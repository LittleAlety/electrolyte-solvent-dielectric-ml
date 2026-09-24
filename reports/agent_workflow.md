# Agent Workflow Visibility

Last updated: 2026-09-24 (Asia/Shanghai)

This file records delegated work at a level the user can audit in the
repository. It is not a substitute for the generated artifacts or independent
verification. Update this file whenever an agent starts, finishes, changes
scope, or is blocked.

## Current Status

| Agent | Assigned scope | State | Result or evidence | Blocker |
| --- | --- | --- | --- | --- |
| Dirac | Independent verification of the v0.3.2 veto-resolution revision (read-only) | Complete | Audit results are integrated and summarized in `reports/v032_veto_resolution.md`; no files were modified by the reviewer | None |
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
| Applicability rule circular | Superseded: Onsager variant measured and rejected; structural donor rule adopted | `src/electrolyte_ml/applicability.py`, `probes/applicability_domain_summary.json` |
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
| Lorentz | P0-1: wire the Onsager threshold into the production caller | `probes/build_applicability_flags.py`, `src/electrolyte_ml/xtb_features.py`, `tests/test_applicability.py` | `onsager_dielectric_estimate` + explicit fallback counters; **superseded in round 3** -- the wired threshold was measured and rejected (0/150 coverage) |
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

### Applicability-domain veto re-derived (2026-09-24, round 3)

The Appendix I veto on the applicability rule was reopened after measurement
showed the round-2 repair did not work. The Onsager-threshold variant the
review prescribed was implemented and run in production, and it is physically
inverted: it covers **0 of the 150** rows whose measured permittivity exceeds
60 and instead flags a low-permittivity ionic liquid (measured 23.3). The
adopted trigger is structural -- at least one hydrogen-bond donor site counted
from SMILES with `[O,S,N;!H0]` -- which is independent of every model output
and covers 150/150 of that zone. On the 6,150 out-of-fold rows the trigger rate
is 33.66% (2,070 rows), with MAE 11.51 outside the domain against 5.02 inside.
Both rejected variants are kept, with their numbers, in
`probes/applicability_domain_summary.json` under `rejected_variants`, and the
rule now carries a pinned trigger-rate check in
`scripts/check_paper_artifact_consistency.py` so the figure cannot drift again.
See `reports/applicability_domain_veto_fix.md`.

### Paper draft inconsistencies: closed (2026-09-24, v0.3.3 round)

Linnaeus' section-level review flagged nine inconsistencies that the first round
did not resolve. All nine are now closed, and the underlying cause (a
hand-maintained `paper/full_draft.md` drifting away from the section files) was
removed: the section files are the single source of truth and
`paper/full_draft.md` is generated from them by
`scripts/build_paper_full_draft.py`.

| # | Original item | Resolution |
| --- | --- | --- |
| 1 | glyme diethers and adiponitrile described as missing | rewritten; they are present under IUPAC names, and the named gaps are now 3-methoxypropionitrile and FEC |
| 2 | neural baselines labelled "same 10x5 folds" without a version | header now names the 205-row v0.2 feature table, and the Chemprop comparison was re-based on like-for-like 205-row numbers (0.203, not 0.190) |
| 3 | scaffold/cluster table carried old values and no version label | replaced with `probes/v032_target_scaffold_summary.json` (v0.3.2, 237 rows); several std values in the existing six-row table were wrong too, e.g. `7.104 +/- 0.257` -> `7.103 +/- 0.168` |
| 4 | Figure 1 said `v0.3 (243)` | now `v0.1 (100) -> v0.2 (210) -> v0.3 (243) -> v0.3.3 (246)` |
| 5 | repository listing omitted `dielectric_v032.csv` and the v0.3.2 verifier | tree rewritten with v0.3.1/v0.3.2/v0.3.3, both verifiers, the exclusion table and the provenance patch table |
| 6 | `immutable release commit` conflicting with candidate status | reworded, and a stale-phrase check now fails the build if the phrase returns |
| 7 | conflict count not version-labelled | now stated as 9 conflict statuses / 6 `model_ready=false` / 4 withheld / 237 fitted, each re-derived from the table |
| 8 | older benchmark values lacked an explicit version tag | every benchmark table now names its dataset version and row count |
| 9 | known data gaps disagreed with the corrected G1 list | rewritten around 3-methoxypropionitrile (no physical-feature row) and FEC (excluded) |

Five further discrepancies surfaced while closing the nine, all now fixed:

| Finding | Evidence |
| --- | --- |
| v0.1 was described as 45 compounds; `data/dielectric_v01.csv` holds 100 | 45 is the Chodera common-key overlap, not the v0.1 row count |
| the Chodera cross-check claimed a median absolute deviation below 0.01 | `probes/chodera_crosscheck_summary.json`: `median_abs_delta = 0.175`, `max_abs_delta = 7.341`, 44 of 45 key pairs within 0.05 K |
| the SpringerMaterials cross-check claimed 30 modern-solvent candidates | `probes/springer_materials_crosscheck_summary.json`: `matched_compounds = 60`, matched against v0.2 |
| the Dummy baseline row claimed MAE 21.66 | no committed artifact reproduces it; replaced by a fold-matched constant baseline (MAE 12.33, R2 -0.010) recomputed from `data/processed/v032_ablation_predictions.csv` |
| the main benchmark quoted Physical AUC>30 as 0.937 | `probes/v032_ablation_summary.json` gives 0.9365, i.e. 0.936 |

Two further claims were softened after the read-only audit showed them to be
overstated: vinylene carbonate contributes about 17.8% of the hybrid
`epsilon > 60` absolute error (material, not dominant), and the 6,150-row
applicability file is 205 compounds x 3 representations x 10 repeats, not
"123 compounds x 10 x 5".

One false sentence was corrected in a historical report:
`reports/v032_veto_resolution.md` claimed "5 compounds excluded from model
fitting"; only the four rows on the curated exclusion list are withheld.

### G1+ tier-2 provenance integration (parallel read-only cluster, 2026-09-24)

Three read-only agents audited the ECW-308 evidence and its downstream
semantics while the main thread held the only write set. No parallel write
conflict occurred, and the integration made zero external API calls.

| Agent | Scope | State | Result or evidence | Blocker |
| --- | --- | --- | --- | --- |
| Noether | ECW-308 Table S3 line-level re-extraction | Complete | Re-ran pypdf from the PDF; confirmed 8/8 target rows (page/value/reference) and the tetraglyme no-hit; classified ECW as a secondary compilation | None |
| Franklin | Provenance-patch and modelling-path audit | Complete | Confirmed the patch layer can update `source_dois_all`, `notes`, and `conflict_status`, cannot update `model_ready`, and does not move the 237-row benchmark; identified the review-license gate for FEC/VC | None |
| Euler | Paper/report consistency audit | Complete | Found the FEC/VC overstatements, nitrile conflict accounting, MOPN licence wording, patch-count drift, and stale agent status | None |
| Main | Patch integration and freeze | Complete | 30 patches / 15 compounds; 246 rows; 9 conflict statuses / 6 `model_ready=false`; output sha256 `2cd58144deac6b3b4b88045de7f53564f1a9c95ff3cc9c06707d776f43e42a1b`; full suite `490 passed`; Ruff clean; all four dataset verifiers pass | None |

The integration audit also found that `data/processed/*` had been ignoring
`dielectric_v03_provenance_patches.csv`: the patch layer was present locally
but absent from Git, so a fresh clone or CI run could not rebuild the frozen
artifact. `.gitignore` now explicitly unignores the patch CSV, and the
30-row file is part of this commit.

### G1+ citation-trace escalation (parallel read-only cluster, 2026-09-24)

Three read-only agents traced the documents ECW-308 cites back to their
originals while the main thread again held the only write set. The agents
wrote no files and the combined request count stayed far below the 500/hour
cap.

| Agent | Scope | State | Result or evidence | Blocker |
| --- | --- | --- | --- | --- |
| Locke | Huang 2019 and Flamme 2017 (ECW refs 40 and 16) | Complete | 28 requests. Both closed; PubMed types Huang as a Review. Neither can supply a measurement, so the diglyme and triglyme entries are third-hand relays | None |
| Galileo | Duncan 2013, Hall 2018, Deng 2020 | Complete | 44 requests. Read the NRC accepted manuscript of Duncan 2013: Table I reports ADN 30, GLN 37, EC 89 as integers, not ECW's 30.00/37.00/89.00, so ECW added unsupported precision | Deng 2020 is closed |
| Banach | Tier 3 print references and Tier 4 databases | Complete (wrapped up on request) | 22–39 requests. Every Tier 3/Tier 4 resource is `blocked` on institutional access - none may be reported as `found=false`. Located the open-access Perricone 2011 thesis | Needs library catalogue, ILL or an institutional subscription |
| Main | Browner verification and patch integration | Complete | Confirmed Hall 2018 is CC BY 4.0 and read Table I; traced VC 126 to Saadi & Lee 1966, whose abstract confirms the dielectric constant of vinylene carbonate was measured. 13 patch rows rewritten in place | Saadi & Lee 1966 full text and Deng 2020 remain paywalled |

The two audit findings that changed the dataset: ECW-308's two-decimal nitrile
values are its own precision, not Duncan's; and the previous VC note claiming
no primary measurement existed was wrong. Neither finding changes any
`dielectric`, `T_K` or `model_ready` value, so the controlled benchmark is
untouched. Evidence: `reports/g1plus_citation_trace_findings.md`,
`reports/g1plus_tier34_access_findings.md`,
`probes/g1plus_citation_trace_evidence.json`.
### Enforcement added

`scripts/check_paper_artifact_consistency.py` re-derives row counts, conflict
counts, the main benchmark table, the scaffold table, the release version and
the generated draft from the committed artifacts, and fails on any mismatch.
`tests/test_paper_artifact_consistency.py` pins it with injected-drift tests, so
each mutation must produce an error. Both run in CI alongside the dataset
verifiers.

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
| 2026-09-24 | `.venv\Scripts\python.exe -m pytest -q` | `481 passed` (first v0.3.3 provenance round) |
| 2026-09-24 | `.venv\Scripts\python.exe -m pytest -q` | `490 passed` (G1+ tier-2 provenance integration) |
| 2026-09-24 | `.venv\Scripts\python.exe scripts/verify_dielectric_v03.py` | `passed=true`, 7/7 checks, 246 rows, sha256 `88f0a1a6...a7a33` |
| 2026-09-24 | `.venv\Scripts\python.exe scripts/verify_dielectric_v032.py` | `passed=true`, 7/7 checks, 245 rows |
| 2026-09-24 | `.venv\Scripts\python.exe scripts/verify_dielectric_v03.py` | `passed=true`, 7/7 checks, 246 rows |
| 2026-09-24 | `.venv\Scripts\python.exe scripts/build_paper_full_draft.py --check` | `paper/full_draft.md` up to date |
| 2026-09-24 | `.venv\Scripts\python.exe scripts/check_paper_artifact_consistency.py` | `paper drafts agree with the frozen artifacts` |
| 2026-09-24 | `.venv\Scripts\python.exe -m pytest tests/test_paper_artifact_consistency.py -q` | `8 passed` (includes 6 injected-drift tests) |

## Visibility Rule

For future delegated work, record:

1. The agent name and bounded scope.
2. The baseline commit or input hashes.
3. The files or artifacts produced.
4. The verification command and observed result.
5. Any blocker, uncertainty, or unverified claim.

Do not infer completion from a running process or an empty response.
