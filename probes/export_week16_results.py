"""Export the Week 16 deliverables (the closeout round: two arms, four debts).

Covers, in one package:

* D8 -- the KPI 15+14 shortlist crossed against this repository's own screen cascade;
* U  -- the Uni-Mol fine-tuning probe specification (specification only);
* F1 -- the online ThermoML viscosity slice check that T1 left registered as
        not-done in Week 15;
* F2 -- the AL Round 4 trace-source repair: traces now come from files git
        tracks, with one declared local-only restricted exception;
* F3 -- the mechanical record behind the identity-layer drawing-difference
        decision, which stays with the author;
* the executable-bit repair for probes/kpi_funnel_cross_run.py.

Week 16 buys no new R2 and fits no model: the D8 cross-run is a rule cascade,
F1 counts online records, F2 repairs a list semantic and F3 reads two tables.
The frozen main scoreboard 0.4091179943351143 is never touched.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from probes.export_results_common import (
    DEFAULT_OUTPUT_ROOT,
    copy_artifacts,
    read_json,
    run_verifiers,
    write_json,
    write_sha256s,
)

WEEK = "week16"

FROZEN_RED_LINES = {
    "data/dielectric_v03.csv": "ff2142936e06e04b329b70f8597574f75349e54ce876e9fff81309e6d35ccce4",
    "probes/l3_stage1_pilot_pool.csv": "b838febbca4d65975d1820ae9275215288968979b78756611cb031eb7c408b18",
    "probes/l3_backvalidation_prereg.json": "77f61a83b82de346292ff055c4f4c52003bccb6bfc98bf11813048abc6f0db98",
    "data/processed/dielectric_observations_v11plus.csv": "159b928f800a55969963da275ed05c30ce8a19cffc48353a9c490eec68a49af9",
    "probes/dielectric_r2_levers_prereg.json": "ab3503c037f05ac398b3c0c59d0e4845943d49fa5a5349fa46b8944f2bc1bdaa",
    "data/viscosity_v01.csv": "12dfa03f34284c93204d1054f75b5a342fd82094da0ca17cee372b4c581c5b26",
}

MAIN_SCOREBOARD = 0.4091179943351143
RANDOM_ROW_LEAK_REFERENCE_R2 = 0.7385332681453336

# The trace-file count the AL Round 4 list carried before the F2 repair.  The
# before/after pair is re-derived from two committed states (the Week 16
# opening commit 85cb059, and the worktree that ships this package) instead of
# being restated, so the arithmetic cannot drift away from the list again.
PRE_REPAIR_LIST_COMMIT = "85cb0590284926f13a11be313c560ec20e885081"
PRE_REPAIR_LIST_PATH = "probes/al_round4_backfill_list_v0.csv"
PRE_REPAIR_RECORDED_FILES = 148

EXEC_BIT_REPAIR_NOTE = (
    "上一版提交把 probes/kpi_funnel_cross_run.py 以索引模式 100644 落库，而它带 shebang，"
    "触发 tests/test_repo_hygiene.py 的 EXE001（有 shebang 无执行位），并使 Week 15 导出器的"
    " verifier 块连带变红。本轮用 git update-index --chmod=+x 把索引模式改为 100755，"
    "文件内容一字未动（digest 保持 c65982fc…c800815）。"
)


README_TEXT = """# Week 16 交付包（余项收口：在线黏度切片、追踪源改版、身份画法裁决）

数据血缘: 规范数据集 data/dielectric_v03.csv **未改动**（digest ff2142936e…35ccce4）；
v1.0 已发布工件与 week11–week15 交付包未被触碰；本轮除三处**语义修补**（F2 追踪源、F3 无数据改动、
执行位修复）外，其余为新增文件。
生成脚本: probes/export_week16_results.py

## 头条（六句话，都不许外推）

1. **本轮不产新 R²**。四条臂没有一条拟合模型：D8 是规则级联、F1 只数在线记录、F2 修清单语义、
   F3 只读两张表。冻结主记分牌 **0.4091179943351143** 未被触碰（`main_scoreboard_touched = false`）。
2. **D8（KPI 15+14 短清单 × 本仓漏斗）**：判据 A 自洽 **0/29 违反**；判据 B **29/29** 出 InChIKey
   （14 行 SMILES→RDKit、15 行 CAS→PubChem）；判据 C 交集 Batt-P30K **13** / 314 键名册 **2** /
   冻结 ε v0.3 **2** / v1.x 观测表 **1**。本仓漏斗 **S0 29,519 → S1 29,519（零剔除）→ S2 22,249 →
   S3 11,709 → S4 登记为缺口不跑**；S3 用的是**导出白名单**（C/N/O 三种）标 `derived_not_declared`，只能当下界读。
3. **U（Uni-Mol 探针规格）**：只定规格，不训练、不下载权重、不建环境；`verify_unimol_probe_spec.py --check`
   **34/34**（退出码在 verification.json 里），测试 **22 passed**；变异测试可红可还原（摘要钉已改为等式断言）。
4. **F1（在线黏度切片核查，清偿 T1 登记的「本轮未做」）**：ThermoML JSON API 全库 **11,923 条记录**；
   `"Viscosity, Pa*s"` **1,690**、`"Kinematic viscosity, m2/s"` **70**（口径＝**记录数**，两切片分页抓全、DOI 唯一）；
   本地 29 个含黏度 XML 的 DOI **29/29 命中**在线并集（**1,743** 条记录），未命中 0；覆盖率只按记录口径给
   **29 / 1,690 = 1.72%**，**在线行数记 `unknown`、行口径不可比**。口径事实：API 的 `pageNum` 是 **0 基**的，
   从 `pageNum=1` 起分页会**永久漏掉最前 100 条**（已写进预注册并由 `FIRST_PAGE_NUM = 0` 固化）。
5. **F2（追踪源改版，采纳 `git ls-files` 正解）**：`local_trace_files` 的候选集改为「**git 跟踪的文件** ∩
   声明 curated 根」，唯一显式例外是本地-only 的 `data/restricted/`（单独计数、命中行继续 `local_trace_restricted = yes`）；
   **被 ignore 的下载缓存不再能冒充项目知识**——本轮真实受害 token（`data/external/g1plus/pubchem/kpi_shortlist_identity/108-32-7.json`）
   已消失，去重 trace 文件 **148 → 77**（**文件口径**消失 **71** ＝ `data/external/` 69 ＋ `data/processed/` 2；**新增 0**；由导出器从 85cb059 那份清单重数，机器可复算）。`decisions_log.md` §27.5 另给 **token 口径** 156 → 83（消失 73、新增 0）——**两个口径不许相减**，也不许拿它们去和上几轮登记的 114 / 128 / 146 相减；新增机读 `trace_scan_census`
   （`tracked_candidates = 98` ＋ `restricted_local_only_candidates = 21` = **119**，含 `path_list_sha256`），
   使「128 → 146」这类漂移从此可归因。**21 行清单只有 `local_trace_files` 一列变化，无 `local_trace` 翻转。**
6. **F3（身份层画法差异：机械取证 + 不改写建议）**：15 条 SMILES 差异 = 立体层假警报 10 ＋ 结构层 5；
   5 条全部 `identity_check = roundtrip_match`、`pubchem_inchikey` 与 `inchikey` **逐字相同**；
   5 条本地串**全部是复制而非撰写**（4 条在**冻结件** `data/dielectric_v03.csv` 内、1 条在 ilthermo 派生表内、
   0 条由身份层自己撰写）；其中 **4 条携带几何派生特征**。建议 **不改写**
   （`recommended_no_rewrite_awaiting_human_confirmation`）：改写不是文本编辑而是**版本化迁移**
   （须重生特征表 + 出新冻结版本）。裁决权归作者，本轮 `no_data_change_made = true`。

## 本轮顺手修掉的一个自带缺陷

上一版提交把 `probes/kpi_funnel_cross_run.py` 以索引模式 **100644** 落库，而它带 shebang，
触发 `tests/test_repo_hygiene.py` 的 EXE001（有 shebang 无执行位），并使 Week 15 导出器的 verifier 块**连带变红**。
本轮用 `git update-index --chmod=+x` 把索引模式改为 **100755**，**文件内容一字未动**
（digest 仍为 c65982fc…c800815）。这是「提交后 CI 才看得见」的一类缺陷，记在此处以免下次重犯。

## Week 15 包里的一个数字漂移，在此一次性解释

Week 15 包的 `README.md` 与 `week15_summary.json` 把 AL Round 4 的「本地痕迹文件数」依次记成
114 → 128 → **146**。那不是三次不同的测量口径，而是**同一个错误口径**在同一张盘上被反复读数：
当时 `local_trace_files` 是「递归扫描 `data/` 下所有文件」的函数，每落一个文件就漂一次。
本轮（F2）把扫描源换成 `git ls-files` ∩ 声明策展根之后，同一张清单的读数稳定为 **77**；
修复前后的逐目录差异由导出器在导出当天从 `85cb059` 那份清单重数出来，写在
`lanes.f2_trace_source_repair.trace_file_census.repair_comparison` 里，**不是抄过来的**。
Week 15 包**不回改**——已落盘的读数按项目纪律逐字保留，漂移在此解释并封存。

## 边界（不许省略）

- 在线 `size` 是**记录（文档）数**，不是数据行数；**在线行数 = `unknown`**，行口径**不可比**，不许用
  记录的 `data_summary` 顶替行数，也不许做任何估计。
- 本地 `data/raw/thermoml/` 是 NIST 全库（11,923 条记录）的**筛选缓存**，不得当作全库；29 个含黏度文件是
  **严格子集不是全集**（在线并集 1,743 条记录）。
- `data/external/thermoml_api/`（38 个文件 / 151,793,252 B）是**原始响应缓存**，被 `.gitignore` 忽略、
  **不随包分发**；干净克隆上 `--check` 退用已提交 summary 的清单，仍然**零网络**复现。
- `local_trace_files` 的唯一例外是 `data/restricted/`：**本机专属、不在干净 clone 内**，标准库口径下**不可复现**，
  故单独计数、绝不假装成版本库内容。
- `random_row` 只作泄漏参照（R² = 0.7385332681453336），**从不进入任何判决**。
- 主记分牌口径隔离照旧：0.4091179943351143（457 行 / 97 化合物）与 v1.0 headline 0.364 不得混用；
  `0.5332` / `0.5454` 只许带池定义引用。
- 受限数据：Reaxys 值未进 `data/`、未进任何池；Schrödinger 受限 **858** 条未被绕取。

## 复现

    .\\.venv\\Scripts\\python.exe probes\\export_week16_results.py --overwrite
    .\\.venv\\Scripts\\python.exe probes\\kpi_funnel_cross_run.py --check
    .\\.venv\\Scripts\\python.exe probes\\verify_unimol_probe_spec.py --check
    .\\.venv\\Scripts\\python.exe probes\\thermoml_viscosity_online_slice.py --check
    .\\.venv\\Scripts\\python.exe probes\\identity_smiles_drawing_decision.py --check
    .\\.venv\\Scripts\\python.exe probes\\al_round4_new_compound_backfill.py
"""


ARTIFACTS = (
    ("reports/decisions_log.md", "decisions_log.md"),
    # D8 -- the KPI 15+14 shortlist crossed with this repository's own cascade.
    ("probes/kpi_funnel_cross_run.py", "kpi_funnel_cross_run.py"),
    ("probes/kpi_funnel_cross_run_prereg.json", "kpi_funnel_cross_run_prereg.json"),
    ("probes/kpi_funnel_cross_run_summary.json", "kpi_funnel_cross_run_summary.json"),
    (
        "data/reference/kpi_shortlist_identity.csv",
        "data/reference/kpi_shortlist_identity.csv",
    ),
    ("reports/kpi_funnel_cross_run.md", "kpi_funnel_cross_run.md"),
    ("tests/test_kpi_funnel_cross_run.py", "test_kpi_funnel_cross_run.py"),
    # U -- the Uni-Mol probe specification (specification only, no model run).
    ("probes/unimol_probe_spec_prereg.json", "unimol_probe_spec_prereg.json"),
    ("probes/verify_unimol_probe_spec.py", "verify_unimol_probe_spec.py"),
    ("reports/unimol_probe_spec.md", "unimol_probe_spec.md"),
    ("tests/test_unimol_probe_spec.py", "test_unimol_probe_spec.py"),
    # F1 -- the online ThermoML viscosity slice check (closes T1's debt).
    (
        "probes/thermoml_viscosity_online_slice_prereg.json",
        "thermoml_viscosity_online_slice_prereg.json",
    ),
    ("probes/thermoml_viscosity_online_slice.py", "thermoml_viscosity_online_slice.py"),
    (
        "probes/thermoml_viscosity_online_slice_summary.json",
        "thermoml_viscosity_online_slice_summary.json",
    ),
    (
        "reports/thermoml_viscosity_online_slice.md",
        "thermoml_viscosity_online_slice.md",
    ),
    (
        "tests/test_thermoml_viscosity_online_slice.py",
        "test_thermoml_viscosity_online_slice.py",
    ),
    # F2 -- the trace-source repair, and the Week 15 exporter that carries it.
    ("probes/al_round4_new_compound_backfill.py", "al_round4_new_compound_backfill.py"),
    ("probes/al_round4_backfill_list_v0.csv", "al_round4_backfill_list_v0.csv"),
    (
        "probes/al_round4_new_compound_backfill_summary.json",
        "al_round4_new_compound_backfill_summary.json",
    ),
    ("reports/al_round4_new_compound_backfill.md", "al_round4_new_compound_backfill.md"),
    (
        "tests/test_al_round4_new_compound_backfill.py",
        "test_al_round4_new_compound_backfill.py",
    ),
    ("probes/export_week15_results.py", "export_week15_results.py"),
    ("tests/test_export_week15_results.py", "test_export_week15_results.py"),
    # F3 -- the mechanical record behind the identity-layer drawing decision.
    (
        "probes/identity_smiles_drawing_decision.py",
        "identity_smiles_drawing_decision.py",
    ),
    (
        "probes/identity_smiles_drawing_decision_summary.json",
        "identity_smiles_drawing_decision_summary.json",
    ),
    (
        "reports/identity_smiles_drawing_decision.md",
        "identity_smiles_drawing_decision.md",
    ),
    (
        "tests/test_identity_smiles_drawing_decision.py",
        "test_identity_smiles_drawing_decision.py",
    ),
    # Scaffolding touched this round.
    (".gitignore", ".gitignore"),
    ("tests/fixtures/manual_appendix_j_snapshot.md", "manual_appendix_j_snapshot.md"),
)

VERIFIERS = (
    "scripts/verify_dielectric_v03.py",
    (
        "-m pytest tests/test_thermoml_viscosity_online_slice.py "
        "tests/test_identity_smiles_drawing_decision.py tests/test_kpi_funnel_cross_run.py "
        "tests/test_unimol_probe_spec.py tests/test_al_round4_new_compound_backfill.py "
        "tests/test_export_week15_results.py tests/test_repo_hygiene.py "
        "tests/test_manual_appendix_reconciliation.py -q -p no:cacheprovider"
    ),
    "probes/kpi_funnel_cross_run.py --check",
    "probes/verify_unimol_probe_spec.py --check",
    "probes/thermoml_viscosity_online_slice.py --check",
    "probes/identity_smiles_drawing_decision.py --check",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _head_commit(source_root: Path) -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=source_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return (completed.stdout or "").strip()


def _worktree_status(source_root: Path) -> tuple[bool, int]:
    """Say whether the worktree was dirty at export time, and by how many paths."""

    completed = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=source_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    paths = [line for line in (completed.stdout or "").splitlines() if line.strip()]
    return bool(paths), len(paths)


def _frozen_red_lines() -> dict[str, dict[str, object]]:
    red_lines: dict[str, dict[str, object]] = {}
    for path, expected in FROZEN_RED_LINES.items():
        measured = _sha256(REPOSITORY_ROOT / path)
        red_lines[path] = {
            "sha256": measured,
            "expected_sha256": expected,
            "intact": measured == expected,
        }
    return red_lines


def _git(source_root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=source_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "git " + " ".join(args) + " failed: " + (completed.stderr or "").strip()
        )
    return completed.stdout or ""


def _trace_paths(rows: list[dict[str, str]]) -> set[str]:
    """The distinct files a list cites as local traces, tier suffix stripped."""

    return {
        entry.split(":")[0]
        for row in rows
        for entry in (row.get("local_trace_files") or "").split(";")
        if entry.strip()
    }


def trace_file_census(source_root: Path) -> dict[str, object]:
    """Re-measure the shipped list, and the list as it stood before the repair.

    The pre-repair side is read out of git (the Week 16 opening commit) rather
    than remembered, so the before/after numbers in the package are two
    measurements of two committed states.  When that commit is not reachable
    (a shallow clone, say) the comparison is registered as unavailable instead of
    being filled in from the constant above.
    """

    list_path = REPOSITORY_ROOT / "probes" / "al_round4_backfill_list_v0.csv"
    with list_path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    now = _trace_paths(rows)
    tally = Counter(row.get("local_trace") for row in rows)
    keys = ("yes", "no", "na")

    comparison: dict[str, object]
    try:
        raw = _git(
            source_root, "show", PRE_REPAIR_LIST_COMMIT + ":" + PRE_REPAIR_LIST_PATH
        )
        before_rows = list(csv.DictReader(io.StringIO(raw.lstrip("\ufeff"))))
        before = _trace_paths(before_rows)
        before_tally = Counter(row.get("local_trace") for row in before_rows)
        by_root = Counter(
            path.split("/")[1]
            for path in (before - now)
            if path.startswith("data/") and path.count("/") > 1
        )
        comparison = {
            "available": True,
            "pre_repair_commit": PRE_REPAIR_LIST_COMMIT,
            "pre_repair_distinct_files": len(before),
            "post_repair_distinct_files": len(now),
            "disappeared": len(before - now),
            "added": len(now - before),
            "disappeared_by_root": dict(sorted(by_root.items())),
            "local_trace_before": {key: before_tally.get(key, 0) for key in keys},
            "local_trace_after": {key: tally.get(key, 0) for key in keys},
            "local_trace_flipped": before_tally != tally,
        }
    except RuntimeError as error:
        comparison = {
            "available": False,
            "reason": str(error),
            "recorded_pre_repair_files": PRE_REPAIR_RECORDED_FILES,
        }

    return {
        "list": "probes/al_round4_backfill_list_v0.csv",
        "rows": len(rows),
        "distinct_local_trace_files": len(now),
        "local_trace": {key: tally.get(key, 0) for key in keys},
        "counting_rule": (
            "distinct files cited across the list's local_trace_files entries, with "
            "the path:tier suffix stripped"
        ),
        "repair_comparison": comparison,
    }

def export_results(*, output_root: Path, overwrite: bool) -> dict:
    week_root = output_root / WEEK
    if week_root.exists() and not overwrite:
        raise FileExistsError(f"{week_root} already exists; pass --overwrite")

    copied = copy_artifacts(REPOSITORY_ROOT, week_root, ARTIFACTS)
    verification = run_verifiers(REPOSITORY_ROOT, VERIFIERS)

    d8 = read_json(REPOSITORY_ROOT / "probes" / "kpi_funnel_cross_run_summary.json")
    spec = read_json(REPOSITORY_ROOT / "probes" / "unimol_probe_spec_prereg.json")
    f1 = read_json(
        REPOSITORY_ROOT / "probes" / "thermoml_viscosity_online_slice_summary.json"
    )
    al4 = read_json(
        REPOSITORY_ROOT / "probes" / "al_round4_new_compound_backfill_summary.json"
    )
    f3 = read_json(
        REPOSITORY_ROOT / "probes" / "identity_smiles_drawing_decision_summary.json"
    )

    frozen = _frozen_red_lines()
    trace_census = trace_file_census(REPOSITORY_ROOT)
    artifacts_commit = _head_commit(REPOSITORY_ROOT)
    worktree_dirty, worktree_dirty_paths = _worktree_status(REPOSITORY_ROOT)

    funnel_ours = [
        {
            "id": stage["id"],
            "name": stage["name"],
            "survivors": stage["survivors"],
            "excluded_here": stage["excluded_here"],
        }
        for stage in d8["funnel_ours"]
    ]
    c3 = d8["criterion_c_intersection"]
    c1 = d8["criterion_a_self_consistency"]
    c2 = d8["criterion_b_identity"]
    f1_c3 = f1["criterion_c_unit_honesty"]
    f3_gates = {
        name: bool(gate.get("passed")) for name, gate in sorted(f3["gates"].items())
    }

    summary = {
        "week": WEEK,
        # The export-time HEAD.  Kept under its historical name; on its own it is
        # not a coordinate for the shipped files, see provenance_note.
        "head_commit": artifacts_commit,
        "artifacts_commit": artifacts_commit,
        "worktree_dirty": worktree_dirty,
        "worktree_dirty_paths": worktree_dirty_paths,
        "provenance_note": (
            "artifacts_commit is the commit to fetch the shipped artefacts from, but "
            "only when worktree_dirty is false; head_commit is kept under its "
            "historical name and carries the same value. When worktree_dirty is true, "
            "at least one shipped file was copied from an uncommitted working tree, "
            "so no commit on its own identifies the shipped bytes: seal the worktree "
            "into a commit, re-export from that commit and cite it before quoting any "
            "artefact coordinate."
        ),
        "buys_no_new_r2": (
            "Week 16 is a closeout round: D8 is a rule cascade, F1 counts online "
            "records, F2 repairs a list semantic and F3 reads two tables. None of "
            "them fits a model, so the round buys no R2 and claims none."
        ),
        "shots": {
            "main_scoreboard_attempts": 0,
            "models_fitted": 0,
            "r2_reported_anywhere": False,
            "rule": (
                "a round that buys no R2 has nothing to deflate; the discipline is "
                "that it also claims no R2"
            ),
        },
        "main_scoreboard": {
            "value": MAIN_SCOREBOARD,
            "touched": False,
            "note": (
                "the frozen main scoreboard is never read by this round: no lane "
                "fits a model, and no lane may quote 0.4091179943351143 as a gain"
            ),
        },
        "random_row_leak_reference_r2": RANDOM_ROW_LEAK_REFERENCE_R2,
        "lanes": {
            "d8_kpi_funnel_cross_run": {
                "probe": "probes/kpi_funnel_cross_run.py",
                "shortlist_csv": d8["source"]["shortlist_csv"]["path"],
                "shortlist_rows": d8["source"]["shortlist_rows"],
                "shortlist_by_shortlist": d8["source"]["shortlist_by_shortlist"],
                "identity_resolution": {
                    "rows": d8["identity_resolution"]["rows"],
                    "resolved": d8["identity_resolution"]["resolved"],
                    "unresolved": len(d8["identity_resolution"]["unresolved"]),
                    "by_route": d8["identity_resolution"]["by_route"],
                },
                "criterion_a_self_consistency": {
                    "rows_checked": c1["rows_checked"],
                    "rows_with_violations": c1["rows_with_violations"],
                    "n_violations": len(c1["violating_rows"]),
                    "passed": c1["passed"],
                },
                "criterion_b_identity": {
                    "statement": c2["statement"],
                    "resolved": c2["resolved"],
                    "required": c2["required"],
                    "passed": c2["passed"],
                },
                "criterion_c_intersection": {
                    "distinct_inchikeys": c3["distinct_inchikeys"],
                    "vs_batt_p30k": c3["vs_batt_p30k"]["n"],
                    "vs_roster_314": c3["vs_roster_314"]["n"],
                    "vs_epsilon_v03": c3["vs_epsilon_v03"]["n"],
                    "vs_epsilon_v11plus": c3["vs_epsilon_v11plus"]["n"],
                },
                "funnel_ours": funnel_ours,
                "element_whitelist": d8["element_whitelist"],
                "pools": d8["pools"],
                "property_crosscheck": {
                    "available": d8["property_crosscheck"]["available"],
                    "n_compared": d8["property_crosscheck"]["n_compared"],
                    "max_abs_delta_k": d8["property_crosscheck"]["max_abs_delta_k"],
                    "median_abs_delta_k": d8["property_crosscheck"]["median_abs_delta_k"],
                },
                "model_fitting": d8["model_fitting"],
                "forbidden_compliance": d8["forbidden_compliance"],
                "run_telemetry": d8["run_telemetry"],
                "usage_boundary": d8["usage_boundary"],
                "boundary": (
                    "the two pools are different pools: only proportions and rules may "
                    "be compared, never absolute counts, and a proportional difference "
                    "may not be attributed to our cascade alone. S3 uses an element "
                    "white list derived from the 29 rows themselves "
                    "(derived_not_declared), so S3 is a lower bound, and S4 is "
                    "registered as a gap and not run."
                ),
            },
            "u_unimol_probe_spec": {
                "prereg": "probes/unimol_probe_spec_prereg.json",
                "verifier": "probes/verify_unimol_probe_spec.py --check",
                "title": spec["title"],
                "locked_at_utc": spec["locked_at_utc"],
                "status": spec["status"],
                "scope_of_this_round": spec["scope_of_this_round"],
                "kill_line_verbatim_zh": spec["kill_line"]["verbatim_zh"],
                "comparator": spec["kill_line"]["comparator_hybrid_xgboost"],
                "evaluation_protocol": {
                    "splitter": spec["evaluation_protocol"]["splitter"],
                    "group_overlap_assertion": spec["evaluation_protocol"][
                        "group_overlap_assertion"
                    ],
                    "random_row": spec["evaluation_protocol"]["random_row"],
                    "repeated_outer_scheme": spec["evaluation_protocol"][
                        "repeated_outer_scheme"
                    ],
                },
                "conformer_count_conflict": {
                    "registered": spec["conformer_count_conflict"]["registered"],
                    "status": spec["conformer_count_conflict"]["status"],
                    "no_silent_resolution": spec["conformer_count_conflict"][
                        "no_silent_resolution"
                    ],
                },
                "registered_uncertainties": len(spec["registered_uncertainties"]),
                "forbidden_rules": len(spec["forbidden"]),
                "frozen_red_lines_declared": spec["frozen_red_lines"]["count"],
                "self_check": spec["self_check"],
                "boundary": (
                    "this round writes the specification only: no training, no "
                    "fine-tuning, no inference, no weight download and no environment "
                    "is built, so not one number here is a model reading. The "
                    "conformer-count conflict is registered as unresolved and must be "
                    "pinned in the run-time pre-registration before any fit."
                ),
            },
            "f1_online_viscosity_slice": {
                "probe": "probes/thermoml_viscosity_online_slice.py",
                "prereg_sha256": f1["prereg"]["sha256"],
                "prereg_locked_at_utc": f1["prereg"]["locked_at_utc"],
                "api_endpoint": f1["api"]["endpoint"],
                "page_num_base": f1["api"]["page_num_base"],
                "total_records_query_star": f1["dataset"]["total_records"]["size_records"],
                "slice_records": {
                    slice_["id"]: slice_["size_records"]
                    for slice_ in f1["dataset"]["slices"]
                },
                "slice_records_collected": {
                    slice_["id"]: slice_["records_collected"]
                    for slice_ in f1["dataset"]["slices"]
                },
                "criterion_a_online_slice": {
                    "n_violations": f1["criterion_a_online_slice"]["n_violations"],
                    "passed": f1["criterion_a_online_slice"]["passed"],
                },
                "criterion_b_local_subset": {
                    "local_doi_count": f1["criterion_b_local_subset"]["local_doi_count"],
                    "n_present": f1["criterion_b_local_subset"]["n_present"],
                    "n_phrase_only": f1["criterion_b_local_subset"]["n_phrase_only"],
                    "n_misses": f1["criterion_b_local_subset"]["n_misses"],
                    "online_union_dois": f1["criterion_b_local_subset"]["online_union_dois"],
                    "passed": f1["criterion_b_local_subset"]["passed"],
                },
                "criterion_c_unit_honesty": {
                    "size_unit": f1_c3["size_unit"],
                    "size_unit_statement": f1_c3["size_unit_statement"],
                    "online_row_count": f1_c3["online_row_count"],
                    "online_row_count_reason": f1_c3["online_row_count_reason"],
                    "coverage": f1_c3["coverage"],
                    "n_violations": f1_c3["n_violations"],
                    "passed": f1_c3["passed"],
                },
                "local_source": f1["local_source"],
                "requests_spent": f1["run_provenance"]["requests"]["requests_spent"],
                "request_budget": f1["run_provenance"]["requests"]["budget_limit"],
                "bytes_transferred": f1["run_provenance"]["requests"]["bytes_transferred"],
                "cache": f1["run_provenance"]["cache"],
                "run_mode": f1["run_provenance"]["run_mode"],
                "findings": f1["findings"],
                "boundaries": f1["limitations"],
            },
            "f2_trace_source_repair": {
                "probe": "probes/al_round4_new_compound_backfill.py",
                "rule": al4["trace_scan_scope"]["rule"],
                "tracked_files_are_the_rule": al4["trace_scan_scope"][
                    "tracked_files_are_the_rule"
                ],
                "untracked_files_are_excluded": al4["trace_scan_scope"][
                    "untracked_files_are_excluded"
                ],
                "restricted_exception_root": al4["trace_scan_scope"][
                    "restricted_exception_root"
                ],
                "restricted_exception_rule": al4["trace_scan_scope"][
                    "restricted_exception_rule"
                ],
                "trace_scan_census": al4["trace_scan_census"],
                "trace_file_census": trace_census,
                "list_stats": al4["list_stats"],
                "restricted_values_contract": al4["restricted_values_contract"],
                "network_calls": al4["network_calls"],
                "boundary": (
                    "the candidate set is the intersection of git ls-files and the "
                    "declared curated roots, so an ignored download cache can no "
                    "longer be quoted as project knowledge and the list reproduces in "
                    "a clean clone. One declared exception remains: the local-only "
                    "data/restricted/ cross-check mirror is in no clone, so "
                    "trace_scan_census counts it apart and the rows it touches keep "
                    "local_trace_restricted=yes."
                ),
            },
            "f3_identity_drawing_decision": {
                "probe": "probes/identity_smiles_drawing_decision.py",
                "counts": f3["counts"],
                "gates": f3_gates,
                "geometry_derived_feature_census": {
                    "n_keys_with_geometry_derived_features": f3[
                        "geometry_derived_feature_census"
                    ]["n_keys_with_geometry_derived_features"],
                    "keys": f3["geometry_derived_feature_census"][
                        "keys_with_geometry_derived_features"
                    ],
                    "per_key": f3["geometry_derived_feature_census"]["per_key"],
                    "statement": f3["geometry_derived_feature_census"]["statement"],
                },
                "decision": f3["decision"],
                "run_telemetry": f3["run_telemetry"],
                "caveats": f3["caveats"],
                "boundary": (
                    "this is a mechanical record, not a ruling: the five structural "
                    "differences are drawing differences under one and the same "
                    "identifier, every local string is copied rather than authored, "
                    "and four of the five keys carry geometry-derived features, so an "
                    "in-place rewrite would be a versioned migration, not a text edit. "
                    "The decision stays with the author and no data file was written."
                ),
            },
        },
        "exec_bit_repair": {
            "path": "probes/kpi_funnel_cross_run.py",
            "index_mode_before": "100644",
            "index_mode_after": "100755",
            "content_changed": False,
            "note": EXEC_BIT_REPAIR_NOTE,
        },
        "frozen_red_lines": frozen,
        "frozen_red_lines_all_intact": all(entry["intact"] for entry in frozen.values()),
        "pool_definition_caveat": (
            "0.5332 and 0.5454 may only be quoted with their pool definitions "
            "(a 147-compound training pool against a 97-compound fixed scoring pool); "
            "they must never be compared against the v1.0 headline 0.364, which lives "
            "on the frozen 236-compound pool"
        ),
        "verification": verification,
        "verification_passed": bool(verification.get("passed")),
        "artifacts": copied,
    }

    write_json(week_root / "week16_summary.json", summary)
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
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["verification_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
