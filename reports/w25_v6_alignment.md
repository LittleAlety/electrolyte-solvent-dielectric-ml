# W25 结题报告：母体论文 v6 发展方向的本仓对照

- **性质**：零 QC 只读对照（W25-1 至 W25-4）；不新增电子结构计算，不占主记分牌 shot（累计仍 12）。
- **预注册**：`02f83d7e120af4d493fc669157dc22ddf24a0330d03dcf7360f152895d990eda`，status = locked_before_run。
- **对照对象**：母体论文 v6（r2SCAN-3c / 18 分子 / 10 台阶）。

## 0. 一句话

v6 的六条方向里，⒂⒃⑴ 本仓早已实现且规模更大；本轮把差距最大的四条补齐后，最硬的一条反读是：v6 报「稳健翻转全 0」（分支 C 未观测），而本仓在 38 / 38 个台阶-轴上看到非零（最大 0.393），且它与未解析占比同步（rho = 0.936）；同时本仓在 246 分子上把 v6 的「11/12 铝中心还原」降到 0.34/0.26，说明那一条也带小样本成分。追因后这条「矛盾」不是物理分歧，而是**同名不同阈**：本仓用绝对 0.05 eV 分辨分子对，v6 的 frobustinv(z) 用随 σ 缩放的阈值，后者让位移离散度大的台阶整轴自动落入 unresolved，「已分辨却翻转」的窗口按构造为空；同一轮还给出另一条只在大池上成立的读数——位移离散度判据在 N=246 上是 -0.8095，在 N=28 上坍缩到 -0.2037（bootstrap 区间跨 0）。

## 1. W25-1：位移离散度判据的完整版检验（38 台阶-轴）

| 台阶集 | n | rho(std, tau_b) | 95% CI | rho(abs(mean), tau_b) | rho(std, f_unres) | 留一台阶出 MAE | 方向命中 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 合并（W24-1 + W24-2） | 38 | -0.7878 | [-0.896, -0.582] | -0.6569 | 0.8346 | 0.076 | 27/38 |
| 仅 W24-1（N=246） | 28 | -0.8095 | [-0.920, -0.583] | -0.6393 | 0.8298 | 0.081 | 24/28 |
| 仅 W24-2（N=28） | 10 | -0.2037 | [-0.849, 0.628] | -0.3025 | 0.1049 | 0.058 | 4/10 |

v6 在 10 个台阶上报 -0.8511 / -0.5350 / +0.8936；本仓在 38 个台阶-轴上报 -0.7878 / -0.6569 / 0.8346。方向一致；下面逐条读。

![图 A　位移离散度判据：38 个台阶-轴上的 std vs tau_b，以及三个相关系数的 bootstrap 区间（本仓 vs v6）。](probes/artifacts/w25_dispersion_criterion.png)

## 2. W25-2：f_robust_inv 的矛盾归因

- 本仓非零台阶-轴：**38 / 38**；最大 f_robust_inversion = **0.3931**，均值 0.1078。
- rho(f_robust, f_unresolved) = **0.9361**，95% CI [0.856, 0.967]。
- 非零台阶-轴中 f_unresolved 的最小值为 0.0513。
- 分层：C rung / ox x9, C rung / red x9, P rung / ox x10, P rung / red x10。

![图 B　稳健翻转与未解析占比的关系，以及稳健翻转最高的台阶-轴。](probes/artifacts/w25_robust_inversion.png)

## 3. W25-3：最小昂贵标签预算（237 池，回溯重放）

- 目标量：`delta_homo_eV`（C0→C1 氧化轴条件位移）；特征：homo_free_eV, lumo_free_eV, gap_free_eV, formal_charge, total_energy_free_hartree（本仓 X0 代理）。
- 代理模型：KRR（RBF，alpha 由已揭示集的 LOO 选择）；初始标签 4，每轮揭示 1 个，上限 120 步。
- 恢复判据：中位 tau_b 首次 >= 0.80 所需标签数 n_T。
- 池：237 行（冻结 246 化合物名册里 X0 代理特征与目标量齐全者；不齐的行在入池前剔除，标签未删）。

| 采集函数 | n_T（中位） | 逐种子 n_T |
| --- | --- | --- |
| random | 121 | [121, 121, 121, 121, 121, 121, 121, 121, 121, 121] |
| diversity | 121 | [121, 121, 121, 121, 121, 121, 121, 121, 121, 121] |
| uncertainty | 121 | [121, 121, 121, 121, 121, 121, 121, 121, 121, 121] |
| ranking_aware | 121 | [121, 121, 121, 121, 121, 121, 121, 121, 121, 121] |

![图 C　最小昂贵标签预算：四种采集函数在 237 池上的中位恢复曲线。](probes/artifacts/w25_al_budget.png)

## 4. W25-4：分支认领 A–G 的本仓对照

| 分支 | 判据 | v6 判决 | 本仓判决 |
| --- | --- | --- | --- |
| A | cheap proxy already sufficient | NOT SUPPORTED | **NOT SUPPORTED** |
| B | large shift but stable ranking | SUPPORTED | **PARTIALLY SUPPORTED (differs from v6)** |
| C | structurally concentrated robust inversion | NOT OBSERVED | **OBSERVED (differs from v6)** |
| D | coordination changes state identity | OBSERVED | **PARTIALLY SUPPORTED (differs from v6)** |
| E | shift (delta) learning beats direct learning | SUPPORTED | **NOT TESTED** |
| F | shift cannot be learned from cheap features | NOT SUPPORTED | **NOT SUPPORTED (same direction as v6)** |
| G | most pairs unresolved | PARTIALLY SUPPORTED | **SUPPORTED** |

与 v6 判决不同的分支：**B, C, D, E, G**。

## 5. 判据裁决

| 编号 | 判据 | 实测 | 裁决 |
| --- | --- | --- | --- |
| H1a | rho(std, tau_b) <= -0.70 | -0.7878 | **成立** |
| H1b | |rho(std, tau_b)| >= |rho(|mean|, tau_b)| | -0.7878 vs -0.6569 | **成立** |
| H1c | leave-one-rung-out direction hits >= 8 | 27/38 | **成立** |
| H2 | every nonzero f_robust_inversion is a C rung or has f_unresolved >= 0.30 | 28/38 satisfy the gate; 10 violate it (worst f_unresolved among violators = 0.262) | **判否** |
| H2a | rho(f_robust, f_unresolved) >= 0.30 with CI excluding 0 | 0.9361 [0.856, 0.967] | **成立** |
| H2b | max f_robust_inversion <= 0.20 | 0.3931 | **判否** |
| H3a | random n_T >= 60 | 121 | **成立** |
| H3b | uncertainty or diversity beats random (paired CI excludes 0) | uncertainty n_T = 121, delta(random - alt) = 0.00 [0.00, 0.00] | **判否** |
| H3c | ranking-aware not better than random | n_T = 121 vs random 121 | **成立** |
| H4 | at least one branch verdict differs from v6 | 5 differing: B, C, D, E, G | **成立** |

## 6. 口径与限制（必须与数字同句引用）

- W25-1 的 38 个台阶-轴不独立（同一台阶两条轴共享分子，且两个池的水平不同），所以 bootstrap 区间只能读作「同一关系的稳健性」，不能读作显著性检验。
- v6 的 -0.8511 / -0.5350 / +0.8936 是 10 个台阶的读数，与本仓 38 个台阶-轴的读数只能比方向与量级，不能比大小。
- W25-3 的 X0 特征是本仓口径下的代理（廉价层的自由分子标量），与 v6 的 12 项 X0 不同名同定义；池也从 18 放到 237（246 名册里 5 项代理特征与目标量齐全的行），因此 n_T 只能读作「本池、本特征集」下的预算。
- 各采集函数只有 10 种子，配对 bootstrap 区间的功效有限；不得写成「某采集函数显著更优」。
- 本轮不新增电子结构计算，因此 W25-2 的归因是「口径 + 功效」层面的，不是对 v6 ΔSCF 实现的复核。
- 图 12 以后的一切读数不得与母体论文的绝对值相除或相加。
- W25-3 在 120 步上限处右删失（budget_censored_at = 121）：四种采集函数的中位 n_T 全为 121，10 种子无一达标。因此 H3a（random n_T >= 60）与 H3c（ranking-aware 不比 random 好）是删失状态下自动成立的空判据，不携带信息；本轮只有 H3b 是真判据，且判否。
- W25-1 最值钱的一读不是 38 个台阶上的 ρ 本身，而是它对池规模的依赖：同一条判据在 N=246 子集上给出 ρ(std, tau_b) = -0.8095（bootstrap CI 上界 < 0），在 N=28 子集上给出 -0.2037（CI [-0.849, 0.628]，跨 0）。也就是说「位移离散度而非位移幅值决定排序损失」是一个大池性质，在 28 个化合物上不可复现；母体论文的 10 台阶读数属小池读数，与它同句引用时必须声明池规模。
- W25-2 的对比是同名不同阈：本仓 f_robust_inversion 用绝对分辨阈（源侧位移差与对间差都 >= 0.05 eV 才算已分辨），母体论文的 frobustinv(z) 用随 σ 缩放的阈（已分辨等价于 gap >= z·σij，σij = |δi − δj| / sqrt(2)）。在后者口径下，位移离散度大的台阶几乎整轴自动落入 unresolved，「已分辨却仍然翻转」的窗口按构造为空，因而那 40 个读数全为 0；本仓的绝对阈让同一窗口在 38 个台阶上处处非空。两者不是同口径读数，只能读作「零稳健翻转是阈值约定的产物」，不能读作母体论文的结论被推翻。母体论文自己给出的敏感性（改用 σij² = (δi² + δj²)/2 时 unresolved 升到 0.95-1.00）与这条同向。
- W25-2 的预注册判据 H2（非零翻转须全部落在 C 台阶或 f_unresolved >= 0.30）判否：38 个非零翻转里有 10 个不满足该门（其中最小 f_unresolved 低至 0.262），所以「本仓的非零来自条件态台阶」这个机制假设不成立。成立的只有 H2a：f_robust 与 f_unresolved 同源（ρ = 0.9361，CI [0.856, 0.967]）。

## 7. 产物清单

| 文件 | 内容 |
| --- | --- |
| `probes/w25_v6_alignment.py` | 本探针（只读） |
| `probes/w25_v6_alignment_prereg.json` | 跑前冻结的预注册 |
| `probes/artifacts/w25_dispersion_criterion.csv` | W25-1 的 rho / CI / 留一台阶出读数 |
| `probes/artifacts/w25_robust_inversion_attribution.csv` | W25-2 的逐台阶稳健翻转归因 |
| `probes/artifacts/w25_al_budget.csv` | W25-3 的逐步恢复曲线 |
| `probes/artifacts/w25_branch_claims.csv` | W25-4 的 A–G 分支认领 |
| `probes/artifacts/w25_dispersion_criterion.png` | 图 A |
| `probes/artifacts/w25_robust_inversion.png` | 图 B |
| `probes/artifacts/w25_al_budget.png` | 图 C |
