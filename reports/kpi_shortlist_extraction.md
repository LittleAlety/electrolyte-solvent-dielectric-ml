# KPI 论文 SI 图 S20 / S21 短名单抠取（15 + 14 = 29 行）

**产物**：`data/reference/kpi_15_14_shortlists.csv`（机读表，29 行）、`probes/kpi_shortlist_extraction_summary.json`（摘要）、`probes/kpi_shortlist_extraction.py`（探针）、`tests/test_kpi_shortlist_extraction.py`（单测）。

**论文**：Gao, Yuan, Huang, Yao, Yu, Chen, Zhang, Chen, Angew. Chem. Int. Ed. 2025, 64, e202416506, DOI 10.1002/anie.202416506。

**来源物料**：SI `anie202416506-sup-0001-misc_information.pdf`（64 页 / 43929 字符，sha256 5609c5edb5192829...）；正文 12 页，只用于口径对表。两份 PDF 都不入仓（`.gitignore` 排除所有 `*.pdf`）。

**纪律**：`source_kind=compilation_from_published_si`、`redistributable=false`、`usage=cross_check_only`。

---

## 1 抠取口径

pypdf 提取 SI 与正文的文字层；SI 64 页 / 43929 字符。

图 S20 / S21 的化合物块只存在于栅格图里：两页文字层只有图注，每页只有 1 张整页 <image>，没有可定位的文字对象，整个 SI 文字层里也没有任何 CAS 号形状的字符串。因此 29 行由图块目视转录（非 OCR 自动识别）。

**残余风险**：人工误读单个数字是主要的残余风险。本探针用五道机检把误读压到可发现：① 29 行且 15/14 分片；② 每行满足 MP<230 K、BP>430 K、FP>360 K；③ 除已登记的 1 行外每行 FP<BP；④ 15 个 CAS 全过标准校验位算法；⑤ 14 条 SMILES 全部能被 RDKit 解析。机检能证伪，不能证明与图逐字一致。

本探针不向仓库写任何 PDF 全文或页面转储；只写 CSV、摘要与本报告。

| 短名单 | 图 | PDF 页 | SI 页签 | 图上印刷的字段 |
| --- | --- | --- | --- | --- |
| 15 | Figure S20 | 32 | SI31 | skeletal formula、CAS ID、MP、BP、FP |
| 14 | Figure S21 | 33 | SI32 | skeletal formula、SMILES、MP、BP、FP |

图注（逐字取自 SI 文字层）：

- 短名单 15（Figure S20）：Figure S20. Fifteen molecules with Chemical Abstracts Service Registry Number (CAS ID) were obtained from the high-throughput screening. The skeletal formula, CAS ID, MP, BP, and FP of each molecule are listed.
- 短名单 14（Figure S21）：Figure S 21. Fourteen molecules with CAS ID were obtained from the high - throughput screening. The skeletal formula, SMILES, MP, BP, and FP of each molecule are listed.

---

## 2 逐行清单（29 行）

rank 是图内阅读顺序：先左右、再上下。数值一律保持图上的印刷形式。

### 2.1 短名单 15 —— 带 CAS ID（Fig. S20）

| rank | cas | mp_k | bp_k | fp_k |
| --- | --- | --- | --- | --- |
| 1 | 96-48-0 | 228.2 | 477.2 | 371.5 |
| 2 | 108-32-7 | 224.4 | 514.8 | 389.2 |
| 3 | 4437-69-8 | 222.6 | 504.3 | 369.8 |
| 4 | 4437-70-1 | 217.3 | 513.9 | 367.4 |
| 5 | 4437-85-8 | 216.9 | 514.2 | 514.2 |
| 6 | 6975-71-9 | 227.8 | 491.8 | 365.0 |
| 7 | 623-35-8 | 220.9 | 493.2 | 384.9 |
| 8 | 17611-82-4 | 220.8 | 499.5 | 381.0 |
| 9 | 4172-97-8 | 228.9 | 503.3 | 372.8 |
| 10 | 32091-48-8 | 211.0 | 508.8 | 383.3 |
| 11 | 15074-49-4 | 221.2 | 509.7 | 374.7 |
| 12 | 4553-62-2 | 220.8 | 508.6 | 380.6 |
| 13 | 16525-39-6 | 228.7 | 519.4 | 383.2 |
| 14 | 6959-71-3 | 202.6 | 467.2 | 361.4 |
| 15 | 35633-50-2 | 221.6 | 490.1 | 368.1 |

### 2.2 短名单 14 —— 不带 CAS ID（Fig. S21）

| rank | smiles | mp_k | bp_k | fp_k |
| --- | --- | --- | --- | --- |
| 1 | O=COCC1COCO1 | 229.2 | 458.3 | 360.6 |
| 2 | N#CCCCC1CCC1 | 225.4 | 489.3 | 362.0 |
| 3 | N#CCCC1=CCCC1 | 223.9 | 492.6 | 363.2 |
| 4 | N#CCCC1(CC1)C#N | 228.0 | 525.0 | 387.0 |
| 5 | CCC(CC#N)CC#N | 222.3 | 513.8 | 381.3 |
| 6 | CC(CCC#N)CC#N | 219.3 | 519.2 | 382.0 |
| 7 | CCC(CCC#N)C#N | 223.3 | 514.2 | 381.8 |
| 8 | C#CCCOCCCC#N | 224.7 | 477.2 | 361.9 |
| 9 | CC(COCC#N)C#N | 226.4 | 497.7 | 378.4 |
| 10 | CC(CCOC=O)C#N | 227.7 | 474.8 | 361.7 |
| 11 | CC(COC=O)CC#N | 221.4 | 476.7 | 363.8 |
| 12 | CC(CCC#N)C1CO1 | 226.1 | 499.2 | 360.7 |
| 13 | N#CCCOC1CCC1 | 226.4 | 476.5 | 365.8 |
| 14 | CC1COCC1CC#N | 228.7 | 492.9 | 361.0 |

---

## 3 级联漏斗（论文声称值，未经复算）

| 级 | 论文声称 | 出处 |
| --- | --- | --- |
| QM9 起始分子数 | 133,885 | SI §11 |
| 结构过滤后（去掉 -OH / -COOH，Molwt < 600，#Heavy < 30） | 51,001 | SI §11 |
| MP < 230 K | 13,155 | SI §11 |
| BP > 430 K | 3,619 | SI §11 |
| FP > 360 K | 35 | SI §11 |
| 分拆：带 CAS ID | 15 | SI §11 |
| 分拆：不带 CAS ID | 20 | SI §11 |
| 不带 CAS 的 20 个再过 SAscore > 0.9 | 14 | SI §11 |

**未复算声明**：以上全部是论文声称值，未经我方复算：本仓不复现 QM9 的 133,885 分子池，也不复现 SOTA 模型的 MP/BP/FP 预测，因此漏斗的任何一级都无法验证。本探针只把它们登记下来，供与 SI 印刷文字对表。

SI §11 原文（逐字，空白已折叠）：

> SI11 discover valuable new molecules. 11. High-throughput screening A total of 133,885 molecules from the QM9 [14] dataset were collected and converted to standard SMILES. All molecules had their MPs, BPs, and FPs predicted using SOTA models. Initially, structural screening was applied to all molecules, removing those containing active hydrogen groups (–OH, –COOH) and restricting the Molwt to less than 600 and the #Heavy to less than 30, resulting in 51,001 molecules remaining. Next, molecules were sequentially screened based on ranges set for MPs, BPs, and FPs. The criteria required MPs below 230 K, BPs above 430 K, and FPs above 360 K, leaving 13,155, 3,619, and 35 molecules, respectively. Finally, the resulting molecules were categorized into two groups, which include 15 and 20 molecules with and without CAS ID, respectively. The molecules without CAS ID were further evaluated for synthetic feasibility using the retrosynthetic accessibility score, retaining those with scores greater than 0.9, ultimately 14 molecules were identified.

---

## 4 字段覆盖率

| 字段 | 非空行数 | 覆盖率 | SI 里有吗 | 说明 |
| --- | --- | --- | --- | --- |
| `cas` | 15 / 29 | 51.72% | Fig. S20 每块印 CAS ID；Fig. S21 一块都不印 | 非空 15/29；100% 只成立于短名单 15 这一半，短名单 14 的 CAS 在 SI 里不存在。 |
| `smiles` | 14 / 29 | 48.28% | Fig. S21 每块印 SMILES；Fig. S20 只画骨架式 | 非空 14/29；S20 的 15 行没有印刷 SMILES，本表不用结构感知回填。 |
| `molwt` | 0 / 29 | 0.00% | 两图都不印 | 0/29；SI 只印了 Molwt < 600 这道闸门，没有逐分子数值。 |
| `mp_k` | 29 / 29 | 100.00% | 两图都印 | 29/29，按图上的印刷形式整字转录。 |
| `bp_k` | 29 / 29 | 100.00% | 两图都印 | 29/29，按图上的印刷形式整字转录。 |
| `fp_k` | 29 / 29 | 100.00% | 两图都印 | 29/29，按图上的印刷形式整字转录。 |
| `source_figure` | 29 / 29 | 100.00% | 两图都印 | 29/29。 |
| `source_page` | 29 / 29 | 100.00% | 两图都印 | 29/29；数值是 PDF 页码（1 基），SI 自己印的页签另存一列。 |

---

## 5 与派单预期 / 正文的口径差异

| 检查 | 结果 | 说明 |
| --- | --- | --- |
| si_vs_handoff_expectation | match | SI 印刷值 133885 -> 51001 -> 13155 -> 3619 -> 35 |
| si_vs_handoff_thresholds | match | SI 印刷阈值 MP<230 K / BP>430 K / FP>360 K，与派单给的同一组阈值 |
| si_cas_split_recorded | match | SI 明写 35 个再拆成 15（带 CAS）与 20（不带 CAS），这 20 个再过 SAscore>0.9 得 14 个；派单只写了 15+14，未写 20 这一中间层。 |
| main_text_vs_si_thresholds | documented_difference | 正文结果段印 MP<230 K / BP>430 K / FP>360 K（与 SI 一致），但正文 Figure 5 图注印 MP<250 K / BP>450 K / FP>380 K；本报告以 SI 实际文字 230/430/360 为准。 |
| shortlists_satisfy_the_published_gates | pass | 29 行全部满足 MP<230 K、BP>430 K、FP>360 K；不满足的行：无 |
| main_text_abstract_cas_split | match | 正文摘要写 Fifteen and fourteen molecules, with and without CAS ID, respectively：15 个带 CAS、14 个不带，与 SI 图 S21 只印 SMILES 一致，与其图注自称 with CAS ID 矛盾。 |

**与派单的差异**：派单写的级联「133,885 → 51,001 → 13,155 → 3,619 → 35 → 15+14」与 SI §11 完全一致，SI 的实际文字里没有任何一个数字与它不同。唯一要补的是：SI 在 15 与 14 之间还印了一层「20」——35 拆成 15（带 CAS）与 20（不带 CAS），20 个再过 SAscore > 0.9 得 14；派单把这一步压缩成了「CAS 分拆 + SAscore>0.9」。

---

## 6 异常与未解事项

1. `fp_equals_bp_on_shortlist_15_rank_5`（15/5）：CAS 4437-85-8 那一块把 FP 印成 514.2 K，与同一块的 BP 514.2 K 相等；其余 28 行都满足 FP < BP。本表照实转录该印刷值、未做修正，并把这一对 (15, 5) 钉成唯一允许的例外。
2. `figure_s21_caption_contradicts_the_screening_text`（14/*）：Fig. S21 图注自称 Fourteen molecules with CAS ID，但同页每块印的是 SMILES 而不是 CAS ID；SI §11、正文摘要与正文结果段都写这 14 个 without CAS ID。本表以 SI §11 与正文的叙述为准，Fig. S21 的图注记为 SI 自相矛盾。
3. `figure_s21_caption_spacing`（14/*）：SI 把该图注排版成 Figure S 21.（S 与 21 之间带空格），本表统一写作 Figure S21。
4. `main_text_figure5_caption_quotes_other_thresholds`（不针对具体行）：正文 Figure 5 图注写 MP<250 K / BP>450 K / FP>380 K，而 SI §11 与正文结果段写 230/430/360 K。本报告以 SI 实际文字为准。
5. `cross_figure_identity_not_judged`（不针对具体行）：Fig. S20 只有骨架式、没有 SMILES，所以本表没有对两个短名单做跨图去重或同一性判定。任何跨图去重都必须先有结构感知流程把 S20 的 SMILES 补出来，那一步不在本次范围内。
6. `molwt_never_printed`（不针对具体行）：两图都不印分子量，molwt 列 29 行全空；本表不用 RDKit 回填。

---

## 7 机检清单

| 检查 | 结果 | 说明 |
| --- | --- | --- |
| row_count_is_29 | pass | 行数 = 29 |
| shortlist_split_is_15_14 | pass | shortlist 计数 = {14: 14, 15: 15} |
| ranks_run_1_to_n_per_shortlist | pass | 每个 shortlist 的 rank 为 1..n 连号 |
| every_row_carries_figure_and_page | pass | source_figure / source_page / source_page_label 全部非空；缺项行：无 |
| mp_k_is_numeric_on_every_row | pass | 异常值：[] |
| bp_k_is_numeric_on_every_row | pass | 异常值：[] |
| fp_k_is_numeric_on_every_row | pass | 异常值：[] |
| fp_below_bp_except_the_pinned_exception | pass | 除已登记异常外每行 FP < BP；越界行：无 |
| the_pinned_exception_is_still_present | pass | 实际 FP>=BP 的行 = [(15, 5)] |
| cas_filled_exactly_on_shortlist_15 | pass | 短名单 15 的 15 行全部有 CAS；短名单 14 的 14 行全部为空（SI 未印）。 |
| cas_check_digits_all_valid | pass | 15 个 CAS 全部通过标准校验位算法；未通过：无 |
| smiles_filled_exactly_on_shortlist_14 | pass | 短名单 14 的 14 行全部有 SMILES；短名单 15 的 15 行全部为空（SI 只印骨架式）。 |
| no_duplicate_cas_or_smiles | pass | 重复 CAS = []；重复 SMILES = [] |
| transcribed_smiles_parse_with_rdkit | pass | RDKit 解析 14 / 14 条 SMILES；失败：[] |
| derived_masses_respect_the_600_gate | pass | RDKit 派生的分子量区间 120.155 - 137.182（非 SI 印刷值） |

附：本仓派生值，不是 SI 印刷值，绝不写进 CSV 的 molwt 列——RDKit 解析 14 / 14 条 SMILES，派生分子量区间 120.155 - 137.182 g/mol，全部低于 600 这道闸门。

---

## 8 使用边界

- 本表逐字转录自已发表的 Angew. Chem. Int. Ed. 补充材料图 S20 / S21，属汇编级证据，只用于交叉核对（usage=cross_check_only）。本表不得当作可再分发的数据集（redistributable=false），也不得作为本仓数据集的来源注入冻结管线。
- 本表不进冻结管线：它只被 `tests/test_kpi_shortlist_extraction.py` 与交叉核对用途读取，不参与任何特征构造、训练或评分。
- 本表不是本仓数据集的证据来源：29 个分子的 MP/BP/FP 是论文模型给出的预测值，不是实验观测值。
- 零网络：探针与单测都只读本地文件。
- 图注里 `Figure S 21` 的空格、以及 FP 与 BP 相等的那一行，都属于「照实登记、不做修正」。
