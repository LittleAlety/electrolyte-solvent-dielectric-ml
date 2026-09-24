"""Regression tests for the v0.3.2/v0.3.3 benchmark gate verifier."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from scripts.verify_v032_benchmarks import REPOSITORY_ROOT, verify

NEEDED = (
    "data/dielectric_v03.csv",
    "data/processed/v032_ablation_predictions.csv",
    "data/processed/dielectric_v03_representation_ablation_predictions.csv",
    "data/processed/v032_scaffold_folds.csv",
    "data/processed/v032_target_scaffold_predictions.csv",
    "data/processed/v032_target_scaffold_metrics.csv",
    "probes/v032_controlled_comparison_repeats_oof.csv",
    "probes/v032_ablation_summary.json",
    "probes/dielectric_v03_representation_ablation_summary.json",
    "probes/v032_controlled_comparison_summary.json",
    "probes/v032_target_scaffold_summary.json",
    "data/processed/dielectric_physical_features_v03.csv",
    "data/processed/dielectric_v03_exclusions.csv",
    "data/interim/v03_features_original.csv",
)


def _stage(tmp_path: Path) -> Path:
    for relative in NEEDED:
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPOSITORY_ROOT / relative, destination)
    return tmp_path


def test_the_committed_benchmark_artifacts_pass() -> None:
    result = verify(REPOSITORY_ROOT)
    assert result["passed"], [
        check for check in result["checks"] if not check["passed"]
    ]
    assert result["check_count"] >= 27


def test_a_stale_recorded_dataset_hash_is_rejected(tmp_path: Path) -> None:
    root = _stage(tmp_path)
    summary = root / "probes" / "v032_ablation_summary.json"
    summary.write_text(
        summary.read_text(encoding="utf-8").replace(
            "f5256d164c814030a4b986db6c878f1d64edb2b4f91cf39af3a75ffeaeac853c",
            "0" * 64,
        ),
        encoding="utf-8",
    )
    result = verify(root)
    assert not result["passed"]
    assert any(
        "v0.3.2 dataset hash" in check["name"] and not check["passed"]
        for check in result["checks"]
    )


def test_a_leaked_withheld_row_is_rejected(tmp_path: Path) -> None:
    root = _stage(tmp_path)
    predictions = root / "data" / "processed" / "v032_ablation_predictions.csv"
    lines = predictions.read_text(encoding="utf-8").splitlines()
    header = lines[0]
    leaked = (
        "Morgan,0,0,VAYTZRYEBVHVLE-UHFFFAOYSA-N,vinylene carbonate,"
        "C=C1OC(=O)O1,300.0,127.0,20.0,107.0,low"
    )
    predictions.write_text(
        "\n".join([header, *lines[1:], leaked]) + "\n", encoding="utf-8"
    )
    result = verify(root)
    assert not result["passed"]
    assert any(
        "model_ready gate completeness" in check["name"] and not check["passed"]
        for check in result["checks"]
    )


def test_a_tampered_scaffold_summary_is_rejected(tmp_path: Path) -> None:
    root = _stage(tmp_path)
    summary = root / "probes" / "v032_target_scaffold_summary.json"
    payload = json.loads(summary.read_text(encoding="utf-8"))
    block = payload["summary"]["scaffold_cluster_5fold"]["raw"]["Physical"]["r2"]
    assert block["mean"] == pytest.approx(0.2677824646044)
    block["mean"] = 0.99
    summary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    result = verify(root)
    assert not result["passed"]
    assert any(
        "scaffold summary reproduction" in check["name"] and not check["passed"]
        for check in result["checks"]
    )


def test_a_tampered_controlled_mae_delta_is_rejected(tmp_path: Path) -> None:
    root = _stage(tmp_path)
    summary = root / "probes" / "v032_controlled_comparison_summary.json"
    payload = json.loads(summary.read_text(encoding="utf-8"))
    recorded = payload["paired_deltas"]["Morgan+Physical"]["mae"]
    assert recorded["delta_mean"] == pytest.approx(0.03224684458023495)
    recorded["delta_mean"] = 9.99
    summary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    result = verify(root)
    assert not result["passed"]
    assert any(
        "controlled comparison Morgan+Physical mae" in check["name"] and not check["passed"]
        for check in result["checks"]
    )


def test_an_emptied_scaffold_summary_is_rejected(tmp_path: Path) -> None:
    """An empty or truncated summary must not satisfy the schema check."""

    root = _stage(tmp_path)
    summary = root / "probes" / "v032_target_scaffold_summary.json"
    payload = json.loads(summary.read_text(encoding="utf-8"))
    payload["summary"] = {}
    summary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    result = verify(root)
    assert not result["passed"]
    assert any(
        "scaffold benchmark schema" in check["name"] and not check["passed"]
        for check in result["checks"]
    )


def test_a_dropped_scaffold_metric_is_rejected(tmp_path: Path) -> None:
    root = _stage(tmp_path)
    summary = root / "probes" / "v032_target_scaffold_summary.json"
    payload = json.loads(summary.read_text(encoding="utf-8"))
    metrics = payload["summary"]["scaffold_cluster_5fold"]["raw"]["Physical"]
    assert "auc_gt15" in metrics
    del metrics["auc_gt15"]
    summary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    result = verify(root)
    assert not result["passed"]
    assert any(
        "scaffold benchmark schema" in check["name"] and not check["passed"]
        for check in result["checks"]
    )


def test_a_stale_recorded_input_hash_is_rejected(tmp_path: Path) -> None:
    root = _stage(tmp_path)
    summary = root / "probes" / "v032_target_scaffold_summary.json"
    payload = json.loads(summary.read_text(encoding="utf-8"))
    payload["input_sha256"] = "0" * 64
    summary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    result = verify(root)
    assert not result["passed"]
    assert any(
        "recorded input hashes" in check["name"] and not check["passed"]
        for check in result["checks"]
    )
