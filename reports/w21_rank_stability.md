# W21 Tier 2：轨道通道的不确定性感知排序与筛选决策指标

按框架 §9 / §10 首次实例化。池 = 冻结 ε 名册 ∩ 我方 xTB ∩ Batt 身份命中，**n = 49**，配对数 1,176。
P_0 = GFN2-xTB 气相单点；R_sol = wB97X-V/def2-TZVPPD/SMD(ε=18.5)（MIT 许可，仅作 **reference layer**）。

## 1. §9 排序稳定性（HOMO 通道，方向 T = −HOMO）

| 量 | 值 |
| --- | --- |
| 配对数 | 1176 |
| P_0 侧 unresolved | 0.6156 |
| R_sol 侧 unresolved | 0.0519 |
| 至少一侧 unresolved | 0.6165 |
| 仅一侧可分辨 | 0.5655 |
| 朴素换序率 | 0.1556 |
| **robust inversion（§9.2 分母 = 两侧都可分辨）** | 0.0000 |
| τ 只数可分辨对 | 1.0000 |
| Kendall τ_b（原始值） | 0.6888 |
| Spearman ρ | 0.8640 |
| Pearson r | 0.8223 |

- robust inversion 的 bootstrap 95% CI：`{'lo': 0.0, 'median': 0.0, 'hi': 0.0, 'draws_used': 5000}`
- permutation 检验：`{'p_value': 1.0, 'permutations_used': 912}`（零假设 = 置换 R_sol 的化合物标签）
- 概率化配对排序：p>0.9 占 0.2755，p<0.1 占 0.2313，中间带占 0.4932

## 2. §10.1 / §10.2 Top-k 与 selection regret

| k | overlap | Jaccard | selection regret (eV) |
| --- | --- | --- | --- |
| k/N=10%（k=5） | 0.400000 | 0.250000 | 0.787400 |
| k/N=20%（k=10） | 0.900000 | 0.818182 | 0.100320 |
| k/N=30%（k=15） | 0.800000 | 0.666667 | 0.114680 |

regret 的定义：用便宜模型选出的 Top-k，在参考层下平均比参考层自己选的 Top-k 差多少（越大越差，0 = 无损失）。

## 3. 其它通道

- **lumo**（reference_only）：ρ = 0.6459，τ_b = 0.4660，robust inversion = 0.0000，Kendall/Spearman 只能作参照。
- **gap**（reference_only）：ρ = 0.5266，τ_b = 0.3537，robust inversion = nan，Kendall/Spearman 只能作参照。

### 1.1 容差敏感性（只有 z=1.96 预注册）

| z | P_0 侧可分辨 | 两侧都可分辨 | robust inversion | f_robust | 登记 |
| --- | --- | --- | --- | --- | --- |
| 1.96 | 0.384354 | 451 | 0 | 0.000000 | pre_registered |
| 1.0 | 0.579932 | 669 | 5 | 0.007474 | post_hoc_sensitivity |
| 0.674 | 0.714286 | 810 | 27 | 0.033333 | post_hoc_sensitivity |
| 0.0 | 1.000000 | 1115 | 153 | 0.137220 | post_hoc_sensitivity |

读法：**朴素换序 15.6% 全部落在 xTB 的不确定带里**——把分离要求从 z=1.96 放宽到 z=1.0 才出现 5 个 robust inversion，完全去掉容差才有 153 个。
这正是框架 §9.1 想拦下的那件事：不能把另一模型中的换序直接叫「物理 ranking inversion」。

## 4. §10.3 threshold-based decision error

not_instantiated_in_week21：HOMO 通道上没有来自外部设计要求/实验基准的阈值 T（charter section 8 patch 3）

## 5. 统计边界（必须随读数一起读）

- n=49 落在框架 §13.3 自警的薄区：本件的全部读数都是 machinery pilot，必须带 bootstrap CI 与 permutation 检验阅读，不得当达标结论。
- 参考层的物理不确定度本仓未量化，只登记数值容差；该缺口必须随读数一起报告
