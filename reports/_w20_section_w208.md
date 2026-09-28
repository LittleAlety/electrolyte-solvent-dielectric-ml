## 28.64 漏斗 KPI 定板与封顶修订：三组 12 条指标、明令不做 R²、阶梯封顶（2026-09-28）
|
**定位**：本件是 Week 20 lane W20-8（§28.64）的落地章，给筛选漏斗定一张**三组 12 条** KPI 板（挂 D6 排序键），并做一次**封顶修订**。全文见 `reports/w20_funnel_kpi.md`，排序类 KPI 图见 `probes/artifacts/w20_funnel_kpi_ranking.png`。|
**纪律**：`produces_reading = false`、`shot_number_taken = null`、`scoreboard_attempts_delta = 0`、`reaxys_values_used = 0`、`promoted = false`；主记分牌累计 11 次不变。|
**① 排序类实测（冻结 OOF 表重算）**：`auc_gt15 = 0.8947205768486257`、`auc_gt30 = 0.9392420870425322`、Spearman `0.7737616891926036`、top-20 precision `0.95` / enrichment `3.6179`（base rate `0.26258205689277897`）。|
**② R² 明确不是漏斗 KPI**：`forbidden_kpis = ["r2"]`；总诊断是「**排序学会了、量级学不会**」——R² 量的是量级，故不入板（`FORBIDDEN_KPIS = ("r2",)`，理由「ranking is learned and magnitude is not」）。|
**③ 封顶修订（带 refuted_by）**：阶梯档 `0.58–0.65`（前提：化合物覆盖再翻倍）由 `next_rung` 翻为 **`capped`**；封顶链 **161 → 157 → 153**，净新增上界 **+4**；`refuted_by = reports/decisions_log.md §28.36 / §28.37`（W17 开放许可源二次复核：新源 0 / 净新增 0）。|
**④ 命名纪律（同名不同物）**：文献 KPI = *Knowledge-based electrolyte Property prediction Integration*（DOI `10.1002/anie.202416506`）是**框架名**，与本仓漏斗 KPI 指标**同名不同物**，不得混用。|
**⑤ 隔离声明（永不可混）**：本 KPI 板**不得替换冻结的 ε 主记分牌**；排序类 pooled 4,570 行 = 457 行 × 10 repeat（同键重复计），只作诊断口径，不得当独立样本或新记分牌。|
|
