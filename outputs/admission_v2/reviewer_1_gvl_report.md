# Reviewer 1 — Chemistry / Physics / Experimental Conditions

**Work package:** B02-CONFLICT · **Scope:** gamma-valerolactone dual-row dielectric conflict
**Compound:** γ-valerolactone (γ-pentanolactone, 5-methyloxolan-2-one), CAS 108-29-2, `GAEKPEKOJKCEMS-UHFFFAOYSA-N`
**Rows adjudicated:** `EPSV04-R227` (ε = 36.1, 10.1016/j.isci.2026.115778) and `EPSV04-R248` (ε = 36.9, 10.1016/j.ica.2021.120372)
**Date:** 2026-11-23 · **Verdict:** both `HOLD` / `INFERRED` / `RETAIN_PARALLEL`

---

## 0. Summary of the recommendation

| queue_id | measurement_id | ε | decision | evidence_grade | recommended_resolution |
|---|---:|---:|---|---|---|
| Q-CONF-EPSV04-R227 | EPSV04-R227 | 36.1 | **HOLD** | INFERRED | **RETAIN_PARALLEL** |
| Q-CONF-EPSV04-R248 | EPSV04-R248 | 36.9 | **HOLD** | INFERRED | **RETAIN_PARALLEL** |

**Which ε do I believe?** Neither is *wrong*, and neither can be certified at 298.15 K. On
chemistry alone **36.9 has a slight edge** (it is the number an independent curated index
reproduces, and it sits nearer the centre of the lactone-homology band), but the decisive
finding is that **the 2.2 % gap is smaller than the reproducibility of the measurement
method itself**, so the pair is a single physical quantity sampled twice within its own
noise — not a real disagreement to be resolved by picking a winner. **Both must be retained
in parallel; neither may be promoted to primary and neither may be averaged.**

---

## 1. Is γ-valerolactone a liquid at 298.15 K? — **Yes, unambiguously**

| Property | Value | Source |
|---|---|---|
| Melting point | **−31 °C = 242.15 K** (−24 °F, NTP 1992) | PubChem CID 7921, experimental properties |
| Boiling point | **207–208 °C = 480–481 K** @ 760 mmHg | PubChem CID 7921, experimental properties |
| Density (25 °C) | 1.047–1.054 g/cm³; 1.057 at 68 °F | PubChem CID 7921; repo `density_v01.csv` gives 1049.28 kg/m³ at 298.15 K |
| Vapour pressure | 0.5 mmHg @ 84 °F (29 °C) | PubChem CID 7921 |

The liquid window at 298.15 K is **~236 K wide** (242 K → 480 K), and the sample sits
**56 K above the melting point** and **182 K below the boiling point**. Vapour pressure at
298 K is only a few mmHg, so the sample is not boiling or evaporating appreciably.

**Conclusion: the phase assignment (`liquid`) is physical.** No liquid-window gate should
fire on this compound, and the failure mode that catches ethylene carbonate (a 25 °C value
recorded for a solid that melts at 36 °C — see `reports/reaxys_core_four_crosscheck.md`
Lesson B) **cannot** apply here. Both rows pass the phase test.

---

## 2. Is 36.1 or 36.9 the more plausible static dielectric constant?

### 2.1 What the lactone family actually measures

The most useful anchor is **γ-butyrolactone (GBL)**, the C4 homologue, because the repository
holds a genuine primary ThermoML series for it with stated uncertainties:
`data/raw/thermoml/10.1021__je900503p-c4927a582b2b.xml`, method **Dekameter**, property
`Relative permittivity at zero frequency`, expanded uncertainty **U = 0.06 (95 %)**:

| T (K) | ε(GBL) | U (95 %) |
|---:|---:|---:|
| 293.15 | 42.34 | 0.06 |
| 293.15 | 42.81 | 0.06 |
| 298.15 | **41.64** | 0.06 |
| 303.15 | 41.10 | 0.06 |
| 313.15 | 39.92 | 0.06 |

Two facts fall straight out of this table, and both matter more than the 36.1-vs-36.9
question itself:

- **dε/dT = −0.129 K⁻¹** (linear fit, 293–313 K); locally −0.108 K⁻¹ over 298–303 K.
- **The two replicate measurements at one single temperature differ by 0.47 (1.10 %)** —
  which is **~8× the stated U = 0.06**. The claimed uncertainty of this measurement is
  optimistic by roughly an order of magnitude.

### 2.2 Homology / Kirkwood–Fröhlich estimate for GVL

GVL is GBL with one extra CH₂ on the ring; the ring stays a five-membered γ-lactone. Using
the repository's own xTB dipole moments (`data/processed/dielectric_physical_features_v03.csv`:
μ_GBL = 4.936 D, μ_GVL = 5.038 D) and the measured molar volumes (GBL 76.6, GVL 95.4 cm³/mol,
so the GVL number density is **0.80×** GBL):

| g_GVL / g_GBL | predicted ε(GVL, 298.15 K) |
|---:|---:|
| 0.85 | 29.8 |
| 0.90 | 31.5 |
| 0.95 | 33.2 |
| **1.00** | **34.9** |
| 1.05 | 36.5 |
| 1.10 | 38.2 |

The dilution from the extra CH₂ (−20 % in number density) is nearly cancelled by GVL's
larger dipole (+2 %), so **the whole plausible band is roughly 31–38**. Both 36.1 and 36.9
sit inside it. The Kirkwood correlation factor g is the free parameter and the literature
does not pin it down for GVL, so **chemistry cannot discriminate 36.1 from 36.9.** Any claim
that one of them is "the chemically correct value" over the other would be over-reading the
evidence.

Note also that the naive comparison "GBL ≈ 39, so GVL should be ≈ 36" is **not** safe: the
39.1 figure that circulates for GBL is **6.1 % below** the primary 41.64 at the same
temperature. The secondary literature on this family is already scattered by several
percent, which sets the realistic resolution of the whole exercise.

### 2.3 The 32 / 34 legs, which change the picture

Two further numbers exist for GVL and are **not** in this conflict pair:

- **32 at 25 °C** — Perricone 2011 PhD thesis, Tableau 8, relayed from ref [87]
  (`reports/g1plus_perricone_thesis_crosscheck.md`).
- **34** — also reported in that thesis (`reports/decisions_log.md`, v0.3.6 entry).

32 is **11.4 % below** 36.1. That gap cannot be explained by temperature (it would need
~32 K of offset) and cannot be explained by rounding. It is a genuine literature
disagreement, and it means the **true spread of GVL's reported static permittivity is
32 → 36.9**, roughly 15 %. Against that background, a 2.2 % difference between 36.1 and 36.9
is a rounding-level disagreement, not a conflict of physical substance.

**Verdict on question 2: 36.9 is marginally more plausible** — it is the value the live
Reaxys index reproduces (`probes/reaxys_core_four_crosscheck.csv`: the *only* dielectric row
in the entire GVL substance record, location `supporting information`, Segato et al. 2021),
and it lies nearer the centre of the homology band. But the edge is **weak**, not decisive,
and it is not strong enough to justify discarding 36.1.

---

## 3. Is 2.2 % within normal inter-laboratory reproducibility?

**The question is misframed, and that is the key finding.** The relevant yardstick is not
inter-laboratory reproducibility of *dielectric measurements in general* but the reproducibility
documented for *this exact quantity in this exact compound family*:

| Comparator | Spread | Relative |
|---|---:|---:|
| GBL replicates at 293.15 K, same file, same method | 42.34 vs 42.81 | **1.10 %** |
| GBL stated expanded uncertainty U (95 %) | ±0.06 on 41.6 | 0.14 % |
| Reproducibility implied by the replicates vs stated U | 0.47 vs 0.06 | **8×** |
| GBL primary 41.64 vs commonly quoted 39.1 | 2.54 | **6.1 %** |
| GVL 36.1 vs thesis 32 | 4.1 | **11.4 %** |
| **GVL 36.1 vs 36.9 (this conflict)** | **0.80** | **2.22 %** |
| Project relative tolerance for "conflict" | — | 2.00 % |

The 2.2 % gap is **1.11× the project's 2.00 % conflict threshold** — it trips the threshold
by a hair. But it is **half** the spread the same lab reports between two replicates, **a
third** of the spread between primary and secondary GBL values, and **a fifth** of the spread
already present in the GVL literature (32 → 36.9).

**Interpretation.** A 2.2 % gap is **consistent with ordinary measurement and transcription
noise** for static permittivity of a polar aprotic liquid. It does **not** require, and does
not even suggest, a transcription error or a different physical quantity. Specifically:

- **Not a transcription error.** A digit slip would be expected to produce a larger,
  more structured error (e.g. 63.1, 36.9↔39.6), not two clean two-significant-figure values
  0.8 apart.
- **Not a finite-frequency artefact.** The primary GBL comparator was measured at
  `Relative permittivity at zero frequency`; both GVL legs are low-frequency/static claims.
  A frequency effect in the 10–100 kHz range would be far smaller than 2.2 % for a liquid
  with no significant low-frequency relaxation, and neither source reports a frequency.
- **The threshold itself is the thing that is too tight**, not the data that is too noisy.
  A 2 % relative tolerance is finer than the documented reproducibility of the reference
  measurement (1.1 % between replicates, with a claimed U of 0.14 % that is 8× too
  optimistic).

---

## 4. Could both be correct? — **Yes, on at least three independent mechanisms**

### 4.1 Temperature (the strongest mechanism)

With the measured homologue slope dε/dT = −0.129 K⁻¹, a gap of 0.80 corresponds to only
**6.2 K** (7.4 K at the local −0.108 K⁻¹ slope):

```
ε(291.9 K) = 36.1 + (−0.129)(291.9 − 298.15) = 36.90   ← exactly the R248 value
```

Equivalently: **36.9 measured at 18.8 °C and 36.1 measured at 25 °C lie on the same curve.**
A plain **25 °C vs 20 °C** labelling difference (5 K) reproduces **81 %** of the gap on its own.

This mechanism is not hypothetical here, because **neither leg actually reports a temperature**:

| Row | T_K in dataset | `temperature_source` | What the source says |
|---|---:|---|---|
| R227 (36.1) | 298.15 | `review_table_standard_room_temperature` | review table, **no stated temperature** |
| R248 (36.9) | 298.15 | `not_reported` | SI table **"has no temperature column at all"** |

So the premise of the conflict — "same temperature 298.15 K" — **is manufactured by the
ingest, not asserted by either document.** The 298.15 K is a standard-room-temperature
*convention* applied to two sources that are silent on temperature. A conflict register
cannot legitimately treat two *assumed* temperatures as a matched condition pair, and the
pipeline is right to set `condition_pair_valid = false` on both.

### 4.2 Water content (purity)

GVL is hygroscopic-adjacent and water has ε = 78.2. A linear volume-fraction bound gives:

```
1.9 vol% ≈ 1.8 wt% H₂O  →  +0.8 in ε
```

So a sample carrying ~1.8 wt % water reads **0.8 high** — i.e. **toward 36.9, not toward
36.1**. Water uptake is therefore a plausible one-directional explanation, and it means the
*lower* value is the one closer to a dry sample. Neither source states a purity or water
content, so this cannot be checked, but it is physically sufficient.

### 4.3 Sample history / method

Dekameter bridge measurements (GBL) and whatever the Segato SI used are different instruments
with different calibration lineages; the 8× underestimate of uncertainty in the GBL file shows
this family is not measured to better than ~1 %.

**Answer: both can be correct simultaneously.** The pair is not mutually exclusive.

---

## 5. Should the rows be averaged, chosen, kept parallel, or rejected?

### Rejected options

- **AVERAGE_JUSTIFIED — no.** Averaging is forbidden by project rule unless justified, and
  here it would be *actively harmful*: the two values are **not independent replications**
  (one is a review-table transcription, the other a single SI number from a different paper),
  neither has a reported temperature, and neither has any contributing observation in the
  ledger. Averaging two untraceable, non-independent, temperature-unknown values produces a
  number with **no provenance at all** — the worst possible outcome for a dataset whose whole
  value proposition is provenance. There is no justification available.
- **Choose one as primary — no.** Promoting 36.9 would silently assert a 298.15 K temperature
  the source does not state, and would bury the unresolved 32/34 legs; promoting 36.1 would
  pick the weaker-sourced leg against the source-quality rule. Both moves manufacture
  certainty that the evidence does not support.
- **Reject both — no.** Both are physically sound, in the right band, for a compound that is
  unambiguously liquid at 298 K. Discarding them would throw away real information about a
  solvent the project cares about, and would leave the compound with no dielectric value at all.

### Recommended: **RETAIN_PARALLEL**, both at `HOLD` / `INFERRED`

Both rows stay in the record side by side, flagged unresolved, `model_ready = false`, and
**excluded from any model-fitting or consensus aggregate** until a temperature-resolved
primary measurement is read. This is the only disposition that is simultaneously honest about
the physics (the gap is within method noise), honest about the provenance (neither leg is
traceable to a measurement), and compliant with the no-averaging / no-picking rule.

**Concrete unblocking step** (identical for both rows): obtain the Segato et al. 2021
*Inorg. Chim. Acta* 522, 120372 supporting information directly and read the solvent table's
**temperature and frequency columns**; and read Sun et al. 2026 *iScience* 29, 115778 Table 3
to see whether it cites a temperature at all. If the SI turns out to state 20 °C or to be a
non-static frequency, the conflict dissolves with no numerical change. A tie-breaker would be
the Landolt–Börnstein chapter titled *"Static dielectric constant of γ-valerolactone"*
(Wohlfarth, in *Static Dielectric Constants of Pure Liquids and Binary Liquid Mixtures*,
Vol. IV/17 supplement), which is the natural critical-compilation authority for this quantity
and was not reachable from this session.

### Why HOLD and not PASS or FAIL

- **Not PASS:** zero contributing observations (ledger search for `GAEKPEKOJKCEMS-UHFFFAOYSA-N`
  returns **0 rows**), `condition_pair_valid = false`, `NO_BAND_OBSERVATIONS_FOUND`, and the
  298.15 K is an assumption over a silent source. The provenance gate is correctly failing.
- **Not FAIL:** the values are physically sound, in the right band, for a liquid compound, and
  both come from identifiable citable documents. There is no physics reason to reject either.

### Why `INFERRED` and not `DOCUMENTED`

The chemistry/physics case (phase, magnitude, homology, temperature sensitivity) is established
by **inference from primary data on the homologue plus computed molecular properties**, not by a
documented measurement of GVL itself. No primary GVL dielectric measurement with a stated
temperature and uncertainty was located. `INSUFFICIENT` would understate what *is* known — the
compound's phase and value band are firmly settled — so `INFERRED` is the accurate grade.

---

## 6. Observations on the pipeline (not requested, but material)

1. **`condition_pair_valid = false` is correct and should not be "fixed."** The ingest
   assigned 298.15 K to two documents that never state a temperature. The right repair is to
   record `temperature_source = not_reported` (as R248 already does) and to *stop* presenting
   the pair as same-temperature, rather than to invent a temperature for R227.
2. **R227 carries `model_ready = true` in `dielectric_v04.csv`** despite being the weaker leg,
   while R248 is `false`. The provenance note already flags this as a pre-existing protected
   field awaiting a v0.5 decision. This adjudication recommends that v0.5 set **both** to
   `false` — a model-ready row whose temperature is a review-table convention and whose value
   is one of four circulating numbers is not model-ready.
3. **The 2.00 % conflict tolerance is finer than the reference measurement's reproducibility**
   (1.10 % between replicates; 6.1 % between primary and secondary GBL). Consider widening the
   relative-ε tolerance to ~5 %, which would still catch real conflicts (the 11.4 % GVL/32 leg,
   the 31 % and 28 % spreads in `MCONF-LCGLNKUTAGEVQW`) while no longer flagging method noise.
4. **The `b01` conflict register records `in_review_queue = false`** for
   `CONF-GAEKPEKOJKCEMS-298.1` while `admission_review_queue.csv` clearly contains both rows
   as `Q-CONF-EPSV04-R227/R248`. That is an inconsistency between artifacts worth a separate
   look.

---

## 7. Limitations of this review

- I did **not** read the Segato 2021 SI or the Sun 2026 Table 3 directly; both were blocked
  (publisher 403 / reCAPTCHA). Their temperature and frequency status is therefore inferred
  from the project's own audit notes (`reports/reaxys_core_four_crosscheck.md` §3.3:
  "the table has **no temperature column at all**"), not from the documents.
- The Kirkwood–Fröhlich estimate uses a **free** correlation factor g; the band 31–38 reflects
  that freedom and is not a prediction with an uncertainty.
- The GBL anchor is a single primary source (one paper, one method, one lab). Its own
  replicates disagree by 1.1 %, which is exactly why I treat the family's reproducibility as
  ~1 % rather than the claimed 0.14 %.
- No primary GVL dielectric measurement with stated T and U was found; the Landolt–Börnstein
  critical compilation would be the authoritative tie-breaker and was unreachable.
- I did not inspect the other three reviewers' conclusions and did not speculate about them.

---

## 8. Files

- `outputs/admission_v2/reviewer_1_gvl_decisions.csv` — 2 decision rows
- `outputs/admission_v2/reviewer_1_gvl_report.md` — this report

No existing file was modified.
