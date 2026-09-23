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
