"""Rule pack loader: loading, validation, most-specific rule lookup, stats (synthetic fixture packs)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from engine_builders import FIXTURES_DIR, line, pack, product
from pydantic import ValidationError

from originpass.config import get_settings
from originpass.engine import evaluate
from originpass.models import RulePack, VerdictStatus
from originpass.rulepack import (
    RulePackError,
    find_rule,
    load_rulepack,
    matching_prefix,
    normalise_hs,
    rulepack_stats,
    validate_rulepack,
)


def test_load_fixture_pack():
    p = load_rulepack("test-basic", data_dir=FIXTURES_DIR)
    assert isinstance(p, RulePack)
    assert p.pack_id == "test-basic"
    assert len(p.rules) == 14
    assert all(r.rule_id.startswith("TEST-") for r in p.rules)
    assert validate_rulepack(p) == []


def test_default_data_dir_comes_from_settings(monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(FIXTURES_DIR))
    assert load_rulepack("test-verified").pack_id == "test-verified"


def test_data_dir_accepts_str():
    assert load_rulepack("test-verified", data_dir=str(FIXTURES_DIR)).pack_id == "test-verified"


@pytest.mark.parametrize("pack_id", ["../rulepacks/test-basic", "a/b", "", "Test-Basic", ".hidden", "x\\y"])
def test_invalid_pack_id_rejected(pack_id):
    with pytest.raises(RulePackError, match="invalid rule pack id"):
        load_rulepack(pack_id, data_dir=FIXTURES_DIR)


def test_missing_pack_raises_file_not_found():
    with pytest.raises(FileNotFoundError):
        load_rulepack("does-not-exist", data_dir=FIXTURES_DIR)


def test_pack_id_must_match_file_name():
    with pytest.raises(RulePackError, match="declares pack_id 'something-else'"):
        load_rulepack("test-wrong-id", data_dir=FIXTURES_DIR)


def test_schema_error_raises_validation_error(tmp_path: Path):
    (tmp_path / "rulepacks").mkdir()
    (tmp_path / "rulepacks" / "broken.json").write_text(json.dumps({"pack_id": "broken"}))
    with pytest.raises(ValidationError):
        load_rulepack("broken", data_dir=tmp_path)


def test_invalid_pack_fails_to_load():
    with pytest.raises(RulePackError):
        load_rulepack("test-invalid", data_dir=FIXTURES_DIR)


def _invalid_problems() -> list[str]:
    raw = (FIXTURES_DIR / "rulepacks" / "test-invalid.json").read_text()
    return validate_rulepack(RulePack.model_validate_json(raw))


@pytest.mark.parametrize(
    "expected",
    [
        "tolerance_applies_to must not contain ['MAXNOM']",
        "cumulation_parties must be ISO alpha-2",
        "rule 'TEST-BAD-1': duplicate rule_id",
        "hs_scope '84.71' is not a 2, 4 or 6 digit HS prefix",
        "hs_scope '847' is not a 2, 4 or 6 digit HS prefix",
        "alternative 1 MAXNOM: max_nom_pct must be between 0 and 100",
        "except_from is only allowed on CC/CTH/CTSH",
        "rule 'TEST-BAD-3': empty hs_scope",
        "rule 'TEST-BAD-3': no alternatives",
        "rule 'TEST-BAD-4': alternative 1 has no criteria",
        "max_nom_pct is only allowed on MAXNOM",
        "except_from '91x' is not a 2-6 digit HS prefix",
    ],
)
def test_validate_reports_problem(expected):
    problems = _invalid_problems()
    assert any(expected in p for p in problems), problems


@pytest.mark.parametrize(
    "hs6, rule_id",
    [
        ("847150", "TEST-8471-CTH-OR-MAXNOM50"),  # 4-digit scope beats 2-digit
        ("847130", "TEST-847130-CTSH-AND-MAXNOM40"),  # 6-digit scope beats 4 and 2
        ("847330", "TEST-CH84-CTH"),  # only the chapter scope matches
        ("850440", "TEST-CH85-CC"),
        ("910111", "TEST-9101-CTH-EXCEPT-9114"),
        ("910211", "TEST-9101-CTH-EXCEPT-9114"),  # second scope of the same rule
        ("730820", "TEST-7308-FIRST"),  # tie on identical scope -> first rule
        ("850110", "TEST-8501-CTSH"),
        ("8471.30", "TEST-847130-CTSH-AND-MAXNOM40"),  # dotted notation is normalised
        (" 847130 ", "TEST-847130-CTSH-AND-MAXNOM40"),
        ("999999", None),
        ("", None),
    ],
)
def test_find_rule_most_specific(hs6, rule_id):
    rule = find_rule(pack(), hs6)
    assert (rule.rule_id if rule else None) == rule_id


def test_find_rule_specificity_independent_of_order():
    p = pack()
    p.rules.reverse()
    assert find_rule(p, "847130").rule_id == "TEST-847130-CTSH-AND-MAXNOM40"
    assert find_rule(p, "847150").rule_id == "TEST-8471-CTH-OR-MAXNOM50"
    # with the order reversed, the other 7308 rule is now first and wins the tie
    assert find_rule(p, "730820").rule_id == "TEST-7308-SECOND"


@pytest.mark.parametrize("hs6, prefix", [("910211", "9102"), ("910111", "9101"), ("847150", None)])
def test_matching_prefix(hs6, prefix):
    rule = next(r for r in pack().rules if r.rule_id == "TEST-9101-CTH-EXCEPT-9114")
    assert matching_prefix(rule, hs6) == prefix


@pytest.mark.parametrize(
    "raw, norm", [("8471.30", "847130"), (" 84 71 30 ", "847130"), (None, ""), ("847130", "847130")]
)
def test_normalise_hs(raw, norm):
    assert normalise_hs(raw) == norm


def test_rulepack_stats():
    assert rulepack_stats(pack()) == {"rules": 14, "verified_rules": 1}
    assert rulepack_stats(pack("test-verified")) == {"rules": 2, "verified_rules": 1}


# --- the real CH-CN pack, produced by another workstream --------------------------------------

REAL_PACK = get_settings().data_dir / "rulepacks" / "ch-cn-2014.json"


@pytest.mark.skipif(not REAL_PACK.exists(), reason="data/rulepacks/ch-cn-2014.json not produced yet")
def test_real_pack_loads_and_validates():
    p = load_rulepack("ch-cn-2014", data_dir=REAL_PACK.parent.parent)
    assert p.pack_id == "ch-cn-2014"
    assert p.rules, "pack has no rules"
    assert validate_rulepack(p) == []
    stats = rulepack_stats(p)
    assert 0 <= stats["verified_rules"] <= stats["rules"] == len(p.rules)
    for rule in p.rules:
        assert rule.text.strip() and rule.source.strip(), rule.rule_id


@pytest.mark.skipif(not REAL_PACK.exists(), reason="data/rulepacks/ch-cn-2014.json not produced yet")
def test_engine_runs_on_every_real_rule():
    p = load_rulepack("ch-cn-2014", data_dir=REAL_PACK.parent.parent)
    bom = [line("L1", "999999", "US", 30.0), line("L2", None, "DE", 5.0), line("L3", "391990", "CN", 10.0)]
    for rule in p.rules:
        for scope in rule.hs_scope:
            hs6 = scope.ljust(6, "0")
            verdict = evaluate(product(hs6, bom), p)
            assert verdict.status in set(VerdictStatus)
            assert verdict.rule is not None
            verdict.model_dump_json()
