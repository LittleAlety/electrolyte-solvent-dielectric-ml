## 28.62 上限突破探针（W20-6 三条）：Org-Mol 溯源不破、NBS-514 同源补温行三关全过、CEP 88k 仅 Tier C（2026-09-28）
|
**定位**：本件是 Week 20 lane W20-6（§28.62）的落地章，三条并行子探针一次收口：6a Org-Mol 溯源、6b NBS-514 同源补温行、6c CEP 8.8 万 DFPT。全文分别见 `reports/w20_orgmol_provenance.md`、`reports/w20_nbs514_rows.md`、`reports/w20_cep_tierc.md`。|
**纪律**：三条子探针一律 `produces_reading = false`、`shot_number_taken = null`、`scoreboard_attempts_delta = 0`、`reaxys_values_used = 0`、`promoted = false`；主记分牌本周 **0 次尝试**、累计 **11 次不变**；不动任何冻结件、不引任何 Reaxys 数值。|
**① 6a Org-Mol 溯源（verdict = `inadmissible`，`ceiling_break = false`）**：Org-Mol = *npj Comput. Mater.* **11, 224 (2025)**，DOI `10.1038/s41524-025-01720-4`（arXiv `2501.09896`）；其 ε 微调数据溯源到 **CRC Handbook**（ref 53）与 **Landolt-Börnstein / Springer Materials**（ref 54），二者均在 W20 不做清单上。三关全不过 ⇒ 源级 `inadmissible`；微调集**不公开发布**（data availability：仅「合理的请求」下由通讯作者提供），行级表**拿不到**，故**一行都没分类**、三档计数均 **0**（`source_not_obtainable`）。**不破上限**：ε 标签上限 **161 → 157 → 153** 不动，净新增上界 **+4** 不变。全文见 6a 报告；`ceiling_break = false`。|
**①-表 6a 三关判据（逐关，逐字）**：
| 关 | 判词 | 过 | 理由 |
| --- | --- | :--: | --- |
| gate_1_licence | `restricted` | ❌ | 微调集不发布，其近室 ε 值汇集自两受限源（CRC Handbook；Landolt-Börnstein via Springer Materials），均在 W20 不做清单上 |
| gate_2_locator | `unreachable` | ❌ | 无逐行 DOI + 表/图定位；论文只在系列级引 refs 53 / 54 |
| gate_3_first_hand | `unreachable` | ❌ | 第 2 关无行可回，且一手源有付费墙 |
|
**② 6b NBS-514 同源补温行（verdict = `same_source_rows_admissible_not_promoted`，`admissible = true`，`promoted = false`）**：源 = NBS Circular 514（`10.6028/nbs.circ.514`，公共领域，PDF 在仓）；转录 4 份共 **636** 行，落在 v03 名册化合物上的有 **121** 行；按跑前规则（名册观测须为**一手**：`source_quality ∈ {four_figures, primary_experimental_public_pdf, public_domain_critical_compilation}`）取 **28 条候选** → 频率关剔除 **2** 条（色散区内非静态）→ **26 条可用 / 25 个不同 (化合物, T)**（化合物身份取 InChIKey 连接块）。**三关全过**：`licence = open`（公共领域）、`locator = locatable`（逐行 `nbs514:pXX:YYY` + DOI + 印刷页）、`first_hand = first_hand_checked`（回圆周原文 PDF）⇒ 合格。用法是**未用过的那个**：只在**名册内化合物**上补温度行（同源扩行 `0.530029`，+0.1209），**不是**已证否的外来化学空间块（`0.3809089252433510`，有害）。|
**③ 6c CEP 8.8 万 DFPT（verdict = `not_verifiable`，tier = `C`）**：句柄「CEP 8.8 万 DFPT」（约 88,000 条 DFPT 计算 ε，被举为「ε 的 QM9 等价物」）在本仓**无法落成具名数据集**（无 DOI / 具名数据集 / 许可文本 / 逐行定位，`screen_inputs` 五项全 `null`），本探针不发网络请求 ⇒ 许可判词**读不出** ⇒ `not_verifiable`，源不可导入，一行不分类（`source_not_verifiable`，三档均 0）。**物理理由**：气相 DFPT 计算 ε 与液相实验 ε **不是同一个量**（缺取向相关 **g**；Kirkwood 式里气相 `g = 1` 是构造性的），故只能作 **Tier C**（特征 / 排序信号），**永远不能**作液相靶的标签。|
**④ 隔离声明（永不可混）**：三条子探针**均不产读数**，其判据一律**不得**与 ε 主记分牌读数（`0.4091179943351143` / `0.4766400383507876`）比较；6b 引用的 `0.530029` / `0.3809089252433510` 只在「同源扩行 vs 外来块」的臂口径下引用，**不得**当新读数或新记分牌。|
**⑤ 性质**：三条子探针合计 `models_fitted = 0`、主记分牌 **0 次尝试**；6a / 6c 不产行，6b 登记 26 条合格补温行的**可采性**但**不写回 `data/`、不晋升**（`promoted = false`、`ceiling_break = false`）。|
|

