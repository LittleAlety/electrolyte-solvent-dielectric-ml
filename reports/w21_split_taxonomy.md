# W21 Tier 2：三种拆分的并排报告（框架 §13.2）

任务 = 用 X0 块预测 **R_sol 的 HOMO**（45 个化合物带完整块，掉 4 个）。
三种拆分必须同时报告，且 LOFO 是 transferability 的主要证据来源。

| split | model | metric | mean | std | folds |
| --- | --- | --- | --- | --- | --- |
| random_repeated_kfold_5x10 | mean_baseline | R² | -0.276026 | 0.445205 | 50 |
| random_repeated_kfold_5x10 | ridge | R² | 0.375861 | 0.472557 | 50 |
| random_repeated_kfold_5x10 | krr | R² | -14.344727 | 10.790139 | 50 |
| random_repeated_kfold_5x10 | krr_tuned | R² | 0.376606 | 0.496527 | 50 |
| random_repeated_kfold_5x10 | gpr | R² | 0.446523 | 0.410636 | 50 |
| random_repeated_kfold_5x10 | random_forest | R² | 0.594256 | 0.299366 | 50 |
| random_repeated_kfold_5x10 | gradient_boosting | R² | 0.483878 | 0.528863 | 50 |
| random_repeated_kfold_5x10 | single_feature_baseline | R² | 0.508443 | 0.266980 | 50 |
| group_kfold_scaffold_5 | mean_baseline | R² | -2.443537 | 5.156219 | 5 |
| group_kfold_scaffold_5 | ridge | R² | -1.453592 | 4.615526 | 5 |
| group_kfold_scaffold_5 | krr | R² | -44.442010 | 70.103522 | 5 |
| group_kfold_scaffold_5 | krr_tuned | R² | -1.373457 | 4.233357 | 5 |
| group_kfold_scaffold_5 | gpr | R² | -1.069547 | 3.749411 | 5 |
| group_kfold_scaffold_5 | random_forest | R² | -0.900873 | 3.497608 | 5 |
| group_kfold_scaffold_5 | gradient_boosting | R² | -1.317722 | 4.245338 | 5 |
| group_kfold_scaffold_5 | single_feature_baseline | R² | -1.546094 | 4.898639 | 5 |
| lofo_family_min5 | mean_baseline | R² | -27.446820 | 31.698863 | 4 |
| lofo_family_min5 | ridge | R² | -10.553947 | 7.681254 | 4 |
| lofo_family_min5 | krr | R² | -164.814956 | 72.607814 | 4 |
| lofo_family_min5 | krr_tuned | R² | -26.824168 | 33.512179 | 4 |
| lofo_family_min5 | gpr | R² | -5.681409 | 4.102058 | 4 |
| lofo_family_min5 | random_forest | R² | -6.474553 | 7.518268 | 4 |
| lofo_family_min5 | gradient_boosting | R² | -13.884582 | 19.868937 | 4 |
| lofo_family_min5 | single_feature_baseline | R² | -5.826825 | 6.222672 | 4 |

- 骨架组数：34；LOFO 可用家族（成员 ≥ 5）：`[np.str_('aromatic_hydrocarbon'), np.str_('ester'), np.str_('ether'), np.str_('other')]`
- 平均基线（mean_baseline）必须读：R² 的零点是它，不是 0。
- 本件是 **machinery pilot**：n = 49 在框架 §13.3 的薄区里。
