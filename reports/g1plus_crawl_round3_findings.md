# G1+ crawl round 3：三张开放票据的取证收口

日期：2026-09-24
范围：碳酸亚乙烯酯（VC）、氟代碳酸乙烯酯（FEC）、3-甲氧基丙腈（MOPN）
执行：三名**只读**研究者（Chandrasekhar / Boole / Dalton）+ 主线程本地复核
证据：probes/g1plus_crawl_round3_evidence.json

## 0. 一句话结论

本轮**没有新增任何可入数据集的原始测量值**，但把三张票据各推进了一步：
**FEC 的存量值 102 被证实是闪点（102 °C）而不是介电常数**；VC 的 126 在两张**互不相同**的综述级表格中都被印为整数，但两表**独立性未确立**；
MOPN 的 36 从无名转引追到了**具名 1994 年主来源候选**。数据集本身**一个字节都没动**。

## 1. FEC：102 是闪点，量纲错误（本轮最重要的发现）

存量行：dielectric=102、T_K=298.15、evidence_level=open_access_review_table、conflict_status=public_values_78.4_102_107、model_ready=false。

| 来源 | 实际读到 | 判读 |
|---|---|---|
| Luo et al. 2021, Adv. Sci. 8, 2101051（DOI 10.1002/advs.202101051，PMC8456284） | 表头依次为 Tm、Tb、粘度、Dielectric constant eps、Flash point Tf、密度；FEC 行为 20 / 210 / 3.33 / 78.4 / 102 / 1.45 | **78.4 在介电列，102 在闪点列** |
| Wang et al. 2023 AFM SI Table S3（本地缓存，已由主线程复核） | 166. Fluoroethylene carbonate (FEC) C3H3FO3 17.30 210.00/249.50 4.10 78.40 5.00 130.00 [16, 42] | ECW-308 自己给的是 78.40，并且它把 130.00 放在闪点列 |
| Deng et al. 2020, Energy Storage Mater. 32, 425（DOI 10.1016/j.ensm.2020.07.018） | 全文已读；FEC 行为 249.5 / 18-23 / 130；全文没有出现 78.4 | [42] 这条转引**不能**支撑 78.4 |
| Ue et al. 2014 专著章节 Table 2.3（DOI 10.1007/978-1-4939-0302-3_2） | 4-Fluoro-1,3-dioxolan-2-one (FEC) 106 1.50 **107** 4.1 -13.30 1.45 | 支撑 107 分支，但本身是汇编 |
| Hagiyama et al. 2008, Chem. Lett. 37, 210（DOI 10.1246/cl.2008.210） | Semantic Scholar 标 CLOSED；出版方 PDF 403；J-Stage 两个候选 404 | 107 分支的**具名主来源候选**，本轮 blocked |

**结论：**冲突单应从「78.4 / 102 / 107 三值」改述为「78.4 vs 107 双腿，且 102 属量纲错误」。
两条腿都是名义 25 °C、无频率的二次来源，**不能被解释为温度依赖或频率依赖**。

## 2. VC：126 在两张互不相同的综述表里都被印为整数，但仍无原始测量、两表独立性也未确立

| 来源 | 实际读到 | 状态 |
|---|---|---|
| Hall et al. 2018, J. Electrochem. Soc. 165, A2365（DOI 10.1149/2.1351810jes） | 表为 **Table II**（此前笔记记作 Table I，本轮更正）；VC 行 1.54 / 81 / **126** / 82 / 0.46 / 5.79 / 73；表注 Physical properties are reported at 25 °C or as noted | found_secondary |
| Väli, Jänes & Lust 2016, J. Electrochem. Soc. 163, A851（DOI 10.1149/2.0541606jes，开放） | Table I 的 VC 行 1.355 / - / 22 / 162 / 73 / **126**；表注 eps – dielectric constant at 25 °C | found_secondary（最明确的 25 °C 绑定） |
| Souid et al. 2025, ChemSusChem（DOI 10.1002/cssc.202402091，PMC11997941） | 正文写 high dielectric constant (126 at 298 K), [29]；其 [29] 就是 Väli 2016 | **转述，不是独立确认** |
| Saadi & Lee 1966, J. Chem. Soc. B, 5-6（DOI 10.1039/j29660000005） | 摘要可读：The dielectric constant and dipole moment of vinylene carbonate have been measured…；正文被 Cloudflare 拦截 | **blocked_access**（未绕付费墙） |

**结论：**126（整数，名义 25 °C）在**两张互不相同**的综述级表格中出现，但没有任何可读的原始测量，
而且**两表的独立性未确立**：两张表的 VC 行都没有逐值引注，而已知的原始测量（Saadi & Lee 1966）又不可读，所以两表**可能都在转引同一原始值**。
因此仍是 conflict_open，不升级。Knovel 的 78–127 区间本轮**未取得原表**，按 unverified_secondary 记录，不当竞争值使用。

## 3. MOPN：36 追到具名 1994 主来源候选，且存量精度被高估

主线程在本地缓存 data/external/g1plus/mopn/perricone2011.txt 中**独立复核**到以下五处：

| 位置 | 原文 |
|---|---|
| Tableau 4（印刷页 28）表头 | Solvant … eta à 25 °C (mPa.s) \| **eps_r à 25 °C** \| Moment dipolaire (D) \| DN AN |
| Tableau 4 的 MP 行 | Méthoxypropionitrile **[43]** - 57 165 66 1,1 **36** \| 14,6 \| [61] |
| Figure 10（印刷页 29） | 3-méthoxypropionitrile MP **36** 1,1 15,8 |
| Tableau 12（印刷页 65） | Methoxypropionitrile MP 165 66 1,1 **36** Xi |
| 正文（EC/MP 混合段） | du MP (**eps_r = 36**, DN = 14,6, eta = 0,89 mPa.s à 40 °C) |

**来源链延长：**Perricone 的参考文献 [43] 为 **Ue, M., K. Ida, and S. Mori, J. Electrochem. Soc. 141(11), 2989-2996 (1994)**，DOI 10.1149/1.2059270。
主线程在同一下载文本中确认正文写法为 Ue et al. [43, 51] ont mesuré les conductivités ioniques…，即 [43] 确实指向 Ue 等。
第二条独立综述级确认：Yen et al. 2022, Electrochim. Acta 411, 141105，Table 1 的 MPN 行为 -57 / 165 / 66 / 0.23 (30 °C) / 1.1 / **36**，其自身 [27] 指向 2013 年版 Encyclopedia of Electrochemical Power Sources。
Ue 1994 本体：OpenAlex 标 OA=False，仅见 CiteSeerX submittedVersion 记录（跳转目标不可达）→ **blocked_access**。

**结论：**票据从「无名转引」变成「具名主来源候选 Ue 1994」，但**未升级**为 primary。
另外：所有可读来源印的都是两位有效数字的整数 **36**，存量 **36.0 的位数没有来源支持**。

## 4. 本轮对数据集的影响：无

| 项目 | 值 |
|---|---|
| 行数 | 246 |
| 规范数据集 SHA-256 | 57387b98f899c6c0eff12716cc5b754f65d2ee0edd5523330af049ddded26fab |
| 改动的字段 | **无** |

数值、温度、位数、证据等级、model_ready 与 conflict_status 全部保持原样。FEC 的 102 是**受保护字段**，
在冻结期内不原地改写；更正需要一次新的数据集修订。**下一条修订应原样采用的两行 patch 已写入证据文件的 pending_patch_rows**：

| inchikey | field | value |
|---|---|---|
| SBLRHMKNNHXPHG-UHFFFAOYSA-N | conflict_status | stored_value_102_is_flash_point_not_permittivity |
| SBLRHMKNNHXPHG-UHFFFAOYSA-N | notes | 记录 102 = 闪点、78.4 / 107 两条介电腿、Hagiyama 2008 为候选主来源 |

为什么不当场改：data/dielectric_v03.csv 是被约 25 份报告、探针摘要与 5 个测试硬钉哈希的冻结产物；
改写它需要同步重建数据集、更新全部钉点并重跑基准。这属于一次**新的数据修订**，不适合在分析封版的同时静默进行。

## 5. 请求预算

| 项目 | 数值 |
|---|---:|
| Chandrasekhar（VC）自报外部请求 | 77 |
| Boole（FEC）自报外部请求 | 40 |
| Dalton（MOPN）自报外部请求 | 55 |
| 本轮合计 | 172 |
| 用户硬上限（次/小时） | 500 |
| 主线程外部调用 | 0 |

**两项偏差须如实记录：**

1. 两名研究者**超出了主线程设定的 40 次/人子上限**（77 与 55），累计 172 次。用户规定的 500 次/小时硬上限**未被接近**，但子上限被突破这件事不写成合规。
2. 失败请求（403/404/429/超时）一律**不计为负面证据**；本轮所有 blocked 路径都具名到具体文献与具体失败原因。

## 6. 复核边界

- 主线程**独立复核**了 MOPN 与 FEC 的关键引文（本地缓存文本）以及数据集当前行内容。
- 证据文件为**每一条**引文标注 recheck_status：coordinator（主线程从本地缓存复核）/ agent_only（仅研究者看到，主线程未复核）/ blocked（不可读）。
  本轮 17 条引文中 coordinator 6 条、agent_only 7 条、blocked 4 条；local_recheck.not_rechecked 逐条列出未被主线程复核的来源。
- Hall 2018、Luo 2021、Väli 2016、Souid 2025、Deng 2020、Ue 2014、Hagiyama 2008、Yen 2022、Ue 1994、Saadi & Lee 1966、Knovel 页面**仅由研究者本人看到**，其引文按其报告逐字记录。
- 「查无此值」与「权限阻断」在本轮严格区分：本轮没有任何一条写成「无数据」。

## 7. 仍未闭环

1. **Ue, Ida & Mori 1994（DOI 10.1149/1.2059270）**：MOPN 的具名主来源候选，需正文表格确认 36、温度、频率与方法。
2. **Saadi & Lee 1966（DOI 10.1039/j29660000005）**：VC 的原始测量，两页全文。
3. **Hagiyama et al. 2008（DOI 10.1246/cl.2008.210）**：FEC 107 分支的候选原始测量。
4. **Flamme et al. 2017（DOI 10.1039/c7gc00252a）**：FEC 78.4 分支的上游（RSC 403）。
5. **FEC 数据集修订**：把 conflict_status 与 notes 按 pending_patch_rows 落地到下一次修订。

