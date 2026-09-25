"""Regression tests for the pre-registered leave-EC-out sensitivity probe.

The probe answers "is the single out-of-window row, ethylene carbonate, doing
hidden work inside the frozen benchmark?".  These tests hold the answer still
and prove the guard actually fires.
"""

from __future__ import annotations

import csv
import hashlib
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "scripts"))
sys.path.insert(0, str(REPOSITORY_ROOT / "probes"))
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from verify_d1_leave_ec_out import (
    EC_INCHIKEY,
    FROZEN_PREDICTIONS_PATH,
    PREDICTIONS_PATH,
    SUMMARY_PATH,
    verify,
)

DATASET = REPOSITORY_ROOT / "data" / "dielectric_v03.csv"
FROZEN_DATASET_SHA256 = (
    "ff2142936e06e04b329b70f8597574f75349e54ce876e9fff81309e6d35ccce4"
)
PROBE_SCRIPT = REPOSITORY_ROOT / "probes" / "dielectric_leave_ec_out_sensitivity.py"
PROBE_SUMMARY = REPOSITORY_ROOT / "probes" / "dielectric_leave_ec_out_summary.json"


def _summary() -> dict[str, object]:
    return json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))


def _stage(tmp_path: Path, summary: dict[str, object]) -> Path:
    root = tmp_path / "repo"
    (root / "probes" / "artifacts").mkdir(parents=True)
    (root / "data" / "processed").mkdir(parents=True)
    for source, relative in (
        (PREDICTIONS_PATH, "probes/artifacts/dielectric_leave_ec_out_predictions.csv"),
        (FROZEN_PREDICTIONS_PATH, "data/processed/v032_ablation_predictions.csv"),
        (REPOSITORY_ROOT / "data" / "dielectric_v03.csv", "data/dielectric_v03.csv"),
        (
            REPOSITORY_ROOT
            / "data"
            / "processed"
            / "dielectric_physical_features_v03.csv",
            "data/processed/dielectric_physical_features_v03.csv",
        ),
    ):
        target = root / relative
        target.write_bytes(source.read_bytes())
    (root / "probes" / "dielectric_leave_ec_out_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return root


def test_the_probe_is_present_and_pre_registers_its_decision_rule() -> None:
    text = PROBE_SCRIPT.read_text(encoding="utf-8")
    assert "Pre-registered decision rule" in text
    assert "cannot\n  trigger a post-hoc model switch" in text or (
        "cannot" in text and "post-hoc model switch" in text
    )


def test_ec_is_held_out_in_every_repeat_and_never_trains() -> None:
    summary = _summary()
    assert summary["removed_inchikey"] == EC_INCHIKEY
    assert summary["removed_temperature_band"] == "extended_temperature"
    assert summary["removed_temperature_K"] == 313.15
    assert summary["ec_in_training_folds"] == 0
    assert summary["ec_holdout_repeats"] == 10
    assert summary["ec_training_removals"] == 40
    assert summary["baseline_fit_count"] == 236
    assert summary["leave_ec_out_fit_count"] == 235


def test_the_probe_stays_report_only() -> None:
    summary = _summary()
    assert summary["selection_effect"] == "none"
    assert summary["model_selection_impact"] == "none"


def test_the_baseline_arm_reproduced_the_frozen_benchmark() -> None:
    summary = _summary()
    assert summary["baseline_matches_frozen_predictions"] is True
    assert summary["frozen_prediction_rows_checked"] == 7080


def test_removing_ec_does_not_reorder_the_metric_ranking() -> None:
    summary = _summary()
    for representation in ("Morgan", "Physical", "Morgan+Physical"):
        block = summary["metrics"][representation]
        assert block["ranking_changed"] is False
        assert block["metric_ranking_baseline"] == block["metric_ranking_leave_ec_out"]


def test_removing_ec_does_not_move_the_hybrid_headline_beyond_noise() -> None:
    summary = _summary()
    paired = summary["metrics"]["Morgan+Physical"][
        "paired_leave_ec_out_minus_baseline_235"
    ]
    # The v1.0 headline is R2 ~ 0.35 on the 236-row table; deleting the only
    # out-of-window row must not move it by more than a tenth of a point.
    assert abs(paired["r2"]["delta_mean"]) < 0.1
    assert paired["r2"]["delta_ci95"][0] < 0.0 < paired["r2"]["delta_ci95"][1] or (
        paired["r2"]["paired_t_pvalue"] > 0.01
    )


def test_ec_is_ranked_as_an_outlier_but_compressed() -> None:
    summary = _summary()
    for representation in ("Morgan", "Physical", "Morgan+Physical"):
        block = summary["ec_leave_one_out"][representation]
        assert block["target"] == 90.5
        # The model recognises EC as an extreme member of the table ...
        assert block["rank_percentile_among_235"] > 90.0
        # ... but compresses its magnitude by a large factor.
        assert block["prediction_mean"] < 0.75 * block["target"]


def test_committed_artefacts_pass_the_verifier() -> None:
    report = verify()
    assert report["passed"], json.dumps(report, ensure_ascii=False)[:800]
    assert report["passed_count"] == report["check_count"]


def test_verifier_rejects_a_summary_that_claims_a_selection_effect(
    tmp_path: Path,
) -> None:
    summary = _summary()
    summary["selection_effect"] = "model_switch"
    root = _stage(tmp_path, summary)
    report = verify(
        summary_path=root / "probes" / "dielectric_leave_ec_out_summary.json",
        predictions_path=root
        / "probes"
        / "artifacts"
        / "dielectric_leave_ec_out_predictions.csv",
        frozen_predictions_path=root / "data" / "processed" / "v032_ablation_predictions.csv",
    )
    assert not report["passed"]


def test_verifier_rejects_a_tampered_paired_delta(tmp_path: Path) -> None:
    summary = _summary()
    summary["metrics"]["Morgan+Physical"]["paired_leave_ec_out_minus_baseline_235"][
        "r2"
    ]["delta_mean"] = 0.5
    root = _stage(tmp_path, summary)
    report = verify(
        summary_path=root / "probes" / "dielectric_leave_ec_out_summary.json",
        predictions_path=root
        / "probes"
        / "artifacts"
        / "dielectric_leave_ec_out_predictions.csv",
        frozen_predictions_path=root / "data" / "processed" / "v032_ablation_predictions.csv",
    )
    assert not report["passed"]


def test_verifier_rejects_a_prediction_table_that_drops_the_ec_row(
    tmp_path: Path,
) -> None:
    root = _stage(tmp_path, _summary())
    table = root / "probes" / "artifacts" / "dielectric_leave_ec_out_predictions.csv"
    with table.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = list(reader.fieldnames or [])
        rows = [row for row in reader if row["inchikey"] != EC_INCHIKEY]
    with table.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    report = verify(
        summary_path=root / "probes" / "dielectric_leave_ec_out_summary.json",
        predictions_path=table,
        frozen_predictions_path=root / "data" / "processed" / "v032_ablation_predictions.csv",
    )
    assert not report["passed"]


def test_verifier_rejects_a_missing_paired_field(tmp_path: Path) -> None:
    summary = _summary()
    del summary["metrics"]["Morgan+Physical"]["paired_leave_ec_out_minus_baseline_235"][
        "r2"
    ]["baseline_mean"]
    root = _stage(tmp_path, summary)
    report = verify(
        summary_path=root / "probes" / "dielectric_leave_ec_out_summary.json",
        predictions_path=root
        / "probes"
        / "artifacts"
        / "dielectric_leave_ec_out_predictions.csv",
        frozen_predictions_path=root / "data" / "processed" / "v032_ablation_predictions.csv",
    )
    assert not report["passed"]


def test_verifier_rejects_a_non_finite_published_value(tmp_path: Path) -> None:
    summary = _summary()
    summary["metrics"]["Morgan+Physical"]["paired_leave_ec_out_minus_baseline_235"][
        "r2"
    ]["delta_mean"] = float("nan")
    root = _stage(tmp_path, summary)
    report = verify(
        summary_path=root / "probes" / "dielectric_leave_ec_out_summary.json",
        predictions_path=root
        / "probes"
        / "artifacts"
        / "dielectric_leave_ec_out_predictions.csv",
        frozen_predictions_path=root / "data" / "processed" / "v032_ablation_predictions.csv",
    )
    assert not report["passed"]


def test_verifier_rejects_a_tampered_confidence_interval(tmp_path: Path) -> None:
    summary = _summary()
    summary["metrics"]["Morgan+Physical"]["paired_leave_ec_out_minus_baseline_235"][
        "r2"
    ]["delta_ci95"] = [999.0, 1000.0]
    root = _stage(tmp_path, summary)
    report = verify(
        summary_path=root / "probes" / "dielectric_leave_ec_out_summary.json",
        predictions_path=root
        / "probes"
        / "artifacts"
        / "dielectric_leave_ec_out_predictions.csv",
        frozen_predictions_path=root / "data" / "processed" / "v032_ablation_predictions.csv",
    )
    assert not report["passed"]


def test_verifier_rejects_a_tampered_ec_statistic(tmp_path: Path) -> None:
    summary = _summary()
    summary["ec_leave_one_out"]["Morgan+Physical"]["prediction_std"] = 777.0
    root = _stage(tmp_path, summary)
    report = verify(
        summary_path=root / "probes" / "dielectric_leave_ec_out_summary.json",
        predictions_path=root
        / "probes"
        / "artifacts"
        / "dielectric_leave_ec_out_predictions.csv",
        frozen_predictions_path=root / "data" / "processed" / "v032_ablation_predictions.csv",
    )
    assert not report["passed"]


def test_verifier_rejects_a_tampered_family_ranking(tmp_path: Path) -> None:
    summary = _summary()
    summary["family_ranking"]["baseline"]["r2"] = ["Morgan", "Physical", "Morgan+Physical"]
    root = _stage(tmp_path, summary)
    report = verify(
        summary_path=root / "probes" / "dielectric_leave_ec_out_summary.json",
        predictions_path=root
        / "probes"
        / "artifacts"
        / "dielectric_leave_ec_out_predictions.csv",
        frozen_predictions_path=root / "data" / "processed" / "v032_ablation_predictions.csv",
    )
    assert not report["passed"]


def test_verifier_rejects_a_tampered_fold(tmp_path: Path) -> None:
    root = _stage(tmp_path, _summary())
    table = root / "probes" / "artifacts" / "dielectric_leave_ec_out_predictions.csv"
    with table.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = list(reader.fieldnames or [])
        rows = list(reader)
    for row in rows:
        if row["arm"] == "leave_ec_out" and row["inchikey"] != EC_INCHIKEY:
            row["fold"] = "99"
            break
    with table.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    report = verify(
        summary_path=root / "probes" / "dielectric_leave_ec_out_summary.json",
        predictions_path=table,
        frozen_predictions_path=root / "data" / "processed" / "v032_ablation_predictions.csv",
    )
    assert not report["passed"]


def test_verifier_returns_a_failed_report_when_a_whole_group_is_missing(
    tmp_path: Path,
) -> None:
    root = _stage(tmp_path, _summary())
    table = root / "probes" / "artifacts" / "dielectric_leave_ec_out_predictions.csv"
    with table.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = list(reader.fieldnames or [])
        rows = [
            row
            for row in reader
            if not (
                row["representation"] == "Morgan"
                and row["repeat"] == "0"
                and row["arm"] == "leave_ec_out"
            )
        ]
    with table.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    report = verify(
        summary_path=root / "probes" / "dielectric_leave_ec_out_summary.json",
        predictions_path=table,
        frozen_predictions_path=root / "data" / "processed" / "v032_ablation_predictions.csv",
    )
    assert not report["passed"]
    assert report["check_count"] == 8


def test_run_probe_never_passes_ec_into_a_treatment_fit(
    tmp_path: Path, monkeypatch
) -> None:
    import dielectric_leave_ec_out_sensitivity as probe
    import numpy as np
    from dielectric_leave_ec_out_sensitivity import (
        N_REPEATS,
        N_SPLITS,
        REPRESENTATIONS,
    )

    count = 236
    keys = [EC_INCHIKEY] + [f"FAKE-{index:04d}" for index in range(count - 1)]
    rows = [
        {
            "inchikey": key,
            "name": "ethylene carbonate" if key == EC_INCHIKEY else f"fake {key}",
            "dielectric": "1.0",
            "smiles": "C",
            "T_K": "313.15" if key == EC_INCHIKEY else "298.15",
        }
        for key in keys
    ]
    dataset = tmp_path / "dataset.csv"
    dataset.write_text(
        "inchikey,T_K,temperature_band\n"
        + "\n".join(
            (
                f"{key},313.15,extended_temperature"
                if key == EC_INCHIKEY
                else f"{key},298.15,room_temperature"
            )
            for key in keys
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    frozen = tmp_path / "frozen.csv"
    frozen_rows = [
        {
            "representation": representation,
            "repeat": str(repeat),
            "fold": "0",
            "inchikey": key,
            "prediction": "0",
        }
        for representation in REPRESENTATIONS
        for repeat in range(N_REPEATS)
        for key in keys
    ]
    with frozen.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=("representation", "repeat", "fold", "inchikey", "prediction"),
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(frozen_rows)
    features = tmp_path / "features.csv"
    features.write_text("inchikey\n", encoding="utf-8", newline="\n")

    calls: list[tuple[str, tuple[int, ...]]] = []

    def fake_fit(representation, *, morgan, physical, target, train_indices, test_indices, seed):
        calls.append((representation, tuple(int(index) for index in train_indices)))
        return np.zeros(len(test_indices), dtype=float), None

    monkeypatch.setattr(probe, "read_modelling_rows", lambda *args, **kwargs: (rows, [], []))
    monkeypatch.setattr(probe, "morgan_count_features", lambda smiles: np.zeros((len(smiles), 1)))
    monkeypatch.setattr(probe, "physical_feature_matrix", lambda rows: np.zeros((len(rows), 1)))
    monkeypatch.setattr(probe, "fit_predict_representation", fake_fit)
    monkeypatch.setattr(
        probe,
        "evaluate_repeat",
        lambda target, prediction: {metric: 0.0 for metric in ("r2", "mae", "rmse", "spearman")},
    )

    payload, _ = probe.run_probe(
        features_path=features,
        dataset_path=dataset,
        exclusions_path=tmp_path / "missing_exclusions.csv",
        frozen_predictions_path=frozen,
    )

    treatment_calls = calls[1::2]
    assert len(treatment_calls) == N_REPEATS * N_SPLITS * len(REPRESENTATIONS)
    assert all(0 not in train_indices for _, train_indices in treatment_calls)
    assert payload["ec_in_training_folds"] == 0
    assert payload["ec_training_removals"] == N_REPEATS * (N_SPLITS - 1)
    assert payload["same_fold_ids_for_235"] is True
    assert payload["family_ranking"]["changed"] is False


def test_the_probe_never_moved_the_frozen_dataset() -> None:
    digest = hashlib.sha256(DATASET.read_bytes()).hexdigest()
    assert digest == FROZEN_DATASET_SHA256
    assert PROBE_SUMMARY.is_file()