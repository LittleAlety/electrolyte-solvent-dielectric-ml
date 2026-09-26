# KPI 15+14 短清单 vs 本仓漏斗：交叉试跑

本轮是 `probes/kpi_funnel_cross_run.py` 的一次跨池交叉试跑。预注册在跑之前冻结（2026-09-26T09:11:42Z），判据与阶段定义跑后未回填、未放宽。

## 1 一句话结论

- 身份层：29 行里解析出 29 行 InChIKey（SMILES 路线 14 行，PubChem CAS 路线 15 行），判据 B 达成。
- 短清单与本仓 Batt-P30K 的交集：13 个分子。
- 短清单与本仓 314 键名册的交集：2 个；与冻结 epsilon v0.3 表 2 个；与 v1.x 观测表 1 个。
- 判据 A（29 行自洽）：违反行数 0，允许 0，判 通过。

## 2 池与可比性

- 我方池：Batt-P30K，`data/raw/batt/Batt-P30K.h5`，声明 29519 个分子。
- 本轮实测读入：29519 个；SMILES 不可解析 0 个。
- KPI 池：QM9（133,885），本仓不存在，也未联网获取。
- 可比性：两池不同（pool_different）。只允许比比例与规则，不允许比绝对计数，也不允许把比例差异单方面归因于漏斗。

## 3 判据 A：29 行自洽性

逐行核对 KPI 结构过滤（无 -OH / -COOH、Molwt < 600、重原子数 < 30）与三阈值（MP < 230 K、BP > 430 K、FP > 360 K）。

| 行 | CAS | SMILES | 违反项 |
| --- | --- | --- | --- |
| 14-1 | — | O=COCC1COCO1 | 无 |
| 14-2 | — | N#CCCCC1CCC1 | 无 |
| 14-3 | — | N#CCCC1=CCCC1 | 无 |
| 14-4 | — | N#CCCC1(CC1)C#N | 无 |
| 14-5 | — | CCC(CC#N)CC#N | 无 |
| 14-6 | — | CC(CCC#N)CC#N | 无 |
| 14-7 | — | CCC(CCC#N)C#N | 无 |
| 14-8 | — | C#CCCOCCCC#N | 无 |
| 14-9 | — | CC(COCC#N)C#N | 无 |
| 14-10 | — | CC(CCOC=O)C#N | 无 |
| 14-11 | — | CC(COC=O)CC#N | 无 |
| 14-12 | — | CC(CCC#N)C1CO1 | 无 |
| 14-13 | — | N#CCCOC1CCC1 | 无 |
| 14-14 | — | CC1COCC1CC#N | 无 |
| 15-1 | 96-48-0 | — | 无 |
| 15-2 | 108-32-7 | — | 无 |
| 15-3 | 4437-69-8 | — | 无 |
| 15-4 | 4437-70-1 | — | 无 |
| 15-5 | 4437-85-8 | — | 无 |
| 15-6 | 6975-71-9 | — | 无 |
| 15-7 | 623-35-8 | — | 无 |
| 15-8 | 17611-82-4 | — | 无 |
| 15-9 | 4172-97-8 | — | 无 |
| 15-10 | 32091-48-8 | — | 无 |
| 15-11 | 15074-49-4 | — | 无 |
| 15-12 | 4553-62-2 | — | 无 |
| 15-13 | 16525-39-6 | — | 无 |
| 15-14 | 6959-71-3 | — | 无 |
| 15-15 | 35633-50-2 | — | 无 |

判据 A 通过：29 行全部满足结构过滤与三阈值，违反数 0。

## 4 本仓漏斗 S0-S3（S4 登记为缺口）

| 阶段 | 名称 | 存活 | 本级剔除 | 对池存活率 |
| --- | --- | --- | --- | --- |
| S0 | pool | 29519 | 0 | 1.000000 |
| S1 | kpi_structural_filter | 29519 | 0 | 1.000000 |
| S2 | our_hazard_gate | 22249 | 7270 | 0.753718 |
| S3 | element_whitelist_derived | 11709 | 10540 | 0.396660 |
| S4 | property_thresholds | 不跑 | 不跑 | 不跑 |

- S2 本级剔除原因：acyl_halide=714，aldehyde=1885，alpha_halo_ether=463，azide=4，epoxide=729，halogen_oxygen=323，isocyanate=222，n_x_bond=372，nitro=559，p_x_bond=382，peroxide=547，s_s_bond=219，s_x_bond=531，sulfonyl_halide=325，thiocarbonyl=713
- S3 本级剔除原因：outside_whitelist:Cl=1770，outside_whitelist:Cl+F=309，outside_whitelist:Cl+F+P=2，outside_whitelist:Cl+F+S=24，outside_whitelist:Cl+P=65，outside_whitelist:Cl+P+S=6，outside_whitelist:Cl+S=319，outside_whitelist:F=3206，outside_whitelist:F+P=117，outside_whitelist:F+P+S=8，outside_whitelist:F+S=593，outside_whitelist:P=1100，outside_whitelist:P+S=185，outside_whitelist:S=2836
- S4：本仓没有 MP/BP/FP 模型，Batt-P30K 也不带这三性质，登记为缺口，不跑、不猜、不插值。

## 5 元素白名单（导出值，非原文声明）

- 白名单 = 短清单解析出的元素并集：C N O（3 种，来自 29 行）。
- 状态：`derived_not_declared`。KPI 只说 11 种元素、未给清单；此白名单是导出值，必须标 derived_not_declared
- 因此 S3 的存活数是我方规则下的数字，不是 KPI 规则的复现：本仓导出的白名单比 KPI 声明的 11 元素白名单更严（29 行末端只出现 3 种元素），S3 存活数只能当下界读。

## 6 交集

- Batt-P30K：13 个
  - 14-3 （CAS —，N#CCCC1=CCCC1）
    - Batt-P30K 标签：dipole_norm=2.142689，homo=-9.0201，lumo=1.6832，gap=10.7033，ip=6.430565，ea=-0.054431
  - 15-14 （CAS 6959-71-3，AWVNJBFNHGQUQU-UHFFFAOYSA-N）
    - Batt-P30K 标签：dipole_norm=1.933866，homo=-9.8677，lumo=1.6983，gap=11.566，ip=7.407689，ea=-0.047029
  - 15-12 （CAS 4553-62-2，FPPLREPCQJZDAQ-UHFFFAOYSA-N）
    - Batt-P30K 标签：dipole_norm=2.24985，homo=-11.6671，lumo=1.6842，gap=13.3513，ip=9.407884，ea=-0.045273
  - 15-8 （CAS 17611-82-4，GDCJAPJJFZWILF-UHFFFAOYSA-N）
    - Batt-P30K 标签：dipole_norm=0.539051，homo=-11.7311，lumo=1.6686，gap=13.3997，ip=9.483394，ea=0.029592
  - 14-11 （CAS —，CC(COC=O)CC#N）
    - Batt-P30K 标签：dipole_norm=2.525019，homo=-10.8646，lumo=1.5922，gap=12.4568，ip=8.519195，ea=0.141045
  - 15-4 （CAS 4437-70-1，LWLOKSXSAUHTJO-UHFFFAOYSA-N）
    - Batt-P30K 标签：dipole_norm=2.908878，homo=-11.0709，lumo=1.5609，gap=12.6318，ip=8.725527，ea=0.162447
  - 15-6 （CAS 6975-71-9，OYEXEQFKIPJKJK-UHFFFAOYSA-N）
    - Batt-P30K 标签：dipole_norm=2.139061，homo=-9.3284，lumo=1.7078，gap=11.0362，ip=6.708547，ea=-0.043617
  - 15-3 （CAS 4437-69-8，PUEFXLJYTSRTGI-UHFFFAOYSA-N）
    - Batt-P30K 标签：dipole_norm=2.854806，homo=-11.0837，lumo=1.4702，gap=12.5539，ip=8.758021，ea=0.217153
  - 15-2 （CAS 108-32-7，RUOJZAUFBMNUDX-UHFFFAOYSA-N）
    - Batt-P30K 标签：dipole_norm=2.806128，homo=-11.1265，lumo=1.5229，gap=12.6494，ip=8.792751，ea=0.23632
  - 15-10 （CAS 32091-48-8，WTQMTUQXPWPJIT-UHFFFAOYSA-N）
    - Batt-P30K 标签：dipole_norm=2.451001，homo=-11.6915，lumo=1.6793，gap=13.3708，ip=9.504369，ea=-0.105588
  - 15-1 （CAS 96-48-0，YEJRWHAVMIAJKC-UHFFFAOYSA-N）
    - Batt-P30K 标签：dipole_norm=2.335157，homo=-10.3659，lumo=1.6102，gap=11.9761，ip=8.033307，ea=0.127871
  - 15-15 （CAS 35633-50-2，ZAGOKQGYDCMNPT-UHFFFAOYSA-N）
    - Batt-P30K 标签：dipole_norm=1.997262，homo=-9.7858，lumo=1.6567，gap=11.4425，ip=7.336328，ea=0.106237
  - 15-5 （CAS 4437-85-8，ZZXUZKXVROWEIF-UHFFFAOYSA-N）
    - Batt-P30K 标签：dipole_norm=2.826354，homo=-11.0632，lumo=1.5272，gap=12.5904，ip=8.749941，ea=0.237104
- 314 键名册：2 个
  - 15-2 （CAS 108-32-7，RUOJZAUFBMNUDX-UHFFFAOYSA-N）
    - Batt-P30K 标签：dipole_norm=2.806128，homo=-11.1265，lumo=1.5229，gap=12.6494，ip=8.792751，ea=0.23632
  - 15-1 （CAS 96-48-0，YEJRWHAVMIAJKC-UHFFFAOYSA-N）
    - Batt-P30K 标签：dipole_norm=2.335157，homo=-10.3659，lumo=1.6102，gap=11.9761，ip=8.033307，ea=0.127871
- 冻结 epsilon v0.3：2 个
  - 15-2 （CAS 108-32-7，RUOJZAUFBMNUDX-UHFFFAOYSA-N）
    - Batt-P30K 标签：dipole_norm=2.806128，homo=-11.1265，lumo=1.5229，gap=12.6494，ip=8.792751，ea=0.23632
  - 15-1 （CAS 96-48-0，YEJRWHAVMIAJKC-UHFFFAOYSA-N）
    - Batt-P30K 标签：dipole_norm=2.335157，homo=-10.3659，lumo=1.6102，gap=11.9761，ip=8.033307，ea=0.127871
- v1.x 观测表 v11plus：1 个
  - 15-1 （CAS 96-48-0，YEJRWHAVMIAJKC-UHFFFAOYSA-N）
    - Batt-P30K 标签：dipole_norm=2.335157，homo=-10.3659，lumo=1.6102，gap=11.9761，ip=8.033307，ea=0.127871

预注册写明：交集为 0 不算失败，但必须逐条给出分歧来源。本轮分歧来源见第 7 节。

## 7 分歧来源（逐条）

- 池不同：我方 Batt-P30K 是电池分子池，KPI 池是 QM9；同一结构在两池中存在与否本就不同。
- 规则不同：S2 危险官能团是本仓独有的附加闸门，KPI 侧没有这一级。
- 身份未解析：见判据 B 的未解析清单；未解析行不进交集。
- 转录错：判据 A 已机械核对；任何违反都会列出具体行。

## 8 属性交叉核对（KPI 印刷值 vs 本仓独立取得的 PubChem 汇编值）

- 比对 6 组，|Δ| 中位数 0.05 K，最大 1.42 K。
- 口径提醒：KPI 侧 MP/BP/FP 是论文模型的预测值，本仓侧是 PubChem 汇编的实验值；这不是两个实验源之间的比对。

| 行 | 性质 | KPI 印刷 (K) | 本仓独立值 (K) | Δ (K) | 沉积者 |
| --- | --- | --- | --- | --- | --- |
| 15-1 | melting_point | 228.2 | 229.62 | -1.42 | Hazardous Substances Data Bank (HSDB) |
| 15-1 | boiling_point | 477.2 | 477.15 | 0.05 | Hazardous Substances Data Bank (HSDB) |
| 15-1 | flash_point | 371.5 | 371.15 | 0.35 | Hazardous Substances Data Bank (HSDB) |
| 15-2 | melting_point | 224.4 | 224.35 | 0.05 | Hazardous Substances Data Bank (HSDB) |
| 15-2 | boiling_point | 514.8 | 514.75 | 0.05 | Hazardous Substances Data Bank (HSDB) |
| 15-2 | flash_point | 389.2 | 389.15 | 0.05 | Hazardous Substances Data Bank (HSDB) |

## 9 使用边界

- 短清单仍为 cross_check_only / redistributable=false，永进不了 data/ 冻结表，也进不了任何交付包或模型特征。PubChem 侧结构为公有领域。
- 本轮不拟合任何模型、不产任何 R2；`forbidden_compliance` 逐条登记在 summary 里。
- S4 是缺口，不是结论：任何把 Batt-P30K 各级存活数当作 KPI 级联复现的说法都是错的。
- 短清单是论文模型的预测值，不是本仓实测值。

