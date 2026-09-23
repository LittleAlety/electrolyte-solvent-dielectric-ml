"""Build a per-anchor cross-check table across every in-repo evidence source.

The seven v0.2 anchor compounds (benzene, methanol, acetonitrile, ethylene
carbonate, propylene carbonate, DMC, DEC) each have a literature reference
value.  This script asks a single question for every anchor: *which in-repo
sources carry a value for it, and does that value agree with the reference?*

One output row is one ``(anchor, evidence source)`` pair, so an anchor with
three sources produces three rows.  Nothing is selected, averaged, or repaired
here: an anchor whose sources disagree keeps every disagreeing row, and the
anchor is marked ``promotion_blocked``.  Choosing a winner is a human decision
recorded in ``reports/decisions_log.md``, never a silent one made here.

Evidence sources are existing, independently verified artifacts rather than a
re-implementation of their selection rules:

``p1_spot_check``
    ``data/processed/p1_spot_check.csv`` -- the Week 1 protocol-matched
    observation, already validated by ``scripts/verify_week1.py``.
``dielectric_v01`` / ``dielectric_v02``
    The promoted datasets.
``dielectric_v01_ext``
    The high-temperature extension, which carries an explicit frequency.
``chodera_crosscheck``
    An independent compilation, temperature-matched against the same p1 rows.
``nbs514_transcript``
    The raw NBS Circular 514 transcription, which is upstream of v0.2 and so
    is genuinely independent of it.

Comparability is decided before agreement.  A value measured at a different
temperature (beyond ``TEMPERATURE_MATCH_K``) or a different frequency is
recorded as ``not_comparable``: it is evidence that the compound was measured,
not evidence about the reference value.  This is what keeps a 1 MHz datum from
being scored against a static reference, or a 293.15 K datum against a
298.15 K one.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from electrolyte_ml.anchors import V02_CROSSCHECK_ANCHORS, CrosscheckAnchor

OUTPUT_COLUMNS = (
    "anchor_id",
    "name",
    "inchikey",
    "evidence_source",
    "source_doi",
    "source_record_id",
    "T_K",
    "frequency_MHz",
    "property_family",
    "value",
    "expected_value",
    "reference_T_K",
    "reference_frequency_MHz",
    "tolerance",
    "delta",
    "comparable",
    "agreement",
    "n_evidence_sources",
    "promotion_blocked",
    "gate_flags",
    "notes",
)

AGREEMENT_VALUES = ("agree", "disagree", "not_comparable", "no_data")

# A value is only scored against the reference if it was measured under the same
# protocol.  Temperature gets a small window because published temperatures are
# rounded (298 K vs 298.15 K is the same measurement).
TEMPERATURE_MATCH_K = 1.0
FREQUENCY_MATCH_MHZ = 0.01

SOURCE_ORDER = (
    "p1_spot_check",
    "dielectric_v01",
    "dielectric_v02",
    "dielectric_v01_ext",
    "chodera_crosscheck",
    "nbs514_transcript",
)


@dataclass(frozen=True, slots=True)
class Evidence:
    """One source's observation of one anchor compound."""

    anchor_id: str
    evidence_source: str
    source_doi: str
    source_record_id: str
    T_K: str
    frequency_MHz: str
    property_family: str
    value: str
    gate_flags: str
    notes: str


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv_rows(
    path: Path,
    fieldnames: Sequence[str],
    rows: Sequence[Mapping[str, object]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _frequency_from_gate_flags(gate_flags: str) -> tuple[str, str]:
    """Derive a frequency and property family from a dataset row's flags.

    The promoted datasets do not carry a frequency column; the flag vocabulary
    is the only record of it.  An unrecognised flag set yields blanks rather
    than a guess, which makes the row ``not_comparable``.
    """

    flags = set(filter(None, gate_flags.split("|")))
    if "zero_frequency" in flags:
        return "0.0", "zero_frequency"
    if "frequency_1mhz" in flags:
        return "1.0", "frequency_dependent"
    return "", ""


def _matches_anchor(anchor: CrosscheckAnchor, name: str) -> bool:
    """Return whether ``name`` is exactly one of the anchor's known names.

    Matching is exact after case-folding.  A substring match would conflate
    benzene with nitrobenzene and every alkylbenzene in the NBS 514 table.
    """

    return name.casefold() in {alias.casefold() for alias in anchor.aliases}


def _p1_spot_check_evidence(
    rows: Sequence[Mapping[str, str]],
    anchors: Sequence[CrosscheckAnchor],
) -> list[Evidence]:
    by_id = {row["anchor_id"]: row for row in rows}
    evidence: list[Evidence] = []
    for anchor in anchors:
        row = by_id.get(anchor.anchor_id)
        if row is None or not row.get("observed_value"):
            # A `not_found` or guard row carries no observation to cross-check.
            continue
        evidence.append(
            Evidence(
                anchor_id=anchor.anchor_id,
                evidence_source="p1_spot_check",
                source_doi=row.get("source_doi", ""),
                source_record_id=row.get("source_file", ""),
                T_K=row.get("observed_temperature_K", ""),
                frequency_MHz=row.get("frequency_MHz", ""),
                property_family=(
                    "zero_frequency"
                    if row.get("frequency_MHz") == "0.0"
                    else "frequency_dependent"
                ),
                value=row.get("observed_value", ""),
                gate_flags=row.get("gate_flags", ""),
                notes=(
                    "Week 1 protocol-matched observation, independently "
                    "validated by scripts/verify_week1.py."
                ),
            )
        )
    return evidence


def _dataset_evidence(
    rows: Sequence[Mapping[str, str]],
    anchors: Sequence[CrosscheckAnchor],
    source_name: str,
) -> list[Evidence]:
    by_key = {row["inchikey"]: row for row in rows}
    evidence: list[Evidence] = []
    for anchor in anchors:
        row = by_key.get(anchor.inchikey)
        if row is None:
            continue
        frequency, family = _frequency_from_gate_flags(row.get("gate_flags", ""))
        evidence.append(
            Evidence(
                anchor_id=anchor.anchor_id,
                evidence_source=source_name,
                source_doi=row.get("source_doi", ""),
                source_record_id=row.get("source_record_id", ""),
                T_K=row.get("T_K", ""),
                frequency_MHz=frequency,
                property_family=family,
                value=row.get("dielectric", ""),
                gate_flags=row.get("gate_flags", ""),
                notes=(
                    "Frequency derived from the row's gate flags; the promoted "
                    "schema has no frequency column."
                ),
            )
        )
    return evidence


def _extension_evidence(
    rows: Sequence[Mapping[str, str]],
    anchors: Sequence[CrosscheckAnchor],
) -> list[Evidence]:
    by_key = {row["inchikey"]: row for row in rows}
    evidence: list[Evidence] = []
    for anchor in anchors:
        row = by_key.get(anchor.inchikey)
        if row is None:
            continue
        evidence.append(
            Evidence(
                anchor_id=anchor.anchor_id,
                evidence_source="dielectric_v01_ext",
                source_doi=row.get("source_doi", ""),
                source_record_id=row.get("source_file", ""),
                T_K=row.get("T_K", ""),
                frequency_MHz=row.get("frequency_MHz", ""),
                property_family=row.get("property_family", ""),
                value=row.get("dielectric", ""),
                gate_flags=row.get("gate_flags", ""),
                notes="High-temperature extension row; carries an explicit frequency.",
            )
        )
    return evidence


def _chodera_evidence(
    rows: Sequence[Mapping[str, str]],
    anchors: Sequence[CrosscheckAnchor],
) -> list[Evidence]:
    by_key = {row["inchikey"]: row for row in rows}
    evidence: list[Evidence] = []
    for anchor in anchors:
        row = by_key.get(anchor.inchikey)
        if row is None or not row.get("pair_chodera_value"):
            continue
        evidence.append(
            Evidence(
                anchor_id=anchor.anchor_id,
                evidence_source="chodera_crosscheck",
                source_doi=row.get("chodera_source_doi", ""),
                source_record_id="",
                T_K=row.get("nearest_chodera_T_K", ""),
                frequency_MHz="0.0",
                property_family="zero_frequency",
                value=row.get("pair_chodera_value", ""),
                gate_flags="",
                notes=(
                    "Temperature-matched pair value from an independent "
                    "compilation (median "
                    f"{row.get('chodera_median', '')}). Frequency is inherited "
                    "from the matched p1 observation: the compilation carries no "
                    "explicit frequency field, so this row is weaker evidence "
                    "than a source that states one."
                ),
            )
        )
    return evidence


def _nbs514_evidence(
    rows: Sequence[Mapping[str, str]],
    anchors: Sequence[CrosscheckAnchor],
) -> list[Evidence]:
    evidence: list[Evidence] = []
    for anchor in anchors:
        for row in rows:
            if not _matches_anchor(anchor, row.get("compound_name", "")):
                continue
            notes = (
                "Raw NBS Circular 514 transcription. Pages 13-47 hold critically "
                "evaluated static constants, so frequency is zero by construction."
            )
            if row.get("frequency_note"):
                notes += f" Source frequency footnote: {row['frequency_note']}"
            evidence.append(
                Evidence(
                    anchor_id=anchor.anchor_id,
                    evidence_source="nbs514_transcript",
                    source_doi="10.6028/nbs.circ.514",
                    source_record_id=row.get("source_id", ""),
                    T_K=row.get("T_K", ""),
                    frequency_MHz="0.0",
                    property_family="zero_frequency",
                    value=row.get("dielectric", ""),
                    gate_flags="nbs514_circular_514",
                    notes=notes,
                )
            )
    return evidence


def _classify(
    anchor: CrosscheckAnchor,
    evidence: Evidence,
) -> tuple[bool, str, str]:
    """Return ``(comparable, delta, agreement)`` for one evidence row."""

    if not evidence.value or not evidence.T_K:
        return False, "", "not_comparable"

    try:
        value = float(evidence.value)
        temperature = float(evidence.T_K)
    except ValueError:
        return False, "", "not_comparable"

    if anchor.reference_value is None:
        return False, "", "not_comparable"

    delta = value - anchor.reference_value

    same_temperature = (
        anchor.reference_temperature_K is None
        or abs(temperature - anchor.reference_temperature_K) <= TEMPERATURE_MATCH_K
    )
    same_frequency = True
    if anchor.reference_frequency_MHz is not None and evidence.frequency_MHz:
        same_frequency = (
            abs(float(evidence.frequency_MHz) - anchor.reference_frequency_MHz)
            <= FREQUENCY_MATCH_MHZ
        )
    elif anchor.reference_frequency_MHz is not None and not evidence.frequency_MHz:
        # An unknown frequency cannot be shown to match a stated one.
        same_frequency = False

    if not (same_temperature and same_frequency):
        return False, f"{delta:.6g}", "not_comparable"

    agreement = "agree" if abs(delta) <= anchor.tolerance else "disagree"
    return True, f"{delta:.6g}", agreement


def build_rows(
    anchors: Sequence[CrosscheckAnchor],
    evidence: Sequence[Evidence],
) -> list[dict[str, str]]:
    grouped: dict[str, list[Evidence]] = {anchor.anchor_id: [] for anchor in anchors}
    for item in evidence:
        grouped.setdefault(item.anchor_id, []).append(item)

    rows: list[dict[str, str]] = []
    for anchor in anchors:
        items = sorted(
            grouped.get(anchor.anchor_id, []),
            key=lambda item: (SOURCE_ORDER.index(item.evidence_source), item.T_K),
        )
        source_count = len({item.evidence_source for item in items})
        classified = [(item, *_classify(anchor, item)) for item in items]
        blocked = any(agreement == "disagree" for _, _, _, agreement in classified)

        if not items:
            rows.append(
                _row(
                    anchor,
                    evidence=None,
                    comparable=False,
                    delta="",
                    agreement="no_data",
                    source_count=0,
                    blocked=False,
                    notes=anchor.blocking_reason,
                )
            )
            continue

        for item, comparable, delta, agreement in classified:
            notes = item.notes
            if agreement == "disagree":
                notes += (
                    " DISAGREES with the reference beyond the anchor tolerance; "
                    "no side is chosen here - see reports/decisions_log.md."
                )
            elif agreement == "not_comparable":
                notes += " Protocol differs from the reference (temperature or frequency)."
            rows.append(
                _row(
                    anchor,
                    evidence=item,
                    comparable=comparable,
                    delta=delta,
                    agreement=agreement,
                    source_count=source_count,
                    blocked=blocked,
                    notes=notes,
                )
            )
    return rows


def _row(
    anchor: CrosscheckAnchor,
    *,
    evidence: Evidence | None,
    comparable: bool,
    delta: str,
    agreement: str,
    source_count: int,
    blocked: bool,
    notes: str,
) -> dict[str, str]:
    return {
        "anchor_id": anchor.anchor_id,
        "name": anchor.name,
        "inchikey": anchor.inchikey,
        "evidence_source": evidence.evidence_source if evidence else "",
        "source_doi": evidence.source_doi if evidence else "",
        "source_record_id": evidence.source_record_id if evidence else "",
        "T_K": evidence.T_K if evidence else "",
        "frequency_MHz": evidence.frequency_MHz if evidence else "",
        "property_family": evidence.property_family if evidence else "",
        "value": evidence.value if evidence else "",
        "expected_value": (
            "" if anchor.reference_value is None else f"{anchor.reference_value:g}"
        ),
        "reference_T_K": (
            ""
            if anchor.reference_temperature_K is None
            else f"{anchor.reference_temperature_K:g}"
        ),
        "reference_frequency_MHz": (
            ""
            if anchor.reference_frequency_MHz is None
            else f"{anchor.reference_frequency_MHz:g}"
        ),
        "tolerance": f"{anchor.tolerance:g}",
        "delta": delta,
        "comparable": str(comparable).lower(),
        "agreement": agreement,
        "n_evidence_sources": str(source_count),
        "promotion_blocked": str(blocked).lower(),
        "gate_flags": evidence.gate_flags if evidence else "",
        "notes": notes,
    }


def collect_evidence(
    anchors: Sequence[CrosscheckAnchor],
    root: Path,
) -> list[Evidence]:
    """Gather evidence from every in-repo source."""

    data = root / "data"
    sources: tuple[Callable[[], list[Evidence]], ...] = (
        lambda: _p1_spot_check_evidence(
            read_csv_rows(data / "processed" / "p1_spot_check.csv"), anchors
        ),
        lambda: _dataset_evidence(
            read_csv_rows(data / "dielectric_v01.csv"), anchors, "dielectric_v01"
        ),
        lambda: _dataset_evidence(
            read_csv_rows(data / "dielectric_v02.csv"), anchors, "dielectric_v02"
        ),
        lambda: _extension_evidence(
            read_csv_rows(data / "dielectric_v01_ext.csv"), anchors
        ),
        lambda: _chodera_evidence(
            read_csv_rows(data / "processed" / "chodera_crosscheck.csv"), anchors
        ),
        lambda: _nbs514_evidence(
            [
                row
                for path in sorted((data / "interim").glob("nbs514_organic_part*.csv"))
                for row in read_csv_rows(path)
            ],
            anchors,
        ),
    )
    return [item for source in sources for item in source()]


def build_summary(rows: Sequence[Mapping[str, str]]) -> dict[str, object]:
    by_anchor: dict[str, dict[str, int]] = {}
    for row in rows:
        counts = by_anchor.setdefault(row["anchor_id"], {})
        counts[row["agreement"]] = counts.get(row["agreement"], 0) + 1
    return {
        "anchors": len(by_anchor),
        "rows": len(rows),
        "agreement_counts": {
            value: sum(1 for row in rows if row["agreement"] == value)
            for value in AGREEMENT_VALUES
        },
        "per_anchor": by_anchor,
        "promotion_blocked_anchors": sorted(
            {
                row["anchor_id"]
                for row in rows
                if row["promotion_blocked"] == "true"
            }
        ),
        "status": "built; independent verification required",
    }


def _parse_args() -> argparse.Namespace:
    data_dir = REPOSITORY_ROOT / "data"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=data_dir / "processed" / "anchor_crosscheck.csv",
    )
    parser.add_argument(
        "--summary",
        type=Path,
        default=REPOSITORY_ROOT / "probes" / "anchor_crosscheck_summary.json",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    anchors = V02_CROSSCHECK_ANCHORS
    evidence = collect_evidence(anchors, REPOSITORY_ROOT)
    rows = build_rows(anchors, evidence)
    unknown = {row["agreement"] for row in rows} - set(AGREEMENT_VALUES)
    if unknown:
        raise SystemExit(f"unexpected agreement values: {sorted(unknown)}")
    write_csv_rows(args.output, OUTPUT_COLUMNS, rows)
    summary = build_summary(rows)
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
