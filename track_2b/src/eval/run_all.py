"""Run E1-E4 and write data/eval/results/{summary.json, results.md, run_info.json}.

    python -m eval.run_all                 # from src/api (PYTHONPATH=../ locally) or /app in Docker

summary.json holds no timestamps or durations, so a replay-mode run is byte-for-byte reproducible at a
given commit and replay cache; wall-clock data goes to run_info.json. The LLM mode comes from the
environment (LLM_MODE): `make eval` uses replay, `make eval-live` records new cache entries.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from originpass.config import Settings, get_settings
from originpass.hs.index import HSIndex
from originpass.llm import LLMClient, get_client
from originpass.rulepack.loader import DEFAULT_PACK_ID, load_rulepack
from originpass.tariffs import load_tariffs

from . import e1_hs, e2_origin, e3_dossier, e4_cost, report
from .gold import GOLD_FILE

RESULTS_DIR = Path("eval") / "results"


@dataclass(frozen=True)
class EvalConfig:
    """Sizes and seeds of one evaluation run (the defaults are the reported configuration)."""

    e1_max_items: int | None = None  # per subset; None = the whole test split
    e2_random: int = 300
    e2_rules_per_chapter: int = 3
    e2_llm_n: int = 100
    e2_sweep_per_chapter: int = 20
    e2_sweep_rules_per_chapter: int = 4
    seed: int = 2026


def run(config: EvalConfig, settings: Settings, client: LLMClient, out_dir: Path, rating_path: Path | None) -> dict:
    """Run every experiment with one client (so E4 sees all calls) and write the result files."""
    started = time.time()
    timings: dict[str, float] = {}
    data_dir = settings.data_dir
    t0 = time.perf_counter()
    index = HSIndex.load(data_dir)
    pack = load_rulepack(DEFAULT_PACK_ID, data_dir=data_dir)
    tariffs = load_tariffs(data_dir)
    timings["load"] = time.perf_counter() - t0

    t0 = time.perf_counter()
    e1, trackers = e1_hs.run(index, client, data_dir, config.e1_max_items)
    timings["e1"] = time.perf_counter() - t0

    t0 = time.perf_counter()
    e2, t2 = e2_origin.run(
        pack,
        data_dir,
        client,
        config.e2_random,
        config.seed,
        config.e2_rules_per_chapter,
        config.e2_llm_n,
        config.e2_sweep_per_chapter,
        config.e2_sweep_rules_per_chapter,
    )
    timings["e2"] = time.perf_counter() - t0

    t0 = time.perf_counter()
    e3, t3 = e3_dossier.run(pack, data_dir, client, tariffs, rating_path)
    timings["e3"] = time.perf_counter() - t0

    t0 = time.perf_counter()
    trackers |= t2 | t3
    units = {f"e1.{name}": e1["systems"][name]["items_answered"] for name in ("llm_small", "llm_large")}
    units["e2.llm_only"] = e2["llm_baseline"]["items_answered"]
    units["e3.dossier"] = len(e3["demos"])
    e4 = e4_cost.run(client, trackers, units, index, data_dir, pack)
    timings["e4"] = time.perf_counter() - t0

    summary = {
        "generated_with": {
            "mode": client.mode,
            "llm_name": settings.llm_name,
            "llm_name_small": settings.llm_name_small,
            "rulepack": pack.pack_id,
            "rulepack_sha256": _sha256(data_dir / "rulepacks" / f"{pack.pack_id}.json"),
            "gold_sha256": _sha256(data_dir / GOLD_FILE),
            "replay_cache_entries": len(client.cache),
            "commit": _git("rev-parse", "HEAD"),
            "config": asdict(config),
        },
        "e1": e1,
        "e2": e2,
        "e3": e3,
        "e4": e4,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (out_dir / "results.md").write_text(report.render(summary), encoding="utf-8")
    run_info = {
        "started_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(started)),
        "finished_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "seconds": {k: round(v, 2) for k, v in timings.items()},
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "git_dirty": bool(_git("status", "--porcelain")),
    }
    (out_dir / "run_info.json").write_text(json.dumps(run_info, indent=2) + "\n", encoding="utf-8")
    return summary


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git(*args: str) -> str | None:
    """Output of a git command in this checkout, or None (no git, not a repository, e.g. in Docker)."""
    try:
        out = subprocess.run(
            ["git", *args], cwd=Path(__file__).resolve().parent, capture_output=True, text=True, timeout=10, check=True
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=None, help="output directory (default DATA_DIR/eval/results)")
    parser.add_argument("--no-rating-sheet", action="store_true", help="do not export the E3 rating sheet")
    args = parser.parse_args()
    settings = get_settings()
    out_dir = args.out or settings.data_dir / RESULTS_DIR
    rating = None if args.no_rating_sheet else settings.data_dir / e3_dossier.RATING_FILE
    run(EvalConfig(), settings, get_client(), out_dir, rating)
    print((out_dir / "results.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
