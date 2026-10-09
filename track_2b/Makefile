.PHONY: run up down logs test eval eval-live dev-api dev-web clean

# Judges: `make run` from a clean checkout. Works without an API key (replay mode).
# Set LLM_NAME / LLM_BASE_URL / LLM_API_KEY to call Apertus live.
run:
	@echo "OriginPass CH-CN -> http://localhost:8080  (API: http://localhost:8000/docs)"
	docker compose up --build

up:
	docker compose up --build -d
	@echo "OriginPass CH-CN -> http://localhost:8080"

down:
	docker compose down

logs:
	docker compose logs -f

test:
	docker compose build api
	docker compose run --rm --no-deps api pytest -q tests

# Reproduce every number in technical_report.md from the committed replay cache.
eval:
	docker compose build api
	docker compose run --rm --no-deps -e LLM_MODE=replay api python -m eval.run_all

# Re-run the evaluation against a live Apertus endpoint (needs LLM_API_KEY); records new cache entries.
eval-live:
	docker compose build api
	docker compose run --rm --no-deps -e LLM_MODE=record api python -m eval.run_all

dev-api:
	cd src/api && DATA_DIR=$(CURDIR)/data uvicorn originpass.main:app --reload --port 8000

dev-web:
	cd src/web && npm install && npm run dev

clean:
	docker compose down --rmi local --volumes
