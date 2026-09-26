# Reaxys 介电队列第一刀（FEC / VC / GVL / DME / sulfolane + MOPN 复验）

**日期**：2026-09-26
**浏览器**：Edge（用户已登录的 Reaxys 会话）
**方法事实**：Reaxys 网页端（用户已登录的 Edge 会话）**手动逐条查询**；未使用批量爬虫、未批量导出、未自动遍历。受限值口径见 `restricted_values_contract`：受限 Reaxys 数值**已镜像在本产物的 CSV 与 summary 内**，**禁止再分发**，**不得并入数据集或候选池**，本产物**不声明任何通道可用**。
**产物**：`probes/reaxys_dielectric_queue_first_cut.csv`（19 行）、`probes/reaxys_dielectric_queue_first_cut_summary.json`、`probes/verify_reaxys_dielectric_queue_first_cut.py`

## 0 结论速览

| 化合物 | Reaxys 介电条目 | 本地观测表行数 | 净新增 | 判决 |
| --- | ---: | ---: | ---: | --- |
| FEC（114435-02-8） | 1（Static Dielectric Constant） | 1 | **0** | 只有 78.4 @ 23 °C（Kobayashi 2003），**无 107 腿**；该类别**无频率/方法列** |
| VC（872-36-6） | 1（Dielectric Constant） | 1 | **0** | 无数值**引用存根**；Reference DOI 与冻结行 `source_doi` **逐字相同** |
| **GVL**（108-29-2） | 1（Dielectric Constant） | **0** | **+1** | **真缺口**：Reaxys 36.9（Segato 2021, SI）vs 冻结行 36.1（iScience 2026 综述表），**两者都无温度** |
| DME（110-71-4） | 7（Dielectric Constant） | 9 | **+1 线索** | 本地温度序列已在；Reaxys 新增唯一带温度区间的源 Werblan 1985（7–9.1 @ −30…25 °C, 1591 Hz） |
| **sulfolane**（126-33-0） | 12（Dielectric Constant） | 8 | **0** | Reaxys 与本地**逐点一致**（同一 DOI）→ 独立再确认 |
| **MOPN**（110-67-8） | **0**（无介电分类） | 0 | **0** | **本轮复验**：103 条物性 / 24 个类别里无介电类；三级否定 → Reaxys 侧路线关闭（见 §2.6） |

**一句话**：Reaxys 这一刀**没有翻出任何本地缺失的成品数据**；真正的净产出是**一条真缺口（GVL 本地 0 行）+ 一条新源线索（DME Werblan 1985）+ 一次对本地 sulfolane 温度序列的独立再确认**，外加两条否定性证据（FEC 无 107 腿；VC 无值）。

## 1 Reaxys 的介电数据模型（结构性事实）

Reaxys 把介电数据放在**两个不同的属性类别**下，列集合不同：

| 属性类别 | 列集合 | 频率列 | **方法列** |
| --- | --- | --- | --- |
| `Static Dielectric Constant` | 值 / Temperature (°C) / Location / Comment / Reference | **无** | **无** |
| `Dielectric Constant` | 值 / **Frequency (Hz)** / Temperature (°C) / Location / Comment / Reference | 有 | **无** |

**结论**：Reaxys **从不建模"测量方法"字段**，只有 `Location` / `Comment` 两个自由文本列能偶然承载方法信息。因此"S-4 周四要求的 频率/方法/出处"三件套里，**方法必须回到一手文献**；Reaxys 顶多给频率，且**只有非-static 类别才给**。FEC 的数据恰好落在 Static 类别 → 连频率都给不了。

## 2 逐化合物记录

### 2.1 FEC —— 0 新增，且 107 腿不存在

`Physical Data - 19` 中介电只有 `Static Dielectric Constant - 1`：

| 值 | 温度 (°C) | Location | Comment | Reference |
| --- | --- | --- | --- | --- |
| 78.4 | 23 | *（空）* | *（空）* | Kobayashi et al., *J. Fluorine Chem.* 2003, 120(2), 105-110 |

同页 `Electrical Data - 1` 的内容是 **Electrical conductivity**（同篇），不是介电值。
→ 冻结行 `dielectric=78.4` / `T_K=296.15` 与这条**同源同温**；**Reaxys 侧没有 107 腿**，Hagiyama 2008 的收口**不能指望 Reaxys**。

### 2.2 VC —— 0 新增，出处再确认

`Physical Data - 59` 中介电只有 `Dielectric Constant - 1`，启用全部 6 列后：

| 值 | 频率 (Hz) | 温度 (°C) | Location | Comment | Reference |
| --- | --- | --- | --- | --- | --- |
| *（空）* | *（空）* | *（空）* | *（空）* | *（空）* | Saadi; Lee, *J. Chem. Soc. B* 1966, p. 5 |

文献记录：**No title**，DOI **`10.1039/j29660000005`**，无摘要。
→ 冻结行 `source_doi` **就是这个 DOI** → 溯源**早已闭环**（`evidence_level=primary`，126 ± 1.0 @ 25 °C）。Reaxys 净新增 0。
（检索弯路记录：VC 的 CAS 是 **872-36-6**；用 `872-36-7` 检索会被当纯文本。）

### 2.3 GVL —— 本轮唯一真缺口

本地观测表（`dielectric_observations_v11plus.csv`）里 GVL 是 **0 行**。Reaxys 给出 **1 条**：

| 值 | 频率 (Hz) | 温度 (°C) | Location | Comment | Reference |
| --- | --- | --- | --- | --- | --- |
| **36.9** | *（空）* | *（空）* | **supporting information** | *（空）* | Segato, Jacopo; Baratta, Walter; Belanzoni, Paola; Belpassi, Leonardo; Del Zotto, Alessandro; Zuccaccia, Daniele — *Inorganica Chimica Acta*, 2021, vol. 522 |

→ 与冻结行 **36.1**（`open_access_review_table`，`10.1016/j.isci.2026.115778`）**冲突**，且**两条都没有温度**。`Location = supporting information` 说明 Reaxys 是从该论文的补充材料里抽的。
**待办**：GVL 是 v1.x 温度表的第一优先缺口（本地 0 观测），但 Reaxys 这条只给了一个无温度的点值，**不足以建温度序列**。

### 2.4 DME —— 本地已有温度序列，Reaxys 补一条新源线索

`Dielectric Constant - 7`。其中有值且带条件的条目：

| 值 | 频率 (Hz) | 温度 (°C) | Reference |
| --- | --- | --- | --- |
| 7.2 | *（空）* | *（空）* | Rohani; Horne; Murthy, *Org. Process Res. Dev.* 2005, 9(6), 858-872 |
| *（空）* | *（空）* | *（空）* | Perinu; Arstad; Bouzga; Jens, *J. Phys. Chem. B* 2014, 118(34), 10167-10174 |
| 7.2 | *（空）* | 25 | Schroeder; Hubaud; Vaughey, *Mater. Res. Bull.* 2014, 49(1), 614-617 |
| 7.2 | 10000 | 25 | Kumar et al., *J. Chem. Eng. Data* 1991, 36(4), 467-470 |
| **7 - 9.1** | **1591** | **−30 - 25** | Werblan; Suzdorf; Lin; Szymanski; Lesinski, *Bull. Pol. Acad. Sci. Chem.* 1985, 33(7-8), 285-296 |

其余为**无数值的引用存根**行（Kloepfer 1972、Chastrette 1979、Lumbroso-Bader 1970 …）。
本地 DME 已有 **9 行**温度观测（288.15→338.15 K，两篇 *JCT*）。→ Reaxys 的净贡献是 **Werblan 1985 这条带温度区间的新源线索**（1985 年波兰科学院通报，来源质量待评）。

### 2.5 sulfolane —— 逐点一致，独立再确认

`Dielectric Constant - 12`，其中 **8 条是同一篇的完整温度序列**：

| 值 | 温度 (°C) | 温度 (K) | Reference |
| --- | --- | --- | --- |
| 44.5 | 19.99 | 293.15 | Vahidi, Mehdi; Moshtari, Behnoosh — *Thermochimica Acta*, 2013, vol. 551, p. 1-6 |
| 44 | 24.99 | 298.15 | 同上 |
| 43.4 | 29.99 | 303.15 | 同上 |
| 42.8 | 34.99 | 308.15 | 同上 |
| 42.2 | 39.99 | 313.15 | 同上 |
| 41.6 | 44.99 | 318.15 | 同上 |
| 41.1 | 49.99 | 323.15 | 同上 |
| 40.4 | 54.99 | 328.15 | 同上 |

本地观测表这 8 行**逐点数值完全相同**（同一 DOI `10.1016/j.tca.2012.10.004`）——即这两条独立提取路径互相印证，是本轮**唯一可称"独立再确认"**的结果（校验器已把这条做成硬断言）。
另有 43.4 @ 30 °C（Wu et al., *Small* 2024，Location=Liquid）、43.3（Rohani 2005）、42.13 @ 2 MHz / 20 °C（Laurence et al., *J. Phys. Chem.* 1994, 98(23), 5807-5816）与约 14 行引用存根。

### 2.6 MOPN —— Reaxys 侧确实没有介电分类（三条否定证据：两条独立 + 一条旁证，本轮独立复验）

上一版把 MOPN 记成「手册早前已记，本轮未复验」。本轮用 Edge 登录态**直接复验**，结论与早前一致，而且这次凑齐三条否定证据（其中属性检索卡受空结构槽影响，**只作旁证，不算独立**）：

| 级别 | 操作 | 结果 |
| --- | --- | --- |
| ① 物质记录 | 3-Methoxypropionitrile（CAS **110-67-8**，Reaxys Registry 1739284），Physical Data **103 条** | 点开全部类别（`Load More` ×4 后共 **24 类**，逐项计数）→ **没有任何介电类别**；唯一电学量是 `Electrical Moment - 1` |
| ② 属性检索卡（**旁证**） | Quick search 文本命中后，Reaxys 自动生成的 `Property: dielectric constant` 结果卡 | **0 Substances**（in Reaxys）；**该卡受空结构槽影响，只作旁证，不作唯一依据** |
| ③ 文献层 | `"3-methoxypropionitrile" AND ("dielectric constant" OR "permittivity")` | **112 Documents**；头部命中里真正涉及 3-MPN 的（Shooshtari 2018 *Electrochem. Commun.* 86, 1-5；Shim 2020 *Electrochim. Acta* 337, 135760）**都只把它当电解液溶剂**，介电关键词仅出现在索引词；其余命中是别的材料（BaTiO₃-CoFe₂O₄ 陶瓷、3-溴戊烷、1,3-丁二醇等） |

**MOPN 在 Reaxys 里唯一的电学量**（本轮新抄录）：

| 量 | 值 | 介质 | 出处 |
| --- | --- | --- | --- |
| Dipole moment（`Electrical Moment`，Description=Dipole moment） | **4.04 D** | **dioxane 溶液** | Strobykina, Kataev & Vereshchagin, *Bull. Acad. Sci. USSR Div. Chem. Sci.* **1987**, 36(9), 1965-1966（俄文原刊 *Izv. Akad. Nauk SSSR Ser. Khim.* 1987(9), 2114-2115） |

两条边界必须一起记：这是 **dioxane 溶液**中的偶极矩、**该类别无温度列**，而且**它不是介电常数** —— 不能用来确认 36.0。它的用途是给将来 MOPN 的 xTB 偶极矩特征提供一个外部锚点（MOPN 目前连特征行都没有）。

**判决**：MOPN 的 `model_ready=false` / `conflict_status=awaiting_primary_confirmation` **维持不变**；Reaxys 这条路线在**物质层与属性层已穷尽并关闭**，只剩全文阅读（Reaxys 摘要层读不到 ε）。

**一条必须写清的边界**：Reaxys 结果页会给出厂商自动生成的 SummaryAI 文本（本次它也提示「112 篇上下文无该值」）。那是生成式功能，**不构成证据**；上面的否定结论建立在两条独立证据上：完整类别清单（物质层）与逐条命中标题（文献层）；属性检索计数那张卡受空结构槽影响，**只作旁证**。

## 3 与本地表的对账

| 化合物 | Reaxys | 本地 v11plus | 差额 |
| --- | --- | --- | --- |
| FEC | 78.4 @ 23 °C | 冻结行 78.4 @ 296.15 K | 一致（同源） |
| VC | 无数值 | 126 ± 1.0 @ 25 °C；`source_doi` = 同 DOI | 一致（Reaxys 无值） |
| GVL | 36.9（无 T） | **0 行** | **冲突 + 缺口** |
| DME | 7 条（5 条有值） | 9 行（288.15–338.15 K） | 本地更全；Reaxys 补 1 条新源线索 |
| sulfolane | 8 点序列 | 8 行序列 | **逐点一致** |
| MOPN | **无介电分类** | **0 行** | 无法对账；Reaxys 侧路线关闭（§2.6） |

## 4 仍未闭环

1. **Hagiyama et al. 2008**（`10.1246/cl.2008.210`）—— FEC 107 腿唯一收口项；Reaxys 无记录（本轮新增证据）。
2. **GVL 36.9 vs 36.1** —— 需读 Segato 2021（`Inorg. Chim. Acta` 522，SI）与 iScience 2026 综述表核对；两者均无温度。
3. **DME Werblan 1985**（`Bull. Pol. Acad. Sci. Chem.` 33(7-8), 285-296）—— 来源质量待评，且是区间而非逐值。
4. **MOPN** —— 已于本轮复验并关闭（§2.6）：物质层无介电分类、属性检索 0 条、文献层 112 篇无值。剩余路线只有全文阅读，**不再是 Reaxys 侧待办**。

## 5 复现路径

```
通用：Reaxys > Query builder: [CAS Registry Number is <CAS>] AND [Dielectric Constant]
      > Search in Substances > 结果页 > Physical Data - N > Dielectric Constant - K
      > Show/Hide columns（勾选全部 6 列）> Apply；必要时点 "Show all"
FEC ：Quick search 114435-02-8 > Substances > Physical Data - 19 > Static Dielectric Constant - 1
MOPN：Quick search 3-methoxypropionitrile > Substances > 1 > Physical Data - 103 > Load More ×4（共 24 类）> 逐类查看 > Electrical Moment - 1
```
