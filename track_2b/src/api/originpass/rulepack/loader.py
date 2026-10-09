"""Load, validate and query rule packs (encoded rules of origin of an FTA).

A rule pack lives in `<data_dir>/rulepacks/<pack_id>.json` and is parsed into
`models.RulePack`. Loading also runs `validate_rulepack`, so an encoding error
(e.g. a MAXNOM criterion without a percentage) fails loudly instead of
silently producing a wrong verdict.
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

from ..config import get_settings
from ..models import Criterion, CriterionKind, Rule, RulePack

DEFAULT_PACK_ID = "ch-cn-2014"

_PACK_ID_RE = re.compile(r"[a-z0-9][a-z0-9._-]*")  # no path separators
_SCOPE_RE = re.compile(r"[0-9]{2}|[0-9]{4}|[0-9]{6}")
_PREFIX_RE = re.compile(r"[0-9]{2,6}")
_PARTY_RE = re.compile(r"[A-Z]{2}")
_SHIFT_KINDS = frozenset({CriterionKind.CC, CriterionKind.CTH, CriterionKind.CTSH})
_NO_TOLERANCE_KINDS = frozenset({CriterionKind.MAXNOM, CriterionKind.SPECIFIC})


class RulePackError(ValueError):
    """Raised for an invalid pack id or a pack that fails `validate_rulepack`."""


def normalise_hs(code: str | None) -> str:
    """Remove dots and whitespace from an HS code: '8471.30' -> '847130', None -> ''.

    NFKC first, so full-width input from a Chinese IME ('８４７１．３０') becomes ASCII digits.
    """
    return re.sub(r"[\s.]", "", unicodedata.normalize("NFKC", code or ""))


def load_rulepack(pack_id: str = DEFAULT_PACK_ID, data_dir: Path | None = None) -> RulePack:
    """Read and validate `<data_dir>/rulepacks/<pack_id>.json`.

    `data_dir` defaults to `Settings.data_dir` (env DATA_DIR). Raises
    FileNotFoundError if the file is missing, pydantic.ValidationError if it does
    not match the RulePack schema, and RulePackError if the id is malformed, the
    file declares another pack_id, or `validate_rulepack` reports problems.
    """
    if not _PACK_ID_RE.fullmatch(pack_id):
        raise RulePackError(f"invalid rule pack id {pack_id!r}")
    base = Path(data_dir) if data_dir is not None else get_settings().data_dir
    path = base / "rulepacks" / f"{pack_id}.json"
    pack = RulePack.model_validate_json(path.read_text(encoding="utf-8"))
    problems = validate_rulepack(pack)
    if pack.pack_id != pack_id:
        problems.insert(0, f"file declares pack_id {pack.pack_id!r}, expected {pack_id!r}")
    if problems:
        raise RulePackError(f"{path}: " + "; ".join(problems))
    return pack


def validate_rulepack(pack: RulePack) -> list[str]:
    """Return the encoding problems of a pack (empty list = consistent).

    Checks structure only (codes, percentages, kinds); it cannot check that the
    encoding matches the legal text, which is what `Rule.verified` records.
    """
    problems: list[str] = []
    g = pack.general
    if not 0 <= g.tolerance_pct <= 100:
        problems.append(f"general.tolerance_pct {g.tolerance_pct} outside 0-100")
    bad_tol = sorted(k.value for k in g.tolerance_applies_to if k in _NO_TOLERANCE_KINDS)
    if bad_tol:
        problems.append(f"general.tolerance_applies_to must not contain {bad_tol}")
    if not g.cumulation_parties or not all(_PARTY_RE.fullmatch(p) for p in g.cumulation_parties):
        problems.append("general.cumulation_parties must be ISO alpha-2 codes, e.g. ['CH', 'CN']")
    if not all(op.strip() for op in g.insufficient_operations):
        problems.append("general.insufficient_operations contains an empty entry")

    seen: set[str] = set()
    for rule in pack.rules:
        where = f"rule {rule.rule_id!r}"
        if rule.rule_id in seen:
            problems.append(f"{where}: duplicate rule_id")
        seen.add(rule.rule_id)
        if not rule.hs_scope:
            problems.append(f"{where}: empty hs_scope")
        problems += [
            f"{where}: hs_scope {p!r} is not a 2, 4 or 6 digit HS prefix"
            for p in rule.hs_scope
            if not _SCOPE_RE.fullmatch(p)
        ]
        if not rule.text.strip() or not rule.source.strip():
            problems.append(f"{where}: text and source are required")
        if not rule.alternatives:
            problems.append(f"{where}: no alternatives")
        for i, alternative in enumerate(rule.alternatives, start=1):
            if not alternative:
                problems.append(f"{where}: alternative {i} has no criteria")
            for c in alternative:
                problems += _criterion_problems(c, f"{where} alternative {i} {c.kind.value}")
    return problems


def _criterion_problems(c: Criterion, where: str) -> list[str]:
    problems: list[str] = []
    if c.kind is CriterionKind.MAXNOM:
        if c.max_nom_pct is None or not 0 <= c.max_nom_pct <= 100:
            problems.append(f"{where}: max_nom_pct must be between 0 and 100")
    elif c.max_nom_pct is not None:
        problems.append(f"{where}: max_nom_pct is only allowed on MAXNOM")
    if c.except_from and c.kind not in _SHIFT_KINDS:
        problems.append(f"{where}: except_from is only allowed on CC/CTH/CTSH")
    problems += [
        f"{where}: except_from {p!r} is not a 2-6 digit HS prefix"
        for p in c.except_from
        if not _PREFIX_RE.fullmatch(normalise_hs(p))
    ]
    return problems


def find_rule(pack: RulePack, hs6: str) -> Rule | None:
    """Return the rule whose hs_scope has the longest prefix of `hs6`; ties -> first rule."""
    code = normalise_hs(hs6)
    best: Rule | None = None
    best_len = 0
    for rule in pack.rules:
        prefix = matching_prefix(rule, code)
        if prefix is not None and len(prefix) > best_len:
            best, best_len = rule, len(prefix)
    return best


def matching_prefix(rule: Rule, hs6: str) -> str | None:
    """Longest prefix in `rule.hs_scope` that `hs6` starts with, or None."""
    code = normalise_hs(hs6)
    matches = [p for p in map(normalise_hs, rule.hs_scope) if p and code.startswith(p)]
    return max(matches, key=len, default=None)


def rulepack_stats(pack: RulePack) -> dict:
    """Counts for the UI/report: {'rules': n, 'verified_rules': n_verified}."""
    return {"rules": len(pack.rules), "verified_rules": sum(1 for r in pack.rules if r.verified)}
