# ε–η Walden 耦合配对与 DN 第五通道登记（Week 17 臂 W17-7）

- 构建器：`probes/walden_dn_channel.py`（sha256 `33100ec7315e16d1badc38229b3beb99b4801940c053fd863bdba271dbcaa025`）
- 预注册：`probes/walden_dn_channel_prereg.json`（sha256 `90652b8a5d2bf1dbec1e1e6519d634951869d9c680bb5dd28e580aa7ac4a7fbb`，status=locked_before_run）
- 校验器：`scripts/verify_walden_dn_channel.py --check`（离线复算，PASS=0 / FAIL=1）
- 配对表：`data/processed/walden_coupling_pairs.csv`（1,219 行 + 表头，35 列）
- DN 覆盖审计：`data/processed/dn_coverage_audit.csv`（1,043 行 + 表头，16 列）
- 机读汇总：`probes/walden_dn_channel_summary.json`；其 `manifest` 记录配对表、DN 审计表、构建器与预注册的 sha256（汇总表不能自哈希，由校验器复算）。
- 复现构建：`.\\.venv\\Scripts\\python.exe probes\\walden_dn_channel.py`
- 复现校验：`.\\.venv\\Scripts\\python.exe scripts\\verify_walden_dn_channel.py --check`
- 网络访问：无（network_calls=0）；建模：无（models_fitted=0，r2_reported=false）；冻结件：6/6 INTACT。

## 方法

1. 只读 `data/processed/eta_epsilon_joint_observations.csv`，按 `InChIKey` 与温度列 `T_K` 把 ε 行与 η 行各自分桶；本臂不写、不重建该表，也不写它的排除表。
2. 配对判据（预注册口径）：同一 `InChIKey` 下 `abs(T_eps - T_eta) <= 1e-06 K`；**不插值、不外推、不搬温度**。
3. 冲突不平均：同一 `(inchikey, T_K)` 格内有 m 条 ε 与 n 条 η 时，全部 m×n 组合逐条落表，两侧 provenance 都在行内，`averaging_applied=false`。
4. 耦合量（预注册口径）：主口径 `walden_coupling_epsilon_times_eta = ε · η(Pa·s)`；副口径 `walden_ratio_eta_over_epsilon = η / ε(Pa·s)`，只作读数、不承载判决。
5. 来源四分归属：每行带 `epsilon_dataset_id` 与 `viscosity_dataset_id`，`pair_source_quadrant = '<ε源> x <η源>'`；`pair_quality_layer` 只在两侧都 publishable_core 时为 publishable_core。
6. DN 只做覆盖率检查与来源审计：目标键集 = 联表的全部 `InChIKey`；覆盖率判据 `covered / target >= 0.3`，且只有「实验 + 一手 DOI」的 DN 才允许覆盖一个键。

## 读数

### 联表现状复算（本臂自己重数，不引上游摘要）

| 口径 | 本臂读数 | 预注册期望 | 一致 |
|---|---|---|---|
| 观测行数 | 8,359 | 8,359 | 是 |
| 去重键数 | 1,043 | 1,043 | 是 |
| 来源四分 | epsilon_observations_v11plus 2,065 + pubchem_liquid_window_harvest 163 + schrodinger_viscosity_v01_open_subset 3,582 + thermoml_viscosity 2,549 | epsilon_observations_v11plus 2,065 + pubchem_liquid_window_harvest 163 + schrodinger_viscosity_v01_open_subset 3,582 + thermoml_viscosity 2,549 | 是 |

- ε 行 2,065，η 行 6,294。
- 两层口径：publishable_core 8,196 行，filter_only 163 行。
- 纯/混合：pure 6,293 行，mixture 2,066 行。

### Walden 配对

- 配对行 **1,219**，覆盖 **76** 个键；落在 394 个 `(InChIKey, T_K)` 格上。
- ε 有值的键 153，η 有值的键 993，两条都有值的键 103；其中 **27 个键两条都有值、却没有共享温度**，因此一条配对也不产生（不插值，不外推）。
- 逐键配对数：最少 1，最多 203。
- 主口径 ε·η：min 0.00047799，median 0.0172285，p95 0.0850174，max 9.702 Pa·s（全部配对）。
- 只算 publishable_core 配对（1,129 行）：min 0.00047799，median 0.0153346，max 5.10857 Pa·s。
- 全部配对的 `T_alignment_delta_K` 最大值为 0 K（口径 `abs_dT_le_1e-06_K`）。

### T 对齐敏感性阶梯（只是读数，永不进判决）

| 容差 (K) | 配对行 | 覆盖键 |
|---|---|---|
| 0.5 | 1,529 | 84 |
| 1 | 1,572 | 84 |
| 2 | 1,750 | 86 |

- a reading only. It is reported as counts next to the primary reading, it never forms the pair table and it never enters a verdict. The stored temperatures sit on a coarse grid (e.g. 278.15, 280.65, 283.15 K), so a widened tolerance would merge physically distinct temperatures rather than recover a rounding artefact.

### 来源四分归属与两层口径

| 来源象限 | 配对行 |
|---|---|
| epsilon_observations_v11plus x pubchem_liquid_window_harvest | 90 |
| epsilon_observations_v11plus x schrodinger_viscosity_v01_open_subset | 74 |
| epsilon_observations_v11plus x thermoml_viscosity | 1,055 |

- `pair_quality_layer`：publishable_core 1,129 行，filter_only 90 行；filter_only 来自 PubChem 汇编黏度腿，只许筛选、永不上头条。
- 两侧都纯：525 行；至少一侧为混合物：694 行。

### 冲突不平均

- 69 个格至少一侧有多值，全部 m×n 逐条保留，`averaging_applied=false`。

### DN 第五通道登记与覆盖率

- 目标键集：联表的全部 `InChIKey`（the distinct InChIKeys of the joint observation table），共 **1,043** 个键；判据 `covered / target >= 0.3`。
- 可用（实验 + 一手 DOI）覆盖：**0 / 1,043 = 0.0000** → **不过线**。
- 预测子通道（`solvfunc87_predicted_dn`，本地可键化 87 条）：覆盖 32 / 1,043 = 0.0307；**预测值按 §2.2 不具资格**，只作独立读数、绝不与可用覆盖合并。
- 次级目标集（publishable_core & pure，1,032 键）：可用覆盖 0，预测覆盖 32。
- 逐键状态分布：`{'no_dn': 1011, 'predicted_dn_only': 32}`。

| 候选来源 | 主张 | 可采信 | 本地证据 | 本地值数 | 未采信原因 |
|---|---|---|---|---|---|
| `dn218_acs_nano_experimental` | experimental | 是 | `data/external/g1plus/compilations/nn6c06255_si_001.txt`（在） | 0 | — |
| `solvfunc87_predicted_dn` | predicted | 否 | `data/external/SolvFunc-87.csv`（在） | 0 | predicted_not_experimental |
| `perricone2011_secondary_mopn` | secondary_compilation | 否 | `data/external/g1plus/mopn/perricone2011.txt`（在） | 0 | secondary_compilation_without_a_readable_primary |
| `gsds_zenodo_donornum` | predicted | 否 | `probes/artifacts/gsds_zenodo_archive_listing.json`（在） | 0 | generated_molecule_scoring_task_not_an_experimental_corpus |

- GSDS Zenodo 归档的 15,524 条条目名里，含 `DonorNum` 的 6,950 条**全部**落在生成分子打分任务目录内（独立 DN 数据集文件数 0）——归档内没有可用的 DN 数值表。
- ACS Nano SI（`data/external/g1plus/compilations/nn6c06255_si_001.txt`，sha256 `e29eb956ba44d2cd`）只提到 DN-218 数据集名（DN-218 出现 13 次）与图注，逐分子数值表未落地，本地读出值数 0。
- **判决**：`channel_does_not_enter_the_feature_table` —— 覆盖率不过线，且 §2.2 判 DN 只能实验，故本臂不给任何特征表引入 DN 列。

## 运动黏度解冻状态

- 联表排除表里 `kinematic_viscosity_not_dynamic` 共 214 条，其中 ThermoML 腿 176 条 —— 这是**族级**读数。
- 解冻依赖 `data/density_v01.csv`：该文件在盘上，`thawed=true`。
- 已解冻：data/density_v01.csv 在盘上，后续修订可把 nu 折成 eta 并升级为键级读数。判据与升级路径已写进预注册的 `kinematic_thaw`，解冻前置条件已满足，可把族级读数升级为键级读数，且不必改动本臂已落盘的配对表。

## 与预注册的冲突与不确定处

- **pair_rows_are_derived**（interpretation）：配对行是两条观测的**组合**，不是新测量；同一格多值时 m×n 展开会把行数放大，这是「不平均」纪律的直接后果，不是缺陷。
- **temperature_grid_is_coarse**（data_limitation）：联表温度落在粗网格上（如 278.15 / 280.65 / 283.15 K），所以「两通道都有值却不共享温度」的键占多数；扩大容差会把不同温度并成一个，故本臂坚持数值同一性口径，敏感性阶梯只作读数。
- **epsilon_side_is_always_publishable_core**（observation）：本构建里 ε 腿全部来自 `epsilon_observations_v11plus`（publishable_core），所以配对的层由 η 腿单独决定。
- **dn_temperature_binding_not_defined**（uncertainty）：DN 的记录温度（多为 25 °C）与联表的温度网格不是同一套，本臂只判覆盖率、不做温度对齐；即便日后取到 DN-218，也需要另一条臂先定温度归并口径，才能把它接到 Walden 配对上。
- **predicted_dn_column_encoding**（source_limitation）：`data/external/SolvFunc-87.csv` 是 cp1252 编码的 `;` 分隔表，本臂按该编码读；87 行 SMILES 全部可解析，无一行被丢弃。

## 边界（不许省略）

- **不拟合任何模型、不产任何 R²**：`models_fitted=0`、`r2_reported=false`，冻结基准 `0.4091179943351143` 未被触碰。
- **六件冻结件**：本臂只读，digest 逐位复算 —— `data/dielectric_v03.csv` INTACT；`data/processed/dielectric_observations_v11plus.csv` INTACT；`data/viscosity_v01.csv` INTACT；`probes/dielectric_r2_levers_prereg.json` INTACT；`probes/l3_backvalidation_prereg.json` INTACT；`probes/l3_stage1_pilot_pool.csv` INTACT。
- **不动既有产物**：`data/processed/eta_epsilon_joint_observations.csv` 与 `data/processed/eta_epsilon_joint_exclusions.csv` 只被读取，未被写入。
- **可采信 DN 覆盖为 0**：不是因为「取不到」，而是因为 §2.2 判 DN 为探针化学、只能实验，而本地全部 DN 型数据都是预测值或二手汇编值。
- **新增表的入库**：`data/processed/walden_coupling_pairs.csv` 与 `data/processed/dn_coverage_audit.csv` 是新文件，被 `.gitignore` 的 `data/processed/*` 命中，需另加白名单（本臂按纪律不改 `.gitignore`）。

## 校验

`scripts/verify_walden_dn_channel.py --check` 离线复算预注册 `verification_contract.checks` 的全 7 条，并对配对表、DN 审计表与构建器脚本做 SHA256 清单：

1. 联表逐项重数（行数、键数、来源四分）与预注册期望一致；
2. 每一行配对都带两侧 provenance，且 `averaging_applied=false`；
3. 每一行的 T 对齐规则成立（`abs(dT) <= 容差`）；
4. 两个耦合列都能由两侧存值按口径复算；
5. `pair_quality_layer` 与「两侧都 core」规则一致；
6. DN 覆盖率 = 覆盖键数 / 目标键数，判决按阈值；
7. 六件冻结件 digest 逐位不变。

校验器对给定文件报 PASS/FAIL 并返回退出码（PASS=0，FAIL=1）。
