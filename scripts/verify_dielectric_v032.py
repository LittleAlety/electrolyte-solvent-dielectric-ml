"""Independently verify the v0.3.2 revision against the v0.3.1 baseline."""

from __future__ import annotations

import csv
import json
import subprocess
from collections import Counter
from collections.abc import Mapping, Sequence
from io import StringIO
from pathlib import Path
from urllib.parse import unquote, urlsplit

from rdkit import Chem

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
V03_PATH = REPOSITORY_ROOT / "data" / "dielectric_v03.csv"
V031_PATH = REPOSITORY_ROOT / "data" / "dielectric_v031.csv"
V032_PATH = REPOSITORY_ROOT / "data" / "dielectric_v032.csv"

PC_INCHIKEY = "RUOJZAUFBMNUDX-UHFFFAOYSA-N"
EC_INCHIKEY = "KMTRUDSVKNLOMY-UHFFFAOYSA-N"
VC_INCHIKEY = "VAYTZRYEBVHVLE-UHFFFAOYSA-N"
METHYL_PROPIONATE_INCHIKEY = "RJUFJBKOKNCXHH-UHFFFAOYSA-N"

PC_DOI = "10.1021/j100702a008"
EXPECTED_ROW_COUNT = 245
EXPECTED_MODEL_READY_COUNT = 240
EXPECTED_CONFLICT_COUNT = 6
EXPECTED_ADDED_KEYS = frozenset({PC_INCHIKEY, EC_INCHIKEY})
EXPECTED_SOURCE_SCOPES = frozenset(
    {
        "",
        "nbs514_manual_static_293.15_303.15K",
        "p1_thermoml_zero_frequency_pure_293.15_303.15K",
        (
            "p1_thermoml_zero_frequency_pure_293.15_303.15K;"
            "chodera_2015_historical_dielectric_crosscheck"
        ),
    }
)

REQUIRED_COLUMNS = (
    "inchikey",
    "smiles",
    "name",
    "T_K",
    "dielectric",
    "uncertainty",
    "uncertainty_value",
    "uncertainty_kind",
    "confidence_level",
    "uncertainty_json",
    "source_doi",
    "source_dois_all",
    "n_observations",
    "n_historical_observations",
    "source_scope",
    "crosscheck_available",
    "gate_flags",
    "source_record_id",
    "source_page",
    "source_quality",
    "selection_rank",
    "structure_resolution_source",
    "al_round1_hit",
    "max_tanimoto_solvfunc",
    "dataset_origin",
    "temperature_band",
    "evidence_level",
    "temperature_source",
    "model_ready",
    "conflict_status",
    "source_url",
    "source_citation",
    "source_table",
    "redistribution_status",
    "source_license",
    "license_url",
    "redistribution_conditions",
    "notes",
)


def read_csv_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    """Read a CSV and reject duplicate or malformed headers."""

    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or ())
        rows = list(reader)

    if not fieldnames or any(field is None for field in fieldnames):
        raise ValueError(f"{path}: missing or malformed CSV header")
    if len(fieldnames) != len(set(fieldnames)):
        raise ValueError(f"{path}: duplicate CSV column names")
    if any(None in row for row in rows):
        raise ValueError(f"{path}: row has more values than the header")
    return fieldnames, rows


def read_rows(path: Path) -> list[dict[str, str]]:
    """Backward-compatible row-only CSV reader."""

    _, rows = read_csv_rows(path)
    return rows


def load_baseline_rows(
    v031_path: Path = V031_PATH,
    v03_path: Path = V03_PATH,
) -> tuple[str, list[str], list[dict[str, str]]]:
    """Prefer frozen v0.3.1, falling back to the HEAD v0.3 file."""

    if v031_path.exists():
        fields, rows = read_csv_rows(v031_path)
        return v031_path.relative_to(REPOSITORY_ROOT).as_posix(), fields, rows

    repository_path = v03_path.resolve().relative_to(REPOSITORY_ROOT.resolve()).as_posix()
    source = f"HEAD:{repository_path}"
    completed = subprocess.run(
        ["git", "show", source],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    reader = csv.DictReader(StringIO(completed.stdout))
    fields = list(reader.fieldnames or ())
    rows = list(reader)
    if not fields:
        raise ValueError(f"{source}: missing CSV header")
    return source, fields, rows


def validate_required_columns(fieldnames: Sequence[str]) -> list[str]:
    missing = [field for field in REQUIRED_COLUMNS if field not in fieldnames]
    if not missing:
        return []
    return [f"missing required columns: {', '.join(missing)}"]


def check_unique_keys(
    rows: Sequence[Mapping[str, str]],
) -> tuple[list[str], dict[str, Mapping[str, str]]]:
    errors: list[str] = []
    counts = Counter(str(row.get("inchikey", "")) for row in rows)
    duplicates = sorted(key for key, count in counts.items() if key and count > 1)
    missing_keys = counts.get("", 0)
    if duplicates:
        errors.append(f"duplicate InChIKeys: {', '.join(duplicates)}")
    if missing_keys:
        errors.append(f"rows with missing InChIKey: {missing_keys}")

    by_key: dict[str, Mapping[str, str]] = {}
    for row in rows:
        key = str(row.get("inchikey", ""))
        if key and key not in by_key:
            by_key[key] = row
    return errors, by_key


def check_smiles_inchikeys(rows: Sequence[Mapping[str, str]]) -> list[str]:
    errors: list[str] = []
    for index, row in enumerate(rows, start=1):
        key = str(row.get("inchikey", ""))
        smiles = str(row.get("smiles", ""))
        label = key or f"row {index}"
        if not smiles:
            errors.append(f"{label}: missing SMILES")
            continue
        molecule = Chem.MolFromSmiles(smiles)
        if molecule is None:
            errors.append(f"{label}: invalid SMILES {smiles!r}")
            continue
        derived_key = Chem.MolToInchiKey(molecule)
        if derived_key != key:
            errors.append(
                f"{label}: SMILES InChIKey mismatch: {derived_key!r} != {key!r}"
            )
    return errors


def canonical_doi(value: str) -> str:
    token = value.strip()
    if token.casefold().startswith("doi:"):
        token = token[4:].strip()
    parsed = urlsplit(token)
    if (
        parsed.scheme.casefold() in {"http", "https"}
        and (parsed.hostname or "").casefold()
        in {"doi.org", "dx.doi.org", "www.doi.org"}
    ):
        token = unquote(parsed.path).strip("/")
    return token.rstrip("/").casefold()


def _doi_tokens(value: str) -> list[str]:
    return [token.strip() for token in value.split(";") if token.strip()]


def check_source_metadata(rows: Sequence[Mapping[str, str]]) -> list[str]:
    errors: list[str] = []
    for index, row in enumerate(rows, start=1):
        label = str(row.get("inchikey", "")) or f"row {index}"
        source_doi = str(row.get("source_doi", "")).strip()
        source_dois_all = str(row.get("source_dois_all", ""))
        if not source_doi:
            errors.append(f"{label}: missing source_doi")

        if source_dois_all:
            tokens = _doi_tokens(source_dois_all)
            if len(tokens) != len(source_dois_all.split(";")):
                errors.append(f"{label}: source_dois_all contains an empty DOI token")
            available = {canonical_doi(token) for token in tokens}
            for token in _doi_tokens(source_doi):
                if canonical_doi(token) not in available:
                    errors.append(
                        f"{label}: source_doi {token!r} is absent from source_dois_all"
                    )

        source_url = str(row.get("source_url", "")).strip()
        if source_url:
            parsed_url = urlsplit(source_url)
            if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
                errors.append(f"{label}: invalid source_url {source_url!r}")

        if str(row.get("dataset_origin", "")) == "v0.3_addition":
            for field in ("source_citation", "source_table", "source_quality"):
                if not str(row.get(field, "")).strip():
                    errors.append(f"{label}: addition is missing {field}")

        source_scope = str(row.get("source_scope", ""))
        if source_scope not in EXPECTED_SOURCE_SCOPES:
            errors.append(f"{label}: unsupported source_scope {source_scope!r}")
        if str(row.get("dataset_origin", "")) == "v0.2" and not source_scope:
            errors.append(f"{label}: v0.2 row is missing source_scope")
        if str(row.get("dataset_origin", "")) == "v0.3_addition" and source_scope:
            errors.append(f"{label}: v0.3 addition has unexpected source_scope")
    return errors


def _expect_value(
    row: Mapping[str, str],
    field: str,
    expected: str,
    label: str,
    errors: list[str],
) -> None:
    actual = str(row.get(field, ""))
    if actual != expected:
        errors.append(f"{label}: {field} {actual!r} != {expected!r}")


def check_required_key_rows(
    rows: Sequence[Mapping[str, str]],
) -> tuple[list[str], dict[str, Mapping[str, str]]]:
    errors, by_key = check_unique_keys(rows)

    pc = by_key.get(PC_INCHIKEY)
    if pc is None:
        errors.append("propylene carbonate (PC) missing")
    else:
        _expect_value(pc, "smiles", "CC1COC(=O)O1", "PC", errors)
        _expect_value(pc, "T_K", "298.15", "PC", errors)
        _expect_value(pc, "dielectric", "64.9", "PC", errors)
        _expect_value(pc, "temperature_band", "room_temperature", "PC", errors)
        _expect_value(pc, "evidence_level", "primary", "PC", errors)
        _expect_value(pc, "model_ready", "true", "PC", errors)
        _expect_value(pc, "source_doi", PC_DOI, "PC", errors)
        _expect_value(
            pc,
            "source_url",
            f"https://doi.org/{PC_DOI}",
            "PC",
            errors,
        )
        _expect_value(
            pc,
            "source_citation",
            "Simeral & Amey (1970) J. Phys. Chem. 74, 1443",
            "PC",
            errors,
        )
        _expect_value(pc, "source_table", "Table II", "PC", errors)
        if PC_DOI not in _doi_tokens(str(pc.get("source_dois_all", ""))):
            errors.append(f"PC: source_dois_all does not contain {PC_DOI}")

    ec = by_key.get(EC_INCHIKEY)
    if ec is None:
        errors.append("ethylene carbonate (EC) missing")
    else:
        _expect_value(ec, "smiles", "O=C1OCCO1", "EC", errors)
        _expect_value(ec, "T_K", "313.15", "EC", errors)
        _expect_value(ec, "dielectric", "90.5", "EC", errors)
        _expect_value(ec, "temperature_band", "extended_temperature", "EC", errors)
        _expect_value(ec, "evidence_level", "primary", "EC", errors)
        _expect_value(ec, "model_ready", "true", "EC", errors)
        _expect_value(ec, "source_doi", "10.1021/je050341y", "EC", errors)
        _expect_value(
            ec,
            "source_url",
            "https://doi.org/10.1021/je050341y",
            "EC",
            errors,
        )
        _expect_value(
            ec,
            "source_citation",
            "Chernyak (2006) J. Chem. Eng. Data 51, 416",
            "EC",
            errors,
        )
        _expect_value(ec, "source_table", "Table 2", "EC", errors)

    vc = by_key.get(VC_INCHIKEY)
    if vc is None:
        errors.append("vinylene carbonate (VC) missing")
    else:
        _expect_value(vc, "name", "vinylene carbonate", "VC", errors)
        _expect_value(vc, "model_ready", "false", "VC", errors)
        _expect_value(vc, "conflict_status", "conflict_open", "VC", errors)

    methyl_propionate = by_key.get(METHYL_PROPIONATE_INCHIKEY)
    if methyl_propionate is None:
        errors.append("methyl propionate missing")
    else:
        _expect_value(
            methyl_propionate,
            "name",
            "methyl propionate",
            "methyl propionate",
            errors,
        )
        _expect_value(
            methyl_propionate,
            "conflict_status",
            "conflict_open",
            "methyl propionate",
            errors,
        )
    return errors, by_key


def compare_superset(
    actual_rows: Sequence[Mapping[str, str]],
    baseline_rows: Sequence[Mapping[str, str]],
    *,
    baseline_source: str,
) -> tuple[list[str], dict[str, object]]:
    errors: list[str] = []
    baseline_by_key: dict[str, Mapping[str, str]] = {}
    for row in baseline_rows:
        key = str(row.get("inchikey", ""))
        if key and key not in baseline_by_key:
            baseline_by_key[key] = row
    actual_by_key: dict[str, Mapping[str, str]] = {}
    for row in actual_rows:
        key = str(row.get("inchikey", ""))
        if key and key not in actual_by_key:
            actual_by_key[key] = row

    missing_keys = sorted(set(baseline_by_key) - set(actual_by_key))
    added_keys = sorted(set(actual_by_key) - set(baseline_by_key))
    common_keys = sorted(set(actual_by_key) & set(baseline_by_key))
    mismatch_details: list[dict[str, object]] = []
    equal_common_rows = 0
    for key in common_keys:
        baseline_row = baseline_by_key[key]
        actual_row = actual_by_key[key]
        fields = sorted(
            field
            for field in set(baseline_row) | set(actual_row)
            if baseline_row.get(field, "") != actual_row.get(field, "")
        )
        if fields:
            mismatch_details.append({"inchikey": key, "fields": fields})
        else:
            equal_common_rows += 1

    if missing_keys:
        errors.append(f"baseline keys missing from v0.3.2: {', '.join(missing_keys)}")
    if set(added_keys) != EXPECTED_ADDED_KEYS:
        errors.append(
            "unexpected added keys: "
            f"expected {sorted(EXPECTED_ADDED_KEYS)}, found {added_keys}"
        )
    if mismatch_details:
        errors.append(
            "common-key field mismatches: "
            f"{json.dumps(mismatch_details[:20], ensure_ascii=False)}"
        )
    if equal_common_rows != len(baseline_by_key):
        errors.append(
            "common-key equality count mismatch: "
            f"{equal_common_rows} != {len(baseline_by_key)}"
        )

    report: dict[str, object] = {
        "baseline_source": baseline_source,
        "baseline_row_count": len(baseline_by_key),
        "common_key_count": len(common_keys),
        "equal_common_rows": equal_common_rows,
        "missing_key_count": len(missing_keys),
        "missing_keys": missing_keys,
        "added_key_count": len(added_keys),
        "added_keys": added_keys,
        "mismatch_count": len(mismatch_details),
        "mismatch_details": mismatch_details[:20],
    }
    return errors, report


def check_counts(
    rows: Sequence[Mapping[str, str]],
) -> tuple[list[str], int, int]:
    errors: list[str] = []
    row_count = len(rows)
    model_ready_count = sum(
        str(row.get("model_ready", "")) == "true" for row in rows
    )
    conflict_count = sum(bool(row.get("conflict_status")) for row in rows)
    if row_count != EXPECTED_ROW_COUNT:
        errors.append(f"row count {row_count} != {EXPECTED_ROW_COUNT}")
    if model_ready_count != EXPECTED_MODEL_READY_COUNT:
        errors.append(
            f"model_ready count {model_ready_count} != {EXPECTED_MODEL_READY_COUNT}"
        )
    if conflict_count != EXPECTED_CONFLICT_COUNT:
        errors.append(f"conflict count {conflict_count} != {EXPECTED_CONFLICT_COUNT}")
    return errors, model_ready_count, conflict_count


def _check(name: str, errors: Sequence[str]) -> dict[str, object]:
    return {
        "name": name,
        "passed": not errors,
        "errors": list(errors),
    }


def verify_v032(v032_path: Path = V032_PATH) -> dict[str, object]:
    checks: list[dict[str, object]] = []
    try:
        fieldnames, rows = read_csv_rows(v032_path)
    except (OSError, ValueError) as exc:
        return {
            "passed": False,
            "checks_run": [
                _check("read_v032", [str(exc)]),
            ],
            "row_count": 0,
            "errors": [str(exc)],
        }

    column_errors = validate_required_columns(fieldnames)
    checks.append(_check("required_columns", column_errors))
    if column_errors:
        return {
            "passed": False,
            "checks_run": checks,
            "row_count": len(rows),
            "errors": column_errors,
        }

    unique_errors, _ = check_unique_keys(rows)
    checks.append(_check("unique_inchikeys", unique_errors))
    smiles_errors = check_smiles_inchikeys(rows)
    checks.append(_check("smiles_inchikey_consistency", smiles_errors))
    source_errors = check_source_metadata(rows)
    checks.append(_check("source_metadata", source_errors))
    key_errors, _ = check_required_key_rows(rows)
    checks.append(_check("required_key_rows", key_errors))
    count_errors, model_ready_count, conflict_count = check_counts(rows)
    checks.append(_check("dataset_counts", count_errors))

    try:
        baseline_source, _, baseline_rows = load_baseline_rows()
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        superset_errors = [f"could not load baseline: {exc}"]
        superset_report: dict[str, object] = {"baseline_source": None}
    else:
        superset_errors, superset_report = compare_superset(
            rows,
            baseline_rows,
            baseline_source=baseline_source,
        )
    checks.append(_check("v031_superset", superset_errors))

    errors = [
        error
        for check in checks
        for error in check["errors"]
    ]
    return {
        "passed": not errors,
        "checks_run": checks,
        "row_count": len(rows),
        "model_ready_count": model_ready_count,
        "conflict_count": conflict_count,
        "superset_comparison": superset_report,
        "errors": errors,
    }


def main() -> int:
    report = verify_v032()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())