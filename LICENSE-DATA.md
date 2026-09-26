# Data licence: CC BY 4.0

The dataset files in this repository — `data/**` and the probe outputs derived
from them under `probes/**` — are licensed under the Creative Commons
Attribution 4.0 International licence (CC BY 4.0).

Full legal text: https://creativecommons.org/licenses/by/4.0/legalcode

Per-row provenance is part of the dataset: `source_license`,
`redistribution_status` and `redistribution_conditions` in
`data/dielectric_v03.csv` record the upstream licence and redistribution status
of every value. Values that came from sources which do not permit
redistribution are not shipped; they are recorded as access-blocked instead.

# Upstream sources named explicitly

Most shipped values carry their own `source_license` / `redistribution_status`
columns. The aggregated layers below additionally redistribute derived values
from an upstream dataset that requires attribution, so the credit lives here.

- **PubChemQC B3LYP/6-31G*//PM6** - `data/processed/orbital_second_source_layer.csv`
  (Week 17, arm W17-12). Electronic properties of 85,938,443 molecules.
  (c) NAKATA Maho and contributors, licensed **CC BY 4.0**.
  Citation: M. Nakata et al., J. Chem. Inf. Model. (2023),
  DOI 10.1021/acs.jcim.3c00899. Distributor: `molssiai-hub/pubchemqc-b3lyp`
  (revision 15c15ae6a80c7ed84ee45e966390564e71e2e0bf), shard
  `data/b3lyp_pm6/train/000000001-000253696.json`.
  The upstream shard is **not** redistributed here; only per-molecule orbital
  energies with explicit provenance are shipped, and every derived row keeps
  the `source_dataset`, `source_level` and `source_license` columns intact.

## Licence carve-out: one file is CC BY-NC 4.0, not CC BY 4.0

Every other file under `data/**` and `probes/**` is CC BY 4.0 as stated above.
**`data/processed/themol_orbital_layer.csv` is the single exception** and it is
**not** CC BY 4.0.

- **THEMol** - `data/processed/themol_orbital_layer.csv` (Week 17, arm W17-14).
  The upstream dataset is ByteDance-Seed/THEMol (arXiv 2605.14973), whose code is
  Apache-2.0 but whose **data is licensed CC BY-NC 4.0**. This arm reads only the
  Hessian-subset geometries over HTTP range requests, runs GFN2-xTB single points
  on them, and ships the resulting orbital energies as a derived layer. Because
  the geometry is the input to that derivation, the layer inherits the
  **non-commercial** restriction.

  Consequence, stated plainly: **this one file may not be used commercially and
  may not be relicensed as CC BY 4.0.** It is additive - it never rewrites the
  Batt-P30K columns in `four_core_key_registry.csv` or the PubChemQC columns in
  `orbital_second_source_layer.csv`, both of which stay CC BY 4.0 as before. A
  downstream consumer that needs a purely CC BY 4.0 bundle can drop this single
  file without touching any other artifact.

  Attribution: THEMol, ByteDance Seed. Every row keeps `source_dataset`,
  `source_level` and `source_license` populated, and the probe-side licence note
  is repeated in `reports/themol_orbital_layer.md` section 5. The raw harvest
  under `data/raw/themol/` is git-ignored and is not redistributed here.