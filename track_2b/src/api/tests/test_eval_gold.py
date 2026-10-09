"""E1 gold set: schema, codes exist in HS 2022, frozen splits, language mix, parallel concepts, provenance."""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parents[2]  # local checkout: src/ holds the `eval` package
if (_SRC / "eval" / "__init__.py").exists() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from originpass.config import get_settings  # noqa: E402

from eval.gold import GOLD_FILE, LANGS, check_rows, hs2022_codes, load_gold, split_for  # noqa: E402

DATA_DIR = get_settings().data_dir


@pytest.fixture(scope="module")
def rows() -> list[dict]:
    text = (DATA_DIR / GOLD_FILE).read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def test_gold_file_is_valid(rows: list[dict]) -> None:
    assert check_rows(rows, hs2022_codes(DATA_DIR)) == []
    assert len(load_gold(DATA_DIR)) == len(rows)


def test_splits_are_frozen() -> None:
    # Pinned: changing the salt or the dev share would silently reshuffle dev and test.
    pinned = {"bom-de-002": "test", "bom-en-002": "dev", "bom-fr-001": "dev", "hcc-0001": "dev", "P01": "test"}
    assert {key: split_for(key) for key in pinned} == pinned


def test_hand_labelled_language_mix(rows: list[dict]) -> None:
    main = [r for r in rows if r["subset"] == "main"]
    assert len(main) >= 150
    share = {lang: n / len(main) for lang, n in Counter(r["lang"] for r in main).items()}
    for lang, want in {"en": 0.45, "de": 0.30, "fr": 0.15, "it": 0.10}.items():
        assert abs(share[lang] - want) <= 0.03, (lang, share[lang])
    assert {r["split"] for r in main} == {"dev", "test"}
    assert 0.2 <= sum(r["split"] == "dev" for r in main) / len(main) <= 0.4


def test_parallel_concepts(rows: list[dict]) -> None:
    concepts: dict[str, list[dict]] = {}
    for r in rows:
        if r["subset"] == "parallel":
            concepts.setdefault(r["concept"], []).append(r)
    assert len(concepts) == 30
    for group in concepts.values():
        assert sorted(r["lang"] for r in group) == sorted(LANGS)
        assert len({r["split"] for r in group}) == 1  # translations never straddle dev/test


def test_provenance(rows: list[dict]) -> None:
    external = [r for r in rows if r["subset"] == "hscodecomp"]
    assert external and all(
        r["licence"] == "Apache-2.0" and r["ref"].startswith("test_data.jsonl task_id=") for r in external
    )
    assert len(json.dumps(external).encode()) < 1_000_000
    assert all(r["source"] == "hand-labelled from HS 2022 nomenclature" for r in rows if r["subset"] != "hscodecomp")
    assert (DATA_DIR / "eval" / "LICENSE-HSCodeComp.txt").exists()
    assert "Apache" in (DATA_DIR / "eval" / "README.md").read_text(encoding="utf-8")
