# Week 17 臂 W17-5：液相窗口硬门（MP/BP/FP）—— 正式特征列 + 漏斗硬门 + 触发率

**任务**：`week17_liquid_window_gate`（臂 `W17-5`）｜**生成时刻**：2026-09-26T12:47:14Z｜**网络调用**：0 ｜**拟合模型**：0 ｜**产出 R²**：无
**上游**：AD-1 `probes/pubchem_liquid_window_harvest.py`（PubChem PUG-REST，314 键 M/B/F/Density）
**预注册**：`probes/liquid_window_gate_prereg.json`（`status = locked_before_run`，sha256 `1b2dba9e…`，先于任何一次运行锁定）
**产物**：`data/processed/liquid_window_features.csv`、`data/processed/liquid_window_gate_report.csv`、`probes/liquid_window_gate_summary.json`、本报告

## 1. 结论速览

| 读数 | 值 |
|---|---|
| 覆盖集 | **314 键**（`data/reference/identity_map.csv`，逐键一行） |
| 门判定 | **blocked 77 / pass 126 / unknown 111** |
| 触发率（口径 A：blocked-only） | **24.52%**（77/314） |
| 触发率（口径 B：blocked+unknown，保守漏斗口径） | **59.87%**（188/314） |
| 淘汰原因分解 | `mp_above_T_low` 56；`bp_below_T_high` 21（无一键同时触发两条） |
| EC 判定 | **blocked**（`mp_above_T_low`，mp = 36.4 °C） |
| 适用域 SMARTS 门（历史，6150 行） | 33.66% |
| 适用域 SMARTS 门（同 314 键重算） | 28.34%（89/314） |

一句话：**液相窗口门在 314 键上的触发率与既有适用域 SMARTS 门同量级（24.52% vs 33.66%），且两者互不覆盖——SMARTS 门放行的键里有 40 个被液相窗口门拦下**（含 EC、丙酮、DMC、环丁砜、DMSO）。这正是「便宜且硬、排在 ε 分选之前」的理由。

## 2. 门定义与口径（先于执行冻结）

**工作温度窗口：-20 °C .. +60 °C（闭区间）。**

- **取值理由**：这是商用锂离子电池的行业标准工作/生存区间（0..45 °C 充放电、-20..60 °C 生存），纯组分电解液溶剂若在该区间内不是液体，即不可作纯溶剂使用。窗口**先陈述、后不拟合**——定窗口时未查看任何候选键的数值。该区间同时框住两个 sanity 锚点：EC（mp 36.4 °C，室温固体）落在区间内必须被淘汰，而常规液态共溶剂（DEC mp −43 °C、PC mp −48.8 °C）通过。
- **判定规则**：纯物质在熔点与沸点之间才是液体。要在整个窗口保持液态，必须冷端不冻结（`mp_C > T_low_C` 即失败）、热端不沸腾（`bp_C < T_high_C` 即失败）。**两条子句是各自独立的失效模式，任一条触发即淘汰**；单侧证据足以淘汰（mp 高于冷端就已冻结，与 bp 是否已知无关）。
- **unknown 政策**：缺 `mp_C` 或 `bp_C` **既不默认放行、也不默认淘汰**，单列 `unknown` 并同时报告两种触发率：口径 A（blocked-only，把 unknown 算作放行）与口径 B（blocked+unknown，unknown 不放行的保守漏斗口径）。
- **与既有适用域 SMARTS 门的关系**：两门测的不是一回事，互补而**不冗余**。适用域门（`src/electrolyte_ml/applicability.py`，SMARTS `[O,S,N;!H0]`，6150 折叠外行触发率 33.66%）是**化学**命题——能给出氢键的候选会形成自缔合液体，单分子介电模型无法表征；液相窗口门是**物态**命题——不在工作区间的候选根本不是液体。一个候选可以任一门通过、两门都通过或两门都不过。因为液相窗口的证据已缓存、判定只是一次数值比较，故排在 ε 排序之前，且与 SMARTS 门**并列而非替代**。
- **flash point 的角色**：收割并导出为特征列，但**不进本硬门**。闪点是可燃性/安全性，不是纯液体的相边界；液体可在整个窗口内保持液态却闪点很低。把它塞进相门等于把安全过滤混进物态过滤，故留给独立的安全复核。
- **density 的角色**：仅作特征列。密度不界定液相窗口，且测量口径混杂（绝对 g/cm³ / 相对水 / 无单位 depositor 行），逐行如实标注，不静默转成门。

## 3. 314 键覆盖率清点

| 性质 | 有值键数 | 备注 |
|---|---|---|
| `mp_C`（熔点） | **202** | |
| `bp_C`（沸点） | **216** | |
| `flash_point_C`（闪点） | **189** | |
| `density_g_cm3`（密度） | **212** | 其中 **84** 键主值为 `absolute`（真 g/cm³），其余 77 `relative`、51 `unspecified` |
| 三个温度齐全 | **186** | 与上游 summary 的 186 逐位一致 |
| 四项全无 | **96** | 全部落在 314 键的 `unknown` 侧或本就有值但无 MP/BP |

四个性质的键数、以及「三温度齐全 = 186」均与上游 `pubchem_liquid_window_harvest_summary.json` 的 `property_coverage` / `keys_with_all_three_temperatures` **逐位相等**（`scripts/verify_liquid_window_gate.py` 的 `coverage_vs_upstream:*` 断言）。上游 `network_calls = 0`（缓存复算），本臂沿用缓存，同样 0 次联网。

## 4. 门判定与触发率报告

判定逐键写在 `data/processed/liquid_window_gate_report.csv`（列含 `gate_decision`、`trigger_reasons`、`unknown_reason`、`evidence_columns`、`mp_C`/`bp_C` 及其 depositor/置信档、`T_low_C`/`T_high_C`）。

**触发原因分解（口径 A 的 77 键）**

| 原因 | 键数 | 典型 |
|---|---|---|
| `mp_above_T_low` | 56 | EC（36.4）、DMC（0.5）、环丁砜（27.8）、DMSO（18.45）、苯甲腈（−12.82）、硝基苯（5.7） |
| `bp_below_T_high` | 21 | 丙酮（56.08）、丙烯（−47.68）、1,1,1-三氟乙烷（−47.2）、甲醚（−24.82）、正戊烷（36.06） |

`bp_below_T_high` 拦下的全是常温易挥发物/气体（正是海选该拦的），`mp_above_T_low` 拦下的是室温附近或以上就冻结的固体/半固体。

**unknown 分解（111 键）**：`missing_mp`（只缺 mp、bp 已知）13 键；`missing_mp;missing_bp`（两边界皆缺）98 键。注意 **没有任何键是「只知道 mp 不掌握 bp」**——沸点覆盖（216）严格包含熔点覆盖（202）。这 13 个「只缺 mp」中有 1 个仍被单侧证据淘汰（`2-chloro-2-methylpropane`，bp 50.9 < 60，`mp_C` 空），正好演示了「单条子句足以淘汰」。

## 5. sanity check：EC 是室温固体

- **EC（碳酸乙烯酯，`KMTRUDSVKNLOMY-UHFFFAOYSA-N`）熔点 36.4 °C**（HSDB depositor），室温固态 → 判定 `blocked`，原因 `mp_above_T_low`。纯 EC **过不了门**，这正是海选要拦的情形；「门若放行纯 EC 即门已损坏」写进了预注册与测试（`test_ec_is_a_room_temperature_solid_and_is_blocked`）。
- **Reaxys 温度标签教训**：Reaxys 曾把 EC 的介电值 89.78 标为 **25 °C**；而本仓既有溯源（`reports/jstage_corroboration.md`）把同一 89.78 记为 **40 °C = 313.15 K**，且 EC 熔点 36.4 °C、**25 °C 本就不是液态**——Reaxys 的温度栏就是错的。教训固化为规则：**任何温度标签都必须与该物质的液相窗口交叉核对**，落在 [mp, bp] 之外的值只标记、不消费。本门只把 mp/bp 当作相边界、从不读取任何介电值的温度标签，因此不会继承该错标；教训写入预注册，供后续「液相窗口 × 温度分辨介电行」的臂复用。

## 6. 与适用域 SMARTS 门的量级对照（含异常解释）

**历史对照**：适用域 SMARTS 门 33.66%（2070/6150 折叠外行，`probes/applicability_domain_summary.json`）。本门口径 A = 24.52%、口径 B = 59.87%。口径 B / 33.66% = **1.78×**，在**一个数量级之内**（summary `within_an_order_of_magnitude = true`）。

**同群体对照**（更可比）：把 SMARTS 规则在同 314 键上重算 → **89/314 = 28.34%**（RDKit 解析 314/314，无未解析）。与口径 A 的 24.52% 几乎同量级。

**两门互不覆盖（这是关键，说明不冗余）**：

| 单元格 | 键数 |
|---|---|
| 本门 blocked ∧ SMARTS 命中 | 37 |
| 本门 blocked ∧ SMARTS 放行 | **40** |
| 本门 pass ∧ SMARTS 命中 | 40 |
| 本门 unknown（其中 SMARTS 命中 12） | 111 |

即：**液相窗口门独有拦下 40 键**（丙酮、DMC、环丁砜、DMSO、EC、1,4-二氧六环、正戊烷、二硫化碳、苯甲腈、硝基苯……），这些键多数无 O–H，SMARTS 门必然放行；反过来 **SMARTS 门独有命中 52 键**（本门 pass 或 unknown）。两门各管一类失效，缺一不可。

**异常与解释**：口径 B（59.87%）显著高于 SMARTS 门的 33.66%。异常来源已查明，**不是阈值假象，而是覆盖集构成**：unknown 的 111 键中，**58 键**是 PubChem 无 `Experimental Properties` 段（`no_experimental_properties_section`，其中绝大多数是盐/离子液体：56 键 SMILES 含盐点、48 键含形式电荷），**36 键**是「有该段但无 MP/BP/FP/Density」，**14 键**是无温度值、**3 键**有值但无 MP/BP。缺值高度集中于离子液体/盐——它们本就该走 ILThermo / 一次文献，而不是被 PubChem 遗漏静默放行。这恰恰证明了 unknown 单列的价值。

## 7. 冲突不平均与置信档

口径纪律：同一（键，性质）**取主值 + 记备选，冲突不平均**。主值沿用上游 `liquid_window_selected.csv` 的选定行（温度 `peer_reviewed_first_then_lower_median`；密度 `absolute_then_relative_then_unspecified; peer_reviewed_first; lower_median`），并逐列携带 `*_raw` / `*_depositor` / `*_reference_number` / `*_selection_rule` / `*_peer_reviewed`。备选解析值只记为计数与 min/max 区间（`*_alt_min` / `*_alt_max`），**永不求均值**。

**置信档**（温度容差 2 °C、密度相对容差 2%）：`high` = 主值同行评审且另有解析值在容差内佐证；`medium` = 主值同行评审但无佐证；`low` = 主值非同行评审；`absent` = 无解析值。`*_conflict` 单列布尔（解析值跨度超容差），只标记、不改写主值。

| 性质 | high | medium | low | absent |
|---|---|---|---|---|
| melting_point | 103 | 69 | 30 | 112 |
| boiling_point | 132 | 42 | 42 | 98 |
| flash_point | 47 | 97 | 45 | 125 |
| density | 68 | 33 | 111 | 102 |

口径校验：`primary_within_alternative_range` 断言每个主值都落在其备选区间的闭区间内（314 键 × 4 性质全通过）。

## 8. 边界与已知未核

- **门判的是纯组分**。纯 DMC（mp 0.5 °C）在 −20 °C 被淘汰、纯 EMC/低熔点共溶剂在混合物里才可用——这不是门的错误，而是「海选以纯组分为单位」的既定口径；配液工程在下游。报告如实点出，供配方臂引用。
- **unknown 既非放行也非淘汰**，两种触发率并列给出，读者自行承担缺值成本。
- **数值为 depositor 汇编**（`source_kind=compilation`、`quality_layer=filter_only`）：可筛可排，**不得**当作一手可引核心值；升级需独立判读。
- **未知未核**：58 键离子液体的液相窗口仍未取数（需 ILThermo/一手文献）；flash point 未进门；density 的 77 `relative` + 51 `unspecified` 行只作特征、未转真 g/cm³。
- `data/processed/*` 默认被 `.gitignore` 忽略：本臂两个新产物 `liquid_window_features.csv`、`liquid_window_gate_report.csv` 若要随仓提交，需在 `.gitignore` 增补对应 `!` 反忽略行（本臂**未**改动 `.gitignore`）。

## 9. 复现

```powershell
# 构建特征列 + 硬门判定 + summary（离线，network_calls = 0）
.\.venv\Scripts\python.exe probes\build_liquid_window_features.py

# 离线复算校验（41 项，exit 0 = 全通过）
.\.venv\Scripts\python.exe scripts\verify_liquid_window_gate.py --check

# 本臂离线单测
.\.venv\Scripts\python.exe -m pytest tests\test_liquid_window_gate.py -q
```

## 附录：产物摘要（sha256 / 行数）

| 产物 | 行数 | bytes | sha256 |
|---|---|---|---|
| `data/processed/liquid_window_features.csv` | 314 | 175951 | `a27386787f4c81981fd2489e12139518c29619a13fd9da92a18b28f10ff94fb2` |
| `data/processed/liquid_window_gate_report.csv` | 314 | 50875 | `afcff965856274fc19333a236fb819b16631ae0bb9f49e59daa5d21b4519e0d2` |
| `probes/liquid_window_gate_prereg.json` | — | — | `1b2dba9e93db8f7a7e13a67c851d61e7f25dd85ff27ef102237546f69109f6de` |

六件冻结件 digest 在 summary 的 `frozen_red_lines` 段逐件核对，**六件全 INTACT**。