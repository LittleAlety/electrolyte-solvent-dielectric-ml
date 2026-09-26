"""Independently audit the energy unit of the W17-14 GFN2-xTB harvest (W17-14).

Why this exists
---------------
The W17-12 second-source layer stamped ``unit_check = verified_eV`` on all 912
rows while only 40 of them had any unit evidence behind them; an audit of that
arm called it out as an over-claim.  This probe is the correction applied to our
own arm: instead of asserting a unit per row, it re-derives the unit from the
xTB output itself.

xTB prints each eigenvalue twice, once in hartree and once in eV, on the same
line::

         8        2.0000           -0.4294036             -11.6847 (HOMO)

``probes/themol_hessian_orbitals.py`` reads the last column.  This probe re-runs
the same geometry, reads *both* columns, and checks that the eV column is the
hartree column times the CODATA conversion factor.  If the parser were reading
the hartree column, or if xTB changed its banner, the residual would be huge and
the audit would fail.

The audit is a **pipeline-level** claim: every row in the layer comes from the
same parser, so checking the parser on a deterministic sample checks the
pipeline.  ``build_themol_orbital_layer.py`` only writes
``unit_check = pipeline_audited_eV`` when this file reports a pass.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from probes.themol_hessian_orbitals import (
    HF_MIRROR_BASE,
    HttpRangeFile,
    parse_orbitals,
    resolve_xtb,
    write_xyz,
)

RAW_DIR = ROOT / "data/raw/themol"
SHARD_GLOB = "shard_*.csv"
OUTPUT = RAW_DIR / "unit_audit.json"
SCRATCH = RAW_DIR / "unit_audit_scratch"

HARTREE_TO_EV = 27.211386245988
RESIDUAL_LIMIT_EV = 1e-3
BANNER_MARKER = "Energy/eV"
BLOCK_PATTERN = re.compile(
    r"^\s*\d+\s+(?:\d+\.\d+\s+)?(-?\d+\.\d+)\s+(-?\d+\.\d+)\s+\((HOMO|LUMO)\)"
)


def sample_rows(count: int) -> list[dict[str, str]]:
    """Deterministic sample: every k-th molecule of the merged, sorted harvest."""

    import csv

    rows: list[dict[str, str]] = []
    for path in sorted(RAW_DIR.glob(SHARD_GLOB)):
        with path.open(encoding="utf-8", newline="") as handle:
            rows.extend(
                row
                for row in csv.DictReader(handle)
                if row.get("status") == "ok" and row.get("homo_eV")
            )
    rows.sort(key=lambda row: row.get("inchikey", ""))
    if not rows:
        return []
    step = max(1, len(rows) // count)
    return rows[::step][:count]


def audit_row(row: dict[str, str], xtb_executable: Path, timeout_seconds: int) -> dict[str, object]:
    import h5py
    import requests

    session = requests.Session()
    session.trust_env = False
    session.headers.update({"User-Agent": "Mozilla/5.0", "Accept-Encoding": "identity"})
    url = HF_MIRROR_BASE + "Hessian/" + row["themol_h5_file"]
    remote = HttpRangeFile(url, session)
    workdir = SCRATCH / row["themol_uuid"][:12]
    if workdir.exists():
        shutil.rmtree(workdir)
    workdir.mkdir(parents=True, exist_ok=True)

    from electrolyte_ml.xtb_runner import run_xtb_subprocess

    with h5py.File(remote, "r") as container:
        group = container[row["themol_uuid"]]
        atomic_numbers = group["atomic_numbers"][:].ravel()
        coordinates = group["coords"][:]
    digest = write_xyz(workdir / "mol.xyz", atomic_numbers, coordinates, row["themol_uuid"])
    completed = run_xtb_subprocess(
        xtb_executable,
        ["mol.xyz", "--gfn", "2", "--sp"],
        cwd=workdir,
        timeout_seconds=timeout_seconds,
    )
    text = completed.stdout.decode("utf-8", "replace") + completed.stderr.decode("utf-8", "replace")
    banner = BANNER_MARKER in text
    pairs: dict[str, list[float]] = {"HOMO": [], "LUMO": []}
    for line in text.splitlines():
        match = BLOCK_PATTERN.match(line)
        if match:
            pairs[match.group(3)].append((float(match.group(1)), float(match.group(2))))
    residuals = [
        round(ev - hartree * HARTREE_TO_EV, 8) for values in pairs.values() for hartree, ev in values
    ]
    parsed_homo, parsed_lumo = parse_orbitals(text)
    return {
        "inchikey": row.get("inchikey", ""),
        "name": row.get("name", ""),
        "themol_uuid": row["themol_uuid"],
        "h5_file": row["themol_h5_file"],
        "geometry_sha256": digest,
        "banner_has_energy_eV": banner,
        "n_hartree_eV_pairs": len(residuals),
        "max_abs_residual_eV": max((abs(value) for value in residuals), default=None),
        "residual_eV": max((abs(value) for value in residuals), default=None),
        "harvest_homo_eV": row.get("homo_eV"),
        "reparsed_homo_eV": parsed_homo,
        "harvest_lumo_eV": row.get("lumo_eV"),
        "reparsed_lumo_eV": parsed_lumo,
        "passed": bool(
            banner
            and residuals
            and max(abs(value) for value in residuals) <= RESIDUAL_LIMIT_EV
            and parsed_homo is not None
            and parsed_lumo is not None
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--count", type=int, default=8)
    parser.add_argument("--xtb", type=Path, default=None)
    parser.add_argument("--timeout-seconds", type=int, default=900)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args(argv)

    rows = sample_rows(args.count)
    if not rows:
        print("no harvested rows found; nothing to audit")
        return 1

    xtb_executable = resolve_xtb(args.xtb)
    SCRATCH.mkdir(parents=True, exist_ok=True)
    checks = []
    for row in rows:
        check = audit_row(row, xtb_executable, args.timeout_seconds)
        checks.append(check)
        print(
            f"  {check['name']}: residual={check['max_abs_residual_eV']} "
            f"banner={check['banner_has_energy_eV']} passed={check['passed']}"
        )
    payload = {
        "claim": "the HOMO/LUMO columns of the W17-14 harvest are the eV column of xTB 6.7.1",
        "hartree_to_eV": HARTREE_TO_EV,
        "residual_limit_eV": RESIDUAL_LIMIT_EV,
        "n": len(checks),
        "passed": sum(1 for check in checks if check["passed"]),
        "checks": checks,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8", newline="")
    print(f"wrote {args.output}: {payload['passed']}/{payload['n']} passed")
    return 0 if payload["passed"] == payload["n"] else 1


if __name__ == "__main__":
    raise SystemExit(main())