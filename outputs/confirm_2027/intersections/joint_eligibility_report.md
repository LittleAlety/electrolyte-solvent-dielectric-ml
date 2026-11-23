# B-G0-J01 A18 x B 共同候选资格审计与证据缺口登记

- 契约版本: `B-G0-J01` / `confirm_2027.joint_eligibility/v1` / `confirm_2027.joint_inputs/v1`
- 连接单位: `neutral_parent_inchikey_skeleton` (只连中性母体; Li 配合物与带电态不参与)
- 本报告不含墙钟时间, 可由固定输入逐字节重建 (见 `joint_rebuild_receipt.json`)

## 1. 结论

**`NO_GO_INSUFFICIENT_ELIGIBLE_DATA`** — 仅限确认性联合 Top-k / regret / 联合模型对比; 逐分子处置与证据缺口登记仍照常报告

| 分母 | 值 |
|---|---:|
| `n_a_core_neutral_parents` | 18 |
| `n_identity_common_in_candidate_master` | 18 |
| `n_condition_resolvable` | 4 |
| `n_room_band_qualified` | 3 |
| `n_admitted` | 0 |
| `n_dual_or_more_independent_sources_in_qualified_pool` | 0 |
| `n_cluster_ge3_independent_sources_in_qualified_pool` | 0 |
| `primary_k_under_frozen_rule` | 1 |
| `n_required_for_primary_k_ge_3` | 21 |

本轮没有生成任何联合性能指标 (字段 `confirmatory_metrics_emitted` 为空); 分子级排序只能作为描述性处置, 不得当作确认性结论。

## 2. 输入与冻结

- B 仓 HEAD: `7c58a22f516d602ee495973cda51731c070e986c` (tag `v1.3` = `5aa315169f22f3adb8d88365cd1bcfa763b4e0d6`, 已跟踪文件改动 0, 领先 origin/main 5 个提交)
- v56 版本记录: `electrolyte-ml v5.6 standalone` (生成器 `tools/build_from_prior_repo.py`, files=6618, rewritten_files=18), MANIFEST sha256 `ec289e3dcd39b8af`

| 输入 | 角色 | bytes | sha256 |
|---|---|---:|---|
| `a_core_set` | A 仓 18 个中性母体 (只读连接对象) | 3149 | `630b0ee8c09dc414` |
| `b_dielectric_v04` | B 仓 248 行介电主表 (审计基准) | 134460 | `e046a3831630e36a` |
| `b_observations_v11plus` | B 仓 v11 逐条观测层 (T/相态/频率/压强/来源) | 921601 | `159b928f800a5596` |
| `v56_admission_gap` | v56 248 行 admission 缺口表 (measurement_decision) | 50040 | `597efaf8355483a9` |
| `v56_candidate_master` | v56 248 行候选主表 (含 in_49_preview 标记) | 72349 | `63b9ff45561c9a49` |
| `v56_candidate_pool_b` | v56 高置信池 24 行 | 4482 | `e2f18d4fd09b2ba9` |
| `v56_candidate_pool_c` | v56 池 C 49 行 (逐行 epsilon/evidence_group_id/decision_v2) | 9479 | `c50f9349ec6de434` |
| `v56_formal_decision_draft` | v56 20 行 A1..A12 逐门草案 | 6312 | `d2bfea53546f6197` |
| `v56_human_audit_worksheet` | v56 40 行机器审计/人类签批工作表 | 14056 | `2346b707c46e8204` |
| `v56_manifest` | v56 独立包版本记录 (逐文件 sha256 账本) | 2556541 | `ec289e3dcd39b8af` |
| `v56_primary_k_adoption` | v56 primary_k 采用声明 (FROZEN) | 541 | `c44d83583f38ba02` |
| `v56_round_r007` | v56 Round R007 记录 (纠正/缺口/人类审计状态) | 6455 | `3a223479ab4d6687` |
| `v56_target_protocol` | v56 冻结协议 (门定义/温窗/never-default 规则) | 13420 | `0e848eb6fd8619f8` |
| `v56_three_questions_r001` | v56 三问结论 (ACCEPT=0 的权威陈述) | 6423 | `95bd6ed86668821c` |

### 已登记的不一致 (记录, 不修复)

| 检查 | 状态 | 说明 |
|---|---|---|
| `gap_to_v04_row_mapping` | PASS | problems=0, passed=248/248 |
| `dielectric_v04_mirror` | PASS | main=e046a3831630e36a mirror=e046a3831630e36a |
| `observations_v11plus_mirror` | PASS | main=159b928f800a5596 mirror=159b928f800a5596 |
| `master_in_49_preview_vs_candidate_pool_c` | DISAGREEMENT_RECORDED | master.in_49_preview=yes 有 49 个骨架, candidate_pool_C 有 49 个骨架; 26 个只在 preview, 26 个只在 pool_C — 两者不是同一套 49 池 |
| `worksheet_40_not_subset_of_pool_c` | DISAGREEMENT_RECORDED | human_audit_worksheet_R007 (40 行) 有 9 个骨架 不在 pool_C — 候选层是相互重叠的子集, 不是嵌套结构 |

## 3. 分层交集

| 层 | 行 | 唯一骨架 | A18 命中 |
|---|---:|---:|---:|
| `candidate_master` | 248 | 245 | 18 |
| `formal_draft_20` | 20 | 20 | 1 |
| `master_49_preview` | 49 | 49 | 5 |
| `pool_b` | 24 | 24 | 1 |
| `pool_c` | 49 | 49 | 4 |
| `v11_observation_layer` | 2065 | 153 | 9 |
| `worksheet_40` | 40 | 40 | 4 |

## 4. 七维裁决

注: 本表按 A 全部 18 个母体统计; 第 1 节 `denominators` 里的来源稳健性计数只在**已可解析池** (4 个) 上算 —— 两者分母不同, 不可互相替代。

| 维度 | 判据 | 通过 | 合计 | 未通过分子 |
|---|---|---:|---:|---|
| `identity` | A 母体在 B 主表中身份命中 | 18 | 18 | — |
| `source` | 至少一条可追溯来源 (DOI 或来源文件) | 9 | 18 | C02,C04,C05,C06,C07,C09,C11,C12,C17 |
| `temperature` | 存在室温带 (293.15-303.15 K) 观测或候选行 | 8 | 18 | C02,C04,C05,C06,C07,C09,C11,C12,C17,C18 |
| `phase` | v11 逐行相态证据均为液体 | 9 | 18 | C02,C04,C05,C06,C07,C09,C11,C12,C17 |
| `frequency` | 存在 static/zero-frequency 逐行证据 | 8 | 18 | C02,C04,C05,C06,C07,C09,C11,C12,C16,C17 |
| `human_admission` | 存在显式 ACCEPT 签批 | 0 | 18 | C01,C02,C03,C04,C05,C06,C07,C08,C09,C10,C11,C12,C13,C14,C15,C16,C17,C18 |
| `independent_source_count_ge2` | 独立来源组 >= 2 | 4 | 18 | C01,C02,C03,C04,C05,C06,C07,C09,C11,C12,C13,C14,C17,C18 |
| `independent_source_count_ge3` | 独立来源组 >= 3 (来源簇检验下限) | 1 | 18 | C01,C02,C03,C04,C05,C06,C07,C08,C09,C10,C11,C12,C13,C14,C16,C17,C18 |

## 5. 逐分子结果

| mol | 名称 | 候选层 | v11观测 | 室温 | 来源组 | 频段 | 温带(候选或v04) | 裁决 |
|---|---|---|---:|---:|---:|---|---|---|
| C01 | DMC | candidate_master;formal_draft_20;pool_b;pool_c;worksheet_40 | 5 | 1 | 1 | STATIC_ZERO_HZ_EVIDENCED | room_temperature | CONDITION_QUALIFIED_ADMISSION_PENDING |
| C02 | EMC | candidate_master | 0 | 0 | 0 | NOT_EVALUATED | room_temperature | IDENTITY_ONLY_NO_CONDITION_OBSERVATION |
| C03 | DEC | candidate_master;pool_c;worksheet_40 | 5 | 1 | 1 | STATIC_ZERO_HZ_EVIDENCED | room_temperature | CONDITION_QUALIFIED_ADMISSION_PENDING |
| C04 | EC | candidate_master | 0 | 0 | 0 | NOT_EVALUATED | extended_temperature | IDENTITY_ONLY_NO_CONDITION_OBSERVATION |
| C05 | PC | candidate_master | 0 | 0 | 0 | NOT_EVALUATED | room_temperature | IDENTITY_ONLY_NO_CONDITION_OBSERVATION |
| C06 | FEC | candidate_master | 0 | 0 | 0 | NOT_EVALUATED | room_temperature | IDENTITY_ONLY_NO_CONDITION_OBSERVATION |
| C07 | VC | candidate_master | 0 | 0 | 0 | NOT_EVALUATED | room_temperature | IDENTITY_ONLY_NO_CONDITION_OBSERVATION |
| C08 | DME | candidate_master | 9 | 2 | 2 | STATIC_ZERO_HZ_EVIDENCED | room_temperature | OBSERVATION_READY_NOT_IN_CANDIDATE_POOL |
| C09 | DOL | candidate_master | 0 | 0 | 0 | NOT_EVALUATED | room_temperature | IDENTITY_ONLY_NO_CONDITION_OBSERVATION |
| C10 | TEGDME | candidate_master | 6 | 4 | 2 | STATIC_ZERO_HZ_EVIDENCED | room_temperature | OBSERVATION_READY_NOT_IN_CANDIDATE_POOL |
| C11 | EA | candidate_master | 0 | 0 | 0 | NOT_EVALUATED | room_temperature | IDENTITY_ONLY_NO_CONDITION_OBSERVATION |
| C12 | MA | candidate_master | 0 | 0 | 0 | NOT_EVALUATED | room_temperature | IDENTITY_ONLY_NO_CONDITION_OBSERVATION |
| C13 | GBL | candidate_master | 5 | 4 | 1 | STATIC_ZERO_HZ_EVIDENCED | room_temperature | OBSERVATION_READY_NOT_IN_CANDIDATE_POOL |
| C14 | SL | candidate_master;pool_c;worksheet_40 | 8 | 3 | 1 | STATIC_ZERO_HZ_EVIDENCED | room_temperature | CONDITION_QUALIFIED_ADMISSION_PENDING |
| C15 | DMSO | candidate_master | 105 | 35 | 4 | STATIC_ZERO_HZ_EVIDENCED | room_temperature | OBSERVATION_READY_NOT_IN_CANDIDATE_POOL |
| C16 | AN | candidate_master | 10 | 3 | 2 | RF_ONLY | room_temperature | OBSERVATION_READY_NOT_IN_CANDIDATE_POOL |
| C17 | TMP | candidate_master | 0 | 0 | 0 | NOT_EVALUATED | room_temperature | IDENTITY_ONLY_NO_CONDITION_OBSERVATION |
| C18 | SN | candidate_master;pool_c;worksheet_40 | 17 | 0 | 1 | STATIC_ZERO_HZ_EVIDENCED | high_temperature | CONDITION_QUALIFIED_OFF_ROOM_BAND |

## 6. 三类点名缺口

这三组互不重叠, 加起来覆盖 A18 的全部未合格分子; 报告顺序即处置顺序。

### 6.1 零观测分子 (需要取数)

判定: 身份命中但 v11 观测层 0 条; 计数 **9**。

| mol | 名称 | v04 已登记来源 | v04 T_K | v04 温带 |
|---|---|---|---:|---|
| C02 | EMC | 10.1002/smll.202504276 | 298.15 | room_temperature |
| C04 | EC | 10.1021/je050341y | 313.15 | extended_temperature |
| C05 | PC | 10.1021/j100702a008 | 298.15 | room_temperature |
| C06 | FEC | 10.1016/S0022-1139(02)00317-2 | 296.15 | room_temperature |
| C07 | VC | 10.1039/j29660000005 | 298 | room_temperature |
| C09 | DOL | 10.1016/j.isci.2026.115778 | 298.15 | room_temperature |
| C11 | EA | 10.6028/nbs.circ.514 | 298.15 | room_temperature |
| C12 | MA | 10.6028/nbs.circ.514 | 298.15 | room_temperature |
| C17 | TMP | 10.1016/j.isci.2026.115778 | 298.15 | room_temperature |

### 6.2 已有观测但未取得资格的分子 (证据在, 候选行不在)

判定: 有 v11 观测但不属于任何带证据裁决的候选层; 计数 **5**。

| mol | 名称 | v11观测 | 室温 | 来源组 | 频段 | 相态 | 对齐 | 阻断原因 |
|---|---|---:|---:|---:|---|---|---|---|
| C08 | DME | 9 | 2 | 2 | STATIC_ZERO_HZ_EVIDENCED | LIQUID_EVIDENCED_IN_V11 | ALIGNED | OBSERVATION_READY_NOT_IN_CANDIDATE_POOL |
| C10 | TEGDME | 6 | 4 | 2 | STATIC_ZERO_HZ_EVIDENCED | LIQUID_EVIDENCED_IN_V11 | ALIGNED | OBSERVATION_READY_NOT_IN_CANDIDATE_POOL |
| C13 | GBL | 5 | 4 | 1 | STATIC_ZERO_HZ_EVIDENCED | LIQUID_EVIDENCED_IN_V11 | ALIGNED | OBSERVATION_READY_NOT_IN_CANDIDATE_POOL |
| C15 | DMSO | 105 | 35 | 4 | STATIC_ZERO_HZ_EVIDENCED | LIQUID_EVIDENCED_IN_V11 | ALIGNED | OBSERVATION_READY_NOT_IN_CANDIDATE_POOL |
| C16 | AN | 10 | 3 | 2 | RF_ONLY | LIQUID_EVIDENCED_IN_V11 | SOURCE_CONFLICT | OBSERVATION_READY_NOT_IN_CANDIDATE_POOL |

### 6.3 温带外已可解析 (只差室温证据)

判定: 属于候选层但候选行温度全部在室温带之外; 计数 **1**。

## 7. 温带记录 (不在室温带的已可解析候选)

| mol | 名称 | 候选 T_K | 候选温带 |
|---|---|---|---|
| C18 | SN | 333.15 | high_temperature |

这些行保留原始温度, 不折算到室温, 也不因不在室温带而被删除。

## 8. 来源回填优先级

| 序 | mol | 名称 | 层 | 动作 | 当前阻断 | 目标来源 |
|---:|---|---|---|---|---|---|
| 1 | C01 | DMC | `P0_HUMAN_SIGNATURE_ONLY` | `SIGN_ADMISSION` | EVIDENCE_GROUP_GATE_A9_FAILED;HUMAN_QUALITY_GATE_A11_FAILED;HUMAN_SIGNATURE_PENDING;IDENTITY_FULL_KEY_MATCH;ROOM_BAND_OBSERVATION_PRESENT;SINGLE_INDEPENDENT_SOURCE;STATIC_FREQUENCY_EVIDENCED | 10.1016/j.jct.2008.02.015 |
| 2 | C03 | DEC | `P0_HUMAN_SIGNATURE_ONLY` | `SIGN_ADMISSION` | HUMAN_SIGNATURE_PENDING;IDENTITY_FULL_KEY_MATCH;ROOM_BAND_OBSERVATION_PRESENT;SINGLE_INDEPENDENT_SOURCE;STATIC_FREQUENCY_EVIDENCED | 10.1016/j.jct.2008.02.015 |
| 3 | C14 | SL | `P0_HUMAN_SIGNATURE_ONLY` | `SIGN_ADMISSION` | HUMAN_SIGNATURE_PENDING;IDENTITY_FULL_KEY_MATCH;ROOM_BAND_OBSERVATION_PRESENT;SINGLE_INDEPENDENT_SOURCE;STATIC_FREQUENCY_EVIDENCED | 10.1016/j.tca.2012.10.004 |
| 4 | C08 | DME | `P1_ADMISSION_ROW_CONSTRUCTION` | `CONSTRUCT_ADMISSION_ROW_FROM_V11` | DUAL_INDEPENDENT_SOURCE;IDENTITY_FULL_KEY_MATCH;NOT_IN_ANY_CANDIDATE_POOL;ROOM_BAND_OBSERVATION_PRESENT;STATIC_FREQUENCY_EVIDENCED | 10.1016/j.jct.2008.09.006;10.1016/j.jct.2010.09.008 |
| 5 | C10 | TEGDME | `P1_ADMISSION_ROW_CONSTRUCTION` | `CONSTRUCT_ADMISSION_ROW_FROM_V11` | DUAL_INDEPENDENT_SOURCE;IDENTITY_FULL_KEY_MATCH;NOT_IN_ANY_CANDIDATE_POOL;ROOM_BAND_OBSERVATION_PRESENT;STATIC_FREQUENCY_EVIDENCED | 10.1016/j.jct.2010.09.008;10.1016/j.tca.2012.10.024 |
| 6 | C13 | GBL | `P1_ADMISSION_ROW_CONSTRUCTION` | `CONSTRUCT_ADMISSION_ROW_FROM_V11` | IDENTITY_FULL_KEY_MATCH;NOT_IN_ANY_CANDIDATE_POOL;ROOM_BAND_OBSERVATION_PRESENT;SINGLE_INDEPENDENT_SOURCE;STATIC_FREQUENCY_EVIDENCED | 10.1021/je900503p |
| 7 | C15 | DMSO | `P1_ADMISSION_ROW_CONSTRUCTION` | `CONSTRUCT_ADMISSION_ROW_FROM_V11` | CLUSTER_GE3_INDEPENDENT_SOURCE;IDENTITY_FULL_KEY_MATCH;NOT_IN_ANY_CANDIDATE_POOL;ROOM_BAND_OBSERVATION_PRESENT;STATIC_FREQUENCY_EVIDENCED | 10.1016/j.fluid.2013.12.014;10.1016/j.tca.2017.03.018;10.1021/je400149j;10.1021/je9010773 |
| 8 | C18 | SN | `P2_ROOM_BAND_EVIDENCE` | `FIND_ROOM_BAND_MEASUREMENT` | CANDIDATE_OFF_ROOM_BAND;HUMAN_SIGNATURE_PENDING;IDENTITY_FULL_KEY_MATCH;NO_ROOM_BAND_OBSERVATION;SINGLE_INDEPENDENT_SOURCE;STATIC_FREQUENCY_EVIDENCED | 10.1021/je300958c |
| 9 | C16 | AN | `P3_STATIC_FREQUENCY_EVIDENCE` | `FIND_STATIC_FREQUENCY_EVIDENCE` | DUAL_INDEPENDENT_SOURCE;IDENTITY_FULL_KEY_MATCH;NOT_IN_ANY_CANDIDATE_POOL;RF_FREQUENCY_ONLY;ROOM_BAND_OBSERVATION_PRESENT;SOURCE_CONFLICT_V04_VS_V11 | 10.6028/nbs.circ.514 |
| 10 | C11 | EA | `P4_SOURCE_RETRIEVAL` | `RETRIEVE_SOURCE_ROW` | IDENTITY_FULL_KEY_MATCH;NOT_IN_ANY_CANDIDATE_POOL;NO_V11_OBSERVATION | 10.6028/nbs.circ.514 |
| 11 | C12 | MA | `P4_SOURCE_RETRIEVAL` | `RETRIEVE_SOURCE_ROW` | IDENTITY_FULL_KEY_MATCH;NOT_IN_ANY_CANDIDATE_POOL;NO_V11_OBSERVATION | 10.6028/nbs.circ.514 |
| 12 | C02 | EMC | `P4_SOURCE_RETRIEVAL` | `RETRIEVE_SOURCE_ROW` | IDENTITY_FULL_KEY_MATCH;NOT_IN_ANY_CANDIDATE_POOL;NO_V11_OBSERVATION | 10.1002/smll.202504276 |
| 13 | C04 | EC | `P4_SOURCE_RETRIEVAL` | `RETRIEVE_SOURCE_ROW` | IDENTITY_FULL_KEY_MATCH;NOT_IN_ANY_CANDIDATE_POOL;NO_V11_OBSERVATION | 10.1021/je050341y |
| 14 | C05 | PC | `P4_SOURCE_RETRIEVAL` | `RETRIEVE_SOURCE_ROW` | IDENTITY_FULL_KEY_MATCH;NOT_IN_ANY_CANDIDATE_POOL;NO_V11_OBSERVATION | 10.1021/j100702a008 |
| 15 | C06 | FEC | `P4_SOURCE_RETRIEVAL` | `RETRIEVE_SOURCE_ROW` | IDENTITY_FULL_KEY_MATCH;NOT_IN_ANY_CANDIDATE_POOL;NO_V11_OBSERVATION | 10.1016/S0022-1139(02)00317-2 |
| 16 | C07 | VC | `P4_SOURCE_RETRIEVAL` | `RETRIEVE_SOURCE_ROW` | IDENTITY_FULL_KEY_MATCH;NOT_IN_ANY_CANDIDATE_POOL;NO_V11_OBSERVATION | 10.1039/j29660000005 |
| 17 | C09 | DOL | `P4_SOURCE_RETRIEVAL` | `RETRIEVE_SOURCE_ROW` | IDENTITY_FULL_KEY_MATCH;NOT_IN_ANY_CANDIDATE_POOL;NO_V11_OBSERVATION | 10.1016/j.isci.2026.115778 |
| 18 | C17 | TMP | `P4_SOURCE_RETRIEVAL` | `RETRIEVE_SOURCE_ROW` | IDENTITY_FULL_KEY_MATCH;NOT_IN_ANY_CANDIDATE_POOL;NO_V11_OBSERVATION | 10.1016/j.isci.2026.115778 |

## 9. 重开条件

| id | 条件 | 当前 | 目标 | 状态 |
|---|---|---|---|---|
| R1 | 联合室温带合格并签批的分子数 >= 21, 使 primary_k = max(1, ceil(n/10)) >= 3 | 0 | 21 | OPEN |
| R2 | 新证据进入确认分析之前, 资格标准与统计方案已冻结并预注册 | criteria_sha256=0906bf7898e1756a; target_protocol.status=DRAFT_PENDING_HUMAN_APPROVAL, frozen=False | protocol 由 DRAFT_PENDING_HUMAN_APPROVAL 转为人工批准版本 + 预注册件 | OPEN |
| R3 | 任何来源簇/聚类稳健性主张要求所报分组内独立来源组 >= 3 | 0 | 3 | OPEN |
| R4 | 输入 SHA256 与契约版本一并显式升级, 并重建本目录 | confirm_2027.joint_inputs/v1 | 新 input contract 版本 + 新 joint_inputs_manifest.json | OPEN |

资格标准快照: `joint_eligibility_criteria.json` (freeze_state = `NOT_FROZEN`; sha256 `0906bf7898e1756a`)。新证据可以重评 GO, 但必须先冻结该文件与统计方案。

## 10. 未评估与不授权项

- `a_side_redox_pair_eligible`: not_evaluated
- `joint_topk`: not_evaluated
- `joint_regret`: not_evaluated
- `joint_cluster_robustness`: not_evaluated
- `source_license_redistribution_scope`: not_evaluated

- 本轮不修改 v1.3 冻结产物, 不执行人类 admission 签批, 不新增 ORCA/DFT 计算, 不执行 git push。

## 11. 重建

```
python scripts/confirm_2027/build_joint_eligibility.py --check
```

相同输入下重建产物逐字节一致; 输入 SHA256 或契约版本变化时本工具以非零退出码拒绝出数。

