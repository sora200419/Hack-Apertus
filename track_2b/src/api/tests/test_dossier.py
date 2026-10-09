"""Dossier: fact extraction and checks, generation with regeneration/fallback, letters, checklist (fake LLM only)."""

from __future__ import annotations

import pytest

from originpass.dossier import prompts, templates
from originpass.dossier.builder import build_dossier
from originpass.dossier.validator import (
    check_facts,
    extract_facts,
    glossary_check,
    grounding_check,
    no_preference_check,
    ungrounded_numbers,
)
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
    Shipment,
    Verdict,
    VerdictStatus,
)

# ---------------------------------------------------------------------------
# Synthetic cases: CHF 1250 ex-works, non-originating L2 -> 47.3 % (PASS) or 56 % (FAIL), limit 50 %
# ---------------------------------------------------------------------------

RULE = Rule(
    rule_id="TEST-8413-MAXNOM50",
    hs_scope=["8413"],
    alternatives=[[Criterion(kind=CriterionKind.MAXNOM, max_nom_pct=50.0)]],
    text="SYNTHETIC TEST RULE - not legal text",
    source="tests (synthetic)",
)
TARIFFS = {
    "841370": {
        "description": "synthetic",
        "mfn_rate_pct": 8.0,
        "fta_rate_pct": 0.0,
        "source": "synthetic test entry",
        "verified": True,
    }
}


def make_case(status: VerdictStatus = VerdictStatus.PASS, hs6: str | None = "841370") -> tuple[Product, Verdict]:
    l2_value = 700.0 if status is VerdictStatus.FAIL else 591.25
    nom_pct = round(100 * l2_value / 1250, 2)
    transit = ["DE"] if status is VerdictStatus.UNSURE else []
    product = Product(
        product_id="P-1",
        name="Pump CP-200",
        description="centrifugal pump",
        hs6=hs6,
        ex_works_chf=1250.0,
        processing=["machining", "assembly and testing"],
        bom=[
            BomLine(line_id="L1", description="electric motor", hs6="850152", origin_country="CH", value_chf=400.0),
            BomLine(line_id="L2", description="cast housing", hs6="732510", origin_country="DE", value_chf=l2_value),
        ],
        shipment=Shipment(transit_countries=transit, order_quantity=10),
    )
    maxnom_ok = status is not VerdictStatus.FAIL
    verdict = Verdict(
        product_id="P-1",
        status=status,
        hs6=hs6,
        rule=RULE if hs6 else None,
        rule_verified=False,
        alternatives=[
            AlternativeResult(
                criteria=RULE.alternatives[0],
                met=maxnom_ok,
                checks=[CheckResult(name="MAXNOM 50%", passed=maxnom_ok, detail="synthetic", line_ids=["L2"])],
            )
        ]
        if hs6
        else [],
        general_checks=[
            CheckResult(name="insufficient processing", passed=True, detail="synthetic"),
            CheckResult(
                name="direct transport",
                passed=None if transit else True,
                detail="goods travel through DE: keep non-manipulation evidence" if transit else "no transit",
            ),
        ],
        lines=[
            LineAssessment(line_id="L1", originating=True, reason="CH", hs6="850152", value_chf=400.0),
            LineAssessment(line_id="L2", originating=False, reason="DE", hs6="732510", value_chf=l2_value),
        ],
        nom_value_chf=l2_value,
        nom_pct=nom_pct,
        threshold_pct=50.0 if hs6 else None,
        margin_pct=round(50.0 - nom_pct, 2) if hs6 else None,
        reasons=[f"Verdict {status.value}: synthetic."],
        fixes=["Alternative 1 (MAXNOM 50%): re-source line L2 (CHF 700.00) from a CH/CN supplier."]
        if status is VerdictStatus.FAIL
        else [],
    )
    return product, verdict


class FakeLLM:
    """Canned replies per prompt (explanation / letter / back-translation); raises LLMUnavailable when empty."""

    def __init__(self, explain: list = (), letter: list = (), back: list = ()):
        self.queues = {
            prompts.EXPLAIN_SYSTEM: list(explain),
            prompts.LETTER_SYSTEM: list(letter),
            prompts.BACK_SYSTEM: list(back),
        }
        self.calls: list[dict] = []

    def chat(self, messages, role="large", temperature=0.0, max_tokens=800, tag=""):
        self.calls.append({"messages": messages, "role": role, "temperature": temperature, "tag": tag})
        queue = self.queues[messages[0]["content"]]
        if not queue:
            raise LLMUnavailable("fake: no canned reply")
        return LLMResult(
            text=queue.pop(0), source="replay", model="fake", prompt_tokens=1, completion_tokens=1, latency_s=0.0
        )

    def calls_for(self, system: str) -> list[dict]:
        return [c for c in self.calls if c["messages"][0]["content"] == system]


GOOD_EXPLANATION = (
    "Verdict: PASS. Pump CP-200 (HS 8413.70) qualifies as originating under rule TEST-8413-MAXNOM50. "
    "Non-originating materials are 47.3% of the ex-works price of CHF 1,250.00, below the maximum of 50%. "
    "That leaves 2.7 percentage points of headroom. The rule encoding still has to be verified."
)
WRONG_NUMBER_EXPLANATION = GOOD_EXPLANATION.replace("47.3%", "47.5%")
GOOD_LETTER = (
    "尊敬的[进口商名称]：\n\n我司向贵司出口的产品“Pump CP-200”（HS编码：8413.70）符合中瑞自贸协定的原产地规则，"
    "适用的产品特定原产地规则为：非原产材料价值不超过出厂价的50%。本批货物将随附由经核准出口商出具的原产地声明，"
    "贵司可申请适用协定税率。\n\n此致\n敬礼！\n\n[出口商名称]\n[日期]"
)
GOOD_BACK = (
    'Dear [Importer name],\n\nThe product "Pump CP-200" (HS code: 8413.70) that we export to your company meets the '
    "rules of origin of the China-Switzerland FTA; the applicable product-specific rule is: non-originating "
    "materials not exceeding 50% of the ex-works price. This shipment will be accompanied by an origin declaration "
    "made out by an approved exporter, and your company may apply for the FTA tariff rate.\n\nYours faithfully,\n\n"
    "[Exporter name]\n[Date]"
)
PREFERENCE_LETTER_FOR_FAIL = (
    "尊敬的[进口商名称]：\n\n产品“Pump CP-200”（HS编码：8413.70）符合中瑞自贸协定。本批货物将随附原产地证书，"
    "贵司可申请适用协定税率。\n\n此致\n敬礼！"
)


def all_found(text) -> bool:
    return all(c.found for c in text.fact_checks)


# ---------------------------------------------------------------------------
# Facts and checks
# ---------------------------------------------------------------------------


def test_extract_facts_formats():
    product, verdict = make_case()
    facts = extract_facts(product, verdict)
    assert facts == {
        "product": "Pump CP-200",
        "status": "PASS",
        "hs6": "8413.70",
        "hs6_digits": "841370",
        "nom_pct": "47.3",
        "threshold": "50",
        "margin": "2.7",
        "rule_id": "TEST-8413-MAXNOM50",
        "ex_works": "1250",
    }


def test_extract_facts_without_hs_or_rule():
    product, verdict = make_case(VerdictStatus.UNSURE, hs6=None)
    facts = extract_facts(product, verdict)
    assert {"hs6", "hs6_digits", "threshold", "margin", "rule_id"}.isdisjoint(facts)
    assert facts["status"] == "UNSURE"


@pytest.mark.parametrize("text", ["47.3%", "47,3 %", "share 47.30 percent", "４７．３％", "(47.3)"])
def test_check_facts_number_formats_match(text):
    [check] = check_facts(text, {"nom_pct": "47.3"}, ["nom_pct"])
    assert check.found


@pytest.mark.parametrize("text", ["47.32%", "473%", "4.73%", "47%"])
def test_check_facts_rejects_other_numbers(text):
    assert not check_facts(text, {"nom_pct": "47.3"}, ["nom_pct"])[0].found


@pytest.mark.parametrize(
    ("text", "found"),
    [("HS 8413.70", True), ("HS 841370", True), ("8413 70", True), ("line 8413.70.99", True), ("8413.71", False)],
)
def test_check_facts_hs_code_forms(text, found):
    facts = {"hs6": "8413.70", "hs6_digits": "841370"}
    assert [c.found for c in check_facts(text, facts, ["hs6", "hs6_digits"])] == [found, found]


@pytest.mark.parametrize("text", ["CHF 1'250.00", "CHF 1,250.00", "CHF 1250", "CHF 1.250,00", "CHF 1\u202f250"])
def test_check_facts_amount_formats(text):
    assert check_facts(text, {"ex_works": "1250"}, ["ex_works"])[0].found


def test_check_facts_words_and_signs():
    facts = {"status": "FAIL", "margin": "-6", "product": "Pump CP-200"}
    text = "Verdict: FAIL for pump  cp-200, 6 points over the limit."
    assert all(c.found for c in check_facts(text, facts, ["status", "margin", "product"]))
    assert not check_facts("The product fails.", facts, ["status"])[0].found


def test_ungrounded_numbers_and_grounding_check():
    source = '{"nom_pct": "47.3", "hs6": "8413.70", "ex_works": "1250"}'
    assert ungrounded_numbers("47,3 % of CHF 1'250.00, HS 8413.70, since 2014", source) == ["2014"]
    assert grounding_check("47.30% of CHF 1,250", source).found
    assert not grounding_check("in force since 2014", source).found


def test_glossary_check():
    product, verdict = make_case()
    assert all(c.found for c in glossary_check(templates.letter_zh(product, verdict)))
    checks = {c.fact: c.found for c in glossary_check("根据中华人民共和国和瑞士联邦自由贸易协定，随附原产地证书。")}
    assert checks == {"agreement": True, "proof_of_origin": True, "fta_rate": False}


def test_no_preference_check():
    assert not no_preference_check("本批货物将随附原产地证书。贵司可申请适用协定税率。", "zh").found
    assert no_preference_check("本批货物不能随附原产地证书，贵司无法申请适用协定税率。", "zh").found
    assert not no_preference_check("Your company may apply for the FTA tariff rate.", "en").found
    assert no_preference_check("Your company cannot apply for the FTA (conventional) tariff rate.", "en").found


# ---------------------------------------------------------------------------
# Generation, regeneration and fallback
# ---------------------------------------------------------------------------


def test_happy_path_uses_model_texts():
    product, verdict = make_case()
    llm = FakeLLM(explain=[GOOD_EXPLANATION], letter=[GOOD_LETTER], back=[GOOD_BACK])
    dossier = build_dossier(product, verdict, llm, TARIFFS)

    for text, expected in (
        (dossier.explanation_en, GOOD_EXPLANATION),
        (dossier.letter_zh, GOOD_LETTER),
        (dossier.back_translation_en, GOOD_BACK),
    ):
        assert (text.text, text.llm_source, text.attempts) == (expected, "replay", 1)
        assert all_found(text)
    assert dossier.explanation_de.llm_source == "template" and all_found(dossier.explanation_de)
    assert [c["role"] for c in llm.calls] == ["large", "large", "small"]
    assert all(c["temperature"] == 0.0 for c in llm.calls)
    assert dossier.duty is not None and dossier.duty.duty_saved_chf == 1000.0  # 10 x 1250 x 8 %
    assert dossier.verdict_status is VerdictStatus.PASS


def test_regenerates_once_after_wrong_number():
    product, verdict = make_case()
    llm = FakeLLM(explain=[WRONG_NUMBER_EXPLANATION, GOOD_EXPLANATION])
    text = build_dossier(product, verdict, llm).explanation_en

    assert (text.text, text.llm_source, text.attempts) == (GOOD_EXPLANATION, "replay", 2)
    retry = llm.calls_for(prompts.EXPLAIN_SYSTEM)[1]["messages"]
    assert retry[2] == {"role": "assistant", "content": WRONG_NUMBER_EXPLANATION}
    assert "nom_pct: expected 47.3" in retry[3]["content"]


def test_template_after_two_failures():
    product, verdict = make_case()
    llm = FakeLLM(explain=[WRONG_NUMBER_EXPLANATION, WRONG_NUMBER_EXPLANATION])
    text = build_dossier(product, verdict, llm).explanation_en

    assert (text.llm_source, text.attempts) == ("template", 3)
    assert text.text == templates.explanation_en(product, verdict)
    assert all_found(text)
    assert len(llm.calls_for(prompts.EXPLAIN_SYSTEM)) == 2


@pytest.mark.parametrize("status", list(VerdictStatus))
def test_llm_unavailable_gives_templates(status):
    product, verdict = make_case(status)
    for llm in (FakeLLM(), None):
        dossier = build_dossier(product, verdict, llm)
        texts = (dossier.explanation_en, dossier.explanation_de, dossier.letter_zh, dossier.back_translation_en)
        assert all(t.llm_source == "template" and t.attempts == 1 and all_found(t) for t in texts)
        assert dossier.letter_zh.text == templates.letter_zh(product, verdict)
        assert dossier.back_translation_en.text == templates.letter_en(product, verdict)
        assert "ß" not in dossier.explanation_de.text


def test_fail_letter_must_not_claim_preference():
    product, verdict = make_case(VerdictStatus.FAIL)
    llm = FakeLLM(letter=[PREFERENCE_LETTER_FOR_FAIL, PREFERENCE_LETTER_FOR_FAIL])
    dossier = build_dossier(product, verdict, llm)
    letter = dossier.letter_zh

    assert (letter.llm_source, letter.attempts) == ("template", 3)
    assert "不能申请适用中瑞自贸协定项下的协定税率" in letter.text
    assert {c.fact: c.found for c in letter.fact_checks}["no_preference_claim"]
    assert "cannot apply for the FTA" in dossier.back_translation_en.text
    retry = llm.calls_for(prompts.LETTER_SYSTEM)[1]["messages"][3]["content"]
    assert "no_preference_claim" in retry


def test_unverifiable_back_translation_replaces_model_letter():
    product, verdict = make_case()
    wrong_back = GOOD_BACK.replace("8413.70", "8413.90")
    dossier = build_dossier(product, verdict, FakeLLM(letter=[GOOD_LETTER], back=[wrong_back, wrong_back]))

    assert dossier.letter_zh.llm_source == "template" and dossier.letter_zh.attempts == 2
    assert dossier.letter_zh.text == templates.letter_zh(product, verdict)
    assert dossier.back_translation_en.llm_source == "template"
    assert dossier.back_translation_en.text == templates.letter_en(product, verdict)


def test_prompts_are_stable_for_replay():
    product, verdict = make_case()
    first, second = FakeLLM(), FakeLLM()
    build_dossier(product, verdict, first)
    build_dossier(product, verdict, second)
    assert [c["messages"] for c in first.calls] == [c["messages"] for c in second.calls]
    assert "47.3" in first.calls[0]["messages"][1]["content"]
    letter_prompt = first.calls_for(prompts.LETTER_SYSTEM)[0]["messages"][1]["content"]
    assert "1250" not in letter_prompt  # no cost data in the buyer letter facts


# ---------------------------------------------------------------------------
# Templates and checklist
# ---------------------------------------------------------------------------


def test_german_template_is_swiss_formal():
    product, verdict = make_case()
    text = templates.explanation_de(product, verdict)
    assert text.startswith("Ergebnis: PASS.")
    assert "47,3 %" in text and "CHF 1'250.00" in text and "ß" not in text


def test_templates_handle_missing_hs():
    product, verdict = make_case(VerdictStatus.UNSURE, hs6=None)
    assert "HS编码：待定" in templates.letter_zh(product, verdict)
    assert "classify it first" in templates.explanation_en(product, verdict)


def test_checklist_varies_by_status():
    lists = {s: build_dossier(*make_case(s), None).checklist for s in VerdictStatus}
    assert lists[VerdictStatus.PASS][0].startswith("Proof of origin")
    assert any("approved exporter" in item for item in lists[VerdictStatus.PASS])
    assert lists[VerdictStatus.FAIL][0].startswith("Do not issue")
    assert any(item.startswith("Fix option: Alternative 1") for item in lists[VerdictStatus.FAIL])
    assert any(item.startswith("Open point - direct transport") for item in lists[VerdictStatus.UNSURE])
    not_pass = lists[VerdictStatus.FAIL] + lists[VerdictStatus.UNSURE]
    assert not any(item.startswith("Proof of origin") for item in not_pass)
    assert all(any("calculation records" in item for item in items) for items in lists.values())
    assert any("L1" in item and "Supplier evidence" in item for item in lists[VerdictStatus.PASS])
