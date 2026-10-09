"""Tariff table: schema of the committed file and duty-saving arithmetic."""

from __future__ import annotations

import json

import pytest

from originpass.config import get_settings
from originpass.tariffs import estimate_duty, load_tariffs


def entry(mfn: float | None, fta: float | None, verified: bool = True) -> dict:
    return {"description": "x", "mfn_rate_pct": mfn, "fta_rate_pct": fta, "source": "src", "verified": verified}


def test_estimate_duty_arithmetic():
    tariffs = {"841370": entry(8.0, 2.5)}
    duty = estimate_duty("8413.70", 12500.0, tariffs)
    assert duty is not None
    assert (duty.hs6, duty.mfn_rate_pct, duty.fta_rate_pct) == ("841370", 8.0, 2.5)
    assert duty.duty_saved_chf == 687.5  # 12500 x (8 - 2.5) / 100
    assert duty.order_value_chf == 12500.0 and duty.source == "src"


def test_estimate_duty_rounds_to_cents():
    assert estimate_duty("910211", 333.33, {"910211": entry(10.0, 0.0)}).duty_saved_chf == 33.33


def test_estimate_duty_none_when_unknown():
    tariffs = {"841370": entry(None, None), "848180": entry(7.0, None, verified=False)}
    assert estimate_duty("999999", 1000.0, tariffs) is None
    assert estimate_duty("8413", 1000.0, tariffs) is None
    assert estimate_duty("841370", 1000.0, tariffs) is None
    partial = estimate_duty("848180", 1000.0, tariffs)
    assert partial is not None and partial.duty_saved_chf is None
    assert partial.source.startswith("UNVERIFIED")


def test_committed_tariff_file_schema():
    path = get_settings().data_dir / "tariffs" / "cn_import_tariffs.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert set(raw) == {"source_note", "entries"} and raw["source_note"]
    tariffs = load_tariffs(get_settings().data_dir)
    assert tariffs and set(tariffs) == set(raw["entries"])
    for code, e in tariffs.items():
        assert len(code) == 6 and code.isdigit()
        assert set(e) == {"description", "mfn_rate_pct", "fta_rate_pct", "source", "verified"}
        assert e["source"]
        # Nothing has been checked against the official schedule yet: no entry may claim otherwise.
        assert e["verified"] is False


def test_load_tariffs_missing_and_malformed(tmp_path):
    assert load_tariffs(tmp_path) == {}
    (tmp_path / "tariffs").mkdir()
    path = tmp_path / "tariffs" / "cn_import_tariffs.json"
    path.write_text(json.dumps({"source_note": "s", "entries": {"8413": entry(1.0, 0.0)}}), encoding="utf-8")
    with pytest.raises(ValueError, match="6-digit"):
        load_tariffs(tmp_path)
    path.write_text(json.dumps({"source_note": "s", "entries": {"841370": {"mfn_rate_pct": 1.0}}}), encoding="utf-8")
    with pytest.raises(ValueError):
        load_tariffs(tmp_path)
