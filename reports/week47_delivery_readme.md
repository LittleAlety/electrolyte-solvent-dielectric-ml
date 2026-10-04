# Week 47 交付说明

**本轮性质**：只读转录 / 交叉核对 / 治理周。取件核实推翻了 W47 计划对 Borodin 2013 的归属假设，于是本轮把重点从「新增算力」改成「把源读对、把覆盖算清、把拒答写实」：三张转录锚点表装成只读件、核心集覆盖逐轨核算、氧化轴做一条小样本交叉一致性、实验轨降级并逐件台账、D2/D3 协议冻结、论文回填与投稿就绪评估。
**shot 账本**：**0 shot，累计仍 19**。四条 lane 全是只读转录、交叉核对与治理件。
**冻结读数**：`0.4091179943351143` / `0.4766400383507876` / `0.5861142332208197` / `0.6216672295270079`，一个不动。

---

## 1. 判据总账

| lane | 标题 | 判据 |
| --- | --- | --- |
| W47-A | 计算锚点覆盖核算与氧化轴交叉一致性 | H47a1–H47a9：**9 成立** |
| W47-B | 实验还原轨候选逐件裁定 | H47b1–H47b8：**8 成立** |
| W47-C | D2/D3 协议冻结与 ORCA 算力欠账登记 | H47c1–H47c9：**9 成立** |
| W47-D | 论文回填复核与投稿就绪评估 | H47d1–H47d12：**12 成立** |

**合计 38 条判据 = 38 成立 + 0 判否**（本轮无新增在册判否、无新增登记负结果）。四个冻结读数未动，W47 测试全绿。

## 2. 关键读数与边界

- **三张转录锚点（W47-A）**：Borodin 2013 Table 1 计算氧化 **16 行**（sha256 `0c2809df…4fb86f`）、Table 3 实验氧化 **26 行**（`14e4978f…71b28b`）、Borodin 2015 图 6/7/8 Li⁺ 耦合还原 **8 行**（`5792c3f5…961739`）。**关键更正**：计划所称「68 EA + 86 IP 的 G4MP2 表」是**错误归属**——那是其 ref51（Vydrov & Van Voorhis 2006，G2 离子测试集，实为 **58 个 EA**）的内容；Borodin 2013 为**纯氧化**论文，全文无还原/EA 表。
- **覆盖核算（W47-A）**：核心集 7 溶剂 {EC, PC, EMC, MA, SL, DOL, DMSO} 上——计算氧化 **4/7**（EC/PC/EMC/SL）、实验氧化 **4/7**（同四溶剂单溶剂行）、计算还原 **1/7**（仅 EC，且为计算件）、实验还原 **1/7**（仅 PC）⇒ 还原轨并集 **2 < 5**，**H47a2 拒答分支触发**：D0–D3 主判据**不执行**，降级为「不可判定 + 功效下限」（与 W33 ORCA 层先例同规格，**不算失败**）。
- **氧化轴交叉一致性（W47-A，敏感性读数）**：n = 4 溶剂，计算 G4MP2 绝热氧化自由能（ε=20）对实验氧化电位——τ_b = **0.6666666666666669**、精确单侧 **p = 0.16666666666666666**、Top-1 重叠 **1.00** / Top-2 **0.50**、未解析对占比 **0.3333**；bootstrap 95% CI = **[−1.0, 1.0]**（10000 次重抽中 152 次退化已剔除，n = 4 的区间几乎不携带信息）；ε=1 敏感性列 τ_b 降到 **0.3333**。留一法：去 EC / PC 时 τ_b = 1.0，去 EMC / SL 时 0.3333。**门禁过滤在本件不适用**（W33 门禁按 InChIKey 在 gfn2/orca 层注册，转录表是外部 G4MP2 层、无 InChIKey），已显式登记而非静默跳过。**这条只作敏感性读数，不进判决、不写进摘要级结论。**
- **功效下限（W47-A）**：n = 4 的 MDE（80% 功效）= **0.982638888888889**；精确拒绝率 = **0.041666666666666664**；τ_true = 0.6 / 0.8 时功效只有 **0.0625 / 0.0833**。
- **实验轨台账（W47-B）**：Moshkovich 2001（JES 148, A295）核实为 **PC 单溶剂 × LiClO₄/NaClO₄/KClO₄**、Au 电极，窗口值在 CV 图里、无溶剂×盐表 ⇒ 重分类为 `mechanism_evidence_only`。台账 **9 件**，每件有 verdict 与非空 `condition_flag`：不可得 3 件（Okoshi 2015 / Ue 1994 / DOE APR FY2016）、计算件 3 件、轴不匹配 1 件、待取原件 1 件（**Ue 1997，JES 144, 2684**）；开项 `Ue1997_reduction_side` 维持 `pending_source_retrieval`。实验轨裁决 = **`not_evaluable_condition_differs`**。
- **Lane C 协议冻结（W47-C）**：D2（r2SCAN-3c）六项齐备（含多构象采样 + 构象散布必报，敏感度量级约 **0.13 V**）；D3（ddCOSMO）四项齐备（垂直 NE / 绝热 EQ / W26 介电管线）；腈类 GN/MPN/BC × 3 项 = **9 行**齐备。`orca_available = false` ⇒ 全部条目 `pending_orca_compute`；排期估算 **76** 个单点（估算，不是读数）。`dipole_transfer_v1` 维持 `registered_not_authorized`。
- **论文与治理（W47-D）**：论文 v3 升 **v1.11**、新增 **§3.32**；§1.2 补 **Abaei 2026** 与 **Deng 2026**；§4.6 局限照实更新；参考文献补 **13 篇**；**无附录标题**、论文引用的 **25 张图全部在盘**。**投稿就绪闸门 10/10 通过**，裁决 `conditional_go`；**剩余阻塞项是科学证据而非稿件形式**（还原锚点 0 / D2-D3 未算 / Ue 1997 待取原件 / strict same-level 源 0）。守卫复跑：闸门拒 **3** 个负对照、仅 PubChemQC 过闸；逐轮验收 **44** 轮、fail **0**；AST 静态守卫 **375** 文件、mutation **0**、冻结读数写入 **0**、未登记晋升 **0**；台账登记负结果并集 **9**、越界 **0**、累计 shot 上限 **19**。

## 3. 复现

```powershell
$env:PYTHONIOENCODING="utf-8"; $env:OMP_NUM_THREADS=1; $env:OPENBLAS_NUM_THREADS=1
python probes\w47_anchor_crosscheck.py
python probes\w47_experimental_track.py
python probes\w47_lane_c_plan.py
python probes\w47_paper_readiness.py
python -m pytest tests\test_repo_hygiene.py tests\test_w47_anchor_crosscheck.py tests\test_w47_experimental_track.py tests\test_w47_lane_c_plan.py tests\test_w47_paper_readiness.py -q -p no:cacheprovider
python probes\export_week47_results.py --overwrite
```
