"""Export the Week 24 deliverables -- the Axis B conditional-state arm and the DFT-level Axis A arm.

Week 24 buys the two things the repository had never computed: the Axis B
conditional-state rungs (C_1 = [LiM]+, C_2 = [Li(M)2]+) carried by a *redox*
quantity rather than an orbital energy, scaled to all 246 roster compounds; and
the DFT-level P_1 / P_2 themselves, which two repository documents had wrongly
registered as impossible because "ORCA is not in this toolchain".

Two lanes, not promoted, and none of the frozen numbers moves:
0.4091179943351143, 0.4766400383507876, 0.5861142332208197 and
0.6216672295270079 keep their own definitions, and the main scoreboard gets 0
attempts this week (cumulative stays at 12).
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from probes.export_results_common import (
    DEFAULT_OUTPUT_ROOT,
    copy_artifacts,
    read_json,
    run_verifiers,
    sha256_file,
    write_json,
    write_sha256s,
)

WEEK = "week24"

FROZEN_RED_LINES = {
    "data/dielectric_v03.csv": "ff2142936e06e04b329b70f8597574f75349e54ce876e9fff81309e6d35ccce4",
    "probes/l3_stage1_pilot_pool.csv": "b838febbca4d65975d1820ae9275215288968979b78756611cb031eb7c408b18",
    "probes/l3_backvalidation_prereg.json": "77f61a83b82de346292ff055c4f4c52003bccb6bfc98bf11813048abc6f0db98",
    "data/processed/dielectric_observations_v11plus.csv": "159b928f800a55969963da275ed05c30ce8a19cffc48353a9c490eec68a49af9",
    "probes/dielectric_r2_levers_prereg.json": "ab3503c037f05ac398b3c0c59d0e4845943d49fa5a5349fa46b8944f2bc1bdaa",
    "data/viscosity_v01.csv": "12dfa03f34284c93204d1054f75b5a342fd82094da0ca17cee372b4c581c5b26",
    "data/processed/w21_li_coordination_layer.csv": "48864109573f919ab320aa10d2b7b8e78532115e1f65228b16e75a76123eeedc",
}

FROZEN_READINGS = {
    "frozen_baseline": 0.4091179943351143,
    "frozen_headline": 0.4766400383507876,
    "single_representation_cross_seed": 0.5861142332208197,
    "w20_4_promoted_arm": 0.6216672295270079,
}

LANES: dict[str, dict[str, object]] = {
    "w24_condition_redox": {
        "title": "W24-1：Axis B 条件态首次实例化 —— C_1 氧化还原臂（[LiM]+）与 C_2 显式微溶剂化臂（[Li(M)2]+ 反式 2:1），GFN2-xTB，246 化合物 x 24 臂 = 5,904 次优化",
        "probe": "probes/w24_condition_redox.py",
        "prereg": "probes/w24_condition_redox_prereg.json",
        "summary": "probes/w24_condition_redox_summary.json",
        "report": "reports/w24_condition_redox.md",
        "tests": ("tests/test_w24_condition_redox.py",),
        "artifacts": (
            "data/processed/w24_condition_redox_layer.csv",
            "probes/artifacts/w24_rung_table.csv",
            "probes/artifacts/w24_displacement_law.csv",
            "probes/artifacts/w24_closed_form.csv",
            "probes/artifacts/w24_born_curves.csv",
            "probes/artifacts/w24_state_identity.csv",
            "probes/artifacts/w24_subsample_tau.csv",
            "probes/artifacts/w24_paper_gap_map.csv",
            "probes/artifacts/w24_anchor.csv",
            "probes/artifacts/w24_c2_qc.csv",
            "probes/artifacts/w24_ladder.csv",
            "probes/artifacts/w24_qc.csv",
            "probes/artifacts/w24_condition_redox_ladder.png",
            "probes/w24_condition_redox_figures.py",
            # The re-run is the repair, so its evidence travels with the delivery: the
            # first-pass checkpoint and layer that show the empty Li columns, the
            # column-by-column replay check, and its two outputs.
            "probes/artifacts/w24_condition_redox_records_firstpass.jsonl",
            "probes/artifacts/w24_condition_redox_layer_firstpass.csv",
            "probes/verify_w24_firstpass_reproduction.py",
            "probes/artifacts/w24_firstpass_reproduction.csv",
            "probes/artifacts/w24_firstpass_reproduction.json",
        ),
        "produces_reading": True,
        "promoted": False,
    },
    "w24_2_orca_dft": {
        "title": "W24-2：Axis A 的 P_1 / P_2 DFT 级首次实例化 —— ORCA 6.1.1 r2SCAN-3c 三态垂直 ΔSCF（气相 + CPCM/SMD 乙腈），并更正仓库里「ORCA 不在工具链里」的假登记",
        "probe": "probes/w24_2_orca_dft.py",
        "prereg": "probes/w24_2_orca_dft_prereg.json",
        "summary": "probes/w24_2_orca_dft_summary.json",
        "report": "reports/w24_2_orca_dft.md",
        "tests": ("tests/test_w24_2_orca_dft.py",),
        "artifacts": (
            "data/processed/w24_2_orca_dft_layer.csv",
            "probes/artifacts/w24_2_rung_table.csv",
            "probes/artifacts/w24_2_anchor_table.csv",
            "probes/artifacts/w24_2_anchor_paper_reference.csv",
            "probes/artifacts/w24_2_rung_vs_paper.csv",
            "probes/artifacts/w24_2_bridge.csv",
            "probes/artifacts/w24_2_unbound_anion.csv",
            "probes/artifacts/w24_2_hypotheses.csv",
            "probes/artifacts/w24_2_qc.csv",
            "probes/artifacts/w24_2_orca_bridge.png",
            "probes/w24_2_orca_dft_figures.py",
            "probes/artifacts/w24_2_no2_probe.log",
            "probes/artifacts/w24_2_repair_stdout.log",
        ),
        "produces_reading": True,
        "promoted": False,
    },
    "w24_3_posthoc": {
        "title": "W24-3\uff1a\u628a\u300c\u6570\u636e\u4e0d\u8db3\u300d\u672c\u8eab\u53d8\u6210\u8bfb\u6570 \u2014\u2014 \u5bf9 W24-1 / W24-2 \u51bb\u7ed3\u4ea7\u7269\u7684\u540e\u9a8c\u518d\u5206\u6790\uff08\u4e0d\u65b0\u589e\u67aa\u3001\u4e0d\u5360 shot\uff09",
        "probe": "probes/w24_3_posthoc.py",
        "prereg": None,
        "summary": None,
        "report": "reports/w24_3_posthoc_findings.md",
        "tests": ("tests/test_w24_3_posthoc.py",),
        "artifacts": (
            "probes/artifacts/w24_3_conclusions.csv",
            "probes/artifacts/w24_3_conclusions.json",
            "probes/artifacts/w24_3_sampling_law.csv",
            "probes/artifacts/w24_3_paper_axis_sigma.csv",
            "probes/artifacts/w24_3_axis_flip.csv",
            "probes/artifacts/w24_3_topk_decoupling.csv",
            "probes/artifacts/w24_3_data_adequacy.png",
            "probes/artifacts/w24_3_screening_reading.png",
            "probes/artifacts/w24_3_level_crosscheck.csv",
            "probes/artifacts/w24_3_level_crosscheck.png",
        ),
        "produces_reading": False,
        "promoted": False,
    },
}

LANE_KEYS = tuple(LANES)

CARRY_FORWARD = (
    ("README.md", "README.md"),
    ("reports/decisions_log.md", "decisions_log.md"),
    ("reports/week24_project_charter.md", "week24_project_charter.md"),
    ("reports/w24_2_orca_dft_charter.md", "w24_2_orca_dft_charter.md"),
    ("reports/w24_delivery_readme.md", "w24_delivery_readme.md"),
    ("reports/w21_framework_slot_map.md", "w21_framework_slot_map.md"),
    ("reports/week23_2_project_charter.md", "week23_2_project_charter.md"),
    ("paper/paper_zh_draft_v2.md", "paper_zh_draft_v2.md"),
    ("paper/build_paper_v2.py", "build_paper_v2.py"),
    ("paper/make_paper_docx.py", "make_paper_docx.py"),
    ("paper/_v2_head.md", "paper_v2_head.md"),
    ("paper/_v2_front.md", "paper_v2_front.md"),
    ("paper/_v2_sec29.md", "paper_v2_sec29.md"),
    ("paper/_v2_body_a.md", "paper_v2_body_a.md"),
    ("paper/_v2_body_b.md", "paper_v2_body_b.md"),
    ("paper/_v2_disc_extra.md", "paper_v2_disc_extra.md"),
    ("paper/_v2_concl.md", "paper_v2_concl.md"),
    ("paper/_v2_appendix.md", "paper_v2_appendix.md"),
    ("probes/export_week24_results.py", "export_week24_results.py"),
)

EXTERNAL_DELIVERABLES: tuple[tuple[str, str], ...] = ()

FIGURES: tuple[str, ...] = (
    "probes/artifacts/w24_condition_redox_ladder.png",
    "probes/artifacts/w24_2_orca_bridge.png",
    "probes/artifacts/w24_3_data_adequacy.png",
    "probes/artifacts/w24_3_screening_reading.png",
    "probes/artifacts/w24_3_level_crosscheck.png",
)

VERIFIERS = (
    "scripts/verify_four_core_registry.py --check",
    (
        "-m pytest tests/test_repo_hygiene.py tests/test_w24_condition_redox.py "
        "tests/test_w24_2_orca_dft.py tests/test_w24_3_posthoc.py "
        "-q -p no:cacheprovider"
    ),
)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _head_commit(source_root: Path) -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=source_root, capture_output=True, text=True, check=False
    )
    return (completed.stdout or "").strip()


def _worktree_status(source_root: Path) -> tuple[bool, int]:
    completed = subprocess.run(
        ["git", "status", "--porcelain"], cwd=source_root, capture_output=True, text=True, check=False
    )
    lines = [line for line in (completed.stdout or "").splitlines() if line.strip()]
    return bool(lines), len(lines)


def _frozen_red_lines() -> dict[str, dict[str, object]]:
    result: dict[str, dict[str, object]] = {}
    for relative, expected in FROZEN_RED_LINES.items():
        path = REPOSITORY_ROOT / relative
        measured = sha256_file(path) if path.is_file() else None
        result[relative] = {
            "expected_sha256": expected,
            "measured_sha256": measured,
            "intact": measured == expected,
        }
    return result


def _lane_payload(key: str) -> dict[str, object]:
    lane = LANES[key]
    declared: list[str] = [
        str(lane["probe"]),
        str(lane["report"]),
        *[str(item) for item in lane["tests"]],
        *[str(item) for item in lane["artifacts"]],
    ]
    if lane["prereg"]:
        declared.append(str(lane["prereg"]))
    if lane["summary"]:
        declared.append(str(lane["summary"]))
    prereg_block = None
    if lane["prereg"]:
        path = REPOSITORY_ROOT / str(lane["prereg"])
        payload = read_json(path)
        status = payload.get("status", payload.get("prereg_status"))
        prereg_block = {
            "path": str(lane["prereg"]),
            "sha256": sha256_file(path),
            "status": status,
            "locked_before_run": status == "locked_before_run",
        }
    summary_path = REPOSITORY_ROOT / str(lane["summary"]) if lane["summary"] else None
    return {
        "title": lane["title"],
        "probe": lane["probe"],
        "report": lane["report"],
        "report_sha256": sha256_file(REPOSITORY_ROOT / str(lane["report"]))
        if (REPOSITORY_ROOT / str(lane["report"])).is_file()
        else None,
        "tests": list(lane["tests"]),
        "artifacts": list(lane["artifacts"]),
        "prereg": prereg_block,
        "summary_path": lane["summary"],
        "summary_sha256": sha256_file(summary_path) if summary_path and summary_path.is_file() else None,
        "declared_files": declared,
        "declared_files_missing": [item for item in declared if not (REPOSITORY_ROOT / item).is_file()],
        "produces_reading": lane["produces_reading"],
        "promoted": lane["promoted"],
    }


def _missing_lane_keys() -> tuple[str, ...]:
    return tuple(key for key in LANE_KEYS if not (REPOSITORY_ROOT / str(LANES[key]["report"])).is_file())


README_TEXT = (REPOSITORY_ROOT / "reports/w24_delivery_readme.md").read_text(encoding="utf-8")


def _copy_external(week_root: Path) -> list[str]:
    written: list[str] = []
    for source, destination in EXTERNAL_DELIVERABLES:
        source_path = Path(source)
        if not source_path.is_file():
            continue
        destination_path = week_root / destination
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, destination_path)
        written.append(destination_path.relative_to(week_root).as_posix())
    return written


def export_results(*, output_root: Path, overwrite: bool) -> dict:
    week_root = output_root / WEEK
    if week_root.exists() and not overwrite:
        raise FileExistsError(str(week_root) + " already exists; pass --overwrite")

    frozen = _frozen_red_lines()
    if not all(bool(entry["intact"]) for entry in frozen.values()):
        broken = sorted(name for name, entry in frozen.items() if not entry["intact"])
        raise ValueError("a frozen red line moved: " + ", ".join(broken))

    worktree_dirty, dirty_paths = _worktree_status(REPOSITORY_ROOT)
    head_commit = _head_commit(REPOSITORY_ROOT)

    lanes_missing = list(_missing_lane_keys())
    lanes = {key: _lane_payload(key) for key in LANE_KEYS}
    for key, payload in lanes.items():
        prereg = payload["prereg"]
        if prereg is not None and not bool(dict(prereg)["locked_before_run"]):
            raise ValueError("lane " + key + " has no locked pre-registration")

    pairs: list[tuple[str, str]] = []
    for source, destination in CARRY_FORWARD:
        if (REPOSITORY_ROOT / source).is_file():
            pairs.append((source, destination))
    for key in LANE_KEYS:
        lane = LANES[key]
        for field in ("probe", "summary", "report"):
            value = lane[field]
            if value is not None:
                name = str(value)
                if (REPOSITORY_ROOT / name).is_file():
                    pairs.append((name, Path(name).name))
        if lane["prereg"]:
            name = str(lane["prereg"])
            if (REPOSITORY_ROOT / name).is_file():
                pairs.append((name, Path(name).name))
        for item in (*lane["tests"], *lane["artifacts"]):
            name = str(item)
            if (REPOSITORY_ROOT / name).is_file():
                pairs.append((name, Path(name).name))
    pairs.extend((figure, Path(figure).name) for figure in FIGURES)

    copied = copy_artifacts(REPOSITORY_ROOT, week_root, pairs)
    copied.extend(_copy_external(week_root))
    verification = run_verifiers(REPOSITORY_ROOT, VERIFIERS)

    promoted_lanes = sorted(key for key, payload in lanes.items() if bool(payload["promoted"]))
    reading_lanes = sorted(key for key, payload in lanes.items() if bool(payload["produces_reading"]))

    summary = {
        "schema_version": 1,
        "week": WEEK,
        "generated_at_utc": _utc_now(),
        "source_root": str(REPOSITORY_ROOT),
        "artifacts_commit": head_commit,
        "worktree_dirty": worktree_dirty,
        "worktree_dirty_paths": dirty_paths,
        "provenance_note": (
            "artifacts_commit is the commit that identifies the delivered bytes; a dirty "
            "worktree means no commit identifies them, so this field must be re-read after "
            "the follow-up commit."
        ),
        "lanes": lanes,
        "lanes_missing": lanes_missing,
        "reading_lanes": reading_lanes,
        "promoted_lanes": promoted_lanes,
        "main_scoreboard_attempts_delta": 0,
        "cumulative_main_scoreboard_attempts": 12,
        "frozen_readings": FROZEN_READINGS,
        "frozen_red_lines": frozen,
        "external_deliverables": [destination for _, destination in EXTERNAL_DELIVERABLES],
        "figures": [Path(figure).name for figure in FIGURES],
        "files": sorted(copied),
        "verification": verification,
        "verification_passed": bool(verification.get("passed")),
        "boundaries": [
            "W24-1 是 GFN2-xTB 半经验 + ALPB 隐式溶剂（绝热口径）；W24-2 是 ORCA r2SCAN-3c + CPCM/SMD（垂直口径）。两者绝不可比绝对值。",
            "不引用 Reaxys 数值；不把 Batt-P30K / RX-392 / THEMol 折进任何训练池或标签。",
            "本周 0 次主记分牌尝试，累计仍 12 次；四个冻结读数未动，七条红线逐条 sha256 复核。",
            "负结果照实进交付物：W24-1 的 H1 / H2 / H4 / H5 / H9 判否，W24-2 的 O3 判否。",
            "W24-1 首跑把 24 个 Li 列写成空、H2 成假阴性（n = 0）；已按同一份预注册重跑，45,018 个非 Li 单元逐位回放一致。",
            "W24-2 的 nitrogen dioxide 因自由基基态与预注册的中性态闭壳单重态冲突而按 QC 排除（读数一律 n = 27）。",
            "W24-3 是后验再分析：只读冻结产物、不新增预注册臂、不占 shot；其 R1–R5 不得被引用为预注册结论。",
            "H2 修复后判否的是一条真负结果：达到 0.5 e 的占比 c1 = 0.340 / c2 = 0.258（阈值 0.50，论文 11/12 但 N = 12）。",
        ],
    }
    write_json(week_root / "week24_summary.json", summary)
    write_json(week_root / "verification.json", verification)
    (week_root / "README.md").write_text(README_TEXT, encoding="utf-8", newline="\n")
    write_sha256s(week_root)
    return summary


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    result = export_results(output_root=args.output_root, overwrite=args.overwrite)
    print(
        json.dumps(
            {
                key: result[key]
                for key in (
                    "week",
                    "artifacts_commit",
                    "worktree_dirty",
                    "worktree_dirty_paths",
                    "lanes_missing",
                    "promoted_lanes",
                    "verification_passed",
                )
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if not result["lanes_missing"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
