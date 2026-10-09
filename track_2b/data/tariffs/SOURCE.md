# PRC import tariff rates (`cn_import_tariffs.json`)

Status: **unverified**. Every entry has `verified: false`; `source_note` in the JSON explains the method.

- MFN rates: third-party mirrors of the 2026 Customs Import and Export Tariff of the PRC, seen through web
  search results on 2026-10-08 (the official MOF / China Customs pages were not reachable from the build
  environment):
  - https://www.htshub.com/cn-hs/detail/9102110000 (also 8413709990, 8481804090, 8501520010, 9102210010, 9102210090)
  - https://treayo.com/en/hs/china/91021100 , https://treayo.com/en/hs/china/90261000
- A rate is filled only if every Chinese national line found under the HS6 subheading has the same MFN rate.
- Switzerland conventional rates (协定税率): no source found, all `fta_rate_pct` are null, so the dossier shows
  no duty saving yet.
- To verify: look up the 10-digit line in the official 2026 PRC tariff (Ministry of Finance annex to the 2026
  tariff adjustment plan, or the China Customs online tariff query), read the MFN and Switzerland columns,
  then set the rates, the official source and `verified: true`.
