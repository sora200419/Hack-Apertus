"""SANITY CHECK, NOT THE BENCHMARK: retrieval top-10 hit rate on hand-written part descriptions.

The descriptions and expected HS6 codes below were written by the developers to catch regressions
in the retrieval layer. They are not drawn from customs rulings and are not used to report accuracy;
the benchmark lives in the eval package. Run with `-s` to print the hit rates.
"""

from __future__ import annotations

import pytest

from originpass.hs.classifier import classify
from originpass.hs.index import HSIndex, get_index

# (description, expected HS6)
SANITY_EN: list[tuple[str, str]] = [
    ("centrifugal pump for liquids", "841370"),
    ("wrist watch, automatic winding, stainless steel case", "910221"),
    ("electric motor DC 100 W", "850131"),
    ("disposable syringe", "901831"),
    ("deep groove ball bearing", "848210"),
    ("hexagon head bolt of stainless steel", "731815"),
    ("bare printed circuit board", "853400"),
    ("lithium-ion battery pack", "850760"),
    ("rubber O-ring seal", "401693"),
    ("glass ampoules for pharmaceuticals", "701010"),
    ("milk chocolate bar with hazelnut filling, 100 g", "180631"),
    ("domestic electric coffee machine", "851671"),
    ("complete automatic watch movement", "910820"),
    ("leather watch strap", "911390"),
    ("enamelled copper winding wire", "854411"),
    ("LED lamp", "853952"),
    ("hearing aid", "902140"),
    ("red wine in 75 cl bottles", "220421"),
    ("CNC horizontal lathe for metal", "845811"),
    ("photovoltaic solar panel", "854143"),
    ("pneumatic valve", "848120"),
    ("hydraulic gear pump", "841360"),
    ("laptop computer", "847130"),
    ("microcontroller integrated circuit", "854231"),
    ("digital thermometer", "902519"),
    ("Emmental cheese", "040690"),
]

# (description in DE/FR/IT, English gloss, expected HS6). The gloss stands in for an LLM rewrite
# to check that fusing the raw text with an English rewrite keeps the right code in the top 10.
SANITY_FOREIGN: list[tuple[str, str, str]] = [
    ("Zentrifugalpumpe für Flüssigkeiten", "centrifugal pump for liquids", "841370"),
    ("Armbanduhr mit automatischem Aufzug, Edelstahlgehäuse", "wrist watch, automatic winding, steel case", "910221"),
    ("Gleichstrommotor 100 W", "DC electric motor 100 W", "850131"),
    ("Einwegspritze", "disposable syringe", "901831"),
    ("Rillenkugellager", "deep groove ball bearing", "848210"),
    ("Lithium-Ionen-Akku", "lithium-ion battery", "850760"),
    ("Leiterplatte unbestückt", "bare printed circuit board", "853400"),
    ("Kaffeemaschine für den Haushalt", "domestic coffee machine", "851671"),
    ("Hörgerät", "hearing aid", "902140"),
    ("Uhrarmband aus Leder", "leather watch strap", "911390"),
    ("Sechskantschraube aus Edelstahl", "stainless steel hexagon head bolt", "731815"),
    ("pompe centrifuge pour liquides", "centrifugal pump for liquids", "841370"),
    ("montre-bracelet automatique, boîtier en acier inoxydable", "automatic wrist watch, steel case", "910221"),
    ("roulement à billes", "ball bearing", "848210"),
    ("seringue jetable", "disposable syringe", "901831"),
    ("moteur électrique à courant continu 100 W", "DC electric motor 100 W", "850131"),
    ("chocolat au lait en tablette fourré", "filled milk chocolate bar", "180631"),
    ("fil de cuivre émaillé pour bobinage", "enamelled copper winding wire", "854411"),
    ("panneau solaire photovoltaïque", "photovoltaic solar panel", "854143"),
    ("pompa centrifuga per liquidi", "centrifugal pump for liquids", "841370"),
    ("orologio da polso automatico", "automatic wrist watch", "910221"),
    ("cuscinetto a sfere", "ball bearing", "848210"),
]


def _hit_rate(index: HSIndex, queries: list[list[str]], expected: list[str]) -> float:
    hits = sum(code in {c.hs6 for c in index.fuse(texts, k=10).candidates} for texts, code in zip(queries, expected))
    return hits / len(expected)


@pytest.fixture(scope="module")
def index() -> HSIndex:
    return get_index()


def test_sanity_lists_use_valid_codes(index: HSIndex) -> None:
    assert len(SANITY_EN) >= 15 and len(SANITY_FOREIGN) >= 10
    assert all(index.valid(code) for _, code in SANITY_EN)
    assert all(index.valid(code) for *_, code in SANITY_FOREIGN)


def test_english_top10_hit_rate(index: HSIndex) -> None:
    rate = _hit_rate(index, [[d] for d, _ in SANITY_EN], [c for _, c in SANITY_EN])
    print(f"\n[sanity] EN raw top-10 hit rate: {rate:.2f} (n={len(SANITY_EN)})")
    assert rate >= 0.8


def test_foreign_raw_top10_hit_rate(index: HSIndex) -> None:
    """Raw DE/FR/IT text without any LLM: only cognates help, so the bar is low by design."""
    rate = _hit_rate(index, [[d] for d, _, _ in SANITY_FOREIGN], [c for *_, c in SANITY_FOREIGN])
    print(f"\n[sanity] DE/FR/IT raw top-10 hit rate: {rate:.2f} (n={len(SANITY_FOREIGN)})")
    assert rate >= 0.2


def test_foreign_with_english_gloss_top10_hit_rate(index: HSIndex) -> None:
    """Raw text fused with an English rewrite, as the classifier does when Apertus is available."""
    rate = _hit_rate(index, [[g, d] for d, g, _ in SANITY_FOREIGN], [c for *_, c in SANITY_FOREIGN])
    print(f"\n[sanity] DE/FR/IT raw + English gloss top-10 hit rate: {rate:.2f} (n={len(SANITY_FOREIGN)})")
    assert rate >= 0.8


def test_retrieval_only_precision_when_not_abstaining(index: HSIndex) -> None:
    """Margin rule without an LLM: report coverage and precision of the picks it does make."""
    results = [(classify(d, None, index), code) for d, code in SANITY_EN]
    picked = [(r.chosen, code) for r, code in results if not r.abstained]
    correct = sum(chosen == code for chosen, code in picked)
    print(
        f"\n[sanity] EN retrieval-only: picked {len(picked)}/{len(results)}, correct {correct}/{len(picked)} of picks"
    )
    assert all(r.method == "retrieval_only" and r.llm_source == "none" for r, _ in results)
    assert not picked or correct / len(picked) >= 0.75
