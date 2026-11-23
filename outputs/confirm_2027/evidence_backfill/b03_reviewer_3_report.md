# B03 Reviewer 3 — Data Mapping, Identity, Temperature, Frequency and Code Correctness

**Work package:** B03 (A18 evidence backfill) · **Scope:** code and data mapping audit
**Reviewer:** 3 of 4 (independent) · **Files modified:** none in `data/`, `scripts/`, `outputs/` (all experiments ran in an isolated `mktemp` tree)

**Verdict:** both target values **reproduce exactly**. The *evidence* is real and the *numbers* are right. The *code that claims to prove it* does not prove what it says, and the accounting gate is a tautology. Decisions: **C11 EA = PASS**, **C12 MA = PASS**, with a package-level **HOLD** on the verification logic.

---

## 1. Independent recomputation table

Method: read the three sources directly, no script reuse. Then confirm against the PDF bytes.

| | Ethyl acetate (C11) | Methyl acetate (C12) |
|---|---|---|
| Transcription `data/interim/nbs514_organic_part1.csv` | line 160: `nbs514:p20:022`, p.20, C4H8O2, **6.02**, t=25 °C, T=**298.15** | line 103: `nbs514:p18:009`, p.18, C3H6O2, **6.68**, t=25 °C, T=**298.15** |
| Frozen `data/dielectric_v04.csv` | Ethyl acetate, **6.02** @ **298.15** | Methyl acetate, **6.68** @ **298.15** |
| `data/raw/nbs514_expansion/expansion_observations.csv` | **6.02** @ **298.15**, `source_id=nbs514:p20:022` | **6.68** @ **298.15**, `source_id=nbs514:p18:009` |
| `source_record_id` / `source_id` alignment | all three = `nbs514:p20:022` ✔ | all three = `nbs514:p18:009` ✔ |
| InChIKey (v04 vs expansion) | `XEKOWRVHYACXOJ-UHFFFAOYSA-N` ✔ | `KXKVLQRXCPHEJC-UHFFFAOYSA-N` ✔ |
| **PDF ground truth** (`fitz`, 56 pp.) | page 20: `Ethyl acetate......  6.02  25` | page 18: `Methyl acetate.  6.68  25` |
| **Recomputed ε** | **6.02** | **6.68** |
| **Match** | **true** | **true** |

**All three agree — and they agree with the document itself.** Two independent checks beyond the script's own claim:

1. **PDF verification.** The values are not merely self-consistent across CSVs; extracting text from `data/raw/nbs514/nbscircular514.pdf` yields `6.02`/`25` on page 20 and `6.68`/`25` on page 18. So this is a genuine page read, not a value derived from the same upstream table. Evidence grade **DOCUMENTED** is justified.
2. **Mirror integrity.** `expansion_observations.csv` shares 109 `source_id`s with v04; on all 109 the ε and T match to 1e-12 (0 mismatches). The expansion table is a faithful mirror, so the script's comparison, though mislabelled (§2 D2), lands on correct data.

**Temperature and frequency.** 298.15 K sits inside the 293.15–303.15 K band, so `condition_qualified=true` is legitimate. Frequency: MA/EA rows carry an **empty** `frequency_note` in the transcription (unlike the 127 of 636 rows that carry e.g. `f=4x10^8 cycles/sec`), so treating them as static is correct **for these two rows** — but see D6, the code asserts this unconditionally.

**Byte-for-byte claim: partly false.** The ε/T strings are `'6.02'`/`'6.68'` in all three files, so "byte-for-byte" holds for the values. It does **not** hold for the JSON artifacts (§6).

---

## 2. Code defects

### D1 — `v04_eps` assigned from `n_observations` (dead, but a real trap)
`scripts/b03/verify_nbs514_evidence.py:163-168`

```python
v04_eps = None
v04_t = None
for x in gap:
    if x["a_name"].upper() == short:
        v04_eps = fnum(x.get("n_observations"))   # <-- an observation COUNT, not an epsilon
        break
```

This is a genuine wrong-column bug. `v04_t` (line 164) is never assigned and never read. **`v04_eps` is itself never read**: the emitted `v04_epsilon` comes from `exp_eps` (line 188). Verified by removing the whole lookup — output is unchanged. So it is **dead, and it is not exported anywhere**.

Why it still matters: it *reads* as "the v04 epsilon was fetched and checked", which is exactly the reassurance D2 shows is false. And `n_observations` for EA/MA is **0**, so had anyone wired it up, both molecules would have been reported as `VALUE_MISMATCH` against ε=0. A latent landmine sitting one edit away from a false accusation against two correct records.

### D2 — the "v04" comparison never touches v04 (most serious)
`scripts/b03/verify_nbs514_evidence.py` (whole file); the label is set at `:188`, the comparison at `:175-176`

`grep -n "dielectric_v04" scripts/b03/verify_nbs514_evidence.py` → **no match**. The script never opens `data/dielectric_v04.csv`. The column it writes as `v04_epsilon` is `exp_eps`, from `expansion_observations.csv`.

**Demonstrated:** in an isolated tree, set EA/MA `dielectric` to `99.99` in `dielectric_v04.csv` and re-run. Output is unchanged — still `v04_epsilon=6.02/6.68`, `epsilon_agrees=true`, `VERIFIED_AGAINST_PAGE_READ`.

Consequences:
- The docstring promise (lines 8-10, "confirms the value agrees with the frozen v04 row") is not implemented.
- `nbs514_verification.json` `key_finding` asserts byte-identity with frozen v04 — untested.
- `tests/test_b03_evidence_backfill.py::test_nbs514_verification_matches_frozen_v04` asserts `r["v04_epsilon"] == r["nbs514_epsilon"]` — comparing the page read to *itself*. The test **cannot fail**, so it provides zero protection.

The values do agree (I confirmed independently), so **no incorrect number is published**. The defect is in the *audit claim*, not the data. Because a reviewer reading "verified against frozen v04" would reasonably assume a real cross-check occurred, this needs to be disclosed rather than waved through.

### D3 — silent skip of missing raw inputs
`scripts/b03/verify_nbs514_evidence.py:111-113` and `:122-126`

```python
for part in NBS_PARTS:
    if not part.is_file():
        continue          # no warning, no record, exit 0
```

Only `GAP_REGISTER` is guarded (`:99-102`). **Demonstrated:** removing `nbs514_organic_part1.csv` — the file holding *both* MA and EA — still exits 0 and rewrites every register asserting `NO_NBS514_COVERAGE` ("all four transcriptions lack this compound") for EA and MA. That is a false negative about the exact molecules under audit, emitted with no signal. Removing only `expansion_observations.csv` flips both to `VALUE_MISMATCH` with a blank `v04_epsilon`, again exit 0. A missing input should be fatal, not silently reinterpreted as absence of evidence.

### D4 — no collision in `NAME_MAP` (checked, clean)
`scripts/b03/verify_nbs514_evidence.py:56-70`

All 13 keys distinct; only 4 ever hit (`Acetonitrile`, `Methyl acetate`, `Ethyl acetate`, `Diethyl carbonate`). Lookup is **exact match** on the full stripped upper-cased `compound_name`, so `Ethyl acetate` cannot be captured by `beta-Hydroxyethyl acetate`, `alpha-Cyanoethyl acetate`, `Ethyl dichloroacetate`, or `Ethyl trichloroacetate`.

Formula-level false friends *do* exist and are worth recording: `C3H6O2` holds both `Ethyl formate` and `Methyl acetate`; `C4H8O3` holds `beta-Hydroxyethyl acetate`; `C4H8O2` holds `Butyric acid`, `Propyl formate`, `Methyl propionate`, `1,4-Dioxane`. **A formula-based join would mis-assign MA and EA. The name-based join does not.** This is the single most important identity check in the package and it passes.

### D5 — the accounting gate can never fail
`scripts/b03/build_b03_report.py:64, 70-71`

```python
resolved_ids = {r["a_mol_id"] for r in gap} - {r["a_mol_id"] for r in unres}
accounted = len(resolved) + len(unres)
gate_ok = (accounted == len(gap)) and len(qual) > 0
```

`resolved` is *defined* as the complement of `unres`, so `len(resolved) + len(unres) == len(gap)` is an identity — **true by construction, a comparison that can never fail**.

**Demonstrated:** deleting the `C04/EC` row from `unresolved_molecules.csv` yields `accounting_closed=true`, `gate.open=true`, `resolved=['DMC','DEC','SL','EA','MA','EC']`, and the report prints `6 + 12 = 18 / 18 ✅ 通过`. The gate then **certifies EC as having evidence when it has none** — precisely the "silent disappearance" failure its own docstring says it exists to catch. It is the failure mode, wearing the gate's uniform.

Secondary: `:71` folds `len(qual) > 0` into `gate_ok`, so with zero condition-qualified rows the gate prints `CLOSED` while `accounting_closed` stays `true` — two fields contradicting each other in the same JSON.

The real split is correct today (§4), but nothing enforces it. A real gate must check against an independent denominator (e.g. the frozen A18 priority list), not against a set it just computed.

### D6 — hard-coded "static" frequency claim
`scripts/b03/verify_nbs514_evidence.py:222`

```python
"frequency": "static (NBS514 tabulates static values)",
```

A literal, not a measurement. The transcription has a `frequency_note` column and **127 of 636 rows populate it** (`f=4x10^8 cycles/sec`, etc.), so the blanket claim is false in general. MA/EA are safe because their own note is empty — but the note is never read or validated, so any future molecule routed through `NAME_MAP` would inherit "static" regardless of what the source actually says. This is a frequency-correctness defect with a currently-benign footprint.

### D7 — hard-coded molecule ids in a data-driven branch
`scripts/b03/build_b03_registers.py:212-216`

```python
action = ("检索原始文献/公开数据库; 该分子在 ThermoML 与 NBS514 中均无覆盖"
          if aid not in ("C11", "C12") else
          "该分子有 NBS514 页面读取但核实未通过, 需回原文核对")
```

**The branch does handle EA/MA correctly today** — they are filtered out earlier by `if n_valid > 0 or nbs_ok: continue` (`:209`), so neither appears in `NO_OBSERVATION_AND_NO_PAGE_READ`. Confirmed: `unresolved_molecules.csv` contains no C11/C12 row.

But the id list is hard-coded into a branch that is supposed to be data-driven. **Demonstrated:** corrupting MA's expansion ε pushes MA into this branch, and the emitted `next_action` reads "该分子在 ThermoML 与 NBS514 中均无覆盖" (no coverage in either source) — while the same row's `nbs514_page_read_verified` column says `false` and MA demonstrably *does* have a page read. Internally contradictory output, produced by string-matching on ids instead of on state.

### Minor / non-defects (checked so the others need not)
- **No silent `try/except`.** The only handler is `fnum()` (`:88-95`), catching `ValueError` from `float()` → `None`. Deliberate, cannot hide a failed join.
- **No `.get(key, default)` hides a join.** Every `.get` in `build_b03_registers.py` is either a CSV-column read on an existing row or an explicit default for an absent registry entry.
- **Float comparisons use tolerance.** `:175-178` and `:212` all use `abs(a-b) < 1e-9`. No bare `==` on floats.
- **Unused, harmless:** `v04_t` (`:164`); `coverage`/`cov_by_mol` (`build_b03_registers.py:84-89`) computed then never read.

---

## 3. `build_b03_registers.py` `resolved` logic

`if n_valid > 0 or nbs_ok: continue` (`:209`) classifies every molecule correctly:

| Molecule | n_valid | nbs_ok | Classified | Correct? |
|---|---|---|---|---|
| DMC, DEC, SL | 1 | false | resolved | ✔ has a condition-valid pair |
| **EA, MA** | 0 | **true** | **resolved** | ✔ via page read (see below) |
| DME, TEGDME, GBL, DMSO | 0 | false | unresolved / `NO_CONDITION_VALID_PAIR` | ✔ |
| SN | 0 | false | unresolved / `NO_ROOM_BAND_OBSERVATION` | ✔ |
| AN | 0 | false | unresolved / `NO_CONDITION_VALID_PAIR` | ✔ |
| EMC, EC, PC, FEC, VC, DOL, TMP | 0 | false | unresolved / `NO_OBSERVATION_AND_NO_PAGE_READ` | ✔ |

The `NO_OBSERVATION_AND_NO_PAGE_READ` branch handles EA/MA correctly: they are **not** in it (D7).

**Is "resolved" on a page read alone justified, given nothing is admitted?** Yes, with a caveat. The code is explicit at `:206-208` that the bar is "evidence exists, not admitted", and the artifact refuses to overclaim: `condition_qualified_measurements.csv` stamps `admission_status=PENDING_FOUR_AGENT_REVIEW` and `in_measurement_ledger=false`. Nothing enters B04 on the strength of the label. The caveat is that "resolved" is a strong word for "evidence exists", and `b03_gate_status.json` lists EA/MA under `resolved_molecules` with no qualification — a reader skimming that file alone would over-read it. Recommend renaming to `EVIDENCE_PRESENT_NOT_ADMITTED`, or adding an `admission_status` column to the gate status.

---

## 4. Accounting closure — arithmetic sound, enforcement absent

| Check | Result |
|---|---|
| `unresolved_molecules.csv` rows | 13 |
| resolved | 5 |
| **13 + 5** | **18 = n_a18** ✔ |
| resolved set exactly `{DMC, DEC, SL, EA, MA}` | ✔ (`C01, C03, C14, C11, C12`) |
| resolved ∩ unresolved | ∅ ✔ |
| resolved ∪ unresolved == register | ✔ |
| each of the 5 justified | ✔ (DMC/DEC/SL: `n_condition_valid_pairs=1`; EA/MA: verified page read) |

**The closure is numerically sound.** The 13/5 split is real, not manufactured — no molecule was dropped to make the arithmetic work.

**But it is not *enforced*.** Per D5 the check is a tautology: it validates a set against its own complement. My deletion experiment turned EC into a "resolved" molecule with the gate still reporting `accounting_closed: true`. So the correct answer today is **right by construction of the data, not by construction of the test** — the audit is passing on luck plus diligence, not on machinery.

---

## 5. Reproducibility

Two full runs of all three scripts in an isolated tree:

- **All six CSV deliverables: byte-identical** across runs ✔
  `A18_gap_register.csv`, `source_verification.csv`, `condition_qualified_measurements.csv`, `literature_source_inventory.csv`, `independent_source_map.csv`, `unresolved_molecules.csv`
- **JSON/MD artifacts: NOT byte-identical** ✘ — `generated_at_utc` differs each run in `A18_gap_register.json`, `nbs514_verification.json`, `b03_registers.json`, `b03_gate_status.json`, `evidence_backfill_report.md`; `b03_gate_status.json` additionally embeds `sha256` of `evidence_backfill_report.md`, which carries its own timestamp, so the drift propagates.
- Live artifacts are **not stale**: all 7 recorded `sha256` values in `b03_gate_status.json` match the files on disk. But the recorded `generated_at_utc` (`2026-11-23T06:01:50Z`) predates the report it hashes, so the gate status is self-inconsistent in ordering — it was written before the artifact whose hash it embeds was finalised. Rebuild order is `report → gate`, so the gate always describes the *previous* report. Harmless now (hashes match because a later full rebuild happened), but it is a latent staleness bug.

Determinism is otherwise sound: no `set` iteration leaking into output ordering (all `sorted`), no `random`, no wall-clock beyond the timestamp field, no locale-dependent float formatting (`:g`).

---

## 6. Decisions

| mol | decision | grade | ε recomputed | match |
|---|---|---|---|---|
| **C11 EA** | **PASS** | DOCUMENTED | **6.02** | true |
| **C12 MA** | **PASS** | DOCUMENTED | **6.68** | true |

Both PASS, with the defects above recorded. I am satisfied the ε values are correctly transcribed, correctly mapped to the right molecules, correctly conditioned on temperature, and confirmed against the source document itself. The PASS does **not** extend to the verification *machinery*: `v04_epsilon` is not a v04 value (D2), the v04 test cannot fail (D2), and the accounting gate cannot fail (D5).

**Package-level recommendation: HOLD** on the claim "verified against frozen v04 byte-for-byte" until D2 is fixed (read the real file) and D5 is fixed (independent denominator). Neither fix changes any published value — which is exactly why they are cheap and worth doing before the package advances to B04.

**Nothing has been admitted.** Per `condition_qualified_measurements.csv`, both rows remain `PENDING_FOUR_AGENT_REVIEW` and `in_measurement_ledger=false`. The 0-new-observations statement in the report is honest and I confirm it: EA/MA were already in v04 with `dataset_origin=v0.2`.

---

## 7. Files

- Decisions: `outputs/confirm_2027/evidence_backfill/b03_reviewer_3_decisions.csv` (2 target rows + 7 `ALL` rows)
- This report: `outputs/confirm_2027/evidence_backfill/b03_reviewer_3_report.md`

No file under `data/`, `scripts/`, or existing `outputs/` was modified. Every experiment (v04 corruption, expansion corruption, part1 removal, expansion removal, unresolved-row deletion) ran against a `mktemp -d` copy; the live tree was re-verified clean afterwards (`data/dielectric_v04.csv` sha256 `e046a383...` unchanged, transcription part mtimes unchanged).
