#!/usr/bin/env python
"""B03-1: build the A18 evidence gap register.

PLAN B B03 asks for an `A18_gap_register.csv` describing what evidence is missing
for each of the 18 common molecules. This script assembles it from the frozen
evidence already in the repository -- it does not search literature (that is the
next step) and it does not invent measurements.

The register's job is to make each gap *specific enough to act on*. A row that
says "DMC: insufficient data" is useless. A row that says "DMC: 5 observations,
1 in the room-temperature band, single source, static 0 Hz confirmed, blocker =
no independent source" tells a researcher exactly what to look for.

Priority tiers follow PLAN B B03's own grouping:
    P0  DMC / DEC / SL          -- four-agent consistency review only, no new data
    P1  DME / TEGDME / GBL / DMSO -- J04 provenance + four-agent review first
    P2  SN                      -- find 293.15-303.15 K; 333.15 K must not be folded
    P3  AN                      -- find static 0 Hz; 0.01/1 MHz is not a substitute
    P4  EMC/EC/PC/FEC/VC/DOL/EA/MA/TMP -- zero observations, literature search

Output: outputs/confirm_2027/evidence_backfill/A18_gap_register.csv
        outputs/confirm_2027/evidence_backfill/A18_gap_register.json
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
OUT_DIR = REPO_ROOT / "outputs" / "confirm_2027" / "evidence_backfill"
CONFIRM = REPO_ROOT / "outputs" / "confirm_2027"
GENERATOR = "build_a18_gap_register/1.0.0"

PRIORITY_FILE = CONFIRM / "intersections" / "a18_source_backfill_priority.csv"
MEAS_LEDGER = CONFIRM / "provenance_repair" / "measurement_ledger_v1.csv"
PAIR_VALIDITY = CONFIRM / "provenance_repair" / "condition_pair_validity_v1.csv"
GAP_AUDIT = CONFIRM / "provenance_audit" / "gap_aggregation_audit.csv"
COVERAGE_REG = CONFIRM / "identity_and_coverage" / "coverage_gap_registry.csv"
INDEP = CONFIRM / "provenance_repair" / "source_independence_report.json"

BAND_LOW = 293.15
BAND_HIGH = 303.15

PLACEHOLDERS = {"", "not_evaluated", "nan", "none", "null", "na", "n/a"}

# PLAN B B03's own tier grouping, restated so the code and the plan cannot drift.
PLAN_TIERS = {
    "P0": {"molecules": ["DMC", "DEC", "SL"],
           "action": "四智能体一致性审核即可, 不需重复取数"},
    "P1": {"molecules": ["DME", "TEGDME", "GBL", "DMSO"],
           "action": "先完成 J04 来源重建与四智能体审核, 不得直接生成新候选行"},
    "P2": {"molecules": ["SN"],
           "action": "寻找 293.15-303.15 K 真实测量; 原 333.15 K 必须保留, 不得折算"},
    "P3": {"molecules": ["AN"],
           "action": "寻找符合 static 0 Hz 的测量; 已有 0.01/1 MHz 证据不能直接替代"},
    "P4": {"molecules": ["EMC", "EC", "PC", "FEC", "VC", "DOL", "EA", "MA", "TMP"],
           "action": "优先查找原始文献、公开数据库与已有 DOI; EA/MA 先核查 NBS514"},
}


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


def tier_for(name: str) -> str:
    n = (name or "").strip().upper()
    for tier, spec in PLAN_TIERS.items():
        if n in spec["molecules"]:
            return tier
    return "UNASSIGNED"


def main() -> int:
    for p in (PRIORITY_FILE, MEAS_LEDGER, PAIR_VALIDITY, GAP_AUDIT):
        if not p.is_file():
            print(f"FATAL: missing {p}", file=sys.stderr)
            return 2
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    priority = load(PRIORITY_FILE)
    ledger = load(MEAS_LEDGER)
    gap = load(GAP_AUDIT)

    # Index the ledger by molecule id (a_mol_id) and by inchikey.
    by_mol_id: dict[str, list[dict]] = defaultdict(list)
    for m in ledger:
        aid = (m.get("a_mol_id") or "").strip()
        if aid and aid.lower() not in PLACEHOLDERS:
            by_mol_id[aid].append(m)

    # Gap rows carry a_mol_id too; index them.
    gap_by_mol: dict[str, list[dict]] = defaultdict(list)
    for g in gap:
        aid = (g.get("a_mol_id") or "").strip()
        if aid and aid.lower() not in PLACEHOLDERS:
            gap_by_mol[aid].append(g)

    indep = None
    if INDEP.is_file():
        indep = json.loads(INDEP.read_text(encoding="utf-8"))
    entangled_docs = set()
    if indep:
        for pair in indep.get("entangled_document_pairs", []):
            entangled_docs.add(pair["doc_a"])
            entangled_docs.add(pair["doc_b"])

    # The v04 aggregate table carries a curated value for every A18 molecule,
    # including the nine whose ThermoML observation count is zero. Calling those
    # nine "ZERO_OBSERVATION" without qualification is misleading: the curated
    # value exists, it simply never passed through the ThermoML observation layer.
    # Reviewer 4 (B03) caught this. So we distinguish the two layers explicitly.
    V04 = REPO_ROOT / "data" / "dielectric_v04.csv"
    v04_by_name: dict[str, dict] = {}
    if V04.is_file():
        for x in load(V04):
            v04_by_name[(x.get("name") or "").strip().upper()] = x

    # The A18 register uses short codes (EA, MA, DMC...); v04 uses full chemical
    # names. Without this bridge the join silently misses every molecule -- which
    # is exactly the class of defect that made the earlier queue report blanks.
    A18_TO_V04_NAME = {
        "DMC": "DIMETHYL CARBONATE",
        "DEC": "DIETHYL CARBONATE",
        "SL": "SULFOLANE",
        "DME": "1,2-DIMETHOXYETHANE",
        "TEGDME": "TETRAGLYME",
        "GBL": "GAMMA-BUTYROLACTONE",
        "DMSO": "DIMETHYL SULFOXIDE",
        "SN": "SUCCINONITRILE",
        "AN": "ACETONITRILE",
        "EA": "ETHYL ACETATE",
        "MA": "METHYL ACETATE",
        "EMC": "ETHYL METHYL CARBONATE",
        "EC": "ETHYLENE CARBONATE",
        "PC": "PROPYLENE CARBONATE",
        "FEC": "FLUOROETHYLENE CARBONATE",
        "VC": "VINYLENE CARBONATE",
        "DOL": "1,3-DIOXOLANE",
        "TMP": "TRIMETHYL PHOSPHATE",
    }

    def _v04_row(short_name: str) -> dict:
        for key in (A18_TO_V04_NAME.get(short_name.upper(), short_name.upper()),
                    short_name.upper()):
            if key in v04_by_name:
                return v04_by_name[key]
        return {}

    rows: list[dict] = []
    for p in priority:
        aid = (p.get("a_mol_id") or "").strip()
        name = (p.get("a_name") or "").strip()
        tier = tier_for(name)

        mol_obs = by_mol_id.get(aid, [])
        n_obs = len(mol_obs)
        in_band = []
        for m in mol_obs:
            t = fnum(m.get("temperature_K"))
            if t is not None and BAND_LOW <= t <= BAND_HIGH:
                in_band.append(m)

        sources = sorted({(m.get("source_document_id") or "").strip()
                          for m in mol_obs
                          if (m.get("source_document_id") or "").strip()})
        # Independent-source count must be corrected for known duplicates.
        entangled = [s for s in sources if s in entangled_docs]

        static_hz = sum(1 for m in mol_obs
                        if (fnum(m.get("frequency_hz")) == 0))
        gap_rows = gap_by_mol.get(aid, [])
        pair_valid = sum(1 for g in gap_rows
                         if (g.get("pair_present_in_single_observation") or ""
                             ).strip().lower() == "true")

        # The curated v04 layer may hold a value even when the ThermoML
        # observation layer is empty. Record both so "zero observation" is never
        # read as "no data exists".
        v04_row = _v04_row(name)
        v04_has_value = bool((v04_row.get("dielectric") or "").strip())
        v04_eps = (v04_row.get("dielectric") or "").strip()
        v04_T = (v04_row.get("T_K") or "").strip()
        v04_doi = (v04_row.get("source_doi") or "").strip()
        v04_quality = (v04_row.get("source_quality") or "").strip()

        # What specifically blocks this molecule?
        blockers = []
        if n_obs == 0:
            # Distinguish "no observation in the ThermoML layer" from "no data".
            blockers.append(
                "ZERO_THERMOML_OBSERVATIONS" if v04_has_value
                else "ZERO_OBSERVATIONS")
        if n_obs == 0 and v04_has_value:
            blockers.append("CURATED_VALUE_NOT_IN_OBSERVATION_LAYER")
        if n_obs > 0 and not in_band:
            blockers.append("NO_ROOM_BAND_OBSERVATION")
        if n_obs > 0 and len(sources) == 0:
            blockers.append("NO_SOURCE_DOCUMENT")
        if n_obs > 0 and len(sources) == 1:
            blockers.append("SINGLE_SOURCE_ONLY")
        if entangled:
            blockers.append("SOURCE_DUPLICATION_ENTANGLED")
        if mol_obs and static_hz < n_obs:
            blockers.append("NON_STATIC_FREQUENCY_PRESENT")
        if gap_rows and pair_valid == 0:
            blockers.append("NO_CONDITION_VALID_PAIR")

        # The next concrete action, derived from the blocker set.
        if n_obs == 0 and v04_has_value:
            next_action = (
                f"v04 已有整理值 ε={v04_eps} @ {v04_T} K (DOI {v04_doi}); "
                f"但该值不在 ThermoML 观测层, 无 (T,ε) 配对证据. "
                f"需核实其原始测量并补入观测层, 而非重新检索"
            )
        elif n_obs == 0:
            next_action = (
                "检索原始文献/公开数据库/已有 DOI 寻找该分子的静态相对介电常数测量"
            )
        elif not in_band:
            next_action = (
                f"寻找 {BAND_LOW}-{BAND_HIGH} K 的真实测量; "
                f"现有观测最低温度 {min((fnum(m.get('temperature_K')) for m in mol_obs if fnum(m.get('temperature_K')) is not None), default='?')} K, "
                "**不得把高温观测折算成室温**"
            )
        elif len(sources) <= 1:
            next_action = "寻找第二个独立来源以支持来源聚类稳健性检验"
        else:
            next_action = "补充条件级证据并送四智能体审核"

        rows.append({
            "a_mol_id": aid,
            "a_name": name,
            "plan_b03_tier": tier,
            "plan_b03_action": PLAN_TIERS.get(tier, {}).get("action", ""),
            "priority_order": (p.get("priority_order") or "").strip(),
            "repo_backfill_tier": (p.get("backfill_tier") or "").strip(),
            "n_observations": n_obs,
            "n_room_band_observations": len(in_band),
            "n_static_zero_hz": static_hz,
            "n_source_documents": len(sources),
            "n_entangled_sources": len(entangled),
            "source_documents": ";".join(sources),
            "n_gap_rows": len(gap_rows),
            "n_condition_valid_pairs": pair_valid,
            "v04_curated_value_present": "true" if v04_has_value else "false",
            "v04_dielectric": v04_eps,
            "v04_T_K": v04_T,
            "v04_source_doi": v04_doi,
            "v04_source_quality": v04_quality,
            "frequency_status": (p.get("frequency_status") or "").strip(),
            "independent_source_status": (p.get("independent_source_status") or "").strip(),
            "blockers": ";".join(blockers) if blockers else "NONE_IDENTIFIED",
            "next_action": next_action,
            "evidence_status": (
                "NO_THERMOML_OBSERVATION_BUT_V04_VALUE" if (n_obs == 0 and v04_has_value)
                else "ZERO_OBSERVATION_NO_V04_VALUE" if n_obs == 0
                else "OBSERVED_NOT_ROOM_BAND" if not in_band
                else "ROOM_BAND_PRESENT"
            ),
            "gap_tier": (
                "P4_SOURCE_RETRIEVAL" if n_obs == 0 else
                "P2_ROOM_BAND_EVIDENCE" if not in_band else
                "P0_SIGNATURE_OR_REVIEW"
            ),
        })

    fields = ["a_mol_id", "a_name", "plan_b03_tier", "plan_b03_action",
              "priority_order", "repo_backfill_tier", "n_observations",
              "n_room_band_observations", "n_static_zero_hz",
              "n_source_documents", "n_entangled_sources", "source_documents",
              "n_gap_rows", "n_condition_valid_pairs",
              "v04_curated_value_present", "v04_dielectric", "v04_T_K",
              "v04_source_doi", "v04_source_quality", "frequency_status",
              "independent_source_status", "blockers", "next_action",
              "evidence_status", "gap_tier"]
    csv_path = OUT_DIR / "A18_gap_register.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})

    by_tier = Counter(r["plan_b03_tier"] for r in rows)
    by_status = Counter(r["evidence_status"] for r in rows)
    blocker_counts = Counter()
    for r in rows:
        for b in r["blockers"].split(";"):
            if b and b != "NONE_IDENTIFIED":
                blocker_counts[b] += 1

    doc = {
        "schema": "confirm_2027.a18_gap_register/v1",
        "generator": GENERATOR,
        "generated_at_utc": datetime.now(timezone.utc)
        .replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "declaration": (
            "本表只登记缺口与下一步动作, **不新增任何测量**. "
            "所有数字来自冻结证据层 (measurement_ledger_v1 / gap_aggregation_audit)."
        ),
        "inputs": {
            "a18_source_backfill_priority": {
                "sha256": sha256_file(PRIORITY_FILE), "rows": len(priority)},
            "measurement_ledger_v1": {
                "sha256": sha256_file(MEAS_LEDGER), "rows": len(ledger)},
            "gap_aggregation_audit": {
                "sha256": sha256_file(GAP_AUDIT), "rows": len(gap)},
        },
        "counts": {
            "n_molecules": len(rows),
            "by_plan_tier": dict(sorted(by_tier.items())),
            "by_evidence_status": dict(sorted(by_status.items())),
            "blocker_frequency": dict(sorted(blocker_counts.items(),
                                             key=lambda kv: -kv[1])),
            "n_zero_observation": sum(1 for r in rows if r["n_observations"] == 0),
            "n_no_room_band": sum(1 for r in rows
                                  if r["n_observations"] > 0
                                  and r["n_room_band_observations"] == 0),
        },
        "plan_b03_tiers": PLAN_TIERS,
        "critical_rules": [
            "SN 的 333.15 K 数据必须保留, 不得折算成室温",
            "AN 的 0.01/1 MHz 证据不能直接替代 static 0 Hz",
            "EA/MA 已有 NBS514 资料, 优先核查",
            "P1 分子必须先完成 J04 来源重建, 不得直接生成新候选行",
            "不得为了扩大样本数降低准入标准",
        ],
        "rows": rows,
        "output": {"path": str(csv_path.relative_to(REPO_ROOT)),
                   "sha256": sha256_file(csv_path), "rows": len(rows)},
    }
    json_path = OUT_DIR / "A18_gap_register.json"
    json_path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
                         encoding="utf-8")

    print(f"[B03-1] {csv_path}  ({len(rows)} molecules)")
    print(f"[B03-1] {json_path}")
    print(f"  by tier:   {dict(sorted(by_tier.items()))}")
    print(f"  by status: {dict(sorted(by_status.items()))}")
    print(f"  zero-observation molecules: {doc['counts']['n_zero_observation']}")
    print(f"  no room-band observations : {doc['counts']['n_no_room_band']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
