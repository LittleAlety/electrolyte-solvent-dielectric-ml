# Week 39 交付说明

**本轮性质**：后验读数（一条 lane，三段）。**0 shot（累计仍 19）**，四个冻结读数
（`0.4091179943351143` / `0.4766400383507876` / `0.5861142332208197` / `0.6216672295270079`）一个没动。

**一句话**：本轮把 W38-D 侦察出来的第三条可商用轨道线**落到盘上（QM9，133,885 分子）**，
量出它与我们 xTB 层的**层级关系**，并让它当独立审计员把 W38-C 那条「偶极列有质量疑点」
从**一句话**变成**可分解的两个成因** —— 其中一个成因（构象自由度）**被证伪**。

## 1. lane 与读数

| 段 | 回答 | 关键读数 | 判据 |
| --- | --- | --- | --- |
| **W39-A** 层级对齐 | xTB 间隙与 B3LYP 间隙是什么关系 | 名册命中 **103 / 241**（三条轨道线最宽：Batt-P30K 73、Batt-SLM.smi 79）；Pearson **0.840944**、Spearman **0.885628**；中位数比 **0.705757**、MAE **2.532944 eV**；标定 `xTB = 2.026697·B3LYP − 8.872895`、标定 R² **0.707187**、残差 sd **2.056993 eV** | H39a1–H39a4（4 条） |
| **W39-B** 偶极质量审计 | 我们这一列错多大、错在哪 | Pearson **0.783697**、Spearman **0.802206**、MAE **0.610310 D**；绝对差 ≥ 1 D 的有 **13 / 103**；**刚性域中位绝对差 `0.4442 D` ≥ 柔性域 `0.4205 D`（H39a7 判否）**；刚性域仍被点名 5 例（formamide 0.439 vs 3.7286、NMA 1.593 vs 3.5402…） | H39a5–H39a7（3 条，**1 条已登记判否**） |
| **W39-C** 结论稳健性 | W38-C 的域比是不是 μ 来源的伪影 | 同一 103 子集、μ ≥ 1 D 门槛下，给体 / 非给体 `g_rel` 中位数比：**我们 2.980102** vs **QM9 3.045860**（给体侧 n = 29 / 29） | H39a8–H39a9（2 条） |

**合计 10 条判据 = 9 成立 + 1 条已登记判否（H39a7）**；另加 1 条输入指纹判据（H39a10，成立）。

## 2. 三条必须并读的边界

- **层级不同：只能谈排序与标定，不能直接互换。** QM9 是 **B3LYP/6-31G(2df,p) 气相**轨道能差，
  我们的是 **xTB GFN2 单点**。排序高度一致（Spearman 0.8856）而量级系统性压缩（中位数比 0.7058）
  ⇒ 这正是主记分牌那条「**排序学会了、量级学不会**」在描述符层面的同构读数，不是新纪录。
- **偶极的错被拆成两块，只有一块能定责到我们。** 在 **90/103** 个「基本一致」的化合物上，
  签署差（QM9 − 我们）的中位数是 **−0.3914 D** ⇒ 我们的列**系统性偏高约 0.4 D**（这是主项）；
  另有少数**两端都有**的极端样本（最小 −3.29 D 即 formamide、最大 +5.68 D 即 hexanedinitrile）。
  **刚性 / 柔性切分的作用**：刚性分子（可旋转键 = 0，n = 48）在两来源里必是同一构象，差异只能来自
  **来源本身**；柔性分子（n = 55）的差异可能只是 QM9 取了 anti 构象。**H39a7 判否**说明
  「刚性域的差异更小」**不成立** ⇒ 构象自由度不是主因，**系统偏置**才是。
- **W39-C 只作稳健性检查**：`g_rel` 是无量纲相对量（单位被斜率吸收），只可做域间比较，
  **不得与文献 g 绝对值对照**；本件不重开 W38-C、不改它的任何读数。

## 3. 包里有什么

| 类别 | 路径 |
| --- | --- |
| 外部层（**不入包**） | `data/external/qm9_dataset.csv`（28,637,864 B；sha256 `01d196218c78a0e29575ef8cf9ceb6d2f33fda9cddc3e4b5bd133e191fa2e053`；133,885 行；CC BY 4.0，署名 Ramakrishnan et al. 2014） |
| 探针 | `probes/w39_qm9_crosscheck.py` |
| 产物 | `probes/artifacts/w39_qm9_overlap.csv`（103 行逐化合物：两套间隙、两套偶极、可旋转键、ε、hbd、摩尔体积）、`probes/artifacts/w39_qm9_crosscheck_summary.json` |
| 图 | `probes/artifacts/w39_qm9_alignment.png`（左：间隙散点 + 标定线；右：偶极散点，绿 = 刚性 / 红 = 柔性） |
| 报告 | `reports/w39_qm9_crosscheck.md` |
| 测试 | `tests/test_w39_qm9_crosscheck.py`（**11 项全绿**） |
| 导出 | `probes/export_week39_results.py`（验证块：四核心注册表 + 论文产物一致性 + `tests/test_repo_hygiene.py` + W39 / W38-D 测试） |
| 立项 | `reports/week39_project_charter.md` |

> **第三方数据集内容不进交付包**：QM9 CSV 只按路径 + sha256 复现；本包携带的图与表**均为本轮产物**。
>
> **治理**：W39 的 summary 直接走 `probes/export_results_common.write_json_stable`，因此**重跑探针不会弄脏工作树**（不进 README §11 第 22 条那 110 件的时间戳迁移 backlog）；回归守卫见 `tests/test_w39_qm9_crosscheck.py::test_probe_writes_its_summary_with_the_stable_writer`。

## 4. 复现

```
.venv\Scripts\python.exe probes\w39_qm9_crosscheck.py
.venv\Scripts\python.exe -m pytest tests\test_repo_hygiene.py tests\test_w39_qm9_crosscheck.py -q -p no:cacheprovider
.venv\Scripts\python.exe probes\export_week39_results.py --overwrite
```

## 5. 下一份预注册要处理的两件（已登记）

1. **偶极列的双读数化**：W38-C 的 `g_rel` 主判据改为**同时报我们与 QM9 两套 μ**；
   在偏置来源（系统偏置 约 0.39 D + 少数极端样本）查清之前**不修数、不插补**。
2. **QM9 接轨道通道的外部对照层**（不是标签层）：口径按「只能排序与标定」；若要扩覆盖，
   走 PubChemQC 按名册命中的**单文件子集**（全量 7.7 / 8.4 TB 不可取），且不引入任何 NC 件。
