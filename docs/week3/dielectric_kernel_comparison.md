# Dielectric Kernel Comparison

This comparison evaluates three models on the same 10-repeat, 5-fold split of
the 100-compound dielectric v0.1 dataset:

- Tanimoto-GPR on binary Morgan fingerprints.
- RBF-GPR on count Morgan fingerprints.
- XGBoost on count Morgan fingerprints.

Artifacts:

- `data/processed/dielectric_kernel_comparison.csv`
- `probes/dielectric_kernel_comparison_summary.json`
- `probes/artifacts/dielectric_kernel_comparison.png`
- `reports/dielectric_kernel_comparison.md`

Rebuild and verify:

```powershell
python probes/dielectric_kernel_comparison.py
python scripts/verify_dielectric_kernel_comparison.py
```

Tanimoto gives a small improvement over RBF, but the result remains far below
the `0.8` R2 gate and does not support further kernel tuning.
