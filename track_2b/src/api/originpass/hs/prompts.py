"""Prompts for HS classification (Apertus). Constants only, so the eval can report them verbatim.

Keep every string deterministic (no dates, no ids): the replay cache is keyed on the exact messages.
"""

from __future__ import annotations

REWRITE_MAX_TOKENS = 120
RERANK_MAX_TOKENS = 160
RATIONALE_MAX_WORDS = 40

REWRITE_SYSTEM = (
    "You help classify goods in the Harmonized System (HS). "
    "The user gives one bill-of-materials line, written in German, French, Italian, Chinese or English. "
    "Rewrite it as a concise English customs description: what the article is, its main material and its "
    "function. Drop brand names, part numbers and quantities that do not affect classification. "
    "Then give 3 to 6 English keywords using customs (HS) vocabulary.\n"
    'Reply with JSON only: {"en": "<description>", "keywords": ["<keyword>", "..."]}'
)

REWRITE_USER = "Bill-of-materials line: {description}"

RERANK_SYSTEM = (
    "You classify goods in the Harmonized System (HS 2022) at 6-digit subheading level. "
    "Choose exactly one code from the numbered candidate list, or abstain.\n"
    "Apply the General Interpretative Rules (GIR) briefly:\n"
    "- GIR 1: classification is determined by the terms of the headings and the section and chapter notes; "
    "titles are for reference only.\n"
    "- GIR 2(a): an incomplete, unfinished or unassembled article is classified as the complete article "
    "if it has the essential character of the complete article.\n"
    "- GIR 3: if two headings apply, prefer the most specific description; otherwise the material or "
    "component that gives the essential character.\n"
    "- GIR 6: choose the subheading by its own terms, comparing only subheadings at the same level.\n"
    "- Parts: a part that is itself an article named in a heading (a pump, motor, bearing, screw, "
    "printed circuit) goes to that heading. Other parts used solely or principally with one kind of machine "
    "or instrument go to that machine's 'parts' subheading. Parts of general use (screws, bolts, springs of "
    "base metal) are never classified as parts of a machine.\n"
    "Abstain (hs6 null) if no candidate fits or the description is too vague to decide. "
    "Confidence is your probability (0 to 1) that the chosen code is correct.\n"
    'Reply with JSON only: {"hs6": "<6 digits from the list>" or null, "confidence": <number 0-1>, '
    '"rationale": "<at most 40 words>"}'
)

RERANK_USER = "Goods: {description}\n{rewrite_line}Candidates:\n{candidates}"

RERANK_REWRITE_LINE = "English rewrite: {rewrite}\n"

# Used only when there is no model rewrite: the static glossary's word-by-word gloss (glossary.gloss).
RERANK_GLOSS_LINE = "Word-by-word glossary gloss (may be inaccurate): {gloss}\n"

RERANK_CANDIDATE = "{n}. {hs6}: {path}"
