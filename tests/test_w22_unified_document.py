"""Guards for the Week 22 W22-3 deliverables.

Two things are protected here:

* ``probes/build_unified_data_document.py`` -- the unified data document must be
  a pure function of the files it inventories.  The synthetic-repo tests pin the
  two mechanical properties that make that true (no wall-clock timestamp, stable
  ordering) and that ``--check`` actually detects a one-byte edit; the live-repo
  test pins that the same document can be rebuilt from the current tree.
* ``probes/w22_broad_pool_budget.py`` -- the pre-registered promotion criterion
  and the funnel it produces on the 115,756-row candidate pool.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILDER = ROOT / "probes" / "build_unified_data_document.py"
BUDGET = ROOT / "probes" / "w22_broad_pool_budget.py"
BUDGET_PREREG = ROOT / "probes" / "w22_broad_pool_budget_prereg.json"
BUDGET_SUMMARY = ROOT / "probes" / "w22_broad_pool_budget_summary.json"
DELIVERED = Path(r"E:\Claude Code\电解质ML\成果输出\数据统一文档.md")

FROZEN_READINGS = (
    "0.4091179943351143",
    "0.4766400383507876",
    "0.5861142332208197",
    "0.6216672295270079",
)

REQUIRED_SECTIONS = (
    "## 0. 口径纪律",
    "## 1. 数据表清单",
    "## 2. 探针摘要清单",
    "## 3. 冻结读数",
    "## 4. 通道覆盖",
    "## 5. KPI 板",
    "## 6. 负结果登记",
    "## 7. 出处索引",
)

CHANNEL_COLUMNS = (
    "has_dielectric",
    "has_viscosity",
    "has_orbitals",
    "has_redox_label",
    "has_density",
    "has_liquid_window",
)


def _run_builder(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(BUILDER), *args],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def _run_budget(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(BUDGET), *args],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def _make_synthetic_repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "data" / "processed").mkdir(parents=True)
    (root / "probes").mkdir(parents=True)
    (root / "docs" / "framework").mkdir(parents=True)
    (root / "paper").mkdir(parents=True)
    (root / "reports").mkdir(parents=True)

    (root / "data" / "sample.csv").write_text(
        "inchikey,value,flag\nAAA,1.5,true\nBBB,2.5,false\n", encoding="utf-8"
    )
    (root / "data" / "processed" / "four_core_key_registry.csv").write_text(
        "inchikey,"
        + ",".join(CHANNEL_COLUMNS)
        + ",n_core_channels\nAAA,true,false,true,false,false,false,2\n"
        "BBB,false,false,false,false,false,false,0\n",
        encoding="utf-8",
    )
    (root / "probes" / "toy_summary.json").write_text(
        json.dumps({"schema_version": 1, "task_id": "toy", "title": "toy", "score": 0.5}),
        encoding="utf-8",
    )
    (root / "docs" / "framework" / "note.md").write_text("# Note\n\nbody\n", encoding="utf-8")
    (root / "paper" / "draft.md").write_text("# Draft\n\nbody\n", encoding="utf-8")
    (root / "reports" / "week22_project_charter.md").write_text("# Charter\n", encoding="utf-8")
    return root


def test_synthetic_repo_round_trips_and_is_deterministic(tmp_path: Path) -> None:
    root = _make_synthetic_repo(tmp_path)
    first = tmp_path / "one.md"
    second = tmp_path / "two.md"

    assert _run_builder("--root", str(root), "--out", str(first)).returncode == 0
    assert _run_builder("--root", str(root), "--out", str(second)).returncode == 0
    assert first.read_bytes() == second.read_bytes()

    checked = _run_builder("--root", str(root), "--check", "--out", str(first))
    assert checked.returncode == 0, checked.stdout + checked.stderr


def test_check_mode_detects_one_byte_of_drift(tmp_path: Path) -> None:
    root = _make_synthetic_repo(tmp_path)
    out = tmp_path / "doc.md"
    assert _run_builder("--root", str(root), "--out", str(out)).returncode == 0
    assert _run_builder("--root", str(root), "--check", "--out", str(out)).returncode == 0

    (root / "paper" / "draft.md").write_text("# Draft\n\nedited\n", encoding="utf-8")
    drifted = _run_builder("--root", str(root), "--check", "--out", str(out))
    assert drifted.returncode == 1
    assert "DRIFT" in drifted.stdout


def test_delivered_document_carries_the_required_sections() -> None:
    assert DELIVERED.exists(), DELIVERED
    text = DELIVERED.read_text(encoding="utf-8")
    for section in REQUIRED_SECTIONS:
        assert section in text, section
    for reading in FROZEN_READINGS:
        assert reading in text, reading

    tables = re.findall(r"^\| --- ", text, flags=re.MULTILINE)
    assert len(tables) >= 12, len(tables)

    # the six coverage channels and the measured KPI board must be quoted verbatim
    for column in CHANNEL_COLUMNS:
        assert column in text
    assert "0.8947205768486257" in text
    assert "0.7737616891926036" in text
    assert "probes/artifacts/w20_ranking_key_v1_candidates.csv" in text


def test_the_generator_round_trips_the_live_repository(tmp_path: Path) -> None:
    """The document must be rebuildable byte-for-byte from the current tree.

    The repository can be edited by sibling lanes while this runs, so a bounded
    retry keeps the guard honest without turning a concurrent write into a
    spurious failure.
    """
    out = tmp_path / "unified.md"
    last = None
    for _ in range(3):
        built = _run_builder("--out", str(out))
        assert built.returncode == 0, built.stdout + built.stderr
        last = _run_builder("--check", "--out", str(out))
        if last.returncode == 0:
            return
    raise AssertionError("--check never converged: " + (last.stdout + last.stderr if last else ""))


def test_broad_pool_budget_is_pre_registered_and_pinned() -> None:
    prereg = json.loads(BUDGET_PREREG.read_text(encoding="utf-8"))
    assert prereg["prereg_status"] == "locked_before_run"
    assert prereg["locked_criterion"]["id"] == "criterion_A_cheap_layer_promote"

    summary = json.loads(BUDGET_SUMMARY.read_text(encoding="utf-8"))

    # the locked criterion is the only one the summary is allowed to report
    got = _run_budget("--check")
    assert got.returncode == 0, got.stdout + got.stderr

    funnel = summary["funnel"]
    assert funnel["candidates_total"] == 115756
    assert funnel["criterion_upgrade"] == 0
    assert funnel["filtered_out"] == funnel["candidates_total"]
    assert summary["savings"]["savings_ratio"] == 1.0
    assert summary["savings"]["calls_avoided"] == funnel["candidates_total"]
    assert summary["discipline"]["criterion_swapped_after_run"] is False
    assert summary["input"]["sha256"] == prereg["input"]["sha256"]

    namings = {reading["name"] for reading in summary["readings"]}
    assert {"candidates_total", "criterion_upgrade", "savings_ratio"} <= namings
    for reading in summary["readings"]:
        assert reading["source"], reading