# Reaxys 渲染缺口闭合（propylene carbonate 与 tetraglyme 的「Show all」复验）

**日期**：2026-09-26
**浏览器**：Edge（用户已登录的 Reaxys 会话）
**方法事实**：Reaxys 网页端（用户已登录的 Edge 会话）**手动逐条查询**；未使用批量爬虫、未批量导出、未自动遍历。构建本产物的过程**零网络访问**。受限值口径见 `restricted_values_contract`：受限 Reaxys 数值**已镜像在本产物的 CSV 与 summary 内**，**禁止再分发**，**不得并入数据集或候选池**，本产物**不声明任何通道可用**。
**产物**：`probes/reaxys_render_gap_closure.csv`（18 行 = PC 10 + tetraglyme 8）、`probes/reaxys_render_gap_closure_summary.json`、`probes/verify_reaxys_render_gap_closure.py`、`tests/test_reaxys_render_gap_closure.py`

## 0 一句话

上一轮把「Reaxys 声明 N 条、表里只渲染 M 条（PC 10/7、tetraglyme 8/7）」登记为「未读到的行未闭合」；本轮发现根因是属性表上方的 **`Show all`** 控件——**「声明数 > 渲染数」是 UI 折叠现象，不是数据缺失**。点击后 PC 10 行、tetraglyme 8 行全部读到：PC 新读到第 8/9/10 行（64 @ 30 °C / 64.4 @ 25 °C / 无数值存根），tetraglyme 新读到第 8 行（**无数值存根**）。上一轮对 tetraglyme 缺行「疑为 39.99 °C = 313.14 K」的猜测被本轮**证伪**。

## 1 上一轮登记 → 本轮判决

| 上一轮登记（逐字） | 来源 | 本轮证据 | 判决 |
| --- | --- | --- | --- |
| tetraglyme 侧 Reaxys 声明 Dielectric Constant - 8 hits out of 8，但表内只渲染 7 行；缺失的那一条（疑为 39.99 C = 313.14 K）本轮未读到，属未闭合项。 | `probes/reaxys_v1x_stocking_scan_summary.json#open_items[0]` | 点 `Show all` 后第 8 行出现：**六列全空、无数值**，题录是 Ugelstad 1965 + Graczyk 1978 合并存根 | **封闭 + 猜测证伪**：缺行不是温度点 |
| PC 侧 Reaxys 声明 Dielectric Constant 10 hits，但表内只渲染 7 行（差 3 行）；未读到的 3 行本轮未闭合。 | `probes/reaxys_v1x_stocking_scan_summary.json#open_items[3]` | 点 `Show all` 后 10 行全出，第 8/9/10 行已逐字转录 | **封闭** |
| EC 的 5.4 @ 25 C 条目与同物质其余三条差一个数量级，未判定归属，只登记为可疑条目。 | `#open_items[1]` | 本轮未触及 | **仍未闭合** |
| PC 的 20 C / 35 C 两点在 2 MHz，能否进 v1.x 观测表取决于频率口径，本产物不作入库判断。 | `#open_items[2]` | 本轮扩到 4 点，但频率口径问题不变 | **仍未闭合** |
| EC / PC 在**观测表**里是 0 行（observation_table_distinct_T = 0），人工转录的 1 个温度点取自 **v03 冻结表**冠军行 —— 两个计数口径不同，不可混用。 | `#open_items[4]` | 本轮实测确认 PC 观测表 0 行（§4.2） | **仍未闭合**（事实已被再确认） |
| 1,1,2,2-tetrafluoroethyl 2,2,2-trifluoroethyl ether（TTE）在 Reaxys 与本地都只有单点，缺口未闭合。 | `#open_items[5]` | 本轮未触及 | **仍未闭合** |

## 2 UI 发现：`Show all` 控件是根因

Reaxys 的属性表（结果页 `Physical Data > Dielectric Constant`）默认**只渲染前 M 行**，表上方另有一个 **`Show all`** 按钮；点击后全部 N 行才出现。

| 查询 | 声明数 N | Show all 前渲染 M | Show all 后渲染 | 新读到的行 |
| --- | ---: | ---: | ---: | --- |
| propylene carbonate（108-32-7, Reaxys Registry 107913） | 10 | 7 | 10 | 第 8、9、10 行 |
| tetraethylene glycol dimethyl ether（143-24-8, Reaxys Registry 1760005） | 8 | 7 | 8 | 第 8 行 |

**边界**：这条控件解释的是「声明 > 渲染」这一类现象，**不能**推广去解释别的差异。EC（声明 4 / 渲染 4）与 MOPN（物质层无介电类别）不受它影响，属另一类事实。

## 3 逐化合物全表转录

### 3.1 propylene carbonate（PC）

分类 `Dielectric Constant`，声明 10 条，`Show all` 后 10 行全出（列：值 | Frequency Hz | Temperature °C | Location | Comment | Reference）：

| # | 值 | 频率 (Hz) | 温度 (°C) | Location | Comment | Reference |
| ---: | ---: | --- | ---: | --- | --- | --- |
| 1 | 64.9 | | 25 | | | Segura-Ramirez, Yutzil; Solé-Daura, Albert; Maria, Gomez-Mingot; Fontecave, Marc; Sánchez-Sánchez, Carlos M. — *ChemSusChem*, 2026, vol. 19, #6, art. no. e202502570 |
| 2 | 64.92 | | | supporting information | | Xu, Caili; Zhang, Ming; Li, Pengyu; Chen, Cheng; Zhou, Haiping; Zhang, Shu; Wu, Mengqiang — *Chinese Chemical Letters*, 2026, vol. 37, #8, art. no. 111263 |
| 3 | 64 | | | supporting information | | Segato, Jacopo; Baratta, Walter; Belanzoni, Paola; Belpassi, Leonardo; Del Zotto, Alessandro; Zuccaccia, Daniele — *Inorganica Chimica Acta*, 2021, vol. 522 |
| 4 | 69 | | 25 | | Liquid | Sun, Yihan; Huang, Jinxia; Guo, Zhiguang — *Chemical Communications*, 2019, vol. 55, #92, p. 13876-13879 |
| 5 | 64.92 | | 25 | | | Schroeder; Hubaud; Vaughey — *Materials Research Bulletin*, 2014, vol. 49, #1, p. 614-617 |
| 6 | 62.93 | 2E+06 | 20 | | | Laurence, Christian; Nicolet, Pierre; Dalati, M. Tawfik; Abboud, Jose-Luis M.; Notario, Rafael — *Journal of Physical Chemistry*, 1994, vol. 98, #23, p. 5807-5816 |
| 7 | 63.41 | 2E+06 | 35 | | | Ritzoulis, George — *Canadian Journal of Chemistry*, 1989, vol. 67, p. 1105-1108 |
| **8** | **64** | **2E+06** | **30** | | | Ritzoulis, George — *Canadian Journal of Chemistry*, 1989, vol. 67, p. 1105-1108 |
| **9** | **64.4** | **2E+06** | **25** | | | Ritzoulis, George — *Canadian Journal of Chemistry*, 1989, vol. 67, p. 1105-1108 |
| **10** | *（空）* | *（空）* | *（空）* | *（空）* | *（空）* | Maquestian et al. — *Bulletin des Sociétés Chimiques Belges*, 1971, vol. 80, p. 17,22; Gutmann; Schmid — *Monatshefte für Chemie*, 1969, vol. 100, p. 2113,2118 |

粗体 8/9/10 行是本轮新读到的。第 10 行**六列全空**，是两条题录合并在同一存根里的**无数值引用存根**。

### 3.2 tetraethylene glycol dimethyl ether（tetraglyme）

分类 `Dielectric Constant`，声明 8 条，`Show all` 后 8 行全出：

| # | 值 | 频率 (Hz) | 温度 (°C) | Location | Comment | Reference |
| ---: | ---: | --- | ---: | --- | --- | --- |
| 1 | 8.03 | 1E+06 | 14.99 | | temperature dependence | Rivas; Iglesias; Pereira; Banerji — *Journal of Chemical Thermodynamics*, 2006, vol. 38, #3, p. 245-256 |
| 2 | 7.9 | 1E+06 | 19.99 | | | 同上 |
| 3 | 7.79 | 1E+06 | 24.99 | | | 同上 |
| 4 | 7.67 | 1E+06 | 29.99 | | | 同上 |
| 5 | 7.55 | 1E+06 | 34.99 | | | 同上 |
| 6 | 7.31 | 1E+06 | 44.99 | | | 同上 |
| 7 | 7.07 | 1E+06 | 54.99 | | | 同上 |
| **8** | *（空）* | *（空）* | *（空）* | *（空）* | *（空）* | Ugelstad et al. — *Acta Chemica Scandinavica (1947)*, 1965, vol. 19, p. 208,214; Graczyk et al. — *Journal of the American Chemical Society*, 1978, vol. 100, p. 7333,7338 |

第 2–7 行在 Reaxys 表内与第 1 行**共用同一题录块**，转录原文记作「同上」；CSV 里为了每行自洽，把这 7 行的 `reference` 写成了完整题录，并在 `note` 里注明「同一题录块」。

**证伪记录**：上一轮把 tetraglyme 缺的那一条猜测为「疑为 **39.99 °C** = 313.14 K」；本轮 `Show all` 后第 8 行是 Ugelstad 1965 + Graczyk 1978 的**无数值引用存根**，**不是 39.99 °C 温度点**。该猜测**被证伪**，不得再被当作事实引用。

## 4 v1.x 判读

### 4.1 PC 在 2 MHz 上的 ε(T) 序列只是线索，不是数据

新读到的第 8/9 行（Ritzoulis 1989）与上一轮第 7 行同属一篇，合起来是 **2 MHz** 上 **25 / 30 / 35 °C** 三点；配上第 6 行 Laurence 1994 的 **20 °C**，PC 在 2 MHz 上构成一条 **20 / 25 / 30 / 35 °C 的 ε(T) 序列**（62.93 / 64.4 / 64 / 63.41）。

三条边界必须一起记，所以**这是线索不是数据**：

1. **受限**：取值口径 `restricted_crosscheck_only`，**禁止再分发**、**不得并入数据集或候选池**；
2. **只到题录一级**：Reaxys 只给作者/刊名/卷/页/年，**不给 DOI**，provenance 写不到原始 DOI；
3. **频率腿是 2 MHz**：不是静态介电口径，能否进 v1.x 观测表取决于频率口径（这条同时也是上一轮 `#open_items[2]` 的延续）。

→ 要用这条序列，**必须回到 Laurence 1994（*J. Phys. Chem.* 98(23), 5807-5816）与 Ritzoulis 1989（*Can. J. Chem.* 67, 1105-1108）一手核实**，而不是引用 Reaxys 的二手渲染。

### 4.2 本地 PC 的 ε 观测行数 = 0（实测，不是照抄）

直接读 `data/processed/dielectric_observations_v11plus.csv`（共 2065 行）实测：

| 检索条件 | 命中行数 |
| --- | ---: |
| `name` 含 `propylene carbonate`（不区分大小写） | **0** |
| `inchikey == RUOJZAUFBMNUDX-UHFFFAOYSA-N` | **0** |
| 两条件取并集 | **0** |

（表内 `carbonate` 类只有 diethyl carbonate 与 dimethyl carbonate 两个物质，共 10 行；PC 不在其中。）所以 PC 在**观测表**里确实是**真缺口**，这正是 v1.x 温度表的第一优先项；但它的填法**不是**照抄 Reaxys，而是按 §4.1 回到一手文献。

### 4.3 tetraglyme 本地 6 行 / 5 个 T（实测）

同一张观测表实测：`inchikey == ZUHZGEOKBKGPSW-UHFFFAOYSA-N`（登记名 `2,5,8,11,14-pentaoxapentadecane`）共 **6 行 / 5 个不同 T_K**（288.15 / 293.15 / 298.15 / 303.15 / 308.15 K），来源 DOI 为 `10.1016/j.jct.2010.09.008` 与 `10.1016/j.tca.2012.10.024`——**两个源都不是 Reaxys 侧的 Rivas 2006**。Reaxys 的 Rivas 2006 是 1 MHz 序列，在 288–308 K 与本地窗口重合，而它多出的 318.14 / 328.14 K 两点超出本地窗口；但同样受 §4.1 的三条边界约束，**只作 v1.x 扫漏线索**。

## 5 未闭合项

- EC 的 5.4 @ 25 °C 条目与同物质其余三条差一个数量级，归属未判（延续 `#open_items[1]`）。
- PC 的 2 MHz 序列能否进 v1.x 观测表取决于频率口径，本产物不作入库判断（延续 `#open_items[2]`，本轮已扩到 4 点）。
- EC / PC 在观测表里是 0 行，与「冻结表冠军行有 1 个温度点」是两个计数口径，不可混用（延续 `#open_items[4]`）。
- TTE 在 Reaxys 与本地都只有单点，缺口未闭合（延续 `#open_items[5]`）。
- 本轮只复验了两个物质，**不能**据此断言其它化合物的属性表也会折叠。

## 6 复现路径

```
PC        ：Reaxys 结果页 > Physical Data > Dielectric Constant - 10 > 点表上方「Show all」> 10 行全出
tetraglyme：Reaxys 结果页 > Physical Data > Dielectric Constant - 8  > 点表上方「Show all」> 8 行全出
离线核对  ：.venv/Scripts/python.exe probes/verify_reaxys_render_gap_closure.py
```
