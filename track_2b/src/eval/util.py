"""Shared helpers for the evaluation: an LLM call tracker, Wilson intervals, rounding, Markdown tables."""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from functools import partial

from openai import OpenAIError
from originpass.llm import LLMClient, LLMResult, LLMUnavailable
from originpass.llm.client import Role

# "No model answer", as in originpass.hs.classifier and originpass.dossier.builder.
LLM_DOWN = (LLMUnavailable, OpenAIError)
_CJK = re.compile(r"[\u3000-\u303f\u3400-\u9fff\uf900-\ufaff\uff00-\uffef]")


@dataclass(frozen=True)
class CallRecord:
    """One attempted model call. Token fields are 0 when the call got no answer."""

    tag: str
    role: str
    model: str
    max_tokens: int
    prompt_chars_latin: int
    prompt_chars_cjk: int
    answered: bool
    source: str = "none"
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_s: float = 0.0


@dataclass
class TrackedLLM:
    """Wraps an LLMClient for one experiment: records every attempted call, answered or not.

    It has the `chat` signature the classifier and dossier builder use, so it is passed in place of the
    client. Unanswered calls (replay-cache miss, endpoint down) re-raise, so the pipeline falls back
    exactly as it would in production; the record tells E1-E4 how many cache entries were missing.
    """

    client: LLMClient
    calls: list[CallRecord] = field(default_factory=list)

    def chat(
        self,
        messages: list[dict],
        role: Role = "large",
        temperature: float = 0.0,
        max_tokens: int = 800,
        tag: str = "",
    ) -> LLMResult:
        latin, cjk = char_counts(messages)
        record = partial(
            CallRecord, tag=tag, role=role, max_tokens=max_tokens, prompt_chars_latin=latin, prompt_chars_cjk=cjk
        )
        try:
            res = self.client.chat(messages, role=role, temperature=temperature, max_tokens=max_tokens, tag=tag)
        except LLM_DOWN:
            self.calls.append(record(model=self.client.model_for(role), answered=False))
            raise
        self.calls.append(
            record(
                model=res.model,
                answered=True,
                source=res.source,
                prompt_tokens=res.prompt_tokens,
                completion_tokens=res.completion_tokens,
                latency_s=res.latency_s,
            )
        )
        return res

    def misses(self) -> int:
        return sum(not c.answered for c in self.calls)

    def misses_by_tag(self) -> dict[str, int]:
        return dict(sorted(Counter(c.tag for c in self.calls if not c.answered).items()))


def char_counts(messages: list[dict]) -> tuple[int, int]:
    """(non-CJK, CJK) characters in the message contents (the basis of E4's token estimates)."""
    text = "".join(str(m.get("content", "")) for m in messages)
    cjk = len(_CJK.findall(text))
    return len(text) - cjk, cjk


def wilson(successes: int, n: int, z: float = 1.959964) -> tuple[float, float] | None:
    """95 % Wilson score interval for a proportion; None for n = 0."""
    if n == 0:
        return None
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return round(max(0.0, centre - half), 4), round(min(1.0, centre + half), 4)


def ratio(num: int | float, den: int | float, digits: int = 4) -> float | None:
    return round(num / den, digits) if den else None


def pct(x: float | None, digits: int = 1) -> str:
    """0.4567 -> '45.7%'; None -> 'n/a'."""
    return "n/a" if x is None else f"{100 * x:.{digits}f}%"


def md_table(header: Sequence[str], rows: Sequence[Sequence[object]]) -> str:
    """A GitHub-flavoured Markdown table."""
    out = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    out += ["| " + " | ".join("" if c is None else str(c) for c in row) + " |" for row in rows]
    return "\n".join(out)
