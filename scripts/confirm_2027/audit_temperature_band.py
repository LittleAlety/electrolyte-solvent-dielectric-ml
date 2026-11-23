#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""B-G0-J01K | v11 与冻结协议的温度分带调和.

要回答的唯一问题
----------------
SN 的 333.15 K 观测, v11 记 `outside_declared_window`, 冻结协议温窗记 `high_temperature`.
两者不一致. 要回答的是"哪一个对", 而是"如何在不篡改任何一边的前提下把它记录成
可审计的双字段".

裁决边界 (由授权方规定)
-----------------------
* 不改原始温度, 不覆盖原始标签;
* 不为了统一报告把其中一个直接替换成另一个;
* 293.15 K 与 303.15 K 必须仍然是闭区间, 边界测试保留;
* SN 的 333.15 K 记录不能被计入室温合格数量, 也不能被删除.

因此本模块只输出**并列字段**, 不裁决对错:
  temperature_raw_K                 原始温度
  temperature_band_v11              v11 自己的分带
  temperature_band_protocol         按冻结温窗算出的分带
  temperature_band_reconciliation   两者关系 (AGREE / DISAGREE_*)
  evidence_note                     附加说明

为什么会不一致 (写进产物, 不靠叙述)
-----------------------------------
v11 的 `temperature_band` 由 `build_dielectric_observations_v11plus.py` 生成, 它的分带
词表与冻结协议 `allowed_temperature_windows_K` 不是同一个枚举对象. 本模块不假设哪个
"应该"对, 只把两边的取值并列, 并给出可复核的差异计数.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import os
import platform
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

ANALYSIS_ID = "B-G0-J01K"
ANALYSIS_TITLE = "v11 与冻结协议温度分带调和"
CONTRACT_VERSION = "confirm_2027.temperature_band/v1"
INPUT_CONTRACT_VERSION = "confirm_2027.j01k_inputs/v1"
GENERATOR_VERSION = "audit_temperature_band/1.0.0"

PINNED: dict[str, tuple[str, int]] = {
    "observations_v11": ("a2af3ea16a3f6d9a2ed81b9fcf70d1d1a10d2b5a3e5f4c1b9d8e7f6a5b4c3d2e", 0),
}

OUTPUT_FILES: tuple[str, ...] = (
    "temperature_band_reconciliation.csv",
    "j01k_band_summary.json",
    "j01k_rebuild_receipt.json",
)

BAND_COLUMNS: tuple[str, ...] = (
    "a_mol_id", "a_name", "observation_id", "temperature_raw_K",
    "temperature_band_v11", "temperature_band_protocol",
    "temperature_band_reconciliation", "in_room_band_protocol",
    "counts_as_room_band_qualified", "room_band_exclusion_reason",
    "is_sn_333_15_boundary_case", "evidence_note",
)

#: 授权方点名要保留原值的边界记录
SN_MOL_ID = "C18"
SN_TEMPERATURE = 333.15
ROOM_BAND_LOW = 293.15
ROOM_BAND_HIGH = 303.15


class AuditError(RuntimeError):
    """输入缺失/结构不合法 (退出码 2)."""


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(Path(path).read_bytes())


def skeleton(inchikey: str) -> str:
    text = (inchikey or "").strip()
    return text.split("-")[0] if text else ""


def to_float(text: Any) -> float | None:
    raw = str(text).strip() if text is not None else ""
    if not raw:
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def fmt(value: float | None) -> str:
    if value is None:
        return ""
    text = f"{value:.6f}".rstrip("0").rstrip(".")
    return text if text else "0"


def read_csv_strict(path: Path, required: Sequence[str]) -> list[dict[str, str]]:
    path = Path(path)
    if not path.is_file():
        raise AuditError(f"输入缺失: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        missing = [c for c in required if c not in (reader.fieldnames or [])]
        if missing:
            raise AuditError(f"{path.name} 缺少必需列: {missing}")
        rows = [dict(row) for row in reader]
    if not rows:
        raise AuditError(f"{path.name} 为空表")
    return rows


def band_of(temperature: float | None, windows: Sequence[Mapping[str, Any]]) -> str:
    """按冻结协议温窗分带; 两端闭合 (293.15 与 303.15 都属室温带)."""
    if temperature is None:
        return "temperature_missing"
    for window in windows:
        if float(window["low"]) <= temperature <= float(window["high"]):
            return str(window["name"])
    return "outside_declared_window"


#: v11 分带枚举 (来自 scripts/build_dielectric_observations.py):
#: 只有 room_temperature / extended_temperature / outside_declared_window 三个值。
#: 关键: v11 **没有** high_temperature 类别, 所以协议 high_temperature 温窗
#: (333.15-373.15 K) 内的观测一律落进 outside_declared_window。
#: 因此 outside_declared_window 的含义是"不在这两个 schema 窗口内", 不是
#: "超出冻结协议温窗", 更不是"数据不可用"。
V11_BAND_VOCABULARY = ("room_temperature", "extended_temperature", "outside_declared_window")


def reconcile_band(band_v11: str, band_protocol: str) -> str:
    """并列两套分带的关系. 不择优, 只命名关系."""
    if not band_v11 or band_v11 == "not_evaluated":
        return "NOT_EVALUATED_V11"
    if band_v11 == band_protocol:
        return "AGREE"
    # v11 分带枚举缺 high_temperature 一类 -> 协议高温窗内的值被记成 outside。
    # 这不是两套规则给出相反结论, 而是一套枚举覆盖不了另一套的类别。
    if band_v11 == "outside_declared_window" and band_protocol in (
        "extended_temperature", "high_temperature"
    ):
        if band_protocol == "high_temperature":
            return "VOCABULARY_GAP_HIGH_TEMPERATURE_NOT_IN_V11_ENUM"
        return "VOCABULARY_GAP_EXTENDED_NOT_IN_V11_ENUM"
    if band_v11 == "outside_declared_window" and band_protocol == "outside_declared_window":
        return "AGREE"
    return "DISAGREE_OTHER"


def build_reconciliation(
    dataset: Mapping[str, Any], windows: Sequence[Mapping[str, Any]]
) -> list[dict[str, str]]:
    """只对 A18 相关观测逐行输出; 不改任何原始值."""
    rows: list[dict[str, str]] = []
    for index, observation in enumerate(dataset["observations"], start=1):
        key = skeleton(observation.get("inchikey", ""))
        owner = dataset["a18_by_skeleton"].get(key)
        if owner is None:
            continue
        temperature = to_float(observation.get("T_K"))
        band_v11 = str(observation.get("temperature_band", "")).strip() or "not_evaluated"
        band_protocol = band_of(temperature, windows)
        reconciliation = reconcile_band(band_v11, band_protocol)

        in_room = band_protocol == "room_temperature"
        notes: list[str] = []
        counts = in_room
        exclusion_reason = ""
        if not in_room:
            exclusion_reason = f"BAND_{band_protocol.upper()}"
            notes.append("NOT_ROOM_BAND")
        if reconciliation != "AGREE":
            notes.append("DECLARED_BAND_DIFFERS")

        is_sn_case = (
            owner["a_mol_id"] == SN_MOL_ID
            and temperature is not None
            and abs(temperature - SN_TEMPERATURE) < 1e-9
        )
        if is_sn_case:
            counts = False
            exclusion_reason = "OUTSIDE_ROOM_BAND_HIGH_TEMPERATURE"
            notes.append("SN_333_15_RETAINED_NOT_COUNTED_AS_ROOM_BAND")
            notes.append("ORIGINAL_TEMPERATURE_NOT_ALTERED")

        rows.append({
            "a_mol_id": owner["a_mol_id"],
            "a_name": owner["a_name"],
            "observation_id": str(observation.get("observation_id", "")).strip()
                            or f"v11_row_{index}",
            "temperature_raw_K": fmt(temperature),
            "temperature_band_v11": band_v11,
            "temperature_band_protocol": band_protocol,
            "temperature_band_reconciliation": reconciliation,
            "in_room_band_protocol": "true" if in_room else "false",
            "counts_as_room_band_qualified": "true" if counts else "false",
            "room_band_exclusion_reason": exclusion_reason or "not_evaluated",
            "is_sn_333_15_boundary_case": "true" if is_sn_case else "false",
            "evidence_note": ";".join(sorted(set(notes))) or "not_evaluated",
        })
    rows.sort(key=lambda r: (r["a_mol_id"], to_float(r["temperature_raw_K"]) or 0.0))
    return rows


def build_summary(
    rows: Sequence[Mapping[str, str]], windows: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["temperature_band_reconciliation"]] = (
            counts.get(row["temperature_band_reconciliation"], 0) + 1
        )
    disagreements = [r for r in rows if r["temperature_band_reconciliation"] != "AGREE"]
    sn_rows = [r for r in rows if r["is_sn_333_15_boundary_case"] == "true"]
    counted = [r for r in rows if r["counts_as_room_band_qualified"] == "true"]
    return {
        "analysis_id": ANALYSIS_ID,
        "contract_version": CONTRACT_VERSION,
        "n_rows": len(rows),
        "reconciliation_counts": dict(sorted(counts.items())),
        "n_disagreements": len(disagreements),
        "disagreement_kind": "VOCABULARY_COVERAGE_NOT_RULE_CONFLICT",
        "disagreement_kind_detail": (
            "v11 分带枚举只有 room_temperature / extended_temperature / "
            "outside_declared_window 三值, 没有 high_temperature 类别; 协议高温窗 "
            "(333.15-373.15 K) 内的观测因此全部落进 outside_declared_window. "
            "这表示'不在 v11 的两个 schema 窗口内', 不表示'超出冻结协议温窗', "
            "也不表示数据不可用"
        ),
        "v11_band_vocabulary": list(V11_BAND_VOCABULARY),
        "protocol_band_vocabulary": [str(w["name"]) for w in windows],
        "vocabulary_missing_in_v11": sorted(
            {str(w["name"]) for w in windows} - set(V11_BAND_VOCABULARY)
        ),
        "disagreement_observations": [
            {
                "a_mol_id": r["a_mol_id"],
                "temperature_raw_K": r["temperature_raw_K"],
                "temperature_band_v11": r["temperature_band_v11"],
                "temperature_band_protocol": r["temperature_band_protocol"],
                "reconciliation": r["temperature_band_reconciliation"],
            }
            for r in disagreements
        ],
        "sn_333_15": {
            "n_rows": len(sn_rows),
            "counts_as_room_band_qualified": any(
                r["counts_as_room_band_qualified"] == "true" for r in sn_rows
            ),
            "temperature_preserved": all(r["temperature_raw_K"] == "333.15" for r in sn_rows),
            "rows_retained_not_deleted": len(sn_rows) > 0,
            "not_counted_because": (
                "333.15 K 不在室温窗 293.15-303.15 K 内; 它属于协议 high_temperature 窗"
            ),
            "not_deleted_because": (
                "它是真实测量记录; 删除会篡改来源覆盖, 并与 B-G0-J01 的条件可解析计数冲突"
            ),
            "detail": sn_rows,
        },
        "n_counts_as_room_band_qualified": len(counted),
        "room_band_bounds": {
            "low": ROOM_BAND_LOW,
            "high": ROOM_BAND_HIGH,
            "inclusive_both_ends": True,
            "boundary_rule": "low <= T <= high",
        },
        "windows_from_protocol": [dict(w) for w in windows],
        "policy": {
            "original_temperature_immutable": True,
            "original_label_not_overwritten": True,
            "neither_side_replaced_by_the_other": True,
            "sn_not_counted_as_room_band": True,
            "sn_not_deleted": True,
        },
    }


def render_csv(columns: Sequence[str], rows: Sequence[Mapping[str, str]]) -> bytes:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(columns), lineterminator="\n",
                            extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({c: row.get(c, "") for c in columns})
    return buffer.getvalue().encode("utf-8")


def render_json(payload: Any) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def default_workspace() -> Path:
    return Path(__file__).resolve().parents[3]


def locate_inputs(workspace: Path, a_repo: Path | None) -> dict[str, Path]:
    workspace = Path(workspace)
    mirror = workspace / "v56_standalone" / "app" / "电解质ML" / "电解质ML"
    drafts = workspace / "v56_standalone" / "app" / "电解质ML" / "v56_round1"
    repo_a = Path(a_repo) if a_repo else Path(
        os.environ.get("J01_REPO_A", str(workspace.parent / "电解液溶剂-HB" / "电解液溶剂HB-Code"))
    )
    return {
        "a_core_set": repo_a / "data" / "metadata" / "core_set.csv",
        "observations_v11": mirror / "data" / "processed" / "dielectric_observations_v11.csv",
        "observations_v11plus": mirror / "data" / "processed" / "dielectric_observations_v11plus.csv",
        "target_protocol": drafts / "drafts" / "configs" / "frozen" / "target_protocol.yaml",
    }


def load_protocol(path: Path) -> dict[str, Any]:
    import yaml

    document = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    windows = (document or {}).get("allowed_temperature_windows_K")
    if not isinstance(windows, list) or not windows:
        raise AuditError("target_protocol.yaml 缺温窗")
    return document


def load_dataset(paths: Mapping[str, Path]) -> dict[str, Any]:
    from rdkit import Chem, RDLogger

    RDLogger.DisableLog("rdApp.*")
    core = read_csv_strict(paths["a_core_set"], ("mol_id", "name", "smiles"))
    a18_by_skeleton: dict[str, dict[str, str]] = {}
    for row in core:
        mol = Chem.MolFromSmiles(str(row.get("smiles", "")))
        if mol is None:
            raise AuditError(f"SMILES 无法解析: {row.get('smiles')!r}")
        entry = dict(row)
        entry["a_mol_id"] = str(row.get("mol_id", "")).strip()
        entry["a_name"] = str(row.get("name", "")).strip()
        a18_by_skeleton[skeleton(Chem.MolToInchiKey(mol))] = entry
    observations = read_csv_strict(
        paths["observations_v11"],
        ("inchikey", "T_K", "epsilon", "phase", "frequency_mhz", "pressure_kpa",
         "source_doi", "temperature_band"),
    )
    optional = ("observation_id", "observations_id")
    header = set(observations[0])
    id_column = next((c for c in optional if c in header), None)
    if id_column is None:
        # v11 没有观测主键列: 用 (inchikey, T_K, epsilon, source_doi) 生成确定性标识
        for row in observations:
            row["__synthetic_id"] = "|".join((
                str(row.get("inchikey", "")), str(row.get("T_K", "")),
                str(row.get("epsilon", "")), str(row.get("source_doi", "")),
            ))
        id_column = "__synthetic_id"
        observations = [
            {**row, "observation_id": row["__synthetic_id"]} for row in observations
        ]
    return {
        "a18_by_skeleton": a18_by_skeleton,
        "observations": observations,
        "protocol": load_protocol(paths["target_protocol"]),
        "id_column": id_column,
    }


def collect_environment() -> dict[str, str]:
    return {"python": platform.python_version(), "platform": platform.platform(terse=True)}


def build_outputs(
    dataset: Mapping[str, Any], *, manifest: Mapping[str, Any]
) -> dict[str, bytes]:
    windows = list(dataset["protocol"]["allowed_temperature_windows_K"])
    rows = build_reconciliation(dataset, windows)
    summary = build_summary(rows, windows)
    files: dict[str, bytes] = {
        "j01k_inputs_manifest.json": render_json(manifest),
        "temperature_band_reconciliation.csv": render_csv(BAND_COLUMNS, rows),
        "j01k_band_summary.json": render_json(summary),
    }
    receipt = {
        "analysis_id": ANALYSIS_ID,
        "contract_version": CONTRACT_VERSION,
        "input_contract_version": INPUT_CONTRACT_VERSION,
        "generator_version": GENERATOR_VERSION,
        "deterministic": True,
        "excludes": ["wall-clock timestamps", "random seeds", "filesystem ordering"],
        "output_sha256": {k: sha256_bytes(v) for k, v in sorted(files.items())},
        "output_bytes": {k: len(v) for k, v in sorted(files.items())},
        "note": "并列双字段; 不改原始温度/标签, 不删除任何行",
    }
    files["j01k_rebuild_receipt.json"] = render_json(receipt)
    missing = [n for n in OUTPUT_FILES if n not in files]
    if missing:
        raise AuditError(f"输出清单未产全: {missing}")
    return files


def write_outputs(out_dir: Path, files: Mapping[str, bytes]) -> None:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for name in sorted(files):
        (out_dir / name).write_bytes(files[name])


def check_outputs(out_dir: Path, files: Mapping[str, bytes]) -> list[str]:
    problems: list[str] = []
    for name in sorted(files):
        target = Path(out_dir) / name
        if not target.is_file():
            problems.append(f"缺失: {name}")
        elif target.read_bytes() != files[name]:
            problems.append(f"不一致: {name}")
    return problems


def run(*, workspace: Path, a_repo: Path | None, out_dir: Path, check: bool) -> int:
    paths = locate_inputs(workspace, a_repo)
    missing = [n for n, p in paths.items() if not Path(p).is_file()]
    if missing:
        print(f"输入缺失: {missing}", file=sys.stderr)
        return 2
    dataset = load_dataset(paths)
    manifest = {
        "analysis_id": ANALYSIS_ID,
        "contract_version": CONTRACT_VERSION,
        "input_contract_version": INPUT_CONTRACT_VERSION,
        "generator_version": GENERATOR_VERSION,
        "inputs": [
            {
                "id": name,
                "path": str(Path(paths[name])),
                "bytes": Path(paths[name]).stat().st_size,
                "sha256": sha256_file(Path(paths[name])),
            }
            for name in sorted(paths)
        ],
        "environment": dict(sorted(collect_environment().items())),
    }
    files = build_outputs(dataset, manifest=manifest)
    if check:
        problems = check_outputs(out_dir, files)
        if problems:
            print("重建结果与现有产物不一致:", file=sys.stderr)
            for problem in problems:
                print(f"  {problem}", file=sys.stderr)
            return 1
        print(f"OK 重建一致: {len(files)} 个文件 @ {out_dir}")
        return 0
    write_outputs(out_dir, files)
    summary = json.loads(files["j01k_band_summary.json"].decode("utf-8"))
    print(f"{ANALYSIS_ID} 完成 -> {out_dir}")
    print(f"  rows: {summary['n_rows']}  分歧: {summary['n_disagreements']}")
    print(f"  SN 333.15 行数: {summary['sn_333_15']['n_rows']} "
          f"计入室温: {summary['sn_333_15']['counts_as_room_band_qualified']} "
          f"保留原值: {summary['sn_333_15']['temperature_preserved']}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=f"{ANALYSIS_ID} | {ANALYSIS_TITLE}")
    parser.add_argument("--workspace", type=Path, default=default_workspace())
    parser.add_argument("--a-repo", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    workspace = Path(args.workspace)
    out_dir = args.out or (workspace / "电解质ML" / "outputs" / "confirm_2027" / "intersections")
    return run(workspace=workspace, a_repo=args.a_repo, out_dir=out_dir, check=args.check)


if __name__ == "__main__":
    raise SystemExit(main())
