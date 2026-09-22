# Week 1 Probe Runbook

Week 1 follows the P0 and P1 probes from `执行手册_探针与周计划.md`.

## P0: Environment And Fingerprints

Run `notebooks/00_sanity_check.ipynb`. It parses ethylene carbonate, computes a
Morgan fingerprint, and writes `probes/artifacts/p0_ec_molecule.png`.

## P1: Dielectric Data Census

The preferred input is the checksum-pinned 2020 ThermoML archive. The NIST
bulk endpoint returned repeated HTTP 504 responses during this run, so the
executed fallback used the live NIST API union:

```powershell
python scripts/fetch_thermoml.py `
  --query "type:TRCTml4 AND dielectric" `
  --limit 93

python scripts/fetch_thermoml.py `
  --query "type:TRCTml4 AND permittivity" `
  --limit 117

python probes/p1_thermoml_dielectric.py
```

The extractor uses `thermoml-io` to parse each XML document and writes:

- `data/processed/dielectric_raw.csv`
- `probes/p1_summary.json`
- `probes/artifacts/dielectric_distribution.png`
- `probes/artifacts/family_coverage.png`
- `probes/p1_eda.ipynb`

## Result

The live API fallback contains 11,646 dielectric observations from 91
documents. Near 298.15 K +/- 5 K, the all-component zero-frequency census has
124 unique compounds. The formal gate population is narrower: 100 unique
compounds occur in pure-component zero-frequency observations, and mixture
partners do not enter the gate.

The handbook gate was not formally executed because the complete checksum-
pinned 2020 archive could not be downloaded. Applying the handbook thresholds
to the fallback census therefore gives only the provisional decision
`dielectric_viscosity_joint`, not `mainline_go`. The source mode remains
`individual_xml_fallback`; the machine-readable summary records
`decision_status: provisional`, `handbook_gate_executed: false`, and the
archive limitation.

## Closure

Run the reproducible closure builder after the P1 extraction:

```powershell
python scripts/build_week1_closure.py
python scripts/verify_week1.py
```

It generates:

- `data/processed/thermoml_source_manifest.csv` with 205 verified XML sources.
- `data/processed/p1_spot_check.csv` with five passing anchors, PC as
  `not_found`, and an EC temperature-gate guard.
- `data/processed/coverage_gap.csv` and
  `data/processed/coverage_gap_summary.json`. The requested 308-solvent ECW
  target is explicitly unavailable; Chodera 2015 is a 246-row historical
  fallback with 45 unique InChIKeys.
- `data/processed/viscosity_raw.csv` with 3,582 experimental rows from Chew
  supplement 2.
- `data/processed/viscosity_predictions.csv` with 650 predicted rows from
  supplement 3, kept separate from experimental data.
- `data/processed/dielectric_viscosity_intersection.csv` and
  `probes/p3_viscosity_summary.json`.

The current compound-level intersection contains 62 InChIKeys. After applying
the <=5 K pairing rule, 46 keys produce 456 paired rows. This is a loose
two-table join (`model_ready=false`); use a dual-label table at matched
temperatures or an explicit temperature model before joint modeling.

## P2 Diagnostics

`probes/p2_diagnostics.py` and the executed `probes/p2_diagnostics.ipynb` resolve
the Batt-P30K dipole unit from PiNN source-code evidence, quantify the Debye
target distribution, recompute stratified held-out errors, and compare Dummy,
MW+heavy-atom Ridge, and Morgan+XGBoost under the same 80/20 split.

The R2 gate remains failed. The diagnostic artifacts are
`probes/p2_diagnostics_summary.json`,
`data/processed/p2_diagnostics.csv`, and the two `p2_*` diagnostic plots.

## Export

```powershell
python probes/export_week1_results.py
```

Important artifacts are copied to:

```text
E:\Claude Code\电解质ML\成果输出\week1
```
