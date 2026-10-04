# W46-B 还原轴同装置锚点系列侦察与准入

只读侦察 lane，0 shot。把「有多少还原锚点可用」落成台账，而不是一句「源不存在」。

## 1 扫描分母

- 扫描 CSV 文件：518 个（data / reports / probes / docs）。
- 候选列（词元族命中）：151 列；命名对照件：32 件；台账行合计：190。

## 2 层准入（admit_prior，未登记 = 不准入）

| 层 | 登记判决 | 闸门 |
| --- | --- | --- |
| batt | reject | refused |
| qm9 | defer | refused |
| pubchemqc | admit | admitted |
| xtb | defer | refused |
| ccsd_t | unregistered | refused |
| exp_anchor | unregistered | refused |

## 3 候选列裁定（按层汇总）

| 层 | 候选列数 | 代表文件 | verdict |
| --- | --- | --- | --- |
| batt | 2 | data/processed/redox_merged.csv | rejected_computed_only |
| xtb | 149 | data/processed/four_core_key_registry.csv | rejected_computed_only |

## 4 收口：Lane A 判否分支

- 可用同装置还原锚点数 n_anchors = **0**（阈 5）。
- n_pairs_effective = C(n_anchors, 2) = **0**。
- ⇒ H46a2 拒答分支**触发**：是。Lane A 主判据不执行，产出自动降级为「不可判定 + Lane C 功效下限」。

## 5 判据

| id | 判据 | 值 | 阈 | 判决 |
| --- | --- | --- | --- | --- |
| H46b1 | 扫描分母可复算：扫了盘上 CSV 文件数、候选列数、命名对照数 | {"scanned_files": 518, "candidate_columns": 151, "named_controls": 32} | {"roots": ["data", "reports", "probes", "docs"], "tier_min": 1} | 成立 |
| H46b2 | 逐件有结论：候选行每行都带非空 verdict | {"candidate_rows": 183, "unjudged": 0} | {"per_item_verdict_required": true} | 成立 |
| H46b3 | verdict 全部落在预注册词表内 | {"distinct": ["rejected_computed_only", "rejected_criterion_mismatch"]} | {"vocabulary": ["hit_interactive_anchor", "rejected_license", "rejected_criterion_mismatch", "rejected_rig_mismatch", "rejected_computed_only", "not_available_on_disk", "environment_blocked"]} | 成立 |
| H46b4 | 计算系列（batt / qm9 / pubchemqc / xtb 层）一律判 rejected_computed_only | {"computed_rows": 181} | {"rule": "计算系列只作对照"} | 成立 |
| H46b5 | 实验件（exp_anchor 层）判 rejected_criterion_mismatch（判据不同，非还原电位） | {"exp_anchor_rows": 2} | {"rule": "实验锚点件均非还原电位"} | 成立 |
| H46b6 | 层准入：六个考察层逐一有判决，未登记层被 PriorRefused，仅 pubchemqc 过闸 | {"layers": {"batt": "refused", "qm9": "refused", "pubchemqc": "admitted", "xtb": "refused", "ccsd_t": "refused", "exp_anchor": "refused"}} | {"admitted_layers": ["pubchemqc"]} | 成立 |
| H46b7 | 空结果也登记：至少一条 not_available_on_disk（还原锚点系列盘上不可得） | {"not_available_on_disk": 1} | {"empty_result_registered_requires_not_available": true} | 成立 |
| H46b8 | 锚点不足触发 H46a2 拒答分支：n_anchors < min_anchors_for_lane_a | {"n_anchors": 0, "min_anchors_for_lane_a": 5} | {"n_pairs_threshold": 10} | 成立 |
| H46b9 | n_pairs_effective = C(n_anchors, 2)（公式逐位成立） | {"n_anchors": 0, "n_pairs_effective": 0} | {"formula": "n_pairs_effective = C(n_anchors, 2)"} | 成立 |
| H46b10 | 输入（Lane B 预注册 + W44 闸门 + W43 准入表）sha256 未变 | true | true | 成立 |

> 说明：admit_prior 管的是**排序先验**准入（W43/W44 口径）；本表用同一闸门复核「还原锚点层」是否可进主检验。被拒不是因为许可，而是因为**没有同装置实验锚点落盘**（计算系列只作对照）。
