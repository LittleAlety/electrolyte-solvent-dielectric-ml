# Reviewer 2 Report — Source Literature, DOI, Original Measurement and Source Independence

**Work package:** B04-PRECONFLICT · project `electrolyte-solvent-dielectric-ml`
**Reviewer:** Reviewer 2 of 4 (independent) · **Scope:** source/DOI verification and source independence only
**Deliverable:** `reviewer_2_decisions.csv` (2 rows, exact schema)

---

## 0. Summary of verdicts

| conflict_id | molecule | decision | evidence_grade | DOIs resolved | genuinely independent | resolution |
|---|---|---|---|---|---|---|
| `MCONF-BTANRVKWQNVYAZ-298` | butan-2-ol | **PASS** | DOCUMENTED | 4 / 4 | **2** (not 4) | `KEEP_V06_VALUE` |
| `MCONF-FXHOOIRPVKKKFG-303.15` | N,N-dimethylethanamide | **HOLD** | DOCUMENTED | 3 / 3 | **2** (not 3) | `NEEDS_PRIMARY_DOCUMENT` |

**Headline:** both conflicts are inflated by duplicate counting — each collapses from 4→2 and 3→2 independent experiments. But they behave in *opposite* ways once the duplicates are removed. Butan-2-ol **dissolves** (the survivors agree within their own stated uncertainties). DMAc **survives and hardens** (the survivors disagree at 4.2 σ, and deduplication is what reveals it).

---

## 1. Do the DOIs resolve to real publications?

Yes — all **7 of 7**. Verified two ways independently: the Crossref REST API (`api.crossref.org/works/<doi>`) and the citation block inside each local ThermoML record. Metadata agreed on title, journal, year, volume and pages in every case.

| DOI | Title (abridged) | Journal | Year | Vol:Pages | Authors |
|---|---|---|---|---|---|
| `10.1016/j.fluid.2013.12.014` | Dielectric constant of dimethyl sulfoxide–monohydric alcohol mixture solution at the microwave frequency | Fluid Phase Equilib. | 2014 | 365:5–10 | Guo-Zhu Jia; Qian Jie |
| `10.1021/je3007666` | Static Permittivities of Isomeric Butanol Mixtures at Temperatures from (288.15 to 308.15) K | J. Chem. Eng. Data | 2012 | 57:3164–3170 | Klimaszewski; Boruń; Bald; Sengwa |
| `10.1021/je800593p` | Dielectric Properties of Methanol Mixtures with Ethanol, Isomers of Propanol, and Butanol | J. Chem. Eng. Data | 2009 | 54:801–806 | Chmielewska; Zurada; Klimaszewski; Bald |
| `10.1021/je900503p` | Relative Permittivities, Refractive Indices, and Densities of Dihydrofuran-2(3H)-one + Butan-1-ol and + Butan-2-ol at *T* = (293.15, 298.15, 303.15, and 313.15) K | J. Chem. Eng. Data | 2010 | 55:1035–1038 | Farhan; Awwad |
| `10.1016/j.fluid.2008.01.024` | Dielectric properties and hydrogen bonding interaction behaviour in binary mixtures of glycerol with amides and amines | Fluid Phase Equilib. | 2008 | 266:54–58 | Sengwa; Khatri; Sankhla |
| `10.1016/j.fluid.2009.07.009` | Dielectric constant and molecular association in binary mixtures of N,N-dimethylethanolamine with alcohols and amides | Fluid Phase Equilib. | 2009 | 285:50–53 | Sengwa; Sankhla; Khatri |
| `10.1021/je9002515` | Static Dielectric Permittivity and Electric Conductivity of *N*-Methylacetamide + *N*,*N*-Dimethylacetamide Mixtures | J. Chem. Eng. Data | 2009 | 54:2296–2300 | Świergiel; Jadżyn |

All seven are **primary research articles** in two primary measurement journals. **None is a secondary compilation.** This matters for item 4 below: the usual "compilation vs primary" tie-breaker is unavailable, so quality must be ranked on measurement design instead.

---

## 2. Are any of them the same underlying experiment? — Yes, both conflicts

This is the crux, and the answer is yes in both cases. I did not rely on the project's prior flagging alone; I re-derived it from the raw ThermoML files, which carry value, expanded uncertainty, method and sample metadata per data point.

### Conflict 1 — butan-2-ol: 4 DOIs → **2** experiments

The neat butan-2-ol point at ~298 K in each document:

| DOI | T / K | ε | u (95 %) | method | group |
|---|---|---|---|---|---|
| `10.1021/je3007666` | 298.15 | **16.60** | 0.06 | Dielectrometer | Klimaszewski/Boruń/Bald/Sengwa |
| `10.1021/je800593p` | 298.15 | **16.60** | 0.06 | dielectrometer | Chmielewska/Zurada/Klimaszewski/Bald |
| `10.1021/je900503p` | 298.15 | **16.58** | 0.06 | Dekameter | Farhan & Awwad |
| `10.1016/j.fluid.2013.12.014` | 298 | **17.60** | **1.90** | PNA-N5227A microwave network analyzer | Guo-Zhu Jia & Qian |

**je3007666 ≡ je800593p** is a byte-identical duplicate: same ε to the last digit, *and* the same 0.06 expanded uncertainty, same method, and three of four authors overlap (Klimaszewski, Bald) — the project's `duplicate_observation_groups.csv` already flags this as `DUPLICATE_TRANSCRIPTION_NOT_REPLICATION`, and `source_independence_report.json` records 15 shared observations between this pair, the most entangled pair in the entire dataset.

**je900503p is also not independent, contrary to what the 4-source count implies.** Two independent arguments:

1. *Direct value collisions with the Klimaszewski cluster at other temperatures.* At 293.15 K, je900503p gives 17.51 — identical to both je3007666 and je800593p. At 303.15 K it gives 15.75 — again identical to both. At 298.15 K it gives 16.58, i.e. 0.02 from 16.60. Across the whole overlap the three documents reproduce each other's values to 2–3 significant figures *including the identical 0.06 expanded uncertainty*, which two genuinely separate Dekameter and dielectrometer measurements would not do.
2. *Structural.* Farhan & Awwad's paper is about dihydrofuran-2(3H)-one + butanol mixtures; neat butan-2-ol appears only as the pure-component end member. Its purpose there is a literature-anchored reference point, not an independent determination.

**⇒ 2 genuinely independent experiments:** Klimaszewski/Bald dielectrometer series (16.60 ± 0.06) and Guo-Zhu & Qian (17.60 ± 1.90).

### Conflict 2 — DMAc: 3 DOIs → **2** experiments

| DOI | T / K | ε | u (95 %) | method | group |
|---|---|---|---|---|---|
| `10.1016/j.fluid.2008.01.024` | 303.15 | **37.72** | 0.23 | capacitive | Sengwa/Khatri/Sankhla |
| `10.1016/j.fluid.2009.07.009` | 303.15 | **37.72** | 0.23 | parallel plate capacitor | Sengwa/Sankhla/Khatri |
| `10.1021/je9002515` | 303.15 | **38.67** | 0.387 | parallel plate capacitor | Świergiel & Jadżyn |

The two Fluid Phase Equilibria papers share **the same three authors in permuted order** and report the neat-DMAc point at 303.15 K as ε = 37.72 with an **identical** expanded uncertainty of 0.23. `source_independence_report.json` records 5 shared observations across this document pair. Duplicate transcription, not replication.

**⇒ 2 genuinely independent experiments:** Sengwa (37.72 ± 0.23) and Świergiel & Jadżyn (38.67 ± 0.387).

---

## 3. Is the spread an artefact of duplicated data?

**For butan-2-ol: yes, entirely.** **For DMAc: no — and deduplication makes it worse, not better.** This is the single most important asymmetry in this adjudication, and it is why the two conflicts receive different decisions.

### Butan-2-ol — the conflict dissolves

After deduplication the residual difference is 1.00 in ε against a combined standard uncertainty of 0.95:

- **1.05 σ** in standard-uncertainty terms
- **0.53 ×** the combined 95 % expanded uncertainty

The two independent experiments **agree within their stated uncertainties.** Three further checks confirm the spread is not a real physical disagreement:

1. **The deviating point's own interval contains the consensus value.** Guo-Zhu's 17.60 ± 1.90 gives [15.70, 19.50], which brackets 16.60 comfortably. Its own relative uncertainty is **10.8 %** — larger than the 6.15 % spread it was accused of creating.
2. **Temperature binning is not the cause.** Guo-Zhu reports T = 298 K (3 significant digits) while the others report 298.15 K. Using the measured dε/dT = −0.177 K⁻¹, the 0.15 K mis-binning contributes only **0.027** in ε — negligible against the 1.00 residual.
3. **The conclusion is robust to the independence judgment.** Even if I am wrong about je900503p and it *is* independent, the low group mean becomes 16.59 and the difference is 1.01 → **1.06 σ**, still consistent.

So the reported 6.15 % spread is an artefact of two compounding errors: counting one duplicated experiment three times, and including a low-precision single point whose error bar is wider than the spread itself. **There is no genuine conflict here.**

### DMAc — the conflict is real, and larger than reported

After deduplication the residual difference is 0.95 against a combined standard uncertainty of 0.225:

- **4.22 σ** in standard-uncertainty terms
- **2.11 ×** the combined 95 % expanded uncertainty

This is a **statistically significant disagreement**, not a rounding or binning effect (both are at exactly 303.15 K, so no temperature mismatch exists). Critically, the duplicated pair was *masking* the conflict: pooling two identical Sengwa values as if they were two observations would shrink the standard error to 0.081 and inflate the discrepancy to **4.53 σ**, while simultaneously creating a false impression of 2-against-1 support. Deduplication correctly reduces Sengwa's weight to a single experiment and exposes the disagreement as a clean 1-vs-1.

---

## 4. Which source is highest quality?

All seven are primary articles, so quality is ranked on **measurement design**, not on journal tier.

**Butan-2-ol — `10.1021/je3007666` (Klimaszewski et al., JCED 2012) is clearly best.**
- A **dedicated** isomeric-butanol study; butan-2-ol is a principal objective, not a by-product.
- A self-consistent **5-temperature series** (288.15–308.15 K) with tight, uniform u = 0.06 (0.36 % relative), allowing an internal dε/dT check — which I used above and which is physically sensible.
- Documented sample provenance: commercial, 99.5 % stated by supplier, **fractionally distilled**.
- It is also the same value the v06 dataset already carries (16.60).

By contrast, Guo-Zhu & Qian is a DMSO–alcohol mixture study measured at a single nominal 298 K with a 10.8 % relative uncertainty, where butan-2-ol is one of six alcohols used as a mixture component. It is not wrong — it is simply too imprecise to overturn a dedicated measurement, and it does not disagree with it.

**DMAc — `10.1021/je9002515` (Świergiel & Jadżyn, JCED 2009) is the stronger record.**
- A **dedicated** dielectric study with DMAc as a principal objective.
- A **self-consistent 10-point series** from 303.15 to 393.15 K (38.67 → 24.923), giving an internal consistency check the single-point Sengwa papers cannot offer. Its local slope (−0.212 K⁻¹) back-extrapolates to ε(298.15 K) = **37.61**, close to the widely cited anchor of 37.78 ([N,N-dimethylacetamide, ε = 37.78 at 298.15 K](https://ir.nbu.ac.in/bitstream/123456789/703/5/05%20chapter%202.pdf)).
- Sample purity **99.5 %, stated by supplier**.
- It also measured electrical conductivity in the same cell — relevant, because both groups used a parallel-plate capacitor on a conductive liquid, where low-frequency electrode polarisation is the dominant systematic.

Against this, the Sengwa values carry real weaknesses: DMAc is a **minor component** in both papers (glycerol + amides; N,N-dimethylethanolamine + amides), reported at a **single temperature** with no series and hence no internal check; and the 2009 record's purity is **compiler-estimated at only 98 %**, for a strongly hygroscopic solvent whose water content is not recorded in ThermoML. Water contamination depresses ε in DMAc, which would push a value *down* — consistent in direction with Sengwa's lower 37.72.

**However, quality ranking does not settle this conflict**, for two honest reasons:
- Both 37.72 and 38.67 sit near **distinct documented literature clusters** (≈37.78 and ≈38.9). Neither value is an obvious outlier on priors.
- The discriminating information — frequency range, the low-frequency extrapolation/correction protocol, and actual water content — lives in the **primary PDFs** and is simply **absent from ThermoML metadata**.

---

## 5. Recommendations

### `MCONF-BTANRVKWQNVYAZ-298` → **PASS** / `KEEP_V06_VALUE`

No genuine conflict exists. The v06 value 16.60 is the highest-precision primary measurement, comes from a dedicated study, and is statistically consistent with the only other independent experiment (1.05 σ; 0.53 × combined 95 % U). Keep 16.60.

Two follow-up actions that do **not** block B04:
- **Collapse the source count from 4 to 2** anywhere downstream (B07 robustness, "n independent sources ≥ k" claims). Reporting 4 would be a factual error.
- **Record 17.60 / `10.1016/j.fluid.2013.12.014` as a corroborating low-precision observation**, not as a competing value. Do not exclude it — it agrees — but it must not be given equal weight, and it must not be counted as a second independent source alongside the Klimaszewski cluster.

### `MCONF-FXHOOIRPVKKKFG-303.15` → **HOLD** / `NEEDS_PRIMARY_DOCUMENT`

The conflict is real, bounded (2.52 %), statistically significant (4.22 σ), and **not resolvable from bibliographic metadata**. Metadata verification is complete and successful; the missing evidence is measurement-protocol detail held only in the primary documents.

Concretely: obtain the three primary PDFs and check, in priority order —
1. **Water content / purity statement**, especially Sengwa 2009 (compiler-estimated 98 %).
2. **Frequency range and low-frequency extrapolation method** for the parallel-plate capacitor measurements, including any electrode-polarisation correction.
3. Whether the two Sengwa papers describe **one or two measurement campaigns** (they share authors, method and values; confirming this would justify permanently collapsing them to one evidence unit).

Then resolve to exactly one of:
- `ADOPT_OTHER_VALUE` → adopt **38.67** if Świergiel's protocol is confirmed sound and Sengwa's sample is shown to be wet or its correction inadequate;
- `KEEP_V06_VALUE` → keep **37.72** if the opposite is shown;
- `RETAIN_PARALLEL` → only if both survive scrutiny, keeping one value with the 0.95 (2.5 %) disagreement carried as a **documented label uncertainty** rather than deleting an experiment.

**Do not silently keep 37.72.** The v06 value happens to equal the duplicated Sengwa value, which is precisely the value whose evidential weight deduplication just halved.

---

## 6. Method, provenance and limitations

**What I verified directly (DOCUMENTED):** all 7 DOIs against Crossref; all 7 titles/journals/years/volumes/pages against the local ThermoML citation blocks; every ε value, expanded uncertainty, temperature, pressure, method string and sample-purity record re-extracted from the raw ThermoML XML rather than taken from the project's derived CSVs; duplicate structure re-derived from first principles and cross-checked against `duplicate_observation_groups.csv` and `source_independence_report.json`.

**Reproducibility.** Extraction and statistics were scripted read-only in `outputs/b01/conflict_adjudication/`: `_r2_extract.py`, `_r2_verify.py`, `_r2_stats.py`, `_r2_corpus.py`, `_r2_emit.py`. **No existing file was modified.** Scripts are retained as an audit trail.

**Corpus-wide tie-break attempt (negative result, reported honestly).** I scanned all 726 local ThermoML files for *any* other neat-compound static-permittivity data on these two molecules. Result: **exactly the same documents already in dispute** — 4 for butan-2-ol, 3 for DMAc. No independent fourth source exists in the local corpus to break the DMAc tie, which is why `NEEDS_PRIMARY_DOCUMENT` is the honest resolution rather than a fabricated preference.

**Limitations I want on the record:**
1. **Uncertainty convention.** ThermoML records these as `nCombExpandUncertValue` with level of confidence 95, so I treated them as *expanded* (k ≈ 2) and divided by 2 for the σ tests. If any are in fact standard uncertainties, the butan-2-ol conclusion is unchanged (it only becomes more consistent), and the DMAc conflict becomes *stronger* (≈8 σ). The direction of both verdicts is therefore robust to this convention.
2. **Author-level independence is not observable.** As `source_independence_report.md` correctly states, document-level metadata cannot prove experimental independence. My je900503p call rests on value/uncertainty collisions plus structural reasoning, not on a signed statement. It is graded DOCUMENTED because the collisions are directly observable; the *interpretation* is inference, and I have flagged that the butan-2-ol verdict is insensitive to it.
3. **No primary PDFs were consulted** for this review. Everything here is metadata- and ThermoML-level. That is precisely the boundary that forces HOLD on DMAc.
4. **I did not consult the other three reviewers**, per instructions, and did not modify the conflict register or dataset.

---

## 7. Files

| Path | Content |
|---|---|
| `outputs/b01/conflict_adjudication/reviewer_2_decisions.csv` | Required 2-row, 8-column deliverable (schema and enums validated) |
| `outputs/b01/conflict_adjudication/reviewer_2_report.md` | This report |
| `outputs/b01/conflict_adjudication/_r2_*.py` | Read-only extraction/statistics scripts (audit trail) |
