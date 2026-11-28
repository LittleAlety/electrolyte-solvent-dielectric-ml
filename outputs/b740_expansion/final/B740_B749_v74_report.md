# PLAN B v7.4 — 液相物理、分子扩张与多尺度描述符

**版本**：v7.4
**基线**：v7.3 / commit `e819038`（122 条测试通过，工作区干净）
**本轮测试**：45 条新增契约测试 + 122 条继承 = **167 条全部通过**（`tests/test_b700_orca`、`test_b710_evidence`、`test_b720_external`、`test_b730_mechanism`、`test_b740_expansion`，2.0 s）
**产出**：`outputs/b740_expansion/`（11 个子目录）+ `data/external_raw/pubchem_b740/`（144 个结构缓存）

> 说明：`pytest tests/` 全树包含依赖网络的探针（ILThermo/WebBook 抓取等），本轮未纳入门禁；门禁范围与 v7.3 相同，即五个轮次目录。

---

## 0. 本轮最重要的一件事

**本轮最大的成果不是某个模型涨点，而是一次"数据恢复 → 自纠错 → 结论反转"的完整链条。**

三件事必须写在最前面，因为它们改变了本轮的结论：

| # | 发现 | 影响 |
|---|---|---|
| 1 | 新分子的摩尔质量缺失，导致 V_m 无法计算，`molar_refraction` 只有 14 个分子 | 补上"从 ThermoML 分子式算 M"的兜底后，V_m 从 27 → **50**，`molar_refraction` 从 14 → **39**，ε∞ 校验样本从 14 → **22** |
| 2 | 上述修复使 X3 面板从 n=14 → **n=22**，液相性质层的配对增益从 **+0.941 翻转为 −0.023** | v7.4 早先"液相性质层有帮助"的结论**被本轮自己推翻** |
| 3 | 本地 ThermoML 语料里**焓蒸发热记录为 0 条**（不是"稀疏"） | CED / Hildebrand 从"样本小"改判为 **`NOT_TESTABLE`** |

> 这三条都记录在脚本注释与本报告 §12。**结论可以被自己的数据推翻，这才是可交付的部分。**

---

## 1. 数据恢复：本地 ThermoML 语料（B740）

### 1.1 规模

| 项目 | 数值 |
|---|---|
| 文档 | 242 篇（解析失败 0） |
| 记录总数 | 25 612 |
| 纯物质记录 | 5 879 |
| 混合物记录 | 19 733 |
| 静态相对介电常数 | **1 713 条 / 103 个分子**（纯物质） |
| 频率相关介电常数 | 1 109 条 / 93 个分子（**全部排除，见 §1.3**） |
| 密度 | 2 422 条 / 127 个分子 |
| 折射率 | 635 条 / 86 个分子 |
| 焓蒸发热 | **0 条** |
| ε+ρ 同时可得 | 51 个分子 |
| ε+ρ+n_D 同时可得 | 41 个分子 |

证据：`outputs/b740_expansion/thermoml/thermoml_coverage.json`、`thermoml_local_scan.csv`（25 612 行）。

### 1.2 来源独立性（这直接攻击 v7.1–v7.3 的阻塞）

v7.3 的阻塞是"clean-source OOD 不可行"：0 篇原始研究独占 ≥3 个分子。v7.4 的答案是**换一条路**——不再要求"独占来源"，而是要求"分子在 CORE239 之外，且其 ε 来自可引用 DOI"。

| 分子 | 独立 DOI 数 | 全部为原始文献 | 温度点 | ε 中位数 |
|---|---|---|---|---|
| butan-1-ol | 6 | 6 | 16 | 17.80 |
| propan-1-ol | 5 | 5 | 10 | 21.15 |
| dimethyl sulfoxide | 4 | 4 | **105** | 45.39 |
| N,N-dimethylethanamide (DMF) | 3 | 3 | 12 | 32.95 |
| water | 3 | 3 | 33 | 77.29 |
| cyclohexanone | 2 | 2 | 30 | 17.07 |
| 2,5,8-trioxanonane（glyme） | 2 | 2 | 9 | 7.12 |
| 2,5,8,11-tetraoxadodecane | 2 | 2 | 8 | 7.58 |
| sulfolane | 1 | 1 | 8 | 42.80 |

证据：`outputs/b740_expansion/molecule_expansion/cohort_ledger.csv`。

**等级：`CONFIRMED`** —— 67 个 `NEW_MOLECULE_VALIDATED` 分子中，17 个有 ≥2 个原始 DOI，35 个有 ≥5 个温度点。

**但仍然不是"干净 OOD"**：这些分子的 ε 记录多数仍在 ThermoML 汇编内部，只是 DOI 追溯到原始文献。**"来源独立"改善的是可追溯性，不是"独立实验室集合"。** 这一点不粉饰。

### 1.3 静态 vs 频率相关：绝不允许合并

`dielectric_constant_static`（"Relative permittivity at zero frequency"）与 `dielectric_constant_frequency_dependent`（"at various frequencies"）在 CSV 中是两个不同的 `property` 值：

- 静态行中 `has_frequency=true` 的数量 = **0**
- 频率相关组 1 109 条 / 93 个分子，`definition` 字段明确写着 **excluded from every modelling set**
- 两者的 `(doi, property_raw)` 集合互不相交（契约测试断言）

**这是本轮最危险的 bug 面**：第一版解析器把两组都标成 static，会让 1 109 条频率相关数据冒充静态 ε。已修正并加了契约测试。

### 1.4 混合物永不作为纯液体标签

19 733 条混合物记录全部 `is_mixture=true`，`mixture_policy` 写明 "NEVER used as pure-liquid epsilon labels"。纯静态 ε 的 103 个分子只来自 `is_mixture=false` 的记录。

**同类修正**：早先按逗号计数判断混合物，把 45 个 IUPAC 名（如 "acrylic acid, methyl ester"）误判为混合物。ThermoML 只用分号分隔组分，已改为只认 `;`。

---

## 2. 新分子结构解析与身份校验（B741）

新分子只有 InChIKey，没有 SMILES，既不能算描述符，也不能判断氢键能力。方案：PubChem PUG REST 按 InChIKey 取 SMILES，然后**用 RDKit 反推 InChIKey 做身份证明**。

| 项目 | 结果 |
|---|---|
| 请求分子 | 145（有 ε/ρ/n_D 数据的全部非 CORE239 分子） |
| 身份校验通过 | **144** |
| 未解析 | 1（`1-ethyl-3-(2-methoxyethyl)imidazolium dicyanamide`，PubChem HTTP 404） |
| 缓存文件 | 144 个，SHA-256 记录于 `PROVENANCE.json` |

**为什么必须做往返校验**：PubChem 一个 InChIKey 会返回多个 CID（水就返回中性 `O` 和 `[H+].[OH-]` 两个）。盲取第一个 CID 会把离子当液体。逐候选往返测试后，不匹配的结构被**拒绝而不是"修好"**。

**等级：`CONFIRMED`**。证据：`outputs/b740_expansion/molecule_expansion/new_molecule_structures.csv`、`structure_resolution_summary.json`。

**重要副产品**：这 144 个结构也让混合物的"是否含氢键给体"判定从"按名字猜"变成"按结构算"（§6）。

---

## 3. 极化率张量（B742 / RQ1）

| 项目 | 结果 |
|---|---|
| 记录数 | 478（opt 239 + sp 239） |
| 张量对称 | 478/478 |
| iso（ORCA 打印）vs 本征值均值 | 最大差 5×10⁻⁶ |
| 迹 = (α_xx+α_yy+α_zz)/3 | 最大差 5×10⁻⁶ |
| Δα 定义 √(½Σ(λᵢ−λⱼ)²) | 最大差 5×10⁻⁶ |
| bohr³→Å³（0.14818471） | 最大差 5.7×10⁻⁶ |
| 重复 (分子, 层) 对 | 0 |

**框架约定守卫**：ORCA 在自己分子坐标系里打印张量，6 个非对角分量**跨分子不可比**；只有 3 个本征值无框架依赖。所有跨分子陈述只用本征值，原始分量仅留档。

### 3.1 各向异性比按家族（opt 层，中位数 Δα/ᾱ）

| 家族 | n | 中位数 |
|---|---|---|
| 芳香 | 39 | **0.626** |
| 腈 | 7 | 0.584 |
| 硝基 | — | 0.445 |
| 卤代烃 | 27 | 0.397 |
| 羧酸 | 8 | 0.362 |
| 醚 | 16 | 0.361 |
| 酯 | 27 | 0.328 |
| 酮/醛 | 22 | 0.312 |
| 胺 | 10 | 0.298 |
| 醇/多元醇 | 32 | **0.221** |

排序符合化学直觉：π 体系与腈的电子云最不各向同性，多羟基醇因氢键网络主导的近球形局部场而最接近各向同性。**等级：`SUPPORTED`（描述性统计，未做显著性检验，n 逐族不等）。**

---

## 4. 构象统计（B743 / RQ2）——一个明确的负结果

| 项目 | 结果 |
|---|---|
| 分子数 | 39 |
| S_conf 中位数 | 10.58 J·mol⁻¹·K⁻¹（0.05–14.09） |
| N_eff 中位数 | 约 3.4–4.7（按家族） |
| C_μ 中位数 | **0.682**（0.0006–0.9785） |
| 权重来源 | GFN2-xTB 电子能（**`is_gibbs: false`**） |
| 分子内氢键 | 33 个分子有几何判据；占据率中位数 0.0 |

**必须是电子能**：S_conf 是**结构柔性指数**，不是液体的热力学熵。契约测试直接断言 `is_gibbs is False` 且注释含 "ELECTRONIC"。

**负结果（这是本轮该被引用的部分之一）**：

| 面板 | 配置 | n | MAE | 配对增益 |
|---|---|---|---|---|
| X2_PANEL | X0+X1 | 39 | 2.9947 | — |
| X2_PANEL | X0+X1+X2 | 39 | 3.3767 | **−0.382** |

构象层**使误差变差**。与 v7.3 的独立证据一致：C_μ 与 |残差| 的 Pearson r = −0.079，C_μ 中位数 0.658（v7.3 口径）。**等级：`CONFIRMED`（配对、同面板、同划分）。**

---

## 5. 液相热力学指数（B744 / RQ4）

### 5.1 覆盖（修复后）

| 指数 | 可用分子数 |
|---|---|
| 摩尔体积 V_m | **50** / 51 |
| 摩尔折射 R_m | **39**（中位数 26.80 cm³/mol） |
| Lorentz–Lorenz 极化率 α_LL | 39 |
| Lippert–Mataga Δf | **40**（中位数 0.233；−0.0007–0.320） |
| dε/dT | **40**（97.5% 为负；−0.333–+0.0005 K⁻¹） |
| CED / Hildebrand | **0 → `NOT_TESTABLE`** |

### 5.2 摩尔体积的来源必须分开

- 本表 V_m 全部由**实测密度**换算：`V_m = (M/1000)/ρ × 10⁶`（cm³/mol）
- 水 18.05、甲醇 40.49、甲苯 106.89、decan-1-ol 191.53 cm³/mol → 物理合理
- **不接受** RDKit vdW 体积充当液体 V_m（v7.3 已证明它只有真实液体 V_m 的一半左右）

### 5.3 摩尔质量兜底（本轮修的第一个 bug）

`V_m` 需要 M，而 M 只存在于 CORE239 描述符表；67 个新分子没有。补上"从 ThermoML 分子式算 M"：

| 项目 | 结果 |
|---|---|
| 从描述符取 M | 27 |
| 从 ThermoML 分子式取 M | **24** |
| 无 M | 0 |
| 两源重叠分子 | **102** |
| 最大偏差 | **0.007 g/mol** |

多组分/带电/未知元素符号的分子式**直接拒绝**（不求和、不跳过）——求和会凭空造出一个 V_m。

### 5.4 DFT 极化率 vs Lorentz–Lorenz 实测（关键校验）

| 项目 | 修复前 | 修复后 |
|---|---|---|
| 样本 | 14 | **22** |
| Pearson r | 0.9993 | **0.9972** |
| MAE | 1.115 Å³ | **1.1368 Å³** |

**这不是拟合，是校验**：一边是实测 n_D 与实测 V_m 经 Lorentz–Lorenz 得到的 α，另一边是 r²SCAN-3c 气相 α。r≈0.997 说明 r²SCAN-3c 的极化率与光学响应自洽。

**必须保留的告诫**：n_D 是钠 D 线（589 nm），与**静态** DFT α 相比隐含"光学与静态电子响应相同"的近似，**不是恒等式**。此告诫写在 `thermodynamic_summary.json` 的 `caveats` 里，契约测试断言其存在。

### 5.5 温度配对纪律

`matched_T_K` 容差 2 K；一个复合指数只取**一个** (T, ε, n, ρ) 元组，禁止跨温拼接。契约测试断言：每一行都有 `matched_T_K` 与 `epsilon_at_matched_T`，且配对计数不超过 ε 点数。

---

## 6. 混合物介电混合规则（B745 / RQ5）

这是本轮**新开且唯一能测"分子间"的实验面**：同一对分子在许多组成下被测量。

### 6.1 数据

| 项目 | 数值 |
|---|---|
| 扫描到的混合物记录 | 3 064 |
| 可评估点 | **2 278** |
| 不同二元对 | **36** |
| 不同 DOI | **13** |
| 剔除：缺纯物质 ε | 164 |
| 剔除：缺纯物质密度/质量 | 622 |

### 6.2 三种理想规则（不拟合任何参数）

| 规则 | 定义 | n | MAE（ε 单位） |
|---|---|---|---|
| 线性（摩尔分数） | ε = x₁ε₁ + x₂ε₂ | 2 278 | 1.1148 |
| Lichtenecker（体积分数对数） | ln ε = φ₁ln ε₁ + φ₂ln ε₂ | 2 278 | **0.7282** |
| Clausius–Mossotti（体积分数 f(ε) 加和） | f=(ε−1)/(ε+2) 加权 | **318** | **0.2073** |
| 常数基线 | 预测均值 | 2 278 | 8.4184 |

### 6.3 CM 规则的定义域必须交代（否则就是误导）

CM 加和规则在加权 g 达到 0.49 时**发散**，因此：

| 项目 | 数值 |
|---|---|
| CM 有定义 | **318 / 2 278（14%）** |
| CM 无定义 | 1 960 |

**后果**：CM 的 MAE 0.2073 只覆盖低 ε 的组成区间，**不能当作全数据集的精度**；富水/高 ε 混合物在 CM 下形式无定义。Lichtenecker 才是全点有定义的规则。

### 6.4 残差按氢键能力分层（本轮最干净的物理结论）

| 类别 | 点数 | 对 | 残差 vs Lichtenecker（中位，95% CI） | 残差 vs CM（中位，95% CI） |
|---|---|---|---|---|
| 无质子给体 | 550 | 11 | **+0.0886** [0.0746, 0.1000] | +0.1017 [0.0771, 0.1308]（n=264） |
| 含质子给体 | 1 728 | 25 | **+0.2442** [0.2032, 0.2894] | +0.2112 [0.0990, 0.3890]（n=54） |

两个结论：

1. **残差系统性为正**——实测 ε 总是高于任何理想混合规则。
2. **含氢键给体的混合物偏离更大**（0.244 vs 0.089），且两者的 95% CI **不重叠**。

这正是单分子描述符**结构上看不到**的量：混合后增强的偶极关联。**等级：`SUPPORTED`**（不是 `CONFIRMED`）——因为 2 278 个点来自 36 个对/13 个 DOI，点间不独立，CI 是按点自助法算的，偏乐观。

### 6.5 不能说什么

- 不能把残差换算成"缔合参数"或 Kirkwood g——规则不是从混合物分子模型导出的
- 不能把混合物记录放进单分子 ε 训练集
- 纯物质参考 ε 有 58.5% 来自另一项研究（跨来源拼接**只发生在参考端**，逐行有 `pure_eps_same_doi_*` 标记）

---

## 7. 多尺度消融（B748）——一个结论被自己推翻

### 7.1 结果

| 集合 | 配置 | n | MAE | R² | 增益 |
|---|---|---|---|---|---|
| 全队列 | X0 | 239 | 7.0072 | 0.083 | — |
| 全队列 | X0+X1 | 239 | **5.1077** | **0.322** | **+1.8995** |
| X2 面板 | X0+X1 | 39 | 2.9947 | 0.634 | — |
| X2 面板 | X0+X1+X2 | 39 | 3.3767 | 0.551 | **−0.382** |
| X3 面板 | X0+X1 | 22 | 4.5627 | 0.452 | — |
| X3 面板 | X0+X1+X3 | 22 | 4.5859 | 0.364 | **−0.0232** |

### 7.2 结论翻转

- 修复 M 之前：X3 面板 n=14，增益 **+0.9413**（"液相性质层有帮助"）
- 修复 M 之后：X3 面板 n=22，增益 **−0.0232**（"没有帮助"）

原因不是物理变了，而是**样本选择变了**：原来 n=14 的分子是"同时有 ε、ρ、n_D、DFT α"的那批，几乎全是 CORE239 里数据最全的分子；补上 M 兜底后更多新分子进来，增益消失。**早先的正增益是小样本选择效应。**

### 7.3 全层交集

所有层都有值的分子 = **5** → `statistical_power: INADEQUATE`，并在 JSON 写入 `selection_bias_warning`："COMMON_SUBSET 的 MAE 不可与全队列 MAE 比较"。

契约测试断言：`n_common_subset < 10` 时 `statistical_power == INADEQUATE`；`n < 20` 的面板不得标 `ADEQUATE`；配对增益必须由同面板配对运行算出。

---

## 8. 新分子迁移测试（B748-02 / RQ6）

问题：在 CORE239 上拟合的模型，能不能预测那 67 个新分子？

### 8.1 控制

- 特征层对两个队列用**同一段代码**重算（RDKit），避免"特征定义差异"冒充"迁移效应"
- 去掉 `morgan2_nbits`：该列是整数，其指纹参数未记录在 v7.0 产物里，新分子无法同口径重算
- 离子液体**单独报告**：67 个里有 25 个是盐，CORE239 里没有离子液体
- V_m 描述符重实现校验：与存档值中位相对差 **0.56%**（最大 1.5%）

### 8.2 结果

| 评估 | n | MAE | R² | 偏差（预测−实测） |
|---|---|---|---|---|
| CORE239 十折 CV | 239 | 7.1696 | **0.0085** | +0.03 |
| 迁移（全部） | 65 | 11.7905 | 0.2727 | **−10.06** |
| 迁移（中性有机物） | 38 | 11.1457 | 0.2122 | −8.94 |
| 迁移（离子液体） | 27 | 12.6980 | 0.3709 | −11.64 |

### 8.3 误差结构说明真因

- 残差 vs 实测 ε 的 Pearson r = **−0.8191**（典型回归均值特征）
- ε ≥ 15 的一半：n=35，MAE **16.10**，偏差 **−15.01**
- ε < 15 的一半：n=30，MAE 6.77，**但常数基线 MAE 只有 3.33**（模型比"猜均值"还差，R² 为负）

**结论不是"新分子难"，而是"只有结构层的模型本身没有 ε 能力"**（CORE239 自身 CV R² 只有 0.0085）。真正携带极性信息的是 X1（偶极/极化率/能隙），而这 67 个新分子**还没有 DFT 层**。

**等级：`CONFIRMED`（负结果）**。这一条直接定义了下一步：不是换模型，而是**补新分子的电子层**。证据：`outputs/b740_expansion/transfer/transfer_summary.json`。

---

## 9. MD 前检（B747）——`BLOCKED_FOR_POLARIZABLE_MD`

| 检验 | 判据 | 可评 | 通过 | 结论 |
|---|---|---|---|---|
| T1 密度 | 相对误差 ≤3% | 7 | 3 | PARTIAL（中位 6.73%） |
| T2 介电 | 相对误差 ≤15% | 12 | **1** | **FAIL**（中位 53.3%，11/12 低估，平均 −3.905） |
| T3 Kirkwood 合理性 | 0<g<100 | 12 | 12 | PASS |

物理原因清楚：固定电荷力场没有显式诱导极化，无法产生集体偶极响应。

**合法用法**：作为"非极化模型在介电响应上失败"的**负对照**；密度作结构检查。
**非法用法**：引用 ε_md 当预测值；用其 g_K 解释 g_apparent；声称做过 Kirkwood 对比。

**等级：`BLOCKED`（诚实阻塞）**。没有极化/Drude/涨落电荷力场可用（`openmm` 在，`openff.evaluator`/`mdtraj`/`parmed` 不在）。

---

## 10. 计算层执行状态（B742 ORCA）

新分子的 r²SCAN-3c 层已**建包**并开始执行，但**结果尚无**，因此不作为结论引用。

| 项目 | 状态 |
|---|---|
| 目标分子 | 67（全部 `NEW_MOLECULE_VALIDATED`） |
| 输入包 | `outputs/b740_expansion/dft_expansion/package_opt/`（67 个 `jobs/<IK>/{geom.xyz,job.inp}`） |
| 方法 | r²SCAN-3c `Opt` + `%elprop Polar 1` |
| 起始几何 | RDKit ETKDG(seed 42) + MMFF（**与 CORE239 的 GFN2-xTB 起始几何不同**，已写入 manifest） |
| 为什么不建 sp 层 | b700 的 `sp` 定义是"在 GFN2-xTB 几何上做单点"；新分子没有 xTB 几何，同名不同义会污染层定义 |
| 集群 | `pengqihang@202.114.96.180`，hpxg，`--ntasks=4 --cpus-per-task=1` |
| 提交状态 | 试点 `--array=1`：job **`4592091`**（RUNNING, n0356）；其余 `--array=2-9`：job **`4592244`**（2/3/4 RUNNING，5–9 PENDING，触发 `QOSMaxCpuPerUserLimit`＝每用户最多 4 个并发数组任务） |
| 结果状态 | **`SUBMITTED_RUNNING_RESULTS_NOT_COLLECTED`** —— 尚无任何新分子描述符可引用 |
| 记录文件 | `package_opt/submission_record.json`（含回收步骤；sbatch 脚本会跳过已完成作业，重提幂等） |

**已修的部署 bug**：`joblist.txt` 在 Windows 文本模式下写成 CRLF，Slurm 端每条路径都带 `\r`，8 个作业全部 `cd ... No such file or directory` 后继续。改为显式 LF 后试点正常启动。

---

## 11. 验收问题（Q1–Q24）

> 编号按 v7.4 计划的六 RQ 结构、每 RQ 四问排列（Q1–Q4 = RQ1，…，Q21–Q24 = RQ6）。若原编号顺序不同，按 RQ 对应即可。每条给出等级与证据文件。

### RQ1 单分子电子极限

| # | 问题 | 回答 | 等级 |
|---|---|---|---|
| Q1 | 极化率张量是否已算且自洽？ | 478 条记录，对称 478/478，迹/本征值/Å³ 换算均在 6×10⁻⁶ 内闭合 | `CONFIRMED` |
| Q2 | 各向异性是否分层？ | 芳香 0.626 → 醇 0.221，10 个家族单调合理 | `SUPPORTED` |
| Q3 | 电子层对 ε 是否有增益？ | CORE239 内 MAE 7.0072→5.1077（+1.90），R² 0.083→0.322 | `CONFIRMED` |
| Q4 | 四极矩是否计算？ | **未计算**（本轮 B742 只做极化率张量） | `NOT_IMPLEMENTED` |

### RQ2 构象与分子内效应

| # | 问题 | 回答 | 等级 |
|---|---|---|---|
| Q5 | S_conf/N_eff/N_PR 是否计算？ | 39 个分子；S_conf 中位 10.58 J/mol/K；N_eff≈3.4–4.7 | `CONFIRMED` |
| Q6 | 构象层是否改善 ε？ | **否**，配对增益 −0.382（n=39） | `CONFIRMED`（负） |
| Q7 | 分子内氢键是否量化？ | 33 个分子有几何判据；占据率中位 0.0（气相构象大多无分子内氢键） | `SUPPORTED` |
| Q8 | 构象熵是否被误当热力学熵？ | 否，`is_gibbs:false`，注释明确；且该层无增益 | `CONFIRMED` |

### RQ3 凝聚相关联

| # | 问题 | 回答 | 等级 |
|---|---|---|---|
| Q9 | Kirkwood–Fröhlich g_app 能否复算？ | 194 行复算，最大相对差 0.61%（存储舍入级） | `CONFIRMED` |
| Q10 | g_app 是否按家族呈两方向体制？ | 醇 3.47 / 胺 3.09 ↔ 羧酸 0.35 / 腈 0.69，按氢键能力分裂 | `SUPPORTED` |
| Q11 | g_app 是否等于 Kirkwood g？ | **不是**，用的是气相 μ，命名刻意保留 "apparent" | `REFUSED` |
| Q12 | 强关联假设能否检验？ | 本地数据不足以分离取向相关与 μ 误差 | `UNRESOLVED` |

### RQ4 液体热力学

| # | 问题 | 回答 | 等级 |
|---|---|---|---|
| Q13 | V_m 是否可靠？ | 50/51 由实测密度换算；水 18.05 cm³/mol；分子式 M 与描述符 M 重叠 102 例最大差 0.007 g/mol | `CONFIRMED` |
| Q14 | 摩尔折射是否与 DFT α 一致？ | n=22，r=0.9972，MAE 1.137 Å³（含 n_D vs 静态近似告诫） | `CONFIRMED` |
| Q15 | Δf 与 dε/dT 是否可用？ | 40 / 40 个分子；97.5% 的 dε/dT 为负 | `SUPPORTED` |
| Q16 | CED/Hildebrand 是否可得？ | **不可得**：本地语料 0 条焓蒸发热记录 | `NOT_TESTABLE` |

### RQ5 多频响应

| # | 问题 | 回答 | 等级 |
|---|---|---|---|
| Q17 | 频率相关 ε 是否被正确分离并排除？ | 1 109 条/93 分子单列，静态行含频率标记数 = 0，两组不相交 | `CONFIRMED` |
| Q18 | 多频介电谱能否建模？ | 仅 46 条频率相关记录带明确频率值，无谱覆盖 | `NOT_TESTABLE` |
| Q19 | 混合物 ε 是否服从理想混合？ | 否：Lichtenecker MAE 0.728、线性 1.115、CM 0.207（仅 14% 组成域有定义） | `CONFIRMED` |
| Q20 | 混合偏离是否随氢键能力增大？ | 是：含质子给体 +0.244 vs 无给体 +0.089（CI 不重叠） | `SUPPORTED`（点不独立） |

### RQ6 筛选可靠性

| # | 问题 | 回答 | 等级 |
|---|---|---|---|
| Q21 | 来源独立性阻塞是否解除？ | **部分解除**：67 个新分子（17 个 ≥2 原始 DOI），但"独占来源集合"仍为 0 篇 | `PARTIALLY_RESOLVED` |
| Q22 | MD 能否给出介电？ | 否，T2 1/12 通过，11/12 低估，仅作负对照 | `BLOCKED` |
| Q23 | 多尺度分层是否有增益？ | 只有 X1 有（+1.90）；X2 \(−0.382\)、X3 \(−0.0232\)（修复后翻转）；全层交集 n=5 `INADEQUATE` | `MIXED` |
| Q24 | 新分子迁移是否成立？ | 结构层无迁移能力（CV R² 0.0085；迁移 MAE 11.79、偏差 −10.06、残差-实测 r=−0.82）；需电子层，包已建、试点运行中 | `CONFIRMED`（负） |

**未回答 / 未实现的问题清单（不掩盖）**：
- 四极矩（Q4）：未实现
- 多频谱（Q18）：数据不足
- CED/Hildebrand（Q16）：数据为 0
- 强关联分解（Q12）：方法不足
- 67 个新分子的 DFT 层：已提交试点，结果未回

---

## 12. 本轮自纠错清单（全部已定位并修正）

| # | 错误 | 后果 | 修正 | 位置 |
|---|---|---|---|---|
| 1 | 静态与频率相关介电常数合并 | 1 109 条频率数据冒充静态 ε | 拆成两个 `property` 值 | `scan_thermoml_local.py` |
| 2 | 按逗号判断混合物 | 45 个 IUPAC 名被误判为混合物 | 只认 `;` | `scan_thermoml_local.py` |
| 3 | ThermoML 标签假设错误（`VariableID`/`PropertyID`） | 解析出 0 条记录 | 改用 `nPropNumber`/`nVarNumber` | `scan_thermoml_local.py` |
| 4 | 新分子无 M → V_m 空白 | `molar_refraction` 只有 14 个分子 | 从 ThermoML 分子式算 M（多组分/带电拒绝） | `compute_molar_refraction.py` |
| 5 | `row_best` 取第一个可用温点 | 有 n 无 ρ 的温点覆盖了 n+ρ 都有的温点 | 按"完整度→|ΔT|"择优 | `compute_molar_refraction.py` |
| 6 | 焓蒸发热被描述为"稀疏" | 实际是 0 条，措辞低估了缺口 | 改为 `NOT_TESTABLE` 并写明 0 记录 | `compute_molar_refraction.py` |
| 7 | 离子液体用净电荷判断 | 盐的净电荷为 0，25 个 IL 全被当"中性" | 改用片段数 >1 | `run_new_molecule_transfer.py` |
| 8 | `joblist.txt` 写成 CRLF | Slurm 端 8 个作业全部 `cd` 失败 | 显式 LF 写字节 | `build_new_orca_package.py` |
| 9 | 混合规则用 `eVariableType` 标签 | 该标签不存在，0 条混合物被识别 | 改看叶标签名（`eTemperature`/`eComponentComposition`） | `analyze_mixture_dielectric.py` |

**纪律**：以上每条都在对应脚本注释里就地记录，不是事后补写。

---

## 13. 下一步（只写"必须做"的，不做承诺）

1. **回收集群上 67 个新分子的 DFT 层**（试点通过 → 提交 `--array=2-9` → 拉回 `job.out` → 解析 dipole/polarizability/HOMO-LUMO），然后重跑 §8 迁移测试并做 X0+X1 迁移消融。**这是唯一能把 Q24 从负结果变成可判定的动作。**
2. 用新分子的电子层重跑 §7 的全层交集，看 X3 面板是否能摆脱 n=22 的 `INADEQUATE`。
3. CED/Hildebrand 只能靠外部数据源（NIST WebBook / DIPPR）补齐，本地语料为 0。
4. 四极矩（Q4）需要 ORCA 的 `%elprop Quadrupole` 或 traceless 二次矩计算，本轮未做。
5. 混合物分析需要把点级自助法换成**按对聚类**的自助法，以匹配"点不独立"的事实。

---

## 14. 复现

```bash
# 数据侧
python scripts/b740_expansion/scan_thermoml_local.py
python scripts/b740_expansion/build_molecule_candidates.py
python scripts/b740_expansion/resolve_new_structures.py
python scripts/b740_expansion/compute_polarizability_tensor.py
python scripts/b740_expansion/compute_conformer_entropy.py
python scripts/b740_expansion/compute_molar_refraction.py
python scripts/b740_expansion/analyze_mixture_dielectric.py
python scripts/b740_expansion/validate_md_convergence.py
python scripts/b740_expansion/run_feature_ablation.py
python scripts/b740_expansion/run_new_molecule_transfer.py
python scripts/b740_expansion/build_new_orca_package.py

# 测试
python -m pytest tests/test_b740_expansion -q          # 44 passed
# 轮次门禁（与 v7.3 同范围）
python -m pytest tests/test_b700_orca tests/test_b710_evidence \
                 tests/test_b720_external tests/test_b730_mechanism \
                 tests/test_b740_expansion -q          # 167 passed in 2.1s
```

依赖顺序：`scan` → `build_molecule_candidates` → `resolve_new_structures` →（`compute_conformer_entropy` / `compute_molar_refraction` / `analyze_mixture_dielectric`）→（`run_feature_ablation` / `run_new_molecule_transfer`）。`compute_polarizability_tensor` 依赖 b700 的 ORCA 结果，独立于本链。

**全部 45 条契约测试覆盖**：静态/频率分离、混合物排除、语料"SUBSET"声明、队列准入规则、CORE239 身份不变、极化率张量四条恒等式、构象统计四条恒等式（含 `is_gibbs:false`）、V_m 物理范围与依赖列空值纪律、R_m/α_LL/Δf 定义式、Kirkwood 复算、V_m 来源分离、g_app 拒绝而非爆炸、MD `BLOCKED` 与禁止用法、多尺度选择偏差守卫、迁移的统计口径、结构身份校验、混合规则算术、以及 v6.0/v7.0/v7.2/v7.3 与外部原始数据的哈希不变。
