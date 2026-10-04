# W45-A 扩展层标定列的保真与泄漏审计

只读计算 lane；0 shot。问题：calib_* 是不是 in-sample 仿射、补电平还是补序、泄漏多大。

## 1 标定映射

| target | n | slope | intercept | 残差上限 | batt-fit slope | batt-fit intercept |
| --- | --- | --- | --- | --- | --- | --- |
| homo | 4668 | 0.8702565775077505 | -0.20421040258262516 | 1.7763568394002505e-15 | 0.870256577507751 | -0.20421040258262502 |

## 2 保序与电平

| target | rho(gfn2,batt) | rho(calib,batt) | 差 | MAE 前 | MAE 后 | CV MAE | 泄漏缺口 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| homo | 0.8388852321667876 | 0.8388852321667876 | 0.0 | 1.206598583979079 | 0.3031706538321493 | 0.3032870786108595 | 0.00013051895059329466 |

- 449 行 calibrated_estimate 套用同一映射的残差上限： 1.7763568394002505e-15。

## 3 判据

| 判据 | 描述 | 读数 | 阈值 | 结论 |
| --- | --- | --- | --- | --- |
| H45a1 | paired_anchor 行数 >= 4600（双端 gap 齐备） | 4668 | 4600 | 成立 |
| H45a2 | calibrated_estimate 行数 >= 400 | 449 | 400 | 成立 |
| H45a3 | calib_homo 是 homo_gfn2 的精确一元仿射（残差上限 <= 1e-9） | 1.7763568394002505e-15 | 1e-09 | 成立 |
| H45a4 | 该仿射与 homo_gfn2->homo_batt 的 in-sample OLS 同一映射 | {"slope_delta": 4.440892098500626e-16, "intercept_delta": 1.3877787807814457e-16} | {"tolerance": 1e-06} | 成立 |
| H45a5 | 仿射保序：rho(calib_homo,batt) == rho(homo_gfn2,batt) | {"spearman_gfn2_batt": 0.8388852321667876, "spearman_calib_batt": 0.8388852321667876, "delta": 0.0} | {"tolerance": 1e-06} | 成立 |
| H45a6 | 标定只补电平：homo MAE 从 >= 1.0 降到 <= 0.35 eV | {"before": 1.206598583979079, "after": 0.3031706538321493} | {"before_min": 1, "after_max": 0.35} | 成立 |
| H45a7 | 标定只覆盖 homo：calib_lumo 在 paired 行上非空计数 = 0（登记为已知边界） | {"calib_homo_nonempty": 4668, "calib_lumo_nonempty": 0} | {"calib_lumo_nonempty": 0} | 成立 |
| H45a8 | 449 行 calibrated_estimate 套用同一映射（残差上限 <= 1e-9） | 1.7763568394002505e-15 | 1e-09 | 成立 |
| H45a9 | 5 折 out-of-sample 复拟合 MAE <= 0.45 eV 且泄漏缺口 >= 0 | {"cv_mae": 0.3032870786108595, "leakage_gap": 0.00013051895059329466} | {"cv_mae_max": 0.45, "leakage_gap_min": 0} | 成立 |
| H45a10 | 输入（扩展层 + prereg）sha256 未变 | True | True | 成立 |

## 4 边界

- 只读：不改 calib 列、不改标签或特征列。
- 结论：该标定列是 2 参数 in-sample 仿射；仿射保序，因此它对 Batt 的秩一致与原始 gfn2 完全相同，只补电平不补序。
- 0 shot；四个冻结读数一个不动。
