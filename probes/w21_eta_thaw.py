"""W21 Tier 2 -- thaw the Walden kinematic-viscosity exclusion into dynamic eta.

The Walden arm registered `kinematic_thaw` with exactly one dependency:
`data/density_v01.csv`.  That file is on disk now, so the excluded rows can be
folded in as eta = nu * rho under the *frozen* pairing rule of the viscosity
builder (exact 1e-3 K, else nearest within 1.0 K).

This is a data-layer result only.  No model is refitted: 176 rows over 5
compounds cannot carry a channel-level reading, and a refit would mint a new
model version that needs its own pre-registration.
"""

from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from export_results_common import write_json_stable

ROOT = Path(__file__).resolve().parents[1]
THERMOML = ROOT / "data" / "processed" / "viscosity_observations_thermoml.csv"
DENSITY = ROOT / "data" / "density_v01.csv"
JOINT = ROOT / "data" / "processed" / "eta_epsilon_joint_observations.csv"
EXCLUSIONS = ROOT / "data" / "processed" / "eta_epsilon_joint_exclusions.csv"
ROWS_CSV = ROOT / "probes" / "artifacts" / "w21_eta_thawed_rows.csv"
SUMMARY = ROOT / "probes" / "w21_eta_thaw_summary.json"
REPORT = ROOT / "reports" / "w21_eta_thaw.md"

EXACT_T_TOLERANCE_K = 1e-3
NEAREST_T_TOLERANCE_K = 1.0


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, header: tuple[str, ...], rows: list[tuple[object, ...]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(header)
        for row in rows:
            writer.writerow(row)


def build_density_index() -> dict[str, list[tuple[float, float, str]]]:
    index: dict[str, list[tuple[float, float, str]]] = {}
    for row in read_rows(DENSITY):
        unit = str(row.get("density_kg_m3", "")).strip()
        if not unit:
            continue
        index.setdefault(str(row["inchikey"]), []).append(
            (float(row["T_K"]), float(unit), str(row.get("source_doi", "")))
        )
    for values in index.values():
        values.sort()
    return index


def pair_density(index: dict[str, list[tuple[float, float, str]]], key: str, temperature: float):
    candidates = index.get(key)
    if not candidates:
        return None
    for t, rho, doi in candidates:
        if abs(t - temperature) <= EXACT_T_TOLERANCE_K:
            return (rho, doi, t, "exact")
    best = None
    for t, rho, doi in candidates:
        delta = abs(t - temperature)
        if delta <= NEAREST_T_TOLERANCE_K and (best is None or delta < best[0]):
            best = (delta, rho, doi, t)
    if best is None:
        return None
    return (best[1], best[2], best[3], "nearest")


def main() -> int:
    index = build_density_index()
    kinematic = [
        row
        for row in read_rows(THERMOML)
        if str(row.get("viscosity_kinematic_m2_s", "")).strip()
    ]

    rows: list[tuple[object, ...]] = []
    unmatched = 0
    by_pairing: dict[str, int] = {}
    keys: set[str] = set()
    pure = 0
    for row in kinematic:
        key = str(row["inchikey"])
        temperature = float(row["T_K"])
        nu = float(row["viscosity_kinematic_m2_s"])
        paired = pair_density(index, key, temperature)
        if paired is None or not (1e-10 < nu < 1e-3):
            unmatched += 1
            rows.append((key, row.get("name", ""), f"{temperature:.4f}", f"{nu:.8g}", "", "", "", "", "unpaired_no_density_at_temperature"))
            continue
        rho, doi, t_density, kind = paired
        eta = nu * rho
        if not (1e-6 < eta < 1e3):
            unmatched += 1
            rows.append((key, row.get("name", ""), f"{temperature:.4f}", f"{nu:.8g}", f"{rho:.4f}", f"{eta:.8g}", doi, f"{t_density:.4f}", "rejected_out_of_range"))
            continue
        keys.add(key)
        by_pairing[kind] = by_pairing.get(kind, 0) + 1
        if str(row.get("pure_or_mixture")) == "pure":
            pure += 1
        rows.append(
            (
                key,
                row.get("name", ""),
                f"{temperature:.4f}",
                f"{nu:.8g}",
                f"{rho:.10g}",
                f"{eta:.12g}",
                doi,
                f"{t_density:.4f}",
                f"thawed_{kind}",
            )
        )

    write_csv(
        ROWS_CSV,
        ("inchikey", "name", "T_K", "nu_m2_s", "rho_kg_m3", "eta_Pa_s", "density_source_doi", "density_T_K", "status"),
        rows,
    )

    exclusions = read_rows(EXCLUSIONS)
    kinematic_exclusions = [
        row for row in exclusions if str(row.get("reason_code")) == "kinematic_viscosity_not_dynamic"
    ]
    joint = read_rows(JOINT)
    joint_keys = {str(row["inchikey"]) for row in joint}
    newly_covered = sorted(keys - joint_keys)

    paired = sum(by_pairing.values())
    summary = {
        "schema_version": 1,
        "task_id": "week21_w21_2_eta_thaw",
        "title": "Tier 2：Walden kinematic_thaw 解冻（nu x rho -> eta），数据层结清",
        "generated_at_utc": utc_now(),
        "run_mode": "offline",
        "models_fitted": 0,
        "network_calls": 0,
        "writes_any_pool": False,
        "frozen_files_touched": [],
        "inputs": {
            "thermoml_observations": str(THERMOML.relative_to(ROOT)).replace("\\", "/"),
            "density": str(DENSITY.relative_to(ROOT)).replace("\\", "/"),
            "joint": str(JOINT.relative_to(ROOT)).replace("\\", "/"),
            "exclusions": str(EXCLUSIONS.relative_to(ROOT)).replace("\\", "/"),
            "density_sha256": sha256_file(DENSITY),
        },
        "pairing_rule": {
            "exact_tolerance_k": EXACT_T_TOLERANCE_K,
            "nearest_tolerance_k": NEAREST_T_TOLERANCE_K,
            "source": "probes/build_viscosity_v02.py（冻结规则，本件逐字复用）",
        },
        "kinematic_rows_seen": len(kinematic),
        "kinematic_exclusions_registered": len(kinematic_exclusions),
        "kinematic_exclusions_by_dataset": {
            dataset: sum(1 for row in kinematic_exclusions if str(row.get("dataset_id")) == dataset)
            for dataset in sorted({str(row.get("dataset_id")) for row in kinematic_exclusions})
        },
        "kinematic_exclusions_note": "214 = 176 条 thermoml（本件折出）+ 38 条 pubchem 液窗行（不在本件数据源内）",
        "thawed_rows": paired,
        "unmatched_or_rejected": unmatched,
        "by_pairing_kind": dict(sorted(by_pairing.items())),
        "distinct_keys_thawed": len(keys),
        "pure_rows": pure,
        "keys_not_previously_in_joint_table": newly_covered,
        "joint_table_rows": len(joint),
        "joint_table_keys": len(joint_keys),
        "decision": {
            "data_layer": "解冻完成：nu 已按冻结配对规则折成 eta，行表见 w21_eta_thawed_rows.csv",
            "model_layer": "不重拟合。176 行 / 5 个化合物不足以支撑通道级读数，且重拟合会铸出新模型版本，需另立预注册。",
            "walden_kinematic_thaw_flag": "closeable_in_data_layer",
        },
        "boundaries": [
            "不写任何池；折出的行只登记在 artifacts 里，等下一份预注册决定是否并池。",
            "密度配对失败的行如实留在表里（status 列写明原因），不插补。",
            "不引用 Reaxys 数值。",
        ],
        "outputs": {
            "rows": "probes/artifacts/w21_eta_thawed_rows.csv",
            "summary": "probes/w21_eta_thaw_summary.json",
            "report": "reports/w21_eta_thaw.md",
        },
    }
    write_json_stable(SUMMARY, summary)

    lines = [
        "# W21 Tier 2：η 解冻（Walden kinematic_thaw 的依赖已到货）",
        "",
        "Walden 臂把运动黏度行登记为排除态，理由写的是「本仓没有密度可换算」。`data/density_v01.csv` 现在在盘上，所以这一步可以把 nu 按**冻结的配对规则**折成 eta。",
        "",
        "## 1. 结果",
        "",
        "| 项 | 值 |",
        "| --- | --- |",
        f"| 运动黏度行（thermoml 观测表） | {len(kinematic)} |",
        f"| 登记在案的排除行（全部来源） | {len(kinematic_exclusions)}（176 thermoml + 38 pubchem） |",
        f"| **成功折成 eta** | **{paired}** |",
        f"| 未能配对/被范围剔除 | {unmatched} |",
        f"| 涉及化合物 | {len(keys)} |",
        f"| 其中纯组分行 | {pure} |",
        f"| 配对方式 | `{json.dumps(dict(sorted(by_pairing.items())), ensure_ascii=False)}` |",
        f"| 这 5 个键里原本不在联合表内的 | {len(newly_covered)} |",
        "",
        "## 2. 结清到什么程度",
        "",
        f"- **数据层：结清。** `{summary['outputs']['rows']}` 逐行给出 nu、配到的 rho、来源 DOI、以及折出的 eta；配对失败的行留在表里并写明原因，不插补。",
        "- **模型层：明确不做。** 176 行只覆盖 5 个化合物，任何通道级 R² 都会是噪声；而且重拟合等于铸一个新模型版本，必须另立预注册。",
        "",
        "## 3. 边界",
        "",
    ]
    lines += [f"- {item}" for item in summary["boundaries"]]
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")

    print("kinematic seen:", len(kinematic), "thawed:", paired, "unmatched:", unmatched, "keys:", len(keys))
    print("pairing:", dict(sorted(by_pairing.items())), "new keys vs joint:", len(newly_covered))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())