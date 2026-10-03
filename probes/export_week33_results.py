"""Export the Week 33 deliverables.

Week 33 has two lanes, both post hoc and neither taking a main-scoreboard shot.

Lane A (W33-A) acts on the parent paper's open diagnosis.  The reduction-axis tau_b
flips sign when the electronic-structure level moves (GFN2 +0.835 vs ORCA -0.602), but
that flip had only ever been measured over states that are largely not bound.  W33-A
promotes state legality from a post hoc caveat to a front gate (geom AND homo AND ea)
with an explicit refusal queue, then re-reads the reduction axis on the legal subset.
The gate removes most of the census, EA alone cannot serve as the gate, and every GFN2
medium's tau_b drops once the unbound states are excluded -- so part of the old
agreement was drift among unbound states, not signal.  On the paired anchor set the
legal counts are GFN2 1/22 and ORCA 0/22, so the ORCA layer is declared undecidable
rather than quoted at -0.602.

Lane B (W33-B) supplies the exact small-sample counterpart to the Week 32-A fitted
resampling law: for n <= 12 the null distribution of Kendall tau_b is the Mahonian
inversion-count distribution, so p-values and critical values are exact rationals.  The
parent paper's n = 7, tau >= 0.90 threshold turns out to sit at P = 1/720.

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

WEEK = "week33"

FROZEN_RED_LINES = {
    "probes/artifacts/w24_3_level_crosscheck.csv":
        "71dd995850080176595f3c554e7338f76714b0e622e57975409d25696a991ee0",
    "probes/artifacts/w24_3_sampling_law.csv":
        "8cd15a8e23d06809f06b75f1918a7529bdb30e33cc27b6391a446ada98c5cfcc",
    "probes/artifacts/w32_rank_stability.json":
        "106983b41e84808b331043927df3aba9afc9addcebdf985d9845d4330e2e8e95",
    "data/processed/w23_redox_dscf_layer.csv":
        "d24d4c5a0937bbf971afb5d52f15038505f58e47d43c4ed8ebe44a07910d1b9f",
    "data/processed/w24_2_orca_dft_layer.csv":
        "c48a541d1a831f073cfd87810510f89c934a6f645a869880886518e1acc03246",
    "data/processed/dielectric_representation_ablation_predictions.csv":
        "a8dee3c6b1bd31c979931f34b7e6f463614808e67c11bef81741917fce061a19",
}

FROZEN_READINGS = {
    "frozen_baseline": 0.4091179943351143,
    "frozen_headline": 0.4766400383507876,
    "single_representation_cross_seed": 0.5861142332208197,
    "w20_4_promoted_arm": 0.6216672295270079,
}

LANES: dict[str, dict[str, object]] = {
    "w33_bound_state_gate": {
        "title": (
            "W33-A 后验重建：态合法性前置门禁 + 拒答队列 + 门禁后的还原轴排序重读"
            "（不占 shot）"
        ),
        "probe": "probes/w33_bound_state_gate.py",
        "prereg": "probes/w33_bound_state_gate_prereg.json",
        "summary": "probes/artifacts/w33_bound_state_gate_summary.json",
        "report": "reports/w33_bound_state_gate.md",
        "tests": ("tests/test_w33_bound_state_gate.py",),
        "artifacts": (
            "probes/artifacts/w33_bound_state_gate_gates.csv",
            "probes/artifacts/w33_bound_state_gate_refuse_queue.csv",
            "probes/artifacts/w33_bound_state_gate_readings.csv",
            "probes/artifacts/w33_bound_state_gate.png",
        ),
        "produces_reading": False,
        "promoted": False,
    },
    "w33_kendall_null_tool": {
        "title": (
            "W33-B 统计工具化：Kendall tau_b 的精确零分布、临界值与立项前预算"
            "（不占 shot）"
        ),
        "probe": "probes/w33_kendall_null_tool.py",
        "prereg": None,
        "summary": "probes/artifacts/w33_kendall_null_summary.json",
        "report": "reports/w33_kendall_null_tool.md",
        "tests": ("tests/test_w33_kendall_null_tool.py",),
        "artifacts": (
            "probes/artifacts/w33_kendall_null_table.csv",
            "probes/artifacts/w33_kendall_null_budget.csv",
            "probes/artifacts/w33_kendall_null.png",
        ),
        "produces_reading": False,
        "promoted": False,
    },
}

CARRY_FORWARD = (
    ("README.md", "README.md"),
    ("reports/decisions_log.md", "decisions_log.md"),
    ("reports/week32_delivery_readme.md", "week32_delivery_readme.md"),
    ("reports/week33_project_charter.md", "week33_project_charter.md"),
    ("reports/week33_delivery_readme.md", "week33_delivery_readme.md"),
    ("reports/w33_bound_state_gate.md", "w33_bound_state_gate.md"),
    ("reports/w33_kendall_null_tool.md", "w33_kendall_null_tool.md"),
    ("paper/paper_zh_draft_v2.md", "paper_zh_draft_v2.md"),
    ("paper/make_paper_docx_template.py", "make_paper_docx_template.py"),
    ("probes/export_week32_results.py", "export_week32_results.py"),
    ("probes/export_week33_results.py", "export_week33_results.py"),
    ("probes/w32_presentation_figures.py", "w32_presentation_figures.py"),
)

LANE_KEYS = tuple(LANES)

EXTERNAL_DELIVERABLES: tuple[tuple[str, str], ...] = ()

FIGURES: tuple[str, ...] = (
    "probes/artifacts/w33_bound_state_gate.png",
    "probes/artifacts/w33_kendall_null.png",
)

VERIFIERS = (
    "scripts/verify_four_core_registry.py --check",
    (
        "-m pytest tests/test_repo_hygiene.py tests/test_w33_bound_state_gate.py "
        "tests/test_w33_kendall_null_tool.py tests/test_w32_rank_stability.py "
        "-q -p no:cacheprovider"
    ),
)

README_TEXT = (REPOSITORY_ROOT / "reports/week33_delivery_readme.md").read_text(encoding="utf-8")
GATE_SUMMARY_PATH = REPOSITORY_ROOT / "probes/artifacts/w33_bound_state_gate_summary.json"
NULL_SUMMARY_PATH = REPOSITORY_ROOT / "probes/artifacts/w33_kendall_null_summary.json"


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
    null = read_json(NULL_SUMMARY_PATH)
    if gate["preregistration"]["sha256"] != sha256_file(
            REPOSITORY_ROOT / gate["preregistration"]["path"]):
        raise ValueError("the gate pre-registration hash moved after the run")

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
    verdicts = {item["id"]: item for item in (*gate["criteria"], *null["criteria"])}
    failed = sorted(identifier for identifier, verdict in verdicts.items()
                    if verdict["verdict"] != "成立")
    census = {entry["medium"]: entry for entry in gate["census"]}
    orca = {entry["medium"]: entry for entry in gate["orca"]}
    budget = {(row["channel"], row["target"]): row for row in null["budget"]}

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
        "shots_by_lane": {"w33_bound_state_gate": 0, "w33_kendall_null_tool": 0},
        "main_scoreboard_attempts_delta": 0,
        "cumulative_main_scoreboard_attempts": 19,
        "frozen_readings": FROZEN_READINGS,
        "frozen_red_lines": frozen,
        "bound_state_gate": {
            "gate": gate["gate"],
            "census": gate["census"],
            "orca": gate["orca"],
            "cross": gate["cross"],
            "anchors": gate["anchors"],
        },
        "kendall_null_tool": {
            "anchor": null["anchor"],
            "channels": null["channels"],
            "n_grid": null["n_grid"],
            "alphas": null["alphas"],
        },
        "headline_readings": {
            "gas_pass_rate": census["gas"]["pass_rate"],
            "gas_refusal_rate": census["gas"]["refusal_rate"],
            "gas_legal": census["gas"]["legal"],
            "gas_rows": census["gas"]["rows"],
            "ea_pass_gap_vs_homo": (census["gas"]["clause_ea_pass"]
                                    - census["gas"]["clause_homo_pass"]) / census["gas"]["rows"],
            "tau_all_gas": census["gas"]["tau_all"],
            "tau_legal_gas": census["gas"]["tau_legal"],
            "max_tau_drop": max(abs(entry["tau_legal"] - entry["tau_all"])
                                for entry in gate["census"]),
            "orca_gas_legal": orca["orca_gas"]["legal"],
            "orca_gas_verdict": orca["orca_gas"]["verdict"],
            "paired_legal_gfn2": gate["cross"]["gfn2_legal"],
            "paired_legal_orca": gate["cross"]["orca_legal"],
            "paired_n": gate["cross"]["n_paired"],
            "anchor_p_upper_n7_tau90": null["anchor"]["p_upper"],
            "scaling_spread": next(item["value"] for item in null["criteria"]
                                   if item["id"] == "H33g"),
            "critical_tau_n12_alpha005": next(row["critical_tau_alpha_0_05"]
                                              for row in null["table"] if row["n"] == 12),
            "required_n_dielectric_delta_tau_0_10":
                budget[("dielectric", 0.1)]["required_n"],
        },
        "verdicts": {identifier: verdict["verdict"] for identifier, verdict in verdicts.items()},
        "verdicts_failed": failed,
        "files": sorted(copied),
        "figures": list(FIGURES),
        "external_deliverables": {},
        "verification": verification,
        "verification_passed": bool(verification.get("passed")),
        "boundaries": [
            "W33-A / W33-B 都是后验读数 / 工具：不拟合主记分牌臂、不占 shot（累计仍 19）、不得当作预注册结论引用。",
            "门禁 = geom AND homo AND ea 三条款之交；合法子集 < 5 判「不可判定」（拒答），不得插补、不得赋伪值、不得静默丢弃。",
            "ORCA 两层（气相 0/22、SMD 乙腈 2/22）合法子集均 < 5，报告必须写「不可判定」，不得引用 -0.602 作为该层还原轴读数。",
            "跨层级只在 22 个配对化合物上比裁决一致性（一致率 95.5%），不把两层数值结果混在同一张记分牌上。",
            "H33e 判否照实登记：预注册猜「两层裁决不一致占多数」，实测两层高度一致；层级依赖体现为「合法子集不够读数」。",
            "W33-B 的精确零分布假设无并列（Kendall tau_a 口径）；有并列的真实读数按 tau_b 处理，此时精确表是下界参考。",
            "预算表的 s0 / N_pop 取 W32-A 各通道中位，是粗算；正式预注册必须用该序列自己的 s0。",
            "四个冻结读数（0.4091179943351143 / 0.4766400383507876 / 0.5861142332208197 / 0.6216672295270079）未动；不改 METRIC_NAMES、不新增特征列、缺行不插补。",
        ],
    }
    write_json(week_root / "week33_summary.json", summary)
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