# W17-E · OMat24 轨道数据可行性审计：**否决**——它是周期性无机晶体数据集，标注只有 energy / forces / stress，既无 HOMO/LUMO 也无任何分子结构标识

**一句话结论**：作者点名让试的 OMat24（`facebook/OMAT24`，CC BY 4.0）**不能**为本仓的电解液溶剂补 HOMO/LUMO。它把 1 亿余条**周期性无机晶体**（金属间化合物、氧化物、卤化物、氢化物）的**单点总能（eV）/ 受力（eV/Å）/ 应力（eV/Å³）**打包成 ASE-LMDB，托管在 HF **之外**的 `dl.fbaipublicfiles.com`（HF 仓库本体只有 5 个文件、`usedStorage` = 15,388 B）。逐条解压解析 35,579 条真实记录后，key 并集**恰好 15 个**，其中**没有任何** `homo`/`lumo`/`gap`/`eigenvalues`/`orbital` 字段；`pbc` 全 `True` 的记录 **35,579/35,579**（非周期记录 0）；全库找不到一个 InChIKey 形状的字符串（0 条）。判决 **`reject`**。**否决与许可无关**——CC BY 4.0 本来就满足本仓 `source_license` / `redistribution_status` 的要求。

- 事实件：`probes/omat24_feasibility_facts.json`（18,507 B，sha256 `766a71e9595b397893a33a7c572dd5e08b983207aa6ff374eb653cb2c1b35a18`）
- 审计脚本：`probes/omat24_feasibility_audit.py`（`--check` 重跑比对；网络不可用则打印 `NETWORK_UNAVAILABLE` 并以非零退出，绝不伪造成功）
- 测试：`tests/test_omat24_feasibility.py`
- 报告：本文件

## 1. 数据形态：真实数据不在 HF 上

表 1 · 仓库与许可（全部为实测 HTTP 200 的字段）

| 字段 | 实测值 |
| --- | --- |
| 仓库 id（请求 `facebook/OMAT24`） | `facebook/OMAT24` |
| 别名 `fairchem/OMAT24` | 解析到同一 id、同一 sha ⇒ 同一个仓库 |
| revision sha | `ca00b8aac581497cd0a13146fb3708ad8e2e2fe8` |
| gated / private | `false` / `false` |
| lastModified | `2025-12-11T19:29:18.000Z` |
| downloads / likes | 282 / 81 |
| **HF 仓库自身占用** | **15,388 B**（只有 5 个文件） |
| 许可 | `cc-by-4.0`（卡片 `cardData.license` 与 README front-matter 一致） |

表 2 · HF 仓库文件清单（逐字节，`/tree/main` + `/tree/main/references`）

| path | size (B) |
| --- | --- |
| `.gitattributes` | 2,419 |
| `README.md` | 10,424 |
| `references/README.md` | 580 |
| `references/element-references.yaml` | 4,617 |
| `references/omat-elemental-reference-compounds.json.gz` | 15,388 |

表 3 · 真实数据的托管与规模（`dl.fbaipublicfiles.com`，HEAD → 200）

| 子集 | Content-Length (B) |
| --- | --- |
| `val/rattled-1000-subsampled.tar.gz` | 79,870,946 |
| **`val/rattled-300-subsampled.tar.gz`（本次深度探测）** | **71,395,159** |
| `val/rattled-relax.tar.gz` | 122,957,680 |
| `omat24_1M_251210.tar.gz` | 2,274,568,000 |

卡片声明的结构数：train 合计 **100,824,585**；val 合计 **1,025,361**；1M 子抽样 **1,009,850**；sAlex 10,447,765 + 553,218。分布格式为 **ASE 兼容 LMDB（`.aselmdb`）装在 `.tar.gz` 里**。

表 4 · 本次逐字节探测的文件

| 项 | 值 |
| --- | --- |
| tar.gz 字节 / sha256 | 71,395,159 / `b13c8f54fdc1b3b07f00125fc85ddb012915d5613c4349bce406fe6e92fd20c3` |
| 成员 | `rattled-300-subsampled/data.aselmdb` 110,694,400 B；`rattled-300-subsampled/metadata.npz` 284,898 B；`data.aselmdb-lock` 8,192 B |
| LMDB 条目 | **35,580** = 35,579 条记录 + 1 条 `nextid` 计数器（值为 35580） |
| 值编码 | zlib 压缩的 UTF-8 JSON，一条记录一个 LMDB key |

## 2. 记录里到底有哪些 key（逐字，不是照抄卡片）

**顶层 15 个**：`calculator`、`calculator_parameters`、`cell`、`ctime`、`data`、`energy`、`forces`、`initial_magmoms`、`mtime`、`numbers`、`pbc`、`positions`、`stress`、`unique_id`、`user`

**`data` 下 13 个**：`calc_id`、`composition_reduced`、`correction_warnings`、`elements`、`energy_adjustments_mp2020`、`energy_corrected_mp2020`、`energy_correction_uncertainty_mp2020`、`parent_id`、`parent_prototype_label`、`prototype_error`、`prototype_label`、`sid`、`task_type`

**侧车 `metadata.npz` 只有 1 个数组**：`natoms`。

一条真实记录（LMDB key `1`，逐字；长数组在事实件里标注 `truncated` 并保留头部）：

```json
{
  "lmdb_key": "1",
  "numbers": [90, 90, 90, 90, 90, 90, 40, 40, 40, 40, 40, 40, 44, 44, 44, 44, 44, 44],
  "positions": {"len": 18, "head": [[8.136739179121218, 9.479193038840803, 4.576589660081089], [7.3526927122876, 2.120690432563553, 4.001271612212653]], "truncated": true},
  "unique_id": "fedbc7703b6ba049b558b28dd2de326e",
  "pbc": [true, true, true],
  "cell": {"len": 3, "head": [[8.13813971092779, 0.0, 0.0], [4.283889406321219, 8.754443562991698, 0.8513761455349222]], "truncated": true},
  "initial_magmoms": [0.0, 0.0, -0.0, -0.0, 0.0, -0.0, -0.0, 0.0, 0.0, 0.0, 0.0, -0.0, -0.0, -0.0, -0.0, 0.0, 0.0, 0.0],
  "calculator": "unknown",
  "calculator_parameters": {},
  "energy": -138.05475538,
  "forces": {"len": 18, "head": [[1.29960991, 1.36349229, -1.18587072], [-0.02752006, 1.06949269, 1.33729234]], "truncated": true},
  "stress": [0.04292414037077928, 0.03392008099760184, 0.023772964937524572, -0.01093546013750446, -0.008892291236833907, 0.005438810157926878],
  "ctime": 24.971422513214957,
  "user": "lbluque",
  "mtime": 24.971422513214957,
  "data": {
    "sid": "agm001016223_ABC_9111_spg46_1_0_rattled-300-subsampled_4upfxt",
    "calc_id": "rattled-300-subsampled",
    "task_type": "Static",
    "composition_reduced": "Th1 Zr1 Ru1",
    "prototype_label": "ABC_aP18_1_6a_6a_6a:Ru-Th-Zr",
    "prototype_error": "",
    "energy_corrected_mp2020": -138.05475538,
    "energy_correction_uncertainty_mp2020": 0.0,
    "energy_adjustments_mp2020": [],
    "correction_warnings": ["Failed to guess oxidation states for Entry None (ThZrRu). Assigning anion correction to only the most electronegative atom."],
    "elements": "ThZrRu",
    "parent_id": "agm001016223_ABC_9111_spg46",
    "parent_prototype_label": "ABC_oI36_46_bc_3b_ac:Ru-Th-Zr"
  }
}
```

## 3. 是不是分子：不是（是周期性无机晶体）

- `pbc` 全 `True` 的记录 **35,579 / 35,579**，非周期记录 **0**；每条记录都带 3×3 的 `cell`（晶格）。
- `natoms`：min **10** / mean **14.326** / max **104** —— 这是**晶胞**里的原子数，不是分子原子数。
- 元素直方图（按含该元素的记录数），共 **85 种元素**，前排几乎全是金属：
  `O` 2327、`Li` 2267、`Tl` 2237、`La` 2159、`Y` 2120、`Hg` 2113、`Mg` 2072、`Se` 2071、`Zn` 2044、`In` 2042、`Cd` 1985、`Sc` 1981 …
- 电解液相关元素也在，但全部落在**周期晶体**里：`S` 1735、`Cl` 1664、`P` 1649、`Si` 1591、`Br` 1565、`N` 1516、`H` 1292、`I` 1186、`F` 1130、`C` 1020、`B` 734、`Li` 2267。
- 只含「非金属小元素」集合 `{H,C,N,O,F,S,P,Cl,Br,I,B,Si,Li}` 的记录 **193** 条，实测配方样例：`Si1 C1`、`P1 I1 O2`、`I1 F5`、`Li1 N5`、`H2 S1 I2`、`Si1 H1 I1`、`Li1 H1 I2 N1`、`H3 O2`、`S1 Br2 Cl1`、`B1 C2` —— 是 SiC、卤化物、氢化物一类**共价固体**，不是可溶剂化的分子。
- 记录的识别索引是**材料学**的：`sid`（如 `agm001016223_ABC_9111_spg46_1_0_rattled-300-subsampled_4upfxt`）、`parent_id`、`prototype_label`（如 `ABC_aP18_1_6a_6a_6a:Ru-Th-Zr`）；`agm` 指 Alexandria/MP，`spg46` 是空间群号。

## 4. 有没有轨道量：没有

- 逐候选检索了 **20 个** key 名（`homo`、`lumo`、`homo_lumo_gap`、`gap`、`bandgap`、`band_gap`、`eigenvalues`、`orbital`、`orbitals`、`mo_energy`、`mo_occ`、`homo_energy`、`lumo_energy`、`dos`、`fermi`、`efermi`、`ip`、`ea`、`orbital_energies`、`homo_minus_lumo`）⇒ **命中 0 个**。
- 数据集卡片自己声明的标签只有三个，README 原文逐字：`The dataset contains structures labeled with total energy (eV), forces (eV/A) and stress (eV/A^3).`
- 侧车 `metadata.npz` 只有 `natoms`，没有任何能级数组。
- ⇒ **不存在** HOMO/LUMO；而且**连周期性体系常见的 band gap / Fermi level / DOS 都没有**。

## 5. 能不能对上本仓分子：不能（结构检索不可行）

- 结构标识候选 **12 个** key（`smiles`、`canonical_smiles`、`isomeric_smiles`、`inchi`、`inchikey`、`formula`、`molecular_formula`、`cid`、`pubchem_cid`、`iupac_name`、`cas`、`cas_number`）⇒ **命中 0 个**。
- 全库 35,579 条记录里，**没有任何一个字符串**匹配 InChIKey 形状正则 `^[A-Z]{14}-[A-Z]{10}-[A-Z]$`（命中 **0**）。
- 试了本仓 `data/dielectric_v04.csv` 前 5 行：用 RDKit 从 SMILES 算分子式，再与 OMat24 唯一的「式样」字段 `data.composition_reduced` 逐字比对。

| 名册行 | InChIKey | RDKit 分子式 | OMat24 精确命中 |
| --- | --- | --- | --- |
| N-methylaniline | `AFBPFSWMIHJQDM-UHFFFAOYSA-N` | C7H9N | **0** |
| triethylpentylammonium bis(trifluoromethylsulfonyl)imide | `ALYCOCULEAWWJO-UHFFFAOYSA-N` | C13H26F6N2O4S2 | **0** |
| pentan-1-ol | `AMQJEAYHLZJPGS-UHFFFAOYSA-N` | C5H12O | **0** |
| methyl propenoate | `BAPJBEWLBFYGME-UHFFFAOYSA-N` | C4H6O2 | **0** |
| heptan-1-ol | `BBMCTIGTTCKYKF-UHFFFAOYSA-N` | C7H16O | **0** |

- 结论：**结构检索不可行**。`composition_reduced` 描述的是**周期性晶胞**的约化组成（如 `Th1 Zr1 Ru1`），不是分子式；拿它反查分子溶剂在语义上就是错的。

## 6. 许可：CC BY 4.0（明确可再分发，**不是**否决理由）

- 卡片 `cardData.license` = `cc-by-4.0`；README front-matter `license: cc-by-4.0`。
- README 原文逐字：`The OMat24 dataset is licensed under a [Creative Commons Attribution 4.0 License](https://creativecommons.org/licenses/by/4.0/legalcode). If you use this work, please cite:`
- 因此本仓 `source_license` / `redistribution_status` 是**可以填**的；本轮否决**与许可无关**。

## 7. 判决

| 候选 | 轨道量 | 结构标识 | 许可 | 与本仓溶剂对齐 | 裁决 |
| --- | --- | --- | --- | --- | --- |
| **OMat24**（`facebook/OMAT24`） | **无**（15 个 key 里 0 个） | **无分子标识**（0 个 key，0 条 InChIKey 形状串） | CC BY 4.0（可再分发） | 0 / 5 | **`reject`** |
| `nimashoghi/omat24`（216 文件，parquet 转写） | 无（同一批数据） | 无 | 卡片未标 | — | 只作镜像核过，不采纳 |
| `StructureCloud/OMat24`（117 文件，`.pt` 预处理器） | 无（同一批数据） | 无 | 卡片未标 | — | 只作镜像核过，不采纳 |

**一句话理由**：OMat24 是**无机周期晶体**的 energy / forces / stress 数据集——既给不出 HOMO/LUMO，也没有能把记录接到本仓溶剂名册上的结构键。

**若要翻案**：只有当 OMat24 系发布中出现**分子子集**（带轨道能级 **且** 带 SMILES/InChIKey 之类的结构键）时才值得重开。

## 8. 未取到及原因

- **轨道特征值**：不是取不到，而是**不存在**。已在 20 个候选 key 名上逐条检索，并 dump 了一条完整记录。
- **分子结构**：不存在。35,579 条记录全部为周期晶胞，0 条 `pbc` 非全 True。
- **训练集（1 亿余条）**：未逐字节读。理由有二：① 卡片把标签集合定义为**全数据集**级别（`The dataset contains structures labeled with total energy (eV), forces (eV/A) and stress (eV/A^3).`）；② 所有子集由同一个 writer 写成同一种 ASE-LMDB schema。本轮逐字节核了 **1 个验证子集（35,579 条）** 作为实证锚点，并核了全部 4 个官方包的 HTTP 体积。

## 9. 复现

```powershell
.\\.venv\\Scripts\\python.exe probes/omat24_feasibility_audit.py          # 重新生成事实件
.\\.venv\\Scripts\\python.exe probes/omat24_feasibility_audit.py --check  # 重跑并比对（PASS）
.\\.venv\\Scripts\\python.exe -m pytest tests/test_omat24_feasibility.py -q
```

- 网络：`hf-mirror.com`（HF 镜像）与 `dl.fbaipublicfiles.com`（Meta 官方下载站），均以 `ProxyHandler({})` 直连；每个 URL 与 HTTP 状态码逐条记在事实件 `evidence_urls`（共 12 条，全部 200）。
- 原始字节只落在系统临时目录 `%TEMP%\\omat24_audit\\`（**不进仓库**，不污染 `data/`）。
