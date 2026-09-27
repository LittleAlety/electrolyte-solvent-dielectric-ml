## 28.55 Week 19 D9 shots 记账台账：shot 19 / 20 判「已用掉编号」、21 归抽取探针 Phase-0、下一支产读数枪取 22；主记分牌本周 0 次尝试、累计 11 次不变（2026-09-28）
|
**定位**：本件是 `Week19立项计划_文献驱动三线.md` §W19-9「纪律与 shots 记账」的落地章。机器可读台账 `probes/w19_shots_ledger.json`；行文版 `reports/w19_shots_ledger.md`；字面钉测试 `tests/test_w19_shots_ledger.py`。**本件不拟合任何模型、不产任何 R² / MAE、不动任何冻结件、不引用 Reaxys 数值**；`produces_reading = false`。
|
**① 占用判据（本件采用，且须作者确认）**
- 判据来源是计划书 §W19-9 的**字面**判据：「shot 19 / 20 对应的资产在仓内已存在」（`reports/decisions_log.md:6071`；同文转述 `reports/w19_channel_transfer.md:47`）。本件沿用该字面判据，**不自造更复杂的占用规则**。
- 一支枪的编号被「用掉」⇔ 其对应产出资产**在本周（W19 lane 周）之前已落盘并已入册**，或该编号被计划书**明文预分配**。
- 审计 / 复核 / 外部交叉核对**不触发主记分牌（ε）晋升尝试**⇒ 按「**复核不占号**」处理。
|
**② 逐枪证据表**
| shot | 归属（计划书原编号） | 对应资产 | 本周之前已在盘？ | 产读数？ | 状态 |
| --- | --- | --- | --- | --- | --- |
| 19 | Batt-P30K 交叉核对 | `reports/decisions_log.md` §28.17（Batt ↔ PubChemQC 标定 n = 111） | **是** | 是 | **consumed** |
| 20 | Onsager 预检（条件性） | `probes/dielectric_onsager_delta_summary.json` | **是** | 是 | **consumed** |
| 21 | 抽取探针 Phase-0（本周 = W19-D4） | `probes/w19_extraction_phase0_prereg.json` | 否（本周新落） | 否 | `taken_this_week_phase0_design_only` |
- **shot 19**：`reports/decisions_log.md:4706`（§28.17 标题，W17 收口提交 `a6ed806` 引入）与 `:4748`（「判定 D：n ≥ 60 通过，**n = 111**；2 折样本外」）；`reports/w19_state_audit.md:28` 本机逐字复核「**一致**」；`probes/w19_batt_direct_hit_summary.json::shot_accounting_judgement.basis[2]` 独立登记该标定「**已被登记为已用资源**」。
- **shot 20**：`probes/dielectric_onsager_delta_summary.json` 的 `generated_at = 2026-09-25T05:55:35.227743+00:00`（早于本周）、`decision.decision = "go"`；入册章节 `reports/decisions_log.md:5648`（§28.44）。
- **shot 21**：`probes/w19_extraction_phase0_prereg.json::shot_accounting`（`planned_shot_in_the_plan = 21`、`plan_reference = "§W19-2 标题预分配 shot 21"`、`fallback_if_shot_19_20_counted = 22`、`this_file_consumes_a_shot = false`，rationale「占号发生在抽取执行时」）；顶层 `produces_reading = false`。
|
**③ 本周九项工作「复核不占号」**
| lane | 字面标志 | 触发主记分牌晋升？ |
| --- | --- | --- |
| W19-D1 | 审计件，报告自述「未运行任何拟合或训练」（无 JSON） | 否 |
| W19-D2 | `read_only = true`、`models_fitted = 0`、`reaxys_values_used = false`；`writes_any_pool = false` | 否 |
| W19-D3 | `promotes_no_reading = true`、`main_scoreboard_untouched = true`、`scoreboard_attempts_delta = 0` | 否 |
| W19-D4 | `produces_reading = false` | 否 |
| W19-D5 | `promoted = false`（读数在 η 通道） | 否 |
| W19-D6 | 报告自述「不拟合任何模型…不产生任何新性质预测值」（无 JSON） | 否 |
| W19-D7 | `produces_reading = false`、`promotes_no_reading = true`、`shot_number_taken = null` | 否 |
| W19-N2 | `promoted = false` | 否 |
| W19-7 | 报告自述 `produces_reading = false`、`promoted = false`、不占 shot（无 JSON） | 否 |
- **键表不统一的照实登记**：只有 D4 / D7 直接带 `produces_reading = false`；D2 / D5 / N2 带 `promoted = false`；D3 带 `promotes_no_reading` 一族；D1 / D6 / W19-7 无 JSON 产物（D3 报告 §0 已登记为 `vocabulary gap`）。本件不把这些**不等价**的字面键当成同一个字面，只把它们共同证明的事实当作依据。
|
**④ 裁定与两分支对照**
| 分支 | 读法 | 依据 | 下一支产读数的枪 |
| --- | --- | --- | --- |
| A（**本件采用**） | shot 19 / 20 视为**已用** | 计划书 §W19-9「若视为已用，新工作取 shot 22 起」 | **22** |
| B（备选） | shot 19 / 20 视为**复核性工作、不占号** | `probes/w19_extraction_phase0_prereg.json::shot_accounting.recommended_reading` / `fallback_if_shot_19_20_counted = 22` | **22** |
- **分支稳健性**：两支读法在「下一支产新读数的枪」上**收敛到同一个数字 22**——裁定对该分支**不敏感**。须作者拍板的是 shot 19 / 20 的**标签**，不是 `next_shot_number` 的值。本件裁定 `next_shot_number = 22`。
|
**⑤ 未决项与冻结**
- **须作者确认（唯一一条）**：shot 19 / shot 20 的编号归属——本件采用「**已用掉编号**」；若改判为「复核不占号」，须由作者在预注册层拍板后重写，且 `next_shot_number` 仍为 **22**。
- `prereg_status = locked_pending_author_confirmation`（本件**不**声明 `locked_before_run`，因为它是在七条 lane 跑完之后才落笔的）。
- `effective_after_author_confirmation = true`：确认前本件不得被单方引用为「已生效」。
- `no_retroactive_edit = true`：生效后**不得事后改**（§W19-9 原文口径）。
|
**⑥ 主记分牌自证**
- 冻结基线 `0.4091179943351143`、冻结头条 `0.4766400383507876` **原位未动**（`probes/export_week18_results.py:60` / `:62`）。
- 累计主记分牌尝试 **11** 次（`probes/export_week18_results.py:65`；累加口径见 `:459-461`）。本周（W19）增量 **0** 次：`scoreboard_attempts_delta = 0`、`main_scoreboard_untouched = true`，九项工作逐条 `promoted = false`。
- 本件**不占任何 shot 编号**（记账件，不产读数）。
|
**⑦ 数字自检（token → 来源）**
- `19` / `20` / `21` / `22` ⇒ 计划书 §W19-9（`reports/decisions_log.md:6071`）｜本件 `next_shot_number`
- `n = 111` ⇒ `reports/decisions_log.md:4748`｜`reports/w19_state_audit.md:28`
- `decision = "go"` ⇒ `probes/dielectric_onsager_delta_summary.json::decision.decision`
- `2026-09-25T05:55:35.227743+00:00` ⇒ `probes/dielectric_onsager_delta_summary.json::generated_at`
- `0.4091179943351143` / `0.4766400383507876` / `11` ⇒ `probes/export_week18_results.py:60` / `:62` / `:65`
- `4208fe8adf4ed6eee305b1a83ad322aada7f5bea01f538a57e45462a86899838` ⇒ `reports/w19_state_audit.md:28`
- `28.55` ⇒ 本节号（任务书逐字指定）
- **不可核登记（照实）**：计划书原文不在仓内（§W19-9 在仓内只有 `:6071` 与 `w19_channel_transfer.md:47` 两处转述）；任务书提到的 `probes/w19_state_audit*.json` 不存在（`git ls-files` 仅列 md 与测试）；`reports/w19_safety_channel_registry.json` 实际在 `probes/` 下。
|
