# W36-A 结题报告：主记分牌「端点规则」正式化

- **性质**：后验规则入册 + 端点复算（只读已冻结的逐重复表），**不占 shot**
- **累计 shot**：19

## 1. 规则条款

| 条款 | 内容 | 来源 |
| --- | --- | --- |
| R1 端点定义 | 先对每个种子的全部折取算术均值，再对锁定种子集取算术均值 | 本仓主记分牌惯例（W20 起） |
| R2 锁定种子集 | 42,1234,2026,31337,7 | probes/dielectric_hyperparameter_grid.py::SEEDS（跑前锁定，不得事后增删） |
| R3 每个种子的折数 | 10 | 逐重复表 repeat ∈ {0,...,9}（RepeatedKFold 5×10） |
| R4 稠密 13 列块默认配置 | max_bin=128; colsample_bytree=0.8; reg_lambda=1.0; max_depth=2; n_estimators=200; learning_rate=0.05 | W29 最佳档位 fine_bin128_cs08_l1（+0.017053 对冻结档位） |
| R5 端点判等容差 | 1e-12 | 本轮复算暴露：发布值与 fmean 复算值最多差 2 ulp（见 abs_diff 列） |
| R6 冻结读数表条目策略 | 不新增条目；只登记新配置读数；四个冻结读数原值不变 | README §11 第 4 条 |
| R7 四个冻结读数 | 0.4091179943351143;0.4766400383507876;0.5861142332208197;0.6216672295270079 | 论文附录 A |

## 2. 端点复算符

`endpoint_of(rows, arm)` 先对每个种子的全部折取均值，再对锁定种子集 42,1234,2026,31337,7 取均值；**种子集或折数不一致直接抛 `SeedSetDriftError`**——端点不允许在漂移的网格上宣读。

## 3. 复算结果（六张表 / 全部臂）

| 表 | 臂数 | 已登记发布值 | 容差内复现 | 不适用 | 最大差 |
| --- | --- | --- | --- | --- | --- |
| `w20_epsilon_second_stage_repeats.csv` | 9 | 6 | 6 | 0 | 1.1102230246251565e-16 |
| `w28_dense_hyperparameters_repeats.csv` | 13 | 3 | 3 | 3 | 1.1102230246251565e-16 |
| `w29_dense_binning_repeats.csv` | 6 | 6 | 6 | 0 | 1.1102230246251565e-16 |
| `w30_combination_ladder_repeats.csv` | 6 | 5 | 5 | 0 | 1.1102230246251565e-16 |
| `w31_capacity_exchange_repeats.csv` | 6 | 2 | 2 | 0 | 2.220446049250313e-16 |
| `w32_regularization_ladder_repeats.csv` | 9 | 4 | 4 | 0 | 2.220446049250313e-16 |

**不适用臂**（种子集或折数不满足 R2/R3；已标注、不参与判等）：`probes/artifacts/w28_dense_hyperparameters_repeats.csv::lever4_morgan_frozen`、`probes/artifacts/w28_dense_hyperparameters_repeats.csv::lever4_morgan_retuned`、`probes/artifacts/w28_dense_hyperparameters_repeats.csv::lever4_physical_retuned_shuffled_target`。

**本轮最重要的发现（把规则写下来才会暴露）**：端点对求均值顺序敏感到最后一位——复算值与论文附录 A 的发布值最多差 **2.220446049250313e-16**（1–3 ulp）。因此「端点判等」**不能**写成逐位字符串相等，规则 R5 明确写成 **容差 1e-12**。

## 4. 判据

| 判据 | 内容 | 读数 | 阈值 | 裁决 |
| --- | --- | --- | --- | --- |
| H36a1 | 锁定种子集与折数在六张表、可宣读臂上一致 | 46 | — | 成立 |
| H36a2 | 已发布端点全部在容差内复现 | 26 | 26 | 成立 |
| H36a3 | 复算与发布值的最大差 <= 容差（记录 ulp 量级） | 2.22045e-16 | 1e-12 | 成立 |
| H36a4 | 冻结读数表未新增条目（四个冻结读数原值不变） | — | — | 成立 |
| H36a5 | 不适用臂已标注且无发布值 | 3 | — | 成立 |

## 5. 边界

- 本件只读已冻结的逐重复表，不重跑任何模型；端点复算不产生新读数。
- 端点规则只约束主记分牌（457 行 / 97 化合物池）；不改变任何历史读数。
- R5 的容差 1e-12 是**判等容差**，不是新的显著性门；不得用它放宽任何判据。
- 不占 shot（累计仍 19）、不改 METRIC_NAMES、不动四个冻结读数与 ε 主记分牌。
