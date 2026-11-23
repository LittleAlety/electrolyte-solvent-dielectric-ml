# B00 审计报告：版本冻结与仓库取证

**工作包：** B00（PLAN B 第二仓库，第一个工作包）
**生成时间：** 2026-11-23
**执行主体：** AI 主智能体
**性质：** 只读取证。未执行 commit / push / release / merge / checkout，未修改任何冻结字节。

---

## 零、本轮结论摘要

| 项 | 状态 | 一句话 |
|---|---|---|
| 本地 W49 | ✅ 确认 | `HEAD = 7c58a22`，提交主题以 W49 开头 |
| origin/main 的 W40 | ✅ 确认 | `origin/main = 04b27e3`，主题以 W40-B 开头 |
| 5 个未推送提交 | ✅ 已逐条取证 | +42,515 / −74 行，293 文件 |
| 本地与 origin 的关系 | ⚠️ **关键发现** | 纯 **fast-forward**（ahead 5 / behind 0），不是分叉 |
| J01/J02/J03 冻结字节 | ✅ 24/24 文件哈希复算通过 | 见 §三 |
| v1.3 独立论文包 | ✅ 已定位并核验 | 它是 **git 标签**，不是目录 |
| 冻结产物的 git 保护 | ❌ **风险** | `outputs/` 下 **0** 个文件被 git 跟踪 |
| v56_standalone R007 | ⚠️ **风险** | 位于**仓库工作树之外**，git 完全不保护 |
| 冻结基线口径更正 | ⚠️ **新发现** | `58` 是 J03 的分类计数，**不是**条件配对行数（后者为 78） |

---

## 一、仓库快照（B00 要求 1、2、3）

**脚本：** `scripts/b00/build_repo_snapshot.py`
**输出：** `outputs/b00/repo_snapshot.json`

### 1.1 端点

| 项 | 值 |
|---|---|
| HEAD | `7c58a22f516d602ee495973cda51731c070e986c` |
| 分支 | `main`，upstream `origin/main` |
| origin/main | `04b27e3cdb20b7f85ca1588b63fd58219cfef437` |
| ahead / behind | **5 / 0** |
| remote | `https://github.com/LittleAlety/electrolyte-solvent-dielectric-ml.git` |

### 1.2 一个必须先讲清楚的结构事实

`PLAN B` 描述的执行对象是 **`electrolyte-solvent-dielectric-ml`**。磁盘上实际存在三层目录：

```
E:\Claude Code\电解质ML\              ← 外层工作目录（不是 git 仓库）
├── 电解质ML\                          ← 真正的 git 仓库（本报告的所有 git 操作都在这里）
│   ├── .git\
│   ├── outputs\confirm_2027\          ← J01/J02/J03/J04/J05 产物（未被 git 跟踪！）
│   └── scripts\confirm_2027\          ← 生成上述产物的脚本（未被 git 跟踪！）
├── v56_standalone\                    ← 公开基线 R007（在仓库工作树之外！）
└── v56_round1\                        ← 更早的轮次
```

**这带来两个独立的保护缺口，见 §四。**

---

## 二、W49 提交对账（B00 要求 3）

**脚本：** `scripts/b00/build_branch_reconciliation.py`
**输出：** `outputs/b00/branch_inventory.csv`、`w49_commit_reconciliation.md`、`w49_commit_reconciliation.json`

### 2.1 最重要的判断：这不是分叉，是快进

```
merge-base(origin/main, HEAD) = 04b27e3cdb20...  =  origin/main
```

两者相等 ⇒ **origin 上没有任何本地缺失的提交**。本地 `main` 是 `origin/main` 的**纯后继**。

**这个判断决定了后续动作的性质：**「对账 W49」在技术上不是一次**合并决策**，而是一次**推送决策**。PLAN B 第八章明确把 `git push` 列为「必须停止并请求批准」，所以本轮只登记状态，不推进。

### 2.2 五个未推送提交的实际差异

| # | SHA | 日期 | 主题 | 文件 | +行 | −行 |
|---|---|---|---|---|---|---|
| 1 | `7c58a22` | 2026-11-22 | W49 投稿包落地：venue 默认决断 + 形式适配 + 期刊模板 docx 重渲染 + 投稿四件 + week48 证据包 | 13 | 1,287 | 0 |
| 2 | `92d47b8` | 2026-11-21 | W48-B/C/D 收口：Ue 1997 三态落定、§4.6 欠账逐条终稿、venue 备忘录 | 22 | 1,712 | 0 |
| 3 | `151cf69` | 2026-11-21 | W48-A 收口：封树与干净重导 8/8 成立，包改钉版本态 | 3 | 421 | 0 |
| 4 | `e583242` | 2026-11-20 | W48-A 校验器修正：自身产出登记 + 导出前 purge + 补 H48a2 判据修正说明 | 1 | 71 | 9 |
| 5 | `78349a3` | 2026-11-20 | W47 封树：W21–W47 全部产物入库（AF-12 步①） | 254 | 39,024 | 65 |
| | | | **合计** | **293** | **+42,515** | **−74** |

**观察：** 5 个提交中 4 个的删除行数为 0，唯一的删除（−9 / −65）出现在校验器修正与封树调整。这与「纯增量式封树」的叙述一致，但**本报告不对其正确性背书**——那是代码审核（B02 Reviewer 3）的职责。

### 2.3 分支与标签

| 类型 | ref | tip |
|---|---|---|
| 本地 | `main`（当前） | `7c58a22` |
| 远程 | `origin/main` | `04b27e3` |
| 远程 | `origin/HEAD` → `origin/main` | — |

标签：`v1.0`、`v1.1`、`v1.2`、`v1.2.1`、`v1.3`（共 5 个）。

---

## 三、J01 / J02 / J03 冻结字节锁定（B00 要求 5）

**脚本：** `scripts/b00/verify_frozen_artifacts.py`
**输出：** `outputs/b00/j01_j02_j03_hash_lock.json`、`v56_r007_freeze_manifest.json`

### 3.1 方法：不信回执，重算字节

J01–J03 的每个生成器都会写一份 `output_sha256` 回执。但按 B01 原则「生成者自证不可作为验收依据」，本脚本**重新读取磁盘字节计算 sha256**，再与回执声明对账。不一致即判 FAIL，不是警告。

### 3.2 结果

| 分析 | 文件数 | 通过 | 失败 | 状态 |
|---|---:|---:|---:|---|
| J01（联合资格 + go/no-go） | 9 | 9 | 0 | ✅ PASS |
| J02A（40 行排除对账） | 4 | 4 | 0 | ✅ PASS |
| J02B（preview vs pool_C 溯源） | 5 | 5 | 0 | ✅ PASS |
| J03（248 行聚合溯源） | 6 | 6 | 0 | ✅ PASS |
| **合计** | **24** | **24** | **0** | ✅ |

上游输入（14 条，含 `candidate_pool_C`、`candidate_master`、`dielectric_v04`、`target_protocol`、`a_core_set` 等）逐条重算：**14/14 MATCH，0 缺失，0 漂移**。

### 3.3 一处必须在报告里说明的自身缺陷（已修复）

本轮第一版校验器把 J01 的回执指向了 `j01k_rebuild_receipt.json`。那是**另一个分析**（B-G0-J01K，温度带词汇对账），不是 J01。后果是 J01 的 6 个文件全部落入「回执未声明」分支，而当时的判定逻辑把「未声明」当作通过，于是打印出 `J01 PASS` 但 `pass=0`。

**这是一个典型的假阳性通过**——正是冻结校验最不能有的东西。已做两处修正：

1. 回执改指 `joint_rebuild_receipt.json`（J01 生成器 `build_joint_eligibility.py` 的真实回执），并把 J01 正式产物从 6 个补全到 9 个；
2. **`UNCLAIMED_BY_RECEIPT` 从「通过」改为「失败」**（新增状态 `FAIL_UNCLAIMED_OUTPUT`）。理由：没有任何生成器背书的文件，恰好是第三方可以静默替换而不被发现的文件。

修正后 J01 为 9/9 真通过。

---

## 四、两个冻结保护缺口（本轮最重要的风险发现）

### 缺口 A：`outputs/` 完全没有 git 保护

```
git ls-files outputs/  →  0 个文件
```

J01/J02/J03/J04/J05 的全部产物（含本报告的 `outputs/b00/`）**只存在于工作区磁盘上**。这意味着：

- 任何一次 `git clean -xdf`、磁盘故障、或误覆盖，都会**不可恢复地**销毁冻结证据；
- 冻结声明目前只有**叙事效力**，没有**字节效力**；
- 本轮的 `j01_j02_j03_hash_lock.json` 提供了可复核的哈希清单，**但清单本身也在未被跟踪的 `outputs/b00/` 里**——它保护不了自己。

**建议（需人工批准，本轮未执行）：** 将 `outputs/b00/j01_j02_j03_hash_lock.json` 与 `v56_r007_freeze_manifest.json` 复制到仓库外受控位置（或另行提交）。按 PLAN B 第八章，`git commit` 属需批准动作。

### 缺口 B：`v56_standalone` 在仓库工作树之外

`v56_standalone/` 是公开基线 R007 的载体，位于 `E:\Claude Code\电解质ML\v56_standalone`，即**仓库的父目录**，git 明确拒绝：

```
fatal: '../v56_standalone' is outside repository
```

其冻结因此**只能**由外部哈希清单保证。本轮已为其 20 个关键文件（全部 `*R007*` 报告 + 6 个权威池/矩阵文件）建立 `v56_r007_freeze_manifest.json`。

---

## 五、v1.3 独立论文包审计（B00 要求 4）

**脚本：** `scripts/b00/audit_paper_package.py`
**输出：** `outputs/b00/paper_v13_inventory.csv`、`paper_v13_inventory.json`

### 5.1 v1.3 是标签，不是目录

| 项 | 值 |
|---|---|
| 标签 | `v1.3` |
| 标签提交 | `5aa315169f22` |
| 日期 | 2026-09-28 |
| 包内 `paper/` 文件 | **14** |
| 工作区 `paper/` 中**不在包内**的文件 | **22** |

**这个区分是 B08 的前提。** `paper/` 目录下现在有 36 个文件，但只有 14 个属于 v1.3。其余 22 个是打标签之后才写的 v2/v3 草稿（`paper_zh_draft_v2.md` 136 KB、`paper_zh_draft_v3.md` 113 KB 等）。**任何把它们当作 v1.3 包内容的做法都会改变包的身份**，违反 PLAN B §2.1「不得覆盖 v1.3 投稿包」。

### 5.2 字节漂移

14 个包内文件中有 **2 个**与标签字节不一致：

| 文件 | 标签 sha256 | 工作区 sha256 |
|---|---|---|
| `release_notes_v1.3.md` | `0c7178381c1b…` | `5a34d807a63b…` |
| `submission_checklist.md` | `1094baf4a22a…` | `611babd68fd5…` |

`release_notes_v1.3.md` 的漂移是**已知且自证的**：该文件正文明确写着版本 DOI 由打标签之后的回填提交写入（"This line is written by the backfill commit, after the tag froze"）。`submission_checklist.md` 的漂移**尚未解释**，登记为待查项。

**注意：** 这两个漂移都在**工作区**，标签 `v1.3` 本身的字节未变。归档包完好。

### 5.3 归档数据摘要核验

`release_notes_v1.3.md` 声明 `data/dielectric_v03.csv` 的 sha256 为 `ff2142936e06…`。

实测：`ff2142936e06e04b329b70f8597574f75349e54ce876e9fff81309e6d35ccce4` — ✅ **完全一致**。

归档数据未被改动。

---

## 六、冻结基线口径核实（对 PLAN B 第二章「已报告结果」的逐条验证）

PLAN B §2 明确要求「以上均为报告基线，不能直接视为已经重新核实的事实」。本节即该核实。

### 6.1 已核实为真的项

| 报告值 | 实测 | 结论 |
|---|---|---|
| 本地 W49 + v56_standalone R007 | `7c58a22` + 20 个 R007 文件 | ✅ |
| 公开版本 W40 | `origin/main = 04b27e3`（W40-B） | ✅ |
| 独立论文包 v1.3 | 标签 `5aa3151`，14 文件 | ✅ |
| J01 = `NO_GO_INSUFFICIENT_ELIGIBLE_DATA` | `joint_go_nogo.json` 阻断码 `NO_ADMITTED_LABEL` 等 4 条 | ✅ |
| J02A = 4/4 `REQUIRES_HUMAN_REVIEW` | `verdict_counts.REQUIRES_HUMAN_REVIEW = 4` | ✅ |
| J03 = 248 行完整分类 | 248 行，六类合计 248 | ✅ 逐类精确吻合 |
| 底层测量 460 | `in_aggregate_window=true` 恰为 460 | ✅ |
| 人工准入 0 | `N_admitted = 0` | ✅ |

**J03 六类逐项核对（报告值 vs 实测）：**

| 分类 | 报告 | 实测 |
|---|---:|---:|
| `RAW_SINGLE_OBSERVATION` | 48 | **48** ✅ |
| `SINGLE_SOURCE_AGGREGATE` | 10 | **10** ✅ |
| `MULTI_SOURCE_AGGREGATE` | 3 | **3** ✅ |
| `PROVENANCE_INCOMPLETE` | 148 | **148** ✅ |
| `AGGREGATION_UNDOCUMENTED` | 17 | **17** ✅ |
| `COMPOSITE_CONDITION_UNMATCHED` | 22 | **22** ✅ |
| **合计** | **248** | **248** ✅ |

### 6.2 J01 关键结果逐条核实

| 项 | 报告 | 实测 | 结论 |
|---|---|---|---|
| 身份命中 | 18/18 | `n_identity_common_in_candidate_master = 18` | ✅ |
| 条件可解析 | 4/18 | `n_condition_resolvable = 4` | ✅ |
| 室温合格 | 3/18 | `n_room_band_qualified = 3` | ✅ |
| 人工 ACCEPT | 0 | `n_admitted = 0` | ✅ |
| 合格池独立来源组 ≥2 的分子 | 0 | `n_dual_or_more_independent_sources_in_qualified_pool = 0` | ✅ |
| primary_k | 1 | `primary_k_under_frozen_rule = 1` | ✅ |
| primary_k≥3 需 n≥21 | 21 | `n_required_for_primary_k_ge_3 = 21` | ✅ |

### 6.3 ⚠️ 一处必须更正的口径：`58` 不是条件配对行数

PLAN B §2 把 `58` 列为「条件合格记录」。本轮独立重算后确认：**这个标签是错的，但它不是数据错误，而是命名错误。**

**58 的真实来源**（J03 生成器 `audit_gap_aggregation_provenance.py` 第 93、709 行）：

```python
PASSING_VERDICTS = frozenset({V_RAW, V_SINGLE})   # = RAW_SINGLE_OBSERVATION + SINGLE_SOURCE_AGGREGATE
...
if row["verdict"] in PASSING_VERDICTS:
    qualified += 1
```

即 `58 = 48 (RAW_SINGLE_OBSERVATION) + 10 (SINGLE_SOURCE_AGGREGATE)`。它是**「裁决属于两类『干净』分类的行数」**，与「T 与 ε 是否来自同一次测量」是**两个不同的判据**。

**真正的条件配对行数是 78**（J04 独立重算）：

| 口径 | 值 | 定义 |
|---|---:|---|
| J03 `N_condition_qualified` | **58** | 裁决 ∈ {RAW_SINGLE, SINGLE_SOURCE} 的行数 |
| J04 `condition_pair_valid = true` | **78** | (T, ε) 可对应到**同一次观测**的行数 |
| 两者差 | 20 | 其中 17 行 `AGGREGATION_UNDOCUMENTED` + 3 行 `MULTI_SOURCE_AGGREGATE` |

**交叉验证：** 在 J03 自己的 `gap_aggregation_audit.csv` 里，`pair_present_in_single_observation=true` 恰好也是 **78** 行。也就是说 J03 的**数据列**同意 78，只有 J03 的**叙述文字**写成了 58。

**结论：** 78 是测量级配对的正确定义；58 应改称「干净分类行数」。这个区分在 B01（测量级重建）里至关重要，因为 78 才是可作为测量级证据入口的行数。**本轮不修改任何 J03 冻结字节**，只登记口径更正。

### 6.4 其余报告值

| 报告值 | 实测 | 说明 |
|---|---|---|
| 独立证据单位 34 | ✅ 34 | **口径限定**：这是「v04 聚合窗口内」的来源文档数；全量为 61 |
| 条件合格记录 58 | ⚠️ 见 §6.3 | 应为 58（分类口径）/ 78（配对口径） |

`34` 的口径限定已在 `provenance_repair_report.md` §7 自行声明，本轮独立复算确认。

### 6.5 测量级账本（J04）核实

| 项 | 值 | 核验 |
|---|---:|---|
| `measurement_ledger_v1.csv` 行数 | 2065 | ✅ |
| 其中落在 v04 聚合窗口 | 460 | ✅ 与报告一致 |
| static 0 Hz | 1630 | ✅ |
| `traceability_status = TRACEABLE` | 2065/2065 | ✅ 全部可追溯 |
| `source_document_registry_v1.csv` 文档数 | 61 | ✅ |
| `condition_pair_validity_v1.csv` 有效/无效 | 78 / 170 | ✅ 合计 248 |

**J04 最重要的更正已被账本证实：** `460` 不是「测量总数」，而是「v04 聚合窗口内的观测数」；全量测量为 **2065**。J03 曾把 460 标为 `N_measurement`，这是一个**量级错误**（低估约 4.5 倍），J04 已更正。

### 6.6 DMSO 案例复核（PLAN B B01 特别要求）

PLAN B 要求证明：DMSO 的 `298.0 K` 来自来源 A，而 `ε = 46.05` 来自来源 D，该条件组合是否真实存在于原始实验中。

**实测（`gap_aggregation_audit.csv`，`EPSV04-R031`）：**

| 字段 | 值 |
|---|---|
| `gap_T_K` | 298 |
| `gap_epsilon` | 46.05 |
| `v04_source_doi_count` | 4 |
| `contributing_sources` | `10.1016/j.fluid.2013.12.014`; `10.1016/j.tca.2017.03.018`; `10.1021/je400149j`; `10.1021/je9010773` |
| `sources_lost_in_gap` | 后 3 个 DOI（gap 表只保留了第 1 个） |
| `temperature_median_holders` | `298@493` |
| `epsilon_median_holders` | `46.05@483`; `46.05@484` |
| **`pair_present_in_single_observation`** | **false** |
| `verdict` | `COMPOSITE_CONDITION_UNMATCHED` |
| `verdict_reason` | `MEDIAN_T_AND_EPSILON_FROM_DIFFERENT_OBSERVATIONS` |

**结论：该组合不真实。** 温度中位数持有者是观测 #493，ε 中位数持有者是观测 #483/#484，**两者不是同一次测量**。这正是 PLAN B B01「核心原则 4」禁止的情形：温度中位数与介电常数中位数不能自动组成真实测量对。

同时确认 `MULTI_SOURCE_ROW_WITH_UNRESOLVED_ATTRIBUTION`：gap 表把 4 个来源压成 1 个，**丢失 3 个来源**。

DMSO 已正确进入 `REQUIRES_HUMAN_REVIEW` 队列（J02A），未被评为合格。

### 6.7 22 条 `COMPOSITE_CONDITION_UNMATCHED` 复核

J02A 复核的 4 个分子中，DMSO/TEGDME/DME/GBL 全部 `REQUIRES_HUMAN_REVIEW`，`pool_c_v2_construction_allowed = false`。

J03 中 22 条 `COMPOSITE_CONDITION_UNMATCHED` 与 J04 中 22 条 `pair_present_in_single_observation=false` 且非 `PROVENANCE_INCOMPLETE` 的行**一一对应**（148 + 22 = 170 = 全部无效配对行）。

**PLAN B B01 要求「22 条必须进入独立审核队列」—— 已确认它们在 B02 审核队列中，见 §七。**

---

## 七、B00 阶段门判定

| B00 要求 | 状态 | 证据 |
|---|---|---|
| 1. 确认本地 W49 | ✅ | `repo_snapshot.json::head.sha = 7c58a22` |
| 2. 确认 origin/main 的 W40 | ✅ | `origin_main_sha = 04b27e3` |
| 3. 检查 5 个未推送提交及实际差异 | ✅ | `w49_commit_reconciliation.json::unpushed_commits`（5 条，含逐条 numstat） |
| 4. 检查 v1.3 论文包 | ✅ | `paper_v13_inventory.json`（14 包内 / 22 包外 / 2 漂移） |
| 5. 锁定 J01/J02/J03 全部正式文件 | ✅ | `j01_j02_j03_hash_lock.json`（24/24 MATCH） |
| 6. 不自动合并分支 | ✅ | 脚本无 merge/checkout 调用路径 |
| 7. 不执行 commit/push/release | ✅ | 脚本无写 git 调用路径 |

**B00 状态：PASS（7/7）**

**但 B00 揭示的两个保护缺口（§四）是未关闭风险**，不阻塞 B01 启动，但必须在任何 `git clean` / 重装 / 迁移之前解决。

---

## 八、本轮实际读取与新增的文件

### 8.1 新增脚本（4 个）

| 文件 | 行数级 | 职责 |
|---|---|---|
| `scripts/b00/build_repo_snapshot.py` | ~230 | 只读 git 快照 |
| `scripts/b00/verify_frozen_artifacts.py` | ~330 | 冻结字节重算 + 哈希锁 |
| `scripts/b00/build_branch_reconciliation.py` | ~250 | 分支清单 + W49 对账 |
| `scripts/b00/audit_paper_package.py` | ~200 | v1.3 包清单 |

### 8.2 新增输出（8 个，全部在 `outputs/b00/`）

`repo_snapshot.json`、`branch_inventory.csv`、`w49_commit_reconciliation.md`、`w49_commit_reconciliation.json`、`j01_j02_j03_hash_lock.json`、`v56_r007_freeze_manifest.json`、`paper_v13_inventory.csv`、`paper_v13_inventory.json`、`b00_audit_report.md`（本文件）。

### 8.3 读取的既有文件（未修改）

- `outputs/confirm_2027/intersections/*`（J01/J02A/J02B 全部产物与回执）
- `outputs/confirm_2027/provenance_audit/*`（J03）
- `outputs/confirm_2027/provenance_repair/*`（J04）
- `outputs/confirm_2027/identity_and_coverage/*`（J05）
- `v56_standalone/reports/*R007*` 与 6 个权威池文件
- `paper/release_notes_v1.3.md`、`data/dielectric_v03.csv`

### 8.4 明确未做的事

- 未修改 J01/J02/J03 任何字节（哈希已复算验证）
- 未修改 `candidate_pool_C`、`candidate_master`、`dielectric_v04`、`gap` 表
- 未合并 `master.in_49_preview` 与 `candidate_pool_C`（`merge_forbidden=true` 继续有效）
- 未 commit / push / release / merge / checkout
- 未启动任何 DFT
- 未把 AI 审核结果写入任何 `HUMAN_SIGNED` 字段

---

## 九、计算资源消耗

| 项 | 消耗 |
|---|---|
| CPU core-hours | **< 0.01**（4 个只读脚本，纯 I/O + sha256） |
| 并发核心 | 1（串行） |
| DFT | 0（未授权，未启动） |
| 预算使用率 | ≈ 0.003% / 300 core-hours |

---

## 十、四智能体审核状态

**B00 本轮未触发四智能体审核。** 理由：B00 是只读取证工作包，其输出不构成科学主张，也不改变任何冻结状态。PLAN B §5 列举必须四方审核的对象是：J04 测量级重建、40 行准入、A18 新增证据、candidate_pool_v2、E1/E4/E6 确认性实验、最终论文证据包——B00 不在其中。

**但 B00 的输出（哈希锁、分支判断、58/78 口径更正）将作为 B02 四智能体审核的输入证据。**

---

## 十一、数据缺口登记

| # | 缺口 | 影响 | 处置 |
|---|---|---|---|
| G1 | `outputs/` 未被 git 跟踪 | 冻结证据无字节保护，可被 `git clean` 销毁 | 建议复制哈希锁到受控位置（需批准） |
| G2 | `v56_standalone` 在仓库外 | R007 基线无 git 保护 | 已建外部哈希清单；清单本身需另存 |
| G3 | `submission_checklist.md` 工作区漂移未解释 | 不影响标签字节，但工作区状态不明 | 登记待查，不阻塞 |
| G4 | 58 / 78 口径混淆 | 若按 58 做 B01，会少算 20 行可配对证据 | 已在本报告更正；B01 必须用 78 |
| G5 | `34` 未标口径即被引用 | 易被误读为「独立证据单位」总数 | 已限定为「窗口内来源文档数」，全量 61 |

---

## 十二、临时补救

**本轮无临时补救。** 未发生 DOI 失效、格式变化、文件损坏、聚合来源缺失等情况。未生成 `temporary_exception_record.json`。

（唯一一次自身缺陷——J01 回执指向错误——属于本轮内部代码修正，在 §3.3 完整披露，不属于对冻结证据的补救。）

---

## 十三、当前阶段门与下一步

**当前阶段门：B00 PASS（7/7），但带 2 个未关闭的保护风险（G1、G2）。**

**下一步工作（按 PLAN B 主线）：**

1. **B01（J04 测量级重建）** — 主要证据已存在（`measurement_ledger_v1.csv` 2065 行、61 来源文档、78 有效配对），本轮已核实其核心数字。B01 需要补齐 PLAN B 要求的**字段级完整性检查**：`measurement_locator`、`extraction_method`、`frequency_Hz`、`pressure` 等字段是否齐全，以及 `reconstruction_exceptions.csv` 是否覆盖全部不可恢复项。
2. **B02（四智能体准入审核）** — 需要**真实启动 4 个独立子智能体**。PLAN B 明确禁止「一个模型的四次自我评价冒充四智能体审核」。本轮已完成 B02 的输入准备（审核队列 = J02A 的 4 个分子 + 22 条 `COMPOSITE_CONDITION_UNMATCHED` + J04 恢复的候选证据）。
3. **B03 部分文献检索** 可与 B01/B02 并行。

**需要人工批准才能推进的事项：**

- 解决 G1/G2 保护缺口（涉及 `git commit` 或仓库外写入）
- 任何 `git push`（W49 是纯快进，推送是机械操作，但 PLAN B 第八章要求批准）
- 启动 DFT-A（需 B01 通过 + 候选池与协议冻结 + 四智能体 4/4 PASS）

---

## 附录 A：复现命令

```bash
cd "E:/Claude Code/电解质ML/电解质ML"
.venv/Scripts/python.exe scripts/b00/build_repo_snapshot.py
.venv/Scripts/python.exe scripts/b00/verify_frozen_artifacts.py
.venv/Scripts/python.exe scripts/b00/build_branch_reconciliation.py
.venv/Scripts/python.exe scripts/b00/audit_paper_package.py
```

全部只读，可重复执行；除 `outputs/b00/` 外不写任何路径。

## 附录 B：环境

| 项 | 值 |
|---|---|
| Python | 3.12.14（`.venv`） |
| rdkit | 2026.03.6 |
| pandas | 3.0.6 |
| numpy | 2.5.3 |
| scikit-learn | 1.9.1 |
| 平台 | Windows-11 |
