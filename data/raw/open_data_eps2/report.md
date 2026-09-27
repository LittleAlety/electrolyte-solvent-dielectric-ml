# 开放数据 ε 采集报告 W17-23（高 ε 锚点专攻）

- 输出目录：`data/raw/open_data_eps2/`（`observations.csv` / `reference_only.csv` / `coverage.json` / `report.md` / `raw/`）
- 采集时间（UTC）：`2026-09-27T07:33:06Z`
- 可用观测行：**96**；可用化合物（按 InChIKey 去重）：**31**
- 可用源：**22**（21 篇 CC BY 4.0 开放获取论文 + Wikidata CC0）
- reference_only 行：**10**（9 化合物）
- 25 个高 ε 锚点中：拿到**可用行**的 **15** 个，另有 1 个仅拿到 reference_only 行

## 1. 环境与可达性实测

| 入口 | 结果 |
| --- | --- |
| Europe PMC REST（`www.ebi.ac.uk`）| 可达；**本轮主力来源** |
| PubChem PUG-View / PUG-REST | 可达（`/rest/pug_view/data/compound/{cid}/JSON` 正常，`/rest/pug-view/` 确为 404）|
| Wikidata SPARQL + wbgetentities | 可达（SPARQL 偶发 429，改为按 InChIKey 批量取实体）|
| NIST WebBook | 可达，但页面**无介电常数数据字段**（水/甲酰胺/环丁砜等均无）|
| Zenodo API | `zenodo.org` **DNS 失败**；须用直连 IP `188.185.48.75` + `Host: zenodo.org`（`verify=False`）|
| figshare API | **不可达**：全部请求 HTTP 403（CDN 拦截）|
| Dryad API | 可达，但 `dielectric constant solvent` 检索 0 命中 |
| Crossref API | 可达；仅能定位条目，多为无 license 的记录 |
| hf-mirror.com | 可达；命中均为**无机材料**介电数据集（MatBench 等），非溶剂 |
| OpenAlex API | 可达（偶发 429）|

所有 HTTP 客户端统一 `trust_env=False`（不走环境代理）。

## 2. 有数据入库的来源（可用，逐源）

> 全部为期刊 CC BY 4.0 开放获取全文（Europe PMC JATS XML）；数值均来自其正文/表格，未做任何推断或插值。

| source_id | 标题（期刊）| license | 行数 |
| --- | --- | --- | --- |
| PMC10980761 | An integrated high-throughput robotic platform and active learning app | cc by | 15 |
| PMC8509758 | Dielectric Characteristics, Electrical Conductivity and Solvation of I | cc by | 9 |
| PMC13395902 | Implicit solvent effects on the binding interactions of amines with CO | cc by | 9 |
| PMC9781749 | Current-Voltage Characteristics and Solvent Dissociation of Bipolar Me | cc by | 8 |
| PMC11397147 | Influence of Solvent Relative Permittivity in Swab Spray Mass Spectrom | cc by | 7 |
| PMC6669325 | Solvents and Supporting Electrolytes in the Electrocatalytic Reduction | cc by | 7 |
| PMC8218942 | The Pretreatment of Lignocelluloses With Green Solvent as Biorefinery  | cc by | 5 |
| PMC7075290 | Tailoring the Anodic Hafnium Oxide Morphology Using Different Organic  | cc by | 4 |
| PMC10837367 | High-permittivity Solvents Increase MXene Stability and Stacking Order | cc by | 4 |
| PMC10821504 | (1<i>E</i>,3<i>E</i>)-1,4-Dinitro-1,3-butadiene-Synthesis, Spectral Ch | cc by | 4 |
| PMC13531275 | Recent Applications of Propylene Carbonate as a Solvent in Sustainable | cc by | 3 |
| PMC10926162 | Measuring the Capacitance of Carbon in Ionic Liquids: From Graphite to | cc by | 3 |
| PMC11238592 | Transcending Lifshitz Theory: Reliable Prediction of Adhesion Forces b | cc by | 3 |
| PMC9028971 | Polymer Electrolytes for Lithium-Ion Batteries Studied by NMR Techniqu | cc by | 3 |
| PMC12426283 | An optimized sliding rail-assisted micrometer system for sensing volum | cc by | 3 |
| PMC13364195 | Investigation on the Indium-Tin Oxide Nanoparticle-Based Chemoresistiv | cc by | 2 |
| PMC4200807 | Deactivation of 6-aminocoumarin intramolecular charge transfer excited | cc by | 2 |
| PMC9572648 | Understanding the Liquid States of Cyclic Hydrocarbons Containing N, O | cc by | 1 |
| PMC12131135 | Effect of polar organic solvents on the separation of rare earths and  | cc by | 1 |
| wikidata_P5675 | Wikidata relative permittivity (P5675) | CC0 1.0 | 1 |
| PMC13244376 | Advanced Microwave Processing for Next-Generation Materials. | cc by | 1 |
| PMC11769007 | L-Shaped Coplanar Strip Dipole Antenna Sensor for Adulteration Detecti | cc by | 1 |

逐源要点：
- **PMC10980761**（Nat. Commun. 2024, 10.1038/s41467-024-47070-5）：22 种有机溶剂物性表含 ε 列（PC 64、DMSO 46.68、NMP 32.3、HMPA 30.54 等）。
- **PMC8509758**（Materials 2021, 10.3390/ma14195617）：`Static dielectric constant εs ... t=25 °C` 表（NMF 181、甲酰胺 109.5、PC 64.9、DMSO 47.1 等）。
- **PMC13395902**（J. Mol. Model. 2026, 10.1007/s00894-026-06863-9）：正文逐条列出 `ε = ...`（甲酰胺 111.0、水 80.1、DMSO 46.7、DMAC 37.8、硝基甲烷 35.87 等），无温度标注。
- **PMC9781749**（Membranes 2022, 10.3390/membranes12121236）：`Physicochemical properties of the solvents` 表（NMF 182.4、甲酰胺 111.0、甘油 42.5、水 78.4 等）。
- **PMC11397147**（Molecules 2024, 10.3390/molecules29174274）：`Relative permittivity (20 °C)` 表；本轮取水 80.120、DMSO 47.242、硝基甲烷 37.272、甘油 46.532、正己烷、二氧六环、甲苯。
- **PMC6669325**（iScience 2019, 10.1016/j.isci.2019.07.014）：`T = 25 °C` 溶剂参数表（水 78.4、PC 66.1、DMSO 46.5、HMPA 29.6 等）。
- **PMC8218942**（Front. Plant Sci. 2021, 10.3389/fpls.2021.670061）：`Properties of usual polar aprotic solvents`（环丁砜 43.4、DMSO 46.7、NMP 32.2、DMF 36.7、DMAc 37.8）。
- **PMC7075290**（Nanomaterials 2020, 10.3390/nano10020382）：κ 列（NMF 182.4、甲酰胺 109.5、DMSO 46.70、乙二醇 37.70）。
- **PMC10837367**（Adv. Sci. 2023, 10.1002/advs.202305099）：`Permittivity εr (298 K)`（NMF 171、甲酰胺 109.5、水 78.4、DMF 37.2）——**少数给出温度的源之一**。
- **PMC10821504**（Molecules 2024, 10.3390/molecules29020542）：溶剂栏括注 ε（DMF 37.781、硝基甲烷 36.562、甲醇 32.613、丙酮 20.493），无温度。
- **PMC13531275**（ChemSusChem, 10.1002/cssc.71001）：PC 64、DMSO 46、环丁砜 43（无温度）。
- **PMC10926162**（ACS, 无 DOI 元数据）：`Relative Permittivity at Room Temperature`（甲酰胺 111、PC 64、DMSO 47）。
- **PMC11238592**（Langmuir 2023, 10.1021/acs.langmuir.3c03218）：ε 表（水 78.36、硝基甲烷 35.87、乙醇 24.55）。
- **PMC9028971**（Membranes 2022, 10.3390/membranes12040416）：EC 95.3 **@40 °C**、PC 65.1、GBL 39。
- **PMC12426283**（Front. Bioeng. Biotechnol. 2025, 10.3389/fbioe.2025.1575142）：**300 MHz, 20 °C** 相对介电（DMSO 47.0、水 80.2、乙醇 22.7）——**唯一给出频率的源**。
- **PMC13364195 / PMC4200807 / PMC9572648 / PMC12131135 / PMC13244376 / PMC11769007**：分别补充水/乙醇、DMSO/HMPA、环丁砜、水、甲酸（ε′≈56 @25 °C）、过氧化氢（εr=84.2）。
- **wikidata_P5675**（CC0 1.0）：P5675 relative permittivity，25 个锚点仅 **甘油** 命中（46.53 @20 °C）。

## 3. 未能进入可用表：reference_only（许可不兼容 / 无法核验）

| 来源 | 化合物 | 行数 | 原因 |
| --- | --- | --- | --- |
| PubChem PUG-View「Other Experimental Properties」| N-甲基甲酰胺(200.1@15°C,182.4@25°C)、甲酰胺(84)、肼(51.7@25°C)、甲酸(51.1)、NMP(32.3@25°C)、环丁砜(43.3)、DMSO(45) | 8 | 许可不兼容：PubChem 汇聚条目引自版权手册（Dean's Handbook 1987 / HSDB 等），不可再分发 |
| Zenodo 5816419（扫描 PDF）| 水(78.54)、硝基甲烷(36.7) | 2 | 无法核验：上传件许可为上传者声明 CC BY-4.0，原刊（J. Indian Chem. Soc. 2006）版权无法核验；扫描表列对齐不确定 |

> 注：本轮检索到的 CC BY-NC / CC BY-NC-ND 论文（如 `PMC13156642` iScience、`PMC13060596` Sci. Adv.）全文**未暴露可抽取的 ε 表**，故 reference_only 中没有 NC 类行。

## 4. 25 个高 ε 锚点逐一点数

| 锚点 | InChIKey | 可用行 | reference_only 行 |
| --- | --- | --- | --- |
| N-methylacetamide | OHLUUHNLEMFGTQ-UHFFFAOYSA-N | 0 | 0 |
| N-methylformamide | ATHHXGZTWNVVOU-UHFFFAOYSA-N | 4 | 2 |
| formamide | ZHNUHDYFZUAESO-UHFFFAOYSA-N | 6 | 1 |
| water | XLYOFNOQVPJJNP-UHFFFAOYSA-N | 10 | 1 |
| N-methylpropionamide | QJQAMHYHNCADNR-UHFFFAOYSA-N | 0 | 0 |
| N-methylbutanamide | OLLZXQIFCRIRMH-UHFFFAOYSA-N | 0 | 0 |
| hydrogen peroxide | MHAJPDPJQMAIIY-UHFFFAOYSA-N | 1 | 0 |
| ethylene carbonate | KMTRUDSVKNLOMY-UHFFFAOYSA-N | 1 | 0 |
| propylene carbonate | RUOJZAUFBMNUDX-UHFFFAOYSA-N | 6 | 0 |
| hydrazine | OAKJQQAXSVQMHS-UHFFFAOYSA-N | 0 | 1 |
| formic acid | BDAGIHXWWSANSR-UHFFFAOYSA-N | 1 | 1 |
| 1-methylpyrrolidin-2-one | SECXISVLQFMRJM-UHFFFAOYSA-N | 2 | 1 |
| pyrrolidin-2-one | HNJBEVLQSNELDL-UHFFFAOYSA-N | 0 | 0 |
| 1,3-dimethylimidazolidin-2-one | CYSGHNMQYZDMIA-UHFFFAOYSA-N | 0 | 0 |
| acetamide | DLFVBJFMPXGRIB-UHFFFAOYSA-N | 0 | 0 |
| 2-chloroethanol | SZIFAVKTNFCBPC-UHFFFAOYSA-N | 0 | 0 |
| 1,3-propanediol | YPFDHNVEDLHUCE-UHFFFAOYSA-N | 0 | 0 |
| 1,2-propanediol | DNIAPMSPPWPWGF-UHFFFAOYSA-N | 1 | 0 |
| tetramethylurea | AVQQQNCBBIEMEU-UHFFFAOYSA-N | 0 | 0 |
| hexamethylphosphoric triamide | GNOIPBMMFNIUFM-UHFFFAOYSA-N | 3 | 0 |
| N-methyl-2-pyrrolidone | SECXISVLQFMRJM-UHFFFAOYSA-N | 2 | 1 |
| nitromethane | LYGJENNIWJXYER-UHFFFAOYSA-N | 4 | 1 |
| sulfolane | HXJUTPCZVOIRIF-UHFFFAOYSA-N | 3 | 1 |
| gamma-butyrolactone | YEJRWHAVMIAJKC-UHFFFAOYSA-N | 1 | 0 |
| dimethyl sulfoxide | IAZDPXIOMUYVGZ-UHFFFAOYSA-N | 11 | 1 |

**0 行（既无可用也无 reference）的锚点**：N-methylacetamide、N-methylpropionamide、N-methylbutanamide、pyrrolidin-2-one、1,3-dimethylimidazolidin-2-one、acetamide、2-chloroethanol、1,3-propanediol、tetramethylurea

**仅 reference_only**：hydrazine

## 5. 失败 / 不可用来源与原因

| 来源 | 状态 | 说明 |
| --- | --- | --- |
| figshare | 不可达 | API 全站 HTTP 403（CDN 层拦截），本轮与上一轮一致 |
| NIST WebBook / SRD | 无数据 | 页面可达但无介电常数项；SRD 数值集无开放许可 |
| Zenodo 数据集 21192109（cc-zero）| 无 ε 行 | 「liquid permittivity/loss at MHz」原始数据是**谐振频率与 Q**，ε 需运行其处理脚本才能得到，未直接给值 |
| Zenodo 数据集 5816419（cc-by-4.0）| 转 reference_only | 见第 3 节 |
| Dryad | 0 命中 | `dielectric constant solvent` 检索无结果 |
| Crossref | 无可用 | 仅定位到无 license 的 dataset 记录（如 10.29172/9c9d58c4…），不可用 |
| hf-mirror.com | 不适用 | 命中为无机材料介电数据集，非纯溶剂 ε(T) |
| en.wikipedia | 未重试 | 上一轮已判 DNS 污染且 CC BY-SA 许可不兼容 |

## 6. 口径与约定

- `epsilon_unit = 1`：全部为相对介电常数 / 相对电容率（无量纲）。
- `frequency_mhz`：**仅当源明确给出频率时填值**（本轮仅 PMC12426283 的 300 MHz），其余留空，**不声称「静态」**（遵守静态判据从严）。
- `t_k`：仅当源明确给出温度时换算为开尔文填写（如 20 °C→293.15、25 °C→298.15、40 °C→313.15、298 K→298.0）；未标温度者留空。未做任何插值/猜测。
- `phase = liquid`；`component_count = 1`（仅纯物质；混合溶剂/混合物行一律不收）。
- `source_url` 指向可点击的文章 DOI 主页（无 DOI 者指向 PMC 页面）或 Wikidata 条目；`source_sha256` 为 `raw/` 中对应原始文件（Europe PMC JATS XML / Wikidata 实体 JSON / PubChem PUG-View JSON / Zenodo 文件）的 sha256。
- 同一化合物不同源给出不同值时**全部保留**，便于后续源间一致性分析。
- 已排除一条明显异常：PMC12030400 表中「Nitromethane 4.33 @20 °C」与公认值（≈35.9）矛盾，疑为笔误，未收录。
