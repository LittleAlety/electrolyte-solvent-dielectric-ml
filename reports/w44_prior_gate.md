# W44-A 层准入闸门 + 全仓消费者审计（治理 lane，0 shot）

把 W43-C 的层准入表升成**会抛异常**的闸门 `admit_prior()`，并对全仓消费者做机械审计。

## 1 闸门规则

- `admit_prior(layer, use)`：层未登记 ⇒ 抛 `PriorRefused`；verdict != admit ⇒ 抛 `PriorRefused`。
- 判决表：{"xtb": "defer", "qm9": "defer", "pubchemqc": "admit", "batt": "reject"}。

## 2 负对照与正对照

| 层 | 角色 | 闸门结果 |
| --- | --- | --- |
| ccsd_t | 负对照 | refused |
| qm9 | 负对照 | refused |
| batt | 负对照 | refused |
| pubchemqc | 正对照 | admitted |

## 3 消费者审计

- 扫描 611 个 *.py / *.md；命中 (文件 x 层) 对 18 个。
- 运营性先验使用（文件里出现 `admit_prior"LAYER"`）：1 个。
- 未申报的先验使用：0 个。

| 消费者 | 层 | 类别 | 闸门 |
| --- | --- | --- | --- |
| probes/w44_prior_gate.py | pubchemqc | operational_prior | admitted |
| probes/export_week41_results.py | batt | declaration_only | not_applicable |
| probes/export_week43_results.py | pubchemqc | declaration_only | not_applicable |
| probes/export_week44_results.py | pubchemqc | declaration_only | not_applicable |
| probes/w41_orbital_level_declaration.py | batt | declaration_only | not_applicable |
| probes/w41_orbital_level_declaration.py | qm9 | declaration_only | not_applicable |
| probes/w43_prior_admission.py | batt | declaration_only | not_applicable |
| probes/w43_prior_admission.py | pubchemqc | declaration_only | not_applicable |
| probes/w43_prior_admission.py | xtb | declaration_only | not_applicable |
| probes/w44_prior_gate.py | batt | declaration_only | not_applicable |
| probes/w44_prior_gate.py | qm9 | declaration_only | not_applicable |
| probes/w44_prior_gate.py | xtb | declaration_only | not_applicable |
| reports/decisions_log.md | batt | declaration_only | not_applicable |
| reports/decisions_log.md | pubchemqc | declaration_only | not_applicable |
| reports/decisions_log.md | qm9 | declaration_only | not_applicable |
| reports/decisions_log.md | xtb | declaration_only | not_applicable |
| reports/week41_delivery_readme.md | batt | declaration_only | not_applicable |
| reports/week41_project_charter.md | batt | declaration_only | not_applicable |

## 4 判据

| 判据 | 描述 | 读数 | 阈值 | 结论 |
| --- | --- | --- | --- | --- |
| H44a1 | 扫描到的 *.py / *.md 文件数 >= 300 | 611 | 300 | 成立 |
| H44a2 | 准入表判决为 pubchemqc admit、其余 defer/reject | {"xtb": "defer", "qm9": "defer", "pubchemqc": "admit", "batt": "reject"} | {"pubchemqc": "admit"} | 成立 |
| H44a3 | 三个负对照全部被拒 | ["ccsd_t", "qm9", "batt"] | [{"layer": "ccsd_t", "why": "从未登记的新层级"}, {"layer": "qm9", "why": "verdict = defer"}, {"layer": "batt", "why": "标签目标层，恒 reject"}] | 成立 |
| H44a4 | 正对照 pubchemqc 过闸 | {"pubchemqc": "admitted"} | {"pubchemqc": "admitted"} | 成立 |
| H44a5 | 运营性先验使用全部过闸（无 refused） | {"probes/w44_prior_gate.py": "admitted"} | all admitted | 成立 |
| H44a6 | 未申报的先验使用数 <= 0 | [] | <= 0 | 成立 |
| H44a7 | 声明表覆盖全部扫描到的 (文件 x 层) 对 | {"declared": 18, "scanned_pairs": 18} | declared >= scanned | 成立 |
| H44a8 | 输入文件生成前后 sha256 不变 | 1.0 | 1.0 | 成立 |

## 5 边界

- 只读：闸门只查表、不写标签、不改 summary。
- 当前唯一的运营性先验使用是正对照 pubchemqc（已过闸）；闸门的价值是**下一次有人要用时必须先过它**。
- 0 shot；四个冻结读数一个不动。
