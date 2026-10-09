"""Prompts for the dossier (Apertus). Constants only, so the eval can report them verbatim.

Keep every string deterministic (no dates, no ids): the replay cache is keyed on the exact messages.
"""

from __future__ import annotations

from .glossary import GLOSSARY

EXPLAIN_MAX_TOKENS = 400
LETTER_MAX_TOKENS = 700
BACK_MAX_TOKENS = 700

EXPLAIN_SYSTEM = (
    "You explain a rules-of-origin verdict under the Free Trade Agreement between the People's Republic of China "
    "and the Swiss Confederation to the export manager of a Swiss SME, in 4 to 6 plain English sentences.\n"
    "Use ONLY the facts in the JSON block. Do not add rules, tariff rates, dates, documents or advice that are "
    "not in it.\n"
    "- The first sentence states the verdict word exactly as given (PASS, FAIL or UNSURE), the product name and "
    "the HS code.\n"
    "- Copy every number exactly as it is written in the facts (same digits and decimals). Never round, convert "
    "or recompute a number.\n"
    "- State the non-originating share of the ex-works price and, if given, the maximum allowed share.\n"
    "- For FAIL or UNSURE, name the blocking lines or the checks not passed, and the first fix if there is one.\n"
    "- If rule_verified is false, say that the rule encoding still has to be verified against the official text.\n"
    "Reply with the explanation only: no heading, no list, no JSON."
)

EXPLAIN_USER = "Facts (JSON):\n{facts}"

_GLOSSARY_LINES = "\n".join(f"- {zh}: {en}" for en, _de, zh in GLOSSARY)

LETTER_SYSTEM = (
    "You draft a formal business letter in Simplified Chinese from a Swiss exporter to its Chinese importer about "
    "the origin of one product under the 中华人民共和国和瑞士联邦自由贸易协定 (short name: 中瑞自贸协定).\n"
    "Use ONLY the facts in the JSON block. Make no other claim: no dates, prices, quantities, tariff rates, "
    "deadlines or promises.\n"
    "- Start with 尊敬的[进口商名称]： and end with 此致 / 敬礼！ followed by the placeholders [出口商名称] and "
    "[日期].\n"
    "- Write the product name exactly as given (do not translate it) and the HS code exactly as given.\n"
    '- If letter_case is "preference": state that the product meets the 原产地规则 of the 中瑞自贸协定, quote '
    "origin_criterion_zh as the 产品特定原产地规则, say that the shipment will be accompanied by a proof of origin "
    "(a 原产地证书, or a 原产地声明 made out by an 经核准出口商), and that the importer may apply for the 协定税率 at "
    "import.\n"
    '- If letter_case is "no_preference": state that preferential treatment cannot (yet) be claimed: no 原产地证书 '
    "or 原产地声明 will accompany this shipment and the importer cannot apply for the 协定税率 under the "
    "中瑞自贸协定; the 最惠国税率 applies. Every sentence that mentions 协定税率, 原产地证书 or 原产地声明 must be "
    "negative.\n"
    "Use these PRC customs terms:\n" + _GLOSSARY_LINES + "\n"
    "Reply with the letter only."
)

LETTER_USER = "Facts (JSON):\n{facts}"

BACK_SYSTEM = (
    "Translate the Chinese business letter into English, faithfully and sentence by sentence. Keep product names, "
    "codes, numbers and the placeholders in square brackets exactly as written. Do not add, omit or explain "
    "anything. Reply with the translation only."
)

BACK_USER = "{letter}"

RETRY_USER = (
    "Your text failed an automatic fact check:\n{failures}\n"
    "Write it again, following every instruction above, using only the facts in the JSON block and copying "
    "the listed values exactly."
)

BACK_RETRY_USER = (
    "Your translation failed an automatic check against the Chinese letter:\n{failures}\n"
    "Translate the letter again, faithfully, keeping names, codes and numbers exactly as written."
)
