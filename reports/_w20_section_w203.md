## 28.59 排序键 v1 + 交集填充：Batt-SLM 全域域外、交集填充为空前沿，键仍只含 HOMO/LUMO 两维（2026-09-28）
|
**机制假设**：筛选使命要的是**排序**而不是单目标 R²。W20-3 把 Week 19 D6 的排序键 v0 推进到 v1：加一层**通道扩维登记**（被别的 lane 的裁决件闸住）、一道**去重守门**（共线列不得重复计权）、一道**适用域闸门**（域外不给分），并用 Tier C 层（冻结特征 + 冻结模型预测）把 `data/external/Batt-SLM.smi` 的 **115,756** 候选填成多通道可评分候选清单。它是**排序键、不是候选生成器**：不产新分子、不产任何新性质预测值；分数是**集合相对**的排序量、不是物性值。本件**不拟合任何模型**（填充只调用冻结特征块与冻结模型预测），不占 shot 编号、不产通道读数、不动主记分牌（本周 0 次、累计 11 次不变）、不引用任何 Reaxys 数值。
**预注册**：`probes/w20_ranking_key_v1_prereg.json`（`prereg_status = locked_before_run`，锁于 2026-09-28T04:42:40.052Z）。锁定的对象是**键维度、方向、权重、去重组、域规则与扩展并入条件**；权重以字面量钉进模块 `PREREG_WEIGHTS`（import 时与派生键逐位比对，漂移即报错），示例排序与共线相关性以字面量钉进 `tests/test_w20_ranking_key_v1.py`。**权重或方向改动 = 预注册改动**，不许事后静默改数。
|
**读数一 · 三条锁定规则（charter §1 W20-3）逐条落地**
| 规则 | 内容 | 实现（可执行，违者抛错） | 测试 |
| --- | --- | --- | --- |
| ① 去重 | IP–HOMO `r = −0.9876`、EA–LUMO `r = −0.9513` 已在册，**不得重复计权** | `COLLINEARITY_RECORD` 登记两组；`validate_keys` 遇同组两列进键即 `ValueError`（`the same information may not be counted twice`） | `test_a_collinear_pair_may_not_be_counted_twice` |
| ② 适用域闸门 | 域外候选**不给分，不是给低分** | `assign_scores` 域外返回 `None`；`_front_flags` 令域外**永不进前沿**；min-max **只在域内集合内**归一；`dominates` 对域外行**拒绝回答** | `test_out_of_domain_rows_get_no_score_at_all`、`test_a_rejected_row_cannot_move_a_kept_score` |
| ③ 权重跑前声明 | 无成本比证据 ⇒ **等权** | `PREREG_WEIGHTS = {homo 0.5, lumo 0.5}`，`weights_source = no_cost_ratio_evidence`；`build_default_keys` 拒绝无钉列通道；`assert_no_unregistered_verdicts` 拒绝默默并入新裁决件 | `test_the_default_key_is_equal_weight_over_the_two_gated_channels` |
- **去重共线**：保留列 `(HOMO_eV, LUMO_eV)`、丢弃列 `(IP_eV, EA_eV)`；IP `0.2010970559642009` 与 EA `0.23415453202842548` 本身也未过 0.20 eV 门（只登记、不进键）。
- **域规则 D1**：`NumHDonors(SMILES) >= 1 and TPSA(SMILES) >= 20.0`（只读冻结 SMILES 特征，不读标签）；失效区阈值 `HIGH_PERMITTIVITY_EPS = 60.0`。
- **分数语义**：每通道在**域内行集内** min-max 归一到 [0,1]（1 = 最好；整列同值取 0.5），按权重线性求和 ⇒ 集合相对排序量，不得跨集合比较、不得当预测值引用。
|
**读数二 · 交集填充实测（本机跑，源 `data/external/Batt-SLM.smi` sha256 `c2ec78256ce6189366aebd9f7f0403e669c963e911cf51f7732083bce6374a1d`，1,879,361 B）**
| 量 | 实测 |
| --- | ---: |
| 文件候选 / 读入 | 115756 / 115756 |
| SMILES 可解析 / 无效 | 115756 / 0 |
| 唯一 InChIKey / 重复行 | 115756 / 0 |
| **域内 / 域外** | **0 / 115756**（share **1.0**） |
| 键维度可评分行 / 前沿 `front_size` | **0 / 0** |
| `top_20` | `[]` |
- **空前沿是一等结论，不是失败**：Batt-SLM 是电池溶剂空间，样本以无氢键给体、`TPSA < 20` 的小分子为主（首行 `CP(C)(=S)c1cccnc1`：`NumHDonors = 0`、`TPSA = 12.89` ⇒ 域外）。D1 下**全部 115,756 候选判域外** ⇒ 无候选得分、前沿为空。闸门**正在做它该做的事**：域外**不给分**（而非给一个会被误读的低分），可行集为空就**不排任何东西、不编造任何东西**。
- **键的当前站立面**：`key_dimensions = [HOMO_eV, LUMO_eV]`（2 维）、`core_channels_filled = [orbitals]`、`core_channels_not_filled = [dielectric, viscosity, liquid_window]`、`scoreable_on_core_channels = 1` ⇒ 四通道里**只填了轨道 1 条**，不得叙述成四通道综合排序。
- **池内对照**：`data/processed/four_core_key_registry.csv` 共 **31949** 行、**29519** 行含两个键维度、**7** 行含四条核心通道 ⇒ 四通道交集在池内本就极稀。
|
**读数三 · 每候选出口契约（域声明 + 可追溯出处 + 哪个通道给排序）**
- 候选 CSV 16 列（`CANDIDATE_COLUMNS`）：`inchikey, smiles, canonical_smiles, source_line, NumHDonors, TPSA, HOMO_eV, LUMO_eV, gap_eV, domain, ranking_channels, key_score, rank, on_front, excluded_reason, provenance`。
- **域声明** `domain ∈ {in_domain, out_of_domain}`；**通道** `ranking_channels = homo+lumo`；域外行 `key_score` / `rank` 留空、`on_front = false`、`excluded_reason = out_of_domain` ⇒ 下游无法把「域外」误读成「分很低」。
- **可追溯出处** `provenance`（样本）：`tier_c|features=rdkit_morgan_count_r2_2048+30_descriptors|prediction=HOMO=models/homo_lumo_homo.ubj@7e945fc5647f;LUMO=models/homo_lumo_lumo.ubj@9f6c2d6e6f86|domain=NumHDonors(SMILES) >= 1 and TPSA(SMILES) >= 20.0|ranking_channel=orbitals` ⇒ 每个候选可回溯到特征层 + 两个模型件（sha256 前 12 位）+ 域规则 + 排序通道。
|
**读数四 · 扩维登记（并入条件 = 预注册改动，被裁决件闸住）**
| 通道 | owner | 裁决件在盘 | `merged` | 并入条件 |
| --- | --- | --- | --- | --- |
| viscosity（η） | W20-1 | **是**（重跑时在盘） | **false**（并入条件已成立，仍卡自己的门） | W20-1 公平性复检在盘且过（`delta <= -0.02` 且两臂过门状态不变） |
| safety | W20-2（Step 2） | **是** | **true** | W20-2 Step-2 建模裁决在盘且过自己的门 |
- **safety 已满足并入条件（`merged = true`，非「进了键」）**：`probes/w20_safety_model_summary.json`（§28.58，shot 22）判 `modelable_all`、`blocking_conditions = []`；但 safety **无门读数、无钉键列** ⇒ `_eligible_channels` 仍把它挡在键外，**键维度不变**；按 §28.58 分域声明 safety **只进 ε 侧、不进 η 侧**。
- **η 已到裁决、键仍未加宽（重跑后的实际状态）**：`probes/w20_eta_fairness_summary.json` 已在盘，W20-1 判 `eta_crosses_gate_out_of_fold`（行级 Δ = `-0.05419789751156204`，两臂门状态不变）⇒ **并入条件成立**；但 η 仍卡在**自己的门**：本模块 η 读数取**族级** `0.17477197208762`（未过 0.15），且 `KEY_CHANNEL_SPECS` 未钉 η 列与方向 ⇒ 键**未加宽**。`extension_status.viscosity` 现记 `verdict_present = true`、`verdict = eta_crosses_gate_out_of_fold`、`merged = false`。
- **两级闸门**：进键须同时满足 ① 通道自己的门读数过门 ② 扩展并入条件成立；η 与 safety 都卡在 ① ⇒ 四通道里当前只有轨道 1 条在键内。
- **口径澄清（η；预判已应验）**：本件跑前即写明「即便 W20-1 日后给出有利裁决，η 也不会自动进键」。重跑证实：授权到了、键未动。让 η 进键须**另立预注册**钉其键列与方向，并**改本模块的 η 门读数口径**（族级 `0.17477197208762` → 行级 `0.1054414994165841`）——两者都属改冻结件级动作，超出本版范围。
|
**判定与边界**
- `verdict`：**v1 成立且范围受限** —— 键仍只含 HOMO / LUMO 两维、等权；域闸门与去重守门均在位；四通道交集填充在 Batt-SLM 上**结果为空**（如实报空）。
- **空前沿 ≠ 失败**：把 11.5 万域外行强行排序才是本键要避免的错误；域外**无分**是机制在正确工作。
- **不占主记分牌**：本件不产读数、不占 shot 编号；冻结基线 `0.4091179943351143` 与冻结头条 `0.4766400383507876` 未动。
- **预测用于排序、永不入池当标签**：Tier C 输出只写进候选 CSV 的排序列，不写进任何 pool / 特征 / 交付包。
- **生成闭环永久钉死（三条证据，承 §28.50）**：① ElectrolyteGPT 在 10 性质下 uniqueness 塌到 **0.349**；② 其 10 个性质全为代理输出、`never subjected to a group-split audit`；③ 其许可 `CC-BY-NC-ND` 4.0 不得改作。**本项目不做生成闭环、不做候选生成器。**
- **未来扩通道的唯一路径**：先把该通道推过自己的门，再改本件并重钉预注册；**先加通道再加门是禁止的**。
|
**产物清单**
- `reports/w20_ranking_key_v1_spec.md`（本机 stat 12,355 B；sha256 `b0cfc117b844bce8a777e3c47a636e738a65ec8892bd60c5c08be925399de245`）
- `probes/w20_ranking_key_v1.py`（45,516 B；sha256 `cc19e4e92e7cf787469b6ed0e8b8dacc7d01af2b642b81a7d7713e6723f25bfe`）
- `probes/w20_ranking_key_v1_prereg.json`（4,517 B；sha256 `b19163b8da642f5df646a3a846d506b1d2f4c08e082d945111dc3da2ff056958`）
- `probes/w20_ranking_key_v1_summary.json`（本机 stat 4,517B 级；sha256 见下回填）
- `probes/artifacts/w20_ranking_key_v1_candidates.csv`（45,093,401 B；sha256 `b52f720bfa904a1c71e730e0d8fb2bb7ec7d4041ce9aae7ce7b1835c518ae6c5`）
- `tests/test_w20_ranking_key_v1.py`（13,007 B；sha256 `49d5c18e2bfdf043d081c3859a6a525847e166723afd464358dc2a55ebd7713c`）
|
**数字出处**
- 三条锁定规则与扩维条件 ← `reports/week20_project_charter.md` §1 `W20-3`；本件 §1–§4 与 `probes/w20_ranking_key_v1_prereg.json`
- `−0.9876` / `−0.9513` ← `reports/homo_lumo_baselines.md` 标签空间诊断；实现 `probes/w20_ranking_key_v1.py::COLLINEARITY_RECORD`（W19 D6 亦在册）
- `0.5 / 0.5`、`no_cost_ratio_evidence` ← `probes/w20_ranking_key_v1.py::PREREG_WEIGHTS` / `PREREG_WEIGHTS_SOURCE`
- 115756 / 0 / 115756 / 1.0 / 31949 / 29519 / 7 ← `probes/w20_ranking_key_v1_summary.json::fill` / `::registry_reference`
- `0.8285714285714287` / `0.34285714285714286` / `0.8057142857142858` / `0.3885714285714286` ← `tests/test_w20_ranking_key_v1.py::EXAMPLE_SCORES` / `HEAVY_HOMO_SCORES`（与模块示例输出一致）
- `0.45401075998423623` / `0.524012313223719` / `0.3198024498133034` ← `probes/dielectric_applicability_domain_summary.json`（§28.45 分域第二记分牌）
- `0.17477197208762` / `0.15` ← `probes/viscosity_baseline_summary.json#primary_gate`；`0.4091179943351143` / `0.4766400383507876` ← W18 冻结基线 / 头条
- `0.349` / `never subjected to a group-split audit` / `CC-BY-NC-ND` ← W19 D6 §2 生成闭环三证据（§28.50）
**数字自检**：片段内数值 token 已对 `reports/w20_ranking_key_v1_spec.md` + `probes/w20_ranking_key_v1.py` + `tests/test_w20_ranking_key_v1.py` + `probes/w20_ranking_key_v1_summary.json` 逐字回搜（ISO 日期整段排除、digest 不作数值 token）。**推算值 / 运行值 / 外部常量**：`28.59`（节号，任务书指定）；`0.4091179943351143`（W18 冻结基线常量）；`12,355` / `13,007` / `45,516` / `4,517` / `45,093,401`（各交付件**本机 stat 实测字节数**）；`11`（累计主记分牌尝试，W18 冻结记账）。其余数值 token 在本 lane 素材内逐字命中。
|