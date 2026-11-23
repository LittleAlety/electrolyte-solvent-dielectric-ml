# Reviewer 4 — Independent Adversarial Audit (Red Team)
## B02-CONFLICT · gamma-valerolactone (GAEKPEKOJKCEMS-UHFFFAOYSA-N) at 298.15 K

**Mandate:** try to BREAK the claim that this conflict can be resolved at all.
**Stance:** both records are unusable until proven otherwise. Nothing was passed.
**Files read (all, in full):** `admission_review_queue.csv`, `b01/source_conflict_register.csv/.json`,
`confirm_2027/provenance_repair/measurement_ledger_v1.csv` (2065 rows, exhaustive),
`provenance_repair/{aggregate_contribution_ledger_v1,condition_pair_validity_v1,reconstruction_exceptions}.csv`,
`provenance_audit/gap_aggregation_audit.csv`, `identity_and_coverage/{coverage_gap_registry,identity_conflict_resolution,b02_work_order}.csv`,
`v56_standalone/reports/candidate_master_R001.csv`, `candidate_pool_C_R001.csv`, plus every `dielectric_v0*.csv`,
`modern_solvent_public_review_observations.csv`, `themol_orbital_layer*.csv`, `four_core_key_registry.csv`,
`landolt_boernstein_2015_pure_liquid_queue.csv`, `probes/reaxys_dielectric_queue_first_cut.csv`.
**Nothing was modified.** Only the two output files below were created.

---

## 1. Verdict

| queue_id | measurement | ε | decision | grade | adversarial finding | conflict | recommended |
|---|---|---|---|---|---|---|---|
| Q-CONF-EPSV04-R227 | EPSV04-R227 | 36.1 | **FAIL** | INSUFFICIENT | `SECONDARY_SOURCE` | true | **REJECT_ROW** |
| Q-CONF-EPSV04-R248 | EPSV04-R248 | 36.9 | **FAIL** | INSUFFICIENT | `NO_TRACEABLE_MEASUREMENT` | true | **NEEDS_PRIMARY_DOCUMENT** |

**Both records are inadmissible as measurements.** I am *not* recommending `NEEDS_PRIMARY_DOCUMENT` for the
pair as a whole, and I am *not* recommending `REJECT_ROW` for both. The two rows are **not symmetrically
defective**, and flattening them into one verdict would destroy the only actionable information in this
work package: R248 points at a retrievable document; R227 points at a review article whose own primary
source is R248's paper.

---

## 2. The five attacks, and which ones actually landed

### Attack 1 — "Neither has a traceable measurement." **LANDED. Fatal.**

Exhaustive search of the 2065-row ledger (153 distinct molecules, 61 distinct source documents):

- rows with `molecule_key` / `inchikey` = `GAEKPEKOJKCEMS-UHFFFAOYSA-N`: **0**
- rows with `a_name` containing `valerolactone`: **0**
- rows citing `10.1016/j.isci.2026.115778`: **0**
- rows citing `10.1016/j.ica.2021.120372`: **0**

Gamma-valerolactone is **entirely absent** from the observation layer. Neither ε can be reproduced from
any observation, at any temperature, at any frequency. `n_contributing_measurements = 0`,
`condition_pair_valid = false`, `contribution_certificate = MISSING_CERTIFICATE`,
`NO_BAND_OBSERVATIONS_IN_SOURCE_LAYER` on both.

This is the load-bearing finding. The conflict is **not a disagreement between two measurements**; it is
a disagreement between **two bibliography entries**. Nothing was ever measured inside this project for
this compound. Whether 36.1 or 36.9 is "right" is unanswerable from project data, and — as attacks 3–5
show — is also not cleanly answerable from the cited sources.

### Attack 2 — "The 2026 DOI is a future/hallucinated identifier." **FAILED. Both DOIs are real.**

I searched both and both resolve. I record this honestly rather than manufacturing a defect:

- **`10.1016/j.isci.2026.115778` → RESOLVES.** Crossref HTTP 200: iScience, vol. 29, issue 5, article
  115778, published 2026-05, created 2026-04-17. Authors Annie Y. Sun, Nicolas L. Simi, Vilas G. Pol
  (Purdue). EuropePMC confirms `PMCID: PMC13156642`, `PMID: 42111170`, `isOpenAccess: Y`, CC BY-NC.
  Title: *"Revolutionary horizons in nonaqueous and aqueous-nonaqueous electrolyte design for safer
  high-performance zinc-ion batteries."* The identifier is genuine. The project's citation
  `Sun et al. (2026) iScience 29 115778` and its `PMC13156642` URL are both correct.
- **`10.1016/j.ica.2021.120372` → RESOLVES.** Crossref HTTP 200: Inorganica Chimica Acta, vol. 522,
  article 120372, published 2021-07, created 2021-03-30. Authors Segato, Baratta, Belanzoni, Belpassi,
  Del Zotto, Zuccaccia. Title: *"Experimental and theoretical investigation of the cycloisomerization of
  N-propargylcarboxamide catalyzed by NHC-Au-X in green solvents."* The citation in
  `dielectric_v04_roster_additions.csv` is accurate, including the volume and article number.

**Conclusion:** the "future DOI" suspicion is a false alarm and I retract it. The date is not anomalous —
the system clock reads 2026-11, so a May 2026 iScience article is a *past* publication. But the DOI
resolving does **not** make the record admissible: a resolvable DOI establishes that a document exists,
not that a permittivity was measured. That distinction is the whole case.

### Attack 3 — "Inorganica Chimica Acta is a secondary source for a pure organic solvent's ε." **LANDED.**

The journal identity is a red herring — but the attack's *mechanism* is correct, and it is worse than
suspected. The paper is a **homogeneous gold catalysis** study:

> *"Experimental and theoretical investigation of the cycloisomerization of N-propargylcarboxamide
> catalyzed by NHC-Au-X in green solvents"*

GVL appears as a **green reaction medium**, not as a characterized dielectric. Its 113 references are
uniformly Au-catalysis / green-chemistry / NHC ligand work (`Chem. Rev.` gold catalysis, `Organometallics`,
`ACS Catal.`, `Green Chem.`); **not one is a dielectric-constant or permittivity study.** A permittivity
value appearing in such a paper's supporting information is, with near-certainty, a **methods-table
citation to a handbook** — exactly the pattern the mandate predicted — not a measurement made by those
authors. The project's own metadata concedes the locus: `source_page = "supporting information"`,
`source_table = "supporting information"`.

Critically, the label `source_quality = "primary"` on this row is an **inference from document type**
("this is a research article, therefore primary"), not evidence that a permittivity was measured. Under
adversarial reading it is **mislabeled**: the row is a tertiary hand-off (handbook → SI table → Reaxys →
this project) wearing a primary badge.

### Attack 4 — "Are there other GVL values that corroborate or contradict?" **LANDED as a scope finding.**

I swept every CSV in the repository (652 candidate files) for the InChIKey and for `valerolactone`, and
extracted every value in a dielectric/epsilon/target column. The complete inventory in the 30–45 window:

| ε | files | status |
|---|---|---|
| **35.688** | 4 | `w26_dielectric_scan.csv` / `w26_model_contrast.csv` — **not a GVL value**. These are ε **grid/scan points** in a Born/continuum solvation scan (the same files carry 1.0, 2.0, 4.0, 7.58, 12.0, 18.0, 25.0, 80.4, 120.0, 200.0, 400.0, 1000.0). Appears on a GVL row only because GVL is the scanned solute. **Must not be read as evidence for or against 36.1/36.9.** |
| **36.1** | 70 | single origin: the iScience review table. Propagates to `dielectric_v03/v031/v032/v04.csv`, `modern_solvent_public_review_observations.csv`, `four_core_key_registry.csv`, `w21_chemical_space_metadata.csv`, and every model/target column in the ML artifacts. |
| **36.9** | 30 | single origin: the Segato 2021 SI via Reaxys. Propagates to `dielectric_v04.csv`, `dielectric_v04_roster_additions.csv`, **and `themol_orbital_layer.csv` / `themol_orbital_layer_expanded.csv`** (`in_epsilon_roster=true`, `epsilon=36.9`, flagged `flagship_dielectric`). |
| **43.2905** | 6 | `dielectric_onsager_delta_*` — a **computed Onsager reaction-field** quantity, not a measurement. `epsilon_observed = 36.1` sits beside it. Not a third value. |

**No third independent value exists anywhere in the repository.** Every occurrence traces to exactly one
of the two contested bibliography entries. There is no internal corroboration and no internal contradiction
beyond the pair itself. This *strengthens* the case for `NEEDS_PRIMARY_DOCUMENT`: the project has two
propagating copies, not two observations, and **the 36.9 leg has already silently reached the orbital
feature layer** — a downstream contamination that a `REJECT_ROW`-both verdict would leave in place
unflagged.

### Attack 5 — "Is the conflict even real, or a transcription artifact?" **PARTLY LANDED — and it exposed a real defect.**

Three sub-attacks:

**(a) Duplicate transcription of one value?** No. 36.1 and 36.9 differ in the second digit; there is no
transposition, digit-drop or decimal-shift relationship. They descend from two different documents by two
different author groups. `identity_conflict_resolution.csv` independently rules `is_true_conflict = true`,
`SAME_COMPOUND_SOURCE_CONFLICT`, `distinct_full_inchikey = 1`, `stereo_difference = false`. Not an artifact.

**(b) Same value at a different temperature, mislabeled 298.15 K?** **This is the strongest surviving
attack, and it cannot be refuted — only noted.** The conflict register's own declared tolerance is
`relative_epsilon = 0.02` (2%), and the observed spread is **2.216%** — i.e. the pair barely crosses a
threshold the register itself admits is *"本审计的选择, 不是冻结协议的一部分"* (this audit's choice, not part
of the frozen protocol). The gap is **0.8 ε units**. For a polar liquid of ε≈36, dε/dT ≈ −0.2 to −0.3 K⁻¹,
so 0.8 units corresponds to **2.7–4.0 K** of unrecorded temperature difference. Since *neither row carries
a measured temperature* (see below), 36.1 at 295 K and 36.9 at 298 K are entirely compatible, and so are the
reverse. **The "conflict" may be a temperature artifact of two rows whose temperatures were both invented.**
The register treats 298.15 K as a shared condition; it is not a shared *measurement* condition.

**Temperature provenance is fabricated on both legs — verified:**

| row | ε | T_K | `temperature_source` | uncertainty | `model_ready` |
|---|---|---|---|---|---|
| R227 | 36.1 | 298.15 | **`review_table_standard_room_temperature`** | *(empty)* | `true` |
| R248 | 36.9 | 298.15 | **`not_reported`** | *(empty)* | `false` |

`review_table_standard_room_temperature` is by name a **convention**, not a reading. `not_reported` is an
explicit admission. The project's own notes state *"neither leg carries a measurement temperature."* So the
`298.15` in `admission_review_queue.csv` is **not data** — it is a placeholder that the queue then
propagated as if it were a condition. Both rows also carry **no uncertainty whatsoever**, so neither can be
adjudicated against a tolerance. And note the internal inconsistency: R227 is `model_ready = true` despite
having an imputed temperature, no uncertainty and a secondary source — while its own `notes` field says the
field *"is protected and is therefore not silently rewritten"* even though it *"was written before the
competing primary leg was known."* A row that is simultaneously `model_ready=true` and `conflict_status=unresolved`
is a live contradiction in the frozen dataset.

**(c) NEW DEFECT FOUND — the audit table contradicts itself on R227.** In
`gap_aggregation_audit.csv`, row `EPSV04-R227` reports `gap_epsilon = 36.1` but **`v04_epsilon = 36.9`** —
the audit has silently substituted R248's value onto R227's row. I tested the obvious explanations:

- *Off-by-one shift?* **Refuted.** Across all 248 rows, 245 have `gap_epsilon == v04_epsilon`; only 3 differ
  (`EPSV04-R166`, `EPSV04-R174`, `EPSV04-R227`).
- *Stereo-sibling mis-join?* **Confirmed as the mechanism.** R166 (`ZQDPJFUHLCOCRG-WAYWQWQTSA-N`) picked up
  the value of `ZQDPJFUHLCOCRG-AATRIKPKSA-N` (*trans*-3-hexene, ε=2.000); R174
  (`KFUSEUYYWQURPO-UPHRSURJSA-N`) picked up `KFUSEUYYWQURPO-OWOJBTEDSA-N` (*trans*-1,2-dichloroethylene,
  ε=2.14). Both are **different stereoisomers sharing an InChIKey first block**. The auditor built its v04
  index by last-row-wins on that first block, so cis/trans pairs collapse and one isomer's ε is compared
  against the other's. For R227 the collapse is the GVL **dual row itself**: the index kept the second
  (`36.9`) entry.

So the provenance evidence for R227 is **self-contradictory across the project's own audit trail**, and the
defect is systemic (3 rows), not clerical. This is exactly the kind of thing the adversarial role exists to
surface, and it independently disqualifies R227 from being used as a verified datum.

---

## 3. Why the two rows get *different* verdicts

The mandate offered `NEEDS_PRIMARY_DOCUMENT` (honest refusal) or `REJECT_ROW` for both. I reject both
options as stated, because the evidence is asymmetric:

**R227 (36.1) → `REJECT_ROW`.** Its defect is not "we need a better document" — it is that the document it
cites can *never* be a primary source for a permittivity. It is a **review article** (`pubTypeList:
["review-article","Review"]`, self-described as "this review"/"this perspective"). A review's Table 3 is a
compilation of other people's values with the primary origin stripped. The project already knows this and
says so in its own metadata: `source_quality = "open_access_review_table"`, `evidence_level =
"open_access_review_table"`, `dataset_origin = "v0.3_addition"`. Asking for R227's "primary document" is
category error: **the review's primary source is R248's Segato 2021 paper.** R227 is not an independent
second measurement of GVL — it is a downstream echo of the same lineage, one compilation removed. Retaining
it as a parallel value would be **double-counting one document as two independent sources**, which is
precisely the error the conflict register was built to prevent. Add the fabricated temperature, the empty
uncertainty, and the self-contradictory audit row, and there is nothing left to retain. **Reject the row.**

**R248 (36.9) → `NEEDS_PRIMARY_DOCUMENT`.** This row's defect *is* documentary and *is* repairable. It cites
a real research article by authors who actually worked with GVL; the value sits in an SI table. What is
missing is (i) whether those authors measured it or quoted a handbook, (ii) at what temperature, and
(iii) what the SI actually says — none of which can be settled from the repository. That is the textbook
definition of `NEEDS_PRIMARY_DOCUMENT`. It should be **held, not passed and not rejected**, pending
retrieval of the Segato 2021 supporting information.

**Additional retrieval lead the project has not used.** `landolt_boernstein_2015_pure_liquid_queue.csv`
row `lb2015:0208` names a dedicated handbook chapter: *"Static dielectric constant of γ-valerolactone"*
(book DOI `10.1007/978-3-662-48168-4`, chapter DOI `10.1007/978-3-662-48168-4_90`), status
`awaiting_manual_review`, `closed_subscription`. That chapter — not the Au-catalysis SI — is the document
that would settle both 36.1 and 36.9. It is the correct target for `NEEDS_PRIMARY_DOCUMENT`.

---

## 4. Direct answer: is the conflict resolvable?

**Not from project data, and not by either value.** Three independent reasons:

1. **No measurement exists.** 0/2065 ledger rows. The conflict is between bibliography entries, not data.
2. **No condition exists.** Both temperatures are imputed (`review_table_standard_room_temperature`,
   `not_reported`), both uncertainties empty. A "same-compound, same-temperature" conflict cannot be
   asserted when **neither temperature was measured**. The register compares `298.1 K` against `298.15 K`
   and calls it one condition; that is an assumption, not a finding.
3. **The two "sources" are not independent.** `distinct_sources = 2` counts two DOIs, but one is a review
   that compiles the other's lineage. **The effective number of independent primary sources is zero — or at
   most one, pending the Segato SI.** The 2.22% spread is therefore not a cross-laboratory reproducibility
   signal; it is the difference between a number and a paraphrase of the same number.

Accordingly, `AVERAGE_JUSTIFIED` is **explicitly forbidden** (the register's own rule: 不得平均) and would in
any case be meaningless — averaging a value with a compilation of itself produces neither measurement.
`RETAIN_AS_PRIMARY` fails for both. `RETAIN_PARALLEL` is defensible *only* as a temporary holding state and
*only* for R248; for R227 it would launder a review echo into apparent independence.

**Honest disposition:** reject R227, hold R248 for the Segato SI, and separately retrieve the
Landolt-Börnstein chapter as the arbiter. Until then gamma-valerolactone has **no admissible dielectric
constant** in this project, and every model artifact that consumed 36.1 (70 files) or 36.9 (30 files,
including the orbital feature layer) is resting on an unverified number. That contamination should be
registered regardless of how the adjudication lands.

---

## 5. What I could not do (stated, not hidden)

- **Could not read the iScience Table 3 directly.** `pmc.ncbi.nlm.nih.gov/.../table/tbl3/` returned a
  reCAPTCHA interstitial; `cell.com` and `europepmc.org` returned HTTP 403. I verified the article's
  existence, type and authorship through the Crossref and EuropePMC REST APIs, but **I did not independently
  confirm that 36.1 appears in its Table 3**. The value's presence in the table is taken from the project's
  own metadata, not from my own reading of the source.
- **Could not read the Segato 2021 SI.** Elsevier paywall; no open SI located. **I did not independently
  confirm that 36.9 appears in it.** Same caveat.
- **Could not retrieve the Landolt-Börnstein chapter** (closed subscription) — hence the recommendation, not
  a resolution.
- **Could not extract an independent literature value for GVL's ε.** Repeated searches surfaced only
  secondary tables, unrelated applications (GVL as a green solvent in catalysis), or paywalled PDFs. The one
  genuinely independent primary dataset I identified — Svejda et al., *J. Chem. Eng. Data* 44(3):597,
  "Refractive Indices and Relative Permittivities of Liquid Mixtures of γ-Butyrolactone, γ-Valerolactone,
  δ-Valerolactone, or ε-Caprolactone + Benzene, + Toluene, or Ethylbenzene at 293.15 K and 313.15 K"
  (DOI `10.1021/je980288w`) — **would settle this directly** (a pure-lactone permittivity at two measured
  temperatures), but I could not extract its numeric table (ACS 403 / PDF fetch failure). **This is the
  single highest-value retrieval target after the Landolt-Börnstein chapter, and I flag it as a lead rather
  than pretending I obtained the number.**

Because I could not read either primary document myself, `evidence_grade = INSUFFICIENT` is the honest grade
for both rows. A `PASS` would have required me to search for counter-evidence and find none; I searched, and
I found the opposite — no traceable measurement, no measured temperature, no uncertainty, and a
self-contradictory audit trail.

---

## 6. Defects raised for the wider audit (beyond this pair)

1. **`gap_aggregation_audit.csv` stereo-collapse (systemic, 3/248 rows).** The v04 index is keyed on the
   InChIKey first block with last-row-wins, so stereoisomer pairs collapse (R166, R174) and dual rows collide
   (R227). `v04_epsilon` on those 3 rows does not describe the row's own `gap_epsilon`. Any conclusion drawn
   from `v04_epsilon` on those rows is invalid.
2. **Imputed temperatures are indistinguishable from measured ones downstream.** 22/248 `dielectric_v04.csv`
   rows have `temperature_source` ∈ {`review_table_standard_room_temperature`, `not_reported`}, and **18 of
   those 22 are `model_ready = true`.** R227 is one of them. The queue then presents their imputed 298.15 K
   as a condition. This is a general route by which fabricated conditions enter model training.
3. **`source_quality` is inferred from document type, not from measurement evidence.** R248 is labeled
   `primary` on the strength of being a research article; its ε is an SI value in an unrelated catalysis
   paper. The label should require positive evidence of a measurement, not merely non-review status.
4. **Downstream contamination is unflagged.** `themol_orbital_layer.csv` and
   `themol_orbital_layer_expanded.csv` carry `epsilon = 36.9` with `in_epsilon_roster = true` and
   `flagship_dielectric`, with no marker that the value is disputed. Resolving the queue without touching
   these files leaves the unresolved value in the feature layer.

---

## 7. Deliverables

- `outputs/admission_v2/reviewer_4_gvl_decisions.csv` — 2 rows, exact schema
  `queue_id,measurement_id,decision,evidence_grade,adversarial_finding,conflict_found,recommended_resolution,evidence_detail`
- `outputs/admission_v2/reviewer_4_gvl_report.md` — this file

**No other file was created or modified.** All prior `reviewer_4_decisions.csv` / `reviewer_4_report.md`
(the 70-row queue-wide review) are untouched; the GVL adjudication is delivered under the `_gvl_` filenames
the work package specified.

*Reviewer 4 · independent adversarial audit · red team · nothing passed.*
