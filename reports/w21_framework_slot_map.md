# W21 · 资产 → v2 框架槽位映射表（正式版）

- **权威输入**：`docs/framework/ranking-electrolyte-materials-v2.md`（逐字节副本，sha256 `e55c1b07a127ef7d…`，54,147 B / 1,779 行）
- **本件性质**：接线与编址。**不产读数之外的新模型、不动任何冻结件、不占 shot**（本周主记分牌尝试 **0** 次，累计仍 **12** 次）。
- **配套读数**：`reports/w21_rank_stability.md`（§9/§10）、`reports/w21_split_taxonomy.md`（§13）、`reports/w21_feature_cost.md` 的内容并入 `reports/w21_framework_alignment.md`（§11/§5.2）、`reports/w21_eta_thaw.md`、**`reports/w21_li_coordination.md`（Tier 3：§3 Axis B `C_1` / §11 `X2`）**。

## 0. 一张表看完「框架要什么 / 我们已经有什么」

| 框架槽位 | 本仓资产（evidence path） | 落点 | 缺口 | 判词 |
| --- | --- | --- | --- | --- |
| §3 Axis A `P_0` cheap scalar proxy | `data/processed/themol_orbital_layer.csv`（GFN2-xTB 气相单点，166 行）；13 维物理块 `data/processed/dielectric_physical_features_v03.csv` | 已作便宜层 | 无 | **在役** |
| §3 Axis A `P_1` gas-phase redox thermodynamics | 无自算；`data/processed/four_core_key_registry.csv` 的 IP/EA 列来自外部参考层 | — | 本仓无 free-molecule DFT | **未执行** |
| §3 Axis A `P_2` fixed-background continuum | 无 | — | 需要 SMD/连续介质 DFT | **未执行** |
| §3 Axis B `C_0` free molecular state | 等同 `P_0` 的母分子态 | 在役 | 无 | **在役** |
| §3 Axis B `C_1` Li⁺ 配位条件态 | `data/processed/w21_li_coordination_layer.csv`（246 化合物 × 2 臂 = **492 次 GFN2-xTB**）；`probes/w21_li_coordination_summary.json` | Tier 3 首次实例化 | 层级**只到 GFN2-xTB 半经验**，不是框架 §7 要求的 DFT 级；C_1 侧**没有外部参考层** | **已执行（低层级，如实标注）** |
| §3 Axis B `C_2` 显式微溶剂化 | 无 | — | 同上 | **未执行** |
| §3 Axis C `R_gas` | `pubchemqc_second_source`（B3LYP/6-31G*//PM6，801 + 111 行，`attribution_required`）；`themol_gfn2`（166 行，`noncommercial`） | 已入四角色 sidecar | Batt 是 SMD 层，不是气相锚 | **部分在役** |
| §3 Axis C `R_sol` | `batt_p30k_primary`（29,519 行，ωB97X-V/def2-TZVPPD/SMD(ε=18.5)，MIT）；`data/external/Batt-SLM-RX-392.csv`（392 行） | 首次当 reference layer 用时**就落在 §9/§10 上**（本件） | 参考层物理不确定度未量化 | **在用，且已标注** |
| §3 Axis C `R_env` | 无 | — | 需要环境/界面层 | **未执行** |
| §4.1 方向量（ox/red 分开） | `reports/w19_ranking_key_v1_spec.md` | 本件按 `P^ox = −ε_HOMO` 选 Top-k | 排序键 v1 仍把两方向混在一条键里 | **部分成立** |
| §5.2 多轴 metadata | `data/processed/w21_chemical_space_metadata.csv`（246 行；16 个主家族 + 多选标签 + 角色） | 本件新建 | `conformer_count` / `Li_motif_count` / `state_identity_status` / `reactivity_status` 四列仓内不存在，如实写 `not_available_in_repo` | **成立（含 4 个显式空列）** |
| §5.1 双层结构 core / broad | 冻结 ε 名册 246 → 建模集 236；轨道可核主臂 49；η 4,151 行 / 976 键 | 三套池各自登记 | 无统一 core/broad 命名 | **部分成立** |
| §9 不确定性感知排序 | `probes/w21_rank_stability_summary.json` | 首次实例化 | 参考层无 σ（只登记 0.05 eV 数值容差） | **已产读数** |
| §10.1 Top-k overlap / §10.2 selection regret | `probes/artifacts/w21_topk_overlap.csv` | 首次实例化（k/N = 10/20/30%） | 无 | **已产读数** |
| §10.3 threshold decision error | 无 | — | HOMO 通道上没有来自外部设计要求的阈值 | **未执行（如实登记）** |
| §11 feature-cost accounting | `probes/artifacts/w21_feature_cost_map.csv`（18 行；X0 9 / X1 2 / X2 1 / target 2 / reference 4）；X2 一行的 `evidence_path` 现指向 `data/processed/w21_li_coordination_layer.csv` | 本件新建；**Tier 3 把 X2 由空补上** | X2 只有 1 列（条件态 Δ），且层级为半经验 | **成立，且 X2 由空转有** |
| §12 Δ-learning | `reports/w18_*.md`（Onsager Δ 读数 `0.2242978111516481`，登记为「框架外已做」） | 登记 | 无 direct vs conditional-shift 对照 | **框架外** |
| §13.1 复杂度阶梯 | `probes/artifacts/w21_split_metrics.csv` | 本件跑满 8 条（含均值基线与单特征基线） | KRR 未调参时炸掉（−164.8），已单列 `krr_tuned` | **已产读数** |
| §13.2 三拆分并排 | 同上 + `reports/dielectric_splitters_auc.md`（ε 侧三拆分） | 轨道侧首次并排 | LOFO 只够 4 个家族（成员 ≥5） | **已产读数** |
| §14 active learning | 无 | — | 需要昂贵标签预算 | **未执行** |
| §18 多目标不构造综合分 | `reports/w20_ranking_key_v1_spec.md`、四通道交集 7 分子 | 遵守 | — | **成立** |
| §19 Stage 0 / Stage 1 gate | `probes/artifacts/w21_stage_gate_verdicts.csv`（14 条：成立 8 / 部分成立 3 / 未执行 3）；Tier 3 后 `C_1` 不再计入「未执行」 | 本件落判词 | Gate 1 **仍未闭合**（C_1 侧无外部参考层），但缺口性质由「空的」变为「低层级已实例化」 | **已落判词（Tier 3 后修订）** |
| §22 情形分支 | ε 主记分牌 + 分域记分牌 + 本件 §9 读数 | 见下节 | — | **已归属** |
| 判据机器（预注册 / 安慰剂 / 泄漏 / shot 台账） | `reports/decisions_log.md`、`probes/w19_shots_ledger.json` | 整体复用 | — | **全仓最贵资产** |

## 1. §22 情形分支归属（照实说）

| 分支 | 框架描述 | 本仓对应 |
| --- | --- | --- |
| §22.1 情形 A | cheap proxy 已经稳定保持排序 | **ε 通道**：W20-4 跨种子均值 `0.6216672295270079`、五种子下界 `0.5999547508973201`；轨道通道的 ρ = 0.8640 也支持「排序稳定」 |
| §22.2 情形 B | 数值变化很大但排序稳定 | **轨道通道的准确描述**：跨层级系统偏移 1.0708 eV（Batt − 我方），但 ρ = 0.8640 |
| §22.7 情形 G | 大部分 pairs 都 unresolved | **本件 §9 的实测归属**：预注册容差下 61.6% 的 pair 至少一侧不可分辨，`f_robust_inversion = 0/451` |

**一个必须同时说的边界**：情形 A 与情形 G 同时成立并不矛盾——ε 通道量的是「我们的模型 vs 实验标签」，轨道通道量的是「便宜层 vs 外部参考层」。两块记分牌永不混比。

## 2. 本件不做的（写清为什么）

- **`C_1` 已由 Tier 3（`probes/w21_li_coordination.py`）在 GFN2-xTB 层级实例化**；`C_2` / `P_1` / `P_2` 仍不做（分别需要显式微溶剂化、free-molecule DFT、连续介质 DFT，塞不进本周）。本仓不假装做过这三者。
- **不做 §14 active-learning replay**：它需要「昂贵标签预算 → 决策精度」曲线，而本仓的昂贵标签（Batt 层）只有 49 个可核点。
- **不发 v1.4**：本周无晋升、无冻结件移动，发布线不动。