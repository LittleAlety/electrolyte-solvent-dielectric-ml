"""Guards for the Week 21 eta thaw.

The Walden arm registered the kinematic rows as excluded *because* no density
was on disk.  Now it is, so the exclusion is void -- but it buys five compounds
and no model reading, and the test file exists to keep that honest.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUMMARY = ROOT / "probes/w21_eta_thaw_summary.json"
ROWS = ROOT / "probes/artifacts/w21_eta_thawed_rows.csv"
REPORT = ROOT / "reports/w21_eta_thaw.md"


def test_every_kinematic_row_folds_in_by_exact_density_pairing() -> None:
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    assert summary["kinematic_rows_seen"] == 176
    assert summary["kinematic_exclusions_registered"] == 214
    assert summary["kinematic_exclusions_by_dataset"]["thermoml_viscosity"] == 176
    assert summary["kinematic_exclusions_by_dataset"]["pubchem_liquid_window_harvest"] == 38
    assert summary["thawed_rows"] == 176
    assert summary["unmatched_or_rejected"] == 0
    assert summary["distinct_keys_thawed"] == 5
    assert summary["by_pairing_kind"] == {"exact": 176}
    assert summary["models_fitted"] == 0
    assert summary["writes_any_pool"] is False


def test_the_thawed_rows_reproduce_eta_equals_nu_times_rho() -> None:
    with ROWS.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 176
    assert bytes([13, 10]) not in ROWS.read_bytes()
    for row in rows:
        assert row["status"] == "thawed_exact"
        eta = float(row["nu_m2_s"]) * float(row["rho_kg_m3"])
        assert abs(eta - float(row["eta_Pa_s"])) <= 1e-9 * abs(eta)
        assert row["density_source_doi"]


def test_the_thaw_adds_no_compound_and_says_so() -> None:
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    assert summary["keys_not_previously_in_joint_table"] == []
    assert "不重拟合" in summary["decision"]["model_layer"]
    text = REPORT.read_text(encoding="utf-8")
    for needle in ("数据层：结清", "模型层：明确不做", "176"):
        assert needle in text, needle