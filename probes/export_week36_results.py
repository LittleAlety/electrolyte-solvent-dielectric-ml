"""Export the Week 36 deliverables.

Week 36 closes the five remaining README section 11 items in one round.  Every lane is
post hoc and none takes a main-scoreboard shot (cumulative stays at 19).

  * W36-A writes the endpoint rule down (seven clauses) and ships an executable endpoint
    recomputer.  Recomputing all 26 published endpoints exposed that they differ from a
    fresh average by up to two ulp, so endpoint equality has to be a tolerance (1e-12),
    never a string comparison.
  * W36-B hangs the Week 32-A channel noise floor beside every ``*_repeats.csv`` without
    touching a frozen byte.  W36-C turns the fidelity gap into an explicit selection
    criterion for low-fidelity proxies.
  * W36-D promotes the Week 35-A reference register into an admission list: an
    unregistered reduction-axis citation point raises instead of warning.
  * W36-E answers README section 11 item 15 (the v1 and English lines are clean) and lands
    the Week 35-B wording corrections on the assembly sources, so a rebuild can no longer
    resurrect them.  The drift that remains is registered, not hidden.

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

WEEK = "week36"

FROZEN_RED_LINES = {
    "paper/paper_zh_draft_v2.md":
        "dfb3b282f8ccf76653d244a6a2c618d92a6e12003d012b81cca9f08dc9c6e78e",
    "probes/w36_v2_source_correction_prereg.json":
        "d5270ba1f875e3dba3636380fb15ac582f1621db5b9324b57550c8101d9732b7",
    "paper/_v2_body_b.md":
        "3660f00b39b6ec2d8cb112a392b70d6db24b54defa667d42acd81315c6b252fb",
    "paper/_v2_appendix.md":
        "ebb3ef1130b8214fb25ca459da06955aa1dd59c41cced93a451c79857b8b034d",
    "paper/_v2_concl.md":
        "a915e595221873688deb2e37f2926cdd9530931152884ab0880637036591dd49",
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
    "w36_endpoint_rule": {
        "title": "W36-A 后验规则入册：主记分牌端点规则 7 条 + 端点复算符（不占 shot）",
        "probe": "probes/w36_endpoint_rule.py",
        "prereg": None,
        "summary": "probes/artifacts/w36_endpoint_rule_summary.json",
        "report": "reports/w36_endpoint_rule.md",
        "tests": ("tests/test_w36_endpoint_rule.py",),
        "artifacts": (
            "data/processed/w36_endpoint_rule_registry.csv",
            "probes/artifacts/w36_endpoint_conformance.csv",
        ),
        "produces_reading": False,
        "promoted": False,
    },
    "w36_channel_noise_floor": {
        "title": "W36-B/C 后验显示层与准则：噪声地板接进显示层 + 多保真度联合准则（不占 shot）",
        "probe": "probes/w36_channel_noise_floor.py",
        "prereg": None,
        "summary": "probes/artifacts/w36_channel_noise_floor_summary.json",
        "report": "reports/w36_channel_noise_floor.md",
        "tests": ("tests/test_w36_channel_noise_floor.py",),
        "artifacts": (
            "probes/artifacts/w36_channel_noise_floor.csv",
            "probes/artifacts/w36_repeats_display_layer.csv",
            "probes/artifacts/w36_channel_dashboard_v2.csv",
            "probes/artifacts/w36_fidelity_criterion.csv",
        ),
        "produces_reading": False,
        "promoted": False,
    },
    "w36_gate_admission": {
        "title": "W36-D 后验治理件：引用登记升为准入清单（不占 shot）",
        "probe": "probes/w36_gate_admission.py",
        "prereg": None,
        "summary": "probes/artifacts/w36_gate_admission_summary.json",
        "report": "reports/w36_gate_admission.md",
        "tests": ("tests/test_w36_gate_admission.py",),
        "artifacts": (
            "probes/artifacts/w36_gate_admission_manifest.csv",
            "probes/artifacts/w36_gate_admission_refusals.csv",
        ),
        "produces_reading": False,
        "promoted": False,
    },
    "w36_v2_source_correction": {
        "title": "W36-E 预注册驱动的装配源口径同步（幂等改稿；不占 shot）",
        "probe": "probes/w36_v2_source_correction.py",
        "prereg": "probes/w36_v2_source_correction_prereg.json",
        "summary": "probes/artifacts/w36_v2_source_correction_summary.json",
        "report": "reports/w36_v2_source_correction.md",
        "tests": ("tests/test_w36_v2_source_correction.py",),
        "artifacts": ("probes/artifacts/w36_v2_drift_inventory.csv",),
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

# No new figure is produced this round (W36 is a governance round).  The two Week 32
# figures that W36-B / W36-C build on are carried so the package stays self-contained.
FIGURES: tuple[str, ...] = (
    "probes/artifacts/w32_fig_noise_floor.png",
    "probes/artifacts/w32_fig_fidelity_law.png",
)

VERIFIERS = (
    "scripts/verify_four_core_registry.py --check",
    "scripts/check_paper_artifact_consistency.py",
    (
        "-m pytest tests/test_repo_hygiene.py tests/test_w36_endpoint_rule.py "
        "tests/test_w36_channel_noise_floor.py tests/test_w36_gate_admission.py "
        "tests/test_w36_v2_source_correction.py tests/test_w35_paper_r6_correction.py "
        "tests/test_w35_redox_gate_consumers.py tests/test_w34_legality_registry.py "
        "-q -p no:cacheprovider"
    ),
)

README_TEXT = (REPOSITORY_ROOT / "reports/week36_delivery_readme.md").read_text(encoding="utf-8")
ENDPOINT_SUMMARY_PATH = REPOSITORY_ROOT / "probes/artifacts/w36_endpoint_rule_summary.json"
FLOOR_SUMMARY_PATH = REPOSITORY_ROOT / "probes/artifacts/w36_channel_noise_floor_summary.json"
ADMISSION_SUMMARY_PATH = REPOSITORY_ROOT / "probes/artifacts/w36_gate_admission_summary.json"
SOURCE_SUMMARY_PATH = REPOSITORY_ROOT / "probes/artifacts/w36_v2_source_correction_summary.json"


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

    endpoint = read_json(ENDPOINT_SUMMARY_PATH)
    floor = read_json(FLOOR_SUMMARY_PATH)
    admission = read_json(ADMISSION_SUMMARY_PATH)
    source = read_json(SOURCE_SUMMARY_PATH)

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
    verdicts = {item["id"]: item for item in (*endpoint["criteria"], *floor["criteria"],
                                              *admission["criteria"], *source["criteria"])}
    failed = sorted(identifier for identifier, verdict in verdicts.items()
                    if verdict["verdict"] != "成立")

    boundary_rows = []
    for payload in (endpoint, floor, admission, source):
        boundary_rows.extend(payload.get("boundaries", []))

    summary = {
        "schema": "week36_delivery/summary@1",
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
            "note": "五条 lane 全部是后验显示层 / 治理件 / 规则入册：不拟合主记分牌臂。",
        },
        "frozen_readings": FROZEN_READINGS,
        "frozen_red_lines": frozen,
        "headline_readings": {
            "endpoint_published_checked": endpoint["diagnostics"]["published_checked"],
            "endpoint_published_passed": endpoint["diagnostics"]["published_passed"],
            "endpoint_max_abs_diff": endpoint["diagnostics"]["max_abs_diff"],
            "endpoint_ineligible_arms": endpoint["diagnostics"]["ineligible"],
            "endpoint_locked_seeds": endpoint["locked_seeds"],
            "endpoint_tolerance": endpoint["endpoint_tolerance"],
            "noise_floor_channels": len(floor["floor"]),
            "noise_floor_repeats_files": floor["display_layer"]["repeats_files"],
            "noise_floor_mapped": floor["display_layer"]["mapped"],
            "noise_floor_unmapped": floor["display_layer"]["unmapped"],
            "noise_floor_frozen_repeats_intact": floor["display_layer"]["frozen_repeats_intact"],
            "fidelity_spearman": floor["fidelity_law"]["spearman"],
            "fidelity_r2": floor["fidelity_law"]["r2"],
            "fidelity_intercept": floor["fidelity_law"]["intercept"],
            "fidelity_slope": floor["fidelity_law"]["slope"],
            "admission_rows": admission["admission_list"]["rows"],
            "admission_reduction_rows": admission["admission_list"]["reduction_rows"],
            "admission_refused": len([row for row in admission["refusals"]
                                      if row["verdict"] == "拒绝"]),
            "source_audit_hits": sum(row["hit_count"] for row in source["audit"]),
            "source_corrections": [row["id"] for row in source["corrections"]],
            "source_shipped_draft_sha256": source["shipped_draft"]["sha256"],
            "source_shipped_draft_unchanged": source["shipped_draft"]["unchanged"],
            "source_drift_blocks": source["rebuild"]["drift_blocks"],
        },
        "verdicts": {identifier: verdict["verdict"] for identifier, verdict in verdicts.items()},
        "verdicts_failed": failed,
        "files": sorted(copied),
        "figures": list(FIGURES),
        "external_deliverables": {},
        "verification": verification,
        "verification_passed": bool(verification.get("passed")),
        "boundaries": [
            "五条 lane 全部后验：0 shot（累计仍 19）、不改 METRIC_NAMES、不新增特征列、缺行不插补、不动四个冻结读数。",
            "W36-A 的 1e-12 是端点判等容差，不是新的显著性门；不得用它放宽任何判据。",
            "W36-A 里 3 个一折描述性臂标注「不适用」且没有发布值——不适用不等于 0，也不参与判等。",
            "W36-B 的 52 张 `*_repeats.csv` 在生成显示层前后逐文件 sha256 相等：加列会改字节、破坏 AF-12 坐标，所以噪声地板走旁挂附表。",
            "W36-C 的缺口→噪声地板斜率来自 26 条已发布序列，不得跨通道族外推；它是外推校验，不是新的显著性门。",
            "W36-D 的准入件只约束还原轴；氧化轴标「不适用（门禁只覆盖还原轴）」。拒答不是缺失值，不得插补或赋伪值。",
            "W36-E 只把已发布稿里的四处更正落回装配源；装配源与已发布稿仍有漂移（w36_v2_drift_inventory.csv），尚未回灌。",
            "本包携带的两张图（w32_fig_noise_floor.png / w32_fig_fidelity_law.png）是 W32 的产物，W36 本身不产新图。",
        ],
    }
    write_json(week_root / "week36_summary.json", summary)
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