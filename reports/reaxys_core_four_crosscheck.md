# W17-RX -- Reaxys crosscheck of the four core channels (hand-driven session)

**Arm**: W17-RX · **Week**: 17 · **Script**: `probes/reaxys_core_four_crosscheck.py`
**Rows**: `probes/reaxys_core_four_crosscheck.csv` (80 observation rows) ·
**Summary**: `probes/reaxys_core_four_crosscheck_summary.json`

> **Access tag: `restricted_crosscheck_only`.** Every row below is Reaxys content. It is
> crosscheck evidence only. No value in this report entered `data/`, any feature pool, any
> training split, or any export. Nothing is redistributable, and nothing was averaged.

## 1. Session

| item | value |
| --- | --- |
| surface | author's own Edge, `https://www.reaxys.com/#/search/quick/query` |
| signed-in marker | `Reaxys Access` avatar `QP`, no login wall |
| method | manual quick search, **one substance per query**; batch crawling is banned |
| queries | 9 |
| profile-copy route | **rejected**: the running Edge holds `Default/Network/Cookies` exclusively, `CreateFileW` returns error **32** (sharing violation) |

The logged-in session was reached through the browser-extension channel against the tab the
author already had open. Copying the Edge profile to a scratch directory was attempted first
and failed on the cookie database, so no copy of the author's profile was ever made.

## 2. What Reaxys can and cannot deliver

| core channel | verdict | numeric rows observed | why |
| --- | --- | --- | --- |
| dielectric constant eps | **usable_numeric** | 27 of 39 | eps is stored as a number with its own temperature column, including full eps(T) series |
| viscosity eta | **usable_numeric** | 27 of 41 | Dynamic and Kinematic Viscosity both return numbers |
| HOMO/LUMO | **reference_only** | 0 | only a property keyword plus a citation |
| redox potential | **reference_only** | 0 | only a description plus a citation |

**HOMO/LUMO answer for the author, stated exactly.** Reaxys indexes HOMO/LUMO work as the
string `Electronic energy levels, Molecular orbitals` with `Method = DFT - density functional
methods`, and nothing more. Ethylene carbonate exposes 5 such rows and succinonitrile exposes
2, and **not one of them carries a number**. Where Reaxys does have a numeric-looking
electronic category, `Ionization Potential` for dimethyl carbonate, the table has a
`Reference` column and **no value column**. Reaxys is therefore a literature finder for the
HOMO/LUMO channel, not a numeric supplier, and it does not relieve the L3 label bottleneck.
The same holds for redox: propylene carbonate's `Electrochemical Characteristics` row reads
`cyclovoltammetry` with comment `potential diagram` and cites Lu et al. 2014, and contains no
voltage.

## 3. Per-substance readings

### 3.1 Ethylene carbonate (`KMTRUDSVKNLOMY-UHFFFAOYSA-N`, RN 106249, CAS 96-49-1)

`Dielectric Constant` (4 rows) -- **5.4 at 25 C** (ChemSusChem 2026); **89.78 with a blank
temperature** (Chinese Chemical Letters 2026 SI); **89.78 at 25 C** (Schroeder, Hubaud &
Vaughey 2014); two further reference-only rows (Maquestian 1971, D'Aprano 1974).

`Static Dielectric Constant` (7 rows) -- **90.5 at 40 C** (Chernyak 2006), **90.05 at 40 C**
(Naejus 2002), **90.8 at 36 C**, **89.6 at 40 C**, **85.1 at 50 C**, **81 at 60 C**,
**77.3 at 70 C** (last three Seward & Vieira 1958).

`Dynamic Viscosity` (17 rows) -- **0.0193 P at 40 C** = 1.93 mPa*s (ChemSusChem 2026);
**0.0477 P at 25 C** = 4.77 mPa*s (Angew 2026 SI); then five rows from Tachouaft 2023 at
**80, 70, 60, 55 and 50 C whose value field is empty**.

`Melting Point` (30 rows) -- 39.5; **36.4** (Angew 2025 SI); 34-37; 41.3; 36-37 (Green Chem
2016 SI); 36-40 (patent CN104387421 paragraph 0025); **36** (Schroeder 2014).

`Other Data -> Quantum Chemical Calculations` (5 rows) -- DFT with keywords `Density of
states`, `Electronic energy levels, Molecular orbitals` (twice), `Atom distances, angles`,
`IR bands, intensities, transition moments, Raman bands`. **No numeric value in any row.**

### 3.2 Propylene carbonate (`RUOJZAUFBMNUDX-UHFFFAOYSA-N`, CAS 108-32-7)

`Dielectric Constant` (10 rows) -- **64.9 at 25 C**, **64.92** (blank T), **64** (Segato 2021),
**69 at 25 C** (Sun 2019), **64.92 at 25 C** (Schroeder 2014), **62.93 at 2E+06 Hz and 20 C**
(Laurence 1994), **63.41 at 2E+06 Hz and 35 C** (Ritzoulis 1989).

`Dynamic Viscosity` (74 rows, first page read) -- **0.0251 P at 25 C** = 2.51 mPa*s;
**0.0549 P at 25 C** = 5.49 mPa*s (Angew 2026 SI); one empty-value row; then
**0.0114 at 74.99 C, 0.01213 at 69.99 C, 0.01294 at 64.99 C, 0.01385 at 59.99 C**
(Liu 2021).

`Kinematic Viscosity` (2 rows) -- **0.0212 St at 25 C** (Ponomarenko 1995);
**1.36 - 2.39 St at 24.9 - 57.9 C** (Rosseinsky & Monk 1990).

`Electrochemical Characteristics` (1 row) -- `cyclovoltammetry` / `potential diagram`,
Lu 2014. **No number.**

### 3.3 gamma-Valerolactone (`GAEKPEKOJKCEMS-UHFFFAOYSA-N`, RN 80420, CAS 108-29-2)

`Dielectric Constant` -- **exactly one row in the whole substance record: 36.9**, location
`supporting information`, Segato et al. 2021, Inorganica Chimica Acta vol. 522, and the table
has **no temperature column at all**.

`Dynamic Viscosity` (4 rows, Devi 2023) -- **1.88 mPa*s at 24.99 C**, **1.68 at 29.99 C**,
**1.56 at 34.99 C**, **1.45 at 39.99 C**. The numbers sit **inside the Comment free text**
(`Liquid, Dynamic Viscosity: 1.45 mPa*s`); the structured value column is empty.

### 3.4 Succinonitrile (`IAHFWCOBPZCAEA-UHFFFAOYSA-N`, CAS 110-61-2)

`Dielectric Constant` (3 rows) -- **55 at 50 C**, whose reference column reads **`No author`**;
plus two reference-only rows (Williams & Smyth 1962, Longueville 1971) and one row with a
temperature span of `-190 - 78.2 C` and an empty value.

`Static Dielectric Constant` (2 rows) -- **`2.76 - 60.83` over `-151 - 60.5 C`** (Lafontaine
1958): an entire eps(T) series compressed into one min-max pair, next to reference-only rows.

`Dynamic Viscosity` (5 rows, complete) -- **0.02591 P at 60 C** and **0.02008 P at 75 C**
(Timmermans 1937); **0.0276 P at 58.7 C** and **0.0181 P at 83 C** (Dunstan 1913);
**0.0246 P at 60 C** (Walden 1911). At 60 C the three independent sources give
**2.46, 2.591 and 2.76 mPa*s**; the spread is reported, not averaged.

`Other Data -> Quantum Chemical Calculations` (2 rows) -- the same DFT keyword form, no number.

### 3.5 Dimethyl carbonate (`IEJIGPNLZYLLBP-UHFFFAOYSA-N`, RN 635821, CAS 616-38-6)

`Dielectric Constant` (5 rows) -- **3.11 at 25 C** (Schroeder 2014); **3.13 - 3.15 over
15 - 55 C** (Rivas 2004); **3.13 - 3.15 over 15 - 30 C** (Rivas 2002); **3.17 at 2E+06 Hz and
20 C** (Laurence 1994).

`Dynamic Viscosity` (24 rows) -- **0.00439 - 0.00669 P over 14.99 - 54.99 C** (Liu 2018);
**0.00401 at 59.99 C, 0.0042 at 54.99 C, 0.00442 at 49.99 C, 0.00465 at 44.99 C,
0.00491 at 39.99 C** (Chen 2015); one falling-ball row with an empty value.

`Ionization Potential` (1 row) -- Meeks 1975, Chem. Phys. Lett. 30, 190, **reference only**.

## 4. The three lessons

### Lesson A -- the GVL InChIKey: **not reproduced, and it is our error**

`JYVATQXCHBTGRN-UHFFFAOYSA-N` returns **0 substances and 0 documents**. Reaxys never assigns
that key. `GAEKPEKOJKCEMS-UHFFFAOYSA-N` returns **4 substances**, the first being
`5-methyl-dihydro-furan-2-one`, RN 80420, CAS 108-29-2, molecular weight 100.117.

The bad key sits in the **key column** of `probes/reaxys_dielectric_queue_first_cut.csv`,
whose gamma-valerolactone row otherwise carries the *right* 36.9, the *right* `supporting
information` location and the *right* Segato 2021 reference -- exactly what the live lookup
returns under the correct key. Only the key column was ever wrong, and it was wrong on our
side. `probes/reaxys_v1x_stocking_queue.csv` and
`probes/reaxys_thin_family_backfill_queue.csv` both already carry the correct key.

### Lesson B -- a Reaxys temperature label for EC: **reproduced**

Two independent facts collide. First, EC melts at **36.4 C** in Reaxys (and at **36 C** in
Schroeder 2014, the same paper as the eps row). Second, the value **89.78 appears twice**:
once with a **blank temperature** (Chinese Chemical Letters 2026 SI) and once tagged
**25 C** (Schroeder 2014). EC's own `Static Dielectric Constant` series puts 89.6 to 90.8 at
**36 to 40 C**. A pure-liquid measurement at 25 C is therefore physically impossible, and the
**25 C tag is the defect**, not the value. This is precisely the failure mode the
liquid-window gate exists to catch, and the gate already blocks EC on its 36.4 C melting point.

### Lesson C -- 89.78 filed as an EC melting point: **not reproduced**

The EC `Melting Point` category lists 39.5, 36.4, 34-37, 41.3, 36-37, 36-40 and 36. **No row
starts with 89.** In the live index 89.78 is a dielectric constant only. If the old label ever
came from Reaxys it has since been corrected; if it came from our own parse, it was ours.

## 5. Data-shape traps found in the live index

- **Ranges as strings.** `3.13 - 3.15` over `15 - 55`, `1.36 - 2.39` over `24.9 - 57.9`,
  `2.76 - 60.83` over `-151 - 60.5`. A whole temperature series can collapse into one cell.
- **Unit drift.** poise (`P`), stokes (`St`) and `mPa*s` all appear across rows of the same
  property, and the unit is only in the column header.
- **Value hidden in free text.** GVL's eta values exist only inside the `Comment` field.
- **Float noise in temperatures.** 59.99 / 69.99 / 74.99 instead of 60 / 70 / 75.
- **Frequency-labelled eps next to static eps** (2E+06 Hz rows) with no separating flag.
- **Empty value cells** with a populated temperature, in bulk.
- **Missing author metadata.** Succinonitrile's only numeric eps row has `No author`.
- **Secondary attribution.** PC's 64.9 at 25 C is credited to a 2026 paper, while the shipped
  project value for the identical number and temperature is Simeral & Amey 1970.

## 6. Queue key audit

All 14 audited substances were re-derived with RDKit and compared against the key actually
stored in `probes/reaxys_thin_family_backfill_queue.csv` (the queue file wins over the
literal). Result: **14 matched, 0 mismatched**. The W17-2 queue's InChIKeys are sound,
including gamma-valerolactone and ethyl methyl carbonate.

One negative control is recorded: `JBTWLSYIZRCDFA-UHFFFAOYSA-N` returns 0 substances because
the true key ends in `O`, not `A`. That slip was made in this session's own typing and is
labelled as such -- it is a useful control because it proves the Reaxys key lookup is an exact
match, not a fuzzy one.

## 7. Limitations

- The Reaxys category list is virtualised, so **not observed is not proven absent**.
  `alphabetical_tail_observed` records which walks reached the end of the list.
- `Other Data` was fully enumerated for ethylene carbonate and succinonitrile only.
- Five substances were walked. The thin families are covered by DMC (carbonate), GVL
  (lactone) and succinonitrile (nitrile); **no acid-family and no protic-ionic-pair substance
  was walked**.
- Every number is a point-in-time snapshot of a live index that Reaxys can change.
- A blank Reaxys temperature column means Reaxys indexed no temperature, not that none exists.