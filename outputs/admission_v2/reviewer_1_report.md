# Reviewer 1 Report — Chemistry, Physics and Experimental-Condition Soundness

**Project:** electrolyte-solvent-dielectric-ml · **Work package:** B02
**Scope:** Is each candidate record a chemically and physically plausible **static relative permittivity (εr) measurement of a PURE LIQUID**, with internally consistent stated conditions?
**Queue reviewed:** `outputs/admission_v2/admission_review_queue.csv` (70 rows, 62 distinct measurements)
**Queue SHA-256 (final, as verified):** `02be88c78bade79f8a1937cc4ac916e9f9cd70314bd51b01ec99c6fb9e8148b6` (38 845 bytes, `generated_at_utc` 2026-11-23T04:20:39Z)
**Decisions written to:** `outputs/admission_v2/reviewer_1_decisions.csv`
**Files modified:** none (read-only audit; only the two output files were created)

> **Provenance note.** I began analysis on queue hash `1b701aaa…2cdbab` (34 440 bytes) and the queue was regenerated to `02be88c7…8148b6` (38 845 bytes) mid-review. I re-validated the complete decision set against the new bytes: `queue_id` and `measurement_id` sequences match **exactly** in order (70/70), all 30 columns and every value distribution are unchanged, and each decision's embedded T/ε matches the current queue. The regeneration changed byte-level CSV quoting only, not content. All findings below hold on the final hash.

---

## 1. Methodology

I did not accept the pre-computed `machine_audit_status` / `j03_verdict` / `j04_*` columns at face value. Instead I went **upstream to the primary ThermoML XML** and re-derived every condition myself.

1. **Identity resolution.** All 62 queue InChIKeys were resolved to name + SMILES from the in-repo `data/dielectric_v04.csv` and `data/processed/dielectric_observations_v11.csv`. No key was unresolvable, so criterion 1 could be evaluated for all 70 rows.
2. **Primary-source reconstruction.** I wrote an independent ThermoML parser (`nPureOrMixtureData` → component `RegNum` → `Compound` name/formula, plus `Variable`/`Constraint`/`Property`/`NumValues`) and parsed the raw XML in `data/raw/thermoml/` directly. This mattered: **many source files are multi-compound mixture studies**, so "the file contains the molecule" is not evidence that "the record is the pure component". I matched each queue row to its `ncomp == 1` pod and confirmed the pod's `RegNum` compound is the assigned chemical.
3. **Condition audit.** For each matched record I extracted the actual `ePhase`, `ePropPhase`, pressure `Constraint`, method, and expanded uncertainty. I then compared these against the queue's `phase`, `pressure_kpa`, and `frequency_mhz` fields.
4. **Frequency semantics.** I checked the true property name in the source. ThermoML distinguishes `Relative permittivity at zero frequency` (261 records repo-wide) from `Relative permittivity at various frequencies` (277 records), and a genuine frequency axis appears as a `Frequency, MHz` variable or constraint. This is the documentary support the protocol requires before a `frequency_mhz = 0` label may be treated as a measured static value.
5. **Phase consistency.** I pulled experimental melting and boiling points from `data/external/g1plus/pubchem/liquid_window/liquid_window_values.csv` (945 mp + 1031 bp entries) and tested each T against the substance's liquid window.
6. **ε-plausibility.** I checked each value against chemical-class bands **and** against the molecule's own measured ε(T) series in the v11 ledger — the stronger test, because an internal inconsistency is provable without external literature.
7. **Composite detection.** For rows with `n_contributing_sources > 1`, I located which underlying observation actually *holds* the reported ε. A reported (T, ε) pair with no single observation holding both coordinates is a spliced pair, not a measurement.

**Decision rule applied strictly as instructed:** PASS only with positive documentary grounds; chemically plausible but not confirmable as a real measurement ⇒ HOLD; an irreconcilable contradiction ⇒ FAIL. A bare `frequency_mhz = 0` was never accepted as a measured static value without source support.

---

## 2. Counts

| Decision | n | Evidence grade |
|---|---|---|
| **PASS** | **31** | DOCUMENTED 31 |
| **HOLD** | **29** | INFERRED 20 · INSUFFICIENT 9 |
| **FAIL** | **10** | DOCUMENTED 10 |
| **Total** | **70** | DOCUMENTED 41 · INFERRED 20 · INSUFFICIENT 9 |

By track:

| Track | n | PASS | HOLD | FAIL |
|---|---|---|---|---|
| `R007_WORKSHEET_40ROW` | 40 | 31 | 9 | 0 |
| `COMPOSITE_CONDITION_UNMATCHED_22` | 22 | 0 | 14 | 8 |
| `P0_P1_NAMED_MOLECULE` | 4 | 0 | 3 | 1 |
| `J02A_REQUIRES_HUMAN_REVIEW_4` | 4 | 0 | 3 | 1 |

All 31 PASS records are R007 worksheet rows verified pure single-component ThermoML records with an explicit `at zero frequency` property name, a low-frequency capacitance method, `ePhase = Liquid`, `ePropPhase = Liquid`, and an explicit near-ambient pressure constraint. The 9 R007 HOLDs are the NBS Circular 514 manual page reads, which have no phase/pressure/frequency and zero measurement-ledger provenance.

---

## 3. Most serious problems found

### Finding A — Systematic high-pressure contamination of ambient ε values (4 measurements; the most serious)

`10.1021/je060248p` is **not** an ambient-pressure dielectric study. It is a **pressure-dependence study** at fixed T = 298.15 K, sweeping **0.1 MPa → 300 MPa**, and it contributes **54 rows** to the v11 ledger. The aggregation treated those 54 rows as independent ambient observations at a single temperature.

Because the ε values rise monotonically with pressure at fixed T, the median of a mixed set silently lands at an **intermediate pressure**, and the queue then presents that number with a **blank `pressure_kpa`**:

| measurement_id | molecule | reported ε | ambient ε | inferred pressure | error |
|---|---|---|---|---|---|
| `EPSV04-R040` | octan-1-ol | 10.66 | 9.85–10.01 | ≈75 MPa | **+6.5 %** |
| `EPSV04-R046` | butan-1-ol | 18.03 | 17.49–17.58 | ≈50 MPa | **+2.6 %** |
| `EPSV04-R097` | hexan-1-ol | 14.26 | 13.06 | ≈75–100 MPa | **+9.2 %** |

`EPSV04-R040` is the cleanest proof: its ε = 10.66 is *exactly* the median of `{9.85 (101.3 kPa), 10.01 (100 kPa), 10.48 (50 MPa), 10.84 (100 MPa), 11.13 (150 MPa), 11.39 (200 MPa)}`. The median of a monotonic pressure series is a pressure, not a permittivity. `EPSV04-R097` fails identically with the 8-value hexan-1-ol set.

`EPSV04-R091` (toluene) is the same defect in milder form: ε = 2.40445 comes from the 290.63/290.65 K **100 kPa** rows while the reported T = 297.385 K corresponds to a 6.9–41.9 MPa cluster.

**This is not a rounding issue — it is a condition-attribution error that shifts ε by up to 9 %**, larger than most of the model's error budget, and it biases exactly the alcohols that are most relevant to electrolyte formulation.

### Finding B — Temperature/ε splicing: the reported pair exists in no source observation (5 measurements)

The R219 aggregation rule takes T as the *median temperature* and ε as the *median value* of a band **independently**. When the temperature distribution is skewed this produces a pair that no instrument ever recorded:

- **`EPSV04-R057`** (methanol): ε = 33.6 is held **only** at 293.15 K; the stated T is 298.15 K, where the source itself reports 32.6. Error ≈ **3 %**.
- **`EPSV04-R044`** (ethanol): ε = 25.02 is held **only** at 293.15 K, stated T = 298.15 K. Ambient 298.15 K is 24.35–24.37.
- **`EPSV04-R003`** (pentan-1-ol): ε = 15.736 is held **only** at 293.15 K, stated T = 298.15 K where the source reports 15.144. The source's own dε/dT = −0.116 K⁻¹ makes the error **+3.9 %**.
- **`EPSV04-R091`** (toluene): ~7 K of misattribution (see Finding A).
- **`EPSV04-R086`** (γ-butyrolactone): **neither coordinate is a measurement.** T = 295.65 K does not exist in the ledger at all, and ε = 41.99 is held by no observation — it is the interpolation between 42.34 (293.15 K) and 41.64 (298.15 K).

`EPSV04-R086` carries an additional decisive contradiction, re-confirmed against the final queue bytes: **the same `measurement_id` appears twice in the frozen queue with two different temperatures** — `Q-PRI-EPSV04-R086` and `Q-CCU-EPSV04-R086` both state T = 295.65 K, while `Q-J02A-EPSV04-R086` states T = 293.15 K, all three with ε = 41.99. At 293.15 K the measured values are 42.34 and 42.81, so **none** of the frozen rows is consistent with its own source, and the frozen queue is internally inconsistent about a single measurement's temperature. This alone invalidates the freeze for that measurement.

### Finding C — 9 of 40 R007 rows rest on a 1951 secondary compilation with no conditions at all (HOLD)

`EPSV04-R115, R144, R147, R156, R171, R173, R195, R203, R206` are all sourced from **NBS Circular 514 (1951)**, DOI `10.6028/nbs.circ.514`, as manual page reads. Every one has `n_contributing_sources = 0`, no measurement-ledger entry, `j03 = PROVENANCE_INCOMPLETE`, and `gate_failures = A7` with A2/A5/A6/A9/A11 unresolved. Critically for my scope: **`frequency_mhz` is blank, `phase` is blank, and `pressure_kpa` is blank** — so *none* of the six conditions can be evaluated from documentary evidence. Several also carry a phase problem: the published melting range of o-cresol is 302.95–304.26 K against a stated T = 298.15 K, so `EPSV04-R144` asserts a Liquid phase **below the melting point** with no supercooling statement.

### Additional finding — supercooled-liquid records that PASS only because the source declares it

Three PASS records have T at or below the published melting point and are chemically defensible **only** because the source explicitly declares `ePhase = Liquid` (supercooled):

- **`EPSV04-R028`** sulfolane, T = 298.15 K, mp = 299.26–300.95 K (T is **below** mp)
- **`EPSV04-R048`** diisopropanolamine, T = 303.15 K, mp = 315.15 K (T is **below** mp)
- **`EPSV04-R013`** 2-amino-2-methylpropan-1-ol, T = 303.15 K, mp = 304.15–305.15 K (marginal)
- **`EPSV04-R026`** cyclohexanol, T = 298.15 K, mp = 295.93–299.08 K (T is **inside** the mp range)

I passed these because the ε values match the accepted liquid-phase values and the sources declare the liquid phase, but the *phase* is metastable, not thermodynamic. If the project requires equilibrium liquids, these four should be re-examined.

---

## 4. Systematic issues the other three reviewers must also consider

1. **The aggregation rule manufactures non-measurements, and no single-reviewer scope catches it.** 20 of 29 HOLDs are composites where the reported ε is a median (`R007`, `R036`, `R064`, `R085`, `R089`, `R099`), a midpoint of two temperatures (`R016`, `R033`, `R041`, `R080`, `R083`, `R084`), or a value borrowed from a different temperature (`R031`, `R095`). Each is *individually* physically sensible — I verified every one against the molecule's own ε(T) series — which is exactly why a chemistry-only review would wave them through. They fail the "is this a measurement" test, not the "is this plausible" test. **A provenance reviewer must decide whether a median of ≥2 sources counts as a measurement at all; my chemistry scope cannot settle it.**

2. **`pressure_kpa` is blank for 39 of 70 rows, including every composite.** This is not cosmetic: for the alcohol rows the missing pressure *is* the defect (Finding A). Any reviewer who treats a blank pressure as "ambient by default" will pass 3 rows that are provably wrong by 2.6–9.2 %. **Blank pressure must be read as UNKNOWN, never as 101.325 kPa.**

3. **`frequency_mhz = 0` is defensible for the 31 ThermoML rows but must not be generalised.** Those 31 carry the literal source property name `Relative permittivity at zero frequency` plus a capacitance/LCR method — genuine documentary support. The 9 NBS rows carry a blank field with no support. But note the repo-wide hazard: **277 of 538 permittivity records are `Relative permittivity at various frequencies`**, and 9 source files contain a real `Frequency, MHz` axis. Two of those files are in this queue's provenance (`10.1016/j.jct.2008.09.006`, `10.1016/j.fluid.2016.10.026`). I verified their queue rows resolve to the pure `at zero frequency` pods, so they are clean — but the `0` label is doing **no discriminating work** and would silently absorb a frequency-dependent record. **Do not treat `frequency_mhz = 0` as evidence of anything.**

4. **`10.1021/je9010773` (DMSO, 78 rows) is also a pressure-dependence study** — its rows span 91–5093 kPa at six near-constant temperatures. It contaminates `EPSV04-R031`/`R031`/`R031` (the four-source DMSO composite). I graded that HOLD rather than FAIL because the 0.14 K offset is negligible, but the ambient condition is not documented.

5. **`10.1021/je060248p` and `10.1021/je9010773` should probably be excluded from ambient-ε use entirely, or used only with an explicit pressure filter.** This is a data-layer decision beyond my scope but it affects the other reviewers' verdicts.

6. **Multi-compound source files are a live identity trap.** Files such as `10.1016__j.jct.2011.07.021` (2-ethyl-1-hexanol + 1,2-butanediol + 1,4-dioxane), `10.1021__je600515j` (7 compounds incl. water), and `10.1016__j.jct.2008.02.015` (triglyme + DMC + DEC) contain the target molecule **plus mixtures of it**. A verifier that matches on "molecule appears in file" rather than "molecule is the sole component of this pod" will silently admit mixture data. My parser enforced `ncomp == 1`; **the other reviewers should confirm their verification does the same.**

7. **Water (`EPSV04-R083`) is outside the intended scope.** ε = 78.87 at 297.575 K is physically correct, but water is not an organic electrolyte solvent and the record is a midpoint interpolation across 8 sources. I held it on measurement grounds; **a scope reviewer should also ask whether it belongs in the roster at all.**

---

## 5. Verdict summary for the consensus record

- **31 PASS** — pure, single-component, liquid, ambient-pressure ThermoML static-ε measurements with documented `at zero frequency` semantics. Recommended for admission subject to the other three reviewers.
- **29 HOLD** — 9 NBS page reads with no evaluable conditions (INSUFFICIENT) and 20 composites whose ε is a derived statistic rather than an observation (INFERRED). None is chemically implausible; none is confirmable as a measurement.
- **10 FAIL** — 3 pressure-contaminated (`R040`, `R046`, `R097`), 4 temperature-spliced (`R003`, `R044`, `R057`, `R091`), 1 doubly-computed with a frozen-queue self-contradiction (`R086`, appearing in 3 tracks). These are irreconcilable contradictions, not doubts.

Under the frozen 4/4 consensus rule, **any single HOLD or FAIL blocks the record**; on my scope alone, 39 of 70 queue rows (31 distinct measurements) are blocked.
