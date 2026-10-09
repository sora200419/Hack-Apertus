"""General origin checks that apply whatever the product-specific rule: insufficient processing, direct transport."""

from __future__ import annotations

import re

from ..models import CheckResult, GeneralProvisions, Product

INSUFFICIENT = "insufficient processing"
DIRECT_TRANSPORT = "direct transport"
_COUNTRY_NAMES = {"CH": "Switzerland", "CN": "China"}
# Clause boundaries inside one operation text: ';', '&', '+', a comma not inside a number, conjunctions.
_CLAUSE_SEPARATORS = re.compile(r"[;&+]|,(?!\d)|\b(?:and|or|then|und|oder|sowie|dann|et|ou|puis)\b", re.IGNORECASE)


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


def unmatched_clauses(operation: str, keywords: list[str]) -> list[str]:
    """Clauses of `operation` that contain no keyword: 'CNC machining and packing' -> ['CNC machining']."""
    clauses = (c.strip() for c in _CLAUSE_SEPARATORS.split(operation))
    return [c for c in clauses if normalise_text(c) and matched_keyword(c, keywords) is None]


def insufficient_processing(product: Product, general: GeneralProvisions) -> CheckResult:
    """Screen the described operations against the insufficient-operation keywords (Art. 3.6).

    None if no processing is described; True if some operation matches no keyword; False if every
    operation consists only of keyword clauses; otherwise None (keywords mixed with other work).

    Matching is keyword screening: each `general.insufficient_operations` entry is
    looked for as a whole-word phrase (case-insensitive, punctuation ignored)
    inside each operation, so packs should list short keywords ('packing',
    'labelling', 'simple assembly'). An operation such as 'CNC machining and
    packing' matches 'packing' but also describes other work, so it can neither
    pass nor fail the check on its own. True therefore means "not obviously
    insufficient", not a legal confirmation of sufficient processing.
    """
    ops = operations(product)
    country = _COUNTRY_NAMES.get(product.exporter_country, product.exporter_country)
    if not ops:
        return CheckResult(name=INSUFFICIENT, passed=None, detail=f"describe the processing done in {country}")
    keywords = general.insufficient_operations
    matches = [(op, matched_keyword(op, keywords)) for op in ops]
    sufficient = [op for op, kw in matches if kw is None]
    mixed = [(op, kw, rest) for op, kw in matches if kw and (rest := unmatched_clauses(op, keywords))]
    if mixed and not sufficient:
        listed = "; ".join(f"'{op}' (matches '{kw}', but also '{', '.join(rest)}')" for op, kw, rest in mixed)
        detail = (
            f"no operation described in {country} clearly goes beyond the listed insufficient operations, and "
            f"{listed} mixes them with other work that keyword screening cannot judge; list each operation "
            "separately"
        )
        return CheckResult(name=INSUFFICIENT, passed=None, detail=detail)
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

    A declared transshipment/storage flag without countries is treated as transit too. None as well
    when exporter and destination are the same Party (Art. 3.13(1): transport between the Parties).
    """
    shipment = product.shipment
    if shipment.destination == product.exporter_country:
        detail = (
            f"exporter and destination are both {product.exporter_country}: preferences apply only to goods "
            "transported between the Parties, so set the destination to the other Party"
        )
        return CheckResult(name=DIRECT_TRANSPORT, passed=None, detail=detail)
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
