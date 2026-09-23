from __future__ import annotations

from electrolyte_ml.pathing import portable_basename, portable_relative_path


def test_portable_basename_handles_windows_and_posix_paths() -> None:
    assert portable_basename(r"C:\data\raw\thermoml\water.xml") == "water.xml"
    assert portable_basename("data/raw/thermoml/water.xml") == "water.xml"
    assert portable_basename("/tmp/thermoml/water.xml") == "water.xml"


def test_portable_relative_path_normalizes_relative_and_absolute_paths(
    tmp_path,
    monkeypatch,
) -> None:
    nested = tmp_path / "data" / "example.csv"
    monkeypatch.chdir(tmp_path)

    assert portable_relative_path(nested, root=tmp_path) == "data/example.csv"
    assert portable_relative_path("example.csv", root=tmp_path) == "example.csv"
    assert portable_relative_path(tmp_path.parent / "outside.csv", root=tmp_path) == (
        tmp_path.parent / "outside.csv"
    ).resolve().as_posix()
