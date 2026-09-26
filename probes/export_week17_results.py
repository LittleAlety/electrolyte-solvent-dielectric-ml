"""Export the Week 17 deliverables (the pivot week: more compounds, more dimensions).

Covers, in one package:

* W17-0/W17-1 -- the two author rulings that unblocked the week, plus the
                 dielectric v0.4 roster patch (the succinonitrile roster gap
                 and the gamma-valerolactone dual-row conflict, never averaged);
* W17-2        -- the thin-family backfill queue.  This is a PLAN, not a
                 measurement: `reaxys_queries_executed == 0` and no Reaxys
                 value entered `data/`;
* W17-4        -- density_v01, the first missing dimension, plus the
                 kinematic-viscosity unfreeze gate (176/176 rows matched);
* W17-5        -- the liquid-window hard gate (314 keys, 77 blocked, EC caught);
* W17-6        -- the Li+ coordination block promoted to production features,
                 and the two-lever merge re-run;
* W17-7        -- the epsilon-eta Walden coupling and the donor-number audit;
* W17-9        -- the four-channel coverage board (epsilon / eta / HOMO-LUMO /
                 redox), which is where the HOMO/LUMO status is re-read.

Week 17 quotes exactly one R2 figure, and it is the merge re-run's delta, not a
new lever.  The frozen main scoreboard 0.4091179943351143 is reproduced to
`abs_delta = 0.0` and is never quoted as a gain by any lane.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from probes.export_results_common import (
    DEFAULT_OUTPUT_ROOT,
    copy_artifacts,
    read_json,
    run_verifiers,
    write_json,
    write_sha256s,
)

WEEK = "week17"

FROZEN_RED_LINES = {
    "data/dielectric_v03.csv": "ff2142936e06e04b329b70f8597574f75349e54ce876e9fff81309e6d35ccce4",
    "probes/l3_stage1_pilot_pool.csv": "b838febbca4d65975d1820ae9275215288968979b78756611cb031eb7c408b18",
    "probes/l3_backvalidation_prereg.json": "77f61a83b82de346292ff055c4f4c52003bccb6bfc98bf11813048abc6f0db98",
    "data/processed/dielectric_observations_v11plus.csv": "159b928f800a55969963da275ed05c30ce8a19cffc48353a9c490eec68a49af9",
    "probes/dielectric_r2_levers_prereg.json": "ab3503c037f05ac398b3c0c59d0e4845943d49fa5a5349fa46b8944f2bc1bdaa",
    "data/viscosity_v01.csv": "12dfa03f34284c93204d1054f75b5a342fd82094da0ca17cee372b4c581c5b26",
}

MAIN_SCOREBOARD = 0.4091179943351143
RANDOM_ROW_LEAK_REFERENCE_R2 = 0.7385332681453336

# The v0.4 roster digest, so the package can prove the patch landed on top of
# the frozen v0.3 bytes rather than beside them.
DIELECTRIC_V04_SHA256 = "e046a3831630e36aae6b67666f74f787b8b33303057877c3402ff7a414e0873c"
DIELECTRIC_V03_SHA256 = "ff2142936e06e04b329b70f8597574f75349e54ce876e9fff81309e6d35ccce4"

# W17-6's merge shot is the only week-17 attempt at the main scoreboard.
W17_MAIN_SCOREBOARD_ATTEMPTS = 1
# Programme count for the two blocks being merged: lever 4 held 1 shot and
# lever 8 held 2 before this round, and the merge itself is the fourth.
LEVER_4_PLUS_LEVER_8_PROGRAMME_SHOTS_AFTER = 4
# Cumulative main-scoreboard attempts after this round: the Week 14 ledger read
# 10 and is never rewritten, so the running total is 10 + 1.
MAIN_SCOREBOARD_CUMULATIVE_ATTEMPTS = 11

# Ruling B (reports/decisions_log.md section 28.2): every Reaxys-derived list is
# excluded from outward-facing bundles, whole file, and the repository keeps it
# verbatim as cross-check evidence.  The second field says whether the file carries
# Reaxys values at all, so a reader can tell a value list from a plan that merely
# lives beside one.
# The four load-bearing claims the integrator re-ran by hand on the author's
# signed-in Edge session, so the crosscheck is not a single hand's word.
# Identifiers (CAS, Reaxys RN, InChIKey) are quoted; Reaxys *property values* are
# not, because ruling B keeps every Reaxys-derived value out of this bundle. The
# molecular weights the substance records carried are deliberately absent for the
# same reason, so do not "round out" a fact by putting one back.
INDEPENDENT_RECHECK_FACTS = (
    {
        "claim": "the GVL key in the week12 first-cut queue is not a Reaxys key",
        "observed": "JYVATQXCHBTGRN-UHFFFAOYSA-N returns 0 Substances and 0 Documents",
    },
    {
        "claim": "the corrected key resolves to gamma-valerolactone",
        "observed": (
            "GAEKPEKOJKCEMS-UHFFFAOYSA-N returns 4 Substances; the top hit is "
            "5-methyl-dihydro-furan-2-one, CAS 108-29-2, Reaxys RN 80420"
        ),
    },
    {
        "claim": "dimethyl carbonate resolves to one substance",
        "observed": (
            "IEJIGPNLZYLLBP-UHFFFAOYSA-N returns 1 Substance: carbonic acid dimethyl "
            "ester, CAS 616-38-6, Reaxys RN 635821"
        ),
    },
    {
        "claim": "Reaxys stores HOMO/LUMO as references, not as numbers",
        "observed": (
            "the dimethyl carbonate Quantum Chemical Calculations table has exactly "
            "the columns Calculated Properties, Method, Location and Reference; its "
            "first row is Density of states / DFT-density functional methods / "
            "supporting information / a citation, and no numeric HOMO, LUMO or gap "
            "column exists"
        ),
    },
)
RESTRICTED_EXCLUDED = (
    ("probes/reaxys_core_four_crosscheck.csv", True),
    ("probes/reaxys_core_four_crosscheck_summary.json", True),
    ("probes/reaxys_core_four_crosscheck.py", True),
    ("reports/reaxys_core_four_crosscheck.md", True),
    ("tests/test_reaxys_core_four_crosscheck.py", True),
    ("probes/reaxys_thin_family_backfill_queue.csv", False),
    ("probes/reaxys_thin_family_query.py", True),
    ("probes/reaxys_thin_family_query_summary.json", True),
    ("probes/reaxys_thin_family_query_facts.csv", False),
    ("reports/reaxys_thin_family_query.md", True),
    ("tests/test_reaxys_thin_family_query.py", False),
    ("probes/reaxys_thin_family_query_b2.py", True),
    ("probes/reaxys_thin_family_query_b2_summary.json", True),
    ("probes/reaxys_thin_family_query_b2_facts.csv", False),
    ("tests/test_reaxys_thin_family_query_b2.py", False),
)

README_TEXT = """# Week 17 交付包（扩物质与多维度：黏度 v0.2 / 密度 / 液相窗口 / 配位块 / Walden / DN）

数据血缘: 规范数据集 `data/dielectric_v03.csv` **未改动**
（digest `ff2142936e…35ccce4`）；v1.0 已发布工件与 week11–week16 交付包未被触碰。
本周的扩容一律进**新版本表**：`data/dielectric_v04.csv`（248 行）、`data/density_v01.csv`
（182,154 行）、`data/viscosity_v02.csv`（42,941 行）；六件冻结件 digest **6/6 INTACT**。
生成脚本: `probes/export_week17_results.py`

## 头条（十五句话，都不许外推）

1. **四大核心数据的现状到此一眼可查**（四通道覆盖板，`four_channel_coverage.csv`，29 行）：
   **ε** 主记分牌 `0.4091179943351143`（457 行 / 97 化合物 = **276** 对），天花板是**信息缺口**
   （缺 Kirkwood g 维）不是行数缺口；**η** `group_key` R² `0.7481271437772365`、MAE
   `0.17477197208762`（门 0.15，**红**，只许族级结论）；**HOMO** MAE `0.19050925839013938`
   与 **LUMO** MAE `0.13855083976437643`（门 0.2 eV，**两门都过**）；**redox** 氧化
   `0.2905180517963865` / 还原 `0.4096241620366996`（门 0.15 V，**红**，瓶颈是 **392** 条标签）。
2. **HOMO / LUMO 维持现状、本轮不投精度**（IP `0.2010970559642009` 与 EA `0.23415453202842548`
   仍未过 0.2 eV 门，照 W17-8 维持粗筛口径）。
3. **密度是第一缺口维度，本周补上了**：`density_v01` 182,154 纯物质行（2,178 键），
   对 ε v0.3 名册 **246 → 180 = 73.17%** 覆盖。**7 成覆盖是「换算因子可用」的量级，
   不是「可当 ε 新特征」的量级**（先例：杠杆 4 的 95/97）；两种用途**不混用**。
4. **176 行运动黏度已全部解冻、口径由族级升到行级**：在 |ΔT| ≤ 1e-3 K 内 **176/176 精确命中**
   密度，η = κ·ρ 反解 **176 行**、其中**纯组分 86 行入主表**（另 90 行多组分只进另册、不拆角色），
   逐行 provenance 见 `viscosity_v02.csv` 的 `density_*` 列（W17-3 执行，取代 W17-7 落盘时的族级读数）。
5. **黏度 v0.2 建成，三种口径分开报**：在线目录层 **1,743 条记录**（`Viscosity, Pa*s` 1,690 ＋
   `Kinematic viscosity, m2/s` 70）；数值层 **268,247 观测行 / 1,547 键**；主表
   `data/viscosity_v02.csv` **42,941 行 / 1,228 键** = Pa*s 直测 42,855 ＋ 运动黏度反解 86。
   **本地 2,549 行逐行对账 2549/2549 命中、0 未命中**；`group_overlap == 0`（5 折 GroupKFold）。
   **记录数 ≠ 观测行数 ≠ 键数，三者不许相除。**
6. **液相窗口硬门已转正**：314 键，**blocked 77**（24.52%，触发率 `0.24522292993630573`）/
   pass 126 / unknown 111；把 unknown 一并算作保守触发则 59.87%（`0.5987261146496815`）。
   **EC 被正确拦下**（mp 36.4 °C ⇒ 25 °C 不是液体）——
   「Reaxys 把 EC 熔点标成 25 °C」的教训由此有了机器化纠错锚。
7. **Li⁺ 配位块转正，且两枪合并已实测**：`plus_both` R² `0.4766400383507876`，
   对基线 Δ **+0.0675220440156733**（门 +0.0200），安慰剂塌缩 ✅，正向重复 9/10。
   **合并非加和**：朴素相加 = +0.0998972687629372，实测**低 0.0323752247472639**；
   合并枪相对最强单枪只多 +0.011683591468432397，**这一枪是本轮唯一一次主记分牌尝试**。
8. **Walden 耦合已建成、DN 通道不过门**：ε–η 联表复算 **8,359 行 / 1,043 键**通过，
   产出 **1,219 对**（同温度才配对、不平均）；**DN 可采信覆盖 0 / 1,043 = 0.00%**
   （门 30%）⇒ **不进特征表**（DN 只有实验 + 一手 DOI 才算可采信）。
9. **Reaxys 交叉核验（W17-RX）只作核对、不入数据**：作者已登录的 Edge 会话上**逐条手动**
   查了 **9 次 / 5 个物质 / 80 行观测**，**无批量爬虫**；集成者随后**用同一会话独立复跑**了四条
   承重结论。判决：**ε 与 η 有可用数值**，但 **HOMO/LUMO 与氧化还原电位在 Reaxys 只有文献
   引用、0 条数值** —— 它**无法缓解** P4 的 **392** 条标签瓶颈。三条教训：GVL 的错键
   **`JYVATQXCHBTGRN-…` 是我们自己写错的**（Reaxys 返回 0 Substances / 0 Documents，正键
   `GAEKPEKOJKCEMS-…` 返回 4 Substances）；EC 的 ε=89.78 有两条腿、其中一条标 **25 °C** 而
   EC 熔点 **36.4 °C** ⇒ **25 °C 标签即缺陷**；「Reaxys 把 89.78 当熔点」**不成立**。
   **受限清单按裁决 B 整文件排除本包**（见 `week17_summary.json.restricted_contract`）。
10. **本周不产新杠杆**：除 W17-6 那一枪合并复测外，其余臂**均不拟合模型**
    （`models_fitted = 0` / `r2_reported = false`）。周范围之外的部分照实登记为未做：
    AL Round 4 的 P1/P3 动作；W17-RX 只核对、**不产净增行数**（Reaxys 值不入 `data/`）。
11. **四大核心数据已整理成一张跨通道注册表**（`four_core_key_registry.csv`，**31,949 行 / 30 列**，
    键 = InChIKey，一行一键）：六通道键数 ε **247**、η **1,228**、orbitals **29,868**、
    redox 标签 **392**、ρ **2,178**、液相窗口 **218**（该表其实有 **314** 行，其中 **96** 行
    mp/bp/闪点/密度四列全空）；四核心两种口径全齐 **7**（ε+η+orbitals+redox 标签）与
    **51**（把 redox 换成液相窗口；上一轮登记的 **53** 是**表键口径**，两种都登记在表里）。
    描述性关系：Kirkwood K(ε) 与 DFT 偶极平方 Pearson `0.6464482483155134`（n = **79**），
    **只作描述、非判决**；本臂 `models_fitted = 0`，不碰主记分牌。
12. **轨道通道拿到了第二个可再分发的源，而且它真的能用**（W17-12，
    `data/processed/orbital_second_source_layer.csv`，**912 行 / 35 列**，sha256
    `ba55897a296181267cc0673cbf2d4d98d17b3e5de8280958b7896556e053abfe`）：新源是
    **PubChemQC B3LYP/6-31G*//PM6**（CC BY 4.0，DOI `10.1021/acs.jcim.3c00899`，
    镜像 `molssiai-hub/pubchemqc-b3lyp`；抓取痕迹 1246 次请求 / 352,262,591 B）。
    它在 ε 名册上覆盖 **210/247 = 85.0%**——此前唯一的替代候选 iMolS 只有 **103/247 = 41.7%**、
    无任何再分发条款且对全站 `Disallow` ⇒ **否决**；η 名册预注册随机样本 **139/300 = 46.3%**
    （全 1,228 键名册命中 **240**，两个分母不许混用）；与 Batt-P30K 配对 **111** 个，但配对集
    **不是 Batt 池的随机样本**（12 随机 ＋ 101 定向 ＋ 10 头部扫描），只能当作**电解质类分子**
    的跨水平映射。跨水平映射（2 折、样本外）：**HOMO slope `1.0132507837193052` /
    截距 `−2.8354161402050426 eV` / r `0.9717477841107552` / MAE `0.17662467232470583 eV`
    ⇒ `usable_with_flag`**；**LUMO 因 r `0.7349044734023142` < 0.80 诚实降级 `reference_only`
    （`calib_lumo_eV` 列全空）**。单位已定案：卡片标的 `hartree` 是**文档缺陷**，实测是 **eV**
    （分层审计 **240/240**、跨 CID 1→233,866；独立锚点：η 名册合法含氦，其 HOMO `−17.681958` /
    LUMO `+30.471309` / gap `48.153267` eV）。`unit_check` 分级：
    `verified_eV_audited` **20 行** / `dataset_level_eV` **892 行**。
    **主源不变**——`four_core_key_registry.csv` 的 `HOMO_eV`/`LUMO_eV` 一字节未改，
    本层不含任何 Reaxys 数值；本臂 `models_fitted = 0`，不碰主记分牌 `0.4091179943351143`。
13. **Reaxys 薄族补货队列**第一次被**真的走了一遍**（W17-13，10 物质 / **21** 次查询 / 预算 25；
    W17-2 交付队列时 `reaxys_queries_executed = 0`）。结论按通道分开：ε 在 6 个物质上有类目、
    5 个有数值；η 最厚（169 行 / **143** 个点值 / 10 个物质全覆盖）；**轨道通道在 Reaxys 里不是
    HOMO/LUMO，而是 `Ionization Potential`**（18 行 / 10 个点值，其余为区间或纯文献）
    ＋ 全为 reference-only 的 `Quantum Chemical Calculations`（6 行 / 0 数值）；**氧化还原只有 5 个
    点值，且全部写在 `Comment` 列而非数值列**。因此 W17-RX 的「Reaxys 0 条数值」需**收窄**：
    它在**轨道通道**上仍成立（没有任何 HOMO/LUMO/gap 列），但氧化还原通道确有数值，只是不在数值列里。
    **P4 的 392 条标签瓶颈没有被缓解**。按裁决 B，本臂**整文件不进本交付包**，数值不进 `data/`、
    不进任何池或特征表；本臂 `models_fitted = 0`。

14. **THEMol 的几何能用，但它的能级不能直接混用**（W17-14，`data/processed/themol_orbital_layer.csv`，
    **166 行 / 34 列**，sha256 `6e05f02e755c57ab09d73a784687b2c1deb757f80e43c5746358f1f7a5ecde80`）：
    ByteDance-Seed/THEMol（**CC BY-NC 4.0**）的 Hessian 子集有 **2,695,304** 条 DFT 几何，
    本仓关键名册命中 **5,117/31,949 = 16.0%**、ε 名册 **142/247 = 57.5%**、η 名册 **242/1,228 = 19.7%**。
    THEMol 自己**不含任何轨道量**（HDF5 组只有 `atomic_numbers` / `coords` / `hessian`），
    所以这一臂走「HTTP Range 只读几何（**142,150,508 B，0 字节 .h5 落盘**）＋ GFN2-xTB 单点」，
    对 ε 名册 ∪ W17-12 的 111 个配对锚（去重 **166** 个分子，其中 **74** 个锚）**全部出数、0 失败**。
    跨能级映射（2 折样本外；门限逐字继承 W17-12，**不是看到结果才定的**）：
    **HOMO r `0.8557447540814086` 过门，但 MAE `0.353095083458508 eV` 超 0.35 eV 门 0.0031 eV；
    LUMO r `0.5295614175613801`（slope 仅 `0.0903748834229043`）；gap r `0.3072262053474138`
    ⇒ 三通道全部 `reference_only`**，`calib_homo_eV` / `calib_lumo_eV` **整列为空**、
    `calibrated_estimate = 0`。能级偏移：HOMO 均值 **−1.0595 eV**（σ 0.4797，规整可平移）、
    LUMO 均值 **−7.0126 eV**（σ 2.4789，离散不可平移）；**gap 是平移不变通道，r 仍是 0.31**
    ⇒ 不是参考点问题，是尺度问题，**GFN2 的虚轨道不可用**。诚实性对齐上一臂被审出的三个 P1：
    `unit_check` 改**管道级**声明（独立重跑 8 分子、同读 Eh 与 eV 两列、最大残差 **4.49e-05 eV**、
    8/8 通过）；`structure_check` **逐行**从该行自己的 SMILES 重算 InChIKey（**166/166 命中**）。
    **主源不变**——Batt-P30K 与 PubChemQC 两列一个字节未改；本臂 `models_fitted = 0`，不碰主记分牌。
15. **Reaxys 薄族第二批：真正的瓶颈是队列本身没有键**（W17-15，**4** 物质 / **4** 次查询 / 预算 30）：
    队列第 11–25 行的 `candidate_inchikey` **15 行全为空**（族线索型，不是库存键型），
    无键可逐字断言 ⇒ 改走队列里**仍带逐字键且 W17-13 未走过**的 4 行
    （GVL / EC / EMC / 亚硫酸二乙酯，队列第 59/60/62/67 行）。逐通道（条数 / 有数值 / 点值）：
    ε **19/17/16**、η **22/21/21**、电离能 **12/0/0**、氧化还原 **1/0/0**。
    **两条与第一批冲突的发现**：① **η 也会躲在 `Comment` 列**——本批 **11/21** 个点值只在 Comment
    （数值列全空；EC 的 17 行里 7 行如此），**只读数值列会只看得见 10/21**；
    ② 该块在 4 张卡里有 3 张标成 `Quantum Chemical Calculations`（其首列列头仍是
    `Calculated Properties`），与第一批记的 `Other Data > Calculated Properties` 是同一物、标签不同。
    **轨道通道仍无任何 HOMO/LUMO**，氧化还原仍 **0 个点值** ⇒ **P4 的 392 条标签瓶颈未被缓解**。
    按裁决 B 整文件不进本交付包，数值不进 `data/`、不进任何池或特征表；本臂 `models_fitted = 0`。

## 本周目录

| 臂 | 内容 | 落点 |
| --- | --- | --- |
| W17-1 | v0.4 名册补丁（succinonitrile + GVL 双行） | data/dielectric_v04.csv |
| W17-2 | 薄家族补货队列（**计划，非测量**） | reaxys_thin_family_backfill_queue.csv（**受限清单，不进本包**） |
| W17-3 | 黏度 v0.2（在线切片 ＋ 本地对账 ＋ 运动黏度解冻） | data/viscosity_v02.csv |
| W17-4 | 密度 ρ(T) 新表 + 解冻门 | data/density_v01.csv |
| W17-5 | 液相窗口特征列 + 漏斗硬门 | liquid_window_features.csv |
| W17-6 | Li⁺ 配位块转正 + 两枪合并复测 | dielectric_coordination_block_v3_summary.json |
| W17-7 | ε–η Walden 耦合 + DN 覆盖审计 | walden_coupling_pairs.csv / dn_coverage_audit.csv |
| W17-9 | 四通道覆盖板 | four_channel_coverage.csv |
| W17-RX | Reaxys 四大核心数据交叉核验（**只核对，不入数据**） | probes/reaxys_core_four_crosscheck.csv（**不进本包**） |
| W17-11 | 四大核心数据跨通道注册表 ＋ 通道关系矩阵（**不拟合模型**） | data/processed/four_core_key_registry.csv |
| W17-12 | 轨道第二源 PubChemQC（CC BY 4.0）定向取样 ＋ 跨水平标定 ＋ 三张图 | data/processed/orbital_second_source_layer.csv |
| W17-13 | Reaxys 薄族补货队列实查（10 物质，**只核对，不入数据**） | probes/reaxys_thin_family_query_facts.csv（**不进本包**） |
| W17-14 | THEMol/GFN2-xTB 第三轨道源（几何可读、能级不可混用；**负结果**） | data/processed/themol_orbital_layer.csv |
| W17-15 | Reaxys 薄族第二批实查（4 物质，**只核对，不入数据**） | probes/reaxys_thin_family_query_b2_facts.csv（**不进本包**） |

## 复跑方式

```
.\\.venv\\Scripts\\python.exe probes\\export_week17_results.py --overwrite
.\\.venv\\Scripts\\python.exe scripts\\verify_dielectric_v04.py
.\\.venv\\Scripts\\python.exe scripts\\verify_liquid_window_gate.py --check
.\\.venv\\Scripts\\python.exe scripts\\verify_walden_dn_channel.py --check
.\\.venv\\Scripts\\python.exe probes\\verify_unimol_probe_spec.py --check
.\\.venv\\Scripts\\python.exe scripts\\verify_four_core_registry.py --check
.\\.venv\\Scripts\\python.exe scripts\\verify_orbital_second_source.py --check
.\\.venv\\Scripts\\python.exe scripts\\verify_themol_orbital_layer.py --check
```

`scripts/verify_density_v01.py --check` 与 `scripts/verify_viscosity_v02.py --check` **都不在** CI 里：
两者的数值层分别需要被忽略的 54 MB `data/processed/density_raw.csv` 与 81 MB
`data/processed/viscosity_v02_raw.csv`（或 `data/raw/` 下的原始缓存），属 tier-2（本机缓存）verifier；
因此它们各自的测试件都按需 `skip`，且两侧的目录层/数值层判据一条没有放宽。

## 边界（不许外推）

- **随机行**参照 `0.7385332681453336` 只说明「按行随机切分会让同一化合物的观测落进
  训练集」，是**泄漏诊断**，不是成绩、不是基线，禁止与主记分牌 `0.4091179943351143` 比较。
- `0.5332` / `0.5454` 只在各自池定义下成立（147 化合物训练池 / 97 化合物固定评分池），
  永不与 v1.0 头条 `0.364`（冻结的 236 化合物池）混用。
- 本周未做的部分逐条登记在 `week17_summary.json.not_done_this_week`；W17-2 只交付队列、
  `reaxys_queries_executed = 0`（本臂**一次 Reaxys 查询都没跑**）。

## 受限数据（裁决 B）

Reaxys 派生清单**整文件排除**本包，本仓库内部逐字保留以便复核；
`week17_summary.json.restricted_contract` 逐件给出路径、digest 与是否带值。
**本包内不含任何 Reaxys 数值。**
"""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


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


def _worktree_status(source_root: Path) -> tuple[bool, int]:
    completed = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=source_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    paths = [line for line in (completed.stdout or "").splitlines() if line.strip()]
    return bool(paths), len(paths)


def _frozen_red_lines() -> dict[str, dict[str, object]]:
    red_lines: dict[str, dict[str, object]] = {}
    for path, expected in FROZEN_RED_LINES.items():
        measured = _sha256(REPOSITORY_ROOT / path)
        red_lines[path] = {
            "sha256": measured,
            "expected_sha256": expected,
            "intact": measured == expected,
        }
    return red_lines


def _csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


ARTIFACTS = (
    ("reports/decisions_log.md", "decisions_log.md"),
    # W17-1 -- the dielectric v0.4 roster patch.
    ("scripts/build_dielectric_v04.py", "build_dielectric_v04.py"),
    ("scripts/verify_dielectric_v04.py", "verify_dielectric_v04.py"),
    ("probes/dielectric_v04_summary.json", "dielectric_v04_summary.json"),
    ("data/dielectric_v04.csv", "data/dielectric_v04.csv"),
    (
        "data/processed/dielectric_v04_roster_additions.csv",
        "data/processed/dielectric_v04_roster_additions.csv",
    ),
    (
        "data/processed/dielectric_v04_provenance_patches.csv",
        "data/processed/dielectric_v04_provenance_patches.csv",
    ),
    ("reports/dielectric_v04.md", "dielectric_v04.md"),
    ("tests/test_dielectric_v04.py", "test_dielectric_v04.py"),
    # W17-2 -- the thin-family backfill queue (a plan, not a measurement).
    ("probes/reaxys_thin_family_backfill.py", "reaxys_thin_family_backfill.py"),
    (
        "probes/reaxys_thin_family_backfill_prereg.json",
        "reaxys_thin_family_backfill_prereg.json",
    ),
    (
        "probes/reaxys_thin_family_backfill_summary.json",
        "reaxys_thin_family_backfill_summary.json",
    ),
    (
        "reports/reaxys_thin_family_backfill.md",
        "reaxys_thin_family_backfill.md",
    ),
    (
        "tests/test_reaxys_thin_family_backfill.py",
        "test_reaxys_thin_family_backfill.py",
    ),
    # W17-4 -- density rho(T), the first missing dimension.
    ("probes/build_density_v01.py", "build_density_v01.py"),
    ("probes/build_density_v01_prereg.json", "build_density_v01_prereg.json"),
    ("probes/density_v01_summary.json", "density_v01_summary.json"),
    ("scripts/verify_density_v01.py", "verify_density_v01.py"),
    ("reports/density_v01.md", "density_v01.md"),
    ("data/density_v01.csv", "data/density_v01.csv"),
    ("tests/test_build_density_v01.py", "test_build_density_v01.py"),
    # W17-3 -- viscosity v0.2: the online slice, the local reconciliation and the
    # kinematic unfreeze.  The 80 MB value layer stays git-ignored, like density_raw.
    ("probes/build_viscosity_v02.py", "build_viscosity_v02.py"),
    (
        "probes/build_viscosity_v02_prereg.json",
        "build_viscosity_v02_prereg.json",
    ),
    ("probes/viscosity_v02_summary.json", "viscosity_v02_summary.json"),
    ("scripts/verify_viscosity_v02.py", "verify_viscosity_v02.py"),
    ("reports/viscosity_v02.md", "viscosity_v02.md"),
    ("data/viscosity_v02.csv", "data/viscosity_v02.csv"),
    ("tests/test_build_viscosity_v02.py", "test_build_viscosity_v02.py"),
    # W17-5 -- the liquid-window hard gate.
    ("probes/build_liquid_window_features.py", "build_liquid_window_features.py"),
    ("probes/liquid_window_gate_prereg.json", "liquid_window_gate_prereg.json"),
    ("probes/liquid_window_gate_summary.json", "liquid_window_gate_summary.json"),
    ("scripts/verify_liquid_window_gate.py", "verify_liquid_window_gate.py"),
    ("reports/liquid_window_gate.md", "liquid_window_gate.md"),
    ("tests/test_liquid_window_gate.py", "test_liquid_window_gate.py"),
    # W17-6 -- the Li+ coordination block, promoted and merge-tested.
    (
        "probes/dielectric_coordination_block_v3.py",
        "dielectric_coordination_block_v3.py",
    ),
    (
        "probes/dielectric_coordination_block_prereg_v3.json",
        "dielectric_coordination_block_prereg_v3.json",
    ),
    (
        "probes/dielectric_coordination_block_v3_summary.json",
        "dielectric_coordination_block_v3_summary.json",
    ),
    (
        "probes/artifacts/dielectric_coordination_block_v3_folds.csv",
        "artifacts/dielectric_coordination_block_v3_folds.csv",
    ),
    (
        "probes/artifacts/dielectric_coordination_block_v3_repeats.csv",
        "artifacts/dielectric_coordination_block_v3_repeats.csv",
    ),
    (
        "probes/artifacts/dielectric_coordination_block_v3_predictions.csv",
        "artifacts/dielectric_coordination_block_v3_predictions.csv",
    ),
    (
        "reports/dielectric_coordination_block_v3.md",
        "dielectric_coordination_block_v3.md",
    ),
    (
        "tests/test_dielectric_coordination_block_v3.py",
        "test_dielectric_coordination_block_v3.py",
    ),
    # W17-7 -- the Walden coupling and the donor-number audit.
    ("probes/walden_dn_channel.py", "walden_dn_channel.py"),
    ("probes/walden_dn_channel_prereg.json", "walden_dn_channel_prereg.json"),
    ("probes/walden_dn_channel_summary.json", "walden_dn_channel_summary.json"),
    ("scripts/verify_walden_dn_channel.py", "verify_walden_dn_channel.py"),
    ("reports/walden_dn_channel.md", "walden_dn_channel.md"),
    ("tests/test_walden_dn_channel.py", "test_walden_dn_channel.py"),
    (
        "data/processed/walden_coupling_pairs.csv",
        "data/processed/walden_coupling_pairs.csv",
    ),
    ("data/processed/dn_coverage_audit.csv", "data/processed/dn_coverage_audit.csv"),
    # W17-9 -- the four-channel coverage board.
    ("probes/four_channel_coverage.py", "four_channel_coverage.py"),
    (
        "probes/four_channel_coverage_summary.json",
        "four_channel_coverage_summary.json",
    ),
    (
        "data/processed/four_channel_coverage.csv",
        "data/processed/four_channel_coverage.csv",
    ),
    ("reports/four_channel_coverage.md", "four_channel_coverage.md"),
    ("tests/test_four_channel_coverage.py", "test_four_channel_coverage.py"),
    # W17-11 -- the four-core cross-channel registry and the channel relation matrix.
    ("probes/build_four_core_registry.py", "build_four_core_registry.py"),
    ("probes/four_core_registry_prereg.json", "four_core_registry_prereg.json"),
    ("probes/four_core_registry_summary.json", "four_core_registry_summary.json"),
    (
        "data/processed/four_core_key_registry.csv",
        "data/processed/four_core_key_registry.csv",
    ),
    ("scripts/verify_four_core_registry.py", "verify_four_core_registry.py"),
    ("reports/four_core_registry.md", "four_core_registry.md"),
    ("tests/test_build_four_core_registry.py", "test_build_four_core_registry.py"),
    # Scaffolding touched this round.
    # W17-12 -- the second orbital source (PubChemQC, CC BY 4.0).
    ("probes/harvest_pubchemqc_orbital.py", "harvest_pubchemqc_orbital.py"),
    ("probes/build_orbital_second_source.py", "build_orbital_second_source.py"),
    ("probes/orbital_second_source_prereg.json", "orbital_second_source_prereg.json"),
    ("probes/orbital_second_source_summary.json", "orbital_second_source_summary.json"),
    ("scripts/verify_orbital_second_source.py", "verify_orbital_second_source.py"),
    ("probes/plot_orbital_second_source.py", "plot_orbital_second_source.py"),
    ("reports/orbital_second_source.md", "orbital_second_source.md"),
    (
        "data/processed/orbital_second_source_layer.csv",
        "data/processed/orbital_second_source_layer.csv",
    ),
    ("tests/test_build_orbital_second_source.py", "test_build_orbital_second_source.py"),
    (
        "probes/artifacts/orbital_second_source_calibration.png",
        "orbital_second_source_calibration.png",
    ),
    (
        "probes/artifacts/orbital_second_source_coverage.png",
        "orbital_second_source_coverage.png",
    ),
    (
        "probes/artifacts/orbital_second_source_landscape.png",
        "orbital_second_source_landscape.png",
    ),
    # W17-14 -- THEMol Hessian geometry + GFN2-xTB, the third orbital source.
    ("probes/themol_hessian_orbitals.py", "themol_hessian_orbitals.py"),
    ("probes/build_themol_target_roster.py", "build_themol_target_roster.py"),
    ("probes/themol_orbital_unit_audit.py", "themol_orbital_unit_audit.py"),
    ("probes/build_themol_orbital_layer.py", "build_themol_orbital_layer.py"),
    ("probes/themol_orbital_layer_prereg.json", "themol_orbital_layer_prereg.json"),
    ("probes/themol_orbital_layer_summary.json", "themol_orbital_layer_summary.json"),
    (
        "data/processed/themol_orbital_layer.csv",
        "data/processed/themol_orbital_layer.csv",
    ),
    ("scripts/verify_themol_orbital_layer.py", "verify_themol_orbital_layer.py"),
    ("probes/plot_themol_orbital_layer.py", "plot_themol_orbital_layer.py"),
    ("reports/themol_orbital_layer.md", "themol_orbital_layer.md"),
    ("tests/test_themol_orbital_layer.py", "test_themol_orbital_layer.py"),
    (
        "probes/artifacts/themol_orbital_layer_calibration.png",
        "themol_orbital_layer_calibration.png",
    ),
    (
        "probes/artifacts/themol_orbital_layer_coverage.png",
        "themol_orbital_layer_coverage.png",
    ),
    (".gitignore", ".gitignore"),
    (".github/workflows/ci.yml", "ci.yml"),
    ("probes/export_results_common.py", "export_results_common.py"),
    ("probes/manual_appendix_reconciliation.py", "manual_appendix_reconciliation.py"),
    ("tests/fixtures/manual_appendix_j_snapshot.md", "manual_appendix_j_snapshot.md"),
    ("probes/unimol_probe_spec_prereg.json", "unimol_probe_spec_prereg.json"),
    ("probes/verify_unimol_probe_spec.py", "verify_unimol_probe_spec.py"),
    ("reports/unimol_probe_spec.md", "unimol_probe_spec.md"),
    ("tests/test_unimol_probe_spec.py", "test_unimol_probe_spec.py"),
    ("tests/test_week15_reporting_accuracy.py", "test_week15_reporting_accuracy.py"),
    ("tests/test_manual_appendix_reconciliation.py", "test_manual_appendix_reconciliation.py"),
)

VERIFIERS = (
    "scripts/verify_dielectric_v04.py",
    "scripts/verify_liquid_window_gate.py --check",
    "scripts/verify_walden_dn_channel.py --check",
    "probes/verify_unimol_probe_spec.py --check",
    "scripts/verify_four_core_registry.py --check",
    "scripts/verify_orbital_second_source.py --check",
    "scripts/verify_themol_orbital_layer.py --check",
    (
        "-m pytest tests/test_dielectric_v04.py tests/test_reaxys_thin_family_backfill.py "
        "tests/test_build_density_v01.py tests/test_build_viscosity_v02.py "
        "tests/test_liquid_window_gate.py "
        "tests/test_dielectric_coordination_block_v3.py tests/test_walden_dn_channel.py "
        "tests/test_four_channel_coverage.py tests/test_manual_appendix_reconciliation.py "
        "tests/test_build_four_core_registry.py "
        "tests/test_build_orbital_second_source.py "
        "tests/test_unimol_probe_spec.py tests/test_week15_reporting_accuracy.py "
        "tests/test_reaxys_core_four_crosscheck.py "
        "tests/test_reaxys_thin_family_query.py tests/test_reaxys_thin_family_query_b2.py "
        "tests/test_themol_orbital_layer.py tests/test_export_week16_results.py "
        "tests/test_repo_hygiene.py -q -p no:cacheprovider"
    ),
)


def export_results(*, output_root: Path, overwrite: bool) -> dict:
    week_root = output_root / WEEK
    if week_root.exists() and not overwrite:
        raise FileExistsError(f"{week_root} already exists; pass --overwrite")

    copied = copy_artifacts(REPOSITORY_ROOT, week_root, ARTIFACTS)
    verification = run_verifiers(REPOSITORY_ROOT, VERIFIERS)

    v04 = read_json(REPOSITORY_ROOT / "probes" / "dielectric_v04_summary.json")
    thin = read_json(REPOSITORY_ROOT / "probes" / "reaxys_thin_family_backfill_summary.json")
    density = read_json(REPOSITORY_ROOT / "probes" / "density_v01_summary.json")
    window = read_json(REPOSITORY_ROOT / "probes" / "liquid_window_gate_summary.json")
    block = read_json(
        REPOSITORY_ROOT / "probes" / "dielectric_coordination_block_v3_summary.json"
    )
    walden = read_json(REPOSITORY_ROOT / "probes" / "walden_dn_channel_summary.json")
    board = read_json(REPOSITORY_ROOT / "probes" / "four_channel_coverage_summary.json")
    viscosity = read_json(REPOSITORY_ROOT / "probes" / "viscosity_v02_summary.json")
    reaxys = read_json(
        REPOSITORY_ROOT / "probes" / "reaxys_core_four_crosscheck_summary.json"
    )

    frozen = _frozen_red_lines()
    artifacts_commit = _head_commit(REPOSITORY_ROOT)
    worktree_dirty, worktree_dirty_paths = _worktree_status(REPOSITORY_ROOT)

    v04_table = v04["output"]
    v04_on_disk = _sha256(REPOSITORY_ROOT / v04_table["path"])
    density_table = density["outputs"]["table"]
    density_coverage = density["coverage"]["vs_dielectric_v03"]
    unfreeze = density["criterion_c_unfreeze"]
    gate = window["gate"]
    verdict = block["verdict"]
    merge = block["merge_readings"]
    collapse = block["collapse"]
    block_shots = block["shots"]
    walden_decision = walden["decision"]
    dn = walden["dn_channel"]
    thaw = walden["kinematic_thaw"]
    recount = walden["joint_table_recount"]
    pins = board["pinned"]
    v02_table = viscosity["outputs"]["table"]
    v02_raw = viscosity["outputs"]["raw"]
    v02_dual = viscosity["criterion_d_basis_honesty"]["dual_basis_counts"]
    v02_unfreeze = viscosity["criterion_c_unfreeze"]
    v02_recon = viscosity["criterion_e_row_reconciliation"]
    v02_overlap = viscosity["group_overlap_audit"]

    def arm_r2(name: str) -> float:
        return block["arms"][name]["Morgan+Physical"]["r2"]["mean"]

    summary = {
        "week": WEEK,
        "head_commit": artifacts_commit,
        "artifacts_commit": artifacts_commit,
        "worktree_dirty": worktree_dirty,
        "worktree_dirty_paths": worktree_dirty_paths,
        "provenance_note": (
            "artifacts_commit is the commit to fetch the shipped artefacts from, but "
            "only when worktree_dirty is false. When worktree_dirty is true, at least "
            "one shipped file was copied from an uncommitted working tree, so no commit "
            "on its own identifies the shipped bytes: seal the worktree into a commit, "
            "re-export from that commit and cite it before quoting any artefact "
            "coordinate."
        ),
        "pivot": (
            "Week 17 is the pivot from chasing epsilon precision to making each of the "
            "four funnel channels trustworthy: more compounds (a v0.4 roster patch and a "
            "thin-family backfill queue) and more dimensions (density, liquid window, the "
            "Li+ coordination block promoted to production, the Walden coupling, and a "
            "donor-number coverage audit that fails its gate)."
        ),
        "shots": {
            "main_scoreboard_attempts": W17_MAIN_SCOREBOARD_ATTEMPTS,
            "main_scoreboard_cumulative_attempts": MAIN_SCOREBOARD_CUMULATIVE_ATTEMPTS,
            "lever_4_plus_lever_8_programme_shots_after": (
                LEVER_4_PLUS_LEVER_8_PROGRAMME_SHOTS_AFTER
            ),
            "models_fitted": 1,
            "r2_reported_anywhere": True,
            "rule": (
                "every scored attempt at the main scoreboard is counted, including "
                "failed ones. Week 17 made exactly one attempt (W17-6's merge re-run) "
                "and it is registered in reports/decisions_log.md section 28.5."
            ),
        },
        "main_scoreboard": {
            "value": MAIN_SCOREBOARD,
            "touched": True,
            "touched_by": "W17-6 only, as a re-run of the frozen baseline",
            "baseline_reproduced": verdict["baseline_reproduced"],
            "baseline_abs_delta": verdict["baseline_abs_delta"],
            "note": (
                "0.4091179943351143 is reproduced to abs_delta = 0.0 and used only as "
                "the baseline of the merge shot. No lane quotes it as a gain."
            ),
        },
        "random_row_leak_reference_r2": RANDOM_ROW_LEAK_REFERENCE_R2,
        "lanes": {
            "w17_1_dielectric_v04_roster": {
                "probe": "scripts/build_dielectric_v04.py",
                "dataset_version": v04["dataset_version"],
                "v03_row_count": v04["v03_row_count"],
                "row_count": v04["row_count"],
                "compound_count": v04["compound_count"],
                "addition_count": v04["addition_count"],
                "additions": v04["additions"],
                "model_ready_addition_count": v04["model_ready_addition_count"],
                "conflict_addition_count": v04["conflict_addition_count"],
                "source_counts": v04["source_counts"],
                "evidence_counts": v04["evidence_counts"],
                "temperature_band_counts": v04["temperature_band_counts"],
                "temperature_ranges_K": v04["temperature_ranges_K"],
                "provenance_patches": v04["provenance_patches"],
                "table": {
                    "path": v04_table["path"],
                    "rows": v04_table["row_count"],
                    "sha256": v04_table["sha256"],
                    "measured_sha256": v04_on_disk,
                    "digest_matches_summary": v04_on_disk == v04_table["sha256"],
                    "expected_sha256": DIELECTRIC_V04_SHA256,
                },
                "frozen_v03_untouched": (
                    _sha256(REPOSITORY_ROOT / "data" / "dielectric_v03.csv")
                    == DIELECTRIC_V03_SHA256
                ),
                "boundary": (
                    "the succinonitrile leg stores the coldest existing observation "
                    "(333.15 K, epsilon 56.09) and invents no value; the "
                    "gamma-valerolactone conflict is stored as two rows and never "
                    "averaged, with the primary set to 36.9 by source quality."
                ),
            },
            "w17_2_thin_family_backfill_queue": {
                "probe": "probes/reaxys_thin_family_backfill.py",
                "target_families": thin["target_families"],
                "lower_bound": thin["lower_bound"],
                "family_report": thin["family_report"],
                "queue_rows": thin["queue_rows"],
                "queue_by_source": thin["queue_by_source"],
                "reaxys_queries_executed": thin["reaxys_queries_executed"],
                "restricted_title_index_available": thin[
                    "restricted_title_index_available"
                ],
                "restricted_contract": thin["restricted_contract"],
                "boundary": (
                    "this lane builds a queue and the rules for walking it; it executes "
                    "no query and writes no Reaxys value anywhere. reaxys_queries_executed "
                    "is 0."
                ),
                "honesty_boundaries": thin["honesty_boundaries"],
            },
            "w17_3_viscosity_v02": {
                "probe": "probes/build_viscosity_v02.py",
                "prereg": viscosity["prereg"],
                "table": v02_table,
                "value_layer": {
                    "path": v02_raw["path"],
                    "rows": v02_raw["rows"],
                    "sha256": v02_raw["sha256"],
                    "shipped_in_this_bundle": False,
                    "why": (
                        "81 MB value layer, offline-recomputable from "
                        "data/raw/thermoml_viscosity_pa_s/; kept git-ignored like density_raw"
                    ),
                },
                "catalog_slices": {
                    key: {k: v for k, v in value.items() if k != "dois"}
                    for key, value in viscosity["dataset"]["slices"].items()
                },
                "dual_basis_counts": v02_dual,
                "unfreeze": {
                    "local_rows": v02_unfreeze["local_rows"],
                    "local_keys": v02_unfreeze["local_keys"],
                    "exact_rows": v02_unfreeze["exact_rows"],
                    "nearest_rows": v02_unfreeze["nearest_rows"],
                    "converted_rows": v02_unfreeze["converted_rows"],
                    "pooled_rows": v02_unfreeze["pooled_rows"],
                    "deferred_multi_component_rows": (
                        v02_unfreeze["deferred_multi_component_rows"]
                    ),
                    "exact_tolerance_k": v02_unfreeze["exact_tolerance_k"],
                    "nearest_tolerance_k": v02_unfreeze["nearest_tolerance_k"],
                    "by_key": v02_unfreeze["by_key"],
                },
                "row_reconciliation": v02_recon,
                "group_overlap": {
                    "splitter": v02_overlap["splitter"],
                    "assertion": v02_overlap["assertion"],
                    "assertion_passed": v02_overlap["assertion_passed"],
                    "max_group_overlap": v02_overlap["max_group_overlap"],
                    "subset_rows": v02_overlap["subset_rows"],
                    "subset_groups": v02_overlap["subset_groups"],
                    "random_row": v02_overlap["random_row"],
                },
                "criteria": {
                    "a_online_slice": viscosity["criterion_a_online_slice"]["passed"],
                    "b_local_subset": viscosity["criterion_b_local_subset"]["passed"],
                    "c_unit_honesty": viscosity["criterion_c_unit_honesty"]["passed"],
                    "d_basis_honesty": viscosity[
                        "criterion_d_basis_honesty"
                    ]["passed"],
                },
                "run_telemetry": viscosity["run_provenance"]["run_telemetry"],
                "findings": viscosity["findings"],
                "limitations": viscosity["limitations"],
                "boundary": (
                    "record count, observation-row count and InChIKey count are three "
                    "different bases and are never divided by one another. The online "
                    "kinematic slice holds 1,391 accepted pure-component rows, but this "
                    "arm converted only the 176 local ones its pre-registration locked; "
                    "the multi-component rows are deferred, not split into roles."
                ),
            },
            "w17_4_density_v01": {
                "probe": "probes/build_density_v01.py",
                "table": {
                    "path": density_table["path"],
                    "rows": density_table["rows"],
                    "columns": density_table["columns"],
                    "sha256": density_table["sha256"],
                    "unit": density_table["unit"],
                },
                "catalog": {
                    "total_records": density["dataset"]["total_records"],
                    "slice_size_records": density["dataset"]["slice"]["size_records"],
                    "pages_fetched": density["dataset"]["slice"]["pages_fetched"],
                    "records_collected": density["dataset"]["slice"]["records_collected"],
                },
                "value_layer": density["value_layer"],
                "coverage_vs_dielectric_v03": {
                    "target_size": density_coverage["target_size"],
                    "density_size": density_coverage["density_size"],
                    "intersection_size": density_coverage["intersection_size"],
                    "covered_fraction": density_coverage["covered_fraction"],
                },
                "criteria": {
                    "a_catalog": density["criterion_a_catalog"]["passed"],
                    "b_values": density["criterion_b_values"]["passed"],
                    "c_unfreeze": density["criterion_c_unfreeze"]["passed"],
                    "d_honesty": density["criterion_d_honesty"]["passed"],
                },
                "unfreeze": {
                    "local_rows": unfreeze["local_rows"],
                    "local_keys": unfreeze["local_keys"],
                    "exact_rows": unfreeze["exact_rows"],
                    "unfreeze_rows": unfreeze["unfreeze_rows"],
                    "exact_tolerance_k": unfreeze["exact_tolerance_k"],
                    "by_key": unfreeze["by_key"],
                },
                "boundary": (
                    "the catalogue size is a count of records (ThermoML documents), not "
                    "of rows; the row-level layer is not comparable with the online "
                    "record counts. The two uses of density are declared apart: a "
                    "conversion factor for the viscosity line (available), and a "
                    "candidate feature for the epsilon model (must clear a coverage gate "
                    "on its own)."
                ),
                "findings": density["findings"],
                "limitations": density["limitations"],
            },
            "w17_5_liquid_window_gate": {
                "probe": "probes/build_liquid_window_features.py",
                "gate": gate,
                "coverage": window["coverage"],
                "coverage_set": window["coverage_set"],
                "trigger_rate_comparison": window["trigger_rate_comparison"],
                "confidence_counts": window["confidence_counts"],
                "property_coverage": window["property_coverage"],
                "sanity_checks": window["sanity_checks"],
                "upstream_agreement": window["upstream_agreement"],
                "outputs": window["outputs"],
                "run_telemetry": window["run_telemetry"],
                "caveats": window["caveats"],
            },
            "w17_6_coordination_block_merge": {
                "probe": "probes/dielectric_coordination_block_v3.py",
                "decision": verdict["decision"],
                "passed": verdict["passed"],
                "baseline_r2": verdict["baseline_r2"],
                "baseline_r2_published": verdict["baseline_r2_published"],
                "baseline_abs_delta": verdict["baseline_abs_delta"],
                "delta_r2": verdict["delta_r2"],
                "pass_bar": verdict["pass_bar"],
                "kill_line": verdict["kill_line"],
                "positive_repeats": verdict["positive_repeats"],
                "repeats_total": verdict["repeats_total"],
                "placebo_collapsed": verdict["placebo_collapsed"],
                "v1_decision_is_still_in_force": verdict["v1_decision_is_still_in_force"],
                "v2_decision_is_still_in_force": verdict["v2_decision_is_still_in_force"],
                "arms": {
                    name: arm_r2(name)
                    for name in ("baseline", "plus_lever4", "plus_lever8", "plus_both")
                },
                "merge_readings": merge,
                "collapse": collapse,
                "shots": block_shots,
                "reproduction_checks": block["reproduction_checks"],
                "run_telemetry": block["run_telemetry"],
                "honest_boundaries": block["honest_boundaries"],
                "boundary": (
                    "the merge arm and the two single arms share folds and the shuffled "
                    "label vector, so they are not independent samples; the merge shot "
                    "beats the baseline but its increment over the best single arm "
                    "(+0.011683591468432397) was never gated on, so it must not be read "
                    "as a proven increment, and the single-lever deltas are never added."
                ),
            },
            "w17_7_walden_and_dn": {
                "probe": "probes/walden_dn_channel.py",
                "decision": walden_decision,
                "joint_table_recount": recount,
                "walden_pairs": walden["walden_pairs"],
                "dn_channel": {
                    "coverage_threshold": dn["coverage_threshold"],
                    "coverage_definition": dn["coverage_definition"],
                    "admissible": dn["admissible"],
                    "audit_rows": dn["audit_rows"],
                    "admissibility_rule": dn["admissibility_rule"],
                    "gsds_audit": dn["gsds_audit"],
                    "acs_nano_audit": dn["acs_nano_audit"],
                },
                "kinematic_thaw": thaw,
                "kinematic_thaw_superseded_by": (
                    "the frozen W17-4 density table is on disk, so this arm's "
                    "pre-registered thaw condition is met: the 176 ThermoML kinematic "
                    "rows matched a density in 176/176 cases (|dT| <= 1e-3 K). The arm "
                    "itself still states only the family-level fact; whether the Walden "
                    "pairing is promoted from family level to row level is decided by "
                    "W17-3's pre-registration, not here."
                ),
                "run_telemetry": walden["run_telemetry"],
                "boundaries": walden["boundaries"],
            },
            "w17_9_four_channel_board": {
                "probe": "probes/four_channel_coverage.py",
                "channels": board["channels"],
                "board_rows": board["board_rows"],
                "pinned": pins,
                "main_scoreboard": board["main_scoreboard"],
                "random_row_leak_reference_r2": board["random_row_leak_reference_r2"],
                "outputs": board["outputs"],
                "boundaries": board["boundaries"],
                "headline": (
                    "HOMO and LUMO both clear their 0.2 eV gate "
                    "(0.19050925839013938 / 0.13855083976437643); IP and EA do not "
                    "(0.2010970559642009 / 0.23415453202842548) and stay coarse "
                    "screens; the viscosity line is red on MAE and stays family level; "
                    "redox is red with 392 labels as the bottleneck."
                ),
            },
            "w17_rx_reaxys_core_four_crosscheck": {
                "probe": "probes/reaxys_core_four_crosscheck.py",
                "status": (
                    "crosscheck only. The value-bearing artefacts live in the "
                    "repository and are withheld from this bundle under ruling B; "
                    "only non-value metadata is mirrored here."
                ),
                "session": {
                    "channel": reaxys["session"]["channel"],
                    "method": reaxys["session"]["method"],
                    "queries_executed": reaxys["session"]["queries_executed"],
                    "batch_crawling": reaxys["session"]["batch_crawling"],
                },
                "compliance": reaxys["compliance"],
                "substances_queried": reaxys["substances_queried"],
                "observation_rows": reaxys["observation_rows"],
                "observations_sha256": reaxys["observations_sha256"],
                "channel_verdicts": [
                    {
                        "channel": item["channel"],
                        "verdict": item["verdict"],
                        "rows_observed": item["rows_observed"],
                        "numeric_rows": item["numeric_rows"],
                        "numeric_share": item["numeric_share"],
                    }
                    for item in reaxys["channel_verdicts"]
                ],
                "queue_key_audit_summary": reaxys["queue_key_audit_summary"],
                "lesson_findings": {
                    item["lesson"]: item["finding"] for item in reaxys["lessons"]
                },
                "boundaries": reaxys["limitations"],
                "independent_recheck": {
                    "by": "the integrating agent, on the author's signed-in Edge session",
                    "date": "2026-09-26",
                    "method": (
                        "manual single-substance quick searches; no batch crawling"
                    ),
                    "facts": INDEPENDENT_RECHECK_FACTS,
                    "note": (
                        "a second hand re-ran the four load-bearing claims. "
                        "Every one reproduced; nothing in the crosscheck needed "
                        "a correction."
                    ),
                },
            },
        },
        "restricted_contract": {
            "decision": "reports/decisions_log.md section 28.2 (the author's ruling B)",
            "rule": (
                "Reaxys-derived value lists are excluded from outward-facing bundles, "
                "whole file; the repository keeps them verbatim as cross-check "
                "evidence. Nothing Reaxys-derived enters data/, any pool or any "
                "feature table."
            ),
            "values_enter_data": False,
            "values_enter_any_pool": False,
            "values_ship_in_this_bundle": False,
            "row_labels": ["reaxys_crosscheck_only", "restricted_crosscheck_only"],
            "repo_internal_only": [
                {
                    "path": relative,
                    "sha256": _sha256(REPOSITORY_ROOT / relative),
                    "carries_reaxys_values": carries_values,
                }
                for relative, carries_values in RESTRICTED_EXCLUDED
            ],
        },
        "frozen_red_lines": frozen,
        "frozen_red_lines_all_intact": all(entry["intact"] for entry in frozen.values()),
        "pool_definition_caveat": (
            "0.5332 and 0.5454 may only be quoted with their pool definitions "
            "(a 147-compound training pool against a 97-compound fixed scoring pool); "
            "they must never be compared against the v1.0 headline 0.364, which lives "
            "on the frozen 236-compound pool"
        ),
        "not_done_this_week": [
            (
                "the AL Round 4 P1 read (1,2-dimethoxypropane, DOI "
                "10.1021/acsenergylett.2c02003) and the six P3 lead-only actions were not "
                "executed; W17-1 delivered only the roster gap and the conflict ruling"
            ),
            (
                "W17-2 produced a queue and executed no Reaxys query, so the thin families "
                "are still at their measured sizes"
            ),
            (
                "W17-8 items stay out of scope by design: decomposition free energies, "
                "RDF/MD pipelines, IP/EA precision, and the paywalled Schrodinger rows"
            ),
        ],
        "verification": verification,
        "verification_passed": bool(verification.get("passed")),
        "artifacts": copied,
    }

    write_json(week_root / "week17_summary.json", summary)
    write_json(week_root / "verification.json", verification)
    (week_root / "README.md").write_text(README_TEXT, encoding="utf-8", newline="\n")
    write_sha256s(week_root)
    return summary


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
