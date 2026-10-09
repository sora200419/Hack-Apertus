"""Adversarial tests: rule-pack faithfulness to the raw Annex II text, HS 2022 codes, engine edge cases.

Every test that pins a fixed bug says so in its docstring ("Bug: ...").
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from functools import cache
from pathlib import Path

import pytest
from engine_builders import adhoc_pack, crit, line, pack, product

from originpass.config import get_settings
from originpass.engine import apply_changes, evaluate
from originpass.models import CriterionKind, Product, RulePack, VerdictStatus
from originpass.rulepack.build_ch_cn import build, read_correlation
from originpass.rulepack.loader import find_rule

PASS, FAIL, UNSURE = VerdictStatus.PASS, VerdictStatus.FAIL, VerdictStatus.UNSURE
DATA_DIR = get_settings().data_dir
RAW_ANNEX = DATA_DIR / "raw" / "annex2_psr_zh_gacc_2014_51.txt"
CORRELATION = DATA_DIR / "raw" / "hs2022_hs2012_correlation_unsd.csv"
needs_raw = pytest.mark.skipif(not RAW_ANNEX.exists() or not CORRELATION.exists(), reason="raw sources absent")


@cache
def real_pack() -> RulePack:
    return build(DATA_DIR)[0]


def fresh_real_pack() -> RulePack:
    return real_pack().model_copy(deep=True)


# --- 1. the builder parsed every Annex II entry faithfully ------------------------------------------
#
# Independent reading of the raw text: the Word-table export ends every cell with \x07 and every row
# is five cells (code, description, column 3, column 4, row end). Nothing from build_ch_cn is reused.

_CN_UNITS = {numeral: n for n, numeral in enumerate("一二三四五六七八九", start=1)}
_SHIFT_WORDS = {"章改变": CriterionKind.CC, "品目改变": CriterionKind.CTH, "子目改变": CriterionKind.CTSH}


def _chapter_number(numeral: str) -> int:
    tens, ten, units = numeral.partition("十")
    if not ten:
        return _CN_UNITS[numeral]
    return _CN_UNITS.get(tens, 1) * 10 + _CN_UNITS.get(units, 0)


def _code_to_prefix(cell: str) -> tuple[str, bool]:
    ex = cell.startswith("ex")
    body = cell.removeprefix("ex").strip()
    if body.startswith("第") and body.endswith("章"):
        return f"{_chapter_number(body[1:-1]):02d}", ex
    digits = body.replace(".", "")
    assert re.fullmatch(r"\d{4}|\d{6}", digits), cell
    return digits, ex


@cache
def raw_rows() -> tuple[tuple[str, str, bool, tuple[str, ...]], ...]:
    """(code cell, HS prefix, is_ex, alternative texts) for every row of the Annex II table."""
    text = RAW_ANNEX.read_text(encoding="utf-8")
    cells = [c.replace("\x0c", "").strip() for c in text[text.index("第三节") :].split("\x07")]
    first = next(i for i, c in enumerate(cells) if c.startswith("(3)")) + 2  # skip the column-number header row
    rows = []
    for i in range(first, len(cells) - 4, 5):
        code, _description, col3, col4, row_end = cells[i : i + 5]
        assert row_end == "", f"row {code!r} does not have five cells"
        alternatives = [a.strip("；; \n") for a in re.split(r"\n\s*或者\s*\n", col3) if a.strip()]
        if col4:
            alternatives.append(col4)
        prefix, ex = _code_to_prefix(code)
        rows.append((code, prefix, ex, tuple(alternatives)))
    assert cells[first + 5 * len(rows) :] in ([""], ["", ""]), "unparsed cells after the last row"
    return tuple(rows)


@cache
def annex_rule_by_prefix() -> dict[str, list]:
    by_prefix: dict[str, list] = {}
    for rule in real_pack().rules:
        for scope in rule.hs_scope:
            by_prefix.setdefault(scope, []).append(rule)
    return by_prefix


@needs_raw
def test_raw_table_has_one_row_per_entry_and_all_chapters():
    rows = raw_rows()
    assert len(rows) == 206
    assert {p for _, p, _, _ in rows if len(p) == 2} == {f"{n:02d}" for n in range(1, 98)}
    assert len({p for _, p, _, _ in rows}) == len(rows)  # no code appears twice


@needs_raw
def test_every_code_cell_maps_to_exactly_one_rule():
    by_prefix = annex_rule_by_prefix()
    for code, prefix, ex, _ in raw_rows():
        rules = by_prefix.get(prefix, [])
        assert len(rules) == 1, f"{code}: {len(rules)} rules"
        rule = rules[0]
        assert rule.hs_scope[0] == prefix and f"entry '{code}'" in rule.source
        assert rule.text.endswith("listed separately)") is ex, code
    annex_rules = [r for r in real_pack().rules if "Annex II product-specific rules" in r.source]
    assert len(annex_rules) == len(raw_rows())


@needs_raw
def test_no_code_like_line_is_left_out_of_the_table():
    """Loose line scan: every line of the list section that looks like an HS code is a code cell."""
    text = RAW_ANNEX.read_text(encoding="utf-8")
    table = text[text.index("第三节") :].replace("\x07", "\n").replace("\x0c", "\n")
    looks_like_code = re.compile(r"^(ex)?\s*(第[一二三四五六七八九十]+章|\d{2}\.\d{2}(\.\d{2})?|\d{4}\.\d{2})\s*$")
    found = [ln.strip() for ln in table.split("\n") if looks_like_code.match(ln.strip())]
    assert found == [code for code, _, _, _ in raw_rows()]


@needs_raw
def test_alternatives_and_criteria_match_the_raw_cells():
    by_prefix = annex_rule_by_prefix()
    for code, prefix, _, raw_alts in raw_rows():
        rule = by_prefix[prefix][0]
        if not raw_alts:  # chapter 77 is reserved
            assert [[c.kind for c in a] for a in rule.alternatives] == [[CriterionKind.SPECIFIC]], code
            continue
        alternatives = rule.alternatives
        if 27 <= int(prefix[:2]) <= 40:  # Section II routes, one extra SPECIFIC alternative
            *alternatives, section_ii = alternatives
            assert [c.kind for c in section_ii] == [CriterionKind.SPECIFIC], code
            assert section_ii[0].note.startswith("Annex II Section II"), code
        assert len(alternatives) == len(raw_alts), code  # column 3 OR column 4 (OR '或者' inside a cell)
        for raw, alt in zip(raw_alts, alternatives, strict=True):
            kinds = [c.kind for c in alt]
            raw_pcts = sorted(float(p) for p in re.findall(r"非原产材料价值(\d+)[%％]", raw))
            assert sorted(c.max_nom_pct for c in alt if c.kind is CriterionKind.MAXNOM) == raw_pcts, (code, raw)
            shifts = [kind for word, kind in _SHIFT_WORDS.items() if raw.startswith(word)]
            assert [k for k in kinds if k in _SHIFT_WORDS.values()] == shifts, (code, raw)
            if "且" in raw:  # '且' joins criteria with AND inside one alternative
                assert len(alt) >= 2, (code, raw)
            if raw == "完全获得":
                assert kinds == [CriterionKind.WO], code
            excluded = re.search(r"从(.+)改变至此除外", raw)
            if shifts and excluded:
                body = excluded.group(1)
                if body.startswith("第"):
                    expected = [f"{_chapter_number(n):02d}" for n in re.findall(r"第([一二三四五六七八九十]+)章", body)]
                else:
                    expected = [c.replace(".", "") for c in re.findall(r"\d{2}\.?\d{2}(?:\.\d{2})?", body)]
                assert alt[0].except_from == expected, (code, raw)
            if not shifts and not raw_pcts and raw != "完全获得":
                assert kinds == [CriterionKind.SPECIFIC], (code, raw)
            if CriterionKind.SPECIFIC in kinds:
                assert any(c.note for c in alt if c.kind is CriterionKind.SPECIFIC), code


@needs_raw
def test_every_vnm_percentage_in_the_raw_text_is_in_its_rule():
    """Flat line scan: each '非原产材料价值N%' belongs to the rule of the code line above it."""
    text = RAW_ANNEX.read_text(encoding="utf-8")
    lines = [ln.strip() for ln in re.split(r"[\x07\x0c\n]", text[text.index("第三节") :])]
    codes = iter([(code, prefix) for code, prefix, _, _ in raw_rows()])
    upcoming = next(codes)
    found: dict[str, list[float]] = {}
    current = None
    for ln in lines:
        if upcoming and ln == upcoming[0]:
            current, upcoming = upcoming[1], next(codes, None)
            found[current] = []
            continue
        pcts = [float(p) for p in re.findall(r"非原产材料价值(\d+)[%％]", ln)]
        assert current or not pcts
        if pcts:
            found[current] += pcts
    assert upcoming is None and len(found) == 206
    assert sum(map(len, found.values())) > 100
    for prefix, pcts in found.items():
        rule = annex_rule_by_prefix()[prefix][0]
        assert sorted(pcts) == sorted(c.max_nom_pct for a in rule.alternatives for c in a if c.max_nom_pct), prefix


@needs_raw
def test_rule_semantics_of_the_real_pack_against_the_fta_text():
    """Art. 3.5(2): no tolerance for value criteria; Art. 3.7: bilateral CH/CN accumulation; target chapters."""
    p = real_pack()
    assert p.general.tolerance_pct == 10.0
    assert not {CriterionKind.MAXNOM, CriterionKind.SPECIFIC} & set(p.general.tolerance_applies_to)
    assert p.general.cumulation_parties == ["CH", "CN"]
    for hs6, pct in [("847989", 50), ("854370", 50), ("901890", 55), ("910221", 40)]:
        assert [[(c.kind, c.max_nom_pct) for c in a] for a in find_rule(p, hs6).alternatives] == [
            [(CriterionKind.MAXNOM, float(pct))]
        ]


# --- 2. real pack: 'ex' entries, OR of columns 3/4, AND ('且'), HS 2022 codes -----------------------


@needs_raw
@pytest.mark.parametrize(
    "hs6, rule_id",
    [
        ("021020", "CHCN-021020"),
        ("021011", "CHCN-02"),
        ("030111", "CHCN-0301"),
        ("030489", "CHCN-03"),
        ("281511", "CHCN-281511"),
        ("281520", "CHCN-28"),
        ("848180", "CHCN-84"),
        ("852990", "CHCN-85"),
    ],
)
def test_more_specific_entry_overrides_the_ex_chapter(hs6, rule_id):
    assert find_rule(real_pack(), hs6).rule_id == rule_id


@needs_raw
@pytest.mark.parametrize(
    "material, value, status",
    [
        ("940390", 55.0, PASS),  # CTH broken (same heading 9403) but column 4 'VNM 60%' is met
        ("940390", 61.0, FAIL),  # both columns fail
        ("440710", 61.0, PASS),  # column 3 'CTH' is met even above 60 %
    ],
)
def test_column_3_or_column_4(material, value, status):
    v = evaluate(product("940360", [line("L1", material, "VN", value)]), fresh_real_pack())
    assert v.rule.rule_id == "CHCN-94" and v.status is status


@needs_raw
@pytest.mark.parametrize(
    "material, value, status",
    [
        ("020130", 50.0, PASS),  # CTH met, VNM decides
        ("020130", 50.01, FAIL),
        ("021011", 9.0, PASS),  # same heading 0210: CTH met only within the 10 % tolerance
        ("021011", 11.0, FAIL),
    ],
)
def test_qie_is_and(material, value, status):
    """0210.20 '品目改变且非原产材料价值50%': CTH AND VNM 50 %."""
    v = evaluate(product("021020", [line("L1", material, "AR", value)]), fresh_real_pack())
    assert v.rule.rule_id == "CHCN-021020" and v.status is status


@needs_raw
@pytest.mark.parametrize(
    "hs6, material, nom, status",
    [
        ("392690", "392690", 56.0, UNSURE),  # CTH and VNM 55 % fail; a Section II route may still apply
        ("392690", "392690", 55.0, PASS),
        ("847989", "847989", 51.0, FAIL),  # outside chapters 27-40 nothing changes
    ],
)
def test_section_ii_routes_for_chapters_27_to_40(hs6, material, nom, status):
    """Bug: Annex II Section II (fermentation = WO; chemical reaction, purification, ... where the change of
    tariff classification cannot be applied) was not encoded, so chapter 27-40 products could get a hard FAIL."""
    v = evaluate(product(hs6, [line("L1", material, "US", nom)]), fresh_real_pack())
    assert v.status is status
    if status is UNSURE:
        assert any("Annex II Section II" in r for r in v.reasons)


@needs_raw
@pytest.mark.parametrize(
    "hs6, rule_id, nom, status",
    [
        ("811261", "CHCN-810730", 30.0, FAIL),  # cadmium waste: entry 8107.30 'WO', prefix gave 'CTH or VNM 60%'
        ("810931", "CHCN-810930", 30.0, FAIL),  # zirconium waste: entry 8109.30 'WO'
        ("382211", "CHCN-30", 55.0, PASS),  # diagnostic reagents, HS 2012 3002.10: 'VNM 60%'
        ("240412", "CHCN-HS2022-240412", 55.0, PASS),  # HS 2012 3824.90: VNM 60 % column decides alone
        ("240412", "CHCN-HS2022-240412", 65.0, UNSURE),  # CTH must be judged on HS 2012 codes
        ("852411", "CHCN-HS2022-852411", 45.0, PASS),  # display modules: <= 50 % meets every candidate entry
        ("852411", "CHCN-HS2022-852411", 70.0, UNSURE),  # chapter 95 'CTH' could still apply
        ("880621", "CHCN-HS2022-880621", 55.0, UNSURE),  # drones: CHCN-85 (50 %) or CHCN-88 (60 %)
        ("880621", "CHCN-HS2022-880621", 61.0, FAIL),  # above every candidate's limit
    ],
)
def test_hs2022_code_uses_the_entry_of_its_hs2012_predecessors(hs6, rule_id, nom, status):
    """Bug: HS 2022 subheadings that did not exist in HS 2012 were matched by prefix only, e.g. 811261
    cadmium waste got 'ex chapter 81: CTH or VNM 60%' (PASS at 30 %) instead of entry 8107.30 'WO'."""
    bom = [line("L1", "999999", "US", nom), line("L2", "999999", "CH", 100.0 - nom)]
    v = evaluate(product(hs6, bom), fresh_real_pack())
    assert v.rule.rule_id == rule_id
    assert v.status is status
    assert "correlation" in v.reasons[0]


@needs_raw
def test_every_hs2022_only_code_resolves_to_its_predecessors_entry():
    """Independent check over all HS 2022 subheadings that are not HS 2012 subheadings."""
    p = real_pack()
    correlation = read_correlation(CORRELATION)
    annex = p.model_copy(
        update={
            "rules": [
                r.model_copy(update={"hs_scope": r.hs_scope[:1]})
                for r in p.rules
                if not r.rule_id.startswith("CHCN-HS2022-")
            ]
        }
    )
    hs2012 = set().union(*correlation.values())
    new_codes = sorted(set(correlation) - hs2012)
    assert len(new_codes) > 500
    for code in new_codes:
        candidates = {find_rule(annex, old).rule_id for old in correlation[code]}
        resolved = find_rule(p, code).rule_id
        if candidates == {find_rule(annex, code).rule_id}:
            assert resolved == find_rule(annex, code).rule_id, code
        elif resolved.startswith("CHCN-HS2022-"):
            assert all(c in find_rule(p, code).text for c in candidates), code
        else:  # joined the single candidate entry, which has no tariff shift to re-judge in HS 2012 terms
            assert candidates == {resolved}, code
            assert not any(c.kind in _SHIFT_WORDS.values() for a in find_rule(p, code).alternatives for c in a)
    scopes = [s for r in p.rules for s in r.hs_scope]
    assert len(scopes) == len(set(scopes))  # no code is claimed by two rules


@needs_raw
@pytest.mark.parametrize("hs6", ["848180", "841370", "910221", "902610", "901890", "847130", "852990"])
def test_codes_that_existed_in_hs2012_keep_their_prefix_rule(hs6):
    rule = find_rule(real_pack(), hs6)
    assert rule.rule_id == f"CHCN-{hs6[:2]}" and len(rule.hs_scope) == 1


@needs_raw
def test_all_originating_bom_never_fails_any_real_rule():
    """With no non-originating material every criterion but SPECIFIC is met (Art. 3.2(c) route)."""
    p = real_pack()
    bom = [line("L1", "999999", "CH", 40.0), line("L2", None, "CN", 30.0)]
    for rule in p.rules:
        hs6 = rule.hs_scope[0].ljust(6, "0")
        if find_rule(p, hs6) is not rule:
            continue
        v = evaluate(product(hs6, bom), p)
        has_plain_alt = any(all(c.kind is not CriterionKind.SPECIFIC for c in a) for a in rule.alternatives)
        assert v.status is (PASS if has_plain_alt else UNSURE), rule.rule_id
        assert v.nom_pct == 0.0 and v.fixes == []


# --- 3. engine edge cases (synthetic fixture packs) ---------------------------------------------


@pytest.mark.parametrize(
    "nom, ex_works, status, margin",
    [
        (50000.4, 100000.0, FAIL, -0.01),  # 50.0004 %: displayed nom_pct 50.0 must not come with margin -0.0
        (500.004, 1000.0, FAIL, -0.01),
        (49999.6, 100000.0, PASS, 0.0),
        (50.0, 100.0, PASS, 0.0),
        (617.25, 1234.5, PASS, 0.0),
    ],
)
def test_margin_sign_matches_the_limit_at_float_boundaries(nom, ex_works, status, margin):
    """Bug: a share a hair above the threshold showed nom_pct == threshold and margin_pct -0.0 on a FAIL."""
    v = evaluate(product("901890", [line("L1", "901890", "US", nom)], ex_works=ex_works), pack())
    assert v.status is status
    assert v.margin_pct == margin and str(v.margin_pct) != "-0.0"
    assert (v.margin_pct < 0) is (status is FAIL)


def test_over_the_limit_amount_never_rounds_to_zero():
    """Bug: 'over the limit by CHF 0.00' for a sub-cent excess; the excess is now rounded up."""
    v = evaluate(product("901890", [line("L1", "901890", "US", 500.004)], ex_works=1000.0), pack())
    assert "over the limit by CHF 0.01" in v.alternatives[0].checks[0].detail


@pytest.mark.parametrize(
    "bom, ex_works, status",
    [
        ([line("A", "901890", "US", 0.1), line("B", "901890", "US", 0.2)], 0.6, PASS),  # 0.1 + 0.2 == 0.3 exactly
        ([line("A", "901890", "US", 5e11)], 1e12, PASS),
        ([line("A", "901890", "US", 5e11 + 0.01)], 1e12, FAIL),
        ([line("A", "901890", "US", 1e-9)], 2e-9, PASS),
    ],
)
def test_maxnom_exact_at_extreme_magnitudes(bom, ex_works, status):
    assert evaluate(product("901890", bom, ex_works=ex_works), pack()).status is status


@pytest.mark.parametrize("value, ex_works", [("1e400", "100"), ("10", "1e400"), ("Infinity", "100")])
def test_non_finite_amount_is_a_clear_value_error(value, ex_works):
    """Bug: JSON 1e400 or Infinity parses to inf (the models allow it); the engine crashed with
    decimal.InvalidOperation. It now raises a ValueError that names the problem."""
    data = product("901890", [line("L1", "901890", "US", 1)]).model_dump()
    data["ex_works_chf"], data["bom"][0]["value_chf"] = "EX", "VAL"
    raw = json.dumps(data).replace('"EX"', ex_works).replace('"VAL"', value)
    with pytest.raises(ValueError, match="finite"):
        evaluate(Product.model_validate_json(raw), pack())


@pytest.mark.parametrize("hs6, status", [("901890", PASS), ("847150", PASS), ("020130", UNSURE), ("010121", PASS)])
def test_empty_bom(hs6, status):
    """Art. 3.2(c): no non-originating material; SPECIFIC still needs a human."""
    v = evaluate(product(hs6, []), pack())
    assert v.status is status and v.lines == [] and v.fixes == [] and v.nom_pct == 0.0


def test_duplicate_line_ids_are_rejected():
    """Bug: duplicated line ids were silently accepted, so 're-source line L1' could mean either line."""
    with pytest.raises(ValueError, match="duplicate BOM line_id"):
        product("901890", [line("L1", "901890", "US", 30), line("L1", "901890", "US", 30)])
    unique = evaluate(product("901890", [line("L1", "901890", "US", 30), line("L2", "901890", "US", 30)]), pack())
    assert unique.nom_value_chf == 60.0


@pytest.mark.parametrize("hs6", ["990100", "000000", "989900"])
def test_product_outside_every_rule_is_unsure(hs6):
    v = evaluate(product(hs6, [line("L1", "901890", "US", 10)]), pack())
    assert v.status is UNSURE and v.rule is None and v.alternatives == []


@needs_raw
def test_reserved_chapter_77_is_unsure():
    v = evaluate(product("770000", [line("L1", "760110", "US", 10)]), fresh_real_pack())
    assert v.rule.rule_id == "CHCN-77" and v.status is UNSURE


@pytest.mark.parametrize(
    "nom, mets, status, threshold",
    [
        (45.0, [True, True, True], PASS, 50.0),
        (55.0, [False, True, False], PASS, 60.0),  # threshold of the met alternative
        (65.0, [False, False, False], FAIL, 60.0),  # closest failing alternative
    ],
)
def test_multiple_maxnom_alternatives(nom, mets, status, threshold):
    p = adhoc_pack([[crit("MAXNOM", 50)], [crit("MAXNOM", 60)], [crit("MAXNOM", 70), crit("MAXNOM", 50)]])
    v = evaluate(product("847150", [line("L1", "847150", "US", nom)]), p)
    assert [a.met for a in v.alternatives] == mets and v.status is status
    assert v.threshold_pct == threshold


@pytest.mark.parametrize(
    "material, passed",
    [
        ("720851", False),  # excluded by chapter prefix '72'
        ("730890", False),  # excluded by heading prefix '7308'
        ("731815", False),  # excluded by subheading '7318.15' (dotted in the pack)
        ("731816", True),  # same heading 7318 as an excluded subheading, but not excluded itself
        ("732620", False),  # same heading 7326 as the product
        ("850440", True),
    ],
)
def test_except_from_with_mixed_prefix_lengths(material, passed):
    p = adhoc_pack([[crit("CTH", except_from=("72", "7308", "7318.15"))]], scope=("73",))
    v = evaluate(product("732690", [line("L1", material, "DE", 40)]), p)
    assert v.alternatives[0].checks[0].passed is passed


@pytest.mark.parametrize(
    "bom, passed, tolerance_used",
    [
        ([line("U", None, "DE", 10)], True, True),  # unknown line absorbed by the 10 % tolerance
        ([line("U", None, "DE", 10.01)], None, False),  # unknown and above: undecided, not failed
        ([line("V", "847180", "DE", 4), line("U", None, "DE", 6)], True, True),
        ([line("V", "847180", "DE", 4), line("U", None, "DE", 6.01)], None, False),
        ([line("V", "847180", "DE", 10.01), line("U", None, "DE", 1)], False, False),
    ],
)
def test_tolerance_and_lines_without_hs6(bom, passed, tolerance_used):
    v = evaluate(product("847150", bom), adhoc_pack([[crit("CTH")]]))
    assert v.alternatives[0].checks[0].passed is passed
    assert v.tolerance_used is tolerance_used


@pytest.mark.parametrize(
    "kind, material, passed",
    [
        ("CTH", "847150", False),
        ("CTH", "847130", False),
        ("CTSH", "847130", True),
        ("CTSH", "847150", False),
        ("CC", "850440", True),
        ("CC", "840999", False),
    ],
)
def test_material_in_the_products_own_heading(kind, material, passed):
    v = evaluate(product("847150", [line("L1", material, "DE", 40)]), adhoc_pack([[crit(kind)]]))
    assert v.alternatives[0].checks[0].passed is passed


def test_fix_when_no_single_line_closes_the_gap_flips_to_pass():
    bom = [
        line("A", "901890", "US", 9),
        line("B", "901890", "US", 8),
        line("C", "901890", "US", 2),
        line("D", "901890", "US", 41),
    ]
    p = product("901890", bom)
    v = evaluate(p, adhoc_pack([[crit("MAXNOM", 10)]], scope=("90",)))
    assert v.status is FAIL
    assert "no single line is enough, so re-source lines D (CHF 41.00) and A (CHF 9.00)" in v.fixes[0]
    fixed = apply_changes(p, [{"line_id": i, "origin_country": "CH"} for i in ("D", "A")])
    assert evaluate(fixed, adhoc_pack([[crit("MAXNOM", 10)]], scope=("90",))).status is PASS


def test_reasons_are_deterministic_and_follow_bom_order():
    bom = [line("B", "847180", "DE", 30), line("A", None, "JP", 15), line("C", "850440", "CH", 5)]
    p = adhoc_pack([[crit("CTH")], [crit("MAXNOM", 40)], [crit("CC"), crit("MAXNOM", 50)]])
    first = evaluate(product("847150", bom), p)
    assert all(evaluate(product("847150", bom), p) == first for _ in range(3))
    flipped = evaluate(product("847150", bom[::-1]), p)
    assert (flipped.status, flipped.nom_pct, [a.met for a in flipped.alternatives]) == (
        first.status,
        first.nom_pct,
        [a.met for a in first.alternatives],
    )
    assert first.reasons.index(next(r for r in first.reasons if "Alternative 2" in r)) < first.reasons.index(
        next(r for r in first.reasons if "Alternative 3" in r)
    )


@needs_raw
def test_build_is_independent_of_hash_seed():
    """The builder iterates sets (HS 2022 correlation); its output must not depend on PYTHONHASHSEED."""
    script = (
        "import json, sys; from pathlib import Path; from originpass.rulepack.build_ch_cn import build; "
        "p, n = build(Path(sys.argv[1])); print(json.dumps([p.model_dump(mode='json'), n], sort_keys=False))"
    )
    outputs = []
    for seed in ("1", "2"):
        env = {**os.environ, "PYTHONHASHSEED": seed}
        run = subprocess.run(
            [sys.executable, "-c", script, str(DATA_DIR)],
            capture_output=True,
            text=True,
            env=env,
            cwd=Path(__file__).resolve().parents[1],
            check=True,
        )
        outputs.append(json.loads(run.stdout))
    assert outputs[0] == outputs[1]


# --- 4. general checks: Art. 3.6 screening and Art. 3.13 --------------------------------------------


@pytest.mark.parametrize(
    "processing, passed, status",
    [
        (("CNC machining, assembly, testing and packing",), None, UNSURE),  # was FAIL: one keyword in a list
        (("washing & surface grinding",), None, UNSURE),
        (("packing and labelling",), False, FAIL),
        (("packing of 1,5 mm sheets",), False, FAIL),  # a decimal comma is not a clause boundary
        (("simple assembly; packing",), False, FAIL),
        (("packing", "CNC machining"), True, PASS),
        (("CNC machining and packing", "TIG welding of the frame"), True, PASS),
    ],
)
def test_operations_mixing_keywords_with_other_work(processing, passed, status):
    """Bug: any keyword inside an operation made the whole operation insufficient, so a one-line
    description 'CNC machining, assembly, testing and packing' gave FAIL ('re-sourcing cannot help')."""
    v = evaluate(product("847150", [line("L1", "850440", "DE", 10)], processing=processing), pack())
    assert v.general_checks[0].passed is passed and v.status is status
    if passed is None:
        assert "list each operation separately" in v.general_checks[0].detail


@needs_raw
@pytest.mark.parametrize(
    "operation, passed",
    [
        ("simple assembly of two parts", False),
        ("einfache Montage", False),
        ("assembly of 40 components", True),
        ("Verpacken und Etikettieren", False),
        ("emballage et étiquetage", False),
        ("precision grinding", True),
    ],
)
def test_simple_qualifier_from_the_real_keywords(operation, passed):
    """Art. 3.6(1)(o)/(j): only *simple* assembly or grinding is listed; plain assembly is not screened out."""
    v = evaluate(product("847150", [line("L1", "850440", "DE", 10)], processing=(operation,)), fresh_real_pack())
    assert v.general_checks[0].passed is passed


def test_exporter_equal_to_destination_is_not_direct_transport():
    """Bug: exporter CH shipping to destination CH was reported as 'shipped directly', verdict PASS."""
    p = product("847150", [line("L1", "850440", "DE", 10)])
    p.shipment.destination = "CH"
    v = evaluate(p, pack())
    assert v.general_checks[1].passed is None and v.status is UNSURE
    assert "both CH" in v.general_checks[1].detail
    cn = product("847150", [line("L1", "850440", "DE", 10)], exporter="CN")
    cn.shipment.destination = "CH"
    assert evaluate(cn, pack()).status is PASS


@pytest.mark.parametrize(
    "product_hs6, material_hs6, origin, passed",
    [
        ("847150", "８４７１８０", "DE", False),  # full-width digits, same heading 8471: must break the CTH
        ("８４７１．５０", "850440", "DE", True),  # full-width product code with a full-width dot
        ("847150", "٨٤٧١٨٠", "DE", None),  # other Unicode digits are not an HS code: unclassified, not 'other heading'
        ("847150", "847180", "ＣＮ", True),  # full-width party code still counts as originating
    ],
)
def test_full_width_input_from_a_chinese_ime(product_hs6, material_hs6, origin, passed):
    """Bug: '\\d' accepted full-width digits, so material '８４７１８０' looked like another heading than 8471
    and the CTH passed (false PASS); a full-width product code found no rule."""
    v = evaluate(product(product_hs6, [line("L1", material_hs6, origin, 40)]), adhoc_pack([[crit("CTH")]]))
    assert v.hs6 == "847150"
    assert v.alternatives[0].checks[0].passed is passed
