"""General origin checks that apply whatever the product-specific rule: insufficient processing, direct transport."""

from __future__ import annotations

import re

from ..models import CheckResult, GeneralProvisions, Product

INSUFFICIENT = "insufficient processing"
DIRECT_TRANSPORT = "direct transport"
_COUNTRY_NAMES = {"CH": "Switzerland", "CN": "China"}


def normalise_text(text: str) -> str:
    """Casefold, turn punctuation into spaces, collapse whitespace: 'Re-Packing,  labels' -> 're packing labels'."""
    return " ".join(re.sub(r"[\W_]+", " ", text.casefold()).split())


def matched_keyword(operation: str, keywords: list[str]) -> str | None:
    """First keyword found as a whole-word phrase inside the operation text, else None."""
    padded = f" {normalise_text(operation)} "
    for keyword in keywords:
        kw = normalise_text(keyword)
        if kw and f" {kw} " in padded:
            return keyword
    return None


def operations(product: Product) -> list[str]:
    return [op.strip() for op in product.processing if op.strip()]


def insufficient_processing(product: Product, general: GeneralProvisions) -> CheckResult:
    """None if no processing is described; False if EVERY operation matches a keyword; else True.

    Matching is keyword screening: each `general.insufficient_operations` entry is
    looked for as a whole-word phrase (case-insensitive, punctuation ignored)
    inside each operation, so packs should list short keywords ('packing',
    'labelling', 'simple assembly'). True therefore means "not obviously
    insufficient", not a legal confirmation of sufficient processing.
    """
    ops = operations(product)
    country = _COUNTRY_NAMES.get(product.exporter_country, product.exporter_country)
    if not ops:
        return CheckResult(name=INSUFFICIENT, passed=None, detail=f"describe the processing done in {country}")
    matches = [(op, matched_keyword(op, general.insufficient_operations)) for op in ops]
    sufficient = [op for op, kw in matches if kw is None]
    if not sufficient:
        listed = "; ".join(f"'{op}' (matches '{kw}')" for op, kw in matches)
        detail = (
            f"all {len(ops)} operation(s) described in {country} are insufficient operations that cannot "
            f"confer origin on their own: {listed}"
        )
        return CheckResult(name=INSUFFICIENT, passed=False, detail=detail)
    detail = (
        f"{len(sufficient)} of {len(ops)} operation(s) go beyond the listed insufficient operations "
        f"(e.g. '{sufficient[0]}'); keyword screening only, not a legal assessment of the processing"
    )
    return CheckResult(name=INSUFFICIENT, passed=True, detail=detail)


def insufficient_processing_fix(product: Product) -> str:
    """Fix sentence when insufficient processing failed (re-sourcing cannot help)."""
    country = _COUNTRY_NAMES.get(product.exporter_country, product.exporter_country)
    return (
        f"All {len(operations(product))} operation(s) described count as insufficient processing, so re-sourcing "
        f"materials cannot confer origin; origin needs processing in {country} beyond these operations."
    )


def direct_transport(product: Product) -> CheckResult:
    """True if no transit is declared; None (evidence needed) if transit or transshipment/storage is declared.

    A declared transshipment/storage flag without countries is treated as transit too.
    """
    shipment = product.shipment
    transit = list(dict.fromkeys(c.strip().upper() for c in shipment.transit_countries if c.strip()))
    if not transit and not shipment.transshipment_or_storage_in_transit:
        detail = f"shipped directly from {product.exporter_country} to {shipment.destination}, no transit declared"
        return CheckResult(name=DIRECT_TRANSPORT, passed=True, detail=detail)
    via = f"through {', '.join(transit)}" if transit else "with an intermediate stop"
    storage = " with transshipment or storage" if shipment.transshipment_or_storage_in_transit and transit else ""
    detail = (
        f"goods travel {via}{storage}: keep non-manipulation evidence showing they were not processed "
        "or altered in transit, as required by the direct transport rule"
    )
    return CheckResult(name=DIRECT_TRANSPORT, passed=None, detail=detail)


def general_checks(product: Product, general: GeneralProvisions) -> list[CheckResult]:
    return [insufficient_processing(product, general), direct_transport(product)]
