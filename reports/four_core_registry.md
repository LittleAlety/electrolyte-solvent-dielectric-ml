# W17-11 四大核心数据整理：跨通道注册表与通道关系矩阵

本表是**派生注册表**（键 = InChIKey，一行一键），不是新数据源；任何引用都必须同时说清它派生于哪几张源表。本臂只做整理与关系度量：不拟合任何模型、不产 MAE 与 R2、不引用主记分牌。

- 注册表：`data/processed/four_core_key_registry.csv`（31949 行 / 30 列）
- 通道：6 个，核心 4 个（介电常数 eps、黏度 eta、HOMO/LUMO/IP/EA/偶极、氧化还原自由能（RX-392 标签））
- 四核心全齐的键：7
- 判据：PASS

## 输入（判据 A：跑前逐位钉死）

| channel | path | sha256（前 16 位） | bytes | rows | keys | 钉死 |
|---|---|---|---|---|---|---|
| dielectric | `data/dielectric_v04.csv` | e046a3831630e36a | 134460 | 248 | 247 | 一致 |
| viscosity | `data/viscosity_v02.csv` | 907f5368ff6d4d6c | 11501156 | 42941 | 1228 | 一致 |
| orbitals_and_redox | `data/processed/redox_merged.csv` | 5b0731db9f1af784 | 7967704 | 29911 | 29868 | 一致 |
| density | `data/density_v01.csv` | 47f920f773054ccd | 29601928 | 182154 | 2178 | 一致 |
| liquid_window | `data/processed/liquid_window_features.csv` | a27386787f4c8198 | 175951 | 314 | 314 | 一致 |

## 通道覆盖（判据 C：口径自校验）

| 通道 | 源表 | 取值列 | 单位 | 归约 | 注册表 has_* = true | 口径键数 | 源表去重键数 |
|---|---|---|---|---|---|---|---|
| 介电常数 eps（`dielectric`） | `data/dielectric_v04.csv` | dielectric | dimensionless | nearest_to_target_T | 247 | 247 | 247 |
| 黏度 eta（`viscosity`） | `data/viscosity_v02.csv` | viscosity_Pa_s | Pa*s | nearest_to_target_T | 1228 | 1228 | 1228 |
| HOMO/LUMO/IP/EA/偶极（`orbitals`） | `data/processed/redox_merged.csv` | HOMO, LUMO, IP, EA, dipole | eV,eV,eV,eV,atomic_units(e*bohr) | first_non_empty_in_file_order | 29868 | 29868 | 29868 |
| 氧化还原自由能（RX-392 标签）（`redox_label`） | `data/processed/redox_merged.csv` | oxidation_free_energy, reduction_free_energy | eV | first_non_empty_in_file_order | 392 | 392 | 29868 |
| 密度 rho（`density`） | `data/density_v01.csv` | density_kg_m3 | kg/m3 | nearest_to_target_T | 2178 | 2178 | 2178 |
| 液相窗口（mp/bp/闪点/密度）（`liquid_window`） | `data/processed/liquid_window_features.csv` | mp_C, bp_C, flash_point_C, density_g_cm3 | degC,degC,degC,g/cm3 | first_non_empty_in_file_order | 218 | 218 | 314 |

orbitals 与 redox_label 共用 `data/processed/redox_merged.csv`，所以「源表去重键数」对这两个子通道是同一个数；要把两者分开，判据 C 只能按各自的取值列定义键集（即某个取值列里至少有一个有限数值）。

## 通道两两交集（键数）

| 通道 A | 通道 B | 交集键数 |
|---|---|---|
| 介电常数 eps | 黏度 eta | 143 |
| 介电常数 eps | HOMO/LUMO/IP/EA/偶极 | 84 |
| 介电常数 eps | 氧化还原自由能（RX-392 标签） | 10 |
| 介电常数 eps | 密度 rho | 180 |
| 介电常数 eps | 液相窗口（mp/bp/闪点/密度） | 181 |
| 黏度 eta | HOMO/LUMO/IP/EA/偶极 | 118 |
| 黏度 eta | 氧化还原自由能（RX-392 标签） | 10 |
| 黏度 eta | 密度 rho | 1179 |
| 黏度 eta | 液相窗口（mp/bp/闪点/密度） | 156 |
| HOMO/LUMO/IP/EA/偶极 | 氧化还原自由能（RX-392 标签） | 392 |
| HOMO/LUMO/IP/EA/偶极 | 密度 rho | 192 |
| HOMO/LUMO/IP/EA/偶极 | 液相窗口（mp/bp/闪点/密度） | 75 |
| 氧化还原自由能（RX-392 标签） | 密度 rho | 13 |
| 氧化还原自由能（RX-392 标签） | 液相窗口（mp/bp/闪点/密度） | 8 |
| 密度 rho | 液相窗口（mp/bp/闪点/密度） | 184 |

## 四核心全齐

同时有 ε、η、HOMO/LUMO（含 IP/EA/偶极）、氧化还原自由能标签的键：7 个。下表是全部键按「命中几个核心通道」的分布。

| 命中核心通道数 | 键数 |
|---|---|
| 0 | 898 |
| 1 | 30433 |
| 2 | 559 |
| 3 | 52 |
| 4 | 7 |

### 四通道全齐的三种口径（对账用）

| 口径 | 通道 | 键数 |
|---|---|---|
| prereg_core_four | dielectric、viscosity、orbitals、redox_label | 7 |
| with_liquid_window_data | dielectric、viscosity、orbitals、liquid_window | 51 |
| with_liquid_window_table_keys | dielectric、viscosity、orbitals、liquid_window(表键口径) | 53 |

液相窗口表的行数是 314，其中 96 行的 mp/bp/闪点/密度四列全空（`quality_layer = filter_only`，是过了筛选但没取到数的候选）。本注册表的 `has_liquid_window` 只认「四列里至少有一个有限数值」，即 218 键。上一轮登记的交集（ε 246 / η 202 / orbitals 89 / ρ 246）用的是表键口径；两种口径并列如下。


| 通道 | 与液相窗口的交集（表键口径） | 与液相窗口的交集（取值列口径） |
|---|---|---|
| 介电常数 eps | 246 | 181 |
| 黏度 eta | 202 | 156 |
| HOMO/LUMO/IP/EA/偶极 | 89 | 75 |
| 氧化还原自由能（RX-392 标签） | 10 | 8 |
| 密度 rho | 246 | 184 |

这 96 个空壳键里，有 65 个同时有 ε、46 个有 η、14 个有 orbitals —— 液相窗口的 filter_only 人口与核心名册高度重叠，不是一批无关化合物。

| 空壳键同时命中的通道 | 键数 |
|---|---|
| 介电常数 eps | 65 |
| 黏度 eta | 46 |
| HOMO/LUMO/IP/EA/偶极 | 14 |
| 氧化还原自由能（RX-392 标签） | 2 |
| 密度 rho | 62 |

## 描述性关系：Kirkwood-Frohlich 与 DFT 偶极

- 口径：registry 里 has_dielectric = true 且 dipole 非空且 eps > 0 的键
- n = 79（ε 名册 247 键；orbitals 通道 29868 键，其中带偶极 29519 键）
- K(eps) = (eps - 1) * (2 * eps + 1) / (9 * eps)
- Pearson(K(ε), μ_D²) = 0.6464482483155134
- Pearson(K(ε), μ_D) = 0.5934413462534026
- 对数版：n = 77，Pearson(log10 K, log10 μ_D²) = 0.11065312624151812（因非正而跳过 2 个）
- 角色：`descriptive_only_never_a_verdict`。这是描述性统计，只用来说明手里有多少料、关系是什么形态；不是模型性能，不是判决，不许当杠杆证据。样本量小（ε 名册只有 247 键），任何引用都要连同 n 一起给。
- 单位：源表 dipole 是 atomic_units (e*bohr)（见 `probes/p4_redox_summary.json` 的 units 块），本表同时给 dipole_D = dipole_au × 2.541746473。Pearson 对常数缩放不变，故 μ_au² 与 μ_D² 给出同一个 r。

## 判据 A-F

| 判据 | 结果 | 说明 |
|---|---|---|
| A 输入钉死 | PASS | 五个源表 sha256 与字节数逐位一致才继续 |
| B 表结构 | PASS | 列名与预注册逐字一致；31949 行 = 六通道键并集；一键一行 |
| C 口径自校验 | PASS | 每通道 has_* = true 的键数 = 该通道按取值列算出的键数 |
| D 不碰模型 | PASS | models_fitted = 0 / r2_reported = false / 主记分牌 0 次 |
| E 描述性关系 | PASS | 相关系数按描述性上报（n = 79），不是判决 |
| F 全 LF | PASS | 三件产物都以 newline=LF 写出，字节里没有 CR |
| 口径守卫 | PASS | 报告里没有性能断言用词，且带齐描述性与非判决标注 |

## 边界（不许外推）

- 本表是派生视图：源表才是事实；源表一改，本表与两份伴生件都要重跑。
- 归约口径写死在预注册里（nearest_to_target_T 的三级并列规则 / first_non_empty_in_file_order），不做平均、不跨温度外推。
- 温度归约到 298.15 K 只是选行规则，不代表该键只有这一个温度；要温度曲线请回源表。
- redox_label 通道只有 RX-392 的 392 条标签，是全仓最紧的瓶颈；四个外部数据源与 Reaxys 都没能补上它。
- 不含任何 Reaxys 数值；外部数据源（OMat24 / OMol25 / THEMol / 火山 QC）的核查结论见手册附录 AI-2b / AI-2c。
- 描述性关系只说明规模与形态，不是模型性能、不是判决、不许当杠杆证据。

## 复现

- 生成：`.venv/Scripts/python.exe probes/build_four_core_registry.py`
- 复核：`.venv/Scripts/python.exe probes/build_four_core_registry.py --check`
- 独立核验：`.venv/Scripts/python.exe scripts/verify_four_core_registry.py --check`
- 预注册：`probes/four_core_registry_prereg.json`（sha256 c54bbb96890dec44…）
