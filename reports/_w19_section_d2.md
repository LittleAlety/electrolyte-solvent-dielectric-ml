## 28.47 Week 19 D2 Batt-P30K 直接命中核查：名册实为 246 行、逐字命中 77/246、规范化 78/246（2026-09-28）
|
**机制假设**：W19-1 剩一个开口 —— 我们的冻结 ε 名册到底有多少化合物**直接落在** MIT 许可的 Batt-P30K（29,519 分子、ωB97X-V/def2-TZVPPD/SMD(ε=18.5)）里。这个数决定 Batt-P30K 能不能当 HOMO/LUMO 的迁移源。D2 只做**只读身份核对**：不拟合任何模型（`models_fitted = 0`）、不产 R2 / MAE、不动任何冻结件、不引用任何 Reaxys 数值。
**预注册**：本件无独立预注册 JSON —— 它是既有资产的身份核对，`read_only = true`、`writes_any_pool = false`、`reaxys_values_used = false`。冻结读数以字面量钉在 `tests/test_w19_batt_direct_hit.py`（sha256 `f2a710d7c7529c832cde712b0690a516805c2bbc17c03841bd30168c1ff6d558`）；探针内亦钉死输入身份 `EXPECTED_BATT_SHA256 = 587f1490613a008b91f45ee9de607a2e057c88c301fa9e5c9d7785b1968d118d` 与名册 digest `ff2142936e06e04b329b70f8597574f75349e54ce876e9fff81309e6d35ccce4`。命中阶梯（rungs）与规范化配方在探针里先声明、再执行。
|
**读数一 · 直接命中（分母 = 冻结 ε 名册 `data/dielectric_v03.csv` 实测 246 行 / 246 个唯一 InChIKey）**
| 读数 | 命中 | 分母 | 比率 |
| --- | --- | --- | --- |
| 逐字 SMILES 相等 | 77 | 246 | 0.3130081300813008 |
| RDKit 规范化（主读数 = InChIKey 全 27 位） | 78 | 246 | 0.3170731707317073 |
| 最宽阶梯（去盐去电荷后取骨架前 14 位） | 78 | 246 | 0.3170731707317073 |
- 主读数用的是与 §28.17 Batt 键**同一配方**（裸 RDKit `MolFromSmiles` → `MolToInchiKey`，取全 27 位），因此与既有 registry / 锚点可直接对齐。
- 阶梯累计命中：`verbatim_raw_smiles` 77 → `rdkit_canonical_smiles_isomeric_true` 78 → `inchikey_full_27_bare_rdkit` 78 → `inchikey_skeleton_14_bare_rdkit` 78 → `inchikey_full_27_desalted_uncharged` 78 → `inchikey_skeleton_14_desalted_uncharged` 78 ⇒ **规范化只买到 1 个化合物**（`HCBRSIIGBBDDCD-UHFFFAOYSA-N`，首现于 `rdkit_canonical_smiles_isomeric_true`），更宽的档位再加不了任何分子。
- 计数自洽：77 + 1 + 168 = 246（168 为规范化后仍未命中数）。
|
**读数二 · 分母口径发现（计划书写 239 / 76，磁盘实测 246 / 77）**
- 磁盘 `data/dielectric_v03.csv` 实测 **246** 行、246 个唯一 InChIKey；逐字命中 **77**、规范化命中 **78** ⇒ 计划书的「239 行 / 76 命中」两个数**都对不上**。这是**分母口径分歧**，不是数据变化（该文件是冻结件，本件未改一个字节，digest 仍为 `ff214293…35ccce4`）。
- 换成计划所用的 239 行口径（`probes/artifacts/v03_features_baseline_input.csv`）重跑：逐字 **70**、规范化 **71** ⇒ 两个口径都复现不出 76。
|
**读数三 · 与 §28.17 n = 111 配对锚点的包含关系**
- 锚点定义：`data/processed/orbital_second_source_layer.csv` 中 `role == paired_anchor` 且 `batt_homo_eV` 非空的行；本机直接从该层重算得 **111** 个（与冻结摘要一致）。
- 锚点落在 Batt 键全集里：**111 / 111**（子集判定 `true`）⇒ 两条链的身份**配方一致**。
- 锚点落在冻结 ε 名册里：**75**（逐字 / 规范化 / 骨架三个口径都是 75）；**111 是否为本轮命中集的子集 = `false`**。
- 真正可报的三个交并量：名册命中集共 **78** 个键，其中 **3** 个不在锚点集内；111 锚点里有 **36** 个根本不在这份 ε 名册里（75 + 36 = 111）。
- **宇宙不同、不得直接说谁包含谁**：锚点分母是「PubChemQC 抓取窗口内恰好也落在 `four_core_key_registry` 轨道键上的分子」（全 Batt 池 29,519 键 + 名册外分子），本轮命中集分母是冻结 ε 名册的 246 行。
- **一处必须登记的自我纠错**：`anchor_containment` 里两格曾拿 27 位 InChIKey 去比 14 位骨架集、拿名册命中集去减锚点集，得 `0` 与 `-33`；已按同宇宙重修 —— `anchors_skeleton_in_max_rung_key_set = 111`、`roster_hit_keys_not_in_anchors = 3`，且旧的 `anchors_in_max_rung_key_set` 键已删除。
|
**读数四 · 与 `four_core_key_registry` 的配方交叉核对**
- registry 的 `has_orbitals` 键数 **29868**，其中能在 Batt 里找到 **29519**；本轮 Batt 键集全在 registry 轨道键里（`batt_keys_subset_of_registry_orbit = true`）。
- Batt h5 身份：`groups_scanned = 29519`、`groups_without_smiles = 0`、`partial_scan = false`、sha256 与登记值 `sha256_matches_registered = true`。
|
**判定与边界**
- `verdict`：**命中确认** —— 逐字 77/246、规范化 78/246；规范化只多 1 个化合物；111 锚点全部落在 Batt 键全集里（配方一致性成立），但只有 75 个落在 ε 名册里。
- **命中 ≠ 拿到 Batt 级 HOMO/LUMO 估计**，更不等于过 §28.17 的 cross-level 标定门；前 14 位骨架读数只作敏感性上界（会抹掉质子化 / 立体差异），**不得当主读数引用**。
- **不静默改用 239**：本件按磁盘实测 246 报数，差异登记在案。
- **shot 编号留作者裁定**：`shot_accounting_judgement.author_decision_required = true`、`does_not_self_assign_shot_number = true` —— 本件零拟合、只读三件已冻结资产，建议按「复核不占号」处理；若要按「新信息产出」计号则由作者在预注册层拍板。
- `promoted = false`；主记分牌尝试 **0** 次、累计 **11** 次不变；冻结基线 `0.4091179943351143` 与冻结头条 `0.4766400383507876` 未动。
|
**产物清单**
- `probes/w19_batt_direct_hit.py`（sha256 `de221cb253ca7ba97843b2b8f22c317f7ba5f62f1a6774236321642addb85dd2`）
- `probes/w19_batt_direct_hit_summary.json`（41,768 B；sha256 `46892d764461e0cdac474f9f4c3f81f11da5455fcac569b9bbe8cb478c2ad97e`）
- `reports/w19_batt_direct_hit.md`（3,278 B；sha256 `e958e9a51e6f48b1e7f5c6082c57686a7702f9c17d40e773bdf2d654921f8ab5`）
- `tests/test_w19_batt_direct_hit.py`（7,857 B；sha256 `f2a710d7c7529c832cde712b0690a516805c2bbc17c03841bd30168c1ff6d558`）
|
**数字出处**
- 246 / 77 / 78 / 0.3130081300813008 / 0.3170731707317073 ← `probes/w19_batt_direct_hit_summary.json::roster_rows` / `verbatim_hits` / `normalized_hits` / `verbatim_ratio` / `hit_ratio`
- 阶梯 6 档与累计命中 ← `probes/w19_batt_direct_hit_summary.json::ladder.rung_cumulative_hits`
- `HCBRSIIGBBDDCD-UHFFFAOYSA-N` / 168 ← `probes/w19_batt_direct_hit_summary.json::lost_by_verbatim` / `misses_still`
- 239 / 70 / 71 ← `probes/w19_batt_direct_hit_summary.json::alternate_roster`
- 111 / 75 / 3 / 36 ← `probes/w19_batt_direct_hit_summary.json::anchor_containment`
- 29868 / 29519 ← `probes/w19_batt_direct_hit_summary.json::registry_crosscheck`
- `read_only` / `models_fitted` / `reaxys_values_used` / `writes_any_pool` / `shot_accounting_judgement` ← 同名 JSON 键
**数字自检**：片段内数值 token 已对 `reports/w19_batt_direct_hit.md` + `probes/w19_batt_direct_hit_summary.json` + `tests/test_w19_batt_direct_hit.py` 逐字回搜（ISO 日期整段排除、digest 不作数值 token）。**推算值 / 运行值 / 外部常量**：`28.47`（节号，任务书指定）；`18.5`（Batt-P30K 计算级别里的 SMD 介电常数，出自 D1 / E2 的级别串，非本 lane 素材）；`0.4091179943351143` / `0.4766400383507876`（W18 冻结常量）；`41,768` / `3,278` / `7,857`（三个交付件的**本机 stat 实测字节数**）；`11`（累计主记分牌尝试，W18 冻结记账）；`-33` 与 `27 / 14`（自我纠错段引的是修复前的两格旧值与键宽，`-33` 见 `tests/test_w19_batt_direct_hit.py::test_the_repaired_fields_stay_in_one_universe` 注释原文）。其余全部数值 token 在本 lane 素材内逐字命中。
|
