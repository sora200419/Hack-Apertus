"""HS classifier with a fake LLM: rerank, abstention paths and the retrieval-only fallback. No network."""

from __future__ import annotations

import json

import pytest

from originpass.hs import prompts
from originpass.hs.classifier import classify, classify_bom, parse_choice, rerank_messages
from originpass.hs.index import HSIndex, get_index
from originpass.llm import LLMResult, LLMUnavailable
from originpass.models import BomLine, Product

REWRITE_OK = json.dumps({"en": "centrifugal pump for liquids", "keywords": ["pump", "centrifugal", "liquids"]})


class FakeLLM:
    """Stub of LLMClient.chat: canned replies (or exceptions) keyed by call tag."""

    def __init__(self, replies: dict[str, str | Exception], source: str = "replay"):
        self.replies = replies
        self.source = source
        self.calls: list[dict] = []

    def chat(self, messages, role="large", temperature=0.0, max_tokens=800, tag=""):
        self.calls.append(
            {"messages": messages, "role": role, "temperature": temperature, "max_tokens": max_tokens, "tag": tag}
        )
        reply = self.replies[tag]
        if isinstance(reply, Exception):
            raise reply
        return LLMResult(
            text=reply, source=self.source, model="fake", prompt_tokens=10, completion_tokens=5, latency_s=0.0
        )


def _rerank(hs6, confidence=0.9, rationale="Centrifugal pump for liquids, GIR 1 and 6.") -> str:
    return json.dumps({"hs6": hs6, "confidence": confidence, "rationale": rationale})


@pytest.fixture(scope="module")
def index() -> HSIndex:
    return get_index()


def test_happy_path(index: HSIndex) -> None:
    llm = FakeLLM({"hs_rewrite": REWRITE_OK, "hs_rerank": _rerank("841370")})
    s = classify("Kreiselpumpe für Kühlwasser", llm, index)
    assert (s.chosen, s.abstained, s.method, s.llm_source) == ("841370", False, "llm", "replay")
    assert s.confidence == 0.9
    assert s.query == "Kreiselpumpe für Kühlwasser"
    assert "841370" in [c.hs6 for c in s.candidates]
    assert [c["tag"] for c in llm.calls] == ["hs_rewrite", "hs_rerank"]
    assert all(c["role"] == "small" and c["temperature"] == 0.0 and c["max_tokens"] <= 200 for c in llm.calls)
    user = llm.calls[1]["messages"][1]["content"]
    assert "English rewrite: centrifugal pump for liquids (pump, centrifugal, liquids)" in user
    assert f"841370: {index.describe('841370')}" in user
    assert llm.calls[1]["messages"][0]["content"] == prompts.RERANK_SYSTEM


def test_rerank_uses_requested_role_and_live_source(index: HSIndex) -> None:
    llm = FakeLLM({"hs_rewrite": REWRITE_OK, "hs_rerank": _rerank("841370")}, source="live")
    s = classify("centrifugal pump", llm, index, role="large")
    assert [c["role"] for c in llm.calls] == ["small", "large"]
    assert s.llm_source == "live"


def test_prompts_are_deterministic(index: HSIndex) -> None:
    first, second = (FakeLLM({"hs_rewrite": REWRITE_OK, "hs_rerank": _rerank("841370")}) for _ in range(2))
    classify("Kreiselpumpe", first, index)
    classify("Kreiselpumpe", second, index)
    assert first.calls == second.calls


def test_dotted_code_is_accepted(index: HSIndex) -> None:
    llm = FakeLLM({"hs_rewrite": REWRITE_OK, "hs_rerank": _rerank("8413.70")})
    assert classify("centrifugal pump", llm, index).chosen == "841370"


def test_hs6_not_among_candidates_abstains(index: HSIndex) -> None:
    llm = FakeLLM({"hs_rewrite": REWRITE_OK, "hs_rerank": _rerank("010121")})  # valid HS, not a candidate
    s = classify("centrifugal pump", llm, index)
    assert (s.chosen, s.abstained, s.method, s.confidence) == (None, True, "llm", 0.0)
    assert "010121" in s.rationale


def test_malformed_json_abstains(index: HSIndex) -> None:
    llm = FakeLLM({"hs_rewrite": REWRITE_OK, "hs_rerank": "It is probably a pump, 8413 something."})
    s = classify("centrifugal pump", llm, index)
    assert (s.chosen, s.abstained, s.method) == (None, True, "llm")
    assert s.candidates  # the user still sees the shortlist


def test_low_confidence_abstains(index: HSIndex) -> None:
    llm = FakeLLM({"hs_rewrite": REWRITE_OK, "hs_rerank": _rerank("841370", confidence=0.3)})
    s = classify("centrifugal pump", llm, index, min_confidence=0.5)
    assert (s.chosen, s.abstained, s.confidence) == (None, True, 0.3)
    assert "841370" in s.rationale


def test_model_abstention_is_respected(index: HSIndex) -> None:
    llm = FakeLLM({"hs_rewrite": REWRITE_OK, "hs_rerank": _rerank(None, confidence=0.0, rationale="Too vague.")})
    s = classify("part", llm, index)
    assert (s.chosen, s.abstained, s.method) == (None, True, "llm")
    assert "Too vague." in s.rationale


def test_malformed_rewrite_falls_back_to_raw_text(index: HSIndex) -> None:
    llm = FakeLLM({"hs_rewrite": "Sure! A pump.", "hs_rerank": _rerank("841370")})
    s = classify("centrifugal pump for liquids", llm, index)
    assert s.chosen == "841370"
    assert "English rewrite" not in llm.calls[1]["messages"][1]["content"]


def test_llm_unavailable_falls_back_to_retrieval_only(index: HSIndex) -> None:
    llm = FakeLLM({"hs_rewrite": LLMUnavailable("replay cache miss"), "hs_rerank": _rerank("841370")})
    s = classify("centrifugal pump for liquids", llm, index)
    assert (s.method, s.llm_source, s.chosen, s.abstained) == ("retrieval_only", "none", "841370", False)
    assert 0.5 < s.confidence <= 1.0
    assert [c["tag"] for c in llm.calls] == ["hs_rewrite"]  # no rerank attempt after the outage


def test_retrieval_only_abstains_when_rankers_disagree(index: HSIndex) -> None:
    s = classify("wrist watch automatic stainless steel case", None, index)
    assert (s.method, s.chosen, s.abstained, s.confidence) == ("retrieval_only", None, True, 0.0)
    assert any(c.hs6.startswith("9102") for c in s.candidates)


def test_rerank_unavailable_keeps_rewrite_source(index: HSIndex) -> None:
    llm = FakeLLM({"hs_rewrite": REWRITE_OK, "hs_rerank": LLMUnavailable("replay cache miss")})
    s = classify("Kreiselpumpe für Flüssigkeiten", llm, index)
    assert (s.method, s.llm_source) == ("retrieval_only", "replay")


def test_no_candidates_abstains_without_rerank(index: HSIndex) -> None:
    llm = FakeLLM({"hs_rewrite": "{}", "hs_rerank": _rerank("841370")})
    s = classify("123 456", llm, index)
    assert (s.chosen, s.abstained, s.candidates) == (None, True, [])
    assert [c["tag"] for c in llm.calls] == ["hs_rewrite"]


def test_empty_description_makes_no_llm_call(index: HSIndex) -> None:
    llm = FakeLLM({})
    s = classify("   ", llm, index)
    assert s.abstained and llm.calls == []


def test_chapter_filter_restricts_candidates(index: HSIndex) -> None:
    s = classify("pump", None, index, chapters=["84"])
    assert s.candidates and all(c.hs6.startswith("84") for c in s.candidates)


def test_classify_bom_skips_lines_with_hs6(index: HSIndex) -> None:
    product = Product(
        product_id="P1",
        name="Pump unit",
        description="Pump unit",
        ex_works_chf=100.0,
        bom=[
            BomLine(line_id="L1", description="Kreiselpumpe", origin_country="DE", value_chf=10.0),
            BomLine(line_id="L2", description="Ball bearing", hs6="848210", origin_country="JP", value_chf=5.0),
            BomLine(line_id="L3", description="Elektromotor", origin_country="CN", value_chf=20.0),
        ],
    )
    llm = FakeLLM({"hs_rewrite": REWRITE_OK, "hs_rerank": _rerank("841370")})
    out = classify_bom(product, llm, index)
    assert set(out) == {"L1", "L3"}
    assert [c["messages"][1]["content"] for c in llm.calls if c["tag"] == "hs_rewrite"] == [
        prompts.REWRITE_USER.format(description="Kreiselpumpe"),
        prompts.REWRITE_USER.format(description="Elektromotor"),
    ]


@pytest.mark.parametrize(
    ("reply", "expected"),
    [
        ('{"hs6": "841370", "confidence": 0.8, "rationale": "ok"}', ("841370", 0.8, "ok")),
        ('```json\n{"hs6": 10121, "confidence": "0.7"}\n```', ("010121", 0.7, "")),
        ('{"hs6": null, "rationale": "vague"}', (None, 0.0, "vague")),
        ('{"hs6": "841370", "confidence": 85}', None),
        ('{"hs6": "841370", "confidence": true}', None),
        ('{"hs6": "841370"}', None),
        ('{"confidence": 0.9}', None),
        ('{"hs6": ["841370"], "confidence": 0.9}', None),
        ("no json here", None),
    ],
)
def test_parse_choice(reply: str, expected) -> None:
    assert parse_choice(reply) == expected


def test_rationale_is_clipped_to_40_words() -> None:
    reply = json.dumps({"hs6": "841370", "confidence": 0.9, "rationale": " ".join(["word"] * 60)})
    assert len(parse_choice(reply)[2].split()) == prompts.RATIONALE_MAX_WORDS


def test_rerank_prompt_numbers_candidates(index: HSIndex) -> None:
    cands = index.search("ball bearing", k=3)
    user = rerank_messages("Kugellager", None, cands, index)[1]["content"]
    lines = user.split("\n")
    assert lines[:2] == ["Goods: Kugellager", "Candidates:"]
    assert [line.split(":")[0] for line in lines[2:]] == [f"{n}. {c.hs6}" for n, c in enumerate(cands, start=1)]
