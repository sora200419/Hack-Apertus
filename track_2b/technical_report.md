# Technical report — OriginPass CH–CN

A sovereign rules-of-origin copilot for Swiss SMEs exporting to China, built on Apertus.

- **Track:** Track 2B — OriginPass CH–CN
- **Event:** Online
- **Team:** `team name` — `member`
- **Demo:** `link to video`

## 1. Summary

Swiss exporters leave Switzerland–China FTA preferences unclaimed. A University of St. Gallen ten-year
evaluation puts utilisation at about 71% and the remaining potential at up to about USD 200 M. The causes
are complex forms and missing know-how. The FTA upgrade concluded on 20 Aug 2026 will make every exporter
re-check eligibility. Proving origin means BOM-level work: classify every material, find the product's Annex
II rule, and compute the non-originating share of the ex-works price. Bills of materials and supplier prices
are trade secrets, so the work cannot go to foreign SaaS.

OriginPass splits the job:
- **Apertus** does the language work. It classifies free-text BOM lines written in DE/FR/IT/EN, explains the
  verdict, and drafts a formal Chinese letter to the importer.
- **A deterministic engine** decides origin from the treaty's own text. The rule pack was parsed from the
  official Chinese Annex II (GACC Announcement 2014 No. 51): all 97 chapters, 221 rules.

Headline results:
- The engine agrees with an independent re-implementation on **100% of 5,823 synthetic BOMs across 96
  chapters**, with **0 false PASS**.
- Every number in every generated text is checked against the engine.
- Without a model, HS retrieval reaches 29.6% top-1 on English BOM lines but **2.4% on German and 0% on
  Italian**. The cross-lingual gap is exactly where Apertus is needed.
- The Apertus rows are filled from a recorded replay cache (see §5).

## 2. Architecture

```
 Browser (React, bundled, no CDN)             FastAPI (Python 3.11)                         Apertus 1.5
 ┌──────────────────────────┐  /api   ┌────────────────────────────────────────┐  OpenAI-compatible
 │ BOM editor + what-if     │ ──────▶ │ hs/       BM25 + char-ngram TF-IDF (RRF)│ ─────────────────▶ 8B: rewrite,
 │ verdict + rule trace     │         │           over HS 2022 → Apertus rerank │                    rerank, back-
 │ dossier (EN/DE/ZH)       │ ◀────── │ engine/   VNM / CC / CTH / CTSH / WO,   │ ◀───────────────── translation
 │ evaluation, about        │         │           tolerance, Art. 3.6, 3.7, 3.13│                    70B: explanation,
 └──────────────────────────┘         │ dossier/  facts → Apertus → validator   │                    Chinese letter
                                      │ llm/      record/replay cache, cost log │
                                      │ data/     rule pack, HS 2022, tariffs   │
                                      └────────────────────────────────────────┘
```

**Data flow.**
1. A BOM is entered (demo, CSV, or edited in the UI).
2. Lines without an HS code are classified: Apertus rewrites the text to an English customs description,
   hybrid retrieval returns 10 candidates, and Apertus picks one or abstains.
3. The engine evaluates the product against the most specific Annex II entry and the Chapter 3 provisions.
4. Every edit (origin, value, HS code) re-runs the engine, so the UI doubles as a sourcing simulator.
5. The dossier step sends only engine facts to Apertus. Generated text is fact-checked and regenerated once
   if a number is wrong; after that, a deterministic template takes over.

### Target architecture (mandatory)

OriginPass is deployable as **(a) on-premise** and **(b) air-gapped**, and is
**(c) Swiss-sovereign-cloud ready**.

- **(a) On-premise:** two containers (`api`, `web`) run with `make run` on one VM. Apertus 1.5 is served
  next to them by vLLM (8B or 70B), or the 8B runs on CPU through llama.cpp. The app reads
  `LLM_BASE_URL/LLM_NAME/LLM_API_KEY` only, so pointing it to an in-house endpoint is configuration, not code.
- **(b) Air-gapped:** at runtime there are no external calls besides the configured LLM endpoint. The HS
  index, rule pack, tariff table, fonts and JS bundle are all inside the images. With no endpoint, the app
  falls back to retrieval, the engine and templates, and says so in the UI.
- **(c) Swiss sovereign cloud:** configured by default for the CSCS Inference API (Lugano; CSCS does not
  record prompts). Infomaniak or Swisscom are the same OpenAI-compatible configuration.

Dependencies:
- **Build time:** PyPI and npm packages, Docker base images.
- **Runtime:** none, apart from the LLM endpoint.

## 3. Use of Apertus

- **Models:**
  - `swiss-ai/Apertus-v1.5-8B` (`LLM_NAME_SMALL`): query rewrite, reranking, back-translation.
  - `swiss-ai/Apertus-v1.5-70B` (`LLM_NAME`): the explanation and the Chinese letter.
- **How it is used:** inference only, temperature 0, non-thinking mode. Prompt-level JSON is validated with
  pydantic, invalid answers abstain, and there is one retry.
- **Where it runs:** the hosted CSCS endpoint during the hackathon; on-premise vLLM or llama.cpp in
  production.

**Why an LLM, and only there.**
- HS classification of BOM text is a language problem. Lines are terse, multilingual and full of trade
  jargon ("Rillenkugellager 6309-2Z C3", "boîtier inox 316L"), while the nomenclature is English legal text.
- The origin verdict is arithmetic over legal rules. It is never delegated to the model: §5 E2 measures what
  happens when it is.

**Prompts.** Prompts are constants in `originpass/hs/prompts.py` and `originpass/dossier/prompts.py`.
- The reranker sees a numbered candidate list and must return one of those codes or `null`.
- The explainer and the letter writer receive a JSON facts block and must not introduce numbers that are not
  in it. A validator (`dossier/validator.py`) extracts numbers, HS codes and rule IDs and compares them with
  the engine.
- The Chinese letter must use standard PRC customs terms (原产地证书, 原产地声明, 经核准出口商, 协定税率), checked
  against a glossary.

**Replay cache.** Every live call is stored in `data/replay/llm_cache.jsonl`, keyed by role, messages and
parameters. `make run` and `make eval` work on a clean checkout without a key, and judges see exactly the
answers the reported numbers come from.

## 4. Data

| Data | Source | Licence / status |
|---|---|---|
| Annex II product-specific rules, 97 chapters | GACC Announcement 2014 No. 51 (official Chinese text) | Official text (PRC Copyright Law Art. 5) |
| Chapter 3 rules of origin (EN/DE/ZH) | MOFCOM English text (ToTA corpus), fedlex SR 0.946.292.492, GACC 2014 No. 52 | Official texts (URG Art. 5) |
| Tariff rates, 8,277 lines | GACC 2014 No. 53, Annex 1 (MFN and Swiss conventional rates at 1 July 2014) | Official text; labelled as 2014 rates |
| HS 2022 nomenclature | github.com/datasets/harmonized-system (UN Comtrade) | ODC-PDDL |
| HS 2022→2012 correlation | UNSD correlation table | UN public data |
| E1 gold: 211 e-commerce titles | HSCodeComp (AIDC-AI) | Apache-2.0 |
| E1 gold: 179 BOM lines + 120 parallel rows | written and labelled by the author from the HS 2022 text | CC-BY-4.0; not official rulings |
| Demo BOMs (5 products) | synthetic, fictional companies | CC-BY-4.0 |

There is no personal data. All BOMs are synthetic, as the CSCS terms require. Provenance per file:
`data/raw/SOURCE.md`, `data/eval/README.md`, `data/tariffs/SOURCE.md`.

## 5. Evaluation

All numbers come from `make eval` (`python -m eval.run_all`): seeded, temperature 0 and replayable. Full tables
are in `data/eval/results/results.md`.

**E1 — HS classification (the AI task).**
- Test split of 126 hand-labelled BOM lines (EN 54 / DE 42 / FR 18 / IT 12), 148 HSCodeComp titles, and 88
  parallel rows (22 concepts × 4 languages).
- Metrics: top-1 and top-3 accuracy at HS6 and HS4, recall@10 (the reranker's ceiling), coverage and
  selective accuracy, and cross-lingual agreement.

| Setup (BOM test set, n=126) | Top-1 HS6 | Top-1 HS4 | EN / DE / FR / IT top-1 |
|---|---|---|---|
| Baseline: BM25 | 14.3% | 19.8% | 29.6 / 2.4 / 5.6 / 0.0 |
| Baseline: fused retrieval (RRF) | 15.9% | 22.2% | 29.6 / 2.4 / 16.7 / 0.0 |
| Ours: Apertus 8B rewrite + 8B rerank | *pending live run* | | |
| Ours: Apertus 8B rewrite + 70B rerank | *pending live run* | | |

Without a model, recall@10 is only 31%, because German and Italian part names share no words with the
English nomenclature: "Kugellager Edelstahl 6204" retrieves paintings (9701). The Apertus rewrite step is
what lifts the candidate set; the reranker then chooses within it or abstains.

**E2 — origin verdicts.**
- (a) Differential test: the engine against an independent re-implementation (`eval/reference.py`, own rule
  lookup, exact fractions).
- (b) The five demos.
- (c) An LLM-only baseline: Apertus 70B gets the same BOM, rule text (EN + ZH) and ex-works price and must
  answer PASS/FAIL/UNSURE with the VNM %.

| Setup | Metric | Result |
|---|---|---|
| Engine vs reference, 5,823 BOMs, 96 chapters (incl. boundary, tolerance, cumulation, transit cases) | status agreement / false PASS | **100% / 0** |
| LLM-only baseline (Apertus 70B), 105 BOMs | accuracy / false-PASS rate / VNM % error | *pending live run* |

A false PASS (claiming preference wrongly) is the costly error: it triggers retroactive duty claims. The
engine's false-PASS rate is 0 by construction and is verified differentially. The LLM-only row shows why the
verdict is not left to a model.

**E3 — export dossier.** For the 5 demos, the metrics are:
- fact checks passed (100% in template mode);
- the share of texts written by the model vs template fallbacks;
- glossary compliance of the Chinese letter (100%);
- a native-speaker rating (1–4) of the Chinese letters (`data/eval/e3_letters_for_rating.csv`): *pending*.

**E4 — cost and latency.** The projection uses Public AI list prices and the measured prompt sizes:

| Per 1,000 | Apertus 8B only | Apertus 70B only | As routed (8B HS, 70B dossier) |
|---|---|---|---|
| BOM lines classified | CHF 0.15 | CHF 1.50 | CHF 0.15 |
| Dossiers | CHF 0.41 | CHF 5.21 | CHF 3.52 |

That is well under a rappen per product check, against hours of manual BOM work per product. Measured p50/p95
latency will be added from the live run.

## 6. Limitations

- **Rule encoding.** The English Annex II strings are rendered from the official Chinese text; independent
  English sources confirm chapters 84, 85 and 90. Rules are marked `verified` only after a human check
  (`docs/rule_verification_zh.md`); the UI shows unverified rules.
- **HS versions.** Annex II is HS 2012. HS 2022 product codes new since 2012 are mapped through the UNSD
  table; ambiguous ones give UNSURE. Material codes in tariff-shift tests are compared as entered.
- **Judgement calls.** Specific-process rules, Annex II Section II (chapters 27–40) and mixed processing
  descriptions give UNSURE by design. The Art. 3.6 screen is keyword-based.
- **Tariffs** are the 1 July 2014 rates; current rates are lower. The upgraded FTA is not yet published and
  is not encoded; the pack is versioned (`ch-cn-2014`) for a later `ch-cn-upgrade`.
- **Gold labels.** The hand-written HS labels are the author's, from the nomenclature, with no second
  annotator. HSCodeComp labels are US classifications.
- **Not legal advice.** Decision support only; the exporter remains responsible for the declaration.

## 7. Reproducibility

- **Hardware:** any x86-64 or ARM machine with Docker; no GPU (models are remote or self-hosted).
- **Commands:**
  - `make run`: UI at http://localhost:8080, API docs at :8000/docs.
  - `make test`: about 550 tests.
  - `make eval`: replay mode, about 30 s, byte-identical `summary.json`.
  - `make eval-live`: records new cache entries against `LLM_BASE_URL`.
- **Seeds:** synthetic BOM seed 2026; dev/test splits are hash-frozen; temperature 0.
- **Commit:** see `data/eval/results/results.md` (the commit hash is written by `run_all`).

## 8. Next steps

- Encode the upgraded CH–CN FTA as soon as its texts are published, with a side-by-side "2014 vs upgrade" view.
- Add Switzerland's other FTAs. The rule-pack schema is agreement-neutral.
- Integrate with ERP BOM exports and fill the EUR.1 / origin declaration fields directly.
- Pilot with a chamber of commerce. Measure time saved per origin check and agreement with their experts.
- Compare quantised Apertus 8B on CPU against the hosted 70B to support fully air-gapped SMEs.

## License

Creative Commons Attribution 4.0 (CC-BY-4.0). All HackApertus projects are open-sourced.

## References

- Free Trade Agreement between the Swiss Confederation and the People's Republic of China, Chapter 3 and
  Annex II (SR 0.946.292.492).
- GACC Announcements 2014 No. 51, No. 52, No. 53; 2021 No. 49.
- Universität St. Gallen, "10 years free trade agreement between Switzerland and China".
- Swiss AI Initiative, Apertus technical report (arXiv 2509.14233).
- AIDC-AI, HSCodeComp benchmark (Apache-2.0).
