# W21 · 框架 v2 口径补丁清单（本仓执行时生效，**不对外改原文**）

框架原文在 `docs/framework/ranking-electrolyte-materials-v2.md`，逐字节副本，sha256 `e55c1b07a127ef7d…`。本件只登记缺陷与处置，**一个字节都不改**。

## 1. 立项章预登记的九条

| # | 缺陷 | 本仓处置 | W21 实测证据 |
| --- | --- | --- | --- |
| 1 | §9.2 `f_robust inv` 的分母是「两侧都可分辨的 pair」，会静默丢掉「仅单侧可分辨」的 pair | 补报 `f_resolved_in_exactly_one` | **实测 0.5655** —— 1,176 个 pair 里有 665 个只被一侧解析，占 56.5%。分母 451 只占全部 pair 的 38.4%，这不是小数点问题 |
| 2 | §13.1 缺常数/均值基线，也缺单特征排序基线 | 补齐两条基线 | `mean_baseline` 在 LOFO 下 R² = **−27.45**、random 下 **−0.276** ⇒ 「R² = 0」不是零点，均值基线才是。`single_feature_baseline` 在 random 下 **0.508**，比 ridge（0.376）还高 |
| 3 | §10.3 threshold decision error 的阈值 `T` 来源未给 | 标 `not_instantiated_in_week21` | HOMO 通道没有来自外部设计要求/实验基准的阈值；**不事后挑一个有利阈值**（§10.3 自己禁止） |
| 4 | §10.2 selection regret 的 `T` 是模型而非真值，定义处缺交叉引用 | 本件把 `T` 明确为 reference layer（Batt），并在报告里写死 | Top-k regret：k=5 **0.7874 eV**、k=10 0.1003、k=15 0.1147 |
| 5 | §23「最小成果判据」11 项 ≈ Stage 0–9 全做，与 §29「8–12 周 MVP」矛盾 | 本仓切两层：MVP = Stage 0–1 + `P_0/P_1` + 单域 rank-stability | 本件落 Stage 0（8 条判词）与 Stage 1（6 条判词） |
| 6 | §19 Gate 只到 Stage 1，Stage 3/5 无 gate | 本仓为 Stage 3/5 各补一条**建议** gate，标注「本仓补」 | 见 `probes/artifacts/w21_stage_gate_verdicts.csv` 的 `detail` 列 |
| 7 | 核心命题缺反向证伪条件 | 写入本文件待议，**不进正式判词** | 见下节 §3 |
| 8 | 格式：13 处有序列表缺第 3 项；§23 有重复 `11.`；抬头文件名与实际文件名不一致 | **只在本次登记，不改原文** | 本仓副本保留原样 |
| 9 | §4.1 方向约定建议加 direction convention box | 本仓排序与 Top-k 强制使用 `P^ox = −ε_HOMO` | `reports/w21_rank_stability.md` §1 写明 |

## 2. W21 跑出来、预登记时还不知道的三条

| # | 观察 | 处置 |
| --- | --- | --- |
| 10 | §9.4 probabilistic pair ordering 的 `p_ij` 完全由单点 σ 假设决定；本仓 σ 取「留一残差绝对值」，是异方差且被离群点支配 | 本件照报（p>0.9 占 0.2755、p<0.1 占 0.2313、中间带 0.4932），并把 σ 的来源写进 prereg 的 `registered_limit`，**不掩饰** |
| 11 | 立项章 Tier 2 第 11 项写「把 `auc_gt15` / `auc_gt30` 加进 `METRIC_NAMES`」——**这条不该执行** | 该问题已由 W18 的 AUC sidecar 解决（`probes/artifacts/dielectric_auc_sidecar.csv` + `dielectric_splitters_auc.csv`），且 `tests/test_auc_sidecar_and_splitters.py` 明确断言 `METRIC_NAMES` 冻结为七项、不得含 AUC。**本件不执行该条**，登记为「立项章笔误」 |
| 12 | §13.3 的「60–100 个 core points 统计薄区」警告在本仓**实测触发** | 49 个可核点里只有 4 个家族成员 ≥5（aromatic_hydrocarbon / ester / ether / other），LOFO 只能报这 4 个家族；全部读数标 `machinery pilot` |

## 3. 待议：核心命题的反向证伪条件

框架的核心命题是「决定筛选可靠的是环境条件态与不确定性，不是更高的数值精度」。要让它可证伪，需要事先说清**什么观测会推翻它**。本仓提一条候选，供作者裁定，**本周不作判词**：

> 若在 `C_1`（Li⁺ 配位）条件态下，便宜层 `P_0` 与条件态 `P_1` 的排序一致率（Kendall τ_b）高于「把不确定性纳入后的可分辨一致率」，则「环境条件态是主要瓶颈」这一命题被削弱。

## 4. 红线（本件全程未触碰）

- 不引用 Reaxys 数值；不把 Batt 参考层当训练标签；不把 THEMol（CC BY-NC 4.0）值折进任何交付池。
- 不动 `0.4091179943351143` / `0.4766400383507876` / `0.5861142332208197` / `0.6216672295270079` 四个数。
- 不改框架原文的一个字节。