"""Regression tests for the xTB recovery-feasibility probe."""

from __future__ import annotations

import copy
import json
import subprocess
import tempfile
from pathlib import Path

import pytest

from probes.xtb_recovery_probe import (
    CONTROL_STRATEGY_IDS,
    EVIDENCE_PATH,
    FE_KEY,
    FROZEN_FLAGS,
    ION_PAIR_KEYS,
    SCF_STRATEGIES,
    check_payload,
    resolve_xtb,
    screen_fe_candidate,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
RUNNER = REPOSITORY_ROOT / "scripts" / "run_xtb_physical_features.py"
DATASET = REPOSITORY_ROOT / "data" / "dielectric_v03.csv"


def _evidence() -> dict[str, object]:
    return json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))


def test_evidence_satisfies_its_own_invariants() -> None:
    assert check_payload(_evidence()) == []


def test_the_probe_judgement_follows_the_frozen_runner() -> None:
    """The premise of the whole probe: the runner accepts a sentinel, not only
    the stdout marker.  If that ever changes, this probe must be revisited."""

    source = RUNNER.read_text(encoding="utf-8")
    assert '"normal termination of xtb" in output_text' in source
    assert '".xtboptok"' in source


def test_strategy_prefix_is_verbatim_the_frozen_invocation() -> None:
    assert FROZEN_FLAGS == ("--opt", "--gfn", "2", "--chrg", "0", "--uhf", "0")


def test_every_ion_pair_records_the_whole_strategy_matrix() -> None:
    ion_pairs = _evidence()["ion_pairs"]
    assert set(ion_pairs) == set(ION_PAIR_KEYS)
    declared = {strategy["id"] for strategy in SCF_STRATEGIES}
    for key, record in ion_pairs.items():
        seen = {attempt["strategy"] for attempt in record["attempts"]}
        assert seen == declared, key


def test_the_frozen_protocol_still_fails_for_all_three_ion_pairs() -> None:
    """This is the defect the whole line of work starts from."""

    for key, record in _evidence()["ion_pairs"].items():
        frozen = next(
            attempt
            for attempt in record["attempts"]
            if attempt["strategy"] == "frozen"
        )
        assert frozen["exit_code"] == 128, key
        assert frozen["frozen_runner_accepts"] is False, key


def test_the_ion_pairs_are_accepted_under_some_reproducible_protocol() -> None:
    for key, record in _evidence()["ion_pairs"].items():
        winners = [
            attempt["strategy"]
            for attempt in record["attempts"]
            if attempt["frozen_runner_accepts"] is True
        ]
        assert winners, key
        assert record["recovered"] is True, key
        assert record["recovered_by"] in winners, key
        for attempt in record["attempts"]:
            if attempt["frozen_runner_accepts"] is True:
                assert attempt["features"] is not None, (key, attempt["strategy"])


def test_relaxing_the_scc_threshold_alone_does_not_recover_anything() -> None:
    """--acc 5.0 is the cheap hypothesis, and it does not work."""

    for key, record in _evidence()["ion_pairs"].items():
        loose = next(
            attempt for attempt in record["attempts"] if attempt["strategy"] == "acc_5"
        )
        assert loose["exit_code"] == 128, key
        assert loose["frozen_runner_accepts"] is False, key


def test_control_rows_are_accepted_under_the_frozen_protocol() -> None:
    """Without this the sensitivity comparison would be meaningless."""

    controls = _evidence()["protocol_sensitivity"]["controls"]
    assert controls
    for key, entry in controls.items():
        assert set(entry["runs"]) == set(CONTROL_STRATEGY_IDS), key
        assert entry["runs"]["frozen"]["frozen_runner_accepts"] is True, key
        assert entry["runs"]["etemp_5000"]["frozen_runner_accepts"] is True, key
        assert entry["feature_deltas"], key


def test_the_recovery_protocol_is_not_protocol_neutral() -> None:
    """The decisive negative: a recovery flag moves already-frozen features,
    and it moves them most on the very class being recovered."""

    sensitivity = _evidence()["protocol_sensitivity"]
    assert sensitivity["max_relative_change"] > 0.5
    controls = sensitivity["controls"]
    worst = max(
        delta["relative_change"]
        for entry in controls.values()
        for delta in entry["feature_deltas"].values()
        if delta["relative_change"] is not None
    )
    assert worst == pytest.approx(sensitivity["max_relative_change"], abs=1e-6)
    # The near-null control: propan-1-ol has a bit-identical dipole and gap,
    # while polarizability and total energy drift only at the 1e-8 level, which
    # is why the report prints them as 0.0000%.
    propanol = controls["BDERNNFJNOPAEC-UHFFFAOYSA-N"]["feature_deltas"]
    assert propanol["dipole_debye"]["relative_change"] == 0.0
    assert propanol["homo_lumo_gap_ev"]["relative_change"] == 0.0
    for field in ("polarizability_au", "total_energy_hartree"):
        assert 0.0 < propanol[field]["relative_change"] < 1e-6
    ionic_liquid = controls["ALYCOCULEAWWJO-UHFFFAOYSA-N"]["feature_deltas"]
    assert ionic_liquid["homo_lumo_gap_ev"]["relative_change"] > 0.8


def test_fe_screening_finds_a_single_fragment_fe_c_structure_that_embeds() -> None:
    section = _evidence()["fe_structures"]
    assert section["viable_found"] is True
    viable = [
        candidate
        for candidate in section["candidates"]
        if candidate["id"] in section["viable_candidate_ids"]
    ]
    assert viable
    for candidate in viable:
        assert candidate["sanitises"] is True
        assert candidate["fragments"] == 1
        assert candidate["has_fe_c_bond"] is True
        assert candidate["embed_return"] >= 0
        lengths = candidate["fe_c_bond_lengths_angstrom"]
        assert len(lengths) == 5
        assert all(1.9 <= value <= 2.2 for value in lengths)


def test_the_stored_carbonyl_value_is_not_an_fe_c_structure() -> None:
    """The frozen SMILES is six fragments with no Fe-C bond, which is why the
    row cannot be recovered by only fixing the geometry."""

    stored = next(
        candidate
        for candidate in _evidence()["fe_structures"]["candidates"]
        if candidate["id"] == "stored"
    )
    assert stored["sanitises"] is True
    assert stored["fragments"] == 6
    assert stored["has_fe_c_bond"] is False


def test_the_screening_helper_is_reproducible_and_matches_the_evidence() -> None:
    section = _evidence()["fe_structures"]
    assert section["target"] == FE_KEY
    recorded = {candidate["id"]: candidate for candidate in section["candidates"]}
    for identifier in ("stored", "dative_neutral_bracket"):
        candidate = recorded[identifier]
        fresh = screen_fe_candidate(
            {
                "id": candidate["id"],
                "note": candidate["note"],
                "smiles": candidate["smiles"],
            }
        )
        assert fresh["sanitises"] == candidate["sanitises"]
        assert fresh["fragments"] == candidate["fragments"]
        assert fresh["has_fe_c_bond"] == candidate["has_fe_c_bond"]
        assert fresh["embed_return"] == candidate["embed_return"]


def test_embed_attempts_charge_and_dative_direction_are_recorded() -> None:
    """The reviewer's last Minor: the evidence must show *how* a candidate embedded,
    not just the final return code, and must expose the Fe-C bond order/direction."""

    candidates = {
        candidate["id"]: candidate
        for candidate in _evidence()["fe_structures"]["candidates"]
    }
    best = candidates["dative_neutral_bracket"]
    assert best["default_embed_return"] == -1
    assert best["random_coords_embed_return"] == 0
    assert best["embed_return"] == 0
    assert best["formal_charge"] == 0
    assert len(best["fe_c_bond_types"]) == 5
    assert all(kind.startswith("C->Fe:") for kind in best["fe_c_bond_types"])
    assert all("DATIVE" in kind for kind in best["fe_c_bond_types"])
    assert len(best["fe_c_bond_types"]) == len(best["fe_c_bond_lengths_angstrom"])

    stored = candidates["stored"]
    assert stored["formal_charge"] == 0
    assert stored["fe_c_bond_types"] == []
    assert stored["has_fe_c_bond"] is False


def test_check_flags_a_tampered_recovery_flag() -> None:
    tampered = copy.deepcopy(_evidence())
    key = ION_PAIR_KEYS[0]
    attempts = tampered["ion_pairs"][key]["attempts"]
    frozen = next(a for a in attempts if a["strategy"] == "frozen")
    frozen["frozen_runner_accepts"] = True
    problems = check_payload(tampered)
    assert problems, "flipping an acceptance flag has to be caught"


def test_the_frozen_dataset_digest_is_still_pinned() -> None:
    """The probe must never have moved the dataset it is reasoning about."""

    import hashlib

    digest = hashlib.sha256(DATASET.read_bytes()).hexdigest()
    assert digest == (
        "a446c216874538d900e9f3ebbf18178926b812b77a213a395f4ff8cddfc01085"
    )


def test_local_xtb_prints_its_termination_marker_on_stderr() -> None:
    """Pin the behaviour the acceptance rule leans on, when xTB is installed."""

    try:
        executable = resolve_xtb()
    except FileNotFoundError:
        pytest.skip("xTB binary is not installed on this machine")
    with tempfile.TemporaryDirectory() as directory:
        work = Path(directory)
        (work / "input.xyz").write_text(
            "3\nwater\nO 0.0 0.0 0.0\nH 0.0 0.0 0.96\nH 0.93 0.0 -0.24\n",
            encoding="utf-8",
        )
        completed = subprocess.run(
            [
                str(executable),
                "input.xyz",
                "--scc",
                "--gfn",
                "2",
                "--chrg",
                "0",
                "--uhf",
                "0",
            ],
            cwd=work,
            capture_output=True,
            timeout=300,
            check=False,
        )
    assert completed.returncode == 0
    assert b"normal termination of xtb" not in completed.stdout
    assert b"normal termination of xtb" in completed.stderr
