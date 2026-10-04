# -*- coding: utf-8 -*-
"""W49 投稿包落地：形式适配、投稿四件、round-2 登记（类④ + 类③，0 shot）。

默认 venue = PCCP（可被用户一票覆盖）。本件只做形式与打包，不动任何科学内容：

  * H49a1：形式适配映射清单交付且覆盖四类形式项；
  * H49a2：期刊模板 docx 按当前 v3 重渲染，段/表/图计数与稿一致；
  * H49a3：25 图逐图校验——画布长宽比与原始图片偏差 < 1e-3、绘制尺寸不超版面框；
  * H49b1：投稿四件齐备（docx / cover letter / 可复现性声明 / manifest）；
  * H49b2：可复现性声明与导出包互指（week47 包 + SHA256SUMS + commit）；
  * H49b3：形式改动零科学漂移（一致性校验 PASS + 四个冻结读数逐字在稿）；
  * H49b4 / H49d3：0 shot；
  * H49d1：README §11 第 54 条 round-2 登记落字；
  * H49d2：不变量复算一致（9 条负结果 / shot 19 / 冻结读数不在 canon 外）。

只读 + 打包治理件，不占主记分牌。累计 shot 仍 19。

Run:
    .venv/Scripts/python.exe probes/w49_submission_pack.py
    .venv/Scripts/python.exe probes/w49_submission_pack.py --check
"""

from __future__ import annotations

import argparse
import io
import json
import shutil
import subprocess
import sys
import time
import zipfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from xml.etree import ElementTree as ET

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))
sys.path.insert(0, str(REPOSITORY_ROOT / "probes"))

import w43_governance_ledger as ledger_guard
from export_results_common import write_json_stable
from w42_common import ARTIFACTS, FROZEN_READINGS, criteria_row, sha256_file, utc_now, write_csv_lf

try:
    from PIL import Image
except ImportError:  # pragma: no cover - Pillow ships with the plotting stack
    Image = None

PREREG_PATH = REPOSITORY_ROOT / "probes" / "w49_submission_pack_prereg.json"
PAPER_PATH = REPOSITORY_ROOT / "paper" / "paper_zh_draft_v3.md"
README_PATH = REPOSITORY_ROOT / "README.md"
W43_PREREG_PATH = REPOSITORY_ROOT / "probes" / "w43_protocol_prereg.json"
FORMAT_MAPPING = REPOSITORY_ROOT / "reports" / "w49_format_mapping.md"
COVER_LETTER = REPOSITORY_ROOT / "reports" / "w49_cover_letter.md"
REPRO_STATEMENT = REPOSITORY_ROOT / "reports" / "w49_reproducibility_statement.md"
MANIFEST = REPOSITORY_ROOT / "reports" / "w49_submission_manifest.md"
PACKAGE_DIR = (REPOSITORY_ROOT.parent / "成果输出" / "week49" / "投稿包")
DOCX = PACKAGE_DIR / "论文_电解液溶剂筛选中的描述符决策稳定性_期刊模版.docx"
SUMMARY_PATH = ARTIFACTS / "w49_submission_pack_summary.json"
CRITERIA_CSV = ARTIFACTS / "w49_submission_pack_criteria.csv"
REPORT_PATH = REPOSITORY_ROOT / "reports" / "w49_submission_pack.md"

SCHEMA = "w49_submission_pack/summary@1"
TASK = "week49_submission_pack"
REGISTERED_NEGATIVES: tuple[str, ...] = ()
CRITERIA_FIELDS = ("id", "description", "value", "threshold", "verdict")

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
WP = "{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}"
A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
EMU_PER_CM = 360000.0
USABLE_W_CM = 16.4
USABLE_H_CM = 23.3
MAX_ASPECT_DEVIATION = 1e-3

EXPECTED_PARAGRAPHS = 412
EXPECTED_TABLES = 9
EXPECTED_FIGURES = 25
FORMAT_MARKERS = ("① 标题页", "② 摘要", "③ 图件", "④ 参考文献")
REPRO_MARKERS = ("成果输出/week47", "SHA256SUMS", "92d47b8")
README_MARKERS = ("54. **新登记（W49）", "round-2")


def load_prereg() -> Mapping[str, object]:
    payload = json.loads(PREREG_PATH.read_text(encoding="utf-8-sig"))
    if payload.get("status") != "locked_before_run":
        raise SystemExit("w49 prereg is not locked_before_run: " + str(payload.get("status")))
    return payload


def run_consistency() -> int:
    completed = subprocess.run(
        [sys.executable, "scripts/check_paper_artifact_consistency.py"],
        cwd=str(REPOSITORY_ROOT), capture_output=True, text=True, check=False)
    return completed.returncode


def inspect_docx(path: Path) -> dict[str, object]:
    if not path.is_file():
        return {"exists": False, "paragraphs": 0, "tables": 0, "figures": 0,
                "max_aspect_deviation": None, "overflows": [], "media": 0}
    with zipfile.ZipFile(path) as archive:
        root = ET.fromstring(archive.read("word/document.xml"))
        body = root.find(W + "body")
        paragraphs = len(body.findall(W + "p"))
        tables = len(body.findall(W + "tbl"))
        inlines = list(root.iter(WP + "inline"))
        blips = list(root.iter(A + "blip"))
        rels = ET.fromstring(archive.read("word/_rels/document.xml.rels"))
        relmap = {element.get("Id"): element.get("Target") for element in rels}
        deviations: list[float] = []
        overflows: list[list[float]] = []
        media = len([name for name in archive.namelist() if name.startswith("word/media/")])
        for inline, blip in zip(inlines, blips):
            extent = inline.find(WP + "extent")
            if extent is None:
                continue
            cx = int(extent.get("cx"))
            cy = int(extent.get("cy"))
            target = relmap.get(blip.get(R + "embed"))
            if not target:
                continue
            data = archive.read("word/" + target.replace("../", ""))
            if Image is None:
                continue
            with Image.open(io.BytesIO(data)) as image:
                width_px, height_px = image.size
            if height_px and cy:
                deviations.append(abs((cx / cy) / (width_px / height_px) - 1.0))
            width_cm = cx / EMU_PER_CM
            height_cm = cy / EMU_PER_CM
            if width_cm > USABLE_W_CM + 1e-6 or height_cm > USABLE_H_CM + 1e-6:
                overflows.append([round(width_cm, 3), round(height_cm, 3)])
    return {
        "exists": True,
        "paragraphs": paragraphs,
        "tables": tables,
        "figures": len(inlines),
        "media": media,
        "max_aspect_deviation": max(deviations) if deviations else None,
        "n_measured": len(deviations),
        "overflows": overflows,
        "sha256": sha256_file(path),
        "bytes": path.stat().st_size,
    }


def write_manifest(docx: Mapping[str, object]) -> None:
    rows = [
        ("论文（期刊模板 docx）", "论文_..._期刊模版.docx", str(docx.get("sha256"))),
        ("Cover letter", "reports/w49_cover_letter.md", sha256_file(COVER_LETTER)),
        ("形式适配映射清单", "reports/w49_format_mapping.md", sha256_file(FORMAT_MAPPING)),
        ("可复现性声明", "reports/w49_reproducibility_statement.md", sha256_file(REPRO_STATEMENT)),
        ("论文源稿 v3", "paper/paper_zh_draft_v3.md", sha256_file(PAPER_PATH)),
    ]
    lines = [
        "# W49 投稿包清单（submission manifest）",
        "",
        "默认 venue = PCCP（可覆盖）。本清单由 probes/w49_submission_pack.py 生成，内容确定、不含时间戳。",
        "",
        "| 件 | 路径 | sha256 |",
        "| --- | --- | --- |",
    ]
    for label, relative, digest in rows:
        lines.append("| " + label + " | " + relative + " | " + str(digest) + " |")
    lines.append("")
    lines.append("包目录：" + str(PACKAGE_DIR))
    lines.append("")
    MANIFEST.write_text("\n".join(lines), encoding="utf-8", newline="\n")


def stage_package() -> list[str]:
    PACKAGE_DIR.mkdir(parents=True, exist_ok=True)
    staged = []
    for source in (COVER_LETTER, FORMAT_MAPPING, REPRO_STATEMENT, MANIFEST):
        if source.is_file():
            shutil.copy2(source, PACKAGE_DIR / source.name)
            staged.append(source.name)
    return sorted(staged)


def compute(prereg: Mapping[str, object]) -> dict[str, object]:
    docx = inspect_docx(DOCX)
    format_text = FORMAT_MAPPING.read_text(encoding="utf-8") if FORMAT_MAPPING.is_file() else ""
    repro_text = (REPRO_STATEMENT.read_text(encoding="utf-8")
                  if REPRO_STATEMENT.is_file() else "")
    readme = README_PATH.read_text(encoding="utf-8")
    paper = PAPER_PATH.read_text(encoding="utf-8")
    ledger_payload = ledger_guard.compute(
        json.loads(W43_PREREG_PATH.read_text(encoding="utf-8-sig")))
    invariants = ledger_payload["invariants"]
    return {
        "docx": docx,
        "format_markers": {marker: (marker in format_text) for marker in FORMAT_MARKERS},
        "repro_markers": {marker: (marker in repro_text) for marker in REPRO_MARKERS},
        "readme_markers": {marker: (marker in readme) for marker in README_MARKERS},
        "cover_letter_exists": COVER_LETTER.is_file(),
        "repro_exists": REPRO_STATEMENT.is_file(),
        "manifest_exists": MANIFEST.is_file(),
        "format_mapping_exists": FORMAT_MAPPING.is_file(),
        "readings_literal": {str(reading): (str(reading) in paper)
                             for reading in FROZEN_READINGS},
        "consistency_returncode": run_consistency(),
        "registered_negatives": len(invariants["registered_negatives_union"]),
        "cumulative_shots_max": int(invariants["cumulative_shots_max"]),
        "frozen_outside_canon": int(invariants["frozen_outside_canon"]),
    }


def evaluate(payload: Mapping[str, object], prereg: Mapping[str, object]) -> list[dict[str, object]]:
    docx = payload["docx"]
    deviation = docx["max_aspect_deviation"]
    return [
        criteria_row("H49a1", "形式适配映射清单交付且覆盖四类形式项（标题页/摘要/图件/参考文献）",
                     {"exists": payload["format_mapping_exists"],
                      "markers": payload["format_markers"]},
                     {"markers": list(FORMAT_MARKERS)},
                     bool(payload["format_mapping_exists"])
                     and all(payload["format_markers"].values())),
        criteria_row("H49a2", "期刊模板 docx 结构与当前 v3 一致（段/表/图计数）",
                     {"exists": docx["exists"], "paragraphs": docx["paragraphs"],
                      "tables": docx["tables"], "figures": docx["figures"],
                      "bytes": docx.get("bytes")},
                     {"paragraphs": EXPECTED_PARAGRAPHS, "tables": EXPECTED_TABLES,
                      "figures": EXPECTED_FIGURES},
                     bool(docx["exists"]) and docx["paragraphs"] == EXPECTED_PARAGRAPHS
                     and docx["tables"] == EXPECTED_TABLES
                     and docx["figures"] == EXPECTED_FIGURES),
        criteria_row("H49a3", "25 图逐图可完整显示：长宽比偏差 < 1e-3 且不超版面框",
                     {"n_measured": docx.get("n_measured"),
                      "max_aspect_deviation": deviation,
                      "overflows": docx["overflows"],
                      "usable_cm": [USABLE_W_CM, USABLE_H_CM]},
                     {"min_measured": EXPECTED_FIGURES,
                      "max_aspect_deviation": MAX_ASPECT_DEVIATION, "overflows": []},
                     docx.get("n_measured") == EXPECTED_FIGURES
                     and deviation is not None and deviation < MAX_ASPECT_DEVIATION
                     and not docx["overflows"]),
        criteria_row("H49b1", "投稿四件齐备（docx / cover letter / 可复现性声明 / manifest）",
                     {"docx": docx["exists"], "cover_letter": payload["cover_letter_exists"],
                      "reproducibility": payload["repro_exists"],
                      "manifest": payload["manifest_exists"]},
                     {"all_four": True},
                     bool(docx["exists"]) and bool(payload["cover_letter_exists"])
                     and bool(payload["repro_exists"]) and bool(payload["manifest_exists"])),
        criteria_row("H49b2", "可复现性声明与导出包互指（week47 包 + SHA256SUMS + 基线 commit）",
                     {"markers": payload["repro_markers"]},
                     {"markers": list(REPRO_MARKERS)},
                     all(payload["repro_markers"].values())),
        criteria_row("H49b3", "形式改动零科学漂移：一致性校验 PASS 且四个冻结读数逐字在稿",
                     {"consistency_returncode": payload["consistency_returncode"],
                      "readings_literal": payload["readings_literal"]},
                     {"consistency_returncode": 0, "all_literal": True},
                     payload["consistency_returncode"] == 0
                     and all(payload["readings_literal"].values())),
        criteria_row("H49b4", "0 shot（投稿操作不占主记分牌）",
                     {"shots_this_week": 0}, {"shots": 0}, True),
        criteria_row("H49d1", "README §11 第 54 条 round-2 登记落字",
                     {"markers": payload["readme_markers"]}, {"markers": list(README_MARKERS)},
                     all(payload["readme_markers"].values())),
        criteria_row("H49d2", "不变量复算一致：9 条负结果 / shot 19 / 冻结读数不在 canon 外",
                     {"registered_negatives": payload["registered_negatives"],
                      "cumulative_shots_max": payload["cumulative_shots_max"],
                      "frozen_outside_canon": payload["frozen_outside_canon"]},
                     {"registered_negatives": 9, "cumulative_shots_max": 19,
                      "frozen_outside_canon": 0},
                     payload["registered_negatives"] == 9
                     and payload["cumulative_shots_max"] == 19
                     and payload["frozen_outside_canon"] == 0),
        criteria_row("H49d3", "0 shot（结算周不改主记分牌）",
                     {"shots_this_week": 0}, {"shots": 0}, True),
    ]


def render_report(payload: Mapping[str, object],
                  criteria: Sequence[Mapping[str, object]]) -> str:
    docx = payload["docx"]
    lines: list[str] = []
    add = lines.append
    add("# W49 投稿包落地（默认 venue = PCCP，0 shot）")
    add("")
    add("类④（投稿操作）+ 类③（round-2 登记）。venue 默认 PCCP，可被用户一票覆盖。")
    add("")
    add("## 1 投稿包四件")
    add("")
    add("| 件 | 状态 |")
    add("| --- | --- |")
    add("| 期刊模板 docx | " + ("在" if docx["exists"] else "缺") + "（段 " + str(docx["paragraphs"])
        + " / 表 " + str(docx["tables"]) + " / 图 " + str(docx["figures"])
        + "，sha256 " + str(docx.get("sha256"))[:16] + "） |")
    add("| cover letter | " + ("在" if payload["cover_letter_exists"] else "缺") + " |")
    add("| 可复现性声明 | " + ("在" if payload["repro_exists"] else "缺") + " |")
    add("| submission manifest | " + ("在" if payload["manifest_exists"] else "缺") + " |")
    add("")
    add("- 图片完整性：实测 " + str(docx.get("n_measured")) + " 图，最大长宽比偏差 "
        + str(docx.get("max_aspect_deviation")) + "，越界 " + str(docx["overflows"]) + "。")
    add("- 包目录：" + str(PACKAGE_DIR) + "。")
    add("")
    add("## 2 判据")
    add("")
    add("| id | 判据 | 值 | 阈 | 判决 |")
    add("| --- | --- | --- | --- | --- |")
    for row in criteria:
        add("| " + str(row["id"]) + " | " + str(row["description"]) + " | "
            + json.dumps(row["value"], ensure_ascii=False) + " | "
            + json.dumps(row["threshold"], ensure_ascii=False) + " | " + str(row["verdict"]) + " |")
    add("")
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="只算不写盘")
    args = parser.parse_args(argv)
    started = time.perf_counter()
    prereg = load_prereg()
    if not args.check:
        write_manifest(inspect_docx(DOCX))
    payload = compute(prereg)
    sources = [PREREG_PATH, PAPER_PATH, README_PATH, FORMAT_MAPPING, COVER_LETTER,
               REPRO_STATEMENT, MANIFEST]
    before = {str(path): sha256_file(path) for path in sources if path.is_file()}
    staged = [] if args.check else stage_package()
    after = {str(path): sha256_file(path) for path in sources if path.is_file()}
    inputs_unchanged = before == after

    criteria = evaluate(payload, prereg)
    failed = [item for item in criteria if item["verdict"] != "成立"]
    unregistered = [item for item in failed if str(item["id"]) not in REGISTERED_NEGATIVES]

    if not args.check:
        write_csv_lf(CRITERIA_CSV, CRITERIA_FIELDS, criteria)
        summary = {
            "schema": SCHEMA,
            "task": TASK,
            "generated_at_utc": utc_now(),
            "elapsed_seconds": float(time.perf_counter() - started),
            "ledger": {
                "main_scoreboard_shots_this_week": 0,
                "cumulative_main_scoreboard_attempts_after": 19,
                "why_not_a_shot": "投稿包落地：只做形式映射、docx 重渲染与打包，不拟合主记分牌臂、不新增特征列、不动冻结读数。",
            },
            "inputs": before,
            "inputs_unchanged": inputs_unchanged,
            "frozen_readings_untouched": list(FROZEN_READINGS),
            "default_venue": "PCCP",
            "venue_overridable": True,
            "package_dir": str(PACKAGE_DIR),
            "package_staged": staged,
            "docx": payload["docx"],
            "format_markers": payload["format_markers"],
            "repro_markers": payload["repro_markers"],
            "readme_markers": payload["readme_markers"],
            "readings_literal": payload["readings_literal"],
            "consistency_returncode": payload["consistency_returncode"],
            "invariants": {"registered_negatives": payload["registered_negatives"],
                           "cumulative_shots_max": payload["cumulative_shots_max"],
                           "frozen_outside_canon": payload["frozen_outside_canon"]},
            "criteria": criteria,
            "registered_negatives": list(REGISTERED_NEGATIVES),
            "headline": [
                "投稿包四件齐备；docx " + str(payload["docx"]["paragraphs"]) + " 段 / "
                + str(payload["docx"]["tables"]) + " 表 / " + str(payload["docx"]["figures"])
                + " 图，长宽比偏差 " + str(payload["docx"]["max_aspect_deviation"]) + "。",
                "默认 venue = PCCP（可覆盖）；round-2 登记已落 README §11 第 54 条。",
                "0 shot（累计仍 19）；四个冻结读数不动。",
            ],
        }
        write_json_stable(SUMMARY_PATH, summary)
        REPORT_PATH.write_text(render_report(payload, criteria), encoding="utf-8", newline="\n")

    print("docx %s | figures %d | max_ar_dev %s | consistency rc %d | shots 0"
          % (payload["docx"]["exists"], payload["docx"]["figures"],
             payload["docx"]["max_aspect_deviation"], payload["consistency_returncode"]))
    print("criteria %d/%d" % (len(criteria) - len(failed), len(criteria)))
    for item in failed:
        print("FAIL %s %s" % (item["id"], item["description"]))
    return 1 if unregistered else 0


if __name__ == "__main__":
    raise SystemExit(main())
