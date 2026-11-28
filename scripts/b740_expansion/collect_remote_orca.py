"""Collect normally terminated B742 outputs without changing queued jobs.

Requires optional dependency paramiko. Uses existing known_hosts and a supplied
SSH key; unknown hosts are refused. The complete manifest remains the denominator.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import shlex
import tarfile
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath


def safe_outputs(archive: bytes):
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as tar:
        for member in tar.getmembers():
            parts = PurePosixPath(member.name).parts
            if (
                len(parts) != 3
                or parts[0] != "jobs"
                or parts[2] != "job.out"
                or parts[1] in (".", "..")
                or not member.isfile()
            ):
                raise ValueError(f"Unexpected archive member: {member.name}")
            yield parts[1], tar.extractfile(member).read()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--key", type=Path, required=True)
    p.add_argument("--known-hosts", type=Path, required=True)
    p.add_argument("--host", default="202.114.96.180")
    p.add_argument("--username", default="pengqihang")
    p.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parents[2]
        / "outputs/b740_expansion/dft_expansion/results_opt",
    )
    p.add_argument("--remote-dir", default="/project/pengqihang/b742/package_opt")
    a = p.parse_args()
    import paramiko

    remote = a.remote_dir
    if not remote.startswith("/project/pengqihang/b742/") or ".." in PurePosixPath(remote).parts:
        raise ValueError("Remote directory must stay within the B742 project")
    client = paramiko.SSHClient()
    client.load_host_keys(str(a.known_hosts))
    client.connect(
        a.host,
        username=a.username,
        key_filename=str(a.key),
        timeout=20,
        auth_timeout=20,
        banner_timeout=20,
    )
    try:
        _, out, err = client.exec_command("squeue -u " + shlex.quote(a.username), timeout=30)
        queue = out.read().decode("utf-8", errors="replace")
        queue_error = err.read().decode("utf-8", errors="replace")
        command = (
            "cd " + shlex.quote(remote) + " && grep -l 'ORCA TERMINATED NORMALLY' "
            "jobs/*/job.out | tar czf - -T -"
        )
        _, out, err = client.exec_command(command, timeout=180)
        archive = out.read()
        archive_error = err.read().decode("utf-8", errors="replace")
        exit_status = out.channel.recv_exit_status()
        if exit_status != 0:
            raise RuntimeError(f"Remote archive failed: {exit_status}: {archive_error}")
        payload = list(safe_outputs(archive))
    finally:
        client.close()
    repo = Path(__file__).resolve().parents[2]
    manifest = json.loads(
        (repo / "outputs/b740_expansion/dft_expansion/package_opt/manifest.json").read_text(
            encoding="utf-8"
        )
    )
    expected = {j["inchikey"] for j in manifest["jobs"]}
    if any(ik not in expected for ik, _ in payload):
        raise ValueError("Remote outputs include an identity outside the frozen package")
    entries = []
    for ik, raw in payload:
        dest = a.output_dir / "jobs" / ik / "job.out"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(raw)
        entries.append(
            {"inchikey": ik, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
        )
    a.output_dir.mkdir(parents=True, exist_ok=True)
    doc = {
        "schema": "b740.remote_collection/v1",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "remote_dir": remote,
        "selection": "normal termination marker; parser validation required",
        "n_collected": len(entries),
        "n_expected": manifest["n_jobs"],
        "files": entries,
        "queue_snapshot": queue,
        "queue_error": queue_error,
        "archive_error": archive_error,
    }
    (a.output_dir / "collection_manifest.json").write_text(
        json.dumps(doc, indent=2), encoding="utf-8"
    )
    print(json.dumps({"n_collected": len(entries), "n_expected": manifest["n_jobs"]}))


if __name__ == "__main__":
    main()
