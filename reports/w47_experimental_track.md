# W47-B 实验还原轨候选逐件裁定

只读 lane，0 shot。取件核实后 Moshkovich 2001 降级为**机理证据**（PC 单溶剂、无溶剂 x 盐表），
实验还原轨核心集覆盖 1/7 < 5 ⇒ 登记 `not_evaluable_condition_differs`；计算系列一律不得当实验锚点。

## 1 逐件台账（9 件）

| id | 源 | 轴 | verdict | condition_flag |
| --- | --- | --- | --- | --- |
| moshkovich2001 | Moshkovich, Gofer & Aurbach 2001 | reduction | mechanism_evidence_only | CONDITION_DIFFERS_LI_DEPOSITION |
| ue1997 | Ue 1997 | oxidation | anchor_candidate_pending_source | CONDITION_MATCH_UNVERIFIED |
| okoshi2015 | Okoshi 2015 | oxidation | not_available_on_disk | CONDITION_MATCH_UNVERIFIED |
| ue1994 | Ue 1994 | oxidation | not_available_on_disk | CONDITION_MATCH_UNVERIFIED |
| borodin2013_table1 | Borodin, Behl & Jow 2013 Table 1 | oxidation | rejected_computed_only | NOT_APPLICABLE_SINGLE_SOLVENT |
| borodin2013_table3 | Borodin, Behl & Jow 2013 Table 3 | oxidation | rejected_criterion_mismatch | NOT_APPLICABLE_SINGLE_SOLVENT |
| borodin2015_fig6_7_8 | Borodin et al. 2015 fig. 6/7/8 | reduction | rejected_computed_only | NOT_APPLICABLE_SINGLE_SOLVENT |
| borodin2019_conversion | Borodin et al. 2019 | reduction | rejected_computed_only | NOT_APPLICABLE_SINGLE_SOLVENT |
| doe_apr_fy2016 | DOE APR FY2016 secondary values | reduction | not_available_on_disk | CONDITION_MATCH_UNVERIFIED |

## 2 覆盖与裁决

- 核心集实验还原成员：PC（1/7）；min_core_anchors = 5。
- 实验轨裁决 = **not_evaluable_condition_differs**；只作 D2 的敏感性检验对象，不作 Gate 1 替换。
- 不可得件：okoshi2015，ue1994，doe_apr_fy2016；计算件（不得当锚点）：borodin2013_table1，borodin2015_fig6_7_8，borodin2019_conversion。
- 开项：Ue1997_reduction_side -> pending_source_retrieval。

## 3 判据

| id | 判据 | 值 | 阈 | 判决 |
| --- | --- | --- | --- | --- |
| H47b1 | 实验轨台账逐件给出 verdict，且每行 condition_flag 非空 | {"n_items": 9, "missing": []} | {"missing": []} | 成立 |
| H47b2 | Moshkovich 2001 重分类为 mechanism_evidence_only（PC 单溶剂，非锚点行） | {"sensitivity_only_object": "moshkovich2001", "verdict": ["mechanism_evidence_only"]} | {"verdict": "mechanism_evidence_only"} | 成立 |
| H47b3 | 核心集实验还原覆盖 1/7 < 5 ⇒ 实验轨登记 not_evaluable_condition_differs | {"experimental_reduction_members": ["PC"], "min_core_anchors": 5, "experimental_track_verdict": "not_evaluable_condition_differs"} | {"verdict": "not_evaluable_condition_differs"} | 成立 |
| H47b4 | 空结果/不可得件逐件登记（not_available_on_disk 至少 1 件） | {"not_available_items": ["okoshi2015", "ue1994", "doe_apr_fy2016"]} | {"min_items": 1} | 成立 |
| H47b5 | Ue1997_reduction_side 开项登记为 pending_source_retrieval | {"id": "Ue1997_reduction_side", "description": "Ue 1997 (JES 144, 2684) 是否含还原侧需取原件核实；取件优先级最高。", "status": "pending_source_retrieval"} | {"status": "pending_source_retrieval"} | 成立 |
| H47b6 | verdict 与 condition_flag 取值都落在预注册词汇表内（封闭） | {"verdicts": ["anchor_candidate_pending_source", "mechanism_evidence_only", "not_available_on_disk", "rejected_computed_only", "rejected_criterion_mismatch"], "flags": ["CONDITION_DIFFERS_LI_DEPOSITION", "CONDITION_MATCH_UNVERIFIED", "NOT_APPLICABLE_SINGLE_SOLVENT"]} | {"vocabularies_closed": true} | 成立 |
| H47b7 | 计算系列一律 rejected_computed_only（不得当实验锚点） | {"rejected_computed_only_items": ["borodin2013_table1", "borodin2015_fig6_7_8", "borodin2019_conversion"]} | {"min_items": 2} | 成立 |
| H47b8 | 输入（预注册 + 取件裁决报告 + Lane A 预注册）sha256 未变 | {"inputs_unchanged": true} | {"unchanged": true} | 成立 |
