from __future__ import annotations

from pathlib import Path

import h5py
import numpy as np
import pytest

from probes.p4_redox_baseline import (
    RX_SOURCE_SHA256,
    RX_SOURCE_SIZE,
    parse_rx_text,
    read_batt_p30k,
    regression_metrics,
)

RX_COLUMNS = (
    "MolId",
    "Inchi",
    "UniqueSolvents",
    "UniqueLevel",
    "Charge",
    "SpinMulti",
    "NumAtoms",
    "NumElems",
    "Composition",
    "listElements",
    "dictIEs",
    "dictEAs",
    "dictRedoxLevels",
    "dictOxPots",
    "dictRedPots",
)


def _rx_line(
    *,
    mol_id: str = "rx-test-1",
    inchi: str = "InChI=1S/C2H6O/c1-2-3/h3H,2H2,1H3",
    ip: float = 3.0,
    raw_ea: float = -2.0,
    oxidation_potential: float = 1.0,
    reduction_potential: float = -1.0,
) -> str:
    values = {
        "MolId": mol_id,
        "Inchi": inchi,
        "UniqueSolvents": (
            "DIELECTRIC=7,230;N=1,410&DIELECTRIC=18,500;N=1,415;"
            "ALPHA=0,000;BETA=0,735;GAMMA=20,200;PHI=0,000;PSI=0,000"
        ),
        "UniqueLevel": "wB97X-V/def2-TZVPPD/SMD",
        "Charge": "0",
        "SpinMulti": "",
        "NumAtoms": "9",
        "NumElems": "3",
        "Composition": "C2 H6 O1",
        "listElements": "C&H&O",
        "dictIEs": (
            "DIELECTRIC=7,230;N=1,410:2.0&"
            f"DIELECTRIC=18,500;N=1,415;ALPHA=0,000;BETA=0,735;"
            f"GAMMA=20,200;PHI=0,000;PSI=0,000:{ip}"
        ),
        "dictEAs": (
            "DIELECTRIC=7,230;N=1,410:9.0&"
            f"DIELECTRIC=18,500;N=1,415;ALPHA=0,000;BETA=0,735;"
            f"GAMMA=20,200;PHI=0,000;PSI=0,000:{raw_ea}"
        ),
        "dictRedoxLevels": (
            "DIELECTRIC=18,500;N=1,415;ALPHA=0,000;BETA=0,735;"
            "GAMMA=20,200;PHI=0,000;PSI=0,000:0"
        ),
        "dictOxPots": (
            "DIELECTRIC=7,230;N=1,410:0.5&"
            f"DIELECTRIC=18,500;N=1,415;ALPHA=0,000;BETA=0,735;"
            f"GAMMA=20,200;PHI=0,000;PSI=0,000:{oxidation_potential}"
        ),
        "dictRedPots": (
            "DIELECTRIC=7,230;N=1,410:0.25&"
            f"DIELECTRIC=18,500;N=1,415;ALPHA=0,000;BETA=0,735;"
            f"GAMMA=20,200;PHI=0,000;PSI=0,000:{reduction_potential}"
        ),
    }
    return "$".join(values[column] for column in RX_COLUMNS)


def test_rx_source_constants_are_pinned() -> None:
    assert RX_SOURCE_SIZE == 248404
    assert (
        RX_SOURCE_SHA256
        == "d30ec1ffccba15538bac0b67157c14e045f1721441be23837c6195eca24a5d87"
    )


def test_parse_rx_text_selects_dielectric_18_and_applies_formulas() -> None:
    text = "$".join(RX_COLUMNS) + "\n" + _rx_line() + "\n"

    rows = parse_rx_text(text)

    assert len(rows) == 1
    row = rows[0]
    assert row["IP"] == 3.0
    assert row["EA"] == 2.0
    assert row["oxidation_free_energy"] == 5.44
    assert row["reduction_free_energy"] == pytest.approx(-3.44)
    assert row["smiles"] == "CCO"
    assert row["inchikey"] == "LFQSCWFLJHTTHZ-UHFFFAOYSA-N"
    assert row["source"] == "RX-392"
    assert row["status"] == "source_native_dft"


def test_parse_rx_text_rejects_missing_dielectric_18() -> None:
    text = "$".join(RX_COLUMNS) + "\n" + _rx_line().replace("DIELECTRIC=18,500", "DIELECTRIC=7,230") + "\n"

    try:
        parse_rx_text(text)
    except ValueError as error:
        assert "DIELECTRIC=18" in str(error)
    else:
        raise AssertionError("expected missing DIELECTRIC=18 to fail")


def test_read_batt_p30k_maps_required_fields(tmp_path: Path) -> None:
    path = tmp_path / "Batt-P30K.h5"
    with h5py.File(path, "w") as handle:
        group = handle.create_group("CompMol0")
        group.create_dataset(
            "smiles",
            data=np.asarray(["CCO"], dtype=h5py.string_dtype("utf-8")),
        )
        for name, value in {
            "ip": 8.0,
            "ea": 1.0,
            "homo": -10.0,
            "lumo": 2.0,
            "dipole": (3.0, 4.0, 0.0),
        }.items():
            group.create_dataset(name, data=np.asarray(value, dtype=np.float32))

    rows = read_batt_p30k(path)

    assert len(rows) == 1
    assert rows[0]["row_id"] == "batt-p30k:CompMol0"
    assert rows[0]["source"] == "Batt-P30K"
    assert rows[0]["IP"] == 8.0
    assert rows[0]["EA"] == 1.0
    assert rows[0]["HOMO"] == -10.0
    assert rows[0]["LUMO"] == 2.0
    assert rows[0]["dipole"] == 5.0
    assert rows[0]["oxidation_free_energy"] == ""
    assert rows[0]["reduction_free_energy"] == ""


def test_regression_metrics_and_gate_threshold() -> None:
    metrics = regression_metrics(
        np.asarray([1.0, 2.0]),
        np.asarray([1.0, 2.0]),
    )

    assert metrics == {"mae": 0.0, "rmse": 0.0, "r2": 1.0}
    assert metrics["mae"] < 0.15
