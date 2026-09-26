# L1 liquid window: PubChem experimental MP / BP / FP (+ density) for the 314 InChIKeys

**Date:** 2026-09-26
**Probe:** `probes/pubchem_liquid_window_harvest.py`
**Summary:** `probes/pubchem_liquid_window_harvest_summary.json`
**Evidence:** raw PUG-View responses and the derived tables live under
`data/external/g1plus/pubchem/liquid_window/` (git-ignored):
`liquid_window_values.csv` (3,825 deposited values, one row per value),
`liquid_window_selected.csv` (819 representative values, one row per key and
property) and `_harvest_runs.jsonl` (one cost line per run).
**Opened with:** plain HTTPS through `urllib`, PUG-View
`/rest/pug_view/data/compound/{CID}/JSON?heading=Experimental+Properties`.

## The claim under test

Appendix AA puts PubChem in the L1 *harvesting* role and the identity layer (L0)
already pinned one canonical CID per InChIKey. The question here is different and
narrower: **for the liquid window of these 314 compounds — melting point, boiling
point, flash point, and density — what does PubChem actually deposit, who
deposited it, and what does each number cite?** This probe answers that question
and stops there. It makes no adjudication and promotes nothing.

The CIDs are taken from the read-only L0 output `data/reference/identity_map.csv`;
all 314 rows carry `identity_check = roundtrip_match`, so a CID can never be
attached to the wrong substance in this probe, and no identity is re-resolved.

## Answer, short form

For roughly two thirds of the coverage set PubChem deposits a usable liquid
window, and for the ionic liquids it deposits nothing citable at all.

| Property | Keys with a deposited value | Keys with a parsed value | Value rows | Peer-reviewed rows |
| --- | --- | --- | --- | --- |
| Melting point | 204 | **202** | 945 | 185 |
| Boiling point | 218 | **216** | 1,031 | 196 |
| Flash point | 190 | **189** | 848 | 227 |
| Density | 212 | **212** | 1,001 | 270 |

* **186 / 314** keys carry all three temperatures (MP and BP and FP) as parsed
  values; **217 / 314** carry at least one of them.
* **94 / 314** keys carry no MP, BP or FP at all, and they are not a random 30%:
  **58** keys have no `Experimental Properties` section whatsoever (51 of them are
  ionic-liquid / ammonium / imidazolium / sulfonyl species), and **36** have the
  section but none of the four target headings.
* Every one of the 3,825 value rows carries a depositor (`SourceName`); 1,690
  carry the depositor's own citation string, 843 carry a measurement condition
  ("at 25 °C", "at 760 mm Hg"), and 317 carry a normalised pressure.
* 11 distinct depositors supply the window. By melting-point rows: HSDB 187,
  CAMEO Chemicals 158, ICSCs 147, PAC 140, HMDB 107, OSHA 89, NIOSH 85,
  DrugBank 31, EU Food Improvement Agents 1. Two depositors appear only outside
  the melting point: Haz-Map (120 flash-point rows, 4 boiling-point rows) and
  JECFA (64 boiling-point and 64 density rows).
* `request_failures` is empty: no key was lost to a hard HTTP error, and
  `retries` is 0.

## Cost, throttle and the lesson from the previous round

| Quantity | Pilot (10 keys) | Harvest run (314 keys) | Cache-only re-parse |
| --- | --- | --- | --- |
| Network calls | 10 | **304** | **0** |
| Cache hits | 10 | 324 | 628 |
| Retries | 0 | 0 | 0 |
| Throttle waits / seconds slept | 9 / 2.218 s | **303 / 74.949 s** | 0 / 0.0 s |
| Wall clock | ~12 s | ~8 min | < 1 s |

* Throttle spacing is `DEFAULT_THROTTLE_SECONDS = 0.25` s (4 requests/s), which
  mirrors the L0 probe and sits one request per second **below** PubChem's
  published guidance for automated use without an API key (no more than five
  requests per second). The harvest run slept 74.9 s in 303 waits, so the throttle
  was actually engaged, not merely configured. The remaining ~5 minutes of the
  harvest is response latency: PUG-View scoped records run from a few kB to a few
  hundred kB.
* The cache stores one JSON file per InChIKey plus a `.url` marker holding the
  exact URL it came from. A file whose marker disagrees is treated as absent, so a
  mis-keyed or stale entry can never be served as evidence for another compound.
* **The harvesting run writes its own log line.** This was the failure of the
  previous round: the cache-only re-run logged `network_calls = 0`, the harvest
  run logged nothing, and the request cost became unrecoverable. Here
  `_harvest_runs.jsonl` receives one line per run — harvest runs included — and
  the committed summary additionally carries the recovered cost as
  `recorded_harvest_cost_from_log`
  (`{"logged_runs": 6, "max_network_calls": 304, "retries_at_max": 0,
  "throttle_seconds_at_max": 74.949}`). The committed summary itself was produced
  by a cache-only re-parse with the final parser (`network_calls = 0`,
  `cache_hits = 628`, `run_idempotent = true`), so its counts and the value table
  are guaranteed to agree.
* `run_idempotent` is `true`: the probe harvests twice per run, and the second
  pass returned byte-identical rows, statuses and zero additional requests.

## What is recorded per value

`liquid_window_values.csv` is long-format — one row per deposited value, not one
row per compound — precisely so that no provenance is dropped:

| Column | Meaning |
| --- | --- |
| `value_raw` | the depositor's own string, verbatim |
| `value_numeric`, `unit` | normalised value (`degC` for the three temperatures, `g/cm3` or `relative` for density) |
| `temperature_c` | for MP/BP/FP the value itself in °C; for density the measurement temperature |
| `condition_raw`, `pressure_mmhg` | the `at ...` clause and its pressure where stated |
| `subtype` | density only: `absolute`, `relative`, `unspecified`, `excluded_vapour`, `excluded_bulk`, `unparsed` |
| `depositor`, `reference`, `reference_number` | PUG-View `SourceName`, the depositor's citation string, and the depositor's reference index |
| `peer_reviewed` | `true` where PUG-View marks the entry `PEER REVIEWED` |
| `source_kind`, `quality_layer` | fixed `compilation` / `filter_only` |
| `source_url`, `retrieved_at` | the exact scoped URL and the run timestamp |
| `notes` | why a value was converted, skipped or left unparsed |

`liquid_window_selected.csv` picks one representative per (InChIKey, property)
with a rule stated in every row: peer-reviewed entries first; for density the most
absolute subtype wins (absolute, then relative, then unspecified); among what
remains the lower median is taken, and that row's own depositor, citation and
condition travel with it.

## Quality layer: these are compilations, not first-hand values

PubChem does not measure anything here. HSDB, CAMEO Chemicals, the ICSCs, PAC,
OSHA, NIOSH, DrugBank, HMDB and JECFA are themselves secondary compilers, and the
citations they attach (the CRC Handbook, the Merck Index, Kirk-Othmer, CHRIS, NTP
1992, ...) are the compilations of record, not the measurement.

Every row is therefore stamped `source_kind = "compilation"` and
`quality_layer = "filter_only"`. **These values may screen, rank and
cross-check compounds inside the funnel; they must not be promoted to
first-hand, citable core values, and no value here should be quoted in a
paper as an original measurement.** Anything that ends up in a published core
table needs independent adjudication against the cited primary source.

## What the numbers look like, and where they bite

Normalised ranges across the harvested values (see
`numeric_ranges_by_property` in the summary):

| Property | n | min | max |
| --- | --- | --- | --- |
| Melting point | 909 | -185.3 °C | 177.0 °C |
| Boiling point | 994 | -48.0 °C | 350.0 °C |
| Flash point | 837 | -108.0 °C | 345.0 °C |
| Density | 908 | 0.0019 g/cm3 | 3.1 g/cm3 |

Honest caveats, all of them visible in the row that carries them:

* **Unit conversion is the norm, not the exception.** Of the 2,740 parsed
  temperature values, 1,665 were already stated in °C and 1,075 were converted
  from °F (a handful from K); each converted row says
  `converted_from_degF`. Where a depositor gave both scales ("42 °F (6 °C)") the
  Celsius reading is taken so no conversion error is introduced.
* **Ranges are recorded by their first bound.** Values such as "0.810-0.816" are
  stored as 0.81 with the raw string intact; the summary does not try to model
  intervals.
* **669 density rows state no unit at all** (HSDB/OSHA/PAC frequently deposit a
  bare number under the Density heading). They are kept as `unspecified` rather
  than silently assumed to be g/cm3, and they never win the selection against an
  `absolute` row.
* **55 vapour/air entries and 28 bulk-density entries were excluded** from the
  Density heading, and 5 narrative sentences inside the MP/BP sections (for
  example "Burns with luminous flame; dielectric constant: 38.8 at 20 °C") were
  refused as values rather than recorded as a boiling point.
* **Unit-less `Value.Number` entries are recorded but not parsed.** Where PubChem
  deposits a bare structured number (propan-1-ol's `-126.1` and `97.2`, water's
  `0`) the row carries the raw text and `structured_value_not_parsed`; the unit is
  unknowable, so no value is invented.
* **Some depositor numbers are simply wrong, and this probe faithfully repeats
  them.** Examples: PAC deposits `3.1 @25 °C` for 1,4-butanediol (real value
  ~1.017 g/cm3, which HSDB also deposits as `1.0171 g/cu cm`); OSHA deposits
  `0.062` for 2-methylbutane and PAC `0.06504 @ 20°C` for 2-methyl-1-butene (both
  ~10x low against CAMEO/HSDB); dimethylamine's melting point carries the sentence
  "Deliquescent leaflets; mp: 171 °C", which reads like a salt form. This is
  exactly why the values are `filter_only` and why the selected table prefers
  peer-reviewed rows over raw medians.
* **Methyl ether** (dimethyl ether) legitimately yields `1.91855 g/L at 1 atm and
  25 °C`, i.e. 0.0019 g/cm3 — a gas density, not a liquid one. It is the minimum
  of the density range and it is a correct conversion of what the depositor
  stated.

## Failed and missing keys

| Status | Keys | Note |
| --- | --- | --- |
| `harvested` | 220 | at least one of the four target headings |
| `harvested_without_target_properties` | 36 | Experimental Properties exists, but none of MP/BP/FP/Density |
| `no_experimental_properties_section` | 58 | scoped PUG-View 404 (51 are ionic liquids / salts) |
| `unresolved_offline` / `unresolved_empty_response` / `request_failed` | 0 | nothing was abandoned |

The 58 scoped 404s are the interesting negative result: TFSI, BF4, PF6 and halide
ionic liquids (for example triethylpentylammonium bis(trifluoromethylsulfonyl)imide,
1-ethyl-3-methylimidazolium ethyl sulfate, 1-butyl-3-methylimidazolium iodide)
have a PubChem record but no `Experimental Properties` section at all, so their
liquid window must come from somewhere else (ILThermo, the primary literature).
The full list, with names and CIDs, is `missing_temperature_keys` in the summary.

## Limits of this probe, stated plainly

* **A scoped 404 is read as "the section is absent", not "the compound is
  absent".** A single request cannot distinguish the two. It is safe here only
  because L0 already proved each CID exists by InChIKey round trip, and it was
  spot-checked: the unscoped PUG-View record for CID 53384372 exists (79 kB) and
  indeed contains no Experimental Properties section.
* **Only one heading per request.** PUG-View honours the first `heading`
  parameter and ignores the rest, so the probe asks for the whole
  `Experimental Properties` section once and walks its subsections locally. Four
  separate per-heading requests per key would have quadrupled the request count
  for no extra coverage.
* **Flash point is taken from the Experimental Properties section only.** Where a
  compound files its flash point solely under Safety and Hazard Properties, this
  probe does not see it; that section was deliberately left out of scope.
* **`peer_reviewed` is PUG-View's own marker**, not an independent review. It is
  used only to order candidates within a key.
* **Network path.** The workstation's environment carries a stale
  `HTTP(S)_PROXY` (`127.0.0.1:10809`) that refused connections, so the probe
  defaults to a direct connection (`--proxy none`) and can be pointed at a proxy
  with `--proxy env` or an explicit URL.
* **This is a 2026-09-26 snapshot.** PubChem is continuously re-deposited; the
  cache and the URLs in `source_url` are what make the snapshot checkable later.

## Re-running

```powershell
# full harvest (writes cache, value tables, summary and one log line)
.\.venv\Scripts\python.exe probes\pubchem_liquid_window_harvest.py

# cache-only re-parse: network_calls must be 0
.\.venv\Scripts\python.exe probes\pubchem_liquid_window_harvest.py --offline

# a bounded pilot
.\.venv\Scripts\python.exe probes\pubchem_liquid_window_harvest.py --limit 10
```

Tests are offline and never touch the network:
`.\.venv\Scripts\python.exe -m pytest tests/test_pubchem_liquid_window_harvest.py -q`.
