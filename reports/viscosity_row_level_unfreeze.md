# η 通道行级解冻（W18-A）

冻结基线的组键读数是 MAE 0.17477197208762 / R2 0.7481271437772365（池 data/viscosity_v01.csv，3582 行 / 957 键），
门是 log10(cP) MAE < 0.15。probes/walden_dn_channel_prereg.json 的 kinematic_thaw 把 176 行运动黏度登记为族级读数、
解冻依赖 data/density_v01.csv。本枪把该依赖用上：176/176 行按 |dT| <= 1e-3 K 精确配到密度，eta = nu * rho 反解成动态黏度，
其中纯组分 86 行入池、多组分 90 行按冻结规则另册。

## 三个池、三块记分牌（并列报，绝不相减）

| 读数 | 池 | 行 / 键 | group_key MAE | group_key R2 | 过 0.15 门 |
| --- | --- | --- | --- | --- | --- |
| `family_level` | 族级读数：冻结基线的原位复现（control） | 3582 / 957 | `0.17477197208762` | `0.74812714377724` | 否 |
|  |  |  | random_row MAE `0.063573153487505`（泄漏参照，不进判决） |  |  |
| `thaw_only` | 增量读数：只加 86 行解冻纯组分运动黏度 | 3668 / 960 | `0.15698877870055` | `0.78528438083963` | 否 |
|  |  |  | random_row MAE `0.06320052316234`（泄漏参照，不进判决） |  |  |
| `row_level` | 行级读数：+483 行 ThermoML 纯组分 Pa*s、+86 行解冻行 | 4151 / 976 | `0.15686276760095` | `0.75268221522395` | 否 |
|  |  |  | random_row MAE `0.061702037428482`（泄漏参照，不进判决） |  |  |

## 判决

- verdict：refuted
- 过门的池：（无）
- 族级原位复现：MAE 偏差 0.000e+00、R2 偏差 0.000e+00（容差 1e-09）；输入摘要同钉：True
- promoted：False

## 解冻账本

- 运动黏度行 176；精确配对 176、最近邻配对 176、反解成功 176
- 入池（纯组分）86；另册（多组分）90
- 解冻涉及的键：['GSNUFIFRDBKVIE-UHFFFAOYSA-N', 'VQKFNUFAXTZWDK-UHFFFAOYSA-N', 'WYJOVVXUZNRJQY-UHFFFAOYSA-N', 'YLQBMQCUIZJEEH-UHFFFAOYSA-N']
- ThermoML 纯组分动态行 483 行 / 43 键；多组分未入池 2066 行

## 诚实边界

- 族级、行级、增量是三块不同记分牌的并列读数，差值不构成本枪的任何结论。
- 解冻只接受纯组分（n_components == 1）行；90 行多组分运动黏度按冻结规则 deferred，未入池。
- ThermoML 动态行同样只接受纯组分；2066 行多组分 Pa*s 行未入池。
- 同一 (inchikey, T_K) 的重复观测两条都留、不做平均；v01 与 ThermoML 侧重叠 22 个单元。
- 组键折只证明新分子外推，不排除骨架相似；random_row 折只作泄漏参照，永不进判决。
- 本枪不动任何冻结数字：ε 基线 0.4091179943351143 与 ε 头条 0.4766400383507876 不在此记分牌上。

## 产物

- 脚本：probes/viscosity_row_level_unfreeze.py
- 预注册：probes/viscosity_row_level_prereg.json（sha256 6ba63936499a18a002b29afc3f0d4fbdbd8ba13e17e363197e51fb308877777a）
- 读数表：probes/artifacts/viscosity_row_level_repeats.csv
- 摘要：probes/viscosity_row_level_summary.json
- 墙钟：45.3 s，jobs 4

