# Demo video storyboard (≤ 2:00)

Record at 1440×900, browser zoom 100%, `make run` with a live `LLM_API_KEY` (or the recorded replay cache).
Narration in English; keep the Chinese letter on screen long enough to read.

| Time | Screen | Narration (draft) |
|---|---|---|
| 0:00–0:12 | Title card: "OriginPass CH–CN — rules-of-origin copilot on Apertus" | "Swiss exporters leave up to 200 million dollars of China-FTA savings unclaimed, because proving origin means BOM-level spreadsheet work on data they cannot send to foreign clouds." |
| 0:12–0:30 | Pick **Centrifugal pump AP-80**. Verdict card: **FAIL**, gauge at 51.2 % vs the 50 % limit, rule CHCN-84 quoted in English and in the official Chinese text | "OriginPass reads the product's rule straight from the official Annex II — here chapter 84, non-originating materials at most 50 % — and computes the share deterministically: 51.2 %, fail." |
| 0:30–0:45 | BOM table: German/Italian part names; click **Classify all missing HS codes**; show a suggestion with candidates, confidence and rationale | "Apertus reads multilingual BOM lines — German, French, Italian — rewrites them into customs English and picks the HS code from retrieved candidates, or abstains when unsure." |
| 0:45–1:00 | What-if: change motor L01 origin DE → CH. Card flips to **PASS** (34.8 %); duty estimate shows the saving per order | "Switch one supplier, and the verdict flips live. That is a sourcing decision an export manager can make in seconds instead of days." |
| 1:00–1:25 | Dossier tab → **Generate dossier**: English explanation, German summary, **Chinese letter to the importer** with back-translation; green fact-check chips | "Apertus drafts the explanation and a formal Chinese letter for the importer, with the right customs terms — 原产地证书, 协定税率. Every number is checked against the engine; a wrong number is regenerated or replaced by a template." |
| 1:25–1:42 | Evaluation tab: E1 by language, E2 "5,823 BOMs, 100 % agreement, 0 false PASS", cost per 1,000 checks | "We measure it: [insert the live E1 result per language here; do not claim an improvement before the live run] the engine matches an independent implementation on 5,823 BOMs with zero false passes, and a check costs a fraction of a rappen." |
| 1:42–1:55 | About tab: target architecture (on-premise / air-gapped / Swiss cloud) | "Everything runs on-premise or on Swiss infrastructure — CSCS, Infomaniak, or a vLLM box in the exporter's server room. BOMs never leave Switzerland." |
| 1:55–2:00 | Closing card: repo URL, "Built on Apertus · Hack Apertus 2026" | "OriginPass: sovereign AI for Swiss exporters." |

Checklist before recording: header badge shows **Live Apertus** (or "Replay cache" if pre-recorded), rule
verification badge after the human check, browser console clean, no personal data on screen.
