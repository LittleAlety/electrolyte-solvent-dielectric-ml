# B05-E4 跨域泛化与适用域
> 生成器 `run_e4_domain_generalization/1.0.0` · 2026-11-23T10:16:03Z

## ⚠️ 探索性
可用分子 **22** 个。所有跨域结论都是探索性的；任一留出组小于 2 个分子时报告 `insufficient_power` 而不是数值。

## 一、覆盖率
- 候选池：22
- 可用：**22**
- 缺 SMILES：0
- 缺描述符：0
- 未归类家族：3

## 二、化学家族分布
| 家族 | 分子数 | 分子 |
|---|---:|---|
| `primary_secondary_amine` | 4 | N-methylaniline, 2-amino-2-methylpr, N-(2-hydroxypropyl, diethanolamine |
| `alcohol` | 3 | 1,2-butanediol, 1,2-propanediol, cyclohexanol |
| `unclassified` | 3 | nonane, heptane, methylcyclohexane |
| `carbonate` | 2 | dimethyl carbonate, diethyl carbonate |
| `dinitrile` | 2 | octanedinitrile, heptanedinitrile |
| `ketone` | 2 | cycloheptanone, 2-acetylthiophene |
| `carboxylic_acid` | 1 | acetic acid |
| `ester` | 1 | methyl propenoate |
| `ether` | 1 | 1,4,7,10,13-pentao |
| `imidazole` | 1 | 1-methylimidazole |
| `sulfone` | 1 | sulfolane |
| `tertiary_amine` | 1 | triethanolamine |

## 三、留一家族出（leave-one-family-out）
| 家族 | 成员 | 训练 | 测试 | MAE | 常数基线 MAE | 优于基线 | 状态 |
|---|---:|---:|---:|---:|---:|---|---|
| `primary_secondary_amine` | 4 | 18 | 4 | 9.1431 | 6.383 | false | measured |
| `alcohol` | 3 | 19 | 3 | 1.7258 | 5.9042 | true | measured |
| `unclassified` | 3 | 19 | 3 | 3.1594 | 17.7646 | true | measured |
| `carbonate` | 2 | 20 | 2 | 3.2783 | 15.7646 | true | measured |
| `dinitrile` | 2 | 20 | 2 | 4.5025 | 11.5605 | true | measured |
| `ketone` | 2 | 20 | 2 | 4.8941 | 8.135 | true | measured |
| `carboxylic_acid` | 1 | 21 | 1 |  |  |  | insufficient_power |
| `ester` | 1 | 21 | 1 |  |  |  | insufficient_power |
| `ether` | 1 | 21 | 1 |  |  |  | insufficient_power |
| `imidazole` | 1 | 21 | 1 |  |  |  | insufficient_power |
| `sulfone` | 1 | 21 | 1 |  |  |  | insufficient_power |
| `tertiary_amine` | 1 | 21 | 1 |  |  |  | insufficient_power |

**可测家族：6；其中优于常数基线：5**

## 四、结构距离 OOD
| 距离桶 | n | MAE | 平均最近邻 Tanimoto | 状态 |
|---|---:|---:|---:|---|
| far  (<0.40) | 15 | 7.4639 | 0.2532 | measured |
| mid  (0.40-0.60) | 3 | 8.7388 | 0.4375 | measured |
| near (>=0.60) | 4 | 2.7917 | 1.0 | measured |

**误差与最近邻相似度的 Spearman 相关：-0.5051**

若该相关为负且显著，说明「越远越差」，即存在可用的适用域信号；若接近 0，说明误差与结构距离无关 —— 描述符本身不携带可迁移信息，而不是「域外失效」。**这两种情况的处置完全不同。**

## 五、来源 OOD
| 来源 DOI | 分子数 | MAE | 状态 |
|---|---:|---:|---|
| `10.1021/je600515j` | 5 | 12.8807 | measured |
| `10.1021/je300958c` | 2 | 4.5025 | measured |
| `10.1016/j.jct.2008.02.015` | 2 | 3.2783 | measured |
| `10.1016/j.jct.2011.10.028` | 1 |  | insufficient_power |
| `10.1021/je301333b` | 1 |  | insufficient_power |
| `10.1016/j.jct.2008.09.006` | 1 |  | insufficient_power |
| `10.1016/j.jct.2011.07.021` | 1 |  | insufficient_power |
| `10.1021/je200682t` | 1 |  | insufficient_power |
| `10.1021/acs.jced.8b00755` | 1 |  | insufficient_power |
| `10.1016/j.tca.2012.10.004` | 1 |  | insufficient_power |
| `10.1016/j.jct.2010.09.008` | 1 |  | insufficient_power |
| `10.1016/j.fluid.2014.05.006` | 1 |  | insufficient_power |
| `10.1016/j.jct.2012.08.009` | 1 |  | insufficient_power |
| `10.1016/j.jct.2012.04.011` | 1 |  | insufficient_power |
| `10.1021/je300234g` | 1 |  | insufficient_power |
| `10.1016/j.fluid.2016.10.026` | 1 |  | insufficient_power |

> **重要限定：** 本项目的来源独立性尚未评估（B01 已证明 DOI 数 ≠ 独立实验数，且存在多组逐字节相同的重复观测）。因此上表**不得**作为「来源聚类稳健性」的证据，只能作为描述性统计。

## 七、决定性检验：指纹完全相同处的误差
有 **4** 个分子的最近邻指纹 **Tanimoto = 1.000**（描述符无法区分两者）。

- 这些分子上的平均误差：**2.7917**
- 最大误差：**5.1494**

| 分子 | 最近邻 | 误差 |
|---|---|---:|
| heptanedinitrile | octanedinitrile | 5.1494 |
| nonane | heptane | 4.5305 |
| heptane | nonane | 1.1888 |
| octanedinitrile | heptanedinitrile | 0.2983 |

在指纹完全相同 (Tanimoto=1.0) 的分子对上, 误差本应接近 0. 但必须先排除『模型整体水平偏移』这一更简单的解释: 若 |bias|/MAE ≈ 1, 大部分误差属于标定失败而非描述符失明.

**必须记录的更正：** 早期版本因 ridge 回归缺少截距项而把整体偏差混入本指标, 得到 19.48 的虚高值. 修复截距后该值显著下降. 因此『描述符无法分辨相似分子』这一强结论**不成立** —— 它主要是模型规格错误造成的假象 (Reviewer 1, B04+B05).

**另需注意：这 4 个分子只构成 2 个分子对**（nonane/heptane、heptanedinitrile/octanedinitrile），不是 4 个独立案例。

## 八、域内 vs 域外误差
- 域内（Tanimoto ≥ 0.4）：**7** 个，MAE = 5.3405
- 域外：**15** 个，MAE = 7.4639
- 域外/域内 误差比：**1.398** → `NO_USEFUL_SEPARATION`

⚠️ **域内与域外的误差几乎相同**，说明 Tanimoto 距离**不能**用作适用域判据。这与 Spearman 相关接近 0 一致：
结构相似度对这个任务没有预测力，因此「适用域」本身不可靠。

## 九、适用域覆盖
- 适用域阈值：最近邻 Tanimoto ≥ **0.4**
- 域内：**7**
- 域外：**15**
- 覆盖率：**31.8%**

域外分子**不得**给出预测宣称；只能说明「无足够相似训练样本」。

## 七、本实验不能回答的问题
- 不能回答「模型在真实新化学空间上如何」——22 个分子、家族多数只有 1-4 个成员
- 不能做来源聚类稳健性宣称（来源独立性未评估）
- 不能给出确认性的 OOD 性能数字
