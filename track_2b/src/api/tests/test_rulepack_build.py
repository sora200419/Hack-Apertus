"""Builder for the ch-cn-2014 pack: parser units + the committed pack matches a fresh build."""

import json
from pathlib import Path

import pytest

from originpass.models import CriterionKind
from originpass.rulepack.build_ch_cn import PACK_ID, build, cn_to_int, parse_code, parse_criterion
from originpass.rulepack.loader import find_rule, validate_rulepack

DATA_DIR = Path(__file__).resolve().parents[3] / "data"
needs_raw = pytest.mark.skipif(not (DATA_DIR / "raw" / "chapter3_provisions.json").exists(), reason="raw sources absent")


@pytest.mark.parametrize("cn,n", [("一", 1), ("十", 10), ("十二", 12), ("二十", 20), ("八十四", 84), ("九十七", 97)])
def test_cn_to_int(cn, n):
    assert cn_to_int(cn) == n


@pytest.mark.parametrize(
    "line,expected",
    [("第八十四章", ("84", False)), ("ex 第二章", ("02", True)), ("ex第七十四章", ("74", True)),
     ("03.01", ("0301", False)), ("0210.20", ("021020", False)), ("活动物", None)],
)
def test_parse_code(line, expected):
    assert parse_code(line) == expected


def kinds(crits):
    return [(c.kind, c.max_nom_pct, c.except_from) for c in crits]


@pytest.mark.parametrize(
    "line,expected,en",
    [
        ("完全获得", [(CriterionKind.WO, None, [])], "WO"),
        ("品目改变", [(CriterionKind.CTH, None, [])], "CTH"),
        ("非原产材料价值50％", [(CriterionKind.MAXNOM, 50.0, [])], "VNM 50%"),
        ("非原产材料价值60%", [(CriterionKind.MAXNOM, 60.0, [])], "VNM 60%"),
        ("品目改变且非原产材料价值50%", [(CriterionKind.CTH, None, []), (CriterionKind.MAXNOM, 50.0, [])], "CTH and VNM 50%"),
        ("章改变，从第四章、第十一章改变至此除外", [(CriterionKind.CC, None, ["04", "11"])], "CC (except from chapter 04, 11)"),
        ("品目改变，从品目5106、5107 或5108改变至此除外", [(CriterionKind.CTH, None, ["5106", "5107", "5108"])], None),
        ("品目改变，从品目52.05 或5206改变至此除外", [(CriterionKind.CTH, None, ["5205", "5206"])], None),
        ("子目改变，从子目2815.12改变至此除外", [(CriterionKind.CTSH, None, ["281512"])], None),
        ("品目改变，从品目7108或7110改变至此除外；", [(CriterionKind.CTH, None, ["7108", "7110"])], None),
    ],
)
def test_parse_criterion(line, expected, en):
    crits, rendered = parse_criterion(line)
    assert kinds(crits) == expected
    if en:
        assert rendered == en


@pytest.mark.parametrize(
    "line", ["非原产材料价值30%，限从生咖啡豆制造，包括焙炒工序", "成套货品里的每项产品都必须满足它不作为成套货品时所适用的规则", "产品应在一方发现"]
)
def test_unmappable_text_becomes_specific(line):
    crits, _ = parse_criterion(line)
    assert any(c.kind is CriterionKind.SPECIFIC for c in crits)


@needs_raw
def test_fresh_build_is_valid_and_complete():
    pack, notes = build(DATA_DIR)
    assert validate_rulepack(pack) == []
    chapters = {r.hs_scope[0] for r in pack.rules if len(r.hs_scope[0]) == 2}
    assert chapters == {f"{n:02d}" for n in range(1, 98)}
    assert all(r.text_zh and r.source for r in pack.rules)
    assert len(notes) < 25


@needs_raw
@pytest.mark.parametrize("hs6,pct", [("841370", 50), ("848180", 50), ("850152", 50), ("901890", 55), ("902610", 55), ("910211", 40), ("911410", 40)])
def test_target_chapters_are_single_vnm_rules(hs6, pct):
    pack, _ = build(DATA_DIR)
    rule = find_rule(pack, hs6)
    assert [[(c.kind, c.max_nom_pct) for c in alt] for alt in rule.alternatives] == [[(CriterionKind.MAXNOM, float(pct))]]
    assert f"非原产材料价值{pct}" in rule.text_zh


@needs_raw
def test_committed_pack_matches_fresh_build():
    committed = DATA_DIR / "rulepacks" / f"{PACK_ID}.json"
    if not committed.exists():
        pytest.skip("pack not built")
    pack, _ = build(DATA_DIR)
    assert json.loads(committed.read_text(encoding="utf-8")) == pack.model_dump(mode="json")
