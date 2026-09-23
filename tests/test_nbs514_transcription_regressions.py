from __future__ import annotations

import csv
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def test_carbon_disulfide_uses_four_figure_quality() -> None:
    path = REPOSITORY_ROOT / "data" / "interim" / "nbs514_organic_part1.csv"
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    row = next(row for row in rows if row["source_id"] == "nbs514:p13:004")
    assert row["compound_name"] == "Carbon disulfide"
    assert row["dielectric"] == "2.641"
    assert row["source_quality"] == "four_figures"
