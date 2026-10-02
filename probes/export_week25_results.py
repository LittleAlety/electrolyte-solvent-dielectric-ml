"""Export the Week 25 deliverables -- the v6 alignment round.

Week 25 maps the six development directions of the parent manuscript (v6) onto
this repository's frozen W21-W24 artefacts.  It buys four things without spending
a single electronic-structure cycle:

  * the displacement-dispersion criterion recomputed on 38 rung-axes with a
    2x10^4 bootstrap interval and a leave-one-rung-out check, plus the reading
    that only this pool size can produce (it holds at N=246 and collapses at
    N=28);
  * the attribution of the "v6 reports zero robust inversions, we report 38/38"
    gap, which the frozen pre-registration judged as H2 = NOT MET and which the
    report resolves as a same-name/different-threshold collision rather than a
    physical disagreement;
  * the minimal expensive-label budget replayed on the 237-row pool, where the
    criterion tau_b >= 0.80 is right-censored for all four acquisition functions;
  * the A-G branch claims of v6 mapped onto in-repo evidence.

Zero shots on the frozen main scoreboard this week (cumulative stays at 12), and
the four frozen readings keep their own definitions:
0.4091179943351143, 0.4766400383507876, 0.5861142332208197, 0.6216672295270079.
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

WEEK = "week25"

# The eight tables the round reads and never writes.  A move here means a delivered
# reading no longer has the input it claims, so the export refuses to run.
FROZEN_RED_LINES = {
    "probes/artifacts/w24_rung_table.csv": "ae734d752511e40113a6acad313321b0818707a0e06a90e5327ba0e4248cae81",
    "probes/artifacts/w24_2_rung_table.csv": "23db67368fdc8bf9d0e2b45d59a12b3e27d325169b9d2f13e377694a8e279c2a",
    "probes/artifacts/w24_ladder.csv": "806542af9c495948d8df923de7cd85eb1ff8407498ed45a0846f6ca174425ac7",
    "probes/artifacts/w24_closed_form.csv": "410d1429468fed8b28c3a58e22e2285b6a57db6bb75e8c67d2366808a2b1b49c",
    "probes/artifacts/w24_displacement_law.csv": "961d41fdadf00bd3ed465e65aeda8ffa7e8113c5c7c462164a6fad34c3f64c79",
    "data/processed/w21_li_coordination_layer.csv": "48864109573f919ab320aa10d2b7b8e78532115e1f65228b16e75a76123eeedc",
    "data/processed/w21_chemical_space_metadata.csv": "fba4a7b287f38018dd30500ff34dc6132c6eec5a17490789b562a1e99868a27f",
    "data/processed/w24_condition_redox_layer.csv": "d61169c1fcb1052289c7631973d8c385c393986ca1614ac575ecc988b78bf636",
}

FROZEN_READINGS = {
    "frozen_baseline": 0.4091179943351143,
    "frozen_headline": 0.4766400383507876,
    "single_representation_cross_seed": 0.5861142332208197,
    "w20_4_promoted_arm": 0.6216672295270079,
}

LANES: dict[str, dict[str, object]] = {
    "w25_v6_alignment": {
        "title": "W25：把母体论文 v6 的六条发展方向映射到本仓（零 QC 四条臂：位移离散度判据完整版 / f_robust 归因 / 最小昂贵标签预算 / 分支认领 A–G）",
        "probe": "probes/w25_v6_alignment.py",
        "prereg": "probes/w25_v6_alignment_prereg.json",
        "summary": "probes/w25_v6_alignment_summary.json",
        "report": "reports/w25_v6_alignment.md",
        "tests": ("tests/test_w25_v6_alignment.py",),
        "artifacts": (
            "probes/artifacts/w25_dispersion_criterion.csv",
            "probes/artifacts/w25_robust_inversion_attribution.csv",
            "probes/artifacts/w25_al_budget.csv",
            "probes/artifacts/w25_branch_claims.csv",
            "probes/artifacts/w25_dispersion_criterion.png",
            "probes/artifacts/w25_robust_inversion.png",
            "probes/artifacts/w25_al_budget.png",
        ),
        "produces_reading": True,
        "promoted": False,
    },
}

LANE_KEYS = tuple(LANES)

CARRY_FORWARD = (
    ("README.md", "README.md"),
    ("reports/decisions_log.md", "decisions_log.md"),
    ("reports/week25_project_charter.md", "week25_project_charter.md"),
    ("reports/week25_delivery_readme.md", "week25_delivery_readme.md"),
    ("reports/w24_delivery_readme.md", "w24_delivery_readme.md"),
    ("reports/w21_framework_slot_map.md", "w21_framework_slot_map.md"),
    ("reports/week23_2_project_charter.md", "week23_2_project_charter.md"),
    ("paper/paper_zh_draft_v2.md", "paper_zh_draft_v2.md"),
    ("paper/build_paper_v2.py", "build_paper_v2.py"),
    ("paper/make_paper_docx.py", "make_paper_docx.py"),
    ("probes/export_week25_results.py", "export_week25_results.py"),
)

EXTERNAL_DELIVERABLES: tuple[tuple[str, str], ...] = ()

FIGURES: tuple[str, ...] = (
    "probes/artifacts/w25_dispersion_criterion.png",
    "probes/artifacts/w25_robust_inversion.png",
    "probes/artifacts/w25_al_budget.png",
)

VERIFIERS = (
    "scripts/verify_four_core_registry.py --check",
    (
        "-m pytest tests/test_repo_hygiene.py tests/test_w25_v6_alignment.py "
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


README_TEXT = (REPOSITORY_ROOT / "reports/week25_delivery_readme.md").read_text(encoding="utf-8")


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


def _verdicts() -> dict[str, dict[str, object]]:
    payload = read_json(REPOSITORY_ROOT / "probes/w25_v6_alignment_summary.json")
    return {entry["id"]: entry for entry in payload["verdicts"]}


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
    verdicts = _verdicts()

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
        "verdicts": verdicts,
        "files": sorted(copied),
        "verification": verification,
        "verification_passed": bool(verification.get("passed")),
        "boundaries": [
            "本轮零电子结构计算：四条臂只读冻结的 W21–W24 产物表，不新增任何量子化学作业。",
            "不引用任何 Reaxys 数值；Batt-P30K / RX-392 / THEMol 只作参考层，不入任何训练池或标签。",
            "主记分牌 0 次尝试（累计 12 次）；四个冻结读数未动，八条输入红线逐条 sha256 复核。",
            "W25-1 的 38 个台阶-轴不独立（同一台阶两条轴共享分子，且两个池的水平不同），bootstrap 区间只读作同一关系的稳健性，不读作显著性检验。",
            "W25-2 的本仓 f_robust_inversion 与 v6 的 frobustinv(z) 是同名不同阈：本仓用绝对 0.05 eV，v6 用随 σ 缩放的阈；差异因此读作阈值约定的产物，不读作物理分歧。",
            "W25-2 的预注册 H2 判否（28/38 过门，10 个违反），H2a / H2b 是同轮的探索性细化，不得当作预注册结论。",
            "W25-3 的 tau_b >= 0.80 在 120 步上限处右删失（四臂中位 n_T 全为 121），因此 H3a 与 H3c 是空判据，只有 H3b 携带信息。",
            "W25-3 的 X0 特征是本仓口径下的代理，池是 246 名册里特征齐全的 237 行，与 v6 的 18 分子池 / 12 项 X0 不可相加。",
            "W25-5（几何台阶 G1→G2）与 W25-6（介电层 1/ε 律）登记但本轮不执行，理由与设计见交付说明 §7。",
        ],
    }
    write_json(week_root / "week25_summary.json", summary)
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
