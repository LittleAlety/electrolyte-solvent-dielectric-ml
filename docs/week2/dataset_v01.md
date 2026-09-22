# Dataset v0.1

## Files

- `data/dielectric_v01.csv`: compound-level dielectric training table.
- `data/viscosity_v01.csv`: experimental viscosity table, one measurement per row.
- `data/processed/dielectric_v01_observations.csv`: observation-level source
  audit table for P1 and Chodera 2015.
- `data/processed/dataset_v01_summary.json`: row counts, ranges, source counts,
  overlap facts, and exclusion policy.

## Units

- `T_K`: kelvin.
- `dielectric`: dimensionless relative permittivity.
- `viscosity_Pa_s`: pascal seconds, computed exactly as `cP * 1e-3`.
- `density`: kg/m3. It remains empty in v0.1 because Chew `MD_density` is a
  molecular-dynamics value, not an experimental measurement.

## Dielectric Construction

The compound-level table includes only P1 ThermoML observations satisfying:

```text
property_family = zero_frequency
is_pure = true
293.15 K <= T_K <= 303.15 K
```

The current selection contains 460 observations and 100 unique InChIKeys.
Canonical SMILES are derived from each ThermoML standard InChI. Missing or
unparseable InChI values raise an error and are never silently dropped.
Every observation retains `source_sha256` and `source_size_bytes`; the verifier
recomputes both from the raw source when it is present locally.

The dielectric value is the median value inside the window. `T_K` is the median
observation temperature, and `n_observations` is the number of P1 observations
for that InChIKey.

Uncertainty fields are not mixed blindly. `uncertainty_value`,
`uncertainty_kind`, and `confidence_level` are retained when the observations
share one kind and confidence level; the unified value is the median of all
available uncertainty values. Mixed kinds leave the unified `uncertainty` field
empty, set `uncertainty_kind=mixed`, and preserve all unique uncertainty
signatures in `uncertainty_json`.

## Chodera 2015 Cross-check

All 246 Chodera rows and 45 unique keys are retained in
`dielectric_v01_observations.csv` with
`selection_status=historical_crosscheck_only`. They do not add independent
molecules to v0.1:

- P1 keys: 100
- Chodera keys: 45
- Overlap: 45
- Chodera additions: 0
- Compound-level union: 100, not 145

If an InChIKey has a Chodera cross-check, `source_dois_all` includes
`arXiv:1506.00262`; the main value still comes only from the P1 window median.

## Viscosity Construction

Only Chew 2024 supplement 2 experimental rows enter `viscosity_v01.csv`
(3,582 rows, 957 unique InChIKeys). Supplement 3 contains 650 predictions and
is explicitly excluded. Every viscosity row has
`data_status=experimental` and `source_scope=chew_2024_supp2_experimental_viscosity`.

The existing 456-row loose dielectric-viscosity join is not merged into either
v0.1 table and remains `model_ready=false`.

## Rebuild

```powershell
python scripts/build_dataset_v01.py
python scripts/verify_dataset_v01.py
```

The builder is deterministic and reads only P1, Chodera, Chew supplement 2,
Chew supplement 3 for exclusion accounting, and the P3 intersection summary.
