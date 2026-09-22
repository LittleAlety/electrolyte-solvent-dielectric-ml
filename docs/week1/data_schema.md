# Unified Data Schema

The shared row schema for multi-property electrolyte-solvent work is:

```text
inchikey, smiles, T_K, dielectric, viscosity_Pa_s, density, source_doi, gate_flags
```

## Units and semantics

- `inchikey`: standard InChIKey used as the molecule match key.
- `smiles`: RDKit isomeric canonical SMILES.
- `T_K`: thermodynamic temperature in kelvin.
- `dielectric`: relative permittivity, dimensionless.
- `viscosity_Pa_s`: dynamic viscosity in pascal seconds.
- `density`: density in kg/m3, not g/cm3.
- `source_doi`: citation DOI or an explicitly labeled historical source.
- `gate_flags`: pipe-delimited machine-readable labels.

Missing values are empty fields in CSV, not zero. Derived predictions must keep
an explicit `predicted` flag and must not be mixed into experimental raw rows.

## Matching and pairing

- Join dielectric and viscosity rows by exact InChIKey.
- Prefer pure-component dielectric rows when the same InChIKey also occurs in
  mixture data.
- Temperature pairing uses minimum `abs(T_viscosity - T_dielectric)` within the
  selected window; the Week 1 closure uses 298.15 K +/- 5 K.
- The current dielectric-viscosity table is a `pair_type=loose_join` coverage
  and exploration artifact with `model_ready=false`. It is not a joint-training
  table because the two properties were not observed in one exact row.
- A loose two-table join is evidence of coverage, not automatically a
  model-ready dual-label row. Prefer a dual-label table at matched temperatures
  or explicitly model each property over temperature.

## Gate flags

Allowed labels are:

```text
historical_fallback_target
target_308_unavailable
not_found
missing_viscosity
not_training_ready
zero_frequency
frequency_dependent
pure_component
mixture_only
experimental
predicted
temperature_delta_le_5K
temperature_delta_gt_5K
temperature_gate
exclude_liquid_298K
dipole_units_unreported
r2_gate_failed
```

The executable enum lives in `src/electrolyte_ml/standardize.py`.
