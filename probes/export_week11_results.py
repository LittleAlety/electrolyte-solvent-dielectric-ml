"""Export the v1.x temperature-resolved observation work (Week 11)."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from electrolyte_ml.exporting import canonical_text_sha256
from probes.export_results_common import (
    DEFAULT_OUTPUT_ROOT,
    copy_artifacts,
    read_json,
    run_verifiers,
    write_json,
    write_sha256s,
)

WEEK = "week11"

README_TEXT = """# Week 11 交付包（v1.x 温度分辨观测级表 + 分组 CV 判决）

数据血缘: 规范数据集 data/dielectric_v03.csv **未改动**（246 行 × 38 列，
digest `ff2142936e06e04b329b70f8597574f75349e54ce876e9fff81309e6d35ccce4`）；
本轮全部产物为新增文件，v1.0 已发布工件未被触碰。
生成脚本: probes/export_week11_results.py

## 入口
- week11_summary.json - 机器可读摘要（表规模、判决数字、泄漏标尺、闸门退出码）
- verification.json - verifier 退出码与报告
- dielectric_observations_v11.csv - 观测级表本体（1,630 行）
- dielectric_observations_v11_summary.json - 表的构建摘要
- dielectric_observations_v11plus.csv - 合并观测表本体（2,065 行 / 153 化合物，频率闸并入）
- dielectric_observations_v11plus_summary.json - 合并表的构建摘要
- dielectric_observations_grouped_benchmark_summary.json - 分组基准全文
- artifacts/ - 基准明细（folds / repeats / predictions）与曲线
- dielectric_observations_v11_benchmark.md - 判决报告全文
- dielectric_compound_coverage_curve.md / .csv / .png - 化合物覆盖学习曲线
- openalex_oa_candidates.csv / openalex_unpaywall_sweep_summary.json / g1plus_oa_sweep_round6.md
  - W13 扫漏的候选清单、预算账与报告
- SHA256SUMS - 本目录全部文件的清单

## 本周做了什么（W11 下半周 + W12）
打开 v0.3 入库时的 293.15–303.15 K 温度闸门，把本地 ThermoML 抽取里**早已解析过、
又被丢掉**的温度点重新取回：`data/processed/dielectric_raw.csv` 的 11,646 条观测中，
纯组分 + 零频 + 液相的有 **1,630 条 / 103 化合物 / 35 个 DOI / 223.02–406.64 K**，
其中 **979 条**落在申报窗口之外。逐条计数丢弃原因（混合物 8,824 / 变频 1,109 / 非液相 83），
不静默去重（7 条完全重复保留并打标）。

## 判决（负结果）
同一张表、同一 XGBoost 配置、同一组表示，只换切分口径：

| 口径 | 行数 | 化合物 | Hybrid R² | Hybrid MAE |
| --- | ---: | ---: | ---: | ---: |
| grouped（按 InChIKey） | 1,594 | 98 | **0.160** | 10.29 |
| grouped_single_row（同协议，每化合物 1 行） | 98 | 98 | **0.186** | 10.59 |
| random_row（仅作泄漏参照） | 1,594 | 98 | 0.934 | 2.39 |
| v1.0 冻结基准 | 236 | 236 | 0.364 | 6.69 |

- 原判据 grouped R² ≥ 0.364 **未过**；把 1 行扩到 1,594 行，R² 反而从 0.186 掉到 0.160。
- **泄漏被量化**：`random_row` 的 50 个折**全部**有化合物跨训练/测试（单折最多 62 个），
  grouped 为 0。同一份数据上 0.160 与 0.934 的落差全部由泄漏贡献。
- **机制**：1,630 行 ε 的方差 **97.7% 在化合物之间、2.3% 在化合物内部（温度）**。
- **路线修正**：温度表定位为证据覆盖与 schema 增益（观测级溯源、温度带、冲突标注），
  不再作为"加温度提精度"的理由；v1.x 的杠杆改为**化合物覆盖**。

## W13 扫漏（OpenAlex + Unpaywall，round 6）
6 个查询族 / 120 篇作品 / 37 个 OA 候选 / 126 次请求（预算 200）/ 0 失败，联网实测成功。
**诚实降级**：21 个 `new_leads` 是高估——氟代醚族大半是 Novec 池沸腾传热论文
（"dielectric" 只是形容词），真正与电池溶剂相关的约 6–9 条；每族只读第 1 页
（共 1,305 条匹配），是浅扫不是穷举；**未从任何全文读出 ε(T) 数值**，37 行全是线索。

## 迭代 2：把"训练方向"从口号变成判决

同一批 98 个化合物、同一 grouped by InChIKey 协议、只换温度带
（`probes/dielectric_band_ablation.py`）：

| 口径 | 行数 | 化合物 | Hybrid R2 | Hybrid MAE |
| --- | ---: | ---: | ---: | ---: |
| 仅室温带 band_room_only | 457 | 97 | **0.409** | 8.04 |
| 室温+扩展带 | 644 | 98 | 0.212 | 9.84 |
| train_all_test_core | 1,594 | 98 | 0.198 | 9.81 |
| 每化合物 1 行（近 298.15 K） | 98 | 98 | 0.186 | 10.59 |
| 全带（W12 原口径） | 1,594 | 98 | 0.160 | 10.29 |

- 窗口外行**两侧都是负贡献**：加训练侧 -0.0136、加测试侧 -0.0378（测试侧占 74%）。
- "多温度点当训练正则"这条机制被否证：加进去 Spearman 也从 0.606 掉到 0.599。
- `band_room_only` 是五个口径里最好的，但它的被打分池与 v1.0 的 236 化合物池**不配对**
  （池方差 335.64 vs 580.30），所以**本包不宣称"室温多观测超过了 v1.0 的 0.364"**。

## 迭代 2：本地资产的第二扇闸——频率

`build_dielectric_observations` 的门是"纯组分 + **零频** + 液相"。对本地 `dielectric_raw.csv`
逐层取证后发现：

- raw 全表 175 个不同化合物（其中纯组分 160 个），零频闸只过 103 个；**57 个纯组分在零频行里完全不存在**
  （液相口径 53 个），频率跨 1 kHz-340 MHz（本次放行档位：主闸 ≤1 MHz 共 136 行、扩展闸 1-3 MHz 共 299 行），低频极限对纯液体就是静态值。
- **混合物嫌疑被排除**：被丢的 8,824 行 `component_count` 只有 2 和 3，没有一个纯组分藏在里面，
  这条闸是干净的、不用回头。
- 频率上限只能"界定"不能"认证"：同源配对 **0/136**，所以先量噪声地板（949 对，中位数 0.615%），
  再看各频率档。1 MHz 档 |偏差| 中位数 **0.201%**、28% 逐位精确复现；0.01 MHz 档最弱（-3.0%）。
- 放行 **435 行 / 50 化合物**（主闸 1 MHz + 扩展闸 3 MHz），温度跨度 218-348 K；
  其中 **39 个不在名录**，另有 **11 个名录成员 `model_ready=true` 却在 v11 表里一行都没有**。

## 迭代 2：配对判决——窗口外的行不进训练面

`probes/dielectric_room_window_paired.py` 把折与被打分池锁死后只换训练面（同池方差 335.6435）：

| 训练池 | Hybrid R2 | MAE | Spearman | dR2 |
| --- | ---: | ---: | ---: | ---: |
| 仅室温带（457 行） | **0.4091** | 8.0407 | 0.7763 | - |
| + 扩展带（644 行） | 0.3625 | 8.3202 | 0.7721 | **-0.0466** |
| + 窗口外（1,594 行） | 0.3230 | 8.5436 | 0.7792 | **-0.0395** |

合计 **-0.0861**，`train_all_test_room` 的 0.3230 **跌破 v1.0 的 0.3636**。
MAE 同向变差而 Spearman 几乎不动，是典型的"压向均值"。

配对版 v1.0 对账（锁在 v1.0 236 池交 v1.1 池 = 98 个化合物，其中 97 个有室温行）：
`cohort_v10_frozen` 0.2158 → `cohort_single_row` 0.2198 → `cohort_room_train_single_test` **0.2299**
（只加训练行 **+0.0101**，MAE 反向 +0.2193）→ `cohort_room_rows` 0.4091
（+0.1792，**这一跳是打分池从 97 行变 457 行的口径差，不是能力差**）。

**合并判决**：0.3636 到 0.2158 的缺口是**化合物覆盖 236 到 97**，不是温度维度；
窗口内同化合物的更多观测可以进训练面但只值 +0.0101；窗口外的行既不进训练面也不进评估面。

## 迭代 2：外部来源的止损结论

| 来源 | 实测结果 |
| --- | --- |
| NIST ThermoML 在线 API | **0 个新化合物**：在线严格集（103）与本地 103 **集合全等**，双向差集为空 |
| 本地损坏 tgz | 不可救：189,433,115 字节、95.6% 零填充、只有一个 8 MiB 块；旧 `.tgz/.bib/_Data.xml` 全部 404 |
| ILThermo | ε 有、温度序列没有：纯化合物 **1/109** 数据集随温度变化；58 个新名字只解析出 **29 个 InChIKey**，且 76/76 全是离子液体 |
| OpenAlex/Unpaywall（W13） | 37 条全是线索；AL Round 3 逐条取数 **ε 数值 0 个**（出版商侧 10x403 + 6 落地页，另 2x403 在仓储侧） |

**外部"零频 ε"这扇门已经关上了**——不是我们找不到，而是本地缓存本就是 NIST 该口径的完整快照。
v1.x 的增量只能来自（a）本地频率闸、（b）离子液体家族（需 v0.4 立项）、（c）机构代理取全文。

## 迭代 2：覆盖率配对判决（本轮唯一的正结果）

`probes/dielectric_coverage_paired_benchmark.py` 把折与被打分池锁死后，只把训练面从
`paired_base` 扩到 `paired_plus_coverage`（把频率闸新增的 50 个化合物的室温行加进训练）：

| 口径 | 训练池 | Hybrid R2 | MAE | Spearman |
| --- | ---: | ---: | ---: | ---: |
| paired_base | 457 行 / 97 化合物 | 0.4091 | 8.04 | 0.7763 |
| **paired_plus_coverage** | 584 行 / 147 化合物 | **0.5332** | **6.50** | **0.8844** |
| paired_plus_new_xtb | 561 行 / 136 化合物 | 0.5454 | 6.69 | 0.8531 |
| paired_plus_v03_block | 480 行 / 108 化合物 | 0.4302 | 7.71 | 0.8482 |

**dR2 = +0.1241、dMAE = -1.5362、dSpearman = +0.1081，decision = "helps"。**
拆分：新跑的 **39 个 xTB 化合物贡献 +0.1363**，存量 **v03 块 11 个贡献 +0.0211**。
每折真实多训练 **127 行**（50 折 min=max=127，合计 6,350 行），训练池化合物 97 -> 147。
`extended_pool_room` 0.4783 是同期不同池的参照；`extended_pool_room_random_row` 0.6748 **只是泄漏标尺**。

独立对抗审计（`probes/dielectric_coverage_paired_benchmark_audit.py`，5 项全 confirmed、0 项被证伪）：
- **预测确实变了**：3 个表示 × 50 格 × 457 行 = **13,710 个打分格，13,706 格逐位不同（99.97%）**
  （Morgan 与混合表示各 4,570/4,570 全变，Physical 4,566/4,570）；
- **多的料确实来自新化合物**：新增 127 行 = 50 个低频闸化合物的室温行，
  与被打分池重叠 **0 行**、与 v11 观测表重叠 **0 行**，且新增化合物与被打分化合物交集为空；
- **"+0.1241 只是先验位移"这一替代解释被排除**：新增训练块的目标分布确实偏低
  （均值 12.66 vs 被打分池 21.49，KS p = 2.0e-4），但**秩相关的 Spearman 同步上升**、
  且把收缩方向偏回归掉之后配对增量仍跟着目标偏差走（偏相关 0.566）；
  97 个被打分化合物里 **64 个**平均绝对误差下降、60.3% 的行误差下降；
  ΔMSE 分解为对齐项 -79.14 + 位移惩罚 +37.50 = -41.65。
- **仍未排除（留档）**：新增 127 行来自另一批化合物，其作用可能含**样本量/正则化**成分；
  要彻底分开需要"安慰剂重训 + 第三批表外化合物复现"两次对照，本轮按约定不重训。
  故 +0.1241 只当"**扩大化合物覆盖的收益上界（经审计）**"，不得表述成"新化学被学到了"。

## 迭代 2：源 2 的第二半（α 先验特征）判决 = 零覆盖，不可用

`probes/dielectric_alpha_prior_probe.py`（同折同池、每个特征臂配同宽全 NaN 安慰剂）：

- **覆盖是死结**：NBS 514 系数在 v1.x **室温基准上覆盖 0/97 化合物**（全带 1/98，多温化合物 1/60）；
  只有在 v1.0 的 236 池上才有 **44/236 = 18.6%**。→ 源 2 的"系数作先验特征"在 v1.x 上**无从生效**。
- **泄漏幻觉的第三个量化案例**：把斜率在全表上拟合（leaky）对安慰剂 **+0.0864** 看着很好；
  换成只在训练折内拟合（诚实版）**-0.0641 = hurts**，且测试化合物覆盖率为 0。

## 迭代 2：源 6（DDB 免费检索）关闭

`probes/ddb_free_search_probe.py`（28 次请求 / 3,700,842 字节 / 19x200、4x404、5 次连接被丢弃）：

- 免费层**存在、匿名、可用**（`http://ddbonline.ddbst.com/DDBSearch/onlineddboverview.exe`，无登录），
  但厂商原文：**"This DDB online search does not present any data"**，且**无物性查询面**。
- 它只给"有没有"：乙腈 771 点/115 集/115-623 K、PC 103/30/195-378 K、DMC 36/6/278-353 K、
  水 1569/273/67-823 K、EC 17/10/298-343 K；MDEC 银行纯组分 50 个 / 2,244 点。
- **读出 ε 数值 = 0**、温度数值 = 0、无 CSV/JSON 导出端点 → **净新增可建模化合物 = 0**。
- 纪律披露：该主机约 28% 首连被丢弃（首次成功率 0.722），不重试会把"可达"误判成"不可达"。

## 校验
从那仓根目录运行（scripts/ 不在交付包内，此处同名脚本为副本）:
python scripts/verify_dielectric_observations.py
python scripts/verify_dielectric_observations_v11plus.py
python scripts/verify_dielectric_v03.py
python scripts/verify_export_manifests.py --output-dir <本目录>
"""

ARTIFACTS = (
    ("data/processed/dielectric_observations_v11.csv", "dielectric_observations_v11.csv"),
    (
        "probes/dielectric_observations_v11_summary.json",
        "dielectric_observations_v11_summary.json",
    ),
    (
        "probes/dielectric_observations_grouped_benchmark_summary.json",
        "dielectric_observations_grouped_benchmark_summary.json",
    ),
    (
        "probes/artifacts/dielectric_observations_benchmark_folds.csv",
        "artifacts/dielectric_observations_benchmark_folds.csv",
    ),
    (
        "probes/artifacts/dielectric_observations_benchmark_repeats.csv",
        "artifacts/dielectric_observations_benchmark_repeats.csv",
    ),
    (
        "probes/artifacts/dielectric_observations_benchmark_predictions.csv",
        "artifacts/dielectric_observations_benchmark_predictions.csv",
    ),
    (
        "probes/artifacts/dielectric_compound_coverage_curve.csv",
        "artifacts/dielectric_compound_coverage_curve.csv",
    ),
    (
        "probes/artifacts/dielectric_compound_coverage_curve.png",
        "artifacts/dielectric_compound_coverage_curve.png",
    ),
    ("reports/dielectric_observations_v11_benchmark.md", "dielectric_observations_v11_benchmark.md"),
    ("reports/dielectric_compound_coverage_curve.md", "dielectric_compound_coverage_curve.md"),
    ("scripts/build_dielectric_observations.py", "build_dielectric_observations.py"),
    ("scripts/verify_dielectric_observations.py", "verify_dielectric_observations.py"),
    ("tests/test_build_dielectric_observations.py", "test_build_dielectric_observations.py"),
    (
        "probes/dielectric_observations_grouped_benchmark.py",
        "dielectric_observations_grouped_benchmark.py",
    ),
    (
        "probes/dielectric_compound_coverage_curve.py",
        "dielectric_compound_coverage_curve.py",
    ),
    ("data/processed/openalex_oa_candidates.csv", "openalex_oa_candidates.csv"),
    (
        "probes/openalex_unpaywall_sweep_summary.json",
        "openalex_unpaywall_sweep_summary.json",
    ),
    ("probes/openalex_unpaywall_sweep.py", "openalex_unpaywall_sweep.py"),
    ("tests/test_openalex_unpaywall_sweep.py", "test_openalex_unpaywall_sweep.py"),
    ("reports/g1plus_oa_sweep_round6.md", "g1plus_oa_sweep_round6.md"),
    # W12 follow-up: temperature-band ablation.
    (
        "probes/dielectric_band_ablation_summary.json",
        "dielectric_band_ablation_summary.json",
    ),
    (
        "probes/artifacts/dielectric_band_ablation_folds.csv",
        "artifacts/dielectric_band_ablation_folds.csv",
    ),
    (
        "probes/artifacts/dielectric_band_ablation_repeats.csv",
        "artifacts/dielectric_band_ablation_repeats.csv",
    ),
    (
        "probes/artifacts/dielectric_band_ablation_predictions.csv",
        "artifacts/dielectric_band_ablation_predictions.csv",
    ),
    ("probes/dielectric_band_ablation.py", "dielectric_band_ablation.py"),
    ("tests/test_dielectric_band_ablation.py", "test_dielectric_band_ablation.py"),
    ("reports/dielectric_band_ablation.md", "dielectric_band_ablation.md"),
    (
        "probes/dielectric_room_window_paired_summary.json",
        "dielectric_room_window_paired_summary.json",
    ),
    (
        "probes/artifacts/dielectric_room_window_paired_folds.csv",
        "artifacts/dielectric_room_window_paired_folds.csv",
    ),
    (
        "probes/artifacts/dielectric_room_window_paired_repeats.csv",
        "artifacts/dielectric_room_window_paired_repeats.csv",
    ),
    (
        "probes/artifacts/dielectric_room_window_paired_predictions.csv",
        "artifacts/dielectric_room_window_paired_predictions.csv",
    ),
    (
        "probes/dielectric_room_window_paired.py",
        "dielectric_room_window_paired.py",
    ),
    (
        "tests/test_dielectric_room_window_paired.py",
        "test_dielectric_room_window_paired.py",
    ),
    ("reports/dielectric_room_window_paired.md", "dielectric_room_window_paired.md"),
    # v1.x merged observation table: zero-frequency rows plus the admitted
    # low-frequency rows, with the extra xTB block the coverage benchmark reads.
    (
        "data/processed/dielectric_observations_v11plus.csv",
        "dielectric_observations_v11plus.csv",
    ),
    (
        "probes/dielectric_observations_v11plus_summary.json",
        "dielectric_observations_v11plus_summary.json",
    ),
    (
        "scripts/build_dielectric_observations_v11plus.py",
        "build_dielectric_observations_v11plus.py",
    ),
    (
        "scripts/verify_dielectric_observations_v11plus.py",
        "verify_dielectric_observations_v11plus.py",
    ),
    (
        "tests/test_build_dielectric_observations_v11plus.py",
        "test_build_dielectric_observations_v11plus.py",
    ),
    (
        "data/processed/dielectric_physical_features_v11plus_new.csv",
        "dielectric_physical_features_v11plus_new.csv",
    ),
    ("scripts/prepare_v11plus_xtb_input.py", "prepare_v11plus_xtb_input.py"),
    (
        "probes/dielectric_v11plus_xtb_input_summary.json",
        "dielectric_v11plus_xtb_input_summary.json",
    ),
    # v1.x frequency gate: compounds whose only local rows are frequency dependent.
    (
        "data/processed/dielectric_lowfreq_candidates.csv",
        "dielectric_lowfreq_candidates.csv",
    ),
    (
        "probes/dielectric_lowfreq_gate_summary.json",
        "dielectric_lowfreq_gate_summary.json",
    ),
    ("probes/dielectric_lowfreq_gate_probe.py", "dielectric_lowfreq_gate_probe.py"),
    (
        "tests/test_dielectric_lowfreq_gate_probe.py",
        "test_dielectric_lowfreq_gate_probe.py",
    ),
    ("reports/dielectric_lowfreq_gate.md", "dielectric_lowfreq_gate.md"),
    ("data/processed/dielectric_lowfreq_structures.csv", "dielectric_lowfreq_structures.csv"),
    (
        "probes/dielectric_lowfreq_structures_summary.json",
        "dielectric_lowfreq_structures_summary.json",
    ),
    ("probes/dielectric_lowfreq_structures.py", "dielectric_lowfreq_structures.py"),
    (
        "tests/test_dielectric_lowfreq_structures.py",
        "test_dielectric_lowfreq_structures.py",
    ),
    ("reports/dielectric_lowfreq_structures.md", "dielectric_lowfreq_structures.md"),
    # ThermoML online top-up: the refresh buys zero compounds.
    (
        "probes/thermoml_online_topup_summary.json",
        "thermoml_online_topup_summary.json",
    ),
    ("probes/thermoml_online_topup_probe.py", "thermoml_online_topup_probe.py"),
    ("tests/test_thermoml_online_topup_probe.py", "test_thermoml_online_topup_probe.py"),
    ("reports/thermoml_online_topup_round6.md", "thermoml_online_topup_round6.md"),
    # ILThermo: the probe and the structure resolution that followed it.
    ("probes/ilthermo_probe.py", "ilthermo_probe.py"),
    ("probes/ilthermo_probe_summary.json", "ilthermo_probe_summary.json"),
    ("tests/test_ilthermo_probe.py", "test_ilthermo_probe.py"),
    ("reports/ilthermo_probe.md", "ilthermo_probe.md"),
    ("data/processed/ilthermo_new_compounds.csv", "ilthermo_new_compounds.csv"),
    (
        "probes/ilthermo_structure_resolution_summary.json",
        "ilthermo_structure_resolution_summary.json",
    ),
    ("probes/ilthermo_structure_resolution.py", "ilthermo_structure_resolution.py"),
    (
        "tests/test_ilthermo_structure_resolution.py",
        "test_ilthermo_structure_resolution.py",
    ),
    ("reports/ilthermo_structure_resolution.md", "ilthermo_structure_resolution.md"),
    # W13 AL Round 3 refresh queue.
    ("data/processed/al_round3_candidates.csv", "al_round3_candidates.csv"),
    ("probes/al_round3_summary.json", "al_round3_summary.json"),
    ("probes/al_round3_candidates.py", "al_round3_candidates.py"),
    ("tests/test_al_round3_candidates.py", "test_al_round3_candidates.py"),
    ("reports/al_round3.md", "al_round3.md"),
    # Coverage-paired benchmark: does widening the training material with the
    # newly covered compounds move the frozen room-band score?
    (
        "probes/dielectric_coverage_paired_benchmark_summary.json",
        "dielectric_coverage_paired_benchmark_summary.json",
    ),
    (
        "probes/artifacts/dielectric_coverage_paired_benchmark_folds.csv",
        "artifacts/dielectric_coverage_paired_benchmark_folds.csv",
    ),
    (
        "probes/artifacts/dielectric_coverage_paired_benchmark_repeats.csv",
        "artifacts/dielectric_coverage_paired_benchmark_repeats.csv",
    ),
    (
        "probes/artifacts/dielectric_coverage_paired_benchmark_predictions.csv",
        "artifacts/dielectric_coverage_paired_benchmark_predictions.csv",
    ),
    (
        "probes/dielectric_coverage_paired_benchmark.py",
        "dielectric_coverage_paired_benchmark.py",
    ),
    (
        "tests/test_dielectric_coverage_paired_benchmark.py",
        "test_dielectric_coverage_paired_benchmark.py",
    ),
    (
        "reports/dielectric_coverage_paired_benchmark.md",
        "dielectric_coverage_paired_benchmark.md",
    ),
    # Independent adversarial audit of that benchmark.
    (
        "probes/dielectric_coverage_paired_benchmark_audit_summary.json",
        "dielectric_coverage_paired_benchmark_audit_summary.json",
    ),
    (
        "probes/dielectric_coverage_paired_benchmark_audit.py",
        "dielectric_coverage_paired_benchmark_audit.py",
    ),
    (
        "tests/test_dielectric_coverage_paired_benchmark_audit.py",
        "test_dielectric_coverage_paired_benchmark_audit.py",
    ),
    (
        "reports/dielectric_coverage_paired_benchmark_audit.md",
        "dielectric_coverage_paired_benchmark_audit.md",
    ),
    # NBS 514 alpha coefficients as a prior feature: inert, zero coverage.
    (
        "probes/dielectric_alpha_prior_probe_summary.json",
        "dielectric_alpha_prior_probe_summary.json",
    ),
    ("probes/dielectric_alpha_prior_probe.py", "dielectric_alpha_prior_probe.py"),
    ("tests/test_dielectric_alpha_prior_probe.py", "test_dielectric_alpha_prior_probe.py"),
    ("reports/dielectric_alpha_prior_probe.md", "dielectric_alpha_prior_probe.md"),
    # DDB free online search: coverage metadata only, zero values.
    (
        "probes/ddb_free_search_probe_summary.json",
        "ddb_free_search_probe_summary.json",
    ),
    ("probes/ddb_free_search_probe.py", "ddb_free_search_probe.py"),
    ("tests/test_ddb_free_search_probe.py", "test_ddb_free_search_probe.py"),
    ("reports/ddb_free_search_probe.md", "ddb_free_search_probe.md"),
)

VERIFIERS = (
    "scripts/verify_dielectric_observations.py --json",
    "scripts/verify_dielectric_observations_v11plus.py",
    "scripts/verify_dielectric_v03.py",
)


def _head_commit(source_root: Path) -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=source_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return (completed.stdout or "").strip()


def _hybrid(summary: dict, protocol: str, metric: str = "r2") -> float:
    """Hybrid-representation mean of ``metric`` for one declared protocol.

    A protocol that was asked for but is absent would make the published summary
    silently carry ``null``; a rename is an export bug, so raise instead.
    """

    protocols = summary.get("summary") or {}
    if protocol not in protocols:
        raise KeyError(f"protocol {protocol!r} is not present in the summary")
    node = protocols[protocol].get("Morgan+Physical") or {}
    if metric not in node or "mean" not in node[metric]:
        raise KeyError(f"metric {metric!r} is not present for protocol {protocol!r}")
    return node[metric]["mean"]


def export_results(
    *,
    source_root: Path = REPOSITORY_ROOT,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    overwrite: bool = False,
) -> dict[str, object]:
    week_root = output_root / WEEK
    if week_root.exists() and not overwrite:
        raise FileExistsError(f"refusing to overwrite existing output: {week_root}")
    written = copy_artifacts(source_root, week_root, ARTIFACTS)

    verification = run_verifiers(source_root, VERIFIERS)
    write_json(week_root / "verification.json", verification)

    observations_path = source_root / "data" / "processed" / "dielectric_observations_v11.csv"
    table_summary = read_json(
        source_root / "probes" / "dielectric_observations_v11_summary.json"
    )
    benchmark = read_json(
        source_root / "probes" / "dielectric_observations_grouped_benchmark_summary.json"
    )
    sweep = read_json(
        source_root / "probes" / "openalex_unpaywall_sweep_summary.json"
    )
    band_ablation = read_json(
        source_root / "probes" / "dielectric_band_ablation_summary.json"
    )
    lowfreq = read_json(source_root / "probes" / "dielectric_lowfreq_gate_summary.json")
    lowfreq_structures = read_json(
        source_root / "probes" / "dielectric_lowfreq_structures_summary.json"
    )
    topup = read_json(source_root / "probes" / "thermoml_online_topup_summary.json")
    ilthermo = read_json(
        source_root / "probes" / "ilthermo_structure_resolution_summary.json"
    )
    al_round3 = read_json(source_root / "probes" / "al_round3_summary.json")
    room_window = read_json(
        source_root / "probes" / "dielectric_room_window_paired_summary.json"
    )
    v11plus = read_json(
        source_root / "probes" / "dielectric_observations_v11plus_summary.json"
    )
    coverage_paired = read_json(
        source_root / "probes" / "dielectric_coverage_paired_benchmark_summary.json"
    )
    coverage_audit = read_json(
        source_root / "probes" / "dielectric_coverage_paired_benchmark_audit_summary.json"
    )
    alpha_prior = read_json(
        source_root / "probes" / "dielectric_alpha_prior_probe_summary.json"
    )
    ddb = read_json(source_root / "probes" / "ddb_free_search_probe_summary.json")
    reference = benchmark.get("reference", {}).get("hybrid", {}).get("r2", {}).get("mean")

    write_json(
        week_root / "week11_summary.json",
        {
            "schema_version": "week11_export/v1",
            "week": WEEK,
            "head_commit": _head_commit(source_root),
            "frozen_dataset": {
                "path": "data/dielectric_v03.csv",
                "sha256": table_summary["inputs"]["roster_sha256"],
                "changed": False,
            },
            "observation_table": {
                "path": "data/processed/dielectric_observations_v11.csv",
                "sha256": canonical_text_sha256(observations_path),
                "rows": table_summary["rows"],
                "compounds": table_summary["compounds"],
                "source_dois": table_summary["source_dois"],
                "rows_missing_source_doi": table_summary["rows_missing_source_doi"],
                "temperature_k": table_summary["temperature_k"],
                "band_counts": table_summary["band_counts"],
                "dropped": table_summary["dropped"],
                "structure": table_summary["structure"],
            },
            "verdict": {
                "criterion": "grouped R2 >= 0.364 (the v1.0 headline)",
                "criterion_met": False,
                "grouped_hybrid_r2": _hybrid(benchmark, "grouped"),
                "grouped_single_row_hybrid_r2": _hybrid(benchmark, "grouped_single_row"),
                "random_row_hybrid_r2": _hybrid(benchmark, "random_row"),
                "v1_0_reference_hybrid_r2": reference,
                "modelled_rows": benchmark["rows"],
                "modelled_compounds": benchmark["compounds"],
                "group_leak": benchmark.get("group_leak", {}),
                "conclusion": (
                    "the temperature dimension does not hold at the 0.364 bar; the "
                    "enlarged table is a coverage/schema gain, not an accuracy gain"
                ),
            },
            "w13_sweep": {
                "probe": "probes/openalex_unpaywall_sweep.py",
                "queries": len(sweep.get("queries", [])),
                "works_collected": sweep.get("works_collected"),
                "oa_candidates": sweep.get("oa_candidates"),
                "new_leads": sweep.get("new_leads"),
                "requests_used": sweep.get("requests_used"),
                "request_budget": sweep.get("request_budget"),
                "failures": len(sweep.get("failures", [])),
                "caveat": (
                    "leads only: no permittivity value was read from any full text, and "
                    "the new_leads count is an over-estimate (fluorinated-ether noise)"
                ),
            },
            "next_direction": (
                "compound coverage, not temperature coverage: the v1.0 R2 rests on 236 "
                "compounds while the local ThermoML corpus supports 98-101"
            ),
            "band_ablation": {
                "probe": "probes/dielectric_band_ablation.py",
                "hybrid_r2": {
                    name: _hybrid(band_ablation, name)
                    for name in (
                        "band_room_only",
                        "band_room_extended",
                        "train_all_test_core",
                        "single_row_298",
                        "band_all",
                    )
                },
                "mechanism": band_ablation.get("mechanism", {}),
                "caveat": (
                    "band_room_only is the best of the five protocols, but its scored "
                    "pool is not paired with the v1.0 236-compound pool, so it does not "
                    "license a claim of beating the 0.364 headline"
                ),
            },
            "coverage_extension": {
                "builder": "scripts/build_dielectric_observations_v11plus.py",
                "rows": v11plus["rows"],
                "compounds": v11plus["compounds"],
                "compounds_added_over_v11": v11plus["compounds_added_over_v11"],
                "rows_by_origin": v11plus["rows_by_origin"],
                "compounds_by_origin": v11plus["compounds_by_origin"],
                "origin_overlap_rows": v11plus["origin_overlap_rows"],
                "rows_missing_source_doi": v11plus["rows_missing_source_doi"],
                "smiles_backfilled": v11plus["gate_counters"].get("smiles_backfilled", 0),
                "caveat": (
                    "the merged table adds compounds, not temperature accuracy: the "
                    "out-of-window rows stay in the table for provenance but are excluded "
                    "from the training and scoring faces"
                ),
            },
            "coverage_paired_benchmark": {
                "probe": "probes/dielectric_coverage_paired_benchmark.py",
                "audit": "probes/dielectric_coverage_paired_benchmark_audit.py",
                "scored_rows": coverage_paired["fixed_pool_family"]["protocols"]["paired_base"][
                    "scored_rows"
                ],
                "scored_compounds": coverage_paired["fixed_pool_family"]["protocols"][
                    "paired_base"
                ]["compounds_scored"],
                "folds_are_shared": coverage_paired["fixed_pool_family"]["folds_are_shared"],
                "hybrid_r2": {
                    name: _hybrid(coverage_paired["fixed_pool_family"], name)
                    for name in (
                        "paired_base",
                        "paired_plus_coverage",
                        "paired_plus_new_xtb",
                        "paired_plus_v03_block",
                    )
                },
                "delta_r2": coverage_paired["verdict"]["delta_r2"],
                "delta_mae": coverage_paired["verdict"]["delta_mae"],
                "delta_spearman": coverage_paired["verdict"]["delta_spearman"],
                "decision": coverage_paired["verdict"]["decision"],
                "train_pool_compounds_widened": coverage_paired["fixed_pool_family"][
                    "protocols"
                ]["paired_plus_coverage"]["train_pool_compounds"],
                "extra_train_rows_per_fold": coverage_paired["fixed_pool_family"][
                    "training_expansion"
                ]["paired_plus_coverage"]["extra_rows_fitted_per_fold_mean"],
                "extended_pool_room_hybrid_r2": _hybrid(
                    coverage_paired["extended_pool_family"], "extended_pool_room"
                ),
                "leak_reference_hybrid_r2": _hybrid(
                    coverage_paired["extended_pool_family"],
                    "extended_pool_room_random_row",
                ),
                "audit_verdict": coverage_audit["verdict"],
                "audit_tally": coverage_audit["tally"],
                "statement": coverage_paired["verdict"]["statement"],
                "caveat": (
                    "the leak-reference protocol is reported only to size the leak; the "
                    "conclusion number is the grouped paired_base step"
                ),
            },
            "alpha_prior": {
                "probe": "probes/dielectric_alpha_prior_probe.py",
                "coefficient_coverage_v11_room_band": alpha_prior["coverage"]["v11_room_band"][
                    "coefficient_coverage"
                ],
                "coefficient_coverage_v10_pool": alpha_prior["coverage"]["v10_pool"][
                    "coefficient_coverage"
                ],
                "nbs_alpha_delta_r2_versus_the_placebo": alpha_prior["verdict"][
                    "nbs_alpha_room_delta_r2_versus_the_placebo"
                ],
                "leaky_slope_delta_r2_versus_the_placebo": alpha_prior["verdict"][
                    "leaky_slope_room_delta_r2_versus_the_placebo"
                ],
                "honest_train_only_slope_delta_r2_versus_the_placebo": alpha_prior["verdict"][
                    "honest_train_only_slope_delta_r2_versus_the_placebo"
                ],
                "honest_train_only_slope_classification": alpha_prior["verdict"][
                    "honest_train_only_slope_classification"
                ],
                "statement": (
                    "the NBS 514 coefficients cover none of the v1.x room benchmark, so the "
                    "prior feature is inert there by construction; the compound's own slope "
                    "only looks usable in its leaky form"
                ),
            },
            "ddb_free_search": {
                "probe": "probes/ddb_free_search_probe.py",
                "free_layer": ddb["answers"]["q1_free_layer_exists"]["verdict"],
                "app_has_no_property_query": ddb["answers"]["q1_free_layer_exists"][
                    "app_has_no_property_query"
                ],
                "permittivity_values_read": ddb["answers"][
                    "q2_contains_permittivity_temperature"
                ]["permittivity_values_read"],
                "csv_or_json_export_endpoint_found": ddb["answers"]["q3_machine_readable"][
                    "csv_or_json_export_endpoint_found"
                ],
                "dielectric_bank_pure_components": ddb["answers"]["q4_net_new_compounds"][
                    "dielectric_bank_pure_components"
                ],
                "net_new_compounds": ddb["answers"]["q4_net_new_compounds"][
                    "net_new_compounds"
                ],
                "net_new_compounds_at_coverage_metadata_level": ddb["answers"][
                    "q4_net_new_compounds"
                ]["net_new_compounds_at_coverage_metadata_level"],
                "http_requests": ddb["counts"]["http_requests"],
                "bytes_received": ddb["counts"]["bytes_received"],
                "verdict": ddb["answers"]["q4_net_new_compounds"]["verdict"],
            },
            "room_window_paired": {
                "probe": "probes/dielectric_room_window_paired.py",
                "window_family_hybrid_r2": {
                    name: _hybrid(room_window["window_family"], name)
                    for name in (
                        "band_room_only",
                        "train_core_test_room",
                        "train_all_test_room",
                    )
                },
                "cohort_family_hybrid_r2": {
                    name: _hybrid(room_window["cohort_family"], name)
                    for name in (
                        "cohort_v10_frozen",
                        "cohort_single_row",
                        "cohort_room_train_single_test",
                        "cohort_room_rows",
                    )
                },
                "cohort_intersection_compounds": len(
                    room_window["cohort_family"]["membership"]["shared_compounds"]
                ),
                "cohort_scored_compounds": room_window["cohort_family"]["protocols"][
                    "cohort_v10_frozen"
                ]["compounds_scored"],
                "window_train_chain": room_window["window_family"]["chain"],
                "verdict": (
                    "out-of-window rows must not enter the training face (paired -0.0861, "
                    "and widening to every row drops below the v1.0 headline); extra "
                    "in-window observations of an already covered compound are worth only "
                    "+0.0101 and move MAE the wrong way"
                ),
            },
            "frequency_gate": {
                "probe": "probes/dielectric_lowfreq_gate_probe.py",
                "primary_cap_mhz": lowfreq["gate_decision"]["primary_cap_mhz"],
                "extended_cap_mhz": lowfreq["gate_decision"]["extended_cap_mhz"],
                "frequency_only_compounds": lowfreq["frequency_inventory"][
                    "frequency_only_compounds"
                ],
                "accepted_rows": lowfreq["candidates"]["accepted_rows"],
                "accepted_compounds": lowfreq["candidates"]["accepted_compounds"],
                "accepted_new_compounds": lowfreq["candidates"]["accepted_new_compounds"],
                "noise_floor": lowfreq["bias_check"]["noise_floor"],
                "same_source_pairs": lowfreq["bias_check"]["same_source_pairs"],
            },
            "frequency_gate_structures": {
                "probe": "probes/dielectric_lowfreq_structures.py",
                "structurally_complete": lowfreq_structures["resolution"][
                    "n_structurally_complete"
                ],
                "inchikey_roundtrip_match": lowfreq_structures["identity_checks"][
                    "inchikey_roundtrip_match"
                ],
                "needs_xtb": lowfreq_structures["coverage"]["n_needs_xtb"],
                "with_frozen_features": lowfreq_structures["coverage"][
                    "n_with_frozen_features"
                ],
                "v11_absence_reasons": lowfreq_structures["v11_absence"]["reason_counts"],
            },
            "thermoml_online_topup": {
                "probe": "probes/thermoml_online_topup_probe.py",
                "archive_verdict": topup["local_archive"]["classification"]["verdict"],
                "records_online": topup["online"]["total_records_online"],
                "new_keys_with_zero_frequency_epsilon": topup["coverage"][
                    "new_keys_with_zero_frequency_epsilon"
                ],
                "statement": topup["headline"]["statement"],
            },
            "ilthermo": {
                "probe": "probes/ilthermo_structure_resolution.py",
                "resolved_new_compounds": ilthermo["resolution"]["resolved_new_compounds"],
                "resolved_rate": ilthermo["resolution"]["resolved_rate_of_queried"],
                "compounds_with_temperature_series": ilthermo["temperature"][
                    "n_compounds_with_temperature_series"
                ],
                "verdict": ilthermo["temperature"]["verdict"],
            },
            "al_round3": {
                "probe": "probes/al_round3_candidates.py",
                "leads": al_round3["lead_count"],
                "dispositions": al_round3["disposition_counts"],
                "value_status": al_round3["value_status_counts"],
                "resolved_compounds_new": al_round3["compounds"]["unique_new"],
            },
            "gates": {
                "pytest": "see verification.json",
                "ruff": "checked outside this export",
            },
            "verification": verification["passed"],
        },
    )
    (week_root / "README.md").write_text(README_TEXT, encoding="utf-8", newline="\n")
    written.append("README.md")
    write_sha256s(week_root)
    return {
        "week": WEEK,
        "output": str(week_root),
        "written_count": len(written),
        "verification_passed": verification["passed"],
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    result = export_results(output_root=args.output_root, overwrite=args.overwrite)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["verification_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
