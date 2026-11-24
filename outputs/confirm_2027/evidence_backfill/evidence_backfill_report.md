# B03 A18 证据回填报告
> 生成器 `build_b03_report/1.0.0` · 2026-11-24T02:22:33Z
> 本报告由产物机械生成，不手写，避免与数据漂移。

## 一、结论
- A18 分子：**18**
- 已有可用条件级证据：**5**（DMC, DEC, SL, EA, MA）
- 仍未解决：**13**
- 条件合格（待审）记录：**2**
- 证明非独立的文档对：**9**

**账目闭合：** 5 + 13 = 18 / 18 ✅

### ⚠️ 必须澄清：本轮没有新增任何观测
EA 与 MA 的 ε 值（6.02 / 6.68）**早已存在于 `dielectric_v04.csv`** （`dataset_origin = v0.2`，`source_doi = 10.6028/nbs.circ.514`）。B03 做的是**核实**这两条既有记录确实可由 NBS514 页面读取复现，**不是新增了两条测量**。

正确表述：

- ✅ 「EA/MA 的既有值已通过页面级核实」
- ❌ 「B03 回填了 2 条新测量」—— 这是错的

**证据基数的真实变化是 0 条新观测。** 任何把 `condition_qualified_measurements.csv` 的 2 行当作样本量增长的解读都是错误的。

## 二、PLAN B B03 分层执行情况
| Tier | 分子 | 数量 | 状态 |
|---|---|---|---:|
| P0 | DMC, DEC, SL | 3 | 已解决 3/3 |
| P1 | DME, TEGDME, GBL, DMSO | 4 | 已解决 0/4 |
| P2 | SN | 1 | 已解决 0/1 |
| P3 | AN | 1 | 已解决 0/1 |
| P4 | EA, MA, EMC, EC, PC, FEC, VC, DOL, TMP | 9 | 已解决 2/9 |

## 三、NBS514 核实（PLAN B 指定 EA/MA 优先核查）
| 分子 | 核实状态 | v04 ε | NBS514 ε | 一致 | 页面定位 |
|---|---|---:|---:|---|---|
| DOL | `NO_NBS514_COVERAGE` |  |  |  |  |
| EA | `VERIFIED_AGAINST_PAGE_READ` | 6.02 | 6.02 | true | nbs514:p20:022 (page 20, section C. ORGA |
| EC | `NO_NBS514_COVERAGE` |  |  |  |  |
| EMC | `NO_NBS514_COVERAGE` |  |  |  |  |
| FEC | `NO_NBS514_COVERAGE` |  |  |  |  |
| MA | `VERIFIED_AGAINST_PAGE_READ` | 6.68 | 6.68 | true | nbs514:p18:009 (page 18, section C. ORGA |
| PC | `NO_NBS514_COVERAGE` |  |  |  |  |
| TMP | `NO_NBS514_COVERAGE` |  |  |  |  |
| VC | `NO_NBS514_COVERAGE` |  |  |  |  |

### ⚠️ 这是**转录完整性检查**，不是独立佐证

`data/dielectric_v04.csv` 中 EA/MA 两行的 `source_doi` 就是 `10.6028/nbs.circ.514`，`source_record_id` 分别是 `nbs514:p20:022`（EA）与 `nbs514:p18:009`（MA）—— **与本次页面读取完全相同**。

因此 `epsilon_agrees=true` 证明的是「转录忠实」，**不是**「两个独立来源相互印证」。把这一步称为「PLAN B 的假设成立 / 独立核实」会高估证据强度。

EA 与 MA 仍然各自是 **SINGLE_SOURCE**。

**其余 7 个 P4 分子在 NBS514 中无覆盖：** DOL, EC, EMC, FEC, PC, TMP, VC。

**但这不是「无数据」。** 这 9 个分子在 `dielectric_v04.csv` 中**全部都有整理值**（见 §二 的 `v04_curated_value_present` 列）；它们只是不在 ThermoML 观测层。而且 EC/PC/FEC/VC 是 1951 年之后才商业化的溶剂，要求它们出现在 NBS514 里是同义反复。

### 为什么这 2 条不进 measurement_ledger
账本的不变量是「每条测量可追溯到带 sha256 的源文件」。NBS514 转录没有 ThermoML 源文件，强行加入会让该不变量失效，并使已报告的 2065 计数发生未声明的变化。因此页面读取作为**条件级证据**单独交付，由四智能体审核决定是否使用。

## 四、未解决分子
| 分子 | Tier | 原因 | 观测数 | 下一步 |
|---|---|---|---:|---|
| DME | P1 | `NO_CONDITION_VALID_PAIR` | 9 | 有室温观测但 (T,ε) 不来自同一次测量; 需按 measurement_id 逐条取用 |
| TEGDME | P1 | `NO_CONDITION_VALID_PAIR` | 6 | 有室温观测但 (T,ε) 不来自同一次测量; 需按 measurement_id 逐条取用 |
| GBL | P1 | `NO_CONDITION_VALID_PAIR` | 5 | 有室温观测但 (T,ε) 不来自同一次测量; 需按 measurement_id 逐条取用 |
| DMSO | P1 | `NO_CONDITION_VALID_PAIR` | 105 | 有室温观测但 (T,ε) 不来自同一次测量; 需按 measurement_id 逐条取用 |
| SN | P2 | `NO_ROOM_BAND_OBSERVATION` | 17 | 寻找 293.15-303.15 K 的真实测量; 不得折算高温数据 |
| AN | P3 | `NO_CONDITION_VALID_PAIR` | 10 | 有室温观测但 (T,ε) 不来自同一次测量; 需按 measurement_id 逐条取用 |
| EMC | P4 | `NO_OBSERVATION_AND_NO_PAGE_READ` | 0 | 检索原始文献/公开数据库; 该分子在 ThermoML 与 NBS514 中均无覆盖 |
| EC | P4 | `NO_OBSERVATION_AND_NO_PAGE_READ` | 0 | 检索原始文献/公开数据库; 该分子在 ThermoML 与 NBS514 中均无覆盖 |
| PC | P4 | `NO_OBSERVATION_AND_NO_PAGE_READ` | 0 | 检索原始文献/公开数据库; 该分子在 ThermoML 与 NBS514 中均无覆盖 |
| FEC | P4 | `NO_OBSERVATION_AND_NO_PAGE_READ` | 0 | 检索原始文献/公开数据库; 该分子在 ThermoML 与 NBS514 中均无覆盖 |
| VC | P4 | `NO_OBSERVATION_AND_NO_PAGE_READ` | 0 | 检索原始文献/公开数据库; 该分子在 ThermoML 与 NBS514 中均无覆盖 |
| DOL | P4 | `NO_OBSERVATION_AND_NO_PAGE_READ` | 0 | 检索原始文献/公开数据库; 该分子在 ThermoML 与 NBS514 中均无覆盖 |
| TMP | P4 | `NO_OBSERVATION_AND_NO_PAGE_READ` | 0 | 检索原始文献/公开数据库; 该分子在 ThermoML 与 NBS514 中均无覆盖 |

### 按原因分解
- `NO_CONDITION_VALID_PAIR`：**5**
- `NO_OBSERVATION_AND_NO_PAGE_READ`：**7**
- `NO_ROOM_BAND_OBSERVATION`：**1**

## 五、来源独立性
证明非独立的文档对：**9**

| 文档 A | 文档 B | 相同观测 | 共享 A18 分子 |
|---|---|---:|---|
| `10.1016/j.fluid.2008.01.024` | `10.1016/j.fluid.2009.07.009` | 5 | — |
| `10.1016/j.tca.2012.05.036` | `10.1016/j.tca.2012.10.024` | 3 | — |
| `10.1021/acs.jced.8b00755` | `10.1021/je060248p` | 1 | — |
| `10.1021/je060248p` | `10.1021/je800593p` | 2 | — |
| `10.1021/je060248p` | `10.1021/je900503p` | 1 | — |
| `10.1021/je3007666` | `10.1021/je800593p` | 15 | — |
| `10.1021/je3007666` | `10.1021/je900503p` | 2 | — |
| `10.1021/je800593p` | `10.1021/je900503p` | 2 | — |
| `10.6028/nbs.circ.514` | `10.6028/nbs.circ.514` | 0 | EA;MA |

**含义：** 「独立来源数」在本数据集中是一个**上界**，不是实测值。B07 的来源聚类检验必须先按文档去重。

## 六、文献来源清单
仓库已持有并覆盖 A18 的源文档：**14** 个。

| 源文档 | 覆盖 A18 分子数 | 账本行数 | 有源字节 | 录入路径 |
|---|---:|---:|---|---|
| `10.1016/j.jct.2008.02.015` | 2 | 15 | true | THERMOML_XML |
| `10.1016/j.jct.2010.09.008` | 2 | 15 | true | THERMOML_XML |
| `10.6028/nbs.circ.514` | 2 | 0 | true | NBS514_CIRCULAR_MANUAL_ENTRY |
| `10.1016/j.fluid.2013.12.014` | 1 | 7 | true | THERMOML_XML |
| `10.1016/j.jct.2008.09.006` | 1 | 18 | true | THERMOML_XML |
| `10.1016/j.tca.2012.10.004` | 1 | 16 | true | THERMOML_XML |
| `10.1016/j.tca.2012.10.024` | 1 | 9 | true | THERMOML_XML |
| `10.1016/j.tca.2017.03.018` | 1 | 4 | true | THERMOML_XML |
| `10.1016/j.tca.2019.03.028` | 1 | 3 | true | THERMOML_XML |
| `10.1021/je300958c` | 1 | 139 | true | THERMOML_XML |
| `10.1021/je400149j` | 1 | 53 | true | THERMOML_XML |
| `10.1021/je700055p` | 1 | 9 | true | THERMOML_XML |
| `10.1021/je900503p` | 1 | 13 | true | THERMOML_XML |
| `10.1021/je9010773` | 1 | 183 | true | THERMOML_XML |

> **范围声明：** 本清单描述仓库**已持有**的源文档，**不代表已完成穷尽式文献检索**。

## 七、跨来源冲突（R4 发现）
仓库**已持有**的 CC BY 4.0 来源 (`data/raw/open_data_eps/eps_observations.csv`) 对 EA/MA 给出了与 NBS514 不一致的值，此前从未对账：

| 分子 | NBS514 值 | NBS514 T | 持有来源值 | 持有来源 T | 差异 |
|---|---:|---:|---:|---:|---:|
| EA | 6.02 | 298.15 | 6.5 | — | 7.97% |
| MA | 6.68 | 298.15 | 7.072 | 288.15 | 5.87% |
| MA | 6.68 | 298.15 | 7.2 | — | 7.78% |

**这推翻了「已核实」的简单叙事。** 核实只证明 NBS514 的转录忠实，不证明该值是唯一正确值。MA 的 5.87% 差异无法用 10 K 温差解释（酯类 dε/dT 约 −0.15~−0.2 %/K）。

**B04 前必须裁决**，不得择一作为主值而不说明。

## 八、明确未做的事
- 未新增任何测量到 measurement_ledger
- 未把 NBS514 页面读取伪装成 ThermoML 测量
- 未把高温观测折算成室温
- 未把 AN 的 0.01/1 MHz 证据当作 static 0 Hz
- 未对任何未解决分子降低准入标准
- 未声称已完成穷尽式文献检索

## 九、阶段门
**B03 交付物：7/7**

**账目闭合：** ✅ 通过

**条件合格测量：** 2 条（待四智能体审核）

**未解决分子：** 必须留在未解决清单，**不得为了凑数进入 B04**。
