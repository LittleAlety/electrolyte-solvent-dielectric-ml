#!/usr/bin/env python
"""B710-00: freeze the v7.0 E4/E6 evidence before any v7.1 work touches it.

This writes a SHA256 manifest over every artifact the v7.1 conclusions will lean
on. If a later script accidentally rewrites a frozen file, the v7.1 contract test
fails instead of silently producing a report that cites numbers no longer on disk.

Also records the exact evaluation protocol constants, because the E6 stability
claim ("regret is unstable, MAE is stable") is only meaningful together with the
protocol that produced it.

Output: outputs/b710_evidence/final/v70_freeze_manifest.json
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
B700 = REPO_ROOT / "outputs" / "b700"
OUT = REPO_ROOT / "outputs" / "b710_evidence" / "final"
GEN = "freeze_v70_evidence/1.0.0"

FROZEN = {
    "e4_family_diagnostics_json": B700 / "B706_E4_family_diagnostics.json",
    "e4_family_diagnostics_csv": B700 / "B706_E4_family_diagnostics.csv",
    "e4_lofo_predictions_csv": B700 / "B706_E4_lofo_predictions.csv",
    "e6_seed_stability_json": B700 / "B706_E6_seed_stability.json",
    "e6_report_sp_json": B700 / "B706_experiments_report_sp.json",
    "e6_report_opt_json": B700 / "B706_experiments_report_opt.json",
    "e3_conformer_json": B700 / "B706_E3_conformer.json",
    "descriptors_sp_csv": B700 / "orca_r2scan3c_descriptors.csv",
    "descriptors_opt_csv": B700 / "orca_r2scan3c_opt_model.csv",
    "b703_full_matrix_json": B700 / "B703_full_matrix.json",
    "final_summary_json": B700 / "B700_FINAL_SUMMARY.json",
    "final_report_md": B700 / "B700_FINAL_REPORT_v7.md",
    "sp_parsed_csv": B700 / "B701_DFT" / "production_239" / "parsed_sp.csv",
    "opt_parsed_csv": B700 / "B701_DFT" / "production_239" / "parsed_opt.csv",
    "conformer_parsed_csv": B700 / "B704_conformers" / "parsed_conformers.csv",
    "method_freeze_json": B700 / "B701_DFT" / "method_freeze_v2.json",
    "v60_freeze_json": B700 / "B700_V60_FREEZE.json",
}

# Files whose content the v7.1 contracts rely on remaining byte-identical.
PROTECTED_V60 = {
    "v60_dft_descriptors": REPO_ROOT / "outputs" / "b100" / "deliverables" / "dft_descriptors_b100.csv",
    "v60_xtb_descriptors": REPO_ROOT / "outputs" / "b100" / "deliverables" / "xtb_descriptors_b100.csv",
    "v60_model_matrix": REPO_ROOT / "outputs" / "b100" / "model_matrix_b100.csv",
    "v60_epsilon_labels": REPO_ROOT / "outputs" / "b100" / "deliverables" / "epsilon_labels_b100.csv",
}

PROTOCOL = {
    "evaluation": "nested leave-one-out; lambda chosen per held-out point by inner 5-fold CV",
    "lambda_grid": [0.01, 0.1, 1.0, 10.0, 100.0, 1000.0],
    "standardisation": "training fold only (means/sds from the fold, applied to the test point)",
    "model": "ridge with intercept",
    "topk": 10,
    "topk_sensitivity": [5, 15],
    "candidate_pool": "239 phase-verified molecules with a valid static epsilon label",
    "regret_definition": "mean(top-k true epsilon) - mean(true epsilon of the model's top-k)",
    "e6_seeds": [20261123, 20261124, 20261125, 20261126, 20261127],
    "seed_semantics": (
        "seeds perturb only the fold partition used for lambda selection. They are NOT "
        "independent experimental sources and NOT a population confidence interval."
    ),
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    files = {}
    missing = []
    for key, path in FROZEN.items():
        if path.exists():
            files[key] = {
                "path": str(path.relative_to(REPO_ROOT)).replace("\\", "/"),
                "sha256": sha256(path),
                "bytes": path.stat().st_size,
            }
        else:
            missing.append(key)

    protected = {}
    for key, path in PROTECTED_V60.items():
        if path.exists():
            protected[key] = {
                "path": str(path.relative_to(REPO_ROOT)).replace("\\", "/"),
                "sha256": sha256(path),
            }
        else:
            missing.append(key)

    doc = {
        "schema": "b710.v70_freeze/v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "generator": GEN,
        "purpose": (
            "Freeze v7.0 E4/E6 evidence before v7.1 adds new analysis. v7.1 must not "
            "overwrite these files; it writes to outputs/b710_evidence/ instead."
        ),
        "v70_head_reference": "09ccab8",
        "evaluation_protocol": PROTOCOL,
        "frozen_artifacts": files,
        "protected_v60_artifacts": protected,
        "missing": missing,
        "immutability_contract": [
            "v7.1 新增分析不得覆盖 outputs/b700/ 下任何被冻结文件",
            "v7.1 的所有新增输出写入 outputs/b710_evidence/",
            "v6.0 的 B3LYP/xTB/model_matrix/epsilon_labels 只读",
            "若冻结文件哈希变化, test_b710_evidence 必须失败",
        ],
    }

    path = OUT / "v70_freeze_manifest.json"
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Wrote {path}")
    print(f"frozen artifacts: {len(files)}, protected v6.0: {len(protected)}")
    if missing:
        print(f"MISSING: {missing}")


if __name__ == "__main__":
    main()
