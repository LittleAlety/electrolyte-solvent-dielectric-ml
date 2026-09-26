"""Offline tests for the W17-18 THEMol per-molecule property inventory.

Nothing here touches the network or xTB.  The delivered inventory JSON is the
primary object under test: it is the artefact that states which HDF5 keys
THEMol actually carries, so the tests pin the key sets and the MBIS
self-consistency checks that the report quotes.  The fetching primitives are
exercised against a stub session so range accounting and the download ceiling
are checked without a single request leaving the machine.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "probes"))

import themol_property_inventory as inventory

INVENTORY = REPOSITORY_ROOT / "probes" / "themol_property_inventory.json"
PROBE = REPOSITORY_ROOT / "probes" / "themol_property_inventory.py"

EXPECTED_SUBSETS = [
    "hessian",
    "hessian_relax",
    "mbis",
    "torsion_scan",
    "torsion_scan_relax",
]

HESSIAN_DATASET_KEYS = [
    "atomic_numbers",
    "coords",
    "hessian",
    "mapped_isomeric_smiles",
    "mapped_nonisomeric_smiles",
]

MBIS_DATASET_KEYS = [
    "atomic_numbers",
    "coords",
    "mapped_isomeric_smiles",
    "mapped_nonisomeric_smiles",
    "parameters",
]

MBIS_INFO_KEYS = [
    "atomic_charge",
    "atomic_dipole",
    "atomic_quadrupole",
    "atomic_volumes",
]

MOLECULE_CAP = 40

# 1 e * angstrom expressed in Debye, CODATA-consistent with the 4.80320 value the
# probe uses; pinned so a silent constant edit cannot pass the numeric tests.
E_ANGSTROM_TO_DEBYE = 4.803204712570263


class _StubResponse:
    def __init__(self, payload: bytes, status_code: int = 206, headers: dict | None = None) -> None:
        self._payload = payload
        self.status_code = status_code
        self.headers = headers or {}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def iter_content(self, chunk_size: int):
        for start in range(0, len(self._payload), chunk_size):
            yield self._payload[start : start + chunk_size]

    def close(self) -> None:
        return None


class _StubSession:
    def __init__(self, responses: list[_StubResponse]) -> None:
        self._responses = list(responses)
        self.requests: list[dict | None] = []

    def get(self, url, headers=None, timeout=None, stream=False):
        self.requests.append(headers)
        if not self._responses:
            raise AssertionError("stub session ran out of prepared responses")
        return self._responses.pop(0)


def test_expected_subsets_match_the_module_declaration() -> None:
    assert sorted(subset.name for subset in inventory.SUBSETS) == EXPECTED_SUBSETS
    assert inventory.MOLECULE_CAP == MOLECULE_CAP


def test_fetcher_truncates_a_range_ignoring_server() -> None:
    payload = bytes(range(256)) * 8
    session = _StubSession([_StubResponse(payload, headers={"Content-Range": "bytes 0-2047/4096"})])
    fetcher = inventory.Fetcher(session, limit_bytes=1_000_000)

    got, headers = fetcher.get_range("https://example.invalid/x", 0, 9)

    assert got == payload[:10]
    assert headers["Content-Range"].endswith("/4096")
    assert fetcher.total_bytes == 10


def test_fetcher_refuses_to_cross_the_download_ceiling() -> None:
    session = _StubSession([_StubResponse(b"x" * 64)])
    fetcher = inventory.Fetcher(session, limit_bytes=16)

    with pytest.raises(inventory.DownloadBudgetExceeded):
        fetcher.get_range("https://example.invalid/x", 0, 63)

    assert fetcher.total_bytes == 0
    assert fetcher.remaining_bytes == 16


def test_range_reader_serves_repeated_reads_from_cache() -> None:
    payload = b"abcdefgh" * 16
    probe = _StubResponse(b"a", headers={"Content-Range": f"bytes 0-0/{len(payload)}"})
    body = _StubResponse(payload)
    session = _StubSession([probe, body])
    fetcher = inventory.Fetcher(session, limit_bytes=1_000_000)
    reader = inventory.RangeReader(fetcher, "https://example.invalid/x")

    assert reader.size == len(payload)
    reader.seek(0)
    assert reader.read(4) == payload[:4]
    requests_after_first_read = len(session.requests)
    reader.seek(0)
    assert reader.read(4) == payload[:4]

    assert len(session.requests) == requests_after_first_read
    assert fetcher.total_bytes == 5


def test_mbis_derived_dipole_from_a_charge_pair() -> None:
    charges = np.array([1.0, -1.0])
    coordinates = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]])
    zeros3 = np.zeros((2, 3))
    zeros33 = np.zeros((2, 3, 3))
    volumes = np.array([1.0, 2.0])
    parameters = np.array([[0.0, 1.0, 1.0], [1.0, 1.0, 1.0]])
    atomic_numbers = np.array([1, 1])

    derived = inventory.mbis_derived(
        charges, coordinates, zeros3, zeros33, volumes, parameters, atomic_numbers
    )

    assert derived["charge_sum_e"] == pytest.approx(0.0)
    assert derived["dipole_magnitude_e_a"] == pytest.approx(1.0)
    assert derived["dipole_magnitude_debye"] == pytest.approx(E_ANGSTROM_TO_DEBYE)
    assert derived["dipole_vector_e_a"] == pytest.approx([-1.0, 0.0, 0.0])
    assert derived["volume_sum_angstrom3"] == pytest.approx(3.0)
    assert derived["electron_count_delta_e"] == pytest.approx(0.0)
    assert derived["max_abs_quadrupole_trace_e_a2"] == pytest.approx(0.0)


def test_mbis_derived_flags_a_broken_charge_sum() -> None:
    charges = np.array([1.0, -0.5])
    coordinates = np.zeros((2, 3))
    parameters = np.array([[0.0, 1.0, 1.0], [1.0, 1.0, 1.0]])
    derived = inventory.mbis_derived(
        charges,
        coordinates,
        np.zeros((2, 3)),
        np.zeros((2, 3, 3)),
        np.array([1.0, 1.0]),
        parameters,
        np.array([1, 1]),
    )
    assert derived["charge_sum_e"] == pytest.approx(0.5)
    assert derived["electron_count_delta_e"] == pytest.approx(0.5)


def test_parse_xtb_dipole_reads_the_total() -> None:
    text = (
        "molecular dipole:\n"
        "                 x           y           z       tot (Debye)\n"
        " q only:       -0.131       0.919       0.666\n"
        "   full:       -0.158       1.104       0.800       3.489\n"
    )
    assert inventory.parse_xtb_dipole(text) == pytest.approx(3.489)
    assert inventory.parse_xtb_dipole("no dipole here") is None


def test_formal_charge_from_smiles() -> None:
    assert inventory.formal_charge_from_smiles("CCO") == 0
    assert inventory.formal_charge_from_smiles("[Na+]") == 1
    assert inventory.formal_charge_from_smiles("not a smiles") is None


def test_orbital_key_pattern_matches_only_orbital_names() -> None:
    for name in ("homo", "lumo_energy", "orbital", "eigenvalues", "band_gap"):
        assert inventory.ORBITAL_KEY_PATTERN.search(name)
    for name in ("atomic_charge", "coords", "hessian", "parameters", "energy"):
        assert not inventory.ORBITAL_KEY_PATTERN.search(name)


def _load_inventory() -> dict:
    if not INVENTORY.is_file():
        pytest.fail(f"missing delivered inventory: {INVENTORY}")
    return json.loads(INVENTORY.read_text(encoding="utf-8"))


def test_delivered_inventory_is_internally_consistent() -> None:
    payload = _load_inventory()
    assert inventory.inventory_problems(payload) == []


def test_delivered_inventory_pins_the_measured_keys() -> None:
    payload = _load_inventory()
    subsets = payload["subsets"]

    assert sorted(subsets) == EXPECTED_SUBSETS
    assert sorted(subsets["hessian"]["measured_keys"]) == HESSIAN_DATASET_KEYS
    assert sorted(subsets["mbis"]["measured_keys"]) == sorted(
        MBIS_DATASET_KEYS + MBIS_INFO_KEYS
    )
    for nested_key in MBIS_INFO_KEYS:
        assert nested_key in subsets["mbis"]["measured_keys"]


def test_delivered_inventory_reports_no_dft_orbitals() -> None:
    payload = _load_inventory()
    assert payload["orbital_energy_fields"]["found_in_any_subset"] is False
    assert payload["orbital_energy_fields"]["matching_keys"] == []
    assert payload["answers"]["does_themol_store_dft_homo_lumo"]["answer"] == "no"
    assert payload["all_measured_keys"] == sorted(payload["all_measured_keys"])


def test_delivered_inventory_stays_inside_its_budget() -> None:
    payload = _load_inventory()
    budget = payload["budget"]
    assert budget["downloaded_bytes"] > 0
    assert budget["downloaded_bytes"] <= budget["limit_bytes"]
    assert budget["within_limit"] is True
    assert budget["limit_bytes"] <= 50 * 1024 * 1024
    assert payload["poc"]["molecules_probed"] <= MOLECULE_CAP
    assert payload["poc"]["within_cap"] is True


def test_delivered_inventory_mbis_numbers_are_physical() -> None:
    payload = _load_inventory()
    subsets = payload["subsets"]
    assert subsets["mbis"]["molecules_probed"] >= 4

    poc = subsets["mbis"]["mbis_poc"]
    # MBIS covers ions as well as neutrals, so the charge test is against the
    # SMILES formal charge, not against zero.
    assert poc["charge_residual_within_tolerance"] is True
    assert poc["molecules_with_known_formal_charge"] == poc["molecules"]
    assert poc["charged_molecules"] >= 1
    assert poc["quadrupoles_traceless_within_tolerance"] is True
    assert poc["electron_count_within_tolerance"] is True
    assert 0.0 < poc["dipole_debye_min"] <= poc["dipole_debye_max"] < 15.0

    for sample in subsets["mbis"]["molecule_samples"]:
        assert sample["natoms"] > 0
        assert abs(sample["charge_sum_e"] - sample["formal_charge_from_smiles"]) <= 1e-3
        assert sample["volumes_positive"] is True
        assert sample["slater_populations_positive"] is True
        assert sample["inverse_widths_positive"] is True
        assert sample["parent_index_in_range"] is True


def test_delivered_inventory_evidence_levels_are_declared() -> None:
    payload = _load_inventory()
    candidates = payload["answers"]["epsilon_dn_candidates"]
    assert candidates, "the epsilon/DN candidate list must not be empty"
    for candidate in candidates:
        assert candidate["evidence"] in {"measured", "documented", "inferred"}
        assert candidate["field"]
        assert candidate["why"]

    for record in payload["subsets"].values():
        if record.get("status"):
            continue
        for entry in record["schema"]["datasets"]:
            assert entry["unit_evidence"] in {"measured", "documented", "n/a", "unmeasured"}


def test_check_mode_passes_on_the_delivered_inventory() -> None:
    completed = subprocess.run(
        [sys.executable, str(PROBE), "--check"],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "inventory consistent" in completed.stdout


def test_check_mode_fails_on_a_mutilated_inventory(tmp_path: Path) -> None:
    payload = _load_inventory()
    payload["subsets"]["mbis"]["measured_keys"] = ["coords"]
    payload["orbital_energy_fields"] = {"found_in_any_subset": True, "matching_keys": ["homo"]}
    broken = tmp_path / "broken.json"
    broken.write_text(json.dumps(payload), encoding="utf-8")

    problems = inventory.inventory_problems(json.loads(broken.read_text(encoding="utf-8")))
    assert any("MBIS key" in problem for problem in problems)
    assert any("orbital-looking" in problem for problem in problems)
