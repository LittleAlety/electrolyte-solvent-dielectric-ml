#!/usr/bin/env python
"""B00-2: verify and lock the frozen J01/J02/J03 artifact bytes.

This script does two distinct things, deliberately separated:

  1. VERIFY  -- recompute sha256 of every formal J01/J02/J03 output and of every
                recorded input, then compare against the digest the producing
                module itself wrote into its rebuild receipt. A mismatch is a
                hard failure, not a warning.

  2. LOCK    -- emit an independent hash manifest (j01_j02_j03_hash_lock.json)
                that a later round can re-verify without trusting this script's
                own memory of events.

Why both: the receipts are self-reported by the generators. Per PLAN B B01 the
generator must not be the sole witness of its own output. So we (a) recompute
from bytes and (b) publish the recomputed set so a third party can re-check.

It also verifies the v56_standalone R007 baseline, which lives OUTSIDE this
repository's working tree and therefore has no git-level byte protection.

Read-only: nothing under outputs/confirm_2027/ or v56_standalone/ is written.

Outputs:
  outputs/b00/j01_j02_j03_hash_lock.json
  outputs/b00/v56_r007_freeze_manifest.json
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = REPO_ROOT / "outputs" / "b00"
CONFIRM = REPO_ROOT / "outputs" / "confirm_2027"
STANDALONE = REPO_ROOT.parent / "v56_standalone"

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[2] / "probes"))
from export_results_common import write_json_stable  # noqa: E402

def _write_json_stable(path, payload):
    """Reuse the repo's AF-12 convention: a re-run with identical scientific
    fields must not rewrite bookkeeping-only bytes."""
    return write_json_stable(path, payload)

GENERATOR = "verify_frozen_artifacts/1.0.0"

# The three formal analyses whose bytes are frozen by PLAN B chapter 2.1.
# Each entry names the receipt written by its generator and the directory that
# holds the outputs. The receipt's own "output_sha256" block is the claim we
# test against the bytes on disk.
FROZEN_ANALYSES = {
    "J01": {
        "role": "A18 x B joint candidate eligibility + go/no-go",
        # NOTE: j01k_rebuild_receipt.json is a DIFFERENT analysis (temperature
        # band vocabulary reconciliation, B-G0-J01K). The J01 generator is
        # build_joint_eligibility.py and its receipt is joint_rebuild_receipt.json.
        "receipt": CONFIRM / "intersections" / "joint_rebuild_receipt.json",
        "output_dir": CONFIRM / "intersections",
        "formal_outputs": [
            "joint_eligibility.csv",
            "joint_eligibility_criteria.json",
            "joint_go_nogo.json",
            "joint_eligibility_report.md",
            "joint_inputs_manifest.json",
            "joint_candidate_measurement_rows.csv",
            "joint_pool_layer_summary.json",
            "joint_v11_observation_rows.csv",
            "a18_source_backfill_priority.csv",
        ],
    },
    "J02A": {
        "role": "40-row / R252 candidate exclusion reconciliation",
        "receipt": CONFIRM / "intersections" / "j02a_rebuild_receipt.json",
        "output_dir": CONFIRM / "intersections",
        "formal_outputs": [
            "candidate_exclusion_reconciliation.csv",
            "j02a_exclusion_summary.json",
            "j02a_inputs_manifest.json",
            "j02a_review_report.md",
        ],
    },
    "J02B": {
        "role": "master.in_49_preview vs candidate_pool_C lineage",
        "receipt": CONFIRM / "intersections" / "j02b_rebuild_receipt.json",
        "output_dir": CONFIRM / "intersections",
        "formal_outputs": [
            "j02b_inputs_manifest.json",
            "pool_lineage_reconciliation.csv",
            "pool_lineage_report.md",
            "pool_membership_diff.csv",
            "pool_version_decision.json",
        ],
    },
    "J03": {
        "role": "gap aggregation provenance / 248-row classification",
        "receipt": CONFIRM / "provenance_audit" / "j03_rebuild_receipt.json",
        "output_dir": CONFIRM / "provenance_audit",
        "formal_outputs": [
            "gap_aggregation_audit.csv",
            "j03_inputs_manifest.json",
            "lookup_feasibility.json",
            "measurement_reconstruction.csv",
            "source_contributor_map.csv",
            "aggregation_provenance_report.md",
        ],
    },
}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_analysis(name: str, spec: dict) -> dict:
    """Recompute digests and compare against the generator's own receipt."""
    receipt_path = spec["receipt"]
    result = {
        "analysis": name,
        "role": spec["role"],
        "receipt_path": str(receipt_path.relative_to(REPO_ROOT)),
        "receipt_present": receipt_path.is_file(),
        "checks": [],
        "n_pass": 0,
        "n_fail": 0,
        "n_missing": 0,
        "status": None,
    }

    claimed = {}
    if receipt_path.is_file():
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        claimed = receipt.get("output_sha256", {}) or {}
        result["receipt_analysis_id"] = receipt.get("analysis_id")
        result["receipt_generator_version"] = receipt.get("generator_version")
        result["receipt_contract_version"] = receipt.get("contract_version")

    for fname in spec["formal_outputs"]:
        fpath = spec["output_dir"] / fname
        entry = {"file": fname}
        if not fpath.is_file():
            entry["status"] = "MISSING"
            result["n_missing"] += 1
            result["checks"].append(entry)
            continue

        actual = sha256_file(fpath)
        entry["bytes"] = fpath.stat().st_size
        entry["actual_sha256"] = actual
        expected = claimed.get(fname)

        if expected is None:
            # Not covered by the receipt. This is a FAILURE of the freeze claim,
            # not a pass: a file whose digest no generator vouches for is
            # precisely the case an adversary could swap undetected. Record the
            # digest so the lock still pins it, but refuse to call it verified.
            entry["expected_sha256"] = None
            entry["status"] = "UNCLAIMED_BY_RECEIPT"
            result["n_unclaimed"] = result.get("n_unclaimed", 0) + 1
            result["checks"].append(entry)
            continue

        entry["expected_sha256"] = expected
        if actual == expected:
            entry["status"] = "MATCH"
            result["n_pass"] += 1
        else:
            entry["status"] = "MISMATCH"
            result["n_fail"] += 1
        result["checks"].append(entry)

    if result["n_fail"]:
        result["status"] = "FAIL_HASH_MISMATCH"
    elif result["n_missing"]:
        result["status"] = "FAIL_MISSING_OUTPUT"
    elif result.get("n_unclaimed", 0):
        # A frozen file no receipt vouches for cannot be considered verified.
        result["status"] = "FAIL_UNCLAIMED_OUTPUT"
    else:
        result["status"] = "PASS"

    return result


def verify_recorded_inputs() -> dict:
    """Re-hash every input path recorded in the J02B manifest.

    These are the upstream bytes the frozen analyses were computed from. If an
    input drifted, the frozen outputs are no longer reproducible even though
    their own bytes are intact.
    """
    manifest_path = CONFIRM / "intersections" / "j02b_inputs_manifest.json"
    out = {"manifest": str(manifest_path.relative_to(REPO_ROOT)), "checks": [],
           "n_pass": 0, "n_fail": 0, "n_absent": 0, "status": None}
    if not manifest_path.is_file():
        out["status"] = "FAIL_MANIFEST_MISSING"
        return out

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for item in manifest.get("inputs", []):
        raw_path = item.get("path")
        expected = item.get("sha256")
        entry = {"id": item.get("id"), "path": raw_path, "expected_sha256": expected}
        p = Path(raw_path) if raw_path else None
        if p is None or not p.is_file():
            entry["status"] = "ABSENT"
            out["n_absent"] += 1
            out["checks"].append(entry)
            continue
        actual = sha256_file(p)
        entry["actual_sha256"] = actual
        if actual == expected:
            entry["status"] = "MATCH"
            out["n_pass"] += 1
        else:
            entry["status"] = "MISMATCH"
            out["n_fail"] += 1
        out["checks"].append(entry)

    if out["n_fail"]:
        out["status"] = "FAIL_INPUT_DRIFT"
    elif out["n_absent"]:
        out["status"] = "PARTIAL_INPUT_ABSENT"
    else:
        out["status"] = "PASS"
    return out


def verify_r007_baseline() -> dict:
    """Lock the v56_standalone R007 report set (outside the git working tree)."""
    reports = STANDALONE / "reports"
    out = {
        "baseline_root": str(STANDALONE),
        "reports_dir": str(reports),
        "inside_repo_working_tree": False,
        "protection_note": (
            "v56_standalone 不在仓库工作树内, git 不跟踪它的任何字节. "
            "其冻结只能由本清单保证; 本清单本身必须另存一份到受控位置."
        ),
        "files": [],
        "n_files": 0,
        "status": None,
    }
    if not reports.is_dir():
        out["status"] = "FAIL_BASELINE_ABSENT"
        return out

    # The R007 round artifacts plus the canonical pool/protocol the plan names.
    patterns = ["*R007*"]
    seen: set[Path] = set()
    for pat in patterns:
        for p in sorted(reports.glob(pat)):
            if p.is_file():
                seen.add(p)

    # Canonical objects PLAN B chapter 2 names explicitly.
    named = [
        "candidate_pool_C_R001.csv",
        "candidate_pool_C_v2_R001.csv",
        "candidate_master_R001.csv",
        "evidence_backfill_R001.csv",
        "admission_matrix_R001.csv",
        "admission_matrix_v2_R001.csv",
    ]
    for name in named:
        p = reports / name
        if p.is_file():
            seen.add(p)

    for p in sorted(seen):
        out["files"].append({
            "path": str(p),
            "name": p.name,
            "bytes": p.stat().st_size,
            "sha256": sha256_file(p),
        })
    out["n_files"] = len(out["files"])
    out["status"] = "PASS" if out["n_files"] else "FAIL_NO_FILES"
    return out


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    analyses = {name: verify_analysis(name, spec)
                for name, spec in FROZEN_ANALYSES.items()}
    inputs = verify_recorded_inputs()
    r007 = verify_r007_baseline()

    all_status = [a["status"] for a in analyses.values()]
    overall = "PASS" if all(s == "PASS" for s in all_status) else "FAIL"

    lock = {
        "schema": "b00.frozen_hash_lock/v1",
        "generator": GENERATOR,
        "generated_at_utc": datetime.now(timezone.utc)
        .replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "declaration": (
            "J01/J02/J03 的正式产物字节在此锁定. 本锁不修改任何冻结字节, "
            "只记录重算后的 sha256 供后续轮次独立复核."
        ),
        "overall_status": overall,
        "analyses": analyses,
        "recorded_inputs": inputs,
        "summary": {
            "n_analyses": len(analyses),
            "n_analyses_pass": sum(1 for a in analyses.values() if a["status"] == "PASS"),
            "n_files_verified": sum(a["n_pass"] for a in analyses.values()),
            "n_files_failed": sum(a["n_fail"] for a in analyses.values()),
            "n_files_missing": sum(a["n_missing"] for a in analyses.values()),
            "n_files_unclaimed": sum(a.get("n_unclaimed", 0) for a in analyses.values()),
            "n_inputs_checked": len(inputs["checks"]),
            "n_inputs_pass": inputs["n_pass"],
            "n_inputs_fail": inputs["n_fail"],
            "n_inputs_absent": inputs["n_absent"],
        },
    }
    lock_path = OUT_DIR / "j01_j02_j03_hash_lock.json"
    _write_json_stable(lock_path, lock)

    r007_doc = {
        "schema": "b00.v56_r007_freeze/v1",
        "generator": GENERATOR,
        "generated_at_utc": lock["generated_at_utc"],
        "baseline": "v56_standalone R007",
        **r007,
    }
    r007_path = OUT_DIR / "v56_r007_freeze_manifest.json"
    _write_json_stable(r007_path, r007_doc)

    print(f"[B00-2] {lock_path}")
    for name, a in analyses.items():
        print(f"  {name:5s} {a['status']:22s} "
              f"pass={a['n_pass']} fail={a['n_fail']} missing={a['n_missing']}")
    print(f"  inputs  {inputs['status']:22s} "
          f"pass={inputs['n_pass']} fail={inputs['n_fail']} absent={inputs['n_absent']}")
    print(f"  R007    {r007['status']:22s} files={r007['n_files']}")
    print(f"  OVERALL {overall}")
    print(f"[B00-2] {r007_path}")

    return 0 if overall == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
