# Week 14 合并臂（杠杆 2 / 3 / 7）

> 本文由 `probes/dielectric_merge_arm_probe.py` 从 `probes/dielectric_merge_arm_summary.json` 确定性渲染；数字与摘要同源，改一处必须重跑脚本。

## 一、预注册口径

- 预注册：`probes/dielectric_r2_levers_prereg.json`（sha256=`ab3503c037f05ac398b3c0c59d0e4845943d49fa5a5349fa46b8944f2bc1bdaa`）
- 合并规则：only levers that cleared their own criterion may be combined. The merge arm is re-scored on the main scoreboard, and its delta is reported against the best single passing lever as well as against the baseline, so a merge that adds nothing is visible.
- 全不过门时的规则：the merge arm is not run; the week reports three dead levers and keeps the 0.5454 reading untouched

## 二、杠杆清点

| 杠杆 | 状态 | 主记分牌 R² 均值 | ΔR²（相对各自基准臂） |
| --- | --- | ---: | ---: |
| `lever_2_association_blind_spot_features` | dead | 0.397234 | -0.011884 |
| `lever_3_target_transform_and_robust_loss` | dead | 0.303746 | -0.105372 |
| `lever_7_bagging` | dead | 0.410867 | +0.001750 |

- 过门：无；死：['lever_2_association_blind_spot_features', 'lever_3_target_transform_and_robust_loss', 'lever_7_bagging']；未定：无

## 三、判决

- 合并臂是否开跑：**False**
- 是否退化为单杠杆：**False**
- 理由：no lever cleared its own criterion, so the pre-registered `merge_rule.if_nothing_passes` applies: the merge arm is not run and the week reports three dead levers

## 四、为什么不跑

按预注册原文，合并臂只在有杠杆过门时才开跑。本轮逐条结果是：

- `lever_2_association_blind_spot_features`：dead，ΔR² = -0.011884
- `lever_3_target_transform_and_robust_loss`：dead，ΔR² = -0.105372
- `lever_7_bagging`：dead，ΔR² = +0.001750

因此这里**没有**「合并等于白干」需要回答：根本没有合并发生。

## 五、shots 计数

- 合并臂自身新增的记分牌实测次数：**0**
- 说明：the merge arm was not run, so it adds no scored attempt to the main scoreboard

## 六、诚实边界

- this arm combines only levers that cleared their own criterion; a dead lever is never smuggled in
- the main scoreboard is the 457-row / 97-compound paired_base pool, not the v1.0 236-row pool
- 0.5332 / 0.5454 are never quoted next to the v1.0 headline 0.364 without their pool definitions
- no random_row split was constructed, let alone judged

## 七、产物

- `report`：`reports/dielectric_merge_arm.md`
- `summary`：`probes/dielectric_merge_arm_summary.json`
