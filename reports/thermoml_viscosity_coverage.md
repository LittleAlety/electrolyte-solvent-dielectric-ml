# T1 重解析：本地 ThermoML 语料的黏度覆盖率（Week 15）

- 探针：`probes/thermoml_viscosity_coverage_probe.py`
- 机读汇总：`probes/thermoml_viscosity_coverage_summary.json`
- 观测表：`data/processed/viscosity_observations_thermoml.csv`（2,725 行 + 表头）
- 复现命令：`.\.venv\Scripts\python.exe probes\thermoml_viscosity_coverage_probe.py`
- 网络访问：无。冻结数据集写入：无。建模：无（本周只做数据工程）。

## 数据来源

| 项 | 路径 | 实测规模 |
|---|---|---|
| 本地 ThermoML XML 缓存 | `data/raw/thermoml/*.xml` | 242 个 `.xml`，合计 39,080,965 B（37.27 MB）；同目录另有 242 个 `.lock` 与 242 个 `.meta.json`，共 726 个目录项，本探针只读 `.xml` |
| 通用归一化产物 | `data/processed/thermoml_normalized.csv` | 625 行 / 34 列，只来自 4 个文件；`property_name` 仅「Relative permittivity at zero frequency」(578) 与「… at various frequencies」(47) |
| 介电专用抽取 | `data/processed/dielectric_raw.csv` | 11,646 行 / 25 列，两种属性名同理，全为介电 |
| 抓取清单 | `data/processed/thermoml_source_manifest.csv` | 205 行 / 11 列，含 `dielectric_row_count`，**无任何黏度列** |
| ε 观测表（v1.x） | `data/processed/dielectric_observations_v11plus.csv` | 153 个 InChIKey |
| 存量黏度表（Week 3） | `data/viscosity_v01.csv` | 957 个 InChIKey |

解析路径：直接复用仓内 `src/electrolyte_ml/thermoml.py` 的 `parse_thermoml_file()`，**没有另写 XML 解析器**。该解析器对每个 `PropertyValue` 都产出一行，并只在 `_is_dielectric_property()` 命中时打 `is_dielectric=true`；黏度行此前没有进入任何下游表。

身份层：ThermoML 文档自身携带 `<sStandardInChIKey>`，因此 **η 线不需要任何名称→结构解析**（与 PubChem 收割线相反）。47 个纯组分 InChIKey、2,725 行观测的 `inchikey` 列 **无一为空**。

## 方法

1. 用仓内解析器全量重解析 242 个 XML，得到 48,864 行属性观测。
2. 以 `"viscosity" in property_name.lower()` 过滤出黏度行；按 `component_count == 1` 划分纯组分 / 多组分。
3. 纯组分 InChIKey 集合分别与 ε 观测表（153 keys）和存量黏度表（957 keys）做交、差，得到重叠与净新增。
4. 每行取 XML 的 `<sDOI>` 作 `source_doi`；为空时回退到缓存文件名反解（如 `10.1016__j.jct.2014.09.015-<hash>.xml` → `10.1016/j.jct.2014.09.015`）。
5. 与开工前的侦察值逐项对账：任何不一致都会进入 `expectation_vs_remeasured`，并由 `expectation_mismatches` 暴露（本轮为空）。
6. 幂等性：`build_summary()` 只带一个 `generated_at_utc` 时间戳；去掉它后连续两次运行逐键一致，观测表逐字节一致。

## 读数

### 验收值对账（侦察预期 vs 本次实测）

| 指标 | 侦察预期 | 实测 | 判定 |
|---|---:|---:|---|
| `xml_files_scanned` | 242 | 242 | match |
| `viscosity_files` | 29 | 29 | match |
| `viscosity_rows` | 2,725 | 2,725 | match |
| ├ `Viscosity, Pa*s` | 2,549 | 2,549 | match |
| └ `Kinematic viscosity, m2/s` | 176 | 176 | match |
| `pure_rows` | 569 | 569 | match |
| `mixture_rows` | 2,156 | 2,156 | match |
| `pure_keys` | 47 | 47 | match |
| `overlap_eps_obs` | 37 | 37 | match |
| `overlap_viscosity_v01` | 28 | 28 | match |
| `new_vs_eps_and_v01` | 3 | 3 | match |

恒等式：`pure_rows + mixture_rows = 2,725 = viscosity_rows`（569 + 2,156）。

### 明细

- **提取缺口已闭环**：原始 XML 里 2,725 行黏度；而由同一语料派生的三张表里黏度行数分别是 **0 / 0 / 0**（`thermoml_normalized.csv` 625 行、`dielectric_raw.csv` 11,646 行、`thermoml_source_manifest.csv` 205 行），且清单里**连一个黏度列都没有**。所以「黏度字段从未被收割」是可机检的事实，不是推测。
- **组分分布**：`component_count` = 1 → 569 行；= 2 → 1,524 行；= 3 → 632 行。
- **温度**：2,725 行的温度单位 **全部是 K**，无缺值；95 个不同温度值；总体区间 278.15–531.1 K，纯组分区间 278.15–458.9 K。
- **相态**：2,725 行全部 `Liquid`（黏度观测天然是液相）。
- **DOI**：29 个不同 DOI，**0 行缺 DOI**，与 29 个文件一一对应。行数最多的三个文件为 `j.fluid.2019.06.022`（287）、`j.jct.2014.09.015`（245）、`je800664z`（189）。
- **纯组分集合的三种归属**：47 个 key 中，37 个已在 ε 观测表、28 个已在存量黏度表、**21 个两边都在**、只有 **3 个是净新增**：

  | InChIKey | 名称 | 纯组分行数 | T 区间 (K) |
  |---|---|---:|---|
  | `INDFXCHYORWHLQ-UHFFFAOYSA-N` | 1-butyl-3-methylimidazolium bis(trifluoromethylsulfonyl)imide | 9 | 293.15–333.15 |
  | `ZTWVDFVGJLMQNA-UHFFFAOYSA-O` | pyrrolidinium nitrate | 8 | 283.15–353.15 |
  | `SEGLCEQVOFDUPX-UHFFFAOYSA-N` | bis(2-ethylhexyl) hydrogen phosphate | 4 | 303.15–333.15 |

- **两条对下游有用的交叉事实**：
  1. **碳酸丙烯酯（PC，`RUOJZAUFBMNUDX-UHFFFAOYSA-N`）在本地有 28 行纯组分 η(T)**，尽管本仓的 `thermoml_local_coverage_audit.md` 已证实本地**没有** PC 的 ε 数据。即：PC 的 η 不需要外部源，ε 才需要。
  2. 纯组分黏度集合里已经躺着 **2 个咪唑类离子液体**（`LSBXQLQATZTAPE` = BMIM-BF4、`INDFXCHYORWHLQ` = BMIM-NTf2）。对 v0.4 是否收 IL 的决策，这是一条本地已有锚点。
- **观测表契约**：`data/processed/viscosity_observations_thermoml.csv` 19 列 × 2,725 行，按 `(thermoml_file, source_row_index)` 排序；每行都带 `T_K`、`source_doi`、`thermoml_file`、`pure_or_mixture`。`smiles_or_name` 列填的是名称——ThermoML 不带 SMILES，身份以 `inchikey` 列为准。

## 边界（不许省略）

1. **本地是子集，不是全集**。`data/raw/thermoml/` 是 NIST ThermoML 全库（11,923 条记录）的**筛选缓存**，缓存本身是为介电检索组建的。因此「29 个文件含黏度」**不是** NIST 黏度数据的总体上界；「本地没有」只等于「本地缓存没有」。要下总体结论，必须另做在线黏度切片核查（本探针不做，且不联网）。
2. **多组分 2,156 行未做溶质/溶剂角色拆分**。`inchikey` 列对多组分行**只是第一个组分**，不能代表整条观测的身份；本表的纯组分口径严格等于 `component_count == 1`。
3. **运动黏度 176 行不能当动力黏度用**。它们以 m²/s 记录，没有密度就无法换算成 Pa·s；本表原样保留在 `viscosity_kinematic_m2_s` 列，**不参与任何 ε+η 配对**，也不计入 `viscosity_cP`。
4. **`extraction_gap` 的适用范围**：它只覆盖由本地 ThermoML 语料派生的表。本仓另有含黏度列的表（`viscosity_raw.csv`、`dielectric_viscosity_intersection.csv` 等）来自 Schrödinger SI，**不是** ThermoML 产物，不能用来反驳该结论。
5. **本轮只是抽取，不是建模**。行数（2,725）不是样本量：建模口径必须按 `(化合物, T)` 与 InChIKey 分组，并在 GroupKFold 下评估；本探针不训练任何模型、不改评分池、不把任何值写进冻结数据集（`data/dielectric_v03.csv` 与 `dielectric_observations_v11plus.csv` 的 digest 在本轮之后仍与冻结值一致）。
6. **温度闸门不等于温度泛化**。观测里覆盖 278–531 K 只说明数据存在；「温度外推能力」需要单独预注册的温度留出折，不能拿本表的温度覆盖当卖点。
