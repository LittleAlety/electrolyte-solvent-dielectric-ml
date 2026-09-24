# G1+ Tier 3：MOPN 介电常数 36.0 的原始来源判定

日期：2026-09-24  
目标：判定 3-甲氧基丙腈（MOPN，CAS 110-67-8，SMILES COCCC#N）在 25 °C 的介电常数 36.0 能否由一个原始实验来源支撑。  
证据文件：probes/g1plus_tier3_mopn_evidence.json  
请求日志：data/external/g1plus/tier3/_request_log.jsonl

## 结论

**最终标签：secondary_compilation_unverified。**

36.00 @ 25 °C 的唯一已落地数值来自 Wang et al. 2023 的补充材料 Table S3。该表将数值归于 Perricone et al. 2013，但本轮无法取得 Perricone 论文正文或表格，因此无法确认论文本身是否报告该值，也无法把该值追溯到论文所实际采用的原始测量。

Perricone 2013 的情形判定为 **(c) 无法判定**，而不是 (a) 或 (b)：

- 不是 (a)：没有合法可达的论文正文或表格证据显示 ε = 36。
- 不是已证实 (b)：没有取得正文来证明论文只是转引了另一个来源。
- 因而只能判为 (c)：公开书目和摘要可确认论文高度相关，但正文不可达，不能据此猜测 36.0 的来源性质。

## Crossref 完整书目记录

- DOI：10.1016/j.electacta.2013.01.084
- 准确标题：Investigation of methoxypropionitrile as co-solvent for ethylene carbonate based electrolyte in supercapacitors. A safe and wide temperature range electrolyte
- 作者：E. Perricone; M. Chamas; L. Cointeaux; J.-C. Leprêtre; P. Judeinstein; P. Azais; F. Béguin; F. Alloin
- 期刊：Electrochimica Acta
- 卷/页：93, 1-7
- 出版时间：2013-03
- 出版商：Elsevier BV
- 类型：journal-article
- ISSN：0013-4686
- URL：https://doi.org/10.1016/j.electacta.2013.01.084
- Crossref 摘要字段：null
- Crossref 许可证字段：Elsevier TDM 许可，不是开放内容许可
- Crossref 引用数：18；检索时被引次数：55

## Wang 2023 汇编中的证据

来源文件为 data/external/g1plus/compilations/adfm202212342-sup-0001-SuppMat.pdf，文本提取文件为同目录 adfm202212342-sup-0001-SuppMat.txt。

| 项目 | 记录 |
|---|---|
| 论文 | Wang et al., Advanced Functional Materials 2023, DOI 10.1002/adfm.202212342 |
| 表 | Table S3，页面标签 S70 |
| 行 | 51. 3-Methoxypropionitrile |
| 文本行 | 5344-5346 |
| 行文本 | C4H7NO -63.00 164.00 2.50 36.00 25.00 / 66.00 [36] |
| 数值 | 36.00 |
| 温度 | 25 °C |
| 原引文标记 | [36] |
| 原引文 | E. Perricone, M. Chamas, L. Cointeaux, J. C. Leprêtre, P. Judeinstein, P. Azais, F. Béguin, F. Alloin, Electrochim. Acta 2013, 93, 1. |

同一补充材料的另一处拼写行也出现 36.00：Methoxypropionitrile -51.86 1.10 36.00 / 66.00 [36]（文本行 5305-5309）。两处仍属于同一 Wang 2023 汇编链，不构成第二个独立来源。

## Perricone 2013 可达性逐来源判定

| 来源 | 请求号/结果 | 是否出现 36 或 ε 数值 | 判定 |
|---|---|---|---|
| Crossref DOI 记录 | 2；HTTP 200 | 否 | 只能确认书目；摘要字段为 null，无正文/表格。 |
| OpenAlex | 3-4；HTTP 200 | 否 | is_oa=false，oa_status=closed，无摘要索引，无开放位置。 |
| HAL 文章记录 | 5；HTTP 200 | 否 | 记录 hal-01884288v1 为非开放；公开摘要提到电导率和黏度，但未提介电常数，且无公开文件。 |
| OpenAIRE | 10；HTTP 200 | 否 | best access right 为 closed；只有 DOI/封闭仓储实例，没有合法全文。 |
| Unpaywall | 11 为 HTTP 422；12 为 HTTP 200 | 否 | 用仓库既有联系邮箱重试后，is_oa=false，oa_status=closed，oa_locations 为空。 |
| Semantic Scholar | 13；HTTP 200 | 否 | openAccessPdf 状态为 CLOSED；abstract 为 null。 |
| ScienceDirect 文章页 | 26；ERROR | 否 | 连接被意外关闭，未取得正文或表格。 |
| Elsevier API | 27；HTTP 429 | 否 | Too Many Requests，且无 API key/授权全文。 |
| Semantic Scholar 引用上下文 | 14 为 HTTP 429；38-39 为 HTTP 200 | 否 | 重试成功；上下文只有 MOPN 使用案例，没有介电常数数值。 |
| Crossref 18 条参考文献 | 7 为 HTTP 400；8-9 为 HTTP 200 | 否 | 未发现专门的介电性质汇编来源；但这不能替代正文，因为正文不可达。 |

结论：**没有获得 Perricone 2013 的正文或表格，也没有在可达摘要、参考文献元数据或引用上下文中观察到 36.0。公开摘要未出现该值，只能说明当前证据不足，不能据此宣称论文一定不含该值。**

## 额外独立来源搜索

| 来源/方法 | 请求号 | 结果 | 独立数值 |
|---|---|---|---|
| 本地 Landolt-Börnstein 2015 pure liquid queue | 无网络 | 217 条数据；按 MOPN、CAS、SMILES、InChIKey 等检索均 0 命中 | 无 |
| Chodera 2015 原始介电表 | 无网络 | 246 条数据；0 命中 | 无 |
| Chodera crosscheck 产物 | 无网络 | 45 个共同 InChIKey；0 命中 | 无 |
| Europe PMC 精确组合检索 | 6 | HTTP 200；宽泛返回 17 条，摘要中无 MOPN 数值 | 无 |
| Europe PMC 全文词检 | 15 | HTTP 200；FULL_TEXT 组合检索 0 命中 | 无 |
| OpenAlex 宽检索 | 17 | HTTP 200；返回候选 DOI 10.1149/1.1789372 | 候选无数值证据 |
| 2004 JES 候选论文 | 18-24 | 摘要确认 MOPN 电解液，但未给介电常数；IOP PDF 端点返回 HTML；EPFL 页超时；OpenAIRE 判定 closed/unknown | 无 |
| Crossref 其他书目检索 | 25 | HTTP 200；结果与 MOPN 介电数据无关 | 无 |
| Perricone 2011 博士论文元数据 | 28、31-33 | HAL 标记 open access，发现 NNT 2011GRENI032 和公开 PDF 标识 | 未取得可核验数值 |
| Perricone 2011 博士论文正文 | 29-30、34-35 | HAL 文档端点和直接 PDF 均被 Cloudflare 的 bot challenge 返回 HTML，未保存全文 | 无 |
| 公共网页搜索 | 36-37 | HTTP 200；没有可用的独立数值结果 | 无 |

**没有找到第二个独立、可核验的 MOPN 介电常数数值来源。** 2004 JES 论文只是最强候选，无法从其公开摘要确认 36.0，且 PDF 不可达。PubChem 与 NIST WebBook 的既有零结果不在本轮重复请求。

## 三种情形判定

| 情形 | 判定 | 依据 |
|---|---|---|
| (a) 论文正文报告 ε=36 | 未证实 | 正文、表格、补充材料均不可合法取得；没有论文级直接证据。 |
| (b) 论文只是被汇编者引用，实际值另有出处 | 未证实 | 18 条 Crossref 参考文献中没有明显的介电性质汇编来源，但这不能证明论文没有转引；缺少正文。 |
| (c) 无法判定 | **采用** | closed access、ScienceDirect 连接失败、Elsevier API 429、开放副本未索引、HAL 公开正文受 bot challenge，形成明确阻断。 |

## 最终建议

将 36.0 标记为 **secondary_compilation_unverified**，不得标为 primary。它可作为 Wang 2023 汇编中的候选值，但不能表述为“已由 Perricone 2013 原论文证实”，也不能表述为“已追溯到可靠的原始测量”。

## 约束执行情况

- 网络请求总数：39，低于 40 次上限。
- 请求间隔：日志时间戳检查显示最小间隔不低于 1.0 秒。
- 每次请求均记录到 data/external/g1plus/tier3/_request_log.jsonl，包含序号、URL、时间、HTTP 状态和用途。
- 未保存任何受限全文；公开 PDF/HTML 只在内存中尝试读取和检索，且未写入磁盘。
- 未修改任何已有文件；新增内容仅位于允许路径。
- 完成最终写入后不再发起网络请求。
