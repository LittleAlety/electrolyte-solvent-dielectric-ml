from __future__ import annotations

from probes.build_modern_solvent_candidate_queue import choose_nearest_row


def test_choose_nearest_row_prefers_room_temperature() -> None:
    rows = [
        {"T_K": 313.0, "dielectric": 5.0},
        {"T_K": 298.0, "dielectric": 6.0},
    ]

    selected = choose_nearest_row(rows)

    assert selected is not None
    assert selected["dielectric"] == 6.0


def test_choose_nearest_row_rejects_values_far_from_room_temperature() -> None:
    assert choose_nearest_row([{"T_K": 350.0, "dielectric": 5.0}]) is None
