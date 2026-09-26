# AL Round 4：新化合物补录清单 v0（离线、本地再分析）

本产物按 Week 14 附录 D1 的口径立项：v1.x 的精度杠杆只剩「化合物覆盖」，所以 Round 4 的取向从「补温度点」切换为「补新化合物」。全程离线，只读本地 CSV，不调用 OpenAlex / Unpaywall / 任何 HTTP 接口。

## 1. 输入与完整性

| 输入 | sha256（实际） | 钉住 | 完整 |
|---|---|---|---|
| al_round3_oa_triage | e1cac8a8305ebdb745597c5452ce1c228a1f75cd71c70b1da40fbccd7fa22991 | e1cac8a8305ebdb745597c5452ce1c228a1f75cd71c70b1da40fbccd7fa22991 | OK |
| openalex_oa_candidates | 3e1d7ee537b2bf4fffa38b243e5c208bf5cc83b1e4d8b04303f50f89a07a8d5d | 3e1d7ee537b2bf4fffa38b243e5c208bf5cc83b1e4d8b04303f50f89a07a8d5d | OK |
| dielectric_v03 | ff2142936e06e04b329b70f8597574f75349e54ce876e9fff81309e6d35ccce4 | ff2142936e06e04b329b70f8597574f75349e54ce876e9fff81309e6d35ccce4 | OK |
| dielectric_observations_v11plus | 159b928f800a55969963da275ed05c30ce8a19cffc48353a9c490eec68a49af9 | 159b928f800a55969963da275ed05c30ce8a19cffc48353a9c490eec68a49af9 | OK |

## 2. 清单总览

| 指标 | 值 |
|---|---|
| 清单行数 | 21 |
| 真新化合物行（is_new_compound=yes） | 7 |
| 对账行（本地已覆盖 / 名册缺口） | 13 |
| 缺口家族行 | 1 |
| 优先级分布（全表） | P1=1, P3=20 |
| 优先级分布（真新化合物） | P1=1, P3=6 |
| 证据类型（真新化合物） | 无ε线索=3, 汇编转述=3, 第一手测量=1 |
| 本地非介电痕迹（真新化合物） | no=2, yes=5 |
| Round 3 三连组错位行 | 0 |

## 3. 真新化合物（本地介电面板完全没有）

| 优先级 | 化合物 | InChIKey | ε 线索 | 证据 | 本地痕迹 | 受限痕迹 | OA | 动作 | 来源 DOI |
|---|---|---|---|---|---|---|---|---|---|
| P1 | 1,2-dimethoxypropane | LEEANUDEDHYDTG-UHFFFAOYSA-N | wording_only | 汇编转述 | yes | no | green | 人读 | 10.1021/acsenergylett.2c02003 |
| P3 | 2,2,2-trifluoroethanol | RHQDFWAXVIIEBN-UHFFFAOYSA-N | wording_only | 汇编转述 | yes | yes | bronze;green | 仅线索 | 10.1021/jp302790j;10.1529/biophysj.106.098715;10.1073/pnas.182199699 |
| P3 | decafluoropentane | RIQRGMUSBYGDBL-UHFFFAOYSA-N | none | 无ε线索 | no | no | gold;hybrid | 放弃 | 10.1088/1742-6596/2685/1/012064;10.1016/j.applthermaleng.2023.121803;10.3390/nano11123216 |
| P3 | hexafluoroisopropanol | BYEAHWXPCBROCE-UHFFFAOYSA-N | wording_only | 第一手测量 | no | no | green;hybrid | 仅线索 | 10.1002/anie.202416091;10.1021/jp302790j |
| P3 | methoxy-nonafluorobutane | OKIYQFLILPKULA-UHFFFAOYSA-N | wording_only | 汇编转述 | yes | no | bronze;gold | 放弃 | 10.3390/app14020495;10.1002/2014wr015291 |
| P3 | perfluorohexane | ZJIJAJXFLBMLCK-UHFFFAOYSA-N | none | 无ε线索 | yes | no | gold | 放弃 | 10.1088/1742-6596/2685/1/012064 |
| P3 | tripropylene glycol | LEQCJROTXBYLEU-UHFFFAOYSA-N | none | 无ε线索 | yes | no | bronze | 仅线索 | 10.1063/1.4740236 |

真新化合物有两种分解，两种都写在这里：按本地痕迹 —— 本地完全没有任何痕迹 2 个（decafluoropentane、hexafluoroisopropanol），本地只在非介电表里出现过 5 个（1,2-dimethoxypropane、2,2,2-trifluoroethanol、methoxy-nonafluorobutane、perfluorohexane、tripropylene glycol）；按 ε 证据 —— 无ε线索 3、汇编转述 3、第一手测量 1。痕迹只统计已声明的策展数据树（data/external/、data/processed/、data/raw/、data/reference/、data/restricted/）与 data/ 顶层策展表；data/interim/ 这个周内 scratch 区，以及任何以“_”开头的私有命名文件，都按声明排除。

### P1 · 1,2-dimethoxypropane（人读）

- InChIKey：`LEEANUDEDHYDTG-UHFFFAOYSA-N`
- SMILES：`COCC(C)OC`
- 判定：genuinely new to the panel: absent from both dielectric_v03.csv and dielectric_observations_v11plus.csv under an InChIKey join；round3_target=core; epsilon=wording_only; leads=1
- ε 线索：wording_only（无数值）；证据类型 汇编转述
- OA：green，可达=false；线索来源 https://zenodo.org/record/7801393
- 本地非介电痕迹：data/external/SolvFunc-87.csv:name;data/processed/al_round1_longlist.csv:name;data/processed/l3_homo_lumo_cv_predictions.csv:key;data/processed/redox_merged.csv:key

### P3 · 2,2,2-trifluoroethanol（仅线索）

- InChIKey：`RHQDFWAXVIIEBN-UHFFFAOYSA-N`
- SMILES：`OCC(F)(F)F`
- 判定：genuinely new to the panel: absent from both dielectric_v03.csv and dielectric_observations_v11plus.csv under an InChIKey join；round3_target=off; epsilon=wording_only; leads=3
- ε 线索：wording_only（无数值）；证据类型 汇编转述
- OA：bronze;green，可达=true；线索来源 https://edoc.unibas.ch/48169/1/No%2037%20Hankache_JPhysChemA_2012_116_8159.pdf
- 本地非介电痕迹：data/external/chew_2024_viscosity_supp_2.csv:name;data/processed/landolt_boernstein_2015_pure_liquid_queue.csv:name;data/processed/viscosity_baseline_predictions.csv:key;data/processed/viscosity_raw.csv:key;data/restricted/springer_materials/interactive_pure_dielectric_catalog.json:name;data/viscosity_v01.csv:key
- 受限痕迹：命中 data/restricted/ 下的文件。本清单只记路径、不取任何值；该物质应走受限交叉核对通道判定，而不是靠新取数解决。

### P3 · decafluoropentane（放弃）

- InChIKey：`RIQRGMUSBYGDBL-UHFFFAOYSA-N`
- SMILES：`FC(F)(F)C(F)(F)C(F)C(F)C(F)(F)F`
- 判定：genuinely new to the panel: absent from both dielectric_v03.csv and dielectric_observations_v11plus.csv under an InChIKey join；round3_target=off; epsilon=none; noise_veto=pool_boiling_heat_transfer; leads=3
- ε 线索：none（无数值）；证据类型 无ε线索
- OA：gold;hybrid，可达=true；线索来源 https://doi.org/10.1088/1742-6596/2685/1/012064
- 本地非介电痕迹：无

### P3 · hexafluoroisopropanol（仅线索）

- InChIKey：`BYEAHWXPCBROCE-UHFFFAOYSA-N`
- SMILES：`OC(C(F)(F)F)C(F)(F)F`
- 判定：genuinely new to the panel: absent from both dielectric_v03.csv and dielectric_observations_v11plus.csv under an InChIKey join；round3_target=off; epsilon=wording_only; leads=2
- ε 线索：wording_only（无数值）；证据类型 第一手测量
- OA：green;hybrid，可达=true；线索来源 https://doi.org/10.1002/anie.202416091
- 本地非介电痕迹：无

### P3 · methoxy-nonafluorobutane（放弃）

- InChIKey：`OKIYQFLILPKULA-UHFFFAOYSA-N`
- SMILES：`COC(F)(F)C(F)(F)C(F)(F)C(F)(F)F`
- 判定：genuinely new to the panel: absent from both dielectric_v03.csv and dielectric_observations_v11plus.csv under an InChIKey join；round3_target=core; epsilon=wording_only; noise_veto=geophysics_dnapl|pool_boiling_heat_transfer; leads=2
- ε 线索：wording_only（无数值）；证据类型 汇编转述
- OA：bronze;gold，可达=false；线索来源 https://www.mdpi.com/2076-3417/14/2/495/pdf?version=1704460575
- 本地非介电痕迹：data/processed/l3_homo_lumo_cv_predictions.csv:key;data/processed/redox_merged.csv:key

### P3 · perfluorohexane（放弃）

- InChIKey：`ZJIJAJXFLBMLCK-UHFFFAOYSA-N`
- SMILES：`FC(F)(F)C(F)(F)C(F)(F)C(F)(F)C(F)(F)C(F)(F)F`
- 判定：genuinely new to the panel: absent from both dielectric_v03.csv and dielectric_observations_v11plus.csv under an InChIKey join；round3_target=off; epsilon=none; noise_veto=pool_boiling_heat_transfer; leads=1
- ε 线索：none（无数值）；证据类型 无ε线索
- OA：gold，可达=true；线索来源 https://doi.org/10.1088/1742-6596/2685/1/012064
- 本地非介电痕迹：data/processed/viscosity_raw.csv:key;data/viscosity_v01.csv:key

### P3 · tripropylene glycol（仅线索）

- InChIKey：`LEQCJROTXBYLEU-UHFFFAOYSA-N`
- SMILES：`CC(O)COCC(C)OCC(C)O`
- 判定：genuinely new to the panel: absent from both dielectric_v03.csv and dielectric_observations_v11plus.csv under an InChIKey join；round3_target=adjacent; epsilon=none; leads=1
- ε 线索：none（无数值）；证据类型 无ε线索
- OA：bronze，可达=false；线索来源 https://pubs.aip.org/aip/jcp/article-pdf/doi/10.1063/1.4740236/14080820/064508_1_online.pdf
- 本地非介电痕迹：data/external/chew_2024_viscosity_supp_2.csv:name;data/processed/viscosity_baseline_predictions.csv:name;data/processed/viscosity_raw.csv:name;data/viscosity_v01.csv:name

## 4. 本地已覆盖条目（对账行，不计入补录）

| 行类型 | 化合物 | InChIKey | v03 | 观测表 | 观测行数 | 温度点 | Round 3 判定 | 动作 |
|---|---|---|---|---|---|---|---|---|
| roster_gap | succinonitrile | IAHFWCOBPZCAEA-UHFFFAOYSA-N | no | yes | 17 | 17 | human_reading_list;pending | 放弃 |
| local_duplicate_reconciliation | 1,2-dimethoxyethane | XTHFKEDIFFGKHM-UHFFFAOYSA-N | yes | yes | 9 | 6 | pending | 放弃 |
| local_duplicate_reconciliation | 1-butanol | LRHPLDYGYMQRHN-UHFFFAOYSA-N | yes | yes | 23 | 7 | discard | 放弃 |
| local_duplicate_reconciliation | adiponitrile | BTGRAWJCKBQKAO-UHFFFAOYSA-N | yes | yes | 31 | 31 | human_reading_list | 放弃 |
| local_duplicate_reconciliation | diglyme | SBZXBUIDTXKZTM-UHFFFAOYSA-N | yes | yes | 9 | 6 | pending | 放弃 |
| local_duplicate_reconciliation | ethane-1,2-diol | LYCAIKOWRPUZTN-UHFFFAOYSA-N | yes | yes | 1 | 1 | pending | 放弃 |
| local_duplicate_reconciliation | ethyl methyl carbonate | JBTWLSYIZRCDFO-UHFFFAOYSA-N | yes | no | 0 | 0 | pending | 放弃 |
| local_duplicate_reconciliation | ethylene carbonate | KMTRUDSVKNLOMY-UHFFFAOYSA-N | yes | no | 0 | 0 | pending | 放弃 |
| local_duplicate_reconciliation | glutaronitrile | ZTOMUSMDRMJOTH-UHFFFAOYSA-N | yes | yes | 31 | 31 | human_reading_list;pending | 放弃 |
| local_duplicate_reconciliation | propylene carbonate | RUOJZAUFBMNUDX-UHFFFAOYSA-N | yes | no | 0 | 0 | discard;human_reading_list;pending | 放弃 |
| local_duplicate_reconciliation | tetraglyme | ZUHZGEOKBKGPSW-UHFFFAOYSA-N | yes | yes | 6 | 5 | human_reading_list;pending | 放弃 |
| local_duplicate_reconciliation | triglyme | YFNKIDBQEZZDLK-UHFFFAOYSA-N | yes | yes | 8 | 5 | pending | 放弃 |
| local_duplicate_reconciliation | water | XLYOFNOQVPJJNP-UHFFFAOYSA-N | yes | yes | 33 | 32 | discard;pending | 放弃 |

这些化合物的 ε 值在本地已经有了，Round 3 却按「温度点」把它们又扫了一遍。它们是 Round 3 与 Round 4 口径差异的直接体现：同一批线索换成覆盖口径之后大部分作废。

## 5. 明确缺口家族

| 家族 | 来源 DOI | Round 3 判定 | 动作 | 说明 |
|---|---|---|---|---|
| [family gap] glyme | 10.1016/j.electacta.2019.02.110 | pending/P2 | 仅线索 | target=core_family_unresolved; families=glyme; unresolved: glyme=generic glyme without a chain-length prefix; oligomer length unnamed; target=core_family_unresolved; epsilon=none; temperature=unknown; oa=unknown; score=3 |

## 6. 本地覆盖缺口 top-5 家族（该补什么的本地证据）

| 家族 | 信号 | 化合物数 | 观测行数 | 行/化合物 | 单行化合物 | 来源 DOI 数 |
|---|---|---|---|---|---|---|
| acid | thin_family | 1 | 1 | 1.00 | 1 | 1 |
| lactone | thin_family | 1 | 5 | 5.00 | 0 | 1 |
| carbonate | thin_family | 2 | 10 | 5.00 | 0 | 1 |
| sulfone | thin_family | 2 | 113 | 56.50 | 0 | 5 |
| protic_ionic_pair | single_row_dominated | 4 | 4 | 1.00 | 4 | 1 |

排序口径：先按化合物数升序，再按「行/化合物」（证据深度）升序；water 与 unparsed 两类退化家族按声明排除（单分子家族不是化学缺口，unparsed 是数据卫生信号）。全部 14 个家族、41 个单行化合物与 61 个来源 DOI 的明细见 probes/artifacts/al_round4_local_coverage_gaps.csv。

## 7. 与 Round 3 对账

| 指标 | 值 |
|---|---|
| Round 3 线索总数 | 37 |
| 进入 v0 的线索数 | 35 |
| 未进入 v0 的线索数 | 2 |
| 未进入 v0 的 DOI | 10.1016/j.applthermaleng.2020.115862, 10.1016/j.bpj.2017.12.013 |
| Round 3 化合物条目（去重） | 20 |
| 其中真新化合物 | 7 |
| 其中本地已覆盖 | 13 |

## 8. pending 20 篇分流

| 动作 | 篇数 |
|---|---|
| 人读 | 1 |
| 仅线索 | 2 |
| 归档 | 17 |

逐篇明细见 reports/al_round4_pending_oa_triage.md。

## 9. 三条诚实边界

1. **v0 是线索清单，不是数据集。** 每一行只记录「哪篇文献提到了哪个化合物、本地有没有」，没有任何一条 ε 观测被写进 data/，也没有任何特征被派生。要变成数据，必须走取全文 → 表格抽取 → verifier 这条链路。
2. **OA 可达 ≠ 有 ε 数值。** Round 3 的 37 条线索里 epsilon_clue_kind=value 的只有 1 条，其余 22 条是 wording_only（摘要里说「低介电常数」却不给数），14 条连措辞都没有。wording_only 在本清单里一律不带数值。
3. **数据库覆盖边际收益递减。** 13 个 Round-3 化合物条目本地已有（其中 succinonitrile 是「名册缺口」而非「数据缺口」），真新化合物只有 7 个，而其中 P1 只有 1 个。要真正扩大覆盖面，得换一组面向新化合物的检索式，而不是继续榨 Round 3 的余料。

## 10. shots 与口径

- shots = 1：本轮只按预注册规则跑了一次，没有事后手调。
- 本地痕迹扫描口径：只接受已声明的策展数据树（data/external/、data/processed/、data/raw/、data/reference/、data/restricted/）与 data/ 顶层的策展表；data/interim/ 这一周内 scratch 区按声明排除——临时转储、计时探针、一次性重跑都不是项目知识，让它们进来会让证据链取决于某个副任务当天下午恰好写了什么。
- 第二条 scratch 规则：basename 以“_”开头的文件一律不进证据链（仓库里现存的该类文件都是 g1plus 的请求日志）。这条不是临时补丁——本轮真正踩到的就是一个名为 _lever8_paper_text.txt 的转储被递归扫描当成项目知识，名字约定能拦住它落在任何目录的变体。
- 默认拒绝：data/ 下既不属于已声明策展树、也不是顶层策展表的路径一律不进扫描，所以将来新增的 scratch 目录天然被排除，无需再改代码。
- 其他 scratch 路径已确认：data/ 下唯一的 scratch 区就是 data/interim/；data/external/g1plus/、data/raw/、data/restricted/ 以及 data/processed/ 下未入库的探针输出都是策展缓存/产物，按同一规则留在扫描范围内。
- gitignore 状态不是判据：data/ 下若干策展路径因体积或再分发条款被 ignore（尤其 data/restricted/、data/external/g1plus/），它们仍在扫描范围内；排除一律按已声明的 scratch 规则执行。
- 优先级规则在跑之前就已写死在 derive_priority() 里，事后不放宽；noise veto 的线索永不因家族归属而升级。
- 复现：.venv\Scripts\python.exe probes\al_round4_new_compound_backfill.py
