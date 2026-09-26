"""Guards for the Week 17 four-channel coverage board."""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from electrolyte_ml.exporting import canonical_text_sha256
from probes.four_channel_coverage import (
    CHANNELS,
    MAIN_SCOREBOARD,
    PINNED,
    build_board,
    scoreboard_shape,
)

BOARD = REPOSITORY_ROOT / "data" / "processed" / "four_channel_coverage.csv"
SUMMARY = REPOSITORY_ROOT / "probes" / "four_channel_coverage_summary.json"
PREDICTIONS = (
    REPOSITORY_ROOT
    / "probes"
    / "artifacts"
    / "dielectric_coverage_paired_benchmark_predictions.csv"
)


def _board() -> list[dict[str, str]]:
    with BOARD.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_scoreboard_shape_is_recomputed_not_remembered() -> None:
    assert scoreboard_shape(PREDICTIONS) == (457, 97, 276)


def test_board_reproduces_from_the_shipped_artifacts() -> None:
    rows, summary = build_board()
    shipped = _board()
    assert len(rows) == len(shipped)
    for actual, expected in zip(shipped, rows, strict=True):
        assert actual == expected
    assert summary["board_rows"] == len(shipped)


def test_main_scoreboard_is_quoted_never_recomputed() -> None:
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    assert summary["main_scoreboard"] == MAIN_SCOREBOARD
    assert summary["run_telemetry"]["models_fitted"] == 0
    assert summary["run_telemetry"]["r2_reported"] is False
    values = {row["metric"]: row["value"] for row in _board()}
    assert float(values["main_scoreboard_grouped_r2"]) == MAIN_SCOREBOARD


def test_the_four_channels_and_the_added_dimensions_are_all_on_the_board() -> None:
    channels = {row["channel"] for row in _board()}
    assert set(CHANNELS).issubset(channels)
    assert {"liquid_window", "walden", "dn", "density", "li_coordination"}.issubset(channels)


def test_gate_statuses_match_the_owning_artifacts() -> None:
    rows = {row["metric"]: row for row in _board()}
    assert rows["HOMO_fold_mean_mae"]["gate_status"] == "green"
    assert rows["LUMO_fold_mean_mae"]["gate_status"] == "green"
    assert rows["IP_fold_mean_mae"]["gate_status"] == "red"
    assert rows["EA_fold_mean_mae"]["gate_status"] == "red"
    assert rows["group_key_r2"]["gate_status"] == "red"
    assert rows["admissible_coverage_fraction"]["gate_status"] == "red"
    assert rows["ec_melting_point_verdict"]["gate_status"] == "blocked"


def test_sample_size_is_reported_as_pairs_not_rows() -> None:
    rows = {row["metric"]: row for row in _board()}
    assert rows["scoreboard_distinct_compound_temperature_pairs"]["value"] == "276"
    assert rows["scoreboard_rows"]["value"] == "457"


def test_board_is_lf_only() -> None:
    assert b"\r\n" not in BOARD.read_bytes()


def test_summary_pins_match_the_file() -> None:
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    assert summary["pinned"] == PINNED
    assert summary["outputs"]["board"]["sha256"] == canonical_text_sha256(BOARD)
    assert summary["outputs"]["board"]["row_count"] == len(_board())


def test_a_drifted_pin_fails_loudly(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(PINNED, "viscosity_v01_rows", 3583)
    with pytest.raises(SystemExit, match="pinned value drifted"):
        build_board()
