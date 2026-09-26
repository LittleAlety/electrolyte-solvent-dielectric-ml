r"""W17-11 四大核心数据整理：按 InChIKey 的跨通道注册表 + 通道关系矩阵。

作者要求「把数据整理好」，本臂只做**整理**与**关系度量**：
  * 把四个核心通道各落各表的现状汇成一张派生注册表（键 = InChIKey，一行一键）；
  * 把通道两两交集算成一个可引用的关系矩阵，回答「谁和谁能接上、能接上多少」；
  * 顺手量一下 eps 与 DFT 偶极的重叠规模，以及 Kirkwood-Frohlich 关系的描述性强度
    （主记分牌的天花板被登记为「缺 Kirkwood g 维」的信息缺口，先量清手里有多少料）。

判据跑前冻结在 probes/four_core_registry_prereg.json 里：
  A 输入钉死（五个源表 sha256 逐位一致才继续）；
  B 表结构（列名逐字、行 = 键并集、一键一行）；
  C 逐通道口径自校验（has_* 为真的键数 = 该通道按取值列算出的键数）；
  D 不拟合模型、不碰主记分牌（models_fitted = 0 / r2_reported = false）；
  E 描述性关系只用来说明规模与形态，不许当判决；
  F 新产出全 LF。

不做：不拟合任何模型、不产 MAE/R2、不改任何既有表、不写进冻结件、不给源表去重或合并。

用法（PowerShell，仓库根）：
    .\.venv\Scripts\python.exe probes/build_four_core_registry.py          # 生成
    .\.venv\Scripts\python.exe probes/build_four_core_registry.py --check  # 离线重算并与磁盘比对
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

DEFAULT_PREREG = REPOSITORY_ROOT / "probes" / "four_core_registry_prereg.json"
DEFAULT_TABLE = REPOSITORY_ROOT / "data" / "processed" / "four_core_key_registry.csv"
DEFAULT_SUMMARY = REPOSITORY_ROOT / "probes" / "four_core_registry_summary.json"
DEFAULT_REPORT = REPOSITORY_ROOT / "reports" / "four_core_registry.md"

TARGET_T_K = 298.15
AU_TO_DEBYE = 2.541746473

UNSTABLE_SUMMARY_KEYS: tuple[str, ...] = ("generated_at_utc",)

CORE_CHANNELS: tuple[str, ...] = ("dielectric", "viscosity", "orbitals", "redox_label")
ALL_CHANNELS: tuple[str, ...] = (
    "dielectric",
    "viscosity",
    "orbitals",
    "redox_label",
    "density",
    "liquid_window",
)

CHANNEL_LABELS: dict[str, str] = {
    "dielectric": "介电常数 eps",
    "viscosity": "黏度 eta",
    "orbitals": "HOMO/LUMO/IP/EA/偶极",
    "redox_label": "氧化还原自由能（RX-392 标签）",
    "density": "密度 rho",
    "liquid_window": "液相窗口（mp/bp/闪点/密度）",
}

BANNED_CLAIM_TOKENS: tuple[str, ...] = ("提升", "增益", "改进", "优于")

TABLE_COLUMNS: tuple[str, ...] = (
    "inchikey",
    "smiles",
    "name",
    "has_dielectric",
    "dielectric",
    "dielectric_T_K",
    "has_viscosity",
    "viscosity_Pa_s",
    "viscosity_T_K",
    "has_orbitals",
    "HOMO_eV",
    "LUMO_eV",
    "gap_eV",
    "IP_eV",
    "EA_eV",
    "dipole_au",
    "dipole_D",
    "has_redox_label",
    "oxidation_free_energy_eV",
    "reduction_free_energy_eV",
    "has_density",
    "density_kg_m3",
    "density_T_K",
    "has_liquid_window",
    "mp_C",
    "bp_C",
    "flash_point_C",
    "ambient_density_g_cm3",
    "n_core_channels",
    "channels_present",
)


class InputDriftError(RuntimeError):
    """判据 A 失败：输入字节与预注册的 sha256/字节数不一致，不许继续。"""


@dataclass(frozen=True)
class ChannelSpec:
    name: str
    has_column: str
    source: str
    value_columns: tuple[str, ...]
    temperature_column: str | None
    reduction: str


CHANNEL_SPECS: tuple[ChannelSpec, ...] = (
    ChannelSpec(
        name="dielectric",
        has_column="has_dielectric",
        source="data/dielectric_v04.csv",
        value_columns=("dielectric",),
        temperature_column="T_K",
        reduction="nearest_to_target_T",
    ),
    ChannelSpec(
        name="viscosity",
        has_column="has_viscosity",
        source="data/viscosity_v02.csv",
        value_columns=("viscosity_Pa_s",),
        temperature_column="T_K",
        reduction="nearest_to_target_T",
    ),
    ChannelSpec(
        name="orbitals",
        has_column="has_orbitals",
        source="data/processed/redox_merged.csv",
        value_columns=("HOMO", "LUMO", "IP", "EA", "dipole"),
        temperature_column=None,
        reduction="first_non_empty_in_file_order",
    ),
    ChannelSpec(
        name="redox_label",
        has_column="has_redox_label",
        source="data/processed/redox_merged.csv",
        value_columns=("oxidation_free_energy", "reduction_free_energy"),
        temperature_column=None,
        reduction="first_non_empty_in_file_order",
    ),
    ChannelSpec(
        name="density",
        has_column="has_density",
        source="data/density_v01.csv",
        value_columns=("density_kg_m3",),
        temperature_column="T_K",
        reduction="nearest_to_target_T",
    ),
    ChannelSpec(
        name="liquid_window",
        has_column="has_liquid_window",
        source="data/processed/liquid_window_features.csv",
        value_columns=("mp_C", "bp_C", "flash_point_C", "density_g_cm3"),
        temperature_column=None,
        reduction="first_non_empty_in_file_order",
    ),
)


# --------------------------------------------------------------------------------------
# 基础工具
# --------------------------------------------------------------------------------------


def display_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPOSITORY_ROOT).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def read_rows(path: Path) -> list[dict[str, str]]:
    with open(path, encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def read_text_raw(path: Path) -> str:
    with path.open(encoding="utf-8", newline="") as handle:
        return handle.read()


def write_text_lf(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def write_json_lf(path: Path, payload: Any) -> None:
    write_text_lf(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def write_csv_lf(path: Path, fieldnames: Sequence[str], rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fieldnames), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def csv_text(fieldnames: Sequence[str], rows: Sequence[Mapping[str, Any]]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(
        buffer, fieldnames=list(fieldnames), lineterminator="\n", extrasaction="ignore"
    )
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


def canonical_json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def stable_view(summary: Mapping[str, Any]) -> dict[str, Any]:
    clone = json.loads(json.dumps(summary, ensure_ascii=False))
    for key in UNSTABLE_SUMMARY_KEYS:
        clone.pop(key, None)
    return clone


def fmt_value(value: float) -> str:
    return f"{value:.12g}"


def chip(text: str | None) -> str:
    return (text or "").strip()


def parse_float(text: str | None) -> float | None:
    stripped = chip(text)
    if not stripped:
        return None
    try:
        value = float(stripped)
    except ValueError:
        return None
    return value if math.isfinite(value) else None


def first_numeric(rows: Sequence[Mapping[str, str]], value_column: str) -> float | None:
    for row in rows:
        value = parse_float(row.get(value_column))
        if value is not None:
            return value
    return None


def first_text(rows: Sequence[Mapping[str, str]], column: str) -> str:
    for row in rows:
        text = chip(row.get(column))
        if text:
            return text
    return ""


def group_by_key(rows: Sequence[Mapping[str, str]]) -> dict[str, list[Mapping[str, str]]]:
    grouped: dict[str, list[Mapping[str, str]]] = {}
    for row in rows:
        key = chip(row.get("inchikey"))
        if key:
            grouped.setdefault(key, []).append(row)
    return grouped


def nearest_to_target(
    rows: Sequence[Mapping[str, str]], value_column: str, temperature_column: str
) -> tuple[float | None, float | None]:
    """在「值与温度都有」的行里取 |T - 298.15| 最小的一行。

    并列时取 T 更小的一行（规则跑前定死，不事后挑）；再并列时取源文件里先出现的那一行。
    若该键所有行都缺温度，则退化为「文件序第一个非空值」，并把温度记为空（summary 里有计数）。
    """
    best: tuple[float, float, int, float] | None = None
    for index, row in enumerate(rows):
        value = parse_float(row.get(value_column))
        temperature = parse_float(row.get(temperature_column))
        if value is None or temperature is None:
            continue
        candidate = (abs(temperature - TARGET_T_K), temperature, index, value)
        if best is None or candidate[:3] < best[:3]:
            best = candidate
    if best is not None:
        return best[3], best[1]
    return first_numeric(rows, value_column), None


def kirkwood_factor(epsilon: float) -> float:
    return (epsilon - 1.0) * (2.0 * epsilon + 1.0) / (9.0 * epsilon)


def pearson(xs: Sequence[float], ys: Sequence[float]) -> float | None:
    n = len(xs)
    if n < 3 or n != len(ys):
        return None
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    sxx = sum((x - mean_x) ** 2 for x in xs)
    syy = sum((y - mean_y) ** 2 for y in ys)
    sxy = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True))
    if sxx <= 0.0 or syy <= 0.0:
        return None
    return sxy / math.sqrt(sxx * syy)


def markdown_table(header: Sequence[str], rows: Sequence[Sequence[str]]) -> list[str]:
    out = ["| " + " | ".join(header) + " |", "|" + "|".join(["---"] * len(header)) + "|"]
    for row in rows:
        out.append("| " + " | ".join(row) + " |")
    return out


def verdict_of(summary: Mapping[str, Any]) -> str:
    keys = (
        "criterion_a_inputs",
        "criterion_b_schema",
        "criterion_c_per_channel",
        "criterion_d_no_model",
        "criterion_e_descriptive",
        "criterion_f_lf",
    )
    ok = all(bool(summary[key]["passed"]) for key in keys)
    if "wording_guard" in summary:
        ok = ok and bool(summary["wording_guard"]["passed"])
    return "PASS" if ok else "FAIL"


CHANNEL_TABLE_COLUMNS: dict[str, tuple[tuple[str, str], ...]] = {
    "dielectric": (("dielectric", "dielectric"),),
    "viscosity": (("viscosity_Pa_s", "viscosity_Pa_s"),),
    "orbitals": (
        ("HOMO", "HOMO_eV"),
        ("LUMO", "LUMO_eV"),
        ("IP", "IP_eV"),
        ("EA", "EA_eV"),
        ("dipole", "dipole_au"),
    ),
    "redox_label": (
        ("oxidation_free_energy", "oxidation_free_energy_eV"),
        ("reduction_free_energy", "reduction_free_energy_eV"),
    ),
    "density": (("density_kg_m3", "density_kg_m3"),),
    "liquid_window": (
        ("mp_C", "mp_C"),
        ("bp_C", "bp_C"),
        ("flash_point_C", "flash_point_C"),
        ("density_g_cm3", "ambient_density_g_cm3"),
    ),
}

CHANNEL_TABLE_TEMPERATURE: dict[str, str | None] = {
    "dielectric": "dielectric_T_K",
    "viscosity": "viscosity_T_K",
    "orbitals": None,
    "redox_label": None,
    "density": "density_T_K",
    "liquid_window": None,
}


def collect_inputs(
    prereg: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, str]]]]:
    inputs: list[dict[str, Any]] = []
    sources: dict[str, list[dict[str, str]]] = {}
    for entry in prereg["inputs"]:
        relative = str(entry["path"])
        path = REPOSITORY_ROOT / relative
        if not path.is_file():
            raise InputDriftError("缺输入：" + relative)
        digest = sha256_of(path)
        size = path.stat().st_size
        rows = read_rows(path)
        sources[relative] = rows
        inputs.append(
            {
                "channel": str(entry["channel"]),
                "path": display_path(path),
                "bytes": size,
                "sha256": digest,
                "pinned_sha256": str(entry["sha256"]),
                "pinned_bytes": int(entry["bytes"]),
                "sha256_matches": digest == str(entry["sha256"]),
                "bytes_matches": size == int(entry["bytes"]),
                "rows": len(rows),
                "keys": len(group_by_key(rows)),
            }
        )
    return inputs, sources


def scan_channels(
    sources: Mapping[str, Sequence[Mapping[str, str]]],
) -> tuple[
    dict[str, dict[str, dict[str, float | None]]],
    dict[str, dict[str, float | None]],
    dict[str, int],
    dict[str, dict[str, list[Mapping[str, str]]]],
]:
    grouped = {path: group_by_key(rows) for path, rows in sources.items()}
    channel_values: dict[str, dict[str, dict[str, float | None]]] = {}
    channel_temperature: dict[str, dict[str, float | None]] = {}
    fallbacks: dict[str, int] = {}
    for spec in CHANNEL_SPECS:
        rows_by_key = grouped[spec.source]
        values_for_key: dict[str, dict[str, float | None]] = {}
        temperature_for_key: dict[str, float | None] = {}
        fallback_count = 0
        for key, rows in rows_by_key.items():
            if spec.reduction == "nearest_to_target_T" and spec.temperature_column:
                value, temperature = nearest_to_target(
                    rows, spec.value_columns[0], spec.temperature_column
                )
                values = {spec.value_columns[0]: value}
                if value is not None and temperature is None:
                    fallback_count += 1
            else:
                values = {column: first_numeric(rows, column) for column in spec.value_columns}
                temperature = None
            if any(value is not None for value in values.values()):
                values_for_key[key] = values
                temperature_for_key[key] = temperature
        channel_values[spec.name] = values_for_key
        channel_temperature[spec.name] = temperature_for_key
        fallbacks[spec.name] = fallback_count
    return channel_values, channel_temperature, fallbacks, grouped


def build_table_rows(
    keys: Sequence[str],
    channel_values: Mapping[str, Mapping[str, Mapping[str, float | None]]],
    channel_temperature: Mapping[str, Mapping[str, float | None]],
    grouped: Mapping[str, Mapping[str, Sequence[Mapping[str, str]]]],
) -> list[dict[str, str]]:
    identity: dict[str, dict[str, str]] = {}
    for spec in CHANNEL_SPECS:
        for key, rows in grouped[spec.source].items():
            entry = identity.setdefault(key, {"smiles": "", "name": ""})
            if not entry["smiles"]:
                entry["smiles"] = first_text(rows, "smiles")
            if not entry["name"]:
                entry["name"] = first_text(rows, "name")

    rows: list[dict[str, str]] = []
    for key in keys:
        row: dict[str, str] = {column: "" for column in TABLE_COLUMNS}
        row["inchikey"] = key
        entry = identity.get(key, {"smiles": "", "name": ""})
        row["smiles"] = entry["smiles"]
        row["name"] = entry["name"]
        flags: dict[str, bool] = {}
        for spec in CHANNEL_SPECS:
            values = channel_values[spec.name].get(key)
            flags[spec.name] = values is not None
            row[spec.has_column] = "true" if values is not None else "false"
            if values is None:
                continue
            temperature = channel_temperature[spec.name].get(key)
            for source_column, table_column in CHANNEL_TABLE_COLUMNS[spec.name]:
                value = values.get(source_column)
                row[table_column] = "" if value is None else fmt_value(value)
            table_temperature = CHANNEL_TABLE_TEMPERATURE[spec.name]
            if table_temperature is not None and temperature is not None:
                row[table_temperature] = fmt_value(temperature)

        dipole_au = parse_float(row["dipole_au"])
        if dipole_au is not None:
            row["dipole_D"] = fmt_value(dipole_au * AU_TO_DEBYE)
        homo = parse_float(row["HOMO_eV"])
        lumo = parse_float(row["LUMO_eV"])
        if homo is not None and lumo is not None:
            row["gap_eV"] = fmt_value(lumo - homo)

        row["n_core_channels"] = str(sum(1 for name in CORE_CHANNELS if flags[name]))
        row["channels_present"] = "|".join(name for name in ALL_CHANNELS if flags[name])
        rows.append(row)
    return rows


def guard_violations(
    prereg: Mapping[str, Any], report: str, summary: Mapping[str, Any]
) -> list[str]:
    problems: list[str] = []
    if prereg["status"] != "locked_before_run":
        problems.append("预注册未处于 locked_before_run")
    criterion_d = summary["criterion_d_no_model"]
    if criterion_d["models_fitted"] != 0 or criterion_d["r2_reported"] is not False:
        problems.append("判据 D 违约：本臂不许拟合模型或上报 R2")
    for token in BANNED_CLAIM_TOKENS:
        if token in report:
            problems.append("报告出现性能断言用词：" + token)
    required = (
        "描述性",
        "非判决",
        str(prereg["descriptive_relation_definition"]["role"]),
    )
    for text in required:
        if text not in report:
            problems.append("报告缺少必备标注：" + text)
    return problems


def passed_label(block: Mapping[str, Any]) -> str:
    return "PASS" if block.get("passed") else "FAIL"


def render_report(summary: Mapping[str, Any]) -> str:
    lines: list[str] = []
    add = lines.append
    registry = summary["registry"]
    add("# W17-11 四大核心数据整理：跨通道注册表与通道关系矩阵")
    add("")
    add(
        "本表是**派生注册表**（键 = InChIKey，一行一键），不是新数据源；任何引用都必须同时"
        "说清它派生于哪几张源表。本臂只做整理与关系度量：不拟合任何模型、不产 MAE 与 R2、"
        "不引用主记分牌。"
    )
    add("")
    add(
        "- 注册表：`"
        + str(registry["path"])
        + "`（"
        + str(registry["n_rows"])
        + " 行 / "
        + str(registry["n_columns"])
        + " 列）"
    )
    add(
        "- 通道："
        + str(len(ALL_CHANNELS))
        + " 个，核心 "
        + str(len(CORE_CHANNELS))
        + " 个（"
        + "、".join(CHANNEL_LABELS[name] for name in CORE_CHANNELS)
        + "）"
    )
    add("- 四核心全齐的键：" + str(summary["core_all_present"]))
    add("- 判据：" + str(summary["verdict"]))
    add("")

    add("## 输入（判据 A：跑前逐位钉死）")
    add("")
    lines.extend(
        markdown_table(
            ("channel", "path", "sha256（前 16 位）", "bytes", "rows", "keys", "钉死"),
            [
                [
                    str(item["channel"]),
                    "`" + str(item["path"]) + "`",
                    str(item["sha256"])[:16],
                    str(item["bytes"]),
                    str(item["rows"]),
                    str(item["keys"]),
                    "一致" if item["sha256_matches"] and item["bytes_matches"] else "漂移",
                ]
                for item in summary["inputs"]
            ],
        )
    )
    add("")

    add("## 通道覆盖（判据 C：口径自校验）")
    add("")
    readings = {
        str(item["channel"]): item for item in summary["criterion_c_per_channel"]["readings"]
    }
    counts = summary["channel_counts"]
    lines.extend(
        markdown_table(
            (
                "通道",
                "源表",
                "取值列",
                "单位",
                "归约",
                "注册表 has_* = true",
                "口径键数",
                "源表去重键数",
            ),
            [
                [
                    CHANNEL_LABELS[name] + "（`" + name + "`）",
                    "`" + str(counts[name]["source_table"]) + "`",
                    ", ".join(str(column) for column in counts[name]["value_columns"]),
                    str(counts[name]["unit"]),
                    str(counts[name]["reduction"]),
                    str(readings[name]["registry_has_true"]),
                    str(readings[name]["contract_keys"]),
                    str(readings[name]["source_table_keys"]),
                ]
                for name in ALL_CHANNELS
            ],
        )
    )
    add("")
    add(
        "orbitals 与 redox_label 共用 `data/processed/redox_merged.csv`，所以「源表去重键数」"
        "对这两个子通道是同一个数；要把两者分开，判据 C 只能按各自的取值列定义键集"
        "（即某个取值列里至少有一个有限数值）。"
    )
    add("")

    add("## 通道两两交集（键数）")
    add("")
    intersections = summary["channel_intersections"]
    lines.extend(
        markdown_table(
            ("通道 A", "通道 B", "交集键数"),
            [
                [
                    CHANNEL_LABELS[left],
                    CHANNEL_LABELS[right],
                    str(intersections[left + "&" + right]),
                ]
                for index, left in enumerate(ALL_CHANNELS)
                for right in ALL_CHANNELS[index + 1 :]
            ],
        )
    )
    add("")

    add("## 四核心全齐")
    add("")
    add(
        "同时有 ε、η、HOMO/LUMO（含 IP/EA/偶极）、氧化还原自由能标签的键："
        + str(summary["core_all_present"])
        + " 个。下表是全部键按「命中几个核心通道」的分布。"
    )
    add("")
    histogram = registry["n_core_channels_histogram"]
    lines.extend(
        markdown_table(
            ("命中核心通道数", "键数"),
            [[str(name), str(histogram[str(name)])] for name in range(len(CORE_CHANNELS) + 1)],
        )
    )
    add("")

    add("### 四通道全齐的三种口径（对账用）")
    add("")
    quartets = summary["coverage_quartets"]
    lines.extend(
        markdown_table(
            ("口径", "通道", "键数"),
            [
                [
                    str(name),
                    "、".join(str(channel) for channel in quartets[name]["channels"]),
                    str(quartets[name]["keys"]),
                ]
                for name in quartets
            ],
        )
    )
    add("")
    reconciliation = summary["liquid_window_reconciliation"]
    add(
        "液相窗口表的行数是 "
        + str(reconciliation["table_rows"])
        + "，其中 "
        + str(reconciliation["keys_with_all_four_columns_empty"])
        + " 行的 mp/bp/闪点/密度四列全空（`quality_layer = filter_only`，"
        "是过了筛选但没取到数的候选）。本注册表的 `has_liquid_window` 只认"
        "「四列里至少有一个有限数值」，即 "
        + str(reconciliation["keys_with_any_numeric"])
        + " 键。上一轮登记的交集（ε 246 / η 202 / orbitals 89 / ρ 246）用的是表键口径；"
        + "两种口径并列如下。"
    )
    add("")
    add("")
    lines.extend(
        markdown_table(
            ("通道", "与液相窗口的交集（表键口径）", "与液相窗口的交集（取值列口径）"),
            [
                [
                    CHANNEL_LABELS[name],
                    str(reconciliation["intersections_with_table_keys"][name]),
                    str(summary["channel_intersections"][name + "&liquid_window"]),
                ]
                for name in ALL_CHANNELS
                if name != "liquid_window"
            ],
        )
    )
    add("")
    overlap = reconciliation["empty_keys_overlap_with_channels"]
    add(
        "这 "
        + str(reconciliation["keys_with_all_four_columns_empty"])
        + " 个空壳键里，有 "
        + str(overlap["dielectric"])
        + " 个同时有 ε、"
        + str(overlap["viscosity"])
        + " 个有 η、"
        + str(overlap["orbitals"])
        + " 个有 orbitals —— 液相窗口的 filter_only 人口与核心名册高度重叠，"
        + "不是一批无关化合物。"
    )
    add("")
    lines.extend(
        markdown_table(
            ("空壳键同时命中的通道", "键数"),
            [
                [
                    CHANNEL_LABELS[name],
                    str(reconciliation["empty_keys_overlap_with_channels"][name]),
                ]
                for name in ALL_CHANNELS
                if name != "liquid_window"
            ],
        )
    )
    add("")

    add("## 描述性关系：Kirkwood-Frohlich 与 DFT 偶极")
    add("")
    relation = summary["descriptive_relation"]
    add("- 口径：" + str(relation["key_set"]))
    add(
        "- n = "
        + str(relation["n_pairs"])
        + "（ε 名册 "
        + str(relation["n_dielectric_keys"])
        + " 键；orbitals 通道 "
        + str(relation["n_orbitals_keys"])
        + " 键，其中带偶极 "
        + str(relation["n_orbitals_with_dipole"])
        + " 键）"
    )
    add("- " + str(relation["formula"]))
    add("- Pearson(K(ε), μ_D²) = " + repr(relation["pearson_kirkwood_vs_dipole_sq"]))
    add("- Pearson(K(ε), μ_D) = " + repr(relation["pearson_kirkwood_vs_dipole"]))
    add(
        "- 对数版：n = "
        + str(relation["log10"]["n_pairs"])
        + "，Pearson(log10 K, log10 μ_D²) = "
        + repr(relation["log10"]["pearson_log10_kirkwood_vs_log10_dipole_sq"])
        + "（因非正而跳过 "
        + str(relation["log10"]["n_skipped_nonpositive"])
        + " 个）"
    )
    add(
        "- 角色：`"
        + str(relation["role"])
        + "`。这是描述性统计，只用来说明手里有多少料、关系是什么形态；"
        "不是模型性能，不是判决，不许当杠杆证据。样本量小（ε 名册只有 "
        + str(relation["n_dielectric_keys"])
        + " 键），任何引用都要连同 n 一起给。"
    )
    add(
        "- 单位：源表 dipole 是 atomic_units (e*bohr)（见 `probes/p4_redox_summary.json` 的 units 块），"
        "本表同时给 dipole_D = dipole_au × "
        + repr(AU_TO_DEBYE)
        + "。Pearson 对常数缩放不变，故 μ_au² 与 μ_D² 给出同一个 r。"
    )
    add("")

    add("## 判据 A-F")
    add("")
    lines.extend(
        markdown_table(
            ("判据", "结果", "说明"),
            [
                [
                    "A 输入钉死",
                    passed_label(summary["criterion_a_inputs"]),
                    "五个源表 sha256 与字节数逐位一致才继续",
                ],
                [
                    "B 表结构",
                    passed_label(summary["criterion_b_schema"]),
                    "列名与预注册逐字一致；"
                    + str(registry["n_rows"])
                    + " 行 = 六通道键并集；一键一行",
                ],
                [
                    "C 口径自校验",
                    passed_label(summary["criterion_c_per_channel"]),
                    "每通道 has_* = true 的键数 = 该通道按取值列算出的键数",
                ],
                [
                    "D 不碰模型",
                    passed_label(summary["criterion_d_no_model"]),
                    "models_fitted = 0 / r2_reported = false / 主记分牌 0 次",
                ],
                [
                    "E 描述性关系",
                    passed_label(summary["criterion_e_descriptive"]),
                    "相关系数按描述性上报（n = " + str(relation["n_pairs"]) + "），不是判决",
                ],
                [
                    "F 全 LF",
                    passed_label(summary["criterion_f_lf"]),
                    "三件产物都以 newline=LF 写出，字节里没有 CR",
                ],
                [
                    "口径守卫",
                    passed_label(summary["wording_guard"]),
                    "报告里没有性能断言用词，且带齐描述性与非判决标注",
                ],
            ],
        )
    )
    add("")

    add("## 边界（不许外推）")
    add("")
    for item in summary["boundaries"]:
        add("- " + str(item))
    add("")

    add("## 复现")
    add("")
    add("- 生成：`" + str(summary["reproducibility"]["run"]) + "`")
    add("- 复核：`" + str(summary["reproducibility"]["check"]) + "`")
    add("- 独立核验：`" + str(summary["reproducibility"]["verifier"]) + "`")
    add(
        "- 预注册：`"
        + str(summary["prereg"]["path"])
        + "`（sha256 "
        + str(summary["prereg"]["sha256"])[:16]
        + "…）"
    )
    add("")
    return "\n".join(lines)


def settle(summary: dict[str, Any], prereg: Mapping[str, Any]) -> str:
    """两遍渲染：先把口径守卫与判据 F 的结果写回 summary，再出最终报告。"""
    summary["wording_guard"] = {"passed": True, "violations": []}
    summary["verdict"] = verdict_of(summary)
    report = render_report(summary)
    violations = guard_violations(prereg, report, summary)
    summary["wording_guard"] = {"passed": not violations, "violations": violations}
    if "\r" in report:
        summary["criterion_f_lf"]["passed"] = False
    summary["verdict"] = verdict_of(summary)
    report = render_report(summary)
    if guard_violations(prereg, report, summary) != violations:
        raise RuntimeError("口径守卫在报告重渲染后发生变化")
    if "\r" in report:
        raise RuntimeError("报告里出现 CR，判据 F 违约")
    return report


def compose(
    args: argparse.Namespace, *, generated_at: str | None
) -> tuple[dict[str, Any], str, list[dict[str, str]]]:
    prereg = json.loads(args.prereg.read_text(encoding="utf-8"))
    prereg_sha256 = sha256_of(args.prereg)

    inputs, sources = collect_inputs(prereg)
    criterion_a = {
        "passed": all(item["sha256_matches"] and item["bytes_matches"] for item in inputs),
        "n_inputs": len(inputs),
        "n_sha256_mismatch": sum(1 for item in inputs if not item["sha256_matches"]),
        "n_bytes_mismatch": sum(1 for item in inputs if not item["bytes_matches"]),
        "rule": "sha256 与字节数逐位一致才继续；不一致直接 FAIL。",
    }
    if not criterion_a["passed"]:
        raise InputDriftError(
            "判据 A 失败：输入与预注册不一致（sha256 不符 {} 个 / 字节数不符 {} 个）".format(
                criterion_a["n_sha256_mismatch"], criterion_a["n_bytes_mismatch"]
            )
        )

    channel_values, channel_temperature, fallbacks, grouped = scan_channels(sources)

    key_sets = {name: set(channel_values[name]) for name in ALL_CHANNELS}
    all_keys = sorted(set().union(*key_sets.values()))
    rows = build_table_rows(all_keys, channel_values, channel_temperature, grouped)

    registry_columns = list(TABLE_COLUMNS)
    pinned_columns = [str(name) for name in prereg["registry_schema"]]
    unique_keys = {row["inchikey"] for row in rows}
    criterion_b = {
        "passed": registry_columns == pinned_columns
        and len(rows) == len(all_keys)
        and len(unique_keys) == len(rows),
        "columns_match_prereg": registry_columns == pinned_columns,
        "n_columns": len(registry_columns),
        "n_rows": len(rows),
        "n_union_keys": len(all_keys),
        "one_row_per_key": len(unique_keys) == len(rows),
        "rule": "列名与预注册 registry_schema 逐字一致；行数 = 六通道键并集；一键一行。",
    }

    readings: list[dict[str, Any]] = []
    for spec in CHANNEL_SPECS:
        has_true = sum(1 for row in rows if row[spec.has_column] == "true")
        contract_keys = len(channel_values[spec.name])
        readings.append(
            {
                "channel": spec.name,
                "has_column": spec.has_column,
                "registry_has_true": has_true,
                "contract_keys": contract_keys,
                "source_table_keys": len(grouped[spec.source]),
                "matches": has_true == contract_keys,
                "nearest_temperature_fallbacks": fallbacks[spec.name],
            }
        )
    criterion_c = {
        "passed": all(item["matches"] for item in readings),
        "readings": readings,
        "reading_note": (
            "orbitals 与 redox_label 共用 data/processed/redox_merged.csv，"
            "所以「该通道源表里出现的去重键数」对这两个子通道都等于整表键数；"
            "要能把两者分开，判据 C 只能按各自的取值列定义键集"
            "（即某个取值列里至少有一个有限数值），source_table_keys 一并列出以供对照。"
        ),
    }

    criterion_d = {
        "passed": True,
        "models_fitted": 0,
        "r2_reported": False,
        "mae_reported": False,
        "main_scoreboard_attempts": 0,
        "note": "本臂只做连接与计数：不拟合任何模型、不上报任何 R2 或 MAE、不引用主记分牌。",
    }

    pairs: list[tuple[float, float]] = []
    orbitals_with_dipole = 0
    for row in rows:
        if row["has_orbitals"] == "true" and row["dipole_au"]:
            orbitals_with_dipole += 1
        if row["has_dielectric"] != "true":
            continue
        epsilon = parse_float(row["dielectric"])
        dipole_d = parse_float(row["dipole_D"])
        if epsilon is None or dipole_d is None or epsilon <= 0.0:
            continue
        pairs.append((dipole_d, kirkwood_factor(epsilon)))

    log_pairs: list[tuple[float, float]] = []
    skipped_nonpositive = 0
    for dipole_d, factor in pairs:
        if dipole_d > 0.0 and factor > 0.0:
            log_pairs.append((math.log10(dipole_d * dipole_d), math.log10(factor)))
        else:
            skipped_nonpositive += 1

    relation = {
        "name": str(prereg["descriptive_relation_definition"]["name"]),
        "role": str(prereg["descriptive_relation_definition"]["role"]),
        "formula": "K(eps) = (eps - 1) * (2 * eps + 1) / (9 * eps)",
        "key_set": "registry 里 has_dielectric = true 且 dipole 非空且 eps > 0 的键",
        "n_pairs": len(pairs),
        "n_dielectric_keys": len(channel_values["dielectric"]),
        "n_orbitals_keys": len(channel_values["orbitals"]),
        "n_orbitals_with_dipole": orbitals_with_dipole,
        "dipole_unit_in_source": "atomic_units (e*bohr)",
        "dipole_au_to_debye_factor": AU_TO_DEBYE,
        "pearson_kirkwood_vs_dipole_sq": pearson(
            [dipole * dipole for dipole, _ in pairs], [factor for _, factor in pairs]
        ),
        "pearson_kirkwood_vs_dipole": pearson(
            [dipole for dipole, _ in pairs], [factor for _, factor in pairs]
        ),
        "log10": {
            "n_pairs": len(log_pairs),
            "n_skipped_nonpositive": skipped_nonpositive,
            "pearson_log10_kirkwood_vs_log10_dipole_sq": pearson(
                [x for x, _ in log_pairs], [y for _, y in log_pairs]
            ),
        },
    }
    criterion_e = {
        "passed": relation["n_pairs"] >= 3
        and relation["role"] == str(prereg["descriptive_relation_definition"]["role"]),
        "role": relation["role"],
        "n_pairs": relation["n_pairs"],
        "note": "相关系数只用来说明规模与形态；不是模型性能、不是判决、不许当杠杆证据。",
    }

    intersections: dict[str, int] = {}
    for index, left in enumerate(ALL_CHANNELS):
        for right in ALL_CHANNELS[index + 1 :]:
            intersections[left + "&" + right] = len(key_sets[left] & key_sets[right])

    histogram = {str(value): 0 for value in range(len(CORE_CHANNELS) + 1)}
    for row in rows:
        histogram[row["n_core_channels"]] += 1
    core_all_present = histogram[str(len(CORE_CHANNELS))]

    liquid_window_table_keys = set(grouped["data/processed/liquid_window_features.csv"])
    empty_liquid_window = liquid_window_table_keys - key_sets["liquid_window"]
    liquid_window_reconciliation = {
        "source_table": "data/processed/liquid_window_features.csv",
        "table_rows": len(sources["data/processed/liquid_window_features.csv"]),
        "table_keys": len(liquid_window_table_keys),
        "keys_with_any_numeric": len(key_sets["liquid_window"]),
        "keys_with_all_four_columns_empty": len(empty_liquid_window),
        "empty_keys": sorted(empty_liquid_window),
        "empty_keys_overlap_with_channels": {
            name: len(empty_liquid_window & key_sets[name])
            for name in ALL_CHANNELS
            if name != "liquid_window"
        },
        "why": (
            "这 "
            + str(len(empty_liquid_window))
            + " 行是过筛但没取到数的候选（quality_layer = filter_only）："
            + "mp/bp/闪点/密度四列全空、四个 has_* 全 false。"
            + "按表键口径与按取值列口径会得到两组交集，本 summary 两种都登记，"
            + "避免同一件事被引用成两个数。"
        ),
        "intersections_with_table_keys": {
            name: len(key_sets[name] & liquid_window_table_keys)
            for name in ALL_CHANNELS
            if name != "liquid_window"
        },
        "quartet_with_table_keys": len(
            key_sets["dielectric"]
            & key_sets["viscosity"]
            & key_sets["orbitals"]
            & liquid_window_table_keys
        ),
    }
    coverage_quartets = {
        "prereg_core_four": {
            "channels": list(CORE_CHANNELS),
            "keys": core_all_present,
        },
        "with_liquid_window_data": {
            "channels": ["dielectric", "viscosity", "orbitals", "liquid_window"],
            "keys": len(
                key_sets["dielectric"]
                & key_sets["viscosity"]
                & key_sets["orbitals"]
                & key_sets["liquid_window"]
            ),
        },
        "with_liquid_window_table_keys": {
            "channels": ["dielectric", "viscosity", "orbitals", "liquid_window(表键口径)"],
            "keys": liquid_window_reconciliation["quartet_with_table_keys"],
        },
    }

    summary: dict[str, Any] = {
        "schema_version": 1,
        "task": "build_four_core_registry",
        "title": str(prereg["title"]),
        "generated_at_utc": generated_at or utc_now(),
        "status": "generated",
        "prereg": {
            "path": display_path(args.prereg),
            "sha256": prereg_sha256,
            "status": str(prereg["status"]),
            "locked_at_utc": str(prereg["locked_at_utc"]),
        },
        "inputs": inputs,
        "registry": {
            "path": display_path(args.table),
            "n_rows": len(rows),
            "n_columns": len(registry_columns),
            "columns": registry_columns,
            "one_row_per_key": criterion_b["one_row_per_key"],
            "n_core_channels_histogram": histogram,
        },
        "channel_counts": {
            spec.name: {
                "label": CHANNEL_LABELS[spec.name],
                "source_table": spec.source,
                "value_columns": list(spec.value_columns),
                "unit": str(
                    prereg["channel_value_contract"][
                        "redox" if spec.name == "redox_label" else spec.name
                    ]["unit"]
                ),
                "reduction": spec.reduction,
                "keys": len(channel_values[spec.name]),
                "source_table_keys": len(grouped[spec.source]),
            }
            for spec in CHANNEL_SPECS
        },
        "core_channels": list(CORE_CHANNELS),
        "core_all_present": core_all_present,
        "coverage_quartets": coverage_quartets,
        "liquid_window_reconciliation": liquid_window_reconciliation,
        "channel_intersections": intersections,
        "descriptive_relation": relation,
        "criterion_a_inputs": criterion_a,
        "criterion_b_schema": criterion_b,
        "criterion_c_per_channel": criterion_c,
        "criterion_d_no_model": criterion_d,
        "criterion_e_descriptive": criterion_e,
        "boundaries": [
            "本表是派生视图：源表才是事实；源表一改，本表与两份伴生件都要重跑。",
            (
                "归约口径写死在预注册里（nearest_to_target_T 的三级并列规则 / "
                "first_non_empty_in_file_order），不做平均、不跨温度外推。"
            ),
            "温度归约到 298.15 K 只是选行规则，不代表该键只有这一个温度；要温度曲线请回源表。",
            (
                "redox_label 通道只有 RX-392 的 392 条标签，是全仓最紧的瓶颈；"
                "四个外部数据源与 Reaxys 都没能补上它。"
            ),
            (
                "不含任何 Reaxys 数值；外部数据源（OMat24 / OMol25 / THEMol / 火山 QC）的核查结论"
                "见手册附录 AI-2b / AI-2c。"
            ),
            "描述性关系只说明规模与形态，不是模型性能、不是判决、不许当杠杆证据。",
        ],
        "reproducibility": {
            "run": ".venv/Scripts/python.exe probes/build_four_core_registry.py",
            "check": ".venv/Scripts/python.exe probes/build_four_core_registry.py --check",
            "verifier": ".venv/Scripts/python.exe scripts/verify_four_core_registry.py --check",
            "deterministic": "同一批输入字节 => 同一批输出字节；summary 的 generated_at_utc "
            "是唯一易变位，--check 按 stable_view 剥掉。",
        },
    }

    table_text = csv_text(TABLE_COLUMNS, rows)
    summary["criterion_f_lf"] = {
        "passed": "\r" not in table_text and "\r" not in canonical_json(summary),
        "policy": "三件产物都以 newline=LF 写出（write_text_lf / write_json_lf / write_csv_lf "
        "显式指定）；report 走 render_report 的同一条路径。",
    }

    report = settle(summary, prereg)
    return summary, report, rows


def print_summary(
    summary: Mapping[str, Any], table_path: Path, summary_path: Path, report_path: Path
) -> None:
    print("W17-11 四大核心数据跨通道注册表")
    print("判据 A 输入钉死   : " + passed_label(summary["criterion_a_inputs"]))
    print(
        "判据 B 表结构     : "
        + passed_label(summary["criterion_b_schema"])
        + "（"
        + str(summary["registry"]["n_rows"])
        + " 行 / "
        + str(summary["registry"]["n_columns"])
        + " 列）"
    )
    print("判据 C 口径自校验 : " + passed_label(summary["criterion_c_per_channel"]))
    print("判据 D 不碰模型   : " + passed_label(summary["criterion_d_no_model"]))
    print(
        "判据 E 描述性关系 : "
        + passed_label(summary["criterion_e_descriptive"])
        + "（n = "
        + str(summary["descriptive_relation"]["n_pairs"])
        + "）"
    )
    print("判据 F 全 LF      : " + passed_label(summary["criterion_f_lf"]))
    print("口径守卫          : " + passed_label(summary["wording_guard"]))
    print("四核心全齐        : " + str(summary["core_all_present"]))
    print("verdict           : " + str(summary["verdict"]))
    print("table             : " + display_path(table_path))
    print("summary           : " + display_path(summary_path))
    print("report            : " + display_path(report_path))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="W17-11 四大核心数据跨通道注册表（不拟合任何模型）。"
    )
    parser.add_argument("--check", action="store_true", help="离线重算并与磁盘产物逐字节比对")
    parser.add_argument("--prereg", type=Path, default=DEFAULT_PREREG)
    parser.add_argument("--table", type=Path, default=DEFAULT_TABLE)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args(argv)

    if args.check:
        if not args.summary.is_file():
            print("FAIL 缺 summary：" + display_path(args.summary))
            return 1
        disk = json.loads(args.summary.read_text(encoding="utf-8"))
        try:
            summary, report, rows = compose(args, generated_at=str(disk.get("generated_at_utc")))
        except InputDriftError as error:
            print("FAIL " + str(error))
            return 1
        problems: list[str] = []
        if stable_view(summary) != stable_view(disk):
            problems.append("summary 与离线重算不一致")
        if not args.report.is_file():
            problems.append("缺 report：" + display_path(args.report))
        elif read_text_raw(args.report) != report:
            problems.append("report 不是 render_report(summary) 的逐字输出")
        if not args.table.is_file():
            problems.append("缺表：" + display_path(args.table))
        elif read_text_raw(args.table) != csv_text(TABLE_COLUMNS, rows):
            problems.append("four_core_key_registry.csv 与离线重算不一致")
        for problem in problems:
            print("FAIL " + problem)
        if problems:
            return 1
        print(
            "OK 离线复算一致；判据 A {}；注册表 {} 行；四核心全齐 {}；verdict {}".format(
                passed_label(summary["criterion_a_inputs"]),
                summary["registry"]["n_rows"],
                summary["core_all_present"],
                summary["verdict"],
            )
        )
        return 0

    try:
        summary, report, rows = compose(args, generated_at=None)
    except InputDriftError as error:
        print("FAIL " + str(error))
        return 1
    write_json_lf(args.summary, summary)
    write_text_lf(args.report, report)
    write_csv_lf(args.table, TABLE_COLUMNS, rows)
    print_summary(summary, args.table, args.summary, args.report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
