"""Validate the complete 67-job manifest against recovered ORCA opt outputs."""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import math
import re
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "outputs/b740_expansion/dft_expansion"


def load_parser():
    spec = importlib.util.spec_from_file_location(
        "b701_parser", ROOT / "scripts/b700/parse_b701_orca.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.parse_one


def parse_validated(text, parsed):
    directives = re.findall(
        r"^\s*(?:\|\s*\d+\s*>\s*)?!\s*(.*)$", text, re.MULTILINE | re.IGNORECASE
    )
    flags = {
        "charge_multiplicity_verified": bool(
            re.search(r"\*\s+xyzfile\s+0\s+1\s+", text, re.IGNORECASE)
        ),
        "terminated_normally": "ORCA TERMINATED NORMALLY" in text,
        "opt_converged": bool(re.search("THE OPTIMIZATION HAS CONVERGED", text, re.IGNORECASE)),
        "scf_converged": bool(re.search("SCF CONVERGED AFTER", text, re.IGNORECASE)),
        "method_verified": any(
            re.search(r"\br2SCAN-3c\b", x, re.IGNORECASE)
            and re.search(r"\bOpt\b", x, re.IGNORECASE)
            for x in directives
        ),
    }
    reasons = [key.upper() + "_FALSE" for key, value in flags.items() if not value]
    values = {}
    for key in ("dipole_D", "polarizability_au", "total_energy_hartree"):
        try:
            value = float(parsed.get(key))
        except (TypeError, ValueError):
            value = None
        if value is None or not math.isfinite(value):
            reasons.append("MISSING_OR_NONFINITE_" + key)
            value = None
        values[key] = value
    if values["dipole_D"] is not None and values["dipole_D"] < 0:
        reasons.append("NEGATIVE_DIPOLE")
    if values["polarizability_au"] is not None and values["polarizability_au"] <= 0:
        reasons.append("NONPOSITIVE_POLARIZABILITY")
    return {
        **flags,
        **values,
        "status": "REJECTED" if reasons else "ACCEPTED",
        "reason": ";".join(reasons),
    }


def run(manifest, jobs_dir, output_dir, fallback_jobs_dir=None):
    raw = manifest.read_bytes()
    document = json.loads(raw)
    jobs = document["jobs"]
    keys = [j["inchikey"] for j in jobs]
    if len(keys) != 67 or len(set(keys)) != 67:
        raise ValueError("Expected frozen 67 distinct job identities")
    parser = load_parser()
    rows = []
    for job in jobs:
        ik = job["inchikey"]
        source = jobs_dir / ik / "job.out"
        if not source.is_file() and fallback_jobs_dir is not None:
            source = fallback_jobs_dir / ik / "job.out"
        row = {
            "inchikey": ik,
            "name": job.get("name", ""),
            "smiles": job.get("smiles", ""),
            "status": "NOT_RECOVERED",
            "reason": "OUTPUT_NOT_ON_DISK",
            "original_input_sha256": job.get("inp_sha256", ""),
            "source_output": str(source),
            "output_sha256": "",
        }
        if source.is_file():
            payload = source.read_bytes()
            text = payload.decode("utf-8", errors="replace")
            row["output_sha256"] = hashlib.sha256(payload).hexdigest()
            try:
                row.update(parse_validated(text, parser(text)))
            except (ValueError, TypeError, KeyError, OverflowError) as exc:
                row.update(status="REJECTED", reason=f"PARSER_ERROR:{type(exc).__name__}:{exc}")
        rows.append(row)
    output_dir.mkdir(parents=True, exist_ok=True)
    fields = [
        "inchikey",
        "name",
        "smiles",
        "status",
        "reason",
        "dipole_D",
        "polarizability_au",
        "total_energy_hartree",
        "terminated_normally",
        "opt_converged",
        "scf_converged",
        "method_verified",
        "charge_multiplicity_verified",
        "original_input_sha256",
        "output_sha256",
        "source_output",
    ]
    accepted = [r for r in rows if r["status"] == "ACCEPTED"]
    for name, records in [
        ("validation_ledger.csv", rows),
        ("new_molecule_descriptors.csv", accepted),
    ]:
        with (output_dir / name).open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(records)
    (output_dir / "failure_certificates.json").write_text(
        json.dumps([r for r in rows if r["status"] != "ACCEPTED"], indent=2), encoding="utf-8"
    )
    counts = Counter(r["status"] for r in rows)
    summary = {
        "schema": "b750.orca_validation/v1",
        "generator": "validate_new_orca_results/1.0.0",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "expected": 67,
        "recovered": 67 - counts["NOT_RECOVERED"],
        "accepted": len(accepted),
        "rejected": counts["REJECTED"],
        "not_recovered": counts["NOT_RECOVERED"],
        "complete": len(accepted) == 67,
        "manifest_sha256": hashlib.sha256(raw).hexdigest(),
        "units": {
            "dipole_D": "Debye",
            "polarizability_au": "bohr^3",
            "total_energy_hartree": "hartree",
        },
        "method": "ORCA r2SCAN-3c opt",
        "gap_policy": "Not parsed; no xTB gap fallback permitted",
        "full_transfer_status": "READY" if len(accepted) == 67 else "BLOCKED_INCOMPLETE_RESULTS",
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=BASE / "package_opt/manifest.json")
    parser.add_argument("--jobs-dir", type=Path, default=BASE / "results_opt/jobs")
    parser.add_argument("--output-dir", type=Path, default=BASE / "results_opt/validation")
    parser.add_argument("--fallback-jobs-dir", type=Path)
    args = parser.parse_args()
    print(json.dumps(run(args.manifest, args.jobs_dir, args.output_dir, args.fallback_jobs_dir)))


if __name__ == "__main__":
    main()
