# Reviewer 3 — Data Mapping, Identity, Temperature, Frequency and Code Correctness

**Project** electrolyte-solvent-dielectric-ml · **Work package** B02 · **Role** independent
implementation auditor (1 of 4).

**Inputs (byte-verified against `admission_review_queue_manifest.json`, all 8 hashes OK)**

| input | sha256 (prefix) | rows |
|---|---|---|
| `admission_review_queue.csv` | `1b701aaa31256051…` | 70 |
| `measurement_ledger_v1.csv` | `1031611d703a5a29…` | 2065 |
| `condition_pair_validity_v1.csv` | `8baea7bc87842d6c…` | 248 |
| `aggregate_contribution_ledger_v1.csv` | — | 248 |
| `gap_aggregation_audit.csv` | `6b34cc69e79ade24…` | 248 |
| `j05_summary.json` | — | 3 folded skeletons |
| raw `dielectric_observations_v11plus.csv` | `159b928f800a5596…` | 2065 |
| raw `dielectric_v04.csv` | `e046a3831630e36a…` | 248 |

**Deliverables written**
- `E:\Claude Code\电解质ML\电解质ML\outputs\admission_v2\reviewer_3_decisions.csv` (70 rows)
- `E:\Claude Code\电解质ML\电解质ML\outputs\admission_v2\reviewer_3_report.md` (this file)
- working artifacts, not deliverables: `outputs\admission_v2\_reviewer3_work\`
  (`_reviewer3_recompute.py`, `_reviewer3_recompute.json`, `_reviewer3_decide.py`)

No input file was modified. The three generator scripts were re-run in `--check` mode and
all three reproduce byte-identically (see §6).

---

## 1. Methodology

I did **not** import any project module for the recomputation. The project's own verifier
(`audit_condition_pair_integrity.py`) is an independent reimplementation, but it shares
`load_device()`, `to_decimal()`, `BAND_*` constants and the `v04row-NNN` numbering with the
generator it audits, so a defect in any of those is invisible to it. I re-derived everything
from the two raw CSVs:

1. **Band reconstruction from raw observations.** For each molecule key I selected rows of
   `dielectric_observations_v11plus.csv` with exact full-InChIKey equality, `293.15 ≤ T ≤
   303.15`, `phase.lower() == "liquid"`, `frequency_mhz == "0"`, and both `T_K`/`epsilon`
   parseable as `Decimal`. This is the window documented at
   `audit_gap_aggregation_provenance.py:77-80`.
2. **Median in exact decimal arithmetic.** `Decimal` median with the even-count average
   `(a+b)/2`, matching `build_dataset_v01.py:126-133`. No float anywhere in the aggregate
   path of my recomputation.
3. **Pair test.** `pair_valid := ∃ one observation with T == median_T and eps == median_E`
   — the strictest reading, and the one `build_provenance_preserving_dataset.py:256-261`
   claims to implement.
4. **Cross-check against four independent recorded sources** per record: the queue row, the
   `condition_pair_validity_v1.csv` row, the `aggregate_contribution_ledger_v1.csv` row, and
   the `gap_aggregation_audit.csv` row.
5. **Source-count and source-set recount** from raw DOIs, compared with
   `n_contributing_sources` / `contributing_sources`.
6. **Join-failure probing.** I tested each `.get()`-style join in
   `build_admission_review_queue.py` against the actual key domains of its input files.

Recomputation coverage: 60 of 70 queue records have ≥1 in-band observation and were fully
recomputed (median T, median E, pair test, source count, source set). 10 records have zero
in-band observations and could not be recomputed.

---

## 2. Counts

### 2.1 Decision tally (70 queue rows, 62 distinct measurements)

| decision | n | tracks |
|---|---:|---|
| **PASS** | **30** | all `R007_WORKSHEET_40ROW` |
| **FAIL** | **30** | 22 `COMPOSITE_CONDITION_UNMATCHED_22`, 4 `P0_P1_NAMED_MOLECULE`, 4 `J02A_REQUIRES_HUMAN_REVIEW_4` |
| **HOLD** | **10** | all `R007_WORKSHEET_40ROW` |

Measurement-level (worst case over the 62 distinct `measurement_id`s, since
EPSV04-R031/R085/R086/R099 each appear under three queue ids): **PASS 30, FAIL 22, HOLD 10**.

| field | distribution |
|---|---|
| `pair_valid` | true 31 · false 30 · not_applicable 9 |
| `recompute_match` | true 60 · false 1 · not_applicable 9 |
| `evidence_grade` | DOCUMENTED 60 · INFERRED 1 · INSUFFICIENT 9 |
| `code_defect_found` | false 39 · true 31 |

### 2.2 Independent recomputation results

| quantity | value |
|---|---:|
| queue records with ≥1 in-band observation | 60 |
| queue records with 0 in-band observations | 10 |
| records where **(T, ε) is one real observation** | 31 (30 recomputed + R247) |
| records where **(T, ε) is NOT one real observation** | 30 |
| records with `n_contributing_sources > 1` (distinct aggregates) | 21 |
| … of which my median reproduces the recorded ε **exactly** | 21 / 21 |
| … of which a **mean** would give a different answer | 15 / 21 |
| … with any rounding / float drift | 0 |
| v04 (T, ε) == my recomputed (median T, median ε) | 58 / 60 (2 exceptions, §4.4) |
| J04 `condition_pair_valid` vs my judgment, all 248 v04 rows | 0 disagreements |
| J03 `pair_present_in_single_observation` vs mine, all 248 | 0 disagreements |
| ledger-vs-raw window median disagreements | 0 |
| `n_contributing_sources` mismatches (queue vs my recount) | 0 |
| `contributing_sources` set mismatches | 0 |

The **aggregate arithmetic is correct**. Every multi-source ε in the queue is exactly the
median of its contributing observations, computed in exact decimal, with no drift. The
defects I found are in the *joins, windows and defaults around* the arithmetic, not in the
arithmetic itself.

### 2.3 The 30 PASS records

`Q-WS-EPSV04-R001 R004 R008 R009 R012 R013 R014 R015 R018 R019 R024 R026 R028 R032 R034
R037 R045 R048 R051 R056 R059 R061 R065 R068 R069 R071 R076 R079 R087 R092`.

For each: my median T and median ε match the recorded `median_temperature` /
`median_epsilon` to the last digit, at least one real observation holds the pair, the v04
(T, ε) equals the recomputed medians, and the recorded source count/set matches my recount.

Three of them (R059, R068, R071) carry a **documented caveat** in `evidence_detail`:

> `n_contributing_sources = 2` counts **documents**, not independent measurements. The two
> DOIs report *bit-identical* (T, ε): R059 `(303.15, 41.17)` twice, R071 `(303.15, 17.18)`
> twice, R068 three pairs each duplicated across `10.1016/j.tca.2012.05.036` and
> `10.1016/j.tca.2012.10.024`. This is duplicate transcription, not 2-fold replication.
> It does not invalidate the pair, so these stay PASS, but the `n_contributing_sources`
> column must never be read as a replication count.

### 2.4 The 30 FAIL records

All 30 fail on the **same, proven** ground: the (T, ε) pair is a synthetic composite.

Independent result: for these records **zero** of the in-band observations simultaneously
holds `median_T` and `median_E`. Every one of the 30 carries
`MEDIAN_T_AND_EPSILON_FROM_DIFFERENT_OBSERVATIONS`; 23 additionally carry
`EPSILON_MEDIAN_NOT_AN_OBSERVED_VALUE` and 10 also carry
`TEMPERATURE_MEDIAN_NOT_AN_OBSERVED_VALUE` (at the level of the 22 distinct aggregates:
22 / 17 / 8). The two mechanisms are:

- **the medians land on different observations** (all 30) — e.g. DMSO `EPSV04-R031`: 35
  in-band observations over 4 DOIs. Median T = 298 K is held by exactly **one** observation,
  row 493, whose ε is **49.0** — the single most extreme value in the whole set. Median
  ε = 46.05 is held by rows 483/484, both at T = 297.86. **No single observation holds
  both**, so the resulting `(298, 46.05)` combines one outlier's temperature with a
  typical-value ε. This is not a rounding artefact; it is a physically incoherent pair.
- **the ε median is not even an observed value** (23 of 30) because the count is even and the
  two middle values differ. GBL `EPSV04-R086`: 4 in-band observations
  `(293.15, 42.34) (293.15, 42.81) (298.15, 41.64) (303.15, 41.10)`; median ε =
  `(41.64+42.34)/2 = 41.99`, a number that **appears nowhere** in the source. The 8 rows
  where the *T* median is likewise unobserved are
  `v04row-016 033 041 080 083 084 086 091`.

For all 30, `pair_valid = false`, `recompute_match = true` (my medians equal theirs),
`evidence_grade = DOCUMENTED`. Per the review contract, a pair that was never measured
⇒ **FAIL for measurement-level use**. This matches the project's own
`COMPOSITE_CONDITION_UNMATCHED` verdict, which is the correct call.

### 2.5 The 10 HOLD records

Nine are the NBS514 manual-transcription rows whose molecule is **entirely absent from the
observation layer** — I verified 0 rows at full-InChIKey **and** 0 rows at skeleton level, so
this is not a skeleton-join artefact: `NTIZESTWPVYFNL`, `QWVGKYWNOKOFNN`, `LFSAPCRASZRSKS`,
`YWAKXRMUMFPDSH`, `CYTYCFOTNPOANT`, `GETTZEONDQJALK`, `PYLWMHQQBFSUBP`,
`BTQZKHUEUDPRST`, `PMJHHCWVYXUKFD`. The contribution list cannot be reconstructed from the
source layer, so `condition_pair_valid = false` is a *certificate* (`NO_CONTRIBUTING_
MEASUREMENTS`), not a computed test. Cannot recompute ⇒ **HOLD / INSUFFICIENT**. All nine
are in `coverage_gap_registry.csv` as `RECOVERABLE_NBS514_MANUAL_TRANSCRIPTION`.

The tenth is `EPSV04-R247` (succinonitrile, C18 `SN`, `IAHFWCOBPZCAEA`), discussed in §4.4 —
it is a **false negative** in the pipeline, not a genuine gap.

---

## 3. Identity mapping — InChIKey skeleton join

### 3.1 Is any queue record affected?

**No.** This is the one known risk in the project that is cleanly handled for the queue:

- `v04` has exactly 3 skeletons with two rows each
  (`j05_summary.json`: `ZQDPJFUHLCOCRG` = cis/trans-3-hexene, `KFUSEUYYWQURPO` =
  cis/trans-1,2-dichloroethylene, `GAEKPEKOJKCEMS` = γ-valerolactone *source conflict*, not
  stereo).
- Intersecting those skeletons with the 70 queue `molecule_id`s returns the **empty set**.
- Zero observations in the 2065-row layer are mis-joined to an A18 member by skeleton-only
  matching (I resolved all 18 A18 SMILES through RDKit and compared full keys).
- All 16 queue rows with a populated `a_name` match their A18 member on the **full**
  InChIKey, not merely the skeleton.

So the queue itself is safe. **But the audit layer is not** — see §4.3.

### 3.2 `j05_summary.json` is internally honest

It correctly reports `n_skeletons_with_multiple_rows: 3`, splits
`SAME_COMPOUND_SOURCE_CONFLICT: 1` / `STEREOISOMER_DISTINCT_COMPOUNDS: 2`, and states
`a18_affected_by_stereoisomer_folding: []`. I independently confirm A18 is untouched. The
residual risk is documented, not hidden.

---

## 4. Code defects found

Severity: **S1** silently corrupts a frozen output · **S2** produces a wrong verdict on a
real record · **S3** latent / currently harmless but unsound.

### 4.1 S1 — `build_admission_review_queue.py:100` + `:154,:196,:238,:277` — J04 column is empty on 70/70 rows

```python
100:    pv_rows = {r["aggregate_id"]: r for r in load_csv(pair_validity)}
...
154:    "j04_condition_pair_valid": pv.get("condition_pair_valid", ""),
```

`pv_rows` is keyed by **`aggregate_id`**, whose values are `v04row-001 … v04row-248`
(verified: `condition_pair_validity_v1.csv` has no `measurement_id` column at all). But the
lookup at lines 154/196/238/277 is `pv.get(mid)` where `mid = "EPSV04-R001"` etc. The keys
**can never match**.

Measured consequence: `j04_condition_pair_valid` and `j04_invalidity_reason` are empty
strings on **all 70 rows** — `n_j04_column_populated = 0/70`, and 70/70 disagree with the
actual `condition_pair_validity_v1.csv` value for the same aggregate. The queue that four
reviewers were told to judge therefore **carries no pair-validity verdict whatsoever**, even
though the manifest pins and hashes that exact file as an input. The `.get(key, "")` default
is what converts a total join failure into a plausible-looking blank instead of an error —
the exact "missing value becomes a plausible-looking non-value" pattern this audit targets.

Because `j04_condition_pair_valid` is empty rather than `true`, no PASS can be granted on
the strength of the queue column alone. I supplied the verdict by joining on
`measurement_id → aggregate_id = "v04row-%03d"`, which I verified is a correct 1:1 mapping
(`v04row-NNN` ↔ v04 row NNN ↔ `EPSV04-R{NNN}`, 248/248 exact on both T and ε).

### 4.2 S1 — `build_admission_review_queue.py:98` + `:126,:171,:211,:251` — 29/70 rows get blank phase/pressure/frequency/verdict

```python
98:     am_rows = {r["measurement_id"]: r for r in load_csv(admission_matrix)}
126:    am = am_rows.get(mid, {})
```

The keying is correct here, but `admission_matrix_R001.csv` contains only **64** rows and the
queue has **70** ids. `am_rows.get(mid, {})` silently substitutes an empty dict, and every
field sourced from `am` becomes `""`:

- 29/70 rows have `phase == ""`, `pressure_kpa == ""`, `frequency_mhz == ""`
- 29/70 rows have `admission_verdict_frozen == ""`
- hits by track: `R007_WORKSHEET_40ROW` 40/40, `P0_P1_NAMED_MOLECULE` **0/4**,
  `COMPOSITE_CONDITION_UNMATCHED_22` **1/22**, `J02A_REQUIRES_HUMAN_REVIEW_4` **0/4**

This directly defeats the frequency/phase dimension of my scope: for 39 of 70 queue rows the
frequency is **blank, not `0`**, so a reviewer cannot tell "static (0 Hz)" from "not
supplied". It also means the frozen admission verdict is absent for the 29 CCU/PRI/J02A rows
— the tracks where the answer matters most. An explicit `MISSING_UPSTREAM` sentinel was
required; an empty string was written instead. Flagged `code_defect_found = true` on every
affected FAIL record.

### 4.3 S2 — `audit_gap_aggregation_provenance.py:523` + `:550` — skeleton-keyed v04 lookup folds stereoisomers

```python
523:    "v04_by_skeleton": {skeleton(r["inchikey"]): r for r in v04 if skeleton(r["inchikey"])},
550:    v04_row = dataset["v04_by_skeleton"].get(skeleton(molecule_id))
```

Line 523 is a **last-row-wins dict comprehension**. For the 3 folded skeletons, both isomers
collapse to whichever v04 row came later. Line 550 then looks up each gap row through that
collapsed dict, so on those 6 audit rows one isomer's v04 (T, ε) is compared against the
*other* isomer's gap (T, ε). Measured:

| measurement | gap (T, ε) | audit `v04_T_K`,`v04_epsilon` | truth |
|---|---|---|---|
| EPSV04-R166 (trans-3-hexene) | 298.15, **2.062** | 298.15, **2.0** | should be 2.062 |
| EPSV04-R167 (cis-3-hexene) | 298.15, 2.0 | 298.15, 2.0 | ok |
| EPSV04-R174 (trans-1,2-DCE) | 298.15, **9.2** | 298.15, **2.14** | should be 9.2 |
| EPSV04-R175 (cis-1,2-DCE) | 298.15, 2.14 | 298.15, 2.14 | ok |
| EPSV04-R227 (γ-VL) | 298.15, **36.1** | 298.15, **36.9** | should be 36.1 |
| EPSV04-R248 (γ-VL) | 298.15, 36.9 | 298.15, 36.9 | ok |

The *verdict* (`PROVENANCE_INCOMPLETE`) happens to stay correct because both isomers have
`n_band = 0`, so the corruption is confined to the reported `v04_T_K`/`v04_epsilon` columns.
It is still a real mis-join in a frozen audit artifact, and it will become a wrong verdict
the moment either isomer gains a usable in-band observation. Note the generator's own
module docstring (`:46`) forbids treating a median-coincidence as provenance — the same
caution was not applied to the skeleton key.

*Same class, same file, third instance*: `audit_candidate_exclusion.py:447` builds
`gap_by_skeleton` from the 248-row gap table, which has 3 duplicated skeletons, so
`gap_row` for a review target can be another compound's row. Not currently reachable (the 4
`REVIEW_TARGETS` are all single-row skeletons) but latent.

### 4.4 S2 — hard-coded temperature window turns a real measurement into a "no contribution" certificate

`audit_gap_aggregation_provenance.py:77-78` and
`build_provenance_preserving_dataset.py:127-132` hard-code `BAND_LOW/HIGH = 293.15/303.15`
and never consult v04's own `temperature_band` column. `dielectric_v04.csv` marks 246 rows
`room_temperature`, 1 `extended_temperature` (`v04row-222`, T = 313.15), 1
`high_temperature` (`v04row-247`, T = 333.15).

`EPSV04-R247` (succinonitrile, `IAHFWCOBPZCAEA`): 17 observations exist, and
`(T = 333.15, ε = 56.09)` matches observation row 443 **exactly** (freq = 0, Liquid,
`10.1021/je300958c`). Yet the pipeline reports `n_contributing_measurements = 0`,
`n_contributing_sources = 0`, `condition_pair_valid = false`,
`invalidity_reason = NO_CONTRIBUTING_MEASUREMENTS`, verdict `PROVENANCE_INCOMPLETE`.

That is a **false negative**: a genuine single observation is being reported as
unreconstructable. I record `pair_valid = true`, `recompute_match = false`,
`code_defect_found = true`, **HOLD / INFERRED** — the value is sound but the frozen verdict
is wrong and must be re-adjudicated, not accepted and not rejected.

Note the window is *mostly* harmless: recomputing with and without the accepted low-frequency
observations (`accepted_extended_lowfreq` 299 + `accepted_primary_lowfreq` 136) changes the
aggregate for **0** of the 70 queue records, so `frequency_mhz == "0"` is not distorting any
queue value. The `293.15–303.15` bound is the one that bites.

### 4.5 S2 — `build_admission_review_queue.py:261-262` — a nearest-neighbour T paired with an aggregate ε

```python
261:    "temperature_raw_K": m["temperature_raw_K"],   # from j02a_exclusion_summary.json
262:    "dielectric_raw": gap.get("v04_epsilon", ""),   # from the v04 aggregate
```

For the `J02A` track the two halves of `(T, ε)` come from **different provenance chains**.
`j02a_exclusion_summary.json` → `audit_candidate_exclusion.py:477-479`:

```python
477:    chosen = match["exact"][0] if len(match["exact"]) == 1 else (
478:        match["nearest"][0][2] if match["nearest"] else None
479:    )
```

When there is no unique exact match, `chosen` becomes the **nearest** observation, and its
`T_K` is then published as `temperature_raw_K` (`:540`) — a substitution, not a
measurement. The ε, meanwhile, is taken from the v04 aggregate. Result on
`Q-J02A-EPSV04-R086` (GBL):

- queue row says `(T, ε) = (293.15, 41.99)`
- true band median is `(295.65, 41.99)`; the *same* measurement's `Q-CCU` row correctly says `295.65`
- GBL's observations are `(293.15, 42.34) (293.15, 42.81) (298.15, 41.64) (303.15, 41.10) (313.15, 39.92)`
- **41.99 is not any observation's ε at 293.15** — the pair `(293.15, 41.99)` was never measured

So this one queue row exhibits *two* independent provenance breaks: the T is a
nearest-neighbour substitution, and the ε is an even-count median that is itself unobserved.
The four `J02A` rows are the only place in the queue where this construction is used, and it
is exactly the failure mode the project's own `COMPOSITE_CONDITION_UNMATCHED` verdict exists
to catch — yet the J02A row is labelled `REQUIRES_HUMAN_REVIEW` with a T that looks
authoritative.

### 4.6 S2 — `build_provenance_preserving_dataset.py:437-441` — vacuous acceptance criterion

```python
437:            "no_synthetic_pair_marked_valid": all(
438:                r["condition_pair_valid"] == "true"
439:                for r in validity_rows
440:                if r["invalidity_reason"] in ("not_evaluated",)
441:            ),
```

The criterion is named "no synthetic pair marked valid" but it filters to rows whose
`invalidity_reason` is exactly `not_evaluated`. `invalidity_reason` is only `not_evaluated`
when `reasons` was empty, and `reasons` always contains
`MEDIAN_T_AND_EPSILON_FROM_DIFFERENT_OBSERVATIONS` when the pair is invalid
(`:264-265`). The filter therefore **selects only rows that are valid by construction**:

- rows inspected: 69 of 248
- all 69 have `condition_pair_valid == "true"` — the test is `all(True)`
- rows that *should* have been inspected (the 170 `pair_valid == "false"`) are excluded by
  the filter and never checked

The acceptance gate reported in `dataset_v05_manifest.json` and in the J04-C/D report is
thus unconditionally `True` regardless of the data. It is a tautology presented as a
verification. (A correct form would test `pair_valid == "true"` ⇒ `not reasons` for *every*
row.)

### 4.7 S3 — `reconstruct_measurement_ledger.py:294` — unit field degrades to a non-value

```python
294:    "epsilon_unit": str(observation.get("epsilon_unit", "")).strip() or "not_evaluated",
```

`epsilon_unit` is **empty for all 2065 raw observations** (verified: `Counter({'' : 2065})`),
so every ledger row records the string `not_evaluated`. Relative permittivity is
dimensionless, and the unit is in fact recoverable from `property_name`
(`Relative permittivity at zero frequency`, 1630 rows; `… at various frequencies`, 435) and
`property_family`, both of which the ledger does carry. So the *information* is preserved and
I found **no evidence of an absolute-vs-relative unit error** anywhere — every value is a
dimensionless relative permittivity consistent with its `property_name`. But the dedicated
unit column is 100% `not_evaluated`, which means no downstream consumer can assert the unit
from that column. The `or "not_evaluated"` default masks an upstream extraction gap rather
than surfacing it.

### 4.8 S3 — `frequency_mhz == "0"` is treated as "static" only by convention; 435 observations are excluded with no v04 record of why

The conversion itself is **correct**: `reconstruct_measurement_ledger.py:230-235` multiplies
by 1000 in `Decimal`; I verified 0 conversion errors and 0 blank-mismatches across all 2065
rows (`0→0`, `1→1000`, `2→2000`, `0.01→10`, `0.05→50`, `0.1→100`, `3→3000`).

The problem is the *selection rule*. `frequency_mhz` is a plain numeric column with values
`{0: 1630, 2: 279, 0.01: 61, 1: 48, 3: 20, 0.1: 15, 0.05: 12}` — there is no separate
"is static" flag, and the window test is a **string** comparison
`str(row.get("frequency_mhz","")).strip() != "0"` (`audit_gap_aggregation_provenance.py:293`,
`build_provenance_preserving_dataset.py:131`, `audit_condition_pair_integrity.py:99`). So
`0` means static and `0.01` means 10 kHz, decided purely by string equality on a numeric
field. 435 observations (127 of them inside the 293.15–303.15 K liquid window) are silently
dropped from every aggregation on this basis, and `dielectric_v04.csv` has **no frequency
column at all** to record that a frequency filter was applied. The information survives only
as `NOT_IN_ANY_AGGREGATE_WINDOW` in the ledger note. I confirmed this currently changes no
queue aggregate (§4.4), so it is latent, not active — but the "0 = static" convention is
load-bearing and undocumented at the point of use.

### 4.9 S3 — `audit_condition_pair_integrity.py` float/Decimal mixing

`independent_window()` (`:90-94`) converts to `float` and `:173-181` takes
`statistics.median` in float, then compares to the generator's `Decimal` result with a
`> 1e-9` tolerance. The generator uses exact `Decimal`. I hunted for a case where this
diverges and found **none** at the `1e-9` tolerance for any even-count median reachable from
the data (max observed drift `4.4e-16`, on `2.40445/2.41`). So the tolerance is adequate for
the current data — but the verifier is not the exact-arithmetic check its docstring claims
("独立重算"), and the `1e-9` band is an unstated assumption. `:93 except ValueError: continue`
also silently drops unparseable rows rather than reporting them (currently 0 such rows).

### 4.10 S3 — wall-clock in a frozen artifact

`build_admission_review_queue.py:29,327` writes `datetime.now(timezone.utc)` into
`admission_review_queue_manifest.json` (`generated_at_utc: 2026-11-23T04:06:05Z`). The
*queue CSV* is deterministic, but the manifest that pins its hash is not reproducible. Every
`confirm_2027` generator explicitly excludes wall-clock; the B02 builder does not.

### 4.11 Not defects (checked and cleared)

- **No silent `try/except` swallowing real data.** `to_decimal` (`reconstruct_measurement_
  ledger.py:128-135`) and `to_float` catch broad `Exception` and return `None`, but every
  caller treats `None` as missing (`:275-280` records `TEMPERATURE_NOT_NUMERIC`), and 0 rows
  are affected.
- **No `float()` on empty strings.** `to_decimal` short-circuits on `""`.
- **No NaN/inf coercion.** 0 rows contain `nan`/`inf`; 0 values are accepted by `float()`
  but rejected by `Decimal()`.
- **No set/dict iteration-order dependence in output.** Every place a set is serialised it
  goes through `joined()` → `sorted()` (`:160-161`) or explicit `sorted()`.
- **No off-by-one in `v04row-NNN` ↔ `EPSV04-R{NNN}`.** Verified 248/248 exact on both T and
  ε against the gap table.
- **No duplicate measurement ids.** `measurement_id_for()` hashes
  `(inchikey,T,eps,doi,source_row_index)`; all 2065 identity tuples are distinct, so 0
  collisions and 0 duplicate `MSR-` ids.
- **All 2065 ledger rows are `TRACEABLE`** (DOI + file sha256 + row index all present);
  `n_untraceable = 0`.

---

## 5. Temperature mapping — direct answer

**Is `temperature_raw_K` from the same observation as `dielectric_raw`?**

| track | n | same observation? |
|---|---:|---|
| `R007_WORKSHEET_40ROW` | 40 | **30 yes, 10 n/a** — both come from the frozen worksheet row, which is a single (T, ε) pair; for the 30 the pair is confirmed real, for the 10 there is no observation at all |
| `P0_P1_NAMED_MOLECULE` | 4 | **no** — T from `gap.v04_T_K`, ε from `gap.v04_epsilon`; both are the *independently computed medians*, and for all 4 no observation holds both |
| `COMPOSITE_CONDITION_UNMATCHED_22` | 22 | **no** — same construction, same result |
| `J02A_REQUIRES_HUMAN_REVIEW_4` | 4 | **no, and worse** — T from a *nearest-neighbour substitution* (`audit_candidate_exclusion.py:477-479`), ε from the v04 aggregate |

The known v04 defect is therefore **confirmed and quantified**: of the 60 queue records that
have a reconstructable observation window, **30 (50%) have a (T, ε) pair that never
co-occurred in a single real measurement**. For 9 of them the ε median is not even an
observed value (`(41.64+42.34)/2 = 41.99` for GBL is the clearest example).

`j04_condition_pair_valid` and `j03_pair_in_single_observation` **cannot be used to detect
this in the queue**, because the former is empty on all 70 rows (§4.1) and the latter is
populated but, for the 22 CCU rows, is the only thing standing between a reviewer and a
synthetic pair. Where both are populated (`R007` track, 40 rows) they agree with each other
and with my recomputation 40/40 — so the *underlying* J03/J04 analysis is sound; only its
transport into the queue is broken.

---

## 6. Reproducibility

I ran all three generator scripts in `--check` mode against the frozen outputs:

| script | result |
|---|---|
| `reconstruct_measurement_ledger.py --check` | `OK 重建一致: 3 个文件` (exit 0) |
| `build_provenance_preserving_dataset.py --check` | `OK 重建一致: C/D 5 个文件` (exit 0) |
| `audit_condition_pair_integrity.py --check` | `OK 重建一致: J04-D 3 个文件` (exit 0) |
| `audit_gap_aggregation_provenance.py --check` | `OK 重建一致: 7 个文件` (exit 0) |

All four `confirm_2027` outputs are byte-reproducible. They are also **deterministic in the
sense the audit asked about**: no wall-clock (the `--check` byte comparison would fail if
timestamps were embedded), no RNG (no `random`/`seed`/`uuid` anywhere), no filesystem-order
dependence (every set is `sorted()` before serialisation, every iteration is over a list
built by `read_csv_strict`, and `sorted()` is used at every aggregation boundary —
`reconstruct_measurement_ledger.py:161,321,351`, `audit_gap_aggregation_provenance.py:209,
545,623`, `build_provenance_preserving_dataset.py:182-187`).

Two caveats:
- `j03_inputs_manifest.json` embeds `environment: {"platform": "Windows-11", "python":
  "3.12.14"}`, so the manifest hash is machine-dependent even though the data outputs are
  not. Same class as §4.10.
- `build_admission_review_queue.py` is **not** reproducible (§4.10), so the *manifest* that
  binds four reviewers to one byte-identical queue cannot be re-derived. The queue CSV itself
  is stable — I re-hashed it at `1b701aaa31256051562b09d4046c34fa39eb2a5416fbfd7e685841d258
  2cdbab`, matching the manifest.

---

## 7. Systematic issues

1. **`.get(key, default)` is used as an error-handling strategy, and it is the dominant
   failure mode in this work package.** Both S1 defects (§4.1, §4.2) are a `.get()` that
   silently returns `""` or `{}` when a key domain does not match. In each case the *key
   domains are statically knowable* (`aggregate_id` vs `measurement_id`; 248 vs 64 rows) and
   a one-line `assert` or a `KeyError` would have caught it at build time. The pattern
   converts a hard join failure into a blank field that looks like "not applicable".

2. **The queue is assembled from four files with four different key schemes and no
   reconciliation step.** `gap_aggregation_audit.csv` is keyed by `measurement_id` (works,
   70/70), `condition_pair_validity_v1.csv` by `aggregate_id` (fails, 0/70),
   `admission_matrix_R001.csv` by `measurement_id` but covers only 64 ids (fails, 29/70),
   and `j02a_exclusion_summary.json` by its own `observation_id`. Three of the four joins are
   broken. The manifest hashes all four inputs, which gives a false impression that all four
   were *used*.

3. **Generator and verifier are not independent.** `audit_condition_pair_integrity.py`
   advertises "不复用生成逻辑" but imports `load_device`, `to_decimal`, `skeleton`,
   `BAND_*`, `PINNED` and the `v04row-NNN` numbering from the module it verifies. It
   correctly re-implements the window filter and median, and it did catch nothing because
   there was nothing to catch *in those two functions* — but the skeleton-fold defect (§4.3)
   lives in the shared `skeleton()` + a shared dict convention and is therefore invisible to
   it. A verifier that shares any code with the generator cannot audit that code.

4. **Acceptance criteria are written as filters that select their own passing cases**
   (§4.6). `no_synthetic_pair_marked_valid` inspects only rows already known valid and
   reports `True`. Because it is emitted into the frozen manifest and the J04-C/D report, a
   reader is told "no synthetic pair is marked valid" by a check that would say `True` even
   if every pair were synthetic. This is the most dangerous class of defect here: not a
   wrong number, but a *guarantee* that is empty.

5. **`n_contributing_sources` counts documents, and three queue records are duplicate
   transcriptions.** R059/R068/R071 each list 2 DOIs reporting bit-identical (T, ε). The
   column name invites reading it as replication. The project does separately record
   `experimental_independence_status: not_evaluated` in the source registry — the honest
   position — but the queue exposes only the misleading count.

6. **Hard-coded window constants outlive the column that supersedes them.** v04 carries
   `temperature_band` (`room_temperature` / `extended_temperature` / `high_temperature`), but
   all three window functions hard-code `293.15–303.15`. The two rows that fall outside are
   `v04row-222` (T=313.15, no observations anyway) and `v04row-247` (T=333.15, **17
   observations, exact match**), producing the one false negative in the queue (§4.4).

7. **The three folded stereoisomer skeletons are handled correctly in `j05` and incorrectly
   in `audit_gap_aggregation_provenance.py`.** `j05_summary.json` identifies them, names them,
   and prescribes "在按骨架连接的分析中必须显式排除这两个骨架, 或改用完整 InChIKey 连接".
   That prescription was then not followed in the very module that joins v04 to gap by
   skeleton (§4.3). The knowledge existed and was not applied — the classic failure of a
   documented risk without a mechanical control.

---

## 8. Bottom line for B02

- **30/70 PASS** — every one a `R007_WORKSHEET_40ROW` record with a verified real (T, ε)
  observation, a reproduced median, and a reproduced source count. These are the only records
  in the queue I can certify for measurement-level use.
- **30/70 FAIL** — every one a synthetic (T, ε) composite, independently confirmed as
  co-occurring in **zero** observations. The project's own `COMPOSITE_CONDITION_UNMATCHED`
  verdict is correct; the queue simply fails to carry it in a usable column.
- **10/70 HOLD** — 9 genuinely unreconstructable NBS514 transcriptions (correct certificate,
  insufficient evidence to recompute), plus `EPSV04-R247`, which is a **false negative**: a
  real single observation mislabelled as having no contributors.
- **No queue record is affected by the stereoisomer skeleton fold.** The risk is real but
  lands on the audit layer, not the queue.
- **The aggregation arithmetic is correct** — 21/21 multi-source medians reproduce exactly
  in decimal, 0 drift, 0 source-count mismatches. The defects are all in the plumbing:
  joins, defaults, windows and acceptance filters.

The single most consequential fix is §4.1: without a populated `j04_condition_pair_valid`
column, a reviewer reading only the queue cannot distinguish a real measurement from a
synthetic composite, and 30 of the 70 rows are synthetic.
