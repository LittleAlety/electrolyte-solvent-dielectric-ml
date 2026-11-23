# B-G0-J04 聚合贡献账本与条件配对完整性

- 契约: `confirm_2027.aggregate_contribution/v1` / `confirm_2027.j04_inputs/v1`
- 本报告不含墙钟时间, 可由固定输入逐字节重建
- 聚合窗口: 293.15-303.15 K, liquid, 0 Hz

## 1. 五维证据账本 (不是单调漏斗)

| 指标 | 数量 | 统计单位 | 说明 |
|---|---:|---|---|
| `N_database_rows` | 248 | v04 聚合行 (化合物-条件记录) | 不是测量数, 也不是独立证据数 |
| `N_raw_measurements` | 2065 | v11plus 逐行观测 (测量记录) | 全量; 其中 460 条落在 v04 聚合窗口内 |
| `N_source_documents` | 61 | 可验证身份的来源文档 (DOI + 文件 sha256) | 文档身份不等于实验独立性 |
| `N_in_aggregate_window` | 460 | v04 聚合窗口内观测 | J03 曾把 460 误称为 N_measurement |
| `N_condition_pair_valid` | 78 | 聚合行中 (T, epsilon) 可对应到同一次测量的行数 | 只有这些行可作为测量级证据的入口 |
| `N_condition_pair_invalid` | 170 | 聚合行中组合不对应真实测量的行数 | 含 148 行无贡献测量的缺失证书 + 22 行合成条件对 |
| `N_admitted` | 0 | 人工准入记录 | 与上面每一层都是不同统计单位 |

**这六个数不是单调漏斗: N_raw_measurements(2065) > N_database_rows(248), N_condition_pair_valid(100) 与 N_source_documents(61) 单位不同. 正确论点: 数据库行数既可能低估测量规模, 也可能高估独立证据规模**

## 2. 聚合贡献账本 (J04-C)

| 项 | 数量 |
|---|---:|
| v04 聚合记录 | 248 |
| 贡献清单完整 | 100 |
| 缺失证书 | 148 |
| 多来源聚合 | 27 |

**规则**: 每条聚合记录或贡献清单完整, 或有明确缺失证书; 不存在第三种状态。

## 3. 条件配对完整性 (J04-D)

| 项 | 数量 |
|---|---:|
| 配对有效 (`condition_pair_valid=true`) | 78 |
| 配对无效 | 170 |

### 合成条件对 (有贡献测量, 但组合不对应真实测量)

| aggregate | A18 | v04 (T, ε) | 中位数 (T, ε) | T 持有者 | ε 持有者 | 原因 |
|---|---|---|---|---|---|---|
| v04row-003 | not_evaluated | (298.15, 15.736) | (298.15, 15.736) | 298.15@MSR-220964bd;298.15@MSR-3bcd64ff;298.15@MSR-87ce032e;298.15@MSR-9311b231;298.15@MSR-a6cbf58f;298.15@MSR-abfec1a2;298.15@MSR-ae3b4911;298.15@MSR-b602a72b;298.15@MSR-c267b911 | 15.736@MSR-044a62cb | `MEDIAN_T_AND_EPSILON_FROM_DIFFERENT_OBSERVATIONS;MULTI_SOURCE_DROPPED_IN_GAP` |
| v04row-007 | not_evaluated | (298.15, 13.505) | (298.15, 13.505) | 298.15@MSR-4a3b5e22;298.15@MSR-859e3174 | not_evaluated | `EPSILON_MEDIAN_NOT_AN_OBSERVED_VALUE;MEDIAN_T_AND_EPSILON_FROM_DIFFERENT_OBSERVATIONS;MULTI_SOURCE_DROPPED_IN_GAP` |
| v04row-016 | not_evaluated | (300.65, 22.12) | (300.65, 22.12) | not_evaluated | not_evaluated | `EPSILON_MEDIAN_NOT_AN_OBSERVED_VALUE;MEDIAN_T_AND_EPSILON_FROM_DIFFERENT_OBSERVATIONS;MULTI_SOURCE_DROPPED_IN_GAP;TEMPERATURE_MEDIAN_NOT_AN_OBSERVED_VALUE` |
| v04row-031 | C15 | (298, 46.05) | (298, 46.05) | 298@MSR-5e40e553 | 46.05@MSR-11c0bd47;46.05@MSR-e32be3f7 | `MEDIAN_T_AND_EPSILON_FROM_DIFFERENT_OBSERVATIONS;MULTI_SOURCE_DROPPED_IN_GAP` |
| v04row-033 | not_evaluated | (300.65, 14.38) | (300.65, 14.38) | not_evaluated | not_evaluated | `EPSILON_MEDIAN_NOT_AN_OBSERVED_VALUE;MEDIAN_T_AND_EPSILON_FROM_DIFFERENT_OBSERVATIONS;TEMPERATURE_MEDIAN_NOT_AN_OBSERVED_VALUE` |
| v04row-036 | not_evaluated | (298.15, 15.79) | (298.15, 15.79) | 298.15@MSR-5d89367c;298.15@MSR-ec645d9d | not_evaluated | `EPSILON_MEDIAN_NOT_AN_OBSERVED_VALUE;MEDIAN_T_AND_EPSILON_FROM_DIFFERENT_OBSERVATIONS;MULTI_SOURCE_DROPPED_IN_GAP` |
| v04row-040 | not_evaluated | (298.15, 10.66) | (298.15, 10.66) | 298.15@MSR-04168ba7;298.15@MSR-89392b54;298.15@MSR-a221b2b7;298.15@MSR-b258b21e;298.15@MSR-d440bcc9;298.15@MSR-f5b1d40b | not_evaluated | `EPSILON_MEDIAN_NOT_AN_OBSERVED_VALUE;MEDIAN_T_AND_EPSILON_FROM_DIFFERENT_OBSERVATIONS;MULTI_SOURCE_DROPPED_IN_GAP` |
| v04row-041 | not_evaluated | (299.15, 18.845) | (299.15, 18.845) | not_evaluated | not_evaluated | `EPSILON_MEDIAN_NOT_AN_OBSERVED_VALUE;MEDIAN_T_AND_EPSILON_FROM_DIFFERENT_OBSERVATIONS;MULTI_SOURCE_DROPPED_IN_GAP;TEMPERATURE_MEDIAN_NOT_AN_OBSERVED_VALUE` |
| v04row-044 | not_evaluated | (298.15, 25.02) | (298.15, 25.02) | 298.15@MSR-21cd8c61;298.15@MSR-26a4d537;298.15@MSR-301491ec;298.15@MSR-548984da;298.15@MSR-76115f00;298.15@MSR-7e0d902b;298.15@MSR-ba44811b;298.15@MSR-c6c38454;298.15@MSR-db994403 | 25.02@MSR-3987ee16 | `MEDIAN_T_AND_EPSILON_FROM_DIFFERENT_OBSERVATIONS;MULTI_SOURCE_DROPPED_IN_GAP` |
| v04row-046 | not_evaluated | (298.15, 18.03) | (298.15, 18.03) | 298.15@MSR-045b6bab;298.15@MSR-09eb41a0;298.15@MSR-4f3054d5;298.15@MSR-502e4fbc;298.15@MSR-6a4a8e55;298.15@MSR-8477291b;298.15@MSR-9d37784c;298.15@MSR-9fa2c584;298.15@MSR-bff194c1;298.15@MSR-e80490ba;298.15@MSR-feb44fa0 | not_evaluated | `EPSILON_MEDIAN_NOT_AN_OBSERVED_VALUE;MEDIAN_T_AND_EPSILON_FROM_DIFFERENT_OBSERVATIONS;MULTI_SOURCE_DROPPED_IN_GAP` |
| v04row-057 | not_evaluated | (298.15, 33.6) | (298.15, 33.6) | 298.15@MSR-2730e53a;298.15@MSR-28dd848d;298.15@MSR-44b75f6f;298.15@MSR-5e9dc0f1;298.15@MSR-6ce8e325;298.15@MSR-72822dd2;298.15@MSR-d870506d;298.15@MSR-ed6e704c | 33.6@MSR-dd25eb05 | `MEDIAN_T_AND_EPSILON_FROM_DIFFERENT_OBSERVATIONS;MULTI_SOURCE_DROPPED_IN_GAP` |
| v04row-064 | not_evaluated | (298.15, 7.3815) | (298.15, 7.3815) | 298.15@MSR-1ca8ea47;298.15@MSR-d9db8577 | not_evaluated | `EPSILON_MEDIAN_NOT_AN_OBSERVED_VALUE;MEDIAN_T_AND_EPSILON_FROM_DIFFERENT_OBSERVATIONS;MULTI_SOURCE_DROPPED_IN_GAP` |
| v04row-080 | not_evaluated | (298.115, 11.8861) | (298.115, 11.8861) | not_evaluated | not_evaluated | `EPSILON_MEDIAN_NOT_AN_OBSERVED_VALUE;MEDIAN_T_AND_EPSILON_FROM_DIFFERENT_OBSERVATIONS;TEMPERATURE_MEDIAN_NOT_AN_OBSERVED_VALUE` |
| v04row-083 | not_evaluated | (297.575, 78.87) | (297.575, 78.87) | not_evaluated | not_evaluated | `EPSILON_MEDIAN_NOT_AN_OBSERVED_VALUE;MEDIAN_T_AND_EPSILON_FROM_DIFFERENT_OBSERVATIONS;MULTI_SOURCE_DROPPED_IN_GAP;TEMPERATURE_MEDIAN_NOT_AN_OBSERVED_VALUE` |
| v04row-084 | not_evaluated | (299.4, 10.76) | (299.4, 10.76) | not_evaluated | not_evaluated | `EPSILON_MEDIAN_NOT_AN_OBSERVED_VALUE;MEDIAN_T_AND_EPSILON_FROM_DIFFERENT_OBSERVATIONS;TEMPERATURE_MEDIAN_NOT_AN_OBSERVED_VALUE` |
| v04row-085 | C08 | (298.15, 7.0695) | (298.15, 7.0695) | 298.15@MSR-5ba9d1ba;298.15@MSR-ef862b4d | not_evaluated | `EPSILON_MEDIAN_NOT_AN_OBSERVED_VALUE;MEDIAN_T_AND_EPSILON_FROM_DIFFERENT_OBSERVATIONS;MULTI_SOURCE_DROPPED_IN_GAP` |
| v04row-086 | C13 | (295.65, 41.99) | (295.65, 41.99) | not_evaluated | not_evaluated | `EPSILON_MEDIAN_NOT_AN_OBSERVED_VALUE;MEDIAN_T_AND_EPSILON_FROM_DIFFERENT_OBSERVATIONS;TEMPERATURE_MEDIAN_NOT_AN_OBSERVED_VALUE` |
| v04row-089 | not_evaluated | (298.15, 7.604) | (298.15, 7.604) | 298.15@MSR-afa71ac6;298.15@MSR-bd837341 | not_evaluated | `EPSILON_MEDIAN_NOT_AN_OBSERVED_VALUE;MEDIAN_T_AND_EPSILON_FROM_DIFFERENT_OBSERVATIONS;MULTI_SOURCE_DROPPED_IN_GAP` |
| v04row-091 | not_evaluated | (297.385, 2.40445) | (297.385, 2.40445) | not_evaluated | not_evaluated | `EPSILON_MEDIAN_NOT_AN_OBSERVED_VALUE;MEDIAN_T_AND_EPSILON_FROM_DIFFERENT_OBSERVATIONS;MULTI_SOURCE_DROPPED_IN_GAP;TEMPERATURE_MEDIAN_NOT_AN_OBSERVED_VALUE` |
| v04row-095 | not_evaluated | (302.73, 36.55) | (302.73, 36.55) | 302.73@MSR-1b9deac4;302.73@MSR-67cba3e9;302.73@MSR-ea7274d5 | 36.55@MSR-231a6128;36.55@MSR-9011dc6f | `MEDIAN_T_AND_EPSILON_FROM_DIFFERENT_OBSERVATIONS;MULTI_SOURCE_DROPPED_IN_GAP` |
| v04row-097 | not_evaluated | (298.15, 14.26) | (298.15, 14.26) | 298.15@MSR-0a8aec34;298.15@MSR-0d4e51a1;298.15@MSR-4bc293c7;298.15@MSR-58f93704;298.15@MSR-5bfe46a7;298.15@MSR-7922a0cb;298.15@MSR-e63adb46;298.15@MSR-fd08b919 | not_evaluated | `EPSILON_MEDIAN_NOT_AN_OBSERVED_VALUE;MEDIAN_T_AND_EPSILON_FROM_DIFFERENT_OBSERVATIONS;MULTI_SOURCE_DROPPED_IN_GAP` |
| v04row-099 | C10 | (298.15, 7.798) | (298.15, 7.798) | 298.15@MSR-b83c1a46;298.15@MSR-f61ebea4 | not_evaluated | `EPSILON_MEDIAN_NOT_AN_OBSERVED_VALUE;MEDIAN_T_AND_EPSILON_FROM_DIFFERENT_OBSERVATIONS;MULTI_SOURCE_DROPPED_IN_GAP` |

这些行的 (T, ε) 组合**从未在同一次测量中出现过**。它们不得被当作实验记录配对, 也不得据此在测量账本里生成一条对应的"原始测量"。

## 4. 多来源聚合 (gap 丢了哪些来源)

| aggregate | A18 | 贡献来源数 | gap 丢失来源 |
|---|---|---:|---|
| v04row-003 | not_evaluated | 3 | `10.1016/j.tca.2012.10.024;10.1021/je060248p` |
| v04row-006 | not_evaluated | 5 | `10.1016/j.jct.2011.10.028;10.1016/j.tca.2013.05.022;10.1021/je060248p;10.1021/je800593p` |
| v04row-007 | not_evaluated | 2 | `10.1021/je200682t` |
| v04row-010 | not_evaluated | 4 | `10.1021/je3007666;10.1021/je800593p;10.1021/je900503p` |
| v04row-016 | not_evaluated | 2 | `10.1021/je600515j` |
| v04row-021 | not_evaluated | 3 | `10.1016/j.fluid.2009.07.009;10.1021/je9002515` |
| v04row-031 | C15 | 4 | `10.1016/j.tca.2017.03.018;10.1021/je400149j;10.1021/je9010773` |
| v04row-036 | not_evaluated | 2 | `10.1021/je200682t` |
| v04row-040 | not_evaluated | 2 | `10.1021/je060248p` |
| v04row-041 | not_evaluated | 4 | `10.1016/j.jct.2011.10.028;10.1016/j.tca.2013.05.022;10.1021/je800593p` |
| v04row-044 | not_evaluated | 7 | `10.1016/j.fluid.2013.12.014;10.1016/j.jct.2012.08.009;10.1016/j.tca.2013.05.022;10.1021/acs.jced.8b00755;10.1021/je060248p;10.1021/je800593p` |
| v04row-046 | not_evaluated | 6 | `10.1021/acs.jced.8b00755;10.1021/je060248p;10.1021/je3007666;10.1021/je800593p;10.1021/je900503p` |
| v04row-057 | not_evaluated | 5 | `10.1016/j.jct.2012.08.009;10.1016/j.tca.2013.05.022;10.1021/je060248p;10.1021/je800593p` |
| v04row-059 | not_evaluated | 2 | `10.1016/j.fluid.2009.07.009` |
| v04row-064 | not_evaluated | 2 | `10.1016/j.jct.2010.09.008` |
| v04row-068 | not_evaluated | 2 | `10.1016/j.tca.2012.10.024` |
| v04row-071 | not_evaluated | 2 | `10.1016/j.fluid.2009.07.009` |
| v04row-082 | not_evaluated | 2 | `10.1021/acs.jced.8b00755` |
| v04row-083 | not_evaluated | 3 | `10.1016/j.jct.2012.08.009;10.1021/je400149j` |
| v04row-085 | C08 | 2 | `10.1016/j.jct.2010.09.008` |
| v04row-089 | not_evaluated | 2 | `10.1016/j.jct.2010.09.008` |
| v04row-091 | not_evaluated | 2 | `10.1021/je7006692` |
| v04row-093 | not_evaluated | 2 | `10.1016/j.fluid.2009.07.009` |
| v04row-095 | not_evaluated | 3 | `10.1016/j.fluid.2009.07.009;10.1021/je9010773` |
| v04row-097 | not_evaluated | 2 | `10.1021/je060248p` |
| v04row-099 | C10 | 2 | `10.1016/j.tca.2012.10.024` |
| v04row-100 | not_evaluated | 2 | `10.1021/je800593p` |

## 5. 缺失证书 (不可恢复, 不补造)

共 148 条。以下是 A18 相关的全部证书:

| aggregate | A18 | 证书 | 说明 |
|---|---|---|---|
| v04row-104 | C12 | `NO_BAND_OBSERVATIONS_IN_SOURCE_LAYER` | v04 记录 T=298.15 eps=6.68，但 v11plus 在该分子的 293.15-303.15 K 窗口内没有任何可用的原始观测, 贡献无法重建; 不补造 |
| v04row-105 | C11 | `NO_BAND_OBSERVATIONS_IN_SOURCE_LAYER` | v04 记录 T=298.15 eps=6.02，但 v11plus 在该分子的 293.15-303.15 K 窗口内没有任何可用的原始观测, 贡献无法重建; 不补造 |
| v04row-133 | C16 | `NO_BAND_OBSERVATIONS_IN_SOURCE_LAYER` | v04 记录 T=293.15 eps=37.5，但 v11plus 在该分子的 293.15-303.15 K 窗口内没有任何可用的原始观测, 贡献无法重建; 不补造 |
| v04row-221 | C05 | `NO_BAND_OBSERVATIONS_IN_SOURCE_LAYER` | v04 记录 T=298.15 eps=64.9，但 v11plus 在该分子的 293.15-303.15 K 窗口内没有任何可用的原始观测, 贡献无法重建; 不补造 |
| v04row-222 | C04 | `NO_BAND_OBSERVATIONS_IN_SOURCE_LAYER` | v04 记录 T=313.15 eps=90.5，但 v11plus 在该分子的 293.15-303.15 K 窗口内没有任何可用的原始观测, 贡献无法重建; 不补造 |
| v04row-223 | C02 | `NO_BAND_OBSERVATIONS_IN_SOURCE_LAYER` | v04 记录 T=298.15 eps=2.96，但 v11plus 在该分子的 293.15-303.15 K 窗口内没有任何可用的原始观测, 贡献无法重建; 不补造 |
| v04row-224 | C09 | `NO_BAND_OBSERVATIONS_IN_SOURCE_LAYER` | v04 记录 T=298.15 eps=7.3，但 v11plus 在该分子的 293.15-303.15 K 窗口内没有任何可用的原始观测, 贡献无法重建; 不补造 |
| v04row-231 | C07 | `NO_BAND_OBSERVATIONS_IN_SOURCE_LAYER` | v04 记录 T=298 eps=126，但 v11plus 在该分子的 293.15-303.15 K 窗口内没有任何可用的原始观测, 贡献无法重建; 不补造 |
| v04row-244 | C17 | `NO_BAND_OBSERVATIONS_IN_SOURCE_LAYER` | v04 记录 T=298.15 eps=21.6，但 v11plus 在该分子的 293.15-303.15 K 窗口内没有任何可用的原始观测, 贡献无法重建; 不补造 |
| v04row-245 | C06 | `NO_BAND_OBSERVATIONS_IN_SOURCE_LAYER` | v04 记录 T=296.15 eps=78.4，但 v11plus 在该分子的 293.15-303.15 K 窗口内没有任何可用的原始观测, 贡献无法重建; 不补造 |
| v04row-247 | C18 | `NO_BAND_OBSERVATIONS_IN_SOURCE_LAYER` | v04 记录 T=333.15 eps=56.09，但 v11plus 在该分子的 293.15-303.15 K 窗口内没有任何可用的原始观测, 贡献无法重建; 不补造 |

其余证书明细见 `aggregate_contribution_ledger_v1.csv` 的 `contribution_certificate` 列。

## 6. 验收标准逐条

| 标准 | 结果 |
|---|---|
| `every_measurement_traceable` | True |
| `every_aggregate_has_contribution_or_certificate` | True |
| `no_synthetic_pair_marked_valid` | True |
| `synthetic_pair_check_coverage` | {'n_rows_total': 248, 'n_rows_inspected': 248, 'n_rows_valid': 78, 'n_rows_invalid': 170, 'n_valid_with_shared_holder': 78, 'n_valid_without_holders': 0, 'criterion_can_fail': True, 'note': '本判据检查全部行 (不再按 invalidity_reason 过滤). criterion_can_fail 为 true 表示存在可失败的输入, 判据不是同义反复.'} |
| `multi_source_keeps_all_contributors` | True |
| `duplicate_transcription_not_independent` | True |
| `old_new_comparable` | True |
| `deterministic_rebuild` | True |
| `frozen_outputs_unchanged` | True |

## 7. 对 J03 三处口径的更正

| 项 | J03 的写法 | 更正 |
|---|---|---|
| `N_measurement=460` | 标为原始测量总数 | 460 是 **v04 聚合窗口内** 观测数; 全量测量为 2065 |
| `460→34→58→0` | 写成连续下降 | 34→58 是**上升**; 且 34 (窗口内来源文档) 与 58 (条件合格行) 统计单位不同, 不能串成单调漏斗 |
| `N_independent=34` | 未标口径 | 34 是**窗口内**来源文档数; 全量为 61 |

## 8. 冻结输入

| 输入 | bytes | sha256 |
|---|---:|---|
| `a_core_set` | 3149 | `630b0ee8c09dc414` |
| `admission_gap` | 50040 | `597efaf8355483a9` |
| `candidate_master` | 72349 | `63b9ff45561c9a49` |
| `dielectric_v04` | 134460 | `e046a3831630e36a` |
| `observations_v11plus` | 921601 | `159b928f800a5596` |
| `target_protocol` | 13420 | `0e848eb6fd8619f8` |

## 9. 明确不做的事

- 不修改 `dielectric_v04.csv` / gap 表 / pool_C / backfill
- 不改变 J01/J02/J03 与 J04-A/B 的冻结产物
- 不补造无法恢复的测量 (写缺失证书)
- 不声称 DOI 数等于独立实验数
- 不把本账本当作已获得人工准入

