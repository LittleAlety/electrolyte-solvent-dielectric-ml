# Perricone 2011 论文取证、GVL 冲突更正与四甘醇二甲醚（tetraglyme）独立核验

日期：2026-09-24
执行：只读 agent（Kierkegaard）网络取证 + 主线程本地整合
状态：**本轮未改动数据集**（见第七节"为什么没有写库"）

## 一、为什么这一节重要

执行手册里 GVL 的冲突被写成"某博士论文正文两个表自相矛盾（36.1 vs 32/34）"。本轮把该论文全文拿到手后，这个描述**不成立**，需要更正——它把两件事混成了一件：

- 论文内部确实有矛盾，但是 **34 vs 32**；
- **36.1 根本不在该论文里**，它来自数据集自己引用的开放综述表（Sun et al. 2026, *iScience*, DOI `10.1016/j.isci.2026.115778`）。

## 二、Perricone 2011 论文获取状态（从不闭合变为已获取）

| 项目 | 内容 |
|---|---|
| 标题 | *Mise au point d'électrolytes innovants et performants pour supercondensateurs* |
| 作者 | Emmanuelle Perricone |
| 年份 / NNT | 2011 / `2011GRENI032` |
| HAL id | `tel-00630049`（openAccess_bool=true） |
| 元数据页 | https://theses.hal.science/tel-00630049 |
| 全文 PDF | https://theses.hal.science/tel-00630049v1/file/Perricone_emmanuelle_2011_archivage.pdf |
| 实测获取结果 | **HTTP 200, application/pdf，214 页，2,829,426 bytes** |
| 获取方式 | 命令行取件先返回 Anubis 工作量证明挑战页；完成 PoW 后取得 PDF（不是破解付费墙，该文件本身是 openAccess） |
| 下载位置 | 系统临时目录（未写入仓库；论文受版权保护，不随仓库分发） |

> 上一轮 tier3 报告中"页面正文不在只读 DOM 作用域内、无法读取 PDF 文本"的记录，本轮已被这条命令行路径取代。

## 三、MOPN（3-甲氧基丙腈）的原文证据

| 表 | PDF 页 / 印刷页 | 表头 | 逐字行 | εr | 温度 |
|---|---|---|---|---:|---|
| Tableau 4 | PDF p.41 / 印刷 p.28 | `εr à 25°C` | `Méthoxypropionitrile [43] - 57 165 66 1,1 36` | **36** | 25 °C |
| Tableau 12 | PDF p.78 / 印刷 p.65 | — | `Methoxypropionitrile MP 165 66 1,1 36 Xi` | **36** | 表头未明示 |
| Tableau 14 | PDF p.90 / 印刷 p.77 | `Constante diélectrique à 25°C` | 列名 `EC GV S AM AE MP MMOA MIPA EDFA BN PC ACN`，`MP` 列 = `36` | **36** | 25 °C |

**判读与纪律**

1. 论文原文只写 **36**，**没有写 36.00**。ECW-308 与数据集里的两位小数不是本论文的精度，不能据论文把它"确认成 36.00"。
2. 三张表都是**文献汇编表**（Tableau 4 该行引 `[43]`，即 Ue 1994 一线），**不是作者自测**。因此 MOPN 的证据等级**保持在"二次汇编"**，但来源从"ECW-308 转述"前移到了"Perricone 2011 原始论文逐字"，这是一次实质性的溯源前移。
3. MOPN 仍然在没有 GFN2-xTB 特征行的情况下**不参与拟合**（`model_ready=false`），此次取证不改变这一点。

## 四、GVL 冲突的更正结论

论文全文文本层检索 `36.1` 与 `36,1`：**无命中**。可检出的矛盾是 34 vs 32：

| 表 | PDF 页 / 印刷页 | GVL 值 | 温度 | 逐字行 |
|---|---|---:|---|---|
| Tableau 4 | PDF p.41 / 印刷 p.28 | **34** | 25 °C | `γ-valérolactone [49] - 31 208 81 2,0 34 4,29` |
| Tableau 8 | PDF p.65 / 印刷 p.52 | **32** | 25 °C（表题注明 sauf précision contraire） | `γ-valérolactone GV - 31 207 81 2,18 32 d Xi` |
| Tableau 14 | PDF p.90 / 印刷 p.77 | **34** | 25 °C | `Constante diélectrique à 25°C 90 34 43 (30°C) 6.7 6 36 ...`，`GV` 为第 2 列 |

### 更正后的冲突结构

| 值 | 实际出处 | 层级 | 状态 |
|---:|---|---|---|
| **36.1** | Sun et al. 2026, *iScience* 29, 115778, Table 3（数据集自引的开放综述表） | 综述表 | 该表的**一手上游未回溯**；论文里查无此值 |
| **32** | Perricone 2011 Tableau 8，上游引 `[87]` | 论文表 → 上游 2002 年 J. Phys. IV France 论文 | 上游全文 blocked（EDP 403 / HAL 无 OA / ISTEX 需机构认证） |
| **34** | Perricone 2011 Tableau 4（引 `[49]` Xu 2004 综述）与 Tableau 14（未给逐行来源） | 论文表 → 综述 | 34 的一手来源未闭合 |

**因此**：这不是"同一篇论文内部写出三个值"，而是**跨文献冲突**——开放综述表的 36.1（一手未回溯）对上博士论文的 32/34（一手均未闭合）。数据集现行 GVL 行标注 `open_access_review_table` / `model_ready=true`，**其值 36.1 在本轮仍未获得任何一手支撑**，该票据应保持开放，且不适合当作已裁决。

## 五、tetraglyme 的独立一手数值（意外收获）

上一轮 tier-2 已确认 tetraglyme 在 ECW-308 里**未命中**，属明确的汇编缺口；数据集该行的值 7.798 @298.15 K 来自 ThermoML。本轮 agent 找到一条**独立的一手测量**：

| 分子 | 值 | 温度 | 频率 | 方法 | 来源 |
|---|---:|---|---|---|---|
| TEGDME (tetraglyme, CAS 143-24-8) | **7.816** | 298.15 K (25 °C) | **1 MHz** | Agilent 16452A 液池 + 4294A 精密阻抗分析仪，静态常压 | arXiv:2402.05989，Table 1（PDF p.16） |

同表另给 7.939 @293.15 K、7.692 @303.15 K，方法原文见该 PDF p.4：
`Permittivity measurements were taken using the Agilent 16452A cell, connected to a precision impedance analyzer model 4294A ... measurements were taken at 1 MHz.`

**交叉核对结果**：数据集 7.798 @298.15 K（ThermoML）vs 本条 7.816 @298.15 K @1 MHz，相对差 **+0.23%** —— 在相同温度上高度一致，且这条给出数据集缺失的**频率条件**（1 MHz）。

**保留意见（不得省略）**：agent 把该表归到 DOI `10.1016/j.tca.2012.10.024`，但**arXiv 预印本与该 DOI 的对应关系本轮未复核**。因此本报告只把 **arXiv:2402.05989 Table 1** 记为实际读取到的来源，DOI 归属标注为"待核"。在复核前不得把这条写进数据集的 `source_doi`。

## 六、醚/腈族的本轮结论

| 分子 | 结论 | 阻断证据 |
|---|---|---|
| tetraglyme | **取得独立一手值 7.816 @298.15 K @1 MHz**（见上） | — |
| diglyme / triglyme | 汇编值 7.40 / 7.53 **未获一手逐字核验** | 候选一手测量 DOI `10.1016/j.jct.2010.09.008` 被 OpenAlex 标为 closed，无 OA |
| adiponitrile | 未取得独立一手值 | 候选 DOI `10.1149/1.3023084` 被 Radware/perfdrive 机器人验证拦截（302 → validate.perfdrive.com） |
| glutaronitrile | 未取得独立一手值 | 候选 NRC 开放稿返回 **HTTP 410**（`Resource is no longer available`） |

Perricone 论文另给一条**非独立**的 adiponitrile 表值：Tableau 4（PDF p.41 / 印刷 p.28）`Adiponitrile [43] 2 295 6,0 30`，即 30 @25 °C；它来自表中引文，**不能**替代独立一手核验。

Europe PMC 检索端点本轮返回 **HTTP 500**（`tetraglyme`、`triglyme` 两次最小复测均 500，HTML `Error: 500`）。按纪律记为 **blocked，不是 not_found**。

## 七、为什么本轮没有写库

1. MOPN 的 36 已获论文逐字确认，但**精度只有整数**；数据集现值 36.0 在数值上不冲突。若要把"Perricone 2011 Tableau 4/12/14"写进该行的 provenance note，那是一次 **notes 变更**，会改变 `data/dielectric_v03.csv` 的哈希，牵动 week7 报告、decisions log、agent_workflow 与多处固定哈希——应作为**独立的 provenance patch**（像 v0.3.5/v0.3.6 那样）来做，而不是塞进一次交叉核对提交。
2. tetraglyme 的 7.816 尚未完成 arXiv↔DOI 归属复核，**不具备入库条件**。
3. GVL 的 36.1 vs 32/34 仍是一条**未裁决**的跨文献冲突，写任何一侧进数据集都是替用户做决定。
4. 因此本轮只产出证据与更正，数据集哈希保持
   `f5256d164c814030a4b986db6c878f1d64edb2b4f91cf39af3a75ffeaeac853c`。

## 八、请求与预算（诚实记录）

| agent | 请求数 | 预算 | 备注 |
|---|---:|---:|---|
| Kierkegaard（本节 A/B 部分） | 59 | 80 | 未超支，未写仓库文件 |
| Ramanujan（ECW-308 引文链 + GVL 交叉） | **≥87 次 HTTP + 约 12 次文档导航（合计约 99）** | 80 | **超支**；失败/阻断至少 16 次 |

Ramanujan 的预算超支记录在案：其日志无法严格证明每次重试都不超过 2 次。这不影响已取得的题录（每条都经 DOI 元数据匹配），但下一轮必须把预算门控做在 agent 的工具层而不是提示层。
