# ThermoML Acquisition and Parsing Runbook

## Scope

This runbook covers the Week 0 ThermoML path:

- discover candidate records through the public NIST ThermoML API;
- download and preserve original XML files;
- record URL, retrieval time, SHA256, byte count, ETag, and Last-Modified;
- parse ThermoML with the Python standard library; and
- write a stable CSV schema plus provenance JSON without changing units or
  removing duplicates.

The first-stage acceptance target is a working, reproducible path with real
examples. The longer-term target is 100-300 dielectric-constant records.

## Format Notes

ThermoML is an XML/IUPAC format rooted at `DataReport`. NIST files use the
namespace `http://www.iupac.org/namespaces/ThermoML`.

The parser reads:

- citation metadata such as DOI and title;
- `PureOrMixtureData`, `Property`, `Variable`, `Constraint`, and `NumValues`;
- root-level `Compound` records referenced by each data set, including common
  names, molecular formula, standard InChI, InChIKey, and composition values;
- `ePropName`, `nPropValue`, `nPropDigits`, and uncertainty values;
- temperature and frequency variables or constraints, including their
  original units;
- property phase and method metadata; and
- every variable and constraint in compact JSON columns.

ThermoML usually encodes a property unit in the controlled `ePropName` text,
for example `Speed of sound, m/s`. Dimensionless names such as
`Relative permittivity at zero frequency` have no unit suffix. The parser
keeps the original property name unchanged and records the suffix in
`property_unit`; it does not invent a unit and does not convert values.

## Real NIST Evidence

A real public NIST XML sample was retrieved on 2026-09-22 (HTTP response dated
`Tue, 22 Sep 2026 03:02:16 GMT`):

- Source: https://trc.nist.gov/ThermoML/10.1021/je600515j.xml
- DOI: `10.1021/je600515j`
- Title: "Dielectric Constants of Aqueous Diisopropanolamine, Diethanolamine,
  N-Methyldiethanolamine, Triethanolamine, and 2-Amino-2-methyl-1-propanol
  Solutions"
- Bytes: `133963`
- SHA256:
  `901354EC9C34EADA3FF170F489ED27F108F2B6F7FA42D9FD2533454306A96BD0`
- Property example: `Relative permittivity at zero frequency`
- Method example: `dielectric analyzer`

The same source was downloaded again through the corrected Python path and
normalized into the ignored `data/raw/` directory and the tracked
`data/processed/` batch. After expanding to the first five API matches, the
dielectric-only table contains 625 rows from four source documents, covering
18 primary compounds and 578 static/zero-frequency plus 47 frequency-dependent
values. All rows retain an uncertainty field, but 133 rows have no parsed
temperature variable. See `data_summary.md` for the batch audit and
limitations.

The NIST metadata API query `type:TRCTml4 AND dielectric` returned 93
candidate records during this work. This establishes that the archive has a
usable real candidate pool, but it does not claim that all 93 contain a
primary dielectric-constant property.

The Python API query initially received HTTP 403 from the NIST/Cloudflare edge
because it used the default Python User-Agent. The API and XML requests now
send a project User-Agent and the corrected Python path successfully
downloaded both the sample above and additional matching articles. The current
Week 0 batch therefore exceeds the 100-row acceptance target; it is still a
non-deduplicated candidate batch rather than the final v1.0 dataset.

## Commands

Run from the repository root in PowerShell:

```powershell
# Show planned matches without writing files.
python scripts/fetch_thermoml.py --query "type:TRCTml4 AND dielectric" --limit 10 --dry-run

# Download the 93 candidate XML files and .meta.json sidecars.
python scripts/fetch_thermoml.py --query "type:TRCTml4 AND dielectric" --limit 93

# Download one known record.
python scripts/fetch_thermoml.py --doi "10.1021/je600515j" --limit 1

# Re-running is idempotent for valid existing files.
# Interrupted downloads resume from .part when the server supports Range.

# Produce all parsed rows and a separate marker for dielectric candidates.
python scripts/normalize_thermoml.py

# Explicitly produce only dielectric-related rows.
python scripts/normalize_thermoml.py `
  --csv data/processed/thermoml_dielectric.csv `
  --provenance data/processed/thermoml_dielectric.provenance.json `
  --dielectric-only

# By default, any malformed XML prevents all normalized outputs from being
# replaced. Use --allow-partial only when a partial diagnostic batch is wanted.
python scripts/normalize_thermoml.py --dielectric-only --allow-partial
```

## Outputs

Default download path:

```text
data/raw/thermoml/<doi-or-url-name>.xml
data/raw/thermoml/<doi-or-url-name>.xml.meta.json
```

Each metadata sidecar contains the source URL, UTC retrieval time, SHA256,
size, HTTP status, ETag, and Last-Modified header when supplied.

Default normalization outputs:

```text
data/processed/thermoml_normalized.csv
data/processed/thermoml_normalized.provenance.json
```

The CSV column order is fixed in `CSV_COLUMNS`. It includes provenance,
citation, component identity/composition, property, temperature, frequency,
phase, method, dielectric classification, and full variable/constraint JSON.
For mixtures, `components_json` contains each compound's standard identifiers
and any explicit component-specific composition value. The provenance JSON
records the schema version, generation time, source checksums, row counts,
selected filter, parse errors, `"deduplication": "none"`, and
`"unit_conversion": "none"`.

## Verification

```powershell
$env:PYTHONPATH = "src"
python -m unittest discover -s tests -v
```

The tests use minimal namespaced ThermoML fixtures and cover multiple
properties, compound identity, component-specific composition, temperature and
frequency supplied as either variables or constraints, missing conditions,
duplicate entries, preserved property/value/unit text, stable CSV columns,
provenance metadata, collision-safe filenames, resume, and dry-run behavior.
