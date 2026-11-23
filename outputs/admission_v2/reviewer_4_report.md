# Reviewer 4 — Independent Adversarial Audit (red team)

**Project:** electrolyte-solvent-dielectric-ml, work package B02
**Input (frozen, hashed):** `admission_v2/admission_review_queue.csv`
sha256 `1b701aaa31256051562b09d4046c34fa39eb2a5416fbfd7e685841d2582cdbab`, 70 rows, 62 distinct measurements.
**Output:** `reviewer_4_decisions.csv` — 70 rows, one per `queue_id`.
**Stance:** assume the record is wrong until proven otherwise. A PASS below is an *exoneration after an active search for counter-evidence*, not an endorsement.

---

## 1. Adversarial methodology

I did not review the queue in isolation. The queue turned out to contain three **placeholder fields** that make a naive reading unsafe, and the real adjudication required reconstructing them from the supporting files:

| queue field | what it actually contains | where the truth lives |
|---|---|---|
| `j04_condition_pair_valid` | **NaN for all 70 rows** | `condition_pair_validity_v1.csv` → `condition_pair_valid`, joined on `molecule_key` |
| `sources_lost_in_gap` | literal string `not_evaluated` in 70/70 rows | `gap_aggregation_audit.csv` → `sources_lost_in_gap` |
| `phase` / `pressure_kpa` / `frequency_mhz` | NaN for all 30 non-worksheet rows | ledger `pressure_kpa`, `phase` |

I reconstructed j04 by joining on `molecule_key` and confirmed it agrees with `j03_pair_in_single_observation` on **70/70 rows** (40 false / 30 true). So the j04 gate is not independently informative — it is the same computation re-expressed, and its all-NaN presence in the frozen queue is itself a defect worth flagging to the Lead.

Then, per record, I ran six attacks:

1. **Full-ledger counter-evidence sweep.** For each `molecule_id` I pulled every row of the 2065-row ledger (153 distinct InChIKeys) and searched for competing values at the same temperature (±0.5 K) differing by >2 %, and for any competing value at all at the nominal pressure.
2. **Co-location test.** For each claimed `(T, ε)` I tested whether *some single ledger row* carries both numbers *and* the claimed pressure *and* phase. This is the strongest possible test and it is what actually breaks most records.
3. **Synthetic-value detection.** For every record I tested whether the claimed ε is *exactly* (to 1e-9) the arithmetic mean, the median, or a pairwise midpoint of neighbouring measurements, and whether the claimed T is the midpoint of two real temperatures. I searched pairwise midpoints over the whole molecule, not just the local band.
4. **Circular-provenance test.** I looked for the identical ε at the identical T attributed to more than one DOI, and inspected `evidence_group_id` / `source_file` / `source_row_index` to see whether "independent" sources are the same deposition.
5. **Conditional-consistency / impossibility test.** Pressure and phase spread among contributing rows, T outside the measured range, ε outside physical bounds for a liquid.
6. **Gate-validity test.** For every `PROVENANCE_INCOMPLETE` I verified whether provenance was genuinely lost or whether the gate fired for a mechanical reason.

**Provenance of my own evidence.** The `temperature_median_holders` / `epsilon_median_holders` fields in `gap_aggregation_audit.csv` encode `value@ledger_row_index`. I verified all **140 holder tokens resolve to ledger rows whose value matches the token** (0 mismatches), which makes those fields a trustworthy pointer to the exact rows the aggregation consumed. That is what let me prove composites row-by-row rather than by inference.

---

## 2. Counts

| decision | rows | unique measurements |
|---|---|---|
| PASS | 22 | 22 |
| HOLD | 8 | 8 |
| FAIL | 40 | 32 |
| **total** | **70** | **62** |

`conflict_found = true`: **10 rows** (8 unique measurements).
`fatal_defect = true`: **40 rows** (32 unique measurements).

Finding labels (unique measurements):

| label | unique measurements | (rows) |
|---|---|---|
| `NONE_FOUND` | 22 | 22 |
| `COMPOSITE_CONDITION` | 21 | 27 |
| `NO_CONTRIBUTING_MEASUREMENT` | 9 | 9 |
| `AGGREGATION_UNDOCUMENTED` | 5 | 5 |
| `SOURCE_CIRCULARITY` | 3 | 3 |
| `SYNTHETIC_MIDPOINT` | 1 | 3 |
| `GATE_FALSE_NEGATIVE` | 1 | 1 |
| **total** | **62** | **70** |

(`SYNTHETIC_MIDPOINT` is R086 only; R085 and R099 are the same class of defect but labelled `COMPOSITE_CONDITION` because their temperature is also unmatched. The three rows are the three duplicate queue entries for R086.)

Evidence grade (unique): DOCUMENTED 25, INFERRED 20, INSUFFICIENT 17.

Note the 8 duplicated rows (R031, R085, R086, R099 each appear under three tracks). **The queue presents them as three separate review items; they are one measurement each.** A reviewer scoring row-by-row would triple-count DMSO. Worse, R086's duplicate rows *disagree with each other* (§3.1).

---

## 3. Conflicts and defects discovered

### 3.1 `EPSV04-R086` (GBL, γ-butyrolactone) — the queue contradicts itself

The same measurement is presented with **two different temperatures**:

| queue_id | T (K) | ε |
|---|---|---|
| `Q-PRI-EPSV04-R086` | 295.65 | 41.99 |
| `Q-CCU-EPSV04-R086` | 295.65 | 41.99 |
| `Q-J02A-EPSV04-R086` | **293.15** | 41.99 |

The ledger (`10.1021/je900503p`, Dekameter) contains only:
293.15/42.34, 293.15/42.81, 298.15/41.64, 303.15/41.10, 313.15/39.92.

Neither 41.99 nor 295.65 K exists in **any** row. And the arithmetic is unmistakable:
- 295.65 = (293.15 + 298.15)/2 — the midpoint of two *temperatures*
- 41.99 = (41.64 + 42.34)/2 — the midpoint of two *different* ε values

Two coordinates, each the mean of a different pair, neither measured. This is a synthetic composite, and the queue cannot even state it consistently.

### 3.2 `EPSV04-R031` (DMSO) — the named case, and the composite is real

The Lead asked me to verify whether "T=298.0 from source A, ε=46.05 from source D" is real. **It is real, and it is fatal.**

- ε = 46.05 exists at **T = 297.86 K** (`10.1021/je9010773`, reentrant cavity resonator), never at 298.0 K.
- T = 298.0 K exists in exactly one row: **ε = 49.0** (`10.1016/j.fluid.2013.12.014`).
- The two never co-occur. `epsilon_median_holders` = `46.05@483;46.05@484`; `temperature_median_holders` = `298@493` — **different rows by construction**.

Two further findings the other reviewers may miss:
- **The temperature is fabricated.** T = 298.0 K is exactly (297.85 + 298.15)/2 — the midpoint of two real measurements. The ε = 46.05 *is* a genuine measured value (two rows at 297.86 K), so the ε is sound; the fraud is in the **temperature pairing**, which relabels a 297.86 K measurement as a 298.0 K one. This is a subtler and more insidious defect than a fabricated ε, because the value survives a spot-check against the primary document while the condition does not.
- **Pressure is incoherent.** The contributing rows sit at **101, 114 and 291 kPa** — and across the wider 1 K band at 591, 1089, 2089, 2590, 3089, 4089, 5090 kPa. The ε = 46.05 rows specifically are at 111–291 kPa. Dielectric permittivity of DMSO is pressure-dependent; a value lifted from a pressure series is not a 101.325 kPa measurement, and the queue's `pressure_kpa` is NaN so this is never disclosed.
- **Live source conflict:** `10.1016/j.fluid.2013.12.014` reports **ε = 49.0 at 298 K**, 6.4 % from 46.05. Two sources disagree at the *same nominal temperature* and the record silently picked the lower one.

### 3.3 The pressure-sweep contamination — a systemic defect, not a row-level one

Six records take their median from a band that mixes **near-ambient** measurements with **high-pressure sweep** points from `10.1021/je060248p` (46 rows) and `10.1016/j.tca.2013.05.022`:

| measurement | claimed ε | contributors ≥ 50 MPa | max P |
|---|---|---|---|
| `EPSV04-R003` | 15.736 | 6 of 9 | 300 MPa |
| `EPSV04-R040` | 10.66 | 4 of 6 | 200 MPa |
| `EPSV04-R044` | 25.02 | 6 of 10 | 300 MPa |
| `EPSV04-R046` | 18.03 | 6 of 12 | 300 MPa |
| `EPSV04-R057` | 33.6 | 6 of 9 | 300 MPa |
| `EPSV04-R097` | 14.26 | 6 of 8 | 300 MPa |

Concretely, for `EPSV04-R097` the eight observations being medianed are ε = 13.06 (101.3 kPa), 13.06 (100 kPa), 13.63 (**50 MPa**), 14.07 (**100 MPa**), 14.45 (**150 MPa**), 14.77 (**200 MPa**), 15.06 (**250 MPa**), 15.33 (**300 MPa**). The reported 14.26 is exactly (14.07 + 14.45)/2 — the midpoint of two *pressure-sweep* points, 100 and 150 MPa, neither of which is a room-pressure measurement. The pressure field is NaN in all six queue rows, so **nothing in the frozen queue discloses this**.

### 3.4 Synthetic midpoints — 17 unique measurements

I found **17** measurements whose ε (or T) is an *exact* arithmetic midpoint of two real observations. **14 of these ε values are not present anywhere in the ledger** — they exist only as computed means. Most damning, because they occur at ambient pressure where no physical excuse exists:

| measurement | claimed ε | exact midpoint of | ε measured anywhere? |
|---|---|---|---|
| `EPSV04-R007` | 13.505 | (13.49 + 13.52)/2 | **no** |
| `EPSV04-R036` | 15.79 | (15.77 + 15.81)/2 | **no** |
| `EPSV04-R085` | 7.0695 | (7.069 + 7.070)/2 | **no** |
| `EPSV04-R089` | 7.604 | (7.578 + 7.630)/2 | **no** |
| `EPSV04-R064` | 7.3815 | (7.363 + 7.400)/2 | **no** |
| `EPSV04-R099` | 7.798 | (7.780 + 7.816)/2 | **no** |
| `EPSV04-R091` | 2.40445 | (2.3962 + 2.4127)/2 | **no** |
| `EPSV04-R016` | 22.12 | (21.84 + 22.40)/2 | **no** |
| `EPSV04-R033` | 14.38 | (14.22 + 14.54)/2 | **no** |
| `EPSV04-R084` | 10.76 | (10.70 + 10.82)/2 | **no** |
| `EPSV04-R040` | 10.66 | (10.48 + 10.84)/2 | **no** |
| `EPSV04-R046` | 18.03 | (17.80 + 18.26)/2 | **no** |
| `EPSV04-R080` | 11.8861 | (11.7786 + 11.9936)/2 | **no** |
| `EPSV04-R083` | 78.87 | (78.42 + 79.32)/2 | **no** |
| `EPSV04-R041` | 18.845 | T = (298.15 + 300.15)/2 | n/a (T fabricated) |

By contrast `EPSV04-R057` (33.6), `R003` (15.736), `R044` (25.02) and `R095` (36.55) carry a *genuinely measured* ε that happens to sit at the wrong temperature — for these the fabrication is in the **condition**, not the value (see §3.2 for the same pattern in DMSO). I keep that distinction explicit so the Lead does not over- or under-react.

Several are also *exact medians* of their band (R040, R097), consistent with a pipeline that computes a median and then re-presents it as a measurement. The tell is the **trailing digit count**: 7.0695, 2.40445, 11.8861, 7.3815, 18.845, 13.505 are physically implausible precisions for a capacitance measurement and are exactly what `(a+b)/2` produces.

### 3.5 Circular provenance — 3 measurements

| measurement | ε | DOIs claiming the identical value at the identical T | problem |
|---|---|---|---|
| `EPSV04-R059` | 41.17 | `fluid.2008.01.024`, `fluid.2009.07.009` | different pressure labels (101.0 vs 101.325) |
| `EPSV04-R071` | 17.18 | `fluid.2008.01.024`, `fluid.2009.07.009` | same |
| `EPSV04-R068` | 1.961 | `tca.2012.05.036`, `tca.2012.10.024` | identical ε at 293.15/298.15/303.15 K in *both* files |

For `EPSV04-R068` the two files give **exactly** 1.968 / 1.961 / 1.954 at 293.15 / 298.15 / 303.15 K — identical to four significant figures across three temperatures (`tca.2012.05.036` also carries 288.15 and 308.15, which `tca.2012.10.024` lacks). Two independent measurements do not agree to four significant figures at three temperatures. This is one dataset deposited twice, and `n_contributing_sources = 2` is an inflated independence claim. These three would otherwise have passed; I hold them.

### 3.6 `PROVENANCE_INCOMPLETE` — 9 records, but one gate is wrong

Nine records (R115, R144, R147, R156, R171, R173, R195, R203, R206) have `n_contributing_sources = 0` and **do not appear in the ledger at all** (0 rows). Claimed values are bare numbers with no observation behind them. FAIL, correctly.

But **`EPSV04-R247` is a false negative.** It is labelled `PROVENANCE_INCOMPLETE` / `NO_BAND_OBSERVATIONS_FOUND`, yet the ledger holds **17 rows** for `IAHFWCOBPZCAEA`, including an *exact* match:

> `MSR-b99e9bffc309a7a8`, T = 333.15 K, ε = 56.09, p = 101.325, `10.1021/je300958c`, TRACEABLE

`in_band_n_observations = 0` only because every row carries `in_aggregate_window = False` / `temperature_band_v11 = outside_declared_window` — the room-temperature band filter discarded a valid high-temperature point. The FAIL stands (j03 pair = false is still correct, because the record's own band is empty), but **the stated reason is wrong**, and it means the gap gate can silently report "provenance lost" when provenance is present. The other reviewers should not accept `PROVENANCE_INCOMPLETE` at face value without this check.

### 3.7 `sources_lost_in_gap` — silent narrowing is pervasive

The queue's value is the placeholder `not_evaluated` in all 70 rows. The real values show that the aggregation *did* drop contributing sources, e.g.:

- `EPSV04-R044`: 7 contributing sources, **6 lost in gap**
- `EPSV04-R046`: 6 contributing, **5 lost**
- `EPSV04-R057`: 5 contributing, **4 lost**
- `EPSV04-R031`: 4 contributing, **3 lost**

So DMSO's composite is drawn from 1 of 4 sources, with three silently discarded. The frozen queue discloses none of this.

### 3.8 The 0 Hz question — resolved, and it exonerates

All 31 worksheet rows carry `frequency_mhz = 0`. I checked the whole ledger: the cross-tabulation is **perfect** —

- `Relative permittivity at zero frequency`: 1630 rows, **0** with a non-zero frequency
- `Relative permittivity at various frequencies`: 435 rows, **0** with a zero frequency

So `0 Hz` is the ThermoML designation for a **static (zero-frequency) permittivity**, applied consistently to all 1630 static rows. **It is not a placeholder** and is not, by itself, a defect. I record this explicitly because it is the one attack in my list that failed, and other reviewers may wrongly fail 31 records on it.

### 3.9 Physical plausibility — clean

No record has ε < 1.5 or ε > 100; no claimed T falls outside its molecule's measured range; all ledger rows are `Liquid` with no boiling/melting contradiction. These attacks found nothing.

### 3.10 γ-valerolactone — the known conflict is **absent from this audit**

The named case does not appear here. `GAEKPEKOJKCEMS-UHFFFAOYSA-N` has **0 rows in the ledger** and **0 rows in the 70-row queue**; `EPSV04-R227` and `EPSV04-R248` are not in the queue. `condition_pair_validity_v1.csv` carries both rows as `NO_CONTRIBUTING_MEASUREMENTS` (ε = 36.1 and 36.9, T = 298.15).

So the 36.1-vs-36.9 conflict was **not adjudicated — it was excluded from the review queue entirely.** That is a scope decision made before review, and it means this audit cannot certify that the conflict was resolved. The two mutually exclusive values remain live in the provenance layer.

---

## 4. Assessment of the frozen gates

I agree that `j03_pair_in_single_observation == false` should be fatal — 40 rows — but I note it makes the other gates largely redundant. The gates I do **not** endorse at face value:

- **`j04` is not an independent gate.** It is NaN in the queue and, when reconstructed, is identical to `j03` on 70/70 rows. It adds no information and its presence in the frozen schema is misleading.
- **`PROVENANCE_INCOMPLETE` can be a banding artefact** (§3.6). One of nine is demonstrably a false negative.
- **`BLOCKED_UNRESOLVED_GATE` (31 rows) is used on records that are actually clean.** For the 22 rows I pass, gates A6/A8/A9/A11 amount to "a human must confirm the value against the primary document" — an unfalsifiable, permanent block that no machine audit can ever discharge. Using it as a verdict conflates *unreviewed* with *wrong*. I record these as PASS with the gate noted, rather than laundering a human-signature requirement into a scientific finding.
- Conversely, the gate that *should* have fired — pressure heterogeneity among contributing rows — **is not in the gate set at all** (§3.3).

---

## 5. Most dangerous records if admitted

1. **`EPSV04-R031` (DMSO) — 3 queue rows, 1 measurement.** The single most dangerous record. It is the project's flagship polar solvent, and its ε is *genuinely measured* (46.05, a textbook DMSO permittivity), which makes it maximally convincing and survivable under document spot-check. The defect is that the temperature was synthesised to 298.0 K (the midpoint of 297.85/298.15) and the ε lifted from a 111–291 kPa pressure series. There is also a live 6.4 % source conflict with ε = 49.0 at the same nominal 298 K. A plausible value attached to a fabricated condition is more dangerous than an implausible one, because review passes it.
2. **`EPSV04-R086` (GBL)** — the queue cannot agree with itself on its temperature, and both coordinates are midpoints of different pairs. Any downstream fit consuming this row ingests a fabricated point that will look unremarkable.
3. **The six pressure-sweep records (`R003`, `R040`, `R044`, `R046`, `R057`, `R097`)** — these are the most *systemically* dangerous because they look perfectly ordinary: ambient-pressure, room-temperature, plausible ε, no NaN. Nothing in the frozen queue reveals that the median mixes 0.1 MPa with 300 MPa. If any of these enter a dielectric-constant training set, they teach the model that permittivity is a function of nothing in particular.
4. **`EPSV04-R068` (TEGDME) and the duplicate-DOI pairs** — admitting these as `n_contributing_sources = 2` corrupts any independence-weighted statistic, which is exactly the quantity a provenance audit exists to protect.

**Where I may be wrong.** My PASS set is conditional on the ledger being a faithful transcription of the primary documents; I verified internal consistency and traceability flags, but I cannot verify a digit against the PDF. A PASS here means "no counter-evidence found in the available evidence base," which is the strongest claim the data supports. If the Lead can supply the primary PDFs for the 22 PASS rows, the value-level check should be run before admission — that is precisely what gates A6/A8/A9/A11 are for, and I am not claiming to have discharged them.

**Bottom line.** 22 of 62 measurements (35 %) survive an active adversarial search. 32 (52 %) are fatally defective. The dominant failure mode is not missing data — it is **composite construction**: temperatures and permittivities taken from different observations, plus midpoints and medians presented as measurements, at precisions that betray their origin. The queue's own gate layer detects the symptom (`COMPOSITE_CONDITION_UNMATCHED`) but not the mechanism, and its placeholder fields (`j04` NaN, `sources_lost_in_gap = not_evaluated`) conceal the pressure heterogeneity and source loss that make these records unusable.
