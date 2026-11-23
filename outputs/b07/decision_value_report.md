# B07 决策价值报告
> 生成器 `assemble_b07/1.0.0` · 2026-11-23T10:17:37Z
> 本报告由 B05 产物机械汇总，不手写。

## 零、结论
**模型不可用于筛选决策。** 在现有证据规模上，单分子描述符既不能预测液体介电常数，也不能在候选池中可靠地挑出高 ε 分子。

阻断理由：
- （背景）回归精度优于基线：X0+X1 MAE 6.79 vs 10.81
- Top-k 筛选与随机不可区分（p = 0.16）
- 来源聚类稳健性不可宣称（仅 1 个簇达到 3 个成员）

## 一、PLAN B B07 八条审核点
| # | 审核点 | 状态 | 证据 |
|---|---|---|---|
| 1 | Random split 不能替代跨家族测试 | ✅ | 随机 5 折 6.9815 vs 跨家族 6.6566（差 -4.7%）|
| 2 | 同一分子不得跨训练/测试 | ✅ | 三种划分分子重叠均为 0 |
| 3 | 来源簇 <3 不得宣称聚类稳健 | ❌ 未满足 | 1/16 个簇达到 3 成员 |
| 4 | 必须报告适用域覆盖率 | ✅ | 31.82%（域外 15/22）|
| 5 | MAE 改善 ≠ 筛选收益 | ✅ | E6 噪声阶梯：MAE 恶化但 regret 下降 |
| 6 | Top-k 必须固定 | ✅ | k = 3，来自冻结规则 |
| 7 | regret 必须用预先定义基准 | ✅ | random_uniform_screening |
| 8 | 样本量不足报 insufficient_power | ✅ | E6 状态 INSUFFICIENT_POWER |

## 二、关键数字汇总
| 指标 | 值 | 来源 |
|---|---:|---|
| 回归 MAE（X0+X1） | 6.788274 | E1 |
| 常数基线 MAE | 10.806223 | E1 |
| 跨家族 MAE | 9.1431 | E4 |
| 适用域覆盖率 | 31.82% | E4 |
| 误差 vs 相似度 Spearman | -0.5051 | E4 |
| Top-k=3 regret | 13.38 | E6 |
| P(随机≥模型) | 0.16 | E6 |
| Regret 占可用空间 | 65.22% | E6 |
| 随机 vs 跨家族 MAE 差 | -4.7% | B07 |

## 三、为什么不能靠「更严格的划分」挽救
随机 5 折 MAE 是 6.9815，跨家族 MAE 是 6.6566，差 -4.7%。

**泄漏没有被演示出来** —— 三种划分的数字几乎相同。

这个结果很容易被误读。它**不是**好消息：如果连随机划分都拿不到好数字，说明问题不在划分方式，而在描述符本身不携带可迁移信号。

**推论：换成更严格的划分只会让数字更差，不会更好。** 因此不能用「改用分组划分」来声称改进。

## 四、本报告不能支持的宣称
- ❌ 模型可用于材料筛选或推荐
- ❌ 模型在跨化学空间上泛化
- ❌ 来源聚类稳健
- ❌ 任何确认性性能数字
- ❌ 「改用分组划分后性能提升」

## 五、产物链接
| B07 输出 | 来源 | 说明 |
|---|---|---|
| `leave_one_family_out.csv` | `outputs\b05\E4_domain_generalization\leave_one_family_out.csv` | E4 跨家族留出结果，直接复用 |
| `source_ood_results.csv` | `outputs\b05\E4_domain_generalization\source_ood_results.csv` | E4 来源 OOD 结果；来源独立性未评估，仅作描述性统计 |
| `similarity_ood_results.csv` | `outputs\b05\E4_domain_generalization\structural_distance_ood.csv` | E4 结构距离 OOD（Tanimoto 分桶） |
| `applicability_domain.csv` | `outputs\b05\E4_domain_generalization\applicability_domain.csv` | E4 适用域覆盖；阈值 Tanimoto >= 0.40 |
| `topk_regret.csv` | `outputs\b05\E6_screening_decisions\topk_regret.csv` | E6 Top-k / regret；k 用冻结规则，基线为随机均匀筛选 |
| `screening_reliability.csv` | `outputs\b05\E6_screening_decisions\screening_reliability.csv` | E6 噪声阶梯：衡量筛选可靠性 |

> **不重算的理由：** E4/E6 已经生成这些表。重算会产生两份副本，二者可能漂移 —— 前几轮已多次出现这类缺陷。
