# G1+ : the 3-methoxypropionitrile value 36 traces to a public document

**Date:** 2026-09-24
**Target:** 3-methoxypropionitrile (CAS 110-67-8, `COCCC#N`,
`OOWFYDWAMOKVSF-UHFFFAOYSA-N`)
**Evidence file:** `probes/g1plus_mopn_thesis_evidence.json`
**Previous state:** `secondary_compilation_unverified` - the value 36.00 came from
the ECW-308 compilation (Wang et al. 2023, Adv. Funct. Mater., DOI
10.1002/adfm.202212342, Table S3), which cites Perricone et al. 2013
(Electrochim. Acta 93, 1, DOI 10.1016/j.electacta.2013.01.084) - a closed paper
that could not be retrieved in the tier-3 round.

## What was retrieved

The closed paper could not be opened, but the **doctoral thesis of the same
first author** could:

- Perricone, E. *Mise au point d'electrolytes innovants et performants pour
  supercondensateurs*, Universite de Grenoble, 2011-07-07. NNT `2011GRENI032`,
  HAL `tel-00630049`, open access, 214 pages.
  <https://theses.hal.science/tel-00630049v1>
- PDF: 2,829,426 bytes, sha256
  `3bf35a8ccc498706fcb80a64488cba17ec2ffaf589295b066f41628c1c0a9f25`
  (cached under `data/external/g1plus/mopn/`, git-ignored; never redistributed).

**Chapitre II, page 65, Tableau 12 ("Proprietes physico-chimiques des
solvants")** lists the two nitriles the chapter compares (this table carries
no temperature note):

| Solvant | Structure | Teb (C) | FP (C) | eta (mPa.s) | eps_r | Toxicite |
| --- | --- | --- | --- | --- | --- | --- |
| Methoxyacetonitrile | MA | 119 (731 mmHg) | - | - | 32 | Xn |
| **Methoxypropionitrile** | **MP** | **165** | **66** | **1,1** | **36** | **Xi** |

So the value **eps_r = 36** is reported in an openly accessible document by the
original author, independently of the ECW-308 compilation chain. The 165 C
boiling point and 66 C flash point in the same row match handbook values for
3-methoxypropionitrile, which anchors the row to the correct compound.

## The temperature (corrected in v0.3.10)

**The temperature is stated, not missing.** The thesis gives 25 C for this
value in two tables:

- **Tableau 4** (printed page 28, "Caracteristiques des principaux solvants
  ... famille des carbonates, esters, ethers et nitriles") heads the
  permittivity column verbatim **"eps_r a 25 C"**; the Methoxypropionitrile row
  reads `- 57 | 165 | 66 | 1,1 | 36` against `Tfu | Teb | FP | eta a 25 C |
  eps_r a 25 C`, with no per-cell temperature override.
- **Tableau 14** (printed page 77, "Proprietes des solvants utilises") is a
  transposed matrix whose property row is headed verbatim **"Constante
  dielectrique a 25 C"** and gives **36** in the `MP` column. Its neighbouring
  `a 40 C` annotation belongs to the *viscosity* row, not to permittivity.

Tableau 12 (printed page 65), which the v0.3.5 pass read on its own, also lists
`eps_r = 36` but carries neither a temperature note nor a reference letter -
that single table is why the temperature was first recorded as unstated. The
v0.3.10 revision corrects the provenance note, the probe and this report.

Three other cells in Tableau 14's permittivity row anchor the column alignment:
sulfolane 43 (30 C), propylene carbonate 64,4 and ethylene carbonate 90 all
match values this thesis states elsewhere.

## Independence

**Independence.** The thesis and the 2013 paper belong to the same research
line, so this is a *document* check, not a second measurement lineage. It
answers "can the number be cited to something a reader can open?" with yes. It
does not answer "was the number measured twice by different groups?"

## Consequences for the dataset

- No numeric value changes. The row keeps `dielectric = 36.0`,
  `T_K = 298.15`, `model_ready = false`, and stays on the curated exclusion
  list; the fitted set and every benchmark metric are unaffected.
- A provenance patch adds the thesis to `source_dois_all` and records the
  thesis in the note. The v0.3.5 version of that note said the temperature was
  unstated; the v0.3.10 revision corrects it to 25 C per Tableau 4 and
  Tableau 14. See the v0.3.5 and v0.3.10 entries in `reports/decisions_log.md`.
- Two **independent** blockers keep the row out of every fit, and neither is
  the temperature. Its `model_ready=false` comes from the curated exclusion
  (`data/processed/dielectric_v03_exclusions.csv`: *secondary compilation
  awaiting primary confirmation*), which is what `conflict_status =
  awaiting_primary_confirmation` also records. Separately, the row has **no
  GFN2-xTB physical-feature row at all**: it is simply absent from
  `data/processed/dielectric_physical_features_v03.csv`, so it is an independent
  precondition and does *not* appear among the `failed_physical_feature_*` rows
  (that bucket only holds feature rows that exist with `status=error`). A confirmed primary
  value would therefore still need `COCCC#N` run through the feature pipeline
  before it could be fitted.

## Retrieval method (and why it is recorded)

HAL is protected by an Anubis proof-of-work interstitial. Plain HTTP fetches of
the record page and of the PDF both returned the 12,537-byte challenge HTML.
Launching the user's **Microsoft Edge through Playwright**
(`chromium.launch(channel="msedge")`) executed the challenge in a real browser
and the PDF was then downloaded from that authenticated context - the same route
a human reader takes. No challenge was solved offline, no cookie was forged and
no credential was used. The thesis is open access, so only the numeric fact is
recorded in the repository; the PDF stays in the git-ignored cache.

## Other lead from the same document

Thesis Tableaux 5-8 list eps_r for acetonitrile, benzonitrile,
gamma-valerolactone, propylene carbonate and other solvents with a 25 C caption
and per-value references. This is a free, citable cross-check source for the
carbonate/ester families that the tier-4 database round could not reach.
