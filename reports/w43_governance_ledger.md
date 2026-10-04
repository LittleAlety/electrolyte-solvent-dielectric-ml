# W43-D 仓库级治理台账守卫（治理 lane，0 shot）

把 `probes/**/*.json` 当一本台账机器校验四条不变式。

## 1 不变式

- 扫描 JSON 数：339；带 ledger 的 summary：42。
- 登记负结果并集：["H38a2", "H38b1", "H39a7", "H40a5", "H40c10", "H40c11", "H40d8", "H41b5", "H41d8"]（期望 ["H38a2", "H38b1", "H39a7", "H40a5", "H40c10", "H40c11", "H40d8", "H41b5", "H41d8"]）⇒ 稳定 = True。
- 冻结读数越界计数 = 0 ⇒ 完整 = True。
- 累计 shot 序列：长度 42，min = 19，max = 19，单调不减 = True。
- 本轮 W43 各件：summary 数 5，shots_this_week 全为 0 = True。

## 2 判据

| 判据 | 描述 | 读数 | 阈值 | 结论 |
| --- | --- | --- | --- | --- |
| H43d1 | 扫描到的 JSON 数 >= 300 | 339 | 300 | 成立 |
| H43d2 | 登记负结果集合稳定 == 已知 9 条 | ["H38a2", "H38b1", "H39a7", "H40a5", "H40c10", "H40c11", "H40d8", "H41b5", "H41d8"] | ["H38a2", "H38b1", "H39a7", "H40a5", "H40c10", "H40c11", "H40d8", "H41b5", "H41d8"] | 成立 |
| H43d3 | 冻结读数越界计数 = 0 | 0 | 0 | 成立 |
| H43d4 | 累计 shot 序列单调不减 | {"length": 42, "min": 19, "max": 19} | non-decreasing | 成立 |
| H43d5 | 累计 shot 上限 <= 19 | 19 | 19 | 成立 |
| H43d6 | 带 ledger 的 summary 数 >= 37 | 42 | 37 | 成立 |
| H43d7 | 本轮 W43 各件 shots_this_week 全为 0 | {"week43_summaries": 5, "all_zero": true} | {"min_summaries": 3, "all_zero": true} | 成立 |
| H43d8 | 预注册文件生成前后 sha256 不变 | 1.0 | 1.0 | 成立 |

## 3 边界

- 只读：本件只解析 JSON，不写任何 summary、标签或特征列。
- 逐文件台账见 `probes/artifacts/w43_governance_ledger.csv`。
- 0 shot；四个冻结读数一个不动。
