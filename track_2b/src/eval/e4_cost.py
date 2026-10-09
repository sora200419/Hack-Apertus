"""E4: cost and latency. Measured from the calls E1-E3 made in this process, projected per 1,000 units.

Measured: the client's cost log (every answered call, live or replayed with its recorded token counts and
latency) by model, and per experiment from the call trackers: CHF per classified BOM line and per dossier.

Projected (clearly a projection): CHF per 1,000 BOM lines (rewrite + rerank) and per 1,000 dossiers
(explanation + letter + back-translation, first attempt only) for three settings: every call on Apertus
8B, every call on 70B, and the roles the code uses. Token counts per call type are the measured means when
answered calls exist. Otherwise they are ESTIMATED from the actual prompts (attempted calls, or prompts
rebuilt from the gold set and demo templates) at ASSUMED_CHARS_PER_TOKEN Latin characters or one CJK
character per token, with the completion at its max_tokens cap (an upper bound). Prices: llm/cost.py.
"""

from __future__ import annotations

import inspect
import math
from collections import defaultdict
from pathlib import Path

from originpass.dossier import prompts as dossier_prompts
from originpass.dossier import templates
from originpass.engine.origin import evaluate
from originpass.hs import prompts as hs_prompts
from originpass.hs.classifier import classify, rerank_messages
from originpass.hs.index import HSIndex
from originpass.llm import LLMClient
from originpass.llm.cost import PRICES_USD_PER_M, price_for
from originpass.models import RulePack

from .demos import load_demos
from .gold import load_gold
from .util import CallRecord, TrackedLLM, char_counts, ratio

ASSUMED_CHARS_PER_TOKEN = 4.0
BOM_LINE_TAGS = ("hs_rewrite", "hs_rerank")
DOSSIER_TAGS = ("dossier.explain", "dossier.letter", "dossier.back_translate")
# Roles hard-wired in the dossier builder and the classifier's rewrite step; the rerank role is the
# default of classify(), as used by the API.
CODE_ROLES = {
    "hs_rewrite": "small",
    "hs_rerank": inspect.signature(classify).parameters["role"].default,
    "dossier.explain": "large",
    "dossier.letter": "large",
    "dossier.back_translate": "small",
}
MAX_TOKENS = {
    "hs_rewrite": hs_prompts.REWRITE_MAX_TOKENS,
    "hs_rerank": hs_prompts.RERANK_MAX_TOKENS,
    "dossier.explain": dossier_prompts.EXPLAIN_MAX_TOKENS,
    "dossier.letter": dossier_prompts.LETTER_MAX_TOKENS,
    "dossier.back_translate": dossier_prompts.BACK_MAX_TOKENS,
}
REBUILT_SAMPLE = 20


def estimate_tokens(latin_chars: float, cjk_chars: float) -> int:
    return math.ceil(latin_chars / ASSUMED_CHARS_PER_TOKEN + cjk_chars)


def chf(records: list[CallRecord], usd_to_chf: float) -> float:
    usd = sum(
        (r.prompt_tokens * price_for(r.model)[0] + r.completion_tokens * price_for(r.model)[1]) / 1e6 for r in records
    )
    return round(usd * usd_to_chf, 6)


def token_profile(tag: str, records: list[CallRecord], rebuilt: dict[str, list[tuple[int, int]]]) -> dict:
    """Mean prompt/completion tokens of one call type: measured, else estimated from prompt characters."""
    answered = [r for r in records if r.tag == tag and r.answered]
    if answered:
        return {
            "basis": f"measured ({len(answered)} answered calls)",
            "prompt_tokens": round(sum(r.prompt_tokens for r in answered) / len(answered), 1),
            "completion_tokens": round(sum(r.completion_tokens for r in answered) / len(answered), 1),
        }
    attempted = [(r.prompt_chars_latin, r.prompt_chars_cjk) for r in records if r.tag == tag]
    basis = f"estimated from {len(attempted)} attempted prompts"
    if not attempted:
        attempted = rebuilt.get(tag, [])
        basis = f"estimated from {len(attempted)} rebuilt prompts"
    if not attempted:
        return {"basis": "no estimate", "prompt_tokens": None, "completion_tokens": None}
    latin = sum(a for a, _ in attempted) / len(attempted)
    cjk = sum(c for _, c in attempted) / len(attempted)
    return {
        "basis": f"{basis}; completion = max_tokens cap {MAX_TOKENS[tag]} (assumption)",
        "prompt_tokens": estimate_tokens(latin, cjk),
        "completion_tokens": MAX_TOKENS[tag],
    }


def rebuilt_prompts(index: HSIndex, data_dir: Path, pack: RulePack) -> dict[str, list[tuple[int, int]]]:
    """(Latin, CJK) prompt characters of calls that may never be attempted without a model answer."""
    texts = [it.text for it in load_gold(data_dir) if it.subset == "main" and it.split == "test"][:REBUILT_SAMPLE]
    rerank = [rerank_messages(t, None, index.fuse([t], k=10).candidates, index) for t in texts]
    back = [
        [
            {"role": "system", "content": dossier_prompts.BACK_SYSTEM},
            {
                "role": "user",
                "content": dossier_prompts.BACK_USER.format(letter=templates.letter_zh(p, evaluate(p, pack))),
            },
        ]
        for p in load_demos(data_dir).values()
    ]
    return {"hs_rerank": [char_counts(m) for m in rerank], "dossier.back_translate": [char_counts(m) for m in back]}


def projection(
    profiles: dict[str, dict], tags: tuple[str, ...], usd_to_chf: float, model_for_role: dict[str, str]
) -> dict:
    """CHF per 1,000 units for 8B-only, 70B-only and the code's roles; None if a call type has no estimate."""
    if any(profiles[t]["prompt_tokens"] is None for t in tags):
        return {"8b_only": None, "70b_only": None, "code_roles": None}

    def cost(prices: dict[str, tuple[float, float]]) -> float:
        usd = sum(
            profiles[t]["prompt_tokens"] * prices[t][0] + profiles[t]["completion_tokens"] * prices[t][1] for t in tags
        )
        return round(1000 * usd / 1e6 * usd_to_chf, 4)

    return {
        "8b_only": cost({t: PRICES_USD_PER_M["8b"] for t in tags}),
        "70b_only": cost({t: PRICES_USD_PER_M["70b"] for t in tags}),
        "code_roles": cost({t: price_for(model_for_role[CODE_ROLES[t]]) for t in tags}),
    }


def run(
    client: LLMClient,
    trackers: dict[str, TrackedLLM],
    units: dict[str, int],
    index: HSIndex,
    data_dir: Path,
    pack: RulePack,
) -> dict:
    """`trackers`: experiment name -> tracker; `units`: experiment name -> answered BOM lines or dossiers."""
    usd_to_chf = client.settings.usd_to_chf
    per_experiment = {}
    for name, tracker in trackers.items():
        answered = [c for c in tracker.calls if c.answered]
        cost = chf(answered, usd_to_chf)
        per_experiment[name] = {
            "calls_attempted": len(tracker.calls),
            "calls_answered": len(answered),
            "prompt_tokens": sum(c.prompt_tokens for c in answered),
            "completion_tokens": sum(c.completion_tokens for c in answered),
            "cost_chf": cost,
            "units_answered": units.get(name, 0),
            "chf_per_unit": ratio(cost, units.get(name, 0), 6) if answered else None,
        }

    records = [c for t in trackers.values() for c in t.calls]
    rebuilt = rebuilt_prompts(index, data_dir, pack)
    profiles = {tag: token_profile(tag, records, rebuilt) for tag in (*BOM_LINE_TAGS, *DOSSIER_TAGS)}
    roles = {"small": client.model_for("small"), "large": client.model_for("large")}
    by_tag: dict[str, int] = defaultdict(int)
    for c in records:
        by_tag[c.tag] += 1
    return {
        "measured": {
            "cost_log": client.cost_log.summary(),
            "per_experiment": per_experiment,
            "calls_by_tag": dict(sorted(by_tag.items())),
        },
        "projection": {
            "label": "PROJECTION, not a measurement: token counts per call type as stated in 'token_profiles'",
            "assumptions": {
                "chars_per_token": ASSUMED_CHARS_PER_TOKEN,
                "cjk_chars_per_token": 1,
                "completion_tokens_if_unmeasured": "max_tokens cap of the call (upper bound)",
                "dossier_attempts": 1,
                "usd_to_chf": usd_to_chf,
                "prices_usd_per_m_tokens": PRICES_USD_PER_M,
                "code_roles": {t: f"{CODE_ROLES[t]} ({roles[CODE_ROLES[t]]})" for t in CODE_ROLES},
            },
            "token_profiles": profiles,
            "chf_per_1000_bom_lines": projection(profiles, BOM_LINE_TAGS, usd_to_chf, roles),
            "chf_per_1000_dossiers": projection(profiles, DOSSIER_TAGS, usd_to_chf, roles),
        },
    }
