# W47-D 投稿就绪评估与引用回填复核

只读治理 lane，0 shot。论文 v3 升 v1.11、新增 §3.32，并复跑 W44/W43 守卫。

## 1 引用登记（13/13）

| 引用 | 在位 |
| --- | --- |
| Moshkovich 2001 | 是 |
| Borodin 2013 | 是 |
| Borodin 2015 | 是 |
| Borodin 2019 | 是 |
| Mozhzhukhina 2017 | 是 |
| Murdock 2022 | 是 |
| Timerghazin 2008 | 是 |
| Gunasekaran 2025 | 是 |
| Liu 2026 | 是 |
| Chen 2026 | 是 |
| Vydrov 2006 | 是 |
| Deng 2026 | 是 |
| Abaei 2026 | 是 |

## 2 稿件形式闸门

- §3.32 在位 = 是；§1.2 定位段 = 是；§4.6 局限更新 = 是。
- 附录标题数 = 0；图片来源 25 个、缺失 0 个。

## 3 投稿就绪评估

| 闸门 | 通过 |
| --- | --- |
| citations_complete | 是 |
| section_3_32 | 是 |
| positioning_updated | 是 |
| limitations_updated | 是 |
| no_appendix | 是 |
| figures_all_exist | 是 |
| frozen_readings_intact | 是 |
| registered_negatives_intact | 是 |
| shot_cap_intact | 是 |
| boundaries_declared | 是 |

闸门 10/10 通过；裁决 = **conditional_go**（本件只出「条件可投、边界已声明」的评估；投稿决策不由本件作出。）

**剩余阻塞项（科学证据，非稿件形式）：**

- same_apparatus_experimental_reduction_anchors = 0（核心集实验还原覆盖 1/7）
- D2 的 r2SCAN-3c 版本未计算（pending_orca_compute，转 round-2）
- D3（ddCOSMO 垂直 EA）未计算（pending_orca_compute，转 round-2）
- Ue 1997 的还原侧是否含值未核实（pending_source_retrieval）
- strict same-level 独立源仍为 0（HOMO/LUMO 通道加权仍缺）

## 4 守卫复跑快照

- 闸门：负对照 3 全拒、运营性先验 1 全过闸、准入层 pubchemqc。
- 验收：扫 44 轮、fail 0。
- 静态守卫：文件 375、mutation 0、冻结读数写入 0。
- 台账：负结果并集 9、冻结读数越界 0、累计 shot 上限 19。

论文 sha256：「98973c79ea9734b00115437cea5c5784dfbdea48038b11b151bdb16f3e625fcc」（变化已在 W47-D 登记）。

## 5 判据

| id | 判据 | 值 | 阈 | 判决 |
| --- | --- | --- | --- | --- |
| H47d1 | 第二批引用 13 篇全部在参考文献节内逐条命中（作者 + 年份） | {"present": 13, "required": 13, "citations": {"Moshkovich 2001": true, "Borodin 2013": true, "Borodin 2015": true, "Borodin 2019": true, "Mozhzhukhina 2017": true, "Murdock 2022": true, "Timerghazin 2008": true, "Gunasekaran 2025": true, "Liu 2026": true, "Chen 2026": true, "Vydrov 2006": true, "Deng 2026": true, "Abaei 2026": true}} | {"required": 13} | 成立 |
| H47d2 | §3.32 在位，标题含 W47/还原锚点，正文含 不可判定/0.6667/H47a2/not_evaluable_condition_differs | {"section_present": true, "section_ok": true} | {"must_contain": ["不可判定", "0.6667", "H47a2", "not_evaluable_condition_differs"]} | 成立 |
| H47d3 | §1.2 定位段补 Abaei 2026 与 Deng 2026（跨领域同修辞） | {"positioning_ok": true} | {"must_contain": ["Abaei", "Deng"]} | 成立 |
| H47d4 | §4.6 照实登记未闭合项（还原锚点仍 0 / round-2） | {"limitations_ok": true} | {"groups": [["还原锚点", "还原轴的锚点"], ["round-2", "下周期"]]} | 成立 |
| H47d5 | 论文无附录标题（用户口径：不要附录） | {"appendix_headings": []} | {"headings": []} | 成立 |
| H47d6 | 论文引用的图片全部在盘（图片可完整显示的前置条件） | {"n_links": 25, "missing": []} | {"missing": []} | 成立 |
| H47d7 | 四个冻结读数字面值未被篡改（无变体） | {"variants": {"0.4091179943351143": ["0.4091179943351143"], "0.4766400383507876": ["0.4766400383507876"], "0.5861142332208197": ["0.5861142332208197"], "0.6216672295270079": ["0.6216672295270079"]}} | {"frozen_readings": [0.4091179943351143, 0.4766400383507876, 0.5861142332208197, 0.6216672295270079]} | 成立 |
| H47d8 | 9 条已登记负结果不变（台账并集 = 9） | {"registered_negatives": 9} | {"expected": 9} | 成立 |
| H47d9 | 累计 shot 上限仍 19（本周各件 0） | {"cumulative_shots_max": 19} | {"expected": 19} | 成立 |
| H47d10 | 未闭合边界声明齐备（README 第 33/36/40/42/45/46 条） | {"boundaries_declared": true, "items": ["33. **", "36. **", "40. **", "42. **", "45. **", "46. **"]} | {"items": ["33. **", "36. **", "40. **", "42. **", "45. **", "46. **"]} | 成立 |
| H47d11 | decisions_log §28.102 与 README §11 第 49–52 条登记 | {"decisions_log": true, "readme_items": true} | {"decisions": "28.102", "readme": [49, 50, 51, 52]} | 成立 |
| H47d12 | 投稿就绪评估：10 条闸门逐条判定 + 阻塞项清单 + 论文 sha256 记录 + 守卫复跑全绿 | {"readiness": {"gates": {"citations_complete": true, "section_3_32": true, "positioning_updated": true, "limitations_updated": true, "no_appendix": true, "figures_all_exist": true, "frozen_readings_intact": true, "registered_negatives_intact": true, "shot_cap_intact": true, "boundaries_declared": true}, "gates_passed": 10, "gates_total": 10, "all_gates_passed": true, "blocking_items": ["same_apparatus_experimental_reduction_anchors = 0（核心集实验还原覆盖 1/7）", "D2 的 r2SCAN-3c 版本未计算（pending_orca_compute，转 round-2）", "D3（ddCOSMO 垂直 EA）未计算（pending_orca_compute，转 round-2）", "Ue 1997 的还原侧是否含值未核实（pending_source_retrieval）", "strict same-level 独立源仍为 0（HOMO/LUMO 通道加权仍缺）"], "verdict": "conditional_go", "note": "本件只出「条件可投、边界已声明」的评估；投稿决策不由本件作出。"}, "guard": {"refused_controls": 3, "admitted_layers": ["pubchemqc"], "operational_prior_uses": 1, "operational_all_admitted": true, "acceptance_weeks": 44, "acceptance_failing": 0, "static_files": 375, "metric_name_mutations": 0, "frozen_reading_writes": 0, "unregistered_promotions": 0, "frozen_outside_canon": 0, "registered_negatives": 9, "cumulative_shots_max": 19}, "paper_sha256": "98973c79ea9734b00115437cea5c5784dfbdea48038b11b151bdb16f3e625fcc", "inputs_unchanged": true} | {"all_gates_passed": true, "refused_controls": 3, "mutations": 0, "frozen_writes": 0, "shots_max": 19} | 成立 |
