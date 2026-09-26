# Week 15 建模线：ε hybrid 的逐折训练侧 SHAP 特征重要度排序

- 任务：`week15_modelling_hybrid_shap`
- 生成时间（UTC）：`2026-09-26T06:06:10Z`
- 脚本：`probes/dielectric_hybrid_shap.py`（`sha256` = `091b3f069a43ab68…`）
- 重要度实现：`xgboost_pred_contribs`

## 一句话结论

冻结 hybrid 的 grouped R2 逐位复现 0.4091179943351143，泄漏守卫 150 次排序全部干净（`test_rows_visible_to_ranking=0`）；hybrid 侧平均重要度最高的是 `mu_sq_over_Vm`。与 AB-6 实际引用的那张表逐折 top-3 集合一致率 0.040（判决 `inconsistent`），但与**修正后**的置换排序一致率 0.540（判决 `partially_consistent`）；被引用表与修正置换自身的一致率只有 0.060。原因是杠杆 9 的 `permutation_importance` 洗的是 23 列矩阵的前 10 列（物理块），却贴着知识池的十个名字，该缺陷已复现到 `0.0`。

## 一、协议

- 协议原文：冻结的 ε hybrid（Morgan+Physical，即 v1.x 主记分模型）在冻结主记分牌的每一折训练侧内部，重算精确 TreeSHAP 贡献后按列排序
- 折划分来源：`dielectric_knowledge_purity_sweep.scoreboard_splits（冻结主记分牌）`；分割器 按 InChIKey 分组的 GroupKFold（masked_splits），测试折至少 2 行；seed `42`；50 折（5 folds × 10 repeats）
- 折划分指纹 `signature_sha256` = `864b3a531e404d49c3399bae1426c49abce79f1fab812f5ae8ed15f676bb86be`；与杠杆 9 记录的主记分牌指纹一致；二次发牌一致：True
- 特征列序：2061 列（2048 Morgan count bits + 13 physical），`feature_column_order_sha256` = `b7155b3e744ba3f61da5daf75b6f8c5543d8a6718d9284455b09bbdce5395838`
- 池：457 行 / 97 化合物（`thermoml_zero_frequency` AND `room_temperature`），载入 2029 行，`model_ready` 门与冻结口径未改
- 冻结 hybrid 的 grouped R2：参照 `0.4091179943351143`，本轮复现 `0.4091179943351143`，差 `0.0`（容差 `1e-09`）→ 复现
- 手写 fold 拟合 vs 冻结评分函数：比较 50 折，最大逐点差 `0.0`（逐位相同）

### 1.1 hybrid 不是拼接矩阵（口径澄清，不许省略）

冻结的 `Morgan+Physical` 不是把 2048 位 Morgan 与 13 列物理特征拼成一张 2061 列矩阵，而是**分别**拟合两个 XGBoost（一个只看 Morgan 位、一个只看物理列），再取 `0.5 * (morgan_pred + physical_pred)` 并在 1.0 处截断。SHAP 对「特征集不相交的两个模型的线性组合」是**精确可加**的，所以某一列的 hybrid 贡献恰为 `0.5 ×` 它在自己模型内的贡献；本探针就是这么拼出这 2061 列排序的，`0.5` 这个系数写在 `HYBRID_MIXING_WEIGHT` 里。
- 截断影响：测试折预测中被 1.0 抬起的行数 = `0`（SHAP 读的是截断**之前**的 margin，这条是边界不是成就）

## 二、泄漏守卫

`assert_shap_ranking_scope` 继承杠杆 9 的 `assert_ranking_scope`（`RankingLeakError`），并加两条更强的条款：①排序所用的行必须**恰好**等于训练折（防静默缩域）；②排序所用行里不许出现任何**同时出现在测试折的化合物**（行级检查看不见的组级泄漏）。守卫在生产循环的**每一折**内运行，不是只在测试里跑。

- 排序次数 = `150`（hybrid 臂 50 + 知识臂 50 + 置换参照臂 50）
- 实测 `test_rows_visible_to_ranking` = `0`（逐行记录，最大值为 `0`）
- SHAP 加性校验：检查 150 次拟合，口径 `逐行取 |sum(phi) + bias - margin| / max(|margin|, 1) 之后取最大值`，容差 `1e-05`；hybrid 臂最大**相对**残差 `4.733931336558536e-06`（绝对 `0.00013556028716266155`）、知识臂最大相对残差 `3.1437980782649992e-06` → 通过。残差之所以不是 1e-9 而是 ~1e-7 相对量级，是因为 boosters 以单精度累加贡献——这是关于工具的事实，已在边界里写明

## 三、读数

hybrid 臂共 2061 列（每列 50 折），其中 `stable` 6 列、`unstable` 2055 列；任何一棵树都没用过的列 1880 列。

### 3.1 hybrid 臂 top-10（按跨折平均重要度）

| 名次 | 特征 | 类型 | 平均重要度 | 平均名次 | 名次标准差 | 进 top-10 折数 | 符号一致率 | 稳定性 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | `mu_sq_over_Vm` | physical | 2.647946 | 1.64 | 1.05 | 50/50 | 100.0% | stable |
| 2 | `total_energy_hartree` | physical | 1.911208 | 3.16 | 1.73 | 50/50 | 100.0% | stable |
| 3 | `tpsa_A2` | physical | 1.626098 | 4.02 | 1.67 | 50/50 | 80.0% | stable |
| 4 | `molecular_volume_A3` | physical | 1.528331 | 4.90 | 3.91 | 46/50 | 100.0% | stable |
| 5 | `morgan_bit_0790` | morgan_bit | 1.325632 | 106.44 | 269.61 | 40/50 | 100.0% | stable |
| 6 | `morgan_bit_0427` | morgan_bit | 0.969413 | 100.12 | 190.47 | 40/50 | 80.0% | stable |
| 7 | `morgan_bit_0114` | morgan_bit | 0.907184 | 9.08 | 5.02 | 35/50 | 100.0% | unstable |
| 8 | `morgan_bit_0080` | morgan_bit | 0.737548 | 11.76 | 7.63 | 36/50 | 100.0% | unstable |
| 9 | `hbd` | physical | 0.708850 | 9.80 | 2.56 | 35/50 | 100.0% | unstable |
| 10 | `morgan_bit_0650` | morgan_bit | 0.669538 | 14.60 | 10.60 | 28/50 | 90.0% | unstable |

### 3.2 特征家族占比（hybrid 臂）

| 家族 | 列数 | 平均重要度合计 | 重要度份额 | 曾进过 top-10 的列数 | stable 列数 |
| --- | --- | --- | --- | --- | --- |
| `morgan_bit` | 2048 | 10.6706 | 50.2% | 17 | 2 |
| `physical` | 13 | 10.5888 | 49.8% | 9 | 4 |

### 3.3 知识池交叉臂 top-10（同折、同模型规格、换重要度实现）

| 名次 | 成员 | 平均重要度 | 平均名次 | 名次标准差 | 进 top-3 折数 | 稳定性 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | `donor_acceptor_pair_density` | 1.477590 | 1.16 | 0.55 | 49/50 | stable |
| 2 | `heteroatom_over_carbon` | 0.721048 | 2.56 | 1.05 | 42/50 | unstable |
| 3 | `donor_count` | 0.375795 | 3.60 | 1.28 | 29/50 | unstable |
| 4 | `rotatable_bond_count` | 0.269908 | 4.44 | 1.80 | 17/50 | stable |
| 5 | `double_bond_count` | 0.204673 | 4.80 | 1.46 | 8/50 | stable |
| 6 | `acceptor_count` | 0.140738 | 5.50 | 1.50 | 4/50 | stable |
| 7 | `has_1_donor` | 0.058034 | 6.92 | 1.45 | 1/50 | unstable |
| 8 | `ring_count` | 0.025365 | 8.86 | 1.78 | 0/50 | unstable |
| 9 | `has_2_donors` | 0.005612 | 8.22 | 0.86 | 0/50 | unstable |
| 10 | `has_3plus_donors` | 0.002137 | 8.94 | 0.96 | 0/50 | unstable |

## 四、与 AB-6 对照

AB-6 的三强是**知识池**成员（`heteroatom_over_carbon`、`donor_acceptor_pair_density`、`ring_count`），它们**不在** hybrid 的 2061 维特征空间里（那是 2048 个 Morgan 位 + 13 列物理特征）。唯一「特征对特征」的对照只能走知识臂：同样的 50 折、同样的模型规格、同样的 10 列，只换重要度实现。

### 4.1 三张排序并列

| 对照 | 逐折 top-3 集合完全一致 | 一致率 | 平均 Jaccard | 判决 |
| --- | --- | --- | --- | --- |
| SHAP（本探针） vs AB-6 实际引用的表 | 2/50 | 0.040 | 0.422 | `inconsistent` |
| SHAP（本探针） vs 修正后的置换 | 27/50 | 0.540 | 0.770 | `partially_consistent` |
| 引用表 vs 修正后的置换 | 3/50 | 0.060 | 0.442 | `inconsistent` |

- 众数 top-3：SHAP = `donor_acceptor_pair_density`、`donor_count`、`heteroatom_over_carbon`（22/50）；引用表 = `donor_acceptor_pair_density`、`heteroatom_over_carbon`、`ring_count`（23/50）；修正置换 = `donor_acceptor_pair_density`、`donor_count`、`heteroatom_over_carbon`（14/50）
- 手册 AB-6 五个数字与杠杆 9 机读产物复核：全部对上（容差 `0.005`）——**复核通过不等于口径正确**：它对上的是那张带标签缺陷的表。

### 4.2 引用表的缺陷（已复现到 0.0，不是代码评注）

引用表里挂在十个知识池成员名下的那些重要度，其实是那张 23 列矩阵前 10 列（物理块）的置换重要度；因为 `permutation_importance` 洗的是 `permuted[:, position]`，而 `position` 来自 `enumerate(columns)`，但 `features` 实际带 23 列

- **复现**：500 个「折 × 成员」单元，与 lever 9 存储值的最大差 = `0.0`，名次逐格相同 `500/500`
- **位置同一性**：把 `columns` 换成「前十个物理列名」，数值最大差 = `0.0` → 被洗的确实是矩阵第 0..9 列
- **修正调用确有区别**：命名全部 23 列后与引用读数的最大差 = `194.15807160482248`（>0，两次测量确实不同）
- **名次集合也复现**：由复现分数重建的逐折 top-3 集合与 lever 9 存储名次得到的集合相同 `50/50` 折

引用表里「成员名」与实际被洗矩阵列的对应：

| 引用表里的成员名 | 实际被洗的矩阵列 |
| --- | --- |
| `donor_count` | `T_K` |
| `acceptor_count` | `formal_charge` |
| `has_1_donor` | `heavy_atom_count` |
| `has_2_donors` | `hbd` |
| `has_3plus_donors` | `hba` |
| `donor_acceptor_pair_density` | `tpsa_A2` |
| `ring_count` | `molecular_volume_A3` |
| `double_bond_count` | `dipole_D` |
| `rotatable_bond_count` | `polarizability_A3` |
| `heteroatom_over_carbon` | `mu_sq_over_Vm` |

### 4.3 十个成员的三方逐项对照

| 成员 | SHAP 平均重要度 | SHAP 平均名次 | SHAP 进 top-3 | 引用表平均重要度 | 引用表平均名次 | 引用表进 top-3 | 修正置换平均重要度 | 修正置换平均名次 | 修正置换进 top-3 | 引用标签背后实际被洗的列 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `donor_acceptor_pair_density` | 1.4776 | 1.16 | 49/50 | 39.813 | 2.84 | 37/50 | 56.153 | 1.02 | 50/50 | `tpsa_A2` |
| `heteroatom_over_carbon` | 0.7210 | 2.56 | 42/50 | 92.110 | 1.36 | 49/50 | 3.418 | 2.88 | 39/50 | `mu_sq_over_Vm` |
| `donor_count` | 0.3758 | 3.60 | 29/50 | 0.157 | 8.58 | 0/50 | 1.144 | 4.14 | 17/50 | `T_K` |
| `rotatable_bond_count` | 0.2699 | 4.44 | 17/50 | 17.494 | 4.88 | 7/50 | 1.261 | 4.22 | 20/50 | `polarizability_A3` |
| `double_bond_count` | 0.2047 | 4.80 | 8/50 | 27.415 | 3.72 | 19/50 | 1.214 | 4.12 | 20/50 | `dipole_D` |
| `acceptor_count` | 0.1407 | 5.50 | 4/50 | 0 | 9.88 | 0/50 | 0.337 | 5.88 | 1/50 | `formal_charge` |
| `has_1_donor` | 0.0580 | 6.92 | 1/50 | 5.680 | 6.02 | 2/50 | 0.293 | 7.12 | 3/50 | `heavy_atom_count` |
| `has_2_donors` | 0.0056 | 8.22 | 0/50 | 3.575 | 6.28 | 1/50 | 0.023 | 8.06 | 0/50 | `hbd` |
| `ring_count` | 0.0254 | 8.86 | 0/50 | 44.607 | 3.08 | 35/50 | 0.067 | 8.80 | 0/50 | `molecular_volume_A3` |
| `has_3plus_donors` | 0.0021 | 8.94 | 0/50 | 0.823 | 8.36 | 0/50 | 0.012 | 8.76 | 0/50 | `hba` |

### 4.4 AB-6 三强与副判据在诚实口径下是否还成立

| AB-6 三强 | SHAP 进 top-3 折数 | 修正置换进 top-3 折数 | 引用表进 top-3 折数 | 状态 |
| --- | --- | --- | --- | --- |
| `heteroatom_over_carbon` | 42/50 | 39/50 | 49/50 | weakened |
| `donor_acceptor_pair_density` | 49/50 | 50/50 | 37/50 | reproduced |
| `ring_count` | 0/50 | 0/50 | 35/50 | lost |

- 三强状态统计：`reproduced` 1/3、`weakened` 1/3、`lost` 1/3
- AB-6 副判据「线性计数垫底」（规则：在某种读数下，那两个线性计数排在十名中的倒数三名）：**不成立**。`donor_count` 平均名次 SHAP `3.60` / 修正置换 `4.14`；`acceptor_count` `5.50` / `5.88`

这一节**不成立**或**不许外推**的部分，逐条列出：

- 不声称两种重要度实现哪一个是错的；两者对行的加权方式不同（平均 |贡献| vs 训练 MSE 下降量），所以出现不一致只是关于这两个实现的事实
- 不声称某个特征是物理机制
- 不声称知识纯度控制器有效；那条读数归杠杆 9
- 不声称 AB-6 的结论是错的；把修正后的置换读数与引用读数并列，是为了让结论能对着「真正关于知识池成员的数字」重新核对
- 不评判杠杆 9 那次调用的动机，只陈述代码做了什么、数值是什么
- 本探针不改写杠杆 9：它的文件在本探针写集之外，只读打开；缺陷是**报告**出来的，不是就地修掉的
- 需要本探针写集之外的动作：需要在本探针写集之外做一次 Week 15 勘误决定：涉及杠杆 9 的产物，以及引用它的手册段落；本探针只能报告测量结果

## 五、边界（不许省略）

- 特征重要度不是因果：平均 |SHAP| 大，只说明模型倚重该列，与该介电响应背后的物理无关。
- 本探针没有发现任何新东西。它只是用一套独立的重要度实现，在完全相同的折上重读了杠杆 9 / AB-6 的排序；若不一致，那是关于两个实现的事实，不是关于化学的新发现。
- 对照目标本身被查出有缺陷，这一点是**报告**出来的，不是绕过去的。杠杆 9 的 `permutation_importance` 洗的是 `permuted[:, position]`，`position` 来自 `enumerate(columns)`；杠杆 9 给一张 23 列矩阵只传了十个池成员名，于是真正被洗的是第 0..9 列——前十个物理列——而那十个名字只是标签。缺陷已复现到 0.0，修正后的读数与它并列给出。本探针写集之外的文件一个都没有动。
- hybrid 是「只看 Morgan 的模型」与「只看物理列的模型」的 0.5 加权平均，不是拼接起来的特征矩阵，所以把它说成「Morgan+Physical 拼接」是错的。对特征集不相交的两个模型的线性组合，SHAP 精确可加——这正是两半能拼成一张 2061 列排序的原因。
- SHAP 读的是模型原始 margin。计分路径在 1.0 处把平均预测向下截断；真正触到该下限的测试预测行数被记录了下来，而截断没有被求导穿过。要对它做归因，需要另立一套处理。
- 加性校验用的是相对量级。booster 以**单精度**累加 TreeSHAP 贡献，所以重建误差是 margin 的几个 1e-7——在量级 100 的 margin 上约 1e-4 绝对值——而不是 float64 的机器 epsilon。写死一个 1e-9 的绝对容差不是更严的检验，而是关于这个工具的一个假陈述。
- 任何一棵树都没分裂过的列，在每一折里的贡献都恰好为零。它的名次是并列位次里由固定列序决定的位置，不是测量值；`zero_importance_folds` 已记录，读者可据此排除这类列。
- 名次不能跨臂比较：hybrid 臂排的是 2061 列，知识臂排的是 10 列，同一个名次 4 在两张表里含义不同。
- 符号一致性是 10 次 repeat 的折级统计量。取值 0.8 意味着有 1 次 repeat 不一致；这是披露，不是显著性检验。
- 本轮没有触碰任何新数据源。457 行 / 97 化合物的固定池、折的派发、模型规格与指标都是冻结的，冻结输入在这里是被重新摘要校验过的，而不是被断言的。

## 六、输出物

- `probes/artifacts/dielectric_hybrid_shap_importance.csv`
- `probes/artifacts/dielectric_hybrid_shap_rank_stability.csv`
- `probes/dielectric_hybrid_shap.py`
- `probes/dielectric_hybrid_shap_summary.json`
- `reports/dielectric_hybrid_shap.md`

