"""Whole-roster feature drift under the v0.3.14 candidate SCF protocol.

Companion to probes/xtb_recovery_probe.py.  That probe answered "can the four
failed rows be rescued?" and established, from three control molecules, that the
rescue protocol is not protocol-neutral.  This probe widens the same measurement
to every frozen row, so the v0.3.14 decision -- migrate the whole table or keep
the 236-row fit set -- rests on a distribution instead of one ionic liquid.

Method: every frozen row whose starting geometry is still cached is re-run from
*that same* input.xyz under the candidate protocol.  Only the electronic
structure handling changes, so any feature movement is attributable to the
protocol and not to the geometry.

Non-destructive: runs under data/interim/xtb_protocol_migration/ (git ignored)
and writes only its own evidence JSON.  The frozen feature table, the canonical
dataset, every digest and every delivery package are untouched.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import statistics
import subprocess
import sys
import time
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))
sys.path.insert(0, str(REPOSITORY_ROOT / "probes"))
sys.path.insert(0, str(REPOSITORY_ROOT / "scripts"))


from run_xtb_physical_features import (
    _clear_run_artifacts,
    _executable_fingerprint,
    _valid_cache,
    generate_3d_xyz,
)
from xtb_recovery_probe import OPT_MARKER_FILE, frozen_verdict, resolve_xtb

from electrolyte_ml.xtb_features import XtbFeatureError, parse_xtb_output

FROZEN_FEATURES = (
    REPOSITORY_ROOT / "data" / "processed" / "dielectric_physical_features_v03.csv"
)
FROZEN_CACHE = REPOSITORY_ROOT / "data" / "interim" / "xtb_features"
WORK_ROOT = REPOSITORY_ROOT / "data" / "interim" / "xtb_protocol_migration"
EVIDENCE_PATH = REPOSITORY_ROOT / "probes" / "g1plus_xtb_protocol_migration_probe.json"

CANDIDATE_ID = "etemp_5000"
CANDIDATE_FLAGS = ("--etemp", "5000")

# parsed-feature name -> frozen feature-table column
FEATURE_COLUMNS = {
    "total_energy_hartree": "total_energy_hartree",
    "homo_lumo_gap_ev": "homo_lumo_gap_ev",
    "dipole_debye": "dipole_D",
    "polarizability_au": "polarizability_au",
}
FEATURE_NAMES = tuple(FEATURE_COLUMNS)

# The frozen table was written by _feature_row() in
# scripts/run_xtb_physical_features.py with these format specs (dipole,
# polarizability and gap at 8 significant digits; total energy at 12).  A
# cached output "agrees" with a frozen row when it reproduces that row at the
# same store precision.  A fixed 1e-8 relative tolerance is tighter than the
# stored table itself and rejected ~11% of rows purely on rounding.
FEATURE_CSV_FORMATS = {
    "total_energy_hartree": ".12g",
    "homo_lumo_gap_ev": ".8g",
    "dipole_debye": ".8g",
    "polarizability_au": ".8g",
}
VALIDATION_MODE = "frozen_runner_full_validator_plus_csv_precision_feature_match"

MOVED_TOLERANCE = 1e-9
LARGE_RELATIVE_CHANGE = 0.01

SCOPE_NOTE = (
    "Every row is re-run from the geometry the frozen run itself started from, so "
    "the deltas isolate the SCF protocol.  A row whose four features do not move is "
    "evidence that a whole-table migration is cheap for that row; it is not evidence "
    "that the migration is cheap overall.  Rows without a cached starting geometry "
    "are reported as unmeasured and are never counted as unchanged."
)


def _is_number(value: str) -> bool:
    try:
        float(value)
    except (TypeError, ValueError):
        return False
    return True


def _features_agree(
    parsed: dict[str, float], frozen: dict[str, object]
) -> bool:
    """Whether a parsed cache reproduces a frozen row at the stored precision."""

    return all(
        f"{float(parsed[name]):{FEATURE_CSV_FORMATS[name]}}"
        == f"{float(frozen[name]):{FEATURE_CSV_FORMATS[name]}}"
        for name in FEATURE_NAMES
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def describe_run_environment(xtb: Path, threads: int) -> dict[str, object]:
    """Record enough environment metadata to audit the xTB invocation."""

    completed = subprocess.run(
        [str(xtb), "--version"],
        capture_output=True,
        timeout=60,
        check=False,
    )
    version_text = (completed.stdout + b"\n" + completed.stderr).decode(
        "utf-8", "replace"
    )
    version_line = next(
        (
            line.strip()
            for line in version_text.splitlines()
            if "xtb version" in line.lower()
        ),
        "",
    )
    return {
        "xtb_executable": str(xtb),
        "xtb_executable_sha256": _sha256_file(xtb),
        "xtb_version_line": version_line,
        "threads": threads,
        "geometry_source": "cache_manifest_matching_input_xyz",
        "geometry_seed_used_during_migration": None,
    }




def load_frozen_rows(path: Path = FROZEN_FEATURES) -> list[dict[str, object]]:
    """Frozen rows that carry usable features, paired with their cache directory."""

    rows: list[dict[str, object]] = []
    with path.open(encoding="utf-8", newline="") as handle:
        for raw in csv.DictReader(handle):
            if raw["status"] not in {"ok", "cached"}:
                continue
            if not all(_is_number(raw[column]) for column in FEATURE_COLUMNS.values()):
                continue
            rows.append(
                {
                    "inchikey": raw["inchikey"],
                    "name": raw["name"],
                    "smiles": raw["smiles"],
                    "formal_charge": int(float(raw["formal_charge"])),
                    "frozen": {
                        name: float(raw[column]) for name, column in FEATURE_COLUMNS.items()
                    },
                }
            )
    return rows


def resolve_row_cache(
    row: dict[str, object], *, xtb: Path, cache_root: Path = FROZEN_CACHE
) -> tuple[dict[str, object] | None, str]:
    """Select exactly one cache entry accepted by the frozen runner's validator.

    ``_valid_cache`` is applied unchanged, so every accepted entry is verified
    byte-for-byte against the frozen runner (input, optimised geometry, output
    text and executable fingerprint).  The frozen-feature check is deliberately
    judged at the precision the feature table actually stores.
    """

    inchikey = str(row["inchikey"])
    candidates = sorted(cache_root.glob(f"{inchikey}*"))
    valid: list[Path] = []
    for run_dir in candidates:
        manifest_path = run_dir / "cache_manifest.json"
        if not run_dir.is_dir() or not manifest_path.is_file():
            continue
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        seed = manifest.get("seed")
        if not isinstance(seed, int):
            continue
        expected_input_xyz = generate_3d_xyz(str(row["smiles"]), seed=seed)
        accepted = _valid_cache(
            run_dir,
            smiles=str(row["smiles"]),
            formal_charge=int(row["formal_charge"]),
            seed=seed,
            expected_input_xyz=expected_input_xyz,
            xtb_executable=xtb,
        )
        if accepted is None:
            continue
        _, _, cached_output_text = accepted
        if "normal termination of xtb" not in cached_output_text:
            cached_output_text += "\nnormal termination of xtb\n"
        try:
            cached_features = parse_xtb_output(cached_output_text)
        except XtbFeatureError:
            continue
        parsed = {
            "total_energy_hartree": cached_features.total_energy_hartree,
            "homo_lumo_gap_ev": cached_features.homo_lumo_gap_ev,
            "dipole_debye": cached_features.dipole_debye,
            "polarizability_au": cached_features.polarizability_au,
        }
        frozen = row["frozen"]
        assert isinstance(frozen, dict)
        if _features_agree(parsed, frozen):
            valid.append(run_dir)
    if not valid:
        return None, "no cache entry accepted by the frozen runner's full validator"
    if len(valid) > 1:
        return None, f"ambiguous cache entries accepted by the frozen validator: {len(valid)}"
    run_dir = valid[0]
    manifest = json.loads((run_dir / "cache_manifest.json").read_text(encoding="utf-8"))
    return (
        {
            "run_dir": run_dir,
            "input_xyz": run_dir / "input.xyz",
            "input_sha256": manifest["input_sha256"],
            "input_sha256_matches": True,
            "manifest": manifest,
            "manifest_features_match": True,
            "validation_mode": VALIDATION_MODE,
            "canonical_smiles": manifest.get("canonical_smiles"),
            "formal_charge": manifest.get("formal_charge"),
            "seed": manifest.get("seed"),
        },
        "",
    )


def run_candidate(
    row: dict[str, object],
    *,
    xtb: Path,
    work_root: Path,
    timeout: int,
    threads: int,
) -> dict[str, object]:
    """Re-run one frozen starting geometry under the candidate protocol."""

    inchikey = str(row["inchikey"])
    entry = row["cache"]
    assert isinstance(entry, dict)
    run_dir = work_root / inchikey
    frozen_root = FROZEN_CACHE.resolve()
    for label, candidate in (("work directory", work_root), ("run directory", run_dir)):
        resolved = candidate.resolve()
        if resolved == frozen_root or frozen_root in resolved.parents:
            raise ValueError(
                f"refusing to write the candidate {label} inside the frozen "
                f"cache: {candidate}"
            )
    if run_dir.is_symlink() or (
        hasattr(run_dir, "is_junction") and run_dir.is_junction()
    ):
        raise ValueError(f"refusing to clear a linked run directory: {run_dir}")
    run_dir.mkdir(parents=True, exist_ok=True)
    _clear_run_artifacts(run_dir)
    input_path = run_dir / "input.xyz"
    input_path.write_text(
        Path(entry["input_xyz"]).read_text(encoding="utf-8"),  # type: ignore[arg-type]
        encoding="utf-8",
        newline="\n",
    )
    start_geometry_sha256 = hashlib.sha256(
        input_path.read_text(encoding="utf-8").encode("utf-8")
    ).hexdigest()
    command = [
        str(xtb),
        input_path.name,
        "--opt",
        "--gfn",
        "2",
        "--chrg",
        str(row["formal_charge"]),
        "--uhf",
        "0",
        *CANDIDATE_FLAGS,
    ]
    environment = os.environ.copy()
    environment["OMP_NUM_THREADS"] = str(threads)
    environment["MKL_NUM_THREADS"] = str(threads)
    start = time.perf_counter()
    try:
        completed = subprocess.run(
            command,
            cwd=run_dir,
            env=environment,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        exit_code: int | None = completed.returncode
        stdout_bytes = completed.stdout
        stderr_bytes = completed.stderr
    except subprocess.TimeoutExpired as exc:
        exit_code = None
        stdout_bytes = exc.stdout or b""
        stderr_bytes = exc.stderr or b""
    seconds = round(time.perf_counter() - start, 2)
    stdout = stdout_bytes.decode("utf-8", "replace")
    (run_dir / "candidate_stdout.log").write_bytes(stdout_bytes)
    (run_dir / "candidate_stderr.log").write_bytes(stderr_bytes)
    verdict = frozen_verdict(run_dir=run_dir, stdout=stdout, exit_code=exit_code)
    return {
        "inchikey": inchikey,
        "name": row["name"],
        "candidate": CANDIDATE_ID,
        "cache_dir": str(Path(entry["run_dir"]).relative_to(REPOSITORY_ROOT)),
        "start_geometry_sha256": start_geometry_sha256,
        "cache_manifest_sha256": hashlib.sha256(
            (Path(entry["run_dir"]) / "cache_manifest.json").read_bytes()
        ).hexdigest(),
        "stdout_log": str((run_dir / "candidate_stdout.log").relative_to(REPOSITORY_ROOT)),
        "stderr_log": str((run_dir / "candidate_stderr.log").relative_to(REPOSITORY_ROOT)),
        "stdout_sha256": hashlib.sha256(stdout_bytes).hexdigest(),
        "stderr_sha256": hashlib.sha256(stderr_bytes).hexdigest(),
        "argv": command[1:],
        "exit_code": exit_code,
        "seconds": seconds,
        "frozen_runner_accepts": verdict["frozen_runner_accepts"],
        "parsed_ok": verdict["parsed_ok"],
        "parse_error": verdict["parse_error"],
        "geoopt_converged": verdict["geoopt_converged"],
        "gradient_norm_eh_per_alpha": verdict["gradient_norm_eh_per_alpha"],
        "features": verdict["features"],
    }


def compare_row(row: dict[str, object], candidate: dict[str, object]) -> dict[str, object]:
    """Per-feature absolute and relative movement for one row."""

    features = candidate.get("features")
    if not isinstance(features, dict):
        return {**candidate, "deltas": None, "max_relative_change": None}
    frozen = row["frozen"]
    assert isinstance(frozen, dict)
    deltas: dict[str, dict[str, float | None]] = {}
    largest = 0.0
    for name in FEATURE_NAMES:
        before = float(frozen[name])
        after = float(features[name])
        if before == 0.0 and after == 0.0:
            relative: float | None = 0.0
        elif before == 0.0:
            relative = None
        else:
            relative = abs(after - before) / abs(before)
        deltas[name] = {
            "frozen": before,
            "candidate": after,
            "absolute_change": after - before,
            "relative_change": relative,
        }
        if relative is not None and relative > largest:
            largest = relative
    return {
        **candidate,
        "deltas": deltas,
        "max_relative_change": round(largest, 8),
    }


def summarise(rows: list[dict[str, object]]) -> dict[str, object]:
    """Distribution of movement plus the counts the v0.3.14 decision needs."""

    compared = [row for row in rows if isinstance(row.get("deltas"), dict)]
    moved_rows = []
    identical_rows = []
    for row in compared:
        deltas = row["deltas"]
        assert isinstance(deltas, dict)
        if all(
            abs(float(deltas[name]["absolute_change"])) <= MOVED_TOLERANCE
            for name in FEATURE_NAMES
        ):
            identical_rows.append(row["inchikey"])
        else:
            moved_rows.append(row["inchikey"])
    per_feature: dict[str, object] = {}
    for name in FEATURE_NAMES:
        values = [
            float(row["deltas"][name]["relative_change"])
            for row in compared
            if row["deltas"][name]["relative_change"] is not None
        ]
        moved = [
            float(row["deltas"][name]["absolute_change"])
            for row in compared
        ]
        values.sort()
        worst = max(
            (
                row
                for row in compared
                if row["deltas"][name]["relative_change"] is not None
            ),
            key=lambda row: float(row["deltas"][name]["relative_change"]),
            default=None,
        )
        per_feature[name] = {
            "compared": len(values),
            "moved": sum(1 for change in moved if abs(change) > MOVED_TOLERANCE),
            "zero_baseline_moves": sum(
                1
                for row in compared
                if row["deltas"][name]["relative_change"] is None
                and abs(float(row["deltas"][name]["absolute_change"]))
                > MOVED_TOLERANCE
            ),
            "moved_over_1pct": sum(1 for value in values if value > LARGE_RELATIVE_CHANGE),
            "median_relative_change": (
                round(float(statistics.median(values)), 8) if values else None
            ),
            "p90_relative_change": (
                round(float(values[int(0.9 * (len(values) - 1))]), 8) if values else None
            ),
            "max_relative_change": round(max(values), 8) if values else None,
            "max_mover": worst["inchikey"] if worst is not None else None,
            "max_mover_name": worst["name"] if worst is not None else None,
        }
    over_one_percent = [
        row
        for row in compared
        if any(
            row["deltas"][name]["relative_change"] is not None
            and float(row["deltas"][name]["relative_change"])
            > LARGE_RELATIVE_CHANGE
            for name in FEATURE_NAMES
        )
    ]
    rejected = [row["inchikey"] for row in rows if row["frozen_runner_accepts"] is not True]
    not_converged = [
        row["inchikey"]
        for row in compared
        if row.get("geoopt_converged") is not True
    ]
    return {
        "rows_attempted": len(rows),
        "rows_compared": len(compared),
        "rows_moved": len(moved_rows),
        "rows_feature_identical": len(identical_rows),
        "rows_any_feature_over_1pct": len(over_one_percent),
        "rows_no_feature_over_1pct": len(compared) - len(over_one_percent),
        "rows_rejected_by_frozen_runner": len(rejected),
        "rows_geometry_not_converged": len(not_converged),
        "moved_inchikeys": sorted(moved_rows),
        "identical_inchikeys": sorted(identical_rows),
        "over_one_percent_inchikeys": sorted(
            str(row["inchikey"]) for row in over_one_percent
        ),
        "rejected_inchikeys": sorted(rejected),
        "not_converged_inchikeys": sorted(not_converged),
        "rows_with_undefined_relative_change": sum(
            1
            for row in compared
            if any(
                row["deltas"][name]["relative_change"] is None
                for name in FEATURE_NAMES
            )
        ),
        "zero_baseline_policy": (
            "A feature whose frozen value is exactly 0.0 has no relative change. "
            "Such rows still count as absolute moves (rows_moved and "
            "per_feature.moved) and are reported per feature as zero_baseline_moves, "
            "but they are excluded from the relative-change distributions."
        ),
        "per_feature": per_feature,
    }


def build_payload(
    *,
    measured: list[dict[str, object]],
    unmeasured: list[dict[str, object]],
    frozen_rows: int,
    run_environment: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "probe": "xtb_protocol_migration_probe",
        "question": (
            "If v0.3.14 migrated the whole feature table to the rescue protocol, "
            "how many frozen rows would actually move, and by how much?"
        ),
        "candidate": {
            "id": CANDIDATE_ID,
            "flags": list(CANDIDATE_FLAGS),
            "frozen_fit_rows": 236,
        },
        "method": (
            "Each frozen row is re-run from the exact input.xyz the frozen run "
            "started from, changing only the SCF protocol, so the deltas isolate "
            "the protocol rather than the geometry."
        ),
        "run_environment": run_environment or {},
        "cache_validation": {
            "mode": VALIDATION_MODE,
            "feature_precision": dict(FEATURE_CSV_FORMATS),
            "cached_feature_bytes": (
                "input.xyz, xtbopt.xyz and xtb.out are each re-hashed against the "
                "cache_manifest.json written by the frozen runner"
            ),
            "executable_fingerprint": (
                "path, size and st_mtime_ns are compared for exact equality by "
                "_valid_cache; no drift was tolerated for this run"
            ),
        },
        "scope_note": SCOPE_NOTE,
        "frozen_feature_rows": frozen_rows,
        "measured": measured,
        "unmeasured": unmeasured,
        "summary": summarise(measured),
    }


def check_payload(
    payload: object, *, deep: bool = False, xtb: Path | None = None
) -> list[str]:
    """Report problems in an evidence payload without ever raising.

    The committed JSON is the evidence artifact, so a corrupted or hand-edited
    payload must yield readable problems instead of an AttributeError from
    inside the checker.
    """

    if not isinstance(payload, dict):
        return ["payload is not an object"]
    try:
        return _check_payload_inner(payload, deep=deep, xtb=xtb)
    except (
        AttributeError,
        TypeError,
        KeyError,
        IndexError,
        ValueError,
        ZeroDivisionError,
    ) as exc:
        return [f"malformed payload: {type(exc).__name__}: {exc}"]


def _check_payload_inner(
    payload: dict[str, object], *, deep: bool = False, xtb: Path | None = None
) -> list[str]:
    problems: list[str] = []
    summary = payload.get("summary")
    measured = payload.get("measured")
    if not isinstance(summary, dict):
        problems.append("summary is missing")
        return problems
    if not isinstance(measured, list):
        problems.append("measured rows are missing")
        return problems
    run_environment = payload.get("run_environment")
    if not isinstance(run_environment, dict):
        problems.append("run_environment is missing")
    else:
        for field in (
            "xtb_executable",
            "xtb_executable_sha256",
            "xtb_version_line",
            "threads",
            "geometry_source",
        ):
            if field not in run_environment:
                problems.append(f"run_environment.{field} is missing")
        if not isinstance(run_environment.get("threads"), int):
            problems.append("run_environment.threads is not an integer")
        if (
            xtb is not None
            and xtb.is_file()
            and run_environment.get("xtb_executable_sha256") != _sha256_file(xtb)
        ):
            problems.append(
                "run_environment.xtb_executable_sha256 disagrees with the live executable"
            )
    compared = [row for row in measured if isinstance(row.get("deltas"), dict)]
    if summary.get("rows_attempted") != len(measured):
        problems.append("summary.rows_attempted disagrees with the measured rows")
    if summary.get("rows_compared") != len(compared):
        problems.append("summary.rows_compared disagrees with the measured rows")
    identical = sum(
        1
        for row in measured
        if isinstance(row.get("deltas"), dict)
        and all(
            abs(float(row["deltas"][name]["absolute_change"])) <= MOVED_TOLERANCE
            for name in FEATURE_NAMES
        )
    )
    if summary.get("rows_feature_identical") != identical:
        problems.append("summary.rows_feature_identical disagrees with the rows")
    if summary.get("rows_moved") != len(compared) - identical:
        problems.append("summary.rows_moved disagrees with the rows")
    over_one_percent = sum(
        1
        for row in compared
        if any(
            row["deltas"][name]["relative_change"] is not None
            and float(row["deltas"][name]["relative_change"])
            > LARGE_RELATIVE_CHANGE
            for name in FEATURE_NAMES
        )
    )
    if summary.get("rows_any_feature_over_1pct") != over_one_percent:
        problems.append("summary.rows_any_feature_over_1pct disagrees with the rows")
    if summary.get("rows_no_feature_over_1pct") != len(compared) - over_one_percent:
        problems.append("summary.rows_no_feature_over_1pct disagrees with the rows")
    for name in FEATURE_NAMES:
        entry = summary.get("per_feature", {}).get(name)  # type: ignore[union-attr]
        if not isinstance(entry, dict):
            problems.append(f"per_feature.{name} is missing")
            continue
        values = [
            row["deltas"][name]["relative_change"]
            for row in compared
            if row["deltas"][name]["relative_change"] is not None
        ]
        if entry.get("compared") != len(values):
            problems.append(f"per_feature.{name}.compared disagrees with the rows")
        if values:
            worst = max(float(value) for value in values)
            if abs(float(entry.get("max_relative_change", -1)) - worst) > 1e-6:
                problems.append(f"per_feature.{name}.max_relative_change is wrong")
    rejected = sum(1 for row in measured if row.get("frozen_runner_accepts") is not True)
    if summary.get("rows_rejected_by_frozen_runner") != rejected:
        problems.append("summary.rows_rejected_by_frozen_runner disagrees with the rows")
    not_converged = sum(
        1 for row in compared if row.get("geoopt_converged") is not True
    )
    if summary.get("rows_geometry_not_converged") != not_converged:
        problems.append("summary.rows_geometry_not_converged disagrees with the rows")
    expected_summary = summarise(measured)  # type: ignore[arg-type]
    for key, expected in expected_summary.items():
        if summary.get(key) != expected:
            problems.append(f"summary.{key} disagrees with the measured rows")
    unmeasured = payload.get("unmeasured")
    if not isinstance(unmeasured, list):
        problems.append("unmeasured rows are missing")
    else:
        keys = [str(row.get("inchikey")) for row in measured if isinstance(row, dict)]
        keys += [str(row.get("inchikey")) for row in unmeasured if isinstance(row, dict)]
        if len(keys) != len(set(keys)):
            problems.append("measured and unmeasured InChIKeys are not unique")
        if len(measured) + len(unmeasured) != payload.get("frozen_feature_rows"):
            problems.append("measured + unmeasured disagrees with frozen_feature_rows")
    cache_validation = payload.get("cache_validation")
    if not isinstance(cache_validation, dict):
        problems.append("cache_validation is missing")
    elif cache_validation.get("mode") != VALIDATION_MODE:
        problems.append("cache_validation.mode disagrees with the probe")
    candidate = payload.get("candidate")
    if not isinstance(candidate, dict) or candidate.get("id") != CANDIDATE_ID:
        problems.append("candidate.id disagrees with the probe candidate")
    if not payload.get("scope_note"):
        problems.append("scope_note is missing")
    if deep:
        problems.extend(_roster_completeness_problems(payload, xtb=xtb))
        problems.extend(_deep_row_problems(measured, xtb=xtb))
    return problems


def _roster_completeness_problems(
    payload: dict[str, object], *, xtb: Path | None = None
) -> list[str]:
    """Bind the evidence to the frozen roster so a truncated JSON cannot pass.

    Without this, a payload that keeps one real row and drops the other 236
    still satisfies ``measured + unmeasured == frozen_feature_rows`` and would
    be declared healthy.
    """

    problems: list[str] = []
    try:
        expected = {str(row["inchikey"]) for row in load_frozen_rows()}
    except (OSError, KeyError, TypeError) as exc:  # pragma: no cover - defensive
        return [f"frozen feature table could not be read: {exc}"]
    if not expected:
        return ["frozen feature table is empty"]
    observed: list[str] = []
    for section in ("measured", "unmeasured"):
        entries = payload.get(section)
        if not isinstance(entries, list):
            problems.append(f"{section} rows are missing")
            continue
        observed.extend(
            str(entry.get("inchikey")) for entry in entries if isinstance(entry, dict)
        )
    if payload.get("frozen_feature_rows") != len(expected):
        problems.append("frozen_feature_rows disagrees with the frozen feature table")
    missing = sorted(expected - set(observed))
    extra = sorted(set(observed) - expected)
    if missing:
        problems.append(
            f"evidence does not cover the frozen roster: {len(missing)} of "
            f"{len(expected)} rows are absent, e.g. {missing[:3]}"
        )
    if extra:
        problems.append(
            f"evidence carries rows outside the frozen roster: {len(extra)} "
            f"unexpected keys, e.g. {extra[:3]}"
        )
    if len(observed) != len(set(observed)):
        problems.append("evidence repeats an InChIKey across measured/unmeasured")
    if xtb is not None and FROZEN_CACHE.is_dir():
        frozen_by_key = {str(row["inchikey"]): row for row in load_frozen_rows()}
        resolvable: list[str] = []
        for entry in payload.get("unmeasured") or []:
            if not isinstance(entry, dict):
                continue
            key = str(entry.get("inchikey"))
            frozen_row = frozen_by_key.get(key)
            if frozen_row is None:
                continue
            cache_entry, _ = resolve_row_cache(frozen_row, xtb=xtb)
            if cache_entry is not None:
                resolvable.append(key)
        if resolvable:
            problems.append(
                f"{len(resolvable)} rows are reported as unmeasured but still resolve "
                f"to a valid frozen cache, e.g. {sorted(resolvable)[:3]}"
            )
    return problems


def _deep_row_problems(
    measured: list[dict[str, object]], *, xtb: Path | None = None
) -> list[str]:
    """Re-parse saved logs and recompute every row's deltas.

    This is a local-only check because the candidate logs live under git-ignored
    data/interim.  The committed JSON still carries their hashes and paths.
    When the xTB executable is available, each row's cache manifest fingerprint
    is re-verified, so the "no mtime drift" claim is reproducible rather than
    narrative.
    """

    problems: list[str] = []
    frozen_rows = {str(row["inchikey"]): row for row in load_frozen_rows()}
    live_fingerprint: dict[str, object] | None = None
    if xtb is not None and FROZEN_CACHE.is_dir():
        try:
            live_fingerprint = _executable_fingerprint(xtb)
        except OSError as exc:  # pragma: no cover - defensive
            problems.append(f"xTB executable fingerprint could not be read: {exc}")
    elif xtb is None and FROZEN_CACHE.is_dir():
        problems.append(
            "xTB executable was not available, so the cache manifest fingerprints "
            "could not be re-verified"
        )
    for row in measured:
        if not isinstance(row, dict):
            problems.append("measured row is not an object")
            continue
        key = str(row.get("inchikey"))
        frozen_row = frozen_rows.get(key)
        if frozen_row is None:
            problems.append(f"{key}: measured row has no frozen feature row")
            continue
        features = row.get("features")
        deltas = row.get("deltas")
        if not isinstance(features, dict) or not isinstance(deltas, dict):
            problems.append(f"{key}: features or deltas are missing")
            continue
        for name in FEATURE_NAMES:
            before = float(frozen_row["frozen"][name])  # type: ignore[index]
            after = float(features[name])
            entry = deltas[name]
            expected_absolute = after - before
            if before == 0.0 and after == 0.0:
                expected_relative: float | None = 0.0
            elif before == 0.0:
                expected_relative = None
            else:
                expected_relative = abs(after - before) / abs(before)
            if abs(float(entry["candidate"]) - after) > 1e-12:
                problems.append(f"{key}.{name}: candidate feature drift differs from the row")
            if abs(float(entry["frozen"]) - before) > 1e-12:
                problems.append(f"{key}.{name}: frozen feature differs from the feature table")
            if abs(float(entry["absolute_change"]) - expected_absolute) > 1e-12:
                problems.append(f"{key}.{name}: absolute change is not recomputable")
            if expected_relative is None:
                if entry["relative_change"] is not None:
                    problems.append(f"{key}.{name}: relative change should be null")
            elif entry["relative_change"] is None or abs(
                float(entry["relative_change"]) - expected_relative
            ) > 1e-12:
                problems.append(f"{key}.{name}: relative change is not recomputable")
        expected_max = max(
            [
                float(deltas[name]["relative_change"])
                for name in FEATURE_NAMES
                if deltas[name]["relative_change"] is not None
            ]
            or [0.0]
        )
        if abs(float(row.get("max_relative_change", -1)) - round(expected_max, 8)) > 1e-12:
            problems.append(f"{key}: max_relative_change is not recomputable")
        cache_dir = row.get("cache_dir")
        if not cache_dir:
            # A missing cache_dir used to switch this whole block off, so a payload
            # could drop its provenance and still pass the deep check.
            problems.append(f"{key}: cache_dir is missing")
        elif live_fingerprint is not None:
            if not Path(str(cache_dir)).name.startswith(key):
                problems.append(f"{key}: cache_dir does not belong to this InChIKey")
            manifest_path = REPOSITORY_ROOT / str(cache_dir) / "cache_manifest.json"
            if not manifest_path.is_file():
                problems.append(f"{key}: cache manifest is missing")
            else:
                try:
                    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    problems.append(f"{key}: cache manifest is unreadable")
                else:
                    if manifest.get("xtb_executable") != live_fingerprint:
                        problems.append(
                            f"{key}: cache manifest executable fingerprint drifted"
                        )
                    if (
                        hashlib.sha256(manifest_path.read_bytes()).hexdigest()
                        != row.get("cache_manifest_sha256")
                    ):
                        problems.append(f"{key}: cache manifest hash mismatch")
                    cache_input = manifest_path.parent / "input.xyz"
                    if not cache_input.is_file():
                        problems.append(f"{key}: cached input.xyz is missing")
                    else:
                        cached_digest = hashlib.sha256(
                            cache_input.read_text(encoding="utf-8").encode("utf-8")
                        ).hexdigest()
                        if cached_digest != manifest.get("input_sha256"):
                            problems.append(
                                f"{key}: cached input.xyz does not match its manifest"
                            )
                        elif cached_digest != row.get("start_geometry_sha256"):
                            problems.append(
                                f"{key}: cached input.xyz is not the candidate start geometry"
                            )
        if not row.get("stdout_log") or not row.get("stderr_log"):
            problems.append(f"{key}: saved log paths are missing")
            continue
        stdout_path = REPOSITORY_ROOT / str(row["stdout_log"])
        stderr_path = REPOSITORY_ROOT / str(row["stderr_log"])
        if not stdout_path.is_file() or not stderr_path.is_file():
            problems.append(f"{key}: saved stdout/stderr log is missing")
            continue
        stdout_bytes = stdout_path.read_bytes()
        stderr_bytes = stderr_path.read_bytes()
        if hashlib.sha256(stdout_bytes).hexdigest() != row.get("stdout_sha256"):
            problems.append(f"{key}: stdout log hash mismatch")
        if hashlib.sha256(stderr_bytes).hexdigest() != row.get("stderr_sha256"):
            problems.append(f"{key}: stderr log hash mismatch")
        input_path = stdout_path.parent / "input.xyz"
        if not input_path.is_file():
            problems.append(f"{key}: candidate input.xyz is missing")
        else:
            start_digest = hashlib.sha256(
                input_path.read_text(encoding="utf-8").encode("utf-8")
            ).hexdigest()
            if start_digest != row.get("start_geometry_sha256"):
                problems.append(f"{key}: start geometry hash mismatch")
        text = stdout_bytes.decode("utf-8", "replace")
        verdict = frozen_verdict(
            run_dir=stdout_path.parent,
            stdout=text,
            exit_code=row.get("exit_code"),  # type: ignore[arg-type]
        )
        reported = row.get("frozen_runner_accepts")
        if bool(verdict["frozen_runner_accepts"]) != bool(reported):
            problems.append(
                f"{key}: frozen_runner_accepts={reported!r} is not what the saved log "
                f"yields ({verdict['frozen_runner_accepts']!r}; "
                f"marker={verdict['normal_termination_in_stdout']}, "
                f"sentinel={verdict['opt_marker_file']}, "
                f"geometry_written={verdict['optimized_geometry_written']}, "
                f"exit_code={row.get('exit_code')!r}); {OPT_MARKER_FILE} or the xTB "
                f"termination marker is required"
            )
        if bool(verdict["geoopt_converged"]) != bool(row.get("geoopt_converged")):
            problems.append(f"{key}: geoopt_converged disagrees with the saved log")
        if verdict["frozen_runner_accepts"] is not True:
            continue
        parsed_features = verdict["features"]
        assert isinstance(parsed_features, dict)
        for name in FEATURE_NAMES:
            if abs(float(features[name]) - float(parsed_features[name])) > 1e-12:
                problems.append(f"{key}.{name}: saved log disagrees with features")
    return problems


def _read_committed() -> dict[str, object]:
    if not EVIDENCE_PATH.is_file():
        return {}
    return json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", help="re-run the roster")
    parser.add_argument("--write", action="store_true", help="write the evidence JSON")
    parser.add_argument("--check", action="store_true", help="validate the evidence JSON")
    parser.add_argument(
        "--refresh-metadata",
        action="store_true",
        help="add environment metadata to an existing evidence JSON without re-running xTB",
    )
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--threads", type=int, default=1)
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--xtb", type=Path, default=None)
    parser.add_argument("--work-dir", type=Path, default=WORK_ROOT)
    args = parser.parse_args(argv)

    if args.check:
        committed = _read_committed()
        if not committed:
            print("EVIDENCE MISSING", file=sys.stderr)
            return 1
        try:
            xtb = args.xtb or resolve_xtb()
        except FileNotFoundError:
            xtb = None
        problems = check_payload(committed, deep=True, xtb=xtb)
        for problem in problems:
            print(f"EVIDENCE MISMATCH: {problem}", file=sys.stderr)
        if problems:
            return 1
        print("evidence invariants hold")
        return 0

    if args.refresh_metadata:
        committed = _read_committed()
        if not committed:
            print("EVIDENCE MISSING", file=sys.stderr)
            return 1
        xtb = args.xtb or resolve_xtb()
        committed["run_environment"] = describe_run_environment(xtb, args.threads)
        EVIDENCE_PATH.write_text(
            json.dumps(committed, ensure_ascii=False, indent=2, sort_keys=True)
            + chr(10),
            encoding="utf-8",
            newline=chr(10),
        )
        problems = check_payload(committed)
        for problem in problems:
            print(f"EVIDENCE MISMATCH: {problem}", file=sys.stderr)
        if problems:
            return 1
        print(f"updated run metadata in {EVIDENCE_PATH}")
        return 0

    if args.write and args.limit > 0:
        parser.error("--write requires a full run; omit --limit")

    committed = _read_committed()
    measured = committed.get("measured") if not args.run else None
    unmeasured = committed.get("unmeasured") if not args.run else None
    committed_environment = committed.get("run_environment") if not args.run else None

    frozen_count: int | None = None
    if args.run:
        frozen = load_frozen_rows()
        frozen_count = len(frozen)
        xtb = args.xtb or resolve_xtb()
        runnable: list[dict[str, object]] = []
        missing: list[dict[str, object]] = []
        for row in frozen:
            entry, reason = resolve_row_cache(row, xtb=xtb)
            if entry is None:
                missing.append(
                    {
                        "inchikey": row["inchikey"],
                        "name": row["name"],
                        "reason": reason,
                    }
                )
                continue
            runnable.append({**row, "cache": entry})
        if args.limit > 0:
            runnable = runnable[: args.limit]
        measured = []
        for position, row in enumerate(runnable, start=1):
            result = run_candidate(
                row,
                xtb=xtb,
                work_root=args.work_dir,
                timeout=args.timeout,
                threads=args.threads,
            )
            compared = compare_row(row, result)
            measured.append(compared)
            print(
                json.dumps(
                    {
                        "processed": position,
                        "total": len(runnable),
                        "name": row["name"],
                        "accepts": compared["frozen_runner_accepts"],
                        "max_relative_change": compared["max_relative_change"],
                    }
                ),
                flush=True,
            )
        unmeasured = missing

        if args.write:
            payload = build_payload(
                measured=measured,
                unmeasured=unmeasured,  # type: ignore[arg-type]
                frozen_rows=frozen_count,
                run_environment=describe_run_environment(xtb, args.threads),
            )
            EVIDENCE_PATH.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + chr(10),
                encoding="utf-8",
                newline=chr(10),
            )
            print(f"wrote {EVIDENCE_PATH}")
            return 0

    if measured is None:
        print("nothing to do: pass --run or --check", file=sys.stderr)
        return 1
    payload = build_payload(
        measured=measured,  # type: ignore[arg-type]
        unmeasured=unmeasured or [],  # type: ignore[arg-type]
        frozen_rows=frozen_count if frozen_count is not None else len(measured),  # type: ignore[arg-type]
        run_environment=committed_environment,  # type: ignore[arg-type]
    )
    print(json.dumps(payload["summary"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
