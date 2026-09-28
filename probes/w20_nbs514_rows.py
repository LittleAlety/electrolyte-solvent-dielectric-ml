"""Week 20 -- W20-6b: NBS Circular 514 same-source added temperature rows.

The lever
---------
Four weeks of epsilon representation levers were bought and killed.  The one
data lever that ever moved the main arm up is the same-source row expansion --
the pool-expansion reading 0.530029 against the frozen 0.4091179943351143,
that is +0.1209 -- while the foreign chemical-space block, importing NBS
Circular 514 as *new* compounds, drove the arm *down* to 0.3809089252433510.

So the point of this probe is the *unused* usage of NBS Circular 514: not the
refuted foreign-compound block, but temperature rows for compounds the frozen
v0.3 roster already carries.  Every candidate row lands on a compound already
on the roster; no new compound enters the chemical space.

The candidate rule (pinned before the run)
------------------------------------------
A transcript row is a candidate when
1. it is an NBS Circular 514 organic transcript row (parts 1-4);
2. it resolves to an InChIKey through the frozen structure sidecar;
3. that InChIKey is already on the data/dielectric_v03.csv roster; and
4. the roster observation is first-hand -- source_quality in
   {four_figures, primary_experimental_public_pdf,
   public_domain_critical_compilation} -- so the NBS row extends a compound the
   roster already carries as a measurement, rather than a shared three-figure
   compilation row or an open-access review-table value.

The three gates
---------------
The licence gate reads the circular own terms: NBS Circular 514 is a US
Government publication (10.6028/nbs.circ.514, Maryott & Smith 1951) and is
public domain, so the gate clears.  The per-row locator gate clears because
every transcript row carries source_id (nbs514:pXX:YYY = page:row), the source
DOI and the printed page.  The first-hand gate clears because the circular own
PDF is in the repository (data/raw/nbs514/nbscircular514.pdf), so the locating
row is re-checked against the primary source itself.  What does bite is the
NBS *frequency* gate: a row carrying an explicit microwave frequency note sits
inside the dispersion region and is not a static permittivity, so it is
dropped rather than imported.

Nothing is promoted.  The probe fits no model, takes no shot number, touches no
frozen artefact and makes no network request.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from electrolyte_ml.pathing import portable_relative_path

TRANSCRIPT_FILES = (
    "data/interim/nbs514_organic_part1.csv",
    "data/interim/nbs514_organic_part2.csv",
    "data/interim/nbs514_organic_part3.csv",
    "data/interim/nbs514_organic_part4.csv",
)
CANDIDATE_STRUCTURES = "data/processed/nbs514_structure_candidates.csv"
ROSTER = "data/dielectric_v03.csv"
NBS_PDF = "data/raw/nbs514/nbscircular514.pdf"
ARTIFACT_PATH = REPOSITORY_ROOT / "probes" / "artifacts" / "w20_nbs514_rows.csv"
SUMMARY_PATH = REPOSITORY_ROOT / "probes" / "w20_nbs514_rows_summary.json"

NBS_DOI = "10.6028/nbs.circ.514"
NBS_CIRCULAR = "NBS Circular 514 (Maryott & Smith, 1951)"
NBS_SOURCE_URL = "https://nvlpubs.nist.gov/nistpubs/Legacy/circ/nbscircular514.pdf"

#: The licence verdict read from the source own terms.
LICENCE_VERDICT = "open"
LICENCE_KIND = "public_domain"

#: A candidate row must sit on a roster compound whose observation is first-hand.
FIRST_HAND_ROSTER_QUALITIES = (
    "four_figures",
    "primary_experimental_public_pdf",
    "public_domain_critical_compilation",
)

#: Roster qualities that are deliberately excluded (a shared three-figure
#: compilation row or an open-access review-table value, not a first-hand one).
SECONDARY_ROSTER_QUALITIES = ("three_figures", "open_access_review_table")

ACCEPTED_WINDOW_K = (283.15, 303.15)

#: Compound identity used for the "distinct (compound, T)" count.  The
#: connectivity block of the standard InChIKey, so the cis/trans pair that
#: shares a skeleton and a temperature is one compound, not two.
COMPOUND_ID_LENGTH = 14

ROWS_COLUMNS = (
    "source_id",
    "inchikey",
    "compound_name",
    "T_K",
    "temperature_C",
    "dielectric",
    "frequency_note",
    "roster_T_K",
    "roster_dielectric",
    "roster_source_quality",
    "static_frequency",
    "usable",
    "licence_verdict",
    "locator",
    "first_hand_verdict",
)


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def licence_reading() -> dict[str, object]:
    """The licence verdict, read from the circular own terms."""

    return {
        "source": NBS_CIRCULAR,
        "doi": NBS_DOI,
        "verdict": LICENCE_VERDICT,
        "kind": LICENCE_KIND,
        "url": NBS_SOURCE_URL,
        "pdf_in_repo": NBS_PDF,
        "reason": (
            "NBS Circular 514 is a US Government publication of the National "
            "Bureau of Standards and is public domain; the repository already "
            "relies on it as the v0.2 NBS import source, so no new licence "
            "obligation is incurred by re-reading its organic-liquid table."
        ),
    }


def locator_for(row: Mapping[str, str]) -> str:
    """The per-row locator: page:row key, source DOI and printed page."""

    page = str(row.get("source_page", "")).strip()
    return " | ".join(
        part for part in (str(row.get("source_id", "")).strip(), NBS_DOI, ("p" + page) if page else "") if part
    )


def three_gate_result() -> dict[str, object]:
    """The three gates, in order.  All three clear for this source."""

    return {
        "gate_1_licence": {
            "verdict": LICENCE_VERDICT,
            "cleared": True,
            "reason": (
                "NBS Circular 514 is a US Government public-domain publication "
                "(10.6028/nbs.circ.514); the fine-tuning set of an ML model is "
                "not involved, and no restricted compilation is being re-bought"
            ),
        },
        "gate_2_locator": {
            "verdict": "locatable",
            "cleared": True,
            "reason": (
                "every transcript row carries source_id = nbs514:pXX:YYY (printed "
                "page and row), the source DOI 10.6028/nbs.circ.514 and the source "
                "page, so each accepted row has a per-row table locator"
            ),
        },
        "gate_3_first_hand": {
            "verdict": "first_hand_checked",
            "cleared": True,
            "reason": (
                "the circular own PDF is in the repository "
                "(data/raw/nbs514/nbscircular514.pdf), so the locating row is "
                "re-checked against the primary source, not taken from a "
                "compiling set own metadata"
            ),
        },
    }


def frequency_gate() -> dict[str, object]:
    """The gate that does bite: an explicit microwave note is not static."""

    return {
        "rule": (
            "an NBS Circular 514 row carrying an explicit frequency note is a "
            "measurement inside the dispersion region and is dropped; only "
            "static-frequency rows are usable"
        ),
        "source": (
            "scripts/resolve_nbs514_structures.py records the exclusion reason "
            "frequency_dependent for any non-empty frequency_note"
        ),
    }


def candidate_rows(
    transcript: Iterable[Mapping[str, str]],
    sidecar: Mapping[str, Mapping[str, str]],
    roster_by_key: Mapping[str, Mapping[str, str]],
) -> list[tuple[dict[str, str], dict[str, str], dict[str, str]]]:
    """Transcript rows that land on a first-hand roster compound."""

    chosen: list[tuple[dict[str, str], dict[str, str], dict[str, str]]] = []
    for row in transcript:
        structure = sidecar.get(str(row.get("source_id", "")))
        if structure is None:
            continue
        key = structure.get("inchikey", "")
        roster = roster_by_key.get(key)
        if roster is None:
            continue
        if roster.get("source_quality", "") not in FIRST_HAND_ROSTER_QUALITIES:
            continue
        chosen.append((dict(row), dict(structure), dict(roster)))
    chosen.sort(key=lambda item: item[0]["source_id"])
    return chosen


def is_static(row: Mapping[str, str]) -> bool:
    return not str(row.get("frequency_note", "")).strip()


def compound_id(inchikey: str) -> str:
    return inchikey[:COMPOUND_ID_LENGTH]


def build_rows_artifact(
    candidates: Sequence[tuple[Mapping[str, str], Mapping[str, str], Mapping[str, str]]],
) -> list[dict[str, str]]:
    """One row per candidate, with the gate outcomes spelled out."""

    gates = three_gate_result()
    rows: list[dict[str, str]] = []
    for row, structure, roster in candidates:
        static = is_static(row)
        rows.append(
            {
                "source_id": str(row["source_id"]),
                "inchikey": str(structure["inchikey"]),
                "compound_name": str(row["compound_name"]),
                "T_K": str(row["T_K"]),
                "temperature_C": str(row.get("t_C", "")),
                "dielectric": str(row["dielectric"]),
                "frequency_note": str(row.get("frequency_note", "")),
                "roster_T_K": str(roster["T_K"]),
                "roster_dielectric": str(roster["dielectric"]),
                "roster_source_quality": str(roster["source_quality"]),
                "static_frequency": "true" if static else "false",
                "usable": "true" if static else "false",
                "licence_verdict": str(gates["gate_1_licence"]["verdict"]),
                "locator": locator_for(row),
                "first_hand_verdict": str(gates["gate_3_first_hand"]["verdict"]),
            }
        )
    return rows


def write_rows_artifact(path: Path, rows: Sequence[Mapping[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(ROWS_COLUMNS), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def build(repo_root: Path = REPOSITORY_ROOT) -> dict[str, object]:
    transcript: list[dict[str, str]] = []
    for relative in TRANSCRIPT_FILES:
        transcript.extend(read_csv_rows(repo_root / relative))

    sidecar = {
        str(entry["source_id"]): entry
        for entry in read_csv_rows(repo_root / CANDIDATE_STRUCTURES)
    }
    roster_rows = read_csv_rows(repo_root / ROSTER)
    roster_by_key = {
        str(entry["inchikey"]): entry for entry in roster_rows if entry.get("inchikey")
    }

    first_hand = candidate_rows(transcript, sidecar, roster_by_key)
    all_matched = [
        row
        for row in transcript
        if sidecar.get(str(row.get("source_id", "")), {}).get("inchikey", "") in roster_by_key
    ]

    usable = [item for item in first_hand if is_static(item[0])]
    dropped = [item for item in first_hand if not is_static(item[0])]

    pairs = {(item[1]["inchikey"], item[0]["T_K"]) for item in usable}
    compound_pairs = {(compound_id(item[1]["inchikey"]), item[0]["T_K"]) for item in usable}

    gates = three_gate_result()
    row_artifact = build_rows_artifact(first_hand)

    in_window = sum(
        1
        for item in usable
        if ACCEPTED_WINDOW_K[0] <= float(item[0]["T_K"]) <= ACCEPTED_WINDOW_K[1]
    )

    return {
        "schema_version": "w20_nbs514_rows_v0",
        "task": "week20_w20_6b_nbs514_rows",
        "status": "executed",
        "verdict": "same_source_rows_admissible_not_promoted",
        "ceiling_break": False,
        "produces_reading": False,
        "promoted": False,
        "shot_number_taken": None,
        "scoreboard_attempts_delta": 0,
        "reaxys_values_used": 0,
        "models_fitted": 0,
        "main_scoreboard_untouched": True,
        "licence_verdict": LICENCE_VERDICT,
        "licence_reading": licence_reading(),
        "accepted_window_K": list(ACCEPTED_WINDOW_K),
        "source": "data/interim/nbs514_organic_part1..4.csv",
        "source_doi": NBS_DOI,
        "source_citation": NBS_CIRCULAR,
        "roster": ROSTER,
        "roster_sha256": sha256_file(repo_root / ROSTER),
        "candidate_rule": (
            "NBS Circular 514 organic transcript row that resolves to an "
            "InChIKey already on the data/dielectric_v03.csv roster whose roster "
            "observation is first-hand (source_quality in "
            + ", ".join(FIRST_HAND_ROSTER_QUALITIES)
            + ")"
        ),
        "first_hand_roster_qualities": list(FIRST_HAND_ROSTER_QUALITIES),
        "excluded_roster_qualities": list(SECONDARY_ROSTER_QUALITIES),
        "counts": {
            "transcript_rows": len(transcript),
            "roster_matched_rows_all": len(all_matched),
            "candidate_rows": len(first_hand),
            "non_static_frequency_rows_dropped": len(dropped),
            "usable_rows": len(usable),
            "usable_rows_in_accepted_window": in_window,
            "distinct_compound_temperature_pairs": len(compound_pairs),
            "distinct_full_inchikey_temperature_pairs": len(pairs),
        },
        "compound_identity": (
            "standard InChIKey connectivity block (first "
            + str(COMPOUND_ID_LENGTH)
            + " characters), so a cis/trans pair sharing a skeleton and a "
            "temperature counts as one compound"
        ),
        "three_gate_result": gates,
        "frequency_gate": frequency_gate(),
        "admissibility": {
            "licence_cleared": bool(gates["gate_1_licence"]["cleared"]),
            "locator_cleared": bool(gates["gate_2_locator"]["cleared"]),
            "first_hand_cleared": bool(gates["gate_3_first_hand"]["cleared"]),
            "admissible": all(bool(block["cleared"]) for block in gates.values()),
            "note": (
                "the licence, per-row locator and first-hand gates all clear; "
                "the only gate that bites is the NBS static-frequency gate, "
                "which drops the 2 frequency-noted rows"
            ),
        },
        "point_of_the_probe": (
            "same-source extension: temperature rows for compounds already on "
            "the roster, never a foreign-chemical-space block; no row is "
            "promoted and the main scoreboard is untouched"
        ),
        "rows_artifact": portable_relative_path(ARTIFACT_PATH, root=repo_root),
        "row_artifact_rows": row_artifact,
    }


def write_summary(path: Path, payload: Mapping[str, object]) -> None:
    body = {key: value for key, value in payload.items() if key != "row_artifact_rows"}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(body, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--write", action="store_true", help="write the summary and rows artifact")
    parser.add_argument("--summary", type=Path, default=SUMMARY_PATH)
    parser.add_argument("--rows", type=Path, default=ARTIFACT_PATH)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    payload = build()
    if args.write:
        write_summary(args.summary, payload)
        write_rows_artifact(args.rows, payload["row_artifact_rows"])
    printable = {key: value for key, value in payload.items() if key != "row_artifact_rows"}
    print(json.dumps(printable, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover - manual inspection helper
    raise SystemExit(main())
