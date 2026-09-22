"""Verify dataset v0.1 schemas, units, source roles, and count contracts."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sys
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import TextIO

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from electrolyte_ml.standardize import GATE_FLAGS

REQUIRED_DIELECTRIC_COLUMNS = {
    "inchikey",
    "smiles",
    "name",
    "T_K",
    "dielectric",
    "uncertainty",
    "source_doi",
    "n_observations",
    "source_scope",
    "gate_flags",
}
REQUIRED_VISCOSITY_COLUMNS = {
    "inchikey",
    "smiles",
    "name",
    "T_K",
    "viscosity_Pa_s",
    "density",
    "source_doi",
    "n_observations",
    "source_scope",
    "gate_flags",
}
REQUIRED_OBSERVATION_COLUMNS = {
    "dataset_source",
    "selection_status",
    "inchikey",
    "smiles",
    "T_K",
    "dielectric",
    "source_file",
    "source_sha256",
    "source_size_bytes",
}


@dataclass(frozen=True, slots=True)
class Check:
    name: str
    passed: bool
    detail: str


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _columns(rows: Sequence[Mapping[str, str]]) -> set[str]:
    return set(rows[0]) if rows else set()


def _decimal_median(values: Sequence[Decimal]) -> Decimal:
    ordered = sorted(values)
    if not ordered:
        raise ValueError("median requires at least one value")
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / Decimal(2)


def check_compound_values_from_observations(
    compound_rows: Sequence[Mapping[str, str]],
    observation_rows: Sequence[Mapping[str, str]],
) -> Check:
    primary_rows = [
        row
        for row in observation_rows
        if row.get("dataset_source") == "P1 ThermoML"
        and row.get("selection_status") == "primary"
    ]
    grouped: dict[str, list[Mapping[str, str]]] = {}
    for row in primary_rows:
        grouped.setdefault(str(row.get("inchikey", "")), []).append(row)
    compound_by_key = {str(row.get("inchikey", "")): row for row in compound_rows}
    if set(grouped) != set(compound_by_key):
        return Check(
            "dataset dielectric value recomputation",
            False,
            "P1 observation keys do not match compound-level keys",
        )
    for inchikey, observations in grouped.items():
        compound = compound_by_key[inchikey]
        if int(compound["n_observations"]) != len(observations):
            return Check(
                "dataset dielectric value recomputation",
                False,
                f"observation count mismatch for {inchikey}",
            )
        try:
            expected_temperature = _decimal_median(
                [Decimal(row["T_K"]) for row in observations]
            )
            expected_dielectric = _decimal_median(
                [Decimal(row["dielectric"]) for row in observations]
            )
            observed_temperature = Decimal(compound["T_K"])
            observed_dielectric = Decimal(compound["dielectric"])
        except (InvalidOperation, ValueError, KeyError) as exc:
            return Check(
                "dataset dielectric value recomputation",
                False,
                f"cannot recompute {inchikey}: {exc}",
            )
        if observed_temperature != expected_temperature:
            return Check(
                "dataset dielectric value recomputation",
                False,
                (
                    f"median T_K mismatch for {inchikey}: "
                    f"{observed_temperature} != {expected_temperature}"
                ),
            )
        if observed_dielectric != expected_dielectric:
            return Check(
                "dataset dielectric value recomputation",
                False,
                (
                    f"median dielectric mismatch for {inchikey}: "
                    f"{observed_dielectric} != {expected_dielectric}"
                ),
            )
    return Check(
        "dataset dielectric value recomputation",
        True,
        "100 compound medians and median temperatures recomputed exactly",
    )


def check_dielectric_compound_rows(
    rows: Sequence[Mapping[str, str]],
) -> Check:
    missing = REQUIRED_DIELECTRIC_COLUMNS - _columns(rows)
    if missing:
        return Check(
            "dataset dielectric compound rows",
            False,
            f"missing columns: {sorted(missing)}",
        )
    if len(rows) != 100:
        return Check(
            "dataset dielectric compound rows",
            False,
            f"expected 100 rows, got {len(rows)}",
        )
    keys = [str(row.get("inchikey", "")) for row in rows]
    if any(not key for key in keys):
        return Check(
            "dataset dielectric compound rows",
            False,
            "empty InChIKey",
        )
    if len(set(keys)) != 100:
        return Check(
            "dataset dielectric compound rows",
            False,
            f"expected 100 unique InChIKeys, got {len(set(keys))}",
        )
    if sum(int(row["n_observations"]) for row in rows) != 460:
        return Check(
            "dataset dielectric compound rows",
            False,
            "P1 observation counts do not sum to 460",
        )
    invalid_gate_flags = {
        flag
        for row in rows
        for flag in str(row["gate_flags"]).split("|")
        if flag not in GATE_FLAGS
    }
    if invalid_gate_flags:
        return Check(
            "dataset dielectric compound rows",
            False,
            f"unknown gate flags: {sorted(invalid_gate_flags)}",
        )
    for row in rows:
        temperature = float(row["T_K"])
        dielectric = float(row["dielectric"])
        if not 293.15 <= temperature <= 303.15 or not math.isfinite(dielectric):
            return Check(
                "dataset dielectric compound rows",
                False,
                f"invalid temperature or dielectric for {row['inchikey']}",
            )
    if any(str(row["name"]).casefold() == "ethylene carbonate" for row in rows):
        return Check(
            "dataset dielectric compound rows",
            False,
            "EC must not be present in the 293.15-303.15 K liquid set",
        )
    return Check(
        "dataset dielectric compound rows",
        True,
        "100 unique keys; 460 P1 observations; EC absent",
    )


def check_viscosity_rows(
    rows: Sequence[Mapping[str, str]],
) -> Check:
    missing = REQUIRED_VISCOSITY_COLUMNS - _columns(rows)
    if missing:
        return Check(
            "dataset viscosity rows",
            False,
            f"missing columns: {sorted(missing)}",
        )
    predicted = [
        row
        for row in rows
        if row.get("data_status") != "experimental"
        or "prediction" in str(row.get("source_scope", "")).casefold()
        or "predicted" in str(row.get("gate_flags", "")).split("|")
    ]
    if predicted:
        return Check(
            "dataset viscosity rows",
            False,
            f"predicted/supp3 rows present: {len(predicted)}",
        )
    invalid_flags = {
        flag
        for row in rows
        for flag in str(row.get("gate_flags", "")).split("|")
        if flag not in GATE_FLAGS
    }
    if invalid_flags:
        return Check(
            "dataset viscosity rows",
            False,
            f"unknown flags: {sorted(invalid_flags)}",
        )
    if len(rows) != 3582:
        return Check(
            "dataset viscosity rows",
            False,
            f"expected 3582 rows, got {len(rows)}",
        )
    if len({row["inchikey"] for row in rows}) != 957:
        return Check(
            "dataset viscosity rows",
            False,
            "expected 957 unique InChIKeys",
        )
    if any(row["density"] != "" for row in rows):
        return Check(
            "dataset viscosity rows",
            False,
            "density must be empty because no experimental density is available",
        )
    for row in rows:
        if not row["inchikey"] or not row["smiles"]:
            return Check(
                "dataset viscosity rows",
                False,
                "empty InChIKey or SMILES",
            )
        expected_pa_s = float(row["viscosity_cP"]) * 1e-3
        if not math.isclose(
            float(row["viscosity_Pa_s"]),
            expected_pa_s,
            rel_tol=0,
            abs_tol=1e-15,
        ):
            return Check(
                "dataset viscosity rows",
                False,
                f"cP conversion mismatch for record {row['record_id']}",
            )
    return Check(
        "dataset viscosity rows",
        True,
        "3582 experimental rows; 957 keys; density empty; no predictions",
    )


def check_observations(
    rows: Sequence[Mapping[str, str]],
) -> Check:
    missing = REQUIRED_OBSERVATION_COLUMNS - _columns(rows)
    if missing:
        return Check(
            "dataset dielectric observations",
            False,
            f"missing columns: {sorted(missing)}",
        )
    if len(rows) != 706:
        return Check(
            "dataset dielectric observations",
            False,
            f"expected 706 rows, got {len(rows)}",
        )
    p1_rows = [row for row in rows if row.get("dataset_source") == "P1 ThermoML"]
    chodera_rows = [
        row for row in rows if row.get("dataset_source") == "Chodera 2015"
    ]
    if len(p1_rows) != 460 or len(chodera_rows) != 246:
        return Check(
            "dataset dielectric observations",
            False,
            f"P1={len(p1_rows)}, Chodera={len(chodera_rows)}",
        )
    if any(not row.get("inchikey") or not row.get("smiles") for row in rows):
        return Check(
            "dataset dielectric observations",
            False,
            "empty InChIKey or SMILES",
        )
    if any(not row.get("source_sha256") for row in rows):
        return Check(
            "dataset dielectric observations",
            False,
            "missing source SHA256",
        )
    invalid_flags = {
        flag
        for row in rows
        for flag in str(row.get("gate_flags", "")).split("|")
        if flag not in GATE_FLAGS
    }
    if invalid_flags:
        return Check(
            "dataset dielectric observations",
            False,
            f"unknown flags: {sorted(invalid_flags)}",
        )
    return Check(
        "dataset dielectric observations",
        True,
        "706 rows: 460 P1 + 246 Chodera; source hashes present",
    )


def check_observation_provenance(
    rows: Sequence[Mapping[str, str]],
    *,
    root: Path,
) -> Check:
    raw_dir = root / "data" / "raw" / "thermoml"
    p1_rows = [row for row in rows if row.get("dataset_source") == "P1 ThermoML"]
    chodera_rows = [
        row for row in rows if row.get("dataset_source") == "Chodera 2015"
    ]
    verified_p1 = 0
    raw_cache: dict[Path, tuple[str, int]] = {}
    if raw_dir.is_dir():
        for row in p1_rows:
            path = root / str(row["source_file"])
            if path not in raw_cache:
                if not path.is_file():
                    return Check(
                        "dataset observation provenance",
                        False,
                        f"missing raw source: {path}",
                    )
                raw_cache[path] = (sha256_file(path), path.stat().st_size)
            actual_hash, actual_size = raw_cache[path]
            if actual_hash != row["source_sha256"]:
                return Check(
                    "dataset observation provenance",
                    False,
                    f"SHA256 mismatch for {path.name}",
                )
            if str(actual_size) != str(row["source_size_bytes"]):
                return Check(
                    "dataset observation provenance",
                    False,
                    f"size mismatch for {path.name}",
                )
            verified_p1 += 1

    verified_chodera = 0
    for row in chodera_rows:
        path = root / str(row["source_file"])
        if not path.is_file():
            return Check(
                "dataset observation provenance",
                False,
                f"missing Chodera source: {path}",
            )
        if sha256_file(path) != row["source_sha256"]:
            return Check(
                "dataset observation provenance",
                False,
                "Chodera source SHA256 mismatch",
            )
        if str(path.stat().st_size) != str(row["source_size_bytes"]):
            return Check(
                "dataset observation provenance",
                False,
                "Chodera source size mismatch",
            )
        verified_chodera += 1

    if not raw_dir.is_dir():
        return Check(
            "dataset observation provenance",
            True,
            (
                "raw XML SHA256/size checks skipped (raw directory absent); "
                f"Chodera rows verified: {verified_chodera}"
            ),
        )
    return Check(
        "dataset observation provenance",
        True,
        (
            f"P1 observation rows hash/size verified: {verified_p1}; "
            f"Chodera rows verified: {verified_chodera}"
        ),
    )


def check_summary(summary: Mapping[str, object]) -> Check:
    row_counts = summary.get("row_counts")
    overlap = summary.get("overlap")
    viscosity = summary.get("viscosity")
    if not isinstance(row_counts, Mapping) or not isinstance(overlap, Mapping):
        return Check("dataset v0.1 summary", False, "row_counts/overlap missing")
    if row_counts.get("dielectric_compound_rows") != 100:
        return Check(
            "dataset v0.1 summary",
            False,
            "compound row count must be 100",
        )
    if row_counts.get("dielectric_observation_rows") != 706:
        return Check(
            "dataset v0.1 summary",
            False,
            "observation row count must be 706",
        )
    if (
        overlap.get("p1_keys") != 100
        or overlap.get("chodera_keys") != 45
        or overlap.get("overlap_keys") != 45
        or overlap.get("chodera_adds_unique_keys") != 0
        or overlap.get("union_key_count") != 100
        or overlap.get("union_is_not_145") is not True
    ):
        return Check(
            "dataset v0.1 summary",
            False,
            "P1/Chodera overlap summary is inconsistent",
        )
    if not isinstance(viscosity, Mapping):
        return Check("dataset v0.1 summary", False, "viscosity summary missing")
    if (
        viscosity.get("predicted_rows_excluded") != 650
        or viscosity.get("md_density_used_as_density") is not False
    ):
        return Check(
            "dataset v0.1 summary",
            False,
            "viscosity exclusion summary is inconsistent",
        )
    return Check(
        "dataset v0.1 summary",
        True,
        "100 keys; 460 P1 + 246 Chodera; 45 overlap; 0 Chodera additions",
    )


def run_checks(root: Path = ROOT) -> list[Check]:
    dielectric_path = root / "data" / "dielectric_v01.csv"
    viscosity_path = root / "data" / "viscosity_v01.csv"
    observations_path = (
        root / "data" / "processed" / "dielectric_v01_observations.csv"
    )
    summary_path = root / "data" / "processed" / "dataset_v01_summary.json"
    missing = [
        str(path)
        for path in (
            dielectric_path,
            viscosity_path,
            observations_path,
            summary_path,
        )
        if not path.is_file()
    ]
    if missing:
        return [Check("dataset v0.1 files", False, f"missing: {missing}")]
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    compound_rows = read_csv_rows(dielectric_path)
    observation_rows = read_csv_rows(observations_path)
    return [
        check_dielectric_compound_rows(compound_rows),
        check_viscosity_rows(read_csv_rows(viscosity_path)),
        check_observations(observation_rows),
        check_compound_values_from_observations(compound_rows, observation_rows),
        check_observation_provenance(observation_rows, root=root),
        check_summary(summary),
    ]


def main(
    argv: Sequence[str] | None = None,
    *,
    stdout: TextIO | None = None,
) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    checks = run_checks(args.root)
    failures = [check for check in checks if not check.passed]
    output = stdout if stdout is not None else sys.stdout
    if args.json:
        print(
            json.dumps(
                {
                    "passed": not failures,
                    "checks": [asdict(check) for check in checks],
                },
                ensure_ascii=False,
                indent=2,
            ),
            file=output,
        )
    else:
        for check in checks:
            marker = "PASS" if check.passed else "FAIL"
            print(f"[{marker}] {check.name}: {check.detail}", file=output)
        print(f"\n{len(checks) - len(failures)}/{len(checks)} checks passed", file=output)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
