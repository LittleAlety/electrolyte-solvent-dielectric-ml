# Agent Workflow Visibility

Last updated: 2026-09-24 (Asia/Shanghai)

This file records delegated work at a level the user can audit in the
repository. It is not a substitute for the generated artifacts or independent
verification. Update this file whenever an agent starts, finishes, changes
scope, or is blocked.

## Current Status

| Agent | Assigned scope | State | Result or evidence | Blocker |
| --- | --- | --- | --- | --- |
| Dirac | Independent verification of the v0.3.2 veto-resolution revision (read-only) | Running | Checks data integrity, RDKit re-derivation, Crossref DOI resolution, applicability-domain circularity, verifier strength, and benchmark control | None |
| Darwin | Independent baseline review | Complete | Reviewed the Week 1 tree at baseline `7d1d645`; found no Critical/Important issue; independently reproduced 124 all-component and 100 pure-component gate identities; full suite `71 passed`; no files modified | None |
| Arendt | Week 1 fixes and evidence | Complete | Pure-only gate, provisional decision metadata, robust histogram cap, tests, notebook, and exports; targeted tests `9 passed`, full suite `71 passed`, Ruff clean; HEAD remained `7d1d645` in that worktree | None for that scope |
| Archimedes | Kernel-comparison contradiction audit | Complete | Confirmed `tree_method="exact"` and `n_jobs=1` in builder/verifier/summary; kernel tests `16 passed`, full suite `255 passed`, Ruff clean | None; the later exact-tree verifier rerun passed `5/5` |
| Hubble | Additional review | Complete with no summary | No final message or artifact was returned | No usable output; do not claim work from this agent |
| Bohr | NBS Circular 514, PDF pages 13-22 | Complete | Extracted 200 pure-liquid rows into `data/interim/nbs514_organic_part1.csv`; IDs, schema, and temperature arithmetic validated | None reported |
| Pauli | NBS Circular 514, PDF pages 23-32 | Complete | Extracted 184 pure-liquid rows into `data/interim/nbs514_organic_part2.csv`; schema and temperature arithmetic validated | Two trailing-decimal source ambiguities are marked low precision |
| Dewey | NBS Circular 514, PDF pages 33-42 | Complete | Extracted 196 pure-liquid rows into `data/interim/nbs514_organic_part3.csv`; schema, IDs, temperature conversion, and alpha scaling validated | None reported |
| Sagan | NBS Circular 514, PDF pages 43-52 | Complete | Extracted 56 pure-liquid rows into `data/interim/nbs514_organic_part4.csv`; pages 48-52 contain bibliography rather than tabulated rows | One uncertain source spelling at `nbs514:p44:012` |
| Epicurus | Independent NBS transcription audit | Complete | Sampled 20 selected rows across every page 13-32; names, formulas, values, temperature, pages, and footnotes matched | Found `Carbon disulfide` source quality mislabeled as three instead of four figures; values were correct |

## Integrated Commits

| Commit | Purpose | Status |
| --- | --- | --- |
| `eee5d40` | Use exact XGBoost trees for kernel comparison | Committed |
| `5c1251a` | Add the 217-row Landolt-Bornstein manual candidate queue | Committed |

## Follow-up

- Complete: `scripts/verify_dielectric_kernel_comparison.py` reproduced all 150
  model/repeat/fold rows and passed `5/5` checks. The Tanimoto-minus-RBF R2 mean
  difference is `0.0195030237`; the best model is `Tanimoto_GPR`; the model gate
  remains `false`.
- Complete: NBS Circular 514 extraction produced 215 resolved new structures;
  the top 110 eligible structures were added to `data/dielectric_v02.csv`,
  which now has 210 unique compounds and passes `8/8` v0.2 checks.
- Post-v0.2 work: the Landolt-Bornstein queue remains metadata-only and can be
  used for cross-checks or later expansion. The fixed-test learning curve shows
  no immediate model gain at equal training sizes, so feature/kernel work
  remains necessary.


## v0.3.2 Veto-Resolution Round (2026-09-24)

Main-thread work resolved the two Appendix I veto items. No parallel write
conflicts occurred because the revision was done single-threaded after the
read-only evidence was gathered.

| Item | Action | Evidence |
| --- | --- | --- |
| PC absent | Added epsilon=64.9 at 298.15 K | DOI 10.1021/j100702a008, Crossref-verified |
| EC absent | Added epsilon=90.5 at 313.15 K | DOI 10.1021/je050341y |
| Applicability rule circular | Added `onsager_epsilon` parameter | `src/electrolyte_ml/applicability.py`, 3 tests pass |
| Premature v1.0 tag | Deleted local + remote | Release candidate renamed to v0.3.2 |
| Glymes/dinitriles mis-reported absent | Corrected; already present under IUPAC names | `reports/g1_data_gate_review.md` |
| Benchmark stale | Re-ran on 237 rows; v0.3 baseline reproduced exactly | `probes/v032_ablation_summary.json` |

## VETO Fix Round 2 (parallel agent cluster, 2026-09-24)

Dirac's audit of the first fix attempt found that two of the three claimed
fixes were incomplete and that the headline benchmark claim was not
controlled. Five agents then ran on disjoint write sets; every agent was
read-only until it received an explicit, non-overlapping write scope.

| Agent | Bounded scope | Write set | Outcome |
| --- | --- | --- | --- |
| Dirac | adversarial audit of the first VETO fix | none (read-only) | 3 P0 + 2 P1 findings |
| Lorentz | P0-1: wire the Onsager threshold into the production caller | `probes/build_applicability_flags.py`, `src/electrolyte_ml/xtb_features.py`, `tests/test_applicability.py` | `onsager_dielectric_estimate` + explicit fallback counters; 8 tests |
| Jason | P0-3 + P1: restore provenance, harden the verifier | `data/dielectric_v032.csv`, `data/dielectric_v03.csv`, `scripts/verify_dielectric_v032.py`, `tests/test_verify_dielectric_v032.py` | 243/243 strict superset; 7 named checks; 11 tests |
| Averroes | Appendix J resource ladder | execution manual, outside the repository | Appendix J in both copies |
| Linnaeus | v1.0 wording and section sync in the paper | `paper/abstract_and_intro.md`, `paper/benchmark_and_figures.md`, `paper/code_and_data.md`, `paper/outline.md`, `paper/technical_validation.md` | 13 wording/number alignments; flagged 12 further inconsistencies, one of which the main thread also fixed; the rest are listed under remaining gaps |
| Main thread | P0-2 controlled benchmark and integration | `probes/v032_controlled_comparison.py`, `paper/full_draft.md`, `reports/`, `scripts/build_dielectric_v03.py`, `tests/test_build_dielectric_v03.py` | paired gain +0.0265 R2; validator fix; re-freeze |

### What the audit changed

The first fix attempt claimed that adding PC/EC raised hybrid R2 by +0.056.
The controlled re-run attributes **+0.0265** (95% CI +0.0171 to +0.0359) to
the data addition; 1272 of 2350 compound x repeat fold assignments (54.1%)
had silently changed between the two splits. The independently computed churn
fraction from the audit reviewer and from the main-thread probe agree to three
significant figures. The paper no longer cites +0.056 as a gain.

### Known remaining inconsistencies (open, not silently dropped)

Linnaeus' section-level review flagged inconsistencies that this round did
**not** resolve. They are recorded here rather than fixed with guessed
values, because each needs a version check against the frozen artifacts:

| Location | Issue | Why it was left open |
| --- | --- | --- |
| `paper/abstract_and_intro.md:68-70` | still describes glyme diethers and adiponitrile as missing | the G1 correction proves they exist under IUPAC names; needs a rewrite, not a number swap |
| `paper/benchmark_and_figures.md:20-35` | neural baselines labelled "same 10x5 folds" without a version | they were never rerun on v0.3.2 folds |
| `paper/benchmark_and_figures.md:38-49` | scaffold/cluster table carries older values with no version label | main draft has a different six-row v0.3.2 table |
| `paper/benchmark_and_figures.md:67-71` | Figure 1 still says `v0.3 (243)` | should read `v0.3.2 (245)` |
| `paper/code_and_data.md:16-24` | repository listing omits `dielectric_v032.csv` and the v0.3.2 verifier | structural, needs a matching rewrite |
| `paper/outline.md:122` | `immutable release commit` conflicts with candidate status | ambiguous: aspiration vs. claim |
| `paper/technical_validation.md:24-31` | conflict count not version-labelled | needs the v0.3 vs v0.3.2 distinction |
| `paper/technical_validation.md:98-99,115` | older benchmark values lack an explicit version tag | same |
| `paper/technical_validation.md:159-165` | known data gaps disagree with the corrected G1 list | same |

None of these affect the dataset, the verifier or the controlled benchmark,
but they must be closed before any v1.0 freeze.

### Verification commands for this round

| Command | Result |
| --- | --- |
| `.venv\Scripts\python.exe -m pytest -q` | `457 passed` (baseline was 441) |
| `.venv\Scripts\python.exe -m ruff check scripts src probes tests` | All checks passed |
| `.venv\Scripts\python.exe scripts/verify_dielectric_v032.py` | `passed=true`, 7/7 checks, 245 rows |
| `.venv\Scripts\python.exe probes/v032_controlled_comparison.py` | paired deltas in `probes/v032_controlled_comparison_summary.json` |

## Verification Log

| Date | Command | Result |
| --- | --- | --- |
| 2026-09-23 | `.venv\Scripts\python.exe scripts\verify_dielectric_kernel_comparison.py` | `5/5` checks passed after independent recomputation |
| 2026-09-23 | `.venv\Scripts\python.exe scripts\verify_dielectric_v02.py` | `8/8` checks passed for 210 unique compounds |
| 2026-09-23 | `.venv\Scripts\python.exe -m pytest -q` | `265 passed` |
| 2026-09-23 | `.venv\Scripts\python.exe -m ruff check scripts src probes tests` | All checks passed |
| 2026-09-23 | `.venv\Scripts\python.exe scripts\analyze_springer_materials_crosscheck.py` | 60 v0.2 compounds matched; median absolute delta `0.05`; one review conflict retained |
| 2026-09-24 | `.venv\Scripts\python.exe -m pytest -q` | `457 passed` |

## Visibility Rule

For future delegated work, record:

1. The agent name and bounded scope.
2. The baseline commit or input hashes.
3. The files or artifacts produced.
4. The verification command and observed result.
5. Any blocker, uncertainty, or unverified claim.

Do not infer completion from a running process or an empty response.
