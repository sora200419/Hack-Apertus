"""Origin engine: criterion kinds, tolerance, cumulation, overrides, OR/AND logic, status (synthetic packs)."""

from __future__ import annotations

import pytest
from engine_builders import adhoc_pack, crit, line, pack, product

from originpass.engine import evaluate
from originpass.models import CriterionKind, VerdictStatus

PASS, FAIL, UNSURE = VerdictStatus.PASS, VerdictStatus.FAIL, VerdictStatus.UNSURE


def only_check(verdict, alt: int = 0, idx: int = 0):
    return verdict.alternatives[alt].checks[idx]


# --- product classification and rule lookup ---------------------------------------------------


@pytest.mark.parametrize("hs6", [None, "", "8471", "84715", "8471500", "ABCDEF", "84-71-50"])
def test_invalid_product_hs6_is_unsure(hs6):
    v = evaluate(product(hs6, [line("L1", "850440", "DE", 10)]), pack())
    assert v.status is UNSURE
    assert v.rule is None and v.rule_verified is False
    assert "classify the product first" in v.reasons[0]
    assert v.alternatives == [] and v.fixes == []
    assert v.nom_pct == 10.0  # materials are still assessed for display
    assert [c.name for c in v.general_checks] == ["insufficient processing", "direct transport"]


@pytest.mark.parametrize("hs6", ["8471.50", " 847150", "847150"])
def test_product_hs6_normalised(hs6):
    v = evaluate(product(hs6, [line("L1", "850440", "DE", 10)]), pack())
    assert v.hs6 == "847150"
    assert v.rule.rule_id == "TEST-8471-CTH-OR-MAXNOM50"


def test_no_rule_is_unsure():
    v = evaluate(product("999999", [line("L1", "850440", "DE", 10)]), pack())
    assert v.status is UNSURE
    assert "no product-specific rule encoded for HS 999999" in v.reasons[0]
    assert v.rule is None


def test_rule_without_alternatives_is_unsure_not_fail():
    v = evaluate(product("847150", [line("L1", "850440", "DE", 10)]), adhoc_pack([]))
    assert v.status is UNSURE


# --- tariff shift kinds -----------------------------------------------------------------------


@pytest.mark.parametrize(
    "kind, material_hs6, passed",
    [
        ("CC", "847330", False),  # same chapter 84
        ("CC", "850440", True),
        ("CTH", "847330", True),  # heading 8473 != 8471
        ("CTH", "847180", False),  # same heading 8471
        ("CTH", "850440", True),
        ("CTSH", "847180", True),  # subheading 847180 != 847150
        ("CTSH", "847150", False),
        ("CTSH", "847330", True),
    ],
)
def test_tariff_shift_kinds(kind, material_hs6, passed):
    v = evaluate(product("847150", [line("L1", material_hs6, "DE", 40)]), adhoc_pack([[crit(kind)]]))
    assert only_check(v).passed is passed
    assert v.status is (PASS if passed else FAIL)
    assert v.lines[0].shift_ok is passed
    if not passed:
        assert only_check(v).line_ids == ["L1"]


def test_shift_ignores_originating_materials_in_same_heading():
    bom = [line("L1", "847180", "CH", 60), line("L2", "847180", "CN", 30)]
    v = evaluate(product("847150", bom), adhoc_pack([[crit("CTH")]]))
    assert v.status is PASS
    assert all(la.shift_ok is True for la in v.lines)


@pytest.mark.parametrize(
    "material_hs6, passed",
    [
        ("911410", False),  # other heading, but excluded by 'except from 9114'
        ("911190", True),  # other heading, not excluded
        ("910119", False),  # same heading 9101
        ("850440", True),
    ],
)
def test_except_from(material_hs6, passed):
    v = evaluate(product("910111", [line("L1", material_hs6, "JP", 40)]), pack())
    assert v.rule.rule_id == "TEST-9101-CTH-EXCEPT-9114"
    assert only_check(v).passed is passed
    assert only_check(v).name == "CTH except from 9114"


def test_except_from_with_dotted_prefix():
    p = adhoc_pack([[crit("CTH", except_from=("91.14",))]], scope=("9101",))
    v = evaluate(product("910111", [line("L1", "911410", "JP", 40)]), p)
    assert only_check(v).passed is False
    assert "except from 9114" in only_check(v).detail


def test_except_from_material_absorbed_by_tolerance():
    v = evaluate(product("910111", [line("L1", "911410", "JP", 5)]), pack())
    assert v.status is PASS and v.tolerance_used


@pytest.mark.parametrize("kind", ["CC", "CTH", "CTSH"])
def test_non_originating_line_without_hs6_is_undecidable(kind):
    v = evaluate(product("847150", [line("L1", None, "DE", 40)]), adhoc_pack([[crit(kind)]]))
    assert only_check(v).passed is None
    assert only_check(v).line_ids == ["L1"]
    assert v.status is UNSURE
    assert v.lines[0].shift_ok is None


def test_originating_line_without_hs6_does_not_matter():
    v = evaluate(product("847150", [line("L1", None, "CH", 40)]), adhoc_pack([[crit("CTH")]]))
    assert v.status is PASS


# --- general tolerance ------------------------------------------------------------------------


@pytest.mark.parametrize(
    "values, ex_works, passed",
    [
        ([10.0], 100.0, True),  # exactly 10 % -> tolerance applies
        ([10.01], 100.0, False),  # 10.01 % -> fails
        ([9.99], 100.0, True),
        ([0.0], 100.0, True),
        ([123.45], 1234.5, True),  # exactly 10 % with awkward floats
        ([123.46], 1234.5, False),
        ([3.3, 3.3, 3.4], 100.0, True),  # sums to exactly 10.00 (float sum would not)
        ([3.3, 3.3, 3.41], 100.0, False),
        ([0.1, 0.2], 3.0, True),  # 0.3 of 3.0 = exactly 10 %
    ],
)
def test_tolerance_boundary(values, ex_works, passed):
    bom = [line(f"L{i}", "847180", "DE", v) for i, v in enumerate(values, start=1)]
    v = evaluate(product("847150", bom, ex_works=ex_works), adhoc_pack([[crit("CTH")]]))
    assert only_check(v).passed is passed
    assert v.tolerance_used is passed
    assert v.status is (PASS if passed else FAIL)
    if passed:
        assert "general tolerance" in only_check(v).detail
        assert only_check(v).line_ids == [f"L{i}" for i in range(1, len(values) + 1)]


@pytest.mark.parametrize(
    "violating, unknown, passed",
    [
        (5.0, 5.0, True),  # together exactly 10 % -> absorbed
        (5.0, 6.0, None),  # violating alone fits, the unknown line decides
        (11.0, 1.0, False),  # violating alone exceeds the tolerance
        (0.0, 11.0, None),
        (0.0, 10.0, True),
    ],
)
def test_tolerance_with_unclassified_lines(violating, unknown, passed):
    bom = [line("V", "847180", "DE", violating), line("U", None, "DE", unknown)]
    v = evaluate(product("847150", bom), adhoc_pack([[crit("CTH")]]))
    assert only_check(v).passed is passed


@pytest.mark.parametrize("kind", ["CC", "CTH", "CTSH"])
def test_tolerance_not_applied_when_kind_not_listed(kind):
    p = adhoc_pack([[crit(kind)]], tolerance_applies_to=[])
    v = evaluate(product("847150", [line("L1", "847150", "DE", 1.0)]), p)
    assert only_check(v).passed is False
    assert "does not apply" in only_check(v).detail
    assert v.tolerance_used is False


def test_tolerance_not_applied_to_unclassified_line_when_kind_not_listed():
    p = adhoc_pack([[crit("CTH")]], tolerance_applies_to=[])
    v = evaluate(product("847150", [line("L1", None, "DE", 1.0)]), p)
    assert only_check(v).passed is None


def test_tolerance_never_applies_to_maxnom_even_if_listed():
    p = adhoc_pack([[crit("MAXNOM", 50)]], tolerance_applies_to=[CriterionKind.MAXNOM])
    v = evaluate(product("847150", [line("L1", "850440", "DE", 55)]), p)
    assert only_check(v).passed is False
    assert v.tolerance_used is False


def test_tolerance_pct_is_read_from_pack():
    p = adhoc_pack([[crit("CTH")]], tolerance_pct=15.0)
    v = evaluate(product("847150", [line("L1", "847180", "DE", 15)]), p)
    assert v.status is PASS and v.tolerance_used


# --- MAXNOM -----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "nom, ex_works, status",
    [
        (50.0, 100.0, PASS),  # equal to the threshold passes
        (50.01, 100.0, FAIL),
        (49.99, 100.0, PASS),
        (0.0, 100.0, PASS),
        (1.5, 3.0, PASS),  # exactly 50 %
        (0.15, 0.3, PASS),  # exactly 50 %, float arithmetic would say 50.000000000000004 %
        (617.25, 1234.5, PASS),
        (617.26, 1234.5, FAIL),
    ],
)
def test_maxnom_boundary(nom, ex_works, status):
    v = evaluate(product("901890", [line("L1", "901890", "US", nom)], ex_works=ex_works), pack())
    assert v.rule.rule_id == "TEST-CH90-MAXNOM50"
    assert v.status is status
    assert v.threshold_pct == 50.0


def test_maxnom_counts_all_non_originating_lines():
    bom = [line("L1", "901890", "US", 20), line("L2", None, "JP", 20), line("L3", "850440", "DE", 15)]
    v = evaluate(product("901890", bom), pack())
    assert v.nom_value_chf == 55.0 and v.nom_pct == 55.0
    assert v.status is FAIL
    assert only_check(v).line_ids == ["L1", "L2", "L3"]


def test_maxnom_without_percentage_is_undecided():
    v = evaluate(product("847150", [line("L1", "850440", "DE", 10)]), adhoc_pack([[crit("MAXNOM")]]))
    assert only_check(v).passed is None
    assert v.status is UNSURE


# --- WO and SPECIFIC --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bom, status",
    [
        ([line("L1", "230990", "CH", 5)], PASS),
        ([line("L1", "230990", "CN", 5)], PASS),
        ([line("L1", "230990", "DE", 5)], FAIL),
        ([line("L1", "230990", "DE", 5, override=True)], PASS),
        ([], PASS),
    ],
)
def test_wholly_obtained(bom, status):
    v = evaluate(product("010121", bom), pack())
    assert v.rule.rule_id == "TEST-CH01-WO"
    assert v.status is status
    assert "rarely relevant for manufactured goods" in only_check(v).detail


def test_wo_uses_tolerance_only_when_pack_lists_it():
    bom = [line("L1", "230990", "DE", 5)]
    listed = adhoc_pack([[crit("WO")]], scope=("01",), tolerance_applies_to=[CriterionKind.WO])
    assert evaluate(product("010121", bom), listed).status is PASS
    assert evaluate(product("010121", bom), adhoc_pack([[crit("WO")]], scope=("01",))).status is FAIL


def test_specific_needs_human():
    v = evaluate(product("020130", [line("L1", "020130", "CH", 5)]), pack())
    assert only_check(v).passed is None
    assert "human judgement" in only_check(v).detail
    assert v.status is UNSURE


@pytest.mark.parametrize("nom, status", [(30.0, PASS), (60.0, UNSURE)])
def test_specific_or_maxnom(nom, status):
    v = evaluate(product("300490", [line("L1", "293390", "IN", nom)]), pack())
    assert [a.met for a in v.alternatives] == [None, status is PASS]
    assert v.status is status
    assert "synthetic specific process" in only_check(v).detail


# --- OR / AND combinations ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "material_hs6, value, mets, status",
    [
        ("440710", 35.0, [True, False], PASS),  # CC met; alt 2 fails on MAXNOM 30
        ("940190", 25.0, [False, True], PASS),  # CC fails (same chapter), CTH and MAXNOM 30 met
        ("940190", 35.0, [False, False], FAIL),  # CTH met but MAXNOM 30 fails
        ("940390", 25.0, [False, False], FAIL),  # same heading: CC and CTH both fail
        ("940390", 5.0, [True, True], PASS),  # within tolerance for both shifts
    ],
)
def test_or_of_ands(material_hs6, value, mets, status):
    v = evaluate(product("940360", [line("L1", material_hs6, "VN", value)]), pack())
    assert v.rule.rule_id == "TEST-9403-CC-OR-CTH-MAXNOM30"
    assert [a.met for a in v.alternatives] == mets
    assert v.status is status


@pytest.mark.parametrize(
    "bom, checks, status",
    [
        ([line("L1", "847180", "DE", 30)], [True, True], PASS),
        ([line("L1", "847180", "DE", 45)], [True, False], FAIL),
        ([line("L1", "847130", "DE", 30)], [False, True], FAIL),
        ([line("L1", "847130", "DE", 45)], [False, False], FAIL),
        ([line("L1", None, "DE", 30)], [None, True], UNSURE),
        ([line("L1", None, "DE", 45)], [None, False], FAIL),  # one AND-ed criterion failing is enough
    ],
)
def test_and_inside_alternative(bom, checks, status):
    v = evaluate(product("847130", bom), pack())
    assert v.rule.rule_id == "TEST-847130-CTSH-AND-MAXNOM40"
    assert [c.passed for c in v.alternatives[0].checks] == checks
    assert v.status is status


@pytest.mark.parametrize(
    "origin, nom, mets, status",
    [
        ("CN", 15.0, [True, True], PASS),
        ("SA", 0.0, [False, True], PASS),  # a zero-value non-originating material still breaks WO
        ("SA", 15.0, [False, True], PASS),
        ("SA", 25.0, [False, False], FAIL),
    ],
)
def test_wo_or_maxnom(origin, nom, mets, status):
    v = evaluate(product("392690", [line("L1", "390110", origin, nom), line("L2", "390110", "CH", 10)]), pack())
    assert [a.met for a in v.alternatives] == mets
    assert v.status is status


# --- cumulation and overrides -----------------------------------------------------------------


@pytest.mark.parametrize(
    "country, originating",
    [("CH", True), ("CN", True), ("cn", True), (" ch ", True), ("DE", False), ("US", False), ("HK", False)],
)
def test_bilateral_cumulation(country, originating):
    v = evaluate(product("901890", [line("L1", "901890", country, 60)]), pack())
    assert v.lines[0].originating is originating
    assert v.status is (PASS if originating else FAIL)
    assert v.nom_value_chf == (0.0 if originating else 60.0)
    if originating:
        assert "supplier provides proof of origin" in v.lines[0].reason


def test_cumulation_parties_come_from_pack():
    p = pack()
    p.general.cumulation_parties = ["CH"]
    v = evaluate(product("901890", [line("L1", "901890", "CN", 60)]), p)
    assert v.lines[0].originating is False
    assert v.status is FAIL


@pytest.mark.parametrize(
    "country, override, originating",
    [
        ("DE", True, True),
        ("CH", False, False),
        ("CN", False, False),
        ("DE", None, False),
        ("CH", None, True),
    ],
)
def test_originating_override(country, override, originating):
    v = evaluate(product("901890", [line("L1", "901890", country, 60, override=override)]), pack())
    assert v.lines[0].originating is originating
    assert v.status is (PASS if originating else FAIL)
    if override is not None:
        assert "override" in v.lines[0].reason


# --- verdict fields ---------------------------------------------------------------------------


def test_nom_pct_rounded_for_display_only():
    v = evaluate(product("901890", [line("L1", "901890", "US", 100)], ex_works=300), pack())
    assert v.nom_pct == 33.33
    assert v.margin_pct == 16.67
    assert v.nom_value_chf == 100.0


@pytest.mark.parametrize(
    "hs6, bom, threshold, margin",
    [
        ("847150", [line("L1", "847330", "DE", 63)], 50.0, -13.0),  # PASS via CTH, MAXNOM alt still reported
        ("847130", [line("L1", "847180", "DE", 30)], 40.0, 10.0),
        ("850440", [line("L1", "760429", "DE", 30)], None, None),  # CC only: no MAXNOM
        ("940360", [line("L1", "440710", "DE", 20)], 30.0, 10.0),
    ],
)
def test_threshold_and_margin(hs6, bom, threshold, margin):
    v = evaluate(product(hs6, bom), pack())
    assert v.threshold_pct == threshold
    assert v.margin_pct == margin


def test_threshold_uses_closest_alternative_with_maxnom():
    p = adhoc_pack([[crit("CTH"), crit("MAXNOM", 30)], [crit("MAXNOM", 60)]])
    v = evaluate(product("847150", [line("L1", "847180", "DE", 40)]), p)
    assert [a.met for a in v.alternatives] == [False, True]
    assert v.threshold_pct == 60.0 and v.margin_pct == 20.0


def test_tolerance_flag_prefers_alternative_met_without_tolerance():
    bom = [line("L1", "847180", "DE", 8)]
    v = evaluate(product("847150", bom), pack())  # CTH via tolerance OR MAXNOM 50 met outright
    assert [a.met for a in v.alternatives] == [True, True]
    assert v.tolerance_used is False
    only_cth = evaluate(product("847150", bom), adhoc_pack([[crit("CTH")]]))
    assert only_cth.tolerance_used is True
    assert any("General tolerance used" in r for r in only_cth.reasons)


def test_shift_ok_flags():
    bom = [
        line("O", "847180", "CH", 5),
        line("OK", "850440", "DE", 5),
        line("BAD", "847180", "DE", 5),
        line("UNK", None, "DE", 5),
    ]
    v = evaluate(product("847150", bom), adhoc_pack([[crit("CTH")]]))
    assert {la.line_id: la.shift_ok for la in v.lines} == {"O": True, "OK": True, "BAD": False, "UNK": None}


def test_shift_ok_none_when_rule_has_no_tariff_shift():
    v = evaluate(product("901890", [line("L1", "901890", "US", 10)]), pack())
    assert v.lines[0].shift_ok is None


def test_line_hs6_is_normalised_in_output():
    v = evaluate(product("847150", [line("L1", "8504.40", "DE", 5)]), pack())
    assert v.lines[0].hs6 == "850440"
    assert v.lines[0].shift_ok is True


def test_verdict_does_not_alias_pack():
    p = pack()
    v = evaluate(product("847150", [line("L1", "850440", "DE", 5)]), p)
    v.rule.alternatives[0][0].except_from.append("9999")
    assert find_criterion(p).except_from == []


def find_criterion(p):
    rule = next(r for r in p.rules if r.rule_id == "TEST-8471-CTH-OR-MAXNOM50")
    return rule.alternatives[0][0]


def test_empty_bom():
    v = evaluate(product("847150", []), pack())
    assert v.status is PASS
    assert v.nom_value_chf == 0.0 and v.nom_pct == 0.0
