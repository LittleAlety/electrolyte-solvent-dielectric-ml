# Week 19 · D1 现状核对表与修订台账（本机实测版）

- **性质**：审计件。§W19-0.5 现状核对表 + §W19-0.6 修订台账的复核。下表每个数字都是本机复算的；计划文档只作**被检对象**，不作事实来源。
- **生成时间（本机 UTC 时钟）**：2026-09-27T16:11:33.876Z；宿主 Windows / PowerShell；**未运行任何拟合或训练**（16 核被 W18 四条 lane 占用）。
- **测量方式**：node 流式 sha256；逐字节行尾（CRLF）与 BOM 扫描；HDF5 **元数据**读取（`data/raw/batt/Batt-P30K.h5` 只列顶层 group，**不整表加载**）；PyMuPDF 文本抽取（仅 `au5c01628.pdf`）；ripgrep 全仓检索。
- **权威输入（只读）**：`E:/大二/d2qc/电解液（长期项目）/文献调研/重点且同向/Week19立项计划_文献驱动三线.md`
  - 实测 24,077 B；sha256 `1ba6a239241200aef9f767c5203bd0c6ad0dc7e02d49eea9594f683d39752899`；mtime `2026-09-27T14:13:11Z`。
- **判定纪律**：计划写「已核 / 一致」但本机无副本可复现的，一律记 **不一致 / 不可核**，不替计划圆场。

## ① 结论

计划的**资产表（§W19-0.5）与 Onsager 既成读数（§W19-5）在字节级、数值级上高度可复现**：`Batt-P30K.h5` 的 sha256 与冻结 `v03` 的 digest 逐位一致，Onsager 八臂读数与域计数逐位一致，E5 的 76/239 被本机独立复现。
但有三处必须改判或登记：**(a) 转录表里 EDB 18,316 实为「EDB + MP」合计**；**(b) HOMO/LUMO MAE 确认记错**（仓内 0.17662 / 0.24935 eV，非 0.304 / 0.350）；**(c) 修订台账 E1 的许可出处本机无法证实**。
另有一条**计划未登记、但影响判据**的矛盾：§W19-3 依赖里写「kinematic 存量 214 行仍冻结，待密度配对解冻」，而 W18 §28.38 **已经解冻并实测过**（176 行 ThermoML kinematic 经 `density_v01` 配对 → 池化 86 行）。详见 ④-b。

## ② 现状核对表

| 资产 | 路径 | 实测字节数 | 实测 sha256（全值） | mtime (UTC) | 计划里的声称 | 本机实测是否一致 |
| --- | --- | ---: | --- | --- | --- | --- |
| Batt-P30K 数据集 | `data/raw/batt/Batt-P30K.h5` | 183,771,012 | `587f1490613a008b91f45ee9de607a2e057c88c301fa9e5c9d7785b1968d118d` | 2026-09-22T08:18:31Z | 183,771,012 B；sha256 `587f1490…8d118d`（与上游 LFS oid 逐位一致）；已下载 | **字节数与 sha256 逐位一致**；但「与上游 LFS oid 逐位一致」本机不可核（本地无上游 LFS 指针副本）⇒ 上游半句记**不可核** |
| Batt-SLM 空间 | `data/external/Batt-SLM.smi` | 1,879,361 | `c2ec78256ce6189366aebd9f7f0403e669c963e911cf51f7732083bce6374a1d` | 2026-09-22T15:24:11Z | 1,879,361 B（115,756 行 SMILES） | **一致**（实测 115,756 行，无表头、LF、无 BOM） |
| RX-392（氧化还原） | `data/external/Batt-SLM-RX-392.csv` | 248,404 | `d30ec1ffccba15538bac0b67157c14e045f1721441be23837c6195eca24a5d87` | 2026-09-22T15:52:42Z | 248,404 B（393 行） | **字节数一致**；行数口径需注明：393 行**含 `$` 分隔表头** ⇒ 实测 **392 条记录**、392 个唯一 MolId（与文件名 RX-392 相符） |
| CPI 特征表 | `data/external/SolvFunc-87.csv` | 20,753 | `1031abc49ee4f15d46211a519be6b5cdee3b68115e5e2f5141f7d155342ba493` | 2026-09-22T15:19:57Z | 20,753 B（87 溶剂） | **一致**（88 行含 `;` 分隔表头 ⇒ 87 数据行；含 `DC_Pred` 列，87 行全部非空） |
| HOMO/LUMO/IP/EA 基线（Batt 池） | `probes/homo_lumo_baselines_summary.json` | 20,977 | `aac25ae6fc57fc3b7944717ae23412f39fda8a5fa33d4b6f7649bef79ce55425` | 2026-09-25T21:39:34Z | 2026-09-25T21:36:40Z；`complete=true`；HOMO/LUMO/IP/EA 四目标全完成；池 29,515 行（4 冠军已排除）；`gate_status=final` | **一致**。内部 `generated_at_utc` 逐字为 `2026-09-25T21:36:40Z`（计划引的是内部时间戳，非文件 mtime；两者差 2m54s，属写盘时刻，非矛盾）。实测 `pool_rows=29515`、`gate_status=final`、`completed_targets=[LUMO,HOMO,IP,EA]`、`champions_excluded` 恰 4 个 |
| Onsager Δ-learning 探针 | `probes/dielectric_onsager_delta_summary.json` | 108,084 | `3acd499b2653135556bcdd61a1bdb2e8977973821f8b00f804e2431edef1754b` | 2026-09-25T05:55:35Z | 2026-09-25T05:55:35Z；234 分析样本；行级 RepeatedKFold 5×10 seed 42；`decision=go` | **一致**。内部 `generated_at=2026-09-25T05:55:35.227743+00:00`；`sample_count=234`；`splitter.level=row`、`n_splits=5`、`n_repeats=10`、`random_state=42`；`decision.decision=go` |
| 介电通道族比较 v2 | `probes/dielectric_channel_v2_summary.json` | 37,597 | `159f780bcb41be3bcc4358aece4ec26af0a7cb0e242618d2704696adfb85ef01` | 2026-09-25T22:41:42Z | 2026-09-25T22:20:02Z；`not_a_verdict=true`、`verdict_eligible=false` | **一致**。内部 `generated_at_utc` 逐字为 `2026-09-25T22:20:02Z`；两布尔键与声称同值（计划引内部时间戳，文件 mtime 晚 21m40s） |
| 氧化还原通道 v2 | `probes/p4_redox_v2_summary.json` | 58,332 | `d3e3ae6624d04f0dc9f020f09c6ce9ac1a5f830d6bff5ea7f19fe69253cd2692` | 2026-09-25T21:36:47Z | 含 `verdict` / `gate` / `learning_curve` | **一致**（三键俱在；无内部 `generated_at*` 键，故计划未引时间戳） |
| Batt ↔ PubChemQC 跨水平标定 | `reports/decisions_log.md` §28.17 | 547,262 | `4208fe8adf4ed6eee305b1a83ad322aada7f5bea01f538a57e45462a86899838` | 2026-09-27T15:45:11Z | n = 111 配对锚点，2 折样本外 | **一致**。`reports/decisions_log.md:4748`：「判定 D：n ≥ 60 通过，n = 111；2 折样本外」；§28.17 标题在 `:4706`（全表 5,530 行、纯 LF） |
| 冻结 ε 表 v03 | `data/dielectric_v03.csv` | 130,844 | `ff2142936e06e04b329b70f8597574f75349e54ce876e9fff81309e6d35ccce4` | 2026-09-25T05:49:09Z | 246 行；sha256 `ff214293…35ccce4` | **一致**（247 行含表头 ⇒ 246 数据行；digest 全值逐位一致；该 digest 同时写在 Onsager 摘要的 `dataset_sha256` 字段里） |
| THEMol 名册摘要（E2 依据） | `probes/themol_registry_expansion_roster_summary.json` | 1,664 | `ccaad016db6cb1bbda967755e85a445502b7b45e9613ff73538dcae8d38e6e45` | 2026-09-26T22:18:07Z | `level_of_theory` 用于证明 THEMol 为气相单点 | **一致**（见 ④ E2；`is_a_plan_not_a_measurement=true`、`queries_executed=0` 也在盘） |
| 适用域旧记录（继承） | `probes/applicability_domain_summary.json` | 2,198 | `bc20c21c0a015b45a54a94711a34e4c46a377849c3c109b0c625a8275479fdd6` | 2026-09-24T20:17:13Z | 旧 Onsager 阈值规则记物理反转、维持否决态 | **一致**。`rejected_variants.onsager_threshold.rule` 逐字为 `hbond_donor_count >= 1 and onsager_epsilon > 60`，`reason` 明写 physically inverted（Kirkwood g ≫ 1），`high_permittivity_zone_covered=0` |
| η 池 v02 | `data/viscosity_v02.csv` | 11,501,156 | `907f5368ff6d4d6c15fa26c8c2b57e8bbc8c7ac7a7b3db06ec2c689b283bf3a5` | 2026-09-26T13:40:42Z | 42,941 数据行 + 1 表头 | **一致**（42,942 行含表头 ⇒ 42,941 数据行；`Viscosity, Pa*s` 42,855 + `Kinematic viscosity, m2/s` 86） |
| xTB 物理特征输入 | `probes/artifacts/v03_features_baseline_input.csv` | 47,293 | `da82f748daeccbc9c7c045aa2369085b147c2124693c62dc72994a4cb629f5f4` | 2026-09-24T20:17:18Z | 已含 `dipole_D` / `mu_sq_over_Vm`，覆盖 239 行 | **一致**（恰 239 数据行，两列俱在）。**交叉印证**：该文件 sha256 与 Onsager 摘要的 `input_sha256` 逐位相同 ⇒ W19-5 的偶极确实来自此表 |
| 仓库许可件（E1 被检对象） | `LICENSE` / `LICENSE-DATA.md` | 1,256 / 3,704 | `726e83cc33938882c7152342eec3ad1f9e25799be0c76742f924f2cf965f1b7f` / `3897e58e93800909b25db7be63df03c1ac2f8f9509396b2b3a5c4f0e2ca5a8ba` | 2026-09-25T10:02:36Z / 2026-09-26T20:00:16Z | E1 声称「Batt-SLM 仓库 LICENSE = MIT（Copyright (c) 2026 Zhan-Yun Zhang）」 | **不一致（不可核）**：本机 `LICENSE` 是 MIT，但版权人逐字为 `the electrolyte-solvent-dielectric-ml authors`；全仓（含 `data/raw/batt/`，该目录实测只有 `Batt-P30K.h5`、无上游 LICENSE 副本）对 `Zhan-Yun` **零命中** ⇒ E1 的「依据 = 实测 LICENSE 全文」在本机无可复现副本 |

**②-a 时间戳口径说明**：计划 §W19-0.5 里 `homo_lumo_baselines` 与 `dielectric_channel_v2` 两行引的是**摘要文件内部**的 `generated_at*`，不是文件 mtime。两处内部值都逐字对齐；文件 mtime 分别晚 2m54s / 21m40s，属写盘时刻，不构成不一致。其余各行按文件 mtime 实测。

## ③ 转录数字核对表（§W19-0 逐行裁定）

计划该表自带「已核 / 未核 / 错」三态。下表是**本机裁定**（左列照抄计划行，右列是本机证据）。

| # | 数字（计划写法） | 计划标注的声明来源 | 计划自评 | **本机实测裁定** |
| --- | --- | --- | --- | --- |
| 1 | DC_Pred 128.94（Vinylene Carbonate） | `data/external/SolvFunc-87.csv` | 已核（87 行，含 DC_Pred 列） | **已核**。实测 VC 行 `DC_Pred = 128.941261`（四舍五入即 128.94）；87 行全部有非空 `DC_Pred`，128.941261 即全表最大值。计划的分句（87 行 / 含该列）与本机逐项相符 |
| 2 | uniqueness 0.349 | au5c01628 | 已核（10 性质条件化档） | **已核，但只在文献层**。本机抽取 `au5c01628.pdf`（15 页 / 81,744 字符）原文：「The model suffers from a notable decline in uniqueness (0.349), with approximately 65% of compounds generated more than once」——正是**条件化生成**档。⚠ 仓内（`git` 工作树文本）对 `0.349` **零命中**（唯一相近的是 `paper/full_draft.md` 的 0.3494 hybrid R²，无关）⇒ 该「已核」**不可在仓内复现**，引用时须注明出处是 PDF |
| 3 | EDB 18,316 条 | au5c01628 / Kumar et al. | 已核 | **数字已核、归属判错**。原文：「a total of 18316 SMILES reported in the EDB **and MP** data sets … was added to give 1,018,316 SMILES total」⇒ 18,316 是 **EDB + MP 两库合计**，不是 EDB 单独；原文另有「extracted from over 250 literature papers」对应 EDB 腿。⇒ 计划把库名写成「EDB 18,316 条」（§W19-0 表与 §W19-2「EDB 先例（250+ 篇文献 → 18,316 条条目）」）为**部分错**：数字对、归属错 |
| 4 | Batt-P30K 29,519 分子 | acsnano.6c06255 / README | 已核（本地 h5 group_count 一致） | **已核**。本机 HDF5 元数据实测顶层 group 数 **29,519**（`CompMol0 … CompMol9999`，带编号空洞）；成员键实测为 `coord, dipole, ea, elems, ener, ener_anion, ener_cation, gap, homo, ip, lumo, quadrupole, smiles`（homo/lumo 在盘）。DOI `10.1021/acsnano.6c06255` 亦见 `redox_merged.csv` 与 homo_lumo 摘要的 `unit.source_doi` |
| 5 | RX-392 393 行 | Batt-SLM 仓库 | 已核（248,404 B） | **已核，口径需注明**。字节数 248,404 一致；文件 393 行**含 `$` 分隔表头** ⇒ 数据记录 **392** 条、唯一 MolId 392 个（与文件名 RX-392 自洽）。若把「393 行」读作「393 个化合物」即为错 |
| 6 | η MAE 0.1223@298K | 记为「文献」 | 未核 | **未核（本机复核，确认无出处）**。全仓 `0.1223` 命中 69 处，**无一处是 MAE**（按 `mae/MAE/error` 语义过滤后为 0 命中）：其中 `data/viscosity_v02.csv` 2 处是**实测黏度** 0.1223 / 0.12234 Pa·s（3-methylnonyl 1,2-benzenedioate，293.15 / 293.23 K），其余为 MLP / Chemprop / Onsager / 各种 predictions 表的逐点残差巧合值。⇒ 计划标「未核」**成立**，且本机可确证其「未核」状态；进正式表格前必须回原文 |
| 7 | HOMO MAE 0.304 / LUMO MAE 0.350 | 记为「THEMol 参考点」 | 错 | **确认为错**。本仓 `reports/decisions_log.md:4752` HOMO 样本外 MAE = **0.17662467232470583 eV**（slope 1.0132507837193052、intercept −2.8354161402050426 eV、r 0.9717477841107552）→ `usable_with_flag`；`:4753` LUMO MAE = **0.24935401611452185 eV**（r **0.7349044734023142**）→ `reference_only`，且降级由 **r < 0.80** 触发、**不是** MAE（0.249 ≤ 0.35 本身过关）。同值另见 `reports/orbital_second_source.md:75`。与 E3 一致 |

### ③-b ε ≥ 60 名册实测（`data/dielectric_v03.csv` 全表，246 行）

本机解析全表后按 `dielectric >= 60` 过滤，命中 **9 个**（下表为**全部**成员，按 ε 降序）：

| # | 名称（表内 `name` 原样） | ε | T_K | InChIKey |
| --- | --- | ---: | ---: | --- |
| 1 | N-methylacetamide | 178.47 | 303.15 | `OHLUUHNLEMFGTQ-UHFFFAOYSA-N` |
| 2 | vinylene carbonate | 126 | 298.0 | `VAYTZRYEBVHVLE-UHFFFAOYSA-N` |
| 3 | formamide | 106.14 | 303.15 | `ZHNUHDYFZUAESO-UHFFFAOYSA-N` |
| 4 | ethylene carbonate | 90.5 | 313.15 | `KMTRUDSVKNLOMY-UHFFFAOYSA-N` |
| 5 | 2-hydroxyethylammonium lactate | 85.6 | 298.15 | `NEQXUPRFDXNNTA-UHFFFAOYSA-N` |
| 6 | water | 78.87 | 297.575 | `XLYOFNOQVPJJNP-UHFFFAOYSA-N` |
| 7 | fluoroethylene carbonate | 78.4 | 296.15 | `SBLRHMKNNHXPHG-UHFFFAOYSA-N` |
| 8 | propylene carbonate | 64.9 | 298.15 | `RUOJZAUFBMNUDX-UHFFFAOYSA-N` |
| 9 | ethanolammonium nitrate | 60.9 | 298.15 | `LZJIBRSVPKKOSI-UHFFFAOYSA-O` |

**与计划 §W19-5 的 9 个逐字比对：一致。** 计划写的「NMA 178.47 / VC 126 / 甲酰胺 106.14 / EC 90.5 / HEAL 85.6 / 水 78.87 / FEC 78.4 / PC 64.9 / 乙醇铵硝酸盐 60.9」与上表**逐个成员、逐个数值对齐**（中文名是译名：甲酰胺=formamide、乙醇铵硝酸盐=ethanolammonium nitrate；HEAL 见 ④ E6）。

三条必须随数字引用的边界：
- **不含 NMF**：`N-methylformamide` 在 `v03` 与 `v04` 全表**零命中**（最近的同类是 `dimethylformamide` ε=36.55）⇒ E4 的「不含 NMF」成立。
- **水是 78.87 不是 80.0**：W17 旧「6 个自缔合质子液」名册写的「水 80.0」与本表的 78.87 **不是同一名册**，两处数字不得互引（E4 已登记此冲突）。
- **v04 同名单**：`data/dielectric_v04.csv`（134,460 B，sha256 `e046a3831630e36aae6b67666f74f787b8b33303057877c3402ff7a414e0873c`，248 数据行）按同一阈值实测**同为这 9 个、数值逐位相同** ⇒ 名册在 v03→v04 之间未漂移。

## ④ 修订台账 E1–E6 复核

| # | 计划的说法（原表述 → 修正后） | 本机实测 | 复核结论 |
| --- | --- | --- | --- |
| E1 | 「Batt-SLM 仓库 MIT、数据集 CC-BY」→ 仓库 `LICENSE` = **MIT**（Copyright (c) 2026 Zhan-Yun Zhang）；「数据集 CC-BY」无出处、删除。依据记为「实测 `LICENSE` 全文」 | 本机**没有** Batt-SLM 上游仓库副本：`data/raw/batt/` 实测只有 `Batt-P30K.h5`；全仓对 `Zhan-Yun` **零命中**。本仓自己的 `LICENSE`（1,256 B）是 MIT，但版权人逐字为 `the electrolyte-solvent-dielectric-ml authors`；`LICENSE-DATA.md`（3,704 B）声明的是**本项目** `data/**` 的 CC BY 4.0 再分发条款 | **不可核**。「删除无出处的数据集 CC-BY」的**处置方向正确**，但 E1 声称的依据（实测上游 LICENSE 全文）在本机**无副本可复现**；且**不得**用本仓 `LICENSE-DATA.md` 冒充上游许可证据 |
| E2 | 「Batt-P30K 为单点 SMD(ε=18.5)，THEMol 为集成」→ THEMol = GFN2-xTB//B3LYP-D3(BJ)/DZVP **气相**单点（在 DFT 几何上）；Batt-P30K = ωB97X-V/def2-TZVPPD/**SMD(ε=18.5)** 隐式溶剂化 | `probes/themol_registry_expansion_roster_summary.json` 的 `level_of_theory` 逐字为 `GFN2-xTB//B3LYP-D3(BJ)/DZVP (gas phase, single point on the DFT geometry)`；Batt 侧见 `homo_lumo_baselines_summary.json` 的 `unit.dataset_method` = `wB97X-V/def2-TZVPPD/SMD(epsilon=18.5)`，且 `Batt-SLM-RX-392.csv` 的 `UniqueLevel` 列同串 | **一致（双侧都实测到）**。注意 E2 的「依据」列只点了 THEMol 侧文件，Batt 侧依据在另一个文件里 |
| E3 | 「HOMO MAE 0.304 usable_with_flag / LUMO 0.350 reference_only」→ **HOMO 0.17662 eV / LUMO 0.24935 eV**；且 LUMO 降级由 **r = 0.7349 < 0.80** 触发，不是 MAE | `reports/decisions_log.md:4752` HOMO `0.17662467232470583 eV`、r `0.9717477841107552`；`:4753` LUMO `0.24935401611452185 eV`、r `0.7349044734023142`；`reports/orbital_second_source.md:75` 同值 | **一致** |
| E4 | 「6 个自缔合质子液」（含 NMF 169.8、水 80.0）与 v03 的 ε≥60 名单冲突；后者为 **9 个**且**不含 NMF** | 见 ③-b：v03 全表 ε≥60 恰 **9 个**，与计划所列逐字一致；`N-methylformamide` 在 v03/v04 零命中 | **一致** |
| E5 | 「76/239 verbatim SMILES 命中」是**逐字匹配下界**（写作环境无 rdkit、未做规范化），真实交集可能更高，须补规范化重匹配 | 本机独立复现：取 `probes/artifacts/v03_features_baseline_input.csv`（**恰 239 行**）的 `smiles` 列，与 `data/external/Batt-SLM.smi` 的 **115,756** 行做**逐字字符串相等**比对，命中 **76 / 239**（同一口径下 v03 全表 246 行命中 83）。仓内对字符串 `76 / 239` 检索**零命中**（该数字此前未落盘） | **一致，且已补齐落盘证据**。E5 的两个限定词（「逐字」「下界」）与实测相符——但须注意：**规范化后的真实交集尚未测**，「下界」定性正确、数值不可当终值 |
| E6 | 「乳酸乙醇铵 85.6」→ 正名 **2-hydroxyethylammonium lactate**（HEAL / 羟乙基乳酸铵） | v03/v04 的 ε=85.6 行 `name` 逐字为 `2-hydroxyethylammonium lactate`（InChIKey `NEQXUPRFDXNNTA-UHFFFAOYSA-N`） | **一致（正名）**；但**缩写 `HEAL` 不是仓内术语**——全仓 73 处 `HEAL` 命中全是无关子串（如 pubchem JSON 的字段名），**零处**指该化合物 ⇒ 预注册里若写 `HEAL` 须自带定义 |

### ④-b 追加不一致登记（本机发现、计划未登记）

以下四条不在 E1–E6 里，但都直接影响 W19 判据，按同款纪律登记：

1. **§W19-3 的 kinematic 依赖与已执行的 W18 事实矛盾（本轮最有问题的一条）**。计划写：「kinematic 存量 **214 行**（176 ThermoML + 38 其他）**仍冻结**，待密度配对解冻（W18-4 口径）」。本机实测：(a) `data/viscosity_v02.csv` 里 `Kinematic viscosity, m2/s` 只有 **86 行**（全部 `value_origin=kinematic_converted`）；(b) **214** 的真实出处是 `reports/eta_epsilon_joint_table.md:88` 的**族级排除计数** `kinematic_viscosity_not_dynamic = 214`，`reports/walden_dn_channel.md:91` 已明注「这是**族级**读数」（其中 ThermoML 腿 176）；(c) W18 §28.38（`reports/decisions_log.md:5450-5459`）**已经解冻并实测**：176 行 ThermoML kinematic 经 `density_v01` 配对 → **池化 86 行**进 `thaw_only` / `row_level`（另有 90 行多组分延后），三池 MAE `0.17477197208762 / 0.15698877870055475 / 0.15686276760094522`，**全部未过 0.15**，`verdict=refuted`。⇒ 「214 行仍冻结、待解冻」是**双重问题**：数级口径混用（族级 214 vs 行级 86）+ 状态过期（已解冻、已判 refuted）。W19-3 的「本枪只用已解冻数据」因此指向的是一份**已被判负**的池。
2. **§W19-5 的失败名单计数错**：计划写「差异来自 4 个拟合失败 + 1 个留出 + 其余过滤：**2 个咪唑类 IL** 与六羰基铁失败」。实测 `failed_names` 共 4 条 = **3 个咪唑类 IL**（`1,3-dimethylimidazolium dimethylphosphate`、`1-butyl-2,3-dimethylimidazolium hexafluorophosphate`、`1-butyl-3-methylimidazolium hexafluorophosphate`）**+ Iron pentacarbonyl**。⇒ 「2 个」应为 **3 个**（否则 2+1=3 ≠ 计数 4）。另：246 − 4 失败 − 1 留出 = 241，与 `sample_count=234` 差 **7 行**，计划只写「其余过滤」未给数。
3. **§W19-1 的「UChicago Box」无证据**：计划写 ElectrolyteGPT「数据与预训练模型托管于 **UChicago Box**」。本机抽取 `au5c01628.pdf` 全文（15 页 / 81,744 字符）对 `Box` **零命中**；论文 Data Availability Statement 逐字指向 `https://github.com/AmanchukwuLab/ElectrolyteGPT`。⇒ 「UChicago Box」在原文与本机均**无出处**（**许可半句已核实**：页脚逐字「This article is licensed under CC-BY-NC-ND 4.0」⇐ 计划 §W19-1/§W19-2 的 CC-BY-NC-ND 判读成立）。
4. **§W19-3 的 Chemprop 待核项可结案**：计划写「Chemprop 在 ε 上已负（原稿写 0.237 < 0.364，**待核**）」。本机实测 `reports/decisions_log.md:432`：`10x5 outer folds, mean R2 is 0.237, MAE 7.887, and Spearman 0.665`（对照 v1.0 headline `0.364`，见同文件 `:455` / `:512`）⇒ **0.237 < 0.364 成立**，该「待核」可改判**已核**。

## ⑤ 不做清单与引用纪律（照抄计划实质约束，措辞压缩、不放宽）

**不做清单**
- 不接 OMat24（无机晶体，与本项目分子液体错配）。
- 不做生成闭环、不做候选生成器（uniqueness 0.349 证据在册）。
- 不把 ElectrolyteGPT 的代理输出当训练数据；不用任何**随机拆分**文献数字做对照靶或晋升依据。
- **不重跑已在盘的 W17 资产**（Batt-P30K 下载与标定、Onsager 探针、`homo_lumo_baselines`、`dielectric_channel_v2`）；确需重跑，须先在预注册里写明既有结果的缺陷。
- **不把行级随机折读数当对照靶**——既包括文献读数，也包括**仓内** Onsager 探针与 `channel_v2` 的读数。
- 不动 6 个冻结件：v03 `ff214293…`、v11plus `159b928f…`、viscosity_v01 `12dfa03f…`、3 个预注册件 `ab3503c0…` / `77f61a83…` / `b838febb…`。
- 不开**无预注册**的枪；81 MB 原始层不进任何 bundle；受限值永不在再分发层出现。
- 不在本章修订 Week 18 的任何判据（W18-2 端点定义、W18-7 退出判据只能由作者确认后修订，**修订即记录**）。

**引用纪律**
- 每条枪先锁预注册，**预注册永不事后修订**（lever-8 先例）；placebo 不过门则增益不引用；覆盖检查先于特征；冲突不平均（GVL 双行前例）；叙述层数字**字面钉测试**（AF-13）。
- 图源读数与受限库（含 Reaxys）值一律 `restricted_crosscheck_only`：**永不入 `data/`、永不入任何池**；每条抽取记录必须带 DOI + 表/图定位，**无定位不入库**；出版商站点手动逐条查询合规、**批量爬虫禁止**（OA API 除外且需登记）。
- 许可判读：EDB / ElectrolyteGPT 的**字段设计**可借鉴（思想不受版权保护），但其数据受 CC-BY-NC-**ND** 约束，**不得改造后入库**；此判读须写入预注册。
- 口径不得混比：行级随机折（in-distribution interpolation）与 GroupKFold 组外读数**并列报、不混比**；`214`（族级排除）与 `86`（行级池化）**不得互引**（见 ④-b-1）。

**本报告的自证边界**
- 所有 sha256 均由本机对**当前工作树字节**流式计算；若文件在报告生成后被改动，摘要将失配——**这正是本报告作为 D1 交付件的用途**。
- 本报告**未**复核「上游 LFS oid」「Batt-SLM 上游仓库 LICENSE」两类**本机无副本**的声明；它们被显式记为「不可核」，**不得**在后续章节改写成「已核」。
- 报告生成时工作树含 W18 未提交产物；`reports/decisions_log.md` 正在被 W18 收口写入，其 sha256 只标识本报告生成时刻的字节。

