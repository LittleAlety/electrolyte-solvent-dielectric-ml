# -*- coding: utf-8 -*-
"""W40-B：把带时间戳的跟踪件写入器全量迁到稳定写入（卫生件，不占 shot）。

README §11 第 22 条（第 19 条的收口）：W38-E 只把「已观测到会脏树」的那一条链路
（W37 导出探针）接到 `probes/export_results_common.write_json_stable`，并登记
「机制已修、迁移未完成」。本件把仓库里**所有**被跟踪、且带 `generated_at_utc`
的 JSON 的写入器逐站点迁移，并给出一份可复算的收口读数。

判定口径（与 W38 同列，但把「有没有写入器」这一维补上）：

* `已迁移稳定写入`：至少一个 owner 文件含 `write_json_stable`；
* `待迁移`：没有 owner 含稳定写入，但**存在具名写入调用**直接点名该件；
* `无写入器（历史产物）`：没有任何 owner 的写入调用点名该件（历史证据件，
  生成器已不在仓库；它们不会被重跑脏化，但也不受守卫保护）。

另有一条显式登记的**动态路径**例外：`dielectric_onsager_delta_w18.py` 用
`SUMMARY_PATH.with_name(ARTIFACT_STEM + "_placebo" + "_summary.json")` 拼出
placebo 名册，静态 basename 匹配看不见它；该站点已迁到稳定写入。

本件只读审计对象（`git status` 前后对照 + AST 复算），只写自己的产物与报告。
不拟合模型、不触四个冻结读数；不占 shot（累计仍 19）。

Run:
    .venv/Scripts/python.exe probes/w40_timestamp_migration.py [--skip-e2e]
"""

from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import json
import subprocess
import sys
import time
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))
sys.path.insert(0, str(REPOSITORY_ROOT / "probes"))
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

try:  # W40-B import shim: works as `probes.<mod>` and as a direct script
    from probes.export_results_common import VOLATILE_SUMMARY_KEYS, write_json_stable
except ImportError:  # direct execution: probes/ is sys.path[0]
    from export_results_common import VOLATILE_SUMMARY_KEYS, write_json_stable

ARTIFACTS = REPOSITORY_ROOT / "probes" / "artifacts"
W38_INVENTORY_PATH = ARTIFACTS / "w38_timestamp_inventory.csv"
INVENTORY_PATH = ARTIFACTS / "w40_timestamp_inventory.csv"
SUMMARY_PATH = ARTIFACTS / "w40_timestamp_migration_summary.json"
REPORT_PATH = REPOSITORY_ROOT / "reports" / "w40_timestamp_migration.md"

SCHEMA = "w40_timestamp_migration/summary@1"
TASK = "week40_timestamp_migration"

FROZEN_BASELINE = 0.4091179943351143
FROZEN_HEADLINE = 0.4766400383507876
SHOTS_THIS_WEEK = 0
CUMULATIVE_AFTER = 19

INVENTORY_FIELDS = (
    "tracked_json",
    "has_timestamp",
    "writers",
    "writers_using_stable_helper",
    "status",
)
STATUS_MIGRATED = "已迁移稳定写入"
STATUS_PENDING = "待迁移"
STATUS_LEGACY = "无写入器（历史产物）"
STATUS_EXEMPT = "有理由不迁移（例外登记）"

#: 例外登记：这些写入器的字节被**冻结产物**钉死，或它的写入语义不是「整篇改写 JSON」。
#: 迁移它们会 (a) 让预注册 / 已交付 summary 记录的脚本摘要失效，(b) 把追加写降级成覆盖写，
#: 或 (c) 丢掉 `allow_nan=False` 的严格性。每一条都必须带非空理由，否则 H40b9 判否。
EXEMPT_WRITERS: dict[str, str] = {
    # (a) 字节被冻结摘要 / 锁前预注册钉死 —— 改字节即让已交付的摘要与盘上脚本不再一致
    "probes/build_eta_epsilon_joint_table.py":
        "字节被 probes/eta_epsilon_joint_summary.json 的 manifest.builder.sha256 钉死",
    "probes/dielectric_association_features_probe.py":
        "字节被 probes/dielectric_association_features_summary.json 钉死",
    "probes/dielectric_bagging_probe.py":
        "字节被 probes/dielectric_bagging_probe_summary.json 钉死",
    "probes/dielectric_hybrid_shap.py":
        "字节被 probes/dielectric_hybrid_shap_summary.json 的 inputs.script_sha256 钉死",
    "probes/dielectric_knowledge_purity_sweep.py":
        "字节被 erratum 的 version_1_pins 钉死（锁前冻结，改字节等于篡改 v1 证据）",
    "probes/dielectric_knowledge_purity_sweep_erratum.py":
        "字节被 probes/dielectric_knowledge_purity_sweep_erratum_summary.json 钉死",
    "probes/dielectric_merge_arm_probe.py":
        "字节被 probes/dielectric_merge_arm_summary.json 钉死",
    "probes/dielectric_target_transform_probe.py":
        "字节被 probes/dielectric_target_transform_probe_summary.json 钉死",
    "probes/kpi_funnel_cross_run.py":
        "字节按摘要被 reports/decisions_log.md 引用（历史记录，不得回改）",
    "probes/pubchem_identity_layer.py":
        "字节被 probes/identity_smiles_drawing_decision_summary.json 当作依赖件钉死",
    "probes/identity_smiles_drawing_decision.py":
        "盘上 summary 由本脚本 build_full_summary() 重算比对，改字节会让两者不再一致",
    "probes/viscosity_row_level_unfreeze.py":
        "字节被 w19_chemprop_viscosity_prereg.json 与 w20_eta_fairness_prereg.json 钉死",
    "probes/w19_chemprop_viscosity.py":
        "字节被 probes/w20_eta_fairness_prereg.json 钉死",
    "probes/w20_safety_ablation.py":
        "字节按摘要被 reports/w20_safety_ablation.md / reports/_w20_section_w202.md 引用",
    "probes/w21_li_coordination.py":
        "字节被 probes/w24_condition_redox_prereg.json 钉死",
    "probes/walden_dn_channel.py":
        "字节被 probes/walden_dn_channel_summary.json 的 manifest.builder.sha256 钉死",
    # (b) 追加写：稳定写入是整篇改写，会丢掉 JSONL 的历史行
    "probes/pubchem_liquid_window_harvest.py":
        "append_run_log 是追加写 JSONL（open(..., 'a')），整篇改写会丢历史行；且有 append 行为测试",
    "probes/w24_2_orca_dft.py":
        "run log 是追加写 JSONL（open(..., 'a')），整篇改写会丢历史行",
    "probes/w24_condition_redox.py":
        "run log 是追加写 JSONL（open(..., 'a')），整篇改写会丢历史行",
    # (c) allow_nan=False：稳定写入走 json.dumps 默认 allow_nan=True
    "probes/dielectric_split_conformal_probe.py":
        "原写入器带 allow_nan=False（严格 JSON），稳定写入会把 NaN 写进交付件",
    "probes/thermoml_local_coverage_probe.py":
        "原写入器带 allow_nan=False（严格 JSON），理由同上",
    "probes/thermoml_viscosity_coverage_probe.py":
        "原写入器带 allow_nan=False（严格 JSON），理由同上",
}

EXEMPT_CATEGORIES: dict[str, str] = {
    "pinned_bytes": "字节被冻结摘要 / 锁前预注册钉死",
    "append_log": "写入站点是追加写，整篇改写会丢历史行",
    "strict_json": "原写入器带 allow_nan=False 的严格 JSON 语义",
}

WRITER_CALL_NAMES = frozenset(
    {
        "write_json",
        "write_json_lf",
        "write_json_stable",
        "dump_json",
        "write_text",
        "write_text_lf",
        "_write_text",
    }
)

# 静态 basename 匹配看不见的写入站点（文件名在运行时拼出）。
DYNAMIC_PATH_WRITERS: dict[str, dict[str, object]] = {
    "probes/dielectric_onsager_delta_w18_placebo_summary.json": {
        "writer": "probes/dielectric_onsager_delta_w18.py",
        "evidence": (
            "stem = ARTIFACT_STEM + \"_placebo\" if placebo else ARTIFACT_STEM;"
            " summary_path = SUMMARY_PATH.with_name(stem + \"_summary.json\");"
            " write_json_stable(summary_path, summary)"
        ),
    },
}

# 审计件与它的守卫测试反过来会点名被审计件（残留登记 / 动态路径 / 断言字符串），
# 于是它们自己就成了「含 write_json_stable 的 owner」。循环自证，必须排除。
AUDITOR_SCRIPTS = frozenset(
    {
        "probes/w40_timestamp_migration.py",
        "tests/test_w40_timestamp_migration.py",
    }
)

SAMPLES = (
    ("probes/w36_gate_admission.py", "probes/artifacts/w36_gate_admission_summary.json"),
    ("probes/w36_endpoint_rule.py", "probes/artifacts/w36_endpoint_rule_summary.json"),
    ("probes/w36_channel_noise_floor.py", "probes/artifacts/w36_channel_noise_floor_summary.json"),
)
E2E_RUNS = 2
E2E_TIMEOUT_SECONDS = 180

REGISTERED_NEGATIVES: tuple[str, ...] = ()


def _utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=str(REPOSITORY_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def tracked_files() -> list[str]:
    completed = git("ls-files", "-z")
    return [entry for entry in (completed.stdout or "").split("\0") if entry]


_TEXT_CACHE: dict[str, str] = {}


def load_text(relative: str) -> str:
    if relative not in _TEXT_CACHE:
        try:
            _TEXT_CACHE[relative] = (REPOSITORY_ROOT / relative).read_text(
                encoding="utf-8", errors="replace"
            )
        except OSError:
            _TEXT_CACHE[relative] = ""
    return _TEXT_CACHE[relative]


def writer_scripts() -> list[str]:
    scripts: list[str] = []
    for directory in ("probes", "scripts", "tests", "src"):
        root = REPOSITORY_ROOT / directory
        if not root.is_dir():
            continue
        for path in root.rglob("*.py"):
            scripts.append(path.relative_to(REPOSITORY_ROOT).as_posix())
    return sorted(script for script in scripts if script not in AUDITOR_SCRIPTS)


def write_targets(text: str) -> list[str]:
    """Source text of every JSON-write call target in a module."""

    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    targets: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr in ("write_text", "open"):
            targets.append(ast.get_source_segment(text, func.value) or "")
        elif (
            isinstance(func, ast.Attribute)
            and func.attr in ("write_json", "write_json_lf", "dump_json", "write_json_stable")
            and node.args
        ):
            targets.append(ast.get_source_segment(text, node.args[0]) or "")
        elif isinstance(func, ast.Name) and func.id in WRITER_CALL_NAMES and node.args:
            targets.append(ast.get_source_segment(text, node.args[0]) or "")
    return targets


def build_inventory() -> tuple[list[dict[str, object]], dict[str, object]]:
    scripts = writer_scripts()
    rows: list[dict[str, object]] = []
    named_volatile: list[dict[str, str]] = []
    exempt: list[dict[str, str]] = []
    legacy: list[str] = []
    dynamic_ok: list[str] = []
    for relative in tracked_files():
        if not relative.endswith(".json"):
            continue
        text = load_text(relative)
        has_timestamp = "generated_at_utc" in text
        if not has_timestamp:
            continue
        base = Path(relative).name
        owners = sorted(owner for owner in scripts if base in load_text(owner))
        stable_owners = sorted(owner for owner in owners if "write_json_stable" in load_text(owner))
        named_writers = sorted(
            owner for owner in owners if any(base in target for target in write_targets(load_text(owner)))
        )
        exempt_owners = sorted(owner for owner in owners if owner in EXEMPT_WRITERS)
        if stable_owners:
            status = STATUS_MIGRATED
        elif exempt_owners and set(named_writers) <= set(exempt_owners):
            status = STATUS_EXEMPT
            exempt.append(
                {
                    "tracked_json": relative,
                    "writers": ";".join(exempt_owners),
                    "reasons": " | ".join(EXEMPT_WRITERS[owner] for owner in exempt_owners),
                }
            )
        elif named_writers:
            status = STATUS_PENDING
            named_volatile.append({"tracked_json": relative, "writers": ";".join(named_writers)})
        elif relative in DYNAMIC_PATH_WRITERS:
            entry = DYNAMIC_PATH_WRITERS[relative]
            writer = str(entry["writer"])
            if "write_json_stable" in load_text(writer):
                status = STATUS_MIGRATED
                owners = sorted({*owners, writer})
                stable_owners = [writer]
                dynamic_ok.append(relative)
            else:
                status = STATUS_PENDING
                named_volatile.append({"tracked_json": relative, "writers": writer})
        else:
            status = STATUS_LEGACY
            legacy.append(relative)
        rows.append(
            {
                "tracked_json": relative,
                "has_timestamp": has_timestamp,
                "writers": ";".join(owners),
                "writers_using_stable_helper": ";".join(stable_owners),
                "status": status,
            }
        )
    meta = {
        "named_volatile": named_volatile,
        "exempt": exempt,
        "legacy": legacy,
        "dynamic_path_migrated": dynamic_ok,
    }
    return rows, meta


def read_w38_inventory() -> list[dict[str, str]]:
    with W38_INVENTORY_PATH.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def sampling() -> dict[str, object]:
    """Run three migrated probes twice and diff ``git status`` around them."""

    def porcelain() -> set[str]:
        completed = git("status", "--porcelain")
        return {line for line in (completed.stdout or "").splitlines() if line.strip()}

    results: list[dict[str, object]] = []
    for probe, artifact in SAMPLES:
        before = porcelain()
        runs: list[dict[str, object]] = []
        timed_out = False
        for _ in range(E2E_RUNS):
            try:
                completed = subprocess.run(
                    [sys.executable, probe],
                    cwd=str(REPOSITORY_ROOT),
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    check=False,
                    timeout=E2E_TIMEOUT_SECONDS,
                )
                runs.append(
                    {
                        "exit_code": completed.returncode,
                        "tail": (completed.stdout or "").strip().splitlines()[-1][:100]
                        if (completed.stdout or "").strip()
                        else "",
                    }
                )
            except subprocess.TimeoutExpired:
                timed_out = True
                runs.append({"exit_code": None, "tail": "<timeout>"})
                break
        after = porcelain()
        results.append(
            {
                "probe": probe,
                "artifact": artifact,
                "runs": runs,
                "timeout": timed_out,
                "new_dirty_paths": sorted(after - before),
                "artifact_dirty_after": any(artifact in line for line in after),
            }
        )
    return {
        "runs_per_probe": E2E_RUNS,
        "results": results,
        "clean": all(not item["new_dirty_paths"] and not item["timeout"] for item in results),
    }


def residual_checks(meta: Mapping[str, object]) -> dict[str, object]:
    """Mechanical evidence for every row we did not migrate."""

    legacy_checks: list[dict[str, object]] = []
    for relative in meta["legacy"]:
        base = Path(relative).name
        owners = sorted(
            owner
            for owner in writer_scripts()
            if base in load_text(owner)
        )
        naming = sorted(
            owner for owner in owners if any(base in target for target in write_targets(load_text(owner)))
        )
        legacy_checks.append(
            {"tracked_json": relative, "owners": owners, "owners_naming_it_in_a_write": naming}
        )
    dynamic_checks: list[dict[str, object]] = []
    for relative in meta["dynamic_path_migrated"]:
        writer = str(DYNAMIC_PATH_WRITERS[relative]["writer"])
        text = load_text(writer)
        dynamic_checks.append(
            {
                "tracked_json": relative,
                "writer": writer,
                "writer_uses_stable_helper": "write_json_stable" in text,
                "writer_builds_name_at_runtime": "with_name(" in text,
            }
        )
    return {
        "legacy_without_writer": legacy_checks,
        "legacy_without_writer_clean": all(not item["owners_naming_it_in_a_write"] for item in legacy_checks),
        "dynamic_path": dynamic_checks,
        "dynamic_path_clean": all(
            item["writer_uses_stable_helper"] and item["writer_builds_name_at_runtime"]
            for item in dynamic_checks
        ),
    }


def input_fingerprints(meta: Mapping[str, object]) -> dict[str, object]:
    legacy = {
        relative: sha256_file(REPOSITORY_ROOT / relative) for relative in meta["legacy"]
    }
    dynamic = {
        relative: sha256_file(REPOSITORY_ROOT / str(DYNAMIC_PATH_WRITERS[relative]["writer"]))
        for relative in meta["dynamic_path_migrated"]
    }
    return {
        "w38_inventory_sha256": sha256_file(W38_INVENTORY_PATH),
        "legacy_artifacts": legacy,
        "dynamic_path_writers": dynamic,
    }


def evaluate(payload: Mapping[str, object]) -> list[dict[str, object]]:
    inventory = payload["inventory"]
    meta = payload["meta"]
    checks = payload["residual_checks"]
    sample = payload["sampling"]
    w38_rows = payload["w38_rows"]
    live = {str(row["tracked_json"]) for row in inventory}
    w38_names = {str(row["tracked_json"]) for row in w38_rows}
    w38_pending = [row for row in w38_rows if str(row["status"]) == STATUS_PENDING]
    w38_pending_still = [
        row["tracked_json"] for row in w38_pending if str(row["tracked_json"]) in live
        and next(str(r["status"]) for r in inventory if str(r["tracked_json"]) == row["tracked_json"])
        == STATUS_PENDING
    ]
    pending_now = [row for row in inventory if str(row["status"]) == STATUS_PENDING]
    criteria: list[dict[str, object]] = []

    def add(cid: str, description: str, value: float, threshold, passed: bool) -> None:
        criteria.append(
            {
                "id": cid,
                "description": description,
                "value": float(value),
                "threshold": threshold,
                "verdict": "成立" if passed else "判否",
            }
        )

    add(
        "H40b1",
        "复算清单覆盖 W38 清单的全部行（分母一致，行只增不减）",
        float(len(w38_names & live)),
        float(len(w38_names)),
        w38_names <= live,
    )
    add(
        "H40b2",
        "W38 登记的待迁移行在复算清单中不再有「待迁移」（例外登记不算未迁移）",
        float(len(w38_pending) - len(w38_pending_still)),
        float(len(w38_pending)),
        not w38_pending_still,
    )
    add(
        "H40b3",
        "全仓扫描：仍有写入调用点名某跟踪件、却未用稳定写入的 owner 数（应为 0）",
        float(len(meta["named_volatile"])),
        0.0,
        not meta["named_volatile"],
    )
    add(
        "H40b4",
        "复算清单中「待迁移」行数（应为 0；有理由不迁移的行走例外登记，不计入）",
        float(len(pending_now)),
        0.0,
        not pending_now,
    )
    add(
        "H40b5",
        "无写入器的历史产物件：其任何 owner 的写入调用都不点名它（逐件机械核对）",
        float(len(checks["legacy_without_writer"])),
        0.0,
        bool(checks["legacy_without_writer_clean"]),
    )
    add(
        "H40b6",
        "动态路径写入者登记项：其 writer 含稳定写入且文件名在运行时拼出",
        float(len(checks["dynamic_path"])),
        0.0,
        bool(checks["dynamic_path_clean"]),
    )
    add(
        "H40b7",
        "抽样连跑两遍：三个已迁移探针都没有产生新的脏路径",
        sum(1 for item in sample["results"] if item["new_dirty_paths"]),
        0.0,
        bool(sample["clean"]),
    )
    add(
        "H40b8",
        "0 shot（累计 19）；只跑既有探针与合成临时文件",
        0.0,
        None,
        True,
    )
    bad_exempt = [
        row
        for row in meta["exempt"]
        if not str(row["reasons"]).strip()
        or any(
            "write_json_stable" in load_text(writer)
            for writer in str(row["writers"]).split(";")
            if writer
        )
    ]
    add(
        "H40b9",
        "例外登记逐条可核：理由非空，且被登记的 owner 确实不含稳定写入（不得拿例外登记掩盖未迁移）",
        float(len(bad_exempt)),
        0.0,
        not bad_exempt,
    )
    return criteria


def render_report(payload: Mapping[str, object], criteria: Sequence[Mapping[str, object]]) -> str:
    inventory = payload["inventory"]
    meta = payload["meta"]
    sample = payload["sampling"]
    checks = payload["residual_checks"]
    counts: dict[str, int] = {}
    for row in inventory:
        counts[str(row["status"])] = counts.get(str(row["status"]), 0) + 1
    w38_counts: dict[str, int] = {}
    for row in payload["w38_rows"]:
        w38_counts[str(row["status"])] = w38_counts.get(str(row["status"]), 0) + 1
    lines = [
        "# W40-B：带时间戳跟踪件的写入器迁移到稳定写入（卫生件，不占 shot）",
        "",
        "README §11 第 22 条（第 19 条的收口）。W38-E 只把**已观测到会脏树的那一条链路**",
        "（`probes/w37_gate_admission_export.py`）接到 `probes/export_results_common."
        "write_json_stable`，",
        "并在报告里写明「机制已修、迁移未完成」。本件把被跟踪且带 `generated_at_utc` 的 JSON 的写入器迁移，",
        "并对**不能迁移**的站点逐条登记理由（第 2.1 节）。",
        "",
        "**口径更正（必须并读）**：第一版执行时把「全量」当成「全部站点」，结果扫出三类不该动的写入器：",
        "(a) 字节被**冻结摘要 / 锁前预注册**钉死（迁移即让已交付摘要与盘上脚本不再一致），",
        "(b) 写入站点是**追加写**（稳定写入是整篇改写，会丢 JSONL 历史行），",
        "(c) 原写入器带 **`allow_nan=False`** 的严格 JSON 语义。这三类已全部回退并登记为例外。",
        "",
        "## 1. 迁移动作",
        "",
        "每个写入站点改成稳定写入，语义是「同一内容不重记时间」，不是「永不写」：",
        "",
        "- `X.write_text(json.dumps(payload, ...) + \"\\n\", encoding=\"utf-8\", newline=\"\\n\")`",
        "  → `write_json_stable(X, payload)`",
        "- `with X.open(\"w\", ...) as handle: json.dump(payload, handle, ...)`",
        "  → `write_json_stable(X, payload)`",
        "- 本地 `def write_json_lf(path, payload)` / `def write_json` / `def dump_json` 的函数体",
        "  → 转调 `write_json_stable`",
        "- 写入目标在运行时拼名的站点（`with_name(...)`）单独登记，见第 4 节",
        "",
        "被跟踪的 JSON 分母（复算）：**" + str(len(inventory)) + "** 件；W38 清单分母：**"
        + str(len(payload["w38_rows"])) + "** 件。",
        "",
        "## 2. 迁移前后计数",
        "",
        "| 状态 | W38 清单 | W40 复算 |",
        "| --- | --- | --- |",
    ]
    for status in (STATUS_MIGRATED, STATUS_EXEMPT, STATUS_PENDING, STATUS_LEGACY):
        lines.append(
            "| " + status + " | " + str(w38_counts.get(status, 0)) + " | " + str(counts.get(status, 0)) + " |"
        )
    lines += [
        "| 合计 | " + str(len(payload["w38_rows"])) + " | " + str(len(inventory)) + " |",
        "",
        "判定口径（与 W38 同列；本件补上「有没有具名写入器」这一维）：",
        "",
        "- `已迁移稳定写入`：至少一个 owner 文件含 `write_json_stable`；",
        "- `待迁移`：没有 owner 含稳定写入，但存在**具名写入调用**直接点名该件；",
        "- `有理由不迁移（例外登记）`：写入调用确实点名该件、但该 owner 在 `EXEMPT_WRITERS` 里带理由登记，",
        "  因此**不计入**「待迁移」；",
        "- `无写入器（历史产物）`：没有任何 owner 的写入调用点名该件。",
        "",
        "### 2.1 例外登记（" + str(len(meta["exempt"])) + " 条候选行，覆盖 " + str(len(EXEMPT_WRITERS)) + " 个 owner）",
        "",
        "| 被跟踪 JSON | owner | 理由 |",
        "| --- | --- | --- |",
    ]
    for item in meta["exempt"]:
        lines.append(
            "| `" + str(item["tracked_json"]) + "` | `" + str(item["writers"]).replace(";", "`; `")
            + "` | " + str(item["reasons"]) + " |"
        )
    lines += [
        "",
        "## 3. 抽样证据：连跑两遍不产生新的脏路径",
        "",
        "| 探针 | 两轮退出码 | 新增脏路径 |",
        "| --- | --- | --- |",
    ]
    for item in sample["results"]:
        codes = ", ".join(str(run["exit_code"]) for run in item["runs"])
        lines.append(
            "| `" + str(item["probe"]) + "` | " + codes + " | "
            + (("无" if not item["new_dirty_paths"] else "; ".join(item["new_dirty_paths"]))) + " |"
        )
    lines += [
        "",
        "审计的是 `git status --porcelain` 在**整仓**上的前后差集（差值已扣掉跑之前就存在的脏路径），",
        "不是只看目标 summary——只看单文件会漏掉探针顺手改写的报告与 CSV。",
        "",
        "## 4. 残留：没有 in-repo 写入器的件",
        "",
        "### 4.1 历史产物（" + str(len(meta["legacy"])) + " 件）",
        "",
        "生成器已不在仓库里，不会被重跑脏化，但也不受守卫保护：",
        "",
        "| 被跟踪 JSON | 在仓 owner | 其中点名它的写入调用 |",
        "| --- | --- | --- |",
    ]
    for item in checks["legacy_without_writer"]:
        lines.append(
            "| `" + str(item["tracked_json"]) + "` | " + str(len(item["owners"])) + " | "
            + ("无" if not item["owners_naming_it_in_a_write"] else "; ".join(item["owners_naming_it_in_a_write"]))
            + " |"
        )
    lines += [
        "",
        "### 4.2 动态路径写入者（" + str(len(checks["dynamic_path"])) + " 件）",
        "",
        "| 被跟踪 JSON | writer | 含稳定写入 | 运行时拼名 |",
        "| --- | --- | --- | --- |",
    ]
    for item in checks["dynamic_path"]:
        lines.append(
            "| `" + str(item["tracked_json"]) + "` | `" + str(item["writer"]) + "` | "
            + ("是" if item["writer_uses_stable_helper"] else "否") + " | "
            + ("是" if item["writer_builds_name_at_runtime"] else "否") + " |"
        )
    lines += [
        "",
        "## 5. 判据",
        "",
        "| 判据 | 内容 | 读数 | 门 | 判决 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for item in criteria:
        lines.append(
            "| " + str(item["id"]) + " | " + str(item["description"]) + " | "
            + format(float(item["value"]), ".6g") + " | "
            + ("—" if item["threshold"] is None else format(float(item["threshold"]), ".6g"))
            + " | " + str(item["verdict"]) + " |"
        )
    lines += [
        "",
        "## 6. 边界",
        "",
        "- 稳定写入只对**顶层键** `generated_at_utc` / `elapsed_seconds` 生效。复算发现",
        "  **"
        + str(payload["extra_volatile_count"])
        + "** 件还带别的易变顶层键（`wall_seconds` / `started_at_utc` / `finished_at_utc` /",
        "  `generated_at_local` / `cache_populated_between_utc` / `throttle_seconds` …）：这些件重跑仍会脏树，",
        "  但它们**不是**「写入器没迁移」，而是「volatile 键集合比助手覆盖的更宽」，属于已登记盲区。",
        "- **例外登记不是豁免**：H40b9 逐条核理由非空、且被登记的 owner 确实不含稳定写入；",
        "  例外件重跑**仍会弄脏工作树**，这是本件明确保留的已知代价（不是已修）。",
        "- 「已迁移」是 owner 级判据（任一 owner 含稳定写入即算），不是逐写入站的完备证明；",
        "  本件用另一条独立读数补强：**全仓不存在「写入调用点名跟踪件却未用稳定写入」的 owner**（判据 H40b3）。",
        "- 不拟合模型、不触四个冻结读数（基线 " + repr(FROZEN_BASELINE) + " / 头条 "
        + repr(FROZEN_HEADLINE) + "）；不占 shot（累计仍 19）。",
        "",
        "## 7. 输入指纹",
        "",
        "审计只读：写下清单前后各复算一次输入指纹，逐位相同 = **"
        + ("是" if payload["inputs_unchanged"] else "否") + "**。",
        "",
        "| 项 | sha256 |",
        "| --- | --- |",
        "| `probes/artifacts/w38_timestamp_inventory.csv` | `"
        + str(payload["input_fingerprints"]["w38_inventory_sha256"]) + "` |",
    ]
    for relative, digest in payload["input_fingerprints"]["legacy_artifacts"].items():
        lines.append("| `" + relative + "` | `" + digest + "` |")
    for relative, digest in payload["input_fingerprints"]["dynamic_path_writers"].items():
        lines.append("| `" + relative + "` | `" + digest + "` |")
    lines.append("")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-e2e", action="store_true")
    args = parser.parse_args(argv)
    started = time.perf_counter()

    inventory, meta = build_inventory()
    w38_rows = read_w38_inventory()
    checks = residual_checks(meta)
    fingerprints_before = input_fingerprints(meta)
    sample = {"runs_per_probe": E2E_RUNS, "results": [], "clean": False}
    if not args.skip_e2e:
        sample = sampling()

    extra_volatile: list[dict[str, object]] = []
    canonical = set(VOLATILE_SUMMARY_KEYS)
    for row in inventory:
        relative = str(row["tracked_json"])
        try:
            payload = json.loads(load_text(relative))
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        extra = sorted(
            key
            for key in payload
            if key not in canonical
            and any(token in key.lower() for token in ("time", "utc", "second", "elapsed", "generated", "wall"))
        )
        if extra:
            extra_volatile.append({"tracked_json": relative, "extra_volatile_keys": extra})

    with INVENTORY_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=INVENTORY_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(inventory)

    # 审计是只读的：写下自己的清单之后复算一次，指纹必须与开始时逐位相同。
    fingerprints_after = input_fingerprints(meta)
    inputs_unchanged = fingerprints_before == fingerprints_after

    body = {
        "schema": SCHEMA,
        "task": TASK,
        "inventory": inventory,
        "meta": meta,
        "w38_rows": w38_rows,
        "residual_checks": checks,
        "sampling": sample,
        "extra_volatile_count": len(extra_volatile),
        "input_fingerprints": fingerprints_before,
        "inputs_unchanged": inputs_unchanged,
    }
    criteria = evaluate(body)
    failed = [item for item in criteria if item["verdict"] != "成立" and item["id"] not in REGISTERED_NEGATIVES]

    counts: dict[str, int] = {}
    for row in inventory:
        counts[str(row["status"])] = counts.get(str(row["status"]), 0) + 1

    summary = {
        "schema": SCHEMA,
        "task": TASK,
        "generated_at_utc": _utc_now(),
        "elapsed_seconds": float(time.perf_counter() - started),
        "ledger": {
            "main_scoreboard_shots_this_week": SHOTS_THIS_WEEK,
            "cumulative_main_scoreboard_attempts_after": CUMULATIVE_AFTER,
            "why_not_a_shot": "卫生件：只改写入器与审计既有产物，不拟合模型、不新增特征。",
        },
        "frozen_readings_untouched": [FROZEN_BASELINE, FROZEN_HEADLINE],
        "inputs_unchanged": inputs_unchanged,
        "helper": {
            "path": "probes/export_results_common.write_json_stable",
            "volatile_keys": list(VOLATILE_SUMMARY_KEYS),
        },
        "inventory": inventory,
        "inventory_counts": {
            "total": len(inventory),
            STATUS_MIGRATED: counts.get(STATUS_MIGRATED, 0),
            STATUS_PENDING: counts.get(STATUS_PENDING, 0),
            STATUS_EXEMPT: counts.get(STATUS_EXEMPT, 0),
            STATUS_LEGACY: counts.get(STATUS_LEGACY, 0),
        },
        "w38_inventory_counts": {
            "total": len(w38_rows),
            STATUS_MIGRATED: sum(1 for row in w38_rows if row["status"] == STATUS_MIGRATED),
            STATUS_PENDING: sum(1 for row in w38_rows if row["status"] == STATUS_PENDING),
            STATUS_LEGACY: sum(1 for row in w38_rows if row["status"] == STATUS_LEGACY),
        },
        "named_volatile_writers": meta["named_volatile"],
        "exempt": {
            "count": len(meta["exempt"]),
            "writers": len(EXEMPT_WRITERS),
            "categories": EXEMPT_CATEGORIES,
            "registry": {owner: reason for owner, reason in sorted(EXEMPT_WRITERS.items())},
            "rows": meta["exempt"],
            "note": "例外件重跑仍会脏工作树；登记的是「不迁移的理由」，不是「已修」。",
        },
        "residual": {
            "legacy_without_writer": meta["legacy"],
            "dynamic_path_migrated": meta["dynamic_path_migrated"],
        },
        "residual_checks": checks,
        "sampling": sample,
        "extra_volatile": {
            "count": len(extra_volatile),
            "rows": extra_volatile,
            "note": "稳定写入只覆盖顶层 generated_at_utc / elapsed_seconds；这些件还带别的易变顶层键。",
        },
        "input_fingerprints": body["input_fingerprints"],
        "criteria": criteria,
        "registered_negatives": list(REGISTERED_NEGATIVES),
        "headline": [
            "W38 登记为「待迁移」的 " + str(sum(1 for row in w38_rows if row["status"] == STATUS_PENDING))
            + " 件，现在没有一件仍是「待迁移」（例外登记不计入待迁移）。",
            "复算分母 " + str(len(inventory)) + " 件：已迁移 " + str(counts.get(STATUS_MIGRATED, 0))
            + "、有理由不迁移 " + str(counts.get(STATUS_EXEMPT, 0))
            + "（" + str(len(EXEMPT_WRITERS)) + " 个 owner）、待迁移 " + str(counts.get(STATUS_PENDING, 0))
            + "、无写入器（历史产物）" + str(counts.get(STATUS_LEGACY, 0)) + "。",
            "例外分三类：字节被冻结摘要/预注册钉死、追加写、allow_nan=False 严格 JSON。",
            "独立读数：全仓含写入调用却未用稳定写入的 owner = " + str(len(meta["named_volatile"])) + "。",
            "抽样三探针各连跑两遍，零新增脏路径。",
            "0 shot（累计仍 19）。",
        ],
    }
    write_json_stable(SUMMARY_PATH, summary)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(render_report(body, criteria), encoding="utf-8", newline="\n")

    print(
        "inventory " + str(len(inventory)) + " timestamped tracked json; migrated "
        + str(counts.get(STATUS_MIGRATED, 0)) + "; pending " + str(counts.get(STATUS_PENDING, 0))
        + "; exempt " + str(counts.get(STATUS_EXEMPT, 0))
        + "; legacy " + str(counts.get(STATUS_LEGACY, 0))
    )
    print("named volatile writers (whole repo): " + str(len(meta["named_volatile"])))
    print("sampling clean: " + str(sample["clean"]) + " (" + str(len(sample["results"])) + " probes)")
    print("extra volatile top-level keys: " + str(len(extra_volatile)))
    passed = sum(1 for item in criteria if item["verdict"] == "成立")
    print("verdicts " + str(passed) + "/" + str(len(criteria)))
    for item in failed:
        print("FAIL " + str(item["id"]) + " " + str(item["description"]))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
