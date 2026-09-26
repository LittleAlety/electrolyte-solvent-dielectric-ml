# W17-4 加维度①·密度 ρ(T)：density_v01 纯组分密度表

- 探针：probes/build_density_v01.py
- 预注册（跑前冻结）：probes/build_density_v01_prereg.json，sha256 4eb1a255402ca1211fef4544c1c6addd5300b1b0fbae7f98031ebdea2b84110e，locked_at_utc 2026-09-26T12:47:44Z，status locked_before_run
- 机读汇总：probes/density_v01_summary.json
- 新表：data/density_v01.csv（182154 条纯组分密度观测）；原始层：data/processed/density_raw.csv
- 数据源两层：目录层 = NIST/TRC ThermoML 检索 API；数值层 = 同源 ThermoML XML（https://trc.nist.gov/ThermoML）
- 建模：无。六件冻结件：未动。本臂不修改任何既有文件。

## 1 目录层读数（口径：记录数，不是数据行数）

| 检索词 | 在线 size（记录数） | 已抓记录数 | 页数 |
|---|---:|---:|---:|
| * | 11923 条记录 | — | 1 |
| "Density, kg/m3" | 4697 条记录 | 4697 | 47 |

- 结构化 ePropName 命中（按记录计）：Mass density, kg/m3 4673 条记录；Critical density, kg/m3 33 条记录。检索词是短语索引，故 size 记录数不等于「全是 ρ(T)」.
- 判据 A：0 条违反，允许 0，判 通过。

## 2 数值层（ThermoML XML 观测行）

- 目录层里含纯组分 Mass density, kg/m3 的记录 3465 条；这些记录的 ThermoML XML 构成数值层。
- 命中 accepted 属性名的总观测：570950 条；其中纯组分接受 182154 条、拒绝 648 条、多组分 388148 条。
- 唯一 InChIKey 数：2178；smiles 未能还原的行数：159。
- 判据 B：0 条违反，允许 0，判 通过。

| 温度区间 | 观测行数 |
|---|---:|
| T < 200 K | 138 |
| 200 <= T < 250 K | 725 |
| 250 <= T < 273.15 K | 1595 |
| 273.15 <= T < 298.15 K | 35724 |
| 298.15 <= T < 323.15 K | 64409 |
| 323.15 <= T < 373.15 K | 63763 |
| 373.15 <= T < 450 K | 12261 |
| T >= 450 K | 3539 |

## 3 覆盖率（口径：化合物，唯一 InChIKey）

| 目标集合 | 目标键数 | 密度表键数 | 交集 | 覆盖率 | 缺失键 |
|---|---:|---:|---:|---:|---:|
| vs_dielectric_v03 | 246 | 2178 | 180 | 0.7317 | 66 |
| vs_identity_map | 314 | 2178 | 246 | 0.7834 | 68 |
| vs_local_kinematic | 5 | 2178 | 5 | 1.0000 | 0 |

缺失键清单逐条列在 probes/density_v01_summary.json 的 coverage 一节。

## 4 解冻指标（判据 C）

- 目标：本地运动黏度 176 行（5 个化合物）。
- exact（|ΔT| <= 0.001 K）配到密度：176 行。
- nearest（|ΔT| <= 1.0 K，取最近邻）配到密度 = 解冻行数：176 行。
- 判据 C：0 条违反，允许 0，判 通过。

| InChIKey | 运动黏度行数 | exact | nearest |
|---|---:|---:|---:|
| BTANRVKWQNVYAZ-UHFFFAOYSA-N | 90 | 90 | 90 |
| GSNUFIFRDBKVIE-UHFFFAOYSA-N | 25 | 25 | 25 |
| VQKFNUFAXTZWDK-UHFFFAOYSA-N | 25 | 25 | 25 |
| WYJOVVXUZNRJQY-UHFFFAOYSA-N | 25 | 25 | 25 |
| YLQBMQCUIZJEEH-UHFFFAOYSA-N | 11 | 11 | 11 |

## 5 口径诚实性（判据 D）

- 在线目录层的 size 是检索命中的 ThermoML 记录（文档）数，不是数据行数；它不能与本表（或任何 CSV）的观测行数相减或相除。
- 在线数据行数：unknown —— JSON API 只暴露记录级元数据与 data_summary 计数，不含 NumValues 数值行（跑前侦察实测：整页 100 条记录里 nValue/PropertyValue 均出现 0 次），故在线行数只能记 unknown，不估。
- 本表的每一行都来自同一 DOI 的 ThermoML XML 的一个 NumValues 行，与在线记录数是两套口径，禁止相除当覆盖率。
- 短语命中 vs 结构化命中：4697 条记录里，结构化 Mass density, kg/m3 4673 条记录、Critical density, kg/m3 33 条记录。
- 判据 D：0 条违反，允许 0，判 通过。

## 6 读数与边界

- 目录层：检索词 * 的在线 size 是 11923 条记录，检索词 "Density, kg/m3" 的在线 size 是 4697 条记录，分 47 页从 pageNum=0 抓全（抓到 4697 条记录，DOI 唯一 4697 个）。
- 目录层里结构化 ePropName 恰为 Mass density, kg/m3 的记录 4673 条、恰为 Critical density, kg/m3 的记录 33 条：检索词是短语索引，不能拿 size 当「全是 ρ(T)」。
- 数值层：从目录层里 3465 条含纯组分 Mass density, kg/m3 的记录的 ThermoML XML 里抽出密度观测行，其中纯组分接受 182154 行、拒绝 648 行、多组分行 388148 行。
- 解冻指标：本地运动黏度 176 行（5 个化合物）里，exact 温度配到密度的 176 行，nearest（|ΔT| <= 1.0 K）176 行。
- 覆盖率（口径：化合物，唯一 InChIKey）：vs dielectric_v03 180 / 246，vs identity_map 246 / 314，vs 本地运动黏度化合物 5 / 5。
- 在线目录层的 size 是记录数，不是数据行数；在线行数记 unknown（JSON API 不含数值行），本表不给出任何以在线记录数为分母的行口径覆盖率。
- 本表的行是 ThermoML XML 的 NumValues 观测行，与目录层记录数是两套口径；XML 数值层来自 https://trc.nist.gov/ThermoML/{doi}.xml，与目录层同源同 DOI，但不是同一份字节。
- 覆盖率的单位一律是化合物（唯一 InChIKey），不是观测行、不是记录；缺的键逐条列在 summary 的 coverage 一节。
- 只取 Mass density, kg/m3（含别名 Density, kg/m3）的纯组分行；Critical density, kg/m3、Amount density, mol/m3、多组分行都不入主表，只在 summary 里计数。
- 解冻指标只做「同 InChIKey + 同温度（exact）或最近邻且 |ΔT| <= 1.0 K」的配对，不插值、不外推；1.0 K 之外没有密度就记未配对。
- 本臂只建表与计数：不拟合模型、不产 R2/MAE、不改任何既有文件。

## 7 复现

- 首跑：.venv\Scripts\python.exe probes/build_density_v01.py --resolve-online
- 增量：.venv\Scripts\python.exe probes/build_density_v01.py
- 离线核查：.venv\Scripts\python.exe probes/build_density_v01.py --check
- 独立核验：.venv\Scripts\python.exe scripts/verify_density_v01.py --check
- 目录层清单指纹（manifest_sha256）：2950d5dbc3187f7d546551f1d96e17bfb2e07dcd0ccd834a3ede0e9ec803e448
