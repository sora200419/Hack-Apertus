"""Deterministic origin verdict: product + rule pack -> Verdict.

Semantics (no LLM involved; same input always gives the same JSON):

1. No valid 6-digit product HS code -> UNSURE ('classify the product first');
   no encoded rule for it -> UNSURE. Lines, non-originating share and general
   checks are still reported for display.
2. A BOM line is originating if `originating_override` says so, otherwise if its
   origin country is a cumulation party (bilateral cumulation, assuming the
   supplier provides proof of origin). nom_pct = 100 * non-originating value /
   ex-works price; comparisons are exact (Decimal), display is rounded to 2 dp.
3. A rule's alternatives are OR-ed, criteria inside an alternative AND-ed
   (see engine.criteria for each criterion kind and the general tolerance).
4. General checks: insufficient processing, direct transport (engine.general).
5. FAIL if every alternative fails or any general check fails; PASS if an
   alternative is met and every general check passes; otherwise UNSURE.
   `rule_verified` is reported but never changes the status.
6. threshold_pct is the strictest MAXNOM limit of the alternative closest to
   being met among those that have one; margin_pct = threshold - nom_pct.
7. Fixes (engine.fixes) are given only when no alternative is met; if the
   processing is insufficient, the only fix says that re-sourcing cannot help.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from ..models import (
    AlternativeResult,
    CheckResult,
    Criterion,
    LineAssessment,
    Product,
    RulePack,
    Verdict,
    VerdictStatus,
)
from ..rulepack.loader import find_rule, matching_prefix
from .criteria import SHIFT_DIGITS, AlternativeEval, evaluate_alternative, shift_violation
from .fixes import suggest_fixes
from .general import general_checks, insufficient_processing_fix
from .materials import CENT, Context, Material, assess_material, chf, dec, hs6_or_none, pct_of, pct_str, total

UNVERIFIED = "Rule encoding not yet verified against the official Annex II text"
_MET_RANK = {True: 0, None: 1, False: 2}
_STATE = {True: "passed", False: "failed", None: "undecided"}
_ALT_STATE = {True: "met", False: "not met", None: "undecided"}
_CHANGE_KEYS = frozenset({"line_id", "origin_country", "value_chf", "hs6", "originating_override"})


def evaluate(product: Product, pack: RulePack) -> Verdict:
    """Compute the origin verdict of `product` under `pack` (see module docstring)."""
    parties = [p.strip().upper() for p in pack.general.cumulation_parties]
    materials = tuple(assess_material(line, parties) for line in product.bom)
    ex_works = dec(product.ex_works_chf)
    nom_lines = tuple(m for m in materials if not m.originating)
    nom_value = total(nom_lines)
    nom_pct = pct_of(nom_value, ex_works)
    general = general_checks(product, pack.general)
    hs6 = hs6_or_none(product.hs6)
    summary = (
        f"Materials: {len(nom_lines)} of {len(materials)} BOM line(s) are non-originating, {chf(nom_value)} = "
        f"{pct_str(nom_pct)} of the ex-works price {chf(ex_works)}; materials from {'/'.join(parties)} count as "
        "originating (bilateral cumulation), assuming the supplier provides proof of origin."
    )
    base = dict(
        product_id=product.product_id,
        hs6=hs6 or product.hs6,
        general_checks=general,
        nom_value_chf=float(nom_value),
        nom_pct=float(nom_pct.quantize(CENT, ROUND_HALF_UP)),
    )

    rule = find_rule(pack, hs6) if hs6 else None
    if rule is None:
        problem = (
            "classify the product first (no valid 6-digit HS code for the finished product)"
            if hs6 is None
            else f"no product-specific rule encoded for HS {hs6}"
        )
        reasons = [f"Status UNSURE: {problem}.", summary, *_general_reasons(general)]
        return Verdict(
            **base,
            status=VerdictStatus.UNSURE,
            rule=None,
            rule_verified=False,
            lines=[_line(m, None, "") for m in materials],
            reasons=reasons,
        )

    ctx = Context(hs6, ex_works, materials, pack.general)
    alts = [evaluate_alternative(i, crit, ctx) for i, crit in enumerate(rule.alternatives, start=1)]
    ranked = sorted(alts, key=lambda a: _closeness(a, nom_pct))
    status = _status(alts, general)
    threshold = _threshold(ranked)
    verified = rule.verified and pack.general.verified
    best = ranked[0] if ranked else None

    reasons = [
        f"Rule {rule.rule_id} applies to HS {hs6} (most specific encoded scope {matching_prefix(rule, hs6)}); "
        f"source: {rule.source}.",
        summary,
        *_alternative_reasons(alts),
        *_general_reasons(general),
    ]
    if not verified:
        reasons.append(f"{UNVERIFIED} ({_unverified_parts(rule.verified, pack.general.verified, rule.rule_id)}).")
    reasons.append(_conclusion(status, best, general))

    # Fixes: re-sourcing cannot cure insufficient processing, and is pointless once an alternative is met.
    fixes: list[str] = []
    if any(c.passed is False for c in general):
        fixes = [insufficient_processing_fix(product)]
    elif not any(a.met is True for a in alts):
        fixes = suggest_fixes(ranked, ctx)

    reference = next((c for a in ranked for c in a.criteria if c.kind in SHIFT_DIGITS), None)
    return Verdict(
        **base,
        status=status,
        rule=rule.model_copy(deep=True),  # the verdict must not alias the (possibly cached) pack
        rule_verified=verified,
        alternatives=[
            AlternativeResult(
                criteria=[c.model_copy(deep=True) for c in a.criteria],
                met=a.met,
                checks=[o.check for o in a.outcomes],
            )
            for a in alts
        ],
        lines=[_line(m, reference, hs6) for m in materials],
        threshold_pct=threshold,
        margin_pct=None if threshold is None else float((dec(threshold) - nom_pct).quantize(CENT, ROUND_HALF_UP)),
        tolerance_used=bool(best and best.tolerance_used),
        reasons=reasons,
        fixes=fixes,
    )


def apply_changes(product: Product, changes: list[dict]) -> Product:
    """What-if: return a validated deep copy of `product` with BOM line edits applied.

    Each change is {line_id, origin_country?, value_chf?, hs6?, originating_override?};
    later changes to the same line win. Raises ValueError for an unknown or
    duplicated line_id, an unknown key, or an invalid value. The input is never mutated.
    """
    data = product.model_dump()
    for change in changes:
        unknown = set(change) - _CHANGE_KEYS
        if unknown or "line_id" not in change:
            raise ValueError(f"invalid change {change!r}: allowed keys are {sorted(_CHANGE_KEYS)} incl. line_id")
        targets = [line for line in data["bom"] if line["line_id"] == change["line_id"]]
        if len(targets) != 1:
            raise ValueError(f"line_id {change['line_id']!r} matches {len(targets)} BOM lines, expected 1")
        targets[0].update({k: v for k, v in change.items() if k != "line_id"})
    return Product.model_validate(data)


def _closeness(alt: AlternativeEval, nom_pct: Decimal) -> tuple:
    """Sort key, smaller = closer to being met.

    Order: met state, #failed, #undecided criteria, reliance on the tolerance, MAXNOM excess, rule order.
    """
    states = [o.check.passed for o in alt.outcomes]
    excess = max((nom_pct - dec(limit) for limit in alt.maxnom_limits), default=Decimal(0))
    return (
        _MET_RANK[alt.met],
        states.count(False),
        states.count(None),
        alt.tolerance_used,
        max(excess, Decimal(0)),
        alt.index,
    )


def _status(alts: list[AlternativeEval], general: list[CheckResult]) -> VerdictStatus:
    if any(c.passed is False for c in general) or (alts and all(a.met is False for a in alts)):
        return VerdictStatus.FAIL
    if any(a.met is True for a in alts) and all(c.passed is True for c in general):
        return VerdictStatus.PASS
    return VerdictStatus.UNSURE


def _threshold(ranked: list[AlternativeEval]) -> float | None:
    """Strictest MAXNOM limit of the closest alternative that has one."""
    with_maxnom = [a for a in ranked if a.maxnom_limits]
    return min(with_maxnom[0].maxnom_limits) if with_maxnom else None


def _line(m: Material, reference: Criterion | None, product_hs6: str) -> LineAssessment:
    """shift_ok against the tariff shift of the closest alternative (else the next one that has one).

    Originating lines satisfy it trivially (True); a non-originating line without
    HS6, or a rule without any tariff shift, gives None.
    """
    if reference is None:
        shift_ok = None
    elif m.originating:
        shift_ok = True
    elif m.hs6 is None:
        shift_ok = None
    else:
        shift_ok = shift_violation(reference, product_hs6, m.hs6) is None
    return LineAssessment(
        line_id=m.line_id,
        originating=m.originating,
        reason=m.reason,
        hs6=m.hs6 or m.line.hs6,
        value_chf=m.line.value_chf,
        shift_ok=shift_ok,
    )


def _alternative_reasons(alts: list[AlternativeEval]) -> list[str]:
    reasons: list[str] = []
    for a in alts:
        reasons.append(f"Alternative {a.index} ({a.label}): {_ALT_STATE[a.met]}.")
        for o in a.outcomes:
            reasons.append(f"Alternative {a.index}, {o.check.name}: {_STATE[o.check.passed]}: {o.check.detail}.")
            if o.tolerance_used:
                reasons.append(
                    f"General tolerance used for {o.check.name} in alternative {a.index} "
                    f"(lines {', '.join(o.check.line_ids)})."
                )
    return reasons


def _general_reasons(general: list[CheckResult]) -> list[str]:
    return [f"General check '{c.name}': {_STATE[c.passed]}: {c.detail}." for c in general]


def _unverified_parts(rule_ok: bool, general_ok: bool, rule_id: str) -> str:
    parts = ([] if rule_ok else [f"product-specific rule {rule_id}"]) + ([] if general_ok else ["general provisions"])
    return "unverified: " + " and ".join(parts)


def _conclusion(status: VerdictStatus, best: AlternativeEval | None, general: list[CheckResult]) -> str:
    failed = [c.name for c in general if c.passed is False]
    open_checks = [c.name for c in general if c.passed is None]
    if status is VerdictStatus.PASS:
        return f"Verdict PASS: alternative {best.index} ({best.label}) is met and all general checks pass."
    if status is VerdictStatus.FAIL:
        if failed:
            return f"Verdict FAIL: general check(s) failed: {', '.join(failed)}."
        return "Verdict FAIL: no alternative of the rule is met."
    pending = ", ".join(open_checks) if open_checks else "none"
    if best is not None and best.met is True:
        return f"Verdict UNSURE: alternative {best.index} ({best.label}) is met; open general checks: {pending}."
    return f"Verdict UNSURE: no alternative is decided as met yet; open general checks: {pending}."
