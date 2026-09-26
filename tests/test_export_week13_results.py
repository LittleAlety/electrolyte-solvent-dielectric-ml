"""Delivery-package regression tests for the Week 13 export."""

from __future__ import annotations

import json
import shlex
import subprocess
from pathlib import Path

import pytest

from electrolyte_ml.exporting import verify_export_manifest
from probes.export_week13_results import (
    ARTIFACTS,
    FROZEN_DIGEST,
    PREREG_SHA256,
    README_TEXT,
    VERIFIERS,
    WEEK,
    export_results,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def exported(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, dict]:
    root = tmp_path_factory.mktemp("week13")
    return root, export_results(output_root=root, overwrite=False)


def test_every_declared_artifact_exists_in_the_repository() -> None:
    missing = [source for source, _ in ARTIFACTS if not (REPOSITORY_ROOT / source).is_file()]
    assert missing == []


def test_export_ships_every_artifact_readme_manifest_and_verification(
    exported: tuple[Path, dict],
) -> None:
    root, result = exported
    week_root = root / WEEK

    assert result["verification_passed"] is True
    for _, destination in ARTIFACTS:
        assert (week_root / destination).is_file()
    for name in ("README.md", "week13_summary.json", "verification.json", "SHA256SUMS"):
        assert (week_root / name).is_file()
    assert verify_export_manifest(week_root) == []


def test_export_refuses_to_overwrite_without_the_flag(tmp_path: Path) -> None:
    export_results(output_root=tmp_path, overwrite=False)
    with pytest.raises(FileExistsError):
        export_results(output_root=tmp_path, overwrite=False)

    again = export_results(output_root=tmp_path, overwrite=True)
    assert again["verification_passed"] is True


def test_declared_verifiers_are_real_scripts() -> None:
    for command in VERIFIERS:
        parts = shlex.split(command)
        if parts[0] == "-m":
            assert len(parts) >= 3 and parts[1] == "pytest", command
            for target in parts[2:]:
                if target.endswith(".py"):
                    assert (REPOSITORY_ROOT / target).is_file(), command
            continue
        assert (REPOSITORY_ROOT / parts[0]).is_file(), command


def test_summary_pins_the_frozen_dataset_and_the_current_prereg_revision(
    exported: tuple[Path, dict],
) -> None:
    root, _ = exported
    summary = json.loads((root / WEEK / "week13_summary.json").read_text(encoding="utf-8"))

    assert summary["frozen_dataset"]["sha256"] == FROZEN_DIGEST
    assert summary["frozen_dataset"]["unchanged"] is True
    assert summary["preregistration"]["sha256"] == PREREG_SHA256
    assert summary["preregistration"]["is_the_current_revision"] is True


def test_summary_records_the_stage_1_pilot_as_a_non_verdict(
    exported: tuple[Path, dict],
) -> None:
    root, _ = exported
    summary = json.loads((root / WEEK / "week13_summary.json").read_text(encoding="utf-8"))
    pilot = summary["stage_1_pilot"]

    assert pilot["label"] == "stage_1_pilot_not_a_verdict"
    assert pilot["not_a_verdict"] is True
    assert pilot["verdict_eligible"] is False
    assert pilot["pool"]["rows"] == 236
    assert pilot["pool"]["matches_the_pin"] is True
    assert pilot["pool"]["size_by_list"] == {"solvent": 236}

    recall = pilot["C1_recall_at_K"]
    assert recall["K"] == 20
    assert recall["hits_in_dielectric_solvent_list"] == 0
    assert recall["passed_in_this_channel"] is False
    assert recall["champion_ranks"] == {"EC": 24, "PC": 58}

    ec = pilot["C2_solvent"]["EC"]
    pc = pilot["C2_solvent"]["PC"]
    assert ec["truth_dielectric"] == 90.5
    assert pc["truth_dielectric"] == 64.9
    assert ec["predicted_dielectric"] == pytest.approx(23.05650945343228)
    assert pc["predicted_dielectric"] == pytest.approx(17.043769200900982)
    assert ec["delta_log10"] == pytest.approx(-0.5938550195186852)
    assert pc["delta_log10"] == pytest.approx(-0.5806790522537534)
    assert ec["within_c2_tolerance"] is False
    assert pc["within_c2_tolerance"] is False

    assert pilot["C3"] == "c3_not_run_stage_1_pilot"
    assert pilot["C2_additive"] == "not_run_stage_1_pilot_redox_channel_not_executed"

    anchor = pilot["regression_anchor"]
    assert anchor["status"] == "aligned"
    assert anchor["max_abs_metric_diff"] == 0.0
    assert anchor["row_values_compared"] == 14160
    assert anchor["row_value_mismatches"] == []

    assert pilot["temperature_check"] == {
        "EC": {"frozen_table_T_K": 313.15, "prereg_truth_T_K": 313.15, "consistent": True},
        "PC": {"frozen_table_T_K": 298.15, "prereg_truth_T_K": 298.15, "consistent": True},
    }


def test_summary_records_the_outlet_2_gate_as_two_of_four(
    exported: tuple[Path, dict],
) -> None:
    root, _ = exported
    summary = json.loads((root / WEEK / "week13_summary.json").read_text(encoding="utf-8"))
    outlet = summary["outlet_2"]

    assert outlet["pool_rows"] == 29515
    assert outlet["pool_matches_the_pin"] is True
    assert outlet["unit"] == "eV"

    gate = outlet["gate"]
    assert gate["threshold_mae"] == 0.2
    assert gate["passed"] is False
    assert gate["targets_passed"] == 2
    assert gate["targets_total"] == 4
    mae = gate["best_model_mae"]
    assert mae["LUMO"] == pytest.approx(0.13855083976437643)
    assert mae["HOMO"] == pytest.approx(0.19050925839013938)
    assert mae["IP"] == pytest.approx(0.2010970559642009)
    assert mae["EA"] == pytest.approx(0.23415453202842548)

    assert outlet["per_target_pass"] == {
        "LUMO": True,
        "HOMO": True,
        "IP": False,
        "EA": False,
    }
    # The protocol was not downgraded: the shipped run really is 5x10.
    protocol = outlet["cv_protocol"]
    assert protocol["n_splits"] == 5
    assert protocol["n_repeats"] == 10
    assert protocol["random_state"] == 42
    assert protocol["deviation"]["deviates_from_project_standard"] is False


def test_summary_records_the_redox_v2_gate_as_still_red(
    exported: tuple[Path, dict],
) -> None:
    root, _ = exported
    summary = json.loads((root / WEEK / "week13_summary.json").read_text(encoding="utf-8"))
    redox = summary["redox_v2"]

    assert redox["gate"]["threshold_mae"] == 0.15
    assert redox["gate"]["passed"] is False
    assert redox["gate"]["best_model_mae"]["oxidation_free_energy"] == pytest.approx(
        0.2174014393126818
    )
    assert redox["gate"]["best_model_mae"]["reduction_free_energy"] == pytest.approx(
        0.33169277465193164
    )
    cv = redox["gate_repeated_cv"]
    assert cv["passed"] is False
    assert cv["best_model_mae"]["oxidation_free_energy"] == pytest.approx(0.20608489698122529)
    assert cv["best_model_mae"]["reduction_free_energy"] == pytest.approx(0.31834980213720787)
    assert redox["verdict"]["gate_passed"] is False
    assert redox["verdict"]["gate_passed_repeated_cv"] is False
    # The anchors still reproduce the frozen v1 numbers exactly.
    anchors = redox["anchors"]
    assert anchors["matches"] is True
    assert anchors["expected_test_id_hash"] == anchors["reproduced_test_id_hash"]
    assert anchors["reproduced_v1_oxidation_linear"]["mae"] == pytest.approx(0.2905180517963865)
    assert anchors["reproduced_v1_oxidation_linear"]["r2"] == pytest.approx(0.9443164629360373)


def test_the_git_ignored_homo_lumo_tables_are_copied_byte_for_byte(
    exported: tuple[Path, dict],
) -> None:
    """``data/processed/*`` never reaches git, so the package is the archive."""

    root, _ = exported
    week_root = root / WEEK
    for source in (
        "data/processed/l3_homo_lumo_repeated_cv.csv",
        "data/processed/l3_homo_lumo_cv_predictions.csv",
    ):
        name = Path(source).name
        shipped = week_root / "data_processed" / name
        assert shipped.is_file(), source
        assert shipped.read_bytes() == (REPOSITORY_ROOT / source).read_bytes(), source


def test_the_homo_lumo_tables_really_are_ignored_by_git() -> None:
    """The archive blind spot is a fact about the repository, so pin it."""

    for path in (
        "data/processed/l3_homo_lumo_repeated_cv.csv",
        "data/processed/l3_homo_lumo_cv_predictions.csv",
    ):
        completed = subprocess.run(
            ["git", "check-ignore", "--quiet", path],
            cwd=REPOSITORY_ROOT,
            check=False,
        )
        assert completed.returncode == 0, f"{path} is no longer git-ignored"


def test_the_ubj_weights_are_not_shipped_and_the_json_records_their_hashes(
    exported: tuple[Path, dict],
) -> None:
    root, _ = exported
    week_root = root / WEEK

    assert list(week_root.rglob("*.ubj")) == []
    assert not (week_root / "models").exists()

    baselines = json.loads((week_root / "homo_lumo_baselines.json").read_text(encoding="utf-8"))
    recorded = {
        target: block["model"]["artifact"] for target, block in baselines["targets"].items()
    }
    assert sorted(recorded) == ["EA", "HOMO", "IP", "LUMO"]
    for target, artifact in recorded.items():
        repo_weight = REPOSITORY_ROOT / artifact["path"]
        assert repo_weight.is_file(), target
        assert artifact["path"].endswith(".ubj")
        assert len(artifact["sha256"]) == 64
        assert not (week_root / Path(artifact["path"]).name).exists()


def test_readme_carries_the_non_negotiable_wording(exported: tuple[Path, dict]) -> None:
    root, _ = exported
    readme = (root / WEEK / "README.md").read_text(encoding="utf-8")

    # The pilot is not a verdict, and the README says so explicitly.
    assert "stage_1_pilot_not_a_verdict" in readme
    assert "这不是判决" in readme
    assert "只管四通道完整跑批" in readme
    # Outlet 2 is 2/4, not "usable".
    assert "2/4" in readme
    # The redox improvement is directional evidence only.
    assert "方向证据" in readme
    assert "不得进任何对外文本" in readme
    # The archive story: current prereg, week12 copy is historical, CSVs and
    # weights live where they live.
    # The README names the *current* revision (advanced by amendment_3) and keeps
    # the previous week-13 snapshot's digest as an explicitly superseded label.
    assert "77f61a83" in readme
    assert "39cc5e67" in readme
    assert "已由 amendment_3 修订覆盖" in readme
    assert "历史修订" in readme
    assert "唯一归档途径" in readme
    assert "权重不在包里" in readme
    assert README_TEXT == readme

