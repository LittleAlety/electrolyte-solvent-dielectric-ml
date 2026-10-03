# Week 40 交付说明

**本轮性质**：**四个已登记项合并交付**（README §11 条目），四条都是后验读数或治理件，**不重拟合主记分牌、不新增特征列、不改 `METRIC_NAMES`**。
**0 shot（累计仍 19）**，四个冻结读数（`0.4091179943351143` / `0.4766400383507876` / `0.5861142332208197` / `0.6216672295270079`）一个没动。四条探针各自 `exit 0`，判否项全部在 `REGISTERED_NEGATIVES` 中登记。

**一句话**：本轮把「**判据怎么问**」「**写入器稳不稳**」「**域规则准不准**」「**轨道层的第二方是谁**」四件收口——其中 W40-A 更正了 W38-A 的**假判否**（那是问法问题），W40-C 更正了**旧域口径高估域分离**（读数因此变保守），W40-D 更正了 W38-D 「325 GB 不可行」的**过粗措辞**。

## 1. lane 与读数

| lane | 回答 | 关键读数 | 判据 |
| --- | --- | --- | --- |
| **W40-A** 三条判据改法 | 反解预算 / 相对与盲区 / 比值判据，能不能把三条旧判否救回来 | tau=30 反解 `alpha* = 0.06`（精度 **0.9000**，推荐 **10** 条；锚点 alpha=0.05 精度 **1.000** / 6 条）；十分位 `|d eps|` 中位比 **0.651822**（p = 0.0）、盲区 **26** 对含 **4** 对 ≥ 5；五个干净阶梯比值 **21.044062 / 13.712271 / 8.092207 / 4.178785 / 7.272894**，AUC30 极差上限 **0.018851** | H40a1–H40a14（**14 条 = 13 成立 + 1 已登记判否**） |
| **W40-B** 稳定写入迁移（含**例外登记**） | README §11 第 19 条那 110 件待迁移，迁完没有 | 分母 **121 = 已迁移 95 + 有理由不迁移 19（22 个 owner）+ 待迁移 0 + 无写入器历史产物 7**；全仓「未用稳定写入**且未登记例外**的 owner」= **0**；抽样三支探针各两遍 `new_dirty_paths = []`；另有 **33** 件易变键（`wall_seconds` 等）**只登记不宣称已迁** | H40b1–H40b9（**9 条全成立**） |
| **W40-C** Onsager 域精化 | 域规则精化后，谁被改判、域比还站得住吗 | 只改判 **3** 条（water A→B、1-Butanethiol 与 1-Pentanethiol B→A）；新域间比 **2.581713**（旧 **2.5016162961750874** 逐位复现）；**高介电族域比 15.650360 → 13.404448**（旧口径高估）；双 μ `Spearman(g_rel)` **0.800684**（n = 76），域比 **2.891737 vs 2.885677**（相对差 0.0021）；偶极偏置校正后 **3.113253**（相对变化 **0.205886 > 0.10**）；水 `g_rel` **2.2506** < 给体域中位 **2.5817** | H40c1–H40c13（**13 条 = 11 成立 + 2 已登记判否**） |
| **W40-D** 轨道外部对照层 | QM9 当第二方，能替代还是只能排序 | 覆盖 **103 / 241**；Spearman **0.885628**、Kendall **0.711442**、Pearson **0.840944**；未标定 MAE **2.532944 eV**、绝对差中位 **2.577390 eV**、**102/103** 条 ≥ 1 eV；留一标定 MAE **1.601998 eV**（降 **36.8% < 50%**）；标定式复现 W39（`matches_w39 = True`）；PubChemQC 最小分片 **536126834 B < 1 GiB**，`b3lyp` 6 config 合计 **7669431815893 B ≈ 7.67 TB** | H40d1–H40d10（**10 条 = 9 成立 + 1 已登记判否**） |

**合计 46 条判据 = 42 成立 + 4 已登记判否**（H40a5 / H40c10 / H40c11 / H40d8）。

## 2. 必须并读的边界

- **W40-A 的第一要求是「阶梯定义干净」。** W28 那 13 个臂若混进阶梯池，AUC30 极差会从 0.005561 抬到 **0.543814**（约 98 倍），比值被压到 **1.293 ⇒ 假判否**。探针已加 `grid_fixed_` 前缀过滤并补入 W29 阶梯。**不得**用比值判据去救**已知被污染**的池子。
- **W40-B 的稳定写入 = 「同一内容不重记时间」，只忽略 `generated_at_utc` / `elapsed_seconds` 两个键。** 那 **33** 件带 `wall_seconds` / `started_at_utc` / `finished_at_utc` 的写入器只被**登记**，**未**处理 ⇒ 不得宣称「产物不再变」。
- **W40-B 有 22 个 owner 是「不能迁移」而不是「不需要迁移」。** 三类理由：字节被**冻结摘要 / 锁前预注册**钉死（16）、写入站点是**追加写**（3）、原写入器带 **`allow_nan=False`**（3；1 个与第 2 类重叠）。**例外登记不是豁免**：这 22 个 owner 重跑**仍会弄脏工作树**，属明确保留的已知代价；`H40b9` 只保证「理由非空、且被登记的 owner 确实不含稳定写入」，**不**保证它们不脏树。
- **7 件无写入器历史产物**（`probes/g1plus_*_evidence.json`、`probes/w19_safety_channel_registry.json` 等）只有读者、没有写入者，因此不构成脏树来源；这不等于它们是稳定写入。
- **W40-C 的域间比是相关读数，不是因果。** 且名册里两种酰胺写作**亚胺醇式** ⇒ 「酰胺共振」假设在本名册**零作用、未被检验**，不得据此宣称否证酰胺机制。两套 μ 的 `g_rel` **只比中位数与秩，不比绝对值**（QM9 只覆盖 103 个命中化合物，第二套 μ 只在该子集成立）。
- **W40-D 的 QM9 层级不同**（B3LYP/6-31G(2df,p) 气相 vs xTB GFN2 单点）⇒ **只能排序与标定，不能互换**；标定后的 eV **不得**写进标签池或特征列。单位写死 Hartree（1 Ha = 27.211386245988 eV）。
- **W38-D 更正**：PubChemQC 真阻塞在**可定位性**（无 CID 索引、无 parquet 分支、本机 PubChem 不可达），不在单文件体积。不得把 0.5 GiB 分片解读成「W38-D 判错了」——它判的是**整库不可行**，方向没错，措辞过粗。
- **分母纪律**：名册分母 **241** 行（`data/processed/dielectric_physical_features_v03.csv`）；246 / 247 行属 `data/dielectric_v03.csv` 口径，**两者不得混引**。

## 3. 包里有什么

| 类别 | 路径 |
| --- | --- |
| 探针 | `probes/w40_criteria_reform.py`、`probes/w40_timestamp_migration.py`、`probes/w40_onsager_domain.py`、`probes/w40_orbital_external.py` |
| 产物 | `probes/artifacts/w40_conformal_inversion.csv`（64 行）、`w40_similarity_bins.csv`（10 行）、`w40_ladder_ratio.csv`（5 行）、`w40_timestamp_inventory.csv`、`w40_onsager_domain_compounds.csv`（241 行）、`w40_onsager_domain_summary.csv`、`w40_orbital_external_control.csv`（103 行）、`w40_orbital_channels_update.csv` 及四份 summary |
| 图 | `probes/artifacts/w40_criteria_reform.png`、`w40_onsager_domain.png`、`w40_orbital_external.png` |
| 报告 | `reports/w40_criteria_reform.md`、`reports/w40_timestamp_migration.md`、`reports/w40_onsager_domain.md`、`reports/w40_orbital_external.md`、`reports/week40_project_charter.md`、`reports/work_log_week37_to_week40.md` |
| 测试 | `tests/test_w40_criteria_reform.py`（12）、`test_w40_timestamp_migration.py`（11）、`test_w40_onsager_domain.py`（15）、`test_w40_orbital_external.py`（13） |
| 论文 | `paper/paper_zh_draft_v2.md` v1.4 —— 新增 §3.22–§3.28（含 W40-A/C/D 三节），摘要新增「主结果四 / 主结果五」，附录 B 补 N-23 至 N-28 |
| 导出 | `probes/export_week40_results.py` |

> **第三方数据集内容不进交付包**：QM9（CC BY 4.0）只按路径 + sha256 复现；本包携带的图与表**均为本轮产物**。
>
> **W40-B 是本轮改动面最大的一件**（迁移涉及 113 个 probe/test 文件，其中 **22 个已回退**），但它是卫生件，**不产生读数**。回退清单 = `EXEMPT_WRITERS`（见 `probes/w40_timestamp_migration.py`）。

## 4. 复现

```
.venv\Scripts\python.exe probes\w40_criteria_reform.py
.venv\Scripts\python.exe probes\w40_timestamp_migration.py
.venv\Scripts\python.exe probes\w40_onsager_domain.py
.venv\Scripts\python.exe probes\w40_orbital_external.py
.venv\Scripts\python.exe -m pytest tests\test_repo_hygiene.py tests\test_w40_criteria_reform.py tests\test_w40_timestamp_migration.py tests\test_w40_onsager_domain.py tests\test_w40_orbital_external.py -q -p no:cacheprovider
.venv\Scripts\python.exe paper\build_paper_v2.py
.venv\Scripts\python.exe scripts\check_paper_artifact_consistency.py
.venv\Scripts\python.exe probes\export_week40_results.py --overwrite
```

## 5. 下一份预注册要处理的三件（已登记）

1. **阶梯池的准入规则要写进预注册**：比值判据必须先声明哪些臂进池（W40-A 已证明污染会让结论从「成立」翻成「判否」），否则每次都要事后清洗。
2. **W40-C 的 `H40c10` 判否要落地成稳健性条款**：域间比对偶极系统偏置敏感（相对变化 0.2059 > 0.10）⇒ 下一份预注册若再引域比，必须**同时报偏置未校正与校正后两个读数**。
3. **W40-D 之后轨道通道的口径**：QM9 只能作排序先验；若要在 HOMO/LUMO 通道上加权重，需先补一个**同层级**的外部源（Batt-P30K 的 ωB97X-V 层），并把「层级不同」写进适用域声明。
4. **例外登记表的准入规则（W40-B 登记）**：`EXEMPT_WRITERS` 目前按三类理由登记 22 个 owner，但准入规则只写在探针里 ⇒ 下一份预注册要把「新增例外只能落在三类之内」「被冻结点名的脚本改字节要走解冻/更正流程」「例外件重跑脏树继续当已知代价报出」三件写死。
