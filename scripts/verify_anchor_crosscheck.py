"""Independently verify the anchor cross-check table.

This follows the repository's verifier convention: it re-reads every upstream
artifact and re-derives each row from scratch rather than trusting the table or
its summary.  Specifically it proves, without calling the builder:

1. Every anchor in ``V02_CROSSCHECK_ANCHORS`` is represented, and an anchor with
   no evidence anywhere is recorded as ``no_data`` rather than omitted.
2. Every row traces back to a real row in the named upstream artifact, with the
   same value, temperature and frequency.
3. The recorded ``delta``, ``comparable`` and ``agreement`` follow from the
   anchor definition and the row data -- they are recomputed here from an
   independent implementation of the comparability rule.
4. No row can be ``disagree`` while its anchor is not ``promotion_blocked``, and
   ``n_evidence_sources`` matches the distinct sources actually present.

A cross-check table is only worth having if a reviewer can re-run it and get the
same verdict, so anything this script cannot reproduce is reported as a failure.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from electrolyte_ml.anchors import V02_CROSSCHECK_ANCHORS

OUTPUT_NAME = "anchor_crosscheck.csv"
SUMMARY_NAME = "anchor_crosscheck_summary.json"

AGREEMENT_VALUES = frozenset({"agree", "disagree", "not_comparable", "no_data"})

KNOWN_SOURCES = frozenset(
    {
        "p1_spot_check",
        "dielectric_v01",
        "dielectric_v02",
        "dielectric_v01_ext",
        "chodera_crosscheck",
        "nbs514_transcript",
    }
)

# Recomputed independently of the builder, which keeps the two implementations
# from sharing a mistake.
TEMPERATURE_MATCH_K = 1.0
FREQUENCY_MATCH_MHZ = 0.01


@dataclass(frozen=True, slots=True)
class Check:
    name: str
    passed: bool
    detail: str


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def load_json(path: Path) -> Mapping[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise TypeError(f"JSON object required: {path}")
    return payload


def _as_float(value: str) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except ValueError:
        return None


def reclassify(row: Mapping[str, str], anchor: object) -> tuple[str, str, str]:
    """Return ``(delta, comparable, agreement)`` computed from first principles."""

    reference = anchor.reference_value  # type: ignore[attr-defined]
    temperature = _as_float(row["T_K"])
    value = _as_float(row["value"])
    frequency = _as_float(row["frequency_MHz"])
    ref_temperature = anchor.reference_temperature_K  # type: ignore[attr-defined]
    ref_frequency = anchor.reference_frequency_MHz  # type: ignore[attr-defined]

    if value is None or temperature is None or reference is None:
        return "", "false", "not_comparable"

    delta = value - reference
    same_temperature = (
        ref_temperature is None or abs(temperature - ref_temperature) <= TEMPERATURE_MATCH_K
    )
    if ref_frequency is None:
        same_frequency = True
    elif frequency is None:
        same_frequency = False
    else:
        same_frequency = abs(frequency - ref_frequency) <= FREQUENCY_MATCH_MHZ

    if not (same_temperature and same_frequency):
        return f"{delta:.6g}", "false", "not_comparable"

    tolerance = anchor.tolerance  # type: ignore[attr-defined]
    agreement = "agree" if abs(delta) <= tolerance else "disagree"
    return f"{delta:.6g}", "true", agreement


def check_anchor_coverage(
    rows: Sequence[Mapping[str, str]],
) -> Check:
    expected = {anchor.anchor_id for anchor in V02_CROSSCHECK_ANCHORS}
    present = {row["anchor_id"] for row in rows}
    missing = sorted(expected - present)
    if missing:
        return Check("cross-check anchor coverage", False, f"missing anchors: {missing}")
    extra = sorted(present - expected)
    if extra:
        return Check("cross-check anchor coverage", False, f"unknown anchors: {extra}")
    return Check(
        "cross-check anchor coverage",
        True,
        f"all {len(expected)} anchors represented",
    )


def check_agreement_vocabulary(
    rows: Sequence[Mapping[str, str]],
) -> Check:
    unknown = {row["agreement"] for row in rows} - AGREEMENT_VALUES
    if unknown:
        return Check(
            "cross-check agreement vocabulary",
            False,
            f"unknown agreement values: {sorted(unknown)}",
        )
    unknown_sources = {
        row["evidence_source"] for row in rows if row["evidence_source"]
    } - KNOWN_SOURCES
    if unknown_sources:
        return Check(
            "cross-check agreement vocabulary",
            False,
            f"unknown evidence sources: {sorted(unknown_sources)}",
        )
    return Check(
        "cross-check agreement vocabulary",
        True,
        f"agreement values and {len(KNOWN_SOURCES)} evidence sources are known",
    )


def check_reclassification(
    rows: Sequence[Mapping[str, str]],
) -> Check:
    anchors = {anchor.anchor_id: anchor for anchor in V02_CROSSCHECK_ANCHORS}
    for row in rows:
        if row["agreement"] == "no_data":
            continue
        anchor = anchors[row["anchor_id"]]
        delta, comparable, agreement = reclassify(row, anchor)
        if row["delta"] != delta:
            return Check(
                "cross-check reclassification",
                False,
                f"delta mismatch for {row['anchor_id']}/{row['evidence_source']}: "
                f"recorded {row['delta']!r} recomputed {delta!r}",
            )
        if row["comparable"] != comparable:
            return Check(
                "cross-check reclassification",
                False,
                f"comparability mismatch for {row['anchor_id']}/"
                f"{row['evidence_source']}: recorded {row['comparable']!r} "
                f"recomputed {comparable!r}",
            )
        if row["agreement"] != agreement:
            return Check(
                "cross-check reclassification",
                False,
                f"agreement mismatch for {row['anchor_id']}/{row['evidence_source']}: "
                f"recorded {row['agreement']!r} recomputed {agreement!r}",
            )
    return Check(
        "cross-check reclassification",
        True,
        f"{len(rows)} rows reproduce from the anchor definitions",
    )


def check_promotion_blocking(
    rows: Sequence[Mapping[str, str]],
) -> Check:
    # `promotion_blocked` is a per-anchor rollup repeated on every row of that
    # anchor, so a single inconsistent row would otherwise go unnoticed.
    per_anchor: dict[str, set[str]] = {}
    for row in rows:
        per_anchor.setdefault(row["anchor_id"], set()).add(row["promotion_blocked"])
    ragged = sorted(
        anchor_id for anchor_id, values in per_anchor.items() if len(values) > 1
    )
    if ragged:
        return Check(
            "cross-check promotion blocking",
            False,
            f"inconsistent promotion_blocked within an anchor: {ragged}",
        )

    disagreeing = {
        row["anchor_id"] for row in rows if row["agreement"] == "disagree"
    }
    blocked = {row["anchor_id"] for row in rows if row["promotion_blocked"] == "true"}
    if disagreeing - blocked:
        return Check(
            "cross-check promotion blocking",
            False,
            f"disagreeing but not blocked: {sorted(disagreeing - blocked)}",
        )
    if blocked - disagreeing:
        return Check(
            "cross-check promotion blocking",
            False,
            f"blocked without a disagreement: {sorted(blocked - disagreeing)}",
        )
    return Check(
        "cross-check promotion blocking",
        True,
        f"blocked anchors match disagreements: {sorted(blocked)}",
    )


def check_source_counts(
    rows: Sequence[Mapping[str, str]],
) -> Check:
    counts: dict[str, set[str]] = {}
    for row in rows:
        if row["evidence_source"]:
            counts.setdefault(row["anchor_id"], set()).add(row["evidence_source"])
    for row in rows:
        expected = len(counts.get(row["anchor_id"], set()))
        if row["n_evidence_sources"] != str(expected):
            return Check(
                "cross-check source counts",
                False,
                f"{row['anchor_id']}: recorded {row['n_evidence_sources']} "
                f"but {expected} distinct sources present",
            )
    return Check(
        "cross-check source counts",
        True,
        f"{len(counts)} anchors carry evidence",
    )


def check_no_data_anchors(
    root: Path,
    rows: Sequence[Mapping[str, str]],
) -> Check:
    """A ``no_data`` anchor must have no evidence in any upstream artifact."""

    no_data = {row["anchor_id"] for row in rows if row["agreement"] == "no_data"}
    if not no_data:
        return Check("cross-check no-data anchors", True, "no anchor is without data")

    data = root / "data"
    evidence_keys: dict[str, set[str]] = {
        "dielectric_v01.csv": set(),
        "dielectric_v02.csv": set(),
        "dielectric_v01_ext.csv": set(),
        "chodera_crosscheck.csv": set(),
    }
    for relative, keys in evidence_keys.items():
        path = (
            data / relative
            if relative != "chodera_crosscheck.csv"
            else data / "processed" / relative
        )
        keys.update(row["inchikey"] for row in read_csv_rows(path))

    spot = {row["anchor_id"] for row in read_csv_rows(data / "processed" / "p1_spot_check.csv")}
    transcript_names = {
        row["compound_name"].casefold()
        for path in sorted((data / "interim").glob("nbs514_organic_part*.csv"))
        for row in read_csv_rows(path)
    }

    for anchor in V02_CROSSCHECK_ANCHORS:
        if anchor.anchor_id not in no_data:
            continue
        if anchor.inchikey in evidence_keys["dielectric_v01.csv"]:
            return Check(
                "cross-check no-data anchors",
                False,
                f"{anchor.anchor_id} is no_data but appears in dielectric_v01",
            )
        if anchor.inchikey in evidence_keys["dielectric_v02.csv"]:
            return Check(
                "cross-check no-data anchors",
                False,
                f"{anchor.anchor_id} is no_data but appears in dielectric_v02",
            )
        if anchor.inchikey in evidence_keys["dielectric_v01_ext.csv"]:
            return Check(
                "cross-check no-data anchors",
                False,
                f"{anchor.anchor_id} is no_data but appears in the extension",
            )
        if anchor.inchikey in evidence_keys["chodera_crosscheck.csv"]:
            return Check(
                "cross-check no-data anchors",
                False,
                f"{anchor.anchor_id} is no_data but appears in the Chodera table",
            )
        if anchor.anchor_id in spot:
            observed = next(
                row
                for row in read_csv_rows(data / "processed" / "p1_spot_check.csv")
                if row["anchor_id"] == anchor.anchor_id
            )
            if observed.get("observed_value"):
                return Check(
                    "cross-check no-data anchors",
                    False,
                    f"{anchor.anchor_id} is no_data but the spot check has a value",
                )
        if any(alias.casefold() in transcript_names for alias in anchor.aliases):
            return Check(
                "cross-check no-data anchors",
                False,
                f"{anchor.anchor_id} is no_data but appears in the NBS 514 transcript",
            )
    return Check(
        "cross-check no-data anchors",
        True,
        f"{sorted(no_data)} has no evidence in any upstream artifact",
    )


def check_evidence_traceability(
    root: Path,
    rows: Sequence[Mapping[str, str]],
) -> Check:
    """Every row must point at a real upstream row with the same numbers."""

    data = root / "data"
    spot = {
        row["anchor_id"]: row
        for row in read_csv_rows(data / "processed" / "p1_spot_check.csv")
    }
    datasets = {
        "dielectric_v01": {
            row["inchikey"]: row
            for row in read_csv_rows(data / "dielectric_v01.csv")
        },
        "dielectric_v02": {
            row["inchikey"]: row
            for row in read_csv_rows(data / "dielectric_v02.csv")
        },
    }
    extension = {
        row["inchikey"]: row
        for row in read_csv_rows(data / "dielectric_v01_ext.csv")
    }
    chodera = {
        row["inchikey"]: row
        for row in read_csv_rows(data / "processed" / "chodera_crosscheck.csv")
    }
    transcript: dict[str, dict[str, str]] = {}
    for path in sorted((data / "interim").glob("nbs514_organic_part*.csv")):
        for row in read_csv_rows(path):
            if row["source_id"] in transcript:
                return Check(
                    "cross-check traceability",
                    False,
                    f"duplicate NBS source_id: {row['source_id']}",
                )
            transcript[row["source_id"]] = row

    for row in rows:
        source = row["evidence_source"]
        if not source:
            continue
        if source == "p1_spot_check":
            upstream = spot.get(row["anchor_id"])
            if upstream is None or not upstream.get("observed_value"):
                return Check(
                    "cross-check traceability",
                    False,
                    f"no spot-check observation for {row['anchor_id']}",
                )
            pairs = (
                ("value", upstream["observed_value"]),
                ("T_K", upstream["observed_temperature_K"]),
                ("frequency_MHz", upstream["frequency_MHz"]),
            )
        elif source in datasets:
            upstream = datasets[source].get(row["inchikey"])
            if upstream is None:
                return Check(
                    "cross-check traceability",
                    False,
                    f"{source} has no row for {row['inchikey']}",
                )
            # The promoted datasets have no frequency column, so the cross-check
            # derives one from the gate flags.  A wrong derivation would move a
            # row between comparable and not_comparable, so re-derive it here.
            flags = set(filter(None, upstream["gate_flags"].split("|")))
            expected_frequency = (
                "0.0"
                if "zero_frequency" in flags
                else "1.0"
                if "frequency_1mhz" in flags
                else ""
            )
            if row["frequency_MHz"] != expected_frequency:
                return Check(
                    "cross-check traceability",
                    False,
                    f"{row['anchor_id']}/{source}: frequency {row['frequency_MHz']!r} "
                    f"does not follow from gate flags {upstream['gate_flags']!r}",
                )
            pairs = (("value", upstream["dielectric"]), ("T_K", upstream["T_K"]))
        elif source == "dielectric_v01_ext":
            upstream = extension.get(row["inchikey"])
            if upstream is None:
                return Check(
                    "cross-check traceability",
                    False,
                    f"extension has no row for {row['inchikey']}",
                )
            pairs = (
                ("value", upstream["dielectric"]),
                ("T_K", upstream["T_K"]),
                ("frequency_MHz", upstream["frequency_MHz"]),
            )
        elif source == "chodera_crosscheck":
            upstream = chodera.get(row["inchikey"])
            if upstream is None or not upstream.get("pair_chodera_value"):
                return Check(
                    "cross-check traceability",
                    False,
                    f"Chodera table has no pair value for {row['inchikey']}",
                )
            pairs = (
                ("value", upstream["pair_chodera_value"]),
                ("T_K", upstream["nearest_chodera_T_K"]),
            )
        elif source == "nbs514_transcript":
            upstream = transcript.get(row["source_record_id"])
            if upstream is None:
                return Check(
                    "cross-check traceability",
                    False,
                    f"transcript has no source_id {row['source_record_id']}",
                )
            pairs = (("value", upstream["dielectric"]), ("T_K", upstream["T_K"]))
        else:
            return Check(
                "cross-check traceability",
                False,
                f"unhandled evidence source: {source}",
            )

        for field, expected in pairs:
            if row[field] != expected:
                return Check(
                    "cross-check traceability",
                    False,
                    f"{row['anchor_id']}/{source}: {field} recorded {row[field]!r} "
                    f"but upstream has {expected!r}",
                )
    return Check(
        "cross-check traceability",
        True,
        f"{sum(1 for row in rows if row['evidence_source'])} rows trace upstream",
    )


def check_summary(
    root: Path,
    rows: Sequence[Mapping[str, str]],
) -> Check:
    path = root / "probes" / SUMMARY_NAME
    if not path.is_file():
        return Check("cross-check summary", False, f"missing {path}")
    summary = load_json(path)
    if int(summary.get("rows", -1)) != len(rows):
        return Check("cross-check summary", False, "summary row count differs")
    if int(summary.get("anchors", -1)) != len({row["anchor_id"] for row in rows}):
        return Check("cross-check summary", False, "summary anchor count differs")
    blocked = sorted(
        {row["anchor_id"] for row in rows if row["promotion_blocked"] == "true"}
    )
    if list(summary.get("promotion_blocked_anchors", [])) != blocked:
        return Check("cross-check summary", False, "summary blocked anchors differ")
    return Check("cross-check summary", True, f"{len(rows)} rows agree with the summary")


def run_checks(root: Path = REPOSITORY_ROOT) -> list[Check]:
    path = root / "data" / "processed" / OUTPUT_NAME
    if not path.is_file():
        return [Check("cross-check artifact", False, f"missing {path}")]
    rows = read_csv_rows(path)
    if not rows:
        return [Check("cross-check artifact", False, "table is empty")]
    return [
        check_anchor_coverage(rows),
        check_agreement_vocabulary(rows),
        check_reclassification(rows),
        check_promotion_blocking(rows),
        check_source_counts(rows),
        check_evidence_traceability(root, rows),
        check_no_data_anchors(root, rows),
        check_summary(root, rows),
    ]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=REPOSITORY_ROOT)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    checks = run_checks(args.root)
    failures = [check for check in checks if not check.passed]
    if args.json:
        print(
            json.dumps(
                {"passed": not failures, "checks": [asdict(check) for check in checks]},
                indent=2,
            )
        )
    else:
        for check in checks:
            print(f"[{'PASS' if check.passed else 'FAIL'}] {check.name}: {check.detail}")
        print(f"\n{len(checks) - len(failures)}/{len(checks)} checks passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
