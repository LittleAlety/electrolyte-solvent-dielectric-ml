from __future__ import annotations

import pytest

from electrolyte_ml.xtb_features import (
    XtbFeatureError,
    clausius_mossotti_proxy,
    generate_3d_xyz,
    molecular_volume_A3,
    onsager_proxy,
    parse_xtb_output,
)

SAMPLE_XTB_OUTPUT = """
         ::::::::::::::::::::::::::::::::::::::::::::::::::::::
         :: total energy              -8.226118333165 Eh    ::
         ::::::::::::::::::::::::::::::::::::::::::::::::::::::
                  HL-Gap            0.4814543 Eh           13.1010 eV
   Mol. α(0) /au        :         21.569029
molecular dipole:
                 x           y           z       tot (Debye)
 q only:       -0.089       0.430       0.280
   full:       -0.074       0.627       0.411       1.915
normal termination of xtb
"""


def test_parse_xtb_output_extracts_physical_features() -> None:
    parsed = parse_xtb_output(SAMPLE_XTB_OUTPUT)
    assert parsed.total_energy_hartree == pytest.approx(-8.226118333165)
    assert parsed.homo_lumo_gap_ev == pytest.approx(13.1010)
    assert parsed.dipole_debye == pytest.approx(1.915)
    assert parsed.polarizability_au == pytest.approx(21.569029)
    assert parsed.normal_termination is True


def test_parse_xtb_output_rejects_incomplete_run() -> None:
    with pytest.raises(XtbFeatureError, match="normal termination"):
        parse_xtb_output(SAMPLE_XTB_OUTPUT.replace("normal termination", "abnormal"))


def test_onsager_proxy_uses_squared_dipole_per_molar_volume() -> None:
    assert onsager_proxy(2.0, 4.0e-5) == pytest.approx(1.0e5)


def test_clausius_mossotti_proxy_converts_polarizability_to_angstrom_cubed() -> None:
    value = clausius_mossotti_proxy(1.0, 10.0)
    assert value == pytest.approx(0.01481847)


def test_generate_3d_xyz_contains_all_atoms() -> None:
    xyz = generate_3d_xyz("CO", seed=42)
    lines = xyz.strip().splitlines()
    assert lines[0] == "6"
    assert len(lines) == 8
    assert lines[2].split()[0] == "C"


def test_molecular_volume_is_positive_for_methanol_geometry() -> None:
    xyz = generate_3d_xyz("CO", seed=42)
    assert molecular_volume_A3(xyz) > 0
