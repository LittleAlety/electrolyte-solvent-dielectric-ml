# Week 38 交付说明

**本轮性质**：后验读数 + 治理件。**0 shot（累计仍 19）**，四个冻结读数
（`0.4091179943351143` / `0.4766400383507876` / `0.5861142332208197` / `0.6216672295270079`）一个没动。

**一句话**：本轮把「拒答」从一个黑白开关升级成**有覆盖保证的推荐集合**，把「结构≠功能」从一句话变成
一条**可复算的谱**，把母体论文那条「单分子描述符传不了分子间关联」的诊断**钉到 Kirkwood–Onsager 的残差上**，
并修掉 README §11 最后一条未处理项。

## 1. 五条 lane

| lane | 回答 | 关键读数 | 判据 |
| --- | --- | --- | --- |
| **W38-A** 保形筛选举荐 | 拒答能不能变成带保证的短名单 | 行级覆盖 **0.9337 / 0.8858 / 0.8109**（α = 0.05 / 0.10 / 0.20，均 ≥ 1−α−0.05）；τ=30 上 α=0.05 给 **6** 条推荐、精度 **1.000**；α=0.10 给 **16** 条、精度 **0.8125** | 8 条（1 条**已登记判否** H38a2） |
| **W38-B** 结构≠功能 | 指纹相近的分子标签能差多少 | 结构-only 基线 R² **0.2502679**；Spearman(sim, \|Δε\|) = **−0.0607**（z **−2.163**、p 0.026）；**指纹盲区 26 对**（Tanimoto ≥ 0.99），4 对 \|Δε\| ≥ 5、最大 **13.25** | 7 条（1 条**已登记判否** H38b1） |
| **W38-C** Kirkwood-Onsager 残差 | 缺的那一维是不是取向相关 g | 给体域 / 非给体域 g_rel 中位数比 **2.5016**（z **4.076**、p 0.006）；leave-top-5-out **2.5597**；ε ≥ 60 族内给体子群比 **15.65** | 8 条 |
| **W38-E** 时间戳脏树收口 | 干净重导为什么不干净 | 连跑两次 W37 导出探针后，被跟踪 summary **相对 HEAD 无改动**；111 个带时间戳跟踪件已迁移 1 / 待迁移 110 | 6 条 |
| **W38-D** 数据侦察 | 四个核心量还有没有**合法**新来源 | 名册命中实测：Batt-P30K **73/241**（MIT）、Batt-SLM.smi **79/241**、RX-392 **10/241**、chew 粘度 **140/241**（**CC BY-NC 4.0**，不入商用池）、Chodera 介电 **45/241**（**GPL-2.0**，零频口径）、SolvFunc-87 **26/241**；三份 Batt-SLM 附属件与上游 git blob **逐字节相等**（不算新源）；真新增仅 CPI 两表（MIT，**无核心量标签**） | 9 条 |

**合计 38 条判据，36 成立 + 2 条已登记判否。**

## 2. 三条必须并读的边界

- **覆盖是边际覆盖**，不是给定化合物上的后验概率。W38-A 的 α=0.10 / τ=15 上，每个 repeat 约 49 个评估
  化合物里有 **42.1** 个落在未决区，而「确信为低」的拒答几乎为零 ⇒ 在这个池规模上，**漏斗的真实约束是
  可判定性，不是精度**。
- **W38-C 的 `g_rel` 是无量纲相对量**，单位被斜率吸收，只可做域间比较。`dipole_D` / `mu_sq_over_Vm`
  有质量疑点（formamide 0.439 D、NMA 1.593 D 与实验值差数倍），且 `L/x` 在 μ → 0 处**发散**
  （环戊烷 μ = 0.001 D → g_rel 7.2e5）；因此主判据全用中位数/秩，另加 μ ≥ 1.0 D 的数值门槛。
- **W38-E 的状态是「机制已修、迁移未完成」**（1/111），第 19 条**不算关闭**。

## 3. 包里有什么

| 类别 | 路径 |
| --- | --- |
| 探针 | `probes/w38_conformal_shortlist.py`、`probes/w38_structure_function.py`、`probes/w38_onsager_residual.py`、`probes/w38_summary_timestamp.py`、`probes/w38_data_recon.py` |
| 共享件 | `probes/export_results_common.py`（新增 `write_json_stable`） |
| 产物 | `probes/artifacts/w38_{conformal_coverage,conformal_shortlist,structure_nn,structure_pairs,onsager_compounds,onsager_domains,timestamp_inventory,recon_hits,recon_channels}.csv`、`probes/artifacts/w38_*_summary.json` |
| 图 | `w38_conformal_coverage.png`（覆盖-规模）、`w38_structure_function.png`（相似度-标签差 / 1-NN）、`w38_onsager_g.png`（域间 g_rel）、`w38_recon_hits.png`（外部件名册覆盖率 × 许可类别） |
| 报告 | `reports/w38_{conformal_shortlist,structure_function,onsager_residual,timestamp_closeout,data_recon}.md` |
| 测试 | `tests/test_w38_{conformal_shortlist,structure_function,onsager_residual,summary_timestamp,data_recon}.py`（34 项全绿） |
| 立项 | `reports/week38_project_charter.md` |

## 4. 复现

```
.venv\Scripts\python.exe probes\w38_conformal_shortlist.py
.venv\Scripts\python.exe probes\w38_structure_function.py
.venv\Scripts\python.exe probes\w38_onsager_residual.py
.venv\Scripts\python.exe probes\w38_summary_timestamp.py
.venv\Scripts\python.exe probes\w38_data_recon.py
.venv\Scripts\python.exe -m pytest tests/test_w38_conformal_shortlist.py tests/test_w38_structure_function.py tests/test_w38_onsager_residual.py tests/test_w38_summary_timestamp.py tests/test_w38_data_recon.py -q -p no:cacheprovider
.venv\Scripts\python.exe probes\export_week38_results.py --overwrite
```

## 5. 下一份预注册要处理的三件（已登记）

1. **H38a2 反解**：把「固定 alpha 判精度」改成「达到 precision ≥ 0.90 所需的最小预算 `alpha*`」，
   并把短名单规模一并入判据（阈值不原地改）。
2. **H38b1 改判据**：绝对标签差阈值换成相对判据 + 指纹盲区判据（后者已在 W38-B 以事后读数交付）。
3. **剩余 110 个带时间戳跟踪件迁移 + Onsager 域规则精化**（改用显式的「可给体质子」定义，
   并加偶极质量审计）。

## 6. W38-D 带出来的三条数据线（登记，未执行）

1. **可商用轨道线变宽**：`molssiai-hub/pubchemqc-{b3lyp,pm6}`（**CC-BY-4.0**，含
   `energy-{alpha,beta}-homo/lumo/gap`）+ QM9 原始 deposition（**CC BY 4.0**）。
   动作：只按名册命中化合物的**单文件子集**取数，不取整仓（7.7 / 8.4 TB）。
2. **η 线封在 NC 上**：覆盖最高的 140/241 是 CC BY-NC 4.0 ⇒ 只能做非商业内部对照；
   要进商用池必须另找源，或接受 η 通道停在组键 MAE 0.1748 / 门 0.15。
3. **红线清单化**：NIST WebBook / DDBST / Cheméo / MNSol / QMugs / THEMol /
   MolSSI liquid-electrolytes 一律不入池，渠道表 `probes/artifacts/w38_recon_channels.csv`
   是准入清单。