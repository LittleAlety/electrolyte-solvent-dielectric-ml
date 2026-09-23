# Modern Solvent Source Audit

## Promoted public additions

| Evidence group | Rows | Source | Use status |
|---|---:|---|---|
| Primary article | 6 nitriles | Helambe et al. (1995), `10.1007/BF02848094` | model-ready |
| Public-domain compilation | 4 NBS records | NBS Circular 514, `10.6028/nbs.circ.514` | model-ready |
| Open review table | EMC, methyl butyrate | `10.1002/smll.202504276`, Table 2 | model-ready with room-temperature assumption |
| Open review table | DOL, THF, GVL, methyl propionate, DFBn, NMP | `10.1016/j.isci.2026.115778`, Table 3 | model-ready with room-temperature assumption |
| Open review table | HFE, TTE, BTFE, TEP, TMP, FEC | `10.1039/d5sc06221g`, Table 1 | mixed; TEP/TMP/FEC conflict-excluded |
| Open article text | VC | `10.1002/cssc.202402091`, explicit 298 K | model-ready |
| Open review table | 2-MeTHF | `10.1002/smtd.202400183`, Table 1 | model-ready with room-temperature assumption |
| Open review table | ethoxybenzene and chlorinated diluents | `10.1002/adma.73388`, Table 1 | model-ready with room-temperature assumption |

## Conflict exclusions

- `FEC`: public review values span `78.4`, `102`, and `107`.
- `TEP`: public review values are `10` and `13`.
- `TMP`: public review values are `10` and `21.6`.
- `Ethyl isothiocyanate`: NBS gives `19.5` at `294.15 K`; the restricted
  SpringerMaterials cross-check gives `29.7` at `293.2 K`.

All four rows remain in source audit material but carry
`model_ready=false`. The numeric conflicts are not averaged.

## Interpretation limit

Most CC-BY review tables do not state an independent measurement temperature
for every solvent value. Such rows use `T_K=298.15 K` and the explicit
`review_table_standard_room_temperature` provenance flag. They are suitable
for the v0.3 coverage benchmark but should not be treated as independently
verified v1.0 training records until their primary sources are inspected.
