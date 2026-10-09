"""Shared data contracts for OriginPass CH-CN.

Every module (engine, hs, dossier, API, eval, web) exchanges these models.
Change them only together with all consumers.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, model_validator

# Parties to the Switzerland-China FTA. Materials originating in either party
# count as originating (bilateral cumulation), subject to the rule pack.
PARTIES = ("CH", "CN")


# ---------------------------------------------------------------------------
# Input: a product and its bill of materials
# ---------------------------------------------------------------------------


class BomLine(BaseModel):
    line_id: str
    description: str = Field(description="Free-text part description, any language")
    hs6: str | None = Field(
        default=None, description="6-digit HS 2022 code of the material, if known"
    )
    origin_country: str = Field(description="ISO 3166-1 alpha-2, e.g. CH, CN, DE, JP")
    value_chf: float = Field(ge=0, allow_inf_nan=False, description="Value of this material per unit of product, CHF")
    supplier: str | None = None
    originating_override: bool | None = Field(
        default=None,
        description="Set when the exporter holds proof that the material is originating "
        "(e.g. supplier declaration). None = derive from origin_country.",
    )


class Shipment(BaseModel):
    destination: Literal["CN", "CH"] = "CN"
    transit_countries: list[str] = Field(default_factory=list)
    transshipment_or_storage_in_transit: bool = False
    order_quantity: int = Field(default=1, ge=1)


class Product(BaseModel):
    product_id: str
    name: str
    description: str
    hs6: str | None = Field(default=None, description="6-digit HS code of the finished product")
    ex_works_chf: float = Field(gt=0, allow_inf_nan=False, description="Ex-works price per unit, CHF")
    exporter_country: Literal["CH", "CN"] = "CH"
    processing: list[str] = Field(
        default_factory=list,
        description="Operations carried out in the exporting party, plain text",
    )
    bom: list[BomLine]
    shipment: Shipment = Field(default_factory=Shipment)

    @model_validator(mode="after")
    def _unique_line_ids(self) -> "Product":
        ids = [ln.line_id for ln in self.bom]
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        if dupes:
            raise ValueError(f"duplicate BOM line_id(s): {', '.join(dupes)}")
        return self


# ---------------------------------------------------------------------------
# Rule pack (encoded from Annex II of the FTA)
# ---------------------------------------------------------------------------


class CriterionKind(str, Enum):
    WO = "WO"  # wholly obtained
    CC = "CC"  # change of chapter (2-digit)
    CTH = "CTH"  # change of tariff heading (4-digit)
    CTSH = "CTSH"  # change of tariff sub-heading (6-digit)
    MAXNOM = "MAXNOM"  # non-originating materials <= x % of ex-works price
    SPECIFIC = "SPECIFIC"  # specific processing, decided by a human -> UNSURE


class Criterion(BaseModel):
    kind: CriterionKind
    max_nom_pct: float | None = Field(default=None, description="Only for MAXNOM")
    except_from: list[str] = Field(
        default_factory=list,
        description="HS prefixes whose non-originating materials do NOT satisfy the shift, "
        "e.g. CTH 'except from heading 91.14' -> ['9114']",
    )
    note: str | None = None


class Rule(BaseModel):
    rule_id: str
    hs_scope: list[str] = Field(
        description="HS prefixes (2/4/6 digits) this rule covers; most specific prefix wins"
    )
    # A product qualifies if ANY alternative is met; an alternative is met if ALL its criteria are met.
    alternatives: list[list[Criterion]]
    text: str = Field(description="Rule text quoted verbatim from the source")
    text_zh: str | None = None
    source: str = Field(description="Document + page/line reference")
    verified: bool = Field(
        default=False,
        description="True only after a human compared `text` and the encoding with the official text",
    )


class GeneralProvisions(BaseModel):
    tolerance_pct: float = Field(description="General de-minimis tolerance, % of ex-works price")
    tolerance_applies_to: list[CriterionKind]
    tolerance_text: str
    insufficient_operations: list[str] = Field(
        description="Operations that never confer origin on their own"
    )
    insufficient_operations_text: str
    cumulation_parties: list[str] = Field(default_factory=lambda: list(PARTIES))
    direct_transport_text: str
    max_items_per_certificate: int | None = None
    source: str
    verified: bool = False


class RulePack(BaseModel):
    pack_id: str
    agreement: str
    version_note: str
    general: GeneralProvisions
    rules: list[Rule]


# ---------------------------------------------------------------------------
# Output: origin verdict
# ---------------------------------------------------------------------------


class VerdictStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNSURE = "UNSURE"


class CheckResult(BaseModel):
    name: str = Field(description="e.g. 'CTH', 'MAXNOM 50%', 'insufficient processing'")
    passed: bool | None = Field(description="None = could not be decided")
    detail: str
    line_ids: list[str] = Field(default_factory=list, description="BOM lines that drive this check")


class AlternativeResult(BaseModel):
    criteria: list[Criterion]
    met: bool | None
    checks: list[CheckResult]


class LineAssessment(BaseModel):
    line_id: str
    originating: bool
    reason: str
    hs6: str | None
    value_chf: float
    shift_ok: bool | None = Field(
        default=None, description="Does this line satisfy the tariff shift of the chosen rule?"
    )


class Verdict(BaseModel):
    product_id: str
    status: VerdictStatus
    hs6: str | None
    rule: Rule | None
    rule_verified: bool
    alternatives: list[AlternativeResult] = Field(default_factory=list)
    general_checks: list[CheckResult] = Field(default_factory=list)
    lines: list[LineAssessment] = Field(default_factory=list)
    nom_value_chf: float
    nom_pct: float = Field(description="Non-originating materials as % of ex-works price")
    threshold_pct: float | None = None
    margin_pct: float | None = Field(
        default=None, description="threshold - nom_pct; positive = headroom"
    )
    tolerance_used: bool = False
    reasons: list[str] = Field(default_factory=list, description="Plain-English trace, ordered")
    fixes: list[str] = Field(default_factory=list, description="Cheapest changes that would flip FAIL to PASS")


# ---------------------------------------------------------------------------
# HS classification
# ---------------------------------------------------------------------------


class HSCandidate(BaseModel):
    hs6: str
    description: str
    score: float
    source: Literal["bm25", "tfidf", "fused"] = "fused"


class HSSuggestion(BaseModel):
    query: str
    candidates: list[HSCandidate]
    chosen: str | None = Field(description="Chosen HS6, None when abstaining")
    confidence: float = Field(ge=0, le=1)
    rationale: str
    abstained: bool
    method: Literal["llm", "retrieval_only", "fallback"]
    llm_source: Literal["live", "replay", "none"] = "none"


# ---------------------------------------------------------------------------
# Dossier
# ---------------------------------------------------------------------------


class FactCheck(BaseModel):
    fact: str
    expected: str
    found: bool


class DossierText(BaseModel):
    lang: str
    text: str
    llm_source: Literal["live", "replay", "template"]
    fact_checks: list[FactCheck] = Field(default_factory=list)
    attempts: int = 1


class Dossier(BaseModel):
    product_id: str
    verdict_status: VerdictStatus
    explanation_en: DossierText
    explanation_de: DossierText
    letter_zh: DossierText
    back_translation_en: DossierText
    checklist: list[str]
    duty: DutyEstimate | None = None


class DutyEstimate(BaseModel):
    hs6: str
    mfn_rate_pct: float | None
    fta_rate_pct: float | None
    order_value_chf: float
    duty_saved_chf: float | None
    source: str


Dossier.model_rebuild()
