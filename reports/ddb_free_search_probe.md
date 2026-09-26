# DDBST 免费层探针：`www.ddbst.com` Online Search 到底给不给 ε(T)

对应 v1.x 数据源表第 6 项（DDB / DDBST，Online Search，标注"部分免费"，用途"纯组分 ε(T) 散点补充，免费额度内当线索用"）。
此前唯一一条 DDBST 审计记录审的是 `https://www.ddbst.com/en/ddbst/No-Data-Policy.php`（访问约束页，不是查询面），
**Online Search 免费层从未被实际探测过**。本报告补上这一刀。

产物：
- `probes/ddb_free_search_probe.py`（探针，含注入式 HTTP 层 + 磁盘响应缓存）
- `probes/ddb_free_search_probe_summary.json`（本轮全部请求、状态、字节数、逐条证据）
- `tests/test_ddb_free_search_probe.py`（36 项，全离线）
- 本报告

---

## 一句话判决

免费层**真实存在、匿名可用、不需要登录**，而且比厂商自己的说法更进一步——它能给出**纯组分 ε(T) 的覆盖元数据**（数据集数、数据点数、温度区间、状态分布），
但**一个 ε 数值都不返回**。因此这条线对 v1.x 的**化合物覆盖净增量 = 0 个可建模化合物**；
它值一条"该去别处找什么"的线索，不值一次取数。手工取值只有一条路：给 `info@ddbst.com` 发邮件索取报价（人工、非机器可读）。

---

## 一、入口与可达性（实测）

| 事实 | 证据 |
|---|---|
| 入口页面 | `https://www.ddbst.com/ddb-search.html` 的 "Start Online DDB Search" 链接 → `http://ddbonline.ddbst.com/DDBSearch/onlineddboverview.exe` |
| DNS | `ddbonline.ddbst.com` → `80.228.13.55` |
| **端口 80** | TCP 连通，0.25 s |
| **端口 443** | 连接超时（8 s 无响应）→ 该应用只有明文 HTTP |
| 应用入口页 | HTTP 200，5,826 字节，`text/html`；抓两次 sha256 相同 `7440e54e451f5238dd943668bb026c7ae2ea91a40b625b1595fa02d786b2c675` |
| 是否要登录/许可 | 无。页面无 login/password/subscription/licence 任何标记（探针内 `has_login_marker` = False） |
| 免费额度 | 免费页面上**没有**任何请求数/令牌额度声明；实测 28 次请求未遇 429 |
| **首连被丢弃** | 本轮 18 次应用请求中 13 次拿到 200（**0.722**），其余靠第二次及以后成功；入口页也是第 2 次才给 200 |

> ⚠️ **本轮最大的操作陷阱**：该主机会丢掉相当比例的首次 TCP 连接。不复试就会把"可达"误判成"不可达"——我自己的第一轮探测正是这样误判的，
> 直到改用重试才拿到 200。探针因此把每次 app 调用都做成可重试，并把"尝试次数 vs 成功次数"单独记账。

## 二、免费层有三个面

1. **`?submit=Search`（默认页）**——组分检索，五个入口：`ddbnumber` / `name` / `casn` / `formula` / `smiles`，POST 到同一个 `.exe`。
   **没有任何物性检索入口**：不能按物性查，只能按组分查。
2. **`?submit=Statistics`**——全库覆盖统计（29 个数据银行 × 5 档系统尺寸）。总盘子：**1,572,707 sets / 11,645,914 points / 112,103 components**，页面自标 "created August 2026"。
3. **`?submit=DDBSystems&databank=<CODE>` 与 `?submit=Details&systemcomplist=<DDB#>`**——按数据银行列系统清单；按组分列**物性级**覆盖表（下面 Q2 的核心证据）。

## 三、四个问题逐条回答

### Q1：Online Search 免费层是否存在、是否匿名可用？

**存在、免费、匿名可用。** 判决 `exists_free_of_charge_anonymous_and_usable_with_retries`。

- 厂商说法两处一致：`online.html`「now allows everybody world-wide to search the content of the Dortmund Data Bank online」；`ddb-search.html` 同义。
- 免费层支持的数据银行清单里**明确列有 `Dielectric constants`**（`extract_supported_banks` 从 `ddb-search.html` 抽出的行）。
- 需要登录：否。需要许可：否。免费额度：未声明。

### Q2：免费层里有没有纯组分 ε(T)？

**有"覆盖元数据"，没有数值。** 判决 `temperature_resolved_coverage_visible_but_no_values_returned`；`permittivity_values_read = 0`，`temperature_values_read = 0`。

厂商自己在两处写死了边界：
- `online.html`：「This DDB online search **does not present any data** but allows sending a mail to DDBST for requesting further information.」
- `ddb-search.html`：「**does not reveal any data** but allows to send a mail to DDBST for requesting further information.」
- `ddb-mdec.html`：「**Pure component dielectric constants have been part of the PCP data bank from its start in 1994**」
- 组分 Details 页顶部：「A quote for experimental literature data about the component can be obtained via email.」

免费**计算器**（`calculation.html`）不是这条路：它只覆盖 5 个物性——蒸气压(Antoine)、液相密度(DIPPR 105)、液相动力黏度(Vogel)、表面张力(DIPPR 106)、汽化焓(PPDS12)；
该页 permittivity/dielectric 出现次数 = **0**。

**但 Details 页确实把 ε(T) 的存在、规模与温区摊开了**（本项目关心的 5 个化合物，全部命中）：

| 化合物 | DDB# | 返回的属性名 | 数据点 | 数据集 | 温度区间 | 状态分布 |
|---|---:|---|---:|---:|---|---|
| acetonitrile | 3 | `Dielectric Constant` | 771 | 115 | **115–623 K** | Liquid 97 / Supercritical 8 / Further States 10 |
| propylene carbonate | 728 | `Dielectric Constant` | 103 | 30 | **195–378 K** | Liquid 29 / Further States 1 |
| dimethyl carbonate | 451 | `Dielectric Constant` | 36 | 6 | **278–353 K** | Liquid 6 |
| water | 174 | `Dielectric Constant` | 1569 | 273 | **67–823 K** | Liquid 250 / Further States 23 |
| ethylene carbonate | 1713 | `Dielectric Constant` | 17 | 10 | **298–343 K** | Liquid 9 / Solid 1 |

（DDB# 与 CAS 自洽：acetonitrile 75-05-8、PC 108-32-7、DMC 616-38-6、water 7732-18-5。单位方面：温度区间单位为 K，数据点只给计数、不给逐个温度值与 ε 值。）

介电数据银行 **MDEC**（Mixture Dielectric Constants）的覆盖规模：

| 系统尺寸 | Sets | Points | 计数单位 |
|---|---:|---:|---|
| 纯组分 | 263 | 2,244 | 50 components |
| 二元 | 10,544 | 90,598 | 3,881 systems |
| 三元 | 735 | 6,145 | 341 systems |
| 四元 | 6 | 46 | 4 systems |
| 更高元 | 27 | 138 | 21 systems |
| **合计** | **11,575** | **99,171** | 4,297 systems |

**内部一致性校验**：系统清单页（`DDBSystems&databank=MDEC`）解析出的纯组分块恰好 **50 行**，其 sets/points 逐项求和 = **263 / 2,244**，与统计页纯组分列**逐位相同**；
各档系统行数 50+3881+341+4+4+17 = **4,297**，与页面头「4297 systems with 11575 data set/s and 99171 data point/s found」一致。→ 解析器没有错位。

> 结论措辞：厂商"不透露任何数据"这句话在**数值**这一层是准确的；免费层实际给的是**覆盖元数据**。把覆盖计数当成 ε 数据用，就是把它算成"可得数据"——本报告不这么算。

### Q3：能否机器读取？

**不能。** 判决 `html_tables_only_no_export_endpoint`。

- 免费页面上**没有任何 CSV/JSON 导出链接**（`find_export_links` 结果为空；注意站点导航里的 `export-compliance.html` 是合规声明，不是导出——探针专门为此加了误报测试）。
- 数据面是**服务端渲染的 HTML 表格**，跑在一个 Windows 可执行端点（`.exe`）上，无文档化 API。
- 但是 **URL 稳定、可脚本化**：

| 用途 | URL |
|---|---|
| 组分检索 | `.../onlineddboverview.exe?submit=Search&name=<name>` |
| 组分物性覆盖 | `.../onlineddboverview.exe?submit=Details&systemcomplist=<DDB#>` |
| 全库统计 | `.../onlineddboverview.exe?submit=Statistics` |
| 数据银行系统清单 | `.../onlineddboverview.exe?submit=DDBSystems&databank=<CODE>` |

- 唯一取值路径：发邮件索取报价（厂商明示）。
- **解析陷阱（都已写进测试）**：
  1. 每行**第一个 `<td>` 从未闭合**（`<td class="cellformat">1<td ...`），按 `</td>` 切分会让所有列错位；
  2. 检索结果行是等宽列 + `&nbsp;` 填充，按单空格切分会把无 CAS 的多词名拆成 `formula=Tap / name=water`——于是 `Water`、`Tap water`、`River water`、`Mineral water`、`Formation water` 全部塌缩成同名 `water`，精确匹配被迫放弃。**这是我第一轮 water 查不到的真正原因**；
  3. Statistics 页有一张重复全部银行代码的图例表，朴素遍历会把每个银行读两遍，且第一遍没有数字；
  4. 二元及以上系统把每个组分的 DDB# 用 `<br />` 连在一格（`1<br />31`），`str.isdigit()` 会把所有二元/三元行整批丢掉。

### Q4：对 v1.x 的化合物覆盖有没有净增量？

**净增量 = 0 个可建模化合物。** 判决 `coverage_metadata_only_name_level_candidates`。

- 5 个目标化合物全部**有**可见的 ε(T) 覆盖，但读到的 ε 数值 = 0 个、温度值 = 0 个。
- MDEC 纯组分共 **50 个**，全部只有计数没有数值。与冻结 246 名录做**名称级**比对：
  - 严格同名（大小写/标点无关）命中 **13** 个；
  - 位标顺序宽容归一（字符多重集）再命中 **4** 个：`2-Butanol↔butan-2-ol`、`1-Butanol↔butan-1-ol`、`2-Propanol↔propan-2-ol`、`1-Propanol↔propan-1-ol`；
  - 残余 **33** 条只是**名称级线索，未核验**，且其中相当一部分明显不是 v1.x 目标（`Corn oil` / `Kerosene` / `Gasoline` / `nylon 6` / `Honey` / `polydimethylsiloxane` 等油脂燃料聚合物），另有 8 个咪唑类 IL 盐（v1.0 只把 IL 作为边界化合物标注）。
- 明确记录的残余风险：本比对**只做了名称**，没有 CAS/SMILES/结构层对账。像 `tert-Butanol` 与名录里的 `2-Methyl-2-butanol` 是同一物但名称形态不同，宽容归一仍会漏配——**所以那 33 条既不能当新增，也不能当不存在**。
- 附带发现：`1,2-Dimethoxyethane`（乙二醇二甲醚，glyme 系）在名录内且 DDB 有 ε 覆盖；名录外的 `Nitromethane`、三个乳酸酯在 DDB 有 ε 覆盖，可作为"值得去别处找"的线索。

---

## 四、这条线值不值得继续

**不值得为取值继续，值得当作"覆盖度校验器"保留。** 一句话：DDB 免费层能告诉你"某化合物有没有 ε(T)、大概多少个点、跨多宽温区"，但永远不给你数字；
它必须用 DDBST 自己的系统清单/Details 页当查询入口，且入口主机约三成首连会被丢弃、需要重试。

给 v1.x 的具体用法（不新增主线）：
1. 把它当**优先级排序器**：要补某个缺失电池溶剂的 ε(T) 时，先查 DDB Details 看温区与点数，判断"值不值得去追一手文献"；
2. **不要**把它写进任何观测表——它没有观测值；
3. 若确需数值，唯一合规路径是 `info@ddbst.com` 邮件索取报价（人工、非机器可读、不属免费层）。

---

## 五、礼貌抓取与预算（如实披露）

- 全部请求 `User-Agent` 声明研究用途；**每次 HTTP 调用间隔 ≥1 s**；无并发；只对"连接被丢弃"做重试，不做重试风暴。
- **本轮规范运行**：28 次请求（预算上限 60），状态分布 `{200: 19, 404: 4, 连接被丢弃: 5}`，共 3,700,842 字节。5 次丢弃全部由重试补齐（`phases_completed` 显示 5/5 营销页、5/5 组分检索、5/5 Details、统计页与介电银行清单均拿到内容）。
- **超预算披露（必须说明）**：本任务全程（侦察探索 + 因"可达性发现"而必须重跑的若干轮）合计约 **200 次 HTTP 尝试**，明显超出 60 的上限。原因是探测方案在过程中被实测推翻：
  计划里 DDB 只是一页静态查询面，实测发现它是一台**会丢首连的交互式应用**，且免费层结构（Statistics / DDBSystems / Details）是侦察阶段才发现的，
  于是必须补跑才能回答 Q2/Q4；期间还修掉了 4 个会把结论带偏的解析缺陷。缓解措施：中途给探针加了**磁盘响应缓存**（成功响应落盘，重跑只补缺口），
  后续轮次从 29 次请求降到 4 次。此后已停止全部网络活动。
- 未做任何绕过登录、绕过付费墙、抓取授权数据的行为。

## 六、未确认的疑点

- **443 超时未归因**：可能是服务端只监听 80，也可能是本机/中间设备策略；两者无法从外部区分。
- **首连丢弃机制未归因**：只量化了结果（0.722 首次成功率），没有定位是 SYN 丢弃、CDN，还是站点侧限流。
- **免费层的速率/额度上限未知**：免费页面无声明，实测 28 次无 429；不能推断"无限"。
- **快照新鲜度未知**：Statistics 页自标 "created August 2026"，但免费层不暴露上次更新时间，无法核对 2019 年后新增情况（这一项本属 ThermoML 线，不在本次范围）。
- **"Other Mixtures" 一档语义未核实**：MDEC 各档系统行数与页面头的 4,297 一致，但该档（17 行）具体指哪些多组分体系没有进一步展开。

## 七、复现

```powershell
# 实网（默认预算 60，每次调用间隔 ≥1 s；--cache-dir 让重跑只补缺口）
.\.venv\Scripts\python.exe probes\ddb_free_search_probe.py --sleep 1.0 --cache-dir "$env:TEMP\ddb_cache"

# 零请求自检
.\.venv\Scripts\python.exe probes\ddb_free_search_probe.py --offline

# 离线测试（注入式 HTTP + tmp_path，零联网）
.\.venv\Scripts\python.exe -m pytest tests\test_ddb_free_search_probe.py -q
```