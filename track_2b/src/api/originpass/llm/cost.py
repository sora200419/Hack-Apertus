"""Token, latency and CHF cost accounting.

Prices are Public AI list prices for Apertus 1.5 (USD per million tokens, Oct 2026),
converted with USD_TO_CHF. They are an assumption for the cost table, not a quote.
"""

from __future__ import annotations

import statistics
import threading
from dataclasses import asdict, dataclass

from ..config import Settings

# (input, output) USD per 1M tokens
PRICES_USD_PER_M = {
    "8b": (0.10, 0.20),
    "70b": (0.82, 2.92),
}


def price_for(model: str) -> tuple[float, float]:
    m = model.lower()
    if "70b" in m:
        return PRICES_USD_PER_M["70b"]
    return PRICES_USD_PER_M["8b"]


@dataclass
class UsageRecord:
    tag: str
    role: str
    model: str
    source: str
    prompt_tokens: int
    completion_tokens: int
    latency_s: float

    @classmethod
    def from_result(cls, res, tag: str, role: str) -> "UsageRecord":
        return cls(
            tag=tag,
            role=role,
            model=res.model,
            source=res.source,
            prompt_tokens=res.prompt_tokens,
            completion_tokens=res.completion_tokens,
            latency_s=res.latency_s,
        )

    def cost_usd(self) -> float:
        pin, pout = price_for(self.model)
        return (self.prompt_tokens * pin + self.completion_tokens * pout) / 1_000_000


class CostLog:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._records: list[UsageRecord] = []
        self._lock = threading.Lock()

    def add(self, rec: UsageRecord) -> None:
        with self._lock:
            self._records.append(rec)

    def records(self) -> list[UsageRecord]:
        with self._lock:
            return list(self._records)

    def summary(self) -> dict:
        recs = self.records()
        by_model: dict[str, list[UsageRecord]] = {}
        for r in recs:
            by_model.setdefault(r.model, []).append(r)
        out = {}
        for model, rs in by_model.items():
            lat = sorted(r.latency_s for r in rs if r.latency_s)
            usd = sum(r.cost_usd() for r in rs)
            out[model] = {
                "calls": len(rs),
                "prompt_tokens": sum(r.prompt_tokens for r in rs),
                "completion_tokens": sum(r.completion_tokens for r in rs),
                "cost_usd": round(usd, 6),
                "cost_chf": round(usd * self.settings.usd_to_chf, 6),
                "latency_p50_s": round(statistics.median(lat), 3) if lat else None,
                "latency_p95_s": round(lat[min(len(lat) - 1, int(0.95 * len(lat)))], 3) if lat else None,
            }
        return {"usd_to_chf": self.settings.usd_to_chf, "prices_usd_per_m": PRICES_USD_PER_M, "by_model": out}

    def as_dicts(self) -> list[dict]:
        return [asdict(r) | {"cost_usd": r.cost_usd()} for r in self.records()]
