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
new lever.  Since 2026-09-27 that same arm is also the *headline* of the main
scoreboard: the frozen baseline 0.4091179943351143 is reproduced to
`abs_delta = 0.0`, retained unchanged, and now sits beside the promoted headline
0.4766400383507876 in a versioned v2 pair.  The promotion re-reports a number that
was already measured and pre-registered; it adds no measurement and no shot.
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

# The main scoreboard is a versioned pair.  The baseline is the frozen W11/W12
# grouped hybrid reading and never moves; the headline is the W17-6 pre-registered
# merged arm (lever 4 + lever 8) that the author asked to be promoted on
# 2026-09-27.  Both numbers were measured long before the promotion.
MAIN_SCOREBOARD = 0.4091179943351143
MAIN_SCOREBOARD_VERSION = "v2"
MAIN_SCOREBOARD_HEADLINE_R2 = 0.4766400383507876
MAIN_SCOREBOARD_HEADLINE_DELTA_R2 = 0.0675220440156733
MAIN_SCOREBOARD_PROMOTED_AT_UTC = "2026-09-27T01:34:06Z"
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
    ("probes/reaxys_v1x_stocking_query.py", True),
    ("probes/reaxys_v1x_stocking_query_summary.json", True),
    ("probes/reaxys_v1x_stocking_query_facts.csv", False),
    ("reports/reaxys_v1x_stocking_query.md", True),
    ("tests/test_reaxys_v1x_stocking_query.py", False),
    ("probes/reaxys_v1x_stocking_query_round2.py", True),
    ("probes/reaxys_v1x_stocking_query_round2_summary.json", True),
    ("probes/reaxys_v1x_stocking_query_round2_facts.csv", False),
    ("reports/reaxys_v1x_stocking_query_round2.md", True),
    ("tests/test_reaxys_v1x_stocking_query_round2.py", False),
)

README_TEXT = """# Week 17 交付包（扩物质与多维度：黏度 v0.2 / 密度 / 液相窗口 / 配位块 / Walden / DN）

数据血缘: 规范数据集 `data/dielectric_v03.csv` **未改动**
（digest `ff2142936e…35ccce4`）；v1.0 已发布工件与 week11–week16 交付包未被触碰。
本周的扩容一律进**新版本表**：`data/dielectric_v04.csv`（248 行）、`data/density_v01.csv`
（182,154 行）、`data/viscosity_v02.csv`（42,941 行）；六件冻结件 digest **6/6 INTACT**。
生成脚本: `probes/export_week17_results.py`

## 头条（十九句话，都不许外推）

1. **四大核心数据的现状到此一眼可查**（四通道覆盖板，`four_channel_coverage.csv`，30 行）：
   **ε** 主记分牌自 2026-09-27 起是**版本化 v2 两行制**：**头条 `0.4766400383507876`**
   （Morgan+Physical ＋ 杠杆 4 ＋ 杠杆 8；457 行 / 97 化合物 = **276** 对），
   冻结**基线 `0.4091179943351143`** 逐位未动、并列保留（Δ `+0.0675220440156733`）；
   头条是**重报**已测得的预注册合并枪，**不新增测量、不新增 shot**，两个数字**只许各带配置引用、永不混比**；
   天花板仍是**信息缺口**（缺 Kirkwood g 维）不是行数缺口；**η** `group_key` R² `0.7481271437772365`、MAE
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
7. **Li⁺ 配位块转正，两枪合并已实测，并已被提升为主记分牌头条**：`plus_both` R² `0.4766400383507876`，
   对基线 Δ **+0.0675220440156733**（门 +0.0200），安慰剂塌缩 ✅，正向重复 9/10。
   **合并非加和**：朴素相加 = +0.0998972687629372，实测**低 0.0323752247472639**；
   合并枪相对最强单枪只多 +0.011683591468432397，**这一枪是本轮唯一一次主记分牌尝试**——
   提升不改这一条：它**不是新发现**（§22.5：11 枪 3 枪越线且同源），只是把已测得的数摆到头条。
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
16. **Reaxys 库存队列 P1+P2 实查：氧化还原的 392 条瓶颈不是「没有数据」，而是「数据不在数值列里」**
    （W17-16，**19** 物质 / **21** 次查询 / 预算 30）：P2 层 22 行里 3 行早前车道已读 ⇒ 未读集 **19** 个，
    逐通道（条数 / 有数值 / 点值）：ε **98/70/53**、η **144/130/90**、轨道 **70/30/30**、氧化还原 **27/0/0**。
    **两条新发现**：① `Electrochemical Characteristics` **整个分类没有数值列**——27 行里 **13** 行的电位只写在
    `Comment` 字符串里（`-2.57 V` / `2.24 V` / `> 3.2 V`），只读数值列的下游会看到 **0** 个氧化还原值；
    ② 队列自带的 `probed_in_this_round` 列**已过期**：3 行标 `no` 而早前车道已读过，**该列不能用来筛目标集**。
    轨道通道结论不变：**Reaxys 仍不提供可用的 HOMO/LUMO 数字**。按裁决 B 数值不进本包、不进 `data/`。
    第二轮（W17-20）把预算跑到 **30/30**、再实查 **7** 个物质（专挑芳环/卤代芳烃，因为它们的卡片氧化还原行最密）：
    氧化还原的**证据面**从 **27** 行扩到 **121** 行，但**有数值 / 点值仍是 0/0**——
    也就是说 P4 的 **392** 条标签瓶颈**在数值层面一条都没有缓解**（121 行里 58 行把电压写在 `Comment` 串里）。
17. 17. **THEMol 全量扩展：HOMO 通道翻过门，LUMO/gap 仍旧不可用**（W17-17）：把「关键名册 ∩ THEMol」
    的全部 **5,117** 个分子冻结成名册（`probes/themol_registry_expansion_roster.csv`，运行前锁 digest），
    同一 GFN2-xTB 单点链路跑到 **5,117 个（100.0%，`run_status = complete`）**，其中 **291 个分子此前没有任何轨道数值**、
    ε 名册命中 **142/247**。跨水平标定样本从 W17-14 的 **74 个锚**涨到 **4,668 对**：
    **HOMO r 0.8549、样本外 MAE 0.3036 eV ⇒ 两个门都过（`usable_with_flag`）**——W17-14 当时就是差 **0.0031 eV** 没过；
    但 **LUMO（r 0.6141，MAE 0.3495 eV，slope 0.1497）与 gap（r 0.4343，MAE 0.5910 eV）仍是 `reference_only`**，
    「半经验紧束缚的虚轨道不可用」被更大的样本重新确认。能级偏移 GFN2−Batt：HOMO **-1.2052 eV**（σ 0.4046，可平移）、
    LUMO **-7.5377 eV**（σ 1.9654，离散不可平移）。**Batt 与 PubChemQC 两列一个字节未改**，本臂 `models_fitted = 0`。
18. **OMat24 已核：不是分子、也没有任何轨道量 ⇒ 否决**（W17-18）：仓库 `facebook/OMAT24` 本体只有 5 个文件
    （15,388 B），真实数据托管在 HF 之外；实测解析 `val/rattled-300-subsampled` 的 **35,579** 条记录，
    20 个候选轨道 key（`homo`/`lumo`/`gap`/`bandgap`/`eigenvalues`/…）命中 **0**，
    `pbc` 全 `True`（**35,579/35,579**，非周期 0 条），元素前排是 Li/Tl/La/Y/Hg ⇒ 周期性无机晶体数据集。
    结构检索同样不可行（12 个标识 key 全 0 命中；5 个 ε 溶剂的分子式 5/5 无命中）。
    许可本身没有问题（**CC BY 4.0**）——**否决与许可无关**。
19. **W17-14 的 ε 子集在第二条独立代码路径上复现：逐位相同**（W17-19）：把 agent 手写链路的 **51** 个可比分子
    与官方层逐 InChIKey 对齐，ΔHOMO 最大 **1×10⁻⁴ eV**、ΔLUMO **1×10⁻⁴**、Δgap **2×10⁻⁴**
    （141 个通道里 108 个 Δ=0），**`themol_uuid` 一致率 100%（51/51）** ⇒ 同一构象、同一几何。
    同时纠正一处记录：那条链路的文件名写着 `eps142`，实际只有 **51** 个唯一分子（三个分片是同一批的重复跑），
    **W17-14 官方层才是权威列**。
20. **介电扩池四枪：训练池推到千位级，R2 仍未过 0.60**（W17-21 .. W17-24，`probes/dielectric_pool_expansion_*`）。
    计分侧全程冻结：**457 行 / 97 化合物（276 个 (化合物, T) 对）**、GroupKFold by InChIKey、10 重复 × 5 折 = **50 折**、seed 42；
    每枪脚本内都逐位复现冻结基线 **0.4091179943351143**（`baseline_abs_gap = 0.0`）。四枪都只动**训练池**，靶子 0.60：
    - **第 12 枪（外来化学空间，NBS 块 +362 行 / 360 化合物）**：主臂 `plus_expansion_hybrid` = **0.3809089252433510**（Δ −0.028209）⇒ `primary_missed`；Arm A PASS / **Arm B（剂量单调）FAIL**。
    - **第 13 枪（同源全表，训练池 2,029 行 / 148 化合物）**：co-primary `full_table_hybrid` = **0.530028742596643**、
      `full_table_lever4_lever8` = **0.49147018524319047** ⇒ `co_primaries_missed`。**非盲披露**：该枪的 `full_table_hybrid` 在预注册落盘前
      **36 秒**已被一个自称 `exploratory_not_promotable` 的诊断探针测到 0.530029，故只能读作「**事后选定臂 ＋ 预先写定判决规则下的重测**」，不是盲法确认。
      本枪最高读数是**不在 co-primary 名单**的 `full_table_lever4` = **0.5433111678100043**。
    - **第 14 枪（配位块铺满 987 → 1,462 行 / 88 → 125 化合物）**：co-primary `full_table_lever4_lever8full` = **0.48600023850174934**、
      `static_lever4_lever8full` = **0.4035089033119271** ⇒ `co_primaries_missed`；**Arm A ＋ Arm B 都 PASS**。四个复现锚点（0.4091 / 0.5300 / 0.5433 / 0.4915）**逐位命中**（`anchors_reproduced = true`）。
    - **第 15 枪（高 ε 锚点 +5 行 / 5 个全新化合物）**：主臂 `anchors_lever4` = **0.510231505819011** ⇒ `primary_missed`；Arm A ＋ Arm B 都 PASS。
    **五条杠杆的方向（各自带池定义，永不跨池相减）**：外来化学空间 **有害**（0.380909）；同源扩行 **唯一有效**（0.409118 → 0.530029，+0.1209）；
    配位块铺满 **无效**（0.491470 → 0.486000，**推翻了「覆盖太稀疏」的诊断**）；静态-only 训练池 **有害**（0.323041 ⇒ 435 条有限频率行不是污染，反而有用）；
    Reaxys 加宽 **读数作废**（`widened_lever4_lever8full` = 0.515154，但该臂把 Reaxys 受限值当训练标签，违反本仓红线「禁止任何受限值进入池或特征」，见 `reports/decisions_log.md` §28.33 —— **不得引用，也不得当作杠杆结论**）；高 ε 锚点 **有害**（0.510232）。**结论：天花板在表示能力，不在数据量。**
    **R2 > 0.60 未达到**；最好读数 **0.5433111678100043** 不是任何一枪的 co-primary、**不得提升**，冻结头条保持 **0.4766400383507876**。
    图：`probes/artifacts/w17_pool_expansion_{arms,dose,ceiling}.png`。
21. **新增开放数据源入库：ε 的 22 个可用源 ⇒ 96 行 / 31 化合物**（W17-24，`data/raw/open_data_eps2/`）：
    21 篇 **CC BY 4.0** 开放获取论文（Europe PMC 全文）＋ **Wikidata P5675（CC0）**；另有 **10 行 `reference_only`**
    （PubChem「Other Experimental Properties」8 行引自**许可不兼容**的版权手册、Zenodo 上传扫描件 2 行**无法核验**），两者**都不入训练池**。
    口径：`epsilon_unit = 1`、`frequency_mhz` 只在源给频率时填（**空 = 视作静态**，未插值）、`t_k` 只按源给温度换算；**未插值、未编造**。
    其中 5 行进了第 15 枪的锚点块（碳酸乙烯酯 **95.3**、碳酸丙烯酯 **64.9**、甲酸 **56.0**、硝基甲烷 **37.3**、HMPA **29.6**）。
22. **本轮对抗审计 ＋ 两处环境漂移收口**（W17-25）：审计报告原文入库 `reports/dielectric_pool_expansion_audit.md`
    （八问逐条处置见 `reports/decisions_log.md` §28.30 / §28.31 / §28.32）；`git ls-files` 普查因本轮新入库 8 件由
    **112 → 120**、总数 **133 → 141**；Uni-Mol 规格的 xTB 暂存被当日轨道批次**纯追加** 247 个目录（**246 → 493**），
    已在 spec 里留 `original_measurement` ＋ `remeasured_at_utc`。**两处都不改被锁文件的历史字节。**
23. **单一表示 0.6081 的换折种子复验：`>0.60` 是**种子 42 的运气**，但「Physical > 混合」跨 5 个种子成立**（W17-26，`probes/dielectric_representation_seed_robustness.py`）。
    W17 记录里**唯一** `>0.60` 的读数是 shot 13 的 **`full_table_lever4` / `Physical`（单表示）= 0.6080587938801277**（10 个重复里 **6 个** >0.60）；
    审计 `reports/dielectric_pool_expansion_audit.md` Q7 判定它是**单表示**读数、与预注册主判据（`Morgan+Physical` 混合）**不是同一口径**，**不得当作达标**。
    本枪**不动池**（2,029 行基表训练 / 457 行计分 / 97 化合物 / 10 重复 × 5 折 / GroupKFold by InChIKey），**只换折种子**（42, 1234, 2026, 31337, 7）；
    脚本先要求种子 42 在 **1e-9** 内逐位复现三个已登记读数（`abs_gap = 0.00e+00`）且折签名与冻结折一致，否则拒绝对外报告任何数。
    - **逐种子差值（Physical − Morgan+Physical）5/5 为正**（均值 **+0.044489**，最小 **+0.015919**）⇒ `confirmed_out_of_seed`：
      「Physical 更好」**不是**种子 42 的选择性偏差（机制读作「Morgan(ECFP) 块在该臂上净有害」，同臂 `Morgan` 单独跨种子均值仅 0.000550）；**但**
    - **跨种子平均 Physical = 0.586114**（sd 0.0175，range 0.565349–0.608059）⇒ **0.6081 含种子 42 的运气**，5 个种子里**只有 1 个** >0.60，**R² > 0.60 仍未达到**；
    - **反例（不许省略）**：在 `full_table_hybrid` 臂上方向**相反**（跨种子均值混合 **0.523136** > Physical **0.486277**）⇒ 结论**只在 lever4 配置下成立**，不是普适结论。
    本枪**非盲、诊断性**：任何读数**一律不提升**，冻结头条保持 **0.4766400383507876**、基线 **0.4091179943351143**。图：`probes/artifacts/w17_representation_seed_robustness.png`。
24. **换模型头一枪（shot 17）被否决：深度 2 是正则化器，不是欠拟合**（W17-27，`probes/dielectric_head_sweep.py`）。
    冻结头（200 棵树 / 深度 2 / lr 0.05）当年是为 **2048 维稀疏 Morgan** 定的；胜出的 `Physical(lever4)` 只有 **13–15** 列稠密特征，
    深度 2 = 每树 4 叶，**先验上几乎必然欠拟合**。本枪**只换头**，池 / 折 / 锚点全部冻结：
    锚点 `xgb_reference` 逐位复现 **0.6080587938801277**（`abs_gap = 0.0`）、50 折折签名与冻结折一致、泄漏审计 **350 折全 0**。
    seed 42 七臂：`xgb_reference` **0.608059** > `blend_uniform` **0.567035** > `xgb_deep`（d8 / 1200 / lr.03）**0.552121** >
    `extra_trees` **0.516236** > `kernel_ridge` **0.458044** > `selected_inner_cv` **0.372442** > `mlp` **0.121422**。
    ⇒ `verdict = refuted`，最佳增益 **−0.041024**（`blend_uniform`），**七臂无一超过冻结头**、`promoted = false`。
    **关键新负结果**：`selected_inner_cv` 在 50 折里选族 = `kernel_ridge` 25 / `mlp` 10 / `xgb_deep` 8 / `extra_trees` 4 / **冻结头只 3**
    ⇒ **内层选族系统性地选中表现最差的族**，在 97 化合物 / 276 样本的量级上内层 GroupKFold 选族**不可迁移**；
    ⇒ 由此得出 Week 18 的方法论约束：**网格必须预注册锁死，不得依赖内层 CV 选族**。
    本枪**非盲、诊断性**（对 seed 42），任何读数**一律不提升**。图：`probes/artifacts/w17_head_sweep.png`。
25. **AUC 侧车 ＋ 三档划分表：我们不是「模型差」，是「排序学会了、量级学不会」**（W18-F1 / W18-F2）。
    主链路 `evaluate_repeat` 其实一直在算 `auc_gt15` / `auc_gt30`，但 `METRIC_NAMES` 只带 7 个指标，**驱动冻结的 `REPEAT_COLUMNS_OUT`，于是所有 `*_repeats.csv` 都把两列丢了**。
    **侧车（W18-F1，`probes/dielectric_auc_sidecar.py`，零重拟合）**：从**已随包的** `*_predictions.csv` 重算 AUC，**不改 `METRIC_NAMES`、不改任何冻结字节**；
    5 个源里 R² 最大偏差 **0.00e+00**（逐位一致），最差源 `dielectric_coordination_block_v3`（230 组）**auc_gt30 = 0.7011**；
    **冻结头条臂 `plus_both` 的 auc_gt30 = 0.9579**（`baseline` 0.9401）、安慰剂 `placebo_shuffled_target` **0.5131**、`no_information_floor` **0.4647**。
    **三档划分 × AUC（W18-F2，`probes/dielectric_splitters_auc.py`）**：前三档**零重拟合重算**（最大 R² 差 0）＋ `scaffold` 本轮新跑（125.8 s）。
    **池是 1594 行 / 98 化合物 / 50 骨架族**（`dielectric_observations_v11` ＋ `dielectric_physical_features_v03`），**不是 457/97 的 ε 主记分牌池，两块池永不混比**。
    | 划分器 | Morgan r2/auc30 | Physical r2/auc30 | Morgan+Physical r2/auc30 |
    | --- | --- | --- | --- |
    | `random_row`（**泄漏参考，不可引用**） | +0.9010/0.9865 | +0.9383/0.9960 | **+0.9337/0.9938** |
    | `grouped`（化合物留出，唯一诚实口径） | −0.0678/0.6480 | −0.0880/0.8699 | **+0.1602/0.8412** |
    | `scaffold`（骨架留出，最苛刻） | −0.4104/0.5093 | −0.3904/0.8122 | **−0.0860/0.7358** |
    | `grouped_single_row`（温度扩表对照） | +0.0755/0.7416 | +0.1317/0.8718 | **+0.1861/0.8571** |
    ⇒ **叙事成立**：R² 从 `random_row` 的 **0.9337** 塌到 `grouped` 的 **0.1602**、再塌到 `scaffold` 的 **−0.0860**，
    而同一行的 **auc_gt30 只从 0.9938 → 0.8412 → 0.7358**（Spearman 同步塌：0.9676 → 0.4595 → 0.2084）。
    **结论：R² 量的是「量级」，AUC 量的是「排序」；我们排序学会了、量级没学会。**
    两块都**不提升任何冻结数**（`promoted = false`）；`random_row` 的 **0.9337 是泄漏参考、绝不可当达标题**。
    图：`probes/artifacts/w17_ordering_vs_magnitude.png`。
26. **ε 开放许可源二次普查（**复核性，非新检索**）：新源 0 / 净新增 0，「见底」未被推翻，并登记一处「raw 键集」口径缺口**（W17-28，`reports/w17_dielectric_source_sweep_v2.md`）。
    本臂**不联网、不跑新检索**：只对前几轮已抓回本地的**开放许可** ε 文件做**本地键集核算**，并把各轮已实测的源可达性结论汇总成一张 13 行逐源表。
    结论：**新源 0 个、可入库净新增化合物 0、净新增行 0**；上限仍是 **153 + 4 = 157**（最宽口径 **161**）
    ⇒ **「ε 开放许可源见底」本轮未被推翻**，千位级（10³）差两个数量级。
    新角度的阻断原因：NIST WebBook **无介电常数字段**、figshare 全程 **HTTP 403**、Dryad 检索 **0 命中**、
    Zenodo 8252886 只有 **785 张 PNG**（数值源自受限 DDB ⇒ 红线）、HF 命中全是无机 / MD / CC BY-NC-ND。
    **唯一新信息**：把三份已抓的开放许可文件按 InChIKey 去重后与 153 名单求差，另有 **58 个 raw 键**落在名单之外
    （`pubchem_eps` 26 ＋ `open_data_eps` 34 ＋ `open_data_eps2` 7，含重叠）；它们全部来自**已做过入库判定**的源，
    本轮**未重判**，故**不计入净新增**——这个「raw 键集 vs 已判定名单」的口径缺口在此显式登记。
    本臂 `models_fitted = 0`，不动任何冻结读数。逐源明细：`probes/dielectric_source_sweep_v2_sources.csv`。
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
| W17-16 | Reaxys 库存队列 P1+P2 实查（19 物质，**只核对，不入数据**） | probes/reaxys_v1x_stocking_query_facts.csv（**不进本包**） |
| W17-17 | THEMol/GFN2-xTB 全量轨道扩展（5,117 目标；跨水平标定重估） | data/processed/themol_orbital_layer_expanded.csv |
| W17-18 | OMat24 可行性审计（**否决**：无轨道量、非分子） | probes/omat24_feasibility_facts.json |
| W17-19 | W17-14 ε 子集在第二条代码路径上的独立复现 | probes/themol_eps_reproduction_facts.csv |
| W17-20 | Reaxys 库存队列第二轮（预算 30/30；**只核对，不入数据**） | probes/reaxys_v1x_stocking_query_round2_facts.csv（**不进本包**） |
| W17-21 | 介电扩池第 12 枪（外来化学空间 NBS；**未过 0.60**） | probes/dielectric_pool_expansion_summary.json |
| W17-22 | 介电扩池第 13 枪（同源全表 2,029 行；**未过 0.60**，含非盲披露） | probes/dielectric_pool_expansion_full_table_summary.json |
| W17-23 | 介电扩池第 14 枪（配位块铺满 ＋ Reaxys 加宽；**未过 0.60**） | probes/dielectric_pool_expansion_v3_summary.json |
| W17-24 | 介电扩池第 15 枪 ＋ 22 个开放源 96 行入库（**未过 0.60**） | probes/dielectric_anchor_summary.json |
| W17-25 | 扩池对抗审计 ＋ 交付前一致性收口（普查重钉 / xTB 暂存复核） | reports/dielectric_pool_expansion_audit.md |
| W17-26 | 单表示 0.6081 的换折种子复验（5 种子；**非盲、不提升**） | probes/dielectric_representation_seed_robustness_summary.json |
| W17-27 | 换模型头扫描（7 臂；**refuted、不提升**）＋ 内层选族不可迁移 | probes/dielectric_head_sweep_summary.json |
| W18-F | AUC 侧车（零重拟合）＋ 三档划分 × AUC 表（**排序 vs 量级**） | probes/dielectric_splitters_auc_summary.json |
| W17-28 | ε 开放许可源二次普查（**复核性，非新检索**；登记 raw 键集口径缺口） | reports/w17_dielectric_source_sweep_v2.md |

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
.\\.venv\\Scripts\\python.exe scripts\\verify_themol_orbital_layer_expanded.py --check
.\\.venv\\Scripts\\python.exe scripts\\verify_reaxys_v1x_stocking_probe_roster.py --check
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
- **扩池四枪的读数一律带池定义**：它们是**同一张 457 行计分池**上的**训练池**实验，与头条 0.4766 同池，可作方向比较；
  但与 v1.0 头条 `0.364`（236 化合物池）、`0.5332` / `0.5454`（147/97 化合物池）**永不混比**。另两条口径：
  **安慰剂臂不可跨枪比较**（第 13 枪 `0.05539621902141869` vs 第 14 枪 `0.1593289384795436`，打乱向量长度随池而变）；
  表中 R2 一律是**各 repeat 的 R² 均值**，直接对 `_folds.csv` 取均值会得到**另一套数**，两者不许相减。

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
    # W17-16 -- the Reaxys stocking-queue probe roster (a plan: no Reaxys value).
    ("probes/build_reaxys_v1x_stocking_probe_roster.py", "build_reaxys_v1x_stocking_probe_roster.py"),
    ("probes/reaxys_v1x_stocking_probe_roster.csv", "reaxys_v1x_stocking_probe_roster.csv"),
    ("probes/reaxys_v1x_stocking_probe_roster_summary.json", "reaxys_v1x_stocking_probe_roster_summary.json"),
    ("probes/reaxys_v1x_stocking_probe_prereg.json", "reaxys_v1x_stocking_probe_prereg.json"),
    ("scripts/verify_reaxys_v1x_stocking_probe_roster.py", "verify_reaxys_v1x_stocking_probe_roster.py"),
    ("reports/reaxys_v1x_stocking_probe_roster.md", "reaxys_v1x_stocking_probe_roster.md"),
    ("tests/test_reaxys_v1x_stocking_probe_roster.py", "test_reaxys_v1x_stocking_probe_roster.py"),
    # W17-17 -- THEMol/GFN2-xTB registry-wide orbital expansion.
    ("probes/build_themol_registry_expansion_roster.py", "build_themol_registry_expansion_roster.py"),
    ("probes/themol_registry_expansion_roster.csv", "themol_registry_expansion_roster.csv"),
    ("probes/themol_registry_expansion_roster_summary.json", "themol_registry_expansion_roster_summary.json"),
    ("probes/themol_registry_expansion_prereg.json", "themol_registry_expansion_prereg.json"),
    ("probes/build_themol_orbital_layer_expanded.py", "build_themol_orbital_layer_expanded.py"),
    ("probes/themol_orbital_layer_expanded_summary.json", "themol_orbital_layer_expanded_summary.json"),
    ("data/processed/themol_orbital_layer_expanded.csv", "data/processed/themol_orbital_layer_expanded.csv"),
    ("scripts/verify_themol_orbital_layer_expanded.py", "verify_themol_orbital_layer_expanded.py"),
    ("probes/plot_themol_registry_expansion.py", "plot_themol_registry_expansion.py"),
    ("probes/artifacts/themol_expansion_coverage.png", "themol_expansion_coverage.png"),
    ("probes/artifacts/themol_expansion_calibration.png", "themol_expansion_calibration.png"),
    ("reports/themol_orbital_layer_expanded.md", "themol_orbital_layer_expanded.md"),
    ("tests/test_themol_registry_expansion.py", "test_themol_registry_expansion.py"),
    ("probes/themol_expand_unit_recheck.py", "themol_expand_unit_recheck.py"),
    # What THEMol actually contains, keyed off the H5 bytes: the DFT orbital
    # energies we want are not in the dataset, MBIS atomic populations are.
    ("probes/themol_property_inventory.py", "themol_property_inventory.py"),
    ("probes/themol_property_inventory.json", "themol_property_inventory.json"),
    ("reports/themol_property_inventory.md", "themol_property_inventory.md"),
    ("tests/test_themol_property_inventory.py", "test_themol_property_inventory.py"),
    ("tests/test_themol_expand_unit_recheck.py", "test_themol_expand_unit_recheck.py"),
    # W17-17 addenda: the adversarial audit of this arm and the visual report.
    ("probes/audit_themol_expanded_layer.py", "audit_themol_expanded_layer.py"),
    ("probes/themol_expanded_layer_audit.json", "themol_expanded_layer_audit.json"),
    ("reports/themol_expanded_layer_audit.md", "themol_expanded_layer_audit.md"),
    ("tests/test_themol_expanded_layer_audit.py", "test_themol_expanded_layer_audit.py"),
    ("probes/plot_week17_channels.py", "plot_week17_channels.py"),
    ("reports/week17_visual_report.md", "week17_visual_report.md"),
    ("tests/test_plot_week17_channels.py", "test_plot_week17_channels.py"),
    ("probes/artifacts/w17_channels_gate_board.png", "w17_channels_gate_board.png"),
    ("probes/artifacts/w17_channels_label_inventory.png", "w17_channels_label_inventory.png"),
    ("probes/artifacts/w17_reaxys_round_tally.png", "w17_reaxys_round_tally.png"),
    ("probes/artifacts/w17_themol_calibration_parity.png", "w17_themol_calibration_parity.png"),
    ("probes/artifacts/w17_themol_level_offsets.png", "w17_themol_level_offsets.png"),
    ("probes/artifacts/w17_themol_tier_delivery.png", "w17_themol_tier_delivery.png"),
    # The independent reproduction of the W17-14 eps subset on a second code path.
    ("probes/themol_eps_reproduction.py", "themol_eps_reproduction.py"),
    ("probes/themol_eps_reproduction_facts.csv", "themol_eps_reproduction_facts.csv"),
    ("probes/themol_eps_reproduction_summary.json", "themol_eps_reproduction_summary.json"),
    ("reports/themol_eps_reproduction.md", "themol_eps_reproduction.md"),
    ("tests/test_themol_eps_reproduction.py", "test_themol_eps_reproduction.py"),
    # The OMat24 verdict: no orbital quantity, not molecular. A rejection with evidence.
    ("probes/omat24_feasibility_audit.py", "omat24_feasibility_audit.py"),
    ("probes/omat24_feasibility_facts.json", "omat24_feasibility_facts.json"),
    ("reports/omat24_feasibility.md", "omat24_feasibility.md"),
    ("tests/test_omat24_feasibility.py", "test_omat24_feasibility.py"),
    ("tests/test_omat24_feasibility.py", "test_omat24_feasibility.py"),
    # W17-21 .. W17-24 -- the dielectric pool-expansion shots 12-15, the
    # "add data and chase R2 > 0.60" round the author asked for.  The scoring pool
    # never moves; every shot widens the *training* pool only.
    ("probes/dielectric_pool_expansion_benchmark.py", "dielectric_pool_expansion_benchmark.py"),
    ("probes/dielectric_pool_expansion_prereg.json", "dielectric_pool_expansion_prereg.json"),
    ("probes/dielectric_pool_expansion_summary.json", "dielectric_pool_expansion_summary.json"),
    ("probes/dielectric_pool_expansion_full_table.py", "dielectric_pool_expansion_full_table.py"),
    ("probes/dielectric_pool_expansion_prereg_v2.json", "dielectric_pool_expansion_prereg_v2.json"),
    ("probes/dielectric_pool_expansion_full_table_summary.json", "dielectric_pool_expansion_full_table_summary.json"),
    ("probes/dielectric_pool_expansion_v3.py", "dielectric_pool_expansion_v3.py"),
    ("probes/dielectric_pool_expansion_prereg_v3.json", "dielectric_pool_expansion_prereg_v3.json"),
    ("probes/dielectric_pool_expansion_v3_summary.json", "dielectric_pool_expansion_v3_summary.json"),
    ("probes/dielectric_anchor_benchmark.py", "dielectric_anchor_benchmark.py"),
    ("probes/dielectric_anchor_prereg.json", "dielectric_anchor_prereg.json"),
    ("probes/dielectric_anchor_summary.json", "dielectric_anchor_summary.json"),
    ("probes/build_dielectric_anchor_blocks.py", "build_dielectric_anchor_blocks.py"),
    ("probes/dielectric_anchor_build_summary.json", "dielectric_anchor_build_summary.json"),
    ("probes/build_dielectric_pool_expansion.py", "build_dielectric_pool_expansion.py"),
    ("probes/dielectric_pool_expansion_build_summary.json", "dielectric_pool_expansion_build_summary.json"),
    ("probes/dielectric_coordination_block_full.py", "dielectric_coordination_block_full.py"),
    ("probes/dielectric_coordination_block_full_summary.json", "dielectric_coordination_block_full_summary.json"),
    # The non-blind exploratory diagnostic, shipped on purpose: the audit cites it.
    ("probes/dielectric_pool_expansion_diagnostic.py", "dielectric_pool_expansion_diagnostic.py"),
    ("probes/dielectric_pool_expansion_diagnostic.json", "dielectric_pool_expansion_diagnostic.json"),
    ("probes/dielectric_target_scale_explore.py", "dielectric_target_scale_explore.py"),
    ("probes/dielectric_target_scale_explore.json", "dielectric_target_scale_explore.json"),
    ("probes/plot_week17_pool_expansion.py", "plot_week17_pool_expansion.py"),
    ("reports/dielectric_pool_expansion.md", "dielectric_pool_expansion.md"),
    ("reports/dielectric_pool_expansion_full_table.md", "dielectric_pool_expansion_full_table.md"),
    ("reports/dielectric_pool_expansion_v3.md", "dielectric_pool_expansion_v3.md"),
    ("reports/dielectric_anchor.md", "dielectric_anchor.md"),
    ("reports/dielectric_pool_expansion_audit.md", "dielectric_pool_expansion_audit.md"),
    ("tests/test_dielectric_pool_expansion_v3.py", "test_dielectric_pool_expansion_v3.py"),
    ("probes/artifacts/dielectric_pool_expansion_folds.csv", "dielectric_pool_expansion_folds.csv"),
    ("probes/artifacts/dielectric_pool_expansion_repeats.csv", "dielectric_pool_expansion_repeats.csv"),
    ("probes/artifacts/dielectric_pool_expansion_full_table_folds.csv", "dielectric_pool_expansion_full_table_folds.csv"),
    ("probes/artifacts/dielectric_pool_expansion_full_table_repeats.csv", "dielectric_pool_expansion_full_table_repeats.csv"),
    ("probes/artifacts/dielectric_pool_expansion_v3_folds.csv", "dielectric_pool_expansion_v3_folds.csv"),
    ("probes/artifacts/dielectric_pool_expansion_v3_repeats.csv", "dielectric_pool_expansion_v3_repeats.csv"),
    ("probes/artifacts/dielectric_anchor_folds.csv", "dielectric_anchor_folds.csv"),
    ("probes/artifacts/dielectric_anchor_repeats.csv", "dielectric_anchor_repeats.csv"),
    ("probes/artifacts/dielectric_coordination_block_features_full.csv", "dielectric_coordination_block_features_full.csv"),
    ("probes/artifacts/w17_pool_expansion_arms.png", "w17_pool_expansion_arms.png"),
    ("probes/artifacts/w17_pool_expansion_dose.png", "w17_pool_expansion_dose.png"),
    ("probes/artifacts/w17_pool_expansion_ceiling.png", "w17_pool_expansion_ceiling.png"),
    # W17-24/25 addenda: the open-access epsilon sources gathered this round, the
    # processed tables the shots admit, and the per-shot fold/repeat ledgers.
    ("data/raw/open_data_eps2/observations.csv", "data/raw/open_data_eps2/observations.csv"),
    ("data/raw/open_data_eps2/reference_only.csv", "data/raw/open_data_eps2/reference_only.csv"),
    ("data/raw/open_data_eps2/coverage.json", "data/raw/open_data_eps2/coverage.json"),
    ("data/raw/open_data_eps2/report.md", "data/raw/open_data_eps2/report.md"),
    # W17-28 -- the open-licence epsilon frontier re-check (a re-check, not a new crawl).
    ("reports/w17_dielectric_source_sweep_v2.md", "w17_dielectric_source_sweep_v2.md"),
    ("probes/dielectric_source_sweep_v2_sources.csv", "dielectric_source_sweep_v2_sources.csv"),
    ("data/processed/dielectric_pool_expansion_observations.csv", "data/processed/dielectric_pool_expansion_observations.csv"),
    ("data/processed/dielectric_pool_expansion_features.csv", "data/processed/dielectric_pool_expansion_features.csv"),
    ("data/processed/dielectric_anchor_observations.csv", "data/processed/dielectric_anchor_observations.csv"),
    ("data/processed/dielectric_anchor_features.csv", "data/processed/dielectric_anchor_features.csv"),
    # W17-26 -- the seed-robustness re-measurement of the single-representation 0.6081.
    ("probes/dielectric_representation_seed_robustness.py", "dielectric_representation_seed_robustness.py"),
    (
        "probes/dielectric_representation_seed_robustness_prereg.json",
        "dielectric_representation_seed_robustness_prereg.json",
    ),
    (
        "probes/dielectric_representation_seed_robustness_summary.json",
        "dielectric_representation_seed_robustness_summary.json",
    ),
    ("probes/plot_representation_seed_robustness.py", "plot_representation_seed_robustness.py"),
    (
        "reports/dielectric_representation_seed_robustness.md",
        "dielectric_representation_seed_robustness.md",
    ),
    (
        "probes/artifacts/dielectric_representation_seed_robustness_repeats.csv",
        "dielectric_representation_seed_robustness_repeats.csv",
    ),
    (
        "probes/artifacts/w17_representation_seed_robustness.png",
        "w17_representation_seed_robustness.png",
    ),
    ("tests/test_representation_seed_robustness.py", "test_representation_seed_robustness.py"),
    # W17-27 -- the model-head sweep (refuted) and its inner-CV transferability finding.
    ("probes/dielectric_head_sweep.py", "dielectric_head_sweep.py"),
    ("probes/dielectric_head_sweep_prereg.json", "dielectric_head_sweep_prereg.json"),
    ("probes/dielectric_head_sweep_summary.json", "dielectric_head_sweep_summary.json"),
    ("probes/plot_head_sweep.py", "plot_head_sweep.py"),
    ("reports/dielectric_head_sweep.md", "dielectric_head_sweep.md"),
    (
        "probes/artifacts/dielectric_head_sweep_repeats.csv",
        "dielectric_head_sweep_repeats.csv",
    ),
    ("probes/artifacts/w17_head_sweep.png", "w17_head_sweep.png"),
    ("tests/test_head_sweep.py", "test_head_sweep.py"),
    # W18-F1 -- the AUC sidecar rebuilt from the shipped prediction rows, zero refits.
    ("probes/dielectric_auc_sidecar.py", "dielectric_auc_sidecar.py"),
    ("probes/dielectric_auc_sidecar_summary.json", "dielectric_auc_sidecar_summary.json"),
    ("probes/artifacts/dielectric_auc_sidecar.csv", "dielectric_auc_sidecar.csv"),
    ("reports/dielectric_auc_sidecar.md", "dielectric_auc_sidecar.md"),
    # W18-F2 -- the leak reference / honest / scaffold splitter table and its figure.
    ("probes/dielectric_splitters_auc.py", "dielectric_splitters_auc.py"),
    ("probes/dielectric_splitters_auc_summary.json", "dielectric_splitters_auc_summary.json"),
    ("probes/plot_splitters_auc.py", "plot_splitters_auc.py"),
    ("probes/artifacts/dielectric_splitters_auc.csv", "dielectric_splitters_auc.csv"),
    (
        "probes/artifacts/w17_ordering_vs_magnitude.png",
        "w17_ordering_vs_magnitude.png",
    ),
    ("reports/dielectric_splitters_auc.md", "dielectric_splitters_auc.md"),
    ("tests/test_auc_sidecar_and_splitters.py", "test_auc_sidecar_and_splitters.py"),
    ("reports/w17_core_property_coverage_audit.md", "w17_core_property_coverage_audit.md"),
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
    "scripts/verify_themol_orbital_layer_expanded.py --check",
    "scripts/verify_reaxys_v1x_stocking_probe_roster.py --check",
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
        "tests/test_reaxys_v1x_stocking_query.py tests/test_reaxys_v1x_stocking_probe_roster.py "
        "tests/test_themol_orbital_layer.py tests/test_export_week16_results.py "
        "tests/test_themol_registry_expansion.py tests/test_themol_eps_reproduction.py "
        "tests/test_omat24_feasibility.py "
        "tests/test_themol_expand_unit_recheck.py tests/test_themol_property_inventory.py "
        "tests/test_themol_expanded_layer_audit.py "
        "tests/test_plot_week17_channels.py tests/test_reaxys_v1x_stocking_query_round2.py "
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
    # The late week-17 arms: the Reaxys stocking queue, the THEMol registry-wide
    # expansion, the OMat24 verdict and the independent reproduction.
    stocking_roster = read_json(
        REPOSITORY_ROOT / "probes" / "reaxys_v1x_stocking_probe_roster_summary.json"
    )
    stocking_query = read_json(
        REPOSITORY_ROOT / "probes" / "reaxys_v1x_stocking_query_summary.json"
    )
    stocking_round2 = read_json(
        REPOSITORY_ROOT / "probes" / "reaxys_v1x_stocking_query_round2_summary.json"
    )
    themol_expanded = read_json(
        REPOSITORY_ROOT / "probes" / "themol_orbital_layer_expanded_summary.json"
    )
    omat24 = read_json(REPOSITORY_ROOT / "probes" / "omat24_feasibility_facts.json")
    eps_repro = read_json(
        REPOSITORY_ROOT / "probes" / "themol_eps_reproduction_summary.json"
    )

    pool_shot12 = read_json(
        REPOSITORY_ROOT / "probes" / "dielectric_pool_expansion_summary.json"
    )
    pool_shot13 = read_json(
        REPOSITORY_ROOT / "probes" / "dielectric_pool_expansion_full_table_summary.json"
    )
    pool_shot14 = read_json(
        REPOSITORY_ROOT / "probes" / "dielectric_pool_expansion_v3_summary.json"
    )
    pool_shot15 = read_json(
        REPOSITORY_ROOT / "probes" / "dielectric_anchor_summary.json"
    )
    pool_coord_full = read_json(
        REPOSITORY_ROOT / "probes" / "dielectric_coordination_block_full_summary.json"
    )
    pool_open_sources = read_json(
        REPOSITORY_ROOT / "data" / "raw" / "open_data_eps2" / "coverage.json"
    )
    seed_robust = read_json(
        REPOSITORY_ROOT / "probes" / "dielectric_representation_seed_robustness_summary.json"
    )
    head_sweep = read_json(
        REPOSITORY_ROOT / "probes" / "dielectric_head_sweep_summary.json"
    )
    auc_sidecar = read_json(
        REPOSITORY_ROOT / "probes" / "dielectric_auc_sidecar_summary.json"
    )
    splitters = read_json(
        REPOSITORY_ROOT / "probes" / "dielectric_splitters_auc_summary.json"
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
            "schema_version": 2,
            "version": MAIN_SCOREBOARD_VERSION,
            "headline": {
                "value": MAIN_SCOREBOARD_HEADLINE_R2,
                "configuration": (
                    "hybrid Morgan+Physical 0.5*(Morgan+Physical) plus lever 4 "
                    "(conformer-average dipole, 2 columns) plus lever 8 (Li+ coordination "
                    "block, 5 columns)"
                ),
                "delta_vs_baseline": MAIN_SCOREBOARD_HEADLINE_DELTA_R2,
                "source": (
                    "probes/dielectric_coordination_block_v3_summary.json"
                    "#arms.plus_both.Morgan+Physical"
                ),
                "pool": (
                    "457 rows / 97 compounds / 276 distinct (compound, temperature) pairs"
                ),
                "folds": "GroupKFold by InChIKey, 10 repeats x 5 folds, seed 42",
                "promoted_at_utc": MAIN_SCOREBOARD_PROMOTED_AT_UTC,
                "promotion_basis": (
                    "pre-registered merge arm (probes/dielectric_coordination_block_prereg_v3.json, "
                    "sha256 4d02a99b4677334123cd29597a16d531343adf34d2224799d0ca54e3b373399b), "
                    "verdict pass_merged_blocks, placebo collapsed, 9/10 repeats positive"
                ),
            },
            "baseline": {
                "value": MAIN_SCOREBOARD,
                "reproduced_abs_delta": verdict["baseline_abs_delta"],
                "reproduced": verdict["baseline_reproduced"],
                "status": "retained_unchanged",
                "still_used_as_the_comparability_anchor": True,
            },
            "value": MAIN_SCOREBOARD,
            "touched": True,
            "touched_by": (
                "W17-6 re-ran the frozen baseline and measured the merged arm; on "
                "2026-09-27 an explicit author instruction promoted that already-measured, "
                "pre-registered arm to the headline. The promotion adds no measurement."
            ),
            "baseline_reproduced": verdict["baseline_reproduced"],
            "baseline_abs_delta": verdict["baseline_abs_delta"],
            "promoted_r2": MAIN_SCOREBOARD_HEADLINE_R2,
            "headline_minus_baseline_r2": MAIN_SCOREBOARD_HEADLINE_DELTA_R2,
            "mixing_rule": (
                "the headline and the baseline may appear together only with this block's "
                "own configuration lines; they are never divided, added, or compared as two "
                "models, and neither is ever compared with the v1.0 headline 0.364"
            ),
            "note": (
                "0.4091179943351143 is reproduced to abs_delta = 0.0, is never quoted as a "
                "gain, and is retained unchanged beside the promoted headline."
            ),
            "caveats": [
                (
                    "the merged arm shares folds and the shuffled-label vector with the two "
                    "single arms; it is not an independent sample"
                ),
                (
                    "the +0.011683591468432397 over the best single arm has no gate of its "
                    "own and must not be read as a proven increment"
                ),
                (
                    "per decisions_log section 22.5 -- 11 shots, 3 over the line, all in the "
                    "same epsilon feature family -- this is not a new discovery"
                ),
            ],
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
                "main_scoreboard_version": board["main_scoreboard_version"],
                "main_scoreboard_headline": board["main_scoreboard_headline"],
                "main_scoreboard_headline_delta_r2": board[
                    "main_scoreboard_headline_delta_r2"
                ],
                "main_scoreboard_headline_source": board[
                    "main_scoreboard_headline_source"
                ],
                "random_row_leak_reference_r2": board["random_row_leak_reference_r2"],
                "outputs": board["outputs"],
                "boundaries": board["boundaries"],
                "headline": (
                    "HOMO and LUMO both clear their 0.2 eV gate "
                    "(0.19050925839013938 / 0.13855083976437643); IP and EA do not "
                    "(0.2010970559642009 / 0.23415453202842548) and stay coarse "
                    "screens; the viscosity line is red on MAE and stays family level; "
                    "redox is red with 392 labels as the bottleneck. The epsilon "
                    "scoreboard is quoted as a v2 pair: the promoted merged-arm headline "
                    "0.4766400383507876 beside the unchanged 0.4091179943351143 baseline."
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
        "late_arms": {
            "W17-16_reaxys_stocking_queue": {
                "roster": {
                    "path": "probes/reaxys_v1x_stocking_probe_roster.csv",
                    "sha256": _sha256(REPOSITORY_ROOT / "probes/reaxys_v1x_stocking_probe_roster.csv"),
                    "rows": (stocking_roster.get("roster") or {}).get("rows"),
                    "probe_target": (stocking_roster.get("counts") or {}).get("probe_target"),
                    "already_probed": (stocking_roster.get("counts") or {}).get("already_probed"),
                    "aromatic_non_electrolyte_suspects": (stocking_roster.get("counts") or {}).get(
                        "aromatic_non_electrolyte_suspect"
                    ),
                    "queries_executed": stocking_roster.get("queries_executed"),
                    "is_a_plan_not_a_measurement": stocking_roster.get("is_a_plan_not_a_measurement"),
                },
                "reader": {
                    "path": "probes/reaxys_v1x_stocking_query_facts.csv",
                    "sha256": _sha256(REPOSITORY_ROOT / "probes/reaxys_v1x_stocking_query_facts.csv"),
                    "substances_queried": stocking_query.get("substances_queried"),
                    "channel_tally": stocking_query.get("channel_tally"),
                },
                "carries_reaxys_values": False,
                "values_ship_in_this_bundle": False,
                "finding": (
                    "the Electrochemical Characteristics category has no numeric column at "
                    "all: 13 of its 27 rows carry the potential only inside the Comment "
                    "string, so a downstream reader of the value column sees zero redox "
                    "numbers; and the probed_in_this_round column shipped with the queue is "
                    "stale, with three rows marked no although earlier lanes had read them"
                ),
            },
            "W17-20_reaxys_stocking_round2": {
                "reader": {
                    "path": "probes/reaxys_v1x_stocking_query_round2_facts.csv",
                    "sha256": _sha256(
                        REPOSITORY_ROOT / "probes" / "reaxys_v1x_stocking_query_round2_facts.csv"
                    ),
                    "substances_queried": stocking_round2.get("substances_queried"),
                    "channel_tally": stocking_round2.get("channel_tally"),
                    "cumulative_queries": (stocking_round2.get("session") or {}).get(
                        "cumulative_queries"
                    ),
                    "redox_comment_audit": stocking_round2.get("redox_comment_audit"),
                },
                "carries_reaxys_values": False,
                "values_ship_in_this_bundle": False,
                "finding": (
                    "the second round spends the rest of the query budget (30/30) on seven "
                    "aromatic and halogenated substances picked because their cards are "
                    "redox-row dense; it grows the redox evidence surface from 27 to 121 rows "
                    "while the count of usable numeric redox labels stays at zero, because the "
                    "Electrochemical Characteristics category still has no numeric column"
                ),
            },
            "W17-17_themol_registry_expansion": {
                "layer": {
                    "path": "data/processed/themol_orbital_layer_expanded.csv",
                    "sha256": _sha256(
                        REPOSITORY_ROOT / "data/processed/themol_orbital_layer_expanded.csv"
                    ),
                },
                "run_status": themol_expanded.get("run_status"),
                "delivered_rows": themol_expanded.get("delivered_rows"),
                "roster_rows": themol_expanded.get("roster_rows"),
                "rows_by_tier": themol_expanded.get("rows_by_tier"),
                "calibration": {
                    channel: {
                        "status": payload.get("status"),
                        "n": payload.get("n"),
                        "pearson_r_in_sample": payload.get("pearson_r_in_sample"),
                        "pearson_r_out_of_sample": payload.get("pearson_r_out_of_sample"),
                        "status_basis": payload.get("status_basis"),
                        "mae_out_of_sample_eV": payload.get("mae_out_of_sample_eV"),
                    }
                    for channel, payload in themol_expanded.get("calibration", {}).items()
                },
                "coverage": themol_expanded.get("coverage"),
                "level_offsets_gfn2_minus_batt": themol_expanded.get(
                    "level_offsets_gfn2_minus_batt"
                ),
                "models_fitted": themol_expanded.get("models_fitted"),
            },
            "W17-18_omat24_feasibility": {
                "verdict": omat24.get("verdict"),
                "verdict_reason": omat24.get("verdict_reason"),
                "reason": (
                    "periodic inorganic crystals with energy / forces / stress labels only "
                    "and no orbital quantity; not usable for solvent HOMO/LUMO"
                ),
                "license": (omat24.get("q5_license") or {}).get("card_license_field"),
            },
            "W17-19_eps_reproduction": {
                "matched_keys": (eps_repro.get("match") or {}).get("matched"),
                "chain_b_unique_keys": (eps_repro.get("match") or {}).get("chain_b_keys"),
                "max_abs_delta_eV": eps_repro.get("max_abs_delta_eV"),
                "uuid_agreement_rate": (eps_repro.get("uuid") or {}).get("match_rate"),
                "note": (
                    "the second code path reproduces the W17-14 layer; the chain that "
                    "shipped as eps142 actually carries 51 unique molecules"
                ),
            },
            "W17-21_dielectric_pool_expansion": {
                "probe": "probes/dielectric_pool_expansion_v3.py",
                "scoring_pool_frozen": {
                    "rows_scored": pool_shot14["pool"]["scored_rows"],
                    "compounds_scored": 97,
                    "compound_temperature_pairs": 276,
                    "folds": 50,
                    "grouping": "GroupKFold by InChIKey, 10 repeats x 5 folds, seed 42",
                    "frozen_baseline_r2": 0.4091179943351143,
                    "baseline_reproduced_in_every_shot": True,
                },
                "target_r2": 0.6,
                "target_met": False,
                "promoted_headline_unchanged_r2": MAIN_SCOREBOARD_HEADLINE_R2,
                "best_reading": {
                    "r2": 0.5433111678100043,
                    "arm": "full_table_lever4",
                    "shot": "shot 13",
                    "pool": (
                        "training pool = the 2,029-row same-source full table; the "
                        "scoring pool is the same frozen 457-row pool"
                    ),
                    "promotable": False,
                    "why_not": (
                        "it is not a co-primary of any shot: shot 13 named "
                        "full_table_hybrid and full_table_lever4_lever8, and neither "
                        "passed 0.60"
                    ),
                },
                "shots": {
                    "shot_12_foreign_space": {
                        "prereg": "probes/dielectric_pool_expansion_prereg.json",
                        "summary": "probes/dielectric_pool_expansion_summary.json",
                        "pool": pool_shot12["expansion"],
                        "primary_arm": pool_shot12["verdict"]["primary_arm"],
                        "primary_r2": pool_shot12["verdict"]["primary_r2"],
                        "decision": pool_shot12["verdict"]["decision"],
                        "arm_a_pass": pool_shot12["verdict"]["arm_a_pass"],
                        "arm_b_pass": pool_shot12["verdict"]["arm_b_pass"],
                    },
                    "shot_13_same_source_full_table": {
                        "prereg": "probes/dielectric_pool_expansion_prereg_v2.json",
                        "summary": "probes/dielectric_pool_expansion_full_table_summary.json",
                        "pool": pool_shot13["pool"],
                        "co_primary_values": pool_shot13["verdict"]["co_primary_values"],
                        "decision": pool_shot13["verdict"]["decision"],
                        "arm_a_pass": pool_shot13["verdict"]["arm_a_pass"],
                        "arm_b_pass": pool_shot13["verdict"]["arm_b_pass"],
                        "not_blind": (
                            "an exploratory, explicitly non-promotable diagnostic measured "
                            "full_table_hybrid at 0.530029 36 seconds before this prereg "
                            "landed, so the value is a post-hoc chosen arm re-measured "
                            "under a pre-written decision rule, not a blind confirmation"
                        ),
                    },
                    "shot_14_block_full_plus_reaxys_widening": {
                        "prereg": "probes/dielectric_pool_expansion_prereg_v3.json",
                        "summary": "probes/dielectric_pool_expansion_v3_summary.json",
                        "pool": pool_shot14["pool"],
                        "arms": {
                            name: block["r2"] for name, block in pool_shot14["arms"].items()
                        },
                        "co_primary_values": pool_shot14["verdict"]["co_primary_values"],
                        "decision": pool_shot14["verdict"]["decision"],
                        "arm_a_pass": pool_shot14["verdict"]["arm_a_pass"],
                        "arm_b_pass": pool_shot14["verdict"]["arm_b_pass"],
                        "anchors_reproduced": pool_shot14["verdict"]["anchors_reproduced"],
                        "coordination_block_full": pool_coord_full,
                    },
                    "shot_15_high_epsilon_anchors": {
                        "prereg": "probes/dielectric_anchor_prereg.json",
                        "summary": "probes/dielectric_anchor_summary.json",
                        "pool": pool_shot15["pool"],
                        "co_primary_values": pool_shot15["verdict"]["co_primary_values"],
                        "decision": pool_shot15["verdict"]["decision"],
                        "arm_a_pass": pool_shot15["verdict"]["arm_a_pass"],
                        "arm_b_pass": pool_shot15["verdict"]["arm_b_pass"],
                        "anchors_reproduced": pool_shot15["verdict"]["anchors_reproduced"],
                    },
                },
                "lever_directions": {
                    "rule": (
                        "every number keeps its own pool definition; these are directions, "
                        "never subtractions across pools"
                    ),
                    "foreign_chemical_space": "harmful (0.380909 vs 0.409118)",
                    "same_source_more_rows": "the only effective lever (0.409118 -> 0.530029)",
                    "coordination_block_filled": "ineffective (0.491470 -> 0.486000)",
                    "static_only_training_pool": "harmful (0.323041)",
                    "reaxys_widening": (
                        "VOID, not a reading: this arm trained on Reaxys-restricted "
                        "values, which breaches the standing rule that no restricted "
                        "value may enter any pool or feature table "
                        "(reports/decisions_log.md section 28.33). It must not be cited "
                        "and carries no lever conclusion."
                    ),
                    "high_epsilon_anchors": "harmful (0.510232 vs 0.543311)",
                },
                "ceiling_finding": (
                    "the ceiling is representational capacity, not data volume: the row "
                    "count already reaches the four-digit range while the compound count "
                    "is capped by what the sources carry, and the extreme-epsilon "
                    "compounds have no same-family training labels inside the fold that "
                    "tests them"
                ),
                "open_access_sources": {
                    "path": "data/raw/open_data_eps2/",
                    "counts": pool_open_sources["counts"],
                    "boundary": (
                        "the 10 reference-only rows never enter the training pool; an "
                        "empty frequency_mhz means static, nothing is interpolated"
                    ),
                },
                "audit": "reports/dielectric_pool_expansion_audit.md",
                "report": "reports/dielectric_pool_expansion_v3.md",
            },
            "W17-26_representation_seed_robustness": {
                "probe": "probes/dielectric_representation_seed_robustness.py",
                "prereg": {
                    "path": "probes/dielectric_representation_seed_robustness_prereg.json",
                    "sha256": seed_robust["prereg"]["sha256"],
                    "status": seed_robust["prereg"]["status"],
                },
                "question": (
                    "the only reading above 0.60 in the whole W17 record is "
                    "full_table_lever4 / Physical = 0.6080587938801277; it is a "
                    "single-representation reading that the pre-registered primary "
                    "criterion (the Morgan+Physical hybrid) does not cover, so the "
                    "question is whether it is an artifact of the frozen fold seed 42"
                ),
                "frozen_side_unchanged": True,
                "frozen_baseline_r2": 0.4091179943351143,
                "frozen_headline_unchanged_r2": MAIN_SCOREBOARD_HEADLINE_R2,
                "seeds": seed_robust["contract"]["seeds"],
                "seed_42_anchors_reproduced": seed_robust["anchors"]["reproduced"],
                "leakage_clean": seed_robust["leakage"]["clean"],
                "seed_42_single_representation_r2": seed_robust["seed42_single_representation"],
                "hypothesis": {
                    "statement": seed_robust["hypothesis"]["statement"],
                    "arm": seed_robust["hypothesis"]["arm"],
                    "verdict": seed_robust["hypothesis"]["verdict"],
                    "positive_seeds": seed_robust["hypothesis"]["positive_seeds"],
                    "total_seeds": seed_robust["hypothesis"]["total_seeds"],
                    "delta_mean": seed_robust["hypothesis"]["delta_mean"],
                    "delta_min": seed_robust["hypothesis"]["delta_min"],
                },
                "cross_seed_means": {
                    row["arm"] + "/" + row["representation"]: row["r2_seed_mean"]
                    for row in seed_robust["seed_averaged"]
                },
                "target_r2": 0.6,
                "target_met": False,
                "reading_never_promoted": True,
                "finding": (
                    "the Physical > Morgan+Physical ordering on full_table_lever4 holds on "
                    "5 of 5 fresh fold seeds, so it is not a seed-42 artifact; but the "
                    "cross-seed mean of Physical is 0.586114 with a range of "
                    "0.565349-0.608059, i.e. the 0.6081 itself is partly seed-42 luck and "
                    "0.60 is not reached; and on full_table_hybrid the ordering reverses, "
                    "so the effect is specific to the lever4 configuration"
                ),
                "counterexample": (
                    "full_table_hybrid cross-seed means: Morgan+Physical 0.523136 > "
                    "Physical 0.486277"
                ),
                "open_source_frontier": (
                    "an independent open-licence sweep run this round found no new "
                    "epsilon source: net-new compounds are approximately zero (upper "
                    "bound 4, all from the ThermoML archive the repo already carries); "
                    "the sweep evidence is local-only and ships in no bundle"
                ),
                "non_blind": True,
                "promotable": False,
                "report": "reports/dielectric_representation_seed_robustness.md",
                "figure": "probes/artifacts/w17_representation_seed_robustness.png",
            },
            "W17-27_model_head_sweep": {
                "probe": "probes/dielectric_head_sweep.py",
                "prereg": {
                    "path": head_sweep["prereg"]["path"],
                    "sha256": head_sweep["prereg"]["sha256"],
                    "status": head_sweep["prereg"]["status"],
                },
                "question": (
                    "the frozen head (200 trees / depth 2 / lr 0.05) was chosen for a "
                    "2048-dim sparse Morgan matrix; the winning Physical(lever4) "
                    "configuration has only 13-15 dense columns, so is depth 2 simply "
                    "underfitting? swap the head at the same frozen pool, folds and anchors"
                ),
                "pool": head_sweep["pool"],
                "anchors": head_sweep["anchors"],
                "leakage_clean": head_sweep["leakage"]["clean"],
                "leakage_folds": head_sweep["leakage"]["folds_by_seed"],
                "heads": [row["head"] for row in head_sweep["cross_seed"]],
                "head_r2": {
                    row["head"]: row["r2_seed_mean"] for row in head_sweep["cross_seed"]
                },
                "head_improvement_vs_reference": {
                    row["head"]: row["improvement_vs_reference"]
                    for row in head_sweep["cross_seed"]
                },
                "reference_head": head_sweep["answers"]["reference_head"],
                "reference_r2": head_sweep["answers"]["reference_r2"],
                "best_head": head_sweep["answers"]["best_head"],
                "best_r2": head_sweep["answers"]["best_r2"],
                "best_improvement": head_sweep["answers"]["best_improvement"],
                "target_r2": head_sweep["answers"]["target_r2"],
                "partial_target_r2": head_sweep["answers"]["partial_target_r2"],
                "verdict": head_sweep["verdict"],
                "target_met": head_sweep["answers"]["target_met_at_anchor_seed"],
                "inner_cv_choices": head_sweep["inner_cv_choices"],
                "finding": (
                    "no head beats the frozen reference: the best is blend_uniform at "
                    "0.567035 against the reference 0.608059, a gain of -0.041024, so "
                    "depth 2 is a regulariser rather than an underfit knob and capacity "
                    "is not the ceiling; the deeper tree loses 0.055938 and the MLP "
                    "collapses to 0.121422"
                ),
                "inner_cv_finding": (
                    "selected_inner_cv picked kernel_ridge in 25 of 50 folds, mlp in 10, "
                    "xgb_deep in 8, extra_trees in 4 and the frozen head only 3 -- the "
                    "inner GroupKFold systematically picks the worst families, so family "
                    "selection is not transferable at the 97-compound / 276-sample scale "
                    "and any W18 grid must be pre-registered and locked"
                ),
                "non_blind": True,
                "promotable": False,
                "report": "reports/dielectric_head_sweep.md",
                "figure": "probes/artifacts/w17_head_sweep.png",
                "repeats": "probes/artifacts/dielectric_head_sweep_repeats.csv",
            },
            "W18-F1_auc_sidecar": {
                "probe": "probes/dielectric_auc_sidecar.py",
                "why": auc_sidecar["why"],
                "metric_names_shipped": auc_sidecar["metric_names_shipped"],
                "metric_names_extended": auc_sidecar["metric_names_extended"],
                "r2_tolerance": auc_sidecar["r2_tolerance"],
                "worst_r2_abs_gap": auc_sidecar["worst_r2_abs_gap"],
                "sources": {
                    name: {
                        "scored_groups": block["counts"]["scored_groups"],
                        "max_r2_abs_gap": block["max_r2_abs_gap"],
                        "auc_gt15_mean": block["auc_gt15_mean"],
                        "auc_gt30_mean": block["auc_gt30_mean"],
                    }
                    for name, block in auc_sidecar["sources"].items()
                },
                "finding": (
                    "the AUC columns can be restored from the shipped prediction rows "
                    "with zero refits: the largest R2 deviation from the shipped repeats "
                    "is 0.00e+00 across all five sources, so the magnitude metric is "
                    "unchanged and only the ordering metric is added"
                ),
                "frozen_repeats_untouched": auc_sidecar["frozen_repeats_untouched"]["note"],
                "promotable": False,
                "table": "probes/artifacts/dielectric_auc_sidecar.csv",
                "report": "reports/dielectric_auc_sidecar.md",
            },
            "W18-F2_splitters_auc": {
                "probe": "probes/dielectric_splitters_auc.py",
                "question": splitters["question"],
                "frozen_side": splitters["frozen_side"],
                "pool": splitters["new_run"],
                "protocol_notes": splitters["protocol_notes"],
                "protocol_order": splitters["protocol_order"],
                "primary": splitters["primary"],
                "reused_from_shipped_predictions": splitters["reused_from_shipped_predictions"],
                "reused_max_r2_abs_gap": splitters["reused_max_r2_abs_gap"],
                "shipped_predictions_sha256": splitters["shipped_predictions_sha256"],
                "by_protocol": splitters["by_protocol"],
                "pool_caveat": (
                    "this pool is 1594 rows / 98 compounds / 50 scaffold groups from "
                    "dielectric_observations_v11 + dielectric_physical_features_v03; it is "
                    "NOT the 457-row / 97-compound epsilon scoreboard pool, and the two "
                    "must never be subtracted or mixed"
                ),
                "finding": (
                    "R2 collapses from 0.9337 (random_row) to 0.1602 (grouped) to "
                    "-0.0860 (scaffold) while auc_gt30 only falls from 0.9938 to 0.8412 "
                    "to 0.7358 on the same arm and representation: the ordering metric "
                    "survives compound and scaffold holdout far better than the magnitude "
                    "metric, i.e. the ranking is learned and the magnitude is not"
                ),
                "random_row_is_a_leak_reference": True,
                "promotable": False,
                "report": "reports/dielectric_splitters_auc.md",
                "figure": "probes/artifacts/w17_ordering_vs_magnitude.png",
                "table": "probes/artifacts/dielectric_splitters_auc.csv",
            },
            "W17-28_open_licence_source_recheck": {
                "report": "reports/w17_dielectric_source_sweep_v2.md",
                "candidates": "probes/dielectric_source_sweep_v2_sources.csv",
                "nature": (
                    "a close-out re-check, not a new crawl: local key-set accounting over "
                    "already-fetched open-licence files plus a per-source reachability "
                    "table that summarises earlier rounds"
                ),
                "new_sources": 0,
                "net_new_compounds": 0,
                "net_new_rows": 0,
                "roster_size": 153,
                "upper_bound_compounds": 157,
                "widest_bound_compounds": 161,
                "frontier_exhausted_not_overturned": True,
                "raw_keys_outside_the_roster": 58,
                "raw_keys_note": (
                    "pubchem_eps 26 + open_data_eps 34 + open_data_eps2 7 (overlapping) "
                    "raw keys fall outside the 153 roster, but they all come from sources "
                    "that already went through an admission ruling and were not re-judged "
                    "here, so they do not count as net-new; the 153/157-161 bound therefore "
                    "only holds under the already-adjudicated convention"
                ),
                "blocking_reasons": {
                    "nist_webbook": "no dielectric-constant field at all",
                    "figshare_api": "HTTP 403 at the CDN layer, unreachable",
                    "dryad_api": "search for dielectric constant solvent returned 0 hits",
                    "zenodo_8252886": "785 PNG images only; values come from the restricted DDB",
                    "hf_hits": "inorganic crystals, MD boxes, or a CC BY-NC-ND licence",
                },
                "models_fitted": 0,
                "promotable": False,
            },
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
