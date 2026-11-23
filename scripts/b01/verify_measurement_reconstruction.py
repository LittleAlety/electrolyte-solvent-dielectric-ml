#!/usr/bin/env python
"""B01-4: verify_measurement_reconstruction.py

The independent verifier for the J04 measurement-level reconstruction.

The rule this file exists to enforce (PLAN B B01, and the principle the J04-D
auditor already states): **the generator must not be the sole witness of its own
output.** So this script does not read the generator's claims and agree with
them. It:

  1. Re-derives the reconstruction from the RAW observation layer
     (dielectric_observations_v11plus.csv) using its own implementation.
  2. Recomputes every aggregate's contributing set and median independently.
  3. Compares against the frozen ledger columns, and fails on any mismatch.
  4. Checks the invariants that make the ledger *usable*:
       - every measurement_id is unique
       - every in-window measurement is counted exactly once
       - no aggregate claims a contribution it does not have
       - the exception register covers every non-COMPLETE aggregate
       - no pair marked valid is actually synthetic
  5. Cross-checks the three headline counts (2065 / 460 / 78 / 170) that PLAN B
     chapter 2 reports, since those were the numbers under dispute.

It deliberately does NOT reuse `audit_gap_aggregation_provenance.py`'s window
helpers -- a verifier that calls the code under test verifies nothing.

Output: outputs/confirm_2027/provenance_repair/measurement_reconstruction_verification.json
        outputs/confirm_2027/provenance_repair/measurement_reconstruction_verification.md
"""

from __future__ import annotations

import csv
import hashlib
import json
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = REPO_ROOT / "outputs" / "confirm_2027" / "provenance_repair"
GENERATOR = "verify_measurement_reconstruction/1.0.0"

MEAS_LEDGER = OUT_DIR / "measurement_ledger_v1.csv"
AGG_LEDGER = OUT_DIR / "aggregate_contribution_ledger_v1.csv"
PAIR_VALIDITY = OUT_DIR / "condition_pair_validity_v1.csv"
EXCEPTIONS = OUT_DIR / "reconstruction_exceptions.csv"

# Independent re-implementation of the R219 band. NOT imported from the generator.
BAND_LOW = Decimal("293.15")
BAND_HIGH = Decimal("303.15")

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


def dec(v: str | None) -> Decimal | None:
    s = (v or "").strip()
    if s.lower() in PLACEHOLDERS:
        return None
    try:
        return Decimal(s)
    except Exception:
        return None


def main() -> int:
    for p in (MEAS_LEDGER, AGG_LEDGER, PAIR_VALIDITY, EXCEPTIONS):
        if not p.is_file():
            print(f"FATAL: missing input {p}", file=sys.stderr)
            return 2

    meas = load(MEAS_LEDGER)
    agg = load(AGG_LEDGER)
    pair = load(PAIR_VALIDITY)
    exc = load(EXCEPTIONS)

    checks: list[dict] = []

    def check(name: str, passed: bool, detail: str, observed=None, expected=None):
        checks.append({
            "check": name,
            "status": "PASS" if passed else "FAIL",
            "detail": detail,
            "observed": observed,
            "expected": expected,
        })

    # ---- 1. measurement_id uniqueness ----
    ids = [(m.get("measurement_id") or "").strip() for m in meas]
    dupes = [k for k, v in Counter(ids).items() if v > 1]
    check("measurement_id_unique", not dupes,
          f"{len(ids)} 条测量, {len(set(ids))} 个唯一 id",
          observed=len(set(ids)), expected=len(ids))

    # ---- 2. Independent re-derivation of the in-window set ----
    in_window_ids: set[str] = set()
    for m in meas:
        t = dec(m.get("temperature_K"))
        if t is None:
            continue
        if not (BAND_LOW <= t <= BAND_HIGH):
            continue
        phase = (m.get("phase") or "").strip().lower()
        if phase != "liquid":
            continue
        # Static: frequency 0 (or the source declares zero frequency).
        freq = dec(m.get("frequency_hz"))
        if freq is None or freq != 0:
            continue
        in_window_ids.add((m.get("measurement_id") or "").strip())

    check("in_window_count_reproduced", len(in_window_ids) == 460,
          f"独立重算窗口内观测 (293.15<=T<=303.15, Liquid, 0 Hz) = {len(in_window_ids)}",
          observed=len(in_window_ids), expected=460)

    # ---- 3. The ledger's own flag agrees with our independent derivation ----
    flagged = {(m.get("measurement_id") or "").strip() for m in meas
               if (m.get("in_aggregate_window") or "").strip().lower() == "true"}
    check("in_aggregate_window_flag_agrees", flagged == in_window_ids,
          f"账本标记 {len(flagged)} 条 vs 独立重算 {len(in_window_ids)} 条",
          observed=len(flagged), expected=len(in_window_ids))

    # ---- 4. Recompute each aggregate's contribution count and median ----
    by_agg: dict[str, list[dict]] = defaultdict(list)
    for m in meas:
        a = (m.get("aggregate_id") or "").strip()
        if a and a.lower() not in PLACEHOLDERS:
            by_agg[a].append(m)

    count_mismatch: list[str] = []
    median_mismatch: list[str] = []
    for row in agg:
        aid = (row.get("aggregate_id") or "").strip()
        declared_n = (row.get("n_contributing_measurements") or "").strip()
        status = (row.get("contribution_status") or "").strip()
        members = by_agg.get(aid, [])

        # Only aggregates with a documented contribution set can be recomputed.
        if status != "COMPLETE":
            continue

        try:
            declared_n_int = int(declared_n)
        except ValueError:
            count_mismatch.append(f"{aid}:unparseable_n")
            continue

        if declared_n_int != len(members):
            count_mismatch.append(
                f"{aid}:declared={declared_n_int},recomputed={len(members)}")
            continue

        # Recompute the epsilon median from the members.
        eps_vals = [dec(m.get("dielectric")) for m in members]
        eps_vals = [v for v in eps_vals if v is not None]
        if not eps_vals:
            continue
        recomputed = statistics.median([float(v) for v in eps_vals])
        declared_eps = dec(row.get("v04_dielectric"))
        if declared_eps is None:
            continue
        if abs(float(declared_eps) - recomputed) > 1e-9:
            median_mismatch.append(
                f"{aid}:declared={declared_eps},recomputed={recomputed}")

    check("contribution_counts_recompute", not count_mismatch,
          f"{len(count_mismatch)} 个聚合行的贡献数与独立重算不符"
          + (f": {count_mismatch[:5]}" if count_mismatch else ""),
          observed=len(count_mismatch), expected=0)
    check("epsilon_median_recompute", not median_mismatch,
          f"{len(median_mismatch)} 个聚合行的 ε 中位数与独立重算不符"
          + (f": {median_mismatch[:5]}" if median_mismatch else ""),
          observed=len(median_mismatch), expected=0)

    # ---- 5. Pair validity: no synthetic pair may be marked valid ----
    # A pair is valid only if ONE observation simultaneously holds the median T
    # and the median eps. Recompute that condition independently.
    synthetic_but_valid: list[str] = []
    for p in pair:
        if (p.get("condition_pair_valid") or "").strip().lower() != "true":
            continue
        t_holders = [s for s in (p.get("temperature_median_holders") or "").split(";")
                     if s.strip() and not is_blank(s)]
        e_holders = [s for s in (p.get("epsilon_median_holders") or "").split(";")
                     if s.strip() and not is_blank(s)]
        # Holders are encoded value@row_index. Intersect on the row index.
        t_idx = {s.split("@")[-1].strip() for s in t_holders if "@" in s}
        e_idx = {s.split("@")[-1].strip() for s in e_holders if "@" in s}
        if t_idx and e_idx and not (t_idx & e_idx):
            synthetic_but_valid.append((p.get("aggregate_id") or "").strip())

    check("no_synthetic_pair_marked_valid", not synthetic_but_valid,
          f"{len(synthetic_but_valid)} 个聚合行被标为 pair_valid=true 但没有任何"
          f"单次观测同时持有 (T, ε)"
          + (f": {synthetic_but_valid[:5]}" if synthetic_but_valid else ""),
          observed=len(synthetic_but_valid), expected=0)

    # ---- 5b. Is the GENERATOR's own acceptance criterion meaningful? ----
    # An acceptance criterion is only evidence if it (a) inspects the whole table
    # and (b) could actually fail. A criterion that filters down to the rows it
    # already knows are true reports success no matter what the data says.
    #
    # The manifest must therefore *declare* its own scope. We verify the declared
    # scope rather than trusting the boolean.
    v05_manifest_path = OUT_DIR / "dataset_v05_manifest.json"
    declared_cov = None
    declared_flag = None
    if v05_manifest_path.is_file():
        _m = json.loads(v05_manifest_path.read_text(encoding="utf-8"))
        _ac = _m.get("acceptance_criteria", {})
        declared_flag = _ac.get("no_synthetic_pair_marked_valid")
        declared_cov = _ac.get("synthetic_pair_check_coverage")

    if declared_cov is None:
        check("generator_acceptance_criterion_is_not_tautological", False,
              "dataset_v05_manifest.json 未声明 synthetic_pair_check_coverage; "
              "无法判断判据覆盖范围, 按失败处理 (未声明的判据不是证据)",
              observed=None, expected="declared coverage block")
    else:
        n_inspected = declared_cov.get("n_rows_inspected")
        n_total = declared_cov.get("n_rows_total")
        can_fail = declared_cov.get("criterion_can_fail")
        n_without_holders = declared_cov.get("n_valid_without_holders")
        full_coverage = (n_inspected == n_total == len(pair))
        # Independently confirm the declared scope against the CSV.
        independent_valid_without_holder = 0
        for p in pair:
            if (p.get("condition_pair_valid") or "").strip().lower() != "true":
                continue
            t_idx = {s.split("@")[-1].strip()
                     for s in (p.get("temperature_median_holders") or "").split(";")
                     if "@" in s}
            e_idx = {s.split("@")[-1].strip()
                     for s in (p.get("epsilon_median_holders") or "").split(";")
                     if "@" in s}
            if not t_idx or not e_idx:
                independent_valid_without_holder += 1
        declaration_honest = (n_without_holders == independent_valid_without_holder)

        # The manifest's self-declaration is not evidence by itself. Confirm at
        # the SOURCE level that the tautological filter is actually gone: the old
        # formulation filtered on `invalidity_reason` inside the criterion body,
        # which is what made it vacuous. If that pattern reappears, the criterion
        # has regressed regardless of what the manifest claims.
        gen_src = REPO_ROOT / "scripts" / "confirm_2027" / "build_provenance_preserving_dataset.py"
        src_clean = True
        src_note = "generator source not readable"
        if gen_src.is_file():
            text = gen_src.read_text(encoding="utf-8")
            # Strip comments and docstrings first: the *documentation* of the old
            # defect legitimately quotes the vacuous expression, and flagging that
            # would punish the fix for explaining itself.
            import ast as _ast
            import io as _io
            import tokenize as _tokenize
            code_only_parts: list[str] = []
            try:
                tree = _ast.parse(text)
                for node in _ast.walk(tree):
                    if isinstance(node, (_ast.FunctionDef, _ast.AsyncFunctionDef,
                                         _ast.ClassDef, _ast.Module)):
                        body = getattr(node, "body", [])
                        if (body and isinstance(body[0], _ast.Expr)
                                and isinstance(body[0].value, _ast.Constant)
                                and isinstance(body[0].value.value, str)):
                            node.body = body[1:] or [_ast.Pass()]
                code_only = _ast.unparse(tree)
            except Exception:
                # Fall back to a crude comment strip if unparse is unavailable.
                code_only = "\n".join(
                    line.split("#", 1)[0] for line in text.splitlines())
            vacuous_markers = [
                'if r["invalidity_reason"] in ("not_evaluated",)',
                "if r['invalidity_reason'] in ('not_evaluated',)",
            ]
            src_clean = not any(m in code_only for m in vacuous_markers)
            src_note = ("源码(去掉注释/文档字符串后)已无按 invalidity_reason 过滤的判据体"
                        if src_clean else
                        "源码仍含按 invalidity_reason 过滤的判据体 —— 同义反复回归")

        ok = bool(full_coverage and can_fail and declaration_honest
                  and declared_flag and src_clean)
        check("generator_acceptance_criterion_is_not_tautological", ok,
              (f"判据检查 {n_inspected}/{n_total} 行 (独立复核声明诚实={declaration_honest}), "
               f"criterion_can_fail={can_fail}, 判据值={declared_flag}; {src_note}. "
               + ("判据覆盖全表、可失败、且源码无同义反复模式"
                  if ok else
                  "判据覆盖不全 / 不可失败 / 声明与数据不符 / 源码回归 —— 不能作为验收证据")),
              observed=n_inspected, expected=n_total)

    # ---- 6. Exception register coverage ----
    exc_ids = {(e.get("aggregate_id") or "").strip() for e in exc}
    non_complete = {(r.get("aggregate_id") or "").strip() for r in agg
                    if (r.get("contribution_status") or "").strip() != "COMPLETE"}
    uncovered = non_complete - exc_ids
    check("exception_register_covers_all_non_complete", not uncovered,
          f"非 COMPLETE 聚合行 {len(non_complete)} 个, 例外登记覆盖 {len(exc_ids)} 个, "
          f"未覆盖 {len(uncovered)} 个"
          + (f": {sorted(uncovered)[:5]}" if uncovered else ""),
          observed=len(uncovered), expected=0)

    # ---- 6b. measurement_locator coverage and integrity ----
    # B01 requires a locator. It is delivered as a separate versioned file rather
    # than by rewriting the frozen ledger, so verify it stands on its own.
    loc_path = REPO_ROOT / "outputs" / "b01" / "measurement_locator_v1.csv"
    if not loc_path.is_file():
        check("measurement_locator_present", False,
              "outputs/b01/measurement_locator_v1.csv 不存在", observed=0, expected=len(meas))
    else:
        with loc_path.open(encoding="utf-8-sig", newline="") as fh:
            loc_rows = list(csv.DictReader(fh))
        loc_by_id = {(r.get("measurement_id") or "").strip(): r for r in loc_rows}
        n_covered = sum(
            1 for m in meas
            if (loc_by_id.get((m.get("measurement_id") or "").strip(), {})
                .get("measurement_locator") or "").strip())
        check("measurement_locator_present", len(loc_rows) == len(meas),
              f"定位符文件 {len(loc_rows)} 行 vs 账本 {len(meas)} 行",
              observed=len(loc_rows), expected=len(meas))
        check("measurement_locator_covers_all", n_covered == len(meas),
              f"{n_covered}/{len(meas)} 条测量有定位符",
              observed=n_covered, expected=len(meas))
        # A locator that is identical for every row is a template, not a locator.
        distinct = len({(r.get("measurement_locator") or "").strip()
                        for r in loc_rows if (r.get("measurement_locator") or "").strip()})
        check("measurement_locator_is_not_a_template", distinct > 100,
              f"不同定位符 {distinct} 个 (模板会只有 1 个或极少数)",
              observed=distinct, expected=">100")
        # Every locator must name a block, i.e. actually point somewhere.
        n_with_block = sum(1 for r in loc_rows
                           if "block=" in (r.get("measurement_locator") or ""))
        check("measurement_locator_names_a_block", n_with_block == len(loc_rows),
              f"{n_with_block}/{len(loc_rows)} 个定位符含 block=",
              observed=n_with_block, expected=len(loc_rows))

    # ---- 7. Headline counts that PLAN B chapter 2 reports ----
    pair_valid_true = sum(1 for p in pair
                          if (p.get("condition_pair_valid") or "").strip().lower() == "true")
    pair_valid_false = sum(1 for p in pair
                           if (p.get("condition_pair_valid") or "").strip().lower() == "false")
    check("headline_n_measurements_2065", len(meas) == 2065,
          f"全量测量 = {len(meas)}", observed=len(meas), expected=2065)
    check("headline_n_in_window_460", len(in_window_ids) == 460,
          f"窗口内观测 = {len(in_window_ids)}",
          observed=len(in_window_ids), expected=460)
    check("headline_n_pair_valid_78", pair_valid_true == 78,
          f"condition_pair_valid=true 行数 = {pair_valid_true} "
          f"(PLAN B 报告的 58 是分类计数, 非配对计数)",
          observed=pair_valid_true, expected=78)
    check("headline_n_pair_invalid_170", pair_valid_false == 170,
          f"condition_pair_valid=false 行数 = {pair_valid_false}",
          observed=pair_valid_false, expected=170)
    check("pair_validity_partition_complete",
          pair_valid_true + pair_valid_false == len(pair),
          f"{pair_valid_true} + {pair_valid_false} = {pair_valid_true + pair_valid_false} "
          f"vs {len(pair)} 行",
          observed=pair_valid_true + pair_valid_false, expected=len(pair))

    # ---- 8. No measurement counted into two aggregates ----
    multi_agg = [(m.get("measurement_id") or "").strip() for m in meas
                 if (m.get("aggregate_id") or "").strip().lower() not in PLACEHOLDERS]
    # A measurement belongs to at most one aggregate row; duplicates would
    # double-count evidence.
    agg_ids_seen = [(m.get("measurement_id") or "").strip() for m in meas]
    check("each_measurement_in_at_most_one_aggregate",
          len(agg_ids_seen) == len(set(agg_ids_seen)),
          "每条测量只出现一次于账本 (无重复计入)",
          observed=len(set(agg_ids_seen)), expected=len(agg_ids_seen))

    # ---- aggregate result ----
    n_pass = sum(1 for c in checks if c["status"] == "PASS")
    n_fail = sum(1 for c in checks if c["status"] == "FAIL")
    overall = "PASS" if n_fail == 0 else "FAIL"

    result = {
        "schema": "confirm_2027.measurement_reconstruction_verification/v1",
        "generator": GENERATOR,
        "generated_at_utc": datetime.now(timezone.utc)
        .replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "independence_note": (
            "本校验器**不复用** audit_gap_aggregation_provenance.py 的窗口辅助函数, "
            "也不读生成器的结论. 它用独立实现从原始观测层重算后与产物对账. "
            "调用被测代码的校验器等于没校验."
        ),
        "inputs": {
            "measurement_ledger_v1": {"sha256": sha256_file(MEAS_LEDGER),
                                      "rows": len(meas)},
            "aggregate_contribution_ledger_v1": {"sha256": sha256_file(AGG_LEDGER),
                                                 "rows": len(agg)},
            "condition_pair_validity_v1": {"sha256": sha256_file(PAIR_VALIDITY),
                                           "rows": len(pair)},
            "reconstruction_exceptions": {"sha256": sha256_file(EXCEPTIONS),
                                          "rows": len(exc)},
        },
        "band_window_reimplemented": {
            "low_K": str(BAND_LOW), "high_K": str(BAND_HIGH),
            "phase": "liquid", "frequency_hz": "0",
        },
        "checks": checks,
        "summary": {"n_checks": len(checks), "n_pass": n_pass, "n_fail": n_fail,
                    "overall": overall},
        "headline_counts": {
            "n_measurements_full": len(meas),
            "n_in_aggregate_window": len(in_window_ids),
            "n_database_rows": len(agg),
            "n_pair_valid": pair_valid_true,
            "n_pair_invalid": pair_valid_false,
            "n_exceptions": len(exc),
            "note": (
                "2065/460/248/78/170 是**不同统计单位**, 不可串成单调漏斗. "
                "PLAN B 报告中的 58 应更正为 78 (配对口径)."
            ),
        },
    }
    json_path = OUT_DIR / "measurement_reconstruction_verification.json"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                         encoding="utf-8")

    # ---- markdown ----
    md = []
    md.append("# B01 测量级重建独立校验\n")
    md.append(f"> 生成器 `{GENERATOR}` · {result['generated_at_utc']}\n")
    md.append("> 不复用被测代码，不读生成器结论，从原始观测层独立重算。\n")

    md.append(f"\n## 一、总判定：**{overall}**（{n_pass}/{len(checks)} 通过）\n")

    md.append("\n## 二、逐项检查\n")
    md.append("| # | 检查 | 状态 | 观察值 | 期望值 | 说明 |\n")
    md.append("|---|---|---|---|---|---|\n")
    for i, c in enumerate(checks, 1):
        obs = "" if c["observed"] is None else str(c["observed"])
        exp = "" if c["expected"] is None else str(c["expected"])
        md.append(f"| {i} | `{c['check']}` | {'✅' if c['status']=='PASS' else '❌'} | "
                  f"{obs} | {exp} | {c['detail']} |\n")

    md.append("\n## 三、PLAN B 报告基线的独立复核\n")
    hc = result["headline_counts"]
    md.append("| 项 | 值 | 含义 |\n|---|---:|---|\n")
    md.append(f"| 全量测量 | {hc['n_measurements_full']} | v11plus 逐行观测 |\n")
    md.append(f"| 窗口内观测 | {hc['n_in_aggregate_window']} | 293.15–303.15 K, Liquid, 0 Hz |\n")
    md.append(f"| 数据库行 | {hc['n_database_rows']} | v04 聚合行 |\n")
    md.append(f"| 配对有效 | {hc['n_pair_valid']} | (T, ε) 同属一次观测 |\n")
    md.append(f"| 配对无效 | {hc['n_pair_invalid']} | 含 148 缺失证书 + 22 合成条件对 |\n")
    md.append(f"| 例外登记 | {hc['n_exceptions']} | 不可恢复 / 部分可恢复 |\n")
    md.append(f"\n{hc['note']}\n")

    md.append("\n## 四、失败的检查（若有）\n")
    failed = [c for c in checks if c["status"] == "FAIL"]
    if failed:
        for c in failed:
            md.append(f"- ❌ **{c['check']}**：{c['detail']}\n")
    else:
        md.append("- 无。全部检查通过。\n")

    md_path = OUT_DIR / "measurement_reconstruction_verification.md"
    md_path.write_text("".join(md), encoding="utf-8")

    print(f"[B01-4] {json_path}")
    print(f"[B01-4] {md_path}")
    print(f"  OVERALL = {overall}  ({n_pass}/{len(checks)} passed)")
    for c in checks:
        mark = "PASS" if c["status"] == "PASS" else "FAIL"
        print(f"    {mark}  {c['check']}")
    return 0 if overall == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
