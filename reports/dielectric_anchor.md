# Shot 15: a high-permittivity anchor block

**Generated:** 2026-09-27T07:52:10Z

**Decision:** `primary_missed` -- the anchor arm misses 0.60

## 1. Reproduction anchors

| Arm | Expected | Observed | Abs gap | Reproduced |
|---|---|---|---|---|
| `baseline_hybrid` | 0.4091179943351143 | 0.4091179943351143 | 0.00e+00 | True |
| `full_table_lever4` | 0.5433111678100043 | 0.5433111678100043 | 0.00e+00 | True |

## 2. Arms

| Arm | R2 | Delta vs baseline |
|---|---|---|
| `baseline_hybrid` | 0.4091179943351143 | +0.000000 |
| `full_table_lever4` | 0.5433111678100043 | +0.134193 |
| `anchors_hybrid` | 0.4980038916914576 | +0.088886 |
| `anchors_lever4` | 0.5102315058190110 | +0.101114 |
| `anchors_label_placebo` | 0.1657995057541687 | -0.243318 |

## 3. Governance

| Dose | Compounds | Rows | R2 | Delta vs baseline |
|---|---|---|---|---|
| 0.25 | 26 | 266 | -0.2271450598639756 | -0.636263 |
| 0.50 | 52 | 811 | 0.2401582841662447 | -0.168960 |
| 0.75 | 79 | 1297 | 0.4700765130683850 | +0.060959 |
| 1.00 | 105 | 1572 | 0.5239744338803091 | +0.114856 |

- Arm A (label placebo): delta -0.243318 -> PASS
- Arm B (monotone dose response): PASS

