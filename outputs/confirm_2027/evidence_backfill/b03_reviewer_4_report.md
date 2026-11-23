# B03 Reviewer 4 — Independent Adversarial Audit (Red Team)

> Scope: A18 evidence backfill, work package B03, project `electrolyte-solvent-dielectric-ml`
> Role: try to BREAK the claim that B03 made progress. No files were modified except the two required deliverables.
> Interpreter: `E:\Claude Code\电解质ML\电解质ML\.venv\Scripts\python.exe`
> Decision file: `b03_reviewer_4_decisions.csv` (C11, C12, ALL)

---

## 0. Bottom line

**B03 added zero new evidence.** Both "new" condition-qualified measurements already existed in the frozen
`data/dielectric_v04.csv` under the *same* `source_record_id`, *same* DOI, *same* value and *same* temperature.
B03 re-read a page and confirmed a number it already had, then counted that confirmation as progress.

**Verdict: HOLD on C11 (EA) and C12 (MA); FAIL on the systemic claim.** The headline "5 of 18 resolved" is not
reproducible from B03's own register, which yields 3. The "7 uncovered molecules" are characterised as having
*no observation* when all seven already hold curated primary-source values in the same frozen dataset.

---

## 1. Are the values genuinely new? — **NO**

### 1.1 Direct proof of pre-existence

`data/dielectric_v04.csv` already contains:

| row | inchikey | name | T_K | dielectric | source_doi | source_record_id | source_page | model_ready |
|---|---|---|---|---|---:|---|---|---|
| 104 | `XEKOWRVHYACXOJ-UHFFFAOYSA-N` | Ethyl acetate | 298.15 | **6.02** | `10.6028/nbs.circ.514` | `nbs514:p20:022` | 20 | True |
| 103 | `KXKVLQRXCPHEJC-UHFFFAOYSA-N` | Methyl acetate | 298.15 | **6.68** | `10.6028/nbs.circ.514` | `nbs514:p18:009` | 18 | True |

These are the *exact same* `source_record_id` values that B03's
`condition_qualified_measurements.csv` presents as newly qualified. The identical numbers are also present in
`dielectric_v02`, `v03`, `v031`, `v032`, and in the **frozen modelling set** `data/interim/v03_original_243.csv`
(rows 103/104). `data/raw/nbs514_expansion/expansion_observations.csv` holds them too, with the same
`source_file_sha256`.

### 1.2 Chronology (mtimes)

| timestamp | file |
|---|---|
| 2026-09-23 09:23 | `data/interim/nbs514_organic_part1.csv` (the transcript) |
| 2026-09-26 20:43 | `data/dielectric_v04.csv` (values already present) |
| 2026-11-23 14:01 | `evidence_backfill_report.md` (B03 "discovers" them) |

B03 ran ~58 days after the values were already frozen into the modelling dataset.

### 1.3 B03's own artefact concedes this

`source_verification.csv` column `epsilon_agrees = true`, and the report says the NBS514 value is
"逐字节一致" (byte-identical) with the frozen v04 value. That is not a discovery test; it is a confirmation
test that could only return `true`. A verification whose pass condition is "equals the value we already have"
cannot establish new evidence.

### 1.4 B03 explicitly added no rows

The report states under "明确未做的事": *"未新增任何测量到 measurement_ledger"*. The ledger stays at 2065 rows.
So: **new ledger rows = 0. New molecules with evidence = 0. Net growth of the evidence base = 0.**

---

## 2. Is the page read genuine? — **YES** (this is the one thing B03 got right)

I independently re-extracted the PDF rather than trusting the transcript.

`data/raw/nbs514/nbscircular514.pdf` (56 pages, sha256 `cb3fa923…`) — **PDF page index 19 (1-based page 20)**:

```
C4H8O2 Butyric acid.        2.97   20   -0.23   10,70   96,149 [2,7]
       Isobutyric acid..    2.71   10           149 [2,7]
       Propyl formate.      7.70*  19
       Ethyl acetate......  6.02   25    1.5    at 25   8,63,276
```

**PDF page index 17 (1-based page 18)**:

```
Ethyl formate.      7.18   25    160 [1,7]
Methyl acetate.     6.68   25    2.2   25,40   63,260
```

So `6.02` / `298.15 K` and `6.68` / `298.15 K` are transcribed correctly, the page locators are accurate, and the
PDF is held with a matching hash. **The transcription is honest. The problem is that it is a re-read, not a find.**

---

## 3. "Resolved" is inflated — the real number is 3/18, arguably 0/18

### 3.1 B03's own register contradicts its headline

`A18_gap_register.csv` (`n_condition_valid_pairs`):

| molecule | n_condition_valid_pairs | evidence_status |
|---|---:|---|
| DMC | 1 | ROOM_BAND_PRESENT |
| DEC | 1 | ROOM_BAND_PRESENT |
| SL | 1 | ROOM_BAND_PRESENT |
| **EA** | **0** | **ZERO_OBSERVATION** |
| **MA** | **0** | **ZERO_OBSERVATION** |
| EMC, EC, PC, FEC, VC, DOL, TMP | 0 | ZERO_OBSERVATION |

**Only 3 molecules have `n_condition_valid_pairs >= 1`.** EA and MA are recorded with
`n_observations = 0`, `n_source_documents = 0`, `independent_source_status = NO_SOURCE`.
The "5" cannot be regenerated from this file.

### 3.2 An independent, earlier artefact says the same thing

`outputs/confirm_2027/provenance_repair/condition_pair_validity_v1.csv`:

```
C12 MA  v04_dielectric=6.68  n_contributing_measurements=0  n_contributing_sources=0
        condition_pair_valid=False   invalidity_reason=NO_CONTRIBUTING_MEASUREMENTS
C11 EA  v04_dielectric=6.02  n_contributing_measurements=0  n_contributing_sources=0
        condition_pair_valid=False   invalidity_reason=NO_CONTRIBUTING_MEASUREMENTS
```

`aggregate_contribution_ledger_v1.csv` adds `contribution_status = MISSING_CERTIFICATE`,
`contribution_certificate = NO_BAND_OBSERVATIONS_IN_SOURCE_LAYER`.
`intersections/joint_eligibility.csv` marks both `admitted = False`,
`eligibility_verdict = IDENTITY_ONLY_NO_CONDITION_OBSERVATION`.

### 3.3 The 5 mixes two incompatible standards

- DMC / DEC / SL — ledger-backed, condition-valid, `condition_pair_valid = True`.
- EA / MA — a page read that B03 **deliberately excluded from the ledger**, still
  `PENDING_FOUR_AGENT_REVIEW`, never reviewed, never admitted.

Adding these into one number silently upgrades an unreviewed page read to the status of an admitted measurement.
**Defensible count: 3/18.** If "resolved" means "has admitted evidence", it is **0/18** — nothing has been
admitted, and B03's own gate file says `"open": true` with the condition-qualified rows still pending.

### 3.4 The "evidence" is not even in the evidence layer

`condition_qualified_measurements.csv` has `in_measurement_ledger = false` for both rows. The two molecules B03
counts as resolved have **no rows in the measurement ledger at all** (verified: 0 ledger rows for both
`XEKOWRVHYACXOJ` and `KXKVLQRXCPHEJC`). Calling a molecule resolved while its only evidence sits outside the
project's own evidence substrate is an accounting sleight of hand.

---

## 4. The 7 "uncovered" molecules — the framing is misleading

`unresolved_molecules.csv` labels EMC, EC, PC, FEC, VC, DOL, TMP as
`NO_OBSERVATION_AND_NO_PAGE_READ` with `n_observations = 0`. **This is false as stated.** All seven already hold
curated rows in `dielectric_v04.csv` with real DOIs:

| mol | ε (v04) | T_K | evidence_level | source_doi |
|---|---:|---:|---|---|
| EMC | 2.96 | 298.15 | open_access_review_table | `10.1002/smll.202504276` |
| EC | 90.5 | 313.15 | **primary** | `10.1021/je050341y` |
| PC | 64.9 | 298.15 | **primary** | `10.1021/j100702a008` |
| FEC | 78.4 | 296.15 | **primary** | `10.1016/S0022-1139(02)00317-2` |
| VC | 126.0 | 298.0 | **primary** | `10.1039/j29660000005` |
| DOL | 7.3 | 298.15 | open_access_review_table | `10.1016/j.isci.2026.115778` |
| TMP | 21.6 | 298.15 | open_access_review_table | `10.1016/j.isci.2026.115778` |

The label is true only for the **ThermoML observation layer**, which by construction never carries
manual-curation rows. `coverage_gap_registry.csv` already diagnoses this correctly as
`RECOVERABLE_NBS514_MANUAL_TRANSCRIPTION` / "机制性缺席, 不是数据丢失" (mechanistic absence, not data loss).
B03 took a known *mechanistic* absence and re-labelled it as *no observation*.

### 4.1 "NO_NBS514_COVERAGE" is a tautology

NBS Circular 514 is a 1951 compilation. EC (ethylene carbonate as a battery solvent), PC, FEC and VC are
carbonate/electrolyte solvents whose use post-dates — in FEC's and VC's case by decades — that compilation.
**Their absence from a 1951 table is guaranteed and carries no information.** Presenting
`NO_NBS514_COVERAGE` for these four as a *finding*, with next action "需另寻来源" (must find another source),
implies the project looked and came up empty, when in fact usable sources are already in the repository.
This is the most misleading single element of the report.

---

## 5. Pre-1960 measurement methodology — admissibility attack

The admitted values rest on **Williams & J. W. Krchma, J. Am. Chem. Soc. 49, 1676 (1927)** (NBS514 reference 63)
and, for MA, additionally ref 260 (Phadke et al., J. Indian Chem. Soc. 22, 235, 1945). Both EA and MA cite ref 63.

Defects, all confirmed from the transcript:

1. **Frequency unknown.** `frequency_note` is `NaN` for both rows. Only 44 of 200 rows in
   `nbs514_organic_part1.csv` carry any frequency statement at all. Static permittivity is only defined at ω→0;
   a 1927 conductance-bridge measurement is typically somewhere in the audio-to-RF band where ε is dispersing.
   **B03's own CSV asserts `frequency = "static (NBS514 tabulates static values)"` — that is an
   unsupported inference, not a documented fact.** It is an `INFERRED` claim presented in a `DOCUMENTED` column.
2. **No purity statement.** No mol-fraction, no drying protocol, no water content. Esters are hygroscopic;
   absorbed water raises ε sharply (ε_water ≈ 80).
3. **No temperature control.** NBS514 records integer °C ("25"), yet the deliverable reports `298.15 K` —
   a **0.15 K precision claim that the source does not support**. The transcript's own `T_K` column performs
   this conversion mechanically (`t_C=25 → 298.15`).
4. **No uncertainty.** v04 `uncertainty = NaN` for both rows. 101 of 248 v04 rows do carry uncertainty; these do not.
5. **Secondary relay, not primary.** The compilation is not the experiment. B03 grades this `DOCUMENTED`
   (strongest grade) when it is at best `INFERRED`.

### 5.1 Systematic bias direction

**Upward (positive) bias.** Two mechanisms push ε too high:

- **Water uptake in hygroscopic esters** — ε_water ≈ 80 vs ε_ester ≈ 6, so even ~1 wt% water moves ε by
  several percent in the positive direction. This is a one-sided error: contamination can only raise ε here.
- **Frequency dispersion** — measured below the static limit, ε(ω) ≤ ε(0) for a Debye-type liquid, so a
  non-zero measurement frequency biases ε **downward**, partially masking the water effect. Net direction is
  not analytically determinable, which is precisely why an unstated frequency is disqualifying.

Both effects are one-sided and neither is quantified, so the values cannot carry a defensible uncertainty budget.
They should not enter an ML training set at a grade that lets the model treat them as ground truth.

---

## 6. Contradicting values for EA and MA — **FOUND**

I swept every CSV under `data/` and `outputs/` (77 files contain the EA/MA inchikeys) for ε.

### 6.1 `data/raw/open_data_eps/eps_observations.csv` (CC BY 4.0, held in-repo)

| mol | ε | T_K | source |
|---|---:|---:|---|
| EA | **6.081** | 293.15 | PMC11397147 |
| EA | **6.500** | — | PMC12558406 |
| EA | **6.000** | — | PMC13567569 |
| EA | 6.020 | — | PMC11220793 |
| MA | **7.072** | 288.15 | PMC11397147 |
| MA | **7.200** | — | PMC12558406 |

**EA:** 6.000 – 6.500 at/near room temperature, against the admitted 6.02. The 6.081 @ 293.15 K leg is the most
damaging: it is a *real temperature-qualified* measurement, and the 6.02 @ 298.15 K value is 1.0% lower at a
5 K higher temperature — which is at least the right *sign* (ε falls as T rises) but the magnitude is larger
than the 3-significant-figure precision B03 implies.

**MA — the serious one:** 7.072 @ 288.15 K and 7.200 (no T) against the admitted **6.68 @ 298.15 K**.
7.072 vs 6.68 is **+5.9%**, at a temperature only **10 K lower**. ε rises as T falls, so a 288 K value *above*
the 298 K value is directionally consistent, but 5.9% over 10 K implies a temperature coefficient of roughly
−0.6%/K, which is far too steep for methyl acetate (typical dε/dT for esters ≈ −0.15 to −0.2 %/K, i.e. ~1.5–2%
over 10 K). **The two legs cannot both be correct static permittivities of the same pure substance.**
Either 6.68 is low, or 7.07/7.20 are not static (they may be RF or solution values). B03 neither found nor
reconciled this, despite claiming a condition-qualified pair.

### 6.2 What I did *not* find

No contradicting value in any ledger, feature table, or modelling artefact. All internal tables
(`v03_original_243`, `dielectric_v02…v04`, `dielectric_pool_expansion_*`, `dielectric_physical_features*`,
`themol_orbital_layer*`, `w21_chemical_space_metadata`, `four_core_key_registry`, `nbs514_structure_candidates`,
`expansion_observations`) reproduce 6.02 / 6.68 exactly — but that is **circular**, because they all descend from
the same single NBS514 row. 21 occurrences of 6.02 and 20 of 6.68 are one observation counted many times, not
21 independent confirmations.

The apparent outliers (ε = 1.00, 7.58, 18.00, 35.688, 80.40) are **not** measurements — they are the continuum
dielectric constants of the SMD/xtb solvation environments (gas, THF, benzaldehyde, acetonitrile, water) in
`data/processed/redox_state_legality_registry.csv`. Correctly excluded.

---

## 7. Independence — partially propagated, and B03 missed a pair

### 7.1 What B03 got right

The report does state: *"「独立来源数」在本数据集中是一个**上界**，不是实测值"* (the independent-source count is an
upper bound, not a measured value) and directs B07 to deduplicate by document first. That caveat is present and
correct.

### 7.2 Where it fails

- `independent_source_map.csv` has `shared_a18_molecules` **empty for all 8 pairs** — the column exists but was
  never populated, so the 8 pairs cannot be joined back to the A18 molecules they affect.
- Only **2 of the 8** entangled documents are A18 source documents (`10.1016/j.tca.2012.10.024` for TEGDME,
  `10.1021/je900503p` for GBL). So "8 entangled pairs" overstates relevance to A18 — it is a whole-dataset
  finding reported in an A18 deliverable.
- `A18_gap_register.csv` still reports `independent_source_status` per molecule with **no discount applied**:
  DMSO remains `CLUSTER_GE3` (4 sources) while the report's own logic says that cluster must be deduplicated.
  A reader of the register alone would take `n_source_documents = 4` as four independent experiments.
- **EA and MA are entangled with each other and B03 did not notice.** Both entries cite NBS514 reference **63**
  = Williams & I. J. Krchma, *J. Am. Chem. Soc.* **49**, 1676 (1927). MA additionally cites 260. So the two
  "new" measurements are two rows from one 1927 paper (plus one 1945 paper), not two independent experiments.
  B03's entanglement detector only compares exact `(inchikey, T, ε)` tuples, so it structurally cannot catch
  shared-reference entanglement. The 8-pair count is therefore a **lower bound on entanglement**, which directly
  undercuts the report's claim that the source count is an upper bound — both bounds are in fact wrong.

---

## 8. Fatal flaw hunt: is 5 + 13 = 18 a valid closure?

**Arithmetically yes, semantically no.** The closure is a tautology: 18 molecules are partitioned into a
"resolved" set and an "unresolved" set, so any split sums to 18. The number carries no evidential content.
The substantive errors are in *which bucket*:

1. **EA and MA are in the wrong bucket.** Every machine-readable register in the repository
   (`A18_gap_register.csv`, `condition_pair_validity_v1.csv`, `aggregate_contribution_ledger_v1.csv`,
   `joint_eligibility.csv`) says they have 0 condition-valid pairs and are not admitted. Only the prose report
   and `b03_gate_status.json` say they are resolved. The prose was written to match the narrative, not the data.
2. **Internal contradiction on the same molecules.** `A18_gap_register.csv` reports
   `n_observations = 0` for EA while `dielectric_v04.csv` holds a `model_ready = True` EA row from the same DOI.
   Both files were generated in the same work package. One of them is wrong, and B03 shipped both.
3. **The "unresolved" bucket is also mislabelled.** Seven molecules are filed under
   `NO_OBSERVATION_AND_NO_PAGE_READ` / `ZERO_OBSERVATIONS` despite holding curated primary values.
4. **B03's gate file self-reports a defect it then ignores.** `b03_gate_status.json` sets
   `"has_condition_qualified_evidence": true` and `"accounting_closed": true` while the same file records both
   condition-qualified rows as awaiting review. The gate is open on evidence that is, by the file's own
   admission, not yet evidence.

**Net: the closure is formally closed and substantively unsound. FAIL.**

---

## 9. The three most serious findings

1. **Zero new evidence, presented as 2 new measurements.** Both values already sat in the frozen
   `dielectric_v04.csv` (and in the frozen modelling set `v03_original_243.csv`) from the identical
   `source_record_id`, ~58 days before B03 ran. B03 added no ledger rows, no molecules, no observations.
   The entire deliverable is a confirmation of prior state.

2. **The 5/18 "resolved" count is inflated and contradicts B03's own registers.** Three separate artefacts in
   the repository record EA and MA as `n_condition_valid_pairs = 0` / `condition_pair_valid = False` /
   `MISSING_CERTIFICATE`. The defensible figure is 3/18; on an "admitted evidence" reading it is 0/18.
   B03 also shipped a file claiming EA has `n_observations = 0` while another file in the same work package
   holds a `model_ready = True` EA row.

3. **"NO_NBS514_COVERAGE" and "NO_OBSERVATION" for the 7 molecules are false and misleading.** All seven hold
   curated v04 values with real DOIs — four of them graded `primary`. And demanding NBS514 coverage from EC, PC,
   FEC and VC, which post-date a 1951 compilation, is a tautology dressed as a research finding. The report's
   framing makes the evidence base look emptier than it is, while simultaneously overstating what B03 itself
   achieved.

### Secondary finding worth escalating

**MA has an unreconciled 5.9% value conflict** with an in-repo CC BY 4.0 source (7.072 @ 288.15 K vs admitted
6.68 @ 298.15 K) that is too large to explain by the 10 K temperature difference. EA likewise spans
6.000–6.500 in the same held source. Neither is mentioned anywhere in B03.

---

## 10. Explicit statement of search effort

Per the mandate, I actively searched for counter-evidence before assigning any grade:

- Re-extracted the PDF pages directly (pymupdf), not trusting the transcript — confirmed honest transcription.
- Swept all 77 CSVs under `data/` and `outputs/` containing the EA/MA inchikeys for every ε value.
- Checked all 6 `dielectric_v0*` versions plus `v03_original_243` for prior occurrence.
- Cross-checked `condition_pair_validity_v1`, `aggregate_contribution_ledger_v1`, `joint_eligibility`,
  `coverage_gap_registry`, `A18_gap_register`, `nbs514_verification.json`, `b03_gate_status.json`,
  `b03_registers.json`.
- Verified all 4 NBS514 organic parts for duplicate EA/MA entries (only one each).
- Extracted the NBS514 reference list and resolved refs 8, 63, 260, 276.
- Verified mtimes to establish chronology.
- Checked the measurement ledger (2065 rows) — 0 rows for EA, MA, and all 7 "no observation" molecules.

**No PASS was issued for any row, because counter-evidence was found in every case.** I could not construct a
reading under which B03 grew the evidence base.

## 11. Recommended actions

| # | Action |
|---|---|
| 1 | Withdraw the "5/18 resolved" figure. Restate as **3/18** resolved, 2 pending review, 13 unresolved. |
| 2 | Re-grade EA/MA from `DOCUMENTED` to `INFERRED`: the `frequency = "static"` claim is an inference, not a source statement. |
| 3 | Hold EA/MA for primary sources (Williams & Krchma 1927 is reachable) rather than accepting a 1951 secondary relay. |
| 4 | Reconcile the MA 6.68 vs 7.072 @ 288.15 K conflict before either value enters any training set. |
| 5 | Rename the 7 molecules' reason from `NO_OBSERVATION` to `NO_THERMOML_OBSERVATION`; they hold curated v04 values. |
| 6 | Delete `NO_NBS514_COVERAGE` as a finding for EC/PC/FEC/VC — it is chronologically guaranteed and uninformative. |
| 7 | Extend the entanglement detector to shared bibliography (reference-level), not just identical `(inchikey, T, ε)` tuples. EA–MA via ref 63 is a live example it misses. |
| 8 | Populate `shared_a18_molecules` in `independent_source_map.csv`, or drop the column and stop reporting 8 pairs as an A18 result. |
| 9 | Add an uncertainty column for NBS514-derived rows, or mark them `uncertainty = UNKNOWN` rather than leaving `NaN` to be read as zero. |
