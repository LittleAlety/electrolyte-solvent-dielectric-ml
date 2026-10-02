# Week 22 立项章（草案）：对外评审整改轮 —— 把 A/B/C/D 四组意见写成可执行断言

- **性质**：整改轮（review-response round）。本件**不新增昂贵量化计算、不拟合新模型、不动任何冻结件、不引用任何 Reaxys 数值**；以解析界 + 蒙特卡洛仿真 + 重抽样 + 文档统一为主。
- **状态**：`draft_pending_author_confirmation`
- **权威输入**：外部评审报告（2026-10-02 作者转述，A/B/C/D 四组）；本仓实测（`probes/artifacts/w21_rank_pairs.csv`、`probes/w21_rank_stability_summary.json`、`probes/w20_funnel_kpi_summary.json`、`probes/artifacts/w20_ranking_key_v1_candidates.csv`）。
- **生成时间**：2026-10-02（本机）

## 0. 战略判断

### 0.1 一个必须先说的定位问题（照实登记）

评审针对的那份 PDF 正文（`A_axis`、漏解安全定理、十级台阶、`P1` vs GFN2-xTB ΔSCF 的 `4.48 eV / τb 0.91`、介电阶梯 `eps = 200`、`F24` 页眉）在本仓与工作目录内**均不存在**。本仓现有的是介电数据集/筛选管线论文（`paper/paper_zh_draft.md`）与 v2 框架方案（`docs/framework/ranking-electrolyte-materials-v2.md`），二者均不含上述记号。

⇒ 本立项章按**规格书**处置这份评审：能在仓内复算/修订的条目**本轮执行**；依赖原文页面或原文数据表的条目**登记为待办**，第 1 节的处置矩阵即作者回填原文时的对照表。

### 0.2 三条本仓实测支撑（说明为什么 B 组大部分可在仓内落地）

| 事实 | 出处 |
| --- | --- |
| n=49 排序臂的**逐 pair 表**在盘（1,176 pair × 10 列，含 `dP0_eV` / `dRsol_eV` / `separation_threshold_eV` / `robust_inversion`） ⇒ 配对 bootstrap 与 CI 可在仓内重算 | `probes/artifacts/w21_rank_pairs.csv` |
| 多通道同时检验的读数在册（HOMO/LUMO/gap 三通道 + 排序 KPI 面板） ⇒ 多重比较校正可重报 | `probes/w21_rank_stability_summary.json`、`probes/w20_funnel_kpi_summary.json` |
| 大候选池在盘 ⇒ broad-pool 的最小信息预算演示可在仓内做 | `probes/artifacts/w20_ranking_key_v1_candidates.csv` |

## 1. 逐条处置矩阵（评审 A/B/C/D 四组）

| # | 评审条目（摘要） | 本轮处置 | 归宿 |
| --- | --- | --- | --- |
| A1 | 英文摘要在页面上被截断 | **依赖原文 PDF，本仓不可核**：登记为「提交前必查项」并写入 `paper/submission_checklist.md` | W22-4 |
| A2 | 中文摘要旗舰数字方向写反（`0.73` 写成「降为」） | **依赖原文数值对**；本轮给出**方向自检规则**（数值单调性 + 该对是否展示解耦），并把规则写进清单 | W22-4 |
| A3 | 漏解「安全定理」疑似差一个因子 2（`A_axis` 是单格界，间距受两格扰动 ⇒ 严格界应为 `2A_axis`） | **本轮执行**：解析证明 `|Δd| ≤ 2A_axis` + 蒙特卡洛仿真覆盖同向/反向 + 重报保护格计数与节省率 | W22-1 |
| A4 | 页眉是乱码的图题 | **依赖原文 PDF**：登记 + 给出「页眉来源逐页核对」清单 | W22-4 |
| A5 | 还原轴的物理载体要说死（气相阴离子不束缚 ⇒ ΔSCF「EA」是伪束缚 artifact） | **本轮执行（仓内可比部分）**：把 W21 的 `C_0/C_1` 气相阴离子判据与该结论对齐，明确「还原轴结论只以有连续介质的层为载体」 | W22-4 |
| A6 | 「介电层可以不算」与 A5 自相矛盾 | **本轮执行**：口径收紧为「ε ≥ 200 的高介电细化与 ε 扫描可省，**单一连续介质计算不可省**」 | W22-4 |
| B1 | `n=10` 的 `ρ = −0.851` 需三道加固（CI / 非独立 / 敏感性） | **仓内等价执行**：对 n=49 排序臂补化合物级 bootstrap CI、留一化合物敏感性、合成数据蒙特卡洛；原 n=10 条目登记 | W22-2 |
| B2 | `τb` 差值在显著性边缘 ⇒ 要**配对 bootstrap 的 Δτb CI** | **本轮执行**：在仓内 pair 表上落地配对 bootstrap 机制并出 CI（原表 0.727 vs 0.911 登记） | W22-2 |
| B3 | 图 10(d) 的 9 个预测子多重比较 | **本轮执行**：对仓内多通道/多指标检验做 Holm/Bonferroni 重报，并明确「提示性证据」定性 | W22-2 |
| B4 | 数值口径不一致（表 2 vs 图 9、§3.2 vs §3.6、ε 点数三处、360 格 vs 90 点） | **部分执行**：出具仓内口径一致性审计（哪些数同源、哪些非独立）；原文表注/图注登记 | W22-2 / W22-4 |
| B5 | broad pool 的承诺没兑现 | **本轮执行**：在 `w20_ranking_key_v1_candidates.csv` 上给出一次真实的「值得升级」排序与预算节省数字 | W22-3 |
| C1–C8 | 文字与规范（Yang et al. 定性、r2SCAN-3c 校正名、ASCII 占位符、关键词换行、参考文献缺引、图注对不上、台阶计数、图注混排） | **仓内可比部分本轮执行**，其余登记（原文） | W22-4 |
| D1 | 闭式判据的前瞻性检验（leave-one-rung-out） | **本轮执行（仿真版）**：用留一台阶仿真检验「判据能否事前预判不可分辨对」 | W22-1 |
| D2 | 关 Gate 1（溶液相锚点，Ue 2014 / Okoshi 2015） | **登记**：需原文/外部数据表，本仓不跑 DFT | W22-4 |
| D3 | 热修正抽样 | **登记**：需 xTB 频率计算额度 | W22-4 |
| D4 | 配位饱和加固（EC → 2–3 分子 DFT n=3） | **登记**：需 DFT 额度 | W22-4 |
| D5 | Week 20 路径扫描收进正文 | **登记**：依赖原文 | W22-4 |
| D6 | 最小信息预算流程图 | **本轮执行**：出决策流程图 | W22-4 |
| D7 | broad pool 的实际演示 | 同 B5 | W22-3 |

## 2. Lanes

### W22-1 安全定理严格化（A3 / D1｜成本：低｜产读数：仿真）

- **动机**：现定理把 `A_axis` 定义为**单格**最大效应量，却在 pair 判据上用 `|d0| ≥ A_axis`。一对分子的间距受**两个**格子的扰动，最坏情形是 `2A_axis`。
- **设计**：① 解析证明 `|Δ(e_i − e_j)| ≤ |Δe_i| + |Δe_j| ≤ 2A_axis`（三角不等式），并给出 pair 级重定义 `A_pair = max_pair |Δ(e_i − e_j)|` 下定理形式不变的版本；② 蒙特卡洛：每格扰动独立均匀/正态，比较 `m=1`（现判据）与 `m=2`（严格判据）的漏解率；③ 留一台阶（leave-one-rung-out）仿真：用其余台阶估扰动分布，预测本台阶哪些 pair 不可分辨，对照实测。
- **判据（跑前锁定）**：`m=1` 在反向扰动下应出现 > 0 漏解；`m=2` 在全扰动空间下漏解率 = 0。两条都成立 ⇒ A3 成立（现定理确实差因子 2），否则本臂被证否。
- **产物**：`probes/w22_safety_theorem.py` / `_prereg.json` / `_summary.json` / `probes/artifacts/w22_safety_theorem_{coverage,leakage}.png` / `tests/test_w22_safety_theorem.py` / `reports/w22_safety_theorem.md`。

### W22-2 排序统计加固（B1 / B2 / B3 / B4｜成本：低｜产读数：统计量）

- **设计**：① 化合物级 bootstrap（重抽样 49 个化合物、重算全部 pair）出 `τb` / `ρ` / `f_robust_inversion` 的 95% CI；② 配对 bootstrap 的 `Δτb`（同一批分子内重抽样，两臂共用抽到的分子集）；③ 留一化合物敏感性（剔除影响力最大的化合物后重算）；④ 多重比较校正：对 HOMO/LUMO/gap 三通道 + KPI 面板的检验做 Holm 与 Bonferroni 重报；⑤ 口径一致性审计（哪些读数是同一批分子、哪些非独立）。
- **判据（跑前锁定）**：CI 与点估计一并报告；校正后仍显著的标 `survives_correction`，否则标 `suggestive_only`。
- **产物**：`probes/w22_stat_hardening.py` / `_prereg.json` / `_summary.json` / `probes/artifacts/w22_stat_hardening_*.csv` / `tests/test_w22_stat_hardening.py` / `reports/w22_stat_hardening.md`。

### W22-3 数据统一文档 + broad-pool 最小信息预算演示（用户交付物 / B5 / D7｜成本：低）

- **设计**：① 自动生成**统一数据文档**（扫描仓内数据表与全部 probe summary，逐件输出 sha256 / 行数 / 列数 / 关键读数 / 出处），落盘 `E:\Claude Code\电解质ML\成果输出\数据统一文档.md`；② 在 `w20_ranking_key_v1_candidates.csv` 上，用「仅 P0 + 判据」预测哪些分子值得升级到昂贵层，给出候选数、升级数、节省比例。
- **产物**：`probes/build_unified_data_document.py`、`probes/w22_broad_pool_budget.py` + `_summary.json`、`tests/test_w22_unified_document.py`、`reports/w22_data_consolidation.md`、`成果输出/数据统一文档.md`。

### W22-4 论文整改清单与口径修订（A1/A2/A4/A5/A6/C*/D2–D6）

- **设计**：出 `paper/review_response_matrix.md`（逐条：原文问题 → 修法 → 是否可在仓内执行 → 状态），并**在仓内可核的范围内**修订 `paper/paper_zh_draft.md`（符号/关键词/图注/口径句）。给出 D6 的最小信息预算决策流程图。
- **产物**：`paper/review_response_matrix.md`、`paper/submission_checklist.md` 增补、`probes/artifacts/w22_min_information_budget.png`。

### W22-5 收口

- 决策日志 §28.71 起、交付包 `E:\Claude Code\电解质ML\成果输出\week22\`、README、`verification.json`。

## 3. 验收

1. 每条 lane 的 `probe / summary / report / tests` 齐备且 `pytest` 通过。
2. **冻结件零改动**：`0.4091179943351143` / `0.4766400383507876` / `0.5861142332208197` / `0.6216672295270079` 逐位不变；本周主记分牌尝试 **0 次**（累计不变）。
3. 统一数据文档可由生成器**逐字节重算**（`--check`）。
4. 每条读数带出处与 CI；不得出现无出处的数字。

## 4. 不做清单

- 不跑任何 DFT / 新 xTB 批量；不新增候选池；不动任何冻结件；不引任何 Reaxys 数值。
- 不把「仿真得到的严格界」冒充「实测的零漏解」——正文须把**定理（严格界）**与**实测（经验零漏）**分成两句。
- 不为对齐原文而编造原文数据表里的数字。

## 5. 时间安排（建议 3 个工作日）

| 日 | 内容 |
| --- | --- |
| D1 | 立项章 + W22-1 + W22-2 |
| D2 | W22-3 + W22-4 |
| D3 | 收口、验证、交付包、决策日志 |

## 6. 数字出处

- 排序 pair 表：`probes/artifacts/w21_rank_pairs.csv`
- 排序读数：`probes/w21_rank_stability_summary.json`
- KPI 面板：`probes/w20_funnel_kpi_summary.json`
- 大候选池：`probes/artifacts/w20_ranking_key_v1_candidates.csv`
- 冻结读数：`probes/export_week18_results.py::MAIN_SCOREBOARD` 等