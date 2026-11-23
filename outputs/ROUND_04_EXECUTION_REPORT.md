# PLAN B 第四轮执行汇报：B03 完成 + 四智能体审核

**工作包：** B03 A18 证据回填（全部 7 个交付物）+ 四智能体审核
**时间：** 2026-11-23
**性质：** 完成 B03 交付，四审发现并修复 4 个自身代码缺陷

---

## 零、本轮结论

| 项 | 结果 |
|---|---|
| **B03 交付物** | ✅ **7/7 齐备** |
| **账目闭合** | ✅ 18/18（5 有证据 + 13 未解决） |
| **B03 四智能体审核** | ✅ 完成（2 PASS + 2 HOLD → **HOLD**） |
| **新增观测** | ⚠️ **0 条**（EA/MA 早已在 v04） |
| **四审发现的自有缺陷** | 🔴 **4 个，已全部修复** |
| 测试 | ✅ **268/268 通过** |
| 冻结字节 | ✅ **OVERALL PASS** |
| B01 独立校验 | ✅ **18/18 PASS** |

---

## 一、B03 交付物

PLAN B B03 要求的 7 个文件全部生成：

| 文件 | 行数 | 内容 |
|---|---:|---|
| `A18_gap_register.csv` | 18 | 逐分子缺口与下一步 |
| `literature_source_inventory.csv` | 14 | 仓库已持有的源文档 |
| `source_verification.csv` | 9 | NBS514 页面核实 |
| `condition_qualified_measurements.csv` | 2 | 条件合格记录（待审） |
| `independent_source_map.csv` | 9 | 证明非独立的文档对 |
| `unresolved_molecules.csv` | 13 | 未解决分子与原因 |
| `evidence_backfill_report.md` | — | 机械生成的报告 |

**分层与 PLAN B 完全一致**：P0=3、P1=4、P2=1、P3=1、P4=9。

---

## 二、必须澄清：本轮没有新增任何观测

EA 与 MA 的 ε 值（6.02 / 6.68）**早已存在于 `dielectric_v04.csv`**
（`dataset_origin = v0.2`，`source_doi = 10.6028/nbs.circ.514`）。

B03 做的是**核实**这两条既有记录确实可由 NBS514 页面读取复现，
**不是新增了两条测量**。

**证据基数的真实变化是 0 条新观测。**

这一点被四位评审全部独立确认（R4 还给出了 mtime 证据链：
转录 2026-09-23 → v04 2026-09-26 → B03 报告 2026-11-23）。

---

## 三、B03 四智能体审核：HOLD

| Reviewer | EA (C11) | MA (C12) | 关注点 |
|---|---|---|---|
| R1 化学/物理 | **PASS** | **PASS** | 数值与化学合理性 |
| R2 来源/DOI | **HOLD** | **HOLD** | 来源分级 + 独立性 |
| R3 代码/数据 | **PASS** | **PASS** | 独立重算 |
| R4 反向审计 | **HOLD** | **HOLD** | 证据基数是否真增长 |

**共识：两条均 `AI_CONSENSUS_HOLD`**（未达 4/4 PASS）。

### 3.1 分裂点不在数值，在溯源

四位评审的分歧是**可以精确描述**的：

- **R1/R3 认可数值**：R3 独立重算得 6.02 / 6.68，并用 PyMuPDF 从 PDF
  第 20/18 页抽取出 `6.02 25` 与 `6.68 25`；R1 读了原始 PDF，
  确认整条乙酸酯系列单调（甲 6.68 > 乙 6.02 > 丙 5.69 > 丁 5.01）。
- **R2/R4 质疑溯源**：NBS514 是 1951 年**二手汇编**（R2 引原文 §2.6
  「All tabulated data are based on the references indicated by numbers not
  enclosed in brackets」）；EA 与 MA **共享参考文献 63**。

**两者可以同时为真**：数字是对的，但证据不够强。

### 3.2 R1 的化学验证（超出要求）

R1 做了两项独立验证：

1. **同系物单调性**：从同一份印刷原件读出丙酯 5.69、丁酯 5.01，
   MA−EA 的 0.66 差值是两倍 NBS 2% 误差带的 **3.67 倍**，
   即使取最坏情形仍保持序关系。
2. **NBS 自身温度系数反推**：用原件印出的 α（MA 2.2e-3、EA 1.5e-3 /°C）
   把 25 °C 值反推到 20 °C，得 6.790 与 6.095，
   与文献 20 °C 值（6.79/6.87、6.09/6.10）相差 **0.00% / 0.08%**。
   **这是真正的独立验证**，因为锚点与系数是表中两份独立信息。

**R1 还确认 298.15 K 是实测温度而非制表约定**：NBS 该节印了 13 个不同 t 值，
仅 22.5% 在 25 °C；而 298.15 K 正是这两行的锚点，因此零温度换算。

---

## 四、四审发现的 4 个自有缺陷（全部已修复）

### D2（最严重）：校验器从未打开 v04

`verify_nbs514_evidence.py` 声称「与冻结 v04 值比对」，但**从未打开
`dielectric_v04.csv`**——它读的是 expansion 镜像。

**R3 用污染实验证明**：把 v04 的 EA/MA 改成 99.99，输出**逐字节不变**。

**修复**：新增 `_v04_lookup()` 真正读取 `dielectric_v04.csv`。
**负向对照已验证**：污染 v04 后，校验器现在正确报 `VALUE_MISMATCH`。

### D5：账目门是代数恒等式，永不失败

```python
resolved_ids = gap_ids - unres_ids          # resolved := gap − unres
gate_ok = len(resolved) + len(unres) == len(gap)   # 恒成立
```

R3 证明：从 `unresolved_molecules.csv` 删掉 EC，门仍然打印
「6 + 12 = 18 / 18 ✅ PASS」，把**没有任何证据的 EC 认证为已解决**。

**修复**：改为对「独立重推的解决集合」做交叉核对。

```python
derived_resolved = {分子 | n_condition_valid_pairs>0 或 有 NBS514 页面核实}
if derived_resolved != resolved_ids: → accounting_errors
```

**负向对照已验证**：删掉 EC 后，门现在报 **CLOSED**，
并输出 `解决判定与独立重推不一致: 清单多出 ['C04']`。

### D1：死代码把观测数当 ε

`v04_eps = fnum(x.get("n_observations"))` —— 把**计数**赋给 ε 变量。
虽未被导出（死代码），但是陷阱。**已随 D2 重写删除。**

### D6/D7：硬编码与状态不匹配

- `frequency="static"` 是硬编码字面量（636 行转录中有 127 行带真实频率注记）
- 修复文本按硬编码 `("C11","C12")` 分支，而非按状态

---

## 五、R4 发现的两个实质问题（已修复）

### 5.1 「零观测」标签是错的

R4 指出：9 个 P4 分子标为 `ZERO_OBSERVATION`，但它们在
`dielectric_v04.csv` 中**全部都有整理值**（EC 90.5、PC 64.9、FEC 78.4、
VC 126.0、EMC 2.96、DOL 7.3、TMP 21.6）。

**「无观测」只对 ThermoML 观测层成立**，对 v04 层不成立。

**修复**：新增 `v04_curated_value_present` 等 5 列，状态改为
`NO_THERMOML_OBSERVATION_BUT_V04_VALUE`，blocker 拆为
`ZERO_THERMOML_OBSERVATIONS` + `CURATED_VALUE_NOT_IN_OBSERVATION_LAYER`。

R4 还指出：要求 EC/PC/FEC/VC 出现在 1951 年的汇编里是**同义反复**——
这些溶剂在 1951 年之后才商业化。

### 5.2 MA 的跨来源冲突从未对账

仓库**已持有**的 CC BY 4.0 来源（`data/raw/open_data_eps/eps_observations.csv`）
给出与 NBS514 不一致的值：

| 分子 | NBS514 | 持有来源 | 差异 |
|---|---:|---:|---:|
| EA | 6.02 @298.15 | 6.5 @— | **7.97%** |
| MA | 6.68 @298.15 | 7.072 @288.15 | **5.87%** |
| MA | 6.68 @298.15 | 7.2 @— | **7.78%** |

MA 的 5.87% 差异**无法用 10 K 温差解释**（酯类 dε/dT 约 −0.15~−0.2 %/K）。

**已新建 `cross_source_conflicts.csv` 登记，标记 UNRESOLVED。**

---

## 五之二、缺陷修复：dataset v06

PLAN B 要求**修复**高压污染与合成中点，而非仅测量。障碍在于：修复会改变
合格行数，从而静默移动已报告的 460/78/170 计数。

**解法是版本化，不是修改**：

| 版本 | 状态 |
|---|---|
| `v04` / J01 / J02 / J03 | **字节不变，永久**（哈希已验证 `e046a383…`） |
| `v05` 测量账本 | **字节不变** |
| `v06`（本轮新建） | **新数据集**，排除缺陷行，并列存在 |

### v06 的三项修复

| 修复 | 机制 |
|---|---|
| **压力异质性** | 贡献观测跨越常压与加压的聚合行排除出 `model_ready`，标 `PRESSURE_HETEROGENEOUS`；**不做静默替换** |
| **合成中点** | 由两个独立中位数拼成的 (T,ε) 对不是测量，排除并标 `SYNTHETIC_PAIR` |
| **温度推定** | 温度推定的行**保留**（ε 可能仍真实），但标 `TEMPERATURE_IMPUTED`，不得作为同温证据 |

### 结果

| 项 | 数量 |
|---|---:|
| v04 总行数 | 248 |
| **v06 model_ready** | **74** |
| v06 排除 | 174 |
| v05 `pair_valid` | 78 |
| 差额 | −4 |

**没有任何行被删除。** 每个被排除的行都保留在 `dataset_v06_exclusions.csv`
并注明原因，因此旧分母可完整复现。

**74 条 model_ready 全部通过三项检查**：`pair_valid=true`、
无推定温度、无加压数据。

**差额 −4 的解释**：v05 只判 (T,ε) 是否同源；v06 额外要求温度非推定且压力同质。
两者**不是同一口径**，已在 manifest 的 `denominator_note` 中写明。

---

## 六、必须记录的一个方法论更正：循环论证

`source_verification.csv` 报告 `epsilon_agrees = true`，
早期报告把它称为「独立核实」。

**但 v04 中 EA/MA 两行的 `source_doi` 就是 `10.6028/nbs.circ.514`，
`source_record_id` 分别是 `nbs514:p20:022` 与 `nbs514:p18:009`——
与本次页面读取完全相同。**

因此这证明的是**转录忠实**，**不是**两个独立来源相互印证。

R1 与 R4 独立发现了这一点。报告已改写，并在 JSON 中加入
`circularity_warning`。

**EA 与 MA 仍各自是 SINGLE_SOURCE。**

---

## 七、修复清单

| # | 缺陷 | 发现者 | 修复 | 负向对照 |
|---|---|---|---|---|
| D2 | 校验器未读 v04 | R3 | `_v04_lookup()` 真读 v04 | ✅ 污染 v04 → VALUE_MISMATCH |
| D5 | 账目门恒等式 | R3 | 独立重推交叉核对 | ✅ 删 EC → CLOSED |
| D1 | 观测数当 ε | R3 | 随 D2 删除 | — |
| D6/D7 | 硬编码 | R3 | 状态驱动 | — |
| — | 「零观测」误导 | R4 | 5 个新列 + 双 blocker | ✅ 测试锁定 |
| — | EA/MA 共享引用 | R2/R4 | 新增独立性记录 | ✅ 测试锁定 |
| — | 跨来源冲突未对账 | R4 | `cross_source_conflicts.csv` | ✅ 测试锁定 |
| — | 循环论证表述 | R1/R4 | 报告改写 + JSON 警告 | ✅ 测试锁定 |

---

## 八、测试与验证

| 项 | 结果 |
|---|---|
| `test_b03_gap_register.py` | **8/8** |
| `test_b03_evidence_backfill.py` | **16/16** |
| `test_b03_consensus.py` | **7/7** |
| `test_b01_reconstruction.py` | 21/21 |
| `test_b02_gvl_conflict.py` | 7/7 |
| `test_b02_consensus_gate.py` | 9/9 |
| `test_b00_repo_forensics.py` | 10/10 |
| 既有 confirm_2027 五套 | 183/183 |
| **合计** | **268/268 通过** |
| 冻结产物 | **OVERALL PASS**（24/24 + 14 输入 + 20 R007） |
| B01 独立校验 | **18/18 PASS** |
| CPU core-hours | **< 0.03**（累计 < 0.12） |
| DFT | **0** |

---

## 九、B04 阻断状态

B04 **仍不得建池**。阻断项从 3 个增至 5 个：

| # | 阻断项 | 数量 | 来源 |
|---|---|---:|---|
| 1 | 压力污染未修复 | 15 行 | B01 |
| 2 | 观测层冲突未裁决 | 56 组 | B01 |
| 3 | 合成条件对 | 22 行 | B01 |
| 4 | **温度推定** | 22 行（18 model_ready） | B01 |
| 5 | **EA/MA 跨来源冲突 + 未达 4/4** | 3 条冲突 + 2 记录 HOLD | B03 |

---

## 十、下一步

### 需人工批准（阻塞 B04）

1. **G14 温度推定**：18 行改 `model_ready=false` 改变 v04 可用样本数
2. **G15 `v04_epsilon` 污染**：修复骨架连接改变 J03 产物
3. **G12 压力分层**：改动 R219 冻结窗口语义

### 可自主推进

4. **EA/MA 冲突裁决**：回 NBS514 原始参考文献（ref 8/63/260/276）核对
5. **剩余 56 组冲突**：按 GVL 模式分批送四审
6. **B03 补检索**：EC/PC/FEC/VC 等现代溶剂需查 1951 年后的文献

### 建议顺序

```
EA/MA 回原始文献 → 剩余冲突分批四审 → [批准] G14/G15/G12 → B04 → B05
```

---

## 附录：复现命令

```bash
cd "E:/Claude Code/电解质ML/电解质ML"
PY=.venv/Scripts/python.exe

$PY scripts/b03/build_a18_gap_register.py
$PY scripts/b03/verify_nbs514_evidence.py
$PY scripts/b03/build_b03_registers.py
$PY scripts/b03/build_b03_report.py
$PY scripts/b03/build_b03_consensus.py

$PY -m pytest tests/test_b03_gap_register.py tests/test_b03_evidence_backfill.py tests/test_b03_consensus.py -q
```
