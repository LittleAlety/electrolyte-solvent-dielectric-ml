# v0.3.3 - Reproducible provenance upgrade

Date: 2026-09-24
Base: v0.3.2 (`data/dielectric_v032.csv`, sha256 `39d15e161a4f...b30be`)

## 1. What v0.3.3 is

v0.3.3 is a **provenance revision**, not a modelling revision. It closes the
G1+ source-priority backlog and makes every provenance edit reproducible from
checked-in inputs.

| quantity | v0.3.2 | v0.3.3 |
|---|---|---|
| dataset rows | 245 | **246** |
| `model_ready == true` rows | 240 | **240 (unchanged)** |
| v0.3 additions | 35 | 36 |
| model-ready additions | 31 | 31 |
| additions carrying `conflict_status` | 5 | 6 |
| provenance patches | 0 | **30** |
| `data/dielectric_v03.csv` sha256 | `39d15e16...b30be` | **`88f0a1a6...a7a33`** |

Because the model-ready set is byte-identical, **every controlled benchmark
number derived for v0.3.2 still applies to v0.3.3**. That is enforced by
`test_existing_model_ready_observations_are_stable_from_v032_to_v03` and
`test_shipped_patches_are_metadata_only`.

## 2. P0-1: provenance edits were not reproducible (closed)

The v0.3.2 revision restored four rows by **hand-editing the frozen CSV**:
propylene carbonate, ethoxybenzene, methyl propionate and vinylene carbonate.
Those edits lived only in the artifact, so any rebuild silently dropped them.
This is the same failure mode the revision notes describe as "the rebuild that
added PC and EC also reverted three existing rows".

Evidence: rebuilding v0.3.2 inputs without patches produced 12 field-level
differences against the frozen CSV, in `evidence_level` (3), `notes` (11),
`source_dois_all` (3) and `temperature_source` (1).

Fix: all four rows were absorbed into the checked-in patch file
`data/processed/dielectric_v03_provenance_patches.csv` (30 patches, 15 compounds).
`apply_provenance_patches` rejects unknown compounds, protected fields
(`inchikey`, `name`, `smiles`, `dielectric`, `T_K`, `temperature_band`,
`model_ready`, `dataset_origin`) and duplicate `(inchikey, field)` pairs, and
records `previous_value` + `rationale` for every patch.

`scripts/verify_dielectric_v03.py` now applies the patch file too, so the
independent verifier reproduces the shipped artifact instead of a patched-out
variant.

**Corrupted note repaired.** The vinylene carbonate note restored in v0.3.2 was
stored as unreadable replacement characters
(`"??????????(Knovel Critical Tables????);????78-127..."`). No readable version
exists anywhere in git history (the note is empty before commit `8f3fdf6` and
mojibake after). It has been rewritten from the evidence actually collected,
and `test_shipped_patch_file_is_complete_and_auditable` now rejects runs of
`????` in any patch value.

## 3. P0-2: `model_ready` is not enforced by the modelling pipeline (open)

**This is a live defect and it is not fixed by v0.3.3.**

`probes/dielectric_representation_ablation.py::read_modelling_rows` filters only
on `status != "error"`. Nothing in the modelling path reads `model_ready`; the
only gate is `data/processed/dielectric_v03_exclusions.csv` (4 rows).

Consequence: **vinylene carbonate is trained on** even though v0.3.2 marked it
`model_ready=false` / `conflict_open` on the grounds that 126 is an extreme
value and contested (78-127).

Evidence (v0.3.2 predictions):

```
features rows 241, usable 237, prediction keys 237
rows in modelling set with model_ready != true: 1
  VAYTZRYEBVHVLE-UHFFFAOYSA-N | vinylene carbonate
  model_ready=false | conflict=conflict_open | eps=126 | in_predictions=True
```

Fixing the wiring removes VC from the modelling set and therefore **changes the
controlled benchmark**, including the reported paired delta of +0.0265 R2.
That is a deliberate, separately reported decision, so v0.3.3 deliberately
leaves it alone. It is now guarded:
`test_only_known_non_model_ready_rows_reach_the_modelling_feature_file` pins the
current offender set, so the mismatch cannot grow silently, and any future fix
fails loudly and forces the guard to be updated.

Recommended follow-up: either enforce `model_ready` in `read_modelling_rows` or
move VC into the exclusions file, then re-run the controlled comparison.

## 4. G1+ evidence: tiers 0-3

Request budgets were respected: tier 1 = 40, tier 2 = 39, tier 3 = 39, each
logged per request.

### Tier 0 - local ThermoML (242/242 parsed) and NBS Circular 514 (636 rows)

Upgraded to named primary provenance:

| compound | value | source |
|---|---|---|
| adiponitrile | 32.12 +/- 0.1 @ 298.15 K | `10.1021/je300958c` dataset 3 |
| glutaronitrile | 34.6 +/- 0.1 @ 298.15 K | `10.1021/je300958c` dataset 2 |

Recorded as critical compilations (arithmetic mean of two agreeing zero-frequency
primary observations, never averaged silently):

| compound | stored | components |
|---|---|---|
| diglyme | 7.3815 | 7.363 +/- 0.147 (`10.1016/j.jct.2008.09.006`) + 7.4 +/- 0.15 (`10.1016/j.jct.2010.09.008`) |
| triglyme | 7.604 | 7.578 +/- 0.152 (`10.1016/j.jct.2008.02.015`) + 7.63 +/- 0.15 (`10.1016/j.jct.2010.09.008`) |
| tetraglyme | 7.798 | 7.78 +/- 0.16 (`10.1016/j.jct.2010.09.008`) + 7.816 +/- 0.469 (`10.1016/j.tca.2012.10.024`) |

Dichloromethane keeps its 298.15 K review value 9.1 and is now cross-checked
against NBS Circular 514 `eps=9.08 @ 293.15 K` (p13 row 008). The two agree to
rounding and were **not** averaged.

Refuted claims:

- "triglyme only has 318.15/328.15 K data" is **false**; two zero-frequency
  pure-component observations at 298.15 K exist.
- THF and NMP are **not** in NBS Circular 514. Their open-access values are
  retained deliberately and the restricted SpringerMaterials records are used
  only as non-redistributable cross-checks.
- The archival file `ThermoML.v2020-09-30.tgz` is corrupt (no gzip magic,
  SHA256 does not match the pin) and contributed no evidence.

### Tier 1 - PubChem, NIST WebBook, Chodera: the premise was falsified

PubChem does **not** carry structured permittivity data. For all 10 targets the
`Dielectric Constant` heading returned HTTP 404, the Experimental Properties
payloads contained zero dielectric/permittivity hits, and the control compounds
water (CID 962) and acetonitrile (CID 6342) were also 404. PC/EC/diglyme pages do
cite Riddick 4th ed., but for solubility, not permittivity. NIST WebBook had no
dielectric field for any target (FEC's registry number does not exist).
Chodera matched diglyme only, at `extracted_dataset` grade.

### Tier 2 - ECW-308 (Wang et al. 2023, `10.1002/adfm.202212342`)

The publisher supplement was retrieved through the browser (all curl paths are
Cloudflare 403). Table S3 column semantics were derived independently twice:
against DMF (37.00), DMA (38.00) and ACN (37.00), and against a shift test that
rules out the neighbouring viscosity/conductivity/flash columns.

Cross-checks against the frozen dataset (compilation vs. primary, never averaged):

| compound | stored | ECW-308 @ 25 C | note |
|---|---|---|---|
| PC | 64.9 | 64.90 | exact reproduction |
| VC | 126 | 126.00 | independently reproduces the contested high value |
| FEC | 78.4/102/107 conflict | 78.40 | supports the low branch; conflict stays open |
| diglyme | 7.3815 | 7.40 | +0.25% |
| triglyme | 7.604 | 7.53 | -0.97% |
| tetraglyme | 7.798 | not present | no third-party check |
| adiponitrile | 32.12 (primary) | 30.00 | -6.6% compilation disagreement |
| glutaronitrile | 34.60 (primary) | 37.00 | +6.9% compilation disagreement |
| EC | 90.5 @ 313.15 K | 89.00 @ 25 C | different temperature, not comparable |

Follow-up provenance integration: the G1+ tier-2 pass now records the ECW-308
value, SI page, and reference for diglyme, triglyme, PC, EC, FEC, adiponitrile,
and glutaronitrile. The two nitrile rows carry
`conflict_status=primary_vs_ecw308_compilation_differs` while retaining their
ThermoML primary values. FEC and VC record the ECW cross-check in `notes` only,
because both are review-licensed rows and the closed-license ECW DOI cannot be
added to their `source_dois_all` without violating the source-license gate.


The DC-200 dataset could not be obtained: the ACS Nano SI contains no
per-molecule table, the author GitHub tree has no DC-200 asset, and the Zenodo
record describes only fine-tuning results. All `dc200` fields are `found=false`
- "asset not published", not "compound not found".

### Tier 3 - is the MOPN value primary?

**No.** Crossref confirms the cited paper: Perricone et al., *Electrochim.
Acta* 2013, **93**, 1-7, DOI `10.1016/j.electacta.2013.01.084`, "Investigation of
methoxypropionitrile as co-solvent for ethylene carbonate based electrolyte in
supercapacitors". The paper is closed access, no open full text exists
(OpenAlex / Unpaywall / OpenAIRE / Semantic Scholar), ScienceDirect was
unreachable, the Elsevier API returned HTTP 429, and no second independent
source for the MOPN permittivity was found.

Therefore 36.0 can only be labelled `secondary_compilation_unverified`.

## 5. MOPN row added, deliberately not model-ready

`3-methoxypropionitrile` (InChIKey `OOWFYDWAMOKVSF-UHFFFAOYSA-N`) is now row 246:

| field | value |
|---|---|
| dielectric | 36.0 |
| T_K | 298.15 |
| evidence_level | `secondary_compilation_unverified` |
| model_ready | `false` |
| conflict_status | `awaiting_primary_confirmation` |
| source_doi | `10.1016/j.electacta.2013.01.084` |
| source_dois_all | `10.1016/j.electacta.2013.01.084;10.1002/adfm.202212342` |
| source_quality | `secondary_compilation_publisher_si` |

The row carries **no CC licence claim** - its only access path is a non-CC
publisher supplement - and no `source_license` / `license_url` /
`redistribution_conditions` values. This is asserted by
`test_mopn_secondary_compilation_row_claims_no_open_licence`.

MOPN has **no row** in `data/processed/dielectric_physical_features_v03.csv`, so
it cannot reach the model even by accident. Promoting it requires a verified
primary value, an xTB feature row and a re-run of the controlled benchmark.

## 6. Verification

- `pytest -q`: **490 passed** after the G1+ tier-2 provenance integration
  (the first v0.3.3 provenance round was 481).
- `ruff check scripts src probes tests`: clean.
- `scripts/verify_dielectric_v03.py`: **7/7 checks pass**, 246 rows, 36 additions,
  output sha256 `88f0a1a609b4c462db51a507f72e2909a1a28de8eb4e887c936adaa6f74a7a33`.
- Frozen hash re-pinned in `tests/test_build_dielectric_v03.py`.
- Raw fetch caches for the tier 0-3 passes live in `data/external/g1plus/`, which is
  git-ignored: it contains the text extraction of a closed-access publisher
  supplement and the tests / verifier must not depend on it. Re-run the collectors to
  regenerate it; the committed evidence is `probes/g1plus_*.json` plus these reports.

## 7. Open items

1. **P0-2 above** - `model_ready` is not enforced; VC is trained on. Fixing it
   invalidates the +0.0265 controlled benchmark and needs its own report.
2. FEC keeps an unresolved 78.4/102/107 conflict; ECW-308 now supports the low
   branch but the row stays out of the model.
3. Tier 4 (Reaxys / SciFinder-n / DIPPR 801) is still unchecked; it is the most
   likely route to a primary MOPN value.
4. The DC-200 dataset remains unpublished in an accessible location.
5. `reports/v032_veto_resolution.md` still describes v0.3.2 as a strict
   byte-identical superset of v0.3.1. That remains true for v0.3.2; v0.3.3
   supersedes it at the level of the modelling projection, not bytes.
