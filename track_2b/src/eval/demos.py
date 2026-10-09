"""Demo products: verdict table, automatic re-tuning to the rule pack's MAXNOM threshold, CSV export.

Threshold demos are listed in data/bom/demo_tuning.json. Each entry names a swing BOM line and a
supplier swap. `retune` reads the MAXNOM limit T from the loaded rule pack, so the limit is never
hard-coded. It then sets only the ex-works price so that the non-originating share sits
`target_margin_pp` below T (PASS; negative = above T, FAIL), and checks with the independent reference
and with the engine that the single swap flips the verdict. When the rule pack changes, run:

    python -m eval.demos --write      # from src/api; re-tunes, rewrites the JSON and CSV files
"""

from __future__ import annotations

import argparse
import csv
import io
import json
from dataclasses import asdict, dataclass
from fractions import Fraction
from pathlib import Path

from originpass.engine.origin import evaluate
from originpass.models import BomLine, CriterionKind, Product, RulePack

from .reference import lookup_rule, money, reference_verdict

CSV_COLUMNS = ["line_id", "description", "hs6", "origin_country", "value_chf", "supplier"]
TUNING_FILE = Path("bom") / "demo_tuning.json"
DEMO_DIR = Path("bom") / "demo"


@dataclass(frozen=True)
class TuneResult:
    product_id: str
    ok: bool
    note: str
    rule_id: str | None = None
    threshold_pct: float | None = None
    ex_works_old: float | None = None
    ex_works_new: float | None = None
    status_before: str | None = None
    nom_pct_before: float | None = None
    status_after_swap: str | None = None
    nom_pct_after_swap: float | None = None


def demo_paths(data_dir: Path) -> dict[str, Path]:
    """product_id -> JSON path of every demo product."""
    out = {}
    for path in sorted((data_dir / DEMO_DIR).glob("*.json")):
        out[json.loads(path.read_text(encoding="utf-8"))["product_id"]] = path
    return out


def load_demos(data_dir: Path) -> dict[str, Product]:
    return {pid: Product.model_validate_json(p.read_text(encoding="utf-8")) for pid, p in demo_paths(data_dir).items()}


def load_tuning(data_dir: Path) -> list[dict]:
    path = data_dir / TUNING_FILE
    return json.loads(path.read_text(encoding="utf-8"))["demos"] if path.exists() else []


def swap(product: Product, spec: dict) -> Product:
    """The product after the spec's single supplier swap on its swing line."""
    bom = [ln.model_copy(update=spec["swap"]) if ln.line_id == spec["swing_line"] else ln for ln in product.bom]
    return product.model_copy(update={"bom": bom})


def retune(product: Product, spec: dict, pack: RulePack) -> tuple[Product, TuneResult]:
    """Set the ex-works price so that `spec["swap"]` flips the verdict at the pack's MAXNOM limit."""
    pid = product.product_id
    rule = lookup_rule(pack, product.hs6 or "")
    limits = sorted(
        {
            c.max_nom_pct
            for alt in (rule.alternatives if rule else [])
            for c in alt
            if c.kind is CriterionKind.MAXNOM and c.max_nom_pct is not None
        },
        reverse=True,
    )
    if rule is None or not limits:
        what = f"rule {rule.rule_id} has no MAXNOM criterion" if rule else f"no rule for HS {product.hs6}"
        return product, TuneResult(pid, False, f"skipped: {what}", rule.rule_id if rule else None)
    margin = Fraction(repr(float(spec["target_margin_pp"])))
    step = Fraction(repr(float(spec.get("round_chf", 5))))
    want_before = "PASS" if margin > 0 else "FAIL"
    want_after = "FAIL" if margin > 0 else "PASS"
    parties = {p.upper() for p in pack.general.cumulation_parties}
    nom = sum(
        (money(ln.value_chf) for ln in product.bom if not _originating(ln, parties)),
        Fraction(0),
    )
    materials = sum((money(ln.value_chf) for ln in product.bom), Fraction(0))
    notes = []
    for limit in limits:
        target = money(limit) - margin
        ex_works = round(nom * 100 / target / step) * step
        if ex_works <= materials:
            notes.append(f"MAXNOM {limit:g}: ex-works {float(ex_works):.2f} would not cover the materials")
            continue
        tuned = product.model_copy(update={"ex_works_chf": float(ex_works)})
        before, after = reference_verdict(tuned, pack), reference_verdict(swap(tuned, spec), pack)
        if (before.status, after.status) != (want_before, want_after):
            notes.append(
                f"MAXNOM {limit:g}: swap gives {before.status} -> {after.status}, not {want_before} -> {want_after}"
            )
            continue
        engine_note = _engine_agrees(tuned, swap(tuned, spec), pack, (before.status, after.status))
        result = TuneResult(
            pid,
            engine_note is None,
            engine_note or f"tuned to MAXNOM {limit:g}% with margin {float(margin):g} pp",
            rule.rule_id,
            limit,
            product.ex_works_chf,
            float(ex_works),
            before.status,
            before.nom_pct,
            after.status,
            after.nom_pct,
        )
        return tuned, result
    return product, TuneResult(pid, False, "cannot tune: " + "; ".join(notes), rule.rule_id)


def _originating(line: BomLine, parties: set[str]) -> bool:
    if line.originating_override is not None:
        return line.originating_override
    return line.origin_country.strip().upper() in parties


def _engine_agrees(before: Product, after: Product, pack: RulePack, expected: tuple[str, str]) -> str | None:
    """None if the engine gives the same two statuses, else a note."""
    got = (evaluate(before, pack).status.value, evaluate(after, pack).status.value)
    return None if got == expected else f"engine gives {got}, reference {expected}: investigate"


def bom_csv(product: Product) -> str:
    """BOM lines in the upload CSV format (line_id,description,hs6,origin_country,value_chf,supplier)."""
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(CSV_COLUMNS)
    for ln in product.bom:
        writer.writerow(
            [ln.line_id, ln.description, ln.hs6 or "", ln.origin_country, f"{ln.value_chf:.2f}", ln.supplier or ""]
        )
    return buf.getvalue()


def product_json(product: Product) -> str:
    return json.dumps(product.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n"


def demo_table(products: dict[str, Product], pack: RulePack) -> list[dict]:
    """One row per demo: engine and reference status, NOM share, rule."""
    rows = []
    for pid, p in products.items():
        ref = reference_verdict(p, pack)
        engine = evaluate(p, pack)
        rows.append(
            {
                "product_id": pid,
                "hs6": p.hs6,
                "rule_id": ref.rule_id,
                "lines": len(p.bom),
                "lines_without_hs6": sum(1 for ln in p.bom if not ln.hs6),
                "nom_pct": ref.nom_pct,
                "reference_status": ref.status,
                "engine_status": engine.status.value,
                "threshold_pct": engine.threshold_pct,
            }
        )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--pack", default="ch-cn-2014")
    parser.add_argument("--pack-dir", type=Path, default=None, help="directory holding rulepacks/ (default DATA_DIR)")
    parser.add_argument("--write", action="store_true", help="write re-tuned JSON and regenerated CSV files")
    args = parser.parse_args()

    from originpass.config import get_settings
    from originpass.rulepack.loader import load_rulepack

    data_dir = get_settings().data_dir
    pack = load_rulepack(args.pack, data_dir=args.pack_dir or data_dir)
    products = load_demos(data_dir)
    paths = demo_paths(data_dir)
    for spec in load_tuning(data_dir):
        tuned, result = retune(products[spec["product_id"]], spec, pack)
        print(json.dumps(asdict(result), ensure_ascii=False))
        if args.write and result.ok:
            products[spec["product_id"]] = tuned
            paths[spec["product_id"]].write_text(product_json(tuned), encoding="utf-8")
    if args.write:
        for pid in csv_demo_ids(data_dir):
            paths[pid].with_suffix(".csv").write_text(bom_csv(products[pid]), encoding="utf-8")
    for row in demo_table(products, pack):
        print(json.dumps(row, ensure_ascii=False))


def csv_demo_ids(data_dir: Path) -> list[str]:
    path = data_dir / TUNING_FILE
    return json.loads(path.read_text(encoding="utf-8")).get("csv_exports", []) if path.exists() else []


if __name__ == "__main__":
    main()
