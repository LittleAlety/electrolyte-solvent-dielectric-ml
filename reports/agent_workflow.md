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
| Benchmark stale | Re-ran the v0.3.2 lineage and reproduced the v0.3 baseline exactly (**superseded in round 4:** 236 fitted rows once `model_ready` became a gate) | `probes/v032_ablation_summary.json` |

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
| Main thread | P0-2 controlled benchmark and integration | `probes/v032_controlled_comparison.py`, `paper/full_draft.md`, `reports/`, `scripts/build_dielectric_v03.py`, `tests/test_build_dielectric_v03.py` | paired gain +0.0265 R2; validator fix; re-freeze. **Superseded in round 4:** +0.0059 once `model_ready` became a gate |

### What the audit changed

The first fix attempt claimed that adding PC/EC raised hybrid R2 by +0.056.
The controlled re-run attributes **+0.0265** (95% CI +0.0171 to +0.0359) to
the data addition; 1272 of 2350 compound x repeat fold assignments (54.1%)
(superseded in round 4 -- with the `model_ready` gate the same control gives
+0.0059 and 1224 of 2340 = 52.3% churn)
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

### model_ready gate enforced (2026-09-24, round 4)

A read-only audit of the paper's own claim -- "5 withheld, 236 fitted" -- found
that no fitting script could have produced that split. The feature tables carry
no `model_ready` column, so `read_modelling_rows` had no way to honour the flag:
it dropped rows on the curated exclusion list and rows whose features failed,
and silently kept everything else. Vinylene carbonate, flagged
`model_ready=false` and `conflict_open`, was therefore inside the fitted set in
every revision up to v0.3.3, while 3-methoxypropionitrile was outside it only
because its feature row happened to be missing.

`probes/dielectric_representation_ablation.py::read_modelling_rows` is the
single choke point for every dielectric fit. It now reads `model_ready` from
`data/dielectric_v03.csv` (join on InChIKey) and returns a three-way split --
fitted, feature-failed, withheld. Withheld rows are returned to the caller
instead of being dropped, a source row that has no roster entry raises
`ValueError` (its status would be unknowable), and the accounting invariant is
extended to `fitted + failed + withheld + excluded == source`, with the
exclusion list intersected against the source lineage and any unmatched
exclusion reported.

| Lineage | Source | Fitted | Excluded | Feature failures | Withheld |
| --- | --- | --- | --- | --- | --- |
| v0.3.2 | 245 | 236 | 4 | 4 | 1 |
| v0.3.3 | 246 | 236 | 5 | 4 | 1 |

Vinylene carbonate is the withheld row in both lineages.
3-Methoxypropionitrile was implicitly out before (no feature row, no exclusion
entry) and is now an explicit fifth exclusion row.

The benchmark was re-derived on 236 rows, and the controlled PC/EC gain did not
survive the gate:

| Representation | Baseline R2 | +PC/EC | Paired delta | 95% CI | p |
| --- | --- | --- | --- | --- | --- |
| Morgan | 0.2203 | 0.2191 | -0.0012 | [-0.006, +0.003] | 0.59 |
| Physical | 0.3201 | 0.3194 | -0.0007 | [-0.016, +0.014] | 0.92 |
| Morgan+Physical | 0.3456 | 0.3515 | **+0.0059** | [-0.002, +0.013] | 0.11 |

The previously reported +0.0265 hybrid and +0.0502 Physical gains were carried
by the withheld row: PC and EC are structural analogues of vinylene carbonate,
so appending them to the training folds mostly improved the prediction of that
one contested compound. Fold churn between the two splits is now 1224 of 2340
compound x repeat assignments (52.3%). `data/dielectric_v03.csv` was unchanged in
that round (sha256 `2cd58144...a1b` as of v0.3.4; the current revision is
`f5256d16...a853c`): no `dielectric`, `T_K` or `model_ready` value moved,
and the v0.3.2 and v0.3.3 lineages now fit the *same* 236 rows and return
identical metrics, so the old row-wise v0.3 -> v0.3.2 "coverage gain" was fold
churn plus the ungated row.

Enforcement added in this round:

- `scripts/check_paper_artifact_consistency.py` gained
  `check_modelling_set_and_controlled_delta` (re-derives the fitted-row count,
  the paired delta and its CI from the artifacts), `check_coverage_sensitivity_table`
  (validates the per-version coverage table against the ablation summaries), and
  stale-phrase guards for the superseded benchmark tables.
- `tests/test_dielectric_representation_ablation.py` pins the three-way split,
  the withheld-versus-failed distinction, the unknown-roster `ValueError`, and
  the shipped tables (exactly one withheld row, vinylene carbonate).
- `tests/test_build_dielectric_v03.py` asserts that the gate withholds exactly
  the pinned offender set.
- `probes/dielectric_target_and_scaffold.py` now resolves every output path up
  front, and `probes/v032_controlled_comparison.py` derives its frozen-test-set
  note and churn figure from the data instead of hard-coding them.

Write-up: `reports/v034_model_ready_gate.md`.

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
| 3 | scaffold/cluster table carried old values and no version label | replaced with `probes/v032_target_scaffold_summary.json` (v0.3.2 lineage, 236 fitted rows); several std values in the existing six-row table were wrong too, e.g. `7.104 +/- 0.257` -> `7.103 +/- 0.168` |
| 4 | Figure 1 said `v0.3 (243)` | now `v0.1 (100) -> v0.2 (210) -> v0.3 (243) -> v0.3.3 (246)` |
| 5 | repository listing omitted `dielectric_v032.csv` and the v0.3.2 verifier | tree rewritten with v0.3.1/v0.3.2/v0.3.3, both verifiers, the exclusion table and the provenance patch table |
| 6 | `immutable release commit` conflicting with candidate status | reworded, and a stale-phrase check now fails the build if the phrase returns |
| 7 | conflict count not version-labelled | now stated as 9 conflict statuses / 6 `model_ready=false` / 5 withheld / 236 fitted, each re-derived from the table |
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
| Franklin | Provenance-patch and modelling-path audit | Complete | Confirmed the patch layer can update `source_dois_all`, `notes`, and `conflict_status`, cannot update `model_ready`, and does not move the benchmark (round 4 later took the fitted set to 236 rows); identified the review-license gate for FEC/VC | None |
| Euler | Paper/report consistency audit | Complete | Found the FEC/VC overstatements, nitrile conflict accounting, MOPN licence wording, patch-count drift, and stale agent status | None |
| Main | Patch integration and freeze | Complete | 32 patches / 17 compounds; 246 rows; 9 conflict statuses / 6 `model_ready=false`; output sha256 `f5256d164c814030a4b986db6c878f1d64edb2b4f91cf39af3a75ffeaeac853c`; full suite `553 passed` (as of the final freeze); Ruff clean; all four dataset verifiers pass | None |

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
counts, the main benchmark table, the scaffold table, the per-version coverage
table, the fitted-row count and the controlled PC/EC delta, the release version
and the generated draft from the committed artifacts, and fails on any mismatch;
superseded number strings are rejected outright.
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

## Tier-1 closeout: WebBook structural negative and the adversarial repair (parallel read-only cluster, 2026-09-24)

The main thread again held the only write set. Two read-only reviewers were
dispatched against the v0.3.6 diff with different lenses - one on provenance
semantics, one on reproducibility and export integrity - and the NIST WebBook
probe was written by the main thread while they ran, so no two writers touched
the same file.

| Agent | Scope | State | Result or evidence | Blocker |
| --- | --- | --- | --- | --- |
| Heisenberg | Provenance and evidence-semantics audit of the PubChem artefact | Complete, **FAIL** | Found the P1 classification defect (nine compounds filed as standard values when only two carry a number), two citation errors (p. 98 vs the cached p. 989; "dry ether" vs "dry ethyl ether"), 429/5xx being swallowed into `not_in_pubchem`, cache staleness, and the `riddick_reference_count` naming defect | None |
| Peirce | Reproducibility, hash-chain and export-integrity audit | Complete, **FAIL** | Independently reproduced the same P1, confirmed the hash re-pin is complete and that no test assertion was weakened, and found the week7/week8 exports stale, four artefacts missing from the exporter, the hard-coded `0.3.3 (v0.3.4 candidate)` label, and the 30/490 statistics drift | None |
| Main | WebBook probe, adversarial repair, evidence regeneration, Materials Project evaluation, re-export | Complete | NIST WebBook closed as a dielectric source (13/14 resolved, 0 facets, 4/4 positive controls also empty); seven repair items plus four second-round items applied; Materials Project closed as out of scope (control populated, 14/14 targets empty) while CatalystHub is recorded as unreachable rather than empty | None |

### What the reviewers changed

Both reviewers independently returned FAIL on the same P1, which is the useful
outcome: the report said "only two of fourteen targets expose a number" while the
machine-readable summary said nine. The summary was wrong. Fixing it then
introduced a second defect that the same scrutiny caught - the first numeric
parser read temperatures as dielectric values - so the split is now explicit:
pinned to values (with temperatures kept as a separate field, including kelvin
and frequency annotations, and any segment the parser cannot consume whole is
flagged as `unparsed_clauses` rather than guessed at), narrative-and-link
mentions are recorded as mentions, and
`tests/test_g1plus_tier1_probes.py` locks all four categories down offline.

A second, independent check was run on the two databases the user supplied as
alternatives once SpringerMaterials went away. The Materials Project probe deliberately
carries a positive control: the collection really does expose DFPT dielectric fields
(`e_total`, `n`), and SiO2 returns 322 populated documents, while all 14 molecular-liquid
targets return `total_doc = 0`. That pairing is what turns "no results" into a supportable
claim about scope. CatalystHub could not be reached at any plausible endpoint, and is
recorded as inaccessible rather than as empty.

No dataset value moved in this round: `data/dielectric_v03.csv` is still
`f5256d164c814030a4b986db6c878f1d64edb2b4f91cf39af3a75ffeaeac853c`.


## ECW-308 second adversarial round: identity gate and extractor precision (round 3, 2026-09-24)

Reviewer: Boole (read-only adversarial pass, independent pypdf scan, no reuse of the
extractor's own helpers). Verdict on v0.3.8: **FAIL - 1 Important, 2 Minor, no Critical**.
The main thread held the only write set; the reviewer ran read-only.

| # | Finding (reviewer) | Fix (main thread) |
| --- | --- | --- |
| Important 1 | Three same-CID name pairs were still outside `SYNONYM_NAMES`, so `matched=24 / formula_only=20` was a mechanical count rather than a complete identity gate | Added `n butyl acetate`, `dimethylketone`, `n methylpyrrolidinone`; the three rows now pass the gate (5.00/5.01, 20.50/20.7, 32.00/32.2) |
| Minor 1 | Row 279's name carried its row number because pypdf splits `279.` into `279` `.` tokens | Name assembly strips a bare row index plus the punctuation token that follows it |
| Minor 2 | `ecw_no_formula` still mixed two different causes (row pitch vs page break) | Both causes fixed in the extractor; the state now reads 0 and is kept as a safety net |

The reviewer's three findings also exposed four **extraction** defects that the counts alone
would have hidden. They were fixed at the root rather than by adjusting expectations:

| Defect | Evidence | Fix |
| --- | --- | --- |
| Two row pitches (24.6 pt / 48.7 pt) left the formula of wrapped rows 36.3 pt below the label, past the 35 pt cap | rows 88 (DFEME) and 89 (TFEME) had no formula | Per-line clustering (2.5 pt gap) plus a 45 pt cap whose real bound is the next row label |
| Names were read from the label line only | row 88 was `1,1 - Difluoro 2 (2` | Names are reassembled line by line down to the formula line; continuation lines must start in the name column (x<=250) and value tokens are refused |
| The block was bounded per page | rows 43 (MOPN) and 116 print their formula at the top of the following page | Block boundaries moved to document order `(page, -y)`; both formulas recovered |
| The duplicate guard dropped a token whenever it appeared inside an earlier one | `1` inside `91.` and `Me` inside `Methyl` were deleted | Only same-coordinate duplicates are dropped, with a word-boundary test for multi-character chunks |

Row-by-row diff against the v0.3.8 artefacts (definitions reproducible): rows carrying a formula
**267 -> 308** (**+41 gained, 0 lost, 0 changed**); **130** rows changed their `name`, net **+2004**
characters (sum of `len(new) - len(old)`), including net **+172** printed hyphens; **no field other
than `name`/`formula` moved**.

The round-3 reviewer (Einstein) then judged this revision FAIL with 2 Important and 1 Minor, all of
which were real and are fixed in the follow-up commit:

| Finding | Evidence | Fix |
| --- | --- | --- |
| The report's `+21 / 112 / 66` numbers did not match a row-by-row diff, and the claimed "45 pt cap" did not exist in the code | `git show d37c5b8:...evidence.json` vs the new file: 41 rows gained a formula, 0 lost; 130 names changed | Numbers replaced with reproducible definitions; the dead `FORMULA_*_DY` constants were deleted and the report now describes the real rule (next row label, no dy window) |
| Refusing every numeric token on a continuation line deleted legitimate locants | rows 207 (`octane - 3 - one`), 235 (`3 - Methoxysulfolane`), 246 (`ethyl 2 - methylsulfonylethyl carbonate`) | Only decimal value cells are refused on a continuation line |
| The report tail still pinned the v0.3.8 hashes | `reports/g1plus_ecw308_crosscheck.md` section 7 | Hashes updated to the v0.3.9 pair |

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
| 2026-09-24 | `.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider` | `509 passed` (v0.3.4 model_ready gate round) |
| 2026-09-24 | `.venv\Scripts\python.exe -m ruff check scripts src probes tests` | All checks passed |
| 2026-09-24 | `.venv\Scripts\python.exe scripts/verify_dielectric_representation_ablation.py` | every fold, repeat and summary metric recomputed from the shipped tables; `passed=true` |
| 2026-09-24 | `.venv\Scripts\python.exe scripts/verify_dielectric_target_scaffold.py` | scaffold balance and input hash verified; `passed=true` |
| 2026-09-24 | `.venv\Scripts\python.exe scripts/verify_dielectric_v03.py` | `passed=true`, 7/7 checks, 246 rows, sha256 `2cd58144...a1b` |
| 2026-09-24 | `.venv\Scripts\python.exe scripts/verify_dielectric_v032.py` | `passed=true`, 7/7 checks, 245 rows |
| 2026-09-24 | `.venv\Scripts\python.exe scripts/verify_dielectric_v02.py` | 9/9 checks passed |
| 2026-09-24 | `.venv\Scripts\python.exe scripts/verify_week1.py` | 15/15 checks passed |
| 2026-09-24 | `.venv\Scripts\python.exe scripts/check_paper_artifact_consistency.py` | `paper drafts agree with the frozen artifacts` (now also checks the coverage table, the fitted-row count and the controlled delta) |
| 2026-09-24 | `.venv\Scripts\python.exe probes/g1plus_nist_webbook_probe.py` | 13/14 targets resolved on the identity gate; 0 dielectric facets; 4/4 positive controls also empty, so the negative is structural |
| 2026-09-24 | `.venv\Scripts\python.exe probes/g1plus_pubchem_probe.py` | regenerated after the repair: numeric values exactly `[sulfolane, acetonitrile]`, 9 SpringerMaterials links, 1 narrative-only mention, 5 with no evidence |
| 2026-09-24 | `.venv\Scripts\python.exe -m pytest tests/test_g1plus_tier1_probes.py -q` | `18 passed` - value/temperature separation, the narrative and link categories, the Riddick occurrence count, and the WebBook identity gate |
| 2026-09-24 | `.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider` | `538 passed` (521 before this round) |
| 2026-09-24 | `.venv\Scripts\python.exe probes/g1plus_materials_project_probe.py` | Materials Project: positive control SiO2 = 322 documents with populated `e_total`/`n`; **0/14 targets** |
| 2026-09-24 | `.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider tests/test_g1plus_materials_project_probe.py` | `14 passed` - control-populated evidence, LF-only artefacts, a guard that no API key shape leaked into them, and the 429/5xx, non-transient-error and cache-binding paths |
| 2026-09-24 | `.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider` | `553 passed` (538 before the Materials Project round) |
| 2026-09-24 | `.venv\Scripts\python.exe probes/g1plus_ecw308_extract.py` | 308 rows / 87 value / 204 blank / 11 missing / 6 stacked; crosscheck matched=27, divergent=6, formula_only=19, ecw_no_formula=0 |
| 2026-09-24 | `.venv\Scripts\python.exe probes/g1plus_ecw308_extract.py --check` | `evidence reproduces: True` after the identity-gate and extractor repairs |
| 2026-09-24 | `.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider tests/test_g1plus_ecw308_extract.py` | `48 passed` (36 before this round) |
| 2026-09-24 | `.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider` | `601 passed` (589 before this round) |

## Visibility Rule

For future delegated work, record:

1. The agent name and bounded scope.
2. The baseline commit or input hashes.
3. The files or artifacts produced.
4. The verification command and observed result.
5. Any blocker, uncertainty, or unverified claim.

Do not infer completion from a running process or an empty response.
