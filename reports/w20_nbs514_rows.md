# W20-6b NBS-514 同源补温行：28 条候选 → 26 条可用 / 25 个不同 (化合物, T)，三关全过、不晋升

- **任务** `week20_w20_6b_nbs514_rows`｜**节号** §28.62｜**日期** 2026-09-28
- **性质**：**不拟合任何模型、不占 shot 编号、不产任何通道读数、不动任何冻结件**；`produces_reading = false`、`promoted = false`、`shot_number_taken = null`、`scoreboard_attempts_delta = 0`、`reaxys_values_used = 0`、`models_fitted = 0`、`main_scoreboard_untouched = true`。本件产出的是**同源补温行的可采性判读**，不是读数。
- **权威输入**：`reports/week20_project_charter.md` §1 `W20-6b`；`data/interim/nbs514_organic_part1..4.csv`（实测 **636** 行）；结构侧车 `data/processed/nbs514_structure_candidates.csv`；名册 `data/dielectric_v03.csv`；一手 PDF `data/raw/nbs514/nbscircular514.pdf`（在仓）。
- **机器可读产物**：`probes/w20_nbs514_rows_prereg.json`（跑前锁定）、`probes/w20_nbs514_rows_summary.json`（跑后落盘）、逐行表 `probes/artifacts/w20_nbs514_rows.csv`（28 行）。

## 1. 规则（跑前钉）

一条转录行是**候选**当且仅当：① 来自 NBS Circular 514 有机液体转录（parts 1–4）；② 经冻结结构侧车解出 InChIKey；③ 该 InChIKey **已在 `data/dielectric_v03.csv` 名册上**；④ 该名册观测是**一手**的 —— 名册 `source_quality ∈ {four_figures, primary_experimental_public_pdf, public_domain_critical_compilation}`。

第 ④ 条排除了两类名册行：共享三图表的 `three_figures`，与开放获取综述表 `open_access_review_table`。保留的三类都是**一手测量或公共领域权威汇编**，NBS 行是在名册已有化合物上**补一行温度**，而不是把外来化合物或转述表再搬一次。

## 2. 计数：28 → 26 → 25（照实）

| 口径 | 行数 |
| --- | ---: |
| NBS 转录总行 | 636 |
| 落在 v03 名册化合物上的转录行（不限质量） | 121 |
| **候选行**（限定一手名册质量） | **28** |
| 其中带频率注记、被频率关剔除 | 2 |
| **可用行** | **26** |
| **不同 (化合物, T) 对** | **25** |

「不同 (化合物, T)」用标准 InChIKey 的**连接块（前 14 字符）**作化合物身份：cis-3-己烯与 trans-3-己烯共享骨架且同为 298.15 K，算**一个**化合物，故 26 条可用行给出 25 个不同对（若用完整 InChIKey 则是 26）。被剔除的 2 条是 `nbs514:p20:008`（Butyronitrile，f=3.6×10^8 cycles/sec）与 `nbs514:p23:010`（Valeronitrile，同频率），二者都落在色散区内，不是静态介电常数。

## 3. 三关判据（按序）

| 关 | 判据 | 读数 | 判 |
| --- | --- | --- | :--: |
| 1 licence | 从源自许条款读判词 | NBS Circular 514 = 美国政府出版物 `10.6028/nbs.circ.514`（Maryott & Smith 1951），**公共领域** | ✅ **open** |
| 2 locator | 每行需 `DOI + 表/图定位` | 每行带 `source_id = nbs514:pXX:YYY`（印刷页:行）、DOI 与印刷页 | ✅ **locatable** |
| 3 first_hand | 需回一手源复核 | 圆周原文 PDF **在仓**（`data/raw/nbs514/nbscircular514.pdf`），定位行回原文核 | ✅ **first_hand_checked** |

**三关全过 ⇒ 合格（可入池）**：`admissibility.admissible = true`、`licence_cleared = true`、`locator_cleared = true`、`first_hand_cleared = true`。这与 6a 的 Org-Mol 形成对照：Org-Mol 三关**全不过**（licence restricted / locator unreachable / first_hand unreachable）⇒ `inadmissible`；NBS-514 三关**全过** ⇒ 合格行。

## 4. 频率关（唯一咬人的关）

咬人的**不是**许可关，而是 **NBS 自身的频率关**：带显式微波频率注记的行在色散区内，不是静态 ε，按 `scripts/resolve_nbs514_structures.py` 的 `frequency_dependent` 排除规则剔除（与仓内既有 127 条频率行一视同仁）。28 条候选中恰好 **2 条**带频率注记，剔除后 26 条可用。

## 5. 「同源扩行」对「外来化学空间块」（本 lane 的存在理由）

| 用法 | 读数 | 对照（冻结基线） | 判定 |
| --- | ---: | ---: | --- |
| 外来化学空间块（NBS 作为**新化合物**导入，+362 行 / 360 化合物） | 0.3809089252433510 | 0.4091179943351143 | **有害（已证否）** |
| 同源扩行（同源行扩池，457 → 1934 训练行） | 0.530029 | 0.4091179943351143 | **全项目唯一有效（+0.1209）** |

本 lane 用的是**未用过的那个用法**：不导入任何新化合物，只在**名册内化合物**上补 NBS 温度行。本件**不跑任何臂、不产任何读数**，只把这条「同源补温行」集合的可采性钉死，供后续（若立项）在**预注册**下使用；本件自身 `promoted = false`、`ceiling_break = false`。

## 6. 照实登记「不可核」

- **不是新化合物**：候选行 100% 落在 v03 名册化合物上（`inchikey` 逐一在册）；无一行引入外来化学空间。
- **不破上限**：ε 标签上限 **161 → 157 → 153** 不动，净新增上界 **+4** 不变；本件只登记可采性，`ceiling_break = false`。
- **2 条频率行不可用**：Butyronitrile / Valeronitrile 的 NBS 值（20.3 / 17.4 @ 294.15 K）与名册值（22.0 / 21.0 @ 298.15 K，来源 `primary_experimental_public_pdf`）**不一致**；本件不作仲裁、不平均、不改名册，只按频率关剔除并照实登记。
- **不做仲裁/不写回**：本件不向 `data/` 写入任何行，只写 `probes/` 三个自级产物与 `reports/` 一份报告。

## 7. 纪律

- `promoted = false`、`produces_reading = false`、`shot_number_taken = null`、`scoreboard_attempts_delta = 0`、`reaxys_values_used = 0`、`models_fitted = 0`。
- 主记分牌本周 **0 次尝试**，累计 **11 次不变**。
- **不引用任何 Reaxys 数值**；**不为 ε 购买或抓取任何受限库**。
- verdict = `same_source_rows_admissible_not_promoted`。

