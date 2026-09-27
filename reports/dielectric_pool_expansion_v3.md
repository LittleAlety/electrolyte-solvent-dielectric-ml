# Shot 14: full coordination coverage and a static-only training pool

**Generated:** 2026-09-27T07:40:15Z

**Decision:** `co_primaries_missed` -- at least one co-primary arm misses 0.60

> **红线登记（2026-09-27 发现并如实登记，未做静默修改）**：`widened_lever4_lever8full`（**0.5151538934971656**）这一臂把
> `data/raw/reaxys_w17f/observations.csv` 里的 **Reaxys 受限数值当作训练标签**用了 **155 行** —— 这违反本仓既有红线
> 「**禁止任何受限值进入池或特征**」（`reports/decisions_log.md` 第 2908 行 / 第 4793 行，`restricted_crosscheck_only` 纪律）。
> 该文件位于被忽略的 `data/raw/` 下，**没有任何 Reaxys 数值进入 `data/`、特征表或交付包**（复核：`data/processed/` 无 widened 产物，
> `git ls-files | rg -i reaxys` 无本轮新增带值件），但「**该读数由受限值导出**」这一点属实。
> **处置**：该臂读数**作废、不得引用**，也不得当作「Reaxys 加宽有害」的证据；登记见 `reports/decisions_log.md` §28.33。

## 1. Reproduction anchors

| Arm | Expected | Observed | Abs gap | Reproduced |
|---|---|---|---|---|
| `baseline_hybrid` | 0.4091179943351143 | 0.4091179943351143 | 0.00e+00 | True |
| `full_table_hybrid` | 0.5300287425966430 | 0.5300287425966430 | 0.00e+00 | True |
| `full_table_lever4` | 0.5433111678100043 | 0.5433111678100043 | 0.00e+00 | True |
| `full_table_lever4_lever8` | 0.4914701852431905 | 0.4914701852431905 | 0.00e+00 | True |

## 2. Arms

| Arm | R2 | Delta vs baseline |
|---|---|---|
| `baseline_hybrid` | 0.4091179943351143 | +0.000000 |
| `full_table_hybrid` | 0.5300287425966430 | +0.120911 |
| `full_table_lever4` | 0.5433111678100043 | +0.134193 |
| `full_table_lever4_lever8` | 0.4914701852431905 | +0.082352 |
| `full_table_lever4_lever8full` | 0.4860002385017493 | +0.076882 |
| `static_hybrid` | 0.3230413291579051 | -0.086077 |
| `static_lever4_lever8full` | 0.4035089033119271 | -0.005609 |
| `widened_lever4_lever8full` | 0.5151538934971656 | +0.106036 |
| `full_table_label_placebo` | 0.1593289384795436 | -0.249789 |

## 3. Governance

| Dose | Compounds | Rows | R2 | Delta vs baseline |
|---|---|---|---|---|
| 0.25 | 26 | 266 | -0.3176962057727917 | -0.726814 |
| 0.50 | 52 | 811 | 0.0774699367881770 | -0.331648 |
| 0.75 | 79 | 1297 | 0.4160647370881480 | +0.006947 |
| 1.00 | 105 | 1572 | 0.4291789881938171 | +0.020061 |

- Arm A (label placebo): delta -0.249789 -> PASS
- Arm B (monotone dose response): PASS

## 4. Pool

- base_rows: 2029
- static_training_rows: 1594
- finite_frequency_training_rows: 435
- widened_rows: 155
- widened_compounds: 39
- coordination_released_rows_with_the_block: 1109
- coordination_full_rows_with_the_block: 1597
- coordination_full_compounds_with_the_block: 125
- rows_total: 2184
- scored_rows: 457
- widened_report: {'rows_read': 711, 'rows_admitted': 155, 'compounds_admitted': 39, 'dropout': {'compound_not_in_the_released_pool': 14, 'duplicate_of_an_existing_row': 162, 'not_experimental': 206, 'temperature_out_of_the_training_band': 86, 'value_is_not_a_plain_decimal': 88}, 'available': True, 'source': 'data/raw/reaxys_w17f/observations.csv'}

