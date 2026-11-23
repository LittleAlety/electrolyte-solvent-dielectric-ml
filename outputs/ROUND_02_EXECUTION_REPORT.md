# PLAN B 第二轮执行汇报：B01 收口

**项目：** Molecular Descriptor Validity & Liquid Dielectric Property Research
**工作包：** B01（J04 测量级数据重建）收口 + B02 缺陷修复
**时间：** 2026-11-23
**性质：** 只读审计 + 新增版本化产物。未修改任何冻结字节。

---

## 零、本轮结论

| 项 | 结果 |
|---|---|
| B01 交付物 | ✅ **7/7 齐全**（补上 `reconstruction_exceptions.csv`） |
| B01 核心程序 | ✅ **5/5 齐全**（补上 2 个校验器） |
| B01 独立校验 | ⚠️ **13/14**，1 项 FAIL —— **该失败是正确的** |
| B01 阶段门 | 🔒 **CLOSED**（2 个真实阻断项） |
| B02 队列缺陷 | ✅ **已修复 2 处**（j04 连接 + 压力回填） |
| B02 共识结论 | ✅ **稳定**：22 ACCEPTED / 8 HOLD / 40 REJECTED |
| 冻结字节 | ✅ **24/24 MATCH，OVERALL PASS** |
| 测试 | ✅ **216/216 通过** |

---

## 一、本轮新增的 6 个程序

| 文件 | 职责 |
|---|---|
| `scripts/b01/build_reconstruction_exceptions.py` | 例外登记（不可恢复记录） |
| `scripts/b01/validate_source_independence.py` | 来源独立性校验 |
| `scripts/b01/audit_pressure_heterogeneity.py` | 压力异质性审计 |
| `scripts/b01/build_source_conflict_register.py` | 未决来源冲突登记 |
| `scripts/b01/verify_measurement_reconstruction.py` | 独立校验器（14 项检查） |
| `scripts/b01/build_b01_gate_status.py` | 阶段门状态汇总 |

新增测试：`tests/test_b01_reconstruction.py`（15 项）。

---

## 二、B01 交付物补齐

PLAN B B01 要求 7 个输出，此前缺 1 个：

| 文件 | 状态 |
|---|---|
| `measurement_ledger_v1.csv` | ✅ 已有（2065 行） |
| `source_document_registry_v1.csv` | ✅ 已有（61 文档） |
| `aggregate_contribution_ledger_v1.csv` | ✅ 已有（248 行） |
| `condition_pair_validity_v1.csv` | ✅ 已有（248 行） |
| `dataset_v05_manifest.json` | ✅ 已有 |
| `reconstruction_exceptions.csv` | 🆕 **本轮新建**（170 条例外） |
| `provenance_repair_report.md` | ✅ 已有 |

### 2.1 例外登记的三类区分

`reconstruction_exceptions.csv` 不是简单的"失败清单"，它把三类情况**分开记录**：

| 类别 | 数量 | 含义 |
|---|---:|---|
| `NO_CONTRIBUTING_MEASUREMENT` | 147 | 来源层**确实没有**窗口内观测，不可恢复 |
| `SYNTHETIC_PAIR_FROM_INDEPENDENT_MEDIAN` | 22 | 有贡献测量，但 (T, ε) 来自两次不同观测 |
| `SOURCE_LAYER_MISMATCH_FALSE_NEGATIVE` | **1** | 证书说没数据，实际**有**精确匹配观测 |

**第三类的存在是关键。** 147 + 22 + 1 = 170，与 `pair_valid=false` 的 170 行完全对应。

---

## 三、发现并修复的两个队列缺陷

### 3.1 缺陷一：j04 连接失败（B02 遗留）

第一版队列按 `aggregate_id`(`v04row-NNN`) 建键却用 `measurement_id`(`EPSV04-RNNN`) 查询，
`j04_condition_pair_valid` 在 **70/70 行全空**。

**修复：** 显式桥接（248/248 对齐验证）+ "关键列全空即 FATAL" 自检 + 覆盖率写入 manifest。

**修复后：** `j04` = true 30 / false 40，覆盖率 **100%**。

### 3.2 缺陷二：压力/相/频率静默空白

`admission_matrix_R001.csv` 只有 64 行，队列有 70 个 id，`.get(mid, {})` 让 29 行拿到空字典。
结果 `pressure_kpa` / `phase` / `frequency_mhz` 覆盖率只有 **44.3%**。

**这个缺陷的后果特别严重：** 空白的 `pressure_kpa` 会让审阅者把加压扫描记录读成常压记录。

**修复：** 从测量账本回填，并对多观测聚合**显式标记分歧**而非择一：

```
EPSV04-R097  pressure='MIXED[100|100000|101.3|150000|200000|250000|300000|50000]'
```

覆盖率从 44.3% → **87.1%**。

**这个修复让压力污染从"不可见"变成"队列里一眼可见"。**

---

## 四、B01 独立校验：14 项检查

**校验器设计原则：不复用被测代码，不读生成器结论。**

### 4.1 通过项（13）

| 检查 | 结果 |
|---|---|
| `measurement_id_unique` | 2065 唯一 |
| `in_window_count_reproduced` | 独立重算 = 460 |
| `in_aggregate_window_flag_agrees` | 账本标记与独立重算一致 |
| `contribution_counts_recompute` | 100 个 COMPLETE 聚合行贡献数全部复现 |
| `epsilon_median_recompute` | ε 中位数全部复现，0 漂移 |
| `no_synthetic_pair_marked_valid` | 78 个有效配对全部有共享持有观测 |
| `exception_register_covers_all_non_complete` | 170/170 覆盖 |
| `headline_n_measurements_2065` | ✅ |
| `headline_n_in_window_460` | ✅ |
| `headline_n_pair_valid_78` | ✅（非 58） |
| `headline_n_pair_invalid_170` | ✅ |
| `pair_validity_partition_complete` | 78 + 170 = 248 |
| `each_measurement_in_at_most_one_aggregate` | 无重复计入 |

### 4.2 唯一失败项 —— 而它**应该**失败

**`generator_acceptance_criterion_is_not_tautological`**

`build_provenance_preserving_dataset.py:437` 的验收判据：

```python
"no_synthetic_pair_marked_valid": all(
    r["condition_pair_valid"] == "true"
    for r in validity_rows
    if r["invalidity_reason"] in ("not_evaluated",)     # ← 问题在这
)
```

`invalidity_reason == "not_evaluated"` **只在 reasons 为空时成立**，也就是只在配对天然有效时成立。
该判据实际只检查 **69/248 行**（全部为 true），把 179 行排除在外——其中 **170 行是 false**。

**它不可能失败。** 这是同义反复，不是验收证据。

我的校验器把这一项判为 FAIL，而不是配合它假装通过。**这个 FAIL 是本轮最重要的产出之一。**

---

## 五、四审发现缺陷的独立复核

### 5.1 压力污染：四审说 6 个，实测 **15 个**

| 类别 | 数量 |
|---|---:|
| `AMBIENT_CONSISTENT` | 83 |
| `MIXED_AMBIENT_AND_PRESSURISED` | 12 |
| `PRESSURISED_ONLY` | 3 |
| `UNCLASSIFIED` | 2 |
| **受污染合计** | **15** |

**R097 逐行复核（决定性证据）：**

| 压力 (kPa) | ε |
|---:|---:|
| 100 | 13.06 |
| 101.3 | 13.06 |
| 50,000 | 13.63 |
| 100,000 | 14.07 |
| 150,000 | 14.45 |
| 200,000 | 14.77 |
| 250,000 | 15.06 |
| 300,000 | 15.33 |

报告值 **14.26 = (14.07 + 14.45) / 2**，即 100–150 MPa 的中点。

**这比四审报告的范围更大**——除 R097/R040/R046/R057 外，还发现
R003、R005、R006、R022、R031、R041、R044、R080、R088、R091、R095。

### 5.2 来源独立性：27 组重复，与 R2 完全一致

| 指标 | 实测 |
|---|---:|
| 跨文档完全重复观测组 | **27** |
| 涉及文档 | **9** |
| 纠缠文档对 | **8** |
| 受影响聚合行 | **28** |
| 注册表 `independence=not_evaluated` | **61/61** |

**R2 独立报告 27 组 / 8 对 —— 完全吻合。** 这是两个独立实现的交叉验证。

### 5.3 未决冲突：聚合层 1 组，观测层 49 组

| 层 | 冲突数 |
|---|---:|
| 聚合层（数据库行互相矛盾） | **1**（γ-戊内酯 36.1 vs 36.9） |
| 观测层（跨文献同分子同温分歧） | **49**（涉及 16 个分子） |

**两层必须分开报。** 聚合把分歧压成单个中位数，所以聚合层只能看到最严重的那个。
观测层才是真实分歧的规模——**49 组**。

**γ-戊内酯确认未入队**（`in_review_queue = false`），与 R4 的发现一致。

---

## 六、B01 阶段门：CLOSED

**两个阻断项：**

1. `generator_acceptance_criterion_is_not_tautological` 判 FAIL
2. 账本字段真实缺口：`measurement_locator`

### 为什么我不打开这道门

B01 的数据重建本身是**扎实的**：2065 条全部可追溯，78 条配对有效，170 条例外已登记，
所有算术独立复现、0 漂移。

但**扎实不等于可以放行**：

- 生成器的一条验收判据是空洞的 → 说明验收体系本身有漏洞
- `measurement_locator` 缺失 → 回原文复核的通道不完整
- 压力污染 15 行未修 → 修复需改动冻结窗口，属协议决策
- 49 组观测层冲突未裁决 → 进入 B05 会引入标签噪声

**按 PLAN B「不得以降低准入门槛解决数据不足」的原则，这道门保持关闭。**

### 对 B04 的明确结论

**B04 不得创建 candidate_pool_v2。** 即使 B02 有 22 条 4/4 PASS，
在下列问题解决前构造新池会把已知缺陷固化进新版本：

1. 压力污染 15 行
2. 合成中点（至少 17 个测量的 ε 不存在于账本）
3. γ-戊内酯冲突未裁决
4. 49 组观测层冲突未裁决

---

## 七、测试与资源

| 项 | 结果 |
|---|---|
| `test_b01_reconstruction.py` | **15/15** |
| `test_b00_repo_forensics.py` | 10/10 |
| `test_b02_consensus_gate.py` | 8/8 |
| 既有 confirm_2027 五套 | 183/183 |
| **合计** | **216/216 通过** |
| 冻结完整性 | **OVERALL PASS**（24/24 + 14 输入 + 20 R007） |
| CPU core-hours | **< 0.02**（累计 < 0.07） |
| DFT | **0**（未授权） |

---

## 八、数据缺口更新

| # | 缺口 | 状态 |
|---|---|---|
| G1 | `outputs/` 未被 git 跟踪 | ⬜ 未解决（需批准） |
| G2 | `v56_standalone` 在仓库外 | ⬜ 未解决（需批准） |
| G3 | `measurement_locator` 缺失 | 🔒 **B01 阻断项** |
| G4 | `extraction_method` 语义错位 | ✅ 已登记 |
| G5 | `epsilon_unit` 全占位符 | ✅ 已登记 |
| G6 | `submission_checklist.md` 漂移 | ⬜ 未查 |
| G7 | γ-戊内酯冲突未入队 | ✅ **已登记并量化**（仍未裁决） |
| G8 | 58/78 口径混淆 | ✅ 已更正 |
| G9 | 来源独立性全域未评估 | ✅ 已量化（27 组重复） |
| G10 | B01 未真正重建 | ✅ **本轮已收口** |
| **G11** | **生成器验收判据同义反复** | 🆕 **新发现，B01 阻断项** |
| **G12** | **压力污染 15 行未修** | 🆕 新发现，需协议决策 |
| **G13** | **观测层 49 组冲突未裁决** | 🆕 新发现 |

---

## 九、下一步

### 需人工批准（阻塞）

1. **G11 修复**：改写 `build_provenance_preserving_dataset.py:437` 的判据，
   使其能检查全部 248 行。这会改变 `dataset_v05_manifest.json` 的
   `acceptance_criteria` 字段 → 属版本变更
2. **G12 修复**：压力分层规则。改动 R219 冻结窗口语义 →
   改变 460/78/170 三个已报告计数 → **必须批准**
3. **G1/G2 保护缺口**：涉及 `git commit` 或仓库外写入

### 可自主推进（不阻塞）

4. **G3 `measurement_locator`**：回原文逐条核对，纯增量、不改冻结字节
5. **G13 冲突裁决队列**：把 49 组观测层冲突送入四审
6. **B03 文献检索**：P0(DMC/DEC/SL) 可与上述并行

### 建议顺序

```
G3 补 locator  →  G13 冲突入队四审  →  [批准] G11 判据修复
                →  [批准] G12 压力分层  →  B04  →  B05
```

---

## 附录：复现命令

```bash
cd "E:/Claude Code/电解质ML/电解质ML"
PY=.venv/Scripts/python.exe

# B01 全套（只读 + 新增版本化产物）
$PY scripts/b01/build_reconstruction_exceptions.py
$PY scripts/b01/validate_source_independence.py
$PY scripts/b01/audit_pressure_heterogeneity.py
$PY scripts/b01/build_source_conflict_register.py
$PY scripts/b01/audit_b01_schema_conformance.py
$PY scripts/b01/verify_measurement_reconstruction.py   # 预期返回 1（1 项 FAIL 是设计如此）
$PY scripts/b01/build_b01_gate_status.py

# B02 重建（修复后）
$PY scripts/b02/build_admission_review_queue.py
$PY scripts/b02/build_consensus_gate.py

# 测试
$PY -m pytest tests/test_b01_reconstruction.py tests/test_b02_consensus_gate.py -q
```
