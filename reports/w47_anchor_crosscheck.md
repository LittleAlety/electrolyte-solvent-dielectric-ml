# W47-A 计算锚点覆盖核算与氧化轴交叉一致性

只读 lane，0 shot。取件核实推翻了 W47 计划的 V1 归属：Borodin 2013 是纯氧化论文（无还原/EA 表），
Borodin 2015 给的是 Li+ 耦合**计算**还原，Moshkovich 2001 只有 PC 单溶剂。据此本件不执行还原主判据，
改交一张覆盖核算表与一条氧化轴小样本交叉一致性读数。

## 1 覆盖核算（核心集 7 溶剂）

| 轴 | 轨 | 成员 | 覆盖 |
| --- | --- | --- | --- |
| 氧化 | 计算 | EC / PC / EMC / SL | 4/7 |
| 氧化 | 实验（单溶剂行） | EC / PC / EMC / SL | 4/7 |
| 还原 | 计算 | EC | 1/7 |
| 还原 | 实验 | PC | 1/7 |

还原轨并集 = EC / PC（2 < 5）⇒ **H47a2 拒答分支触发**：H47a2：核心集还原锚点并集 2 < 5，主判据（D2 tau_b >= 0.9 或 Delta tau_b(D2-D0) CI 整体 > 0）不执行，降级为「不可判定 + 功效下限」，与 W33 ORCA 层先例同规格（不算失败）。

## 2 氧化轴计算-实验交叉一致性（敏感性读数，n = 4）

| 溶剂 | 计算 dGa(eps=20) | 实验 E_ox vs Li | 计算秩 | 实验秩 | 判据 |
| --- | --- | --- | --- | --- | --- |
| EC | 7.07 | 6.20 | 2 | 3 | criterion_primary_5mV_1mA_ref53 |
| PC | 7.01 | 6.60 | 3 | 2 | criterion_primary_5mV_1mA_ref53 |
| EMC | 7.17 | 6.70 | 1 | 1 | criterion_primary_5mV_1mA_ref53 |
| SL | 6.64 | 5.80 | 4 | 4 | criterion_secondary_2mV_0.5mA_ref57 |

- tau_b = **0.6667**；精确单侧 p = **0.1667**；bootstrap 95% CI = [-1.0000, 1.0000]。
- 未解析占比（z = 1.96，计算 -> 实验）= **0.3333**。
- Top-k 重叠：k=1 -> 1.00，k=2 -> 0.50。
- 敏感性列 tau_b：dEa_eps20_V 0.6667，dGa_eps1_V 0.3333，dEa_eps1_V 0.3333。
- 留一法：去 EC 1.0000，去 PC 1.0000，去 EMC 0.3333，去 SL 0.3333。
- 门禁过滤：W33 态合法性门禁按 InChIKey 在 gfn2/orca 层注册；本件转录表是外部 G4MP2 层、无 InChIKey，门禁过滤不适用（过滤前后同一集合），显式登记而非静默跳过。

## 3 功效下限（n = 4）

- MDE（80% 功效）= **0.9826**；精确拒绝率 = 0.041667。
- 功效：tau_true = 0.4 / 0.6 / 0.8 时 = 0.0556 / 0.0625 / 0.0833。
- 达到 80% 功效所需锚点数：tau_true = 0.6 -> 8；0.8 -> 6。

## 4 table_pins

| 表 | 行数 | sha256 命中 |
| --- | --- | --- |
| computed_oxidation | 16 | 是 |
| experimental_oxidation | 26 | 是 |
| computed_reduction_li_coupled | 8 | 是 |

## 5 判据

| id | 判据 | 值 | 阈 | 判决 |
| --- | --- | --- | --- | --- |
| H47a1 | 主判据（D2 tau_b >= 0.9 或 Delta tau_b(D2-D0) CI 整体 > 0）按 H47a2 不执行，登记为不可判定（不判否） | {"status": "not_executed", "reason": "H47a2：核心集还原锚点并集 2 < 5，主判据（D2 tau_b >= 0.9 或 Delta tau_b(D2-D0) CI 整体 > 0）不执行，降级为「不可判定 + 功效下限」，与 W33 ORCA 层先例同规格（不算失败）。"} | {"status": "not_executed"} | 成立 |
| H47a2 | 拒答分支条件：核心集还原锚点（计算+实验并集）< min_core_anchors = 5 | {"reduction_tracks_union": ["EC", "PC"], "reduction_union_size": 2, "min_core_anchors": 5} | {"reduction_union_size_lt": 5} | 成立 |
| H47a3 | 三件套同报（tau_b + Top-k 重叠 + 未解析占比 z=1.96），且门禁过滤前后各报一遍（本件过滤不适用，前后同一集合） | {"tau_b": 0.6666666666666669, "top_k": [{"k": 1, "computed_top": ["EMC"], "experimental_top": ["EMC"], "overlap_count": 1, "overlap": 1.0}, {"k": 2, "computed_top": ["EMC", "EC"], "experimental_top": ["EMC", "PC"], "overlap_count": 1, "overlap": 0.5}], "unresolved_share": 0.3333333333333333, "gate_filter": {"applicable": false, "registry_levels": ["gfn2", "orca"], "external_transcribed_levels": ["G4MP2", "G4MP2//LC-wPBE"], "n_before": 4, "n_removed": 0, "n_after": 4, "reason": "W33 态合法性门禁按 InChIKey 在 gfn2/orca 层注册；本件转录表是外部 G4MP2 层、无 InChIKey，门禁过滤不适用（过滤前后同一集合），显式登记而非静默跳过。"}} | {"triple": ["tau_b", "top_k", "unresolved_share"], "gate_before_after": "both"} | 成立 |
| H47a4 | 层级纪律：三张转录表层级声明齐备，跨层只作 rank_only（不得声明 same_level） | {"computed_oxidation": "cross_level_rank_only, not_same_level", "experimental_oxidation": "transcribed_as_tabulated__upstream_conversion_unaudited", "computed_reduction_li_coupled": "cross_level_rank_only, not_same_level"} | {"must_not_claim_same_level": true} | 成立 |
| H47a5 | 氧化轴计算-实验交叉一致性可复算：n = 4、精确单侧 p 与 tau_b 同报（禁止单独引用 tau_b） | {"n": 4, "pairs": 6, "tau_b": 0.6666666666666669, "exact_p_upper": 0.16666666666666666, "bootstrap": {"point": 0.6666666666666669, "draws": 10000, "valid": 9848, "invalid": 152, "mean": 0.6750812347684809, "sd": 0.5007524484463164, "lo": -1.0, "hi": 1.0}} | {"n": 4, "exact_p_required": true} | 成立 |
| H47a6 | 覆盖核算与预注册逐项一致（五张成员表全等） | {"computed_oxidation_members": true, "experimental_oxidation_single_solvent_members": true, "computed_reduction_members": true, "experimental_reduction_members": true, "reduction_tracks_union": true} | {"all_equal": true} | 成立 |
| H47a7 | table_pins：三张转录表行数 + sha256 与预注册逐位一致 | {"computed_oxidation": {"rows": 16, "sha256": "0c2809df482fa4e6ef44e194f9511ce99e62a5d8c86cc1586769d30b2b4fb86f"}, "experimental_oxidation": {"rows": 26, "sha256": "14e4978fb133594d03ac8b1f9fa4eb57487622b2791d7f1f4a8ae49d7c71b28b"}, "computed_reduction_li_coupled": {"rows": 8, "sha256": "5792c3f5376b303419a28d38a5303b6dd4d16e89ba6e4fbca21585b8d3961739"}} | {"rows_and_sha256": "all_match"} | 成立 |
| H47a8 | 功效下限同报（n = 4 的 MDE / 精确拒绝率 / 所需锚点数），与 taub_power 工具逐位一致 | {"n": 4, "mde": 0.982638888888889, "exact_rejection_rate": 0.041666666666666664, "power_at_tau_0.4": 0.05555555555555558, "power_at_tau_0.6": 0.06250000000000001, "power_at_tau_0.8": 0.0833333333333334, "required_n_tau_0.6": {"n_min": 8, "reachable": true, "n_max": 200}, "required_n_tau_0.8": {"n_min": 6, "reachable": true, "n_max": 200}} | {"n": 4, "mde_reported": true} | 成立 |
| H47a9 | 输入（预注册 + 三张转录表 + 合法性注册表）sha256 未变 | {"inputs_unchanged": true} | {"unchanged": true} | 成立 |

**结论**：还原轴实验/计算锚点并集仍 < 5，主判据不可判定；氧化轴 n = 4 交叉一致性 tau_b = 0.6667（精确 p = 0.1667）**只作敏感性读数，不进判决、不写进摘要级结论**。0 shot（累计仍 19）。
