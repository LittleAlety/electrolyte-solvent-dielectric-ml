# Reaxys v1.x 备货扫描（第二刀补）

**日期**：2026-09-26
**浏览器**：Edge (user-logged-in Reaxys session), manual per-record queries
**方法合规**：手动逐条查询（无批量抓取 / 无导出 / 无自动化遍历）；所有取值 `restricted_crosscheck_only`，永不进可分发数据集。**本产物确实含受限数值的机器可读镜像**（`readings[].rendered_rows` 与 `net_new_detail[].value` 是渲染表数值列的逐值转录），只存于本仓库与 week13 包内，禁止再次分发。
**产物**：`probes/reaxys_v1x_stocking_queue.csv`、`probes/reaxys_v1x_stocking_scan_summary.json`、`probes/reaxys_v1x_stocking_scan.py`、`probes/verify_reaxys_v1x_stocking_scan.py`

## 0 结论速览

| 问题 | 答案 |
| --- | --- |
| v1.x 温度线还缺多少？（**池内**口径） | 池内 236 个溶剂里，有 **167** 个在本地观测表里没有温度序列（<2 个不同温度）；池内**有**温度序列的是 69 个（167 + 69 = 236） |
| 另有一个更大的计数是什么？（**全表**口径） | 观测表**全表** 153 个物质里有温度序列的是 106 个。**这与上一行不是一个口径**（上一行只数池内成员），两者不可混用 |
| Reaxys 能补多少？ | 本轮探测 7 个物质，**净新增带温度的介电条目 4 条**（2 个物质、3 篇一手文献）：PC 2 条 @2E+06；tetraglyme 2 条 @1E+06 |
| 冠军真值有没有被旁证？ | **没有独立旁证**。PC 那两条 25 C 是「汇编转述一致」（最终都指回 Riddick 4th ed. 汇编，见第 5 节）；EC 那条 89.78 被 Reaxys 标成 25 C，而本仓库既有溯源记为 40 C = 313.15 K —— 温度栏自相矛盾 |
| 前面的外部源全证伪结论要不要改？ | **不用改**。Reaxys 的净增益与「外部免费 ε(T) 扩张收官」的四源（ThermoML 在线 / ILThermo 温度维度 / DDB 免费层 / OA 直读）同向，都是极小。该四源结论各自的证据见 `reports/thermoml_online_topup_round6.md`、`reports/ilthermo_probe.md`、`reports/ddb_free_search_probe.md`、`reports/al_round3.md` |

## 1 本轮先修正了一个自己的错

按俗名（`adiponitrile` / `diglyme` / `triglyme` / `tetraglyme`）去本地表做覆盖度匹配，会**全部误判成 0 行**：本地观测表用 IUPAC 登记名。真实情况是——

| 物质 | 本地登记名 | 观测表温度点数（自动重算） | 已登记温度点数（人工转录） | 该计数取自哪张表 | 温度范围 |
| --- | --- | ---: | ---: | --- | --- |
| tetraglyme | tetraethylene glycol dimethyl ether | 5 | 5 | `observation_table` | 288.15-308.15 K |
| triglyme | triethylene glycol dimethyl ether | 5 | 5 | `observation_table` | 288.15-328.15 K |
| adiponitrile | adiponitrile (hexanedinitrile) | 31 | 31 | `observation_table` | 278.15-353.15 K |
| diglyme | diglyme (diethylene glycol dimethyl ether) | 6 | 6 | `observation_table` | 288.15-338.15 K |

`stocking_queue` 因此改为按 **InChIKey** 重算，不再依赖名称匹配。这条与本项目「新特征先过覆盖率检查」是同一类教训的另一面：**覆盖度检查本身也要用不依赖命名的键**。

## 2 v1.x 备货队列（自动重算）

- 池：`probes/l3_stage1_pilot_pool.csv`，236 行 / 236 个 InChIKey（sha256 复核 `b838febbca4d6597...`）
- 观测表：`data/processed/dielectric_observations_v11plus.csv`，2065 行 / 153 个物质（sha256 复核 `159b928f800a5596...`）
- 队列：**167** 个池成员没有温度序列；池内**有**温度序列的 69 个（两个数相加 = 池内 236 个成员，脚本内已断言）
- 优先级口径：**P1 ≡ 池内 `is_champion=true` 的行**（本队列 2 行），不是硬编码物质名；P2 的 `model_ready` 条件在本队列上恒真（True），因此 P2 实际只由族决定
- **P2 是族级复核顺序，不是可用性判断**：族集合 {carbonate, lactone, glyme_ether, fluorinated} 里的 `fluorinated` 是子串规则，会把非电解液芳烃（1,2-difluorobenzene、1-Fluoropentane、2-Fluoro-2-methylbutane、Fluorobenzene、Trifluoroacetic acid、alpha,alpha,alpha-Trifluorotoluene 等 9 行）一并排进 P2。这些行只是**先被复核**，不代表任何电池可用性；`stocking_priority` 全文都不得读成可用性结论

优先级分布：`P1` 2、`P2` 22、`P3` 143

族分布：`alcohol_amine` 27、`carbonate` 3、`fluorinated` 9、`glyme_ether` 11、`ionic_liquid` 23、`lactone` 1、`nitrile` 9、`other` 83、`siloxane` 1

队列前 20（完整表见 CSV）：

| # | 物质 | 族 | 优先级 | 本地温度点数 |
| ---: | --- | --- | --- | ---: |
| 1 | ethylene carbonate | `carbonate` | P1 | 0 |
| 2 | propylene carbonate | `carbonate` | P1 | 0 |
| 3 | ethyl methyl carbonate | `carbonate` | P2 | 0 |
| 4 | m-Fluorotoluene | `fluorinated` | P2 | 0 |
| 5 | Trifluoroacetic acid | `fluorinated` | P2 | 0 |
| 6 | alpha,alpha,alpha-Trifluorotoluene | `fluorinated` | P2 | 0 |
| 7 | 1,2-difluorobenzene | `fluorinated` | P2 | 0 |
| 8 | 2-Fluoro-2-methylbutane | `fluorinated` | P2 | 0 |
| 9 | o-Fluorotoluene | `fluorinated` | P2 | 0 |
| 10 | 1-Fluoropentane | `fluorinated` | P2 | 0 |
| 11 | Fluorobenzene | `fluorinated` | P2 | 0 |
| 12 | p-Fluorotoluene | `fluorinated` | P2 | 0 |
| 13 | 1,1,2,2-tetrafluoroethyl 2,2,2-trifluoroethyl ether | `glyme_ether` | P2 | 0 |
| 14 | 1,1,2,2-tetrafluoroethyl 2,2,3,3-tetrafluoropropyl ether | `glyme_ether` | P2 | 0 |
| 15 | 2-methyltetrahydrofuran | `glyme_ether` | P2 | 0 |
| 16 | bis(2,2,2-trifluoroethyl) ether | `glyme_ether` | P2 | 0 |
| 17 | Propyl ether | `glyme_ether` | P2 | 0 |
| 18 | Ethyl ether | `glyme_ether` | P2 | 0 |
| 19 | 1,1-Dimethoxyethane | `glyme_ether` | P2 | 0 |
| 20 | 1,3-dioxolane | `glyme_ether` | P2 | 0 |

## 3 Reaxys 探测读数（人工转录）

| 物质 | CAS | Reaxys 声明条目 | 实际渲染行 | 温度序列？ | 观测表温度点数（自动） | 已登记温度点数（人工） | 净新增温度点 | 判决 |
| --- | --- | ---: | ---: | --- | ---: | ---: | ---: | --- |
| EC | 96-49-1 | 4 | 4 | 否 | 0 | 1（`frozen_table_v03`） | 0 | `no_temperature_series` |
| PC | 108-32-7 | 10 | 7 | 否 | 0 | 1（`frozen_table_v03`） | 2 | `cross_check_ok_plus_two_frequency_qualified_points` |
| tetraglyme | 143-24-8 | 8 | 7 | 是 | 5 | 5（`observation_table`） | 2 | `net_new_temperature_points_from_a_new_primary_source` |
| triglyme | 112-49-2 | 1 | 1 | 否 | 5 | 5（`observation_table`） | 0 | `reaxys_weaker_than_local` |
| adiponitrile | 111-69-3 | 1 | 1 | 否 | 31 | 31（`observation_table`） | 0 | `reaxys_weaker_than_local` |
| diglyme | 111-96-6 | 0 | 0 | 否 | 6 | 6（`observation_table`） | 0 | `absent_in_reaxys` |
| TTE | — | 0 | 0 | 否 | 0 | 1（`observation_table_single_point`） | 0 | `absent_in_reaxys_and_local_is_single_point` |

**两张表的「本地温度点数」不是一回事**（本报告上一版把 236 / 167 / 106 三个数写混，根因就在这里）：EC / PC 在**观测表**里是 0 行 0 个温度点，人工转录的那 1 个点取自 **v03 冻结表**的冠军行；glyme 系与己二腈取自观测表，两张表计数恰好相同。列名已按来源分开，读者不应把两列相加。
### 3.1 逐物质要点

**EC**（ethylene carbonate，CAS 96-49-1）——只有 25 C 标签。5.4 @ 25 C 这一条与同物质其余三条差一个数量级，疑为异质测量或单位混入，只作可疑条目登记、不作数值使用。89.78 这条**不能按 Reaxys 标的 25 C 读**：本仓库既有溯源（reports/jstage_corroboration.md）把同一个 89.78 记为 **40 C = 313.15 K**，正好是 EC 的冻结温度，相对偏差 0.80%；而 EC 熔点 36.4 C，25 C 本就不是液态。Reaxys 的温度标注在这里是错的，这本身就是「Reaxys 温度栏不可信」的内部证据（见第 5 节）。

**PC**（propylene carbonate，CAS 108-32-7）——Reaxys 侧有两条 25 C 条目（64.9 与 64.92）与冻结冠军真值 64.9 @ 298.15 K 相符，但**这不是独立测量旁证**：本仓库既有溯源（reports/jstage_corroboration.md）已证明 64.92 来自 Nanbu 2007 转引的 Riddick《Organic Solvents》4th ed. 汇编值，属「汇编转述一致」。详见第 5 节。另有 20 C / 35 C 两点，但都标在 2 MHz，是否可入 v1.x 观测表受频率口径约束，本产物只报线索，不做入库判断。

**tetraglyme**（tetraethylene glycol dimethyl ether，CAS 143-24-8）——本轮唯一的净新增温度点来源。Reaxys 侧 7 个已渲染温度点里，前 5 个与本地 288.15-308.15 K 逐点重合（差 0.01 K，属摄氏/开氏换算舍入），可作本地两条 JCT/TCA 来源的独立复现；净新增为高端 318.14 K 与 328.14 K 两点，一手出处 Rivas et al., J. Chem. Thermodynamics, 2006, 38(3), 245-256（1 MHz）。全部 7 点均来自该单一来源，因此新增点的独立性只体现在「与本地已有点的方法不同」上，不构成第二个独立来源。

**triglyme**（triethylene glycol dimethyl ether，CAS 112-49-2）——唯一一条是「提及级」条目：值/频率/温度/Location/Comment 五列全空，只有引文。本地 5 点温度序列严格更强。

**adiponitrile**（adiponitrile (hexanedinitrile)，CAS 111-69-3）——同样只有一条五列全空的提及级条目。本地 dielectric_observations_v11plus.csv 里该物质（登记名 hexanedinitrile，BTGRAWJCKBQKAO-UHFFFAOYSA-N）已有 278.15-353.15 K 共 31 个温度点——这条也修正了本轮早先按俗名 adiponitrile 做的覆盖度误判。

**diglyme**（diglyme (diethylene glycol dimethyl ether)，CAS 111-96-6）——Reaxys 侧 Property: dielectric constant 命中 0 个物质（PubChem 侧 7 个）。本地 6 点温度序列严格更强。

**TTE**（1,1,2,2-tetrafluoroethyl 2,2,2-trifluoroethyl ether，CAS —）——Reaxys 侧 0 个物质（PubChem 侧 5 个）。本地池内该物质（CWIFAKBLLXGZIC-UHFFFAOYSA-N）只有一个 298.15 K 点，因此它是真缺口——但 Reaxys 补不上，这一条维持未闭合。

## 4 净新增：4 条 / 2 个物质 / 3 篇一手文献

| 物质 | 净新增条目 | 温度点 (C) | 频率 (Hz) | 一手出处 | 口径限定 |
| --- | ---: | --- | --- | --- | --- |
| PC | 2 | [20.0, 35.0] | ['2E+06'] | Laurence, Christian; Nicolet, Pierre; Dalati, M. Tawfik; Abboud, Jose-Luis M.; Notario, Rafael - Journal of Physical Chemistry, 1994, vol. 98, #23, p. 5807-5816<br>Ritzoulis, George - Canadian Journal of Chemistry, 1989, vol. 67, p. 1105-1108 | 2 MHz AC；本地 PC 只有一个 298.15 K 点，故这两点相对本地是新温度点，但频率口径不同 |
| tetraglyme | 2 | [44.99, 54.99] | ['1E+06'] | Rivas; Iglesias; Pereira; Banerji - Journal of Chemical Thermodynamics, 2006, vol. 38, #3, p. 245-256 | 1 MHz AC；本地 tetraglyme 的温度序列到 308.15 K 为止，这两点是高端延伸 |

**口径限定（PC）**：PC 的「净新增 2 条」以 **v03 冻结表冠军行**（64.9 @ 298.15 K）为基线——PC 在**观测表**里是 0 行（`observation_table_distinct_T = 0`）。换成观测表基线这两条同样是净新增，但「本地已有 1 个点」这句话只对冻结表成立，基线切换在上一版里没有声明。

**频率口径**：4 条净新增点全部带给定频率（PC 两条 2 MHz、tetraglyme 两条 1 MHz），与本地常温序列不是同一频率口径；能否并入 v1.x 观测表由 v1.x 的频率口径决定，本产物不作判断。

tetraglyme 的 7 个已渲染温度点（1 MHz，14.99-54.99 C）里，前 5 个与本地 288.15-308.15 K 逐点重合（差 0.01 K，摄氏/开氏换算舍入），因此**可当本地两条 JCT/TCA 来源的独立复现**；净新增只有高端的 318.14 K 与 328.14 K。且这 7 点全部来自同一篇（Rivas et al. 2006, J. Chem. Thermodynamics, 38(3), 245-256），所以新增点的「独立性」只体现在测量方法与本地已有点不同，**不构成第二个独立来源**。

## 5 冠军核对（判决按证据强度降级）

| 冠军 | 冻结真值 | Reaxys 侧条目 | 判决 | 证据链要点 |
| --- | --- | --- | --- | --- |
| PC | 64.9 @ 298.15 K | 64.9 @ 25 C (Segura-Ramirez, ChemSusChem)；64.92 @ 25 C (Schroeder; Hubaud; Vaughey, Mater. Res. Bull. 2014, 49(1), 614-617) | `compilation_restatement_agrees` | 2 条互异题录，但同值且都指回同一部汇编 —— 转述一致，非独立测量 |
| EC | 90.5 @ 313.15 K | 89.78 @ 25 C (Schroeder; Hubaud; Vaughey, Mater. Res. Bull. 2014, 49(1), 614-617) | `value_matches_but_reaxys_temperature_label_conflicts` | 同一条 89.78：本仓库溯源记 40 C = 313.15 K，Reaxys 标 25 C —— 温度栏自相矛盾 |

**PC**：两条 25 C 条目与冻结真值相符，但这是**汇编转述一致**，不是两个独立测量。按本项目的证据纪律降级为 `compilation_restatement_agrees`，不得写成「独立旁证」。

> 交叉引用 `reports/jstage_corroboration.md`：Corroboration here means *agreement with a compilation restatement*, not independent measurement.

**EC**：89.78 就是本仓库已经溯源过的那个 89.78，但它属于 **40 C = 313.15 K**（= EC 冻结温度，相对偏差 0.80%）。Reaxys 把它标成 25 C，而 EC 熔点 36.4 C、25 C 根本不是液态，所以既不记为「一致」，也不记为「不冲突」，而记为「数值相符但 Reaxys 温度标注错」。这条同时是「Reaxys 温度栏不可信」的内部证据。

> 交叉引用 `reports/jstage_corroboration.md`：| Ethylene carbonate | **90.5** at 313.15 K (40 C) | 89.78 at 40 C | yes | 0.72 | 0.802% |

上一版把 PC 写成两个互相独立来源的复现，与本仓库自己的溯源结论相反：`reports/jstage_corroboration.md` 已写明该值来自汇编转述。本轮把判决降级为 `compilation_restatement_agrees` 并把证据链写成机读字段，同时补上 EC 那条被漏用的既有事实。

## 6 未闭合项

- tetraglyme 侧 Reaxys 声明 Dielectric Constant - 8 hits out of 8，但表内只渲染 7 行；缺失的那一条（疑为 39.99 C = 313.14 K）本轮未读到，属未闭合项。
- EC 的 5.4 @ 25 C 条目与同物质其余三条差一个数量级，未判定归属，只登记为可疑条目。
- PC 的 20 C / 35 C 两点在 2 MHz，能否进 v1.x 观测表取决于频率口径，本产物不作入库判断。
- PC 侧 Reaxys 声明 Dielectric Constant 10 hits，但表内只渲染 7 行（差 3 行）；未读到的 3 行本轮未闭合。
- EC / PC 在**观测表**里是 0 行（observation_table_distinct_T = 0），人工转录的 1 个温度点取自 **v03 冻结表**冠军行 —— 两个计数口径不同，不可混用。
- 1,1,2,2-tetrafluoroethyl 2,2,2-trifluoroethyl ether（TTE）在 Reaxys 与本地都只有单点，缺口未闭合。

## 7 纪律

- 本产物**只做数据侧探测**：不训练模型、不写 `data/`、不改池、不产出任何 L3 读数的替代值；
- Reaxys 取值一律 `restricted_crosscheck_only`，provenance 为 `reaxys<-bibliographic_citation`（Reaxys 渲染表只给文献题录、不给 DOI，写成 `reaxys<-primary_doi` 不准确），需用时可回到一手文献；
- **本产物确实含受限数值的机器可读镜像**（`readings[].rendered_rows`、`net_new_detail[].value`）：它只存于本仓库与 week13 交付包内，**禁止再次分发**，也不得并入任何可分发数据集；
- 队列 CSV 里的 `target_dielectric` / `target_T_K` 是**本地冻结表**的值，不是受限值；
- **本产物不产生任何通道可用性声明**：它不说介电通道可用、不说任何家族过门、不替代任何冻结读数、不改变任何 L3 结论；§5 的判决是**证据强度**判决，不是通道判决；
与「外部免费 ε(T) 扩张收官」的既有结论关系：**方向一致，不改结论**——Reaxys 的净增益是 4 条 / 2 个物质 / 3 篇一手文献，4 条全部带给定频率口径（PC 2 MHz、tetraglyme 1 MHz）。
