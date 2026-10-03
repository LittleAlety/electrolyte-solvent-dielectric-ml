"""Export the Week 34 deliverables.

Week 34 has two lanes, both post hoc and neither taking a main-scoreboard shot.

Lane A (W34-A) writes Week 33-A's gate verdict down as an authoritative artifact instead
of leaving it inside a report: a 1,028-row registry (one row per level x medium x
molecule), a guard that raises RedoxGateRefusal instead of returning None, and a
four-channel dashboard that pools the Week 32-A budgets with the Week 33-A gate status.

Lane B (W34-B) closes the last gap in the cross-level story.  R6 is the only cross-level
conclusion in the repository without a resolution reading: the six parent-paper rungs
carry a sigma column and the four channels carry a resampling law, but R6 had only two
point estimates.  A paired bootstrap over the 22 paired compounds (B = 4000, seed locked
before the run) says the reduction-axis flip is a resolvable effect and the oxidation-axis
move is not -- so "the oxidation axis is insensitive to the level" becomes "no difference
detected at n = 22".

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

WEEK = "week34"

FROZEN_RED_LINES = {
    "data/processed/w23_redox_dscf_layer.csv":
        "d24d4c5a0937bbf971afb5d52f15038505f58e47d43c4ed8ebe44a07910d1b9f",
    "data/processed/w24_2_orca_dft_layer.csv":
        "c48a541d1a831f073cfd87810510f89c934a6f645a869880886518e1acc03246",
    "probes/artifacts/w24_3_level_crosscheck.csv":
        "71dd995850080176595f3c554e7338f76714b0e622e57975409d25696a991ee0",
    "probes/artifacts/w24_3_sampling_law.csv":
        "8cd15a8e23d06809f06b75f1918a7529bdb30e33cc27b6391a446ada98c5cfcc",
    "probes/artifacts/w32_rank_stability.json":
        "106983b41e84808b331043927df3aba9afc9addcebdf985d9845d4330e2e8e95",
    "probes/artifacts/w33_bound_state_gate_summary.json":
        "c5519c719086d705b92d82c325a21bccd864376272babbed7530781685803f6d",
    "probes/artifacts/w33_bound_state_gate_gates.csv":
        "130a6f627c785b8f981d1e9246909a3fd663a2916643654a5e62fc0d7efc0542",
    "probes/artifacts/w33_kendall_null_budget.csv":
        "eb16242737abc9b0c8308fb855a2f52cc3a3ba3b755726a67b4e480b0afe0b28",
    "probes/w34_paired_power_prereg.json":
        "431e8fd5c78744906c4a7c19293dea3859ba7957438d8bf58e1308545ea21f0e",
}

FROZEN_READINGS = {
    "frozen_baseline": 0.4091179943351143,
    "frozen_headline": 0.4766400383507876,
    "single_representation_cross_seed": 0.5861142332208197,
    "w20_4_promoted_arm": 0.6216672295270079,
}

LANES: dict[str, dict[str, object]] = {
    "w34_legality_registry": {
        "title": (
            "W34-A 后验注册表：还原轴态合法性注册表 + 门禁守卫 + 四通道看板（不占 shot）"
        ),
        "probe": "probes/w34_legality_registry.py",
        "prereg": None,
        "summary": "probes/artifacts/w34_legality_registry_summary.json",
        "report": "reports/w34_legality_registry.md",
        "tests": ("tests/test_w34_legality_registry.py",),
        "artifacts": (
            "data/processed/redox_state_legality_registry.csv",
            "probes/artifacts/w34_channel_dashboard.csv",
            "probes/artifacts/w34_channel_dashboard.md",
            "probes/artifacts/w34_legality_registry.png",
        ),
        "produces_reading": False,
        "promoted": False,
    },
    "w34_paired_power": {
        "title": (
            "W34-B 后验读数：R6 的配对 bootstrap 分辨率审计（B = 4000，种子跑前锁定；不占 shot）"
        ),
        "probe": "probes/w34_paired_power.py",
        "prereg": "probes/w34_paired_power_prereg.json",
        "summary": "probes/artifacts/w34_paired_power_summary.json",
        "report": "reports/w34_paired_power.md",
        "tests": ("tests/test_w34_paired_power.py",),
        "artifacts": (
            "probes/artifacts/w34_paired_power_bootstrap.csv",
            "probes/artifacts/w34_paired_power_table.csv",
            "probes/artifacts/w34_paired_power.png",
        ),
        "produces_reading": False,
        "promoted": False,
    },
}

CARRY_FORWARD = (
    ("README.md", "README.md"),
    ("reports/decisions_log.md", "decisions_log.md"),
    ("reports/week33_delivery_readme.md", "week33_delivery_readme.md"),
    ("reports/week34_project_charter.md", "week34_project_charter.md"),
    ("reports/week34_delivery_readme.md", "week34_delivery_readme.md"),
    ("reports/w34_legality_registry.md", "w34_legality_registry.md"),
    ("reports/w34_paired_power.md", "w34_paired_power.md"),
    ("paper/paper_zh_draft_v2.md", "paper_zh_draft_v2.md"),
    ("paper/make_paper_docx_template.py", "make_paper_docx_template.py"),
    ("probes/export_week33_results.py", "export_week33_results.py"),
    ("probes/export_week34_results.py", "export_week34_results.py"),
)

LANE_KEYS = tuple(LANES)

EXTERNAL_DELIVERABLES: tuple[tuple[str, str], ...] = ()

FIGURES: tuple[str, ...] = (
    "probes/artifacts/w34_legality_registry.png",
    "probes/artifacts/w34_paired_power.png",
)

VERIFIERS = (
    "scripts/verify_four_core_registry.py --check",
    (
        "-m pytest tests/test_repo_hygiene.py tests/test_w34_legality_registry.py "
        "tests/test_w34_paired_power.py tests/test_w33_bound_state_gate.py "
        "-q -p no:cacheprovider"
    ),
)

README_TEXT = (REPOSITORY_ROOT / "reports/week34_delivery_readme.md").read_text(encoding="utf-8")
REGISTRY_SUMMARY_PATH = REPOSITORY_ROOT / "probes/artifacts/w34_legality_registry_summary.json"
POWER_SUMMARY_PATH = REPOSITORY_ROOT / "probes/artifacts/w34_paired_power_summary.json"


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

    registry = read_json(REGISTRY_SUMMARY_PATH)
    power = read_json(POWER_SUMMARY_PATH)

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
    verdicts = {item["id"]: item for item in (*registry["criteria"], *power["criteria"])}
    failed = sorted(identifier for identifier, verdict in verdicts.items()
                    if verdict["verdict"] != "成立")
    dashboard = {row["channel"]: row for row in registry["dashboard"]}
    ox = power["table"]["ox"]
    red = power["table"]["red"]

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
        "shots_by_lane": {"w34_legality_registry": 0, "w34_paired_power": 0},
        "main_scoreboard_attempts_delta": 0,
        "cumulative_main_scoreboard_attempts": 19,
        "frozen_readings": FROZEN_READINGS,
        "frozen_red_lines": frozen,
        "legality_registry": {
            "rows": sum(int(entry["rows"]) for entry in registry["register"]),
            "register": registry["register"],
            "dashboard": registry["dashboard"],
            "anchors": registry["anchors"],
            "min_legal_subset": registry["gate"]["min_legal_subset"],
        },
        "paired_power": {
            "n_paired": power["n_paired"],
            "method": power["method"],
            "table": power["table"],
            "gate": power["gate"],
            "reproduction_anchors": power["full_set_tau"],
        },
        "headline_readings": {
            "registry_rows": sum(int(entry["rows"]) for entry in registry["register"]),
            "gfn2_gas_legal": next(int(entry["legal"]) for entry in registry["register"]
                                   if entry["level"] == "gfn2" and entry["medium"] == "gas"),
            "orca_gas_legal": next(int(entry["legal"]) for entry in registry["register"]
                                   if entry["level"] == "orca" and entry["medium"] == "gas"),
            "redox_gate_applies": dashboard["redox"]["gate_applies"],
            "paired_ox_delta": ox["delta"],
            "paired_ox_ci": [ox["ci_low"], ox["ci_high"]],
            "paired_ox_crosses_zero": ox["crosses_zero"],
            "paired_red_delta": red["delta"],
            "paired_red_ci": [red["ci_low"], red["ci_high"]],
            "paired_red_crosses_zero": red["crosses_zero"],
            "independent_floor_n22": power["method"]["independent_floor"],
            "half_width_ratio_ox": power["method"]["half_width_ratio_ox"],
        },
        "verdicts": {identifier: verdict["verdict"] for identifier, verdict in verdicts.items()},
        "verdicts_failed": failed,
        "files": sorted(copied),
        "figures": list(FIGURES),
        "external_deliverables": {},
        "verification": verification,
        "verification_passed": bool(verification.get("passed")),
        "boundaries": [
            "W34-A / W34-B 都是后验注册表 / 读数：不拟合主记分牌臂、不占 shot（累计仍 19）、不得当作预注册结论引用。",
            "注册表逐位派生自冻结表与 W33-A 预注册门禁；不改门禁规则、不改阈值、不改拒答优先级。",
            "拒答不是缺失值：守卫抛 RedoxGateRefusal 是「在本层不可宣读」的明确结论，不得捕获后插补、赋伪值或静默跳过。",
            "bootstrap 只在 22 个配对化合物上重抽，不外推到 246 普查；区间是该配对设计下的分辨率，不是全域噪声地板。",
            "区间跨 0 的正确读法是「未检出差异」，不是「证明无差异」。",
            "四个冻结读数（0.4091179943351143 / 0.4766400383507876 / 0.5861142332208197 / 0.6216672295270079）未动；不改 METRIC_NAMES、不新增特征列、缺行不插补。",
        ],
    }
    write_json(week_root / "week34_summary.json", summary)
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