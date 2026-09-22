from __future__ import annotations

from scripts.verify_p4_redox import (
    check_308_status,
    check_formula_recomputation,
    check_h5_rows,
    check_merged_counts,
    check_merged_hash,
    check_metrics_from_predictions,
    check_model_configs,
)


def test_verifier_rejects_formula_tamper() -> None:
    raw_rows = [
        {
            "raw_EA": -2.0,
            "oxidation_potential": 1.0,
            "reduction_potential": -1.0,
        }
    ]
    merged_rows = [
        {
            "EA": "1.5",
            "oxidation_free_energy": "5.44",
            "reduction_free_energy": "-3.44",
        }
    ]

    result = check_formula_recomputation(raw_rows, merged_rows)

    assert result.passed is False
    assert "EA" in result.detail


def test_verifier_rejects_canonical_structure_tamper() -> None:
    raw_rows = [
        {
            "row_id": "rx392:one",
            "smiles": "CCO",
            "inchikey": "LFQSCWFLJHTTHZ-UHFFFAOYSA-N",
            "raw_EA": -2.0,
            "oxidation_potential": 1.0,
            "reduction_potential": -1.0,
        }
    ]
    merged_rows = [
        {
            "row_id": "rx392:one",
            "smiles": "CO",
            "inchikey": "LFQSCWFLJHTTHZ-UHFFFAOYSA-N",
            "EA": "2.0",
            "oxidation_free_energy": "5.44",
            "reduction_free_energy": "-3.44",
        }
    ]

    result = check_formula_recomputation(raw_rows, merged_rows)

    assert result.passed is False
    assert "smiles" in result.detail


def test_verifier_rejects_merged_count_mismatch() -> None:
    result = check_merged_counts(
        rows=[
            {"source": "RX-392"},
            {"source": "Batt-P30K"},
        ],
        expected_rx=392,
        expected_p30k=29519,
    )

    assert result.passed is False
    assert "RX-392" in result.detail


def test_verifier_rejects_metric_mismatch() -> None:
    rows = [
        {
            "target_name": "oxidation_free_energy",
            "model": "linear",
            "split": "test",
            "used_for_metrics": "true",
            "target": "1.0",
            "prediction": "2.0",
        }
    ]
    summary = {
        "metrics": {
            "oxidation_free_energy": {
                "linear": {"mae": 0.0, "rmse": 0.0, "r2": 1.0}
            }
        }
    }

    result = check_metrics_from_predictions(rows, summary)

    assert result.passed is False
    assert "mismatch" in result.detail


def test_verifier_requires_308_unavailable_status() -> None:
    assert check_308_status({"status": "available"}).passed is False
    assert check_308_status({"status": "unavailable", "rows": 0}).passed is True


def test_verifier_skips_missing_h5_explicitly(tmp_path) -> None:
    result = check_h5_rows(tmp_path / "missing.h5")

    assert result.passed is True
    assert "skipped" in result.detail


def test_verifier_rejects_merged_hash_mismatch(tmp_path) -> None:
    path = tmp_path / "merged.csv"
    path.write_text("a\n", encoding="utf-8")

    result = check_merged_hash({"merged": {"sha256": "0" * 64}}, path)

    assert result.passed is False
    assert "SHA256" in result.detail


def test_verifier_rejects_model_config_tamper() -> None:
    summary = {
        "model_configs": {
            "oxidation_free_energy:linear": "LinearRegression; random_state=42",
            "oxidation_free_energy:scalar_gpr": "random_state=42",
            "oxidation_free_energy:fingerprint_gpr": (
                "initial_kernel=x; final_kernel=y; random_state=42"
            ),
            "reduction_free_energy:linear": "LinearRegression; random_state=42",
            "reduction_free_energy:scalar_gpr": (
                "initial_kernel=x; final_kernel=y; random_state=42"
            ),
            "reduction_free_energy:fingerprint_gpr": (
                "initial_kernel=x; final_kernel=y; random_state=42"
            ),
        }
    }

    result = check_model_configs(summary)

    assert result.passed is False
    assert "scalar_gpr" in result.detail
