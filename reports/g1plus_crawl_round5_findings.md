# G1+ 第五轮爬取：FEC 78.4 与 VC 126 两条腿在原始测量层面闭死

证据文件 `probes/g1plus_crawl_round5_evidence.json`。四名只读研究者并行
（Tesla 标识符与腈类、Peirce 两篇挡墙文献、Ampere Flamme/78.4 上游、Pasteur 三个数据源适用性），
主线程冻结写集、用已登录的 Reaxys 检索、解析两份机构访问 PDF、独立复核机器可读断言、合并证据。
**本轮没有改动数据集任何单元格**——两条可落地的更正都写成字段级补丁留在 backlog，原因见第 9 节。

---

## 1. 头条一：FEC 的 78.4 是一条原始测量，温度 23 °C

链条的最后一跳读到了。

Kobayashi, Inoguchi, Iida, Tanioka, Kumase & Fukai, *J. Fluorine Chem.* **120**(2), 105–110 (2003),
DOI `10.1016/S0022-1139(02)00317-2`，**Table 2** "Physical properties of non-fluorinated and
fluorinated carbonates"，第三条数据行逐字为：

```
210   17.3   1497   4.1e   78.4e   1.04e   Our data
```

三个要点：

| 要点 | 原文依据 |
|---|---|
| 温度 = 23 °C | 介电值写作 `78.4e`，Table 2 脚注 **e = "At 23 °C."** |
| 是自己测的，不是转抄 | Table 2 脚注 **b = "Physical properties are cited from ref. [11,12] except our data."**，该行 Ref 列写 **"Our data"** |
| 这一行就是 FEC | 该行 mp 17.3 / bp 210 / 黏度 4.1 / ε 78.4 与 Flamme 2017 Table 1 entry 21 的 FEC 四项完全一致 |

完整链条：

```
ECW-308 Table S3 entry 166  (78.40)
   -> Flamme 2017 Table 1 entry 21  (78.4, 引 [36],[42])
      -> [42] Kobayashi 2003 Table 2  (78.4, "Our data", 23 °C)
```

**温度边界必须记下来**：规范行存的是 298.15 K，原始测量在 23 °C = **296.15 K**，差 2.0 K。
在本轮 5 K 的比较窗口内，但**不是同一温度**，不做四舍五入掩盖。

同表还给可用的交叉项：EC = 90 @ 40 °C（引自 [11]）、PC = 65 @ 20 °C（引自 [11]）——
注意这两行是**引用他人**，不是 Kobayashi 自己测的。

## 2. 头条二：VC 的 126 也是一条原始测量，温度 25 °C，±1.0

Saadi & Lee, *J. Chem. Soc. B: Physical Organic*, 1966, pp. 5–6, DOI `10.1039/j29660000005`。
实验部分原文：

> Calibration of the cell with benzene, methanol, and water gave a linear capacity-dielectric constant
> plot of slope 1.014 ppf per dielectric unit; extrapolation of this line to the capacity of the cell
> when filled with vinylene carbonate gave: **E (25°) = 126 ± 1.0**.

**Table 2** "Physical properties of some cyclic carbonates at 25°"：

| 化合物 | ε | μ (D) | ρ | B.P. (°C) |
|---|---:|---:|---:|---:|
| **Vinylene carbonate** | **126** | 4.45 | 1.81 | 162 |
| Ethylene carbonate \* | 95.3 | 4.78 | 1.27 | 238 |
| Propylene carbonate | 61.0 | 4.94 | 1.08 | 232 |
| Chloroethylene carbonate \* | 62.0 | 3.99 | 1.45 | 212 |
| Water | 78.5 | 1.84 | 2.57 | 100 |

（\* = At 40 °C，其余为 25 °C。）

**数据集存储的 126 是对的**，缺的是它当时的"身份"——这一轮把它从"开放获取综述正文"
升级为"原始测量 + 明示不确定度 ±1.0"。存储温度 298.0 K 与 25 °C（298.15 K）差 0.15 K，
在原文报告精度之内。

### 2.1 顺带把 Saadi 标识符彻底定案

第四轮发现 DOI `10.1039/j29660000005` 是**碳酸亚乙烯酯**论文而不是己二腈/戊二腈论文，
但当时只能靠题名判断。这一轮两条独立证据把它钉死：

- 原文拿到手，题名与摘要确认测的是 vinylene carbonate 的介电常数与偶极矩；
- 已登录的 Reaxys 里，该引用被挂在 vinylene carbonate 物质行（CAS 872-36-6，
  Reaxys RN 105683）的 "Dielectric Constant - 1" 分类下。

也就是说：**仓库此前把它当腈类票据是仓库的错，标识符本身没错。**

## 3. 给第四轮补下一层：Flamme 2017 **确实**承载 FEC 78.4

第四轮证据写的是"Flamme 2017 未被确立为 FEC 78.4 的原始测量"。**这句话本身没有错，也没有被撤回**：Flamme 确实不是原始测量，第四轮只是把 Flamme 的全文留在了未取得状态。
本轮 Ampere 从 HZDR 机构库取到全文，因此是**补下一层**（Flamme 到底承不承载），不是反转上一条结论：

- 正文原句：`a decrease of the dielectric constant is observed when EC is replaced by FEC
  (εr=89.8 for EC and 78.4 for FEC, Table 1, entries 20 and 21)`；
- Table 1 entry 21 逐字：`17.3 210 4.1 78.4 4.70 1.50 (70.70) 5.0 6.6 (Pt) [36],[42]`。

另外，Crossref 的 `reference.key` 相对 Flamme 的方括号编号存在 **+3 下标偏移**：
校正后 `[36]` = Ue et al. 2014 专著章节，`[42]` = Kobayashi 2003。
第四轮把数组第 35/41 项直读成 `[36]/[42]` 会错解，本轮已修正。

**结论分两层，必须分开写**：Flamme **是**承载者（第四轮未确立，本轮确立）；Flamme **不是**原始测量。

## 4. 受限互证：把"同源确认"和"独立互证"分开

本轮最容易被误用的成果是"受限数据库和我们一致"。**一致分两种，价值完全不同。**

| 目标 | 数据集来源 | 受限记录的引用 | 判定 |
|---|---|---|---|
| 己二腈 | Swiergiel (2013) | Swiergiel (2013) | **同源确认**（同一 DOI `10.1021/je300958c`） |
| 戊二腈 | Swiergiel (2013) | Swiergiel (2013) | **同源确认**（同一 DOI） |
| 四甘醇二甲醚 | Riadigos (2011); Rivas (2012) | Iglesias 2001 / Pereira 2001 / Rivas 2006-07 / Ugelstad 1965 | **独立互证**（8 条近室温行） |
| 四氢呋喃 | Sun (2026) 综述表 | 19 位不同作者，25 条近室温行 | **独立互证** |
| N-甲基吡咯烷酮 | Sun (2026) 综述表 | George 2004 / Olavi 1967 / Granshan 1970 / Uosaki 1996 | **独立互证** |
| 二甘醇二甲醚 | Lago (2009); Riadigos (2011) | Lago 2009 + Goldshtein 1967 + Ugelstad 1965 | **混合**：一条同源、两条独立 |

计数：`same_source_confirmation 2 / independent_sources_only 3 / mixed 1 / no_capture 10`。

**两个腈类只有"抄写正确"级别的证明，没有独立互证。** 这一点写进报告与证据文件，
不允许后续被美化成"独立验证通过"。

## 5. 压力闸门：NMP 的 100 kPa–250 MPa 序列被挡住

NMP 的 Uosaki 1996 是一条**压力序列**（100 kPa → 250 MPa），而 canonical 行是常压值。
生成器实现 90–110 kPa 的常压窗口并逐条计数：NMP 保留 5 条窗口内近室温行，
**排除 5 条加压行**。没有任何加压值进入比较。

## 6. 本地 ThermoML：两个存储均值可复现，环丁砜存的是单点取值

| 目标 | 存储值 | 本地观测 | 算术 | 存储值就是均值吗 |
|---|---:|---|---:|---|
| 二甘醇二甲醚 | 7.3815 | Lago 2009 (7.363) + Riadigos 2011 (7.4) | 均值 7.3815 | **是** |
| 乙二醇二甲醚 | 7.0695 | Lago 2009 (7.069) + Riadigos 2011 (7.07) | 均值 7.0695 | **是** |
| 环丁砜 | 44.0 | Rivas 2012 三点 293.15/298.15/303.15 K = 44.5 / 44.0 / 43.4 | 均值 43.967 | **否**，存的是 298.15 K 那一个单点 |

前两行的存储值就是观测值的算术平均，能逐条复现。**环丁砜不一样**：三条同源观测
（44.5 / 44.0 / 43.4）的均值是 43.967，但数据集存的是 **298.15 K 的单点 44.0**
（该行 `n_observations=3`）。"存单点"和"存均值"是两种口径，不能混称。
证据文件里这一条也**只列观测值、不写 `mean` 字段**，免得 43.967 被误读成存储值。

## 7. 受限目录覆盖缺口：4 个目标"有目录记录、无取值"

有目录记录但**没有抓到任何近室温行**（因此无从比较）：
EC（`SMI_SC_31657`）、GVL（`SMI_SC_31853`）、DME（`SMI_SC_31827`）、环丁砜（`SMI_SC_31784`）。

目录里**完全没有**：MOPN、VC、FEC、三甘醇二甲醚、碳酸丙烯酯（PC）、乙腈。

**目录里有记录 ≠ 有可用数值。** 证据文件里两者严格分开写。

## 8. 三个数据源的否定结论与两个网站的不可达

| 数据源 | 判定 | 依据范围 |
|---|---|---|
| Materials Project | **不适用** | SiO₂ 对照 200 / `total_doc=322` 证明 key 有效；EC、PC、乙腈均 `total_doc=0`；其介电量是晶体计算值，不是液体实验值 |
| NIST WebBook | **无介电数据** | 53 个缓存文件全文检索 `dielectric/permittivity/epsilon/ε` 命中 **0**；水/甲醇/乙醇/丙酮正对照同样为 0 |
| CatalystHub | **入口不可达** | 三个入口测试，两个超时；相似域名 200 但身份未确认；密钥未发送到未确认主机 |

SpringerMaterials 与上海有机所数据库**当前都打不开**（用户确认），
因此本轮**没有从这两处取得任何新抓取**；涉及这两处的受限陈述都是对 2026-09-23 已有磁盘抓取的重读。
但本轮**确实新增了受限材料**，来自另外几个付费/受限源：Kobayashi 2003（HZDR 机构库外的付费原文）、
Saadi & Lee 1966、Reaxys 抓取、Flamme 2017 HZDR 副本。清单见 `probes/g1plus_crawl_round5_evidence.json`
的 `new_restricted_materials_this_round`。
上海有机所那次会话返回的是"无此用户名"错误页，不是已登录态，所以那里一次查询都没发。

## 9. 为什么本轮仍然"不改数据"：两条更正都已写成字段级补丁

两条头条各自意味着一次数据修订，但 `data/dielectric_v03.csv` 的规范哈希被
**约 20 个探针、报告与测试**写死（`765fd8e0…`）。改一格就要连带重跑这些产物，
必须作为**独立的数据修订轮**落地，而不是混在取证轮里。

补丁已逐字段写进 `probes/g1plus_crawl_round5_evidence.json` 的 `backlog`：

- **FEC**：`dielectric 102 -> 78.4`、`T_K 298.15 -> 296.15`、`evidence_level -> primary`、
  `source_doi -> 10.1016/S0022-1139(02)00317-2`、`source_table -> Table 2`、
  `temperature_source -> reported`、`source_quality -> primary_experimental`，`notes` **必须按原始测量重写**，
  `model_ready` **保持 false**（78.4 vs 107 的冲突未解，且动它会改变冻结的拟合子集）。
- **VC**：数值不用改，改的是身份——`evidence_level -> primary`、
  `source_doi -> 10.1039/j29660000005`、`source_table -> Table 2`、`source_quality -> primary_experimental`、
  `temperature_source -> reported`、`notes` **必须按原始测量重写**、
  `uncertainty_kind -> reported` + `uncertainty_value 1.0`，`conflict_status` 重写为
  "Knovel 78–127 是包含原始值的低信息量区间，不是竞争点值"。
  许可与再分发字段必须重新推导（原始源是 1966 年付费论文，不再是 CC BY-NC）。

## 10. 请求预算（如实记账）

| agent | 目标 | 请求数 | 40 次子上限 | 是否突破 |
|---|---|---:|---:|---|
| Tesla | Saadi 标识符 + 腈类原始源 | 40 | 40 | 否 |
| Peirce | Hagiyama 2008 / Ue 1994 开放途径 | 40 | 40 | 否 |
| Ampere | Flamme 2017 与 78.4 上游 | 40 | 40 | 否 |
| Pasteur | MP / WebBook / CatalystHub 适用性 | 10 | 40 | 否 |
| **合计** | | **130** | | |

用户 500 次/小时硬上限未被接近；主线程没有从本环境发出计量 API 调用
（Reaxys 走浏览器已登录会话，两份 PDF 由用户提供）。

## 11. 仍未闭环（按优先级）

1. **FEC 107 腿**：107 已在 Ue et al. 2014 Table 2.3（印刷页 101）汇编层读到；具名原始源 Hagiyama 2008 仍受 OUP/Cloudflare 403 阻断。
2. **MOPN 介电值**：Ue, Ida & Mori 1994（IOPscience 付费摘要页）。Repo 侧已确认 Reaxys 无该分类。
3. **受限目录 4 个未取值目标**：需要 SpringerMaterials 恢复可达。
4. ~~**v0.3.12 数据修订**：把上面两条字段级补丁落地并重跑级联。~~ **已结清（2026-09-25）。**
5. 温度带决策（33 条 A 类）、DC-200 成员表。
