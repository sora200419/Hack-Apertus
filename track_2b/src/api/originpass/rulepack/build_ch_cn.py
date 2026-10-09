"""Build the ch-cn-2014 rule pack from the official texts in data/raw/.

Annex II source: GACC Announcement 2014 No. 51, the official Chinese publication of the
Switzerland-China FTA product-specific rules (data/raw/annex2_psr_zh_gacc_2014_51.txt).
General provisions: verbatim Chapter 3 quotes (data/raw/chapter3_provisions.json).
HS 2022 -> HS 2012: UNSD correlation table (data/raw/hs2022_hs2012_correlation_unsd.csv, sheet
"HS2022-HS2012 Correlations" of HS2022toHS2012ConversionAndCorrelationTables.xlsx, as mirrored in
github.com/insongkim/concordance data-raw/), used only for HS 2022 subheadings that did not exist in
HS 2012 (see map_hs2022).

The parser is deterministic and conservative: any criterion it cannot map exactly becomes a
SPECIFIC criterion (the engine then answers UNSURE) and is listed in the parse notes. Section II
(notes for chapters 27-40) gives those chapters further routes to origin that need human judgement,
so their rules get one more SPECIFIC alternative (SECTION_II_NOTE).
A rule is marked verified only if data/rulepacks/verification.json lists its rule_id, i.e.
after a human compared the encoding with the official text.

Usage:  python -m originpass.rulepack.build_ch_cn [--data-dir DIR]
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from ..config import get_settings
from ..models import Criterion, CriterionKind, GeneralProvisions, Rule, RulePack
from .loader import validate_rulepack

PACK_ID = "ch-cn-2014"
ANNEX_FILE = "annex2_psr_zh_gacc_2014_51.txt"
PROVISIONS_FILE = "chapter3_provisions.json"
CORRELATION_FILE = "hs2022_hs2012_correlation_unsd.csv"
SOURCE = "GACC Announcement 2014 No. 51, Annex II product-specific rules (official Chinese text)"
CORRELATION_SOURCE = "UNSD HS 2022-HS 2012 correlation table"
EX_NOTE = " (ex entry: applies except to the headings listed separately)"
SECTION_II_HEADER = "第二节 第27章至第40章的注释"
SECTION_II_CHAPTERS = range(27, 41)
SECTION_II_NOTE = (
    "Annex II Section II (notes for chapters 27-40): products obtained by fermentation (in chapter 30 also by "
    "cell culture) are wholly obtained, and where the change in tariff classification cannot be applied, "
    "chemical reaction, mixing, purification, change of particle size, standard materials or isomer separation "
    "confer origin (in that order, each for the chapters its note lists)"
)

_CN_DIGITS = {"零": 0, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
_CN_NUM = "[一二三四五六七八九十零]+"
CHAPTER_RE = re.compile(rf"^(ex\s*)?第({_CN_NUM})章$")
HEADING_RE = re.compile(r"^(ex\s*)?(\d{2})\.(\d{2})$")
SUBHEADING_RE = re.compile(r"^(ex\s*)?(\d{4})\.(\d{2})$")
CRITERION_STARTS = ("完全获得", "章改变", "品目改变", "子目改变", "非原产材料价值", "从品目", "成套货品", "产品应在一方发现")
OR_SEPARATOR = "或者"

SHIFT_KINDS = {"章改变": CriterionKind.CC, "品目改变": CriterionKind.CTH, "子目改变": CriterionKind.CTSH}
SHIFT_EN = {CriterionKind.CC: "CC", CriterionKind.CTH: "CTH", CriterionKind.CTSH: "CTSH"}
EXCEPT_EN = {CriterionKind.CC: "chapter", CriterionKind.CTH: "heading", CriterionKind.CTSH: "subheading"}


def cn_to_int(s: str) -> int:
    """Chinese numerals up to 99: 九 -> 9, 十二 -> 12, 九十一 -> 91."""
    if "十" not in s:
        return _CN_DIGITS[s]
    tens, _, units = s.partition("十")
    return (_CN_DIGITS[tens] if tens else 1) * 10 + (_CN_DIGITS[units] if units else 0)


@dataclass
class Entry:
    code: str
    hs: str
    ex: bool
    description: list[str] = field(default_factory=list)
    criteria_lines: list[str] = field(default_factory=list)


def parse_code(line: str) -> tuple[str, bool] | None:
    """Return (hs prefix, is_ex) for a column-1 code line, else None."""
    if m := CHAPTER_RE.match(line):
        return f"{cn_to_int(m.group(2)):02d}", bool(m.group(1))
    if m := HEADING_RE.match(line):
        return m.group(2) + m.group(3), bool(m.group(1))
    if m := SUBHEADING_RE.match(line):
        return m.group(2) + m.group(3), bool(m.group(1))
    return None


def clean_lines(raw: str) -> list[str]:
    # The text is a Word-table export: \x07 marks cell ends, \x0c page breaks.
    text = raw.replace("\x07", "\n").replace("\x0c", "\n").replace("\r", "").replace("　", " ")
    lines = [ln.strip() for ln in text.split("\n")]
    start = lines.index("第一章")
    return [ln for ln in lines[start:] if ln]


def split_entries(lines: list[str], notes: list[str]) -> list[Entry]:
    entries: list[Entry] = []
    for line in lines:
        code = parse_code(line)
        if code:
            entries.append(Entry(code=line, hs=code[0], ex=code[1]))
            continue
        entry = entries[-1]
        # Artefact: a criterion glued to the chapter code of its own entry ("品目改变第七十二章").
        glued = re.match(rf"^(.+?)(第{_CN_NUM}章)$", line)
        if glued and glued.group(1).startswith(CRITERION_STARTS):
            chapter = f"{cn_to_int(glued.group(2)[1:-1]):02d}"
            if chapter == entry.hs[:2]:
                notes.append(f"{entry.code}: stripped trailing '{glued.group(2)}' from criterion '{line}'")
                line = glued.group(1)
        if entry.criteria_lines or line.startswith(CRITERION_STARTS) or line == OR_SEPARATOR:
            entry.criteria_lines.append(line)
        else:
            entry.description.append(line)
    return entries


def _except_prefixes(clause: str) -> list[str] | None:
    """'从品目5106、5107 或5108改变至此除外' -> ['5106', '5107', '5108']; None if not an exception clause."""
    m = re.fullmatch(r"从(第.+章|品目.+|子目.+)改变至此除外", clause)
    if not m:
        return None
    body = m.group(1)
    if body.startswith("第"):
        return [f"{cn_to_int(c):02d}" for c in re.findall(rf"第({_CN_NUM})章", body)]
    codes = [re.sub(r"\D", "", c) for c in re.findall(r"\d{2}\.?\d{2}(?:\.\d{2})?", body)]
    return codes or None


def parse_criterion(line: str) -> tuple[list[Criterion], str]:
    """One column-3/4 criterion -> (AND-list of criteria, English rendering)."""
    text = line.rstrip("；;。. ")
    if text == "完全获得":
        return [Criterion(kind=CriterionKind.WO)], "WO"

    m = re.fullmatch(r"(章改变|品目改变|子目改变)(?:且非原产材料价值(\d+)[%％])?(?:，(.+))?", text)
    if m:
        kind = SHIFT_KINDS[m.group(1)]
        crit = Criterion(kind=kind)
        parts = [SHIFT_EN[kind]]
        extra: list[Criterion] = []
        if m.group(3):
            prefixes = _except_prefixes(m.group(3))
            if prefixes:
                crit.except_from = prefixes
                parts[0] += f" (except from {EXCEPT_EN[kind]} " + ", ".join(prefixes) + ")"
            else:
                extra.append(Criterion(kind=CriterionKind.SPECIFIC, note=m.group(3)))
                parts.append("specific processing condition (see Chinese text)")
        if m.group(2):
            extra.insert(0, Criterion(kind=CriterionKind.MAXNOM, max_nom_pct=float(m.group(2))))
            parts.insert(1, f"VNM {m.group(2)}%")
        return [crit, *extra], " and ".join(parts)

    m = re.fullmatch(r"非原产材料价值(\d+)[%％](?:，(.+))?", text)
    if m:
        crits = [Criterion(kind=CriterionKind.MAXNOM, max_nom_pct=float(m.group(1)))]
        en = f"VNM {m.group(1)}%"
        if m.group(2):
            crits.append(Criterion(kind=CriterionKind.SPECIFIC, note=m.group(2)))
            en += " and specific processing condition (see Chinese text)"
        return crits, en

    return [Criterion(kind=CriterionKind.SPECIFIC, note=text)], "specific requirement (see Chinese text)"


def build_rule(entry: Entry, notes: list[str]) -> Rule:
    alternatives: list[list[Criterion]] = []
    en_parts: list[str] = []
    zh_parts: list[str] = []
    for line in entry.criteria_lines:
        if line == OR_SEPARATOR:
            continue
        crits, en = parse_criterion(line)
        alternatives.append(crits)
        en_parts.append(en)
        zh_parts.append(line.rstrip("；; "))
        if any(c.kind is CriterionKind.SPECIFIC for c in crits):
            notes.append(f"{entry.code}: criterion kept as SPECIFIC (human judgement): '{line}'")
    if not alternatives:
        alternatives = [[Criterion(kind=CriterionKind.SPECIFIC, note="no criterion in the list")]]
        en_parts = ["no rule listed"]
        notes.append(f"{entry.code}: no criterion lines")
    elif int(entry.hs[:2]) in SECTION_II_CHAPTERS:
        alternatives.append([Criterion(kind=CriterionKind.SPECIFIC, note=SECTION_II_NOTE)])
        en_parts.append("a Section II route (fermentation, chemical reaction, purification, ...)")
    description = "".join(entry.description)
    return Rule(
        rule_id=f"CHCN-{entry.hs}",
        hs_scope=[entry.hs],
        alternatives=alternatives,
        text="; or ".join(en_parts) + (EX_NOTE if entry.ex else ""),
        text_zh=f"{entry.code} {description}：" + " 或者 ".join(zh_parts),
        source=f"{SOURCE}, entry '{entry.code}'",
        verified=False,
    )


def read_correlation(path: Path) -> dict[str, frozenset[str]]:
    """{HS 2022 subheading: the HS 2012 subheadings it correlates with} from the UNSD table."""
    pairs: dict[str, set[str]] = {}
    with path.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            pairs.setdefault(row["hs2022"], set()).add(row["hs2012"])
    return {code: frozenset(olds) for code, olds in pairs.items()}


def map_hs2022(pack: RulePack, correlation: dict[str, frozenset[str]], notes: list[str]) -> list[Rule]:
    """Route HS 2022 subheadings that did not exist in HS 2012 to the entry of their HS 2012 predecessors.

    Annex II is written in HS 2012, so prefix matching is wrong for such a code when its predecessors
    fall under another entry (HS 2022 811261 cadmium waste was HS 2012 810730, entry 8107.30 'WO', but
    its prefix finds 'ex chapter 81'). One predecessor entry without a tariff shift: the code joins that
    rule's hs_scope (mutating `pack`). Otherwise a CHCN-HS2022-<code> rule is returned: the single
    entry's alternatives with every tariff shift turned into SPECIFIC (it must be judged on HS 2012
    codes), or, for several candidate entries, a SPECIFIC criterion naming them (see _any_entry).
    Codes that existed in HS 2012 keep their prefix rule.
    """
    hs2012 = frozenset().union(*correlation.values())
    by_id = {rule.rule_id: rule for rule in pack.rules}
    by_scope: dict[str, str] = {}
    for rule in pack.rules:  # entry scopes are 2, 4 or 6 digits; the first rule wins ties, as in find_rule
        for scope in rule.hs_scope:
            by_scope.setdefault(scope, rule.rule_id)

    def entry_of(code: str) -> str | None:
        return next((by_scope[code[:n]] for n in (6, 4, 2) if code[:n] in by_scope), None)

    extend: dict[str, list[str]] = {}
    groups: dict[tuple[str, ...], list[str]] = {}
    for code in sorted(correlation.keys() - hs2012):
        candidates = tuple(sorted({e for e in map(entry_of, correlation[code]) if e}))
        if not candidates or candidates == (entry_of(code),):
            continue
        if len(candidates) == 1 and not _has_shift(by_id[candidates[0]]):
            extend.setdefault(candidates[0], []).append(code)
        else:
            groups.setdefault(candidates, []).append(code)
    for rule_id, codes in extend.items():
        rule = by_id[rule_id]
        rule.hs_scope += codes
        rule.source += f"; HS 2022 subheading(s) {', '.join(codes)} added via the {CORRELATION_SOURCE}"
        notes.append(f"HS 2022 {', '.join(codes)}: not in HS 2012, predecessors under {rule_id}; added to its scope")
    new_rules = [_hs2022_rule(codes, [by_id[i] for i in ids], correlation) for ids, codes in groups.items()]
    notes.append(
        f"HS 2022: {sum(map(len, groups.values()))} subheadings not in HS 2012 whose predecessors need the HS 2012 "
        f"classification to pick or apply an entry -> {len(new_rules)} CHCN-HS2022-* rules with SPECIFIC criteria"
    )
    return sorted(new_rules, key=lambda r: r.rule_id)


def _has_shift(rule: Rule) -> bool:
    return any(c.kind in SHIFT_EN for alt in rule.alternatives for c in alt)


def _hs2012_shift(c: Criterion, entry: Rule, predecessors: str) -> Criterion:
    """A copy of `c`; a tariff shift becomes SPECIFIC because it compares HS 2012 headings, not HS 2022 ones."""
    if c.kind not in SHIFT_EN:
        return c.model_copy(deep=True)
    label = SHIFT_EN[c.kind] + (f" except from {', '.join(c.except_from)}" if c.except_from else "")
    note = f"{label} of entry {entry.rule_id}, to be judged on the HS 2012 codes (product: {predecessors})"
    return Criterion(kind=CriterionKind.SPECIFIC, note=note)


def _vnm_limits(rule: Rule) -> list[float]:
    """Limits of the alternatives that are a single MAXNOM criterion."""
    return [alt[0].max_nom_pct for alt in rule.alternatives if len(alt) == 1 and alt[0].max_nom_pct is not None]


def _any_entry(entries: list[Rule]) -> tuple[list[list[Criterion]], str]:
    """Alternatives and text for a product that falls under one of `entries`, unknown which.

    Undecided (SPECIFIC) in general. If every entry can be met by a VNM limit alone, VNM <= the
    smallest of those limits meets whichever entry applies; if every alternative of every entry is a
    VNM limit, VNM above the largest one fails all of them.
    """
    listing = ", ".join(f"{r.rule_id} ({r.text.removesuffix(EX_NOTE)})" for r in entries)
    note = f"the product's HS 2012 subheading decides which Annex II entry applies ({listing})"
    undecided = [Criterion(kind=CriterionKind.SPECIFIC, note=note)]
    which = f"the entry of the product's HS 2012 subheading, one of {listing}"
    limits = [_vnm_limits(r) for r in entries]
    if not all(limits):
        return [undecided], f"no single Annex II entry: {which}"
    meets_all = min(max(lim) for lim in limits)
    if all(len(lim) == len(r.alternatives) for lim, r in zip(limits, entries, strict=True)):
        undecided.append(Criterion(kind=CriterionKind.MAXNOM, max_nom_pct=max(max(lim) for lim in limits)))
    text = f"VNM {meets_all:g}% (meets every candidate entry); or {which}"
    return [[Criterion(kind=CriterionKind.MAXNOM, max_nom_pct=meets_all)], undecided], text


def _hs2022_rule(codes: list[str], entries: list[Rule], correlation: dict[str, frozenset[str]]) -> Rule:
    """A non-Annex rule for HS 2022 `codes` whose HS 2012 predecessors fall under `entries` (see map_hs2022)."""
    olds = sorted(frozenset().union(*(correlation[c] for c in codes)))
    shown = ", ".join(olds[:8]) + (f" and {len(olds) - 8} more" if len(olds) > 8 else "")
    if len(entries) == 1:
        entry = entries[0]
        alternatives = [[_hs2012_shift(c, entry, shown) for c in alt] for alt in entry.alternatives]
        text = f"{entry.text.removesuffix(EX_NOTE)}, as entry {entry.rule_id} of the HS 2012 predecessors"
    else:
        alternatives, text = _any_entry(entries)
    return Rule(
        rule_id=f"CHCN-HS2022-{codes[0]}",
        hs_scope=codes,
        alternatives=alternatives,
        text=text,
        text_zh="；".join(e.text_zh or e.rule_id for e in entries),  # the official text of each candidate entry
        source=f"{CORRELATION_SOURCE} (HS 2012 predecessors {shown}); not an Annex II entry",
        verified=False,
    )


def build_general(prov: dict) -> GeneralProvisions:
    ops = prov["minimal_operations"]
    return GeneralProvisions(
        tolerance_pct=10.0,
        # Art. 3.5(2): not for value criteria; BAZG reads it as WO, CC, CTH, CTSH.
        tolerance_applies_to=[CriterionKind.WO, CriterionKind.CC, CriterionKind.CTH, CriterionKind.CTSH],
        tolerance_text=f"{prov['de_minimis']['article']}: {prov['de_minimis']['en']}",
        insufficient_operations=ops["keywords"],
        insufficient_operations_text=f"{ops['article']}: {ops['en']}",
        cumulation_parties=["CH", "CN"],
        direct_transport_text=f"{prov['direct_transport']['article']}: {prov['direct_transport']['en']}",
        max_items_per_certificate=prov["certificate_items"]["max_items"],
        source="Switzerland-China FTA, Chapter 3 (MOFCOM English text via ToTA; fedlex SR 0.946.292.492; "
        "GACC Announcement 2014 No. 52); GACC Announcement 2021 No. 49 for the 50-item limit",
        verified=False,
    )


def build(data_dir: Path) -> tuple[RulePack, list[str]]:
    raw_dir = data_dir / "raw"
    notes: list[str] = []
    annex = (raw_dir / ANNEX_FILE).read_text(encoding="utf-8")
    if SECTION_II_HEADER not in annex:
        raise ValueError(f"{ANNEX_FILE}: Section II header {SECTION_II_HEADER!r} not found")
    entries = split_entries(clean_lines(annex), notes)
    in_section_ii = sum(int(e.hs[:2]) in SECTION_II_CHAPTERS for e in entries)
    notes.append(f"Section II: one SPECIFIC alternative added to each of the {in_section_ii} entries of chapters 27-40")
    general = build_general(json.loads((raw_dir / PROVISIONS_FILE).read_text(encoding="utf-8")))
    pack = RulePack(
        pack_id=PACK_ID,
        agreement="Free Trade Agreement between the Swiss Confederation and the People's Republic of China "
        "(signed 6 July 2013, in force 1 July 2014)",
        version_note="Annex II as published in HS 2012 nomenclature; applied to HS 2022 codes by prefix, except "
        "HS 2022 subheadings that did not exist in HS 2012 and whose predecessors (UNSD correlation) fall under "
        "another entry (added to that entry's scope) or need the HS 2012 classification (rules CHCN-HS2022-*). "
        "The upgraded FTA concluded on 20 Aug 2026 is not yet published; slot 'ch-cn-upgrade' is reserved.",
        general=general,
        rules=[build_rule(e, notes) for e in entries],
    )
    pack.rules += map_hs2022(pack, read_correlation(raw_dir / CORRELATION_FILE), notes)

    verification_path = data_dir / "rulepacks" / "verification.json"
    verified = json.loads(verification_path.read_text(encoding="utf-8")) if verification_path.exists() else {}
    for rule in pack.rules:
        rule.verified = rule.rule_id in verified.get("rules", {})
    general.verified = "general" in verified
    return pack, notes


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--data-dir", type=Path, default=get_settings().data_dir)
    args = ap.parse_args()
    pack, notes = build(args.data_dir)
    problems = validate_rulepack(pack)
    if problems:
        raise SystemExit("rule pack invalid:\n" + "\n".join(problems))
    out = args.data_dir / "rulepacks" / f"{PACK_ID}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(pack.model_dump(mode="json"), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    (out.parent / f"{PACK_ID}.parse_notes.txt").write_text("\n".join(notes) + "\n", encoding="utf-8")
    verified = sum(r.verified for r in pack.rules)
    print(f"wrote {out}: {len(pack.rules)} rules ({verified} verified), {len(notes)} parse notes")


if __name__ == "__main__":
    main()
