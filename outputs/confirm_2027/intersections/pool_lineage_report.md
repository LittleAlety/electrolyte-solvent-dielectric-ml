# B-G0-J02B master.in_49_preview 与 candidate_pool_C 版本溯源

- 契约: `confirm_2027.pool_lineage/v1` / `confirm_2027.j02b_inputs/v1`
- 本报告不含墙钟时间, 可由固定输入逐字节重建

## 1. 裁决

**`PREVIEW_IS_HISTORICAL_PRESERVE_AND_KEEP_POOL_C_AUTHORITATIVE`**

| 字段 | 值 |
|---|---|
| preview 定性 | `LEGACY_OR_UNRESOLVED_PREVIEW` |
| pool_C 定性 | `CURRENT_AUTHORITATIVE_OPERATIONAL_POOL` |
| 是否禁止合并 | True |
| 下一步 | 保留 preview 历史版本, pool_C 继续作为当前权威操作池; 不重出 joint_eligibility |

判据: 
- 两个层的上游输入不同: preview 源自 S4 折角色表, pool_C 源自 evidence_backfill
- pool_C 生成器完全不读预览表, 因此不存在'池更新未回写预览'的链路
- 两池互不嵌套 (preview_only=26, pool_c_only=26), 排除了'一个是另一个的子集'的解释

合并被禁止的原因: 并集会把两套不同筛选规则混成既非预览也非正式池的第三物, 并伪造更大的分母。

## 2. 成员差异

| 项 | 数量 |
|---|---:|
| `n_preview` | 49 |
| `n_pool_c` | 49 |
| `n_common` | 23 |
| `n_preview_only` | 26 |
| `n_pool_c_only` | 26 |
| `n_union` | 75 |
| 集合关系 | `neither_subset` |

## 3. 生成链溯源

| 层 | 生成器 | 上游输入 | 语义 | 准入规则 | 授予批准 |
|---|---|---|---|---|---|
| `candidate_pool_C` | `tools/build_candidate_pool_R001.py` | `reports/evidence_backfill_R001.csv` | candidate pool built from RESOLVED mechanical evidence | backfill.status == "RESOLVED" and not REJECT and no salt token | no (decision_v2=CANDIDATE, never ACCEPT) |
| `master_49_preview` | `tools/candidate_master_R001.py` | `drafts/artifacts/s4_fold_DRAFT_INDICATIVE_R293.csv` | S4 fold role assignment (holdout/train/validation), not a candidate pool | none (role table carries no admission decision) | no |

### 源码级证据

| 检查 | 状态 | 说明 |
|---|---|---|
| `master_in_49_preview_upstream_is_s4_preview` | PASS | candidate_master_R001.py 用 S4_PREVIEW = s4_fold_DRAFT_INDICATIVE_R293.csv 派生 in_49_preview |
| `candidate_pool_C_upstream_is_evidence_backfill` | PASS | build_candidate_pool_R001.py 以 backfill[m]["status"] == "RESOLVED" 作为池 C 成员条件 |
| `candidate_pool_C_does_not_read_preview` | PASS | build_candidate_pool_R001.py 完全不引用 S4 预览表, 因此不存在'pool_C 更新后未回写 preview' 的链路 |
| `evidence_backfill_requires_explicit_measurement_list` | PASS | evidence_backfill_R001.py 要求外部显式提供 measurement_id 列表 (--measurements required=True); 名单本身的出处不在代码里, 属下游可复现性的已知缺口 |

## 4. 两层各自规模

| 层 | 行 | 唯一骨架 |
|---|---:|---:|
| `candidate_pool_C` | 49 | 49 |
| `evidence_backfill` | 49 | 49 |
| `master_49_preview` | 49 | 49 |
| `s4_preview_source` | 49 | 49 |

## 5. 只允许两个裁决

| 核查结果 | 后续动作 |
|---|---|
| preview 是历史预览 | 保留历史版本, pool_C 继续作为当前权威池 |
| preview 本应反映当前 pool_C | 修复上游回写, 建立新版本并重新运行联合资格审计 |

本轮不修改 B-G0-J01 的冻结产物; 若裁决要求重跑, 必须在新版本池上重跑而不是覆盖。

## 6. 冻结输入

| 输入 | bytes | sha256 |
|---|---:|---|
| `a_core_set` | 3149 | `630b0ee8c09dc414` |
| `admission_gap` | 50040 | `597efaf8355483a9` |
| `admission_matrix` | 51830 | `0b50c54dba7d259b` |
| `backfill_script` | 5116 | `645efd34d55f58c3` |
| `candidate_master` | 72349 | `63b9ff45561c9a49` |
| `candidate_pool_B` | 4482 | `e2f18d4fd09b2ba9` |
| `candidate_pool_C` | 9479 | `c50f9349ec6de434` |
| `evidence_backfill` | 6178 | `7ef1502439b3422b` |
| `master_script` | 10513 | `c911972d658cf454` |
| `pool_c_diff` | 9664 | `0eb6bb8313c93b41` |
| `pool_c_v2` | 6907 | `32e1bea54f938f9c` |
| `pool_script` | 4569 | `84c6744078b4be80` |
| `s4_preview` | 4923 | `cb57ab59fb0f2d9f` |
| `target_protocol` | 13420 | `0e848eb6fd8619f8` |

