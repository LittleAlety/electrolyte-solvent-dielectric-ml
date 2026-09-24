# G1 Data Gate Review: Conflict List & Provenance Changes

> Updated 2026-09-24: v0.3.2 revision with PC & EC addition.
> Updated 2026-09-24 (v0.3.3): G1+ tiers 0-3 executed; MOPN gap row added;
> provenance made reproducible. Details: `reports/v033_provenance_upgrade.md`.
> All findings from Week 7-8 G1+ source-priority pass.

## 1. New Additions (v0.3.2)

| Compound | Value | T/K | Source | Evidence | Status |
|---|---|---|---|---|---|
| **Propylene carbonate (PC)** | 64.9 | 298.15 | Simeral & Amey (1970) J. Phys. Chem. 74, 1443; DOI 10.1021/j100702a008 | Primary experimental (critical compilation) | **added, model_ready=true** |
| **Ethylene carbonate (EC)** | 90.5 | 313.15 | Chernyak (2006) J. Chem. Eng. Data 51, 416; DOI 10.1021/je050341y | Primary experimental | **added, model_ready=true, extended_temperature** |

*Note: EC mp~36.4°C; measured at 40°C (313.15K) in liquid state; flagged as extended_temperature band.*

## 2. New Conflict Exclusions

| Compound | Value | Conflict Interval | Current Status | Action | Reason |
|---|---|---|---|---|---|
| Vinylene carbonate (VC) | 126 | 78-127 | model_ready=true, open_access_article_text | **model_ready -> false** | Extreme high value; Knovel compilation conflicts; mp~22°C, 298K near melting |
| Methyl propionate | 6.2 | 5.5-6.2 | open_access_review_table | **open conflict** | NBS 514 has eps=5.5 vs review 6.2, ~13% difference |

## 3. Provenance Promotions

| Compound | Current evidence | New evidence | Match |
|---|---|---|---|
| Ethoxybenzene | open_access_review_table | **promoted to primary** | NBS p35:011 eps=4.22 matches Cui (2026) 4.2, ~0.5% |

## 4. Compounds Previously Flagged as Absent — Now Found

These compounds were listed as "known gaps" in G1 report v1 but their IUPAC/systematic names already existed in v0.3:

| Common Name | IUPAC Name (in dataset) | ε @ 298K | InChIKey |
|---|---|---|---|
| **Diglyme** | 2,5,8-trioxanonane | 7.3815 | SBZXBUIDTXKZTM |
| **Triglyme** | 2,5,8,11-tetraoxadodecane | 7.604 | YFNKIDBQEZZDLK |
| **Tetraglyme** | 2,5,8,11,14-pentaoxapentadecane | 7.798 | ZUHZGEOKBKGPSW |
| **Adiponitrile** | hexanedinitrile | 32.12 | BTGRAWJCKBQKAO |
| **Glutaronitrile** | pentanedinitrile | 34.60 | ZTOMUSMDRMJOTH |

*All sourced from ThermoML; the dinitriles use DOI 10.1021/je300958c, and each glyme's exact zero-frequency datasets are recorded in the v0.3.3 provenance notes. ECW-308 cross-checks are recorded separately.*

## 5. Remaining Known Gaps (for paper Limitations)

| Compound | CAS | Status | Evidence |
|---|---|---|---|
| Methoxypropionitrile | 110-67-8 | **Recorded, held out of the model** | v0.3.3 adds `36.0 @ 298.15 K` from the ECW-308 supplement (Table S3), which cites Perricone et al. 2013, `10.1016/j.electacta.2013.01.084`. That primary paper is closed access and unreachable, and no second source exists, so the row is `secondary_compilation_unverified`, `model_ready=false`, `conflict_status=awaiting_primary_confirmation`. |
| FEC | 114435-02-8 | **Primary 78.4 landed in v0.3.12; still held out** | The previously stored 102 was the flash point, not a permittivity. v0.3.12 promoted the 78.4 primary measurement (Kobayashi et al. 2003, Table 2, 296.15 K, `Our data`) to the stored value; the competing 107 claim (Ue et al. 2014 Table 2.3 read through Hall 2018; Hagiyama 2008 blocked) is still unread, so the row stays `model_ready=false` |
| THF/NMP/DCM | Various | **Resolved (no upgrade possible)** | These three are in the dataset from **open-access review tables**, not NBS 514: direct checks of NBS Circular 514 found no THF or NMP entry. SpringerMaterials holds restricted THF/NMP records that agree with the open values (NMP 32.16/32.17 K records vs review 32.2), but that source is non-redistributable and was used only as a cross-check. The review-table provenance is therefore retained deliberately, not left un-upgraded by neglect. |

## 6. Progress Summary

| Gate | Status | Evidence |
|---|---|---|
| G1a: PC VETO | **RESOLVED** | Added ε=64.9@298K from Simeral & Amey (DOI 10.1021/j100702a008) |
| G1b: EC | **RESOLVED** | Added ε=90.5@313K from Chernyak (DOI 10.1021/je050341y) |
| G1c: Glymes | **RESOLVED** | Already in dataset under IUPAC names |
| G1d: Adiponitrile/Glutaronitrile | **RESOLVED** | Already in dataset |
| G1e: VC conflict | **Confirmed** | model_ready=false |
| G1f: Applicability domain | **FIXED** | Structural HBD≥1 (`[O,S,N;!H0]`); Onsager variant measured and rejected (0/150 coverage of ε>60) |
| G1g: v1.0 premature tag | **DELETED** | Local + remote deleted |
| G1h: reproducible provenance | **RESOLVED (v0.3.3)** | 4 hand-edited rows absorbed into a 19-patch checked-in layer; verifier now applies it |
| G1i: `model_ready` is advisory only | **FIXED (v0.3.4)** | `read_modelling_rows` now withholds every row whose dataset record is not `model_ready=true` and returns those rows explicitly; the accounting invariant counts them. Vinylene carbonate is withheld, the fitted set fell 237 -> 236, and the controlled PC/EC gain fell from +0.0265 to +0.0059 (p = 0.11). See `reports/v034_model_ready_gate.md`. |
