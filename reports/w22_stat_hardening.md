# W22-2 排序统计加固（评审 B1 / B2 / B3 / B4）

按 `reports/week22_project_charter.md` 的 W22-2 节执行。池 = W21 排序臂：冻结 ε 名册 ∩ 我方 GFN2-xTB ∩ Batt 身份命中，**n = 49**，配对 1,176。
全部读数在**同一批 49 个化合物**上重抽样；点估计在原始 49 个化合物上直接计算。bootstrap 次数 = 5000，CI 方法 = percentile（2.5 / 50 / 97.5 分位），固定种子，无墙钟字段。

## 0. 结论摘要

- (a) 主通道 homo τ_b = 0.6888（95% CI [0.5684, 0.7974]）；lumo τ_b = 0.4660（[0.2620, 0.6342]）；gap τ_b = 0.3537（[0.2063, 0.4987]）。
- (b) 配对 Δτb(homo − lumo) = 0.2228，95% CI [-0.0087, 0.4852]，跨 0 ⇒ 该通道差只到提示级（suggestive）。
- (d) 三通道的置换 p 值经 Bonferroni / Holm 校正后全部 survives_correction；这与 (b) 的配对差是两个问题（见 §3 与 §5）。
- (e) 三通道共用同一批 49 个化合物，互不独立；n = 49 是 247 键 ε 名册的子集。

## 1. 口径复现（先证明口径一致，再看统计）

- 读入 `probes/artifacts/w21_rank_pairs.csv` **1176** 行；与从 `data/dielectric_v03.csv` × `data/processed/themol_orbital_layer.csv` 复算的逐 pair 表一致（dP0 最大舍入差 5.00e-07 eV，dRsol 最大舍入差 5.00e-07 eV，resolved_in_R_sol 不一致 0 条，inversion 不一致 0 条）。
- 复算的两侧都可分辨数 = 451，robust inversion = 0，与 W21 一致。

| 通道 | τ_b（复算） | τ_b（W21） | 差 | ρ（复算） | f_robust |
| --- | --- | --- | --- | --- | --- |
| homo | 0.6888 | 0.6888 | 0.00e+00 | 0.8640 | 0.0000 |
| lumo | 0.4660 | 0.4660 | 0.00e+00 | 0.6459 | 0.0000 |
| gap | 0.3537 | 0.3537 | 0.00e+00 | 0.5266 | nan |

## 2. (a) 化合物级 bootstrap 95% CI（点估计与 CI 同句）

| 通道 | 统计量 | 点估计 | 95% CI | draws_used |
| --- | --- | --- | --- | --- |
| homo | kendall_tau_b | 0.6888 | [0.5684, 0.7974] | 5000 |
| homo | spearman_rho | 0.8640 | [0.7487, 0.9301] | 5000 |
| homo | f_robust_inversion | 0.0000 | [0.0000, 0.0000] | 5000 |
| lumo | kendall_tau_b | 0.4660 | [0.2620, 0.6342] | 5000 |
| lumo | spearman_rho | 0.6459 | [0.3877, 0.8134] | 5000 |
| lumo | f_robust_inversion | 0.0000 | [0.0000, 0.0000] | 4947 |
| gap | kendall_tau_b | 0.3537 | [0.2063, 0.4987] | 5000 |
| gap | spearman_rho | 0.5266 | [0.3022, 0.6983] | 5000 |
| gap | f_robust_inversion | nan | [0.0000, 0.0000] | 1288 |

读法：τ_b 与 ρ 的 CI 是**化合物级**重抽样区间；f_robust_inversion 在 homo 上点估计为 0 且 CI 塌缩到 0（两侧都可分辨的 pair 在重抽样下仍几乎不出现符号翻转）。
读法：τ_b 与 ρ 的 CI 是**化合物级**重抽样区间；f_robust_inversion 在 homo 上点估计为 0 且 CI 塌缩到 0（两侧都可分辨的 pair 在重抽样下仍几乎不出现符号翻转）。gap 的全池 f_robust 无定义（两侧都可分辨的 pair 少于 5，§9.2 分母塌缩），只有部分重抽样能算，且都落在 0。

## 3. (b) 配对 bootstrap 的 delta_tau_b（B2 落地点）

| 比较 | 点估计 Δτb | 95% CI | 是否跨 0 | draws_used |
| --- | --- | --- | --- | --- |
| homo_minus_lumo | 0.2228 | [-0.0087, 0.4852] | 是 | 5000 |
| homo_minus_gap | 0.3350 | [0.1315, 0.5478] | 否 | 5000 |

同一批化合物进入两通道、逐 draw 相减，因此这是**配对** Δτb；CI 不跨 0 才说明通道间排序质量差异在一个抽样区间内站得住。

## 4. (c) 留一化合物敏感性（τ_b(homo)）

- 全池 τ_b = 0.6888；剔除单个化合物后 τ_b 落在 **[0.6791, 0.7163]**。
- 影响力最大的化合物：`JUJWROOIHBZHMG-UHFFFAOYSA-N`（Δτ_b = +0.0275）。
- 完整 49 行见 `probes/artifacts/w22_stat_hardening_leave_one_out.csv`。

## 5. (d) 多重比较校正（B3）

族 = homo / lumo / gap，m = 3；检验 = 单侧置换检验 τ_b > 0（打乱 R_sol 侧标签），置换 5000 次。

| 通道 | τ_b | p（置换） | p_Bonferroni | p_Holm | 判定 |
| --- | --- | --- | --- | --- | --- |
| homo | 0.6888 | 2.00e-04 | 6.00e-04 | 6.00e-04 | survives_correction |
| lumo | 0.4660 | 2.00e-04 | 6.00e-04 | 6.00e-04 | survives_correction |
| gap | 0.3537 | 4.00e-04 | 1.20e-03 | 6.00e-04 | survives_correction |

`gap` 无方向语义，只作对照；它的 p 值同样进族，不做后验剔除。

## 6. (e) 口径一致性审计（B4）

- **同一批 49 个化合物**：homo/lumo/gap 三通道读数取自同一批 49 个化合物，因此三条置换 p 值与三组 bootstrap CI 互不独立。
- **名册层级**：n=49 是 247 键 ε 名册（data/dielectric_v04.csv，248 行）的子集；W21 池规则用的是冻结的 246 键文件 data/dielectric_v03.csv。
- 不可互比的池：
  - 49 化合物轨道臂不可与 W20 funnel KPI 面板（457 行 / 97 化合物）合并——名册不同、端点不同
  - broad-pool 候选（w20_ranking_key_v1_candidates.csv）不属于本臂，不得并入这些 CI

## 7. 统计边界

- bootstrap gives a sampling interval for the 49-compound arm; it does NOT remove the non-independence of homo/lumo/gap (same compounds, same pool) nor the selection of the pool itself -- the arm is a machinery pilot, not a pass/fail gate
- bootstrap 不解决非独立性，也不解决池子选择问题：CI 只描述「同一设计、同一 49 化合物」下的抽样波动。
- 参考层物理不确定度（R_sol）本仓未量化，读数须与 W21 的容差口径一起阅读。

## 8. 产物清单（行数 / bytes / sha256）

| 产物 | 行数 | bytes | sha256 |
| --- | --- | --- | --- |
| `probes/w22_stat_hardening_prereg.json` | 101 | 3792 | `9e5960d67e496131aa17ae75100099f43c03922d218b95ba9edcd65aa6ee36bf` |
| `probes/artifacts/w22_stat_hardening_pair_bootstrap.csv` | 12 | 1545 | `667e4e1cd666ed51563e4ab4ee39e8f00e35bfda2ad68503193c43559d855652` |
| `probes/artifacts/w22_stat_hardening_leave_one_out.csv` | 50 | 4713 | `948901cc9495dc3fa762f9f8e8e2eed0bc3cbec7b35df7e7142c633f88d991c3` |
| `probes/artifacts/w22_stat_hardening_multiple_comparison.csv` | 4 | 647 | `b4dd97438cc6378e7773f8bbd9d935f0219b262eca61514a1c4d4ed19f506252` |
| `probes/w22_stat_hardening_summary.json` | 268 | 8946 | `75b130e2647c1aec581834aea471c0209b3a56d265e728638bc83d88e6c0e604` |

（报告自身不列入上表以避免自引用。）

## 9. 冻结件与纪律

- 主记分牌尝试：**0 次**（累计不变）；promoted = False。
- 冻结读数逐位不变：`[0.4091179943351143, 0.4766400383507876, 0.5861142332208197, 0.6216672295270079]`。

