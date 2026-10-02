# Understanding Electrolyte Materials through Decision-Centric Ranking Stability
## 从分子级代理量、环境条件态到不确定性感知筛选的技术研究方案（v2）

**文件名：** `understanding-electrolyte-materials-v2.md`  
**版本日期：** 2026-09-28  
**研究定位：** 固定背景电解液环境下的候选小分子/共溶剂/添加剂；以材料筛选决策的稳定性为核心，而非直接宣称预测完整电池性能。

## 摘要

电解液分子计算筛选经常使用 HOMO/LUMO、气相离化能/电子亲和能、偶极矩、静电势、Li$^+$ 配位能等廉价分子级指标，再利用机器学习扩展到更大化学空间。然而，真实电解液中的氧化还原行为受到溶剂化、Li$^+$ 配位、盐阴离子、构象分布、局域溶剂化结构、界面电场和反应动力学等因素共同影响。一个低成本模型即使数值误差不小，也可能仍能正确保留候选排序；相反，一个平均误差很小的模型，也可能在性质高度密集的候选区域频繁改变材料选择。因此，材料筛选真正需要回答的并不只是“数值能否预测准确”，而是“**哪些缺失物理会真正改变材料决策，以及恢复目标排序最低需要多少昂贵信息**”。

本课题据此将原来的一维“高低 fidelity ladder”重构为三个相互独立的层次：第一是**代理量/电子结构层**，研究从廉价 scalar proxy 到较严格的分子氧化还原自由能；第二是**环境与物种条件层**，分别研究自由分子、固定连续介质和 Li$^+$ 配位条件态，而不把 $[\mathrm{Li}M]^+$ 自动视为“更真实的同一物种”；第三是**外部 reference layer**，利用实验或更高层计算 anchor 判断某一 target model 是否真正更接近可观测量。由此严格区分

$$
\boxed{
\text{model complexity}
\neq
\text{accuracy}
\neq
\text{physical representativeness}
}
$$

以及

$$
\boxed{
\text{different conditional species}
\neq
\text{different-fidelity estimates of the same observable}
}.
$$

研究重点从 MAE/$R^2$ 转向 uncertainty-aware Kendall $\tau_b$、robust pairwise inversion、Top-$k$ overlap、selection regret、unresolved-pair fraction 和 decision error，并显式审计 feature cost，避免用接近目标层成本的特征去证明“低成本预测”。进一步采用 $\Delta$-learning 和主动学习，研究在给定 target model 下恢复材料排序所需的最小昂贵标签预算。

本项目不以“找到一个综合性能最好的电解液”为必要成功条件。若低成本模型已经稳定保留排序，则得到其适用域；若排序发生稳健翻转，则识别导致决策改变的缺失物理；若 $\Delta$ 无法由廉价表示学习，则说明现有 descriptor 缺失关键环境信息；若电子添加/移除后发生配位切换、断键或状态身份改变，则进一步表明平滑连续回归本身失效。上述任一结果都能形成可证伪、可解释并可迁移的方法学结论。

# 1. 背景：从“预测性质”到“判断筛选是否可靠”

## 1.1 电解液高通量计算已经成熟，但“筛选标签是否足够”仍是核心问题

量子化学、高通量自动化和机器学习已经广泛进入电解液分子发现。Electrolyte Genome 等早期工作建立了大规模分子量子化学筛选流程；Korth 2014 直接用高层 WFT reference 审计低成本 SQM/DFT 在大规模筛选中的适用性，Husch 等 2015 又将 collective properties 和 Pareto-optimal filtering 纳入筛选。因此，“低成本模型是否足以支持材料选择”以及“多指标如何改变候选集合”并不是新的问题。近年来，机器学习进一步扩展到溶剂化、输运、界面化学和配方设计，并逐渐强调物理可解释 descriptor、chemical-space coverage 与 extrapolation evaluation。

因此，本项目并不把“使用 ranking metric”本身作为创新，也不把“考虑 Li$^+$ 配位”本身作为创新。后者已经有直接先例：2025 年 Yang 等系统比较了有/无 Li$^+$ 配位的电解液分子 redox potential 并构建机器学习模型。真正尚值得系统回答的问题是：

> **从廉价代理量到更丰富的电子结构与环境模型时，哪些改变只是数值 offset，哪些改变会产生超出方法不确定性的稳健 rank inversion？在给定 target model 或实验 anchor 下，恢复筛选决策最低需要多少昂贵计算？**

这比“训练一个模型预测 redox potential”更接近材料发现真正的决策问题。

## 1.2 数值准确与决策准确不是同一件事

设两个模型 $A$ 和 $B$ 对同一目标量给出 $P_A(i)$ 与 $P_B(i)$。传统评价通常关注

$$
\mathrm{MAE}(A,B)
=
\frac{1}{N}\sum_i |P_A(i)-P_B(i)|.
$$

但材料筛选常常只需要决定：

- 哪些候选进入后续昂贵计算；
- 哪些候选进入 Top-$k$；
- 哪些候选满足外部阈值；
- 两个候选中哪个更值得优先实验验证。

例如，若

$$
P_B(i)=P_A(i)+c
$$

近似成立，即使常数偏差 $c$ 很大，所有候选排序仍保持不变，模型 $A$ 仍可能是优秀的 pre-screening model。反之，在密集候选区域，即使 MAE 很小，也可能有大量 pairwise order reversal。

因此本项目始终区分

$$
\boxed{
\text{value error}
\neq
\text{ranking error}
\neq
\text{decision error}
}.
$$

## 1.3 “更复杂”不等于“更接近真实”

原始方案容易把“逐步加入更多物理因素”称为“更高 fidelity”，并进一步默认其排序就是更正确的排序。v2 明确取消这一逻辑捷径。

例如，$[\mathrm{Li}M]^+$ 比自由分子 $M$ 多包含了 Li$^+$ 局域配位物理，但若真实体系中该分子的主要 population 并非 1:1 配位态，那么 $[\mathrm{Li}M]^+$ 并不自动比自由分子模型更接近实验。类似地，一个更昂贵的电子结构方法如果没有经过外部 benchmark，也只能称为更高成本/更高理论层级，而不能自动称为 ground truth。

因此全文使用：

- **model/physics hierarchy**：表示加入了什么模型成分；
- **target model**：本阶段希望被低成本模型重现的指定模型；
- **reference layer**：由实验或更高等级计算提供、用于判断 accuracy 的外部锚点。

只有通过 reference layer 验证后，才讨论“更接近实验”或“更准确”。

# 2. 研究定位与边界

## 2.1 MVP 的对象：固定背景中的候选小分子/共溶剂/添加剂

为了避免“每个候选既是被研究分子、又定义自己的 bulk solvent 环境”这一混杂问题，第一阶段统一把所有候选解释为：

> **处于同一固定参考电解液背景中的候选小分子、共溶剂或添加剂。**

EC、PC、DMC、DME、sulfolane 等常见主溶剂仍可以作为 recognizable anchors，但在本项目的 common-embedding comparison 中，它们同样接受相同背景环境；这是一种受控比较，不等价于预测各自 neat-liquid 电解液中的真实行为。

这样，研究问题首先是：

$$
\text{molecular identity}
\rightarrow
\text{conditional molecular redox thermodynamics}
\rightarrow
\text{ranking stability}.
$$

而不是：

$$
\text{molecule}
\rightarrow
\text{complete battery performance}.
$$

## 2.2 本项目能够回答什么

第一阶段可以严格回答：

1. 廉价 scalar proxy 对自由分子/固定介质 redox thermodynamic proxy 的排序保持程度；
2. 固定连续介质引起的 rank shift 是否具有 family dependence；
4. 条件 Li$^+$ 配位对同一候选的 redox free-energy proxy 引起多大改变；
5. 哪些 pairwise inversions 超出方法不确定性、属于 robust inversion；
6. 哪些分子结构特征与稳健 inversion 有关；
7. 在指定 target model 下，多少昂贵 labels 足以恢复 Top-$k$ 或整体排序；
8. 这种恢复在同 family 插值与跨 family 外推之间是否显著不同。

## 2.3 第一阶段明确不声称什么

不能从本项目第一阶段直接声称：

- 某分子具有真实更宽的 electrochemical stability window；
- 某分子一定形成更优 SEI/CEI；
- Li$^+$ 配位越强越好；
- 某分子一定具有更高离子电导或更低黏度；
- $[\mathrm{Li}M]^+$ 的 redox quantity 就是实际浓度电解液的有效 redox potential；
- 某个 target-model ranking 就是真实实验 ranking。

这些结论需要盐浓度、阴离子、局域 population、界面电场、反应动力学乃至电极表面等额外信息。

# 3. 三层研究框架：代理量/电子结构、环境条件态与外部参考

v2 不再使用单一的 $L_0\rightarrow L_4$ 线性 ladder，而采用下列三层结构。

## 3.1 Axis A：proxy / electronic-structure hierarchy

这一轴只比较**尽可能相同的条件态和目标物理量**，主要改变电子结构/性质定义的精细程度。

### $P_0$：cheap scalar proxy

$P_0$ 必须是可以排序的**标量代理量**，而不能把一组 descriptors 当成一个“fidelity level”。例如可定义：

$$
P_0^{\mathrm{ox}}
=
-\varepsilon_{\mathrm{HOMO}}
$$

作为 oxidation-related cheap proxy；对于 reduction，可分别测试

$$
P_0^{\mathrm{red}}
=
\varepsilon_{\mathrm{LUMO}}
$$

作为与“越大越难发生一电子还原”同方向的 Koopmans-like proxy，或使用符号经过同样统一的 xTB vertical electron-attachment proxy。

这些量不被解释为真实 redox potential，只用于回答：**极低成本 scalar proxy 是否已经保留目标排序？**

偶极矩 $\mu$、极化率 $\alpha$、ESP、分子体积、fingerprint 等属于 features，不属于 $P_0$ 本身。

### $P_1$：gas-phase molecular redox thermodynamics

定义自由分子的氧化/还原自由能代理量：

$$
\Delta G_{\mathrm{ox}}^{\mathrm{gas}}(M)
=
G_{\mathrm{gas}}(M^+)-G_{\mathrm{gas}}(M),
$$

$$
\Delta G_{\mathrm{red}}^{\mathrm{gas}}(M)
=
G_{\mathrm{gas}}(M^-)-G_{\mathrm{gas}}(M).
$$

若气相阴离子不是稳定电子束缚态，则该候选在这一层标记为 `unbound_anion`，而不是强制给出伪精确 adiabatic EA。

### $P_2$：fixed-background continuum molecular redox thermodynamics

在统一背景介质中定义：

$$
\Delta G_{\mathrm{ox}}^{\mathrm{cont}}(M)
=
G_{\mathrm{cont}}(M^+)-G_{\mathrm{cont}}(M),
$$

$$
\Delta G_{\mathrm{red}}^{\mathrm{cont}}(M)
=
G_{\mathrm{cont}}(M^-)-G_{\mathrm{cont}}(M).
$$

该层用于研究同一分子加入共同 embedding 后的 rank shift，而不是模拟每个候选自己的 neat-liquid bulk environment。

## 3.2 Axis B：environment / conditional-species hierarchy

这一轴不称为“同一 observable 的更高 fidelity”，因为环境变化可能同时改变 chemical species。

### $C_0$：free molecular state

目标物种为自由候选分子 $M$。

### $C_1$：Li$^+$-coordinated conditional state

目标物种为 $[\mathrm{Li}M]^+$ 及其相应 redox states。其作用是回答条件问题：

> **如果候选分子处于 Li$^+$ 配位态，其 redox thermodynamic proxy 相对于自由态如何变化？**

对氧化：

$$
\Delta G_{\mathrm{ox}}^{\mathrm{free}}
=
G(M^+)-G(M),
$$

$$
\Delta G_{\mathrm{ox}}^{\mathrm{Li}}
=
G([\mathrm{Li}M]^{2+})-G([\mathrm{Li}M]^+),
$$

并定义 conditional coordination shift：

$$
\Delta\Delta G_{\mathrm{ox}}^{\mathrm{coord}}
=
\Delta G_{\mathrm{ox}}^{\mathrm{Li}}
-
\Delta G_{\mathrm{ox}}^{\mathrm{free}}.
$$

对还原：

$$
\Delta G_{\mathrm{red}}^{\mathrm{free}}
=
G(M^-)-G(M),
$$

$$
\Delta G_{\mathrm{red}}^{\mathrm{Li}}
=
G([\mathrm{Li}M]^0)-G([\mathrm{Li}M]^+),
$$

$$
\Delta\Delta G_{\mathrm{red}}^{\mathrm{coord}}
=
\Delta G_{\mathrm{red}}^{\mathrm{Li}}
-
\Delta G_{\mathrm{red}}^{\mathrm{free}}.
$$

这里的 $\Delta\Delta G^{\mathrm{coord}}$ 是本项目最重要的环境响应量之一。

### $C_2$：selected explicit microsolvation states

只对少量代表体系构造相同化学计量下的显式局域溶剂化 cluster，用于判断 $C_1$ 的 1:1 配位图像是否对关键 inversion 结论稳健。

第一阶段**不**把不同配位数、不同阴离子数、不同化学计量的 clusters 用裸 Gibbs energy 混在一起做简单 Boltzmann 平均。若后续要处理真实 population，应转向显式 MD/statistical-mechanical treatment。

## 3.3 Axis C：external reference layer

这一层用于判断 accuracy，而非定义模型复杂度。

### $R_{\mathrm{gas}}$

选择若干小分子，使用实验 gas-phase IP/EA 或可靠更高层电子结构结果作为 anchor，用于审计 $P_1$。

### $R_{\mathrm{sol}}$

选择约 10–20 个具有尽可能统一溶剂、盐浓度、温度与 reference electrode 条件的实验 solution redox 数据，作为 $P_2$ 的外部 anchor。

不同实验条件无法严格统一时，不强行合并成单一绝对 benchmark，而应把条件信息保存在 metadata 中，并优先比较相同实验系列中的相对排序。

### $R_{\mathrm{env}}$

对于少量典型 Li-coordination cases，可使用已发表的 explicit-cluster、溶液模拟或相关实验趋势作为定性/半定量 anchor。第一阶段不要求这一层完整覆盖全部候选。

# 4. 目标量与方向定义

## 4.1 氧化与还原必须分别定义“筛选方向”

若定义

$$
S_{\mathrm{ox}}(M)
=
\Delta G_{\mathrm{ox}}(M),
$$

则 $S_{\mathrm{ox}}$ 越大表示一电子氧化越困难。

对于还原，为使“越大越稳定”的方向与氧化一致，可定义

$$
S_{\mathrm{red}}(M)
=
\Delta G_{\mathrm{red}}(M)
=
G(M^-)-G(M).
$$

当电子附着越不利时，$S_{\mathrm{red}}$ 越大，因此在本项目的**完整分子一电子热力学 proxy**语境中可以解释为更难发生该一电子还原。

所有 Top-$k$、selection regret 和 threshold metric 必须分别记录 `objective_direction`，不允许在代码中默认“所有指标越大越好”。

## 4.2 这些目标量不是完整 electrochemical stability window

本项目研究的是：

> **intact-species / conditional-species one-electron redox thermodynamic proxies**。

真实电解液分解可能涉及 solvent–anion charge transfer、质子/氢转移、协同断键、表面催化、EDL enrichment 和 SEI/CEI passivation。已有研究已经显示，多组分耦合和界面 population 可以改变实际分解顺序。因此正文与输出图中避免把 $S_{\mathrm{ox/red}}$ 简写为“真实稳定窗口”。

# 5. 数据集设计

## 5.1 双层数据结构

v2 将数据分为两个规模层级。

### Core paired benchmark set

建议 $N_{\mathrm{core}}\approx60$–100。

这些分子完成主要的 $P_0$、$P_1$、$P_2$ 以及 $C_1$ conditional Li-coordination calculations，用于严格的 paired rank comparison。

### Broad cheap pool

建议 $N_{\mathrm{pool}}\approx300$–1000，视自动化和资源而定。

只计算廉价结构 descriptor、xTB proxy，必要时加 free-molecule DFT。该 pool 用于真正测试：

$$
\text{从大候选池中如何选择最值得做昂贵 }C_1\text{ 或 }P_2\text{ 的点？}
$$

若项目时间有限，broad pool 可以只做到 $P_0$，但结构和 metadata 仍应一次性建立。

## 5.2 Chemical-space metadata 必须是多轴而非单一 family

每个候选至少保存：

| 字段 | 含义 |
|---|---|
| `molecule_id` | 唯一编号 |
| `canonical_smiles` | 规范结构 |
| `structural_family` | carbonate / ether / nitrile / sulfone / phosphate 等互斥主家族 |
| `functionalization_tags` | fluorinated / unsaturated / cyclic / chelating 等可多选标签 |
| `use_role` | solvent / co-solvent / additive / anchor |
| `donor_atoms` | 潜在 Li 配位原子 |
| `formal_charge` | 母分子形式电荷 |
| `rotatable_bonds` | 柔性指标 |
| `conformer_count` | 进入 QC 的构象数 |
| `Li_motif_count` | 配位异构体数 |
| `state_identity_status` | redox 状态身份 QC |
| `reactivity_status` | intact / motif switch / dissociation 等 |
| `qc_status` | 各模型层计算状态 |

“fluorinated analogues”不再作为与 carbonate/ether 平行的 structural family，因为氟化是一种跨家族 functionalization。

## 5.3 样本选择原则

Core set 需要同时覆盖：

- 不同 donor atom 类型；
- 单齿与潜在双齿配位；
- 不同极性和极化率；
- 刚性与柔性分子；
- 同家族内部的系统取代；
- 跨家族的结构差异；
- 若干常见电解液分子作为 anchors。

不能用一个母骨架枚举几十个极相似衍生物，再随机切分 train/test。

# 6. 构象与状态采样

## 6.1 母分子构象

建议流程：

1. canonical SMILES 生成 3D 初始结构；
2. CREST/GFN2-xTB 做构象搜索；
4. 在预设能量窗口内保留候选；
5. 根据结构/扭转角/RMSD 聚类；
6. 选择约 3–10 个独立低能构象进入 DFT；
7. neutral、cation、anion 不假定共享同一个最优构象空间。

如果柔性分子较多，应显式比较：

$$
\text{single minimum}
\rightarrow
\text{small conformer ensemble}
\rightarrow
\text{expanded ensemble}
$$

是否改变候选排序。这本身就是“达到稳定决策所需的最小采样复杂度”问题的一部分。

## 6.2 构象 ensemble

同一 charge state、同一化学计量、同一模型下，可定义

$$
G_q^{\mathrm{ens}}
=
-RT\ln\sum_i g_i
\exp\left(-\frac{G_{q,i}}{RT}\right).
$$

不同 charge states 分别建立 ensemble，最终 redox quantity 由 ensemble free-energy difference 得到，而不是强制一一对应同一 conformer。

## 6.3 Li$^+$ 配位 motif 生成

对每个候选：

1. 识别 O/N/S/P 等 donor atoms；
2. 对每个 donor 生成单齿 Li$^+$ 初始位点；
4. 对几何允许的 donor pairs 生成双齿候选；
5. 根据 molecular ESP minima 补充可能遗漏的位点；
6. xTB 预优化；
7. 依据 Li–donor connectivity、关键距离、结构相似度和能量去重；
8. 将若干低能 motif 送入 DFT；
9. 对不同 redox states 重新允许 motif relaxation，而不是机械固定 neutral-state 配位方式。

## 6.4 State identity QC

$[\mathrm{Li}M]^+ + e^-$ 后得到的 $[\mathrm{Li}M]^0$ 并不保证新增电子仍是“分子还原”。因此每个 redox state 必须保存：

- fragment charge；
- spin density；
- SOMO/LUMO 或相应 frontier-state localization；
- Li–M 键合变化；
- connectivity；
- 主要电子密度变化区域。

至少分成：

- `molecule_centered_redox`；
- `Li_centered_or_mixed_redox`；
- `motif_switch`；
- `no_intact_minimum_found`；
- `dissociated_optimized_product`；
- `reaction_path_verified`。

只有经过额外 reaction-path/TS/动力学证据时，最后一种才可被解释为已验证反应路径。几何优化导致断键本身不能证明实际溶液中该反应无势垒或足够快。

# 7. 量子化学方法与方法审计

## 7.1 原则：先做 method audit，再冻结 production protocol

生产计算前选择约 8–10 个 benchmark molecules，覆盖主要 structural families、柔性程度和配位模式。

审计至少包含：

- 两种合理 DFT functionals；
- 至少两个 basis-set 级别或 diffuse-basis variants；
- continuum model sensitivity；
- gas-phase external anchor；
- 若可得，solution experimental anchor。

需要区分：

$$
\text{method sensitivity}
$$

与

$$
\text{method accuracy}.
$$

前者只需比较不同合理方法；后者必须依赖外部 reference。

## 7.2 几何与频率建议

可将

$$
\mathrm{r^2SCAN\text{-}3c}
$$

作为几何与频率的生产起点，因为成本适中且适合较大批量有机分子。但这一选择仍需 benchmark set 验证。

每个状态检查：

- SCF convergence；
- geometry convergence；
- imaginary frequencies；
- spin contamination；
- connectivity change；
- 波函数稳定性（至少对异常样本）；
- redox-state localization。

## 7.3 单点电子能建议

可从 range-separated hybrid + triple-$\zeta$ basis 作为生产候选，例如 $\omega$B97X-D4 一类方案，但最终方法必须由 audit 冻结，而不是凭习惯选择。

对于阴离子必须单独建立 diffuse-basis protocol。至少对 benchmark subset 检查：

- diffuse augmentation；
- SOMO 空间扩展；
- electron detachment stability；
- SCF solution 是否为伪束缚态。

如果 gas-phase anion 不稳定，则标记 `unbound_anion`，不强行生成一个 gas-phase adiabatic reduction ranking。

## 7.4 推荐保存的生产参数

最终 workflow 必须机器可读地记录：

- software/version；
- functional；
- basis；
- auxiliary basis / RI approximation；
- dispersion correction；
- integration grid；
- SCF threshold；
- geometry threshold；
- charge/multiplicity；
- solvent model；
- temperature；
- standard state；
- conformer/motif ID；
- QC flags。

# 8. Solution thermochemistry：避免把 association artifact 当成化学规律

## 8.1 Redox free-energy difference 与 association free energy 要分开处理

对于同一分子在两个 charge states 间的 redox difference，molecularity 不变，许多标准态和 translational terms 会显著抵消。

但对于

$$
\mathrm{Li}^+ + M
\rightarrow
[\mathrm{Li}M]^+
$$

molecularity 改变，标准 continuum + gas-phase RRHO 工作流可能引入明显的溶液平动熵 artifact。2026 年系统分析进一步表明，这类 association/cluster formation 特别容易受到理想气体 RRHO translational entropy 的非物理惩罚。

因此本项目不把简单

$$
G=E_{\mathrm{elec}}+G_{\mathrm{thermal}}+\Delta G_{\mathrm{solv}}
$$

当作无需说明的通用 solution free-energy formula，而要求显式记录 thermodynamic cycle 和每一项的来源。

## 8.2 Li$^+$ 配位优先使用相对 ligand-exchange quantity

绝对

$$
\Delta G_{\mathrm{bind}}
=
G([\mathrm{Li}M]^+)-G(\mathrm{Li}^+)-G(M)
$$

可保留作辅助量，但不作为核心 mechanistic truth。它会受到单离子 solvation、continuum cavity、标准态、RRHO entropy 和 cluster definition 的共同影响。

更推荐选统一 reference ligand $R$，构造

$$
[\mathrm{Li}R]^+ + M
\rightarrow
[\mathrm{Li}M]^+ + R,
$$

并定义

$$
\Delta\Delta G_{\mathrm{bind}}(M;R)
=
G([\mathrm{Li}M]^+)+G(R)
-G([\mathrm{Li}R]^+)-G(M).
$$

该反应前后 molecularity 相同，可显著降低标准态和平动熵伪差，同时减少对 Li$^+$ 绝对 solvation free energy 的依赖。

reference ligand $R$ 应在 Stage 0 冻结，可选择结构简单、配位模式明确、在 core set 中稳定的代表分子。

## 8.3 连续介质的两类 sensitivity test 必须分开

### A. Fixed-solvent continuum benchmark

选择一个被所用 continuum 模型明确参数化、同时与 external anchor 数据兼容的固定参考溶剂，全部候选使用同一设定。

### B. Dielectric-only sensitivity

使用 CPCM/COSMO 类模型分别检查若干 $\epsilon$，例如

$$
\epsilon=5,10,20,40,
$$

研究纯电静力 screening 改变是否导致稳健 rank inversion。

不能把 SMD 的 solvent-specific non-electrostatic 参数与“只改变 dielectric constant”混成同一操作。

# 9. 不确定性感知的排序定义

这是 v2 相对于原方案最关键的升级之一。

## 9.1 为什么不能把所有换序都称为 inversion

若模型给出

$$
P(A)=4.21,
\qquad
P(B)=4.24,
$$

但 method/conformer uncertainty 为 $0.1$–$0.2$ 的相应单位，则 $A/B$ 的次序并没有被计算可靠解析。把另一模型中的换序称为“物理 ranking inversion”是不合理的。

因此首先定义 pair difference：

$$
\Delta P_{ij}^{(m)}
=
P_i^{(m)}-P_j^{(m)}.
$$

并给出模型/方法不确定度 $\sigma_{ij}^{(m)}$ 或预注册 tolerance $\delta_m$。

若

$$
|\Delta P_{ij}^{(m)}|<\delta_m
$$

或

$$
|\Delta P_{ij}^{(m)}|<z\sigma_{ij}^{(m)},
$$

则该 pair 在模型 $m$ 下记为 `unresolved/tied`。

## 9.2 Robust inversion

只有当两个模型都能解析该 pair，且符号相反时，才定义 robust inversion：

$$
\operatorname{sign}
\left(\Delta P_{ij}^{(A)}\right)
\neq
\operatorname{sign}
\left(\Delta P_{ij}^{(B)}\right),
$$

同时满足两侧 separation 均超过预设 uncertainty threshold。

robust inversion fraction 定义为：

$$
f_{\mathrm{robust\ inv}}
=
\frac{N_{\mathrm{robust\ inversions}}}
{N_{\mathrm{pairs\ resolved\ in\ both}}}.
$$

同时必须报告 unresolved-pair fraction：

$$
f_{\mathrm{unresolved}}
=
\frac{N_{\mathrm{unresolved\ pairs}}}
{\binom{N}{2}}.
$$

若某个模型看似 inversion 很少，但绝大部分 pairs 实际都无法区分，这一模型不能被称为筛选稳定。

## 9.3 Kendall $\tau_b$

因为 v2 显式允许 ties/unresolved pairs，优先使用 Kendall $\tau_b$，而不是无 ties 的简单 $\tau$。

Spearman $\rho$ 仍可作为全局 rank monotonicity 的辅助量。

## 9.4 Probabilistic pair ordering

若可构建 posterior/bootstrapped distribution，则进一步定义

$$
p_{ij}^{(m)}
=
P\left(P_i^{(m)}>P_j^{(m)}\right).
$$

例如可设：

- $p_{ij}>0.9$：有较强证据 $i>j$；
- $p_{ij}<0.1$：有较强证据 $i<j$；
- 中间区域：unresolved。

这样 ranking stability 直接转化为概率决策，而不是伪确定顺序。

# 10. 筛选决策指标

## 10.1 Top-$k$ overlap

若 $S_A(k)$ 与 $S_B(k)$ 是两个模型选出的 Top-$k$：

$$
O_k
=
\frac{|S_A(k)\cap S_B(k)|}{k}.
$$

因为两集合大小都等于 $k$，这里 precision@k 与 recall@k 数值相同，因此 v2 统一称为 **Top-$k$ overlap**。

同时报告 Jaccard：

$$
J_k
=
\frac{|S_A(k)\cap S_B(k)|}
{|S_A(k)\cup S_B(k)|}.
$$

$k$ 必须在看结果前预注册。建议至少报告：

$$
k/N=10\%,20\%,30\%.
$$

## 10.2 Selection regret

若目标是最大化统一方向的 target quantity：

$$
R_k
=
\frac{1}{k}\sum_{i\in S_T(k)}P_T(i)
-
\frac{1}{k}\sum_{i\in S_M(k)}P_T(i),
$$

其中 $T$ 为 target model/reference，$M$ 为廉价模型。

它衡量“使用廉价模型做选择后，在 target model 下平均损失多少性能”。

## 10.3 Threshold-based decision error

只有当阈值 $T$ 来自外部设计要求、实验基准或事先定义的工程标准时才使用：

$$
d_T(i)=\mathbf 1[P_T(i)\ge T],
$$

$$
d_M(i)=\mathbf 1[P_M(i)\ge T],
$$

$$
E_{\mathrm{decision}}
=
\frac{1}{N}\sum_i
\mathbf 1[d_T(i)\ne d_M(i)].
$$

不允许看完数据后人为挑一个最有利阈值。

# 11. Descriptor 与 feature-cost accounting

## 11.1 $X^{(0)}$：真正廉价、可在 query 前获得

包括：

- molecular weight；
- structural family/tags；
- heteroatom count；
- donor count；
- TPSA；
- rotatable bonds；
- molecular fingerprint；
- xTB orbital proxy；
- $\mu$、$\alpha$；
- xTB partial charge；
- xTB ESP extrema；
- cheap conformer spread。

## 11.2 $X^{(1)}$：free-molecule DFT 已知后可获得

例如：

- vertical/adiabatic gas redox quantities；
- DFT $\mu$、$\alpha$；
- free-molecule geometry response；
- continuum free-molecule target；
- DFT-level ESP。

这些特征可以用于预测昂贵的 $C_1$ Li-coordination response，因为它们在做新的 $C_1$ 计算前已经可得。

## 11.3 $X^{(2)}$：需要 Li-complex DFT 后才能获得

例如：

- DFT $\Delta\Delta G_{\mathrm{bind}}$；
- 优化后的 Li–X 距离；
- DFT Li-complex charge redistribution；
- DFT coordination geometry descriptors。

$X^{(2)}$ 可以用于**机制解释**，但不能用于证明“无需做 $C_1$ 就能低成本预测 $C_1$”。

所有 ML 表格必须包含 `feature_cost_level`。如果 active-learning acquisition 依赖一个 feature，则该 feature 必须在 query 前真实可用。

# 12. $\Delta$-learning 的严格定义

对相同 target definition 的 method correction，可写：

$$
P_T=P_L+\Delta_{\mathrm{method}}.
$$

对环境条件态则避免称为普通 fidelity correction，而写：

$$
\Delta_{\mathrm{coord}}
=
P(C_1)-P(C_0).
$$

模型分别比较：

### Direct model

$$
\hat P_T=f(X^{(0/1)}).
$$

### Conditional-shift model

$$
\widehat{\Delta}_{\mathrm{coord}}
=f(X^{(0/1)}),
$$

$$
\hat P(C_1)
=
P(C_0)+\widehat{\Delta}_{\mathrm{coord}}.
$$

需要检验：

1. $\Delta_{\mathrm{coord}}$ 的方差是否小于完整 target；
2. 是否具有更简单的 descriptor dependence；
4. LOFO 时是否仍保持优势；
5. MAE 优势是否同步转化为 $\tau_b$、Top-$k$ overlap 和 regret 优势。

如果 $\Delta$ 出现明显 discontinuity，并与 motif switching、state identity change 或 dissociation 共现，则不应继续单纯增加回归模型复杂度；应先做 state classification。

# 13. 机器学习与外推评估

## 13.1 模型复杂度顺序

对于 core set 的规模，优先：

1. linear / ridge；
2. KRR；
4. GPR；
5. random forest / gradient boosting 作为非线性对照。

不把深度神经网络作为第一阶段默认方案。

## 13.2 三种数据拆分必须同时报告

### Random split

只作为传统 interpolation baseline。

### Group/scaffold split

高度相似 scaffold 不跨 train/test。

### LOFO：leave-one-structural-family-out

完整留下一个 structural family 测试。

LOFO 是 transferability 的主要证据来源。`functionalization_tags` 不作为互斥 family，用于分析 fluorination、chelation 等跨 family 扰动。

## 13.3 60–100 个 core points 的统计边界

这一规模足以做 paired physical analysis 和 proof-of-concept，但不应对复杂 ML 泛化能力作过强结论。每个 LOFO test family 可能只有约 10 个样本，统计置信区间必须通过 bootstrap 或 permutation analysis 报告。

如果希望把 active learning 和 cross-family transferability 变成主要论文结论，应扩大 broad pool，并尽可能增加 core target labels。

# 14. Active learning：真正的问题是最小昂贵信息预算

## 14.1 目标

给定 broad pool 中所有候选的 $X^{(0)}$ 或 $X^{(1)}$，只有少量候选有 target model label。研究：

$$
n_T
\longrightarrow
\tau_b,
$$

$$
n_T
\longrightarrow
O_k,
$$

$$
n_T
\longrightarrow
R_k.
$$

这里 $n_T$ 是已经完成的昂贵 target calculations 数量。

## 14.2 Retrospective replay

在 core set 已经获得完整 target labels 后，可以把它们暂时隐藏，模拟真实 active-learning loop：

1. 选择初始 seeds；
2. 仅使用当时可见的 labels/features 训练模型；
4. acquisition 选择下一批候选；
5. 揭示 target label；
6. 更新模型；
7. 重复直到预算耗尽。

所有 normalization、hyperparameter tuning 和 feature selection 都必须在每一轮可见数据内部完成，不能偷看完整 target set。

## 14.3 Baselines

至少比较：

### Random

定义最弱 baseline。

### Diversity

选择 cheap descriptor space 中距离当前已标注集合最远的点。

### Uncertainty

GPR 等模型选择预测 epistemic uncertainty 最大的点，但在使用前必须检查 uncertainty calibration。

### Ranking-aware acquisition

直接关心 candidate 是否进入 Top-$k$ 或关键 pair order 是否未解析。例如从 posterior samples 估计

$$
p_i=P(i\in\mathrm{Top}\text{-}k),
$$

并计算二元 entropy

$$
H_i
=
-p_i\ln p_i-(1-p_i)\ln(1-p_i).
$$

优先 query 那些“最不确定是否应该被选中”的候选。

## 14.4 必须多次重复

对于 random/diversity/uncertainty/ranking-aware acquisition，使用多个 initial seeds 和多个随机重复，报告 median 与置信区间，而不是单条最漂亮 trajectory。

# 15. 外部 reference anchors

## 15.1 Gas-phase anchors

选择约 8–10 个结构小、实验 IP/EA 或高等级计算可靠的分子。

目标不是让整个项目依赖昂贵 wave-function calculation，而是验证 production DFT 是否至少在典型体系上给出合理的：

- absolute scale；
- family trend；
- ranking。

## 15.2 Solution redox anchors

优先寻找同一实验系列中、条件尽可能一致的 10–20 个分子：

- solvent；
- supporting salt；
- concentration；
- temperature；
- reference electrode；
- scan conditions。

如果数据不可统一，不强行对全部文献做绝对值 pooled regression，而优先使用 within-series relative ranking。

## 15.3 Reference 的作用

没有 external anchor 时，本项目可以严谨声称：

> “模型 $A$ 能否恢复 target model $B$ 的排序。”

有 external anchor 后，才可以进一步声称：

> “在这些已验证的 chemical/experimental domains 内，某一廉价模型能够保持 experimentally anchored ranking decisions。”

# 16. Li$^+$ 配位与 speciation：条件效应与真实 population 分开

## 16.1 $C_1$ 是 conditional coordination experiment

$C_1$ 研究的是：

$$
M
\quad\text{vs}\quad
[\mathrm{Li}M]^+.
$$

其科学意义是揭示 Li$^+$ 局域电场、几何重排、螯合和电子密度再分布如何改变 redox thermodynamics。

它**不**等价于真实电解液中该分子的平均状态。

## 16.2 真实体系需要 population

真实体系可能同时存在：

$$
M,
\quad
[\mathrm{Li}M]^+,
\quad
[\mathrm{Li}M_2]^+,
\quad
[\mathrm{Li}M_mA],
\ldots
$$

其概率依赖盐浓度、共溶剂比例、阴离子、温度和界面位置。

因此后续真正的 effective quantity 需要显式 population：

$$
\{p_s\}.
$$

这属于 Phase II/III，而不是 MVP 中通过强制 1:1 complex 偷偷替代。

# 17. Explicit microsolvation 的正确定位

## 17.1 MVP 中只做 targeted sensitivity check

选择约 8–12 个候选：

- ranking-stable；
- robust inversion；
- high uncertainty；
- 不同 families 的代表。

对每个候选构造少数**相同化学计量**的局域 cluster，检查 1:1 Li coordination 的关键结论是否改变。

## 17.2 不做不严格的“随意 cluster 指数平均”

对于同一 charge state、相同 stoichiometry 的离散构象，可以分别定义

$$
G_q^{\mathrm{ens}}
=
-RT\ln\sum_i
\exp(-G_{q,i}/RT),
$$

再计算

$$
\Delta G
=
G_{q_2}^{\mathrm{ens}}
-
G_{q_1}^{\mathrm{ens}}.
$$

但如果 microstates 来自不同配位数/不同阴离子数，必须引入 chemical potential 或更完整的统计力学框架，不能直接比较裸 Gibbs energies。

若后续从显式 MD 轨迹获得连续环境，则应使用 vertical energy-gap distribution、free-energy perturbation、umbrella/Marcus-type analysis 等具有明确统计力学基础的方法，而不是把独立优化后的 cluster energies 机械 Boltzmann average。

# 18. 多目标问题：不构造武断“综合电解液分数”

氧化 proxy、还原 proxy、Li coordination response、溶解度、黏度和输运是不同物理目标。

特别地，Li$^+$ binding **不是越强越好**。更强溶剂化可能改善某些局域稳定性，却可能增加 desolvation cost、改变 anion participation 并对界面或低温 transport 不利。

因此第一阶段：

- $\Delta\Delta G_{\mathrm{bind}}$ 主要作为 mechanistic descriptor；
- 不把它默认设为“maximize”目标；
- 若做多目标展示，使用 Pareto front 或明确 target window，而不是

$$
S=\sum_i w_iP_i
$$

这种缺乏物理依据的综合分数。

# 19. 分阶段实施方案

## Stage 0：冻结科学定义与 metadata

### 操作

1. 确定 core set 与 broad pool；
2. 建立 `structural_family`、`functionalization_tags`、`use_role`；
4. 定义 oxidation/reduction quantity 与方向；
5. 冻结 common embedding 的物理含义；
6. 预注册 $k/N=10\%,20\%,30\%$；
7. 预注册 robust-pair tolerance 的确定方法；
8. 冻结 reference ligand $R$；
9. 冻结 external anchor 搜集规则。

### Gate 0

任何目标量、family 定义、筛选方向或阈值不得在看完整结果后无记录修改。

## Stage 1：方法审计与 external anchors

### 操作

1. 选 8–10 个 method-audit molecules；
2. 比较 functionals/basis/diffuse treatment；
4. 建立 gas-phase external anchors；
5. 搜集 solution redox anchor subset；
6. 比较 absolute error 与 rank stability；
7. 冻结 production protocol。

### Gate 1

只有在 production protocol 对典型体系的 state identity、SCF stability、gas-phase anchor 和 solution trend 均没有明显系统性失败后，才能启动批量计算。

## Stage 2：Broad cheap pool

### 操作

1. 生成 canonical structures；
2. RDKit descriptors；
4. CREST/GFN2-xTB；
5. 提取 $P_0$ scalar proxies；
6. 建立 $X^{(0)}$；
7. 检查 duplicate/chemical-space coverage。

### 输出

整个候选池的 cheap chemical-space map。

## Stage 3：Core free-molecule electronic structure

### 操作

1. neutral/cation/anion 构象搜索与 DFT refinement；
2. state-specific ensembles；
4. gas-phase $P_1$；
5. unbound-anion QC；
6. external-anchor validation。

### 主要问题

$$
P_0
\rightarrow
P_1
$$

是否保持排序？哪些 family 最先失效？

## Stage 4：Fixed-background continuum

### 操作

1. 全部候选使用同一 production continuum setting；
2. 得到 $P_2$；
4. audit subset 做 dielectric-only scan；
5. 计算 $P_1\rightarrow P_2$ robust rank shifts。

### 主要问题

continuum environment 主要产生 common offset、family-dependent shift，还是 pairwise reordering？

## Stage 5：Conditional Li$^+$ coordination

### 操作

1. donor/motif enumeration；
2. xTB prescreen；
4. DFT motif optimization；
5. state identity QC；
6. redox-state-specific ensemble；
7. 计算 $\Delta\Delta G_{\mathrm{ox/red}}^{\mathrm{coord}}$；
8. 计算相对 ligand-exchange $\Delta\Delta G_{\mathrm{bind}}$；
9. 对 robust inversion cases 做人工结构审查。

### 主要问题

Li$^+$ coordination 是否引起超出 method uncertainty 的真实 decision shift？

## Stage 6：Uncertainty-aware ranking analysis

### 输出

- Kendall $\tau_b$ matrix；
- unresolved-pair fraction；
- robust inversion fraction；
- Top-$k$ overlap/Jaccard；
- selection regret；
- family-resolved statistics；
- cross-family statistics。

### 必须区分

$$
\text{rank change}
$$

与

$$
\text{robust rank change beyond uncertainty}.
$$

## Stage 7：Mechanism analysis + $\Delta$-learning

### 任务

1. 用 $X^{(0)}$/$X^{(1)}$ 学习 conditional shift；
2. direct vs $\Delta$ model；
4. random/group/LOFO；
5. 识别 robust inversion 的结构机制；
6. 将 $X^{(2)}$ 仅用于 post hoc mechanistic interpretation。

## Stage 8：Active-learning replay

### 任务

比较 random、diversity、uncertainty 和 ranking-aware acquisition：

$$
n_T
\rightarrow
\tau_b,
\quad
O_k,
\quad
R_k.
$$

必须重复多个 seeds，并给出置信区间。

## Stage 9：Optional explicit-microsolvation validation

只对关键 stable/inversion/uncertain cases 做 targeted check。若本科项目时间有限，Stage 9 不作为项目完成的必要条件。

# 20. QC 状态机

每个 calculation object 至少有以下状态：

`generated` → `prescreened` → `submitted` → `scf_converged` → `geometry_converged` → `frequency_checked` → `state_identity_checked` → `accepted`。

异常分支至少包括：

- `scf_failed`；
- `geometry_failed`；
- `imaginary_mode_unresolved`；
- `unbound_anion`；
- `spin_contamination_flag`；
- `motif_switch`；
- `no_intact_minimum_found`；
- `dissociated_optimized_product`；
- `state_identity_ambiguous`。

ML 数据表不得自动把这些样本当成普通缺失值删除。每一类异常都应统计其发生率和 chemical-family dependence。

# 21. 计算预算与执行规模

实际任务数近似为

$$
N_{\mathrm{mol}}
\times
N_{\mathrm{charge}}
\times
N_{\mathrm{conformer}}
\times
N_{\mathrm{environment}}
\times
N_{\mathrm{motif}}.
$$

60 个母分子很容易扩展成上千次 optimization/frequency/single-point jobs。因此 Stage 1 后必须统计：

- median CPU-core-hours；
- 90th percentile job cost；
- failure rate；
- conformer survival rate；
- Li-motif survival rate；
- frequency cost fraction。

之后再冻结 core-set 最终规模。

如果 frequency 成本过高，应在 benchmark 后决定是否：

- 只对低能构象做 frequency；
- 对高层 single point 与低层 thermochemical correction 分离；
- 只在排序可能改变的 near-degenerate candidates 上升级 thermochemistry。

这与本项目的“minimal required information”思想一致。

# 22. 预期结果与可解释分支

## 22.1 情形 A：cheap proxy 已经稳定保持排序

若在某一 chemical domain 中

$$
\tau_b(P_0,P_2)
$$

很高、unresolved fraction 低且 Top-$k$ overlap 高，则说明廉价 proxy 在该适用域内已经足以支持筛选。

科学结论不是“高层计算没用”，而是：

> 对该特定材料决策，额外计算真实性的边际价值有限。

## 22.2 情形 B：数值变化很大，但排序稳定

若

$$
|P_2-P_1|
$$

整体很大，而 robust inversion fraction 很低，则说明环境主要引入 common/family-level offset。

此时可进一步测试：

$$
P_2=P_1+b_f
$$

这样的 family-dependent correction 是否已经足够。

## 22.3 情形 C：存在少量结构集中的 robust inversion

若 robust inversion 集中于：

- chelating motifs；
- 特定 donor atoms；
- 强局域 ESP；
- 高 fluorination；
- 某类柔性分子；

则项目可进一步提出清楚的 missing-physics mechanism。

## 22.4 情形 D：Li coordination 引发 state identity change

如果 $[\mathrm{Li}M]^0$ 经常出现 Li-centered/mixed reduction、断键或 motif switching，则说明

$$
\Delta_{\mathrm{coord}}
$$

不是一个统一平滑函数。

此时应先做：

$$
\text{state classification}
\rightarrow
\text{conditional regression},
$$

而不是继续增加 ML 复杂度。

## 22.5 情形 E：$\Delta$-learning 优于 direct learning

若在 LOFO 下仍然成立，说明 free-molecule physics 已经捕获大部分变化，而 coordination/environment correction 相对低维。

这为扩大 cheap pool、只选择少量 target calculations 提供直接依据。

## 22.6 情形 F：$\Delta$ 无法由 cheap features 学习

这说明现有 representation 缺失关键物理信息。下一步应优先加入：

- cheap coordination geometry proxy；
- conformational flexibility；
- local ESP topology；
- donor-pair geometry；

而不是直接更换更大的 neural network。

## 22.7 情形 G：大部分 pairs 都 unresolved

这也是重要结果。它意味着在当前 method uncertainty 下，候选之间的细粒度排序本身没有被可靠解析。

此时最合理的输出不是“强行排名”，而是候选 equivalence classes 或 tiered sets。

# 23. 最小成果判据

项目完成不要求发现一个“最佳电解液”。最低科学闭环为：

1. 一个 metadata 严格、chemical-space 平衡的 core set；
2. 一个 broad cheap pool；
4. $P_0$、$P_1$、$P_2$ 的一致定义；
5. $C_1$ Li-coordination conditional analysis；
6. external gas/solution anchors；
7. uncertainty-aware rank comparison；
8. robust inversion mechanism analysis；
9. random/group/LOFO；
10. direct vs $\Delta$-learning；
11. feature-cost-aware active-learning replay；
11. high-cost-label budget vs decision accuracy 曲线。

若上述问题得到清楚回答，即使没有新候选分子，项目仍具有完整科研价值。

# 24. 建议核心图

## Figure 1：Two-axis model hierarchy + reference layer

横轴：proxy/electronic-structure hierarchy。  
纵轴：environment/conditional-species states。  
外侧单独标出 external references。

这张图首先建立：

$$
\text{complexity}
\neq
\text{truth}.
$$

## Figure 2：External validation and uncertainty audit

展示 gas/solution anchors、不同方法的误差和 rank consistency，并据此定义 robust-pair tolerance。

## Figure 3：Uncertainty-aware rank stability matrix

同时展示：

- Spearman $\rho$；
- Kendall $\tau_b$；
- unresolved fraction；
- robust inversion fraction。

## Figure 4：Robust rank-flow map

只显示超出 uncertainty threshold 的 rank shifts；普通 near-degenerate swaps 不作为“机制发现”。

## Figure 5：Mechanisms of coordination-induced inversion

分析

$$
\Delta\Delta G_{\mathrm{coord}}
$$

与 donor type、ESP、chelation、flexibility、functionalization tags 的关系，并展示典型 molecular/state-density pictures。

## Figure 6：Direct vs $\Delta$-learning under extrapolation

重点比较 LOFO，而不是只展示 random split $R^2$。

## Figure 7：Minimal expensive-information budget

比较 random/diversity/uncertainty/ranking-aware acquisition：

$$
n_T
\rightarrow
\{
\tau_b,
O_k,
R_k
\}.
$$

这很可能是整个项目最具有一般方法学辨识度的一张图。

# 25. 与已有工作的差异和真正的创新点

## 25.1 不把“ranking/selection”本身当创新

早期大规模电解液筛选已经用高层 reference 审计低成本电子结构方法，并进一步采用多性质过滤与 Pareto-optimal selection。因此本项目的推进不是“第一次关注候选排序/选择”，而是：

> **研究 candidate ordering 在不同物理模型和环境条件态之间何时保持、何时发生超出不确定性的稳健 inversion，并把这种变化直接连接到后续材料决策成本。**

## 25.2 不把“Li$^+$ coordination changes redox”当创新

Yang 等 2025 年已经直接研究有/无 Li$^+$ 配位的 redox potentials 并使用 ML。因此本项目必须超越：

$$
\text{coordination}
\rightarrow
\text{property regression}.
$$

真正的新增内容是：

1. free/coordination states 在概念上严格分离；
2. 检查 electron localization 与 state identity；
4. robust inversion 必须超过 method uncertainty；
5. random interpolation 与 LOFO extrapolation 分开；
6. feature-cost accounting 防止虚假的“低成本预测”；
7. external anchors 将 model-to-model preservation 与 accuracy 分开；
8. active learning 直接针对 materials decision，而不是只减少 property MAE。

## 25.3 更一般的方法学命题

最终希望回答的不是：

> “哪个电解液分子的 redox potential 最高？”

而是：

$$
\boxed{
\text{Which missing physics actually changes the materials decision?}
}
$$

$$
\boxed{
\text{Is an apparent ranking inversion larger than model uncertainty?}
}
$$

$$
\boxed{
\text{What is the minimum information cost required to reproduce a validated target ranking?}
}
$$

这三个问题可以迁移到 OLED、redox-flow molecules、吸附、催化和聚合物添加剂等广泛 computational screening 问题。

# 26. 科学意义

## 26.1 从 property prediction 转向 decision reliability

多数 screening workflow 隐含假设：

$$
\text{更准确的数值}
\Rightarrow
\text{更好的材料选择}.
$$

本项目直接检验这一假设，而不是默认它成立。

## 26.2 定量定义“足够的物理真实性”

不是所有候选都值得最高等级计算。真正需要的是确定：

$$
\text{minimum model/information complexity required for a stable decision}.
$$

这是计算资源配置问题，也是科学问题。

## 26.3 把不确定性本身纳入材料筛选

传统 ranking 强制输出全序：

$$
A>B>C>D.
$$

本项目允许：

$$
A>B\approx C>D,
$$

其中 $B/C$ 在当前精度下 unresolved。这比伪精确的完整排名更加符合计算证据强度。

## 26.4 让 negative result 变得有价值

若廉价模型不失效，得到适用域；若失效，得到 missing physics；若无法学习 correction，得到 representation limit；若 redox state 发生化学身份改变，得到 continuous-regression breakdown。

因此项目不依赖预设的“漂亮结果”。

# 27. 后续升级路线

## Phase II：真实配位 population

加入盐阴离子和不同配位数，研究：

$$
M,
[\mathrm{Li}M]^+,
[\mathrm{Li}M_2]^+,
[\mathrm{Li}M_mA],
\ldots
$$

的 population。

此阶段需要明确浓度和组成。

## Phase III：显式液体采样

使用 classical MD、AIMD 或专门训练的 MLFF 获得真实 coordination distribution，并从轨迹构建 statistically controlled redox free-energy analysis。

## Phase IV：电极界面与 EDL

加入：

- electrode potential；
- surface；
- EDL composition；
- solvent–anion charge transfer；
- decomposition pathway；
- SEI/CEI chemistry。

此时研究对象才逐步从 molecular screening 进入真实 electrochemical stability。

# 28. 推荐项目目录与可追溯数据结构

```text
project/
├── metadata/
│   ├── core_set.csv
│   ├── broad_pool.csv
│   └── references.csv
├── structures/
│   ├── neutral/
│   ├── charged/
│   └── li_motifs/
├── P0_cheap_proxy/
├── P1_gas_dft/
├── P2_fixed_continuum/
├── C1_li_conditional/
├── C2_microsolvation_optional/
├── external_reference/
│   ├── gas/
│   └── solution/
├── analysis/
│   ├── uncertainty/
│   ├── ranking/
│   ├── inversion/
│   ├── delta_learning/
│   └── active_learning/
└── results/
```

每个最终数值必须可追溯到：

- molecule ID；
- conformer/motif ID；
- geometry；
- charge/multiplicity；
- software/version；
- method/basis；
- solvent model；
- temperature/standard state；
- raw output；
- QC state；
- state-identity label。

# 29. 建议的执行时间框架

对于本科阶段的首轮 MVP，可按约 8–12 周组织，但实际进度由 Stage 1 benchmark 的真实计算成本决定。

### 第 1–2 周

Stage 0–1：数据冻结、external anchors、方法审计、自动化 QC。

### 第 3–4 周

Stage 2–3：broad cheap pool + core free-molecule DFT。

### 第 5–6 周

Stage 4：fixed-background continuum；完成首轮 uncertainty-aware ranking。

### 第 7–8 周

Stage 5：Li$^+$ conditional states；重点完成 robust inversion cases。

### 第 9–10 周

Stage 6–7：ranking/statistics、mechanism、$\Delta$-learning、LOFO。

### 第 11–12 周

Stage 8：active-learning replay；若资源允许，再做少量 Stage 9 microsolvation。

不应为了赶时间牺牲 state-identity QC 和 method audit；宁可缩小 core set，也不要批量生成物理定义不一致的数据。

# 30. 最终项目定位

本项目不应描述为：

> “用 DFT 和机器学习筛选新的锂电池电解液。”

更准确的表述是：

> **建立一个不确定性感知、决策导向的电解液分子筛选框架，严格区分廉价代理量、电子结构层级、环境条件态与外部参考；系统研究溶剂化和 Li$^+$ 配位等缺失物理何时只改变数值、何时会导致超出方法误差的材料排序翻转，并确定恢复指定且经验证的 target ranking 所需的最小昂贵计算预算。**

其最核心的工作流可以浓缩为：

$$
\boxed{
\text{cheap proxy}
\rightarrow
\text{validated target model}
\rightarrow
\text{uncertainty-aware rank change}
\rightarrow
\text{mechanism of robust inversion}
\rightarrow
\text{minimal information budget}
}
$$

与 v1 相比，v2 的本质变化不是“计算更多”，而是把以下四件事严格分开：

$$
\boxed{
\text{复杂度、准确性、物种状态、材料决策}
}
$$

只有在这四者被清楚定义后，ranking study 才能从一个普通的电解液 DFT/ML 项目升级为具有一般方法学意义的 computational screening benchmark。

# 参考文献

1. Qu, X.; Jain, A.; Rajput, N. N.; Cheng, L.; Zhang, Y.; Ong, S. P.; Brafman, M.; Maginn, E.; Curtiss, L. A.; Persson, K. A. *The Electrolyte Genome project: A big data approach in battery materials discovery*. **Computational Materials Science** 2015, 103, 56–67. DOI: 10.1016/j.commatsci.2015.02.050.

2. Korth, M. *Large-scale virtual high-throughput screening for the identification of new battery electrolyte solvents: evaluation of electronic structure theory methods*. **Physical Chemistry Chemical Physics** 2014, 16, 7919–7926. DOI: 10.1039/C4CP00547C.

3. Husch, T.; Yilmazer, N. D.; Balducci, A.; Korth, M. *Large-scale virtual high-throughput screening for the identification of new battery electrolyte solvents: computing infrastructure and collective properties*. **Physical Chemistry Chemical Physics** 2015, 17, 3394–3401. DOI: 10.1039/C4CP04338C.

4. Peljo, P.; Girault, H. H. *Electrochemical potential window of battery electrolytes: the HOMO–LUMO misconception*. **Energy & Environmental Science** 2018, 11, 2306–2309. DOI: 10.1039/C8EE01286E.

5. Borodin, O. *Challenges with prediction of battery electrolyte electrochemical stability window and guiding the electrode–electrolyte stabilization*. **Current Opinion in Electrochemistry** 2019, 13, 86–93. DOI: 10.1016/j.coelec.2018.10.015.

6. Fadel, E. R.; Faglioni, F.; Samsonidze, G.; et al. *Role of solvent-anion charge transfer in oxidative degradation of battery electrolytes*. **Nature Communications** 2019, 10, 3360. DOI: 10.1038/s41467-019-11317-3.

7. Itkis, D.; Cavallo, L.; Yashina, L. V.; Minenkov, Y. *Ambiguities in solvation free energies from cluster-continuum quasichemical theory: lithium cation in protic and aprotic solvents*. **Physical Chemistry Chemical Physics** 2021, 23, 16077–16088. DOI: 10.1039/D1CP01454D.

8. Wu, Q.; et al. *Effect of the Electric Double Layer (EDL) in Multicomponent Electrolyte Reduction and Solid Electrolyte Interphase (SEI) Formation in Lithium Batteries*. **Journal of the American Chemical Society** 2023, 145, 2473–2484. DOI: 10.1021/jacs.2c11807.

9. Yang, D.; Zhang, P.; Xiong, Y.; et al. *Unveiling redox potential behavior in electrolytes: A machine learning approach to Li-ion coordination effects*. **Materials Today Energy** 2025, 54, 102121. DOI: 10.1016/j.mtener.2025.102121.

10. Rebollar-Zepeda, A.; Carreon-Gonzalez, M.; Muñoz-Rugeles, L.; Alvarez-Idaboy, J. R. *Systematic Molecularity-Dependent Entropy Errors in Continuum/RRHO Solution Thermochemistry: Origin and Correction*. **Journal of Chemical Theory and Computation** 2026, 22, 6367–6376. DOI: 10.1021/acs.jctc.6c00575.

11. Chen, H.; Xu, H.; Zhou, Q.; et al. *Machine Learning for Rational Electrolyte Design in Lithium Batteries: Bridging Macroscopic Performance and Physically Interpretable Descriptors*. **Advanced Energy Materials** 2026, e71542. DOI: 10.1002/aenm.71542.
