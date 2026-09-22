# Decisions Log

## 2026-09-22: Week 1 remains provisional

- Decision: use the `dielectric_viscosity_joint` path provisionally.
- Evidence: the live NIST fallback contains 205 XML files, 91 dielectric source
  documents, and 11,646 observations. Near 298.15 K +/- 5 K there are 124
  all-component zero-frequency compounds but only 100 pure-component gate
  compounds.
- Limitation: the complete 189 MB ThermoML 2020 archive remained unavailable.
  `handbook_gate_executed=false` and `decision_status=provisional`.
- Spot check: water, acetonitrile at 1 MHz, sulfolane, DMC, and methanol pass.
  Propylene carbonate is `not_found` against the current fallback and keeps the
  manual reference 64.9. Ethylene carbonate is a blocked temperature-gate guard
  because it is not treated as a liquid pure solvent near 298 K.

## 2026-09-22: The 308-solvent ECW target is unavailable

- DOI: `10.1002/adfm.202212342`.
- Crossref, OpenAlex, Unpaywall, and DataCite expose no open machine-readable
  dataset relationship.
- Wiley returns HTTP 403 with a Cloudflare challenge; the ANSTO record contains
  metadata only.
- Decision: `target_308_available=false`. No 308-row list was fabricated.
  `coverage_gap.csv` uses Chodera 2015 as an explicit historical fallback:
  246 rows and 45 unique InChIKeys.

## 2026-09-22: Viscosity source and limits

- Correct DOI: `10.1186/s13321-024-00820-5`.
- Chew supplement 2 contains 3,582 experimental rows and 957 unique canonical
  SMILES after RDKit standardization.
- Supplement 3 contains 650 model predictions for 50 solvents and is stored
  separately with `data_status=predicted`.
- The paper's 4,440-row source dataset is not fully public because the remaining
  records were withheld for copyright reasons.

## 2026-09-22: Dielectric-viscosity intersection

- Matching uses exact InChIKey and prefers pure-component dielectric rows.
- Near 298.15 K +/- 5 K, 62 InChIKeys have both properties somewhere in the two
  tables: 51 pure-component keys and 11 mixture-only keys.
- The <=5 K temperature rule leaves 46 temperature-paired InChIKeys and 456
  paired rows across 366 unique P1 dielectric rows.
- Every exported row is marked `pair_type=loose_join`,
  `model_ready=false`, and `not_training_ready`.
- Decision: use this intersection for coverage and exploration only. Before
  joint modeling, prefer a dual-label single table at matched temperatures or
  include an explicit temperature model.

## 2026-09-22: P2 failure diagnosed

- Batt-P30K SHA256:
  `587f1490613a008b91f45ee9de607a2e057c88c301fa9e5c9d7785b1968d118d`.
- Dataset: 29,519 groups and 0 invalid SMILES.
- Morgan count fingerprint radius 2, 2048 bits, plus XGBoost.
- Unit: PiNN source/docs and Batt-SLM `params.yml` establish high-confidence
  atomic-unit semantics for the dipole target; HDF5 itself has no unit metadata.
  Final MAE/RMSE are `0.3601/0.4896 a.u.` or `0.9152/1.2444 D`.
- Dummy R2 is `-0.0000026`; MW+heavy-atom Ridge R2 is `0.00679`;
  Morgan+XGBoost R2 remains `0.56365`, below 0.8.
- The diagnostic independently retrains Morgan+XGBoost and audits it against the
  formal metrics. Maximum absolute differences are MAE `4.73e-8`,
  RMSE `7.47e-9`, and R2 `3.92e-9`, below the `1e-7` numerical tolerance.
- Only `4.24%` of targets are below `1 D`, so near-zero target compression is
  not the primary explanation for the R2 result.
- Decision: the pipeline is GREEN but the model gate is FAILED. The evidence
  supports insufficient 3D/conformational representation rather than a unit
  mismatch or simple code bug. Move next to Chemprop/D-MPNN or a 3D/GNN.

## 2026-09-23: Dielectric GPR is a weak starting baseline

- Input: `data/dielectric_v01.csv`, 100 unique P1 compound keys. The 45
  Chodera keys all overlap P1 and add no independent compounds.
- Fixed model: Morgan count fingerprint radius 2/2048 bits, StandardScaler,
  GaussianProcessRegressor with deterministic 80/20 split, seed 42.
- Final kernel: `2.16**2 * RBF(length_scale=42.4) + WhiteKernel(noise_level=0.278)`.
- Test metrics: MAE `11.5345014`, RMSE `21.0820913`, R2 `0.2312574`.
- Posterior uncertainty: mean std `18.3566`; 95% empirical coverage `19/20`.
- Decision: this is an active-learning starting point, not a finished model.
  The R2 gate fails, and no Week3/P4 work is started from this result.

## 2026-09-23: Dielectric baseline diagnostics

- Original 80/20 GPR metrics remain unchanged: MAE `11.5345`, RMSE `21.0821`,
  R2 `0.23126`.
- Same-split controls: Dummy R2 `-0.01811`; MW+heavy-atom Ridge R2 `0.03728`.
- Repeated 5-fold/10-repeat CV: MorganRBFGPR R2 `0.02295 +/- 0.68149`, showing
  weak and highly variable performance across folds.
- The fixed-test learning curve is noisy; the full 80-row training subset was
  best in this experiment.
- Descriptor augmentation quick test reaches R2 `0.38059`, MAE `10.1514`, and
  RMSE `18.9240`. This is evidence for a future representation upgrade, not a
  gate pass or finalized model.

## 2026-09-23: Chodera cross-check and high-temperature extension

- Chodera cross-check includes all 45 common InChIKeys. Median absolute median
  difference is `0.175`; maximum is `7.341` for N-methylacetamide.
- Nearest-temperature pairing uses observed pairs only, with no interpolation.
  Forty-four keys are near-isothermal, where temperature cannot explain the
  observed difference. One key has a `10.05 K` gap where temperature may
  contribute, but this is not proven without a temperature model.
- The high-temperature NIST window `313.15-323.15 K` contains 205 observations
  and 46 keys.
- Ethylene carbonate is added only as a manual literature point: `313.15 K`,
  `90.5`, `1 MHz`, DOI `10.1021/je050341y`, `<1.5% relative` uncertainty.
  It remains `frequency_dependent`, single-source, and absent from main v0.1.
- Decision: keep the main v0.1 table unchanged; the extension contains 47 keys
  and 206 observations as supplemental evidence.

## 2026-09-23: Dielectric kernel comparison

- Tanimoto-GPR, RBF-GPR, and XGBoost were evaluated on the same 10x5 repeated
  CV split.
- Mean R2: Tanimoto `0.04246 +/- 0.81976`, RBF `0.02295 +/- 0.68149`,
  XGBoost `0.03185 +/- 0.54243`.
- Tanimoto improves mean R2 over RBF by only `0.01950`, with the best MAE and
  RMSE among the three models.
- Decision: the modest improvement does not pass the `0.8` gate and does not
  justify further kernel hyperparameter tuning. Inspect fold-level failures
  and representation/data limits next.

## 2026-09-23: Viscosity strong baseline

- Input: 3,582 experimental viscosity rows and 957 unique InChIKeys.
- Target: `log10(viscosity_cP)`; features are Morgan count 2048 plus `T_K` and
  `1000/T_K`.
- Random-row XGBoost: MAE `0.06357`, RMSE `0.11868`, R2 `0.93689`; passes the
  log10(cP) MAE `0.15` gate.
- Group-holdout XGBoost: MAE `0.17477`, RMSE `0.24407`, R2 `0.74813`; fails
  the same gate.
- Decision: random-row success primarily reflects temperature interpolation
  within known molecules. The group-holdout result is the relevant limitation
  for screening unseen molecules; no tuning is performed this round.

## 2026-09-23: AL Round-1 shortlist

- Inputs are pinned to Batt-SLM commit
  `a5101e30c6975552d97e34f1e93461126715c862`; Batt-SLM SHA256 is
  `c2ec78256ce6189366aebd9f7f0403e669c963e911cf51f7732083bce6374a1d`.
- The 115,756-row pool yields 85,921 safe candidates after excluding 27 keys
  present in dielectric v0.1 and 29,808 structures matching the versioned
  `al_round1_hazard_v4` SMARTS rules. The thiocarbonyl flag uses both the
  ordinary `[CX3]=[SX1]` rule and the complete `[#6]=[#16]` motif; the real
  cumulated SMILES `C1=S=C=C2OCCOC=12` is excluded.
- Acquisition is `std_percentile * novelty`; all 300 longlist rows are Tier A/B.
  Hard family quota 6 without an all-remaining fallback selected 20 A/B rows,
  then 10 Tier C rows were added as continuation candidates.
- The deterministic MaxMin Top 30 contains 6 Cyclic Carbonates, 6 Ethers,
  6 Formates, 5 Sulfones/Sulfoxides, 3 Ketones, 2 Nitriles, 1 Other Ester, and
  1 Linear Carbonate. Tiers are A 6, B 14, and C 10. Every family count is at
  most 6.
- Polyhalogenated alkyl structures that do not match a hard rule are retained
  with `manual_review_warnings=polyhalogenated_alkyl`: 10,602 safe candidates
  and 9 final Top 30 rows. The field `model_sha256` is renamed
  `model_input_sha256` to avoid implying that the hash is a serialized model
  artifact.
- Decision: keep all 30 as `awaiting_manual_review`. They are not confirmed as
  available, room-temperature liquids, or experimental dielectric references.
  The unavailable 308-solvent ECW list was not used as a candidate pool.
