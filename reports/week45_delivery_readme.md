# Week 45 交付说明

**本轮性质**：计算周。审计 W43 遗留的标定列、把 4668 行 xTB–Batt 分层、把 ~0.39 D 偶极偏置分层归因，并把三条治理守卫复跑成快照。
**shot 账本**：**0 shot，累计仍 19**。四条 lane 全是只读计算与治理复跑。
**冻结读数**：`0.4091179943351143` / `0.4766400383507876` / `0.5861142332208197` / `0.6216672295270079`，一个不动。

---

## 1. 判据总账

| lane | 标题 | 判据 |
| --- | --- | --- |
| W45-A | 扩展层标定列的保真与泄漏审计 | H45a1–H45a10：**10 成立** |
| W45-B | 4668 行 xTB–Batt 的分层残差与稳健离群 | H45b1–H45b10：**10 成立** |
| W45-C | 偶极偏置的分层归因 | H45c1–H45c10：**10 成立** |
| W45-D | 三条治理守卫 + 台账复跑快照 | H45d1–H45d7：**7 成立** |

**合计 37 条判据 = 37 成立 + 0 判否**（本轮无新增在册判否）。四个冻结读数未动，24 项 W45 测试全绿（含 `tests/test_repo_hygiene.py`）。

## 2. 关键读数与边界

- **标定列（W45-A）**：扩展层 `calib_homo_eV` 是 `homo_gfn2_eV` 的**精确一元仿射** `calib = 0.8702565775077505 * homo_gfn2 - 0.20421040258262516`（4668 行最大残差 **1.8e-15**），且与 `homo_gfn2 -> homo_batt` 的 in-sample OLS **逐位同映射**（slope/intercept 差 ≤ 4.4e-16）；449 行 `calibrated_estimate` 套用同一映射（残差 1.8e-15）。仿射保序 ⇒ ρ(calib, batt) 与 ρ(gfn2, batt) **完全相同**（差 0.0）：**标定只补电平（MAE 1.2066 → 0.3032 eV）不补序**。5 折 (按 InChIKey 哈希分折) out-of-sample 复拟合 MAE **0.30329 eV**、泄漏缺口 **1.3e-4 eV**。`calib_lumo_eV` 在 4668 行上**全为空**（标定只覆盖 homo，登记为已知边界 H45a7）。
- **分层残差（W45-B）**：总体 ρ 逐位复现 **0.5984785837315431**（bootstrap 95% CI **[0.5800, 0.6173]**、置换 p **0.0005**）。tier 分层同质：`calibration_bulk` **0.5974** / `flagship_dielectric` **0.5280** / `named_core_channel` **0.5130**（与 bulk 最大间距 0.084 < 0.15）。重原子数分层**单调退化**：5–12 **0.8107** / 13–17 **0.7315** / 18–40 **0.4810** ⇒ xTB 的排序信息集中在**小分子**上。Δgap 含 **6.9873 eV** 的系统电平差（MAD 0.6400 eV），故离群只能用**去中位后的稳健尺度**判：|z|>3.5 比例 **0.1165**。
- **偶极偏置（W45-C）**：重合 n = **103**，均值偏置 **+0.39451165048543685 D** 逐位复现 W42-C（bootstrap 95% CI **[0.2296, 0.5639]**、符号翻转置换 p 0.0005、Wilcoxon p **9.4e-11**）。分层：HBD 0/1/2+ 中位 **0.3793 / 0.4205 / 0.9831 D**；重原子数 1–5 / 6–7 / 8–9 中位 **0.3364 / 0.4424 / 0.4088 D**；**偶极三分位 low 0.0598 / mid 0.4817 / high 0.5207 D** ⇒ **偏置不是常量平移，而随偶极幅度增长**（偏置幅度 vs 偶极幅度秩相关 **0.4775**；vs 重原子数仅 **0.0234**，不是尺寸伪影）。这条直接支撑 W43-B 协议里 **affine 优先于 shift**。
- **守卫复跑（W45-D）**：准入闸门拒 3 个负对照、PubChemQC 过闸、未申报 **0**、运营性先验使用 **1**（全过闸）；逐轮验收 **42** 轮、**34** 轮声明、fail **0**、最近五轮全过；AST 静态守卫 **365** 文件、mutation **0**、冻结读数写入 **0**、未登记晋升 **0**；台账登记负结果并集 **9**、冻结读数越界 **0**、累计 shot 上限 **19**。闸门判决表与 W43 准入表逐项一致。

## 3. 复现

```powershell
$env:PYTHONIOENCODING="utf-8"; $env:OMP_NUM_THREADS=1; $env:OPENBLAS_NUM_THREADS=1
python probes\w45_calibration_audit.py
python probes\w45_stratified_residual.py
python probes\w45_dipole_strata.py
python probes\w45_governance_rerun.py
python -m pytest tests\test_repo_hygiene.py tests\test_w45_calibration_audit.py tests\test_w45_stratified_residual.py tests\test_w45_dipole_strata.py tests\test_w45_governance_rerun.py -q -p no:cacheprovider
python probes\export_week45_results.py --overwrite
```
