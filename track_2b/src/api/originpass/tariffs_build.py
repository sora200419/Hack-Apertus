"""Build data/tariffs/cn_import_tariffs.json from the official 2014 CH-CN FTA tariff schedule.

Source: GACC Announcement 2014 No. 53, Annex 1 "《中国-瑞士自由贸易协定》2014年协定税率表"
(8-digit PRC national lines with the 2014 MFN rate and the Switzerland conventional rate),
extracted to data/raw/cn_tariff_ch_fta_2014_gacc_53.tsv.

Per HS6 subheading: if all national lines share the same rates they are used as is; otherwise the
line with the SMALLEST MFN-FTA margin is used, so the duty saving shown is a lower bound, and the
other lines are listed in the source text. These are the rates at entry into force (1 July 2014):
the FTA phase-down and later MFN cuts make current rates lower, which the source text states.

Usage:  python -m originpass.tariffs_build [--data-dir DIR]
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from .config import get_settings

RAW_FILE = Path("raw") / "cn_tariff_ch_fta_2014_gacc_53.tsv"
OUT_FILE = Path("tariffs") / "cn_import_tariffs.json"
SOURCE = "GACC Announcement 2014 No. 53, Annex 1 (official CH-CN FTA tariff schedule, rates at 1 July 2014)"


def _rate(raw: str) -> float | None:
    return None if raw in ("NaN", "-", "") else float(raw)


def build(data_dir: Path) -> dict:
    lines_by_hs6: dict[str, list[dict]] = {}
    with (data_dir / RAW_FILE).open(encoding="utf-8") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            mfn, fta = _rate(row["mfn_2014_pct"]), _rate(row["fta_ch_2014_pct"])
            if mfn is None or fta is None:
                continue
            lines_by_hs6.setdefault(row["hs8"][:6], []).append(
                {"hs8": row["hs8"], "name": row["name_zh"], "mfn": mfn, "fta": fta}
            )

    entries = {}
    for hs6, lines in sorted(lines_by_hs6.items()):
        chosen = min(lines, key=lambda ln: (ln["mfn"] - ln["fta"], ln["hs8"]))
        uniform = all((ln["mfn"], ln["fta"]) == (chosen["mfn"], chosen["fta"]) for ln in lines)
        detail = f"national line {chosen['hs8']}"
        if not uniform:
            others = "; ".join(f"{ln['hs8']} {ln['mfn']:g}%/{ln['fta']:g}%" for ln in lines if ln is not chosen)
            detail += f" (lowest saving of {len(lines)} lines under {hs6}; others MFN/FTA: {others})"
        entries[hs6] = {
            "description": chosen["name"],
            "mfn_rate_pct": chosen["mfn"],
            "fta_rate_pct": chosen["fta"],
            "source": f"{SOURCE}, {detail}. Current 2026 rates may be lower.",
            "verified": True,
        }
    return {
        "source_note": f"{SOURCE}. Taken verbatim from the official schedule; per HS6 the national line with the "
        "smallest MFN-FTA margin is used (duty saving = lower bound). Rates are those at entry into force; "
        "check the current PRC tariff before quoting a saving to a customer.",
        "entries": entries,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--data-dir", type=Path, default=get_settings().data_dir)
    args = ap.parse_args()
    table = build(args.data_dir)
    out = args.data_dir / OUT_FILE
    out.write_text(json.dumps(table, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {out}: {len(table['entries'])} HS6 entries")


if __name__ == "__main__":
    main()
