# B03 A18 Evidence Backfill — Reviewer 1 Report
## Chemistry, Physics and Experimental-Condition Soundness

**Role:** Reviewer 1 of 4, independent. Work package B03 (A18 evidence backfill).
**Scope:** the two condition-qualified records added from NBS Circular 514.
**Artifact:** `outputs/confirm_2027/evidence_backfill/b03_reviewer_1_decisions.csv`
**Verdict:** both records **PASS** on chemistry and experimental-condition grounds, at evidence grade **DOCUMENTED**. Two provenance defects are flagged in §7 and are outside my remit to adjudicate.

---

## 1. Summary of decisions

| a_mol_id | Name | decision | evidence_grade | chemistry_plausible | phase_physical | temperature_is_measured | frequency_comparable |
|---|---|---|---|---:|---:|---:|---:|
| C11 | EA (ethyl acetate) | **PASS** | DOCUMENTED | true | true | true | true |
| C12 | MA (methyl acetate) | **PASS** | DOCUMENTED | true | true | true | true |

ε = 6.02 (EA) and 6.68 (MA) at 298.15 K, both from `10.6028/nbs.circ.514`, records `nbs514:p20:022` (page 20) and `nbs514:p18:009` (page 18).

**A note on what PASS means here.** My verdict covers chemistry and experimental conditions only. It says the numbers are chemically real, physically plausible, correctly phased, and correctly frequency-classified. It does **not** certify source independence — see §7, where I find that the independence check in `source_verification.csv` is circular. A reviewer responsible for provenance should not read my PASS as clearing that.

---

## 2. Method

I did not take the repository's transcription on trust. I read the primary artifact:

- `data/raw/nbs514/nbscircular514.pdf` — 56 pages, sha256 `cb3fa9239fd977d7fa85389fbc219baea69667d5cc7c9e5382b09157fda40683`, matching the hash recorded in `nbs514_verification.json`.
- Extracted with PyMuPDF 1.x under the project venv (`.venv/Scripts/python.exe`, Python 3.12.14).
- Located the two rows on the printed pages and confirmed the digits, the temperature column, the α column, the applicability range and the reference numbers against `data/interim/nbs514_organic_part1.csv` lines 103 and 160.
- Read the introduction (printed pp. iii–iv) for NBS's own definitions of "static", accuracy class, and reference convention, and the bibliography (printed p. 40 ff.) for the primary references.

Chemistry checks used RDKit 2026.03.6 for InChIKey regeneration. Physics checks used closed-form Kirkwood–Fröhlich, Debye relaxation and two effective-medium mixing models. Every formula below was validated on a system with a known answer before being applied (water g = 2.81 vs literature 2.8–2.9; methanol g = 3.07 vs 2.6–2.9; ethanol g = 3.14 vs 2.2–3.0).

No existing file was modified. All scratch scripts are prefixed `_tmp_r1_` in the evidence_backfill directory and are disposable.

---

## 3. Chemical identity

| | EA | MA |
|---|---|---|
| SMILES used | `CCOC(=O)C` | `CC(=O)OC` |
| InChIKey claimed | `XEKOWRVHYACXOJ-UHFFFAOYSA-N` | `KXKVLQRXCPHEJC-UHFFFAOYSA-N` |
| InChIKey regenerated | `XEKOWRVHYACXOJ-UHFFFAOYSA-N` | `KXKVLQRXCPHEJC-UHFFFAOYSA-N` |
| Formula / MW | C4H8O2 / 88.11 | C3H6O2 / 74.08 |
| Components | 1 | 1 |

Both match exactly. Both are real, single-component, neutral (the `UHFFFAOYSA` block signals no stereochemistry, correct for these achiral esters), and both are liquid at 298.15 K. The v04 SMILES (`CCOC(C)=O`, `COC(C)=O`) are the same molecules in a different writing order, not identity conflicts.

The names in the compilation are unambiguous — "Methyl acetate" and "Ethyl acetate" appear as plain names under the correct formulas C3H6O2 and C4H8O2, and NBS's own ordering rule (carbon count, then hydrogen count) places them correctly in section C. There is no isomeric ambiguity of the kind that affects, say, the crotononitrile or dibromobutane rows.

**Verdict: identity sound for both.**

---

## 4. Physical plausibility of ε

### 4.1 Direct comparison with literature

| | NBS514 (25 °C) | Modern tabulated (25 °C) | Back-extrapolated to 20 °C | Literature 20 °C |
|---|---:|---:|---:|---|
| MA | 6.68 | 6.68 | **6.790** | 6.79 (Dean) / 6.87 |
| EA | 6.02 | 6.02 | **6.095** | 6.09 / 6.10 |

The back-extrapolation uses NBS's own printed temperature coefficient (α = 2.2×10⁻³ °C⁻¹ for MA, 1.5×10⁻³ °C⁻¹ for EA, in the `a` = −dε/dt convention). It reproduces independent 20 °C literature values to **0.00%** (MA) and **0.08%** (EA). That is a genuine external check: the coefficient and the anchor temperature are separate pieces of information in the table, and together they land on a number the compilers did not tabulate.

### 4.2 The homologous series — and the MA > EA question

The task asks me to verify that MA > EA is what the data shows, since chemistry predicts it. I read all four acetate rows from the same printed circular rather than comparing two isolated numbers:

| Ester | ε | t | NBS page |
|---|---:|---:|---|
| Methyl acetate | **6.68** | 25 °C | printed p. 10 |
| Ethyl acetate | **6.02** | 25 °C | printed p. 12 |
| Propyl acetate | 5.69 | 19 °C | printed p. 16 |
| Butyl acetate | 5.01 | 20 °C | printed p. 20 |

**The series is strictly monotonic decreasing. MA > EA is confirmed, and MA is the series maximum.**

Is the 0.66 gap real, or an artefact of rounding? NBS assigns 3-figure values class (b) accuracy — "probably accurate to 2 percent or better". Propagating both bands in quadrature gives 0.180, so the gap is **3.67× the combined band**. Even in the pathological case where both errors run adversarially (MA low by 2%, EA high by 2%), the ordering holds: 6.546 > 6.140. The sign of the MA − EA difference is not in doubt.

### 4.3 Why the trend is the right shape

Two independent arguments, both of which the data satisfy:

**Dipole number density.** N·μ² (N from liquid density, μ from gas-phase dipole moment) falls monotonically across the series, normalised to MA:

| | N·μ² | ε |
|---|---:|---:|
| MA | 1.000 | 6.68 |
| EA | 0.870 | 6.02 |
| Propyl | 0.747 | 5.69 |
| Butyl | 0.685 | 5.01 |

The ε ratio MA/EA = 1.11 and the N·μ² ratio = 1.15 agree to ~4%. The chain-lengthening effect is not a mystery needing a special explanation — it is quantitatively what dilution of the ester dipole by added CH₂ does.

**Kirkwood–Fröhlich correlation factor.** Using g = [9ε₀k_BT·M/(N_A·ρ·μ²)] · [(ε−ε∞)(2ε+ε∞)] / [ε(ε∞+2)²] with ε∞ = n_D²:

| | g_KF |
|---|---:|
| MA | 0.972 |
| EA | 0.958 |
| Propyl | 1.011 |
| Butyl | 0.903 |

All four sit at g ≈ 0.9–1.0. This is the physically expected result for a non-hydrogen-bonded ester: essentially no parallel dipole correlation. It is also a **sensitive negative test for contamination** — water (g = 2.8) or a dissolved ionic species would push g far above 1. The measured ε values are consistent with an isolated-molecule Onsager/Kirkwood liquid and inconsistent with an inflated contaminated one.

**Verdict: ε plausible for both, and the series behaviour is chemically correct.**

---

## 5. Phase consistency at 298.15 K

| | mp | bp | 298.15 K position |
|---|---:|---:|---|
| MA | 175.10 K (−98.0 °C) | 329.95 K (56.8 °C) | 123.1 K above mp, **31.8 K below bp** |
| EA | 189.55 K (−83.6 °C) | 350.25 K (77.1 °C) | 108.6 K above mp, 52.1 K below bp |

Both are unambiguously liquid at 298.15 K. NBS states in §2 of the introduction that "usually the pressure is atmospheric or insignificantly different", and that a vapour-pressure footnote is given where data are listed above the normal boiling point. Neither row carries such a footnote, and neither is near its boiling point, so the measurement is at ~1 atm in the normal liquid range.

The only phase-adjacent risk worth naming is MA's volatility (bp 57 °C, ~32 K of margin). A 1951 open-cell capacitance measurement of a solvent this volatile is exposed to evaporative composition drift and to condensation on cell walls. That is a real historical hazard, but NBS flags no such caveat, the assigned accuracy is class (b), and the value agrees with modern data to <1%. I record it as a residual risk rather than a defect.

**Verdict: phase assignment physical for both.**

---

## 6. Temperature provenance — measurement or tabulation convention?

**I judge these to be MEASUREMENT temperatures, not a tabulation convention.** This is the question the task flags as mattering, so I give my reasoning explicitly, since the opposite reading is defensible on a superficial look.

The argument for "convention" would be: a 1951 compilation has to standardise, 25 °C is the obvious standard state, so the printed t might be a house normalisation rather than what the experimenter actually held.

Three pieces of evidence from the document itself refute that:

1. **The tabulated t is not standardised.** In section C part 1, 200 rows carry a numeric t spanning **13 distinct values** (15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 30 °C). Only 45/200 = 22.5% are at 25 °C; **97/200 = 48.5% are at 20 °C**. If 25 °C were a tabulation convention, the column would be near-constant. It is not. NBS is reporting the temperature at which each value was obtained, and 20 °C happens to be the more common historical choice.

2. **The coefficient is fitted over an explicit range anchored on t.** §2.5 states that ε_t, t, and α are all specified in the table and the equation is valid over the printed t₁, t₂ range. For EA the range literally reads **"at 25"**, and for MA **"25,40"** — the printed t is the *anchor point of the fit*, not a relabelling applied afterwards. An anchor must be an actual state of the data.

3. **The anchor behaves like a real measurement under extrapolation.** §4.1's 20 °C back-extrapolation lands on independent literature values to <0.1%. A convention-driven number would not have that property.

A fourth, decisive point for this specific work package: **298.15 K is the anchor itself for both rows.** So whatever the philosophical status of the printed t, *zero* temperature harmonisation or extrapolation is being applied to these two records. This is materially different from the rest of the NBS514 corpus, where the anchor is usually 293.15 K and a shift is needed — the project's own harmonisation probe reports a median absolute shift of 0.0108 ε units and a maximum of 2.5 across 42 v0.3 records. EA and MA are in the `already_at_target` class. The `temperature_is_measured = true` flag is therefore safe in the strong sense: the number used needs no temperature correction at all.

**Verdict: temperature is a measured condition for both.**

---

## 7. Frequency semantics — is a 1951 "static" value comparable to a modern zero-frequency datum?

**Substantially yes, with a caveat about what "static" certifies.**

### What NBS actually claims

Introduction §2: "The dielectric constants are intended to be the limiting values at low frequencies, the so-called 'static' values. Data obtained at such high frequencies that anomalous dispersion was evident are not included. In questionable cases the frequency is given in a footnote."

This is a *curated exclusion rule*, not a measurement protocol. NBS did not measure at 0 Hz; they selected low-frequency data and excluded dispersion-affected data. That is the honest characterisation of a 1951 compilation's "static".

### Is the exclusion real, and does it bind these two rows?

Yes on both counts. The repository's own frequency-gate audit (`reports/nbs514_frequency_gate_audit.md`) establishes that 127 of 636 rows carry an explicit frequency note (3.6, 4, 5 × 10⁸ cycles/sec — i.e. 360–500 MHz, inside the dispersion region), and that **0 of those 127** entered the frozen dataset. The gate is enforced and it is not vacuous.

Critically for my two records: **neither EA nor MA carries any frequency footnote.** I verified this on the printed page. The `f = 3.6 × 10⁸` and `f = 5 × 10⁸` footnotes on the methyl acetate page attach to propionaldehyde and propyl nitrate / isopropyl nitrite respectively; on the ethyl acetate page the `f = 3.6 × 10⁸` footnote attaches to butyronitrile and isobutyronitrile. The absence of a footnote on EA and MA is NBS's affirmative statement that no dispersion correction was needed — which is exactly the §2 "in questionable cases" clause failing to trigger.

### How much could a 1951 bridge frequency bias the result?

Methods available in 1951 were the capacitance bridge (typically 1–100 kHz) and the heterodyne beat method (10⁵–10⁷ Hz). Both are far below the acetate-ester relaxation. Taking Debye τ ≈ 3.4 ps (MA) and 5.4 ps (EA), giving f_r ≈ 47 GHz and 30 GHz:

| Measurement frequency | f/f_r (MA) | Dispersion deficit as fraction of (ε_s − ε∞) |
|---|---|---:|
| 1 MHz | 2.1 × 10⁻⁵ | ~5 × 10⁻¹⁰ |
| 100 kHz | 2.1 × 10⁻⁶ | ~5 × 10⁻¹² |
| 10 kHz | 2.1 × 10⁻⁷ | ~5 × 10⁻¹⁴ |

For EA the deficits are ~2× larger and equally negligible. Converted to ε units, the worst case (1 MHz) is a bias of order 10⁻⁹ on ε ≈ 6. This is **eight orders of magnitude below** the 2% accuracy class. The systematic bias from measurement frequency is not merely small; it is irrelevant.

### The residual caveat

The defensible statement is: *NBS514's static value is comparable to a modern zero-frequency value for these molecules, because their relaxation is ~4 orders of magnitude above any plausible 1951 measurement frequency and NBS flagged no dispersion.* The indefensible statement would be: *NBS514 measured at 0 Hz.* It did not, and the project should not describe it that way. This matters for how the record is documented, not for whether the number is usable.

One genuine limitation: "static" in NBS514 means "low-frequency limit as judged in 1951", and the judgement was applied to the underlying primary references (refs 8, 63, 276 for EA; 63, 260 for MA), some of which are 19th-century. NBS evaluated their apparatus and methods (§2.4 says the accuracy class was assigned "after considerations of the investigators' apparatus and methods, precision, probable purity of materials, and comparisons, where possible, with the results of others") but the modern reader cannot audit that judgement without retrieving those primary papers. The 2% class is the honest bound.

**Verdict: frequency-comparable for both, with the semantics caveat above.**

---

## 8. Purity and impurity risk

The task asks specifically how much water would shift ε by 0.1. Answer: **a lot more than is plausible.**

| | Water needed for Δε = +0.10 (linear) | Water needed (Bruggeman) |
|---|---:|---:|
| EA | 0.138 vol% ≈ **1500 ppm mass** | 0.68 vol% ≈ 7500 ppm |
| MA | 0.139 vol% ≈ **1490 ppm mass** | 0.63 vol% ≈ 6700 ppm |

The lever is weak because ε only goes 6 → 80, a factor of ~13 rather than the ~10⁵ seen for ionic conductivity. Concretely:

| Water content | Δε (EA, linear) | Δε (EA, Bruggeman) |
|---|---:|---:|
| 100 ppm | +0.007 (+0.11%) | +0.001 |
| 500 ppm | +0.033 (+0.54%) | +0.007 |
| 1000 ppm | +0.066 (+1.09%) | +0.013 |
| 5000 ppm | +0.328 (+5.4%) | +0.066 |

So water becomes a threat only above roughly 1000–1500 ppm, which for a distilled 1951 ester is at or beyond the plausible worst case — and even then it stays near the 2% band.

**The more dangerous impurity is the hydrolysis co-product, not water.** Esters hydrolyse to the alcohol plus acid, and both alcohols are fully miscible and much more polar:

| Contaminant | Δε at 1000 ppm | at 5000 ppm | at 10000 ppm |
|---|---:|---:|---:|
| Ethanol in EA (ε 24.3) | +0.018 | +0.091 | +0.183 (3.0%) |
| Methanol in MA (ε 32.6) | +0.026 | +0.130 | +0.260 (3.9%) |

Note the direction: hydrolysis **raises** ε. So the historical failure mode for a 1951 ester measurement is a positive bias from alcohol/acid, not from water per se. 1% alcohol contamination alone would consume half the accuracy budget.

**Why I still judge contamination non-material here:** the values agree with modern literature to <1% at 25 °C and reproduce independent 20 °C values to <0.1% via NBS's own coefficient. A sample carrying ≥5000 ppm alcohol would be biased by 1.5–2% and would not land on the modern numbers. The Kirkwood–Fröhlich g ≈ 1 result (§4.3) independently rules out the associated/ionic signature that gross contamination produces. The agreement is the empirical bound; the g factor is the mechanistic one.

**Verdict: purity risk real but empirically bounded well inside the stated accuracy class, for both.**

---

## 9. Systematic concerns about using 1951 tabulated values

Four concerns, in descending order of how much they should affect downstream use.

### 9.1 The independence claim in `source_verification.csv` is circular — highest priority

`source_verification.csv` records `v04_epsilon = 6.02`, `nbs514_epsilon = 6.02`, `epsilon_agrees = true` for EA (and the same pattern for MA), and `evidence_backfill_report.md` §3 celebrates this as "数值与冻结 v04 值**逐字节一致**" and concludes "PLAN B 的假设成立".

But `data/dielectric_v04.csv` sources these rows from **the same document at the same record id**:

```
XEKOWRVHYACXOJ-UHFFFAOYSA-N, ... ,298.15,6.02, ... ,10.6028/nbs.circ.514, ... ,nbs514:p20:022,20,...
KXKVLQRXCPHEJC-UHFFFAOYSA-N, ... ,298.15,6.68, ... ,10.6028/nbs.circ.514, ... ,nbs514:p18:009,18,...
```

The v04 "frozen value" *is* the NBS514 transcription. Comparing them and reporting agreement is one transcription compared with itself. It is a useful **transcription-integrity** check (it proves the manual entry was not corrupted between layers, which is worth having) but it is **not corroboration**, and the report's framing overstates it.

Consequence: EA and MA each remain **single-source** (`n_source_documents = 1`), which is consistent with the gap register's own `SINGLE_SOURCE` / `NO_SOURCE` labels for C11 and C12 — but inconsistent with the report's "假设成立" narrative. Anyone reading §3 of that report as evidence of independent agreement is being misled.

### 9.2 EA and MA are not independent of each other

From the printed bibliography, both rows cite **ref 63 = J. W. Williams & I. J. Krchma, *J. Am. Chem. Soc.* **49**, 1676 (1927)** as an unbracketed (i.e. employed) reference. The reference sets are:

- MA: {63, 260}
- EA: {8, 63, 276}

So the two "new" condition-qualified measurements share a primary source. For B07's source-clustering work this means EA and MA cannot be counted as two independent observations of the acetate-ester trend. The report's §5 already warns that "独立来源数 is an upper bound" — this is a concrete instance of that warning, and it applies to the two records being added.

### 9.3 "Static" is a 1951 editorial judgement, and the primary literature is old

As in §7: NBS514 is a critical compilation, not a measurement. The underlying references here span 1899 (ref 8, K. F. Lowe) to 1947 (ref 276, Shidlovskaya & Syrkin). NBS's accuracy assignment accounts for apparatus and purity "where possible" but the modern user cannot audit that. The 3-figure → 2% class is the correct uncertainty to carry, and it is *four times worse* than the 0.5% class that the 4-figure entries (e.g. acetone 20.70, 1,4-dioxane 2.209) receive. Downstream models that treat all NBS514 entries as equally precise will be wrong by a factor of 4 on these two.

I verified from the PDF span geometry that the final digit in each is full-size, not subscript — `6.68` at size 7.2 and `6.02` at size 7.9, versus the smaller-type pattern NBS uses for non-significant trailing figures (e.g. `20.7₀` at 7.2 with a 6.0 subscript, `5.3₀` at 7.8). So 3 significant figures is the correct reading and class (b) is the correct band. This is a point in the transcription's favour.

### 9.4 Age-related selection effects

A 1951 compilation reflects what was measured by 1951, with 1951 purification standards. Two specific mechanisms:

- **Survivorship toward "nice" values.** Compilers choosing among conflicting old measurements can unconsciously favour round or concordant numbers. Not detectable from the document alone; the <1% agreement with modern data is reassuring but modern tabulations may themselves descend from the same primary references, so the agreement is weaker evidence than it appears.
- **Purity optimism.** Reagent-grade 1951 esters were typically 95–99% with water and alcohol as the main impurities. As §8 shows, the bias direction is upward and the magnitude is within the stated 2% band for reasonable purity, but not negligible for poor purity.

Neither is grounds for HOLD on chemistry. Both argue for carrying the 2% class explicitly rather than treating 6.02 and 6.68 as exact.

### 9.5 One presentation defect worth noting

`evidence_backfill_report.md` §1 and §三 count EA and MA among "已有可用条件级证据：**5**（DMC, DEC, SL, EA, MA）", while `A18_gap_register.csv` still labels C11/C12 with `repo_backfill_tier = P4_SOURCE_RETRIEVAL` and `blockers = ZERO_OBSERVATIONS`. The register's `ZERO_OBSERVATIONS` label is itself imprecise — the build script's own comment (lines 132–136) says the intended label when a curated v04 value exists is `ZERO_THERMOML_OBSERVATIONS` plus `CURATED_VALUE_NOT_IN_OBSERVATION_LAYER`, yet the emitted CSV shows the bare `ZERO_OBSERVATIONS` and `n_observations = 0` even though v04 carries `n_observations = 1` for both rows. This is a register/bookkeeping inconsistency, not a chemistry finding, but it means the gap register currently understates what is known about C11 and C12 and should not be used as-is to argue they are uncovered.

---

## 10. What I did not do, and limits of this review

- I did not retrieve the primary references (Lowe 1899, Williams & Krchma 1927, Phadke et al. 1945, Shidlovskaya & Syrkin 1948). The 2% class is therefore inherited from NBS, not independently audited.
- I did not verify the transcription of any NBS514 row other than the two under review, plus the propyl and butyl acetate rows used for the series check.
- I did not adjudicate source independence or admission policy. §9.1–9.2 are findings handed to whoever owns that question; they are not part of my PASS/FAIL basis.
- My Kirkwood–Fröhlich check uses gas-phase dipole moments and 25 °C densities from standard tables; it is a consistency test at the ~5% level, not a precision determination.
- I did not assess whether NBS514 is the *best available* source for these two molecules. Modern primary measurements certainly exist; this review only asks whether the 1951 values are sound.
- No existing file was modified. Scratch scripts `_tmp_r1_*.py` in the evidence_backfill directory are disposable and may be deleted.

---

## 11. Bottom line

Both records pass on chemistry and experimental conditions. ε = 6.02 (EA) and 6.68 (MA) at 298.15 K are plausible, mutually consistent, correctly ordered for the acetate homologous series, correctly phased as liquids, anchored on a real measured temperature requiring no harmonisation, and frequency-classified as static in a sense that is quantitatively indistinguishable from zero-frequency for molecules relaxing at ~30–47 GHz. Contamination cannot plausibly explain them.

The two records do **not**, however, constitute two independent pieces of evidence, and the report's agreement claim is circular. That is a provenance matter, and it is the finding from this review that most changes what the parent should do next.
