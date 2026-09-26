# W17-13 · Reaxys 薄族补货队列的**实查**（10 物质）

**一句话结论**：W17-2 只交付了队列、跑过 **0 次** 查询；本臂把队列**头部 10 个物质**在作者已登录的 Reaxys 会话上逐张物质卡走完，**21 次查询**（预算 25），得到 290 行逐条观测。结论是**分通道**的：**ε 在 6 个物质上有类目、5 个有数值**；**η 是最厚的一通道**（169 行 / 143 个点值 / 10 个物质全覆盖）；**轨道通道在 Reaxys 里根本不是 HOMO/LUMO，而是 `Ionization Potential`（18 行 / 10 个点值，4 个是区间）＋ 全为 reference-only 的 `Quantum Chemical Calculations`（6 行 / 0 数值）**；**氧化还原只有 5 个点值，且全部写在 `Comment` 列而不是数值列**（三氟乙酸 −1.2 V；戊酸 −1.35 / −1.08 / −1.40 / −1.44 V）。

- 事实表：`probes/reaxys_thin_family_query_facts.csv`（10 行 / 19 列，sha256 `f57e865fc1f63ff69c566c6335ac667fbd106a1192c7677f6b65ab61cc33f847`）
- 摘要：`probes/reaxys_thin_family_query_summary.json`（sha256 `2a8b44cf78262b8ddda49020e3f442ad1b6a676e58b4c4e07a1bc4f0e37daa40`）
- 生成器：`probes/reaxys_thin_family_query.py`（`--check` 逐字节重算）
- 原始证据：`data/raw/reaxys_w17b/`（22 件 / 1,425,151 B，被 `.gitignore` 忽略；仓库内**原样保留**）

## 1. 为什么要做这一臂

W17-2 建立了「薄家族补货队列」（`probes/reaxys_thin_family_backfill_queue.csv`，124 行候选），并**明确记录 `reaxys_queries_executed = 0`**。计划不落地就还是计划。本臂把队列头部 10 个候选真正查一遍，把「Reaxys 到底有什么」从**推测**变成**测量**。

## 2. 方法与纪律

| 项 | 取值 |
| --- | --- |
| 通道 | 作者**已登录**的 Reaxys 标签页，经 Codex 浏览器通道接管；**未**复制 profile、**未**重新登录、**未**无头爬取 |
| 查询次数 | **21 / 25**；另有 1 次点击被会话过期弹窗吞掉、未产生结果，不计入 |
| 交互方式 | 一次一张物质卡；类目表**展开到 Reaxys 自报的行数**，不盲目翻页 |
| 键来源 | 全部取自队列的 `candidate_inchikey` 列；生成器**硬断言**这一点，手抄键会让构建失败 |
| 数值落点 | 只在 `probes/`、`reports/`、`tests/`；原始页证据只在被忽略的 `data/raw/reaxys_w17b/` |

**「valued」与「point」分开计**：Reaxys 把**区间**和**点值**写进同一个 value 列（例如乙酸的 `6.17 - 6.8`、`2.46 - 2.79`）。本臂因此对每个通道同时给出三个数：`rows`（全部行）、`valued`（value 列非空，含区间）、`point`（整格能解析成单个浮点）。原始层的 `observations_summary.json` 里 `*_numeric` 的含义是 **valued**，生成器按这个口径断言，绝不把两者混为一谈。

## 3. 结果

### 3.1 逐通道

| 通道 | 定义 | rows | valued | point | reference-only | 有数值的物质数 |
| --- | --- | --- | --- | --- | --- | --- |
| ε | Dielectric Constant + Static Dielectric Constant | 78 | 66 | **59** | 12 | **5 / 10** |
| η | Dynamic Viscosity + Kinematic Viscosity | 169 | 162 | **143** | 7 | **10 / 10** |
| 轨道 | Ionization Potential + Calculated Properties（QCC） | 24 | 13 | **10** | 11 | **2 / 10** |
| 氧化还原 | Electrochemical Characteristics | 19 | 5 | **5** | 14 | **2 / 10** |

### 3.2 逐物质（点值个数）

| 物质 | InChIKey | ε | η | 轨道 | 氧化还原 |
| --- | --- | --- | --- | --- | --- |
| 三氟乙酸 | `DTQVDTLACAAQTR-UHFFFAOYSA-N` | 1 | 1 | 0 | **1**（Comment） |
| 丁酸 | `FERIUCNNQQJTOY-UHFFFAOYSA-N` | 9 | 21 | **3** | 0 |
| 异戊酸 | `GWYFCOCPABKNJV-UHFFFAOYSA-N` | 0 | 5 | 0 | 0 |
| 戊酸 | `NQPDZGIKBAWPEJ-UHFFFAOYSA-N` | 1 | 3 | 0 | **4**（Comment） |
| 乙酸 | `QTBSBXVTEAMEQO-UHFFFAOYSA-N` | 31 | 44 | **7** | 0 |
| 碳酸丙烯酯（PC） | `RUOJZAUFBMNUDX-UHFFFAOYSA-N` | 17 | 64 | 0 | 0 |
| 2-羟乙基铵乙酸盐 | `VVLAIYIMMFWRFW-UHFFFAOYSA-N` | 0 | 2 | 0 | 0 |
| 2-羟乙基铵乳酸盐 | `NEQXUPRFDXNNTA-UHFFFAOYSA-N` | 0 | 1 | 0 | 0 |
| 三乙醇胺乳酸盐 | `RJQQOKKINHMXIM-UHFFFAOYSA-N` | 0 | 1 | 0 | 0 |
| 三乙醇铵乙酸盐 | `UPCXAARSWVHVLY-UHFFFAOYSA-N` | 0 | 1 | 0 | 0 |

四个**质子型离子液体**（HEAL / HEL / TEL / TEAA）在 Reaxys 卡上**根本没有 ε 类目** —— 这是 Reaxys 的缺口，不是查询的缺口。

### 3.3 轨道通道：Reaxys 里没有 HOMO/LUMO

`Ionization Potential` 18 行 / 13 个 valued / 10 个 point：乙酸 10.32-10.38、10.35、10.6-10.7、10.66、10.7、10.72、11.15 eV；丁酸 10.17、10.24、10.22 eV；异戊酸、戊酸、三氟乙酸各 1 行（纯文献）。**电离能不是轨道能级**，两者不可互换，本臂不把任何一个 IP 写进轨道通道。`Quantum Chemical Calculations` 在本集合里出现 6 次、**0 个数值**，含 PC 的 `Electronic energy levels / Molecular orbitals / Density of states`（DFT）条目。

### 3.4 氧化还原：5 个数值，全部藏在 Comment 列

19 行 `Electrochemical Characteristics` 里只有 5 行 value 列非空，而**这 5 行的 `source_page` 都标着「value read from the Reaxys Comment column」**。也就是说：即便有数值，它们也**不在数值列里**，任何按数值列抓取的下游都会漏掉它们。这 5 个值是三氟乙酸 −1.2 V 与戊酸 −1.35 / −1.08 / −1.40 / −1.44 V。

## 4. 对 W17-RX 结论的**收窄**（不是推翻）

| | 内容 |
| --- | --- |
| 原结论 | W17-RX：HOMO/LUMO 与氧化还原电位在 Reaxys **只有文献引用、0 条数值** |
| 仍然成立 | 本集合里**没有任何 HOMO / LUMO / gap 列**；`Quantum Chemical Calculations` 全为 reference-only |
| 必须收窄 | 原结论是在**五个碳酸酯/腈类溶剂**上测的。扩到 10 个薄族物质后，它只在**轨道通道**上成立：**氧化还原通道确实有 5 个点值**（2 个羧酸），且全部写在 Comment 列 |
| 为什么不改变结论方向 | P4 的 **392** 条标签瓶颈**没有被缓解**：多了 5 个数、2 个物质，无一在数值列，且依旧没有任何数值 HOMO/LUMO |

## 5. 诚实边界（必须随数字一起引用）

- **10 个物质是 124 行队列的头部，不是队列本身。**
- PC 的 `Use` 类目在卡面**封顶在 141 行中的 107 行**，余下 34 行在该界面没有翻页控件、未从其它界面绕行。
- **Reaxys 自带的单位噪声原样保留、未修**：PC `24.997 P` / `0.253 P`、丁酸 `58 P`、乙酸 `0.0001176 P` 都像是把 cP 记进了 P 列。
- `T_K` 是 Reaxys 所显示摄氏值的**确定性换算**，区间保持区间；**未取中值、未平均、未把空温度补成 298.15 K**。
- 四个质子型离子液体里有三个（HEL / TEL / TEAA）在卡上显示 `Retrieve CAS RN`，故 `cas` 列为空 —— 是证据如此，不是漏填；HEAL 有 CAS（`54300-24-2`）。
- 氧化还原**只统计 `Electrochemical Characteristics`**；`Electrochemical Behaviour`（酸解离、极谱类）被有意排除。
- **受限条款**（裁决 B）：这些数值**不进 `data/`、不进任何池、不进任何特征表、不进交付包**。本臂 `models_fitted = 0`、不报 R²、不碰主记分牌。
