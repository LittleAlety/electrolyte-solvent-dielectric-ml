# W41-C 例外登记表准入规则（三类理由的机械守卫）

**性质**：后验 / 治理件，**0 shot（累计仍 19）**。不改任何 owner 字节，只按源码证据分类。

## 1. 准入规则

| 类别 | 机械证据 |
| --- | --- |
| `pinned_bytes` | 理由文本命中 {钉死, 冻结, 摘要, summary, prereg, manifest, 依赖件, 引用, 历史记录, 比对} 之一 |
| `append_log` | owner 源码含追加模式 `open(..., "a")` |
| `strict_json` | owner 源码含 `allow_nan=False` |

三条策略规则（写进 `probes/artifacts/w41_exemption_policy.json`）：

1. 新增例外必须落在三类理由之内（pinned_bytes / append_log / strict_json），新类别要先改本预注册再登记。
2. 被冻结点名的脚本若要改字节，先走『解冻 / 更正』流程，不得默默改。
3. 例外件重跑仍会弄脏工作树，必须继续作为已知代价报出，不得计入迁移完成率。

## 2. 计数与更正

| 类别 | 机械证据计数 | W40 手写分组 |
| --- | ---: | ---: |
| pinned_bytes | 16 | 16 |
| append_log | 4 | 3 |
| strict_json | 3 | 3 |

**更正**：v1 按 W40 手写分组预登记 16/3/3 并把 pubchem_liquid_window_harvest 当作唯一 (a)(b) 重叠；机械证据复核（本预注册的 evidence_rules）发现 pubchem_identity_layer.py 同时有追加写站点（line 702）与被依赖件摘要钉死，真重叠是它；pubchem_liquid_window_harvest 只有追加写证据。v2 更正为 16/4/3、重叠 1、distinct 22。

## 3. 判定

| 判据 | 说明 | 读数 | 门槛 | 判定 |
| --- | --- | ---: | ---: | --- |
| H41c1 | 例外登记共 22 个 owner | 22 | 22 | 成立 |
| H41c2 | 机械证据下 pinned_bytes 计数 = 16 | 16 | 16 | 成立 |
| H41c3 | 机械证据下 append_log 计数 = 4（更正 W40 手写分组的 3） | 4 | 4 | 成立 |
| H41c4 | 机械证据下 strict_json 计数 = 3 | 3 | 3 | 成立 |
| H41c5 | pinned ∩ append 重叠只有 1 个且是 pubchem_identity_layer.py | 1 | 1 | 成立 |
| H41c6 | 每个 owner 至少落进一条理由类别（没有无理由例外） | 22 | 22 | 成立 |
| H41c7 | 没有任何被登记 owner 含 write_json_stable（反向漏网 = 0） | 0 | 0 | 成立 |
| H41c8 | 每条例外理由非空（>= 6 字符） | 35 | 6 | 成立 |
| H41c9 | 三类准入规则写进策略件（3 条） | 3 | 3 | 成立 |
| H41c10 | W40 探针字节前后一致（登记表来源未被改写） | 1 | 1 | 成立 |

## 4. 边界

- 例外登记**不是豁免**：这 22 个 owner 重跑仍会弄脏工作树，是明确保留的已知代价。
- 机械证据只证明「理由可归入三类且 owner 确不含稳定写入」，**不**证明这些站点不能迁移以外的任何事。
- `pinned_bytes` 的关键词匹配是文本级证据；它给出的是准入判据，不是对钉死链的完整证明。
- 0 shot；四个冻结读数一个不动。
