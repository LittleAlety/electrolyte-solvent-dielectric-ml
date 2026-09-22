from __future__ import annotations

import json

from electrolyte_ml.exporting import verify_export_manifest
from probes.export_week3_results import export_week3_results


def test_week3_export_is_self_contained_and_manifested(tmp_path) -> None:
    export_week3_results(tmp_path)

    summary = json.loads((tmp_path / "week3_summary.json").read_text(encoding="utf-8"))
    assert (tmp_path / "SHA256SUMS").is_file()
    assert verify_export_manifest(tmp_path) == []
    assert {
        "chodera_crosscheck",
        "chodera_summary",
        "dielectric_ext",
        "dielectric_ext_observations",
        "dielectric_ext_summary",
    }.issubset(summary["outputs"])
