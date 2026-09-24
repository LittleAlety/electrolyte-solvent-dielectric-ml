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

**v0.1 (100 compounds).** Extracted from the NIST ThermoML archive
(https://trc.nist.gov/ThermoML/) using the thermoml-io parser. Only
zero-frequency, pure-component observations within 293.15-303.15 K were
retained. The extraction shares 45 keys with Chodera et al. (2015)
arXiv:1506.00262 from the same archive, and that 45-record overlap is the figure
quoted in the cross-check below; v0.1 itself holds 100 compounds.

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

**v0.3.2 (245 compounds).** Added the two decisive battery carbonates that were
absent from every earlier revision:
- Propylene carbonate (PC, epsilon=64.9 at 298.15 K) from Simeral & Amey (1970)
  J. Phys. Chem. 74, 1443 (https://doi.org/10.1021/j100702a008).
- Ethylene carbonate (EC, epsilon=90.5 at 313.15 K) from Chernyak (2006)
  J. Chem. Eng. Data 51, 416 (https://doi.org/10.1021/je050341y); EC melts at
  36.4 C, so the measurement is flagged extended_temperature.

**v0.3.3 (246 compounds).** Adds one row and repairs provenance. The new row is
3-methoxypropionitrile (epsilon=36.0 at 298.15 K), transcribed from the ECW-308
battery-solvent supporting information (Wang & Shi, Adv. Funct. Mater. 2023,
https://doi.org/10.1002/adfm.202212342). No traceable primary measurement was
found for it, so it is flagged secondary_compilation_unverified with
model_ready=false. v0.3.3 also applies 30 reproducible provenance patches
(data/processed/dielectric_v03_provenance_patches.csv) that restore the
source-priority decisions and conflict records that earlier hand-edits had
lost.

Every v0.3 addition records its source DOI, table or section identifier,
license and redistribution conditions, and temperature-source status. Review-
table values that do not state an independent measurement temperature are
flagged with review_table_standard_room_temperature and are distinguished from
primary-literature values.

The restricted SpringerMaterials Interactive database (Landolt-Bornstein
series) was used as cross-check evidence only. No subscription-only numeric
values were promoted into the public dataset.

ECW-308 (Wang et al., Adv. Funct. Mater. 2023, DOI
10.1002/adfm.202212342) was retrieved from a non-redistributable publisher
supplement and used only as a secondary cross-check. It reproduces PC 64.90
exactly, reports EC 89.00 at a different temperature (25 C versus the stored
313.15 K), supports the glyme values, and disagrees with the retained primary
nitrile values. No ECW-308 numeric value replaces a primary row.

## Conflict handling

When independent public sources disagree materially, the conflicting values
are recorded and the row is flagged; conflicts are never averaged. Nine rows
carry an explicit conflict_status and six are flagged model_ready=false. The
benchmark withholds four rows through a curated exclusion list
(data/processed/dielectric_v03_exclusions.csv): FEC (values 78.4, 102, 107),
TEP (10, 13), TMP (10, 21.6), and ethyl isothiocyanate (NBS 19.5 at 294.15 K vs.
restricted cross-check 29.7 at 293.2 K). Methyl propionate (NBS 5.5 vs. review
6.2) is also documented and retained. Adiponitrile and glutaronitrile retain
their ThermoML primary values (32.12 and 34.6); ECW-308 compilation values
(30.00 and 37.00) are recorded as disagreements, not replacements.

One flagged row is not yet withheld. Vinylene carbonate (literature range
78-127; ECW-308 independently reports 126.00, but this study did not trace 126
to an original measurement) carries model_ready=false and conflict_open but
still reaches the feature table, because the modelling pipeline currently
honours only the exclusion list and not the model_ready flag. The discrepancy is
recorded as a known issue rather than smoothed over; 3-methoxypropionitrile has
no physical-feature row, so it is absent from the fitted set for that reason
alone.

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

### data/dielectric_v03.csv (246 compounds)

The current table (dataset version 0.3.3). It is a strict superset of v0.3.2:
the only added row is 3-methoxypropionitrile, flagged
secondary_compilation_unverified and model_ready=false. Each row contains:

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

Superseded historical revision (v0.3.1) incorporating the first G1 data-gate
findings:
- Vinylene carbonate: model_ready demoted to false, conflict range 78-127.
- Ethoxybenzene: provenance promoted to primary (NBS Circular 514 p35:011
  eps=4.22 matches review 4.2).
- Methyl propionate: conflict opened (NBS 5.5 vs. review 6.2, 13% difference).

### data/dielectric_v032.csv (245 compounds)

Superseded by v0.3.3. Supersedes v0.3.1 by adding two decisive battery
solvents that were missing from all earlier revisions:
- Propylene carbonate (PC), epsilon=64.9 at 298.15 K, primary source traced to
  Simeral & Amey (1970) DOI 10.1021/j100702a008.
- Ethylene carbonate (EC), epsilon=90.5 at 313.15 K (liquid range), primary
  source DOI 10.1021/je050341y, flagged extended_temperature.
The glyme diethers (diglyme/triglyme/tetraglyme) and the dinitriles
(adiponitrile, glutaronitrile) that earlier reports listed as "absent" were
already present under their IUPAC names; they are now documented explicitly.

### data/dielectric_v02.csv (210 compounds)

The v0.2 predecessor built from ThermoML and NBS Circular 514.

## Derived data files

| File | Contents |
|------|----------|
| data/processed/dielectric_physical_features.csv | GFN2-xTB and RDKit features for 205 compounds |
| data/processed/dielectric_applicability_flags.csv | Per-row applicability flags (6150 = 205 compounds x 3 representations x 10 repeats; each row carries the held-out fold index) |
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
| probes/dielectric_target_scaffold_summary.json | Scaffold/cluster holdout benchmark (v0.2, 205 rows) |
| probes/v032_target_scaffold_summary.json | v0.3.2 target-transform and scaffold benchmark (237 rows) |
| probes/v032_ablation_summary.json | v0.3.2 main ablation benchmark (237 rows) |
| probes/v032_controlled_comparison_summary.json | Paired PC/EC train-only control |
| probes/dielectric_v03_summary.json | v0.3.3 build manifest, patches and SHA256 |
| 
eports/g1_data_gate_review.md | G1 conflict list and provenance changes |

## Known gaps (for v1.1)

**Fluoroethylene carbonate (FEC).** Withheld from model fitting through the
curated exclusion list because public sources disagree (78.4, 102, 107).
ECW-308 independently supports the low endpoint 78.4, but its cited original
table was not retrieved and 102/107 remain unresolved.

**3-Methoxypropionitrile (MOPN).** Present in the table as a flagged,
non-model-ready row (36.0 at 298.15 K, secondary_compilation_unverified). Tier-0
checks over all 242 local ThermoML dielectric files and all 636 transcribed NBS
Circular 514 organic rows returned no permittivity observation for it. The value
rests on the ECW-308 battery-solvent compilation, and its cited primary source
(Perricone et al. 2013, https://doi.org/10.1016/j.electacta.2013.01.084) is
closed access with no open full text. It is the single named solvent gap.

**Resolved gap reports.** The glyme diethers and the dinitriles that earlier
internal reports listed as absent are present in the table under their IUPAC
names (diglyme = 2,5,8-trioxanonane, and so on); those reports were wrong about
absence, not about the underlying measurements. The open items above constitute
explicit targets for the next dataset revision.
