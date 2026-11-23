# Reviewer 2 — Measurement Sources, Conditions and Data Independence

**Dataset under review:** B100, 257 molecules of pure-liquid static relative permittivity (εr), project `electrolyte-solvent-dielectric-ml`, PLAN B v6.0.
**Reviewer:** 2 of 4 (independent). **Scope:** provenance, conditions, source independence, duplicates.
**Verdict file:** [`b100_reviewer_2.csv`](b100_reviewer_2.csv) — 6 rows.
**Verdicts:** PASS 2 · HOLD 2 · FAIL 2.

Nothing in the existing tree was modified. Every number below was recomputed from the files listed in §7.

---

## 0. Bottom line

| item | decision | evidence_grade | eligibility_verified | lineage_complete | shared_source_found |
|---|---|---|---|---|---|
| dataset_257 | **HOLD** | INFERRED | false | false | true |
| NBS_frequency_audit | **PASS** | INFERRED | true | true | true |
| phase_verification | **FAIL** | INSUFFICIENT | false | false | false |
| source_independence | **HOLD** | INFERRED | true | false | true |
| Q1_Q2_grading | **PASS** | DOCUMENTED | true | true | false |
| cross_source_agreement | **FAIL** | INFERRED | false | false | true |

Three sentences:

1. The **257 count is safe** (147/257 survive without the fabricated melting points, so the ≥100 threshold holds), but the claim "all 257 are phase-verified liquid" is **false**: 110/257 melting points are parser fabrications, most of them literally the digit `1` from `InChI=1S/…`.
2. The **NBS frequency audit is done correctly in the only way it can be done** — 127 high-frequency rows really were excluded and none leaked in — but "static" is an *inference from an absent footnote*, not a documented per-row condition, and that is what the project's own wording says.
3. The **independence accounting is honest in headline but wrong in mechanism**: the "18 corroborated" flag tests *presence in both layers*, not agreement; 6 of the 18 were never compared; and all 11 molecules that *did* disagree were deleted by the same gate that then certifies the rest as conflict-free.

---

## 1. NBS admission and the frequency audit — PASS (INFERRED)

**Claim:** empty `frequency_mhz` means "source-level static definition", not "unknown frequency", because 127 high-frequency rows were excluded.

Verified, row by row, in `outputs/b100/nbs514_condition_audit.csv` (392 rows):

- `frequency_status` = `STATIC_BY_SOURCE_DEFINITION` for **392/392**; `expansion_frequency_mhz` blank **392/392**; `transcription_frequency_note` blank **392/392**; `transcription_found` true **392/392**.
- The exclusions are real: `data/interim/nbs514_organic_part{1..4}.csv` contains **127** rows whose `frequency_note` is a high-frequency value (57 × 5×10⁸, 35 × 4×10⁸, 27 × 3.6×10⁸, 9 spaced variants, 1 annotated "reference 60"). **0/127** appear in `data/processed/dielectric_pool_expansion_observations.csv`, and **0/226** admitted molecules carries a note.
- 636 transcription rows − 392 selected = **244** unselected, of which **127** are the frequency rows and **117** are other rejections (140 `two_or_less`, 16 `candidate_exception` before de-duplication).
- The transcription shows the convention: NBS 514's organic table mixes static values with a second table of high-frequency values, marked by footnote (e.g. `nbs514:p13:010` formic acid, ε 58.5 at 16 °C, `f=4×10⁸ cycles/sec`; `nbs514:p14:005` bromal). Marking those out is the right move.

**Why INFERRED and not DOCUMENTED:**

- The label is assigned *mechanically* from an empty note: `build_b100_asset_inventory.py` L167-170 — `"STATIC_BY_SOURCE_DEFINITION" if src` else `"UNVERIFIED"`, with no per-row evidence column. It is a naming convention for "no footnote", and it cannot fail.
- The audit is built **from the already-filtered observation set**, so it is tautologically 392/392 static. Excluding high-frequency rows does not *prove* the remaining rows are static; it proves only that they carry no high-frequency footnote. (The project's own readiness text is careful here — "必须标记为来源级静态定义, 不得与逐条报告频率的 ThermoML 测量等同" — and that wording is what saves the item.)
- **37/226** admitted molecules cite at least one primary reference that *also* produced a high-frequency row, so the source-level rule cannot establish which value was transcribed for them. Examples: `nbs514:p35:007` m-xylene (refs 3,12,16,35,107,116,207,229), `nbs514:p41:004` 1-bromonaphthalene (refs 272 [7,12]), `nbs514:p39:016` propylbenzene (refs 3,35 [1,7]).
- The 226 rest on **122 distinct NBS reference numbers** (ref 272 → 23 molecules, 82 → 19, 7 → 18), i.e. the compendium is not even internally monolithic — which cuts both ways: not 226 independent measurements, but not one laboratory either.
- Re-verifiability: `frequency_note` is **not present in `raw_line`** (0/636), so the 127 exclusions can only be re-checked against the printed PDF. The pointer (source_id + page + references) exists, so I still score `lineage_complete = true`.

---

## 2. Phase verification — FAIL (INSUFFICIENT)

**Claim:** all 257 are "phase-verified liquid" (mp < T_meas).

### 2.1 The mechanism

`pubchem_mp_lookup_b100.csv` has a `mp_note` column that the phase audit **ignores**. Among the 257:

| note class | n (of 257) | what it is |
|---|---:|---|
| `ASSUMED_C` | **110** | no unit-tagged mp found; parser took the first bare number in −150…400 from *any* property string |
| `CONVERTED_FROM_F` | 67 | real value, °F→°C |
| `OK` | 43 | real value |
| HSDB / PAC / ILO | 37 | real value, sourced |

`fetch_pubchem_mp_b100.py` L144-163 is explicit:

```python
# no unit-tagged value found: accept a bare number only if it is plausible as C
...
if -150.0 <= v <= 400.0:
    return round(v, 3), f"ASSUMED_C: {raw[:70]}"
```

For 85 of the 110 the "property string" is an InChI, so the number is the **`1` of `InChI=1S/…`**; 18 are `2.0`, 6 are `3.0`, 1 is `−1.0`. Examples:

| InChIKey | name | fabricated mp | T_meas |
|---|---|---:|---:|
| CKVJSNYSBIZAAE-UHFFFAOYSA-N | 1,2-Dibromoheptane | 1.0 °C (from `InChI=1S/…`) | 298.15 K |
| ZMUYMRCYZZYRSL-UHFFFAOYSA-N | 1-Bromo-2-ethoxyheptane | 1.0 °C | 293.15 K |
| HNTGIJLWHDPAFN-UHFFFAOYSA-N | 1-Bromohexadecane | 1.0 °C | 298.15 K |
| FKHNZQFCDGOQGV-UHFFFAOYSA-N | 2,3-Dimethylquinoxaline | 2.0 °C | 298.15 K |
| CITMYAPULDSOHG-UHFFFAOYSA-N | 1,2-Dibromopentane | 1.0 °C | 298.15 K |

`audit_b100_phase_state.py` then reads `mp_C` only, sets `mp_source = PUBCHEM_PUGVIEW`, `has_mp_data = true`, and passes anything with `mp < T_C`. The record's own `mp_note` never reaches the audit. So the phase gate is **circular**: an unparseable melting point becomes ≈1 °C, which guarantees `mp < 20–30 °C`.

The 110 are not harmless. `2,3-Dimethylquinoxaline` is a fused aromatic heterocycle whose PubChem record carries **no melting point at all**; admitting it at 298.15 K with "mp = 2.0 °C" is the exact failure mode PLAN B v6.0 warns about, only inverted (a row count standing in for a verified state). Long-chain alkyl halides (1-bromohexadecane, 1-iodohexadecane, 1-bromopentadecane) sit within a few K of their real melting points, where the assumed 1 °C is decisive. These need manual literature mp before any is called liquid.

### 2.2 The same extractor also rejects real liquids

The parser treats any `… °C` string as a melting point, including **normal boiling points** (`@760 mm Hg`) and bp-at-reduced-pressure. 7 of the 14 `SOLID_OR_SUPERCOOLED` exclusions are therefore not solids:

| excluded as "solid" | note recorded | reality |
|---|---|---|
| 1-Iodopentane (20 °C) | `OK: 157 °C @760 [mm Hg]` | **bp**, not mp |
| Diiodomethane (25 °C) | `OK: 181 °C @760 [mm Hg]` | **bp 181 °C**, not mp |
| Isoamyl ether (20 °C) | `OK: 172.5 °C` | bp |
| Isobutyl benzoate (20 °C) | `OK: 242.00 °C @ 760.00 mm Hg` | bp |
| Butyl nitrate (20 °C) | `OK: 136 °C @760 [mm Hg]` | bp |
| 1,3-bis(CF₃)benzene (30 °C) | `OK: 116 °C @760 [mm Hg]` | bp |
| 3-Heptanol (22 °C) | `OK: 66 °C (20 mm Hg)` | bp at 20 mmHg |

So the phase layer has **false positives (110 assumed mps) and false negatives (≥7 liquids excluded) at the same time**. The 14/35/257 partition is not a measurement of phase state; it is a measurement of how a regex did on PubChem prose.

### 2.3 Marginal admits

9 admitted molecules have `mp_margin_K < 5`, i.e. the phase decision is inside the uncertainty of a typical mp: N-methylacetamide 2.0 K, diethanolamine 2.1 K, butyl stearate 3.0 K, phenyl ether 3.2 K, acetic acid 3.4 K, oleic acid 3.7 K, caprylic acid 3.9 K, tetrahydro-β-naphthol 4.5 K, m-nitrotoluene 4.5 K. These are defensible but must be flagged, not counted as clean.

### 2.4 What is sound

`phase_state_audit_b100.csv` is internally consistent: `phase_verified = true` for exactly 257, `above_boiling_point = false` for all 306, no mp of −300 °C, `min mp = −123.1 °C`, `max = 242 °C`, and the 35 `UNKNOWN_NO_MP` are correctly *not* assumed liquid. The report's `criterion` line is honest. The failure is upstream, in the mp values themselves, and the audit never looks at their provenance.

---

## 3. Source independence — HOLD (INFERRED)

**Claim:** 226/257 from ONE compendium is a documented limitation; only 18 molecules are independently corroborated; Q1 = 31, Q2 = 226.

### 3.1 How many independent measurement programmes?

| unit | count |
|---|---:|
| Editorial compendium (NBS Circular 514) covering 226/257 | **1** |
| Distinct citable ThermoML journal documents in the 257 | **29** (23 carry Q1 labels) |
| ⇒ citable sources in hand | **30** |
| Primary references *inside* NBS 514 behind the 226 | 122 (none retrieved, none checked) |
| Molecules with ≥ 2 independent programmes | **19** (14×2, 4×3, 1×5) |
| Molecules with a *verified* independent replication | **18** |
| Molecules for which an independent value comparison was actually recorded | **12** |
| Sources listed in `source_registry_b100.csv` / of which contribute to the 257 | 62 / 30 (32 contribute nothing) |

**Answer:** the 257 rest on **one compendium (88% of the molecules) plus 29 journal documents**, i.e. **two layers, 30 citable sources, one of which is a 1951 critical compilation that is itself an aggregation of 122 primary papers**. In terms of *verifiable* independence, the dataset is effectively a **single-source dataset with a 12% independent annex**. The project's "30 independent programmes" is arithmetically right (1 + 29) but rhetorically generous: 23 of the 29 documents carry Q1 labels and 18 Q1 molecules have only one document each, so "programme" here means "DOI", not "independent laboratory".

The histogram in `source_independence_b100.json` is honest and important: `{1: 238, 2: 14, 3: 4, 5: 1}`. 238 molecules — the compendium — are one programme. Any `n = 257` statistical power claim inherits that.

### 3.2 Is "18 corroborated" correct?

Mechanically, the flag is **presence, not agreement**. `audit_b100_source_independence.py` L132/149:

```python
in_both = bool(nbs_srcs) and bool(core_srcs)
"independently_corroborated": "true" if in_both else "false",
```

No ε comparison is performed, yet `source_independence_b100.json` states the 18 are molecules where "NBS 汇编与 ThermoML 原始文献中都有 ε, **且两者一致** (见 cross_source_agree_b100.csv)". Of the 18, only **12** appear in `cross_source_agree_b100.csv`; **6 appear in neither** the agree nor the conflict file:

| InChIKey | molecule | NBS ε @T | nearest ledger record | deviation |
|---|---|---|---:|---:|
| VFWCMGCRMGJXDK-UHFFFAOYSA-N | 1-Chlorobutane | 7.390 @293.15 | 7.552 @283.15 / 7.157 @298.15 | ~1.5% (interp) |
| NHTMVDHEPJAVLT-UHFFFAOYSA-N | 2,2,4-Trimethylpentane | 1.940 @293.15 | 1.940 @293.15 | 0.0% |
| KWOLFJPFCHCOCG-UHFFFAOYSA-N | Acetophenone | 17.390 @298.15 | 17.510 @298.15 | 0.7% |
| VZGDMQKNWNREIO-UHFFFAOYSA-N | Carbon tetrachloride | 2.238 @293.15 | 2.230 @293.15 | 0.4% |
| LQNUZADURLCDLV-UHFFFAOYSA-N | Nitrobenzene | 34.820 @298.15 | 34.780 @298.15 | 0.1% |
| SNRUBQQJIBEYMU-UHFFFAOYSA-N | n-Dodecane | 2.014 @293.15 | 2.030 @293.15 | 0.8% |

I performed the comparison the pipeline skipped: **all six agree within 1.5%**. So the count of 18 is substantively correct — but it was *asserted*, not computed, and the JSON's pointer to a supporting file is wrong for one third of the set. Six of the 18 are also graded Q2 despite having full ThermoML records: the Q2 label attaches to the NBS-sourced label value, which is defensible, but it means "Q2" does not mean "no per-measurement provenance".

### 3.3 The part that matters most: conflicts were removed, then agreement was certified

`build_b100_admission_gate.py` L230 and L245-246/L275-276 exclude every molecule in `conflict_keys`. All 11 conflict molecules are therefore absent from the 257 (0/11), and the admission ledger records it explicitly: `CROSS_SOURCE_CONFLICT_UNRESOLVED` appears 22 times across 11 molecules. The dataset's *clean* cross-source record is therefore **selected**, not observed. This does not make the 257 wrong — dropping unresolved conflicts is conservative — but it forbids the sentence "high agreement between the two layers shows the dielectric values are broadly trustworthy" (readiness §3): the agreement rate is 12/12 only because 11/23 dissenting cases were removed first.

---

## 4. Q1/Q2 grading — PASS (DOCUMENTED)

**Claim:** Q1 = 31 with per-measurement provenance; Q2 = 226 source-level.

Verified against `outputs/confirm_2027/provenance_repair/measurement_ledger_v1.csv`:

- **31/31** Q1 label values reproduce an exact ledger record — same `temperature_K` **and** same `dielectric`, to within 0.01 K / 0.02 ε. No Q1 label is a v04 aggregate.
- 243 ledger records for the 31 molecules: **100%** `traceability_status = TRACEABLE`, **100%** `phase = Liquid`, **0** null `source_document_id`, `source_file_sha256` + `source_row_index` present, pressure 91.3–101.325 kPa, `experimental_independence_unit = source_document` for all.
- **23 distinct DOIs** for 31 molecules (e.g. butan-2-ol `BTANRVKWQNVYAZ-UHFFFAOYSA-N`, ε 16.6 @298.15 from `10.1016/j.fluid.2013.12.014; 10.1021/je3007666; 10.1021/je800593p; 10.1021/je900503p`; butan-2-ol is also the only Q1 molecule with substantial same-T spread, 16.58–17.60 = 6.1%).
- **0** Q1 molecules appear in `reconstruction_exceptions.csv`, so no Q1 label is a synthetic T/ε pair.
- The 226 Q2 molecules have no ledger record at all — only page-level transcription. The split is applied as claimed.

**Two caveats, neither fatal:**

1. `frequency_mhz = 0.0` on **all 243** Q1 records. Only 20/263 core records in the frozen ledger are non-zero (0.01–3 MHz), and **none belongs to a Q1 molecule**. So "per-measurement provenance" covers T, P, ε and document — **not frequency**. The Q1 layer's static basis is exactly as inferred as the NBS layer's; its advantage is document traceability, not frequency documentation. This should be stated wherever Q1 is presented as "逐条报告频率的 ThermoML 测量" (readiness §2) — that sentence is not supported.
2. Q1 ≠ independently corroborated: 18 of the 31 have a single document.

---

## 5. Cross-source agreement — FAIL (INFERRED)

**Claim (readiness §3):** 147 molecules in both layers, 136 agree, 11 conflict, conflicts registered and not averaged.

### 5.1 The 11 conflicts are not what they are called

`cross_source_conflict_b100.csv` compares a v04 "core" value with the NBS transcription. Cross-referencing `reconstruction_exceptions.csv` shows **5 of the 11 comparison values are documented as invalid**:

- `SYNTHETIC_PAIR_FROM_INDEPENDENT_MEDIAN` (T and ε taken from different observations, `condition_pair_valid = False`): cyclohexanone `JHIVVAPYMSGYDF`, pentan-1-ol `AMQJEAYHLZJPGS`, hexan-1-ol `ZSIAUFGUXNUGDI`, butan-1-ol `LRHPLDYGYMQRHN`.
- `NO_CONTRIBUTING_MEASUREMENT`: 1,4-dichlorobutane `KJDRSWPQXHESDQ` — the "conflict" is against a value with **no measurement behind it at all**.

And one is not a conflict at all: methylcyclohexane `UAEPNZWRGJTJPN` — ε 2.010 @298.20 vs 2.02 @293.15, **0.5–1.4% apart** — labelled `CONFLICT_CONDITION_MISMATCH` only because ΔT = 5.05 K exceeded the 5.0 K tolerance by 0.05 K.

Re-doing the comparison like-for-like (NBS value vs `measurement_ledger_v1.csv` at the NBS temperature, interpolating only where needed):

| molecule | NBS ε | ledger ε @T_NBS | Δ | verdict |
|---|---:|---:|---:|---|
| methylcyclohexane | 2.020 | 1.993 | 1.4% | **agreement** |
| 2-methylpropan-2-ol | 10.900 | 11.340 | 3.9% | **agreement** (also below its mp) |
| formamide | 109.000 | 104.389 | 4.4% | **agreement** (dε/dT over 10 K) |
| 1,2-ethanediol | 37.700 | 39.511 | 4.6% | borderline |
| butan-1-ol | 17.100 | 18.290 | 6.5% | conflict |
| hexan-1-ol | 13.300 | 14.260 | 6.7% | conflict (NBS matches the 13.06 low end) |
| 1,2-propanediol | 32.000 | 29.303 | 9.2% | conflict (dε/dT over 10 K) |
| propan-1-ol | 20.100 | 22.265 | 9.7% | conflict |
| cyclohexanone | 18.300 | 16.080 | 13.8% | conflict |
| pentan-1-ol | 13.900 | 16.120 | 13.8% | conflict |
| 1,4-dichlorobutane | 8.900 | **none** | — | unverifiable |

**So ~6 conflicts survive a like-for-like check and ~5 do not.** They are not "genuinely unresolved" because they are irreconcilable; they are unresolved because no one adjudicated them — and four of them would move inside the project's own 5% tolerance simply by comparing at a common temperature. Two of the survivors (cyclohexanone 13.8%, pentan-1-ol 13.8%) are real and should be named as such rather than buried in a list of 11 that includes a 0.5% non-conflict.

### 5.2 The 136 "agreements" are weaker than they look

- **122/136** AGREE rows rest on v04 core values whose `condition_pair_valid` is `False` in `reconstruction_exceptions.csv`. The agree table inherits the same synthetic-median defect as the conflict table; it just happens that the medians land close to the NBS values.
- **124/136** AGREE molecules are **not in the 257** (they failed other gates). The only cross-source evidence bearing on the delivered dataset is the **12** admitted agreements — the same 12 that back the "18 corroborated" claim.

---

## 6. Duplicate and identity risk (folded into `dataset_257`)

`identity_audit_b100.json` reports `MATCH 257`, and `smiles_verification_b100.json` reports `SAME 240 / STEREO_ONLY 17`, `0` duplicate PubChem CIDs. Both tests are *internal*: they recompute the InChIKey from the recorded SMILES, so they cannot detect a wrong structure assignment, and they treat different CIDs for the same substance as different substances. Two real risks survive:

1. **Limonene counted twice.** `XMGQYMWWDOXHJM-UHFFFAOYSA-N` "dl-Limonene" ε 2.30 and `XMGQYMWWDOXHJM-JTQLQIEISA-N` "d-Limonene" ε 2.36 carry the **same constitutional SMILES** `CC1=CCC(CC1)C(=C)C`; the only difference is the stereocentre. ε is a bulk scalar, so these are one substance, two rows (NBS p42:004/p42:005, ref 24). −1 effective molecule.
2. **A name/structure mismatch that also creates a duplicate.** NBS p39:008–010 lists three separate isomers from ref 215: 1-phenyl-1-propene (2.73), 2-phenyl-1-propene (2.28), 3-phenyl-1-propene (2.63). The project resolved both p39:008 and p39:010 to the **propenylbenzene** skeleton:

   | InChIKey | recorded name | recorded SMILES | PubChem CID | PubChem IUPAC | ε |
   |---|---|---|---:|---|---:|
   | QROGIFZRVHSFLM-QHHAFSJGSA-N | 1-Phenyl-1-propene | `CC=CC1=CC=CC=C1` | 252325 | (E)-prop-1-enylbenzene | 2.73 |
   | QROGIFZRVHSFLM-UHFFFAOYSA-N | **3-Phenyl-1-propene** | `CC=CC1=CC=CC=C1` | 12500 | **prop-1-enylbenzene** | 2.63 |

   `3-Phenyl-1-propene` is allylbenzene (C₆H₅CH₂CH=CH₂), a different connectivity with its own InChIKey. The row therefore either mislabels a propenylbenzene measurement or mis-assigns allylbenzene's ε 2.63 to propenylbenzene; either way **allylbenzene is missing from the dataset and propenylbenzene is present twice** (once defined E, once undefined stereo), with identical xTB input SMILES. −1 effective molecule.

Net: the 257 are **≤ 255 distinct substances**, and both reductions are invisible to the two identity audits the project relies on. The remaining 5 skeleton collisions (cis/trans-3-octene, -4-octene, -5-decene, dl/meso-2,3-dibromobutane, dl/meso-3,4-dibromohexane) are genuine diastereomer pairs with distinct ε and are fine.

---

## 7. Provenance claims I consider unsupported

| # | claim (where) | status |
|---|---|---|
| 1 | "257 个经熔点验证在设定温度下确为液态" — readiness §0, final report §1 | **Unsupported.** 110/257 mp are `ASSUMED_C` parser fabrications; only 147 are real values. Rephrase as "147 mp-verified + 110 assumed liquid (mp unavailable)". |
| 2 | "被两个来源独立印证的只有 18 个分子" + "且两者一致 (见 cross_source_agree_b100.csv)" — final report §1, `source_independence_b100.json` | **Number right, mechanism wrong.** The flag is presence-only; 6 of the 18 have no row in the cited file. I verified those 6 by hand and they agree, so the count survives — but the pipeline never tested what the text claims. |
| 3 | "136 对一致 / 11 对冲突. 高一致率说明两层介电数值总体可信" — readiness §3 | **Unsupported inference.** All 11 conflicts were excluded before the 257 were defined, so 12/12 agreement among admitted molecules is selected. 122/136 agree rows also rest on invalid condition pairs. |
| 4 | "11 个冲突已单独登记" presented as genuinely unresolved | **Overstated.** 5 comparison values are documented invalid (`SYNTHETIC_PAIR…`, `NO_CONTRIBUTING_MEASUREMENT`), 1 is a 0.5% non-conflict mislabelled by a 0.05 K tolerance overrun, and 3–4 move inside 5% at a common temperature. ~6 survive. |
| 5 | "Q1 证据 = 逐条报告频率的 ThermoML 测量" — readiness §2 | **Not supported.** `frequency_mhz = 0.0` on all 243 Q1 records; 0 Q1 molecules have a nonzero-frequency record. Q1 documents T/P/ε/document, not frequency. |
| 6 | "30 个独立测量方案" — `source_independence_b100.json` | **Misleading unit.** = 1 compendium + 29 DOIs; only 19 molecules have ≥2 programmes, and 18 of the 31 Q1 molecules have one. 226 molecules sit inside a compendium that itself aggregates 122 primary refs. |
| 7 | "身份 MATCH 257 / STEREO_ONLY 17, 0 defects" | **Insufficient scope.** Cannot see the limonene duplicate or the allylbenzene→propenylbenzene mis-assignment; both are internally consistent. |
| 8 | `source_registry_b100.csv` as "the sources behind B100" (62 rows) | **Overstated.** 32 of the 61 ThermoML documents contribute nothing to the 257. |

Claims that **hold up** and should be kept: the single-compendium limitation and its consequences (readiness §6, JSON `what_is_NOT_supported`); the 127-row frequency exclusion; the Q1/Q2 split as applied to the label values; `UNKNOWN_NO_MP` not being assumed liquid; "cross-source conflicts were not averaged".

---

## 8. What I would require before this layer is used for confirmatory claims

1. Re-derive all 306 melting points with a parser that rejects `@xxx mm Hg` / `(xx mm Hg)` strings, rejects InChI-derived numbers, and refuses to emit a value when the note is `ASSUMED_C`. Expected effect: ~110 molecules move to `UNKNOWN_NO_MP`, ~7 liquids return from the false-solid bucket.
2. Re-run the phase audit treating `mp_note` as part of the evidence and propagating an mp uncertainty (±1–2 K) into `mp_margin_K`.
3. Replace the `STATIC_BY_SOURCE_DEFINITION` labelling with an explicit `frequency_basis = NO_FOOTNOTE_IN_SOURCE` and stop describing Q1 as frequency-documented.
4. Add a real `independently_corroborated` test (same-T ε within tolerance) to the independence script, and report the 6 currently unchecked cases.
5. Report the conflict rate on the *same* molecule set as the final 257 — i.e., state "12 compared, 12 agreed, 11 excluded for conflict" rather than "136/11 overall", or present the conflicts inside a `n = 23` denominator.
6. Resolve the two duplicate-substance pairs (limonene, propenylbenzene/allylbenzene) and re-resolve NBS p39:010 as allylbenzene.

---

## 9. Method and reproduction

All numbers were recomputed with `E:\Claude Code\电解质ML\电解质ML\.venv\Scripts\python.exe` (pandas only). Nothing in the tree was modified; this directory contains only the review artefacts.

Inputs read: `outputs/b100/{nbs514_condition_audit, phase_state_audit_b100, pubchem_mp_lookup_b100, source_independence_b100, cross_source_agree_b100, cross_source_conflict_b100, smiles_verification_b100, identity_audit_b100, qualified_molecules_b100, excluded_molecules_b100}.csv/json`; `outputs/b100/deliverables/{measurement_ledger_b100, epsilon_labels_b100, exclusion_ledger_b100, molecule_registry_b100, source_registry_b100}.csv` plus `B100_FINAL_REPORT.md`; `outputs/b100/B100_STAGE1_READINESS.md`; `data/interim/nbs514_organic_part{1..4}.csv`; `data/processed/dielectric_pool_expansion_observations.csv`; `data/processed/liquid_window_gate_report.csv`; `outputs/confirm_2027/provenance_repair/{measurement_ledger_v1, reconstruction_exceptions}.csv`; scripts `audit_b100_phase_state.py`, `fetch_pubchem_mp_b100.py`, `build_b100_admission_gate.py`, `build_b100_asset_inventory.py`, `audit_b100_source_independence.py`.

Key checks, in one line each:

- `nbs514_condition_audit.csv`: `frequency_status` nunique = 1; `frequency_note` non-null = 0; `expansion_frequency_mhz` non-null = 0.
- transcription: `frequency_note` non-null = 127; `set(obs.source_id) ∩ set(high_freq.source_id)` = 0.
- `pubchem_mp_lookup` ∩ `phase_verified` = 257 rows; `mp_note` prefix counts = `{ASSUMED_C 110, CONVERTED_FROM_F 67, OK 43, H… 35, PAC 1, ILO 1}`.
- `source_independence`: `n_independent_programmes` histogram `{1: 238, 2: 14, 3: 4, 5: 1}`; `independently_corroborated` = 18, of which 12 in `cross_source_agree`, 0 in `cross_source_conflict`.
- Q1 ↔ ledger: 31/31 exact (T, ε) matches; 243 records; 0 null docs; 0 nonzero frequencies.
- conflicts: `cross_source_conflict` ∩ 257 = 0; `exclusion_ledger` `CROSS_SOURCE_CONFLICT_UNRESOLVED` = 22 rows / 11 molecules.
- duplicates: InChIKey skeleton groups > 1 = 7 (14 molecules); duplicate constitutional SMILES = 2 pairs.
