"""Small builders for engine tests (synthetic products and the synthetic fixture rule packs)."""

from __future__ import annotations

from functools import cache
from pathlib import Path

from originpass.models import BomLine, Criterion, CriterionKind, Product, Rule, RulePack, Shipment
from originpass.rulepack import load_rulepack

FIXTURES_DIR = Path(__file__).resolve().parent


@cache
def _load(pack_id: str) -> RulePack:
    return load_rulepack(pack_id, data_dir=FIXTURES_DIR)


def pack(pack_id: str = "test-basic") -> RulePack:
    """A fresh deep copy of a fixture pack, safe to mutate in a test."""
    return _load(pack_id).model_copy(deep=True)


def line(
    line_id: str,
    hs6: str | None,
    origin: str,
    value: float,
    override: bool | None = None,
) -> BomLine:
    return BomLine(
        line_id=line_id,
        description=f"synthetic part {line_id}",
        hs6=hs6,
        origin_country=origin,
        value_chf=value,
        originating_override=override,
    )


def product(
    hs6: str | None,
    bom: list[BomLine],
    ex_works: float = 100.0,
    processing: tuple[str, ...] = ("CNC machining of the housing", "final assembly and testing"),
    transit: tuple[str, ...] = (),
    storage: bool = False,
    exporter: str = "CH",
) -> Product:
    return Product(
        product_id="P-TEST",
        name="Synthetic test product",
        description="synthetic",
        hs6=hs6,
        ex_works_chf=ex_works,
        exporter_country=exporter,
        processing=list(processing),
        bom=bom,
        shipment=Shipment(transit_countries=list(transit), transshipment_or_storage_in_transit=storage),
    )


def crit(kind: str, pct: float | None = None, except_from: tuple[str, ...] = ()) -> Criterion:
    return Criterion(kind=CriterionKind(kind), max_nom_pct=pct, except_from=list(except_from))


def adhoc_pack(alternatives: list[list[Criterion]], scope: tuple[str, ...] = ("84",), **general) -> RulePack:
    """The test-basic pack reduced to one synthetic rule; `general` overrides GeneralProvisions fields."""
    p = pack()
    p.rules = [
        Rule(
            rule_id="TEST-ADHOC",
            hs_scope=list(scope),
            alternatives=alternatives,
            text="SYNTHETIC ad-hoc test rule",
            source="tests (synthetic)",
        )
    ]
    if general:
        p.general = p.general.model_copy(update=general)
    return p
