"""run_all smoke tests on a tiny configuration: a fake model (all LLM paths) and an empty replay cache
('not run' paths, byte-identical summaries). No network: the fake answers from canned JSON and the replay
client never calls an endpoint."""

from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[2]  # local checkout: src/ holds the `eval` package
if (_SRC / "eval" / "__init__.py").exists() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from originpass.config import Settings  # noqa: E402
from originpass.llm import LLMClient, LLMResult, LLMUnavailable  # noqa: E402
from originpass.llm.cost import CostLog, UsageRecord  # noqa: E402

from eval.e3_dossier import RATING_COLUMNS  # noqa: E402
from eval.run_all import EvalConfig, run  # noqa: E402

TINY = EvalConfig(
    e1_max_items=4, e2_random=14, e2_rules_per_chapter=1, e2_llm_n=3, e2_sweep_per_chapter=1, e2_sweep_rules_per_chapter=1
)
_CANDIDATE = re.compile(r"^1\. (\d{6}):", re.MULTILINE)


class FakeLLM(LLMClient):
    """Canned replies: HS rewrite and rerank (always candidate 1), the LLM-only verdict; dossier calls miss."""

    def chat(
        self, messages: list[dict], role: str = "large", temperature: float = 0.0, max_tokens: int = 800, tag: str = ""
    ) -> LLMResult:
        user = messages[-1]["content"]
        if tag == "hs_rewrite":
            text = '{"en": "ball bearing of steel", "keywords": ["ball bearing"]}'
        elif tag == "hs_rerank":
            match = _CANDIDATE.search(user)
            text = json.dumps({"hs6": match.group(1) if match else None, "confidence": 0.9, "rationale": "fake"})
        elif tag == "e2.llm_only":
            text = '{"status": "PASS", "nom_pct": 12.5, "reason": "fake"}'
        else:
            raise LLMUnavailable(f"fake model has no reply for {tag}")
        res = LLMResult(
            text=text,
            source="replay",
            model=self.model_for(role),
            prompt_tokens=100,
            completion_tokens=20,
            latency_s=0.5,
        )  # type: ignore[arg-type]
        self.cost_log.add(UsageRecord.from_result(res, tag=tag, role=role))
        return res


def _settings(tmp: Path) -> Settings:
    # The client's replay cache lives under its own data_dir: an empty temporary one.
    return Settings(llm_mode="replay", llm_api_key="", data_dir=tmp)


def test_run_all_with_fake_model(tmp_path: Path) -> None:
    settings = Settings(llm_mode="replay", llm_api_key="")
    client = FakeLLM(settings=_settings(tmp_path), cost_log=CostLog(settings))
    rating = tmp_path / "rating.csv"
    summary = run(TINY, settings, client, tmp_path / "out", rating)

    e1, e2, e3, e4 = summary["e1"], summary["e2"], summary["e3"], summary["e4"]
    assert e1["systems"]["llm_small"]["status"] == "run"
    assert e1["subsets"]["main"]["llm_large"]["n"] == e1["subsets"]["main"]["fused"]["n"] > 0
    assert e1["subsets"]["main"]["llm_small"]["coverage"] == 1.0
    assert e1["cross_lingual"]["llm_small"]["concepts"] == 1
    assert e2["synthetic"]["random"]["n"] == 14 and e2["synthetic"]["random"]["false_pass"] == 0
    base = e2["llm_baseline"]
    assert base["status"] == "run" and base["items"] == 3 + len(e2["demos"]["table"])
    assert base["accuracy"] is not None and base["nom_pct_mae_pp"] is not None
    assert e3["template_fallbacks"] == e3["model_texts"] == 15
    assert e4["measured"]["per_experiment"]["e1.llm_small"]["chf_per_unit"] > 0
    assert e4["projection"]["token_profiles"]["hs_rerank"]["basis"].startswith("measured")
    with rating.open(encoding="utf-8", newline="") as f:
        sheet = list(csv.DictReader(f))
    assert list(sheet[0]) == RATING_COLUMNS and len(sheet) == 5
    assert "Apertus small rewrite + small rerank" in (tmp_path / "out" / "results.md").read_text(encoding="utf-8")


def test_run_all_replay_without_cache_is_reproducible(tmp_path: Path) -> None:
    settings = Settings(llm_mode="replay", llm_api_key="")
    outs = []
    for name in ("a", "b"):
        client = LLMClient(settings=_settings(tmp_path / name), cost_log=CostLog(settings))
        run(TINY, settings, client, tmp_path / name / "out", None)
        outs.append((tmp_path / name / "out" / "summary.json").read_text(encoding="utf-8"))
    assert outs[0] == outs[1]
    summary = json.loads(outs[0])
    assert not re.search(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}", outs[0])  # no timestamps in summary.json
    assert summary["e1"]["systems"]["llm_large"]["status"] == "not run"
    assert summary["e1"]["systems"]["llm_large"]["missing_cache_entries"] > 0
    assert summary["e2"]["llm_baseline"]["status"] == "not run"
    assert summary["e4"]["projection"]["chf_per_1000_bom_lines"]["8b_only"] is not None
    assert (tmp_path / "a" / "out" / "run_info.json").exists()
