# Reviewer 2 Report — Source Literature, DOI, Original Measurement and Source Independence

**Project:** electrolyte-solvent-dielectric-ml · **Work package:** B02 · **Reviewer:** Reviewer 2 of 4 (independent)
**Input (frozen):** `outputs/admission_v2/admission_review_queue.csv` — 70 queue rows / 62 distinct measurements, sha256 `1b701aaa31256051562b09d4046c34fa39eb2a5416fbfd7e685841d2582cdbab`
**Output:** `outputs/admission_v2/reviewer_2_decisions.csv` (70 rows)
**Scope judged:** DOI validity · source document identity (hash) · source independence · DOI ≠ independence · transcription integrity · provenance completeness. **Out of scope:** statistics, ML validity, phase/pressure physics (other reviewers).

---

## 1. Verdict counts

| Decision | Rows | Distinct measurements |
|---|---:|---:|
| **PASS** | 30 | 30 |
| **HOLD** | 1 | 1 |
| **FAIL** | 39 | 31 |
| **Total** | **70** | **62** |

| Evidence grade | Rows |
|---|---:|
| DOCUMENTED | 61 |
| INFERRED | 9 |
| INSUFFICIENT | 0 |

| Independence assessment | Rows |
|---|---:|
| SINGLE_SOURCE_OK | 37 |
| MULTI_SOURCE_LOSSY | 24 |
| INDEPENDENCE_UNVERIFIED | 0 |
| NOT_APPLICABLE | 9 |

| `ledger_entry_found` | Rows |
|---|---:|
| true | 61 |
| false | 9 |

Cross-tab of my decision against the frozen `j03_verdict`:

| j03_verdict | PASS | HOLD | FAIL |
|---|---:|---:|---:|
| RAW_SINGLE_OBSERVATION | 15 | 0 | 0 |
| SINGLE_SOURCE_AGGREGATE | 7 | 0 | 0 |
| MULTI_SOURCE_AGGREGATE | 1 | 0 | 0 |
| AGGREGATION_UNDOCUMENTED | 7 | 0 | 0 |
| COMPOSITE_CONDITION_UNMATCHED | 0 | 0 | **30** |
| PROVENANCE_INCOMPLETE | 0 | 1 | **9** |

---

## 2. Method

Every judgement was recomputed from primary artefacts, not taken from the queue's own labels.

1. **DOI validity.** All 24 distinct `source_group` values in the queue were resolved live against `api.crossref.org`. **24/24 resolved** to real records with title, container, year, volume, page and author list. Every one is a well-formed `10.xxxx/...` string; none is an `arXiv:` string, a placeholder, or malformed. No fabricated DOI was found. (I still read the queue's `doi_checked` column as the DOI I examined, not as a claim of resolvability, and I recorded the resolution outcome inside `evidence_detail`.)

2. **Source document identity.** I re-hashed every `source_file` in `source_document_registry_v1.csv` (61 documents) and every distinct `(source_file, source_file_sha256)` pair in `measurement_ledger_v1.csv` against the bytes on disk. **61/61 registry hashes and all ledger hashes match — zero mismatches, zero missing files.** The document-identity layer of this project is genuinely sound; the defects are downstream of it.

3. **Queue→ledger join.** I mapped each queue row to its `v04row-NNN` aggregate via `measurement_id`, then enumerated every `measurement_ledger_v1` row in that aggregate, keeping `source_document_id`, `source_file_sha256`, `temperature_K`, `dielectric`, `source_row_index`. I then tested whether the reported `(T, ε)` is an **actual observation** in the named DOI, in any DOI, or nowhere.

4. **Independent XML re-check.** For the 61 ThermoML rows I re-parsed the raw XML myself (compound order → `nOrgNum` → `<ePropName>` → `<nPropValue>`), rather than trusting the ledger. This caught the fact that the ledger's own extraction is correct for these rows: **33/61 reported ε values are literal `<nPropValue>` permittivity entries in the source XML, and 32 of those sit in the same observation block as the stated temperature.** The 28 that are not literal are exactly the 28 `COMPOSITE_CONDITION_UNMATCHED` ThermoML rows.

5. **Source-loss adjudication.** For every row with a non-empty `sources_lost_in_gap` I computed, per lost DOI, the exact set of `(T, ε)` observations it contributes and tested whether that set is a **subset** of the retained DOI's observations. A subset ⇒ the lost source is a duplicate re-report, not an independent contributor.

6. **Duplicate-detection across DOIs.** Grouping the whole ledger by `(inchikey, T, ε)` and keeping groups spanning >1 document produced **27 exact-duplicate observation groups across 8 DOI pairs** — decisive evidence that "one DOI = one independent experiment" is false here.

I did not modify any input file. The generator script is `outputs/admission_v2/_r2_gen_decisions.py` (auxiliary, reproducible).

---

## 3. Most serious findings

### 3.1 CRITICAL — Nine records cite a DOI that is *not* the document holding their value (misattribution)

For 5 queue rows the reported ε is **not present anywhere in the named `source_group`**; it exists only in a *different* DOI that was dropped from the gap:

| queue_id | measurement_id | named `source_group` | ε | DOI that actually holds ε |
|---|---|---|---|---|
| Q-PRI-EPSV04-R031 | EPSV04-R031 | 10.1016/j.fluid.2013.12.014 | 46.05 | **10.1021/je9010773** |
| Q-CCU-EPSV04-R031 | EPSV04-R031 | 10.1016/j.fluid.2013.12.014 | 46.05 | **10.1021/je9010773** |
| Q-J02A-EPSV04-R031 | EPSV04-R031 | 10.1016/j.fluid.2013.12.014 | 46.05 | **10.1021/je9010773** |
| Q-CCU-EPSV04-R044 | EPSV04-R044 | 10.1016/j.fluid.2009.07.009 | 25.02 | **10.1016/j.jct.2012.08.009** |
| Q-CCU-EPSV04-R057 | EPSV04-R057 | 10.1016/j.fluid.2013.12.014 | 33.60 | **10.1021/je800593p** |

`10.1016/j.fluid.2013.12.014` is *Guo-Zhu & Jie, "Dielectric constant of dimethyl sulfoxide–monohydric alcohol mixture solution at the microwave frequency", Fluid Phase Equilib. 365 (2014) 5–10* — a DMSO–alcohol mixture paper. It is the **sole** ledger contribution to v04row-031 at T=298 K with ε = **49.0**, not 46.05. The 46.05 that the queue reports is the *median of 35 observations pooled across four sources*, and the observation closest to it comes from `10.1021/je9010773` (25 near-298 K observations of ε ≈ 45.4–46.1). The DOI printed on the record therefore names a paper whose number is not the number on the record. This is worse than a lossy aggregate: it is a **false citation**, and it is the single most damaging provenance defect I found.

### 3.2 CRITICAL — 23 "measurements" are arithmetic medians, not measurements

23 of the 30 `COMPOSITE_CONDITION_UNMATCHED` rows report an ε that is **not an observed value anywhere in the entire ledger** for that molecule — it is the arithmetic median of the in-band pool:

- `Q-CCU-EPSV04-R080` / EPSV04-R080: ε = 11.8861 from `10.1021/je700343t`. The ledger holds **32 in-band observations** for WZLFPVPRZGTCKP-UHFFFAOYSA-N (ε from 11.2337 to 12.5349); 11.8861 is the median of the 32, and no observation equals it. Single source, but 32 separate measurements collapsed into one fabricated-looking value.
- `Q-CCU-EPSV04-R084` / EPSV04-R084: ε = 10.76 from `10.1021/je300234g`; observations are 10.58, 10.70, 10.82, 10.95 — median = 10.76, an interpolated value between two observations.
- `Q-CCU-EPSV04-R091` / EPSV04-R091: ε = 2.40445 from `10.1016/j.jct.2012.04.011`; the ledger holds only **2.38**, and the T = 297.385 K is likewise a median.
- `Q-CCU-EPSV04-R083` / EPSV04-R083: ε = 78.87 from `10.1016/j.fluid.2014.05.006`; the single observation is **80.0** — the reported value is not even the median of the named source's own observations.

In all 30 composite rows the reported ε equals the median of the pooled in-band set to 1e-6 (`E_eq_medall = 30/30`), and `aggregation_method` is `NOT_DOCUMENTED` in `aggregate_contribution_ledger_v1`. A downstream ML model would treat these as point measurements with an uncertainty; they are pooled statistics with an undocumented rule.

### 3.3 CRITICAL — The nine NBS Circular 514 records have no document identity in the provenance chain

`10.6028/nbs.circ.514` is a **valid DOI** — it resolves in Crossref to *Maryott, A. A., "Circular of the Bureau of Standards no. 514", National Bureau of Standards, 1951, type=report*. But it is **absent from both** `source_document_registry_v1.csv` (61 documents, no NBS entry) and `measurement_ledger_v1.csv` (**zero** rows with that `source_document_id`). Consequently:

- no `source_file_sha256` is bound to these records anywhere in the chain;
- `aggregate_contribution_ledger_v1` marks them `contribution_status = MISSING_CERTIFICATE` / `NO_BAND_OBSERVATIONS_IN_SOURCE_LAYER`;
- `j03_verdict = PROVENANCE_INCOMPLETE` = **no contributing measurement found**.

Affected: `EPSV04-R115, R144, R147, R156, R171, R173, R195, R203, R206`.

To be fair to the record, the numbers are **not invented**. I located `data/raw/nbs514/nbscircular514.pdf` (sha256 `cb3fa9239fd977d7fa85389fbc219baea69667d5cc7c9e5382b09157fda40683`) and found each value in the non-chain extraction file `data/raw/nbs514_expansion/expansion_observations.csv` (`nbs514:p28:015` → 13.11; `nbs514:p31:006` → 11.5; `nbs514:p32:001` → 14.0; `nbs514:p23:012` → 2.100; `nbs514:p14:003` → 2.30; `nbs514:p30:003` → 9.18; `nbs514:p26:005` → 5.42; `nbs514:p30:015` → 5.42; `nbs514:p23:001` → 2.32). That file's sha256 `32648c0e…` is registered nowhere. So these are **plausibly genuine page reads that were never wired into the ledger** — grade INFERRED, not DOCUMENTED, and they cannot PASS. Two spot checks against the PDF text layer are consistent (`13.1` on printed p20 for the MIBK row; `11.5` for o-cresol on printed p23), though OCR garbling means I flag rather than certify.

### 3.4 HIGH — The "duplicate source" defence rescues only 3 of 27 lossy rows

Source loss is real: **27 queue rows / 21 distinct measurements** carry a non-empty `sources_lost_in_gap`, totalling **50 dropped source-slots across 18 distinct DOIs**. Most frequently dropped: `10.1021/je060248p` (6×), `10.1016/j.tca.2012.10.024` (5×), `10.1016/j.jct.2010.09.008` (5×).

Applying my subset test, only **3 rows** have lost sources that are provably duplicates of the retained one:

- `EPSV04-R059` — lost `10.1016/j.fluid.2009.07.009` contributes exactly (303.15 K, 41.17), byte-identical to the retained `10.1016/j.fluid.2008.01.024` observation.
- `EPSV04-R071` — lost `10.1016/j.fluid.2009.07.009` contributes (303.15 K, 17.18), byte-identical to the retained `10.1016/j.fluid.2008.01.024` observation.
- `EPSV04-R068` — lost `10.1016/j.tca.2012.10.024` contributes the same three (T, ε) points (293.15/1.968, 298.15/1.961, 303.15/1.954) as the retained `10.1016/j.tca.2012.05.036`.

All three pairs are the **same author group re-reporting one measurement** (Sengwa/Khatri/Sankhla in Fluid Phase Equilib. 2008 vs 2009; Alonso/González/García de la Fuente/Cobos in Thermochim. Acta 2012 vs 2013). These three rows PASS, but only because the loss is *proven* benign — and their `n_contributing_sources = 2` still **overstates independence**, since the true independent count is 1.

The other 24 lossy rows are `MULTI_SOURCE_LOSSY` and FAIL.

### 3.5 HIGH — `n_contributing_sources` systematically overstates independence

I found **27 exact-duplicate `(inchikey, T, ε)` observation groups spanning 8 DOI pairs**. The largest offenders:

| Duplicate observations | DOI pair | Interpretation |
|---:|---|---|
| **15** | `10.1021/je3007666` ↔ `10.1021/je800593p` | Klimaszewski/Boruń/Bald/Sengwa vs Chmielewska/Żurada/Klimaszewski/Bald — same group, same numbers |
| 5 | `10.1016/j.fluid.2008.01.024` ↔ `10.1016/j.fluid.2009.07.009` | Sengwa group, two papers, one measurement |
| 3 | `10.1016/j.tca.2012.05.036` ↔ `10.1016/j.tca.2012.10.024` | Alonso/Cobos group |
| 2 | `10.1021/je060248p` ↔ `10.1021/je800593p` | Uosaki et al. vs Chmielewska et al. |
| 2 | `10.1021/je3007666` ↔ `10.1021/je900503p` | shared provenance |
| 2 | `10.1021/je800593p` ↔ `10.1021/je900503p` | shared provenance |
| 1 | `10.1021/je060248p` ↔ `10.1021/je900503p` | shared provenance |
| 1 | `10.1021/acs.jced.8b00755` ↔ `10.1021/je060248p` | shared provenance |

`n_contributing_sources` counts *distinct DOI strings*, not independent experiments. Every row reporting `n_contributing_sources ≥ 2` built on these pairs is inflated. The registry itself concedes this: `experimental_independence_status = not_evaluated` for **all 61** documents, with the note that document identity does not establish experimental independence. **No record in this dataset has an evidence-backed independence claim.** My `SINGLE_SOURCE_OK` label therefore means "one document, one measurement, no cross-source pooling claimed" — it is *not* an assertion that the underlying experiment is independent of other rows for the same molecule.

### 3.6 MEDIUM — One rule deviation, declared

`EPSV04-R247` (Q-WS-EPSV04-R247) is `j03 = PROVENANCE_INCOMPLETE`, which per my instructions mandates FAIL. **I did not apply FAIL here, and I am flagging that openly.** A contributing measurement genuinely exists: ledger `MSR-b99e9bffc309a7a8`, `source_row_index` 8073, ε = 56.09 at T = 333.15 K from `10.1021/je300958c` (sha256 `9c3a2f8c4017b916a6e7eb2a5957de40bbfa4556eb7d6bcbba3fa33aa3d06080`), and 56.09 is a literal `<nPropValue>` in the raw XML. The `PROVENANCE_INCOMPLETE` label is an **aggregate-window artefact**: 333.15 K is outside the 293.15–303.15 K band, so `in_aggregate_window = false`, `aggregate_id = not_evaluated`, `contribution_status = MISSING_CERTIFICATE`. I graded it **HOLD** because it is not a provenance failure but also cannot be admitted while it sits outside the declared window and carries a blocking j03 label. If the panel prefers a literal reading of the rule, this single row should be flipped to FAIL; the other 9 `PROVENANCE_INCOMPLETE` rows are unambiguous FAILs.

---

## 4. Systematic issues

1. **The aggregation is undocumented by construction.** `aggregation_method = NOT_DOCUMENTED` for 213 of 248 rows in `aggregate_contribution_ledger_v1`; only 21 rows carry the R219 median-in-window rule and 14 a temperature-failure rule. 36 of the 70 queue rows map to aggregates with `aggregation_documented = false`. Any claim of "transcription" for those rows is unsupported, which is why I never grade them better than DOCUMENTED-on-the-value but FAIL-on-the-pair.

2. **The 293.15–303.15 K window is doing silent work.** `EPSV04-R247` is excluded purely by window membership. `EPSV04-R051` (39.78 at exactly 298.00 K) survives. The band is a modelling choice presented as a provenance fact.

3. **Track duplication inflates the apparent evidence base.** 4 measurements (`EPSV04-R031, R085, R086, R099`) appear **3× each** across the `P0_P1_NAMED_MOLECULE`, `COMPOSITE_CONDITION_UNMATCHED_22` and `J02A_REQUIRES_HUMAN_REVIEW_4` tracks. 70 rows = only 62 measurements. Consensus counting must be per-measurement, not per-row, or these 4 records get 3 votes each.

4. **`EPSV04-R086` has a temperature inconsistency across tracks.** `Q-PRI-EPSV04-R086` and `Q-CCU-EPSV04-R086` report T = 295.65 K, while `Q-J02A-EPSV04-R086` reports **T = 293.15 K** for the same measurement_id and the same ε = 41.99. The ledger holds two observations at 293.15 K (ε = 42.34 and 42.81) and one at 298.15 K (41.64); 41.99 is the median of the four in-band values and 295.65 is their median temperature. The J02A track's 293.15 K is not reproducible from the ledger — a transcription defect independent of the median problem.

5. **`arXiv:1506.00262` is silently appended to 45 rows.** `data/dielectric_v04.csv` `source_dois_all` carries `arXiv:1506.00262` (Chodera et al., *Towards Automated Benchmarking of Atomforcefields…*, arXiv:1506.00262v1 — I resolved it and it is a **benchmarking/re-analysis** paper, not an experimental source). It is correctly excluded from `contributing_sources` in the audit layer, so the queue itself is clean, but its presence in the upstream `source_dois_all` column is a live trap: any downstream consumer reading `source_dois_all` would count a re-analysis paper as an independent experimental source. Worth a schema-level guard.

6. **`condition_pair_valid` is empty in the queue.** `j04_condition_pair_valid` and `j04_invalidity_reason` are blank for **all 70 rows**, while `condition_pair_validity_v1.csv` has real values for 100 rows (`false` for 170 of 248 aggregates, 78 `true`). The queue failed to propagate the j04 result. I reconstructed it: all 30 composite rows are `condition_pair_valid = false`, and the 40 worksheet rows are `true`. A reviewer trusting the queue column would see no j04 signal at all.

7. **DOI ≠ independence, confirmed empirically.** One DOI never means one independent experiment in this corpus (see §3.5), and multiple DOIs frequently mean one experiment (27 duplicate groups). Both failure modes are present simultaneously.

---

## 5. What I could not verify

- **NBS 514 values against the PDF text layer.** The scanned PDF's OCR is badly garbled (e.g. "13.1" for 13.11, "2. 100" for 2.100, "1 1 .5" for 11.5). I confirmed the values appear in the extraction file and that spot-checked digits are consistent, but I did not certify each digit against the printed page. Grade INFERRED.
- **Whether the same-author duplicate pairs are truly one experiment or two independent runs.** I can prove the *numbers* are byte-identical, which makes independent measurement implausible; I cannot prove they were not two runs reported identically. The conservative reading (treat as one) is what I used.
- **Journal-level content for paywalled DOIs.** Crossref metadata resolved for all 24, but I did not open full texts. Resolution is evidence of existence, not of the specific value.
- **Non-resolution is not non-existence.** I note this because zero DOIs failed to resolve — but had any failed, I would have graded INFERRED rather than called fabrication.

---

## 6. Bottom line

The **DOI layer is clean** (24/24 real, well-formed, resolvable) and the **document-identity layer is clean** (61/61 sha256 verified against disk, zero mismatches). The failure is entirely in the layer that converts documents into admitted measurements:

- **39 of 70 rows FAIL** — 30 because the reported `(T, ε)` is a synthetic median of pooled observations (23 of which are not observed anywhere), 9 because the cited NBS report has no entry in the ledger or registry.
- **5 rows cite a DOI that does not contain their own value** (§3.1) — the most serious finding.
- **24 of 27 lossy rows** cannot be rescued: the dropped sources are genuine independent contributors, not duplicates.
- **Only 3 rows** (R059, R068, R071) survive with source loss, and only because I could prove the loss was a duplicate re-report.
- **Independence is asserted nowhere and verifiable nowhere**: `experimental_independence_status = not_evaluated` for all 61 documents, and 27 exact-duplicate observation groups show that distinct DOIs routinely mean one experiment.

I recommend that no record be admitted on the basis of `source_group` alone; each must carry a `measurement_id`-level certificate binding `(molecule, T, ε)` to a specific `source_document_id` + `source_file_sha256` + `source_row_index`, which only the 30 PASS rows currently have.
