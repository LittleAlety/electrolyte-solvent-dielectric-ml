from __future__ import annotations

import json
from io import StringIO
from types import SimpleNamespace

from scripts import check_environment


def test_python_check_accepts_real_sys_version_info_shape() -> None:
    result = check_environment.check_python((3, 11, 9, "final", 0))

    assert result.passed is True
    assert result.actual == "3.11.9"


def test_package_check_fails_when_import_is_missing() -> None:
    spec = check_environment.PackageSpec(
        distribution="demo-package",
        import_name="demo_package",
        minimum=(2, 0),
    )

    def missing_importer(name: str) -> object:
        raise ModuleNotFoundError(name)

    result = check_environment.check_package(spec, importer=missing_importer)

    assert result.passed is False
    assert result.actual is None
    assert "could not import demo_package" in result.detail


def test_package_check_fails_when_version_is_below_minimum() -> None:
    spec = check_environment.PackageSpec(
        distribution="demo-package",
        import_name="demo_package",
        minimum=(2, 0),
    )

    result = check_environment.check_package(
        spec,
        importer=lambda name: SimpleNamespace(__name__=name),
        version_getter=lambda name: "1.9.9",
    )

    assert result.passed is False
    assert result.actual == "1.9.9"
    assert "below required >=2.0" in result.detail


def test_run_checks_passes_with_importable_packages_and_minimal_rdkit() -> None:
    class FakeChem:
        @staticmethod
        def MolFromSmiles(smiles: str) -> object | None:
            return object() if smiles == "CCO" else None

    class FakeDescriptors:
        @staticmethod
        def MolWt(molecule: object) -> float:
            assert molecule is not None
            return 46.07

    def fake_importer(name: str) -> object:
        if name == "rdkit.Chem":
            return FakeChem
        if name == "rdkit.Chem.Descriptors":
            return FakeDescriptors
        return SimpleNamespace(__name__=name)

    report = check_environment.run_checks(
        python_version=(3, 11, 9),
        importer=fake_importer,
        version_getter=lambda name: "9999.0.0",
    )

    assert report.passed is True
    assert report.python.passed is True
    assert all(result.passed for result in report.packages)
    assert report.rdkit_smiles.passed is True


def test_main_json_all_pass_returns_zero_and_machine_readable_output() -> None:
    class FakeChem:
        @staticmethod
        def MolFromSmiles(smiles: str) -> object | None:
            return object() if smiles == "CCO" else None

    class FakeDescriptors:
        @staticmethod
        def MolWt(molecule: object) -> float:
            return 46.07

    def fake_importer(name: str) -> object:
        if name == "rdkit.Chem":
            return FakeChem
        if name == "rdkit.Chem.Descriptors":
            return FakeDescriptors
        return SimpleNamespace(__name__=name)

    stdout = StringIO()
    exit_code = check_environment.main(
        ["--json"],
        python_version=(3, 11, 9),
        importer=fake_importer,
        version_getter=lambda name: "9999.0.0",
        stdout=stdout,
    )
    payload = json.loads(stdout.getvalue())

    assert exit_code == 0
    assert payload["passed"] is True
    assert payload["rdkit_smiles"]["passed"] is True
