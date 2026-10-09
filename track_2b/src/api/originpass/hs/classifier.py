"""HS classification of free-text BOM lines: hybrid retrieval + Apertus rerank with abstention.

Pipeline of `classify`:
1. Rewrite (small model): a German/French/Italian/Chinese/English line -> concise English customs
   description + keywords. On a malformed reply the raw text is used alone.
2. Retrieve: RRF over BM25 and char n-gram TF-IDF, for the rewrite and the raw text (index.fuse).
3. Rerank (model role per argument): pick one numbered candidate or abstain. The code must be one of
   the candidates and the confidence must reach `min_confidence`; otherwise we abstain.
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

import logging
import math

from openai import OpenAIError

from ..llm import LLMClient, LLMUnavailable, extract_json
from ..models import HSCandidate, HSSuggestion, Product
from . import prompts
from .index import RRF_K, Fusion, HSIndex, get_index, normalise_hs6

log = logging.getLogger(__name__)

# "No model answer": no key / replay-cache miss, or the endpoint still failing after the client's retries.
_LLM_DOWN = (LLMUnavailable, OpenAIError)

MIN_MARGIN_PER_LIST = 1.0 / (RRF_K + 1) - 1.0 / (RRF_K + 3)


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
    query = " ".join(description.split())
    rewrite: str | None = None
    source = "none"
    llm_up = llm is not None and bool(query)
    if llm_up:
        try:
            rewrite, source = _rewrite(query, llm)
        except _LLM_DOWN as exc:
            log.info("HS rewrite unavailable, retrieval only: %s", exc)
            llm_up = False

    fusion = index.fuse([t for t in (rewrite, query) if t], k=k, chapters=chapters)
    if not fusion.candidates:
        rationale = "No HS 2022 subheading matches the description."
        return _result(query, [], None, 0.0, rationale, "retrieval_only", source)
    if llm_up:
        try:
            return _rerank(query, rewrite, fusion.candidates, llm, index, role, min_confidence)
        except _LLM_DOWN as exc:
            log.info("HS rerank unavailable, retrieval only: %s", exc)
    return _retrieval_only(query, fusion, source)


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


def rerank_messages(description: str, rewrite: str | None, candidates: list[HSCandidate], index: HSIndex) -> list[dict]:
    lines = "\n".join(
        prompts.RERANK_CANDIDATE.format(n=n, hs6=c.hs6, path=index.describe(c.hs6))
        for n, c in enumerate(candidates, start=1)
    )
    rewrite_line = prompts.RERANK_REWRITE_LINE.format(rewrite=rewrite) if rewrite else ""
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
    data = extract_json(res.text)
    en = data.get("en") if isinstance(data, dict) else None
    if not isinstance(en, str) or not en.strip():
        log.info("HS rewrite reply not usable, using raw text")
        return None, res.source
    raw_keywords = data.get("keywords")
    if not isinstance(raw_keywords, list):
        raw_keywords = []
    keywords = [kw.strip() for kw in raw_keywords if isinstance(kw, str) and kw.strip()]
    en = " ".join(en.split())
    return (f"{en} ({', '.join(keywords[:6])})" if keywords else en), res.source


def parse_choice(text: str) -> tuple[str | None, float, str] | None:
    """(hs6 or None, confidence, rationale) from a rerank reply; None when malformed."""
    data = extract_json(text)
    if not isinstance(data, dict) or "hs6" not in data:
        return None
    raw = data["hs6"]
    if raw is None or (isinstance(raw, str) and raw.strip().lower() in ("", "null", "none")):
        hs6 = None
    elif isinstance(raw, (str, int)) and not isinstance(raw, bool):
        hs6 = normalise_hs6(raw)
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
) -> HSSuggestion:
    res = llm.chat(
        rerank_messages(query, rewrite, candidates, index),
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


def _retrieval_only(query: str, fusion: Fusion, source: str) -> HSSuggestion:
    """Apply the margin rule from the module docstring."""
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
