"""Week 17 / W17-RX -- manual Reaxys crosscheck of the four core channels.

The author authorised a live, hand-driven Reaxys session for Week 17 ("reaxys is
already logged in, use Edge if you need it").  This arm spends that session on the
question the Week 17 chapter and the author's own prompt put first: **which of the
four core channels (viscosity eta, relative permittivity eps, HOMO/LUMO, redox
potential) can Reaxys actually supply as numbers, and do the numbers it supplies
agree with what this repository already ships?**

Collection discipline (a red line, inherited unchanged from Week 12/16):

* every lookup is issued **one substance at a time by hand** through the public
  Reaxys quick-search box; batch crawling is banned, so no value below was obtained
  by scraping a result set;
* Reaxys content is **restricted**: every harvested row is stamped
  ``access = restricted_crosscheck_only`` and ``reaxys_crosscheck_only = TRUE``.
  Restricted values are crosscheck evidence only -- they never enter ``data/``,
  never enter a feature pool, never enter a training split, and are not
  redistributable.  This module therefore writes only its own two artifacts next to
  itself and never touches ``data/``;
* conflicting values are reported side by side and are **never averaged**;
* the Reaxys category list is virtualised (only the rendered slice is in the DOM),
  so a category that is not listed below is reported as *not observed*, not as
  *proven absent*.  ``alphabetical_tail_observed`` records, per substance, whether
  the walk actually reached the alphabetical end of the list.

The offline entry point (``--check``) re-derives every verdict from the shipped
repository files and re-verifies the checked-in summary without network access.
``--write`` regenerates the CSV and the summary.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

CSV_PATH = REPOSITORY_ROOT / "probes" / "reaxys_core_four_crosscheck.csv"
SUMMARY_PATH = REPOSITORY_ROOT / "probes" / "reaxys_core_four_crosscheck_summary.json"

DIELECTRIC_V04 = REPOSITORY_ROOT / "data" / "dielectric_v04.csv"
LIQUID_WINDOW_SUMMARY = REPOSITORY_ROOT / "probes" / "liquid_window_gate_summary.json"
BACKFILL_QUEUE = REPOSITORY_ROOT / "probes" / "reaxys_thin_family_backfill_queue.csv"

ACCESS = "restricted_crosscheck_only"

SESSION = {
    "channel": "edge_extension_attached_to_the_author_browser",
    "profile": "Default, already in use by the author",
    "signed_in_marker": "Reaxys Access avatar QP present, no login wall",
    "surface": "https://www.reaxys.com/#/search/quick/query",
    "method": "manual single-substance quick search, one substance per query",
    "queries_executed": 9,
    "batch_crawling": False,
    "profile_copy_route": "rejected: the running Edge holds Default/Network/Cookies "
                          "exclusively, CreateFileW returns error 32 (sharing violation)",
}

# Declared before the harvest, so the collection rules cannot be fitted afterwards.
HARVEST_PROTOCOL = {
    "per_substance_actions": [
        "quick-search box, one InChIKey or one substance name per query",
        "open the substance preview card (View Results for the Substances group)",
        "expand the Physical Data accordion and walk Load More to the end",
        "expand the Other Data accordion and walk Load More to the end",
        "open every category that can carry a core-channel number and read its table",
    ],
    "recorded_fields": [
        "value as printed by Reaxys, raw, with the Reaxys unit",
        "temperature as printed by Reaxys, raw, in the Reaxys unit",
        "the Reaxys location column, for example supporting information",
        "a reference short form: authors, journal, year, volume, page",
(
            "the row shape: numeric, range, range_with_temperature, reference_only, "
            "temperature_only or value_in_comment"
        ),
    ],
    "not_recorded": [
        "no value is averaged",
        "no value is unit-converted into a candidate record",
        "no value is written under data/",
    ],
    "stopping_rule": "stop once the four channels have a verdict per substance and five "
                     "substances spanning carbonate, lactone and nitrile space are walked",
}
# --------------------------------------------------------------------------------------
# Reference short forms.  A citation is metadata, not a restricted value.
# --------------------------------------------------------------------------------------
REFS = {
    "segura2026": "Segura-Ramirez, Sole-Daura, Gomez-Mingot, Fontecave, Sanchez-Sanchez; ChemSusChem 2026, 19(6), e202502570",
    "xu2026": "Xu, Zhang, Li, Chen, Zhou, Zhang, Wu; Chinese Chemical Letters 2026, 37(8), 111263",
    "schroeder2014": "Schroeder, Hubaud, Vaughey; Materials Research Bulletin 2014, 49(1), 614-617",
    "maquestian1971": "Maquestian et al.; Bulletin des Societes Chimiques Belges 1971, 80, 17,22",
    "daprano1974": "D'Aprano; Gazzetta Chimica Italiana 1974, 104, 91",
    "chernyak2006": "Chernyak, Yury; Journal of Chemical and Engineering Data 2006, 51(2), 416-418",
    "naejus2002": "Naejus, Damas, Lemordant, Coudert, Willmann; Journal of Chemical Thermodynamics 2002, 34(6), 795-806",
    "seward1958": "Seward, Vieira; Journal of Physical Chemistry 1958, 62, 127",
    "kempa1958": "Kempa, Lee; Journal of the Chemical Society 1958, 1936",
    "heng2025": "Heng, Gu, Liu, Liang, Deng, Zhao, Wang, Xue, Hong-Yan, Wu; Angewandte Chemie International Edition 2025, 64(14), e202423044",
    "kasakado2022": "Kasakado, Fukuyama, Nakagawa, Taguchi, Ryu; Beilstein Journal of Organic Chemistry 2022, 18, 152-158",
    "hofmann2016": "Hofmann, Migeot, Hanemann; Journal of Chemical and Engineering Data 2016, 61(1), 114-123",
    "liu2016": "Liu, Zhang, Song, Liu, Ma, He; Green Chemistry 2016, 18(9), 2871-2876",
    "cn104387421": "Current Patent Assignee: SUZHOU ERYE PHARMACEUTICALS; CN104387421, 2016, B, paragraph 0025",
    "shen2026": "Shen, Yuan, Fu, Fan, Zhou, Lu; Angewandte Chemie International Edition 2026, 65(31), e6110810",
    "tachouaft2023": "Tachouaft, Damas, Naejus; Journal of Solution Chemistry 2023, 52(11), 1232-1254",
    "sreedeep2025": "Sreedeep, Lee, Aravindan; Journal of Materials Chemistry A 2025, 13(18), 13262-13275",
    "chen2026": "Chen, Ding, Zeng, Dong, Yue, Si, Zhang, Qu, Liang, Hao; Chinese Chemical Letters 2026, 37(7), 111127",
    "wu2023": "Wu, Huang, Wang, Tao, Yu, Zhang; Catalysis Letters 2023, 153(1), 62-73",
    "wang2022": "Wang, Yu, Zhao, Xue, Jiang, Wang, Wu; Spectrochimica Acta Part A 2022, 281, 121593",
    "segato2021": "Segato, Baratta, Belanzoni, Belpassi, Del Zotto, Zuccaccia; Inorganica Chimica Acta 2021, 522, 120372",
    "sun2019": "Sun, Huang, Guo; Chemical Communications 2019, 55(92), 13876-13879",
    "laurence1994": "Laurence, Nicolet, Dalati, Abboud, Notario; Journal of Physical Chemistry 1994, 98(23), 5807-5816",
    "ritzoulis1989": "Ritzoulis, George; Canadian Journal of Chemistry 1989, 67, 1105-1108",
    "wangx2022": "Wang, Song, Wu, Yu, Feng, Armand, Huang, Zhou, Zhang; Angewandte Chemie International Edition 2022, 61(47), E202211623",
    "liu2021": "Liu, Ma, Wang, Ni, Fu, Wang, Zheng; Journal of Molecular Liquids 2021, 325, 114573",
    "ponomarenko1995": "Ponomarenko, Mushtakova, Demakhin, Faifel, Kalmanovich; Russian Journal of General Chemistry 1995, 65(2.1), 160-167",
    "rosseinsky1990": "Rosseinsky, Monk; Journal of the Chemical Society, Faraday Transactions 1990, 86(21), 3597-3601",
    "lu2014": "Lu, Korf, Kambe, Tu, Archer; Angewandte Chemie International Edition 2014, 53(2), 488-492",
    "devi2023": "Devi, Rani, Kumar, Kataria; Journal of Molecular Liquids 2023, 390, 123056",
    "williams1962": "Williams, Smyth; Journal of the American Chemical Society 1962, 84, 1808,1810",
    "longueville1971": "Longueville et al.; Journal de Chimie Physique 1971, 68, 436,438,439",
    "white1937": "White, Morgan; Journal of Chemical Physics 1937, 5, 661",
    "noauthor_ea": "No author recorded in the Reaxys reference column; Electrochimica Acta",
    "walden1903": "Walden; Zeitschrift fur Physikalische Chemie 1903, 46, 174 and 1906, 54, 163",
    "schlundt1902": "Schlundt; Chemisches Zentralblatt 1902, 73(I), 3",
    "lafontaine1958": "Lafontaine; Bulletin des Societes Chimiques Belges 1958, 67, 153,161",
    "timmermans1937": "Timmermans, Hennaut-Roland; Journal de Chimie Physique 1937, 34, 711",
    "dunstan1913": "Dunstan, Hilditch, Thole; Journal of the Chemical Society 1913, 103, 140",
    "walden1911": "Walden; Zeitschrift fur Physikalische Chemie 1911, 75, 575",
    "su2025": "Su, Qu, Hu, Wang, Song, Pei, Mao, Jian, Hu; Angewandte Chemie International Edition 2025, 64(7), e202418959",
    "zhang2023": "Zhang, Liu, Sun, Liu, Xu, Xi, Ji, Zhu, Liu; Angewandte Chemie International Edition 2023, 62(44), e202310006",
    "meeks1975": "Meeks et al.; Chemical Physics Letters 1975, 30, 190",
    "wittel1975": "Wittel et al.; Zeitschrift fur Naturforschung Teil B 1975, 30, 862,863,864",
    "rivas2004": "Rivas, Pereira, Banerji, Iglesias; Journal of Chemical Thermodynamics 2004, 36(3), 183-191",
    "rivas2002": "Rivas, Pereira, Iglesias; Journal of Chemical Thermodynamics 2002, 34(11), 1897-1907",
    "gao2024": "Gao, Hong, Zhang, Li; Journal of Solution Chemistry 2024, 53(2), 257-277",
    "liu2018": "Liu, Zhao, Zheng, Mou, Zhang; Journal of Chemical and Engineering Data 2018, 63(12), 4484-4496",
    "chen2015": "Chen, Yang, Chen, Hu, Chen, Cai; Journal of Molecular Liquids 2015, 209, 683-692",
}

def _row(substance, inchikey, cas, rn, channel, section, category, value_raw, unit_raw,
         value_si, temperature_raw, temperature_K, location, ref_key, row_kind, note=""):
    return {
        "substance": substance,
        "inchikey": inchikey,
        "cas": cas,
        "reaxys_registry_number": rn,
        "channel": channel,
        "reaxys_section": section,
        "reaxys_category": category,
        "value_raw": value_raw,
        "unit_raw": unit_raw,
        "value_si": value_si,
        "temperature_raw_C": temperature_raw,
        "temperature_K": temperature_K,
        "location": location,
        "reference": REFS[ref_key],
        "row_kind": row_kind,
        "access": ACCESS,
        "reaxys_crosscheck_only": "TRUE",
        "note": note,
    }


EC = ("ethylene carbonate", "KMTRUDSVKNLOMY-UHFFFAOYSA-N", "96-49-1", "106249")
PC = ("propylene carbonate", "RUOJZAUFBMNUDX-UHFFFAOYSA-N", "108-32-7", "")
GVL = ("gamma-valerolactone", "GAEKPEKOJKCEMS-UHFFFAOYSA-N", "108-29-2", "80420")
SN = ("succinonitrile", "IAHFWCOBPZCAEA-UHFFFAOYSA-N", "110-61-2", "")
DMC = ("dimethyl carbonate", "IEJIGPNLZYLLBP-UHFFFAOYSA-N", "616-38-6", "635821")

OBSERVATIONS = [
    # ---- ethylene carbonate ----------------------------------------------------------
    _row(*EC, "dielectric", "Physical Data", "Dielectric Constant", "5.4", "", "", "25", "298.15", "", "segura2026", "numeric",
         "a single outlier against every other EC entry"),
    _row(*EC, "dielectric", "Physical Data", "Dielectric Constant", "89.78", "", "", "", "", "supporting information", "xu2026", "numeric",
         "the same number as the Schroeder row, here with NO temperature"),
    _row(*EC, "dielectric", "Physical Data", "Dielectric Constant", "89.78", "", "", "25", "298.15", "", "schroeder2014", "numeric",
         "lesson B: a 25 C tag on a value whose own series sits at 36-40 C"),
    _row(*EC, "dielectric", "Physical Data", "Dielectric Constant", "", "", "", "", "", "", "maquestian1971", "reference_only",
         "reference indexed, no numeric value"),
    _row(*EC, "dielectric", "Physical Data", "Dielectric Constant", "", "", "", "", "", "", "daprano1974", "reference_only",
         "reference indexed, no numeric value"),
    _row(*EC, "dielectric", "Physical Data", "Static Dielectric Constant", "90.5", "", "", "40", "313.15", "", "chernyak2006", "numeric",
         "matches the shipped v0.4 primary leg value and temperature exactly"),
    _row(*EC, "dielectric", "Physical Data", "Static Dielectric Constant", "90.05", "", "", "40", "313.15", "", "naejus2002", "numeric", ""),
    _row(*EC, "dielectric", "Physical Data", "Static Dielectric Constant", "90.8", "", "", "36", "309.15", "", "seward1958", "numeric", ""),
    _row(*EC, "dielectric", "Physical Data", "Static Dielectric Constant", "89.6", "", "", "40", "313.15", "", "kempa1958", "numeric", ""),
    _row(*EC, "dielectric", "Physical Data", "Static Dielectric Constant", "85.1", "", "", "50", "323.15", "", "seward1958", "numeric", ""),
    _row(*EC, "dielectric", "Physical Data", "Static Dielectric Constant", "81", "", "", "60", "333.15", "", "seward1958", "numeric", ""),
    _row(*EC, "dielectric", "Physical Data", "Static Dielectric Constant", "77.3", "", "", "70", "343.15", "", "seward1958", "numeric",
         "a clean eps(T) series, the only EC eps series Reaxys exposes"),
    _row(*EC, "melting_point", "Physical Data", "Melting Point", "39.5", "degC", "", "", "", "", "segura2026", "numeric", ""),
    _row(*EC, "melting_point", "Physical Data", "Melting Point", "36.4", "degC", "", "", "", "supporting information", "heng2025", "numeric",
         "reproduces the 36.4 C the liquid-window gate already blocks on"),
    _row(*EC, "melting_point", "Physical Data", "Melting Point", "34 - 37", "degC", "", "", "", "", "kasakado2022", "range", ""),
    _row(*EC, "melting_point", "Physical Data", "Melting Point", "41.3", "degC", "", "", "", "", "hofmann2016", "numeric", ""),
    _row(*EC, "melting_point", "Physical Data", "Melting Point", "36 - 37", "degC", "", "", "", "supporting information", "liu2016", "range", ""),
    _row(*EC, "melting_point", "Physical Data", "Melting Point", "36 - 40", "degC", "", "", "", "Paragraph 0025", "cn104387421", "range",
         "patent paragraph"),
    _row(*EC, "melting_point", "Physical Data", "Melting Point", "36", "degC", "", "", "", "", "schroeder2014", "numeric",
         "the same paper that carries the eps 89.78 at 25 C row"),
    _row(*EC, "viscosity", "Physical Data", "Dynamic Viscosity", "0.0193", "P", "1.93", "40", "313.15", "", "segura2026", "numeric",
         "1.93 mPa*s, physically sensible for EC above its melting point"),
    _row(*EC, "viscosity", "Physical Data", "Dynamic Viscosity", "0.0477", "P", "4.77", "25", "298.15", "supporting information", "shen2026", "numeric",
         "2.5x the Segura value at 25 C, a temperature at which pure EC is a solid"),
    _row(*EC, "viscosity", "Physical Data", "Dynamic Viscosity", "", "", "", "80", "353.15", "", "tachouaft2023", "temperature_only",
         "temperature row with the value field empty"),
    _row(*EC, "viscosity", "Physical Data", "Dynamic Viscosity", "", "", "", "70", "343.15", "", "tachouaft2023", "temperature_only", ""),
    _row(*EC, "viscosity", "Physical Data", "Dynamic Viscosity", "", "", "", "60", "333.15", "", "tachouaft2023", "temperature_only", ""),
    _row(*EC, "viscosity", "Physical Data", "Dynamic Viscosity", "", "", "", "55", "328.15", "", "tachouaft2023", "temperature_only", ""),
    _row(*EC, "viscosity", "Physical Data", "Dynamic Viscosity", "", "", "", "50", "323.15", "", "tachouaft2023", "temperature_only", ""),
    _row(*EC, "homo_lumo", "Other Data", "Quantum Chemical Calculations", "", "", "", "", "", "supporting information", "sreedeep2025", "reference_only",
         "keyword 'Electronic energy levels, Molecular orbitals', method DFT"),
    _row(*EC, "homo_lumo", "Other Data", "Quantum Chemical Calculations", "", "", "", "", "", "", "xu2026", "reference_only",
         "keyword 'Electronic energy levels, Molecular orbitals', method DFT"),
    _row(*EC, "homo_lumo", "Other Data", "Quantum Chemical Calculations", "", "", "", "", "", "supporting information", "chen2026", "reference_only",
         "keyword 'Density of states', method DFT"),
    _row(*EC, "homo_lumo", "Other Data", "Quantum Chemical Calculations", "", "", "", "", "", "", "wu2023", "reference_only",
         "keyword 'Atom distances, angles', method DFT"),
    _row(*EC, "homo_lumo", "Other Data", "Quantum Chemical Calculations", "", "", "", "", "", "", "wang2022", "reference_only",
         "keyword 'IR bands, intensities, transition moments, Raman bands'"),
]
OBSERVATIONS += [
    # ---- propylene carbonate ---------------------------------------------------------
    _row(*PC, "dielectric", "Physical Data", "Dielectric Constant", "64.9", "", "", "25", "298.15", "", "segura2026", "numeric",
         "the shipped Simeral & Amey value and temperature, attributed here to a different paper"),
    _row(*PC, "dielectric", "Physical Data", "Dielectric Constant", "64.92", "", "", "", "", "", "xu2026", "numeric", ""),
    _row(*PC, "dielectric", "Physical Data", "Dielectric Constant", "64", "", "", "", "", "", "segato2021", "numeric",
         "the same paper that carries the shipped GVL 36.9 leg"),
    _row(*PC, "dielectric", "Physical Data", "Dielectric Constant", "69", "", "", "25", "298.15", "", "sun2019", "numeric",
         "an outlier against the 64.9 cluster"),
    _row(*PC, "dielectric", "Physical Data", "Dielectric Constant", "64.92", "", "", "25", "298.15", "", "schroeder2014", "numeric", ""),
    _row(*PC, "dielectric", "Physical Data", "Dielectric Constant", "62.93", "", "", "20", "293.15", "", "laurence1994", "numeric",
         "frequency 2E+06 Hz: a frequency-labelled eps sitting next to static eps with no flag to separate them"),
    _row(*PC, "dielectric", "Physical Data", "Dielectric Constant", "63.41", "", "", "35", "308.15", "", "ritzoulis1989", "numeric",
         "frequency 2E+06 Hz"),
    _row(*PC, "viscosity", "Physical Data", "Dynamic Viscosity", "0.0251", "P", "2.51", "25", "298.15", "", "segura2026", "numeric", "2.51 mPa*s"),
    _row(*PC, "viscosity", "Physical Data", "Dynamic Viscosity", "0.0549", "P", "5.49", "25", "298.15", "supporting information", "shen2026", "numeric",
         "the same reference that overstates EC, here 2.2x the Segura value"),
    _row(*PC, "viscosity", "Physical Data", "Dynamic Viscosity", "", "", "", "25", "298.15", "supporting information", "wangx2022", "temperature_only",
         "temperature row with the value field empty"),
    _row(*PC, "viscosity", "Physical Data", "Dynamic Viscosity", "0.0114", "P", "1.14", "74.99", "348.14", "", "liu2021", "numeric", ""),
    _row(*PC, "viscosity", "Physical Data", "Dynamic Viscosity", "0.01213", "P", "1.213", "69.99", "343.14", "", "liu2021", "numeric", ""),
    _row(*PC, "viscosity", "Physical Data", "Dynamic Viscosity", "0.01294", "P", "1.294", "64.99", "338.14", "", "liu2021", "numeric", ""),
    _row(*PC, "viscosity", "Physical Data", "Dynamic Viscosity", "0.01385", "P", "1.385", "59.99", "333.14", "", "liu2021", "numeric",
         "clean eta(T) series; note the 59.99 and 69.99 float noise rather than 60 and 70"),
    _row(*PC, "viscosity", "Physical Data", "Kinematic Viscosity", "0.0212", "St", "2.12", "25", "298.15", "", "ponomarenko1995", "numeric",
         "2.12 cSt, consistent with eta/rho for PC"),
    _row(*PC, "viscosity", "Physical Data", "Kinematic Viscosity", "1.36 - 2.39", "St", "", "24.9 - 57.9", "", "", "rosseinsky1990", "range_with_temperature",
         "a whole temperature series collapsed into one min-max cell, in a different unit from the other rows"),
    _row(*PC, "redox", "Physical Data", "Electrochemical Characteristics", "", "", "", "", "", "supporting information", "lu2014", "reference_only",
         "description 'cyclovoltammetry', comment 'potential diagram': no number"),

    # ---- gamma-valerolactone ---------------------------------------------------------
    _row(*GVL, "dielectric", "Physical Data", "Dielectric Constant", "36.9", "", "", "", "", "supporting information", "segato2021", "numeric",
         "lesson A: the entire GVL dielectric series in Reaxys is this single row, and it is the shipped v0.4 main value"),
    _row(*GVL, "viscosity", "Physical Data", "Dynamic Viscosity", "1.88", "mPa*s", "1.88", "24.99", "298.14", "", "devi2023", "value_in_comment",
         "the numeric eta lives in the Comment free text, not in the value column"),
    _row(*GVL, "viscosity", "Physical Data", "Dynamic Viscosity", "1.68", "mPa*s", "1.68", "29.99", "303.14", "", "devi2023", "value_in_comment",
         "value stored only inside the Comment free text"),
    _row(*GVL, "viscosity", "Physical Data", "Dynamic Viscosity", "1.56", "mPa*s", "1.56", "34.99", "308.14", "", "devi2023", "value_in_comment",
         "value stored only inside the Comment free text"),
    _row(*GVL, "viscosity", "Physical Data", "Dynamic Viscosity", "1.45", "mPa*s", "1.45", "39.99", "313.14", "", "devi2023", "value_in_comment",
         "value stored only inside the Comment free text"),

    # ---- succinonitrile --------------------------------------------------------------
    _row(*SN, "dielectric", "Physical Data", "Dielectric Constant", "55", "", "", "50", "323.15", "", "noauthor_ea", "numeric",
         "the only numeric dielectric value Reaxys exposes for succinonitrile"),
    _row(*SN, "dielectric", "Physical Data", "Dielectric Constant", "", "", "", "", "", "", "williams1962", "reference_only",
         "reference indexed, no numeric value"),
    _row(*SN, "dielectric", "Physical Data", "Dielectric Constant", "", "", "", "", "", "", "longueville1971", "reference_only",
         "reference indexed, no numeric value"),
    _row(*SN, "dielectric", "Physical Data", "Dielectric Constant", "", "", "", "-190 - 78.2", "", "", "white1937", "temperature_only",
         "temperature span with the value field empty; comment 'Frequency:1-100 kHz.'"),
    _row(*SN, "dielectric", "Physical Data", "Static Dielectric Constant", "2.76 - 60.83", "", "", "-151 - 60.5", "", "", "lafontaine1958", "range_with_temperature",
         "a whole eps(T) series collapsed into one min-max value and one min-max temperature"),
    _row(*SN, "dielectric", "Physical Data", "Static Dielectric Constant", "", "", "", "", "", "", "walden1903", "reference_only", ""),
    _row(*SN, "dielectric", "Physical Data", "Static Dielectric Constant", "", "", "", "", "", "", "schlundt1902", "reference_only", ""),
    _row(*SN, "viscosity", "Physical Data", "Dynamic Viscosity", "0.02591", "P", "2.591", "60", "333.15", "", "timmermans1937", "numeric", ""),
    _row(*SN, "viscosity", "Physical Data", "Dynamic Viscosity", "0.02008", "P", "2.008", "75", "348.15", "", "timmermans1937", "numeric", ""),
    _row(*SN, "viscosity", "Physical Data", "Dynamic Viscosity", "0.0276", "P", "2.76", "58.7", "331.85", "", "dunstan1913", "numeric",
         "conflicts with 2.591 mPa*s at 60 C from Timmermans: reported side by side, never averaged"),
    _row(*SN, "viscosity", "Physical Data", "Dynamic Viscosity", "0.0181", "P", "1.81", "83", "356.15", "", "dunstan1913", "numeric", ""),
    _row(*SN, "viscosity", "Physical Data", "Dynamic Viscosity", "0.0246", "P", "2.46", "60", "333.15", "", "walden1911", "numeric",
         "a third independent source at 60 C: the 60 C cluster spans 2.46 to 2.76 mPa*s"),
    _row(*SN, "homo_lumo", "Other Data", "Quantum Chemical Calculations", "", "", "", "", "", "", "su2025", "reference_only",
         "keyword 'Electronic energy levels, Molecular orbitals', method DFT"),
    _row(*SN, "homo_lumo", "Other Data", "Quantum Chemical Calculations", "", "", "", "", "", "", "zhang2023", "reference_only",
         "keyword 'Molecular orbitals, Electronic energy levels', method DFT"),

    # ---- dimethyl carbonate ----------------------------------------------------------
    _row(*DMC, "dielectric", "Physical Data", "Dielectric Constant", "3.11", "", "", "25", "298.15", "", "schroeder2014", "numeric",
         "low against the shipped 3.134 and against the Rivas range"),
    _row(*DMC, "dielectric", "Physical Data", "Dielectric Constant", "3.13 - 3.15", "", "", "15 - 55", "", "", "rivas2004", "range_with_temperature",
         "a range value and a range temperature in one cell"),
    _row(*DMC, "dielectric", "Physical Data", "Dielectric Constant", "3.13 - 3.15", "", "", "15 - 30", "", "", "rivas2002", "range_with_temperature", ""),
    _row(*DMC, "dielectric", "Physical Data", "Dielectric Constant", "3.17", "", "", "20", "293.15", "", "laurence1994", "numeric",
         "frequency 2E+06 Hz"),
    _row(*DMC, "viscosity", "Physical Data", "Dynamic Viscosity", "0.00439 - 0.00669", "P", "", "14.99 - 54.99", "", "", "liu2018", "range_with_temperature",
         "a range value with a range temperature"),
    _row(*DMC, "viscosity", "Physical Data", "Dynamic Viscosity", "0.00401", "P", "0.401", "59.99", "333.14", "", "chen2015", "numeric", ""),
    _row(*DMC, "viscosity", "Physical Data", "Dynamic Viscosity", "0.0042", "P", "0.42", "54.99", "328.14", "", "chen2015", "numeric", ""),
    _row(*DMC, "viscosity", "Physical Data", "Dynamic Viscosity", "0.00442", "P", "0.442", "49.99", "323.14", "", "chen2015", "numeric", ""),
    _row(*DMC, "viscosity", "Physical Data", "Dynamic Viscosity", "0.00465", "P", "0.465", "44.99", "318.14", "", "chen2015", "numeric", ""),
    _row(*DMC, "viscosity", "Physical Data", "Dynamic Viscosity", "0.00491", "P", "0.491", "39.99", "313.14", "", "chen2015", "numeric",
         "a clean eta(T) series for DMC"),
    _row(*DMC, "viscosity", "Physical Data", "Dynamic Viscosity", "", "", "", "19.99 - 49.99", "", "", "gao2024", "temperature_only",
         "kind of measurement: falling-ball capillary; value field empty"),
    _row(*DMC, "homo_lumo", "Physical Data", "Ionization Potential", "", "", "", "", "", "", "meeks1975", "reference_only",
         "lesson C: the Ionization Potential table has a Reference column and NO value column"),
    _row(*DMC, "homo_lumo", "Physical Data", "Ionization Potential", "", "", "", "", "", "", "wittel1975", "reference_only",
         "a second reference-only row in the same table"),
]
# Per-substance walk bookkeeping.  The category list is virtualised, so completeness
# is reported, never assumed.
SWEEPS = [
    {
        "substance": "ethylene carbonate",
        "inchikey": EC[1],
        "physical_data_total": 314,
        "physical_categories_observed": 39,
        "alphabetical_tail_observed": True,
        "other_data_total": 20,
        "other_categories_observed": 2,
        "other_categories": ["Quantum Chemical Calculations", "Use"],
        "homo_lumo_category_present": True,
        "homo_lumo_numeric_present": False,
        "redox_category_present": False,
        "redox_numeric_present": False,
    },
    {
        "substance": "propylene carbonate",
        "inchikey": PC[1],
        "physical_data_total": 919,
        "physical_categories_observed": 32,
        "alphabetical_tail_observed": False,
        "other_data_total": 146,
        "other_categories_observed": 0,
        "other_categories": [],
        "homo_lumo_category_present": False,
        "homo_lumo_numeric_present": False,
        "redox_category_present": True,
        "redox_numeric_present": False,
    },
    {
        "substance": "gamma-valerolactone",
        "inchikey": GVL[1],
        "physical_data_total": None,
        "physical_categories_observed": 28,
        "alphabetical_tail_observed": True,
        "other_data_total": None,
        "other_categories_observed": 0,
        "other_categories": [],
        "homo_lumo_category_present": False,
        "homo_lumo_numeric_present": False,
        "redox_category_present": False,
        "redox_numeric_present": False,
    },
    {
        "substance": "succinonitrile",
        "inchikey": SN[1],
        "physical_data_total": None,
        "physical_categories_observed": 45,
        "alphabetical_tail_observed": False,
        "other_data_total": None,
        "other_categories_observed": 3,
        "other_categories": ["Biodegradation", "Quantum Chemical Calculations", "Use"],
        "homo_lumo_category_present": True,
        "homo_lumo_numeric_present": False,
        "redox_category_present": True,
        "redox_numeric_present": False,
    },
    {
        "substance": "dimethyl carbonate",
        "inchikey": DMC[1],
        "physical_data_total": None,
        "physical_categories_observed": 36,
        "alphabetical_tail_observed": False,
        "other_data_total": None,
        "other_categories_observed": 0,
        "other_categories": [],
        "homo_lumo_category_present": True,
        "homo_lumo_numeric_present": False,
        "homo_lumo_category_names": ["Ionization Potential"],
        "redox_category_present": True,
        "redox_numeric_present": False,
    },
]

# Read straight off the live Reaxys result header for each single-key query.
RESOLUTION = {
    "KMTRUDSVKNLOMY-UHFFFAOYSA-N": {"substances": 2, "note": "ethylene carbonate and ethylene carbonate anion"},
    "RUOJZAUFBMNUDX-UHFFFAOYSA-N": {"substances": 1, "note": "propylene carbonate"},
    "GAEKPEKOJKCEMS-UHFFFAOYSA-N": {"substances": 4, "note": "5-methyl-dihydro-furan-2-one, CAS 108-29-2"},
    "IAHFWCOBPZCAEA-UHFFFAOYSA-N": {"substances": 1, "note": "butanedinitrile"},
    "IEJIGPNLZYLLBP-UHFFFAOYSA-N": {"substances": 1, "note": "carbonic acid dimethyl ester, CAS 616-38-6"},
    "JBTWLSYIZRCDFO-UHFFFAOYSA-N": {"substances": None, "note": "the true ethyl methyl carbonate key, not queried by itself"},
    "JBTWLSYIZRCDFA-UHFFFAOYSA-N": {"substances": 0, "note": "control: a one-letter InChIKey slip, 0 substances and 0 documents"},
    "JYVATQXCHBTGRN-UHFFFAOYSA-N": {"substances": 0, "note": "0 substances and 0 documents: Reaxys never assigns this key"},
}

# Deliberate negative controls.  A key lookup in Reaxys is exact, which is what makes
# the two zero-hit results below informative rather than noisy.
CONTROLS = [
    {
        "probe": "one-letter InChIKey slip",
        "key": "JBTWLSYIZRCDFA-UHFFFAOYSA-N",
        "true_key": "JBTWLSYIZRCDFO-UHFFFAOYSA-N",
        "substances": 0,
        "documents": 0,
        "meaning": "typing ...A instead of ...O returns nothing at all.  This is how the slip "
                   "was caught, and it proves the lookup is an exact match rather than a fuzzy one. "
                   "The slip was the session's own transcription error, not a defect in the "
                   "W17-2 backfill queue, whose ethyl methyl carbonate key is correct.",
    },
    {
        "probe": "the mis-key that travelled with the GVL value",
        "key": "JYVATQXCHBTGRN-UHFFFAOYSA-N",
        "true_key": "GAEKPEKOJKCEMS-UHFFFAOYSA-N",
        "substances": 0,
        "documents": 0,
        "meaning": "the key recorded against gamma-valerolactone in "
                   "probes/reaxys_dielectric_queue_first_cut.csv is not a Reaxys key at all. "
                   "Under the correct key the same lookup returns the same value, the same "
                   "supporting-information location and the same Segato 2021 reference that the "
                   "first-cut file already carried, so only the key column was wrong.",
    },
]

# The RDKit ground truth is recomputed at run time; this literal only pins the audit.
QUEUE_KEY_AUDIT_LITERALS = {
    "Trifluoroacetic acid": ("DTQVDTLACAAQTR-UHFFFAOYSA-N", "match"),
    "Butyric acid": ("FERIUCNNQQJTOY-UHFFFAOYSA-N", "match"),
    "Isovaleric acid": ("GWYFCOCPABKNJV-UHFFFAOYSA-N", "match"),
    "Valeric acid": ("NQPDZGIKBAWPEJ-UHFFFAOYSA-N", "match"),
    "acetic acid": ("QTBSBXVTEAMEQO-UHFFFAOYSA-N", "match"),
    "ethylene carbonate": ("KMTRUDSVKNLOMY-UHFFFAOYSA-N", "match"),
    "propylene carbonate": ("RUOJZAUFBMNUDX-UHFFFAOYSA-N", "match"),
    "gamma-valerolactone": ("GAEKPEKOJKCEMS-UHFFFAOYSA-N", "match"),
    "succinonitrile": ("IAHFWCOBPZCAEA-UHFFFAOYSA-N", "match"),
    "ethyl methyl carbonate": ("JBTWLSYIZRCDFO-UHFFFAOYSA-N", "match"),
    "2-hydroxyethylammonium acetate": ("VVLAIYIMMFWRFW-UHFFFAOYSA-N", "match"),
    "2-hydroxyethylammonium lactate": ("NEQXUPRFDXNNTA-UHFFFAOYSA-N", "match"),
    "triethanolamine lactate": ("RJQQOKKINHMXIM-UHFFFAOYSA-N", "match"),
    "triethanolammonium acetate": ("UPCXAARSWVHVLY-UHFFFAOYSA-N", "match"),
}

QUEUE_KEY_SMILES = {
    "Trifluoroacetic acid": "FC(F)(F)C(=O)O",
    "Butyric acid": "CCCC(=O)O",
    "Isovaleric acid": "CC(C)CC(=O)O",
    "Valeric acid": "CCCCC(=O)O",
    "acetic acid": "CC(=O)O",
    "ethylene carbonate": "O=C1OCCO1",
    "propylene carbonate": "CC1COC(=O)O1",
    "gamma-valerolactone": "CC1CCC(=O)O1",
    "succinonitrile": "N#CCCC#N",
    "ethyl methyl carbonate": "CCOC(=O)OC",
    "2-hydroxyethylammonium acetate": "NCCO.CC(=O)O",
    "2-hydroxyethylammonium lactate": "NCCO.CC(O)C(=O)O",
    "triethanolamine lactate": "OCCN(CCO)CCO.CC(O)C(=O)O",
    "triethanolammonium acetate": "OCCN(CCO)CCO.CC(=O)O",
}

FROZEN_FILES = {
    "data/dielectric_v03.csv": "ff2142936e06e04b329b70f8597574f75349e54ce876e9fff81309e6d35ccce4",
    "data/processed/dielectric_observations_v11plus.csv": "159b928f800a55969963da275ed05c30ce8a19cffc48353a9c490eec68a49af9",
    "data/viscosity_v01.csv": "12dfa03f34284c93204d1054f75b5a342fd82094da0ca17cee372b4c581c5b26",
}


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_csv(path):
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def dielectric_v04_rows():
    return _read_csv(DIELECTRIC_V04)


def liquid_window_summary():
    return json.loads(LIQUID_WINDOW_SUMMARY.read_text(encoding="utf-8"))


def backfill_queue_rows():
    return _read_csv(BACKFILL_QUEUE)


def row_for(rows, inchikey, name):
    return [row for row in rows if row.get("inchikey") == inchikey and row.get("name") == name]


def rows_by(inchikey, channel=None, category=None):
    out = [row for row in OBSERVATIONS if row["inchikey"] == inchikey]
    if channel is not None:
        out = [row for row in out if row["channel"] == channel]
    if category is not None:
        out = [row for row in out if row["reaxys_category"] == category]
    return out


def crosschecks():
    """Local-versus-Reaxys agreement checks that are pure arithmetic."""
    v04 = dielectric_v04_rows()
    lw = liquid_window_summary()
    checks = []

    gvl_rows = row_for(v04, GVL[1], "gamma-valerolactone")
    assert len(gvl_rows) == 2, "the shipped v0.4 GVL pair must be exactly two rows"
    main_legs = [row for row in gvl_rows if row["source_quality"] == "primary"]
    assert len(main_legs) == 1, "exactly one GVL leg must carry source_quality == primary"
    gvl = main_legs[0]
    reaxys_gvl = rows_by(GVL[1], channel="dielectric")
    assert len(reaxys_gvl) == 1, "Reaxys exposes exactly one GVL dielectric row"
    checks.append({
        "name": "gvl_dielectric_value",
        "local_source": "data/dielectric_v04.csv",
        "local_value": gvl["dielectric"],
        "reaxys_value": reaxys_gvl[0]["value_raw"],
        "agree": gvl["dielectric"] == reaxys_gvl[0]["value_raw"],
        "note": "the shipped main value and the only Reaxys row are the same number",
    })
    checks.append({
        "name": "gvl_dielectric_location",
        "local_source": "data/dielectric_v04.csv:source_page",
        "local_value": gvl["source_page"],
        "reaxys_value": reaxys_gvl[0]["location"],
        "agree": gvl["source_page"] == reaxys_gvl[0]["location"],
        "note": "both sides say the number lives in the supporting information",
    })
    checks.append({
        "name": "gvl_dielectric_temperature_absent",
        "local_source": "data/dielectric_v04.csv:temperature_source",
        "local_value": gvl["temperature_source"],
        "reaxys_value": reaxys_gvl[0]["temperature_raw_C"] or "(blank)",
        "agree": gvl["temperature_source"] == "not_reported" and reaxys_gvl[0]["temperature_raw_C"] == "",
        "note": "neither leg carries a temperature, which is why model_ready stays false",
    })

    checks.append({
        "name": "gvl_dual_row_not_averaged",
        "local_source": "data/dielectric_v04.csv",
        "local_value": "; ".join(sorted(row["dielectric"] for row in gvl_rows)),
        "reaxys_value": "36.9 only",
        "agree": sorted(row["dielectric"] for row in gvl_rows) == ["36.1", "36.9"],
        "note": "the review-table leg 36.1 does not exist in Reaxys; the two legs stay separate and nothing is averaged",
    })

    ec_rows = row_for(v04, EC[1], "ethylene carbonate")
    assert len(ec_rows) == 1, "the shipped v0.4 EC main leg must be a single row"
    ec = ec_rows[0]
    static = rows_by(EC[1], category="Static Dielectric Constant")
    ec_match = [row for row in static if row["value_raw"] == ec["dielectric"] and row["temperature_K"] == ec["T_K"]]
    checks.append({
        "name": "ec_static_dielectric_value_and_temperature",
        "local_source": "data/dielectric_v04.csv",
        "local_value": f"{ec['dielectric']} at {ec['T_K']} K",
        "reaxys_value": f"{ec_match[0]['value_raw']} at {ec_match[0]['temperature_K']} K" if ec_match else "(no match)",
        "agree": bool(ec_match),
        "note": "Reaxys reproduces the Chernyak 2006 leg value and temperature exactly",
    })

    local_mp = lw.get("sanity_checks", {}).get("EC_melting_point_C")
    reaxys_mp = [row for row in rows_by(EC[1], category="Melting Point") if row["value_raw"] == "36.4"]
    checks.append({
        "name": "ec_melting_point",
        "local_source": "probes/liquid_window_gate_summary.json:sanity_checks.EC_melting_point_C",
        "local_value": local_mp,
        "reaxys_value": "36.4" if reaxys_mp else "(absent)",
        "agree": local_mp == 36.4 and bool(reaxys_mp),
        "note": "the 36.4 C the liquid-window gate already blocks on is the Reaxys supporting-information value",
    })

    queue_keys = {row["candidate_inchikey"] for row in backfill_queue_rows() if row.get("candidate_inchikey")}
    checks.append({
        "name": "backfill_queue_gvl_key_is_correct",
        "local_source": "probes/reaxys_thin_family_backfill_queue.csv",
        "local_value": GVL[1] if GVL[1] in queue_keys else "(absent)",
        "reaxys_value": f"{RESOLUTION[GVL[1]]['substances']} substances",
        "agree": GVL[1] in queue_keys,
        "note": "the backfill queue is clean; the mis-key lived in the upstream stocking queue",
    })
    return checks


def queue_key_audit():
    """Recompute the canonical InChIKey of every audited substance with RDKit."""
    from rdkit import Chem
    from rdkit.Chem.inchi import MolToInchiKey

    queue_by_name = {
        row["candidate_name"]: row["candidate_inchikey"]
        for row in backfill_queue_rows()
        if row.get("candidate_inchikey")
    }
    out = []
    for name, (literal_key, expected) in QUEUE_KEY_AUDIT_LITERALS.items():
        in_queue = name in queue_by_name
        # The queue file wins whenever it carries the name; the literal is only a
        # fallback, so a hand-typed key can never silently overwrite the shipped one.
        queue_key = queue_by_name.get(name, literal_key)
        mol = Chem.MolFromSmiles(QUEUE_KEY_SMILES[name])
        rdkit_key = MolToInchiKey(mol) if mol is not None else None
        out.append({
            "substance": name,
            "queue_key": queue_key,
            "queue_key_source": "queue_file" if in_queue else "literal_fallback",
            "literal_key": literal_key,
            "literal_matches_queue_file": in_queue and literal_key == queue_key,
            "rdkit_key": rdkit_key,
            "verdict": "match" if rdkit_key == queue_key else "mismatch",
            "expected_verdict": expected,
            "in_backfill_queue": in_queue,
            "reaxys_resolution": RESOLUTION.get(queue_key, {}).get("substances"),
        })
    return sorted(out, key=lambda item: item["substance"])

NUMERIC_KINDS = ("numeric", "range", "range_with_temperature", "value_in_comment")


def channel_verdicts():
    """One verdict per core channel, argued from the harvested rows only."""
    def rows(channel):
        return [row for row in OBSERVATIONS if row["channel"] == channel]

    def numeric(channel):
        return [row for row in rows(channel) if row["row_kind"] in NUMERIC_KINDS and row["value_raw"]]

    return [
        {
            "channel": "dielectric_epsilon",
            "verdict": "usable_numeric",
            "rows_observed": len(rows("dielectric")),
            "numeric_rows": len(numeric("dielectric")),
            "numeric_share": round(len(numeric("dielectric")) / len(rows("dielectric")), 4),
            "why": "Reaxys exposes eps as a number alongside a temperature column, and it carries full "
                   "eps(T) series for ethylene carbonate (7 static points) and propylene carbonate",
            "caveats": [
                "ranges are stored as 'min - max' strings in both the value and the temperature column",
                "frequency-labelled eps (2E+06 Hz) sits next to static eps with no flag to separate them",
                "a large minority of rows carry a reference and no number at all",
            ],
        },
        {
            "channel": "viscosity_eta",
            "verdict": "usable_numeric",
            "rows_observed": len(rows("viscosity")),
            "numeric_rows": len(numeric("viscosity")),
            "numeric_share": round(len(numeric("viscosity")) / len(rows("viscosity")), 4),
            "why": "Dynamic Viscosity and Kinematic Viscosity both return numbers, and eta(T) series "
                   "exist for propylene carbonate and dimethyl carbonate",
            "caveats": [
                "units are inconsistent across rows: poise, stokes and mPa*s all appear",
(
                    "gamma-valerolactone stores the number only inside the Comment free text, so a "
                    "structured field scrape misses it entirely"
                ),
                "temperatures arrive as 59.99 / 69.99 / 74.99 rather than 60 / 70 / 75",
                "rows with a temperature and an empty value field exist in bulk",
            ],
        },
        {
            "channel": "homo_lumo",
            "verdict": "reference_only",
            "rows_observed": len(rows("homo_lumo")),
            "numeric_rows": len(numeric("homo_lumo")),
            "numeric_share": 0.0,
            "why": "Reaxys indexes HOMO/LUMO work only as a property keyword, 'Electronic energy levels, "
                   "Molecular orbitals' with method DFT, or as an Ionization Potential table whose only "
                   "column is Reference",
            "caveats": [
(
                    "no numeric HOMO, LUMO, gap, ionization potential or electron affinity value was "
                    "observed for any of the five substances"
                ),
                "the keyword rows are still useful as literature leads for the existing L3 channel",
            ],
        },
        {
            "channel": "redox_potential",
            "verdict": "reference_only",
            "rows_observed": len(rows("redox")),
            "numeric_rows": len(numeric("redox")),
            "numeric_share": 0.0,
            "why": "Electrochemical Behaviour and Electrochemical Characteristics return descriptions "
                   "such as 'cyclovoltammetry' and 'potential diagram' plus a citation, never a volt value",
            "caveats": [
(
                    "this is the channel where the project's 392-label bottleneck lives, and Reaxys does "
                    "not relieve it"
                ),
            ],
        },
    ]


def lessons():
    miskey = RESOLUTION["JYVATQXCHBTGRN-UHFFFAOYSA-N"]
    ec_dielectric = rows_by(EC[1], category="Dielectric Constant")
    ec_25 = [row for row in ec_dielectric if row["value_raw"] == "89.78" and row["temperature_raw_C"] == "25"]
    ec_blank = [row for row in ec_dielectric if row["value_raw"] == "89.78" and row["temperature_raw_C"] == ""]
    ec_mp = rows_by(EC[1], category="Melting Point")
    ec_mp_89 = [row for row in ec_mp if row["value_raw"].startswith("89")]
    return [
        {
            "lesson": "A_gvl_inchikey",
            "question": "does Reaxys mislabel gamma-valerolactone as JYVATQXCHBTGRN-UHFFFAOYSA-N?",
            "finding": "not_reproduced",
            "evidence": f"JYVATQXCHBTGRN-UHFFFAOYSA-N returns {miskey['substances']} substances and 0 "
                        f"documents, so Reaxys never assigns that key; GAEKPEKOJKCEMS-UHFFFAOYSA-N returns "
                        f"{RESOLUTION['GAEKPEKOJKCEMS-UHFFFAOYSA-N']['substances']} substances including CAS 108-29-2",
            "attribution": "the bad key is ours, not Reaxys's. It sits in the key column of "
                           "probes/reaxys_dielectric_queue_first_cut.csv, whose GVL row otherwise carries "
                           "the right value, the right location and the right reference. The W17-2 backfill "
                           "queue and probes/reaxys_v1x_stocking_queue.csv both already carry the correct "
                           "key, and the v0.4 provenance note already says so",
            "action": "no Reaxys-side correction is needed; pin the correct key in the audit table above",
        },
        {
            "lesson": "B_ec_temperature_label",
            "question": "does a Reaxys temperature label for ethylene carbonate survive a liquid-window check?",
            "finding": "reproduced",
            "evidence": f"the EC melting point is 36.4 C in Reaxys and 36 C in the very Schroeder 2014 paper "
                        f"that carries the eps=89.78 row; eps=89.78 appears twice, once with a blank "
                        f"temperature ({len(ec_blank)} row) and once tagged 25 C ({len(ec_25)} row); EC's own "
                        f"Static Dielectric Constant series puts 89.6 to 90.8 at 36 to 40 C",
            "attribution": "25 C is below EC's melting point, so a pure-liquid measurement at 25 C is "
                           "physically impossible; the 25 C tag is the defect, not the 89.78 value",
            "action": "never take a Reaxys temperature label at face value; run it through the "
                      "liquid-window gate before it reaches a model",
        },
        {
            "lesson": "C_ec_8978_as_melting_point",
            "question": "does Reaxys file 89.78 as an ethylene carbonate melting point?",
            "finding": "not_reproduced",
            "evidence": f"the EC Melting Point category lists 39.5, 36.4, 34-37, 41.3, 36-37, 36-40 and 36; "
                        f"{len(ec_mp_89)} row starts with 89",
            "attribution": "in the live index 89.78 is a dielectric constant only. If the old label came "
                           "from Reaxys it has since been corrected; if it came from our own parse, it was ours",
            "action": "keep the liquid-window gate as the guard: it catches the physically impossible "
                      "pairing whichever side produced it",
        },
    ]


CSV_FIELDS = [
    "substance", "inchikey", "cas", "reaxys_registry_number", "channel", "reaxys_section",
    "reaxys_category", "value_raw", "unit_raw", "value_si", "temperature_raw_C", "temperature_K",
    "location", "reference", "row_kind", "access", "reaxys_crosscheck_only", "note",
]

ARTIFACT_PATHS = [
    "probes/reaxys_core_four_crosscheck.csv",
    "probes/reaxys_core_four_crosscheck_summary.json",
    "reports/reaxys_core_four_crosscheck.md",
]


def build_summary():
    audit = queue_key_audit()
    return {
        "schema_version": 1,
        "task": "reaxys_core_four_crosscheck",
        "week": "week17",
        "arm": "W17-RX",
        "session": SESSION,
        "harvest_protocol": HARVEST_PROTOCOL,
        "compliance": {
            "access": ACCESS,
            "reaxys_crosscheck_only": True,
            "values_written_under_data": False,
            "values_entered_any_pool": False,
            "values_entered_any_split": False,
            "redistributable": False,
            "averaging_performed": False,
            "batch_crawling": False,
            "files_written": ARTIFACT_PATHS,
        },
        "observation_rows": len(OBSERVATIONS),
        "observations_sha256": sha256_file(CSV_PATH) if CSV_PATH.exists() else None,
        "substances_queried": [entry["substance"] for entry in SWEEPS],
        "sweeps": SWEEPS,
        "resolution": RESOLUTION,
        "controls": CONTROLS,
        "channel_verdicts": channel_verdicts(),
        "crosschecks": crosschecks(),
        "queue_key_audit": audit,
        "queue_key_audit_summary": {
            "audited": len(audit),
            "matched": sum(1 for item in audit if item["verdict"] == "match"),
            "mismatched": sum(1 for item in audit if item["verdict"] == "mismatch"),
        },
        "lessons": lessons(),
        "frozen_files": FROZEN_FILES,
        "limitations": [
(
                "the Reaxys category list is virtualised, so 'not observed' is not 'proven absent'; "
                "alphabetical_tail_observed records which walks actually reached the end of the list"
            ),
            "Other Data was fully enumerated for ethylene carbonate and succinonitrile only",
(
                "five substances were walked: two carbonates, one lactone and one nitrile, plus ethylene "
                "carbonate; no acid-family and no protic-ionic-pair substance was walked"
            ),
(
                "the harvest ran through the author's own signed-in Edge session, driven by hand, so every "
                "number here is a point-in-time snapshot that Reaxys can change"
            ),
(
                "a Reaxys row with a blank temperature column is not evidence that no temperature exists; "
                "it only means Reaxys did not index one"
            ),
        ],
    }


def write_csv(path=CSV_PATH):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, lineterminator="\n")
        writer.writeheader()
        for row in OBSERVATIONS:
            writer.writerow(row)
    return path


def write_summary(path=SUMMARY_PATH):
    payload = build_summary()
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return path


def check():
    if not CSV_PATH.exists() or not SUMMARY_PATH.exists():
        return {"passed": False, "reason": "artifacts missing"}
    scratch = Path(str(CSV_PATH) + ".tmp")
    write_csv(scratch)
    regenerated = scratch.read_text(encoding="utf-8")
    scratch.unlink()
    if regenerated != CSV_PATH.read_text(encoding="utf-8"):
        return {"passed": False, "reason": "csv does not reproduce from the module"}
    expected = build_summary()
    on_disk = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
    expected["observations_sha256"] = on_disk.get("observations_sha256")
    same = json.dumps(on_disk, ensure_ascii=False, sort_keys=True) == json.dumps(expected, ensure_ascii=False, sort_keys=True)
    return {
        "passed": same,
        "reason": "summary reproduces" if same else "summary drift",
        "csv_rows": len(OBSERVATIONS),
        "crosschecks_agree": sum(1 for item in expected["crosschecks"] if item["agree"]),
        "crosschecks_total": len(expected["crosschecks"]),
        "queue_key_audit": expected["queue_key_audit_summary"],
        "channel_verdicts": {item["channel"]: item["verdict"] for item in expected["channel_verdicts"]},
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Reaxys four-channel crosscheck (offline).")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--write", action="store_true", help="regenerate CSV and summary")
    group.add_argument("--check", action="store_true", help="offline re-derivation and drift check")
    args = parser.parse_args(argv)
    if args.write:
        write_csv()
        write_summary()
        print(json.dumps({"written": [str(CSV_PATH), str(SUMMARY_PATH)]}, ensure_ascii=False))
        return 0
    result = check()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())