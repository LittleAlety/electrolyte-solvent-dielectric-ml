# 综述 → 仓库描述符映射（Task A / 杠杆 8）

来源论文（本地副本）：`C:\Users\Little Alety\Downloads\nz5c02291.pdf`
ACS Energy Letters 2025, 10, 4962−4982, DOI `10.1021/acsenergylett.5c02291`
标题：*Elucidating the Solvating Power of Solvents for Designing High-Performance Electrolytes in Lithium Batteries*

抽取方式：`pymupdf` 文本抽取（21 页 / 112,467 字符），未做 OCR。
文本转储存放在仓库**之外**（`%TEMP%\lever8\paper_text.txt`），避免污染兄弟任务的扫描型产物。

对比基准（冻结 v03 物理块，13 列）：
`T_K, formal_charge, heavy_atom_count, hbd, hba, tpsa_A2, molecular_volume_A3, dipole_D, polarizability_A3, mu_sq_over_Vm, alpha_over_Vm, total_energy_hartree, homo_lumo_gap_ev`

本地数据落点核实：
- `data/dielectric_v03.csv`（130,844 B）——名册/目标表，存在。
- `data/processed/dielectric_observations_v11plus.csv`（921,601 B）——观测级温度表，存在。

---

## 0. 目标错配声明（先读，后文所有"可用性"都按这条判）

本综述服务的**目标**是：给**电解质内 Li⁺ 的溶剂化结构/溶剂化能力**找定量描述符，用于电池设计。
我们冻结管线的**目标**是：用**纯溶剂**的分子描述符预测该**纯溶剂在室温窗口的静态介电常数 ε**。

两者只在"分子本征性质 → 分子本征性质"这一小块重叠。凡是需要**锂盐存在**才能定义的量（溶剂化壳层、AGG 比例、相对溶剂化能力），对本目标不是"弱相关"，而是**定义域不成立**——没有盐，它们没有数值。后文把这类一律判为"根本不可用"，理由逐条写明。

---

## 1. 综述点名的定量描述符 → 13 列逐一映射

三档口径：
- **已有** = 冻结 v03 物理块里已经有对应的列（或 ε 本身就是目标列）。
- **可额外 xTB 算** = 用现有钉死的 xTB 启动器再加计算即可得到（本杠杆已实现其中一部分）。
- **只能实验** = 现有管线（GFN2-xTB + RDKit 描述子）无论怎么扩也拿不到，必须有实验或高阶理论。

| # | 综述点名的定量描述符 | 综述分类 | 映射到我们的列 | 档 | 对我们的适用性（一句话） |
|---|---|---|---|---|---|
| 1 | 介电常数 ε | 本征性质 | `data/dielectric_v03.csv` 的目标列（**不是**特征） | 已有（作为标签） | 这就是我们的目标本身；作为特征会泄漏，永久排除 |
| 2 | 偶极矩 μ | 本征性质 | `dipole_D`、`mu_sq_over_Vm` | 已有 | 可用。μ²/V 与 Onsager/Kirkwood 型 ε 关联直接对口 |
| 3 | 极化率 α | 本征性质 | `polarizability_A3`、`alpha_over_Vm` | 已有 | 可用。α/V 是 Clausius–Mossotti 的显式变量 |
| 4 | 分子体积 / 摩尔体积 | 本征性质（综述在密度/体积语境下用） | `molecular_volume_A3` | 已有 | 可用。既进 μ²/V、α/V，也单独进模型 |
| 5 | 分子静电势 ESP / MEP（含极值、σ-profile 类量） | 本征性质 | 无原生列；本杠杆新增 `q_max_h`、`q_min_hetero`、`esp_imbalance`（Mulliken 电荷代理） | **可额外 xTB 算** | 部分可用。作为真实 ESP 的**代理**，与 ε 只有间接关联；要真 ESP 需 `--pop` 之外的网格/波函数后处理 |
| 6 | 轨道能级（LUMO / HOMO 相关） | 本征性质（"结合其它关键性质"节） | `homo_lumo_gap_ev` | 已有 | 可用但与我们目标弱相关（它冲还原稳定性，不冲 ε）；保留作对照 |
| 7 | 氢键能力（Kamlet–Taft 的**定义**侧） | 本征/相互作用边界 | `hbd`、`hba`、`tpsa_A2` | 已有（**片段计数代理**，非实验值） | 弱可用。是官能团计数，不是 β/α 实验值；只能当粗糙结构提示 |
| 8 | 温度 T | 综述通篇做 T 分辨，但未列入描述符清单 | `T_K` | 已有 | 可用，且是 v1.x 温度扩展的主轴 |
| 9 | 基态电子总能 | 综述未点名 | `total_energy_hartree` | 已有 | 可用（作为 ΔE_binding 的参考项，本杠杆即这样用） |
| 10 | 形式电荷 / 重原子数 | 综述未点名（我方自有复杂度控制列） | `formal_charge`、`heavy_atom_count` | 已有 | 可用（规模/复杂度控制，非物理机理列） |
| 11 | Gutmann 供体数 DN | 探针–溶剂相互作用 | 无 | **只能实验** | **根本不可用**（见 §2.2） |
| 12 | Kamlet–Taft 受体数 β | 探针–溶剂相互作用 | 无 | **只能实验** | **根本不可用**（见 §2.2） |
| 13 | Li⁺–溶剂结合能 E_b | 探针–溶剂相互作用 | 本杠杆新增 `li_binding_energy_ev` | **可额外 xTB 算** | 部分可用。气相单分子–单 Li⁺，缺溶剂结构与竞争 |
| 14 | Li⁺–O/N 键长（"Li bond" 的几何代理） | 探针–溶剂相互作用 | 本杠杆新增 `li_binding_distance_a` | **可额外 xTB 算** | 部分可用。几何量，受泛函/基组影响，但方向性比能量稳 |
| 15 | "Li bond" 概念本身（键级/QTAIM 类） | 探针–溶剂相互作用 | 无 | **只能实验/高阶理论** | **不可用**（现行管线做不到；需 NBO/QTAIM 且仍无实验锚点） |
| 16 | Li⁺ 溶剂化 Gibbs 自由能 ΔG_solv（绝对值） | 探针–溶剂相互作用 | 无（只有气相电子能） | **只能实验** | **根本不可用**（见 §2.2） |
| 17 | 相对溶剂化能力 γ（Amine 等） | 电解质体相 | 无 | **只能实验** | **根本不可用**（见 §2.3） |
| 18 | NMR 化学位移（⁷Li/¹⁷O/¹H/¹⁹F） | 电解质体相 | 无 | **只能实验** | **根本不可用**（见 §2.3） |
| 19 | Raman 位移 / AGG 百分比 / CIP-SSIP-AGG 分布 | 电解质体相 | 无 | **只能实验** | **根本不可用**（见 §2.3） |
| 20 | 扩散系数 D / 迁移数 | 电解质体相 | 无 | **只能实验** | **根本不可用**（见 §2.3） |
| 21 | 电化学窗口 / 电池电压 | 电解质体相（稳定性） | 无 | **只能实验** | **根本不可用**（见 §2.3） |

### 三档计数（只统计综述点名的描述符，不含我方自有列）

- **已有：6 个** —— ε（作为目标列）、偶极矩 μ、极化率 α、分子体积、HOMO/LUMO 能级、氢键能力（hbd/hba/tpsa 代理）。
- **可额外 xTB 算：3 个** —— ESP 类量（以 Mulliken 电荷代理实现）、Li⁺–溶剂结合能、Li⁺–O/N 键长。
- **只能实验：9 个** —— DN、β、Li bond（键级）、ΔG_solv 绝对值、相对溶剂化能力 γ、NMR 位移、Raman/AGG%、扩散系数/迁移数、电化学窗口。

合计 18 个综述点名描述符。映射覆盖 13 个 v03 列中的全部 13 列（第 8/9/10 行分别承接 `T_K`、`total_energy_hartree`、`formal_charge`/`heavy_atom_count` 这些综述未点名但我们在用的列）。
---

## 2. 三大家族逐类结论

综述的骨架（原文小标题）是：
- **Based on Intrinsic Properties of Solvents** —— 偶极矩与介电常数、静电势；
- **基于探针–溶剂相互作用强度** —— Donor Number、Kamlet–Taft β（受体数）、Binding Energy、Li bond；
- **Derived from Electrolyte Bulk Property** —— 相对溶剂化能力 γ、NMR 化学位移、Raman 位移等。

### 2.1 本征性质类：**这是我们唯一能整类迁移的一族**

理由：这一族的定义域就是"单个溶剂分子"，不依赖盐、不依赖探针、不依赖体相。因此它的量可以合法地当作**纯溶剂静态 ε 预测**的输入特征——事实上我们已经有了其中的 μ、α、分子体积、HOMO–LUMO 与温度。

**但注意两个限制**：
1. 综述本人在 Figure 13 里明确批评了这一族——"ε、μ、ESP 易得，但忽略分子间相互作用，对位阻与齿合（denticity）不敏感"。也就是说，这一族被综述判为**解释力不足**，而不是"完备"。我们把它当特征，是因为我们**只**预测纯溶剂 ε，恰好落在它擅长的定义域内；不是因为它对溶剂化能力强。
2. 属于此族的 ESP / MEP 我们**没有真值**，只有 Mulliken 电荷代理。这是一个需要如实标注的降级。

### 2.2 探针–溶剂相互作用类：**对本目标跨定义域，基本不可用**

| 描述符 | 为什么对我们不可用 |
|---|---|
| Gutmann DN | 定义是 SbCl₅ 与 Lewis 碱在非配位溶剂中的**反应焓**。它测的是"溶剂对 SbCl₅ 的给电子能力"，是把**探针分子的化学**投影到溶剂上。我们表里没有 SbCl₅，也没有任何办法从纯溶剂的分子结构算出对 SbCl₅ 的反应焓；xTB 算出来的是"该溶剂对 Li⁺ 的亲和"，与 DN 只是**相关**而非等同。 |
| Kamlet–Taft β（及 α） | 定义是**探针染料**（如对硝基苯酚类）光谱位移的溶剂化致平移。同样必须有探针分子在场。纯溶剂静态 ε 的模型里放一个"需要另一种分子参与"的量，是把两个体系混为一谈。 |
| Li⁺ 结合能 ΔE_bind | **这一条是我们唯一主动去"造"的**，因为它是从纯溶剂 + Li⁺ 两个实体算出来的，不需要额外分子或盐。但要如实承认：它是**气相、单分子–单 Li⁺、零竞争**的量，正是综述自己批评 binding energy 的那句话——"只算单溶剂分子与单 Li⁺ 的相互作用，忽略了溶剂结构以及与溶剂–溶剂竞争的效应"。因此本块只能作为**假设检验**（"综述指的这条轴能否迁到纯溶剂 ε 上"），不能当作溶剂化能力的替代测量。 |
| Li⁺–O/N 键长 | 同上，几何代理。 |
| Li bond（键级） | 需要 NBO/QTAIM 级分析，且综述自陈"实验测量困难"。现行管线无此能力，判为不可用。 |
| ΔG_solv 绝对值 | 定义是"溶剂化的 Li⁺ 与真空孤立 Li⁺ 的 Gibbs 自由能差"，**必须包含隐式溶剂模型 + 热化学 + 通常还含盐浓度**。冻结管线只产出气相电子能，缺少熵/溶剂化自由能修正，直接算会得到一个系统性偏移的数，比不算更危险。 |

### 2.3 电解质体相类：**对本目标连定义域都不成立，一律判死**

- **相对溶剂化能力 γ**（Amine 等）：定义是"测试溶剂与**参比溶剂**在含盐体系中的配位百分比之比"。需要锂盐 + 参比溶剂。没有盐 → 无配位壳层 → 量不存在。
- **NMR 化学位移**：测的是**电解质中** Li⁺/溶剂/阴离子的电子环境。纯溶剂没有 Li⁺ 溶剂化壳层，参考位移也就不存在。
- **Raman 位移 / AGG 百分比 / CIP-SSIP-AGG 分布**：AGG/CIP 这些词本身就以"盐"为前提（接触离子对、聚集体）。纯溶剂没有 AGG 可言。
- **扩散系数 / 迁移数**：电解质整体输运性质，取决于盐浓度、粘度、介观结构。
- **电化学窗口 / 电池电压**：器件级量，取决于电极与界面。

**结论一句话**：这一族不是"我们暂时算不出来"，而是"在我们的目标里没有对应的物理对象"。即使将来接入实验数据，也不能把它们塞进"纯溶剂静态 ε"的特征矩阵——那是把不同定义域的量当成同一坐标系。

### 2.4 对我们「纯溶剂静态 ε」这个不同目标，哪些根本不可用（汇总）

**根本不可用（定义域不成立）：** 相对溶剂化能力 γ、NMR 化学位移、Raman/AGG%、扩散系数/迁移数、电化学窗口、DN、β、ΔG_solv 绝对值 —— 共 8 个。
前 5 个必须含盐；DN 与 β 必须含探针分子；ΔG_solv 需要溶剂化自由能口径与盐环境。

**降级可用（能算但语义已变）：** ESP 类（Mulliken 代理）、Li⁺ 结合能、Li⁺–O/N 键长 —— 3 个。

**原样可用：** 偶极矩 μ、极化率 α、分子体积、HOMO/LUMO 能级、hbd/hba/tpsa 代理、温度 T、基态总能 —— 7 个。

---

## 3. 综述 Figure 13 逐条摘录 + 对我们的适用性

Figure 13 的图题原文：
> **Figure 13.** Advantages and disadvantages of the commonly used solvating power quantitative descriptors.

正文（Perspectives 首段）逐条如下，左列原文、右列我方判定：

| 原文摘录（逐条） | 对我们的适用性 |
|---|---|
| "Dielectric constant, dipole moment, and ESP are readily obtained by experimental or computational methods, yet they **neglect intermolecular interactions and are insensitive to steric hindrance or denticity effects**." | **这是对我们最有利的一条**。我们恰恰只预测纯溶剂 ε，不试图解释溶剂化结构；被批评的"忽略分子间作用"对纯溶剂 ε 而言是可接受近似（ε 本身正是分子间作用的宏观体现，被 λ 项间接吸收）。"对位阻/齿合不敏感"对我们影响有限——位阻/齿合主要影响 Li⁺ 配位，而非纯溶剂 ε。 |
| "Binding energy refers to the interaction between one solvent molecule and one Li ion, which **ignores the effect of solvent structure and competition with solvent−solvent interaction**." | **直接击中本杠杆（配位块）**。我们的 `li_binding_energy_ev` 正是"单分子–单 Li⁺、气相、无竞争"。因此本块的定位只能是**轴可迁移性的假设检验**，不能声称测得了溶剂化能力。 |
| "Donor number and β reflect the interaction between **probe molecules, such as antimony pentachloride or hydroxyl groups, and solvent molecules**. Although the measurement methods are well established, their **accuracy is limited by the similarity between the probe molecules and Li ion**." | 印证 §2.2：DN/β 是"探针化学"而非纯溶剂性质。两句批评（探针与 Li⁺ 相似度有限、测量成熟但语义偏移）都与我们"不引入探针分子"的立场一致。 |
| "The Li bond directly reflects Li⁺−component interactions, and ΔG takes into account the overall properties of the electrolyte, enabling them high accuracy on reflecting solvating power of solvents. However, **convenient measurement methods are still urgently needed**." | 承认精度高但**不可便捷测量**。对我们意味着：即便将来要做，也缺参考数据锚点，短期不可能进 v1.x。 |
| "The **relative solvating power requires the introduction of a reference solvent, inducing deviations from the actual electrolyte system**." | 印证 §2.3 判死 γ：连综述自己都指出它引入参比溶剂导致偏移。 |
| "NMR-based chemical shifts and Raman shifts are experimentally convenient, but they **suffer from unclear quantifiability and high subjectivity**." | 印证 §2.3：可测量性差 + 主观性强，不适合当回归目标或特征。 |
| "Overall, developing quantitative parameters for solvating power that **simultaneously offer high accuracy and wide applicability remains a significant challenge**." | 综述的收口判断：这一领域尚无"又准又通用"的描述符。**这正好解释了为什么本杠杆的期望值不该高**——我们在试一条被综述点为"难"的轴，失败是合理结果。 |

**给我们的一条正向可执行结论**：Figure 13 的第一条（ε/μ/ESP 易得但对结构不敏感）说明——**用本征性质预测本征性质（我们的 ε 目标）恰恰是这一族最擅长、也最不会被"忽略分子间作用"这条批评击穿**的用法。综述的批评针对的是"拿 μ/ε 去解释溶剂化结构"，不是"拿 μ/α 去预测 ε"。

---

## 4. 综述点名的结构设计策略 → 新化合物候选清单

综述第三部分系统整理了"怎么调溶剂化能力"的策略。我们把它转成**覆盖候选清单**：
`probes/artifacts/al_round4_pdf_new_compound_candidates.csv`（37 行，LF）

列为：`name, family, parent_solvent, design_strategy, named_in_doi, in_local_v03, in_local_observations, reason_it_is_a_coverage_candidate`

策略族与代表分子（**仅列本地没有的**，已在册的在 CSV 里显式标注为 `reconciliation row, NOT a new compound`，不计入新化合物）：

- **降低螯合（reduce chelation）**：DMM（缩短桥）、1,3-DMP（六元环）、DMB（七元环，综述记为**失败**案例）。
  综述给出的定量锚点：DME–Li⁺ 结合能 **−15.7 kcal/mol** vs DE **−11.6 kcal/mol**（少一个氧、螯合消失）。
- **增加位阻（increase steric hindrance）**：1,2-DMP（甲基化；综述记 CIP 27.9%→41.4%、AGG 10.2%→15.0%）、DEE（体积更大的烷基）、THF→THP（扩环）、DOL→HMD（多甲基化）。
- **氟代（fluorination）**：FDMB（有 Li–F 2.935 Å）、MDOL、TFDOL、TFDMP、FDEE、FEMC、FPy。
- **硅氧烷/硅酸酯低溶剂化溶剂**：TMOS、TFTMS、TFMDS、DMOTFS、TEOS。
- **中等 DN / 弱配位补充**：DMI、TMU、CPME、mFT（稀释剂）。

**真新候选：22 个**（DMM、1,3-DMP、DMB、1,2-DMP、DEE、THP、HMD、MDOL、TFDOL、TFDMP、FDEE、FEMC、FDMB、TMOS、TFTMS、TFMDS、DMOTFS、TEOS、FPy、DMI、TMU、CPME）。
**已在册（对账行）：15 个**（DME、DOL、DMC、EMC、DEC、EC、PC、FEC、DE、DPE、mFT、1,4-DX、TMP、TEP、furan）。

⚠️ **口径说明**：本表的 `family` 列（`glyme` / `carbonate` / `cyclic_ether` / `siloxane` / `amide` / `ether` / `phosphate` / `diluent` / `additive` / `heteroaromatic`）是**本表自有分类**，与兄弟探针 AL Round 4 的判据类别**不是同一套口径**，两者不可直接对齐比较。
另外：本表的 `in_local_observations` 只查 `data/processed/dielectric_observations_v11plus.csv`。DOL/EMC/EC/PC/FEC/mFT/TMP/TEP/DE/DPE 等落在"**在 v03 名册、不在观测表**"的状态——这与兄弟智能体 AL Round 4 的 `roster_gap` 发现一致，属于**观测覆盖缺口**（有化合物但缺温度分辨观测），而不是"我们有这个化合物的 ε(T) 数据"。

---

## 5. 一句话总纲

本综述给的是**电解质配方层面**的溶剂化能力地图；我们做的是**纯溶剂单分子 → 纯溶剂静态 ε**。可迁移的只有"本征性质"这一族，且我们**已经把这一族吃干**（μ、α、体积、轨道、温度全在块里）。探针类与体相类要么跨定义域、要么需要盐/探针分子，不能进纯溶剂特征矩阵。因此杠杆 8 选择"Li⁺ 配位块"是一次**有边界的假设检验**：如果它能提升 R²，说明"探针–溶剂相互作用轴"里确实存在可迁移成分；如果塌缩，则与综述"该轴精度受限于探针与 Li⁺ 相似度"的判断互相印证。