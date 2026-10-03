"""Export the Week 35 deliverables.

Week 35 has two lanes, both post hoc and neither taking a main-scoreboard shot.

Lane A (W35-A) closes the enforcement gap left by Week 34-A.  The guard
``assert_redox_readable`` existed but nothing forced a downstream reader to call it:
the paper, the appendix and the decision log quoted -0.602 / +0.835 with no gate
verdict attached.  Week 35-A ships a per-molecule bypass table, registers every
reduction-axis reference point and evaluates its mark *through the Week 34-A guard*,
and audits seven downstream consumers.  The audit fails on the reconstructed
pre-correction paper (three consumers missing the mark) and passes now (7/7).

Lane B (W35-B) turns Week 34-B's resolution reading into the paper's wording.  A locked
pre-registration pins the four corrections and their inputs, and a probe applies them
idempotently: "the oxidation axis is insensitive to the level" becomes "no difference
detected at n = 22" while every original number stays in place.

Shot ledger: delta 0, cumulative 19.  The four frozen readings keep their own
definitions: 0.4091179943351143, 0.4766400383507876, 0.5861142332208197,
0.6216672295270079.
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

WEEK = "week35"

FROZEN_RED_LINES = {
    "data/processed/redox_state_legality_registry.csv":
        "a01272b3e75514a609295275d18c82c39fb65c5bc27056feb4ed8c6cd0c6b60d",
    "data/processed/four_core_key_registry.csv":
        "e42885eb43779b7a4d472da88fefe018fe94150ff5b6fba86b3ed9bc83dc8bee",
    "probes/artifacts/w24_3_level_crosscheck.csv":
        "71dd995850080176595f3c554e7338f76714b0e622e57975409d25696a991ee0",
    "probes/artifacts/w33_bound_state_gate_gates.csv":
        "130a6f627c785b8f981d1e9246909a3fd663a2916643654a5e62fc0d7efc0542",
    "probes/artifacts/w34_legality_registry_summary.json":
        "a53d286e16643fd72fff4cd8bccdd4ae974c9176d0a9401adce529700c326783",
    "probes/artifacts/w34_paired_power_summary.json":
        "96131211bde31320565b57ce27e37415f82603f254d03815cb8797db07d929f9",
    "probes/w35_paper_r6_correction_prereg.json":
        "3bef7a992f124a8bfdef9ff2dba94e6bd41ba3a1f25fc688c8869b447edf85ac",
}

FROZEN_READINGS = {
    "frozen_baseline": 0.4091179943351143,
    "frozen_headline": 0.4766400383507876,
    "single_representation_cross_seed": 0.5861142332208197,
    "w20_4_promoted_arm": 0.6216672295270079,
}

LANES: dict[str, dict[str, object]] = {
    "w35_redox_gate_consumers": {
        "title": (
            "W35-A 后验旁路层：门禁旁路表 + 引用登记表 + 下游消费者审计（不占 shot）"
        ),
        "probe": "probes/w35_redox_gate_consumers.py",
        "prereg": None,
        "summary": "probes/artifacts/w35_redox_gate_consumers_summary.json",
        "report": "reports/w35_redox_gate_consumers.md",
        "tests": ("tests/test_w35_redox_gate_consumers.py",),
        "artifacts": (
            "data/processed/redox_readability_sidecar.csv",
            "probes/artifacts/w35_gated_reference_register.csv",
            "probes/artifacts/w35_gated_consumer_audit.csv",
            "probes/artifacts/w35_redox_gate_consumers.png",
        ),
        "produces_reading": False,
        "promoted": False,
    },
    "w35_paper_r6_correction": {
        "title": (
            "W35-B 预注册驱动的论文 R6 口径更正（幂等改稿；不占 shot）"
        ),
        "probe": "probes/w35_paper_r6_correction.py",
        "prereg": "probes/w35_paper_r6_correction_prereg.json",
        "summary": "probes/artifacts/w35_paper_r6_correction_summary.json",
        "report": "reports/w35_paper_r6_correction.md",
        "tests": ("tests/test_w35_paper_r6_correction.py",),
        "artifacts": (),
        "produces_reading": False,
        "promoted": False,
    },
}

CARRY_FORWARD = (
    ("README.md", "README.md"),
    ("reports/decisions_log.md", "decisions_log.md"),
    ("reports/week34_delivery_readme.md", "week34_delivery_readme.md"),
    ("reports/week34_project_charter.md", "week34_project_charter.md"),
    ("reports/week35_project_charter.md", "week35_project_charter.md"),
    ("reports/week35_delivery_readme.md", "week35_delivery_readme.md"),
    ("reports/w34_legality_registry.md", "w34_legality_registry.md"),
    ("reports/w34_paired_power.md", "w34_paired_power.md"),
    ("reports/w35_redox_gate_consumers.md", "w35_redox_gate_consumers.md"),
    ("reports/w35_paper_r6_correction.md", "w35_paper_r6_correction.md"),
    ("paper/paper_zh_draft_v2.md", "paper_zh_draft_v2.md"),
    ("paper/make_paper_docx_template.py", "make_paper_docx_template.py"),
    ("probes/export_week34_results.py", "export_week34_results.py"),
    ("probes/export_week35_results.py", "export_week35_results.py"),
)

LANE_KEYS = tuple(LANES)

EXTERNAL_DELIVERABLES: tuple[tuple[str, str], ...] = ()

FIGURES: tuple[str, ...] = (
    "probes/artifacts/w35_redox_gate_consumers.png",
)

VERIFIERS = (
    "scripts/verify_four_core_registry.py --check",
    "scripts/check_paper_artifact_consistency.py",
    (
        "-m pytest tests/test_repo_hygiene.py tests/test_w35_paper_r6_correction.py "
        "tests/test_w35_redox_gate_consumers.py tests/test_w34_legality_registry.py "
        "tests/test_w34_paired_power.py tests/test_w33_bound_state_gate.py "
        "-q -p no:cacheprovider"
    ),
)

README_TEXT = (REPOSITORY_ROOT / "reports/week35_delivery_readme.md").read_text(encoding="utf-8")
GATE_SUMMARY_PATH = REPOSITORY_ROOT / "probes/artifacts/w35_redox_gate_consumers_summary.json"
PAPER_SUMMARY_PATH = REPOSITORY_ROOT / "probes/artifacts/w35_paper_r6_correction_summary.json"


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

    gate = read_json(GATE_SUMMARY_PATH)
    paper = read_json(PAPER_SUMMARY_PATH)

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
    verification = run_verifiers(REPOSITORY_ROOT, VERIFIERS)

    promoted_lanes = sorted(key for key, payload in lanes.items() if bool(payload["promoted"]))
    reading_lanes = sorted(key for key, payload in lanes.items()
                           if bool(payload["produces_reading"]))
    verdicts = {item["id"]: item for item in (*gate["criteria"], *paper["criteria"])}
    failed = sorted(identifier for identifier, verdict in verdicts.items()
                    if verdict["verdict"] != "成立")
    register = {row["reference_id"]: row for row in gate["register"]["rows_detail"]}

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
        "promoted_lanes": promoted_lanes,
        "reading_lanes": reading_lanes,
        "shots_by_lane": {"w35_redox_gate_consumers": 0, "w35_paper_r6_correction": 0},
        "main_scoreboard_attempts_delta": 0,
        "cumulative_main_scoreboard_attempts": 19,
        "frozen_readings": FROZEN_READINGS,
        "frozen_red_lines": frozen,
        "redox_gate_consumers": {
            "sidecar_rows": gate["sidecar"]["rows"],
            "sidecar_vs_registry_pairs": gate["sidecar"]["pairs_checked"],
            "sidecar_mismatches": gate["sidecar"]["mismatches"],
            "medium_table": gate["sidecar"]["medium_table"],
            "reference_rows": gate["register"]["rows"],
            "refused_rows": gate["register"]["refused_rows"],
            "not_applicable_rows": gate["register"]["not_applicable_rows"],
            "consumers": gate["audit"]["rows"],
            "missing_before": gate["audit"]["missing_before"],
            "missing_after": gate["audit"]["missing_after"],
            "registry_sha256": gate["inputs"]["registry_sha256"],
        },
        "paper_r6_correction": {
            "prereg_sha256": paper["prereg"]["sha256"],
            "prereg_status": paper["prereg"]["status"],
            "paper_sha256_before": paper["paper"]["sha256_before"],
            "paper_sha256_after": paper["paper"]["sha256_after"],
            "corrections": [item["id"] for item in paper["corrections"]],
            "oxidation_ci": [paper["evidence"]["oxidation"]["ci_low"],
                             paper["evidence"]["oxidation"]["ci_high"]],
            "reduction_ci": [paper["evidence"]["reduction"]["ci_low"],
                             paper["evidence"]["reduction"]["ci_high"]],
        },
        "headline_readings": {
            "sidecar_rows": gate["sidecar"]["rows"],
            "reference_rows": gate["register"]["rows"],
            "r6_red_gfn2_legal": register["r6_red_gfn2"]["legal_n"],
            "r6_red_orca_legal": register["r6_red_orca"]["legal_n"],
            "r6_red_marks": [register["r6_red_gfn2"]["mark"], register["r6_red_orca"]["mark"]],
            "w33a_gfn2_census_legal": [register["w33a_gfn2_gas"]["legal_n"],
                                       register["w33a_gfn2_thf"]["legal_n"],
                                       register["w33a_gfn2_benzaldehyde"]["legal_n"],
                                       register["w33a_gfn2_water"]["legal_n"]],
            "w33a_orca_legal": [register["w33a_orca_gas"]["legal_n"],
                                register["w33a_orca_smd_acetonitrile"]["legal_n"]],
            "consumers_missing_before": len(gate["audit"]["missing_before"]),
            "consumers_missing_after": len(gate["audit"]["missing_after"]),
            "oxidation_ci": [paper["evidence"]["oxidation"]["ci_low"],
                             paper["evidence"]["oxidation"]["ci_high"]],
            "oxidation_crosses_zero": paper["evidence"]["oxidation"]["crosses_zero"],
            "reduction_ci": [paper["evidence"]["reduction"]["ci_low"],
                             paper["evidence"]["reduction"]["ci_high"]],
            "reduction_crosses_zero": paper["evidence"]["reduction"]["crosses_zero"],
        },
        "verdicts": {identifier: verdict["verdict"] for identifier, verdict in verdicts.items()},
        "verdicts_failed": failed,
        "files": sorted(copied),
        "figures": list(FIGURES),
        "external_deliverables": {},
        "verification": verification,
        "verification_passed": bool(verification.get("passed")),
        "boundaries": [
            "W35-A / W35-B 都是后验旁路层 / 预注册驱动的口径更正：不拟合主记分牌臂、不占 shot（累计仍 19）、不得当作预注册结论引用。",
            "拒答不是缺失值：登记表里 ORCA 两层的 tau_legal 值列留空，就是守卫抛出的拒答结论，不得捕获后插补、赋伪值或静默跳过。",
            "门禁是阴离子态审计，只覆盖还原轴；氧化轴登记为「不适用（门禁只覆盖还原轴）」，不得把阴离子门禁套到阳离子轴上。",
            "同一（层级，介质）在 246 普查与 22 配对集上的合法子集数不同，引用还原轴读数必须带 population_scope。",
            "区间跨 0 的正确读法是「未检出差异」，不是「证明无差异」。",
            "四个冻结读数（0.4091179943351143 / 0.4766400383507876 / 0.5861142332208197 / 0.6216672295270079）未动；不改 METRIC_NAMES、不新增特征列、缺行不插补。",
        ],
    }
    write_json(week_root / "week35_summary.json", summary)
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