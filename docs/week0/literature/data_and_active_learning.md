# Week 0 文献精读：数据方法、主动学习与高吞吐计算

## 阅读范围与核验口径

- 阅读日期：2026-09-22。
- 来源均为只读 PDF；本次只新建本文件，不修改源 PDF，不提交 Git。
- 页码默认指 **PDF 物理页**。第一篇是 Nature Communications 文章号 8396 的 14 页 PDF，页脚右侧页码与 PDF 物理页一致；文章号 8396 每页重复出现，不是连续页码。第二篇页脚为 `Page x of 13`，也与 PDF 物理页一致。
- 主 PDF 不支持嵌入附件；已检查两篇的 PDF attachments，均为空。文中引用的 Supporting Information、Supplementary Notes、Tables Sx 和 Figures Sx 多数不在主 PDF 内，因此不能在本笔记中把未提供内容写成已核验事实。
- 文件名与实际全文不一致时必须以后者为准。第二篇文件名为 `s13321-024-00918-w.pdf`，实际全文是 StreaMD 的论文，而不是主动学习论文；详见后文披露。

### 源文件身份

| 文件 | 实际题名 | 实际 DOI | 页数 | SHA-256 |
|---|---|---:|---:|---|
| `Active learning accelerates electrolyte solvent screening for anode-free lithium metal batteries.pdf` | Active learning accelerates electrolyte solvent screening for anode-free lithium metal batteries | `10.1038/s41467-025-63303-7` | 14 | `E3FCB8DFF404E74861604249E273E38ED1732F3F331CD82FD7608E4A01E1028B` |
| `s13321-024-00918-w.pdf` | StreaMD: the toolkit for high-throughput molecular dynamics simulations | `10.1186/s13321-024-00918-w` | 13 | `F3A6AFDC56F46119D96FFD31D3C3EF70E81FC29EE1C3FD766C8E160F203DACD0` |

第一篇文件名不含 DOI；正文首页和 PDF 元数据给出的 DOI 为 `10.1038/s41467-025-63303-7`。第二篇文件名 stem 与正文 DOI 一致。任务未提供“原计划 DOI 清单”，所以无法比较计划 DOI 是否不同；若任务文档中另有 DOI，应以上表实际全文 DOI 为准。

---

## 第一篇：Active learning accelerates electrolyte solvent screening for anode-free lithium metal batteries

### 1. 完整书目信息

Peiyuan Ma, Ritesh Kumar, Ke-Hsin Wang, Chibueze V. Amanchukwu. “Active learning accelerates electrolyte solvent screening for anode-free lithium metal batteries.” *Nature Communications*, 2025, 16, article 8396. DOI: `10.1038/s41467-025-63303-7`.

作者单位为 University of Chicago, Pritzker School of Molecular Engineering。论文于 2024-12-11 收到，2025-08-15 接收。PDF 共 14 页；`Nature Communications, 2025, 16, article 8396` 中的 8396 是文章号，不是某一页的页码。代码仓库为 `https://github.com/AmanchukwuLab/AL-anode-free`，论文还给出代码/数据归档 DOI `10.5281/zenodo.16174975`。见 PDF p.1、p.12、p.13。

### 2. 研究问题

论文要解决的是：在无负极锂金属电池的液体电解质设计中，实验数据少、标签有噪声、候选化学空间巨大，且缺乏普适设计规则。作者不用“先建大数据集再离线预测”的传统频率学派路线，而是尝试用序贯 Bayesian 实验设计/主动学习，让模型用尽量少的实际电池测试，在虚拟电解质空间中发现高容量保持的溶剂候选。

优化对象是 `Cu||LiFePO4`（`Cu||LFP`）无负极电池的循环性能，而不是仅做计算筛选。论文刻意把溶剂身份作为主变量，不依赖额外的光谱或计算描述符来训练采集模型。见 PDF p.1-p.2。

### 3. 标签、数据规模与划分

**目标标签**

- 主标签为 `C20_norm`：第 20 圈的放电容量，以正极理论容量归一化。该标签同时反映早期容量损失与后续衰减，且减少不同正极类型间的绝对容量差异影响。见 PDF p.2。
- 主动学习采集批次统一使用 `Cu||LFP` coin cell、`1 M LiFSA`。两圈 C/10 formation 后进行 C/3 长循环，电压窗口 2.9-3.8 V。见 PDF p.4、p.10-p.11。
- 图 2b 的批次性能是两次重复电池的平均值。见 PDF p.5-p.6。
- 若候选溶剂不能溶解 1 M LiFSA，或电解质不能完成首圈，性能被“任意赋值为 0”。这不是缺失标签，而是一个需要显式建模和披露的标签口径。见 PDF p.4。

**初始数据**

- 初始训练集为 58 条无负极 LMB 循环曲线，不是 58 个随机独立样本；其中多数是单溶剂-单盐电解质。26 个唯一溶剂里有 22 个为醚，盐为 1 M 或 2 M LiFSA。见 PDF p.3。
- 初始数据不是完全同分布：包含 2 M 盐、NMC 正极和更高温度等不同条件。作者在对数据做特征化后混合使用，但没有在主文中给出随机训练/测试划分；见 PDF p.3。
- 室内数据噪声由重复实验估计：DME/2 M LiFSA 的 3 次重复标准差为 5.6%；氟化醚的 4 次重复标准差为 8.2%。见 PDF p.3。

**虚拟空间**

- 摘要和讨论称搜索了约 100 万个虚拟电解质；方法称从数据库过滤后保留约 380,000 个唯一溶剂分子；Fig. 1c 又标出大约 1.35 亿原始溶剂分子、约 480 万经过化学片段过滤、约 380 万经过 RAscore 的中间量，再经离子电导率预测得到约 38 万分子。见 PDF p.1、p.3、p.10。
- 上述“1 million electrolytes”与“380k unique solvent molecules”在正文中并列出现，而 Fig. 1c 的过滤链还有更大中间量。主 PDF 没有把每个数量在唯一口径上完全对齐，因此本笔记不把它们武断地视为同一个集合；复现时应把“原始数据库记录、唯一溶剂、盐/浓度展开后的电解质、最终未标注池”分别统计。
- 化学片段过滤排除了自由基、腈和芳烃等不理想基团；RAscore 小于 0.01 的分子被删除。见 PDF p.10。

**划分和评价方式**

- 没有描述常规的随机 train/validation/test split。
- 实际评价是序贯批次外的泛化：比较同一批内部的 RMSE 和对后续/批外样本的 RMSE。第 6 批模型收敛时，批内 RMSE 为 0.20，批外 RMSE 为 0.26。见 PDF p.4。
- 这是一种时间顺序的 batch holdout，比随机切分更贴近主动学习部署；但主文没有明确说明是否对每个 batch 做了滚动验证。

### 4. 数据采集与主动学习闭环

主流程如下，见 PDF p.2、p.3、p.4、p.6、p.10：

1. 用 58 条室内数据训练初始代理模型。
2. 用四类 Gaussian process regression 模型预测未标注虚拟空间的均值和不确定性，并通过 Bayesian model averaging 聚合。
3. 用 expected improvement 的聚合形式 `EI_aggr` 排名候选。
4. 从高排名候选往下筛选；优先美国可购买、单价低于 `$1000/g`、交期小于 2 周的材料。
5. 通常优先测 top 5,000，最多不超过 top 10,000；相似物只取较高排名者，主动提高多样性。
6. 采购或合成后，以 `1 M LiFSA/Cu||LFP` 测第 20 圈容量，形成新标签。
7. 已测试或已选分子从虚拟池永久移除，避免下一轮重复；新标签回填后重训并进入下一批。

批次事实：

- 前 6 批是 EI 引导的主动学习，每批约测 10 个商业可购分子。第 3 批在 top 10,000 中只找到 5 个可购买候选，于是补充合成排名第 7 的 `3-6` 和排名第 214 的 `3-7`。见 PDF p.4。
- 训练 6 批、增加约 60 条实验数据后，第 6 与第 7 批 top 5,000 候选重合超过 60%，作者据此判定最有希望区域基本被定位。见 PDF p.6。
- 第 7 批不是继续纯 EI：top 5,000 中只剩 3 个可购买物 `7-1` 至 `7-3`，因此改为 greedy sampling，忽略不确定度、按预测性能排序；再从 top 300 中按一步可合成性选 6 个 `7-11` 至 `7-16`。故摘要的“seven campaigns”应按“6 轮 EI + 第 7 轮 greedy 扩展”理解，不能把七轮都说成同一种采集策略。见 PDF p.6。
- 第 5 批后主动删除含氯分子，因为此前含氯溶剂均显示持续分解；这属于实验中加入的专家约束。见 PDF p.4。

### 5. 模型、算法与指标

- 分子表示：1024-bit Morgan fingerprint/ECFP4，经 PCA 降到 10 维；另含盐身份、盐浓度和电解质组成特征。见 PDF p.10。
- 代理模型：4 个 GPR，分别用 RBF+ESS、Matern-3/2、Rational Quadratic 和 Pairwise kernel。
- 集成：Bayesian model averaging 聚合四模型均值和不确定性，避免单一先验在 58 条小数据上过强。
- 采集函数：expected improvement；报告使用聚合后的 `EI_aggr`。不确定性大时偏探索，接近最优且不确定性小时偏利用。
- 主要预测指标：RMSE。第 6 批 in-batch/out-of-batch RMSE 分别为 0.20/0.26，且四个 GP 的性能趋同。
- 解释分析：SHAP，用于检查模型是否学到合理的结构-性能趋势。主文把 `MW_solv` 列为最重要特征，并强调 methoxy、tri-functional、tetra-functional 等指纹；同时明确提醒 SHAP 假设特征独立，不能完整解释交互和混杂。

实验工作还使用 Raman、PFG-NMR、EIS、SEM、XPS 和 Li 电位测试，但这些主要是事后机理验证，不进入主动学习采集闭环。见 PDF p.7-p.9、p.11-p.12。

### 6. 关键结果

- 第 6 批最佳候选 `6-3` 的平均第 20 圈容量达到 124.1 mAh/g；正文把它写成约 124 mAh/g。`5-7` 为 112.0 mAh/g；第 7 批 `7-16`、`7-14`、`7-15`、`7-1`、`7-12` 分别为 123.5、116.5、115.8、115.6、108.9 mAh/g。数值来自 PDF p.5 的 Fig. 2b，正文对 `6-3` 做了取整。见 PDF p.4-p.5。
- 汇总的最佳性能溶剂共 7 个：`6-3`、`5-7` 以及第 7 批的 5 个表现较好候选。最终选取 `6-3`、`7-1`、`7-15`、`7-16` 做深挖。见 PDF p.6。
- 四个重点电解质在 `Cu||LFP` 中与文献氟化醚基线 F5DEE 的循环表现相当，并相对 `4 M LiFSA/DME` 有更高初始容量和更好容量保持；主文没有给出可直接抄录的容量保持百分比表，结论依赖 Fig. 3 曲线。见 PDF p.7。
- Raman 解析中，四个重点电解质的 CIP+AGG 合计为 60%-100%；`6-3` 的 AGG 为 91%，`7-16` 为 63%。见 PDF p.8。
- 20 °C 离子电导率：`7-1` 最高，为 3.5 mS/cm；另外三个为 0.7-1.0 mS/cm。对照 F5DEE 约为 5.0 mS/cm，4 M DME 约为 5.7 mS/cm。见 PDF p.8。
- Li 迁移数为 0.47-0.53，与 F5DEE 的 0.49 和 4 M DME 的 0.47 接近。见 PDF p.8。
- 模型并未只追随数据频率：tetra-functional 指纹只出现在约 20% 的已测溶剂中，却对应最高的平均归一化容量。见 PDF p.6。

### 7. 复现所需资源

**计算侧**

- Python 3.9.12；RDKit、scikit-learn 0.23、OpenTSNE、NumPy、SciPy；matplotlib、seaborn、plotly 或 Origin。
- 论文提供 Jupyter notebooks 和 model checkpoints，MIT 许可。见 PDF p.12。

**实验侧**

- 氩手套箱，要求 `O2,H2O < 1 ppm`；`Cu||LFP`、`Li||Cu` 等 CR2032 coin cell；LFP 正极、LiFSA、Celgard 2325、隔膜、Cu 和所需电解液。
- 电化学工作站、恒温 20±1 °C 房间、循环仪；用于机理复核时还需 Raman、PFG-NMR、EIS、SEM 和 XPS。
- 候选采购/合成是闭环的一部分。论文给出的筛选阈值是 `$1000/g` 和 2 周交期；主文列出了多种前体和合成路线，但精确采购商和逐批用量主要在 Table S3/补充材料中。
- 数据可用性称实验循环数据在 Supporting Information、GitHub 和 source data 中；主 PDF 未内嵌 source data，且 SI 不在本次两个源文件中。见 PDF p.12。

### 8. 局限与需要保留的怀疑

- 只研究单溶剂、单盐 `LiFSA`，主要为固定 1 M；没有系统搜索盐、添加剂、稀释剂和浓度配方。见 PDF p.9。
- 实验验证只在 `Cu||LFP`，未覆盖 NMC811 等高压正极。见 PDF p.9。
- 只优化一个目标 `C20_norm`，没有同时约束倍率、低温、安全和寿命。见 PDF p.9。
- 商业可获得性成为强偏差源。初始数据约 90% 是醚，且醚本身也更容易买到，最终“偏好醚”不能仅归因于模型的物理发现。见 PDF p.5-p.6。
- RAscore 不能保证实际可采购或可合成；研究者后来直接改用一步合成约束。缺少盐溶解度预测也会把“不能溶解”样本压成 0。见 PDF p.4、p.9。
- 标签含 0 值截断、初始数据异质性、重复实验标准差 5.6%/8.2% 等噪声来源；主文没有给出完整的标签不确定性传播方案。
- 虚拟空间的 `1 million`、`380k` 和 Fig. 1c 过滤链口径未完全对齐，复现前必须重新定义计数单位。
- 主 PDF 未给出 GP kernel 超参数、BMA 权重、EI 公式细节、所有批次数量和完整随机种子，这些被放在补充笔记或代码中。

### 9. 对本项目 Week 1-3 的具体实现建议

**Week 1：先冻结标签和数据契约**

- 把“候选、实验条件、原始测量、派生标签”分成四层表。至少记录 `sample_id`、canonical SMILES、溶剂/盐/添加剂、浓度、电池构型、电压窗口、formation 和 cycling protocol、cycle number、原始容量、理论容量、归一化标签、重复编号、批次号、采集日期、来源。
- 对 Week 1 的现有数据先定义一个主标签，并单独维护 `label_version`。像第一篇那样，把不可溶、首圈失败写成 0 时必须保留 `failure_reason`，同时训练一个“失败/成功”辅助分类器，不能让 0 同时代表“真实性能为零”和“没有测到”。
- 建立三个独立计数：原始数据库条目、去重后的 canonical molecule、展开盐/浓度后的 electrolyte。不要把第一篇里不同口径的百万/38 万数字混成一个字段。

**Week 2：实现最小可审计 AL 闭环**

- 先实现 `load labeled -> featurize -> fit surrogate -> score unlabeled -> apply constraints -> select batch -> append labels -> refit`，不要先追求复杂网络。
- 用至少两个不同 kernel 的 GP 和一个简单均值基线做 pilot；记录每个 batch 的模型版本、特征版本、候选池 hash、筛选规则和选中原因。第一篇的核心不是特定 kernel，而是 uncertainty-aware 排名和可追溯回填。
- 采用时间批次留出，而不是随机切分：用第 `t` 批以前的数据训练，在第 `t+n` 批上报告 RMSE/MAE。第一篇的 in/out-batch 0.20/0.26 至少应被复现为同一类时序泛化指标。
- 把采集函数设计成可插拔策略：`EI`、`UCB`、`greedy`、`random` 和 `diversity` 都要在同一候选池、同一预算、同一约束下比较。

**Week 3：补上约束、基准和失败分析**

- 建立独立的 acquisition constraints 模块：可购买性、估算成本、交期、合成步数、官能团排除、溶解性/稳定性风险。第一篇表明，模型排名与实际可测候选之间有明显差距。
- 每次 batch 同时报告：预测性能、经验最优、探索/利用比例、候选重复率、化学多样性、失败标签比例和单位实验成本。避免只看 top-k 预测值。
- 至少做 `random`、固定网格/分位数采样和主动学习三条对照轨迹，并用不同随机种子重复。若主动学习不能在相同实验预算下稳定优于简单基线，应明确报告，不应只展示一次成功曲线。
- 给 UQ 做校准诊断，例如覆盖率、区间宽度和 batch 内方差；第一篇把不确定度作为核心卖点，但主文没有给出完整校准图。
- 将领域约束版本化。像“第 5 批后排除含氯物”这样的专家决策必须写成带生效批次的规则，不能只留在实验记录里。

### 10. 页码核验点

| 核验点 | PDF 页码 | 可核验内容 |
|---|---:|---|
| 题名、DOI、摘要主数字 | p.1 | `10.1038/s41467-025-63303-7`；文章号 8396；初始 58 条；约 100 万候选；7 轮；每轮约 10 个；4 个重点溶剂 |
| 标签与初始模型 | p.2 | `Cu||LFP`；`C20_norm` 为第 20 圈归一化放电容量；4 个 GPR kernel；BMA；EI；6 轮实验反馈 |
| 室内数据集构成 | p.3 | 58 条曲线；22/26 唯一溶剂为醚；1-2 M LiFSA；重复标准差 5.6% 和 8.2% |
| 批次选择与模型误差 | p.4 | top 5,000、最高 top 10,000；`$1000/g`、2 周；批内/批外 RMSE 0.20/0.26；不可溶/失败标 0 |
| Fig. 2b 与第 7 批策略变化 | p.5-p.6 | `6-3=124.1 mAh/g` 等 Fig. 2b 数值位于 p.5；6 批增加约 60 条、重合 >60%、greedy top 300 选 6 个等文字位于 p.6 |
| 方法学与版本 | p.10 | 约 100 万到约 38 万；ECFP4 1024 bit 到 PCA 10 维；4 个 kernel；Python 3.9.12；scikit-learn 0.23 |
| 代码、数据与许可 | p.12 | GitHub `AmanchukwuLab/AL-anode-free`；MIT；notebook 与 model checkpoints；实验数据在 SI/GitHub/source data |

---

## 第二篇：StreaMD: the toolkit for high-throughput molecular dynamics simulations

### 0. 必须披露的文件内容不一致

文件名 `s13321-024-00918-w.pdf` 与 DOI 一致，但实际全文不是主动学习论文，而是 Aleksandra Ivanova、Olena Mokshyna、Pavel Polishchuk 的 StreaMD 软件论文。其研究对象是蛋白/蛋白-配体复合物的高吞吐分子动力学和 MM-GBSA/PBSA，不是电解液主动学习。以下按实际全文精读，并在 Week 1-3 建议中把它定位为“批处理与实验/计算 oracle 工程参考”，不强行套用为 AL 算法文献。

### 1. 完整书目信息

Aleksandra Ivanova, Olena Mokshyna, Pavel Polishchuk. “StreaMD: the toolkit for high-throughput molecular dynamics simulations.” *Journal of Cheminformatics*, 2024, 16, article 123. DOI: `10.1186/s13321-024-00918-w`。

作者单位为 Palacky University 的 Institute of Molecular and Translational Medicine，以及 Czech Academy of Sciences 的 Institute of Organic Chemistry and Biochemistry。论文于 2024-06-12 收到，2024-10-19 接收，采用 CC BY 4.0。主 PDF 共 13 页，页码与 PDF 物理页一致。见 PDF p.1、p.13。

### 2. 研究问题

论文要解决的是：GROMACS 的 MD 与结合自由能计算步骤多、参数多、易出错，已有工具常只生成脚本或只适用于单机；在大批量 ligand、cofactor、金属中心或含硼分子场景下，用户仍需手工编排准备、执行、续算和分析。作者开发 Python/Linux 工具 StreaMD，把蛋白、配体、cofactor 体系的结构准备、显式水 MD、轨迹分析、MM-GBSA/PBSA 和相互作用指纹整合成可在单机或 Dask 网络/集群运行的 pipeline。见 PDF p.1-p.3。

### 3. 数据规模、标签与划分

这里没有监督学习标签，也没有 active learning 的 train/validation/test split。论文的“数据规模”是验证与性能 benchmark；所有 benchmark 的候选集合在运行前固定，结果不会反馈改变下一批候选。

| 数据集/实验 | 原始规模 | 实际完成/筛选后规模 | 任务标签或目标 |
|---|---:|---:|---|
| Greenidge 数据集 | 626 个 protein-ligand complexes | 成功运行 624；收敛条件子集 503 | 计算 `ΔG_binding`，与实验 `pKd` 比较 |
| human beta-secretase 1 | 166 | 满足收敛条件 134 | 与实验亲和力比较 |
| human alpha-thrombin | 63 | 满足收敛条件 58 | 与实验亲和力比较 |
| bovine trypsin | 51 | 满足收敛条件 32 | 与实验亲和力比较；并用于 51 个体系的扩展性测试 |
| cofactor 示例 | 主文未给复合物总数 | 未给 | estradiol dimers 的 150 ns MD 与结合自由能 |

- Greenidge 的 626 个中，`1SRG` 被意外准备成只有 3 个氨基酸的体系，`1NJE` 在 antechamber 配体准备阶段收敛失败，最终 624 个完成。见 PDF p.7。
- 对 624 个 complex 做 10 ns 单次模拟，先比较 0-10 ns、5-10 ns、9-10 ns 的轨迹段。收敛过滤采用 ligand 平均 RMSD `<= 5 Å` 且 RMSD 标准差 `<= 0.5 Å`。作者解释 0.5 Å 的 2 sigma 大致对应 95% 时间保持在 2 Å 内。见 PDF p.7、p.9。
- Bahia 等人的三套基准先按结构相似性和分辨率选一个 reference complex，再把其他 ligand 对齐到 reference 获得初始坐标；随后每个 complex 做 10 ns。见 PDF p.9。
- 这套“筛选后子集”不是训练集划分，而是轨迹是否收敛的质量门控。未收敛样本在 correlation 图中仍被标红展示，而主相关系数也分别给出全集和收敛子集。

### 4. 采集/“主动学习”循环

论文没有 acquisition function、surrogate retraining、batch feedback 或探索/利用策略。

它的循环是确定性计算 DAG：

`蛋白准备 -> ligand/cofactor 参数化 -> complex 组装、溶剂化和中和 -> 能量最小化 -> NVT/NPT -> production MD -> 去 PBC/对齐/居中 -> RMSD/RMSF/Rg -> MM-GBSA/PBSA 与 ProLIF`

- 每一步尽量写 checkpoint；已有输出则跳过，支持中断后续算和完成后续跑。见 PDF p.4-p.5。
- 每个 complex 的准备、模拟和分析可并行；Dask 可通过 SSH 使用多台机器，不要求专用 scheduler。见 PDF p.3-p.4。
- ligand 准备失败时只跳过该 ligand；cofactor 失败则终止整个 system，因为缺 cofactor 的模拟没有意义。见 PDF p.5。
- 默认不允许在同一个 run 内重复模拟；若要做 replica，需要为不同 run 设不同工作目录和种子。见 PDF p.5。
- 因此，它适合作为本项目“候选生成后批量执行”的 workflow 模板，但不能作为主动学习策略或数据选择算法的依据。

### 5. 模型、算法与评价指标

**主要引擎和模型**

- GROMACS 做显式水 MD。
- 默认水模型 TIP3P，默认蛋白力场 AMBER99SB-ILDN；用户可替换。
- 非标准配体默认用 antechamber 生成 BCC 电荷和 mol2；含硼且缺参数时调用 Gaussian 做几何优化和 ESP/RESP，再由 antechamber 转换。
- 金属中心体系可选择 MCPB.py。
- MM-GBSA/PBSA 通过 `gmx_MMPBSA` 计算；默认内部介电常数 `intdiel=4`，默认使用 interaction entropy，但论文结论建议大批量排序时去掉熵项。
- 相互作用指纹通过 ProLIF 提取。
- docking 对照使用 EasyDock 集成 Vina 和 Gnina；Gnina 使用 dense ensemble 模型，两者 `exclusiveness=32`。见 PDF p.10。

**指标**

- 轨迹收敛：ligand 平均 RMSD 和 RMSD 标准差。
- 结构稳定性：蛋白/活性位点/ligand/cofactor 的 RMSD，蛋白 RMSF，radius of gyration。
- 排序质量：计算分数与实验 `pKd` 的 Pearson correlation 绝对值 `|r|`。
- 计算性能：总运行时间、节点/CPU/GPU 配置和并行 overhead。

### 6. 关键结果

**Greenidge 数据集**

- Fig. 3 的图上显示：全部 624 个 complex 与 `pKd` 的 `r=-0.68, p=8.9e-87`；满足平均 RMSD `<=5 Å` 且标准差 `<=0.5 Å` 的 503 个 complex 为 `r=-0.69, p=2.3e-73`。Fig. 3 图注写成“Pearson R=-0.69 for 624”，与图内全 624 的 `-0.68` 不同；本笔记保留这一图内不一致，不强行统一。见 PDF p.8。
- 5-10 ns 与其他轨迹段的整体相关性差别不大，作者推荐用最后 5 ns。各轨迹段数值在 Table S1，主 PDF 未提供该表。见 PDF p.9。

**三个 Bahia 基准**

Fig. 4 给出了不同打分方法的 `|Pearson r|`：

| 数据集 | MM-GBSA, intdiel=1, with IE | intdiel=1, without IE | intdiel=4, with IE | intdiel=4, without IE | Vina | Gnina |
|---|---:|---:|---:|---:|---:|---:|
| BACE1 | 0.46 | 0.49 | 0.62 | 0.63 | 0.50 | 0.72 |
| Thrombin | 0.28 | 0.69 | 0.49 | 0.55 | 0.43 | 0.56 |
| Trypsin | 0.36 | 0.64 | 0.61 | 0.65 | 0.78 | 0.70 |

这些柱内数值在普通文本抽取中不完整，已渲染 PDF p.9 核验。结论是：整体建议 `intdiel=4` 且省略 entropy term；但 thrombin 上 `intdiel=1 + without IE` 最好。trypsin 上 Vina/Gnina 排名相关性优于 MM-GBSA；作者提醒 Gnina 的 benchmark 可能落在 PDBbind refined set v2019 的训练分布中，Vina 比较也受潜在线索泄漏影响。见 PDF p.9-p.10。

**其他结果**

- cofactor-containing estradiol dimer 体系做 150 ns MD，计算自由能与实验聚合速率的相关为 0.93；主文未给出样本数。见 PDF p.7。
- 相互作用指纹能发现数据问题：trypsin 的 `2FX6` ligand 在 PDB 中 bond order 注释错误，导致远离初始 pose；轨迹分析可反向定位数据质量问题。见 PDF p.10-p.12。

### 7. 复现所需资源

- Linux 操作系统；StreaMD 与 conda 版 GROMACS 在论文所述条件下只能运行 Linux。见 PDF p.12。
- Python 3、GROMACS、AmberTools 中的 antechamber/parmchk2/tleap、ParmED、gmx_MMPBSA、ProLIF、Dask。含硼特殊参数化或 MCPB.py 还需要 Gaussian license。
- 输入是补齐残基/侧链、处理 alternates、去共晶配体和水、正确质子化的 PDB 蛋白；ligand/cofactor 为 MOL 或 SDF，且坐标与蛋白对齐。见 PDF p.3。
- Dask SSH 分布式运行需要一个节点地址文本文件；GPU 版可使用 CUDA GPU，论文测试卡为 NVIDIA A100-SXM4-40 GB。
- 主文只称数据在 manuscript 或 supplementary information files 中，没有在正文给出代码仓库、软件许可证或独立 Zenodo DOI；见 PDF p.13。主 PDF 也未显示作者对代码可用性的单独声明。

### 8. 局限与需要保留的怀疑

- benchmark 全部是蛋白-配体或 enzyme-ligand 任务，不能直接证明工具适合液体电解质、溶剂化结构或电池循环数据。迁移到电解质时，结构准备、力场、收敛判据和目标性质都要重新设计。
- 默认设置被称为适用于广泛体系的“suboptimal parameters”，不是普适最优。MM-GBSA 的介电常数和 entropy treatment 明显依赖系统，论文也推荐参数扫描。
- 只做单次 MD，同一 run 内不自动做 replica；多重复需要用户手工建立多个工作目录和种子。对高噪声标签，no training split，因此不能把 benchmark correlation 当作 ML generalization estimate。
- docking 对照可能有训练集污染，尤其 Gnina 的 CONV 模型与 PDBbind refined set v2019 重叠；这降低了“docking优于MM-GBSA”结论的独立性。
- 蛋白处理缺少残基/循环、alternative location、质子化和 histidine 状态仍要求用户正确完成，工具不能替用户判断生物化学正确性。
- MCPB.py 行为高度依赖系统；Gaussian 和 MCPB.py 需要商业许可证。少于节点总核数的任务会因 antechamber 单核/单 ligand 限制而效率低下。
- 某些精确 benchmark 数字只在 Figure/Table S 中；Table S1、S2-S11、具体脚本和输入文件不在本次阅读的 13 页主 PDF 内。

### 9. 对本项目 Week 1-3 的具体实现建议

**Week 1：把“批量计算”设计成可恢复 DAG**

- 不要先写一个长脚本。为每个 candidate/job 定义 manifest：输入 hash、软件版本、力场/参数版本、命令、输出路径、状态、失败原因、开始和结束时间。
- 把准备、执行、分析至少拆成三个可单独运行的阶段。第二篇指出小批任务在所有节点间准备阶段会产生约 14% overhead，分阶段调度适合 Week 3 做性能调优。
- 原始轨迹、输入结构和日志只追加不改写；派生指标写独立表。每次重跑都保留 `job_id` 和版本，便于定位 `2FX6` 类似的数据质量问题。

**Week 2：用极小 smoke set 先验证正确性，再扩规模**

- 先选 3-10 个小体系做端到端 smoke test，覆盖正常 ligand、一个故意错误输入和一次中断续跑。只有 checkpoint、失败隔离和日志链通过后，再跑大 benchmark。
- 对本项目若采用 MD/量子化学 oracle，务必固定默认参数版本，并明确哪些失败是候选物性质、哪些是 pipeline bug。不要将工具失败静默当负标签。
- 若只借用 StreaMD 的思想而不使用其蛋白领域代码，仍应实现相同的状态机和幂等性：相同输入重复提交不能产生重复实验或覆盖结果。

**Week 3：把 benchmark 运行结果变成可比较的资产**

- 建立固定 benchmark manifest，记录数据来源、参考结构/pose、输入清理、随机种子、机器配置、模拟时长、收敛阈值和输出 hash。
- 对每个批量任务报告三类指标：成功/失败率、单体系墙钟时间/GPU 时间、科学指标（如与实验标签的 Spearman/Pearson 和收敛率）。第二篇的 624/626 与 503 收敛子集说明“完成计算”和“可用于结论”必须分开统计。
- 若要接入 Week 1-3 的主动学习，应把这条计算 pipeline 放在 `oracle/evaluator` 层，而不是 `acquisition` 层；AL 选定候选后由它批量评估，然后把结果回填。
- 不建议在本项目直接复刻 624 体系 benchmark；先做 10-30 个体系的分层测试，按蛋白/分子家族或数据来源分层，检查失败和性能是否被单一来源支配。

### 10. 页码核验点

| 核验点 | PDF 页码 | 可核验内容 |
|---|---:|---|
| 题名、DOI、研究问题 | p.1 | 实际题名 StreaMD；DOI `10.1186/s13321-024-00918-w`；MD 准备/执行/分析自动化；单机与分布式 |
| pipeline 与 Dask | p.3-p.4 | Python 3/Linux；checkpoint；SSH 网络；Dask；输入 PDB/MOL/SDF |
| 默认体系参数 | p.4-p.6 | TIP3P；AMBER99SB-ILDN；1000 kJ/mol/nm 或最多 50,000 步；1 ns 默认 production；每 50/100 帧抽轨迹 |
| Greenidge 规模与失败 | p.7 | 626 个输入；624 个成功；`1SRG` 和 `1NJE` 失败原因；10 ns 模拟；150 ns cofactor 示例与 r=0.93 |
| 相关系数与图注不一致 | p.8 | 624 全集 `r=-0.68, p=8.9e-87`；503 收敛子集 `r=-0.69, p=2.3e-73`；图注却称 624 的 R=-0.69 |
| 三套 benchmark 与筛选后规模 | p.9 | 166/63/51；收敛后 134/58/32；RMSD 5 Å 和 0.5 Å；Fig. 4 correlation 数值 |
| 计算性能和限制 | p.10、p.12 | 1026 min、90 min、13 nodes ×128 CPU、14% overhead；A100 40 GB、12 CPU、514 min、约 200% speedup；Linux/Gaussian 局限 |
| 数据可用性 | p.13 | 只声明数据在 manuscript 或 supplementary files；没有代码可用性段落或代码仓库 |

---

## 两篇横向对比

| 维度 | 第一篇：AL for anode-free LMB | 第二篇：StreaMD |
|---|---|---|
| 研究类型 | 实验闭环主动学习发现新材料/电解质 | 高吞吐 MD 软件与 benchmark |
| 数据规模 | 58 条初始实验标签；摘要称约 100 万虚拟电解质；方法称过滤后约 38 万唯一溶剂；前 6 批再增加约 60 条，第 7 批另行候选 | Greenidge 626 输入/624 完成；Bahia 三套 166/63/51，收敛后 134/58/32；性能测试 51 个体系 |
| 标签口径 | 实验 `Cu||LFP` 第 20 圈归一化放电容量 `C20_norm`；失败/不溶被赋 0；批次容量是两次重复均值 | benchmark 标签为实验 `pKd` 或活性；模型 output 为 MM-GBSA `ΔG_binding`/docking score；收敛标签由 ligand RMSD 阈值派生 |
| 主动学习策略 | 4 GPR + BMA + aggregated EI；前 6 批序贯回填；第 7 批转为 greedy；包含可购买性、价格、交期和多样性约束 | 无主动学习、无 acquisition、无模型回填；固定 benchmark 的确定性 prepare-run-analyze DAG |
| Benchmark/基线 | 内部 58 条数据、批次内外 RMSE、室内最佳、1 M F5DEE、4 M LiFSA/DME；无独立外部候选测试集 | Greenidge、BACE1、thrombin、trypsin；与 Vina、Gnina 比较；报告收敛子集和参数敏感性 |
| 代码/数据开放度 | 论文明确给出 MIT GitHub 和 Zenodo DOI；notebook、checkpoints、source data/SI 可供复现 | 正文只说数据在 manuscript/SI，主 PDF 没有代码仓库、代码 license 或软件归档 DOI |
| 对本项目直接价值 | AL 循环、标签治理、时序 batch 评估和约束采集的主要参考 | 批量 oracle/计算 pipeline、checkpoint、失败隔离、分布式调度和 benchmark 统计的工程参考 |

## 未能从主 PDF 提取的内容

1. 第一篇的 Supplementary Notes 1-10、Tables S1-S5、Figures S1-S17 未包含在 14 页主 PDF 中。因此 EI/BMA 的完整公式、kernel 超参数、每个 batch 的精确候选数、Table S3 的全部分子和供应商、Table S4 电极规格、Table S5 黏度等不能从现有源 PDF 独立核验。
2. 第一篇 Fig. 2b、Fig. 3、Fig. 4、Fig. 5 中部分曲线点或柱内数值没有完整文本层；本笔记只使用正文明确写出的数值，以及在图页上直接可读且列出的 Fig. 2b 容量值。其他曲线读出值没有被当成精确数字。
3. 第一篇的 source data 未嵌入 PDF，GitHub/Zenodo 归档也未在本次任务中下载核对，因而只能核实论文对开放度的声明，不能核实仓库中的文件、版本和 license 实际状态。
4. 第二篇的 Supplementary material 1/2、Tables S1/S2 和 Figures S1-S11 未包含在主 PDF 中。不同轨迹段相关系数、三套 benchmark 的全部散点、entropy term 消融细节等不能在本次阅读范围内复核。
5. 第二篇 Fig. 4 的数值主要来自图形柱标签；已通过渲染 PDF p.9 核对。主 PDF 没有逐项表格给出这些相关系数。
6. 第二篇没有代码可用性声明或代码仓库地址，无法从主 PDF 判断 StreaMD 的许可证、安装源和版本归档。主文虽提到软件功能，但本次没有访问外部项目页面。
