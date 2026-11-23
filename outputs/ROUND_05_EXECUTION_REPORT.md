# PLAN B 第五轮执行汇报：两组冲突裁决 + B04 候选池建成

**工作包：** B04-PRECONFLICT 冲突裁决 + B04 候选池 v2 + v06 缺陷修复
**时间：** 2026-11-23
**性质：** 修复四审发现的 v06 系统性缺陷；两组冲突四审完成；B04 首次建池

---

## 零、本轮结论

| 项 | 结果 |
|---|---|
| **两组阻断冲突四审** | ✅ 完成 |
| butan-2-ol | **4/4 PASS**（保留） |
| DMAc | **4/4 HOLD**（排除） |
| **v06 系统性缺陷** | 🔴 发现并修复（v06 从未读冲突表） |
| **B04 候选池 v2** | ✅ **22 条记录建成** |
| **B04 阻断项** | ✅ **清零** |
| 测试 | ✅ **282/282 通过** |
| 冻结产物 | ✅ **OVERALL PASS** |

---

## 一、上一轮的两个 Reviewer 执行失败但已落盘

R1 与 R3 的 subagent 在执行末尾报 failed，但**决策文件已完整写入**。
本轮核实后确认四份决策均有效、schema 合规，遂据此裁决。

| Reviewer | butan-2-ol | DMAc | 处置建议 |
|---|---|---|---|
| R1 化学/物理 | **PASS** | HOLD | KEEP / KEEP |
| R2 来源/DOI | **PASS** | HOLD | KEEP / NEEDS_PRIMARY |
| R3 代码/数据 | **PASS** | HOLD | KEEP / NEEDS_PRIMARY |
| R4 反向审计 | **PASS** | HOLD | KEEP / EXCLUDE |

**butan-2-ol：4/4 PASS。DMAc：4/4 HOLD。**

---

## 二、两组冲突的真实结构

### 2.1 butan-2-ol：冲突是**假象**

R2 与 R4 独立发现同一件事：所谓「4 个来源」其实是 **2 个实验**。

- `10.1021/je3007666` 与 `10.1021/je800593p` 在整个温度序列上**逐字节相同**
  （288.15–308.15 K 全部一致），是同一实验的两次发表。
- R4 进一步指出：分歧腿 `10.1016/j.fluid.2013.12.014` 自报
  **U = ±1.90（10.8%）**，区间 [15.70, 19.50] **包含** 16.60。
  也就是说，两值在各自声明的不确定度内**一致**。

**真正的问题在检测器，不在数据**：冲突检测用了平坦的 2% 阈值，
而一条 10.8% 不确定度的测量与一条 0.36% 的测量必然"冲突"。

R2 还发现 `je900503p` 也不是独立的：它在 293.15 K 与 303.15 K 复现
Klimaszewski 组的数值到末位（含相同的 u=0.06）。

**剩余分歧：1.05 σ（约 0.53 倍合成 95% U）→ 实际上是一致的。**

### 2.2 DMAc：冲突是**真的**，而且去重后更清楚

R2 的统计：两个 Sengwa 论文（同三位作者，署名顺序不同）给出**逐字节相同**的
37.72 ± 0.23。去重后剩两组：

- Sengwa 37.72 ± 0.23
- Świergiel & Jadzyn 38.67 ± 0.387

**残差 4.22 σ（2.11 倍合成 95% U）→ 真实且显著的冲突。**

**R4 的关键发现**：v06 的 37.72 是**重复计数造成的假象**。
因为 37.72 被算了两次、38.67 只算一次，中位数被拖向 37.72。
去重后中位数变成 **38.195**（+1.26%）。

R4 扫描 3,391 个文件后发现，外部数据只会**加宽**这个分歧
（Reaxys 给出 37.79–38.60，open_data_eps 加 37.8），两者都落在包络内，
**谁也不是标准答案**。

---

## 三、四审抓出的 v06 系统性缺陷（已修复）

### 3.1 v06 完全没读冲突登记表

R4 的指控：

> `dataset_v06` DOES NOT READ THE CONFLICT REGISTER AT ALL. 56 conflicts, all
> UNRESOLVED; exactly 2 map to model_ready=true — precisely these two. The 14
> other conflicted molecules were excluded for UNRELATED reasons.

**我独立验证：`grep -n "conflict" scripts/b01/build_dataset_v06.py` → 零命中。**

这是真实缺陷。v06 的 74 条 model_ready 里混进了 2 条未解决冲突行，
不是因为设计，而是因为它们**恰好没有别的阻断理由**。这个缺陷对任何
"只缺冲突这一个阻断理由"的分子都会复发。

**修复**：v06 现在显式读取冲突登记表**与四智能体裁决**，并区分：

| 裁决 | 处理 |
|---|---|
| 4/4 PASS（butan-2-ol） | **保留**，标 `CONFLICT_RESOLVED_PASS` |
| 4/4 HOLD（DMAc） | **排除**，标 `CONFLICT_UNRESOLVED` |
| 未裁决 | **排除**（保守） |

**结果**：model_ready 74 → **73**；`CONFLICT_UNRESOLVED` 排除 **15** 行。

### 3.2 没有按实验去重

R4：DMAc 的 37.72 被算了两次，中位数因此偏向错误一侧。

**修复**：v06 用并查集在 (molecule, T) 层面合并逐字节相同的文档，
新增 `n_independent_experiments` 列。DMAc 现在正确显示 **2** 个独立实验。

### 3.3 阻断理由重复

我的第一个修复版本把 `CONFLICT_UNRESOLVED` 加了两次
（`excl_reason` 一次 + 显式检查一次），导致计数虚高到 293。
**已修复并加测试锁定。**

---

## 四、B04 候选池 v2：22 条

### 4.1 三道独立的准入门

| 门 | 来源 | 要求 | 通过 |
|---|---|---|---:|
| B02 四智能体 | `consensus_decisions.csv` | `AI_CONSENSUS_ACCEPTED` | 22 |
| v06 模型可用 | `dataset_v06_model_ready.csv` | `model_ready == true` | 73 |
| 无未解决阻断 | `dataset_v06_exclusions.csv` | 未被排除 | — |

**交集 = 22 条**，恰好每分子一条。

### 4.2 ⚠️ 22 条不是数据集

这是本轮最需要强调的一点：

> **22 个分子、每分子 1 条记录，是筛选可行性集，不是训练集。**
> B05 必须以此为前提设计实验，**不得宣称统计功效充分**。

按冻结规则 `primary_k = max(1, ceil(22/10)) = 3`。
但 B07 必须报告这 22 个分子是否有足够独立来源做聚类检验
——考虑到 B01 已证明「独立来源数」在本数据集中只是**上界**，
这个条件很可能不满足。

### 4.3 温度未被折算

池内温度原始值全部保留：293.15、298、298.15、298.2、300.15、303.15。

闭区间测试：**[293.15, 303.15] 内 22 条，区间外 0 条**。
293.15 与 303.15 本身计入（闭区间），与 R219 冻结窗口口径一致。

### 4.4 冻结产物状态

| 产物 | 状态 |
|---|---|
| `candidate_pool_C` | **权威历史版本，字节未动**（sha256 已记录并测试） |
| `master.in_49_preview` | **历史 S4 折，`merge_forbidden` 继续有效** |
| J01 / J02 / J03 | **字节不变**，校验器 24/24 MATCH |

---

## 五、B04 阻断项清零

**修复前**：4 个阻断项（压力污染、观测层冲突 56 组、合成条件对、温度推定）

**修复后**：**0 个**

关键是冲突计数口径的修正。直接引用「56 组」会**高估**阻断范围：

```json
{
  "n_total": 56,
  "n_resolved_by_four_agent": 1,
  "n_blocking_model_ready": 0,
  "note": "总数扣掉已裁决与已不在 model-ready 的分子后才是 B04 的真实暴露"
}
```

56 组冲突中，1 组已被四审裁决（butan-2-ol），其余 54 组所涉分子
**本来就不在 model-ready 集合内**（被压力/配对/温度等更早的关卡排除）。

---

## 六、测试

| 项 | 结果 |
|---|---|
| `test_b04_candidate_pool.py` | **9/9** |
| `test_b01_dataset_v06.py` | **13/13** |
| `test_b03_consensus.py` | 7/7 |
| `test_b03_evidence_backfill.py` | 16/16 |
| `test_b03_gap_register.py` | 8/8 |
| `test_b01_reconstruction.py` | 21/21 |
| `test_b02_gvl_conflict.py` | 7/7 |
| `test_b02_consensus_gate.py` | 9/9 |
| `test_b00_repo_forensics.py` | 10/10 |
| 既有 confirm_2027 五套 | 183/183 |
| **合计** | **282/282 通过** |
| 冻结产物 | **OVERALL PASS** |
| B01 独立校验 | **18/18 PASS** |
| CPU core-hours | **< 0.03**（累计 < 0.15） |
| DFT | **0** |

---

## 七、新增的测试守护

本轮新增 6 个针对性测试，每个都对应一个**真实发生过的缺陷**：

| 测试 | 守护什么 |
|---|---|
| `test_conflict_register_is_actually_wired_in` | v06 必须读冲突表（防 R4 那个缺陷复发） |
| `test_adjudicated_verdict_decides_the_row` | 4/4 PASS 保留、4/4 HOLD 排除 |
| `test_duplicate_experiments_are_deduped` | 独立实验数不得等于原始行数 |
| `test_no_duplicate_blocking_reasons` | 阻断理由不得重复 |
| `test_pool_is_exactly_the_intersection` | 池必须是交集，不得是并集 |
| `test_v06_outputs_are_byte_reproducible` | v06 可复现 |

---

## 八、下一步

### 可自主推进

1. **B05 描述符实验**：E1（X0 vs X0+X1）、E4（跨家族 OOD）、E6（Top-k/regret）必做。
   但样本只有 22 个分子 —— **必须按探索性实验报告，不得包装成确认性结果**
2. **剩余 54 组冲突**：按本轮模式分批四审（虽当前不阻断 B04）
3. **B03 补检索**：EC/PC/FEC/VC 等现代溶剂需查 1951 年后文献

### 需人工批准

- **G14 温度推定 22 行**：改 `model_ready=false` 会改变 v04 可用样本数
- **G15 `v04_epsilon` 污染 3 行**：修复骨架连接会改变 J03 产物

### 建议顺序

```
B05 探索性 E1/E4/E6（22 分子，明确标注探索性） → B07 筛选决策 → B08 + outputs/final/
```

---

## 附录：复现命令

```bash
cd "E:/Claude Code/电解质ML/电解质ML"
PY=.venv/Scripts/python.exe

$PY scripts/b01/build_conflict_preanalysis.py
$PY scripts/b01/build_dataset_v06.py
$PY scripts/b01/build_b01_gate_status.py
$PY scripts/b04/build_candidate_pool_v2.py

$PY -m pytest tests/test_b04_candidate_pool.py tests/test_b01_dataset_v06.py -q
```
