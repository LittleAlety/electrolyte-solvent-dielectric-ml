"""Export the Week 27 deliverables -- the dielectric-response descriptor block.

Week 27 appends the thirteen ddCOSMO response columns Week 26 measured (Born
prefactors, cavity residuals, band coefficients of variation, electron affinities
and orbital slopes against 1/epsilon) to the dense lever-4 physical block and
scores that arm on the frozen main scoreboard pool: 2029 base training rows / 457
scored rows over 97 compounds, GroupKFold by InChIKey, five frozen seeds.

The block is derived entirely from on-disk Week 26 artefacts, so the arm costs no
new quantum chemistry.  Two disciplines are declared rather than assumed: missing
pool rows are not imputed (the block carries NaN and XGBoost's own missing-value
handling applies), and no column of the block touches the measured permittivity.

This round takes the first shot on the frozen main scoreboard since Week 20 (delta
1, cumulative 13).  The four frozen readings keep their own definitions:
0.4091179943351143, 0.4766400383507876, 0.5861142332208197, 0.6216672295270079.
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

WEEK = "week27"

# The three artefacts the round reads and never writes.  A move here means a delivered
# reading no longer has the input it claims, so the export refuses to run.
FROZEN_RED_LINES = {
    "probes/artifacts/w26_dielectric_scan.csv":
        "8ac4fc2a2b50185f989cda358fd39203c6204dc6b3dcaae17affdb5f55ec325f",
    "probes/artifacts/w26_born_fit.csv":
        "e50ae20acf007cb48d93eef6a05d5eb72c831b163272a2170b58e9275c9c7393",
    "probes/artifacts/w26_anion_gate.csv":
        "6dd5663921a6c85e6c9d6fda7a02f38aacd0c97278e409b7cff5002911a3acc9",
}

FROZEN_READINGS = {
    "frozen_baseline": 0.4091179943351143,
    "frozen_headline": 0.4766400383507876,
    "single_representation_cross_seed": 0.5861142332208197,
    "w20_4_promoted_arm": 0.6216672295270079,
}

LANES: dict[str, dict[str, object]] = {
    "w27_dielectric_response": {
        "title": "W27：介电响应描述符块接入冻结主记分牌池（13 列 ddCOSMO 响应列 + 稠密 lever4；五种子 GroupKFold by InChIKey）",
        "probe": "probes/w27_dielectric_response.py",
        "prereg": "probes/w27_dielectric_response_prereg.json",
        "summary": "probes/w27_dielectric_response_summary.json",
        "report": "reports/w27_dielectric_response.md",
        "tests": ("tests/test_w27_dielectric_response.py",),
        "artifacts": (
            "probes/artifacts/w27_dielectric_response_block.csv",
            "probes/artifacts/w27_dielectric_response_repeats.csv",
            "probes/artifacts/w27_dielectric_response.png",
            "probes/w27_dielectric_response_placebo_summary.json",
        ),
        "produces_reading": True,
        "promoted": False,
    },
}

CARRY_FORWARD = (
    ("README.md", "README.md"),
    ("reports/decisions_log.md", "decisions_log.md"),
    ("reports/week27_project_charter.md", "week27_project_charter.md"),
    ("reports/week27_delivery_readme.md", "week27_delivery_readme.md"),
    ("reports/week26_project_charter.md", "week26_project_charter.md"),
    ("reports/week26_delivery_readme.md", "week26_delivery_readme.md"),
    ("paper/paper_zh_draft_v2.md", "paper_zh_draft_v2.md"),
    ("paper/make_paper_docx_template.py", "make_paper_docx_template.py"),
    ("probes/export_week27_results.py", "export_week27_results.py"),
)

LANE_KEYS = tuple(LANES)

EXTERNAL_DELIVERABLES: tuple[tuple[str, str], ...] = ()

FIGURES: tuple[str, ...] = (
    "probes/artifacts/w27_dielectric_response.png",
)

VERIFIERS = (
    "scripts/verify_four_core_registry.py --check",
    (
        "-m pytest tests/test_repo_hygiene.py tests/test_w27_dielectric_response.py "
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
            "revision": payload.get("revision"),
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


README_TEXT = (REPOSITORY_ROOT / "reports/week27_delivery_readme.md").read_text(encoding="utf-8")


def _verdicts() -> dict[str, dict[str, object]]:
    payload = read_json(REPOSITORY_ROOT / "probes/w27_dielectric_response_summary.json")
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
    verification = run_verifiers(REPOSITORY_ROOT, VERIFIERS)

    promoted_lanes = sorted(key for key, payload in lanes.items() if bool(payload["promoted"]))
    reading_lanes = sorted(key for key, payload in lanes.items() if bool(payload["produces_reading"]))
    verdicts = _verdicts()
    probe_summary = read_json(REPOSITORY_ROOT / "probes/w27_dielectric_response_summary.json")

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
        "main_scoreboard_attempts_delta": 1,
        "cumulative_main_scoreboard_attempts": 13,
        "frozen_readings": FROZEN_READINGS,
        "frozen_red_lines": frozen,
        "external_deliverables": [destination for _, destination in EXTERNAL_DELIVERABLES],
        "figures": [Path(figure).name for figure in FIGURES],
        "verdicts": verdicts,
        "headline_readings": {
            "primary_representation": probe_summary["primary_representation"],
            "anchor_mean": probe_summary["anchor_mean"],
            "block_mean": probe_summary["block_mean"],
            "delta_mean": probe_summary["delta_mean"],
            "delta_min": probe_summary["delta_min"],
            "delta_physical_mean": probe_summary["delta_physical_mean"],
            "placebo_delta": probe_summary["placebo_delta"],
            "block_row_coverage": probe_summary["coverage"]["block_row_coverage"],
            "scored_compounds_with_the_block": probe_summary["coverage"]["scored_compounds_with_the_block"],
        },
        "files": sorted(copied),
        "verification": verification,
        "verification_passed": bool(verification.get("passed")),
        "boundaries": [
            "W27 的池、评分掩码、分组切分器、拟合器与五种子集合全部取自冻结主记分牌；本枪只改表示块。",
            "块由盘上已有的 W26 产物派生，不跑新的量子化学；13 列响应列的构造规则在预注册里逐列冻结。",
            "缺行不插补：块在 W26 名册之外的池行上留 NaN，交给 XGBoost 自带的缺失值处理；不计算任何折内统计量。",
            "块里没有任何一列触及被测的介电常数；每一列都是溶质对给定 epsilon 连续介质的响应。",
            "主读数取 Morgan+Physical（与冻结锚 0.5433111678100043 同一表示）；Physical 单表示读数作为描述性次读数并列报出。",
            "预注册修订 2 更正了锚的表示口径（修订 1 误标为 Physical），修订发生在只跑过 1 个种子的冒烟之后、五种子生产运行之前；没有任何阈值被移动。",
            "主记分牌 shot = 1（累计 13）；四个冻结读数未动，三条输入红线逐条 sha256 复核。",
            "不引用任何 Reaxys 数值；THEMol（CC BY-NC 4.0）不入交付包；Batt-P30K（MIT）与 RX-392 / SolvFunc-87 只作参考层。",
        ],
    }
    write_json(week_root / "week27_summary.json", summary)
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

