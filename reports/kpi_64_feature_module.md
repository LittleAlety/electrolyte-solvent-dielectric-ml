# KPI 64 维分子特征模块（复刻报告）

**产物**：`src/electrolyte_ml/kpi_descriptors.py`（实现）、`tests/test_kpi_descriptors.py`（35 项测试）

**任务来源**：执行手册附录 AA-3「KPI SI 五件战利品」第 1 件 —— 把 KPI 论文的 64 维描述符全表搬成本仓可调用模块。

---

## 1 定义来源与证据链

### 1.1 正文 PDF 不含该表（已实测）

正文副本 `C:/Users/Little Alety/Downloads/Angew Chem Int Ed - 2024 - Gao - A Knowledge Data Dual-Driven Framework for Predicting the Molecular Properties of.pdf`
（注意文件名里的连字符是 U+2010，不是 ASCII `-`）**12 页 / 51,680 字符**。用 `pypdf` 6.19.0 全文提取后，`Table S` 只出现 **1 次**，是一次指向 SI 的引用；`S6`/`S7`/`S8`/`S9` 各只出现 1–2 次且均为指代。**正文里没有 64 特征表。**

### 1.2 SI 里有全表（提取成功）

同目录下的 SI 副本 `anie202416506-sup-0001-misc_information.pdf`，**64 页 / 43,992 字符**。提取后定位到：

| 内容 | 提取文本中的字符位置 | 判据 |
| --- | --- | --- |
| Table S6（原子数与质量，7 列） | 25,973 | `Table S6. The descriptors representing the number and mass of atoms in molecules.` |
| Table S7（键性质，17 列） | 26,471 | `Table S7. The descriptors representing the nature of bonds in molecules.` |
| Table S8（官能团，32 列） | 27,310 | `Table S8. The descriptors representing the functional groups in molecules.` |
| Table S9（电子性质，8 列） | 28,719 | `Table S9. The descriptors representing the electronic properties of molecules.` |
| SI 第 4 节「Molecular feature extraction」 | 5,097 | 给出 AvgI/AvgA/AvgX 的求和公式与“primarily constructed using the RDKit toolkit” |

提取出的 64 个缩写已**逐字**抄进 `tests/test_kpi_descriptors.py` 的 `PAPER_ABBREVIATIONS` 常量（手抄，不从被测模块派生），并断言 `KPI_COLUMNS == PAPER_ABBREVIATIONS`。

### 1.3 SI 明确给出的公式（逐字复刻的依据）

> AvgI, AvgA, and AvgX are defined as the first ionization energy, electron affinity, and electronegativity of each element multiplied by the number of atoms of that element in the molecule, averaged over the total number of atoms in the molecule.
>
> `AvgM = (x·E(A) + y·E(B) + z·E(C)) / (x + y + z)`

**关键推论（有实测后果）**：分母是「total number of atoms in the molecule」，**包含氢**。
实现里若对隐式氢分子直接 `Mol.GetAtoms()`，水会算成 AvgX = 3.44（只有氧），正确值是 (2×2.20 + 3.44)/3 = **2.6133**。
本模块因此在元素平均与 ValE 两处显式 `Chem.AddHs`，并由测试钉住。

### 1.4 SI **没有**给出的东西

- 任何一条官能团/键型的 SMARTS 或计数规则（只有英文词条与缩写）；
- 元素性质**值表**本身（Pauling 电负性/第一电离能/电子亲和的数值一个都没印）；
- 部分电荷（MaxPC/MinPC/MaxAPC/MinAPC）用的**电荷模型**；
- 最长碳链的算法细节（只说用 NetworkX 枚举「all possible simple paths between each pair of atoms」）。

---

## 2 逐列定义

「保真度」四档：**逐字复刻**（论文/手册给了公式或名字）、**RDKit 原生**（论文点名用 RDKit，该量与 RDKit 同名描述符一一对应）、**本仓自写**（论文只给措辞，由本模块选定 SMARTS/图算法）、**未确证**（论文完全没说方法）。

### Table S6 —— 原子数与质量（7 列）

| # | 缩写 | 论文释义 | 保真度 | 实现 |
| --- | --- | --- | --- | --- |
| 1 | `Molwt` | Molecular weight | RDKit 原生 | rdkit.Chem.Descriptors.MolWt（平均分子量，含同位素加权） |
| 2 | `#Heavy` | Number of heavy atoms (any atoms other than hydrogen) | RDKit 原生 | Mol.GetNumHeavyAtoms()，即非氢原子数 |
| 3 | `#C` | Number of carbon atoms | 本仓自写 | 原子计数：原子序数 6 的原子个数 |
| 4 | `#O` | Number of oxygen atoms | 本仓自写 | 原子计数：原子序数 8 的原子个数 |
| 5 | `#O/#C` | Ratio of oxygen atoms to carbon atoms | 本仓自写 | #O / #C；#C == 0 时按约定记为 0.0（论文的比值在此处数学上未定义） |
| 6 | `#Het` | Number of heteroatoms | 本仓自写 | 既非 C 也非 H 的原子计数 |
| 7 | `#Het/#C` | Ratio of heteroatoms to carbon atoms | 本仓自写 | #Het / #C；#C == 0 时按约定记为 0.0 |

### Table S7 —— 键的性质（17 列）

| # | 缩写 | 论文释义 | 保真度 | 实现 |
| --- | --- | --- | --- | --- |
| 1 | `#R=R` | Number of double bonds | 本仓自写 | RDKit 键型为 DOUBLE 的键计数（字面读法的“全部双键”，含 S=O、N=O） |
| 2 | `#R#R` | Number of triple bonds | 本仓自写 | RDKit 键型为 TRIPLE 的键计数 |
| 3 | `#Donor` | Number of hydrogen bond donors | RDKit 原生 | rdkit.Chem.Lipinski.NumHDonors（RDKit 的 Lipinski HBD 定义） |
| 4 | `#Accept` | Number of hydrogen bond acceptors | RDKit 原生 | rdkit.Chem.Lipinski.NumHAcceptors（RDKit 的 Lipinski HBA 定义） |
| 5 | `#Rot` | Number of rotatable bonds | RDKit 原生 | rdkit.Chem.Lipinski.NumRotatableBonds（RDKit 默认严格定义） |
| 6 | `#Ring` | Number of rings | RDKit 原生 | rdkit.Chem.rdMolDescriptors.CalcNumRings（SSSR 环数） |
| 7 | `#Nring` | Number of atoms on the maximum ring | 本仓自写 | SSSR（AtomRings）中最大环的原子个数；无环记 0 |
| 8 | `#AlCR` | Number of aliphatic carbocycles | RDKit 原生 | CalcNumAliphaticCarbocycles |
| 9 | `#AlHR` | Number of aliphatic heterocycles | RDKit 原生 | CalcNumAliphaticHeterocycles |
| 10 | `#AlR` | Number of aliphatic rings | RDKit 原生 | CalcNumAliphaticRings |
| 11 | `#ArCR` | Number of aromatic carbocycles | RDKit 原生 | CalcNumAromaticCarbocycles |
| 12 | `#ArHR` | Number of aromatic heterocycles | RDKit 原生 | CalcNumAromaticHeterocycles |
| 13 | `#ArR` | Number of aromatic rings | RDKit 原生 | CalcNumAromaticRings |
| 14 | `#SCR` | Number of saturated carbocycles | RDKit 原生 | CalcNumSaturatedCarbocycles |
| 15 | `#SHR` | Number of saturated heterocycles | RDKit 原生 | CalcNumSaturatedHeterocycles |
| 16 | `#SR` | Number of saturated rings | RDKit 原生 | CalcNumSaturatedRings |
| 17 | `#Bran` | Number of branches | 本仓自写 | 碳骨架最长简单路径（分支限界 DFS，平局按原子索引升序）之外、且与链上碳直接相连的碳原子数 |

### Table S8 —— 官能团（32 列）

| # | 缩写 | 论文释义 | 保真度 | 实现 |
| --- | --- | --- | --- | --- |
| 1 | `#OH` | Number of hydroxyl groups | 本仓自写 | SMARTS [OX2H] |
| 2 | `#AlOH` | Number of aliphatic hydroxyl groups | 本仓自写 | SMARTS [OX2H][CX4] |
| 3 | `#ArOH` | Number of aromatic hydroxyl groups | 本仓自写 | SMARTS [OX2H]c |
| 4 | `#COO` | Number of carboxylic acids | 本仓自写 | SMARTS [CX3](=[OX1])[OX2H1] |
| 5 | `#AlCOO` | Number of aliphatic carboxylic acids | 本仓自写 | SMARTS [CX4][CX3](=[OX1])[OX2H1] |
| 6 | `#ArCOO` | Number of aromatic carboxylic acids | 本仓自写 | SMARTS c[CX3](=[OX1])[OX2H1] |
| 7 | `#C=O` | Number of carbonyl O | 本仓自写 | SMARTS [CX3]=[OX1] |
| 8 | `#C=O\COO` | Number of carbonyl O, excluding COOH | 本仓自写 | #C=O − #COO（论文把这一列写成“excluding COOH”的派生量） |
| 9 | `#Ether` | Number of ether oxygens (including phenoxy) | 本仓自写 | SMARTS [OD2]([#6])[#6]（含 phenoxy） |
| 10 | `#Ester` | Number of esters | 本仓自写 | SMARTS [CX3](=[OX1])[OX2H0][#6]，按锚原子去重（否则环状碳酸酯被计两次） |
| 11 | `#Halogen` | Number of halogens | 本仓自写 | SMARTS [F,Cl,Br,I] |
| 12 | `#Benzene` | Number of benzene rings | 本仓自写 | 环信息法：6 元、全碳、全芳香环的个数（萘记 2） |
| 13 | `#Ar-N` | Number of aromatic nitrogens | 本仓自写 | SMARTS [n]（芳香氮原子个数） |
| 14 | `#ArN` | Number of N functional groups attached to aromatics | 本仓自写 | SMARTS [NX3,NX2;+0;!$([n]);!$([NX3][CX3]=[OX1])]-c |
| 15 | `#ArNH` | Number of aromatic amines | 本仓自写 | SMARTS [NX3;H1,H2;!$([NX3][CX3]=[OX1])]-c |
| 16 | `#Imine` | Number of imines | 本仓自写 | SMARTS [CX3]=[NX2] |
| 17 | `#NH2` | Number of primary amines | 本仓自写 | SMARTS [NX3;H2;+0;!$([NX3][CX3]=[OX1])]（排除酰胺） |
| 18 | `#NH1` | Number of secondary amines | 本仓自写 | SMARTS [NX3;H1;+0;!$([NX3][CX3]=[OX1])]（排除酰胺） |
| 19 | `#NH0` | Number of tertiary amines | 本仓自写 | SMARTS [NX3;H0;+0;!$([NX3][CX3]=[OX1])]（排除酰胺与带电氮，如硝基） |
| 20 | `#SH` | Number of thiol groups | 本仓自写 | SMARTS [SX2H] |
| 21 | `#Aldehyde` | Number of aldehydes | 本仓自写 | SMARTS [CX3H1](=[OX1])[#6] |
| 22 | `#Amide` | Number of amides | 本仓自写 | SMARTS [NX3][CX3]=[OX1] |
| 23 | `#Aniline` | Number of anilines | 本仓自写 | SMARTS [NX3;+0;!$([NX3][CX3]=[OX1])]-c1ccccc1 |
| 24 | `#Phenol` | Number of phenols | 本仓自写 | SMARTS [OX2H]c1ccccc1，按氧锚原子去重（邻苯二酚记 2） |
| 25 | `#Epoxide` | Number of epoxide rings | 本仓自写 | SMARTS [OX2r3]（三元环内氧） |
| 26 | `#Furan` | Number of furan rings | 本仓自写 | SMARTS c1ccoc1 |
| 27 | `#Piperdine` | Number of piperdine rings | 本仓自写 | SMARTS C1CCNCC1（哌嗪不匹配） |
| 28 | `#Pyridine` | Number of pyridine rings | 本仓自写 | SMARTS c1ccncc1（嘧啶不匹配） |
| 29 | `#Lactone` | Number of cyclic esters (lactones) | 本仓自写 | SMARTS [CX3;R](=[OX1])[OX2;R][#6]，按羰基碳去重 |
| 30 | `#Ketone` | Number of ketones | 本仓自写 | SMARTS [#6][CX3](=[OX1])[#6]（两侧皆为碳，故排除酯/酸/酰胺/醛） |
| 31 | `#Nitrile` | Number of nitriles | 本仓自写 | SMARTS [NX1]#[CX2] |
| 32 | `#Sulfone` | Number of sulfone groups | 本仓自写 | SMARTS [$([#16](=[#8])(=[#8]))]（也命中磺酰胺/硫酸酯的 S） |

### Table S9 —— 电子性质（8 列）

| # | 缩写 | 论文释义 | 保真度 | 实现 |
| --- | --- | --- | --- | --- |
| 1 | `AvgX` | Average electronegativity | 逐字复刻（值表另择） | SI 公式：Σ 各元素原子数 × Pauling 电负性 ÷ 总原子数（含氢） |
| 2 | `AvgI` | Average ionization energy | 逐字复刻（值表另择） | SI 公式：Σ 各元素原子数 × 第一电离能(eV) ÷ 总原子数（含氢） |
| 3 | `AvgA` | Average electron affinity | 逐字复刻（值表另择） | SI 公式：Σ 各元素原子数 × 电子亲和能(eV) ÷ 总原子数（含氢） |
| 4 | `MaxAPC` | Maximum absolute partial charge | 未确证 | max |Gasteiger 电荷|（在按 SMILES 画出的分子上，即隐式氢；氢不参与） |
| 5 | `MinAPC` | Minimum absolute partial charge | 未确证 | min |Gasteiger 电荷| |
| 6 | `MaxPC` | Maximum partial charge | 未确证 | max Gasteiger 电荷 |
| 7 | `MinPC` | Minimum partial charge | 未确证 | min Gasteiger 电荷 |
| 8 | `ValE` | Number of valence electrons | 本仓自写 | Σ 各原子（含氢）外层电子数，取 RDKit PeriodicTable.GetNOuterElecs |

---

## 3 保真度汇总

| 档位 | 列数 |
| --- | --- |
| 逐字复刻（值表另择） | 3 |
| RDKit 原生 | 15 |
| 本仓自写 | 42 |
| 未确证 | 4 |
| **合计** | **64** |

其中「逐字复刻」严格说只有 **3 列**（AvgX/AvgI/AvgA）：公式逐字来自 SI，但**元素值表是论文没印的**，本模块采用 CRC Handbook 的 Pauling 电负性与 NIST ASD 的第一电离能/电子亲和能，属于另择来源。

---

## 4 未确证列清单

以下列**必须**视为「本仓替论文做的选择」，不是复刻结果。

| 列名 | 本模块采用的近似定义 | 不确定原因 |
| --- | --- | --- |
| `MaxPC` | 分子内 Gasteiger 电荷的最大值（在按 SMILES 画出的分子上计算，即**隐式氢**，氢不带电荷） | SI 从未说明电荷模型（Gasteiger / MMFF94 / QEq / 量子化学皆未提）；也从未说明是否加显式氢 |
| `MinPC` | Gasteiger 电荷的最小值 | 同上 |
| `MaxAPC` | max \|Gasteiger 电荷\| | 同上；「absolute partial charge」指绝对值这一点由列名可推，但模型不可推 |
| `MinAPC` | min \|Gasteiger 电荷\| | 同上 |

**已知后果（两种离子液体）**：
名册 246 条里有 2 条是六氟磷酸盐离子液体（`CCCCn1cc[n+](C)c1.F[P-](F)(F)(F)(F)F` 与其 2-甲基同系物）。
RDKit 的 Gasteiger 参数表没有 P、F 之外的 P–F 参数，这 7 个原子（1 个 P + 6 个 F）会得到非有限的电荷值。
模块采用**显式 0.0 兜底**并单独暴露 `charge_fallback_atoms(smiles)`，测试钉住「恰好 2 条分子、每条 7 个原子」——
这样将来若有人换了电荷模型或改了分子，读数不会静默漂移。

**值表选择（AvgX/AvgI/AvgA）同样是本仓选择**：论文没印元素值表，若作者用的是别的数据源，这三列会系统性偏移。
本模块采用：Pauling 电负性（CRC 97th ed.）、第一电离能 eV（NIST ASD）、电子亲和能 eV（NIST ASD，**氮取 −0.070 eV 不截断为 0**）。

---

## 5 与 KPI 原文的差异（逐条）

1. **不是 byte 级复刻**。本模块是「同名同序 + 公式照抄 + 未给部分显式自选」，不能声称与论文私有管线逐位一致。
2. **`#Bran` 的算法不同**。论文用 NetworkX 枚举全部简单路径；本模块用分支限界 DFS 求最长简单路径（指数最坏情况被剪枝压住），平局按原子索引升序固定。对同一分子两者可能给出**不同**的最长链（当存在多条等长链时），从而 `#Bran` 可能差 1。
3. **`#Nring` 用 SSSR**。论文说「the number of atoms in the largest ring within the molecule」；本模块取 RDKit SSSR 环集合中的最大环。对桥环/大环体系 SSSR 的最小环基可能不含直觉上的「最大环」。
4. **`#R=R` 计全部双键**。论文措辞是「Number of double bonds」，本模块字面执行，因此 DMSO 的 S=O、硝基的 N=O 都计入（DMSO `#R=R` = 1、环丁砜 = 2）。若作者的 R 特指碳，这两列会系统性偏高。
5. **官能团计数按锚原子去重**。裸 `GetSubstructMatches` 会把碳酸乙烯酯的酯基算两次（两个环氧各给一次匹配）。本模块对每个 SMARTS 以**第一个匹配原子**为锚去重，碳酸乙烯酯得 `#Ester = 1`、`#Lactone = 1`。
6. **比率列的 #C = 0 约定**。`#O/#C`、`#Het/#C` 在无碳分子上数学未定义；本模块记 0.0（水：两列皆 0.0）。名册 246 条全部有碳，故该约定只影响测试用的探针分子。
7. **`#Donor`/`#Accept` 用 RDKit 的 Lipinski 定义**。RDKit 的 `NumHDonors` 要求 O/S 上恰有 1 个氢，因此**水会得到 0**（化学直觉是 2）。论文只说「primarily constructed using the RDKit toolkit」，未指明具体定义；本模块选择 RDKit 原生定义并在此披露该边界。
8. **元素白名单外的元素**。论文的适用域白名单是 {H,C,N,O,F,Si,P,S,Cl,Br,I}；名册里另有 **B（4 条）、Fe（1 条，五羰基铁）、Si（1 条）**。其中 B 与 Si 有值表条目，**Fe 三个元素性质表都没有，取 0.0 参与平均**。`element_coverage()` 会把这件事报出来，测试断言 Fe 的存在不被静默忽略。

---

## 6 边界与使用须知

- **本模块不预测任何性质**。它只产特征；任何「用了 KPI 特征所以精度应该更好」的说法都必须走本仓既有的预注册 + GroupKFold 判决流程。
- **不接冻结管线**。`data/dielectric_v03.csv`、`data/processed/dielectric_observations_v11plus.csv` 等冻结文件只被**读**（测试里读 246 条 SMILES 做 NaN 率断言），没有任何写回。
- **零网络依赖**。模块只用 RDKit，可完全离线复跑。
- **NaN 率**。对名册 246 条 SMILES 全表 64×246 = **15,744 格，非有限值 0 格**（测试 `test_every_roster_smiles_is_describable_without_a_single_nan`）。
- **解析失败是硬错误**。不能解析的 SMILES 抛 `ValueError`，绝不静默变成一行 0。
- **列名里的反斜杠**。`#C=O\COO` 这一列名按论文原样保留反斜杠；写 CSV 时无影响，但在某些 shell/正则场景需要转义。

