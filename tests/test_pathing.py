from __future__ import annotations

from electrolyte_ml.pathing import portable_basename


def test_portable_basename_handles_windows_and_posix_paths() -> None:
    assert portable_basename(r"C:\data\raw\thermoml\water.xml") == "water.xml"
    assert portable_basename("data/raw/thermoml/water.xml") == "water.xml"
    assert portable_basename("/tmp/thermoml/water.xml") == "water.xml"
