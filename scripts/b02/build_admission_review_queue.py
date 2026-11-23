#!/usr/bin/env python
"""B02-1: build the admission review queue from the frozen evidence.

This assembles *what will be reviewed*. It does not review anything and it emits
no admission verdict. That separation is deliberate: the queue must be frozen
and hashed before any reviewer sees it, otherwise a reviewer could be shown a
different input than the one recorded.

Queue membership (PLAN B B02):
  * the R007 40-row worksheet rows (the canonical admission targets)
  * DMC / DEC / SL  (P0)
  * DME / TEGDME / GBL / DMSO  (P1)
  * the 22 COMPOSITE_CONDITION_UNMATCHED rows, which B01 says must enter an
    independent review queue

Every queued item carries the evidence a reviewer needs to judge it, plus the
sha256 of each input file, so the review is bound to exact bytes.

Output: outputs/admission_v2/admission_review_queue.csv
        outputs/admission_v2/admission_review_queue_manifest.json
"""

from __future__ import annotations

import csv
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = REPO_ROOT / "outputs" / "admission_v2"
CONFIRM = REPO_ROOT / "outputs" / "confirm_2027"
STANDALONE = REPO_ROOT.parent / "v56_standalone"
GENERATOR = "build_admission_review_queue/1.0.0"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


# P0/P1 molecule groups the plan names explicitly.
PRIORITY_GROUPS = {
    "DMC": "P0", "DEC": "P0", "SL": "P0",
    "DME": "P1", "TEGDME": "P1", "GBL": "P1", "DMSO": "P1",
}

# Name aliases: the frozen tables use several spellings.
NAME_ALIASES = {
    "DIMETHYL CARBONATE": "DMC",
    "DIETHYL CARBONATE": "DEC",
    "SULFOLANE": "SL",
    "TETRAMETHYLENE SULFONE": "SL",
    "1,3-PROPANE SULTONE": "SL",
    "DIMETHOXYETHANE": "DME",
    "1,2-DIMETHOXYETHANE": "DME",
    "TETRAGLYME": "TEGDME",
    "GAMMA-BUTYROLACTONE": "GBL",
    "DIMETHYL SULFOXIDE": "DMSO",
    "SULFOLANE (TETRAMETHYLENE SULFONE)": "SL",
}


def canonical_name(raw: str) -> str:
    n = (raw or "").strip().upper()
    if not n or n in {"NOT_EVALUATED", "NAN", "NONE"}:
        return ""
    return NAME_ALIASES.get(n, n)


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    worksheet = STANDALONE / "reports" / "human_audit_worksheet_R007.csv"
    admission_matrix = STANDALONE / "reports" / "admission_matrix_R001.csv"
    pool_c = STANDALONE / "reports" / "candidate_pool_C_R001.csv"
    gap_audit = CONFIRM / "provenance_audit" / "gap_aggregation_audit.csv"
    pair_validity = CONFIRM / "provenance_repair" / "condition_pair_validity_v1.csv"
    ledger = CONFIRM / "provenance_repair" / "measurement_ledger_v1.csv"
    j02a = CONFIRM / "intersections" / "j02a_exclusion_summary.json"

    for p in (worksheet, admission_matrix, pool_c, gap_audit, pair_validity, ledger, j02a):
        if not p.is_file():
            print(f"FATAL: missing input {p}", file=sys.stderr)
            return 2

    ws_rows = load_csv(worksheet)
    am_rows = {r["measurement_id"]: r for r in load_csv(admission_matrix)}
    gap_rows = {r["measurement_id"]: r for r in load_csv(gap_audit)}

    # The admission matrix only covers 64 of the queue's ids, so 29 rows used to
    # get a blank phase/pressure/frequency via `.get(mid, {})`. But the MEASUREMENT
    # LEDGER carries those fields for every in-window observation. Backfilling
    # from the ledger is strictly better than shipping a blank that a reviewer
    # would read as "unknown" when the value is actually known.
    # For multi-observation aggregates we take the *distinct* set of values and
    # mark disagreement explicitly rather than picking one silently.
    _ledger_by_agg: dict[str, list[dict]] = {}
    for _m in load_csv(ledger):
        _a = (_m.get("aggregate_id") or "").strip()
        if _a and _a.lower() != "not_evaluated":
            _ledger_by_agg.setdefault(_a, []).append(_m)

    def _agg_suffix(mid: str) -> str:
        return f"v04row-{mid[len('EPSV04-R'):]}" if mid.startswith("EPSV04-R") else mid

    def _ledger_field(mid: str, field: str) -> str:
        """Distinct values of `field` across an aggregate's contributing rows."""
        rows = _ledger_by_agg.get(_agg_suffix(mid), [])
        vals = sorted({(r.get(field) or "").strip() for r in rows
                       if (r.get(field) or "").strip().lower() not in ("", "not_evaluated")})
        if not vals:
            return ""
        if len(vals) == 1:
            return vals[0]
        # Disagreement is itself evidence -- never collapse it to one value.
        return "MIXED[" + "|".join(vals) + "]"

    def _resolve(mid: str, am: dict, field: str) -> str:
        """Prefer the admission matrix, fall back to the ledger."""
        v = (am.get(field) or "").strip()
        if v:
            return v
        return _ledger_field(mid, field)

    # The condition-pair table is keyed by `aggregate_id` (v04row-NNN) while the
    # gap table is keyed by `measurement_id` (EPSV04-RNNN). These are the SAME
    # object under two names -- verified below by aligning the numeric suffix on
    # all 248 rows -- so build an explicit bridge instead of a silent join that
    # returns empty for every row.
    pv_by_measurement: dict[str, dict] = {}
    _pv_rows = load_csv(pair_validity)
    _n_bridged = 0
    for pv_row in _pv_rows:
        agg = (pv_row.get("aggregate_id") or "").strip()
        if not agg.startswith("v04row-"):
            continue
        suffix = agg[len("v04row-"):]
        mid = f"EPSV04-R{suffix}"
        if mid in gap_rows:
            pv_by_measurement[mid] = pv_row
            _n_bridged += 1
    if _n_bridged != len(_pv_rows):
        print(f"WARNING: bridged {_n_bridged}/{len(_pv_rows)} condition-pair rows",
              file=sys.stderr)

    j02a_doc = json.loads(j02a.read_text(encoding="utf-8"))

    # Molecule name lookup from the frozen pool + gap table.
    name_by_meas: dict[str, str] = {}
    for r in load_csv(pool_c):
        name_by_meas[r["measurement_id"]] = canonical_name(r.get("name", ""))
    for r in gap_rows.values():
        if r["measurement_id"] not in name_by_meas:
            name_by_meas[r["measurement_id"]] = canonical_name(r.get("a_name", ""))

    queue: list[dict] = []
    seen: set[tuple[str, str]] = set()

    def add(item: dict) -> None:
        key = (item["queue_id"], item["measurement_id"])
        if key in seen:
            return
        seen.add(key)
        queue.append(item)

    # ---- Track 1: the R007 worksheet rows (canonical 40-row admission set) ----
    for r in ws_rows:
        mid = r["measurement_id"]
        gap = gap_rows.get(mid, {})
        pv = pv_by_measurement.get(mid, {})
        am = am_rows.get(mid, {})
        add({
            "queue_id": f"Q-WS-{mid}",
            "track": "R007_WORKSHEET_40ROW",
            "priority_group": "P0" if canonical_name(gap.get("a_name", "")) in
            {"DMC", "DEC", "SL"} else "BASE",
            "measurement_id": mid,
            "molecule_id": r.get("molecule_id", ""),
            "a_name": gap.get("a_name", ""),
            "canonical_name": canonical_name(gap.get("a_name", "")) or
            canonical_name(name_by_meas.get(mid, "")),
            "source_group": r.get("source_group", ""),
            "temperature_raw_K": r.get("T_K", ""),
            "dielectric_raw": r.get("epsilon", ""),
            "pressure_kpa": r.get("pressure_kpa", ""),
            "phase": _resolve(mid, am, "phase"),
            "frequency_mhz": _resolve(mid, am, "frequency_mhz"),
            "evidence_provenance": r.get("evidence_provenance", ""),
            "machine_evidence": r.get("machine_evidence", ""),
            "machine_audit_status": r.get("machine_audit_status", ""),
            "a9_group_level": r.get("a9_group_level", ""),
            "human_items_to_judge": r.get("human_items_to_judge", ""),
            "human_audit_status": r.get("human_audit_status", ""),
            "admission_verdict_frozen": am.get("admission_verdict", ""),
            "gate_failures": am.get("failing", ""),
            "gate_unresolved": am.get("unresolved", ""),
            "j03_verdict": gap.get("verdict", ""),
            "j03_pair_in_single_observation": gap.get("pair_present_in_single_observation", ""),
            "j04_condition_pair_valid": pv.get("condition_pair_valid", ""),
            "j04_invalidity_reason": pv.get("invalidity_reason", ""),
            "n_contributing_sources": gap.get("n_contributing_sources", ""),
            "contributing_sources": gap.get("contributing_sources", ""),
            "sources_lost_in_gap": gap.get("sources_lost_in_gap", ""),
            "review_basis": "R007 worksheet row; frozen gates already computed",
        })

    # ---- Track 2: P0/P1 molecules named by the plan ----
    # Find their measurements in the ledger so reviewers see raw provenance.
    for mid, name in sorted(name_by_meas.items()):
        canon = canonical_name(name)
        if canon not in PRIORITY_GROUPS:
            continue
        gap = gap_rows.get(mid, {})
        pv = pv_by_measurement.get(mid, {})
        am = am_rows.get(mid, {})
        add({
            "queue_id": f"Q-PRI-{mid}",
            "track": "P0_P1_NAMED_MOLECULE",
            "priority_group": PRIORITY_GROUPS[canon],
            "measurement_id": mid,
            "molecule_id": gap.get("molecule_id", ""),
            "a_name": gap.get("a_name", name),
            "canonical_name": canon,
            "source_group": gap.get("gap_source_group", ""),
            "temperature_raw_K": gap.get("v04_T_K", ""),
            "dielectric_raw": gap.get("v04_epsilon", ""),
            "pressure_kpa": _resolve(mid, am, "pressure_kpa"),
            "phase": _resolve(mid, am, "phase"),
            "frequency_mhz": _resolve(mid, am, "frequency_mhz"),
            "evidence_provenance": "",
            "machine_evidence": "",
            "machine_audit_status": "",
            "a9_group_level": "",
            "human_items_to_judge": "",
            "human_audit_status": "",
            "admission_verdict_frozen": am.get("admission_verdict", ""),
            "gate_failures": am.get("failing", ""),
            "gate_unresolved": am.get("unresolved", ""),
            "j03_verdict": gap.get("verdict", ""),
            "j03_pair_in_single_observation": gap.get("pair_present_in_single_observation", ""),
            "j04_condition_pair_valid": pv.get("condition_pair_valid", ""),
            "j04_invalidity_reason": pv.get("invalidity_reason", ""),
            "n_contributing_sources": gap.get("n_contributing_sources", ""),
            "contributing_sources": gap.get("contributing_sources", ""),
            "sources_lost_in_gap": gap.get("sources_lost_in_gap", ""),
            "review_basis": "named P0/P1 molecule; requires J04 provenance + 4-agent review",
        })

    # ---- Track 3: the 22 COMPOSITE_CONDITION_UNMATCHED rows ----
    # B01 requires these enter an independent review queue regardless of whether
    # their molecule is in P0/P1.
    for mid, gap in sorted(gap_rows.items()):
        if gap["verdict"] != "COMPOSITE_CONDITION_UNMATCHED":
            continue
        pv = pv_by_measurement.get(mid, {})
        am = am_rows.get(mid, {})
        canon = canonical_name(gap.get("a_name", ""))
        add({
            "queue_id": f"Q-CCU-{mid}",
            "track": "COMPOSITE_CONDITION_UNMATCHED_22",
            "priority_group": PRIORITY_GROUPS.get(canon, "CCU"),
            "measurement_id": mid,
            "molecule_id": gap.get("molecule_id", ""),
            "a_name": gap.get("a_name", ""),
            "canonical_name": canon,
            "source_group": gap.get("gap_source_group", ""),
            "temperature_raw_K": gap.get("v04_T_K", ""),
            "dielectric_raw": gap.get("v04_epsilon", ""),
            "pressure_kpa": _resolve(mid, am, "pressure_kpa"),
            "phase": _resolve(mid, am, "phase"),
            "frequency_mhz": _resolve(mid, am, "frequency_mhz"),
            "evidence_provenance": "",
            "machine_evidence": "",
            "machine_audit_status": "",
            "a9_group_level": "",
            "human_items_to_judge": "",
            "human_audit_status": "",
            "admission_verdict_frozen": am.get("admission_verdict", ""),
            "gate_failures": am.get("failing", ""),
            "gate_unresolved": am.get("unresolved", ""),
            "j03_verdict": gap["verdict"],
            "j03_pair_in_single_observation": gap.get("pair_present_in_single_observation", ""),
            "j04_condition_pair_valid": pv.get("condition_pair_valid", ""),
            "j04_invalidity_reason": pv.get("invalidity_reason", ""),
            "n_contributing_sources": gap.get("n_contributing_sources", ""),
            "contributing_sources": gap.get("contributing_sources", ""),
            "sources_lost_in_gap": gap.get("sources_lost_in_gap", ""),
            "review_basis": "COMPOSITE_CONDITION_UNMATCHED; B01 mandates independent review",
        })

    # ---- Track 4: J02A's 4 explicit review targets ----
    for m in j02a_doc["molecules"]:
        mid = m["observation_id"]
        gap = gap_rows.get(mid, {})
        pv = pv_by_measurement.get(mid, {})
        am = am_rows.get(mid, {})
        add({
            "queue_id": f"Q-J02A-{mid}",
            "track": "J02A_REQUIRES_HUMAN_REVIEW_4",
            "priority_group": PRIORITY_GROUPS.get(canonical_name(m["a_name"]), "P1"),
            "measurement_id": mid,
            "molecule_id": gap.get("molecule_id", ""),
            "a_name": m["a_name"],
            "canonical_name": canonical_name(m["a_name"]),
            "source_group": gap.get("gap_source_group", ""),
            "temperature_raw_K": m["temperature_raw_K"],
            "dielectric_raw": gap.get("v04_epsilon", ""),
            "pressure_kpa": _resolve(mid, am, "pressure_kpa"),
            "phase": _resolve(mid, am, "phase"),
            "frequency_mhz": _resolve(mid, am, "frequency_mhz"),
            "evidence_provenance": "",
            "machine_evidence": "",
            "machine_audit_status": "",
            "a9_group_level": "",
            "human_items_to_judge": ";".join(m["exclusion_reasons"]),
            "human_audit_status": m["verdict"],
            "admission_verdict_frozen": am.get("admission_verdict", ""),
            "gate_failures": am.get("failing", ""),
            "gate_unresolved": am.get("unresolved", ""),
            "j03_verdict": gap.get("verdict", ""),
            "j03_pair_in_single_observation": gap.get("pair_present_in_single_observation", ""),
            "j04_condition_pair_valid": pv.get("condition_pair_valid", ""),
            "j04_invalidity_reason": pv.get("invalidity_reason", ""),
            "n_contributing_sources": gap.get("n_contributing_sources", ""),
            "contributing_sources": gap.get("contributing_sources", ""),
            "sources_lost_in_gap": gap.get("sources_lost_in_gap", ""),
            "review_basis": "J02A REQUIRES_HUMAN_REVIEW; exclusion reasons attached",
        })

    # ---- Track 5: unresolved source conflicts ----
    # Reviewer 4 found that gamma-valerolactone (36.1 vs 36.9 at the same T) was
    # ABSENT from this queue: excluded from review rather than adjudicated. An
    # audit that never sees a conflict cannot resolve it, so conflicts now enter
    # the queue by construction instead of by luck.
    conflict_register = REPO_ROOT / "outputs" / "b01" / "source_conflict_register.csv"
    if conflict_register.is_file():
        for c in load_csv(conflict_register):
            agg_ids = [a for a in (c.get("aggregate_ids") or "").split(";") if a.strip()]
            eps_vals = (c.get("epsilon_values") or "").strip()
            for agg_id in agg_ids:
                agg_id = agg_id.strip()
                if not agg_id.startswith("v04row-"):
                    continue
                mid = f"EPSV04-R{agg_id[len('v04row-'):]}"
                gap = gap_rows.get(mid, {})
                pv = pv_by_measurement.get(mid, {})
                am = am_rows.get(mid, {})
                add({
                    "queue_id": f"Q-CONF-{mid}",
                    "track": "UNRESOLVED_SOURCE_CONFLICT",
                    "priority_group": PRIORITY_GROUPS.get(
                        canonical_name(gap.get("a_name", "")), "CONFLICT"),
                    "measurement_id": mid,
                    "molecule_id": gap.get("molecule_id", ""),
                    "a_name": gap.get("a_name", c.get("a_name", "")),
                    "canonical_name": canonical_name(
                        gap.get("a_name", "") or c.get("a_name", "")),
                    "source_group": gap.get("gap_source_group", ""),
                    "temperature_raw_K": gap.get("v04_T_K", c.get("temperature_K", "")),
                    # Use the condition-pair table's value: it is the one the
                    # conflict register compared, and gap_epsilon can disagree
                    # with v04_epsilon on exactly these disputed rows (R227 has
                    # gap=36.1 but v04=36.9). Using the wrong side would make the
                    # two conflict rows look identical and hide the conflict.
                    "dielectric_raw": (
                        pv.get("v04_dielectric")
                        or gap.get("v04_epsilon", "")),
                    "pressure_kpa": _resolve(mid, am, "pressure_kpa"),
                    "phase": _resolve(mid, am, "phase"),
                    "frequency_mhz": _resolve(mid, am, "frequency_mhz"),
                    "evidence_provenance": "",
                    "machine_evidence": "",
                    "machine_audit_status": "",
                    "a9_group_level": "",
                    "human_items_to_judge": (
                        f"UNRESOLVED_CONFLICT: same compound, same T, "
                        f"epsilon={eps_vals}; sources="
                        f"{(c.get('source_documents') or '')}"),
                    "human_audit_status": "PENDING_REVIEW",
                    "admission_verdict_frozen": am.get("admission_verdict", ""),
                    "gate_failures": am.get("failing", ""),
                    "gate_unresolved": am.get("unresolved", ""),
                    "j03_verdict": gap.get("verdict", ""),
                    "j03_pair_in_single_observation": gap.get(
                        "pair_present_in_single_observation", ""),
                    "j04_condition_pair_valid": pv.get("condition_pair_valid", ""),
                    "j04_invalidity_reason": pv.get("invalidity_reason", ""),
                    "n_contributing_sources": gap.get("n_contributing_sources", ""),
                    "contributing_sources": gap.get("contributing_sources", ""),
                    "sources_lost_in_gap": gap.get("sources_lost_in_gap", ""),
                    "review_basis": (
                        "未决来源冲突; 必须裁决, 不得平均或择一"),
                })

    fieldnames = list(queue[0].keys())

    # Self-check: a column that is empty for EVERY row is almost always a broken
    # join rather than a genuine data property. Fail loudly instead of shipping a
    # queue whose "evidence" columns are silently blank. (This exact failure
    # happened once: condition_pair_validity is keyed by v04row-NNN while the
    # queue is keyed by EPSV04-RNNN, so the join returned nothing.)
    _critical = ["j04_condition_pair_valid", "j03_verdict",
                 "j03_pair_in_single_observation", "temperature_raw_K",
                 "dielectric_raw"]
    _empty_critical = [
        c for c in _critical
        if all(not (row.get(c) or "").strip() for row in queue)
    ]
    if _empty_critical:
        print(f"FATAL: these columns are empty on every queue row, which indicates "
              f"a broken join: {_empty_critical}", file=sys.stderr)
        return 3

    _coverage = {
        c: round(100.0 * sum(
            1 for row in queue
            if (row.get(c) or "").strip() and (row.get(c) or "").strip() != "not_evaluated"
        ) / len(queue), 1)
        for c in fieldnames
    }

    csv_path = OUT_DIR / "admission_review_queue.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        for row in queue:
            w.writerow(row)

    # ---- manifest binds the review to exact input bytes ----
    input_hashes = {
        "human_audit_worksheet_R007": {
            "path": str(worksheet), "sha256": sha256_file(worksheet),
            "bytes": worksheet.stat().st_size},
        "admission_matrix_R001": {
            "path": str(admission_matrix), "sha256": sha256_file(admission_matrix),
            "bytes": admission_matrix.stat().st_size},
        "candidate_pool_C_R001": {
            "path": str(pool_c), "sha256": sha256_file(pool_c),
            "bytes": pool_c.stat().st_size},
        "gap_aggregation_audit": {
            "path": str(gap_audit), "sha256": sha256_file(gap_audit),
            "bytes": gap_audit.stat().st_size},
        "condition_pair_validity_v1": {
            "path": str(pair_validity), "sha256": sha256_file(pair_validity),
            "bytes": pair_validity.stat().st_size},
        "measurement_ledger_v1": {
            "path": str(ledger), "sha256": sha256_file(ledger),
            "bytes": ledger.stat().st_size},
        "j02a_exclusion_summary": {
            "path": str(j02a), "sha256": sha256_file(j02a),
            "bytes": j02a.stat().st_size},
    }

    by_track: dict[str, int] = {}
    by_group: dict[str, int] = {}
    for r in queue:
        by_track[r["track"]] = by_track.get(r["track"], 0) + 1
        by_group[r["priority_group"]] = by_group.get(r["priority_group"], 0) + 1

    manifest = {
        "schema": "admission_v2.review_queue/v1",
        "generator": GENERATOR,
        "generated_at_utc": datetime.now(timezone.utc)
        .replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "declaration": (
            "本文件只组装待审队列, 不产生任何准入结论. 队列在此冻结并哈希, "
            "四位 Reviewer 必须针对同一份字节作答."
        ),
        "counts": {
            "n_queue_items": len(queue),
            "by_track": dict(sorted(by_track.items())),
            "by_priority_group": dict(sorted(by_group.items())),
        },
        "column_coverage_pct": _coverage,
        "column_coverage_note": (
            "每个队列列的非空率. 任何 0.0% 的列都意味着该字段在此队列中不承载信息, "
            "Reviewer 不得把'该列存在'当作证据存在."
        ),
        "input_hashes": input_hashes,
        "queue_csv": {
            "path": str(csv_path), "sha256": sha256_file(csv_path),
            "bytes": csv_path.stat().st_size,
        },
        "review_contract": {
            "decision_values": ["PASS", "HOLD", "FAIL"],
            "consensus_rule": "4/4 PASS required; any HOLD or FAIL blocks the record",
            "forbidden": [
                "majority vote",
                "one model answering as four reviewers",
                "writing AI consensus into a HUMAN_SIGNED field",
            ],
            "required_per_record": [
                "input hash", "reviewer identity", "model/agent version",
                "prompt version", "review timestamp", "independent decision",
                "concrete evidence", "final consensus",
            ],
        },
    }
    man_path = OUT_DIR / "admission_review_queue_manifest.json"
    man_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")

    print(f"[B02-1] {csv_path}  ({len(queue)} queue items)")
    print(f"[B02-1] {man_path}")
    for k, v in sorted(by_track.items()):
        print(f"  track {k:38s} {v}")
    print("  by group:", dict(sorted(by_group.items())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
