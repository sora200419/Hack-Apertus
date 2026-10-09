"""Origin engine: general checks (insufficient processing, direct transport), reasons trace, verification flag."""

from __future__ import annotations

import pytest
from engine_builders import line, pack, product

from originpass.engine import evaluate
from originpass.engine.general import matched_keyword, normalise_text
from originpass.engine.origin import UNVERIFIED
from originpass.models import VerdictStatus

PASS, FAIL, UNSURE = VerdictStatus.PASS, VerdictStatus.FAIL, VerdictStatus.UNSURE
GOOD_BOM = [line("L1", "850440", "DE", 10)]  # meets every alternative of TEST-8471-CTH-OR-MAXNOM50


def general(verdict, name):
    return next(c for c in verdict.general_checks if c.name == name)


@pytest.mark.parametrize(
    "processing, passed, status",
    [
        ((), None, UNSURE),
        (("   ",), None, UNSURE),
        (("packing",), False, FAIL),
        (("Packing", "LABELLING"), False, FAIL),
        (("re-packing into boxes",), False, FAIL),  # 'packing' as a whole word
        (("washing; sorting",), False, FAIL),
        (("simple assembly of two parts",), False, FAIL),
        (("packing", "CNC milling of the housing"), True, PASS),
        (("unpacking and inspection",), True, PASS),  # 'packing' only inside another word
        (("assembly of 40 components with reflow soldering",), True, PASS),
        (("final assembly and testing",), True, PASS),
    ],
)
def test_insufficient_processing(processing, passed, status):
    v = evaluate(product("847150", GOOD_BOM, processing=processing), pack())
    assert general(v, "insufficient processing").passed is passed
    assert v.status is status


def test_missing_processing_asks_for_description():
    v = evaluate(product("847150", GOOD_BOM, processing=()), pack())
    assert general(v, "insufficient processing").detail == "describe the processing done in Switzerland"
    cn = evaluate(product("847150", GOOD_BOM, processing=(), exporter="CN"), pack())
    assert "processing done in China" in general(cn, "insufficient processing").detail


def test_insufficient_processing_fails_even_when_rule_is_met():
    v = evaluate(product("847150", GOOD_BOM, processing=("packing", "labelling")), pack())
    assert all(a.met for a in v.alternatives)
    assert v.status is FAIL
    assert len(v.fixes) == 1 and "re-sourcing materials cannot confer origin" in v.fixes[0]
    assert v.reasons[-1].startswith("Verdict FAIL: general check(s) failed: insufficient processing")


def test_insufficient_operations_come_from_pack():
    p = pack()
    p.general.insufficient_operations = ["milling"]
    v = evaluate(product("847150", GOOD_BOM, processing=("CNC milling",)), p)
    assert general(v, "insufficient processing").passed is False


@pytest.mark.parametrize(
    "text, normalised",
    [("Re-Packing,  labels", "re packing labels"), ("ÉTIQUETAGE", "étiquetage"), ("a_b", "a b")],
)
def test_normalise_text(text, normalised):
    assert normalise_text(text) == normalised


@pytest.mark.parametrize(
    "operation, keyword",
    [("Packing in boxes", "packing"), ("unpacking", None), ("simple  ASSEMBLY", "simple assembly"), ("", None)],
)
def test_matched_keyword(operation, keyword):
    assert matched_keyword(operation, ["packing", "simple assembly", "  "]) == keyword


@pytest.mark.parametrize(
    "transit, storage, passed, status",
    [
        ((), False, True, PASS),
        (("SG",), False, None, UNSURE),
        (("sg", "SG", "DE"), False, None, UNSURE),
        (("",), False, True, PASS),
        ((), True, None, UNSURE),  # transshipment declared without a country
        (("AE",), True, None, UNSURE),
    ],
)
def test_direct_transport(transit, storage, passed, status):
    v = evaluate(product("847150", GOOD_BOM, transit=transit, storage=storage), pack())
    check = general(v, "direct transport")
    assert check.passed is passed
    assert v.status is status
    if passed is None:
        assert "non-manipulation evidence" in check.detail
        assert v.fixes == []  # the rule is met; only evidence is missing


def test_transit_countries_deduplicated_in_detail():
    v = evaluate(product("847150", GOOD_BOM, transit=("sg", "SG", "DE")), pack())
    assert "through SG, DE" in general(v, "direct transport").detail


def test_transit_does_not_rescue_a_failing_rule():
    v = evaluate(product("847150", [line("L1", "847180", "DE", 60)], transit=("SG",)), pack())
    assert v.status is FAIL


# --- reasons and verification -------------------------------------------------------------------


def test_reasons_are_ordered_trace():
    v = evaluate(product("847150", GOOD_BOM), pack())
    r = v.reasons
    assert r[0].startswith("Rule TEST-8471-CTH-OR-MAXNOM50 applies to HS 847150")
    assert r[1].startswith("Materials: 1 of 1 BOM line(s) are non-originating")
    idx = {
        key: next(i for i, s in enumerate(r) if s.startswith(key))
        for key in (
            "Alternative 1 (CTH)",
            "Alternative 2 (MAXNOM 50%)",
            "General check 'insufficient processing'",
            "General check 'direct transport'",
            UNVERIFIED,
            "Verdict PASS",
        )
    }
    assert list(idx.values()) == sorted(idx.values())
    assert idx["Verdict PASS"] == len(r) - 1


@pytest.mark.parametrize(
    "pack_id, hs6, verified, parts",
    [
        ("test-verified", "847150", True, None),
        ("test-verified", "850440", False, "product-specific rule TEST-V-CH85-CTH"),
        ("test-basic", "847130", False, "general provisions"),  # rule verified, general not
        ("test-basic", "847150", False, "product-specific rule TEST-8471-CTH-OR-MAXNOM50 and general provisions"),
    ],
)
def test_rule_verified_flag(pack_id, hs6, verified, parts):
    v = evaluate(product(hs6, [line("L1", "760429", "DE", 10)]), pack(pack_id))
    assert v.rule_verified is verified
    unverified = [r for r in v.reasons if r.startswith(UNVERIFIED)]
    if verified:
        assert unverified == []
    else:
        assert len(unverified) == 1 and parts in unverified[0]


def test_verification_does_not_change_status():
    bom = [line("L1", "847180", "DE", 40)]
    verified = evaluate(product("847150", bom), pack("test-verified"))
    p = pack("test-verified")
    p.rules[0].verified = False
    p.general.verified = False
    unverified = evaluate(product("847150", bom), p)
    assert verified.status is unverified.status is FAIL
    assert verified.rule_verified and not unverified.rule_verified
