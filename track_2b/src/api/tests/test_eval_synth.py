"""E2 building blocks: synthetic BOMs are deterministic, the reference is sane, engine == reference."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parents[2]  # local checkout: src/ holds the `eval` package
if (_SRC / "eval" / "__init__.py").exists() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from originpass.config import get_settings  # noqa: E402
from originpass.engine.origin import evaluate  # noqa: E402
from originpass.models import BomLine, CriterionKind, Product, RulePack, Shipment  # noqa: E402
from originpass.rulepack.loader import load_rulepack  # noqa: E402

from eval.e2_origin import compare, synthetic_cases  # noqa: E402
from eval.reference import lookup_rule, reference_verdict  # noqa: E402
from eval.synth import generate  # noqa: E402

DATA_DIR = get_settings().data_dir


@pytest.fixture(scope="module")
def pack() -> RulePack:
    return load_rulepack(data_dir=DATA_DIR)


def _maxnom(pack: RulePack, hs6: str) -> float:
    rule = lookup_rule(pack, hs6)
    assert rule is not None
    limits = [c.max_nom_pct for alt in rule.alternatives for c in alt if c.kind is CriterionKind.MAXNOM]
    assert limits and limits[0] is not None
    return limits[0]


def _product(hs6: str | None, lines: list[tuple[str, str | None, float]], **kw) -> Product:
    bom = [
        BomLine(line_id=f"L{i}", description="part", hs6=h, origin_country=o, value_chf=v)
        for i, (o, h, v) in enumerate(lines)
    ]
    return Product(
        product_id="T",
        name="Test",
        description="test",
        hs6=hs6,
        ex_works_chf=1000.0,
        processing=kw.get("processing", ["CNC machining of the housing"]),
        bom=bom,
        shipment=kw.get("shipment", Shipment()),
    )


def test_generate_is_deterministic(pack: RulePack) -> None:
    a = generate(pack, DATA_DIR, n_per_chapter=6, seed=7, chapters=("84", "91"), rules_per_chapter=1)
    b = generate(pack, DATA_DIR, n_per_chapter=6, seed=7, chapters=("84", "91"), rules_per_chapter=1)
    c = generate(pack, DATA_DIR, n_per_chapter=6, seed=8, chapters=("84", "91"), rules_per_chapter=1)
    assert [x.to_dict() for x in a] == [x.to_dict() for x in b]
    assert [x.to_dict() for x in a] != [x.to_dict() for x in c]
    assert sum(x.kind == "random" for x in a) == 12


def test_reference_maxnom_boundary(pack: RulePack) -> None:
    limit = _maxnom(pack, "910221")  # wrist-watch, chapter 91: a value-only rule in the pack
    at_limit = limit * 10  # CHF, ex-works 1000
    assert reference_verdict(_product("910221", [("JP", "910820", at_limit)]), pack).status == "PASS"
    assert reference_verdict(_product("910221", [("JP", "910820", at_limit + 0.01)]), pack).status == "FAIL"
    # Bilateral cumulation: the same material from China is originating.
    assert reference_verdict(_product("910221", [("CN", "910820", 900.0)]), pack).nom_pct == 0.0


def test_reference_general_provisions(pack: RulePack) -> None:
    ok = [("DE", "731815", 10.0)]
    assert reference_verdict(_product(None, ok), pack).status == "UNSURE"
    transit = Shipment(transit_countries=["SG"], transshipment_or_storage_in_transit=True)
    assert reference_verdict(_product("910221", ok, shipment=transit), pack).status == "UNSURE"
    packing_only = ["packaging", "labelling"]
    assert reference_verdict(_product("910221", ok, processing=packing_only), pack).status == "FAIL"
    assert reference_verdict(_product("910221", ok, processing=[]), pack).status == "UNSURE"


def test_engine_equals_reference_on_seeded_sample(pack: RulePack) -> None:
    cases = synthetic_cases(pack, DATA_DIR, n_random=35, seed=11, rules_per_chapter=1)
    assert len(cases) > 35  # random cases plus edge cases
    mismatches = [(c.case_id, diff) for c in cases if not all((diff := compare(c, evaluate(c.product, pack))).values())]
    assert mismatches == []
