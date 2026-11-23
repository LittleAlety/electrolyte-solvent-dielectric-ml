# Reviewer 1 — Chemistry, Physics and Experimental-Condition Soundness

**Work package:** B04-PRECONFLICT · **Scope:** two observation-layer conflicts blocking B04
**Verdict:** `MCONF-BTANRVKWQNVYAZ-298` → **PASS** (resolved, 16.6 stands) · `MCONF-FXHOOIRPVKKKFG-303.15` → **HOLD** (37.72 stands, conflict not closed)

Neither molecule should be removed from the model-ready set. Both conflicts are *physically* explicable, but only the butan-2-ol one is *evidentially* closed.

---

## 0. Correction to the brief's premise (important)

The task brief states dε/dT for alcohols ≈ −0.2 to −0.3 %/K. **That is too small by roughly a factor of four.** Fitting the project's own high-precision butan-2-ol series (`10.1021/je3007666`, U = 0.06 at every point) gives:

| interval (K) | Δε/ΔT (K⁻¹) | relative (%/K) |
|---|---:|---:|
| 288.15 → 293.15 | −0.1920 | −1.040 |
| 293.15 → 298.15 | −0.1820 | −1.039 |
| 298.15 → 303.15 | −0.1700 | −1.024 |
| 303.15 → 308.15 | −0.1620 | −1.029 |

Mean **−0.1765 K⁻¹ = −1.06 %/K**. This inverts one of the brief's own hypotheses: a 6.15% spread needs only **5.78 K** of temperature error, not 20–30 K. A nominally "room temperature" measurement actually taken at 293 K reproduces the outlier *exactly* (17.51 at 293.15 K vs 17.60 reported). So temperature mislabelling is a **live** explanation for butan-2-ol, not an excluded one — and it is far cheaper than the water hypothesis (which needs 1.95 wt% contamination against a 0.5% purity spec).

The same correction matters for DMAc: its measured slope near 303 K is **−0.55 %/K**, so the 2.52% spread corresponds to 4.60 K.

---

## 1. The register's `n_distinct_sources` is counting DOIs, not experiments

Both conflicts are inflated by double-counting. This is the single most consequential structural fact, and it is documented, not inferred.

**Butan-2-ol** — `10.1021/je3007666` (Klimaszewski, Boruń, Bald & Sengwa 2012) and `10.1021/je800593p` (Chmielewska, Zurada, Klimaszewski & Bald 2009) are the **same Łódź laboratory** (K. Klimaszewski / A. Bałd appear on both). Their pure butan-2-ol tables are *bit-identical* at all five temperatures:

| T (K) | je3007666 | je800593p | je900503p (independent) | U |
|---:|---:|---:|---:|---:|
| 288.15 | 18.47 | 18.47 | — | 0.06 |
| 293.15 | 17.51 | 17.51 | 17.51 | 0.06 |
| 298.15 | **16.60** | **16.60** | **16.58** | 0.06 |
| 303.15 | 15.75 | 15.75 | 15.75 | 0.06 |
| 308.15 | 14.94 | 14.94 | — | 0.06 |
| 313.15 | — | — | 14.44 | 0.06 |

That is a **duplicate transcription, not a replication** — the project's own `duplicate_observation_groups.csv` already flags these groups as `DUPLICATE_TRANSCRIPTION_NOT_REPLICATION`. So butan-2-ol has **2 independent experiments**, not 4.

**DMAc** — `10.1016/j.fluid.2008.01.024` (Sengwa, Khatri & Sankhla) and `10.1016/j.fluid.2009.07.009` (Sengwa, Sankhla & Khatri) are the **same group**, both reporting **37.72 with the identical U = 0.23**. Also a duplicate. So DMAc has **2 independent experiments**, not 3.

---

## 2. Butan-2-ol: the spread is ONE imprecise measurement → PASS

Once the duplicate is removed, the conflict is between the Łódź consensus (16.60) and Farhan & Awwad (16.58) — **0.12% apart, 0.02 in ε against U = 0.06**. Statistically indistinguishable. There is no conflict left among the precise measurements.

The entire 6.15% spread is manufactured by one value: Guo & Jie's **17.60**. And that paper **declares its own imprecision**:

> `10.1016/j.fluid.2013.12.014`, pure butan-2-ol @ 298 K: ε = 17.60, `nCombExpandUncertValue` = **1.90** (95% expanded).

Std u = 1.90/1.96 = **0.969 (5.51% relative)**; expanded 10.8%. Therefore:

- The full spread of 1.00 in ε is only **1.03 σ** of that single observation's own stated uncertainty. The two "conflicting" values are consistent at ~1σ.
- The register flags them only because `build_source_conflict_register.py` applies a flat `REL_EPS_TOLERANCE = 2%` to point estimates and **never reads the stated uncertainties**. A ±10.8% measurement is being treated as equally informative to a ±0.36% one.

### Why 17.60 is high — three candidate mechanisms, tested

**(a) Water — ruled out.** Lifting 16.60 → 17.60 with ε_water = 80 requires, by linear bound,
φ_w = 1.00/63.4 = **1.57 vol% = 1.95 wt%**. The sample is specified at 99.5% purity (0.5% max), so this exceeds spec by ~4×. Decisively, Guo & Jie's *own* pure-alcohol values scatter in **both directions** against handbook:

| alcohol | Guo & Jie | handbook | deviation |
|---|---:|---:|---:|
| methanol | 33.10 | 32.70 | +1.2% |
| ethanol | 22.80 | 24.55 | **−7.1%** |
| propan-1-ol | 21.30 | 20.45 | +4.2% |
| propan-2-ol | 19.10 | 19.92 | **−4.1%** |
| butan-1-ol | 17.80 | 17.51 | +1.7% |
| butan-2-ol | 17.60 | 16.60 | **+6.0%** |

A water contaminant is one-sided (it can only raise ε). The observed scatter is two-sided, so this is **general DRS-extrapolation imprecision**, not contamination. The method is a PNA-N5227A network analyser fitting a Davidson–Cole relaxation — the static permittivity is an *extrapolated* quantity, and the 5.5% uncertainty is honest about that.

**(b) Temperature mislabelling — plausible, non-essential.** The abstract says measurements were made "at room temperature"; the 298 K entry is a nominal label (`nVarDigits = 3`). At −1.06 %/K, a true 293 K gives 17.51. This alone would explain the gap without invoking contamination. I do not need to choose between (b) and (c) — either way the value 16.60 is unaffected.

**(c) Real inter-laboratory bias — not supported.** The two independent precise labs agree to 0.12%.

**Conclusion:** the value is determinable and the v06 value is right. ε(butan-2-ol, 298.15 K) = **16.6** is corroborated by two independent high-precision laboratories (16.60 Łódź, 16.58 Kuwait) and lies in the literature band 16.5–17.4. → **PASS, KEEP_V06_VALUE, DOCUMENTED.**

---

## 3. DMAc: a genuine discrepancy whose value is nonetheless determinable → HOLD

Here the structure differs. Removing the Sengwa duplicate leaves **two** independent values that **genuinely disagree**, and unlike butan-2-ol the stated uncertainties do **not** cover the gap:

| source | lab | ε(303.15 K) | U(95%) | std u |
|---|---|---:|---:|---:|
| fluid.2008.01.024 | Sengwa | 37.72 | 0.23 | 0.117 |
| fluid.2009.07.009 | Sengwa | 37.72 | 0.23 | 0.117 |
| je9002515 | Świergiel & Jadżyń | **38.67** | 0.387 | 0.197 |

z = 0.950 / √(0.117² + 0.197²) = 0.950 / 0.230 = **4.14**. This is a real inter-laboratory discrepancy, and 2.52% exceeds the project's own 2.00% tolerance. So I do **not** judge this a spurious flag.

### But 37.72 is the more defensible number — three independent arguments

**(a) Świergiel's own series contradicts its 303.15 K endpoint.** That paper reports a full 10-point series (38.67, 36.551, 34.678, 32.949, 31.458, 29.954, 28.578, 27.287, 26.074, 24.923 K over 303–393 K). Fitting only its 313–393 K points and extrapolating to 303.15 K:

- linear fit → **37.48** (residual of the reported point: **+1.19**)
- quadratic fit → **38.38** (residual: **+0.29**)

So its own high-temperature data point to 37.48–38.38, which **brackets and nearly hits Sengwa's 37.72**. The 303.15 K value is the lowest-temperature endpoint of an impedance-spectroscopy extrapolation and is the least reliable point in the series.

**(b) Sign test — the decisive argument.** ε falls with T for polar aprotic liquids, and Świergiel's own slope near 303 K is −0.55 %/K. The handbook value is ε(DMAc, 298.15 K) = **37.78**. Therefore ε(303.15 K) **must be below 37.78**. Świergiel's 38.67 would require ε to *rise* by 0.89 between 298.15 and 303.15 K — **unphysical in sign**. Sengwa's 37.72 sits 0.06 below 37.78: correct sign, correct magnitude (the −0.55 %/K slope over 5 K predicts ≈ −0.38, i.e. ~37.4, and the local slope flattens toward low T). 37.72 also sits inside the literature band 36.7–37.8 for 303 K, while 38.67 sits ~2.3% **above** the top of that band.

**(c) Water is a credible mechanism — and it points at the high value.** DMAc is markedly hygroscopic. Lifting 37.72 → 38.67 requires φ_w = 0.950/42.28 = **2.25 vol% ≈ 2.4 wt%** (linear bound; DMAc–water is slightly positive-deviating, so the true requirement is ~2–2.5 wt%). 2.4 wt% uptake is entirely ordinary for bench-handled DMAc — far more attainable than the 1.95 wt% needed for butan-2-ol in a 99.5%-spec alcohol. This attributes the wet sample to Świergiel and makes 37.72 the dry value.

Note the asymmetry with butan-2-ol: there, the imprecise value was **self-declared** as imprecise (U = 5.5%) and its author's other values scattered two-sidedly. Here, Świergiel reports a **small** uncertainty (0.51%) and is nonetheless 4.1σ from Sengwa — which is precisely the signature of an unmodelled systematic (water), not of random scatter.

### Why HOLD and not PASS

I can determine the **value** (37.72) but I cannot **close the conflict** on the record: I have no sample water content for either study, and the attribution of the wet sample to Świergiel is inference from physics, not documentation. Hence `evidence_grade = INFERRED`, `decision = HOLD`. The residual source-conflict flag must travel into B04 rather than being silently retired.

---

## 4. Does the spread exceed the method's reproducibility?

| conflict | spread | best-lab reproducibility | verdict |
|---|---:|---:|---|
| butan-2-ol | 6.15% | 0.36% (U = 0.06 on 16.6) | **Yes — but only for the one lab at 5.5% rel.** Within the two precise labs the gap is 0.12%, far inside 0.36%. Spread is an artefact of pooling unequal precisions under a flat 2% tolerance. |
| DMAc | 2.52% | 0.51% (U = 0.387 on 38.67); 0.61% (U = 0.23 on 37.72) | **Yes — genuinely.** 2.52% is ~4× the stated reproducibility and 4.1σ. Exceeds the project's 2.00% tolerance. Real. |

The distinguishing test is **whether the stated uncertainties cover the gap**. For butan-2-ol they do (1.03σ). For DMAc they do not (4.14σ). That is why one conflict closes and the other does not.

---

## 5. Should either molecule stay in the model-ready set?

**Butan-2-ol — keep, no qualification needed.** Two independent, mutually consistent, high-precision determinations (16.60, 16.58) at 0.36% reproducibility, plus a five-point internal temperature series that is monotonic and physically smooth. The "conflict" is a tolerance artefact. Removing it would discard one of the better-characterised alcohols in the set.

**DMAc — keep, with a residual flag.** Do not exclude. It is a well-characterised solvent with 10 internally consistent temperatures, a physically correct monotonic decline (−0.55 %/K near 303 K, flattening at high T), and the v06 value 37.72 sits inside the literature band and passes the sign test against the 298.15 K handbook anchor. Excluding the molecule over one low-temperature endpoint of one paper would be a disproportionate remedy and would remove valid data. The correct action is to retain 37.72 **and** carry the source-conflict flag, so B04 knows this point has 4.1σ inter-laboratory spread even though its value is defensible.

---

## 6. Process recommendation (feeds B04)

The two rows here expose a **detector defect**, not a data defect. `build_source_conflict_register.py` sets `REL_EPS_TOLERANCE = 2%` and compares **point estimates only**, ignoring the `CombinedUncertainty` that the ledger already carries. Consequences:

1. A ±10.8% measurement is declared to "conflict" with ±0.36% measurements, generating a spurious conflict (butan-2-ol).
2. `n_distinct_sources` counts **DOI strings**, not independent experiments, so same-group duplicate transcriptions inflate the apparent evidence base — 2 of 4 for butan-2-ol, 2 of 3 for DMAc.

Recommended before B04 pooling: replace the flat 2% point-estimate test with an **uncertainty-aware** test (e.g. flag only when |Δε| > k·√(u₁²+u₂²), k ≈ 2), and deduplicate by `experimental_independence_unit` / author-group **before** counting sources. Under such a test, butan-2-ol would not have been flagged at all, and DMAc would have been flagged at 4.1σ — exactly the discrimination this adjudication had to reconstruct by hand.

---

## Appendix — files read

- `outputs/b01/measurement_conflict_register.csv` (56 conflicts; both target rows)
- `outputs/b01/dataset_v06_model_ready.csv` (both molecules present, `model_ready = true`)
- `outputs/b01/dataset_v06_exclusions.csv` (neither molecule present)
- `outputs/b01/b01_gate_status.md` (gate OPEN pending these 56 adjudications)
- `outputs/confirm_2027/provenance_repair/measurement_ledger_v1.csv` (27 observations for the two InChIKeys)
- `outputs/confirm_2027/provenance_repair/source_document_registry_v1.csv` (all 7 DOIs; `independence = not_evaluated` for 61/61)
- `outputs/confirm_2027/provenance_repair/duplicate_observation_groups.csv` (confirming duplicate transcriptions)
- `scripts/b01/build_source_conflict_register.py` (`T_TOLERANCE_K = 0.5`, `REL_EPS_TOLERANCE = 0.02`)
- Raw ThermoML for all 7 DOIs under `data/raw/thermoml/` — extracted `nPropValue` and `nCombExpandUncertValue` directly
- External: [DMAc ε = 37.78 @ 298.15 K](https://ir.nbu.ac.in/bitstream/123456789/703/5/05%20chapter%202.pdf), [NIST ThermoML 10.1021/je9002515](https://trc.nist.gov/ThermoML/10.1021/je9002515.xml)

No existing file was modified. Working scripts written to `outputs/b01/conflict_adjudication/_r1_*.py`.
