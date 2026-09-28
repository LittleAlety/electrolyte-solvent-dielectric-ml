"""Week 20 -- W20-6a: is the Org-Mol dielectric set admissible, or only a lead?

Registered skeleton, now extended to execute.  The module fits no model, reads
no prediction table, takes no shot number, touches no frozen artefact and makes
no network request.

The lead
--------
Org-Mol is described as a fine-tuning set of 850+ organic liquids carrying an
experimental dielectric constant near 25 C.  That window sits inside this
repository accepted band of 283.15-303.15 K, and the set is absent from the
Week 17 thirteen-source census -- ThermoML, PubChem PUG-View, Europe PMC twice,
NIST WebBook, Zenodo 8252886, the HuggingFace thermophysical set, figshare,
Dryad, foundry-ml, molssiai, the Na-ion boxes and ORD_reaction -- which is the
only reason it is worth a probe at all.

The three gates, in order
-------------------------
1. licence     a verdict read from the source own licence text must be recorded
               before a single row is classified.
2. locator     every accepted row needs a DOI plus a table or figure locator.  A
               row that cannot be located is a lead, not data.
3. first_hand  the locating reference is re-checked against the primary source,
               not taken from the compiling set own metadata.

The three exit classes
----------------------
    admissible     licence ok, locator present, first-hand check recorded
    needs_lead     licence ok, locator missing or incomplete
    inadmissible   licence restricted or unknown, or outside the accepted window

Only admissible rows may enter a pool.  needs_lead rows still earn their keep:
they say which compounds carry a value and are worth chasing in an open primary
source, but they must not be counted as a ceiling break.  That is the honest
downgrade the Week 20 charter anticipates for compiled ML sets, and this file is
where it gets applied.

What the source screen found (2026-09-28)
-----------------------------------------
The lead resolves to the Org-Mol representation model of Ou et al., npj
Computational Materials 11, 224 (2025), DOI 10.1038/s41524-025-01720-4 (arXiv
2501.09896).  Its near-25-C dielectric fine-tuning data is collected from
ref. 53 (the CRC Handbook of Chemistry and Physics, 2014) and ref. 54 (Wohlfahrt,
Landolt-Boernstein "2 pure liquids: Data", Springer Materials, (c) 1991
Springer-Verlag Berlin Heidelberg).  Both are restricted compilations and both
sit on the Week 20 do-not list.  The paper data-availability statement releases
the complete fine-tuning datasets only upon reasonable request, so the set is not
released and no row-level DOI + table/figure locator exists.  The gates therefore
read licence = restricted, locator = unreachable, first-hand = unreachable, and
the source is inadmissible.  No row is classified and no count is invented: the
honest row-level statement is source_not_obtainable.

What this module refuses to do
------------------------------
The source table is not in this repository, so run() still has nothing to
classify and says so rather than guessing a schema.  LICENCE_VERDICT stays a
preregistration field, not a default, so no row can be classified before the
licence has been read.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from electrolyte_ml.pathing import portable_relative_path

V03_ROSTER_PATH = REPOSITORY_ROOT / "data" / "dielectric_v03.csv"
SUMMARY_PATH = REPOSITORY_ROOT / "probes" / "w20_orgmol_provenance_summary.json"
PREREG_PATH = REPOSITORY_ROOT / "probes" / "w20_orgmol_provenance_prereg.json"

#: The verdicts a licence review may return.  None means "not yet read".
LICENCE_VERDICTS = ("open", "attribution_required", "restricted", "unknown")
LICENCE_VERDICT: str | None = None

ACCESS_CLASSES = ("admissible", "needs_lead", "inadmissible")

#: The source columns this module requires the normalised table to carry.
#: inchikey is required rather than derived, so the plate cannot move silently.
REQUIRED_COLUMNS = ("inchikey", "smiles", "epsilon", "temperature_C")
LOCATOR_COLUMNS = ("doi", "locator")

ACCEPTED_WINDOW_K = (283.15, 303.15)

#: Reasons that bar a row from any pool outright; the rest only downgrade it to
#: a lead.  Kept as data so the split is reviewable rather than buried in an if.
FATAL_REASONS = frozenset(
    {"licence_not_cleared", "no_inchikey", "outside_283.15_303.15_K"}
)

#: What the lead actually is, read from the source own text on 2026-09-28.
SOURCE_IDENTITY = {
    "name": "Org-Mol",
    "description": (
        "3D-transformer molecular representation model pre-trained on 60 million "
        "PM6-optimised small-organic-molecule structures, then fine-tuned on public "
        "experimental bulk properties"
    ),
    "paper_title": (
        "High-accuracy physical property prediction for pure organics via molecular "
        "representation learning: bridging data to discovery"
    ),
    "journal": "npj Computational Materials 11, 224 (2025)",
    "doi": "10.1038/s41524-025-01720-4",
    "arxiv": "2501.09896",
    "upstream_framework": "Uni-Mol (github.com/DeepModeling/Uni-Mol)",
    "composition_warning": (
        "Org-Mol is a model; the 850+ near-room dielectric values are a fine-tuning "
        "set compiled from restricted sources, not a newly measured collection"
    ),
}

#: The licence of the compilation that carries the near-room dielectric values,
#: as its own reference list and data-availability statement give it.
LICENCE_READING = {
    "verdict": "restricted",
    "compilation_released": False,
    "article_licence": "CC BY-NC-ND 4.0",
    "data_availability_quote": (
        "Complete fine-tuning datasets can be obtained upon reasonable request by "
        "contacting the corresponding authors."
    ),
    "epsilon_provenance_refs": [
        {
            "ref": "53",
            "citation": "Haynes, W. CRC Handbook of Chemistry and Physics (CRC Press, 2014).",
            "access_class": "restricted",
            "on_week20_do_not_list": True,
        },
        {
            "ref": "54",
            "citation": (
                "Wohlfahrt, C. 2 pure liquids: Data. Springer Materials, "
                "sm_lbs_978-3-540-47619-1_2, (c) 1991 Springer-Verlag Berlin Heidelberg."
            ),
            "access_class": "restricted",
            "on_week20_do_not_list": True,
        },
    ],
}

#: The three gates, in order, as read at source level.
THREE_GATE_RESULT = {
    "gate_1_licence": {
        "verdict": "restricted",
        "cleared": False,
        "reason": (
            "the fine-tuning set is not released, and its near-room dielectric values "
            "are compiled from two restricted sources (CRC Handbook; Landolt-Boernstein "
            "via Springer Materials), both on the Week 20 do-not list"
        ),
    },
    "gate_2_locator": {
        "verdict": "unreachable",
        "cleared": False,
        "reason": (
            "no per-row DOI + table/figure locator is published; the paper cites only "
            "the two compilations (refs 53 and 54) at series level"
        ),
    },
    "gate_3_first_hand": {
        "verdict": "unreachable",
        "cleared": False,
        "reason": ("gate 2 has no located row to re-check, and the primary sources are paywalled"),
    },
}

SOURCE_LEVEL_ACCESS_CLASS = "inadmissible"


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def read_fieldnames(path: Path) -> list[str]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        return next(reader, [])


def missing_columns(fieldnames: Sequence[str] | None) -> list[str]:
    present = set(fieldnames or ())
    required = [*REQUIRED_COLUMNS, *LOCATOR_COLUMNS]
    return [column for column in required if column not in present]


def celsius_to_kelvin(value: object) -> float | None:
    try:
        return float(value) + 273.15
    except (TypeError, ValueError):
        return None


def inside_window(temperature_c: object) -> bool:
    kelvin = celsius_to_kelvin(temperature_c)
    if kelvin is None:
        return False
    low, high = ACCEPTED_WINDOW_K
    return low <= kelvin <= high


def row_reasons(row: Mapping[str, str], *, licence_verdict: str | None) -> list[str]:
    """Every gate this row fails, in gate order."""

    reasons: list[str] = []
    if licence_verdict != "open" and licence_verdict != "attribution_required":
        reasons.append("licence_not_cleared")
    if not str(row.get("inchikey", "")).strip():
        reasons.append("no_inchikey")
    if not str(row.get("doi", "")).strip():
        reasons.append("no_doi")
    if not str(row.get("locator", "")).strip():
        reasons.append("no_table_or_figure_locator")
    if not inside_window(row.get("temperature_C")):
        reasons.append("outside_283.15_303.15_K")
    return reasons


def classify_row(
    row: Mapping[str, str], *, licence_verdict: str | None
) -> tuple[str, list[str]]:
    """Return the access class and the failed gates for one row."""

    reasons = row_reasons(row, licence_verdict=licence_verdict)
    if FATAL_REASONS & set(reasons):
        return "inadmissible", reasons
    if reasons:
        return "needs_lead", reasons
    return "admissible", reasons


def classify_table(
    rows: Iterable[Mapping[str, str]], *, licence_verdict: str | None
) -> dict[str, list[dict[str, object]]]:
    """Split a normalised source table into the three access classes."""

    buckets: dict[str, list[dict[str, object]]] = {name: [] for name in ACCESS_CLASSES}
    for row in rows:
        access_class, reasons = classify_row(row, licence_verdict=licence_verdict)
        buckets[access_class].append({**dict(row), "reasons": reasons})
    return buckets


def roster_key_set(rows: Iterable[Mapping[str, str]]) -> set[str]:
    return {str(row["inchikey"]) for row in rows if row.get("inchikey")}


def overlap_with_roster(
    candidate_keys: Iterable[str], roster_keys: set[str], *, sample_size: int = 20
) -> dict[str, object]:
    """How much of the candidate set would be new to the frozen v03 roster."""

    keys = {key for key in candidate_keys if key}
    fresh = keys - roster_keys
    return {
        "candidate_keys": len(keys),
        "roster_keys": len(roster_keys),
        "already_in_roster": len(keys & roster_keys),
        "new_keys": len(fresh),
        "new_keys_sample": sorted(fresh)[:sample_size],
    }


def blocking_conditions(
    *, source_path: Path | None = None, licence_verdict: str | None = LICENCE_VERDICT
) -> list[str]:
    """Everything the preregistration must pin before a row may be classified."""

    blockers: list[str] = []
    if licence_verdict is None:
        blockers.append("LICENCE_VERDICT is unset; read the source licence text first")
    elif licence_verdict not in LICENCE_VERDICTS:
        blockers.append(f"LICENCE_VERDICT is not a pinned verdict: {licence_verdict!r}")
    if source_path is None:
        blockers.append("SOURCE_PATH is unset; the Org-Mol table is not in this repository")
    elif not Path(source_path).is_file():
        blockers.append(f"SOURCE_PATH does not exist: {source_path}")
    return blockers


def plan() -> dict[str, object]:
    """The pinned configuration, printable without classifying anything."""

    return {
        "schema_version": "w20_orgmol_provenance_plan_v0",
        "task": "week20_w20_6a_orgmol_provenance_probe",
        "status": "preregistered",
        "preregistered_by": "reports/week20_project_charter.md section 1 (W20-6a)",
        "not_executed_this_week": True,
        "produces_reading": False,
        "promotes_no_reading": True,
        "main_scoreboard_untouched": True,
        "scoreboard_attempts_delta": 0,
        "shot_number_taken": None,
        "licence_verdict": LICENCE_VERDICT,
        "licence_verdicts": list(LICENCE_VERDICTS),
        "access_classes": list(ACCESS_CLASSES),
        "fatal_reasons": sorted(FATAL_REASONS),
        "required_columns": list(REQUIRED_COLUMNS),
        "locator_columns": list(LOCATOR_COLUMNS),
        "accepted_window_K": list(ACCEPTED_WINDOW_K),
        "absence_from_week17_census": [
            "thermoml",
            "pubchem_pug_view",
            "europe_pmc_a",
            "europe_pmc_b",
            "nist_webbook",
            "zenodo_8252886",
            "huggingface_thermophysical",
            "figshare",
            "dryad",
            "foundry_ml",
            "molssiai",
            "na_ion_boxes",
            "ord_reaction",
        ],
        "roster": portable_relative_path(V03_ROSTER_PATH, root=REPOSITORY_ROOT),
        "blocking_conditions": blocking_conditions(),
    }


def source_screen() -> dict[str, object]:
    """The source-level three-gate result, with no row-level table in hand."""

    screen = plan()
    screen.update(
        {
            "status": "source_screened_not_obtainable",
            "ceiling_break": False,
            "source_identity": SOURCE_IDENTITY,
            "licence_reading": LICENCE_READING,
            "three_gate_result": THREE_GATE_RESULT,
            "source_level_access_class": SOURCE_LEVEL_ACCESS_CLASS,
            "row_level_classification": {
                "status": "source_not_obtainable",
                "admissible": 0,
                "needs_lead": 0,
                "inadmissible": 0,
                "note": (
                    "the row-level Org-Mol table is neither in this repository nor "
                    "publicly released, so no row is classified and no count is "
                    "invented"
                ),
            },
            "downgrade": (
                "were the set obtainable it would be a lead set only (which compounds "
                "carry a value), never a ceiling break, and its restricted provenance "
                "would make it inadmissible regardless"
            ),
        }
    )
    return screen


def run(
    *,
    source_path: Path | None = None,
    roster_path: Path = V03_ROSTER_PATH,
    licence_verdict: str | None = LICENCE_VERDICT,
    sample_size: int = 20,
) -> dict[str, object]:
    """Classify a normalised Org-Mol table.  Refuses while unarmed."""

    blockers = blocking_conditions(source_path=source_path, licence_verdict=licence_verdict)
    if blockers:
        raise SystemExit("W20-6a is not armed: " + "; ".join(blockers))
    assert source_path is not None

    missing = missing_columns(read_fieldnames(source_path))
    if missing:
        raise SystemExit("the source table is missing required columns: " + ", ".join(missing))

    buckets = classify_table(
        read_csv_rows(source_path), licence_verdict=licence_verdict
    )
    roster_keys = roster_key_set(read_csv_rows(roster_path))

    roster_overlap: dict[str, object] = {}
    for name in ACCESS_CLASSES:
        roster_overlap[name] = overlap_with_roster(
            (str(row["inchikey"]) for row in buckets[name]),
            roster_keys,
            sample_size=sample_size,
        )

    return {
        **plan(),
        "status": "executed",
        "not_executed_this_week": False,
        "produces_reading": True,
        "ceiling_break": False,
        "source": portable_relative_path(source_path, root=REPOSITORY_ROOT),
        "row_counts": {name: len(buckets[name]) for name in ACCESS_CLASSES},
        "roster_overlap": roster_overlap,
    }


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--plan", action="store_true", help="print the pinned plan and exit")
    parser.add_argument(
        "--source-screen",
        action="store_true",
        help="apply the three gates at source level (default when no table is given)",
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=None,
        help="the normalised Org-Mol table (inchikey, smiles, epsilon, temperature_C, doi, locator)",
    )
    parser.add_argument(
        "--licence-verdict",
        choices=LICENCE_VERDICTS,
        default=None,
        help="the verdict read from the source licence text; no default on purpose",
    )
    parser.add_argument("--write-summary", action="store_true", help="write the summary JSON")
    parser.add_argument("--summary", type=Path, default=SUMMARY_PATH)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.plan:
        print(json.dumps(plan(), ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    if args.source is not None:
        summary = run(source_path=args.source, licence_verdict=args.licence_verdict)
    else:
        summary = source_screen()
    if args.write_summary:
        args.summary.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover - manual inspection helper
    raise SystemExit(main())
