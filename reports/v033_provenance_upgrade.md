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

## 3. P0-2: `model_ready` is now enforced by the modelling pipeline (FIXED in v0.3.4)

**This was a live defect in v0.3.3. It is fixed in v0.3.4; the description
below is kept as the record of what was wrong.**

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
controlled benchmark**, including the reported paired delta of +0.0265 R2. That
was treated as a deliberate, separately reported decision, so v0.3.3 left it
alone.

**Resolution (v0.3.4).** `read_modelling_rows` now enforces `model_ready` and
returns the withheld rows explicitly; the accounting invariant counts them. VC
is withheld, the fitted set fell 237 -> 236, and the controlled PC/EC gain fell
from +0.0265 to **+0.0059** (95% CI -0.002 to +0.013, p = 0.11) -- the earlier
value was carried by the withheld row, which is a structural analogue of the two
added carbonates. The guard
`test_only_known_non_model_ready_rows_reach_the_modelling_feature_file` now also
asserts that the gate withholds exactly the pinned offender set. See
`reports/v034_model_ready_gate.md`.

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
ThermoML primary values. A later pass renamed that label to
`primary_vs_duncan2013_reported_value_differs` once the cited original table had
been retrieved; see section 8. FEC and VC record the ECW cross-check in `notes` only,
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
  output sha256 `2cd58144deac6b3b4b88045de7f53564f1a9c95ff3cc9c06707d776f43e42a1b`
  after the citation-trace round in section 8 (previously
  `88f0a1a609b4c462db51a507f72e2909a1a28de8eb4e887c936adaa6f74a7a33`);
  superseded in v0.3.5, which re-pins it to `b99327766b7b7f7369f7a55bbb1067508fe138e0c344f25c9cffbdf205a2d74f` after the
  3-methoxypropionitrile provenance patch (see `reports/decisions_log.md`).
- Frozen hash re-pinned in `tests/test_build_dielectric_v03.py`.
- Raw fetch caches for the tier 0-3 passes live in `data/external/g1plus/`, which is
  git-ignored: it contains the text extraction of a closed-access publisher
  supplement and the tests / verifier must not depend on it. Re-run the collectors to
  regenerate it; the committed evidence is `probes/g1plus_*.json` plus these reports.

## 7. Open items

1. ~~**P0-2 above** - `model_ready` is not enforced; VC is trained on.~~ Fixed in
   v0.3.4: the gate withholds it and the controlled benchmark was re-run
   (+0.0265 -> +0.0059).
2. FEC keeps an unresolved 78.4/102/107 conflict; ECW-308 now supports the low
   branch but the row stays out of the model.
3. Tier 4 (Reaxys / SciFinder-n / DIPPR 801) is still unchecked; it is the most
   likely route to a primary MOPN value.
4. The DC-200 dataset remains unpublished in an accessible location.
5. `reports/v032_veto_resolution.md` still describes v0.3.2 as a strict
   byte-identical superset of v0.3.1. That remains true for v0.3.2; v0.3.3
   supersedes it at the level of the modelling projection, not bytes.

## 8. Citation-trace escalation (2026-09-24)

The tier-2 pass recorded what ECW-308 prints; this pass recorded what the
documents ECW-308 cites actually are. Method and per-compound evidence are in
`reports/g1plus_citation_trace_findings.md` and
`probes/g1plus_citation_trace_evidence.json`.

Four results changed the dataset's provenance layer:

1. **Duncan et al. 2013 was retrieved legally.** The NRC Publications Archive
   accepted manuscript (record `431ad01c-3fb7-4610-923b-99d08c6a4c16`) was read
   in full. Its Table I on p. A840 reports adiponitrile as `30` and
   glutaronitrile as `37` - integers, not `30.00` and `37.00`. The two decimals
   in ECW-308 are therefore ECW's own extension and are unsupported precision.
   The paper states that dielectric constants were measured with a Brookhaven
   BI-870 meter, but Table I has no per-row provenance and no temperature,
   frequency or uncertainty, so the rows are **not** promoted to primary and
   their stored ThermoML values are **not** replaced or averaged.
2. **The nitrile conflict label names the real counterpart.**
   `primary_vs_ecw308_compilation_differs` became
   `primary_vs_duncan2013_reported_value_differs`, and `10.1149/2.088306jes`
   joined their `source_dois_all` because the document is legally held.
3. **Vinylene carbonate has a named primary measurement source.** ECW-308
   citation [3] is Hall et al. 2018 (CC BY 4.0), whose Table I reports VC as
   `126` and attributes it to Saadi & Lee, *J. Chem. Soc. B* 1966, 5-6,
   DOI `10.1039/j29660000005`. That paper's abstract states that the dielectric
   constant and dipole moment of vinylene carbonate were measured, so the
   previous note claiming that no primary measurement had been found was wrong
   and has been corrected. The numeric value could not be read, so VC stays
   `conflict_open` and is still not promoted to primary.
4. **EC's class assignment is confirmed by a closed loop.** Hall et al. 2018
   Table I lists EC as `90.5` citing ref 78, DOI `10.1021/je050341y` - the same
   source this repository already uses - and footnotes that EC permittivity is
   quoted at 40 C. This corroborates the 313.15 K assignment rather than adding
   an independent measurement.

Two further independent relays were recorded in `notes` without changing any
value: Hall et al. 2018 gives PC as `64.9` (a 1972 measurement, DOI
`10.1021/j100664a019`), methyl propionate as `6.07`, and FEC as `107` (citing
the Ue et al. 2014 book chapter, DOI `10.1007/978-1-4939-0302-3_2`), which
supports the high endpoint of the unresolved 78.4/102/107 FEC spread.

Hall et al. 2018 is CC BY 4.0 and therefore redistributable, but it was still
recorded in `notes` rather than added to VC's `source_dois_all`: a dataset row
carries a single licence metadata set, and VC's row already carries the
CC BY-NC 4.0 metadata of its retained review source. The source-licence gate
would reject a second, differently licensed DOI on the same row. This is a
structural limitation of the current schema, not a licensing objection.

Effect on the shipped artifacts: 30 provenance patches (13 rewritten in place),
246 rows, `source_dois_all` changed on 2 rows, `conflict_status` on 2 rows,
`notes` on 9 rows, and **no change to `dielectric`, `T_K`, `model_ready`,
`temperature_band` or `dataset_origin`**. The controlled benchmark is therefore
untouched by this round.

Verification after the round: `pytest -q` **490 passed**, Ruff clean,
`verify_week1.py` 15/15, `verify_dielectric_v02.py` 9/9,
`verify_dielectric_v03.py` 7/7 (246 rows, 36 additions),
`verify_dielectric_v032.py` 7/7, and
`check_paper_artifact_consistency.py` reports that the paper drafts agree with
the frozen artifacts. Frozen hashes re-pinned: dataset
`2cd58144deac6b3b4b88045de7f53564f1a9c95ff3cc9c06707d776f43e42a1b` (superseded in v0.3.5 by `b99327766b7b7f7369f7a55bbb1067508fe138e0c344f25c9cffbdf205a2d74f`), patches
`76070535fb51eb64f50facc7501f617f052e26feda775dc7b2c40c776bae3a47`.

Open items after this round: the Saadi & Lee 1966 two-page full text is still
needed to read the actual VC number, and Deng et al. 2020 (FEC) and Perricone
et al. 2013 (MOPN) remain closed. Tier 3 and Tier 4 access judgements live in
`reports/g1plus_tier34_access_findings.md`.
