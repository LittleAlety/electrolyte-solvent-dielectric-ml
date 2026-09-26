# 杠杆 4：xTB 全表迁移（v0.4 构象平均偶极）

> 本文的数字全部从 `probes/dielectric_xtb_full_table_migration_summary.json` 与三个落盘产物逐字读取；摘要与报告同源，
> 改一处必须重跑 `probes/dielectric_xtb_full_table_migration.py`。

## 一、口径与预注册状态

- 杠杆 4 **不在** `probes/dielectric_r2_levers_prereg.json` 的覆盖范围内（该文件只锁杠杆 2/3/7）；本杠杆的判据在脚本内、
  **跑之前**写死：`PASS_DELTA_R2 = +0.0100`、`INERT_DELTA_R2 = 0.0000`，取自附录 X 的 +0.01~+0.03 期望带的**下沿**，不是带内任一点。
- 主记分牌：457 行 / 97 化合物，GroupKFold by InChIKey，50 折（5 折 × 10 重复），seed 42，
  min_test_rows_per_fold=2；折划分来自 `probes/dielectric_coverage_paired_benchmark.py` 的 `masked_splits`，
  本探针**不重建**折号（`mask_reused_not_rebuilt = true`）。
- 基线复现：脚本内重跑未改动的 `paired_base` → **0.4091179943351143**，与发布值逐位相同（|Δ| = 0.000e+00，容差 1e-09）→ 复现成立，delta 方可引用。
- shots：**1 枪**（本杠杆唯一一次对主记分牌的正式读取）。

## 二、v0.4 协议（跑之前写死）

- 几何：RDKit ETKDGv3，numConfs=8，MMFF94（UFF 兜底），seed = 42 + 名册序号；
- 电子结构：每个构象一次 GFN2 **单点**（`xtb <input.xyz> --gfn 2 --chrg <q> --uhf 0`，**不带 --opt**），
  每个构象在**清空过的独立目录**里跑，防止上一构象的 `xtbrestart` 当重启文件污染收敛偶极；
- 聚合：构象偶极的**算术平均**（Boltzmann 平均并列上报，不进判决）；
- 只迁移两列：`dipole_D`、`mu_sq_over_Vm = dipole² / V_m`（V_m 取**冻结**值；几何迁移另立 pending），其余 11 列冻结。

## 三、主记分牌读数（混合表 `Morgan+Physical`）

| 臂 | R² 均值 | R² 标准差 | MAE | RMSE | Spearman | MAE·ε>60 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 基线臂（原地重跑） | 0.4091179943351143 | 0.088967 | 8.0407 | 14.0504 | 0.7763 | 55.7131 |
| 迁移臂（v0.4 偶极） | 0.4649564468823552 | 0.063522 | 7.2733 | 13.3805 | 0.8274 | 55.1153 |
| 安慰剂臂（偶极跨化合物置换） | 0.3298988035441514 | 0.107557 | — | — | — | — |

- **ΔR²（迁移 − 基线）= 0.0558384525472409**
- 逐列口径：ΔMAE = -0.7674、ΔRMSE = -0.6699、ΔSpearman = +0.0511、ΔMAE·ε>60 = -0.5978、ΔMAE·ε<20 = -0.8522
- 重复级标准差同时收窄 0.088967 → 0.063522（−28.6%）；这是**附带观察**，不是本杠杆的判据。

## 四、机制旁证（同一次跑里就有）

- 纯 `Physical` 表示：0.2531659995294713 → **0.4226563729289389**（+0.1695）。迁移动的就是物理块，增益也落在物理块上。
- 纯 `Morgan` 表示：四个臂**逐位相同** 0.06487386371009436（Morgan 特征不含偶极）→ 评分行、折划分、模型与分母在四臂间完全一致，
  差异只可能来自被迁移的两列。
- 三臂的 50 个 `(repeat, fold)` 格里 `(inchikey, T_K)` 集合**逐位同一**（独立复算确认）；`paired_base_random_row_leak` 的签名与之不同（它本来就是行级切分）。

## 五、安慰剂与泄漏参照

- 安慰剂臂 `paired_base_conformer_dipole_shuffled`：把 274 个构象均值**跨化合物置换**（边际分布逐位保留），同一折、同一模型、同一超参。
  - R² = 0.3298988035441514 → **control_delta_r2 = -0.0792191907909630**
  - 探针 docstring 里跑前写死的判据是「控制的 delta 若**也复现**增益，即判为噪声」。迁移 +0.0558 vs 控制 -0.0792，间距 **0.1351**
    → 置换**没有**复现增益，增益不是「偶极数值分布」带来的 → 门过。
  - 摘要另有一个布尔字段 `control_collapsed`（定义 = |shuffled − baseline| ≤ 0.02）= **false**。该字段问的是
    「安慰剂是否落到基线上」，对**数值置换**臂按构造不可能成立（与杠杆 2/3 报告里记的同一处口径含糊）。本轮照实上报，
    **不用它替代上面的判据，也不事后改写它**。
- 泄漏参照（**只此一次、不进任何判决**）：`paired_base_random_row_leak` 行级切分 R² = **0.7385332681453336**。
  行级切分把同一化合物的不同温度点放到两侧，正是 GroupKFold 存在的理由 —— 它只用来量这个泄漏有多大。

## 六、成本（实测，非外推）

| 项 | 值 |
| --- | ---: |
| 名册化合物 / 实测成功 | 276 / 274 |
| xTB 累计 | 244.02 s |
| 构象嵌入累计 | 11.71 s |
| 墙钟（xTB 阶段全程） | 268.62 s（4.5 min） |
| 每化合物 xTB（mean / median / max / min） | 0.8906 / 0.6615 / 5.3073 / 0.5078 s |
| 重原子回归 | slope 0.1051 s·atom⁻¹，intercept 0.0912 s |
| 全表外推 | 245.8 s（按实测均值线性外推；名册最重 28 重原子） |

- 时间预算 2400 s，实际只用了 268.6 s（11%）→ **没有触发 bounded pilot**；
  `completeness` 之所以不是 `whole_table`，是覆盖原因（见第八节），不是时间原因。
- 冻结 v0.3 对照（`probes/p5b_xtb_timing.csv`，5 个化合物，**带 --opt**）：单构象 0.134–0.235 s。本轮每个**单点**约
  0.111 s（0.8906/8），即 v0.4 用 8× 的偶极采样换来比冻结 --opt 更便宜的单点；该表是冷缓存下单构象的 --opt 成本，
  **不是**同口径比值。

## 七、判决

- **verdict = `pass`**：ΔR² = **+0.0558** ≥ 写死的 +0.0100；基线逐位复现；安慰剂未复现增益。
  - 英文判决句（摘要原文）：_the v0.4 conformer-averaged dipole migrates the main scoreboard by +0.0558 R2, at or above the +0.0100 the lever was written for_
- 是否进入合并臂：本轮合并规则属**杠杆 2/3/7** 的预注册范围（`if_nothing_passes` 那条），杠杆 4 不自作合并；v0.4 偶极迁移作为
  数据面改动进入 v0.4 目录候选，最终是否落表由主线集成者按周计划裁决。

## 八、诚实边界（不许省略）

- **覆盖是 95/97，不是 97/97**：`conformer_coverage.scored_compounds_migrated = 95`，`readings.completeness = "partial_coverage"`。
  2 个失败化合物**都是多组分咪唑鎓盐**：
  - `1-ethyl-3-methylimidazolium diethyl phosphate`（`HQWOEDCLDNFWEV-UHFFFAOYSA-M`，SMILES `CCOP(=O)([O-])OCC.CCn1cc[n+](C)c1`）
  - `1-ethyl-2,3-dimethylimidazolium bis[(trifluoromethyl)sulfonyl]imide`（`XDJYSDBSJWNTQT-UHFFFAOYSA-N`，SMILES `CCn1cc[n+](C)c1C.O=S(=O)([N-]S(=O)(=O)C(F)(F)F)C(F)(F)F`）
  - 失败原因是 **SCF 不收敛**：工作目录留下 `.sccnotconverged`，手动复跑原命令得到
    `*** convergence criteria cannot be satisfied within 250 iterations ***` 与 `Self consistent charge iterator did not converge`，exit=128。
- **失败是「逐构象」的，被 fail-fast 策略放大**：诊断复跑（只改 `--etemp`，**不进判决**；证据落在 `probes/dielectric_xtb_migration_scf_diagnostic.json`）显示 `HQWOEDCLDNFWEV` 的 8 个构象里只有 0、5 号 exit 128、
  其余 6 个正常收敛；`XDJYSDBSJWNTQT` 只有 4 号失败、其余 7 个正常。加 `--etemp 500` / `--etemp 1000` 的 exit 码**逐位不变**（etemp 对这 2 个化合物无效）。
  探针的 `run_conformer_compound` 是**首个失败即整化合物判失败**的 fail-fast 策略，所以 1/8 个坏构象就把整个化合物挡在迁移之外；要拿到 whole-table 覆盖，
  需要「舍弃不收敛构象、对余下构象取平均」的**宽容策略**，那是跑后新增的协议变体，本轮**故意不跑**（不事后改口径）。
- 机制早有记载：`probes/xtb_fragment_geometry_defect.py` 与 `probes/xtb_recovery_probe.py` 记录过 —— 单个 ETKDG 调用嵌入**不连通图**时片段互相重叠，
  这类多片段离子对在冻结调用下就是 exit 128；同类离子对的恢复旗标先例见 `probes/g1plus_xtb_recovery_probe.json`。这 2 行的冻结偶极来自 v0.3 缓存
  （`_feature_source = frozen_v03`，`xtb_version 6.7.1pre`）。
  这 2 行**保留冻结偶极**，所以本轮读数是「迁移 95/97 化合物（2027/2029 行）」的效果，**不是全表**。
- 迁移账目（独立复算，非引用摘要）：2027 行带 v0.4 偶极、2 行保持冻结；其中 2019 行数值确实改变，另 8 行属于偶极**恰为 0.0** 的
  对称分子（迁移前后同值）；除 `dipole_D`/`mu_sq_over_Vm` 外**全部物理列逐位未变**；`mu_sq_over_Vm` 在每一迁移行都等于
  `dipole² / 冻结摩尔体积`（逐位，atol 1e-12），`rows_without_a_frozen_molar_volume = 0`。
- 独立复算：从落盘的 `..._predictions.csv` 逐折重算 R²，基线与迁移两臂与摘要**逐位相同**（0.4091179943351143 / 0.4649564468823552），
  600 个折行的 R² 与落盘折表最大差 **0.000e+00**。
- **几何迁移仍 pending**：`molecular_volume_A3`、`molar_volume_m3_mol`、`alpha_over_Vm` 未用 v0.4 构象重算；本轮只动偶极派生列。
- 聚合方式：迁移用**算术平均**（跑前写死）。Boltzmann 平均与算术平均最大差 23.41 D（1-甲基咪唑鎓溴化物，构象能差极大）、
  平均差 0.468 D —— 换聚合口径会改变个别化合物，本轮不动。
- 构象采样的事实：274 个成功化合物里 **86 个（31.4%）8 个构象给出完全相同的偶极**（刚性分子），**28.8% 的化合物构象极差 > 1 D**
  （这些分子的冻结单构象偶极确实只是 size-1 采样）；全表 `|构象均值 − 冻结偶极|` 均值 0.5978 D、中位 0.1080 D、
  Pooled Pearson 0.7695。
- 0.5332 / 0.5454 只能带池定义引用（147 化合物训练池 / 97 化合物固定评分池），**不得**与 v1.0 headline 0.364 直接比大小；
  本报告的 R² 全是「97 化合物固定评分池 / paired_base 折划分」口径。
- 冻结红线四条 INTACT（`data/dielectric_v03.csv`、`probes/l3_stage1_pilot_pool.csv`、`probes/l3_backvalidation_prereg.json`、
  `data/processed/dielectric_observations_v11plus.csv`），三个新 CSV 全为 LF。
- shots 计数与判决登记由主线集成者写入 `reports/decisions_log.md`；本探针不改该文件。

