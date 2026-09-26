# W17-6 杠杆 4 与杠杆 8 同时入模 —— 冻结主记分牌合并臂

- 生成时间: `2026-09-26T13:08:39Z`
- 预注册 (v3): `probes/dielectric_coordination_block_prereg_v3.json` (sha256 `4d02a99b4677334123cd29597a16d531343adf34d2224799d0ca54e3b373399b`, 锁定 2026-09-26T12:44:25Z)
- 判决: **pass_merged_blocks** —— 过门

- lever 4 and lever 8 together moved grouped Morgan+Physical R2 by +0.0675 against the re-run baseline and the reused amended placebo clause collapsed; the merge arm beat the baseline in 9 of 10 repeats. The v1 decision remains `dead`, the v2 decision remains `pass_under_amended_placebo_clause`, and this is a third, separately counted shot.

## 与 v1 / v2 并列阅读，绝不覆盖

- v1 (`probes/dielectric_coordination_block_summary.json`) 记录 **dead**，且仍然记录 **dead**；其预注册与全部产物逐字节未动。
- v2 (`probes/dielectric_coordination_block_v2_summary.json`) 记录 **pass_under_amended_placebo_clause**，且仍然逐字如此（delta R2 +0.0441）。
- 本轮合并是单独计数的第三次 shot：它既不推翻 v1 的 `dead`，也不等同于 v2 的 `pass_under_amended_placebo_clause`。
- 两块从未合并复测（戒律 AB-3）；本轮是第一次合并，且**不把单臂 delta 相加外推**。

## 记分牌

- 计分行 457，化合物 97，折数 50，repeats 10
- 跨折化合物: 0
- 打乱标签向量: seed 42，sha256 `fe2a1ba082fcee62809dbfd90d532c2b3b1607003a29f5bc4e7d748e8dc4e75b` —— 沿用 v1/v2，不重抽
- 本 shot 执行的 xTB: **否**（两块都逐字节复用冻结产物，成本为 0）

## 两块

- 杠杆 4（构象平均偶极）: 迁移 2027 行 / 146 化合物，计分池覆盖 95/97；列 ['dipole_D', 'mu_sq_over_Vm']
- 杠杆 8（Li⁺ 配位块）: 88 化合物可用块，五列 ['li_binding_energy_ev', 'li_binding_distance_a', 'q_max_h', 'q_min_hetero', 'esp_imbalance']，逐字节读自 v1 特征产物

## 各臂读数

| 臂 | 角色 | R2 | MAE | Spearman | MAE>60 |
| --- | --- | --- | --- | --- | --- |
| `baseline` | 参考臂（真标签，冻结 v03 physical + Morgan，本脚本内重跑） | 0.4091 | 8.0407 | 0.7763 | 55.7131 |
| `plus_lever4` | 杠杆 4 单臂（v0.4 构象平均偶极，真标签） | 0.4650 | 7.2733 | 0.8274 | 55.1153 |
| `plus_lever8` | 杠杆 8 单臂（五列配位块，真标签） | 0.4532 | 7.9176 | 0.7869 | 51.0224 |
| `plus_both` | 本轮 shot（杠杆 4 与杠杆 8 同时入模，真标签） | 0.4766 | 7.4344 | 0.8249 | 49.4432 |
| `placebo_shuffled_target` | placebo（合并后管线，标签打乱） | -0.0304 | 13.5770 | 0.0001 | 68.1460 |
| `baseline_features_shuffled_target` | 对照（冻结特征集，同一打乱标签） | -0.0304 | 13.5725 | -0.0052 | 67.9139 |
| `lever4_features_shuffled_target` | 对照（杠杆 4 管线，同一打乱标签） | -0.0200 | 13.5357 | 0.0123 | 67.6508 |
| `no_information_floor` | 无信息下限（训练折均值，同一打乱标签） | -0.0044 | 13.3887 | -0.0692 | 68.4284 |
| `no_information_floor_real_labels` | 无信息下限（真标签，语境） | -0.0687 | 14.0197 | -0.3535 | 68.7348 |

## 合并读数（`plus_both` 对基线与各单臂）

- 合并臂 delta R2 对基线: +0.067522
- 单臂 delta: `plus_lever4` +0.055838, `plus_lever8` +0.044059
- 最佳单臂: `plus_lever4` (+0.055838)；合并臂相对最佳单臂 +0.011684
- 合并臂相对 `plus_lever4` 的增量 +0.011684；相对 `plus_lever8` 的增量 +0.023463
- **禁止外推**: 单臂 +0.0558384525472409 (杠杆 4) 与 +0.044058816215696295 (杠杆 8) 相加 = +0.099897，这个数**不是读数**，只登记以便拒绝；实测合并 delta 与该和的差 -0.032375

## 复用的修订 placebo 条款（三读需同时成立）

- 规则 1，下限上界: placebo -0.0304 减下限 -0.0044 = -0.0260 -> 成立: True
- 规则 2，同一合并管线真标签臂: placebo 减 `plus_both` = -0.5070 -> 成立: True
- 规则 3，同管线打乱对照: placebo 减同一打乱标签下的冻结特征集 = +0.0000 -> 成立: True
- 每条规则容差: 0.02；**塌缩: True**
- 下限定义: the training-fold-mean predictor scored on the identical folds and the identical permuted label vector as the shuffled-label arm
- 另一读数（仅报告，非门）: placebo 低于真标签基线 -0.4395

## 配对 delta (`plus_both` - `baseline`)

| 指标 | delta |
| --- | --- |
| r2 | +0.0675 |
| mae | -0.6063 |
| rmse | -0.8095 |
| spearman | +0.0486 |
| mae_lt20 | -0.9779 |
| mae_20_60 | +0.4684 |
| mae_gt60 | -6.2699 |

## 复现检查

- `baseline`: 0.4091179943351143 vs 已发布 0.4091179943351143（绝对差 0.00e+00，容差 1e-09）
- `plus_lever4` vs 迁移发布值: 0.4649564468823552 vs 0.4649564468823552（绝对差 0.00e+00）
- `plus_lever8` vs v2 发布值: 0.4531768105508106 vs 0.4531768105508106（绝对差 0.00e+00）

## 运行遥测

- 墙钟 620.4 s，jobs 6，Python 3.12.14，平台 win32
- 各臂耗时 (s): baseline 89.6, plus_lever4 91.0, plus_lever8 87.9, plus_both 88.2, placebo_shuffled_target 89.7, baseline_features_shuffled_target 87.8, lever4_features_shuffled_target 84.8, no_information_floor 0.3, no_information_floor_real_labels 0.2

## shots 记账

- 本轮 shot: 1
- 杠杆 4 此前 shot: 1
- 杠杆 8 此前 shot: 2
- 本轮之后杠杆 4 + 杠杆 8 项目累计 shot: 4
- 规则: every scored attempt at the main scoreboard is counted, including failed ones
- this probe may not edit decisions_log.md, so the count is carried here for the integrator to register

## 诚实边界

- v1 的 `dead` 仍然有效，v2 的 `pass_under_amended_placebo_clause` 仍然逐字有效；本轮合并既不推翻 v1，也不等同于 v2，是单独计数的第三次 shot。
- 本次两块都逐字节读自冻结产物（v1 配位块特征、v0.4 构象偶极），因此本 shot 不跑 xTB，特征侧按构造冻结，不引入新化学。
- 两块触及同一物理轴（极性 / Li⁺ 配位），单臂 delta 极可能重叠；禁止把杠杆 4 的 +0.0558 与杠杆 8 的 +0.0441 相加外推，合并 delta 只认本轮实测。
- 合并臂相对最佳单臂的增量仅旁列报告、不入门：冻结判据只认对基线的 delta R2 与复用的修订 placebo 条款。
- 杠杆 4 只覆盖计分池 95/97 化合物，缺 2 个（无 xTB 特征块的离子液体）；冻结模型原生处理缺失值。
- 杠杆 8 有 9 个化合物无 O 也无 N，按预注册的位点规则把块留空为 NaN，而不是填值。
- GFN2-xTB 对 Li⁺ 过度成键；只使用结合能在化合物间的分布，绝不把其绝对值当作热化学。
- Li⁺ 络合物为气相单分子：无阴离子、无溶剂-溶剂竞争——正是综述自己指出的结合能描述符弱点。
- mae_gt60、MAE、RMSE、Spearman 以及合并-单臂增量仅旁列报告，不构成 v3 判据。
- placebo 臂低于真标签基线 -0.4395；这是打乱标签的预期符号，仅作完整性报告——把该距离当真门的 v1 条款在本轮被沿用其修订形式，而非删除。

## 文件

- folds: `probes/artifacts/dielectric_coordination_block_v3_folds.csv`
- predictions: `probes/artifacts/dielectric_coordination_block_v3_predictions.csv`
- repeats: `probes/artifacts/dielectric_coordination_block_v3_repeats.csv`
- report: `reports/dielectric_coordination_block_v3.md`
- summary: `probes/dielectric_coordination_block_v3_summary.json`

