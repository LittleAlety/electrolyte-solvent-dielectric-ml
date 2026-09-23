"""Tests for the search-material registrar.

The registrar itself is never wired into CI, because the directory it walks
(`搜索资料`) only exists on the author's machine and holds publisher PDFs and
screenshots that must never reach the repository.  Its *rules* are still worth
testing on a throwaway tree, which is outside the repository and so passes the
same external-root guard the real run does.
"""

from __future__ import annotations

import csv
import subprocess
import sys
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "scripts"))

from register_search_material import (
    DEFAULT_ROOT,
    MANIFEST_DIR_NAME,
    REGISTRY_NAME,
    RegistrationError,
    artifact_id_for,
    build_row,
    classify_usable_as_data,
    collect_artifacts,
    ensure_root_is_external,
    main,
    read_existing_registry,
    sha256_file,
    source_family_for,
)


def test_rejects_a_root_inside_the_repository() -> None:
    with pytest.raises(RegistrationError):
        ensure_root_is_external(REPOSITORY_ROOT)
    with pytest.raises(RegistrationError):
        ensure_root_is_external(REPOSITORY_ROOT / "data")


def test_accepts_a_root_outside_the_repository(tmp_path: Path) -> None:
    ensure_root_is_external(tmp_path)


@pytest.mark.parametrize(
    ("relative_path", "artifact_type", "expected"),
    [
        # Only a full-value export can be data.
        ("springermaterials/licensed_pages/table.csv", "csv_export", True),
        ("springermaterials/licensed_pages/table.xlsx", "xlsx_export", True),
        # A screenshot of a search page shows counts, not values.
        ("springermaterials/public_metadata/search.png", "screenshot", False),
        ("nbs514/circular514.pdf", "pdf", False),
        ("nbs514/notes.md", "manual_note", False),
        # A preview or search-result file is never a data source, whatever its
        # extension claims.
        ("springermaterials/public_metadata/dec_c31.csv", "csv_export", False),
        ("springermaterials/preview/export.xlsx", "xlsx_export", False),
        ("springermaterials/search_results/table.csv", "csv_export", False),
    ],
)
def test_classify_usable_as_data(
    relative_path: str, artifact_type: str, expected: bool
) -> None:
    assert classify_usable_as_data(relative_path, artifact_type) is expected


def test_source_family_falls_back_to_other() -> None:
    assert source_family_for("nbs514/page.pdf") == "nbs514"
    assert source_family_for("springermaterials/x/y.csv") == "springermaterials"
    assert source_family_for("mystery/file.csv") == "other"
    # Captured material always lands in a subdirectory, so a root-level file is
    # authored scaffolding rather than third-party content.
    assert source_family_for("README.md") == "authored"


def test_root_level_files_do_not_inherit_restricted_defaults(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# notes\n", encoding="utf-8")
    (tmp_path / "acquisition_requests.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    artifacts = collect_artifacts(tmp_path)
    assert len(artifacts) == 2
    for artifact in artifacts:
        row = build_row(artifact, previous=None, now="2026-09-23T00:00:00Z")
        assert row["source_family"] == "authored"
        assert row["closed_source"] == "false"
        assert row["non_redistributable"] == "false"
        assert row["redistribution_status"] == "allowed"
        assert row["access_authorization"] == "n/a"
        # A worklist is not measurement data, whatever its extension says.
        assert row["usable_as_data"] == "false"


def test_artifact_id_is_stable_and_path_derived() -> None:
    first = artifact_id_for("nbs514/page.pdf")
    assert first == artifact_id_for("nbs514/page.pdf")
    assert first != artifact_id_for("nbs514/other.pdf")
    assert first.startswith("sm:")


def _make_tree(root: Path) -> None:
    (root / "nbs514").mkdir(parents=True)
    (root / "nbs514" / "circular514.pdf").write_bytes(b"%PDF-1.4 fake")
    (root / "springermaterials" / "public_metadata").mkdir(parents=True)
    (root / "springermaterials" / "public_metadata" / "search.png").write_bytes(b"fakepng")


def test_collect_artifacts_skips_derived_outputs(tmp_path: Path) -> None:
    _make_tree(tmp_path)
    # The manifest directory holds the registry itself, and a root SHA256SUMS is
    # regenerated every run; registering either would make the registry hash
    # itself and never verify again.
    (tmp_path / MANIFEST_DIR_NAME).mkdir()
    (tmp_path / MANIFEST_DIR_NAME / REGISTRY_NAME).write_text("x", encoding="utf-8")
    (tmp_path / "SHA256SUMS").write_text("y", encoding="utf-8")

    paths = {artifact.relative_path for artifact in collect_artifacts(tmp_path)}
    assert paths == {
        "nbs514/circular514.pdf",
        "springermaterials/public_metadata/search.png",
    }


def test_build_row_defaults_to_restricted(tmp_path: Path) -> None:
    _make_tree(tmp_path)
    # Deliberately the springermaterials artifact: the nbs514 one is public by
    # design, so it cannot test the restricted default.
    artifact = next(
        item
        for item in collect_artifacts(tmp_path)
        if item.relative_path.startswith("springermaterials/")
    )
    row = build_row(artifact, previous=None, now="2026-09-23T00:00:00Z")
    assert row["closed_source"] == "true"
    assert row["non_redistributable"] == "true"
    assert row["redistribution_status"] == "unclear"
    assert row["access_authorization"] == "unknown"
    assert row["usable_as_data"] == "false"


def test_build_row_treats_nbs514_as_public(tmp_path: Path) -> None:
    _make_tree(tmp_path)
    artifact = next(
        item
        for item in collect_artifacts(tmp_path)
        if item.relative_path.startswith("nbs514/")
    )
    row = build_row(artifact, previous=None, now="2026-09-23T00:00:00Z")
    assert row["closed_source"] == "false"
    assert row["access_authorization"] == "public"


def test_build_row_preserves_hand_edited_provenance(tmp_path: Path) -> None:
    _make_tree(tmp_path)
    artifact = collect_artifacts(tmp_path)[0]
    previous = {
        "source_url": "https://example.invalid/dec_c31",
        "retrieved_at": "2026-09-20",
        "access_authorization": "institutional",
        "notes": "captured while logged in",
    }
    row = build_row(artifact, previous=previous, now="2026-09-23T00:00:00Z")
    assert row["source_url"] == "https://example.invalid/dec_c31"
    assert row["retrieved_at"] == "2026-09-20"
    assert row["access_authorization"] == "institutional"
    assert row["notes"] == "captured while logged in"
    # Derived columns are still refreshed.
    assert row["added_at"] == "2026-09-23T00:00:00Z"


def test_register_then_verify_round_trip(tmp_path: Path) -> None:
    _make_tree(tmp_path)
    assert main(["--root", str(tmp_path)]) == 0

    registry = tmp_path / MANIFEST_DIR_NAME / REGISTRY_NAME
    assert registry.is_file()
    assert (tmp_path / "SHA256SUMS").is_file()

    rows = read_existing_registry(registry)
    assert set(rows) == {
        "nbs514/circular514.pdf",
        "springermaterials/public_metadata/search.png",
    }
    assert main(["--root", str(tmp_path), "--verify"]) == 0


def test_verify_detects_a_changed_artifact(tmp_path: Path) -> None:
    _make_tree(tmp_path)
    assert main(["--root", str(tmp_path)]) == 0
    (tmp_path / "nbs514" / "circular514.pdf").write_bytes(b"%PDF-1.4 tampered")
    assert main(["--root", str(tmp_path), "--verify"]) == 1


def test_verify_detects_an_unregistered_file(tmp_path: Path) -> None:
    _make_tree(tmp_path)
    assert main(["--root", str(tmp_path)]) == 0
    (tmp_path / "nbs514" / "sneaked_in.pdf").write_bytes(b"%PDF-1.4")
    assert main(["--root", str(tmp_path), "--verify"]) == 1


def test_repeated_runs_are_idempotent(tmp_path: Path) -> None:
    _make_tree(tmp_path)
    assert main(["--root", str(tmp_path)]) == 0
    first = (tmp_path / MANIFEST_DIR_NAME / REGISTRY_NAME).read_text(encoding="utf-8")
    assert main(["--root", str(tmp_path)]) == 0
    second = (tmp_path / MANIFEST_DIR_NAME / REGISTRY_NAME).read_text(encoding="utf-8")
    assert first == second


def test_missing_root_exits_cleanly(tmp_path: Path) -> None:
    # Absent on CI and on any machine that has not captured material yet.
    assert main(["--root", str(tmp_path / "does_not_exist")]) == 0


def test_registry_columns_are_written_in_order(tmp_path: Path) -> None:
    _make_tree(tmp_path)
    assert main(["--root", str(tmp_path)]) == 0
    with (tmp_path / MANIFEST_DIR_NAME / REGISTRY_NAME).open(
        encoding="utf-8", newline=""
    ) as handle:
        header = next(csv.reader(handle))
    assert header[0] == "artifact_id"
    assert "closed_source" in header
    assert "redistribution_status" in header
    assert header[-1] == "notes"


def test_verify_rejects_contradictory_provenance(tmp_path: Path) -> None:
    """A closed source must never also be declared freely redistributable."""

    _make_tree(tmp_path)
    assert main(["--root", str(tmp_path)]) == 0
    registry = tmp_path / MANIFEST_DIR_NAME / REGISTRY_NAME
    rows = list(csv.DictReader(registry.read_text(encoding="utf-8").splitlines()))
    for row in rows:
        if row["relative_path"].startswith("springermaterials/"):
            row["closed_source"] = "true"
            row["redistribution_status"] = "allowed"
    with registry.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    assert main(["--root", str(tmp_path), "--verify"]) == 1


def test_no_tracked_file_is_copied_from_the_search_archive() -> None:
    """Guard the repository/archive boundary mechanically.

    `搜索资料` holds publisher PDFs and screenshots that must never be committed.
    Comparing hashes rather than paths catches a copy that was renamed.
    """

    archive = DEFAULT_ROOT
    if not archive.is_dir():
        pytest.skip("search archive is not present on this machine")

    listed = subprocess.run(
        ["git", "ls-files"],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    tracked_hashes = {
        sha256_file(REPOSITORY_ROOT / relative)
        for relative in listed.stdout.split()
        if (REPOSITORY_ROOT / relative).is_file()
    }
    archived_hashes = {
        artifact.sha256 for artifact in collect_artifacts(archive)
    }
    duplicated = tracked_hashes & archived_hashes
    assert not duplicated, (
        f"{len(duplicated)} tracked file(s) are byte-identical to archived "
        "search material and must not be committed"
    )
