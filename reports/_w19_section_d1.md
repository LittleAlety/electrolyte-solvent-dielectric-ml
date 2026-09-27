## 28.46 Week 19 D1 现状核对与修订台账：11 条计划数字被本机实测逐条裁定（2026-09-28）
|
**机制假设**：Week 19 的全部 lane 都吃同一份输入 —— `Week19立项计划_文献驱动三线.md`（本机实测 24,077 B、sha256 `1ba6a239241200aef9f767c5203bd0c6ad0dc7e02d49eea9594f683d39752899`）的资产表 §W19-0.5、转录表 §W19-0、修订台账 §W19-0.6。D1 不造任何东西，只问一件事：计划里那些写着「已核 / 一致」的字节与数值，在本机能不能复现。判定纪律照抄：**计划只作被检对象、不作事实来源**；本机无副本可复现的，一律记「不可核」，不替计划圆场。
**预注册**：本件是审计件，**不是枪** —— 不锁预注册、不拟合任何模型、不产 R2 / MAE。报告 `reports/w19_state_audit.md`，sha256 `6deeaab6c32eef511336d02677dac654dfc6c8adf71c30f4b5df81cc3e723e1c`；字面钉测试 `tests/test_w19_state_audit.py`，sha256 `ef1a4c7c54004adeeef1939335ce1a568cc6899f5f2e0d0be4107b113325d39e`（逐字钉住报告 digest 与 43 条实测字面量）。报告生成于本机 UTC `2026-09-27T16:11:33.876Z`，全部 digest 按当时工作树字节流式计算。
|
**读数一 · 资产表（字节级 + digest 级逐条复算）**
- `data/raw/batt/Batt-P30K.h5`：183,771,012 B、sha256 `587f1490613a008b91f45ee9de607a2e057c88c301fa9e5c9d7785b1968d118d` ⇒ **与计划逐位一致**（h5 内实测 group 29,519 个，成员键含 `homo` / `lumo` / `gap` / `ip` / `ea` / `dipole` / `quadrupole` / `coord` / `smiles`）。
- `data/external/Batt-SLM.smi`：1,879,361 B、**115,756** 行（无表头、纯 LF、无 BOM）⇒ 一致。
- `data/external/Batt-SLM-RX-392.csv`：248,404 B。计划写「393 行」，实测 393 行**含 `$` 分隔表头** ⇒ 数据记录 **392** 条、唯一 MolId 392 个（与文件名 RX-392 自洽）。
- `data/external/SolvFunc-87.csv`：20,753 B、87 数据行，`DC_Pred` 列 87 行全非空；该列最大值 = Vinylene Carbonate 的 **128.941261**（即计划写的 128.94）。
- `data/dielectric_v03.csv`：130,844 B、**246** 数据行（247 行含表头）、digest `ff2142936e06e04b329b70f8597574f75349e54ce876e9fff81309e6d35ccce4` ⇒ 与计划逐位一致；`data/dielectric_v04.csv`（134,460 B）248 数据行，同名单、数值逐位相同。
- `data/viscosity_v02.csv`：11,501,156 B、**42,941** 数据行（42,942 行含表头），其中 `Viscosity, Pa*s` 42,855 行、`Kinematic viscosity, m2/s` **86** 行。
- `probes/artifacts/v03_features_baseline_input.csv`：47,293 B、恰 **239** 数据行，`dipole_D` / `mu_sq_over_Vm` 两列俱在。
- `probes/homo_lumo_baselines_summary.json`：`pool_rows = 29515`、`gate_status = final`、四目标全完成、champions 恰排除 4 个。
- `probes/dielectric_onsager_delta_summary.json`：`sample_count = 234`、行级 RepeatedKFold 5×10 / seed 42、`decision = go`。
- `LICENSE`（1,256 B）/ `LICENSE-DATA.md`（3,704 B）：本仓 MIT 的版权人逐字为 `the electrolyte-solvent-dielectric-ml authors`；全仓对 `Zhan-Yun` **零命中**。
|
**读数二 · 转录表逐行裁定（§W19-0 的 7 行）**
| # | 计划写法 | 计划自评 | **本机裁定** |
| --- | --- | --- | --- |
| 1 | DC_Pred 128.94（Vinylene Carbonate） | 已核 | **已核**（实测 128.941261，且为全表最大） |
| 2 | uniqueness 0.349 | 已核 | **已核，但只在 PDF 层**：原文「decline in uniqueness (0.349), with approximately 65% of compounds generated more than once」；仓内文本对 `0.349` **零命中** ⇒ 引用须注出处是 PDF |
| 3 | EDB 18,316 条 | 已核 | **数字对、归属错**：原文是「EDB **and MP** data sets」，18,316 为两库**合计**（EDB 腿对应「over 250 literature papers」） |
| 4 | Batt-P30K 29,519 分子 | 已核 | **已核**（HDF5 顶层 group 实测 29,519） |
| 5 | RX-392 393 行 | 已核 | **已核、口径需注明**：248,404 B 一致；393 行含表头 ⇒ 392 条记录 |
| 6 | η MAE 0.1223@298K | 未核 | **未核（本机确证无出处）**：全仓 `0.1223` 命中 69 处，无一处是 MAE；其中 2 处是 `viscosity_v02.csv` 的**实测黏度** 0.1223 Pa·s ⇒ 计划标「未核」成立 |
| 7 | HOMO MAE 0.304 / LUMO MAE 0.350 | 错 | **确认为错**：仓内 HOMO **0.17662467232470583** eV、LUMO **0.24935401611452185** eV；且 LUMO 降级由 r = **0.7349044734023142** < 0.80 触发、**不是** MAE |
|
**读数三 · ε ≥ 60 名册（`dielectric_v03.csv` 全表 246 行，按阈值过滤）**
实测恰 **9 个**，与计划 §W19-5 逐个成员、逐个数值对齐：N-methylacetamide 178.47 / vinylene carbonate 126 / formamide 106.14 / ethylene carbonate 90.5 / 2-hydroxyethylammonium lactate 85.6 / water 78.87 / fluoroethylene carbonate 78.4 / propylene carbonate 64.9 / ethanolammonium nitrate 60.9。
- **不含 NMF**：`N-methylformamide` 在 v03 / v04 全表零命中 ⇒ E4 成立。
- **水是 78.87，不是 80.0**：W17 旧「6 个自缔合质子液」名册的水 80.0 与 v03 的 78.87 不是同一名册，两处数字**不得互引**。
- **v04 同名单**：按同一阈值实测同为这 9 个、数值逐位相同 ⇒ 名册在 v03 → v04 之间未漂移。
|
**读数四 · 修订台账 E1–E6 复核**
- E1（许可出处）：**不可核**。本机没有 Batt-SLM 上游仓库副本（`data/raw/batt/` 只有 `Batt-P30K.h5`），全仓对 `Zhan-Yun` 零命中；本仓自己的 `LICENSE` 版权人是本项目 ⇒ E1 声称的「实测上游 LICENSE 全文」在本机无副本可复现；**不得**用本仓 `LICENSE-DATA.md` 冒充上游许可证据。
- E2（计算级别）：**一致（双侧实测）**。THEMol 侧 `level_of_theory` 逐字为 `GFN2-xTB//B3LYP-D3(BJ)/DZVP (gas phase, single point on the DFT geometry)`；Batt 侧 `unit.dataset_method` 逐字为 `wB97X-V/def2-TZVPPD/SMD(epsilon=18.5)`。
- E3（HOMO / LUMO MAE）：**一致**，见读数二第 7 行。
- E4（9 个 vs 6 个）：**一致**，见读数三。
- E5（76 / 239 逐字命中）：**一致，且已补齐落盘证据**。本机取 `v03_features_baseline_input.csv`（恰 239 行）与 `Batt-SLM.smi` 的 115,756 行做逐字比对，命中 **76 / 239**；同一口径下 v03 全表 246 行命中 83。
- E6（乳酸乙醇铵 85.6）：**一致（正名）** 为 `2-hydroxyethylammonium lactate`；但缩写 `HEAL` **不是仓内术语**（全仓 73 处命中无一指该化合物）⇒ 预注册里若写 `HEAL` 须自带定义。
|
**读数五 · ④-b 追加不一致登记（计划未登记、本机新发现 4 条）**
- **最有问题的一条：§W19-3 的 kinematic 依赖与已执行的 W18 事实矛盾**。计划写「kinematic 存量 214 行（176 ThermoML + 38 其他）仍冻结，待密度配对解冻」。本机实测：`Kinematic viscosity, m2/s` 只有 **86** 行；**214** 的真实出处是 `reports/eta_epsilon_joint_table.md:88` 的**族级排除计数** `kinematic_viscosity_not_dynamic = 214`；而 W18 §28.38 **已经解冻并实测**（176 行 ThermoML kinematic 经 `density_v01` 配对 → 池化 **86** 行，另 90 行多组分延后），三池 MAE `0.17477197208762` / `0.15698877870055475` / `0.15686276760094522`，全部未过 0.15，`verdict = refuted`。⇒ 「214 行仍冻结」是**数级口径混用（族级 214 vs 行级 86）+ 状态过期**的双重问题。
- **§W19-5 失败名单计数错**：实测 `failed_names` 共 4 条 = **3 个**咪唑类 IL + Iron pentacarbonyl（计划写「2 个」）。另 246 − 4 失败 − 1 留出 = 241，与 `sample_count = 234` 差 **7** 行，计划只写「其余过滤」未给数。
- **§W19-1 的「UChicago Box」无证据**：本机抽取 `au5c01628.pdf` 全文（15 页 / 81,744 字符）对 `Box` 零命中，Data Availability Statement 逐字指向 `https://github.com/AmanchukwuLab/ElectrolyteGPT`；（许可半句已核实：页脚 `CC-BY-NC-ND 4.0`）。
- **§W19-3 的 Chemprop 待核项可结案**：`reports/decisions_log.md:432` 逐字为 `10x5 outer folds, mean R2 is 0.237, MAE 7.887, and Spearman 0.665`，对照 v1.0 headline `0.364` ⇒ **0.237 < 0.364 成立**，由「待核」改判**已核**。
|
**判定与边界**
- `verdict`：资产表与 Onsager 读数**高度可复现**（digest 逐位一致、E5 独立复现）；但有 **3 条必须改判/登记**（EDB 归属、HOMO/LUMO MAE 记错、E1 许可出处不可核）+ **4 条追加不一致**（kinematic 矛盾、失败名单计数、UChicago Box、Chemprop 待核结案）。
- **本件不占 shot、不动主记分牌**：`models_fitted = 0`、无任何 R2 / MAE；冻结基线 `0.4091179943351143` 与冻结头条 `0.4766400383507876` 不受影响；累计主记分牌尝试仍为 11）。
- **不可核 = 不可核**：「上游 LFS oid」与「上游仓库 LICENSE」两类本机无副本的声明**不得**在后续章节改写成「已核」；`214`（族级）与 `86`（行级）**不得互引**。
- **不在本章修订 Week 18 判据**：W18-2 端点定义、W18-7 退出判据只能由作者确认后修订，修订即记录。
|
**产物清单**
- `reports/w19_state_audit.md`（23,234 B；sha256 `6deeaab6c32eef511336d02677dac654dfc6c8adf71c30f4b5df81cc3e723e1c`）
- `tests/test_w19_state_audit.py`（3,013 B；sha256 `ef1a4c7c54004adeeef1939335ce1a568cc6899f5f2e0d0be4107b113325d39e`）
|
**数字出处**
- 24,077 / `1ba6a239241200aef9f767c5203bd0c6ad0dc7e02d49eea9594f683d39752899` ← `reports/w19_state_audit.md`（权威输入块）
- 183,771,012 / `587f1490…8d118d`（全值见报告）/ 29,519 / 115,756 / 248,404 / 392 / 128.941261 / 130,844 / 246 / 42,941 / 42,942 / 86 / 47,293 / 239 ← `reports/w19_state_audit.md` 资产表与 ③-b
- 0.17662467232470583 / 0.24935401611452185 / 0.7349044734023142 / 0.1223 / 69 / 18,316 ← `reports/w19_state_audit.md` 转录数字核对表
- 178.47 / 126 / 106.14 / 90.5 / 85.6 / 78.87 / 78.4 / 64.9 / 60.9 ← `reports/w19_state_audit.md` ③-b 名册表
- 214 / 176 / 38 / 0.17477197208762 / 0.15698877870055475 / 0.15686276760094522 / 241 / 234 / 0.237 / 0.364 ← `reports/w19_state_audit.md` ④-b
- 45 条字面量 / digest 钉 ← `tests/test_w19_state_audit.py::MEASURED_LITERALS` / `REPORT_SHA256`
**数字自检**：片段内数值 token 已对 `reports/w19_state_audit.md` + `tests/test_w19_state_audit.py` 逐字回搜（ISO 日期时间戳整段排除、十六进制 digest 不作数值 token）。**推算值 / 运行值 / 外部常量（素材文件搜不到，故不冒充出处）**：`28.46`（节号，任务书逐字指定）；`0.4091179943351143` / `0.4766400383507876`（W18 冻结基线 / 头条常量，出自 Week 17–18 章节，本 lane 素材不含）；`23,234` / `3,013`（两个交付件的**本机 stat 实测字节数**，文件正文不含自身字节数）；`43`（`MEASURED_LITERALS` 的条目数，**本机清点**得出，非文件字面量）。其余全部数值 token 均在本 lane 素材内逐字命中。
|
