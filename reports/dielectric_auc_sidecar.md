# 把主链路丢掉的 AUC 补回来（零重拟合，不动任何冻结字节）

**这不是新模型、也不是新读数。** `evaluate_repeat` 一直在算 `auc_gt15` / `auc_gt30`，
但 `METRIC_NAMES`（它驱动 `REPEAT_COLUMNS_OUT`）只有 7 个指标，
所以每个记分牌的 repeats CSV 都把这两列丢了；预测行本身**是随包发的**，
AUC 只依赖 `(target, prediction)`，因此可以**离线重算**。

## 口径

- 随包指标列：r2, mae, rmse, spearman, mae_lt20, mae_20_60, mae_gt60
- 侧车补列：auc_gt15, auc_gt30
- **不修改 `METRIC_NAMES`**：改它会改被锁 CSV 的表头与字节。本探针只**新建**文件。
- 诚实性检查：用同一批预测行重新求出的 R² 必须与随包 repeats CSV **逐位一致**，
  容差 1e-09，否则拒绝写出。

## 各源（重新求出的 R² 与随包值之差）

| 源 | key 列 | 打分组数 | 预测行 | 最大 R² 差 | AUC>15 均值 | AUC>30 均值 |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| dielectric_coordination_block_v3 | arm | 230 | 105110 | 0.00e+00 | 0.6821 | 0.7011 |
| dielectric_observations_benchmark | protocol | 90 | 98580 | 0.00e+00 | 0.8654 | 0.8673 |
| dielectric_room_window_paired | protocol | 240 | 111390 | 0.00e+00 | 0.8362 | 0.8476 |
| dielectric_coverage_paired_benchmark | protocol | 180 | 89880 | 0.00e+00 | 0.8938 | 0.9152 |
| dielectric_band_ablation | protocol | 150 | 103110 | 0.00e+00 | 0.8189 | 0.8187 |

## 边界（不许省略）

1. AUC 是**已经随包的行**的第二种读法，不是新拟合；它解释 R² 与 AUC 的差距，**不动任何冻结数**。
2. 冻结头条保持 0.4766400383507876，冻结基线保持 0.4091179943351143。
3. 每个随包 repeats CSV 的 sha256 已记录在摘要里，并由守护测试复核。

