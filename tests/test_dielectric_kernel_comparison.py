from __future__ import annotations

import numpy as np
import pytest

from probes.dielectric_kernel_comparison import (
    summarize_metric_rows,
    tanimoto_kernel,
)


def test_tanimoto_kernel_matches_manual_intersection_over_union() -> None:
    fingerprints = np.asarray(
        [
            [1, 1, 0],
            [1, 0, 1],
            [0, 0, 0],
        ],
        dtype=np.uint8,
    )

    kernel = tanimoto_kernel(fingerprints)

    assert kernel[0, 1] == pytest.approx(1 / 3)
    assert kernel[0, 0] == 1.0
    assert kernel[2, 0] == 0.0
    np.testing.assert_allclose(kernel, kernel.T)


def test_summarize_metric_rows_reports_mean_and_std() -> None:
    rows = [
        {"model": "Tanimoto_GPR", "mae": 1.0, "rmse": 2.0, "r2": 0.1},
        {"model": "Tanimoto_GPR", "mae": 3.0, "rmse": 4.0, "r2": 0.3},
    ]

    summary = summarize_metric_rows(rows)

    assert summary["Tanimoto_GPR"]["mae"]["mean"] == 2.0
    assert summary["Tanimoto_GPR"]["mae"]["std"] == pytest.approx(np.sqrt(2.0))
