# Scientific Data Paper Skeleton

## Working title

An auditable machine-learning dataset of static dielectric constants for
liquid electrolyte solvents

## Abstract

State the dataset scope, public reproducibility, source mixing, cross-checks,
and the three explicit boundaries: representation ceiling, scaffold/cluster
holdout performance, and poor transfer to associated liquids.

## Background and Summary

- Battery electrolyte screening needs solvent permittivity inputs that are
  traceable and machine-readable.
- Existing public resources are fragmented across ThermoML, NBS Circular 514,
  historical compilations, and journal tables.
- The contribution is a curated dataset and benchmark, not a claim that a
  small-data model solves static permittivity prediction.

## Methods

### Dataset scope

- Main room-temperature window: 293.15-303.15 K.
- Pure-component, zero-frequency or explicitly documented static-equivalent
  observations.
- Structure standardization by RDKit and InChIKey.
- Gate flags for source type, frequency, phase, purity, and conflicts.

### Source construction

- v0.1: ThermoML zero-frequency pure observations.
- v0.2: NBS Circular 514 additions.
- v0.3: public literature and remaining eligible NBS additions.
- Restricted SpringerMaterials data are cross-check evidence only.

### Physical features

- GFN2-xTB dipole and polarizability.
- RDKit HBD/HBA, TPSA, molecular volume.
- Onsager-style `mu^2 / Vm`.
- Experimental-density variant retained as a negative robustness result.

### Models and validation

- XGBoost with fixed 10x5 RepeatedKFold.
- Morgan, Physical, and equal-weight Morgan+Physical representations.
- Raw and `log(epsilon - 1)` targets.
- Scaffold/cluster holdout for extrapolation.
- Small-data MLP and Chemprop D-MPNN baseline rows.

## Data Records

- `data/dielectric_v01.csv`
- `data/dielectric_v02.csv`
- `data/dielectric_v03.csv`
- `data/processed/modern_solvent_public_review_observations.csv`
- `data/processed/dielectric_physical_features_density.csv`
- `data/processed/dielectric_physical_features_v03.csv`
- `data/processed/dielectric_applicability_flags.csv`
- Source manifests, exclusion tables, and verification reports

## Technical Validation

- Chodera 2015 cross-check.
- SpringerMaterials restricted cross-check with median absolute delta `0.05`.
- Ethyl isothiocyanate conflict remains explicitly unresolved.
- Deterministic builders and independent verifiers.
- v0.3 model sensitivity: broader modern-solvent coverage without an accuracy
  gain (`R2 0.310` hybrid on 235 rows versus `0.320` on 205 v0.2 rows).
- Cross-platform CI over all committed artifacts.

## Benchmark Tables

### Main benchmark

Rows: Dummy, size-only, Morgan, Physical, Hybrid.

Columns: raw/log target, R2, MAE, Spearman, AUC>30, and high-permittivity
stratum MAE.

### Neural baselines

- MLP-Morgan
- MLP-Physical
- MLP-Hybrid
- Chemprop D-MPNN

### Extrapolation benchmark

- random CV versus scaffold/cluster holdout
- best representation for each target mode

## Applicability Domain

Predictions with `HBD >= 1` and predicted dielectric `> 60` are marked
`outside_associated_liquid`. The dataset paper should state that Kirkwood
correlation effects require multi-body descriptions outside the frozen model.

## Figures

1. Dataset growth and source composition from v0.1 to v1.0.
2. Chemical-space projection with electrolyte families highlighted.
3. Model benchmark and uncertainty across repeated folds.
4. Prediction error by dielectric stratum.
5. Applicability-domain boundary.
6. Cross-source agreement and conflict map.

## Limitations

- Small experimental dataset.
- Most additions are at a single near-room temperature.
- Conformer-averaged dipole moments are not implemented.
- Associated liquids remain outside the model boundary.
- Some modern-solvent targets still require public primary-source resolution.

## Code and Data Availability

List the GitHub repository, immutable release commit, Zenodo DOI, environment
versions, and commands for each verifier.
