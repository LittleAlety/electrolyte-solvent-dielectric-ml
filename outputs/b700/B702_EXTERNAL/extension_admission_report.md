# 外部电解质溶剂扩展集 B_EXT_ELECTROLYTE_SOLVENTS_V1

- 候选溶剂: 8
- 准入: 8
- 其中多来源: 4，单来源: 4
- 原始待审记录: 321，准入记录: 270

## 准入条件

- **C1_identity**: InChIKey 必须等于登记值(名称差异不用于准入)
- **C2_phase**: phase 必须为 liquid
- **C3_static**: frequency_mhz 为空或 0; 频率限定值一律拒绝
- **C4_temperature**: t_k 必须存在; 缺失者保留在账本并标记, 不做温度折算
- **C5_value**: epsilon 必须存在且 > 1

## 结果

| 溶剂 | 准入 | 来源数 | eps 均值 | eps 范围 | T 范围 (K) |
|---|---|---:|---:|---|---|
| water | 是 | 2 | 77.074 | 67.07–87.0 | 273.15–333.15 |
| dimethyl sulfoxide | 是 | 2 | 44.986 | 42.0–50.58 | 283.15–333.15 |
| N,N-dimethylformamide | 是 | 2 | 36.872 | 32.434–41.274 | 277.72–328.09 |
| tetrahydrofuran | 是 | 1 | 7.501 | 7.4–7.58 | 295.15–298.15 |
| gamma-butyrolactone | 是 | 2 | 41.135 | 39.0–42.81 | 293.15–313.15 |
| ethylene carbonate | 是 | 1 | 89.0 | 89.0–89.0 | 298.15–298.15 |
| propylene carbonate | 是 | 1 | 64.0 | 64.0–64.0 | 298.15–298.15 |
| sulfolane | 是 | 1 | 42.5 | 40.4–44.5 | 293.15–328.15 |

## 缺失证据

- **tetrahydrofuran** — SINGLE_SOURCE_ONLY: only 1 source(s) supply a qualifying measurement
- **ethylene carbonate** — SINGLE_SOURCE_ONLY: only 1 source(s) supply a qualifying measurement
- **propylene carbonate** — SINGLE_SOURCE_ONLY: only 1 source(s) supply a qualifying measurement
- **sulfolane** — SINGLE_SOURCE_ONLY: only 1 source(s) supply a qualifying measurement

## 声明

- 未新增任何虚构测量；所有准入行都有 source_url 与 source_sha256
- 未做温度折算：不在室温窗口的记录只被标记，未被调整
- 未混用频率：frequency_mhz > 0 的记录一律拒绝
- 单来源溶剂不得被表述为已获独立验证
