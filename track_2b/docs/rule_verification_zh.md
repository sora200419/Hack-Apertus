# 规则核对清单（请用中文原文核对）

OriginPass 的规则包共 221 条：其中 206 条从**海关总署公告2014年第51号**（《中瑞自贸协定》产品特定原产地规则，官方中文文本）自动解析，另 15 条是 HS 2022 新增子目的过渡规则（附件二基于 HS 2012，这些子目需要人工判断，引擎返回 UNSURE）。
原文在 `data/raw/annex2_psr_zh_gacc_2014_51.txt`。请逐条核对下面的「原文」和「编码」是否一致，然后在方框里打 ✔。
核对完后告诉我哪些已确认，我会写进 `data/rulepacks/verification.json`，界面上的 “unverified” 警告就会消失。

## A. 演示用到的四章（最重要）

| 规则 ID | 原文（第51号公告） | 编码（引擎实际执行的） | 确认 |
|---|---|---|---|
| CHCN-84 | 第八十四章 核反应堆、锅炉、机器、机械器具及其零件：非原产材料价值50％ | VNM 50% → MAXNOM ≤50% | ☐ |
| CHCN-85 | 第八十五章 电机、电气设备及其零件；声音的录制和重放设备及其零件、附件：非原产材料价值50％ | VNM 50% → MAXNOM ≤50% | ☐ |
| CHCN-90 | 第九十章 光学、照相、电影、计量、检验、医疗或外科用仪器及设备、精密仪器及设备；上述物品的零件、附件：非原产材料价值55％ | VNM 55% → MAXNOM ≤55% | ☐ |
| CHCN-91 | 第九十一章 钟表及其零件：非原产材料价值40％ | VNM 40% → MAXNOM ≤40% | ☐ |

## B. 总则（第三章）

| 项目 | 引擎中的处理 | 依据 | 确认 |
|---|---|---|---|
| 微小含量 | 非原产材料 ≤ 出厂价 10% 时，免于满足附件二的完全获得 / 章改变 / 品目改变 / 子目改变条件；**不适用于** “非原产材料价值” 标准 | 第3.5条 | ☐ |
| 微小加工或处理 | 若申报的全部加工工序都只属于第3.6条所列操作（包装、贴标、简单装配等）→ 不具原产资格；同一工序里混有其他加工 → UNSURE。“抛光、漂白、去壳、去皮”只在条文限定的语境（简单抛光、谷物/大米、水果/坚果/蔬菜）下才算 | 第3.6条 | ☐ |
| 累积 | 原产于中国或瑞士的材料视为原产材料（需供应商提供原产地证明） | 第3.7条 | ☐ |
| 直接运输 | 经第三方转运，或出口方与目的地相同时 → UNSURE，需证明未经加工且处于海关监管下 | 第3.13条 | ☐ |
| 证书商品项数 | 每份原产地证书最多 50 项 | 海关总署公告2021年第49号 | ☐ |
| 第二节注释（第27–40章） | 化学反应、提纯、混合等备选规则需人工判断：这些章的规则多加一个 “需人工判断” 的备选项（结果可能为 UNSURE） | 附件二第二节 | ☐ |

## C. 解析说明（自动解析无法确定的条目，标记为 SPECIFIC，引擎返回 UNSURE）

- ex 第七十二章: stripped trailing '第七十二章' from criterion '品目改变第七十二章'
- Section II: one SPECIFIC alternative added to each of the 31 entries of chapters 27-40
- 0901.21: criterion kept as SPECIFIC (human judgement): '非原产材料价值30%，限从生咖啡豆制造，包括焙炒工序'
- 0901.22: criterion kept as SPECIFIC (human judgement): '非原产材料价值30%，限从生咖啡豆制造，包括焙炒工序'
- 0901.90: criterion kept as SPECIFIC (human judgement): '非原产材料价值30%，限从生咖啡豆制造，包括焙炒工序'
- 37.01: criterion kept as SPECIFIC (human judgement): '品目改变，如果成品涂有感光乳剂或其他涂层溶剂，则该感光乳剂或其他涂层溶剂须在一方生产；如果需要干燥、涂层、剪切及包装工序，则上述工序也应在该方完成。'
- 37.02: criterion kept as SPECIFIC (human judgement): '品目改变，如果成品涂有感光乳剂或其他涂层溶剂，则该感光乳剂或其他涂层溶剂须在一方生产；如果需要干燥、涂层、剪切及包装工序，则上述工序也应在该方完成。'
- 71.06: criterion kept as SPECIFIC (human judgement): '从品目7106、7108或7110的贵金属电解、加热、化学分解或熔接而来；'
- 71.06: criterion kept as SPECIFIC (human judgement): '从品目7106、7108或7110的贵金属合铸或与贱金属的合铸而来'
- 71.08: criterion kept as SPECIFIC (human judgement): '从品目7106、7108或7110的贵金属电解、加热、化学分解或熔接而来；'
- 71.08: criterion kept as SPECIFIC (human judgement): '从品目7106、7108或7110的贵金属合铸或与贱金属的合铸而来'
- 71.10: criterion kept as SPECIFIC (human judgement): '从品目7106、7108或7110的贵金属电解、加热、化学分解或熔接而来；'
- 71.10: criterion kept as SPECIFIC (human judgement): '从品目7106、7108或7110的贵金属合铸或与贱金属的合铸而来'
- 第七十七章: no criterion lines
- 82.06: criterion kept as SPECIFIC (human judgement): '成套货品里的每项产品都必须满足它不作为成套货品时所适用的规则'
- 96.05: criterion kept as SPECIFIC (human judgement): '成套货品里的每项产品都必须满足它不作为成套货品时所适用的规则'
- 97.05: criterion kept as SPECIFIC (human judgement): '产品应在一方发现'
- HS 2022 382211, 382213: not in HS 2012, predecessors under CHCN-30; added to its scope
- HS 2022 810931, 810939: not in HS 2012, predecessors under CHCN-810930; added to its scope
- HS 2022 811261: not in HS 2012, predecessors under CHCN-810730; added to its scope
- HS 2022: 38 subheadings not in HS 2012 whose predecessors need the HS 2012 classification to pick or apply an entry -> 15 CHCN-HS2022-* rules with SPECIFIC criteria

## D. 如何确认

回复例如：「A 全部确认，B 全部确认」即可。若发现不一致，请指出规则 ID 和正确内容。
