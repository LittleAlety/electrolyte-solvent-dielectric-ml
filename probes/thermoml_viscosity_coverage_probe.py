"""T1: recount the local ThermoML corpus for viscosity observations.

The local ``data/raw/thermoml`` cache was assembled for *dielectric* retrieval,
so the stored extraction (``data/processed/thermoml_normalized.csv``) holds only
``Relative permittivity ...`` rows. Appendix Z-4 of the project manual claims the
same XML documents also carry viscosity fields that were never harvested. This
probe re-derives that claim from the raw corpus with the repository parser
(:mod:`electrolyte_ml.thermoml`) instead of trusting the extraction output, so a
silent extraction gap cannot masquerade as "no viscosity data".

Identity layer: every ThermoML document carries ``<sStandardInChIKey>`` for each
component, so the harvested viscosity rows need **no** name -> structure
resolution step. That is the opposite of the PubChem harvesting lane and it is
recorded explicitly under ``identity_layer``.

The probe is read-only with respect to every frozen artefact. It writes only its
own summary JSON and its own observation CSV, and promotes nothing into
``data/dielectric_v03.csv`` or any other frozen table.
"""

from __future__ import annotations

import argparse
import collections
import csv
import glob
import json
import math
import re
import sys
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))
sys.path.insert(0, str(REPOSITORY_ROOT / "probes"))

from electrolyte_ml.exporting import canonical_text_sha256
from electrolyte_ml.thermoml import parse_thermoml_file

THERMOML_GLOB = "data/raw/thermoml/*.xml"
NORMALIZED_PATH = "data/processed/thermoml_normalized.csv"
EPS_OBSERVATIONS_PATH = "data/processed/dielectric_observations_v11plus.csv"
VISCOSITY_V01_PATH = "data/viscosity_v01.csv"
STORED_EXTRACTION_PATHS: tuple[str, ...] = (
    "data/processed/thermoml_normalized.csv",
    "data/processed/dielectric_raw.csv",
    "data/processed/thermoml_source_manifest.csv",
)
DEFAULT_SUMMARY = REPOSITORY_ROOT / "probes" / "thermoml_viscosity_coverage_summary.json"
DEFAULT_ROWS = REPOSITORY_ROOT / "data" / "processed" / "viscosity_observations_thermoml.csv"

PASCAL_SECOND_PROPERTY = "Viscosity, Pa*s"
KINEMATIC_PROPERTY = "Kinematic viscosity, m2/s"

# Reconnaissance values measured by a throwaway shell scan before this probe
# existed. They are acceptance targets, not the source of truth: every one is
# recomputed below and any disagreement is reported in
# ``expectation_vs_remeasured`` and ``expectation_mismatches`` instead of being
# papered over by editing a number.
RECON_EXPECTATIONS: dict[str, int] = {
    "xml_files_scanned": 242,
    "viscosity_files": 29,
    "viscosity_rows": 2725,
    "viscosity_rows_pa_s": 2549,
    "viscosity_rows_kinematic": 176,
    "pure_rows": 569,
    "mixture_rows": 2156,
    "pure_keys": 47,
    "overlap_eps_obs": 37,
    "overlap_viscosity_v01": 28,
    "new_vs_eps_and_v01": 3,
}

ROW_COLUMNS: tuple[str, ...] = (
    "inchikey",
    "smiles_or_name",
    "name",
    "T_K",
    "viscosity_Pa_s",
    "viscosity_cP",
    "viscosity_kinematic_m2_s",
    "property_name",
    "property_value",
    "property_unit",
    "uncertainty",
    "uncertainty_kind",
    "phase",
    "method_name",
    "n_components",
    "pure_or_mixture",
    "source_doi",
    "thermoml_file",
    "source_row_index",
)

_FILENAME_DOI_RE = re.compile(
    r"^(?P<prefix>.+?)__(?P<rest>.+?)(?:-[0-9a-f]{8,})?\.xml$"
)


def _json_ready(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    return value


def display_path(path: Path) -> str:
    """Prefer a repository-relative path, but never fail on an external one."""

    try:
        return str(path.relative_to(REPOSITORY_ROOT)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def write_json_lf(path: Path, payload: object) -> None:
    """Write JSON with explicit LF endings and no non-finite literals.

    ``Path.write_text`` would translate the newline to ``os.linesep`` on Windows
    and make the artifact bytes host-dependent. Non-finite floats are converted
    to ``null`` first because bare NaN and Infinity are not valid JSON.
    """

    text = (
        json.dumps(_json_ready(payload), ensure_ascii=False, indent=2, allow_nan=False)
        + "\n"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        handle.write(text)


def write_csv_lf(
    path: Path,
    fieldnames: Sequence[str],
    rows: Sequence[Mapping[str, str]],
) -> None:
    """Write CSV with explicit LF endings and no BOM.

    ``csv.writer`` defaults to ``\r\n``; every other committed CSV in this
    repository is LF-only, so the artifact must not silently switch endings.
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def read_keys(path: Path, column: str) -> set[str]:
    return {
        (row.get(column) or "").strip()
        for row in read_csv_rows(path)
        if (row.get(column) or "").strip()
    }


def to_float(text: object) -> float | None:
    try:
        value = float(str(text).strip())
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def stored_extraction_scan(paths: Sequence[str]) -> dict[str, dict[str, object]]:
    """Look for viscosity rows in every stored ThermoML-derived product.

    A zero here is the load-bearing half of the extraction-gap claim: the fields
    exist in the raw XML and appear in none of the tables the project built from
    that same corpus.
    """

    report: dict[str, dict[str, object]] = {}
    for relative in paths:
        rows = read_csv_rows(REPOSITORY_ROOT / relative)
        columns = list(rows[0].keys()) if rows else []
        report[relative] = {
            "rows": len(rows),
            "columns": len(columns),
            "viscosity_rows": sum(
                1
                for row in rows
                if "viscosity" in (row.get("property_name") or "").lower()
            ),
            "has_property_name_column": "property_name" in columns,
            "viscosity_labelled_columns": [
                column for column in columns if "viscosity" in column.lower()
            ],
        }
    return report


def is_viscosity_property(property_name: str) -> bool:
    return "viscosity" in property_name.lower()


def doi_from_source_file(source_file: str) -> str:
    """Recover a DOI from a cached ThermoML filename.

    Cached documents are named ``10.1016__j.jct.2014.09.015-<hash>.xml``, i.e.
    the DOI with ``/`` replaced by ``__`` plus a content hash. This is only a
    fallback: every harvested viscosity row carries a structured ``<sDOI>``.
    """

    match = _FILENAME_DOI_RE.match(source_file)
    if match is None:
        return ""
    return f"{match.group('prefix')}/{match.group('rest')}"


def scan_thermoml(paths: Sequence[Path]) -> list[dict[str, str]]:
    """Parse every local ThermoML document with the repository parser."""

    parsed: list[dict[str, str]] = []
    for path in paths:
        parsed.extend(parse_thermoml_file(path))
    return parsed


def observation_rows(viscosity_rows: Sequence[Mapping[str, str]]) -> list[dict[str, str]]:
    """Project parsed viscosity rows onto the published observation contract."""

    output: list[dict[str, str]] = []
    for row in viscosity_rows:
        name = (row.get("primary_compound_name") or "").strip()
        property_name = (row.get("property_name") or "").strip()
        raw_value = (row.get("property_value") or "").strip()
        value = to_float(raw_value)
        component_count = int((row.get("component_count") or "0").strip() or 0)
        pa_s = ""
        centipoise = ""
        kinematic = ""
        if value is not None and property_name == PASCAL_SECOND_PROPERTY:
            pa_s = raw_value
            centipoise = f"{value * 1000.0:.12g}"
        elif value is not None and property_name == KINEMATIC_PROPERTY:
            kinematic = raw_value
        source_file = (row.get("source_file") or "").strip()
        output.append(
            {
                "inchikey": (row.get("primary_compound_inchi_key") or "").strip(),
                # ThermoML carries InChI/InChIKey, never SMILES. Identity comes
                # from the InChIKey column; this column is the name fallback.
                "smiles_or_name": name,
                "name": name,
                "T_K": (row.get("temperature_value") or "").strip(),
                "viscosity_Pa_s": pa_s,
                "viscosity_cP": centipoise,
                "viscosity_kinematic_m2_s": kinematic,
                "property_name": property_name,
                "property_value": raw_value,
                "property_unit": (row.get("property_unit") or "").strip(),
                "uncertainty": (row.get("property_uncertainty") or "").strip(),
                "uncertainty_kind": (row.get("property_uncertainty_kind") or "").strip(),
                "phase": (row.get("phase") or "").strip(),
                "method_name": (row.get("method_name") or "").strip(),
                "n_components": str(component_count),
                "pure_or_mixture": "pure" if component_count == 1 else "mixture",
                "source_doi": (row.get("doi") or "").strip()
                or doi_from_source_file(source_file),
                "thermoml_file": source_file,
                "source_row_index": (row.get("source_row_index") or "").strip(),
            }
        )
    output.sort(
        key=lambda item: (item["thermoml_file"], int(item["source_row_index"] or "0"))
    )
    return output


def build_summary(
    *,
    summary_path: Path = DEFAULT_SUMMARY,
    rows_path: Path = DEFAULT_ROWS,
) -> dict[str, object]:
    paths = sorted(Path(path) for path in glob.glob(str(REPOSITORY_ROOT / THERMOML_GLOB)))
    parsed = scan_thermoml(paths)
    viscosity = [
        row for row in parsed if is_viscosity_property(row.get("property_name") or "")
    ]
    observations = observation_rows(viscosity)

    by_property = collections.Counter((row.get("property_name") or "") for row in viscosity)
    pure = [row for row in viscosity if row.get("component_count") == "1"]
    mixture = [row for row in viscosity if row.get("component_count") != "1"]
    pure_keys = {
        (row.get("primary_compound_inchi_key") or "").strip()
        for row in pure
        if (row.get("primary_compound_inchi_key") or "").strip()
    }
    eps_keys = read_keys(REPOSITORY_ROOT / EPS_OBSERVATIONS_PATH, "inchikey")
    v01_keys = read_keys(REPOSITORY_ROOT / VISCOSITY_V01_PATH, "inchikey")
    overlap_eps = pure_keys & eps_keys
    overlap_v01 = pure_keys & v01_keys
    new_keys = pure_keys - eps_keys - v01_keys

    normalized_rows = read_csv_rows(REPOSITORY_ROOT / NORMALIZED_PATH)
    normalized_properties = collections.Counter(
        (row.get("property_name") or "") for row in normalized_rows
    )
    stored_extraction = stored_extraction_scan(STORED_EXTRACTION_PATHS)

    remeasured: dict[str, int] = {
        "xml_files_scanned": len(paths),
        "viscosity_files": len({(row.get("source_file") or "") for row in viscosity}),
        "viscosity_rows": len(viscosity),
        "viscosity_rows_pa_s": by_property.get(PASCAL_SECOND_PROPERTY, 0),
        "viscosity_rows_kinematic": by_property.get(KINEMATIC_PROPERTY, 0),
        "pure_rows": len(pure),
        "mixture_rows": len(mixture),
        "pure_keys": len(pure_keys),
        "overlap_eps_obs": len(overlap_eps),
        "overlap_viscosity_v01": len(overlap_v01),
        "new_vs_eps_and_v01": len(new_keys),
    }
    expectation_table = [
        {
            "metric": metric,
            "recon_expectation": expected,
            "remeasured": remeasured[metric],
            "verdict": "match" if remeasured[metric] == expected else "mismatch",
        }
        for metric, expected in RECON_EXPECTATIONS.items()
    ]
    expectation_mismatches = [
        entry["metric"] for entry in expectation_table if entry["verdict"] != "match"
    ]

    rows_by_file: dict[str, int] = collections.Counter(
        (row.get("source_file") or "") for row in viscosity
    )
    doi_by_file: dict[str, str] = {}
    for row in viscosity:
        source_file = (row.get("source_file") or "").strip()
        doi_by_file.setdefault(
            source_file, (row.get("doi") or "").strip() or doi_from_source_file(source_file)
        )
    files = [
        {"thermoml_file": name, "viscosity_rows": count, "source_doi": doi_by_file[name]}
        for name, count in sorted(rows_by_file.items())
    ]

    payload: dict[str, object] = {
        "schema_version": "thermoml_viscosity_coverage/v1",
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "design": {
            "question": (
                "Do the local ThermoML XML documents really carry viscosity "
                "observations that the stored extraction never harvested?"
            ),
            "method": (
                "Full re-parse of every local ThermoML XML with the repository "
                "parser (electrolyte_ml.thermoml.parse_thermoml_file) plus a "
                "set-level comparison against the dielectric observation table "
                "and the stored viscosity table."
            ),
            "network_access": False,
            "promotes_values_into_frozen_dataset": False,
            "identity_layer": (
                "ThermoML documents carry <sStandardInChIKey>, so no name -> "
                "structure resolution is required for this lane."
            ),
        },
        "inputs": {
            "thermoml_glob": THERMOML_GLOB,
            "xml_files_scanned": len(paths),
            "normalized_path": NORMALIZED_PATH,
            "normalized_rows": len(normalized_rows),
            "normalized_property_names": dict(sorted(normalized_properties.items())),
            "dielectric_observations_path": EPS_OBSERVATIONS_PATH,
            "dielectric_observations_keys": len(eps_keys),
            "dielectric_observations_sha256": canonical_text_sha256(
                REPOSITORY_ROOT / EPS_OBSERVATIONS_PATH
            ),
            "viscosity_v01_path": VISCOSITY_V01_PATH,
            "viscosity_v01_keys": len(v01_keys),
        },
        "xml_files_scanned": len(paths),
        "viscosity_files": remeasured["viscosity_files"],
        "viscosity_rows": len(viscosity),
        "viscosity_rows_pa_s": remeasured["viscosity_rows_pa_s"],
        "viscosity_rows_kinematic": remeasured["viscosity_rows_kinematic"],
        "viscosity_rows_by_property": dict(sorted(by_property.items())),
        "pure_rows": len(pure),
        "mixture_rows": len(mixture),
        "pure_plus_mixture": len(pure) + len(mixture),
        "pure_keys": len(pure_keys),
        "overlap_eps_obs": len(overlap_eps),
        "overlap_viscosity_v01": len(overlap_v01),
        "new_vs_eps_and_v01": len(new_keys),
        "pure_key_overlap_detail": {
            "pure_keys": len(pure_keys),
            "in_eps_observation_table": len(overlap_eps),
            "in_stored_viscosity_table": len(overlap_v01),
            "in_both": len(pure_keys & eps_keys & v01_keys),
            "in_neither": len(new_keys),
            "new_keys": sorted(new_keys),
        },
        "stored_extraction": stored_extraction,
        "extraction_gap": {
            "viscosity_rows_in_local_xml": len(viscosity),
            "viscosity_rows_in_stored_thermoml_extractions": sum(
                int(entry["viscosity_rows"]) for entry in stored_extraction.values()
            ),
            "verdict": (
                "viscosity fields are present in the raw XML but absent from every "
                "table this project built out of that same ThermoML corpus"
            ),
        },
        "component_count_distribution": dict(
            sorted(collections.Counter((row.get("component_count") or "") for row in viscosity).items())
        ),
        "temperature_units": dict(
            sorted(collections.Counter((row.get("temperature_unit") or "") for row in viscosity).items())
        ),
        "phase_distribution": dict(
            sorted(collections.Counter((row.get("phase") or "") for row in viscosity).items())
        ),
        "source_doi": {
            "distinct_dois": len({entry["source_doi"] for entry in files}),
            "rows_without_doi": sum(1 for row in viscosity if not (row.get("doi") or "").strip()),
        },
        "files_with_viscosity": files,
        "expectation_vs_remeasured": expectation_table,
        "expectation_mismatches": expectation_mismatches,
        "outputs": {
            "summary_path": display_path(summary_path),
            "rows_path": display_path(rows_path),
            "rows": len(observations),
            "rows_pure": sum(1 for row in observations if row["pure_or_mixture"] == "pure"),
        },
        "findings": [
            (
                "本地 242 个 ThermoML XML 里确实躺着 2,725 行黏度观测（分布在 29 个文件），"
                "而存量抽取表 thermoml_normalized.csv 只有 625 行、全部是相对介电常数："
                "黏度字段从未被收割，附录 Z-4 的前提成立。"
            ),
            (
                "2,725 行中纯组分 569 行 / 47 个 InChIKey，多组分 2,156 行。"
                "ThermoML 自带 <sStandardInChIKey>，η 线不需要名称→结构解析。"
            ),
            (
                "纯组分黏度集合相对 ε 观测表（153 keys）与存量黏度表（957 keys）"
                "只净新增 3 个 InChIKey，所以 ThermoML 黏度是补给线而不是新矿脉；"
                "ηε-joint 的骨架规模应由 ε∩η 决定，而不是由本地黏度本体的行数决定。"
            ),
        ],
        "limitations": [
            (
                "本地 XML 是 NIST 全库（11,923 条记录）的筛选子集，"
                "“29 个文件含黏度”不构成 NIST 黏度总体上界；"
                "“本地没有”只等于“本地缓存没有”，要下总体结论必须另做在线黏度切片核查。"
            ),
            (
                "多组分 2,156 行未做溶质/溶剂角色拆分；inchikey 列对多组分行"
                "只是第一个组分，不能当作整条观测的身份。"
            ),
            (
                "运动黏度 176 行以 m2/s 记录，没有密度就无法换算成 Pa*s；"
                "本表原样保留在 viscosity_kinematic_m2_s 列，且不参与任何 ε+η 配对。"
            ),
            (
                "extraction_gap 只覆盖由本地 ThermoML 语料派生的表；"
                "本仓其他含黏度列的表（viscosity_raw.csv、dielectric_viscosity_intersection.csv 等）"
                "来自 Schrödinger SI，不是 ThermoML，不能拿来反驳该结论。"
            ),
            (
                "本探针只做计数与抽取：不做建模、不改评分池、不把任何值写进冻结数据集。"
            ),
        ],
    }

    write_json_lf(summary_path, payload)
    write_csv_lf(rows_path, ROW_COLUMNS, observations)
    return payload


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--rows", type=Path, default=DEFAULT_ROWS)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    payload = build_summary(summary_path=args.summary, rows_path=args.rows)
    print(
        json.dumps(
            {
                "schema_version": payload["schema_version"],
                "xml_files_scanned": payload["xml_files_scanned"],
                "viscosity_files": payload["viscosity_files"],
                "viscosity_rows": payload["viscosity_rows"],
                "viscosity_rows_by_property": payload["viscosity_rows_by_property"],
                "pure_rows": payload["pure_rows"],
                "mixture_rows": payload["mixture_rows"],
                "pure_plus_mixture": payload["pure_plus_mixture"],
                "pure_keys": payload["pure_keys"],
                "overlap_eps_obs": payload["overlap_eps_obs"],
                "overlap_viscosity_v01": payload["overlap_viscosity_v01"],
                "new_vs_eps_and_v01": payload["new_vs_eps_and_v01"],
                "expectation_mismatches": payload["expectation_mismatches"],
                "outputs": payload["outputs"],
            },
            ensure_ascii=True,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
