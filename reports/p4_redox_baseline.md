# P4 Redox Baseline

## Scope and provenance

This probe evaluates simple redox free-energy models using the pinned
Batt-SLM commit `a5101e30c6975552d97e34f1e93461126715c862`.

- `data/external/Batt-SLM-RX-392.csv`: 248,404 bytes, SHA256
  `d30ec1ffccba15538bac0b67157c14e045f1721441be23837c6195eca24a5d87`,
  392 data rows.
- `data/raw/batt/Batt-P30K.h5`: 29,519 molecules with IP, EA, HOMO, LUMO,
  and dipole fields.
- Source DOI: `10.1021/acsnano.6c06255`.
- The 308-solvent ECW target remains unavailable and contributes zero rows.

The RX parser follows the upstream
`Redox-Pot/Redox-Ener/redox_free_ener.py`: only `DIELECTRIC=18` conditions are
selected. The formulas are:

```text
EA = -raw_EA
oxidation_free_energy = oxidation_potential + 4.44
reduction_free_energy = -(reduction_potential + 4.44)
```

## Unit convention

The upstream script labels IP, EA, and redox free energies in `eV`. The 4.44
V reference potential is therefore applied as 4.44 eV in the electron
free-energy convention. The gate threshold `0.15` is evaluated in eV on the
free-energy targets. It is not described as a separate volts-to-eV conversion.

## Merged dataset

`data/processed/redox_merged.csv` contains 29,911 rows:

| Source | Rows | Redox free-energy targets |
| --- | ---: | --- |
| RX-392 | 392 | oxidation and reduction free energy |
| Batt-P30K | 29,519 | blank; only source-native IP/EA/HOMO/LUMO/dipole |

P30K rows are not assigned imputed redox free energies. Its HDF5
`dipole` vectors are reduced to their Euclidean magnitude; the magnitude is
retained in source HDF5 units and is not used by these models.

## Models and split

The fixed split is an 80/20 deterministic permutation, seed 42:
314 train and 78 test rows. Test ID hash:
`dba15cd8c3a99215cc3e1fd5b2a73b9a5c0275eb2ee41fba436bcf62f2d2daee`.

The three fixed baselines are:

- Linear regression: IP to oxidation free energy and EA to reduction free
  energy.
- Scalar GPR: the same one-dimensional feature, StandardScaler, and a fixed
  RBF plus white-noise kernel.
- Fingerprint GPR: Morgan count fingerprint radius 2, 2048 bits, with the
  existing fixed dielectric-GPR kernel configuration.

No hyperparameters were selected using the held-out test metrics.

## Held-Out Metrics

All values are in eV.

| Target | Model | MAE | RMSE | R2 |
| --- | --- | ---: | ---: | ---: |
| Oxidation free energy | Linear | 0.290518 | 0.379072 | 0.944316 |
| Oxidation free energy | Scalar GPR | 0.292735 | 0.383648 | 0.942964 |
| Oxidation free energy | Fingerprint GPR | 0.693011 | 1.051656 | 0.571421 |
| Reduction free energy | Linear | 0.415337 | 0.659711 | 0.735089 |
| Reduction free energy | Scalar GPR | 0.409624 | 0.653855 | 0.739771 |
| Reduction free energy | Fingerprint GPR | 0.669877 | 0.892811 | 0.514810 |

The best oxidation model has MAE `0.290518 eV`; the best reduction model has
MAE `0.409624 eV`. The requested gate is `MAE < 0.15 eV`, so the gate fails for
both targets. The higher R2 values should not be presented as a gate pass.

The fingerprint GPR performs substantially worse than the scalar models. This
supports treating the 1D IP/EA mapping as the useful signal for RX-392 while
not claiming that molecular fingerprint transfer is established.

## Limitations

- RX-392 is a small 392-molecule DFT-derived set.
- Batt-P30K adds coverage but no redox free-energy labels.
- The unavailable 308-solvent ECW set is not represented by fabricated rows.
- These are in-silico targets, not experimental redox measurements.
- No claim is made that the `0.15 eV` gate has been reached.

Artifacts:

- `data/processed/redox_merged.csv`
- `data/processed/p4_redox_predictions.csv`
- `probes/p4_redox_summary.json`
- `probes/artifacts/p4_redox_linear.png`
- `probes/artifacts/p4_redox_parity.png`
- `probes/p4_redox_baseline.ipynb`
