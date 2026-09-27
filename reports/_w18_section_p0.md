## 28.42 W18-P0 稠密物理配置重调 XGB 超参：最优臂跨种子均值 0.599820 未过 0.60（差 0.00018），判 partial（2026-09-27）
|
**机制假设**：冻结头（200 树 / `max_depth=2` / lr 0.05）是当年为 **2048 列稀疏 Morgan** 指纹定的；胜出的 `Physical(lever4)` 只有 **13–15 列稠密特征**，深度 2 = 每树 4 叶，**几乎必然欠拟合**。P0 问的是同族最窄的一个问题：同池、同切分、同计分器、同表示，只重调 XGBoost 超参，能否把跨种子端点顶过 0.60。这是 shot 17「换拟合器」被证否（最佳替代族 0.567035 vs 冻结头 0.608059）之后**剩下的同族杠杆**。
**预注册**：`probes/dielectric_hyperparameter_grid_prereg.json`，sha256 `79834b717141dbbace6ae91bd259fa37289f81f7d310feaa8b2470d7743179bc`，`status = locked_before_run`；**非盲**（`non_blind = true`，理由原文：seed 42 的 `0.6080587938801277` 与 shot 17 的读数在写预注册前已知，这是**族内超参网格、不是外部检验**）。搜索空间：全笛卡尔 **288 臂**，注册上限 **24 臂**，实际注册 **7 臂**。判据：confirm = 跨种子均值 > 0.60 **且** 提升 ≥ +0.02；partial = 提升 ≥ +0.005；否则 refuted。
**运行前修订（必须单列·没有任何读数时做的）**：候选块最初登记 **22 臂**；**开跑前实测成本** = 一次冻结头拟合（200 树 / depth 2）在 **2029 × 2061** 稠密矩阵上 **4.16 s CPU**（机器有负载时 8.04 s wall），最深候选（800 树 / depth 6）同一矩阵约 **35 s**；原文指出 XGBoost 直方图构建是 O(rows × features)，**2048 列稠密 ECFP 主导成本，冻结头的任何超参都改不了它**。于是 22 臂 × 50 折 × 5 种子 = **5,500 fits/种子**、单种子集约 **18,500 s CPU**、五种子的集合在算进程开销前就 **> 2.6 小时纯 CPU**。据此把注册臂缩到 **7 臂**（`cost_amendment.rule` 原文：「amended before the first fit; no reading of any arm existed when this was written」，`no_result_existed = true`）：**两条预注册轴都保住**——冻结树数下的 depth 3/4/6、冻结 depth 下的 400/800 树——外加一个 depth × 容量交互点（depth 4 / 400 树）；被砍的是 lr / min_child_weight / subsample / colsample 轴变体与 8 个 800 树格点；**表示、池、切分器、冻结头、五种子、锚点、判据一字未动**。`pre_run_correction` 还记录同一轮更早的一次修订：`arm_params` 首抄把 subsample/colsample 写死 0.8、与臂名冲突，脚本在任何拟合前拒绝启动、按臂名重建、**重钉 digest**。两次修订**都发生在零结果状态**，预注册 sha 因此重钉为上述值。
**锚点先复现**：seed 42 / `xgb_reference` 期望 `0.6080587938801277`、实测 `0.6080587938801277`、`abs_gap = 0`、`reproduced = true`（容差 `1e-09`）⇒ **逐位复现**；折签名必须等于冻结 scoreboard 的签名，不符则拒绝报其它任何数并非零退出。
|
**实测（跨种子均值 = 端点；种子 42 / 1234 / 2026 / 31337 / 7）**：
- `xgb_reference`（冻结头，200/2）：**0.5861142332208197**（sd 0.017461880006798203）｜过 0.60 种子数 **1/5**
- `hp_d3_n200_lr0.05_mcw1_ss0.8_cs0.8`（200/3）：0.5638672862389339（sd 0.03017441957774392）｜0/5
- `hp_d4_n200_lr0.05_mcw1_ss0.8_cs0.8`（200/4，**最优臂**）：**0.5998203128630835**（sd 0.008159756085597283）｜**2/5**
- `hp_d6_n200_lr0.05_mcw1_ss0.8_cs0.8`（200/6）：0.5306397096540456（sd 0.025239974044738225）｜0/5
- `hp_d2_n400_lr0.05_mcw1_ss0.8_cs0.8`（400/2）：0.498277146324478（sd 0.029308014890417542）｜0/5
- `hp_d2_n800_lr0.05_mcw1_ss0.8_cs0.8`（800/2）：0.3463236145907241（sd 0.04741787133989063）｜0/5
- `hp_d4_n400_lr0.05_mcw1_ss0.8_cs0.8`（400/4，capacity_ladder）：0.5767934182517341（sd 0.00900105949233252）｜0/5
- 参考臂 `0.5861142332208197` 与该表示家族的**冻结跨种子端点逐位一致**——这是对 0.5861 这个端点的**又一次独立复现**。
- 最优臂对参考的提升 **+0.01370607964226378**；判据 `target_met_cross_seed = false`（**0.599820 对 0.60 差 0.00018，未过门**）、`improvement_met = false`（提升门 +0.02）。
|
**机制发现（单列）**：`hp_d4_n200` 不仅唯一稳定超过参考，而且**种子方差几乎减半**（`r2_seed_sd` **0.008159756085597283** vs 参考 **0.017461880006798203**），**五个种子的均值全部落在 0.590–0.609**（0.6079114372577955 / 0.5976706539764927 / 0.5949201897635696 / 0.5900344987346258 / 0.6085647845829333；最差一枪 0.5900344987346258 仍高于参考的跨种子均值），`seeds_above_060` = **2/5**（参考只有 **1/5**，那 1 个就是 seed 42 ⇒ 参考「过 0.60」是单种子运气、不是端点性质）。即「**冻结 depth 2 在 13–15 列稠密块上欠拟合**」**方向被证实、幅度不足以过门**；反向同样成立：容量加到 depth 6（0.5306397096540456）或只加树数到 800（0.3463236145907241）都**急剧反噬**——欠的是「每树多切几刀」，不是「多堆树」。
|
**泄漏审计**：`clean = true`；`folds_by_seed` 五种子**各 350**（= 50 折 × 7 臂），逐种子 `folds_with_a_straddling_compound = 0`、`max_straddling_compounds_in_a_fold = 0`。
**placebo**：预注册在 `decision_rule` 里声明了 `placebo` 词条（`--placebo` 会在计分行上置换 target 后才拟合）；**主跑的 `placebo` 字段为 `false`**，安慰剂是**另一条独立运行、独立产物**，本节**不声称**任何安慰剂结果。
**测试门禁随修订同步的留证**：`tests/test_hyperparameter_grid.py` 里旧文本门 `text.count("hp_d") >= 21`（=「脚本必须声明 22 臂」）是**修订前写的、与注册集冲突**；本次改为「**6 个非参考注册臂 + 脚本必须写明 `PRE_RUN_AMENDMENT` 修订记录 + 禁用旧 22 臂措辞**」（现为 `assert text.count("hp_d") >= 6`、`assert "PRE_RUN_AMENDMENT" in text`、`assert "5,500 fits per seed" in text`、`assert "the registered arm set is the 7-arm subset" in text`、`assert "no result existed" in text`、`assert "pre-registers a 22-arm grid" not in text`）——这是**门禁跟随注册集**，不是放宽门禁。
⇒ **但脚本侧留证本次核对时尚未落盘（未核）**：`probes/dielectric_hyperparameter_grid.py`（本次核对字节，mtime 2026-09-27T23:42:19）全文 **0 命中** `PRE_RUN_AMENDMENT` / `5,500 fits per seed` / `the registered arm set is the 7-arm subset` / `no result existed`，且 docstring 仍写「pre-registers a 22-arm grid」（被禁用的串仍在）⇒ 该测试项按当前字节应为**红**，需在收口时把修订记录写进脚本（**本节不据此改任何数**）。
|
**verdict = `partial`**（过了 kill bar 0.005，未过提升门 0.02；目标 0.60 **未达成**）。
- **不提升**：`promotion.promoted = false`，冻结头条 **0.4766400383507876** 与冻结基线 **0.4091179943351143** 原位未动；原因原文：本轮是冻结协议上的**诊断性超参网格**，冻结头条是 co-primary 混合臂，而本网格**对 seed 42 非盲**、端点是 **7 臂多重比较**。**本 lane 零次主记分牌尝试**（W18 累计仍 **11 次**，与 §28.41 结转一致）。
- 产物：`probes/dielectric_hyperparameter_grid.py`、`probes/dielectric_hyperparameter_grid_prereg.json`、`probes/dielectric_hyperparameter_grid_summary.json`、`probes/artifacts/dielectric_hyperparameter_grid_repeats.csv`（350 行 = 5 种子 × 7 臂 × 10 重复）、`reports/dielectric_hyperparameter_grid.md`、`tests/test_hyperparameter_grid.py`。
|
**数字出处**（`值 ← 文件::JSON键`）
- 预注册 sha256 / status / arm_count ← `probes/dielectric_hyperparameter_grid_summary.json::prereg.sha256` ｜ `::prereg.status` ｜ `::prereg.arm_count`
- non_blind / full_cartesian_size / max_arms_cap / arms / seeds / decision_rule ← `probes/dielectric_hyperparameter_grid_prereg.json::non_blind` ｜ `::grid.full_cartesian_size` ｜ `::grid.max_arms_cap` ｜ `::arms` ｜ `::seeds` ｜ `::decision_rule`
- 4.16 s CPU（8.04 s wall） / 约 35 s / O(rows x features) ← `prereg.json::cost_amendment.measurement[0..2]`
- 5,500 fits/种子、约 18,500 s CPU/种子、> 2.6 h、22→7 臂、保住两轴 / amended before the first fit ... / no_result_existed ← `prereg.json::cost_amendment.registered_cost` ｜ `::cost_amendment.rule` ｜ `::cost_amendment.amended_arm_count` ｜ `::cost_amendment.preserved` ｜ `::cost_amendment.dropped` ｜ `::cost_amendment.no_result_existed`
- 两次运行前修订与重钉 digest ← `prereg.json::pre_run_correction`
- 锚点 0.6080587938801277 / abs_gap = 0 / reproduced = true / 容差 1e-09 ← `probes/dielectric_hyperparameter_grid_summary.json::anchors.rows[0].measured` ｜ `::anchors.rows[0].abs_gap` ｜ `::anchors.reproduced` ｜ `::anchors.tolerance`
- 参考臂跨种子均值 0.5861142332208197 ← `summary.json::answers.reference_cross_seed_mean`；其 sd 0.017461880006798203 ← `::cross_seed[0].r2_seed_sd`
- 七臂跨种子均值与过 0.60 种子数 ← `summary.json::cross_seed[i].r2_seed_mean` ｜ `::cross_seed[i].seeds_above_060`（i = 0…6，次序同 `::contract.arms`：reference / d3n200 / d4n200 / d6n200 / d2n400 / d2n800 / d4n400）
- d4_n200 的 sd 0.008159756085597283 / 五种子均值 0.6079114372577955, 0.5976706539764927, 0.5949201897635696, 0.5900344987346258, 0.6085647845829333 ← `summary.json::cross_seed[2].r2_seed_sd` ｜ `::cross_seed[2].seed_means`
- 最优臂 0.5998203128630835 / 提升 +0.01370607964226378 / target_met_cross_seed = false / improvement_met = false / 门 0.6 与 0.02 与 0.005 ← `summary.json::answers.best_cross_seed_mean` ｜ `::answers.best_improvement_vs_reference` ｜ `::answers.target_met_cross_seed` ｜ `::answers.improvement_met` ｜ `::answers.target_r2` ｜ `::answers.improvement_bar_r2` ｜ `::answers.kill_bar_r2`
- verdict = partial ← `summary.json::verdict`；泄漏 clean = true 与五种子各 350 ← `::leakage.clean` ｜ `::leakage.folds_by_seed`；placebo = false ← `::placebo`
- promoted = false / 冻结头条 0.4766400383507876 / 冻结基线 0.4091179943351143 / 不提升理由 ← `summary.json::promotion.promoted` ｜ `::promotion.frozen_headline` ｜ `::promotion.frozen_baseline` ｜ `::promotion.reason`
- 2029 训练行 / 457 计分行 / 2635.1006592000003 s / jobs 6 ← `summary.json::pool.base_rows` ｜ `::pool.scored_rows` ｜ `::wall_seconds` ｜ `::jobs`
- 350 行（含表头 351）与列 schema ← `probes/artifacts/dielectric_hyperparameter_grid_repeats.csv`
- 累计 11 次主记分牌尝试 ← `reports/decisions_log.md::§28.41`（原文「W18 零次主记分牌尝试，累计 11 次不变」）
- 门禁断言全文（hp_d >= 6 / PRE_RUN_AMENDMENT / 禁用串 not in text） ← `tests/test_hyperparameter_grid.py::test_the_script_states_the_frozen_head_and_the_ladder`
- 「脚本 0 命中 `PRE_RUN_AMENDMENT`、docstring 仍含 pre-registers a 22-arm grid」 ← `probes/dielectric_hyperparameter_grid.py`（本次只读核对，非 JSON 键）
|
