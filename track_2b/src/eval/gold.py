"""E1 gold set: BOM-style descriptions with gold HS 2022 subheadings (data/eval/hs_gold.jsonl).

Three subsets, one JSON object per line:
- "main": hand-labelled BOM lines and finished goods (EN/DE/FR/IT), labels assigned by the author from
  the HS 2022 nomenclature text in data/hs/hs2022.csv;
- "parallel": 30 concepts, each written in EN, DE, FR and IT (cross-lingual consistency);
- "hscodecomp": English e-commerce product titles from HSCodeComp (AIDC-AI, Apache-2.0), chapters of
  interest only, gold = first 6 digits of the expert-assigned US HTS code.

The split is frozen by construction: `split_for` hashes the row id (the concept id for parallel rows, so
that all translations of one concept land in the same split) with a fixed salt; about 30 % go to 'dev'.
Adding rows never moves existing rows. The CLI re-imports the HSCodeComp subset or checks the file:

    python -m eval.gold --check
    python -m eval.gold --import-hscodecomp <clone>/Marco-DeepResearch-Family/HSCodeComp/data/test_data.jsonl
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

GOLD_FILE = Path("eval") / "hs_gold.jsonl"
SPLIT_SALT = "originpass-e1-v1"
DEV_SHARE = 0.30
LANGS = ("en", "de", "fr", "it")
SUBSETS = ("main", "parallel", "hscodecomp")
HSCODECOMP_CHAPTERS = ("84", "85", "90", "91", "39", "40", "73", "76", "74", "70")
HSCODECOMP_SOURCE = "HSCodeComp (AIDC-AI, github.com/AIDC-AI/Marco-Search-Agent, commit 2be90e4)"
HAND_SOURCE = "hand-labelled from HS 2022 nomenclature"
REQUIRED_FIELDS = ("id", "text", "lang", "gold_hs6", "source", "licence", "subset", "split")


@dataclass(frozen=True)
class GoldItem:
    id: str
    text: str
    lang: str
    gold_hs6: str
    source: str
    licence: str
    subset: str
    split: str
    concept: str | None = None
    note: str | None = None
    ref: str | None = None


def split_for(key: str) -> str:
    """'dev' for about DEV_SHARE of keys, else 'test'; a pure function of the key (frozen split)."""
    digest = hashlib.sha256(f"{SPLIT_SALT}:{key}".encode()).digest()
    return "dev" if int.from_bytes(digest[:8], "big") / 2**64 < DEV_SHARE else "test"


def split_key(row: dict) -> str:
    return row.get("concept") or row["id"]


def load_gold(data_dir: Path) -> list[GoldItem]:
    with (data_dir / GOLD_FILE).open(encoding="utf-8") as f:
        return [GoldItem(**json.loads(line)) for line in f if line.strip()]


def hs2022_codes(data_dir: Path) -> set[str]:
    """6-digit HS 2022 subheadings in data/hs/hs2022.csv (UN Comtrade 'TOTAL' aggregates excluded)."""
    with (data_dir / "hs" / "hs2022.csv").open(encoding="utf-8-sig", newline="") as f:
        return {r["hscode"] for r in csv.DictReader(f) if r["level"] == "6" and r["section"] != "TOTAL"}


def check_rows(rows: list[dict], codes: set[str]) -> list[str]:
    """Problems with the gold rows (empty list = valid)."""
    problems = []
    ids = Counter(r.get("id") for r in rows)
    problems += [f"duplicate id {i}" for i, n in ids.items() if n > 1]
    for r in rows:
        rid = r.get("id")
        missing = [f for f in REQUIRED_FIELDS if not r.get(f)]
        if missing:
            problems.append(f"{rid}: missing {missing}")
            continue
        if r["gold_hs6"] not in codes:
            problems.append(f"{rid}: gold {r['gold_hs6']} is not an HS 2022 subheading")
        if r["lang"] not in LANGS:
            problems.append(f"{rid}: unknown lang {r['lang']}")
        if r["subset"] not in SUBSETS:
            problems.append(f"{rid}: unknown subset {r['subset']}")
        if r["split"] != split_for(split_key(r)):
            problems.append(f"{rid}: split {r['split']} differs from the frozen split")
        if r["subset"] == "parallel" and not r.get("concept"):
            problems.append(f"{rid}: parallel row without concept")
    concepts: dict[str, list[dict]] = {}
    for r in rows:
        if r.get("subset") == "parallel" and r.get("concept"):
            concepts.setdefault(r["concept"], []).append(r)
    for concept, group in concepts.items():
        if sorted(r["lang"] for r in group) != sorted(LANGS):
            problems.append(f"{concept}: languages {sorted(r['lang'] for r in group)}, want {sorted(LANGS)}")
        if len({r["gold_hs6"] for r in group}) != 1:
            problems.append(f"{concept}: translations carry different gold codes")
    return problems


def import_hscodecomp(path: Path, chapters: tuple[str, ...] = HSCODECOMP_CHAPTERS) -> list[dict]:
    """Gold rows from HSCodeComp test_data.jsonl: product title as text, HTS10[:6] as gold, chapter filter."""
    rows = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            item = json.loads(line)
            hts10 = f"{int(item['hs_code']):010d}"
            if not hts10.startswith(chapters):
                continue
            row = {
                "id": f"hcc-{int(item['task_id']):04d}",
                "text": " ".join(item["product_name"].split()),
                "lang": "en",
                "gold_hs6": hts10[:6],
                "source": HSCODECOMP_SOURCE,
                "licence": "Apache-2.0",
                "subset": "hscodecomp",
                "ref": f"test_data.jsonl task_id={item['task_id']}, US HTS {hts10}",
            }
            rows.append(row | {"split": split_for(row["id"])})
    return rows


def write_rows(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--import-hscodecomp", type=Path, help="path to HSCodeComp data/test_data.jsonl")
    parser.add_argument("--check", action="store_true", help="validate the gold file")
    args = parser.parse_args()

    from originpass.config import get_settings

    data_dir = get_settings().data_dir
    path = data_dir / GOLD_FILE
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if args.import_hscodecomp:
        rows = [r for r in rows if r["subset"] != "hscodecomp"] + import_hscodecomp(args.import_hscodecomp)
        write_rows(path, rows)
    problems = check_rows(rows, hs2022_codes(data_dir))
    counts = Counter((r["subset"], r["lang"], r["split"]) for r in rows)
    print(json.dumps({"rows": len(rows), "counts": {"/".join(k): n for k, n in sorted(counts.items())}}, indent=1))
    if problems:
        raise SystemExit("\n".join(problems))


if __name__ == "__main__":
    main()
