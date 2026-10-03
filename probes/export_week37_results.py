"""Export the Week 37 deliverables.

Week 37 is a post hoc governance round: it closes the remaining open README section 11
items without taking a main-scoreboard shot (cumulative stays at 19).

  * W37-A (endpoint tolerance guard) turns the Week 36-A endpoint rule into an enforced
    guard.  It re-reads the 1e-12 tolerance from the Week 36 registry (R5), then scans
    ``probes`` / ``scripts`` / ``src`` / ``tests`` with an AST + literal-substring pass
    for bitwise endpoint comparisons.  561 files scanned, 94 endpoint comparison sites
    found, 0 forbidden.  A synthetic ``if value == 0.5861142332208197:`` is caught while
    the legal ``abs(a - b) <= ENDPOINT_TOLERANCE`` form is not.
  * W37-B (gate admission export) wires the Week 36-D admission list into the
    export/verify link: the paper appendix's reduction-axis citation points are checked
    mechanically at export time.  Appendix A binds 7 citation points across 2 table rows
    (5 reduction / 2 oxidation); every mark comes from the Week 34-A guard, and a
    synthetic deleted/renamed registry row makes the checker exit non-zero.
  * W37-C (v2 backfill) answers README section 11 item 16 by backfilling the 12 drift
    blocks from the shipped draft into the assembly sources.  The rebuild is byte
    identical to the shipped draft, whose sha256 does not change.

The four frozen readings keep their own definitions: 0.4091179943351143,
0.4766400383507876, 0.5861142332208197, 0.6216672295270079.
"""
from __future__ import annotations

import argparse
import json
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

WEEK = "week37"

FROZEN_RED_LINES = {
    "paper/paper_zh_draft_v2.md":
        "dfb3b282f8ccf76653d244a6a2c618d92a6e12003d012b81cca9f08dc9c6e78e",
    "paper/_v2_body_b.md":
        "e1d5fb38e71cd1336bbdc8caba3b5b4c57822072c84cbc8443268fdb2650751d",
    "paper/_v2_appendix.md":
        "4677c9ece09ac0fa3b42b7b0a2e28d018d4665adfe6668aef6c620d1fd99d8ef",
    "paper/_v2_concl.md":
        "f7feb3c4795f0a2839d282f7ffc22e542eed7542cede164ca44406aefe47d4b2",
    "paper/_v2_disc_extra.md":
        "5916a27e58233161021640e75647a3ff6ff38089bb8935763298ca2ac6ac2257",
    "paper/build_paper_v2.py":
        "be1121e4216cc48e1dc62b7ae08c7ea084c22bbfc194aabda47f2b318b80f8c7",
    "paper/_v2_splices.json":
        "cd25c9de88826b17262999045f815085f464e117a6e1aad714273db6f175d70a",
    "probes/artifacts/w35_gated_reference_register.csv":
        "b201c776ff66bf07cf85a2e68039d2547f31da3d59845e62a3641f98b69b098c",
    "probes/artifacts/w33_kendall_null_budget.csv":
        "eb16242737abc9b0c8308fb855a2f52cc3a3ba3b755726a67b4e480b0afe0b28",
    "probes/artifacts/w32_rank_stability.json":
        "106983b41e84808b331043927df3aba9afc9addcebdf985d9845d4330e2e8e95",
    "probes/artifacts/w34_channel_dashboard.csv":
        "f5db0cd34e8e66cdc4ccf34388bf24fddabfc97ccb4e2f739b5ef6f2629f62ca",
    "data/processed/redox_state_legality_registry.csv":
        "a01272b3e75514a609295275d18c82c39fb65c5bc27056feb4ed8c6cd0c6b60d",
    "data/processed/four_core_key_registry.csv":
        "e42885eb43779b7a4d472da88fefe018fe94150ff5b6fba86b3ed9bc83dc8bee",
}

FROZEN_READINGS = {
    "frozen_baseline": 0.4091179943351143,
    "frozen_headline": 0.4766400383507876,
    "single_representation_cross_seed": 0.5861142332208197,
    "w20_4_promoted_arm": 0.6216672295270079,
}

LANES: dict[str, dict[str, object]] = {
    "w37_v2_backfill": {
        "title": "W37-C 后验回灌：README §11 第 16 条装配源回灌（12 段；重建逐字节相等；不占 shot）",
        "probe": "probes/w37_v2_backfill.py",
        "prereg": None,
        "summary": "probes/artifacts/w37_v2_backfill_summary.json",
        "report": "reports/w37_v2_backfill.md",
        "tests": ("tests/test_w37_v2_backfill.py",),
        "artifacts": (
            "probes/artifacts/w37_v2_backfill_inventory.csv",
            "paper/_v2_splices.json",
            "paper/_v2_splice_sec381_dc267936.md",
            "paper/_v2_splice_sec310_7fdd4a5f.md",
            "paper/_v2_splice_sec314_f46f67ab.md",
        ),
        "produces_reading": False,
        "promoted": False,
    },
    "w37_endpoint_tolerance_guard": {
        "title": "W37-A 后验守卫件：端点判等容差守卫入导出链（AST 扫描 561 文件；不占 shot）",
        "probe": "probes/w37_endpoint_tolerance_guard.py",
        "prereg": None,
        "summary": "probes/artifacts/w37_endpoint_tolerance_guard_summary.json",
        "report": "reports/w37_endpoint_tolerance_guard.md",
        "tests": ("tests/test_w37_endpoint_tolerance_guard.py",),
        "artifacts": (
            "probes/artifacts/w37_endpoint_compare_sites.csv",
        ),
        "produces_reading": False,
        "promoted": False,
    },
    "w37_gate_admission_export": {
        "title": "W37-B 后验治理件：准入件接进交付/导出链路（论文附录引用点机械校验；不占 shot）",
        "probe": "probes/w37_gate_admission_export.py",
        "prereg": None,
        "summary": "probes/artifacts/w37_gate_admission_export_summary.json",
        "report": "reports/w37_gate_admission_export.md",
        "tests": ("tests/test_w37_gate_admission_export.py",),
        "artifacts": (
            "probes/artifacts/w37_gate_admission_export_sites.csv",
            "scripts/check_redox_admission.py",
        ),
        "produces_reading": False,
        "promoted": False,
    },
}

CARRY_FORWARD = (
    ("README.md", "README.md"),
    ("reports/decisions_log.md", "decisions_log.md"),
    ("reports/week35_project_charter.md", "week35_project_charter.md"),
    ("reports/week35_delivery_readme.md", "week35_delivery_readme.md"),
    ("reports/week36_project_charter.md", "week36_project_charter.md"),
    ("reports/week36_delivery_readme.md", "week36_delivery_readme.md"),
    ("reports/week37_project_charter.md", "week37_project_charter.md"),
    ("reports/week37_delivery_readme.md", "week37_delivery_readme.md"),
    ("reports/work_log_week1_to_week36.md", "work_log_week1_to_week36.md"),
    ("reports/w36_endpoint_rule.md", "w36_endpoint_rule.md"),
    ("reports/w36_channel_noise_floor.md", "w36_channel_noise_floor.md"),
    ("reports/w36_gate_admission.md", "w36_gate_admission.md"),
    ("reports/w36_v2_source_correction.md", "w36_v2_source_correction.md"),
    ("paper/paper_zh_draft_v2.md", "paper_zh_draft_v2.md"),
    ("paper/make_paper_docx_template.py", "make_paper_docx_template.py"),
    ("probes/export_week35_results.py", "export_week35_results.py"),
    ("probes/export_week36_results.py", "export_week36_results.py"),
)

LANE_KEYS = tuple(LANES)

EXTERNAL_DELIVERABLES: tuple[tuple[str, str], ...] = ()

# No new figure is produced this round (W37 is a governance round).  The two Week 32
# figures that the W36-B / W36-C display layer builds on are carried so the package stays
# self-contained.
FIGURES: tuple[str, ...] = (
    "probes/artifacts/w32_fig_noise_floor.png",
    "probes/artifacts/w32_fig_fidelity_law.png",
)

VERIFIERS = (
    "scripts/verify_four_core_registry.py --check",
    "scripts/check_paper_artifact_consistency.py",
    (
        "-m pytest tests/test_repo_hygiene.py tests/test_w37_endpoint_tolerance_guard.py "
        "tests/test_w37_gate_admission_export.py tests/test_w37_v2_backfill.py "
        "tests/test_w36_endpoint_rule.py tests/test_w36_gate_admission.py "
        "tests/test_w35_paper_r6_correction.py tests/test_w35_redox_gate_consumers.py "
        "-q -p no:cacheprovider"
    ),
)

DELIVERY_README_PATH = REPOSITORY_ROOT / "reports/week37_delivery_readme.md"
README_TEXT = (DELIVERY_README_PATH.read_text(encoding="utf-8")
               if DELIVERY_README_PATH.is_file()
               else "# Week 37 交付包\n\n"
                    "本包由 probes/export_week37_results.py 生成；交付说明见 "
                    "reports/week37_delivery_readme.md。\n")
BACKFILL_SUMMARY_PATH = REPOSITORY_ROOT / "probes/artifacts/w37_v2_backfill_summary.json"
GUARD_SUMMARY_PATH = REPOSITORY_ROOT / "probes/artifacts/w37_endpoint_tolerance_guard_summary.json"
ADMISSION_SUMMARY_PATH = REPOSITORY_ROOT / "probes/artifacts/w37_gate_admission_export_summary.json"


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _head_commit(source_root: Path) -> str:
    completed = subprocess.run(["git", "rev-parse", "HEAD"], cwd=source_root,
                               capture_output=True, text=True, check=False)
    return (completed.stdout or "").strip()


def _worktree_status(source_root: Path) -> tuple[bool, int]:
    completed = subprocess.run(["git", "status", "--porcelain"], cwd=source_root,
                               capture_output=True, text=True, check=False)
    lines = [line for line in (completed.stdout or "").splitlines() if line.strip()]
    return bool(lines), len(lines)


def _frozen_red_lines() -> dict[str, dict[str, object]]:
    result: dict[str, dict[str, object]] = {}
    for relative, expected in FROZEN_RED_LINES.items():
        path = REPOSITORY_ROOT / relative
        measured = sha256_file(path) if path.is_file() else None
        result[relative] = {"expected_sha256": expected, "measured_sha256": measured,
                            "intact": measured == expected}
    return result


def _lane_payload(key: str) -> dict[str, object]:
    lane = LANES[key]
    declared: list[str] = [str(lane["probe"]), str(lane["report"]),
                           *[str(item) for item in lane["tests"]],
                           *[str(item) for item in lane["artifacts"]]]
    if lane["prereg"]:
        declared.append(str(lane["prereg"]))
    if lane["summary"]:
        declared.append(str(lane["summary"]))
    prereg_block = None
    if lane["prereg"]:
        path = REPOSITORY_ROOT / str(lane["prereg"])
        payload = read_json(path)
        status = payload.get("status", payload.get("prereg_status"))
        prereg_block = {"path": str(lane["prereg"]), "sha256": sha256_file(path),
                        "status": status, "revision": payload.get("revision"),
                        "locked_before_run": status == "locked_before_run"}
    summary_path = REPOSITORY_ROOT / str(lane["summary"]) if lane["summary"] else None
    report_path = REPOSITORY_ROOT / str(lane["report"])
    return {"title": lane["title"], "probe": lane["probe"], "report": lane["report"],
            "report_sha256": sha256_file(report_path) if report_path.is_file() else None,
            "tests": list(lane["tests"]), "artifacts": list(lane["artifacts"]),
            "prereg": prereg_block, "summary_path": lane["summary"],
            "summary_sha256": (sha256_file(summary_path)
                               if summary_path and summary_path.is_file() else None),
            "declared_files": declared,
            "declared_files_missing": [item for item in declared
                                       if not (REPOSITORY_ROOT / item).is_file()],
            "produces_reading": lane["produces_reading"], "promoted": lane["promoted"]}


def _missing_lane_keys() -> tuple[str, ...]:
    return tuple(key for key in LANE_KEYS
                 if not (REPOSITORY_ROOT / str(LANES[key]["report"])).is_file())


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

    backfill = read_json(BACKFILL_SUMMARY_PATH)
    guard = read_json(GUARD_SUMMARY_PATH)
    admission = read_json(ADMISSION_SUMMARY_PATH)

    pairs: list[tuple[str, str]] = []
    for source_path, destination in CARRY_FORWARD:
        if (REPOSITORY_ROOT / source_path).is_file():
            pairs.append((source_path, destination))
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
    verification = run_verifiers(REPOSITORY_ROOT, VERIFIERS)

    promoted_lanes = sorted(key for key, payload in lanes.items() if bool(payload["promoted"]))
    reading_lanes = sorted(key for key, payload in lanes.items()
                           if bool(payload["produces_reading"]))
    verdicts = {item["id"]: item for item in (*backfill["criteria"], *guard["criteria"],
                                              *admission["criteria"])}
    failed = sorted(identifier for identifier, verdict in verdicts.items()
                    if verdict["verdict"] != "成立")

    boundary_rows: list[str] = []
    for payload in (backfill, guard, admission):
        boundary_rows.extend(payload.get("boundaries") or [])

    summary = {
        "schema": "week37_delivery/summary@1",
        "week": WEEK,
        "generated_at_utc": _utc_now(),
        "artifacts_commit": head_commit,
        "worktree_dirty": bool(worktree_dirty),
        "worktree_dirty_paths": int(dirty_paths),
        "source_root": str(REPOSITORY_ROOT),
        "output_root": str(week_root),
        "lanes": lanes,
        "lanes_missing": lanes_missing,
        "lane_count": len(LANE_KEYS),
        "reading_lanes": reading_lanes,
        "promoted_lanes": promoted_lanes,
        "shot_ledger": {
            "this_week": 0,
            "cumulative_after": 19,
            "note": "三条 lane 全部是后验守卫件 / 治理件 / 回灌：不拟合主记分牌臂。",
        },
        "frozen_readings": FROZEN_READINGS,
        "frozen_red_lines": frozen,
        "headline_readings": {
            "backfill_plans": backfill["backfill"]["plans"],
            "backfill_after_blocks": backfill["backfill"]["after_blocks"],
            "backfill_splices": backfill["backfill"]["splices"],
            "backfill_inventory_csv": backfill["backfill"]["inventory_csv"],
            "backfill_shipped_draft_sha256_before": backfill["shipped_draft"]["sha256_before"],
            "backfill_shipped_draft_sha256_after": backfill["shipped_draft"]["sha256_after"],
            "backfill_shipped_draft_unchanged": backfill["shipped_draft"]["unchanged"],
            "backfill_rebuild_bytes_equal_to_shipped":
                backfill["rebuild"]["bytes_equal_to_shipped"],
            "backfill_dry_run_rolled_back": backfill["rebuild"]["dry_run_rolled_back"],
            "guard_endpoint_tolerance": guard["endpoint_tolerance"],
            "guard_endpoint_tolerance_source": guard["endpoint_tolerance_source"],
            "guard_reused_module": guard["reused_from_w36"]["module"],
            "guard_files_scanned": guard["scan"]["files_scanned"],
            "guard_sites_total": guard["sites"]["total"],
            "guard_sites_allowed": guard["sites"]["allowed"],
            "guard_sites_forbidden": guard["sites"]["forbidden"],
            "guard_reuse_bitwise_equal": guard["reuse_diagnostic"]["bitwise_equal"],
            "guard_reuse_endpoints_equal": guard["reuse_diagnostic"]["endpoints_equal"],
            "admission_checker_passed": admission["checker"]["passed"],
            "admission_sites_rows": admission["sites"]["rows"],
            "admission_sites_reduction": admission["sites"]["reduction"],
            "admission_sites_oxidation": admission["sites"]["oxidation"],
            "admission_violations": len(admission["violations"]),
            "admission_negative_control": admission["negative_control"],
            "admission_inputs_unchanged": admission["inputs_unchanged"],
        },
        "verdicts": {identifier: verdict["verdict"] for identifier, verdict in verdicts.items()},
        "verdicts_failed": failed,
        "files": sorted(copied),
        "figures": list(FIGURES),
        "external_deliverables": {},
        "verification": verification,
        "verification_passed": bool(verification.get("passed")),
        "boundaries": [
            "三条 lane 全部后验：0 shot（累计仍 19）、不改 METRIC_NAMES、不新增特征列、缺行不插补、不动四个冻结读数。",
            "W37-A 的 1e-12 是端点判等容差，不是新的显著性门；守卫只读盘上文件，不修改任何被扫描文件。",
            "W37-A 只扫 8 位以上有效数字的**字面量**比较；运行期变量对变量的一般相等不在守卫范围。",
            "W37-B 的准入件只约束还原轴；氧化轴引用点按既有约定标「不适用」。拒答不是缺失值，不得插补或赋伪值。",
            "W37-C 只把已发布稿的 12 段漂移回灌装配源；回灌后重建产物与已发布稿逐字节相等，已发布稿 sha256 未变。",
            "本包携带的两张图（w32_fig_noise_floor.png / w32_fig_fidelity_law.png）是 W32 的产物，W37 本身不产新图。",
            *boundary_rows,
        ],
    }
    write_json(week_root / "week37_summary.json", summary)
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
    print(json.dumps({key: result[key] for key in ("week", "artifacts_commit", "worktree_dirty",
                                                   "worktree_dirty_paths", "lanes_missing",
                                                   "promoted_lanes", "verification_passed")},
                     ensure_ascii=False, indent=2))
    return 0 if not result["lanes_missing"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
