# Week 8 Report: analysis freeze and the benchmark that survived the gate

**Date:** 2026-09-24
**Commit:** `060e9d7`
**Fitted set:** 236 rows (frozen)
**Status:** analysis frozen for the v1.0 candidate; the `v1.0` tag is still
withheld pending the open provenance conflicts.

## Outcome

Week 8 was supposed to freeze a benchmark. It instead **found that the previous
benchmark was wrong** and re-derived it. Two things happened:

1. The `model_ready` flag was still decorative in the modelling path:
   `read_modelling_rows` honoured the curated exclusion list and the
   physical-feature status column, but never the flag itself, so vinylene
   carbonate (`model_ready=false`, `conflict_open`) was being fitted in every
   revision up to v0.3.3.
2. Once the gate was enforced, the headline claim that adding PC/EC improved the
   model collapsed from +0.0265 to +0.0059 (p = 0.11) - the earlier gain was
   carried by that one withheld row.

Both corrections are now enforced by tests and by the paper-consistency
checker, so neither can silently return.

## The frozen benchmark (236 fitted rows, 10x5 repeated CV)

| Representation | Target | R2 | MAE | Spearman | AUC (eps > 30) | MAE (eps < 20) |
| --- | --- | --- | --- | --- | --- | --- |
| Constant (train-fold mean) | raw | -0.012 | 11.75 | - | - | 7.84 |
| Morgan (ECFP4) | raw | 0.240 | 7.61 | 0.722 | 0.837 | 4.38 |
| Physical (13-dim) | raw | 0.342 | 7.10 | 0.802 | 0.937 | 4.33 |
| **Morgan+Physical** | **raw** | **0.364** | **6.69** | **0.828** | 0.933 | 3.95 |
| Morgan | log(eps-1) | 0.187 | 7.32 | 0.766 | 0.845 | 3.20 |
| Physical | log(eps-1) | 0.290 | 6.37 | 0.880 | 0.926 | 2.70 |
| Morgan+Physical | log(eps-1) | 0.293 | 6.27 | 0.878 | 0.927 | 2.55 |

Source: the raw rows come from `probes/v032_ablation_summary.json`; the
`log(eps-1)` rows come from `probes/v032_target_scaffold_summary.json`
(`random_repeated_kfold`). The constant row is a fold-matched predictor
recomputed from `data/processed/v032_ablation_predictions.csv`; it has no
ranking signal, so its Spearman and AUC are undefined rather than 0.5.

## Row accounting (the invariant that makes the table auditable)

| Lineage | Source | Fitted | Curated exclusions | Feature failures | Withheld (`model_ready=false`) |
| --- | --- | --- | --- | --- | --- |
| v0.3.2 | 245 | 236 | 4 | 4 | 1 |
| v0.3.3 | 246 | 236 | 5 | 4 | 1 |

Withheld: vinylene carbonate. The fifth v0.3.3 exclusion is
3-methoxypropionitrile, previously out only because it had no feature row.
After the gate the v0.3.2 and v0.3.3 lineages fit the **same** 236 rows and
return identical metrics, so the row-wise "coverage gain" that earlier drafts
reported between them was fold churn plus the ungated row.

## Controlled PC/EC comparison (train-only append, paired per repeat)

| Representation | Baseline R2 | + PC/EC | Paired delta | 95% CI | p |
| --- | --- | --- | --- | --- | --- |
| Morgan | 0.2203 | 0.2191 | -0.0012 | [-0.006, +0.003] | 0.59 |
| Physical | 0.3201 | 0.3194 | -0.0007 | [-0.016, +0.014] | 0.92 |
| Morgan+Physical | 0.3456 | 0.3515 | **+0.0059** | [-0.002, +0.013] | 0.11 |

Honest reading: PC and EC broaden coverage and are now in the dataset, but they
deliver **no measurable accuracy gain** on the v0.3 compounds. Both arms score
the identical held-out compounds in identical frozen folds; fold churn between
the two dataset splits is 1224 of 2340 compound x repeat assignments (52.3%).

## Extrapolation: scaffold/cluster holdout (236 rows)

| Representation | Target | R2 | MAE | Spearman |
| --- | --- | --- | --- | --- |
| Morgan | raw | 0.138 +/- 0.014 | 9.097 +/- 0.239 | 0.597 +/- 0.014 |
| Physical | raw | 0.268 +/- 0.051 | 8.082 +/- 0.317 | 0.747 +/- 0.016 |
| Morgan+Physical | raw | 0.295 +/- 0.027 | 7.806 +/- 0.105 | 0.756 +/- 0.017 |
| **Physical** | **log(eps-1)** | **0.276 +/- 0.044** | **6.669 +/- 0.218** | **0.862 +/- 0.016** |
| Morgan+Physical | log(eps-1) | 0.261 +/- 0.029 | 6.885 +/- 0.129 | 0.838 +/- 0.015 |

Physical features are the best representation under structure-based holdout, as
in the random split: the ranking signal is physical, the fingerprint only helps
inside the random-CV regime.

## Neural line (N2) closed for v1.0

| Model | R2 | MAE | Spearman | AUC (eps > 30) |
| --- | --- | --- | --- | --- |
| MLP-Morgan | -0.447 | 12.81 | 0.170 | 0.563 |
| MLP-Physical | -0.172 | 7.43 | **0.884** | 0.940 |
| MLP-Hybrid | -0.458 | 12.89 | 0.228 | 0.646 |
| MLP-Physical (calibrated) | -0.309 | 7.81 | 0.865 | 0.937 |
| Chemprop D-MPNN | 0.237 | 7.89 | 0.665 | - |

The calibrated MLP is a **true negative result**: the pre-registered
slope/intercept calibration is fitted inside each training fold and still leaves
R2 negative, so the failure is not a scale offset. Neural rows stay on the
205-row v0.2 table and are not recomputed on the 236-row folds; deeper
architectures move to future work (N3/N4).

## Paper artifacts

The five section files are the single source of truth for
`paper/full_draft.md`, and `scripts/check_paper_artifact_consistency.py`
re-derives, from the committed artifacts: row counts, conflict counts, the main
benchmark table, the scaffold table, the per-version coverage table, the
fitted-row count, the controlled PC/EC delta and its CI, the release version and
the generated draft. Superseded number strings fail the build.

## Verification

| Command | Result |
| --- | --- |
| `pytest -q -p no:cacheprovider` | `509 passed` at commit `060e9d7` (historical; later revisions raise the suite) |
| `ruff check scripts src probes tests` | All checks passed |
| `scripts/check_paper_artifact_consistency.py` | paper drafts agree with the frozen artifacts |
| `scripts/verify_dielectric_representation_ablation.py` | all fold, repeat and summary metrics recomputed |
| `scripts/verify_dielectric_target_scaffold.py` | scaffold balance and input hash verified |
| `scripts/verify_dielectric_v03.py` | 7/7 checks, 246 rows; the dataset digest is `a446c216874538d900e9f3ebbf18178926b812b77a213a395f4ff8cddfc01085` (v0.3.11 was `765fd8e0...646b60`; v0.3.12 was `1b285fe8...22456`; re-pinned by the v0.3.13 FEC metadata revision and its downstream 40 C temperature-attribution addendum; no benchmark row moved) |
| `scripts/verify_dielectric_v032.py` | 7/7 checks, 245 rows |

## What is not frozen

- Vinylene carbonate is withheld from every fit and its primary 126 +/- 1.0
  measurement (Saadi & Lee 1966, Table 2) landed in v0.3.12; the competing
  Knovel 78-127 interval is unresolved, so the paper must keep saying that the
  row is `model_ready=false` with
  `conflict_status=knovel_78_127_interval_contains_primary_value`.
- FEC stays excluded. The stored 102 was shown to be the flash point in
  v0.3.11, and v0.3.12 promoted the 78.4 primary measurement (Kobayashi et al.
  2003, Table 2, 296.15 K) to the stored value. The competing 107 compilation
  value is now read in Ue et al. 2014 Table 2.3 (printed p.101), which attributes
  the FEC data to Hagiyama 2008 [25]; only Hagiyama 2008's primary measurement
  remains unread.
- The dataset is still a **candidate**: `model_ready` is a protected field and
  the release line says so.

## Evidence files

- `probes/v032_ablation_summary.json`, `probes/v032_target_scaffold_summary.json`
- `probes/v032_controlled_comparison_summary.json`
- `probes/dielectric_v03_representation_ablation_summary.json`
- `probes/dielectric_mlp_calibration_summary.json`
- `reports/v034_model_ready_gate.md`
- `paper/full_draft.md` and the section files

> **Re-pinned for v0.3.14 (2026-09-25).** The current canonical digest of
> `data/dielectric_v03.csv` is
> `ff2142936e06e04b329b70f8597574f75349e54ce876e9fff81309e6d35ccce4`.
> The v0.3.14/D2 scope relabel added the `out_of_scope_ionic_or_organometallic`
> gate flag plus a scope note to the four rows whose xTB feature generation
> failed. It changed no numeric value, temperature, `model_ready` flag or
> `conflict_status`; the 246 rows x 38 columns, the 240 `model_ready=true` rows
> and the 236-row frozen benchmark are byte-identical. Every earlier hash quoted
> above remains the historical pin of its own revision and is deliberately not
> rewritten.
