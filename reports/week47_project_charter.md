# Week 47 立项章：双轨还原锚点、主判据执行与投稿就绪评估

**日期**：2026-10-04
**上一轮**：W46（还原轴描述符重定义 / 同装置锚点侦察 / τ_b 功效工具化 + 论文回填；README §11 第 45–48 条登记）
**本轮范围**：W46 登记三处缺口（D2 的 r2SCAN-3c 版本、D3 的 ddCOSMO 垂直 EA、同装置还原锚点 ≥ 5），W47 计划原打算用「Borodin 2013 的 G4MP2 EA 表」当计算锚点直接执行主判据。**取件核实推翻了这个前提**：该表实为其 ref51（Vydrov 2006，G2 离子测试集，58 个 EA，无电解液溶剂）的内容，Borodin 2013 是纯氧化论文。于是本轮改成四条**只读转录/治理** lane：**A** 覆盖核算 + 氧化轴交叉一致性、**B** 实验轨逐件台账、**C** D2/D3 协议冻结与算力欠账、**D** 引用回填 + §3.32 + 投稿就绪评估。
**shot 账本**：**本轮 0 shot，累计仍 19**。四条 lane 全是只读转录、交叉核对与治理件，不拟合主记分牌臂、不新增特征列、不改 `METRIC_NAMES`。
**四个冻结读数**：`0.4091179943351143` / `0.4766400383507876` / `0.5861142332208197` / `0.6216672295270079`，本轮**一个都不动**。

---

## 1. 为什么这一轮的重点是「把源读对」

W46 的收口句是「还原轴需要重新定义」。要把它推进成「已重定义并通过检验」，需要一条**同协议的锚点系列**。计划把它们寄在 Borodin 2013 上；取件后发现三处误判：

1. **Borodin 2013 是纯氧化论文**（Table 1 计算氧化 16 行、Table 3 实验氧化 26 行、Table 2 阴离子氧化），**全文无还原/EA 表**；所谓「68 EA + 86 IP」是 ref51（Vydrov & Van Voorhis 2006，**58 个 EA**，G2 离子测试集）。
2. **Moshkovich 2001 是 PC 单溶剂**（Li/Na/K 高氯酸盐、Au 电极），窗口值在 CV 图里、无溶剂×盐表 ⇒ 不能当锚点行。
3. **Borodin 2015 图 6/7/8 是 Li⁺ 耦合的计算还原**（给 D2 定义性先例），不是实验锚点。

所以本轮把重点从「新增算力」改成「把源读对、把覆盖算清、把拒答写实」——**还原锚点缺口填不上，是必须照实交付的负向结论**。

| lane | 回答 | 登记来源 |
| --- | --- | --- |
| W47-A 覆盖核算 + 氧化轴交叉一致性 | 核心集 7 溶剂上四条轨各覆盖多少；氧化轴计算-实验是否一致（敏感性） | W47 计划 §2 / 取件裁决 V1/V2 |
| W47-B 实验轨逐件台账 | 每条实验还原候选为何能/不能当锚点 | W47 计划 §3 |
| W47-C D2/D3 协议冻结 | 需要什么口径、缺多少机时 | W46 登记的算力缺口 |
| W47-D 引用回填 + 投稿就绪评估 | 稿件形式是否到位、还差什么（科学 vs 形式） | W47 计划 §5 / V6 |

## 2. 四条 lane 的判据与读数

| lane | 关键读数 | 判据 |
| --- | --- | --- |
| **W47-A** 覆盖 + 交叉一致性 | 计算氧化 4/7、实验氧化 4/7、计算还原 1/7、实验还原 1/7 ⇒ 并集 **2 < 5**，H47a2 触发、主判据不可判定；氧化轴 n = 4：τ_b **0.6667**、精确 p **0.1667**、Top-1 **1.00** / Top-2 **0.50**、未解析 **0.3333**（敏感性列 ε=1 降到 **0.3333**）；n = 4 功效下限 MDE **0.9826**、精确拒绝率 **0.04167** | **H47a1–H47a9：9 成立** |
| **W47-B** 实验轨台账 | Moshkovich 2001 ⇒ `mechanism_evidence_only`；9 件台账全有 verdict + 非空 `condition_flag`；实验轨 **`not_evaluable_condition_differs`**；`Ue1997_reduction_side` 仍待取原件 | **H47b1–H47b8：8 成立** |
| **W47-C** 协议冻结 | D2 六项 + D3 四项 + 腈类 3×3 = 9 行齐备；`orca_available = false` ⇒ 全部 `pending_orca_compute`；排期估算 **76** 个单点；`dipole_transfer_v1` 维持 `registered_not_authorized` | **H47c1–H47c9：9 成立** |
| **W47-D** 论文与治理 | 引用 **13/13** 在位；§3.32 在位；§1.2 补 Abaei/Deng 2026；§4.6 局限更新；**无附录标题**、25 张图全在盘；投稿就绪闸门 **10/10**（裁决 `conditional_go`）；守卫复跑全绿 | **H47d1–H47d12：12 成立** |

## 3. 本轮不做的事

- 不用任何计算系列（Borodin 2013 Table 1 / Borodin 2015 图 6–8 / 2019 换算）补造实验还原锚点。
- 不把 n = 4 的氧化轴交叉一致性读进判决或摘要级结论（只作敏感性读数，且必须与精确单侧 p 同报）。
- 不计算 D2 的 r2SCAN-3c 版本与 D3（ddCOSMO 垂直 EA）——本环境无 ORCA，全部登记欠账，完成后按同一预注册复跑。
- 不执行腈类三项检查（无 ORCA），条目为 `pending_orca_compute`。
- 不授权任何修数（`dipole_transfer_v1` 维持 `registered_not_authorized`）；不动四个冻结读数或任何已登记负结果。
- 不引入附录、不触碰 v2 论文线与 `_v2_*` 冻结件（改稿只落 v3）。
- 不擅自改投稿决策：只出「条件可投、边界已声明」的评估与阻塞项清单。

## 4. 交付物

- 预注册：`probes/w47_anchor_prereg.json`、`w47_experimental_track_prereg.json`、`w47_orca_rerun_prereg.json`、`w47_paper_readiness_prereg.json`（均 `locked_before_run`）。
- 转录锚点：`data/external/w47_borodin2013_table1_computed_oxidation.csv`（16 行）、`w47_borodin2013_table3_experimental_oxidation.csv`（26 行）、`w47_borodin2015_li_coupled_reduction.csv`（8 行）。
- 探针：`probes/w47_anchor_crosscheck.py`、`w47_experimental_track.py`、`w47_lane_c_plan.py`、`w47_paper_readiness.py`。
- 判据产物：`probes/artifacts/` 下 `w47_anchor_coverage.csv`、`w47_oxidation_crosscheck.csv`、`w47_experimental_ledger.csv`、`w47_lane_c_plan.csv`、`w47_paper_readiness_ledger.csv` 与四份 `w47_*summary.json`。
- 报告：`reports/w47_literature_verdict.md`、`w47_anchor_crosscheck.md`、`w47_experimental_track.md`、`w47_lane_c_plan.md`、`w47_paper_readiness.md`。
- 论文与文档：`paper/paper_zh_draft_v3.md`（v1.11、§3.32）、README §0/§5/§7/§8/§11（第 49–52 条）、`reports/decisions_log.md` §28.102。
- 测试：`tests/test_w47_anchor_crosscheck.py`、`test_w47_experimental_track.py`、`test_w47_lane_c_plan.py`、`test_w47_paper_readiness.py`。
- 导出：`probes/export_week47_results.py` -> `成果输出/week47`。

## 5. 风险与处置

| 风险 | 等级 | 处置 |
| --- | --- | --- |
| 还原锚点覆盖不足 | 高（已发生） | H47a2 拒答分支：主判据不可判定 + 功效下限同报；照实写入论文 §3.32 与 §4.6 |
| 转录值与原文冲突 | 中 | 逐行进 `adjudication` 列；EC/PC/EMC 与 Okoshi 2015、Ue 1994 的 0.3 V 条件差异已登记 |
| n = 4 交叉一致性被过度解读 | 中 | 预注册禁止单独引用 τ_b；必须与精确单侧 p 同报；产物页眉标「敏感性读数」 |
| ORCA 不可得导致 Lane C 拖延 | 中（已发生） | 全部条目 `pending_orca_compute`；Lane A 先出可执行版；Lane C 是计划内复跑而非前置依赖 |
| 抢发风险上升 | 中（上升） | Abaei 2026 已跨领域出现同修辞；Lane D 投稿就绪评估本轮必出 |
| 稿件形式缺陷（附录 / 缺图） | 低 | 抽查无附录标题、25 张图全部在盘、docx 重渲染核验真实字节嵌入 |
