"""Adversarial review of hs/, dossier/ and tariffs.py: one regression test per confirmed bug, plus guards.

Every test marked "Bug:" failed before its fix. Fake LLM clients only; no network.
"""

from __future__ import annotations

import json
import re
import unicodedata
from decimal import Decimal

import pytest

from originpass.config import get_settings
from originpass.dossier import templates
from originpass.dossier.builder import build_dossier
from originpass.dossier.checklist import build_checklist
from originpass.dossier.facts import facts_json, letter_facts, origin_criterion_code
from originpass.dossier.validator import (
    check_facts,
    grounding_check,
    no_preference_check,
    number_values,
    origin_code_check,
)
from originpass.hs import prompts as hs_prompts
from originpass.hs.classifier import classify, parse_choice, rerank_messages
from originpass.hs.index import HSIndex, get_index, words
from originpass.llm import LLMResult, LLMUnavailable
from originpass.models import (
    AlternativeResult,
    BomLine,
    CheckResult,
    Criterion,
    CriterionKind,
    LineAssessment,
    Product,
    Rule,
    Verdict,
    VerdictStatus,
)
from originpass.tariffs import estimate_duty, load_tariffs


def nfd(text: str) -> str:
    return unicodedata.normalize("NFD", text)


class FakeLLM:
    """LLMClient.chat stub: canned replies (or exceptions) keyed by call tag; records every call."""

    def __init__(self, replies: dict[str, str | Exception]):
        self.replies = replies
        self.calls: list[dict] = []

    def chat(self, messages, role="large", temperature=0.0, max_tokens=800, tag=""):
        self.calls.append({"messages": messages, "role": role, "tag": tag})
        reply = self.replies.get(tag, LLMUnavailable("fake: no canned reply"))
        if isinstance(reply, Exception):
            raise reply
        return LLMResult(text=reply, source="replay", model="fake", prompt_tokens=1, completion_tokens=1, latency_s=0)


@pytest.fixture(scope="module")
def index() -> HSIndex:
    return get_index()


# ---------------------------------------------------------------------------
# HS: replay-key stability and tokenisation
# ---------------------------------------------------------------------------


def test_decomposed_unicode_is_tokenised_like_composed():
    """Bug: NFD input (macOS) split 'Kühlwasser' into 'ku' + 'hlwasser', because a combining mark is not \\w."""
    assert words(nfd("Kühlwasser Flüssigkeit")) == words("Kühlwasser Flüssigkeit") == ["kuhlwasser", "flussigkeit"]


def test_decomposed_input_gives_same_prompts_and_candidates(index):
    """Bug: the same visible text in NFD gave another replay key (and other candidates) than in NFC."""
    replies = {"hs_rewrite": json.dumps({"en": "centrifugal pump", "keywords": ["pump"]}), "hs_rerank": "{}"}
    composed, decomposed = FakeLLM(replies), FakeLLM(replies)
    a = classify("Kreiselpumpe für Kühlwasser", composed, index)
    b = classify(nfd("Kreiselpumpe für Kühlwasser"), decomposed, index)
    assert composed.calls == decomposed.calls
    assert a.query == b.query and [c.hs6 for c in a.candidates] == [c.hs6 for c in b.candidates]


# ---------------------------------------------------------------------------
# HS: JSON robustness of the rerank / rewrite replies
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("reply", "expected"),
    [
        # Bug: prose with other braces before the object made extract_json's first-{ to last-} slice invalid.
        (
            'Candidates {1, 2} fit less well. Answer: {"hs6": "841370", "confidence": 0.8, "rationale": "pump"}',
            ("841370", 0.8, "pump"),
        ),
        # Bug: a Python-style object with single quotes (common from small models) was rejected.
        ("{'hs6': '841370', 'confidence': 0.8, 'rationale': 'pump'}", ("841370", 0.8, "pump")),
        # Bug: 8- and 10-digit national tariff lines and an "HS" prefix were not reduced to the HS6 subheading.
        ('{"hs6": "8413.70.99", "confidence": 0.9}', ("841370", 0.9, "")),
        ('{"hs6": "8413 70 00 00", "confidence": 0.9}', ("841370", 0.9, "")),
        ('{"hs6": 84137099, "confidence": 0.9}', ("841370", 0.9, "")),
        ('{"hs6": "HS 8413.70", "confidence": 0.9}', ("841370", 0.9, "")),
        ('{"hs6": "８４１３．７０", "confidence": 0.9}', ("841370", 0.9, "")),
        # Guards: fenced JSON, codes that are not 6/8/10 digits, ambiguous replies.
        ('```json\n{"hs6": "8413.70", "confidence": 0.7}\n```\nGIR 1 applies.', ("841370", 0.7, "")),
        ('{"hs6": "84137", "confidence": 0.9}', ("84137", 0.9, "")),
        ('{"hs6": "8413709", "confidence": 0.9}', ("8413709", 0.9, "")),
        ('{"hs6": "841370", "confidence": 0.4} or rather {"hs6": "841381", "confidence": 0.9}', None),
        ('{"hs6": "841370", "confidence": "high"}', None),
        ('{"hs6": "841370", "confidence": 1.5}', None),
        ('{"hs6": 841370.0, "confidence": 0.9}', None),
    ],
)
def test_parse_choice_robustness(reply, expected):
    assert parse_choice(reply) == expected


def test_national_code_reply_is_accepted_by_the_classifier(index):
    """Bug: the model answering the national line '8413.70.99' made the classifier abstain."""
    llm = FakeLLM(
        {
            "hs_rewrite": json.dumps({"en": "centrifugal pump", "keywords": ["pump"]}),
            "hs_rerank": json.dumps({"hs6": "8413.70.99", "confidence": 0.9, "rationale": "pump"}),
        }
    )
    s = classify("centrifugal pump for water", llm, index)
    assert (s.chosen, s.abstained, s.method) == ("841370", False, "llm")


def test_rewrite_keywords_given_as_a_string(index):
    """Bug: keywords sent as one comma-separated string were dropped from the rewrite."""
    llm = FakeLLM({"hs_rewrite": '{"en": "centrifugal pump", "keywords": "pump, centrifugal"}', "hs_rerank": "{}"})
    classify("Kreiselpumpe", llm, index)
    assert "English rewrite: centrifugal pump (pump, centrifugal)" in llm.calls[1]["messages"][1]["content"]


def test_hs_prompts_are_deterministic_with_gloss_hint(index):
    """Guard: the gloss hint (rewrite failed) is deterministic, so replay keys stay stable."""
    replies = {"hs_rewrite": "not json", "hs_rerank": "{}"}
    first, second = FakeLLM(replies), FakeLLM(replies)
    classify("Kugellager Edelstahl 6204", first, index)
    classify("Kugellager Edelstahl 6204", second, index)
    assert first.calls == second.calls
    user = first.calls[1]["messages"][1]["content"]
    assert "Word-by-word glossary gloss (may be inaccurate): ball bearing stainless steel 6204" in user
    assert "English rewrite" not in user


def test_abstention_on_a_valid_code_outside_the_candidates(index):
    """Guard: a plausible code that is not a retrieved candidate is never accepted."""
    llm = FakeLLM(
        {
            "hs_rewrite": json.dumps({"en": "centrifugal pump", "keywords": ["pump"]}),
            "hs_rerank": json.dumps({"hs6": "9102.11", "confidence": 0.99}),
        }
    )
    s = classify("centrifugal pump", llm, index)
    assert s.abstained and s.chosen is None and "910211" in s.rationale


def test_rerank_prompt_has_no_gloss_line_when_a_rewrite_exists(index):
    cands = index.search("ball bearing", k=2)
    user = rerank_messages("Kugellager", "ball bearing", cands, index, "ball bearing")[1]["content"]
    assert "English rewrite: ball bearing" in user and "glossary" not in user
    assert hs_prompts.RERANK_GLOSS_LINE.format(gloss="x") not in user


# ---------------------------------------------------------------------------
# Dossier fixtures: CHF 1250 ex-works, MAXNOM 50 %
# ---------------------------------------------------------------------------

MAXNOM50 = Rule(
    rule_id="TEST-MAXNOM50",
    hs_scope=["8413"],
    alternatives=[[Criterion(kind=CriterionKind.MAXNOM, max_nom_pct=50.0)]],
    text="SYNTHETIC TEST RULE - not legal text",
    source="tests (synthetic)",
)
WO_RULE = Rule(
    rule_id="TEST-WO",
    hs_scope=["0301"],
    alternatives=[[Criterion(kind=CriterionKind.WO)]],
    text="SYNTHETIC TEST RULE - not legal text",
    source="tests (synthetic)",
)


def case(
    status: VerdictStatus = VerdictStatus.PASS,
    *,
    l2_origin: str = "DE",
    rule: Rule = MAXNOM50,
    hs6: str = "841370",
    name: str = "Pump CP-200",
    checks: list[CheckResult] | None = None,
) -> tuple[Product, Verdict]:
    originating = l2_origin in ("CH", "CN")
    product = Product(
        product_id="P-1",
        name=name,
        description="pump",
        hs6=hs6,
        ex_works_chf=1250.0,
        bom=[
            BomLine(line_id="L1", description="motor", hs6="850152", origin_country="CH", value_chf=400.0),
            BomLine(line_id="L2", description="housing", hs6="732510", origin_country=l2_origin, value_chf=591.25),
        ],
    )
    nom = 0.0 if originating else 591.25
    met = {VerdictStatus.PASS: True, VerdictStatus.FAIL: False, VerdictStatus.UNSURE: None}[status]
    verdict = Verdict(
        product_id="P-1",
        status=status,
        hs6=hs6,
        rule=rule,
        rule_verified=True,
        alternatives=[
            AlternativeResult(
                criteria=rule.alternatives[0],
                met=met,
                checks=checks or [CheckResult(name="MAXNOM 50%", passed=met, detail="synthetic", line_ids=["L2"])],
            )
        ],
        general_checks=[CheckResult(name="direct transport", passed=True, detail="no transit")],
        lines=[
            LineAssessment(line_id="L1", originating=True, reason="CH", hs6="850152", value_chf=400.0),
            LineAssessment(line_id="L2", originating=originating, reason=l2_origin, hs6="732510", value_chf=591.25),
        ],
        nom_value_chf=nom,
        nom_pct=round(100 * nom / 1250, 2),
        threshold_pct=50.0,
        margin_pct=round(50.0 - 100 * nom / 1250, 2),
        reasons=["synthetic"],
    )
    return product, verdict


# ---------------------------------------------------------------------------
# Dossier: no claim of preferential treatment in FAIL / UNSURE letters
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "lang"),
    [
        # Bug: a negation anywhere in the sentence covered a claim in another clause.
        ("我司不能提供其他文件，但贵司可申请适用协定税率。", "zh"),
        ("Without delay, your company may apply for the FTA tariff rate.", "en"),
        ("We cannot ship before May, but your company can apply for the FTA (conventional) tariff rate.", "en"),
        # Bug: duty advantages worded without the listed terms were not recognised as claims.
        ("贵司进口时可享受零关税。", "zh"),
        ("贵司可享受中瑞自贸协定的关税减免。", "zh"),
        ("贵司可享受优惠税率。", "zh"),
        ("Your company can import the goods duty-free.", "en"),
        ("Your company will benefit from a tariff reduction under the agreement.", "en"),
    ],
)
def test_no_preference_check_catches_claims(text, lang):
    assert not no_preference_check(text, lang).found


@pytest.mark.parametrize(
    ("text", "lang"),
    [
        ("因此，本批货物不能随附原产地证书或原产地声明，贵司不能申请适用中瑞自贸协定项下的协定税率，进口时适用最惠国税率。", "zh"),
        ("本批货物不适用协定税率，也没有原产地证书。", "zh"),
        ("No certificate of origin will accompany this shipment; your company cannot apply for the FTA rate.", "en"),
        ("This shipment is not eligible for preferential tariff treatment.", "en"),
    ],
)
def test_no_preference_check_accepts_negative_statements(text, lang):
    assert no_preference_check(text, lang).found


@pytest.mark.parametrize("status", [VerdictStatus.FAIL, VerdictStatus.UNSURE])
def test_fail_and_unsure_template_letters_claim_nothing(status):
    """Guard: the template letters (always the fallback) pass the stricter clause-level check."""
    product, verdict = case(status)
    assert no_preference_check(templates.letter_zh(product, verdict), "zh").found
    assert no_preference_check(templates.letter_en(product, verdict), "en").found
    assert "原产地标准" not in templates.letter_zh(product, verdict)
    assert origin_criterion_code(verdict) is None


def test_fail_model_letter_promising_zero_duty_is_replaced():
    """Bug: a FAIL letter promising zero duty passed every check and was shipped to the buyer."""
    product, verdict = case(VerdictStatus.FAIL)
    claim = (
        "尊敬的[进口商名称]：\n\n产品“Pump CP-200”（HS编码：8413.70）目前不符合中瑞自贸协定的原产地规则，"
        "本批货物不能随附原产地证书或原产地声明，贵司不能申请协定税率。但贵司可享受零关税。\n\n此致\n敬礼！"
    )
    dossier = build_dossier(product, verdict, FakeLLM({"dossier.letter": claim}))
    assert dossier.letter_zh.llm_source == "template"
    assert dossier.letter_zh.text == templates.letter_zh(product, verdict)


# ---------------------------------------------------------------------------
# Dossier: number validator
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("text", ["CHF 50,000", "CHF 50.000", "50,000 units"])
def test_threshold_is_not_found_inside_a_thousands_number(text):
    """Bug: '50,000' was also read as 50.000 = 50, so it 'stated' the 50 % threshold and was grounded by it."""
    assert not check_facts(text, {"threshold": "50"}, ["threshold"])[0].found
    assert not grounding_check(text, '{"max_non_originating_pct": "50"}').found


@pytest.mark.parametrize(
    ("text", "value", "found"),
    [
        ("147.3%", "47.3", False),
        ("500%", "50", False),
        ("47.35%", "47.3", False),
        ("8413.70", "70", False),
        ("47,3 %", "47.3", True),
        ("CHF 1,250.00", "1250", True),
        ("CHF 1'250", "1250", True),
        ("0,750 kW", "0.75", True),
    ],
)
def test_numbers_match_whole_tokens_only(text, value, found):
    """Guard: a fact never matches a number it is a substring of."""
    assert check_facts(text, {"x": value}, ["x"])[0].found is found


def test_number_readings():
    assert number_values("1,250") == number_values("1.250") == {1250}
    assert number_values("47,3") == number_values("47.30") == {Decimal("47.3")}
    assert number_values("1,250.50") == number_values("1.250,50") == number_values("1'250.50")


@pytest.mark.parametrize(
    ("text", "status", "found"),
    [
        # Bug: any occurrence of the verdict word counted, so an explanation claiming PASS for a FAIL product
        # passed the check as soon as "FAIL" appeared later in the text.
        ("Verdict: PASS. Without the tolerance it would FAIL.", "FAIL", False),
        ("Verdict: UNSURE for now; it can still PASS or FAIL.", "PASS", False),
        # Guards: the first verdict word decides; capitals (as instructed) win over an earlier lowercase word.
        ("Verdict: FAIL. It would PASS with a CH supplier.", "FAIL", True),
        ("Fail-safe valve FS-2: verdict PASS.", "PASS", True),
        ("Verdict: Pass.", "PASS", True),
        ("The product fails.", "FAIL", False),
    ],
)
def test_status_is_the_first_verdict_word(text, status, found):
    assert check_facts(text, {"status": status}, ["status"])[0].found is found


def test_explanation_with_the_wrong_verdict_is_replaced():
    """Bug: a model explanation opening with "Verdict: PASS" was accepted for a FAIL product."""
    product, verdict = case(VerdictStatus.FAIL)
    wrong = (
        "Verdict: PASS. Pump CP-200 (HS 8413.70) is close to the limit; it would FAIL only if the share rose. "
        "Non-originating materials are 47.3% of the ex-works price, against a maximum of 50%."
    )
    dossier = build_dossier(product, verdict, FakeLLM({"dossier.explain": wrong}))
    assert dossier.explanation_en.llm_source == "template"
    assert dossier.explanation_en.text.startswith("Verdict: FAIL.")


def test_product_name_in_decomposed_unicode_is_found():
    """Bug: a product name stored in NFD never matched the model's (NFC) text, forcing the template."""
    facts = {"product": nfd("Kühlpumpe Zürich")}
    assert check_facts("Die Kühlpumpe Zürich erfüllt ...", facts, ["product"])[0].found


# ---------------------------------------------------------------------------
# Dossier: origin criterion code on the certificate (WO / WP / PSR)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("kwargs", "code"),
    [
        ({"l2_origin": "DE"}, "PSR"),  # a non-originating material is used
        ({"l2_origin": "CN"}, "WP"),  # every material originates in CH/CN
        ({"l2_origin": "CN", "rule": WO_RULE, "hs6": "030111"}, "WO"),  # wholly obtained rule met
    ],
)
def test_pass_letter_states_the_right_origin_criterion_code(kwargs, code):
    """Bug: the PASS letter always cited the product-specific rule and never the certificate's criterion code,
    so a product made only from CH/CN materials (WP) or wholly obtained (WO) was presented as PSR."""
    product, verdict = case(**kwargs)
    assert origin_criterion_code(verdict) == code
    zh, en = templates.letter_zh(product, verdict), templates.letter_en(product, verdict)
    assert f"原产地标准为“{code}”" in zh
    assert f'the origin criterion stated on the certificate of origin is "{code}"' in en
    others = {"WO", "WP", "PSR"} - {code}
    assert not any(re.search(rf"\b{o}\b", zh + en) for o in others)
    assert ("适用的产品特定原产地规则" in zh) is (code == "PSR")
    assert letter_facts(product, verdict)["origin_criterion_code"] == code
    assert any(f'origin criterion "{code}"' in item for item in build_checklist(product, verdict))
    dossier = build_dossier(product, verdict, None)
    assert all(c.found for c in dossier.letter_zh.fact_checks + dossier.back_translation_en.fact_checks)


def test_model_letter_with_a_wrong_origin_code_is_replaced():
    """Bug: a PASS letter citing WP for a product with non-originating materials passed validation."""
    product, verdict = case()  # PSR
    wrong = (
        "尊敬的[进口商名称]：\n\n我司向贵司出口的产品“Pump CP-200”（HS编码：8413.70）符合中瑞自贸协定的原产地规则，"
        "原产地证书所列原产地标准为“WP”。本批货物将随附原产地证书，贵司可申请适用协定税率。\n\n此致\n敬礼！"
    )
    assert not origin_code_check(wrong, "PSR").found
    dossier = build_dossier(product, verdict, FakeLLM({"dossier.letter": wrong}))
    assert dossier.letter_zh.llm_source == "template" and "“PSR”" in dossier.letter_zh.text


def test_letter_prompt_gives_the_code_and_stays_stable():
    product, verdict = case(l2_origin="CN")
    block = facts_json(letter_facts(product, verdict))
    assert '"origin_criterion_code": "WP"' in block and block == facts_json(letter_facts(*case(l2_origin="CN")))


# ---------------------------------------------------------------------------
# Dossier: German template (Swiss Standard German) and Chinese terminology
# ---------------------------------------------------------------------------


def test_german_open_points_use_german_criterion_names():
    """Bug: undecided criterion checks were listed with the engine's English names ('Offene Punkte: SPECIFIC')."""
    checks = [
        CheckResult(name="SPECIFIC", passed=None, detail="needs human judgement"),
        CheckResult(name="CTH except from 9114", passed=None, detail="L2 has no HS code"),
        CheckResult(name="MAXNOM 40.5%", passed=None, detail="synthetic"),
    ]
    product, verdict = case(VerdictStatus.UNSURE, checks=checks)
    text = templates.explanation_de(product, verdict)
    assert (
        "Offene Punkte: spezifische Be- oder Verarbeitung, Positionswechsel (mit Ausnahmen), "
        "Wertkriterium (höchstens 40,5 %)." in text
    )
    assert "SPECIFIC" not in text and "MAXNOM 40" not in text and "ß" not in text


@pytest.mark.parametrize("status", list(VerdictStatus))
def test_german_templates_use_swiss_spelling(status):
    product, verdict = case(status)
    text = templates.explanation_de(product, verdict)
    assert "ß" not in text and "CHF 1'250.00" in text
    assert "Ursprungseigenschaft" in text and "Ab-Werk-Preis" in text


def test_chinese_letters_use_prc_customs_terms():
    pass_zh = templates.letter_zh(*case())
    for term in ("原产地证书", "原产地声明", "经核准出口商", "协定税率", "出厂价", "非原产材料", "原产地标准", "直接运输"):
        assert term in pass_zh, term
    assert "由瑞士直接运输至中国" in pass_zh
    assert "transported directly from Switzerland to China" in templates.letter_en(*case())
    fail_zh = templates.letter_zh(*case(VerdictStatus.FAIL))
    assert "最惠国税率" in fail_zh and "不能申请适用中瑞自贸协定项下的协定税率" in fail_zh


# ---------------------------------------------------------------------------
# Tariffs
# ---------------------------------------------------------------------------

TARIFFS = {
    "841370": {
        "description": "synthetic",
        "mfn_rate_pct": 8.0,
        "fta_rate_pct": 7.2,
        "source": "GACC Announcement 2014 No. 53, Annex 1 (rates at 1 July 2014). Current 2026 rates may be lower.",
        "verified": True,
    }
}


@pytest.mark.parametrize("code", ["８４１３．７０", "８４１３７０", "8413　70"])
def test_full_width_hs_code_gets_a_duty_estimate(code):
    """Bug: a full-width code from a Chinese IME (accepted by the engine via NFKC) gave no duty estimate."""
    duty = estimate_duty(code, 1000.0, TARIFFS)
    assert duty is not None and duty.hs6 == "841370" and duty.duty_saved_chf == 8.0


def test_dossier_duty_for_full_width_product_code():
    product, verdict = case()
    product = product.model_copy(update={"hs6": "８４１３．７０"})
    assert build_dossier(product, verdict, None, TARIFFS).duty is not None


def test_committed_rates_are_labelled_as_2014_rates_not_current():
    """Guard: every committed rate says it is the 1 July 2014 schedule and that 2026 rates may differ, and the
    estimate passes that label on unchanged."""
    tariffs = load_tariffs(get_settings().data_dir)
    assert tariffs
    for code, entry in tariffs.items():
        assert entry["verified"] and "rates at 1 July 2014" in entry["source"], code
        assert "Current 2026 rates may be lower" in entry["source"], code
    duty = estimate_duty("841370", 1250.0, tariffs)
    assert duty is not None and "1 July 2014" in duty.source and not duty.source.startswith("UNVERIFIED")


@pytest.mark.parametrize("status", list(VerdictStatus))
def test_dossier_texts_quote_no_tariff_rates_or_years(status):
    """Guard: duty rates live only in the labelled DutyEstimate, never in the explanation, letter or checklist."""
    product, verdict = case(status)
    dossier = build_dossier(product, verdict, None, TARIFFS)
    texts = [dossier.explanation_en.text, dossier.explanation_de.text, dossier.letter_zh.text]
    texts += [dossier.back_translation_en.text, *dossier.checklist]
    for text in texts:
        assert not re.search(r"\b(?:2014|2026)\b|7\.2|7,2", text), text
