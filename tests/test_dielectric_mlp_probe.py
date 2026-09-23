from __future__ import annotations

import numpy as np
import pytest

from probes.dielectric_mlp_probe import inverse_log_dielectric, log_dielectric


def test_log_dielectric_round_trip() -> None:
    values = np.asarray([1.0001, 2.0, 10.0, 80.0])

    restored = inverse_log_dielectric(log_dielectric(values))

    np.testing.assert_allclose(restored, values, rtol=1e-12, atol=1e-12)


def test_inverse_log_dielectric_clips_nonphysical_values() -> None:
    restored = inverse_log_dielectric(np.asarray([-10.0]))

    assert restored.tolist() == pytest.approx([1.0], abs=5e-5)
