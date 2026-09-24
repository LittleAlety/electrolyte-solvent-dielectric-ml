# G1+ : the FEC 78.4 leg is at 23 C, and the 40 C version is a downstream restatement

**Date:** 2026-09-25
**Target:** fluoroethylene carbonate (FEC, CAS 114435-02-8, `O=C1OCC(F)O1`,
`SBLRHMKNNHXPHG-UHFFFAOYSA-N`)
**Evidence file:** `probes/g1plus_fec_temperature_attribution_evidence.json`
**Revision:** v0.3.13 (second finding of the same FEC pass)
**Question that triggered it:** the row stores **78.4 at 296.15 K (23 C)**. A
peer-reviewed paper from the same research group restates the same number as
**40 C**. Does that force `T_K` to move, and does the competing 107 leg sit at a
different temperature, which would turn the 78.4-vs-107 split into a
temperature pair rather than a conflict?

Both questions answer **no**.

## 1. The 40 C restatement

Nanbu, N.; Suzuki, K.; Yagi, N.; Sugahara, M.; Takehara, M.; Ue, M.; Sasaki, Y.
"Use of Fluoroethylene Carbonate as Solvent for Electric Double-Layer
Capacitors", *Electrochemistry* 2007, 75(8), 607-610, DOI
`10.5796/electrochemistry.75.607`, printed page 608:

> "The dynamic viscosity of FEC (4.1 mPa s at 40 C)4) is higher than those of
> EC (1.930 mPa s at 40 C)12) and PC (2.530 mPa s at 25 C).12) Strange to say,
> the relative permittivity of FEC (78.4 at 40 C)4) is lower than that of EC
> (89.78 at 40 C).12) The relative permittivity of PC is 64.92 at 25 C.12)"

Its reference 4) is, verbatim, "M. Kobayashi, T. Inoguchi, T. Iida, T. Tanioka,
H. Kumase, and Y. Fukai, *J. Fluorine Chem.*, 120, 105 (2003)" - i.e. the very
paper the dataset already cites. So this is **not a second measurement**; it is a
downstream restatement of the same primary value.

Two properties of the restatement matter:

- it moves **two quantities at once** (dielectric 78.4 **and** dynamic viscosity
  4.1 mPa s) from 23 C to 40 C, which is the signature of a systematic
  temperature shift in the citation rather than an isolated typo;
- the same paragraph pins EC at 40 C and PC at 25 C, so the author was tracking
  temperatures carefully for the *other* two solvents - the FEC row is the odd
  one out.

## 2. The primary table, re-read as an image

Because a textual extraction cannot be trusted for superscript footnote markers,
the primary table page (Kobayashi et al. 2003, *J. Fluorine Chem.* 120(2)
105-110, Table 2, printed page 108, PDF page 4) was **rendered at 600 dpi with
PyMuPDF and inspected as an image**:

- the FEC row reads `210 | 17.3 | 1497 | 4.1^e | 78.4^e | 1.04^e | Our data`,
  with the superscripts unmistakably the letter **e**;
- the footnote block beneath the table reads `c At 40 C.` / `d At 20 C.` /
  `e At 23 C.` / `f At 60 C.` / `g At 25 C.`;
- the ethylene carbonate row (90, at 40 C) carries **c**, and the propylene
  carbonate row (65) carries **d** - so the footnote letters are doing real,
  differentiated work in this table and the FEC row is not simply inheriting the
  EC temperature.

The primary's own cell-level footnote therefore says **23 C**, and the row is
marked "Our data", i.e. measured by the authors (footnote b: "Physical properties
are cited from ref. [11,12] except our data.").

## 3. The competing 107 leg is also near room temperature

The 107 claim is quoted at secondary level with an explicit temperature, and both
quotations resolve to the same underlying paper already named for this row:

- Nambu, N.; Takahashi, R.; Takehara, M.; Ue, M.; Sasaki, Y., *Electrochemistry*
  **2013**, 81(10), 817-819, printed page 817: "The relative permittivity of FEC
  (about 107 at 25 C)5 is considerably higher than that of PC (64.92 at 25 C).6"
  Its reference 5 is Hagiyama et al., *Chem. Lett.* 37, 210 (2008).
- Nambu, N.; Kobayashi, T.; Kobayashi, D.; Takahashi, R.; Sasaki, Y.,
  *Electrochemistry* **2013**, 81(10), 820-822, printed page 820: "The relative
  permittivity of MetPC (about 102 at 25 C)4 was also considerably higher than
  that of PC (64.92 at 25 C)5 and was comparable with that of FEC (about 107 at
  25 C).4" Its reference 4 is the same Hagiyama et al. paper.

Both are open-access J-STAGE communications and both copies are held locally.
Consequence: the two legs sit at **23 C vs 25 C**, a 2.00 K gap. The 78.4-vs-107
split therefore **cannot** be dismissed as a temperature artefact; it stays a
value conflict to be settled against Hagiyama 2008 (temperature, frequency,
purity, method) or another primary source.

## 4. Decision and what it cost the dataset

- `dielectric` stays **78.4**, `T_K` stays **296.15 K**, `model_ready` stays
  **false**; nothing is averaged and nothing is promoted.
- The 40 C restatement is now **registered on the row itself**
  (`conflict_status` and `notes`) and in
  `data/processed/dielectric_v03_exclusions.csv`, so a reader who only has the
  dataset sees the conflict. A documentation-only change, but one that moves the
  canonical digest.
- No Kobayashi 40 C variant was found. If one ever surfaces it would have to be
  weighed against the primary footnote before `T_K` could move.

## Reproduce

```powershell
.venv\Scripts\python.exe -X utf8 -c "import pymupdf; d=pymupdf.open(r'data/restricted/kobayashi2003/1-s2.0-S0022113902003172-main.pdf'); pg=d[3]; pg.get_pixmap(dpi=600, clip=pymupdf.Rect(38,150,560,360)).save('table2_zoom.png')"
.venv\Scripts\python.exe -X utf8 -c "import pymupdf; d=pymupdf.open(r'data/external/g1plus/tier3/jstage_2007_607.pdf'); t=' '.join(p.get_text() for p in d); i=t.find('relative permittivity of FEC'); print(t[i-200:i+260])"
```

*Note:* a plain-text extraction of `jstage_2007_607.pdf` hides every numeric
string because of a broken embedded font encoding. PyMuPDF re-extraction recovers
them; this is why the 40 C quote went unnoticed on the first pass.

## Still open

- **Hagiyama et al. 2008**, *Chem. Lett.* 37, 210-211 (DOI `10.1246/cl.2008.210`),
  is still **not held locally**. It is the only item that can close this row: it
  would establish whether the ~107 has a primary measurement behind it and under
  which conditions.
- An unverified agent report claimed the OUP PDF path yielded the Hagiyama text
  with "eps_r ~ 107 at 25 C (Figure 2b, p. 211)". **No local artefact backs that
  claim**, so it was not promoted; the finding above rests only on the
  locally-held 2013 quotations that name Hagiyama.
