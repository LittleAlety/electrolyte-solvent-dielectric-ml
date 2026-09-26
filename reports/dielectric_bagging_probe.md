# 杠杆 7：XGBoost bagging 集成（Week 14 R2 攻坚）

> 本文由 `probes/dielectric_bagging_probe.py` 从 `probes/dielectric_bagging_probe_summary.json` 确定性渲染；数字与摘要同源，改一处必须重跑脚本。

## 一、口径与预注册

- 预注册：`probes/dielectric_r2_levers_prereg.json`（status=`locked_before_run`，sha256=`ab3503c037f05ac398b3c0c59d0e4845943d49fa5a5349fa46b8944f2bc1bdaa`），判据先锁后跑、事后不放宽
- 主记分牌：457 行 / 97 化合物，GroupKFold by InChIKey，5 折 × 10 重复，seed=42，min_test_rows_per_fold=2
- 折划分：bagging 臂直接复用基准臂消费的同一份 `splits`，实测折数 = 50，评分侧签名一致 = True（the bagged arm was handed the same fold assignment the baseline arm consumed）
- 基准读数（本脚本内原地重跑）`paired_base` 混合表示 R² = 0.4091179943351143（已发布值 0.4091179943351143，|Δ| = 0.000e+00，容差 1e-09）→ 复现成立

## 二、集成规格（预注册原文）

- 成员数 n_bags = 10；种子规则 `random_state = seed * 1000 + bag index`
- 实际成员种子：[42000, 42001, 42002, 42003, 42004, 42005, 42006, 42007, 42008, 42009]
- 冻结超参：`{'n_estimators': 200, 'max_depth': 2, 'learning_rate': 0.05, 'subsample': 0.8, 'colsample_bytree': 0.8, 'reg_lambda': 1.0, 'objective': 'reg:squarederror', 'tree_method': 'hist', 'max_bin': 64, 'n_jobs': 1}`；改动过的超参：无
- 平均口径：one complete hybrid prediction per bag, then the bags averaged, then the frozen non-negativity clip
- 本臂评分的表示：['Morgan+Physical']（单表示不重复 bagging，只用于基准臂的折号对账）

## 三、三臂读数（混合表示 `Morgan+Physical`）

| 臂 | R² 均值 | R² 标准差 | MAE | MAE·ε>60 | Spearman |
| --- | ---: | ---: | ---: | ---: | ---: |
| 基准臂（原样重跑） | 0.409118 | 0.088967 | 8.040674 | 55.713141 | 0.776256 |
| bagging 臂（10 成员平均） | 0.410867 | 0.082979 | 7.959075 | 56.349949 | 0.778724 |
| 安慰剂臂（同模型、标签打乱） | -0.046001 | 0.010280 | 13.822469 | 69.942903 | 0.038797 |

- 均值位移：**+0.001750**（下限 -0.0050，达标）
- 重复级 R² 标准差：0.088967 → 0.082979 = **+6.73%**（要求收窄 ≥ 20%，未达标）
- 本杠杆真正交付的是**区间**而不是均值：均值不掉不等于结论，只有区间被压窄才算数。

## 四、判决

**DEAD**

- mean grouped R2 moved by +0.001750, against a pre-registered floor of -0.0050
- repeat-level R2 std moved from 0.088967 to 0.082979 (+6.73 percent), against a required shrink of 20 percent
- the interval did not narrow by the pre-registered 20 percent

- 次要判据：ΔMAE = -0.081599（声明噪声带 2% 内：True）；ΔMAE·ε>60 = +0.636808（带内：True）；ΔSpearman = +0.002468
- 噪声带定义：a MAE move inside 2 percent of the baseline MAE is called noise（声明值，非预注册值）

## 五、安慰剂对照

- 打乱标签臂 R² = -0.046001（基准臂重跑 0.409118）
- **同一套打乱标签**上的无信息地板（折内训练均值）= -0.006352
- 相对地板：-0.039649（|Δ| = 0.039649，容差 0.02）
- 塌缩：**True**；严格双侧口径是否也达标：False
- 口径说明：the pre-registration names no reference for the collapse delta; measured against the real-label baseline the test is unsatisfiable by construction, so the control is measured against the no-information floor and both readings are reported

## 六、共享折号

- the bagged arm was handed the same fold assignment the baseline arm consumed（评分侧一致：True）

## 七、合并臂状态

- 本探针只回答「杠杆 7 自身是否过门」（是否进入合并臂：False）；合并臂是否开跑由预注册 `merge_rule` 与集群收口决定。

## 八、shots 计数

- 本杠杆：**1** 次主记分牌实测；安慰剂臂 1 次
- 口径：every scored attempt at the main scoreboard counts, including dead ones

## 九、诚实边界

- the main scoreboard is the 457-row / 97-compound paired_base pool, not the v1.0 236-row pool
- 0.5332 / 0.5454 are never quoted next to the v1.0 headline 0.364 without their pool definitions
- no random_row split was constructed, let alone judged
- test residuals did not steer anything: n_bags and the bag-seed rule were frozen in the pre-registration
- the scored pool, the fold numbers and the metric denominator did not move; only the fitted model did
- every frozen hyper-parameter is untouched; bagging changes how many models are fitted, not what one model is
- the bagged arm is scored on the main scoreboard's representation only; the single representations are not re-bagged
- the bagged arm re-implements the frozen fit loop because the frozen helper fits exactly one model per representation; the baseline arm does not
- the number of worker processes cannot move a number: every fit is independent and seeded

## 十、产物

- `folds`：`probes/artifacts/dielectric_bagging_folds.csv`
- `predictions`：`probes/artifacts/dielectric_bagging_predictions.csv`
- `repeats`：`probes/artifacts/dielectric_bagging_repeats.csv`
- `report`：`reports/dielectric_bagging_probe.md`
- `summary`：`probes/dielectric_bagging_probe_summary.json`
