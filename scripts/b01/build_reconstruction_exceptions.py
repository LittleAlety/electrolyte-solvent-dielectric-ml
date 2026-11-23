#!/usr/bin/env python
"""B01-2: build reconstruction_exceptions.csv -- the formal record of what could
NOT be recovered.

PLAN B B01 requires this file, and chapter 6 says an unrecoverable measurement
must be *marked* unrecoverable rather than guessed. This script produces that
marking. It is the negative ledger: every row here is an aggregate that could not
be resolved back to a contributing measurement, with the specific reason.

Three exception classes are emitted, and the distinction matters:

  NO_CONTRIBUTING_MEASUREMENT
      The source layer genuinely holds no in-band observation for this aggregate.
      Nothing can be reconstructed. Certificate stands.

  SOURCE_LAYER_MISMATCH_FALSE_NEGATIVE
      An in-band observation *does* exist but was excluded by the hard-coded
      window, not by an absence of data. Reviewer 3 and Reviewer 4 both found
      this for EPSV04-R247 (succinonitrile): the ledger holds an exact match at
      333.15 K, but the window is 293.15-303.15 K, so it was counted as zero.
      The FAIL verdict is still correct for room-temperature use, but the
      *stated reason* is wrong. Marking these separately stops the project from
      later claiming "provenance was lost" when provenance was present.

  SYNTHETIC_PAIR_FROM_INDEPENDENT_MEDIAN
      A pair was assembled from two different observations (temperature median
      from one, epsilon median from another). The pair is real arithmetic but not
      a real measurement.

This script does NOT repair anything. It records. Repair decisions belong to a
reviewed change, not to an exception register.

Output: outputs/confirm_2027/provenance_repair/reconstruction_exceptions.csv
        outputs/confirm_2027/provenance_repair/reconstruction_exceptions_summary.json
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
OUT_DIR = REPO_ROOT / "outputs" / "confirm_2027" / "provenance_repair"
GENERATOR = "build_reconstruction_exceptions/1.0.0"

AGG_LEDGER = OUT_DIR / "aggregate_contribution_ledger_v1.csv"
PAIR_VALIDITY = OUT_DIR / "condition_pair_validity_v1.csv"
MEAS_LEDGER = OUT_DIR / "measurement_ledger_v1.csv"

BAND_LOW = 293.15
BAND_HIGH = 303.15

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


def is_blank(v: str | None) -> bool:
    return (v or "").strip().lower() in PLACEHOLDERS


def main() -> int:
    for p in (AGG_LEDGER, PAIR_VALIDITY, MEAS_LEDGER):
        if not p.is_file():
            print(f"FATAL: missing input {p}", file=sys.stderr)
            return 2

    agg = load(AGG_LEDGER)
    pair = load(PAIR_VALIDITY)
    meas = load(MEAS_LEDGER)

    # Bridge v04row-NNN <-> EPSV04-RNNN (the same object under two names).
    pair_by_meas: dict[str, dict] = {}
    for p in pair:
        aid = (p.get("aggregate_id") or "").strip()
        if aid.startswith("v04row-"):
            pair_by_meas[f"EPSV04-R{aid[len('v04row-'):]}"] = p

    # Index the measurement ledger by molecule so we can detect false negatives.
    ledger_by_mol: dict[str, list[dict]] = defaultdict(list)
    for m in meas:
        ledger_by_mol[(m.get("inchikey") or "").strip()].append(m)

    exceptions: list[dict] = []

    for a in agg:
        aid = (a.get("aggregate_id") or "").strip()
        mid = f"EPSV04-R{aid[len('v04row-'):]}" if aid.startswith("v04row-") else aid
        status = (a.get("contribution_status") or "").strip()
        cert = (a.get("contribution_certificate") or "").strip()
        pv = pair_by_meas.get(mid, {})
        mol = (a.get("molecule_key") or "").strip()
        v04_t = (a.get("v04_T_K") or "").strip()
        v04_eps = (a.get("v04_dielectric") or "").strip()

        pair_valid = (pv.get("condition_pair_valid") or "").strip()
        invalidity = (pv.get("invalidity_reason") or "").strip()

        # ---- Class A: no contributing measurement ----
        if status == "MISSING_CERTIFICATE":
            # Is this a genuine absence, or a window artefact?
            mol_rows = ledger_by_mol.get(mol, [])
            off_band_matches = []
            for r in mol_rows:
                try:
                    t = float((r.get("temperature_K") or "").strip())
                    e = float((r.get("dielectric") or "").strip())
                except (TypeError, ValueError):
                    continue
                in_band = BAND_LOW <= t <= BAND_HIGH
                if in_band:
                    continue
                # An exact (T, eps) match to the v04 aggregate, but outside band.
                try:
                    if abs(e - float(v04_eps)) < 1e-9 and abs(t - float(v04_t)) < 1e-9:
                        off_band_matches.append(r)
                except (TypeError, ValueError):
                    continue

            if off_band_matches:
                hit = off_band_matches[0]
                exceptions.append({
                    "exception_id": f"EXC-{mid}",
                    "aggregate_id": aid,
                    "measurement_id": mid,
                    "molecule_key": mol,
                    "a_name": (a.get("a_name") or "").strip(),
                    "v04_T_K": v04_t,
                    "v04_dielectric": v04_eps,
                    "exception_class": "SOURCE_LAYER_MISMATCH_FALSE_NEGATIVE",
                    "contribution_status": status,
                    "contribution_certificate": cert,
                    "condition_pair_valid": pair_valid,
                    "invalidity_reason": invalidity,
                    "recoverable": "true",
                    "evidence": (
                        f"账本中存在精确匹配观测 {(hit.get('measurement_id') or '').strip()} "
                        f"(T={(hit.get('temperature_K') or '').strip()}, "
                        f"eps={(hit.get('dielectric') or '').strip()}, "
                        f"src={(hit.get('source_document_id') or '').strip()})，"
                        f"但因该观测温度落在硬编码窗口 [{BAND_LOW}, {BAND_HIGH}] K 之外而被计为 0 条贡献"
                    ),
                    "stated_reason_is_wrong": "true",
                    "downstream_rule": (
                        "室温用途的 FAIL 结论仍然成立；但不得据此宣称『来源已丢失』。"
                        "若需高温用途，须另建独立窗口，不得改动本窗口"
                    ),
                    "repair_action": "NONE_AUTOMATIC",
                })
            else:
                exceptions.append({
                    "exception_id": f"EXC-{mid}",
                    "aggregate_id": aid,
                    "measurement_id": mid,
                    "molecule_key": mol,
                    "a_name": (a.get("a_name") or "").strip(),
                    "v04_T_K": v04_t,
                    "v04_dielectric": v04_eps,
                    "exception_class": "NO_CONTRIBUTING_MEASUREMENT",
                    "contribution_status": status,
                    "contribution_certificate": cert,
                    "condition_pair_valid": pair_valid,
                    "invalidity_reason": invalidity,
                    "recoverable": "false",
                    "evidence": (
                        f"来源层无该分子的窗口内观测 (分子在账本中共 {len(mol_rows)} 行)。"
                        f"证书: {cert}"
                    ),
                    "stated_reason_is_wrong": "false",
                    "downstream_rule": (
                        "不可恢复。不得插值、不得反推、不得从聚合结果还原。"
                        "保留原始 v04 值作为不可追溯记录"
                    ),
                    "repair_action": "NONE_AUTOMATIC",
                })
            continue

        # ---- Class B: pair invalid even though contributions exist ----
        if status == "COMPLETE" and pair_valid == "false":
            exceptions.append({
                "exception_id": f"EXC-{mid}",
                "aggregate_id": aid,
                "measurement_id": mid,
                "molecule_key": mol,
                "a_name": (a.get("a_name") or "").strip(),
                "v04_T_K": v04_t,
                "v04_dielectric": v04_eps,
                "exception_class": "SYNTHETIC_PAIR_FROM_INDEPENDENT_MEDIAN",
                "contribution_status": status,
                "contribution_certificate": cert,
                "condition_pair_valid": pair_valid,
                "invalidity_reason": invalidity,
                "recoverable": "partial",
                "evidence": (
                    f"有 {a.get('n_contributing_measurements','')} 条贡献测量、"
                    f"{a.get('n_contributing_sources','')} 个来源，但 (T, eps) 不是同一次观测。"
                    f"原因: {invalidity}"
                ),
                "stated_reason_is_wrong": "false",
                "downstream_rule": (
                    "该聚合行可作为『有贡献测量』的入口，但 (T, eps) 组合不得作为测量记录使用。"
                    "需按 measurement_id 逐条取用贡献测量"
                ),
                "repair_action": "USE_CONTRIBUTING_MEASUREMENTS_NOT_THE_PAIR",
            })

    # ---- write CSV ----
    fields = ["exception_id", "aggregate_id", "measurement_id", "molecule_key",
              "a_name", "v04_T_K", "v04_dielectric", "exception_class",
              "contribution_status", "contribution_certificate",
              "condition_pair_valid", "invalidity_reason", "recoverable",
              "stated_reason_is_wrong", "evidence", "downstream_rule",
              "repair_action"]
    csv_path = OUT_DIR / "reconstruction_exceptions.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for r in exceptions:
            w.writerow(r)

    by_class = Counter(r["exception_class"] for r in exceptions)
    by_recoverable = Counter(r["recoverable"] for r in exceptions)
    false_neg = [r["measurement_id"] for r in exceptions
                 if r["exception_class"] == "SOURCE_LAYER_MISMATCH_FALSE_NEGATIVE"]

    summary = {
        "schema": "confirm_2027.reconstruction_exceptions/v1",
        "generator": GENERATOR,
        "generated_at_utc": datetime.now(timezone.utc)
        .replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "declaration": (
            "本文件记录**无法恢复**的聚合行及其具体原因. 不修复、不插值、不反推. "
            "把『来源层真的没有数据』与『窗口把数据排除了』分开记录, "
            "避免以后把后者误称为来源丢失."
        ),
        "inputs": {
            "aggregate_contribution_ledger_v1": {
                "sha256": sha256_file(AGG_LEDGER),
                "rows": len(agg)},
            "condition_pair_validity_v1": {
                "sha256": sha256_file(PAIR_VALIDITY),
                "rows": len(pair)},
            "measurement_ledger_v1": {
                "sha256": sha256_file(MEAS_LEDGER),
                "rows": len(meas)},
        },
        "counts": {
            "n_aggregates_total": len(agg),
            "n_exceptions": len(exceptions),
            "by_class": dict(sorted(by_class.items())),
            "by_recoverable": dict(sorted(by_recoverable.items())),
            "n_stated_reason_wrong": sum(
                1 for r in exceptions if r["stated_reason_is_wrong"] == "true"),
        },
        "false_negatives_found": sorted(false_neg),
        "false_negative_note": (
            "这些行的 contribution_certificate 声称来源层无数据, 但账本中确实存在"
            "精确匹配观测, 只是温度落在硬编码窗口外. 结论 (pair 无效) 仍对, "
            "但理由错误."
        ),
        "band_window": {"low_K": BAND_LOW, "high_K": BAND_HIGH,
                        "note": "R219 冻结窗口; 本文件不改动它"},
        "repair_policy": {
            "automatic_repair": False,
            "forbidden": [
                "插值补造测量",
                "从聚合结果反推贡献清单",
                "为了凑数把高温观测折成室温",
                "改动 R219 冻结窗口",
            ],
        },
        "output": {"path": str(csv_path.relative_to(REPO_ROOT)),
                   "sha256": sha256_file(csv_path), "rows": len(exceptions)},
    }
    json_path = OUT_DIR / "reconstruction_exceptions_summary.json"
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
                         encoding="utf-8")

    print(f"[B01-2] {csv_path}  ({len(exceptions)} exceptions)")
    print(f"[B01-2] {json_path}")
    for k, v in sorted(by_class.items()):
        print(f"  {k:42s} {v}")
    print(f"  recoverable: {dict(sorted(by_recoverable.items()))}")
    print(f"  false negatives found: {false_neg}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
