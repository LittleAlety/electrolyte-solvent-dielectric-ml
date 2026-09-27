"""Offline tests for the Week 18 lane visual pack.

The figures themselves are pure reads of the lane summaries, so these tests
exercise the same path: they load the committed JSONs, assert the frozen
anchors still read back at the literal tolerance, prove the derived numbers are
taken from the JSON rather than typed in, and render the pack once to check the
PNGs land with real bytes.  No network, no model fit, no xTB.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))

from probes import plot_week18 as pack

FIGURE_LANE = {
    "w18_multiseed_endpoint.png": "endpoint",
    "w18_hyperparameter_grid.png": "grid",
    "w18_onsager_delta.png": "onsager",
    "w18_conformer_flexibility.png": "flex",
    "w18_log_scale_calibration.png": "logscale",
    "w18_viscosity_row_level.png": "viscosity",
    "w18_applicability_domain.png": "domain",
}

EXPECTED_FIGURES = {
    "w18_multiseed_endpoint.png",
    "w18_hyperparameter_grid.png",
    "w18_onsager_delta.png",
    "w18_conformer_flexibility.png",
    "w18_log_scale_calibration.png",
    "w18_viscosity_row_level.png",
    "w18_applicability_domain.png",
    "w18_scoreboard.png",
}


@pytest.fixture(scope="module")
def inputs() -> dict:
    return pack.load_inputs()


@pytest.fixture(scope="module")
def rendered(inputs: dict):
    return pack.render(inputs)


def test_figure_names_are_new_and_prefixed() -> None:
    assert len(pack.FIGURE_FILES) == len(EXPECTED_FIGURES)
    assert set(pack.FIGURE_FILES) == EXPECTED_FIGURES
    assert all(name.startswith("w18_") for name in pack.FIGURE_FILES)
    assert all(name.endswith(".png") for name in pack.FIGURE_FILES)


def test_ready_lane_frozen_literals_read_back(inputs: dict) -> None:
    derived = pack.derive(inputs)
    for key, expected in pack.PINNED.items():
        if key not in derived:
            continue
        assert abs(float(derived[key]) - float(expected)) <= pack.TOLERANCE, key


def test_check_pins_is_clean(inputs: dict) -> None:
    derived = pack.derive(inputs)
    assert pack.check_pins(inputs, derived) == []


def test_derived_numbers_come_from_the_json_not_from_literals(inputs: dict) -> None:
    derived = pack.derive(inputs)

    flex = inputs["flex"]
    assert flex is not None
    assert derived["flex_cross_seed_reference"] == float(flex["cross_seed"]["reference_lever4"])
    assert derived["flex_anchor_measured"] == float(flex["anchors"]["rows"][0]["measured"])

    viscosity = inputs["viscosity"]
    assert viscosity is not None
    gate = viscosity["primary_gate"]
    assert derived["viscosity_family_mae"] == float(gate["family_level_mae"])
    assert derived["viscosity_row_level_mae"] == float(gate["row_level_mae"])
    assert derived["viscosity_gate"] == float(gate["threshold"])

    domain = inputs["domain"]
    assert domain is not None
    assert derived["domain_global_r2"] == float(domain["endpoint"]["global"]["all"]["r2_mean"])
    assert derived["domain_d1_in_r2"] == float(
        domain["headline_vs_in_domain"]["D1_in_domain_r2"]
    )

    # the frozen anchors are the only numbers this pack is allowed to type in
    assert pack.FROZEN_BASELINE == 0.4091179943351143
    assert pack.FROZEN_HEADLINE == 0.4766400383507876


def test_lane_table_reports_every_lane(inputs: dict) -> None:
    rows = pack.lane_table(inputs)
    assert len(rows) == 8
    lanes = [row[0] for row in rows]
    # the scoreboard must carry all eight Week 18 lanes, P5 (Uni-Mol) included
    assert "P5 Uni-Mol embedding block" in lanes
    assert len(set(lanes)) == len(lanes)
    verdicts = {row[1] for row in rows}
    assert verdicts <= set(pack.VERDICT_COLOURS)
    for lane, verdict, reading in rows:
        if verdict == "not_landed":
            assert reading == "-"
        else:
            assert reading != "-"


def test_rendered_pngs_exist_with_real_bytes(inputs: dict, rendered) -> None:
    drawn, missing = rendered
    assert len(drawn) + len(missing) == len(pack.FIGURE_FILES)
    assert not (set(drawn) & set(missing))
    assert pack.FIG_SCOREBOARD in drawn
    # every lane whose summary is on disk must have produced its figure
    for name, key in FIGURE_LANE.items():
        if inputs[key] is not None:
            assert name in drawn, name
        else:
            assert name in missing, name
    for name in drawn:
        path = pack.ARTIFACTS / name
        assert path.is_file(), name
        assert path.stat().st_size > 0, name


def test_cjk_font_flag_is_consistent() -> None:
    assert pack.ZH == (pack.CJK_FONT is not None)
    if pack.ZH:
        assert pack.t("中文", "english") == "中文"
    else:
        assert pack.t("中文", "english") == "english"
