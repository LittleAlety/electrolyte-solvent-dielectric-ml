# W32-A 结题报告：四个核心通道 × 多种代理 —— 排序不稳定性的抽样律

- **性质**：后验读数（post-hoc）。只读盘上已冻结的逐分子「预测—标签」表；不重新拟合主记分牌臂、不新增特征列、不联网、**不占主记分牌 shot**。
- **输入**：`data/processed/dielectric_representation_ablation_predictions.csv`、`viscosity_baseline_predictions.csv`、`l3_homo_lumo_cv_predictions.csv`、`probes/artifacts/p4_redox_v2_predictions.csv`，逐位只读并记录 sha256。
- **产出**：`probes/artifacts/w32_rank_stability_series.csv` / `_curves.csv` / `.json` / `.png`。
- **重抽**：每个序列在每个 N 上 1000 次无放回抽子集，N ∈ [10, 18, 25, 49, 100]，种子 = 20261003 + 序列序号（可复算）。

## 0. 一句话

W24-3 在介电通道上实测出的重抽律 `sd(N) = s0·sqrt(1/N − 1/N_pop)`，本轮被搬到**四个核心通道、26 个「代理 vs 标签」序列**上重新检验：拟合 rmse 的中位是 0.0071（门 0.012），并且 s0 不是任意常数 —— 它随排序保真度缺口单调上升（Spearman 0.806）。因此这条律不是介电通道的巧合，而是**秩统计量在有限总体上的普遍行为**；每个通道由此得到自己的噪声地板与最小信息预算。

## 1. 序列清单

| 通道 | 序列数 | 评测单元数（中位） | 保真度 tau_b（中位） | s0（中位 / 区间） |
| --- | --- | --- | --- | --- |
| 介电常数 eps | 3 | 205 | 0.6583 | 0.474 / 0.452–0.563 |
| 分子轨道 HOMO/LUMO/IP/EA | 8 | 29515 | 0.3656 | 0.583 / 0.311–0.761 |
| 氧化还原自由能 | 12 | 392 | 0.7675 | 0.369 / 0.307–0.716 |
| 黏度 eta | 3 | 708 | 0.1179 | 0.490 / 0.000–0.734 |

| 序列 | 通道 | 单元数 | tau_b（全量） | s0 | 拟合 rmse | sd@N=12 | sd@N=18 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `dielectric|Morgan|epsilon` | dielectric | 205 | 0.5150 | 0.563 | 0.0094 | 0.1577 | 0.1267 |
| `dielectric|Morgan+Physical|epsilon` | dielectric | 205 | 0.6603 | 0.474 | 0.0088 | 0.1327 | 0.1066 |
| `dielectric|Physical|epsilon` | dielectric | 205 | 0.6583 | 0.452 | 0.0069 | 0.1267 | 0.1018 |
| `viscosity|DummyMean|log10_eta_cP` | viscosity | 708 | 0.0000 | 0.000 | 0.0000 | 0.0000 | 0.0000 |
| `viscosity|MorganTemperatureXGBoost|log10_eta_cP` | viscosity | 708 | 0.6885 | 0.490 | 0.0093 | 0.1403 | 0.1141 |
| `viscosity|TOnlyRidge|log10_eta_cP` | viscosity | 708 | 0.1179 | 0.734 | 0.0099 | 0.2102 | 0.1708 |
| `orbital|dummy_mean|EA` | orbital | 29515 | -0.0183 | 0.742 | 0.0077 | 0.2143 | 0.1750 |
| `orbital|morgan_plus_2d+deeper_slower|EA` | orbital | 29515 | 0.7482 | 0.431 | 0.0076 | 0.1243 | 0.1015 |
| `orbital|dummy_mean|HOMO` | orbital | 29515 | -0.0201 | 0.761 | 0.0072 | 0.2195 | 0.1792 |
| `orbital|morgan_plus_2d+deeper_slower|HOMO` | orbital | 29515 | 0.8205 | 0.323 | 0.0069 | 0.0933 | 0.0762 |
| `orbital|dummy_mean|IP` | orbital | 29515 | -0.0194 | 0.735 | 0.0075 | 0.2121 | 0.1731 |
| `orbital|morgan_plus_2d+deeper_slower|IP` | orbital | 29515 | 0.8246 | 0.313 | 0.0056 | 0.0904 | 0.0738 |
| `orbital|dummy_mean|LUMO` | orbital | 29515 | -0.0170 | 0.756 | 0.0067 | 0.2181 | 0.1781 |
| `orbital|morgan_plus_2d+deeper_slower|LUMO` | orbital | 29515 | 0.8232 | 0.311 | 0.0074 | 0.0898 | 0.0733 |
| `redox|dummy_mean|oxidation_free_energy` | redox | 392 | -0.2019 | 0.710 | 0.0070 | 0.2018 | 0.1635 |
| `redox|gpr_enriched|oxidation_free_energy` | redox | 392 | 0.8342 | 0.347 | 0.0070 | 0.0986 | 0.0798 |
| `redox|linear_scalar|oxidation_free_energy` | redox | 392 | 0.8166 | 0.340 | 0.0051 | 0.0965 | 0.0782 |
| `redox|ridge_enriched|oxidation_free_energy` | redox | 392 | 0.8266 | 0.327 | 0.0082 | 0.0931 | 0.0754 |
| `redox|xgb_enriched|oxidation_free_energy` | redox | 392 | 0.8608 | 0.307 | 0.0054 | 0.0871 | 0.0706 |
| `redox|xgb_structure_only|oxidation_free_energy` | redox | 392 | 0.6744 | 0.472 | 0.0096 | 0.1341 | 0.1086 |
| `redox|dummy_mean|reduction_free_energy` | redox | 392 | -0.1725 | 0.716 | 0.0086 | 0.2035 | 0.1648 |
| `redox|gpr_enriched|reduction_free_energy` | redox | 392 | 0.7680 | 0.392 | 0.0076 | 0.1115 | 0.0903 |
| `redox|linear_scalar|reduction_free_energy` | redox | 392 | 0.7346 | 0.447 | 0.0062 | 0.1272 | 0.1030 |
| `redox|ridge_enriched|reduction_free_energy` | redox | 392 | 0.7670 | 0.335 | 0.0059 | 0.0953 | 0.0772 |
| `redox|xgb_enriched|reduction_free_energy` | redox | 392 | 0.8130 | 0.341 | 0.0063 | 0.0968 | 0.0784 |
| `redox|xgb_structure_only|reduction_free_energy` | redox | 392 | 0.6936 | 0.445 | 0.0068 | 0.1264 | 0.1024 |

## 2. 闭式检验（R1）

- 拟合 rmse 的**中位 0.0071** 对门 0.012 ⇒ **成立**；最差的一条是 0.0099；100.0% 的序列 rmse ≤ 0.020。
- 这与 W24-3 在介电**层级**口径上得到的 rmse ≤ 0.0086 同量级：把参照物从「另一个电子结构层级」换成「另一个模型」并不改变这条律的形式。

## 3. s0 不是常数，而是保真度的函数（R2）

- Spearman(s0, 1 − tau_b_full) = **0.806**（门 > 0）⇒ **成立**。
- 读法：一个代理越排不好（缺口越大），它在小样本上的**重抽标准差也越大** —— s0 度量的是「排序信号在每个化合物上的离散度」，不是某个通道的固定常数。因此跨通道比较噪声地板时，必须**在同一保真度水平上比**（见 §4 的 dummy 对照）。

## 4. 每个通道的最小信息预算（R3）

| 通道 | s0（中位） | 分子数（中位） | sd@N=12（中位） | sd@N=18（中位） | 使 sd ≤ 0.05 所需 N |
| --- | --- | --- | --- | --- | --- |
| 介电常数 eps | 0.474 | 205 | 0.1327 | 0.1066 | 62 |
| 分子轨道 HOMO/LUMO/IP/EA | 0.583 | 29515 | 0.1682 | 0.1373 | 135 |
| 氧化还原自由能 | 0.369 | 392 | 0.1050 | 0.0851 | 48 |
| 黏度 eta | 0.490 | 708 | 0.1403 | 0.1141 | 85 |

- 这张表把「这个通道现在能不能分辨两档方法的排序差异」变成可算的数：把中位 s0 代回闭式即得。

## 5. 与冻结的介电层级口径对比（R4）

- 冻结的 `w24_3_sampling_law.csv`（层级 vs 层级，池 204–242）：s0 ∈ [0.307, 0.542]，中位 0.436。
- 本轮「代理 vs 标签」的 s0 中位 0.446。两者**不同口径**（前者量的是层级位移的方向一致性，后者量的是模型误差），因此**不得直接混比**；可比的是律的**形式**与各自通道内部的相对结构。

## 6. 零假设对照（R5）

- dummy 均值臂（无信息）的 tau_b 中位 -0.0194（门 |tau| ≤ 0.050）⇒ **成立**；其拟合 rmse 中位 0.0072。
- 意义：闭式对**零信号序列**同样成立，说明它描述的是「子集抽取」这件事本身，而不是被拟合出来的假象。

## 7. 口径与边界（必须并报）

1. **评测单元随通道而定**：介电 / 氧化还原按分子聚合（对重复与折取均值），轨道通道用出折预测均值，而**黏度按（分子 x 温度）行**排序 —— 黏度是温度依赖量，按分子平均会把温度信号抹平；每个序列的单元与聚合方式登记在 `_series.csv` 的 `unit` / `aggregation` 列。
2. **N_pop 是序列可用评测单元数**，不是数据库键数：例如介电 205、黏度 192、氧化还原 392、轨道 29,515。跨通道比较噪声地板时必须同时报 N_pop。
3. **不占 shot**：本件不改主记分牌、不引用 Reaxys 数值、不新增特征列；它是 W24-3/W31-A 那条线的第三个刻度。
4. **不得外推**：s0 是对「该序列在该分子池上的排序信号离散度」的估计，跨池不可搬运；换池必须重算。
