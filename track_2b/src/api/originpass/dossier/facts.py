"""Deterministic facts taken from the verdict: number formatting, criterion labels and the JSON facts blocks.

The facts blocks are the only content the model may use; the validator checks generated numbers against them.
"""

from __future__ import annotations

import json
import re
from decimal import ROUND_HALF_UP, Decimal

from ..models import CheckResult, Criterion, CriterionKind, Product, Verdict, VerdictStatus

_CENT = Decimal("0.01")
_STATE = {False: "failed", None: "undecided"}


def fmt_num(value: float) -> str:
    """Canonical number: 2 dp, trailing zeros dropped (47.30 -> '47.3', 50.0 -> '50', -5.25 -> '-5.25')."""
    text = str(Decimal(str(value)).quantize(_CENT, ROUND_HALF_UP))
    text = text.rstrip("0").rstrip(".")
    return "0" if text in ("", "-0") else text


def fmt_chf(value: float, thousands: str = ",") -> str:
    """CHF amount with 2 decimals and a thousands separator: 1250 -> '1,250.00' (Swiss style: "1'250.00")."""
    return f"{Decimal(str(value)).quantize(_CENT, ROUND_HALF_UP):,.2f}".replace(",", thousands)


def hs6_digits(product: Product, verdict: Verdict) -> str | None:
    code = re.sub(r"[\s.]", "", verdict.hs6 or product.hs6 or "")
    return code if re.fullmatch(r"\d{6}", code) else None


def hs6_dotted(code: str) -> str:
    return f"{code[:4]}.{code[4:]}"


# ---------------------------------------------------------------------------
# Origin criterion labels (from the encoded rule, never invented)
# ---------------------------------------------------------------------------

_KIND_LABELS = {
    CriterionKind.WO: ("wholly obtained", "vollständig gewonnen oder hergestellt", "完全获得"),
    CriterionKind.CC: ("change of chapter", "Kapitelwechsel", "章改变"),
    CriterionKind.CTH: ("change of tariff heading", "Positionswechsel", "品目改变"),
    CriterionKind.CTSH: ("change of tariff subheading", "Unterpositionswechsel", "子目改变"),
    CriterionKind.SPECIFIC: ("specific processing", "spezifische Be- oder Verarbeitung", "特定加工工序"),
}
_LANGS = {"en": 0, "de": 1, "zh": 2}
_EXCEPTIONS = {"en": " (with exceptions)", "de": " (mit Ausnahmen)", "zh": "（另有例外规定）"}
_JOIN = {"en": " and ", "de": " und ", "zh": "，并且"}


def criterion_label(c: Criterion, lang: str) -> str:
    if c.kind is CriterionKind.MAXNOM:
        pct = fmt_num(c.max_nom_pct)  # the rule-pack loader rejects MAXNOM without a limit
        return {
            "en": f"non-originating materials not exceeding {pct}% of the ex-works price",
            "de": f"Wert der Vormaterialien ohne Ursprungseigenschaft höchstens {pct.replace('.', ',')} % "
            "des Ab-Werk-Preises",
            "zh": f"非原产材料价值不超过出厂价的{pct}%",
        }[lang]
    label = _KIND_LABELS[c.kind][_LANGS[lang]]
    return label + (_EXCEPTIONS[lang] if c.except_from else "")


def met_criteria(verdict: Verdict) -> list[Criterion]:
    """Criteria of the first alternative that is met ([] if none)."""
    return next((a.criteria for a in verdict.alternatives if a.met is True), [])


def criteria_text(criteria: list[Criterion], lang: str) -> str:
    return _JOIN[lang].join(criterion_label(c, lang) for c in criteria)


# ---------------------------------------------------------------------------
# What blocks the verdict
# ---------------------------------------------------------------------------


def open_checks(verdict: Verdict) -> list[CheckResult]:
    """Checks that keep the verdict from PASS: general checks not passed and, unless an alternative
    is met, the criteria checks not passed in every alternative."""
    if verdict.status is VerdictStatus.PASS:
        return []
    checks = [c for c in verdict.general_checks if c.passed is not True]
    if not any(a.met is True for a in verdict.alternatives):
        checks += [c for a in verdict.alternatives for c in a.checks if c.passed is not True]
    return checks


def blocking_line_ids(verdict: Verdict) -> list[str]:
    """BOM lines named by the open checks or failing the tariff shift, in BOM order."""
    if verdict.status is VerdictStatus.PASS:
        return []
    named = {i for c in open_checks(verdict) for i in c.line_ids}
    named |= {line.line_id for line in verdict.lines if line.shift_ok is False}
    return [line.line_id for line in verdict.lines if line.line_id in named]


def _blocking_lines(product: Product, verdict: Verdict) -> list[dict]:
    bom = {b.line_id: b for b in product.bom}
    out = []
    for line_id in blocking_line_ids(verdict):
        b = bom.get(line_id)
        out.append(
            {
                "line_id": line_id,
                "description": b.description if b else None,
                "origin_country": b.origin_country if b else None,
                "hs6": b.hs6 if b else None,
                "value_chf": fmt_num(b.value_chf) if b else None,
            }
        )
    return out


# ---------------------------------------------------------------------------
# Facts blocks given to the model
# ---------------------------------------------------------------------------


def explanation_facts(product: Product, verdict: Verdict) -> dict:
    """Everything the English explanation may say."""
    hs = hs6_digits(product, verdict)
    rule = verdict.rule
    return {
        "product": product.name,
        "hs6": hs6_dotted(hs) if hs else None,
        "verdict_status": verdict.status.value,
        "rule_id": rule.rule_id if rule else None,
        "rule_text": rule.text if rule else None,
        "rule_verified": verdict.rule_verified,
        "origin_criterion_met": criteria_text(met_criteria(verdict), "en") or None,
        "ex_works_price_chf": fmt_num(product.ex_works_chf),
        "non_originating_value_chf": fmt_num(verdict.nom_value_chf),
        "non_originating_pct_of_ex_works": fmt_num(verdict.nom_pct),
        "max_non_originating_pct": None if verdict.threshold_pct is None else fmt_num(verdict.threshold_pct),
        "margin_pct_points": None if verdict.margin_pct is None else fmt_num(verdict.margin_pct),
        "tolerance_used": verdict.tolerance_used,
        "blocking_lines": _blocking_lines(product, verdict),
        "checks_not_passed": [
            {"check": c.name, "result": _STATE[c.passed], "detail": c.detail} for c in open_checks(verdict)
        ],
        "fixes": verdict.fixes,
        "conclusion": verdict.reasons[-1] if verdict.reasons else None,
    }


def letter_facts(product: Product, verdict: Verdict) -> dict:
    """Everything the Chinese letter may say (no cost data: the buyer does not need it)."""
    hs = hs6_digits(product, verdict)
    preference = verdict.status is VerdictStatus.PASS
    criteria = met_criteria(verdict)
    facts = {
        "letter_case": "preference" if preference else "no_preference",
        "verdict_status": verdict.status.value,
        "product": product.name,
        "hs6": hs6_dotted(hs) if hs else None,
    }
    if preference:
        facts["origin_criterion"] = criteria_text(criteria, "en")
        facts["origin_criterion_zh"] = criteria_text(criteria, "zh")
        if verdict.rule and verdict.rule.text_zh:
            facts["rule_text_zh"] = verdict.rule.text_zh
    else:
        facts["reason"] = (
            "the product does not meet the rules of origin"
            if verdict.status is VerdictStatus.FAIL
            else "the origin check is not complete, so origin cannot be confirmed yet"
        )
    return facts


def facts_json(facts: dict) -> str:
    """Stable JSON rendering (the replay cache is keyed on the exact prompt)."""
    return json.dumps(facts, ensure_ascii=False, indent=2)
