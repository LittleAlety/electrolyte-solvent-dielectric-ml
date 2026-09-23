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
| eports/g1_data_gate_review.md | G1 conflict list and provenance changes |

## Known gaps (for v1.1)

The following compounds lack publicly traceable dielectric constant measurements
from primary sources and are excluded from the current dataset: diglyme,
triglyme, tetraglyme, and adiponitrile. FEC is excluded due to unresolved
conflicts (three reported values 78.4, 102, 107 without traceable primary
sources). These compounds constitute explicit targets for the next dataset
revision.
