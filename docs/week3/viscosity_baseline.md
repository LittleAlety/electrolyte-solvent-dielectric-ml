# Viscosity Baseline

Input: `data/viscosity_v01.csv`, 3,582 experimental measurements and 957
unique InChIKeys. Target: `log10(viscosity_cP)`.

Artifacts:

- `data/processed/viscosity_baseline_predictions.csv`
- `probes/viscosity_baseline_summary.json`
- `probes/artifacts/viscosity_baseline_parity.png`
- `reports/viscosity_baseline.md`

Models use Morgan count radius 2/2048 plus `T_K` and `1000/T_K`, with DummyMean,
T-only Ridge, and fixed XGBoost controls.

Two split modes are retained:

- random row 80/20 seed 42;
- group holdout by InChIKey 80/20 seed 42.

Rebuild and verify:

```powershell
python probes/viscosity_baseline.py
python scripts/verify_viscosity_baseline.py
```

Random-row XGBoost passes the log10(cP) MAE gate, but group-holdout XGBoost
does not. The gap distinguishes temperature interpolation within known
molecules from generalization to unseen molecules.
