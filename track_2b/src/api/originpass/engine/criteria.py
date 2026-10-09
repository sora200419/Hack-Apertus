"""Evaluate single origin criteria (WO, CC, CTH, CTSH, MAXNOM, SPECIFIC) and alternatives.

Criteria inside an alternative are AND-ed. Only non-originating materials are
tested. The general tolerance can rescue a criterion whose kind is listed in
`general.tolerance_applies_to` (never MAXNOM or SPECIFIC): if the offending
lines (violating + undecidable) together are <= tolerance_pct % of the
ex-works price, the criterion passes with tolerance_used=True.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from ..models import CheckResult, Criterion, CriterionKind
from ..rulepack.loader import normalise_hs
from .materials import (
    Context,
    Material,
    chf,
    chf_up,
    dec,
    describe_lines,
    limit_str,
    pct_of,
    pct_str,
    total,
    within_pct,
)

SHIFT_DIGITS = {CriterionKind.CC: 2, CriterionKind.CTH: 4, CriterionKind.CTSH: 6}
_SHIFT_UNIT = {CriterionKind.CC: "chapter", CriterionKind.CTH: "heading", CriterionKind.CTSH: "subheading"}
_NO_TOLERANCE = frozenset({CriterionKind.MAXNOM, CriterionKind.SPECIFIC})
_WO_NOTE = (
    "WO (wholly obtained) is rarely relevant for manufactured goods; it is treated as met "
    "only when no non-originating materials are used"
)


@dataclass(frozen=True)
class Outcome:
    """A criterion's CheckResult plus the lines behind it (used for fixes and line flags)."""

    check: CheckResult
    tolerance_used: bool = False
    violating: tuple[Material, ...] = ()
    unknown: tuple[Material, ...] = ()


@dataclass(frozen=True)
class AlternativeEval:
    """One alternative (1-based `index`) of a rule with its per-criterion outcomes."""

    index: int
    criteria: list[Criterion]
    outcomes: tuple[Outcome, ...]

    @property
    def met(self) -> bool | None:
        """True if all criteria pass, False if any fails, else None (also for an empty alternative)."""
        states = [o.check.passed for o in self.outcomes]
        if False in states:
            return False
        if states and all(s is True for s in states):
            return True
        return None

    @property
    def label(self) -> str:
        return " and ".join(criterion_label(c) for c in self.criteria) or "no criteria"

    @property
    def tolerance_used(self) -> bool:
        return any(o.tolerance_used for o in self.outcomes)

    @property
    def maxnom_limits(self) -> list[float]:
        return [c.max_nom_pct for c in self.criteria if c.kind is CriterionKind.MAXNOM and c.max_nom_pct is not None]


def criterion_label(c: Criterion) -> str:
    """Short name, e.g. 'CTH', 'CTH except from 9114', 'MAXNOM 50%'."""
    if c.kind is CriterionKind.MAXNOM:
        return f"MAXNOM {limit_str(c.max_nom_pct)}" if c.max_nom_pct is not None else "MAXNOM"
    if c.except_from:
        return f"{c.kind.value} except from {', '.join(normalise_hs(p) for p in c.except_from)}"
    return c.kind.value


def shift_violation(c: Criterion, product_hs6: str, hs6: str) -> str | None:
    """Why a non-originating material with `hs6` breaks the tariff shift `c`, or None if it satisfies it."""
    for prefix in map(normalise_hs, c.except_from):
        if prefix and hs6.startswith(prefix):
            return f"excluded by 'except from {prefix}'"
    n = SHIFT_DIGITS[c.kind]
    if hs6[:n] == product_hs6[:n]:
        return f"same {_SHIFT_UNIT[c.kind]} {hs6[:n]} as the product"
    return None


def evaluate_alternative(index: int, criteria: list[Criterion], ctx: Context) -> AlternativeEval:
    return AlternativeEval(index, criteria, tuple(evaluate_criterion(c, ctx) for c in criteria))


def evaluate_criterion(c: Criterion, ctx: Context) -> Outcome:
    if c.kind in SHIFT_DIGITS:
        return _shift(c, ctx)
    if c.kind is CriterionKind.MAXNOM:
        return _maxnom(c, ctx)
    if c.kind is CriterionKind.WO:
        return _wo(c, ctx)
    detail = f"specific requirement, needs human judgement: {c.note or 'see the rule text'}"
    return Outcome(CheckResult(name=criterion_label(c), passed=None, detail=detail))


def _shift(c: Criterion, ctx: Context) -> Outcome:
    unit = _SHIFT_UNIT[c.kind]
    own = ctx.product_hs6[: SHIFT_DIGITS[c.kind]]
    nom = ctx.non_originating
    violating: list[Material] = []
    parts: list[str] = []
    for m in nom:
        why = shift_violation(c, ctx.product_hs6, m.hs6) if m.hs6 else None
        if why:
            violating.append(m)
            parts.append(f"{m.describe()}: {why}")
    unknown = [m for m in nom if m.hs6 is None]
    parts += [f"{m.describe()}: no 6-digit HS code, cannot be checked" for m in unknown]
    if not parts:
        if not nom:
            detail = f"no non-originating materials, so the change of {unit} is satisfied"
        else:
            excluded = " and outside the excluded codes" if c.except_from else ""
            detail = (
                f"all {len(nom)} non-originating material(s) are classified outside the product's "
                f"{unit} {own}{excluded}"
            )
        return Outcome(CheckResult(name=criterion_label(c), passed=True, detail=detail))
    failure = f"non-originating materials must change {unit} (product {unit} {own}); not satisfied by " + "; ".join(
        parts
    )
    return _resolve(c, ctx, failure, tuple(violating), tuple(unknown))


def _wo(c: Criterion, ctx: Context) -> Outcome:
    nom = ctx.non_originating
    if not nom:
        return Outcome(
            CheckResult(name=criterion_label(c), passed=True, detail=f"no non-originating materials; {_WO_NOTE}")
        )
    failure = f"{_WO_NOTE}; non-originating {describe_lines(nom)} used"
    return _resolve(c, ctx, failure, nom, ())


def _resolve(
    c: Criterion, ctx: Context, failure: str, violating: tuple[Material, ...], unknown: tuple[Material, ...]
) -> Outcome:
    """Decide a criterion broken by `violating` and undecidable for `unknown`, applying the tolerance.

    passed=True (tolerance_used) if violating+unknown together fit in the
    tolerance; False if the violating lines alone do not fit (or no tolerance
    applies and there are violating lines); otherwise None, because the result
    depends on lines that have no HS code yet.
    """
    name = criterion_label(c)
    offending = violating + unknown
    applies = tolerance_applies(c, ctx)
    tol_pct = ctx.general.tolerance_pct
    off_total = total(offending)
    share = f"{chf(off_total)} ({pct_str(pct_of(off_total, ctx.ex_works))})"
    allowance = f"{limit_str(tol_pct)} of the ex-works price ({chf(tolerance_limit(ctx))})"
    if applies and within_pct(off_total, tol_pct, ctx.ex_works):
        detail = f"{failure}. Met under the general tolerance: together {share}, within {allowance}"
        check = CheckResult(name=name, passed=True, detail=detail, line_ids=_ids(offending))
        return Outcome(check, True, violating, unknown)
    if applies:
        note = f"together {share}, more than the general tolerance of {allowance}"
    else:
        note = f"the general tolerance does not apply to {c.kind.value}"
    if violating and not (applies and within_pct(total(violating), tol_pct, ctx.ex_works)):
        check = CheckResult(name=name, passed=False, detail=f"{failure}; {note}", line_ids=_ids(violating))
        return Outcome(check, False, violating, unknown)
    detail = f"{failure}; {note}; undecided until the unclassified line(s) get an HS code"
    return Outcome(
        CheckResult(name=name, passed=None, detail=detail, line_ids=_ids(unknown)), False, violating, unknown
    )


def _maxnom(c: Criterion, ctx: Context) -> Outcome:
    name = criterion_label(c)
    if c.max_nom_pct is None:
        return Outcome(CheckResult(name=name, passed=None, detail="rule encoding error: MAXNOM without max_nom_pct"))
    nom = ctx.nom_value
    limit = dec(c.max_nom_pct) * ctx.ex_works / 100
    ok = within_pct(nom, c.max_nom_pct, ctx.ex_works)
    detail = (
        f"non-originating materials {chf(nom)} = {pct_str(pct_of(nom, ctx.ex_works))} of the ex-works price "
        f"{chf(ctx.ex_works)}; limit {limit_str(c.max_nom_pct)} ({chf(limit)}); "
        + ("within the limit" if ok else f"over the limit by {chf_up(nom - limit)}")
        + "; the general tolerance never applies to MAXNOM"
    )
    return Outcome(CheckResult(name=name, passed=ok, detail=detail, line_ids=_ids(ctx.non_originating)))


def _ids(materials: tuple[Material, ...]) -> list[str]:
    return [m.line_id for m in materials]


def tolerance_limit(ctx: Context) -> Decimal:
    """General tolerance in CHF for this product."""
    return dec(ctx.general.tolerance_pct) * ctx.ex_works / 100


def tolerance_applies(c: Criterion, ctx: Context) -> bool:
    return c.kind in ctx.general.tolerance_applies_to and c.kind not in _NO_TOLERANCE
