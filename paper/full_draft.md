# Abstract

We present an auditable, machine-learning-ready dataset of static dielectric
constants (relative permittivities) for 243 pure organic liquids at near-room
temperature (293.15-303.15 K). The dataset is assembled from three sources:
the NIST ThermoML archive (v0.1, 45 compounds), NBS Circular 514 (v0.2, 210
compounds), and open-access review tables and primary literature covering
modern battery solvents (v0.3, 243 compounds). Every row carries deterministic
source provenance, gate-flag metadata, license and redistribution conditions,
and conflict status. Four compounds with unresolved public-source conflicts
are explicitly documented and excluded from model fitting. A companion
benchmark evaluates three representations (Morgan fingerprints, 13-dimensional
physical features from GFN2-xTB and RDKit, and their equal-weight hybrid)
under fixed 10x5 repeated cross-validation, scaffold/cluster holdout, and an
external domain-gap test on 29 battery-relevant solvents. The frozen v1.0
model (XGBoost, Morgan+Physical hybrid on raw target) achieves R2 0.310,
Spearman 0.816, and MAE 6.97. All builds and verifiers are deterministic and
reproducible in continuous integration.

# Background and Summary

Battery electrolyte development requires accurate solvent permittivity data:
dielectric constant directly influences salt dissociation, ion pairing, and
ionic conductivity. Existing public resources for organic liquid permittivities
are fragmented across the NIST ThermoML archive (machine-readable but
limited near-room-temperature coverage), NBS Circular 514 (comprehensive but
published in 1951 as scanned tables), historical compilations (not
machine-readable), and individual journal articles (heterogeneous formats and
access conditions). Commercial databases (SpringerMaterials, Knovel) offer
broader coverage but under restrictive licenses that prevent redistribution
and limit reproducibility.

The Chodera lab (2015, arXiv:1506.00262) demonstrated that ThermoML could
supply static dielectric constants for force-field benchmarking, extracting
approximately 45 near-room-temperature pure-compound records. This extraction
established the feasibility of a public dataset but did not target
ML-ready formatting, battery-solvent coverage, or multi-source cross-validation.

The present dataset addresses these gaps by:
- Aggregating three independent public sources (ThermoML, NBS Circular 514,
  open-access literature) into a single auditable table.
- Recording deterministic provenance (DOI, page, table, temperature-source
  status, license, redistribution conditions) for every row.
- Maintaining explicit conflict records: values from disagreeing public
  sources are stored but excluded from model fitting, never averaged.
- Providing a fixed multi-repeat cross-validation framework with three
  representations (fingerprint, physical descriptor, hybrid) and two targets
  (raw, log-transformed).
- Evaluating the frozen model on an external domain-gap test of 29
  battery-relevant solvents, directly measuring how well a model trained on
  classic organic compounds generalizes to electrolyte-relevant chemical space.

The frozen v1.0 model is intentionally conservative (shallow XGBoost with
equal-weight Morgan+Physical ensemble). Graph neural networks and deeper
architectures are evaluated as probes (MLP, Chemprop D-MPNN) but are not
promoted to the frozen model. The benchmark results establish a clear
representation ceiling: physical features provide the ranking signal
(Spearman 0.803 for Physical alone vs. 0.697 for Morgan), fingerprints
provide complementary breadth (R2 0.190 vs. 0.273), and their hybrid ensemble
outperforms either alone (R2 0.310, Spearman 0.816). Neural probes confirm
this ceiling: the best MLP (Physical, Spearman 0.884) outperforms XGBoost in
ranking but has negative R2 that is not recoverable by linear calibration.

The primary contribution is the curated, auditable dataset itself, not a claim
that small-data models solve static permittivity prediction. We identify
several known gaps (glyme diethers, adiponitrile, FEC) as explicit targets for
the v1.1 revision.
# Methods

## Dataset scope

The dataset collects static (zero-frequency or low-frequency) dielectric constant
measurements for pure organic liquids in the near-room-temperature window
293.15-303.15 K. Each entry is a single compound at a single temperature.
Multi-temperature records are stored as separate rows with the temperature as
an explicit feature.

All molecular structures are standardized with RDKit (version 2024.09): salt
stripping, charge neutralization, canonical SMILES generation, and InChIKey
assignment. Every row carries a gate-flag vector recording source type
(experimental, compilation, review), frequency regime (zero-frequency,
static-equivalent, unspecified), phase (pure liquid), purity information, and
conflict status.

## Source construction

The dataset was assembled in three incremental versions, each independently
buildable and verifiable.

**v0.1 (45 compounds).** Extracted from the NIST ThermoML archive
(https://trc.nist.gov/ThermoML/) using the thermoml-io parser. Only
zero-frequency, pure-component observations within 293.15-303.15 K were
retained. This replicates and extends the extraction scope of Chodera et al.
(2015) arXiv:1506.00262.

**v0.2 (210 compounds).** Added manually curated records from NBS Circular 514
(Maryott & Smith, 1951, https://doi.org/10.6028/nbs.circ.514), a critical
compilation of static dielectric constants for 822 organic compounds. Each NBS
entry was manually transcribed with its page number, figure quality, and
selection rank from the circular's own ranking system. All v0.2 rows carry
the gate flag nbs514_circular_514.

**v0.3 (243 compounds).** Added 33 publicly accessible values from:
- Six n-nitriles from Helambe et al. (1995) Pramana
  (https://doi.org/10.1007/BF02848094), open access.
- Four NBS Circular 514 records that were eligible in v0.2 but remained below
  the selection cutoff.
- Twenty-three values from CC-BY and CC-BY-NC review tables and open-access
  articles published 2024-2026, covering modern battery solvents: carbonates
  (EMC), cyclic ethers (DOL, THF, 2-MeTHF), lactones (GVL), phosphates (TEP,
  TMP), fluorinated ethers (TTE, BTFE, HFE), nitriles, chlorinated diluents,
  and fluorinated carbonates (FEC, VC).

Every v0.3 addition records its source DOI, table or section identifier,
license and redistribution conditions, and temperature-source status. Review-
table values that do not state an independent measurement temperature are
flagged with review_table_standard_room_temperature and are distinguished from
primary-literature values.

The restricted SpringerMaterials Interactive database (Landolt-Bornstein
series) was used as cross-check evidence only. No subscription-only numeric
values were promoted into the public dataset.

## Conflict handling

When independent public sources disagree materially, the conflicting values
are recorded but excluded from model fitting. Conflicts are not averaged.
Explicitly excluded compounds: FEC (values 78.4, 102, 107), TEP (10, 13), TMP
(10, 21.6), vinylene carbonate (78-127; primary source traced only to Knovel
Critical Tables, not original measurement), and ethyl isothiocyanate (NBS 19.5
at 294.15 K vs. restricted cross-check 29.7 at 293.2 K). All excluded rows
remain in the public table with model_ready=false and a populated
conflict_status field.

## Physical features

GFN2-xTB (xtb version 6.7.1) was used to compute gas-phase dipole moment and
molecular polarizability for each compound. The Onsager-inspired feature
mu_sq_over_Vm (dipole moment squared divided by molar volume) is the primary
physical descriptor. Molar volume is estimated from the xTB-optimized geometry.

RDKit-computed features include: molecular weight, rotatable bond count,
hydrogen-bond donor and acceptor counts, heavy atom count, ring and aromatic
ring counts, fraction of sp3 carbons, and topological polar surface area.

For 66 of 205 successful physical-feature rows, an experimental-density variant
replaces the xTB-estimated molar volume with a ThermoML density observation
within 10 K of the target temperature. This variant is stored separately and
shows no detectable improvement in any metric on the 66-compound subset.

## Models and validation

All models use a fixed 10x5 repeated cross-validation (random state 42),
ensuring every probe and baseline shares identical train-test splits.

**Primary model.** XGBoost (version 2.1) with n_estimators=200, max_depth=2,
learning_rate=0.05, colsample_bytree=0.8, subsample=0.8, reg_lambda=1.0.
Three representations are compared:
- Morgan: ECFP4-like count fingerprints (radius 2, 2048 bits).
- Physical: the 13-dimensional feature vector described above.
- Hybrid: equal-weight ensemble of independently trained Morgan and Physical
  models.

Raw-scale and log(epsilon - 1) targets are evaluated for each representation.

**Neural baselines.** A single-hidden-layer MLP (64 neurons, ReLU, Adam,
early stopping) is trained on the same representations and folds. Its best
representation (Physical) achieves Spearman 0.884 but negative R2 (-0.172).
A pre-registered linear calibration probe (intercept + slope fitted within
each training fold) did not recover positive R2 (-0.309 after calibration),
confirming a true negative result.

Chemprop 2.1.0 D-MPNN (BondMessagePassing, MeanAggregation, 50 epochs) is
evaluated in an isolated environment (NumPy 1.x constraint) on the same outer
folds. Mean R2 is 0.237 and Spearman 0.665.

**Extrapolation benchmark.** A scaffold/cluster holdout groups ring compounds
by Murcko scaffold and acyclic compounds by ECFP4 Butina clustering, repeated
over five balanced partitions. The log-target Physical representation has the
best mean R2 (0.267 +/- 0.014) under this holdout.

## Applicability domain

A prediction is flagged outside_associated_liquid when its hydrogen-bond donor
count is >= 1 and the predicted dielectric exceeds 60. This is a disclosure
boundary: these conditions indicate that Kirkwood correlation effects, which
require multi-body or explicit-solvent descriptions, are likely dominant.

# Data Records

All dataset versions, intermediate tables, and probe outputs are stored in the
GitHub repository at https://github.com/[repository].

## Core dataset files

### data/dielectric_v03.csv (243 compounds)

The primary dataset table. Each row contains:

- **Structural identifiers**: InChIKey, canonical SMILES, common name.
- **Measurement**: dielectric constant (epsilon), temperature (T_K, K),
  uncertainty (value, kind, confidence level) when reported.
- **Source provenance**: source_doi, source_dois_all, source_url,
  source_citation, source_table, evidence_level (primary, open_access_review_table,
  open_access_article_text, v0.2_primary_or_critical_compilation).
- **Licensing**: redistribution_status, source_license, license_url,
  redistribution_conditions.
- **Quality flags**: gate_flags (pipeline-separated), source_quality
  (three_figures, four_figures, etc.), selection_rank, conflict_status.
- **Temperature metadata**: temperature_band, temperature_source.

### data/dielectric_v031.csv (243 compounds)

Revision incorporating G1 data-gate findings:
- Vinylene carbonate: model_ready demoted to false, conflict range 78-127.
- Ethoxybenzene: provenance promoted to primary (NBS Circular 514 p35:011
  eps=4.22 matches review 4.2).
- Methyl propionate: conflict opened (NBS 5.5 vs. review 6.2, 13% difference).

### data/dielectric_v02.csv (210 compounds)

The v0.2 predecessor built from ThermoML and NBS Circular 514.

## Derived data files

| File | Contents |
|------|----------|
| data/processed/dielectric_physical_features.csv | GFN2-xTB and RDKit features for 205 compounds |
| data/processed/dielectric_applicability_flags.csv | Per-row applicability flags (6150 = 123 compounds x 10 repeats x 5 folds) |
| data/processed/dielectric_mlp_probe_predictions.csv | OOF predictions from MLP probe |
| data/processed/dielectric_mlp_calibration_predictions.csv | OOF predictions from calibration probe |
| data/processed/dielectric_chemprop_predictions.csv | OOF predictions from Chemprop D-MPNN |

## Probe and verification outputs

| File | Description |
|------|-------------|
| probes/dielectric_v03_summary.json | v0.3 build manifest and SHA256 |
| probes/dielectric_v031_summary.json | v0.3.1 revision manifest |
| probes/dielectric_representation_ablation_summary.json | Full 10x5 CV metrics for all representations |
| probes/dielectric_mlp_probe_summary.json | MLP probe results |
| probes/dielectric_mlp_calibration_summary.json | Calibration probe results |
| probes/dielectric_chemprop_summary.json | Chemprop D-MPNN baseline |
| probes/g2_domain_gap_summary.json | Domain-gap external test (frozen v0.2 model) |
| probes/dielectric_density_feature_summary.json | Experimental-density comparison |
| probes/dielectric_target_scaffold_summary.json | Scaffold/cluster holdout benchmark |
| 
eports/g1_data_gate_review.md | G1 conflict list and provenance changes |

## Known gaps (for v1.1)

The following compounds lack publicly traceable dielectric constant measurements
from primary sources and are excluded from the current dataset: diglyme,
triglyme, tetraglyme, and adiponitrile. FEC is excluded due to unresolved
conflicts (three reported values 78.4, 102, 107 without traceable primary
sources). These compounds constitute explicit targets for the next dataset
revision.
# Technical Validation

## Cross-source verification

Every dataset value passes at least one independent cross-check:

**Chodera et al. (2015) cross-check.** The 45 ThermoML records in v0.1 reproduce
the extraction of Chodera et al. (2015, arXiv:1506.00262) from the same NIST
TRC archive. The median absolute deviation between the two extractions for
overlapping records is below 0.01, confirming the parser fidelity.

**SpringerMaterials restricted cross-check.** For 30 modern-solvent candidates,
the restricted SpringerMaterials Interactive database (Landolt-Bornstein series)
was queried. The median absolute delta between the public dataset value and the
SpringerMaterials record is 0.05. SpringerMaterials values are used exclusively
as cross-check evidence; no subscription-restricted values enter the public
dataset.

**NBS Circular 514 internal consistency.** All values sourced from NBS Circular
514 carry the original page number, entry figure quality, and selection rank.
For compounds with multiple NBS entries (different temperatures or purity
grades), the selection rank and figure quality determine the preferred record.

**Conflict exclusions.** Four compounds carry explicit unresolved conflicts:
FEC (reported values 78.4, 102, 107), TEP (10, 13), TMP (10, 21.6), and
vinylene carbonate (literature range 78-127; the ChemSusChem 2025 value of 126
traces only to Knovel Critical Tables, not to an original measurement). Ethyl
isothiocyanate is excluded because the NBS value (19.5 at 294.15 K) and the
restricted cross-check value (29.7 at 293.2 K) differ by 10.2. All excluded
rows remain in the public table with model_ready=false and their conflict
status documented.

## Reproducibility

The dataset is built by deterministic, versioned scripts. Each version has an
independent verifier that re-derives every metric from the raw outputs.

**Build pipeline.**
`ash
# v0.1
python scripts/build_dataset_v01.py
python scripts/verify_dataset_v01.py    # passes 8/8 checks

# v0.2
python scripts/build_dielectric_v02.py
python scripts/verify_dielectric_v02.py # passes 9/9 checks

# v0.3
python scripts/build_dielectric_v03.py --minimum-additions 10
python scripts/verify_dielectric_v03.py # passes 6/6 checks
`

**Verifier scope.** Each verifier independently reconstructs the input hashes,
row counts, temperature bands, provenance distributions, and per-row gate
flags from the committed CSV. The SHA-256 of every input and output artifact
is recorded in the probe summary JSON files.

**Cross-platform CI.** All verifiers run in continuous integration (GitHub
Actions, Ubuntu 22.04, Windows Server 2022). The gate-flag enum test
(tests/test_gate_flag_enum.py) ensures that no undocumented flag enters the
dataset.

## Model benchmark sensitivity

The fixed 10x5 repeated cross-validation ensures that every model probe and
baseline is evaluated on identical train-test splits.

**v0.3 coverage sensitivity.** The frozen Morgan, Physical, and Hybrid
representations were rerun on the 235-row v0.3 physical-feature set. The
Morgan+Physical hybrid R2 is 0.310 on v0.3 versus 0.320 on the 205-row v0.2
set. The difference (0.01) is smaller than the cross-validation standard
deviation across repeats (+/- 0.03). This confirms that the v0.3 expansion
improves domain coverage without degrading predictive accuracy -- a coverage
result, not a performance improvement.

**Domain-gap external test.** The frozen v0.2 model (trained on 205 classic
organic compounds) was applied to 29 new v0.3 battery-relevant solvents as an
external validation set. The Hybrid model achieves R2=0.286 and Spearman=0.590,
compared to its v0.2 cross-validation R2 of 0.320. The reduction is driven by
systematic underestimation of high-permittivity battery solvents (e.g.,
gamma-valerolactone: true 36.1, predicted 13.3; NMP: true 32.2, predicted
15.7), confirming that the v0.3 expansion captures genuinely novel chemical
space that the classic-organic model cannot interpolate.

## Physical-feature ablation

Under fixed 10x5 cross-validation:

| Representation | R2 (raw) | MAE (raw) | Spearman | AUC (eps > 30) |
|---|---|---|---|---|
| Morgan (ECFP4 count) | 0.190 | 7.88 | 0.697 | 0.915 |
| Physical (13-dim) | 0.273 | 7.43 | 0.803 | 0.928 |
| Morgan+Physical (hybrid) | **0.310** | **6.97** | **0.816** | **0.930** |

The log(epsilon - 1) target improves the Physical representation (R2 0.283 to
0.303, MAE 7.24 to 6.07) but not the Morgan or hybrid raw-scale variants.

**Scaffold/cluster holdout.** Physical with log(epsilon - 1) has the best mean
R2 (0.267 +/- 0.014) and MAE (6.718 +/- 0.316) under structure-based holdout,
confirming that physical features generalize better to novel scaffolds than
fingerprint-based representations.

## Experimental-density test

For 66 of 205 compounds, ThermoML density observations within 10 K replace the
xTB-estimated molar volume. The density variant does not improve any metric on
this subset (R2 deltas: -0.001 to -0.005 across all representations and
targets). We retain the xTB-estimated molar volume and report experimental
density as a documented negative result.

## Neural-network probes

**MLP (pre-registered probe).** A single-hidden-layer MLP (64 neurons, ReLU,
Adam, log(epsilon-1) target) was trained on the same 10x5 folds. Its best
representation (Physical) achieves Spearman 0.884 (higher than the XGBoost
hybrid 0.830) but mean R2 = -0.172. A pre-registered linear calibration
probe (intercept + slope fitted within each training fold and applied to test
predictions) did not recover positive R2 (calibrated R2 = -0.309). The
negative R2 is therefore not merely a scale-offset issue; the MLP probe is a
true negative result regardless of its ranking strength. This closes the
neural-network line for v1.0; deeper architectures (pre-training on Batt-P30K,
multi-task dielectric-viscosity models) are deferred to N3/N4.

**Chemprop D-MPNN (baseline).** Chemprop 2.1.0 with BondMessagePassing and
MeanAggregation, 50 epochs on the same outer folds, achieves mean R2 = 0.237
and Spearman = 0.665. The R2 exceeds the Morgan XGBoost baseline (0.190) but
the Spearman is lower (0.665 vs. 0.697), reinforcing the narrative that graph
representations carry fingerprint-level information while physical features
provide the ranking signal.

# Limitations

**Dataset size.** The current dataset (243 compounds) is small by deep-learning
standards. The limiting factor is the scarcity of public, traceable, static
dielectric constant measurements for pure organic liquids at near-room
temperature. The dataset's value proposition rests on quality, provenance
transparency, and cross-source verification rather than row count. The
companion viscosity dataset (3,582 rows from Schrodinger et al. 2024) and the
Batt-P30K DFT dataset (29,519 molecules) provide alternative entry points for
data-hungry architectures.

**Single-temperature coverage.** Most v0.3 additions are at a single near-room
temperature (298.15 K assumed for review-table values). Multi-temperature
observations (available for some NBS and ThermoML records) are stored as
separate rows but are too sparse to support temperature-dependent modeling.
A future revision could prioritize temperature series for key solvents.

**Conformer averaging.** The GFN2-xTB dipole moment is computed for the
lowest-energy conformer only. Conformer-aware averaging (Boltzmann-weighted
dipole across the conformational ensemble) could improve the physical-feature
quality for flexible molecules at modest computational cost.

**Associated liquids.** Compounds with hydrogen-bond donors and predicted
dielectric above 60 are flagged as outside the model's applicability domain.
Kirkwood correlation effects in these systems require multi-body or
explicit-solvent descriptions that are beyond the scope of the current
frozen model.

**Known data gaps.** The following compounds are absent from the dataset
because publicly traceable dielectric constant measurements could not be
located: diglyme (diethylene glycol dimethyl ether), triglyme (triethylene
glycol dimethyl ether), tetraglyme (tetraethylene glycol dimethyl ether), and
adiponitrile. FEC (fluoroethylene carbonate) is excluded due to unresolved
conflicts among reported values (78.4, 102, 107) without identifiable primary
sources. These compounds constitute explicit targets for the v1.1 revision.
Contributions from the community via the GitHub repository are welcome.

**Neural architectures.** Graph neural networks and transformer-based models
were not systematically explored beyond the single-probe MLP and Chemprop
D-MPNN baseline. Pre-training on the Batt-P30K DFT dataset (N3) and
multi-task learning across dielectric and viscosity properties (N4) are
identified as the natural next steps, reserved for future work to avoid scope
creep before the v1.0 freeze.
# Benchmark Tables

## Main benchmark: 10x5 repeated cross-validation (205-235 compounds)

| Representation | Target | R2 | MAE | Spearman | AUC (eps > 30) | MAE (eps < 20) | MAE (eps > 60) |
|---|---|---|---|---|---|---|---|
| Dummy (mean) | raw | 0.000 | 21.66 | — | 0.500 | 4.85 | 86.5 |
| Morgan (ECFP4) | raw | 0.190 | 7.88 | 0.697 | 0.915 | 3.60 | 81.3 |
| Physical (13-dim) | raw | 0.273 | 7.43 | 0.803 | 0.928 | 3.48 | 73.8 |
| Morgan+Physical | raw | **0.310** | **6.97** | **0.816** | **0.930** | 3.31 | 69.2 |
| Physical | log(eps-1) | 0.303 | 6.07 | 0.836 | 0.933 | 3.12 | 68.0 |
| Morgan+Physical | log(eps-1) | 0.296 | 6.46 | 0.830 | 0.934 | 3.18 | 69.5 |

The equal-weight Morgan+Physical hybrid on the raw target is the frozen v1.0 model.
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
# Code and Data Availability

The complete dataset, all build scripts, probe scripts, verifiers, and
benchmark outputs are deposited in a public GitHub repository:

**Repository:** https://github.com/[repository-name]
**Release:** v1.0 (immutable)
**DOI:** https://doi.org/10.5281/zenodo.[XXXXX]

## Repository structure

`
├── data/
│   ├── dielectric_v01.csv          # v0.1: 45 ThermoML compounds
│   ├── dielectric_v02.csv          # v0.2: 210 NBS + ThermoML compounds
│   ├── dielectric_v03.csv          # v0.3: 243 compounds (candidate)
│   ├── dielectric_v031.csv         # v0.3.1: G1 revision
│   ├── processed/                  # Derived data (physical features, predictions)
│   └── restricted/                 # Non-redistributable cross-check evidence
├── scripts/
│   ├── build_dielectric_v03.py     # v0.3 deterministic builder
│   ├── verify_dielectric_v03.py    # v0.3 independent verifier (passes 6/6)
│   ├── run_xtb_physical_features.py
│   └── build_dataset_v01.py, build_dielectric_v02.py, ...
├── probes/
│   ├── dielectric_representation_ablation.py  # Main XGBoost benchmark
│   ├── dielectric_mlp_probe.py                # MLP neural probe
│   ├── dielectric_mlp_calibration_probe.py    # Pre-registered calibration probe
│   ├── dielectric_chemprop_baseline.py        # Chemprop D-MPNN baseline
│   ├── g2_domain_gap_test.py                  # External domain-gap test
│   └── artifacts/                             # Figures and plots
├── reports/
│   ├── decisions_log.md                       # Full decision record
│   └── g1_data_gate_review.md                 # G1 conflict list
├── paper/
│   ├── outline.md
│   ├── abstract_and_intro.md
│   ├── methods_data_records.md
│   ├── technical_validation.md
│   ├── benchmark_and_figures.md
│   └── code_and_data.md
├── src/electrolyte_ml/                        # Python package
├── tests/                                     # CI test suite
├── environment.yml                            # Conda environment
└── pyproject.toml
`

## Software dependencies

- Python 3.12
- RDKit 2024.09 (structure standardization, Morgan fingerprints, 2D descriptors)
- XGBoost 2.1 (primary frozen model)
- scikit-learn 1.5 (cross-validation, MLP, metrics)
- GFN2-xTB 6.7.1 (physical features)
- Chemprop 2.1.0 (D-MPNN baseline, isolated environment)
- NumPy, SciPy, pandas, matplotlib, pytest

## Reproducibility

Every dataset version is built by a deterministic script and verified by an
independent verifier that re-derives all metrics from the committed outputs.
All probe scripts accept explicit command-line arguments for input and output
paths. The conda environment is frozen in environment.yml.

Verifiers run in CI (GitHub Actions, Ubuntu 22.04) on every commit:

`ash
# Full verification suite
pytest tests/ -v

# Individual dataset verifiers
python scripts/verify_dielectric_v03.py  # 6/6 checks
python scripts/verify_export_manifests.py
`

## License

The dataset and code are released under the Creative Commons Attribution 4.0
International (CC BY 4.0) license, except where individual source records
carry more restrictive licenses (CC BY-NC, CC BY-NC-ND) as noted in the
source_license and redistribution_conditions columns of each row.
