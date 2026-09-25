# Manual Dielectric Entry Schema

Use this schema for the human literature/handbook pass that may create
`data/dielectric_v02.csv`. The schema is for manual transcription and
verification; it does not authorize redistribution of closed-source material.

## Required row fields

```text
row_id
compound_name
smiles
inchikey
canonical_structure_verified
T_K
temperature_source
phase
pure_component
frequency_MHz
frequency_type
dielectric
uncertainty_value
uncertainty_kind
confidence_level
source_type
source_doi
source_url
source_citation
source_page_or_table
source_record_id
retrieved_at
manual_transcriber
review_status
closed_source
non_redistributable
redistribution_status
gate_flags
notes
```

## Field rules

- `inchikey` and canonical `smiles` are mandatory. `canonical_structure_verified`
  must be `true`; otherwise the row is `awaiting_manual_review`.
- `T_K` is in kelvin. The v0.2 target window is `293.15-303.15 K`.
  The v0.3 revision keeps that window as `temperature_band =
  room_temperature` and adds exactly one explicitly enumerated extended
  window, `313.15-323.15 K` (`temperature_band = extended_temperature`),
  reserved for compounds that cannot be measured as a liquid inside the
  primary window. v0.3 uses it for ethylene carbonate (m.p. about 36.4 C)
  only; no other compound may take the extended band.
- `pure_component` must be `true`; mixture rows are not eligible for v0.2.
- `frequency_type` must be `zero_frequency` or an explicitly justified
  `static_low_frequency` protocol. Frequency-dependent values remain separate.
- `dielectric` is dimensionless. Preserve `uncertainty_kind` as one of
  `standard`, `expanded`, `relative`, or `not_reported`.
- `source_page_or_table` and `source_record_id` are required for traceability.
- `closed_source=true` means the source is login-, subscription-, or
  license-restricted.
- `non_redistributable=true` means raw source text or exported tables must not
  be committed. Keep a local pointer/hash instead of redistributing content.
- `redistribution_status` must be `allowed`, `prohibited`, or `unclear`.
  `unclear` is treated as non-redistributable until resolved.
- Closed-source rows may support local model development only when the user has
  lawful access and the derived record's release status is explicitly recorded.

## Workflow

1. Search the AL Top30/longlist and secondary sources for candidate compounds.
2. Verify the original table, page, units, temperature, phase, and frequency.
3. Record the row with all required fields.
4. Run the structure and unit checks before promoting the row to v0.2.
5. Do not fill missing temperature, phase, or frequency by assumption.
6. Do not promote new rows into `data/dielectric_v02.csv` until the promoted
   row count remains at least 200 and the provenance checks pass. The current
   v0.2 file is built from the open NBS Circular 514 additions and remains
   independently verified.

## Closed-source marker example

```text
closed_source=true
non_redistributable=true
redistribution_status=unclear
source_type=subscription_handbook
```

This is a schema example only. No measured value is created or inferred by this
document.
