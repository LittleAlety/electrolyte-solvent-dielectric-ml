# ThermoML Week 0 Batch Audit

Generated from the first five matches for the NIST API query
`type:TRCTml4 AND dielectric`.

## Summary

| Metric | Value |
|---|---:|
| Candidate XML documents downloaded | 5 |
| Documents with dielectric rows | 4 |
| Dielectric candidate rows | 625 |
| Primary compounds (InChIKey) | 18 |
| Static/zero-frequency rows | 578 |
| Frequency-dependent rows | 47 |
| Frequency metadata | 385 MHz on all 47 frequency-dependent rows |
| Rows with uncertainty | 625 |
| Rows missing temperature | 133 |
| Parse errors | 0 |

The batch is intentionally not deduplicated and no unit conversion is
performed. The 47 frequency-dependent rows are not interchangeable with the
578 static/low-frequency rows and must remain a separate target.

## Files

- `data/raw/thermoml/`: original XML and `.meta.json` provenance sidecars;
  ignored by Git.
- `data/processed/thermoml_normalized.csv`: tracked candidate rows.
- `data/processed/thermoml_normalized.provenance.json`: tracked source
  checksums, retrieval times, row counts, filter, and parse errors.

## Known limitations

1. The file name and API query are discovery filters, not proof that every
   property is a pure-solvent dielectric constant.
2. Rows with missing temperature require manual review before modeling.
3. Aqueous, mixed-gas, and other multicomponent records must not be silently
   merged with pure organic solvents.
4. Composition values are retained when explicitly represented by the source.
   The second component of a binary mixture may be implied by mass balance.
5. No duplicate resolution, outlier detection, structure curation, or
   Clausius-Mossotti cross-check has been performed yet.
6. A malformed source file now prevents normalized outputs from being
   overwritten unless `--allow-partial` is explicitly supplied.

## Regenerate

```powershell
python scripts/fetch_thermoml.py `
  --query "type:TRCTml4 AND dielectric" `
  --limit 5

python scripts/normalize_thermoml.py --dielectric-only
python scripts/verify_week0.py
```
