# 覆盖率配对基准的对抗复核（独立复算，只读、离线）

被审对象：`probes/dielectric_coverage_paired_benchmark_summary.json`

- 复核脚本：`probes/dielectric_coverage_paired_benchmark_audit.py`
- 机器可读结论：`probes/dielectric_coverage_paired_benchmark_audit_summary.json`
- 本复核不 import 被审模块、不重训模型、不联网，只从已发布的 CSV/JSON 独立复算。

## 总判定

- 确认 5 项 / 证伪 0 项 / 仍存疑 0 项

| 查伪项 | 判定 | 一句话结论 |
| --- | --- | --- |
| prediction_shift | confirmed | changed cells 4570/4570 (100.0000%) |
| training_expansion_composition | confirmed | the +127 training rows are exactly the thermoml_low_frequency room rows of 50 compounds, none scored and none of them carried by the v11 table |
| prior_shift_alternative | confirmed | the added block has a clearly different target distribution, yet the rank-based Spearman also rises and the paired delta still tracks the target deviation after the shrinkage direction is partialled out, so a pure level/scale prior shift is excluded |
| fold_identity_and_metrics | confirmed | folds, scored rows, headline metrics, the v11 block and the input digest all reproduce |
| leak_reference_framing | confirmed | the row-level number is stamped as a leak reference in the JSON, kept out of the fixed-pool chain and the verdict; it occurs in 4 report line(s), and after counting the protocol name itself as a label every one of them is labelled (the strict rule flags 1 table row(s), whose first cell is the self-labelling protocol name) |

## 1. 预测真的变了吗

| 表示 | 对齐槽位数 | 逐位相同 | 变了 | 变动比例 | 平均位移 | 最大位移绝对值 |
| --- | --- | --- | --- | --- | --- | --- |
| Morgan | 4570 | 0 | 4570 | 100.0000% | -2.0816 | 61.3384 |
| Physical | 4570 | 4 | 4566 | 99.9125% | 0.0387 | 51.2878 |
| Morgan+Physical | 4570 | 0 | 4570 | 100.0000% | -1.0195 | 39.2948 |

Hybrid 口径：4570 个槽位里 4570 个预测值逐位不同（100.0000%），平均位移 -1.0195，位移区间 [-39.2948, 22.6277]，10 次重复的重复内平均位移落在 [-4.0708, 0.6191]，没有任何一次重复的平均位移为 0。

**判定：confirmed** —— 新增训练料确实进入了模型，不存在「新行没进训练」的假结论。

## 2. 训练面是不是真的多了料

独立重建的门控表（同一套可用性规则，由本复核自己重写）：

| 阶段 | zero_frequency 行/化合物 | low_frequency 行/化合物 |
| --- | --- | --- |
| 门控前（原始合并表） | 460 / 100 | 127 / 50 |
| 门控后（打分池 / 新增） | 457 / 97 | 127 / 50 |

- 新增化合物 ∩ 被打分化合物 = 空集（必须为空）
- 新增化合物中已带 v11 观测的 = 空集（必须为空）
- 行级指纹（inchikey+T_K+epsilon+DOI+文件+行号）重叠 = 0
- 逐折训练行差（folds.csv 独立重算）：50 折，均值 127.0，范围 [127, 127]
- 门控前该带被丢掉各 1 行的化合物：GSGLHYXFTXGIAQ-UHFFFAOYSA-M, IXQYBUDWDLYNMA-UHFFFAOYSA-N, JWFPQAXAGSAKRF-UHFFFAOYSA-N（与 summary 的 room_gate_audit 一致）。

**判定：confirmed** —— the +127 training rows are exactly the thermoml_low_frequency room rows of 50 compounds, none scored and none of them carried by the v11 table

## 3. +0.1241 会不会只是目标分布位移

新增 127 行训练目标 vs 被打分 457 行目标（都从合并表独立重算）：

| 口径 | 行数 | 均值 | 中位 | 总体方差 | min | max | >60 行数 | >60 占比 | <20 占比 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 被打分池（457 行） | 457 | 21.4895 | 16.0800 | 335.6435 | 1.93 | 178.47 | 13 | 2.84% | 61.05% |
| 新增训练行（127 行） | 127 | 12.6602 | 9.3500 | 303.4563 | 1.89 | 169.76 | 1 | 0.79% | 85.83% |

- KS 统计量 0.3267（置换 p = 0.0002）；均值差 -8.8293（= -0.481 个池标准差，置换 p = 0.0002）。
- 判定：新增块**不是**同分布（本复核判为不同分布）——「新增行与打分池同分布，增益只是更好的先验」这条替代解释在数据上不成立。

更有判别力的两条离线证据：

1. **秩不变性反证**：对 `paired_base` 的预测整体加 25（纯水平位移）或整体乘 0.5（纯缩放），Spearman 完全不动（0.773762 / 0.773762 / 0.773762），而 R² 从 0.4091 变到 -1.4465 / -0.0474。也就是说 R² 会被纯水平/缩放伪影拉动，**Spearman 不会被拉动**。
   （上面三个 Spearman 是池化 4570 格上的值，所以 0.7738 与逐重复均值 0.7763 略有出入；R²/MAE 因为每次重复都打分同一批 457 行而可精确分解，池化值恰好等于逐重复均值。下同。）
   逐重复口径的实测 Spearman 由 0.7763 升到 0.8844（+0.1081）——排序信息真的变好了，这不是水平/缩放能造出来的。
2. **误差归因分解**：把配对 MSE 变化拆成对齐项与位移罚项，对齐项 -79.1438、位移罚项 37.4950，净变化 -41.6488（对齐项是位移罚项的 2.11 倍，净增益只有对齐项的 53%，其余被位移吃掉）。逐化合物看，97 个被打分化合物里 64 个平均绝对误差下降、33 个上升；逐行看 2755 / 4570 行的绝对误差下降。改善是弥散的，不是个别化合物带出来的。
   更直接的一条：预测增量与「向池均值收缩」方向的相关系数只有 +0.0152（近似正交），把该方向偏回归掉之后，预测增量与目标偏离（y 减池均值）的偏相关仍有 +0.5664。这次位移不是向中心收缩，它带着目标信息。

分层 MAE（从 repeats.csv 独立重算，Hybrid）：

| 口径 | MAE<20 | MAE 20-60 | MAE>60 | Spearman | MAE | RMSE | R2 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| paired_base | 5.8821 | 7.9347 | 55.7131 | 0.7763 | 8.0407 | 14.0504 | 0.4091 |
| paired_plus_coverage | 3.9366 | 7.6186 | 47.4743 | 0.8844 | 6.5045 | 12.5006 | 0.5332 |

**判定：confirmed** —— the added block has a clearly different target distribution, yet the rank-based Spearman also rises and the paired delta still tracks the target deviation after the shrinkage direction is partialled out, so a pure level/scale prior shift is excluded

**仍然排除不掉的那一支**：新增行来自**另一批化合物**，它们对「同一批被打分化合物」的作用可能只是**样本量/正则化**（更多行把树的正则拉紧、把输出分布收窄），而不是「新化学带来可迁移信息」。
要彻底排除它，需要一次重训对照（本复核按约定不重训）：

1. **安慰剂重训**：行、特征、折完全不变，只把新增 127 行的目标值随机置换。若 R² 仍显著上升，那是样本量/正则效应；若增益消失，增益归功于特征-目标关系。
2. **第三批化合物**：另取一批表外化合物做同样加料，看增益是否复现。

## 4. 挡拆检查（折与分母逐位一致）

- `paired_base` 与 `paired_plus_coverage` 共 50 个 (repeat, fold) 槽，被打分行序列（inchikey+T_K+target，含顺序）逐位相同：不一致槽位 0 个。
- 每折被打分行数集合 [40, 43, 46, 51, 55, 59, 60, 63, 68, 72, 73, 74, 77, 78, 80, 81, 82, 91, 92, 94, 97, 98, 99, 102, 104, 106, 108, 109, 111, 114, 116, 117, 124, 126, 128, 129, 136, 162]，10 次重复合计 4570 行（= 457 乘 10）。

从原始预测表独立重算的指标 vs 已发布值：

| 指标 | 复算 base | 发布 base | 绝对差 | 复算 widened | 发布 widened | 绝对差 |
| --- | --- | --- | --- | --- | --- | --- |
| r2 | 0.409117994335 | 0.409117994335 | 0.00e+00 | 0.533204444033 | 0.533204444033 | 0.00e+00 |
| mae | 8.040673846400 | 8.040673846400 | 0.00e+00 | 6.504491097161 | 6.504491097161 | 0.00e+00 |
| rmse | 14.050439465637 | 14.050439465637 | 0.00e+00 | 12.500628788243 | 12.500628788243 | 0.00e+00 |
| spearman | 0.776256478070 | 0.776256478070 | 0.00e+00 | 0.884356126300 | 0.884356126300 | 0.00e+00 |

- 跨工件对账：`paired_base` 与 `dielectric_room_window_paired_predictions.csv` 的 `band_room_only` 比 4570 格，被打分行序列不一致 0 个、预测值逐位不同 0 个（即完全 bit-exact）。
- 钉死的字面量 0.4091179943351143 == room_window_paired summary 的 band_room_only Hybrid R2 0.4091179943351143：True。
- 合并表 v11 块：v11plus 的 zero_frequency 子表 1630 行 vs v11 表 1630 行，共比 30 列，顺序一致 True、集合一致 True。
- 输入摘要：合并表 LF 规范化 sha256 159b928f800a5596 与 summary 声明值 159b928f800a5596：True。

**判定：confirmed** —— folds, scored rows, headline metrics, the v11 block and the input digest all reproduce

## 5. 行级随机折有没有被当成结论

- 该口径在 JSON 里的描述：`LEAK REFERENCE ONLY: same rows as extended_pool_room but split by row, so one compound reaches both sides of a fold. Never a conclusion number.`
- leak_reference.note：`reported to size the leak only; never a conclusion number`
- 它的数 0.6748 与 grouped 同池的 0.4783 并列，但不在固定池 chain 里（chain 提到该口径：False），也不在 verdict 里（verdict 提到 random_row：False）。
- 报告 `reports/dielectric_coverage_paired_benchmark.md` 里含该数字的行 4 行，未带泄漏标记的 0 行。
- 判据透明说明：严格标记表（泄漏/LEAK/参照/绝不/虚高）最初命中 `1` 行未标记——那是家族二的汇总表行，首列就是协议名 `extended_pool_room_random_row`，协议名本身即标记。把协议名计入标记后未标记行为 `0`，本复核据此判 confirmed，并把两种口径都留在 JSON 里（`report_unlabelled_lines_strict_rule` 与 `report_unlabelled_lines_with_0_6748`）。
- 扩展池族的 comparability 声明：`a different scored pool from the fixed-pool family, so its R2 is NOT comparable to the 0.4091 of band_room_only; the pool variance is reported for that reason`

**判定：confirmed** —— the row-level number is stamped as a leak reference in the JSON, kept out of the fixed-pool chain and the verdict; it occurs in 4 report line(s), and after counting the protocol name itself as a label every one of them is labelled (the strict rule flags 1 table row(s), whose first cell is the self-labelling protocol name)

## 三段清单

### 被证伪

- 无：本次 5 项查伪没有一项推翻 Boyle 的结论。

### 被确认

- `prediction_shift`：changed cells 4570/4570 (100.0000%)
- `training_expansion_composition`：the +127 training rows are exactly the thermoml_low_frequency room rows of 50 compounds, none scored and none of them carried by the v11 table
- `prior_shift_alternative`：the added block has a clearly different target distribution, yet the rank-based Spearman also rises and the paired delta still tracks the target deviation after the shrinkage direction is partialled out, so a pure level/scale prior shift is excluded
- `fold_identity_and_metrics`：folds, scored rows, headline metrics, the v11 block and the input digest all reproduce
- `leak_reference_framing`：the row-level number is stamped as a leak reference in the JSON, kept out of the fixed-pool chain and the verdict; it occurs in 4 report line(s), and after counting the protocol name itself as a label every one of them is labelled (the strict rule flags 1 table row(s), whose first cell is the self-labelling protocol name)

### 仍存疑

- 本复核的 5 项判定中无「仍存疑」项。
- **离线复核能力之外的残留**：新增 127 行究竟是「样本量/正则化效应」还是「可迁移的新化学信息」，只能靠重训对照（安慰剂目标置换 / 第三批化合物）分开，本复核按约定不重训。
- **频率档位本身的认证**仍是老问题：同源配对 0/136，只能界定偏差不能认证；0.01 MHz 档的系统负偏未归因。这与本基准的配对结论无关，但仍属本条线的未闭环项。

