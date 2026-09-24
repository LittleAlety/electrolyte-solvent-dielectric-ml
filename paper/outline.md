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
- `data/dielectric_v03.csv` (v0.3.3, 246 compounds, current)
- `data/dielectric_v031.csv` (243) and `data/dielectric_v032.csv` (245), historical
- `data/processed/dielectric_v03_exclusions.csv` (5-row curated exclusion list)
- `data/processed/dielectric_v03_provenance_patches.csv` (30 reproducible patches)
- `data/processed/modern_solvent_public_review_observations.csv`
- `data/processed/dielectric_physical_features_density.csv`
- `data/processed/dielectric_physical_features_v03.csv`
- `data/processed/dielectric_applicability_flags.csv`
- Source manifests, exclusion tables, and verification reports

## Technical Validation

- Chodera 2015 cross-check.
- SpringerMaterials restricted cross-check with median absolute delta `0.05`.
- Ethyl isothiocyanate conflict remains explicitly unresolved and is withheld.
- Vinylene carbonate is flagged `model_ready=false`; since v0.3.4 the modelling
  gate withholds it from every fit and the accounting reports it explicitly.
- Deterministic builders and independent verifiers.
- v0.3.2 model sensitivity: broader modern-solvent coverage without a
  controlled accuracy gain (`R2 0.364` hybrid on 236 fitted rows versus `0.320`
  on the 205-row v0.2 table). A paired train-only control attributes only
  `+0.0059` (95% CI `-0.002` to `+0.013`, p = 0.11) to the PC/EC addition; 1224
  of 2340 fold assignments (52.3%) also changed, so the raw version-to-version
  difference is not a controlled estimate.
- Cross-platform CI over all committed artifacts.

## Benchmark Tables

### Main benchmark

Rows: Constant (train-fold mean), size-only, Morgan, Physical, Hybrid.

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

Predictions for compounds with at least one hydrogen-bond donor site
(`[O,S,N;!H0]`, counted from the structure rather than from the model output)
are marked `outside_associated_liquid`; the rule triggers on 33.66% of
out-of-fold rows. The dataset paper should state that Kirkwood correlation
effects require multi-body descriptions outside the candidate model.

## Figures

1. Dataset growth and source composition from v0.1 to v0.3.3 (246 compounds).
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
- Some modern-solvent targets still require public primary-source resolution;
  3-methoxypropionitrile (secondary compilation) and fluoroethylene carbonate
  (competing 107 claim unread) are the two named open items.

## Code and Data Availability

List the GitHub repository, the candidate release commit (which becomes the
immutable v1.0 commit only after the Appendix I freeze conditions are met), the
Zenodo DOI, environment versions, and the command for each verifier. Do not
describe the release commit as immutable while the release is still a
candidate.
