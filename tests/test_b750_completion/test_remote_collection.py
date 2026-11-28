import importlib.util
import io
import tarfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "remote_collector", ROOT / "scripts/b740_expansion/collect_remote_orca.py"
)
collector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(collector)


def archive(name, symlink=False):
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w:gz") as t:
        member = tarfile.TarInfo(name)
        if symlink:
            member.type = tarfile.SYMTYPE
            member.linkname = "../../outside"
            t.addfile(member)
        else:
            member.size = 4
            t.addfile(member, io.BytesIO(b"test"))
    return stream.getvalue()


@pytest.mark.parametrize(
    "name", ["../outside/job.out", "/jobs/KEY/job.out", "jobs/../job.out", "jobs/KEY/other"]
)
def test_rejects_unsafe_or_unexpected_archive_paths(name):
    with pytest.raises(ValueError):
        list(collector.safe_outputs(archive(name)))


def test_rejects_archive_symlinks():
    with pytest.raises(ValueError):
        list(collector.safe_outputs(archive("jobs/KEY/job.out", symlink=True)))


def test_reads_only_expected_output_layout():
    assert list(collector.safe_outputs(archive("jobs/KEY/job.out"))) == [("KEY", b"test")]
