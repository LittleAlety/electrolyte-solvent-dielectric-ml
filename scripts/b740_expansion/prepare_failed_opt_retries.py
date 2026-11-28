"""Isolated same-method restarts; original outputs and queued jobs stay intact."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "outputs/b740_expansion/dft_expansion"
REMOTE = "/project/pengqihang/b742/retry_opt_20261126"


def xyz_symbols(text):
    lines = text.splitlines()
    n = int(lines[0])
    atoms = lines[2 : 2 + n]
    if len(atoms) != n or any(len(line.split()) != 4 for line in atoms):
        raise ValueError("Malformed XYZ")
    for line in atoms:
        if any(not math.isfinite(float(x)) for x in line.split()[1:]):
            raise ValueError("Nonfinite coordinate")
    return [line.split()[0] for line in atoms]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--key", type=Path, required=True)
    parser.add_argument("--known-hosts", type=Path, required=True)
    parser.add_argument("--submit", action="store_true")
    args = parser.parse_args()
    import paramiko

    package = ROOT / "outputs/b750_completion/retry_opt"
    receipt = package / "submission_record.json"
    if args.submit and receipt.exists():
        raise ValueError("Submission recorded; refusing duplicate jobs")
    failures = json.loads((BASE / "results_opt/validation/failure_certificates.json").read_text())
    failures = [
        r for r in failures if r["status"] == "REJECTED" and r.get("terminated_normally") is True
    ]
    if not failures:
        raise ValueError("No rejected normally terminated jobs")
    client = paramiko.SSHClient()
    client.load_host_keys(str(args.known_hosts))
    client.connect("202.114.96.180", username="pengqihang", key_filename=str(args.key), timeout=20)
    sftp = client.open_sftp()
    records = []
    try:
        for failed in failures:
            ik = failed["inchikey"]
            original = BASE / "package_opt/jobs" / ik
            with sftp.open(
                "/project/pengqihang/b742/package_opt/jobs/" + ik + "/job.xyz", "rb"
            ) as handle:
                xyz = handle.read().decode()
            if xyz_symbols(xyz) != xyz_symbols((original / "geom.xyz").read_text()):
                raise ValueError("Restart atom order changed: " + ik)
            inp = (original / "job.inp").read_text()
            if "%geom" in inp.lower():
                raise ValueError("Existing geometry controls need review")
            inp = inp.replace("* xyzfile", "%geom\n  MaxIter 300\nend\n\n* xyzfile")
            dest = package / "jobs" / ik
            dest.mkdir(parents=True, exist_ok=True)
            (dest / "geom.xyz").write_text(xyz, encoding="utf-8", newline="\n")
            (dest / "job.inp").write_text(inp, encoding="utf-8", newline="\n")
            records.append(
                {
                    "inchikey": ik,
                    "previous_rejection": failed["reason"],
                    "original_output_sha256": failed["output_sha256"],
                    "restart_geometry_sha256": hashlib.sha256(xyz.encode()).hexdigest(),
                    "retry_input_sha256": hashlib.sha256(inp.encode()).hexdigest(),
                }
            )
        (package / "joblist.txt").write_text(
            "".join("jobs/" + r["inchikey"] + "\n" for r in records), encoding="utf-8", newline="\n"
        )
        script = """#!/bin/bash
#SBATCH --job-name=b742_retry
#SBATCH -p hpxg
#SBATCH -N 1
#SBATCH --ntasks=4
#SBATCH --cpus-per-task=1
#SBATCH --time=12:00:00
#SBATCH --output=slurm-%A_%a.out
set -eu
module load openmpi/5.0
source "$HOME/project/soft/orca/env.sh"
PKG_DIR="$SLURM_SUBMIT_DIR"
JOB_DIR=$(sed -n "$SLURM_ARRAY_TASK_ID p" "$PKG_DIR/joblist.txt")
cd "$PKG_DIR/$JOB_DIR"
if [ -f job.out ] && grep -q 'ORCA TERMINATED NORMALLY' job.out && grep -q 'THE OPTIMIZATION HAS CONVERGED' job.out && grep -q 'Isotropic polarizability' job.out; then exit 0; fi
"$ORCA_DIR/orca" job.inp > job.out 2>&1
"""
        (package / "run_retry.sbatch").write_text(script, encoding="utf-8", newline="\n")
        record = {
            "schema": "b750.opt_retry/v1",
            "generated_at_utc": datetime.now(UTC).isoformat(),
            "n_jobs": len(records),
            "method": "unchanged ORCA r2SCAN-3c opt",
            "changes": "previous final XYZ; geometry MaxIter=300; all electronic, response, charge and multiplicity settings unchanged",
            "remote_dir": REMOTE,
            "jobs": records,
            "original_outputs": "preserved",
        }
        (package / "manifest.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
        if args.submit:
            _, out, err = client.exec_command("mkdir -p " + REMOTE + "/jobs", timeout=20)
            if out.channel.recv_exit_status() != 0:
                raise RuntimeError(err.read().decode())
            for rec in records:
                ik = rec["inchikey"]
                try:
                    sftp.mkdir(REMOTE + "/jobs/" + ik)
                except OSError:
                    pass
                for name in ("geom.xyz", "job.inp"):
                    sftp.put(str(package / "jobs" / ik / name), REMOTE + "/jobs/" + ik + "/" + name)
            for name in ("joblist.txt", "run_retry.sbatch"):
                sftp.put(str(package / name), REMOTE + "/" + name)
            command = (
                "cd "
                + REMOTE
                + " && sbatch --parsable --dependency=afterany:4592091:4592244 --array=1-"
                + str(len(records))
                + "%4 run_retry.sbatch"
            )
            _, out, err = client.exec_command(command, timeout=20)
            value = out.read().decode().strip()
            error = err.read().decode()
            if out.channel.recv_exit_status() != 0 or not value.split(";")[0].isdigit():
                raise RuntimeError("sbatch failed: " + value + " " + error)
            record.update(
                status="SUBMITTED_DEPENDENCY_NOT_COLLECTED",
                job_id=value,
                dependency="afterany:4592091:4592244",
            )
            receipt.write_text(json.dumps(record, indent=2), encoding="utf-8")
        print(
            json.dumps(
                {
                    "n_jobs": len(records),
                    "status": record.get("status", "BUILT_NOT_SUBMITTED"),
                    "job_id": record.get("job_id"),
                }
            )
        )
    finally:
        sftp.close()
        client.close()


if __name__ == "__main__":
    main()
