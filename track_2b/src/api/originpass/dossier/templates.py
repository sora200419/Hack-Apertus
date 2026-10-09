"""Deterministic texts: English and German explanations, Chinese letter and its exact English counterpart.

Used as the German text (always) and as the fallback whenever the model is unavailable or fails the fact
checks. Every number comes from the verdict; the German follows Swiss usage ('ss', guillemets, CHF 1'250.00).
"""

from __future__ import annotations

from ..models import Product, Verdict, VerdictStatus
from .facts import (
    blocking_line_ids,
    criteria_text,
    fmt_chf,
    fmt_num,
    hs6_digits,
    hs6_dotted,
    met_criteria,
    open_checks,
)

_CH_THOUSANDS = "'"  # Swiss thousands separator: CHF 1'250.00
_DE_CHECK_NAMES = {
    "insufficient processing": "nicht ausreichende Be- oder Verarbeitung",
    "direct transport": "direkte Beförderung",
}


def _sentence(text: str) -> str:
    text = text.strip()
    return text if text.endswith((".", "!", "?")) else text + "."


def _hs(product: Product, verdict: Verdict) -> str | None:
    code = hs6_digits(product, verdict)
    return hs6_dotted(code) if code else None


# ---------------------------------------------------------------------------
# English explanation
# ---------------------------------------------------------------------------


def explanation_en(product: Product, verdict: Verdict) -> str:
    hs = _hs(product, verdict)
    ref = f"{product.name} (HS {hs})" if hs else product.name
    agreement = "the China-Switzerland FTA"
    rule = verdict.rule
    status = verdict.status
    out: list[str] = []
    if rule is None:
        problem = (
            "the finished product has no 6-digit HS code yet, so classify it first"
            if hs is None
            else f"no product-specific rule is encoded for HS {hs}, so check Annex II of the FTA manually"
        )
        out.append(f"Verdict: UNSURE. The origin of {ref} under {agreement} cannot be assessed yet: {problem}.")
    elif status is VerdictStatus.PASS:
        criterion = criteria_text(met_criteria(verdict), "en")
        out.append(
            f"Verdict: PASS. {ref} qualifies as originating under rule {rule.rule_id} of {agreement} ({criterion})."
        )
    elif status is VerdictStatus.FAIL:
        out.append(f"Verdict: FAIL. {ref} does not qualify as originating under rule {rule.rule_id} of {agreement}.")
    else:
        out.append(
            f"Verdict: UNSURE. {ref} cannot yet be confirmed as originating under rule {rule.rule_id} of {agreement}."
        )
    out.append(_share_en(product, verdict))
    if status is VerdictStatus.PASS:
        out.append(
            "Ship with a proof of origin (a certificate of origin, or an origin declaration made out by an approved "
            "exporter) so that the importer can claim the FTA tariff rate."
        )
    else:
        out += _blockers_en(product, verdict)
        out.append("Until this is resolved, do not issue a proof of origin; the MFN tariff rate applies.")
    if rule is not None and not verdict.rule_verified:
        out.append("Note: the rule encoding has not yet been verified against the official Annex II text.")
    return " ".join(out)


def _share_en(product: Product, verdict: Verdict) -> str:
    text = (
        f"Non-originating materials amount to {fmt_num(verdict.nom_pct)}% of the ex-works price of "
        f"CHF {fmt_chf(product.ex_works_chf)}"
    )
    margin = verdict.margin_pct
    if verdict.threshold_pct is not None and margin is not None:
        gap = "of headroom" if margin >= 0 else "over the limit"
        text += (
            f", against a maximum of {fmt_num(verdict.threshold_pct)}% under the rule's value criterion "
            f"({fmt_num(abs(margin))} percentage points {gap})"
        )
    return text + "."


def _blockers_en(product: Product, verdict: Verdict) -> list[str]:
    out: list[str] = []
    bom = {b.line_id: b for b in product.bom}
    lines = [
        f"{i} ({bom[i].description}, {bom[i].origin_country}, CHF {fmt_chf(bom[i].value_chf)})" if i in bom else i
        for i in blocking_line_ids(verdict)
    ]
    if lines:
        out.append(f"Blocking BOM lines: {'; '.join(lines)}.")
    undecided = [c for c in open_checks(verdict) if c.passed is None]
    if undecided:
        out.append("Open points: " + "; ".join(f"{c.name}: {c.detail}" for c in undecided) + ".")
    if verdict.fixes:
        out.append(_sentence(f"Cheapest fix: {verdict.fixes[0]}"))
    return out


# ---------------------------------------------------------------------------
# German explanation (Swiss Standard German)
# ---------------------------------------------------------------------------


def _de_num(value: float) -> str:
    return fmt_num(value).replace(".", ",")


def explanation_de(product: Product, verdict: Verdict) -> str:
    hs = _hs(product, verdict)
    item = f"«{product.name}» (HS {hs})" if hs else f"«{product.name}»"
    agreement = "des Freihandelsabkommens zwischen der Schweiz und China"
    rule = verdict.rule
    status = verdict.status
    out: list[str] = []
    if rule is None:
        out.append(f"Ergebnis: UNSURE. Die Ursprungseigenschaft des Produkts {item} kann noch nicht beurteilt werden.")
        out.append(
            "Zuerst ist die sechsstellige HS-Nummer des Fertigprodukts zu bestimmen."
            if hs is None
            else f"Für die HS-Nummer {hs} ist keine produktspezifische Ursprungsregel erfasst; Anhang II des "
            "Abkommens ist manuell zu prüfen."
        )
    elif status is VerdictStatus.PASS:
        criterion = criteria_text(met_criteria(verdict), "de")
        out.append(
            f"Ergebnis: PASS. Das Produkt {item} erfüllt die Ursprungsregel {rule.rule_id} {agreement} ({criterion})."
        )
    elif status is VerdictStatus.FAIL:
        out.append(f"Ergebnis: FAIL. Das Produkt {item} erfüllt die Ursprungsregel {rule.rule_id} {agreement} nicht.")
    else:
        out.append(
            f"Ergebnis: UNSURE. Für das Produkt {item} kann die Ursprungseigenschaft nach "
            f"der Ursprungsregel {rule.rule_id} {agreement} noch nicht bestätigt werden."
        )
    out.append(_share_de(product, verdict))
    if status is VerdictStatus.PASS:
        out.append(
            "Der Sendung ist ein Ursprungsnachweis beizulegen (Ursprungszeugnis oder Ursprungserklärung eines "
            "ermächtigten Ausführers), damit der Importeur den Präferenzzollsatz beantragen kann."
        )
    else:
        out += _blockers_de(verdict)
        out.append(
            "Für diese Sendung darf kein Ursprungsnachweis ausgestellt werden; es gilt der Meistbegünstigungszollsatz."
            if status is VerdictStatus.FAIL
            else "Bis zur Klärung ist kein Ursprungsnachweis auszustellen; es gilt der Meistbegünstigungszollsatz."
        )
    if rule is not None and not verdict.rule_verified:
        out.append(
            "Hinweis: Die Erfassung der Ursprungsregel wurde noch nicht anhand des amtlichen Textes von Anhang II "
            "überprüft."
        )
    return " ".join(out)


def _share_de(product: Product, verdict: Verdict) -> str:
    text = (
        f"Der Anteil der Vormaterialien ohne Ursprungseigenschaft beträgt {_de_num(verdict.nom_pct)} % des "
        f"Ab-Werk-Preises von CHF {fmt_chf(product.ex_works_chf, _CH_THOUSANDS)}"
    )
    margin = verdict.margin_pct
    if verdict.threshold_pct is not None and margin is not None:
        gap = "Spielraum" if margin >= 0 else "Überschreitung"
        text += (
            f"; nach dem Wertkriterium der Regel sind höchstens {_de_num(verdict.threshold_pct)} % zulässig "
            f"({gap}: {_de_num(abs(margin))} Prozentpunkte)"
        )
    return text + "."


def _blockers_de(verdict: Verdict) -> list[str]:
    out: list[str] = []
    lines = blocking_line_ids(verdict)
    if lines:
        out.append(f"Massgebende Stücklistenpositionen: {', '.join(lines)}.")
    undecided = [_DE_CHECK_NAMES.get(c.name, c.name) for c in open_checks(verdict) if c.passed is None]
    if undecided:
        out.append(f"Offene Punkte: {', '.join(undecided)}.")
    if verdict.fixes:
        out.append("Die Verbesserungsvorschläge sind in der englischen Fassung aufgeführt.")
    return out


# ---------------------------------------------------------------------------
# Letter to the Chinese importer, and its exact English counterpart
# ---------------------------------------------------------------------------

_ZH_AGREEMENT = "《中华人民共和国和瑞士联邦自由贸易协定》（以下简称“中瑞自贸协定”）"
_EN_AGREEMENT = (
    "the Free Trade Agreement between the People's Republic of China and the Swiss Confederation "
    '(the "China-Switzerland FTA")'
)
_ZH_CLOSING = "如需其他资料，敬请随时与我司联系。\n\n此致\n敬礼！\n\n[出口商名称]\n[日期]"
_EN_CLOSING = (
    "Please do not hesitate to contact us if you need any further documents.\n\n"
    "Yours faithfully,\n\n[Exporter name]\n[Date]"
)


def letter_zh(product: Product, verdict: Verdict) -> str:
    hs = _hs(product, verdict)
    item = f"产品“{product.name}”（HS编码：{hs or '待定'}）"
    if verdict.status is VerdictStatus.PASS:
        criterion = criteria_text(met_criteria(verdict), "zh")
        body = (
            f"您好！我司谨此告知：我司向贵司出口的{item}符合{_ZH_AGREEMENT}的原产地规则，"
            f"适用的产品特定原产地规则为：{criterion}。\n\n"
            "本批货物将随附原产地证明，即主管机构签发的原产地证书，或由经核准出口商出具的原产地声明。"
            "贵司在办理进口申报时，可凭该原产地证明向海关申请适用中瑞自贸协定项下的协定税率。"
        )
    elif verdict.status is VerdictStatus.FAIL:
        body = (
            f"您好！我司已根据{_ZH_AGREEMENT}的原产地规则，对向贵司出口的{item}进行了原产资格核查。"
            "核查结果显示，该产品目前不符合上述原产地规则的要求。\n\n"
            "因此，本批货物不能随附原产地证书或原产地声明，贵司不能申请适用中瑞自贸协定项下的协定税率，"
            "进口时适用最惠国税率。如情况发生变化，我司将及时通知贵司。"
        )
    else:
        body = (
            f"您好！我司正在根据{_ZH_AGREEMENT}的原产地规则，对向贵司出口的{item}进行原产资格核查，"
            "目前尚不能确认该产品符合上述原产地规则。\n\n"
            "在核查完成之前，本批货物暂不能随附原产地证书或原产地声明，"
            "贵司暂不能申请适用中瑞自贸协定项下的协定税率。如核查确认符合要求，我司将及时通知贵司。"
        )
    return f"尊敬的[进口商名称]：\n\n{body}\n\n{_ZH_CLOSING}"


def letter_en(product: Product, verdict: Verdict) -> str:
    hs = _hs(product, verdict)
    item = f'the product "{product.name}" (HS code: {hs or "to be determined"})'
    if verdict.status is VerdictStatus.PASS:
        criterion = criteria_text(met_criteria(verdict), "en")
        body = (
            f"We hereby inform you that {item} that we export to your company meets the rules of origin of "
            f"{_EN_AGREEMENT}; the applicable product-specific rule of origin is: {criterion}.\n\n"
            "This shipment will be accompanied by a proof of origin, namely a certificate of origin issued by the "
            "competent authority, or an origin declaration made out by an approved exporter. When making the import "
            "declaration, your company may present this proof of origin to customs and apply for the FTA "
            "(conventional) tariff rate under the China-Switzerland FTA."
        )
    elif verdict.status is VerdictStatus.FAIL:
        body = (
            f"We have checked the originating status of {item} that we export to your company against the rules "
            f"of origin of {_EN_AGREEMENT}. The check shows that the product currently does not meet these rules "
            "of origin.\n\n"
            "Therefore this shipment cannot be accompanied by a certificate of origin or an origin declaration, and "
            "your company cannot apply for the FTA (conventional) tariff rate under the China-Switzerland FTA; the "
            "MFN tariff rate applies at import. We will inform you promptly if the situation changes."
        )
    else:
        body = (
            f"We are checking the originating status of {item} that we export to your company against the rules "
            f"of origin of {_EN_AGREEMENT}; at present we cannot yet confirm that the product meets these rules "
            "of origin.\n\n"
            "Until the check is complete, this shipment cannot be accompanied by a certificate of origin or an "
            "origin declaration, and your company cannot yet apply for the FTA (conventional) tariff rate under "
            "the China-Switzerland FTA. We will inform you promptly once the check confirms compliance."
        )
    return f"Dear [Importer name],\n\n{body}\n\n{_EN_CLOSING}"
