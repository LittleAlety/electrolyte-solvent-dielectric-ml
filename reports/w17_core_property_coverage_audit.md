# W17 交付包核心性质覆盖审计：ε / η / HOMO-LUMO / 氧化还原

**一句话**：四类核心数据在 W17 包里**都能查到**，但**深浅不一**——ε 与 η 有独立主表落盘，
HOMO/LUMO 与氧化还原则主要靠 `data/processed/four_core_key_registry.csv` 的**单值列**承载；
其中**氧化还原没有任何独立交付表**，且四类里有三类的**读数源文件没有随包发出**（只在仓库里），
另有一处 `artifacts_commit` 与包内产物**不一致**的 provenance 断链。

- 审计对象：`probes/export_week17_results.py` 的 `ARTIFACTS`（436 条字符串字面量、其中 **40 条** `data/` 条目），
  以及落盘交付包 `E:\Claude Code\电解质ML\成果输出\week17`（README/SHA256SUMS 时间戳 2026-09-27 17:56）。
- 方法：**只读**。解析 `ARTIFACTS` 定义、比对落盘目录逐文件、复算行数/键数并回读源表列名。
  **不拟合模型、不产任何 R²、不跑 pytest、不改动任何既有文件。**
- 口径铁律：`457` 是行数、**`276`** 才是样本量（97 化合物、50 折、GroupKFold by InChIKey）；两者永不混用。
  Reaxys 在本仓一律 **0 条数值**，不进任何池、不进本包。

## 1. 四类性质覆盖矩阵

| 性质 | 在 W17 包内 | 包内承载文件 | 规模（键/行） | 数据源 | 模型门 | 缺口 |
|---|---|---|---|---|---|---|
| **ε 介电常数** | **是（独立主表）** | `data/dielectric_v04.csv`；`four_channel_coverage.csv`；registry `dielectric` 列 | 名册 **248 行 / 247 键**；记分牌 457 行 / 97 化合物 / **276** 对 | 冻结 v0.3（246 键）+ W17-1 名册补丁 + 22 源 96 行 | 头条 `0.4766400383507876`、基线 `0.4091179943351143`；适用域触发 33.66% | 名册只有 247 键；天花板是**信息缺口**（缺 Kirkwood g）非行数 |
| **η 黏度** | **是（独立主表）** | `data/viscosity_v02.csv` | **42,941 行 / 1,228 键 / 28 列** | NIST/TRC ThermoML 检索 API + XML NumValues + 密度反解 86 行 | `group_key` R² `0.7481271437772365`、MAE `0.17477197208762` log10(cP) → **红（族级）** | 数值层 `viscosity_v02_raw.csv`（**268,247 行 / 1,547 键**）未随包；行级模型未过门 |
| **HOMO / LUMO** | **是（单值列 + 三源图层）** | registry `HOMO_eV`/`LUMO_eV`/`gap_eV`/`IP_eV`/`EA_eV`/`dipole_au`；`themol_orbital_layer_expanded.csv`；`themol_orbital_layer.csv`；`orbital_second_source_layer.csv` | HOMO/LUMO 各 **29,519**；IP/EA 各 **29,868**；图层 5,117 / 166 / 912 行 | Batt-P30K 主源；PubChemQC 第二源（CC BY 4.0）；THEMol/GFN2-xTB 第三源 | HOMO MAE `0.19050925839013938` ✅、LUMO `0.13855083976437643` ✅、IP `0.2010970559642009` ❌、EA `0.23415453202842548` ❌（门 0.2 eV） | 主源合并表 `redox_merged.csv`（29,911 行 / 15 列）未随包；读数源 `models/homo_lumo_baselines.json` 未随包 |
| **氧化还原电位/自由能** | **是（仅单值列）** | registry `oxidation_free_energy_eV` / `reduction_free_energy_eV`；`four_channel_coverage.csv` 读数行 | **392 键**（RX-392） | Batt-SLM RX-392（DOI `10.1021/acsnano.6c06255`），4.44 V vs H⁺/H 换算为自由能 eV | 氧化 MAE `0.2905180517963865`、还原 `0.4096241620366996` eV → **红** | **无独立交付表**；口径是**自由能 eV**不是电极电位 V；标签只 392 条（瓶颈）；读数源 `p4_redox_summary.json` / `p4_redox_v2_summary.json` 未随包 |

## 2. 逐类明细

### 2.1 ε 介电常数

- **交付形态**：独立主表 `data/dielectric_v04.csv`（248 行 / 247 键）随包发出，另有 `data/processed/
  dielectric_v04_roster_additions.csv`、`dielectric_v04_provenance_patches.csv`、`data/raw/open_data_eps2/
  {observations.csv, reference_only.csv, coverage.json, report.md}` 作扩容侧证据。
- **规模**：名册 247 键（v0.3 的 246 + W17-1 补丁）；**记分牌 457 行 / 97 化合物 / 276 对**。
- **数据源**：冻结 `data/dielectric_v03.csv`（sha256 `ff214293…35ccce4`，未改动）+ W17 名册补丁 + 22 个开放源 96 行。
- **缺口**：名册仅 247 键，**不是千位级**；四通道板明写天花板是**信息缺口**（缺 Kirkwood g 维）而非行数缺口。
  本轮开放 ε 源已见底（净新增化合物 ≈ 0，上界 4 且同属已用 ThermoML）。

### 2.2 η 黏度

- **交付形态**：独立主表 `data/viscosity_v02.csv`（**42,941 行 / 1,228 键 / 28 列**）随包发出，行内带逐行 provenance 列
  （`value_origin`、`property_unit_raw`、`unit_conversion_factor`、`density_kg_m3_used`、`density_source_doi`、
  `thermoml_file`、`source_row_index` 等）。
- **规模**：主表 42,941 行 = Pa·s 直测 42,855 + 运动黏度反解 86；数值层 268,247 观测行 / 1,547 键。
- **数据源**：NIST/TRC ThermoML 检索 API（目录层 1,743 记录）+ 同源 XML NumValues 观测行 + `density_v01.csv` 反解运动黏度。
- **缺口**：数值层 `data/processed/viscosity_v02_raw.csv`（81 MB）被 `.gitignore` 忽略、**不在包内**（与 `density_raw.csv` 同级，
  属 tier-2 本机缓存）；模型只过 `random_row`、`group_key` R² 0.7481 / MAE 0.1748 **红**，只许族级结论。
  η 的**读数源 `probes/viscosity_baseline_summary.json` 未随包**，包内读数只能从 `four_channel_coverage.csv` 看到。

### 2.3 HOMO / LUMO 轨道能

- **交付形态（三源都在包内）**：
  - 主源 Batt-P30K：以 registry 单值列承载 —— `HOMO_eV` / `LUMO_eV` / `gap_eV` 各 **29,519**，`IP_eV` / `EA_eV` 各 **29,868**，`dipole_au` 29,519。
  - 第二源 PubChemQC（CC BY 4.0）：`data/processed/orbital_second_source_layer.csv`，**912 行 / 35 列**。
  - 第三源 THEMol/GFN2-xTB：`data/processed/themol_orbital_layer.csv`（166 行）与
    `data/processed/themol_orbital_layer_expanded.csv`（**5,117 行**，`run_status = complete`）。
- **数据源水平**：主源 wB97X-V/def2-TZVPPD/SMD(ε=18.5)，DOI `10.1021/acsnano.6c06255`；第二源 B3LYP/6-31G*//PM6（跨水平标定后只作增量列）；
  第三源 GFN2-xTB（几何可读、**能级不可与主源混用**，属负结果登记）。
- **模型门**：HOMO MAE 0.19050925839013938 ✅、LUMO 0.13855083976437643 ✅、IP 0.2010970559642009 ❌、EA 0.23415453202842548 ❌（门 0.2 eV，**2/4**）；
  特征只用结构描述符，DFT 派生列**禁止**当输入。
- **缺口**：**主源合并表 `data/processed/redox_merged.csv`（29,911 行 / 15 列）不在 W17 包内**（它只在 week3 包发出）；
  registry 只有**单值列**，不带 `source` / `method` / `source_doi` / `status` provenance 列，
  也**不含**逐分子的 ε=18.5 计算水平标注。同一张表上挂的氧化还原标签同样因此缺少溯源列。

### 2.4 氧化还原电位 / 自由能

- **交付形态（最薄）**：只有 registry 的两列 `oxidation_free_energy_eV` / `reduction_free_energy_eV`，**各 392 键**；
  `four_channel_coverage.csv` 里有对应的 MAE 读数行。**没有独立的氧化还原交付表。**
- **规模**：RX-392 = **392 行**（`data/external/Batt-SLM-RX-392.csv`，248,404 B，sha256 `d30ec1ff…24a5d87`）；
  `redox_merged.csv` 里 392 行带 redox 标签、29,519 行 Batt-P30K 行的这两列为空。
- **数据源与口径**：Batt-SLM RX-392，DOI `10.1021/acsnano.6c06255`；上游 `redox_free_ener.py` 只取 `DIELECTRIC=18` 条件，
  `oxidation_free_energy = oxidation_potential + 4.44`、`reduction_free_energy = -(reduction_potential + 4.44)`，
  **4.44 V vs H⁺/H 按 4.44 eV 计入电子自由能约定** ⇒ 交付口径是**自由能 eV**，不是可对电极比较的电位 V。
- **模型门**：氧化 MAE 0.2905180517963865、还原 0.4096241620366996（门 0.15 eV）→ **红**；
  富特征留出 0.2174014393126818 / 0.33169277465193164，瓶颈是 **392 条标签**而非模型容量。
- **缺口**：①无独立表；②只有 392 条标签；③**Reaxys 实测 0 条数值**（红线：Reaxys 数值不入任何池/列/包），无法缓解标签瓶颈；
  ④读数源 `probes/p4_redox_summary.json`、`probes/p4_redox_v2_summary.json`、`data/processed/redox_merged.csv` **均未随包**。

## 3. 缺口清单

### 3.1 数据缺口（数据本身不够）

| # | 缺口 | 现状 | 可否低成本补 |
|---|---|---|---|
| D1 | 氧化还原标签只有 **392** 条 | 门红，瓶颈是标签不是模型 | **否**，需新标签预算；Reaxys 已实测 0 数值 |
| D2 | ε 名册只有 **247** 键 | 天花板是信息缺口（缺 Kirkwood g） | 否，开放源已见底 |
| D3 | η 跨分子（group_key）不过门 | R2 0.7481 / MAE 0.1748 | 部分：需行级模型 + 运动黏度全解冻 |
| D4 | IP / EA 差门 | 0.2011（差 1.1 meV）/ 0.2342（差 34 meV） | 维持粗筛口径 |
| D5 | 氧化还原是自由能 eV、非电极电位 V | 4.44 V vs H+/H 折进电子自由能 | 口径问题，非数据问题（见 4.4） |

### 3.2 交付断链（覆盖板引用了、但包内没有的源文件）

`data/processed/four_channel_coverage.csv` 每一行的 `source` 列指向一份读数源；逐条比对 `ARTIFACTS` 与落盘包，
下列文件**被引用但未随包发出**（在仓库里都在，只是没进包）：

| 被引用源 | 服务哪一类 | 影响 |
|---|---|---|
| `models/homo_lumo_baselines.json` | **HOMO/LUMO** | 包内 HOMO/LUMO 的 MAE 读数**无法就地复算** |
| `data/processed/redox_merged.csv` | **HOMO/LUMO + 氧化还原** | 主源合并表缺席：无逐分子 `method`/`DOI`/`status` 溯源 |
| `probes/p4_redox_summary.json` | **氧化还原** | 392 标签的氧化/还原 MAE 无源 |
| `probes/p4_redox_v2_summary.json` | **氧化还原** | 富特征留出 0.2174 / 0.3317 无源 |
| `probes/viscosity_baseline_summary.json` | **η** | 黏度 R2 0.7481 / MAE 0.1748 无源 |
| `probes/dielectric_coverage_paired_benchmark_summary.json` | **ε** | 冻结基线 `0.4091179943351143` 的源 |
| `probes/applicability_domain_summary.json` | **ε** | 适用域门触发率 33.66% 的源 |
| `probes/artifacts/dielectric_coverage_paired_benchmark_predictions.csv` | **ε** | 457 / 97 / 276 三个计数的源 |

**结论**：这些是**交付断链**，不是数据缺失 —— 文档里能读到数，但包内无法就地校验。
（对照：四通道板引用的 `density_v01_summary.json`、`dielectric_coordination_block_v3_summary.json`、
`liquid_window_gate_summary.json`、`walden_dn_channel_summary.json`、`reports/decisions_log.md` **都在包内**，属正例。）

### 3.3 provenance 断链：`artifacts_commit` 指向错误提交

- 落盘包 `week17_summary.json` 记录 `artifacts_commit = 9ff6c183c1031eab9edbdf5dfcfdbe9ee5176abb`（2026-09-27T16:53），
  但包内**已包含** W17-26 换折种子复验五件产物（`probes/dielectric_representation_seed_robustness.py`、
  `..._prereg.json`、`..._summary.json`、`..._repeats.csv`、`probes/artifacts/w17_representation_seed_robustness.png`）。
- 实测：`git ls-tree -r 9ff6c18` **不含**上述任何 `representation_seed_robustness` 路径；
  它们首次入库是在**后一个提交** `45a99c6`（2026-09-27T18:16）。
- 影响：按包内 README 的「从 `artifacts_commit` 取件」指引去取 W17-26 的件会**取不到**。
  （包是在提交之前出的：出包 17:56 < 提交 18:16，`head_commit` 因此被钉在了上一提交。）

## 4. 补强建议（可执行清单，只列动作与前置条件，本审计不执行）

### P0 —— 让四类性质在包内各自「可就地校验」

1. **氧化还原独立化**：在 `probes/export_week17_results.py` 的 `ARTIFACTS` 里补 2~3 条——
   `("data/processed/redox_merged.csv", "data/processed/redox_merged.csv")`、
   `("probes/p4_redox_summary.json", "p4_redox_summary.json")`，可选 `("data/external/Batt-SLM-RX-392.csv", ...)`。
   - 先例成立：week3 包已发出 `redox_merged.csv`，**不是新的分发许可问题**；且该表不含任何 Reaxys 数值（红线不受影响）。
   - 配套必改：README 增条 + 目录表加行 + **重钉 `README_SHA256`**（现钉值在 `tests/test_export_week17_results.py:70`，
     断言在 `:920`）与 `README_NARRATIVE_NUMBERS`（`:71`/`:928`）；`--overwrite` 重出后验证器须 exit 0；
     `tests/test_export_week17_results.py:834` 的 `shipped` 集合与 `RESTRICTED_EXCLUDED`（25 条）不得冲突。
2. **HOMO/LUMO 读数源入包**：`("models/homo_lumo_baselines.json", "homo_lumo_baselines.json")`。
   否则包内 HOMO/LUMO 的 4 个 MAE 只能引用 `four_channel_coverage.csv`，无法就地复算。
3. **η 读数源入包**：`("probes/viscosity_baseline_summary.json", "viscosity_baseline_summary.json")`。
   （`viscosity_v02_summary.json` **已在包内**，缺的是 v01 基线那份——R² 0.7481 / MAE 0.1748 的出处。）
4. **ε 读数源入包**：`probes/applicability_domain_summary.json`、`probes/dielectric_coverage_paired_benchmark_summary.json`、
   `probes/artifacts/dielectric_coverage_paired_benchmark_predictions.csv`（457 / 97 / 276 三计数的出处）。
   （`dielectric_coordination_block_v3_summary.json` 与 `density_v01_summary.json` **已在包内**。）

### P1 —— provenance 与可复算

5. **修 `artifacts_commit`**：把「出包」排在「提交」之后重跑一次 `--overwrite`，使 `head_commit`/`artifacts_commit`
   指向真正含 W17-26 的提交（现为 `9ff6c18`，缺该件；正确应为 `45a99c6` 或更晚）。
6. **补一张 provenance 表**：新增 `data/processed/four_core_provenance.csv`（每通道一行：`channel, source_table, method, source_doi, unit, status, gate`），
   而不是给 30 列的 `four_core_key_registry.csv` 加列——保持注册表「一键一行」的口径不变。
7. **η 数值层可复算**：把 268,247 行数值层裁成「**已入库 1,228 键的观测摘录**」入包（几 MB 量级），
   原始 81 MB `viscosity_v02_raw.csv` 继续 gitignore；这样 η 的关键词「记录数 / 观测行数 / 键数」三分口径在包内可核。

### 不建议做的事

- **不要把 Reaxys 数值加进来**（红线：Reaxys 0 数值，只作核对）；
- 不要为凑覆盖率把 `four_channel_coverage.csv` 的 `source` 改成包内已有文件——**断链本身是要暴露的事实，不是要掩盖的瑕疵**。

## 5. 边界与取证

- 本审计**只读**：未运行 pytest、未改动任何既有文件、未拟合任何模型、未产生新的 R² 或 MAE；
  新建文件只有本报告 `reports/w17_core_property_coverage_audit.md`。
- 行数/键数分离口径：**行 ≠ 键**（如 η 42,941 行 / 1,228 键）；**457 是行数、276 才是样本量**。
  本报告所有计数均按源表原地复算，未做跨表相除。
- `ε` 的头条 `0.4766400383507876` 与基线 `0.4091179943351143` 只作**引用**，两者永不混比；
  `0.7385332681453336` 是**泄漏参照**，从不进判决。本报告不引用任何主记分牌数字作结论。
- **Reaxys 数值一律未写入任何文件**；本报告提到 Reaxys 时只复述「0 条数值」这一既有结论。

### 取证清单（逐条已实测）

| 取证项 | 命令/依据 | 结果 |
|---|---|---|
| 包内 `data/` 条目 | 解析 `ARTIFACTS` 字面量 | 40 条 |
| ε 主表规模 | `data/dielectric_v04.csv` 复算 | 248 行 / 247 键 |
| η 主表 / 数值层 | `data/viscosity_v02.csv`、`data/processed/viscosity_v02_raw.csv` | 42,941 行 / 1,228 键；268,247 行 / 1,547 键 |
| HOMO/LUMO 三源 | registry 列 + 三个图层文件 | 29,519 / 29,868 / 912 / 5,117 / 166 |
| redox 标签 | registry 两列 + `redox_merged.csv` | 392 / 392 |
| 覆盖板断链 | `four_channel_coverage.csv` 的 `source` 列 × `ARTIFACTS` | 8 个被引用源不在包内 |
| provenance 断链 | `week17_summary.json.artifacts_commit` × `git ls-tree` | `9ff6c18` 不含 W17-26 产物 |

