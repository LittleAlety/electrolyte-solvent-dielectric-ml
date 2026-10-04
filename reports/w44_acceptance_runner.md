# W44-B 逐轮验收运行器（治理 lane，0 shot）

一次同时跑 W43-D 的四个台账不变式 + 逐轮交付摘要的五类验收字段。

## 1 台账不变式（复用 W43-D 规则）

- 负结果并集稳定 = True；冻结读数越界 = 0；shot 单调 = True；上限 = 19；扫描 JSON = 347。

## 2 逐轮验收矩阵

- 扫描轮数 41；声明验收字段 33；判 fail 的轮： 无。
- 最近五轮：week40, week41, week42, week43, week44，全过 = True。

| 轮 | verification_passed | lanes_missing 空 | 冻结红线 | 无未登记判否 | 判定 |
| --- | --- | --- | --- | --- | --- |
| week33 | True | True | — | — | pass |
| week34 | True | True | — | — | pass |
| week35 | True | True | — | — | pass |
| week36 | True | True | — | — | pass |
| week37 | True | True | — | — | pass |
| week38 | True | True | True | — | pass |
| week39 | True | True | True | True | pass |
| week40 | True | True | True | True | pass |
| week41 | True | True | True | True | pass |
| week42 | True | True | True | True | pass |
| week43 | True | True | True | True | pass |
| week44 | True | True | True | True | pass |

## 3 判据

| 判据 | 描述 | 读数 | 阈值 | 结论 |
| --- | --- | --- | --- | --- |
| H44b1 | 扫描到的轮数 >= 40 | 41 | 40 | 成立 |
| H44b2 | 声明了验收字段的轮数 >= 30 | 33 | 30 | 成立 |
| H44b3 | 最近五轮验收全部通过 | {"weeks": ["week40", "week41", "week42", "week43", "week44"], "all_pass": true} | {"min": 5, "all_pass": true} | 成立 |
| H44b4 | 无任何一轮判 fail | [] | [] | 成立 |
| H44b5 | 复用 W43-D 的四个台账不变式全部成立 | {"negatives_stable": true, "frozen_outside": 0, "monotone": true, "ceiling": 19} | {"negatives_stable": true, "frozen_outside": 0, "monotone": true, "ceiling": 19} | 成立 |
| H44b6 | 台账扫描数 >= 300（守卫仍有效） | 347 | 300 | 成立 |
| H44b7 | 输入文件生成前后 sha256 不变 | 1.0 | 1.0 | 成立 |

## 4 边界

- 只读：不改任何 week summary，不重跑模型，不新增 shot。
- 早期轮次没有这些字段（记为 not_declared，不算 fail）；运行器不会替它们补字段。
- 0 shot；四个冻结读数一个不动。
