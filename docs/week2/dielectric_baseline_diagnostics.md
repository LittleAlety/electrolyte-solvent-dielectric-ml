# Dielectric Baseline Diagnostics

The diagnostic evidence package extends the original Morgan+GPR baseline without
replacing its seed-42 held-out metrics.

Artifacts:

- `data/processed/dielectric_baseline_comparison.csv`: DummyMean,
  SizeOnlyRidge, and MorganRBFGPR on the original 80/20 split.
- `data/processed/dielectric_gpr_repeated_cv.csv`: 5-fold, 10-repeat metrics
  for all three models.
- `data/processed/dielectric_learning_curve.csv`: fixed-test learning-curve
  runs at train sizes 20/40/60/80.
- `probes/dielectric_baseline_diagnostics_summary.json`: metrics, CV and
  learning-curve summaries, descriptor quick test, input/split hashes, and
  configurations.
- `probes/artifacts/dielectric_baseline_comparison.png` and
  `dielectric_learning_curve.png`.

Rebuild and verify:

```powershell
python probes/dielectric_baseline_diagnostics.py
python scripts/verify_dielectric_baseline_diagnostics.py
```

The current descriptor quick test improves R2 from `0.23126` to `0.38059`, but
the original gate remains failed and repeated CV remains highly variable.
