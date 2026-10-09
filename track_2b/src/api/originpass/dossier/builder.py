"""Export dossier: explanation (EN by Apertus, DE template), Chinese buyer letter + back-translation, checklist, duty.

Every model text is validated deterministically (validator) against the facts the engine computed:
- explanation_en: required facts present and every number grounded in the facts block;
- letter_zh: product and HS code, required PRC customs terms, numbers grounded, and for FAIL/UNSURE no
  sentence that claims the FTA rate or a proof of origin;
- back_translation_en: the same facts and numbers as the letter, and the same negative statement.
A text that fails is regenerated once with the failed checks listed; after a second failure, or when no
model answers, the deterministic template is used. A model letter whose back-translation cannot be
verified is replaced by the template letter, so the English counterpart always matches the Chinese.

`attempts` counts generation attempts, the final template included (template only = 1; two failed
model attempts then template = 3).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Literal

from openai import OpenAIError

from ..llm import LLMClient, LLMUnavailable
from ..models import Dossier, DossierText, FactCheck, Product, Verdict, VerdictStatus
from ..tariffs import estimate_duty
from . import prompts, templates
from .checklist import build_checklist
from .facts import explanation_facts, facts_json, letter_facts
from .validator import check_facts, extract_facts, glossary_check, grounding_check, no_preference_check

log = logging.getLogger(__name__)

# "No model answer": no key / replay-cache miss, or the endpoint still failing after the client's retries.
_LLM_DOWN = (LLMUnavailable, OpenAIError)
MAX_MODEL_ATTEMPTS = 2

Validate = Callable[[str], list[FactCheck]]


def build_dossier(product: Product, verdict: Verdict, llm: LLMClient | None, tariffs: dict | None = None) -> Dossier:
    """Assemble the dossier for one product and its verdict; works without a model (templates only)."""
    facts = extract_facts(product, verdict)
    explain_block = facts_json(explanation_facts(product, verdict))
    letter_block = facts_json(letter_facts(product, verdict))
    explain_required = _present(facts, ["status", "hs6", "nom_pct", "threshold"])
    letter_required = _present(facts, ["product", "hs6"])
    preference = verdict.status is VerdictStatus.PASS

    def check_explanation(text: str) -> list[FactCheck]:
        return [*check_facts(text, facts, explain_required), grounding_check(text, explain_block)]

    def check_letter(text: str) -> list[FactCheck]:
        checks = [
            *check_facts(text, facts, letter_required),
            *glossary_check(text),
            grounding_check(text, letter_block),
        ]
        return checks if preference else [*checks, no_preference_check(text, "zh")]

    def check_back(text: str, letter: str) -> list[FactCheck]:
        checks = [*check_facts(text, facts, letter_required), grounding_check(text, letter)]
        return checks if preference else [*checks, no_preference_check(text, "en")]

    explanation_en = _generate(
        llm,
        lang="en",
        role="large",
        messages=_messages(prompts.EXPLAIN_SYSTEM, prompts.EXPLAIN_USER.format(facts=explain_block)),
        max_tokens=prompts.EXPLAIN_MAX_TOKENS,
        tag="dossier.explain",
        retry=prompts.RETRY_USER,
        validate=check_explanation,
        template=templates.explanation_en(product, verdict),
    )
    german = templates.explanation_de(product, verdict)
    explanation_de = DossierText(lang="de", text=german, llm_source="template", fact_checks=check_explanation(german))

    letter_zh = _generate(
        llm,
        lang="zh",
        role="large",
        messages=_messages(prompts.LETTER_SYSTEM, prompts.LETTER_USER.format(facts=letter_block)),
        max_tokens=prompts.LETTER_MAX_TOKENS,
        tag="dossier.letter",
        retry=prompts.RETRY_USER,
        validate=check_letter,
        template=templates.letter_zh(product, verdict),
    )
    letter_zh, back_translation_en = _back_translate(llm, letter_zh, check_letter, check_back, product, verdict)

    duty = None
    if tariffs and product.hs6:
        duty = estimate_duty(product.hs6, product.ex_works_chf * product.shipment.order_quantity, tariffs)

    return Dossier(
        product_id=product.product_id,
        verdict_status=verdict.status,
        explanation_en=explanation_en,
        explanation_de=explanation_de,
        letter_zh=letter_zh,
        back_translation_en=back_translation_en,
        checklist=build_checklist(product, verdict),
        duty=duty,
    )


def _back_translate(
    llm: LLMClient | None,
    letter: DossierText,
    check_letter: Validate,
    check_back: Callable[[str, str], list[FactCheck]],
    product: Product,
    verdict: Verdict,
) -> tuple[DossierText, DossierText]:
    """(letter, back-translation); a template letter gets its exact English counterpart without a model call."""
    english = templates.letter_en(product, verdict)
    if letter.llm_source == "template":
        return letter, _template_text("en", english, check_back(english, letter.text))

    back = _generate(
        llm,
        lang="en",
        role="small",
        messages=_messages(prompts.BACK_SYSTEM, prompts.BACK_USER.format(letter=letter.text)),
        max_tokens=prompts.BACK_MAX_TOKENS,
        tag="dossier.back_translate",
        retry=prompts.BACK_RETRY_USER,
        validate=lambda text: check_back(text, letter.text),
        template=english,
    )
    if back.llm_source != "template":
        return letter, back
    # The model letter could not be verified through its back-translation: ship the template pair instead.
    zh = templates.letter_zh(product, verdict)
    fallback = DossierText(
        lang="zh", text=zh, llm_source="template", fact_checks=check_letter(zh), attempts=letter.attempts + 1
    )
    return fallback, _template_text("en", english, check_back(english, zh), back.attempts)


def _generate(
    llm: LLMClient | None,
    *,
    lang: str,
    role: Literal["large", "small"],
    messages: list[dict],
    max_tokens: int,
    tag: str,
    retry: str,
    validate: Validate,
    template: str,
) -> DossierText:
    """Model text that passes `validate` within MAX_MODEL_ATTEMPTS, else the template."""
    attempts = 0
    while llm is not None and attempts < MAX_MODEL_ATTEMPTS:
        try:
            res = llm.chat(messages, role=role, temperature=0.0, max_tokens=max_tokens, tag=tag)
        except _LLM_DOWN as exc:
            log.info("%s: no model answer, using the template: %s", tag, exc)
            break
        attempts += 1
        text = res.text.strip()
        checks = validate(text)
        if text and all(c.found for c in checks):
            return DossierText(lang=lang, text=text, llm_source=res.source, fact_checks=checks, attempts=attempts)
        log.info("%s: attempt %d failed checks %s", tag, attempts, [c.fact for c in checks if not c.found])
        messages = [
            *messages,
            {"role": "assistant", "content": res.text},
            {"role": "user", "content": retry.format(failures=_failures(checks))},
        ]
    return _template_text(lang, template, validate(template), attempts + 1)


def _template_text(lang: str, text: str, checks: list[FactCheck], attempts: int = 1) -> DossierText:
    return DossierText(lang=lang, text=text, llm_source="template", fact_checks=checks, attempts=attempts)


def _failures(checks: list[FactCheck]) -> str:
    return "\n".join(f"- {c.fact}: expected {c.expected}" for c in checks if not c.found) or "- the reply was empty"


def _messages(system: str, user: str) -> list[dict]:
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _present(facts: dict[str, str], keys: list[str]) -> list[str]:
    return [k for k in keys if k in facts]
