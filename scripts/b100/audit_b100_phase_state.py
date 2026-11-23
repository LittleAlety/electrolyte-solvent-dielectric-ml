#!/usr/bin/env python
"""B100-3: phase-state audit for the whole candidate set, not just 22 molecules.

B100-2 first produced 306 "qualified" molecules, but 290 of them (95%) had never had
their phase state checked -- the earlier audit only covered the original 22-molecule
pool. Calling those molecules qualified would repeat exactly the failure mode PLAN B
v6.0 warns about: a row count standing in for a verified sample.

So this script extends the SAME criterion to every candidate:

    liquid at the stated T  <=>  mp_C  <  (T_K - 273.15)

Melting points come from `liquid_window_gate_report.csv`, which covers 314
molecules. Molecules with no melting point available are NOT assumed liquid -- they
are marked UNKNOWN and cannot enter the confirmed set.

This is the difference between "389 candidates" and "N verified liquid samples", and
it is the number B100 must be planned around.

Output: outputs/b100/phase_state_audit_b100.csv
        outputs/b100/phase_state_audit_b100.json
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
OUT = REPO_ROOT / "outputs" / "b100"
GENERATOR = "audit_b100_phase_state/1.0.0"

QUALIFIED = OUT / "qualified_molecules_b100.csv"
GATE = REPO_ROOT / "data" / "processed" / "liquid_window_gate_report.csv"

# A supercooled liquid is a real, measurable state -- but it is NOT the
# thermodynamic liquid the target quantity describes. Measurements below the melting
# point are retained as data but flagged, never silently counted as liquid.
SUPERCOOL_TOL_K = 0.0

PLACEHOLDERS = {"", "not_evaluated", "nan", "none", "null", "na", "n/a"}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load(path: Path) -> list[dict]:
    raw = path.read_bytes()
    text = None
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        raise RuntimeError(f"cannot decode {path}")
    header = text.splitlines()[0] if text.splitlines() else ""
    delim = ";" if header.count(";") > header.count(",") else ","
    import io
    return list(csv.DictReader(io.StringIO(text, newline=""), delimiter=delim))


def fnum(v):
    s = (v or "").strip()
    if s.lower() in PLACEHOLDERS:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def main() -> int:
    for p in (QUALIFIED, GATE):
        if not p.is_file():
            print(f"FATAL: missing {p}", file=sys.stderr)
            return 2

    qualified = load(QUALIFIED)
    gate = {r["inchikey"]: r for r in load(GATE)}

    # Melting points obtained by the B100-4 fetch take precedence: the gate report
    # only ever covered the original 314-molecule set, so relying on it alone left
    # 269 candidates "unknown" even after their melting points had been retrieved.
    mp_lookup = OUT / "pubchem_mp_lookup_b100.csv"
    fetched_mp: dict[str, float] = {}
    fetched_src: dict[str, str] = {}
    if mp_lookup.is_file():
        for r in load(mp_lookup):
            ik = (r.get("inchikey") or "").strip()
            v = (r.get("mp_C") or "").strip()
            if not ik or not v:
                continue
            try:
                fetched_mp[ik] = float(v)
            except ValueError:
                continue
            fetched_src[ik] = (r.get("mp_note") or "").strip()

    rows: list[dict] = []
    for q in qualified:
        ik = q["inchikey"]
        g = gate.get(ik, {})
        t_k = fnum(q.get("T_K"))
        t_c = (t_k - 273.15) if t_k is not None else None
        gate_mp = fnum(g.get("mp_C"))
        fetch_mp = fetched_mp.get(ik)
        # Prefer the fetched value; fall back to the gate report. Record which was
        # used so the provenance of every phase decision is explicit.
        if fetch_mp is not None:
            mp_c, mp_source = fetch_mp, "PUBCHEM_PUGVIEW"
        elif gate_mp is not None:
            mp_c, mp_source = gate_mp, "LIQUID_WINDOW_GATE"
        else:
            mp_c, mp_source = None, "NONE"
        bp_c = fnum(g.get("bp_C"))

        if mp_c is None or t_c is None:
            status = "UNKNOWN_NO_MP"
            margin = None
        elif mp_c < t_c - SUPERCOOL_TOL_K:
            status = "LIQUID_AT_STATED_T"
            margin = t_c - mp_c
        else:
            status = "SOLID_OR_SUPERCOOLED_AT_STATED_T"
            margin = t_c - mp_c

        # Boiling point sanity: a measurement far above bp is also suspect.
        above_bp = (bp_c is not None and t_c is not None and t_c > bp_c)

        # Boiling point sanity: a measurement ABOVE the normal boiling point is a
        # vapour, not a liquid. Previously this was only recorded as a flag while the
        # molecule still counted as phase-verified liquid.
        above_bp = (bp_c is not None and t_c is not None and t_c > bp_c)
        if above_bp and status == "LIQUID_AT_STATED_T":
            status = "ABOVE_BOILING_POINT"
            margin = None

        rows.append({
            "inchikey": ik,
            "name": q.get("name", ""),
            "layer": q.get("layer", ""),
            "evidence_grade": q.get("evidence_grade", ""),
            "T_K": q.get("T_K", ""),
            "T_C": round(t_c, 3) if t_c is not None else "",
            "epsilon": q.get("epsilon", ""),
            "mp_C": mp_c if mp_c is not None else "",
            "mp_source": mp_source,
            "bp_C": bp_c if bp_c is not None else "",
            "mp_margin_K": round(margin, 3) if margin is not None else "",
            "has_mp_data": "true" if mp_c is not None else "false",
            "phase_status": status,
            "above_boiling_point": "true" if above_bp else "false",
            "phase_verified": "true" if status == "LIQUID_AT_STATED_T" else "false",
        })

    path = OUT / "phase_state_audit_b100.csv"
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        for r in sorted(rows, key=lambda z: z["name"]):
            w.writerow(r)

    by_status = Counter(r["phase_status"] for r in rows)
    n_liquid = by_status.get("LIQUID_AT_STATED_T", 0)
    n_solid = by_status.get("SOLID_OR_SUPERCOOLED_AT_STATED_T", 0)
    n_unknown = by_status.get("UNKNOWN_NO_MP", 0)
    n_above_bp = sum(1 for r in rows if r["above_boiling_point"] == "true")

    # A molecule is "phase-verified liquid" only when it clears the criterion.
    verified = [r for r in rows if r["phase_verified"] == "true"]
    n_verified_qtb = sum(1 for r in verified if r["layer"] == "nbs514_expansion")

    doc = {
        "schema": "b100.phase_state_audit/v1",
        "generator": GENERATOR,
        "generated_at_utc": datetime.now(timezone.utc)
        .replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "why_this_exists": (
            "B100-2 首轮给出 306 个『合格』分子, 但其中 290 个 (95%) 从未做过相态检查 "
            "—— 原审计只覆盖 22 个分子. 把那些分子称为合格, 正是 PLAN B v6.0 "
            "警告的『用行数冒充已验证样本』."
        ),
        "criterion": "mp_C < (T_K - 273.15), 即该物质在设定温度下为液态",
        "rollup_of_qualified_list": {
            "n_input_qualified": len(qualified),
            "n_liquid_at_stated_T": n_liquid,
            "n_solid_or_supercooled": n_solid,
            "n_unknown_no_mp": n_unknown,
            "n_above_boiling_point": n_above_bp,
            "n_phase_verified_liquid": len(verified),
            "of_which_expansion_layer": n_verified_qtb,
        },
        "headline": (
            f"在 B100-2 的 {len(qualified)} 个候选中, "
            f"{len(verified)} 个通过相态验证 ({100*len(verified)/max(len(qualified),1):.1f}%), "
            f"{n_solid} 个在设定温度下低于熔点, "
            f"{n_unknown} 个缺少熔点数据因而无法验证."
        ),
        "consequence_for_target": {
            "hard_threshold": 100,
            "phase_verified_liquid": len(verified),
            "meets_threshold_after_phase_check": len(verified) >= 100,
            "gap": max(0, 100 - len(verified)),
            "note": (
                "缺熔点数据的分子**不得默认当作液态**. 它们需要从 PubChem 或原始"
                "文献补齐熔点后才能计入, 这是可执行的扩充路径, 而不是降低标准."
            ),
        },
        "solid_or_supercooled_examples": [
            {"name": r["name"], "T_C": r["T_C"], "mp_C": r["mp_C"],
             "margin_K": r["mp_margin_K"]}
            for r in sorted(
                [x for x in rows
                 if x["phase_status"] == "SOLID_OR_SUPERCOOLED_AT_STATED_T"],
                key=lambda z: float(z["mp_margin_K"]))[:15]
        ],
        "inputs": {
            "qualified_molecules_b100": {"sha256": sha256_file(QUALIFIED),
                                         "rows": len(qualified)},
            "liquid_window_gate_report": {"sha256": sha256_file(GATE),
                                          "rows": len(gate)},
        },
        "output": {"path": str(path.relative_to(REPO_ROOT)),
                   "sha256": sha256_file(path), "rows": len(rows)},
    }
    j_path = OUT / "phase_state_audit_b100.json"
    j_path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")

    print(f"[B100-3] {j_path}")
    print(f"[B100-3] {path}")
    print(f"  input qualified      = {len(qualified)}")
    print(f"  LIQUID at stated T   = {n_liquid}")
    print(f"  SOLID/supercooled    = {n_solid}")
    print(f"  UNKNOWN (no mp)      = {n_unknown}")
    print(f"  above boiling point  = {n_above_bp}")
    print(f"  PHASE-VERIFIED LIQUID= {len(verified)}  (threshold 100)")
    print(f"  meets threshold      = {len(verified) >= 100}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
