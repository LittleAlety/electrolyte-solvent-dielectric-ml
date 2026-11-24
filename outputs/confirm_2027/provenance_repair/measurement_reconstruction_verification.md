# B01 测量级重建独立校验
> 生成器 `verify_measurement_reconstruction/1.0.0` · 2026-11-24T02:22:31Z
> 不复用被测代码，不读生成器结论，从原始观测层独立重算。

## 一、总判定：**PASS**（18/18 通过）

## 二、逐项检查
| # | 检查 | 状态 | 观察值 | 期望值 | 说明 |
|---|---|---|---|---|---|
| 1 | `measurement_id_unique` | ✅ | 2065 | 2065 | 2065 条测量, 2065 个唯一 id |
| 2 | `in_window_count_reproduced` | ✅ | 460 | 460 | 独立重算窗口内观测 (293.15<=T<=303.15, Liquid, 0 Hz) = 460 |
| 3 | `in_aggregate_window_flag_agrees` | ✅ | 460 | 460 | 账本标记 460 条 vs 独立重算 460 条 |
| 4 | `contribution_counts_recompute` | ✅ | 0 | 0 | 0 个聚合行的贡献数与独立重算不符 |
| 5 | `epsilon_median_recompute` | ✅ | 0 | 0 | 0 个聚合行的 ε 中位数与独立重算不符 |
| 6 | `no_synthetic_pair_marked_valid` | ✅ | 0 | 0 | 0 个聚合行被标为 pair_valid=true 但没有任何单次观测同时持有 (T, ε) |
| 7 | `generator_acceptance_criterion_is_not_tautological` | ✅ | 248 | 248 | 判据检查 248/248 行 (独立复核声明诚实=True), criterion_can_fail=True, 判据值=True; 源码(去掉注释/文档字符串后)已无按 invalidity_reason 过滤的判据体. 判据覆盖全表、可失败、且源码无同义反复模式 |
| 8 | `exception_register_covers_all_non_complete` | ✅ | 0 | 0 | 非 COMPLETE 聚合行 148 个, 例外登记覆盖 170 个, 未覆盖 0 个 |
| 9 | `measurement_locator_present` | ✅ | 2065 | 2065 | 定位符文件 2065 行 vs 账本 2065 行 |
| 10 | `measurement_locator_covers_all` | ✅ | 2065 | 2065 | 2065/2065 条测量有定位符 |
| 11 | `measurement_locator_is_not_a_template` | ✅ | 1782 | >100 | 不同定位符 1782 个 (模板会只有 1 个或极少数) |
| 12 | `measurement_locator_names_a_block` | ✅ | 2065 | 2065 | 2065/2065 个定位符含 block= |
| 13 | `headline_n_measurements_2065` | ✅ | 2065 | 2065 | 全量测量 = 2065 |
| 14 | `headline_n_in_window_460` | ✅ | 460 | 460 | 窗口内观测 = 460 |
| 15 | `headline_n_pair_valid_78` | ✅ | 78 | 78 | condition_pair_valid=true 行数 = 78 (PLAN B 报告的 58 是分类计数, 非配对计数) |
| 16 | `headline_n_pair_invalid_170` | ✅ | 170 | 170 | condition_pair_valid=false 行数 = 170 |
| 17 | `pair_validity_partition_complete` | ✅ | 248 | 248 | 78 + 170 = 248 vs 248 行 |
| 18 | `each_measurement_in_at_most_one_aggregate` | ✅ | 2065 | 2065 | 每条测量只出现一次于账本 (无重复计入) |

## 三、PLAN B 报告基线的独立复核
| 项 | 值 | 含义 |
|---|---:|---|
| 全量测量 | 2065 | v11plus 逐行观测 |
| 窗口内观测 | 460 | 293.15–303.15 K, Liquid, 0 Hz |
| 数据库行 | 248 | v04 聚合行 |
| 配对有效 | 78 | (T, ε) 同属一次观测 |
| 配对无效 | 170 | 含 148 缺失证书 + 22 合成条件对 |
| 例外登记 | 170 | 不可恢复 / 部分可恢复 |

2065/460/248/78/170 是**不同统计单位**, 不可串成单调漏斗. PLAN B 报告中的 58 应更正为 78 (配对口径).

## 四、失败的检查（若有）
- 无。全部检查通过。
