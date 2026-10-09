"""Deterministic checks on generated text: required facts present, numbers grounded, terminology, no false claims.

Number matching is tolerant to formatting only ('47.3%', '47,3 %', '47.30', "1'250.00", full-width digits),
never to rounding: 47.32 does not match 47.3. Signs are ignored ('-5.2' matches '5.2 points over').
"""

from __future__ import annotations

import re
from decimal import Decimal

from ..models import FactCheck, Product, Verdict
from .facts import fmt_num, hs6_digits, hs6_dotted
from .glossary import REQUIRED_ZH

HS_KEYS = frozenset({"hs6", "hs6_digits"})

_FULLWIDTH = str.maketrans("０１２３４５６７８９．％", "0123456789.%")
_NUMBER = re.compile(r"\d+(?:[.,'\u2019\u2009\u202f]\d+)*")
_GROUP_SEPARATORS = re.compile(r"['\u2019\u2009\u202f]")
_PLAIN_NUMBER = re.compile(r"-?\d+(?:\.\d+)?")

# Sentences mentioning preference or a proof of origin; in a no-preference letter each must be negative.
_PREFERENCE_TERMS = {
    "zh": re.compile("协定税率|优惠关税|关税优惠|优惠待遇|原产地证书|原产地声明|原产地证明"),
    "en": re.compile(
        r"preferential|certificates? of origin|origin declarations?|proofs? of origin"
        r"|\b(?:fta|conventional|agreement)\)?\s+(?:\(conventional\)\s+)?(?:tariff\s+|duty\s+)?rates?\b",
        re.IGNORECASE,
    ),
}
_NEGATION = {
    "zh": re.compile("不能|无法|不可|暂不|不得|尚不|不予|未能"),
    "en": re.compile(r"\b(?:not|cannot|can't|unable|no|neither|nor|without)\b", re.IGNORECASE),
}
_SENTENCE_SPLIT = {"zh": re.compile(r"[。！？!?\n]"), "en": re.compile(r"(?<=[.!?])\s+|\n")}


def extract_facts(product: Product, verdict: Verdict) -> dict[str, str]:
    """Canonical facts as strings: product, status, hs6 ('8413.70'), hs6_digits ('841370'), nom_pct ('47.3'),
    ex_works, and when known threshold, margin, rule_id."""
    facts = {"product": product.name, "status": verdict.status.value}
    hs = hs6_digits(product, verdict)
    if hs:
        facts["hs6"] = hs6_dotted(hs)
        facts["hs6_digits"] = hs
    facts["nom_pct"] = fmt_num(verdict.nom_pct)
    if verdict.threshold_pct is not None:
        facts["threshold"] = fmt_num(verdict.threshold_pct)
    if verdict.margin_pct is not None:
        facts["margin"] = fmt_num(verdict.margin_pct)
    if verdict.rule is not None:
        facts["rule_id"] = verdict.rule.rule_id
    facts["ex_works"] = fmt_num(product.ex_works_chf)
    return facts


def check_facts(text: str, facts: dict[str, str], required: list[str]) -> list[FactCheck]:
    """One FactCheck per required key: is facts[key] stated in `text`?"""
    norm = _normalise(text)
    numbers = {v for token in _NUMBER.findall(norm) for v in number_values(token)}
    return [
        FactCheck(fact=key, expected=facts[key], found=_contains(norm, numbers, key, facts[key])) for key in required
    ]


def glossary_check(text_zh: str) -> list[FactCheck]:
    """Each required Chinese customs term (any accepted variant) must appear."""
    return [
        FactCheck(fact=name, expected=" / ".join(terms), found=any(t in text_zh for t in terms))
        for name, terms in REQUIRED_ZH.items()
    ]


def grounding_check(text: str, source: str) -> FactCheck:
    """Every number in `text` must also appear (in any formatting) in `source`, e.g. the facts block."""
    bad = ungrounded_numbers(text, source)
    expected = "only numbers from the facts" + (f" (unsupported: {', '.join(bad)})" if bad else "")
    return FactCheck(fact="numbers_grounded", expected=expected, found=not bad)


def no_preference_check(text: str, lang: str) -> FactCheck:
    """For FAIL/UNSURE letters: every sentence mentioning the FTA rate or a proof of origin must be negative."""
    claims = [
        s.strip()
        for s in _SENTENCE_SPLIT[lang].split(_normalise(text))
        if _PREFERENCE_TERMS[lang].search(s) and not _NEGATION[lang].search(s)
    ]
    expected = "no claim of preferential treatment" + (f" (claimed in: {claims[0][:80]})" if claims else "")
    return FactCheck(fact="no_preference_claim", expected=expected, found=not claims)


def ungrounded_numbers(text: str, source: str) -> list[str]:
    """Number tokens of `text` with no reading in common with any number token of `source` (unique, in order)."""
    allowed: set = set()
    for token in _NUMBER.findall(_normalise(source)):
        allowed |= _keys(token)
    bad: list[str] = []
    for token in _NUMBER.findall(_normalise(text)):
        if not _keys(token) & allowed and token not in bad:
            bad.append(token)
    return bad


def number_values(token: str) -> set[Decimal]:
    """Every plausible reading of a number token: '47,3' -> {47.3}; '1,250' -> {1250, 1.25}; "1'250.00" -> {1250}.

    The decimal separator is '.' or ',' (or absent); any other separator must split groups of 3 digits.
    """
    plain = _GROUP_SEPARATORS.sub("", token)
    return {v for sep in (".", ",", None) if (v := _reading(plain, sep)) is not None}


# ---------------------------------------------------------------------------
# internals
# ---------------------------------------------------------------------------


def _normalise(text: str) -> str:
    return text.translate(_FULLWIDTH)


def _reading(token: str, decimal_sep: str | None) -> Decimal | None:
    if decimal_sep is not None and decimal_sep in token:
        int_part, frac = token.rsplit(decimal_sep, 1)
    elif decimal_sep is None:
        int_part, frac = token, ""
    else:
        return None
    groups = re.split(r"[.,]", int_part)
    if any(len(g) != 3 for g in groups[1:]) or (frac and not frac.isdigit()):
        return None
    return Decimal("".join(groups) + (f".{frac}" if frac else ""))


def _keys(token: str) -> set:
    """Comparable keys of a number token: its readings, or its raw digits when it is not a number (8413.70.99)."""
    return set(number_values(token)) or {"#" + re.sub(r"\D", "", token)}


def _contains(text: str, numbers: set[Decimal], key: str, value: str) -> bool:
    if key in HS_KEYS:
        digits = re.sub(r"\D", "", value)
        return re.search(rf"(?<!\d){digits[:4]}[.\s]?{digits[4:]}(?!\d)", text) is not None
    if _PLAIN_NUMBER.fullmatch(value):
        return abs(Decimal(value)) in numbers
    words = r"\s+".join(re.escape(w) for w in value.split())
    return re.search(rf"(?<![A-Za-z0-9]){words}(?![A-Za-z0-9])", text, re.IGNORECASE) is not None
