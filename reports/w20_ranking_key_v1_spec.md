# W20-3 排序键 v1 + 交集填充（§28.59）

**性质**：排序键规范 + 一次 Tier C 交集填充实测。**不拟合任何模型**（填充只调用冻结特征块与冻结模型预测）、不产任何通道读数、不占 shot 编号、`produces_reading = false`、`promoted = false`、不动主记分牌（本周 0 次、累计 11 次）、不引用任何 Reaxys 数值、预测**永不入池当标签**。

**一句话**：这是**排序键，不是候选生成器**（`POSITION_STATEMENT = 这是排序键，不是候选生成器`）。

**产物**：
- `probes/w20_ranking_key_v1.py`（可执行实现）；
- `probes/w20_ranking_key_v1_prereg.json`（跑前锁定，`prereg_status = locked_before_run`）；
- `probes/w20_ranking_key_v1_summary.json`（跑后落盘）；
- `probes/artifacts/w20_ranking_key_v1_candidates.csv`（候选清单，16 列契约，见 §5）；
- `tests/test_w20_ranking_key_v1.py`（字面钉测试）、`reports/_w20_section_w203.md`（决策志节）、本报告。

**权威依据**：`reports/week20_project_charter.md` §1 `W20-3`、§5、§7；上游规范件 `reports/w19_ranking_key_spec.md`（排序键 v0）。

---

## 1 三条锁定规则（charter §1 W20-3）与逐条遵守证据

| 规则 | 内容（charter 原文口径） | 实现（可执行） | 测试（可推翻） |
| --- | --- | --- | --- |
| ① 去重 | IP–HOMO `r = −0.9876`、EA–LUMO `r = −0.9513` **已在册**，**不得重复计权** | `COLLINEARITY_RECORD` 登记两组共线；`validate_keys` 对「同组两列同时进键」直接 `ValueError` | `test_a_collinear_pair_may_not_be_counted_twice` |
| ② 适用域闸门 | 域外候选**不给分，不是给低分** | `assign_scores` 对域外行返回 `None`；`_front_flags` 令域外行**永不进前沿**；min-max **只在域内集合内**归一 | `test_out_of_domain_rows_get_no_score_at_all`、`test_a_rejected_row_cannot_move_a_kept_score` |
| ③ 权重跑前声明 | 无成本比证据 ⇒ **等权** | `PREREG_WEIGHTS = {homo 0.5, lumo 0.5}`，`weights_source = no_cost_ratio_evidence`；import 时自检 `DEFAULT_WEIGHTS == PREREG_WEIGHTS`；`build_default_keys` 拒绝无钉列的通道 | `test_the_default_key_is_equal_weight_over_the_two_gated_channels`、`test_a_weight_change_moves_the_ranking` |

三条规则在本件里**是结构，不是编辑口径**：违者由 `validate_keys` / `assign_scores` / import 期自检**直接抛错**，不靠叙述保证。

## 2 去重共线证据（规则①）

在**冻结标签空间**上，IP 与 HOMO、EA 与 LUMO 高度共线（出处：`reports/homo_lumo_baselines.md` 标签空间诊断）——

| 共线组 | Pearson r | 处置 |
| --- | ---: | --- |
| `HOMO_eV` ↔ `IP_eV` | −0.9876 | 保留 `HOMO_eV`，**丢弃** `IP_eV` |
| `LUMO_eV` ↔ `EA_eV` | −0.9513 | 保留 `LUMO_eV`，**丢弃** `EA_eV` |

- 保留列 `DEDUP_KEPT_COLUMNS = (HOMO_eV, LUMO_eV)`，丢弃列 `DEDUP_DROPPED_COLUMNS = (IP_eV, EA_eV)`。
- **不得重复计权**由 `validate_keys` 强制：任一键列只要与其共线伙伴同处一键即报 `is collinear with ...; the same information may not be counted twice`。测试用 `(HOMO_eV, IP_eV)` 与 `(LUMO_eV, EA_eV)` 两组各触发一次。
- IP 0.2010970559642009 与 EA 0.23415453202842548 本身**也未过** 0.20 eV 门（只登记，不进键）。

## 3 适用域闸门：域外不给分，不是给低分（规则②）

- **规则 D1**：`NumHDonors(SMILES) >= 1 and TPSA(SMILES) >= 20.0`（`D1_RULE`），**只读冻结 SMILES 算出的特征**，不读任何标签。
- 域外处置（`out_of_domain_policy`）：**不给分、不给秩、永不进前沿**。`assign_scores` 对域外行返回 `score = None`；`ranking_key_table` 给 `rank = None`、`excluded_reason = out_of_domain`、`on_front = false`。
- **归一化只跑域内集合**：`assign_scores` 先按域掩码取出 `kept`，min-max 只在 `kept` 内做 ⇒ **被拒行无法移动被保留行的分数**（测试 `test_a_rejected_row_cannot_move_a_kept_score`）。
- **「无顺序」而非「最差」**：`dominates` 对域外行**拒绝回答**（`an out-of-domain row carries no order`）——域外行不参与支配判定，不能被拿来当「垫底」。
- 失效区：`HIGH_PERMITTIVITY_EPS = 60.0`；`epsilon > 60` 的行同样判域外（`high_permittivity_excluded`）。
- 分域第二记分牌（本键对齐，非替换）：全域 `0.45401075998423623` / D1 域内 `0.524012313223719` / 域外 `0.3198024498133034`（`probes/dielectric_applicability_domain_summary.json`；`reports/_w18_section_domain.md` §28.45）。

## 4 权重跑前声明（规则③）

- 进键权重：**HOMO 0.5 / LUMO 0.5**（等权）。理由：两通道之间**没有任何实测的成本或收益比**可据以加权；无证据时等权是唯一不引入自由度的选择。`weights_source = no_cost_ratio_evidence`。
- **权重改动 = 预注册改动**：`PREREG_WEIGHTS` 以字面量钉在模块里，import 时与派生键 `DEFAULT_WEIGHTS` 逐位比对，**漂移即报错**；任何非等权都必须先给一条可证伪的理由，并新钉一份预注册。
- **扩维需新预注册**：`build_default_keys` 对「已过门但无钉列/钉方向」的通道**拒绝**（`widening the key needs a new preregistration`）；`assert_no_unregistered_verdicts` 对磁盘上新出现的扩展裁决件**拒绝默默并入**。
- 分数定义：每通道在**域内行集内** min-max 归一到 [0,1]（方向按通道声明，1 = 最好；整列同值取 0.5），再按权重线性求和 ⇒ **集合相对排序量**，不得跨集合比较、不得当预测值引用。

## 5 每候选出口契约（域声明 + 可追溯出处 + 哪个通道给排序）

候选 CSV 的 16 列（`CANDIDATE_COLUMNS`，与 summary 的 `candidate_artifact.columns` 逐位一致）：

`inchikey, smiles, canonical_smiles, source_line, NumHDonors, TPSA, HOMO_eV, LUMO_eV, gap_eV, domain, ranking_channels, key_score, rank, on_front, excluded_reason, provenance`

- **域声明**：`domain ∈ {in_domain, out_of_domain}`，由 D1 规则从冻结 SMILES 判出；`excluded_reason = out_of_domain`（域内为空串）。
- **哪个通道给出排序**：`ranking_channels = homo+lumo`（本版键 = HOMO / LUMO 两维；`ranking_channel = orbitals`）。
- **可追溯出处**：`provenance` 为固定格式串，样本（CSV 第 1 数据行）：

  `tier_c|features=rdkit_morgan_count_r2_2048+30_descriptors|prediction=HOMO=models/homo_lumo_homo.ubj@7e945fc5647f;LUMO=models/homo_lumo_lumo.ubj@9f6c2d6e6f86|domain=NumHDonors(SMILES) >= 1 and TPSA(SMILES) >= 20.0|ranking_channel=orbitals`

  其中 `@` 后为模型件 sha256 前 12 位 ⇒ 每个候选都能回溯到**特征层 + 两个模型件 + 域规则 + 排序通道**。
- **分数列语义**：域内行给 `key_score`（6 位小数）与 `rank`（域内 `(-score, name)` 序）；域外行**两列留空**，`on_front = false` ⇒ 下游无法把「域外」误读成「分很低」。

## 6 交集填充结果：空前沿是一等结论，不是失败

输入 `data/external/Batt-SLM.smi`（sha256 `c2ec78256ce6189366aebd9f7f0403e669c963e911cf51f7732083bce6374a1d`，1,879,361 B）。本机实测（`summary.fill`）：

| 量 | 实测 |
| --- | ---: |
| 文件候选数 / 读入数 | 115756 / 115756 |
| SMILES 可解析 / 无效 | 115756 / 0 |
| 唯一 InChIKey / 重复 InChIKey 行 | 115756 / 0 |
| **域内 `in_domain`** | **0** |
| **域外 `out_of_domain`** | **115756**（share **1.0**） |
| 键维度可评分行 `scoreable_on_key_dimensions_rows` | **0** |
| **前沿 `front_size`** | **0** |
| `top_20` | `[]` |

- **四通道交集填充为空**：Batt-SLM 是**电池溶剂空间**，样本以无氢键给体、`TPSA < 20` 的小分子为主（例：首行 `CP(C)(=S)c1cccnc1`，`NumHDonors = 0`、`TPSA = 12.89` ⇒ 域外）。在发布前锁定的 D1（极性质子）规则下，**全部 115,756 候选判域外**，故**没有任何候选获得分数**，前沿为空。
- **空前沿是结论，不是失败**：闸门**正在做它该做的事** —— 域外**不给分**（而不是给一个会被误读的低分），前沿是**可行集**而可行集为空 ⇒ 不排任何东西、不编造任何东西。把 11.5 万域外行强行排序，才是本键要避免的错误。
- **键的当前站立面（诚实范围）**：`key_dimensions = [HOMO_eV, LUMO_eV]`（2 维）；`core_channels_filled = [orbitals]`；`core_channels_not_filled = [dielectric, viscosity, liquid_window]`；`scoreable_on_core_channels = 1`。四通道里**只填了轨道 1 条**，不得叙述成四通道综合排序。
- **池内对照（`registry_reference`）**：`data/processed/four_core_key_registry.csv` 共 **31949** 行、其中 **29519** 行含两个键维度、**7** 行含四条核心通道 ⇒ 四通道交集在**池内**本就极稀（7 行），域外过滤后为空并不反常。

## 7 扩展登记（W20-1 η / W20-2 Step 2 safety）

扩维是**预注册改动**，被另一 lane 的裁决件闸住；裁决件不在盘上时**保守读作「未过」**，登记为 `pending`，而不是被假设掉。**本节已按 2026-09-28 的重跑更新：**两条裁决件现均已在盘；W20-3 在 W20-1 落盘后重跑，因此下表是重跑时的磁盘状态 —— 结论与跑前预判一致：

| 通道 | owner | 裁决件在盘 | `merged` | 条件 |
| --- | --- | --- | --- | --- |
| viscosity（η） | W20-1 | **是** | **false**（并入条件成立，仍卡自己的门） | W20-1 公平性复检在盘且过（`delta <= -0.02` 且两臂过门状态不变）才并入 |
| safety | W20-2（Step 2） | **是** | **true** | W20-2 Step-2 建模裁决在盘且过自己的门才并入 |

- **η（W20-1）裁决已到（重跑更新）**：`probes/w20_eta_fairness_summary.json` 已在盘，判 `eta_crosses_gate_out_of_fold`（行级 Δ = `-0.05419789751156204`，两臂门状态不变）⇒ **并入条件成立**；但 η 仍卡在 ①：本模块读 η 取**族级（group_key）** `0.17477197208762`（未过 0.15），且 `KEY_CHANNEL_SPECS` 未钉 η 列与方向 ⇒ `merged = false`、键未加宽。
- **safety（W20-2 Step 2）已满足并入条件（`merged = true`）**：`probes/w20_safety_model_summary.json`（§28.58，shot 22）判 `modelable_all`、`blocking_conditions = []`。**但 `merged` 只表示「并入条件成立」，不等于「进了键」** —— safety 仍**没有**声明过的门读数、也**没有**钉住的键列（`KEY_CHANNEL_SPECS` 只有 homo / lumo），因此 `_eligible_channels` 把 safety 挡在键外，**键维度不变**（仍 HOMO / LUMO 两维）。按 W20-2 §28.58 的分域声明，safety **只允许进 ε 侧键、不得进 η 侧**。
- **两级闸门（本版实际机制）**：一条通道进键须同时满足 ① 其**自己的门读数过门**（`CHANNEL_GATE_STATUS[*].passed`）与 ② 扩展通道的**并入条件成立**（`merged`）。η 卡在 ①（族级读数 0.17477197208762 未过 0.15），safety 卡在 ①（无门读数）⇒ 四通道里当前只有轨道 1 条在键内。
- **口径澄清（η；预判已应验）**：本件跑前即写明「即便 W20-1 日后给出有利裁决，η 也不会自动进键」。重跑证实：授权到了、键未动。让 η 进键须**另立预注册**（钉其键列与方向），并**改本模块的 η 门读数口径**（族级 `0.17477197208762` → 行级 `0.1054414994165841`）——两者都属改冻结件级动作，超出本版范围。

## 8 纪律块

| 项 | 值 |
| --- | --- |
| `promoted` | **false** |
| 主记分牌尝试（本周 / 累计） | **0 / 11** |
| `predictions_written_to_any_pool` | **false** |
| 生成闭环 | **welded shut**（uniqueness **0.349** 在册） |
| `reaxys_values_used` | **false** |

- 冻结基线 `0.4091179943351143` 与冻结头条 `0.4766400383507876` **未动**。
- **预测用于排序，永不入池当标签**：Tier C 输出只写进候选 CSV 的排序列，不写进任何 pool / 特征 / 交付包。
- **生成闭环焊接**（三条证据，承 §28.50）：① ElectrolyteGPT 在 10 性质下 uniqueness 塌到 **0.349**；② 其 10 个性质全为代理输出、`never subjected to a group-split audit`；③ 其许可 `CC-BY-NC-ND` 4.0 不得改作。**本项目不做生成闭环、不做候选生成器。**

## 9 复现与测试

- 填充（可复现）：`.venv/Scripts/python.exe probes/w20_ranking_key_v1.py` ⇒ 写 `probes/artifacts/w20_ranking_key_v1_candidates.csv`（LF / UTF-8 / 无 BOM）与 `probes/w20_ranking_key_v1_summary.json`（LF / UTF-8 / 无 BOM）。
- 示例排序（合成夹具，数值任意、不含任何化学主张）：`.venv/Scripts/python.exe probes/w20_ranking_key_v1.py --print-example`。
- 扩维扫描：`.venv/Scripts/python.exe probes/w20_ranking_key_v1.py --check-extensions`。
- 测试：`.venv/Scripts/python.exe -m pytest tests/test_w20_ranking_key_v1.py -q -p no:cacheprovider`。
- 示例钉值（默认等权）：`demo-b 0.8285714285714287 > demo-c 0.5 = demo-d 0.5 > demo-f 0.34285714285714286`，前沿 `{demo-b, demo-c, demo-d}`，`demo-a` / `demo-e` 域外 `None`；权重改 HOMO 0.9 / LUMO 0.1 后排序变为 `demo-d 0.9 > demo-b 0.8057142857142858 > demo-f 0.3885714285714286 > demo-c 0.1` ⇒ **权重是显式的、可被测试直接推翻的**。

## 10 边界（不许省略）

- 排序键**不产生新数据**：本版决策域 = HOMO / LUMO 两维；ε / η / 氧化 / 还原未过门，**其数字不得进键、不得作排序依据**。
- 分数是**集合相对排序量**，不是物性预测；域外行**无分数**，不得被当「最差」使用。
- 全 115,756 候选域外 ⇒ 本件**不产出任何可用短名单**；空前沿如实报空。
- 未来扩通道的唯一路径：先把该通道推过自己的门，再改本件并重钉预注册；**先加通道再加门是禁止的**。
