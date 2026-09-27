"""Offline tests for the Week 17 four-channel visual pack.

These only exercise input parsing: they read the same committed artifacts the
figures read, assert the frozen literals still read back unchanged, and let the
module's --check run its structural assertions.  No figure is rendered and no
network or xTB is touched.
"""

from __future__ import annotations

import csv
import hashlib
import sys
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))

from probes import plot_week17_channels as pack

FROZEN_FIGURES = {"themol_expansion_coverage.png", "themol_expansion_calibration.png"}

BOARD_KEYS = {
    ("dielectric", "main_scoreboard_headline_grouped_r2"),
    ("dielectric", "main_scoreboard_baseline_grouped_r2"),
    ("viscosity", "group_key_r2"),
    ("viscosity", "group_key_mae_log10_cP"),
    ("homo_lumo", "HOMO_fold_mean_mae"),
    ("homo_lumo", "LUMO_fold_mean_mae"),
    ("homo_lumo", "IP_fold_mean_mae"),
    ("homo_lumo", "EA_fold_mean_mae"),
    ("redox", "oxidation_free_energy_mae"),
    ("redox", "reduction_free_energy_mae"),
    ("dn", "admissible_coverage_fraction"),
}

FROZEN_LITERALS = {
    "dielectric_r2": 0.4091179943351143,
    "dielectric_r2_headline": 0.4766400383507876,
    "viscosity_r2": 0.7481271437772365,
    "viscosity_mae": 0.17477197208762,
    "homo_mae": 0.19050925839013938,
    "lumo_mae": 0.13855083976437643,
    "ip_mae": 0.2010970559642009,
    "ea_mae": 0.23415453202842548,
    "redox_ox_mae": 0.2905180517963865,
    "redox_red_mae": 0.4096241620366996,
    "redox_rx392": 392.0,
    "dn_covered": 0.0,
    "dn_target": 1043.0,
    "roster_rows": 5117.0,
    "tier_no_reference": 421.0,
    "tier_flagship": 54.0,
    "tier_named": 68.0,
    "tier_calibration": 4574.0,
}

CALIBRATION_COLUMNS = {
    "homo_gfn2_eV", "lumo_gfn2_eV", "gap_gfn2_eV",
    "batt_homo_eV", "batt_lumo_eV", "batt_gap_eV",
    "gfn2_minus_batt_homo_eV", "gfn2_minus_batt_lumo_eV", "gfn2_minus_batt_gap_eV",
}


@pytest.fixture(scope="module")
def inputs() -> dict:
    return pack.load_inputs()


def test_figure_names_are_new_and_prefixed() -> None:
    assert len(pack.FIGURE_FILES) >= 4
    assert all(name.startswith("w17_") for name in pack.FIGURE_FILES)
    assert not (set(pack.FIGURE_FILES) & FROZEN_FIGURES)


def test_frozen_channel_literals_read_back(inputs: dict) -> None:
    derived = pack.derive(inputs)
    for key, expected in FROZEN_LITERALS.items():
        assert derived[key] == pytest.approx(expected, rel=1e-9, abs=1e-12), key
    assert pack.check_pins(inputs, derived) == []


def test_rebuilding_layer_is_only_checked_structurally(inputs: dict) -> None:
    derived = pack.derive(inputs)
    rows = len(inputs["layer"])
    assert derived["delivered_rows"] == rows
    expected_status = "complete" if rows == inputs["roster"]["roster_rows"] else "partial"
    assert inputs["themol"]["run_status"] == expected_status
    for level in pack.CALIBRATION_LEVELS:
        assert inputs["themol"]["calibration"][level]["n"] <= rows


def test_board_carries_the_metric_keys_the_figures_read(inputs: dict) -> None:
    assert BOARD_KEYS <= set(inputs["board"])


def test_layer_header_has_the_calibration_columns(inputs: dict) -> None:
    with pack.LAYER_CSV.open(encoding="utf-8", newline="") as handle:
        header = set(next(csv.reader(handle)))
    assert CALIBRATION_COLUMNS <= header


def test_reaxys_summary_carries_the_plotted_categories(inputs: dict) -> None:
    tally = inputs["reaxys"]["channel_tally"]
    assert set(tally) >= {"eps", "eta", "hp", "redox"}
    for channel in ("eps", "eta", "hp", "redox"):
        for axis in ("rows", "valued_rows", "point_values"):
            assert axis in tally[channel]


def test_check_mode_passes_and_writes_no_figure(inputs: dict, capsys: pytest.CaptureFixture) -> None:
    before = {
        name: hashlib.sha256((pack.ARTIFACTS / name).read_bytes()).hexdigest()
        for name in pack.FIGURE_FILES
        if (pack.ARTIFACTS / name).exists()
    }
    assert pack.main(["--check"]) == 0
    out = capsys.readouterr().out
    assert "PASS" in out
    after = {
        name: hashlib.sha256((pack.ARTIFACTS / name).read_bytes()).hexdigest()
        for name in pack.FIGURE_FILES
        if (pack.ARTIFACTS / name).exists()
    }
    assert before == after
