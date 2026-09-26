# NBS 514 alpha 温度系数：交叉校验与先验特征

本报告由 `probes/dielectric_alpha_prior_probe.py` 直接生成，所有数字来自实测；读不到的地方写 `n/a` 并注明原因。
对应执行手册数据源表第 2 项：调和列（week 8 已交付）之外的"系数本身作为先验特征"这一步。

## 0. 判决前置

- **alpha 不进 v1.x 特征块。** v1.x 室温带化合物池里有系数的化合物占 **0.0%**，该 arm 加进去的每一格都是缺失值。它与同宽安慰块的配对比 ΔR² = 0.0000（inert）。
- **它对温度维度无用，它是个覆盖率资产。** alpha 表与 v11 观测表的化合物集合几乎不相交；唯一覆盖率说得过去的地方是 v1.0 的 246 化合物池（18.6%）。
- **化合物自身的经验斜率不可部署。** 诚实版本（只用训练折拟合）在被打分行上的覆盖率是 **0.0%**，相对同宽安慰块的 ΔR² = -0.0641（hurts）。也就是说：在分组 CV 下，一个被打分化合物的温度敏感度本质上不可观测。
- **加列不是无操作。** 冻结超参里 `colsample_bytree = 0.8` 按列下标抽样，塞进两列全 NaN 也会改变预测（实测最大偏差 5.932785 ε 单位，`predictions_identical = False`）。因此本探针每个特征臂都配了一个同宽全 NaN 安慰块，"该不该进管线"的判据一律取**相对安慰块**的效应，而不是相对基线。
- 室温带基线逐位复现：**True**（R² = `0.40911799433511431`，钉住常数 = `0.40911799433511431`）。

## 1. alpha 的定义与单位换算

定义取自 `probes/nbs514_alpha_harmonization_probe.py`（它转录的是 NBS Circular 514 第 2.1 / 2.5 节），不是本探针的重新猜测：

```
kind "a"      a     = -d(eps)/dT          printed as  a     * 1e5
kind "alpha"  alpha = -d(log10 eps)/dT    printed as  alpha * 1e5
```

反解（两者都按开尔文）：

```
kind "a"      d(eps)/dT = -a_1e5     * 1e-5
kind "alpha"  d(eps)/dT = -alpha_1e5 * 1e-5 * eps * ln(10)
```

两点必须写清楚：

1. 转录列**一律叫 `alpha_1e5`**，即使 `alpha_kind == "a"` 时它装的是 `a` 而不是 `alpha`。它是被换算过的系数，不是导数；任何与经验 dε/dT 的比较都必须过 kind 分支，因为两支之间差一个 `eps * ln(10)`（水差 5 倍，乙腈差 86 倍）。
2. `alpha` 支是**相对量**（每单位 eps），换算成导数需要一个 eps。本探针**没有**把 `implied_dielectric_slope` 当特征：v1.0 池里 44 条带系数的行中有 **43 条**的标签与那张表登记的 eps 逐位相同，该列会是标签的函数。因此特征块只用与 eps 无关的两列。

换算自检：本探针独立重推的换算与冻结列 `implied_dielectric_slope` 在 **74** 行上比较，`bit_exact = False`，max_abs_delta = 4.39959180198457e-12。

## 2. 覆盖率（先验能不能用，先看它有没有值）

| 池 | 行数 | 化合物 | 有 alpha 行 | 有系数 | 系数覆盖率 | kind 分布 |
|---|---:|---:|---:|---:|---:|---|
| `v11_observations` | 1594 | 98 | 1 | 1 | 1.0% | {'a': 1} |
| `v11_room_band` | 457 | 97 | 0 | 0 | 0.0% | {} |
| `v11_multi_temperature_compounds` | 1535 | 60 | 1 | 1 | 1.7% | {'a': 1} |
| `v10_pool` | 236 | 236 | 119 | 44 | 18.6% | {'a': 28, 'alpha': 16} |
| `lowfreq_candidates` | 501 | 53 | 14 | 9 | 17.0% | {'a': 4, 'alpha': 5} |

## 3. 交叉校验：NBS 系数 vs 经验 dε/dT

经验斜率 = 同一化合物在 v11 观测表（或旁证表）里全部温度点上的最小二乘斜率，单位 K⁻¹。NBS 侧按 kind 分支换算；`alpha` 支额外在**该化合物的观测均值 eps**上取值（经验割线实际所在的 eps）。

| cohort | 配对数 | kind | 经验斜率中位 | NBS 斜率中位 | 带符号偏差中位 | 绝对偏差中位 (p90) | 对称相对偏差中位 (p90) | 同号比例 |
|---|---:|---|---:|---:|---:|---:|---:|---:|
| `lowfreq_extended_gate` | 3 | {'a': 1, 'alpha': 2} | -0.026500 | -0.028503 | 0.002003 | 0.002003 (0.011184) | 7.94% (31.14%) | 100.0% |
| `lowfreq_primary_gate` | 4 | {'a': 2, 'alpha': 2} | -0.064303 | -0.053864 | -0.001122 | 0.005080 (0.015368) | 7.12% (16.71%) | 100.0% |
| `v11_all_bands` | 1 | {'a': 1} | -0.022330 | -0.023800 | 0.001470 | 0.001470 (0.001470) | 6.37% (6.37%) | 100.0% |
| **合并** | 8 | {'a': 4, 'alpha': 4} | -0.026300 | -0.026155 | 0.000977 | 0.002149 (0.015011) | 7.61% (25.04%) | 100.0% |

逐条配对见 `probes/artifacts/dielectric_alpha_prior_crosscheck.csv`；全部经验斜率见 `probes/artifacts/dielectric_alpha_prior_empirical_slopes.csv`。

## 4. 作为先验特征：配对对照

室温带 457 行 / 97 化合物，GroupKFold by InChIKey, shuffled compound order，5×10（50 折）；所有 arm 共用同一折划分与同一被打分行集合。表示法与超参取自冻结管线（`fit_predict_representation` 原样复用）。

| arm | 加了几列 | Hybrid R² | MAE | Spearman | ΔR² vs 基线 | ΔR² vs 同宽安慰块 | 判定 |
|---|---:|---:|---:|---:|---:|---:|---|
| `room_baseline` | 0 | 0.4091 ± 0.0890 | 8.0407 | 0.7763 | n/a | n/a | - |
| `room_plus_null_block_two_columns` | 2 | 0.4231 ± 0.0782 | 7.8332 | 0.7874 | 0.0140 | n/a | - |
| `room_plus_nbs_alpha` | 2 | 0.4231 ± 0.0782 | 7.8332 | 0.7874 | 0.0140 | 0.0000 | inert |
| `room_plus_null_block_one_column` | 1 | 0.4097 ± 0.0889 | 7.9803 | 0.7728 | 0.0006 | n/a | - |
| `room_plus_emp_slope_leaky_all` | 1 | 0.4961 ± 0.0503 | 7.0664 | 0.8175 | 0.0870 | 0.0864 | helps |
| `room_plus_emp_slope_leaky_room` | 1 | 0.3867 ± 0.0737 | 7.9800 | 0.7947 | -0.0224 | -0.0229 | hurts |
| `room_plus_emp_slope_train_only` | 1 | 0.3456 ± 0.0821 | 8.5934 | 0.7407 | -0.0635 | -0.0641 | hurts |

v1.0 池（236 行 / 236 化合物，其中 1 行被 model_ready 扣留、4 行 xTB 失败）：第一个 splitter 逐位重放已发布的 RepeatedKFold 协议，第二个保持本探针的分组纪律。

| arm | 加了几列 | Hybrid R² | MAE | ΔR² vs 基线 | ΔR² vs 同宽安慰块 | 判定 |
|---|---:|---:|---:|---:|---:|---|
| `v10_frozen_baseline` | 0 | 0.3636 ± 0.0394 | 6.6862 | n/a | n/a | - |
| `v10_frozen_plus_null_block` | 2 | 0.3640 ± 0.0327 | 6.6841 | 0.0004 | n/a | - |
| `v10_frozen_plus_nbs_alpha` | 2 | 0.3658 ± 0.0337 | 6.6923 | 0.0022 | 0.0017 | inert |
| `v10_grouped_baseline` | 0 | 0.3767 ± 0.0189 | 6.5990 | n/a | n/a | - |
| `v10_grouped_plus_null_block` | 2 | 0.3767 ± 0.0212 | 6.5995 | -0.0000 | n/a | - |
| `v10_grouped_plus_nbs_alpha` | 2 | 0.3785 ± 0.0228 | 6.6020 | 0.0019 | 0.0019 | inert |

安慰块效应的含义：`inert` 表示该列带给模型的变化落在"换一列噪声"的量级内，即该特征没有被模型用起来；`hurts` 表示它不仅没用、还把采样扰动放大成了实打实的掉点。

## 5. 自检复现

- 室温带基线 Hybrid R² = `0.40911799433511431`，钉住常数 = `0.40911799433511431`，`bit_exact = True`。
- 与两个兄弟 summary 逐格比较（42 格）：`bit_exact = True`，max_abs_delta = 0.0。
- 参照文件：['dielectric_band_ablation_summary.json:summary.band_room_only', 'dielectric_room_window_paired_summary.json:reference.band_ablation.protocols.band_room_only']；缺失：[]。
- 加列扰动对照：`predictions_identical = False`，max_abs_prediction_delta = 5.9327850341796875。

## 6. 未闭环与如实标注

- **α 表与 v11 几乎不相交**：v11 的 98 个化合物里只有 1 个在 alpha 表里，唯一进入多温度集合的是 `Methyl ether`。任务书里那条"与 NBS 514 在共同化合物上对比"在 v11 上因此是 n=1，不构成统计判断；本报告用磁盘上其余温度分辨表把 cohort 撑大，并逐 cohort 单独报告。
- 旁证 cohort（`lowfreq_*`）是**频率弛豫**数据（1 MHz 主闸等），不是零频；它的 dε/dT 含色散成分，只能作为方向与量级的旁证，不能当零频斜率用。
- `lowfreq_candidates` 表来自同期并行工作流，本探针只读它；文件缺失时该 cohort 退化为不出现，不报 0。
- v1.0 池的分组 splitter 与已发布 RepeatedKFold 的折成员不同，因此 `v10_grouped_baseline` 的绝对值**不可与 0.3636 直接比**；两种 splitter 下可读的都是同折配对的 ΔR²。
- 泄漏口径：`room_plus_emp_slope_leaky_*` 的斜率拟合包含了被打分行本身，只能作为"如果有完美敏感度先验能买到多少"的上界；`room_plus_emp_slope_train_only` 是唯一诚实的版本，它在被打分行上覆盖率 0，因此它相对安慰块的效应就是那两列噪声本身的效应。
- 本探针不写 `data/`，不改任何已发布工件，不修改任何既有文件。

## 7. 复现

```powershell
.\\.venv\\Scripts\\python.exe probes\\dielectric_alpha_prior_probe.py
.\\.venv\\Scripts\\python.exe -m pytest tests\\test_dielectric_alpha_prior_probe.py -q
```

输入指纹：

| 文件 | sha256 | 行数 |
|---|---|---:|
| `data/dielectric_v03.csv` | `ff2142936e06e04b329b70f8597574f75349e54ce876e9fff81309e6d35ccce4` | 246 |
| `data/processed/dielectric_lowfreq_candidates.csv` | `d6c97a3a96102486275689cfa3f37792b7c5147d0b3de05c090b80e530e26627` | 501 |
| `data/processed/dielectric_observations_v11.csv` | `7803587afabdec1fcf9cfd319bb64d23f83af8d3fe07124df75052cfcd6a75fc` | 1630 |
| `data/processed/dielectric_physical_features_v03.csv` | `b36d3439560e4381b7779565b9950eed379832e832b72ea6a3a010662ed24fa3` | 241 |
| `data/processed/nbs514_alpha_harmonization.csv` | `d2191efe60b57afcb94f02f9c800a5855fe778361d1b90179135ac1b16581fce` | 215 |
