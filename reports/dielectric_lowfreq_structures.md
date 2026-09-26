# 低频闸回收化合物的结构补全（R6）

- 生成：`probes/dielectric_lowfreq_structures.py`
- 产物：`data/processed/dielectric_lowfreq_structures.csv`（50 行 × 28 列，LF）、
  `probes/dielectric_lowfreq_structures_summary.json`
- 上游：`probes/dielectric_lowfreq_gate_probe.py`、`data/processed/dielectric_lowfreq_candidates.csv`
- 本轮未改动任何既有文件；`data/dielectric_v03.csv`、v11 观测表、低频候选表、`paper/*` 全部未触碰

## 0. 一句话结论

50 个被频闸回收的化合物**全部拿到结构**：`resolved` 50、`unresolved` 0、`ambiguous` 0、
`needs_manual_review` 0。三条**互相独立**的校验各 50/50 通过：

1. `RDKit(resolved_smiles)` 的分子式 == PubChem 自己报的 `MolecularFormula`；
2. 同一分子式 == ThermoML XML 里自带的 `<Formula>`（从 `components_json` 逐行取）；
3. `RDKit.MolToInchiKey(resolved_smiles)` == 当初拿去查询的那个 InChIKey（逐字符相等）。

其中 **39 个仍需跑 xTB** 才能进 grouped benchmark；另外 **11 个的 xTB 特征早已冻结在 v1.0 里**
（`data/processed/dielectric_physical_features_v03.csv` 11/11 命中）——它们卡的是"准入"，不是"结构"。

"11 个名录内、`model_ready=true`、却在 v11 表里一行都没有"这件事已查清：
**不是 v11 抽取漏掉，也不是闸门判错，而是来源不同**。它们的 roster 值来自
`10.6028/nbs.circ.514`（NBS Circular 514 手工录入），而这份证据根本不在 v11 的输入域里。
详见 §3。

## 1. 输入口径（全部实测）

取自 `data/processed/dielectric_lowfreq_candidates.csv`，只保留 `gate` 以 `accepted` 开头的行：

| 项 | 值 |
|---|---|
| 放行行数 | 435（`accepted_primary_lowfreq` 136 + `accepted_extended_lowfreq` 299） |
| 被排除 | `rejected_highfreq` 66 行 / 3 个化合物（未进入本轮 population，也**未消耗任何请求**） |
| 去重后化合物 | 50（名录内 11 / 名录外 39） |
| `component_count` | 435/435 行都是 1（纯组分） |
| 温度 | 218.12 – 348.20 K；44/50 个化合物有 ≥2 个温度点 |
| 温度带 | room 127 / extended 76 / 窗口外 232 |
| 频率档 | 0.01、0.05、0.1、1、2、3 MHz |
| 来源 DOI | 26 个 |

## 2. 做了什么

### 2.1 按 InChIKey 反查（不是按名字）

```
https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/inchikey/{key}/property/SMILES,ConnectivitySMILES,MolecularFormula/JSON
```

选 InChIKey 而不是名字，是因为候选表已经带了精确的 key：路径里就是 key 本身，
既没有拼写要修，也没有同分异构体要猜，更没有共享分子式能冒充命中。

- 礼貌速率：`sleep 0.30 s`（≤3.3 req/s），预算上限 120
- 实跑：**请求 50/120，HTTP 状态全 200，失败 0**，两次运行（联网一次 + `--facts-from` 重放一次）
- 每个化合物只对应 **1 个 PubChem 记录**（50 个唯一 CID，无一条 InChIKey 命中多个结构）
- 候选表 `smiles` 为空的 39 个，SMILES 全部由 PubChem 补上（`resolution_source=pubchem`）

### 2.2 候选表没有分子式列

实测 `dielectric_lowfreq_candidates.csv` 的 33 个列里**没有** `MolecularFormula`/`formula` 之类的字段，
`data/dielectric_v03.csv` 也没有。所以本轮的交叉核对参照物是 PubChem 自己报的 `MolecularFormula`，
外加 ThermoML 自带的 formula；这一事实写进了 summary 的 `population.candidate_table_has_formula_column = false`
与 `formula_checks.reference`，避免以后有人误以为候选表提供过分子式。

### 2.3 三条校验的实际结果

| 校验 | 口径 | 结果 |
|---|---|---|
| PubChem 分子式 | `RDKit(SMILES)` vs `MolecularFormula` | **50/50 match**，0 mismatch，0 not_checked |
| ThermoML 分子式 | `RDKit(SMILES)` vs `components_json[*].formula` | **50/50 match** |
| InChIKey 往返 | `MolToInchiKey(SMILES)` vs 查询用的 key | **50/50 match**，`not_confirmed` 列表为空 |
| 名录 SMILES 一致性 | 名录 SMILES 与解析 SMILES 的 RDKit 规范型 | **11/11 match**，0 mismatch |

第 3 条是最强的一条：一个 InChIKey 查询返回的结构，其重算 InChIKey 必须逐字符等于查询值——
这排除了"PubChem 返回了一个近邻结构而我们把它的 SMILES 当成目标分子"这类静默错误。

## 3. 为什么这 11 个名录内化合物在 v11 表里一行都没有

### 3.1 结论

**来源差异，不是抽取 bug，也不是闸门误判。**

1. 这 11 个的 roster 记录，`source_doi` 全部是 `10.6028/nbs.circ.514`，
   `source_scope = nbs514_manual_static_293.15_303.15K`，每行 `n_observations = 1`，`dataset_origin = v0.2`。
   也就是说：它们的静态 ε 是**人工从 NBS Circular 514 录入的**，不来自 ThermoML。
2. `data/processed/dielectric_raw.csv` 共 11,646 行 / 91 个 DOI，**全部来自 ThermoML XML**；
   其中 `doi == 10.6028/nbs.circ.514` 的行数是 **0**。
3. v11 表的唯一输入就是这个 raw（`scripts/build_dielectric_observations.py --raw data/processed/dielectric_raw.csv`），
   闸门是「纯组分 + 零频 + 液相」。既然 NBS-514 的证据不在输入域里，这 11 个自然一行都不会有。

交叉复核（排除"只有 v11 才这样"的可能）：
`data/processed/dielectric_v01_observations.csv`（706 行）与
`data/processed/dielectric_v01_ext_observations.csv`（206 行）中，这 11 个 InChIKey 的命中数**也都是 0**。
从 v0.1 起缺席就是一致的。

### 3.2 ThermoML 侧的逐条证据

扫描口径是 `components_json` 的**任意**组件槽位，而不是 `primary_inchi_key`
（后者只装组件 0，会把混合物的非首位组分整个漏掉）：

| 化合物 | ThermoML 行数 | 零频行（纯/混合） | 纯变频行频率 (MHz) | 低频闸放行行数 |
|---|---|---|---|---|
| Acetone | 23 | 0（0/0） | 0.01 | 1 |
| 2-Methyl-2-butanol | 2 | 0（0/0） | 1 | 2 |
| Aniline | 48 | 0（0/0） | 1 | 3 |
| 3-Methyl-1-butanol | 116 | 0（0/0） | 0.01, 0.1, 1 | 3 |
| **Benzene** | 56 | **45（0/45）** | 0.01 | 1 |
| n-Hexane | 201 | 0（0/0） | 1, 2 | 5 |
| 1,4-Butanediol | 89 | 0（0/0） | 0.1 | 4 |
| Acetonitrile | 121 | 0（0/0） | 0.01, 1 | 10 |
| 2-Methoxyethanol | 266 | 0（0/0） | 3 | 5 |
| Furan | 11 | 0（0/0） | 2 | 11 |
| 2-Butanone | 92 | 0（0/0） | 0.01, 0.1 | 4 |

两类缺席原因：

- **10 个**：`roster_value_source_absent_from_thermoml_raw:10.6028/nbs.circ.514|thermoml_has_no_zero_frequency_rows`
  —— ThermoML 缓存里完全没有它们的零频行。
- **1 个（Benzene）**：
  `...|thermoml_zero_frequency_rows_are_all_mixtures`
  —— 45 条零频行**全部是二元混合物**（`component_count = 2`，`is_pure = False`），
  纯组分的只有 1 条变频行。也就是说，即使把闸门放宽到"零频即可"，Benzene 依然进不来，
  因为它自己的零频值在 ThermoML 里就是不存在。

同类现象在名录外也有 2 例：`1,1,1-trifluoroethane`、`tetrachloromethane` 的零频行同样全是混合物。

### 3.3 闸门误判的检测器（0 命中）

探针专门内置了一个反常检测：如果一个化合物在 raw 里有**纯组分**的零频行、却没有进 v11 表，
那才是「闸门错杀」，会被强制标 `needs_manual_review`（原因串以
`thermoml_has_zero_frequency_pure_rows_but_none_were_admitted` 结尾）。

全 50 个化合物的实测：**这个旗标 0 例**，`needs_manual_review` 总数 0。
所以「11 个缺席」没有一个是闸门问题。
## 4. 现在有多少"结构完整"

| 项 | 数量 |
|---|---|
| population（去重化合物） | 50 |
| `resolved` | **50** |
| `unresolved` / `ambiguous` | 0 / 0 |
| 结构完整（resolved 且有 SMILES） | **50** |
| 仍需人工处理 | **0** |
| 唯一 PubChem CID | 50 |
| `needs_xtb = true` | **39** |
| `needs_xtb = false`（特征已冻结） | 11 |
| 与 v11 表有交集的化合物 | 0（这正是本轮要解决的问题） |

39 个新化合物（名录外）名单：1,1,1-trifluoroethane、1,3-butanediol、1-bromo-3-methoxybenzene、
1-butanamine、1-chloro-2-methylpropane、1-chlorobutane、1-hexanamine、2,2,4-trimethylpentane、
2,3-butanediol、2,4-dimethylhexane、2,5-dimethylfuran、2-butoxyethan-1-ol、2-chloro-2-methylpropane、
2-chlorobutane、2-ethoxyethan-1-ol、2-ethylfuran、2-ethylthiophene、2-methyl-1-butanol、2-methylfuran、
2-tetrahydrofurylmethanol、3-methyl-2-butanol、3-methylheptane、3-pentanol、5-methylfurfural、
DL-ethyl lactate、N-(2-aminoethyl)ethanolamine、N-methylformamide、acetophenone、
butyl 2-hydroxypropanoate、cyclohexylamine、dibutylamine、dipropylamine、dodecane、
exo-tetrahydrodicyclopentadiene、methyl 2-hydroxypropanoate、methyl levulinate、nitrobenzene、
pentan-2-ol、tetrachloromethane。

11 个名录内化合物（Acetone、2-Methyl-2-butanol、Aniline、3-Methyl-1-butanol、Benzene、n-Hexane、
1,4-Butanediol、Acetonitrile、2-Methoxyethanol、Furan、2-Butanone）在本轮里
`needs_xtb = false`：它们的 xTB 物理特征已经在 `data/processed/dielectric_physical_features_v03.csv` 里，
SMILES 与名录规范型一致，所以**不需要重跑 xTB**。

## 5. 距"可进 grouped benchmark"还差哪几步（准确边界）

先把话说死：**拿到 SMILES ≠ 可建模样本**。本轮交付的是"结构完整"，不是"特征完整"。
现在把这些行丢进 grouped benchmark 是跑不起来的，缺的是下面 1–5 步。

1. **xTB 构象 / 物理特征（39 个，0/39 完成）**——这是唯一的大块工作。
   现在这 39 个只有 SMILES，没有 `dielectric_physical_features_v03.csv` 同口径的特征块。
   11 个名录内的走另一条路（特征已在，见 §4）。
2. **谱系拼接**——本 CSV 已给 `inchikey` 作为 join 键，但还需要把 435 行的
   `frequency_mhz` / `gate` / `T_K` / `source_doi` 带进观测表，并明确低频行与零频行的来源标签。
3. **低频≈静态的准入口径要落成文字**——1 MHz 档的经验依据来自上游频闸探针
   （|偏差| 中位数 0.201 %、28 % 逐位复现），但**同源配对为 0**，每一对控制都掺了跨来源偏移。
   因此这是"经验界定"而不是"已认证的色散可忽略"。要不要给权重、是否只进扩展带，必须显式决定，
   不能默认当成零频。
4. **11 个名录内化合物的准入**——要么把 NBS-514 作为显式来源补进观测表，
   要么明确它们的温度序列（Furan 11 点、Acetonitrile 10 点、n-Hexane 5 点…）只从低频表取。
   否则这些化合物的温度维度永远缺一块。
5. **个别行的物性判读**——`1,1,1-trifluoroethane`（42 行、218.12–294.12 K）与
   `tetrachloromethane` 是易挥发/低沸点物种，低频行是否算"液相静态 ε"需要单独判。
6. **然后**才能跑 GroupKFold by InChIKey 的观测级 benchmark。顺序不能颠倒：
   39 个没有特征之前，多出来的那 435 行只是"能看见、不能建模"。

## 6. 产物与复现命令

新增文件（本轮全部新建，未改既有文件）：

- `probes/dielectric_lowfreq_structures.py`
- `tests/test_dielectric_lowfreq_structures.py`（59 项，全离线：注入假 HTTP + tmp_path）
- `data/processed/dielectric_lowfreq_structures.csv`（50 行 × 28 列，LF，0 个 CR）
- `probes/dielectric_lowfreq_structures_summary.json`
- `reports/dielectric_lowfreq_structures.md`（本文件）

复现（联网一次，50 请求）：

```
.\.venv\Scripts\python.exe probes\dielectric_lowfreq_structures.py
```

零请求重放（用已存档的回答重建 CSV 与 summary）：

```
.\.venv\Scripts\python.exe probes\dielectric_lowfreq_structures.py --facts-from probes\dielectric_lowfreq_structures_summary.json
```

离线只看磁盘上已有结构（39 个名录外会停在 `not_queried`）：

```
.\.venv\Scripts\python.exe probes\dielectric_lowfreq_structures.py --offline
```

## 7. 请求审计与遗留

- 实跑：`used 50 / limit 120`，`response_status_counts = {"200": 50}`，`failures = []`
- 重放：`used 0 / limit 120`，状态计数沿用存档的 `{"200": 50}`
- PubChem 侧**零限流、零重试**（`BACKOFF_SECONDS` 从未触发）
- 已知遗留（本轮未做，需主线程处理）：
  - `data/processed/dielectric_lowfreq_structures.csv` 仍被 `.gitignore` 的 `data/processed/*` 覆盖，
    需要加一条 `!data/processed/dielectric_lowfreq_structures.csv` 放行条；本任务明确禁止改 `.gitignore`，故未动。
  - 本轮不产出 `needs_xtb` 的特征，只标出"哪 39 个需要"。跑 xTB 是下一步，不是本轮的遗漏。