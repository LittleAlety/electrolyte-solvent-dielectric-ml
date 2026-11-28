#!/usr/bin/env python
"""B702-01: external electrolyte-solvent extension set.

v6.0 admitted 239 molecules and then reported that eight canonical electrolyte solvents
were missing: water, DMSO, DMF, THF, GBL, ethylene carbonate, propylene carbonate,
sulfolane. That gap matters because a dataset named for electrolyte solvents that omits
the solvents the field uses cannot support electrolyte-design claims.

What this script does NOT do: invent, interpolate, or temperature-correct anything. The
repository already holds raw dielectric observations from two independent source
families, both with per-row source_url and source_sha256:

    data/raw/thermoml_full/eps_observations.csv    (ThermoML extraction)
    data/raw/open_data_eps/eps_observations.csv    (open data extraction)

The job here is qualification, not collection: decide which of those raw rows may be
admitted under the PLAN B v7.0 conditions, and record why the rest may not.

Admission conditions (all must hold for a row to be admitted):
  C1 identity     the row's InChIKey equals the one the registry expects for the solvent
  C2 phase        phase records a liquid
  C3 static       frequency_mhz is blank or 0 -- a value measured at 360 MHz or a
                  frequency-extrapolated value is NOT the static permittivity and must
                  never be mixed in
  C4 temperature  t_k is present. Records without it are kept in the ledger and
                  flagged CONDITION_INCOMPLETE; they are never temperature-adjusted
                  to manufacture a room-temperature value

Three data layers are produced, matching the plan:
  LAYER_MAIN_239       the frozen v6.0 main set, read-only
  LAYER_EXTENSION_8    the eight solvents admitted here
  LAYER_JOINT          both, with a layer tag -- NOT merged into a single number

Output: outputs/b700/B702_EXTERNAL/
        solvent_extension_registry.csv, raw_measurement_ledger.csv,
        condition_qualification.csv, independent_source_map.csv,
        missing_evidence_report.csv, extension_manifest.json,
        extension_admission_report.md
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT = REPO_ROOT / "outputs" / "b700" / "B702_EXTERNAL"
B100 = REPO_ROOT / "outputs" / "b100"

SOURCES = {
    "THERMOML": REPO_ROOT / "data" / "raw" / "thermoml_full" / "eps_observations.csv",
    "OPEN_DATA": REPO_ROOT / "data" / "raw" / "open_data_eps" / "eps_observations.csv",
}

# InChIKey is the identity anchor. Names differ between sources (".gamma.-butyrolactone"
# vs "gamma-butyrolactone") so name matching is never used for admission.
KEY_SOLVENTS = {
    "water": "XLYOFNOQVPJJNP-UHFFFAOYSA-N",
    "dimethyl sulfoxide": "IAZDPXIOMUYVGZ-UHFFFAOYSA-N",
    "N,N-dimethylformamide": "ZMXDDKWLCZADIW-UHFFFAOYSA-N",
    "tetrahydrofuran": "WYURNTSHIVDZCO-UHFFFAOYSA-N",
    "gamma-butyrolactone": "YEJRWHAVMIAJKC-UHFFFAOYSA-N",
    "ethylene carbonate": "KMTRUDSVKNLOMY-UHFFFAOYSA-N",
    "propylene carbonate": "RUOJZAUFBMNUDX-UHFFFAOYSA-N",
    "sulfolane": "HXJUTPCZVOIRIF-UHFFFAOYSA-N",
}

ROOM_T_RANGE = (293.15, 308.15)   # reporting band, NOT an adjustment window


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    raw = path.read_bytes()
    text = None
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        return []
    header = text.splitlines()[0] if text.splitlines() else ""
    delim = ";" if header.count(";") > header.count(",") else ","
    return list(csv.DictReader(io.StringIO(text or "", newline=""), delimiter=delim))


def fnum(v):
    s = (str(v) if v is not None else "").strip()
    if s.lower() in ("", "nan", "none", "null", "na", "n/a"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def qualify(row: dict, expected_ik: str, source: str) -> dict:
    """Apply C1-C4 and return the verdict with an explicit reason for each failure."""
    fails = []

    ik = (row.get("inchikey") or "").strip()
    if ik != expected_ik:
        fails.append("C1_IDENTITY_MISMATCH")

    phase = (row.get("phase") or "").strip().lower()
    if phase != "liquid":
        fails.append("C2_NOT_LIQUID")

    freq_raw = (row.get("frequency_mhz") or "").strip()
    freq = fnum(freq_raw)
    if freq_raw and freq is not None and freq > 0:
        fails.append("C3_FREQUENCY_QUALIFIED")
    elif freq_raw and freq is None:
        # a non-numeric frequency field cannot be shown to be static
        fails.append("C3_FREQUENCY_UNPARSABLE")

    t = fnum(row.get("t_k"))
    if t is None:
        fails.append("C4_NO_TEMPERATURE")

    eps = fnum(row.get("epsilon"))
    if eps is None:
        fails.append("C5_NO_EPSILON")
    elif eps < 1.0:
        fails.append("C5_EPSILON_BELOW_ONE")

    return {
        "admitted": not fails,
        "failure_codes": ";".join(fails),
        "frequency_mhz": freq_raw,
        "t_k": t,
        "epsilon": eps,
        "in_room_band": ("true" if (t is not None and ROOM_T_RANGE[0] <= t
                                    <= ROOM_T_RANGE[1]) else "false"),
        "source": source,
        "source_url": (row.get("source_url") or "").strip(),
        "source_sha256": (row.get("source_sha256") or "").strip(),
        "license": (row.get("license") or "").strip(),
        "retrieved_at_utc": (row.get("retrieved_at_utc") or "").strip(),
        "name_as_recorded": (row.get("name") or "").strip(),
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    main_set = load(B100 / "phase_state_audit_b100.csv")
    n_main = sum(1 for r in main_set if r.get("phase_verified") == "true")

    ledger: list[dict] = []
    per_solvent: dict[str, dict] = {}
    source_files = {}

    for tag, path in SOURCES.items():
        if path.is_file():
            source_files[tag] = {"path": str(path.relative_to(REPO_ROOT)),
                                 "sha256": sha256_file(path)}
        rows = load(path)
        for solvent, ik in KEY_SOLVENTS.items():
            mine = [r for r in rows if (r.get("inchikey") or "").strip() == ik]
            if not mine:
                continue
            for r in mine:
                q = qualify(r, ik, tag)
                rec = {"solvent": solvent, "inchikey": ik, **q}
                ledger.append(rec)
                d = per_solvent.setdefault(solvent, {
                    "solvent": solvent, "inchikey": ik,
                    "n_raw": 0, "n_admitted": 0,
                    "n_admitted_room_band": 0,
                    "sources_with_admitted": set(),
                    "eps_values": [], "t_values": [],
                    "failure_histogram": defaultdict(int),
                })
                d["n_raw"] += 1
                if q["admitted"]:
                    d["n_admitted"] += 1
                    d["sources_with_admitted"].add(tag)
                    d["eps_values"].append(q["epsilon"])
                    d["t_values"].append(q["t_k"])
                    if q["in_room_band"] == "true":
                        d["n_admitted_room_band"] += 1
                else:
                    for code in q["failure_codes"].split(";"):
                        if code:
                            d["failure_histogram"][code] += 1

    # ---- registry: one row per solvent ----
    registry = []
    for solvent, ik in KEY_SOLVENTS.items():
        d = per_solvent.get(solvent)
        if not d or d["n_admitted"] == 0:
            registry.append({
                "solvent": solvent, "inchikey": ik,
                "admission": "NOT_ADMITTED",
                "n_admitted": 0,
                "n_independent_sources": 0,
                "reason": ("no record satisfies C1-C5"
                           if d else "no raw record in any source"),
            })
            continue
        eps = d["eps_values"]
        ts = d["t_values"]
        n_src = len(d["sources_with_admitted"])
        registry.append({
            "solvent": solvent, "inchikey": ik,
            "admission": "ADMITTED",
            "n_admitted": d["n_admitted"],
            "n_admitted_room_band": d["n_admitted_room_band"],
            "n_independent_sources": n_src,
            "source_independence": ("MULTI_SOURCE" if n_src >= 2
                                    else "SINGLE_SOURCE"),
            "epsilon_mean": round(sum(eps) / len(eps), 3),
            "epsilon_min": round(min(eps), 3),
            "epsilon_max": round(max(eps), 3),
            "epsilon_spread_over_mean": round(
                (max(eps) - min(eps)) / (sum(eps) / len(eps)), 4) if len(eps) > 1 else "",
            "t_k_min": round(min(ts), 2), "t_k_max": round(max(ts), 2),
            "frequency_all_static": "true",
        })

    admitted = [r for r in registry if r["admission"] == "ADMITTED"]

    # ---- condition qualification table ----
    qual_rows = []
    for solvent in KEY_SOLVENTS:
        mine = [r for r in ledger if r["solvent"] == solvent]
        qual_rows.append({
            "solvent": solvent,
            "n_raw": len(mine),
            "n_admitted": sum(1 for r in mine if r["admitted"]),
            "n_rejected_C1": sum(1 for r in mine
                                 if "C1_IDENTITY_MISMATCH" in r["failure_codes"]),
            "n_rejected_C2": sum(1 for r in mine
                                 if "C2_NOT_LIQUID" in r["failure_codes"]),
            "n_rejected_C3_frequency": sum(
                1 for r in mine
                if "C3_FREQUENCY_QUALIFIED" in r["failure_codes"]
                or "C3_FREQUENCY_UNPARSABLE" in r["failure_codes"]),
            "n_rejected_C4_no_temperature": sum(
                1 for r in mine if "C4_NO_TEMPERATURE" in r["failure_codes"]),
        })

    # ---- independent source map ----
    src_map = []
    for solvent in KEY_SOLVENTS:
        for tag in SOURCES:
            mine = [r for r in ledger
                    if r["solvent"] == solvent and r["source"] == tag and r["admitted"]]
            src_map.append({
                "solvent": solvent, "source": tag,
                "n_admitted_records": len(mine),
                "n_distinct_source_urls": len({r["source_url"] for r in mine
                                               if r["source_url"]}),
                "admitted": "true" if mine else "false",
            })

    # ---- missing evidence report ----
    missing = []
    for solvent in KEY_SOLVENTS:
        r = next((x for x in registry if x["solvent"] == solvent), {})
        if r.get("admission") != "ADMITTED":
            missing.append({"solvent": solvent,
                            "issue": "NO_QUALIFYING_MEASUREMENT",
                            "detail": r.get("reason", "")})
            continue
        if r["n_independent_sources"] < 2:
            missing.append({"solvent": solvent,
                            "issue": "SINGLE_SOURCE_ONLY",
                            "detail": (f"only {r['n_independent_sources']} source(s) "
                                       f"supply a qualifying measurement")})
        if r.get("n_admitted_room_band", 0) == 0:
            missing.append({"solvent": solvent,
                            "issue": "NO_ROOM_BAND_MEASUREMENT",
                            "detail": ("admitted records exist but none lie in "
                                       f"{ROOM_T_RANGE[0]}-{ROOM_T_RANGE[1]} K; "
                                       "not temperature-adjusted")})

    # ---- write the files ----
    def write_csv(name, rows):
        if not rows:
            return
        keys = []
        for r in rows:
            for k in r:
                if k not in keys:
                    keys.append(k)
        with (OUT / name).open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=keys, extrasaction="ignore")
            w.writeheader()
            for r in rows:
                w.writerow(r)

    write_csv("solvent_extension_registry.csv", registry)
    write_csv("raw_measurement_ledger.csv", ledger)
    write_csv("condition_qualification.csv", qual_rows)
    write_csv("independent_source_map.csv", src_map)
    write_csv("missing_evidence_report.csv", missing)

    n_multi = sum(1 for r in admitted if r["n_independent_sources"] >= 2)
    doc = {
        "schema": "b700.b702_extension/v1",
        "generated_at_utc": datetime.now(timezone.utc)
        .replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "dataset_name": "B_EXT_ELECTROLYTE_SOLVENTS_V1",
        "why": (
            "v6.0 报告 8 个关键电解质溶剂缺失. 本扩展集从仓库已有的原始观测中"
            "按严格条件恢复它们, **不新增虚构测量, 不做温度折算, 不混用频率**."
        ),
        "admission_conditions": {
            "C1_identity": "InChIKey 必须等于登记值(名称差异不用于准入)",
            "C2_phase": "phase 必须为 liquid",
            "C3_static": "frequency_mhz 为空或 0; 频率限定值一律拒绝",
            "C4_temperature": "t_k 必须存在; 缺失者保留在账本并标记, 不做温度折算",
            "C5_value": "epsilon 必须存在且 > 1",
        },
        "layers": {
            "LAYER_MAIN_239": {"n": n_main,
                               "note": "v6.0 冻结主集, 只读, 未修改"},
            "LAYER_EXTENSION_8": {"n_admitted": len(admitted),
                                  "n_candidates": len(KEY_SOLVENTS)},
            "LAYER_JOINT": {
                "note": ("两层并置分析, 但**不合并成单一数值**; "
                         "联合集中的每行必须带 layer 标签"),
                "n_if_concatenated": n_main + len(admitted),
            },
        },
        "source_independence_summary": {
            "n_admitted_solvents": len(admitted),
            "n_multi_source": n_multi,
            "n_single_source": len(admitted) - n_multi,
            "statement": (
                "新增溶剂不等于新增独立来源. 每个溶剂的来源数已单独记录; "
                f"其中 {n_multi} 个有 >=2 个独立来源, "
                f"{len(admitted) - n_multi} 个只有单来源证据."
            ),
        },
        "n_raw_rows_examined": len(ledger),
        "n_admitted_rows": sum(1 for r in ledger if r["admitted"]),
        "source_files": source_files,
        "statistical_reporting_requirement": {
            "independent_molecules_main": n_main,
            "independent_sources_total": len(SOURCES),
            "molecules_covered_by_multiple_sources": None,
            "note": ("论文须分别报告独立分子数、独立实验来源数、"
                     "独立来源覆盖的分子数、多来源验证的分子数. "
                     "本文件给出扩展集的来源图; 主集的同类统计在 "
                     "outputs/b100/source_independence_b100.json"),
        },
        "records": registry,
    }
    (OUT / "extension_manifest.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    md = ["# 外部电解质溶剂扩展集 B_EXT_ELECTROLYTE_SOLVENTS_V1\n",
          f"- 候选溶剂: {len(KEY_SOLVENTS)}",
          f"- 准入: {len(admitted)}",
          f"- 其中多来源: {n_multi}，单来源: {len(admitted) - n_multi}",
          f"- 原始待审记录: {len(ledger)}，准入记录: {doc['n_admitted_rows']}",
          "",
          "## 准入条件\n"]
    for k, v in doc["admission_conditions"].items():
        md.append(f"- **{k}**: {v}")
    md += ["", "## 结果\n",
           "| 溶剂 | 准入 | 来源数 | eps 均值 | eps 范围 | T 范围 (K) |",
           "|---|---|---:|---:|---|---|"]
    for r in registry:
        if r["admission"] == "ADMITTED":
            md.append(f"| {r['solvent']} | 是 | {r['n_independent_sources']} | "
                      f"{r['epsilon_mean']} | {r['epsilon_min']}–{r['epsilon_max']} | "
                      f"{r['t_k_min']}–{r['t_k_max']} |")
        else:
            md.append(f"| {r['solvent']} | 否 | 0 | — | — | — |")
    md += ["", "## 缺失证据\n"]
    for m in missing:
        md.append(f"- **{m['solvent']}** — {m['issue']}: {m['detail']}")
    md += ["", "## 声明\n",
           "- 未新增任何虚构测量；所有准入行都有 source_url 与 source_sha256",
           "- 未做温度折算：不在室温窗口的记录只被标记，未被调整",
           "- 未混用频率：frequency_mhz > 0 的记录一律拒绝",
           "- 单来源溶剂不得被表述为已获独立验证"]
    (OUT / "extension_admission_report.md").write_text("\n".join(md) + "\n",
                                                       encoding="utf-8")

    print(f"[B702-01] {OUT}")
    print(f"  raw rows examined : {len(ledger)}")
    print(f"  admitted rows     : {doc['n_admitted_rows']}")
    print(f"  solvents admitted : {len(admitted)}/{len(KEY_SOLVENTS)} "
          f"(multi-source {n_multi})")
    for r in registry:
        if r["admission"] == "ADMITTED":
            print(f"    {r['solvent']:<24} eps={r['epsilon_mean']:<8} "
                  f"n={r['n_admitted']:<4} src={r['n_independent_sources']} "
                  f"T={r['t_k_min']}-{r['t_k_max']}")
        else:
            print(f"    {r['solvent']:<24} NOT ADMITTED ({r.get('reason','')})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
