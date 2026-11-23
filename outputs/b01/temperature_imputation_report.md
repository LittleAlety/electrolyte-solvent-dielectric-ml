# B01 温度推定审计
> 生成器 `audit_temperature_imputation/1.0.0` · 2026-11-23T05:39:25Z
> 只测量范围，不改写 v04。修正推定温度须回原始文献。

## 一、结论
22/248 行的温度是**推定**而非实测 (review_table_standard_room_temperature 或 not_reported). 其中 **18 行标记 model_ready=true** —— 模型会被训练成『一个未知温度下的测量值属于 298.15 K』.

## 二、temperature_source 分布
| 来源 | 行数 |
|---|---:|
| `not_reported` | 1 |
| `reported` | 226 |
| `review_table_standard_room_temperature` | 21 |

## 三、为什么重要
介电常数有显著的 dε/dT (例如甲醇约 -0.116 K⁻¹). 0.8 个 ε 单位约对应 2.7-4.0 K 的未记录温差. 因此 GVL 的 36.1 vs 36.9 冲突**可能根本不是冲突**, 而是两次温度推定之差.

## 四、推定温度行清单
| measurement_id | 分子 | T (K) | ε | 温度来源 | model_ready | 来源质量 |
|---|---|---:|---:|---|---|---|
| `EPSV04-R223` | ethyl methyl carbonate | 298.15 | 2.96 | `review_table_standard_room_temperature` | true | open_access_review_table |
| `EPSV04-R224` | 1,3-dioxolane | 298.15 | 7.3 | `review_table_standard_room_temperature` | true | open_access_review_table |
| `EPSV04-R225` | tetrahydrofuran | 298.15 | 7.5 | `review_table_standard_room_temperature` | true | open_access_review_table |
| `EPSV04-R226` | 2-methyltetrahydrofuran | 298.15 | 6.2 | `review_table_standard_room_temperature` | true | open_access_review_table |
| `EPSV04-R227` | gamma-valerolactone | 298.15 | 36.1 | `review_table_standard_room_temperature` | true | open_access_review_table |
| `EPSV04-R228` | 1,1,2,2-tetrafluoroethyl | 298.15 | 3.2 | `review_table_standard_room_temperature` | true | open_access_review_table |
| `EPSV04-R229` | 1,1,2,2-tetrafluoroethyl | 298.15 | 2.8 | `review_table_standard_room_temperature` | true | open_access_review_table |
| `EPSV04-R230` | bis(2,2,2-trifluoroethyl | 298.15 | 2.5 | `review_table_standard_room_temperature` | true | open_access_review_table |
| `EPSV04-R232` | methyl propionate | 298.15 | 6.2 | `review_table_standard_room_temperature` | true | open_access_review_table |
| `EPSV04-R233` | methyl butyrate | 298.15 | 5.48 | `review_table_standard_room_temperature` | true | open_access_review_table |
| `EPSV04-R234` | 1,2-difluorobenzene | 298.15 | 7.1 | `review_table_standard_room_temperature` | true | open_access_review_table |
| `EPSV04-R236` | N-methylpyrrolidone | 298.15 | 32.2 | `review_table_standard_room_temperature` | true | open_access_review_table |
| `EPSV04-R237` | 1,2-dichloroethane | 298.15 | 10.7 | `review_table_standard_room_temperature` | true | open_access_review_table |
| `EPSV04-R238` | 2,2'-dichlorodiethyl eth | 298.15 | 20.79 | `review_table_standard_room_temperature` | true | open_access_review_table |
| `EPSV04-R239` | 1,2-dichloropropane | 298.15 | 9.0 | `review_table_standard_room_temperature` | true | open_access_review_table |
| `EPSV04-R240` | 1,3-dichloropropane | 298.15 | 9.5 | `review_table_standard_room_temperature` | true | open_access_review_table |
| `EPSV04-R241` | 1,4-dichlorobutane | 298.15 | 9.65 | `review_table_standard_room_temperature` | true | open_access_review_table |
| `EPSV04-R242` | dichloromethane | 298.15 | 9.1 | `review_table_standard_room_temperature` | true | open_access_review_table |
| `EPSV04-R243` | triethyl phosphate | 298.15 | 13 | `review_table_standard_room_temperature` | false | open_access_review_table |
| `EPSV04-R244` | trimethyl phosphate | 298.15 | 21.6 | `review_table_standard_room_temperature` | false | open_access_review_table |
| `EPSV04-R246` | 3-methoxypropionitrile | 298.15 | 36.0 | `review_table_standard_room_temperature` | false | secondary_compilation_publisher_si |
| `EPSV04-R248` | gamma-valerolactone | 298.15 | 36.9 | `not_reported` | false | primary |

## 五、对 GVL 冲突的含义
GVL 冲突的两条腿温度都是推定 (review_table_standard_room_temperature 与 not_reported), 因此『同一温度下数值矛盾』这一前提不成立. 裁决应基于来源质量, 不应基于同温实测矛盾.

## 六、下游规则
- **for_b04**：推定温度行不得以 298.15 K 作为条件参与同温冲突判定
- **for_b05**：建模时须标记 temperature_imputed, 或从确认性样本中排除
- 禁止：把推定温度当作实测温度
- 禁止：为凑同温条件而保留推定值
- 禁止：因推定温度而拒绝一条本来有效的测量
