# W25-7（后验）：直接学习 vs 位移学习（母体论文 v6 方向 9 的本仓对照）

- **性质**：后验臂（post_hoc = true、new_shot = false、主记分牌 shot = **0**）。**未预注册**，不得引用为预注册结论。
- **池**：237 个化合物（冻结 246 名册里 5 项廉价特征与前缘轨道自由/配位两表齐全者），每化合物一行，按 InChIKey 唯一。
- **代理模型**：KRR（RBF，alpha 由训练折 LOO 选择）；**划分**：random 5 折 x 10 种子（配对区间 2x10^4 bootstrap）与 LOFO（留一家族出，motif_class 五家族）。
- **两种形状**：direct 直接学配位层能级；shift 学位移 delta 再把自由层回加（预测 = 自由层 + delta_hat）。
- **两套特征**：
  - x0 = homo_free_eV, lumo_free_eV, gap_free_eV, formal_charge, total_energy_free_hartree（control: the free level is itself a feature）
  - off_free = formal_charge, total_energy_free_hartree（the free level enters only through the shift target）

## 1. 随机划分

| 轴 | 特征集 | direct tau_b | shift tau_b | delta tau_b | 95% CI | 正向重复 | direct R2 | shift R2 | delta R2 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ox | x0 | 0.5946 | 0.5949 | **0.0003** | [-0.003, 0.003] | 5/10 | 0.7943 | 0.8187 | 0.0244 |
| ox | off_free | 0.2675 | 0.5553 | **0.2878** | [0.281, 0.294] | 10/10 | 0.1317 | 0.7558 | 0.6241 |
| red | x0 | 0.3819 | 0.3944 | **0.0125** | [0.004, 0.020] | 8/10 | 0.3260 | 0.3741 | 0.0481 |
| red | off_free | 0.0896 | 0.1978 | **0.1082** | [0.095, 0.122] | 10/10 | 0.0724 | -4.5806 | -4.6531 |

## 2. 留一家族出（LOFO）

| 轴 | 特征集 | delta tau_b 均值 | 正向家族 | 逐家族 delta tau_b |
| --- | --- | --- | --- | --- |
| ox | x0 | **0.0372** | 3/4 | alkene_pi -0.035, anion_halide 未定义(n<3), aromatic_pi 0.010, lone_pair 0.132, no_motif 0.042 |
| ox | off_free | **0.4703** | 4/4 | alkene_pi 0.422, anion_halide 未定义(n<3), aromatic_pi 0.457, lone_pair 0.518, no_motif 0.484 |
| red | x0 | **-0.0451** | 0/4 | alkene_pi -0.047, anion_halide 未定义(n<3), aromatic_pi -0.010, lone_pair -0.019, no_motif -0.105 |
| red | off_free | **0.3720** | 2/4 | alkene_pi 0.807, anion_halide 未定义(n<3), aromatic_pi 0.800, lone_pair -0.066, no_motif -0.053 |

![图 W25-7 direct vs shift](probes/artifacts/w25_7_delta_learning.png)

## 3. 口径与限制

- 本臂**未预注册**，是 W25 冻结预注册之外的后验追加；W25-1..W25-4 的裁决不受它影响。
- **x0 那一对是控制组，不是证据**：该特征集本身就含自由层能级，而 shift 目标 = direct 目标 − 自由层，所以两者在数学上近乎同一份信息，delta tau_b 接近 0 是设计的预期结果。
- **off_free 那一对才是本臂的实质比较**：自由层不可由特征读出，只能经目标代数注入——这正是 v6 所说的「位移学习把先验注入」。
- 池是 237 行、v6 是 18 分子池；特征是 2 项或 5 项、v6 是 12 项 X0。两边**不可相加**、不比绝对值。
- random 划分的 10 个重复共享同一批化合物，配对区间只读作重复间稳健性，不读作独立样本检验。
- LOFO 五家族大小悬殊（最大 175、最小 2），小家族的 delta tau_b 抽样噪声大；逐家族值只作方向读数。
- LOFO 的 anion_halide 家族只有 2 个化合物，tau_b 在 n < 3 时未定义（表中标「未定义(n<3)」）：该族从均值与正向计数里剔除，families_total 仍记 5。
- 指标只在被预测到的行上读取（LOFO 只读留出家族那一块）；早期版本用 np.empty 的整条向量计分，会把未定义项混进 tau_b，已修。

## 4. 产物

| 文件 | 内容 |
| --- | --- |
| probes/artifacts/w25_7_delta_learning.csv | 逐划分逐特征集逐形状读数 |
| probes/artifacts/w25_7_delta_learning.png | 本图 |
| probes/w25_7_delta_learning_summary.json | 机读摘要 |

