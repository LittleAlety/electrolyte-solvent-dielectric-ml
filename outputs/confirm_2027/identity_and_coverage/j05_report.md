# B-G0-J05 身份冲突裁决与覆盖缺口登记

- 契约: `confirm_2027.identity_and_coverage/v1` / `confirm_2027.j05_inputs/v1`
- 本报告不含墙钟时间, 可由固定输入逐字节重建

## 1. 身份冲突裁决 (J05-A)

发现 **3** 个骨架各持多行, 共 **3** 条多余行。

| 骨架 | 行数 | 名称 | 处置 | 真冲突 | 完整键数 |
|---|---:|---|---|---|---:|
| `GAEKPEKOJKCEMS` | 2 | gamma-valerolactone | `SAME_COMPOUND_SOURCE_CONFLICT` | true | 1 |
| `KFUSEUYYWQURPO` | 2 | cis-1,2-Dichloroethylene;trans-1,2-Dichloroethylene | `STEREOISOMER_DISTINCT_COMPOUNDS` | false | 2 |
| `ZQDPJFUHLCOCRG` | 2 | cis-3-Hexene;trans-3-Hexene | `STEREOISOMER_DISTINCT_COMPOUNDS` | false | 2 |

**骨架连接风险**: J01-J05 按 InChIKey 首段骨架连接. 立体异构体会折叠到同一骨架, 因此骨架级计数对这类分子偏高. 本表列出全部受影响骨架及其处置.

### 逐条处置

| 骨架 | 值 | 规则 | 下游动作 |
|---|---|---|---|
| `GAEKPEKOJKCEMS` | T=298.15 ε=36.1;36.9 | 同一化合物、不同来源给出不同值; 属于真实未决冲突 | 人工裁决 (保留并列或选主); 在裁决前不得选出代表值 |
| `KFUSEUYYWQURPO` | T=298.15 ε=2.14;9.2 | 分别作为两个化合物保存; 禁止按骨架合并或平均 | 在按骨架连接的分析中必须显式排除这两个骨架, 或改用完整 InChIKey 连接 |
| `ZQDPJFUHLCOCRG` | T=298.15 ε=2;2.062 | 分别作为两个化合物保存; 禁止按骨架合并或平均 | 在按骨架连接的分析中必须显式排除这两个骨架, 或改用完整 InChIKey 连接 |

## 2. 覆盖缺口登记 (J05-B)

共有 **135** 条 v04 记录在观测层没有任何观测。

| 来源机制 | 行数 |
|---|---:|
| `NBS514_CIRCULAR_MANUAL_ENTRY` | 102 |
| `UNFLAGGED_NO_OBSERVATION` | 33 |

| 可修复性 | 行数 |
|---|---:|
| `NOT_EVALUATED_INGESTION_PATH_UNKNOWN` | 33 |
| `RECOVERABLE_NBS514_MANUAL_TRANSCRIPTION` | 102 |

**关键认知**: 绝大多数缺口不是'数据丢失', 而是**观测层承载范围**与 v04 录入路径不匹配: NBS514 人工转录行从设计上就不进观测层. 把这类缺口与真正的数据缺失混为一谈, 会高估'需要重新取数'的量并低估'已有材料可复核'的量

A18 受影响分子: 9 个 (C02, C04, C05, C06, C07, C09, C11, C12, C17)。

## 3. B02 工作单

| 序 | 轨道 | 编号 | 优先级 | 任务 | 目标 | 可否立即开始 |
|---:|---|---|---|---|---|---|
| 1 | A_STRUCTURE | B02-A1 | P0 | 人工准入签批 (R252) | 40 行候选池的人类质量审计 | true |
| 2 | A_STRUCTURE | B02-A2 | P0 | NBS514 人工转录行复核 | 102 行 | true |
| 3 | A_STRUCTURE | B02-A3 | P0 | 立体异构骨架连接修正 | 3 个骨架 / 3 条多余行 | true |
| 4 | A_STRUCTURE | B02-A4 | P0 | gamma-valerolactone 双行冲突裁决 | EPSV04-R227 (36.1) vs EPSV04-R248 (36.9) | true |
| 5 | B_EXTERNAL | B02-B1 | P0 | 九个零观测分子取数 | EC, PC, EMC, FEC, VC, DOL, EA, MA, TMP | true |
| 6 | B_EXTERNAL | B02-B2 | P1 | SN 室温带补证 | succinonitrile 293.15-303.15 K | true |
| 7 | B_EXTERNAL | B02-B3 | P1 | AN 静态频率补证 | acetonitrile 现有证据仅 0.01/1 MHz | true |
| 8 | B_EXTERNAL | B02-B4 | P2 | ThermoML 路径无观测行核查 | 0 行 | true |
| 9 | B_EXTERNAL | B02-B5 | P2 | 无标记无观测行路径追溯 | 33 行 | true |

### 逐项验收

| 编号 | 前置门 | 验收标准 |
|---|---|---|
| B02-A1 | NONE — 这是唯一能解锁 ACCEPT 的动作 | ACCEPT 行数 > 0, 且每行有 reviewer/date/decision |
| B02-A2 | none | 每行有 page-level 证据与复核人 |
| B02-A3 | B02-A1 (可并行) | 连接键改为完整 InChIKey, 且重跑后计数变化有说明 |
| B02-A4 | none | 有 conflict_status 终态与裁决理由 |
| B02-B1 | none — 不受结构修复阻塞 | 每分子至少一条可追溯观测或明确 NOT_FOUND 证书 |
| B02-B2 | none | 找到则升级室温候选; 找不到则保留 333.15 K 并记 NOT_FOUND |
| B02-B3 | none | 有 static 证据且来源冲突已裁决 |
| B02-B4 | none | 每行标注 XML 存在性与窗口外点位 |
| B02-B5 | none | 每行有录入路径结论或 NOT_EVALUATED 标记 |

## 4. 冻结输入

| 输入 | bytes | sha256 |
|---|---:|---|
| `a_core_set` | 3149 | `630b0ee8c09dc414` |
| `admission_gap` | 50040 | `597efaf8355483a9` |
| `candidate_master` | 72349 | `63b9ff45561c9a49` |
| `candidate_pool_C` | 9479 | `c50f9349ec6de434` |
| `dielectric_v04` | 134460 | `e046a3831630e36a` |
| `evidence_backfill` | 6178 | `7ef1502439b3422b` |
| `observations_v11plus` | 921601 | `159b928f800a5596` |
| `s4_preview` | 4923 | `cb57ab59fb0f2d9f` |
| `target_protocol` | 13420 | `0e848eb6fd8619f8` |

## 5. 不做的事

- 不为立体异构体选择代表行, 不合并或平均它们的值
- 不把「观测层没有」写成「观测为 0」或「值不存在」
- 不修改 v04 / gap / pool_C / backfill / v11plus
- 不改变 J01-J04 的冻结产物

