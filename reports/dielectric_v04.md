# dielectric v0.4 —— Week 17 名册补丁（succinonitrile 花名册缺口 + GVL 双行冲突）

**一句话**：v0.4 = 冻结的 v0.3 名册（246 行）**逐字保留** + 2 行新条目；v0.3 文件一字未动
（digest `ff2142936e06e04b329b70f8597574f75349e54ce876e9fff81309e6d35ccce4`）。

生成脚本：`scripts/build_dielectric_v04.py`；独立复核：`scripts/verify_dielectric_v04.py`
（8 档检查全 PASS）；护栏：`tests/test_dielectric_v04.py`（10 passed）。

## 1. 两行入库，来源各自独立

| # | patch_kind | 化合物 | InChIKey | 取值 | T | 来源 | model_ready |
|---|---|---|---|---|---|---|---|
| 1 | `roster_gap_fill` | succinonitrile | `IAHFWCOBPZCAEA-UHFFFAOYSA-N` | 56.09 | 333.15 K | `10.1021/je300958c`（Świergiel & Jadżyn 2013, JCED 58, 128-131） | false |
| 2 | `conflict_dual_row` | gamma-valerolactone | `GAEKPEKOJKCEMS-UHFFFAOYSA-N` | 36.9 | 298.15 K（温度未报） | `10.1016/j.ica.2021.120372`（Segato 等 2021, Inorg. Chim. Acta 522, 120372, SI） | false |

行数：246（v0.3）→ **248**（v0.4）；唯一 InChIKey 数 **247**（GVL 两行是**有意**的重复键）。
`dataset_origin` 计数：`v0.2` 210 / `v0.3_addition` 36 / `v0.4_addition` 2。
温度带计数：`room_temperature` 246 / `extended_temperature` 1 / `high_temperature` 1。

## 2. succinonitrile：这是名册缺口，不是数据缺口

- 观测层（`data/processed/dielectric_observations_v11plus.csv`）**早就有 17 行**，17 个不同温度，
  区间 **333.15 K – 373.15 K**（60–100 °C），DOI `10.1021/je300958c`；缺的只是 v0.3 名册里的一行。
- 存入的一腿 = **最低温观测**（333.15 K，ε = 56.09，combined 不确定度 0.1，95%）——**没有生成任何新数值**。
- 整个温区在 v0.3 的 extended 窗（313.15–323.15 K）**之上**。v0.4 **没有**去悄悄放宽 v0.3 的带，
  而是**显式声明**一个新带 `high_temperature`（333.15–373.15 K）；v0.3 的 `temperature_band()` 先被调用，
  只有它拒绝的温度才可能落到新带。房间窗内**没有任何观测**，所以该行 `model_ready = false`。
- 该行的数值事实**已经**提交在 v1.x 观测表里，故 `redistribution_status = allowed`，不另声明源许可。

## 3. GVL：双行带 provenance，冲突不平均

- 36.9（Segato 2021, SI，**第一手测量**）vs 36.1（iScience 2026 Table 3，**开放获取综述表**，v0.3 既有行）。
- 两腿**各自成行**，`dielectric` 分别 36.9 / 36.1，**未做任何平均**；两腿都**没有温度**，
  所以新腿 `model_ready = false`。
- **主值按源质量定**：第一手 SI 测量（36.9）是更强的腿。裁决理由按 W17-1 要求写进
  `reports/decisions_log.md` §28.4。
- **既有腿的 `model_ready` 是保护字段**（v0.3 写下的 `true`）：v0.4 **不就地改写**，只允许对
  **非保护字段**打补丁。v0.4 对既有腿只改了两格：
  `conflict_status`（补成 `unresolved_dual_row_review_table_36.1_vs_primary_si_36.9`）与
  `notes`（写明冲突与"新腿是主值"）。**8 档检查里有一条专门断言：除这两个声明过的格，
  246 行 v0.3 行一字未动，且没有任何保护字段被改。**
- 遗留不一致**登记不修**：既有腿的 `model_ready = true` 写于竞争腿被发现之前；字段受保护，
  故登记给将来的 v0.5 决定，而不是在本版静默放宽。

## 4. 一个附带发现：Reaxys 队列把 GVL 的 InChIKey 标错了

`probes/reaxys_dielectric_queue_first_cut.csv` 第 3 行把 gamma-valerolactone 的 InChIKey 记成
`JYVATQXCHBTGRN-UHFFFAOYSA-N`，而 **RDKit 与冻结的 v0.3 行都给 `GAEKPEKOJKCEMS-UHFFFAOYSA-N`**
（SMILES `CC1CCC(=O)O1`）。v0.4 用**正确**的键。Reaxys 队列文件**逐字保留、不回改**，本差异只在此登记。

另：队列与该 DOI 都不带 Crossref 号，本轮**独立经 Crossref** 核到
`10.1016/j.ica.2021.120372`（Inorg. Chim. Acta v522, article 120372, 2021-07，作者
Segato / Baratta / Belanzoni / Belpassi / Del Zotto / Zuccaccia —— 与队列所记作者、卷号一致）。

## 5. 纪律与红线复核（本臂落盘时实测）

- 六件冻结件 **6/6 INTACT**；v0.3 digest 逐位不变。
- 预注册先于执行：v0.4 的判据（带定义、`patch_kind` 枚举、保护字段集合、重复键白名单）写在生成脚本里，
  并在生成时对 `dataset_origin`、温度带、保护字段**硬断言**。
- 冲突不平均：GVL 两腿各占一行，`dielectric` 未被覆盖或平均。
- 文本产物一律 LF（含 `data/dielectric_v04.csv`、两个补丁表、`probes/dielectric_v04_summary.json`）。
- `scripts/export_results_common.py::write_json` 的 CRLF 缺陷本轮顺手修复（见 decisions_log §28.3）。

## 6. 复现

    .\.venv\Scripts\python.exe scripts\build_dielectric_v04.py
    .\.venv\Scripts\python.exe scripts\verify_dielectric_v04.py
    .\.venv\Scripts\python.exe -m pytest tests\test_dielectric_v04.py -q -p no:cacheprovider

读数：`data/dielectric_v04.csv` sha256 = `e046a3831630e36aae6b67666f74f787b8b33303057877c3402ff7a414e0873c`（LF 规范化口径）。
