## 28.53 Week 19 D7 安全通道登记（N14）：闪点 / 沸点 / 熔点 / 安全窗口 登记为第四通道，覆盖门 0.30 与 DN 0.0% 前例在册，只登记不执行（2026-09-28）
|
**定位**：本件是 `Week19立项计划_文献驱动三线.md` §W19-6「安全通道登记（N14，只登记，不执行）」的落地章。本件只做五件事：① 登记工具选型 / 版本 / 许可；② 说明为什么本周不执行；③ 列执行前必须补齐的前置条件；④ 重述 §W19-8 不做清单；⑤ 记分牌纪律自我澄清。**本件不执行任何计算、不下载、不调用任何工具、不产任何标签或读数、不占 shot 编号、不动任何冻结件、不引用 Reaxys 数值**；`produces_reading = false`。
**登记表（机器可读）**：`probes/w19_safety_channel_registry.json`；行文版：`reports/w19_safety_channel.md`。
|
**① 登记了什么（四条候选通道，全部 `registered_not_executed`）**
| 通道 | 性质 | 拟用工具 | 版本登记 | 许可登记 |
| --- | --- | --- | --- | --- |
| `safety_flash_point` | 闪点 | GC-ML 模型 + **Marrero-Gani 基团贡献**（只用一级基团表示） | PDF 未给独立版本号；框架 = Marrero & Gani 2001, Fluid Phase Equilib. 183, 183−208（PDF 引 50）；实现 = Alshehri et al. 2022, AIChE J. 68, e17469（PDF 引 49） | `not_verifiable_in_repo` |
| `safety_boiling_point` | 沸点 | **ADMETlab 3.0** | 3.0（PDF 引 48 = Fu et al., Nucleic Acids Res. 2024, 52, W422−W431） | `not_verifiable_in_repo` |
| `safety_melting_point` | 熔点 | **ADMETlab 3.0**（与沸点同源同版本） | 3.0（同上） | `not_verifiable_in_repo` |
| `safety_window` | 安全窗口（前三条的组合判据） | **无独立工具**；只能由前三条派生登记 | n/a（派生通道，不虚构版本） | n/a（上游 ADMETlab 判读仍适用） |
- 出处可核：计划书 §W19-6 原文 + `E:/大二/d2qc/电解液（长期项目）/文献调研/重点且同向/au5c01628.pdf`（JACS Au 2026, 6, 2288−2302；DOI 10.1021/jacsau.5c01628）。PDF 原句：*"Boiling and melting point were predicted employing ADMETlab 3.0.48"* 与 *"Flash point was predicted employing the GC-ML-model,49 where only the first-order group representation of the Marrero-Gani framework was considered.50"*。
- 口径澄清：`.48` / `,49` / `.50` 是 PDF 的**上标引文号**，不是版本号；因此 ADMETlab 的登记版本 = **3.0**，闪点链登记为「框架 1 篇 + 实现 1 篇」。
|
**② 为什么只登记、不执行**
- **主线占满**：本周主线是 η / HOMO-LUMO / 氧化还原（HOMO `0.19050925839013938` 与 LUMO `0.13855083976437643` 已过 0.20 eV 门；η 在役族级 `0.17477197208762` 未过 0.15 门）。安全是**第四通道**。
- **撞 §W19-8 两条红线**：「不做生成闭环、不做候选生成器」（uniqueness **0.349** 证据在册）与「不开无预注册的枪」。安全窗口天然是多目标组合判据，一上手就滑向生成式闭环。
- **计划书写死**：§W19-6 原文「本周不执行任何计算，不占 shot 编号。」⇒ `shot_number_taken = null`。
- **覆盖未测**：§W19-6 要求的 gate 0.30 覆盖检查，本机**连测都还没测**（本件不测）。
- **许可不可核**：全仓 `rg -S ADMETlab` / `rg -S Marrero` 均 0 命中（本件自身除外），四条通道的 `licence_note` 一律登记 `not_verifiable_in_repo`。
|
**③ 执行前必须补齐的前置条件（六条，缺一不许开枪）**
1. 独立预注册先立（先锁门槛、预注册永不事后修订，lever-8 先例）。
2. 许可判读先补（ADMETlab 3.0 与 Marrero-Gani / GC-ML 两条链的许可、API 条款与再分发边界）。
3. 覆盖门先过（gate **0.3**，口径 `covered_keys / target_keys`；DN 前例覆盖 **0** / 目标 **1043** = **0.0%** 未过门，裁定 `channel_does_not_enter_the_feature_table`）。
4. 适用域声明在先，且与 ε 的 D1 分域声明（`NumHDonors ≥ 1 and TPSA ≥ 20.0`，§28.45）**分开登记**。
5. 隔离声明：安全读数**独立成板**，**不得与 ε 主记分牌（基线 `0.4091179943351143` / 头条 `0.4766400383507876`）或 η 通道读数（行级 `0.08506361044387624` / 族级 `0.08908094784092072`）混比**。
6. 先占号后跑：shots 取号前先由作者裁定 **shot 19 / 20 是否已用掉编号**（§W19-9；本件不裁）。
|
**④ §W19-8 不做清单（逐条重述）**
- 不接 OMat24（无机晶体，与本项目分子液体错配）。
- 不做生成闭环、不做候选生成器（uniqueness **0.349** 证据在册）。
- 不把 ElectrolyteGPT 的代理输出当训练数据；不用任何随机拆分文献数字做对照靶或晋升依据。
- 不重跑已在盘的 W17 资产（Batt-P30K 下载与标定、Onsager 探针、`homo_lumo_baselines`、`dielectric_channel_v2`）。
- 不把行级随机折读数当对照靶（文献读数、仓内 Onsager 探针与 channel_v2 读数都不行）。
- 不动 6 个冻结件（v03 `ff214293…`、v11plus `159b928f…`、viscosity_v01 `12dfa03f…`、3 个预注册件 `ab3503c0…` / `77f61a83…` / `b838febb…`）。
- 不开无预注册的枪；81 MB 原始层不进任何 bundle；受限值永不在再分发层出现。
- 不在本章修订 Week 18 的任何判据（W18-2 端点定义、W18-7 退出判据只能由作者确认后修订，修订即记录）。
|
**⑤ 记分牌纪律（自我澄清）**
- **本件抬高主记分牌了吗？没有。** `promoted = false`、`produces_reading = false`、`scoreboard_attempts_delta = 0`；主记分牌尝试 **0** 次，累计仍 **11** 次；冻结基线 `0.4091179943351143` 与冻结头条 `0.4766400383507876` **原位未动**。
- 口径**永不混比**：ε **457** 行 / **97** 化合物 / **276** 个（化合物, T）对 / 训练侧全表 **2029** 行，**不得**与 η 的 **4151** 行 / **976** 键（族级 **3582** 行 / **957** 键）混说；ε 的诚实端点 `0.5861142332208197` 与冻结头条 `0.4766400383507876` 永不混比。
- 本件不含任何 Reaxys 数值（§28.33 红线）；登记里的数字全部来自仓内文件或那份 PDF 的文献出处。
|
**数字自检**（逐条列 token → 来源）
- `0.3` / `covered_keys` / `target_keys` / `0` / `1043` / `channel_does_not_enter_the_feature_table` ⇒ `probes/walden_dn_channel_summary.json::dn_channel.coverage_threshold` / `::dn_channel.coverage_definition` / `::dn_channel.admissible` / `::decision.dn_channel`；`probes/four_channel_coverage_summary.json::pinned.dn_covered_keys` / `::pinned.dn_target_keys`
- `0.15` ⇒ `probes/viscosity_baseline_summary.json::primary_gate.threshold`（`group_key_passed = false`）
- `0.17477197208762` / `0.15686276760094522` / `0.08506361044387624` / `0.08908094784092072` / `4151` / `976` / `3582` / `957` ⇒ `probes/w19_chemprop_viscosity_summary.json`｜`reports/_w19_section_d5.md`（§28.49）
- `0.19050925839013938` / `0.13855083976437643` / `0.20` ⇒ `probes/four_channel_coverage_summary.json::pinned`｜`reports/w19_ranking_key_spec.md`（§28.50）
- `0.4091179943351143` / `0.4766400383507876` / `457` / `97` / `276` ⇒ `probes/four_channel_coverage_summary.json::pinned`
- `2029` ⇒ `reports/_w18_readme_draft.md::4`（训练侧全表行数）
- `0.5861142332208197` ⇒ `reports/decisions_log.md::§28.42`｜`reports/w19_channel_transfer.md`（§28.51）
- `0.349` ⇒ `reports/w19_ranking_key_spec.md::16`｜计划书 §W19-8
- `11`（累计主记分牌尝试）⇒ `reports/_w19_section_d5.md`（§28.49）｜`reports/decisions_log.md::§28.41`
- `NumHDonors ≥ 1 and TPSA ≥ 20.0` ⇒ `reports/decisions_log.md::§28.45`
- `ADMETlab` / `Marrero-Gani` / `GC-ML` / `JACS Au 2026, 6, 2288−2302` / `10.1021/jacsau.5c01628` ⇒ `au5c01628.pdf`（PyMuPDF 抽取，参考文献 48–50）
- `28.53` ⇒ 本节号（任务书逐字指定）
- **不可核登记（照实）**：许可（仓内 0 命中，`not_verifiable_in_repo`）；闪点链无单一打包版本号；安全窗口无独立模型出处；shots 19 / 20 归属属作者裁定。
|
