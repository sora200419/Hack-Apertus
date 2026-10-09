"""HS classification of free-text BOM lines: hybrid retrieval + Apertus rerank with abstention.

Pipeline of `classify`:
1. Rewrite (small model): a German/French/Italian/Chinese/English line -> concise English customs
   description + keywords. Without a usable rewrite (no model, no model answer, malformed reply) the
   static DE/FR/IT glossary (glossary.gloss) gives a word-by-word English gloss instead, if it has one.
2. Retrieve: RRF over BM25 and char n-gram TF-IDF, for the rewrite (or gloss) and the raw text (index.fuse).
3. Rerank (model role per argument): pick one numbered candidate or abstain. The code must be one of
   the candidates and the confidence must reach `min_confidence`; otherwise we abstain. When the rewrite
   failed, the gloss is shown to the model as a labelled hint (deterministic, so replay keys stay stable).
4. No model answer (LLMUnavailable / endpoint error) -> 'retrieval_only' with the margin rule below.

Retrieval-only margin rule (a conservative heuristic in rank units, not a fitted score cut-off).
Let m be the number of ranked lists (2 rankers x each distinct query text) and K the RRF constant.
The fused leader is chosen only if
  (a) every ranked list puts it first: a ranker that disagrees or found nothing means abstain; and
  (b) its fused score beats the runner-up by at least MIN_MARGIN_PER_LIST * m = m * (1/(K+1) - 1/(K+3)),
      i.e. by at least as much as if the runner-up were third in every list.
A runner-up that is second in every list is the typical signature of two sibling subheadings sharing
heading and chapter text, which lexical retrieval cannot tell apart (thresholds, "other than ..."),
so the leader must stand clear of more than one near-twin. The reported confidence is the leader's
share of the top-two fused scores, s1 / (s1 + s2): a separation statistic, not a calibrated probability.
"""

from __future__ import annotations

import ast
import json
import logging
import math
import re
import unicodedata

from openai import OpenAIError

from ..llm import LLMClient, LLMUnavailable, extract_json
from ..models import HSCandidate, HSSuggestion, Product
from . import prompts
from .glossary import gloss
from .index import RRF_K, Fusion, HSIndex, get_index, normalise_hs6

log = logging.getLogger(__name__)

# "No model answer": no key / replay-cache miss, or the endpoint still failing after the client's retries.
_LLM_DOWN = (LLMUnavailable, OpenAIError)

MIN_MARGIN_PER_LIST = 1.0 / (RRF_K + 1) - 1.0 / (RRF_K + 3)

# A code in a model reply: optional "HS" prefix, then 6 digits or an 8/10-digit national tariff line whose first
# six digits are the HS subheading ("8413.70.99" -> 841370). Dots and whitespace are removed first.
_REPLY_CODE = re.compile(r"(?:HS)?(\d{6}(?:\d{2}){0,2})", re.IGNORECASE)


def classify(
    description: str,
    llm: LLMClient | None,
    index: HSIndex | None = None,
    k: int = 10,
    role: str = "small",
    min_confidence: float = 0.5,
    chapters: list[str] | None = None,
) -> HSSuggestion:
    """Suggest one HS 2022 subheading for a free-text description, or abstain."""
    index = index if index is not None else get_index()
    # NFC: the same visible text typed on macOS (NFD) must give the same tokens and the same replay key.
    query = " ".join(unicodedata.normalize("NFC", description).split())
    rewrite: str | None = None
    source = "none"
    llm_up = llm is not None and bool(query)
    if llm_up:
        try:
            rewrite, source = _rewrite(query, llm)
        except _LLM_DOWN as exc:
            log.info("HS rewrite unavailable, retrieval only: %s", exc)
            llm_up = False

    hint = None if rewrite else gloss(query)
    fusion = index.fuse([t for t in (rewrite or hint, query) if t], k=k, chapters=chapters)
    if not fusion.candidates:
        rationale = "No HS 2022 subheading matches the description."
        return _result(query, [], None, 0.0, rationale, "retrieval_only", source)
    if llm_up:
        try:
            return _rerank(query, rewrite, fusion.candidates, llm, index, role, min_confidence, hint)
        except _LLM_DOWN as exc:
            log.info("HS rerank unavailable, retrieval only: %s", exc)
    return _retrieval_only(query, fusion, source, hint)


def classify_bom(product: Product, llm: LLMClient | None, index: HSIndex | None = None) -> dict[str, HSSuggestion]:
    """Suggestions keyed by line_id, for BOM lines that have no hs6 yet."""
    index = index if index is not None else get_index()
    return {line.line_id: classify(line.description, llm, index) for line in product.bom if line.hs6 is None}


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------


def rewrite_messages(description: str) -> list[dict]:
    return [
        {"role": "system", "content": prompts.REWRITE_SYSTEM},
        {"role": "user", "content": prompts.REWRITE_USER.format(description=description)},
    ]


def rerank_messages(
    description: str,
    rewrite: str | None,
    candidates: list[HSCandidate],
    index: HSIndex,
    glossed: str | None = None,
) -> list[dict]:
    """Rerank prompt; the glossary gloss is shown only when there is no model rewrite."""
    lines = "\n".join(
        prompts.RERANK_CANDIDATE.format(n=n, hs6=c.hs6, path=index.describe(c.hs6))
        for n, c in enumerate(candidates, start=1)
    )
    if rewrite:
        rewrite_line = prompts.RERANK_REWRITE_LINE.format(rewrite=rewrite)
    elif glossed:
        rewrite_line = prompts.RERANK_GLOSS_LINE.format(gloss=glossed)
    else:
        rewrite_line = ""
    user = prompts.RERANK_USER.format(description=description, rewrite_line=rewrite_line, candidates=lines)
    return [{"role": "system", "content": prompts.RERANK_SYSTEM}, {"role": "user", "content": user}]


# ---------------------------------------------------------------------------
# Steps
# ---------------------------------------------------------------------------


def _rewrite(query: str, llm: LLMClient) -> tuple[str | None, str]:
    """English rewrite '<description> (<kw>, <kw>)' and the reply's source; None if malformed."""
    res = llm.chat(
        rewrite_messages(query),
        role="small",
        temperature=0.0,
        max_tokens=prompts.REWRITE_MAX_TOKENS,
        tag="hs_rewrite",
    )
    data = reply_object(res.text, "en")
    en = data.get("en") if data else None
    if not isinstance(en, str) or not en.strip():
        log.info("HS rewrite reply not usable, using raw text")
        return None, res.source
    raw_keywords = data.get("keywords")
    if isinstance(raw_keywords, str):
        raw_keywords = re.split(r"[,;]", raw_keywords)
    elif not isinstance(raw_keywords, list):
        raw_keywords = []
    keywords = [kw.strip() for kw in raw_keywords if isinstance(kw, str) and kw.strip()]
    en = " ".join(en.split())
    return (f"{en} ({', '.join(keywords[:6])})" if keywords else en), res.source


def reply_object(text: str, required: str) -> dict | None:
    """The JSON object of a model reply that has the key `required`, or None.

    Accepts a bare or fenced object, an object wrapped in prose (even prose with other braces) and a
    Python-style object with single quotes. Two different objects with the key are ambiguous: None.
    """
    data = extract_json(text)
    if isinstance(data, dict) and required in data:
        return data
    found: list[dict] = []
    decoder = json.JSONDecoder()
    for start in (m.start() for m in re.finditer(r"\{", text)):
        try:
            obj = decoder.raw_decode(text, start)[0]
        except json.JSONDecodeError:
            obj = _python_object(text, start)
        if isinstance(obj, dict) and required in obj and obj not in found:
            found.append(obj)
    return found[0] if len(found) == 1 else None


def _python_object(text: str, start: int) -> object:
    """A Python literal dict starting at `start` ("{'hs6': '841370'}"), or None."""
    for end in (m.end() for m in re.finditer(r"\}", text[start:])):
        try:
            return ast.literal_eval(text[start : start + end])
        except (ValueError, SyntaxError, TypeError, MemoryError, RecursionError):
            continue
    return None


def reply_code(raw: str | int) -> str:
    """Normalised code from a model reply: '8413.70', 'HS 841370', '8413.70.99' (national line) -> '841370'.

    Anything else is returned normalised but unchanged, and then fails the candidate check (abstention).
    """
    code = normalise_hs6(unicodedata.normalize("NFKC", raw) if isinstance(raw, str) else raw)
    match = _REPLY_CODE.fullmatch(code)
    return match.group(1)[:6] if match else code


def parse_choice(text: str) -> tuple[str | None, float, str] | None:
    """(hs6 or None, confidence, rationale) from a rerank reply; None when malformed."""
    data = reply_object(text, "hs6")
    if data is None:
        return None
    raw = data["hs6"]
    if raw is None or (isinstance(raw, str) and raw.strip().lower() in ("", "null", "none")):
        hs6 = None
    elif isinstance(raw, (str, int)) and not isinstance(raw, bool):
        hs6 = reply_code(raw)
    else:
        return None
    conf = data.get("confidence", 0.0 if hs6 is None else None)
    if isinstance(conf, bool) or not isinstance(conf, (int, float, str)):
        return None
    try:
        conf = float(conf)
    except ValueError:
        return None
    if math.isnan(conf) or not 0.0 <= conf <= 1.0:
        return None
    rationale = " ".join(str(data.get("rationale") or "").split()[: prompts.RATIONALE_MAX_WORDS])
    return hs6, conf, rationale


def _rerank(
    query: str,
    rewrite: str | None,
    candidates: list[HSCandidate],
    llm: LLMClient,
    index: HSIndex,
    role: str,
    min_confidence: float,
    glossed: str | None = None,
) -> HSSuggestion:
    res = llm.chat(
        rerank_messages(query, rewrite, candidates, index, glossed),
        role=role,
        temperature=0.0,
        max_tokens=prompts.RERANK_MAX_TOKENS,
        tag="hs_rerank",
    )

    def done(chosen: str | None, confidence: float, rationale: str) -> HSSuggestion:
        return _result(query, candidates, chosen, confidence, rationale, "llm", res.source)

    choice = parse_choice(res.text)
    if choice is None:
        return done(None, 0.0, "Abstained: the model reply was not valid JSON with hs6 and confidence.")
    hs6, confidence, rationale = choice
    if hs6 is None:
        return done(None, 0.0, f"Model abstained. {rationale}".strip())
    if hs6 not in {c.hs6 for c in candidates}:
        return done(None, 0.0, f"Abstained: the model proposed {hs6}, which is not a retrieved candidate.")
    if confidence < min_confidence:
        reason = f"Abstained: the model leaned to {hs6} with confidence {confidence:.2f} < {min_confidence:.2f}."
        return done(None, confidence, f"{reason} {rationale}".strip())
    return done(hs6, confidence, rationale or f"Model chose {hs6}.")


def _retrieval_only(query: str, fusion: Fusion, source: str, glossed: str | None = None) -> HSSuggestion:
    """Apply the margin rule from the module docstring (the gloss, if any, is one more query text)."""
    top, rest = fusion.candidates[0], fusion.candidates[1:]
    runner_up = rest[0].score if rest else 0.0
    margin = top.score - runner_up
    required = fusion.n_lists * MIN_MARGIN_PER_LIST
    firsts = sum(code == top.hs6 for code in fusion.top1)
    detail = (
        f"{top.hs6} is first in {firsts}/{fusion.n_lists} ranked lists and leads "
        f"{rest[0].hs6 if rest else 'no runner-up'} by {margin:.5f} in fused RRF score "
        f"(rule: first in all lists and lead >= {required:.5f})."
    )
    if glossed:
        detail += f' Queries: the raw text and its glossary gloss "{glossed}".'
    if firsts == fusion.n_lists and margin + 1e-12 >= required:
        rationale = f"Apertus unavailable; retrieval-only pick, confirm before use: {detail}"
        confidence = top.score / (top.score + runner_up)
        return _result(query, fusion.candidates, top.hs6, confidence, rationale, "retrieval_only", source)
    rationale = f"Apertus unavailable and retrieval is ambiguous, abstaining: {detail}"
    return _result(query, fusion.candidates, None, 0.0, rationale, "retrieval_only", source)


def _result(
    query: str,
    candidates: list[HSCandidate],
    chosen: str | None,
    confidence: float,
    rationale: str,
    method: str,
    source: str,
) -> HSSuggestion:
    return HSSuggestion(
        query=query,
        candidates=candidates,
        chosen=chosen,
        confidence=round(confidence, 3),
        rationale=rationale,
        abstained=chosen is None,
        method=method,
        llm_source=source,
    )
