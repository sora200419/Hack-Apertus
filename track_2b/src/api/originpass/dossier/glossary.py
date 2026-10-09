"""Customs terminology (English, Swiss Standard German, PRC Simplified Chinese) used by the dossier.

The Chinese terms follow the wording of PRC customs and FTA texts; the German terms follow Swiss
customs usage (no sharp s). The letter prompt lists these terms, and `REQUIRED_ZH` is what
`validator.glossary_check` demands in every Chinese letter.
"""

from __future__ import annotations

# (en, de, zh)
GLOSSARY: list[tuple[str, str, str]] = [
    (
        "Free Trade Agreement between the People's Republic of China and the Swiss Confederation",
        "Freihandelsabkommen zwischen der Schweizerischen Eidgenossenschaft und der Volksrepublik China",
        "中华人民共和国和瑞士联邦自由贸易协定",
    ),
    ("China-Switzerland FTA", "Freihandelsabkommen Schweiz-China", "中瑞自贸协定"),
    ("rules of origin", "Ursprungsregeln", "原产地规则"),
    ("product-specific rule of origin", "produktspezifische Ursprungsregel", "产品特定原产地规则"),
    ("originating goods", "Ursprungserzeugnisse", "原产货物"),
    ("non-originating materials", "Vormaterialien ohne Ursprungseigenschaft", "非原产材料"),
    ("ex-works price", "Ab-Werk-Preis", "出厂价"),
    ("change in tariff classification", "Wechsel der Tarifeinreihung", "税则归类改变"),
    ("change of tariff heading", "Positionswechsel", "品目改变"),
    ("origin criterion (WO / WP / PSR)", "Ursprungskriterium", "原产地标准"),
    ("certificate of origin", "Ursprungszeugnis", "原产地证书"),
    ("origin declaration", "Ursprungserklärung", "原产地声明"),
    ("approved exporter", "ermächtigter Ausführer", "经核准出口商"),
    ("direct transport", "direkte Beförderung", "直接运输"),
    ("preferential tariff treatment", "Zollpräferenzbehandlung", "优惠关税待遇"),
    ("FTA (conventional) tariff rate", "Präferenzzollsatz (Abkommenszollsatz)", "协定税率"),
    ("MFN tariff rate", "Meistbegünstigungszollsatz", "最惠国税率"),
    ("HS code", "HS-Code", "HS编码"),
    ("importer", "Importeur", "进口商"),
    ("exporter", "Exporteur", "出口商"),
]

# fact name -> accepted Chinese terms (any one suffices)
REQUIRED_ZH: dict[str, tuple[str, ...]] = {
    "agreement": ("中瑞自贸协定", "中华人民共和国和瑞士联邦自由贸易协定"),
    "proof_of_origin": ("原产地证书", "原产地声明"),
    "fta_rate": ("协定税率",),
}
