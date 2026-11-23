# B-G0-J03 聚合来源可追溯性检查器

- 契约: `confirm_2027.aggregation_provenance/v1` / `confirm_2027.j03_inputs/v1`
- 本报告不含墙钟时间, 可由固定输入逐字节重建
- 聚合窗口: 293.15-303.15 K, liquid, 0 Hz

## 1. 六值裁决分布

| 裁决 | 行数 | 含义 | 后续 |
|---|---:|---|---|
| `RAW_SINGLE_OBSERVATION` | 48 | 原始单条观测 | 可直接核对 |
| `SINGLE_SOURCE_AGGREGATE` | 10 | 单来源多观测聚合 | 回溯原始测量 |
| `MULTI_SOURCE_AGGREGATE` | 3 | 多来源聚合 | 必须拆分来源 |
| `PROVENANCE_INCOMPLETE` | 148 | 来源贡献记录不完整 | HOLD |
| `AGGREGATION_UNDOCUMENTED` | 17 | 聚合规则不明 | HOLD |
| `COMPOSITE_CONDITION_UNMATCHED` | 22 | 温度与 ε 无法对应到同一实验 | 人工复核 |

## 2. 证据转化链

| 阶段 | 值 | 定义 | 该层损失原因 |
|---|---:|---|---|
| `N_database` | 248 | v04 主表行数 (聚合后的化合物-条件行) | not_evaluated |
| `N_measurement` | 460 | v04 聚合窗口内的原始观测条数 (逐行累加) | 聚合把多条观测压成一行; 行数不等于测量数 |
| `N_independent` | 34 | 带内贡献观测涉及的独立来源文档数 | 同一来源的多条转录不构成独立证据 |
| `N_condition_qualified` | 58 | T 与 epsilon 可对应到同一次测量的行数 | 中位数分别计算导致组合不对应 |
| `N_admitted` | 0 | measurement_decision = ACCEPT 的行数 | 人工准入未完成 |

N_database 与 N_measurement 之间隔着聚合, N_measurement 与 N_independent 之间隔着来源去重, N_independent 与 N_condition_qualified 之间隔着合成条件对, N_condition_qualified 与 N_admitted 之间隔着人工准入。四个损失机制彼此独立。

## 3. 五个检查维度 (逐行)

| 测量 | A18 | 带内 n | 来源数 | T中位数在带内 | ε中位数在带内 | 同条观测配对 | 单键回溯 | 裁决 |
|---|---|---:|---:|---|---|---|---|---|
| EPSV04-R001 | — | 1 | 1 | true | true | true | true | `RAW_SINGLE_OBSERVATION` |
| EPSV04-R002 | — | 1 | 1 | true | true | true | true | `RAW_SINGLE_OBSERVATION` |
| EPSV04-R003 | — | 13 | 3 | true | true | false | true | `COMPOSITE_CONDITION_UNMATCHED` |
| EPSV04-R004 | — | 5 | 1 | true | true | true | true | `SINGLE_SOURCE_AGGREGATE` |
| EPSV04-R005 | — | 7 | 1 | true | true | true | true | `AGGREGATION_UNDOCUMENTED` |
| EPSV04-R006 | — | 13 | 5 | true | true | true | true | `MULTI_SOURCE_AGGREGATE` |
| EPSV04-R007 | — | 6 | 2 | true | false | false | true | `COMPOSITE_CONDITION_UNMATCHED` |
| EPSV04-R008 | — | 1 | 1 | true | true | true | true | `RAW_SINGLE_OBSERVATION` |
| EPSV04-R009 | — | 1 | 1 | true | true | true | true | `RAW_SINGLE_OBSERVATION` |
| EPSV04-R010 | — | 10 | 4 | true | true | true | true | `MULTI_SOURCE_AGGREGATE` |
| EPSV04-R011 | — | 5 | 1 | true | true | true | true | `AGGREGATION_UNDOCUMENTED` |
| EPSV04-R012 | — | 5 | 1 | true | true | true | true | `SINGLE_SOURCE_AGGREGATE` |
| EPSV04-R013 | — | 1 | 1 | true | true | true | true | `RAW_SINGLE_OBSERVATION` |
| EPSV04-R014 | — | 5 | 1 | true | true | true | true | `SINGLE_SOURCE_AGGREGATE` |
| EPSV04-R015 | — | 5 | 1 | true | true | true | true | `AGGREGATION_UNDOCUMENTED` |
| EPSV04-R016 | — | 4 | 2 | false | false | false | true | `COMPOSITE_CONDITION_UNMATCHED` |
| EPSV04-R017 | — | 3 | 1 | true | true | true | true | `SINGLE_SOURCE_AGGREGATE` |
| EPSV04-R018 | — | 1 | 1 | true | true | true | true | `RAW_SINGLE_OBSERVATION` |
| EPSV04-R019 | — | 3 | 1 | true | true | true | true | `AGGREGATION_UNDOCUMENTED` |
| EPSV04-R020 | — | 1 | 1 | true | true | true | true | `RAW_SINGLE_OBSERVATION` |
| EPSV04-R021 | — | 3 | 3 | true | true | true | true | `AGGREGATION_UNDOCUMENTED` |
| EPSV04-R022 | — | 29 | 1 | true | true | true | true | `AGGREGATION_UNDOCUMENTED` |
| EPSV04-R023 | — | 1 | 1 | true | true | true | true | `RAW_SINGLE_OBSERVATION` |
| EPSV04-R024 | — | 1 | 1 | true | true | true | true | `RAW_SINGLE_OBSERVATION` |
| EPSV04-R025 | — | 1 | 1 | true | true | true | true | `RAW_SINGLE_OBSERVATION` |
| EPSV04-R026 | — | 1 | 1 | true | true | true | true | `RAW_SINGLE_OBSERVATION` |
| EPSV04-R027 | — | 1 | 1 | true | true | true | true | `RAW_SINGLE_OBSERVATION` |
| EPSV04-R028 | C14 | 3 | 1 | true | true | true | true | `SINGLE_SOURCE_AGGREGATE` |
| EPSV04-R029 | — | 1 | 1 | true | true | true | true | `RAW_SINGLE_OBSERVATION` |
| EPSV04-R030 | — | 1 | 1 | true | true | true | true | `RAW_SINGLE_OBSERVATION` |
| EPSV04-R031 | C15 | 35 | 4 | true | true | false | true | `COMPOSITE_CONDITION_UNMATCHED` |
| EPSV04-R032 | C01 | 1 | 1 | true | true | true | true | `RAW_SINGLE_OBSERVATION` |
| EPSV04-R033 | — | 2 | 1 | false | false | false | true | `COMPOSITE_CONDITION_UNMATCHED` |
| EPSV04-R034 | — | 1 | 1 | true | true | true | true | `RAW_SINGLE_OBSERVATION` |
| EPSV04-R035 | — | 1 | 1 | true | true | true | true | `RAW_SINGLE_OBSERVATION` |
| EPSV04-R036 | — | 6 | 2 | true | false | false | true | `COMPOSITE_CONDITION_UNMATCHED` |
| EPSV04-R037 | — | 5 | 1 | true | true | true | true | `AGGREGATION_UNDOCUMENTED` |
| EPSV04-R038 | — | 1 | 1 | true | true | true | true | `RAW_SINGLE_OBSERVATION` |
| EPSV04-R039 | — | 1 | 1 | true | true | true | true | `RAW_SINGLE_OBSERVATION` |
| EPSV04-R040 | — | 6 | 2 | true | false | false | true | `COMPOSITE_CONDITION_UNMATCHED` |
| EPSV04-R041 | — | 6 | 4 | false | false | false | true | `COMPOSITE_CONDITION_UNMATCHED` |
| EPSV04-R042 | — | 1 | 1 | true | true | true | true | `RAW_SINGLE_OBSERVATION` |
| EPSV04-R043 | — | 1 | 1 | true | true | true | true | `RAW_SINGLE_OBSERVATION` |
| EPSV04-R044 | — | 15 | 7 | true | true | false | true | `COMPOSITE_CONDITION_UNMATCHED` |
| EPSV04-R045 | — | 5 | 1 | true | true | true | true | `SINGLE_SOURCE_AGGREGATE` |
| EPSV04-R046 | — | 18 | 6 | true | false | false | true | `COMPOSITE_CONDITION_UNMATCHED` |
| EPSV04-R047 | — | 1 | 1 | true | true | true | true | `RAW_SINGLE_OBSERVATION` |
| EPSV04-R048 | — | 1 | 1 | true | true | true | true | `RAW_SINGLE_OBSERVATION` |
| EPSV04-R049 | — | 1 | 1 | true | true | true | true | `RAW_SINGLE_OBSERVATION` |
| EPSV04-R050 | — | 1 | 1 | true | true | true | true | `RAW_SINGLE_OBSERVATION` |
| EPSV04-R051 | — | 1 | 1 | true | true | true | true | `RAW_SINGLE_OBSERVATION` |
| EPSV04-R052 | — | 3 | 1 | true | true | true | true | `AGGREGATION_UNDOCUMENTED` |
| EPSV04-R053 | — | 1 | 1 | true | true | true | true | `RAW_SINGLE_OBSERVATION` |
| EPSV04-R054 | — | 1 | 1 | true | true | true | true | `RAW_SINGLE_OBSERVATION` |
| EPSV04-R055 | — | 1 | 1 | true | true | true | true | `RAW_SINGLE_OBSERVATION` |
| EPSV04-R056 | C03 | 1 | 1 | true | true | true | true | `RAW_SINGLE_OBSERVATION` |
| EPSV04-R057 | — | 13 | 5 | true | true | false | true | `COMPOSITE_CONDITION_UNMATCHED` |
| EPSV04-R058 | — | 1 | 1 | true | true | true | true | `RAW_SINGLE_OBSERVATION` |
| EPSV04-R059 | — | 2 | 2 | true | true | true | true | `AGGREGATION_UNDOCUMENTED` |
| EPSV04-R060 | — | 1 | 1 | true | true | true | true | `RAW_SINGLE_OBSERVATION` |
| EPSV04-R061 | — | 1 | 1 | true | true | true | true | `RAW_SINGLE_OBSERVATION` |
| EPSV04-R062 | — | 1 | 1 | true | true | true | true | `RAW_SINGLE_OBSERVATION` |
| EPSV04-R063 | — | 1 | 1 | true | true | true | true | `RAW_SINGLE_OBSERVATION` |
| EPSV04-R064 | — | 2 | 2 | true | false | false | true | `COMPOSITE_CONDITION_UNMATCHED` |
| EPSV04-R065 | — | 5 | 1 | true | true | true | true | `AGGREGATION_UNDOCUMENTED` |
| EPSV04-R066 | — | 1 | 1 | true | true | true | true | `RAW_SINGLE_OBSERVATION` |
| EPSV04-R067 | — | 1 | 1 | true | true | true | true | `RAW_SINGLE_OBSERVATION` |
| EPSV04-R068 | — | 6 | 2 | true | true | true | true | `MULTI_SOURCE_AGGREGATE` |
| EPSV04-R069 | — | 1 | 1 | true | true | true | true | `RAW_SINGLE_OBSERVATION` |
| EPSV04-R070 | — | 1 | 1 | true | true | true | true | `RAW_SINGLE_OBSERVATION` |
| EPSV04-R071 | — | 2 | 2 | true | true | true | true | `AGGREGATION_UNDOCUMENTED` |
| EPSV04-R072 | — | 1 | 1 | true | true | true | true | `RAW_SINGLE_OBSERVATION` |
| EPSV04-R073 | — | 1 | 1 | true | true | true | true | `RAW_SINGLE_OBSERVATION` |
| EPSV04-R074 | — | 3 | 1 | true | true | true | true | `SINGLE_SOURCE_AGGREGATE` |
| EPSV04-R075 | — | 1 | 1 | true | true | true | true | `RAW_SINGLE_OBSERVATION` |
| EPSV04-R076 | — | 5 | 1 | true | true | true | true | `SINGLE_SOURCE_AGGREGATE` |
| EPSV04-R077 | — | 1 | 1 | true | true | true | true | `RAW_SINGLE_OBSERVATION` |
| EPSV04-R078 | — | 1 | 1 | true | true | true | true | `RAW_SINGLE_OBSERVATION` |
| EPSV04-R079 | — | 5 | 1 | true | true | true | true | `SINGLE_SOURCE_AGGREGATE` |
| EPSV04-R080 | — | 32 | 1 | false | false | false | true | `COMPOSITE_CONDITION_UNMATCHED` |
| EPSV04-R081 | — | 1 | 1 | true | true | true | true | `RAW_SINGLE_OBSERVATION` |
| EPSV04-R082 | — | 3 | 2 | true | true | true | true | `AGGREGATION_UNDOCUMENTED` |
| EPSV04-R083 | — | 8 | 3 | false | false | false | true | `COMPOSITE_CONDITION_UNMATCHED` |
| EPSV04-R084 | — | 4 | 1 | false | false | false | true | `COMPOSITE_CONDITION_UNMATCHED` |
| EPSV04-R085 | C08 | 2 | 2 | true | false | false | true | `COMPOSITE_CONDITION_UNMATCHED` |
| EPSV04-R086 | C13 | 4 | 1 | false | false | false | true | `COMPOSITE_CONDITION_UNMATCHED` |
| EPSV04-R087 | — | 3 | 1 | true | true | true | true | `AGGREGATION_UNDOCUMENTED` |
| EPSV04-R088 | — | 29 | 1 | true | true | true | true | `AGGREGATION_UNDOCUMENTED` |
| EPSV04-R089 | — | 2 | 2 | true | false | false | true | `COMPOSITE_CONDITION_UNMATCHED` |
| EPSV04-R090 | — | 1 | 1 | true | true | true | true | `RAW_SINGLE_OBSERVATION` |
| EPSV04-R091 | — | 8 | 2 | false | false | false | true | `COMPOSITE_CONDITION_UNMATCHED` |
| EPSV04-R092 | — | 1 | 1 | true | true | true | true | `RAW_SINGLE_OBSERVATION` |
| EPSV04-R093 | — | 2 | 2 | true | true | true | true | `AGGREGATION_UNDOCUMENTED` |
| EPSV04-R094 | — | 3 | 1 | true | true | true | true | `SINGLE_SOURCE_AGGREGATE` |
| EPSV04-R095 | — | 26 | 3 | true | true | false | true | `COMPOSITE_CONDITION_UNMATCHED` |
| EPSV04-R096 | — | 1 | 1 | true | true | true | true | `RAW_SINGLE_OBSERVATION` |
| EPSV04-R097 | — | 8 | 2 | true | false | false | true | `COMPOSITE_CONDITION_UNMATCHED` |
| EPSV04-R098 | — | 5 | 1 | true | true | true | true | `AGGREGATION_UNDOCUMENTED` |
| EPSV04-R099 | C10 | 4 | 2 | true | false | false | true | `COMPOSITE_CONDITION_UNMATCHED` |
| EPSV04-R100 | — | 6 | 2 | true | true | true | true | `AGGREGATION_UNDOCUMENTED` |
| EPSV04-R101 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R102 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R103 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R104 | C12 | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R105 | C11 | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R106 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R107 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R108 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R109 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R110 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R111 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R112 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R113 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R114 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R115 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R116 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R117 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R118 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R119 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R120 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R121 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R122 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R123 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R124 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R125 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R126 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R127 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R128 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R129 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R130 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R131 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R132 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R133 | C16 | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R134 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R135 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R136 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R137 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R138 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R139 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R140 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R141 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R142 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R143 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R144 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R145 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R146 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R147 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R148 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R149 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R150 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R151 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R152 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R153 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R154 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R155 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R156 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R157 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R158 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R159 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R160 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R161 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R162 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R163 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R164 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R165 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R166 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R167 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R168 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R169 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R170 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R171 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R172 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R173 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R174 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R175 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R176 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R177 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R178 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R179 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R180 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R181 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R182 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R183 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R184 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R185 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R186 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R187 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R188 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R189 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R190 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R191 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R192 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R193 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R194 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R195 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R196 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R197 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R198 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R199 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R200 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R201 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R202 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R203 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R204 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R205 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R206 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R207 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R208 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R209 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R210 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R211 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R212 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R213 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R214 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R215 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R216 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R217 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R218 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R219 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R220 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R221 | C05 | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R222 | C04 | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R223 | C02 | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R224 | C09 | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R225 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R226 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R227 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R228 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R229 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R230 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R231 | C07 | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R232 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R233 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R234 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R235 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R236 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R237 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R238 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R239 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R240 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R241 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R242 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R243 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R244 | C17 | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R245 | C06 | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R246 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R247 | C18 | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |
| EPSV04-R248 | — | 0 | 0 | false | false | false | false | `PROVENANCE_INCOMPLETE` |

## 4. 合成条件对 (T 与 ε 来自不同观测)

| 测量 | A18 | gap (T, ε) | T 中位数持有者 | ε 中位数持有者 | 真实配对数 |
|---|---|---|---|---|---|
| EPSV04-R003 | not_evaluated | (298.15, 15.736) | 298.15@6;298.15@7;298.15@8;298.15@9;298.15@10;298.15@11;298.15@12;298.15@13;298.15@14 | 15.736@4 | 0 |
| EPSV04-R007 | not_evaluated | (298.15, 13.505) | 298.15@89;298.15@90 | not_evaluated | 0 |
| EPSV04-R016 | not_evaluated | (300.65, 22.12) | not_evaluated | not_evaluated | 0 |
| EPSV04-R031 | C15 | (298, 46.05) | 298@493 | 46.05@483;46.05@484 | 0 |
| EPSV04-R033 | not_evaluated | (300.65, 14.38) | not_evaluated | not_evaluated | 0 |
| EPSV04-R036 | not_evaluated | (298.15, 15.79) | 298.15@614;298.15@615 | not_evaluated | 0 |
| EPSV04-R040 | not_evaluated | (298.15, 10.66) | 298.15@649;298.15@650;298.15@651;298.15@652;298.15@653;298.15@654 | not_evaluated | 0 |
| EPSV04-R041 | not_evaluated | (299.15, 18.845) | not_evaluated | not_evaluated | 0 |
| EPSV04-R044 | not_evaluated | (298.15, 25.02) | 298.15@816;298.15@817;298.15@818;298.15@819;298.15@820;298.15@821;298.15@822;298.15@823;298.15@824 | 25.02@813 | 0 |
| EPSV04-R046 | not_evaluated | (298.15, 18.03) | 298.15@872;298.15@873;298.15@874;298.15@875;298.15@876;298.15@877;298.15@878;298.15@879;298.15@880;298.15@881;298.15@882 | not_evaluated | 0 |
| EPSV04-R057 | not_evaluated | (298.15, 33.6) | 298.15@923;298.15@924;298.15@925;298.15@926;298.15@927;298.15@928;298.15@929;298.15@930 | 33.6@921 | 0 |
| EPSV04-R064 | not_evaluated | (298.15, 7.3815) | 298.15@947;298.15@948 | not_evaluated | 0 |
| EPSV04-R080 | not_evaluated | (298.115, 11.8861) | not_evaluated | not_evaluated | 0 |
| EPSV04-R083 | not_evaluated | (297.575, 78.87) | not_evaluated | not_evaluated | 0 |
| EPSV04-R084 | not_evaluated | (299.4, 10.76) | not_evaluated | not_evaluated | 0 |
| EPSV04-R085 | C08 | (298.15, 7.0695) | 298.15@1214;298.15@1215 | not_evaluated | 0 |
| EPSV04-R086 | C13 | (295.65, 41.99) | not_evaluated | not_evaluated | 0 |
| EPSV04-R089 | not_evaluated | (298.15, 7.604) | 298.15@1375;298.15@1376 | not_evaluated | 0 |
| EPSV04-R091 | not_evaluated | (297.385, 2.40445) | not_evaluated | not_evaluated | 0 |
| EPSV04-R095 | not_evaluated | (302.73, 36.55) | 302.73@1521;302.73@1522;302.73@1523 | 36.55@1534;36.55@1535 | 0 |
| EPSV04-R097 | not_evaluated | (298.15, 14.26) | 298.15@1576;298.15@1577;298.15@1578;298.15@1579;298.15@1580;298.15@1581;298.15@1582;298.15@1583 | not_evaluated | 0 |
| EPSV04-R099 | C10 | (298.15, 7.798) | 298.15@1617;298.15@1618 | not_evaluated | 0 |
| EPSV04-R101 | not_evaluated | (303.15, 13) | not_evaluated | not_evaluated | 0 |
| EPSV04-R102 | not_evaluated | (298.15, 8.03) | not_evaluated | not_evaluated | 0 |
| EPSV04-R103 | not_evaluated | (303.15, 7.57) | not_evaluated | not_evaluated | 0 |
| EPSV04-R104 | C12 | (298.15, 6.68) | not_evaluated | not_evaluated | 0 |
| EPSV04-R105 | C11 | (298.15, 6.02) | not_evaluated | not_evaluated | 0 |
| EPSV04-R106 | not_evaluated | (298.15, 6.49) | not_evaluated | not_evaluated | 0 |
| EPSV04-R107 | not_evaluated | (293.15, 5.01) | not_evaluated | not_evaluated | 0 |
| EPSV04-R108 | not_evaluated | (293.15, 5.29) | not_evaluated | not_evaluated | 0 |
| EPSV04-R109 | not_evaluated | (303.15, 16) | not_evaluated | not_evaluated | 0 |
| EPSV04-R110 | not_evaluated | (298.15, 18.2) | not_evaluated | not_evaluated | 0 |
| EPSV04-R111 | not_evaluated | (298.15, 20.7) | not_evaluated | not_evaluated | 0 |
| EPSV04-R112 | not_evaluated | (293.15, 4.335) | not_evaluated | not_evaluated | 0 |
| EPSV04-R113 | not_evaluated | (293.15, 15.45) | not_evaluated | not_evaluated | 0 |
| EPSV04-R114 | not_evaluated | (293.15, 17) | not_evaluated | not_evaluated | 0 |
| EPSV04-R115 | not_evaluated | (293.15, 13.11) | not_evaluated | not_evaluated | 0 |
| EPSV04-R116 | not_evaluated | (298.15, 25.2) | not_evaluated | not_evaluated | 0 |
| EPSV04-R117 | not_evaluated | (293.15, 39.5) | not_evaluated | not_evaluated | 0 |
| EPSV04-R118 | not_evaluated | (293.15, 40) | not_evaluated | not_evaluated | 0 |
| EPSV04-R119 | not_evaluated | (293.15, 15.9) | not_evaluated | not_evaluated | 0 |
| EPSV04-R120 | not_evaluated | (298.15, 13.9) | not_evaluated | not_evaluated | 0 |
| EPSV04-R121 | not_evaluated | (294.15, 29.3) | not_evaluated | not_evaluated | 0 |
| EPSV04-R122 | not_evaluated | (293.15, 35) | not_evaluated | not_evaluated | 0 |
| EPSV04-R123 | not_evaluated | (293.15, 2.97) | not_evaluated | not_evaluated | 0 |
| EPSV04-R124 | not_evaluated | (298.15, 7.33) | not_evaluated | not_evaluated | 0 |
| EPSV04-R125 | not_evaluated | (303.15, 30.2) | not_evaluated | not_evaluated | 0 |
| EPSV04-R126 | not_evaluated | (293.15, 3.49) | not_evaluated | not_evaluated | 0 |
| EPSV04-R127 | not_evaluated | (293.15, 2.66) | not_evaluated | not_evaluated | 0 |
| EPSV04-R128 | not_evaluated | (293.15, 2.64) | not_evaluated | not_evaluated | 0 |
| EPSV04-R129 | not_evaluated | (298.15, 6.31) | not_evaluated | not_evaluated | 0 |
| EPSV04-R130 | not_evaluated | (303.15, 24.4) | not_evaluated | not_evaluated | 0 |
| EPSV04-R131 | not_evaluated | (298.15, 3.8) | not_evaluated | not_evaluated | 0 |
| EPSV04-R132 | not_evaluated | (303.15, 7.06) | not_evaluated | not_evaluated | 0 |
| EPSV04-R133 | C16 | (293.15, 37.5) | not_evaluated | not_evaluated | 0 |
| EPSV04-R134 | not_evaluated | (298.15, 5.02) | not_evaluated | not_evaluated | 0 |
| EPSV04-R135 | not_evaluated | (293.15, 27.2) | not_evaluated | not_evaluated | 0 |
| EPSV04-R136 | not_evaluated | (293.15, 36.1) | not_evaluated | not_evaluated | 0 |
| EPSV04-R137 | not_evaluated | (293.15, 18.51) | not_evaluated | not_evaluated | 0 |
| EPSV04-R138 | not_evaluated | (293.15, 18) | not_evaluated | not_evaluated | 0 |
| EPSV04-R139 | not_evaluated | (298.15, 14.7) | not_evaluated | not_evaluated | 0 |
| EPSV04-R140 | not_evaluated | (298.15, 5.82) | not_evaluated | not_evaluated | 0 |
| EPSV04-R141 | not_evaluated | (299.15, 3.39) | not_evaluated | not_evaluated | 0 |
| EPSV04-R142 | not_evaluated | (298.15, 3.88) | not_evaluated | not_evaluated | 0 |
| EPSV04-R143 | not_evaluated | (293.15, 13.1) | not_evaluated | not_evaluated | 0 |
| EPSV04-R144 | not_evaluated | (298.15, 11.5) | not_evaluated | not_evaluated | 0 |
| EPSV04-R145 | not_evaluated | (298.15, 11.8) | not_evaluated | not_evaluated | 0 |
| EPSV04-R146 | not_evaluated | (298.15, 4.33) | not_evaluated | not_evaluated | 0 |
| EPSV04-R147 | not_evaluated | (293.15, 14) | not_evaluated | not_evaluated | 0 |
| EPSV04-R148 | not_evaluated | (293.15, 12.4) | not_evaluated | not_evaluated | 0 |
| EPSV04-R149 | not_evaluated | (293.15, 12.4) | not_evaluated | not_evaluated | 0 |
| EPSV04-R150 | not_evaluated | (293.15, 13.3) | not_evaluated | not_evaluated | 0 |
| EPSV04-R151 | not_evaluated | (293.15, 12.3) | not_evaluated | not_evaluated | 0 |
| EPSV04-R152 | not_evaluated | (293.15, 13.3) | not_evaluated | not_evaluated | 0 |
| EPSV04-R153 | not_evaluated | (293.15, 2.641) | not_evaluated | not_evaluated | 0 |
| EPSV04-R154 | not_evaluated | (293.15, 2.436) | not_evaluated | not_evaluated | 0 |
| EPSV04-R155 | not_evaluated | (298.15, 5.621) | not_evaluated | not_evaluated | 0 |
| EPSV04-R156 | not_evaluated | (293.15, 2.1) | not_evaluated | not_evaluated | 0 |
| EPSV04-R157 | not_evaluated | (293.15, 2.197) | not_evaluated | not_evaluated | 0 |
| EPSV04-R158 | not_evaluated | (293.15, 1.965) | not_evaluated | not_evaluated | 0 |
| EPSV04-R159 | not_evaluated | (293.15, 1.933) | not_evaluated | not_evaluated | 0 |
| EPSV04-R160 | not_evaluated | (293.15, 1.844) | not_evaluated | not_evaluated | 0 |
| EPSV04-R161 | not_evaluated | (293.15, 1.843) | not_evaluated | not_evaluated | 0 |
| EPSV04-R162 | not_evaluated | (293.15, 2.284) | not_evaluated | not_evaluated | 0 |
| EPSV04-R163 | not_evaluated | (298.15, 2.22) | not_evaluated | not_evaluated | 0 |
| EPSV04-R164 | not_evaluated | (293.15, 1.985) | not_evaluated | not_evaluated | 0 |
| EPSV04-R165 | not_evaluated | (293.15, 1.965) | not_evaluated | not_evaluated | 0 |
| EPSV04-R166 | not_evaluated | (298.15, 2.062) | not_evaluated | not_evaluated | 0 |
| EPSV04-R167 | not_evaluated | (298.15, 2) | not_evaluated | not_evaluated | 0 |
| EPSV04-R168 | not_evaluated | (293.15, 1.89) | not_evaluated | not_evaluated | 0 |
| EPSV04-R169 | not_evaluated | (298.15, 2.55) | not_evaluated | not_evaluated | 0 |
| EPSV04-R170 | not_evaluated | (293.15, 2.6) | not_evaluated | not_evaluated | 0 |
| EPSV04-R171 | not_evaluated | (298.15, 2.3) | not_evaluated | not_evaluated | 0 |
| EPSV04-R172 | not_evaluated | (293.15, 2.17) | not_evaluated | not_evaluated | 0 |
| EPSV04-R173 | not_evaluated | (303.15, 9.18) | not_evaluated | not_evaluated | 0 |
| EPSV04-R174 | not_evaluated | (298.15, 9.2) | not_evaluated | not_evaluated | 0 |
| EPSV04-R175 | not_evaluated | (298.15, 2.14) | not_evaluated | not_evaluated | 0 |
| EPSV04-R176 | not_evaluated | (293.15, 14.2) | not_evaluated | not_evaluated | 0 |
| EPSV04-R177 | not_evaluated | (294.15, 19.5) | not_evaluated | not_evaluated | 0 |
| EPSV04-R178 | not_evaluated | (293.15, 6.8) | not_evaluated | not_evaluated | 0 |
| EPSV04-R179 | not_evaluated | (293.15, 4.58) | not_evaluated | not_evaluated | 0 |
| EPSV04-R180 | not_evaluated | (293.15, 7.35) | not_evaluated | not_evaluated | 0 |
| EPSV04-R181 | not_evaluated | (293.15, 4.8) | not_evaluated | not_evaluated | 0 |
| EPSV04-R182 | not_evaluated | (298.15, 9.93) | not_evaluated | not_evaluated | 0 |
| EPSV04-R183 | not_evaluated | (298.15, 5.04) | not_evaluated | not_evaluated | 0 |
| EPSV04-R184 | not_evaluated | (298.15, 4.25) | not_evaluated | not_evaluated | 0 |
| EPSV04-R185 | not_evaluated | (298.15, 5.26) | not_evaluated | not_evaluated | 0 |
| EPSV04-R186 | not_evaluated | (298.15, 2.44) | not_evaluated | not_evaluated | 0 |
| EPSV04-R187 | not_evaluated | (298.15, 2.95) | not_evaluated | not_evaluated | 0 |
| EPSV04-R188 | not_evaluated | (298.15, 4.95) | not_evaluated | not_evaluated | 0 |
| EPSV04-R189 | not_evaluated | (298.15, 5.72) | not_evaluated | not_evaluated | 0 |
| EPSV04-R190 | not_evaluated | (298.15, 12.3) | not_evaluated | not_evaluated | 0 |
| EPSV04-R191 | not_evaluated | (293.15, 4.24) | not_evaluated | not_evaluated | 0 |
| EPSV04-R192 | not_evaluated | (293.15, 5.89) | not_evaluated | not_evaluated | 0 |
| EPSV04-R193 | not_evaluated | (298.15, 4.55) | not_evaluated | not_evaluated | 0 |
| EPSV04-R194 | not_evaluated | (298.15, 5.4) | not_evaluated | not_evaluated | 0 |
| EPSV04-R195 | not_evaluated | (298.15, 5.42) | not_evaluated | not_evaluated | 0 |
| EPSV04-R196 | not_evaluated | (293.15, 4.63) | not_evaluated | not_evaluated | 0 |
| EPSV04-R197 | not_evaluated | (293.15, 6.89) | not_evaluated | not_evaluated | 0 |
| EPSV04-R198 | not_evaluated | (298.15, 2.42) | not_evaluated | not_evaluated | 0 |
| EPSV04-R199 | not_evaluated | (293.15, 4.45) | not_evaluated | not_evaluated | 0 |
| EPSV04-R200 | not_evaluated | (293.15, 5.55) | not_evaluated | not_evaluated | 0 |
| EPSV04-R201 | not_evaluated | (293.15, 6.08) | not_evaluated | not_evaluated | 0 |
| EPSV04-R202 | not_evaluated | (303.15, 4.22) | not_evaluated | not_evaluated | 0 |
| EPSV04-R203 | not_evaluated | (303.15, 5.42) | not_evaluated | not_evaluated | 0 |
| EPSV04-R204 | not_evaluated | (303.15, 5.86) | not_evaluated | not_evaluated | 0 |
| EPSV04-R205 | not_evaluated | (293.15, 1.875) | not_evaluated | not_evaluated | 0 |
| EPSV04-R206 | not_evaluated | (298.15, 2.32) | not_evaluated | not_evaluated | 0 |
| EPSV04-R207 | not_evaluated | (298.15, 2.1) | not_evaluated | not_evaluated | 0 |
| EPSV04-R208 | not_evaluated | (298.15, 2.22) | not_evaluated | not_evaluated | 0 |
| EPSV04-R209 | not_evaluated | (298.15, 2.42) | not_evaluated | not_evaluated | 0 |
| EPSV04-R210 | not_evaluated | (298.15, 2.43) | not_evaluated | not_evaluated | 0 |
| EPSV04-R211 | not_evaluated | (298.15, 22) | not_evaluated | not_evaluated | 0 |
| EPSV04-R212 | not_evaluated | (298.15, 21) | not_evaluated | not_evaluated | 0 |
| EPSV04-R213 | not_evaluated | (298.15, 16.3) | not_evaluated | not_evaluated | 0 |
| EPSV04-R214 | not_evaluated | (298.15, 13) | not_evaluated | not_evaluated | 0 |
| EPSV04-R215 | not_evaluated | (298.15, 10.6) | not_evaluated | not_evaluated | 0 |
| EPSV04-R216 | not_evaluated | (298.15, 9.1) | not_evaluated | not_evaluated | 0 |
| EPSV04-R217 | not_evaluated | (298.15, 2.6) | not_evaluated | not_evaluated | 0 |
| EPSV04-R218 | not_evaluated | (298.15, 2.1) | not_evaluated | not_evaluated | 0 |
| EPSV04-R219 | not_evaluated | (293.15, 2.05) | not_evaluated | not_evaluated | 0 |
| EPSV04-R220 | not_evaluated | (293.15, 2.96) | not_evaluated | not_evaluated | 0 |
| EPSV04-R221 | C05 | (298.15, 64.9) | not_evaluated | not_evaluated | 0 |
| EPSV04-R222 | C04 | (313.15, 90.5) | not_evaluated | not_evaluated | 0 |
| EPSV04-R223 | C02 | (298.15, 2.96) | not_evaluated | not_evaluated | 0 |
| EPSV04-R224 | C09 | (298.15, 7.3) | not_evaluated | not_evaluated | 0 |
| EPSV04-R225 | not_evaluated | (298.15, 7.5) | not_evaluated | not_evaluated | 0 |
| EPSV04-R226 | not_evaluated | (298.15, 6.2) | not_evaluated | not_evaluated | 0 |
| EPSV04-R227 | not_evaluated | (298.15, 36.1) | not_evaluated | not_evaluated | 0 |
| EPSV04-R228 | not_evaluated | (298.15, 3.2) | not_evaluated | not_evaluated | 0 |
| EPSV04-R229 | not_evaluated | (298.15, 2.8) | not_evaluated | not_evaluated | 0 |
| EPSV04-R230 | not_evaluated | (298.15, 2.5) | not_evaluated | not_evaluated | 0 |
| EPSV04-R231 | C07 | (298, 126) | not_evaluated | not_evaluated | 0 |
| EPSV04-R232 | not_evaluated | (298.15, 6.2) | not_evaluated | not_evaluated | 0 |
| EPSV04-R233 | not_evaluated | (298.15, 5.48) | not_evaluated | not_evaluated | 0 |
| EPSV04-R234 | not_evaluated | (298.15, 7.1) | not_evaluated | not_evaluated | 0 |
| EPSV04-R235 | not_evaluated | (298.15, 4.2) | not_evaluated | not_evaluated | 0 |
| EPSV04-R236 | not_evaluated | (298.15, 32.2) | not_evaluated | not_evaluated | 0 |
| EPSV04-R237 | not_evaluated | (298.15, 10.7) | not_evaluated | not_evaluated | 0 |
| EPSV04-R238 | not_evaluated | (298.15, 20.79) | not_evaluated | not_evaluated | 0 |
| EPSV04-R239 | not_evaluated | (298.15, 9) | not_evaluated | not_evaluated | 0 |
| EPSV04-R240 | not_evaluated | (298.15, 9.5) | not_evaluated | not_evaluated | 0 |
| EPSV04-R241 | not_evaluated | (298.15, 9.65) | not_evaluated | not_evaluated | 0 |
| EPSV04-R242 | not_evaluated | (298.15, 9.1) | not_evaluated | not_evaluated | 0 |
| EPSV04-R243 | not_evaluated | (298.15, 13) | not_evaluated | not_evaluated | 0 |
| EPSV04-R244 | C17 | (298.15, 21.6) | not_evaluated | not_evaluated | 0 |
| EPSV04-R245 | C06 | (296.15, 78.4) | not_evaluated | not_evaluated | 0 |
| EPSV04-R246 | not_evaluated | (298.15, 36) | not_evaluated | not_evaluated | 0 |
| EPSV04-R247 | C18 | (333.15, 56.09) | not_evaluated | not_evaluated | 0 |
| EPSV04-R248 | not_evaluated | (298.15, 36.9) | not_evaluated | not_evaluated | 0 |

这些 (T, ε) 组合**从未在同一次测量中出现过**。它们不得被当作实验记录配对使用, 也不得据此构造原始候选行。

## 5. 来源可追溯性 (gap 丢失了哪些贡献来源)

| 测量 | A18 | gap 声明 | 实际贡献来源 | 丢失 |
|---|---|---|---|---|
| EPSV04-R003 | not_evaluated | `10.1016/j.tca.2012.05.036` | 3 个 | `10.1016/j.tca.2012.10.024;10.1021/je060248p` |
| EPSV04-R006 | not_evaluated | `10.1016/j.fluid.2013.12.014` | 5 个 | `10.1016/j.jct.2011.10.028;10.1016/j.tca.2013.05.022;10.1021/je060248p;10.1021/je800593p` |
| EPSV04-R007 | not_evaluated | `10.1021/acs.jced.8b00755` | 2 个 | `10.1021/je200682t` |
| EPSV04-R010 | not_evaluated | `10.1016/j.fluid.2013.12.014` | 4 个 | `10.1021/je3007666;10.1021/je800593p;10.1021/je900503p` |
| EPSV04-R016 | not_evaluated | `10.1016/j.tca.2012.10.004` | 2 个 | `10.1021/je600515j` |
| EPSV04-R021 | not_evaluated | `10.1016/j.fluid.2008.01.024` | 3 个 | `10.1016/j.fluid.2009.07.009;10.1021/je9002515` |
| EPSV04-R031 | C15 | `10.1016/j.fluid.2013.12.014` | 4 个 | `10.1016/j.tca.2017.03.018;10.1021/je400149j;10.1021/je9010773` |
| EPSV04-R036 | not_evaluated | `10.1021/acs.jced.8b00755` | 2 个 | `10.1021/je200682t` |
| EPSV04-R040 | not_evaluated | `10.1021/acs.jced.8b00755` | 2 个 | `10.1021/je060248p` |
| EPSV04-R041 | not_evaluated | `10.1016/j.fluid.2013.12.014` | 4 个 | `10.1016/j.jct.2011.10.028;10.1016/j.tca.2013.05.022;10.1021/je800593p` |
| EPSV04-R044 | not_evaluated | `10.1016/j.fluid.2009.07.009` | 7 个 | `10.1016/j.fluid.2013.12.014;10.1016/j.jct.2012.08.009;10.1016/j.tca.2013.05.022;10.1021/acs.jced.8b00755;10.1021/je060248p;10.1021/je800593p` |
| EPSV04-R046 | not_evaluated | `10.1016/j.fluid.2013.12.014` | 6 个 | `10.1021/acs.jced.8b00755;10.1021/je060248p;10.1021/je3007666;10.1021/je800593p;10.1021/je900503p` |
| EPSV04-R057 | not_evaluated | `10.1016/j.fluid.2013.12.014` | 5 个 | `10.1016/j.jct.2012.08.009;10.1016/j.tca.2013.05.022;10.1021/je060248p;10.1021/je800593p` |
| EPSV04-R059 | not_evaluated | `10.1016/j.fluid.2008.01.024` | 2 个 | `10.1016/j.fluid.2009.07.009` |
| EPSV04-R064 | not_evaluated | `10.1016/j.jct.2008.09.006` | 2 个 | `10.1016/j.jct.2010.09.008` |
| EPSV04-R068 | not_evaluated | `10.1016/j.tca.2012.05.036` | 2 个 | `10.1016/j.tca.2012.10.024` |
| EPSV04-R071 | not_evaluated | `10.1016/j.fluid.2008.01.024` | 2 个 | `10.1016/j.fluid.2009.07.009` |
| EPSV04-R082 | not_evaluated | `10.1016/j.jct.2012.04.011` | 2 个 | `10.1021/acs.jced.8b00755` |
| EPSV04-R083 | not_evaluated | `10.1016/j.fluid.2014.05.006` | 3 个 | `10.1016/j.jct.2012.08.009;10.1021/je400149j` |
| EPSV04-R085 | C08 | `10.1016/j.jct.2008.09.006` | 2 个 | `10.1016/j.jct.2010.09.008` |
| EPSV04-R089 | not_evaluated | `10.1016/j.jct.2008.02.015` | 2 个 | `10.1016/j.jct.2010.09.008` |
| EPSV04-R091 | not_evaluated | `10.1016/j.jct.2012.04.011` | 2 个 | `10.1021/je7006692` |
| EPSV04-R093 | not_evaluated | `10.1016/j.fluid.2008.01.024` | 2 个 | `10.1016/j.fluid.2009.07.009` |
| EPSV04-R095 | not_evaluated | `10.1016/j.fluid.2008.01.024` | 3 个 | `10.1016/j.fluid.2009.07.009;10.1021/je9010773` |
| EPSV04-R097 | not_evaluated | `10.1021/acs.jced.8b00755` | 2 个 | `10.1021/je060248p` |
| EPSV04-R099 | C10 | `10.1016/j.jct.2010.09.008` | 2 个 | `10.1016/j.tca.2012.10.024` |
| EPSV04-R100 | not_evaluated | `10.1021/je3007666` | 2 个 | `10.1021/je800593p` |

来源从**实际贡献观测**重建, 不从聚合结果反推; 也不因为 gap 只写了第一个 DOI 就丢掉其余来源。

## 6. 查找可行性

| 指标 | 值 |
|---|---:|
| 测量行数 | 248 |
| 单键能查到东西 | 100 |
| 单键能覆盖全部来源 | 73 |
| 多来源聚合行 | 27 |
| 合成条件对行 | 170 |

**关键区分**: 「单键能查到一条观测」与「单键能覆盖全部贡献来源」是两件事。多来源聚合行即便单键命中, 也只覆盖其中一个来源, 不构成完整可追溯。

## 7. 冻结输入

| 输入 | bytes | sha256 |
|---|---:|---|
| `a_core_set` | 3149 | `630b0ee8c09dc414` |
| `admission_gap` | 50040 | `597efaf8355483a9` |
| `build_dataset` | 21109 | `34bea41bdc08b99d` |
| `candidate_master` | 72349 | `63b9ff45561c9a49` |
| `dielectric_v04` | 134460 | `e046a3831630e36a` |
| `observations_v11plus` | 921601 | `159b928f800a5596` |
| `r219_audit` | 5468 | `333a209f47d59fea` |
| `target_protocol` | 13420 | `0e848eb6fd8619f8` |

## 8. 对 B02 的前置门作用

| 情况 | 允许 | 禁止 |
|---|---|---|
| 裁决通过 (`RAW_SINGLE_OBSERVATION` / `SINGLE_SOURCE_AGGREGATE`) | 可进入来源回填与原始测量回溯 | — |
| 多来源聚合 (`MULTI_SOURCE_AGGREGATE`) | — | 用单个 DOI 代表多个来源; 必须先拆分 |
| 记录不全或规则不明 (`PROVENANCE_INCOMPLETE` / `AGGREGATION_UNDOCUMENTED`) | — | 用聚合值构造原始候选行; 保留 HOLD |
| 合成条件对 (`COMPOSITE_CONDITION_UNMATCHED`) | — | 把 (T, ε) 当同一次实验配对 |

零观测分子的原始文献检索不受本门限制, 可并行进行。

