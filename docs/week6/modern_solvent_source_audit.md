# Modern Solvent Source Audit

## Promoted public additions

| Rows | Data source | Use status |
|---|---|---|
| 6 nitriles | Helambe et al. (1995), `10.1007/BF02848094` | primary/model-ready |
| 4 NBS records | NBS Circular 514, `10.6028/nbs.circ.514` | public domain/model-ready |
| EMC, methyl butyrate | Senthil et al. (2025), `10.1002/smll.202504276`, Table 2 | model-ready with room-temperature assumption |
| DOL, THF, GVL, NMP, TEP, TMP, FEC | Sun et al. (2026), `10.1016/j.isci.2026.115778`, Table 3 | TEP/TMP/FEC conflict-excluded; all values sourced from this table |
| methyl propionate, DFBn, HFE, TTE, BTFE | Karbak et al. (2025), `10.1039/d5sc06221g`, Table 1 | model-ready with room-temperature assumption |
| VC | Souid et al. (2025), `10.1002/cssc.202402091`, explicit 298 K | model-ready |
| 2-MeTHF | Yue et al. (2024), `10.1002/smtd.202400183`, Table 1 | model-ready with room-temperature assumption |
| ethoxybenzene and chlorinated diluents | Cui et al. (2026), `10.1002/adma.73388`, Table 1 | model-ready with room-temperature assumption |

For TEP, TMP, and FEC, the iScience table is the **data source**. The
Chemical Science Table 1 values (`10`, `10`, and `107`) are retained only as
conflict-comparison evidence and are not alternate source rows.

## Open-access reuse conditions

| DOI | License | Redistribution condition |
|---|---|---|
| `10.1002/smll.202504276` | CC BY 4.0 | attribution required |
| `10.1002/smtd.202400183` | CC BY-NC-ND 4.0 | noncommercial, no derivatives |
| `10.1039/d5sc06221g` | CC BY 3.0 | attribution required |
| `10.1002/cssc.202402091` | CC BY-NC 4.0 | noncommercial only |
| `10.1016/j.isci.2026.115778` | CC BY-NC 4.0 | noncommercial only; use the CC license, not the separate Elsevier TDM terms |
| `10.1002/adma.73388` | CC BY 4.0 | attribution required |

These rows are open access under the listed conditions, but they are not
unrestricted. The v0.3 build and verifier reject missing, unknown, restricted,
or unrestricted redistribution-condition labels. Both stages use the same
immutable DOI-to-license-triplet mapping, so a DOI cannot be combined with a
different license or redistribution condition. Validation runs across the
complete final v0.3 row set, including historical rows and DOIs listed in
`source_dois_all`; multiple values in that field are separated by semicolons.
DOI tokens are canonicalized before lookup by removing surrounding and internal
whitespace, applying case folding, and removing an explicit `doi:` prefix.
HTTP(S) resolver URLs on `doi.org` or `dx.doi.org` are parsed structurally:
the URL-decoded path is used, leading and trailing slashes are removed, and
query strings or fragments are ignored.

Final-row license detection builds one normalized text from `source_doi` and
`source_dois_all`: URL decoding is repeated until stable or a bounded pass
limit; any remaining `%xx` escape is a malformed-input error. The decoded text
then receives NFKC normalization and case folding, and only the ASCII
characters `[a-z0-9./:_-]` are retained. Every frozen DOI is detected by
substring containment on that ASCII plane, so resolver variants, encoding
layers, variation selectors, and other combining controls cannot hide a mapped
DOI.

`source_dois_all` is restricted to semicolon-separated tokens. Commas, pipes,
multiple DOI values inside one token, empty tokens, and non-whitelisted
resolver URLs are explicit format errors.

## Conflict exclusions

- `FEC`: public review values span `78.4`, `102`, and `107`.
- `TEP`: public review values are `10` and `13`.
- `TMP`: public review values are `10` and `21.6`.
- `Ethyl isothiocyanate`: NBS gives `19.5` at `294.15 K`; the restricted
  SpringerMaterials cross-check gives `29.7` at `293.2 K`.

All four rows remain in source audit material but carry
`model_ready=false`. The numeric conflicts are not averaged.

## Interpretation limit

Most CC BY review tables do not state an independent measurement temperature
for every solvent value. Such rows use `T_K=298.15 K` and the explicit
`review_table_standard_room_temperature` provenance flag. They are suitable
for the v0.3 coverage benchmark but should not be treated as independently
verified v1.0 training records until their primary sources are inspected.
