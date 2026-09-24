# G1+ 交叉验证：ECW-308 全表重抽与其引文链闭环

日期：2026-09-24
执行：主线程（本地零 API 调用，全部基于已落地的 SI PDF）
结构化证据：`probes/g1plus_ecw308_evidence.json`、`probes/g1plus_ecw308_crosscheck.json`
复现脚本：`probes/g1plus_ecw308_extract.py`（`--check` 可验证可复现性）
测试：`tests/test_g1plus_ecw308_extract.py`（33 项，离线）

## 一、这一轮解决了什么

v0.3.6 的 tier-2 只按目标分子逐行读了 ECW-308 的 SI，留下两个口子：

1. **引文链断在数字上。** SI 的 "Refs." 列印的是方括号编号（`[3, 16]`），编号到完整文献的映射在同一份文件的末尾参考文献表里。只读目标页，就只能看到"Hall et al.; Flamme et al."这样无法核验的残片。
2. **没有全表交叉验证。** ECW-308 是本任务重叠度最高的免费汇编，逐行读只能验证 10 个目标，无法回答"数据集其余行是否也被这份汇编支持"。

本轮把 Table S3 的 **308 行全部结构化**，并把它与冻结数据集做了逐行对账。

## 二、方法：为什么必须做坐标抽取

纯文本 dump 无法支撑这次对账，实测原因是具体的：

- 行是**流式**排布的，多行挤在同一行（`... [16, 34, 36] 159. Propylene carbonate ...`）；
- 第 **279 行的行号在 PDF 里没有句点**（`279`），按 `N.` 切分会整段丢行；
- 第 167 行的行号与名称**粘在一起**（`167.4-Trifluoromethyl...`）；
- SI 对部分条目**上下堆叠两个介电常数值**（MOPN：`36.00` 有引文、`25.00` 无引文）。

因此抽取走 pypdf 的坐标文本流，列归属完全由几何决定：

| 规则 | 内容 |
|---|---|
| 列带 | 介电常数列 = 粘度表头 x 与介电表头 x 的中点 → 介电表头 x 与电导表头 x 的中点（实测 486.3–559.7 pt） |
| 行号 | 行号必须等于**期望的下一个序号**（1→308），断链即停并报告 |
| 行块 | 单元格归属于"基线在其正上方 0–20 pt（允许上溢 2 pt）"的那一行 |
| 取值 | 只有带内恰好一个数值 token 才记 value，否则 blank / missing / stacked |
| 温度 | 列头写明 25 °C 且 SI 无逐行测温，故一律记 `temperature_source = column_header` |

**锚点回归：11/11。** v0.3.6 手工读出的 11 个值（EC 89.00、PC 64.90、VC 126.00、FEC 78.40、triglyme 7.53、diglyme 7.40、MOPN 36.00、ADN 30.00、GLN 37.00、sulfolane 43.00、ACN 37.00）在自动化结果中全部命中，且这 11 条已固化为测试用例。

## 三、抽取覆盖

| 状态 | 行数 | 含义 |
|---|---:|---|
| value | 87 | 带内恰有一个数值 |
| blank | 204 | 单元格印的是 `/` |
| missing | 11 | 带内无任何 token |
| stacked | 6 | 上下堆叠两个数值（不取数） |
| 合计 | 308 | 行号序列完整到达 308 |

另解出 **54 条参考文献**（编号 → 完整引文）。未被任何行块认领的带内 token 记录在 `unclaimed_cells`（31 条，含表头单词与孤立 `/`），不作数值使用。

## 四、引文链闭环：ECW-308 编号 → 完整文献

这一节直接回答了原先"Hall et al. / Flamme et al. 到底是哪篇"的问题。

| 编号 | 完整引文 | 本轮影响到 |
|---|---|---|
| [2] | M. Ue, K. Ida, S. Mori, *J. Electrochem. Soc.* **1994**, 141, 2989 | ACN、sulfolane |
| [3] | D. S. Hall, A. Eldesoky, E. R. Logan, E. M. Tonita, X. Ma, J. R. Dahn, *J. Electrochem. Soc.* **2018**, 165, A2365 | **VC 126.00** |
| [16] | B. Flamme, G. Rodriguez Garcia, M. Weil, M. Haddad, P. Phansavath, V. Ratovelomanana-Vidal, A. Chagnes, *Green Chem.* **2017**, 19, 1828 | PC / EC / VC / FEC / DEC / EME |
| [34] | H. Duncan, N. Salem, Y. Abu-Lebdeh, *J. Electrochem. Soc.* **2013**, 160, A838 | **ADN / GLN / PMN** |
| [36] | E. Perricone, M. Chamas, L. Cointeaux, J. C. Leprêtre, P. Judeinstein, P. Azais, F. Béguin, F. Alloin, *Electrochim. Acta* **2013**, 93, 1 | **MOPN**、EC、PC |
| [40] | Y. Huang, L. Zhao, L. Li, M. Xie, F. Wu, R. Chen, *Adv. Mater.* **2019**, 31, 1808393 | diglyme / triglyme |
| [42] | K. Deng, Q. Zeng, D. Wang, Z. Liu, G. Wang, Z. Qiu, Y. Zhang, M. Xiao, Y. Meng, *Energy Storage Mater.* **2020**, 32, 425 | **FEC 78.40** |

**VC 溯源结论**：ECW-308 的 VC 值 126.00 引 `[3, 16]`，即 Hall 2018 + Flamme 2017，**不是** Saadi & Lee 1966。数据集现存 VC `conflict_open` 的付费墙对象（Saadi & Lee）因此不是 ECW-308 这条链上的原始来源，两者是**不同的证据线**，不应合并。

**MOPN**：ECW-308 条目同时印 `36.00`（引 Perricone 2013）与 `25.00`（无引文），抽取器按规则记为 `stacked` 并保留两个值，未取数；交叉核对确认数据集现值 36.0 落在该单元格内。

## 五、全表对账：16 条通过身份门控的比较

身份门控 = **分子式一致 且 名称身份成立**（去括号全名相同，或命中显式同义词表）。只有分子式相同、名称身份不成立的行一律记 `formula_only_candidate`，**不计入冲突**。这条规则排除了初版的两个假阳性：甲酸甲酯↔乙酸、甲基丙基碳酸酯↔碳酸二乙酯。

结果：**5 条一致到 1% 以内、6 条一致到 5% 以内、5 条分歧**。

### 5.1 一致（8 条）

乙酸乙酯 6.02 = 6.02、碳酸丙烯酯 64.90 = 64.90、乙酸甲酯 6.70 vs 6.68、丁酸甲酯 5.50 vs 5.48、triglyme 7.53 vs 7.604、DME 7.20 vs 7.0695、THF 7.40 vs 7.50、丙酸甲酯 6.07 vs 6.20、碳酸乙烯酯 89.00 vs 90.50、磺砜 43.00 vs 44.00、suberonitrile 25.00 vs 25.94。

其中 EC 的比较是**跨温度**的：ECW-308 是 25 °C 列值，数据集取 313.15 K 的 90.5，-1.7% 的差异与已知温度趋势同向，不构成矛盾。

### 5.2 分歧（5 条）

| # | 分子 | ECW-308 | 引文 | 数据集 | 相对差 | 判读 |
|---|---|---:|---|---|---:|---|
| 52 | glutaronitrile | 37.00 | [34] Duncan 2013 | 34.6（JCED 一手） | +6.9% | 见下 |
| 53 | adiponitrile | 30.00 | [34] Duncan 2013 | 32.12（JCED 一手） | −6.6% | 见下 |
| 54 | pimelonitrile | 28.00 | [34] Duncan 2013 | 29.71 | −5.8% | 见下 |
| 160 | diethyl carbonate | 3.00 | [16, 34] | 2.834 | +5.9% | 汇编两位小数、来源为整数 |
| 166 | fluoroethylene carbonate | 78.40 | [16, 42] Deng 2020 | 102（开放综述表） | −23.1% | 与既有 `public_values_78.4_102_107` 同一冲突 |

**关键判读（本轮新增）**：三条腈类分歧**同一个根因**——它们全部只引 `[34]` Duncan 2013。而上一轮对 Duncan 原文（NRC 接受稿）的核验已确认：该文 Table I 只印整数 `30 / 37 / 89`，**没有给出测量温度、频率与不确定度**，也不区分原始测量与比较数据。ECW-308 把这批整数抄成了两位小数（`30.00 / 37.00`），精度是**二次汇编制造的**，不是原始测量精度。

因此 ADN/GLN/PMN 的"分歧"不是两条独立实验的对立，而是"一手值 vs 由整数转抄来的汇编值"。数据集保留一手值、把 ECW-308 记为低等级交叉参考，是**正确的取舍**；既有 conflict 单可据此降级为"来源等级差异"。

FEC 的 −23.1% 与 DEC 的 +5.9% 维持开放：FEC 的 78.4 与 102 来自不同一手链条（Deng 2020 vs 综述表），本轮未能取得任一侧的原文数值，不能收敛。

## 六、局限（不得越界使用）

1. ECW-308 是**二次汇编**，只能作为交叉核对与引文线索，不能覆盖数据集里的一手值。
2. 表头把数据来源写成"literatures and ChemSpider/PubChem database"，混合了文献值与数据库值；即使身份门控通过，仍需回读该行引文再引用。
3. 介电常数列统一标 25 °C，无逐行测温，**不能**据此推断数据集其他温度的记录。
4. 87/308 行有数值，204 行印 `/`（SI 本身无值），11 行单元格缺失，6 行堆叠——覆盖面有限，未被比较的行**不等于**"不一致"。
5. 13 行通过分子式但未通过身份门控，列为 `formula_only_candidate` 供人工判身份，**未**当作冲突。

## 七、复现与哈希

| 项目 | 值 |
|---|---|
| 源 SI PDF SHA-256 | `19f1166e2aba6834f0cccb1d751b618dded5c80f97ab5b9957b2d15046bdbc76`（脚本内固定，不匹配即中止） |
| evidence SHA-256 | `ac890473f4a07e68c5f04b93d4f30472a30d1d118bf69e417a0606e0966f75fb` |
| crosscheck SHA-256 | `a1bed4df36227c2da58867e54338a5b8b833a0a487db760619bf87efbdd6ab01` |
| 换行 | 两份均为纯 LF |
| 复现命令 | `.venv\Scripts\python.exe probes\g1plus_ecw308_extract.py --check` |
| 数据集是否改动 | **未改动**（本次为交叉核对，任何介电数值与 `conflict_status` 均未写入数据集） |

