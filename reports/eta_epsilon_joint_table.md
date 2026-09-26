# η–ε 联合温度分辨观测表（Week 16 首建）

- 构建器：`probes/build_eta_epsilon_joint_table.py`（sha256 `fba406bb9f4de692aeee66068ef5a82c79a5efa61b96ca8f86c2e718f65f1932`）
- 校验器：`probes/verify_eta_epsilon_joint_table.py`
- 机读汇总：`probes/eta_epsilon_joint_summary.json`
- 观测表：`data/processed/eta_epsilon_joint_observations.csv`（8,359 行 + 表头，27 列）
- 排除表：`data/processed/eta_epsilon_joint_exclusions.csv`（11,977 行 + 表头）
- 契约：`probes/eta_epsilon_joint_schema_prereg.json`（sha256 `132037c8d50767958a81c4347df841b45a3182f1d60093751722f84dac4915c8`，status=locked_before_run）
- 复现构建：`.\.venv\Scripts\python.exe probes\build_eta_epsilon_joint_table.py`
- 复现校验：`.\.venv\Scripts\python.exe probes\verify_eta_epsilon_joint_table.py`
- 网络访问：无（只读 4 个本地源表）；冻结产物写入：无；建模：无（本周只做数据工程）。

## 数据来源

| dataset_id | 源文件 | 源行数 | 进表观测 | 排除记录 | sha256（前 16 位） |
|---|---|---|---|---|---|
| epsilon_observations_v11plus | `data/processed/dielectric_observations_v11plus.csv` | 2,065 | 2,065 | 0 | 159b928f800a5596 |
| thermoml_viscosity | `data/processed/viscosity_observations_thermoml.csv` | 2,725 | 2,549 | 176 | e0d647d6eadc0adc |
| schrodinger_viscosity_v01_open_subset | `data/viscosity_v01.csv` | 3,582 | 3,582 | 0 | 12dfa03f34284c93 |
| pubchem_liquid_window_harvest | `data/external/g1plus/pubchem/liquid_window` | 11,910 | 163 | 11,801 | （目录，见逐文件行） |

源行总数 20,282；其中 `source_rows_uncovered` = 0（必须为 0：任何既没进表、也没有排除记录的源行都是缺陷）。

## 方法

1. ε 线：逐行读 `dielectric_observations_v11plus.csv`，`unit='1'`、`property='epsilon'`；`uncertainty` 取源表的 `uncertainty_expanded`，`uncertainty_kind` 原样保留源值。
2. η 线（ThermoML）：逐行读 `viscosity_observations_thermoml.csv`，只接受 `property_unit='Pa*s'` 且 `viscosity_Pa_s` 非空的行；176 行运动黏度（m2/s）写进排除表。
3. η 线（Schrödinger 开放子集）：逐行读 `viscosity_v01.csv` 的 3,582 行实验值；受限 858 条没有获取、没有推断、没有重建，`supp_3` 的 650 条预测值没有进入。
4. PubChem 液态窗口：逐文件按文档顺序枚举**每一个** `StringWithMarkup` 取值行；只有 `Viscosity` 节能用严格文法读成 (Pa*s, K) 的才进表（`quality_layer='filter_only'`），其余每一个取值行都写进排除表并给原因。
5. 恒等键 `(inchikey, property, T_K, source_file, source_row_index)`：冲突值全部保留，既不平均也不挑选；本模块只统计冲突键。
6. 每行都带 `source_file`、`source_row_index`（该文件内 0 基行号）与 `source_file_sha256`。
7. 评估契约：对 `publishable_core & pure` 子集真跑一次 `GroupKFold` by InChIKey，并断言 `group_overlap == 0`；失败即停，不是告警。

## 读数

### 总行数与分布

| 维度 | 取值 | 行数 |
|---|---|---|
| property | epsilon | 2,065 |
| property | viscosity | 6,294 |
| property_family | dielectric_constant | 2,065 |
| property_family | dynamic_viscosity | 6,294 |
| dataset_id | epsilon_observations_v11plus | 2,065 |
| dataset_id | pubchem_liquid_window_harvest | 163 |
| dataset_id | schrodinger_viscosity_v01_open_subset | 3,582 |
| dataset_id | thermoml_viscosity | 2,549 |
| pure_or_mixture | mixture | 2,066 |
| pure_or_mixture | pure | 6,293 |
| quality_layer | filter_only | 163 |
| quality_layer | publishable_core | 8,196 |
| source_kind | compilation | 163 |
| source_kind | primary_thermoml_measurement | 4,614 |
| source_kind | published_supplement_open_subset | 3,582 |
| licence | cc_by_4_0 | 3,582 |
| licence | publisher_terms_see_source | 163 |
| licence | thermoml_open | 4,614 |
| unit | 1 | 2,065 |
| unit | Pa*s | 6,294 |
| redistributable | false | 163 |
| redistributable | true | 8,196 |
| n_components | 1 | 6,293 |
| n_components | 2 | 1,524 |
| n_components | 3 | 542 |

合计 8,359 行，覆盖 1,043 个 InChIKey。

### 两层口径

- `publishable_core`：**8,196 行**，覆盖 **1,037 个 InChIKey**（quality_layer=publishable_core, i.e. first-hand DOI plus a measurement）。
- `filter_only`：163 行，覆盖 113 个 InChIKey（PubChem 汇编值，只允许做筛选，永远不计入可发表口径）。
- 纯组分子集：6,293 行 / 1,039 个 InChIKey；混合物 2,066 行照存但不作为建模目标。

### 冲突键

- `(inchikey, property, T_K)` 共 5,592 个键，其中**304 个键存在多个不同取值**（涉及 3,014 行）；只算 `publishable_core` 是 283 个键。
- 全部保留、绝不平均；`averaging_applied = False`。
- 主键重复：0（必须为 0）。

### 排除记录

共 11,977 条，覆盖 11,967 个源行。

| reason_code | 条数 |
|---|---|
| composition_undetermined | 9 |
| dielectric_frequency_unstated | 2 |
| kinematic_viscosity_not_dynamic | 214 |
| no_numeric_value | 1 |
| no_temperature_reported | 7 |
| phase_or_state_not_liquid | 2 |
| property_not_in_joint_enum | 11,735 |
| unit_not_recognized | 7 |

逐 `dataset_id`：pubchem_liquid_window_harvest 11,801，thermoml_viscosity 176。

### 评估契约

- `splitter = "GroupKFold by InChIKey"`，分组键 `inchikey`，5 折，子集：quality_layer=publishable_core and pure_or_mixture=pure（6,130 行 / 1,032 组）。
- 断言 `group_overlap == 0 between train and test groups`：**通过**（`max_group_overlap = 0`）。断言失败是停工，不是告警。
- `random_row` 仅作泄漏参照：同一子集按行随机切分时，测试行中5,555 / 6,130 行的 InChIKey 同时出现在训练集里（泄漏比例 0.906199）。它**永不进判决**：同一个化合物出现在多个温度上，按行随机切分会把同一化合物放到切分两侧。
- 本轮判决来源：none: this round is data engineering, no model is fitted。

## 与预注册的冲突与不确定处

- **pubchem_property_enum_conflict**（prereg_internal_conflict）：merge_rules.first_build_sources describes the PubChem liquid-window harvest as 'MP/BP/FP/density, filter_only', but observation_schema restricts property to epsilon and viscosity. MP/BP/FP/density are neither, so they are enumerated in the exclusions file (reason property_not_in_joint_enum) instead of being stored. Storing them would require editing the locked schema, which lock_rule forbids; this is reported as a correction candidate for a later round.
- **pubchem_dielectric_frequency**（interpretation）：two harvested Dielectric Constant strings fit the property enum but state no frequency, and the schema note says a dielectric value without its frequency is not a defined measurement; both are excluded (reason dielectric_frequency_unstated) rather than stored with an empty frequency.
- **dielectric_uncertainty_kind**（source_vocabulary）：every epsilon row carries uncertainty_kind='combined' from the source, while the schema note lists 'expanded / standard / unknown'. The source value is kept verbatim rather than reinterpreted; this needs a main-thread decision.
- **pubchem_source_doi_empty**（source_limitation）：no harvested PubChem viscosity value row carries an ExtendedReference DOI, so source_doi is empty on every filter_only row. The schema allows an empty DOI only in filter_only, which is exactly this layer.
- **pubchem_free_text_parsing**（interpretation）：the harvest stores viscosity as free text. Only shapes with one number, one recognised unit and one numeric temperature are read; every other clause leaves an exclusion record. A different parser would yield a different count, so those rows stay filter_only and are never quoted in the publishable headline.
- **schrodinger_n_components**（assumption）：data/viscosity_v01.csv carries no composition column. It is the open subset of a one-InChIKey-per-row pure-substance viscosity supplement, so n_components=1 and pure_or_mixture='pure' are recorded and not silently defaulted.
- **thermoml_smiles_absent**（source_limitation）：viscosity_observations_thermoml.csv exposes 'smiles_or_name', which holds the compound name on every row inspected; smiles is therefore empty on every ThermoML viscosity row rather than guessed from a name.
- **row_id_is_a_source_row_label**（schema_limitation）：the schema prescribes row_id={dataset_id}:{source_row_index}, so a harvested PubChem value row that reports two temperatures yields two rows with the same row_id. Uniqueness is carried by the primary key, which has no duplicates.
- **prereg_bytes_untouched**（statement）：this build reads the locked prereg and never writes it; the schema was not back-filled and no frozen artefact was modified.

## 边界（不许省略）

- **受限 858 条**：Schrödinger 增补中 4,440 − 3,582 = 858 条受限值**未获取、未推断、未重建**；3,582 行开放子集就是本项目可用的全部。
- **`supp_3`（650 行，`data_status=predicted`）未进入**：预测值不是观测，本构建器不打开该文件。
- **Reaxys 值未进入**：`restricted_crosscheck_only`，只用于裁定冲突，不得进入可分发的数据集。
- **`filter_only` 永不进可发表口径**：上文的 `publishable_core` 读数不含任何 PubChem 行；本表含 163 行 `filter_only`，任何在含这些行的表上引用可发表口径的写法都是缺陷。
- **列表**：`data/external/g1plus/pubchem/liquid_window/` 中 58 个 404 记录（无实验属性节）不产生任何取值行，因此没有可排除的行，只在汇总里计数。
- **MP/BP/FP/密度**：读法与锁定 schema 的冲突见上一节；它们以 `property_not_in_joint_enum` 出现在排除表里，而不是被静默丢弃。

## 校验

`probes/verify_eta_epsilon_joint_table.py` 独立复算预注册 `verification_contract.checks` 的全 7 条，并对观测表、排除表与构建器脚本做 SHA256 清单：

1. 每个必填列都在、且按其规则非空；
2. 每一行的 `unit` 与 `property` 一致；
3. `pure_or_mixture` 与 `n_components` 一致（1 ⇔ pure）；
4. `quality_layer=publishable_core` ⇒ `source_kind` 是一次测量且 `source_doi` 非空；
5. `redistributable=false` 的行按来源在清单里枚举；
6. 主键无重复；
7. 每个被排除的源行都有排除记录（源行全集 = 进表 ∪ 排除）。

校验器对给定文件报 PASS/FAIL 并返回退出码（PASS=0，FAIL=1）。
