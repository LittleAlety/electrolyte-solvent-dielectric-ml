"""Re-derive a seeded sample of the W17-17 orbital layer from scratch.

Why this exists
---------------
The W17-17 layer stamps ``unit_check`` on every row, but the only independent
evidence quoted next to it was ``data/raw/themol/unit_audit.json`` -- 8
molecules that belong to the *W17-14* harvest.  An adversarial audit of this arm
(``reports/themol_expanded_layer_audit.md``, finding F6) called that an
evidence-to-claim mismatch: the pre-registration asked for the delivered numbers
to be reproduced by an independent re-parse, and that had not been done for this
layer.

This probe does it for this layer, on a seeded sample:

1. pick N rows of ``data/processed/themol_orbital_layer_expanded.csv`` with a
   fixed seed (the sample is therefore reproducible and reported with its share
   of the layer, so nobody can read it as full coverage);
2. re-read the geometry from THEMol over HTTP Range and check the XYZ digest
   against the ``geometry_sha256`` the layer recorded -- chain of custody;
3. re-run the same GFN2-xTB single point;
4. read the eigenvalues with **this file own parser** (occupation-based, not the
   ``(HOMO)``/``(LUMO)`` labels and not ``parse_orbitals``), and compare against
   the delivered ``homo_gfn2_eV`` / ``lumo_gfn2_eV``.

A pass means: the delivered number is reproducible from the raw dataset by a
second code path.  It does **not** mean the whole layer was re-derived, and the
JSON says so in ``coverage_note``.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import re
import shutil
import sys
import time
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from probes.themol_hessian_orbitals import (
    HF_MIRROR_BASE,
    HttpRangeFile,
    resolve_xtb,
    write_xyz,
)

LAYER = REPOSITORY_ROOT / "data/processed/themol_orbital_layer_expanded.csv"
OUTPUT = REPOSITORY_ROOT / "data/raw/themol/expand_unit_recheck.json"
SCRATCH = REPOSITORY_ROOT / "data/raw/themol/expand_recheck_scratch"

SEED = 20260927
DEFAULT_SAMPLE = 24
TOLERANCE_EV = 1e-3
PACING_SECONDS = 0.3
SECTION_MARKER = "orbital energies and occupations"
COLUMN_HEADER = "Energy/eV"
HARTREE_TO_EV = 27.211386245988
# index, [occupation], hartree, eV, optional (HOMO|LUMO) label.  xTB leaves the
# occupation cell empty for virtual orbitals, so it has to be optional here:
#     26        2.0000    -0.4006580    -10.9025 (HOMO)
#     27                  -0.2676358     -7.2827 (LUMO)
ORBITAL_ROW = re.compile(
    r"^\s*(\d+)\s+(?:(\d+\.\d+)\s+)?(-?\d+\.\d+)\s+(-?\d+\.\d+)\s*"
    r"(?:\((HOMO|LUMO)\))?\s*$"
)


def layer_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sample_rows(path: Path, count: int, seed: int) -> list[dict[str, str]]:
    """Seeded, reproducible sample of the layer, ordered by InChIKey."""

    with path.open(encoding="utf-8", newline="") as handle:
        rows = [row for row in csv.DictReader(handle) if row.get("homo_gfn2_eV")]
    rows.sort(key=lambda row: row["inchikey"])
    if len(rows) <= count:
        return rows
    return random.Random(seed).sample(rows, count)


def parse_orbital_block(text: str) -> dict[str, object]:
    """Read the ORBITAL ENERGIES table with an occupation-based rule.

    HOMO is the highest occupied eigenvalue, LUMO the lowest virtual one.  The
    ``(HOMO)``/``(LUMO)`` labels are only used as a cross-check, so this parser
    does not share a code path with the harvest parser that produced the layer.
    """

    lines = text.splitlines()
    start = next(
        (i for i, line in enumerate(lines) if SECTION_MARKER in line.lower()),
        None,
    )
    if start is None:
        return {"mode": "no_section", "homo_eV": None, "lumo_eV": None, "n_levels": 0}
    occupied: list[float] = []
    virtual: list[float] = []
    hartree_residuals: list[float] = []
    labelled: dict[str, float] = {}
    header_seen = False
    for line in lines[start + 1 :]:
        if COLUMN_HEADER in line:
            header_seen = True
            continue
        stripped = line.strip()
        # Blank lines, the dashed underline and xTB's ``...`` elision rows all
        # sit inside the table.
        if not stripped or stripped.startswith("-") or set(stripped) <= set(". "):
            continue
        match = ORBITAL_ROW.match(line)
        if not match:
            if header_seen and (occupied or virtual):
                break
            continue
        if not header_seen:
            continue
        occupation = float(match.group(2)) if match.group(2) else 0.0
        hartree = float(match.group(3))
        energy = float(match.group(4))
        hartree_residuals.append(abs(energy - hartree * HARTREE_TO_EV))
        if match.group(5):
            labelled[match.group(5)] = energy
        (occupied if occupation > 0.5 else virtual).append(energy)
    homo = max(occupied) if occupied else None
    lumo = min(virtual) if virtual else None
    agree = {
        key: (value is not None and abs(value - labelled[key]) < TOLERANCE_EV)
        for key, value in (("HOMO", homo), ("LUMO", lumo))
        if key in labelled
    }
    return {
        "mode": "occupation",
        "homo_eV": homo,
        "lumo_eV": lumo,
        "n_levels": len(occupied) + len(virtual),
        "label_agreement": agree,
        "max_abs_hartree_residual_eV": max(hartree_residuals, default=None),
    }


def recheck_row(row: dict[str, str], xtb_executable: Path, timeout_seconds: int) -> dict[str, object]:
    import h5py
    import requests

    from electrolyte_ml.xtb_runner import run_xtb_subprocess

    session = requests.Session()
    session.trust_env = False
    session.headers.update({"User-Agent": "Mozilla/5.0", "Accept-Encoding": "identity"})
    url = HF_MIRROR_BASE + "Hessian/" + row["themol_h5_file"]
    workdir = SCRATCH / row["themol_uuid"][:12]
    if workdir.exists():
        shutil.rmtree(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    result: dict[str, object] = {"inchikey": row["inchikey"], "name": row.get("name", "")}
    try:
        with h5py.File(HttpRangeFile(url, session), "r") as container:
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
        text = completed.stdout.decode("utf-8", "replace") + completed.stderr.decode(
            "utf-8", "replace"
        )
        parsed = parse_orbital_block(text)
        layer_homo = float(row["homo_gfn2_eV"])
        layer_lumo = float(row["lumo_gfn2_eV"])
        homo = parsed["homo_eV"]
        lumo = parsed["lumo_eV"]
        delta_homo = None if homo is None else abs(float(homo) - layer_homo)
        delta_lumo = None if lumo is None else abs(float(lumo) - layer_lumo)
        result.update(
            {
                "themol_uuid": row["themol_uuid"],
                "h5_file": row["themol_h5_file"],
                "geometry_sha256_matches_layer": digest == row["geometry_sha256"],
                "parser_mode": parsed["mode"],
                "n_levels": parsed["n_levels"],
                "label_agreement": parsed["label_agreement"],
                "max_abs_hartree_residual_eV": parsed["max_abs_hartree_residual_eV"],
                "homo_layer_eV": layer_homo,
                "homo_recheck_eV": homo,
                "lumo_layer_eV": layer_lumo,
                "lumo_recheck_eV": lumo,
                "delta_homo_eV": delta_homo,
                "delta_lumo_eV": delta_lumo,
                "passed": bool(
                    digest == row["geometry_sha256"]
                    and delta_homo is not None
                    and delta_homo <= TOLERANCE_EV
                    and delta_lumo is not None
                    and delta_lumo <= TOLERANCE_EV
                ),
            }
        )
    except Exception as error:  # noqa: BLE001 - one flaky molecule must not abort the probe
        result.update({"passed": False, "error": type(error).__name__})
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--layer", type=Path, default=LAYER)
    parser.add_argument("--out", type=Path, default=OUTPUT)
    parser.add_argument("--sample", type=int, default=DEFAULT_SAMPLE)
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--tolerance-eV", type=float, default=TOLERANCE_EV)
    parser.add_argument("--timeout-seconds", type=int, default=180)
    parser.add_argument("--check", action="store_true", help="re-audit an existing JSON offline")
    args = parser.parse_args(argv)

    if args.check:
        payload = json.loads(args.out.read_text(encoding="utf-8"))
        failures = []
        if payload.get("layer_sha256") != layer_digest(args.layer):
            failures.append("the JSON was produced against a different layer digest")
        if not payload.get("all_passed"):
            failures.append("the sampled recheck did not pass")
        print(json.dumps({"failures": failures, "n_sampled": payload.get("n_sampled")}, sort_keys=True))
        if failures:
            for failure in failures:
                print("FAIL " + failure)
            return 1
        print("CHECK OK")
        return 0

    layer_rows = sample_rows(args.layer, args.sample, args.seed)
    if not layer_rows:
        print("no layer rows with an orbital value; nothing to recheck")
        return 2
    xtb_executable = resolve_xtb(None)
    results = []
    for index, row in enumerate(layer_rows, start=1):
        time.sleep(PACING_SECONDS)
        result = recheck_row(row, xtb_executable, args.timeout_seconds)
        results.append(result)
        print(
            f"[{index}/{len(layer_rows)}] {result['inchikey']} "
            f"homo={result.get('homo_recheck_eV')} lumo={result.get('lumo_recheck_eV')} "
            f"passed={result.get('passed')}"
        )

    deltas_homo = [r["delta_homo_eV"] for r in results if r.get("delta_homo_eV") is not None]
    deltas_lumo = [r["delta_lumo_eV"] for r in results if r.get("delta_lumo_eV") is not None]
    with args.layer.open(encoding="utf-8", newline="") as handle:
        total_rows = sum(1 for _ in csv.DictReader(handle))
    payload = {
        "arm": "W17-17",
        "probe": "themol_expand_unit_recheck",
        "question": "are this layer own delivered orbital numbers reproducible by a second code path?",
        "layer_path": str(args.layer.relative_to(REPOSITORY_ROOT)),
        "layer_sha256": layer_digest(args.layer),
        "layer_rows": total_rows,
        "seed": args.seed,
        "n_sampled": len(results),
        "sample_share": len(results) / total_rows if total_rows else None,
        "tolerance_eV": args.tolerance_eV,
        "independent_parser": "occupation-based ORBITAL ENERGIES reader (not parse_orbitals)",
        "coverage_note": (
            "a passing sample shows the delivered numbers are reproducible; it is not a "
            "re-derivation of every row, and the share above is the honest coverage"
        ),
        "max_abs_delta_homo_eV": max(deltas_homo) if deltas_homo else None,
        "max_abs_delta_lumo_eV": max(deltas_lumo) if deltas_lumo else None,
        "geometry_digest_matches": sum(
            1 for r in results if r.get("geometry_sha256_matches_layer")
        ),
        "all_passed": bool(results) and all(r.get("passed") for r in results),
        "results": results,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "all_passed": payload["all_passed"],
                "n_sampled": payload["n_sampled"],
                "sample_share": payload["sample_share"],
                "max_abs_delta_homo_eV": payload["max_abs_delta_homo_eV"],
                "max_abs_delta_lumo_eV": payload["max_abs_delta_lumo_eV"],
            },
            sort_keys=True,
        )
    )
    return 0 if payload["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
