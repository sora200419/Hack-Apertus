"""Deterministic export checklist (documents and steps), adapted to the verdict status.

Items describe what to keep or obtain; they quote no legal wording. Where the FTA prescribes a text or a
period, the item says to take it from the official text instead of restating it here.
"""

from __future__ import annotations

from ..engine.general import DIRECT_TRANSPORT
from ..models import Product, Verdict, VerdictStatus
from .facts import fmt_num, open_checks

_PROOF_OF_ORIGIN = (
    "Proof of origin: a certificate of origin (原产地证书) issued by the competent authority, or an origin "
    "declaration (原产地声明) made out by an approved exporter (经核准出口商)."
)
_APPROVED_EXPORTER = (
    "Origin declaration: only an approved exporter may make it out; copy the declaration wording and the "
    "authorisation number exactly as prescribed by the official FTA text, without paraphrasing."
)


def build_checklist(product: Product, verdict: Verdict) -> list[str]:
    """Documents to obtain or keep and steps to take before shipping, given the verdict."""
    items: list[str] = []
    status = verdict.status
    undecided = [c for c in open_checks(verdict) if c.passed is None]
    if status is VerdictStatus.PASS:
        items += [_PROOF_OF_ORIGIN, _APPROVED_EXPORTER]
    elif status is VerdictStatus.FAIL:
        items.append(
            "Do not issue a certificate of origin or an origin declaration: the product does not qualify, so the "
            "importer pays the MFN rate (最惠国税率)."
        )
        items += [f"Fix option: {fix}" for fix in verdict.fixes]
        items.append("After any change of supplier or process, re-run the origin check before shipping.")
    else:
        items.append(
            "Do not issue a proof of origin until the open points below are resolved and the check reads PASS."
        )
        if verdict.hs6 is None or verdict.rule is None:
            items.append(
                "Classify the finished product (6-digit HS code) and make sure a product-specific rule applies, "
                "then re-run the origin check."
            )
        items += [f"Open point - {c.name}: {c.detail.rstrip('.')}." for c in undecided]
    if status is not VerdictStatus.FAIL and all(c.name != DIRECT_TRANSPORT for c in undecided):
        items.append(
            "Direct transport: keep the transport documents (e.g. bill of lading or air waybill) showing shipment "
            f"from {product.exporter_country} to {product.shipment.destination}."
        )
    originating = [line.line_id for line in verdict.lines if line.originating]
    if originating:
        items.append(
            f"Supplier evidence for the materials counted as originating ({', '.join(originating)}): obtain from "
            "each supplier a declaration or proof of its originating status (materials from Switzerland or China "
            "count through bilateral cumulation); without it the line counts as non-originating."
        )
    if verdict.tolerance_used:
        items.append("The general tolerance was used: document the value of the non-originating lines it covers.")
    if verdict.rule is not None and not verdict.rule_verified:
        items.append(
            "The rule encoding is not yet verified against the official Annex II text: have it checked before "
            "relying on the verdict."
        )
    items.append(
        f"Keep the calculation records (bill of materials, supplier invoices and declarations, this calculation: "
        f"non-originating materials {fmt_num(verdict.nom_pct)}% of the ex-works price) for the retention period "
        "set by the FTA."
    )
    return items
