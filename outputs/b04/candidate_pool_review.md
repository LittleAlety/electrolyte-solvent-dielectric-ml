# B04 候选池 v2 审议
> 生成器 `build_candidate_pool_v2/1.0.0` · 2026-11-24T02:22:35Z

## 一、结论
- 候选池记录数：**22**
- 涉及分子数：**22**
- 每分子记录数：**1**
- 未入选的审计记录：**226**

### ⚠️ 22 条不是数据集
22 个分子、每分子 1 条记录. 这是**筛选可行性集**, 不是训练集. B05 必须以此为前提设计实验, 不得宣称统计功效充分.

按冻结规则 primary_k = max(1, ceil(n/10)) = ceil(22/10) = 3. 但 B07 必须报告这 22 个分子是否有足够独立来源做聚类检验.

## 二、三道独立的准入门
| 门 | 来源 | 要求 | 通过数 |
|---|---|---|---:|
| B02 四智能体 | `consensus_decisions.csv` | `AI_CONSENSUS_ACCEPTED` | 22 |
| v06 模型可用 | `dataset_v06_model_ready.csv` | `model_ready == true` | 73 |
| 无未解决阻断 | `dataset_v06_exclusions.csv` | 未被排除 | 73 |

**交集：22**

## 三、未入选原因分布
| 原因 | 数量 |
|---|---:|
| `NO_CONTRIBUTING_MEASUREMENT;PAIR_NOT_VALID` | 123 |
| `MODEL_READY_NOT_REVIEWED` | 43 |
| `NO_CONTRIBUTING_MEASUREMENT;PAIR_NOT_VALID;TEMPERATURE_IMPUTED` | 22 |
| `SYNTHETIC_PAIR;PAIR_NOT_VALID` | 11 |
| `PRESSURE_HETEROGENEOUS;PAIR_NOT_VALID;CONFLICT_UNRESOLVED` | 9 |
| `MODEL_READY_BUT_NOT_UNANIMOUS` | 8 |
| `PRESSURE_HETEROGENEOUS;CONFLICT_UNRESOLVED` | 4 |
| `PRESSURE_HETEROGENEOUS;PAIR_NOT_VALID` | 2 |
| `CONFLICT_UNRESOLVED` | 1 |
| `CONFLICT_UNRESOLVED;PAIR_NOT_VALID;NO_CONTRIBUTING_MEASUREMENT` | 1 |
| `NO_CONTRIBUTING_MEASUREMENT;PAIR_NOT_VALID;OUTSIDE_ROOM_BAND` | 1 |
| `PAIR_NOT_VALID;OUTSIDE_ROOM_BAND` | 1 |

## 四、温度词表
- 池内温度原始值：293.15, 298, 298.15, 298.2, 300.15, 303.15
- 闭区间 [293.15, 303.15] K 内：**22** 条
- 区间外：**0** 条

293.15 与 303.15 本身计入区间 (闭区间), 与 R219 冻结窗口口径一致.

## 五、冻结产物状态
| 产物 | 状态 |
|---|---|
| `candidate_pool_C` | **权威历史版本，字节未动** |
| `master.in_49_preview` | **历史 S4 折，merge_forbidden 继续有效** |
| J01 / J02 / J03 | **字节不变，已由校验器确认** |

## 六、明确未做的事
- ✅ 所有新增行必须有 measurement_id 与来源 DOI
- ✅ 所有温度原始值保留, 未折算
- ✅ 未为扩大样本数降低准入标准
- ✅ 未合并 master.in_49_preview (merge_forbidden 继续有效)
- ✅ 未覆盖 candidate_pool_C
- ❌ 未把 22 条称为「训练集」
- ❌ 未宣称统计功效充分
- ❌ 未把 AI 共识写入 HUMAN_SIGNED
