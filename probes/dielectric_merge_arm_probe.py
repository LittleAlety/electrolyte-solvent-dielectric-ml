"""The Week 14 merge arm: combining the levers that cleared their criterion.

The pre-registration is explicit about when this arm may run::

    only levers that cleared their own criterion may be combined. The merge arm
    is re-scored on the main scoreboard, and its delta is reported against the
    best single passing lever as well as against the baseline, so a merge that
    adds nothing is visible.

    if_nothing_passes: the merge arm is not run; the week reports three dead
    levers and keeps the 0.5454 reading untouched.

This script therefore has three outcomes, and it records which one happened
rather than being silent about the ones that did not:

* **no lever passed** - the merge arm is not run. The summary states the
  pre-registered reason and inventories the three dead levers with their own
  readings, so "three dead levers" is a documented fact rather than an omission.
* **exactly one lever passed** - the merge degenerates: there is nothing to
  combine, so the merged reading *is* that lever's own reading, the delta against
  the best single passing lever is 0.0 by construction, and the degeneracy is
  labelled. Nothing is refitted, so no new scored attempt is counted.
* **two or more levers passed** - a real combination. This arm would have to
  refit the joint configuration, which this round does not implement; the script
  raises rather than pretending a degenerate identity is a combination.

The lever summaries are read, never trusted blindly: a lever whose summary is
missing or carries no explicit pass/fail is reported as `pending`, never guessed.
"""

from __future__ import annotations

import argparse
import io
import json
import sys
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))
sys.path.insert(0, str(REPOSITORY_ROOT / "probes"))

from electrolyte_ml.exporting import canonical_text_sha256
from electrolyte_ml.pathing import portable_relative_path

PREREG_PATH = REPOSITORY_ROOT / "probes" / "dielectric_r2_levers_prereg.json"
SUMMARY_PATH = REPOSITORY_ROOT / "probes" / "dielectric_merge_arm_summary.json"
REPORT_PATH = REPOSITORY_ROOT / "reports" / "dielectric_merge_arm.md"
MERGE_PATH = Path(__file__).resolve()

BASELINE_ARM = "paired_base"
HYBRID = "Morgan+Physical"
MERGE_ARM = "week14_merge_arm"

#: The lever summaries, in the order the pre-registration lists the levers.
LEVER_SUMMARIES = (
    (
        "lever_2_association_blind_spot_features",
        REPOSITORY_ROOT / "probes" / "dielectric_association_features_summary.json",
    ),
    (
        "lever_3_target_transform_and_robust_loss",
        REPOSITORY_ROOT / "probes" / "dielectric_target_transform_probe_summary.json",
    ),
    (
        "lever_7_bagging",
        REPOSITORY_ROOT / "probes" / "dielectric_bagging_probe_summary.json",
    ),
)


class MergeArmNotImplemented(RuntimeError):
    """Raised when two or more levers passed and a joint refit would be needed."""


def _use_utf8_stdout() -> None:
    encoding = (getattr(sys.stdout, "encoding", "") or "").lower()
    if "utf-8" in encoding or "utf8" in encoding:
        return
    buffer = getattr(sys.stdout, "buffer", None)
    if buffer is not None:
        sys.stdout = io.TextIOWrapper(buffer, encoding="utf-8", errors="replace")


def read_lever_state(lever_id: str, path: Path) -> dict[str, object]:
    """Read one lever summary without trusting it further than it can be read."""

    if not path.is_file():
        return {
            "lever_id": lever_id,
            "summary": portable_relative_path(path, root=REPOSITORY_ROOT),
            "state": "pending",
            "reason": "the lever summary is not on disk, so no pass/fail can be read",
            "reading": None,
        }
    payload = json.loads(path.read_text(encoding="utf-8"))
    verdict = payload.get("verdict")
    if not isinstance(verdict, Mapping) or "decision" not in verdict:
        return {
            "lever_id": lever_id,
            "summary": portable_relative_path(path, root=REPOSITORY_ROOT),
            "summary_sha256": canonical_text_sha256(path),
            "state": "pending",
            "reason": "the lever summary carries no explicit pass/fail decision",
            "reading": None,
        }
    decision = str(verdict["decision"])
    state = {"pass": "pass", "dead": "dead", "unverified": "unverified"}.get(decision, "pending")
    reading = lever_reading(payload, lever_id)
    return {
        "lever_id": lever_id,
        "summary": portable_relative_path(path, root=REPOSITORY_ROOT),
        "summary_sha256": canonical_text_sha256(path),
        "state": state,
        "decision": decision,
        "reasons": list(verdict.get("reasons", [])),
        "carried_into_the_merge_arm": bool(verdict.get("carried_into_the_merge_arm", False)),
        "reading": reading,
    }


def lever_reading(payload: Mapping[str, object], lever_id: str) -> dict[str, object]:
    """Pull one lever's own main-scoreboard reading out of its summary."""

    readings = payload.get("readings")
    if not isinstance(readings, Mapping) or lever_id not in readings:
        return {"available": False}
    block = readings[lever_id]
    if not isinstance(block, Mapping) or HYBRID not in block:
        return {"available": False}
    hybrid = block[HYBRID]
    baseline = readings.get(BASELINE_ARM)
    baseline_hybrid = baseline[HYBRID] if isinstance(baseline, Mapping) else None
    return {
        "available": True,
        "arm": lever_id,
        "representation": HYBRID,
        "r2_mean": float(hybrid["r2"]["mean"]),
        "r2_std": float(hybrid["r2"]["std"]),
        "mae_mean": float(hybrid["mae"]["mean"]),
        "mae_gt60_mean": float(hybrid["mae_gt60"]["mean"]),
        "spearman_mean": float(hybrid["spearman"]["mean"]),
        "baseline_r2_mean": (
            float(baseline_hybrid["r2"]["mean"]) if isinstance(baseline_hybrid, Mapping) else None
        ),
        "baseline_r2_std": (
            float(baseline_hybrid["r2"]["std"]) if isinstance(baseline_hybrid, Mapping) else None
        ),
    }


def build_summary(
    *,
    lever_states: Sequence[Mapping[str, object]],
    prereg_payload: Mapping[str, object],
    prereg_path: Path,
    generated_at: str,
) -> dict[str, object]:
    """Decide which of the three pre-registered outcomes happened."""

    passing = [state for state in lever_states if state["state"] == "pass"]
    pending = [state for state in lever_states if state["state"] == "pending"]
    dead = [state for state in lever_states if state["state"] == "dead"]
    merge_rule = prereg_payload["merge_rule"]

    if pending:
        return _not_run(
            lever_states=lever_states,
            passing=passing,
            dead=dead,
            pending=pending,
            reason=(
                "at least one lever has no readable pass/fail yet, so the merge arm "
                "waits rather than guessing: " + ", ".join(str(s["lever_id"]) for s in pending)
            ),
            merge_rule=merge_rule,
            prereg_payload=prereg_payload,
            prereg_path=prereg_path,
            generated_at=generated_at,
        )

    if not passing:
        return _not_run(
            lever_states=lever_states,
            passing=passing,
            dead=dead,
            pending=pending,
            reason=(
                "no lever cleared its own criterion, so the pre-registered "
                "`merge_rule.if_nothing_passes` applies: the merge arm is not run "
                "and the week reports three dead levers"
            ),
            merge_rule=merge_rule,
            prereg_payload=prereg_payload,
            prereg_path=prereg_path,
            generated_at=generated_at,
        )

    if len(passing) > 1:
        raise MergeArmNotImplemented(
            "more than one lever cleared its criterion ("
            + ", ".join(str(state["lever_id"]) for state in passing)
            + "): a joint refit of the combined configuration is required and this "
            "round does not implement it. Refusing to report an identity as a merge."
        )

    return _degenerate_merge(
        lever_states=lever_states,
        passing=passing,
        dead=dead,
        merge_rule=merge_rule,
        prereg_payload=prereg_payload,
        prereg_path=prereg_path,
        generated_at=generated_at,
    )


def _base_summary(
    *,
    lever_states: Sequence[Mapping[str, object]],
    passing: Sequence[Mapping[str, object]],
    dead: Sequence[Mapping[str, object]],
    pending: Sequence[Mapping[str, object]],
    merge_rule: Mapping[str, object],
    prereg_payload: Mapping[str, object],
    prereg_path: Path,
    generated_at: str,
) -> dict[str, object]:
    inventories = []
    for state in lever_states:
        reading = state.get("reading")
        inventories.append(
            {
                "lever_id": state["lever_id"],
                "summary": state["summary"],
                "summary_sha256": state.get("summary_sha256"),
                "state": state["state"],
                "decision": state.get("decision"),
                "delta_r2": (
                    float(reading["r2_mean"]) - float(reading["baseline_r2_mean"])
                    if isinstance(reading, Mapping) and reading.get("available")
                    else None
                ),
                "r2_mean": (
                    float(reading["r2_mean"])
                    if isinstance(reading, Mapping) and reading.get("available")
                    else None
                ),
                "reasons": list(state.get("reasons", [])),
            }
        )
    return {
        "schema_version": 1,
        "task": "week14_r2_levers",
        "artifact": "merge_arm",
        "title": "Week 14 merge arm",
        "generated_at_utc": generated_at,
        "prereg": {
            "path": portable_relative_path(prereg_path, root=REPOSITORY_ROOT),
            "sha256": canonical_text_sha256(prereg_path),
            "merge_rule": dict(merge_rule),
            "if_nothing_passes": str(merge_rule.get("if_nothing_passes", "")),
        },
        "lever_inventory": inventories,
        "passing_levers": [str(state["lever_id"]) for state in passing],
        "dead_levers": [str(state["lever_id"]) for state in dead],
        "pending_levers": [str(state["lever_id"]) for state in pending],
        "script": portable_relative_path(MERGE_PATH, root=REPOSITORY_ROOT),
        "script_sha256": canonical_text_sha256(MERGE_PATH),
        "honest_boundaries": [
            "this arm combines only levers that cleared their own criterion; a dead lever is never smuggled in",
            "the main scoreboard is the 457-row / 97-compound paired_base pool, not the v1.0 236-row pool",
            "0.5332 / 0.5454 are never quoted next to the v1.0 headline 0.364 without their pool definitions",
            "no random_row split was constructed, let alone judged",
        ],
        "outputs": {},
    }


def _not_run(
    *,
    lever_states: Sequence[Mapping[str, object]],
    passing: Sequence[Mapping[str, object]],
    dead: Sequence[Mapping[str, object]],
    pending: Sequence[Mapping[str, object]],
    reason: str,
    merge_rule: Mapping[str, object],
    prereg_payload: Mapping[str, object],
    prereg_path: Path,
    generated_at: str,
) -> dict[str, object]:
    summary = _base_summary(
        lever_states=lever_states,
        passing=passing,
        dead=dead,
        pending=pending,
        merge_rule=merge_rule,
        prereg_payload=prereg_payload,
        prereg_path=prereg_path,
        generated_at=generated_at,
    )
    summary.update(
        {
            "merge_arm_run": False,
            "degenerate_single_lever_merge": False,
            "reason": reason,
            "merged_reading": None,
            "baseline_reading": None,
            "delta_vs_baseline": None,
            "delta_vs_best_single_lever": None,
            "best_single_lever": None,
            "scored_attempts": 0,
            "shots": {
                "merge_arm": 0,
                "note": "the merge arm was not run, so it adds no scored attempt to the main scoreboard",
            },
        }
    )
    return summary


def _degenerate_merge(
    *,
    lever_states: Sequence[Mapping[str, object]],
    passing: Sequence[Mapping[str, object]],
    dead: Sequence[Mapping[str, object]],
    merge_rule: Mapping[str, object],
    prereg_payload: Mapping[str, object],
    prereg_path: Path,
    generated_at: str,
) -> dict[str, object]:
    survivor = passing[0]
    reading = survivor["reading"]
    if not isinstance(reading, Mapping) or not reading.get("available"):
        raise ValueError(f"{survivor['lever_id']}: the passing lever carries no readable reading")
    summary = _base_summary(
        lever_states=lever_states,
        passing=passing,
        dead=dead,
        pending=[],
        merge_rule=merge_rule,
        prereg_payload=prereg_payload,
        prereg_path=prereg_path,
        generated_at=generated_at,
    )
    delta_vs_baseline = float(reading["r2_mean"]) - float(reading["baseline_r2_mean"])
    summary.update(
        {
            "merge_arm_run": True,
            "degenerate_single_lever_merge": True,
            "reason": (
                "exactly one lever cleared its criterion, so the merge has nothing to "
                "combine: the merged reading is that lever's own reading and the delta "
                "against the best single passing lever is 0.0 by construction. The "
                "pre-registered `merge_rule` has not been violated, but it has been "
                "satisfied degenerately and the fact is labelled rather than dressed up "
                "as a combination effect."
            ),
            "merged_reading": {
                "arm": MERGE_ARM,
                "equivalent_to": str(survivor["lever_id"]),
                "representation": HYBRID,
                "r2_mean": float(reading["r2_mean"]),
                "r2_std": float(reading["r2_std"]),
                "mae_mean": float(reading["mae_mean"]),
                "mae_gt60_mean": float(reading["mae_gt60_mean"]),
                "spearman_mean": float(reading["spearman_mean"]),
            },
            "baseline_reading": {
                "arm": BASELINE_ARM,
                "representation": HYBRID,
                "r2_mean": float(reading["baseline_r2_mean"]),
                "r2_std": float(reading["baseline_r2_std"]),
            },
            "delta_vs_baseline": delta_vs_baseline,
            "delta_vs_best_single_lever": 0.0,
            "best_single_lever": str(survivor["lever_id"]),
            "scored_attempts": 0,
            "shots": {
                "merge_arm": 0,
                "note": (
                    "no refit was performed, so the degenerate merge adds no scored "
                    "attempt; the underlying reading is the passing lever's own shot "
                    "and is counted there, not twice here"
                ),
            },
        }
    )
    return summary


def render_report(summary: Mapping[str, object]) -> list[str]:
    """Render the markdown report from the summary, so the two cannot drift."""

    lines = [
        "# Week 14 合并臂（杠杆 2 / 3 / 7）",
        "",
        (
            "> 本文由 `probes/dielectric_merge_arm_probe.py` 从 "
            "`probes/dielectric_merge_arm_summary.json` 确定性渲染；"
            "数字与摘要同源，改一处必须重跑脚本。"
        ),
        "",
        "## 一、预注册口径",
        "",
        f"- 预注册：`probes/dielectric_r2_levers_prereg.json`（sha256=`{summary['prereg']['sha256']}`）",
        f"- 合并规则：{summary['prereg']['merge_rule'].get('rule')}",
        f"- 全不过门时的规则：{summary['prereg']['if_nothing_passes']}",
        "",
        "## 二、杠杆清点",
        "",
        "| 杠杆 | 状态 | 主记分牌 R² 均值 | ΔR²（相对各自基准臂） |",
        "| --- | --- | ---: | ---: |",
    ]
    for item in summary["lever_inventory"]:
        r2 = item["r2_mean"]
        delta = item["delta_r2"]
        lines.append(
            f"| `{item['lever_id']}` | {item['state']} | "
            f"{'—' if r2 is None else f'{float(r2):.6f}'} | "
            f"{'—' if delta is None else f'{float(delta):+.6f}'} |"
        )
    lines += [
        "",
        (
            f"- 过门：{summary['passing_levers'] or '无'}；"
            f"死：{summary['dead_levers'] or '无'}；"
            f"未定：{summary['pending_levers'] or '无'}"
        ),
        "",
        "## 三、判决",
        "",
        f"- 合并臂是否开跑：**{summary['merge_arm_run']}**",
        f"- 是否退化为单杠杆：**{summary['degenerate_single_lever_merge']}**",
        f"- 理由：{summary['reason']}",
        "",
    ]
    if summary["merge_arm_run"]:
        merged = summary["merged_reading"]
        lines += [
            "## 四、合并读数（与基准、与最好单杠杆同时对照）",
            "",
            "| 口径 | R² 均值 | R² 标准差 | MAE | MAE·ε>60 |",
            "| --- | ---: | ---: | ---: | ---: |",
            (
                f"| 基准臂 `{summary['baseline_reading']['arm']}` | "
                f"{float(summary['baseline_reading']['r2_mean']):.6f} | "
                f"{float(summary['baseline_reading']['r2_std']):.6f} | — | — |"
            ),
            (
                f"| 合并臂（= `{merged['equivalent_to']}`） | "
                f"{float(merged['r2_mean']):.6f} | {float(merged['r2_std']):.6f} | "
                f"{float(merged['mae_mean']):.6f} | {float(merged['mae_gt60_mean']):.6f} |"
            ),
            "",
            f"- Δ 相对基准：**{float(summary['delta_vs_baseline']):+.6f}**",
            (
                f"- Δ 相对最好单杠杆（`{summary['best_single_lever']}`）："
                f"**{float(summary['delta_vs_best_single_lever']):+.6f}**"
                "（合并等于白干时此处就是 0.0，这里正是如此）"
            ),
            "",
            "## 五、shots 计数",
            "",
            f"- 合并臂自身新增的记分牌实测次数：**{summary['scored_attempts']}**",
            f"- 说明：{summary['shots']['note']}",
        ]
    else:
        lines += [
            "## 四、为什么不跑",
            "",
            "按预注册原文，合并臂只在有杠杆过门时才开跑。本轮逐条结果是：",
            "",
        ]
        for item in summary["lever_inventory"]:
            delta = "—" if item["delta_r2"] is None else f"{float(item['delta_r2']):+.6f}"
            lines.append(f"- `{item['lever_id']}`：{item['state']}，ΔR² = {delta}")
        lines += [
            "",
            "因此这里**没有**「合并等于白干」需要回答：根本没有合并发生。",
            "",
            "## 五、shots 计数",
            "",
            f"- 合并臂自身新增的记分牌实测次数：**{summary['scored_attempts']}**",
            f"- 说明：{summary['shots']['note']}",
        ]
    lines += [
        "",
        "## 六、诚实边界",
        "",
    ]
    lines += [f"- {item}" for item in summary["honest_boundaries"]]
    lines += [
        "",
        "## 七、产物",
        "",
    ]
    lines += [f"- `{name}`：`{path}`" for name, path in sorted(summary["outputs"].items())]
    lines.append("")
    return lines


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--summary", type=Path, default=SUMMARY_PATH)
    parser.add_argument("--report", type=Path, default=REPORT_PATH)
    parser.add_argument(
        "--check",
        action="store_true",
        help="re-derive the decision from the stored summary instead of re-reading the levers",
    )
    return parser.parse_args(argv)


def check_summary(summary: Mapping[str, object]) -> list[str]:
    problems: list[str] = []
    inventory = summary["lever_inventory"]
    states = {item["lever_id"]: item["state"] for item in inventory}
    passing = summary["passing_levers"]
    if summary["merge_arm_run"]:
        if len(passing) != 1:
            problems.append("the merge arm claims to have run without exactly one passing lever")
        if summary["merged_reading"]["equivalent_to"] != passing[0]:
            problems.append("the merged reading is not attributed to the passing lever")
        if summary["delta_vs_best_single_lever"] != 0.0:
            problems.append("a degenerate merge must report exactly 0.0 against the best single lever")
        if summary["merged_reading"]["r2_mean"] != summary["baseline_reading"]["r2_mean"] + summary["delta_vs_baseline"]:
            problems.append("the merged delta is not the difference of the two stored means")
    else:
        if passing:
            problems.append("the merge arm was skipped even though a lever passed")
        if not summary["reason"]:
            problems.append("a skipped merge arm must state why")
    for lever_id, state in states.items():
        if state == "pass" and lever_id not in passing:
            problems.append(f"{lever_id} passed but is not in the passing list")
    if summary["scored_attempts"] != 0:
        problems.append("this arm performs no refit, so its scored-attempt count must be zero")
    return problems


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    _use_utf8_stdout()

    if args.check:
        payload = json.loads(Path(args.summary).read_text(encoding="utf-8"))
        problems = check_summary(payload)
        if problems:
            print(f"CHECK FAILED: {args.summary}")
            for problem in problems:
                print(f"  - {problem}")
            return 1
        print(
            f"CHECK OK: {args.summary} merge_arm_run={payload['merge_arm_run']} "
            f"degenerate={payload['degenerate_single_lever_merge']}"
        )
        return 0

    prereg_payload = json.loads(PREREG_PATH.read_text(encoding="utf-8"))
    lever_states = [read_lever_state(lever_id, path) for lever_id, path in LEVER_SUMMARIES]
    summary = build_summary(
        lever_states=lever_states,
        prereg_payload=prereg_payload,
        prereg_path=PREREG_PATH,
        generated_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )
    summary["outputs"] = {
        "summary": portable_relative_path(Path(args.summary), root=REPOSITORY_ROOT),
        "report": portable_relative_path(Path(args.report), root=REPOSITORY_ROOT),
    }
    summary_path = Path(args.summary)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    report_lines = render_report(summary)
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(report_lines), encoding="utf-8", newline="\n")
    print("\n".join(report_lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())