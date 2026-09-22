# P4 Redox Runbook

## Purpose

`probes/p4_redox_baseline.py` builds a provenance-preserving redox table and
evaluates three fixed baselines on RX-392. It does not train a new production
model and does not impute redox targets for Batt-P30K.

## Inputs

- `data/external/Batt-SLM-RX-392.csv`, pinned to Batt-SLM commit
  `a5101e30c6975552d97e34f1e93461126715c862`.
- `data/raw/batt/Batt-P30K.h5`.
- The 308-solvent ECW target is unavailable and represented only in summary
  status.

## Rebuild

```powershell
.\.venv\Scripts\python.exe probes\p4_redox_baseline.py
.\.venv\Scripts\python.exe scripts\verify_p4_redox.py
```

The notebook `probes/p4_redox_baseline.ipynb` reads the merged table and summary
and checks split, metrics, units, and 308 status.

## Parsing Contract

RX rows are split on `$`; the selected property dictionaries are split on `&`
and `:`. Exactly one `DIELECTRIC=18` value is required for each of IP, raw EA,
oxidation potential, and reduction potential. The output formulas follow the
upstream `redox_free_ener.py`, including `EA = -raw_EA` and the 4.44 eV
reference shift.

## Outputs

- `data/processed/redox_merged.csv`
- `data/processed/p4_redox_predictions.csv`
- `probes/p4_redox_summary.json`
- `probes/artifacts/p4_redox_linear.png`
- `probes/artifacts/p4_redox_parity.png`
- `reports/p4_redox_baseline.md`

## Interpretation Boundary

Target models operate on redox free energy in eV. The gate threshold is
`0.15 eV`, and both targets currently fail. Batt-P30K rows retain source-native
IP/EA/HOMO/LUMO/dipole fields but leave the two redox free-energy columns blank.
