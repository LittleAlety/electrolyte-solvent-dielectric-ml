# PLAN B 第三轮执行汇报：B01 收口 + γ-戊内酯四审裁决

**工作包：** B01 收口（G11/G3 修复）+ B02-CONFLICT（γ-戊内酯裁决）
**时间：** 2026-11-23
**性质：** 修复两个 B01 阻断项 + 完成一次完整的四智能体冲突裁决

---

## 零、本轮结论

| 项 | 结果 |
|---|---|
| **G11 生成器同义反复判据** | ✅ **已修复**（69/248 → 248/248，可失败） |
| **G3 measurement_locator** | ✅ **已交付**（2065/2065，block/property/row） |
| **B01 阶段门** | ✅ **OPEN**（18/18 校验通过） |
| **γ-戊内酯冲突入队** | ✅ 已入队并完成四审 |
| **γ-戊内酯裁决** | ⚠️ **两条均 REJECTED**（未达 4/4） |
| **新发现：温度推定** | 🔴 **22/248 行温度是推定值，18 行 model_ready=true** |
| **新发现：skeleton 连接缺陷** | 🔴 **3 行 `v04_epsilon` 被污染（含 9.2→2.14）** |
| **新发现：冲突容差缺陷** | 🔴 **`round(t,1)` 漏检，已改为成对比较（49→56 组）** |
| 测试 | ✅ **237/237 通过** |
| 冻结字节 | ✅ **OVERALL PASS** |

---

## 一、修复 B01 的两个阻断项

### 1.1 G11：同义反复的验收判据

**原判据**（`build_provenance_preserving_dataset.py:437`）：

```python
"no_synthetic_pair_marked_valid": all(
    r["condition_pair_valid"] == "true"
    for r in validity_rows
    if r["invalidity_reason"] in ("not_evaluated",)   # ← 只在有效时才成立
)
```

`invalidity_reason == "not_evaluated"` 只在没有无效原因时出现，即配对天然有效时。
该判据只检查 **69/248** 行，全部为 true，排除的 179 行中有 **170 行是 false**。
**它不可能失败。**

**修复后**：结构化判据——交集温度中位数持有者与 ε 中位数持有者的观测索引。
真实测量有非空交集，合成复合值没有。

```python
def _no_synthetic_pair_marked_valid(validity_rows):
    for row in validity_rows:
        if row["condition_pair_valid"] != "true":
            continue
        t_idx = _holder_row_indices(row["temperature_median_holders"])
        e_idx = _holder_row_indices(row["epsilon_median_holders"])
        if not t_idx or not e_idx:
            return False
        if not (t_idx & e_idx):
            return False
    return True
```

并新增 `synthetic_pair_check_coverage` 块，公开检查范围：

| 字段 | 值 |
|---|---|
| `n_rows_inspected` | **248**（原 69） |
| `n_rows_total` | 248 |
| `n_rows_invalid` | 170 |
| `criterion_can_fail` | **true** |
| `n_valid_with_shared_holder` | 78 |
| `n_valid_without_holders` | 0 |

**负向对照已验证**：把旧判据重新注入代码体后，校验器立即判 FAIL。恢复后通过。

### 1.2 G3：measurement_locator

从 ThermoML 源文件重建定位符，**2065/2065 全覆盖**：

```
ThermoML block=2|prop=1|propname=Relative permittivity at zero frequency
|phase=Liquid|method=impedance analyzer|row=2384
```

**这不是模板**：1,782 个不同定位符，block 编号从 1 到 7 分布。
逐字节验证：定位符指向的 block 确实含 permittivity + impedance analyzer + Liquid。

**诚实边界**：定位到**机器可读沉积记录**，不是论文页码。
ThermoML 不携带页码，编造页码属于伪造。

---

## 二、γ-戊内酯四智能体裁决

### 2.1 背景

Reviewer 4 在 B02 发现：γ-戊内酯 36.1 vs 36.9 的冲突**未进入审核队列**——
被排除而非被裁决。本轮补入队列（Track `UNRESOLVED_SOURCE_CONFLICT`）并完成四审。

### 2.2 四审结果

| Reviewer | R227 (36.1) | R248 (36.9) | 建议处置 |
|---|---|---|---|
| R1 化学/物理 | HOLD | HOLD | RETAIN_PARALLEL |
| R2 来源/DOI | HOLD | **FAIL** | NEEDS_PRIMARY_DOCUMENT |
| R3 代码/数据 | HOLD | HOLD | （报告 authoritative_value） |
| R4 反向审计 | **FAIL** | **FAIL** | REJECT_ROW / NEEDS_PRIMARY_DOCUMENT |

**共识：两条均 `AI_CONSENSUS_REJECTED`**（未达 4/4 PASS）。

### 2.3 四位评审的核心发现（相互独立）

**R2 —— 前提不成立**
iScience Table 3 **没有温度列**。`298.15` 从未在该表出现。
R248 的 `temperature_source = not_reported`，R227 的是
`review_table_standard_room_temperature`。
**「同温下数值矛盾」这个前提是两次独立推定碰巧一致造出来的。**

**R1 —— 2.2% 小于方法本身的重现性**
同一份 GBL 原始 ThermoML 文件在同一温度有两个重复值，相差 1.10%，
是其自报 U=0.06 的 **8 倍**。
2.22% 只有同实验室重复差异的一半、原始 vs 二手 GBL 差异（6.1%）的三分之一。
**这不是实验室间重现性，是方法噪声。**
R1 还给出：dε/dT = −0.129/K，0.80 的差距只需 **6.2 K**；
ε(291.9 K) = 36.1 + (−0.129)(291.9−298.15) = **36.90 恰好**。

**R3 —— 值不平均，但代码有缺陷**
逐行核实：`gap_epsilon == pv.v04_dielectric` **248/248**；
`v04_epsilon` 在 **3/248** 行不一致。
**`v04_epsilon` 是被污染的那一列，不是 `gap_epsilon`。**

**R4 —— 两条都不可采纳，且都不是独立测量**
两条 DOI 都真实存在（未来日期是误判，系统时间就是 2026-11）。
但 iScience 是**综述**（`pubTypeList=["review-article"]`），其引用链最终指向 R248 的
Segato 论文 —— **R227 不是独立的第二次测量，而是一次转引**。
R248 是金催化论文，GVL 是**反应溶剂**，113 篇参考文献**零篇**介电研究。

### 2.4 没有取平均

四位一致拒绝 `AVERAGE_JUSTIFIED`：两条非独立、都无报告温度、都无账本观测。
平均会产出一个**零溯源**的数字。

R3 对每行给出各自的权威值（R227=36.1，R248=36.9），未做任何合并。

---

## 三、本轮新发现的三个系统性缺陷

### 3.1 温度推定（最严重）

`data/dielectric_v04.csv` 的 `temperature_source` 分布：

| 来源 | 行数 |
|---|---:|
| `reported`（源文献报告了温度） | 226 |
| `review_table_standard_room_temperature`（推定室温） | **21** |
| `not_reported`（源文献未报温度） | **1** |
| **推定合计** | **22（8.87%）** |

**其中 18 行 `model_ready = true`。** 模型会被训练成
「一个未知温度下的测量值属于 298.15 K」。

R2 还发现这是**六行聚集**：v04row-224/225/227/236/243/244 全部复现同一张
iScience Table 3，全部顶着同一个推定 298.15 K。已逐行核实。

**后果**：GVL 的 36.1 vs 36.9 **可能根本不是冲突**，而是两次温度推定之差。

### 3.2 InChIKey 骨架连接缺陷（3 行被污染）

`audit_gap_aggregation_provenance.py:523` 用
`v04_by_skeleton = {skeleton(inchikey): row}`，而 `skeleton()` 只取 InChIKey 首段。
248 行 / **245 个骨架** ⇒ 字典推导只保留每组**最后一行**。

| aggregate_id | `v04_epsilon`（污染） | 权威值 | 偏差 |
|---|---:|---:|---:|
| `v04row-166` | 2 | 2.062 | −3.0% |
| `v04row-174` | **2.14** | **9.2** | **−77%** |
| `v04row-227` | 36.9 | 36.1 | +2.2% |

R174 的错误最严重（顺/反-1,2-二氯乙烯被折叠），此前从未被发现，
因为它落在 `COMPOSITE_CONDITION_UNMATCHED` 轨道，没人读它的 ε。

**污染是位置性的**：只有恰好排在组内最后一行的记录是对的。

### 3.3 冲突容差缺陷（漏检 7 组）

原实现用 `round(t, 1)` 分桶 —— 这是**四舍五入后的相等**，不是容差。
`T_TOLERANCE_K = 0.5` 被声明、被写进 JSON 和 MD，但**从未参与计算**（死代码）。

**它漏掉了 298.15 vs 298.2** —— 最典型的「室温」分歧。

改为成对比较 `abs(t1 - t2) <= T_TOLERANCE_K` 后：
观测层冲突 **49 → 56 组**，其中 33 组的温度不在 0.1 K 网格上（如 223.02、233.26）。

---

## 四、修复清单

| # | 缺陷 | 修复 | 验证 |
|---|---|---|---|
| 1 | 验收判据同义反复 | 结构化交集判据 + 覆盖范围公开 | 负向对照：注入旧判据→FAIL |
| 2 | `measurement_locator` 缺失 | 从 ThermoML 重建，2065/2065 | 逐字节验证 block 内容 |
| 3 | GVL 冲突未入队 | 新增 `UNRESOLVED_SOURCE_CONFLICT` 轨道 | 两条均已入队 |
| 4 | 队列静默丢弃未审记录 | 改为遍历队列而非评审并集 | 2 条显示 INCOMPLETE 而非消失 |
| 5 | GVL 两行 ε 显示相同 | 改用 `pv.v04_dielectric` | 36.1 / 36.9 正确显示 |
| 6 | 冲突容差用 `round()` | 改成对比较 | 49 → 56 组 |
| 7 | 温度推定未量化 | 新增审计脚本 | 22 行，18 行 model_ready |

---

## 五、测试与验证

| 项 | 结果 |
|---|---|
| `test_b01_reconstruction.py` | **21/21** |
| `test_b02_gvl_conflict.py` | **7/7** |
| `test_b03_gap_register.py` | **7/7** |
| `test_b02_consensus_gate.py` | 9/9 |
| `test_b00_repo_forensics.py` | 10/10 |
| 既有 confirm_2027 五套 | 183/183 |
| **合计** | **237/237 通过** |
| B01 独立校验 | **18/18 PASS** |
| 冻结产物 | **OVERALL PASS**（24/24 + 14 输入 + 20 R007） |
| CPU core-hours | **< 0.02**（累计 < 0.09） |
| DFT | **0** |

---

## 六、B01 阶段门：**OPEN**

两个原阻断项均已解除：

1. ~~`generator_acceptance_criterion_is_not_tautological`~~ → **PASS**
2. ~~账本字段真实缺口 `measurement_locator`~~ → **已另行交付，覆盖率 100%**

**但 B04 仍不得建池**，阻断项：

| 阻断项 | 数量 |
|---|---:|
| 压力污染未修复 | 15 行 |
| 观测层冲突未裁决 | 56 组 |
| 合成条件对 | 22 行 |
| 温度推定 | 22 行（18 行 model_ready） |

---

## 七、数据缺口更新

| # | 缺口 | 状态 |
|---|---|---|
| G1 | `outputs/` 未被 git 跟踪 | ⬜ 需批准 |
| G2 | `v56_standalone` 在仓库外 | ⬜ 需批准 |
| G3 | `measurement_locator` | ✅ **已解决** |
| G11 | 生成器判据同义反复 | ✅ **已解决** |
| G12 | 压力污染 15 行 | ⬜ 需协议决策 |
| G13 | 观测层 56 组冲突 | 🟡 GVL 已裁决，其余待办 |
| G7 | γ-戊内酯冲突 | ✅ **已入队并裁决（REJECTED）** |
| **G14** | **温度推定 22 行 / 18 行 model_ready** | 🆕 **新发现** |
| **G15** | **`v04_epsilon` 3 行被骨架连接污染** | 🆕 **新发现** |
| **G16** | **冲突容差漏检（已修，需重跑下游）** | ✅ 已修 |
| **G17** | **R227 `model_ready=true` 与冲突状态矛盾** | 🆕 新发现 |

---

## 八、B03 起步：A18 缺口登记

PLAN B B03 的 7 个交付物此前全部缺失。本轮建立第一个：`A18_gap_register.csv`。

**分层与 PLAN B 完全一致**（独立复算，非抄写）：

| Tier | 分子 | 数量 | 状态 |
|---|---|---|---:|
| P0 | DMC, DEC, SL | 3 | 全部 `SINGLE_SOURCE_ONLY` |
| P1 | DME, TEGDME, GBL, DMSO | 4 | 条件对无效 / 来源重复纠缠 |
| P2 | SN | 1 | **无室温观测**（仅高温） |
| P3 | AN | 1 | **非静态频率**（RF_ONLY） |
| P4 | EMC, EC, PC, FEC, VC, DOL, EA, MA, TMP | 9 | **零观测** |

**关键约束已被数据证实**：

- **SN（P2）**：17 条观测、**0 条在 293.15–303.15 K**。
  这正好印证 PLAN B「原 333.15 K 数据必须保留，不能折算成室温数据」。
- **AN（P3）**：`frequency_status = RF_ONLY`，且 `NON_STATIC_FREQUENCY_PRESENT`。
  印证「已有 0.01/1 MHz 证据不能直接替代」。
- **9 个零观测分子**与 PLAN B P4 清单逐一吻合。

**DMSO 的规模**：105 条观测、35 条在室温带、4 个来源 —— 但
`NO_CONDITION_VALID_PAIR`，即没有任何 (T, ε) 对来自同一次测量。
这正是 J04 揭示的核心问题。

**登记表不新增任何测量**：所有计数均可从 `measurement_ledger_v1.csv` 独立复现
（测试 `test_register_adds_no_measurements` 逐分子核对）。

---

## 九、下一步

### 需人工批准（阻塞 B04）

1. **G14 温度推定**：18 行 `model_ready=true` 但温度是推定值。
   改为 `model_ready=false` 会改变 v04 的可用样本数 → 属版本变更
2. **G15 `v04_epsilon` 污染**：修复骨架连接会改变 J03 产物 → 需决定是否新版本
3. **G12 压力分层**：改动 R219 冻结窗口语义

### 可自主推进

4. **G13 剩余 55 组冲突**：按 GVL 模式分批送四审
5. **B03 文献检索**：P0(DMC/DEC/SL) 优先
6. **G17**：把 R227 的 `model_ready` 标记与冲突状态对齐（只改标记，不改数据）

### 建议顺序

```
G17 标记对齐 → G13 冲突分批四审 → [批准] G14/G15/G12 → B04 → B05
```

---

## 附录：复现命令

```bash
cd "E:/Claude Code/电解质ML/电解质ML"
PY=.venv/Scripts/python.exe

$PY scripts/b01/build_reconstruction_exceptions.py
$PY scripts/b01/validate_source_independence.py
$PY scripts/b01/audit_pressure_heterogeneity.py
$PY scripts/b01/build_measurement_locator.py
$PY scripts/b01/audit_temperature_imputation.py
$PY scripts/b01/build_source_conflict_register.py
$PY scripts/b01/verify_measurement_reconstruction.py
$PY scripts/b01/build_b01_gate_status.py

$PY scripts/b02/build_admission_review_queue.py
$PY scripts/b02/build_consensus_gate.py
$PY scripts/b02/build_gvl_conflict_consensus.py

$PY -m pytest tests/test_b01_reconstruction.py tests/test_b02_gvl_conflict.py -q
```
