# Dielectric GPR Baseline Notes

The baseline consumes only `data/dielectric_v01.csv`, containing 100 unique P1
compound keys. Chodera's 45 keys are historical cross-checks and are entirely
overlapped by P1; they do not create a 145-compound dataset.

Input integrity uses a canonical UTF-8/LF text SHA256. CRLF and LF representations
of the same text therefore verify identically on Windows and Linux.

Artifacts:

- `probes/dielectric_gpr_baseline.py`: reproducible model and split.
- `data/processed/dielectric_gpr_test_predictions.csv`: 100 posterior rows,
  with 20 held-out rows marked `used_for_metrics=true`.
- `probes/dielectric_gpr_summary.json`: metrics, coverage, kernel, split IDs,
  input hash, and posterior uncertainty.
- `probes/artifacts/dielectric_gpr_parity.png`: test parity with
  `+/-1.96*std` intervals.
- `reports/dielectric_gpr_baseline.md`: interpretation and limitations.

Rebuild and verify:

```powershell
python probes/dielectric_gpr_baseline.py
python scripts/verify_dielectric_gpr_baseline.py
```

The current result is a weak but honest starting baseline. It must not be
treated as a deployable model or as a replacement for the planned active
learning loop.

Additional diagnostics compare DummyMean, MW+heavy-atom Ridge, and MorganRBFGPR
on the same split, run 5-fold/10-repeat CV, measure a fixed-test learning curve,
and perform one descriptor-augmentation quick test. See
`docs/week2/dielectric_baseline_diagnostics.md`.
