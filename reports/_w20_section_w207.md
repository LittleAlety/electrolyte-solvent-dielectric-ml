## 28.63 标签来源分层与逐通道 sidecar：封闭 role 词汇表与 11 行来源表（2026-09-28）
|
**定位**：本件是 Week 20 lane W20-7（§28.63）的落地章，把散落在冻结图层表里的 role / provenance 列统一成**一张 11 行 sidecar**，不造新科学。全文见 `reports/w20_label_provenance.md`，sidecar 见 `probes/artifacts/w20_label_provenance_sidecar.csv`。|
**纪律**：`produces_reading = false`、`shot_number_taken = null`、`scoreboard_attempts_delta = 0`、`reaxys_values_used = 0`、`promoted = false`；主记分牌累计 11 次不变。|
**① 封闭 role 词汇表**：`primary_reference` / `calibrated_estimate` / `reference_only` / `feature_only`；既有拼写 `paired_anchor`、`uncalibrated_reference` 走显式别名映射，未登记拼写直接报错。|
**② sidecar 字段**：`channel / role / reference_level / calibration_id / source_doi / locator_table_figure / access_class`（与立项章 7 字段逐字对应），另加行键 `source_layer` 与覆盖数 `n_rows`。|
**③ 逐通道行数（图层口径）**：density **182,154**、dielectric **248**、liquid_window **314**、orbitals **35,714**、redox_label **392**、viscosity **42,941**；sidecar 共 **11** 行。|
**④ 隔离声明（永不可混）**：通道标签必须**同源同水平**；跨水平值须先标定并登记 `calibration_id`；标定不过门则该列整列留空、只作 `reference_only`；**ML 预测值永不入池**；**受限许可值（noncommercial）永不入池**。注册表有值格口径（`34,131` 键）与图层行口径（`261,763` 行）**不得混说**。|
**⑤ 性质**：本件不产读数、不占 shot、不引 Reaxys；role 统计 `primary_reference` 255,254 / `calibrated_estimate` 1,250 / `reference_only` 5,259 / `feature_only` 0 行（词汇在册、当前无行，照实登记）。|
|
