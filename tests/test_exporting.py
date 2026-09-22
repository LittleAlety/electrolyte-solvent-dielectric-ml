from __future__ import annotations

import hashlib

from electrolyte_ml.exporting import (
    canonical_text_sha256,
    verify_export_manifest,
    write_export_manifest,
)


def _write(path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def test_manifest_covers_all_files_excluding_itself_and_is_sorted(tmp_path) -> None:
    _write(tmp_path / "z.txt", b"z")
    _write(tmp_path / "nested" / "a.txt", b"a")
    manifest_path = tmp_path / "SHA256SUMS"
    manifest_path.write_text("stale\n", encoding="utf-8")

    write_export_manifest(tmp_path)

    lines = manifest_path.read_text(encoding="utf-8").splitlines()
    assert [line.split("  ", 1)[1] for line in lines] == [
        "nested/a.txt",
        "z.txt",
    ]
    for line in lines:
        digest, relative_path = line.split("  ", 1)
        actual = hashlib.sha256((tmp_path / relative_path).read_bytes()).hexdigest()
        assert digest == actual
    assert verify_export_manifest(tmp_path) == []


def test_manifest_does_not_include_itself_recursively(tmp_path) -> None:
    _write(tmp_path / "a.txt", b"a")

    write_export_manifest(tmp_path)
    first = (tmp_path / "SHA256SUMS").read_bytes()
    write_export_manifest(tmp_path)
    second = (tmp_path / "SHA256SUMS").read_bytes()

    assert first == second
    assert "SHA256SUMS" not in second.decode("utf-8")


def test_manifest_verification_fails_after_file_tampering(tmp_path) -> None:
    _write(tmp_path / "a.txt", b"a")
    write_export_manifest(tmp_path)
    (tmp_path / "a.txt").write_bytes(b"tampered")

    errors = verify_export_manifest(tmp_path)

    assert errors
    assert "hash mismatch" in errors[0]


def test_manifest_verification_fails_after_manifest_tampering(tmp_path) -> None:
    _write(tmp_path / "a.txt", b"a")
    write_export_manifest(tmp_path)
    manifest_path = tmp_path / "SHA256SUMS"
    manifest_path.write_text(
        manifest_path.read_text(encoding="utf-8").replace("a.txt", "b.txt"),
        encoding="utf-8",
    )

    errors = verify_export_manifest(tmp_path)

    assert errors
    assert "missing manifest entry" in errors[0]


def test_manifest_detects_unlisted_file(tmp_path) -> None:
    _write(tmp_path / "a.txt", b"a")
    write_export_manifest(tmp_path)
    _write(tmp_path / "extra.txt", b"extra")

    errors = verify_export_manifest(tmp_path)

    assert errors
    assert "unlisted file" in errors[0]


def test_canonical_text_sha256_normalizes_line_endings(tmp_path) -> None:
    lf_path = tmp_path / "lf.csv"
    crlf_path = tmp_path / "crlf.csv"
    lf_path.write_bytes(b"a,b\n1,2\n")
    crlf_path.write_bytes(b"a,b\r\n1,2\r\n")

    assert canonical_text_sha256(lf_path) == canonical_text_sha256(crlf_path)


def test_canonical_text_sha256_detects_real_content_change(tmp_path) -> None:
    path = tmp_path / "table.csv"
    path.write_bytes(b"a,b\n1,2\n")
    before = canonical_text_sha256(path)
    path.write_bytes(b"a,b\n1,3\n")

    assert canonical_text_sha256(path) != before
