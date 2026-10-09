# Official source texts (Switzerland–China FTA, rules of origin)

These files are what the rule pack is built from (`python -m originpass.rulepack.build_ch_cn`).
Official texts of treaties and government announcements are not protected by copyright
(Swiss URG Art. 5; PRC Copyright Law Art. 5). They are reproduced here unchanged so that the
build is reproducible offline.

| File | Content | Origin |
|---|---|---|
| `annex2_psr_zh_gacc_2014_51.txt` | Annex II product-specific rules, full list (all 97 chapters), official Chinese text | GACC Announcement 2014 No. 51 (海关总署公告2014年第51号, in force 1 July 2014, status valid). Text taken from the customs.gov.cn mirror in github.com/Pinky-Lemon6/customs_spider (`dataset/data/regulations.json`) |
| `chapter3_en_tota.txt` | Chapter 3 (Rules of Origin), English | MOFCOM English treaty text as extracted in the ToTA corpus (github.com/mappingtreaties/tota, `xml/pta_376.xml`). The extraction drops some spaces ("ofthis"); quotes in `chapter3_provisions.json` restore them |
| `chapter3_zh_gacc_2014_52.txt` | Chapter 3, Chinese | GACC Announcement 2014 No. 52, Annex 1 (same mirror) |
| `chapter3_de_fedlex_2021.txt` | Chapter 3, German (consolidated 1 Sept 2021) | fedlex SR 0.946.292.492 (mirror github.com/droid-f/fedlex-assets) |
| `chapter3_provisions.json` | Curated verbatim quotes of Art. 3.5, 3.6, 3.7, 3.13 and the 50-item certificate limit, plus screening keywords for Art. 3.6 | Compiled from the files above; GACC Announcement 2021 No. 49 for the item limit |
| `hs2022_hs2012_correlation_unsd.csv` | HS 2022 → HS 2012 correlation (subheading pairs and relationship type) | UN Statistics Division, sheet "HS2022-HS2012 Correlations" of `HS2022toHS2012ConversionAndCorrelationTables.xlsx`, as mirrored in github.com/insongkim/concordance (`data-raw/`); sha256 prefix 5d416df1210ddbec. Used only for HS 2022 subheadings that did not exist in HS 2012 |
| `cn_tariff_ch_fta_2014_gacc_53.tsv` | PRC 2014 MFN and Switzerland conventional rates, 8,277 national lines | GACC Announcement 2014 No. 53, Annex 1 (same customs.gov.cn mirror as above); see `data/tariffs/SOURCE.md` |

Known limits:
- The English wording of the Annex II list entries ("VNM 50%", "CTH" ...) is rendered from the
  official Chinese text using the notation defined in Annex II, Section I. Independent English
  sources confirm chapters 84 (IHK Stuttgart), 85 (Unitouch 2014) and 90 (Mondaq 2014).
- Annex II uses HS 2012. HS 2022 product codes that existed in HS 2012 are matched by prefix; codes
  new in HS 2022 are mapped back through the UNSD correlation table (ambiguous ones get UNSURE rules).
  Material codes in tariff-shift checks are still compared as given.
- The upgraded FTA (concluded 20 Aug 2026) is not yet published and is not encoded.
