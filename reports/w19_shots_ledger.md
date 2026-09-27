# W19-D9 shots 记账台账（计划书 §W19-9 落地件）

**状态**：`prereg_status = locked_pending_author_confirmation`——台账一经写入即冻结（`no_retroactive_edit = true`），但其**效力待作者确认后方才生效**。本件不声明 `locked_before_run`，因为本件是在 W19 七条 lane 跑完之后才落笔的（见 `generated_at_utc` 与各 lane 的 `generated_at`）。

**机器可读台账**：`probes/w19_shots_ledger.json`。**字面钉测试**：`tests/test_w19_shots_ledger.py`。

**权威依据**：`E:/大二/d2qc/电解液（长期项目）/文献调研/重点且同向/Week19立项计划_文献驱动三线.md` §W19-9；同文重述见 `reports/decisions_log.md:6071`（§28.51）与 `reports/w19_channel_transfer.md:47`。

**本件只做四件事**：① 写清 shots 占用规则；② 给 shot 19 / 20 / 21 的逐枪证据；③ 给出裁定与两分支对照；④ 自证主记分牌本周 0 次尝试、累计 11 次不变。**本件不拟合任何模型、不产任何 R² / MAE、不动任何冻结件、不引用 Reaxys 数值**；`produces_reading = false`。

## 一、shots 占用规则（本件采用的判据）

- **判据来源**：计划书 §W19-9 的字面判据是「**shot 19 / 20 对应的资产在仓内已存在**」（`reports/decisions_log.md:6071`）。本件沿用该字面判据，**不自造更复杂的占用规则**。
- **占用定义**：一支枪的编号被「用掉」，当且仅当它对应的产出资产**已在本周（W19 lane 周）之前落盘且已入册**；或它被计划书**明文预分配**了编号。
- **复核不占号**：本周的审计 / 复核 / 外部交叉核对工作不触发主记分牌（ε）晋升尝试（逐条 `promoted = false`），按「复核不占号」处理——本周九项工作**全部不新增占号**。
- **本文不改口径**：本节规则一旦作者确认即不得事后改（§W19-9 原文：「该判定写入预注册，不得事后改」）。

## 二、逐枪证据表

| shot | 归属（计划书原编号） | 对应资产 | 本周之前已在盘？ | 产读数？ | 状态 |
| --- | --- | --- | --- | --- | --- |
| 19 | Batt-P30K 交叉核对（§W19-2 / §W19-9） | `reports/decisions_log.md` §28.17（Batt ↔ PubChemQC 标定 n = 111）+ `probes/w19_batt_direct_hit_summary.json` | **是** | 是 | **consumed**（已用） |
| 20 | Onsager 预检（条件性，§W19-2 / §W19-9） | `probes/dielectric_onsager_delta_summary.json` | **是** | 是 | **consumed**（已用） |
| 21 | 抽取探针 Phase-0（§W19-2 标题预分配；本周以 W19-D4 落地） | `probes/w19_extraction_phase0_prereg.json` + `reports/w19_extraction_phase0.md` | 否（本周新落） | 否 | `taken_this_week_phase0_design_only` |

**shot 19 证据链**
- `reports/decisions_log.md:4706`：§28.17 标题「轨道第二源（PubChemQC B3LYP/6-31G*//PM6, CC BY 4.0；**W17-12**）」——该节由 W17 收口提交 `a6ed806`（2026-09-27）引入，早于 W19 lane 周。
- `reports/decisions_log.md:4748`：「判定 D：n ≥ 60 通过，**n = 111**；2 折样本外」。
- `reports/w19_state_audit.md:28`：D1 对本机实测逐字复核该资产，结论「**一致**」（并记 sha256 `4208fe8adf4ed6eee305b1a83ad322aada7f5bea01f538a57e45462a86899838`）。
- `probes/w19_batt_direct_hit_summary.json::shot_accounting_judgement.basis[2]`：D2 自己明文登记「该脚的标定部分（n = 111）**已被登记为已用资源**」——这是仓内独立佐证，不是本件推断。

**shot 20 证据链**
- `probes/dielectric_onsager_delta_summary.json`：`generated_at = 2026-09-25T05:55:35.227743+00:00`（早于本周），`decision.decision = "go"`，八臂读数与 `domain_counts` 均在盘。
- 入册章节：`reports/decisions_log.md:5648`（§28.44，判 `refuted`）。

**shot 21 证据链**
- `probes/w19_extraction_phase0_prereg.json::shot_accounting`：`planned_shot_in_the_plan = 21`、`plan_reference = "§W19-2 标题预分配 shot 21"`、`recommended_shot = 21`、`fallback_if_shot_19_20_counted = 22`。
- 同处 `this_file_consumes_a_shot = false`，rationale：「本件是 Phase-0 设计件，本周不执行抽取；按 §W19-9『每枪先锁预注册』，本件锁定的是执行前的模板与门槛，**占号发生在抽取执行时**」——即 21 号由抽取**执行**占用，本件只做设计。顶层 `produces_reading = false`。
- 行文版：`reports/w19_extraction_phase0.md:100`（§九 shot 记账）。

## 三、本周九项工作「复核不占号」逐条

| lane | 机器可读产物 | 字面标志 | 触发主记分牌晋升？ |
| --- | --- | --- | --- |
| W19-D1 | 无 JSON（`reports/w19_state_audit.md`） | 审计件，报告自述「未运行任何拟合或训练」 | 否 |
| W19-D2 | `probes/w19_batt_direct_hit_summary.json` | `read_only = true`、`models_fitted = 0`、`reaxys_values_used = false`、`writes_any_pool = false` | 否 |
| W19-D3 | `probes/w19_onsager_grouped_summary.json` | `promotes_no_reading = true`、`main_scoreboard_untouched = true`、`scoreboard_attempts_delta = 0` | 否 |
| W19-D4 | `probes/w19_extraction_phase0_prereg.json` | `produces_reading = false` | 否 |
| W19-D5 | `probes/w19_chemprop_viscosity_summary.json` | `promoted = false`（读数在 η 通道） | 否 |
| W19-D6 | 无 JSON（`reports/w19_ranking_key_spec.md`） | 报告自述「不拟合任何模型…不产生任何新性质预测值」 | 否 |
| W19-D7 | `probes/w19_safety_channel_registry.json` | `produces_reading = false`、`promotes_no_reading = true`、`shot_number_taken = null` | 否 |
| W19-N2 | `probes/w19_batt_gap_crosscheck_summary.json` | `promoted = false` | 否 |
| W19-7 | 无 JSON（`reports/w19_channel_transfer.md`） | 报告自述 `produces_reading = false`、`promoted = false`、不占 shot | 否 |

**键表不统一的照实登记**：以上字面标志并非同一个键。只有 W19-D4 / W19-D7 直接带 `produces_reading = false`；W19-D2 / D5 / N2 带 `promoted = false`；W19-D3 带 `promotes_no_reading` / `main_scoreboard_untouched` / `scoreboard_attempts_delta`；W19-D1 / D6 / W19-7 无 JSON 产物（D3 报告 §0 已把这类情形登记为 `vocabulary gap`）。**本件不把这些不等价的字面键当成同一个字面**，只把它们共同证明的事实（不触发主记分牌晋升尝试）当作「复核不占号」的依据。

## 四、裁定与两分支对照

**本件采用的读法**：shot 19 / 20 **已用掉编号**；shot 21 由 §W19-2 预分配给抽取探针 Phase-0；本周九项工作**复核不占号**。

⇒ **`next_shot_number = 22`**（下一支会消耗编号的「产新读数」枪取 22；§W19-3 若落为可执行枪，亦取 22）。

| 分支 | 读法 | 依据 | 下一支产读数的枪 |
| --- | --- | --- | --- |
| 分支 A（本件采用） | shot 19 / 20 视为**已用** | 计划书 §W19-9「若视为已用，新工作取 shot 22 起」 | **22** |
| 分支 B（备选） | shot 19 / 20 视为**复核性工作、不占号** | `probes/w19_extraction_phase0_prereg.json::shot_accounting.recommended_reading` / `fallback_if_shot_19_20_counted = 22` | **22** |

**分支稳健性**：两支读法在「下一支产新读数的枪」上收敛到同一个数字 **22**——裁定对这个分支**不敏感**。真正需要作者拍板的是 shot 19 / 20 的**标签**（算已用，还是算复核不占号），而不是 `next_shot_number` 的值。

## 五、未决项（须作者确认的具体一条）

- **须作者确认**：shot 19 / shot 20 的编号归属——**本件采用「已用掉编号」**。若作者改判为「复核性工作、不占号」，本台账须由作者在预注册层拍板后重写；重写后 `next_shot_number` 仍为 **22**（见 §四分支稳健性）。
- **生效条件**：`effective_after_author_confirmation = true`；确认前本件不得被单方引用为「已生效」，也不得据此宣称任何枪已达标。
- **冻结**：`no_retroactive_edit = true`——生效后不得事后改（§W19-9 原文口径）。

## 六、主记分牌自证：本周 0 次尝试、累计 11 次不变

- 冻结基线 `0.4091179943351143`、冻结头条 `0.4766400383507876` **原位未动**（`probes/export_week18_results.py:60` / `:62`）。
- 累计主记分牌尝试 **11** 次（`probes/export_week18_results.py:65`，累加口径见 `:459-461`：Week 14 读 10，Week 17 加一，Week 18 不加）。
- 本周（W19）主记分牌尝试增量 **0** 次：本件 `scoreboard_attempts_delta = 0`、`main_scoreboard_untouched = true`；九项工作逐条 `promoted = false`（见 §三）。
- 本件**不占任何 shot 编号**（它是记账件，不产读数）。

## 七、照实登记为「不可核」的点

- 计划书 §W19-9 在仓内的逐字落点只有 `reports/decisions_log.md:6071`（§28.51）与 `reports/w19_channel_transfer.md:47` 两处**转述**；计划书原文不在仓库内，本件不对其另行取证。
- 本件**无法**在仓内核实 shot 19 / 20 在计划书里「本应产出什么」是否与仓内既有资产逐字等同——本件只核实「对应资产已存在」这一条字面判据。
- 任务书中提到的 `probes/w19_state_audit*.json` 在仓内**不存在**（`git ls-files` 仅列 `reports/w19_state_audit.md` 与 `tests/test_w19_state_audit.py`）；D1 的证据一律只引报告本身。
- 任务书中提到的 `reports/w19_safety_channel_registry.json`，盘上实际路径为 `probes/w19_safety_channel_registry.json`（本件按盘上实测路径引用）。

## 八、数字自检（token → 来源）

- `19` / `20` / `21` / `22` ⇒ 计划书 §W19-9（`reports/decisions_log.md:6071`、`reports/w19_channel_transfer.md:47`）｜本件 `next_shot_number`
- `n = 111` ⇒ `reports/decisions_log.md:4748`｜`reports/w19_state_audit.md:28`
- `decision = "go"` ⇒ `probes/dielectric_onsager_delta_summary.json::decision.decision`
- `2026-09-25T05:55:35.227743+00:00` ⇒ `probes/dielectric_onsager_delta_summary.json::generated_at`
- `0.4091179943351143` / `0.4766400383507876` / `11` ⇒ `probes/export_week18_results.py:60` / `:62` / `:65`
- `a6ed806`（W17 收口提交）⇒ `git log --diff-filter=A -- reports/decisions_log.md`（§28.17 引入提交）
- `4208fe8adf4ed6eee305b1a83ad322aada7f5bea01f538a57e45462a86899838` ⇒ `reports/w19_state_audit.md:28`
- `28.55` ⇒ 本节号（任务书逐字指定）
- **不可核登记（照实）**：见 §七。
