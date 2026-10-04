# 工作日志 · Week 47（双轨还原锚点、主判据执行与投稿就绪评估）

> 承接 `reports/work_log_week46.md`。本轮起点：W46 收口后（HEAD `04b27e3`，工作树 218 项）；导出时工作树 251 项。本轮 0 shot，累计仍 19；四个冻结读数一个不动。

## Week 47：先把源读对，再谈主判据

**目标**：W46 把「还原轴需要重新定义」推进成可执行结论，但把执行主判据的希望寄在「Borodin 2013 的 G4MP2 EA 表」上。W47 取件后核实这个前提不成立，于是把本轮拆成四条**只读** lane：**A** 覆盖核算 + 氧化轴交叉一致性、**B** 实验轨逐件台账、**C** D2/D3 协议冻结与算力欠账、**D** 引用回填 + §3.32 + 投稿就绪评估。

**交付**

- **预注册**：`probes/w47_anchor_prereg.json`、`w47_experimental_track_prereg.json`、`w47_orca_rerun_prereg.json`、`w47_paper_readiness_prereg.json`（均 `locked_before_run`，rev 1）。
- **W47-A 覆盖核算 + 交叉一致性**（9/9 成立）：三张转录锚点行数 + sha256 三处钉住（16 / 26 / 8 行）。覆盖核算：计算氧化 4/7、实验氧化 4/7、计算还原 1/7、实验还原 1/7 ⇒ 还原轨并集 **2 < 5** ⇒ **H47a2 触发**、主判据不可判定。氧化轴 n = 4：τ_b **0.6666666666666669**、精确单侧 p **0.16666666666666666**、Top-1 **1.00** / Top-2 **0.50**、未解析 **0.3333333333333333**、bootstrap CI **[−1.0, 1.0]**（152/10000 退化已剔除）；敏感性列 ε=1 的 τ_b **0.3333**；留一法去 EC/PC → 1.0、去 EMC/SL → 0.3333。功效下限 n = 4：MDE **0.982638888888889**、精确拒绝率 **0.041666666666666664**。
- **W47-B 实验轨台账**（8/8 成立）：Moshkovich 2001 重分类 `mechanism_evidence_only`；台账 **9 件**全有 verdict + 非空 `condition_flag`；实验轨 `not_evaluable_condition_differs`；`Ue1997_reduction_side` 仍 `pending_source_retrieval`。
- **W47-C 协议冻结**（9/9 成立）：D2 六项 + D3 四项 + 腈类 9 行齐备；`orca_available = false` ⇒ 全部 `pending_orca_compute`；估算 **76** 个单点；`dipole_transfer_v1` 维持 `registered_not_authorized`。
- **W47-D 论文与治理**（12/12 成立）：引用 **13/13** 在位；§3.32 在位；§1.2 补 Abaei/Deng 2026；§4.6 局限更新；**无附录标题**、25 张图全在盘；投稿就绪闸门 **10/10**（`conditional_go`）+ 阻塞项清单；`decisions_log.md` §28.102；README §11 第 49–52 条。
- **测试与集成**：`tests/test_w47_*.py`（7+7+7+8 = **29 项**）全绿（含 `test_repo_hygiene.py` 共 34 passed）；论文 v3 -> **v1.11**；README §0/§5/§7/§8/§11；导出脚本 `probes/export_week47_results.py`。

**结果与验收**

- **判据**：38 条（A 9 / B 8 / C 9 / D 12）**全部成立、0 判否**；四条探针连跑两遍，`git status --porcelain` 脏路径集逐项稳定。
- **测试**：`tests/test_w47_*.py`（31 项）加 `test_repo_hygiene.py` / `test_w38_data_recon.py` / `test_w37_gate_admission_export.py` 子集共 **48 passed**。
- **治理校验**：`scripts/verify_four_core_registry.py --check` 全 PASS；`scripts/check_paper_artifact_consistency.py` 打印 `paper drafts agree with the frozen artifacts`；`scripts/verify_paper_figures.py` PASS。
- **论文与渲染**：v3 头部升到 **v1.11**、证据范围 week21–week47、新增 §3.32；`paper/make_paper_v3_docx.py` 重渲染并核验 25 张图全部以真实字节嵌入。
- **导出**：`probes/export_week47_results.py` -> `成果输出/week47`，`verification_passed=true`、`lanes_missing=[]`、`frozen_red_lines_intact=true`。

**坑与更正**

- **计划的两处事实错误（本轮最重要的更正）**：① V1 把「Borodin 2013 有 68 EA + 86 IP 的 G4MP2 表」写成计算锚点——实为其 ref51（Vydrov 2006，G2 离子测试集，**58 EA**）；Borodin 2013 是**纯氧化**论文。② V2 把 Moshkovich 2001 当作「多溶剂窗口系列」——实为 **PC 单溶剂**。两处都按取件原文重分类，并把纠正写进论文 §3.32、§4.6、README §5 与 §11 第 49–50 条。
- **n = 4 的 bootstrap 一度全为 NaN**：`w42_common.bootstrap_ci` 在 n = 4 时会抽到全同/退化重抽，`tau_b` 未定义，导致 mean/sd/percentile 全 NaN。改为本件自带的 NaN-safe 重抽（逐次剔除退化重抽并报 `valid / invalid` 计数），CI 得 **[−1.0, 1.0]**，并把「区间几乎不携带信息」写进论文，而不是留一个空洞的 NaN。
- **rank 列一度错位**：`enumerate(argsort(...))` 的 (位置, 原下标) 被写反，报告表里的「计算秩」错列（EC 显示 3、PC 显示 1）。已改为 `{labels[int(x)]: position}`，并由 `test_oxidation_crosscheck_small_sample` 之外的表列核对确认（EC 2 / PC 3 / EMC 1 / SL 4）。
- **全局替换误伤历史行**：修 `\` 转义残留时，一度把三条**早已存在**的行内代码里「反斜杠 + 反引号」也替换掉（例如 `..\` 与两个 `成果输出\week2N\` 路径）。`git diff` 抓到 **3 行**变更（180 增 / 3 删），已按 diff 逐行回补，最终 `git diff --numstat` = **180 / 0**（纯追加）。
- **导出后治理快照会变**：`成果输出/week47` 出现后，Lane D 的逐轮验收 **43 -> 44** 轮、AST 静态守卫 **374 -> 375** 文件（新增导出器本体）；所有文档数字统一按「导出后复跑」的读数校准，再二次导出。
- **不需要新目录**：本轮 4 条 lane 都复用 `probes/w42_common.py` 与 `probes/export_results_common.py`，未新增共享模块。

**仍未闭合（已登记）**

- 见 README §11 第 49–52 条：① 还原轨核心集覆盖并集 **2/7 < 5**，主判据按 `H47a2` **不可判定**——要执行主判据，须先把同装置实验还原锚点从 0 补到 ≥ 5；② D2 的 r2SCAN-3c 版本与 D3（ddCOSMO 垂直 EA）需**新 ORCA 单点**，转 **round-2**；③ `dipole_transfer_v1` 维持 `registered_not_authorized`，修数未授权；④ strict same_level 外部源仍为 0；⑤ Ue 1997 的还原侧是否含值待取原件。
- **投稿相关**：本轮裁决 `conditional_go`（形式闸门全过），剩余阻塞项为科学证据；是否投稿由作者决定，本件不擅自改决策。
