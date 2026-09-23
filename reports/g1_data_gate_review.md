# G1 Data Gate Review: Conflict List & Provenance Changes

> Updated 2026-09-24: v0.3.2 revision with PC & EC addition.
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
| **Diglyme** | 2,5,8-trioxanonane | 7.38 | SBZXBUIDTXKZTM |
| **Triglyme** | 2,5,8,11-tetraoxadodecane | 7.60 | YFNKIDBQEZHQBU |
| **Tetraglyme** | 2,5,8,11,14-pentaoxapentadecane | 7.80 | LNWVAMHESCFODF |
| **Adiponitrile** | hexanedinitrile | 32.12 | BTGRAWJCKBQKAO |
| **Glutaronitrile** | pentanedinitrile | 34.60 | ZTOMUSMDRMJOTH |

*All sourced from ThermoML (DOI: 10.1021/je300958c for dinitriles; DOIs for glymes scattered across J. Chem. Thermodyn. 2004-2010).*

## 5. Remaining Known Gaps (for paper Limitations)

| Compound | CAS | Status | Evidence |
|---|---|---|---|
| Methoxypropionitrile | 110-67-8 | **Absent** | ThermoML XML mentions but no permittivity data |
| FEC | 114435-16-8 | **Conflict open** | Three conflicting values (78.4/102/107), no traceable source |
| THF/NMP/DCM | Various | **Resolved** | Already in dataset via NBS 514; no upgrade needed |

## 6. Progress Summary

| Gate | Status | Evidence |
|---|---|---|
| G1a: PC VETO | **RESOLVED** | Added ε=64.9@298K from Simeral & Amey (DOI 10.1021/j100702a008) |
| G1b: EC | **RESOLVED** | Added ε=90.5@313K from Chernyak (DOI 10.1021/je050341y) |
| G1c: Glymes | **RESOLVED** | Already in dataset under IUPAC names |
| G1d: Adiponitrile/Glutaronitrile | **RESOLVED** | Already in dataset |
| G1e: VC conflict | **Confirmed** | model_ready=false |
| G1f: Applicability domain | **FIXED** | Onsager-estimated ε > 60 + HBD≥1 |
| G1g: v1.0 premature tag | **DELETED** | Local + remote deleted |
