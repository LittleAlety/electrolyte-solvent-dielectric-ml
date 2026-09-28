# Week 21 立项章（草案）：把既有资产接进 v2 框架的槽位

- **性质**：接线章（framework alignment）。本件只做四件事：① 宣布框架内外分界；② 出资产→槽位映射表；③ 冻结三个判词数字；④ 定义 Tier 1/2/3 与验收。**本件不产任何读数、不拟合任何模型、不动任何冻结件、不引用任何受限数值、不做任何 git 操作。**
- **状态**：`draft_pending_author_confirmation`
- **权威输入**：`C:\Users\Little Alety\Downloads\ranking-electrolyte-materials-v2.md`（1,779 行 / 54,147 B，《Understanding Electrolyte Materials through Decision-Centric Ranking Stability》v2，英中双语，17 节正文 + 13 张建议图 + 11 篇参考文献）。
- **上游**：W20 收口（`reports/decisions_log.md` §28.57–§28.66）、W19 通道转移预案（§28.51）、W18 分域记分牌（§28.45）。
- **生成时间**：2026-09-29（本机）
- **框架内部细化**：**不讨论、不征求**。本件只做接线与口径补丁。

## 0. 战略判断

### 0.1 本轮真正需要接线的原因

框架 v2 不是要我们重做实验，而是要我们把**已经做出来的资产按它的三层轴重新编址**，并把指标从「预测准不准」切到「筛选可不可靠」。仓内实测表明：框架要求的多数槽位**已经有对应资产**，缺口集中在**指标口径**而不是**数据或计算**。

### 0.2 一条必须纠正的旧口径

W18 结论「ε 表示层封顶，跨种子端点 `0.5861142332208197`」**已被 W20-4 超越**：注册臂 `hp2_d4_n200_lr0.05_mcw5_ss0.8_cs0.8_bin128` 跨种子均值 `0.6216672295270079`，五种子下界 `0.5999547508973201`，安慰剂塌缩 `0.41179237661783363`。因此框架 §22.1「cheap proxy 已经稳定保持排序」成为当前对应的情形分支；**立项依据不得再引 0.586 当终态**。冻结头条 `0.4766400383507876` 与冻结基线 `0.4091179943351143` 原位不动。

### 0.3 一条被误判为「缺口」的资产

框架 §3 Axis C（external reference layer）在仓内**已经被部分建成**，但从未被当 reference layer 用于决策指标：

| 事实 | 出处 |
| --- | --- |
| `batt_p30k_primary` 已入 sidecar，29,519 行，`wB97X-V/def2-TZVPPD/SMD(epsilon=18.5)` | `data/processed/four_core_label_provenance_sidecar.csv` |
| 名册 ∩ Batt 身份命中 **78** 键；可核主臂 **n = 49** | `reports/w19_batt_gap_crosscheck.md` 一、二节 |
| `P_0`(GFN2-xTB 气相) × `R_sol`(Batt) 交叉核已做：homo r=`0.8223` / ρ=`0.8640` / 留一 MAE `0.3475` | 同上，主臂读数表 |

⇒ **Tier 2 只差把已有的相关分析改写成 §9 / §10 的决策指标，不需要新增任何量子化学计算。**

### 0.4 真正的瓶颈（仓内实测，`data/processed/four_core_key_registry.csv`，**31,949 行 × 30 列**）

| 通道 | 有值行数 | 占比 |
| --- | ---: | ---: |
| orbitals (HOMO/LUMO/IP/EA/gap) | 29,868 | 93.49% |
| density | 2,178 | 6.82% |
| viscosity | 1,228 | 3.84% |
| redox_label | 392 | 1.23% |
| dielectric | 247 | 0.77% |
| liquid_window (mp/bp/fp) | 218 | 0.68% |

`n_core_channels` 分布：0 通道 **898**；1 通道 **30,433**；2 通道 **559**；3 通道 **52**；4 通道 **7**。

⇒ **四通道交集只有 7 个分子**。框架 §18 禁止构造武断「综合电解液分数」；本仓的多目标叙事因此只能按 **Pareto front / 明确 target window** 写，且**不得**用 7 分子交集当筛选结论。

## 1. 框架内外分界（先钉，否则会出现两套口径）

| 归属 | 对象 | 理由 |
| --- | --- | --- |
| **框架外**（只共享判据机器，不共享口径） | ε 主记分牌 `0.4091179943351143` / `0.4766400383507876` / W20-4 注册臂 `0.6216672295270079`；η 通道行级 `0.15686276760094522` / 族级 `0.17477197208762` | ε 与 η **不是 redox 热力学量**，塞不进 Axis A 的 `P_0/P_1/P_2` |
| **框架内** | 轨道能通道（HOMO/LUMO/gap）、氧化还原通道（`data/external/Batt-SLM-RX-392.csv`，392 条记录）、Li⁺ 条件态 | 直接对应 `P_0/P_1/P_2`、`C_0/C_1/C_2`、`R_gas/R_sol/R_env` |
| **需裁剪** | 排序键 v1（HOMO/LUMO 等权两维） | 撞框架 §4.1：混了氧化方向量（`P_0^ox = -epsilon_HOMO`）与还原方向量（`P_0^red = epsilon_LUMO`）⇒ 拆成**两条单方向键**，或降为框架外工具 |

**永不混比条款**：`0.5861142332208197`（单表示跨种子端点）与 `0.4766400383507876`（冻结头条）永不混比；ε 的 **457 行 / 97 化合物 / 276 个（化合物, T）对**口径不得与 η 的 **4,151 行 / 976 键**混说；Tier 2 的 n=49 口径不得与上述任一口径混说。

## 2. 资产 → 槽位映射（正式版见 `reports/w21_framework_slot_map.md`）

| 框架槽位 | 已有资产（evidence path） | 缺口 |
| --- | --- | --- |
| §3 `P_0` | `probes/artifacts/themol_orbital_layer.csv`（GFN2 气相，166 行）；13 维物理块含 `homo_lumo_gap_ev` | 无 |
| §3 `R_sol` | `batt_p30k_primary`（SMD ε=18.5，29,519 行），已入 sidecar | 层已存在，但**从未当 reference layer 用于决策指标** |
| §3 `R_gas` | `pubchemqc_second_source`（B3LYP/6-31G*//PM6，801 + 111 行）、`themol_gfn2` | 无 |
| §9 不确定感知排序 | 适用域 D1（`NumHDonors>=1 and TPSA>=20.0`）、`HIGH_PERMITTIVITY_EPS=60`、拒答规则 `0.757085020242915`（187/247） | 缺**逐 pair 的 σ / δ_m**（现只有「域」级不确定） |
| §10.1 Top-k overlap | purity@k、Jaccard@k(10/20/50)、AUC15 `0.8947` / AUC30 `0.9392`、ρ `0.7738` | 改命名 + 预注册 k/N 即可 |
| §10.2 / §10.3 | 无 | 首次实例化 |
| §11 feature-cost | `probes/artifacts/w20_label_provenance_sidecar.csv`（4 role / 34,131 键） | 缺 `feature_cost_level`（X⁰/X¹/X²）列 |
| §13.2 三拆分 | random 5×10、group = GroupKFold by InChIKey、scaffold（112 骨架） | **缺 LOFO**（依赖 §5.2 多轴 metadata） |
| §5.2 多轴 metadata | 112 骨架资产 | 缺 `structural_family` / `functionalization_tags` / `use_role` |
| §19 Stage 0/1 | `reports/w19_state_audit.md`（state identity QC）、Batt sha256 校验、gas/solution anchors | 未按 Gate 0 / Gate 1 正式落判词 |
| §22 情形分支 | ε 主记分牌 + 分域记分牌（全域 `0.45401075998423623` / D1 `0.524012313223719` / 域外 `0.3198024498133034`） | 分支归属未按 §22.1–§22.7 明写 |
| 判据机器 | 预注册哈希、安慰剂塌缩、泄漏 0 / 50 折、单臂判词纪律、累计 12 次 shots 台账 | 可**整体复用**，是全仓最贵资产 |

## 3. 三层执行

### Tier 1｜零计算对齐（本周必成）

1. v2 框架**原样入库** `docs/framework/ranking-electrolyte-materials-v2.md`（不改一字节）+ 登记 sha256。
2. 出正式版 `reports/w21_framework_slot_map.md`（§2 的完整版，每槽位带 evidence path、缺口、判词状态）。
3. 补 `feature_cost_level` 列（X⁰/X¹/X²），宿主 = label provenance sidecar。
4. 建多轴 metadata：`structural_family` / `functionalization_tags` / `use_role`（复用 112 骨架 + 官能团 SMARTS）。
5. 补 **LOFO** 拆分器（leave-one-structural-family-out，依赖 4）。
6. 按 §19 把 Stage 0 / Gate 0、Stage 1 / Gate 1 写成正式判词（逐条给出「成立 / 不成立 / 未执行」三态）。

### Tier 2｜零 DFT，本周唯一的真读数层

7. 首次实例化 §9：`robust inversion fraction` + `unresolved-pair fraction` + `Kendall tau_b`，两端 = `P_0`(xTB GFN2 气相) × `R_sol`(Batt ωB97X-V/SMD ε=18.5)。
8. 首次实例化 §10：`Top-k overlap` / `selection regret` / `decision error`。
9. §13.2 三种拆分在轨道通道上**同时**报告（random / group-scaffold / LOFO）。
10. §13.1 复杂度阶梯（linear/ridge → KRR → GPR → RF/GB）在轨道通道跑一遍（target = Batt gap）。
11. η 解冻（Walden `kinematic_thaw`）+ 两处零成本补强：
    - 把 `auc_gt15` / `auc_gt30` 加进 `METRIC_NAMES`（现只在 `ranking_head` 与两处 `representation_ablation` 存在）；
    - 出「三档划分（随机 / 化合物 / 骨架）× R² / AUC / Spearman」一张表。

**硬约束（必须提前钉住）**：Batt 侧可核主臂仅 **n = 49** ⇒ 配对数 `C(49,2) = 1176`，可用化合物数正落在框架 §13.3 自警的统计薄区。故 Tier 2 一律标注为 **machinery pilot**，必须报告 bootstrap 置信区间与 permutation 检验，**不得当框架正式结论**。

### Tier 3｜明确宣布不在本周（写清「为何不做」）

- `C_1` Li⁺ 条件态、显式微溶剂化（`C_2`）、完整 method audit（functional/basis/diffuse 扫描）、active-learning replay、direct vs conditional-shift Δ-learning —— 全部**需新增 DFT 或完整 core labels**，塞不进一周。
- W18 已有的 Onsager Δ 读数 `0.2242978111516481` 按「框架外已做」登记，**不重跑**（其余已否决杠杆：构象方差 `0.5691705415075562`、Uni-Mol `0.1102020209457352`、log 空间 `0.5834189863657219`）。
- 本件不判定、不重跑上述任何一条 ⇒ 无一被改写。

## 4. 判词冻结（三个数字，本周跑前锁定，事后不得改）

| 判词 | 冻结值 / 定义 | 落点 |
| --- | --- | --- |
| `delta_m`（pair 容差确定方法） | 每通道一个 tolerance：由 method/conformer uncertainty 推出，跑前写入预注册；§9.1 的 `abs(dP) < delta_m` 与 `abs(dP) < z*sigma` 两条同时适用 | `probes/w21_rank_stability_prereg.json` |
| k / N | k = 10 / 20 / 50；N = 该口径名册规模；同时报绝对数与比例 | 同上 |
| decision-changing 判据 | 族内 **≥ 20% pair 发生 robust inversion** **且** top-k 成员组成改变 ⇒ 记 `decision_changing` | 同上 |

## 5. 交付物与验收

- **章节**：`reports/week21_project_charter.md`（本件）、`reports/w21_framework_slot_map.md`、`reports/w21_rank_stability.md`、`reports/w21_split_taxonomy.md`、`reports/w21_feature_cost.md`、`reports/w21_framework_notes.md`（§8 补丁清单）。
- **代码**：`probes/w21_*.py` + `*_prereg.json` + `*_summary.json` + `tests/test_w21_*.py`。
- **导出**：`probes/export_week21_results.py` → `E:\Claude Code\电解质ML\成果输出\week21\`。
- **图 3 张**：rank-stability matrix、robust rank-flow map、split × metric 表。
- **验收**：与 week18 / week19 / week20 同构 —— `lanes_missing=[]`、`promoted_lanes=[]`、`worktree_dirty=false`、`artifacts_commit` 指向最新提交、`verification_passed=true`。
- **收口顺序**（AF-12）：封树提交 → 干净重导 → 补修复提交。
- **Zenodo**：默认**不发** v1.4；是否发由作者定。

## 6. 不做清单

- 不与 ε / η 口径混比；不动任何冻结件；不占 shots（本周 **0 次**主记分牌尝试，累计仍 12 次）。
- 不把 Batt-P30K 标签混进 ε / η 训练池 —— 它是 reference layer，不是标签源。
- 不接 OMat24（无机晶体，错配）；不把任何随机拆分文献数字当对照靶或晋升依据。
- 不用 7 分子四通道交集当多目标筛选结论（框架 §18）。
- 不产读数地「顺手修框架」—— 缺陷只登记在 `reports/w21_framework_notes.md`，不改原文一字节。

## 7. 时间安排（建议 5 个工作日）

| 日 | 内容 |
| --- | --- |
| D1 | Tier 1 第 1–2 项：框架入库 + 槽位映射表定稿 |
| D2 | Tier 1 第 3–6 项：feature_cost_level、多轴 metadata、LOFO、Stage 0/1 判词 |
| D3 | §4 三个判词冻结 + Tier 2 第 7 项（§9 三件套） |
| D4 | Tier 2 第 8–11 项：§10、三拆分、复杂度阶梯、η 解冻 + 两处零成本补强 |
| D5 | 图 3 张 + 章节落章 + 导出 + 提交推送 + 干净重导 |

## 8. 框架 v2 口径补丁（本仓执行时生效，**不对外改原文**）

| # | 缺陷 | 本仓处置 |
| --- | --- | --- |
| 1 | §9.2 `f_robust inv` 分母为「pairs resolved in both」，静默丢弃「仅单模型可分辨」的 pair | 补报 `f_resolved_in_exactly_one` |
| 2 | §13.1 缺常数 / 均值基线，也缺**单特征排序基线** | 本周补跑两条基线 |
| 3 | §10.3 threshold decision error 的 `T` 来源未给 | 暂标「MVP 空转」，不进本周读数 |
| 4 | §10.2 selection regret 的 `T` 是模型而非真值，定义处缺交叉引用 | 引用 §15 / §25.2 并显式标注 |
| 5 | §23「最小成果判据」11 项 ≈ Stage 0–9 全做，与 §29「本科 8–12 周 MVP」矛盾 | 本仓切两层：MVP = Stage 0–1 + `P_0/P_1` + 单域 rank-stability |
| 6 | §19 Gate 只到 Stage 1，Stage 3（state-identity QC 通过率）与 Stage 5（motif survival rate）无 gate | 本仓为 Stage 3 / 5 各补一条建议 gate（标注为「本仓补」） |
| 7 | 核心命题缺反向证伪条件（什么观测会承认 `C_1` 就是该用的物种） | 写入 `w21_framework_notes.md` 待议，不进正式判词 |
| 8 | 格式：13 处有序列表缺第 3 项（行 133/410/446/879/892/951/1136/1153/1168/1183/1203/1216/1257/1433/1530）；§23 另有重复 `11.`；抬头 `**文件名：** understanding-electrolyte-materials-v2.md` 与实际文件名 `ranking-electrolyte-materials-v2.md` 不一致 | 只在 `w21_framework_notes.md` 登记，**不改原文** |
| 9 | §4.1 方向约定（`P_0^ox = -epsilon_HOMO`、`P_0^red = epsilon_LUMO`）建议加 direction convention box | 本仓排序键拆分时强制使用该约定 |

## 附 · 数字出处

- 冻结读数（ε）：`probes/export_week18_results.py`（`MAIN_SCOREBOARD` / `MAIN_SCOREBOARD_HEADLINE_R2` / `FROZEN_SINGLE_REPRESENTATION_CROSS_SEED`）
- W20-4 晋升臂、安慰剂、五种子下界：`probes/w20_epsilon_second_stage_summary.json`、`probes/w20_epsilon_second_stage_placebo_summary.json`
- 通道覆盖与 `n_core_channels` 分布：`data/processed/four_core_key_registry.csv`
- Batt 交叉核（78 命中 / n=49 / r / 留一 MAE）：`reports/w19_batt_gap_crosscheck.md`、`probes/w19_batt_gap_crosscheck_summary.json`
- 通道门槛状态：`probes/w19_ranking_key.py::CHANNEL_GATE_STATUS`、`reports/w19_channel_transfer.md`（§28.51）
- η 读数与 Chemprop 对照：`probes/w19_chemprop_viscosity_summary.json`、`probes/w20_eta_fairness_summary.json`
- 适用域与拒答：`probes/dielectric_applicability_domain_summary.json`、`probes/w20_refusal_summary.json`
- 漏斗 KPI（AUC15/AUC30/ρ）：`probes/w20_funnel_kpi_summary.json`
- 标签溯源 sidecar（4 role / 34,131 键）：`probes/artifacts/w20_label_provenance_sidecar.csv`
- 框架原文：`C:\Users\Little Alety\Downloads\ranking-electrolyte-materials-v2.md`
