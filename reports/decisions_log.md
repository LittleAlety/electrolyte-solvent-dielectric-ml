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

## 2026-09-22: P2 baseline does not pass

- Batt-P30K SHA256:
  `587f1490613a008b91f45ee9de607a2e057c88c301fa9e5c9d7785b1968d118d`.
- Dataset: 29,519 groups and 0 invalid SMILES.
- Morgan count fingerprint radius 2, 2048 bits, plus XGBoost.
- Final test metrics: MAE `0.360058308`, RMSE `0.489559393`, R2
  `0.563648641`.
- `pass_r2_gt_0_8=false`. The dipole vector unit is not declared by the source.
- Decision: do not hide this negative result. Morgan count plus XGBoost is
  insufficient. The next model step is descriptor-augmented features, a
  3D/GNN representation, or D-MPNN rather than deeper Morgan+XGBoost tuning.
