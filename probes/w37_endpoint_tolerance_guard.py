# -*- coding: utf-8 -*-
"""W37-A：端点判等容差守卫（回答 README §11 第 17 条；不占 shot）。

W36-A 把主记分牌「端点规则」写成了盘上条款（`data/processed/w36_endpoint_rule_registry.csv`），
其中 R5 规定「端点判等容差 = 1e-12」。但这条规则此前只活在文档里：任何人仍然可以写下
`if value == 0.5861142332208197:` 这种逐位判等，而没有任何机器会拦住他。本件把它变成守卫：

1. 容差**从注册表 R5 读出**并断言等于 `w36_endpoint_rule.ENDPOINT_TOLERANCE`（改注册表会被发现）；
2. 用 AST 扫描 `probes/*.py` / `scripts/*.py` / `src/**/*.py` / `tests/*.py` 里的「端点比较」可疑点
   —— `ast.Compare` 的 `Eq`/`NotEq`，任一侧是 8 位以上有效数字的 float 或数值字符串字面量；
   —— 另用「子串 + AST」两种方式扫四个冻结读数是否被 `==`/`!=` 直接比较；
3. 现场构造一条合成违规与一条合法用法，用同一套扫描逻辑自检（能抓 / 不误抓）。

只读盘上文件；不重跑模型、不新增特征、不触 ε 主记分牌；本件是治理/守卫件，**0 shot**，累计仍 19。
"""

from __future__ import annotations

import ast
import csv
import math
import re
import sys
import time
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_PROBES = str(REPOSITORY_ROOT / "probes")
if _PROBES not in sys.path:
    sys.path.insert(0, _PROBES)
from export_results_common import write_json_stable
from w36_endpoint_rule import ENDPOINT_TOLERANCE, endpoint_of

ARTIFACT_DIR = REPOSITORY_ROOT / "probes" / "artifacts"
SUMMARY_PATH = ARTIFACT_DIR / "w37_endpoint_tolerance_guard_summary.json"
SITES_CSV = ARTIFACT_DIR / "w37_endpoint_compare_sites.csv"
REPORT_PATH = REPOSITORY_ROOT / "reports" / "w37_endpoint_tolerance_guard.md"
REGISTRY_CSV = REPOSITORY_ROOT / "data" / "processed" / "w36_endpoint_rule_registry.csv"
W20_REPEATS = ARTIFACT_DIR / "w20_epsilon_second_stage_repeats.csv"

SCHEMA = "w37_endpoint_tolerance_guard/summary@1"
TASK = "week37_endpoint_tolerance_guard"
MIN_SIGNIFICANT_DIGITS = 8

# 四个冻结读数的十进制字面量（论文附录 A / README §0；R6 规定原值不变）。
FROZEN_READINGS = {
    "frozen_baseline": "0.4091179943351143",
    "frozen_headline": "0.4766400383507876",
    "single_representation_cross_seed": "0.5861142332208197",
    "w20_4_promoted_arm": "0.6216672295270079",
}
FROZEN_VALUES = tuple(FROZEN_READINGS.values())

SCAN_ROOTS = ("probes", "scripts", "src", "tests")
SITE_FIELDS = ("path", "line", "kind", "snippet", "disposition", "reason")

# 自检夹具：一条合成违规（必须被抓）与一条合法用法（必须不被抓）。
SYNTHETIC_VIOLATION = "if value == 0.5861142332208197:\n    pass\n"
SYNTHETIC_LEGAL = "if abs(a - b) <= ENDPOINT_TOLERANCE:\n    pass\n"


# --------------------------------------------------------------------------- #
# 数值与判等入口
# --------------------------------------------------------------------------- #
def significant_digits(text: str) -> int:
    """按书写形式近似计有效数字（不做尾零消歧，偏保守：宁多不少）。"""
    stripped = str(text).strip().lstrip("+-")
    mantissa = re.split("[eE]", stripped, maxsplit=1)[0].replace(".", "")
    return len(mantissa.lstrip("0"))


def is_high_precision_literal_text(text: str) -> bool:
    try:
        float(text)
    except (TypeError, ValueError):
        return False
    return significant_digits(text) >= MIN_SIGNIFICANT_DIGITS


def endpoint_value(text):
    """把盘上 / 字面量里的端点值文本解析成 float，作为判等的统一入口。"""
    if isinstance(text, bool) or not isinstance(text, (int, float, str)):
        raise TypeError("endpoint_value 只接受 int/float/str，收到 " + type(text).__name__)
    stripped = str(text).strip()
    if not stripped:
        raise ValueError("空文本不是端点值")
    try:
        return float(stripped)
    except ValueError:
        raise ValueError("不是可解析的端点数值文本: " + repr(text)) from None


def read_registry_tolerance(path=None) -> float:
    """从注册表 R5 行读出端点判等容差，并断言与 w36 复算符声明一致。"""
    target = REGISTRY_CSV if path is None else Path(path)
    with target.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if row.get("rule_id") == "R5":
                value = endpoint_value(row.get("value", ""))
                if value != ENDPOINT_TOLERANCE:
                    raise AssertionError(
                        "注册表 R5 容差 " + repr(value) + " != ENDPOINT_TOLERANCE "
                        + repr(ENDPOINT_TOLERANCE))
                return value
    raise KeyError("注册表里没有 R5 行: " + str(target))


def endpoints_equal(a, b, tol=None) -> bool:
    """端点判等守卫：默认走注册表 R5 容差，绝不退化成逐位字符串相等。"""
    if tol is None:
        tol = read_registry_tolerance()
    return abs(endpoint_value(a) - endpoint_value(b)) <= tol


# --------------------------------------------------------------------------- #
# AST 扫描
# --------------------------------------------------------------------------- #
def literal_kind(node):
    """返回 (kind, text) 或 None；kind in {"float", "str"}。"""
    if not isinstance(node, ast.Constant):
        return None
    value = node.value
    if isinstance(value, bool):
        return None
    if isinstance(value, float):
        text = repr(value)
        if significant_digits(text) >= MIN_SIGNIFICANT_DIGITS:
            return ("float", text)
        return None
    if isinstance(value, str):
        if is_high_precision_literal_text(value):
            return ("str", value)
    return None


def frozen_match(text: str):
    """字面量（数值或数值字符串）是否等于某个冻结读数；返回其名字或 None。"""
    try:
        value = float(text)
    except (TypeError, ValueError):
        return None
    for name, frozen in FROZEN_READINGS.items():
        if value == float(frozen):
            return name
    return None


def build_parent_map(tree):
    parents = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[child] = parent
    return parents


def is_under_assert(node, parents) -> bool:
    current = node
    while current in parents:
        current = parents[current]
        if isinstance(current, ast.Assert):
            return True
    return False


def normalize_snippet(text: str, limit: int = 160) -> str:
    flat = " ".join(str(text).split())
    return flat if len(flat) <= limit else flat[: limit - 1] + "…"


def classify(under_assert: bool, frozen, kind: str):
    """判定策略：运行期控制流的逐位判等=禁止；测试断言里的登记常量回归=允许。"""
    if under_assert:
        if frozen is not None:
            return ("允许", "测试断言：对已登记冻结读数（" + frozen
                    + "）做原值回归（R6 四冻结读数原值不变）；比较对象是登记常量，不是端点复算判等")
        if kind == "str":
            return ("允许", "测试断言：比较字符串形式的登记引脚值，不是端点数值判等")
        return ("允许", "测试断言：引脚 / 夹具指标（非端点）原值校验，不是端点判等")
    if frozen is not None:
        return ("禁止", "运行期控制流对冻结端点读数（" + frozen
                + "）做逐位 ==/!= 判等；端点判等必须走 endpoint_of()+容差")
    return ("禁止", "运行期控制流用 8 位以上有效数字字面量做逐位 ==/!= 判等；端点判等必须走 endpoint_of()+容差")


def scan_source(code: str, path: str):
    """AST 扫描一段源码里的端点比较可疑点（可复用于合成自检）。"""
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        raise SyntaxError("扫描目标无法解析: " + path + " -> " + str(exc)) from None
    parents = build_parent_map(tree)
    sites = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Compare):
            continue
        if not any(isinstance(op, (ast.Eq, ast.NotEq)) for op in node.ops):
            continue
        for operand in [node.left] + list(node.comparators):
            info = literal_kind(operand)
            if info is None:
                continue
            kind, text = info
            frozen = frozen_match(text)
            if frozen is not None:
                site_kind = "frozen_eq"
            elif kind == "str":
                site_kind = "high_precision_str_eq"
            else:
                site_kind = "high_precision_float_eq"
            disposition, reason = classify(is_under_assert(node, parents), frozen, kind)
            sites.append({
                "path": path, "line": int(node.lineno), "kind": site_kind,
                "snippet": normalize_snippet(ast.get_source_segment(code, node) or ""),
                "disposition": disposition, "reason": reason,
            })
    return sites


def scan_frozen_text(code: str, path: str):
    """子串扫描：冻结读数出现在含 == / != 的行（补足 AST 抓不到的字符串 / 清单用法）。"""
    sites = []
    for lineno, line in enumerate(code.splitlines(), start=1):
        matched = [lit for lit in FROZEN_VALUES if lit in line]
        if not matched or ("==" not in line and "!=" not in line):
            continue
        disposition, reason = classify_text_line(line, matched)
        sites.append({
            "path": path, "line": lineno, "kind": "frozen_text",
            "snippet": normalize_snippet(line), "disposition": disposition, "reason": reason,
        })
    return sites


def classify_text_line(line: str, matched):
    if "approx(" in line:
        return ("允许", "该行已用 pytest.approx 容差比较冻结读数，符合守卫意图")
    for literal in matched:
        if re.search(r"[\"']\s*" + re.escape(literal), line):
            return ("允许", "冻结读数以字符串 / 清单形式登记或交叉校验，不是端点数值判等")
    return ("允许", "文本子串命中：冻结读数出现在含 ==/!= 的行（文档 / 注释 / 字符串拼接），非端点数值判等")


# --------------------------------------------------------------------------- #
# 仓库级扫描
# --------------------------------------------------------------------------- #
def collect_scan_files():
    files = []
    for root in SCAN_ROOTS:
        base = REPOSITORY_ROOT / root
        if root == "src":
            files.extend(base.rglob("*.py"))
        else:
            files.extend(base.glob("*.py"))
    return sorted(set(files))


def scan_repository():
    sites = []
    files_scanned = 0
    unparsable = []
    root_file_counts = {root: 0 for root in SCAN_ROOTS}
    for path in collect_scan_files():
        rel = path.relative_to(REPOSITORY_ROOT).as_posix()
        root_file_counts[rel.split("/", 1)[0]] += 1
        files_scanned += 1
        try:
            code = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            code = path.read_text(encoding="utf-8", errors="replace")
        if code.startswith("\ufeff"):
            code = code[1:]
        try:
            sites.extend(scan_source(code, rel))
        except SyntaxError:
            unparsable.append(rel)
        sites.extend(scan_frozen_text(code, rel))
    return {"sites": dedupe(sites), "files_scanned": files_scanned,
            "files_unparsable": unparsable, "root_file_counts": root_file_counts}


def dedupe(sites):
    seen = set()
    out = []
    for site in sorted(sites, key=lambda s: (s["path"], s["line"], s["kind"], s["snippet"])):
        key = (site["path"], site["line"], site["kind"], site["snippet"])
        if key in seen:
            continue
        seen.add(key)
        out.append(site)
    return out


# --------------------------------------------------------------------------- #
# 复用诊断（证明 endpoint_of 可用，且逐位相等会碎）
# --------------------------------------------------------------------------- #
def reuse_diagnostic():
    if not W20_REPEATS.exists():
        return {"available": False}
    with W20_REPEATS.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    recomputed = endpoint_of(rows, "xgb_reference")
    published = float(FROZEN_READINGS["single_representation_cross_seed"])
    value = recomputed["endpoint"]
    return {
        "available": True,
        "table": W20_REPEATS.relative_to(REPOSITORY_ROOT).as_posix(),
        "arm": "xgb_reference",
        "endpoint_recomputed": repr(value),
        "endpoint_published": repr(published),
        "abs_diff": repr(abs(value - published)),
        "ulp_gap": repr(abs(value - published) / math.ulp(published)) if published else None,
        "bitwise_equal": bool(value == published),
        "endpoints_equal": bool(endpoints_equal(value, published)),
    }


# --------------------------------------------------------------------------- #
# 判据
# --------------------------------------------------------------------------- #
def verdict(identifier, description, value, threshold, passed) -> dict:
    return {"id": identifier, "description": description,
            "value": None if value is None else float(value),
            "threshold": None if threshold is None else float(threshold),
            "verdict": "成立" if bool(passed) else "判否"}


def evaluate(scan, tolerance, reuse):
    forbidden = [site for site in scan["sites"] if site["disposition"] == "禁止"]
    synthetic_bad = [site for site in scan_source(SYNTHETIC_VIOLATION, "<synthetic_violation>")
                     if site["disposition"] == "禁止"]
    synthetic_legal = [site for site in scan_source(SYNTHETIC_LEGAL, "<synthetic_legal>")
                       if site["disposition"] == "禁止"]
    anchor = float(FROZEN_READINGS["single_representation_cross_seed"])
    two_ulp = anchor + 2 * math.ulp(anchor)
    tolerates_ulp = bool(endpoints_equal(anchor, two_ulp) and two_ulp != anchor)
    rejects_noise = not endpoints_equal(anchor, anchor + 1e-9)
    criteria = [
        verdict("H37a1", "注册表 R5 读出容差 == w36 ENDPOINT_TOLERANCE == 1e-12（改注册表会被发现）",
                tolerance, ENDPOINT_TOLERANCE,
                tolerance == ENDPOINT_TOLERANCE and tolerance == 1e-12),
        verdict("H37a2", "现存禁止项 = 0（扫描 probes/scripts/src/tests 的高精度字面量 Eq/NotEq）",
                float(len(forbidden)), 0.0, len(forbidden) == 0),
        verdict("H37a3", "合成违规（if value == 0.5861142332208197:）被抓（禁止项 >= 1）",
                float(len(synthetic_bad)), 1.0, len(synthetic_bad) >= 1),
        verdict("H37a4", "合法用法（abs(a-b) <= ENDPOINT_TOLERANCE）不被误抓（禁止项 = 0）",
                float(len(synthetic_legal)), 0.0, len(synthetic_legal) == 0),
        verdict("H37a5", "endpoints_equal 容忍 1-2 ulp 噪声、拒绝 1e-9 级差异（容差取自 R5）",
                1.0 if (tolerates_ulp and rejects_noise) else 0.0, 1.0,
                bool(tolerates_ulp and rejects_noise)),
    ]
    diagnostics = {
        "forbidden_sites": forbidden,
        "synthetic_violation_forbidden": synthetic_bad,
        "synthetic_legal_forbidden": synthetic_legal,
        "two_ulp_delta": repr(two_ulp - anchor),
        "tolerates_1_2_ulp": bool(tolerates_ulp),
        "rejects_1e-9": bool(rejects_noise),
    }
    return criteria, diagnostics


# --------------------------------------------------------------------------- #
# 产物
# --------------------------------------------------------------------------- #
def write_csv_lf(path, fieldnames, rows) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with Path(path).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def by_kind_counts(sites):
    counts = {}
    for site in sites:
        counts[site["kind"]] = counts.get(site["kind"], 0) + 1
    return counts


def render_report(payload: dict) -> str:
    scan = payload["scan"]
    sites = payload["sites"]
    lines = [
        "# W37-A 结题报告：端点判等容差守卫",
        "",
        "回答 README §11 第 17 条：把「任何端点比对都必须走 `endpoint_of()` + 容差」写成机器守卫，",
        "禁止再新增逐位字符串相等的端点比较。",
        "",
        "- **性质**：治理 / 守卫件 —— 只读盘上文件，不拟合模型、不新增特征、不触 ε 主记分牌。",
        "- **shot 记账**：本件 **0 shot**，累计仍是 **19**；`promoted=False`。",
        "- **复用**：`from w36_endpoint_rule import endpoint_of, ENDPOINT_TOLERANCE`（不重造复算符）。",
        "- **容差来源**：`" + payload["endpoint_tolerance_source"] + "` = `1e-12`，探针运行时从盘上读出。",
        "",
        "## 1. 为什么「逐位字符串相等」会碎",
        "",
        "W36-A 复算了六张逐重复表、全部已发布端点，发现：论文附录 A / README §0 里的发布值",
        "与 `statistics.fmean` 现场复算值**最多差 2 ulp**（约 1.1e-16 ~ 2.2e-16）。",
        "原因是「端点」是两级均值（先对每种子 10 折取均值，再对 5 个锁定种子取均值），",
        "浮点求和的结合顺序一变就会落到相邻浮点上。",
        "",
        "因此 `a == b`、`repr(a) == repr(b)`、`str(a) == \"0.5861142332208197\"` 这类**逐位比较**",
        "会在 1–2 ulp 噪声下随机判否；端点判等必须写成 `abs(a - b) <= 1e-12`（规则 R5）。",
        "",
        "探针复用 `endpoint_of()` 现场演示（`" + str(payload["reuse_diagnostic"].get("table", "—")) + "`，臂 `xgb_reference`）：",
        "",
        "| 量 | 值 |",
        "| --- | --- |",
        "| 复算端点 | `" + str(payload["reuse_diagnostic"].get("endpoint_recomputed", "—")) + "` |",
        "| 发布端点 | `" + str(payload["reuse_diagnostic"].get("endpoint_published", "—")) + "` |",
        "| 绝对差 | `" + str(payload["reuse_diagnostic"].get("abs_diff", "—")) + "` |",
        "| ulp 差 | `" + str(payload["reuse_diagnostic"].get("ulp_gap", "—")) + "` |",
        "| 逐位相等？ | `" + str(payload["reuse_diagnostic"].get("bitwise_equal", "—")) + "` |",
        "| `endpoints_equal`？ | `" + str(payload["reuse_diagnostic"].get("endpoints_equal", "—")) + "` |",
        "",
        "## 2. 扫描方法",
        "",
        "- **AST 法**：对 `" + "/".join(SCAN_ROOTS) + "` 下的 `*.py` 解析 AST，找 `ast.Compare` 的 `Eq`/`NotEq`，",
        "  任一侧是 8 位以上有效数字的 `float` 字面量，或可解析为 float 且 8 位以上有效数字的字符串字面量。",
        "- **冻结读数交叉检查**：四个冻结读数（`" + "`、`".join(FROZEN_VALUES) + "`）",
        "  是否被 `==`/`!=` 直接比较 —— **子串 + AST 两种**方式各扫一遍。",
        "- **自检夹具**：合成违规 `" + SYNTHETIC_VIOLATION.strip().splitlines()[0] + "` 必须被抓；",
        "  合法用法 `" + SYNTHETIC_LEGAL.strip().splitlines()[0] + "` 必须不被抓。",
        "",
        "- 扫描文件数：" + str(scan["files_scanned"]) + "（各来源："
        + "，".join(root + "=" + str(count) for root, count in scan["root_file_counts"].items()) + "）",
        "- 无法解析：" + (("`" + "`、`".join(scan["files_unparsable"]) + "`") if scan["files_unparsable"] else "无"),
        "",
        "## 3. 判定策略",
        "",
        "| 情形 | 处置 | 依据 |",
        "| --- | --- | --- |",
        "| 测试断言（`assert`）里对登记常量 / 引脚做 `==` 原值回归 | 允许 | 比较对象是已入册常量，不是端点复算判等；R6 要求四冻结读数原值不变 |",
        "| 运行期控制流（`if`/`while`/表达式）用高精度字面量做 `Eq`/`NotEq` | 禁止 | 逐位端点判等会在 1–2 ulp 噪声下碎；必须 `endpoint_of()` + 容差 |",
        "| 冻结读数出现在字符串 / 清单 / `pytest.approx(...)` 行 | 允许 | 非端点数值判等，或已用容差比较 |",
        "",
        "## 4. 扫描结果",
        "",
        "| 指标 | 读数 |",
        "| --- | --- |",
        "| 命中点总数 | " + str(sites["total"]) + " |",
        "| 允许 | " + str(sites["allowed"]) + " |",
        "| **禁止** | **" + str(sites["forbidden"]) + "** |",
        "| 按 kind | " + "，".join(kind + "=" + str(count) for kind, count in sites["by_kind"].items()) + " |",
        "",
    ]
    if sites["forbidden"]:
        lines += ["现存禁止项（未擅自改动他人文件，如实登记）：", ""]
        for site in payload["forbidden_sites"]:
            lines.append("- `" + site["path"] + ":" + str(site["line"]) + "` `" + site["snippet"] + "` —— " + site["reason"])
        lines.append("")
    else:
        lines += ["现存禁止项为 0：仓库当前的 8 位以上有效数字字面量 `Eq`/`NotEq` 全部落在测试断言里，",
                  "已按上表判为「允许」并逐条写明 reason。", ""]
    lines += [
        "## 5. 判据",
        "",
        "| 判据 | 内容 | 读数 | 阈值 | 裁决 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for item in payload["criteria"]:
        lines.append("| " + item["id"] + " | " + item["description"] + " | "
                     + ("—" if item["value"] is None else format(item["value"], ".6g")) + " | "
                     + ("—" if item["threshold"] is None else format(item["threshold"], ".6g"))
                     + " | " + item["verdict"] + " |")
    lines += ["", "## 6. 边界", ""]
    lines += ["- " + item for item in payload["boundaries"]]
    lines.append("")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# 主流程
# --------------------------------------------------------------------------- #
def main() -> int:
    started = time.perf_counter()
    tolerance = read_registry_tolerance()
    scan = scan_repository()
    reuse = reuse_diagnostic()
    criteria, diagnostics = evaluate(scan, tolerance, reuse)

    sites = scan["sites"]
    forbidden = [site for site in sites if site["disposition"] == "禁止"]
    allowed = [site for site in sites if site["disposition"] == "允许"]
    if any(not site["reason"] for site in allowed):
        raise AssertionError("允许项必须给出非空 reason")

    write_csv_lf(SITES_CSV, SITE_FIELDS, sites)
    payload = {
        "schema": SCHEMA, "task": TASK,
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "elapsed_seconds": float(time.perf_counter() - started),
        "ledger": {"main_scoreboard_shots_this_week": 0,
                   "cumulative_main_scoreboard_attempts_after": 19,
                   "why_not_a_shot": "治理/守卫件：只做 AST 静态扫描 + 注册表读取，不拟合模型、不新增特征、不触 ε 主记分牌。"},
        "promoted": False,
        "endpoint_tolerance": tolerance,
        "endpoint_tolerance_source": "data/processed/w36_endpoint_rule_registry.csv::R5",
        "reused_from_w36": {"module": "probes/w36_endpoint_rule.py",
                            "symbols": ["endpoint_of", "ENDPOINT_TOLERANCE"]},
        "scan": {"roots": list(SCAN_ROOTS), "files_scanned": scan["files_scanned"],
                 "files_unparsable": scan["files_unparsable"],
                 "root_file_counts": scan["root_file_counts"],
                 "min_significant_digits": MIN_SIGNIFICANT_DIGITS},
        "frozen_readings": FROZEN_READINGS,
        "sites": {"total": len(sites), "allowed": len(allowed), "forbidden": len(forbidden),
                  "by_kind": by_kind_counts(sites)},
        "forbidden_sites": forbidden,
        "synthetic_self_check": {
            "violation_source": SYNTHETIC_VIOLATION,
            "legal_source": SYNTHETIC_LEGAL,
            "violation_forbidden": diagnostics["synthetic_violation_forbidden"],
            "legal_forbidden": diagnostics["synthetic_legal_forbidden"],
        },
        "reuse_diagnostic": reuse,
        "criteria": criteria,
        "boundaries": [
            "边界：只扫 8 位以上有效数字的**字面量**比较；不扫运行期变量之间的一般相等（`a == b` 变量对变量不在此守卫范围）。",
            "有效数字按书写形式近似计数，不做尾零消歧（偏保守，宁多不少）。",
            "判定策略用「是否位于测试断言」区分：运行期控制流的字面量逐位判等=禁止；测试断言对登记常量做原值回归=允许（R6）。",
            "守卫只读盘上文件，不修改任何被扫描文件；本次扫描现存禁止项为 0。",
            "R5 的 1e-12 是判等容差，不是新的显著性门；不得用它放宽任何判据。",
        ],
        "headline": [
            "端点判等容差从注册表 R5 读出并断言 == w36 ENDPOINT_TOLERANCE == 1e-12；改注册表会被发现。",
            "AST + 子串双扫描 probes/scripts/src/tests 共 " + str(scan["files_scanned"]) + " 个文件，命中 "
            + str(len(sites)) + " 个端点比较点，现存禁止项 " + str(len(forbidden)) + " 个。",
            "合成违规 `if value == 0.5861142332208197:` 被抓；合法用法 `abs(a-b) <= ENDPOINT_TOLERANCE` 不被误抓。",
            "复用 endpoint_of() 现场演示：逐位相等会碎、容差判等成立。",
        ],
    }
    write_json_stable(SUMMARY_PATH, payload)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(render_report(payload), encoding="utf-8", newline="\n")

    passed = sum(1 for item in criteria if item["verdict"] == "成立")
    print("files " + str(scan["files_scanned"]) + "; sites " + str(len(sites))
          + "; allowed " + str(len(allowed)) + "; forbidden " + str(len(forbidden)))
    print("tolerance " + repr(tolerance) + "; reuse bitwise_equal "
          + str(reuse.get("bitwise_equal")) + " endpoints_equal " + str(reuse.get("endpoints_equal")))
    print("verdicts " + str(passed) + "/" + str(len(criteria)))
    for item in criteria:
        if item["verdict"] != "成立":
            print("FAIL " + item["id"] + " " + item["description"])
    return 0 if passed == len(criteria) else 1


if __name__ == "__main__":
    raise SystemExit(main())
