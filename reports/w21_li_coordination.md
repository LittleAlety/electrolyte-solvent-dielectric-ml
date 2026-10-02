# W21 · Axis B `C_1`：Li⁺ 配位条件态首次实例化（GFN2-xTB 级）

- **预注册**：`probes/w21_li_coordination_prereg.json`（sha256 `f7fe520e1d913daa…`，status = `locked_before_run`）。
- **池**：冻结 ε 名册 246 化合物 × 2 臂 = 492 次 xTB；其中带配位基序 224 个、无基序（unbound_reference）22 个。
- **层级**：GFN2-xTB 半经验 + 单 Li⁺ + 单预注册构象 + 真空气相。**这不是框架 §7 要求的 DFT 级**，本臂把框架 §11 的 `X2`（条件态特征块）与 §3 Axis B 的 `C_1` 由「未执行」推进到「已实例化（低层级）」。
- **纪律**：不动四个冻结读数、不占 shot（本周主记分牌尝试 0 次，累计仍 12 次）、不引用 Reaxys 数值、不把 Batt 参考层折进任何训练池。

## 1. 池与质控

| 基序类 | n | intact | loose | dissociated | not_available |
| --- | --- | --- | --- | --- | --- |
| `lone_pair` | 178 | 175 | 0 | 0 | 3 |
| `anion_halide` | 6 | 2 | 0 | 0 | 4 |
| `aromatic_pi` | 21 | 21 | 0 | 0 | 0 |
| `alkene_pi` | 19 | 19 | 0 | 0 | 0 |
| `no_motif` | 22 | 17 | 1 | 2 | 2 |

质控判据（跑前冻结）：`intact` = Li–X ≤ 2.60 Å 且 q(Li) ≥ 0.30 e；`dissociated` = Li–X > 3.50 Å 或 q(Li) < 0.10 e；两者之间为 `loose`。

**一条与预注册预期不符、必须照实说的结果**：预注册写的期望是 `no_motif` 类应落到 `dissociated`（Li⁺ 在饱和烃/卤代烷上没有设计给体）。实测并非如此 —— GFN2-xTB 在这些分子上仍然让 Li⁺ 停在约 2.2–2.4 Å 的接触距离上，结构判据因此把它们判成 `intact`。结论：**几何距离 + Mulliken 电荷这两个判据不足以区分「设计过的给体配位」与「半经验方法在无给体分子上的虚假粘附」**。

为把这件事讲清楚，本件另附一条**事后补充（非预注册）**的相互作用强度判据：`binding = E([LiM]⁺) − E(M) − E(Li⁺)`，三项全部取自同一批 GFN2-xTB `--opt` 能量（Li⁺ 用单原子单点）。

| 基序类 | n | binding 均值 (eV) | 中位数 (eV) | 最小 (eV) | 最大 (eV) |
| --- | --- | --- | --- | --- | --- |
| `alkene_pi` | 19 | -1.3381 | -1.4322 | -1.5800 | -0.7641 |
| `anion_halide` | 2 | -0.1054 | -0.1054 | -3.9270 | +3.7162 |
| `aromatic_pi` | 21 | -1.1525 | -1.1686 | -1.6206 | -0.7858 |
| `lone_pair` | 175 | -1.9978 | -2.1639 | -8.5355 | +57.7645 |
| `no_motif` | 20 | +245.6988 | +107.6795 | +4.0247 | +1193.0152 |

该列**不参与任何预注册读数**，只用于解释上面的质控偏差；主读数（第 3、4 节）仍只用 224 个带基序化合物。

## 2. Δ 分布：C_0 → C_1 的条件位移（§12 的 direct vs conditional-shift 对照）

| 通道 | n | Δ 均值 (eV) | Δ 标准差 (eV) | var(Δ)/var(free) | ρ (C_0,C_1) | τ_b |
| --- | --- | --- | --- | --- | --- | --- |
| `homo` | 217 | -4.0459 | 0.8747 | 0.1645 | 0.6273 | 0.4721 |
| `lumo` | 217 | -7.6960 | 3.1894 | 1.0085 | 0.2296 | 0.1706 |
| `gap` | 217 | -3.6501 | 3.4318 | 0.9193 | 0.2737 | 0.1960 |

读法：`var(Δ)/var(free)` 量的是「配位这一步造成的位移」相对「溶剂身份造成的总展宽」有多大。该比值远小于 1 意味着条件态是二阶效应，但它非零本身说明条件态携带独立信息。

## 3. C_0 → C_1 的排序稳定性（§9 的内部台阶）

| 通道 | pairs | naive 换序 | 换序率 | Top-k 10% overlap | Top-k 20% | Top-k 30% |
| --- | --- | --- | --- | --- | --- | --- |
| `homo` | 23436 | 6188 | 0.2640 | 0.909 | 0.651 | 0.631 |
| `lumo` | 23436 | 9719 | 0.4147 | 0.000 | 0.140 | 0.277 |
| `gap` | 23436 | 9422 | 0.4020 | 0.136 | 0.256 | 0.308 |

- `homo`：ρ 的 bootstrap 95% CI = [0.5172, 0.7198]（5000 次重采样）；Top-k 10% overlap 的 CI = [0.636, 1.000]。
- `lumo`：ρ 的 bootstrap 95% CI = [0.0994, 0.3581]（5000 次重采样）；Top-k 10% overlap 的 CI = [0.000, 0.000]。
- `gap`：ρ 的 bootstrap 95% CI = [0.1274, 0.4106]（5000 次重采样）；Top-k 10% overlap 的 CI = [0.000, 0.273]。

## 4. §9 复核：49 化合物 Batt 子集上的三层并排

参考层：`batt_homo_eV`（ωB97X-V/def2-TZVPPD/SMD(ε=18.5)，MIT）。容差：z = 1.96、Δ_R_sol = 0.05 eV。

| 廉价层 | n | pairs | resolved_in_both | robust inversion | f_robust | naive 换序率 | τ_b | ρ |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `P0_themol_geometry_w21_1` | 49 | 1176 | 451 | 0 | 0.0000 | 0.1556 | 0.6888 | 0.8640 |
| `C0_this_arm_free` | 49 | 1176 | 482 | 0 | 0.0000 | 0.1590 | 0.6820 | 0.8606 |
| `C1_this_arm_li` | 49 | 1176 | 329 | 0 | 0.0000 | 0.1905 | 0.6190 | 0.8062 |

`P0_themol_geometry_w21_1` 行是本文件对 W21-1 的回归核验：用同一套代码重算 W21-1 的 P_0（THEMol 几何），应当复现其 `robust inversion = 0 / 451`。

## 5. 与 v03 物理块的一致性核验

- n = 237；Pearson r = 1.0000；平均有符号差 = -0.0001 eV；平均绝对差 = 0.0058 eV。
- 说明：同协议（GFN2-xTB --opt）、不同构象种子；用作 C_0 器的独立一致性核验

## 6. §19 Gate 1 判词

- Gate 1 仍未闭合，但缺口性质改变：X2 槽位以前是「空的」，现在第一次有了内容。
- C_1 侧仍无外部参考层（Batt 只覆盖 49 个化合物，且是自由态轨道能）；本臂给出的是 C_0 到 C_1 的内部台阶证据与 §9 三层并排（C_1 行：robust inversion = 0 / 329），而不是「条件态已被外部基准验证」。

## 7. 边界与不做

- 层级只到 GFN2-xTB 半经验，不是框架 §7 要求的 DFT 级；这是 X2 槽位的首次实例化，不是等价替换。
- 单 Li⁺、单预注册构象、真空气相；不是显式微溶剂化（C_2），也不是 SMD 连续介质。
- C_1 侧没有外部参考层；Batt 只覆盖 49 个化合物，且只用于自由态轨道的三层并排。
- 参考层物理不确定度未量化，只登记 0.05 eV 数值容差 —— 该缺口随读数一起报告。
- 溶剂化自由能 / 配位能 ΔG 未算（缺热化学与溶剂化处理），本臂只报轨道能与基序几何。
- 不与 ε 主记分牌、η 通道或数据集级基准混比。

## 8. 事后诊断（明确标注：非预注册，不进任何主读数）

### 8.1 冻结协议下的失败臂

| 化合物 | 基序类 | C_0 | C_1 | 原因 |
| --- | --- | --- | --- | --- |
| 1,3-dimethylimidazolium dimethylphosphate | `lone_pair` | xtb_failed | xtb_failed | returncode=128 sentinel=False: -1- scf: Self consistent charge iterator did not converge / returncode=128 sent |
| 1-butyl-3-methylimidazolium hexafluorophosphate | `anion_halide` | xtb_failed | ok | returncode=128 sentinel=False: -1- scf: Self consistent charge iterator did not converge |
| 1-butyl-2,3-dimethylimidazolium hexafluorophosphate | `anion_halide` | xtb_failed | ok | returncode=128 sentinel=False: -1- scf: Self consistent charge iterator did not converge |
| 1-butyl-3-methylimidazolium tetrafluoroborate | `anion_halide` | ok | xtb_failed | returncode=128 sentinel=False: -1- scf: Self consistent charge iterator did not converge |
| 1-butyl-2,3-dimethyl-1H-imidazolium bis(trifluoromethylsulfonyl)amide | `lone_pair` | ok | xtb_failed | returncode=128 sentinel=False: -1- scf: Self consistent charge iterator did not converge |
| 1-butyl-2,3-dimethylimidazolium tetrafluoroborate | `anion_halide` | ok | xtb_failed | returncode=128 sentinel=False: -1- scf: Self consistent charge iterator did not converge |
| 2-Methylbutane | `no_motif` | ok | xtb_failed | returncode=128 sentinel=False: -1- optimizer_relax: /grad/ > 500, something is totally wrong! |
| Iron pentacarbonyl | `lone_pair` | xtb_failed | xtb_failed | returncode=128 sentinel=False: -1- Found *very* short distance of  0.000E+00 for C1-C3 / returncode=128 sentin |
| 2-Fluoro-2-methylbutane | `no_motif` | ok | xtb_failed | returncode=128 sentinel=False: -1- optimizer_relax: /grad/ > 500, something is totally wrong! |

### 8.2 SCF 重试（事后）

- 失败臂 **11** 个；换用 `--iterations 1000 --etemp 1000` 重试后 **恢复 3 个、仍失败 8 个**。
- 目的只是区分「SCF 设置伪失败」与「方法层面的真实失败」；冻结层的 246 个化合物读数**不因此改变**。

### 8.3 结合能体检（事后）

- 定义：`binding_eV = E([LiM]⁺) − E(M) − E(Li⁺)`，三项全部来自同一批 GFN2-xTB 能量。
- **判读**：真实给体配位的结合能在 −1 至 −2 eV 量级；结合能为**正**意味着那张「C_1 结构」在能量上根本不成立（Li⁺ 其实没有留下来）。
- 本件共 **24** 行的结合能为正，按基序类统计：
  anion_halide 1 行、lone_pair 3 行、no_motif 20 行。
- **20 行**落在 `no_motif`（unbound_reference）类：冻结的结构判据把它们判成 `intact`/`loose`，结合能体检把它们标为 `not_a_bound_state`。主读数（第 3、4 节）本来就只用带基序化合物，因此不受影响。
- 另外 **4 行落在带基序类内**（见上表），也就是说：**结构判据单独用会骗人，而且骗到的不只是无给体分子**。

**事后敏感性**：把上述 4 行剔除后，重算第 3 节的排序稳定性读数。

| 通道 | n（剔除后） | ρ（剔除后） | ρ（全池） | Top-10% overlap（剔除后） |
| --- | --- | --- | --- | --- |
| `homo` | 213 | 0.6115 | 0.6273 | 0.857 |
| `lumo` | 213 | 0.2295 | 0.2296 | 0.000 |
| `gap` | 213 | 0.2560 | 0.2737 | 0.143 |

剔除的化合物：1-(2-hydroxyethyl)-3-methylimidazolium tetrafluoroborate、1-methylimidazole、1-methylimidazolium bromide、1-methylimidazolium chloride。**结论不随剔除而改变**，这是本条体检最重要的信息。

*W21 Tier 3 · 生成脚本 `probes/w21_li_coordination.py` · 预注册冻结 · 冻结读数未动 · shot 未增*
