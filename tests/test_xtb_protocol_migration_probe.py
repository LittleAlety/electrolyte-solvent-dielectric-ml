"""Regression tests for the whole-roster protocol-migration probe."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from probes.xtb_protocol_migration_probe import (
    EVIDENCE_PATH,
    FEATURE_NAMES,
    FROZEN_CACHE,
    VALIDATION_MODE,
    _deep_row_problems,
    _features_agree,
    build_payload,
    check_payload,
    load_frozen_rows,
    resolve_row_cache,
    resolve_xtb,
    summarise,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DATASET = REPOSITORY_ROOT / "data" / "dielectric_v03.csv"
# Both of these are git-ignored, so a fresh checkout (and CI) has neither:
# the candidate run logs and the frozen cache live under data/interim.
CANDIDATE_RUN_ROOT = REPOSITORY_ROOT / "data" / "interim" / "xtb_protocol_migration"

try:
    LOCAL_XTB: Path | None = resolve_xtb()
except FileNotFoundError:
    LOCAL_XTB = None


def _cache_index(cache_root: Path = FROZEN_CACHE) -> dict[str, list[dict[str, object]]]:
    """Local test helper: map an InChIKey to its cached run directories."""

    index: dict[str, list[dict[str, object]]] = {}
    if not cache_root.is_dir():
        return index
    for run_dir in sorted(cache_root.iterdir()):
        if not run_dir.is_dir():
            continue
        manifest_path = run_dir / "cache_manifest.json"
        if not manifest_path.is_file():
            continue
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        key = run_dir.name.split("__", 1)[0]
        input_xyz = run_dir / "input.xyz"
        input_sha256 = (
            hashlib.sha256(
                input_xyz.read_text(encoding="utf-8").encode("utf-8")
            ).hexdigest()
            if input_xyz.is_file()
            else None
        )
        index.setdefault(key, []).append(
            {
                "run_dir": run_dir,
                "input_xyz": input_xyz,
                "input_sha256_matches": (
                    input_sha256 is not None
                    and input_sha256 == manifest.get("input_sha256")
                ),
            }
        )
    return index


def _pick_cache_entry(
    entry_list: list[dict[str, object]],
) -> dict[str, object] | None:
    """Local test helper: the first entry whose starting geometry is intact."""

    for entry in entry_list:
        xyz = entry["input_xyz"]
        if (
            isinstance(xyz, Path)
            and xyz.is_file()
            and entry.get("input_sha256_matches") is True
        ):
            return entry
    return None


def _row(
    key: str,
    *,
    absolute_change: float,
    relative_change: float,
    accepts: bool = True,
    converged: bool = True,
) -> dict[str, object]:
    return {
        "inchikey": key,
        "name": key,
        "frozen_runner_accepts": accepts,
        "geoopt_converged": converged,
        "deltas": {
            name: {
                "absolute_change": absolute_change,
                "relative_change": relative_change,
            }
            for name in FEATURE_NAMES
        },
    }


def _payload() -> dict[str, object]:
    return build_payload(
        measured=[
            _row("STABLE", absolute_change=0.0, relative_change=0.0),
            _row("MOVED", absolute_change=0.02, relative_change=0.02),
        ],
        unmeasured=[],
        frozen_rows=2,
        run_environment={
            "xtb_executable": "xtb",
            "xtb_executable_sha256": "0" * 64,
            "xtb_version_line": "xtb version test",
            "threads": 4,
            "geometry_source": "cache_manifest_matching_input_xyz",
            "geometry_seed_used_during_migration": None,
        },
    )


def test_synthetic_payload_satisfies_its_own_invariants() -> None:
    assert check_payload(_payload()) == []


def test_material_movement_is_not_reduced_to_float_noise() -> None:
    summary = summarise(
        [
            _row("STABLE", absolute_change=0.0, relative_change=0.0),
            _row("NOISE", absolute_change=1e-8, relative_change=1e-8),
            _row("MOVED", absolute_change=0.02, relative_change=0.02),
        ]
    )
    assert summary["rows_moved"] == 2
    assert summary["rows_feature_identical"] == 1
    assert summary["rows_any_feature_over_1pct"] == 1
    assert summary["rows_no_feature_over_1pct"] == 2
    assert summary["rows_moved"] + summary["rows_feature_identical"] == 3


def test_check_payload_rejects_missing_run_environment() -> None:
    payload = copy.deepcopy(_payload())
    payload.pop("run_environment")
    assert any("run_environment" in problem for problem in check_payload(payload))


def test_check_payload_rejects_a_tampered_attempt_count() -> None:
    payload = copy.deepcopy(_payload())
    payload["summary"]["rows_attempted"] += 1
    assert any("rows_attempted" in problem for problem in check_payload(payload))


def test_check_payload_rejects_a_tampered_compare_count() -> None:
    payload = copy.deepcopy(_payload())
    payload["summary"]["rows_compared"] += 1
    assert any("rows_compared" in problem for problem in check_payload(payload))


def test_check_payload_rejects_a_tampered_material_count() -> None:
    payload = copy.deepcopy(_payload())
    payload["summary"]["rows_any_feature_over_1pct"] = 0
    assert check_payload(payload)


def test_cache_pairing_uses_the_runner_text_hash_not_raw_crlf_bytes(tmp_path: Path) -> None:
    key = "AAAAAAAAAAAAAA-BBBBBBBBBB-C"
    run = tmp_path / key
    run.mkdir()
    text = "3\nwater\nO 0.0 0.0 0.0\nH 0.0 0.0 0.96\nH 0.93 0.0 -0.24\n"
    (run / "input.xyz").write_bytes(text.replace("\n", "\r\n").encode("utf-8"))
    (run / "cache_manifest.json").write_text(
        json.dumps({"input_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()}),
        encoding="utf-8",
    )

    entry = _pick_cache_entry(_cache_index(tmp_path)[key])
    assert entry is not None
    assert entry["input_sha256_matches"] is True


def test_cache_pairing_rejects_changed_start_geometry(tmp_path: Path) -> None:
    key = "AAAAAAAAAAAAAA-BBBBBBBBBB-C"
    run = tmp_path / key
    run.mkdir()
    text = "3\nwater\nO 0.0 0.0 0.0\nH 0.0 0.0 0.96\nH 0.93 0.0 -0.24\n"
    (run / "input.xyz").write_text(text, encoding="utf-8")
    (run / "cache_manifest.json").write_text(
        json.dumps({"input_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()}),
        encoding="utf-8",
    )
    (run / "input.xyz").write_text(text.replace("0.96", "0.97"), encoding="utf-8")

    assert _pick_cache_entry(_cache_index(tmp_path)[key]) is None


@pytest.mark.skipif(
    not FROZEN_CACHE.is_dir() or LOCAL_XTB is None,
    reason="the git-ignored local xTB cache or executable is unavailable",
)
def test_full_roster_resolves_to_exactly_one_frozen_valid_cache() -> None:
    """The authoritative gate: every frozen row pairs with one *validated* cache."""

    assert LOCAL_XTB is not None
    rows = load_frozen_rows()
    unresolved = [
        (row["inchikey"], reason)
        for row, (entry, reason) in (
            (row, resolve_row_cache(row, xtb=LOCAL_XTB)) for row in rows
        )
        if entry is None
    ]
    assert len(rows) == 237
    assert unresolved == []


@pytest.mark.skipif(not EVIDENCE_PATH.is_file(), reason="probe evidence is not built")
def test_committed_evidence_satisfies_its_own_invariants() -> None:
    payload = json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))
    assert check_payload(payload) == []


def test_the_frozen_dataset_digest_is_still_pinned() -> None:
    digest = hashlib.sha256(DATASET.read_bytes()).hexdigest()
    assert digest == (
        "ff2142936e06e04b329b70f8597574f75349e54ce876e9fff81309e6d35ccce4"
    )


class _Parsed:
    """Stand-in for XtbParsed in cache-resolution tests."""

    total_energy_hartree = 1.0
    homo_lumo_gap_ev = 1.0
    dipole_debye = 1.0
    polarizability_au = 1.0


def _fake_cache(tmp_path: Path, dirname: str, *, seed: int = 42) -> Path:
    run = tmp_path / dirname
    run.mkdir(parents=True)
    (run / "input.xyz").write_text("1\nH\nH 0.0 0.0 0.0\n", encoding="utf-8")
    (run / "cache_manifest.json").write_text(
        json.dumps({"seed": seed, "input_sha256": "irrelevant"}),
        encoding="utf-8",
    )
    return run


def _fake_row(key: str) -> dict[str, object]:
    return {
        "inchikey": key,
        "name": key,
        "smiles": "C",
        "formal_charge": 0,
        "frozen": {name: 1.0 for name in FEATURE_NAMES},
    }


def _accept_all(*args: object, **kwargs: object) -> tuple[Path, Path, str]:
    return Path("xtb.out"), Path("xtbopt.xyz"), "cached output"


def _stub_parse(text: str) -> _Parsed:
    return _Parsed()


def test_features_agree_uses_the_feature_table_store_precision() -> None:
    """Eight-significant-digit rounding must not read as a cache mismatch."""

    frozen = {
        "total_energy_hartree": -22.4790633061,
        "homo_lumo_gap_ev": 3.7492,
        "dipole_debye": 1.9,
        "polarizability_au": 162.3657,
    }
    parsed = {
        "total_energy_hartree": -22.47906330614,
        "homo_lumo_gap_ev": 3.749200001,
        "dipole_debye": 1.9000000004,
        "polarizability_au": 162.365698,
    }
    assert _features_agree(parsed, frozen) is True
    parsed["polarizability_au"] = 162.4
    assert _features_agree(parsed, frozen) is False


def test_zero_baseline_move_is_absolute_only() -> None:
    row = {
        "inchikey": "ZERO",
        "name": "ZERO",
        "frozen_runner_accepts": True,
        "geoopt_converged": True,
        "deltas": {
            name: {
                "frozen": 0.0,
                "candidate": 0.5,
                "absolute_change": 0.5,
                "relative_change": None,
            }
            for name in FEATURE_NAMES
        },
    }
    summary = summarise([row])
    assert summary["rows_moved"] == 1
    assert summary["rows_feature_identical"] == 0
    assert summary["rows_any_feature_over_1pct"] == 0
    assert summary["rows_with_undefined_relative_change"] == 1
    for name in FEATURE_NAMES:
        entry = summary["per_feature"][name]
        assert entry["moved"] == 1
        assert entry["zero_baseline_moves"] == 1
        assert entry["moved_over_1pct"] == 0
        assert entry["compared"] == 0


def test_check_payload_reports_malformed_payloads_instead_of_raising() -> None:
    assert check_payload(None) == ["payload is not an object"]
    broken = copy.deepcopy(_payload())
    broken["summary"] = {"rows_attempted": "many"}
    assert check_payload(broken)
    nested = copy.deepcopy(_payload())
    nested["measured"] = [{"deltas": {"dipole_debye": None}}]
    assert check_payload(nested)
    deep = copy.deepcopy(_payload())
    deep["measured"] = [{"inchikey": "X", "deltas": 5, "features": "no"}]
    assert check_payload(deep, deep=True)


def test_resolve_row_cache_accepts_a_single_validated_entry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import probes.xtb_protocol_migration_probe as probe

    key = "AAAAAAAAAAAAAA-BBBBBBBBBB-C"
    _fake_cache(tmp_path, key)
    monkeypatch.setattr(probe, "generate_3d_xyz", lambda smiles, seed: "input")
    monkeypatch.setattr(probe, "_valid_cache", _accept_all)
    monkeypatch.setattr(probe, "parse_xtb_output", _stub_parse)

    entry, reason = resolve_row_cache(_fake_row(key), xtb=Path("xtb"), cache_root=tmp_path)

    assert reason == ""
    assert entry is not None
    assert entry["validation_mode"] == VALIDATION_MODE


def test_resolve_row_cache_uses_the_manifest_seed_not_a_fixed_seed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import probes.xtb_protocol_migration_probe as probe

    key = "AAAAAAAAAAAAAA-BBBBBBBBBB-C"
    _fake_cache(tmp_path, key, seed=57)
    seen: list[int] = []

    def _record(smiles: str, seed: int) -> str:
        seen.append(seed)
        return "input"

    monkeypatch.setattr(probe, "generate_3d_xyz", _record)
    monkeypatch.setattr(probe, "_valid_cache", _accept_all)
    monkeypatch.setattr(probe, "parse_xtb_output", _stub_parse)

    entry, _ = resolve_row_cache(_fake_row(key), xtb=Path("xtb"), cache_root=tmp_path)

    assert seen == [57]
    assert entry is not None


def test_resolve_row_cache_rejects_ambiguous_duplicate_directories(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import probes.xtb_protocol_migration_probe as probe

    key = "AAAAAAAAAAAAAA-BBBBBBBBBB-C"
    _fake_cache(tmp_path, key)
    _fake_cache(tmp_path, key + "__legacy")
    monkeypatch.setattr(probe, "generate_3d_xyz", lambda smiles, seed: "input")
    monkeypatch.setattr(probe, "_valid_cache", _accept_all)
    monkeypatch.setattr(probe, "parse_xtb_output", _stub_parse)

    entry, reason = resolve_row_cache(_fake_row(key), xtb=Path("xtb"), cache_root=tmp_path)

    assert entry is None
    assert "ambiguous" in reason


def test_resolve_row_cache_reports_when_no_entry_is_accepted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import probes.xtb_protocol_migration_probe as probe

    key = "AAAAAAAAAAAAAA-BBBBBBBBBB-C"
    _fake_cache(tmp_path, key)
    monkeypatch.setattr(probe, "generate_3d_xyz", lambda smiles, seed: "input")
    monkeypatch.setattr(probe, "_valid_cache", lambda *args, **kwargs: None)

    entry, reason = resolve_row_cache(_fake_row(key), xtb=Path("xtb"), cache_root=tmp_path)

    assert entry is None
    assert "no cache entry accepted" in reason


def test_resolve_row_cache_skips_a_malformed_manifest(tmp_path: Path) -> None:
    key = "AAAAAAAAAAAAAA-BBBBBBBBBB-C"
    run = tmp_path / key
    run.mkdir()
    (run / "cache_manifest.json").write_text("{ not json", encoding="utf-8")

    entry, reason = resolve_row_cache(_fake_row(key), xtb=Path("xtb"), cache_root=tmp_path)

    assert entry is None
    assert "no cache entry accepted" in reason


def test_deep_check_reports_a_corrupted_saved_log(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import probes.xtb_protocol_migration_probe as probe

    monkeypatch.setattr(probe, "REPOSITORY_ROOT", tmp_path)
    monkeypatch.setattr(
        probe,
        "load_frozen_rows",
        lambda *args, **kwargs: [
            {"inchikey": "K", "frozen": dict.fromkeys(FEATURE_NAMES, 1.0)}
        ],
    )
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "out.log").write_bytes(b"not an xtb output")
    (logs / "err.log").write_bytes(b"")
    row = {
        "inchikey": "K",
        "features": dict.fromkeys(FEATURE_NAMES, 1.0),
        "deltas": {
            name: {
                "frozen": 1.0,
                "candidate": 1.0,
                "absolute_change": 0.0,
                "relative_change": 0.0,
            }
            for name in FEATURE_NAMES
        },
        "max_relative_change": 0.0,
        "frozen_runner_accepts": True,
        "stdout_log": "logs/out.log",
        "stderr_log": "logs/err.log",
        "stdout_sha256": "0" * 64,
        "stderr_sha256": hashlib.sha256(b"").hexdigest(),
    }

    problems = _deep_row_problems([row])

    assert any("stdout log hash mismatch" in problem for problem in problems)
    assert any(
        "termination marker" in problem or "cannot be re-parsed" in problem
        for problem in problems
    ), problems


def test_the_feasibility_report_quotes_the_evidence_exactly() -> None:
    """Narrative numbers must not drift away from the evidence JSON.

    The first full run's prose was quoted from a superseded run and ended up
    claiming a 311.94% dipole move where the surviving evidence says 304.73%.
    This guard re-derives every headline number the report quotes.
    """

    report_path = REPOSITORY_ROOT / "reports" / "g1plus_xtb_protocol_migration_feasibility.md"
    if not report_path.is_file() or not EVIDENCE_PATH.is_file():
        pytest.skip("report or probe evidence is not built")
    report = report_path.read_text(encoding="utf-8")
    payload = json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))
    summary = payload["summary"]

    assert f"{summary['rows_any_feature_over_1pct']}/237" in report
    assert f"{summary['rows_no_feature_over_1pct']}/237" in report
    for name, entry in summary["per_feature"].items():
        assert f"{entry['moved_over_1pct']}/237" in report, name
        assert entry["max_mover_name"] in report, name

    rows = [row for row in payload["measured"] if isinstance(row.get("deltas"), dict)]
    rows.sort(key=lambda row: row["max_relative_change"], reverse=True)
    for row in rows[:10]:
        assert f"{row['max_relative_change'] * 100:.2f}%" in report, row["name"]
        for delta in row["deltas"].values():
            if delta["relative_change"] is not None:
                cell = f"{delta['relative_change'] * 100:.2f}%"
                assert cell in report, (row["name"], cell)


def test_deep_check_rejects_a_truncated_evidence_payload() -> None:
    """Critical: keeping only some rows must not pass the deep gate."""

    if not EVIDENCE_PATH.is_file():
        pytest.skip("probe evidence is not built")
    full = json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))
    payload = build_payload(
        measured=full["measured"][:1],
        unmeasured=[],
        frozen_rows=1,
        run_environment=full["run_environment"],
    )
    for key in ("cache_validation",):
        payload[key] = full[key]

    problems = check_payload(payload, deep=True)

    assert any("frozen roster" in problem for problem in problems), problems


@pytest.mark.skipif(
    not FROZEN_CACHE.is_dir() or LOCAL_XTB is None,
    reason="the git-ignored frozen xTB cache or executable is unavailable",
)
def test_deep_check_rejects_rows_relabelled_as_unmeasured() -> None:
    """Critical: relabelling resolvable rows as unmeasured must not pass."""

    if not EVIDENCE_PATH.is_file():
        pytest.skip("probe evidence is not built")
    full = json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))
    relabelled = [
        {"inchikey": row["inchikey"], "name": row["name"], "reason": "fabricated"}
        for row in full["measured"]
    ]
    payload = build_payload(
        measured=[],
        unmeasured=relabelled,
        frozen_rows=len(full["measured"]),
        run_environment=full["run_environment"],
    )
    payload["cache_validation"] = full["cache_validation"]

    problems = check_payload(payload, deep=True, xtb=LOCAL_XTB)

    assert any("reported as unmeasured" in problem for problem in problems), problems


@pytest.mark.skipif(
    not CANDIDATE_RUN_ROOT.is_dir(),
    reason="the git-ignored candidate run logs are unavailable",
)
def test_deep_check_rejects_a_flipped_self_reported_verdict() -> None:
    """Critical: a self-reported False must not disable the log re-verification."""

    if not EVIDENCE_PATH.is_file():
        pytest.skip("probe evidence is not built")
    full = json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))
    measured = copy.deepcopy(full["measured"])
    measured[0]["frozen_runner_accepts"] = False
    payload = build_payload(
        measured=measured,
        unmeasured=[],
        frozen_rows=full["frozen_feature_rows"],
        run_environment=full["run_environment"],
    )
    payload["cache_validation"] = full["cache_validation"]

    problems = check_payload(payload, deep=True, xtb=LOCAL_XTB)

    assert any("frozen_runner_accepts" in problem for problem in problems), problems

def test_deep_check_requires_a_cache_dir_on_every_measured_row() -> None:
    """Important: dropping cache_dir must not switch the provenance audit off.

    The cache-provenance block used to be guarded by ``row.get("cache_dir")``, so
    a payload with no cache_dir skipped the manifest fingerprint, the manifest
    SHA and the cached input.xyz checks in silence.
    """

    if not EVIDENCE_PATH.is_file():
        pytest.skip("probe evidence is not built")
    full = json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))
    measured = copy.deepcopy(full["measured"])
    for row in measured:
        row.pop("cache_dir", None)
    payload = build_payload(
        measured=measured,
        unmeasured=[],
        frozen_rows=full["frozen_feature_rows"],
        run_environment=full["run_environment"],
    )
    payload["cache_validation"] = full["cache_validation"]

    problems = check_payload(payload, deep=True, xtb=LOCAL_XTB)

    assert any("cache_dir is missing" in problem for problem in problems), problems


@pytest.mark.skipif(
    not FROZEN_CACHE.is_dir() or LOCAL_XTB is None,
    reason="the git-ignored local xTB cache or executable is unavailable",
)
def test_deep_check_binds_each_recorded_cache_dir_to_its_own_row() -> None:
    """Important: borrowing another molecule's valid cache must not pass."""

    if not EVIDENCE_PATH.is_file():
        pytest.skip("probe evidence is not built")
    full = json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))
    measured = copy.deepcopy(full["measured"])
    first, second = measured[0], measured[1]
    first["cache_dir"] = second["cache_dir"]
    first["cache_manifest_sha256"] = second["cache_manifest_sha256"]
    payload = build_payload(
        measured=measured,
        unmeasured=[],
        frozen_rows=full["frozen_feature_rows"],
        run_environment=full["run_environment"],
    )
    payload["cache_validation"] = full["cache_validation"]

    problems = check_payload(payload, deep=True, xtb=LOCAL_XTB)

    assert any("does not belong to this InChIKey" in problem for problem in problems), problems
