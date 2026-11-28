# B720 / B721 外部数据恢复与准入审计报告

**日期**：2026-11-25  
**基线**：v7.1（commit `2947938`，工作区干净，50 条测试通过）  
**产出**：`data/external_raw/`、`outputs/b720_external_data/`  
**契约测试**：`tests/test_b720_external/test_v72_contracts.py`（36 条，含 v7.2 全部约束）

---

## 0. 结论摘要

| 数据集 | 是否恢复 | 原始行数 | 化合物数 | 与 239 重叠 | 新分子 | 准入判定 |
|---|---|---|---|---|---|---|
| LiquidBenchmark | ✅ 是 | 246 | 45 | 25 | 20 | `CANDIDATE_CORROBORATION` / `CANDIDATE_NEW_MOLECULE` |
| ComBat | ✅ 是 | 56 | 56 | 8 | 48 | **介电常数列被拒绝** |

**两个数字必须更正**：

- 计划记载「LiquidBenchmark 约 69 条」→ 实际 **246 行 / 45 个化合物**
- 计划记载「ComBat 约 15 条」→ 实际 **56 行 / 56 个化合物**，其中有 De 值的 29 条、同时有 De 和 DeT 的 20 条

---

## 1. B720 LiquidBenchmark 恢复

### 1.1 溯源

| 项目 | 值 |
|---|---|
| 仓库 | https://github.com/choderalab/LiquidBenchmark |
| 固定 commit | `215ca63a6651625afa96975eedb820f806eb59cd` |
| commit 日期 | 2017-02-03 |
| 仓库最后一次 push | 2017-02-03（此后未变） |
| 许可证 | **GPL-2.0** |
| 关联论文 | Beauchamp et al., *J. Phys. Chem. B* 2015 |

**固定 commit 的理由**：仓库已 8 年未推送，但 `tables/` 目录历史上被改动多次（存在 `tables_3_14`、`tables_4_8`、`tables_dec4_2014` 等快照目录）。若不钉 SHA，「LiquidBenchmark」指哪一版就不可复现。

**传输方式**：`raw.githubusercontent.com` 从本机连接被重置（curl 56），改用 GitHub contents API（base64 返回）。Pinned `?ref=<commit>` 保证与该 commit 的 git checkout 字节一致。

### 1.2 原始文件（未修改）

| 文件 | 字节 | SHA256 前缀 |
|---|---|---|
| `data_dielectric.csv` | 19156 | `030d8f762839fd3d` |
| `data_with_metadata.csv` | 43093 | `23d864cff6be091a` |
| `LICENSE` | 18027 | `a45d0bb572ed792e` |
| `README.md` | 310 | `451207b09d6dec85` |

**GPL-2.0 合规**：GPL-2.0 允许随许可证再分发，LICENSE 与数据同目录存放，文件本身未被改动亦未重新授权。

### 1.3 数据性质

- 列名 `Relative permittivity at zero frequency` → **零频率即静态**，无需假设
- 列名 `Temperature, K`、`Pressure, kPa` → 温度压力齐备
- **246 行全部为纯液体**（ThermoML 的混合物用分号分隔组分数，本文件无分号）

> **一处自查修正**：第一版准入脚本用「`components` 字段含逗号」判定混合物，把 45 行 `acrylic acid, methyl ester` 这类 IUPAC 名称误判为混合物。改为只认分号后，`REJECT_NOT_PURE_LIQUID` 从 45 降到 0。这正是「不要凭名称分类」的反面教材，已记录在脚本注释里。

### 1.4 来源性质：这是重复测量，不是新证据

| 项目 | 值 |
|---|---|
| 与 239 重叠的化合物 | 25 |
| 重叠的可比记录对（\|ΔT\|≤10 K） | 82 |
| **中位相对差** | **1.44%** |
| ≤5% 的比例 | 90.2% |
| ≤2% 的比例 | 54.9% |

**1.44% 的中位差**说明 LiquidBenchmark 与现有 239 引用的是同一批 ThermoML 原始测量。它是**重复测量一致性证据**，不是独立新证据。

**20 个新化合物**确实在 239 之外，但这些记录**没有逐行 DOI**（`ThermoML-derived`），因此无法核实其原始实验出处 —— 见 §3 的来源谱系处理。

---

## 2. B721 ComBat 恢复与拒绝

### 2.1 溯源

| 项目 | 值 |
|---|---|
| 仓库 | https://github.com/rashatwi/combat |
| 固定 commit | `caa1130df2b4feeb9eaafe1565af8e1a4283986a` |
| commit 日期 | 2023-04-15 |
| 许可证 | **MIT** |
| 论文 | Atwi & Rajput, *Patterns* 2023, doi:10.1016/j.patter.2023.100799 |
| 数据类型 | **SECONDARY_COMPILATION** |

### 2.2 字段来源（官网自述）

ComBat 官网对 `De` 的定义是：**"Dielectric constant of the solvent (from public databases & literature)"**，`DeT` 是 "Temperature in °C at which the dielectric constant was measured"。

即：`De` 是**二次整理值**，且**没有频率字段**。

### 2.3 决定性发现：`De` 不是静态介电常数

用冻结的 239 标签做探针：

| 分子 | ComBat `De` | 静态 ε（冻结） | 相对差 |
|---|---|---|---|
| **N-methylacetamide** | 3.97 | 178.47 | **97.8%** |
| **Acetonitrile** | 22.23 | 37.50 | **40.7%** |
| 1,2-二氯乙烷 | 10.45 | 10.36 | 0.9% |
| 环己烷 | 2.02 | 2.02 | 0.0% |
| 乙酸甲酯 | 6.68 | 6.68 | 0.0% |
| 二丁醚 | 3.08 | 3.11 | 0.8% |

**模式**：强极性液体差 40–98%，非极性液体差 <2%。

这正是「同一列混入了静态值与高频/光学值」的典型特征——非极性液体的静态与光学介电常数本来就接近，极性液体则相差数倍。

**判定 `REJECT_DEFINITION_MISMATCH`**：`De` 不能作为静态相对介电常数使用，无论其元数据多完整。

### 2.4 准入结果

| 状态 | 行数 |
|---|---|
| `REJECT_DEFINITION_MISMATCH` | 2 |
| `EXPLORATORY_INCOMPLETE_METADATA` | 27 |
| `REJECT_NO_EPSILON` | 27 |

**ComBat 没有任何一行进入训练集或评价池。** 契约测试 `test_combat_rows_never_enter_a_modelling_pool` 强制校验这一点。

---

## 3. 计划数字 vs 实测数字

| 项目 | 计划记载 | 实测 | 说明 |
|---|---|---|---|
| LiquidBenchmark 记录 | ~69 | **246 行 / 45 化合物** | 计划数字可能只统计了某个子集或某个历史版本 |
| ComBat 相关记录 | ~15 | **56 行**，29 有 De，20 有 De+DeT | 计划数字偏低 |
| 合计 | ~84 | **302 行 / 101 化合物** | — |

> 计划的 69+15 无法在恢复的数据中复现。可能来源：(a) 计划指的是去重后与 239 的交集；(b) 指的是某一历史快照子集。**本轮无法判定，标记为 `UNRESOLVED`**。

---

## 4. 对研究的意义

### 4.1 好消息

- 两个数据集**都成功恢复**，有固定 commit、许可证、SHA256 与字段字典
- LiquidBenchmark 的静态定义是**列名直接给出的**，不需要假设
- 25 个重叠化合物的中位差 1.44%，为「重复测量一致」提供了独立佐证

### 4.2 坏消息

1. **没有真正的新化学空间证据**：LiquidBenchmark 的 20 个新化合物没有逐行 DOI，无法当作「独立原始研究」。ComBat 的 48 个新化合物其介电常数列被拒绝。
2. **ComBat 完全不可用于介电常数研究**，这解释了为什么历史上「15 条 ComBat 记录」一直没能实际纳入。
3. **两者合计不能建立独立测试集**：叠加后仍然是「对已有分子的重复测量」为主。

### 4.3 对 v7.1 结论的影响

v7.1 说「LiquidBenchmark 与 ComBat 在本仓库不存在，标记 UNRESOLVED」。**本轮已解决这个 UNRESOLVED**：

- LiquidBenchmark：存在且已恢复，属性定义正确，但来源不独立
- ComBat：存在且已恢复，**介电常数列定义错误**，不可用于本研究

---

## 5. 复现

```bash
python scripts/b720_external/recover_liquidbenchmark.py
python scripts/b720_external/recover_combat.py
.venv/Scripts/python.exe scripts/b720_external/audit_external_conditions.py
```

全部需要网络。若网络不可用，已恢复的原始文件与 PROVENANCE.json 足以让下游分析独立运行。
