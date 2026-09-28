# W20-8 漏斗 KPI 定板 + 封顶修订（§28.64）

**性质**：登记 + 规范 + 轻量实测。本件**不拟合任何模型、不占主记分牌、不改写任何冻结件、不引用任何 Reaxys 数值**。

**产物**：`probes/w20_funnel_kpi.py`、`probes/w20_funnel_kpi_prereg.json`、`probes/w20_funnel_kpi_summary.json`、`tests/test_w20_funnel_kpi.py`、`probes/artifacts/w20_funnel_kpi_ranking.png`、本报告。

---

## 1 一句话结论

- **KPI 定板**：三组（排序类 / 覆盖与成本类 / 纪律类）挂 D6 排序键，共 12 条指标；排序类从既有**冻结** OOF 预测表重算（重算 baseline R² 与冻结基线 `0.4091179943351143` 逐位一致，确认口径无误）。
- **明令不做 R² KPI**：总诊断是「**排序学会了、量级学不会**」，R² 量的是量级 ⇒ 不入板（`FORBIDDEN_KPIS = ("r2",)`）。
- **命名纪律**：文献里的 KPI = *Knowledge-based electrolyte Property prediction Integration*（框架名）与自家漏斗 KPI 指标**同名不同物** ⇒ 本件只留一种用法（自家指标），另一种显式标注「文献框架名，与本文指标无关」。
- **封顶修订**：阶梯表「`0.58–0.65` 档（前提：化合物翻倍）」前提已被 W17 证否 ⇒ 标 `capped`；`161 → 157 → 153`、净新增上界 `+4`。

## 2 KPI 定板（三组，12 条）

| 组 | 指标 | 定义 | 状态 | 值 | 出处 |
| --- | --- | --- | --- | --- | --- |
| 排序类 | `auc_gt15` | ROC-AUC，目标 ε>15 | 实测 | `0.8947205768486257` | 冻结 OOF 预测表（pooled 4,570 行） |
| 排序类 | `auc_gt30` | ROC-AUC，目标 ε>30 | 实测 | `0.9392420870425322` | 同上 |
| 排序类 | `spearman` | 预测-真值秩相关 | 实测 | `0.7737616891926036` | 同上 |
| 排序类 | `top_k_enrichment` | 预测降序 top-k 中 ε>30 的富集倍数 | 实测 | k=10 `3.4275` / k=20 `3.617916666666667` / k=50 `2.5135000000000005` | 冻结 OOF，repeat 0（457 行，base rate `0.26258205689277897`） |
| 覆盖与成本类 | `scorable_compounds` | 可评分化合物数 | 实测 | `97` | `probes/dielectric_applicability_domain_summary.json` |
| 覆盖与成本类 | `in_domain_coverage` | D1 域内覆盖率 | 实测 | `0.5876288659793815`（57/97） | 同上 |
| 覆盖与成本类 | `compute_cost_per_candidate` | 每候选算力（xTB 单点 CPU 秒） | `defined_not_measured` | 未测 | —— |
| 覆盖与成本类 | `experiment_cost_per_candidate` | 每候选实验成本（一次介电测量） | `defined_not_measured` | 未测 | —— |
| 纪律类 | `promoted_false_count` | 本周未晋升 lane 数 | 实测 | `8` | W20 立项章 §1（8 条 lane，全 `promoted=false`） |
| 纪律类 | `main_scoreboard_attempts` | 本周主记分牌尝试数 | 实测 | `0`（累计 `11` 不变） | `probes/export_week18_results.py::MAIN_SCOREBOARD_CUMULATIVE_ATTEMPTS` |
| 纪律类 | `placebo_collapse` | 每 lane 一条安慰剂 | 政策 | 三条治理 lane 不拟合模型 ⇒ 安慰剂为**空消融** | 本件 `discipline_kpis()` |
| 纪律类 | `redline_violations` | 红线违规数 | 实测 | `0` | 本件 |

- **排序类只量「序」不量「幅」**：AUC>15 / AUC>30 / Spearman / top-k 富集都对单调变换不变，正是「排序学会了」该用的量。
- **`auc_gt15` / `auc_gt30` 的口径出处**：W18 已把二者加进 `probes/dielectric_representation_ablation.py::evaluate_repeat` 输出与 `*_repeats.csv`（本件先 `rg` 确认：`data/processed/dielectric_representation_ablation_repeats.csv` 含 `auc_gt15` / `auc_gt30` 两列，`has_auc_gt15 = true` / `has_auc_gt30 = true`）。
- **重算 arm（跑前声明）**：`protocol = paired_base`、`representation = Morgan+Physical`；其 pooled OOF R² 与冻结基线 `0.4091179943351143` **逐位一致**，证明本件的排序类重算在同一口径上。

## 3 明令不做 R² KPI

- 结论句：**排序学会了、量级学不会**。R² 是量级指标，与其成对失效的证据在册（Uni-Mol 块把 R² 从 `0.586` 砸到 `0.110`，而 AUC>30 只从 ~0.96 掉到 ~0.92 —— 掉的是量级、不是序）。
- 因此 `FORBIDDEN_KPIS = ("r2",)`，理由：R² 量的是量级，不是本漏斗要买的那个「序」。

## 4 命名纪律（同名不同物）

| 用法 | 含义 | 处置 |
| --- | --- | --- |
| **自家漏斗 KPI 指标** | 第 2 节三组 12 条指标 | **本件唯一保留的用法** |
| KPI = *Knowledge-based electrolyte Property prediction Integration*（DOI `10.1002/anie.202416506`） | 文献**框架名**（预测 MP/BP/FP 的知识-数据双驱动框架），**不是指标** | 显式标注「**文献框架名，与本文指标无关**」，不得与上式混用 |

## 5 封顶修订表

| 档 | R² | 载体 | 前提 | 修订前状态 | 修订后 |
| --- | --- | --- | --- | --- | --- |
| 下一档 | `0.58–0.65` | 化合物覆盖再翻倍 + 盲区靶向特征 + 目标变换 | **化合物覆盖再翻倍** | `next_rung` | **`capped`** |

**封顶链（写清）**：`161 → 157 → 153`。

- `161` = 最宽口径上界；`157` = `153 + 4` 的开放许可上界；`153` = 本仓在册开放许可化合物数。
- **净新增上界 `+4`**：W17 开放许可源二次复核（`reports/decisions_log.md` §28.36 / §28.37）给出新源 0 / 净新增 0，上限仍为 `153 + 4 = 157`。
- **前提已证否**：`0.58–0.65` 档假设「化合物覆盖再翻倍」（即上千量级），而开放许可约束下的真实上界只有 `+4`，与千位级差**两个数量级** ⇒ 该档**前提不成立**，标 `capped`。

## 6 边界与不可核（照实登记）

- **成本两项未测**：`compute_cost_per_candidate` / `experiment_cost_per_candidate` 只**定义单位**（xTB 单点 CPU 秒 / 一次介电测量），本周**未标定** ⇒ `defined_not_measured`；不得当成已测成本引用。
- **排序类口径限制**：pooled 4,570 行 = 457 行 × 10 repeat（同键重复计），只作**诊断口径**，**不得**当独立样本或新记分牌；top-k 富集用**单 repeat（repeat 0，457 行）**以避免重复计。
- **本件不占主记分牌**：重算既有冻结 OOF 表不是新尝试；`main_scoreboard_attempts = 0`、累计 `11` 不变。
- **`promoted_false_count = 8` 来自立项章声明的 lane 数**（W20 §1 八条 lane）；本件只登记，不代跑其它 lane。

## 7 数字出处

- 排序类（auc/spearman/top-k）⇒ `probes/artifacts/dielectric_coverage_paired_benchmark_predictions.csv`（sha256 `ad2a658a154a6376ca6a51ebc3e17a4d41147742a4a0ca5952dbd0615f5f4f71`）
- `auc_gt15` / `auc_gt30` 列出处 ⇒ `data/processed/dielectric_representation_ablation_repeats.csv`（sha256 `0987ae61b3efb4b883394e44057a7b704412491d29c031882dc17ed104795de9`）；owner `probes/dielectric_representation_ablation.py::evaluate_repeat`
- `97` / `57` ⇒ `probes/dielectric_applicability_domain_summary.json#endpoint.global` 与 `#endpoint.D1`
- 冻结基线 `0.4091179943351143` ⇒ `probes/export_week18_results.py::MAIN_SCOREBOARD`
- 累计尝试 `11` ⇒ `probes/export_week18_results.py::MAIN_SCOREBOARD_CUMULATIVE_ATTEMPTS`
- `161 / 157 / 153 / +4` ⇒ `reports/decisions_log.md` §28.36 / §28.37；阶梯表原文 `tests/fixtures/manual_appendix_j_snapshot.md::X-2`
- 文献框架名 KPI ⇒ `reports/kpi_framework_mapping.md`（DOI `10.1002/anie.202416506`）
- Uni-Mol 量级塌缩对证据 ⇒ `reports/decisions_log.md` §28.41（R² `0.110` vs AUC>30 ~0.92）

## 8 排序类 KPI 图

- 图：`probes/artifacts/w20_funnel_kpi_ranking.png`（matplotlib，`bbox_inches="tight"`，由 `probes/w20_funnel_kpi.py::write_figure` 重算冻结 OOF 表后落盘）。
- 左：top-k precision 曲线（k=10 `0.90` / k=20 `0.95` / k=50 `0.66`）对 base rate `0.26258205689277897`；右：top-k enrichment（`3.4275` / `3.617916666666667` / `2.5135000000000005`）与 pooled 排序类批注（`auc_gt15 = 0.8947205768486257`、`auc_gt30 = 0.9392420870425322`、Spearman `0.7737616891926036`）。
- 图的落点即本件结论句：**排序学会了、量级学不会**——序强（AUC / Spearman / top-k 均高），量级不入板（**R² 有意不是漏斗 KPI**）。
