# Week 27 立项章：介电响应描述符块接入冻结主记分牌池（第四个表示家族）

- 触发：W26 交付（8d994f1）§9 第 3 条 ——「把 ddCOSMO 的 ε 轴接进 ε 主记分牌：零新物理、纯特征工程」。
- 性质：**零新算力的表示工程 + 主记分牌第一枪**。不跑 xTB、不装新依赖、不联网；13 列响应列全部由盘上已有的 W26 产物派生。
- 与 W26 的关系：W26 把「电子结构对连续介质的**响应**」算了出来（242 分子 × 14 档 ε 的 ddCOSMO 扫描、每化合物 Born 曲线、阴离子闸门、轨道能对 1/ε 的斜率）；W27 第一次把这些**响应量**当特征列喂回冻结主记分牌池。W26 是测量，W27 是消费。
- 主记分牌 shot：**1**（累计 13，W21–W26 各 0）。四个冻结读数（0.4091179943351143 / 0.4766400383507876 / 0.5861142332208197 / 0.6216672295270079）未动。

## 1. 本轮登记的三条臂

| 臂 | 内容 | 冻结判据 | 产物 |
| --- | --- | --- | --- |
| **lever4**（冻结锚） | 锚臂：`context['physical_lever4']`，训练池 full_base，评分掩码 scored，与冻结主记分牌同一表示（Morgan+Physical）；seed 42 必须逐位复现 0.5433111678100043 | H27a（复现容差 1e-09） | 只写读数 |
| **lever4_plus_dielectric_response**（本枪） | 锚臂的稠密物理块与 13 列 ddCOSMO 响应块按行水平拼接 | H27c / H27d / H27f | `probes/artifacts/w27_dielectric_response_block.csv`、`w27_dielectric_response_repeats.csv`、`w27_dielectric_response.png` |
| **lever4_plus_shuffled_response**（安慰剂） | 同本枪，但响应块的行顺序被冻结种子（2026）的置换打乱 | H27e（置换后增量绝对值小于 0.005 才算干净） | `probes/w27_dielectric_response_placebo_summary.json` |

## 2. 为什么这是「本记分牌从未测过的表示家族」

- 主记分牌此前用过三族表示：**ECFP/Morgan 计数**（稀疏指纹）、**Physical 稠密块**（levers 1–4：偶极、极化率、间隙、HOMO/LUMO 等静态量）、以及二者的拼接。
- W27 的 13 列**不是静态描述符**，而是**响应量**：同一个分子在 ε 趋于无穷的 Born 极限、ε = 200 处的腔残余、ε 在 [20, 1000] 带内的幂律变异、气相与 ε = 80.4 处的电子亲和及其位移窗口、以及轨道能对 1/ε 的斜率。静态描述符回答「这个分子是什么」，响应量回答「这个分子对介电环境怎么反应」。
- 覆盖是免费的：W26 的 242 分子池经查就是**介电建模名册 246 行里的 242 行**，广播到冻结主记分牌池后行级覆盖 **1768/2391 = 0.7394**，**评分化合物覆盖 97/97**。

## 3. 13 列冻结清单（RESPONSE_COLUMNS，顺序即写入顺序）

| # | 列 | 来源 | 物理含义 |
| --- | --- | --- | --- |
| 1 | born_c_neutral_eV | w26_born_fit.csv | 中性态 Born 前因子 |
| 2 | born_c_cation_eV | w26_born_fit.csv | 阳离子 Born 前因子 |
| 3 | born_c_anion_eV | w26_born_fit.csv | 阴离子 Born 前因子 |
| 4 | born_resid_cation_200_eV | w26_born_fit.csv | 阳离子在 ε = 200 的腔残余 |
| 5 | born_resid_anion_200_eV | w26_born_fit.csv | 阴离子在 ε = 200 的腔残余 |
| 6 | born_band_cv_cation | w26_born_fit.csv | 阳离子在带内 [20, 1000] 的残余变异系数 |
| 7 | born_band_cv_anion | w26_born_fit.csv | 阴离子带内残余变异系数 |
| 8 | ea_gas_eV | w26_anion_gate.csv | 气相电子亲和 |
| 9 | ea_at_80p4_eV | w26_anion_gate.csv | ε = 80.4 处电子亲和 |
| 10 | ea_window_eV | w26_anion_gate.csv | 整条介电扫描能提供的 EA 位移窗口 |
| 11 | homo_slope_neutral_eV | w26_dielectric_scan.csv | 中性态 HOMO 对 1/ε 的斜率 |
| 12 | lumo_slope_neutral_eV | w26_dielectric_scan.csv | 中性态 LUMO 对 1/ε 的斜率 |
| 13 | gap_slope_neutral_eV | w26_dielectric_scan.csv | 中性态间隙对 1/ε 的斜率 |

三条输入红线（导出器逐条 sha256 复核，任一移动即拒跑）：probes/artifacts/w26_dielectric_scan.csv / probes/artifacts/w26_born_fit.csv / probes/artifacts/w26_anion_gate.csv。

## 4. 口径纪律（本轮全程生效）

- **池与掩码逐字复用冻结主记分牌**：评分 457 行 / 97 化合物，训练池 full_base（2029 行基础 + 362 行外源 = 2391 行）；切分器 splits_for(seed, groups, score_mask, train_mask)（masked_splits + drop_thin_folds，5 折 × 10 重复，GroupKFold by InChIKey）；拟合器与超参逐字复用（max_depth 2、200 树、lr 0.05、hist、max_bin 64、n_jobs 1）。
- **缺行不插补**：块在 W26 名册之外的池行上留 NaN，交给 XGBoost 自带的缺失值处理；不计算任何折内统计量、不丢弃评分行。
- **块里没有任何一列触及被测的介电常数**：每一列都是溶质对**给定 ε 的连续介质**的响应，标签侧 ε 从未进入特征构造。
- **主读数取 Morgan+Physical**（与冻结锚 0.5433111678100043 同一表示口径）；Physical 单表示读数（H27g）只作描述性次读数并列报出，**不单独构成晋升路径**。
- 图层级同句声明：本仓 W27 的特征来自 **GFN2-xTB / ddCOSMO 任意 ε / 刚性气相几何 / 242 分子**；母体论文 v6 = r2SCAN-3c / CPCM / 18 分子。跨层级只比函数形式与量级。
- 不引用任何 Reaxys 数值；THEMol（CC BY-NC 4.0）不入交付包；Batt-P30K（MIT）与 RX-392 / SolvFunc-87 只作参考层。

## 5. 七条判据

| 判据 | 内容 | 阈值 |
| --- | --- | --- |
| H27a | 复现锚：seed 42 的 lever4（Morgan+Physical）逐位复现冻结常量 | 容差 1e-09 |
| H27b | 跨折泄漏：全部种子、两个臂的含跨界化合物折数为 0 | 0 |
| H27c | 确认线：五种子 Morgan+Physical 增量均值 | 大于等于 +0.02 |
| H27d | 部分线：五种子 Morgan+Physical 增量均值 | 大于等于 +0.005 |
| H27e | 安慰剂惰性：行重排后 Morgan+Physical 增量绝对值 | 小于 0.005 |
| H27f | 覆盖纪律：响应块覆盖评分化合物 | 97/97 |
| H27g | 描述性次读数：五种子 Physical 单表示增量均值（不构成晋升路径） | 无阈值 |

## 6. 预注册修订 2（生产运行之前）

- 修订 1 把锚 0.5433111678100043 标成 **Physical** 表示，这是**事实性错误**：该常量在本记分牌家族里的定义是 full_table_lever4 的 **Morgan+Physical** 表示（见 `probes/dielectric_representation_seed_robustness.py` 的 ANCHORS 与 HYPOTHESIS_REFERENCE）。冒烟跑出的 0.543311 正是 Morgan+Physical 那一列。
- 修订 2 把主读数改回 Morgan+Physical、把 Physical 降为描述性次读数，并把 H27g 明确标成描述性。修订发生在**只跑过 1 个种子的冒烟之后、五种子生产运行之前**。
- **没有任何阈值被移动**（1e-09 / 0.02 / 0.005 / 0.005 / 97 全部与原值相同），列清单、臂、种子集、安慰剂规则均未移动；依据逐条记在 `probes/w27_dielectric_response_prereg.json` 的 `revision_note` 与 `smoke_pilot_evidence` 里。

## 7. 交付物与收口

1. probes/w27_dielectric_response_prereg.json（跑前冻结，status = locked_before_run，revision 2，带 sha256）
2. `probes/w27_dielectric_response.py` + `probes/w27_dielectric_response_summary.json`
3. probes/artifacts/w27_dielectric_response_block.csv（242 行 × 13 列）、w27_dielectric_response_repeats.csv、w27_dielectric_response.png
4. `reports/w27_dielectric_response.md`（自动渲染的结题报告）
5. tests/test_w27_dielectric_response.py（回归与纪律守卫）
6. `probes/export_week27_results.py` 导出到 成果输出/week27（AF-12：先封树提交、干净重导、按需补修复提交）
