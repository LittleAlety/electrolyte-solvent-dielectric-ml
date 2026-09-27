## 28.48 Week 19 D4 文献抽取探针 Phase-0：模板 v0 十三字段与门槛先声明、本周不执行抽取（2026-09-28）
|
**机制假设**：ε 通道被 157–161 个开放许可化合物的封顶卡住，文献抽取是**唯一**可能突破该封顶的新路线（结构化库上限来自许可，散点文献值不在其中）。D4 只做 Phase-0：把 §W19-2 的抽取模板落成 13 字段规格，并把门槛、量级守卫、红线、许可判读**在执行前**锁死。本周**不执行抽取、不联网、不跑拟合、不产出任何读数**（机器被 W18 / W19 其余 lane 占满）。
**预注册**：`probes/w19_extraction_phase0_prereg.json`，sha256 `5f83efa632cf7de79c017c938dfb6c63102ae13cbacb0b3f50eeb541d74ccb11`，`status = "locked_before_run"`；`deliverable = "D4"`、`executes_extraction_this_week = false`、`produces_reading = false`、`thresholds_pending_author_confirmation = true`。规格件 `reports/w19_extraction_phase0.md` sha256 `10c7913cefa2f431827d4582250aa2f805c096dd32dce24330c1cdc0230bb25f`；字面钉测试 `tests/test_w19_extraction_phase0.py` sha256 `8b2ee13d53faee3784206b18b7289017413e0f804972ee085111475f0ae74a41`（同时钉住前两个文件的 digest）。
|
**规格一 · 抽取模板 v0（记录粒度 = 一个（化合物, 通道性质, 数值）观测行，13 字段）**
1. `compound_name`（保留原文写法，不得顺手规范化成 IUPAC 名）；2. `smiles`（RDKit 可解析，失败即丢弃、**不得人工替写结构**）；3. `inchikey`（27 字符标准形，须与 SMILES 现算值逐位一致）；4. `disambiguation_confidence`（< 0.90 进人工复核队列，**不得默认 1.0**）；5. `property_value`（过量级守卫）；6. `unit`（受控词表，非表内单位须写 `unit_note`）；7. `temperature_K`（0 < T ≤ 1000，°C 须换算并留 `temperature_note`）；8. `method`（受控词表，必须区分 reported 与 estimated）；9. `source_doi`（**硬门**）；10. `locator_table_figure`（**硬门**，无定位视为未核）；11. `extraction_confidence`（< 0.95 进人工复核队列）；12. `access_class`（写入时自动；`open_oa` 才可能入 `data/`）；13. `source_lane`（∈ {eta, homo_lumo, redox, epsilon}）。
- 分组读法：字段 1–4 服务**化合物消歧**；5–8 服务**数值字段**；9–10 是**硬门**；11 是**抽取置信度**；12–13 是治理列。
|
**规格二 · 通道优先级与 ε 的条件性激活**
- 先做顺序：**η**（存量最大、离过门最近：组键 MAE `0.174772` vs 门 0.15）→ **HOMO/LUMO**（已有基线池可做组外对照）→ **氧化还原电位**（RX-392 存量 + N14 安全通道）；**ε 条件性激活**。
- 预注册落为 `channel_priority.first = [eta, homo_lumo, redox]`、`epsilon_template_activation = "deferred_to_w18_7"`：**ε lane 若在 W18-7 判「封顶、无合法路径」则模板转档案**（不投入 Week 20 规模化、不占抽取预算）；若解冻/换线成功则按同一套字段模板另开预注册立项。**本稿不单方判定 ε 通道死活**。
|
**规格三 · 建议门槛（全部 `status = proposed_pending_author_confirmation`）**
| 门槛 | 建议值 | 作用域 | 不达标后果 |
| --- | --- | --- | --- |
| 数值字段 precision | ≥ 0.95 | `property_value` + `unit` + `temperature_K` | 整通道转人工复核，不得入库 |
| 数值字段 recall | ≥ 0.80 | 同上（金标准 = 人工核对子集） | 整通道转人工复核，不得入库 |
| 化合物消歧 precision | ≥ 0.90 | `compound_name → inchikey` | 全量记录转人工复核消歧 |
| DOI + 表/图定位完整率 | **= 100%（硬门）** | `source_doi` + `locator_table_figure` | **缺则不入库**（不是降级，是不入库） |
- 量级守卫（同为建议值）：η ∈ (0, 10] Pa·s、HOMO/LUMO ∈ [-15, 5] eV、氧化还原（vs Li/Li⁺）∈ [0, 10] V、ε ∈ [1, 300]；超界一律人工复核，不得静默入库。
- **纪律**：上表全部数值均为建议，`design_only_language` 逐字为「建议门槛；待作者确认，不得由本稿单方生效」；**作者未确认前不得作为验收判据，不得据此宣称任何通道达标或抽取路线成立**。
|
**规格四 · 先例与许可判读**
- **EDB 先例**：250+ 篇文献 → **18,316** 条；**口径更正**（引自 D1 实测）：18,316 实为「EDB + MP」**合计**，此后引用一律写合计，不得再单说「EDB 18,316」。
- **`s43246` 先例（RAG + LLM）**：筛选精度 30% → 100%，按「**方法可借鉴、数据不可搬运**」处理。
- **EDB / ElectrolyteGPT 只学字段设计**：字段清单/表结构属思想与方法，不受版权保护；但其数据受 **CC-BY-NC-ND** 约束（ND 禁止改造后再分发/入库、NC 禁止商用），**不得改造后入库**。该判读已写入预注册。
|
**规格五 · 红线（与 Reaxys 条款同构，已逐条写入预注册）**
1. 图源读数与受限库值一律 `restricted_crosscheck_only`：只作交叉核对，**永不入 `data/`、永不入任何池、永不入任何特征**；2. 每条记录必须带 DOI + 表/图定位，**无定位不入库**（硬门）；3. 出版商站点手动逐条查询合规、**批量爬虫禁止**（OA API 除外且需登记：API 名 / 许可条款 / 抓取时间窗 / 条数）；4. Reaxys 数值禁入池 / 特征 / 交付包（§28.33 红线延续）—— 抽取值若与 Reaxys 同源同值，一律按 `restricted_crosscheck_only` 处置，**不得因「文献里也印了同一个数」而洗白入库**。
|
**判定与边界**
- **本件无读数、不占主记分牌**：`produces_reading = false`；`promotion_rule` 逐字写明「本件不提升任何读数、不占主记分牌；W18 冻结头条 `0.4766400383507876` 与基线 `0.4091179943351143` 不受本件影响；累计主记分牌尝试次数不变（11）」。
- **shot 记账待作者裁定（建议，未生效）**：计划预分配 **shot 21**；`shot_accounting.recommended_shot = 21`、`fallback_if_shot_19_20_counted = 22`、`this_file_consumes_a_shot = false`（本件是 Phase-0 设计件，占号发生在抽取执行时）；是否把 shot 19 / 20 视为已用**由作者拍板**。
- **两条分支**：过门（四条门槛全达）⇒ Week 20 立项规模化（语料扩到 200+ 篇 OA）；不过门 ⇒ 降级为半自动辅助工具（LLM 只做候选定位 + 预填，**每条记录人核后才可能入库**，半自动产物不得直接当训练数据）。**看到结果后再改门槛即违反 §W19-9**（lever-8 先例）。
- 本件**不声称**任何通道达标、不声称抽取路线成立；Phase-0 方案本身（语料 20–50 篇 OA、人工核对子集大小、模板冻结后放量）中的待定项同样标注「待作者确认」。
|
**产物清单**
- `reports/w19_extraction_phase0.md`（11,083 B；sha256 `10c7913cefa2f431827d4582250aa2f805c096dd32dce24330c1cdc0230bb25f`）
- `probes/w19_extraction_phase0_prereg.json`（11,634 B；sha256 `5f83efa632cf7de79c017c938dfb6c63102ae13cbacb0b3f50eeb541d74ccb11`）
- `tests/test_w19_extraction_phase0.py`（sha256 `8b2ee13d53faee3784206b18b7289017413e0f804972ee085111475f0ae74a41`）
|
**数字出处**
- `locked_before_run` / `D4` / `executes_extraction_this_week` / `produces_reading` / `thresholds_pending_author_confirmation` / `design_only_language` / `promotion_rule` ← `probes/w19_extraction_phase0_prereg.json` 同名顶层键
- 0.95 / 0.80 / 0.90 / 1.00 / `magnitude_guards` ← `probes/w19_extraction_phase0_prereg.json::thresholds`
- `channel_priority`（`first` / `epsilon_template_activation` / `epsilon_branch`）← 同名 JSON 键
- `shot_accounting`（21 / 22 / `this_file_consumes_a_shot`）← 同名 JSON 键
- 13 字段 ← `probes/w19_extraction_phase0_prereg.json::template_v0.fields`（实测 13 条）；文字表述见 `reports/w19_extraction_phase0.md::二`
- 18,316 / 250 / 30% → 100% / CC-BY-NC-ND ← `reports/w19_extraction_phase0.md::一` 与 `::八`
**数字自检**：片段内数值 token 已对 `reports/w19_extraction_phase0.md` + `probes/w19_extraction_phase0_prereg.json` + `tests/test_w19_extraction_phase0.py` 逐字回搜（ISO 日期整段排除、digest 不作数值 token）。**推算值 / 运行值 / 外部常量**：`28.48`（节号，任务书指定）；`11,083` / `11,634` 两个字节数是**本机 stat 实测**（素材文件正文不含自身字节数；规格件末尾也自注「不自指自身摘要」）；`11`（累计主记分牌尝试，W18 冻结记账，经 `promotion_rule` 引用）。其余全部数值 token 在本 lane 素材内逐字命中。
|
