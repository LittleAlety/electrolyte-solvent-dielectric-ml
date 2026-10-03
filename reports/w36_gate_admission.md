# W36-D 结题报告：引用登记升为准入清单

- **性质**：后验治理件（只读 W34-A 注册表与 W35-A 登记表），**不占 shot**
- **累计 shot**：19

## 1. 机制

`admit(axis, level, medium, quantity, population_scope)`：

1. 先查 `probes/artifacts/w35_gated_reference_register.csv`——**没登记就抛 `AdmissionRefused`**；
2. 氧化轴直接返回「不适用」（门禁是阴离子态审计）；
3. 还原轴**重新调用 W34-A 的 `assert_redox_readable`** 得到 `mark`，与登记表里的值比对；
4. 不一致即判否（防手写「可宣读」）。

## 2. 准入清单

| 引用点 | 轴 | 层级 | 介质 | 总体 | legal | quoted | mark |
| --- | --- | --- | --- | --- | --- | --- | --- |
| r6_ox_gfn2 | oxidation | gfn2 | gas | paired_orca_22 | — | 0.6969696969696969 | 不适用（门禁只覆盖还原轴） |
| r6_ox_orca | oxidation | orca | gas | paired_orca_22 | — | 0.6536796536796536 | 不适用（门禁只覆盖还原轴） |
| r6_red_gfn2 | reduction | gfn2 | gas | paired_orca_22 | 1 | 0.8354978354978355 | 不可判定 |
| r6_red_orca | reduction | orca | gas | paired_orca_22 | 0 | -0.6017316017316018 | 不可判定 |
| w33a_gfn2_gas | reduction | gfn2 | gas | census_246 | 52 | 0.7450980392156863 | 可宣读 |
| w33a_gfn2_thf | reduction | gfn2 | thf | census_246 | 154 | 0.7331296154825566 | 可宣读 |
| w33a_gfn2_benzaldehyde | reduction | gfn2 | benzaldehyde | census_246 | 154 | 0.6740626074991402 | 可宣读 |
| w33a_gfn2_water | reduction | gfn2 | water | census_246 | 161 | 0.8119565217391304 | 可宣读 |
| w33a_orca_gas | reduction | orca | gas | paired_orca_22 | 0 |  | 不可判定 |
| w33a_orca_smd_acetonitrile | reduction | orca | smd_acetonitrile | paired_orca_22 | 2 |  | 不可判定 |

## 3. 负对照（未登记 = 不准入）

| 格子 | 裁决 | 理由 |
| --- | --- | --- |
| reduction/r2scan3c/gas/census_246 | 拒绝 | 未登记：准入清单里没有 reduction/r2scan3c/gas/tau_legal/census_246。新增还原轴读数必须先落进 w35_gated_reference_register.csv。 |
| reduction/gfn2/benzene/census_246 | 拒绝 | 未登记：准入清单里没有 reduction/gfn2/benzene/tau_legal/census_246。新增还原轴读数必须先落进 w35_gated_reference_register.csv。 |
| reduction/gfn2/gas/paired_orca_27 | 拒绝 | 未登记：准入清单里没有 reduction/gfn2/gas/tau_legal/paired_orca_27。新增还原轴读数必须先落进 w35_gated_reference_register.csv。 |

## 4. 判据

| 判据 | 内容 | 读数 | 阈值 | 裁决 |
| --- | --- | --- | --- | --- |
| H36d1 | 准入清单里每一行都通过准入 | 10 | 10 | 成立 |
| H36d2 | 准入清单可由 W35-A 的同一推导逐行复现（含 mark 与 legal_n） | 1 | 1 | 成立 |
| H36d3 | 全部还原轴行的 mark 由 W34-A 守卫复算，与登记值零不一致 | 0 | 0 | 成立 |
| H36d4 | 未登记的合成格子全部被拒（未登记 = 不准入） | 3 | 3 | 成立 |
| H36d5 | 还原轴行在准入件里都带 mark；氧化轴行标「不适用」 | 8 | — | 成立 |

## 5. 边界

- 只读；不重跑模型、不新增数据、不改任何被冻结的读数。
- 准入清单**只约束还原轴**；氧化轴按 W33-A 条款判「不适用」。
- 拒答不是缺失值：不可判定的格子允许被引用，但必须带 `mark`，不得插补或赋伪值。
- 不占 shot（累计仍 19）。
