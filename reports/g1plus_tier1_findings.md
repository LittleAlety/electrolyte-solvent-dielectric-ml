# G1+ 第 1 梯队公开数据库取证

生成时间：2026-09-24T09:06:50+08:00

## 结论摘要

- 本轮实际发起 **40 次**外部请求（PubChem 30 次，NIST 10 次），请求间隔 1.2 s，低于 60 次上限。
- 10 个分子的 PubChem 精确 `Dielectric Constant` heading 全部为 404；随后拉取 `Experimental Properties`，完整响应中 **没有任何 `dielectric` 或 `permittivity` 字符串**。
- NIST Chemistry WebBook 的 10 个 CAS 页面均返回 HTTP 200，但 **没有一页包含 `dielectric` 或 `permittivity`**；FEC 页面正文明确为 `Registry Number Not Found`。
- 本地 Chodera 原始表共 246 行；目标中仅 diglyme 命中 5 个温度点。其 298.2 K 值 `7.3815` 与现有 v0.3.2 的 298.15 K 值一致，但本地 Chodera 表本身不能继续回溯到原始测量文献。
- 因而本轮 **没有新增 primary 值，也没有新增可引用的 PubChem 手册/Riddick 值**。MOPN 仍无可用 dielectric 值，VC/FEC 冲突没有被本批结果解决。

## 逐分子结果

| 标签 | CAS | PubChem | NIST WebBook | 本地 Chodera | 第 1 梯队新值 | 现有 v0.3.2 语境 |
|---|---|---|---|---|---|---|
| MOPN | 110-67-8 | CID 61032；heading 404；Experimental Properties 无词 | 页面正常，无 dielectric 词 | 无 | 未找到 | v0.3.2 无 dielectric 行；本地 Chodera 表也无记录。 |
| VC | 872-36-6 | CID 13385；heading 404；Experimental Properties 无词 | 页面正常，无 dielectric 词 | 无 | 未找到 | v0.3.2: ε=126 @ 298.0 K，conflict_open；原记录为 ChemSusChem 2025 开放论文正文。 |
| FEC | 114435-02-8 | CID 2769656；heading 404；Experimental Properties 无词 | Registry Number Not Found | 无 | 未找到 | v0.3.2: ε=102 @ 298.15 K，public_values_78.4_102_107；原记录为 iScience 2026 review table。 |
| triglyme | 112-49-2 | CID 8189；heading 404；Experimental Properties 无词 | 页面正常，无 dielectric 词 | 无 | 未找到 | v0.3.2: ε=7.604 @ 298.15 K；ThermoML DOI 10.1016/j.jct.2008.02.015 与 10.1016/j.jct.2010.09.008。 |
| tetraglyme | 143-24-8 | CID 8925；heading 404；Experimental Properties 无词 | 页面正常，无 dielectric 词 | 无 | 未找到 | v0.3.2: ε=7.798 @ 298.15 K；ThermoML DOI 10.1016/j.jct.2010.09.008 与 10.1016/j.tca.2012.10.024。 |
| diglyme | 111-96-6 | CID 8150；heading 404；Experimental Properties 无词 | 页面正常，无 dielectric 词 | 命中 5 行（298.2 K: 7.3815） | 7.3815 @ 298.2 K (extracted_dataset) | v0.3.2: ε=7.3815 @ 298.15 K；ThermoML DOI 10.1016/j.jct.2008.09.006 与 10.1016/j.jct.2010.09.008；另有 Chodera 历史汇合。 |
| adiponitrile | 111-69-3 | CID 8128；heading 404；Experimental Properties 无词 | 页面正常，无 dielectric 词 | 无 | 未找到 | v0.3.2: ε=32.12 @ 298.15 K；ThermoML DOI 10.1021/je300958c。 |
| glutaronitrile | 544-13-8 | CID 10994；heading 404；Experimental Properties 无词 | 页面正常，无 dielectric 词 | 无 | 未找到 | v0.3.2: ε=34.6 @ 298.15 K；ThermoML DOI 10.1021/je300958c。 |
| PC | 108-32-7 | CID 7924；heading 404；Experimental Properties 无词 | 页面正常，无 dielectric 词 | 无 | 未找到 | v0.3.2: ε=64.9 @ 298.15 K；原测量 DOI 10.1021/j100702a008。 |
| EC | 96-49-1 | CID 7303；heading 404；Experimental Properties 无词 | 页面正常，无 dielectric 词 | 无 | 未找到 | v0.3.2: ε=90.5 @ 313.15 K；原测量 DOI 10.1021/je050341y。 |

## 重点冲突

### MOPN（最高优先级）

- CAS 查询得到 PubChem CID `61032`。
- `heading=Dielectric+Constant`：HTTP 404，`PUGVIEW.NotFound / No data found`。
- `heading=Experimental+Properties`：HTTP 200；仅见 Kovats Retention Index 等条目，完整响应无 dielectric/permittivity。
- NIST 页面标题为 `Propanenitrile, 3-methoxy-`，但页面无 dielectric/permittivity。
- Chodera 本地表无匹配行。
- 结论：**MOPN 仍缺少本梯队可引用的 relative permittivity 值**。

### VC

- PubChem CID `13385`；精确 heading 404；Experimental Properties 无 dielectric/permittivity。
- NIST 页面标题为 `1,3-Dioxol-2-one`，无 dielectric/permittivity。
- Chodera 本地表无匹配行。
- 现有 v0.3.2 值仍为 `126 @ 298.0 K`，状态 `conflict_open`。本轮不能支持也不能否定 126。

### FEC

- PubChem CID `2769656`；精确 heading 404；Experimental Properties 无 dielectric/permittivity。
- NIST 的 CAS `114435-02-8` 查询返回 `Registry Number Not Found`。
- Chodera 本地表无匹配行。
- 现有冲突 `78.4 / 102 / 107` 仍开放；本轮没有产生可用于裁决的第三来源。

### 其余分子

- triglyme、tetraglyme、diglyme、adiponitrile、glutaronitrile：PubChem/NIST 均无 dielectric 条目；现有 v0.3.2 的 ThermoML 来源保持原状。
- PC、EC：PubChem/NIST 均无 dielectric 条目；现有 primary 测量记录保持原状，无需修改。

## Chodera 本地覆盖

文件：`data/external/chodera_2015_data_dielectric.csv`

仅 `2,5,8-trioxanonane`（diglyme，SMILES `COCCOCCOC`）命中：

| 行号 | T/K | relative permittivity at zero frequency |
|---|---:|---:|
| 949 | 288.2 | 7.669 |
| 959 | 298.2 | 7.3815 |
| 969 | 308.2 | 7.118 |
| 979 | 318.2 | 6.886 |
| 989 | 328.2 | 6.637 |

现有 `data/processed/chodera_crosscheck.csv` 也把该结构列为 P1/Chodera 的共同键，并记录 298.2 K 的最近温度配对值 `7.3815`。该行标识为 `arXiv:1506.00262`，但本地表没有原始测量文献字段，因此 **不能称为 primary**。

## 请求与原响应

- PubChem CID 解析：`data/external/g1plus/pubchem/*_cid_by_cas.json`
- PubChem dielectric heading：`data/external/g1plus/pubchem/*_pugview_dielectric.json`
- PubChem Experimental Properties：`data/external/g1plus/pubchem/*_pugview_experimental_properties.json`
- NIST WebBook：`data/external/g1plus/pubchem/nist_webbook/*_nist_webbook.html`
- 请求清单：`data/external/g1plus/pubchem/*manifest.json` 与 `nist_webbook/nist_query_manifest.json`

失败均如实保留：PubChem dielectric heading 的 404 响应体为原始 JSON；FEC 的 NIST 页面保留原始 HTML，并记录标题 `Registry Number Not Found`。

## 汇编与不可回溯条目

本轮 **没有 PubChem 返回的 dielectric 汇编条目**，因此没有新的 Riddick/Knovel 等汇编值可记录，也没有可供抄录的“PubChem <- 原始出处”链。

唯一命中的第 1 梯队值是 **diglyme 的 Chodera 本地提取表行**。它属于 `extracted_dataset`，不是本次新证据，也不能从本地文件回溯原始测量文献；应继续标作溯源未完成的汇合/提取数据集。
