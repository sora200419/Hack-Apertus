"""Runtime configuration, read from environment variables.

Template-mandated variables: LLM_NAME, LLM_BASE_URL, LLM_API_KEY.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _default_data_dir() -> Path:
    # src/api/originpass/config.py -> track_2b/data
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "data" / "hs").is_dir():
            return parent / "data"
    return Path("/data")


@dataclass(frozen=True)
class Settings:
    llm_name: str = field(default_factory=lambda: os.getenv("LLM_NAME", "swiss-ai/Apertus-v1.5-70B"))
    llm_name_small: str = field(
        default_factory=lambda: os.getenv("LLM_NAME_SMALL") or os.getenv("LLM_NAME", "swiss-ai/Apertus-v1.5-8B")
    )
    llm_base_url: str = field(default_factory=lambda: os.getenv("LLM_BASE_URL", "https://api.inference.cscs.ch/v1"))
    llm_api_key: str = field(default_factory=lambda: os.getenv("LLM_API_KEY", ""))
    # auto: live when a key is set (and record to the cache), otherwise replay
    # live: always call the endpoint; record: live + write cache; replay: never call the endpoint
    llm_mode: str = field(default_factory=lambda: os.getenv("LLM_MODE", "auto"))
    llm_timeout_s: float = field(default_factory=lambda: float(os.getenv("LLM_TIMEOUT_S", "60")))
    data_dir: Path = field(default_factory=lambda: Path(os.getenv("DATA_DIR", str(_default_data_dir()))))
    usd_to_chf: float = field(default_factory=lambda: float(os.getenv("USD_TO_CHF", "0.80")))

    @property
    def effective_mode(self) -> str:
        if self.llm_mode == "auto":
            return "record" if self.llm_api_key else "replay"
        return self.llm_mode

    @property
    def replay_path(self) -> Path:
        return self.data_dir / "replay" / "llm_cache.jsonl"


def get_settings() -> Settings:
    return Settings()
