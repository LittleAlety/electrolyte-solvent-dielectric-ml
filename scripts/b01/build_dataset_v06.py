#!/usr/bin/env python
"""B01-10: build dataset v06 -- the repaired measurement-level dataset.

PLAN B asks for the high-pressure contamination and the synthetic-midpoint defect
to be *repaired*, not merely measured. The obstacle is that repairing them changes
which rows are eligible, which would silently move the reported counts
(460 / 78 / 170) and therefore violate the frozen-evidence rule.

The resolution is versioning, not mutation:

    v04 / J01 / J02 / J03        stay byte-identical, forever
    v05 (measurement ledger)     stays byte-identical
    v06 (this file)              a NEW dataset with the defects excluded

Every v06 row records *why* it is present and *which* v05 rows it replaced, so the
lineage is auditable and the old counts remain reproducible from the old files.

What v06 fixes:

  1. PRESSURE HETEROGENEITY
     An aggregate whose contributing observations span ambient and pressurised
     regimes is not one thermodynamic state. Such aggregates are excluded from
     the model-ready set and marked `PRESSURE_HETEROGENEOUS`. The ambient-only
     sub-median is recorded as an alternative, never silently substituted.

  2. SYNTHETIC MIDPOINTS
     An aggregate whose (T, eps) pair was built from independent medians is not a
     measurement. Excluded from model-ready, marked `SYNTHETIC_PAIR`.

  3. TEMPERATURE IMPUTATION
     An aggregate whose temperature was assumed rather than reported is flagged
     `TEMPERATURE_IMPUTED`. It is retained (the epsilon may still be real) but
     never counted as a same-temperature observation.

Nothing is deleted. Every excluded row stays in the file with its status, so a
reader can reconstruct both the old and the new denominator.

Output: outputs/b01/dataset_v06_manifest.json
        outputs/b01/dataset_v06_model_ready.csv
        outputs/b01/dataset_v06_exclusions.csv
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
OUT_DIR = REPO_ROOT / "outputs" / "b01"
CONFIRM = REPO_ROOT / "outputs" / "confirm_2027"
GENERATOR = "build_dataset_v06/1.0.0"

V04 = REPO_ROOT / "data" / "dielectric_v04.csv"
MEAS_LEDGER = CONFIRM / "provenance_repair" / "measurement_ledger_v1.csv"
PAIR_VALIDITY = CONFIRM / "provenance_repair" / "condition_pair_validity_v1.csv"
EXCEPTIONS = CONFIRM / "provenance_repair" / "reconstruction_exceptions.csv"
PRESSURE = OUT_DIR / "pressure_heterogeneity_audit.json"
TEMP_IMP = OUT_DIR / "temperature_imputation_audit.json"

BAND_LOW = 293.15
BAND_HIGH = 303.15
AMBIENT_KPA = 101.325
AMBIENT_TOL = 5.0

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
    for p in (V04, MEAS_LEDGER, PAIR_VALIDITY, EXCEPTIONS):
        if not p.is_file():
            print(f"FATAL: missing {p}", file=sys.stderr)
            return 2
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    v04 = load(V04)
    ledger = load(MEAS_LEDGER)
    pair = load(PAIR_VALIDITY)
    exc = load(EXCEPTIONS)

    # ---- index the supporting evidence ----
    pair_by_meas: dict[str, dict] = {}
    for p in pair:
        aid = (p.get("aggregate_id") or "").strip()
        if aid.startswith("v04row-"):
            pair_by_meas[f"EPSV04-R{aid[len('v04row-'):]}"] = p

    exc_by_agg = {(e.get("aggregate_id") or "").strip(): e for e in exc}

    pressure_by_agg: dict[str, dict] = {}
    if PRESSURE.is_file():
        pdoc = json.loads(PRESSURE.read_text(encoding="utf-8"))
        for c in pdoc.get("contaminated_aggregates", []):
            pressure_by_agg[c["aggregate_id"]] = c

    # ---- unresolved source conflicts ----
    # Reviewer 4 (B04-PRECONFLICT) found that v06 built its model-ready set
    # WITHOUT ever reading the conflict register: 56 conflicts were all still
    # UNRESOLVED, yet exactly the two that happened to touch model-ready
    # molecules leaked through, because nothing else disqualified them. That is
    # incidental, not designed, and it would recur for any conflicted molecule
    # lacking a different blocker. Wire it in explicitly.
    conflict_by_inchikey: dict[str, dict] = {}
    conflict_path = OUT_DIR / "measurement_conflict_register.csv"
    if conflict_path.is_file():
        for c in load(conflict_path):
            ik = (c.get("molecule_key") or "").strip()
            if not ik:
                continue
            # Keep the widest spread seen for this molecule.
            prev = conflict_by_inchikey.get(ik)
            try:
                spread = float(c.get("relative_spread_pct") or 0)
            except ValueError:
                spread = 0.0
            if prev is None or spread > prev["spread"]:
                conflict_by_inchikey[ik] = {
                    "conflict_id": (c.get("conflict_id") or "").strip(),
                    "spread": spread,
                    "temperature_K": (c.get("temperature_K") or "").strip(),
                    "epsilon_min": (c.get("epsilon_min") or "").strip(),
                    "epsilon_max": (c.get("epsilon_max") or "").strip(),
                    "n_distinct_sources": (c.get("n_distinct_sources") or "").strip(),
                }

    # ---- deduplicate contributing observations by experiment ----
    # Reviewer 2/4: two documents that report byte-identical values for the same
    # molecule at the same temperature are ONE experiment deposited twice. Counting
    # them as two inflates both n_contributing_measurements and -- for DMAc -- the
    # median itself (37.72 was duplicated, 38.67 was not, so the median was
    # dragged to the wrong side).
    dup_pairs: set[tuple[str, str]] = set()
    dup_groups_path = CONFIRM / "provenance_repair" / "duplicate_observation_groups.csv"
    if dup_groups_path.is_file():
        for d in load(dup_groups_path):
            docs = [x.strip() for x in (d.get("documents") or "").split(";") if x.strip()]
            for i in range(len(docs)):
                for j in range(i + 1, len(docs)):
                    dup_pairs.add(tuple(sorted((docs[i], docs[j]))))

    def _dedupe_members(members: list[dict]) -> int:
        """Count distinct experiments among an aggregate's contributing rows."""
        if not members:
            return 0
        # Union-find over documents that are the same experiment.
        parent: dict[str, str] = {}

        def find(x: str) -> str:
            parent.setdefault(x, x)
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a: str, b: str) -> None:
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[rb] = ra

        for m in members:
            find((m.get("source_document_id") or "").strip())
        for a, b in dup_pairs:
            union(a, b)
        return len({find((m.get("source_document_id") or "").strip())
                    for m in members})

    # ---- four-agent conflict adjudication ----
    # Reviewers passed butan-2-ol 4/4 but held DMAc 4/4. The distinction matters:
    # a "conflict" whose competing values agree within their own stated
    # uncertainties is not a conflict (butan-2-ol's divergent leg carries
    # U=+/-1.90 = 10.8%, an interval that CONTAINS the other value). A conflict
    # with disjoint intervals is real (DMAc). Read the adjudication so v06
    # respects that verdict instead of treating "any conflict" as disqualifying.
    adj_dir = REPO_ROOT / "outputs" / "b01" / "conflict_adjudication"
    adjudicated: dict[str, dict] = {}
    for fname in ("reviewer_1_decisions.csv", "reviewer_2_decisions.csv",
                  "reviewer_3_decisions.csv", "reviewer_4_decisions.csv"):
        p = adj_dir / fname
        if not p.is_file():
            continue
        for r in load(p):
            cid = (r.get("conflict_id") or "").strip()
            if not cid or cid == "ALL":
                continue
            d = (r.get("decision") or "").strip().upper()
            slot = adjudicated.setdefault(
                cid, {"pass": 0, "hold": 0, "fail": 0, "resolutions": []})
            if d == "PASS":
                slot["pass"] += 1
            elif d == "HOLD":
                slot["hold"] += 1
            elif d == "FAIL":
                slot["fail"] += 1
            res = (r.get("recommended_resolution") or "").strip()
            if res:
                slot["resolutions"].append(res)

    verdict_by_inchikey: dict[str, dict] = {}
    for cid, slot in adjudicated.items():
        for ik, c in conflict_by_inchikey.items():
            if c["conflict_id"] == cid:
                unanimous_pass = (slot["pass"] == 4 and slot["fail"] == 0
                                  and slot["hold"] == 0)
                verdict_by_inchikey[ik] = {
                    "conflict_id": cid,
                    "pass": slot["pass"], "hold": slot["hold"],
                    "fail": slot["fail"],
                    "verdict": ("RESOLVED_PASS" if unanimous_pass
                                else "UNRESOLVED_HOLD"),
                    "resolutions": sorted(set(slot["resolutions"])),
                }
                break

    # Temperature imputation is a per-row property of v04 itself.
    imputed_names = set()
    if TEMP_IMP.is_file():
        tdoc = json.loads(TEMP_IMP.read_text(encoding="utf-8"))
        imputed_names = {r["measurement_id"] for r in tdoc.get("imputed_rows", [])}

    by_agg: dict[str, list[dict]] = defaultdict(list)
    for m in ledger:
        a = (m.get("aggregate_id") or "").strip()
        if a and a.lower() not in PLACEHOLDERS:
            by_agg[a].append(m)

    model_ready: list[dict] = []
    exclusions: list[dict] = []

    for i, row in enumerate(v04, 1):
        agg_id = f"v04row-{i:03d}"
        mid = f"EPSV04-R{i:03d}"
        name = (row.get("name") or "").strip()
        eps = (row.get("dielectric") or "").strip()
        t_k = (row.get("T_K") or "").strip()
        t_val = fnum(t_k)

        pv = pair_by_meas.get(mid, {})
        pair_valid = (pv.get("condition_pair_valid") or "").strip().lower()
        e = exc_by_agg.get(agg_id, {})
        exc_class = (e.get("exception_class") or "").strip()

        members = by_agg.get(agg_id, [])

        # ---- classify the row ----
        flags: list[str] = []
        excl_reason = ""

        # (0) source conflict -- only blocks when adjudication did NOT resolve it
        inchikey = (row.get("inchikey") or "").strip()
        conflict = conflict_by_inchikey.get(inchikey)
        verdict = verdict_by_inchikey.get(inchikey)
        n_independent = _dedupe_members(members) if members else 0
        conflict_blocks = bool(conflict) and (
            verdict is None or verdict["verdict"] != "RESOLVED_PASS")
        if conflict:
            state = (verdict["verdict"] if verdict else "NOT_ADJUDICATED")
            flags.append(f"CONFLICT_{state}({conflict['spread']:.2f}%)")
            if conflict_blocks:
                excl_reason = "CONFLICT_UNRESOLVED"

        # (1) pressure heterogeneity
        press = pressure_by_agg.get(agg_id)
        if press:
            flags.append(f"PRESSURE_{press['class']}")
            if press["class"] in ("MIXED_AMBIENT_AND_PRESSURISED",
                                  "PRESSURISED_ONLY"):
                excl_reason = "PRESSURE_HETEROGENEOUS"

        # (2) synthetic pair
        if pair_valid == "false" and exc_class == "SYNTHETIC_PAIR_FROM_INDEPENDENT_MEDIAN":
            flags.append("SYNTHETIC_PAIR")
            excl_reason = excl_reason or "SYNTHETIC_PAIR"

        # (3) no contributing measurement at all
        if exc_class == "NO_CONTRIBUTING_MEASUREMENT":
            flags.append("NO_CONTRIBUTING_MEASUREMENT")
            excl_reason = excl_reason or "NO_CONTRIBUTING_MEASUREMENT"

        # (4) temperature imputed
        if mid in imputed_names:
            flags.append("TEMPERATURE_IMPUTED")

        # (5) outside the room-temperature band
        if t_val is None or not (BAND_LOW <= t_val <= BAND_HIGH):
            flags.append("OUTSIDE_ROOM_BAND")

        # ---- decide model readiness ----
        # A row is model-ready only if it has a real measurement pair, sits in the
        # room band, has a reported (not imputed) temperature, and is not
        # pressure-heterogeneous.
        blocking = []
        if excl_reason:
            blocking.append(excl_reason)
        if pair_valid != "true":
            blocking.append("PAIR_NOT_VALID")
        if mid in imputed_names:
            blocking.append("TEMPERATURE_IMPUTED")
        if t_val is None or not (BAND_LOW <= t_val <= BAND_HIGH):
            blocking.append("OUTSIDE_ROOM_BAND")
        if not members and exc_class == "NO_CONTRIBUTING_MEASUREMENT":
            blocking.append("NO_CONTRIBUTING_MEASUREMENT")
        if conflict_blocks and "CONFLICT_UNRESOLVED" not in blocking:
            blocking.append("CONFLICT_UNRESOLVED")

        # De-duplicate while preserving order: the same reason arriving via
        # excl_reason and via an explicit check must appear once.
        seen_reasons: set[str] = set()
        blocking = [b for b in blocking
                    if not (b in seen_reasons or seen_reasons.add(b))]

        ready = not blocking

        record = {
            "aggregate_id": agg_id,
            "measurement_id": mid,
            "inchikey": (row.get("inchikey") or "").strip(),
            "name": name,
            "T_K": t_k,
            "dielectric": eps,
            "source_doi": (row.get("source_doi") or "").strip(),
            "source_quality": (row.get("source_quality") or "").strip(),
            "temperature_source": (row.get("temperature_source") or "").strip(),
            "n_contributing_measurements": len(members),
            "n_independent_experiments": n_independent,
            "conflict_spread_pct": (
                f"{conflict['spread']:.2f}" if conflict else ""),
            "condition_pair_valid": pair_valid,
            "exception_class": exc_class,
            "pressure_class": press["class"] if press else "",
            "p_min_kpa": press["p_min_kpa"] if press else "",
            "p_max_kpa": press["p_max_kpa"] if press else "",
            "flags": ";".join(flags) if flags else "NONE",
            "model_ready": "true" if ready else "false",
            "blocking_reasons": ";".join(blocking) if blocking else "",
        }

        if ready:
            model_ready.append(record)
        else:
            exclusions.append(record)

    # ---- write model-ready set ----
    ready_fields = ["aggregate_id", "measurement_id", "inchikey", "name", "T_K",
                    "dielectric", "source_doi", "source_quality",
                    "temperature_source", "n_contributing_measurements",
                    "n_independent_experiments", "conflict_spread_pct",
                    "condition_pair_valid", "pressure_class", "flags",
                    "model_ready", "blocking_reasons"]
    ready_path = OUT_DIR / "dataset_v06_model_ready.csv"
    with ready_path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=ready_fields)
        w.writeheader()
        for r in model_ready:
            w.writerow({k: r.get(k, "") for k in ready_fields})

    # ---- write exclusion register ----
    excl_fields = ["aggregate_id", "measurement_id", "inchikey", "name", "T_K",
                   "dielectric", "source_doi", "exception_class",
                   "pressure_class", "p_min_kpa", "p_max_kpa",
                   "n_contributing_measurements", "n_independent_experiments",
                   "conflict_spread_pct", "flags", "blocking_reasons"]
    excl_path = OUT_DIR / "dataset_v06_exclusions.csv"
    with excl_path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=excl_fields)
        w.writeheader()
        for r in exclusions:
            w.writerow({k: r.get(k, "") for k in excl_fields})

    # ---- accounting ----
    blocker_counts = Counter()
    for r in exclusions:
        for b in (r["blocking_reasons"] or "").split(";"):
            if b:
                blocker_counts[b] += 1

    old_valid = sum(1 for p in pair
                    if (p.get("condition_pair_valid") or "").strip().lower() == "true")
    new_ready = len(model_ready)

    doc = {
        "schema": "b01.dataset_v06/v1",
        "generator": GENERATOR,
        "generated_at_utc": datetime.now(timezone.utc)
        .replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "declaration": (
            "v06 是**新版本**, 不修改 v04/v05/J01/J02/J03 的任何字节. "
            "被排除的行仍保留在 exclusions.csv 中, 因此旧分母可完整复现."
        ),
        "inputs": {
            "dielectric_v04": {"sha256": sha256_file(V04), "rows": len(v04)},
            "measurement_ledger_v1": {"sha256": sha256_file(MEAS_LEDGER),
                                      "rows": len(ledger)},
            "condition_pair_validity_v1": {"sha256": sha256_file(PAIR_VALIDITY),
                                           "rows": len(pair)},
            "reconstruction_exceptions": {"sha256": sha256_file(EXCEPTIONS),
                                          "rows": len(exc)},
        },
        "repairs_applied": {
            "pressure_heterogeneity": (
                "贡献观测跨越常压与加压两种状态的聚合行被排除出 model_ready, "
                "标记 PRESSURE_HETEROGENEOUS. 不做静默替换."
            ),
            "synthetic_midpoints": (
                "由两个独立中位数拼成的 (T,ε) 对不是测量, 排除并标记 SYNTHETIC_PAIR."
            ),
            "temperature_imputation": (
                "温度为推定值的行保留 (ε 可能仍真实), 但标记 TEMPERATURE_IMPUTED, "
                "不得作为同温证据使用."
            ),
            "unresolved_source_conflicts": (
                "v06 现在**读取**冲突登记表与四智能体裁决. "
                "未解决冲突 (CONFLICT_UNRESOLVED) 排除出 model_ready; "
                "已由 4/4 PASS 裁决为可接受的冲突保留 (CONFLICT_RESOLVED_PASS). "
                "早期版本完全没读该登记表, 导致冲突行靠『恰好没有别的阻断理由』泄漏."
            ),
            "duplicate_experiment_dedup": (
                "同一实验被两篇论文重复报告时, 贡献来源计数与中位数都会被高估. "
                "v06 用并查集在 (molecule, T) 层面合并逐字节相同的文档, "
                "输出 n_independent_experiments."
            ),
        },
        "conflict_adjudication": {
            ik: v for ik, v in verdict_by_inchikey.items()
        },
        "counts": {
            "n_v04_rows": len(v04),
            "n_model_ready_v06": new_ready,
            "n_excluded_v06": len(exclusions),
            "n_pair_valid_v05": old_valid,
            "delta_vs_v05_pair_valid": new_ready - old_valid,
            "exclusions_by_reason": dict(sorted(blocker_counts.items(),
                                                key=lambda kv: -kv[1])),
        },
        "denominator_note": (
            f"v05 的 pair_valid 计数是 {old_valid}; v06 的 model_ready 是 {new_ready}. "
            f"两者**不是**同一口径: v05 只判 (T,ε) 是否同源, "
            f"v06 额外要求温度非推定且压力同质. 差额 {old_valid - new_ready} 行全部列在 "
            f"exclusions.csv, 可逐行追溯."
        ),
        "lineage": {
            "supersedes": "none -- v06 与 v04/v05 并列, 不替代",
            "v04_unchanged": True,
            "v05_unchanged": True,
            "frozen_artifacts_unchanged": True,
        },
        "outputs": {
            "model_ready": {"path": str(ready_path.relative_to(REPO_ROOT)),
                            "sha256": sha256_file(ready_path),
                            "rows": new_ready},
            "exclusions": {"path": str(excl_path.relative_to(REPO_ROOT)),
                           "sha256": sha256_file(excl_path),
                           "rows": len(exclusions)},
        },
    }
    man_path = OUT_DIR / "dataset_v06_manifest.json"
    man_path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")

    print(f"[B01-10] {ready_path}  ({new_ready} model-ready)")
    print(f"[B01-10] {excl_path}  ({len(exclusions)} excluded)")
    print(f"[B01-10] {man_path}")
    print(f"  v04 rows          = {len(v04)}")
    print(f"  v05 pair_valid    = {old_valid}")
    print(f"  v06 model_ready   = {new_ready}  (delta {new_ready - old_valid:+d})")
    for k, v in sorted(blocker_counts.items(), key=lambda kv: -kv[1]):
        print(f"    {k:36s} {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
