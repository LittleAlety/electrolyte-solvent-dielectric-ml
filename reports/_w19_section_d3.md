## 28.52 Week 19 D3 Onsager 残差层换到组外划分：结构族组外 5 门全过（`delta_layer_survives_out_of_family`），但域反号分裂未保持、ε>60 区仍不可解（2026-09-28）
|
**机制假设**：W18-P2 判 `refuted` 的那一枪，把 Onsager 残差 Δ-learning 放在**行级 RepeatedKFold** 上量；该协议允许同族近邻同时出现在训练与测试两侧，等于给「分子间关联」这一层开了后门。D3 的问法不是「再堆一次描述符」，而是**只换划分、不换模型**：把同一探针搬到 111 个 Murcko/Butina 结构族的组外 5 折 x 10 重复（共 50 折），回答计划书 §W19-5 锁定的三问。判据是**预注册的 5 门**，不是 R²，也不是主记分牌。
**预注册**：`probes/w19_onsager_grouped_prereg.json`，sha256 `921ba092c6dfc8976d045c089caeeafb714da639f6c24634a97bd3f9284c6839`，`status = locked_before_run`；跑前登记的**唯一一次增补**是把 `row_level_reproduction` 登记为并列基准（增补时仓内不存在本探针任何结果）。门定义逐字复用冻结的 `probes/dielectric_onsager_delta_probe.py::evaluate_gates`，公式不重写。
|
**池与切分 · 行级参考与组外读数并列、永不混比**
| 项目 | 值 |
| --- | --- |
| 行数 / 唯一 InChIKey | 234 / 234 |
| 结构族（Murcko scaffold；无环走 Butina） | 111（其中单例 76、最大 31） |
| 失败行 / 暂扣行 | 4 / 1 |
| 分层 lt20 / 20_60 / gt60 | 182 / 47 / 5 |
| 域 none / assoc_only / ionic_only / both | 150 / 66 / 15 / 3 |
| `structure_family`（主读数） | 5 折 x 10 重复 = 50 折，训练 149-206 |
| `row_level_reproduction`（对照基准） | RepeatedKFold 5 x 10 = 50 折，训练 187-188 |
| `inchikey`（退化对照，跑前已声明） | 234 组全为单例 ⇒ 退化成普通行级留出，**不计入组外压力** |
- 主读数逐 arm（MAE / R² / Spearman）：`O0_onsager` 10.488447267414694 / -0.682296765194945 / 0.67637461648358；`O1_structured_offset` 9.712536036273614 / -0.5243166065971072 / 0.7508995711631504；`R0_direct_regression` 7.6638502783946505 / 0.2618082947442962 / 0.7576630886950296；`R1_direct_with_logg` 7.105924504314814 / 0.1840837816325239 / 0.7944375166885387；`D0_delta_core` 9.462750080736846 / -0.2823334839412389 / 0.7496583230171197；`D1_delta_core_morgan` 9.732598032673137 / -0.512513404542229 / 0.7301984899382461；`D2_delta_log` 16.6468345368987 / -4.0825878705138585 / 0.6418337835273601；`D3_delta_leaky`（泄漏对照，不受门）8.562802610068925 / -0.062377601950978835 / 0.7558608323774854。
- **两条必须与读数同框的诚实话**：① 主读数上**最好的不是任何 Δ 臂**——`R1_direct_with_logg` 7.105924504314814、`R0_direct_regression` 7.6638502783946505，都低于全部 Δ 臂；② `D0_delta_core` 9.462750080736846 落在 `O0_onsager` 10.488447267414694 的 bootstrap 带内（配对簇 bootstrap `delta_mean = -1.0256971866778457`、`delta_ci95 = [-2.0646583943890198, 0.02264978539549294]`，**跨零**），故 5 门结论是**重复平均点估计**上的结论，不是分离结论。
|
**5 门逐 arm 裁定（主读数 `structure_family`；门槛值取自 summary 实测列）**
| 门 | 判据 | 门槛参照 | D0_delta_core | D1_delta_core_morgan | D2_delta_log |
| --- | --- | --- | --- | --- | --- |
| `a_donor_mae_below_onsager` | `mae_assoc(arm) < mae_assoc(O0_onsager)` | 16.66422703535138 | 13.966612961983486 PASS | 13.031472247883638 PASS | 23.5931562114305 FAIL |
| `b_ionic_mae_not_worse_than_onsager` | `mae_ionic(arm) <= mae_ionic(O0_onsager)` | 41.22140207561585 | 34.93832021859354 PASS | 40.17556915457252 PASS | 50.20548179109598 FAIL |
| `c_high_permittivity_improved` | `mae_gt60(arm) < 87.02347866934045` 或 `spearman_gt60(arm) > -0.7999999999999999` | 87.02347866934045 / -0.7999999999999999 | 72.0614455552206 PASS | 76.81859574687758 PASS | 93.62813989821383 / -0.6199999999999999（仅靠 spearman 子句）PASS |
| `d_overall_mae_below_structured_offset` | `mae(arm) < mae(O1_structured_offset)` | 9.712536036273614 | 9.462750080736846 PASS | 9.732598032673137 **FAIL** | 16.6468345368987 FAIL |
| `e_donor_mae_below_structured_offset` | `mae_assoc(arm) < mae_assoc(O1_structured_offset)` | 14.83331535120289 | 13.966612961983486 PASS | 13.031472247883638 PASS | 23.5931562114305 FAIL |
| **整臂通过** | 5 门全真 | — | **true** | false | false |
- `gates.headline_arm = D0_delta_core`、`gates.passed = true`；summary 自己声明该 headline 选择是**事后**取「确认臂里重复平均 MAE 最低」，并**把逐 arm 门结果并列在旁**。
|
**三问逐条裁定（verdict 字符串逐字照抄）**
| 问 | verdict | 关键依据 |
| --- | --- | --- |
| Q1 Δ 层组外是否仍过 5 门 | `delta_layer_survives_out_of_family` | 主读数 `headline_passed_all_five_gates = true`、`n_groups = 111`；`inchikey_control_degenerate = true` 且其 headline 也全过（退化对照**不构成独立证据**）；`D1_delta_core_morgan` 只失 `d`、`D2_delta_log` 失 4 门 |
| Q2 域反号分裂组外是否保持 | `sign_split_not_preserved_out_of_family` | 逐域偏置符号 vs 行级：`O0_onsager` opposite、`O1_structured_offset` opposite、`D0_delta_core` opposite、`D1_delta_core_morgan` opposite、`D2_delta_log` same；分组与行级两套 pattern **arm 对 arm 一致**，都判 4/5 为 opposite ⇒ 记「随机折内插值假象」，不记机制 |
| Q3 ε > 60 区组外是否仍不可解 | `zone_still_unsolvable_out_of_family` | `row_count = 5`、`threshold = 60`、`onsager_coverage_fraction = 0`、`onsager_coverage_is_split_invariant = true`；组外最佳确认臂 `mae_gt60 = 72.0614455552206` vs 行级最佳 `70.26943459448498` ⇒ `grouped_best_not_better_than_row_level = true`；组外 `bias_gt60`：D0 70.74055320184931、D1 76.65222626086577、D2 48.31560765575515 |
|
**判定与边界**
- `promotes_no_reading = true`；`main_scoreboard_untouched = true`；`scoreboard_attempts_delta = 0`；`produces_deployable_model = false`；**主记分牌尝试仍为 0，累计仍为 11 次**；冻结基线 `0.4091179943351143` 与冻结头条 `0.4766400383507876` 未动；`role` 明写**不是晋升臂**。
- **口径更正（本枪必须登记）**：summary 里**没有** `read_only` / `models_fitted` / `promoted` 三个键；承担同一职能的字面键是 `promotes_no_reading` / `main_scoreboard_untouched` / `scoreboard_attempts_delta` / `produces_deployable_model`。探针效果上是只读的，但**不以未出现的字面键作断言**。
- **复现检查**：`max_abs_difference = 0.0`、`reproduced_bit_for_bit = true`（比较 `mae` / `mae_assoc` / `mae_ionic` / `mae_gt60` / `r2` / `spearman` 六键），对照件 `probes/dielectric_onsager_delta_summary.json` sha256 `3acd499b2653135556bcdd61a1bdb2e8977973821f8b00f804e2431edef1754b`。
- **五条预注册 limitations 逐条照录**：① 池内 234 行一行一化合物，故计划书要求的「按 InChIKey 分组」在本池**约束不了任何东西**；② 结构族是本池唯一非退化的分组键，且比化合物划分**更粗**，故其读数是**下界**；③ 111 个结构族里 76 个是单例，大多数行看到的训练池与化合物级划分无异；④ ε>60 区只有 5 行，其 MAE 是**无区间的点估计**；⑤ Onsager 无标签且确定，其覆盖率**不随划分变化**，动的只有拟合臂。
- **honest_boundary 逐字**：`epsilon_lane_is_frozen = true`、`frozen_baseline = 0.4091179943351143`、`frozen_headline = 0.4766400383507876`、`main_scoreboard_untouched = true`、`not_a_promotion_arm = true`。
- **自我澄清**：分域/组外读数**不替换、不修订、不晋升**任何主记分牌数字；§2.1 与 §2.2 是同一池上的**两套协议**，只并列、**不平均**、不互为替代。本枪**零 Reaxys 引用**（`reaxys_numeric_red_line`：Reaxys 数值禁止进入任何池、特征或交付包）。
|
**产物清单**
- `probes/w19_onsager_grouped.py`（sha256 `e5396bb7dcad7ea4bf587256536105132be4a51c8c3a069efbf22607111046b3`）
- `probes/w19_onsager_grouped_prereg.json`（sha256 `921ba092c6dfc8976d045c089caeeafb714da639f6c24634a97bd3f9284c6839`）
- `probes/w19_onsager_grouped_summary.json`（sha256 `dabb9df580cb7d44e4cd096bdeb72543c0666f0d7bbe8114ded37cad7b9e7dba`）
- `reports/w19_onsager_grouped.md`（sha256 `f70ea93d8b4cd392ffa9e9e2e2eeb84b582ef0433a3e8a807231baa5a17224fe`）
- `tests/test_w19_onsager_grouped.py`（sha256 `f0c066abb46ba6db358102cb35c3ca25792d9beab4ce86961d783765bcc7e2a9`）
|
**数字出处**
- 234 / 234 / 111 / 76 / 31 / 4 / 1 与 182 / 47 / 5、150 / 66 / 15 / 3 ← `probes/w19_onsager_grouped_summary.json::pool` 与 `::structure_groups.group_size_histogram`
- 50 折 / 149-206 / 187-188 ← 同 JSON `::readings.structure_family.n_folds` / `::train_count_min` / `::train_count_max` 与 `::readings.row_level_reproduction`
- 全部逐 arm MAE / R² / Spearman ← 同 JSON `::readings.*.overall_metrics`
- 16.66422703535138 / 41.22140207561585 / 87.02347866934045 / -0.7999999999999999 / 9.712536036273614 / 14.83331535120289 ← 同 JSON `::readings.structure_family.overall_metrics.O0_onsager` 与 `::...O1_structured_offset`
- 各 PASS / FAIL 与 `headline_arm` / `passed` / `failed_gates` ← 同 JSON `::readings.structure_family.gates`（并用探针同一门公式独立重算复核，见测试 `_recompute_gates`）
- 三问 verdict 串与全部依据 ← 同 JSON `::three_questions.q1_grouped_delta_gates` / `::q2_domain_sign_split` / `::q3_high_permittivity_zone`
- `max_abs_difference = 0.0` / `reproduced_bit_for_bit = true` / `3acd499b...f1754b` ← 同 JSON `::reproduction_check`
- `-1.0256971866778457` 与 `[-2.0646583943890198, 0.02264978539549294]` ← 同 JSON `::readings.structure_family.paired_results`（`O0_onsager` vs `D0_delta_core`，metric `mae`）
- 0.4091179943351143 / 0.4766400383507876 ← `probes/w19_onsager_grouped_prereg.json::frozen_baseline` 与 `::frozen_headline`（W18 冻结坐标）
- `11` ← **W18 冻结记账**（累计主记分牌尝试次数），仓内本 lane 素材不含该字面量；此处引用的是 W18 收口既成事实，不是本探针产出。
**数字自检**：片段内数值 token 已对 `probes/w19_onsager_grouped_summary.json` + `probes/w19_onsager_grouped_prereg.json` + `reports/w19_onsager_grouped.md` 逐字回搜（ISO 日期整段排除、sha256 摘要不作数值 token）。**推算值 / 运行值 / 外部常量**：`28.52`（节号，任务书指定）；`11`（W18 冻结记账，仓内无本 lane 字面出处，已在上一行点名）；其余全部数值 token 在本 lane 素材内逐字命中。
|
