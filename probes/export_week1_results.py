"""Export the important Week 1 probe results to the project output folder."""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
from collections.abc import Mapping, Sequence
from decimal import Decimal
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))

from probes.p1_thermoml_dielectric import _identity

DEFAULT_OUTPUT_DIR = Path(r"E:\Claude Code\电解质ML\成果输出\week1")


def build_week1_report(summary: Mapping[str, object]) -> str:
    family_counts = summary.get("zero_frequency_family_counts_near_center", {})
    decision_status = str(summary.get("decision_status", "provisional"))
    handbook_gate_executed = summary.get("handbook_gate_executed") is True
    gate_label = (
        "P1 provisional decision"
        if decision_status != "archive_verified"
        else "P1 archive-verified decision"
    )
    gate_execution = (
        "P1 handbook gate: EXECUTED"
        if handbook_gate_executed
        else "P1 handbook gate: NOT formally executed"
    )
    return f"""# Week 1 探针结果

## P0

P0 gate: PASS

- RDKit 可解析碳酸乙烯酯 `C1COC(=O)O1`
- Morgan fingerprint 可生成
- 分子结构图已输出

## P1

- {gate_label}: `{summary.get("mainline_decision")}`
- decision_status: `{decision_status}`
- handbook_gate_executed: `{handbook_gate_executed}`
- source_mode: `{summary.get("source_mode")}`
- fallback_query_census: `{summary.get("fallback_query_census")}`
- complete_archive_available: `{summary.get("complete_archive_available")}`
- mainline_gate_population: `{summary.get("mainline_gate_population")}`
- mainline_gate_component_count: {summary.get("mainline_gate_component_count")}
- 下载/扫描文献数: {summary.get("document_count")}
- 含介电观测的文献数: {summary.get("source_documents_with_dielectric_rows")}
- 介电观测行数: {summary.get("observation_rows")}
- 298.15 K ±5 K 观测行数: {summary.get("observations_near_center")}
- 298.15 K ±5 K 零频全部组分唯一化合物: {summary.get("all_component_zero_frequency_components_near_center")}
- 298.15 K ±5 K 纯组分零频化合物（gate population）: {summary.get("pure_zero_frequency_components_near_center")}
- all-component target_family_components_near_center: {summary.get("target_family_components_near_center")}
- pure-component target_family_components_near_center: {summary.get("pure_target_family_components_near_center")}
- 目标家族分布: `{json.dumps(family_counts, ensure_ascii=False)}`
- mainline_decision_basis: {summary.get("mainline_decision_basis")}
- source_limitation: {summary.get("source_limitation")}

## Interpretation

{gate_execution}。NIST 的 2020-09-30 完整快照仍未能取得 HTTP 200 下载：
bulk endpoint 出现重复 HTTP 504，当前 30 秒重试也未收到数据。本结果保留
live NIST API 的 `dielectric` 与 `permittivity` 查询并集回退 census，不能冒充
完整 2020 历史快照，也不能宣布执行手册 gate 已正式完成。

按回退 census 的 provisional 统计，near-298 K 零频全部组分有 124 个唯一化合物，
但正式 gate population 只用纯组分零频观测，为 100 个；混合物 partner 不计入。
因此当前 `dielectric_viscosity_joint` 只是 provisional decision。目标电池溶剂家族
覆盖仍然偏窄，后续必须在完整 archive 可用时重跑并复核。

## Files

- `p0_ec_molecule.png`: P0 分子结构图
- `00_sanity_check.ipynb`: P0 notebook
- `dielectric_raw.csv`: P1 介电观测原始提取表
- `p1_summary.json`: P1 机器可读统计
- `zero_frequency_near_298_compounds.csv`: 近似室温零频唯一化合物清单
- `dielectric_distribution.png`: NIST 介电观测分布
- `family_coverage.png`: 溶剂家族覆盖
- `p1_eda.ipynb`: P1 可执行 EDA notebook
"""


def write_unique_compounds_csv(
    observations_path: Path,
    output_path: Path,
    *,
    temperature_center: Decimal = Decimal("298.15"),
    temperature_tolerance: Decimal = Decimal(5),
) -> None:
    unique: dict[str, dict[str, object]] = {}
    with observations_path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if row["property_family"] != "zero_frequency":
                continue
            temperature_text = row.get("temperature_k", "")
            if not temperature_text:
                continue
            temperature = Decimal(temperature_text)
            if abs(temperature - temperature_center) > temperature_tolerance:
                continue
            components = json.loads(row["components_json"])
            for component in components:
                identity = _identity(component)
                record = unique.setdefault(
                    identity,
                    {
                        "identity": identity,
                        "name": component["name"],
                        "formula": component["formula"],
                        "standard_inchi_key": component["standard_inchi_key"],
                        "cas_registry_number": component["cas_registry_number"],
                        "observations_near_298": 0,
                        "appears_in_pure_component_dataset": False,
                    },
                )
                record["observations_near_298"] = int(record["observations_near_298"]) + 1
                if row.get("is_pure") == "True":
                    record["appears_in_pure_component_dataset"] = True

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "identity",
        "name",
        "formula",
        "standard_inchi_key",
        "cas_registry_number",
        "observations_near_298",
        "appears_in_pure_component_dataset",
    ]
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(
            sorted(unique.values(), key=lambda record: str(record["name"]).casefold())
        )


def export_week1_results(output_dir: Path) -> None:
    summary_path = REPOSITORY_ROOT / "probes" / "p1_summary.json"
    observations_path = REPOSITORY_ROOT / "data" / "processed" / "dielectric_raw.csv"
    artifacts_dir = REPOSITORY_ROOT / "probes" / "artifacts"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))

    output_dir.mkdir(parents=True, exist_ok=True)
    copies = {
        artifacts_dir / "p0_ec_molecule.png": output_dir / "p0_ec_molecule.png",
        summary_path: output_dir / "p1_summary.json",
        observations_path: output_dir / "dielectric_raw.csv",
        artifacts_dir / "dielectric_distribution.png": output_dir
        / "dielectric_distribution.png",
        artifacts_dir / "family_coverage.png": output_dir / "family_coverage.png",
        REPOSITORY_ROOT / "notebooks" / "00_sanity_check.ipynb": output_dir
        / "00_sanity_check.ipynb",
        REPOSITORY_ROOT / "probes" / "p1_eda.ipynb": output_dir / "p1_eda.ipynb",
    }
    for source, destination in copies.items():
        shutil.copy2(source, destination)

    write_unique_compounds_csv(
        observations_path,
        output_dir / "zero_frequency_near_298_compounds.csv",
    )
    (output_dir / "week1_report.md").write_text(
        build_week1_report(summary),
        encoding="utf-8",
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args(argv)
    export_week1_results(args.output_dir)
    print(args.output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
