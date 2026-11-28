# PLAN B v7.1 来源独立性与机制审计报告

**日期**：2026-11-25  
**基线**：v7.0（commit `09ccab8`，已冻结哈希）  
**产出目录**：`outputs/b710_evidence/`  
**契约测试**：`tests/test_b710_evidence/` — 29 条全部通过  
**数字来源**：本报告全部数字由 `scripts/b710_evidence/*` 从冻结产物重算，唯一汇总见各 JSON。

---

## 0. 证据等级汇总（先看这一节）

| 结论 | 等级 | 依据 |
|---|---|---|
| 239 分子实际由 **41 个原始来源**（40 篇文献 + 1 部 NBS 514 汇编）支撑 | `CONFIRMED` | `source_lineage.json` |
| **167/239 (69.9%) 分子只有 NBS 514 一个来源** | `CONFIRMED` | 同上 |
| 仅 **55/239 (23.0%)** 分子拥有 ≥2 个独立来源 | `CONFIRMED` | 同上 |
| LiquidBenchmark 与 ComBat 在本仓库中**不存在**，无法核对其 84 条记录 | `UNRESOLVED` | 全仓库检索无匹配文件 |
| 外部数据库新数据**不能**构成独立测试集 | `CONFIRMED` | 58 条重叠记录中仅 34 条条件可比 |
| ether 内部存在两个化学上不同的子族 | `CONFIRMED` | RDKit 结构规则，12/12 可复算 |
| ether 的 ρ=−0.135 是**池化假象**，且本身不显著（p=0.618） | `SUPPORTED` | `ether_subfamily_analysis.json` |
| 卤代烃偏置**可以**被无泄漏校准修正 | `SUPPORTED` | honest MAE 1.783 < 基线 1.952 |
| HCN 与 Triolein 是域外外推点 | `CONFIRMED` | NN 百分位 86.2 / 100.0 |
| Top-10 regret 的波动主要来自**候选池组成**，不是随机种子 | `CONFIRMED` | 种子 sd 6.01 vs 池化 CI [1.34, 32.13] |
| v6.0 的 2.938 与 v7.0 **可以**在协议层面比较 | `CONFIRMED` | 协议逐项核对一致 |
| xTB-on-DFT-geometry **不值得**全量补齐 | `SUPPORTED` | 方法/几何效应比 3.70，但绝对量 0.27 D |
| 当前结果**不能**表述为已获得跨实验来源泛化验证 | `CONFIRMED` | 见 §1.4 |

---

## 1. 来源独立性（最高优先级）

### 1.1 审计了哪些数据

| 数据层 | 记录数 | 说明 |
|---|---|---|
| measurement_ledger_b100 | 593 | core_thermoml 371 + nbs514_expansion 222 |
| epsilon_labels_b100 | 239 | 冻结的建模标签 |
| open_data_eps2 | 96 条 / 22 个 URL | CC-BY 外部补充 |
| pubchem_eps (PUG-View) | 41 条 / 41 个 URL | PubChem 文献转引 |

### 1.2 独立来源的真实数量

按"原始研究"而非"数据库"计数（规则 R1/R2 见 `source_lineage.json`）：

- **原始研究：41 个**（40 篇 ThermoML 文献 + 1 部 NBS Circular 514 汇编）
- **汇编计为 1 个来源**：NBS 514 贡献 222 条记录、113 个建模分子，但只是**一个**编辑来源
- 分子级覆盖：

| 来源数 | 分子数 | 占比 |
|---|---|---|
| 1（仅 NBS 514） | 167 | 69.9% |
| 1（单篇原始文献） | 17 | 7.1% |
| ≥2 | 55 | 23.0% |
| ≥3 | 23 | 9.6% |
| 跨来源一致（AGREE） | 35 | 14.6% |
| 单来源（含汇编） | 204 | 85.4% |

### 1.3 跨来源一致性

457 对可比观测（限制 |ΔT| ≤ 10 K）：

- 中位相对差 **4.85%**
- 仅 **51.4%** 的配对落在 5% 以内
- 结论：即使同一分子，不同实验室的静态 ε 也存在约 5% 的系统离散。这个量级本身就是任何"跨来源泛化"主张的分母。

### 1.4 关键判定：研究级 vs 分子级

这是本轮最重要的区分，v7.0 把两者混在一起了：

| 层级 | 判定 |
|---|---|
| 研究级 | `ENOUGH_PRIMARY_STUDIES`（41 ≥ 5） |
| **分子级** | **`MINORITY_INDEPENDENTLY_CORROBORATED`**（23.0% < 50%） |
| 约束来源 | **分子级覆盖，不是研究数量** |

**允许的主张**：在拥有 ≥2 独立来源的 55 个分子上可以做跨来源验证；167 个仅有汇编来源的分子支持建模，但**不支持**跨来源泛化主张。

### 1.5 LiquidBenchmark / ComBat

计划中提到"LiquidBenchmark 约 69 条、ComBat 约 15 条，合计约 84 条待去重"。

全仓库检索（`*.py` / `*.json` / `*.csv` / `*.md`，排除 `.git` 与虚拟环境）**未找到任何** LiquidBenchmark 或 ComBat 记录。唯一命中的是 scipy 源码注释中的 "combat" 字样（无关）。

**判定 `UNRESOLVED`**：这两个数据集不在本仓库中，无法核实其 69+15 条记录，也无法判断是否存在重复引用。需要用原始出处重新获取。这是本轮唯一无法完成的审计项。

### 1.6 外部数据能否建立独立测试集

审计了 61 个外部 URL 级来源：

| 项目 | 值 |
|---|---|
| 与 239 有分子重叠的来源 | 39 |
| 重叠记录数 | 58 |
| 温度可比（\|ΔT\|≤10 K） | 34 |
| 可比且一致（≤5%） | 30 |
| 可比分子数 | 30 |

- 全部 58 条重叠记录都是**对已有分子的重复测量**，没有引入新化学空间。
- 大多数记录缺频率，部分缺温度 → 31 个来源被标 `EXPLORATORY`，只有 30 个进入 `CANDIDATE_EXTERNAL`。
- **结论**：外部数据可用于**交叉印证**（30 个分子在 5% 内一致），但**不能**构成"未见过来源"的独立测试集。

### 1.7 Source OOD 结果

13 个来源拥有 ≥3 个分子，可做留一来源检验：

| 指标 | 值 |
|---|---|
| 可评估来源 | 13 |
| 优于常数基线 | 7 / 13 |
| 合并 OOD MAE | 5.91 |
| Study-cluster bootstrap 95% CI | [4.71, 7.31] |
| 重采样单位 | **原始研究**（非分子） |

- Bootstrap 用研究作为重采样单位（13 个 cluster ≥5，标为 `RELIABLE`，但 13 个仍偏少）。
- Source OOD MAE 5.91 与化学 OOD（LOFO mean 7.09）不同量级——再次确认这是两个不同问题。
- 严格 no-leak 版本与普通版本数值相同，因为留出集按分子定义，分子不可能通过其他来源进入训练。这一点在 `source_cluster_audit.json` 的 `separation` 字段中显式说明，避免被误读为"已做严格检验"。

---

## 2. ether 家族异质性

### 2.1 结构化分类（不依赖名称）

用 RDKit SMARTS 规则，`name_matching_used: false`：

| 子族 | 规则 | n |
|---|---|---|
| chlorinated_ether | 有 C–O–C 且有 ≥1 个共价 C–Cl（**优先**） | 2 |
| aliphatic_ether | CX4–O–CX4，无芳醚，无 Cl | 8 |
| other_or_ambiguous | 芳醚、混合或无法归类 | 6 |

12/12 可由 SMILES 重新计算（契约测试 `test_ether_subtypes_reproducible_from_smiles` 独立复跑规则并要求标签完全一致）。

### 2.2 为什么 ρ 是负的

| 层 | n | ε 中位 | MAE | bias | ρ | 置换 p |
|---|---|---|---|---|---|---|
| **ether 池化（原）** | 16 | 3.99 | 6.228 | +0.858 | **−0.135** | **0.618** |
| aliphatic_ether | 8 | 3.65 | 5.714 | +4.170 | 0.429 | 0.295 |
| other_or_ambiguous | 6 | 3.99 | 2.933 | +2.783 | 0.600 | 0.245 |
| chlorinated_ether | 2 | 21.90 | 18.166 | −18.166 | n/a | n/a |

**机制**（`SUPPORTED`，非 `CONFIRMED`）：

- 氯代醚 ε≈21–22.6，模型预测到 ~3.7 → **−18 ε** 的巨大低估；
- 脂肪醚 ε≈2.2–13.9，模型普遍**高估 +4 ε**；
- 两个方向相反的误差叠加，在池化后互相抵消，产生接近零或负的秩相关。

**但必须同时说明三点**：

1. 池化 ρ=−0.135 的置换检验 **p=0.618**，即这个"排序反转"在原样本量下**本身不显著**。v7.0 把它当作"唯一真实排序失效"是过度解读。
2. 氯代醚仅 **n=2**，无法做任何相关分析。该子族只能报告 ε 水平和误差，不能报告 ρ。
3. 两个可推断子族的 ρ（0.429 / 0.600）**p 值分别为 0.295 / 0.245，均不显著**。

**结论**：拆分**解释了**池化假象，但**没有**证明子族内部存在可用的排序能力。整体等级 `EXPLORATORY`。

### 2.3 正式 family 未被修改

- `orca_r2scan3c_descriptors.csv` 中这 16 个分子的 `family` 仍是 `ether`（契约测试强制校验）
- 子族只存在于新增列 `family_subtype_v1` / `_rule_version` / `_review_status`
- v7.0 的 LOFO 结果文件未被改动（哈希冻结）

---

## 3. E4 三种失败机制的收紧

### 3.1 卤代烃偏置：这次做了无泄漏检验

v7.0 的"去偏 MAE 1.69"用的是留出家族自己的标签，只能叫**诊断性分解**。本轮加入 honest 版本（K=4 折，在留出家族内部估计偏置，200 次重复）：

| 家族 | n | zero-shot | 诊断去偏 | **honest 校准** | 常数基线 | 判定 |
|---|---|---|---|---|---|---|
| **halocarbon** | 27 | 5.498 | 1.686 | **1.783** | 1.952 | **校准能力成立** |
| other_neutral_liquid | 35 | 3.608 | 2.655 | 2.740 | 1.472 | 诊断性 |
| alcohol_polyol | 32 | 3.972 | 3.893 | 4.053 | 6.901 | 校准能力成立 |
| ketone_aldehyde | 22 | 2.279 | 2.171 | 2.285 | 3.502 | 校准能力成立 |
| amine | 10 | 5.566 | 4.637 | 5.234 | 8.978 | 校准能力成立 |
| aromatic | 39 | 4.206 | 4.022 | 4.127 | 2.840 | 诊断性 |
| ester | 27 | 8.946 | 9.232 | 9.592 | 1.313 | 诊断性 |
| carboxylic_acid | 8 | 11.578 | 8.461 | 9.681 | 7.952 | 诊断性 |
| nitro | 12 | 6.346 | 5.593 | 6.260 | 5.777 | 诊断性 |
| ether | 16 | 6.228 | 5.799 | 6.223 | 4.736 | 诊断性 |
| nitrile | 7 | 19.768 | 21.909 | 26.154 | 21.199 | 诊断性 |

**卤代烃：`CALIBRATION_CAPABILITY_SUPPORTED`**。honest 校准 MAE 1.783 仍低于常数基线 1.952，说明"需要一个族级截距"是真实、可迁移的结论，而不是看了答案。

其余家族：4/11 校准能力成立，7/11 只是诊断性。诚实结论是——**只有部分家族的失败属于"可校准的系统偏置"**。

### 3.2 HCN 与 Triolein

| 分子 | 家族 | ε 真值 | 预测 | \|误差\| | 占家族 MAE | NN 百分位 |
|---|---|---|---|---|---|---|
| HCN | nitrile | 114.90 | 18.45 | 96.45 | **69.7%** | 86.2 |
| Triolein | ester | 3.20 | −56.28 | 59.48 | 24.6% | **100.0** |
| Dioctyl sebacate | ester | 4.01 | −17.05 | 21.06 | 8.7% | 98.3 |
| Trifluoroacetic acid | carboxylic_acid | — | — | 20.10 | 21.7% | 97.1% |
| 3-Chloro-1,2-epoxypropane | ether | 22.60 | 3.85 | 18.75 | 18.8% | 93.3% |

- **HCN**：ε=114.9 是全库最大值，NN 百分位 86.2（不算极端），但目标值本身极端。**这是目标外推，不是结构外推**。
- **Triolein**：NN 百分位 **100.0**，是全库最孤立的点（900 Da 甘油三酯，训练集中无近邻）。**这是结构外推**。
- 去掉最差点后：nitrile 19.77 → **6.99**；ester 8.95 → **7.00**。
- **ester 不能归因于 Triolein 一个分子**：去掉后 MAE 仍 7.00，远高于其常数基线 1.31。
- 契约测试 `test_outliers_are_retained_in_headline_metrics` 用逐分子残差重算家族 MAE，强制要求与 headline 数字一致（容差 1e-3），防止有人事后删点。

### 3.3 修正后的失败机制分类

| 家族 | 主要机制 | 次要机制 |
|---|---|---|
| halocarbon | 可校准系统偏置（93.8%） | 族内 ε 离散小（sd 2.25） |
| other_neutral_liquid | 可校准系统偏置（88%） | 族内 ε 离散小（sd 2.62） |
| nitrile | 单点域外外推（HCN，占 69.7%） | 样本量 n=7 |
| ester | 单点外推 + 真实排序损失 | 族内 ε 离散极小（sd 1.57） |
| carboxylic_acid | 可校准偏置（57%）+ 排序损失 | n=8 |
| ether | 结构分类异质性 | ρ 本身不显著 |
| aromatic | 族内 ε 离散小 + 轻微偏置 | — |
| alcohol_polyol / amine / ketone_aldehyde | 迁移良好 | — |

---

## 4. E6 筛选可靠性（20 种子 + 分子 bootstrap）

### 4.1 三种不确定性（严格分开）

**A. 算法随机性**（20 个种子，仅扰动 lambda 选择的折划分）：

| 特征块 | MAE ± sd | regret 中位 | IQR | p95 | Top-10 重叠 |
|---|---|---|---|---|---|
| X0 + μ²/Vm | 4.3385 ± **0.0784** | 11.270 | [5.61, 17.15] | 17.561 | 0.784 |
| X0 + r²SCAN-3c 电子 | 5.1172 ± 0.0368 | 14.276 | [14.28, 14.28] | 14.276 | **1.000** |
| X0 + xTB 电子 | 5.7124 ± 0.1206 | 16.096 | [15.61, 20.11] | 31.116 | 0.705 |
| X0 结构 | 7.0313 ± 0.0517 | 35.138 | [35.14, 35.66] | 37.721 | 0.873 |

**B. 分子抽样不确定性**（候选池有放回重抽样 + 完整重训练 + 重排序）：

| 特征块 | regret 中位 | 95% CI | 全范围 |
|---|---|---|---|
| X0 + μ²/Vm | 3.973 | **[1.34, 32.13]** | [1.0, 44.4] |
| X0 + r²SCAN-3c 电子 | 13.739 | **[3.38, 50.79]** | [1.7, 70.5] |

**C. 来源不确定性**：见 §1.7（合并 OOD MAE 5.91，CI [4.71, 7.31]，重采样单位是研究）。

三者不可合并成一个标准差，`e6_stability_v71.json` 的 `uncertainty_kinds.warning` 已显式声明。

### 4.2 关键发现：波动主要来自候选池，不是随机种子

- μ²/Vm 的**种子间**相对离散 0.537（sd/中位）
- μ²/Vm 的**池化** 95% CI 是 [1.34, 32.13]，跨度 **24 倍**
- MAE 的相对离散仅 **0.018**（sd/均值）

**结论**：Top-k regret 的不稳定性**压倒性来自候选池组成**，而不是评价流程的随机种子。v7.0 把它表述为"种子敏感"是不完整的——种子只是让这个问题显现出来。

### 4.3 回答计划中的四个问题

| 问题 | 答案 |
|---|---|
| 哪种特征块 MAE 最好？ | μ²/Vm（4.34），且排序在所有种子上稳定 |
| 哪种特征块 regret 最低？ | μ²/Vm（中位 11.27），但 CI 极宽 |
| 哪种特征块 regret 最稳定？ | **r²SCAN-3c 电子**（sd 恒为 0，因为 lambda 恒为 100，排序确定） |
| MAE 改善是否对应排名改善？ | 是（`mae_and_regret_agree_on_winner: true`），但这只在中位数层面成立 |

**Top-k 推荐可靠性：`false`**（`topk_recommendation_reliable: false`）。μ²/Vm 的 regret 相对离散 0.537 超过 0.5 阈值。

### 4.4 v6.0 的 2.938 能否比较

逐项核对（`e6_stability_v71.json` 的 `evaluation_consistency`）：

| 项目 | v6.0 | v7.1 | 一致 |
|---|---|---|---|
| 候选池 | 239 | 239 | ✅ |
| 评价 | 嵌套 LOO，逐折内 5 折 CV 选 lambda | 同 | ✅ |
| 标准化 | 训练折内 | 同 | ✅ |
| 模型 | ridge + 截距 | 同 | ✅ |
| Top-k | 10 | 10 | ✅ |
| regret 定义 | oracle 均值 − 模型 top-k 均值 | 同 | ✅ |

**可以比较**（`CONFIRMED`）。但注意：v7.1 的 20 种子中位是 11.27、池化中位 3.97，**2.938 落在分布的低端**，不是典型值，也不能作为"稳定压到 3"的证据。

### 4.5 实现层面的诚实披露

纯 Python 一次嵌套 LOO 需 35 秒，20 种子 × 4 特征块 + 500 次 bootstrap 约需 20 小时。改用 numpy 闭式解后每次 2.86 秒，并在任何数字输出前做了一次**与纯 Python 参考实现的逐点比对**：

- 40 分子子集，最大绝对差 **3.73e-14**（`self_check_vs_pure_python.passes: true`）
- 该比对结果写入 JSON，契约测试 `test_e6_numpy_impl_verified_against_reference` 强制要求 `passes: true` 且差值 < 1e-9

---

## 5. xTB-on-DFT-geometry（补齐 2×2 矩阵）

### 5.1 执行情况

- 12 分子预检，GFN2-xTB `--sp`（**不重新优化**）在 r2SCAN-3c 几何上
- 12/12 `normal termination`
- 原子顺序 12/12 与输入几何一致（契约测试强制）
- 坐标偏移 0.011–0.157 Å（即 DFT 相对 xTB 几何的弛豫量）
- 输入文件 SHA256 已记录，可复算

### 5.2 2×2 结果（偶极，单位 D）

| 分子 | xTB@xTB | xTB@DFT | DFT@xTB | DFT@DFT |
|---|---|---|---|---|
| 1,2-butanediol | 2.180 | 2.499 | 1.953 | 2.182 |
| tetralin | 0.864 | 0.786 | 0.775 | 0.796 |
| 1,1-diethoxyethane | 2.248 | 2.413 | 1.859 | 1.983 |
| ethanol | 1.721 | 1.782 | 1.503 | 1.549 |
| diethyl carbonate | 0.506 | 0.381 | 0.288 | 0.196 |
| amyl acetate | 2.357 | 2.257 | 1.906 | 1.863 |
| ethylenediamine | 0.495 | 0.605 | 0.251 | 0.343 |
| 1,3-pentadiene | 0.707 | 0.715 | 0.761 | 0.776 |
| propylene glycol dinitrate | 4.701 | 4.638 | 4.043 | 3.982 |
| tetrachloroethane | 0.000 | 1.621 | 1.803 | 1.714 |
| acetonitrile | 3.852 | 3.869 | 4.055 | 4.078 |
| 2-butanone | 3.256 | 3.319 | 2.863 | 2.910 |

### 5.3 效应分解

| 效应 | 均值 | MAE |
|---|---|---|
| 方法效应 @ xTB 几何 | −0.069 | 0.412 |
| 方法效应 @ DFT 几何 | −0.209 | 0.272 |
| 几何效应（xTB） | +0.167 | 0.228 |
| 几何效应（DFT） | +0.026 | 0.074 |
| 交互项 | −0.140 | — |

**方法/几何效应比 = 3.70**

### 5.4 是否值得全量补齐

**判定 `SUPPORTED`：不值得。**

理由：
- 比值 3.70 确实 < 10（脚本的自动阈值），形式上触发了"值得扩展"
- **但绝对量级极小**：12 个分子的方法效应 MAE 只有 0.27 D，几何效应 0.23 D，两者都在 v7.0 的 239 分子方法效应（0.43 D）之下
- 唯一的显著例外是四氯乙烷：xTB@xTB = 0.000（对称），xTB@DFT = 1.621——一个退化几何被打破，这是单点特例而非系统趋势
- 契约测试与 §4.2 已确认几何效应在 239 分子尺度比方法效应小一个量级

**结论**：12 分子预检足以关闭这个矩阵格。继续扩展到 239 会消耗资源但不改变任何研究结论，符合计划中"不要为了让矩阵形式完整而消耗大量资源"的约束。

**注意**：脚本自动给出的 `extend_to_full_239: true` 是基于固定阈值 10 的机械判断。我在此明确推翻该自动建议，理由如上。该矛盾保留在 JSON 中，不做篡改。

---

## 6. 十条验收问题的直接回答

| # | 问题 | 回答 | 等级 |
|---|---|---|---|
| 1 | 是否找到真正独立的外部实验来源？ | 找到 39 个有重叠的外部 URL 级来源，但全部是对已有分子的**重复测量**，无新化学空间 | `CONFIRMED` |
| 2 | 来源独立性是否改善？ | **没有实质改善**。167/239 仍只有单一汇编来源，≥2 独立来源的分子仅 55 个（23.0%） | `CONFIRMED` |
| 3 | ether 是否存在两个不同子族？ | 是。氯代醚 n=2（ε≈22）与脂肪族醚 n=8（ε≈3.7）在结构上和 ε 上都清晰分离 | `CONFIRMED` |
| 4 | 子族拆分是否改善跨家族解释能力？ | **解释了池化假象，但未证明子族内可用排序**。两个子族 ρ 均不显著（p=0.295/0.245） | `EXPLORATORY` |
| 5 | 卤代烃偏置是否经过无泄漏校准验证？ | **是**。honest K=4 折校准 MAE 1.783 < 常数基线 1.952 | `SUPPORTED` |
| 6 | HCN 和 Triolein 是否确实域外？ | HCN 是**目标值外推**（ε=114.9，NN 86.2 百分位）；Triolein 是**结构外推**（NN 100.0 百分位） | `CONFIRMED` |
| 7 | E6 regret 高波动主要来自什么？ | **候选池组成**（CI 跨度 24 倍），不是随机种子（sd/中位 0.54） | `CONFIRMED` |
| 8 | v6.0 的 2.938 能否比较？ | **能**（6 项协议逐项一致），但属分布低端，非典型值 | `CONFIRMED` |
| 9 | 是否值得全量补齐 xTB-on-DFT？ | **不值得**。方法/几何比 3.70 但绝对量 0.27 D，远小于影响结论的量级 | `SUPPORTED` |
| 10 | 距可靠论文级结论还缺什么？ | 见 §7 | — |

---

## 7. 距离论文级结论还缺什么

**必须补的（阻塞）**
1. **分子级来源覆盖**：167 个仅汇编来源的分子无法支撑跨来源主张。需要为这些分子找到第二独立来源，或把结论范围显式限定在 55 个已印证分子上。
2. **LiquidBenchmark / ComBat 核实**：计划提到的 84 条记录在本仓库不存在。要么找到原始文件，要么从计划中删除这一项。

**应当补的（重要但不阻塞）**
3. **ether 子族样本量**：氯代醚 n=2 完全无法推断。要下子族结论需要补充至少 5 个氯代醚。
4. **来源 OOD 的来源数**：13 个 cluster 偏低，CI 仍宽。

**已经关闭的**
5. Top-k regret 的稳定性机制（候选池主导）——已定量，无需追加。
6. xTB-on-DFT-geometry 矩阵格——预检足够，不再扩展。

---

## 8. 交付件

| 路径 | 内容 |
|---|---|
| `outputs/b710_evidence/final/v70_freeze_manifest.json` | v7.0 冻结哈希 + 评价协议常量 |
| `outputs/b710_evidence/source_independence/source_registry.csv` | 41 原始研究 + 61 外部来源的登记表 |
| `.../source_lineage.json` | 规则 R1/R2/R3、分子级覆盖、claim gate |
| `.../molecule_source_overlap.csv` | 239 分子逐条来源数与一致性 |
| `.../external_data_audit.csv` | 61 个外部来源的准入判定 |
| `.../external_agreement.csv` | 58 条重叠记录与冻结标签的比对 |
| `.../source_ood_results.json` | 13 个来源的留一检验 |
| `.../source_bootstrap_results.json` | 研究级 cluster bootstrap |
| `.../source_cluster_audit.json` | 三种 OOD 的显式分离声明 |
| `outputs/b710_evidence/ether_subfamilies/ether_subtype_table.csv` | 16 分子子族标签 + 规则证据 |
| `.../ether_subtype_manifest.json` | 规则版本、非修改声明、n<5 警告 |
| `.../ether_subfamily_analysis.json` | 池化 vs 分层，含置换 p 与 LOO 影响 |
| `outputs/b710_evidence/e4_mechanism_audit/e4_calibration_audit.csv` | 11 家族的 zero/diagnostic/honest 三列 |
| `.../e4_outlier_influence.csv` | 异常点的 NN 距离与 MAE 占比 |
| `.../e4_mechanism_audit.json` | 校准方法与多机制声明 |
| `outputs/b710_evidence/e6_stability/e6_stability_v71.json` | 20 种子 + 分子 bootstrap + 三种不确定性 |
| `.../e6_seed_table.csv` | 80 行逐种子明细 |
| `outputs/b710_evidence/xtb_on_dft_geometry/two_by_two_matrix.csv` | 12 分子完整 2×2 |
| `.../two_by_two_analysis.json` | 效应分解 + 扩展建议（含我的推翻理由） |
| `.../xtb_on_dft_geometry_preflight.json` | 原子顺序校验与哈希 |
| `tests/test_b710_evidence/test_b710_contracts.py` | 29 条契约 |
| `scripts/b710_evidence/*.py` | 8 个分析脚本 + 1 个 sbatch |

---

## 9. 复现

```bash
python scripts/b710_evidence/freeze_v70_evidence.py
python scripts/b710_evidence/build_source_registry.py
python scripts/b710_evidence/analyze_source_ood.py
python scripts/b710_evidence/classify_ether_subfamilies.py   # 需要 rdkit
python scripts/b710_evidence/analyze_ether_subfamilies.py
python scripts/b710_evidence/audit_e4_bias_calibration.py
python scripts/b710_evidence/analyze_e6_stability.py         # 约 40 分钟
python scripts/b710_evidence/build_xtb_on_dft_geometry.py
python scripts/b710_evidence/analyze_2x2_method_geometry.py
python -m pytest tests/test_b710_evidence/ -q                # 29 passed
```

超算侧：`scripts/b710_evidence/run_xtb_on_dft.sbatch`（12 任务，已完成）。
