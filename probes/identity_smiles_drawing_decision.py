#!/usr/bin/env python
"""Identity-layer drawing differences: mechanical provenance, and the no-rewrite recommendation.

`probes/pubchem_identity_layer_summary.json` registers 15 keys whose local SMILES
differs from the PubChem string.  Ten are stereo-only artifacts of the
`ConnectivitySMILES` fallback.  The remaining five look structural: charge
separation, tautomer choice, ring-branch order.  The manual registry (AC-7) has
them down as a human decision on whether to rewrite the local SMILES.

This probe takes no decision on anyone's behalf.  It builds the mechanical record
a decision needs:

  gate A  the five pairs are identity-identical (pubchem_inchikey == inchikey and
          identity_check == roundtrip_match);
  gate B  every local SMILES is a byte-for-byte substring of a declared source
          file, i.e. the identity layer COPIES it and never authors it;
  gate C  the frozen red-line sources still carry those exact strings, so an
          in-place rewrite would either break a frozen digest or be silently
          reverted the next time the generator runs;
  gate D  this probe wrote nothing under data/ and every frozen red-line digest
          still reproduces.

The recommendation is therefore do-not-rewrite, registered as
`recommended_no_rewrite_awaiting_human_confirmation`.  The recommendation is
machine-checked; the decision stays with the author.

No model is fitted, no R2 is reported, no network call is made.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import UTC
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

# A literal backtick, kept out of the source text so no editor can mangle it.
TICK = chr(96)

IDENTITY_MAP_PATH = REPOSITORY_ROOT / "data/reference/identity_map.csv"
IDENTITY_SUMMARY_PATH = REPOSITORY_ROOT / "probes/pubchem_identity_layer_summary.json"
SUMMARY_PATH = REPOSITORY_ROOT / "probes/identity_smiles_drawing_decision_summary.json"
REPORT_PATH = REPOSITORY_ROOT / "reports/identity_smiles_drawing_decision.md"

SOURCE_PATHS: tuple[Path, ...] = (
    REPOSITORY_ROOT / "data/dielectric_v03.csv",
    REPOSITORY_ROOT / "data/processed/ilthermo_new_compounds.csv",
    REPOSITORY_ROOT / "data/reference/dielectric_molecule_aliases.csv",
)

FROZEN_RED_LINES: Mapping[str, str] = {
    "data/dielectric_v03.csv": "ff2142936e06e04b329b70f8597574f75349e54ce876e9fff81309e6d35ccce4",
    "probes/l3_stage1_pilot_pool.csv": "b838febbca4d65975d1820ae9275215288968979b78756611cb031eb7c408b18",
    "probes/l3_backvalidation_prereg.json": "77f61a83b82de346292ff055c4f4c52003bccb6bfc98bf11813048abc6f0db98",
    "data/processed/dielectric_observations_v11plus.csv": "159b928f800a55969963da275ed05c30ce8a19cffc48353a9c490eec68a49af9",
    "probes/dielectric_r2_levers_prereg.json": "ab3503c037f05ac398b3c0c59d0e4845943d49fa5a5349fa46b8944f2bc1bdaa",
    "data/viscosity_v01.csv": "12dfa03f34284c93204d1054f75b5a342fd82094da0ca17cee372b4c581c5b26",
}

GENERATOR_PATH = REPOSITORY_ROOT / "probes/pubchem_identity_layer.py"
DECLARED_COPY_STATEMENT = (
    "the identity layer copies the local SMILES out of its declared sources and"
    " never authors one: load_roster() reads ROSTER_PATH = data/dielectric_v03.csv,"
    " the ILThermo branch reads data/processed/ilthermo_new_compounds.csv, and both"
    " end at row[smiles] = str(target[smiles]) -- a verbatim copy"
)

EXPECTED_ROWS = 314
EXPECTED_MATCH = 299
EXPECTED_DIFFER = 15
EXPECTED_STEREO_ONLY = 10
EXPECTED_STRUCTURAL = 5

REWRITE_DECISION_STATUS = "recommended_no_rewrite_awaiting_human_confirmation"

DIFFERENCE_FAMILY_BY_KEY: Mapping[str, str] = {
    "FSXANJBLYFVXEU-UHFFFAOYSA-N": "charge_separation_salt_vs_neutral",
    "OOKUTCYPKPJYFV-UHFFFAOYSA-N": "charge_separation_salt_vs_neutral",
    "LBHLGZNUPKUZJC-UHFFFAOYSA-N": "amide_imide_plus_ring_branch_order",
    "OHLUUHNLEMFGTQ-UHFFFAOYSA-N": "tautomer_amide_vs_imidic_acid",
    "ZHNUHDYFZUAESO-UHFFFAOYSA-N": "tautomer_amide_vs_imidic_acid",
}


def sha256_bytes(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def read_rows(path: Path) -> list[dict[str, str]]:
    with open(path, "r", encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _utc_now() -> str:
    from datetime import datetime

    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_summary() -> dict[str, Any]:
    map_rows = read_rows(IDENTITY_MAP_PATH)
    layer = json.loads(IDENTITY_SUMMARY_PATH.read_text(encoding="utf-8"))
    differing = list(layer.get("smiles_differing_keys") or [])
    structural = [entry for entry in differing if entry.get("difference_kind") == "structural"]
    stereo_only = [entry for entry in differing if entry.get("difference_kind") != "structural"]
    by_key = {row.get("inchikey", ""): row for row in map_rows}
    source_blobs = {
        path.relative_to(REPOSITORY_ROOT).as_posix(): path.read_bytes() for path in SOURCE_PATHS
    }

    items: list[dict[str, Any]] = []
    for entry in sorted(structural, key=lambda item: str(item.get("inchikey", ""))):
        key = str(entry.get("inchikey", ""))
        row = by_key.get(key, {})
        local = str(entry.get("local_smiles", ""))
        token = local.encode("utf-8")
        carriers = sorted(rel for rel, blob in source_blobs.items() if token in blob)
        frozen_carriers = sorted(rel for rel in carriers if rel in FROZEN_RED_LINES)
        if frozen_carriers:
            authority = "frozen_red_line"
        elif carriers:
            authority = "derived_table"
        else:
            authority = "authored_in_identity_layer"
        items.append(
            {
                "inchikey": key,
                "name": str(entry.get("name", "")),
                "local_smiles": local,
                "pubchem_smiles": str(entry.get("pubchem_smiles", "")),
                "pubchem_cid": row.get("pubchem_cid", ""),
                "identity_check": row.get("identity_check", ""),
                "pubchem_inchikey": row.get("pubchem_inchikey", ""),
                "copied_verbatim_into_the_identity_layer": row.get("smiles") == local,
                "identity_identical": (
                    bool(row)
                    and row.get("pubchem_inchikey") == key
                    and row.get("identity_check") == "roundtrip_match"
                    and row.get("smiles") == local
                ),
                "carrier_files": carriers,
                "frozen_carrier_files": frozen_carriers,
                "source_authority": authority,
                "difference_family": DIFFERENCE_FAMILY_BY_KEY.get(key, "unclassified"),
            }
        )

    frozen_now = {rel: sha256_file(REPOSITORY_ROOT / rel) for rel in FROZEN_RED_LINES}
    inputs = {
        IDENTITY_MAP_PATH.relative_to(REPOSITORY_ROOT).as_posix(): {
            "bytes": len(IDENTITY_MAP_PATH.read_bytes()),
            "sha256": sha256_file(IDENTITY_MAP_PATH),
        },
        IDENTITY_SUMMARY_PATH.relative_to(REPOSITORY_ROOT).as_posix(): {
            "bytes": len(IDENTITY_SUMMARY_PATH.read_bytes()),
            "sha256": sha256_file(IDENTITY_SUMMARY_PATH),
        },
        **{
            rel: {"bytes": len(blob), "sha256": sha256_bytes(blob)}
            for rel, blob in source_blobs.items()
        },
    }

    counts = {
        "identity_rows": len(map_rows),
        "differing_keys_total": len(differing),
        "stereo_only": len(stereo_only),
        "structural": len(structural),
        "structural_in_frozen_red_line_source": sum(1 for item in items if item["frozen_carrier_files"]),
        "structural_in_derived_table": sum(
            1 for item in items if item["carrier_files"] and not item["frozen_carrier_files"]
        ),
        "structural_authored_in_identity_layer": sum(1 for item in items if not item["carrier_files"]),
    }

    gates = {
        "A_identity_identical": {
            "statement": "五对全部共用一个 InChIKey，且 identity_check == roundtrip_match",
            "measured": sum(1 for item in items if item["identity_identical"]),
            "expected": EXPECTED_STRUCTURAL,
            "passed": len(items) == EXPECTED_STRUCTURAL
            and all(item["identity_identical"] for item in items),
        },
        "B_copied_never_authored": {
            "statement": "每条本地串都是某个声明来源文件里的逐字节子串（即身份层只复制、不撰写）",
            "measured": sum(1 for item in items if item["carrier_files"]),
            "expected": EXPECTED_STRUCTURAL,
            "passed": all(item["carrier_files"] for item in items),
        },
        "C_frozen_sources_still_carry_the_string": {
            "statement": "冻结名册仍逐字携带五条中的四条",
            "measured": sum(1 for item in items if item["frozen_carrier_files"]),
            "expected": 4,
            "passed": sum(1 for item in items if item["frozen_carrier_files"]) == 4,
        },
        "D_nothing_rewritten": {
            "statement": "本探针不写任何 data/ 文件，六件冻结件 digest 逐位复现",
            "frozen_red_lines": {
                rel: {
                    "expected": digest,
                    "measured": frozen_now[rel],
                    "intact": frozen_now[rel] == digest,
                }
                for rel, digest in sorted(FROZEN_RED_LINES.items())
            },
            "writes_under_data": 0,
            "passed": all(frozen_now[rel] == digest for rel, digest in FROZEN_RED_LINES.items()),
        },
    }

    counts["smiles_match"] = int((layer.get("smiles_match_counts") or {}).get("match", 0))

    return {
        "schema_version": 1,
        "task": "identity_smiles_drawing_decision",
        "run_telemetry": {
            "generated_at_utc": _utc_now(),
            "network_calls": 0,
            "models_fitted": 0,
            "r2_reported": False,
            "writes_under_data": 0,
            "run_mode": "offline",
        },
        "inputs": inputs,
        "identity_layer_contract": {
            "declared_copy_statement": DECLARED_COPY_STATEMENT,
            "generator": GENERATOR_PATH.relative_to(REPOSITORY_ROOT).as_posix(),
            "generator_sha256": sha256_file(GENERATOR_PATH),
        },
        "counts": counts,
        "structural_differences": items,
        "gates": gates,
    }


GEOMETRY_FEATURE_SOURCES: tuple[str, ...] = (
    "data/processed/dielectric_physical_features_v03.csv",
    "data/processed/dielectric_physical_features_v11plus_new.csv",
)


def _geometry_census(items: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    available = {
        rel: (REPOSITORY_ROOT / rel).read_text(encoding="utf-8", errors="ignore")
        for rel in GEOMETRY_FEATURE_SOURCES
        if (REPOSITORY_ROOT / rel).exists()
    }
    per_item = {
        str(item["inchikey"]): sorted(rel for rel, text in available.items() if str(item["inchikey"]) in text)
        for item in items
    }
    with_features = sorted(key for key, files in per_item.items() if files)
    return {
        "sources": sorted(available),
        "per_key": per_item,
        "keys_with_geometry_derived_features": with_features,
        "n_keys_with_geometry_derived_features": len(with_features),
        "statement": (
            "这些键携带几何派生特征，故画法不是装饰性的：就地改写 SMILES 会静默移动它们的物性特征，除非同步重生特征表"
        ),
    }


def build_full_summary() -> dict[str, Any]:
    summary = build_summary()
    census = _geometry_census(summary["structural_differences"])
    summary["geometry_derived_feature_census"] = census
    summary["gates"]["E_drawing_form_feeds_geometry"] = {
        "statement": census["statement"],
        "measured": census["n_keys_with_geometry_derived_features"],
        "expected": 4,
        "passed": census["n_keys_with_geometry_derived_features"] == 4,
    }
    summary["decision"] = {
        "status": REWRITE_DECISION_STATUS,
        "no_data_change_made": True,
        "recommendation": "不改写本地 SMILES，保留从来源复制来的原串",
        "reasons": [
            "五对全部身份同一：InChIKey 未变，而 InChIKey 正是下游一切联表所用的键（名册 246 + lowfreq 50 + ilthermo 47 = 314），所以改写既不移动任何联表、也不改变身份",
            "五条本地串里有四条落在冻结红线 data/dielectric_v03.csv 内，第五条落在 data/processed/ilthermo_new_compounds.csv 内；身份层只是逐字复制它们，所以就地改写要么打破冻结 digest、要么在生成器下次运行时被静默还原",
            "这些差异正是标准 InChI 有意归一化的类别（盐 vs 电中性、酰胺 vs 亚胺酸），外加一处环支链顺序，所以本地串没有丢任何「键仍然保留」的信息",
            "五条键里有四条携带几何派生特征，所以改写不是一次文本编辑，而是一次迁移：它要求同步重生那些特征表并出新冻结版本，而不是就地改字",
        ],
        "if_the_author_chooses_to_rewrite": (
            "请走版本化迁移：出新的冻结表，并在同一次变更里重生特征表，再重跑身份层，"
            "让本探针保持全绿、并把台账里的 pin 一并更新"
        ),
        "decision_owner": "作者本人；本探针只提供机械取证记录",
    }
    summary["caveats"] = [
        "这里证明的是身份同一，描述符是否同一未测：五对里有四对差在电荷分离或互变异构选择上，即便标准 InChIKey 相同，这仍可能移动 RDKit 与几何描述符",
        "FSXANJBLYFVXEU 这条还带着已登记的 CID 冲突（本地 ILThermo 表记 60196376、PubChem 记 57351531），那是另一笔缺陷，本探针不碰它",
        "那十条「仅立体层」是 ConnectivitySMILES 回退的假警报，不是画法差异，不在本次裁决范围内",
    ]
    return summary
def render_report(summary: Mapping[str, Any]) -> str:
    counts = summary["counts"]
    census = summary["geometry_derived_feature_census"]
    decision = summary["decision"]
    telemetry = summary["run_telemetry"]
    lines: list[str] = []
    lines.append("# 身份层画法差异：机械溯源与「不改写」裁决建议")
    lines.append("")
    lines.append(
        "**任务**："
        + TICK
        + str(summary["task"])
        + TICK
        + " ｜ **生成时刻**："
        + str(telemetry["generated_at_utc"])
        + " ｜ **网络调用**："
        + str(telemetry["network_calls"])
        + " ｜ **拟合模型**："
        + str(telemetry["models_fitted"])
        + " ｜ **产出 R²**：无（"
        + str(telemetry["r2_reported"]).lower()
        + "）"
    )
    lines.append("")
    lines.append("**结论（建议，非裁决）**：" + TICK + str(decision["status"]) + TICK + "；" + str(decision["recommendation"]))
    lines.append("")
    lines.append("## 1. 事实底座")
    lines.append("")
    lines.append("| 项 | 数 |")
    lines.append("|---|---|")
    lines.append("| 身份层行数 | " + str(counts["identity_rows"]) + " |")
    lines.append("| SMILES 相同 | " + str(counts["smiles_match"]) + " |")
    lines.append("| SMILES 不同（合计） | " + str(counts["differing_keys_total"]) + " |")
    lines.append("| 其中仅立体层（ConnectivitySMILES 假警报） | " + str(counts["stereo_only"]) + " |")
    lines.append("| 其中看似结构层（本报告对象） | " + str(counts["structural"]) + " |")
    lines.append("| 本地串落在**冻结件**里 | " + str(counts["structural_in_frozen_red_line_source"]) + " |")
    lines.append("| 本地串落在派生表里 | " + str(counts["structural_in_derived_table"]) + " |")
    lines.append("| 本地串由身份层自己撰写 | " + str(counts["structural_authored_in_identity_layer"]) + " |")
    lines.append("")
    lines.append("## 2. 五条逐条")
    lines.append("")
    lines.append("| InChIKey | 名称 | 本地 SMILES | PubChem SMILES | 本地串出处 | 出处性质 | identity_check |")
    lines.append("|---|---|---|---|---|---|---|")
    for item in summary["structural_differences"]:
        lines.append(
            "| "
            + TICK + str(item["inchikey"]) + TICK
            + " | " + str(item["name"])
            + " | " + TICK + str(item["local_smiles"]) + TICK
            + " | " + TICK + str(item["pubchem_smiles"]) + TICK
            + " | " + ", ".join(item["carrier_files"])
            + " | " + str(item["source_authority"])
            + " | " + str(item["identity_check"]) + " |"
        )
    lines.append("")
    lines.append("## 3. 五道门")
    lines.append("")
    lines.append("| 门 | 含义 | 实测 | 期望 | 判定 |")
    lines.append("|---|---|---|---|---|")
    for name, gate in summary["gates"].items():
        if "frozen_red_lines" in gate:
            measured = (
                str(len(gate["frozen_red_lines"]))
                + " 条冻结件（"
                + (
                    "全 INTACT"
                    if all(entry["intact"] for entry in gate["frozen_red_lines"].values())
                    else "有漂移"
                )
                + "）"
            )
            expected = str(len(gate["frozen_red_lines"]))
        else:
            measured = str(gate["measured"])
            expected = str(gate["expected"])
        lines.append(
            "| " + TICK + str(name) + TICK
            + " | " + str(gate["statement"])
            + " | " + measured
            + " | " + expected
            + " | " + ("通过" if gate["passed"] else "**未通过**") + " |"
        )
    lines.append("")
    lines.append("## 4. 裁决建议与理由")
    lines.append("")
    for reason in decision["reasons"]:
        lines.append("- " + str(reason))
    lines.append("")
    lines.append("**若作者仍要改写**：" + str(decision["if_the_author_chooses_to_rewrite"]))
    lines.append("")
    lines.append("**几何派生特征涉及的键**（" + str(census["n_keys_with_geometry_derived_features"]) + " 个）：" + ", ".join(census["keys_with_geometry_derived_features"]))
    lines.append("")
    lines.append("## 5. 边界与已知未核")
    lines.append("")
    for caveat in summary["caveats"]:
        lines.append("- " + str(caveat))
    lines.append("")
    lines.append("## 6. 复现")
    lines.append("")
    lines.append(r"    .\.venv\Scripts\python.exe probes\identity_smiles_drawing_decision.py")
    lines.append(r"    .\.venv\Scripts\python.exe probes\identity_smiles_drawing_decision.py --check")
    lines.append("")
    return chr(10).join(lines) + chr(10)


def write_outputs(summary: Mapping[str, Any]) -> None:
    SUMMARY_PATH.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + chr(10),
        encoding="utf-8",
        newline=chr(10),
    )
    REPORT_PATH.write_text(render_report(summary), encoding="utf-8", newline=chr(10))


def check() -> list[str]:
    problems: list[str] = []
    for path in (SUMMARY_PATH, REPORT_PATH):
        if not path.exists():
            problems.append("missing deliverable: " + path.name)
    if problems:
        return problems
    on_disk = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
    fresh = build_full_summary()
    left = {key: value for key, value in on_disk.items() if key != "run_telemetry"}
    right = {key: value for key, value in fresh.items() if key != "run_telemetry"}
    if left != right:
        problems.append("summary no longer recomputes to itself")
    for rel, meta in (fresh.get("inputs") or {}).items():
        if sha256_file(REPOSITORY_ROOT / rel) != meta.get("sha256"):
            problems.append("pinned input changed on disk: " + rel)
    if REPORT_PATH.read_text(encoding="utf-8") != render_report(on_disk):
        problems.append("report is not render(summary)")
    return problems


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="recompute and compare against the artifacts already on disk",
    )
    args = parser.parse_args(argv)
    if args.check:
        problems = check()
        for problem in problems:
            print("FAIL: " + problem)
        print("identity_smiles_drawing_decision --check: " + ("OK" if not problems else "FAILED"))
        return 0 if not problems else 2
    summary = build_full_summary()
    write_outputs(summary)
    passed = sum(1 for gate in summary["gates"].values() if gate["passed"])
    print("wrote " + SUMMARY_PATH.name + " and " + REPORT_PATH.name)
    print(
        "structural="
        + str(summary["counts"]["structural"])
        + " gates="
        + str(passed)
        + "/"
        + str(len(summary["gates"]))
        + " status="
        + str(summary["decision"]["status"])
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
