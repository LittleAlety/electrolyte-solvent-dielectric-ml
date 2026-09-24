# Benchmark Tables

## Main benchmark: 10x5 repeated cross-validation (v0.3.2 benchmark, 236 fitted rows)

| Representation | Target | R2 | MAE | Spearman | AUC (eps > 30) | MAE (eps < 20) |
|---|---|---|---|---|---|---|
| Constant (train-fold mean) | raw | -0.013 | 11.97 | — | — | 8.30 |
| Morgan (ECFP4) | raw | 0.240 | 7.61 | 0.722 | 0.837 | 4.38 |
| Physical (13-dim) | raw | 0.342 | 7.10 | 0.802 | 0.937 | 4.33 |
| Morgan+Physical | raw | **0.364** | **6.69** | **0.828** | 0.933 | 3.95 |
| Morgan | log(eps-1) | 0.187 | 7.32 | 0.766 | 0.845 | 3.20 |
| Physical | log(eps-1) | 0.290 | 6.37 | 0.880 | 0.926 | 2.70 |
| Morgan+Physical | log(eps-1) | 0.293 | 6.27 | 0.878 | 0.927 | 2.55 |

The reference row is a constant predictor set to the training-fold mean on the
same 10x5 folds, recomputed from `data/processed/v032_ablation_predictions.csv`.
The 236 fitted rows are the 241 featurized v0.3.2 rows minus four xTB failures
and minus vinylene carbonate, which the dataset flags `model_ready=false`;
`read_modelling_rows` withholds it and reports it separately.
It replaces an earlier `Dummy (mean)` row whose 21.66 MAE could not be
reproduced from any committed artifact. A constant predictor has no ranking
signal, so its Spearman and AUC are undefined rather than 0.5.

The equal-weight Morgan+Physical hybrid on the raw target is the v0.3.2
candidate model. It is selected for its consistent rank across all metrics, not
for a single best score. The log(eps-1) target improves the Physical
representation but does not transfer to the hybrid.

## Neural baselines (205-row v0.2 feature table, same 10x5 folds)

These rows were computed on `data/processed/dielectric_physical_features.csv`
(205 compounds, v0.2). They were **not** recomputed on the v0.3.2 236-row folds,
so they may only be compared against like-for-like 205-row XGBoost references.
They also predate the `model_ready` gate, which the 205-row v0.2 table never
triggers (no v0.2 compound is flagged).

| Model | R2 | MAE | Spearman | AUC (eps > 30) |
|---|---|---|---|---|
| MLP-Morgan | -0.447 | 12.81 | 0.170 | 0.563 |
| MLP-Physical | -0.172 | 7.43 | **0.884** | 0.940 |
| MLP-Hybrid | -0.458 | 12.89 | 0.228 | 0.646 |
| MLP-Physical (calibrated) | -0.309 | 7.81 | 0.865 | 0.937 |
| Chemprop D-MPNN | 0.237 | 7.89 | 0.665 | — |

MLP-Physical achieves the highest Spearman correlation across all models (0.884)
but with negative R2. A pre-registered linear calibration probe did not recover
positive R2, confirming this as a ranking-only representation ceiling.
Chemprop D-MPNN R2 (0.237) exceeds the like-for-like 205-row v0.2 Morgan
XGBoost baseline (0.203) but its Spearman (0.665) is lower than both Morgan
(0.697) and Physical (0.821) on that same 205-row table, reinforcing that graph
representations carry fingerprint-level information while physical features
drive ranking quality. The neural rows are retained as representation-ceiling
evidence on the v0.2 feature table; they were not recomputed on the v0.3.2
236-row fold set.

## Extrapolation: scaffold/cluster holdout (v0.3.2, 236 rows)

Source: `probes/v032_target_scaffold_summary.json` (ring Murcko scaffolds plus
acyclic ECFP4 clusters, five balanced partitions). These values supersede the
older 205-row scaffold table.

| Representation | Target | R2 | MAE | Spearman |
|---|---|---|---|---|
| Morgan | raw | 0.138 +/- 0.014 | 9.097 +/- 0.239 | 0.597 +/- 0.014 |
| Physical | raw | 0.268 +/- 0.051 | 8.082 +/- 0.317 | 0.747 +/- 0.016 |
| Morgan+Physical | raw | 0.295 +/- 0.027 | 7.806 +/- 0.105 | 0.756 +/- 0.017 |
| Morgan | log(eps-1) | 0.130 +/- 0.020 | 8.442 +/- 0.188 | 0.639 +/- 0.024 |
| **Physical** | **log(eps-1)** | **0.276 +/- 0.044** | **6.669 +/- 0.218** | **0.862 +/- 0.016** |
| Morgan+Physical | log(eps-1) | 0.261 +/- 0.029 | 6.885 +/- 0.129 | 0.838 +/- 0.015 |

Physical with log(eps-1) is the best representation for scaffold extrapolation,
confirming that physical descriptors generalize better to novel chemical
structures than fingerprint-based representations.

## Domain-gap external test: frozen v0.2 model on 29 new battery solvents

| Representation | R2 | Spearman |
|---|---|---|
| Morgan | 0.122 | 0.692 |
| RDKit Physical | 0.154 | 0.367 |
| Morgan+Physical (hybrid) | 0.286 | 0.590 |
| v0.2 CRV reference (hybrid) | 0.320 | 0.830 |

The external R2 of 0.286 (vs. 0.320 cross-validation) confirms that the v0.2
model partially generalizes to battery-relevant solvents. The systematic
underprediction of high-permittivity targets (GVL, NMP) directly visualizes
the domain gap that v0.3's expanded coverage aims to close.

# Figures

**Figure 1. Dataset growth and source composition.**
Panel A: Cumulative compound count from v0.1 (100) through v0.2 (210) and
v0.3 (243) to v0.3.3 (246), annotated by source type (ThermoML, NBS Circular
514, open-access review tables, primary literature).
Panel B: Source-type proportions in the final v0.3.3 table.

**Figure 2. Chemical space visualization.**
UMAP or t-SNE projection of Morgan fingerprints (radius 2, 2048 bits) with
compounds colored by dielectric constant magnitude and battery-solvent families
(carbonates, ethers, nitriles, phosphates, fluorinated compounds) highlighted.

**Figure 3. Model benchmark comparison.**
Grouped bar chart of R2, MAE, and Spearman across all representations (Morgan,
Physical, Hybrid) and targets (raw, log), with error bars showing +/- 1 std
across 10 repeats.

**Figure 4. Prediction error by dielectric stratum.**
Stratified MAE for low (eps < 20), medium (20-60), and high (eps > 60)
permittivity ranges, comparing Morgan, Physical, and Hybrid representations.

**Figure 5. Domain-gap parity plot.**
Frozen v0.2 model predictions vs. experimental values for 29 new battery
solvents. High-permittivity outliers (GVL, NMP) are labeled. This figure
directly visualizes the coverage improvement in v0.3.

**Figure 6. Scaffold/cluster holdout comparison.**
R2 under random CV vs. scaffold/cluster holdout for each representation,
demonstrating the extrapolation advantage of physical features.

**Figure 7. Applicability domain boundary.**
Absolute error split by applicability domain, with the
outside_associated_liquid region marked. The structural donor rule triggers on
2,070 of the 6,150 out-of-fold rows (33.66%).

**Figure 8. Cross-source agreement.**
Scatter plot of NBS Circular 514 values vs. ThermoML values for overlapping
compounds, with median absolute deviation annotated. The five withheld
compounds (FEC, TEP, TMP, ethyl isothiocyanate, 3-methoxypropionitrile) are
highlighted as excluded points, and vinylene carbonate, withheld by the
`model_ready` gate, is annotated separately.
