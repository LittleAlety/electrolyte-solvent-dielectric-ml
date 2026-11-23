# PLAN B 第一轮执行汇报

**项目：** Molecular Descriptor Validity & Liquid Dielectric Property Research
**仓库：** electrolyte-solvent-dielectric-ml
**执行主体：** AI 主智能体 + 四个独立审核子智能体
**轮次：** 第 1 轮（B00 → B01 部分 → B02 完成）
**时间：** 2026-11-23

---

## 1. 当前工作包

| 工作包 | 状态 | 说明 |
|---|---|---|
| **B00** 版本冻结与仓库取证 | ✅ **完成（7/7）** | 4 个只读脚本 + 8 个输出 |
| **B01** J04 测量级数据重建 | 🟡 **部分完成** | 核心账本已存在并核实；补齐 schema 符合性检查；未重建 |
| **B02** 四智能体准入审核 | ✅ **完成** | 真实启动 4 个独立子智能体；22 条 4/4 PASS |
| B03–B08 | ⬜ 未开始 | 依赖 B01 完成 |

**本轮未启动 DFT**（B06 条件授权未满足：B01 尚未通过）。

---

## 2. 已核实基线

PLAN B 第二章明确要求「报告基线不能直接视为已核实事实」。本轮逐条核实结果：

### 2.1 完全核实为真

| 项 | 报告值 | 实测值 | 状态 |
|---|---|---|---|
| 本地版本 | W49 | `HEAD = 7c58a22`（W49 主题） | ✅ |
| 公开版本 | W40 | `origin/main = 04b27e3`（W40-B） | ✅ |
| 独立论文包 | v1.3 | git 标签 `5aa3151`，14 个 paper 文件 | ✅ |
| J01 | `NO_GO_INSUFFICIENT_ELIGIBLE_DATA` | 4 条阻断码，含 `NO_ADMITTED_LABEL` | ✅ |
| J02A | 4/4 `REQUIRES_HUMAN_REVIEW` | `verdict_counts = {REQUIRES_HUMAN_REVIEW: 4}` | ✅ |
| J03 | 248 行完整分类 | 248 行，六类**逐类精确吻合** | ✅ |
| 底层测量 | 460 | `in_aggregate_window=true` = 460 | ✅ |
| 人工准入 | 0 | `N_admitted = 0` | ✅ |
| J01 身份命中 | 18/18 | 18 | ✅ |
| J01 条件可解析 | 4/18 | 4 | ✅ |
| J01 室温合格 | 3/18 | 3 | ✅ |
| J01 合格池独立来源≥2 | 0 | 0 | ✅ |
| J01 primary_k | 1 | 1 | ✅ |
| primary_k≥3 需 n≥21 | 21 | 21 | ✅ |

**J03 六类逐项核对：** 48 / 10 / 3 / 148 / 17 / 22，合计 248 — 报告值与实测值**完全一致**。

### 2.2 核实后需要更正的两处口径

**(a) `58` 不是「条件合格记录」**

PLAN B 把 58 列为「条件合格记录」。实测发现：58 是 J03 的**分类计数**，即
`PASSING_VERDICTS = {RAW_SINGLE_OBSERVATION, SINGLE_SOURCE_AGGREGATE}` = 48 + 10 = 58，
与「T 与 ε 是否来自同一次测量」是**两个不同判据**。

真正的条件配对行数是 **78**（J04 独立重算）。交叉验证：J03 自己的
`gap_aggregation_audit.csv` 里 `pair_present_in_single_observation=true` 也恰好是 78 行——
**J03 的数据列同意 78，只有 J03 的叙述文字写成了 58**。

差值 20 = 17 行 `AGGREGATION_UNDOCUMENTED` + 3 行 `MULTI_SOURCE_AGGREGATE`。

**影响：** 若 B01 按 58 做测量级重建，会**少算 20 行**可配对证据。B01 必须用 78。

**(b) `34` 未标口径**

34 是「v04 聚合窗口内」的来源文档数；全量为 **61**。这个限定已由
`provenance_repair_report.md` §7 自行声明，本轮独立复算确认。

### 2.3 J04 测量级账本核实

| 项 | 实测 | 核验 |
|---|---:|---|
| 全量测量 | **2065** | ✅ |
| 其中落在 v04 聚合窗口 | 460 | ✅ |
| static 0 Hz | 1630 | ✅ |
| 可追溯 | 2065/2065 | ✅ |
| 来源文档 | 61 | ✅ |
| 条件配对 有效/无效 | 78 / 170 | ✅ 合计 248 |

**J04 最重要的更正：** `460` 不是测量总数，而是窗口内观测数；全量为 **2065**。
J03 曾把 460 标为 `N_measurement`，是**约 4.5 倍的低估**。

---

## 3. 实际读取的文件

### 3.1 仓库与 git 层
- `git rev-parse / log / status / branch / remote / ls-files / show --numstat`
- `v1.3` 标签树（14 个 paper 文件）、5 个标签
- `paper/release_notes_v1.3.md`、`paper/submission_checklist.md`
- `data/dielectric_v03.csv`（sha256 核验）

### 3.2 冻结产物层（`outputs/confirm_2027/`）
- `intersections/`：J01 全部 9 个产物 + `joint_rebuild_receipt.json`、J02A 4 个、J02B 5 个
- `provenance_audit/`：J03 全部 6 个产物 + 回执
- `provenance_repair/`：J04 的 `measurement_ledger_v1.csv`(2065)、
  `condition_pair_validity_v1.csv`(248)、`aggregate_contribution_ledger_v1.csv`、
  `source_document_registry_v1.csv`(61)、`dataset_v05_manifest.json`、回执
- `identity_and_coverage/`：J05 `j05_summary.json`、`coverage_gap_registry.csv`(135)

### 3.3 基线层（`v56_standalone/`，仓库外）
- `reports/*R007*`（14 个）+ 6 个权威池/矩阵文件，共 20 个已哈希
- `reports/candidate_pool_C_R001.csv`(49)、`candidate_master_R001.csv`、
  `admission_matrix_R001.csv`(64)、`human_audit_worksheet_R007.csv`(40)

### 3.4 代码层
- `scripts/confirm_2027/` 全部 9 个生成器（重点审计
  `audit_gap_aggregation_provenance.py`、`build_provenance_preserving_dataset.py`）
- `probes/export_results_common.py`（复用其 `write_json_stable` 约定）

---

## 4. 修改和新增的文件

### 4.1 新增脚本（7 个）

| 文件 | 职责 |
|---|---|
| `scripts/b00/build_repo_snapshot.py` | 只读 git 快照 |
| `scripts/b00/verify_frozen_artifacts.py` | 冻结字节重算 + 哈希锁 |
| `scripts/b00/build_branch_reconciliation.py` | 分支清单 + W49 对账 |
| `scripts/b00/audit_paper_package.py` | v1.3 包清单 |
| `scripts/b01/audit_b01_schema_conformance.py` | 账本 schema 符合性 |
| `scripts/b02/build_admission_review_queue.py` | 审核队列组装 |
| `scripts/b02/build_consensus_gate.py` | 四审共识门禁 |

### 4.2 新增输出

**`outputs/b00/`（9 个）**
`repo_snapshot.json`、`branch_inventory.csv`、`w49_commit_reconciliation.md/.json`、
`j01_j02_j03_hash_lock.json`、`v56_r007_freeze_manifest.json`、
`paper_v13_inventory.csv/.json`、`b00_audit_report.md`

**`outputs/confirm_2027/provenance_repair/`（2 个，B01）**
`b01_schema_conformance.json/.md`

**`outputs/admission_v2/`（9 个，B02）**
`admission_review_queue.csv`(70)、`admission_review_queue_manifest.json`、
`reviewer_{1..4}_decisions.csv`(各 70)、`reviewer_{1..4}_report.md`、
`consensus_decisions.csv`(70)、`admission_status_machine.json`、`admission_gate_report.md`

### 4.3 新增测试（2 个，18 项）

- `tests/test_b00_repo_forensics.py`（10 项）
- `tests/test_b02_consensus_gate.py`（8 项）

### 4.4 明确未修改

- J01/J02/J03 全部 24 个冻结产物字节（已复算验证）
- `candidate_pool_C`、`candidate_master`、`dielectric_v04`、gap 表、`measurement_ledger_v1.csv`
- `v1.3` 标签及归档数据 `dielectric_v03.csv`
- 未合并 `master.in_49_preview` 与 `candidate_pool_C`（`merge_forbidden` 继续有效）
- 未 commit / push / release / merge / checkout

---

## 5. 核心代码

### 5.1 冻结校验：不信回执，重算字节

```python
# verify_frozen_artifacts.py
actual = sha256_file(fpath)          # 重算磁盘字节
expected = claimed.get(fname)        # 生成器自报的 sha256
if expected is None:
    entry["status"] = "UNCLAIMED_BY_RECEIPT"   # 判为失败, 不是通过
elif actual == expected:
    entry["status"] = "MATCH"
else:
    entry["status"] = "MISMATCH"
```

关键设计：`UNCLAIMED_BY_RECEIPT` 归入 `FAIL_UNCLAIMED_OUTPUT`。理由——没有任何生成器
背书的文件，恰好是第三方可静默替换而不被发现的文件。

### 5.2 四审共识：无多数投票

```python
# build_consensus_gate.py
if missing_reviewers:
    status = "AI_CONSENSUS_INCOMPLETE"
elif n_fail > 0:
    status = "AI_CONSENSUS_REJECTED"      # 任一 FAIL 即否决
elif n_hold > 0:
    status = "AI_CONSENSUS_HOLD"          # 任一 HOLD 即挂起 (3 PASS+1 HOLD ≠ PASS)
elif n_pass == 4:
    status = "AI_CONSENSUS_ACCEPTED"      # 仅 4/4 一致
```

### 5.3 队列自检：全空列即 FATAL

```python
_empty_critical = [c for c in _critical
                   if all(not (row.get(c) or "").strip() for row in queue)]
if _empty_critical:
    print(f"FATAL: columns empty on every row — broken join: {_empty_critical}",
          file=sys.stderr)
    return 3
```

这段代码是**本轮一次真实缺陷的直接产物**（见 §9 临时补救）。

---

## 6. 测试结果

| 测试集 | 结果 |
|---|---|
| `test_b00_repo_forensics.py` | **10 / 10 通过** |
| `test_b02_consensus_gate.py` | **8 / 8 通过** |
| 既有 confirm_2027 五套 | **183 / 183 通过** |
| **本轮相关合计** | **201 / 201 通过** |

**确定性验证：** B00 的 8 个输出在连续两次运行后**逐字节相同**（复用仓库既有的
`write_json_stable` 约定，而非另造一套）。

**冻结完整性验证：** 全部工作完成后重跑 `verify_frozen_artifacts.py`，仍为
J01 9/9、J02A 4/4、J02B 5/5、J03 6/6、输入 14/14、R007 20 文件，**OVERALL PASS**。

> 完整 `tests/` 全量运行超过 10 分钟超时（含大量重型 W01–W49 历史测试），
> 本轮改跑与本工作包相关的 7 个测试文件，201 项全通过。

---

## 7. 计算资源消耗

| 项 | 消耗 |
|---|---|
| CPU core-hours | **< 0.05** |
| 并发核心 | 1（脚本串行）+ 4（Reviewer 并行，纯 I/O 分析） |
| DFT | **0**（条件授权未满足，未启动） |
| 预算使用率 | ≈ 0.017% / 300 core-hours |

远低于 240 core-hours 的预算审核触发线。

---

## 8. 四智能体审核

### 8.1 独立性声明

本轮**真实启动了四个独立子智能体**（4 个 subagent，各自独立上下文）。
不是同一模型对一个问题的四次自我评价。

| Reviewer | 职责 | 文件 |
|---|---|---|
| R1 | 化学、物理与实验条件 | `reviewer_1_decisions.csv` |
| R2 | 来源文献、DOI、独立性 | `reviewer_2_decisions.csv` |
| R3 | 数据映射、身份、代码正确性 | `reviewer_3_decisions.csv` |
| R4 | 反向审计、反例 | `reviewer_4_decisions.csv` |

R1 明确声明**未读取** R3/R4 的输出。四人结论分布显著不同（PASS 从 22 到 31），
这正是不应使用多数投票的实证理由。

### 8.2 四审结果

| Reviewer | PASS | HOLD | FAIL |
|---|---:|---:|---:|
| R1 | 31 | 29 | 10 |
| R2 | 30 | 1 | 39 |
| R3 | 30 | 10 | 30 |
| R4 | 22 | 8 | 40 |

### 8.3 共识（4/4 PASS，无多数投票）

| 共识状态 | 记录数 |
|---|---:|
| `AI_CONSENSUS_ACCEPTED` | **22** |
| `AI_CONSENSUS_HOLD` | 8 |
| `AI_CONSENSUS_REJECTED` | 40 |
| `AI_CONSENSUS_INCOMPLETE` | 0 |

按测量去重（4 个测量在 3 条轨道重复出现）：**22 / 8 / 32**，结论一致。

**22 条 ACCEPTED 全部来自 R007 工作表轨道**，且全部满足
`j03_pair=true` 且 `j04_pair=true`。

### 8.4 四审共同发现的关键缺陷

**（1）队列构建缺陷 —— 三位 Reviewer 独立发现**

我的 `build_admission_review_queue.py` 第一版按 `aggregate_id`(`v04row-NNN`) 建键，
却用 `measurement_id`(`EPSV04-RNNN`) 查询，导致 `j04_condition_pair_valid`
在 **70/70 行全空**。`.get(key,'')` 把彻底的 join 失败伪装成「正常的空白」。

R2、R3、R4 **各自独立**发现了这一点。这是缺陷真实存在的交叉证据。已修复。

**（2）j04 不是独立门禁（R4）**

修复后 j04 与 j03 **70/70 行完全一致**——j04 只是同一计算的另一次表达。
任何「已核对 j04」的说法，若不回 `condition_pair_validity_v1.csv` 重建，等于没核对。

**（3）高压扫描污染 —— 四审独立发现，门禁集完全缺失**

`10.1021/je060248p` 是固定 298.15 K、0.1→300 MPa 的**压力依赖性研究**，贡献 54 行。
最硬证据 `EPSV04-R097`：8 条「观测」实为 101 kPa 到 300 MPa 的压力序列，
报告的 14.26 恰为 (14.07+14.45)/2 = 100–150 MPa 中点。`pressure_kpa` 为空，
队列不披露。同类 R040(+6.5%)、R046(+2.6%)。

**（4）合成中点**

至少 17 个测量的 ε 或 T 是两个真实观测的**精确算术中点**，其中 14 个 ε 值
在账本中不存在。破绽是尾数位数：`7.0695`、`2.40445`、`11.8861` 不是合理电容精度。

**（5）DMSO 真实缺陷比原假设更隐蔽**

PLAN B 假设「T 来自来源 A、ε 来自来源 D」。实测：**ε=46.05 是真实测量值**
（297.86 K，10.1021/je9010773），能通过原文抽查；**被伪造的是温度**——
298.0 K 恰为 (297.85+298.15)/2，无任何测量发生在该温度。ε=46.05 从未在 298.0 K 出现。
**只看 ε 的抽查会判它通过。**

**（6）来源独立性被系统性高估（R2）**

按 (inchikey, T, ε) 分组有 **27 组完全重复观测**，跨 8 对 DOI。
`n_contributing_sources` 数的是 **DOI 字符串**，不是独立实验。
注册表对全部 61 个文档标注 `independence = not_evaluated`。

**（7）一处验收判据是同义反复（R3）**

`no_synthetic_pair_marked_valid` 判据只检查 248 行中 69 行，且这 69 行全部为 true；
170 行 `pair_valid=false` 被过滤条件本身排除。该「通过」是**空洞的**。

**（8）R247 假阴性（三位独立发现）**

判 `PROVENANCE_INCOMPLETE`，但账本有精确匹配行（T=333.15, ε=56.09）。
FAIL 结论仍对，但**陈述理由错误**。`PROVENANCE_INCOMPLETE` 不是「来源确已丢失」的可靠信号。

**（9）0 Hz 攻击失败，属合法（R4）**

交叉表证明：`at zero frequency` = 1630 行全部零频率；
`at various frequencies` = 435 行全部非零频率。**0 Hz 是合法静态标记，不是占位符。**

### 8.5 审核完整性披露

- 队列在审核期间被修正一次（`1b701aaa…` → `02be88c7…`）。R1 独立检测到并用新字节
  重新校验全部 70 条决策；R2/R3/R4 的 `queue_id` 序列与最终队列逐条一致。
- R2 声明一处**主动规则偏离**：R247 按规则应 FAIL，因证据显示有真实贡献测量而判 HOLD，
  并公开标注。该记录最终共识为 REJECTED，不影响结论。

---

## 9. 临时补救

**本轮发生一次临时补救，已按 PLAN B 第四章生成记录。**

### `temporary_exception_record.json` #1

| 项 | 内容 |
|---|---|
| **触发** | 队列构建 join 缺陷导致 `j04_condition_pair_valid` 70/70 行全空 |
| **发现者** | R2、R3、R4 独立发现（非自查发现） |
| **性质** | 本轮自身代码缺陷，非冻结证据缺陷 |
| **处置** | ① 显式桥接 `v04row-NNN ↔ EPSV04-RNNN`（248/248 对齐验证）；② 新增「关键列全空即 FATAL」自检；③ 重建队列并重新校验三份已提交评审的 `queue_id` 序列 |
| **是否影响结论** | 否。三份评审的 `queue_id` 与最终队列逐条一致；且三位 Reviewer 均**未依赖**该空列，各自独立重建了 j04 |
| **是否修改冻结字节** | 否 |

**另有两次本轮内部代码修正**（非临时补救，不生成记录）：
- B00 校验器最初把 J01 回执指向 `j01k_rebuild_receipt.json`（那是 B-G0-J01K 另一个分析），
  导致 `J01 PASS` 但 `pass=0` 的**假阳性**。已改指 `joint_rebuild_receipt.json`，
  并把 `UNCLAIMED_BY_RECEIPT` 从「通过」改为「失败」。
- B02 队列的 `datetime.now()` 曾使 manifest 不可复现，已改用仓库既有 `write_json_stable`。

---

## 10. 数据缺口

| # | 缺口 | 影响 | 处置 |
|---|---|---|---|
| **G1** | `outputs/` 下 **0** 个文件被 git 跟踪 | 冻结证据无字节保护，`git clean -xdf` 即不可恢复 | 建议哈希锁另存受控位置（**需批准**） |
| **G2** | `v56_standalone` 在仓库工作树之外 | R007 基线无 git 保护 | 已建 20 文件外部哈希清单；清单本身需另存 |
| **G3** | `measurement_locator` 字段完全缺失 | 无法定位到论文表格/图/页码，回原文复核困难 | B01 登记为真实缺口，不补造 |
| **G4** | `extraction_method` 语义错位 | 账本 `method` 是**测量方法**，非**提取方法** | B01 判为语义缺口，不复制冒充 |
| **G5** | `epsilon_unit` 全为占位符 | 单位未在账本内显式声明 | B01 登记；相对介电常数无量纲的假设依赖上游 |
| **G6** | `submission_checklist.md` 工作区漂移未解释 | 不影响标签字节 | 登记待查 |
| **G7** | γ-戊内酯 36.1/36.9 冲突**未进审核队列** | R4 指出该冲突被排除而非裁决 | B01/B03 必须补入 |
| **G8** | 58/78 口径混淆 | 按 58 做 B01 会少算 20 行 | 已更正；B01 必须用 78 |
| **G9** | 来源独立性全域 `not_evaluated` | 无任何记录具备证据支持的独立性声明 | 限制 B07 来源聚类稳健性宣称 |
| **G10** | B01 未真正重建 | 本轮只做 schema 符合性，未重跑重建 | B01 下一轮补齐 |

---

## 11. 当前阶段门

### B00 门：**PASS（7/7）**

| 要求 | 状态 |
|---|---|
| 1. 确认本地 W49 | ✅ |
| 2. 确认 origin/main 的 W40 | ✅ |
| 3. 检查 5 个未推送提交及实际差异 | ✅ +42,515/−74 行，293 文件 |
| 4. 检查 v1.3 论文包 | ✅ 14 包内 / 22 包外 / 2 漂移 |
| 5. 锁定 J01/J02/J03 全部正式文件 | ✅ 24/24 MATCH |
| 6. 不自动合并分支 | ✅ 无 merge 代码路径 |
| 7. 不 commit / push / release | ✅ 无写 git 代码路径 |

**关键判断：** 本地 `main` 是 `origin/main` 的**纯快进**（ahead 5 / behind 0），
`merge-base == origin/main`。因此「对账 W49」不是合并决策，而是**推送决策**。
按第八章，推送需批准，本轮未推进。

### B01 门：**PARTIAL**

- 核心账本已存在且**核心数字全部核实**（2065/460/78/170/61）
- schema 符合性：14 个要求字段中 13 个存在，1 个真实缺口（`measurement_locator`）
- **未完成**：PLAN B B01 要求的重建脚本重跑、`reconstruction_exceptions.csv` 覆盖度核验

### B02 门：**PASS_PARTIAL**

- 四智能体**真实**独立审核完成
- **22 条 4/4 PASS**，8 条 HOLD，40 条 REJECTED
- 未使用多数投票；未伪造 `HUMAN_SIGNED`

### B04 前置条件判定

- `AI_CONSENSUS_ACCEPTED` = **22**（> 0），**技术上**允许构造候选池 v2 的候选行
- **但** B01 尚未 PASS，且四审揭示了高压污染、合成中点等系统性缺陷
- **建议：B04 暂缓**，先完成 B01 与缺陷修复

### DFT-A：**未启动**（条件未满足）

---

## 12. 下一步工作

### 优先级 P0（阻塞主线）

1. **补齐 B01**：重跑重建脚本，核验 `reconstruction_exceptions.csv` 覆盖度，
   补 `measurement_locator`（需回原文逐条核对）
2. **修复高压污染**：对 6 个受污染记录（R003/R040/R044/R046/R057/R097）建立
   压力分层，`pressure_kpa` 不得为空
3. **补入 γ-戊内酯冲突**（G7）到审核队列

### 优先级 P1

4. **B03 文献检索**（P0: DMC/DEC/SL；P1: DME/TEGDME/GBL/DMSO；可并行）
5. **修复同义反复判据**（`no_synthetic_pair_marked_valid`）

### 需人工批准才能推进

- **G1/G2 保护缺口**：涉及 `git commit` 或仓库外写入
- **`git push`**：W49 是纯快进，机械操作，但第八章要求批准
- **DFT-A**：需 B01 通过 + 候选池与协议冻结 + 四审 4/4 PASS

---

## 附录 A：复现命令

```bash
cd "E:/Claude Code/电解质ML/电解质ML"
PY=.venv/Scripts/python.exe

# B00（只读，可重复）
$PY scripts/b00/build_repo_snapshot.py
$PY scripts/b00/verify_frozen_artifacts.py
$PY scripts/b00/build_branch_reconciliation.py
$PY scripts/b00/audit_paper_package.py

# B01（只读）
$PY scripts/b01/audit_b01_schema_conformance.py

# B02（队列 + 门禁；Reviewer 输出为外部智能体产物）
$PY scripts/b02/build_admission_review_queue.py
$PY scripts/b02/build_consensus_gate.py

# 测试
$PY -m pytest tests/test_b00_repo_forensics.py tests/test_b02_consensus_gate.py -q
```

## 附录 B：环境

| 项 | 值 |
|---|---|
| Python | 3.12.14（`.venv`） |
| rdkit | 2026.03.6 |
| pandas | 3.0.6 |
| numpy | 2.5.3 |
| scikit-learn | 1.9.1 |
| 平台 | Windows-11 |

## 附录 C：本轮输出的完整哈希

见 `outputs/b00/j01_j02_j03_hash_lock.json`、
`outputs/b00/v56_r007_freeze_manifest.json`、
`outputs/admission_v2/admission_review_queue_manifest.json`。
