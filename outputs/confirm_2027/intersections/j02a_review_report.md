# B-G0-J02A DME/TEGDME/GBL/DMSO 候选行排除原因复核

- 契约: `confirm_2027.candidate_exclusion/v1` / `confirm_2027.j02a_inputs/v1`
- 本报告不含墙钟时间, 可由固定输入逐字节重建
- 复核对象: 4 个分子 (DMSO, TEGDME, DME, GBL)

## 1. 三值裁决结果

| 裁决 | 数量 |
|---|---:|
| `INTENTIONAL_EXCLUSION` | 0 |
| `CANDIDATE_CONSTRUCTION_MISSING` | 0 |
| `REQUIRES_HUMAN_REVIEW` | 4 |

**只有 `CANDIDATE_CONSTRUCTION_MISSING` 允许启动 pool_C_v2 候选行补建。** 补建候选行不产生任何 ACCEPT 标签, 也不改变 `primary_k` 门槛。

## 2. 逐分子结论

| mol | 名称 | 观测 | v11 idx 温度 | 协议温带 | in pool_C | preview | backfill | 裁决 | 可否补建 v2 |
|---|---|---|---:|---|---:|---:|---|---|---|
| C15 | DMSO | EPSV04-R031 | 298 | room_temperature | false | true | NOT_IN_LIST | `REQUIRES_HUMAN_REVIEW` | false |
| C10 | TEGDME | EPSV04-R099 | 298.15 | room_temperature | false | true | NOT_IN_LIST | `REQUIRES_HUMAN_REVIEW` | false |
| C08 | DME | EPSV04-R085 | 298.15 | room_temperature | false | false | NOT_IN_LIST | `REQUIRES_HUMAN_REVIEW` | false |
| C13 | GBL | EPSV04-R086 | 293.15 | room_temperature | false | false | NOT_IN_LIST | `REQUIRES_HUMAN_REVIEW` | false |

## 3. 逐观测证据

| mol | 观测 | 来源 | T_K | 带(v11) | 带(协议) | 相态 | 频率 | 压强 | 机械原因 | 裁决 |
|---|---|---|---:|---|---|---|---|---|---|---|
| C15 | EPSV04-R031 | 10.1016/j.fluid.2013.12.014 | 298 | room_temperature | room_temperature | LIQUID | STATIC_0HZ | PRESENT | false | `REQUIRES_HUMAN_REVIEW` |
| C10 | EPSV04-R099 | 10.1016/j.jct.2010.09.008 | 298.15 | room_temperature | room_temperature | LIQUID | STATIC_0HZ | PRESENT | false | `REQUIRES_HUMAN_REVIEW` |
| C08 | EPSV04-R085 | 10.1016/j.jct.2008.09.006 | 298.15 | room_temperature | room_temperature | LIQUID | STATIC_0HZ | PRESENT | false | `REQUIRES_HUMAN_REVIEW` |
| C13 | EPSV04-R086 | 10.1021/je900503p | 293.15 | room_temperature | room_temperature | LIQUID | STATIC_0HZ | PRESENT | false | `REQUIRES_HUMAN_REVIEW` |

## 4. 排除原因逐条

| mol | 名称 | 原因码 | 说明 |
|---|---|---|---|
| C15 | DMSO | `EPSILON_TOLERANCE_OVERFLOW` | gap 记录 epsilon 与源数据值不是一个数 (转录/取舍差异) |
| C15 | DMSO | `GAP_EPSILON_IS_CROSS_SOURCE_AGGREGATE` | gap 的 epsilon 是多个来源在室温带内的中位数, 不是任何单条观测值; 归属不可辨识 |
| C15 | DMSO | `MEASUREMENT_NOT_IN_DECLARED_LIST` | 该 measurement 不在 backfill 的显式测量名单里, 从来没有进入候选资格链 |
| C15 | DMSO | `MULTI_SOURCE_ROW_WITH_UNRESOLVED_ATTRIBUTION` | 该行汇总了多个来源, 但单条候选行无法声明自己归属哪一个来源 |
| C10 | TEGDME | `EPSILON_TOLERANCE_OVERFLOW` | gap 记录 epsilon 与源数据值不是一个数 (转录/取舍差异) |
| C10 | TEGDME | `GAP_EPSILON_IS_CROSS_SOURCE_AGGREGATE` | gap 的 epsilon 是多个来源在室温带内的中位数, 不是任何单条观测值; 归属不可辨识 |
| C10 | TEGDME | `MEASUREMENT_NOT_IN_DECLARED_LIST` | 该 measurement 不在 backfill 的显式测量名单里, 从来没有进入候选资格链 |
| C10 | TEGDME | `MULTI_SOURCE_ROW_WITH_UNRESOLVED_ATTRIBUTION` | 该行汇总了多个来源, 但单条候选行无法声明自己归属哪一个来源 |
| C08 | DME | `EPSILON_TOLERANCE_OVERFLOW` | gap 记录 epsilon 与源数据值不是一个数 (转录/取舍差异) |
| C08 | DME | `GAP_SOURCE_PROVENANCE_UNDOCUMENTED` | 该 measurement 的聚合口径标为 NOT_DOCUMENTED |
| C08 | DME | `MEASUREMENT_NOT_IN_DECLARED_LIST` | 该 measurement 不在 backfill 的显式测量名单里, 从来没有进入候选资格链 |
| C13 | GBL | `EPSILON_TOLERANCE_OVERFLOW` | gap 记录 epsilon 与源数据值不是一个数 (转录/取舍差异) |
| C13 | GBL | `GAP_EPSILON_IS_WITHIN_SOURCE_BAND_MEDIAN` | gap 的 epsilon 是同一来源在带内多条记录的中位数, 温度点已被中位化 |
| C13 | GBL | `MEASUREMENT_NOT_IN_DECLARED_LIST` | 该 measurement 不在 backfill 的显式测量名单里, 从来没有进入候选资格链 |
| C13 | GBL | `TEMPERATURE_TOLERANCE_OVERFLOW` | gap 记录温度在源数据里没有精确对应温度点 |

## 5. 冻结输入

| 输入 | bytes | sha256 |
|---|---:|---|
| `a_core_set` | 3149 | `630b0ee8c09dc414` |
| `admission_gap` | 50040 | `597efaf8355483a9` |
| `build_candidate_pool` | 4569 | `84c6744078b4be80` |
| `candidate_master` | 72349 | `63b9ff45561c9a49` |
| `candidate_pool_C` | 9479 | `c50f9349ec6de434` |
| `dielectric_v04` | 134460 | `e046a3831630e36a` |
| `evidence_backfill` | 6178 | `7ef1502439b3422b` |
| `evidence_backfill_script` | 5116 | `645efd34d55f58c3` |
| `formal_draft` | 6312 | `d2bfea53546f6197` |
| `observations_v11` | 638159 | `7803587afabdec1f` |
| `observations_v11plus` | 921601 | `159b928f800a5596` |
| `s4_preview` | 4923 | `cb57ab59fb0f2d9f` |
| `target_protocol` | 13420 | `0e848eb6fd8619f8` |
| `worksheet_40` | 14056 | `2346b707c46e8204` |

## 6. 明确不做的事

- 不写 `candidate_pool_C_R001.csv`, 不写 `evidence_backfill_R001.csv`, 不改 gap 表
- 不生成 pool_C_v2 (是否补建由人工依据本表裁决)
- 不把补建候选行当作已获得合格标签
- 不合并 v11 与 v11plus 的口径差异
- 不修改 B-G0-J01 的任何冻结产物

