"""Offline tests for the v0.4 xTB full-table migration probe.

The arithmetic that decides the verdict is pinned here without paying for an xTB run: the
conformer aggregation, the dipole-only substitution into the frozen physical block, the
placebo permutation and the cost regression all run on synthetic tables.  The three
integration tests read the repository's real scoreboard and only execute when the probe's
own summary has been built; the one test that touches the xTB binary skips when it is absent.
"""

from __future__ import annotations

import csv
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PROBE_PATH = REPOSITORY_ROOT / "probes" / "dielectric_xtb_full_table_migration.py"


def _load_probe():
    spec = importlib.util.spec_from_file_location("xtb_full_table_migration_probe", PROBE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


probe = _load_probe()
PHYSICAL_COLUMNS = probe.PHYSICAL_COLUMNS

FROZEN_V03_SHA256 = "ff2142936e06e04b329b70f8597574f75349e54ce876e9fff81309e6d35ccce4"


def _features(**overrides: float) -> dict[str, str]:
    values = {
        "T_K": "298.15",
        "formal_charge": "0",
        "heavy_atom_count": "3",
        "hbd": "1",
        "hba": "1",
        "tpsa_A2": "20.23",
        "molecular_volume_A3": "50.0",
        "dipole_D": "1.5000000",
        "polarizability_A3": "5.0",
        "mu_sq_over_Vm": "3.0",
        "molar_volume_m3_mol": "0.750",
        "alpha_over_Vm": "0.1",
        "total_energy_hartree": "-10.0",
        "homo_lumo_gap_ev": "10.0",
    }
    for column, value in overrides.items():
        values[column] = f"{float(value):.8g}"
    return values


def _row(
    key: str,
    *,
    smiles: str = "CCO",
    t_k: str = "298.15",
    epsilon: str = "24.0",
    features: dict[str, str] | None = None,
) -> dict[str, object]:
    return {
        "inchikey": key,
        "smiles": smiles,
        "T_K": t_k,
        "epsilon": epsilon,
        "_features": features if features is not None else _features(),
    }


def _synthetic_log(dipole: float, energy: float) -> str:
    return (
        "         -------------------------------------------------\n"
        "molecular dipole:\n"
        "                 x           y           z       tot (Debye)\n"
        " q only:        0.464       0.423       0.080\n"
        f"   full:        0.660       0.601       0.113       {dipole:.3f}\n"
        "         -------------------------------------------------\n"
        f"          | TOTAL ENERGY              {energy:.12f} Eh   |\n"
        "          | GRADIENT NORM               0.018980998331 Eh/alpha |\n"
        "          | HOMO-LUMO GAP              14.159668721855 eV   |\n"
        " Mol. alpha(0) /au        :          9.429075\n"
        "                  HL-Gap            0.5203585 Eh           14.1597 eV\n"
        "         :: total energy              -5.070208008270 Eh    ::\n"
        " * finished run on 2026/09/26 at 09:49:12.189\n"
    )


def test_single_point_arguments_drop_the_geometry_step():
    arguments = probe.xtb_single_point_arguments("input.xyz", formal_charge=-1)
    assert arguments[0] == "input.xyz"
    assert "--opt" not in arguments
    assert arguments[1:] == ["--gfn", "2", "--chrg", "-1", "--uhf", "0"]


def test_single_point_parser_requires_a_finished_run():
    with pytest.raises(probe.XtbFeatureError):
        probe.parse_single_point_output("molecular dipole:\n   full: 0 0 0 1.0\n")


def test_single_point_parser_reads_the_full_dipole_line():
    parsed = probe.parse_single_point_output(_synthetic_log(2.287, -5.070208008270))
    assert parsed.dipole_debye == pytest.approx(2.287)
    assert parsed.total_energy_hartree == pytest.approx(-5.070208008270)
    assert parsed.normal_termination is True


def test_boltzmann_weights_favour_the_lowest_energy_and_sum_to_one():
    weights = probe.boltzmann_weights([-10.0, -9.99, -9.0])
    assert float(np.sum(weights)) == pytest.approx(1.0)
    assert weights[0] > weights[1] > weights[2]
    assert weights[0] == pytest.approx(1.0, abs=1e-3)


def test_boltzmann_weights_reject_an_empty_ensemble():
    with pytest.raises(ValueError):
        probe.boltzmann_weights([])


def test_summarize_conformer_dipoles_reports_mean_spread_and_boltzmann():
    summary = probe.summarize_conformer_dipoles([1.0, 3.0, 5.0], [-10.0, -10.0, -10.0])
    assert summary["n_conformers"] == 3
    assert summary["dipole_D_conformer_mean"] == pytest.approx(3.0)
    assert summary["dipole_D_conformer_min"] == pytest.approx(1.0)
    assert summary["dipole_D_conformer_max"] == pytest.approx(5.0)
    assert summary["dipole_D_conformer_range"] == pytest.approx(4.0)
    assert summary["dipole_D_conformer_std"] == pytest.approx(np.std([1.0, 3.0, 5.0]))
    assert summary["dipole_D_conformer_boltzmann"] == pytest.approx(3.0)


def test_summarize_conformer_dipoles_rejects_a_non_finite_value():
    with pytest.raises(ValueError):
        probe.summarize_conformer_dipoles([1.0, float("nan")], [-10.0, -10.0])


def test_shuffled_dipole_map_is_a_permutation_and_is_deterministic():
    original = {"A": 1.0, "B": 2.0, "C": 3.0, "D": 4.0}
    first = probe.shuffled_dipole_map(original, seed=42)
    second = probe.shuffled_dipole_map(original, seed=42)
    assert first == second
    assert sorted(first) == sorted(original)
    assert sorted(first.values()) == sorted(original.values())


def test_build_physical_matrix_v04_touches_only_the_dipole_columns():
    from dielectric_observations_grouped_benchmark import build_matrices

    rows = [_row("A", smiles="CCO"), _row("B", smiles="CC#N", t_k="300.0")]
    _morgan, frozen_physical, _target, _temperatures, _groups = build_matrices(rows)
    matrix, account = probe.build_physical_matrix_v04(rows, dipole_map={"A": 4.0})
    dipole_index = PHYSICAL_COLUMNS.index("dipole_D")
    mu_index = PHYSICAL_COLUMNS.index("mu_sq_over_Vm")
    # molar_volume_m3_mol is not one of the fourteen frozen physical columns, so the
    # migration reads it off the row's own feature block; the test pins the same source.
    volume = float(rows[0]["_features"]["molar_volume_m3_mol"])
    assert account["migrated_rows"] == 1
    assert account["migrated_compounds"] == 1
    assert account["unmigrated_rows"] == 1
    assert account["rows_without_a_frozen_molar_volume"] == 0
    assert matrix[0, dipole_index] == pytest.approx(4.0)
    assert matrix[0, mu_index] == pytest.approx(16.0 / volume)
    kept = [index for index in range(matrix.shape[1]) if index not in (dipole_index, mu_index)]
    assert np.array_equal(matrix[:, kept], frozen_physical[:, kept])
    assert matrix[1, dipole_index] == pytest.approx(frozen_physical[1, dipole_index])
    assert matrix[1, mu_index] == pytest.approx(frozen_physical[1, mu_index])


def test_build_physical_matrix_v04_with_an_empty_map_matches_the_frozen_builder():
    from dielectric_observations_grouped_benchmark import build_matrices

    rows = [
        _row("A", smiles="CCO", features=_features(dipole_D=1.25)),
        _row("B", smiles="CC#N", t_k="305.5", features=_features(dipole_D=3.5)),
    ]
    _morgan, frozen_physical, _target, _temperatures, _groups = build_matrices(rows)
    migrated, account = probe.build_physical_matrix_v04(rows, dipole_map={})
    assert account["migrated_rows"] == 0
    assert np.array_equal(migrated, frozen_physical)


def test_build_physical_matrix_v04_replaces_every_row_of_a_migrated_compound():
    rows = [_row("A", t_k="290.0"), _row("A", t_k="310.0"), _row("B")]
    matrix, account = probe.build_physical_matrix_v04(rows, dipole_map={"A": 2.0})
    assert account["migrated_rows"] == 2
    assert account["migrated_compounds"] == 1
    dipole_index = PHYSICAL_COLUMNS.index("dipole_D")
    assert matrix[0, dipole_index] == pytest.approx(2.0)
    assert matrix[1, dipole_index] == pytest.approx(2.0)
    assert matrix[2, dipole_index] == pytest.approx(1.5)


def test_heavy_atom_cost_regression_recovers_a_known_line():
    regression = probe.heavy_atom_cost_regression([(2, 1.0), (4, 2.0), (6, 3.0)])
    assert regression["n"] == 3
    assert regression["slope_seconds_per_heavy_atom"] == pytest.approx(0.5)
    assert regression["intercept_seconds"] == pytest.approx(0.0)
    assert regression["mean_seconds_per_compound"] == pytest.approx(2.0)


def test_heavy_atom_cost_regression_survives_a_single_point():
    regression = probe.heavy_atom_cost_regression([(6, 1.5)])
    assert regression["n"] == 1
    assert regression["slope_seconds_per_heavy_atom"] == 0.0


def test_register_protocol_descriptions_adds_the_three_arms():
    probe.register_protocol_descriptions()
    for name in (
        "paired_base_conformer_dipole",
        "paired_base_conformer_dipole_shuffled",
        "paired_base_random_row_leak",
    ):
        assert name in probe.coverage.PROTOCOL_DESCRIPTIONS


def test_write_csv_rows_is_lf_only(tmp_path):
    path = tmp_path / "table.csv"
    probe.write_csv_rows(path, ("a", "b"), [{"a": "1", "b": "2"}])
    raw = path.read_bytes()
    assert b"\r\n" not in raw
    assert raw.endswith(b"\n")


def test_build_roster_puts_scored_compounds_first_and_small_first():
    features = {
        "BIG": {"name": "big", "smiles": "CCO", "heavy_atom_count": "9", "dipole_D": "1"},
        "SMALL": {"name": "small", "smiles": "CO", "heavy_atom_count": "2", "dipole_D": "1"},
        "MID": {"name": "mid", "smiles": "CC#N", "heavy_atom_count": "5", "dipole_D": "1"},
    }
    roster = probe.build_roster(features, {"BIG"})
    assert [entry["inchikey"] for entry in roster] == ["BIG", "SMALL", "MID"]


def test_frozen_v03_dataset_digest_is_untouched():
    dataset = REPOSITORY_ROOT / "data" / "dielectric_v03.csv"
    if not dataset.is_file():
        pytest.skip("the frozen v0.3 dataset is not present")
    from electrolyte_ml.exporting import canonical_text_sha256

    assert canonical_text_sha256(dataset) == FROZEN_V03_SHA256


SUMMARY_PATH = REPOSITORY_ROOT / "probes" / "dielectric_xtb_full_table_migration_summary.json"


@pytest.mark.skipif(not SUMMARY_PATH.is_file(), reason="the migration summary has not been built")
def test_built_summary_reproduces_the_reference_baseline():
    summary = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
    readings = summary["readings"]
    assert summary["shots"] == 1
    assert readings["published_r2"] == pytest.approx(probe.REFERENCE_R2)
    assert readings["baseline_r2"] == pytest.approx(probe.REFERENCE_R2, abs=1e-9)
    assert readings["baseline_reproduced"] is True
    assert summary["verdict"]["state"] in {"pass", "partial", "fail", "not_run"}
    assert summary["main_scoreboard"]["rows_scored"] == 457
    assert summary["main_scoreboard"]["compounds_scored"] == 97
    assert summary["main_scoreboard"]["mask_reused_not_rebuilt"] is True


@pytest.mark.skipif(not SUMMARY_PATH.is_file(), reason="the migration summary has not been built")
def test_built_summary_labels_the_leak_reference_and_the_control():
    summary = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
    readings = summary["readings"]
    if "control" in readings:
        assert "never a conclusion number" in probe.coverage.PROTOCOL_DESCRIPTIONS[
            "paired_base_conformer_dipole_shuffled"
        ]
    if "leak_reference" in readings:
        assert readings["leak_reference"]["protocol"] == "paired_base_random_row_leak"
        assert "never enters a pass or a fail" in readings["leak_reference"]["note"]


@pytest.mark.skipif(not SUMMARY_PATH.is_file(), reason="the migration summary has not been built")
def test_built_artifacts_are_lf_only_and_cover_the_roster():
    summary = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
    conformers = REPOSITORY_ROOT / summary["outputs"]["conformers"]
    raw = conformers.read_bytes()
    assert b"\r\n" not in raw
    with conformers.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == summary["conformer_coverage"]["compounds_run"]
    statuses = {row["status"] for row in rows}
    assert statuses <= {"ok", "error"}


def test_conformer_run_uses_the_pinned_single_thread_environment(tmp_path, monkeypatch):
    calls: list[dict[str, object]] = []

    def _fake_run(executable, arguments, *, cwd, timeout_seconds, environment=None):
        calls.append({"environment": environment, "arguments": list(arguments)})

        class _Completed:
            returncode = 0
            stdout = _synthetic_log(1.234, -7.5).encode("utf-8")

        return _Completed()

    monkeypatch.setattr(probe, "run_xtb_subprocess", _fake_run)
    result = probe.run_conformer_compound(
        inchikey="TESTKEY",
        smiles="CO",
        xtb_executable=Path("xtb"),
        work_dir=tmp_path,
        seed=42,
        max_conformers=2,
    )
    assert result["status"] == "ok"
    assert result["n_conformers"] >= 1
    assert all(call["environment"] is None for call in calls)
    assert all("--opt" not in call["arguments"] for call in calls)
    assert result["dipole_D_conformer_mean"] == pytest.approx(1.234)
