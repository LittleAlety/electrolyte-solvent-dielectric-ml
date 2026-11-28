#!/usr/bin/env python
"""B701-03: freeze the ORCA r2SCAN-3c protocol as method_freeze_v2.

v6.0 froze a method that turned out to be a substitution: PySCF/B3LYP instead of the
planned ORCA/r2SCAN-3c. v7.0 does the planned method properly, so it needs its own
freeze that says exactly what was run, on what geometry, with which version, and what
the preflight established before production was allowed to start.

The freeze only issues if the preflight gates actually passed. A protocol freeze that
can be written without passing its own preflight is not a gate.

Output: outputs/b700/B701_DFT/method_freeze_v2.json
        outputs/b700/B701_DFT/method_freeze_v2.md
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
B701 = REPO_ROOT / "outputs" / "b700" / "B701_DFT"
PRE = B701 / "preflight_12"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def jload(p: Path):
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}


def main() -> int:
    sp = jload(PRE / "preflight_report_sp.json")
    opt = jload(PRE / "preflight_report_opt.json")
    # the parser writes one report per stage; the opt stage overwrote it, so read the
    # parsed csvs instead for per-stage convergence
    import csv
    import io

    def read(path):
        if not path.is_file():
            return []
        return list(csv.DictReader(io.StringIO(path.read_text(encoding="utf-8-sig"),
                                               newline="")))

    parsed_sp = read(PRE / "parsed_sp.csv")
    parsed_opt = read(PRE / "parsed_opt.csv")

    def stage_gate(rows, need_opt_conv: bool):
        n = len(rows)
        ok = sum(1 for r in rows if r.get("status") == "OK")
        conv = sum(1 for r in rows
                   if r.get("optimization_converged") == "True")
        has_alpha = sum(1 for r in rows
                        if (r.get("polarizability_au") or "").strip()
                        and r.get("polarizability_au") != "None")
        return {
            "n_jobs": n,
            "n_terminated_normally": ok,
            "n_optimization_converged": conv,
            "n_with_polarizability": has_alpha,
            "passes": (n >= 12 and ok == n
                       and (conv == n or not need_opt_conv)
                       and has_alpha == n),
        }

    gate_sp = stage_gate(parsed_sp, need_opt_conv=False)
    gate_opt = stage_gate(parsed_opt, need_opt_conv=True)

    fixture = (sp.get("parser_fixture_check") or {})

    gates = {
        "orca_runs_12_of_12_sp": gate_sp["n_terminated_normally"] == gate_sp["n_jobs"] == 12,
        "orca_runs_12_of_12_opt": gate_opt["n_terminated_normally"] == gate_opt["n_jobs"] == 12,
        "optimization_converged_12_of_12": gate_opt["n_optimization_converged"] == 12,
        "polarizability_parsed_12_of_12": (gate_sp["n_with_polarizability"] == 12
                                           and gate_opt["n_with_polarizability"] == 12),
        "parser_matches_independent_orca_run": bool(fixture.get("passes")),
    }
    all_pass = all(gates.values())

    doc = {
        "schema": "b700.method_freeze_v2/v1",
        "generated_at_utc": datetime.now(timezone.utc)
        .replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "status": "FROZEN" if all_pass else "NOT_FROZEN",
        "why_v2_exists": (
            "v6.0 的 DFT 层是 PySCF/B3LYP, 而计划要求 ORCA/r2SCAN-3c, "
            "这属于方法替换而非等价实现. v7.0 按计划执行真正的 r2SCAN-3c, "
            "因此需要一份独立的方法学冻结, 不能沿用 v6.0 的说明."
        ),
        "preflight_gates": gates,
        "preflight_detail": {"sp": gate_sp, "opt": gate_opt,
                             "parser_fixture": fixture},
        "protocol": {
            "program": "ORCA",
            "version_expected": "6.1.1",
            "program_path": "/home/pengqihang/project/soft/orca",
            "method": "r2SCAN-3c",
            "method_composition": "r2SCAN + D4 + gCP + def2-mTZVPP (ORCA built-in)",
            "charge": 0,
            "multiplicity": 1,
            "scf": {"maxiter": 300, "tolx": 1e-7, "tole": 1e-8},
            "maxcore_mb": 2000,
            "elprop": "Polar 1 (static polarizability)",
            "parallel": {"slurm_ntasks": 4, "cpus_per_task": 1,
                         "pal_nprocs": 4,
                         "module": "openmpi/5.0",
                         "note": ("ORCA 自己调用 mpirun, 必须给 N 个 task slot; "
                                  "并需 module load openmpi/5.0, 否则 startup 阶段"
                                  "死于 mpirun: command not found")},
        },
        "layers": {
            "fixed_geometry_single_point": {
                "geometry": "GFN2-xTB optimised (v6.0 使用的同一几何)",
                "purpose": ("分离电子结构方法差异: 只有方法变, 几何不变, "
                            "因此描述符差异可归因于方法"),
            },
            "optimised_geometry": {
                "geometry": "r2SCAN-3c 优化几何",
                "purpose": ("生产特征层: 几何与性质来自同一方法, 内部一致, "
                            "但不能与 v6.0 一一对比"),
            },
            "v60_b3lyp_reference": {
                "geometry": "GFN2-xTB 优化几何",
                "purpose": "历史对照层, 保留不动, 用于三方分解方法/几何效应",
            },
        },
        "what_this_freeze_does_NOT_claim": [
            "预检通过不等于 239 个分子都会成功; 失败必须保留失败证书, 不得从分母删除",
            "r2SCAN-3c 是为几何与热化学参数化的复合方法, 它的偶极/极化率可靠性"
            "由本预检的性质层面检查支持, 不能由能量收敛自动推出",
            "偶极与极化率通过预检不代表所有描述符都正确",
        ],
        "preflight_timing": {
            "sp_seconds_per_molecule": "22-35 (4 cores)",
            "opt_seconds_per_molecule": "~120 (4 cores)",
            "note": "用于 239 分子生产的成本估算",
        },
        "inputs_hashed": {
            "parsed_sp.csv": sha256_file(PRE / "parsed_sp.csv")
            if (PRE / "parsed_sp.csv").is_file() else None,
            "parsed_opt.csv": sha256_file(PRE / "parsed_opt.csv")
            if (PRE / "parsed_opt.csv").is_file() else None,
        },
    }

    (B701 / "method_freeze_v2.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    md = ["# 方法学冻结 v2 — ORCA r2SCAN-3c\n",
          f"- 状态: **{doc['status']}**",
          f"- 程序: ORCA {doc['protocol']['version_expected']} @ "
          f"`{doc['protocol']['program_path']}`",
          f"- 方法: `{doc['protocol']['method']}` "
          f"({doc['protocol']['method_composition']})",
          f"- 电荷/多重度: {doc['protocol']['charge']} / "
          f"{doc['protocol']['multiplicity']}",
          "",
          "## 预检闸门\n"]
    for k, v in gates.items():
        md.append(f"- {'PASS' if v else 'FAIL'} — {k}")
    md += ["", "## 三层设计\n"]
    for k, v in doc["layers"].items():
        md.append(f"- **{k}**: {v['purpose']}")
    md += ["", "## 本冻结不声称的事\n"]
    for line in doc["what_this_freeze_does_NOT_claim"]:
        md.append(f"- {line}")
    (B701 / "method_freeze_v2.md").write_text("\n".join(md) + "\n",
                                              encoding="utf-8")

    print(f"[B701-03] method_freeze_v2: {doc['status']}")
    for k, v in gates.items():
        print(f"  {'PASS' if v else 'FAIL'}  {k}")
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
