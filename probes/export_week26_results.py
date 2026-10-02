"""Export the Week 26 deliverables -- the dielectric-law round.

Week 26 buys the first arbitrary-permittivity continuum scan in this repository.
xTB 6.7.1 ddCOSMO (--cosmo EPSILON) decouples epsilon from the identity of a named
solvent, and one gas-phase GFN2 geometry is held rigid across every epsilon and every
charge state, so the dielectric response is separated from geometry relaxation.
It leaves with four things:

  * the Born one-parameter form tested on 14 epsilon points instead of 3, with the
    epsilon >= 80.4 readings measured rather than extrapolated (W26-1);
  * a negative result on the anion binding gate, attributed to the method rather than
    to the continuum: the solvation window is smaller than GFN2’s own gas-phase
    electron-affinity spread (W26-2);
  * a same-epsilon contrast between ddCOSMO, ALPB and CPCM-X, reported as a difference
    between approximations and never as a ranking (W26-3);
  * a priced geometry rung (W26-4) that is registered but not executed.

It also records one convention finding about a frozen artefact: the gas-phase columns
of data/processed/w21_li_coordination_layer.csv are the FIRST ISCF block of an --opt
log (the input geometry), not the optimised geometry.  Week 26 reproduces that block
exactly (H1g, 0.0 eV / 3.8e-11 Ha) and reports the literal anchor (H1f) as failed.

Zero shots on the frozen main scoreboard this week (cumulative stays at 12), and the
four frozen readings keep their own definitions:
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

WEEK = "week26"

# The two artefacts the round reads and never writes.  A move here means a delivered
# reading no longer has the input it claims, so the export refuses to run.
FROZEN_RED_LINES = {
    "data/processed/w21_li_coordination_layer.csv":
        "48864109573f919ab320aa10d2b7b8e78532115e1f65228b16e75a76123eeedc",
    "probes/artifacts/w24_born_curves.csv":
        "8f667824e89336524996c826885dddd6c2c0470ae6cb654d0633d6611b03b260",
}

FROZEN_READINGS = {
    "frozen_baseline": 0.4091179943351143,
    "frozen_headline": 0.4766400383507876,
    "single_representation_cross_seed": 0.5861142332208197,
    "w20_4_promoted_arm": 0.6216672295270079,
}

LANES: dict[str, dict[str, object]] = {
    "w26_dielectric_law": {
        "title": "W26：介电响应律的稠密实测（ddCOSMO 任意 epsilon + 刚性几何 242 分子）、阴离子束缚闸门与隐式模型层级对照",
        "probe": "probes/w26_dielectric_law.py",
        "prereg": "probes/w26_dielectric_law_prereg.json",
        "summary": "probes/w26_dielectric_law_summary.json",
        "report": "reports/w26_dielectric_law.md",
        "tests": ("tests/test_w26_dielectric_law.py",),
        "artifacts": (
            "probes/artifacts/w26_dielectric_scan.csv",
            "probes/artifacts/w26_born_fit.csv",
            "probes/artifacts/w26_anion_gate.csv",
            "probes/artifacts/w26_model_contrast.csv",
            "probes/artifacts/w26_dielectric_law.png",
            "probes/artifacts/w26_anion_gate.png",
        ),
        "produces_reading": True,
        "promoted": False,
    },
}

LANE_KEYS = tuple(LANES)

CARRY_FORWARD = (
    ("README.md", "README.md"),
    ("reports/decisions_log.md", "decisions_log.md"),
    ("reports/week26_project_charter.md", "week26_project_charter.md"),
    ("reports/week26_delivery_readme.md", "week26_delivery_readme.md"),
    ("reports/week25_project_charter.md", "week25_project_charter.md"),
    ("reports/week25_delivery_readme.md", "week25_delivery_readme.md"),
    ("paper/paper_zh_draft_v2.md", "paper_zh_draft_v2.md"),
    ("probes/export_week26_results.py", "export_week26_results.py"),
)

EXTERNAL_DELIVERABLES: tuple[tuple[str, str], ...] = ()

FIGURES: tuple[str, ...] = (
    "probes/artifacts/w26_dielectric_law.png",
    "probes/artifacts/w26_anion_gate.png",
)

VERIFIERS = (
    "scripts/verify_four_core_registry.py --check",
    (
        "-m pytest tests/test_repo_hygiene.py tests/test_w26_dielectric_law.py "
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


README_TEXT = (REPOSITORY_ROOT / "reports/week26_delivery_readme.md").read_text(encoding="utf-8")


def _verdicts() -> dict[str, dict[str, object]]:
    payload = read_json(REPOSITORY_ROOT / "probes/w26_dielectric_law_summary.json")
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
    probe_summary = read_json(REPOSITORY_ROOT / "probes/w26_dielectric_law_summary.json")

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
        "headline_readings": {
            "born_r2_median_ion": probe_summary["born_fit"]["r2_median_ion"],
            "born_c_eV_median_ion": probe_summary["born_fit"]["c_eV_median_ion"],
            "residual_born_at_200_median_ion_eV": probe_summary["born_fit"]["residual_born_200_median_ion_eV"],
            "travel_200_to_1000_median_ion_eV": probe_summary["born_fit"]["travel_200_1000_median_ion_eV"],
            "power_band_median_ion_eV": probe_summary["born_fit"]["power_band_median_ion_eV"],
            "anion_gate_share": probe_summary["anion_gate"]["share_with_gate"],
            "model_contrast_median_abs_diff_eV": probe_summary["model_contrast"]["median_abs_diff_eV"],
            "anchor_convention_max_orbital_dev_eV": probe_summary["anchor_convention"]["max_orbital_dev_eV"],
        },
        "files": sorted(copied),
        "verification": verification,
        "verification_passed": bool(verification.get("passed")),
        "boundaries": [
            "本仓（W26）= GFN2-xTB / ddCOSMO 任意 epsilon / 刚性气相几何 / 242 分子；母体论文 v6 = r2SCAN-3c / CPCM 裸扫描 / 18 分子 / 10 台阶。跨层级只比函数形式与量级，绝不比绝对值。",
            "H1b / H1c / H1d 的主裁决取离子态（阳离子 + 阴离子）；三态合并的同一读数并列报出，供读者自行取用。",
            "ddCOSMO / ALPB / CPCM-X 是三种不同的隐式溶剂近似，W26-3 只报差，不报谁更正确。",
            "W26-2 的两个判据都判否，且原因是方法而非连续介质：气相 EA 的 p05-p95 跨距远大于整条介电扫描能提供的 EA 位移，因此不能用 GFN2 的 EA 做过零闸门。",
            "冻结层 data/processed/w21_li_coordination_layer.csv 的气相列是 xTB --opt 日志里的首个 ISCF 块（输入几何），不是优化后几何。W26 按该口径复现偏差为 0.0 eV / 3.8e-11 Ha（H1g 成立），按原文口径则判否（H1f）。本仓不改该冻结表。",
            "W26 不修改 W24-1 的任何冻结表；对 W24-1 的再解释（几何弛豫被混入、epsilon 与溶剂身份不可分、epsilon >= 80.4 是外推）属于 W26 评注。",
            "预注册在修订 2 中改写了 H1b/H1c/H1d/H1e/H1f 的操作化定义与 H2a 的分母，修订发生在生产运行之前，且没有任何阈值被移动；修订依据记在 prereg.revision_note 与 smoke_pilot_evidence 里。",
            "W26-4（几何台阶 G1->G2）只登记成本，不设成立/判否，也不得被引用为已完成的几何台阶。",
            "主记分牌 shot = 0（累计 12）；四个冻结读数未动，两条输入红线逐条 sha256 复核。",
            "不引用任何 Reaxys 数值；THEMol（CC BY-NC 4.0）不入交付包；Batt-P30K（MIT）与 RX-392 / SolvFunc-87 只作参考层。",
        ],
    }
    write_json(week_root / "week26_summary.json", summary)
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

