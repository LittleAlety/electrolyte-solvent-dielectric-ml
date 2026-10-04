# W46-D 论文回填与治理同步

只读治理 lane，0 shot。论文 v3 升 v1.10、§3.31 落地，并复跑 W44/W43 守卫。

## 1 引用登记（7 篇）

| 引用 | 在位 |
| --- | --- |
| Korth 2014 | 是 |
| Rathnakumaran 2026 | 是 |
| Li 2026 | 是 |
| Gao 2023 | 是 |
| Wang 2023 | 是 |
| Ou 2025 | 是 |
| Bai/Hou 2025 | 是 |

## 2 Gate 1 措辞三处修订

- 阈 0.9 操作特性进局限：在位
- P0 0.5238 vs P1 0.4286 不声称优劣：在位
- p = 0.1194 两解释并列：在位

## 3 守卫复跑快照

- 闸门：负对照 3 全拒、运营性先验 1 全过闸。
- 验收：扫 43 轮、fail 0。
- 静态守卫：文件 370、mutation 0、冻结读数写入 0。
- 台账：负结果并集 9、冻结读数越界 0、累计 shot 上限 19。

论文 sha256：「648d68ffd091c33a5f214a0dff2b156be284cfaa73c112e2fb6e4fcece2fb6a1」（变化已在 W46-D 登记）。

## 4 判据

| id | 判据 | 值 | 阈 | 判决 |
| --- | --- | --- | --- | --- |
| H46d1 | 7 篇新增引用全部在参考文献节内（作者 + 年份逐条命中） | {"citations": {"Korth 2014": true, "Rathnakumaran 2026": true, "Li 2026": true, "Gao 2023": true, "Wang 2023": true, "Ou 2025": true, "Bai/Hou 2025": true}} | {"required": ["Korth 2014 PCCP 16 7919", "Rathnakumaran 2026 JPCB", "Li 2026 J Cheminform", "Gao 2023 JACS", "Wang 2023 AFM", "Ou 2025 npj Comput Mater", "Bai/Hou 2025 Chem Rev"]} | 成立 |
| H46d2 | §1.2 T1/T2 定位段在位，创新点收窄为「纪律 + 判据 + 拒答」，且无未否定的「首次用秩相关」表述 | {"t1t2_paragraph": true, "novelty_narrowed": true, "first_rank_claim_unnegated": false} | {"novelty": "纪律 + 判据 + 拒答"} | 成立 |
| H46d3 | Gate 1 统计措辞三处修订全部在位 | {"wording": {"阈 0.9 操作特性进局限": true, "P0 0.5238 vs P1 0.4286 不声称优劣": true, "p = 0.1194 两解释并列": true}} | {"count": 3} | 成立 |
| H46d4 | §3.31「还原轴描述符重定义与功效边界」在位，且同时含「不可判定」与功效下限读数 | {"section_present": true} | {"must_contain": ["不可判定", "MDE = 0.6541"]} | 成立 |
| H46d5 | decisions_log 追加 §28.101（Week 46） | {"decisions_log": true} | {"section": "28.101"} | 成立 |
| H46d6 | README §11 登记本轮四条 lane（第 45–48 条） | {"readme_items": true} | {"items": [45, 46, 47, 48]} | 成立 |
| H46d7 | 论文 sha256 记录 + 四个冻结读数字面值未被篡改（无变体） | {"paper_sha256": "648d68ffd091c33a5f214a0dff2b156be284cfaa73c112e2fb6e4fcece2fb6a1", "frozen_variants": {"0.4091179943351143": ["0.4091179943351143"], "0.4766400383507876": ["0.4766400383507876"], "0.5861142332208197": ["0.5861142332208197"], "0.6216672295270079": ["0.6216672295270079"]}} | {"frozen_readings": [0.4091179943351143, 0.4766400383507876, 0.5861142332208197, 0.6216672295270079]} | 成立 |
| H46d8 | W44-A/B/D 三条守卫 + W43-D 台账本轮回跑：负对照全拒、mutation 0、冻结读数写入 0、shot 上限 19 | {"gate": {"refused_controls": 3, "admitted_layers": ["pubchemqc"], "operational_prior_uses": 1, "operational_all_admitted": true}, "acceptance": {"weeks_scanned": 43, "failing_weeks": 0}, "static": {"files_scanned": 370, "metric_name_mutations": 0, "frozen_reading_writes": 0, "unregistered_promotions": 0}, "ledger": {"registered_negatives": 9, "frozen_outside_canon": 0, "cumulative_shots_max": 19}, "inputs_unchanged": true} | {"refused_controls": 3, "mutations": 0, "frozen_writes": 0, "shots_max": 19} | 成立 |
