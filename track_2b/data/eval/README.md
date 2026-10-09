# Evaluation data (`data/eval/`)

| File | What it is | Made by |
|---|---|---|
| `hs_gold.jsonl` | E1 benchmark: BOM-style descriptions with a gold HS 2022 subheading (6 digits) | hand labelling + `python -m eval.gold --import-hscodecomp` |
| `LICENSE-HSCodeComp.txt` | Apache License 2.0, copied from the HSCodeComp repository | upstream |
| `e3_letters_for_rating.csv` | E3: Chinese buyer letters and back-translations of the 5 demos, with empty `rating_1to4` and `comment` columns for a blind native-speaker rating | `python -m eval.run_all` |
| `results/summary.json` | machine-readable results of E1-E4 (no timestamps, reproducible in replay mode) | `python -m eval.run_all` |
| `results/results.md` | the same results as Markdown tables for `technical_report.md` | `python -m eval.run_all` |
| `results/run_info.json` | wall-clock times, Python version, git dirty flag | `python -m eval.run_all` |

`run_all` never overwrites a rating sheet that already holds ratings; it writes `e3_letters_for_rating.new.csv` instead.

## `hs_gold.jsonl`

One JSON object per line:

| Field | Meaning |
|---|---|
| `id` | `bom-<lang>-NNN` (hand-labelled), `par-<concept>-<lang>` (parallel), `hcc-NNNN` (HSCodeComp task id) |
| `text` | the description as it would appear in a BOM line or product master |
| `lang` | `en`, `de`, `fr` or `it` |
| `gold_hs6` | gold HS 2022 subheading; every code exists in `data/hs/hs2022.csv` (checked by `tests/test_eval_gold.py`) |
| `source` | `hand-labelled from HS 2022 nomenclature`, or the HSCodeComp repository and commit |
| `licence` | licence of the row: `CC-BY-4.0` (this project) or `Apache-2.0` (HSCodeComp) |
| `subset` | `main`, `parallel` or `hscodecomp` |
| `split` | `dev` (about 30 %) or `test` (about 70 %); frozen, see below |
| `concept` | parallel rows only: the concept id shared by the four translations |
| `note` | optional: why an item is hard (e.g. a chapter note), or a classification detail |
| `ref` | HSCodeComp rows only: upstream task id and the full 10-digit US HTS code |

### Subsets (510 rows)

| Subset | Rows | Languages | Content |
|---|---|---|---|
| `main` | 179 | EN 83, DE 53, FR 26, IT 17 (46/30/15/9 %) | parts as Swiss SMEs write them in BOMs (bearings, screws, nuts, springs, PCBs, ICs, capacitors, connectors, cables, motors, power supplies, batteries, sensors, gaskets, seals, belts, pumps, valves, cylinders, gears, aluminium/copper/brass/stainless semi-finished products, castings, plastic mouldings and granules, packaging, watch cases, dials, straps, movements, crowns, sapphire and mineral glasses) and finished goods (watches, espresso machines, hearing aids, dental implants, CNC lathes, robots, instruments) |
| `parallel` | 120 | 30 concepts x EN/DE/FR/IT | the same item written in four languages, to measure cross-lingual consistency |
| `hscodecomp` | 211 | EN | e-commerce product titles from HSCodeComp, restricted to chapters 39, 40, 70, 73, 74, 76, 84, 85, 90, 91 |

### Split

`split = "dev"` when the first 8 bytes of `sha256("originpass-e1-v1:" + key)` read as an integer fall below 30 % of 2^64;
`key` is the row id, or the concept id for parallel rows (so translations of one concept never straddle dev and test).
The split is a pure function of the key: adding rows never moves existing ones. Prompts and thresholds may be tuned on
`dev`; every reported number is on `test`.

## Provenance and licences

### Hand-labelled rows (`main`, `parallel`)

- Written for this project by the OriginPass author in October 2026, imitating BOM and product-master wording of Swiss
  machine, electronics, medtech and watch SMEs (part numbers, norms such as DIN/ISO, Swiss German spelling without ß).
  No company data was used; any resemblance to real part lists is generic.
- Licence: CC-BY-4.0, like the rest of the project.
- Labelling method: the author read each description and chose the 6-digit subheading from the HS 2022 nomenclature
  text in `data/hs/hs2022.csv` (UN Comtrade, ODC-PDDL), applying the General Interpretative Rules and the section and
  chapter notes as far as they are known to the author. Items with a known trap carry a `note`, for example:
  - watch glasses are classified by their material (Chapter 91, Note 1(a)): synthetic sapphire glass -> 7104.99,
    mineral glass -> 7015.90;
  - parts of general use (Section XV, Note 2) leave Chapter 91 and 84: a steel watch screw -> 7318.15;
  - a toothed wheel presented separately -> 8483.90, a gearbox -> 8483.40;
  - a populated control board of a frequency converter -> 8504.90 (parts of static converters);
  - a solenoid valve for water -> 8481.80, a pneumatic 5/2 valve -> 8481.20.
- HS 2022 merged the former subheading 9114.10 (clock or watch springs) into 9114.90 (UNSD correlation table
  `data/raw/hs2022_hs2012_correlation_unsd.csv`: 911490 <- 911410), so watch springs are labelled 9114.90.

### HSCodeComp rows (`hscodecomp`)

- Source: HSCodeComp, "A Realistic and Expert-level Benchmark for Deep Search Agents in Hierarchical Rule
  Application" (Yang et al., arXiv:2510.19631), file `Marco-DeepResearch-Family/HSCodeComp/data/test_data.jsonl` of
  https://github.com/AIDC-AI/Marco-Search-Agent, commit `2be90e40519f67916b4d7a621491e04efac0b6de`
  (file sha256 `8f5cf651...706a9f3c`). Copyright (C) 2025 AIDC-AI.
- Licence: Apache-2.0 (`LICENSE-HSCodeComp.txt`). Changes made here: kept only the 211 of 632 entries whose code lies
  in the chapters above, kept only the product title (attributes, categories, price and prompt dropped), truncated
  the expert-assigned 10-digit US HTS code to its first 6 digits.
- Upstream disclaimer: the product titles come from public e-commerce listings; the authors "cannot guarantee that
  [the] datasets are completely free of copyright issues or improper content".
- The labels are US classifications (HTS 2025, HS 2022 based); the first six digits are the international HS
  subheading, which the PRC tariff shares. Every one of them exists in `hs2022.csv`. A later paper
  (arXiv:2605.14857) suggests some HSCodeComp labels may not follow the GIR; we did not re-check them.
- The titles are noisy English marketing text (brand names, compatibility lists), unlike BOM lines; the subset is
  reported separately and is not mixed into the BOM numbers.

## Limits of the gold labels

- The hand labels are **author-assigned, not official rulings**. No customs authority, broker or second annotator has
  reviewed them, so there is no inter-annotator agreement figure. Expect a few percent label noise, concentrated in
  items marked `hard` or `medium` (parts vs. articles, sensors, generic plastic and aluminium articles).
- Binding classification needs a BTI/advance ruling (e.g. Swiss FOCBS, PRC GACC); the benchmark measures the
  copilot's suggestions, which a human must confirm.
- The descriptions are short and often under-specified on purpose (that is how BOMs look); some items have a single
  defensible code only under the assumption stated in `note`.
- Chapter coverage follows the project scope (chapters 84, 85, 90, 91 and their typical materials), not the
  distribution of Swiss exports.

## Reproduce

```bash
cd src/api
DATA_DIR=../../data PYTHONPATH=.. python -m eval.gold --check        # validate the gold file
DATA_DIR=../../data PYTHONPATH=.. python -m eval.run_all             # E1-E4 -> data/eval/results/
```
