"""FastAPI app: the HTTP surface used by the web UI and by judges (/docs)."""

from __future__ import annotations

import json
from functools import lru_cache
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from .bom_io import BomParseError, load_demo_products, parse_bom_csv
from .config import get_settings
from .dossier.builder import build_dossier
from .engine.origin import evaluate
from .hs.classifier import classify, classify_bom
from .hs.index import get_index
from .llm import get_client
from .models import Dossier, DutyEstimate, HSSuggestion, Product, RulePack, Verdict
from .rulepack.loader import load_rulepack, rulepack_stats
from .tariffs import estimate_duty, load_tariffs

app = FastAPI(
    title="OriginPass CH-CN",
    version="1.0.0",
    description="Rules-of-origin copilot for Swiss SMEs exporting to China (Hack Apertus, Track 2B).",
)


@lru_cache(maxsize=1)
def _pack() -> RulePack:
    return load_rulepack(data_dir=get_settings().data_dir)


@lru_cache(maxsize=1)
def _tariffs() -> dict:
    return load_tariffs(get_settings().data_dir)


@lru_cache(maxsize=1)
def _demo_products() -> dict[str, Product]:
    return load_demo_products(get_settings().data_dir)


@app.on_event("startup")
def _warm() -> None:
    # Build the HS index and load data once, so the first request is fast.
    get_index()
    _pack()
    _tariffs()
    _demo_products()


# ---------------------------------------------------------------------------
# Meta
# ---------------------------------------------------------------------------


@app.get("/api/health")
def health() -> dict:
    s = get_settings()
    client = get_client()
    return {
        "status": "ok",
        "mode": s.effective_mode,
        "llm_name": s.llm_name,
        "llm_name_small": s.llm_name_small,
        "base_url_host": urlparse(s.llm_base_url).hostname,
        "rulepack": {"pack_id": _pack().pack_id, **rulepack_stats(_pack())},
        "replay_entries": len(client.cache),
    }


@app.get("/api/rulepack", response_model=RulePack)
def rulepack() -> RulePack:
    return _pack()


@app.get("/api/stats/cost")
def cost_stats() -> dict:
    return get_client().cost_log.summary()


@app.get("/api/eval/results")
def eval_results() -> dict:
    path = get_settings().data_dir / "eval" / "results" / "summary.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Products and BOMs
# ---------------------------------------------------------------------------


@app.get("/api/products")
def products() -> list[dict]:
    return [
        {"product_id": p.product_id, "name": p.name, "description": p.description, "hs6": p.hs6}
        for p in _demo_products().values()
    ]


@app.get("/api/products/{product_id}", response_model=Product)
def product(product_id: str) -> Product:
    try:
        return _demo_products()[product_id]
    except KeyError:
        raise HTTPException(404, f"unknown product {product_id}") from None


class BomParseRequest(BaseModel):
    csv: str
    name: str
    ex_works_chf: float = Field(gt=0)
    hs6: str | None = None
    description: str = ""


@app.post("/api/bom/parse", response_model=Product)
def bom_parse(req: BomParseRequest) -> Product:
    try:
        return parse_bom_csv(req.csv, req.name, req.ex_works_chf, req.hs6, req.description)
    except BomParseError as exc:
        raise HTTPException(422, str(exc)) from None


# ---------------------------------------------------------------------------
# Origin, HS, dossier
# ---------------------------------------------------------------------------


class EvaluateResponse(BaseModel):
    verdict: Verdict
    duty: DutyEstimate | None


@app.post("/api/evaluate", response_model=EvaluateResponse)
def evaluate_product(product: Product) -> EvaluateResponse:
    verdict = evaluate(product, _pack())
    duty = None
    if product.hs6:
        duty = estimate_duty(product.hs6, product.ex_works_chf * product.shipment.order_quantity, _tariffs())
    return EvaluateResponse(verdict=verdict, duty=duty)


class SuggestRequest(BaseModel):
    description: str = Field(min_length=2)
    k: int = Field(default=10, ge=3, le=25)


@app.post("/api/hs/suggest", response_model=HSSuggestion)
def hs_suggest(req: SuggestRequest) -> HSSuggestion:
    return classify(req.description, get_client(), get_index(), k=req.k)


class ClassifyBomResponse(BaseModel):
    suggestions: dict[str, HSSuggestion]


@app.post("/api/hs/classify-bom", response_model=ClassifyBomResponse)
def hs_classify_bom(product: Product) -> ClassifyBomResponse:
    return ClassifyBomResponse(suggestions=classify_bom(product, get_client(), get_index()))


@app.post("/api/dossier", response_model=Dossier)
def dossier(product: Product) -> Dossier:
    verdict = evaluate(product, _pack())
    return build_dossier(product, verdict, get_client(), _tariffs())
