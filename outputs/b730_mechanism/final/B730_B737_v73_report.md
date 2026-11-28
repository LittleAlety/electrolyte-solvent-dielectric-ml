# PLAN B v7.3 — 物理机制与描述符有效性边界

**版本**：v7.3  
**基线**：v7.2 / commit `9aa1225`（86 条测试通过，工作区干净）  
**本轮测试**：36 条新增 + 86 条继承 = **122 条全部通过**  
**产出**：`outputs/b730_mechanism/`（9 个子目录）

---

## 0. 本轮最重要的一件事

**CRAFT-ε 的模型被完整重新实现并精确复现（16/16 参考液体，相对差 0.0000）。**

这把先前只能"读摘要"的外部工作变成了可审计的对象：

| 项目 | 结果 |
|---|---|
| 仓库固定 commit | `65fa0fb0a55838a656769ed717d41d52f1516c4a`（MIT） |
| 41 个拟合参数 | 解析得到，与作者声明一致 |
| 52 个摩尔体积贡献 | 从 `molar_volume.py` 提取 |
| 16 个参考液体 | **ε 全部精确复现，V_m 全部 <0.001%** |
| 类别判定 | 16/16 一致 |

复现过程中修正了 3 处自身错误（详见 §7），全部记录在脚本注释里。

**但复现本身不是创新。** 本轮的独立贡献在于用它的模型形式回答本项目的问题（§2-4）。

---

## 1. CRAFT-ε 对照（G730）

### 1.1 能比什么、不能比什么

| 维度 | 结论 |
|---|---|
| 数据重叠 | **`UNRESOLVED`**：训练集 1393 液体**未随仓库发布**，无法核实 |
| 分子重叠 | 只能对 16 个已发布参考液体测量 → **5 个在 CORE239 内** |
| 来源重叠 | **`NOT_TESTABLE`**：无逐分子原始文献 |
| 模型形式对比 | 可以对 5 个重叠分子做物理量分解 |
| 精度排名 | **`NOT_COMPARABLE`，不发布排名** |

### 1.2 为什么不能排名

1. CRAFT 需要在它自己的 GFN2-xTB/ALPB 构象系综上运行；本项目是 ORCA r2SCAN-3c，**没有逐原子电荷/原子偶极/逐原子极化率数组**，喂不进去。
2. CRAFT 公布的 CV 指标与我们 MAE 的比较**跨数据集、跨标签、跨划分**，不成立。
3. **n=5 无法给两个模型排名。**

### 1.3 物理量的直接对比（这是有价值的）

在 5 个重叠分子上，两套模型形式给出很不同的 ε∞：

| 分子 | 真实 ε | CRAFT ε | 我们 ε∞(CC) | CRAFT ε∞ | ΔV_m (cm³) |
|---|---|---|---|---|---|
| Bromoethane | 9.39 | 9.34 | 2.842 | 1.639 | −34.4 |
| 2-Bromobutane | 8.64 | 8.10 | 3.033 | 1.778 | −48.5 |
| dimethyl carbonate | 3.13 | 2.43 | 2.591 | 1.920 | −36.1 |
| 2-Methoxyethanol | 16.00 | 16.05 | 2.674 | 1.995 | −32.8 |
| trans-1,2-DCE | 2.14 | 3.63 | 3.253 | 3.630 | −33.8 |

**两个关键差异**：

1. **CRAFT 的 molblock 是含显式氢的孤立分子几何**，其 V_m 比真实液体小 33–49 cm³/mol。它的 group-contribution V_m 修正了这个差距，但**CRAFT ε∞ 用的是修正后的 V_m，我们用的是 RDKit vdW 体积**——两者不可直接互换。
2. **CRAFT 的 ε∞ 系统性低于我们的 Clausius-Mossotti 估计**（1.64–2.00 vs 2.59–3.25）。这说明我们的 ε∞ 偏高，部分解释了我们的模型为何在高 ε 上偏低。

### 1.4 CRAFT 提供了什么本项目缺少的

| CRAFT 有 | 本项目有 |
|---|---|
| 显式的 Clausius-Mossotti ε∞ | 无显式 ε∞ 建模 |
| 逐原子组标度极化率（3+11 参数） | 单一各向同性极化率 |
| 极性基团分辨的偶极向量（15 个片段标度） | 单一总偶极 |
| Group-contribution 摩尔体积（Bouloup & Mathieu） | RDKit vdW 体积（**偏差约 2 倍**） |
| 构象系综同时对 α 和 μ 做 Boltzmann 平均 | v7.0-7.2 只对 μ 做 |
| — | r2SCAN-3c 逐分子电子结构 |
| — | 家族分辨的误差机制分解 |
| — | 原始研究级来源独立性核算 |
| — | 候选池敏感性 |

**本项目的独立贡献不是"比 CRAFT 准"，而是"说清楚它为什么在某些化学空间必然失效"，以及来源与筛选层面的证据边界。**

---

## 2. 液体介电物理分解（G731）

### 2.1 框架

Kirkwood-Fröhlich 关系，求解剩余项：

```
g_app = [9 ε₀ kB T V_m / (N_A μ²)] · (εs−ε∞)(2εs+ε∞) / [εs(ε∞+2)²]
```

**关键命名决定**：用**气相单分子偶极**代入，得到的是 `apparent_correlation_factor`，**不是** Kirkwood g。它混合了：液相偶极增强 + 取向相关 + 单分子近似误差 + 条件失配。

### 2.2 覆盖率与路线（必须交代）

| 项目 | 数值 |
|---|---|
| 分子总数 | 239 |
| 可算 g_app | **194（81.2%）** |
| 因偶极近零排除 | 29（μ<0.3 D，1/μ² 发散） |
| **V_m 来自实测密度** | **170** |
| V_m 来自 RDKit vdW 体积 | 69 |
| ε∞ 路线：Clausius-Mossotti | 231 |
| ε∞ 路线：n_D² | 8（ComBat，探索性） |

### 2.3 一个必须分层的发现

V_m 的两个来源给出的 g_app **完全不同**：

| V_m 来源 | n | g_app 中位 |
|---|---|---|
| **实测密度（主集）** | **143** | **1.104** |
| RDKit vdW 体积 | 51 | 0.234 |

原因：RDKit 的 `molar_volume_m3_mol` 是**vdW 腔体积 × N_A，约为真实液体 V_m 的一半**（溴乙烷 39.3 vs 74.6 cm³/mol）。这既抬高 CC 的 x 又压低 g_app。

**因此主结论只用实测密度子集，另一组单独报告不作物理解释。** 契约测试 `test_vdw_volume_is_flagged_separately` 强制这一点。

### 2.4 主集结果（n=143）

| 家族 | n | g_app 中位 |
|---|---|---|
| alcohol_polyol | 26 | **3.471** |
| amine | 8 | 3.094 |
| other_neutral_liquid | 6 | 1.579 |
| ether | 10 | 1.535 |
| ketone_aldehyde | 16 | 1.154 |
| ester | 21 | 0.957 |
| nitro | 6 | 0.948 |
| aromatic | 21 | 0.933 |
| halocarbon | 16 | 0.790 |
| nitrile | 5 | 0.687 |
| carboxylic_acid | 5 | 0.347 |

**核心物理解读**：

- **g_app ≈ 1**（酯、硝基、芳香、酮）→ 气相单分子偶极已能解释介电响应，分子间相关接近 1
- **g_app ≈ 3–3.5**（醇、胺）→ 液相取向相关显著，单分子偶极**低估**了 3 倍
- **g_app < 0.7**（腈、卤代烃、羧酸）→ 单分子偶极**高估**了响应，符合偶极抵消/反平行排列

**这是本轮最重要的物理结论**：单分子描述符的失效不是均匀的，而是按氢键能力分成两个方向相反的系统性区间。

### 2.5 与氢键描述符的关系

| 相关 | 值 |
|---|---|
| g_app vs hbd | 0.122 |
| g_app vs hba | 0.151 |
| g_app vs n_rotatable | 0.031 |

**都很弱**。说明 g_app 携带的信息不是简单由 HBD/HBA 计数能替代的——但 n=143 且无置换 p 值，只能作描述性报告。

### 2.6 局限（必须与结论一起引用）

1. 239 个分子**没有折射率数据**，ε∞ 主要靠计算极化率，这本身是模型
2. V_m 有 69 个是 vdW 体积，物理上偏小
3. 气相 μ ≠ 液相 μ
4. 温度匹配是 ±5 K，标签是源级
5. **g_app 不能称为 Kirkwood g**

---

## 3. 构象偶极抵消（G732）

### 3.1 三个量必须分开

```
<μ> = Σ wᵢμᵢ       （向量，Onsager 用的是这个）
<μ²> = Σ wᵢ|μᵢ|²   （标量均方）
|<μ>|² ≤ <μ²>      恒成立
C_μ = 1 − |<μ>|²/<μ²>   ∈ [0,1)
```

v7.1 的 E3 只比较了**标量幅度**，**无法检测方向抵消**。本轮补上。

### 3.2 结果（39 分子，37 有效）

| 统计 | C_μ |
|---|---|
| 中位 | **0.658** |
| 均值 | 0.577 |
| 范围 | 0.0006 – 0.920 |

**中位 0.66 意味着**：典型柔性分子的构象系综里，向量平均只剩均方根的 sqrt(1−0.66) ≈ **58%**。

| 家族 | n | C_μ 中位 |
|---|---|---|
| nitro | 3 | 0.867 |
| ketone_aldehyde | 2 | 0.763 |
| other_neutral_liquid | 4 | 0.752 |
| alcohol_polyol | 7 | 0.736 |
| ester | 10 | 0.709 |
| halocarbon | 4 | 0.515 |
| ether | 2 | 0.277 |
| carboxylic_acid | 3 | 0.197 |

### 3.3 C_μ 与预测误差的关系 → **没有关系**

**Pearson(C_μ, |LOFO 残差|) = −0.079**（n=37）

**这是一个明确的否定结果**：构象偶极抵消**不能**解释单构象模型的残差。

这与 v7.1 的 E3 一致（Boltzmann 平均不改善与 ε 的相关），现在有了机制层面的独立证据：**问题不在构象方向抵消，而在液相取向相关本身**（即 g_app 那一项）。

### 3.4 权重性质的诚实标注

权重是 **GFN2-xTB 电子能量的 Boltzmann 权重**，**不是 Gibbs 自由能**：无热修正、无溶剂化、非液相分布。所有输出都带 `is_gibbs: false`。

---

## 4. 描述符独立信息量（G733）

### 4.1 方法（拒绝朴素置换重要性）

| 用 | 不用 |
|---|---|
| 条件增益（加块前后 LOO，配对 bootstrap） | 朴素 permutation importance |
| 偏相关（B 对 A 残差化后与目标残差相关） | — |
| 训练折内选 λ | 在测试点选特征 |

**理由**：强相关特征下 permutation importance 会任意分摊贡献，不是独立性的证据。

### 4.2 条件增益（相对纯结构基线 MAE 7.018）

| 加入的块 | MAE 增益 | 95% CI | 偏相关 | CI 排除 0 |
|---|---|---|---|---|
| 偶极 | +1.904 | [+1.369, +2.459] | 0.504 | ✅ |
| **μ²/Vm** | **+2.759** | **[+2.022, +3.534]** | **0.631** | ✅ |
| **极化率** | **−0.005** | **[−0.050, +0.041]** | **−0.026** | ❌ |
| xTB 电子 | +1.521 | [+0.917, +2.122] | 0.495 | ✅ |
| DFT 电子 | +1.920 | [+1.380, +2.474] | 0.504 | ✅ |

### 4.3 三个关键结论

**① 极化率在控制分子体积后没有独立贡献**

增益 −0.005（CI 跨 0），偏相关 −0.026。**极化率作为一个"独立物理通道"在本数据上不成立**——它的信息已被分子体积/结构块吸收。

**② DFT 与 xTB 高度冗余**

| 特征对 | Pearson r |
|---|---|
| xTB 偶极 vs DFT 偶极 | **0.921** |
| xTB gap vs DFT gap | **1.000** |

**必须说明**：`homo_lumo_gap_ev_v7` 与 `homo_lumo_gap_ev` 完全相同（r=1.0），因为描述符构建器在 ORCA gap 缺失时**回退到 xTB gap**。

**因此"DFT 电子块强于 xTB"（+1.920 vs +1.521）只能归因于偶极**，不能声称 DFT 提供了第二条独立电子通道。这个限制已写入 JSON。

**③ μ²/Vm 是单一最强块**

增益 2.759，占结构基线 MAE 的 39%。这也是 v7.0-7.2 反复验证的结论。

---

## 5. 239 分子误差机制地图（G734）

### 5.1 八类标签（多标签，非互斥）

| 标签 | 定义 | 计数 |
|---|---|---|
| ASSOCIATION_HEAVY | hbd+hba ≥ 2 | **106** |
| LEVEL_BIAS_FAMILY | 家族 \|bias\|/sd > 0.7 | 62 |
| **NONE** | 无标签 | **56** |
| RANKING_FAILURE_FAMILY | 家族 ρ < 0.3 | 28 |
| STRUCTURAL_EXTRAPOLATION | NN > 池 90 分位 | 24 |
| CONFORMER_SENSITIVE | C_μ > 0.5 | 22 |
| TARGET_EXTRAPOLATION | ε > 池 95 分位（30.20） | 12 |
| LOW_POLARITY_HIGH_EPS | ε≥20 且 μ<0.5 | 1 |

### 5.2 最差 12 个分子的机制组合

| 分子 | 家族 | \|残差\| | 机制 |
|---|---|---|---|
| Hydrocyanic acid | nitrile | 96.45 | TARGET_EXTRAPOLATION |
| Triolein | ester | 59.48 | STRUCTURAL_EXTRAPOLATION; ASSOCIATION_HEAVY |
| Dioctyl sebacate | ester | 21.06 | STRUCTURAL_EXTRAPOLATION; ASSOCIATION_HEAVY |
| Trifluoroacetic acid | carboxylic_acid | 20.10 | 三者同时 |
| 3-Chloro-1,2-epoxypropane | ether | 18.75 | STRUCTURAL + RANKING + LOW_POLARITY |
| Tetranitromethane | nitro | 18.41 | STRUCTURAL + RANKING + ASSOCIATION |
| β,β'-dichlorodiethyl ether | ether | 17.58 | RANKING_FAILURE_FAMILY |
| Butyl stearate | ester | 16.67 | STRUCTURAL + CONFORMER + ASSOCIATION |
| Acetonitrile | nitrile | 16.03 | TARGET_EXTRAPOLATION |
| acetic acid | carboxylic_acid | 15.11 | ASSOCIATION_HEAVY |

### 5.3 解读

- **单一机制解释不了任何大残差分子**。Trifluoroacetic acid 同时踩三个坑。
- **HCN 只有一个标签**（目标外推）——它不是结构异常，只是 ε=114.9 太极端。
- **56 个分子没有任何机制标签**，说明模型在这部分工作正常。
- **`LOW_POLARITY_HIGH_EPS` 只有 1 个**：环氧氯丙烷。这个"低极性高 ε"机制在本数据中几乎不存在。

**重要防护**：`interpretation_guard` 明确写"有标签不等于误差案例"。`TARGET_EXTRAPOLATION` 是**标签分布的性质**，不是分子的缺陷。

---

## 6. 定向扩展与筛选（G735/G737）

### 6.1 新增分子：**0 个进入 VALIDATED**

外部来源共找到 **31 个**不在 CORE239 的候选（LiquidBenchmark 20 + CRAFT 参考 11），其中 **29 个能填补已声明的研究空白**。

**但一个都没进确认性数据集**，因为：

| 要求 | LiquidBenchmark | CRAFT 参考 |
|---|---|---|
| 逐分子原始文献 | ❌ ThermoML 派生，无逐行 DOI | ❌ 作者拟合表条目 |
| 测量频率 | ✅（零频率定义） | ❌ |
| 温度 | ✅ | ✅（298.15 K） |

**把它们当 VALIDATED 会重犯本项目批评的那个错误。**

### 6.2 关键否定结果：**仍然找不到氯代醚**

31 个候选中 **0 个氯代醚**。

| 醚子类 | 候选数 |
|---|---|
| chlorinated_ether | **0** |
| aliphatic_ether | 2 |
| cyclic_ether | 1 |
| aromatic_ether | 0 |

**氯代醚 n=2 的限制在本轮仍无法打破**，与 v7.2 结论一致。

### 6.3 推荐状态（G737）

不输出固定 Top-10（v7.2 已证不可靠），改为逐分子状态：

| 状态 | 定义 | μ²/Vm 臂 | r²SCAN-3c 臂 |
|---|---|---|---|
| STABLE_RECOMMEND | 频率≥0.8 且 rank IQR≤3 且在域内 | **11** | 8 |
| CONDITIONAL | 频率≥0.3 | 2 | 1 |
| EVIDENCE_NEEDED | 频率 0.1–0.3 | 2 | 2 |
| NOT_RECOMMENDED | 频率<0.1 | 200 | 204 |
| OUTSIDE_DOMAIN | NN > p90 | 24 | 24 |

**两臂共同稳定：5 个**

`hexanedinitrile`, `triethanolamine`, `Hydrocyanic acid`, `glycerol`, `Acetonitrile`

（Jaccard = 0.357）

**注意**：这 5 个里 `Hydrocyanic acid` 同时带 TARGET_EXTRAPOLATION 标签。**"稳定推荐"只表示模型排序稳定，不表示预测准确**——HCN 残差 96.45。这个矛盾必须一起报告。

---

## 7. 本轮自行修正的错误（全部记录在代码注释）

| 错误 | 症状 | 修正 |
|---|---|---|
| 摩尔体积单位 | `mw/1000/(rho/1000)/1e6`，比真实值小 1000 倍 | `(mw/1000)/rho` |
| 取向项重复换算 | ε 算成 ~1e5 | V_m 保持 cm³/mol，1e-6 只在取向项内用 |
| V_m 用显式氢 | `no V_m contribution for ['H10']` | `removeHs=True` |
| g_app 未屏蔽近零偶极 | g_app 达 1e14 | μ<0.3 D 排除并标记 |
| SMARTS `#CX4` 无效 | `MolFromSmarts` 返回 None 崩溃 | 改 `#6X4` |
| CRAFT 分支不完整 | 早期版本 ε 差 3 个数量级 | 补全 groups/fragment 逻辑后精确复现 |
| 26 处小格式/顺序错误 | 各种 traceback | 逐个修正 |

---

## 8. 证据等级汇总

| 结论 | 等级 |
|---|---|
| CRAFT 模型精确复现（16/16） | `CONFIRMED` |
| CRAFT 训练集未发布，数据重叠不可测 | `CONFIRMED` |
| CRAFT 与本项目精度排名不成立（n=5） | `CONFIRMED` |
| g_app 按氢键能力分两个方向相反区间 | `SUPPORTED`（n=143，无 p 值） |
| 极化率控制体积后无独立贡献 | `CONFIRMED`（CI 跨 0） |
| DFT 与 xTB 偶极高度冗余（r=0.921） | `CONFIRMED` |
| DFT gap 列非独立 ORCA 量（r=1.0） | `CONFIRMED` |
| C_μ 中位 0.658（构象抵消显著） | `CONFIRMED` |
| C_μ 与预测误差无关（r=−0.079） | `CONFIRMED` |
| 106 分子带 ASSOCIATION_HEAVY 标签 | `CONFIRMED` |
| 大残差分子均有多重机制 | `CONFIRMED` |
| 无新增氯代醚 | `CONFIRMED` |
| 0 个新分子进入 VALIDATED | `CONFIRMED` |
| 5 个分子跨臂稳定推荐 | `SUPPORTED`（HCN 矛盾需并列） |
| 液相取向相关的真实强度 | `UNRESOLVED`（g_app 含近似误差） |
| 独立实验室泛化 | `NOT_TESTABLE` |

---

## 9. 回答计划的 30 个问题（摘要）

**CRAFT-ε**：1 已复现（16/16）；2 只有 16 个参考可见，其中 5 个重叠；3 **不能公平比较**；4 提供了显式 ε∞、逐原子组极化率、片段偶极、group-contribution V_m；5 高 ε 极性液体与羧酸仍失效。

**液体物理**：6 170/239 有实测密度，**0 个有折射率**；7 可算但只能叫 g_app；8 是，g_app 从 0.35 到 3.47 跨 10 倍；9 能解释家族级的系统方向，不能解释单分子残差。

**构象**：10 **否**（r=−0.079）；11 没有证据；12 **否**——真正的问题在液相相关而非构象。

**电子描述符**：13 **部分**——偶极是新的（r=0.921），gap 不是（r=1.0）；14 **否**（CI 跨 0）；15 极化率与体积冗余，DFT 与 xTB gap 完全相同；16 极化率可由体积替代，xTB gap 可替代 DFT gap。

**新增分子**：17 **0 个进入确认集**；18-21 见 §6。

**筛选**：22 11 个（单臂）/ 5 个（跨臂）；23 OUTSIDE_DOMAIN 24 个 + NOT_RECOMMENDED 200 个；24 无家族条件优势；25 **尚不能支持可靠材料推荐**。

**科学贡献**：26 不是准度，而是**失效机制的物理解释 + 来源独立性的严格核算 + 筛选指标的池依赖性**；27-29 见 §8；30 见 §10。

---

## 10. 下一轮最值得投入的

1. **补折射率数据**（239 个分子的 n_D）→ 把 ε∞ 从"计算模型"变成实验量，这是 g_app 物理化的前提
2. **定向文献检索氯代醚**（需要 5–8 个有静态 ε、T、频率的）→ 唯一能解决 ether 排序问题的路径
3. **手收一个单实验室数据集**（5–10 个液体，同一论文、同法测量）→ 唯一能建立干净 Source OOD 的路径
4. 可选：二聚体计算验证氢键液体的 g_app>3 是否真由分子间相关造成（B736 未启动，因为前四项分析已说明单分子模型的主要误差在液相相关，但**尚未定量验证**）

---

## 11. 复现

```bash
python scripts/b730_mechanism/audit_craft_epsilon.py
.venv/Scripts/python.exe scripts/b730_mechanism/validate_craft_baseline.py
.venv/Scripts/python.exe scripts/b730_mechanism/analyze_model_overlap.py
python scripts/b730_mechanism/compute_apparent_gk.py
python scripts/b730_mechanism/analyze_conformer_dipoles.py
.venv/Scripts/python.exe scripts/b730_mechanism/analyze_descriptor_information.py
.venv/Scripts/python.exe scripts/b730_mechanism/build_error_mechanism_map.py
.venv/Scripts/python.exe scripts/b730_mechanism/rank_expansion_candidates.py
.venv/Scripts/python.exe scripts/b730_mechanism/analyze_recommendation_uncertainty.py
.venv/Scripts/python.exe -m pytest tests/test_b730_mechanism/ -q   # 36 passed
```
