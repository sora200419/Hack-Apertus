"""Origin engine: fix suggestions, what-if (apply_changes), determinism and seeded property checks."""

from __future__ import annotations

import json
import random
import re

import pytest
from engine_builders import adhoc_pack, crit, line, pack, product
from pydantic import ValidationError

from originpass.engine import apply_changes, evaluate
from originpass.engine.fixes import lines_to_resource
from originpass.engine.materials import Context, assess_material, dec
from originpass.models import Verdict, VerdictStatus

PASS, FAIL, UNSURE = VerdictStatus.PASS, VerdictStatus.FAIL, VerdictStatus.UNSURE
MAXNOM50 = "901890"  # TEST-CH90-MAXNOM50


def resource(verdict_product, line_ids):
    return apply_changes(verdict_product, [{"line_id": i, "origin_country": "CH"} for i in line_ids])


# --- MAXNOM fixes -------------------------------------------------------------------------------


def test_maxnom_fix_smallest_single_line_that_closes_the_gap():
    bom = [line("A", "901890", "US", 30), line("B", "901890", "US", 25), line("C", "901890", "US", 10)]
    v = evaluate(product(MAXNOM50, bom), pack())
    assert v.status is FAIL
    assert v.fixes == [
        "Alternative 1 (MAXNOM 50%): non-originating materials must fall by at least CHF 15.00, from CHF 65.00 "
        "(65.00%) to at most CHF 50.00 (50% of the ex-works price CHF 100.00); re-source line B (CHF 25.00) "
        "from a CH/CN supplier with proof of origin, assuming the same price."
    ]


def test_maxnom_fix_greedy_set_when_no_single_line_suffices():
    p = adhoc_pack([[crit("MAXNOM", 10)]], scope=("90",))
    bom = [line(i, "901890", "US", v) for i, v in [("A", 8), ("B", 7), ("C", 6), ("D", 5)]]
    v = evaluate(product(MAXNOM50, bom), p)
    (fix,) = v.fixes
    assert "at least CHF 16.00" in fix
    assert "lines A (CHF 8.00), B (CHF 7.00) and C (CHF 6.00)" in fix
    assert "together CHF 21.00" in fix
    assert evaluate(resource(product(MAXNOM50, bom), ["A", "B", "C"]), p).status is PASS
    assert evaluate(resource(product(MAXNOM50, bom), ["A", "B"]), p).status is FAIL


def test_maxnom_fix_tie_prefers_bom_order():
    bom = [line("X", "901890", "US", 20), line("Y", "901890", "US", 20), line("Z", "901890", "US", 3)]
    (fix,) = evaluate(product(MAXNOM50, bom), adhoc_pack([[crit("MAXNOM", 30)]], scope=("90",))).fixes
    assert "at least CHF 13.00" in fix and "re-source line X " in fix


def test_maxnom_fix_exact_boundary_line():
    bom = [line("A", "901890", "US", 40), line("B", "901890", "US", 15), line("C", "901890", "US", 16)]
    (fix,) = evaluate(product(MAXNOM50, bom), pack()).fixes  # nom 71, gap exactly 21
    assert "at least CHF 21.00" in fix and "re-source line A " in fix


def test_maxnom_gap_rounded_up_to_the_cent():
    (fix,) = evaluate(product(MAXNOM50, [line("A", "901890", "US", 50.004)]), pack()).fixes
    assert "at least CHF 0.01" in fix and "to at most CHF 50.00" in fix


@pytest.mark.parametrize(
    "values, gap, expected",
    [
        ([30, 25, 10], "15", ["B"]),
        ([30, 25, 10], "26", ["A"]),
        ([30, 25, 10], "31", ["A", "B"]),
        ([8, 7, 6, 5], "16", ["A", "B", "C"]),
        ([5, 5, 5], "5", ["A"]),
        ([0, 4, 3], "6", ["B", "C"]),
    ],
)
def test_lines_to_resource(values, gap, expected):
    materials = tuple(assess_material(line(chr(65 + i), None, "US", v), ["CH", "CN"]) for i, v in enumerate(values))
    assert [m.line_id for m in lines_to_resource(materials, dec(float(gap)))] == expected


# --- tariff shift and WO fixes ------------------------------------------------------------------


def test_shift_fix_lists_violating_lines_and_tolerance():
    bom = [line("L1", "847180", "DE", 20), line("L2", "847190", "JP", 12), line("L3", "850440", "DE", 5)]
    v = evaluate(product("847150", bom), adhoc_pack([[crit("CTH")]]))
    (fix,) = v.fixes
    assert fix.startswith(
        "Alternative 1 (CTH): CTH is broken by lines L1 (HS 847180, CHF 20.00) and L2 (HS 847190, CHF 12.00)"
    )
    assert "together CHF 32.00" in fix
    assert "or keep these lines at or below CHF 10.00 in total (10% general tolerance)" in fix
    assert "L3" not in fix


def test_shift_fix_asks_to_classify_unknown_lines():
    v = evaluate(product("847150", [line("U", None, "DE", 30)]), adhoc_pack([[crit("CTH")]]))
    assert v.status is UNSURE
    (fix,) = v.fixes
    assert "Classify line U (HS unknown, CHF 30.00) to a 6-digit HS code so CTH can be checked" in fix


def test_shift_fix_without_tolerance_clause():
    p = adhoc_pack([[crit("CTSH")]], tolerance_applies_to=[])
    (fix,) = evaluate(product("847150", [line("L1", "847150", "DE", 3)]), p).fixes
    assert "tolerance" not in fix


def test_wo_fix():
    (fix,) = evaluate(product("010121", [line("L1", "230990", "DE", 5)]), pack()).fixes
    assert fix == (
        "Alternative 1 (WO): WO is broken by line L1 (HS 230990, CHF 5.00); "
        "re-source it from CH/CN suppliers with proof of origin."
    )


def test_fixes_cover_every_unmet_alternative_closest_first():
    bom = [line("L1", "847180", "DE", 20), line("L2", "854239", "JP", 43)]
    v = evaluate(product("847150", bom), pack())  # CTH fails (L1), MAXNOM 50 fails (63 %)
    assert v.status is FAIL
    assert [f.split(":")[0] for f in v.fixes] == ["Alternative 1 (CTH)", "Alternative 2 (MAXNOM 50%)"]
    assert "line L1 (HS 847180, CHF 20.00)" in v.fixes[0]
    assert "at least CHF 13.00" in v.fixes[1] and "re-source line L1 " in v.fixes[1]


def test_and_alternative_gives_one_fix_per_failing_criterion():
    v = evaluate(product("847130", [line("L1", "847130", "DE", 45)]), pack())
    assert [f.split(": ")[1].split(" ")[0] for f in v.fixes] == ["CTSH", "non-originating"]


def test_specific_gives_no_fix_but_maxnom_alternative_does():
    v = evaluate(product("300490", [line("L1", "293390", "IN", 60)]), pack())
    assert v.status is UNSURE
    assert len(v.fixes) == 1 and v.fixes[0].startswith("Alternative 2 (MAXNOM 50%)")


@pytest.mark.parametrize(
    "hs6, bom",
    [
        ("847150", [line("L1", "850440", "DE", 10)]),
        ("010121", [line("L1", "230990", "CH", 5)]),
        ("940360", [line("L1", "440710", "VN", 35)]),
    ],
)
def test_no_fixes_on_pass(hs6, bom):
    v = evaluate(product(hs6, bom), pack())
    assert v.status is PASS and v.fixes == []


# --- what-if: apply_changes -----------------------------------------------------------------------


def base_product():
    return product(MAXNOM50, [line("A", "901890", "US", 30), line("B", None, "JP", 25)])


def test_apply_changes_returns_modified_deep_copy():
    original = base_product()
    snapshot = original.model_dump()
    changed = apply_changes(
        original,
        [{"line_id": "A", "origin_country": "CN", "value_chf": 12.5, "hs6": "901820", "originating_override": True}],
    )
    assert original.model_dump() == snapshot
    assert changed is not original and changed.bom[0] is not original.bom[0]
    a = changed.bom[0]
    assert (a.origin_country, a.value_chf, a.hs6, a.originating_override) == ("CN", 12.5, "901820", True)
    changed.bom[1].description = "mutated"
    changed.shipment.transit_countries.append("SG")
    assert original.model_dump() == snapshot


def test_apply_changes_empty_is_equal_copy():
    original = base_product()
    copy = apply_changes(original, [])
    assert copy == original and copy is not original


def test_apply_changes_later_change_wins_and_can_clear_fields():
    changed = apply_changes(
        base_product(),
        [
            {"line_id": "A", "value_chf": 1.0},
            {"line_id": "A", "value_chf": 2.0, "hs6": None, "originating_override": None},
        ],
    )
    assert changed.bom[0].value_chf == 2.0 and changed.bom[0].hs6 is None


@pytest.mark.parametrize(
    "changes",
    [
        [{"line_id": "NOPE", "origin_country": "CH"}],
        [{"origin_country": "CH"}],
        [{"line_id": "A", "price": 3}],
        [{"line_id": "A", "value_chf": -1}],
        [{"line_id": "A", "origin_country": None}],
    ],
)
def test_apply_changes_rejects_bad_changes(changes):
    original = base_product()
    with pytest.raises(ValueError):
        apply_changes(original, changes)
    assert original == base_product()


def test_validation_error_is_a_value_error():
    assert issubclass(ValidationError, ValueError)


@pytest.mark.parametrize(
    "change, status",
    [
        ({"line_id": "A", "origin_country": "CH"}, PASS),  # 25 % non-originating
        ({"line_id": "A", "originating_override": True}, PASS),
        ({"line_id": "A", "value_chf": 25.0}, PASS),  # exactly 50 %
        ({"line_id": "A", "value_chf": 25.01}, FAIL),
        ({"line_id": "B", "origin_country": "CN"}, PASS),
        ({"line_id": "B", "origin_country": "KR"}, FAIL),
    ],
)
def test_what_if_flips_verdict(change, status):
    p = base_product()
    assert evaluate(p, pack()).status is FAIL  # 55 % > 50 %
    assert evaluate(apply_changes(p, [change]), pack()).status is status


def test_what_if_classifying_a_line_decides_the_shift():
    p = product("847150", [line("U", None, "DE", 30)])
    rule = adhoc_pack([[crit("CTH")]])
    assert evaluate(p, rule).status is UNSURE
    assert evaluate(apply_changes(p, [{"line_id": "U", "hs6": "850440"}]), rule).status is PASS
    assert evaluate(apply_changes(p, [{"line_id": "U", "hs6": "847190"}]), rule).status is FAIL


# --- determinism and serialisation ------------------------------------------------------------------


@pytest.mark.parametrize("hs6", ["847150", "847130", "910111", "010121", "300490", "940360", "999999", None])
def test_deterministic_and_json_serialisable(hs6):
    bom = [line("L1", "847180", "DE", 20.1), line("L2", None, "CN", 3), line("L3", "911410", "US", 7.7)]
    p = product(hs6, bom, transit=("SG",))
    first, second = evaluate(p, pack()), evaluate(p, pack())
    assert first.model_dump_json() == second.model_dump_json()
    assert Verdict.model_validate_json(first.model_dump_json()) == first
    json.dumps(first.model_dump(mode="json"))


def test_evaluate_does_not_mutate_inputs():
    p, rp = base_product(), pack()
    before = (p.model_dump_json(), rp.model_dump_json())
    evaluate(p, rp)
    assert (p.model_dump_json(), rp.model_dump_json()) == before


# --- seeded property checks over random BOMs ----------------------------------------------------------

_CODES = ["847180", "847330", "850440", "760429", "901890", "911410", "390110", None]
_COUNTRIES = ["CH", "CN", "DE", "US", "JP", "VN"]
_PRODUCTS = ["847150", "847130", "850440", "901890", "940360", "910111", "392690", "010121"]


def random_product(seed: int):
    rng = random.Random(seed)
    bom = [
        line(f"L{i}", rng.choice(_CODES), rng.choice(_COUNTRIES), round(rng.uniform(0, 30), 2))
        for i in range(rng.randint(0, 6))
    ]
    return product(rng.choice(_PRODUCTS), bom, ex_works=round(rng.uniform(50, 200), 2))


@pytest.mark.parametrize("seed", range(30))
def test_random_bom_invariants(seed):
    p = random_product(seed)
    rp = pack()
    v = evaluate(p, rp)
    nom = sum(dec(b.value_chf) for b in p.bom if b.origin_country not in ("CH", "CN"))
    assert v.nom_value_chf == float(nom)
    assert abs(v.nom_pct - float(nom * 100 / dec(p.ex_works_chf))) <= 0.005
    met = [a.met for a in v.alternatives]
    assert (v.status is PASS) == (True in met)  # general checks pass for these products
    assert (v.status is FAIL) == (bool(met) and all(m is False for m in met))
    assert all(re.search(r"\d", f) for f in v.fixes), v.fixes
    if v.status is PASS:
        assert v.fixes == []
    if v.threshold_pct is not None:
        assert v.margin_pct == pytest.approx(v.threshold_pct - float(nom * 100 / dec(p.ex_works_chf)), abs=0.006)
    assert evaluate(p, rp) == v


@pytest.mark.parametrize("seed", range(20))
def test_maxnom_fix_lines_flip_fail_to_pass(seed):
    rng = random.Random(1000 + seed)
    bom = [line(f"L{i}", "901890", rng.choice(["US", "DE", "CH"]), round(rng.uniform(1, 40), 2)) for i in range(5)]
    p = product(MAXNOM50, bom)
    v = evaluate(p, pack())
    if v.status is PASS:
        return
    ctx = Context("901890", dec(p.ex_works_chf), tuple(assess_material(b, ["CH", "CN"]) for b in bom), pack().general)
    gap = ctx.nom_value - dec(50) * ctx.ex_works / 100
    chosen = [m.line_id for m in lines_to_resource(ctx.non_originating, gap)]
    for line_id in chosen:
        assert f"{line_id} (CHF " in v.fixes[0]
    assert evaluate(resource(p, chosen), pack()).status is PASS
    if len(chosen) > 1:  # greedy set is minimal in size: dropping its smallest line breaks it
        assert evaluate(resource(p, chosen[:-1]), pack()).status is FAIL
