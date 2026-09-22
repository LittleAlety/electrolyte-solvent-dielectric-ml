"""Independently verify the high-temperature dielectric extension."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import TextIO

from rdkit import Chem

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from electrolyte_ml.exporting import canonical_text_sha256
from electrolyte_ml.pathing import portable_basename
from electrolyte_ml.standardize import GATE_FLAGS

EC_INCHIKEY = "KMTRUDSVKNLOMY-UHFFFAOYSA-N"
EC_DOI = "10.1021/je050341y"
EXPECTED_MAIN_SHA256 = "6f31c5b22a6a85a14954d3103a9ce5498eb4cdb265e55cfc8679adb78e4e5396"


@dataclass(frozen=True, slots=True)
class Check:
    name: str
    passed: bool
    detail: str


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _median(values: Sequence[Decimal]) -> Decimal:
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / Decimal(2)


def _text(value: Decimal) -> str:
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _in_window(value: str) -> bool:
    try:
        temperature = Decimal(value)
    except (InvalidOperation, ValueError):
        return False
    return Decimal("313.15") <= temperature <= Decimal("323.15")


def _canonical_inchi(inchi: str) -> tuple[str, str]:
    molecule = Chem.MolFromInchi(inchi)
    if molecule is None:
        raise ValueError(f"cannot parse InChI: {inchi!r}")
    return (
        Chem.MolToSmiles(molecule, canonical=True, isomericSmiles=True),
        Chem.MolToInchiKey(molecule),
    )


def _independent_nist(
    root: Path,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    raw_path = root / "data" / "processed" / "dielectric_raw.csv"
    raw_rows = read_csv_rows(raw_path)
    selected: list[dict[str, str]] = []
    for row_index, row in enumerate(raw_rows, start=2):
        if row.get("property_family") != "zero_frequency":
            continue
        if row.get("is_pure") != "True":
            continue
        if not _in_window(row.get("temperature_k", "")):
            continue
        smiles, inchikey = _canonical_inchi(row["primary_inchi"])
        selected.append(
            {
                "observation_id": f"p1_ext:{row_index}",
                "dataset_source": "P1 ThermoML",
                "inchikey": inchikey,
                "smiles": smiles,
                "name": row["primary_name"],
                "T_K": row["temperature_k"],
                "dielectric": row["value"],
                "frequency_MHz": "0",
                "property_family": "zero_frequency",
                "uncertainty_value": (
                    row.get("expanded_uncertainty")
                    or row.get("standard_uncertainty")
                    or ""
                ),
                "uncertainty_kind": row.get("uncertainty_kind", ""),
                "confidence_level": row.get("confidence_level", ""),
                "source_doi": row.get("doi", ""),
                "source_type": "thermoml",
                "source_file": (
                    "data/raw/thermoml/" + portable_basename(row["source_file"])
                ),
                "sha256": row["source_sha256"],
                "selection_status": "high_temperature_extension",
                "gate_flags": (
                    "high_temperature_extension|zero_frequency|"
                    "pure_component|experimental"
                ),
            }
        )
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in selected:
        grouped[row["inchikey"]].append(row)
    compound_rows: list[dict[str, str]] = []
    for inchikey, rows in sorted(grouped.items()):
        values = [Decimal(row["dielectric"]) for row in rows]
        temperatures = [Decimal(row["T_K"]) for row in rows]
        compound_rows.append(
            {
                "inchikey": inchikey,
                "smiles": rows[0]["smiles"],
                "name": rows[0]["name"],
                "T_K": _text(_median(temperatures)),
                "dielectric": _text(_median(values)),
                "frequency_MHz": "0",
                "property_family": "zero_frequency",
                "uncertainty": "",
                "uncertainty_value": "",
                "uncertainty_kind": rows[0]["uncertainty_kind"],
                "confidence_level": rows[0]["confidence_level"],
                "uncertainty_text": "",
                "uncertainty_relative_percent_max": "",
                "source_doi": ";".join(
                    sorted({row["source_doi"] for row in rows})
                ),
                "source_type": "thermoml",
                "source_file": ";".join(
                    sorted({row["source_file"] for row in rows})
                ),
                "sha256": ";".join(sorted({row["sha256"] for row in rows})),
                "n_observations": str(len(rows)),
                "gate_flags": (
                    "high_temperature_extension|zero_frequency|"
                    "pure_component|experimental"
                ),
            }
        )
    return compound_rows, selected


def check_nist_compounds(
    rows: Sequence[Mapping[str, str]],
    *,
    root: Path,
) -> Check:
    expected_rows, _ = _independent_nist(root)
    actual_nist = [row for row in rows if row.get("inchikey") != EC_INCHIKEY]
    if len(actual_nist) != len(expected_rows):
        return Check(
            "NIST extension compounds",
            False,
            f"expected {len(expected_rows)} rows, got {len(actual_nist)}",
        )
    actual_by_key = {row["inchikey"]: row for row in actual_nist}
    for expected in expected_rows:
        actual = actual_by_key.get(expected["inchikey"])
        if actual is None:
            return Check(
                "NIST extension compounds",
                False,
                f"missing key {expected['inchikey']}",
            )
        for column, expected_value in expected.items():
            if actual.get(column) != expected_value:
                return Check(
                    "NIST extension compounds",
                    False,
                    f"{column} mismatch for {expected['inchikey']}; median/source mismatch",
                )
    return Check(
        "NIST extension compounds",
        True,
        "46 NIST compound medians and source metadata reproduced",
    )


def check_nist_observations(
    rows: Sequence[Mapping[str, str]],
    *,
    root: Path,
) -> Check:
    _, expected_rows = _independent_nist(root)
    actual_nist = [row for row in rows if row.get("dataset_source") == "P1 ThermoML"]
    if len(actual_nist) != len(expected_rows):
        return Check(
            "NIST extension observations",
            False,
            f"expected {len(expected_rows)} rows, got {len(actual_nist)}",
        )
    expected_by_id = {row["observation_id"]: row for row in expected_rows}
    for actual in actual_nist:
        expected = expected_by_id.get(actual["observation_id"])
        if expected is None:
            return Check(
                "NIST extension observations",
                False,
                f"unexpected observation {actual['observation_id']}",
            )
        for column in ("inchikey", "T_K", "dielectric", "sha256", "source_file"):
            if actual.get(column) != expected[column]:
                label = "source hash" if column == "sha256" else column
                return Check(
                    "NIST extension observations",
                    False,
                    f"{label} mismatch for {actual['observation_id']}",
                )
        source_path = root / actual["source_file"]
        if source_path.is_file():
            digest = hashlib.sha256(source_path.read_bytes()).hexdigest()
            if digest != actual["sha256"]:
                return Check(
                    "NIST extension observations",
                    False,
                    f"source hash mismatch for {actual['observation_id']}",
                )
    return Check(
        "NIST extension observations",
        True,
        "205 NIST observations match raw values, temperatures, and source hashes",
    )


def check_ec_row(row: Mapping[str, str]) -> Check:
    if (
        row.get("inchikey") != EC_INCHIKEY
        or row.get("name") != "ethylene carbonate"
        or row.get("T_K") != "313.15"
        or row.get("dielectric") != "90.5"
    ):
        return Check("EC extension row", False, "EC identity/value mismatch")
    if row.get("frequency_MHz") != "1" or row.get("property_family") != "frequency_dependent":
        return Check(
            "EC extension row",
            False,
            "EC frequency/property_family mismatch",
        )
    if (
        row.get("source_doi") != EC_DOI
        or row.get("source_type") != "literature_manual_entry"
        or row.get("uncertainty_text") != "<1.5% relative"
        or row.get("uncertainty_relative_percent_max") != "1.5"
    ):
        return Check("EC extension row", False, "EC source/uncertainty mismatch")
    expected_flags = {
        "high_temperature_extension",
        "literature_manual_entry",
        "single_source",
        "frequency_1mhz",
    }
    if set(str(row.get("gate_flags", "")).split("|")) != expected_flags:
        return Check("EC extension row", False, "EC gate flags mismatch")
    return Check("EC extension row", True, "exact EC Table 1 row preserved")


def check_ec_summary(summary: Mapping[str, object]) -> Check:
    entry = summary.get("ec_manual_entry")
    if not isinstance(entry, Mapping):
        return Check("EC extension summary", False, "EC metadata missing")
    expected = {
        "name": "ethylene carbonate",
        "inchikey": EC_INCHIKEY,
        "T_K": "313.15",
        "temperature_C": "40",
        "dielectric": "90.5",
        "frequency_MHz": "1",
        "property_family": "frequency_dependent",
        "source_doi": EC_DOI,
        "sample_purity": ">99.9 mass%",
        "instrument": "Agilent 4284A / 16452A",
        "uncertainty_text": "<1.5% relative",
        "uncertainty_relative_percent_max": "1.5",
    }
    for key, value in expected.items():
        if entry.get(key) != value:
            return Check("EC extension summary", False, f"EC {key} mismatch")
    if "Table 1" not in str(entry.get("source")) or "p416" not in str(entry.get("source")):
        return Check("EC extension summary", False, "EC Table 1 p416 metadata mismatch")
    return Check("EC extension summary", True, "EC metadata is exact and complete")


def run_checks(root: Path = ROOT) -> list[Check]:
    raw_path = root / "data" / "processed" / "dielectric_raw.csv"
    ext_path = root / "data" / "dielectric_v01_ext.csv"
    observations_path = (
        root / "data" / "processed" / "dielectric_v01_ext_observations.csv"
    )
    summary_path = root / "probes" / "dielectric_v01_ext_summary.json"
    main_path = root / "data" / "dielectric_v01.csv"
    missing = [
        str(path)
        for path in (raw_path, ext_path, observations_path, summary_path, main_path)
        if not path.is_file()
    ]
    if missing:
        return [Check("dielectric extension artifacts", False, f"missing: {missing}")]
    rows = read_csv_rows(ext_path)
    observations = read_csv_rows(observations_path)
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    ec = next((row for row in rows if row["inchikey"] == EC_INCHIKEY), None)
    checks = [
        Check(
            "dielectric extension counts",
            len(rows) == 47 and len(observations) == 206,
            f"{len(rows)} keys, {len(observations)} observation rows",
        ),
        check_nist_compounds(rows, root=root),
        check_nist_observations(observations, root=root),
    ]
    if ec is None:
        checks.append(Check("EC extension row", False, "EC row missing"))
    else:
        checks.append(check_ec_row(ec))
    checks.append(check_ec_summary(summary))
    invalid_flags = {
        flag
        for row in observations
        for flag in row["gate_flags"].split("|")
        if flag not in GATE_FLAGS
    }
    checks.append(
        Check(
            "dielectric extension flags",
            not invalid_flags,
            "all flags registered" if not invalid_flags else str(sorted(invalid_flags)),
        )
    )
    if canonical_text_sha256(main_path) != EXPECTED_MAIN_SHA256:
        checks.append(
            Check("main v0.1 immutability", False, "main v0.1 SHA256 changed")
        )
    else:
        checks.append(
            Check("main v0.1 immutability", True, "main v0.1 canonical hash unchanged")
        )
    return checks


def main(argv: Sequence[str] | None = None, *, stdout: TextIO | None = None) -> int:
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
                {"passed": not failures, "checks": [asdict(check) for check in checks]},
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
