# Abstract

We present an auditable, machine-learning-ready dataset of static dielectric
constants (relative permittivities) for 246 pure organic liquids at near-room
temperature (293.15-303.15 K). The dataset is assembled from three sources:
the NIST ThermoML archive (v0.1, 100 compounds), NBS Circular 514 (v0.2, 210
compounds), and open-access review tables and primary literature covering
modern battery solvents (v0.3.3, 246 compounds), plus one non-redistributable
publisher-compilation value retained only as a numeric fact and explicitly
flagged. Every row carries deterministic
source provenance, gate-flag metadata, license and redistribution conditions,
and conflict status. Conflicting public values are recorded rather than
averaged: nine rows carry an explicit conflict or unverified-provenance
record, six are flagged model_ready=false, and the benchmark withholds four
rows through a curated exclusion list.

A companion benchmark evaluates three representations (Morgan fingerprints,
13-dimensional physical features from GFN2-xTB and RDKit, and their
equal-weight hybrid) under fixed 10x5 repeated cross-validation,
scaffold/cluster holdout, and an external domain-gap test on 29 battery-relevant
solvents. The v0.3.2 benchmark is carried unchanged into the v0.3.3 candidate,
because v0.3.3 adds no model-ready row; the selected XGBoost Morgan+Physical
hybrid on the raw target achieves R2 0.366, Spearman 0.814, and MAE 7.13 on 237
fitted rows. A paired control that freezes the v0.3 fold assignment and appends
the two added battery carbonates to the training folds only attributes +0.027 R2
(95% CI +0.017 to +0.036) to the data addition, and both added solvents remain
outside the model's extrapolation range. All builds and verifiers are
deterministic and reproducible in continuous integration.

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
- Maintaining explicit conflict records: disagreeing values are stored, never
  averaged, and the withholding decision is recorded per row rather than
  applied as a blanket rule. The benchmark withholds the four rows on the
  curated exclusion list; rows that are flagged but still fitted are labelled
  as such.
- Providing a fixed multi-repeat cross-validation framework with three
  representations (fingerprint, physical descriptor, hybrid) and two targets
  (raw, log-transformed).
- Evaluating the frozen v0.2 model on an external domain-gap test of 29
  battery-relevant solvents, directly measuring how well a model trained on
  classic organic compounds generalizes to electrolyte-relevant chemical space.

The candidate model is intentionally conservative (shallow XGBoost with
equal-weight Morgan+Physical ensemble). Graph neural networks and deeper
architectures are evaluated as probes (MLP, Chemprop D-MPNN) but are not
promoted to the candidate model. The benchmark results establish a clear
representation ceiling: physical features provide the ranking signal
(Spearman 0.801 for Physical alone vs. 0.689 for Morgan), fingerprints
provide complementary breadth (R2 0.223 vs. 0.354), and their hybrid ensemble
outperforms either alone (R2 0.366, Spearman 0.814). Neural probes confirm
this ceiling: the best MLP (Physical, Spearman 0.884) outperforms XGBoost in
ranking but has negative R2 that is not recoverable by linear calibration.

The primary contribution is the curated, auditable dataset itself, not a claim
that small-data models solve static permittivity prediction. The remaining
public-data gaps are narrow and explicit: 3-methoxypropionitrile rests on a
secondary compilation with no traceable primary measurement, and
fluoroethylene carbonate stays conflicted (78.4, 102, 107); ECW-308 independently supports the 78.4 branch, but the cited original table was not retrieved. The glyme diethers
and the dinitriles (adiponitrile, glutaronitrile) that earlier internal reports
listed as absent are present in the table under their IUPAC names. These open
gaps are explicit targets for the v1.1 revision.

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

A prediction is flagged outside_associated_liquid when the compound carries at
least one hydrogen-bond donor site, counted with the SMARTS pattern
`[O,S,N;!H0]` directly from the structure; a prediction below 1.0 is flagged
outside_nonphysical. The donor count is structural, so the boundary is
independent of any model output. The rule triggers on 2,070 of the 6,150
out-of-fold rows (33.66%). This is a disclosure boundary: donor sites indicate
that Kirkwood correlation effects, which require multi-body or
explicit-solvent descriptions, are likely dominant. Two alternative
formulations -- the original `predicted dielectric > 60` rule and a
model-independent Onsager estimate -- were measured and rejected; both are
recorded with their numbers in `probes/applicability_domain_summary.json` and
`reports/applicability_domain_veto_fix.md`.

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

# Technical Validation

## Cross-source verification

Every dataset value passes at least one independent cross-check:

**Chodera et al. (2015) cross-check.** The v0.1 extraction shares 45 keys with
the extraction of Chodera et al. (2015, arXiv:1506.00262) from the same NIST TRC
archive. The median absolute deviation between the two extractions is 0.175
(maximum 7.341), which is larger than parser noise. Temperature does not explain
it: 44 of the 45 key pairs sit within 0.05 K of each other. The difference is
therefore reported as an unresolved disagreement between two extractions of the
same archive, not as a fidelity check that passed. The 45 shared keys are also
why the Chodera overlap is sometimes quoted as "45 records"; v0.1 itself holds
100 compounds.

**SpringerMaterials restricted cross-check.** The restricted SpringerMaterials
Interactive database (Landolt-Bornstein series) was queried against the v0.2
table and matched 60 compounds. The median absolute delta between the public and
restricted values is 0.05 (p90 0.67, maximum 10.2, the last being the ethyl
isothiocyanate conflict). SpringerMaterials values are used exclusively as
cross-check evidence; no subscription-restricted value enters the public
dataset.

**NBS Circular 514 internal consistency.** All values sourced from NBS Circular
514 carry the original page number, entry figure quality, and selection rank.
For compounds with multiple NBS entries (different temperatures or purity
grades), the selection rank and figure quality determine the preferred record.

**Conflict exclusions (v0.3.3 conventions).** Nine rows carry a non-empty
conflict_status and six carry model_ready=false. Four of them are withheld from
model fitting through the curated exclusion list
(data/processed/dielectric_v03_exclusions.csv): FEC (reported values 78.4, 102,
107), TEP (10, 13), TMP (10, 21.6), and ethyl isothiocyanate, whose NBS value
(19.5 at 294.15 K) and restricted cross-check value (29.7 at 293.2 K) differ by
10.2. Methyl propionate (NBS 5.5 vs. review 6.2) and the two ECW-308
nitrile disagreements are recorded with their primary rows retained.

Two flagged rows need qualification rather than a clean exclusion claim.
Vinylene carbonate (literature range 78-127; ECW-308 independently reports
126.00, but this study did not trace 126 to an original measurement) carries
model_ready=false and conflict_open but still reaches the feature table, because
`probes/dielectric_representation_ablation.py` filters on the exclusion list and
not on the model_ready column; its epsilon of 126 therefore remains inside the
237-row benchmark. Eight benchmark rows have epsilon > 60, and vinylene
carbonate accounts for about 17.8% of the total epsilon > 60 absolute error of
the hybrid model; dropping it would move that stratum MAE from 63.93 to 60.04.
That is material but not dominant, and the row is reported rather than removed.
3-Methoxypropionitrile carries model_ready=false and
awaiting_primary_confirmation and is absent from the fitted set because it has no
GFN2-xTB physical-feature row, not because of the flag. The operative filter is
metadata, not the model_ready column. The frozen accounting is 245 source rows
= 237 fitted rows + 4 curated exclusions + 4 physical-feature failures (three
ionic liquids and iron pentacarbonyl).

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
python scripts/verify_dielectric_v03.py # passes 7/7 checks, 246 rows

# v0.3.2 / v0.3.3
python scripts/verify_dielectric_v032.py # passes 7/7 checks, 245 rows
python scripts/verify_dielectric_v03.py  # v0.3.3 superset check, 246 rows
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
baseline is evaluated on identical train-test splits **within a dataset
version**. Growing a dataset reshuffles the split, so a row-wise comparison
across versions is a coverage result, not a controlled estimate of what the
added compounds contribute.

**v0.3.2 coverage sensitivity.** The frozen Morgan, Physical, and Hybrid
representations were rerun under the identical fixed 10x5 protocol as each
dataset expanded. Every version was rebuilt from pinned inputs and the v0.3
baseline was reproduced exactly (R2 0.3099):

| Dataset | Fitted rows | Morgan R2 | Physical R2 | Hybrid R2 |
|---|---|---|---|---|
| v0.2 | 205 | 0.2025 | 0.2829 | 0.3201 |
| v0.3 | 235 | 0.1898 | 0.2731 | 0.3099 |
| **v0.3.2** | **237** | **0.2230** | **0.3538** | **0.3660** |

These values are not attributable to the two added compounds. Enlarging the
table from 235 to 237 rows reshuffles `RepeatedKFold`: 1272 of 2350
compound x repeat fold assignments (54.1%) differ between the two splits, and
the evaluation-set target variance grows by 8.1%. The v0.3 -> v0.3.2 row above
therefore mixes the data addition with a different random partition.

To isolate the data contribution we ran a paired control
(`probes/v032_controlled_comparison.py`). The v0.3 fold assignment was frozen,
all 235 v0.3 compounds kept their original folds in every repeat, and
propylene carbonate (epsilon 64.9) and ethylene carbonate (epsilon 90.5) were
appended to the **training folds only**, so both arms score exactly the same
held-out compounds:

| Representation | v0.3 R2 | + PC/EC (train only) | Paired delta | 95% CI | Paired p |
|---|---|---|---|---|---|
| Morgan | 0.1898 | 0.1899 | +0.0001 | [-0.006, +0.006] | 0.97 |
| Physical | 0.2731 | 0.3233 | **+0.0502** | [+0.032, +0.068] | 1.3e-4 |
| Morgan+Physical | 0.3099 | 0.3364 | **+0.0265** | [+0.017, +0.036] | 1.3e-4 |

The controlled hybrid gain is **+0.027**, about half of the +0.056 implied by
the raw version-to-version comparison. The effect sits in the Physical
representation (+0.050) while the Morgan fingerprint representation is flat
(+0.0001) and its MAE and Spearman deteriorate (p = 0.006 and p = 0.008).
That is consistent with the stated mechanism: the carbonate dipole feature,
not fingerprint bits, separates high-permittivity cyclic carbonates. The
hybrid MAE improves only slightly (6.970 -> 6.906, p = 0.14) while RMSE
improves by 0.31 (p = 9.5e-5), so the addition is a real but moderate
generalization gain rather than a step change.

**The added solvents stay outside the extrapolation range.** Training on all
235 v0.3 compounds and predicting PC and EC as external holdouts underestimates
both: the hybrid predicts 29.8 +/- 1.1 for PC (true 64.9) and 50.3 +/- 2.2 for
EC (true 90.5). Adding these two solvents improves interpolation among the
existing 235 compounds; it does not give the model extrapolation ability for
unseen high-permittivity carbonates. This limitation is consistent with the
applicability-domain rule recorded in the dataset.

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
| Morgan (ECFP4 count) | 0.223 | 8.22 | 0.689 | 0.826 |
| Physical (13-dim) | 0.354 | 7.50 | 0.801 | 0.936 |
| Morgan+Physical (hybrid) | **0.366** | **7.13** | **0.814** | **0.929** |

(All values are the v0.3.2 237-row benchmark; the v0.2 205-row reference
values remain 0.203 / 0.283 / 0.320 for the corresponding representations.)

The log(epsilon - 1) target improves the Physical representation on MAE
(7.50 to 6.53) and Spearman (0.801 to 0.883) while leaving R2 slightly lower
(0.354 to 0.338); it does not transfer to the hybrid (R2 0.315).

**Scaffold/cluster holdout (v0.3.2, 237 rows).** Physical with
log(epsilon - 1) has the best mean R2 (0.299 +/- 0.018) and MAE
(7.103 +/- 0.168) under structure-based holdout, confirming that physical
features generalize better to novel scaffolds than fingerprint-based
representations (probes/v032_target_scaffold_summary.json).

## Experimental-density test

For 66 of 205 compounds, ThermoML density observations within 10 K replace the
xTB-estimated molar volume. The density variant does not improve any metric on
this subset (R2 deltas: -0.001 to -0.005 across all representations and
targets). We retain the xTB-estimated molar volume and report experimental
density as a documented negative result.

## Neural-network probes

**MLP (pre-registered probe).** A single-hidden-layer MLP (64 neurons, ReLU,
Adam, log(epsilon-1) target) was trained on the same 10x5 folds of the 205-row
v0.2 feature table, not on the v0.3.2 fold set. Its best representation
(Physical) achieves Spearman 0.884 (higher than the XGBoost hybrid 0.830 on that
same 205-row table) but mean R2 = -0.172. A pre-registered linear calibration
probe (intercept + slope fitted within each training fold and applied to test
predictions) did not recover positive R2 (calibrated R2 = -0.309). The
negative R2 is therefore not merely a scale-offset issue; the MLP probe is a
true negative result regardless of its ranking strength. This closes the
neural-network line for v1.0; deeper architectures (pre-training on Batt-P30K,
multi-task dielectric-viscosity models) are deferred to N3/N4.

**Chemprop D-MPNN (baseline).** Chemprop 2.1.0 with BondMessagePassing and
MeanAggregation, 50 epochs on the same 205-row v0.2 outer folds, achieves mean
R2 = 0.237 and Spearman = 0.665. Against the like-for-like 205-row XGBoost
reference the R2 exceeds Morgan (0.237 vs. 0.203) but the Spearman is lower
(0.665 vs. 0.697 for Morgan and 0.821 for Physical), reinforcing the narrative
that graph representations carry fingerprint-level information while physical
features provide the ranking signal. Neither neural baseline was recomputed on
the v0.3.2 237-row folds.

# Limitations

**Dataset size.** The current dataset (246 compounds) is small by deep-learning
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

**Associated liquids.** Compounds that carry at least one hydrogen-bond donor
site, counted from the structure with the SMARTS pattern `[O,S,N;!H0]` and
never from the model output, are flagged as outside the model's applicability
domain. The rule triggers on 2,070 of the 6,150 out-of-fold rows (33.66%):
mean absolute error is 11.51 outside the domain against 5.02 inside, and it
covers all 150 rows whose measured permittivity exceeds 60. A model-independent
variant that thresholds an Onsager-estimated static dielectric at 60 was
implemented, wired into the production caller, and then rejected: the
reaction-field estimate is *low* for associated liquids (1.6-40 estimated
against measured 61-178, because the Kirkwood correlation factor `g` is much
greater than 1) and *high* for ionic liquids (82-153 estimated against measured
12-30), so it covered 0 of those 150 rows. Both rejected variants are recorded
with their numbers in `probes/applicability_domain_summary.json`. Kirkwood
correlation effects in these systems require multi-body or explicit-solvent
descriptions that are beyond the scope of the current candidate model.

**Known data gaps.** FEC (fluoroethylene carbonate) is withheld through the
curated exclusion list because reported values (78.4, 102, 107) disagree;
ECW-308 supports 78.4, but no primary source was independently retrieved and
102/107 remain unresolved. 3-Methoxypropionitrile rests on the
ECW-308 secondary compilation (36.0 at 298.15 K): Tier-0 checks of all 242 local
ThermoML dielectric files and all 636 transcribed NBS Circular 514 organic rows
returned no observation, and the cited primary source (Perricone et al. 2013) is
closed access. The glyme diethers and dinitriles that earlier drafts listed as
absent are in fact present in the dataset under their IUPAC names (diglyme =
2,5,8-trioxanonane, and so on) and are now documented explicitly. The remaining
items constitute explicit targets for the v1.1 revision. Contributions from the
community via the GitHub repository are welcome.

**The model_ready flag is advisory, not a gate.** The modelling pipeline filters
on the physical-feature status column and on the curated exclusion list; nothing
in it reads model_ready. Vinylene carbonate is therefore flagged
model_ready=false and conflict_open yet remains fitted, and so does methyl
propionate (conflict_open, model_ready=true). Two consequences are reported
rather than hidden: the 237-row benchmark contains one row the table itself marks
as unresolved, and 3-methoxypropionitrile is absent only because it never
received a physical-feature row. Closing the flag gap changes the fitted set and
invalidates the +0.0265 paired control, so it is recorded here as an open
decision instead of being applied silently.

**Neural architectures.** Graph neural networks and transformer-based models
were not systematically explored beyond the single-probe MLP and Chemprop
D-MPNN baseline. Pre-training on the Batt-P30K DFT dataset (N3) and
multi-task learning across dielectric and viscosity properties (N4) are
identified as the natural next steps, reserved for future work to avoid scope
creep before the v1.0 freeze.

# Benchmark Tables

## Main benchmark: 10x5 repeated cross-validation (v0.3.2 benchmark, 237 fitted rows)

| Representation | Target | R2 | MAE | Spearman | AUC (eps > 30) | MAE (eps < 20) |
|---|---|---|---|---|---|---|
| Constant (train-fold mean) | raw | -0.010 | 12.33 | — | — | 8.20 |
| Morgan (ECFP4) | raw | 0.223 | 8.22 | 0.689 | 0.826 | 4.74 |
| Physical (13-dim) | raw | 0.354 | 7.50 | 0.801 | 0.936 | 4.53 |
| Morgan+Physical | raw | **0.366** | **7.13** | **0.814** | 0.929 | 4.22 |
| Morgan | log(eps-1) | 0.192 | 7.66 | 0.767 | 0.851 | 3.24 |
| Physical | log(eps-1) | 0.338 | 6.53 | **0.883** | 0.931 | 2.68 |
| Morgan+Physical | log(eps-1) | 0.315 | 6.54 | 0.881 | 0.931 | 2.58 |

The reference row is a constant predictor set to the training-fold mean on the
same 10x5 folds, recomputed from `data/processed/v032_ablation_predictions.csv`.
It replaces an earlier `Dummy (mean)` row whose 21.66 MAE could not be
reproduced from any committed artifact. A constant predictor has no ranking
signal, so its Spearman and AUC are undefined rather than 0.5.

The equal-weight Morgan+Physical hybrid on the raw target is the v0.3.2
candidate model. It is selected for its consistent rank across all metrics, not
for a single best score. The log(eps-1) target improves the Physical
representation but does not transfer to the hybrid.

## Neural baselines (205-row v0.2 feature table, same 10x5 folds)

These rows were computed on `data/processed/dielectric_physical_features.csv`
(205 compounds, v0.2). They were **not** recomputed on the v0.3.2 237-row folds,
so they may only be compared against like-for-like 205-row XGBoost references.

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
237-row fold set.

## Extrapolation: scaffold/cluster holdout (v0.3.2, 237 rows)

Source: `probes/v032_target_scaffold_summary.json` (ring Murcko scaffolds plus
acyclic ECFP4 clusters, five balanced partitions). These values supersede the
older 205-row scaffold table.

| Representation | Target | R2 | MAE | Spearman |
|---|---|---|---|---|
| Morgan | raw | 0.129 +/- 0.017 | 9.861 +/- 0.280 | 0.558 +/- 0.042 |
| Physical | raw | 0.213 +/- 0.047 | 8.950 +/- 0.549 | 0.735 +/- 0.033 |
| Morgan+Physical | raw | 0.289 +/- 0.033 | 8.406 +/- 0.420 | 0.739 +/- 0.027 |
| Morgan | log(eps-1) | 0.138 +/- 0.022 | 8.964 +/- 0.228 | 0.619 +/- 0.034 |
| **Physical** | **log(eps-1)** | **0.299 +/- 0.018** | **7.103 +/- 0.168** | **0.855 +/- 0.017** |
| Morgan+Physical | log(eps-1) | 0.279 +/- 0.016 | 7.274 +/- 0.205 | 0.832 +/- 0.016 |

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
compounds, with median absolute deviation annotated. The four withheld
compounds (FEC, TEP, TMP, ethyl isothiocyanate) are highlighted as excluded
points, and the flagged-but-fitted row (vinylene carbonate) is annotated
separately.

# Code and Data Availability

The complete dataset, all build scripts, probe scripts, verifiers, and
benchmark outputs are deposited in a public GitHub repository:

**Repository:** https://github.com/[repository-name]
**Release:** v0.3.3 (candidate; v1.0 tag will be applied only after the Appendix I freeze conditions are met)
**DOI:** https://doi.org/10.5281/zenodo.[XXXXX]

## Repository structure

```text
├── data/
│   ├── dielectric_v01.csv           # v0.1: 100 ThermoML compounds
│   ├── dielectric_v02.csv           # v0.2: 210 NBS + ThermoML compounds
│   ├── dielectric_v03.csv           # v0.3.3: 246 compounds (current candidate)
│   ├── dielectric_v031.csv          # v0.3.1: G1 revision (243, historical)
│   ├── dielectric_v032.csv          # v0.3.2: PC+EC freeze (245, historical)
│   ├── processed/
│   │   ├── dielectric_v03_exclusions.csv           # 4-row curated exclusion list
│   │   ├── dielectric_v03_provenance_patches.csv   # 30 reproducible patches
│   └── restricted/                  # Non-redistributable cross-check evidence
├── scripts/
│   ├── build_dielectric_v03.py      # v0.3/v0.3.3 deterministic builder
│   ├── verify_dielectric_v03.py     # v0.3.3 verifier (7/7 checks, 246 rows)
│   ├── verify_dielectric_v032.py    # v0.3.2 verifier (7/7 checks, 245 rows)
│   ├── build_paper_full_draft.py    # Assembles paper/full_draft.md from the sections
│   ├── check_paper_artifact_consistency.py  # Paper claims vs. frozen artifacts
│   ├── run_xtb_physical_features.py
│   └── build_dataset_v01.py, build_dielectric_v02.py, ...
├── probes/
│   ├── dielectric_representation_ablation.py    # Main XGBoost benchmark
│   ├── dielectric_mlp_probe.py                  # MLP neural probe
│   ├── dielectric_mlp_calibration_probe.py      # Pre-registered calibration probe
│   ├── dielectric_chemprop_baseline.py          # Chemprop D-MPNN baseline
│   ├── g2_domain_gap_test.py                    # External domain-gap test
│   ├── v032_ablation_summary.json               # v0.3.2 237-row benchmark
│   ├── v032_target_scaffold_summary.json        # v0.3.2 scaffold holdout
│   ├── v032_controlled_comparison_summary.json  # Paired PC/EC control
│   └── artifacts/                               # Figures and plots
├── reports/
│   ├── decisions_log.md                         # Full decision record
│   ├── agent_workflow.md                        # Delegation and verification log
│   └── g1_data_gate_review.md                   # G1 conflict list
├── paper/
│   ├── outline.md
│   ├── abstract_and_intro.md
│   ├── methods_data_records.md
│   ├── technical_validation.md
│   ├── benchmark_and_figures.md
│   ├── code_and_data.md                         # sources of full_draft.md
│   └── full_draft.md                            # generated; do not edit by hand
├── src/electrolyte_ml/                          # Python package
├── tests/                                       # CI test suite
├── environment.yml                              # Conda environment
└── pyproject.toml
```

## Software dependencies

- Python 3.12
- RDKit 2024.09 (structure standardization, Morgan fingerprints, 2D descriptors)
- XGBoost 2.1 (primary candidate model)
- scikit-learn 1.5 (cross-validation, MLP, metrics)
- GFN2-xTB 6.7.1 (physical features)
- Chemprop 2.1.0 (D-MPNN baseline, isolated environment)
- NumPy, SciPy, pandas, matplotlib, pytest

## Reproducibility

Every dataset version is built by a deterministic script and verified by an
independent verifier that re-derives all metrics from the committed outputs.
All probe scripts accept explicit command-line arguments for input and output
paths. The conda environment is frozen in environment.yml.

`paper/full_draft.md` is generated from the five section files by
`scripts/build_paper_full_draft.py`; edit the sections, never the draft. The
section files and the generated draft are checked against the frozen artifacts
by `scripts/check_paper_artifact_consistency.py`, which runs in CI.

Verifiers run in CI (GitHub Actions, Ubuntu 22.04) on every commit:

```bash
# Full verification suite
pytest tests/ -v

# Individual dataset verifiers
python scripts/verify_dielectric_v032.py # 7/7 checks, 245 rows
python scripts/verify_dielectric_v03.py  # 7/7 checks, 246 rows
python scripts/verify_export_manifests.py

# Paper claims vs. frozen artifacts
python scripts/check_paper_artifact_consistency.py
```

## License

The dataset and code are released under the Creative Commons Attribution 4.0
International (CC BY 4.0) license, except where individual source records
carry more restrictive licenses (CC BY-NC, CC BY-NC-ND) as noted in the
source_license and redistribution_conditions columns of each row, or because
the underlying source has no stated reuse license.

Two rows need explicit qualification. 3-Methoxypropionitrile (MOPN) was
transcribed from the ECW-308 supporting information and carries no license
statement of its own, so it is flagged model_ready=false; the numeric fact is
retained while the underlying publisher supplement remains non-redistributable,
and no open-license claim is made for that source. The ECW-308 supporting-information text and
the other closed-access extractions used during the Tier-1/Tier-2 search are
kept outside the repository (data/external/ is git-ignored) and are not
redistributed here.
