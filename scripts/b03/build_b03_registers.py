#!/usr/bin/env python
"""B03-3: assemble the remaining B03 registers from frozen evidence.

Builds three of PLAN B B03's deliverables:

  literature_source_inventory.csv  -- every source document that bears on the A18 set
  independent_source_map.csv       -- which sources are provably duplicated
  unresolved_molecules.csv         -- molecules with no admissible evidence, and why

None of these invent evidence. The literature inventory describes sources the
repository already holds; it does not claim a search was performed. That
distinction matters: a "literature inventory" that silently mixes "documents I
read" with "documents that exist somewhere" is a fabricated bibliography.

`unresolved_molecules.csv` is the honest negative ledger: for each molecule that
still has no admissible measurement, it states the specific reason and the
specific next action. A molecule that cannot be resolved must appear here rather
than quietly disappear from the A18 set.

Output: outputs/confirm_2027/evidence_backfill/literature_source_inventory.csv
        outputs/confirm_2027/evidence_backfill/independent_source_map.csv
        outputs/confirm_2027/evidence_backfill/unresolved_molecules.csv
        outputs/confirm_2027/evidence_backfill/b03_registers.json
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
GENERATOR = "build_b03_registers/1.0.0"

GAP_REGISTER = OUT_DIR / "A18_gap_register.csv"
SOURCE_VERIF = OUT_DIR / "source_verification.csv"
MEAS_LEDGER = CONFIRM / "provenance_repair" / "measurement_ledger_v1.csv"
SOURCE_REGISTRY = CONFIRM / "provenance_repair" / "source_document_registry_v1.csv"
INDEP_REPORT = CONFIRM / "provenance_repair" / "source_independence_report.json"
COVERAGE_REG = CONFIRM / "identity_and_coverage" / "coverage_gap_registry.csv"

PLACEHOLDERS = {"", "not_evaluated", "nan", "none", "null", "na", "n/a"}

# NBS514 uses common names; map to the A18 register's short names.
NAME_MAP = {
    "METHYL ACETATE": "MA",
    "ETHYL ACETATE": "EA",
    "DIMETHYL CARBONATE": "DMC",
    "DIETHYL CARBONATE": "DEC",
    "PROPYLENE CARBONATE": "PC",
    "ETHYLENE CARBONATE": "EC",
    "ACETONITRILE": "AN",
    "GAMMA-BUTYROLACTONE": "GBL",
    "SULFOLANE": "SL",
    "1,3-DIOXOLANE": "DOL",
    "DIMETHYL SULFOXIDE": "DMSO",
    "1,2-DIMETHOXYETHANE": "DME",
    "TETRAHYDROFURAN": "THF",
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


def _v04_lookup(short_name: str) -> dict:
    """Look up a molecule's curated v04 row by short code.

    NAME_MAP maps NBS full names -> short codes, so invert it here. Matching on
    `startswith(short_name)` would be wrong ("EA" is not a prefix of any name).
    """
    v04_path = REPO_ROOT / "data" / "dielectric_v04.csv"
    if not v04_path.is_file():
        return {}
    target = None
    for full, short in NAME_MAP.items():
        if short.upper() == short_name.upper():
            target = full
            break
    if target is None:
        return {}
    for x in load(v04_path):
        if (x.get("name") or "").strip().upper() == target:
            return x
    return {}


def main() -> int:
    for p in (GAP_REGISTER, MEAS_LEDGER, SOURCE_REGISTRY):
        if not p.is_file():
            print(f"FATAL: missing {p}", file=sys.stderr)
            return 2
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    gap = load(GAP_REGISTER)
    ledger = load(MEAS_LEDGER)
    registry = {r["source_document_id"]: r for r in load(SOURCE_REGISTRY)}
    source_verif = load(SOURCE_VERIF) if SOURCE_VERIF.is_file() else []

    indep = None
    if INDEP_REPORT.is_file():
        indep = json.loads(INDEP_REPORT.read_text(encoding="utf-8"))
    entangled_pairs = {}
    if indep:
        for p in indep.get("entangled_document_pairs", []):
            entangled_pairs[(p["doc_a"], p["doc_b"])] = p["n_identical_observations"]

    coverage = load(COVERAGE_REG) if COVERAGE_REG.is_file() else []
    cov_by_mol: dict[str, list[dict]] = defaultdict(list)
    for c in coverage:
        aid = (c.get("a_mol_id") or "").strip()
        if aid and aid.lower() not in PLACEHOLDERS:
            cov_by_mol[aid].append(c)

    # ---------------------------------------------------------------- inventory
    # Which source documents touch the A18 molecules, and with how many rows?
    a18_ids = {(r["a_mol_id"] or "").strip() for r in gap}
    doc_to_mols: dict[str, set[str]] = defaultdict(set)
    doc_to_rows: Counter = Counter()
    for m in ledger:
        aid = (m.get("a_mol_id") or "").strip()
        doc = (m.get("source_document_id") or "").strip()
        if not doc or doc.lower() in PLACEHOLDERS:
            continue
        doc_to_rows[doc] += 1
        if aid in a18_ids:
            doc_to_mols[doc].add(aid)

    inv_rows = []
    for doc, mols in sorted(doc_to_mols.items()):
        reg = registry.get(doc, {})
        inv_rows.append({
            "source_document_id": doc,
            "n_a18_molecules_covered": len(mols),
            "a18_molecules": ";".join(sorted(mols)),
            "n_total_ledger_rows": doc_to_rows.get(doc, 0),
            "source_file": (reg.get("source_file") or "").strip(),
            "source_file_sha256": (reg.get("source_file_sha256") or "").strip(),
            "document_identity_verified": (reg.get("document_identity_verified") or "").strip(),
            "experimental_independence_status": (
                reg.get("experimental_independence_status") or "").strip(),
            "ingestion_path": "THERMOML_XML",
            "holds_source_bytes": "true" if reg else "false",
            "evidence_grade": (
                "DOCUMENTED" if reg.get("source_file_sha256") else "INFERRED"),
            "inventory_scope_note": (
                "本行描述仓库**已持有**的源文档; 不代表已完成穷尽式文献检索"
            ),
        })

    # Add the NBS514 source (not in the ThermoML registry).
    nbs_verified = [r for r in source_verif
                    if r.get("verification_status") == "VERIFIED_AGAINST_PAGE_READ"]
    if nbs_verified:
        inv_rows.append({
            "source_document_id": "10.6028/nbs.circ.514",
            "n_a18_molecules_covered": len(nbs_verified),
            "a18_molecules": ";".join(sorted(r["a_name"] for r in nbs_verified)),
            "n_total_ledger_rows": 0,
            "source_file": "data/raw/nbs514/nbscircular514.pdf",
            "source_file_sha256": sha256_file(
                REPO_ROOT / "data" / "raw" / "nbs514" / "nbscircular514.pdf")
            if (REPO_ROOT / "data" / "raw" / "nbs514" / "nbscircular514.pdf").is_file()
            else "",
            "document_identity_verified": "true",
            "experimental_independence_status": "not_evaluated",
            "ingestion_path": "NBS514_CIRCULAR_MANUAL_ENTRY",
            "holds_source_bytes": "true",
            "evidence_grade": "DOCUMENTED",
            "inventory_scope_note": (
                "页面读取, 不在 measurement_ledger 内 (账本口径为 ThermoML)"
            ),
        })

    ifields = ["source_document_id", "n_a18_molecules_covered", "a18_molecules",
               "n_total_ledger_rows", "source_file", "source_file_sha256",
               "document_identity_verified", "experimental_independence_status",
               "ingestion_path", "holds_source_bytes", "evidence_grade",
               "inventory_scope_note"]
    ipath = OUT_DIR / "literature_source_inventory.csv"
    with ipath.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=ifields)
        w.writeheader()
        for r in inv_rows:
            w.writerow({k: r.get(k, "") for k in ifields})

    # ------------------------------------------------------- independence map
    map_rows = []
    for (a, b), n in sorted(entangled_pairs.items()):
        a_mols = sorted(doc_to_mols.get(a, set()))
        b_mols = sorted(doc_to_mols.get(b, set()))
        map_rows.append({
            "document_a": a,
            "document_b": b,
            "n_identical_observations": n,
            "shared_a18_molecules": ";".join(sorted(set(a_mols) & set(b_mols))),
            "independence_verdict": "NOT_INDEPENDENT",
            "basis": (
                f"{n} 条 (inchikey, T, ε) 全精度相同的观测 —— "
                f"两次独立测量不可能如此; 判定为重复转录/共享数据集"
            ),
            "consequence": (
                "这两个文档不得在同一次来源聚类检验中当作两个独立来源; "
                "n_contributing_sources 会因此高估独立实验数"
            ),
            "verified_by": "b01/validate_source_independence.py (独立实现)",
        })

    # ---- NBS514 shared-citation independence (Reviewer 2, B03) ----
    # EA and MA both cite NBS514 ref 63 (Williams & Krchma, JACS 49, 1676, 1927),
    # so they descend from ONE upstream measurement campaign. Treating them as two
    # independent sources would inflate n_contributing_sources by one. The earlier
    # version of this file had zero NBS514 rows because NBS514 is not in the
    # ThermoML source registry -- the independence check was skipped for exactly
    # the two rows that needed it.
    nbs_refs: dict[str, list[str]] = {}
    for part in [REPO_ROOT / "data" / "interim" / f"nbs514_organic_part{i}.csv"
                 for i in range(1, 5)]:
        if not part.is_file():
            continue
        for x in load(part):
            short = NAME_MAP.get((x.get("compound_name") or "").strip().upper())
            if not short:
                continue
            refs = [t.strip() for t in (x.get("references") or "").split(",")
                    if t.strip()]
            if refs:
                nbs_refs.setdefault(short, refs)

    # Which reference numbers are shared by more than one A18 molecule?
    ref_to_mols: dict[str, list[str]] = defaultdict(list)
    for short, refs in nbs_refs.items():
        for r in refs:
            ref_to_mols[r].append(short)
    shared_refs = {r: sorted(m) for r, m in ref_to_mols.items() if len(set(m)) > 1}

    for ref, mols in sorted(shared_refs.items()):
        map_rows.append({
            "document_a": "10.6028/nbs.circ.514",
            "document_b": "10.6028/nbs.circ.514",
            "n_identical_observations": 0,
            "shared_a18_molecules": ";".join(mols),
            "independence_verdict": "NOT_INDEPENDENT_SHARED_PRIMARY_CITATION",
            "basis": (
                f"NBS Circular 514 参考文献 #{ref} 同时被 {', '.join(mols)} 引用 —— "
                f"两者源自同一次上游测量活动, 不是两次独立实验"
            ),
            "consequence": (
                "不得把 EA 与 MA 当作两个独立来源; "
                "若两者同时进入 B04, n_contributing_sources 会多算 1. "
                "应合并为一个以 ref "
                f"{ref} 为根的来源簇"
            ),
            "verified_by": (
                "b03 Reviewer 2 (逐条读取 NBS514 转录的 references 列)"
            ),
        })

    mfields = ["document_a", "document_b", "n_identical_observations",
               "shared_a18_molecules", "independence_verdict", "basis",
               "consequence", "verified_by"]
    mpath = OUT_DIR / "independent_source_map.csv"
    with mpath.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=mfields)
        w.writeheader()
        for r in map_rows:
            w.writerow({k: r.get(k, "") for k in mfields})

    # ---- Cross-source conflicts for the backfilled molecules ----
    # Reviewer 4 (B03) found that MA and EA have conflicting values in a CC BY 4.0
    # source the repository already holds (data/raw/open_data_eps). Those values
    # were never reconciled against the NBS514 ones. Recording the conflict is the
    # point: B03 must not present a single "verified" value while a held source
    # says something materially different.
    OPEN_EPS = REPO_ROOT / "data" / "raw" / "open_data_eps" / "eps_observations.csv"
    open_eps_by_key: dict[str, list[dict]] = defaultdict(list)
    if OPEN_EPS.is_file():
        for x in load(OPEN_EPS):
            ik = (x.get("inchikey") or "").strip()
            if ik:
                open_eps_by_key[ik].append(x)

    A18_INCHIKEY = {
        "MA": "KXKVLQRXCPHEJC-UHFFFAOYSA-N",
        "EA": "XEKOWRVHYACXOJ-UHFFFAOYSA-N",
    }
    cross_conflicts: list[dict] = []
    for short, ik in sorted(A18_INCHIKEY.items()):
        held = open_eps_by_key.get(ik, [])
        if not held:
            continue
        v04 = _v04_lookup(short)
        v04_eps = (v04.get("dielectric") or "").strip()
        v04_t = (v04.get("T_K") or "").strip()
        if not v04_eps:
            continue
        for h in held:
            h_eps = (h.get("epsilon") or "").strip()
            h_t = (h.get("t_k") or "").strip()
            try:
                rel = abs(float(h_eps) - float(v04_eps)) / float(v04_eps)
            except (TypeError, ValueError):
                continue
            if rel <= 0.02:
                continue
            cross_conflicts.append({
                "a_mol_id": "",
                "a_name": short,
                "inchikey": ik,
                "nbs514_value": v04_eps,
                "nbs514_temperature_K": v04_t,
                "held_source_value": h_eps,
                "held_source_temperature_K": h_t,
                "held_source_url": (h.get("source_url") or "").strip(),
                "held_source_license": (h.get("license") or "").strip(),
                "held_source_sha256": (h.get("source_sha256") or "").strip(),
                "relative_difference_pct": f"{rel*100:.2f}",
                "conflict_status": "UNRESOLVED",
                "assessment": (
                    "差值过大, 无法用 10 K 温差解释 "
                    "(酯类 dε/dT 约 -0.15~-0.2 %/K). "
                    "两者不能同时是正确的静态值."
                    if h_t and abs(float(h_t) - float(v04_t or 0)) > 1.0 else
                    "温度缺失或相同, 差值超出测量不确定度"
                ),
                "required_action": (
                    "B04 前必须裁决: 或回原始文献确认, 或两者并列保留并标记不确定. "
                    "不得择一作为主值而不说明"
                ),
            })

    if cross_conflicts:
        cfields = ["a_mol_id", "a_name", "inchikey", "nbs514_value",
                   "nbs514_temperature_K", "held_source_value",
                   "held_source_temperature_K", "held_source_url",
                   "held_source_license", "held_source_sha256",
                   "relative_difference_pct", "conflict_status", "assessment",
                   "required_action"]
        cpath = OUT_DIR / "cross_source_conflicts.csv"
        with cpath.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=cfields)
            w.writeheader()
            for r in cross_conflicts:
                w.writerow({k: r.get(k, "") for k in cfields})

    # ---------------------------------------------------- unresolved molecules
    unresolved = []
    for r in gap:
        aid = r["a_mol_id"]
        n_obs = int(r["n_observations"] or 0)
        n_band = int(r["n_room_band_observations"] or 0)
        n_valid = int(r["n_condition_valid_pairs"] or 0)
        nbs_ok = any(v.get("a_mol_id") == aid
                     and v.get("verification_status") == "VERIFIED_AGAINST_PAGE_READ"
                     for v in source_verif)

        # A molecule is resolved only if it has a condition-valid pair OR a
        # verified page read that a review has accepted. Nothing has been
        # accepted yet, so the bar here is "evidence exists", not "admitted".
        if n_valid > 0 or nbs_ok:
            continue

        if n_obs == 0 and not nbs_ok:
            reason = "NO_OBSERVATION_AND_NO_PAGE_READ"
            action = ("检索原始文献/公开数据库; 该分子在 ThermoML 与 NBS514 中均无覆盖"
                      if aid not in ("C11", "C12") else
                      "该分子有 NBS514 页面读取但核实未通过, 需回原文核对")
        elif n_band == 0:
            reason = "NO_ROOM_BAND_OBSERVATION"
            action = "寻找 293.15-303.15 K 的真实测量; 不得折算高温数据"
        else:
            reason = "NO_CONDITION_VALID_PAIR"
            action = "有室温观测但 (T,ε) 不来自同一次测量; 需按 measurement_id 逐条取用"

        unresolved.append({
            "a_mol_id": aid,
            "a_name": r["a_name"],
            "plan_b03_tier": r["plan_b03_tier"],
            "n_observations": n_obs,
            "n_room_band_observations": n_band,
            "n_condition_valid_pairs": n_valid,
            "nbs514_page_read_verified": "true" if nbs_ok else "false",
            "unresolved_reason": reason,
            "blockers": r["blockers"],
            "next_action": action,
            "resolution_status": "UNRESOLVED",
            "may_enter_b04": "false",
        })

    ufields = ["a_mol_id", "a_name", "plan_b03_tier", "n_observations",
               "n_room_band_observations", "n_condition_valid_pairs",
               "nbs514_page_read_verified", "unresolved_reason", "blockers",
               "next_action", "resolution_status", "may_enter_b04"]
    upath = OUT_DIR / "unresolved_molecules.csv"
    with upath.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=ufields)
        w.writeheader()
        for r in unresolved:
            w.writerow({k: r.get(k, "") for k in ufields})

    by_reason = Counter(r["unresolved_reason"] for r in unresolved)

    doc = {
        "schema": "confirm_2027.b03_registers/v1",
        "generator": GENERATOR,
        "generated_at_utc": datetime.now(timezone.utc)
        .replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "declaration": (
            "本模块只整理仓库**已持有**的证据关系, 不声称已完成穷尽式文献检索. "
            "literature_source_inventory 描述的是现有源文档, 不是检索结果清单."
        ),
        "inputs": {
            "A18_gap_register": {"sha256": sha256_file(GAP_REGISTER)},
            "measurement_ledger_v1": {"sha256": sha256_file(MEAS_LEDGER),
                                      "rows": len(ledger)},
            "source_document_registry_v1": {"sha256": sha256_file(SOURCE_REGISTRY),
                                            "rows": len(registry)},
        },
        "counts": {
            "n_sources_covering_a18": len(inv_rows),
            "n_entangled_pairs": len(map_rows),
            "n_unresolved_molecules": len(unresolved),
            "unresolved_by_reason": dict(sorted(by_reason.items())),
            "n_a18_total": len(gap),
            "n_a18_with_evidence": len(gap) - len(unresolved),
        },
        "independence_finding": (
            f"{len(map_rows)} 对文档被证明共享全精度相同的观测, 因此"
            f"「独立来源数」在本数据集中是一个**上界**, 不是实测值. "
            f"B07 的来源聚类检验必须先按文档去重."
        ),
        "unresolved_finding": (
            f"{len(unresolved)}/{len(gap)} 个 A18 分子仍无可用的条件级证据. "
            f"这些分子必须留在未解决清单里, 不得为了凑数进入 B04."
        ),
        "outputs": {
            "literature_source_inventory": {
                "path": str(ipath.relative_to(REPO_ROOT)),
                "sha256": sha256_file(ipath), "rows": len(inv_rows)},
            "independent_source_map": {
                "path": str(mpath.relative_to(REPO_ROOT)),
                "sha256": sha256_file(mpath), "rows": len(map_rows)},
            "unresolved_molecules": {
                "path": str(upath.relative_to(REPO_ROOT)),
                "sha256": sha256_file(upath), "rows": len(unresolved)},
        },
    }
    json_path = OUT_DIR / "b03_registers.json"
    json_path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
                         encoding="utf-8")

    print(f"[B03-3] {ipath}  ({len(inv_rows)} sources)")
    print(f"[B03-3] {mpath}  ({len(map_rows)} entangled pairs)")
    print(f"[B03-3] {upath}  ({len(unresolved)} unresolved)")
    print(f"[B03-3] {json_path}")
    print(f"  A18 with evidence   = {len(gap) - len(unresolved)}/{len(gap)}")
    for k, v in sorted(by_reason.items()):
        print(f"    {k:36s} {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
