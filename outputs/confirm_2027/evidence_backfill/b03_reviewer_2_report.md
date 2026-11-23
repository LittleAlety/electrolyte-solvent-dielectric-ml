# Reviewer 2 — Source Literature, DOI, Original Measurement and Source Independence

**Work package:** B03 / A18 evidence backfill
**Scope:** judge the *source and provenance* of the two condition-qualified measurements
(EA `nbs514:p20:022`, MA `nbs514:p18:009`) attributed to NBS Circular 514.
**Files modified:** none. This report and `b03_reviewer_2_decisions.csv` are the only outputs.

---

## Verdict summary

| | C11 (EA) | C12 (MA) |
|---|---|---|
| decision | **HOLD** | **HOLD** |
| evidence_grade | DOCUMENTED | DOCUMENTED |
| doi_verified | true | true |
| source_is_primary | **false** | **false** |
| primary_citation_found | true | true |
| independence_assessed | **false** | **false** |

**Bottom line:** the numbers are real and reproducible, but the citation is mis-graded.
NBS514 is a **secondary critical compilation**, not a primary measurement. The true primary
measurements are identifiable and are recorded in the transcription's `references` column —
which B03 read but never interpreted. Worse, **EA and MA share one upstream primary
reference (ref 63, Williams & Krchma 1927)**, so they are *not* independent sources, and the
package's own `independent_source_map.csv` contains no NBS514 row at all.

---

## 1. Is `10.6028/nbs.circ.514` real and verifiable? — **YES**

| Property | Value (verified) |
|---|---|
| Exact title | *Circular of the Bureau of Standards no. 514: table of dielectric constants of pure liquids* |
| Authors | Arthur A. Maryott and Edgar R. Smith |
| Publisher | National Bureau of Standards, Gaithersburg, MD |
| Year | 1951 |
| Type (Crossref) | `report` |
| Length | 56 PDF pages (800+ substances, sections A/B/C + 4. Bibliography) |
| DOI resolves | **YES** — `https://doi.org/10.6028/nbs.circ.514` → HTTP 302 → `http://nvlpubs.nist.gov/nistpubs/Legacy/circ/nbscircular514.pdf` |
| Crossref record | `status: ok`, `is-referenced-by-count: 170`, issued 1951, author `Maryott, Arthur A` |
| PDF metadata | title matches; `author: Maryott, Arthur A`; creator Internet Archive |

**Byte-level identity check (strongest possible).** I re-downloaded the DOI target and hashed it:

```
fresh download of doi.org/10.6028/nbs.circ.514 : cb3fa9239fd977d7fa85389fbc219baea69667d5cc7c9e5382b09157fda40683
data/raw/nbs514/nbscircular514.pdf             : cb3fa9239fd977d7fa85389fbc219baea69667d5cc7c9e5382b09157fda40683
```

Identical. The local PDF is genuinely the DOI-registered document, and the sha256 is recorded
in **two** places: `literature_source_inventory.csv` (`source_file_sha256` column) and
`nbs514_verification.json` (`inputs.nbs514_pdf.sha256`, with `bytes: 4991438`).
The four transcription parts are likewise hashed there.

Minor registry defect: NBS514 is **absent from `provenance_repair/source_document_registry_v1.csv`**
(62 rows, 0 NBS entries — that registry is ThermoML-only). NBS514 lives only in the
evidence_backfill inventory, i.e. it has no `experimental_independence_status` row of `not_evaluated`
like every other document. This is exactly why independence was never assessed.

---

## 2. Is NBS Circular 514 primary or secondary? — **SECONDARY. This is the crux.**

NBS514 is a **critical compilation**. The circular says so itself, in three independent places
that I read directly out of the PDF:

- **Introduction (p. iii):** *"The assemblage and evaluation of the data have been made entirely
  at the National Bureau of Standards…"* — the authors assembled and evaluated; they did not measure.
- **§2.6 "Literature References in Table" (p. iv):** *"**All tabulated data are based on the
  references indicated by numbers not enclosed in brackets.** The numbers refer to the bibliography
  following the table. Some additional references not employed for one reason or another are
  enclosed in brackets."*
- **§2.4 "Estimated Accuracy" (p. iv):** the accuracy flags were *"assigned **arbitrarily** after
  considerations of the **investigators' apparatus and methods**, precision, probable purity of
  materials, and comparisons, where possible, with the results of others."*

So the tabulated ε is **one critically-selected value per substance**, chosen by Maryott & Smith
from other laboratories' work. NBS514 never claims to have measured methyl or ethyl acetate.
Citing it as "the source" cites a **secondary compilation**, and the true primary measurement
sits one step further back — in the `references` column, which the transcription carries but
B03 did not interpret.

Corroborating detail: the "static" frequency is inherited from the compiled sources, and the
package's own note `static (NBS514 tabulates static values)` is a restatement of §2, not a
measurement condition NBS514 controlled.

**Consequence:** `evidence_grade` must not be treated as a primary-measurement grade. The value
is *documented* (it is faithfully transcribed from a real, hashed document) but it is *derived*
(second-hand). Both rows are therefore HOLD, not PASS.

---

## 3. Page reads traced — **both reproduce exactly**

Transcription file: `data/interim/nbs514_organic_part1.csv` (200 rows; parts 1–4 total 636 rows).

**MA — `nbs514:p18:009`**

```
source_page=18  section="C. ORGANIC LIQUIDS"  formula=C3H6O2  compound_name="Methyl acetate"
dielectric=6.68  t_C=25  T_K=298.15  alpha_1e5=2200.0  alpha_kind=a  valid_range_C="25,40"
references="63,260"   source_quality=three_figures
```

PDF page 18 (printed page 10), section C, reads:

```
Methyl acetate.
6.68
25
2.2
25,40
63,260
```

Exact match, including the reference string.

**EA — `nbs514:p20:022`**

```
source_page=20  section="C. ORGANIC LIQUIDS"  formula=C4H8O2  compound_name="Ethyl acetate"
dielectric=6.02  t_C=25  T_K=298.15  alpha_1e5=1500.0  alpha_kind=a  valid_range_C="at 25"
references="8,63,276"  source_quality=three_figures
```

PDF page 20 (printed page 12), section C, reads:

```
Ethyl acetate......
6.02
25
1.5
at 25
8,63,276
```

Exact match. 25 °C → 298.15 K is correct. Coverage is complete: transcription spans printed
pages 13–47 with **no gaps** in 13–46, so "not found" below is a real absence, not a hole in the
data.

**Locator caveat (should be fixed).** The `p18`/`p20` in the locators are **PDF page indices**,
while the document's own printed page numbers are 10 and 12. `source_verification.csv` calls
`nbs514:p20:022` "page 20", which will not match the printed folio. Reproducible only if the
index convention is declared.

---

## 4. Primary citations traced from the `references` field

Resolved against the NBS514 bibliography (printed pp. 40–44, PDF index 47–51):

| Ref | Primary citation | Cited for |
|---|---|---|
| **8** | K. F. Lowe, *Ann. Physik* **66**, 390 (**1898**) | EA |
| **63** | **J. W. Williams & I. J. Krchma, *J. Am. Chem. Soc.* 49, 1676 (1927)** — "The dielectric constants of binary mixtures. II" | **EA and MA** |
| **260** | S. R. Phadke, S. D. Gokhale, N. L. Phalnikar & B. V. Bhide, *J. Indian Chem. Soc.* **22**, 235 (1945) | MA |
| **276** | A. N. Shidlovskaya & Y. K. Syrkin, *J. Phys. Chem. (U.S.S.R.)* **22**, 913 (1948) | EA |

So `primary_citation_found = true` for both — the primary literature is identifiable and is
already sitting in the repository, just uninterpreted.

---

## 5. Independence — **FAILED for the EA/MA pair**

**Ref 63 is shared.** MA cites `63,260`; EA cites `8,63,276`. The common upstream primary
measurement is Williams & Krchma (1927). Two values that descend from one laboratory's 1927
measurement campaign **cannot be counted as two independent sources**.

This is not a theoretical risk. `independent_source_map.csv` exists precisely to catch this
class of entanglement and already flags 8 ThermoML pairs as `NOT_INDEPENDENT` on the grounds
that identical full-precision (inchikey, T, ε) values "cannot arise from two independent
measurements". Yet that map contains **zero rows mentioning NBS514**, and NBS514 is not in
`source_document_registry_v1.csv`, so its `experimental_independence_status` was never set to
`not_evaluated` as it was for all 61 ThermoML documents. **The independence check was skipped for
exactly the two rows it most needed to cover.**

Additional entanglement: Williams & Krchma (1927) is a *binary-mixtures* paper; the acetate
values were likely obtained in solution and referenced back, and EA's other source (Lowe 1898)
is a 19th-century measurement. Both rows are only `three_figures`, which NBS514 §2.4(b) rates
as *"probably accurate to 2 percent or better"* — i.e. 6.02 ±0.12 and 6.68 ±0.13. Any downstream
model that treats these as precision anchors will be over-confident.

**Downstream consequence:** if both EA and MA enter B04 as separate sources, `n_contributing_sources`
is inflated by one. They must be collapsed into a single source cluster rooted at ref 63, or at
minimum annotated with `SOURCE_DUPLICATION_ENTANGLED`.

---

## 6. The 7 "uncovered" P4 molecules — **genuinely uncovered in NBS514, but that is NOT evidence of absence**

I verified the absence **against the PDF text itself**, not just the transcription, for all seven:

| Molecule | ID | Searched (PDF full text) | Result |
|---|---|---|---|
| EMC | C02 | `ethyl methyl carbonate`, `carbonic acid ethyl` | no match |
| EC | C04 | `ethylene carbonate`, `1,3-dioxolan-2-one` | no match |
| PC | C05 | `propylene carbonate`, `4-methyl-1,3-dioxol` | no match |
| FEC | C06 | `fluoroethylene`, `fluorodioxol` | no match |
| VC | C07 | `vinylene carbonate`, `dioxol-2-one` | no match |
| DOL | C09 | `dioxolane`, `dioxolan` | no match (`dioxol` count = 0) |
| TMP | C17 | `trimethyl phosphate`, `methyl phosphate` | no match |

Notes on near-misses (correctly *not* claimed as coverage):
- **EMC** — only hit was `nbs514:p20:025 beta-Hydroxyethyl acetate (Glycol monoacetate) C4H8O3`,
  a formula isomer, not EMC. Correctly rejected.
- **PC** — only hit was `Acetic anhydride C4H6O3` (same formula). Correctly rejected.
- **TMP** — the PDF contains only `Tributylphosphate C12H27O4P` and `Tricresyl phosphate`;
  `trimethyl phosphate` is absent. Correctly rejected.
- The whole circular contains **one** carbonate entry (`Diethyl carbonate`, C5H10O3 — that is DEC,
  not EMC) and **one** dioxane entry (`1,4-Dioxane`), and **zero** dioxolane entries.

**Assessment — absence from one compilation is NOT evidence of absence.** All seven are
electrolyte-solvent staples whose static dielectric constants are unquestionably measured and
published many times over; EC and PC in particular are among the most-measured liquids in the
electrochemistry literature. NBS514 simply predates the commercial relevance of the
fluorinated/vinylene carbonates and did not index these particular names (its §2.3 ordering is
by formula, and coverage of carbonates is demonstrably thin). Therefore:

- `NO_NBS514_COVERAGE` is a **correct and defensible label for this one source** — the package
  does not overclaim, and it explicitly forbids constructing evidence from NBS514 for them.
- It is **not** a negative literature finding. The `unresolved_molecules.csv` blocker text
  *"该分子在 ThermoML 与 NBS514 中均无覆盖"* (no coverage in ThermoML **and** NBS514) is accurate
  as far as it goes, but the two-source basis is narrow. The correct next action is to search
  primary literature / other databases (e.g. NIST/TRC, Landolt-Börnstein, IUPAC-NIST Solubility
  and dielectric compilations), **not** to record these as unmeasurable.

---

## 7. Required corrections before either row can PASS

1. **Re-grade the citation as secondary.** `source_is_primary = false`. Cite NBS514 as a
   *compilation* and cite the primary references (8, 63, 260, 276) alongside it.
2. **Collapse EA and MA into one source cluster** via shared ref 63, and add an NBS514 row to
   `independent_source_map.csv` recording `NOT_INDEPENDENT` for (C11, C12) with basis
   "shared primary reference 63 = Williams & Krchma, JACS 49, 1676 (1927)".
3. **Register NBS514** in `source_document_registry_v1.csv` with
   `experimental_independence_status = not_evaluated` and its sha256, so it is no longer
   invisible to the independence machinery.
4. **Fix the locator convention** — either state "PDF page index" explicitly or convert to the
   printed folio (MA = p10, EA = p12).
5. **Carry the 2 % accuracy band** (`three_figures`) into any downstream use; do not treat
   6.02 / 6.68 as high-precision anchors.

## 8. What is *not* wrong

To be fair to the package: the transcription is faithful, the PDF is present and correctly
hashed, the DOI is real and resolves, the values reproduce byte-exactly from the page, the
T = 298.15 K conversion is right, the `three_figures` quality flag is honestly recorded, and
the decision to keep these rows **out of `measurement_ledger`** (which requires ThermoML +
`source_file_sha256`) is the correct call. The defect is not fabrication or transcription error
— it is **provenance mis-labelling and a skipped independence check**.
