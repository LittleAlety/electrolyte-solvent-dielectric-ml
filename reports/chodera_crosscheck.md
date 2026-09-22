# Chodera/P1 Dielectric Cross-check

## Scope

The table contains 45 common InChIKeys present in both P1 ThermoML
observations and the Chodera 2015 historical table. Chodera adds no independent
compounds: the v0.1 compound-level union remains 100, not 145.

Nearest-temperature pairing uses observed rows only. No interpolation or
temperature model is used.

## Summary

- Common keys: 45
- Median absolute median difference: 0.175
- Maximum absolute median difference: 7.341
- Pair temperature gap: min 0.00 K, median 0.05 K, max 10.05 K
- Near-isothermal keys: 44
- Keys with a temperature gap >=1 K: 1

The largest median difference is N-methylacetamide, with
`Chodera - P1 = -7.341`. Its nearest-temperature gap is only 0.05 K, so
temperature cannot explain that discrepancy.

The only pair with a temperature gap >=1 K is
`LVTYICIALWPMFW-UHFFFAOYSA-N`
(N-(2-hydroxypropyl)-2-hydroxy-1-propanamine), with `DeltaT=10.05 K` and median
difference `-0.38`. Temperature may contribute there, but the current table
contains no interpolation or fitted temperature slope that proves it.

No disagreement is attributed to measurement method without direct source
evidence.

## Top Differences

The ten largest absolute median differences are recorded in
`probes/chodera_crosscheck_summary.json`. They include
N-methylacetamide, 1,2-propanediol, sulfolane, triethanolamine,
N,N-dimethylethanamide, diethanolamine, water, N-methyldiethanolamine,
2-ethyl-1-hexanol, and ethanol.

## Files

- `data/processed/chodera_crosscheck.csv`
- `probes/chodera_crosscheck_summary.json`
- `probes/artifacts/chodera_crosscheck.png`
