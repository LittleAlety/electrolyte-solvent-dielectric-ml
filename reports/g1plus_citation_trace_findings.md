# G1+ ECW-308 引文回溯：汇编值 → 期刊/原始文献

日期：2026-09-24
结构化证据：`probes/g1plus_citation_trace_evidence.json`
上游证据：`reports/g1plus_tier2_findings.md`（ECW-308 落地）、`reports/g1plus_tier3_mopn_findings.md`（MOPN）

## 目的

Tier-2 只做到"ECW-308 里写了什么值、它引了谁"。本轮回溯**它引的那些文献本身是什么**——是原始测量、期刊数据表，还是又一个汇编。这一步决定 G1+ 的目标值能否从 `secondary_compilation` 升级，也决定哪些冲突项可以写成"与另一篇期刊论文冲突"而不是"与一个汇编冲突"。

方法：取被引论文的 Crossref `reference` 数组拿到每条引文的 DOI，逐个查 OpenAlex 开放状态，再对合法可达者读原文表格。全程未使用 Sci-Hub、未绕过付费墙。

## 结论总表

| 分子 | ECW-308 值 | ECW 引文 | 回溯后的实际来源 | 证据等级变化 |
|---|---:|---|---|---|
| adiponitrile | 30.00 | Duncan 2013 | **Duncan 2013 原文 Table I = 30（整数）** | 由"汇编值"变为"期刊论文报告值" |
| glutaronitrile | 37.00 | Duncan 2013 | **Duncan 2013 原文 Table I = 37（整数）** | 同上 |
| ethylene carbonate | 89.00 | Flamme; Duncan; Perricone | Duncan 2013 Table I = 89（整数，温度未报告） | 补充期刊级佐证 |
| diglyme | 7.40 | Huang 2019 | **Huang 2019 是闭源综述**，非测量 | 明确为三手转引 |
| triglyme | 7.53 | Huang 2019 | 同上 | 同上 |
| propylene carbonate | 64.90 | Flamme; Perricone | Hall 2018 Table I = 64.9（另一篇 1972 测量） | 补充独立佐证 |
| vinylene carbonate | 126.00 | Hall 2018; Flamme 2017 | Hall 2018 Table I = 126 → **Saadi & Lee 1966 原始测量** | 首次定位到原始测量论文 |
| fluoroethylene carbonate | 78.40 | Flamme; Deng 2020 | Hall 2018 Table I = 107（引 Ue 2014 书章） | 支持冲突高端 |
| 3-methoxypropionitrile | 36.00 | Perricone 2013 | 正文仍不可达 | 无变化，维持 unverified |

## 关键发现

### 1. Duncan 2013 的原始表格已合法取得，并暴露 ECW-308 的虚假精度

Duncan, Salem & Abu-Lebdeh, *J. Electrochem. Soc.* **160**, A838 (2013)，DOI `10.1149/2.088306jes`。IOP 官方 PDF 被 Radware 拦截，但 **NRC Publications Archive 有明确标注 accepted manuscript 的合法免费副本**（记录号 `431ad01c-3fb7-4610-923b-99d08c6a4c16`），已读取 12 页。

Table I（p. A840，表头写明 `ε is dielectric constant`）：

| 化合物 | 原文 ε | 温度 | 频率 | 不确定度 |
|---|---:|---|---|---|
| Adiponitrile (ADN) | **30** | 未报告 | 未报告 | 未报告 |
| Glutaronitrile (GLN) | **37** | 未报告 | 未报告 | 未报告 |
| Ethylene carbonate (EC) | **89** | 未报告 | 未报告 | 未报告 |

- 原文是整数 `30`/`37`/`89`，ECW-308 写成 `30.00`/`37.00`/`89.00`——**两位小数是 ECW 补的，不是来源精度**。
- 实验部分写明用 Brookhaven BI-870 介电常数仪测量。
- 但 Table I 没有逐行来源，也没有温度、频率、不确定度，因此**不能**把这些行升级为"同条件原始测量"。
- 原文中**没有** VC `126.00` 或 FEC `78.40`。

### 2. Hall 2018（CC-BY）串起了大半张表，并指向 VC 的原始测量

Hall et al., *J. Electrochem. Soc.* **165**, A2365 (2018)，DOI `10.1149/2.1351810jes`。**CC BY 4.0**，正文页脚与 OpenAlex/Semantic Scholar 三处一致。IOP 站点有 Radware hCaptcha，本次经人工确认后正常访问。

Table I 相关行（原文另给每条数值的引用号）：

| 化合物 | ε | 引用号 | 该引用号对应的论文 |
|---|---:|---|---|
| Ethylene carbonate | 90.5 | 78 | `10.1021/je050341y` ← **与本库 EC 主值同一来源** |
| Propylene carbonate | 64.9 | 80 | `10.1021/j100664a019`（J. Phys. Chem. 1972） |
| Vinylene carbonate | **126** | 82 | **`10.1039/j29660000005`（J. Chem. Soc. B 1966）** |
| Fluoroethylene carbonate | 107 | 83 | `10.1007/978-1-4939-0302-3_2`（Ue 书章 2014） |
| Methyl propionate | 6.07 | 85 | `10.1016/j.molliq.2013.04.015` |

脚注 c 明确：**EC 的黏度与介电常数值是 40 °C**——这也解释了为何本库 EC 主值 `90.5` 落在 313.15 K。

### 3. VC 126 的原始测量源已找到（数值本身仍不可读）

Hall 2018 的 VC 行把 126 归于 Saadi & Lee, *J. Chem. Soc. B* **1966**, 5–6，DOI `10.1039/j29660000005`。该文摘要原文：

> "The dielectric constant and dipole moment of vinylene carbonate have been measured, and the alkaline hydrolysis of this ester in dilute aqueous ethanol has been studied. … k1 = 0·067 sec−1 at 25°."

- 这是一篇**明确的原始物理化学测量论文**，不是综述也不是汇编。
- 全文仅 2 页，RSC 页面显示为付费（购物车图标），摘要未给出数值本身，因此**未声称把 VC 升级为 primary**。
- 这条把 VC 备注里"未找到任何原始测量"的旧表述**证伪**了；已改为"原始测量源已定位、数值待取"。

### 4. 闭源与不可达清单（明确阻断，而非"查无此值"）

| 文献 | DOI | 状态 | 阻断原因 |
|---|---|---|---|
| Huang 2019 | `10.1002/adma.201808393` | Closed，PubMed 标注 Review | 综述，非测量；无任何 OA 副本 |
| Flamme 2017 | `10.1039/c7gc00252a` | Closed | RSC 403；SI 亦 404 |
| Deng 2020 | `10.1016/j.ensm.2020.07.018` | Closed | ScienceDirect 403；无仓储副本 |
| Saadi & Lee 1966 | `10.1039/j29660000005` | Closed | 摘要可读，2 页正文付费 |
| Perricone 2013 | `10.1016/j.electacta.2013.01.084` | Closed | 见 Tier-3 报告 |

## 对数据集的处置

只改溯源层，**不改任何数值、温度或 `model_ready`**：

- `adiponitrile` / `glutaronitrile`：`conflict_status` 由 `primary_vs_ecw308_compilation_differs` 改为 `primary_vs_duncan2013_reported_value_differs`；`source_dois_all` 追加 `10.1149/2.088306jes`（合法可得的 accepted manuscript）；notes 记录整数精度与 BI-870 方法。
- `diglyme` / `triglyme`：notes 记录 ECW 所引 Huang 2019 是闭源综述，属三手转引。
- `vinylene carbonate`：notes 替换"无原始测量"表述，记录 Hall 2018 → Saadi & Lee 1966 链路；`conflict_status` 维持 `conflict_open`（Knovel 78–127 区间仍冲突）。
- `ethylene carbonate` / `propylene carbonate` / `methyl propionate` / `fluoroethylene carbonate`：notes 追加独立佐证。
- 未做任何平均；未把闭源 DOI 写入 `source_dois_all`（Hall 2018 为 CC-BY，但一行只能承载一套 license 元数据，故仍只记入 notes）。

## 请求预算

| 执行方 | 请求数 | 上限 |
|---|---:|---:|
| Locke（Huang / Flamme） | 28 | 50 |
| Galileo（Duncan / Hall / Deng） | 44 | 50 |
| 主线程（Crossref / OpenAlex / S2 / IA） | 12 | — |
| Banach（Tier 3–4 可达性） | 见 `reports/g1plus_tier34_access_findings.md` | 40 |

合计远低于 500 次/小时上限。所有 agent 全程只读、未写任何文件。
