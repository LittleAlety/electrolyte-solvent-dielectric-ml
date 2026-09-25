# Electrolyte Solvent Dielectric ML

An auditable, machine-learning-ready dataset of static dielectric constants
(relative permittivities) for **246 pure organic liquids** at near-room
temperature, together with the frozen benchmark and the verifiers that recompute
every reported number.

**Release:** v1.0 (GitHub release 2026-09-25) · **Dataset:** v0.3.3 ·
**DOI:** https://doi.org/10.5281/zenodo.22957696 (concept DOI
https://doi.org/10.5281/zenodo.22957695) ·
**Licences:** data CC BY 4.0 (`LICENSE-DATA.md`), code MIT (`LICENSE`)

## What is here

| Path | What it holds |
| --- | --- |
| `data/dielectric_v03.csv` | the canonical dataset: 246 rows x 38 columns, digest `ff2142936e06e04b329b70f8597574f75349e54ce876e9fff81309e6d35ccce4` |
| `paper/full_draft.md` | the data descriptor, generated from the five section files |
| `paper/release_notes_v1.0.md` | what this release contains and what it admits to |
| `probes/` | every probe behind every number and figure |
| `probes/artifacts/` | the six paper figures and their pinned summaries |
| `scripts/` | build scripts and the verifiers listed below |
| `reports/` | decision log, source audits, adversarial review rounds |
| `docs/` | week-by-week build notes and schemas |

## Reproduce

```powershell
conda env create -f environment.yml
conda activate electrolyte-ml

python scripts/verify_dielectric_v03.py             # 7/7 checks on the canonical dataset
python scripts/verify_v032_benchmarks.py            # the frozen benchmark
python scripts/verify_paper_figures.py              # six figures, each pinned to its script
python scripts/check_paper_artifact_consistency.py  # manuscript vs frozen artefacts
python scripts/build_paper_full_draft.py --check    # the draft is regenerated, not hand-edited
python -m pytest -q                                 # 868 passed at v1.0
```

## What the release is honest about

The dataset ships with its negative results and its boundaries rather than around
them:

- **three model boundaries, quantified.** An association blind spot (structural
  hydrogen-bond-donor rule), scaffold extrapolation (best R2 0.276 +/- 0.044), and
  a polar-aprotic high-permittivity gap (PC predicted 21.6 against 64.9; EC 33.7
  against 90.5).
- **negative results retained.** A ranking head at Spearman 0.884 with
  R2 -0.172 that does not recover under pre-registered calibration (-0.309); a
  density feature worth -0.001 R2; an added-carbonate gain indistinguishable from
  zero (p = 0.11); a conformal interval whose marginal coverage holds (0.915)
  while its high-permittivity stratum collapses to 1.5-26%.
- **conflicts recorded, never averaged.** FEC keeps both legs (78.4 at 296.15 K,
  and 107 read at compilation level); VC keeps the Knovel range beside the primary
  value; MOPN is flagged as a secondary compilation. Six rows carry
  `model_ready=false`.
- **access-blocked is not "absent".** Restricted sources are recorded as
  access-blocked rather than as missing, and four boundary compounds (3 ionic
  liquids plus Fe(CO)5) are explicitly `out_of_scope_ionic_or_organometallic`
  instead of silently dropped.

## Scope

- Reproducible Python environment for RDKit, scikit-learn, XGBoost, pandas and
  matplotlib.
- ThermoML acquisition and parsing, NBS Circular 514 reconciliation, and
  open-access primary-source audits for modern battery solvents.
- The frozen 236-row benchmark, its ablation, applicability-domain and conformal
  diagnostics, and the six-figure manuscript.
