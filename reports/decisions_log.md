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
