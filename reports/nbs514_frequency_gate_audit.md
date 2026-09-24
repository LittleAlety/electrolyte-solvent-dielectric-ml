# NBS Circular 514 frequency gate: the isobutyronitrile crawl hit is not an ingestable static value

**Date:** 2026-09-24
**Scope:** G1+ crawl round 2 (modern battery-solvent candidates). The crawl
surfaced `nbs514:p20:009` as an apparent new static permittivity.
**Artifact:** `probes/nbs514_frequency_gate_audit.json` (schema
`nbs514_frequency_gate_audit/v1`), built by
`probes/nbs514_frequency_gate_audit.py`
**Verdict:** the value is a **360 MHz dispersion measurement**. The NBS import
rule excludes it, and importing it would overrule that rule for one row.

## 1. The crawl hit

| Field | Value |
|---|---|
| Transcript record | `nbs514:p20:009` (NBS Circular 514, part 1, line 147) |
| Compound | isobutyronitrile, C4H7N |
| Permittivity | **20.4** |
| Temperature | 24 °C = **297.15 K** |
| Frequency note | `f=3.6x10^8 cycles/sec` |
| Transcript eligibility | `candidate_near_room` |

The record sits next to `nbs514:p20:008` butyronitrile (20.3 at 294.15 K,
same frequency note). Butyronitrile is already in the dataset at **22.0 at
298.15 K** from a primary source (`10.1007/BF02848094`), i.e. the same
frequency-gated neighbour was previously skipped in favour of a static value.

## 2. Which rule actually applies

It is **not** a project-wide "zero-frequency only" contract. The manual entry
schema (`docs/week3/manual_dielectric_entry_schema.md`) requires
`frequency_type` to be `zero_frequency` **or an explicitly justified
`static_low_frequency` protocol** - which is how the 1 MHz ethylene carbonate
row entered the main table.

The rule that excludes this row is specific to the NBS import path:

- `scripts/resolve_nbs514_structures.py` appends the exclusion reason
  `frequency_dependent` for **any** non-empty `frequency_note`, which makes
  the row `selection_eligible = false`;
- `scripts/build_dielectric_v02.py` raises
  `selected row has a source or stability exclusion` if a selected NBS row
  carries a `frequency_note`.

3.6x10^8 cycles/sec sits inside the dispersion region, so it is not a
low-frequency protocol that could be justified the way the 1 MHz EC measurement
is.

## 3. The gate, measured rather than assumed

| Quantity | Value |
|---|---|
| Transcript rows | 636 |
| Rows carrying an explicit frequency note | **127** |
| Of those, present in `data/dielectric_v03.csv` | **0** |
| Of those, absent from the dataset | 127 |
| Frequency-note values | 3.6, 4 and 5 x 10^8 cycles/sec |
| Those rows' transcript eligibility | `candidate_near_room` 125, `candidate_exception` 2 |
| NBS-sourced rows in the dataset | 114 |
| ... carrying the `zero_frequency` gate flag | **110** |
| ... carrying no gate flags at all | 4 (v0.3 additions: 4-methyl-1,3-pentadiene, 2,3-dimethyl-1,3-butadiene, 1-heptene, 2-methyl-2-hexene) |

The separation is total for the NBS path: every microwave-frequency row is
outside the dataset, and every inherited NBS row inside it is flagged
`zero_frequency`. There is no ambiguous middle case to adjudicate.

## 4. Why this is recorded instead of ingested

Under the project's evidence discipline the correct record is:

- **not** `found=false` - the value exists and is transcribed;
- **not** a dataset row - the NBS import path excludes any row with a frequency
  note, and 360 MHz is not a justifiable static low-frequency protocol;
- **a documented frequency-gated candidate**, listed in
  `cross_check.modern_queue_candidates_gated_by_frequency`.

The modern battery-solvent candidate queue therefore still has exactly one
candidate whose only near-298 K NBS route is frequency-gated:
isobutyronitrile.

## 5. Reproducing

```
.venv\Scripts\python.exe probes\nbs514_frequency_gate_audit.py
.venv\Scripts\python.exe -m pytest tests\test_nbs514_frequency_gate_audit.py -q
```

## 6. Honest limitation

The audit reads the repository's own NBS 514 transcription, not the printed
circular. It establishes that the *transcribed* records with a frequency note
are all outside the dataset; it does not re-verify the transcription against
the scan, nor does it claim that a zero-frequency value for isobutyronitrile
does not exist somewhere else in the literature. It says only that this
particular route yields a frequency-gated observation.
