# Benchmark Tables

## Main benchmark: 10x5 repeated cross-validation (v0.3.2, 237 compounds)

| Representation | Target | R2 | MAE | Spearman | AUC (eps > 30) | MAE (eps < 20) |
|---|---|---|---|---|---|---|
| Dummy (mean) | raw | 0.000 | 21.66 | — | 0.500 | 4.85 |
| Morgan (ECFP4) | raw | 0.223 | 8.22 | 0.689 | 0.826 | 4.74 |
| Physical (13-dim) | raw | 0.354 | 7.50 | 0.801 | 0.937 | 4.53 |
| Morgan+Physical | raw | **0.366** | **7.13** | **0.814** | 0.929 | 4.22 |
| Morgan | log(eps-1) | 0.192 | 7.66 | 0.767 | 0.851 | 3.24 |
| Physical | log(eps-1) | 0.338 | 6.53 | **0.883** | 0.931 | 2.68 |
| Morgan+Physical | log(eps-1) | 0.315 | 6.54 | 0.881 | 0.931 | 2.58 |

The equal-weight Morgan+Physical hybrid on the raw target is the v0.3.2 candidate model.
It is selected for its consistent rank across all metrics, not for a single
best score. The log(eps-1) target improves the Physical representation but does
not transfer to the hybrid.

## Neural baselines (same 10x5 folds)

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
Chemprop D-MPNN R2 (0.237) exceeds Morgan XGBoost (0.190) but its Spearman
(0.665) is lower than both Morgan (0.697) and Physical (0.803), reinforcing
that graph representations carry fingerprint-level information while physical
features drive ranking quality.

## Extrapolation: scaffold/cluster holdout

| Representation | Target | R2 | MAE | Spearman |
|---|---|---|---|---|
| Morgan | raw | 0.119 +/- 0.017 | 8.618 +/- 0.478 | 0.614 +/- 0.031 |
| Physical | raw | 0.219 +/- 0.012 | 7.436 +/- 0.419 | 0.771 +/- 0.023 |
| Morgan+Physical | raw | 0.229 +/- 0.014 | 7.216 +/- 0.473 | 0.766 +/- 0.024 |
| Physical | log(eps-1) | **0.267 +/- 0.014** | **6.718 +/- 0.316** | **0.802 +/- 0.020** |

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
Panel A: Cumulative compound count from v0.1 (45) through v0.2 (210) to v0.3
(243), annotated by source type (ThermoML, NBS Circular 514, open-access
review tables, primary literature).
Panel B: Source-type proportions in the final v0.3 table.

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
Prediction reliability (absolute error) as a function of HBD count and
predicted permittivity, with the outside_associated_liquid region marked.

**Figure 8. Cross-source agreement.**
Scatter plot of NBS Circular 514 values vs. ThermoML values for overlapping
compounds, with median absolute deviation annotated. Conflict compounds
(FEC, TEP, TMP, VC) are highlighted as excluded points.
