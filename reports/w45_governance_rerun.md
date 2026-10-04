# W45-D 三条治理守卫 + 台账的本轮复跑快照

只读治理 lane；0 shot。把 W44 接进机器的守卫在 W45 再跑一遍。

## 1 守卫读数

| guard | metric | value |
| --- | --- | --- |
| gate | refused_controls | 3 |
| gate | admitted_positive | admitted |
| gate | undeclared_prior_uses | 0 |
| gate | operational_prior_uses | 1 |
| acceptance | weeks_scanned | 42 |
| acceptance | declared_weeks | 34 |
| acceptance | failing_weeks | 0 |
| acceptance | recent_all_pass | True |
| static | files_scanned | 365 |
| static | parse_errors | 0 |
| static | metric_name_mutations | 0 |
| static | frozen_reading_writes | 0 |
| static | unregistered_promotions | 0 |
| ledger | summaries_scanned | 353 |
| ledger | registered_negatives | 9 |
| ledger | frozen_outside_canon | 0 |
| ledger | cumulative_shots_max | 19 |

- 本轮 W45 各件 shots： {"w45_calibration_audit_summary.json": 0, "w45_dipole_strata_summary.json": 0, "w45_governance_rerun_summary.json": 0, "w45_stratified_residual_summary.json": 0}。

## 2 判据

| 判据 | 描述 | 读数 | 阈值 | 结论 |
| --- | --- | --- | --- | --- |
| H45d1 | 准入闸门：3 个负对照被拒、PubChemQC 过闸、未申报 0、运营性全过闸 | {"refused": 3, "positive": {"pubchemqc": "admitted"}, "undeclared": 0, "operational_uses": 1, "operational_all_admitted": true} | {"refused": 3, "undeclared_max": 0} | 成立 |
| H45d2 | 逐轮验收：轮数 >= 40、fail 0、最近五轮全过、台账不变式成立 | {"weeks": 42, "declared": 34, "failing": 0, "recent_all_pass": true, "invariants_hold": true} | {"weeks_min": 40, "failing_max": 0} | 成立 |
| H45d3 | AST 静态守卫：文件 >= 350、解析错误 0、mutation 0、冻结读数写入 0、未登记晋升 0 | {"files": 365, "parse_errors": 0, "mutations": 0, "writes": 0, "promotions": 0} | {"files_min": 350} | 成立 |
| H45d4 | 台账：登记负结果并集 == 9、冻结读数越界 0、累计 shot 上限 19 | {"negatives": 9, "negatives_stable": true, "frozen_outside_canon": 0, "frozen_intact": true, "shots_max": 19} | {"negatives": 9, "shot_cap": 19} | 成立 |
| H45d5 | 交叉一致性：闸门判决表 == W43 准入表（xtb defer / qm9 defer / pubchemqc admit / batt reject） | {"xtb": "defer", "qm9": "defer", "pubchemqc": "admit", "batt": "reject"} | {"xtb": "defer", "qm9": "defer", "pubchemqc": "admit", "batt": "reject"} | 成立 |
| H45d6 | 本轮自检：W45 各件 shots_this_week 全为 0 | {"w45_calibration_audit_summary.json": 0, "w45_dipole_strata_summary.json": 0, "w45_governance_rerun_summary.json": 0, "w45_stratified_residual_summary.json": 0} | {"all_zero": true} | 成立 |
| H45d7 | 输入（W43/W44/W45 预注册 + 三条守卫探针）sha256 未变 | True | True | 成立 |

## 3 边界

- 只读：不写任何既有 summary，不重跑轮次导出。
- 早期轮次缺字段记为 not_declared，不算 fail；轮数随交付推进只增不减。
- 0 shot；四个冻结读数一个不动。
