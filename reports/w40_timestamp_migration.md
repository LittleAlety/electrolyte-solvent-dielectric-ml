# W40-B：带时间戳跟踪件的写入器迁移到稳定写入（卫生件，不占 shot）

README §11 第 22 条（第 19 条的收口）。W38-E 只把**已观测到会脏树的那一条链路**
（`probes/w37_gate_admission_export.py`）接到 `probes/export_results_common.write_json_stable`，
并在报告里写明「机制已修、迁移未完成」。本件把被跟踪且带 `generated_at_utc` 的 JSON 的写入器迁移，
并对**不能迁移**的站点逐条登记理由（第 2.1 节）。

**口径更正（必须并读）**：第一版执行时把「全量」当成「全部站点」，结果扫出三类不该动的写入器：
(a) 字节被**冻结摘要 / 锁前预注册**钉死（迁移即让已交付摘要与盘上脚本不再一致），
(b) 写入站点是**追加写**（稳定写入是整篇改写，会丢 JSONL 历史行），
(c) 原写入器带 **`allow_nan=False`** 的严格 JSON 语义。这三类已全部回退并登记为例外。

## 1. 迁移动作

每个写入站点改成稳定写入，语义是「同一内容不重记时间」，不是「永不写」：

- `X.write_text(json.dumps(payload, ...) + "\n", encoding="utf-8", newline="\n")`
  → `write_json_stable(X, payload)`
- `with X.open("w", ...) as handle: json.dump(payload, handle, ...)`
  → `write_json_stable(X, payload)`
- 本地 `def write_json_lf(path, payload)` / `def write_json` / `def dump_json` 的函数体
  → 转调 `write_json_stable`
- 写入目标在运行时拼名的站点（`with_name(...)`）单独登记，见第 4 节

被跟踪的 JSON 分母（复算）：**121** 件；W38 清单分母：**111** 件。

## 2. 迁移前后计数

| 状态 | W38 清单 | W40 复算 |
| --- | --- | --- |
| 已迁移稳定写入 | 1 | 95 |
| 有理由不迁移（例外登记） | 0 | 19 |
| 待迁移 | 110 | 0 |
| 无写入器（历史产物） | 0 | 7 |
| 合计 | 111 | 121 |

判定口径（与 W38 同列；本件补上「有没有具名写入器」这一维）：

- `已迁移稳定写入`：至少一个 owner 文件含 `write_json_stable`；
- `待迁移`：没有 owner 含稳定写入，但存在**具名写入调用**直接点名该件；
- `有理由不迁移（例外登记）`：写入调用确实点名该件、但该 owner 在 `EXEMPT_WRITERS` 里带理由登记，
  因此**不计入**「待迁移」；
- `无写入器（历史产物）`：没有任何 owner 的写入调用点名该件。

### 2.1 例外登记（19 条候选行，覆盖 22 个 owner）

| 被跟踪 JSON | owner | 理由 |
| --- | --- | --- |
| `probes/dielectric_association_features_summary.json` | `probes/dielectric_association_features_probe.py`; `probes/dielectric_merge_arm_probe.py` | 字节被 probes/dielectric_association_features_summary.json 钉死 | 字节被 probes/dielectric_merge_arm_summary.json 钉死 |
| `probes/dielectric_bagging_probe_summary.json` | `probes/dielectric_bagging_probe.py`; `probes/dielectric_merge_arm_probe.py` | 字节被 probes/dielectric_bagging_probe_summary.json 钉死 | 字节被 probes/dielectric_merge_arm_summary.json 钉死 |
| `probes/dielectric_hybrid_shap_summary.json` | `probes/dielectric_hybrid_shap.py` | 字节被 probes/dielectric_hybrid_shap_summary.json 的 inputs.script_sha256 钉死 |
| `probes/dielectric_knowledge_purity_sweep_erratum_summary.json` | `probes/dielectric_knowledge_purity_sweep_erratum.py` | 字节被 probes/dielectric_knowledge_purity_sweep_erratum_summary.json 钉死 |
| `probes/dielectric_knowledge_purity_sweep_summary.json` | `probes/dielectric_hybrid_shap.py`; `probes/dielectric_knowledge_purity_sweep.py`; `probes/dielectric_knowledge_purity_sweep_erratum.py` | 字节被 probes/dielectric_hybrid_shap_summary.json 的 inputs.script_sha256 钉死 | 字节被 erratum 的 version_1_pins 钉死（锁前冻结，改字节等于篡改 v1 证据） | 字节被 probes/dielectric_knowledge_purity_sweep_erratum_summary.json 钉死 |
| `probes/dielectric_merge_arm_summary.json` | `probes/dielectric_merge_arm_probe.py` | 字节被 probes/dielectric_merge_arm_summary.json 钉死 |
| `probes/dielectric_target_transform_probe_summary.json` | `probes/dielectric_merge_arm_probe.py`; `probes/dielectric_target_transform_probe.py` | 字节被 probes/dielectric_merge_arm_summary.json 钉死 | 字节被 probes/dielectric_target_transform_probe_summary.json 钉死 |
| `probes/eta_epsilon_joint_summary.json` | `probes/build_eta_epsilon_joint_table.py` | 字节被 probes/eta_epsilon_joint_summary.json 的 manifest.builder.sha256 钉死 |
| `probes/identity_smiles_drawing_decision_summary.json` | `probes/identity_smiles_drawing_decision.py` | 盘上 summary 由本脚本 build_full_summary() 重算比对，改字节会让两者不再一致 |
| `probes/kpi_funnel_cross_run_summary.json` | `probes/kpi_funnel_cross_run.py` | 字节按摘要被 reports/decisions_log.md 引用（历史记录，不得回改） |
| `probes/pubchem_identity_layer_summary.json` | `probes/identity_smiles_drawing_decision.py`; `probes/pubchem_identity_layer.py` | 盘上 summary 由本脚本 build_full_summary() 重算比对，改字节会让两者不再一致 | 字节被 probes/identity_smiles_drawing_decision_summary.json 当作依赖件钉死 |
| `probes/pubchem_liquid_window_harvest_summary.json` | `probes/pubchem_liquid_window_harvest.py` | append_run_log 是追加写 JSONL（open(..., 'a')），整篇改写会丢历史行；且有 append 行为测试 |
| `probes/thermoml_local_coverage_summary.json` | `probes/thermoml_local_coverage_probe.py` | 原写入器带 allow_nan=False（严格 JSON），理由同上 |
| `probes/viscosity_row_level_summary.json` | `probes/viscosity_row_level_unfreeze.py`; `probes/w19_chemprop_viscosity.py` | 字节被 w19_chemprop_viscosity_prereg.json 与 w20_eta_fairness_prereg.json 钉死 | 字节被 probes/w20_eta_fairness_prereg.json 钉死 |
| `probes/w19_batt_direct_hit_summary.json` | `probes/w20_safety_ablation.py` | 字节按摘要被 reports/w20_safety_ablation.md / reports/_w20_section_w202.md 引用 |
| `probes/w19_chemprop_viscosity_summary.json` | `probes/w19_chemprop_viscosity.py` | 字节被 probes/w20_eta_fairness_prereg.json 钉死 |
| `probes/w21_li_coordination_summary.json` | `probes/w21_li_coordination.py` | 字节被 probes/w24_condition_redox_prereg.json 钉死 |
| `probes/w24_2_orca_dft_summary.json` | `probes/w24_2_orca_dft.py` | run log 是追加写 JSONL（open(..., 'a')），整篇改写会丢历史行 |
| `probes/walden_dn_channel_prereg.json` | `probes/viscosity_row_level_unfreeze.py`; `probes/walden_dn_channel.py` | 字节被 w19_chemprop_viscosity_prereg.json 与 w20_eta_fairness_prereg.json 钉死 | 字节被 probes/walden_dn_channel_summary.json 的 manifest.builder.sha256 钉死 |

## 3. 抽样证据：连跑两遍不产生新的脏路径

| 探针 | 两轮退出码 | 新增脏路径 |
| --- | --- | --- |
| `probes/w36_gate_admission.py` | 0, 0 | 无 |
| `probes/w36_endpoint_rule.py` | 0, 0 | 无 |
| `probes/w36_channel_noise_floor.py` | 0, 0 | 无 |

审计的是 `git status --porcelain` 在**整仓**上的前后差集（差值已扣掉跑之前就存在的脏路径），
不是只看目标 summary——只看单文件会漏掉探针顺手改写的报告与 CSV。

## 4. 残留：没有 in-repo 写入器的件

### 4.1 历史产物（7 件）

生成器已不在仓库里，不会被重跑脏化，但也不受守卫保护：

| 被跟踪 JSON | 在仓 owner | 其中点名它的写入调用 |
| --- | --- | --- |
| `probes/g1plus_crawl_round2_evidence.json` | 2 | 无 |
| `probes/g1plus_crawl_round3_evidence.json` | 1 | 无 |
| `probes/g1plus_crawl_round4_evidence.json` | 2 | 无 |
| `probes/g1plus_tier0_evidence.json` | 1 | 无 |
| `probes/jstage_corroboration_evidence.json` | 2 | 无 |
| `probes/w19_safety_channel_registry.json` | 2 | 无 |
| `probes/w19_shots_ledger.json` | 2 | 无 |

### 4.2 动态路径写入者（1 件）

| 被跟踪 JSON | writer | 含稳定写入 | 运行时拼名 |
| --- | --- | --- | --- |
| `probes/dielectric_onsager_delta_w18_placebo_summary.json` | `probes/dielectric_onsager_delta_w18.py` | 是 | 是 |

## 5. 判据

| 判据 | 内容 | 读数 | 门 | 判决 |
| --- | --- | --- | --- | --- |
| H40b1 | 复算清单覆盖 W38 清单的全部行（分母一致，行只增不减） | 111 | 111 | 成立 |
| H40b2 | W38 登记的待迁移行在复算清单中不再有「待迁移」（例外登记不算未迁移） | 110 | 110 | 成立 |
| H40b3 | 全仓扫描：仍有写入调用点名某跟踪件、却未用稳定写入的 owner 数（应为 0） | 0 | 0 | 成立 |
| H40b4 | 复算清单中「待迁移」行数（应为 0；有理由不迁移的行走例外登记，不计入） | 0 | 0 | 成立 |
| H40b5 | 无写入器的历史产物件：其任何 owner 的写入调用都不点名它（逐件机械核对） | 7 | 0 | 成立 |
| H40b6 | 动态路径写入者登记项：其 writer 含稳定写入且文件名在运行时拼出 | 1 | 0 | 成立 |
| H40b7 | 抽样连跑两遍：三个已迁移探针都没有产生新的脏路径 | 0 | 0 | 成立 |
| H40b8 | 0 shot（累计 19）；只跑既有探针与合成临时文件 | 0 | — | 成立 |
| H40b9 | 例外登记逐条可核：理由非空，且被登记的 owner 确实不含稳定写入（不得拿例外登记掩盖未迁移） | 0 | 0 | 成立 |

## 6. 边界

- 稳定写入只对**顶层键** `generated_at_utc` / `elapsed_seconds` 生效。复算发现
  **33** 件还带别的易变顶层键（`wall_seconds` / `started_at_utc` / `finished_at_utc` /
  `generated_at_local` / `cache_populated_between_utc` / `throttle_seconds` …）：这些件重跑仍会脏树，
  但它们**不是**「写入器没迁移」，而是「volatile 键集合比助手覆盖的更宽」，属于已登记盲区。
- **例外登记不是豁免**：H40b9 逐条核理由非空、且被登记的 owner 确实不含稳定写入；
  例外件重跑**仍会弄脏工作树**，这是本件明确保留的已知代价（不是已修）。
- 「已迁移」是 owner 级判据（任一 owner 含稳定写入即算），不是逐写入站的完备证明；
  本件用另一条独立读数补强：**全仓不存在「写入调用点名跟踪件却未用稳定写入」的 owner**（判据 H40b3）。
- 不拟合模型、不触四个冻结读数（基线 0.4091179943351143 / 头条 0.4766400383507876）；不占 shot（累计仍 19）。

## 7. 输入指纹

审计只读：写下清单前后各复算一次输入指纹，逐位相同 = **是**。

| 项 | sha256 |
| --- | --- |
| `probes/artifacts/w38_timestamp_inventory.csv` | `6a9ff0c7ebe22a79ce30d6374311efb8103cdf1cd7181f15cbb94584b08d92fa` |
| `probes/g1plus_crawl_round2_evidence.json` | `9734c85d3d01e7abcf52f4442d16aa6c31a54978d20486015d312eae59a9a8de` |
| `probes/g1plus_crawl_round3_evidence.json` | `e837395f9c7599d35f1d75b77e6139be780fd9cf480645e769c4f697ece3c870` |
| `probes/g1plus_crawl_round4_evidence.json` | `1d0d32438e3cd595a991085980212e689243dcc1f1c9a397b6aeb5b21fb5625f` |
| `probes/g1plus_tier0_evidence.json` | `eaabcbeae46eacb4478c8d6583fcb9a45f746cb5a9d7acfb277d72faf7426227` |
| `probes/jstage_corroboration_evidence.json` | `16721290d8a123d0ae150476a8d87e802678b0bf2fce8b77aa59f66cfd01d0ec` |
| `probes/w19_safety_channel_registry.json` | `ae2e1f14245653019b593abe290c842ea0cb956109fc96e62610ea11159ae253` |
| `probes/w19_shots_ledger.json` | `8ccd71d73f7d9ace981cab7e881d84f56fb4b62b28e67edecf57f86744463b52` |
| `probes/dielectric_onsager_delta_w18_placebo_summary.json` | `679e2f15effff8a91b357f91c287bc7f2e61929f031cf4fba4501954eb2425cf` |
