"""PRC import duty lookup for the duty-saving estimate (data/tariffs/cn_import_tariffs.json).

Rates are only as good as the file: every entry carries its source and a `verified` flag, and an
unverified source is labelled as such in the estimate. A missing rate stays None; nothing is guessed.
The committed file holds the rates of the official 2014 schedule (GACC Announcement 2014 No. 53, in force
from 1 July 2014); each entry's source says so, and the estimate passes it on verbatim.
"""

from __future__ import annotations

import json
import re
import unicodedata
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from pydantic import BaseModel

from .config import get_settings
from .models import DutyEstimate

TARIFF_FILE = Path("tariffs") / "cn_import_tariffs.json"
_HS6 = re.compile(r"^[0-9]{6}$")
_CENT = Decimal("0.01")


class TariffEntry(BaseModel):
    description: str
    mfn_rate_pct: float | None
    fta_rate_pct: float | None
    source: str
    verified: bool


class TariffFile(BaseModel):
    source_note: str
    entries: dict[str, TariffEntry]


def load_tariffs(data_dir: Path | None = None) -> dict[str, dict]:
    """HS6 -> entry dict from the tariff file; {} if the file is absent. Raises ValueError on a malformed file."""
    path = (data_dir or get_settings().data_dir) / TARIFF_FILE
    if not path.exists():
        return {}
    parsed = TariffFile.model_validate(json.loads(path.read_text(encoding="utf-8")))
    bad = [code for code in parsed.entries if not _HS6.match(code)]
    if bad:
        raise ValueError(f"{path}: entry keys must be 6-digit HS codes, got {bad}")
    return {code: entry.model_dump() for code, entry in parsed.entries.items()}


def estimate_duty(hs6: str, order_value_chf: float, tariffs: dict) -> DutyEstimate | None:
    """Duty estimate for one order; None if the code is not in the table or neither rate is known.

    duty_saved_chf = order value x (MFN - FTA) / 100, only when both rates are known.
    """
    # NFKC like the engine (rulepack.loader.normalise_hs): full-width input from a Chinese IME ("８４１３．７０").
    code = re.sub(r"[\s.]", "", unicodedata.normalize("NFKC", hs6 or ""))
    entry = tariffs.get(code) if _HS6.match(code) else None
    if entry is None:
        return None
    mfn, fta = entry.get("mfn_rate_pct"), entry.get("fta_rate_pct")
    if mfn is None and fta is None:
        return None
    saved = None
    if mfn is not None and fta is not None:
        amount = Decimal(str(order_value_chf)) * (Decimal(str(mfn)) - Decimal(str(fta))) / 100
        saved = float(amount.quantize(_CENT, ROUND_HALF_UP))
    source = entry["source"] if entry.get("verified") else f"UNVERIFIED: {entry['source']}"
    return DutyEstimate(
        hs6=code,
        mfn_rate_pct=mfn,
        fta_rate_pct=fta,
        order_value_chf=order_value_chf,
        duty_saved_chf=saved,
        source=source,
    )
