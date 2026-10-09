"""BOM line originating status and exact money arithmetic for the origin engine.

Amounts are converted to `Decimal` from their shortest repr, so percentages are
compared exactly as the user typed them (CHF 10.00 of CHF 100.00 is exactly
10 %, never 10.000000000000002 %). Floats only appear in the Verdict output.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from decimal import ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP, Decimal

from ..models import BomLine, GeneralProvisions
from ..rulepack.loader import normalise_hs

CENT = Decimal("0.01")
_HS6_RE = re.compile(r"[0-9]{6}")  # ASCII only: other Unicode digits would never match an HS prefix


def dec(value: float) -> Decimal:
    """Exact decimal of a float as written (0.1 -> Decimal('0.1'))."""
    return Decimal(repr(float(value)))


def hs6_or_none(code: str | None) -> str | None:
    """Normalised 6-digit HS code ('8471.30' -> '847130'), or None if not exactly 6 digits."""
    norm = normalise_hs(code)
    return norm if _HS6_RE.fullmatch(norm) else None


def within_pct(amount: Decimal, pct: float, base: Decimal) -> bool:
    """amount <= pct % of base, compared exactly."""
    return amount * 100 <= dec(pct) * base


def pct_of(amount: Decimal, base: Decimal) -> Decimal:
    return amount * 100 / base


def chf(amount: Decimal, rounding: str = ROUND_HALF_UP) -> str:
    return f"CHF {amount.quantize(CENT, rounding)}"


def chf_up(amount: Decimal) -> str:
    """Rounded up to the cent: for 'must fall by at least'."""
    return chf(amount, ROUND_CEILING)


def chf_down(amount: Decimal) -> str:
    """Rounded down to the cent: for 'to at most'."""
    return chf(amount, ROUND_FLOOR)


def pct_str(value: Decimal) -> str:
    return f"{value.quantize(CENT, ROUND_HALF_UP)}%"


def limit_str(pct: float) -> str:
    """A rule percentage as written in the pack: 50.0 -> '50%', 47.5 -> '47.5%'."""
    return f"{pct:g}%"


@dataclass(frozen=True)
class Material:
    """One BOM line with its normalised HS6, exact value and originating status."""

    line: BomLine
    hs6: str | None
    value: Decimal
    originating: bool
    reason: str

    @property
    def line_id(self) -> str:
        return self.line.line_id

    def describe(self, with_hs: bool = True) -> str:
        """'L1 (HS 847330, CHF 40.00)', or 'L1 (CHF 40.00)' without the HS code."""
        hs = f"HS {self.hs6 or 'unknown'}, " if with_hs else ""
        return f"{self.line_id} ({hs}{chf(self.value)})"


def describe_lines(materials: tuple[Material, ...] | list[Material], with_hs: bool = True) -> str:
    """'line L1 (HS ..., CHF ..)' or 'lines L1 (...), L2 (...) and L3 (...)'."""
    parts = [m.describe(with_hs) for m in materials]
    if len(parts) == 1:
        return f"line {parts[0]}"
    return f"lines {', '.join(parts[:-1])} and {parts[-1]}"


def total(materials: tuple[Material, ...] | list[Material]) -> Decimal:
    return sum((m.value for m in materials), Decimal(0))


def assess_material(line: BomLine, parties: list[str]) -> Material:
    """Originating status of one line.

    `originating_override` wins when set. Otherwise a material is originating
    iff its origin country is a cumulation party (bilateral cumulation), on the
    stated assumption that the supplier provides proof of origin.
    """
    country = unicodedata.normalize("NFKC", line.origin_country).strip().upper()  # 'ＣＮ' -> 'CN'
    if line.originating_override is True:
        originating, reason = True, "treated as originating: the exporter holds proof of origin (user override)"
    elif line.originating_override is False:
        originating, reason = False, "treated as non-originating (user override)"
    elif country in parties:
        originating = True
        reason = (
            f"origin {country} is an FTA party, counted as originating under bilateral cumulation; "
            "assumes the supplier provides proof of origin"
        )
    else:
        originating = False
        reason = f"origin {country} is not an FTA party ({'/'.join(parties)}), so the material is non-originating"
    return Material(line, hs6_or_none(line.hs6), dec(line.value_chf), originating, reason)


@dataclass(frozen=True)
class Context:
    """Everything a criterion needs: product HS6, ex-works price, assessed materials, general rules."""

    product_hs6: str
    ex_works: Decimal
    materials: tuple[Material, ...]
    general: GeneralProvisions

    @property
    def non_originating(self) -> tuple[Material, ...]:
        return tuple(m for m in self.materials if not m.originating)

    @property
    def nom_value(self) -> Decimal:
        return total(self.non_originating)

    @property
    def parties(self) -> str:
        """'CH/CN' for fix sentences."""
        return "/".join(p.upper() for p in self.general.cumulation_parties)
