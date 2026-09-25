from __future__ import annotations

import json
from pathlib import Path

import pytest

from electrolyte_ml.exporting import write_export_manifest
from scripts.verify_export_manifests import (
    default_output_dirs,
    main,
    select_output_dirs,
)


def test_default_export_dirs_cover_all_week_outputs_portably() -> None:
    output_root = Path("portable-output") / "exports"

    output_dirs = default_output_dirs(output_root)

    assert [path.name for path in output_dirs] == [
        "week1",
        "week2",
        "week3",
        "week4",
        "week5",
        "week6",
        "week7",
        "week8",
    ]
    assert all(path.parent == output_root for path in output_dirs)


def test_default_selection_returns_all_eight_paths_even_when_missing(tmp_path) -> None:
    output_root = tmp_path / "exports"

    selected = select_output_dirs(output_root=output_root)

    assert selected == default_output_dirs(output_root)


def test_allow_missing_skips_absent_weeks(tmp_path) -> None:
    output_root = tmp_path / "exports"
    week4 = output_root / "week4"
    week6 = output_root / "week6"
    week4.mkdir(parents=True)
    week6.mkdir(parents=True)
    (week4 / "artifact.txt").write_text("week4\n", encoding="utf-8")
    (week6 / "artifact.txt").write_text("week6\n", encoding="utf-8")
    write_export_manifest(week4)
    write_export_manifest(week6)

    selected = select_output_dirs(
        output_root=output_root,
        allow_missing=True,
    )

    assert selected == (week4, week6)


def test_cli_verifies_existing_week4_and_week6_manifests(
    tmp_path,
    capsys,
) -> None:
    output_root = tmp_path / "exports"
    week4 = output_root / "week4"
    week6 = output_root / "week6"
    week4.mkdir(parents=True)
    week6.mkdir(parents=True)
    (week4 / "artifact.txt").write_text("week4\n", encoding="utf-8")
    (week6 / "artifact.txt").write_text("week6\n", encoding="utf-8")
    write_export_manifest(week4)
    write_export_manifest(week6)

    exit_code = main(
        [
            "--output-root",
            str(output_root),
            "--allow-missing",
            "--json",
        ]
    )

    result = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert result["passed"] is True
    assert {path for path in result["results"]} == {str(week4), str(week6)}


def test_explicit_output_dir_only_verifies_requested_directory(
    tmp_path,
    capsys,
) -> None:
    week6 = tmp_path / "exports" / "week6"
    week6.mkdir(parents=True)
    (week6 / "artifact.txt").write_text("week6\n", encoding="utf-8")
    write_export_manifest(week6)

    exit_code = main(
        [
            "--output-root",
            str(tmp_path / "does-not-exist"),
            "--output-dir",
            str(week6),
            "--json",
        ]
    )

    result = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert result["passed"] is True
    assert set(result["results"]) == {str(week6)}


def test_missing_output_root_fails_with_explicit_errors(tmp_path, capsys) -> None:
    output_root = tmp_path / "missing-exports"

    exit_code = main(
        [
            "--output-root",
            str(output_root),
            "--json",
        ]
    )

    result = json.loads(capsys.readouterr().out)
    assert exit_code != 0
    assert result["passed"] is False
    assert len(result["results"]) == 8
    assert all(
        any("missing manifest" in error for error in errors)
        for errors in result["results"].values()
    )


def test_allow_missing_with_zero_directories_is_an_error(tmp_path) -> None:
    with pytest.raises(ValueError, match="no output directories selected"):
        select_output_dirs(
            output_root=tmp_path / "missing-exports",
            allow_missing=True,
        )
