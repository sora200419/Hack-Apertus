"""Static DE/FR/IT -> EN glossary (hs.glossary) and its use in the HS classifier when no model rewrite exists."""

from __future__ import annotations

import csv
import json
import re
import unicodedata

import pytest

from originpass.config import get_settings
from originpass.hs import glossary
from originpass.hs.classifier import classify
from originpass.hs.glossary import DE, FR, IT, gloss
from originpass.hs.index import HSIndex, fold, get_index
from originpass.llm import LLMResult, LLMUnavailable


@pytest.fixture(scope="module")
def index() -> HSIndex:
    return get_index()


@pytest.fixture(scope="module")
def hs_vocabulary() -> set[str]:
    """Folded words of the English HS 2022 nomenclature."""
    with (get_settings().data_dir / "hs" / "hs2022.csv").open(encoding="utf-8-sig", newline="") as f:
        return {fold(w) for row in csv.DictReader(f) for w in re.findall(r"[^\W_]+", row["description"])}


class FakeLLM:
    def __init__(self, replies: dict[str, str | Exception]):
        self.replies = replies
        self.calls: list[dict] = []

    def chat(self, messages, role="large", temperature=0.0, max_tokens=800, tag=""):
        self.calls.append({"messages": messages, "tag": tag})
        reply = self.replies[tag]
        if isinstance(reply, Exception):
            raise reply
        return LLMResult(text=reply, source="replay", model="fake", prompt_tokens=1, completion_tokens=1, latency_s=0)


# ---------------------------------------------------------------------------
# Term coverage
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("table", [DE, FR, IT], ids=["de", "fr", "it"])
def test_every_entry_translates_to_its_own_english(table):
    """Each key, written as in the table, is found and not shadowed by another entry ("für" marks the line as
    German so that English homographs such as "Motor" are translated too)."""
    wrong = {src: gloss(f"{src} für") for src, en in table.items() if gloss(f"{src} für") != f"{en} für"}
    assert not wrong


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Kugellager Edelstahl 6204", "ball bearing stainless steel 6204"),
        ("Rillenkugellager 6005-2Z", "deep groove ball bearing 6005-2Z"),
        ("Roulement à billes 6202-2RS", "ball bearing 6202-2RS"),
        ("Roulements à billes", "ball bearings"),
        ("Cuscinetto a sfere 6203 2RS", "ball bearing 6203 2RS"),
        ("Joint torique NBR 20x2", "o-ring seal NBR 20x2"),
        ("Macchina da caffè automatica", "coffee machine automatic"),
        ("Typenschild Aluminium", "name-plate aluminium"),
        ("Presse-étoupe M20", "cable gland M20"),
    ],
)
def test_terms_and_phrases(text, expected):
    assert gloss(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Schrauben M6", "screw M6"),  # German plural
        ("Elektrische Antriebe", "electric actuator drive"),
        ("Cuscinetti", "bearing"),  # Italian plural
        ("Valvole elettriche", "valve electric"),
        ("Écrous zingués", "nut zinc-plated"),  # French plural, feminine participle
        ("Pièces chromées", "part chromium-plated"),
        ("Composants médicaux", "Composants medical"),  # -aux -> -al
    ],
)
def test_inflected_forms(text, expected):
    assert gloss(text) == expected


# ---------------------------------------------------------------------------
# German compounds
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Edelstahlgehäuse", "stainless steel housing case"),
        ("Zentrifugalpumpe", "centrifugal pump"),
        ("Pumpenwelle", "pump shaft"),  # linking -n-
        ("Zylinderrollenlager NU 206", "cylinder roller bearing NU 206"),  # longest head first
        ("Uhrzeiger", "watch clock hands"),
        ("Kupferlackdraht 0,3 mm", "copper paint varnish wire 0,3 mm"),  # recursive modifier
        ("Sechskantmutter M10 verzinkt", "Sechskant nut M10 galvanised zinc-plated"),  # unknown modifier as written
        ("Ventilgehäuse Stahlguss", "valve housing case cast steel"),
        ("Getriebemotor 24V DC", "gearbox gearing motor 24V DC"),  # homograph head, translated modifier
        ("Sicherungsmutter M12", "lock nut M12"),  # the whole compound is a key: not "fuse nut"
    ],
)
def test_compounds(text, expected):
    assert gloss(text) == expected


def test_homograph_head_with_unknown_modifier_needs_other_evidence():
    assert gloss("Polyamidring") is None  # could be English
    assert gloss("Dichtung mit Polyamidring") == "gasket seal mit Polyamid ring"


def test_compounds_are_german_only():
    """French/Italian keys are not compound heads ("Luminox" is not "lum" + "inox")."""
    assert gloss("Luminox strap") is None and gloss("Victorinox knife") is None
    assert gloss("Upgrade kit") is None  # "rade" -> "Rad" is shorter than a compound head may be


# ---------------------------------------------------------------------------
# Accents, case, Unicode forms
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Écrou hexagonal M6", "nut hexagonal M6"),
        ("Ecrou hexagonal M6", "nut hexagonal M6"),  # accent missing in the BOM
        ("ÉLECTROVANNE 24 V", "solenoid valve 24 V"),
        ("Gehause Edelstahl", "housing case stainless steel"),
        ("Schliesse Edelstahl", "clasp buckle stainless steel"),
        ("Schließe Edelstahl", "clasp buckle stainless steel"),  # German sharp s folds to Swiss "ss"
    ],
)
def test_accents_and_case(text, expected):
    assert gloss(text) == expected


def test_an_added_accent_is_not_an_inflection():
    """'fraisée' (countersunk) is not the noun 'fraise' (milling cutter); the word is kept as written."""
    assert gloss("Vis à tête fraisée M5") == "screw à tête fraisée M5"
    assert gloss("Fraise à rainurer") == "milling cutter à rainurer"


def test_decomposed_unicode_gives_the_same_gloss():
    text = "Edelstahlgehäuse für Kühlwasser, Écrou zingué"
    assert gloss(unicodedata.normalize("NFD", text)) == gloss(text) is not None


# ---------------------------------------------------------------------------
# What is kept, and English lines
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Kugellager 6204-2RS C3, SKF", "ball bearing 6204-2RS C3, SKF"),
        ("Unterlegscheibe M6 DIN 125 A2", "washer M6 DIN 125 A2"),
        ("Keramikkondensator 10µF 25V 0805", "ceramic capacitor 10µF 25V 0805"),
        ("Aluminiumblech 3 mm EN AW-5754", "aluminium sheet 3 mm EN AW-5754"),
        ("Druckfeder Federstahl 0,8x6x20", "compression spring spring steel 0,8x6x20"),
        ("Rückschlagventil Messing 3/4 Zoll", "Rückschlag valve brass 3/4 Zoll"),
        ("Lithium-Ionen-Akku 3,7V", "Lithium-Ionen-accumulator battery 3,7V"),
    ],
)
def test_unknown_tokens_and_part_numbers_are_kept_as_written(text, expected):
    assert gloss(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "Deep groove ball bearing 6204-2RS, stainless steel",
        "Hex nut M8 DIN 934, zinc plated steel",
        "Welded stainless steel tube 1.4301, 25x1.5 mm",
        "Motor 24 V with filter",
        "Measuring tool for monitoring bearing wear",
        "Replacement files for pedicure tools",
        "Silicone watch strap with buckle, set of 2",
        "",
        "6204-2RS 25x1.5",
    ],
)
def test_english_and_code_only_lines_are_not_glossed(text):
    assert gloss(text) is None


def test_no_english_hs_word_is_glossed(hs_vocabulary):
    """An English line made of nomenclature words is never mistaken for a foreign one."""
    assert not {w for w in hs_vocabulary if gloss(w) is not None}


def test_english_forms_list_is_complete(hs_vocabulary):
    """ENGLISH_FORMS holds exactly the nomenclature words that stemming/splitting would turn into strong evidence."""
    keys = {k for table in glossary.WORDS.values() for k in table}
    saved = glossary.ENGLISH_FORMS
    try:
        glossary.ENGLISH_FORMS = frozenset()
        reached = {w for w in hs_vocabulary - keys if (m := glossary._word(w, w)) is not None and m[1]}
    finally:
        glossary.ENGLISH_FORMS = saved
    assert reached == set(saved)


def test_function_words_mark_a_foreign_line():
    assert gloss("Motor") is None and gloss("Filter") is None
    assert gloss("Motor für Pumpe") == "motor für pump"
    assert gloss("Filter pour huile") == "filter pour oil"
    assert gloss("Motore con riduttore") == "motor con gear reducer gearbox"


def test_nothing_translated_is_none():
    assert gloss("Mikrocontroller 32-Bit ARM Cortex-M4") is None
    assert gloss("Manomètre à tube de Bourdon") is None  # "à" marks French, but no word is in the glossary


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_gloss_is_deterministic_and_pure():
    lines = [
        "Kugellager Edelstahl 6204",
        "Vis à tête cylindrique six pans creux M3x8 inox A2",
        "Leiterplatte bestückt, Steuerelektronik für Frequenzumrichter",
        "Orologio da polso automatico, cassa in acciaio",
    ]
    first = [gloss(t) for t in lines]
    lexicon = dict(glossary.LEXICON)
    assert [gloss(t) for t in reversed(lines)][::-1] == first == [gloss(t) for t in lines]
    assert glossary.LEXICON == lexicon


def test_glossary_has_no_conflicting_keys():
    folded: dict[str, str] = {}
    for table in (DE, FR, IT):
        for source, english in table.items():
            key = " ".join(fold(w) for w in re.findall(r"[^\W_]+", unicodedata.normalize("NFC", source)))
            assert folded.setdefault(key, english) == english, key


def test_german_keys_use_swiss_spelling():
    assert not [k for k in DE if "ß" in k]


# ---------------------------------------------------------------------------
# Use in the classifier (no model rewrite)
# ---------------------------------------------------------------------------


def test_retrieval_only_fuses_raw_text_and_gloss(index):
    text = "Kugellager Edelstahl 6204"
    s = classify(text, None, index)
    expected = index.fuse(["ball bearing stainless steel 6204", text], k=10)
    assert [c.hs6 for c in s.candidates] == [c.hs6 for c in expected.candidates]
    assert s.candidates[0].hs6 == "848210"
    assert s.method == "retrieval_only" and 'glossary gloss "ball bearing stainless steel 6204"' in s.rationale
    raw_only = index.fuse([text], k=10)
    assert "848210" not in [c.hs6 for c in raw_only.candidates[:3]]  # what the gloss fixes


def test_english_line_uses_raw_text_only(index):
    text = "centrifugal pump for liquids"
    s = classify(text, None, index)
    assert [c.hs6 for c in s.candidates] == [c.hs6 for c in index.fuse([text], k=10).candidates]
    assert "glossary" not in s.rationale


def test_rewrite_unavailable_falls_back_to_gloss(index):
    llm = FakeLLM({"hs_rewrite": LLMUnavailable("replay cache miss")})
    s = classify("Kreiselpumpe 0,55 kW Edelstahl", llm, index)
    assert s.method == "retrieval_only" and s.candidates[0].hs6 == "841370"
    assert [c["tag"] for c in llm.calls] == ["hs_rewrite"]


def test_malformed_rewrite_shows_the_gloss_to_the_reranker(index):
    llm = FakeLLM({"hs_rewrite": "Sure! A pump.", "hs_rerank": json.dumps({"hs6": "841370", "confidence": 0.9})})
    s = classify("Kreiselpumpe 0,55 kW Edelstahl", llm, index)
    assert (s.chosen, s.method) == ("841370", "llm")
    user = llm.calls[1]["messages"][1]["content"]
    assert "Word-by-word glossary gloss (may be inaccurate): centrifugal pump 0,55 kW stainless steel\n" in user
    assert "English rewrite" not in user


def test_model_rewrite_takes_precedence_over_the_gloss(index):
    rewrite = json.dumps({"en": "centrifugal pump of stainless steel", "keywords": ["pump"]})
    llm = FakeLLM({"hs_rewrite": rewrite, "hs_rerank": json.dumps({"hs6": "841370", "confidence": 0.9})})
    text = "Kreiselpumpe 0,55 kW Edelstahl"
    s = classify(text, llm, index)
    expected = index.fuse(["centrifugal pump of stainless steel (pump)", text], k=10)
    assert [c.hs6 for c in s.candidates] == [c.hs6 for c in expected.candidates]
    assert "glossary" not in llm.calls[1]["messages"][1]["content"]
