# Agent Workflow Visibility

Last updated: 2026-09-23 (Asia/Shanghai)

This file records delegated work at a level the user can audit in the
repository. It is not a substitute for the generated artifacts or independent
verification. Update this file whenever an agent starts, finishes, changes
scope, or is blocked.

## Current Status

| Agent | Assigned scope | State | Result or evidence | Blocker |
| --- | --- | --- | --- | --- |
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

## Verification Log

| Date | Command | Result |
| --- | --- | --- |
| 2026-09-23 | `.venv\Scripts\python.exe scripts\verify_dielectric_kernel_comparison.py` | `5/5` checks passed after independent recomputation |
| 2026-09-23 | `.venv\Scripts\python.exe scripts\verify_dielectric_v02.py` | `8/8` checks passed for 210 unique compounds |
| 2026-09-23 | `.venv\Scripts\python.exe -m pytest -q` | `265 passed` |
| 2026-09-23 | `.venv\Scripts\python.exe -m ruff check scripts src probes tests` | All checks passed |
| 2026-09-23 | `.venv\Scripts\python.exe scripts\analyze_springer_materials_crosscheck.py` | 60 v0.2 compounds matched; median absolute delta `0.05`; one review conflict retained |

## Visibility Rule

For future delegated work, record:

1. The agent name and bounded scope.
2. The baseline commit or input hashes.
3. The files or artifacts produced.
4. The verification command and observed result.
5. Any blocker, uncertainty, or unverified claim.

Do not infer completion from a running process or an empty response.
