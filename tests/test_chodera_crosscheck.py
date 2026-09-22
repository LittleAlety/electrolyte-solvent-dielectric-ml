from __future__ import annotations

import numpy as np

from scripts.build_chodera_crosscheck import build_crosscheck


def _observation(
    *,
    source: str,
    key: str,
    temperature: str,
    value: str,
) -> dict[str, str]:
    return {
        "dataset_source": source,
        "selection_status": "primary" if source == "P1 ThermoML" else "historical_crosscheck_only",
        "inchikey": key,
        "smiles": "CCO",
        "name": "ethanol",
        "T_K": temperature,
        "dielectric": value,
        "source_doi": "10.1000/p1" if source == "P1 ThermoML" else "arXiv:1506.00262",
        "gate_flags": "experimental",
    }


def test_crosscheck_uses_reconstructable_nearest_temperature_pair() -> None:
    key = "LFQSCWFLJHTTHZ-UHFFFAOYSA-N"
    rows, summary = build_crosscheck(
        [
            _observation(source="P1 ThermoML", key=key, temperature="298", value="2"),
            _observation(source="P1 ThermoML", key=key, temperature="300", value="3"),
            _observation(source="Chodera 2015", key=key, temperature="299", value="2.2"),
            _observation(source="Chodera 2015", key=key, temperature="301", value="3.2"),
        ]
    )

    assert len(rows) == 1
    row = rows[0]
    assert row["p1_n"] == 2
    assert row["chodera_n"] == 2
    assert row["nearest_p1_T_K"] == "300"
    assert row["nearest_chodera_T_K"] == "301"
    assert float(row["pair_delta_T_K"]) == 1.0
    assert float(row["pair_value_delta"]) == 0.2
    assert np.isclose(summary["median_abs_delta"], 0.2)
