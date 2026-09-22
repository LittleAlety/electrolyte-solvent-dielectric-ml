from __future__ import annotations

import concurrent.futures
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

from electrolyte_ml.thermoml import DownloadError
from scripts import fetch_thermoml
from scripts.fetch_thermoml import _destinations_for_urls, _migrate_legacy_download


def test_page_size_zero_is_rejected_by_argparse() -> None:
    script = Path(__file__).resolve().parents[1] / "scripts" / "fetch_thermoml.py"

    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--page-size",
            "0",
            "--dry-run",
            "--url",
            "https://example.test/sample.xml",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "--page-size must be a positive integer" in result.stderr


def test_normalize_help_marks_metadata_sidecar_required() -> None:
    script = Path(__file__).resolve().parents[1] / "scripts" / "normalize_thermoml.py"

    result = subprocess.run(
        [sys.executable, str(script), "--help"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    help_text = " ".join(result.stdout.split())
    assert "optional .meta.json sidecars" not in help_text
    assert "required .meta.json sidecars" in help_text


def test_legacy_download_is_migrated_to_stable_name(tmp_path: Path) -> None:
    url = "https://trc.nist.gov/ThermoML/10.1021/je600515j.xml"
    stable_name = _destinations_for_urls([url])[0]
    legacy_path = tmp_path / "je600515j.xml"
    legacy_metadata_path = legacy_path.with_name(legacy_path.name + ".meta.json")
    legacy_path.write_text("<DataReport/>", encoding="utf-8")
    legacy_metadata_path.write_text(
        json.dumps({"url": url, "sha256": "legacy-hash"}),
        encoding="utf-8",
    )
    destination = tmp_path / stable_name

    migrated = _migrate_legacy_download(url, tmp_path, destination)
    repeated = _migrate_legacy_download(url, tmp_path, destination)

    assert migrated == destination
    assert repeated == destination
    assert destination.is_file()
    assert destination.with_name(destination.name + ".meta.json").is_file()
    assert not legacy_path.exists()
    assert not legacy_metadata_path.exists()
    assert sorted(path.name for path in tmp_path.glob("*.xml")) == [destination.name]


def _write_legacy_download(
    path: Path,
    url: str,
    body: bytes,
) -> None:
    path.write_bytes(body)
    path.with_name(path.name + ".meta.json").write_text(
        json.dumps(
            {
                "url": url,
                "sha256": hashlib.sha256(body).hexdigest(),
            }
        ),
        encoding="utf-8",
    )


def test_stable_and_legacy_with_same_hash_quarantines_legacy(
    tmp_path: Path,
) -> None:
    url = "https://trc.nist.gov/ThermoML/10.1021/je600515j.xml"
    body = b"<DataReport>same</DataReport>"
    stable_name = _destinations_for_urls([url])[0]
    stable_path = tmp_path / stable_name
    legacy_path = tmp_path / "je600515j.xml"
    _write_legacy_download(stable_path, url, body)
    _write_legacy_download(legacy_path, url, body)

    result = _migrate_legacy_download(url, tmp_path, stable_path)

    assert result == stable_path
    assert stable_path.read_bytes() == body
    assert not legacy_path.exists()
    assert (tmp_path / "je600515j.xml.migrated").read_bytes() == body
    assert sorted(path.name for path in tmp_path.glob("*.xml")) == [stable_name.name]


def test_multiple_legacy_candidates_with_conflicting_hashes_raise(
    tmp_path: Path,
) -> None:
    url = "https://trc.nist.gov/ThermoML/10.1021/je600515j.xml"
    first = tmp_path / "first.xml"
    second = tmp_path / "second.xml"
    _write_legacy_download(first, url, b"<DataReport>first</DataReport>")
    _write_legacy_download(second, url, b"<DataReport>second</DataReport>")
    destination = tmp_path / _destinations_for_urls([url])[0]

    with pytest.raises(DownloadError, match="conflicting hashes"):
        _migrate_legacy_download(url, tmp_path, destination)

    assert first.is_file()
    assert second.is_file()
    assert not destination.exists()


def test_multiple_legacy_candidates_with_same_hash_keep_one_stable_copy(
    tmp_path: Path,
) -> None:
    url = "https://trc.nist.gov/ThermoML/10.1021/je600515j.xml"
    body = b"<DataReport>same</DataReport>"
    first = tmp_path / "first.xml"
    second = tmp_path / "second.xml"
    _write_legacy_download(first, url, body)
    _write_legacy_download(second, url, body)
    destination = tmp_path / _destinations_for_urls([url])[0]

    result = _migrate_legacy_download(url, tmp_path, destination)

    assert result == destination
    assert destination.read_bytes() == body
    assert sorted(path.name for path in tmp_path.glob("*.xml")) == [destination.name]
    assert (tmp_path / "second.xml.migrated").is_file()


def test_legacy_migration_rolls_back_when_sidecar_replace_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    url = "https://trc.nist.gov/ThermoML/10.1021/je600515j.xml"
    legacy_path = tmp_path / "je600515j.xml"
    _write_legacy_download(legacy_path, url, b"<DataReport/>")
    destination = tmp_path / _destinations_for_urls([url])[0]
    real_replace = fetch_thermoml.os.replace
    calls = 0

    def fail_sidecar(source: Path, target: Path) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("sidecar replace failed")
        real_replace(source, target)

    monkeypatch.setattr(fetch_thermoml.os, "replace", fail_sidecar)

    with pytest.raises(DownloadError, match="migration failed"):
        _migrate_legacy_download(url, tmp_path, destination)

    assert legacy_path.is_file()
    assert legacy_path.with_name(legacy_path.name + ".meta.json").is_file()
    assert not destination.exists()


def test_concurrent_migration_keeps_one_stable_copy(tmp_path: Path) -> None:
    url = "https://trc.nist.gov/ThermoML/10.1021/je600515j.xml"
    legacy_path = tmp_path / "je600515j.xml"
    _write_legacy_download(legacy_path, url, b"<DataReport/>")
    destination = tmp_path / _destinations_for_urls([url])[0]
    barrier = concurrent.futures.ThreadPoolExecutor(max_workers=2)
    real_replace = fetch_thermoml.os.replace

    def slow_replace(source: Path, target: Path) -> None:
        time.sleep(0.1)
        real_replace(source, target)

    fetch_thermoml.os.replace = slow_replace
    try:
        with barrier as executor:
            results = list(
                executor.map(
                    lambda _: _migrate_legacy_download(url, tmp_path, destination),
                    range(2),
                )
            )
    finally:
        fetch_thermoml.os.replace = real_replace

    assert results == [destination, destination]
    assert destination.is_file()
    assert sorted(path.name for path in tmp_path.glob("*.xml")) == [destination.name]
