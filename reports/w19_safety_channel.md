# W19-D7：安全通道登记（N14）——闪点 / 沸点 / 熔点 / 安全窗口 登记为第四通道，只登记不执行

- 任务 `week19_w19d7_safety_channel_registration`；生成时间（本机 UTC 时钟）：2026-09-27T18:45:16.642Z。
- **性质**：登记件。本件是 `Week19立项计划_文献驱动三线.md` **§W19-6 安全通道登记（N14，只登记，不执行）** 的落地件。**本件不执行任何计算、不下载、不调用任何工具、不产任何标签或读数**；`produces_reading = false`。
- **登记表（机器可读）**：`probes/w19_safety_channel_registry.json`。
- **权威输入（只读）**：`E:/大二/d2qc/电解液（长期项目）/文献调研/重点且同向/Week19立项计划_文献驱动三线.md` 的 §W19-6 / §W19-8 / §W19-9；选型出处可核到的 PDF = `E:/大二/d2qc/电解液（长期项目）/文献调研/重点且同向/au5c01628.pdf`（JACS Au 2026, 6, 2288−2302；DOI 10.1021/jacsau.5c01628；PyMuPDF 文本抽取）。
- **五条纪律**：不产读数；不占 shot 编号；不动主记分牌；不引用 Reaxys 数值；计划书写法与 PDF 逐字对齐。

## 0. 本件存在的原因

周 19 有一份**先于执行锁定**的通道顺序：η ⇒ HOMO-LUMO ⇒ 氧化还原（§W19-7 三级转移表）。安全通道**不在这张表里**，它是计划书 §W19-6 单独开的一格：只把**工具选型、版本、许可、覆盖门纪律**记录入册，登记为**候选通道**。
换句话说：本件交付的是一份**可核的选型台账**，不是一条通道的读数组。台账里每一条都能回到计划书原文或那份 PDF，**没有一个是本机算出来的**。

## 1. 为什么只登记、不执行

1. **主线已占满。** 本周主线是 η / HOMO-LUMO / 氧化还原三条（其中 HOMO `0.19050925839013938` 与 LUMO `0.13855083976437643` 已过 0.20 eV 门，η 在役族级 `0.17477197208762` 未过 0.15 门）。安全是**第四通道**，此时加入只会稀释主线。
2. **加它会撞两条红线。** §W19-8 明写「**不做生成闭环、不做候选生成器**」（uniqueness 0.349 证据在册）与「**不开无预注册的枪**」。安全窗口天然是**多目标组合判据**，一上手就滑向「按窗口筛候选」的生成式闭环；而在没有独立预注册的情况下先算数，正是第二条红线。
3. **计划书自己写死了。** §W19-6 原文：*「本周不执行任何计算，不占 shot 编号。」* 本件照办，`shot_number_taken = null`。
4. **覆盖门还没过。** §W19-6 原文：*「适用覆盖门同款纪律（gate 0.30；对照 DN 通道覆盖 0.0% 未过门的前例）：任何安全描述符进特征表前先过覆盖检查。」* 本机连**覆盖都还没测**（本件不测），所以连「能不能进特征表」这个前置问题都还没有答案。
5. **许可未判。** §W19-6 要求「同时登记其版本与许可」。本机可核的只有**版本 / 文献出处**（见第 2 节），**许可在仓内不可核**（全仓 `rg` 检索 `ADMETlab` 与 `Marrero` 均 0 命中）。许可没判清就执行，等于给交付包埋许可风险。

## 2. 登记了什么

| 通道 | 性质 | 拟用工具 | 出处（可核） | 版本登记 | 许可登记 | 状态 |
| --- | --- | --- | --- | --- | --- | --- |
| `safety_flash_point` | 闪点 | GC-ML 模型 + **Marrero-Gani 基团贡献框架**（只用一级基团表示） | 计划书 §W19-6 原文 + `au5c01628.pdf` 原句 *"Flash point was predicted employing the GC-ML-model,49 where only the first-order group representation of the Marrero-Gani framework was considered.50"* | PDF 未给闪点模型的独立版本号；框架出处 = Marrero & Gani 2001, Fluid Phase Equilib. 183, 183−208（PDF 引 50）；实现出处 = Alshehri et al. 2022, AIChE J. 68, e17469（PDF 引 49） | `not_verifiable_in_repo` | `registered_not_executed` |
| `safety_boiling_point` | 沸点 | **ADMETlab 3.0** | 计划书 §W19-6 + `au5c01628.pdf` 原句 *"Boiling and melting point were predicted employing ADMETlab 3.0.48"*（`.48` 是 PDF 上标引文号，**不是**补丁版本） | 3.0（PDF 参考文献 48 = Fu et al., Nucleic Acids Res. 2024, 52, W422−W431） | `not_verifiable_in_repo` | `registered_not_executed` |
| `safety_melting_point` | 熔点 | **ADMETlab 3.0**（与沸点同源同版本） | 同上句 | 3.0（同上） | `not_verifiable_in_repo` | `registered_not_executed` |
| `safety_window` | 安全窗口（前三条的组合判据） | **无独立工具**；若要执行只能由前三条派生，且须单独预注册 | 计划书 §W19-6 并列为候选；PDF 只给前三条的模型出处，**未给安全窗口的独立模型** | n/a（派生通道，不虚构版本） | n/a（不引入新许可问题；上游 ADMETlab 的判读仍适用） | `registered_not_executed` |

**版本登记的一处口径澄清**：PDF 抽取出的 `ADMETlab 3.0.48` 与 `GC-ML-model,49`、`considered.50` 里的尾数是**上标引文序号**，不是版本号。所以 ADMETlab 的登记版本是 **3.0**，闪点链的登记是「框架 1 篇 + 实现 1 篇」而不是一个打包版本号。**不为它臆造版本**。

**许可登记的一处照实说明**：本仓**没有任何**许可判读可按（`rg -S ADMETlab` 与 `rg -S Marrero` 在全仓 0 命中，本件自身除外）。因此四条通道的 `licence_note` 一律写 `not_verifiable_in_repo`，并把「补许可判读」列进第 3 节的前置条件，**不写任何我从没读到的许可结论**。

## 3. 执行前必须补齐的前置条件

安全通道将来若要执行，**六条按序全补齐**，缺一条就不许开枪：

1. **独立预注册先立**：本通道单独一份预注册件，先锁门槛、再跑任何计算，预注册**永不事后修订**（lever-8 先例）。
2. **许可判读先补**：ADMETlab 3.0 与 Marrero-Gani / GC-ML 两条链的许可、API 条款与再分发边界逐条写清；未判清不得执行。
3. **覆盖门先过**：按 gate 0.30（口径 `covered_keys / target_keys`）在 v03 名册上实测覆盖，未过门只登记、不建特征——对标 DN 通道覆盖 0.0%（`covered_keys` 0 / `target_keys` 1043）未过门的前例。
4. **适用域声明在先**：安全通道的适用域必须**声明在前**，且与 ε 的 D1 分域声明（`NumHDonors ≥ 1 and TPSA ≥ 20.0`，§28.45）**分开登记**，不得互相借用。
5. **与既有记分牌的隔离声明**：安全读数必须**独立成板**，并在声明里写明**不得与 ε 主记分牌（基线 `0.4091179943351143` / 头条 `0.4766400383507876`）或 η 通道读数（行级 `0.08506361044387624` / 族级 `0.08908094784092072`）混合比较**。**安全窗口数字一旦引入，必须走独立预注册，且不得与 ε / η 主记分牌混比。**
6. **先占号后跑**：按 §W19-9 的 shots 记账规则取号；取号前须先由作者裁定 **shot 19 / 20 是否已用掉编号**（若视为已用则新工作从 shot 22 起，若视为复核性工作则按「复核不占号」处理）。

## 4. 覆盖门（本件不测，只登记纪律）

| 项 | 登记值 | 来源 |
| --- | --- | --- |
| 门 | **0.3** | `probes/walden_dn_channel_summary.json::dn_channel.coverage_threshold` |
| 口径 | `covered_keys / target_keys` | 同件 `::dn_channel.coverage_definition` |
| 前例（DN 通道） | 覆盖 **0** / 目标 **1043** ⇒ 覆盖分数 **0**（即 0.0%），**未过门** | 同件 `::dn_channel.admissible`；`probes/four_channel_coverage_summary.json::pinned.dn_covered_keys` / `::pinned.dn_target_keys` |
| 前例裁定 | `channel_does_not_enter_the_feature_table` | `probes/walden_dn_channel_summary.json::decision.dn_channel` |
| 本件实测覆盖 | **无**（`produces_reading = false`，本周不测） | 本件自身 |

**这条门的含义**：安全描述符不是「算得出就能用」。DN 通道的前例是**拿得到预测列、但过不了覆盖门**，结果整条通道判 `channel_does_not_enter_the_feature_table`。安全通道要进特征表，第一步是同一把尺子。

## 5. §W19-8 不做清单（逐条重述）

- 不接 OMat24（无机晶体，与本项目分子液体错配）。
- 不做生成闭环、不做候选生成器（uniqueness **0.349** 证据在册）。
- 不把 ElectrolyteGPT 的代理输出当训练数据；不用任何随机拆分文献数字做对照靶或晋升依据。
- **不重跑已在盘的 W17 资产**（Batt-P30K 下载与标定、Onsager 探针、`homo_lumo_baselines`、`dielectric_channel_v2`）；确需重跑须先写明既有结果缺陷并入预注册。
- **不把行级随机折读数当对照靶**——既包括文献读数，也包括仓内 Onsager 探针与 channel_v2 的读数。
- 不动 6 个冻结件（v03 `ff214293…`、v11plus `159b928f…`、viscosity_v01 `12dfa03f…`、3 个预注册件 `ab3503c0…` / `77f61a83…` / `b838febb…`）。
- 不开无预注册的枪；81 MB 原始层不进任何 bundle；受限值永不在再分发层出现。
- 不在本章修订 Week 18 的任何判据（W18-2 端点定义、W18-7 退出判据只能由作者确认后修订，修订即记录）。

**与安全通道的关系**：第 2 条与第 7 条是安全通道**本周不执行**的直接依据；第 6 条意味着登记本身也不许动冻结件。

## 6. 记分牌纪律（本件的自我澄清）

- **本件抬高主记分牌了吗？没有。** `promoted = false`；`produces_reading = false`；主记分牌尝试 **0** 次，`scoreboard_attempts_delta = 0`，累计仍 **11** 次；冻结基线 `0.4091179943351143` 与冻结头条 `0.4766400383507876` **原位未动**。
- **ε 通道口径**：**457** 行 / **97** 化合物 = **276** 个（化合物, T）对；训练侧全表 **2029** 行。这组数**不得**与 η 通道的 **4151** 行 / **976** 键（族级 **3582** 行 / **957** 键）混说。
- **ε 的诚实端点是 `0.5861142332208197`**（单表示跨种子端点，钉为终态），它与冻结头条 `0.4766400383507876` **永不混比**。
- **Reaxys 红线**：本件不含任何 Reaxys 数值；登记里的数字全部来自仓内文件或那份 PDF 的文献出处。

## 7. 数字出处与不可核登记

**可核（逐字回搜命中）**

- `0.3` / 覆盖口径 / DN 前例 `0` 与 `1043` / 裁定 `channel_does_not_enter_the_feature_table` ⇒ `probes/walden_dn_channel_summary.json::dn_channel.coverage_threshold` / `::dn_channel.coverage_definition` / `::dn_channel.admissible` / `::decision.dn_channel`；`probes/four_channel_coverage_summary.json::pinned.dn_covered_keys` / `::pinned.dn_target_keys`
- `0.15`（η 门）⇒ `probes/viscosity_baseline_summary.json::primary_gate.threshold`（`group_key_passed = false`）；`0.17477197208762` / `0.15686276760094522` / `0.08506361044387624` / `0.08908094784092072` ⇒ `probes/w19_chemprop_viscosity_summary.json`｜`reports/_w19_section_d5.md`（§28.49）
- `0.19050925839013938` / `0.13855083976437643` / `0.20` ⇒ `probes/four_channel_coverage_summary.json::pinned`｜`reports/w19_ranking_key_spec.md`（§28.50）
- `0.4091179943351143` / `0.4766400383507876` / `457` / `97` / `276` ⇒ `probes/four_channel_coverage_summary.json::pinned`
- `2029` ⇒ `reports/_w18_readme_draft.md::4`（训练侧全表行数）
- `4151` / `976` / `3582` / `957` ⇒ `reports/_w19_section_d5.md`（§28.49）｜`probes/w19_chemprop_viscosity_summary.json::pools`
- `0.5861142332208197` ⇒ `reports/decisions_log.md::§28.41/§28.42/§28.44`｜`reports/w19_channel_transfer.md`（§28.51）
- `0.349` ⇒ `reports/w19_ranking_key_spec.md::16`（引 `au5c01628`）｜计划书 §W19-8
- `11`（累计主记分牌尝试）⇒ `reports/_w19_section_d5.md`（§28.49）｜`reports/decisions_log.md::§28.41`
- `ADMETlab` / `Marrero-Gani` / `GC-ML` / 两篇参考文献 / `JACS Au 2026, 6, 2288−2302` / DOI ⇒ `au5c01628.pdf` 正文与参考文献 48–50（PyMuPDF 抽取）；§W19-6 原文 ⇒ 计划书 §W19-6
- `NumHDonors ≥ 1 and TPSA ≥ 20.0`（ε 的 D1 分域规则）⇒ `reports/decisions_log.md::§28.45`

**照实登记为「不可核」**

- **许可**：ADMETlab 3.0 与 Marrero-Gani / GC-ML 的许可条款、API 条款、再分发边界——仓内 0 命中，`not_verifiable_in_repo`。本件**不给结论**，只列为前置条件第 2 条。
- **版本**：闪点链没有单一打包版本号；本件只登记「框架 1 篇 + 实现 1 篇」，不编造版本字符串。ADMETlab 的数字版本以 PDF 正文 `3.0` 为准（`.48` 是引文号）。
- **安全窗口的独立工具**：计划书把它与另三条并列，但那份 PDF **没有**给安全窗口的独立模型出处。本件照实写「无独立工具、只能派生登记」，**不为它虚构来源**。
- **shots 19 / 20 是否已用**：属作者裁定，本件不裁（§W19-9）。

**本件不执行的清单**：未下载任何 ADMETlab 数据、未调用任何 API / 网页端点、未实现或运行 GC-ML / Marrero-Gani 闪点模型、未产出任何闪点 / 沸点 / 熔点 / 安全窗口数值、未把任何安全描述符写入特征表或池、未占 shot 编号、未做任何 git 操作。
