"""Offline tests for the NBS 514 alpha prior probe.

Everything here runs against synthetic tables in a temporary directory: no
network, no read of ``data/processed``, no re-fit of the frozen endpoint.

Imports are deliberately bare (``import dielectric_alpha_prior_probe``) rather
than namespaced, for the same reason as in ``test_dielectric_band_ablation.py``:
the probe imports its collaborators by bare name, so the two spellings would
resolve to two module objects and a monkeypatch applied to one would silently
miss the other.
"""

from __future__ import annotations

import csv
import json
import math
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

import numpy as np
import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "probes"))
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

import dielectric_alpha_prior_probe as alpha_probe
import dielectric_observations_grouped_benchmark as grouped_benchmark
from dielectric_alpha_prior_probe import (
    ALPHA_ARMS,
    ARM_ORDER,
    HYBRID,
    MISSING,
    PAIRINGS,
    ROOM_BAND,
    V10_ARMS,
    alpha_coefficient,
    alpha_to_depsilon_dt,
    classify,
    compound_slopes,
    crosscheck_rows,
    describe,
    effect_over_null_block,
    feature_coverage,
    file_sha256,
    fit_empirical_slope,
    label_identity,
    main,
    nbs_alpha_block,
    paired_delta,
    read_alpha_table,
    reference_reproduction,
    render_report,
    repeat_metric_lookup,
    run_arm,
    run_room_family,
    slope_block,
    static_arm,
    subsampling_control,
    summarize_crosscheck,
    symmetric_relative_difference,
    verify_conversion,
)
from dielectric_observations_grouped_benchmark import (
    build_matrices,
    grouped_folds,
    run_protocol,
)
from dielectric_representation_ablation import PHYSICAL_COLUMNS

SMILES = (
    "CCO",
    "CCCO",
    "CCCCO",
    "CCCCC",
    "c1ccccc1",
    "CC(=O)C",
    "CO",
    "CC#N",
)

ROOM = ROOM_BAND

EXTENDED = "extended_temperature"

OUTSIDE = "outside_declared_window"

#: (band, temperature, epsilon) per synthetic compound. Every compound carries
#: at least two room rows so no grouped fold can be dropped as thin, and three
#: of them carry out-of-window rows so the "all bands" slope differs from the
#: room-only one - which is the regression the probe's slope source guards.
BAND_PLAN: dict[int, tuple[tuple[str, float, float], ...]] = {
    0: (
        (ROOM, 295.15, 20.0),
        (ROOM, 300.15, 19.4),
        (EXTENDED, 288.15, 20.6),
        (OUTSIDE, 350.0, 16.0),
    ),
    1: (
        (ROOM, 293.15, 33.0),
        (ROOM, 298.15, 32.4),
        (ROOM, 302.15, 31.9),
        (EXTENDED, 285.0, 33.6),
    ),
    2: ((ROOM, 298.15, 2.4), (ROOM, 303.15, 2.35)),
    3: ((ROOM, 294.15, 5.9), (ROOM, 299.15, 5.8), (OUTSIDE, 330.0, 5.2)),
    4: ((ROOM, 296.15, 12.0), (ROOM, 299.15, 11.8), (EXTENDED, 290.0, 12.3)),
    5: (
        (ROOM, 297.15, 46.0),
        (ROOM, 301.15, 45.1),
        (OUTSIDE, 355.0, 40.0),
        (EXTENDED, 292.0, 46.7),
    ),
    6: ((ROOM, 299.15, 8.1), (ROOM, 302.15, 8.0)),
    7: ((ROOM, 295.65, 3.3), (ROOM, 301.65, 3.26)),
}

#: inchikey -> (coefficient as printed, kind, tabulated T_K, tabulated epsilon).
#: Compound 99 is absent from the observation table on purpose, so the coverage
#: code has to count an alpha row that pairs with nothing.
ALPHA_ROWS: dict[str, tuple[float, str, float, float]] = {
    "SYNTH0000-UHFFFAOYSA-N": (200.0, "a", 293.15, 2.238),
    "SYNTH0001-UHFFFAOYSA-N": (235.0, "alpha", 298.15, 10.36),
    "SYNTH0004-UHFFFAOYSA-N": (335.0, "alpha", 298.15, 17.1),
    "SYNTH0099-UHFFFAOYSA-N": (130.0, "alpha", 293.15, 5.71),
}

#: The subset of the alpha table whose pool label equals the tabulated epsilon.
IDENTICAL_LABELS = {"SYNTH0000-UHFFFAOYSA-N", "SYNTH0001-UHFFFAOYSA-N"}


def _key(index: int) -> str:
    return f"SYNTH{index:04d}-UHFFFAOYSA-N"


def _write_lf_csv(
    path: Path,
    header: Sequence[str],
    rows: Sequence[Sequence[object]],
) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)


def _write_alpha_table(path: Path, table: dict[str, tuple[float, str, float, float]] | None = None) -> None:
    table = ALPHA_ROWS if table is None else table
    rows = []
    for key, (coefficient, kind, temperature, dielectric) in sorted(table.items()):
        rows.append(
            [
                f"nbs514:synthetic:{key}",
                key,
                f"mol-{key[:8]}",
                "C2H6O",
                temperature,
                round(temperature - 273.15, 2),
                dielectric,
                coefficient,
                kind,
                "-10,60",
                -10,
                60,
                "true",
                "range_covers_target",
                -coefficient * 1e-5
                if kind == "a"
                else -coefficient * 1e-5 * dielectric * math.log(10.0),
                "true",
                dielectric,
                0.0,
                0.0,
                "false",
            ]
        )
    _write_lf_csv(
        path,
        (
            "source_id",
            "inchikey",
            "compound_name",
            "formula",
            "T_K",
            "temperature_c",
            "dielectric_observed",
            "alpha_1e5",
            "alpha_kind",
            "valid_range_C",
            "range_low_c",
            "range_high_c",
            "target_in_valid_range",
            "correctability",
            "implied_dielectric_slope",
            "implied_slope_is_physical",
            "dielectric_at_298_15",
            "delta_epsilon",
            "relative_delta_epsilon",
            "in_frozen_v03",
        ),
        rows,
    )


def _write_v11_tables(
    root: Path,
    plan: dict[int, tuple[tuple[str, float, float], ...]] | None = None,
) -> tuple[Path, Path]:
    """Write a synthetic observation + xTB feature pair and return their paths."""

    plan = BAND_PLAN if plan is None else plan
    observations = root / "observations.csv"
    features = root / "features.csv"
    _write_lf_csv(
        observations,
        (
            "inchikey",
            "name",
            "smiles",
            "T_K",
            "epsilon",
            "temperature_band",
            "source_doi",
        ),
        [
            [_key(index), f"mol{index}", SMILES[index], temperature, epsilon, band, "10.1000/synthetic"]
            for index, entries in sorted(plan.items())
            for band, temperature, epsilon in entries
        ],
    )
    _write_lf_csv(
        features,
        ("inchikey", "status", *PHYSICAL_COLUMNS),
        [
            [
                _key(index),
                "ok",
                *[
                    298.15 if column == "T_K" else float(index + 1)
                    for column in PHYSICAL_COLUMNS
                ],
            ]
            for index in sorted(plan)
        ],
    )
    return observations, features


def _write_v10_tables(root: Path) -> tuple[Path, Path]:
    """Write a synthetic frozen-feature table plus the roster it is gated by."""

    frozen = root / "frozen_features.csv"
    dataset = root / "dataset.csv"
    _write_lf_csv(
        frozen,
        ("inchikey", "name", "smiles", "T_K", "dielectric", "status", *PHYSICAL_COLUMNS),
        [
            [
                _key(index),
                f"mol{index}",
                SMILES[index],
                293.15 + index,
                5.0 + index,
                "ok",
                *[
                    293.15 + index if column == "T_K" else float(index + 1)
                    for column in PHYSICAL_COLUMNS
                ],
            ]
            for index in sorted(BAND_PLAN)
        ],
    )
    _write_lf_csv(
        dataset,
        ("inchikey", "model_ready", "dielectric", "T_K"),
        [
            [
                _key(index),
                "true",
                ALPHA_ROWS[_key(index)][3] if _key(index) in IDENTICAL_LABELS else 99.0,
                ALPHA_ROWS[_key(index)][2] if _key(index) in IDENTICAL_LABELS else 293.15,
            ]
            for index in sorted(BAND_PLAN)
        ],
    )
    return frozen, dataset


def _alpha_path(root: Path) -> Path:
    """Write the synthetic alpha table once per root and return its path."""

    path = root / "alpha.csv"
    if not path.exists():
        _write_alpha_table(path)
    return path


def _v11_rows(
    root: Path,
    plan: dict[int, tuple[tuple[str, float, float], ...]] | None = None,
) -> list[dict[str, str]]:
    observations, features = _write_v11_tables(root, plan)
    rows, _features, _dropped = grouped_benchmark.load_table(observations, features)
    return rows


# --------------------------------------------------------------------------- #
# The alpha definition and its unit conversion
# --------------------------------------------------------------------------- #


def test_alpha_definition_kind_a_is_the_linear_branch() -> None:
    assert alpha_to_depsilon_dt(200.0, "a", 2.238) == pytest.approx(-0.002)
    assert alpha_to_depsilon_dt(268.0, "a", 2.641) == pytest.approx(-0.00268)


def test_alpha_definition_kind_a_ignores_the_epsilon() -> None:
    assert alpha_to_depsilon_dt(200.0, "a", 2.0) == alpha_to_depsilon_dt(200.0, "a", 900.0)


def test_alpha_definition_kind_alpha_needs_the_epsilon() -> None:
    expected = -235.0 * 1e-5 * 10.36 * math.log(10.0)
    assert alpha_to_depsilon_dt(235.0, "alpha", 10.36) == pytest.approx(expected)
    # The log branch is proportional to eps, so a larger eps is a larger drop:
    # both values are negative and the bigger-eps one is further from zero.
    assert abs(alpha_to_depsilon_dt(235.0, "alpha", 20.0)) > abs(
        alpha_to_depsilon_dt(235.0, "alpha", 10.0)
    )
    assert alpha_to_depsilon_dt(235.0, "alpha", 20.0) == pytest.approx(
        2.0 * alpha_to_depsilon_dt(235.0, "alpha", 10.0)
    )


def test_the_two_branches_differ_by_the_epsilon_times_ln10() -> None:
    linear = alpha_to_depsilon_dt(200.0, "a", 55.0)
    logarithmic = alpha_to_depsilon_dt(200.0, "alpha", 55.0)
    assert logarithmic / linear == pytest.approx(55.0 * math.log(10.0))


def test_alpha_definition_accepts_the_greek_kind() -> None:
    assert alpha_to_depsilon_dt(235.0, "\u03b1", 10.36) == alpha_to_depsilon_dt(
        235.0, "alpha", 10.36
    )


def test_alpha_definition_refuses_an_unknown_kind() -> None:
    with pytest.raises(ValueError, match="unsupported alpha_kind"):
        alpha_to_depsilon_dt(200.0, "b", 2.0)


def test_both_branches_point_the_same_way_for_a_normal_liquid() -> None:
    for kind in ("a", "alpha"):
        assert alpha_to_depsilon_dt(200.0, kind, 20.0) < 0.0


# --------------------------------------------------------------------------- #
# Empirical slope fitting
# --------------------------------------------------------------------------- #


def test_fit_empirical_slope_is_exact_on_a_straight_line() -> None:
    fit = fit_empirical_slope([300.0, 310.0, 320.0], [20.0, 18.0, 16.0])
    assert fit is not None
    assert fit["slope"] == pytest.approx(-0.2)
    assert fit["intercept"] == pytest.approx(80.0)
    assert fit["r2"] == pytest.approx(1.0)


def test_fit_empirical_slope_reports_the_span_and_the_point_count() -> None:
    fit = fit_empirical_slope([290.0, 300.0, 320.0, 305.0], [10.0, 9.5, 8.5, 9.2])
    assert fit is not None
    assert fit["n_points"] == 4
    assert fit["n_distinct_temperatures"] == 4
    assert fit["span_K"] == pytest.approx(30.0)
    assert fit["mean_temperature_K"] == pytest.approx(303.75)
    assert fit["mean_epsilon"] == pytest.approx(9.3)


def test_fit_empirical_slope_returns_none_for_a_single_temperature() -> None:
    assert fit_empirical_slope([300.0, 300.0], [20.0, 20.1]) is None


def test_fit_empirical_slope_returns_none_for_an_empty_sample() -> None:
    assert fit_empirical_slope([], []) is None


def test_fit_empirical_slope_rejects_mismatched_lengths() -> None:
    with pytest.raises(ValueError, match="differ in length"):
        fit_empirical_slope([300.0, 310.0], [20.0])


def test_compound_slopes_needs_two_distinct_temperatures(tmp_path: Path) -> None:
    rows = _v11_rows(tmp_path)
    slopes = compound_slopes(rows)
    assert set(slopes) == {_key(index) for index in BAND_PLAN}
    single = [
        {"inchikey": _key(0), "T_K": "300.0", "epsilon": "5.0"},
        {"inchikey": _key(0), "T_K": "300.0", "epsilon": "5.1"},
    ]
    assert compound_slopes(single) == {}


def test_compound_slopes_can_be_restricted_to_one_band(tmp_path: Path) -> None:
    rows = _v11_rows(tmp_path)
    room_only = compound_slopes(rows, band=ROOM_BAND)
    everything = compound_slopes(rows)
    assert set(room_only) == set(everything)
    assert room_only[_key(0)]["slope"] != pytest.approx(everything[_key(0)]["slope"])


# --------------------------------------------------------------------------- #
# describe / relative difference
# --------------------------------------------------------------------------- #


def test_describe_reports_quantiles_and_sign_counts() -> None:
    block = describe([-4.0, -2.0, 0.0, 2.0, 4.0])
    assert block["n"] == 5
    assert block["median"] == pytest.approx(0.0)
    assert block["min"] == pytest.approx(-4.0)
    assert block["max"] == pytest.approx(4.0)
    assert block["n_negative"] == 2
    assert block["n_positive"] == 2


def test_describe_drops_non_finite_values() -> None:
    block = describe([1.0, float("nan"), None, 3.0])
    assert block["n"] == 2
    assert block["max"] == pytest.approx(3.0)


def test_describe_of_an_empty_sample_is_all_none() -> None:
    block = describe([])
    assert block["n"] == 0
    assert block["median"] is None


def test_symmetric_relative_difference_is_symmetric() -> None:
    assert symmetric_relative_difference(2.0, 4.0) == pytest.approx(
        symmetric_relative_difference(4.0, 2.0)
    )
    assert symmetric_relative_difference(3.0, 3.0) == 0.0


def test_symmetric_relative_difference_of_two_zeros_is_zero() -> None:
    assert symmetric_relative_difference(0.0, 0.0) == 0.0


# --------------------------------------------------------------------------- #
# The conversion self-check against the frozen column
# --------------------------------------------------------------------------- #


def test_verify_conversion_reproduces_the_frozen_column(tmp_path: Path) -> None:
    path = tmp_path / "alpha.csv"
    _write_alpha_table(path)
    result = verify_conversion(read_alpha_table(path))
    assert result["rows_compared"] == len(ALPHA_ROWS)
    assert result["bit_exact"] is True
    assert result["max_abs_delta"] == 0.0
    assert result["alpha_kind_counts"] == {"a": 1, "alpha": 3}


def test_verify_conversion_detects_a_mismatched_kind(tmp_path: Path) -> None:
    path = tmp_path / "alpha.csv"
    _write_alpha_table(path)
    text = path.read_text(encoding="utf-8").replace(
        "SYNTH0001-UHFFFAOYSA-N", "SYNTH0001-UHFFFAOYSA-N"
    )
    path.write_text(text, encoding="utf-8", newline="\n")
    rows = read_alpha_table(path)
    rows["SYNTH0001-UHFFFAOYSA-N"]["alpha_kind"] = "a"
    result = verify_conversion(rows)
    assert result["bit_exact"] is False
    assert float(result["max_abs_delta"]) > 0.0


def test_verify_conversion_ignores_rows_without_a_coefficient(tmp_path: Path) -> None:
    path = tmp_path / "alpha.csv"
    _write_alpha_table(path)
    rows = read_alpha_table(path)
    rows["SYNTH0004-UHFFFAOYSA-N"]["alpha_1e5"] = ""
    rows["SYNTH0004-UHFFFAOYSA-N"]["implied_dielectric_slope"] = ""
    result = verify_conversion(rows)
    assert result["rows_compared"] == len(ALPHA_ROWS) - 1
    assert result["bit_exact"] is True

# --------------------------------------------------------------------------- #
# The alpha feature block
# --------------------------------------------------------------------------- #


def test_alpha_block_has_two_epsilon_free_columns(tmp_path: Path) -> None:
    rows = _v11_rows(tmp_path)
    alpha = read_alpha_table(_alpha_path(tmp_path))
    block, meta = nbs_alpha_block(rows, alpha)
    assert block.shape == (len(rows), 2)
    assert meta["epsilon_free"] is True
    assert meta["columns"] == ("nbs_alpha_1e5", "nbs_alpha_kind_is_log")
    covered_rows = sum(
        len(entries) for index, entries in BAND_PLAN.items() if _key(index) in ALPHA_ROWS
    )
    assert covered_rows == 11
    assert meta["rows_covered"] == covered_rows
    assert meta["compounds_covered"] == 3
    assert meta["alpha_kind_counts"] == {"a": 4, "alpha": 7}


def test_alpha_block_does_not_read_the_pool_epsilon(tmp_path: Path) -> None:
    """The whole reason the block is epsilon-free: otherwise it would be the label."""

    rows = _v11_rows(tmp_path)
    alpha = read_alpha_table(_alpha_path(tmp_path))
    shifted = [dict(row) for row in rows]
    for row in shifted:
        row["epsilon"] = str(float(row["epsilon"]) * 3.0)
    # equal_nan is required: the uncovered compounds are NaN on both sides and
    # NaN != NaN, so the plain comparison would fail on a block that is identical.
    assert np.array_equal(
        nbs_alpha_block(rows, alpha)[0], nbs_alpha_block(shifted, alpha)[0], equal_nan=True
    )


def test_alpha_block_marks_an_uncovered_compound_with_nan(tmp_path: Path) -> None:
    rows = _v11_rows(tmp_path)
    alpha = read_alpha_table(_alpha_path(tmp_path))
    block, _meta = nbs_alpha_block(rows, alpha)
    uncovered = [i for i, row in enumerate(rows) if row["inchikey"] == _key(2)]
    assert uncovered
    assert all(math.isnan(block[index, 0]) for index in uncovered)
    assert all(math.isnan(block[index, 1]) for index in uncovered)


def test_alpha_block_kind_flag_is_one_only_for_the_log_branch(tmp_path: Path) -> None:
    rows = _v11_rows(tmp_path)
    alpha = read_alpha_table(_alpha_path(tmp_path))
    block, _meta = nbs_alpha_block(rows, alpha)
    for index, row in enumerate(rows):
        if row["inchikey"] == _key(0):
            assert block[index, 0] == 200.0
            assert block[index, 1] == 0.0
        elif row["inchikey"] == _key(1):
            assert block[index, 0] == 235.0
            assert block[index, 1] == 1.0


def test_alpha_coefficient_returns_none_for_a_blank_cell() -> None:
    assert alpha_coefficient({"alpha_1e5": "", "alpha_kind": ""}) is None
    assert alpha_coefficient({"alpha_1e5": " 235 ", "alpha_kind": "alpha"}) == (235.0, "alpha")


def test_slope_block_maps_by_inchikey(tmp_path: Path) -> None:
    rows = _v11_rows(tmp_path)
    slopes = compound_slopes(rows)
    block = slope_block(rows, slopes)
    assert block.shape == (len(rows), 1)
    for index, row in enumerate(rows):
        assert block[index, 0] == pytest.approx(slopes[row["inchikey"]]["slope"])


def test_slope_block_leaves_an_unknown_compound_missing(tmp_path: Path) -> None:
    rows = _v11_rows(tmp_path)
    block = slope_block(rows, {})
    assert np.all(np.isnan(block))


# --------------------------------------------------------------------------- #
# Coverage and label identity
# --------------------------------------------------------------------------- #


def test_feature_coverage_counts_rows_compounds_and_kinds(tmp_path: Path) -> None:
    rows = _v11_rows(tmp_path)
    alpha = read_alpha_table(_alpha_path(tmp_path))
    block = feature_coverage(rows, alpha, label="synthetic")
    assert block["rows"] == len(rows)
    assert block["compounds"] == len(BAND_PLAN)
    assert block["compounds_with_an_alpha_row"] == 3
    assert block["compounds_with_a_coefficient"] == 3
    assert block["coefficient_coverage"] == pytest.approx(3 / 8)
    assert block["alpha_kind_counts"] == {"a": 1, "alpha": 2}


def test_feature_coverage_counts_an_alpha_row_without_a_coefficient(tmp_path: Path) -> None:
    rows = _v11_rows(tmp_path)
    alpha = read_alpha_table(_alpha_path(tmp_path))
    alpha[_key(2)] = {"inchikey": _key(2), "alpha_1e5": "", "alpha_kind": "", "compound_name": "mol2"}
    block = feature_coverage(rows, alpha, label="synthetic")
    assert block["compounds_with_an_alpha_row"] == 4
    assert block["compounds_with_a_coefficient"] == 3


def test_label_identity_counts_the_rows_that_are_the_label(tmp_path: Path) -> None:
    alpha = read_alpha_table(_alpha_path(tmp_path))
    _frozen, dataset = _write_v10_tables(tmp_path)
    block = label_identity(alpha, alpha_probe.read_csv_rows(dataset))
    assert block["alpha_carrying_rows_also_in_the_pool"] == 3
    assert block["label_is_the_nbs_tabulated_value"] == 2


def test_label_identity_ignores_an_alpha_row_that_is_not_in_the_pool(tmp_path: Path) -> None:
    alpha = read_alpha_table(_alpha_path(tmp_path))
    dataset = tmp_path / "tiny_dataset.csv"
    _write_lf_csv(dataset, ("inchikey", "model_ready", "dielectric", "T_K"), [])
    block = label_identity(alpha, alpha_probe.read_csv_rows(dataset))
    assert block["alpha_carrying_rows_also_in_the_pool"] == 0


# --------------------------------------------------------------------------- #
# Cross-check
# --------------------------------------------------------------------------- #


def test_crosscheck_rows_pair_only_tables_that_share_a_compound(tmp_path: Path) -> None:
    rows = _v11_rows(tmp_path)
    alpha = read_alpha_table(_alpha_path(tmp_path))
    table = crosscheck_rows(compound_slopes(rows), alpha, cohort="synthetic")
    assert len(table) == 3
    assert {entry["inchikey"] for entry in table} == {_key(0), _key(1), _key(4)}


def test_crosscheck_rows_evaluate_the_log_branch_at_the_observed_mean_epsilon(
    tmp_path: Path,
) -> None:
    rows = _v11_rows(tmp_path)
    alpha = read_alpha_table(_alpha_path(tmp_path))
    table = crosscheck_rows(compound_slopes(rows), alpha, cohort="synthetic")
    entry = next(item for item in table if item["inchikey"] == _key(1))
    expected = -235.0 * 1e-5 * entry["empirical_mean_epsilon"] * math.log(10.0)
    assert entry["nbs_slope_at_observed_mean_epsilon"] == pytest.approx(expected)
    assert entry["nbs_slope_at_tabulated_epsilon"] == pytest.approx(
        -235.0 * 1e-5 * 10.36 * math.log(10.0)
    )


def test_crosscheck_rows_record_the_signed_deviation_as_empirical_minus_nbs(
    tmp_path: Path,
) -> None:
    rows = _v11_rows(tmp_path)
    alpha = read_alpha_table(_alpha_path(tmp_path))
    table = crosscheck_rows(compound_slopes(rows), alpha, cohort="synthetic")
    for entry in table:
        assert entry["signed_deviation_at_observed"] == pytest.approx(
            entry["empirical_slope"] - entry["nbs_slope_at_observed_mean_epsilon"]
        )


def test_summarize_crosscheck_groups_by_cohort(tmp_path: Path) -> None:
    rows = _v11_rows(tmp_path)
    alpha = read_alpha_table(_alpha_path(tmp_path))
    table_one = crosscheck_rows(compound_slopes(rows), alpha, cohort="all")
    table_two = crosscheck_rows(compound_slopes(rows, band=ROOM_BAND), alpha, cohort="room")
    summary = summarize_crosscheck(table_one + table_two)
    assert set(summary["by_cohort"]) == {"all", "room"}
    assert summary["by_cohort"]["all"]["pairs"] == 3
    assert summary["all_cohorts"]["pairs"] == 6
    assert summary["all_cohorts"]["temperature_span_K"]["n"] == 6


def test_summarize_crosscheck_of_nothing_has_no_combined_block() -> None:
    summary = summarize_crosscheck([])
    assert summary["by_cohort"] == {}
    assert summary["all_cohorts"] is None


# --------------------------------------------------------------------------- #
# Arms and the runner
# --------------------------------------------------------------------------- #


def _frozen_matrices(rows: Sequence[dict[str, str]]) -> dict[str, object]:
    morgan, physical, target, temperatures, groups = build_matrices(rows)
    return {
        "morgan": morgan,
        "physical": physical,
        "target": target,
        "temperatures": temperatures,
        "groups": groups,
    }


def test_run_arm_without_an_arm_reproduces_the_frozen_run_protocol(tmp_path: Path) -> None:
    rows = _v11_rows(tmp_path)
    shared = _frozen_matrices(rows)
    splits = list(grouped_folds(shared["groups"], n_splits=3, n_repeats=2, seed=42))
    mine = run_arm("synthetic", splits, **shared)
    theirs = run_protocol("synthetic", iter(splits), **shared)
    for representation in ("Morgan", "Physical", "Morgan+Physical"):
        my_row = next(
            row for row in mine["repeat_rows"] if row["representation"] == representation
        )
        their_row = next(
            row for row in theirs[1] if row["representation"] == representation
        )
        for metric in ("r2", "mae", "rmse", "spearman"):
            assert my_row[metric] == their_row[metric]
    # The probe annotates every fold row with the number of extra columns it
    # appended; the frozen protocol has no such column, so the comparison runs
    # on the frozen key set and the annotation is checked separately.
    assert [
        {key: row[key] for key in grouped_benchmark.FOLD_COLUMNS} for row in mine["fold_rows"]
    ] == theirs[0]
    assert {row["extra_columns"] for row in mine["fold_rows"]} == {0}


def test_run_arm_records_how_many_columns_the_arm_added(tmp_path: Path) -> None:
    rows = _v11_rows(tmp_path)
    shared = _frozen_matrices(rows)
    splits = list(grouped_folds(shared["groups"], n_splits=3, n_repeats=1, seed=42))
    block = np.full((len(rows), 2), MISSING, dtype=float)
    result = run_arm("synthetic", splits, arm=static_arm(block), **shared)
    assert {row["extra_columns"] for row in result["fold_rows"]} == {2}
    assert result["summary"][HYBRID]["r2"]["n"] == 1


def test_run_arm_refuses_to_report_a_family_with_no_surviving_fold(tmp_path: Path) -> None:
    rows = _v11_rows(tmp_path)
    shared = _frozen_matrices(rows)
    with pytest.raises(ValueError, match="no fold survived"):
        run_arm("synthetic", [], **shared)


def test_static_arm_hands_the_same_block_to_every_fold() -> None:
    block = np.arange(6.0).reshape(3, 2)
    arm = static_arm(block)
    assert arm(np.array([0, 1]), np.array([2])) is block


def test_train_only_arm_leaves_every_scored_row_missing(tmp_path: Path) -> None:
    rows = _v11_rows(tmp_path)
    arm, stats = alpha_probe.make_train_only_arm(rows)
    shared = _frozen_matrices(rows)
    for _repeat, _fold, train_index, test_index in grouped_folds(
        shared["groups"], n_splits=3, n_repeats=2, seed=42
    ):
        block = arm(train_index, test_index)
        assert np.all(np.isnan(block[test_index, 0]))
        assert np.all(np.isfinite(block[train_index, 0]))
    assert stats["test_rows_total"] > 0
    assert stats["test_rows_with_a_slope"] == 0


def test_train_only_arm_fits_only_the_training_rows(tmp_path: Path) -> None:
    rows = _v11_rows(tmp_path)
    arm, _stats = alpha_probe.make_train_only_arm(rows)
    keys = [row["inchikey"] for row in rows]
    target_key = _key(0)
    every_row = np.flatnonzero(np.asarray([key == target_key for key in keys]))
    block = arm(every_row, np.array([0], dtype=int))
    fit = compound_slopes(rows)[target_key]
    assert block[every_row[0], 0] == pytest.approx(fit["slope"])


def test_all_nan_columns_still_move_the_predictions(tmp_path: Path) -> None:
    """The trap that forces the placebo arms to exist."""

    rows = _v11_rows(tmp_path)
    control = subsampling_control(rows)
    assert control["measured"] is True
    assert control["predictions_identical"] is False
    assert control["max_abs_prediction_delta"] > 0.0


def test_effect_over_null_block_subtracts_the_placebo() -> None:
    deltas = {
        "arm": {"mean_delta_r2": 0.030},
        "null": {"mean_delta_r2": 0.010},
    }
    effects = effect_over_null_block(deltas, pairs=(("arm", "null"),))
    assert effects["arm"]["effect_over_the_placebo_r2"] == pytest.approx(0.02)
    assert effects["arm"]["classification"] == "helps"
    assert effects["arm"]["placebo"] == "null"


def test_effect_over_null_block_skips_an_arm_that_was_not_run() -> None:
    effects = effect_over_null_block({"null": {"mean_delta_r2": 0.0}}, pairs=(("arm", "null"),))
    assert effects == {}


def test_classify_uses_the_inert_tolerance() -> None:
    assert classify(0.004) == "inert"
    assert classify(-0.004) == "inert"
    assert classify(0.006) == "helps"
    assert classify(-0.006) == "hurts"
    assert classify(None) == "not run"


def _metrics(r2: float, mae: float, spearman: float) -> dict[str, float]:
    """A complete METRIC_NAMES row; the leak audit reads all seven."""

    return {
        "r2": r2,
        "mae": mae,
        "rmse": mae,
        "spearman": spearman,
        "mae_lt20": mae,
        "mae_20_60": mae,
        "mae_gt60": mae,
    }


def test_repeat_metric_lookup_carries_every_metric() -> None:
    arms = {
        "a": {"repeat_rows": [{"protocol": "a", "repeat": 0, **_metrics(0.5, 1.0, 0.25)}]},
    }
    lookup = repeat_metric_lookup(arms)
    assert lookup[("a", 0)]["r2"] == 0.5
    assert lookup[("a", 0)]["mae_gt60"] == 1.0
    assert lookup[("a", 0)]["spearman"] == 0.25


def test_paired_delta_matches_a_hand_computed_difference() -> None:
    lookup = {
        ("base", 0): _metrics(0.10, 2.0, 0.40),
        ("base", 1): _metrics(0.20, 1.0, 0.50),
        ("arm", 0): _metrics(0.13, 1.8, 0.42),
        ("arm", 1): _metrics(0.24, 0.9, 0.55),
    }
    delta = paired_delta(lookup, baseline="base", arm="arm")
    assert delta["repeats"] == 2
    assert delta["mean_delta_r2"] == pytest.approx(0.035)
    assert delta["delta_r2"]["n_positive"] == 2
    assert delta["repeats_favouring_the_arm"] == 2
    assert delta["classification_r2"] == "helps"
    assert delta["fold_metrics_identical_to_baseline"] is False


def test_paired_delta_of_an_identical_arm_is_zero_and_flagged_identical() -> None:
    lookup = {
        ("base", 0): _metrics(0.10, 2.0, 0.40),
        ("arm", 0): _metrics(0.10, 2.0, 0.40),
    }
    delta = paired_delta(lookup, baseline="base", arm="arm")
    assert delta["mean_delta_r2"] == 0.0
    assert delta["classification_r2"] == "inert"
    assert delta["fold_metrics_identical_to_baseline"] is True
    assert delta["wilcoxon_p_r2"] is None


def test_paired_delta_reports_not_run_for_an_absent_arm() -> None:
    delta = paired_delta({}, baseline="base", arm="arm")
    assert delta["repeats"] == 0
    assert delta["note"] == "not run"


# --------------------------------------------------------------------------- #
# The room family, including the slope-source regression
# --------------------------------------------------------------------------- #


def test_run_room_family_builds_every_arm_on_one_fold_assignment(tmp_path: Path) -> None:
    rows = _v11_rows(tmp_path)
    room = [row for row in rows if row["temperature_band"] == ROOM_BAND]
    family = run_room_family(
        room,
        read_alpha_table(_alpha_path(tmp_path)),
        slope_source_rows=rows,
        n_splits=3,
        n_repeats=2,
        seed=42,
    )
    assert set(family["arms"]) == set(ALPHA_ARMS)
    # every fold row is per representation, so:
    # len(REPRESENTATIONS) x n_splits x n_repeats
    expected_fold_rows = len(alpha_probe.REPRESENTATIONS) * 3 * 2
    fold_counts = {len(arm["fold_rows"]) for arm in family["arms"].values()}
    assert fold_counts == {expected_fold_rows}
    assert family["nbs_alpha_block"]["rows_covered"] == 7
    assert family["train_only_slope"]["test_rows_with_a_slope"] == 0
    assert family["empirical_slope_coverage"]["coverage_over_all_bands"] == pytest.approx(1.0)


def _without_protocol(rows: Sequence[dict[str, object]]) -> list[dict[str, object]]:
    """Arm identity lives in the protocol name; the numbers are what we compare.

    NaN is folded onto a sentinel: an empty stratum makes ``np.nanmean([])`` emit
    NaN, and ``nan != nan`` would make ``==`` fail on two identical arms while
    making ``!=`` vacuously true.
    """

    def _normalise(value: object) -> object:
        if isinstance(value, float) and math.isnan(value):
            return "__nan__"
        return value

    return [
        {key: _normalise(value) for key, value in row.items() if key != "protocol"}
        for row in rows
    ]


def test_the_slope_source_rows_change_the_all_bands_arm(tmp_path: Path) -> None:
    """Regression: fitting "all bands" on room rows made two arms identical.

    The guard has to look at what the two arms are *fitted on*: on a fixture this
    small XGBoost may never select the slope column, so the arm metrics can be
    identical even when the wiring is correct (the reverse of the bug).
    """

    rows = _v11_rows(tmp_path)
    room = [row for row in rows if row["temperature_band"] == ROOM_BAND]
    alpha = read_alpha_table(_alpha_path(tmp_path))
    proper = run_room_family(
        room, alpha, slope_source_rows=rows, n_splits=3, n_repeats=1, seed=42
    )
    degenerate = run_room_family(room, alpha, n_splits=3, n_repeats=1, seed=42)

    slopes_all_bands = compound_slopes(rows)
    slopes_room_only = compound_slopes(rows, band=ROOM_BAND)
    assert slopes_all_bands != slopes_room_only
    all_bands_block = slope_block(room, slopes_all_bands)
    room_band_block = slope_block(room, slopes_room_only)
    assert np.nanmax(np.abs(all_bands_block - room_band_block)) > 0

    # The source table really was threaded through, and it was not silently
    # replaced by the family's own (room) rows.
    assert proper["slope_source_rows"] == len(rows)
    assert degenerate["slope_source_rows"] == len(room)

    degenerate_all = degenerate["arms"]["room_plus_emp_slope_leaky_all"]["fold_rows"]
    degenerate_room = degenerate["arms"]["room_plus_emp_slope_leaky_room"]["fold_rows"]
    assert _without_protocol(degenerate_all) == _without_protocol(degenerate_room)


def test_run_room_family_marks_a_compound_without_two_temperatures(
    tmp_path: Path,
) -> None:
    plan = {index: entries for index, entries in BAND_PLAN.items()}
    plan[2] = ((ROOM, 298.15, 2.4), (ROOM, 298.15, 2.35))
    rows = _v11_rows(tmp_path, plan)
    room = [row for row in rows if row["temperature_band"] == ROOM_BAND]
    family = run_room_family(
        room,
        read_alpha_table(_alpha_path(tmp_path)),
        slope_source_rows=rows,
        n_splits=3,
        n_repeats=1,
        seed=42,
    )
    assert family["empirical_slope_coverage"]["compounds_with_a_slope_over_all_bands"] == 7


# --------------------------------------------------------------------------- #
# Reference reproduction
# --------------------------------------------------------------------------- #


def _baseline_summary(value: float = 0.4) -> dict[str, dict[str, dict[str, float]]]:
    return {
        representation: {
            metric: {"mean": value, "std": 0.1, "n": 10}
            for metric in ("r2", "mae", "rmse", "spearman", "mae_lt20", "mae_20_60", "mae_gt60")
        }
        for representation in ("Morgan", "Physical", "Morgan+Physical")
    }


def test_reference_reproduction_flags_missing_sibling_summaries(tmp_path: Path) -> None:
    result = reference_reproduction(
        _baseline_summary(),
        band_summary_path=tmp_path / "absent_a.json",
        room_summary_path=tmp_path / "absent_b.json",
    )
    assert result["cells_compared"] == 0
    assert result["bit_exact_against_the_sibling_summaries"] is False
    assert result["references_missing"] == ["absent_a.json", "absent_b.json"]
    assert result["bit_exact_against_the_pinned_constant"] is False


def test_reference_reproduction_detects_a_single_bit_difference(tmp_path: Path) -> None:
    reference = _baseline_summary()
    reference["Physical"]["mae"]["mean"] = 0.4000001
    path = tmp_path / "band.json"
    path.write_text(
        json.dumps({"summary": {"band_room_only": reference}}), encoding="utf-8", newline="\n"
    )
    result = reference_reproduction(
        _baseline_summary(),
        band_summary_path=path,
        room_summary_path=tmp_path / "absent.json",
    )
    assert result["cells_compared"] == 21
    assert result["bit_exact_against_the_sibling_summaries"] is False
    assert result["max_abs_delta_vs_the_sibling_summaries"] > 0.0


def test_reference_reproduction_is_exact_when_every_cell_matches(tmp_path: Path) -> None:
    reference = _baseline_summary()
    path = tmp_path / "band.json"
    path.write_text(
        json.dumps({"summary": {"band_room_only": reference}}), encoding="utf-8", newline="\n"
    )
    result = reference_reproduction(
        _baseline_summary(),
        band_summary_path=path,
        room_summary_path=tmp_path / "absent.json",
    )
    assert result["bit_exact_against_the_sibling_summaries"] is True
    assert result["max_abs_delta_vs_the_sibling_summaries"] == 0.0


# --------------------------------------------------------------------------- #
# The command line end to end on synthetic inputs
# --------------------------------------------------------------------------- #


@pytest.fixture()
def synthetic_project(tmp_path: Path) -> dict[str, Path]:
    observations, features = _write_v11_tables(tmp_path)
    alpha = _alpha_path(tmp_path)
    frozen, dataset = _write_v10_tables(tmp_path)
    return {
        "observations": observations,
        "features": features,
        "alpha": alpha,
        "frozen": frozen,
        "dataset": dataset,
        "lowfreq": tmp_path / "no_such_lowfreq.csv",
        "summary": tmp_path / "out" / "summary.json",
        "report": tmp_path / "out" / "report.md",
        "artifacts": tmp_path / "out",
    }


def _cli_args(project: dict[str, Path], **flags: object) -> list[str]:
    args = [
        "--observations", str(project["observations"]),
        "--features", str(project["features"]),
        "--alpha-table", str(project["alpha"]),
        "--lowfreq", str(project["lowfreq"]),
        "--frozen-features", str(project["frozen"]),
        "--dataset", str(project["dataset"]),
        "--summary", str(project["summary"]),
        "--report", str(project["report"]),
        "--artifacts", str(project["artifacts"]),
        "--quick",
    ]
    for name, value in flags.items():
        flag = "--" + name.replace("_", "-")
        if value is True:
            args.append(flag)
        elif value is not None:
            args.extend([flag, str(value)])
    return args


def test_main_quick_writes_a_summary_report_and_artifacts(
    synthetic_project: dict[str, Path],
) -> None:
    assert main(_cli_args(synthetic_project)) == 0
    payload = json.loads(synthetic_project["summary"].read_text(encoding="utf-8"))
    assert payload["quick"] is True
    assert payload["protocol"]["random_row_used"] is False
    assert payload["seed"] == 42
    assert set(payload["coverage"]) == {
        "v11_observations",
        "v11_room_band",
        "v11_multi_temperature_compounds",
        "v10_pool",
    }
    room = payload["benchmark"]["room_family"]
    assert set(room["arms"]) == set(ALPHA_ARMS)
    assert room["arms"]["room_plus_nbs_alpha"]["extra_columns"] == 2
    assert room["arms"]["room_plus_emp_slope_leaky_all"]["extra_columns"] == 1
    # 17 room rows; the three compounds carrying a coefficient contribute 2+3+2
    assert room["nbs_alpha_block"]["rows_covered"] == 7
    v10 = payload["benchmark"]["v10_family"]
    assert set(v10["arms"]) == set(V10_ARMS)
    assert set(v10["arms"]) | set(room["arms"]) == set(ARM_ORDER)
    for arm, baseline in PAIRINGS:
        key = "room" if arm in ALPHA_ARMS else "v10"
        delta = payload["paired"][key][arm]
        assert delta["baseline"] == baseline
        assert delta["repeats"] == 2
    artifacts = synthetic_project["artifacts"]
    for name in (
        "dielectric_alpha_prior_crosscheck.csv",
        "dielectric_alpha_prior_empirical_slopes.csv",
        "dielectric_alpha_prior_feature_coverage.csv",
        "dielectric_alpha_prior_folds.csv",
        "dielectric_alpha_prior_repeats.csv",
        "dielectric_alpha_prior_predictions.csv",
    ):
        assert (artifacts / name).exists(), name
    assert b"\r" not in (artifacts / "dielectric_alpha_prior_folds.csv").read_bytes()
    report_bytes = synthetic_project["report"].read_bytes()
    assert b"\r" not in report_bytes
    report = report_bytes.decode("utf-8")
    assert "判决前置" in report
    assert "NBS Circular 514" in report
    assert "安慰块" in report


def test_main_render_report_is_deterministic(synthetic_project: dict[str, Path]) -> None:
    assert main(_cli_args(synthetic_project, no_report=True, skip_v10=True)) == 0
    payload = json.loads(synthetic_project["summary"].read_text(encoding="utf-8"))
    assert payload["outputs"]["report"] is None
    assert render_report(payload) == render_report(payload)
    assert not synthetic_project["report"].exists()


def test_main_skip_v10_omits_the_v10_family(synthetic_project: dict[str, Path]) -> None:
    assert main(_cli_args(synthetic_project, skip_v10=True)) == 0
    payload = json.loads(synthetic_project["summary"].read_text(encoding="utf-8"))
    assert payload["benchmark"]["v10_family"] is None
    assert payload["paired"]["v10"] == {}
    assert "v10_pool" not in payload["coverage"]


def test_main_records_the_input_fingerprints(synthetic_project: dict[str, Path]) -> None:
    assert main(_cli_args(synthetic_project, skip_v10=True)) == 0
    payload = json.loads(synthetic_project["summary"].read_text(encoding="utf-8"))
    assert payload["inputs"]
    for info in payload["inputs"].values():
        assert len(info["sha256"]) == 64
    assert file_sha256(synthetic_project["alpha"]) in {
        info["sha256"] for info in payload["inputs"].values()
    }


def test_the_alpha_arm_is_the_placebo_arm_when_coverage_is_zero(tmp_path: Path) -> None:
    rows = _v11_rows(tmp_path)
    room = [row for row in rows if row["temperature_band"] == ROOM_BAND]
    alpha = read_alpha_table(_alpha_path(tmp_path))
    for key in list(alpha):
        if key != "SYNTH0099-UHFFFAOYSA-N":
            del alpha[key]
    family = run_room_family(
        room, alpha, slope_source_rows=rows, n_splits=3, n_repeats=1, seed=42
    )
    assert family["nbs_alpha_block"]["rows_covered"] == 0
    real = family["arms"]["room_plus_nbs_alpha"]["repeat_rows"]
    placebo = family["arms"]["room_plus_null_block_two_columns"]["repeat_rows"]
    assert _without_protocol(real) == _without_protocol(placebo)
    assert _without_protocol(
        family["arms"]["room_plus_nbs_alpha"]["fold_rows"]
    ) == _without_protocol(family["arms"]["room_plus_null_block_two_columns"]["fold_rows"])


def test_import_performs_no_network_connection() -> None:
    code = (
        "import socket, sys\n"
        "def _blocked(*args, **kwargs):\n"
        "    raise AssertionError('network access during import')\n"
        "socket.socket.connect = _blocked\n"
        "socket.create_connection = _blocked\n"
        f"sys.path.insert(0, {str(REPOSITORY_ROOT / 'probes')!r})\n"
        f"sys.path.insert(0, {str(REPOSITORY_ROOT / 'src')!r})\n"
        "import dielectric_alpha_prior_probe as probe\n"
        "print(probe.ROOM_BAND)\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == ROOM_BAND


def test_the_module_source_contains_no_http_client() -> None:
    """Belt and braces next to the subprocess test: the probe is pure stdlib plus
    the frozen modelling stack, so there is nothing that could reach the network."""

    source = Path(alpha_probe.__file__).read_text(encoding="utf-8")
    for forbidden in ("import requests", "import urllib", "http.client", "socket."):
        assert forbidden not in source
