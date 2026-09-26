# W17-3 在线黏度切片入库：viscosity_v02

本报告由 probes/build_viscosity_v02.py 从 probes/viscosity_v02_summary.json 逐字渲染；
判据在跑前冻结于 probes/build_viscosity_v02_prereg.json。本臂只建表与计数：不拟合模型、不产 R2/MAE。

## 1 数据源与三层口径

- 目录层：NIST/TRC ThermoML JSON 检索 API（https://trc.nist.gov/ThermoML-API/objects），三条检索词分别取全库与两个黏度切片。
- 数值层：同源 ThermoML XML（https://trc.nist.gov/ThermoML/{doi}.xml）里的 NumValues 观测行。
- 解冻层：本地 176 行运动黏度 kappa(T) 用 data/density_v01.csv 的 rho(T) 反解 eta = kappa * rho。
- 在线行数口径：unknown（JSON API 只给记录级元数据与 data_summary 计数，不含数值行）；一切覆盖率一律以记录数或 InChIKey 数计，绝不相除。

## 2 目录层（判据 A）

- 全库检索词 * 的在线 size 是 11923 条记录。

| 切片 | size 记录数 | 抓取页数 | 抓到记录数 | 唯一 DOI | 结构化命中记录数 |
|---|---:|---:|---:|---:|---:|
| "Viscosity, Pa*s" | 1690 条记录 | 17 | 1690 条记录 | 1690 | 1690 条记录 |
| "Kinematic viscosity, m2/s" | 70 条记录 | 1 | 70 条记录 | 70 | 70 条记录 |

- 分页是 0 基的（pageNum 起于 0，否则最前 100 条记录永久漏掉）；两个切片都逐位复现 size、抓到记录数 == size、DOI 唯一、零失败页。
- 两个切片 DOI 并集 1743 条记录，交集 17 条记录。
- 判据 A：0 条违反，允许 0，判 通过。

## 3 单位诚实三档（判据 C）

- tier1 单位换算表（显式列全，不在表里即 unit_rejected）：
  - Viscosity, Pa*s -> Pa*s：Pa*s=1、Pa s=1、Pa.s=1、Pas=1、N*s/m2=1、N.s/m2=1、kg/(m*s)=1、kg/(m.s)=1、mPa*s=0.001、mPa.s=0.001、mPa s=0.001、uPa*s=1e-06、µPa*s=1e-06、μPa*s=1e-06、cP=0.001、centipoise=0.001、P=0.1、poise=0.1
  - Kinematic viscosity, m2/s -> m2/s：m2/s=1、m^2/s=1、m2 s-1=1、m2.s-1=1、mm2/s=1e-06、cm2/s=0.0001、cSt=1e-06、St=0.0001
- tier2 温度区间 (100.0, 1000.0) K；tier3 数值区间 Pa*s (1e-6, 1e3) / m2/s (1e-10, 1e-3)。
- 分档账本：命中属性名总观测 268247 条 = 纯组分接受 44246 条 + 多组分另册 223605 条 + 未识别单位 0 条 + 超范围温度 319 条 + 非法值 77 条。
- 未识别单位逐条列账（不静默丢）：
  - 无（全部单位都在换算表里）。
- 判据 C：0 条违反，允许 0，判 通过。

## 4 本地 ⊆ 在线（判据 B）

- 本地含黏度 DOI 29 个（来源 probes/thermoml_viscosity_coverage_summary.json）逐个命中在线并集：命中 29 个，缺 0 个。
- 判据 B：0 条违反，允许 0，判 通过。

## 5 主表与双口径清点（判据 D）

- 在线记录数（切片口径）：Pa*s 切片 1690 条记录、kinematic 切片 70 条记录、并集 1743 条记录。
- 数值层观测行数：268247 行（唯一 InChIKey 1547 个）。
- 主表 viscosity_v02 行数：42941 行（唯一 InChIKey 1228 个）= Pa*s 直测 42855 行 + 运动黏度反解 86 行。
- 多组分另册登记：223605 行（未做溶质/溶剂角色拆分前不入主表）。
- 在线目录层的 size 是检索命中的 ThermoML 记录（文档）数，不是数据行数；它不能与本表（或任何 CSV）的观测行数相减或相除。
- 本表的每一行都来自同一 DOI 的 ThermoML XML 的一个 NumValues 行（运动黏度换算行另标 value_origin=kinematic_converted），与在线记录数是两套口径，禁止相除当覆盖率。
- 在线数据行数：unknown —— JSON API 只暴露记录级元数据与 data_summary 计数，不含 NumValues 数值行（跑前侦察实测：整页记录里 nValue/PropertyValue 均出现 0 次），故在线行数只能记 unknown，不估。
- 判据 D：0 条违反，允许 0，判 通过。

## 6 与本地 Pa*s 观测逐行对账（判据 E）

- 本地 Pa*s 观测 2549 行（data/processed/viscosity_observations_thermoml.csv）与在线收割逐行比对：命中 2549 行，未命中 0 行。
- 对账键 = 同 DOI + 同 InChIKey + 同温度 + 同源行号；重复行只标 source_priority（online_duplicate_of_local / online_new），不合并、不平均。

## 7 运动黏度解冻（判据 C 解冻）

- 目标：本地运动黏度 176 行（5 个化合物）。
- exact（|dT| <= 0.001 K）配到密度：176 行。
- nearest（|dT| <= 1.0 K，取最近邻）配到密度：176 行。
- 反解 eta = kappa * rho：176 行；其中纯组分入主表 86 行、多组分另册 90 行。
- 逐行换算 provenance（换算乘子 rho、配对密度来源 DOI、配对容差）见 summary 的 per_row。
- 另册口径：在线 kinematic 切片纯组分接受行 1391 行，本臂只按预注册范围反解本地 176 行（纯组分 86 行入主表），其余纯组分运动黏度行未做换算。

| InChIKey | 运动黏度行数 | exact | nearest | 入主表 |
|---|---:|---:|---:|---:|
| BTANRVKWQNVYAZ-UHFFFAOYSA-N | 90 | 90 | 90 | 0 |
| GSNUFIFRDBKVIE-UHFFFAOYSA-N | 25 | 25 | 25 | 25 |
| VQKFNUFAXTZWDK-UHFFFAOYSA-N | 25 | 25 | 25 | 25 |
| WYJOVVXUZNRJQY-UHFFFAOYSA-N | 25 | 25 | 25 | 25 |
| YLQBMQCUIZJEEH-UHFFFAOYSA-N | 11 | 11 | 11 | 11 |

## 8 联表重建 group_overlap 断言

- 在重建的联表（viscosity_v02 主表 42941 行 / 1228 组）上跑 GroupKFold by InChIKey：max_group_overlap = 0，断言 group_overlap == 0 通过。
- random_row 只作泄漏参照，永不进判决：leaked_fraction = 0.997904。

## 9 读数与边界

- 目录层：检索词 * 的在线 size 是 11923 条记录；"Viscosity, Pa*s" 切片的 size 是 1690 条记录（17 页，pageNum=0 起）、"Kinematic viscosity, m2/s" 切片的 size 是 70 条记录（1 页），两个切片都抓全、DOI 唯一。两个切片 DOI 并集 1743 条记录，交集 17 条记录。
- 数值层：从两个切片 DOI 并集的 ThermoML XML 里抽出黏度观测 268247 条；其中纯组分接受 44246 条、多组分另册登记 223605 条；未识别单位 0 条、超范围温度 319 条、非法值 77 条。
- 主表 viscosity_v02：42941 行 = Pa*s 直测 42855 行 + 本地运动黏度用 rho(T) 反解 86 行；唯一 InChIKey 1228 个。
- 本地对账：本地 Pa*s 观测 2549 行，与在线收割逐行（同 DOI 同物质同温度同行号）命中 2549 行；未命中 0 行。重复行只标 source_priority，不合并、不平均。
- 解冻指标：本地运动黏度 176 行（5 个化合物）；exact（|dT| <= 0.001 K）配到密度 176 行、nearest（|dT| <= 1.0 K）配到 176 行；反解出 eta 的 176 行，其中纯组分入主表 86 行、多组分另册 90 行。
- 本地 ⊆ 在线：本地含黏度 DOI 29 个全部命中所抓在线并集（1743 条记录口径）。
- 联表重建 group_overlap 断言：GroupKFold by InChIKey（5 折，42941 行 / 1228 组）max_group_overlap = 0；random_row 只作泄漏参照（leaked_fraction = 0.997904）。
- 在线目录层的 size 是记录数，不是数据行数；在线行数记 unknown（JSON API 不含数值行），本表不给出任何以在线记录数为分母的行口径覆盖率。
- 本表的行是 ThermoML XML 的 NumValues 观测行（运动黏度换算行另标 value_origin），与目录层记录数是两套口径；XML 数值层来自 https://trc.nist.gov/ThermoML/{doi}.xml，与目录层同源同 DOI，但不是同一份字节。
- 多组分记录未做溶质/溶剂角色拆分，一律另册登记（raw 层 role=multi_component_deferred，以及解冻账本 per_row 里 pooled_into_main_table=false 的行），不入主表。
- 运动黏度另册：在线 kinematic 切片的纯组分接受行共 1391 行（含本地 176 行作为子集），本臂按预注册范围只反解本地 176 行，其中纯组分 86 行入主表；其余纯组分运动黏度行只入 raw 另册，未做换算。
- 运动黏度换算只做「同 InChIKey（主组分）+ 同温度（exact）或最近邻且 |dT| <= 1.0 K」的配对，不插值、不外推；换算式 eta = kappa * rho，rho 取 data/density_v01.csv 的纯组分密度，逐行 provenance 见主表 density_* 列与 summary 的 criterion_c_unfreeze.per_row。
- 本地 Pa*s 行与在线收割行的对账口径是「同 DOI + 同 InChIKey + 同温度 + 同源行号」；重复行只标 source_priority，不做平均、不做去重。
- 本臂只建表与计数：不拟合模型、不产 R2/MAE、不改任何既有文件。

## 10 复现

- 首跑：.venv\Scripts\python.exe probes/build_viscosity_v02.py --resolve-online
- 增量：.venv\Scripts\python.exe probes/build_viscosity_v02.py
- 离线核查：.venv\Scripts\python.exe probes/build_viscosity_v02.py --check
- 独立核验：.venv\Scripts\python.exe scripts/verify_viscosity_v02.py --check
- 目录层清单指纹（manifest_sha256）：c54e4df744565d72c7fc793dd308d0f32d1472dcadf83cd949cb8af004d53f50
