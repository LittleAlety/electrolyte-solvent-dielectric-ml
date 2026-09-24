# G1+ Tier-2 对抗性复核：Table S3 介电常数列

日期：2026-09-24  
复核模式：只读；未修改任何已有文件。  
原始 SI PDF SHA-256：`19F1166E2ABA6834F0CCCB1D751B618DDED5C80F97AB5B9957B2D15046BDBC76`  
PDF 提取文本 SHA-256：`D434A59FBFEC59512E0A670EB747EDE9B23CB107C47C093162CA4DB8C2A1CD4B`

## 独立结论

**Table S3 的第 5 个展示列是 “Dielectric constant at 25 °C”。** 在剔除序号/溶剂名/分子式之后，按六个性质槽读取时，第 4 个数值槽为介电常数：

1. melting point
2. boiling point
3. viscosity
4. **dielectric constant**
5. ionic conductivity
6. flash point

编号 43 和编号 51 的 MOPN 主文献值均为 **36.00（25 °C，换算 298.15 K）**。但是，编号 51 的介电单元格在 PDF 中还有下层堆叠值 **25.00**；编号 43 没有这个值。严格比较“主/上层值”时两次一致；若要求单元格内所有堆叠值完全一致，则编号 51 是一个多值单元格。

## Table S3 的确切列顺序与行号

表标题从第 5062 行开始。文本抽取将多行表头拉平，因此下表按 PDF 的视觉分组还原。

| 列 | 表头 | 文本行 |
|---:|---|---|
| 1 | Category / Solvent | 5064-5065 |
| 2 | Melting point / predicted melting point / °C | 5066-5069 |
| 3 | Boiling point / predicted boiling point / °C | 5070-5073 |
| 4 | Viscosity / cP / at 25 °C mPa s | 5074-5076 |
| 5 | **Dielectric constant / at 25 °C** | **5077-5079** |
| 6 | Ionic conductivity / at 25 °C mS cm−1 | 5080-5083 |
| 7 | Flash point / predicted flash point / °C | 5084-5087 |
| 8 | Refs. | 5088 |

为避免把 PDF 文本的 token 顺序误当表列顺序，我还在内存中渲染了 PDF 的第 67、70、71 页。视觉核验确认介电列位于 Viscosity 与 Ionic conductivity 之间。没有向磁盘写临时图片。

## 对照化合物反推

下面把每行的性质槽直接列出。所有外源值均可在公开 DOI/论文中追溯；网络在本复核中不可用，因此决定使用本地已有的可追溯观测和文献元数据。

| 化合物 | SI 名称/数据行 | 原始数据片段 | 第 4 槽候选 | 公认/独立值 | 出处 |
|---|---:|---|---:|---:|---|
| DMF | 5095 / 5096 | `C3H7NO -61.00 153.00 0.80 37.00 22.80 58.00 [2]` | **37.00** | 36.55 @ 303.15 K，u=0.22 | Fluid Phase Equilibria 266 (2008) 54-58，DOI 10.1016/j.fluid.2008.01.024 |
| DMA | 5097 / 5098 | `C4H9NO -20.00 166.00 0.90 38.00 15.70 61.00-71.00 [2]` | **38.00** | 38.0367 @ 303.2 K | Chodera 2015 dielectric compilation，arXiv:1506.00262 |
| ACN | 5296 / 5297 | `C2H3N -48.00 81.00 0.30 37.00 / 2.00 [34]` | **37.00** | 37.5 @ 293.15 K | NBS Circular 514, p.15，DOI 10.6028/nbs.circ.514 |

三个不同的化合物、三个不同的外部来源都证明“第 4 个性质槽”才与公认介电常数同一量级和最接近；因此列序不是猜测。

补充压力测试（不参与主判定）是 Propanenitrile：第 5299-5302 行的 `27.00` 位于介电列上值，而 `0.39` 位于粘度列。该行同时说明 PDF 中“上下堆叠值”会被提取文本拉平成相邻 token，不能按 token 位置猜列。

## MOPN 每一行的原文片段

### 编号 43 Methoxypropionitrile

> 5309: `43. Methoxypropionitrile -51.86  1.10 36.00 / 66.00 [36]`

> 5313: `S70`

> 5314: `C4H7NO 142.47`

还原：

- melting point = `-51.86 °C`
- measured boiling point = 空
- predicted boiling point = `142.47 °C`（跨页续行）
- viscosity = `1.10 cP`
- **dielectric constant = `36.00`**
- ionic conductivity = `/`
- flash point = `66.00 °C`

### 编号 51 3-Methoxypropionitrile

> 5344: `51. 3-Methoxypropionitrile`

> 5345: `C4H7NO -63.00 164.00 2.50 36.00`

> 5346: `25.00 / 66.00 [36]`

还原：

- melting point = `-63.00 °C`
- boiling point = `164.00 °C`
- viscosity = `2.50 cP`
- **dielectric constant = 上值 `36.00`；同一介电单元格下层还有 `25.00`**
- ionic conductivity = `/`
- flash point = `66.00 °C`

PDF 坐标核验显示 `36.00` 和 `25.00` 的 x 范围相同，均在 Dielectric constant 单元格；`/` 单独位于 Ionic conductivity 单元格。因此 `25.00` 不是“向右错一格”的电导率值，而是同一格的下层附加/未单独标注值。行末 `[36]` 对应该行的来源引用；编号 43 的独立重复行没有出现 `25.00`，故本复核采用主值 `36.00`。

MOPN 在 SI 其他表中还出现在第 684-685、778-779、4253-4254、4269-4270 行；那些不是 Table S3 的介电常数行。

## 反事实错位检验

### 对照物

| 化合物 | 实际介电槽 | 向左一格 | 向右一格 | 排除理由 |
|---|---:|---:|---:|---|
| DMF | 37.00 | 0.80 | 22.80 | 0.80 是粘度；22.80 是电导率列，且不等于公认介电值 36.55 |
| DMA | 38.00 | 0.90 | 15.70 | 0.90 是粘度；15.70 是电导率列，且显著偏离 38.04 |
| ACN | 37.00 | 0.30 | `/` | 0.30 是粘度；右格没有数值 |

### MOPN

| 行 | 左二格 | 左一格 | 采用的介电格 | 右一格 | 右二格 |
|---|---:|---:|---:|---:|---:|
| 43 | boiling=空；pred. bp=142.47 | 1.10 | **36.00** | `/` | 66.00 |
| 51 | 164.00 | 2.50 | **36.00**（下层25.00） | `/` | 66.00 |

`1.10` 和 `2.50` 位于 Viscosity 列，量级也符合粘度而不是高极性腈的介电常数；向右一格是缺失符号 `/`；`142.47`/ `164.00` 是沸点量级和沸点列；`66.00` 是闪点列且带 °C。唯一需要单独说明的替代值是 `25.00`：它位于介电列的同一单元格下层，并非相邻列，且编号 43 的主值与其不一致、编号 51 的行引文仍指向主值 `36.00`。因此 `36.00` 是本复核的主值结论；`25.00` 应作为数据治理时的多值告警保留。

## Tetraglyme 检索

在全 SI 文本中进行了大小写不敏感检索，覆盖：

- `tetraglyme`
- `tetraethylene glycol dimethyl ether`
- `TEGDME`
- `2,5,8,11,14-pentaoxapentadecane`
- `C10H22O5` 与去空格的分子式形式

结果：**0 个命中**。SI 中仅找到相邻的 Diglyme（第 5548-5549 行，ε=7.40）和 Triglyme（第 5568-5569 行，ε=7.53），随后第 5580 行进入其他化合物。没有 tetraglyme 条目。

## 许可状态

已有证据：

- SI PDF 的 XMP/元数据没有 CC-BY、copyright 或 license 字段；metadata 中 `XMP_HAS_CCBY=false`。
- Crossref 只给出 `http://onlinelibrary.wiley.com/termsAndConditions#vor`，这是 Wiley 的 VOR 条款，不是 Creative Commons。
- OpenAlex：`is_oa=false`、`oa_status=closed`、`oa_url=null`。

### (a) 数值本身作为事实能否用于数据集

**原则上可以，但应只提取事实值并保留出处。** 介电常数、温度和分子身份属于可引用的事实性数据；建议记录 DOI、行号、原始片段和独立对照来源。这个结论不等于获得复制整个 SI 表格、排版或 PDF 的许可，也不排除数据库/合同条款。

### (b) SI 文件本身能否再分发

**不能假定可以再分发。** PDF 没有声明开放许可，Crossref 指向 Wiley 条款，OpenAlex 标为 closed。除非取得权利人许可或有其他明确授权，否则不应把该 PDF/SI 直接再分发给第三方或标为 CC-BY。

## 与既有结论是否一致

我在形成上述独立结论后才读取：

- `reports/g1plus_tier2_findings.md`
- `probes/g1plus_tier2_evidence.json`

一致性：

- 既有报告同样采用 MOPN 主值 **36.00 @ 25 °C**。
- 既有报告同样指出编号 51 的 dielectric 单元格下有 `25.00` 堆叠值，并选择不使用它。
- 既有报告同样判定 SI 中没有 tetraglyme。
- 既有报告同样把许可状态判定为 closed/无 CC，不应标成 CC-BY。

本复核增加的内容：

- 既有报告主要记录编号 51；本复核额外找到并核验编号 43 的主值也为 `36.00`，形成重复证据。
- 既有报告没有给出 DMF/DMA/ACN 三对照物的列槽反推表和显式左右错位检验；本报告补齐。
- 既有报告没有把编号 51 的 `25.00` 描述为“同一介电单元格的下层值”；本复核用 PDF 坐标明确验证了这一点。

没有发现数值、列义或许可结论上的矛盾。

## 网络与可复现性

本复核发起的外部请求共 3 次（Sigma 溶剂性质页、LSU 物性 PDF、Wikipedia API），均因超时未使用；上限为 20。决定性证据均来自本地原始文件、PDF 内存渲染和已有的公开 DOI/元数据缓存。未写入任何临时图片或临时数据文件；仅新增本报告与配套 JSON。

