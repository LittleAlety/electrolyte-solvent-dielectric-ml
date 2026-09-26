# Lever 8 - the Li+ coordination block on the frozen dielectric scoreboard

- generated: `2026-09-26T03:57:03Z`
- pre-registration: `probes/dielectric_coordination_block_prereg.json` (sha256 `5aa2e3483c7fae52144dc4e7a524d46138d2c85d714e748e8d59de2787613629`)
- decision: **dead** (appending the five Li+-coordination columns moves grouped Morgan+Physical R2 by +0.0441 on the frozen 457-row / 97-compound scoreboard (0.4091 -> 0.4532); decision: dead)

## The block

Columns appended beside the 13 frozen physical columns; no frozen column is touched:

- `li_binding_energy_ev`
- `li_binding_distance_a`
- `q_max_h`
- `q_min_hetero`
- `esp_imbalance`

- compounds with a usable block: 88 / 97
- observation rows in the long feature table: 2029, of which 987 carry a usable block
- xTB wall clock 0.0 s against a 2700 s ceiling (within budget: True); cpu 748.2 s
- Li+ reference energy: 0.1659637 Eh (from the reused table)
- the wall clock above is the cost inside this run; when the feature table is reused it is 0.0 s and the measured cost is the sum of the per-compound `xtb_seconds` column of the feature table
- pilot scale: no bounded pilot was needed. The whole pool of 97 compounds was attempted and 88 produced a block
- pending list: empty. The compounds without a block carry the status `undefined_no_hetero_site` (no O and no N for the pre-registered site rule), which is an undefined block and not an unrun one
- compounds without the block: BKIMMITUMNQMOS-UHFFFAOYSA-N, FYIRUPZTYPILDH-UHFFFAOYSA-N, IMNFDUFMRHMDMM-UHFFFAOYSA-N, TVMXDCGIABBOFY-UHFFFAOYSA-N, UAEPNZWRGJTJPN-UHFFFAOYSA-N, WZLFPVPRZGTCKP-UHFFFAOYSA-N, XDTMQSROBMDMFD-UHFFFAOYSA-N, YFMFNYKEUDLDTL-UHFFFAOYSA-N, YXFVVABEGXRONW-UHFFFAOYSA-N

## Scoreboard

- scored rows 457, compounds 97, folds 50, repeats 10
- straddling compounds across a fold boundary: 0

## Arms (Morgan+Physical blend)

| arm | R2 | MAE | Spearman | MAE >60 |
| --- | --- | --- | --- | --- |
| `baseline` | 0.4091 | 8.0407 | 0.7763 | 55.7131 |
| `plus_coordination_block` | 0.4532 | 7.9176 | 0.7869 | 51.0224 |
| `placebo_shuffled_target` | -0.0408 | 13.6127 | -0.0166 | 68.4971 |

## Paired deltas (plus_coordination_block - baseline)

| metric | delta |
| --- | --- |
| r2 | +0.0441 |
| mae | -0.1231 |
| rmse | -0.5172 |
| spearman | +0.0106 |
| mae_lt20 | -0.2721 |
| mae_20_60 | +0.4886 |
| mae_gt60 | -4.6907 |

- baseline reproduction: 0.4091179943351143 vs published 0.4091179943351143 (abs delta 0.00e+00)
- placebo arm: R2 -0.0408, delta -0.4500, collapsed: False

## Verdict

- pass bar: delta R2 >= +0.0200 -> met: True
- kill line: delta R2 < +0.0050
- mae_gt60 not worse: True
- kill reason: the placebo arm moved R2 by -0.4500, beyond +-0.0200
- decision: **dead**

### Placebo reading (disclosure; no threshold was changed after the run)

- the pre-registration's secondary criterion is `|delta R2| <= 0.0200` on the placebo arm. Read literally against the baseline arm that inequality can only hold when the placebo keeps the baseline signal, so it is unsatisfiable whenever the placebo behaves as a placebo. It was implemented literally, and that clause is what kills the arm
- the placebo's own R2 is -0.0408 against a baseline of +0.4091: no lift over a trivial predictor, i.e. the shuffling did destroy the signal, which is what the arm exists to demonstrate
- the pass criterion itself was met (delta R2 +0.0441 >= +0.0200) and the mae_gt60 stratum improved, so the recorded verdict is `dead` on the placebo clause alone

## Honest boundaries

- target mismatch: the review describes solvating power inside an electrolyte, this scoreboard predicts the static dielectric constant of a pure solvent. The block tests which of the review's axes transfers to a different target.
- GFN2-xTB overbinds Li+; only the spread of the binding energy across compounds is used, never its absolute value as thermochemistry.
- the Li+ complex is gas phase and single molecule: no anion, no solvent-solvent competition, which is the review's own stated weakness of the binding-energy descriptor.
- the three charge columns come from the frozen week-3 xTB run of the isolated solvent, matched by total energy, so they describe the released geometry and not the Li+-perturbed one.
- compounds with no O and no N (hydrocarbons, hydrofluoroalkanes) have no site for the pre-registered rule, so their block is undefined and left missing rather than filled; they are counted by status in the summary.
- the released v03 `total_energy_hartree` column is the first `:: total energy` line of the run log, i.e. the single point at the input geometry, because the frozen parser uses the first regex match; this block therefore takes the relaxed energy from the same cached run and reports both columns so the difference is auditable.
- no network I/O, no new data source, no change to the frozen scoreboard, the fold numbers or any frozen red-line digest.

## Shots

- main-scoreboard attempts in this probe: 1
- policy: attempts at the main scoreboard are counted in reports/decisions_log.md section 12

## Files

- feature_table: `probes/artifacts/dielectric_coordination_block_features.csv`
- folds: `probes/artifacts/dielectric_coordination_block_folds.csv`
- predictions: `probes/artifacts/dielectric_coordination_block_predictions.csv`
- repeats: `probes/artifacts/dielectric_coordination_block_repeats.csv`
- report: `reports/dielectric_coordination_block.md`
- summary: `probes/dielectric_coordination_block_summary.json`

