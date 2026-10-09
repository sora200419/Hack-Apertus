"""Deterministic synthetic BOM cases for chapters 84, 90 and 91, with ground truth from the reference.

`generate(pack, n_per_chapter, seed)` returns:
- random cases: 4-14 lines, mixed party and non-party origins. Some lines have no HS6 or use dotted
  codes, and a few carry an originating override. Some cases have transit, only insufficient
  processing, or no product HS6.
- edge cases built from up to `rules_per_chapter` rules per chapter:
  - MAXNOM exactly at the limit and one cent over, with neutral or same-subheading materials;
  - general tolerance exactly at the limit and one cent over;
  - missing HS6 within or above the tolerance;
  - bilateral cumulation (CN material vs a DE control);
  - except_from violations, originating overrides, and the general checks.

Amounts are whole cents, so the boundaries are exact. Labels come from `reference.reference_verdict`,
an independent re-implementation, and never from originpass.engine.
"""

from __future__ import annotations

import csv
import random
from dataclasses import asdict, dataclass
from pathlib import Path

from originpass.models import BomLine, CriterionKind, Product, Rule, RulePack, Shipment

from .reference import RefVerdict, clean_hs, lookup_rule, reference_verdict

CHAPTERS = ("84", "90", "91")
PARTIES = ("CH", "CN")
NON_PARTIES = ("DE", "IT", "FR", "AT", "JP", "US", "KR", "TW", "CZ", "SE")
MATERIAL_CHAPTERS = ("39", "40", "70", "72", "73", "74", "76", "83", "84", "85", "90", "91")
# Real HS 2022 subheadings for "neutral" bought-in parts (screws, gaskets, plastic parts, motors, ...)
NEUTRAL_CODES = ("731815", "401693", "392690", "760429", "854442", "850152", "848210", "903289")
SUFFICIENT_OPS = (
    "CNC machining of the housing",
    "winding and assembly of rotor and stator",
    "TIG welding of the frame",
    "heat treatment and precision grinding",
    "calibration and final functional test",
    "injection moulding of the cover",
    "SMT assembly of the control board and firmware flashing",
    "assembly and regulation of the movement",
)
TRANSIT = ("DE", "NL", "SG", "HK", "AE")
EX_WORKS_CENTS = 100_000  # CHF 1000.00 for edge cases: percentages map to whole cents


@dataclass(frozen=True)
class SynthCase:
    case_id: str
    chapter: str
    kind: str  # "random" or "edge:<name>"
    product: Product
    expected: RefVerdict

    def to_dict(self) -> dict:
        return {
            "case_id": self.case_id,
            "chapter": self.chapter,
            "kind": self.kind,
            "product": self.product.model_dump(mode="json"),
            "expected": asdict(self.expected),
        }


def hs_catalogue(data_dir: Path) -> list[str]:
    """Sorted 6-digit HS 2022 codes from data/hs/hs2022.csv."""
    with (data_dir / "hs" / "hs2022.csv").open(encoding="utf-8-sig", newline="") as f:
        return sorted(r["hscode"] for r in csv.DictReader(f) if r["level"] == "6" and r["section"] != "TOTAL")


def generate(
    pack: RulePack,
    data_dir: Path,
    n_per_chapter: int = 40,
    seed: int = 2026,
    chapters: tuple[str, ...] = CHAPTERS,
    rules_per_chapter: int = 3,
) -> list[SynthCase]:
    """Random and edge cases for each chapter, labelled by the reference implementation."""
    codes = hs_catalogue(data_dir)
    cases: list[SynthCase] = []
    for chapter in chapters:
        rng = random.Random(f"{seed}:{chapter}")
        in_chapter = [c for c in codes if c.startswith(chapter)]
        covered: dict[str, list[str]] = {}
        for c in in_chapter:
            rule = lookup_rule(pack, c)
            if rule is not None:
                covered.setdefault(rule.rule_id, []).append(c)
        pool = [c for cs in covered.values() for c in cs] or in_chapter
        pool.sort()
        gen = _Gen(rng, pack, codes)
        for i in range(1, n_per_chapter + 1):
            product = gen.random_product(f"SYN-{chapter}-R{i:03d}", rng.choice(pool))
            cases.append(SynthCase(product.product_id, chapter, "random", product, reference_verdict(product, pack)))
        rule_ids = sorted(covered)
        for rule_id in sorted(rng.sample(rule_ids, min(rules_per_chapter, len(rule_ids)))):
            rule = next(r for r in pack.rules if r.rule_id == rule_id)
            code = rng.choice(covered[rule_id])
            for name, product in gen.edge_products(rule, code, f"SYN-{chapter}-E-{rule_id}"):
                expected = reference_verdict(product, pack)
                cases.append(SynthCase(product.product_id, chapter, f"edge:{name}", product, expected))
    return cases


def split_cents(total: int, weights: list[float]) -> list[int]:
    """Split `total` cents proportionally to `weights`; the last part takes the rounding remainder."""
    s = sum(weights)
    parts = [int(total * w / s) for w in weights[:-1]]
    return [*parts, total - sum(parts)]


class _Gen:
    def __init__(self, rng: random.Random, pack: RulePack, codes: list[str]):
        self.rng = rng
        self.pack = pack
        self.codes = codes
        self.by_chapter: dict[str, list[str]] = {}
        for c in codes:
            self.by_chapter.setdefault(c[:2], []).append(c)

    # -- random cases -------------------------------------------------------
    def random_product(self, product_id: str, code: str) -> Product:
        rng = self.rng
        rule = lookup_rule(self.pack, code)
        excluded = _except_prefixes(rule)
        ex_works = rng.randint(20_000, 2_500_000)
        n = rng.randint(4, 14)
        values = split_cents(int(ex_works * rng.uniform(0.35, 0.9)), [rng.random() + 0.05 for _ in range(n)])
        p_party = rng.uniform(0.15, 0.85)
        lines = []
        for i, cents in enumerate(values, start=1):
            origin = rng.choice(PARTIES) if rng.random() < p_party else rng.choice(NON_PARTIES)
            hs: str | None = self._material_code(code, excluded)
            r = rng.random()
            if r < 0.08:
                hs = None
            elif r < 0.16:
                hs = f"{hs[:4]}.{hs[4:]}"
            override = (rng.random() < 0.5) if rng.random() < 0.04 else None
            lines.append(_line(f"L{i:02d}", hs, origin, cents, override))
        processing = self._processing()
        shipment = Shipment()
        if rng.random() < 0.07:
            shipment = Shipment(
                transit_countries=[rng.choice(TRANSIT)], transshipment_or_storage_in_transit=rng.random() < 0.5
            )
        product_hs = None if rng.random() < 0.03 else code
        return _product(product_id, product_hs, ex_works, lines, processing, shipment)

    def _material_code(self, product_code: str, excluded: list[str]) -> str:
        rng = self.rng
        r = rng.random()
        if r < 0.10:
            return product_code
        if r < 0.22:
            return rng.choice([c for c in self.by_chapter[product_code[:2]] if c[:4] == product_code[:4]])
        if r < 0.34:
            return rng.choice(self.by_chapter[product_code[:2]])
        if r < 0.40 and excluded:
            prefix = rng.choice(excluded)
            return rng.choice([c for c in self.codes if c.startswith(prefix)] or [product_code])
        return rng.choice(self.by_chapter[rng.choice(MATERIAL_CHAPTERS)])

    def _processing(self) -> list[str]:
        rng = self.rng
        weak = self.pack.general.insufficient_operations
        r = rng.random()
        if r < 0.05:
            return []
        if r < 0.11 and weak:
            return [f"{op} of the finished goods" for op in rng.sample(weak, min(2, len(weak)))]
        ops = rng.sample(SUFFICIENT_OPS, rng.randint(1, 3))
        if weak and rng.random() < 0.3:
            ops.append(rng.choice(weak))
        return ops

    # -- edge cases -----------------------------------------------------------
    def edge_products(self, rule: Rule, code: str, id_prefix: str) -> list[tuple[str, Product]]:
        """(name, product) pairs exercising the boundaries of `rule` and the general provisions."""
        excluded = _except_prefixes(rule)
        neutral = [c for c in NEUTRAL_CODES if c[:2] != code[:2] and not c.startswith(tuple(excluded))]
        n1, n2 = neutral[0], neutral[1]
        e = EX_WORKS_CENTS
        big = e * 30 // 100
        out: list[tuple[str, Product]] = []

        def add(
            name: str,
            lines: list[BomLine],
            ops: list[str] | None = None,
            shipment: Shipment | None = None,
            hs: str | None = code,
        ) -> None:
            ops = list(SUFFICIENT_OPS[:2]) if ops is None else ops
            out.append((name, _product(f"{id_prefix}-{name}", hs, e, lines, ops, shipment or Shipment())))

        clean = [_line("L01", n1, "DE", e * 20 // 100), _line("L02", n2, "CH", e * 30 // 100)]
        for limit in _maxnom_limits(rule):
            cap = round(limit * e) // 100
            for extra, label in ((0, "at_limit"), (1, "over_by_cent")):
                nom = cap + extra
                first = nom * 6 // 10
                originating = _line("L03", n2, "CH", e * 15 // 100)
                name = f"maxnom{limit:g}_{label}"
                add(name, [_line("L01", n1, "DE", first), _line("L02", n2, "JP", nom - first), originating])
                same = [_line("L01", code, "IT", first), _line("L02", n1, "US", nom - first), originating]
                add(f"{name}_same_subheading", same)

        tol = self.pack.general.tolerance_pct
        kinds = {c.kind for alt in rule.alternatives for c in alt}
        if tol > 0 and kinds & set(self.pack.general.tolerance_applies_to):
            cap = round(tol * e) // 100
            base = [_line("L02", n1, "DE", e * 20 // 100), _line("L03", n2, "CH", e * 20 // 100)]
            add("tolerance_at_limit", [_line("L01", code, "DE", cap), *base])
            add("tolerance_over_by_cent", [_line("L01", code, "DE", cap + 1), *base])
            add("missing_hs6_within_tolerance", [_line("L01", None, "DE", cap), *base])
            add("missing_hs6_above_tolerance", [_line("L01", None, "DE", cap + 5_000), *base])
            split = [_line("L01", code, "DE", cap // 2), _line("L04", None, "JP", cap - cap // 2 + 1)]
            add("violating_within_but_unknown_over", [*split, *base])

        add("cumulation_cn_same_subheading", [_line("L01", code, "CN", big), *clean])
        add("cumulation_control_de_same_subheading", [_line("L01", code, "DE", big), *clean])
        add("override_true_same_subheading", [_line("L01", code, "DE", big, True), *clean])
        add("override_false_ch_same_subheading", [_line("L01", code, "CH", big, False), *clean])
        add("missing_hs6_large", [_line("L01", None, "US", big), *clean])
        for prefix in excluded:
            hits = [c for c in self.codes if c.startswith(prefix)]
            hits = [c for c in hits if c[:4] != code[:4]] or hits
            if hits:
                add(f"except_from_{prefix}", [_line("L01", hits[0], "DE", big), *clean])
                add(f"except_from_{prefix}_cn", [_line("L01", hits[0], "CN", big), *clean])

        weak = self.pack.general.insufficient_operations
        if weak:
            add("insufficient_processing_only", clean, ops=[f"{w} for export" for w in weak[:2]])
            add("mixed_processing", clean, ops=[weak[0], SUFFICIENT_OPS[0]])
        add("no_processing_described", clean, ops=[])
        storage = Shipment(transit_countries=["SG"], transshipment_or_storage_in_transit=True)
        add("transit_with_storage", clean, shipment=storage)
        add("no_product_hs6", clean, hs=None)
        dotted = [ln.model_copy(update={"hs6": f"{ln.hs6[:4]}.{ln.hs6[4:]}"}) for ln in clean]
        add("dotted_codes", dotted, hs=f"{code[:4]}.{code[4:]}")
        return out


def _maxnom_limits(rule: Rule) -> list[float]:
    return sorted(
        {c.max_nom_pct for alt in rule.alternatives for c in alt if c.kind is CriterionKind.MAXNOM and c.max_nom_pct}
    )


def _except_prefixes(rule: Rule | None) -> list[str]:
    if rule is None:
        return []
    return sorted({clean_hs(p) for alt in rule.alternatives for c in alt for p in c.except_from if clean_hs(p)})


def _line(line_id: str, hs: str | None, origin: str, cents: int, override: bool | None = None) -> BomLine:
    desc = f"synthetic material HS {hs}" if hs else "synthetic material, HS code unknown"
    return BomLine(
        line_id=line_id,
        description=desc,
        hs6=hs,
        origin_country=origin,
        value_chf=cents / 100,
        originating_override=override,
    )


def _product(
    product_id: str,
    hs: str | None,
    ex_works_cents: int,
    lines: list[BomLine],
    processing: list[str],
    shipment: Shipment,
) -> Product:
    return Product(
        product_id=product_id,
        name=f"Synthetic product {product_id}",
        description=f"Synthetic test product, HS {hs or 'unknown'}",
        hs6=hs,
        ex_works_chf=ex_works_cents / 100,
        processing=processing,
        bom=lines,
        shipment=shipment,
    )
