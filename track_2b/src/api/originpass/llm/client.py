"""OpenAI-compatible Apertus client with a record/replay cache and cost logging.

- Live calls go to LLM_BASE_URL (CSCS, Public AI, Infomaniak, self-hosted vLLM...).
- Every live response is appended to data/replay/llm_cache.jsonl (record mode), so
  `make run` and `make eval` work on a clean checkout without an API key (replay mode).
- The cache key uses the model *role* (large/small), not the model name, so a judge
  pointing LLM_NAME at another Apertus host still hits the committed cache.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from ..config import Settings, get_settings
from .cost import CostLog, UsageRecord

log = logging.getLogger(__name__)

Role = Literal["large", "small"]


class LLMUnavailable(RuntimeError):
    """Raised when no live endpoint is configured and the cache has no entry."""


@dataclass
class LLMResult:
    text: str
    source: Literal["live", "replay"]
    model: str
    prompt_tokens: int
    completion_tokens: int
    latency_s: float


def cache_key(role: Role, messages: list[dict], temperature: float, max_tokens: int) -> str:
    payload = json.dumps(
        {"role": role, "messages": messages, "temperature": temperature, "max_tokens": max_tokens},
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class ReplayCache:
    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.Lock()
        self._entries: dict[str, dict] = {}
        if path.exists():
            with path.open(encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        entry = json.loads(line)
                        self._entries[entry["key"]] = entry

    def get(self, key: str) -> dict | None:
        return self._entries.get(key)

    def put(self, entry: dict) -> None:
        with self._lock:
            if entry["key"] in self._entries:
                return
            self._entries[entry["key"]] = entry
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def __len__(self) -> int:
        return len(self._entries)


class LLMClient:
    def __init__(self, settings: Settings | None = None, cost_log: CostLog | None = None):
        self.settings = settings or get_settings()
        self.cache = ReplayCache(self.settings.replay_path)
        self.cost_log = cost_log or CostLog(self.settings)
        self._client = None

    # -- public -----------------------------------------------------------
    @property
    def mode(self) -> str:
        return self.settings.effective_mode

    def model_for(self, role: Role) -> str:
        return self.settings.llm_name if role == "large" else self.settings.llm_name_small

    def chat(
        self,
        messages: list[dict],
        role: Role = "large",
        temperature: float = 0.0,
        max_tokens: int = 800,
        tag: str = "",
    ) -> LLMResult:
        """Return the model's reply. Raises LLMUnavailable in replay mode on a cache miss."""
        key = cache_key(role, messages, temperature, max_tokens)
        mode = self.mode

        if mode in ("replay", "record"):
            hit = self.cache.get(key)
            if hit is not None:
                res = LLMResult(
                    text=hit["response"],
                    source="replay",
                    model=hit.get("model", self.model_for(role)),
                    prompt_tokens=hit.get("prompt_tokens", 0),
                    completion_tokens=hit.get("completion_tokens", 0),
                    latency_s=hit.get("latency_s", 0.0),
                )
                self.cost_log.add(UsageRecord.from_result(res, tag=tag, role=role))
                return res
            if mode == "replay":
                raise LLMUnavailable(f"replay cache miss for {tag or 'call'} ({key[:12]})")

        res = self._live(messages, role, temperature, max_tokens)
        self.cost_log.add(UsageRecord.from_result(res, tag=tag, role=role))
        if mode in ("record", "live"):
            self.cache.put(
                {
                    "key": key,
                    "role": role,
                    "model": res.model,
                    "tag": tag,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "response": res.text,
                    "prompt_tokens": res.prompt_tokens,
                    "completion_tokens": res.completion_tokens,
                    "latency_s": round(res.latency_s, 3),
                    "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                }
            )
        return res

    # -- internals --------------------------------------------------------
    def _openai(self):
        if self._client is None:
            from openai import OpenAI

            if not self.settings.llm_api_key:
                raise LLMUnavailable("LLM_API_KEY is not set")
            self._client = OpenAI(
                base_url=self.settings.llm_base_url,
                api_key=self.settings.llm_api_key,
                timeout=self.settings.llm_timeout_s,
                max_retries=2,
                # Public AI requires a User-Agent; harmless elsewhere.
                default_headers={"User-Agent": "OriginPass/1.0 (Hack Apertus)"},
            )
        return self._client

    def _live(self, messages: list[dict], role: Role, temperature: float, max_tokens: int) -> LLMResult:
        model = self.model_for(role)
        t0 = time.perf_counter()
        resp = self._openai().chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        latency = time.perf_counter() - t0
        text = resp.choices[0].message.content or ""
        usage = getattr(resp, "usage", None)
        return LLMResult(
            text=text,
            source="live",
            model=model,
            prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
            latency_s=latency,
        )


def extract_json(text: str) -> dict | list | None:
    """Best-effort JSON extraction from a model reply (fenced or bare)."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
        text = text.rsplit("```", 1)[0]
    for opener, closer in (("{", "}"), ("[", "]")):
        start, end = text.find(opener), text.rfind(closer)
        if start != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                continue
    return None


_default: LLMClient | None = None


def get_client() -> LLMClient:
    global _default
    if _default is None:
        _default = LLMClient()
    return _default
