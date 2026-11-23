#!/usr/bin/env python
"""B04-2: phase-state audit of the candidate pool.

Reviewer 1 (B04+B05) flagged that some pool molecules are measured *below their
melting point*, i.e. the samples are solids or supercooled liquids, not
thermodynamic liquids. That matters because the target quantity is the static
relative permittivity **of a pure liquid**.

The subtlety the first pass missed: the repository already has a
`liquid_window_gate_report.csv`, but that gate asks a different question. It
tests whether a measurement temperature falls inside a declared **[T_low, T_high]
observation window** (-20 to 60 C), not whether the substance is liquid *at that
temperature*. Every blocked row there carries the reason `mp_above_T_low`, which
compares the melting point to the window's LOWER BOUND, not to the measured
temperature. So the gate cannot answer the phase question at all.

This audit asks the right question directly:

    is  mp_C  <  (T_K - 273.15)  ?

A molecule that fails it is solid (or supercooled) at the stated temperature and
must be flagged -- either excluded from confirmatory use, or retained with an
explicit supercooled-state caveat.

Output: outputs/b04/phase_state_audit.csv
        outputs/b04/phase_state_audit.json
"""

from __future__ import annotations

import csv
import hashlib
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = REPO_ROOT / "outputs" / "b04"
GENERATOR = "audit_pool_phase_state/1.0.0"

POOL = OUT_DIR / "candidate_pool_v2_draft.csv"
GATE = REPO_ROOT / "data" / "processed" / "liquid_window_gate_report.csv"

PLACEHOLDERS = {"", "not_evaluated", "nan", "none", "null", "na", "n/a"}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def fnum(v):
    s = (v or "").strip()
    if s.lower() in PLACEHOLDERS:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def main() -> int:
    for p in (POOL, GATE):
        if not p.is_file():
            print(f"FATAL: missing {p}", file=sys.stderr)
            return 2
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    pool = load(POOL)
    gate = {r["inchikey"]: r for r in load(GATE)}

    rows: list[dict] = []
    for p in pool:
        g = gate.get(p["inchikey"], {})
        t_k = fnum(p["T_K"])
        t_c = (t_k - 273.15) if t_k is not None else None
        mp_c = fnum(g.get("mp_C"))
        bp_c = fnum(g.get("bp_C"))
        window_low = fnum(g.get("T_low_C"))
        window_high = fnum(g.get("T_high_C"))

        # THE phase question: is the substance liquid at the measured T?
        if mp_c is None or t_c is None:
            phase_status = "UNKNOWN_NO_MP"
            margin = None
        elif mp_c < t_c:
            phase_status = "LIQUID_AT_STATED_T"
            margin = t_c - mp_c
        else:
            phase_status = "SOLID_OR_SUPERCOOLED_AT_STATED_T"
            margin = t_c - mp_c

        # Does the existing gate agree? (It answers a different question.)
        gate_decision = (g.get("gate_decision") or "").strip()
        if gate_decision == "blocked" and phase_status == "LIQUID_AT_STATED_T":
            gate_agreement = "GATE_BLOCKED_BUT_ACTUALLY_LIQUID"
        elif gate_decision == "pass" and phase_status == "SOLID_OR_SUPERCOOLED_AT_STATED_T":
            gate_agreement = "GATE_PASSED_BUT_ACTUALLY_SOLID"
        elif gate_decision in ("pass", "blocked") and phase_status.startswith(
                "LIQUID" if gate_decision == "pass" else "SOLID"):
            gate_agreement = "AGREE"
        else:
            gate_agreement = "NOT_COMPARABLE"

        rows.append({
            "measurement_id": p["measurement_id"],
            "inchikey": p["inchikey"],
            "name": p["name"],
            "T_K": p["T_K"],
            "T_C": round(t_c, 4) if t_c is not None else "",
            "mp_C": mp_c if mp_c is not None else "",
            "bp_C": bp_c if bp_c is not None else "",
            "window_low_C": window_low if window_low is not None else "",
            "window_high_C": window_high if window_high is not None else "",
            "mp_margin_K": round(margin, 4) if margin is not None else "",
            "phase_status": phase_status,
            "existing_gate_decision": gate_decision,
            "existing_gate_reasons": (g.get("trigger_reasons") or "").strip(),
            "gate_agreement": gate_agreement,
            "downstream_rule": (
                "可以作为液体测量使用"
                if phase_status == "LIQUID_AT_STATED_T"
                else "必须标记为过冷/固态; 不得作为热力学液体证据, "
                     "除非原始文献明确声明过冷状态"
            ),
        })

    csv_path = OUT_DIR / "phase_state_audit.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        for r in rows:
            w.writerow(r)

    by_status = Counter(r["phase_status"] for r in rows)
    by_agreement = Counter(r["gate_agreement"] for r in rows)
    solid = [r for r in rows
             if r["phase_status"] == "SOLID_OR_SUPERCOOLED_AT_STATED_T"]

    doc = {
        "schema": "b04.phase_state_audit/v1",
        "generator": GENERATOR,
        "generated_at_utc": datetime.now(timezone.utc)
        .replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "question": (
            "候选池中每个分子在其**设定温度**下是否真的是液体? "
            "判据: mp_C < (T_K - 273.15)."
        ),
        "why_the_existing_gate_cannot_answer_this": (
            "liquid_window_gate_report.csv 的 blocked 理由统一写作 mp_above_T_low, "
            "它比较的是**熔点与观测窗口下界(-20 C)**, 不是**熔点与实测温度**. "
            "因此它无法回答相态问题. 例如二甲基碳酸酯 mp=0.5 C 在 25 C 下是液体, "
            "但该门会因为它高于窗口下界而判 blocked."
        ),
        "inputs": {
            "candidate_pool_v2_draft": {"sha256": sha256_file(POOL),
                                        "rows": len(pool)},
            "liquid_window_gate_report": {"sha256": sha256_file(GATE),
                                          "rows": len(gate)},
        },
        "counts": {
            "n_pool": len(rows),
            "by_phase_status": dict(sorted(by_status.items())),
            "by_gate_agreement": dict(sorted(by_agreement.items())),
            "n_solid_or_supercooled": len(solid),
        },
        "solid_or_supercooled": [
            {"name": r["name"], "T_C": r["T_C"], "mp_C": r["mp_C"],
             "margin_K": r["mp_margin_K"]}
            for r in sorted(solid, key=lambda z: -float(z["mp_margin_K"]))
        ],
        "finding": (
            f"{len(solid)}/{len(rows)} 个候选分子在其设定温度下**低于熔点**, "
            f"即样品是固态或过冷液体, 不是热力学液体."
        ),
        "consequence": (
            "液体静态介电常数是**液相**性质. 对过冷样品测得的 ε 在数值上可能正确, "
            "但它描述的是一个亚稳态, 列为『液体』会误导下游使用者. "
            "处理方式: 保留数据但显式标记, 或从确认性样本中排除 —— "
            "不得静默当作正常液体."
        ),
        "reviewer": "Reviewer 1 (B04+B05) 独立发现; 本审计用正确判据复现其结论",
        "output": {"path": str(csv_path.relative_to(REPO_ROOT)),
                   "sha256": sha256_file(csv_path), "rows": len(rows)},
    }
    json_path = OUT_DIR / "phase_state_audit.json"
    json_path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
                         encoding="utf-8")

    print(f"[B04-2] {csv_path}")
    print(f"[B04-2] {json_path}")
    print(f"  phase status: {dict(sorted(by_status.items()))}")
    print(f"  gate agreement: {dict(sorted(by_agreement.items()))}")
    print(f"  SOLID_OR_SUPERCOOLED: {len(solid)}/{len(rows)}")
    for r in sorted(solid, key=lambda z: -float(z["mp_margin_K"])):
        print(f"    {r['name'][:32]:32s} T={r['T_C']:>7} C  mp={r['mp_C']:>7} C  "
              f"margin={r['mp_margin_K']:>+7} K")
    return 0


if __name__ == "__main__":
    sys.exit(main())
