# W17-16：Reaxys 库存队列（v1.x）P2 层逐条实查

**一句话**：把 `probes/reaxys_v1x_stocking_queue.csv` 里 P2 层、且本仓任何 Reaxys 车道都还没读过的
19 个物质，一张卡一张卡地在作者已登录的 Edge Reaxys 会话里读过一遍；四个通道全部只交付**计数**，
Reaxys 数值不进 `data/`、不进任何池、不进任何特征表。

## 1. 范围与目标集

| 项 | 值 |
|---|---|
| 队列 | `probes/reaxys_v1x_stocking_queue.csv`，sha256 `a4ecdab027187475b4d32aefc87dbce9e3821b656562013e6ec7e796c34e33d3` |
| P2 行数 | 22 |
| 已被早前车道读过 | 3（W17-13：`DTQVDTLACAAQTR` 三氟乙酸；W17-15：`GAEKPEKOJKCEMS` GVL、`JBTWLSYIZRCDFO` EMC） |
| **从未读过 = 本车道目标** | **19** |
| 简报 | 逐字列出 19 个键，措辞为「共 20 个」 |
| 查询提交次数 | **21**（预算 30）——19 个物质各一次，外加 2 次重复提交 |

**计数口径的唯一解**：队列自带的 `probed_in_this_round` 列**已过期**——它对上面那 3 个 P2 行仍写着
`no`。所以目标集不是从该列算出来的，而是从早前两条车道自己的事实表
（`reaxys_thin_family_query_facts.csv` / `..._b2_facts.csv`）反推：22 − 3 = **19**，
恰好等于简报逐字列出的那 19 个键。简报里的「20」是 off-by-one，名单本身是对的。

**查询次数如实计 21**：19 次是 19 个物质各一次；另外 2 次是重复提交——氟苯的首次快速检索是学习卡片
布局时手工做的，间氟甲苯的首次走卡因沙箱报错中断后重跑了一次。两次都是对已在目标集内的物质重复提交，
没有读取两次的卡片。

## 2. 逐通道结果（口径严格三分，不混用）

通道定义：ε = `Dielectric Constant` + `Static Dielectric Constant`；η = `Dynamic Viscosity` +
`Kinematic Viscosity`；轨道 = `Ionization Potential` + `Quantum Chemical Calculations`（卡上有时标
`Calculated Properties`）；氧化还原 = **只** `Electrochemical Characteristics`
（`Electrochemical Behaviour` 有意排除）。

`rows` = 分类表全部行数；`valued` = **数值列**非空（含区间）；`point` = **数值列**整格可解析为单个浮点；
`comment` = 数值列为空、但 `Comment` 列里含数字的行数（单独一支，不并入 `valued`）。

| 通道 | rows | valued | point | comment 列来源 | 有行的物质 | 有点值的物质 | 分类表数 |
|---|---|---|---|---|---|---|---|
| ε 介电 | 98 | 70 | 53 | 2 | 13 | 13 | 18 |
| η 黏度 | 144 | 130 | 90 | 10 | 14 | 10 | 18 |
| 轨道（IP + 量化计算） | 70 | 30 | 30 | 0 | 15 | 7 | 22 |
| 氧化还原 | 27 | 0 | 0 | **13** | 7 | 0 | 7 |

证据体量：19 份物质卡 JSON、66 张分类表、去重后 340 行、共 572,032 字节，全部落在
`data/raw/reaxys_w17d/`（被 `data/raw/*` 忽略，本机保留）。

单物质最富的几张：乙醚 ε 45 行 / η 29 行；四氢呋喃 η 29 行 / ε 11 行；氟苯 IP 23 行；异丙醚 ε 11 行；
α,α,α-三氟甲苯氧化还原 12 行。

## 3. 本批两条最重要的新发现

1. **`Electrochemical Characteristics` 在本批根本没有数值列。** 它的表头是
   `Description / Solvent / pH-Value / Temperature / Location / Comment / Product XRN / Product /
   Reference`——没有一列是电位。27 行里有 **13 行**的电位只以字符串形式写在 `Comment` 里
   （如 `-2.57 V`、`> 3.2 V`、`2.24 V`、`Half-peak potential`）。任何只读数值列的下游读者，
   在这 7 个物质上会看到 **0** 个氧化还原值。前两批只在 η 和单个 redox 行上踩过 Comment 坑，
   本批是首次确认「该分类整体没有数值列」。
2. **队列的 `probed_in_this_round` 列不可信**（见 §1）。它把 3 个已读行仍标成未读；若直接拿它筛
   「从未实查」，目标集会虚高到 22，且会把 W17-13/W17-15 的工作重复一遍。目标集必须从各车道的
   事实表计算。

附带的两个口径陷阱（已按定义排除，记录备查）：

- **`Bulk Viscosity` 不能算 η。** 乙醚卡上同时有 `Bulk Viscosity - 1` 和 `Dynamic Viscosity - 29`；
  用 `/viscosity/` 子串匹配会把 Bulk 混进 η。通道定义只认 Dynamic + Kinematic，本批 η = 29（仅 Dynamic）。
- **介电列把频率标注的 ε 与静态 ε 混在同一列**（如氟苯 5.55 @ 2E+06 Hz @ 20 °C），与 W17-RX
  crosscheck 的 caveat 一致；本车道按 Reaxys 原样记录，不做拆分。

轨道通道的结论与前两批一致、未被本批改写：70 行里 30 行是**有数值的 IP**（集中在 7 个物质），
另外 26 行 `Calculated Properties` **全是文字标签**（例如 `Molecular orbitals, Electronic energy
levels`），没有一个是 HOMO、LUMO 或 gap 的数值。**Reaxys 依然不提供可用的 HOMO/LUMO 数字。**

另有两个 P2 物质（`CWIFAKBLLXGZIC`、`HLLCNVLEVVFTJB`）卡上**四个通道一个都没有**——不是漏采：
已核对它们的完整分类清单，确实不存在 Dielectric/Viscosity/Ionization/Electrochemical/Calculated
任何一类。

## 4. 边界与限制

- **单位照 Reaxys 自报原样保留**，不修不换算：η 的数值列是 poise（`Dynamic Viscosity, P`）、
  运动黏度是 stokes（`Kinematic Viscosity, St`）、轨道是 eV。
- 本车道按合规要求**只交付计数**，因此事实表不含温度列；摄氏温度原样留在原始卡片证据里，
  **未做任何换算、未取中值、未补 298.15 K**。
- 氧化还原通道 `valued = point = 0` 是**定义使然**（该分类没有数值列），不代表 Reaxys 没有数据：
  数字在 13/27 行的 `Comment` 里。
- `Dielectric Constant` 的 45 行（乙醚）里含频率标注点，与静态点同列；本车道只计数，不做语义拆分。
- 一次一张物质卡、每个分类表用其自身的 `Show all` 展开到 Reaxys 自报行数；事实表为此设了硬断言
  （读到的行数必须等于按钮上的自报数），全部 66 张表均相等。
- 会话恢复过程记录在摘要的 `session.recovery_note`：当天的 Reaxys 会话 cookie 已过期，机构 SSO 在
  Edge 里被本机失效的系统代理（`127.0.0.1:10809`）挡住；为 `whu.edu.cn` 加了一条**临时**代理绕过，
  Edge 配置里既有的武大会话随后自行完成认证，**绕过在取数结束后已还原**（已核对与原快照一致）。
  未复制 profile、未重新登录、未无头爬取。会话失效当时的登录墙截图存为
  data/raw/reaxys_w17d/blocked_institution_signin.png（同样被 git 忽略）。

## 5. 合规声明（裁决 B）

- Reaxys 派生**数值不进 `data/`**：本车道只在 `probes/`、`reports/`、`tests/` 下写文件；带数值的细节
  只在被忽略的 `data/raw/reaxys_w17d/`。
- 事实表 `carries_reaxys_values = false`，且**不含任何 Reaxys 数值**，只有计数。
- `models_fitted = 0`、`r2_reported = false`、`main_scoreboard_touched = false`；
  主记分牌 `0.4091179943351143` 未被触碰；`data/` 下被 git 跟踪的文件**零改动**。

## 6. 产物

| 文件 | 说明 |
|---|---|
| `probes/reaxys_v1x_stocking_query.py` | 构建器，`--overwrite` / `--check`（`--check` 已通过） |
| `probes/reaxys_v1x_stocking_query_facts.csv` | 19 行 × 30 列，sha256 `0a13fed97e6c5f19b3a57d60f1bcdd2a1a5309cbfefd79564c394ba1a6d1f40f` |
| `probes/reaxys_v1x_stocking_query_summary.json` | 车道摘要、通道合计、键审计、合规块 |
| `tests/test_reaxys_v1x_stocking_query.py` | 14 项测试全绿（含从原始卡片重算全部计数） |
| `reports/reaxys_v1x_stocking_query.md` | 本文件 |
| `data/raw/reaxys_w17d/` | 原始页证据（git 忽略，本机保留） |