# G1+ 第四轮爬取：ThermoML 完整性、DC-200 可得性、四篇未闭环主源

证据文件 `probes/g1plus_crawl_round4_evidence.json`。三名只读研究者并行（Volta 本地复核、Dirac 网络抓取、Banach 开放途径），
主线程冻结写集、独立复核机器可读断言、合并证据，**本轮没有改动数据集任何单元格**。

与前三轮的区别：**这是第一轮每个 agent 都守住了 40 次/人子上限**（35 / 33 / 0），合计网络调用 68 次，用户 500 次/小时硬上限未被接近。

---

## 1. 最重要的发现：此前「本地 ThermoML 未命中」读的是局部子集

用户的怀疑成立。`data/processed/thermoml_normalized.csv` **不是全语料抽取结果**——它自己的 provenance 就写着
`raw_file_count: 5`、`row_count: 625`、`filter: dielectric_only`。5 个文件里 4 个产出 625 行，第 5 个（`j.tca.2015.08.011.xml`）产出 0 行。

独立重解析全部 **242 个本地 XML**：

| 指标 | 数值 |
|---|---:|
| 含结构化介电观测的 XML | 91 |
| 介电 `PropertyValue` 总数 | 11,646 |
| 其中零频 | 6,343 |
| 其中变频 | 5,303 |
| 纯液体零频观测 | 1,630 |
| 有纯液体零频观测的唯一分子 | 103 |
| **归一化表漏掉的行** | **11,021** |
| 反向差异（归一化有、XML 无） | **0** |

漏项是单向的：91 个介电来源里 **87 个在归一化表中完全无匹配**，只有 4 个被完整覆盖。

### 1.1 但被追踪的逐条抽取文件是完整的

独立重解析与 `data/processed/dielectric_raw.csv` 按
`DOI + data_number + property_name + value + temperature + InChIKey` 做多重集比对：**11,646 / 11,646 完全一致**
（唯一归一化是零频的 `frequency` 字段，旧表写 `'0'`、XML 侧为空）。

**结论**：这是**辅助文件的文档缺陷**，不是被追踪抽取的缺陷。两条记录必须分开表述，不能混为「ThermoML 抽取不完整」。

### 1.2 十个目标分子逐条回答（XML 级，非「归一化表未命中」）

| 目标 | 本地纯组分介电观测 | 判定 | 依据 |
|---|---:|---|---|
| PC | 0 | 有观测？否 | InChIKey 命中 26 个 XML、CAS 108-32-7 命中 1 个，与两种介电属性交集为空 |
| EC | 0 | 否 | InChIKey 命中 11 个、CAS 96-49-1 命中 1 个，交集为空 |
| diglyme | 9 | 是 | 9 条零频，已由两个同 DOI 来源代表 |
| triglyme | 15 | 是 | 8 条零频已代表；另 7 条为 1 MHz，来自新 DOI `10.1016/j.jct.2004.08.003` |
| tetraglyme | 11 | 是 | 6 条零频已代表；另 5 条为 1 MHz，来自新 DOI `10.1016/j.jct.2007.05.006` |
| adiponitrile | 31 | 是 | 31 条零频，DOI `10.1021/je300958c`，278.15–353.15 K，已代表 |
| glutaronitrile | 31 | 是 | 31 条零频，同 DOI，248.15–323.15 K，已代表 |
| MOPN | 0 | 否 | InChIKey 仅命中 `10.1016/j.jct.2008.05.012`，该文件无介电属性 |
| VC | 0 | 否 | InChIKey / CAS 872-36-6 / 名称全部 0 命中 |
| FEC | 0 | 否 | InChIKey / CAS 114435-02-8 / 名称全部 0 命中 |

**THF / NMP 假阴性风险已排除且被精确化**：THF（`WYURNTSHIVDZCO-UHFFFAOYSA-N`）精确命中 9 个 XML、NMP（`SECXISVLQFMRJM-UHFFFAOYSA-N`）精确命中 7 个 XML，
两者都**没有**任何结构化介电属性。但纯文本子串检索不安全——`tetrahydrofuran` 会误命中 `2-tetrahydrofurylmethanol`（另一个化合物），
所以该结论只在**用精确身份字段重导**时才成立。

### 1.3 补录 backlog（全部被现有的温压/频率闸门挡在门外）

| 类别 | 行数 | 分子 | 为什么不能直接并入 |
|---|---:|---|---|
| A 类新分子·零频 | 33 | 18-crown-6、butanedinitrile | 全部高于冻结近室温带（315.65–353.15 K / 333.15–373.15 K），需先做温度带决策 |
| B 类同分子新来源·零频 | 145 | dimethyl ether | 2,200–29,400 kPa 高压序列，只能做压力交叉核验 |
| 变频候选 | 550 + 344 | — | 需过频率闸门，不能并入近零频静态列 |
| C 类（分子与来源均已有） | 1,452 | 100 | 不是补录项 |

### 1.4 附带发现：全库归档是不可读的

`data/raw/thermoml_archive/ThermoML.v2020-09-30.tgz`：189,433,115 字节，SHA-256 `984a6f65…2cc807`，
首 8 字节为 `00 00 00 00 00 00 00 00`（**不是 gzip magic**），非零字节仅 8,359,677（4.41%）。
**它不是可读的 gzip 流**，因此本地 242 个 XML 缓存才是有效证据基础。

---

## 2. DC-200：数据集确实存在，但成员没有公开

论文锁定为 **Zhang et al., ACS Nano 2026，PMC13422007，DOI `10.1021/acsnano.6c06255`**，原文：

> we curated 200 aprotic samples measured experimentally at room temperature from the literature and public databases (82, 83) and refer to this data set as DC-200.

三点必须分开说：

1. **DC-200 存在**，200 条、室温、**实验**测量。它不是「拿不到所以不存在」。
2. **介电常数标签是实验值**；论文里计算的是辅助建模用的偶极矩，不是计算介电常数。
3. **成员未公开**：PMC Associated Data 只挂 SI PDF。主线程用本地缓存独立复核——SI 文本中 `DC-200` 出现 13 次，
   **全部是正文或图注**，没有成员表、没有逐行数值、没有逐行温度（只有 `"room temperature"`）。

SI PDF 经 AWS 开放镜像抓取，5,244,112 字节，SHA-256 `E6AFBAF9…C077BA57`，
与仓库既有缓存 `data/external/g1plus/compilations/nn6c06255_si_001.pdf` **逐字节一致**——即该解析是在一份独立下载的副本上重导的。

被挡的路径：ACS Cloudflare 403；PMC 直链返回 1,817 字节工作量证明页；Europe PMC `supplementaryFiles` 超时后得到不完整 ZIP；
作者 GitHub 递归列出 207 个对象、`truncated=false`，无 DC-200 或介电数据文件；Figshare 33005827 只有同一份 SI PDF。
来源方面 ref 82 = He et al. 2025（`10.1063/5.0267184`，`oa_status=closed`）、ref 83 = MNSOL 2012（自述 92 个溶剂），
论文未给出选出 200 条的规则，**无法唯一重建名单**。

**与本地 246 行的交集 = UNKNOWN，不是 0。** DC-200 端不发布任何身份字段，因此既给不出交集条数、也给不出交集 InChIKey 清单。
唯一可做的单点身份检查：正文 Figure 3a 讨论 DC-200 成员 `dimethoxymethane`，本地只有 `1,2-dimethoxyethane` 与 `1,1-Dimethoxyethane`——这对其余 199 个成员不构成任何结论。

---

## 3. 四篇未闭环主源：题录全部确证，数值全部仍被挡；并发现一处标识符错配

四篇的题录都经 Crossref / OpenAlex / Semantic Scholar 确证。开放途径全部失败：OUP 与 RSC 返回 403，
Springer 章节 303 跳转到 `idp.springer.com/authorize`，HAL 按 DOI 与题名均 `numFound=0`，
Google Books / Internet Archive / NDL Search 无响应，Europe PMC 四篇全部 `hitCount=0`。

**本轮的关键更正**：DOI `10.1039/j29660000005` 的题名是
*Physicochemical studies of some cyclic carbonates. Part V. The alkaline hydrolysis of vinylene carbonate*——
**这是一篇碳酸亚乙烯酯（VC）论文，不是己二腈/戊二腈论文**。
用 Crossref 按作者 Saadi + 1966 + adiponitrile/glutaronitrile/dielectric 检索，**没有**这样一篇腈类介电论文；
ECW-308 里的争议值 30 / 37 追到的是 Duncan 2013；而数据集**保留**的己二腈 32.12 与戊二腈 34.6 来自 ThermoML `10.1021/je300958c`，与 Duncan 不是同一条来源。

→ 该阻塞票据必须改名或换标识符。在澄清之前，**不得**把它写成「己二腈的原始测量」。

另两条边界更正：

- **Ue 2014 Table 2.3**（FEC 107 腿）仍未读到。仓库早先转录的 `… (FEC) 106 1.50 107 4.1 -13.30 1.45` 是**此前的人工观察**，
  本轮没有重新取得，不得当作本轮新读到的证据。
- **Flamme 2017** 在仓库链条中承载的是 PC 64.9、EC 89、VC 黏度，**并未**被确立为 FEC 78.4 的原始测量，
  在读到其表格前不得升级为主来源。

---

## 4. 请求预算（如实记账）

| agent | 目标 | 请求数 | 40 次子上限 | 是否突破 |
|---|---|---:|---:|---|
| Volta | ThermoML 本地完整性复核 | 0（纯本地） | 40 | 否 |
| Dirac | DC-200 抓取 | 35 | 40 | 否 |
| Banach | 四篇未闭环主源 | 33 | 40 | 否 |
| **合计** | | **68** | | |

用户硬上限 500 次/小时**未被接近**；主线程外部调用 0 次；没有 429 重试风暴。
所有 blocked 路径都具名到具体文献与具体失败状态，「查无此值」与「权限阻断」严格区分，本轮没有任何一条写成「无数据」。

---

## 5. 仍未闭环（按优先级，已更新）

1. **温度带决策**：33 条 A 类零频候选（18-crown-6、butanedinitrile）全部在近室温带之上。
2. **压力闸门**：145 条 dimethyl ether 高压序列（2,200–29,400 kPa）。
3. **频率闸门**：550 条 A 类 + 344 条 B 类变频候选。
4. **Saadi 1966 标识符更正**：现挂 DOI 是 VC 论文，需改名或换源。
5. **Ue, Ida & Mori 1994**（`10.1149/1.2059270`）：MOPN 的具名主来源候选，仍 blocked。
6. **Hagiyama 2008**（`10.1246/cl.2008.210`）：FEC 107 腿候选原始测量，OUP 403。
7. **Flamme 2017**（`10.1039/c7gc00252a`）：FEC 78.4 腿上游，RSC 403，且链条尚未确立其为此测量。
8. **DC-200 成员表**：需向作者索取数据可用性，已不是「访问失败」而是「发布缺失」。
