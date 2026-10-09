"""E3: export dossiers for the demo products, checked by the deterministic validators.

For each demo, `build_dossier` runs exactly as in the API. Per text we report the source (live / replay
model answer or template fallback), the number of generation attempts and the fact checks; for the Chinese
letter also the glossary compliance (required PRC customs terms). The letters and their back-translations
are exported to data/eval/e3_letters_for_rating.csv for a blind native-speaker rating (1-4). A rating file
that already holds ratings is never overwritten: the new export then goes to a '.new.csv' file next to it.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from originpass.dossier.builder import build_dossier
from originpass.dossier.validator import glossary_check
from originpass.engine.origin import evaluate
from originpass.llm import LLMClient
from originpass.models import Dossier, DossierText, RulePack

from .demos import load_demos
from .util import TrackedLLM, ratio

TEXTS = ("explanation_en", "explanation_de", "letter_zh", "back_translation_en")
# Texts a model may write; explanation_de is a template by design.
MODEL_TEXTS = ("explanation_en", "letter_zh", "back_translation_en")
RATING_FILE = Path("eval") / "e3_letters_for_rating.csv"
RATING_COLUMNS = ["product_id", "status", "letter_zh", "back_translation_en", "rating_1to4", "comment"]


def text_row(text: DossierText) -> dict[str, Any]:
    passed = sum(c.found for c in text.fact_checks)
    return {
        "llm_source": text.llm_source,
        "attempts": text.attempts,
        "checks_passed": passed,
        "checks_total": len(text.fact_checks),
        "failed_checks": [c.fact for c in text.fact_checks if not c.found],
    }


def write_rating_csv(path: Path, dossiers: list[Dossier]) -> Path:
    """Write the rating sheet; keep an already rated sheet and write '<name>.new.csv' instead."""
    if path.exists():
        with path.open(encoding="utf-8", newline="") as f:
            if any((r.get("rating_1to4") or "").strip() for r in csv.DictReader(f)):
                path = path.with_suffix(".new.csv")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(RATING_COLUMNS)
        for d in dossiers:
            writer.writerow(
                [d.product_id, d.verdict_status.value, d.letter_zh.text, d.back_translation_en.text, "", ""]
            )
    return path


def run(
    pack: RulePack, data_dir: Path, client: LLMClient | None, tariffs: dict, rating_path: Path | None
) -> tuple[dict, dict[str, TrackedLLM]]:
    """E3 results and the dossier call tracker (for E4), keyed 'e3.dossier'."""
    tracker = TrackedLLM(client) if client is not None else None
    dossiers = [
        build_dossier(p, evaluate(p, pack), tracker, tariffs)  # type: ignore[arg-type]  # TrackedLLM duck-types LLMClient
        for p in load_demos(data_dir).values()
    ]
    per_demo: list[dict[str, Any]] = []
    for d in dossiers:
        texts = {name: text_row(getattr(d, name)) for name in TEXTS}
        glossary = glossary_check(d.letter_zh.text)
        per_demo.append(
            {
                "product_id": d.product_id,
                "status": d.verdict_status.value,
                "texts": texts,
                "letter_glossary_ok": all(c.found for c in glossary),
                "letter_glossary_missing": [c.fact for c in glossary if not c.found],
                "checklist_items": len(d.checklist),
                "duty_estimate": d.duty is not None,
            }
        )
    rows = [r["texts"][name] for r in per_demo for name in TEXTS]
    model_rows = [r["texts"][name] for r in per_demo for name in MODEL_TEXTS]
    results: dict[str, Any] = {
        "demos": per_demo,
        "fact_check_pass_rate": ratio(sum(r["checks_passed"] for r in rows), sum(r["checks_total"] for r in rows)),
        "texts_all_checks_passed": ratio(sum(r["checks_passed"] == r["checks_total"] for r in rows), len(rows)),
        "letter_glossary_compliance": ratio(sum(r["letter_glossary_ok"] for r in per_demo), len(per_demo)),
        "model_texts": len(model_rows),
        "model_written": sum(r["llm_source"] != "template" for r in model_rows),
        "template_fallbacks": sum(r["llm_source"] == "template" for r in model_rows),
        "attempts_total": sum(r["attempts"] for r in model_rows),
        "missing_cache_entries": tracker.misses() if tracker else None,
    }
    if rating_path is not None:
        written = write_rating_csv(rating_path, dossiers)
        results["rating_sheet"] = (
            f"data/{written.relative_to(data_dir).as_posix()}" if written.is_relative_to(data_dir) else written.name
        )
    return results, {"e3.dossier": tracker} if tracker is not None else {}
