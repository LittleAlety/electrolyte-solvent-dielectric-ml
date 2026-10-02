"""Build the unified, byte-reproducible data document for the electrolyte-ML repo.

Usage
-----
    python probes/build_unified_data_document.py --out "<path>"
    python probes/build_unified_data_document.py --check --out "<path>"

The document is a *pure function* of the on-disk files it inventories: it embeds
no wall-clock timestamp, so re-running the generator must reproduce the file
byte for byte (``--check`` verifies exactly that and exits non-zero on drift).

Design notes
------------
* Large inputs (the 45 MB ranking-key pool, 80 MB raw viscosity tables, ~1.4 GB
  of cached API JSON) are only ever streamed: hashing reads 1 MiB chunks, CSV
  statistics are counted with a streaming reader, and JSON bodies above
  ``JSON_PARSE_LIMIT_BYTES`` are registered by metadata alone.
* Every listing is sorted by POSIX-style relative path so the byte layout does
  not depend on filesystem enumeration order.
* ``--check`` performs no writes; it rebuilds the document in memory and compares
  the UTF-8 bytes against the file named by ``--out``.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path

SCHEMA_VERSION = 1
GENERATOR = "probes/build_unified_data_document.py"
DOCUMENT_TITLE = "电解质 ML 项目 · 数据统一文档"

JSON_PARSE_LIMIT_BYTES = 4 * 1024 * 1024
HASH_CHUNK_BYTES = 1 << 20
MAX_HEADER_COLS = 20
MAX_HEADER_CELL = 40
MAX_SCALARS_PER_SUMMARY = 25
MAX_SCALAR_TEXT = 60
MAX_NEGATIVE_ROWS = 80
MAX_NEGATIVE_TEXT = 180
MAX_DOC_TITLE = 90

DEFAULT_OUT = Path(r"E:\Claude Code\电解质ML\成果输出\数据统一文档.md")
REPO_ROOT = Path(__file__).resolve().parents[1]

FROZEN_READINGS = (
    ("冻结基线 R2", "0.4091179943351143", "probes/export_week18_results.py::MAIN_SCOREBOARD"),
    ("冻结头条 R2", "0.4766400383507876", "probes/export_week18_results.py::MAIN_SCOREBOARD_HEADLINE_R2"),
    ("W18 跨种子端点 R2（已被 W20-4 超越，保留为历史位）", "0.5861142332208197", "probes/w20_epsilon_second_stage_summary.json"),
    ("W20-4 注册臂跨种子均值 R2", "0.6216672295270079", "probes/w20_epsilon_second_stage_summary.json"),
)

CHANNELS = (
    ("dielectric", "has_dielectric"),
    ("viscosity", "has_viscosity"),
    ("orbitals", "has_orbitals"),
    ("redox", "has_redox_label"),
    ("density", "has_density"),
    ("liquid_window", "has_liquid_window"),
)

FILE_GROUPS = (
    ("data_csv", "data/**/*.csv", "data 目录下的 CSV 数据表"),
    ("data_json", "data/**/*.json", "data 目录下的 JSON 数据件"),
    ("probes_summary", "probes/*_summary.json", "探针摘要（probes 顶层）"),
    ("artifacts_csv", "probes/artifacts/*.csv", "探针产物 CSV"),
    ("docs_framework", "docs/framework/*.md", "框架文档"),
    ("paper_md", "paper/*.md", "论文稿件"),
    ("charters", "reports/week*_project_charter.md", "周立项章"),
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(HASH_CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


def raw_line_count(path: Path) -> int:
    count = 0
    with path.open("rb") as handle:
        for _ in handle:
            count += 1
    return count


def csv_stats(path: Path) -> dict:
    try:
        with path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
            reader = csv.reader(handle)
            try:
                header = next(reader)
            except StopIteration:
                return {"records": 0, "cols": 0, "header": [], "status": "empty_file"}
            records = 0
            for _ in reader:
                records += 1
        return {"records": records, "cols": len(header), "header": header[:MAX_HEADER_COLS], "status": "ok"}
    except (csv.Error, UnicodeError, OSError):
        lines = raw_line_count(path)
        return {"records": max(lines - 1, 0), "cols": None, "header": [], "status": "raw_line_fallback"}


def json_stats(path: Path, size: int) -> dict:
    if size > JSON_PARSE_LIMIT_BYTES:
        return {"records": None, "fields": None, "keys": [], "status": "not_parsed_over_4MiB"}
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            data = json.load(handle)
    except (json.JSONDecodeError, UnicodeError, OSError):
        return {"records": None, "fields": None, "keys": [], "status": "invalid_json"}
    if isinstance(data, list):
        records = len(data)
        keys = list(data[0].keys()) if data and isinstance(data[0], dict) else []
    elif isinstance(data, dict):
        records = 1
        keys = list(data.keys())
    else:
        records = 1
        keys = []
    return {"records": records, "fields": len(keys), "keys": keys[:MAX_HEADER_COLS], "status": "ok"}


def md_cell(value) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ").strip()


def short(text, limit: int) -> str:
    text = str(text)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def collect_scalars(node, prefix: str = "", out=None) -> list:
    if out is None:
        out = []
    if isinstance(node, dict):
        for key in node:
            collect_scalars(node[key], f"{prefix}.{key}" if prefix else str(key), out)
    elif isinstance(node, list):
        for index, item in enumerate(node):
            if isinstance(item, (dict, list)):
                collect_scalars(item, f"{prefix}[{index}]", out)
    elif isinstance(node, bool):
        return out
    elif isinstance(node, (int, float)):
        out.append((prefix, node))
    return out


def rel(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def group_paths(root: Path, pattern: str) -> list:
    return sorted((p for p in root.glob(pattern) if p.is_file()), key=lambda p: p.relative_to(root).as_posix())


def register_data_file(path: Path, root: Path) -> dict:
    size = path.stat().st_size
    suffix = path.suffix.lower()
    row = {"path": rel(path, root), "sha256": sha256_file(path), "bytes": size}
    if suffix == ".csv":
        row.update(csv_stats(path))
    elif suffix == ".json":
        row.update(json_stats(path, size))
    else:
        row.update({"records": None, "cols": None, "header": [], "status": "n/a"})
    return row


def render_data_table(rows: list, kind: str) -> list:
    lines = []
    if kind == "csv":
        lines.append("| 相对路径 | sha256 | bytes | 记录数(不含表头) | 列数 | 表头(前20列) | 状态 |")
        lines.append("| --- | --- | ---: | ---: | ---: | --- | --- |")
        for row in rows:
            header = ", ".join(short(cell, MAX_HEADER_CELL) for cell in row["header"])
            cols = row["cols"] if row["cols"] is not None else "n/a"
            records = row["records"] if row["records"] is not None else "n/a"
            lines.append(
                f"| `{md_cell(row['path'])}` | `{row['sha256']}` | {row['bytes']} | "
                f"{records} | {cols} | {md_cell(header)} | {row['status']} |"
            )
    else:
        lines.append("| 相对路径 | sha256 | bytes | 记录数 | 顶层字段数 | 顶层字段(前20) | 状态 |")
        lines.append("| --- | --- | ---: | ---: | ---: | --- | --- |")
        for row in rows:
            keys = ", ".join(short(key, MAX_HEADER_CELL) for key in row.get("keys", []))
            records = row["records"] if row["records"] is not None else "n/a"
            fields = row.get("fields")
            fields = fields if fields is not None else "n/a"
            lines.append(
                f"| `{md_cell(row['path'])}` | `{row['sha256']}` | {row['bytes']} | "
                f"{records} | {fields} | {md_cell(keys)} | {row['status']} |"
            )
    return lines


def directory_rollup(rows: list) -> list:
    buckets: dict = {}
    for row in rows:
        parent = row["path"].rsplit("/", 1)[0] if "/" in row["path"] else "."
        stats = buckets.setdefault(parent, {"files": 0, "bytes": 0})
        stats["files"] += 1
        stats["bytes"] += row["bytes"]
    lines = ["| 目录 | 文件数 | 合计 bytes |", "| --- | ---: | ---: |"]
    for parent in sorted(buckets):
        stats = buckets[parent]
        lines.append(f"| `{md_cell(parent)}` | {stats['files']} | {stats['bytes']} |")
    return lines


def render_channel_coverage(root: Path) -> tuple:
    registry = root / "data" / "processed" / "four_core_key_registry.csv"
    if not registry.exists():
        return ["- （登记表缺失：`data/processed/four_core_key_registry.csv`）"], {}, 0
    counters = {column: 0 for _, column in CHANNELS}
    core_channel_hist: dict = {}
    total = 0
    with registry.open("r", encoding="utf-8", errors="replace", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            total += 1
            for _, column in CHANNELS:
                if (row.get(column) or "").strip().lower() == "true":
                    counters[column] += 1
            if row.get("n_core_channels"):
                value = row["n_core_channels"].strip()
                core_channel_hist[value] = core_channel_hist.get(value, 0) + 1
    lines = [
        f"- 登记表：`data/processed/four_core_key_registry.csv`（{total} 行）",
        f"- sha256：`{sha256_file(registry)}`",
        "",
        "| 通道 | 判据列 | 命中行数 | 占比 |",
        "| --- | --- | ---: | ---: |",
    ]
    for label, column in CHANNELS:
        hits = counters[column]
        share = hits / total if total else 0.0
        lines.append(f"| {label} | `{column}` | {hits} | {share:.4f} |")
    lines.append("")
    lines.append("`n_core_channels` 分布：")
    lines.append("")
    lines.append("| n_core_channels | 行数 |")
    lines.append("| --- | ---: |")
    for value in sorted(core_channel_hist, key=lambda item: int(item) if item.isdigit() else 99):
        lines.append(f"| {value} | {core_channel_hist[value]} |")
    return lines, counters, total


def render_kpi_board(root: Path) -> list:
    summary_path = root / "probes" / "w20_funnel_kpi_summary.json"
    if not summary_path.exists():
        return ["- （KPI 面板缺失：`probes/w20_funnel_kpi_summary.json`）"]
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    ranking = payload.get("ranking", {})
    pooled = ranking.get("pooled", {})
    top_k = ranking.get("top_k", {})
    coverage = payload.get("coverage_cost", {})
    discipline = payload.get("discipline", {})
    lines = [
        f"- 出处：`probes/w20_funnel_kpi_summary.json`（sha256 `{sha256_file(summary_path)}`）",
        "",
        "| KPI 组 | 指标 | 值 |",
        "| --- | --- | ---: |",
    ]
    for key in ("auc_gt15", "auc_gt30", "spearman", "n_rows"):
        lines.append(f"| ranking.pooled | `{key}` | {pooled.get(key)} |")
    for key in sorted(top_k):
        lines.append(f"| ranking.top_k | `{key}` | {top_k[key]} |")
    for key in sorted(coverage):
        lines.append(f"| coverage_cost | `{key}` | {coverage[key]} |")
    for key in sorted(discipline):
        lines.append(f"| discipline | `{key}` | {discipline[key]} |")
    lines.append(f"| 禁令 | `forbidden_kpis` | {', '.join(payload.get('forbidden_kpis', []))} |")
    lines.append(f"| 禁令理由 | `forbidden_kpi_reason` | {md_cell(payload.get('forbidden_kpi_reason'))} |")
    lines.append(f"| 冻结件未动 | `main_scoreboard_untouched` | {payload.get('main_scoreboard_untouched')} |")
    capping = payload.get("capping_revision", {})
    lines.append(f"| 阶梯封顶 | `capping_revision.status_after` | {capping.get('status_after')} |")
    lines.append(f"| 阶梯封顶理由 | `capping_revision.reason` | {md_cell(capping.get('reason'))} |")
    return lines


def render_probe_summaries(root: Path) -> tuple:
    paths = group_paths(root, "probes/*_summary.json")
    blocks = []
    for path in paths:
        payload = None
        if path.stat().st_size < JSON_PARSE_LIMIT_BYTES:
            try:
                payload = json.loads(path.read_text(encoding="utf-8", errors="replace"))
            except (json.JSONDecodeError, UnicodeError, OSError):
                payload = None
        digest = sha256_file(path)
        if isinstance(payload, dict):
            schema = payload.get("schema_version", "n/a")
            task = payload.get("task_id", payload.get("task", "n/a"))
            title = short(payload.get("title", "n/a"), MAX_DOC_TITLE)
            scalars = collect_scalars(payload)
        else:
            schema, task, title, scalars = "n/a", "n/a", "n/a", []
        blocks.append(f"- `{rel(path, root)}` — sha256 `{digest}` — schema_version={md_cell(schema)} — task=`{md_cell(task)}` — title={md_cell(title)}")
        if scalars:
            for name, value in scalars[:MAX_SCALARS_PER_SUMMARY]:
                blocks.append(f"    - {md_cell(name)} = {short(value, MAX_SCALAR_TEXT)}")
            if len(scalars) > MAX_SCALARS_PER_SUMMARY:
                blocks.append(f"    - …（另有 {len(scalars) - MAX_SCALARS_PER_SUMMARY} 条数值标量未展开）")
        else:
            blocks.append("    - （无递归数值标量）")
    return paths, blocks


def render_negative_results(root: Path) -> tuple:
    per_file = []
    rows = []
    reports_dir = root / "reports"
    if not reports_dir.exists():
        return per_file, rows
    for path in sorted(reports_dir.glob("*.md")):
        hits = []
        text = path.read_text(encoding="utf-8", errors="replace")
        for index, line in enumerate(text.splitlines(), 1):
            lowered = line.lower()
            if "refuted" in lowered or "capped" in lowered:
                hits.append((index, line.strip()))
        if hits:
            per_file.append((rel(path, root), len(hits)))
            rows.extend((rel(path, root), index, text_line) for index, text_line in hits)
    return per_file, rows


def build_document(root: Path) -> str:
    lines = []
    lines.append(f"# {DOCUMENT_TITLE}")
    lines.append("")
    lines.append(f"- **生成器**：`{GENERATOR}`（schema_version = {SCHEMA_VERSION}）")
    lines.append("- **可复算性**：本文档不写入生成时间戳；`--check` 逐字节重算并与盘上文件比对，两次生成的 sha256 必须相同。")
    lines.append("- **路径约定**：全部路径为仓库根相对路径（POSIX 分隔符）；仓库根即本仓库工作树。")
    lines.append(f"- **扫描口径**：{'；'.join(pattern for _, pattern, _ in FILE_GROUPS)}")
    lines.append(f"- **大文件口径**：JSON 超过 {JSON_PARSE_LIMIT_BYTES // (1024 * 1024)} MiB 只登记元数据；CSV 与哈希一律流式处理，不整表载入内存。")
    lines.append("")

    # 0. 口径纪律
    lines.append("## 0. 口径纪律")
    lines.append("")
    lines.append("读任何数字前先看这一节；破坏其中任一条的结论本文档不予收录。")
    lines.append("")
    lines.append("1. **不平均冲突值。** 汇编值与原始值冲突时开冲突单，不取均值、不取「看起来更权威」的那个。")
    lines.append("2. **不把受限源数值写进可分发数据集。** 受限记录只作 `restricted_crosscheck_only` 或聚合陈述。")
    lines.append("3. **不把「同源确认」美化成「独立互证」。** 与数据集引用同一 DOI 的记录只证明抄写正确。")
    lines.append("4. **不把「被挡」写成「查无此值」。** 付费墙/登录墙一律记为 `blocked`，只有真的检索过且为空才记 `no data`。")
    lines.append("5. **有效数字与温度必须随值走。** 每个值记 source_id + 温度 + 位数，尽量回溯到原始测量 DOI。")
    lines.append("6. **否定结果同等收录。** 失败的模型门、被否证的规则、走不通的数据源路径全部保留。")
    lines.append("7. **冻结件零改动。** 冻结四读数逐位不变；预测永不入池当标签；不引任何受限数值。")
    lines.append("")

    # 1. 数据表清单
    lines.append("## 1. 数据表清单")
    lines.append("")
    group_rows = {}
    for label, pattern, _ in FILE_GROUPS:
        group_rows[label] = [register_data_file(path, root) for path in group_paths(root, pattern)]
    lines.append("### 1.1 覆盖概览")
    lines.append("")
    lines.append("| 扫描组 | 匹配式 | 文件数 | 合计 bytes |")
    lines.append("| --- | --- | ---: | ---: |")
    for label, pattern, _ in FILE_GROUPS:
        rows = group_rows[label]
        lines.append(f"| {label} | `{pattern}` | {len(rows)} | {sum(row['bytes'] for row in rows)} |")
    total_files = sum(len(group_rows[label]) for label, _, _ in FILE_GROUPS)
    total_bytes = sum(row["bytes"] for label, _, _ in FILE_GROUPS for row in group_rows[label])
    lines.append(f"| **合计** | — | **{total_files}** | **{total_bytes}** |")
    lines.append("")

    lines.append("### 1.2 data/**/*.csv（逐件登记）")
    lines.append("")
    lines.extend(render_data_table(group_rows["data_csv"], "csv"))
    lines.append("")
    lines.append("### 1.3 data/**/*.json（逐件登记）")
    lines.append("")
    lines.append("目录汇总（便于快速定位）：")
    lines.append("")
    lines.extend(directory_rollup(group_rows["data_json"]))
    lines.append("")
    lines.extend(render_data_table(group_rows["data_json"], "json"))
    lines.append("")
    lines.append("### 1.4 probes/artifacts/*.csv（逐件登记）")
    lines.append("")
    lines.extend(render_data_table(group_rows["artifacts_csv"], "csv"))
    lines.append("")
    lines.append("### 1.5 文档件登记（docs/framework、paper、reports 周立项章）")
    lines.append("")
    lines.append("| 类别 | 相对路径 | sha256 | bytes | 标题数 | 首标题 |")
    lines.append("| --- | --- | --- | ---: | ---: | --- |")
    for label in ("docs_framework", "paper_md", "charters"):
        for row in group_rows[label]:
            path = root / row["path"]
            text = path.read_text(encoding="utf-8", errors="replace")
            headings = [line.strip() for line in text.splitlines() if line.strip().startswith("#")]
            first = short(headings[0] if headings else "", MAX_DOC_TITLE)
            lines.append(
                f"| {label} | `{md_cell(row['path'])}` | `{row['sha256']}` | {row['bytes']} | "
                f"{len(headings)} | {md_cell(first)} |"
            )
    lines.append("")

    # 2. 探针摘要清单
    lines.append("## 2. 探针摘要清单")
    lines.append("")
    summary_paths, summary_blocks = render_probe_summaries(root)
    lines.append(f"共 **{len(summary_paths)}** 件 `probes/*_summary.json`；每件给出 sha256、"
                 f"schema_version/task/title，以及递归提取的前 {MAX_SCALARS_PER_SUMMARY} 条数值标量。")
    lines.append("")
    lines.extend(summary_blocks)
    lines.append("")

    # 3. 冻结读数
    lines.append("## 3. 冻结读数")
    lines.append("")
    lines.append("| 读数 | 值 | 出处 |")
    lines.append("| --- | --- | --- |")
    for label, value, source in FROZEN_READINGS:
        lines.append(f"| {label} | `{value}` | `{source}` |")
    lines.append("")

    # 4. 通道覆盖
    lines.append("## 4. 通道覆盖")
    lines.append("")
    coverage_lines, _counters, registry_total = render_channel_coverage(root)
    lines.extend(coverage_lines)
    lines.append("")

    # 5. KPI 板
    lines.append("## 5. KPI 板")
    lines.append("")
    lines.extend(render_kpi_board(root))
    lines.append("")

    # 6. 负结果登记
    lines.append("## 6. 负结果登记")
    lines.append("")
    per_file, negative_rows = render_negative_results(root)
    lines.append(f"扫描 `reports/*.md` 中含 `refuted` / `capped` 的行：命中 **{len(negative_rows)}** 行、"
                 f"分布在 **{len(per_file)}** 个文件；下表列出各文件命中数与按路径排序的前 {MAX_NEGATIVE_ROWS} 行。")
    lines.append("")
    lines.append("| 文件 | 命中行数 |")
    lines.append("| --- | ---: |")
    for name, count in per_file:
        lines.append(f"| `{md_cell(name)}` | {count} |")
    lines.append("")
    lines.append("| 文件 | 行号 | 内容（截断） |")
    lines.append("| --- | ---: | --- |")
    for name, index, text_line in negative_rows[:MAX_NEGATIVE_ROWS]:
        lines.append(f"| `{md_cell(name)}` | {index} | {md_cell(short(text_line, MAX_NEGATIVE_TEXT))} |")
    if len(negative_rows) > MAX_NEGATIVE_ROWS:
        lines.append(f"| … | … | （另有 {len(negative_rows) - MAX_NEGATIVE_ROWS} 行未展开） |")
    lines.append("")

    # 7. 出处索引
    lines.append("## 7. 出处索引")
    lines.append("")
    lines.append("| 资产 / 读数 | 规模或值 | 出处 |")
    lines.append("| --- | --- | --- |")
    lines.append("| 冻结四读数 | 见 §3 | `probes/export_week18_results.py`、`probes/w20_epsilon_second_stage_summary.json` |")
    lines.append(f"| 六通道登记表 | {registry_total} 行 | `data/processed/four_core_key_registry.csv` |")
    lines.append("| KPI 板 | ranking/coverage_cost/discipline | `probes/w20_funnel_kpi_summary.json` |")
    lines.append("| 排序逐 pair 表 | 见文件行数 | `probes/artifacts/w21_rank_pairs.csv` |")
    lines.append("| 排序稳定性读数 | 见 §2 | `probes/w21_rank_stability_summary.json` |")
    lines.append("| 大候选池（broad pool） | 见 §1.4 行数 | `probes/artifacts/w20_ranking_key_v1_candidates.csv` |")
    lines.append("| broad-pool 最小信息预算演示 | 见同目录 `_summary.json` | `probes/w22_broad_pool_budget_summary.json` |")
    lines.append(f"| 本文档生成器 | `{GENERATOR}` | 本仓库 |")
    lines.append("")

    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Build or verify the unified data document.")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="output / comparison target path")
    parser.add_argument("--check", action="store_true", help="rebuild in memory and compare bytes with --out")
    parser.add_argument("--root", default=str(REPO_ROOT), help="repository root")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    target = Path(args.out)
    fresh = build_document(root).encode("utf-8")

    if args.check:
        if not target.exists():
            print(f"[check] MISSING target: {target}")
            return 2
        on_disk = target.read_bytes()
        if on_disk == fresh:
            print(f"[check] OK ({len(fresh)} bytes match: {target})")
            return 0
        limit = min(len(on_disk), len(fresh))
        offset = next((i for i in range(limit) if on_disk[i] != fresh[i]), limit)
        print(f"[check] DRIFT at byte {offset}: disk={len(on_disk)}B fresh={len(fresh)}B target={target}")
        return 1

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(fresh)
    print(f"[build] wrote {len(fresh)} bytes to {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())