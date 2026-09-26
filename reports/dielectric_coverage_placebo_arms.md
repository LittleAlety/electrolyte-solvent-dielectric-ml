# Week 12 · S-5 三臂安慰剂：+0.1241 是观测级信息还是数据量效应？

**探针：** `probes/dielectric_coverage_placebo_arms.py`
**测试：** `tests/test_dielectric_coverage_placebo_arms.py`
**复现命令：** `.\.venv\Scripts\python.exe probes\dielectric_coverage_placebo_arms.py --overwrite`
**降级状态：** 本次运行执行 10 次重复（默认 10），**未降级**
**本文件由探针渲染：** 下面每一个数字都取自同一次运行写出的 `probes/dielectric_coverage_placebo_arms_summary.json`，没有手写数字。

## 一、判读结论（S-5 原文判据）

**数据量效应，+0.1241 不得对外引用**（`decision = data_volume_effect`）

Arm B 剂量曲线不是单调递增。因此 W11 的 +0.1241 只能读作数据量/正则化效应，该数字不得对外引用（Arm C 的均值退化只作机制旁证，不参与这条判据）。

| S-5 判据 | 阈值 / 含义 | 实测 | 结果 |
|---|---|---|---|
| Arm A 标签安慰剂塌缩 | ΔR² ≤ +0.02 | ΔR² = +0.0141 | PASS |
| Arm B 剂量曲线单调递增 | 25→50→75→100%，每一步为正 | 步长 +0.0004、+0.1163、-0.0164 | FAIL |
| Arm C 均值退化低于全量臂 | ΔR²_C < ΔR²_full（机制旁证，不入判据） | ΔR²_C = +0.1021 vs ΔR²_full = +0.1241 | PASS |
| 完整性自检 | 折共享 + W11 钉死值逐位复现 | 见第六节 | PASS |

`verification_passed` = **False**（三项判据 + 完整性自检全过才为 True；headline 按 S-5 的 A 与 B 判据书写）

## 二、三臂实测

打分池钉死为 v11 室温带 **457 行 / 97 化合物**。折由 `masked_splits` 只在打分侧化合物上发放，本探针跑的 11 个协议**打分侧折签名逐位相同 = True**，所以每个臂的分母与被评行都一致。

| 臂 | 协议 | 训练池行 | 训练池化合物 | 每折真实多训练行 | R² | ΔR² | ΔMAE | ΔSpearman | W11 ±0.005 判词 |
|---|---|---|---|---|---|---|---|---|---|
| base | `paired_base` | 457 | 97 | 0.0 | 0.4091 | +0.0000 | +0.0000 | +0.0000 | inert |
| full (+50 compounds) | `paired_plus_coverage` | 584 | 147 | 127.0 | 0.5332 | +0.1241 | -1.5362 | +0.1081 | helps |
| A label placebo | `arm_a_label_placebo` | 584 | 147 | 127.0 | 0.4232 | +0.0141 | -0.2865 | +0.0602 | helps |
| A reference base | `arm_a_reference_base` | 457 | 97 | 0.0 | 0.4091 | +0.0000 | +0.0000 | +0.0000 | inert |
| B dose 25% | `arm_b_dose_25` | 485 | 110 | 28.0 | 0.4330 | +0.0239 | -0.4666 | +0.0458 | helps |
| B dose 50% | `arm_b_dose_50` | 515 | 122 | 58.0 | 0.4334 | +0.0242 | -0.5388 | +0.0684 | helps |
| B dose 75% | `arm_b_dose_75` | 550 | 135 | 93.0 | 0.5497 | +0.1405 | -1.5639 | +0.0941 | helps |
| C mean row | `arm_c_mean_row_only` | 507 | 147 | 50.0 | 0.5112 | +0.1021 | -1.0058 | +0.0705 | helps |
| C nearest real row | `arm_c_nearest_real_row` | 507 | 147 | 50.0 | 0.5088 | +0.0997 | -0.9882 | +0.0684 | helps |

- **W11 钉死值逐位复现：** `paired_base` R² = **0.4091179943351143**（期望 0.4091179943351143）；`paired_plus_coverage` R² = **0.5332044440328436**（期望 0.5332044440328436）；ΔR² = **0.1240864496977293**（期望 0.1240864496977293）；`bit_exact` = **True**
- **有效训练扩张：** 全量臂 **127.0 行/折**（合计 6350，min=max=127），训练池 584 行 / 147 化合物；W11 同项交叉核对 = **True**。
- **上游对账：** 读到的 `probes/dielectric_coverage_paired_benchmark_summary.json` state = read；其固定池链 paired_plus_coverage=+0.1241, paired_plus_new_xtb=+0.1363, paired_plus_v03_block=+0.0211，其 `extra_rows_fitted_per_fold_mean` = 127.0。

## 三、Arm A 标签安慰剂：到底置换了什么

置换只在**新增化合物的 ε 标签之间**做：把某个化合物的标签整块挪到别的化合物上，行数（435 行）、组成、特征向量、T_K 与正则化一字不动，打分侧（v11 零频 457 行）一个标签都没碰。

| 量 | 值 |
|---|---|
| 被打乱的化合物数（自身标签多重集改变） | 50 |
| 收到外来标签的化合物数 | 50 |
| 标签发生变化行数 | 435 |
| 标签变化比例 | 1.0000 |
| 收到外来化合物标签的行数 | 435 |
| 置乱后新增块 ε 多重集不变 | True |
| 新增块之外一个标签都没动 | True |
| 固定种子 | 20260926 |

新增块的 ε 分布（多重集不变，所以均值/方差必然逐位相同）：

| 统计量 | 置换前 | 置换后 |
|---|---|---|
| 行数 | 435 | 435 |
| 均值 | 12.342192 | 12.342192 |
| 方差 | 153.017413 | 153.017413 |
| 最小 / 最大 | 1.873 / 169.76 | 1.873 / 169.76 |
| > 60 的行数 | 1 | 1 |

**安慰剂作用域自检：** 置换只动新增化合物的 ε，而 `paired_base` 既不打分也不拟合这些行，所以「置换目标下的 base」必须与真实标签下的 base 逐位相同。实测 21 个格（3 表示 × 7 指标）的 `max_abs_delta` = **0.0**，`bit_exact` = **True**。
Arm A 的 ΔR² = **+0.0141**：判据要求 ≤ +0.02，实测 PASS。

## 四、Arm B 剂量曲线

子采样在**化合物层**做：先按固定种子 20260927 抽一个化合物顺序，四个档位各取该顺序的前缀，所以各档**互相嵌套**（25% ⊂ 50% ⊂ 75% ⊂ 100%），一个化合物整块进或整块不进。100% 档的训练掩码与全量臂逐位相同 = **True**，故直接复用全量臂的拟合而不重跑。

| 档位 | 纳入化合物 | 训练池行 | 每折多训练行 | R² | ΔR² | 本步增量 |
|---|---|---|---|---|---|---|
| 25% | 13 | 485 | 28.0 | 0.4330 | +0.0239 | - |
| 50% | 25 | 515 | 58.0 | 0.4334 | +0.0242 | +0.0004 |
| 75% | 38 | 550 | 93.0 | 0.5497 | +0.1405 | +0.1163 |
| 100% | 50 | 584 | 127.0 | 0.5332 | +0.1241 | -0.0164 |

- 单调（严格，每步 > 0）= **False**；非递减（浮点容差 1e-12）= **False**；曲线跨度 = +0.1002。
- 判据「剂量曲线单调递增」：**FAIL**。monotone reads 单调递增 strictly (every step positive); non_decreasing is the same curve with a float tolerance and is reported beside it

## 五、Arm C 均值退化：温度分辨率才是载体？

两种读法都跑了，两者都保留 50 个化合物、都只剩 1 行/化合物：(1) **均值行**（合成）= 该化合物自己的 xTB 向量 + 自己的平均 T_K + 自己的平均 ε；(2) **最近真实行**（选择）= 该化合物室温行里 ε 最接近其均值的真实一行。

| 方案 | 协议 | 行/化合物 | 新增行 | 每折多训练行 | R² | ΔR² | 相对全量臂亏损 |
|---|---|---|---|---|---|---|---|
| 全量臂（参照） | `paired_plus_coverage` | 2.54 | 127 | 127.0 | 0.5332 | +0.1241 | - |
| C-1 均值行（合成） | `arm_c_mean_row_only` | 1.00 | 50 | 50.0 | 0.5112 | +0.1021 | -0.0220 |
| C-2 最近真实行 | `arm_c_nearest_real_row` | 1.00 | 50 | 50.0 | 0.5088 | +0.0997 | -0.0244 |

- C-1：保留化合物 **50** 个、只保留 **50** 行（丢掉 77 行），均值行的物理块在化合物内恒定 = **True**。
- C-2：候选 127 行 → 保留 50 行（丢掉 77 行），每化合物恰一行 = **True**。
- 判据「ΔR² 显著低于全量臂」：C-1 PASS、C-2 PASS（两个读法同向才算稳）。

## 六、完整性自检

| 检查 | 结果 |
|---|---|
| frozen_v03_digest_unchanged | PASS |
| merged_v11_block_order_identical | PASS |
| every_protocol_uses_the_grouped_splitter | PASS |
| folds_shared_by_every_arm | PASS |
| scored_pool_is_the_pinned_457_over_97 | PASS |
| added_compounds_are_the_pinned_50 | PASS |
| added_room_rows_are_the_pinned_127 | PASS |
| extra_rows_fitted_per_fold_is_the_pinned_127 | PASS |
| training_expansion_matches_week_11_on_the_shared_names | PASS |
| week_eleven_numbers_reproduced | PASS |
| placebo_moved_only_rows_the_base_cannot_reach | PASS |
| permutation_preserved_the_label_multiset | PASS |
| mean_row_arm_kept_one_row_per_added_compound | PASS |
| mean_rows_are_constant_within_a_compound | PASS |
| ok | PASS |

- 冻结文件 `data/dielectric_v03.csv`：read，实测 sha256 = `ff2142936e06e04b329b70f8597574f75349e54ce876e9fff81309e6d35ccce4`（期望 `ff2142936e06e04b329b70f8597574f75349e54ce876e9fff81309e6d35ccce4`），CRLF = False。
- 输入指纹：cov = `159b928f800a55969963da275ed05c30ce8a19cffc48353a9c490eec68a49af9`，v11 = `7803587afabdec1fcf9cfd319bb64d23f83af8d3fe07124df75052cfcd6a75fc`。

## 七、可复现性

- 固定随机量：折种子 **42**（= W11 的 SEED）x 5 折 x 10 次重复；置换种子 **20260926**；剂量种子 **20260927**。
- 本报告与 summary 不含时间戳，任何随机过程都由上面的种子决定；带 `--overwrite` 重跑两次的产物应当逐字节一致。
- 无降级 显式声明：本次运行与 W11 的重复次数一致，钉死值逐位可比

## 八、红线

- `paper/` 零改动：本探针只写 summary、本报告与三个 CSV。
- `data/dielectric_v03.csv` 未改：digest 保持 `ff2142936e06e04b329b70f8597574f75349e54ce876e9fff81309e6d35ccce4`（实测 = ff2142936e06e04b329b70f8597574f75349e54ce876e9fff81309e6d35ccce4）。
- 未引入新的数据划分：所有臂都跑在 W11 的 `masked_splits` 上，折签名逐位相同。

