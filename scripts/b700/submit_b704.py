#!/usr/bin/env python
"""Submit B704 conformer jobs in small batches respecting QOS limits.

Usage:
  python scripts/b700/submit_b704.py
  python scripts/b700/submit_b704.py --start 16 --end 227
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
KEY = Path.home() / ".ssh" / "id_ed25519_whu"
REMOTE = "pengqihang@202.114.96.180"
REMOTE_DIR = "/project/pengqihang/b700/B704"
LOCAL_DIR = REPO_ROOT / "outputs" / "b700" / "B704_conformers"

BATCH_SIZE = 5
WAIT_SECONDS = 30


def run(cmd: str) -> tuple[int, str, str]:
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=120)
    return r.returncode, r.stdout, r.stderr


def submit_batch(start: int, end: int) -> str | None:
    cmd = (
        f'ssh -i "{KEY}" -o BatchMode=yes {REMOTE} '
        f'"cd {REMOTE_DIR} && '
        f'sbatch --array={start}-{end} --partition=hpxg run_b704_conformers.sbatch joblist.txt"'
    )
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=20)
    except subprocess.TimeoutExpired:
        print(f"  TIMEOUT {start}-{end}")
        return None
    if r.returncode == 0:
        job_id = r.stdout.strip().split()[-1] if r.stdout.strip() else ""
        print(f"  Submitted {start}-{end}: job {job_id}", flush=True)
        return job_id
    else:
        print(f"  FAILED {start}-{end}: {r.stderr.strip()[:100]}", flush=True)
        return None


def wait_for_completion(job_ids: list[str], wait: int) -> None:
    if not job_ids:
        return
    ids = ",".join(job_ids)
    cmd = f'ssh -i "{KEY}" -o BatchMode=yes {REMOTE} "sacct -j {ids} -X --format=JobID,State 2>&1"'
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=15)
    except subprocess.TimeoutExpired:
        return
    if r.returncode != 0:
        return
    states = r.stdout.strip().splitlines()
    pending = any("PENDING" in s or "RUNNING" in s for s in states[1:])
    if pending:
        print(f"  Waiting {wait}s for jobs to complete...", flush=True)
        time.sleep(wait)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=int, default=16)
    parser.add_argument("--end", type=int, default=227)
    parser.add_argument("--batch", type=int, default=BATCH_SIZE)
    parser.add_argument("--wait", type=int, default=WAIT_SECONDS)
    args = parser.parse_args()

    start = args.start
    end = args.end
    batch = args.batch
    wait = args.wait

    print(f"[B704] Submitting conformers {start}-{end} in batches of {batch}")

    job_ids = []
    batch_num = 0
    for i in range(start, end + 1, batch):
        batch_num += 1
        batch_end = min(i + batch - 1, end)
        job_id = submit_batch(i, batch_end)
        if job_id:
            job_ids.append(job_id)

        if batch_num % 3 == 0 and job_ids:
            wait_for_completion(job_ids, wait)
            job_ids = []

    # Final wait
    if job_ids:
        wait_for_completion(job_ids, wait)

    print("[B704] Submission complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
