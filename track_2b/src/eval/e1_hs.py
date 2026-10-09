"""E1: HS classification of BOM descriptions against the gold set (test split only).

Systems:
- bm25 / tfidf: top-1 of a single retrieval ranker on the raw text;
- fused: top-1 of reciprocal-rank fusion of both rankers (the classifier's retrieval stage);
- retrieval_only: the production classifier without a model (margin rule, may abstain);
- llm_small / llm_large: the production classifier with Apertus (rewrite by the small model, rerank by
  the small or large model). An item whose model calls get no answer (replay-cache miss, endpoint down)
  is not scored; the system is 'not run' when no item was answered and 'partial' when some were.

Metrics per subset: top-1 / top-3 accuracy at HS6 and HS4 (an abstention counts as wrong at top-1),
coverage (share not abstained), selective accuracy (accuracy on the non-abstained items), 95 % Wilson
interval of top-1 HS6, recall@10 of the candidate list (the reranker's ceiling), a per-language
breakdown, and cross-lingual agreement on the parallel subset. Top-3 of a classifier is its choice
followed by the retrieval candidates it would show, in order.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from originpass.hs.classifier import classify
from originpass.hs.index import HSIndex
from originpass.llm import LLMClient

from .gold import GoldItem, load_gold
from .util import TrackedLLM, ratio, wilson

RANKERS = ("bm25", "tfidf", "fused")
CLASSIFIERS = ("retrieval_only", "llm_small", "llm_large")
SYSTEMS = (*RANKERS, *CLASSIFIERS)
SUBSETS = ("main", "hscodecomp", "parallel")
K = 10


@dataclass(frozen=True)
class Prediction:
    chosen: str | None  # top-1, None = abstained / nothing retrieved
    ranked: tuple[str, ...]  # what a user would see, best first (top-k)


def ranker_codes(index: HSIndex, ranker: str, text: str, k: int = K) -> list[str]:
    """Top-k codes of one ranker on the raw text ('fused' = the classifier's RRF stage)."""
    if ranker == "fused":
        return [c.hs6 for c in index.fuse([text], k=k).candidates]
    # Single-ranker lists are internal to HSIndex; E1 reads them to isolate each ranker's contribution.
    rank = index._rank_bm25 if ranker == "bm25" else index._rank_tfidf
    return [index._codes[int(i)] for i in rank(text, None)[:k]]


def classifier_prediction(text: str, llm: TrackedLLM | None, index: HSIndex, role: str) -> tuple[Prediction, bool]:
    """(prediction, answered by the model?) of the production classifier."""
    s = classify(text, llm, index, k=K, role=role)  # type: ignore[arg-type]  # TrackedLLM duck-types LLMClient
    ranked = ([s.chosen] if s.chosen else []) + [c.hs6 for c in s.candidates if c.hs6 != s.chosen]
    return Prediction(s.chosen, tuple(ranked[:K])), s.method == "llm"


def score(items: list[GoldItem], preds: dict[str, Prediction]) -> dict:
    """Accuracy metrics over the items that have a prediction."""
    scored = [(it, preds[it.id]) for it in items if it.id in preds]
    n = len(scored)
    covered = [(it, p) for it, p in scored if p.chosen]
    top1_6 = sum(p.chosen == it.gold_hs6 for it, p in scored)
    top1_4 = sum((p.chosen or "")[:4] == it.gold_hs6[:4] for it, p in scored)
    return {
        "n": n,
        "top1_hs6": ratio(top1_6, n),
        "top1_hs6_ci95": wilson(top1_6, n),
        "top1_hs4": ratio(top1_4, n),
        "top3_hs6": ratio(sum(it.gold_hs6 in p.ranked[:3] for it, p in scored), n),
        "top3_hs4": ratio(sum(it.gold_hs6[:4] in {c[:4] for c in p.ranked[:3]} for it, p in scored), n),
        "recall_at_10": ratio(sum(it.gold_hs6 in p.ranked[:K] for it, p in scored), n),
        "coverage": ratio(len(covered), n),
        "selective_hs6": ratio(top1_6, len(covered)),
        "selective_hs4": ratio(top1_4, len(covered)),
    }


def by_language(items: list[GoldItem], preds: dict[str, Prediction]) -> dict[str, dict]:
    groups: dict[str, list[GoldItem]] = defaultdict(list)
    for it in items:
        groups[it.lang].append(it)
    out = {}
    for lang in sorted(groups):
        m = score(groups[lang], preds)
        out[lang] = {k: m[k] for k in ("n", "top1_hs6", "top1_hs4", "top3_hs6", "coverage")}
    return out


def cross_lingual(items: list[GoldItem], preds: dict[str, Prediction]) -> dict:
    """Agreement of top-1 codes across the translations of each parallel concept (abstentions disagree)."""
    concepts: dict[str, dict[str, str | None]] = defaultdict(dict)
    for it in items:
        if it.concept and it.id in preds:
            concepts[it.concept][it.lang] = preds[it.id].chosen
    langs = sorted({it.lang for it in items})
    complete = {c: v for c, v in concepts.items() if set(v) == set(langs)}
    n = len(complete)
    all_agree = sum(len(set(v.values())) == 1 and None not in v.values() for v in complete.values())
    vs_en = {
        lang: ratio(sum(v[lang] is not None and v[lang] == v["en"] for v in complete.values()), n)
        for lang in langs
        if lang != "en"
    }
    return {"concepts": n, "all_languages_agree": ratio(all_agree, n), "agree_with_en": vs_en}


def run(
    index: HSIndex, client: LLMClient | None, data_dir: Path, max_items: int | None = None
) -> tuple[dict, dict[str, TrackedLLM]]:
    """E1 results and the call trackers of the model systems (for E4), keyed 'e1.<system>'."""
    gold = load_gold(data_dir)
    test = {
        s: sorted((it for it in gold if it.subset == s and it.split == "test"), key=lambda it: it.id) for s in SUBSETS
    }
    if max_items is not None:
        test = {s: _cap(items, max_items) for s, items in test.items()}
    items = [it for s in SUBSETS for it in test[s]]

    preds: dict[str, dict[str, Prediction]] = {name: {} for name in SYSTEMS}
    for it in items:
        for ranker in RANKERS:
            codes = ranker_codes(index, ranker, it.text)
            preds[ranker][it.id] = Prediction(codes[0] if codes else None, tuple(codes))
        preds["retrieval_only"][it.id], _ = classifier_prediction(it.text, None, index, role="small")

    trackers: dict[str, TrackedLLM] = {}
    status: dict[str, dict] = {name: {"status": "run", "items": len(items)} for name in (*RANKERS, "retrieval_only")}
    for name, role in (("llm_small", "small"), ("llm_large", "large")):
        tracker = TrackedLLM(client) if client is not None else None
        unanswered = 0
        for it in items:
            pred, answered = classifier_prediction(it.text, tracker, index, role=role)
            if answered:
                preds[name][it.id] = pred
            else:
                unanswered += 1
        status[name] = _llm_status(len(items), unanswered, tracker)
        if tracker is not None:
            trackers[f"e1.{name}"] = tracker

    results = {
        "gold": _gold_counts(gold),
        "systems": status,
        "subsets": {s: {name: score(test[s], preds[name]) for name in SYSTEMS} for s in SUBSETS},
        "per_language": {
            s: {name: by_language(test[s], preds[name]) for name in SYSTEMS} for s in ("main", "parallel")
        },
        "cross_lingual": {name: cross_lingual(test["parallel"], preds[name]) for name in SYSTEMS},
        "examples": _examples(test["main"], preds),
    }
    return results, trackers


def _cap(items: list[GoldItem], n: int) -> list[GoldItem]:
    """First n items, keeping whole parallel concepts together."""
    concepts = list(dict.fromkeys(it.concept for it in items if it.concept))
    if concepts:
        keep = set(concepts[: max(1, n // 4)])
        return [it for it in items if it.concept in keep]
    return items[:n]


def _llm_status(n: int, unanswered: int, tracker: TrackedLLM | None) -> dict[str, Any]:
    out: dict[str, Any] = {"items": n, "items_answered": n - unanswered}
    if tracker is None:
        return out | {"status": "not run", "note": "no LLM client"}
    out |= {"missing_cache_entries": tracker.misses(), "missing_by_tag": tracker.misses_by_tag()}
    if unanswered == 0:
        return out | {"status": "run"}
    if unanswered == n:
        return out | {"status": "not run", "note": f"no endpoint/cache: {unanswered}/{n} items without a model answer"}
    return out | {"status": "partial", "note": f"{unanswered}/{n} items without a model answer are not scored"}


def _gold_counts(gold: list[GoldItem]) -> dict:
    counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for it in gold:
        counts[f"{it.subset}/{it.split}"][it.lang] += 1
    return {
        "file": "data/eval/hs_gold.jsonl",
        "rows": len(gold),
        "counts": {k: dict(sorted(v.items())) for k, v in sorted(counts.items())},
        "sources": sorted({it.source for it in gold}),
    }


def _examples(items: list[GoldItem], preds: dict[str, dict[str, Prediction]], n: int = 8) -> list[dict]:
    """Top-1 of every system on the first n non-English main test items (for the report)."""
    picked = [it for it in items if it.lang != "en"][:n]
    return [
        {"id": it.id, "lang": it.lang, "text": it.text, "gold": it.gold_hs6}
        | {name: (preds[name][it.id].chosen if it.id in preds[name] else "not run") for name in SYSTEMS}
        for it in picked
    ]
