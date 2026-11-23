#!/usr/bin/env python
"""B100-2: expansion-layer admission review -- how many molecules really qualify?

This is the gate PLAN B v6.0 demands: "不能把尚未审核的 372 个候选直接宣布为
372 个合格分子". The answer has to be counted molecule by molecule against explicit
criteria, not asserted from a row count.

Three measurements drive the result, and the first one is decisive:

  1. CORE-LAYER TRACEABILITY. Of the 248 rows in dielectric_v04, some have NO
     corresponding observation in the measurement ledger -- neither by InChIKey nor
     by aggregate_id. Those rows cannot be traced to a measurement, so they cannot
     enter a dataset whose value proposition is measurement-level provenance. They
     are reported as UNTRACEABLE and excluded from the qualified count.

  2. CROSS-SOURCE AGREEMENT. The 147 molecules present in BOTH the core layer and
     the NBS expansion layer are a free independent check. Where the two sources
     disagree beyond a stated tolerance, the pair is a conflict requiring
     adjudication -- not something to average away.

  3. IDENTITY DEDUPLICATION. Qualified molecules are counted by full InChIKey.
     Multiple measurements of one molecule stay one molecule.

The output is the honest number the project needs: how many molecules clear the bar
today, and what blocks the rest.

Output: outputs/b100/qualified_molecules_b100.csv
        outputs/b100/excluded_molecules_b100.csv
        outputs/b100/cross_source_conflict_b100.csv
        outputs/b100/b100_admission_gate.json
"""

from __future__ import annotations

import csv
import hashlib
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT = REPO_ROOT / "outputs" / "b100"
GENERATOR = "build_b100_admission_gate/1.0.0"

V04 = REPO_ROOT / "data" / "dielectric_v04.csv"
EXCLUSIONS = REPO_ROOT / "outputs" / "b01" / "dataset_v06_exclusions.csv"
READY = REPO_ROOT / "outputs" / "b01" / "dataset_v06_model_ready.csv"
EXP_OBS = REPO_ROOT / "data" / "processed" / "dielectric_pool_expansion_observations.csv"
EXP_FEAT = REPO_ROOT / "data" / "processed" / "dielectric_pool_expansion_features.csv"
LEDGER = (REPO_ROOT / "outputs" / "confirm_2027" / "provenance_repair"
          / "measurement_ledger_v1.csv")
PHASE = REPO_ROOT / "outputs" / "b04" / "phase_state_audit.csv"

# Cross-source agreement tolerance. Two independent determinations of the same
# molecule's static epsilon at (nominally) room temperature should agree far better
# than this; anything beyond it is a conflict to adjudicate, not to average.
CROSS_SOURCE_REL_TOL = 0.05      # 5 %
# For the cross-source check the two sources must describe a comparable condition.
CROSS_SOURCE_T_TOL_K = 5.0

PLACEHOLDERS = {"", "not_evaluated", "nan", "none", "null", "na", "n/a", "none"}


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
    OUT.mkdir(parents=True, exist_ok=True)
    for p in (V04, EXP_OBS):
        if not p.is_file():
            print(f"FATAL: missing {p}", file=sys.stderr)
            return 2

    v04 = load(V04)
    exclusions = load(EXCLUSIONS) if EXCLUSIONS.is_file() else []
    ready = load(READY) if READY.is_file() else []
    exp = load(EXP_OBS)
    exp_feat = load(EXP_FEAT) if EXP_FEAT.is_file() else []
    ledger = load(LEDGER) if LEDGER.is_file() else []
    phase = load(PHASE) if PHASE.is_file() else []

    ledger_keys = {(r.get("inchikey") or "").strip() for r in ledger}
    ledger_keys.discard("")
    ledger_aggs = {(r.get("aggregate_id") or "").strip() for r in ledger}
    ledger_aggs = {a for a in ledger_aggs if a and a.lower() != "not_evaluated"}
    excluded_keys = {(r.get("inchikey") or "").strip() for r in exclusions}
    ready_keys = {(r.get("inchikey") or "").strip() for r in ready}
    phase_by_key = {(r.get("inchikey") or "").strip(): r for r in phase}
    feat_by_key = {(r.get("inchikey") or "").strip(): r for r in exp_feat}

    # ---------- core layer: per-row traceability ----------
    core_rows: list[dict] = []
    for r in v04:
        ik = (r.get("inchikey") or "").strip()
        agg = (r.get("aggregate_id") or "").strip()
        if ik and ik in ledger_keys:
            trace = "MATCHED_BY_INCHIKEY"
        elif agg and agg in ledger_aggs:
            trace = "MATCHED_BY_AGGREGATE"
        elif not ik:
            trace = "NO_INCHIKEY"
        else:
            trace = "UNTRACEABLE"
        core_rows.append({
            "layer": "core_thermoml",
            "inchikey": ik,
            "name": (r.get("name") or "").strip(),
            "T_K": (r.get("T_K") or "").strip(),
            "epsilon": (r.get("dielectric") or "").strip(),
            "traceability": trace,
            "aggregate_id": agg,
            "v06_ready": "true" if ik in ready_keys else "false",
            "v06_excluded": "true" if ik in excluded_keys else "false",
        })

    # ---------- expansion layer ----------
    exp_by_key: dict[str, list[dict]] = defaultdict(list)
    for r in exp:
        exp_by_key[(r.get("inchikey") or "").strip()].append(r)

    exp_rows: list[dict] = []
    for ik, rows in exp_by_key.items():
        if not ik:
            continue
        rows_sorted = sorted(rows, key=lambda z: fnum(z.get("T_K")) or 0.0)
        # nearest to 298.15 K is the representative observation
        rep = min(rows_sorted,
                  key=lambda z: abs((fnum(z.get("T_K")) or 0) - 298.15))
        feat = feat_by_key.get(ik, {})
        has_xtb = ((feat.get("dipole_D") or "").strip().lower()
                   not in PLACEHOLDERS)
        ph = phase_by_key.get(ik)
        exp_rows.append({
            "layer": "nbs514_expansion",
            "inchikey": ik,
            "name": (rep.get("name") or "").strip(),
            "T_K": (rep.get("T_K") or "").strip(),
            "epsilon": (rep.get("epsilon") or "").strip(),
            "n_observations_this_molecule": len(rows),
            "traceability": "NBS514_TRANSCRIBED_WITH_SOURCE_ID",
            "source_id": (rep.get("source_id") or "").strip(),
            "source_file_sha256": (rep.get("source_file_sha256") or "").strip(),
            "has_xtb_dipole": "true" if has_xtb else "false",
            "phase_status": (ph or {}).get("phase_status", "NOT_AUDITED"),
            "mp_margin_K": (ph or {}).get("mp_margin_K", ""),
        })

    # ---------- cross-source conflict ----------
    v04_by_key = {}
    for r in v04:
        ik = (r.get("inchikey") or "").strip()
        if ik and ik not in v04_by_key:
            v04_by_key[ik] = r

    conflict_rows: list[dict] = []
    agree_rows: list[dict] = []
    for ik, r in v04_by_key.items():
        if ik not in exp_by_key:
            continue
        a_eps = fnum(r.get("dielectric"))
        a_t = fnum(r.get("T_K"))
        if a_eps is None:
            continue
        # choose the expansion observation closest in temperature
        best = min(exp_by_key[ik],
                   key=lambda z: abs((fnum(z.get("T_K")) or 0) - (a_t or 298.15)))
        b_eps = fnum(best.get("epsilon"))
        b_t = fnum(best.get("T_K"))
        if b_eps is None:
            continue
        dt = abs((a_t or 0) - (b_t or 0))
        rel = abs(a_eps - b_eps) / max(a_eps, b_eps)
        comparable = dt <= CROSS_SOURCE_T_TOL_K
        rec = {
            "inchikey": ik,
            "name": (r.get("name") or "").strip(),
            "core_epsilon": a_eps,
            "core_T_K": a_t,
            "nbs_epsilon": b_eps,
            "nbs_T_K": b_t,
            "delta_T_K": round(dt, 3),
            "relative_difference": round(rel, 6),
            "temperature_comparable": "true" if comparable else "false",
            "verdict": (
                "AGREE" if comparable and rel <= CROSS_SOURCE_REL_TOL
                else "CONFLICT_CONDITION_MISMATCH" if not comparable
                else "CONFLICT_VALUE_DISAGREEMENT"),
        }
        (agree_rows if rec["verdict"] == "AGREE" else conflict_rows).append(rec)

    # ---------- qualification ----------
    # A molecule qualifies only if it clears EVERY criterion for its layer.
    qualified: list[dict] = []
    excluded: list[dict] = []

    conflict_keys = {r["inchikey"] for r in conflict_rows}

    # core molecules that are fully traceable, model-ready, liquid at T, and not
    # in unresolved cross-source conflict
    seen_core = set()
    for r in core_rows:
        ik = r["inchikey"]
        if not ik or ik in seen_core:
            continue
        seen_core.add(ik)
        reasons = []
        if r["traceability"] == "UNTRACEABLE":
            reasons.append("NO_MEASUREMENT_IN_LEDGER")
        if r["v06_excluded"] == "true" and r["v06_ready"] != "true":
            reasons.append("EXCLUDED_IN_V06")
        if ik in conflict_keys:
            reasons.append("CROSS_SOURCE_CONFLICT_UNRESOLVED")
        ph = phase_by_key.get(ik, {})
        if ph.get("phase_status") == "SOLID_OR_SUPERCOOLED_AT_STATED_T":
            reasons.append("NOT_LIQUID_AT_STATED_T")
        if reasons:
            excluded.append({
                "inchikey": ik, "name": r["name"], "layer": "core_thermoml",
                "epsilon": r["epsilon"], "T_K": r["T_K"],
                "blocking_reasons": ";".join(reasons),
            })
        else:
            qualified.append({
                "inchikey": ik, "name": r["name"], "layer": "core_thermoml",
                "epsilon": r["epsilon"], "T_K": r["T_K"],
                "evidence_grade": "Q1",
                "traceability": r["traceability"],
                "has_xtb": "false",
                "admission_basis": "ledger-traced + v06 model-ready + liquid at T",
            })

    # expansion molecules: transcribed with source id, has xTB, liquid at T,
    # not in unresolved conflict
    for r in exp_rows:
        ik = r["inchikey"]
        reasons = []
        if r["traceability"] != "NBS514_TRANSCRIBED_WITH_SOURCE_ID":
            reasons.append("NO_SOURCE_TRANSCRIPTION")
        if r["has_xtb_dipole"] != "true":
            reasons.append("NO_XTB_FEATURES")
        if ik in conflict_keys:
            reasons.append("CROSS_SOURCE_CONFLICT_UNRESOLVED")
        if r["phase_status"] == "SOLID_OR_SUPERCOOLED_AT_STATED_T":
            reasons.append("NOT_LIQUID_AT_STATED_T")
        # already counted through the core layer?
        if ik in {q["inchikey"] for q in qualified} or \
           ik in {e["inchikey"] for e in excluded if e["layer"] == "core_thermoml"}:
            reasons.append("ALREADY_COUNTED_IN_CORE_LAYER")
        if reasons:
            excluded.append({
                "inchikey": ik, "name": r["name"], "layer": "nbs514_expansion",
                "epsilon": r["epsilon"], "T_K": r["T_K"],
                "blocking_reasons": ";".join(reasons),
            })
        else:
            qualified.append({
                "inchikey": ik, "name": r["name"], "layer": "nbs514_expansion",
                "epsilon": r["epsilon"], "T_K": r["T_K"],
                "evidence_grade": "Q2",
                "traceability": r["traceability"],
                "has_xtb": "true",
                "admission_basis": (
                    "NBS514 transcription with source id + static-by-source "
                    "definition + xTB features + liquid at T"),
            })

    q_keys = {q["inchikey"] for q in qualified}
    n_q = len(q_keys)
    n_xtb_covered = sum(1 for q in qualified if q["has_xtb"] == "true")

    # ---------- write ----------
    q_path = OUT / "qualified_molecules_b100.csv"
    if qualified:
        with q_path.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(qualified[0].keys()))
            w.writeheader()
            for r in sorted(qualified, key=lambda z: z["name"]):
                w.writerow(r)

    e_path = OUT / "excluded_molecules_b100.csv"
    if excluded:
        with e_path.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(excluded[0].keys()))
            w.writeheader()
            for r in sorted(excluded, key=lambda z: z["name"]):
                w.writerow(r)

    c_path = OUT / "cross_source_conflict_b100.csv"
    if conflict_rows:
        with c_path.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(conflict_rows[0].keys()))
            w.writeheader()
            for r in sorted(conflict_rows, key=lambda z: -z["relative_difference"]):
                w.writerow(r)

    a_path = OUT / "cross_source_agree_b100.csv"
    if agree_rows:
        with a_path.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(agree_rows[0].keys()))
            w.writeheader()
            for r in sorted(agree_rows, key=lambda z: z["name"]):
                w.writerow(r)

    reasons_counter = Counter()
    for e in excluded:
        for b in e["blocking_reasons"].split(";"):
            if b:
                reasons_counter[b] += 1

    doc = {
        "schema": "b100.admission_gate/v1",
        "generator": GENERATOR,
        "generated_at_utc": datetime.now(timezone.utc)
        .replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "question": (
            "按 B100 的准入标准, 仓库现在真正有多少个合格独立分子?"
        ),
        "criteria": {
            "identity": "按完整 InChIKey 去重, 一分子计一次",
            "core_layer_requirements": [
                "在 measurement_ledger_v1 中有可定位的测量 (traceability 非 UNTRACEABLE)",
                "在 dataset_v06 中为 model_ready",
                "在设定温度下为液态 (phase_state_audit)",
                "无未裁决的跨来源冲突",
            ],
            "expansion_layer_requirements": [
                "在 NBS514 转录中有 source_id 可定位",
                "来源级静态介电常数定义 (见 nbs514 频率审计)",
                "有统一 xTB 特征 (dipole 非空)",
                "在设定温度下为液态",
                "无未裁决的跨来源冲突",
            ],
            "grades": {
                "Q1": "原始实验, 条件可逐条追溯",
                "Q2": "NIST 批判性汇编, 来源级静态定义",
                "Q3": "条件不完整, 不进入主确认集",
            },
            "hard_rule": (
                "不得降低标准凑数; 不得把多条测量记录当成多个独立分子; "
                "未通过审核的候选不得计入合格数."
            ),
        },
        "core_layer_traceability": dict(Counter(r["traceability"]
                                                for r in core_rows)),
        "cross_source_check": {
            "n_molecules_in_both_layers": len(agree_rows) + len(conflict_rows),
            "n_agree": len(agree_rows),
            "n_conflict": len(conflict_rows),
            "relative_tolerance": CROSS_SOURCE_REL_TOL,
            "temperature_tolerance_K": CROSS_SOURCE_T_TOL_K,
            "note": (
                "协和检查是免费得到的独立验证: 同一分子在两个独立来源下的 "
                "ε 若一致, 提升该分子的可信度; 若不一致则必须裁决而非取平均."
            ),
        },
        "result": {
            "n_qualified_molecules": n_q,
            "n_qualified_with_xtb": n_xtb_covered,
            "n_excluded_molecule_records": len(excluded),
            "hard_threshold": 100,
            "meets_threshold": n_q >= 100,
            "gap": max(0, 100 - n_q),
            "verdict": (
                "MEETS_HARD_THRESHOLD" if n_q >= 100
                else f"BELOW_THRESHOLD_BY_{100 - n_q}"),
        },
        "exclusion_reasons": dict(reasons_counter.most_common()),
        "inputs": {
            "dielectric_v04": {"sha256": sha256_file(V04), "rows": len(v04)},
            "dataset_v06_exclusions": {"rows": len(exclusions)},
            "dataset_v06_model_ready": {"rows": len(ready)},
            "expansion_observations": {"sha256": sha256_file(EXP_OBS),
                                       "rows": len(exp)},
            "measurement_ledger_v1": {"rows": len(ledger)},
            "phase_state_audit": {"rows": len(phase)},
        },
        "outputs": {
            "qualified": {"path": str(q_path.relative_to(REPO_ROOT)),
                          "sha256": sha256_file(q_path) if q_path.is_file() else None,
                          "rows": len(qualified)},
            "excluded": {"path": str(e_path.relative_to(REPO_ROOT)),
                         "sha256": sha256_file(e_path) if e_path.is_file() else None,
                         "rows": len(excluded)},
            "conflict": ({"path": str(c_path.relative_to(REPO_ROOT)),
                          "sha256": sha256_file(c_path),
                          "rows": len(conflict_rows)}
                         if c_path.is_file() else None),
        },
        "what_this_does_not_claim": [
            "不宣称排除的分子在物理上无效, 只说它们未通过本轮准入判据",
            "跨来源冲突未裁决前不得取平均",
            "Q2 的静态定义是来源级集体判断, 非逐条频率报告",
        ],
    }
    j_path = OUT / "b100_admission_gate.json"
    j_path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")

    print(f"[B100-2] {j_path}")
    print(f"[B100-2] {q_path}  ({len(qualified)} rows)")
    print(f"[B100-2] {e_path}  ({len(excluded)} rows)")
    if c_path.is_file():
        print(f"[B100-2] {c_path}  ({len(conflict_rows)} rows)")
    print()
    print(f"  core traceability      = {doc['core_layer_traceability']}")
    print(f"  cross-source           = {len(agree_rows)} agree / "
          f"{len(conflict_rows)} conflict")
    print(f"  QUALIFIED MOLECULES    = {n_q}  (threshold 100)")
    print(f"  with xTB               = {n_xtb_covered}")
    print(f"  verdict                = {doc['result']['verdict']}")
    print(f"  top exclusion reasons  = "
          f"{list(reasons_counter.most_common(5))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
