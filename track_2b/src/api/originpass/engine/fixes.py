"""Turn failed or undecided criteria into concrete, numbered fix sentences.

Assumption behind every re-sourcing fix: the replacement material from a
cumulation party costs the same and comes with proof of origin, so the
non-originating value drops by exactly the line's value.
"""

from __future__ import annotations

from decimal import Decimal

from ..models import Criterion, CriterionKind
from .criteria import SHIFT_DIGITS, AlternativeEval, Outcome, criterion_label, tolerance_applies, tolerance_limit
from .materials import (
    Context,
    Material,
    chf,
    chf_down,
    chf_up,
    dec,
    describe_lines,
    limit_str,
    pct_of,
    pct_str,
    total,
)


def suggest_fixes(ranked: list[AlternativeEval], ctx: Context) -> list[str]:
    """One sentence per failed or undecided criterion, closest alternative first (met ones yield none)."""
    fixes: list[str] = []
    for alt in ranked:
        prefix = f"Alternative {alt.index} ({alt.label}):"
        for criterion, outcome in zip(alt.criteria, alt.outcomes, strict=True):
            if outcome.check.passed is True:
                continue
            sentence = _fix(criterion, outcome, ctx)
            if sentence:
                fixes.append(f"{prefix} {sentence}")
    return fixes


def _fix(c: Criterion, outcome: Outcome, ctx: Context) -> str | None:
    if c.kind is CriterionKind.MAXNOM:
        return maxnom_fix(c, ctx)
    if c.kind in SHIFT_DIGITS or c.kind is CriterionKind.WO:
        return _offending_fix(c, outcome, ctx)
    return None


def lines_to_resource(nom: tuple[Material, ...], gap: Decimal) -> list[Material]:
    """Smallest single line with value >= gap; else the greedy set by descending value (ties: BOM order)."""
    singles = [m for m in nom if m.value >= gap]
    if singles:
        return [min(singles, key=lambda m: m.value)]
    chosen: list[Material] = []
    for m in sorted(nom, key=lambda m: m.value, reverse=True):
        chosen.append(m)
        if total(chosen) >= gap:
            break
    return chosen


def maxnom_fix(c: Criterion, ctx: Context) -> str | None:
    """How much non-originating value must go, and which line(s) to re-source to get there."""
    if c.max_nom_pct is None:
        return None
    nom = ctx.nom_value
    limit = dec(c.max_nom_pct) * ctx.ex_works / 100
    gap = nom - limit
    if gap <= 0:
        return None
    chosen = lines_to_resource(ctx.non_originating, gap)
    if len(chosen) == 1:
        action = f"re-source {describe_lines(chosen, with_hs=False)} from a {ctx.parties} supplier with proof of origin"
    else:
        action = (
            f"no single line is enough, so re-source {describe_lines(chosen, with_hs=False)} "
            f"(together {chf(total(chosen))}) from {ctx.parties} suppliers with proof of origin"
        )
    return (
        f"non-originating materials must fall by at least {chf_up(gap)}, from {chf(nom)} "
        f"({pct_str(pct_of(nom, ctx.ex_works))}) to at most {chf_down(limit)} ({limit_str(c.max_nom_pct)} of "
        f"the ex-works price {chf(ctx.ex_works)}); {action}, assuming the same price."
    )


def _offending_fix(c: Criterion, outcome: Outcome, ctx: Context) -> str:
    """List the lines that break a tariff shift (or WO) and what would cure them."""
    label = criterion_label(c)
    parts: list[str] = []
    if outcome.violating:
        lines = outcome.violating
        together = f" (together {chf(total(lines))})" if len(lines) > 1 else ""
        parts.append(
            f"{label} is broken by {describe_lines(lines)}{together}; re-source "
            f"{'it' if len(lines) == 1 else 'them'} from {ctx.parties} suppliers with proof of origin"
        )
    if outcome.unknown:
        parts.append(f"classify {describe_lines(outcome.unknown)} to a 6-digit HS code so {label} can be checked")
    sentence = "; ".join(parts)
    if tolerance_applies(c, ctx):
        sentence += (
            f", or keep these lines at or below {chf_down(tolerance_limit(ctx))} in total "
            f"({limit_str(ctx.general.tolerance_pct)} general tolerance)"
        )
    return sentence[0].upper() + sentence[1:] + "."
