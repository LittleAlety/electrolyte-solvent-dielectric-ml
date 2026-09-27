# W17 室温介电常数 ε 开放许可源二次普查 v2（换角度复核，收口版）

- 生成时间（UTC）：2026-09-27T11:20:00Z
- 口径：室温（283.15–303.15 K）纯组分液体、近静态 ε；冻结池 = 2029 基表训练行 / 457 计分行 / 148 化合物（计分化合物 97）。
- **本轮性质（必须明说）**：这是**收口复核**，不是在跑新检索。本轮只做了两件事：
  1. 把此前各轮已经抓回本地、**开放许可**的 ε 文件（`pubchem_eps/`、`open_data_eps/`、`open_data_eps2/`、`dielectric_frontier_w17h/`）做了一次**本地键集核算**（不联网）；
  2. 把各轮**已实测的源可达性结论**汇总成一张逐源表。
- 因此本轮的「新源」结论是**复核性**的，不是新一轮网络普查的结果。

## 1. 结论摘要（直接回答）

| 问题 | 回答 |
| --- | --- |
| 找到几个**新**源 | **0 个** |
| 净新增**可入库**化合物数 | **0** |
| 净新增行数 | **0** |
| 上限估计 | **+4**（153 → **157**）；最宽口径 **161** |
| 是否与「开放许可化合物 153 ≈ 上限 157–161」一致 | **一致**，但必须加上限定语「在已完成入库判定的口径下」——见第 3 节 |
| 千位级是否可达 | **不可达** |

一句话结论：**ε 开放许可源见底**这一结论本轮**没有被推翻**——新源数为 0，可入库净新增为 0，上界仍是 153 + 4 = 157（最宽 161）；但本轮本地核算发现「153 / 157–161」这个上界**只在通过入库判定之后才成立**，raw（未判定）已抓取键集另有 **58 个键**落在 153 名单之外，这一口径缺口需要显式登记（第 3 节）。

## 2. 逐源复核表

| 源 | 新化合物数（净） | 新行数（净） | 可入库? | 阻断原因 |
| --- | ---: | ---: | --- | --- |
| NIST ThermoML / NIST Data Archive（**已用源**） | 8 键（真正可入溶剂池 ≈ 2） | 0 | 部分，且非新源 | 8 键中 4 个是分子液体，其中 2 个（HFO-1234ze / HFO-1234yf）需加压才液化、超出常压溶剂口径；另 2 个是固体陶瓷 CaTiO3/BaTiO3，2 个是气体 CO2/Ar；且全部来自**已经用过的源** |
| PubChem PUG-View 实验介电常数段 | 26 键（**本轮未重判**） | 0 | 未判定 | 613 个 CID 已抓，478 个含 ε 关键词，其中 **472 个只是 SpringerMaterials 属性链接、无数值**；真正可解析数值仅 40 个；入库判定由 W17 前几轮完成，本轮未复核 |
| Europe PMC CC BY 开放获取全文（`open_data_eps`） | 34 键（**本轮未重判**） | 0 | 未判定 | 135 行 / 58 化合物 / 28 个源条目（14 个有数据、6 个 license 允许但无数值表、4 个 license 被拒）；判定未在本轮重跑 |
| Europe PMC CC BY + Wikidata CC0（`open_data_eps2`） | 7 键（**本轮未重判**） | 0 | 未判定 | 96 行 / 31 化合物 / 22 个源；另有 10 行 reference_only（9 化合物）；Nitromethane 4.33 的明显笔误已剔除 |
| NIST Chemistry WebBook | 0 | 0 | 否 | W17-23 实测：页面**不含介电常数字段**（水、甲酰胺、环丁砜等均无） |
| Zenodo 8252886（Permittivity-over-temperature diagrams Database） | 0 | 0 | 否 | 只有 785 张 PNG、无数值表；论文自述数值来自 Dortmund Data Bank（专有受限）+ ThermoML ⇒ 红线 |
| HF `rasynai/thermophysical-property-corpus` | 0 | 0 | 否 | 11694 行 permittivity 的 source 全部是 `nist_thermoml_bulk`；30232 行文献 permittivity 在发布前已被整理者删除 |
| figshare API | 0 | 0 | 否 | W17-23 实测：全部请求 HTTP 403（CDN 层拦截），不可达 |
| Dryad API | 0 | 0 | 否 | W17-23 实测：`dielectric constant solvent` 命中 0 |
| HF `foundry-ml/dielectric_constant_v1-1` | 0 | 0 | 否 | 无机晶体 DFT 介电常数，非液体溶剂 |
| HF `molssiai-hub/liquid-electrolytes` | 0 | 0 | 否 | CC BY-NC-ND：禁止再分发/衍生 |
| HF `DChristensen12/na-ion-electrolyte-solvation-boxes` | 0 | 0 | 否 | MD 模拟盒，非实验 ε |
| HF `di-zhang-fdu/ORD_reaction_solvent_41K` | 0 | 0 | 否 | 未声明 license，且只是反应溶剂标签，仅可作线索 |

（逐条候选明细见 `probes/dielectric_source_sweep_v2_sources.csv`。）

## 3. 本轮唯一的新信息：raw 键集核算

做法（纯本地、不联网）：把 `pubchem_eps/pugview_eps.csv`、`open_data_eps/eps_observations.csv`、`open_data_eps2/observations.csv` 三个**已抓回**的开放许可文件按 `inchikey` 去重，与 `data/raw/dielectric_frontier_w17h/_baseline_keys.txt`（153 键的 v04 面向名单）求差。

| 源（已抓文件） | 行数 | 不同化合物 | 与 153 名单重合 | raw 净新增键 |
| --- | ---: | ---: | ---: | ---: |
| `pubchem_eps/pugview_eps.csv` | 41 | 39 | 13 | 26 |
| `open_data_eps/eps_observations.csv` | 135 | 58 | 24 | 34 |
| `open_data_eps2/observations.csv` | 96 | 31 | 24 | 7 |
| 三者并集 | — | — | — | **58** |

这 58 个键的构成：**35 个**是「单组分 + phase=liquid + 记录到 283.15–303.15 K 的 ε」，**23 个**是「单组分液体但未记录温度」，0 个是混合物或超温。

要点：

1. 这 58 个键**不是本轮新发现的化合物**，它们来自**已经抓取、且前几轮已经做过入库判定的源**（PubChem / Europe PMC CC BY）。
2. 因此 153 与 157–161 的关系应读作：**「开放许可化合物 153」= 通过入库判定后的名单**，157 = 153 + 4（ThermoML 里 4 个真液体），161 = ThermoML 归档内不同化合物总数。**raw 已抓键集本身远大于 161**，所以「153 ≈ 上限 157–161」这句话只在「已完成入库判定」的前提下成立。
3. 本轮**没有**重跑这 58 个键的入库判定（用户已要求收口、不再开新检索），所以**不能**把这 58 个键当作净新增，也**不能**断言它们全部因口径被拒。这是一个**已登记、未结案**的口径缺口。

## 4. 边界与未复核项（不许省略）

1. **本轮不含任何新的联网检索**：新源数 = 0 是复核结论，不是新一轮普查结论。若要做真正的第二遍网络普查，未穷尽的角度还剩：NIST TRC 归档的逐文件 ε 复核、figshare/OSF 的镜像入口、综述论文 SI 表格（付费墙内）、以及 CRC Handbook 的数值溯源。
2. **Reaxys 红线**：Reaxys 的数值一律不进任何池 / 特征 / 交付包，只可作「指向文献」的线索，本文件也未记录任何 Reaxys 数值。
3. **58 键口径缺口**：需要在下一轮把这三份已抓文件逐键过一遍入库判定，才能把「153 ≈ 上界 157–161」升级为已结案结论。
4. **上界仍为 +4**：在现有判定规则下，ε 开放许可源相对 153 名单的净新增上界是 **4**，与千位级（10^3）差着两个数量级 ⇒ **千位级不可达**，这条结论不因本轮复核而改变。

## 5. 交付物

- `reports/w17_dielectric_source_sweep_v2.md`（本文件）
- `probes/dielectric_source_sweep_v2_sources.csv`（13 行逐源候选表：`source_name, license, url_or_doi, n_compounds, overlap_with_v04_roster, net_new, notes`）

- 复算依据（只读、未修改）：`data/raw/pubchem_eps/`、`data/raw/open_data_eps/`、`data/raw/open_data_eps2/`、`data/raw/dielectric_frontier_w17h/`、`data/raw/thermoml_archive/`
