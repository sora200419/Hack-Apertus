# OriginPass CH–CN

**Rules-of-origin copilot for Swiss SMEs exporting to China. Runs on Apertus, deployable on-premise or in a Swiss sovereign cloud.**

Swiss exporters leave FTA preferences unclaimed because proving origin is slow, BOM-level spreadsheet work,
and their bills of materials and supplier prices are trade secrets they will not upload to foreign SaaS.
The Switzerland–China FTA upgrade (concluded 20 Aug 2026) makes every exporter re-check eligibility.

OriginPass takes a product and its bill of materials and:

1. **Classifies free-text BOM lines** (DE/FR/IT/EN/ZH) to HS 2022 sub-headings. Hybrid retrieval is followed by an **Apertus** re-rank, and the model abstains when unsure.
2. **Computes the origin verdict deterministically** (PASS / FAIL / UNSURE) from the Annex II product-specific rule. The verdict comes with a full rule trace, the non-originating share against the threshold, tolerance and cumulation.
3. **Simulates sourcing changes live.** Swap a supplier and watch the verdict and the duty saved change.
4. **Drafts the export dossier.** This includes an English explanation (Apertus), a German summary (template), a formal Chinese letter to the importer (Apertus) with back-translation, and automatic fact checks so every number matches the engine.

| | |
|---|---|
| Run | `make run` → http://localhost:8080 (API docs: http://localhost:8000/docs) |
| Live Apertus | `export LLM_NAME=swiss-ai/Apertus-v1.5-70B LLM_BASE_URL=https://api.inference.cscs.ch/v1 LLM_API_KEY=...` then `make run` |
| No key? | Runs from the committed replay cache (`data/replay/llm_cache.jsonl`) |
| Tests | `make test` |
| Evaluation | `make eval` (replay) · `make eval-live` (live endpoint) |
| Report | [`technical_report.md`](technical_report.md) |

> Decision support, not customs advice. Verify with the BAZG or your chamber of commerce.

---

## Challenge description (from the Hack Apertus template)

### Track 2 B: Own Project

Bring your own idea and build a working Apertus prototype that tackles a problem you care about — any domain, any use case. The project must be new, started within the hackathon period.

Submissions must use the Apertus model family.
For Track 2 this means that submitted solutions must be built with Apertus. Other open-weights models can be used to support development, e.g. as automatic judges during evaluation. Their role must be clearly described in the submission report.

💬 In case you have questions, join the conversation on [Discord](https://discord.gg/hack-apertus) or send an email to “hello@hackapertus.ch”

---

## 🔧 Resources & Tools

Check our resources & tools page for detailed information:
https://hackapertus.notion.site/resources-tools

| Models           | URL                                      |
|------------------|------------------------------------------|
| Apertus v1.5 8B  | [huggingface.co/swiss-ai/Apertus-v1.5-8B](https://huggingface.co/swiss-ai/Apertus-v1.5-8B)  |
| Apertus v1.5 70B | [huggingface.co/swiss-ai/Apertus-v1.5-70B](https://huggingface.co/swiss-ai/Apertus-v1.5-70B) |


## Target architecture (mandatory)

Whatever you build in Track 2B must be deployable in one of these three architectures:

- **a) On-premise** — on the organisation's own infrastructure, under its own administration.
- **b) Air-gapped** — with no external network connection at runtime.
- **c) Sovereign Swiss cloud** — on a cloud platform operated in Switzerland, under Swiss jurisdiction, with Swiss data residency.

---

## Data

The `data/` directory must not exceed 100 MB.

---

## 📦 Submission Requirements & Deliverables

❗️ Submissions are not handled on Devpost but via this URL only:
http://hackapertus.ch/online-hack/submissions

The submission must: 
1. follow the template repo and include all prerequisite files and definitions
2. follow the specified input/output formats
3. run in a Docker container, launched with `make run` from the root of the project
4. run end-to-end when judges try to run it

### Git repo (URL)
- Create your repo from this template (**Use this template**) and work in the `track_2b/` challenge directory. Delete the other track challenge directories.
- Keep `track_2b/` as it is: don't rename it or move its files.
- Set the repo to PUBLIC (Settings --> Collaborators --> Manage Visibility)
- Submit the URL of YOUR Git repo.

### Technical Report (pdf)
- Update [technical_report.md](technical_report.md) in this repository with all the details for your submission.
- Upload a pdf of your technical report to this directory, named as `TeamName_Report.pdf`.
- Format: pdf, max. 6 pages
- Submit the pdf of the technical report.

### Demo video (URL)
- Max. 2 min demo video of your prototype

### Dataset (URL) - optional, depending on your project
Submitted datasets must comply with our guidelines for responsibly sourced datasets.

- Create a user account on Hugging Face
- Clone our dataset template on Hugging Face: https://huggingface.co/datasets/HackApertus/online_hack_template
- Complete the dataset card with all required information
- Upload your dataset. It should consist of the following components:
    - evaluation dataset (i.e. individual test cases)
    - model response dataset (i.e. the model response to each test case)
    - metadata file (i.e. additional information about each test case; where relevant, this file must contain instance-level licensing information) 
- Make sure your dataset access control is set to PUBLIC
- Provide the URL of _your_ data set


---

## ⚖️ Judging Criteria

1. Purposeful use of AI
2. Technical rigour
3. Value, cost & scalability
4. Sovereign deployability
5. Implementation feasibility

Judges use a Scale 0–5 per dimension.

---

## Support

**Licensing requirements**
Please check our Terms & Conditions (6. What you build is open source):
https://hackapertus.ch/terms-and-conditions

## FAQ
💡 https://hackapertus.ch/faq

## Contact
💬 In case you have questions, join the conversation on Discord or send an email to “hello@hackapertus.ch”
