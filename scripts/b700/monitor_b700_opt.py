#!/usr/bin/env python
"""Monitor opt progress and auto-fetch new results.

Checks cluster status, fetches completed ORCA outputs, parses them, and
reports coverage.

Usage:
  python scripts/b700/monitor_b700_opt.py
  python scripts/b700/monitor_b700_opt.py --fetch
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
KEY = Path.home() / ".ssh" / "id_ed25519_whu"
REMOTE = "pengqihang@202.114.96.180"
REMOTE_BASE = "/project/pengqihang/b700/B701/production_239/package_opt/jobs"
LOCAL_BASE = REPO_ROOT / "outputs" / "b700" / "B701_DFT" / "production_239"


def run(cmd: str) -> tuple[int, str, str]:
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=120)
    return r.returncode, r.stdout, r.stderr


def check_status() -> dict:
    rc, out, err = run(
        f'ssh -i "{KEY}" -o BatchMode=yes {REMOTE} '
        f'"cd {REMOTE_BASE} && '
        f'ok=$(grep -l \\\'ORCA TERMINATED NORMALLY\\\' */job.out 2>/dev/null | wc -l) && '
        f'squeue -u $(whoami) 2>&1 | head -10"'
    )
    lines = out.strip().splitlines()
    running = [l for l in lines if "RUNNING" in l]
    pending = [l for l in lines if "PD" in l]
    return {
        "ok": int(out.split("=")[-1]) if "=" in out else 0,
        "running": len(running),
        "pending": len(pending),
        "raw": out,
    }


def fetch_results() -> int:
    rc, out, err = run(
        f'ssh -i "{KEY}" -o BatchMode=yes {REMOTE} '
        f'"cd {REMOTE_BASE} && '
        f'for d in */; do ik=${{d%/}}; '
        f'if [ -f $d/job.out ] && grep -q \\\'ORCA TERMINATED NORMALLY\\\' $d/job.out 2>/dev/null; then '
        f'mkdir -p /tmp/opt_auto/$ik && cp $d/job.out /tmp/opt_auto/$ik/ 2>/dev/null; fi; done && '
        f'ls /tmp/opt_auto | wc -l"'
    )
    count = int(out.strip())
    if count == 0:
        return 0

    local = str(LOCAL_BASE / "results_opt")
    # Use Python for reliable copy
    py = (
        f'import os,subprocess; '
        f'subprocess.run(["scp","-q","-i","{KEY}","-o","BatchMode=yes","-r",'
        f'"{REMOTE}:/tmp/opt_auto/*","{local}/"])'
    )
    run(f'python -c "{py}"')
    local_dirs = sum(
        1 for d in os.listdir(local)
        if os.path.isdir(os.path.join(local, d))
    )
    return local_dirs


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fetch", action="store_true")
    args = parser.parse_args()

    status = check_status()
    print(f"[OPT] terminated_normally on cluster: {status['ok']}")
    print(f"[OPT] running: {status['running']}, pending: {status['pending']}")

    if args.fetch:
        local = fetch_results()
        print(f"[OPT] fetched to local: {local} directories")
        sys.exit(0)

    return 0


if __name__ == "__main__":
    sys.exit(main())
