# Reviewer 2 — Source Literature / DOI / Provenance Independence

**Work package:** B02-CONFLICT · **Case:** gamma-valerolactone (γ-VL) dual-row ε conflict
**Compound:** gamma-valerolactone, InChIKey `GAEKPEKOJKCEMS-UHFFFAOYSA-N`, SMILES `CC1CCC(=O)O1`
**Rows adjudicated:** `EPSV04-R227` (ε = 36.1) vs `EPSV04-R248` (ε = 36.9), both stamped T = 298.15 K
**Reviewer scope:** DOI resolution, source primacy, source independence, provenance class. Not numerical plausibility (other reviewers), not queue mechanics (Reviewer 3).
**Date of review:** 2026-11-23

---

## 0. Bottom line

Both DOIs are **real and resolve**. Neither is fabricated, and neither is malformed.

That is the only thing the two rows have going for them. My findings, in order of importance:

1. **The 2026 identifier is not a placeholder.** It is a genuine, indexed, open-access iScience article from May 2026. The skepticism the work order asks for is warranted in general but does not pay off here.
2. **R227 is a tertiary compiled value, not a measurement.** I located the exact cell: ε = 36.1 sits in Table 3 of an open-access *perspective/review*. The review measured nothing; its single citation for that number is a zinc-battery paper.
3. **Neither source reports 298.15 K.** This is the finding that reframes the whole case. The iScience Table 3 has no temperature column at all. The ICA row is explicitly flagged `temperature_not_reported`. **T = 298.15 K on both rows is an imputation, applied by a default rule, and the conflict was constructed on top of it.**
4. **R248 is unverifiable and its provenance chain is corrupt at the origin.** Closed access, no OA copy, no local document, absent from Europe PMC. Worse, the upstream Reaxys row had **no DOI** and **the wrong InChIKey**; the DOI was attached afterwards by Crossref lookup.
5. **The pair is not independent.** Two compilation lineages, very likely sharing a common handbook ancestor. Averaging is not defensible.
6. **The ledger absence is *not* the NBS-514 manual-entry mechanism.** Both rows belong to a 33-row class whose ingestion path is recorded as literally `unknown`.

**Decisions: R227 = HOLD, R248 = FAIL. Both → `NEEDS_PRIMARY_DOCUMENT`. No averaging.**

---

## 1. DOI verification

Both were checked against the DOI handle system, Crossref, Unpaywall, Europe PMC and Semantic Scholar.

### 1.1 `10.1016/j.isci.2026.115778` — RESOLVES ✅

| Field | Value |
|---|---|
| Title | Revolutionary horizons in nonaqueous and aqueous-nonaqueous electrolyte design for safer high-performance zinc-ion batteries |
| Journal | *iScience* **29**(5), article 115778 |
| Published | 2026-05 (Crossref `created` 2026-04-17) |
| Authors | Annie Y. Sun, Nicolas L. Simi, Vilas G. Pol |
| Type | journal-article — **perspective / review** |
| Identifiers | DOI handle → `linkinghub…/pii/S2589004226011533`; PMC13156642; PMID 42111170 |
| Access | Gold OA, CC BY-NC 4.0, 128 references |

**On the 2026 date.** I was asked to be skeptical and I was. The skepticism does not survive contact with the evidence. The DOI resolves through the official handle system to a ScienceDirect PII, Crossref carries a full record with 128 references and a funder block (US DEVCOM Army Research Laboratory, award W911NF-25-1-0114), and PubMed/PMC carry it as a live indexed article. Today is 2026-11-23, so the paper is roughly six months old. It is a normal publication, not a future-dated or placeholder identifier.

### 1.2 `10.1016/j.ica.2021.120372` — RESOLVES ✅

| Field | Value |
|---|---|
| Title | Experimental and theoretical investigation of the cycloisomerization of N-propargylcarboxamide catalyzed by NHC-Au-X in green solvents |
| Journal | *Inorganica Chimica Acta* **522**, article 120372 |
| Published | July 2021 (Crossref `created` 2021-03-30) |
| Authors | Jacopo Segato, Walter Baratta, Paola Belanzoni, Leonardo Belpassi, Alessandro Del Zotto, Daniele Zuccaccia |
| Type | journal-article, 113 references |
| Access | **Closed** (`is_oa: false`, `oa_status: closed`); no OA copy; **absent from Europe PMC** (`hitCount: 0`) |

**Does an inorganic-chemistry journal reporting a lactone's dielectric constant make sense?** It makes more sense than the framing of the question implies — but not in the way the record needs. *Inorganica Chimica Acta* is a perfectly normal venue for gold-NHC catalysis, and the published abstract confirms γ-valerolactone genuinely appears in this paper:

> "most of these solvents (cyclohexanone, isopropyl acetate, MIBK, ethyl lactate, furfuryl alcohol, **γ-valerolactone**, propylene carbonate and propionic acid) are comparable or better solvents with respect to traditional VOS"

So γ-VL is real in this paper — **as a reaction solvent in a catalysis study, not as a characterised dielectric material.** A solvent-properties table in such a paper is normally a set of cited descriptors used to rationalise polarity, not an original permittivity measurement.

---

## 2. Is either source a PRIMARY measurement of pure γ-valerolactone?

**R227: No.** I retrieved the full text via Europe PMC (`PMC13156642/fullTextXML`) and found the value verbatim in **Table 3**, "Nonaqueous molecule structures and properties in design categories", under the *Selected polar aprotics* block:

```
N-methyl pyrrolidone (NMP)  | 32.2 | 27.3 | –  | –  | 72
Dichloromethane (DCM)       |  8.9 |  1.0 | –  | 66 | –
γ-valerolactone (GVL)       | 36.1 |  –   | 58 | –  | –
2-butanone                  | 18.5 | 17.4 | –  | –  | 77
Dimethyl sulfoxide (DMSO)   | 46.7 | 29.8 | 56,57 | – | 41,69,81,96
```

Column layout: `Category | Solvent | Structure | Dielectric constant | Donor number (kcal mol⁻¹) | Single-solvent refs | Multi-solvent refs | ANA refs`. So the dielectric constant is 36.1, the donor number is a dash (not reported), and the single citation is **ref 58**.

Ref 58 is:

> Xie C., Liu S., Zhang W., Ji H., Chu S., Zhang Q., Tang Y., Wang H. *Robust and Wide Temperature-Range Zinc Metal Batteries with Unique Electrolyte and Substrate Design.* Angew. Chem., Int. Ed. 2023;62. doi: 10.1002/anie.202304259

That is a zinc-battery paper, not a dielectric or thermophysical study. The dataset's own metadata already agrees with my reading: `source_quality = open_access_review_table`, `evidence_level = open_access_review_table`, `source_table = Table 3`. **R227 is tertiary: a compiled descriptor inside a review, citing another applied paper.**

**R248: Cannot be established, and the balance of evidence is against primary.** The record points at "supporting information". I could not obtain that SI: the article is closed access with no OA location, it is not in Europe PMC, and no PDF or SI for this DOI exists anywhere in the repository (I searched for `115778`, `120372`, `ica.2021`, `isci`, and every PDF). I then checked all 113 Crossref reference entries for this paper: **there is no dielectric, permittivity, handbook, CRC, Landolt or Wohlfarth item.** If the SI ε were an original measurement we would not expect such a citation, but we also cannot rule it out. The honest verdict is **unknown**, leaning secondary: a solvent-descriptor table in a catalysis SI is far more likely a compilation than a new measurement campaign on a pure lactone.

I will not overclaim here. I cannot see the document, so I cannot say the value is not there. What I *can* say is that the project has never possessed it either.

---

## 3. The finding that reframes the case: neither source states 298.15 K

This is the most consequential result of my review and it undercuts the premise of the conflict.

**R227.** Table 3 has **no temperature column**. I searched the full text: the string `298.15` does not occur in the table, `25 °C` occurs only twice in the whole article (dissolved-oxygen solubility in water, and the Aurbach CE test temperature for Cu‖Zn cells) and in neither place is it attached to a solvent property. The only `298` matches in the entire article are inside reference page numbers. The value is a room-temperature-standard descriptor with **no declared measurement temperature**.

The dataset knows this and says so. `dielectric_v04.csv` for this row carries:

```
temperature_source = review_table_standard_room_temperature
gate_flags         = (empty in v04; queue-side flag: temperature_review_table_standard)
```

**R248.** `dielectric_v04.csv` carries `temperature_source = not_reported`, and the gap-table gate flags include `temperature_not_reported`.

So the queue's claim — *same compound, same temperature 298.15 K, two different ε* — **is not supported by either cited document.** Both temperatures were filled in by a room-temperature default rule. The two rows were placed at a common temperature by imputation, and only then declared to be in conflict.

**This is a systematic defect, not an isolated one.** Six v04 rows draw on this same Table 3, and every one reproduces the table exactly while wearing the same imputed 298.15 K:

| aggregate | solvent | ε in v04 | ε in iScience Table 3 | T in v04 | T in source |
|---|---|---:|---:|---:|---|
| v04row-224 | 1,3-dioxolane (DOL) | 7.3 | 7.3 | 298.15 | not stated |
| v04row-225 | THF | 7.5 | 7.5 | 298.15 | not stated |
| v04row-227 | γ-valerolactone | 36.1 | 36.1 | 298.15 | not stated |
| v04row-236 | NMP | 32.2 | 32.2 | 298.15 | not stated |
| v04row-243 | triethyl phosphate (TEP) | 13 | 13 | 298.15 | not stated |
| v04row-244 | trimethyl phosphate (TMP) | 21.6 | 21.6 | 298.15 | not stated |

A single open-access review table was ingested as if it were a set of measurements at a stated temperature. That is a cluster-level provenance defect worth escalating beyond this one pair.

---

## 4. Are the two sources independent?

**No — not in any sense that would license a statistical resolution.**

- R227 is a **compilation** (a review table) whose own single citation for this number is an applied battery paper.
- R248 is a **solvent-descriptor table** in a catalysis SI, unverifiable and probably itself compiled.
- Neither is a measurement, so the 2.2 % spread (36.1 vs 36.9) is the ordinary spread between two *compilation lineages*, very likely both downstream of a common handbook / solvent-table tradition. My reference scan of the ICA paper found no handbook citation, but the iScience table's own structure (a curated descriptor column with one citation per row) is the signature of handbook-derived data.

The practical consequence: **`AVERAGE_JUSTIFIED` is unavailable.** Averaging two numbers that are neither independent nor measured, at a temperature neither document states, would manufacture a third synthetic value on top of a synthetic conflict. That is precisely the failure mode Reviewer 3 documented elsewhere in this queue.

---

## 5. Why is there no contributing observation in the ledger?

The work order's hypothesis was that these might be manual entries like NBS Circular 514 — a legitimate but different provenance class. **That hypothesis is wrong, and the distinction matters.**

The 135-row `coverage_gap_registry.csv` splits cleanly:

| class | count | `ingestion_path` | `recoverability` |
|---|---:|---|---|
| NBS514 manual transcription | **102** | `literature_manual_entry` | `RECOVERABLE_NBS514_MANUAL_TRANSCRIPTION` |
| Unflagged, no observation | **33** | **`unknown`** | `NOT_EVALUATED_INGESTION_PATH_UNKNOWN` |

`v04row-227` and `v04row-248` are both in the **33-row `unknown` group**, not the NBS group. The registry's own wording for this class:

> 该行 gate_flags 为空且观测层无对应观测; 既不是 ThermoML 解析结果, 也未标为人工录入, 录入路径不明
> *("this row has empty gate_flags and no corresponding observation in the source layer; it is neither a ThermoML parse result nor marked as manual entry; the ingestion path is unknown")*

Supporting facts:

- The source layer (`measurement_ledger_v1.csv`, 2065 rows, 61 ThermoML documents) contains **0 rows** for `GAEKPEKOJKCEMS` and **0** for any valerolactone string. Neither DOI appears among the 61 `source_document_id` values.
- `source_document_registry_v1.csv` (61 entries, all `document_identity_verified = true`) contains **neither DOI**. These rows were never registered as source documents at all.
- `condition_pair_validity_v1.csv` and `reconstruction_exceptions.csv` both record `NO_CONTRIBUTING_MEASUREMENTS` / `MISSING_CERTIFICATE` / `NO_BAND_OBSERVATIONS_IN_SOURCE_LAYER`, with the instruction 不得插值、不得反推、不得从聚合结果还原 ("no interpolation, no back-inference, no reconstruction from the aggregate").

So the absence is **not** a benign "manual transcription of a printed handbook" — that class is tracked separately and *is* recoverable by re-reading the original pages. These two rows are an **undeclared ingestion path**: values that entered the dataset from a review table and a Reaxys queue without ever passing through a declared, reproducible ingest. The `PROVENANCE_INCOMPLETE` verdict is therefore correct, and the rows are not recoverable from the source layer as it stands.

---

## 6. The R248 provenance chain is corrupt at its origin

This deserves separate emphasis because it is the strongest single argument against R248. From `dielectric_v04.csv` notes for that row:

> "the upstream **Reaxys queue row** that surfaced the value carried **no DOI**. That queue row also **mislabels the compound's InChIKey as `JYVATQXCHBTGRN-UHFFFAOYSA-N`**; RDKit and the frozen v0.3 row both give `GAEKPEKOJKCEMS-UHFFFAOYSA-N` […] The DOI and the citation were **resolved independently through Crossref**."

Read that sequence carefully. The value arrived with:
1. **no DOI**, and
2. **the wrong structure key** (not γ-valerolactone).

The DOI was then **attached afterwards by Crossref lookup** against a bibliographic string. The project has never held the document. So "DOI resolves" is true but nearly content-free: a resolving DOI proves that a paper with that citation exists, not that the paper contains ε = 36.9 at 298.15 K. Given that the same pipeline had already mis-assigned the compound identity, the attribution deserves to be treated as a hypothesis, not a fact.

This is exactly the case where a resolving DOI must not be read as evidence of sourcing.

---

## 7. Numerical plausibility (context only — outside my remit)

Noted only so it is not mistaken for a defence: γ-butyrolactone is around 39 and γ-valerolactone should be somewhat lower, so both 36.1 and 36.9 are chemically sane. **The defect in these rows is provenance, not magnitude.** A plausible number with no traceable measurement is still unusable as measurement evidence — the same standard Reviewer 3 applied to the synthetic medians.

---

## 8. Recommendations

### `EPSV04-R227` — HOLD, `DOCUMENTED`, `NEEDS_PRIMARY_DOCUMENT`
The DOI resolves and I verified the number is genuinely printed in the cited document. That is enough to *document* the citation, and nothing more. The row is a tertiary compiled descriptor from a perspective review, at an imputed temperature, with an empty `gate_flags` field and an undeclared ingestion path. It must not be promoted to the primary leg of a same-temperature conflict. **Retain as a registered, non-model-ready row** pending retrieval of a real measurement; do not delete (the citation is real and the value is quotable), and do not mark `model_ready`.

### `EPSV04-R248` — FAIL, `INSUFFICIENT`, `NEEDS_PRIMARY_DOCUMENT`
The DOI is real, so this is not a fabrication finding. But the row asserts an unverified ε at an unreported temperature, attributed post hoc to a supporting information table the project has never retrieved, from an upstream record that carried **no DOI and the wrong InChIKey**. There is no evidence at any link in the chain. It fails as an evidence row in its current state. **Do not retain as a primary leg.** It becomes admissible only if and when the SI is obtained and shows both the value and a stated temperature.

### Both rows — `NEEDS_PRIMARY_DOCUMENT`
Neither row should be resolved against the other. Neither document is a primary measurement of pure γ-valerolactone's static permittivity, and **neither states 298.15 K**.

**`AVERAGE_JUSTIFIED` is rejected.** Averaging would (a) combine two non-independent compilations, (b) at a temperature neither source reports, (c) to produce a value that is not a measurement and not attributable to either source. The `UNRESOLVED` / "must not average, must not pick one" instruction in `source_conflict_register.csv` is the correct disposition and should be preserved.

**What would actually close this case.** Retrieve a genuine primary measurement of pure γ-VL static permittivity with a stated temperature. The literature contains exactly the right kind of study — for example Fornefeld-Schwarz & Svejda, *J. Chem. Eng. Data* 1999, **44**, 597–604, doi `10.1021/je980288w`, "Refractive Indices and Relative Permittivities of Liquid Mixtures of γ-Butyrolactone, γ-Valerolactone, δ-Valerolactone, or ε-Caprolactone + Benzene, + Toluene, or + Ethylbenzene at 293.15 K and 313.15 K and Atmospheric Pressure". That paper measures relative permittivities directly, at stated temperatures, for the pure components. I did not obtain it, so I make no claim about its numerical result — but it is the correct *class* of source, and it is the sort of document that should replace both rows. Note its temperatures are 293.15 K and 313.15 K, not 298.15 K, so even a successful retrieval would require re-deriving the conflict at a temperature that actually exists in the data.

### Escalation (outside my two rows, but arising from this review)
The six-row Table 3 ingestion cluster (§3) is a systemic issue. Any γ-VL resolution that leaves those five sibling rows in place will leave the same defect behind, and each of them carries the same fabricated 298.15 K. I recommend a separate audit of `v04row-224/225/236/243/244` against the same Table 3 finding.

---

## 9. Evidence trail

| Item | Location / identifier |
|---|---|
| Queue rows | `outputs/admission_v2/admission_review_queue.csv` lines 72–73 |
| Conflict register | `outputs/b01/source_conflict_register.csv` `CONF-GAEKPEKOJKCEMS-298.1` |
| v04 authoritative rows | `v56_standalone/app/电解质ML/电解质ML/data/dielectric_v04.csv` (both γ-VL rows, incl. `temperature_source`, `source_quality`, `notes`) |
| Gap classification | `outputs/confirm_2027/identity_and_coverage/coverage_gap_registry.csv` v04row-227, v04row-248 |
| Provenance audit | `outputs/confirm_2027/provenance_audit/gap_aggregation_audit.csv` lines 228, 249 |
| Reconstruction refusal | `outputs/confirm_2027/provenance_repair/reconstruction_exceptions.csv` EXC-EPSV04-R227, EXC-EPSV04-R248 |
| Registry check | `outputs/confirm_2027/provenance_repair/source_document_registry_v1.csv` — **neither DOI present** (61 entries) |
| Ledger check | `measurement_ledger_v1.csv` — 2065 rows, 61 DOIs, **0 γ-VL rows** |
| iScience full text | Europe PMC `PMC13156642/fullTextXML`; Table 3; refs 56–60 |
| DOI handles | `doi.org/api/handles/10.1016/j.isci.2026.115778` → PII S2589004226011533; `…/10.1016/j.ica.2021.120372` → PII S0020169321001286 |
| ICA abstract | Semantic Scholar `DOI:10.1016/j.ica.2021.120372` (confirms γ-VL as a screened solvent) |
| OA status | Unpaywall: iScience gold/CC-BY-NC; ICA closed |

---

## 10. Summary table

| queue_id | measurement_id | ε | decision | evidence_grade | doi_resolved | source_is_primary | recommended_resolution |
|---|---|---:|---|---|---|---|---|
| Q-CONF-EPSV04-R227 | EPSV04-R227 | 36.1 | **HOLD** | DOCUMENTED | true | false | NEEDS_PRIMARY_DOCUMENT |
| Q-CONF-EPSV04-R248 | EPSV04-R248 | 36.9 | **FAIL** | INSUFFICIENT | true | unknown | NEEDS_PRIMARY_DOCUMENT |

*Reviewer 2, independent review. I did not consult or speculate about the findings of Reviewers 1, 3 or 4. No existing file was modified.*
