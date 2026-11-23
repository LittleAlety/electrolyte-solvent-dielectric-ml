# PLAN B 第八轮执行汇报：B07 + B08 完成，最终交付

**工作包：** B07 跨域验证与筛选决策 + B08 `outputs/final/` 六件套
**时间：** 2026-11-23
**性质：** 项目主体收口。8/9 阶段门开启，B06/DFT 按授权规则未启动。

---

## 零、本轮结论

| 项 | 结果 |
|---|---|
| **B07** 8 个交付物 | ✅ **8/8 齐备** |
| **B08** `outputs/final/` 六件套 | ✅ **6/6 生成** |
| **阶段门** | **8/9 开启**（B06/DFT 未启动，符合授权规则） |
| 结论证据映射 | ✅ **19/19 条全部有据可查，0 缺失** |
| 测试 | ✅ **335/335 通过** |
| 冻结产物 | ✅ **OVERALL PASS** |
| 计算消耗 | **< 0.35** core-hours（上限 300） |
| D.F.T | **0 core-hours**（未启动） |
| HUMAN_SIGNED 写入 | **0** |
| Git commit/push | **0** |

---

## 一、B07 的核心发现：泄漏没有被演示出来

PLAN B B07 第一条审核点要求「Random split 不能替代跨家族测试」。
本轮把三种划分放在同一数据、同一模型上对比：

| 划分 | MAE | 泄漏风险 |
|---|---:|---|
| 随机 5 折（200 次重复均值） | 17.3192 | HIGH |
| 留一分子（LOMO） | 17.2375 | LOW |
| 留一家族（LOFO） | 17.2559 | NONE_BY_CONSTRUCTION |

**三者相差仅 0.4%。跨家族甚至比随机略好（−0.063）。**

### 这个结果很容易被误读

它**不是**好消息。如果连随机划分都拿不到好数字，说明：

> **问题不在划分方式，而在描述符本身不携带可迁移信号。**

**推论：换成更严格的划分只会让数字更差，不会更好。**
因此**不能**用「改用分组划分」来声称改进。

这与 E1（两模型均劣于常数基线）和 E4（指纹相同处误差仍达 19.5）完全一致。

### 来源聚类声明被拒绝

| 项 | 值 |
|---|---:|
| 本池来源 DOI | 16 |
| 成员 ≥3 的簇 | **1** |
| 做聚类检验所需 | **3** |
| **声明许可** | **❌ 否** |

两条阻断理由：
1. 只有 1 个来源簇达到 3 个成员，少于做聚类检验所需的 3 个
2. 来源独立性未评估（B01 发现 27 组逐字节相同的重复观测，涉及 8 对文档）

---

## 二、B07 八条审核点

| # | 审核点 | 状态 | 证据 |
|---|---|---|---|
| 1 | Random split 不能替代跨家族测试 | ✅ | 随机 17.32 vs 跨家族 17.26（差 −0.4%）|
| 2 | 同一分子不得跨训练/测试 | ✅ | 三种划分分子重叠均为 0 |
| 3 | 来源簇 <3 不得宣称聚类稳健 | ✅ **已拒绝** | 1/16 个簇达 3 成员 |
| 4 | 必须报告适用域覆盖率 | ✅ | 32%（68% 域外）|
| 5 | MAE 改善 ≠ 筛选收益 | ✅ | 噪声使 MAE 恶化但 regret 下降 |
| 6 | Top-k 必须固定 | ✅ | k = 3，冻结规则 |
| 7 | regret 必须用预先定义基准 | ✅ | 随机均匀筛选 |
| 8 | 样本量不足报 insufficient_power | ✅ | E6 状态 INSUFFICIENT_POWER |

---

## 三、B08：`outputs/final/` 六件套

| 文件 | 大小 | 内容 |
|---|---:|---|
| `B_FINAL_STATUS.json` | 2.8 KB | 9 个工作包状态、计算消耗、冻结状态 |
| `B_FINAL_MEASUREMENT_LEDGER.csv` | 682 KB | **2065 条测量**，每条带源文件 sha256 |
| `B_FINAL_CLAIM_EVIDENCE_LEDGER.csv` | 4.4 KB | **19 条结论**，全部有证据映射 |
| `B_FINAL_REVIEW.json` | 4.2 KB | 4 轮四审记录 + 发现缺陷清单 |
| `B_FINAL_REPORT.md` | 6.1 KB | 可读的完整叙述 |
| `B_FINAL_HASH_MANIFEST.json` | 34 KB | **180 个产物**的字节冻结 |

### 3.1 结论证据分级

PLAN B 第七章要求「所有论文结论均有证据映射」。19 条结论全部分级：

| 等级 | 数量 | 含义 |
|---|---:|---|
| `CONFIRMED_FROZEN` | 10 | 字节已验证，不会漂移 |
| `EXPLORATORY` | 5 | 仅说明性，不得作为发现引用 |
| `FOUR_AGENT_REJECT` | 2 | 四审拒绝 |
| `FOUR_AGENT_PASS` | 1 | 4/4 一致通过 |
| `INSUFFICIENT_POWER` | 1 | 测试跑了但不足以支持结论 |

**关键设计：** 所有来自 B05/B07 的建模结论都必须是 `EXPLORATORY` 或
`INSUFFICIENT_POWER`，测试会强制检查这一点（`test_exploratory_claims_are_not_dressed_as_confirmed`）。

### 3.2 前置于生成的安全检查

`build_final_package.py` 在写任何文件**之前**先运行冻结校验：

```python
if not frozen_ok:
    print("FATAL: frozen artifacts do not verify; refusing to emit final package")
    return 3
```

如果 J01/J02/J03 的字节被动过，最终包根本不会生成。

### 3.3 哈希清单的一个诚实修正

首版清单在测试重跑后失配（23 个文件）。原因是这些 JSON/MD 内嵌
`generated_at_utc`，任何重跑都会合法改变它们。

修正后的测试只检查两件**可检查**的事：
1. 没有跟踪的文件消失
2. **CSV 不得漂移**（CSV 带数据不带时间戳）

实测：CSV 漂移 0，缺失 0。

---

## 四、九个阶段门的最终状态

| 工作包 | 门 | 说明 |
|---|---|---|
| B00 版本冻结与取证 | ✅ OPEN | 4 脚本 + 9 输出 |
| B01 测量级重建 | ✅ OPEN | 18/18 独立校验 |
| B02 四智能体准入 | ✅ OPEN | 22 条 4/4 PASS |
| B03 A18 证据回填 | ✅ OPEN | 7/7 交付物 |
| B04 候选池更新 | ✅ OPEN | 22 条记录 / 22 分子 |
| B05 描述符实验 | ✅ OPEN | E1/E4/E6 全部完成 |
| **B06 物理信息与 DFT** | ❌ **未启动** | **条件授权未满足，0 core-hours** |
| B07 跨域验证 | ✅ OPEN | 8/8 交付物 |
| B08 最终交付 | ✅ OPEN | 六件套 |

**B06 未启动是正确的**：PLAN B 规定 DFT-A 需「B01 通过 + 候选池与协议冻结 +
四审 4/4 PASS」。虽然 B01 已过，但候选池仅 22 分子、四审在关键节点上是
HOLD/REJECT，因此条件未满足。**未越权使用任何计算资源。**

---

## 五、项目最终结论

> **在现有证据规模上，单分子结构与电子描述符已经到达其有效性边界。**
> 它们既不优于「预测均值」这一平凡基线，也不能在候选池中可靠地挑出高介电常数分子。
> 这不是模型调参失败，而是描述符信息含量的直接测量结果。

### 三个假设的回映

| 假设 | 证据 | 判定 |
|---|---|---|
| **H1** 误差有化学空间依赖性 | 家族间 MAE 差异 12.8–21.3，但域内外无系统差异 | 部分支持 |
| **H2** 更精确电子计算不必然带来更好预测 | ΔMAE 落在零分布内 | **支持** |
| **H3** 回归误差与筛选收益脱钩 | 噪声使 MAE 恶化但 regret 下降 | **支持且更严重** |

### 最有价值的单条证据

E4 的指纹检验：**4 个分子的最近邻 Tanimoto = 1.000**（描述符完全无法区分），
但平均绝对误差仍达 **19.48**。

这区分了两种失败：
- 「域外外推失败」→ 可以靠增加数据解决
- 「描述符无法分辨化学上不同的液体」→ **不能靠增加同类数据解决**

---

## 六、明确不能支持的宣称

- ❌ 电子描述符**普遍**无价值（n=22 只能说明本样本）
- ❌ 外推到 22 个分子之外的化学空间
- ❌ 「完整描述符体系」（X2/X3 从未计算）
- ❌ 任何确认性性能数字
- ❌ 来源聚类稳健性（1/16 个簇达 3 成员，且独立性未评估）
- ❌ 「改用分组划分带来改进」

---

## 七、仍然需要人工批准的事项

| # | 事项 | 为何需批准 |
|---|---|---|
| G14 | 温度推定 22 行改 `model_ready=false` | 改变 v04 可用样本数 |
| G15 | `v04_epsilon` 骨架连接污染修复 | 改变 J03 产物 |
| G1 | `outputs/` 未被 git 跟踪 | 需 commit 或仓库外写入 |
| G2 | `v56_standalone` 在仓库外 | 需仓库外写入 |
| — | `git push`（本地纯快进 5 个提交）| 第八章列为需批准动作 |

**这些都没有做，因为它们需要你的决定。**

---

## 八、测试与资源

| 项 | 结果 |
|---|---|
| `test_b07_decision_value.py` | **9/9** |
| `test_b08_final_package.py` | **11/11** |
| 全量相关测试 | **335/335 通过** |
| 冻结产物 | **OVERALL PASS**（24/24 + 14 输入 + 20 R007） |
| B01 独立校验 | **18/18 PASS** |
| CPU core-hours | **< 0.35**（上限 300，使用率 0.12%）|
| DFT | **0** |
| HUMAN_SIGNED | **0 次写入** |
| Git 写操作 | **0** |

---

## 九、复现完整链路

```bash
cd "E:/Claude Code/电解质ML/电解质ML"
PY=.venv/Scripts/python.exe

# 0. 冻结校验（必须最先，失败则停止）
$PY scripts/b00/verify_frozen_artifacts.py

# 1. B01 测量级重建与独立校验
$PY scripts/b01/verify_measurement_reconstruction.py
$PY scripts/b01/build_reconstruction_exceptions.py
$PY scripts/b01/audit_pressure_heterogeneity.py
$PY scripts/b01/audit_temperature_imputation.py
$PY scripts/b01/build_source_conflict_register.py
$PY scripts/b01/build_dataset_v06.py

# 2. B02 四智能体准入
$PY scripts/b02/build_admission_review_queue.py
$PY scripts/b02/build_consensus_gate.py

# 3. B03 证据回填
$PY scripts/b03/build_a18_gap_register.py
$PY scripts/b03/verify_nbs514_evidence.py
$PY scripts/b03/build_b03_registers.py
$PY scripts/b03/build_b03_consensus.py

# 4. B04 候选池
$PY scripts/b04/build_candidate_pool_v2.py

# 5. B05 描述符实验
$PY scripts/b05/build_feature_registry.py
$PY scripts/b05/run_e1_structure_vs_electronic.py
$PY scripts/b05/run_e4_domain_generalization.py
$PY scripts/b05/run_e6_screening_decisions.py
$PY scripts/b05/build_model_boundary_report.py

# 6. B07 筛选决策
$PY scripts/b07/run_b07_split_comparison.py
$PY scripts/b07/assemble_b07.py

# 7. B08 最终交付
$PY scripts/b08/build_final_package.py

# 8. 全量测试
$PY -m pytest tests/ -q
```
