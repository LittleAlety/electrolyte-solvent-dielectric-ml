from __future__ import annotations

import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "scripts"))

from analyze_springer_materials_crosscheck import (
    _pure_name,
    build_crosscheck,
)


def test_pure_name_strips_publication_prefix_and_suffix() -> None:
    assert _pure_name("Dielectric Constant of Benzene (pure)") == "benzene"
    assert _pure_name("dl-erythro-example (pure)") == "erythro-example"


def test_crosscheck_uses_only_near_temperature_rows() -> None:
    v02_rows = [
        {
            "name": "Benzene",
            "inchikey": "UHOVQNZJYSORNB-UHFFFAOYSA-N",
            "T_K": "298.15",
            "dielectric": "2.270",
        }
    ]
    datasets = [
        {
            "doc_id": "SMI_SC_TEST",
            "title": "Dielectric Constant of Benzene (pure)",
            "url": "https://example.invalid",
            "rows": [
                {"temperature_K": "298.15", "dielectric": "2.274"},
                {"temperature_K": "300.00", "dielectric": "2.280"},
                {"temperature_K": "350.00", "dielectric": "1.500"},
            ],
        }
    ]
    rows = build_crosscheck(
        v02_rows,
        datasets,
        max_delta_temperature=5.0,
    )
    assert len(rows) == 1
    assert rows[0]["smi_near_rows"] == "2"
    assert float(rows[0]["smi_median_dielectric"]) == 2.277
    assert float(rows[0]["absolute_delta"]) == 0.007
