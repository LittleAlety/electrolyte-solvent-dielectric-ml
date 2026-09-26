# Uni-Mol 微调探针规格（v2.0 缓冲项）—— 定稿报告

**日期**：2026-09-26
**范围**：执行手册附录 AA-5 的「缓冲」项、附录 Y 的 D7、附录 X 杠杆 6 修订、附录 O-4。
**机读规格**：probes/unimol_probe_spec_prereg.json
**规格 sha256**：40ba1d6f2c89e0339541d8674782d3b80dd91c8a77b12c229fd8cf4cbd132857
**独立校验器**：probes/verify_unimol_probe_spec.py --check
**单测**：tests/test_unimol_probe_spec.py

**一句话**：本轮只把规格定稿，**不跑任何模型、不声称任何 R²**；规格里每个数字要么是仓库内实测（带路径与行数），要么是手册转述的 KPI SI 数值（带出处）。构象数的来源冲突（10 vs 11）**并列登记、不静默消解**。

---

## 一、本轮范围与纪律

- 预注册文本先锁后跑：locked_at_utc = 2026-09-26T09:14:46Z，status = locked_before_run。
- 本轮不训练、不微调、不推理；shots_this_round = 0；r2_claimed_this_round = false。
- 只写四个新文件（本报告、机读规格、单测、校验器）；不写 reports/decisions_log.md、不改手册、不写 paper/*、不动任何其它 *_prereg.json、不碰 v1.0 已发布工件与六件冻结件、不写 data/ 下的文件、不引用或复用 Reaxys 受限数值。

## 二、输入：现有 xTB 构象产物到底在哪（仓库查证）

查证入口：probes/dielectric_xtb_full_table_migration.py、src/electrolyte_ml/xtb_features.py 与 xtb_runner.py、scripts/run_xtb_physical_features.py、data/processed 与 data/interim 下的构象/特征表。

**查到的真实路径（全部为实测）**

| 产物 | 路径 | 实测 | 出处/说明 |
|---|---|---|---|
| 冻结单构象暂存（v1.0 口径，1 构象/化合物） | data/interim/xtb_features | 246 个化合物目录、250 个 input.xyz（245 目录各 1 个 + 1 目录 5 个） | 生成器 src/electrolyte_ml/xtb_features.py:176 generate_3d_xyz；脚本默认工作目录 scripts/run_xtb_physical_features.py:549 |
| v1.x 新增 42 化合物的同配方暂存 | data/interim/xtb_features_v11plus | 42 个化合物目录、42 个 input.xyz | 同配方 |
| **唯一的多构象集合**（v0.4 迁移轮） | data/interim/xtb_conformer_migration | 276 个化合物目录、2198 个 input.xyz；每化合物构象数直方图 {8: 274, 5: 1, 1: 1} | probes/dielectric_xtb_full_table_migration.py:108 MAX_CONFORMERS = 8；:92 WORK_DIR；:962 构象种子 = 42 + 名册序 |
| 逐化合物构象记账（随仓库分发） | probes/artifacts/dielectric_xtb_full_table_migration_conformers.csv | 276 行 | 列含 n_conformers / force_field / dipole_D_frozen / dipole_D_conformer_mean |
| 耐久 xTB 特征表（tracked） | data/processed/dielectric_physical_features_v03.csv（241 行，sha256 b36d3439…）与 data/processed/dielectric_physical_features_v11plus_new.csv（42 行，sha256 661df4f8…） | 见左 | digest 出处 probes/dielectric_xtb_full_table_migration_summary.json inputs.* |

**关键事实（决定了 Uni-Mol 输入怎么接）**

1. 现有 xTB 构象**不是**一个以 InChIKey 为键、随仓库分发的耐久系综；它们是 **data/interim/ 下的可再生暂存**。依据：根 .gitignore 的 data/interim/* 一行只放行少数文件，本三个目录都不在放行清单内。
2. 全仓扫描（排除 .git 与**全部虚拟环境目录**：.venv、.venv-chemprop、site-packages 等）后缀普查：.xyz 4435、.mol 3298、.npz 3，**.sdf / .lmdb / .pkl 均为 0**（若只排 `.venv/` 而漏排 `.venv-chemprop`，会漏进 9 个 .sdf 与 23 个 .pkl 的 vendor 命中）。且每个 .xyz 与 .mol 都在 data/interim 之下。
3. 因此「现有 xTB 构象输入」在仓库内的**唯一可行读法**是：以 data/interim/xtb_conformer_migration/<InChIKey>/conf<N>/input.xyz 作为几何来源，或从 SMILES 用 generate_3d_xyz 重算；两者都不随仓库分发。

**待建（查不到或不存在的，照实写「待建」并说明依据）**

- RDKit 10 构象系综：**待建**。仓库最大系综是 8 构象（MAX_CONFORMERS = 8），冻结管线 1 构象/化合物；10 这个数来自 KPI SI 转述（手册行 1517），不是本仓口径。
- LMDB 构象存储：**待建**。全仓零命中（按上条同一排除口径，即排除 .git 与全部虚拟环境目录），且 Python 环境未安装 lmdb 包。
- Uni-Mol 预训练权重与运行时（torch / unimol）：**待建**。解释器 .venv/Scripts/python.exe（Python 3.12.14）中二者 importlib.util.find_spec 均为 None；pyproject.toml 依赖表也没有它们。
- 以 InChIKey 为键的耐久系综产物：**待建**（现有产物均为暂存，唯一 tracked 的构象级产物是统计量 CSV）。

**未查到**

- 任何随仓库分发的单分子 .xyz 构象文件：**未查到**（4435 个 .xyz 全在被忽略的 data/interim 之下）。

## 三、超参照抄 KPI（手册附录 AA-3 第 2 条）

**出处标注规则**：以下每一项的 provenance_kind 都是 **KPI_SI_via_manual**（KPI 论文 SI 经手册转述），our_measurement = false。**禁止**把它们写成「本项目的标定」。

| 项 | 值 | 出处 |
|---|---|---|
| 构象数 | RDKit 10 构象 | 手册附录 AA-3 第 2 条（快照 tests/fixtures/manual_appendix_j_snapshot.md 行 1517） |
| 构象存储 | LMDB | 同上 |
| 优化器 | Adam | 同上 |
| 损失 | smooth MAE（smooth L1） | 同上 |
| batch size | 32 | 同上 |
| epoch 上限 | ≤ 500 | 同上 |
| early stop patience | 20 | 同上 |
| 学习率 | 1e-4 | 同上 |
| 学习率调度 | 多项式衰减 | 同上 |

**明确不抄的**：评估协议。KPI 用随机 8:1:1 + 4 折 CV（手册附录 Y-2 第 2 条，快照行 1408），本项目不得移植（见第七节）。另：手册附录 N-3（快照行 753）写「冻结主干 + 236 行微调」，KPI 原文的微调深度未在手册转述中写明，本条按手册口径执行。

**冷静剂**：KPI 目标是 MP/BP/FP（相变温度，原子数/键型主导，R² 0.974/0.990/0.986），本项目目标是 ε（集体极化）。超参可抄，「照抄超参就能拿到 0.99」不可推（手册附录 Y-2，快照行 1405-1409）。

## 四、照实登记的来源冲突：11 构象 vs RDKit 10 构象

| claim id | 说法 | 出处 | 行号 |
|---|---|---|---|
| claim_y1_11_conformers | 「+ 11 构象输入」 | 手册附录 Y-1（KPI 论文要点速查） | 1400 |
| claim_d7_11_conformers | 「SHAP top-K 纯度 + 可学习流量 + 11 构象」 | 手册附录 Y-3 D7 | 1418 |
| claim_aa3_rdkit_10_conformers | 「RDKit 10 构象 + LMDB」 | 手册附录 AA-3 第 2 条（KPI SI 超参） | 1517 |

**处理方式**：不择一静默消解。两个数并列写进机读规格的 conformer_count_claims 数组（各带出处路径与行号），冲突状态 = unresolved，no_silent_resolution = true。单测会把手册该行**读回来**，确认它确实写着这两个数（tests/test_unimol_probe_spec.py::test_the_conflicting_claims_quote_the_manual_lines_verbatim）。

**可能解释（全部标「未证实」，不得当结论引用）**

1. 10 个 RDKit 构象 + 1 个 xTB 构象 = 11 —— 附录 AA-3 记的是 RDKit 那一半，附录 Y 记的是拼进模型的全部输入。**未证实**：手册与仓库内都没有 KPI SI 的构象拼装清单，我方也没有十构象产物可比对（仓库最大系综是 8 构象）。
2. 两个数出自 KPI SI 的不同小节（一处写采样数、一处写喂进模型的输入数），手册转述时未对齐。**未证实**：本地只有手册转述，没有 SI 原文可逐节核对。
3. 其中之一是转述笔误。**未证实**：仓库内无法证伪或证实；登记为不确定性，不改写任何一处原文。

**跑批前置要求**：跑批前必须把构象数定成一个可执行值，并把「它来自哪一条 claim」写进跑批预注册；在此之前数据加载器必须把构象数当参数，**不得硬编码 10 或 11**。

## 五、知识控制器（D7）与列绑定纪律

**机制**（手册附录 Y-1 行 1400 / Y-3 D7 行 1418；交叉映射 reports/kpi_framework_mapping.md）

- **纯度控制器** = 拼入表征的知识向量维数 top-K，K 由 SHAP top-K 决定。
- **流量控制器** = 可学习嵌入比例。

**泄漏纪律（比 KPI 更严）**：SHAP 排序必须在**每一折的训练侧内部**做（per-fold train-side ranking）。KPI 的排序是在全量数据集上做的再拿去训练；这一点我们不抄（reports/kpi_framework_mapping.md §1.1 已写明「它的做法有泄漏风险，我们不能照抄」）。

**本仓可复用的知识向量候选**：probes/dielectric_knowledge_purity_sweep.py:132 的 KNOWLEDGE_POOL，10 维（donor_count、acceptor_count、has_1_donor、has_2_donors、has_3plus_donors、donor_acceptor_pair_density、ring_count、double_bond_count、rotatable_bond_count、heteroatom_over_carbon）。其顺序**不是不变量**。

**与手册 AC-6 / §25「杠杆 9 洗错列」缺陷的关系（必须写明）**

缺陷原文口径：probes/dielectric_knowledge_purity_sweep.py:560 构造 full = hstack([frozen_physical, knowledge])（物理块在前），:565 把 columns=KNOWLEDGE_POOL 递给 permutation_importance，而该函数在 :307 用 enumerate(columns) 从 position 0 起洗列 —— 于是被洗的是 full[:, 0..K-1]（**物理块前 K 列**），**十个知识池名字只是贴在这些物理列上的标签**。后果：k=2/4/6 的扫描没有测到它想测的东西；k=10 的选择集不受影响（十名全取），但其列序由破损排序决定，而 XGB_PARAMS 含 colsample_bytree=0.8，拟合依赖列序，故 **k=10 的列序与读数都不是不变量**。

出处：手册附录 AC-6(b)（快照行 1683）、附录 AD-3（快照行 1726）、reports/decisions_log.md §24.6(b)（行 3791）、§25.2/§25.3（行 3834、3851）。三序列读数 spread = 0.007080802985126922（§25.3，行 3857）。

**落到本探针规格的硬纪律**：

> **知识向量的列序必须是显式绑定的**，不得让标签位置决定语义。

具体要求：① 存在显式 (column_index -> feature_name) 映射对象；② K 维选择只按该映射取列，禁止用 position/enumerate 从零起推断；③ 对选定列做绑定自检（无操作重排后拟合结果逐位不变）。禁止：把知识池名字直接当列索引、用列表位置决定某维语义、在测试折上做 SHAP 排序或列选择。

## 六、枪毙线（D7 原文口径）与 236 表的核实

**枪毙线原文**：「236 样本打不过 hybrid XGBoost 即停，记负结果」（手册附录 Y-3 D7，快照行 1418；旁证 X-3 杠杆 6，行 1365：「236 样本微调高风险，失败记负结果」）。动作 = 即停 + 记负结果，不得事后放宽。

**236 指的是哪张表（我方核到）**：**v1.0 冻结的 236 行 / 236 化合物拟合池**，即 headline R² 0.364 的同一张表。磁盘上有两种物化形式，二者是**同一个化合物集合**：

| 物化形式 | 路径 | 行数 | digest |
|---|---|---|---|
| 冻结池 CSV | probes/l3_stage1_pilot_pool.csv | 236（共 237 行含表头） | b838febbca4d65975d1820ae9275215288968979b78756611cb031eb7c408b18 |
| 从冻结数据集导出 | data/dielectric_v03.csv（246 行）中 model_ready=true 的 240 行 − 4 个 xTB 特征失败行 | 240 − 4 = 236 | ff2142936e06e04b329b70f8597574f75349e54ce876e9fff81309e6d35ccce4 |

- 240 − 4 = 236 的证据：probes/v032_ablation_summary.json（compound_count = 236、source_count = 245、excluded_count = 4、failed_physical_feature_count = 4、withheld_not_model_ready_count = 1）；tests/test_xtb_fragment_geometry_defect.py:68-77；paper/technical_validation.md:225「0.364 / 6.686 / 0.828, on 236 fitted rows」。
- 4 个特征失败键：GSGLHYXFTXGIAQ-UHFFFAOYSA-M、IXQYBUDWDLYNMA-UHFFFAOYSA-N、JWFPQAXAGSAKRF-UHFFFAOYSA-N、FYOFOKCECDGJBF-UHFFFAOYSA-N（均为多片段分子，xTB 起始几何缺陷导致 SCF 不收敛）。
- **集合相等已核**：{pilot pool 的 236 个 InChIKey} == {dielectric_v03 model_ready 键} − {4 个失败键}，对称差 = 0。

**对照物**：冻结 v1.0 超参的 hybrid（Morgan+Physical 等权集成）XGBRegressor，在 236 池上 R² = 0.3636（发布值四舍五入 0.364；精确重放 0.36357268752900124，见 reports/dielectric_room_window_paired.md:115）。

**未核实/口径待补**：手册原文未点名 236 是哪一张表（本判定是我方用集合相等核到的版本）；D7 的枪毙线**没有给比较算子**（点估计大小还是置信区间不相交）；手册附录 N-3（行 753）的「超 hybrid 的 CV 置信区间才晋升」是相关但不同的一句。跑前必须把该口径定死并写入跑批预注册。

## 七、评估协议：本项目标准（不移植 KPI 随机 8:1:1）

- **观测级** + **GroupKFold by InChIKey** + **每折训练侧排序**，并**断言 group_overlap == 0**。
- **不得**移植 KPI 的随机 8:1:1 + 4 折 CV；KPI 方法若引入，协议一律按本项目标准重做。
- **random_row 只作泄漏参照、永不进判决**（黏度线学费：log10_cP 的 **MAE 0.064 vs 0.175**、**R² 0.93689 vs 0.74813** —— 0.93689 / 0.74813 是 **R²**，MAE 是 0.064 / 0.175；盘上实测见 probes/viscosity_baseline_summary.json 的 random_row / group_key）。
- 出处：手册附录 O-3 第 2 条（行 792）、Y-2 第 2 条（行 1408）、Y-4（行 1426）、AC-7（行 1693）、AD-7（行 1762）。主记分牌的 5 折 × 10 重复 / seed 42 见 reports/decisions_log.md §22.3（行 3584）；本探针的具体折方案在跑批预注册里定死。

## 八、口径隔离

- **主记分牌基线**：0.4091179943351143 —— 457 行 / 97 化合物固定评分池，GroupKFold by InChIKey，50 折，seed 42。
- **辅记分牌 / v1.0 headline**：0.364 —— v1.0 冻结 236 池（枪毙线住在这个池上）。二者池不同，**不得混用、不得互相比较大小**。
- **0.5332 / 0.5454 只许带池定义引用**：「147 化合物训练池在 97 化合物固定评分池上的分组 CV」（手册附录 X-2 行 1350-1351、X-6 行 1390）。
- 本探针若将来跑批：(a) 枪毙线只在 236 池上读；(b) 任何 457 池读数另行标注池定义；(c) 两组数字永不并列成一句比较。

## 九、未查到的项与不确定性登记

1. 构象数冲突（10 vs 11）未证实哪种解释成立；跑前定死取值并注明来源。
2. D7 枪毙线未给比较算子；跑前选定并写死。
3. KPI SI 原文不在仓库内，本地只有手册转述；凡 KPI 侧数值均为二手转述。
4. 目标域不同（ε 集体极化 vs MP/BP/FP 相变温度）；超参照抄不等于精度可迁移。
5. 「236」手册原文未点名表名；本规格判定基于集合相等核验。
6. 现有 xTB 构象产物全部是被 git 忽略的暂存；将来若作输入，须先决定是否固化为随仓库分发的产物。
7. 未查到随仓库分发的单分子 .xyz（见第二节）。

## 十、冻结红线（本轮实测 INTACT）

六件：data/dielectric_v03.csv（ff214293…35ccce4）、probes/l3_stage1_pilot_pool.csv（b838febb…）、probes/l3_backvalidation_prereg.json（77f61a83…）、data/processed/dielectric_observations_v11plus.csv（159b928f80…68a49af9）、probes/dielectric_r2_levers_prereg.json（ab3503c0…）、data/viscosity_v01.csv（12dfa03f…1c5b26）。逐位复现见校验器 red_lines_intact 检查。

## 十一、验收

命令与实测输出见本报告末节「验收实测」。

---

## 验收实测（2026-09-26）

### 1. ruff（两个 .py 文件）

    .\.venv\Scripts\python.exe -m ruff check probes\verify_unimol_probe_spec.py tests\test_unimol_probe_spec.py
    All checks passed!

### 2. pytest

    .\.venv\Scripts\python.exe -m pytest tests\test_unimol_probe_spec.py -q -p no:cacheprovider
    ....................                                                     [100%]
    20 passed in 0.82s

### 3. JSON 自检（规格定义的自校验入口）

    .\.venv\Scripts\python.exe probes\verify_unimol_probe_spec.py --check
    [PASS] lock / scope_no_model / deliverables / red_line_count / red_lines_intact
    [PASS] pilot_pool_rows / pilot_pool_digest / dataset_rows / model_ready_rows
    [PASS] fit_set_arithmetic / fit_set_identity
    [PASS] artifact_frozen_single_conformer_scratch / artifact_v11plus_new_conformer_scratch
    [PASS] artifact_multi_conformer_scratch_v04 / artifact_conformer_accounting
    [PASS] conflict_both_claims / conflict_unresolved / conflict_explanation_registered
    [PASS] kpi_hyperparameter_provenance / kpi_source_pinned
    [PASS] protocol_project_standard / protocol_group_overlap / protocol_kpi_split_barred
    [PASS] scoreboard_main / scoreboard_headline_separated / scoreboard_pool_definitions
    [PASS] knowledge_controller / column_binding / kill_line / file_hygiene
    [PASS] manual_citations_in_range / manual_citations_verbatim / random_row_mae_r2_from_disk
    [PASS] report_declares_spec_digest
    checks=34 passed=34 skipped=0 failed=0
    spec sha256=40ba1d6f2c89e0339541d8674782d3b80dd91c8a77b12c229fd8cf4cbd132857
    PASS: []

### 4. 变异测试（临时改一处期望值 → 变红 → 立即还原 → 逐字相同）

把机读规格里 KPI 超参 batch_size 的 32 临时改成 33（其余字节不动）。

首跑（当时为规格初版：测试 20 条、verifier 30 项、摘要钉只查「sha 前 16 位出现于报告」）：

    pytest: 2 failed, 18 passed
      FAILED test_kpi_hyperparameters_are_attributed_not_measured
      FAILED test_independent_verifier_passes
    verify --check: checks=30 passed=29 failed=1  FAIL: ['kpi_hyperparameter_provenance']
    spec sha256（变异态）=139ea49f9c8df59737458d56f1e843738d3010fd9b47d435d92f3f45fde3f393
    spec sha256（还原后）=d767893cc3b5…1a1013（规格初版值）

勘误：本节原记「pytest: 3 failed, 17 passed」有误，实为 **2 failed, 18 passed**；当时
test_spec_digest_is_pinned_in_the_report 是 PASSED —— 因为报告正文自己印了变异 sha，
弱断言「sha 前 16 位出现于报告任意位置」被自身满足，该钉对「被文档化的那次变异」等于永久失效。
根因已修：断言改为「报告头部声明的 sha == 盘上规格 sha」的等式断言（见复跑）。

复跑（本轮，规格含 corrections 块 41443 B、verifier 34 项、测试 22 条）：

    pytest: 3 failed, 19 passed
      FAILED test_kpi_hyperparameters_are_attributed_not_measured
      FAILED test_independent_verifier_passes
      FAILED test_spec_digest_is_pinned_in_the_report
    verify --check: checks=34 passed=32 failed=2  FAIL: ['kpi_hyperparameter_provenance', 'report_declares_spec_digest']
    spec sha256（变异态）=5234f7972c86c817765406be4bfab3116ab118abed8babb4837eceb00c3d5589

还原后：

    字节级相同（byte_identical = true）
    spec sha256=40ba1d6f2c89e0339541d8674782d3b80dd91c8a77b12c229fd8cf4cbd132857（与改动前逐字相同）
    pytest: 22 passed / verify --check: checks=34 passed=34 failed=0

### 5. 本轮写集

本轮只新建四个文件：probes/unimol_probe_spec_prereg.json、reports/unimol_probe_spec.md、tests/test_unimol_probe_spec.py、probes/verify_unimol_probe_spec.py。没有改任何禁止文件（decisions_log.md、手册快照、paper/*、其它 *_prereg.json、data/ 下任何文件、六件冻结件、v1.0 已发布工件）。
