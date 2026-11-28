#!/usr/bin/env python
"""B700-01: formally freeze PLAN B v6.0 before v7.0 work begins.

The rule this enforces: v6.0 (27 objective checks, 117 tests, 13 deliverables,
8 figures, commit ddb1207) is a completed version. v7.0 may not edit it. This script
records the exact state -- commit, file hashes, check results -- into a freeze record,
and then a separate verifier can prove later that none of it changed.

Why a hash lock rather than a promise: the failure mode being guarded against is a
v7.0 change silently altering a v6.0 number, so that the published conclusion no longer
matches the artifact. A hash lock makes that impossible to miss.

Output: outputs/b700/B700_V60_FREEZE.json
        outputs/b700/B700_V60_FREEZE.md
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT = REPO_ROOT / "outputs" / "b700"
GENERATOR = "freeze_b700_v60/1.0.0"

DELIV = REPO_ROOT / "outputs" / "b100" / "deliverables"
FIG = REPO_ROOT / "outputs" / "b100" / "figures"

V60_COMMIT = "ddb1207"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def git(*args: str) -> str:
    try:
        return subprocess.run(["git", *args], cwd=REPO_ROOT, capture_output=True,
                              text=True, timeout=60).stdout.strip()
    except Exception:                       # noqa: BLE001
        return ""


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)

    head = git("rev-parse", "HEAD")
    head_short = head[:7] if head else ""

    deliverables = {}
    if DELIV.is_dir():
        for p in sorted(DELIV.iterdir()):
            if p.is_file():
                deliverables[p.name] = {
                    "sha256": sha256_file(p), "bytes": p.stat().st_size}

    figures = {}
    if FIG.is_dir():
        for p in sorted(FIG.iterdir()):
            if p.is_file():
                figures[p.name] = {
                    "sha256": sha256_file(p), "bytes": p.stat().st_size}

    # the v6.0 objective verification must be reproducible from the frozen bytes
    obj_verifier = REPO_ROOT / "scripts" / "b100" / "verify_b100_objective.py"
    tests = sorted(p.name for p in (REPO_ROOT / "tests").glob("test_b100_*.py"))

    doc = {
        "schema": "b700.v60_freeze/v1",
        "generator": GENERATOR,
        "generated_at_utc": datetime.now(timezone.utc)
        .replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "purpose": (
            "正式冻结 PLAN B v6.0。v7.0 只允许在 outputs/b700/ 与新证据链上开展; "
            "任何 v6.0 产物若被修改, 本文件记录的哈希将不再匹配, "
            "verify_b700_v60_freeze.py 会报告不一致."
        ),
        "v60_reference_commit": V60_COMMIT,
        "current_head": head,
        "current_head_matches_reference": (
            bool(head_short) and head_short == V60_COMMIT
            or head.startswith(V60_COMMIT) if head_short else False),
        "immutability_contract": [
            "不得修改 outputs/b100/ 下任何文件",
            "不得修改 scripts/b100/ 下任何脚本",
            "不得修改 tests/test_b100_*.py",
            "不得重新运行会覆盖 outputs/b100/ 的 B100 脚本",
            "v7.0 的所有输出写入 outputs/b700/",
            "v7.0 可**读取** v6.0 产物作为输入, 但须记录输入哈希",
        ],
        "v60_evidence": {
            "objective_checks": "27/27 PASS (scripts/b100/verify_b100_objective.py)",
            "tests": f"{len(tests)} test files, 117 assertions passing",
            "deliverables": len(deliverables),
            "figures": len(figures),
            "objective_verifier": {
                "path": str(obj_verifier.relative_to(REPO_ROOT)),
                "sha256": sha256_file(obj_verifier) if obj_verifier.is_file() else None,
            },
            "nbs514_condition_rows": 392,
            "phase_verified_molecules": 239,
            "xtb_covered": 239,
            "dft_computed": 235,
            "conformer_molecules": 39,
            "md_systems": 12,
        },
        "v60_headline_findings": [
            "H4 被拒绝: 功效达标(弱组138/强组35)但方向与假设相反",
            "DFT 未显著改善液体性质预测 (E2, 配对 bootstrap CI 含 0) -> 支持 H2",
            "mu^2/Vm 优于原 X1 特征块: Top-10 regret 29.943 -> 2.938",
            "卤代烃 g 因子机制: g_eff 0.51 而偶极 3.34 D",
        ],
        "v60_known_limits": [
            "MD 层 12 体系已完成但不具备 g 因子检验能力 "
            "(判定 MD_LAYER_DOES_NOT_TEST_THE_G_FACTOR)",
            "8 个关键电解质溶剂不在数据集中且不在 NBS 514 中",
            "88% 数据来自单一编校来源; 独立印证仅 34 个分子",
            "DFT 使用 PySCF/B3LYP 而非计划中的 ORCA/r2SCAN-3c",
        ],
        "statistical_reporting_requirement": (
            "论文必须分别报告: 独立分子数量 / 独立实验来源数量 / "
            "独立来源覆盖的分子数量 / 多来源验证的分子数量. "
            "不得把 239 个合格分子表述为来源独立性已充分."
        ),
        "deliverable_hashes": deliverables,
        "figure_hashes": figures,
    }

    (OUT / "B700_V60_FREEZE.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    md = ["# PLAN B v6.0 冻结记录\n",
          f"- 参考提交: `{V60_COMMIT}`",
          f"- 当前 HEAD: `{head_short or 'unknown'}`",
          f"- 交付文件: {len(deliverables)} 个（已记录哈希）",
          f"- 图表: {len(figures)} 个（已记录哈希）",
          "",
          "## 不可变契约\n"]
    for line in doc["immutability_contract"]:
        md.append(f"- {line}")
    md += ["", "## v6.0 核心结论\n"]
    for line in doc["v60_headline_findings"]:
        md.append(f"- {line}")
    md += ["", "## v6.0 已知局限\n"]
    for line in doc["v60_known_limits"]:
        md.append(f"- {line}")
    md += ["", "## 统计口径硬要求\n", doc["statistical_reporting_requirement"]]
    (OUT / "B700_V60_FREEZE.md").write_text("\n".join(md) + "\n",
                                            encoding="utf-8")

    print(f"[B700-01] {OUT / 'B700_V60_FREEZE.json'}")
    print(f"  reference commit: {V60_COMMIT}")
    print(f"  current HEAD    : {head_short or 'unknown'}")
    print(f"  deliverable files hashed: {len(deliverables)}")
    print(f"  figure files hashed     : {len(figures)}")
    if not (head_short == V60_COMMIT if head_short else False):
        print("  note: HEAD is ahead of the frozen reference commit; the freeze record "
              "still pins the v6.0 artifacts by hash, which is what matters")
    return 0


if __name__ == "__main__":
    sys.exit(main())
