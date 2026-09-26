# 介电通道 v2：预声明、全配置上报的模型族比较

> **v1 冻结口径的读数已如实记录为未过；v2 是新配置，其出现顺序与选型规则均先声明后执行，全部配置无一遗漏上报**

- 生成时间（UTC）：`2026-09-25T22:20:02Z`
- 本文件由 `probes/dielectric_channel_v2.py` 确定性生成，数字与 `probes/dielectric_channel_v2_summary.json` 同源。
- **不是 L3 结论**：只跑介电通道；C2_additive、C3 与其余三通道均未运行，不得把本产物写成「L3 通过」。

## 一、口径与预注册常数

- 预注册：`probes/l3_backvalidation_prereg.json`，status=`LOCKED`，locked_at_utc=`2026-09-25T19:38:49Z`
- 预注册 sha256（规范化行尾）：`77f61a83b82de346292ff055c4f4c52003bccb6bfc98bf11813048abc6f0db98`
- C1 的 K = 20（池内按预测 eps 降序，取前 K）
- C2_solvent 的 max|Δlog10 ε| = 0.1，真值 EC 90.5 / PC 64.9
- pass_expression（原样读取）：`C1 and C2_solvent and C2_additive and C3`
- 池：`probes/l3_stage1_pilot_pool.csv`，sha256=`b838febbca4d65975d1820ae9275215288968979b78756611cb031eb7c408b18`，236 行，行尾 LF（与预注册钉死值一致）

## 二、池、折几何与冠军剔除

- 折几何：RepeatedKFold(n_splits=5, n_repeats=10, random_state=42)；seed 方案：42 + global RepeatedKFold split index；共 50 折
- 折聚合口径：mean_over_the_10_out_of_fold_repeat_predictions
- EC / PC 训练侧剔除次数：EC 40、PC 40（共 50 折）；样本外评分次数：EC 10、PC 10
- 每折断言 champions ∩ train_ids == ∅（产物列 `champions_intersect_train_after_exclusion` 全为 0）；剔除后训练行数 186–189

## 三、预声明与全配置上报表

**SELECTION_RULE（先声明后执行）**：在同时满足 (a) 相对冻结 v1 口径的 OOF 原始 eps MAE 不劣化、(b) C1 命中数严格更大的家族中，取 C2 的 max|dlog10 eps| 最小者；并列取特征更少者，再并列按家族 id 字典序升序。无满足者即报未过。

规则机读定义：`eligibility` = ['family.oof_raw_mae <= baseline.oof_raw_mae', 'family.c1_hits > baseline.c1_hits']；`pick` = minimum family.c2_max_abs_delta_log10 among eligible families；`tie_break` = ['fewer declared_feature_count', 'family id ascending']
- 声明口径说明（自述项，无外部时间戳锚）：`declared_before_execution = true` 是运行产物 `probes/dielectric_channel_v2_summary.json` 的自述标志，本报告不把它当作时间凭证。可核对的时间锚只有两个：预注册 `locked_at_utc = 2026-09-25T19:38:49Z` 与 `fold_and_seed.amendment_3.amended_at_utc = 2026-09-25T22:05:00Z`，两者都早于本报告 `generated_at_utc = 2026-09-25T22:20:02Z`；即「规则与修订先落预注册、报告后生成」这一点可由时间戳核对，而 `declared_before_execution` 布尔值本身不自证。

| 家族 | 组 | 特征数 | OOF raw MAE | R² | C1 命中/2 | EC 名次 | PC 名次 | EC Δlog10 | PC Δlog10 | max|Δlog10| | 过 C2? |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `frozen_v1_log_eps_xgb`（基线） | a | 2061 | 6.2548 | 0.2862 | 0 | 24 | 58 | -0.5939 | -0.5807 | 0.5939 | 否 |
| `linear_raw_mu` | b | 1 | 10.5778 | 0.0677 | 2 | 7 | 8 | -0.5021 | -0.3904 | 0.5021 | 否 |
| `onsager_mu` | c | 1 | 71186452.0745 | -545388278390105.5625 | 2 | 7 | 9 | 6.5205 | -0.2617 | 6.5205 | 否 |
| `ridge_raw_multivar` | d | 6 | 10.1875 | 0.1525 | 2 | 2 | 9 | -0.2723 | -0.3526 | 0.3526 | 否 |
| `ridge_onsager_multivar` | d | 6 | 76271200.2670 | -522225088919541.3125 | 1 | 16 | 53 | -0.6432 | -0.7518 | 0.7518 | 否 |
| `delta_onsager_xgb` | e | 2062 | 48305096.9615 | -307438958490593.2500 | 2 | 3 | 9 | 7.4236 | 0.6713 | 7.4236 | 否 |
| `delta_ridge_onsager_xgb` | e | 2067 | 63559336.0318 | -391668828798776.8750 | 1 | 17 | 64 | -0.3014 | -0.6106 | 0.6106 | 否 |
| `dummy_mean` | control | 0 | 11.5537 | -0.0106 | 0 | 159 | 27 | -0.7869 | -0.6322 | 0.7869 | 否 |

- 共 8 个家族全部上报（无遗漏）；基线 `frozen_v1_log_eps_xgb` 的 OOF raw MAE = 6.2548、C1 命中 = 0/2。

补充诊断（非判据）：Onsager 尺度上的线性拟合可能越过极点，表现为个别折的预测爆到 1e3 以上；下表列出每个家族的最大预测与极点裁剪计数。

| 家族 | 最大预测 ε | 预测 > 1e3 的行·折数 | Onsager 极点裁剪次数 |
| --- | ---: | ---: | ---: |
| `frozen_v1_log_eps_xgb` | 58.9809 | 0 | 0 |
| `linear_raw_mu` | 78.6337 | 0 | 0 |
| `onsager_mu` | 3000000082.8458 | 56 | 56 |
| `ridge_raw_multivar` | 61.3044 | 0 | 0 |
| `ridge_onsager_multivar` | 3000000082.8458 | 63 | 60 |
| `delta_onsager_xgb` | 3000000082.8458 | 41 | 38 |
| `delta_ridge_onsager_xgb` | 3000000082.8458 | 53 | 50 |
| `dummy_mean` | 15.9967 | 0 | 0 |

## 四、SELECTION_RULE 与胜者

- 满足资格条件的家族：（无）
- 胜者：**无**（按先声明规则无家族同时满足 MAE 不劣化与 C1 严格改善），本次如实记未过。

## 五、外推失败机制诊断（仅诊断，不作结论式断言）

- 命题：a depth-2 boosted-tree ensemble is a step function of the training labels, so every held-out prediction stays at or below the largest training dielectric in that fold; it cannot reach a champion above the training ceiling
- 下表按家族 `frozen_v1_log_eps_xgb`（冻结 v1 口径）逐折记录训练集最大 ε 与该折对冠军的预测；逐折明细见 `probes/artifacts/dielectric_channel_v2_extrapolation.csv`。

| 冠军 | 折记录数 | 最大预测 ε | 该冠军出现过的训练集 ε 上界最大值 | 冻结真值 | 预测 ≤ 训练上界？ |
| --- | ---: | ---: | ---: | ---: | --- |
| EC | 10 | 25.4981 | 178.4700 | 90.5000 | 全部为是 |
| PC | 10 | 19.9197 | 178.4700 | 64.9000 | 全部为是 |

- 全部 20 条**冠军折**记录中，预测 − 训练上界 的最大值 = -63.8027（≤0 即被封顶）；这 20 条冠军折的训练集 ε 上界范围 **85.6000–178.4700**（逐折明细见 `probes/artifacts/dielectric_channel_v2_extrapolation.csv`）。
- 若按**全场 50 折**（含非冠军折）统计，训练集 ε 上界范围才是 78.8700–178.4700（`fold_train_max_epsilon`: min 78.87 / max 178.47 / rows 50，见 `probes/dielectric_channel_v2_summary.json`）。两处口径不同，不得混用。
- 观察（非结论）：树集成是训练标签的阶梯函数，其取值被该折训练集的最大 ε 封顶；当冠军真值高于全部折的训练上界时，任何树集成都无法在原始 ε 尺度上够到它。这与「换成可外推的物理形式化线性模型能否救回」是两回事，后者由第三、六节的数据判定。

## 六、分层 MAE 对照

| 家族 | ε ≤ 20 (n) | MAE | 20 < ε ≤ 60 (n) | MAE | ε > 60 (n) | MAE |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `frozen_v1_log_eps_xgb` | 182 | 2.4626 | 47 | 10.9136 | 7 | 73.5729 |
| `linear_raw_mu` | 182 | 6.8580 | 47 | 15.1084 | 7 | 76.8739 |
| `onsager_mu` | 182 | 67582423.0327 | 47 | 89361727.9442 | 7 | 42857212.0349 |
| `ridge_raw_multivar` | 182 | 7.2717 | 47 | 12.5055 | 7 | 70.4347 |
| `ridge_onsager_multivar` | 182 | 85714292.4136 | 47 | 51063860.6195 | 7 | 84.9437 |
| `delta_onsager_xgb` | 182 | 19780226.3845 | 47 | 114893638.9950 | 7 | 342857235.4540 |
| `delta_ridge_onsager_xgb` | 182 | 37912094.2122 | 47 | 127659608.5770 | 7 | 300000079.1080 |
| `dummy_mean` | 182 | 7.4327 | 47 | 17.2510 | 7 | 80.4459 |

- 池内目标分层计数：ε ≤ 20 共 182 行、20–60 共 47 行、> 60 共 7 行。

### 主口径之外的稳健性核对（非判据，事后附加并在此披露）

- 说明：the declared gating readout aggregates the 10 repeat predictions by their mean; a linear fit on the Onsager scale can cross the pole in a single fold and dominate that mean. This secondary readout is reported so the conclusion does not rest on the aggregation choice. It does NOT feed SELECTION_RULE or the winner.

| 家族 | 中位数聚合 EC \|Δlog10\| | PC \|Δlog10\| | max\|Δlog10\| | 过 C2? |
| --- | ---: | ---: | ---: | --- |
| `frozen_v1_log_eps_xgb` | 0.6015 | 0.5845 | 0.6015 | 否 |
| `linear_raw_mu` | 0.5067 | 0.3953 | 0.5067 | 否 |
| `onsager_mu` | 0.1910 | 0.3421 | 0.3421 | 否 |
| `ridge_raw_multivar` | 0.2698 | 0.3719 | 0.3719 | 否 |
| `ridge_onsager_multivar` | 0.7015 | 0.7611 | 0.7611 | 否 |
| `delta_onsager_xgb` | 7.5205 | 0.5015 | 7.5205 | 否 |
| `delta_ridge_onsager_xgb` | 0.4558 | 0.6230 | 0.6230 | 否 |
| `dummy_mean` | 0.7922 | 0.6284 | 0.7922 | 否 |

- 中位数聚合下过 C2 的家族：（无）

## 七、诚实结论

- 过 C1 的家族：['linear_raw_mu', 'onsager_mu', 'ridge_raw_multivar', 'delta_onsager_xgb']
- 过 C2_solvent 的家族：（无）
- 同时过 C1 与 C2 的家族：（无）
- 相对 v1 基线同时改善 C1 与 C2 的家族：['linear_raw_mu', 'ridge_raw_multivar']
- **诊断项（非判据）**：可及下限（按 C2 的 max|Δlog10| 最小者，10 次重复均值聚合口径）：`ridge_raw_multivar`，max|Δ| = 0.3526（EC 0.2723、PC 0.3526），相对门 0.10 差 0.2526；同族 C1 命中 2/2（EC 名次 2、PC 名次 9）。本行与下一行都是诊断读数，不参与 SELECTION_RULE 与胜者判定。
- 基线对照：v1 的 OOF raw MAE = 6.2548、max|Δlog10| = 0.5939；可及下限族的 OOF raw MAE = 10.1875。
- **诊断项（非判据）** 瓶颈证据（特征侧）：EC and PC are NOT the largest mu_sq_over_Vm rows of this pool: six ionic-liquid salts out-rank them (rank 7 and 8). So the Onsager-style linear extrapolation is anchored by a feature whose maximum belongs to other molecules, and the two champions sit on the rising flank rather than at the top edge. 冠军的 mu_sq_over_Vm 名次为 {'EC': 7, 'PC': 8}（诊断读数，不参与 SELECTION_RULE 与胜者判定）；池内 mu 前 6 名是 1-ethyl-3-methylimidazolium butylsulfonate(mu=1542904, ε=30)、1-butyl-3-methylimidazolium tetrafluoroborate(mu=1442436, ε=13.9)、1-butyl-1-methylpyrrolidinium dicyanamide(mu=1170461, ε=18)、1-ethyl-3-methylimidazolium diethyl phosphate(mu=970930, ε=16.9)、3-butyl-1,2,4,5-tetramethyl-1H-imidazol-3-ium tetrafluoroborate(mu=912439, ε=12)、1-(2-hydroxyethyl)-3-methylimidazolium tetrafluoroborate(mu=832802, ε=23.3)。
- 瓶颈证据（数据侧）：高 ε 分层行数很少（见第六节计数），且冠军真实 ε 高于逐折训练上界；单调物理特征在留出外推上把冠军推向预测上界附近，但样本量与特征-目标关系共同限制了可及精度。本节只给出证据，不对「特征还是数据」作单方面结论。

- 稳健性核对（非判据）：中位数聚合下过 C2 的家族仍为 （无）；中位数聚合下 C2 最好的是 `onsager_mu`。
- Onsager 逆变换家族的巨大 MAE / R² 是极点越界的直接后果（见第三节补充诊断的裁剪计数），不是数值噪声；这说明「换成物理形式化的线性模型」并不自动安全。

## 八、产物与验证命令

- `probes/dielectric_channel_v2.py`（CLI）
- `probes/dielectric_channel_v2_summary.json`（全配置上报）
- `probes/artifacts/dielectric_channel_v2_folds.csv`（50 折记录 + 每折剔除数）
- `probes/artifacts/dielectric_channel_v2_predictions.csv`（逐家族逐折逐行）
- `probes/artifacts/dielectric_channel_v2_strata.csv`（分层诊断）
- `probes/artifacts/dielectric_channel_v2_extrapolation.csv`（训练上界 vs 预测）
- 复现：`.venv\Scripts\python.exe probes\dielectric_channel_v2.py`
- 守卫：`.venv\Scripts\python.exe -m pytest tests\test_dielectric_channel_v2.py -q`
- 静态检查：`.venv\Scripts\python.exe -m ruff check scripts src probes tests notebooks`

## 九、未决风险

- 冠军仅在池内按同一代码路径评分，且池被限制在名册内（236 行）；这不等于「对任意新分子可外推」。
- 该池的 mu_sq_over_Vm 前 6 名是离子液体盐类而非冠军，线性模型在高 μ 端的锚点由这些盐决定；换池（例如剔除多片段盐）可能改变结论，本产物不作此声明。
- 只跑介电通道：C2_additive、C3 与其余三通道尚未运行，任何「L3 通过」表述都无效。
- Δ-learning 家族的残差学习器沿用冻结 XGB 超参；未做超参搜索，故本产物是「配置比较」，不是「调参后的最优」。
- 本次没有任何家族同时过 C1 与 C2：按预注册纪律，只能如实记未过，不得宣称通过。
