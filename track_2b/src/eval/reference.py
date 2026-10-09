"""Independent reference implementation of the origin rule semantics, for differential testing (E2).

Written from the data contract (originpass/models.py) and the semantics stated in the engine's module
docstring, not by reusing engine code: it imports nothing from originpass.engine or originpass.rulepack.
It has its own rule lookup, HS normalisation and keyword matching, and uses exact `Fraction`
arithmetic where the engine uses `Decimal`. E2 runs both on the same synthetic cases. A disagreement
means one of the two is wrong, and the trace says which step differs.

Semantics implemented:
1. Product HS6 = the code with dots and spaces removed; it must be exactly 6 digits. The rule is the
   one with the longest matching hs_scope prefix (ties go to the first rule). A missing code or a
   missing rule gives UNSURE.
2. A line is originating if originating_override says so; otherwise if its origin country is a
   cumulation party. Amounts are exact decimals as written; nom_pct = 100 * NOM / ex-works.
3. Alternatives are OR-ed and the criteria inside one are AND-ed. Each criterion is True, False or
   None (undecided).
   - CC/CTH/CTSH: a non-originating line violates the criterion if its HS6 shares the product's
     2/4/6-digit prefix or starts with an except_from prefix. It is unknown if it has no valid HS6.
     With no violating or unknown lines the criterion is True. Otherwise, if the general tolerance
     applies to the kind and violating + unknown <= tolerance % of ex-works, it is True (tolerance
     used). It is False if any line violates and either no tolerance applies or the violating lines
     alone exceed it. In every other case it is None.
   - WO: True without non-originating lines. Otherwise the same tolerance logic applies, with every
     non-originating line counted as violating.
   - MAXNOM: NOM <= pct % of ex-works. The tolerance never applies.
   - SPECIFIC: None, because a human must decide.
   An alternative is False if any criterion is False and True if all are True. Otherwise it is None.
4. General checks:
   - Insufficient processing is None when no operation is described. It is False when every operation
     contains a listed keyword as a whole-word phrase (case-insensitive, punctuation ignored).
     Otherwise it is True.
   - Direct transport is True without transit countries and without the storage flag. Otherwise it
     is None.
5. Status is FAIL if a general check is False or every alternative is False. It is PASS if some
   alternative is True and every general check is True. Otherwise it is UNSURE.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from fractions import Fraction

from originpass.models import Criterion, CriterionKind, Product, Rule, RulePack

_DIGITS = {CriterionKind.CC: 2, CriterionKind.CTH: 4, CriterionKind.CTSH: 6}
_NO_TOLERANCE = {CriterionKind.MAXNOM, CriterionKind.SPECIFIC}


@dataclass(frozen=True)
class RefVerdict:
    """Reference outcome: the fields E2 compares with the engine's Verdict."""

    status: str
    rule_id: str | None
    nom_pct: float  # rounded half-up to 2 decimals, like Verdict.nom_pct
    alternatives_met: tuple[bool | None, ...] = ()
    general: tuple[bool | None, ...] = ()  # (insufficient processing, direct transport)
    trace: tuple[str, ...] = field(default=(), compare=False)


def clean_hs(code: str | None) -> str:
    return re.sub(r"[\s.]", "", code or "")


def hs6(code: str | None) -> str | None:
    c = clean_hs(code)
    return c if len(c) == 6 and c.isdigit() else None


def money(value: float) -> Fraction:
    """Exact value of a float as written: 0.1 -> 1/10."""
    return Fraction(repr(float(value)))


def at_most_pct(amount: Fraction, pct: float, base: Fraction) -> bool:
    return amount * 100 <= money(pct) * base


def round2(x: Fraction) -> float:
    """Round half up to 2 decimals (x >= 0)."""
    cents = (x * 100 + Fraction(1, 2)).__floor__()
    return float(Fraction(cents, 100))


def lookup_rule(pack: RulePack, code: str) -> Rule | None:
    best, best_len = None, 0
    for rule in pack.rules:
        for scope in rule.hs_scope:
            prefix = clean_hs(scope)
            if prefix and code.startswith(prefix) and len(prefix) > best_len:
                best, best_len = rule, len(prefix)
    return best


def _words(text: str) -> str:
    return " ".join(re.findall(r"[^\W_]+", text.casefold()))


def operation_is_insufficient(operation: str, keywords: list[str]) -> bool:
    padded = f" {_words(operation)} "
    return any(_words(k) and f" {_words(k)} " in padded for k in keywords)


@dataclass(frozen=True)
class _Line:
    line_id: str
    hs6: str | None
    value: Fraction
    originating: bool


def _criterion(
    c: Criterion, product_hs6: str, nom: list[_Line], ex_works: Fraction, pack: RulePack
) -> tuple[bool | None, bool]:
    """(state, tolerance_used) of one criterion."""
    if c.kind is CriterionKind.MAXNOM:
        if c.max_nom_pct is None:
            return None, False
        return at_most_pct(sum((m.value for m in nom), Fraction(0)), c.max_nom_pct, ex_works), False
    if c.kind is CriterionKind.SPECIFIC:
        return None, False
    if c.kind is CriterionKind.WO:
        violating, unknown = list(nom), []
    else:
        n = _DIGITS[c.kind]
        excluded = [clean_hs(p) for p in c.except_from if clean_hs(p)]
        violating = [
            m for m in nom if m.hs6 and (m.hs6[:n] == product_hs6[:n] or any(m.hs6.startswith(p) for p in excluded))
        ]
        unknown = [m for m in nom if m.hs6 is None]
    if not violating and not unknown:
        return True, False
    tol = pack.general.tolerance_pct
    applies = c.kind in pack.general.tolerance_applies_to and c.kind not in _NO_TOLERANCE
    v_sum = sum((m.value for m in violating), Fraction(0))
    u_sum = sum((m.value for m in unknown), Fraction(0))
    if applies and at_most_pct(v_sum + u_sum, tol, ex_works):
        return True, True
    if violating and not (applies and at_most_pct(v_sum, tol, ex_works)):
        return False, False
    return None, False


def _alternative(states: list[bool | None]) -> bool | None:
    if False in states:
        return False
    if states and all(s is True for s in states):
        return True
    return None


def _general(product: Product, pack: RulePack) -> tuple[bool | None, bool | None]:
    ops = [op for op in product.processing if op.strip()]
    if not ops:
        processing = None
    else:
        processing = not all(operation_is_insufficient(op, pack.general.insufficient_operations) for op in ops)
    transit = [c for c in product.shipment.transit_countries if c.strip()]
    direct = True if not transit and not product.shipment.transshipment_or_storage_in_transit else None
    return processing, direct


def reference_verdict(product: Product, pack: RulePack) -> RefVerdict:
    """Evaluate `product` under `pack` with the semantics in the module docstring."""
    parties = {p.strip().upper() for p in pack.general.cumulation_parties}
    lines = []
    for b in product.bom:
        if b.originating_override is not None:
            originating = b.originating_override
        else:
            originating = b.origin_country.strip().upper() in parties
        lines.append(_Line(b.line_id, hs6(b.hs6), money(b.value_chf), originating))
    ex_works = money(product.ex_works_chf)
    nom = [m for m in lines if not m.originating]
    nom_pct = round2(sum((m.value for m in nom), Fraction(0)) * 100 / ex_works)
    general = _general(product, pack)
    trace = [f"NOM {len(nom)}/{len(lines)} lines = {nom_pct}%", f"general {general}"]

    code = hs6(product.hs6)
    rule = lookup_rule(pack, code) if code else None
    if code is None or rule is None:
        trace.append("no product HS6" if code is None else f"no rule for {code}")
        return RefVerdict("UNSURE", None, nom_pct, (), general, tuple(trace))

    met: list[bool | None] = []
    for i, alternative in enumerate(rule.alternatives, start=1):
        outcomes = [_criterion(c, code, nom, ex_works, pack) for c in alternative]
        met.append(_alternative([s for s, _ in outcomes]))
        trace.append(
            f"alt {i}: {[(c.kind.value, s, t) for c, (s, t) in zip(alternative, outcomes, strict=True)]} -> {met[-1]}"
        )
    if False in general or (met and all(m is False for m in met)):
        status = "FAIL"
    elif True in met and all(g is True for g in general):
        status = "PASS"
    else:
        status = "UNSURE"
    return RefVerdict(status, rule.rule_id, nom_pct, tuple(met), general, tuple(trace))
