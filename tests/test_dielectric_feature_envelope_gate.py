"""Guards for the Week 14 feature-envelope applicability gate.

The gate exists because Week 13's L3 pilot scored EC and PC at 23.1 and 17.0
against truths of 90.5 and 64.9 and *no* gate fired: the only applicability rule
in the repository is structural (a hydrogen-bond donor count) and a carbonate
has no donor.  These tests pin the replacement on four axes -- the numbers the
two rules produce, the fact that they cannot see a target, the pool freeze, and
the on-disk artifacts being LF-only and re-derivable.
"""

from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from electrolyte_ml.exporting import sha256_file
from probes.dielectric_feature_envelope_gate import (
    DESCRIPTORS,
    EC_PC_CSV_PATH,
    ENVELOPE_CSV_PATH,
    FENCE_K,
    KNN_PERCENTILE,
    MAX_SECONDARY_FLAG_RATE,
    POOL_LOO_CSV_PATH,
    POOL_PATH,
    POOL_SHA256,
    PREREG_PATH,
    PRIMARY_CHAMPIONS,
    REPORT_PATH,
    SUMMARY_PATH,
    descriptor_envelope,
    knn_distance,
    knn_fence,
    load_descriptors,
    load_pool,
    load_prereg,
    rule_a_hits,
    run_gate,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
GATE_SCRIPT = REPOSITORY_ROOT / "probes" / "dielectric_feature_envelope_gate.py"
FEATURES_PATH = (
    REPOSITORY_ROOT / "data" / "processed" / "dielectric_physical_features_v03.csv"
)
CHAMPION_KEYS = {key for _, key in PRIMARY_CHAMPIONS}


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


@pytest.fixture(scope="module")
def pool() -> list[dict[str, str]]:
    return load_pool()


@pytest.fixture(scope="module")
def features() -> dict[str, list[float]]:
    vectors, _source, _incomplete = load_descriptors()
    return vectors


@pytest.fixture(scope="module")
def result(pool, features) -> dict:
    return run_gate(pool, features, {})


@pytest.fixture(scope="module")
def summary() -> dict:
    return json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def loo_rows() -> list[dict[str, str]]:
    return _rows(POOL_LOO_CSV_PATH)


@pytest.fixture(scope="module")
def held_out_rows() -> list[dict[str, str]]:
    return _rows(EC_PC_CSV_PATH)


def _train_matrix(pool, features):
    kept = [row["inchikey"] for row in pool if row["inchikey"] not in CHAMPION_KEYS]
    return np.asarray([features[key] for key in kept], dtype=float)


# --------------------------------------------------------------------------- #
# frozen inputs
# --------------------------------------------------------------------------- #


def test_pool_digest_is_the_frozen_one(pool) -> None:
    assert sha256_file(POOL_PATH) == POOL_SHA256
    assert len(pool) == 236
    assert len({row["inchikey"] for row in pool}) == 236


def test_prereg_is_locked_and_the_constants_are_copied_not_chosen() -> None:
    prereg = load_prereg()
    assert prereg["status"] == "locked_before_run"
    assert prereg["rules"][0]["k"] == FENCE_K == 1.5
    assert prereg["rules"][1]["percentile"] == KNN_PERCENTILE == 95.0


def test_every_pool_member_has_the_eight_descriptors(pool, features) -> None:
    assert set(features) >= {row["inchikey"] for row in pool}
    for key in CHAMPION_KEYS:
        assert len(features[key]) == len(DESCRIPTORS)


def test_run_gate_refuses_a_pool_member_without_descriptors(pool, features) -> None:
    trimmed = dict(features)
    del trimmed[PRIMARY_CHAMPIONS[0][1]]
    with pytest.raises(ValueError):
        run_gate(pool, trimmed, {})


# --------------------------------------------------------------------------- #
# rule A -- the interval fence
# --------------------------------------------------------------------------- #


def test_rule_a_envelope_is_median_plus_minus_k_iqr(pool, features) -> None:
    matrix = _train_matrix(pool, features)
    median, q1, q3, iqr = descriptor_envelope(matrix)
    for index, _name in enumerate(DESCRIPTORS):
        column = matrix[:, index]
        assert median[index] == pytest.approx(float(np.median(column)))
        assert q1[index] == pytest.approx(float(np.percentile(column, 25)))
        assert q3[index] == pytest.approx(float(np.percentile(column, 75)))
        assert iqr[index] == pytest.approx(float(q3[index] - q1[index]))


def test_rule_a_fences_the_two_carbonates_on_dipole_and_mu_squared_over_vm(
    pool, features
) -> None:
    matrix = _train_matrix(pool, features)
    median, _q1, _q3, iqr = descriptor_envelope(matrix)
    for _short, key in PRIMARY_CHAMPIONS:
        value = np.asarray(features[key], dtype=float)
        hits = rule_a_hits(value, median, iqr)
        assert {hit["descriptor"] for hit in hits} == {"dipole_D", "mu_sq_over_Vm"}
        for hit in hits:
            index = DESCRIPTORS.index(hit["descriptor"])
            assert hit["value"] == pytest.approx(value[index])
            assert hit["fence_low"] == pytest.approx(median[index] - FENCE_K * iqr[index])
            assert hit["fence_high"] == pytest.approx(median[index] + FENCE_K * iqr[index])
            assert hit["iqr_units"] == pytest.approx(
                (value[index] - median[index]) / iqr[index]
            )
            assert (
                value[index] < hit["fence_low"] - 1e-9
                or value[index] > hit["fence_high"] + 1e-9
            )


def test_rule_a_leaves_an_in_fence_descriptor_alone(pool, features) -> None:
    matrix = _train_matrix(pool, features)
    median, _q1, _q3, iqr = descriptor_envelope(matrix)
    assert rule_a_hits(np.asarray(median), median, iqr) == []


# --------------------------------------------------------------------------- #
# rule B -- the kNN distance fence
# --------------------------------------------------------------------------- #


def test_rule_b_threshold_is_the_training_loo_95th_percentile(pool, features) -> None:
    matrix = _train_matrix(pool, features)
    _mean, _std, _z, threshold, loo = knn_fence(matrix)
    assert threshold == pytest.approx(float(np.percentile(loo, KNN_PERCENTILE)))


def test_rule_b_distances_match_the_recorded_artifact(pool, features, held_out_rows) -> None:
    matrix = _train_matrix(pool, features)
    mean, std, z, threshold, _loo = knn_fence(matrix)
    recorded = {row["champion"]: row for row in held_out_rows}
    for short, key in PRIMARY_CHAMPIONS:
        distance = knn_distance(np.asarray(features[key], dtype=float), mean, std, z)
        assert distance == pytest.approx(float(recorded[short]["rule_b_nn_distance"]))
    assert threshold == pytest.approx(float(held_out_rows[0]["rule_b_threshold"]))


def test_rule_b_does_not_flag_the_carbonates_and_that_is_recorded(
    held_out_rows,
) -> None:
    for row in held_out_rows:
        assert row["rule_b_flagged"] == "False"
        assert float(row["rule_b_nn_distance"]) < float(row["rule_b_threshold"])


# --------------------------------------------------------------------------- #
# the criteria
# --------------------------------------------------------------------------- #


def test_primary_check_raises_both_targets(result) -> None:
    for short in ("EC", "PC"):
        assert result["primary"][short]["flagged"] is True
        assert result["primary"][short]["rule_a_flagged"] is True
    assert result["criteria"]["primary_met"] is True
    assert result["criteria"]["unflagged_targets"] == []


def test_secondary_rate_is_combined_and_reported_honestly(result, summary, loo_rows) -> None:
    readings = result["readings"]
    # the two rules overlap, so the union is bounded by the sum and floored by
    # whichever rule fired on its own
    assert max(
        readings["secondary_rule_a_flags"], readings["secondary_rule_b_flags"]
    ) <= readings["secondary_any_flags"] <= (
        readings["secondary_rule_a_flags"] + readings["secondary_rule_b_flags"]
    )
    assert readings["secondary_any_rate"] == pytest.approx(
        readings["secondary_any_flags"] / readings["secondary_total_rows"]
    )
    assert readings["secondary_any_flags"] == sum(
        row["flagged_any"] == "True" for row in loo_rows
    )
    assert summary["secondary_check"]["criterion_uses"].startswith("combined")
    assert summary["criteria"]["secondary_met"] == (
        readings["secondary_any_rate"] <= MAX_SECONDARY_FLAG_RATE
    )
    assert summary["criteria"]["kill_line_triggered"] == (
        readings["secondary_any_rate"] > 0.50
    )


def test_summary_keeps_the_verdict_it_computed(summary) -> None:
    criteria = summary["criteria"]
    if criteria["primary_met"] and criteria["secondary_met"]:
        assert criteria["verdict"] == "pass"
    elif criteria["kill_line_triggered"]:
        assert criteria["verdict"] == "kill_line_triggered"
    elif criteria["primary_met"]:
        assert criteria["verdict"] == "primary_met_secondary_not_met"
    else:
        assert criteria["verdict"] == "targets_missed"


# --------------------------------------------------------------------------- #
# no target leakage
# --------------------------------------------------------------------------- #


def test_the_rules_never_read_a_target(pool, features, result) -> None:
    scrambled = []
    for row in pool:
        row = dict(row)
        row["target_dielectric"] = "999.0"
        row["T_K"] = "1.0"
        scrambled.append(row)
    after = run_gate(scrambled, features, {})
    for short in ("EC", "PC"):
        assert after["primary"][short]["flagged"] == result["primary"][short]["flagged"]
        assert after["primary"][short]["rule_a_hits"] == result["primary"][short]["rule_a_hits"]
        assert after["primary"][short]["rule_b_nn_distance"] == pytest.approx(
            result["primary"][short]["rule_b_nn_distance"]
        )
    assert [row["flagged_any"] for row in after["loo_rows"]] == [
        row["flagged_any"] for row in result["loo_rows"]
    ]


def test_removing_the_target_columns_entirely_changes_nothing(pool, features, result) -> None:
    stripped = [
        {key: value for key, value in row.items() if key not in {"target_dielectric", "T_K"}}
        for row in pool
    ]
    after = run_gate(stripped, features, {})
    assert [row["flagged_any"] for row in after["loo_rows"]] == [
        row["flagged_any"] for row in result["loo_rows"]
    ]


# --------------------------------------------------------------------------- #
# on-disk artifacts
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "path", [ENVELOPE_CSV_PATH, POOL_LOO_CSV_PATH, EC_PC_CSV_PATH]
)
def test_artifacts_are_lf_only_without_bom(path: Path) -> None:
    raw = path.read_bytes()
    assert b"\r\n" not in raw
    assert not raw.startswith(b"\xef\xbb\xbf")


def test_loo_artifact_has_one_row_per_pool_member(loo_rows, pool) -> None:
    assert len(loo_rows) == len(pool) == 236
    assert {row["inchikey"] for row in loo_rows} == {row["inchikey"] for row in pool}
    assert sum(row["flagged_any"] == "True" for row in loo_rows) == 80


def test_held_out_artifact_carries_the_smarts_contrast(held_out_rows) -> None:
    assert [row["champion"] for row in held_out_rows] == ["EC", "PC"]
    for row in held_out_rows:
        assert row["smarts_donor_count"] == "0"
        assert row["smarts_structural_gate_fires"] == "False"
        assert row["training_rows"] == "234"


def test_report_states_the_honest_boundaries() -> None:
    text = REPORT_PATH.read_text(encoding="utf-8")
    assert "236-compound pilot pool" in text
    assert "29.5k" in text
    assert "does not rank" in text
    assert "no donor site cannot fire on a carbonate" in text or "cannot fire on a carbonate" in text


def test_summary_pins_are_flat_and_resolvable_by_the_repo_guard(summary) -> None:
    assert summary["pool_sha256"] == sha256_file(POOL_PATH) == POOL_SHA256
    assert summary["prereg_sha256"] == sha256_file(PREREG_PATH)
    assert summary["features_v03_sha256"] == sha256_file(FEATURES_PATH)
    for stem in ("pool", "prereg", "features_v03"):
        target = REPOSITORY_ROOT / summary[f"{stem}_path"]
        assert target.is_file()


def test_recompute_is_deterministic() -> None:
    completed = subprocess.run(
        [sys.executable, str(GATE_SCRIPT), "--check"],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "summary matches" in completed.stdout