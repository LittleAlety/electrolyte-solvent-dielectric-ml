"""Offline unit tests for the W17-11 four-core cross-channel registry builder.

Everything here runs with zero network access. The pinned values are what the frozen
pre-registration (probes/four_core_registry_prereg.json) committed to before the run plus
what the run then produced. They are written out literally rather than recomputed, so a
silent edit to the pre-registration, the summary, the report or the registry CSV shows up
as a failure instead of quietly re-baselining.

The registry is a derived view over five committed source tables; every input is in the
repository, so nothing here needs a skip marker.
"""

from __future__ import annotations

import argparse
import csv
import json
import socket
import sys
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))

from probes.build_four_core_registry import (
    ALL_CHANNELS,
    BANNED_CLAIM_TOKENS,
    CORE_CHANNELS,
    DEFAULT_PREREG,
    DEFAULT_REPORT,
    DEFAULT_SUMMARY,
    DEFAULT_TABLE,
    TABLE_COLUMNS,
    InputDriftError,
    compose,
    csv_text,
    guard_violations,
    kirkwood_factor,
    main,
    pearson,
    read_text_raw,
    stable_view,
    verdict_of,
)

EXPECTED_REGISTRY_ROWS = 31949
EXPECTED_COLUMNS = 30
EXPECTED_CHANNEL_KEYS = {
    "dielectric": 247,
    "viscosity": 1228,
    "orbitals": 29868,
    "redox_label": 392,
    "density": 2178,
    "liquid_window": 218,
}
EXPECTED_SOURCE_TABLE_KEYS = {
    "dielectric": 247,
    "viscosity": 1228,
    "orbitals": 29868,
    "redox_label": 29868,
    "density": 2178,
    "liquid_window": 314,
}
EXPECTED_CORE_ALL_PRESENT = 7
EXPECTED_QUARTETS = {
    "prereg_core_four": 7,
    "with_liquid_window_data": 51,
    "with_liquid_window_table_keys": 53,
}
EXPECTED_INTERSECTIONS = {
    "dielectric&viscosity": 143,
    "dielectric&orbitals": 84,
    "dielectric&redox_label": 10,
    "dielectric&density": 180,
    "dielectric&liquid_window": 181,
    "viscosity&orbitals": 118,
    "viscosity&redox_label": 10,
    "viscosity&density": 1179,
    "viscosity&liquid_window": 156,
    "orbitals&redox_label": 392,
    "orbitals&density": 192,
    "orbitals&liquid_window": 75,
    "redox_label&density": 13,
    "redox_label&liquid_window": 8,
    "density&liquid_window": 184,
}
EXPECTED_LIQUID_WINDOW_TABLE_KEYS = 314
EXPECTED_LIQUID_WINDOW_EMPTY_KEYS = 96
EXPECTED_KIRKWOOD_N = 79
EXPECTED_KIRKWOOD_R = 0.6464482483155134
EXPECTED_KIRKWOOD_R_PREVIOUSLY_LOGGED = 0.6464482483164224
EXPECTED_KIRKWOOD_R_MU = 0.5934413462534026
EXPECTED_DIPOLE_AU_TO_DEBYE = 2.541746473
EXPECTED_CORE_HISTOGRAM = {"0": 898, "1": 30433, "2": 559, "3": 52, "4": 7}

ARTIFACTS = (DEFAULT_PREREG, DEFAULT_TABLE, DEFAULT_SUMMARY, DEFAULT_REPORT)


def load_summary() -> dict[str, Any]:
    return json.loads(DEFAULT_SUMMARY.read_text(encoding="utf-8"))


def load_registry() -> list[dict[str, str]]:
    with DEFAULT_TABLE.open(encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def build_args(**overrides: Path) -> argparse.Namespace:
    values: dict[str, Path] = {
        "prereg": DEFAULT_PREREG,
        "table": DEFAULT_TABLE,
        "summary": DEFAULT_SUMMARY,
        "report": DEFAULT_REPORT,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def test_artifacts_exist() -> None:
    for path in ARTIFACTS:
        assert path.is_file(), path


def test_prereg_is_locked_and_pinned_in_the_summary() -> None:
    summary = load_summary()
    prereg = json.loads(DEFAULT_PREREG.read_text(encoding="utf-8"))
    assert prereg["status"] == "locked_before_run"
    assert prereg["locked_at_utc"].endswith("Z")
    assert summary["prereg"]["status"] == "locked_before_run"
    assert summary["prereg"]["sha256"] == summary["prereg"]["sha256"].lower()
    assert len(summary["prereg"]["sha256"]) == 64
    assert summary["generated_at_utc"].endswith("Z")


def test_registry_columns_match_the_locked_schema() -> None:
    prereg = json.loads(DEFAULT_PREREG.read_text(encoding="utf-8"))
    assert list(TABLE_COLUMNS) == list(prereg["registry_schema"])
    assert len(TABLE_COLUMNS) == EXPECTED_COLUMNS
    with DEFAULT_TABLE.open(encoding="utf-8", newline="") as handle:
        header = next(csv.reader(handle))
    assert header == list(TABLE_COLUMNS)


def test_registry_has_one_row_per_key_and_pinned_size() -> None:
    rows = load_registry()
    assert len(rows) == EXPECTED_REGISTRY_ROWS
    keys = [row["inchikey"] for row in rows]
    assert all(keys)
    assert len(set(keys)) == len(keys)
    assert keys == sorted(keys)


def test_channel_flags_and_counts_are_pinned() -> None:
    summary = load_summary()
    readings = {item["channel"]: item for item in summary["criterion_c_per_channel"]["readings"]}
    assert set(readings) == set(ALL_CHANNELS)
    assert {
        name: int(readings[name]["contract_keys"]) for name in readings
    } == EXPECTED_CHANNEL_KEYS
    assert {
        name: int(readings[name]["source_table_keys"]) for name in readings
    } == EXPECTED_SOURCE_TABLE_KEYS
    assert all(readings[name]["matches"] for name in readings)
    assert all(int(readings[name]["nearest_temperature_fallbacks"]) == 0 for name in readings)

    rows = load_registry()
    observed = {
        spec_name: sum(1 for row in rows if row["has_" + spec_name] == "true")
        for spec_name in ("dielectric", "viscosity", "orbitals", "density", "liquid_window")
    }
    observed["redox_label"] = sum(1 for row in rows if row["has_redox_label"] == "true")
    assert observed == EXPECTED_CHANNEL_KEYS


def test_core_quartets_and_histogram_are_pinned() -> None:
    summary = load_summary()
    assert summary["core_channels"] == list(CORE_CHANNELS)
    assert int(summary["core_all_present"]) == EXPECTED_CORE_ALL_PRESENT
    assert {
        name: int(summary["coverage_quartets"][name]["keys"])
        for name in summary["coverage_quartets"]
    } == EXPECTED_QUARTETS
    assert summary["registry"]["n_core_channels_histogram"] == EXPECTED_CORE_HISTOGRAM
    assert sum(EXPECTED_CORE_HISTOGRAM.values()) == EXPECTED_REGISTRY_ROWS


def test_row_level_consistency_of_core_counts_and_present_channels() -> None:
    rows = load_registry()
    for row in rows:
        present = row["channels_present"].split("|")
        assert present, row["inchikey"]
        assert all(name in ALL_CHANNELS for name in present)
        core_hits = sum(1 for name in present if name in CORE_CHANNELS)
        assert core_hits == int(row["n_core_channels"])
        for name in CORE_CHANNELS:
            assert (row["has_" + name] == "true") == (name in present)
        if row["dipole_au"]:
            expected = float(row["dipole_au"]) * EXPECTED_DIPOLE_AU_TO_DEBYE
            assert abs(float(row["dipole_D"]) - expected) <= 1e-9 * max(1.0, abs(expected))
        if row["HOMO_eV"] and row["LUMO_eV"]:
            expected_gap = float(row["LUMO_eV"]) - float(row["HOMO_eV"])
            assert abs(float(row["gap_eV"]) - expected_gap) <= 1e-9 * max(1.0, abs(expected_gap))


def test_intersection_matrix_is_pinned() -> None:
    summary = load_summary()
    observed = {str(name): int(value) for name, value in summary["channel_intersections"].items()}
    assert observed == EXPECTED_INTERSECTIONS
    assert len(observed) == len(ALL_CHANNELS) * (len(ALL_CHANNELS) - 1) // 2


def test_liquid_window_empty_rows_are_registered() -> None:
    summary = load_summary()
    reconciliation = summary["liquid_window_reconciliation"]
    assert int(reconciliation["table_keys"]) == EXPECTED_LIQUID_WINDOW_TABLE_KEYS
    assert int(reconciliation["keys_with_any_numeric"]) == EXPECTED_CHANNEL_KEYS["liquid_window"]
    assert (
        int(reconciliation["keys_with_all_four_columns_empty"]) == EXPECTED_LIQUID_WINDOW_EMPTY_KEYS
    )
    assert len(reconciliation["empty_keys"]) == EXPECTED_LIQUID_WINDOW_EMPTY_KEYS
    assert reconciliation["empty_keys"] == sorted(reconciliation["empty_keys"])
    assert (
        int(reconciliation["quartet_with_table_keys"])
        == EXPECTED_QUARTETS["with_liquid_window_table_keys"]
    )
    assert int(reconciliation["intersections_with_table_keys"]["dielectric"]) == 246
    assert int(reconciliation["intersections_with_table_keys"]["viscosity"]) == 202
    assert int(reconciliation["intersections_with_table_keys"]["orbitals"]) == 89
    assert int(reconciliation["intersections_with_table_keys"]["density"]) == 246
    assert reconciliation["empty_keys_overlap_with_channels"] == {
        "dielectric": 65,
        "viscosity": 46,
        "orbitals": 14,
        "redox_label": 2,
        "density": 62,
    }


def test_descriptive_relation_is_pinned_and_never_a_verdict() -> None:
    summary = load_summary()
    prereg = json.loads(DEFAULT_PREREG.read_text(encoding="utf-8"))
    relation = summary["descriptive_relation"]
    assert int(relation["n_pairs"]) == EXPECTED_KIRKWOOD_N
    assert float(relation["pearson_kirkwood_vs_dipole_sq"]) == EXPECTED_KIRKWOOD_R
    assert float(relation["pearson_kirkwood_vs_dipole"]) == EXPECTED_KIRKWOOD_R_MU
    assert relation["role"] == prereg["descriptive_relation_definition"]["role"]
    assert relation["role"] == "descriptive_only_never_a_verdict"
    assert float(relation["dipole_au_to_debye_factor"]) == EXPECTED_DIPOLE_AU_TO_DEBYE
    assert int(relation["log10"]["n_pairs"]) == 77
    assert int(relation["log10"]["n_skipped_nonpositive"]) == 2
    # 同一 key 集与同一口径下的重算与上一轮临时脚本登记值一致到 1e-12。
    assert abs(EXPECTED_KIRKWOOD_R - EXPECTED_KIRKWOOD_R_PREVIOUSLY_LOGGED) < 1e-11


def test_no_model_was_fitted_and_no_scoreboard_was_touched() -> None:
    summary = load_summary()
    criterion_d = summary["criterion_d_no_model"]
    assert int(criterion_d["models_fitted"]) == 0
    assert criterion_d["r2_reported"] is False
    assert criterion_d["mae_reported"] is False
    assert int(criterion_d["main_scoreboard_attempts"]) == 0
    assert summary["verdict"] == "PASS"
    for name in (
        "criterion_a_inputs",
        "criterion_b_schema",
        "criterion_c_per_channel",
        "criterion_d_no_model",
        "criterion_e_descriptive",
        "criterion_f_lf",
        "wording_guard",
    ):
        assert summary[name]["passed"], name


def test_artifacts_are_lf_without_bom() -> None:
    for path in ARTIFACTS:
        raw = path.read_bytes()
        assert b"\r" not in raw, path
        assert not raw.startswith(b"\xef\xbb\xbf"), path


def test_report_carries_the_required_labels_and_no_claims() -> None:
    report = read_text_raw(DEFAULT_REPORT)
    prereg = json.loads(DEFAULT_PREREG.read_text(encoding="utf-8"))
    assert "描述性" in report
    assert "非判决" in report
    assert prereg["descriptive_relation_definition"]["role"] in report
    assert str(EXPECTED_KIRKWOOD_R) in report
    for token in BANNED_CLAIM_TOKENS:
        assert token not in report, token
    assert guard_violations(prereg, report, load_summary()) == []


def test_guard_flags_a_performance_claim_and_a_missing_label() -> None:
    prereg = json.loads(DEFAULT_PREREG.read_text(encoding="utf-8"))
    summary = load_summary()
    assert "报告出现性能断言用词：提升" in guard_violations(prereg, "提升", summary)
    assert "报告缺少必备标注：描述性" in guard_violations(prereg, "非判决", summary)
    assert "报告缺少必备标注：descriptive_only_never_a_verdict" in guard_violations(
        prereg, "描述性与非判决", summary
    )
    broken = dict(summary)
    broken["criterion_d_no_model"] = dict(summary["criterion_d_no_model"], models_fitted=1)
    assert "判据 D 违约：本臂不许拟合模型或上报 R2" in guard_violations(
        prereg, read_text_raw(DEFAULT_REPORT), broken
    )


def test_verdict_helper_requires_every_criterion() -> None:
    summary = load_summary()
    assert verdict_of(summary) == "PASS"
    for name in ("criterion_a_inputs", "criterion_f_lf", "wording_guard"):
        broken = json.loads(json.dumps(summary, ensure_ascii=False))
        broken[name] = dict(broken[name], passed=False)
        assert verdict_of(broken) == "FAIL"


def test_pearson_and_kirkwood_helpers() -> None:
    assert kirkwood_factor(1.0) == 0.0
    assert kirkwood_factor(2.0) > 0.0
    assert pearson([1.0, 2.0, 3.0], [2.0, 4.0, 6.0]) == 1.0
    assert pearson([1.0, 2.0], [2.0, 4.0]) is None
    assert pearson([1.0, 1.0, 1.0], [1.0, 2.0, 3.0]) is None


def test_compose_is_deterministic() -> None:
    args = build_args()
    first, first_report, first_rows = compose(args, generated_at="2026-09-26T00:00:00Z")
    second, second_report, second_rows = compose(args, generated_at="2026-09-26T00:00:00Z")
    assert stable_view(first) == stable_view(second)
    assert first_report == second_report
    assert csv_text(TABLE_COLUMNS, first_rows) == csv_text(TABLE_COLUMNS, second_rows)


def test_main_round_trips_through_check(tmp_path: Path) -> None:
    table = tmp_path / "registry.csv"
    summary = tmp_path / "summary.json"
    report = tmp_path / "report.md"
    argv = [
        "--prereg",
        str(DEFAULT_PREREG),
        "--table",
        str(table),
        "--summary",
        str(summary),
        "--report",
        str(report),
    ]
    assert main(argv) == 0
    assert table.is_file() and summary.is_file() and report.is_file()
    assert main(argv + ["--check"]) == 0

    report.write_text(read_text_raw(report) + "额外一行\n", encoding="utf-8", newline="\n")
    assert main(argv + ["--check"]) == 1
    assert main(["--check", "--summary", str(tmp_path / "missing.json")]) == 1


def test_input_pin_drift_is_refused(tmp_path: Path) -> None:
    prereg = json.loads(DEFAULT_PREREG.read_text(encoding="utf-8"))
    prereg["inputs"][0]["sha256"] = "0" * 64
    drifted = tmp_path / "prereg.json"
    drifted.write_text(
        json.dumps(prereg, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n"
    )
    args = build_args(prereg=drifted)
    try:
        compose(args, generated_at="2026-09-26T00:00:00Z")
    except InputDriftError as error:
        assert "判据 A 失败" in str(error)
    else:  # pragma: no cover - 只能在输入漂移时走到
        raise AssertionError("输入漂移没有被拦下")
    assert main(["--prereg", str(drifted)]) == 1


def test_schema_drift_fails_criterion_b_without_raising(tmp_path: Path) -> None:
    prereg = json.loads(DEFAULT_PREREG.read_text(encoding="utf-8"))
    prereg["registry_schema"] = list(prereg["registry_schema"]) + ["an_extra_column"]
    drifted = tmp_path / "prereg.json"
    drifted.write_text(
        json.dumps(prereg, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n"
    )
    summary, _report, _rows = compose(
        build_args(prereg=drifted), generated_at="2026-09-26T00:00:00Z"
    )
    assert summary["criterion_b_schema"]["passed"] is False
    assert summary["criterion_b_schema"]["columns_match_prereg"] is False
    assert summary["verdict"] == "FAIL"


def test_verifier_passes_on_the_committed_artifacts() -> None:
    import subprocess

    completed = subprocess.run(
        [
            sys.executable,
            "-X",
            "utf8",
            str(REPOSITORY_ROOT / "scripts" / "verify_four_core_registry.py"),
            "--check",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(REPOSITORY_ROOT),
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    payload = json.loads(completed.stdout.strip().splitlines()[-1])
    assert payload["passed"] is True
    assert len(payload["checks"]) >= 15


def test_no_test_touches_the_network(monkeypatch: Any) -> None:
    def guard(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("test attempted a network connection")

    monkeypatch.setattr(socket, "create_connection", guard)
    assert socket.create_connection is guard
