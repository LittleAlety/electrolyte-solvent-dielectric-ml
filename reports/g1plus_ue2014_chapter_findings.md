# G1+ : the FEC 107 leg is read in Ue et al. 2014 - at compilation level

**Date:** 2026-09-25
**Target:** fluoroethylene carbonate (FEC, CAS 114435-02-8, `O=C1OCC(F)O1`,
`SBLRHMKNNHXPHG-UHFFFAOYSA-N`)
**Evidence file:** `probes/g1plus_ue2014_chapter_evidence.json`
**Previous state:** the row stores the primary measurement **78.4 at 296.15 K**
(Kobayashi et al. 2003, *J. Fluorine Chem.* 120(2) 105-110, Table 2, third data
row marked "Our data", footnote e "At 23 C.") and keeps `model_ready=false`;
`conflict_status` is `primary_78.4_landed_107_leg_unread`. The manual recorded
Ue et al. 2014 (DOI `10.1007/978-1-4939-0302-3_2`) as blocked behind Springer
identity authentication.

## What was retrieved

Direct HTTP retrieval of the chapter PDF returned status 200 and the complete
73-page chapter on 2026-09-25:

- Ue, M.; Sasaki, Y.; Tanaka, Y.; Morita, M. "Nonaqueous Electrolytes with
  Advances in Solvents", Chapter 2 in T. R. Jow et al. (eds.), *Electrolytes for
  Lithium and Lithium-Ion Batteries*, Modern Aspects of Electrochemistry 58,
  Springer New York, 2014, pp. 93-165.
  ISBN 9781493903016 / 9781493903023. DOI `10.1007/978-1-4939-0302-3_2`.
- PDF: 2,721,678 bytes, sha256
  `88931e6a9151de50a3eddb1992d755b850928ebe0bdb262319a92ca410c0eefe`
  (cached under `data/external/g1plus/tier3/`, git-ignored; never redistributed).

## The value

Table 2.3 "Physical properties of fluorinated solvents", printed page 101
(PDF page 9), columns Name | FW | d, g cm-3 | eps_r | eta, mPa s | E_HOMO, eV |
E_LUMO, eV, contains:

> `4-Fluoro-1,3-dioxolan-2-one (FEC)  106  1.50  107  4.1  -13.30  1.45`

so the chapter states **eps_r = 107** for FEC, alongside FW 106,
d 1.50 g cm-3, eta 4.1 mPa s, E_HOMO -13.30 eV and E_LUMO 1.45 eV.

## Attribution: a compilation row, not a primary measurement

Two statements bound what the 107 is worth:

1. Printed page 100: "The physical properties of typical fluorinated compounds
   and non-fluorinated counterparts were summarized in Tables 2.3 and 2.4,
   respectively **[4, 5]**". References [4] and [5] are both Sasaki review
   items (2011 ECSJ lecture notes; *Electrochemistry* 2008, 76, 2-15), so the
   table as a whole rests on compilation sources.
2. Printed page 105: "The relative permittivity and viscosity of FEC were higher
   than those of EC (Fig. 2.4a, b) **[25]**", where [25] is
   **Hagiyama, K.; Suzuki, K.; Ohtake, M.; Shimada, M.; Nanbu, N.; Takehara, M.;
   Ue, M.; Sasaki, Y., "Physical properties of substituted
   1,3-dioxolan-2-ones", *Chem. Lett.* 2008, 37, 210-211** - the paper the
   dataset already names as the unread primary candidate for the 107 leg.

The FEC row of Table 2.3 carries **no per-row footnote** (footnotes a and b in
that table attach to cis-DFEC and to the two perfluoroether rows only). So this
chapter is the **compilation that relays the Hagiyama line**, not an independent
measurement. It also explains why the 107 leg and the Hagiyama ticket were always
the same ticket.

## What did not change

- Stored `dielectric` stays **78.4**, `T_K` stays **296.15**, `model_ready`
  stays **false**. No average and no substitution is performed.
- The row still has exactly one confirmed primary measurement and one
  compilation-level competing value whose named primary source is unread.
- The dataset gains a provenance field refresh only. No fitted row and no
  benchmark input is touched.

## Rejected lead

Reference [57] of the same chapter is Suzuki et al., "Physical and
electrochemical properties of **fluoroacetonitrile** and its application to
electric double-layer capacitors", *Electrochemistry* 2007, 75, 611-614. It is
**not** 3-methoxypropionitrile and was rejected as a MOPN lead.

## Reproduce

```powershell
curl.exe -s -o data/external/g1plus/tier3/ue2014_chapter.pdf `
  -w "%{http_code} %{content_type}" `
  "https://link.springer.com/content/pdf/10.1007/978-1-4939-0302-3_2.pdf"
.venv\Scripts\python.exe -X utf8 -c "import json;print(json.load(open('probes/g1plus_ue2014_chapter_evidence.json',encoding='utf-8'))['evidence']['fec_row_extract'])"
```

## Still open

- **Hagiyama et al. 2008** (`10.1246/cl.2008.210`) remains unread: on this pass
  the DOI resolved to `academic.oup.com` with HTTP 403 and the J-STAGE path
  returned HTTP 404. Reading it would settle whether the 107 has a primary
  measurement behind it and at which temperature.
- Table 2.4 of the same chapter carries compilation-level values for EC 90
  (40 C), PC 65, DME 5.5 and others. It was recorded but **not** used to change
  any dataset row.
