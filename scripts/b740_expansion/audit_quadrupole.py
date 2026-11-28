"""Audit existing ORCA quadrupole evidence without admitting unknown conventions."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path


def inspect_output(path: Path, repo: Path) -> dict:
    raw = path.read_bytes()
    text = raw.decode("utf-8", errors="replace")
    lines = text.splitlines()
    hits = []
    for i, line in enumerate(lines):
        if re.search(r"\bquadrupole\b", line, re.IGNORECASE):
            hits.append({"line": i + 1, "excerpt": "\n".join(lines[max(0, i - 2) : i + 22])})
    try:
        label = path.relative_to(repo).as_posix()
    except ValueError:
        label = path.as_posix()
    return {
        "path": label,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "normal_termination": "ORCA TERMINATED NORMALLY" in text,
        "n_quadrupole_mentions": len(hits),
        "mentions": hits,
        "quadrupole_requested": bool(re.search(r"Quadrupole moment\s+\.\.\.\s+YES", text)),
        "admission": "AUDIT_ONLY_UNKNOWN_UNITS_ORIGIN_AND_CONVENTION" if hits else "NOT_AVAILABLE",
    }


def main():
    repo = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--jobs-dir", type=Path, default=repo / "outputs/b700/B701_DFT/production_239/results_opt"
    )
    parser.add_argument(
        "--output-dir", type=Path, default=repo / "outputs/b750_completion/quadrupole"
    )
    args = parser.parse_args()
    files = sorted(args.jobs_dir.rglob("job.out"))
    rows = [inspect_output(p, repo) for p in files]
    found = sum(r["n_quadrupole_mentions"] > 0 for r in rows)
    doc = {
        "schema": "b750.quadrupole_audit/v1",
        "generator": "audit_quadrupole/1.0.0",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "n_expected": 239,
        "n_outputs_scanned": len(rows),
        "n_outputs_with_mentions": found,
        "n_validated_tensors": 0,
        "n_outputs_requesting_quadrupole": sum(r["quadrupole_requested"] for r in rows),
        "status": "AUDIT_ONLY" if any(r["quadrupole_requested"] for r in rows) else "NOT_COMPUTED",
        "reason": "Configuration mentions are not computed tensors. If quadrupole was not requested, new calculations are required. Otherwise units, convention and origin need validation.",
        "coordinate_guard": "Eigenvalues can be rotation invariant but quadrupoles remain origin dependent for molecules with nonzero dipole, including neutral molecules. No cross-molecule descriptor is created.",
        "missing_output_count": max(0, 239 - len(rows)),
        "files": rows,
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "quadrupole_audit.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps({k: v for k, v in doc.items() if k != "files"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
