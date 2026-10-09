"""E2: origin verdicts. (a) engine vs the independent reference on seeded synthetic BOMs, (b) the demo
products, (c) an 'LLM-only' baseline: Apertus (large) reads the rule text and the BOM and decides itself.

(a) Synthetic cases come from `synth.generate` (random BOMs plus boundary cases per rule) for MAXNOM
chapters 84/85/90/91 and the 'CTH or VNM 60 %' chapters 73/83/94 of the real pack. Labels come from
`reference.reference_verdict`, which shares no code with the engine. We report status agreement, full
agreement (status, rule, NOM %, each alternative, each general check), the confusion matrix and the
false-PASS rate (engine PASS where the reference says FAIL/UNSURE; the target is 0).

(c) The baseline gets the same inputs as the engine (rule text EN + ZH, general provisions, BOM lines with
HS code, origin and value, ex-works price, processing, transport) and must answer PASS/FAIL/UNSURE and the
non-originating share. It is scored against the engine on a seeded sample of the random cases plus the
demos: accuracy, false-PASS rate, mean absolute error of the VNM %. Without a model answer it is 'not run'.
"""

from __future__ import annotations

import random
from collections import Counter, defaultdict
from pathlib import Path

from originpass.engine.origin import evaluate
from originpass.llm import LLMClient, extract_json
from originpass.models import Product, RulePack, Verdict

from .demos import demo_table, load_demos, load_tuning, swap
from .reference import lookup_rule
from .synth import SynthCase, generate
from .util import LLM_DOWN, TrackedLLM, ratio

CHAPTERS = ("84", "85", "90", "91", "73", "83", "94")
STATUSES = ("PASS", "FAIL", "UNSURE")
MAX_DISAGREEMENTS = 10

BASELINE_MAX_TOKENS = 300
BASELINE_SYSTEM = (
    "You are a rules-of-origin expert for the Free Trade Agreement between the People's Republic of China and "
    "the Swiss Confederation. Decide whether the product below qualifies as originating in the exporting Party "
    "and therefore for preferential tariff treatment. Use only the product-specific rule and the general "
    "provisions given; compute the share of non-originating materials yourself from the bill of materials.\n"
    "PASS = the product-specific rule and all general provisions are met. FAIL = the rule or a general "
    "provision is not met. UNSURE = the information given is not sufficient to decide.\n"
    'Reply with JSON only: {"status": "PASS" | "FAIL" | "UNSURE", "nom_pct": <non-originating materials as a '
    'percentage of the ex-works price, 2 decimals>, "reason": "<at most 30 words>"}'
)
BASELINE_USER = (
    "Product: {name}; HS code of the product: {hs6}; ex-works price: CHF {ex_works}; exporting Party: {exporter}\n"
    "Product-specific rule {rule_id} (English): {rule_en}\n"
    "Product-specific rule (official Chinese text): {rule_zh}\n"
    "General provisions:\n"
    "- {tolerance}\n"
    "- Cumulation: materials originating in {parties} count as originating materials.\n"
    "- {operations}\n"
    "- {transport}\n"
    "Processing carried out in the exporting Party: {processing}\n"
    "Transport: transit countries: {transit}; transshipment or storage in transit: {storage}\n"
    "Bill of materials (line | description | HS code | country of origin | value CHF):\n{lines}"
)


def synthetic_cases(
    pack: RulePack, data_dir: Path, n_random: int, seed: int, rules_per_chapter: int
) -> list[SynthCase]:
    """`n_random` random cases spread over CHAPTERS (remainder to the first chapters) plus edge cases."""
    cases: list[SynthCase] = []
    for i, chapter in enumerate(CHAPTERS):
        n = n_random // len(CHAPTERS) + (i < n_random % len(CHAPTERS))
        cases += generate(
            pack, data_dir, n_per_chapter=n, seed=seed, chapters=(chapter,), rules_per_chapter=rules_per_chapter
        )
    return cases


def compare(case: SynthCase, verdict: Verdict) -> dict[str, bool]:
    ref = case.expected
    general = tuple(c.passed for c in verdict.general_checks)
    return {
        "status": verdict.status.value == ref.status,
        "rule": (verdict.rule.rule_id if verdict.rule else None) == ref.rule_id,
        "nom_pct": verdict.nom_pct == ref.nom_pct,
        "alternatives": tuple(a.met for a in verdict.alternatives) == ref.alternatives_met,
        "general": general == ref.general,
    }


def agreement(pairs: list[tuple[SynthCase, Verdict]]) -> dict:
    """Agreement statistics of engine verdicts with reference labels."""
    n = len(pairs)
    checks = [compare(c, v) for c, v in pairs]
    confusion = {r: {e: 0 for e in STATUSES} for r in STATUSES}
    for case, v in pairs:
        confusion[case.expected.status][v.status.value] += 1
    ref_non_pass = sum(c.expected.status != "PASS" for c, _ in pairs)
    false_pass = sum(confusion[r]["PASS"] for r in ("FAIL", "UNSURE"))
    by_chapter: dict[str, list[bool]] = defaultdict(list)
    for (case, _), ch in zip(pairs, checks, strict=True):
        by_chapter[case.chapter].append(ch["status"])
    return {
        "n": n,
        "status_agreement": ratio(sum(ch["status"] for ch in checks), n),
        "full_agreement": ratio(sum(all(ch.values()) for ch in checks), n),
        "field_agreement": {
            f: ratio(sum(ch[f] for ch in checks), n) for f in ("rule", "nom_pct", "alternatives", "general")
        },
        "confusion_reference_x_engine": confusion,
        "reference_status_counts": dict(Counter(c.expected.status for c, _ in pairs)),
        "false_pass": false_pass,
        "false_pass_rate": ratio(false_pass, ref_non_pass),
        "false_fail": confusion["PASS"]["FAIL"] + confusion["UNSURE"]["FAIL"],
        "by_chapter": {
            ch: {"n": len(v), "status_agreement": ratio(sum(v), len(v))} for ch, v in sorted(by_chapter.items())
        },
    }


def disagreements(pairs: list[tuple[SynthCase, Verdict]]) -> list[dict]:
    out = []
    for case, v in pairs:
        diff = [f for f, ok in compare(case, v).items() if not ok]
        if diff:
            out.append(
                {
                    "case_id": case.case_id,
                    "kind": case.kind,
                    "fields": diff,
                    "reference": case.expected.status,
                    "engine": v.status.value,
                    "reference_trace": list(case.expected.trace),
                }
            )
    return out[:MAX_DISAGREEMENTS]


# ---------------------------------------------------------------------------
# (c) LLM-only baseline
# ---------------------------------------------------------------------------


def baseline_messages(product: Product, pack: RulePack) -> list[dict]:
    rule = lookup_rule(pack, (product.hs6 or "").replace(".", "").strip())
    g = pack.general
    lines = "\n".join(
        f"{ln.line_id} | {ln.description} | {ln.hs6 or 'unknown'} | {ln.origin_country} | {ln.value_chf:.2f}"
        + (
            f" | originating (supplier proof): {'yes' if ln.originating_override else 'no'}"
            if ln.originating_override is not None
            else ""
        )
        for ln in product.bom
    )
    user = BASELINE_USER.format(
        name=product.name,
        hs6=product.hs6 or "unknown",
        ex_works=f"{product.ex_works_chf:.2f}",
        exporter=product.exporter_country,
        rule_id=rule.rule_id if rule else "-",
        rule_en=rule.text if rule else "no product-specific rule found",
        rule_zh=(rule.text_zh or "-") if rule else "-",
        tolerance=g.tolerance_text,
        parties=" and ".join(g.cumulation_parties),
        operations=g.insufficient_operations_text,
        transport=g.direct_transport_text,
        processing="; ".join(product.processing) or "not described",
        transit=", ".join(product.shipment.transit_countries) or "none",
        storage="yes" if product.shipment.transshipment_or_storage_in_transit else "no",
        lines=lines,
    )
    return [{"role": "system", "content": BASELINE_SYSTEM}, {"role": "user", "content": user}]


def parse_baseline(text: str) -> tuple[str | None, float | None]:
    """(status, nom_pct) from the model reply; None for a missing or malformed field."""
    data = extract_json(text)
    if not isinstance(data, dict):
        return None, None
    status = str(data.get("status", "")).strip().upper()
    raw = data.get("nom_pct")
    try:
        nom = float(str(raw).replace("%", "").strip()) if raw is not None and not isinstance(raw, bool) else None
    except ValueError:
        nom = None
    return (status if status in STATUSES else None), nom


def llm_baseline(products: list[Product], pack: RulePack, client: LLMClient | None) -> tuple[dict, TrackedLLM | None]:
    """Score the LLM-only verdicts against the engine."""
    tracker = TrackedLLM(client) if client is not None else None
    rows = []
    for p in products:
        if tracker is None:
            break
        try:
            res = tracker.chat(
                baseline_messages(p, pack), role="large", max_tokens=BASELINE_MAX_TOKENS, tag="e2.llm_only"
            )
        except LLM_DOWN:
            continue
        status, nom = parse_baseline(res.text)
        rows.append((p.product_id, evaluate(p, pack), status, nom))
    n = len(products)
    out: dict = {"items": n, "items_answered": len(rows), "model_role": "large", "max_tokens": BASELINE_MAX_TOKENS}
    if tracker is not None:
        out["missing_cache_entries"] = tracker.misses()
    if not rows:
        note = "no LLM client" if tracker is None else f"no endpoint/cache: {n}/{n} items without a model answer"
        return out | {"status": "not run", "note": note}, tracker
    engine_non_pass = sum(t.status.value != "PASS" for _, t, _, _ in rows)
    false_pass = sum(s == "PASS" and t.status.value != "PASS" for _, t, s, _ in rows)
    errors = [abs(nom - t.nom_pct) for _, t, _, nom in rows if nom is not None]
    out |= {
        "status": "run" if len(rows) == n else "partial",
        "accuracy": ratio(sum(s == t.status.value for _, t, s, _ in rows), len(rows)),
        "unparseable": sum(s is None for _, _, s, _ in rows),
        "false_pass": false_pass,
        "false_pass_rate": ratio(false_pass, engine_non_pass),
        "nom_pct_mae_pp": round(sum(errors) / len(errors), 3) if errors else None,
        "nom_pct_answers": len(errors),
        "confusion_engine_x_llm": _confusion([(t.status.value, s or "unparseable") for _, t, s, _ in rows]),
    }
    if len(rows) < n:
        out["note"] = f"{n - len(rows)}/{n} items without a model answer are not scored"
    return out, tracker


def _confusion(pairs: list[tuple[str, str]]) -> dict[str, dict[str, int]]:
    cols = (*STATUSES, "unparseable")
    table = {r: {c: 0 for c in cols} for r in STATUSES}
    for r, c in pairs:
        table[r][c] += 1
    return table


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def run(
    pack: RulePack,
    data_dir: Path,
    client: LLMClient | None,
    n_random: int = 300,
    seed: int = 2026,
    rules_per_chapter: int = 3,
    llm_n: int = 100,
) -> tuple[dict, dict[str, TrackedLLM]]:
    """E2 results and the LLM-only baseline's call tracker (for E4), keyed 'e2.llm_only'."""
    cases = synthetic_cases(pack, data_dir, n_random, seed, rules_per_chapter)
    pairs = [(c, evaluate(c.product, pack)) for c in cases]
    random_pairs = [(c, v) for c, v in pairs if c.kind == "random"]
    edge_pairs = [(c, v) for c, v in pairs if c.kind != "random"]

    demos = load_demos(data_dir)
    swaps = []
    for spec in load_tuning(data_dir):
        if spec["product_id"] in demos:
            before = evaluate(demos[spec["product_id"]], pack)
            after = evaluate(swap(demos[spec["product_id"]], spec), pack)
            swaps.append(
                {
                    "product_id": spec["product_id"],
                    "swap": f"{spec['swing_line']}: " + ", ".join(f"{k} = {v}" for k, v in spec["swap"].items()),
                    "before": f"{before.status.value} ({before.nom_pct}%)",
                    "after": f"{after.status.value} ({after.nom_pct}%)",
                }
            )

    rng = random.Random(f"{seed}:llm-baseline")
    sample = sorted(rng.sample([c for c, _ in random_pairs], min(llm_n, len(random_pairs))), key=lambda c: c.case_id)
    baseline, tracker = llm_baseline([c.product for c in sample] + list(demos.values()), pack, client)
    baseline["sample"] = {"synthetic": len(sample), "demos": len(demos), "seed": f"{seed}:llm-baseline"}

    results = {
        "synthetic": {
            "config": {
                "seed": seed,
                "chapters": list(CHAPTERS),
                "n_random": n_random,
                "rules_per_chapter": rules_per_chapter,
            },
            "random": agreement(random_pairs),
            "edge": agreement(edge_pairs) | {"kinds": len({c.kind for c, _ in edge_pairs})},
            "disagreements": disagreements(pairs),
        },
        "demos": {"table": demo_table(demos, pack), "swaps": swaps},
        "llm_baseline": baseline,
    }
    return results, {"e2.llm_only": tracker} if tracker is not None else {}
