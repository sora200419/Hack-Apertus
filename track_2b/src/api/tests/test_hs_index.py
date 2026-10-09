"""HS 2022 retrieval index: loading, known queries, describe/valid, filters, tokenisation."""

from __future__ import annotations

import time

import pytest

from originpass.hs.index import HSIndex, get_index, tokenize


@pytest.fixture(scope="module")
def index() -> HSIndex:
    return get_index()


def test_load_builds_fast_and_skips_aggregates() -> None:
    t0 = time.perf_counter()
    idx = HSIndex.load()
    elapsed = time.perf_counter() - t0
    # Target is < 3 s (about 1.3 s on a laptop CPU); the slack keeps a busy CI box from flaking.
    assert elapsed < 5.0
    assert len(idx) == 5612  # 5613 six-digit rows minus the Comtrade aggregate 999999
    assert not idx.valid("999999")


def test_get_index_is_a_singleton() -> None:
    assert get_index() is get_index()


@pytest.mark.parametrize(
    ("query", "prefix"),
    [
        ("centrifugal pump for liquids", "841370"),
        ("wrist watch automatic stainless steel case", "9102"),
        ("electric motor DC 100 W", "8501"),
        ("syringe", "9018"),
    ],
)
def test_known_queries_rank_expected_codes_in_top10(index: HSIndex, query: str, prefix: str) -> None:
    codes = [c.hs6 for c in index.search(query, k=10)]
    assert any(code.startswith(prefix) for code in codes), codes


def test_search_returns_sorted_fused_candidates(index: HSIndex) -> None:
    cands = index.search("centrifugal pump for liquids", k=5)
    assert len(cands) == 5
    assert cands[0].hs6 == "841370"
    assert all(c.source == "fused" for c in cands)
    assert [c.score for c in cands] == sorted((c.score for c in cands), reverse=True)
    assert cands[0].description == "Pumps; centrifugal, n.e.c. in heading no. 8413, for liquids"


def test_search_is_deterministic(index: HSIndex) -> None:
    assert index.search("ball bearing", k=10) == index.search("ball bearing", k=10)


def test_chapter_filter(index: HSIndex) -> None:
    assert all(c.hs6.startswith("84") for c in index.search("pump", k=10, chapters=["84"]))
    assert all(c.hs6.startswith("9018") for c in index.search("needle", k=5, chapters=["9018"]))


def test_fuse_dedupes_texts_and_counts_lists(index: HSIndex) -> None:
    fusion = index.fuse(["ball bearing", " ball  bearing ", ""], k=3)
    assert fusion.n_lists == 2
    assert fusion.top1 == ["848210", "848210"]
    two = index.fuse(["ball bearing", "Kugellager"], k=3)
    assert two.n_lists == 4 and len(two.top1) == 4


def test_unmatched_query_returns_nothing(index: HSIndex) -> None:
    assert index.search("", k=10) == []
    assert index.search("123 456", k=10) == []


def test_describe_gives_chapter_heading_subheading_path(index: HSIndex) -> None:
    path = index.describe("841370")
    assert path.split(" > ") == [
        "Machinery and mechanical appliances, boilers, nuclear reactors; parts thereof",
        "Pumps; for liquids, whether or not fitted with measuring device, liquid elevators",
        "Pumps; centrifugal, n.e.c. in heading no. 8413, for liquids",
    ]
    assert index.describe("8413.70") == path
    with pytest.raises(KeyError):
        index.describe("841399")


@pytest.mark.parametrize(
    ("code", "ok"),
    [("841370", True), ("8413.70", True), ("010121", True), ("841399", False), ("8413", False), ("abcdef", False)],
)
def test_valid(index: HSIndex, code: str, ok: bool) -> None:
    assert index.valid(code) is ok


def test_tokenize_folds_accents_and_drops_function_words() -> None:
    assert tokenize("Pumpe für Flüssigkeiten") == ["pump", "flussigkeiten"]
    assert tokenize("fur collar") == ["fur", "collar"]  # English 'fur' (chapter 43) is kept
    assert tokenize("Wrist-watches, n.e.c. in heading no. 9102") == ["wrist", "watch"]
