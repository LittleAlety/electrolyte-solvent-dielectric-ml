# W20-7 三层标签规范 + 每格 provenance sidecar（§28.63）

**性质**：无依赖｜成本极低。本件**不拟合任何模型、不产任何 R² / MAE、不占主记分牌、不改写任何冻结件、不引用任何 Reaxys 数值**。

**产物**：`probes/w20_label_provenance.py`、`probes/w20_label_provenance_prereg.json`、`probes/w20_label_provenance_summary.json`、新增 sidecar：**声明交付件** `probes/artifacts/w20_label_provenance_sidecar.csv`，以及与其逐字节一致的工作副本 `data/processed/four_core_label_provenance_sidecar.csv`（即 `probes/w20_label_provenance_summary.json::sidecar` 所指路径）、`tests/test_w20_label_provenance.py`、本报告。

---

## 1 一句话结论

- 把「一个通道的标签必须同源同水平」写成**可执行的 sidecar**：11 行 → 覆盖注册表 6 个通道、**34,131** 个有值格。
- 本步**只统一散落的 role 列**（8 个冻结表里 **75** 个 provenance 列 → 1 张 **9** 列 sidecar），**不造新科学**：每个值都从既有表读出，词汇表 `calibrated_estimate` / `reference_only` / `linear_2fold_v1` 本就在册。
- 纠正一处常见误解：**DFT 在本仓就是标签**。被禁的不是计算值，是 ① ML/QSAR 预测值 ② 不同水平不加标注并成一列 ③ 受限值。

## 2 规范句（逐字入册）

> 一个通道的标签必须**同源同水平**；引入另一理论水平的值时必须先做跨水平标定并登记 `calibration_id`；**标定不过门则该列整列留空、只作 `reference_only`**；**ML 预测值永不入池**；**受限许可值永不入池**。

该句以字面量钉在 `probes/w20_label_provenance.py::LABEL_RULE_SENTENCE` 与预注册 `probes/w20_label_provenance_prereg.json::label_rule_sentence`；`tests/test_w20_label_provenance.py` 断言它与 `reports/week20_project_charter.md` 中的原文**逐字一致**（改一个标点即红）。

## 3 纠正一处常见误解：DFT 在本仓就是标签

| 轨道通道来源 | 理论水平 | 在本仓的地位 |
| --- | --- | --- |
| 主源 Batt-P30K | `wB97X-V/def2-TZVPPD/SMD(epsilon=18.5)` | **标签**（`role = primary_reference`） |
| 第二源 PubChemQC | `B3LYP/6-31G*//PM6` | 跨水平标定后才可并入（`calibration_id = linear_2fold_v1`） |
| 第三源 THEMol（本仓自跑） | `GFN2-xTB` 单点（DFT 几何上） | 登记后作 `calibrated_estimate` / `reference_only`；许可为 CC BY-NC 4.0 |

**被禁的不是计算值**，是三件事：① **ML/QSAR 预测值**（`predicted_not_experimental`，循环论证）；② **不同水平不加标注并成一列**；③ **受限许可值**。

## 4 sidecar provenance（新增件）

`data/processed/four_core_label_provenance_sidecar.csv`，一行一个 `(channel, source_layer, role, calibration_id)` 组合：

| channel | source_layer | role | reference_level | calibration_id | n_rows | access_class |
| --- | --- | --- | --- | --- | ---: | --- |
| orbitals | batt_p30k_primary | primary_reference | `wB97X-V/def2-TZVPPD/SMD(epsilon=18.5)` | （空） | 29,519 | open |
| orbitals | pubchemqc_second_source | calibrated_estimate | `B3LYP/6-31G*//PM6` | `linear_2fold_v1` | 801 | attribution_required |
| orbitals | pubchemqc_second_source | reference_only | `B3LYP/6-31G*//PM6` | （空） | 111 | attribution_required |
| orbitals | themol_gfn2 | reference_only | GFN2-xTB 单点 | （空） | 166 | noncommercial |
| orbitals | themol_gfn2_expanded | calibrated_estimate | GFN2-xTB 单点 | `themol_gfn2_to_batt_2fold_v2_registry_wide` | 449 | noncommercial |
| orbitals | themol_gfn2_expanded | reference_only | GFN2-xTB 单点 | `themol_gfn2_to_batt_2fold_v2_registry_wide` | 4,668 | noncommercial |
| redox_label | rx392 | primary_reference | `wB97X-V/.../SMD(epsilon=18.5)` + `redox_free_ener.py` | （空） | 392 | open |
| dielectric | dielectric_v04 | primary_reference | experimental | （空） | 248 | unknown |
| viscosity | viscosity_v02 | primary_reference | experimental | （空） | 42,941 | open |
| density | density_v01 | primary_reference | experimental | （空） | 182,154 | open |
| liquid_window | liquid_window_features | reference_only | PubChem depositor compilation | （空） | 314 | open |

- **role 词汇表封闭**（`primary_reference` / `calibrated_estimate` / `reference_only` / `feature_only`）：既有拼写 `paired_anchor`、`uncalibrated_reference` 走**显式别名映射**，未登记拼写**直接报错**，静默通过被禁止。
- **role 统计**：`primary_reference` 255,254 行 / `calibrated_estimate` 1,250 行 / `reference_only` 5,259 行 / `feature_only` **0** 行（词汇在册、当前无行——照实登记）。
- **`access_class` 词汇**：`open` / `attribution_required` / `noncommercial` / `unknown`。THEMol（CC BY-NC 4.0，衍生值非商用）标 `noncommercial` ⇒ 依规范句**永不入池**；PubChemQC（CC BY 4.0）标 `attribution_required`。
- sidecar 的 7 个字段与立项章 W20-7 逐字对应，另加 `source_layer`（行键）与 `n_rows`（覆盖数）。

## 5 统一前后对照（列数 / 覆盖数）

**统一前**：provenance / role 信息**散落**在 8 个冻结表的列里，共 **75** 列：

| 冻结表 | provenance 列数 | 代表列 |
| --- | ---: | --- |
| `data/dielectric_v04.csv` | 18 | `source_doi`, `source_dois_all`, `source_license`, `evidence_level`, `redistribution_status`, ... |
| `data/processed/liquid_window_features.csv` | 26 | `*_depositor`, `*_reference_number`, `*_selection_rule`, `quality_layer`, ... |
| `data/viscosity_v02.csv` | 8 | `value_origin`, `source_priority`, `thermoml_file`, ... |
| `data/processed/orbital_second_source_layer.csv` | 6 | `source_level`, `source_license`, `calibration_id`, `role` |
| `data/processed/themol_orbital_layer.csv` | 5 | `source_level`, `source_license`, `calibration_id`, `role` |
| `data/processed/themol_orbital_layer_expanded.csv` | 5 | 同上 |
| `data/processed/redox_merged.csv` | 4 | `source`, `source_doi`, `method`, `status` |
| `data/density_v01.csv` | 3 | `source_doi`, `thermoml_file`, `source_row_index` |
| **合计** | **75** | 8 个文件 |

**统一后**：1 张 sidecar、**9** 列、**11** 行，role 走封闭词汇表。

**覆盖数**（注册表有值格，本件实测）：

| channel | 注册表有值格 | 对应图层行数 |
| --- | ---: | ---: |
| orbital（HOMO/LUMO/IP/EA/偶极） | 29,868 | 35,714 |
| density | 2,178 | 182,154 |
| viscosity | 1,228 | 42,941 |
| redox_label | 392 | 392 |
| dielectric | 247 | 248 |
| liquid_window | 218 | 314 |
| **合计** | **34,131** | 261,763 |

- **两个口径不得混说**：注册表列是**按 InChIKey 去重**的键数（如黏度 42,941 行 → 1,228 键），图层列是**观测行数**。
- **sidecar 覆盖 100% 的注册表有值格**：每格按其 `channel` 唯一落到 sidecar 的一行（`probes/w20_label_provenance_summary.json::registry_coverage_total = 34131`）。

## 6 边界与不可核（照实登记）

- **`feature_only` 当前 0 行**：词汇在册但无行；本件不为了填表而把任何值标成 `feature_only`。
- **dielectric 的 `access_class = unknown`**：`data/dielectric_v04.csv` 的 `source_license` 有 **227/248** 行为空（另 9 行 CC BY 4.0、6 行 CC BY-NC 4.0、5 行 CC BY 3.0、1 行 CC BY-NC-ND 4.0，`redistribution_status` 34 行 `allowed`、4 行 `public_domain`）⇒ 取众数类别 `unknown`，逐行明细**留在冻结表本身**，本件不代填。
- **`source_doi` / `locator_table_figure` 在物理/密度/液窗三行是「per-row」指针**，不是单一 DOI：逐行 DOI 与定位在 `dielectric_v04.source_dois_all` / `source_table` / `source_page`、`viscosity_v02.source_doi` / `thermoml_file`、`density_v01.source_doi` / `thermoml_file` 内。本件**不复制**这些逐行值，避免把「通道级 sidecar」误读成「逐行 DOI 断言」。
- **图层行数 > 注册表键数**（如 261,763 vs 34,131）不是矛盾，是去重口径差，见第 5 节。
- **本件不改注册表本身**：注册表（31,949 × 30）是既有件，sidecar 是**新增**的并列件；不改写既有冻结件。

## 7 数字出处

- 规范句 / 三条理论水平 / 三种被禁 ⇒ `reports/week20_project_charter.md` §W20-7（逐字）
- sidecar 11 行与 role/access 统计 ⇒ `probes/w20_label_provenance_summary.json`（对 9 个冻结输入重算）
- 注册表有值格 247 / 1,228 / 29,868 / 392 / 2,178 / 218 / 34,131 ⇒ `data/processed/four_core_key_registry.csv`（sha256 `e42885eb43779b7a4d472da88fefe018fe94150ff5b6fba86b3ed9bc83dc8bee`）
- 75 列 / 8 文件 ⇒ `probes/w20_label_provenance_summary.json::scattered_provenance`
- `linear_2fold_v1` / `paired_anchor` / `uncalibrated_reference` / `calibrated_estimate` ⇒ `data/processed/orbital_second_source_layer.csv`、`data/processed/themol_orbital_layer*.csv` 的 `role` / `calibration_id` 列
