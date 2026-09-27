"""Week 18 lane visual pack (W18-VIS).

Every number plotted here is re-read at run time from the lane's own committed
summary JSON; nothing in this file fits a model, opens the network, touches a
frozen scoreboard or re-derives a lane result.  The literals in PINNED exist
only so --check can assert the frozen anchors still read back unchanged.

Figures (written into probes/artifacts/):
  w18_multiseed_endpoint.png       P1: four arms x five seeds, seed 42 highlighted,
                                   the cross-seed mean endpoint and the 0.60 line
  w18_hyperparameter_grid.png      P0: max_depth x n_estimators grouped-R2 grid,
                                   frozen cell vs best cell
  w18_onsager_delta.png            P2: Onsager analytic form vs the direct and
                                   delta heads, plus the high-epsilon gate
  w18_conformer_flexibility.png    P3: lever4 vs lever4+flexibility, per seed
  w18_log_scale_calibration.png    P6: original-scale R2 vs log space, raw and
                                   isotonic-calibrated, plus the sorting deltas
  w18_viscosity_row_level.png      eta row-level unfreeze: three pools against
                                   the 0.15 MAE gate
  w18_applicability_domain.png     the in-domain / out-of-domain second board
  w18_scoreboard.png               one-page verdict board for every W18 lane

Labels are Chinese when a CJK font is installed and English otherwise, so the
PNGs never ship tofu boxes.
"""

from __future__ import annotations

import argparse
import json
import re
import textwrap
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import Patch

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "probes/artifacts"

VISCOSITY_SUMMARY = ROOT / "probes/viscosity_row_level_summary.json"
DOMAIN_SUMMARY = ROOT / "probes/dielectric_applicability_domain_summary.json"
FLEX_SUMMARY = ROOT / "probes/dielectric_conformer_flexibility_summary.json"
FLEX_PLACEBO_SUMMARY = ROOT / "probes/dielectric_conformer_flexibility_placebo_summary.json"
GRID_SUMMARY = ROOT / "probes/dielectric_hyperparameter_grid_summary.json"
ONSAGER_SUMMARY = ROOT / "probes/dielectric_onsager_delta_w18_summary.json"
LOGSCALE_SUMMARY = ROOT / "probes/dielectric_log_scale_calibration_summary.json"
UNIMOL_SUMMARY = ROOT / "probes/dielectric_unimol_embedding_summary.json"
ENDPOINT_SUMMARY = ROOT / "probes/dielectric_multiseed_endpoint_summary.json"

FIG_ENDPOINT = "w18_multiseed_endpoint.png"
FIG_GRID = "w18_hyperparameter_grid.png"
FIG_ONSAGER = "w18_onsager_delta.png"
FIG_FLEX = "w18_conformer_flexibility.png"
FIG_LOGSCALE = "w18_log_scale_calibration.png"
FIG_VISCOSITY = "w18_viscosity_row_level.png"
FIG_DOMAIN = "w18_applicability_domain.png"
FIG_SCOREBOARD = "w18_scoreboard.png"
FIGURE_FILES = (
    FIG_ENDPOINT,
    FIG_GRID,
    FIG_ONSAGER,
    FIG_FLEX,
    FIG_LOGSCALE,
    FIG_VISCOSITY,
    FIG_DOMAIN,
    FIG_SCOREBOARD,
)

INK = "#3a3a3a"
GRID = "#d8d8d8"
GREEN = "#2f7d4f"
RED = "#a3320b"
AMBER = "#c07d1a"
BLUE = "#3f6fbf"
TEAL = "#2a8f8f"
PURPLE = "#7b5ea7"
GREY = "#b9c4cc"
LIGHT = "#e6e9ec"

FROZEN_BASELINE = 0.4091179943351143
FROZEN_HEADLINE = 0.4766400383507876
FROZEN_SINGLE_REPRESENTATION = 0.6080587938801277
PASS_TARGET_R2 = 0.60
VISCOSITY_MAE_GATE = 0.15

ARM_LABELS = {
    "baseline": ("baseline", "基线"),
    "plus_lever4": ("lever4", "lever4"),
    "plus_lever8": ("lever8", "lever8"),
    "plus_both": ("lever4+lever8", "lever4+lever8"),
    "xgb_reference": ("frozen head", "冻结头"),
    "reference_lever4": ("lever4 ref", "lever4 参照"),
    "plus_flexibility": ("lever4+flex", "lever4+柔性"),
    "flexibility_only": ("flex only", "只柔性"),
    "log_space_raw": ("log raw", "log 无校准"),
    "log_space_isotonic": ("log isotonic", "log+保序"),
    "baseline_direct": ("direct", "直接拟合"),
    "onsager_analytic_only": ("Onsager only", "仅 Onsager"),
    "onsager_delta_xgb": ("Onsager+delta", "Onsager 残差"),
    "onsager_delta_recomputed": ("delta recomputed", "残差重算"),
}

CJK_CANDIDATES = (
    "Microsoft YaHei",
    "SimHei",
    "Noto Sans CJK SC",
    "Source Han Sans SC",
    "WenQuanYi Zen Hei",
)


def pick_cjk_font() -> str | None:
    have = {font.name for font in font_manager.fontManager.ttflist}
    for name in CJK_CANDIDATES:
        if name in have:
            return name
    return None


CJK_FONT = pick_cjk_font()
ZH = CJK_FONT is not None


def t(zh: str, en: str) -> str:
    return zh if ZH else en


# Data-borne strings can carry arrows the CJK font lacks (Microsoft YaHei has no
# U+21D2); swap them for ASCII so a long headline never ships as tofu boxes.
_GLYPH_SWAPS = ((chr(8658), "->"), (chr(8810), "<<"), (chr(8811), ">>"))


def plain(text) -> str:
    out = str(text)
    for source, target in _GLYPH_SWAPS:
        out = out.replace(source, target)
    return out


def configure_fonts() -> None:
    families = [CJK_FONT] if CJK_FONT else []
    families.append("DejaVu Sans")
    plt.rcParams["font.family"] = "sans-serif"
    plt.rcParams["font.sans-serif"] = families
    plt.rcParams["axes.unicode_minus"] = False


def style(panel) -> None:
    panel.grid(True, color=GRID, linewidth=0.7, alpha=0.8)
    panel.set_axisbelow(True)
    for spine in panel.spines.values():
        spine.set_color("#b0b0b0")
    panel.tick_params(colors=INK)
    panel.yaxis.label.set_color(INK)
    panel.xaxis.label.set_color(INK)
    if panel.get_title():
        panel.title.set_color(INK)


def num(value):
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def arm_label(arm: str) -> str:
    pair = ARM_LABELS.get(arm)
    if pair is not None:
        return t(pair[1], pair[0])
    match = re.match(r"^hp_d(\d+)_n(\d+)", str(arm))
    if match:
        return "hp d" + match.group(1) + "xn" + match.group(2)
    return arm


def maybe_json(path: Path):
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def load_inputs() -> dict:
    return {
        "viscosity": maybe_json(VISCOSITY_SUMMARY),
        "domain": maybe_json(DOMAIN_SUMMARY),
        "flex": maybe_json(FLEX_SUMMARY),
        "unimol": maybe_json(UNIMOL_SUMMARY),
        "flex_placebo": maybe_json(FLEX_PLACEBO_SUMMARY),
        "grid": maybe_json(GRID_SUMMARY),
        "onsager": maybe_json(ONSAGER_SUMMARY),
        "logscale": maybe_json(LOGSCALE_SUMMARY),
        "endpoint": maybe_json(ENDPOINT_SUMMARY),
    }


def _bar_labels(panel, xs, values, fmt="{:.3f}", dy=0.006, colour=INK, size=9.0) -> None:
    for x, value in zip(xs, values):
        if value is None:
            continue
        if value < 0:
            panel.text(x, value - dy, fmt.format(value), ha="center", va="top",
                       fontsize=size, color=colour)
        else:
            panel.text(x, value + dy, fmt.format(value), ha="center", va="bottom",
                       fontsize=size, color=colour)


def _rule(panel, y, colour, text, linestyle="--", lw=1.1, x=0.995, va="bottom",
          ha="right", size=8.8) -> None:
    panel.axhline(y, color=colour, linestyle=linestyle, linewidth=lw)
    panel.text(x, y, " " + text, color=colour, fontsize=size, ha=ha, va=va,
               transform=panel.get_yaxis_transform())


def _no_data(panel, name: str) -> None:
    panel.axis("off")
    panel.text(0.5, 0.5, t("该 lane 尚未落盘：" + name, "lane not landed yet: " + name),
               ha="center", va="center", fontsize=13, color=RED)


# ---------------------------------------------------------------------------
# P1  multiple-seed endpoint
# ---------------------------------------------------------------------------
def fig_endpoint(data, path) -> bool:
    ep = data.get("endpoint")
    if ep is None:
        return False
    endpoints = list(ep["endpoints"])
    arms = [str(row["arm"]) for row in endpoints]
    seed_order = [str(s) for s in ep["contract"]["seeds"]]
    anchor_seed = str(ep["contract"]["anchor_seed"])
    target = float(ep.get("target_r2", PASS_TARGET_R2))
    best = ep.get("best_arm", {})
    best_arm = str(best.get("arm", ""))

    fig, panel = plt.subplots(figsize=(12.4, 6.8))
    xs = list(range(len(arms)))
    span = max(len(seed_order) - 1, 1)
    for xi, row in zip(xs, endpoints):
        values = row.get("seed_values", {})
        for k, seed in enumerate(seed_order):
            value = num(values.get(seed))
            if value is None:
                continue
            offset = (k - span / 2.0) * 0.085
            is_anchor = seed == anchor_seed
            panel.scatter(
                [xi + offset], [value],
                s=95 if is_anchor else 52,
                facecolor=(AMBER if is_anchor else "white"),
                edgecolor=(RED if is_anchor else BLUE),
                linewidth=1.5, zorder=5,
            )
            if is_anchor:
                panel.annotate(
                    t("seed 42（单点抽到的高分）", "seed 42 (the lucky single draw)"),
                    (xi + offset, value), textcoords="offset points",
                    xytext=(-6, 11), ha="center", fontsize=9, color=RED, zorder=6,
                )
        mean = num(row.get("cross_seed_mean"))
        sd = num(row.get("cross_seed_sd")) or 0.0
        if mean is not None:
            panel.errorbar([xi], [mean], yerr=[sd], fmt="D", markersize=9,
                           color=GREEN, ecolor=GREEN, elinewidth=1.6, capsize=6,
                           zorder=7)
            panel.text(xi + 0.30, mean, format(mean, ".4f"), fontsize=10.5,
                       color=GREEN, va="center", ha="left", zorder=7)

    _rule(panel, target, GREEN, t("0.60 目标线", "0.60 target"))
    _rule(panel, FROZEN_HEADLINE, "#8a8f95",
          t("冻结头条 0.4766", "frozen headline 0.4766"), linestyle=":", va="top")
    _rule(panel, FROZEN_BASELINE, "#8a8f95",
          t("冻结基线 0.4091", "frozen baseline 0.4091"), linestyle=":", va="top")

    panel.set_xticks(xs)
    panel.set_xticklabels([arm_label(arm) for arm in arms], fontsize=10.5)
    panel.set_ylabel(t("分组 R²（跨种子端点）", "grouped R2 (cross-seed endpoint)"))
    met = t("达到", "met") if ep.get("target_met_cross_seed") else t("未达到", "NOT met")
    panel.set_title(
        t("P1 多种子端点升级：五种子散点 + 跨种子均值端点（最佳臂 "
          + arm_label(best_arm) + " = " + format(float(best.get("cross_seed_mean", 0.0)), ".4f")
          + "；0.60 " + met + "）",
          "P1 multi-seed endpoint: five seeds + cross-seed mean (best arm "
          + arm_label(best_arm) + " = " + format(float(best.get("cross_seed_mean", 0.0)), ".4f")
          + "; 0.60 " + met + ")"),
        fontsize=11.5,
    )
    handles = [
        Patch(facecolor="white", edgecolor=BLUE, label=t("其他四个种子", "the other four seeds")),
        Patch(facecolor=AMBER, edgecolor=RED, label=t("seed 42（锚点，唯一被报告的旧单点）",
                                                      "seed 42 (anchor, the old single point)")),
        Patch(facecolor=GREEN, edgecolor=GREEN, label=t("跨种子均值端点", "cross-seed mean endpoint")),
    ]
    panel.legend(handles=handles, frameon=False, fontsize=9.5, loc="lower right")
    panel.set_ylim(min(FROZEN_BASELINE - 0.03, 0.34), 0.66)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return True


# ---------------------------------------------------------------------------
# P0  hyperparameter grid
# ---------------------------------------------------------------------------
def _grid_rows(data):
    g = data.get("grid")
    if g is None:
        return None
    return g


def fig_grid(data, path) -> bool:
    g = _grid_rows(data)
    if g is None:
        return False
    rows = list(g["cross_seed"])
    frozen = dict(g["contract"]["frozen_hyperparameters"])
    ref_arm = str(g["answers"]["reference_arm"])
    best_arm = str(g["answers"]["best_arm"])

    fixed = {"learning_rate": 0.05, "min_child_weight": 1, "subsample": 0.8,
             "colsample_bytree": 0.8}

    def params_of(row):
        return dict(row.get("params", {}))

    ref_block = next((row.get("block") for row in rows if str(row["arm"]) == ref_arm), None)
    selected = [row for row in rows
                if all(abs(float(params_of(row).get(k, -1.0)) - v) < 1e-9
                       for k, v in fixed.items())
                and (ref_block is None or row.get("block") == ref_block)]
    depths = sorted({int(params_of(r)["max_depth"]) for r in selected})
    estimators = sorted({int(params_of(r)["n_estimators"]) for r in selected})

    fig, panel = plt.subplots(figsize=(11.4, 6.4))
    if len(depths) >= 2 and len(estimators) >= 2 and len(selected) == len(depths) * len(estimators):
        lookup = {(int(params_of(r)["max_depth"]), int(params_of(r)["n_estimators"])): r
                  for r in selected}
        matrix = [[num(lookup[(d, n)]["r2_seed_mean"]) for n in estimators] for d in depths]
        values = [v for line in matrix for v in line]
        image = panel.imshow(matrix, cmap="viridis", aspect="auto",
                             vmin=min(values), vmax=max(values))
        panel.set_xticks(range(len(estimators)))
        panel.set_xticklabels([str(n) for n in estimators])
        panel.set_yticks(range(len(depths)))
        panel.set_yticklabels([str(d) for d in depths])
        panel.set_xlabel(t("n_estimators（树数）", "n_estimators (trees)"))
        panel.set_ylabel(t("max_depth（树深）", "max_depth"))
        panel.grid(False)
        for i, d in enumerate(depths):
            for j, n in enumerate(estimators):
                value = matrix[i][j]
                if value is None:
                    continue
                panel.text(j, i, format(value, ".4f"), ha="center", va="center",
                           fontsize=10, color="white" if value < (min(values) + max(values)) / 2 else "#20202a")
        fd = int(frozen["max_depth"])
        fn = int(frozen["n_estimators"])
        if fd in depths and fn in estimators:
            panel.add_patch(plt.Rectangle((estimators.index(fn) - 0.5, depths.index(fd) - 0.5),
                                          1, 1, fill=False, edgecolor="white", linewidth=3))
            panel.text(estimators.index(fn), depths.index(fd) - 0.34,
                       t("冻结超参", "frozen"), ha="center", va="bottom",
                       fontsize=9.5, color="white", weight="bold")
        best_value = num(next(r for r in rows if str(r["arm"]) == best_arm)["r2_seed_mean"])
        bd = int(next(r for r in rows if str(r["arm"]) == best_arm)["params"]["max_depth"])
        bn = int(next(r for r in rows if str(r["arm"]) == best_arm)["params"]["n_estimators"])
        if bd in depths and bn in estimators:
            panel.add_patch(plt.Rectangle((estimators.index(bn) - 0.5, depths.index(bd) - 0.5),
                                          1, 1, fill=False, edgecolor=RED, linewidth=2.4,
                                          linestyle="--"))
        bar = fig.colorbar(image, ax=panel, fraction=0.045, pad=0.02)
        bar.set_label(t("分组 R²（跨种子均值）", "grouped R2 (cross-seed mean)"))
        panel.set_title(
            t("P0 稠密物理配置超参网格：max_depth x n_estimators（其余固定 lr=0.05 / mcw=1 / ss=0.8 / cs=0.8）"
              "；白框=冻结超参，红框=网格最优 " + format(best_value if best_value is not None else float("nan"), ".4f"),
              "P0 dense-physical hyperparameter grid: max_depth x n_estimators (lr=0.05 / mcw=1 / ss=0.8 / cs=0.8); "
              "white=frozen, red=grid best " + format(best_value if best_value is not None else float("nan"), ".4f")),
            fontsize=11.0,
        )
    else:
        ordered = sorted(rows, key=lambda r: (num(r["r2_seed_mean"]) or -9.9))
        names = [str(r["arm"]) for r in ordered]
        vals = [num(r["r2_seed_mean"]) or 0.0 for r in ordered]
        colours = [GREEN if str(r["arm"]) == best_arm else (GREY if str(r["arm"]) == ref_arm else BLUE)
                   for r in ordered]
        panel.barh(range(len(names)), vals, color=colours, height=0.72)
        panel.set_yticks(range(len(names)))
        panel.set_yticklabels([arm_label(n) for n in names], fontsize=8.0)
        panel.set_xlabel(t("分组 R²（跨种子均值）", "grouped R2 (cross-seed mean)"))
        panel.set_xlim(min(0.0, min(vals) - 0.03) if vals else 0.0,
                       (max(vals) + 0.03) if vals else 1.0)
        panel.axvline(FROZEN_SINGLE_REPRESENTATION, color="#8a8f95",
                      linestyle=":", linewidth=1.1)
        panel.text(FROZEN_SINGLE_REPRESENTATION, 0.995,
                   t(" 单表示锚点 " + format(FROZEN_SINGLE_REPRESENTATION, ".4f"),
                     " single-rep anchor " + format(FROZEN_SINGLE_REPRESENTATION, ".4f")),
                   color="#6d7278", fontsize=8.4, ha="right", va="top",
                   transform=panel.get_xaxis_transform())
        panel.set_title(
            t("P0 超参网格（网格不完整，改画逐臂读数）",
              "P0 hyperparameter grid (incomplete grid: per-arm readout)"), fontsize=11.5)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return True


# ---------------------------------------------------------------------------
# P2  Onsager delta learning
# ---------------------------------------------------------------------------
def fig_onsager(data, path) -> bool:
    o = data.get("onsager")
    if o is None:
        return False
    dec = o["decisions"]
    keys = [k for k in ("endpoint_reference_direct", "endpoint_onsager_analytic_only",
                        "endpoint_onsager_delta_xgb", "endpoint_onsager_delta_recomputed")
            if k in dec and num(dec[k]) is not None]
    values = [num(dec[k]) for k in keys]
    labels = {
        "endpoint_reference_direct": ("direct head", "直接拟合头"),
        "endpoint_onsager_analytic_only": ("Onsager analytic", "Onsager 解析式"),
        "endpoint_onsager_delta_xgb": ("Onsager + delta", "Onsager 残差学习"),
        "endpoint_onsager_delta_recomputed": ("delta recomputed", "残差重算"),
    }

    fig, panels = plt.subplots(1, 2, figsize=(13.6, 6.2),
                               gridspec_kw={"width_ratios": [1.15, 1.0]})
    left, right = panels

    xs = list(range(len(keys)))
    colours = [GREY if k == "endpoint_reference_direct" else BLUE for k in keys]
    left.bar(xs, values, color=colours, width=0.62)
    _bar_labels(left, xs, values)
    left.set_xticks(xs)
    left.set_xticklabels([t(*labels[k]) if k in labels else k for k in keys],
                         fontsize=9.5, rotation=12, ha="right")
    left.set_ylabel(t("分组 R²（跨种子端点）", "grouped R2 (cross-seed endpoint)"))
    _rule(left, PASS_TARGET_R2, GREEN, t("0.60 目标线", "0.60 target"))
    footer = textwrap.fill(plain(o.get("headline_text", "")), 148)
    left.set_title(
        t("P2 Onsager/Kirkwood 残差学习：端点对比（verdict = " + str(dec.get("verdict")) + "）",
          "P2 Onsager/Kirkwood delta learning: endpoint comparison (verdict = "
          + str(dec.get("verdict")) + ")"),
        fontsize=11.0)
    finite = [v for v in values if v is not None]
    left.axhline(0.0, color="#9aa0a6", linewidth=0.9)
    left.set_ylim(min(0.0, min(finite)) - 0.10,
                  max(finite + [PASS_TARGET_R2, 0.0]) + 0.12)

    ons = o.get("onsager", {})
    total_high = num(ons.get("scored_rows_above_60"))
    covered = num(ons.get("scored_rows_above_60_covered_by_onsager"))
    if total_high is not None and covered is not None:
        right.bar([0, 1], [total_high, covered], color=[GREY, RED], width=0.5)
        _bar_labels(right, [0, 1], [total_high, covered], fmt="{:.0f}")
        right.set_xticks([0, 1])
        right.set_xticklabels([t("ε>60 的评分行", "scored rows with eps>60"),
                               t("Onsager 解析式也报 ε>60", "Onsager also says eps>60")],
                              fontsize=10.0)
        right.set_ylabel(t("行数", "rows"))
        right.set_title(
            t("Onsager 形式抓不住高 ε 尾部：解析式单独漏掉的高 ε 行",
              "The analytic Onsager form misses the high-epsilon tail"),
            fontsize=11.0)
        right.set_ylim(0, max(total_high, 1) * 1.25)
    else:
        _no_data(right, ONSAGER_SUMMARY.name)

    if footer:
        fig.text(0.5, 0.012, footer, ha="center", va="bottom",
                 fontsize=8.4, color="#555555")
    fig.tight_layout(rect=(0, 0.115 if footer else 0.03, 1, 1))
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return True


# ---------------------------------------------------------------------------
# P3  conformer flexibility
# ---------------------------------------------------------------------------
def fig_flex(data, path) -> bool:
    c = data.get("flex")
    if c is None:
        return False
    rows = list(c["seed_rows"])
    seed_order = [int(s) for s in c["contract"]["seeds"]]
    by_arm = {}
    for row in rows:
        by_arm.setdefault(str(row["arm"]), {})[int(row["seed"])] = row
    ref_arm = "reference_lever4"
    plus_arm = "plus_flexibility"
    if ref_arm not in by_arm or plus_arm not in by_arm:
        return False

    fig, panels = plt.subplots(1, 2, figsize=(13.4, 6.2),
                               gridspec_kw={"width_ratios": [2.0, 1.0]})
    left, right = panels

    xs = list(range(len(seed_order)))
    width = 0.36
    ref_vals = [num(by_arm[ref_arm][s]["r2_mean"]) for s in seed_order]
    plus_vals = [num(by_arm[plus_arm][s]["r2_mean"]) for s in seed_order]
    left.bar([x - width / 2 for x in xs], ref_vals, width=width, color=GREY,
             label=t("lever4（只用构象均值）", "lever4 (conformer mean only)"))
    left.bar([x + width / 2 for x in xs], plus_vals, width=width, color=BLUE,
             label=t("lever4 + 构象方差/柔性列", "lever4 + conformer variance"))
    for x, value in zip(xs, ref_vals):
        left.text(x - width / 2, value + 0.004, format(value, ".3f"), ha="center",
                  fontsize=8.6, color=INK)
    for x, value in zip(xs, plus_vals):
        left.text(x + width / 2, value + 0.004, format(value, ".3f"), ha="center",
                  fontsize=8.6, color=BLUE)
    left.set_xticks(xs)
    left.set_xticklabels(["seed " + str(s) for s in seed_order])
    left.set_ylabel(t("分组 R²（逐种子）", "grouped R2 (per seed)"))
    _rule(left, PASS_TARGET_R2, GREEN, t("0.60 目标线", "0.60 target"))
    delta = num(c.get("delta_plus_minus_reference"))
    positives = c.get("seeds_with_a_positive_delta")
    left.set_title(
        t("P3 构象方差特征：逐种子 R²（Δ均值 = "
          + format(delta if delta is not None else float("nan"), "+.4f")
          + "；正向种子 " + str(positives) + "/" + str(len(seed_order))
          + "；verdict = " + str(c["decision"]["verdict"]) + "）",
          "P3 conformer variance: per-seed R2 (delta mean = "
          + format(delta if delta is not None else float("nan"), "+.4f")
          + "; positive seeds " + str(positives) + "/" + str(len(seed_order))
          + "; verdict = " + str(c["decision"]["verdict"]) + ")"),
        fontsize=11.0)
    left.legend(frameon=False, fontsize=9.5, loc="lower right")
    left.set_ylim(0.35, 0.70)

    cross = c.get("cross_seed", {})
    placebo = (c.get("placebo") or {}).get("cross_seed", {})
    names = [ref_arm, plus_arm]
    pos = list(range(len(names)))
    cross_vals = [num(cross.get(a)) for a in names]
    placebo_vals = [num(placebo.get(a)) for a in names]
    right.bar([p - 0.19 for p in pos], cross_vals, width=0.36, color=TEAL,
              label=t("真实标签", "real labels"))
    if all(v is not None for v in placebo_vals):
        right.bar([p + 0.19 for p in pos], placebo_vals, width=0.36, color=LIGHT,
                  edgecolor=TEAL, hatch="//", label=t("安慰剂（洗牌标签）", "placebo (shuffled)"))
    _bar_labels(right, [p - 0.19 for p in pos], cross_vals, size=9.0)
    if all(v is not None for v in placebo_vals):
        _bar_labels(right, [p + 0.19 for p in pos], placebo_vals, size=9.0, colour=TEAL)
    right.set_xticks(pos)
    right.set_xticklabels([arm_label(a) for a in names], fontsize=9.5)
    right.set_ylabel(t("跨种子均值 R²", "cross-seed mean R2"))
    right.set_title(t("跨种子均值 vs 安慰剂", "cross-seed mean vs placebo"), fontsize=11.0)
    right.legend(frameon=False, fontsize=9.0)
    right.set_ylim(0.35, 0.68)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return True


# ---------------------------------------------------------------------------
# P6  log space + isotonic calibration
# ---------------------------------------------------------------------------
def fig_logscale(data, path) -> bool:
    l = data.get("logscale")
    if l is None:
        return False
    arms = [str(a) for a in l["contract"]["arms"]]
    cross = l["cross_seed"]
    placebo = (l.get("placebo") or {}).get("cross_seed", {}) or {}
    gains = l.get("secondary_gains", {})
    decision = l.get("decision", {})

    buckets = {}
    for row in l.get("seed_rows", []):
        buckets.setdefault(str(row["arm"]), []).append(num(row.get("log_r2_mean")))
    log_mean = {}
    for arm, values in buckets.items():
        clean = [value for value in values if value is not None]
        log_mean[arm] = (sum(clean) / len(clean)) if clean else None
    if not any(value is not None for value in log_mean.values()):
        log_mean = {}

    fig, panels = plt.subplots(1, 2, figsize=(13.8, 6.3),
                               gridspec_kw={"width_ratios": [1.3, 1.0]})
    left, right = panels

    xs = list(range(len(arms)))
    width = 0.27
    orig = [num(cross.get(a)) for a in arms]
    logv = [log_mean.get(a) for a in arms]
    place = [num(placebo.get(a)) for a in arms]
    left.bar([x - width for x in xs], orig, width=width,
             color=[GREY if a == "reference_lever4" else BLUE for a in arms],
             label=t("原尺度 R²（exp 之后）", "original-scale R2"))
    if log_mean:
        left.bar(xs, logv, width=width,
                 color=[GREY if a == "reference_lever4" else TEAL for a in arms],
                 label=t("log 空间 R²（exp 之前）", "log-space R2 (before exp)"))
    if all(value is not None for value in place):
        left.bar([x + width for x in xs], place, width=width, color=LIGHT, edgecolor=AMBER,
                 hatch="//", label=t("安慰剂（原尺度）", "placebo (original scale)"))
    _bar_labels(left, [x - width for x in xs], orig, size=8.8)
    if log_mean:
        _bar_labels(left, xs, logv, size=8.8, colour=TEAL)
    if all(value is not None for value in place):
        _bar_labels(left, [x + width for x in xs], place, size=8.8, colour=AMBER)

    left.set_xticks(xs)
    left.set_xticklabels([arm_label(a) for a in arms], fontsize=9.6)
    left.set_ylabel(t("分组 R²", "grouped R2"))
    _rule(left, PASS_TARGET_R2, GREEN, t("0.60 目标线", "0.60 target"))
    top = max([v for v in orig + logv + place if v is not None] + [PASS_TARGET_R2]) + 0.16
    left.set_ylim(0.0, top)
    left.set_title(
        t("P6 log 空间 + 保序校准：log 空间 R² 反而更高，回到原尺度就掉下来（verdict = "
          + str(decision.get("verdict")) + "）",
          "P6 log space + isotonic: log-space R2 rises, the original scale falls back (verdict = "
          + str(decision.get("verdict")) + ")"),
        fontsize=10.8)
    legend_handles = [Patch(facecolor=BLUE, label=t("原尺度 R²（exp 之后）", "original-scale R2"))]
    if log_mean:
        legend_handles.append(Patch(facecolor=TEAL,
                                   label=t("log 空间 R²（exp 之前）", "log-space R2 (before exp)")))
    if all(value is not None for value in place):
        legend_handles.append(Patch(facecolor=LIGHT, edgecolor=AMBER, hatch="//",
                                   label=t("安慰剂（原尺度）", "placebo (original scale)")))
    left.legend(handles=legend_handles, frameon=False, fontsize=8.8, loc="upper left")

    gain_specs = [
        ("mae_improvement", t("MAE 改善", "MAE gain"), decision.get("mae_partial_margin")),
        ("spearman_improvement", t("Spearman 改善", "Spearman gain"),
         decision.get("spearman_partial_margin")),
        ("auc_gt30_improvement", t("AUC(>30) 改善", "AUC(>30) gain"),
         decision.get("auc_partial_margin")),
    ]
    gxs = list(range(len(gain_specs)))
    gvals = [num(gains.get(key)) for key, _, _ in gain_specs]
    right.bar(gxs, gvals, color=[AMBER if (value is not None and value > 0) else RED for value in gvals],
              width=0.55)
    _bar_labels(right, gxs, gvals, fmt="{:+.4f}")
    for index, (_, _, margin) in enumerate(gain_specs):
        if margin is None:
            continue
        right.hlines(num(margin), index - 0.34, index + 0.34, color=GREEN, linewidth=1.8)
        right.text(index + 0.36, num(margin), format(num(margin), ".3f"), fontsize=8.4,
                   color=GREEN, va="center", ha="left")
    right.axhline(0.0, color="#8a8f95", linewidth=1.0)
    finite_gains = [value for value in gvals if value is not None]
    margins = [num(m) for _, _, m in gain_specs if num(m) is not None]
    if finite_gains:
        lo = min(finite_gains + [0.0])
        hi = max(finite_gains + margins + [0.0])
        span = (hi - lo) or 1.0
        right.set_ylim(lo - 0.22 * span, hi + 0.18 * span)
    right.set_xticks(gxs)
    right.set_xticklabels([label for _, label, _ in gain_specs], fontsize=9.4)
    right.set_ylabel(t("相对 lever4 参照的改善", "gain vs lever4 reference"))
    right.set_title(
        t("次级口径：保序校准只动了排序，没动原尺度 R²"
          + ("（次级门槛已满足）" if decision.get("secondary_partial_rule_satisfied")
             else "（次级门槛未满足）"),
          "Secondary readouts: ordering only, the original-scale R2 is untouched"),
        fontsize=10.5)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return True

# ---------------------------------------------------------------------------
# eta  row-level unfreeze
# ---------------------------------------------------------------------------
def fig_viscosity(data, path) -> bool:
    v = data.get("viscosity")
    if v is None:
        return False
    readings = v["readings"]
    pools = ["family_level", "thaw_only", "row_level"]
    gate = float(v["primary_gate"]["threshold"])

    fig, panels = plt.subplots(1, 2, figsize=(13.4, 6.2),
                               gridspec_kw={"width_ratios": [1.25, 1.0]})
    left, right = panels

    xs = list(range(len(pools)))
    mae = [num(readings[p]["group_key"]["mae_log10_cP"]) for p in pools]
    left.bar(xs, mae, color=[GREY, AMBER, BLUE], width=0.58)
    _bar_labels(left, xs, mae, fmt="{:.4f}")
    _rule(left, gate, GREEN, t("0.15 过门线", "0.15 gate"), x=0.36, ha="center")
    for x, value in zip(xs, mae):
        if value is None:
            continue
        left.text(x, value / 2.0, "缺口 " + format(value - gate, "+.4f"),
                  ha="center", va="center", fontsize=9.6,
                  color=("white" if x == len(pools) - 1 else INK))
    left.set_xticks(xs)
    left.set_xticklabels([t("族级（冻结基线）", "family (frozen)"),
                          t("只加 86 行解冻", "+86 thawed rows"),
                          t("行级（+483 Pa*s 行）", "row-level (+483 Pa*s rows)")],
                         fontsize=9.2)
    left.set_ylabel(t("group_key 划分 log10(cP) MAE", "group_key log10(cP) MAE"))
    gap_family = (mae[0] - gate) if mae[0] is not None else None
    gap_row = (mae[-1] - gate) if mae[-1] is not None else None
    gap_text = (format(gap_family, "+.4f") + " -> " + format(gap_row, "+.4f")
                if gap_family is not None and gap_row is not None else "n/a")
    left.set_ylim(0.0, max(value for value in mae if value is not None) * 1.17)
    left.set_title(
        t("W18 η 行级解冻：三池 group_key MAE（过门线 " + format(gate, ".2f")
          + "；缺口 " + gap_text + "；verdict = " + str(v.get("verdict")) + "）",
          "W18 eta row-level unfreeze: group_key MAE per pool (gate "
          + format(gate, ".2f") + "; gaps " + gap_text + "; verdict = "
          + str(v.get("verdict")) + ")"),
        fontsize=11.0)

    r2 = [num(readings[p]["group_key"]["r2_log10_cP"]) for p in pools]
    rand = [num(readings[p]["random_row"]["mae_log10_cP"]) for p in pools]
    width = 0.34
    right.bar([x - width / 2 for x in xs], r2, width=width, color=PURPLE,
              label=t("group_key R²（副轴）", "group_key R2"))
    right.set_ylabel(t("group_key R²", "group_key R2"), color=PURPLE)
    right.set_ylim(0.70, 0.82)
    right.tick_params(axis="y", colors=PURPLE)
    twin = right.twinx()
    twin.bar([x + width / 2 for x in xs], rand, width=width, color=TEAL,
             label=t("random_row MAE", "random_row MAE"))
    twin.set_ylabel(t("random_row log10(cP) MAE", "random_row log10(cP) MAE"), color=TEAL)
    twin.tick_params(axis="y", colors=TEAL)
    twin.set_ylim(0.0, 0.12)
    _bar_labels(right, [x - width / 2 for x in xs], r2, fmt="{:.4f}", size=8.6, colour=PURPLE)
    _bar_labels(twin, [x + width / 2 for x in xs], rand, fmt="{:.4f}", size=8.6, colour=TEAL)
    right.set_xticks(xs)
    right.set_xticklabels([t("族级", "family"), t("解冻", "thawed"), t("行级", "row-level")],
                          fontsize=9.5)
    right.set_title(t("同池的 R² 与随机行切分口径", "R2 and the random-row split side by side"),
                    fontsize=11.0)
    handles = [Patch(facecolor=PURPLE, label=t("group_key R²", "group_key R2")),
               Patch(facecolor=TEAL, label=t("random_row MAE", "random_row MAE"))]
    right.legend(handles=handles, frameon=False, fontsize=8.8, loc="upper center",
                 bbox_to_anchor=(0.5, -0.11), ncol=2)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return True


# ---------------------------------------------------------------------------
# applicability domain
# ---------------------------------------------------------------------------
def fig_domain(data, path) -> bool:
    d = data.get("domain")
    if d is None:
        return False
    # Cross-seed endpoint, never per_seed[0]: after the five-seed rerun the per_seed list is
    # ordered numerically, so index 0 is seed 7 and the figure would silently switch away from
    # the anchor seed.  The endpoint block is also the object the pinned literal
    # `headline_vs_in_domain.D1_in_domain_r2` reads, so the figure and the pin share one reading.
    rules = d["endpoint"]
    seed_count = len(d.get("per_seed") or []) or 1
    order = [("global", "all", t("全域（无域声明）", "global (no domain)")),
             ("D1", "in_domain", t("D1 域内", "D1 in-domain")),
             ("D1", "out_of_domain", t("D1 域外", "D1 out-of-domain")),
             ("D2", "in_domain", t("D2 域内", "D2 in-domain")),
             ("D2", "out_of_domain", t("D2 域外", "D2 out-of-domain")),
             ("D3", "in_domain", t("D3 域内", "D3 in-domain")),
             ("D3", "out_of_domain", t("D3 域外", "D3 out-of-domain"))]
    labels = [label for _, _, label in order]
    r2 = [num(rules[a][b]["r2_mean"]) for a, b, _ in order]
    mae = [num(rules[a][b]["mae_mean"]) for a, b, _ in order]
    colours = [GREY, BLUE, RED, BLUE, RED, TEAL, RED]

    fig, panels = plt.subplots(1, 2, figsize=(13.8, 6.2),
                               gridspec_kw={"width_ratios": [1.45, 1.0]})
    left, right = panels
    xs = list(range(len(order)))
    left.bar(xs, r2, color=colours, width=0.62)
    _bar_labels(left, xs, [(0.0 if v is None else v) for v in r2])
    left.set_xticks(xs)
    left.set_xticklabels(labels, fontsize=8.8, rotation=18, ha="right")
    left.set_ylabel(t("分组 R²", "grouped R2"))
    _rule(left, PASS_TARGET_R2, GREEN, t("0.60 目标线", "0.60 target"))
    _rule(left, FROZEN_HEADLINE, "#8a8f95", t("冻结头条 0.4766", "frozen headline"), linestyle=":")
    left.axhline(0.0, color="#8a8f95", linewidth=1.0)
    finite = [value for value in r2 if value is not None]
    if finite:
        span = max(finite) - min(finite) + 1e-6
        left.set_ylim(min(finite) - 0.18 * span, max(finite) + 0.14 * span)
    d1_in = num(rules["D1"]["in_domain"]["r2_mean"])
    global_r2 = num(rules["global"]["all"]["r2_mean"])
    higher = d1_in is not None and global_r2 is not None and d1_in > global_r2
    left.set_title(
        t("ε 分域记分牌（跨 " + str(seed_count) + " 种子端点）：域内 R² "
          + ("高于" if higher else "不高于") + "全域；这是第二块记分牌、不替换主记分牌（verdict = "
          + str(d.get("verdict")) + "）",
          "epsilon applicability domain (cross-seed endpoint over " + str(seed_count)
          + " seed(s)): in-domain R2 " + ("sits above" if higher else "does not sit above")
          + " the global reading; a second board that never replaces the main one (verdict = "
          + str(d.get("verdict")) + ")"),
        fontsize=10.4)

    maes = [v if v is not None and v > 0 else 0.01 for v in mae]
    right.bar(xs, maes, color=colours, width=0.62)
    _bar_labels(right, xs, maes, fmt="{:.1f}", colour=INK)
    right.set_ylim(0.0, max(maes) * 1.16)
    right.set_xticks(xs)
    right.set_xticklabels(labels, fontsize=8.8, rotation=18, ha="right")
    right.set_ylabel(t("MAE", "MAE"))
    d3_out = rules["D3"]["out_of_domain"]
    d3_compounds = round(float(d3_out["compounds_mean"]))
    d3_rows = round(float(d3_out["rows_mean"]))
    right.set_title(
        t("同一批分组的 MAE：D3 域外只有 " + str(d3_compounds) + " 个化合物、"
          + str(d3_rows) + " 行，是诊断件",
          "MAE per group: D3 out-of-domain is " + str(d3_compounds) + " compounds / "
          + str(d3_rows) + " rows, a diagnostic only"),
        fontsize=10.4)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return True


# ---------------------------------------------------------------------------
# one-page verdict board
# ---------------------------------------------------------------------------
VERDICT_COLOURS = {
    "confirmed": GREEN,
    "improved": GREEN,
    "endpoint_upgraded": AMBER,
    "partial": AMBER,
    "placebo": "#8a8f95",
    "refuted": RED,
    "not_landed": "#9aa0a6",
    "pending": "#9aa0a6",
    "domain_split_reported": BLUE,
}


def lane_table(data) -> list:
    rows = []

    g = data.get("grid")
    if g is None:
        rows.append(("P0 XGB hyperparameter grid", "not_landed", "-"))
    else:
        a = g["answers"]
        rows.append(("P0 XGB hyperparameter grid", str(g["verdict"]),
                     "best " + format(float(a["best_cross_seed_mean"]), ".4f")
                     + " / best arm " + arm_label(str(a["best_arm"]))))

    ep = data.get("endpoint")
    if ep is None:
        rows.append(("P1 multi-seed endpoint", "not_landed", "-"))
    else:
        best = ep["best_arm"]
        rows.append(("P1 multi-seed endpoint", str(ep["verdict"]),
                     "best " + format(float(best["cross_seed_mean"]), ".4f")
                     + " / 0.60 " + ("met" if ep["target_met_cross_seed"] else "NOT met")))

    o = data.get("onsager")
    if o is None:
        rows.append(("P2 Onsager delta learning", "not_landed", "-"))
    else:
        dec = o["decisions"]
        best_val = num(dec.get("endpoint_" + str(dec["best_arm"])))
        gain_val = num(dec.get("best_improvement"))
        rows.append(("P2 Onsager delta learning", str(dec["verdict"]),
                     "best " + arm_label(str(dec["best_arm"])) + " "
                     + format(best_val if best_val is not None else float("nan"), ".4f")
                     + " / gain "
                     + (format(gain_val, "+.4f") if gain_val is not None else "n/a")))

    c = data.get("flex")
    if c is None:
        rows.append(("P3 conformer variance", "not_landed", "-"))
    else:
        rows.append(("P3 conformer variance", str(c["decision"]["verdict"]),
                     "delta mean " + format(float(c["delta_plus_minus_reference"]), "+.4f")
                     + " / positive seeds " + str(c["seeds_with_a_positive_delta"]) + "/5"))

    u = data.get("unimol")
    if u is None:
        rows.append(("P5 Uni-Mol embedding block", "not_landed", "-"))
    else:
        uc = u["cross_seed"]
        rows.append(("P5 Uni-Mol embedding block", str(u["decision"]["verdict"]),
                     "plus Uni-Mol " + format(float(uc["plus_unimol"]), ".4f")
                     + " / anchor " + format(float(uc["reference_lever4"]), ".4f")))

    l = data.get("logscale")
    if l is None:
        rows.append(("P6 log space + isotonic", "not_landed", "-"))
    else:
        cross = l["cross_seed"]
        rows.append(("P6 log space + isotonic", str(l["decision"]["verdict"]),
                     "lever4 " + format(float(cross["reference_lever4"]), ".4f")
                     + " / isotonic " + format(float(cross["log_space_isotonic"]), ".4f")))

    v = data.get("viscosity")
    if v is None:
        rows.append(("eta row-level unfreeze", "not_landed", "-"))
    else:
        gate = v["primary_gate"]
        rows.append(("eta row-level unfreeze", str(v["verdict"]),
                     "gate " + format(float(gate["threshold"]), ".2f")
                     + " / best " + format(float(gate["row_level_mae"]), ".4f")))

    d = data.get("domain")
    if d is None:
        rows.append(("epsilon applicability domain", "not_landed", "-"))
    else:
        hb = d["headline_vs_in_domain"]
        rows.append(("epsilon applicability domain", str(d["verdict"]),
                     "global " + format(float(hb["global_endpoint_r2"]), ".4f")
                     + " / D1 in " + format(float(hb["D1_in_domain_r2"]), ".4f")))
    return rows


def fig_scoreboard(data, path) -> bool:
    rows = lane_table(data)
    fig, panel = plt.subplots(figsize=(14.2, 7.4))
    panel.axis("off")
    panel.set_xlim(0, 1)
    panel.set_ylim(0, 1)
    panel.text(0.02, 0.955, t("Week 18 记分牌（W18-VIS）", "Week 18 scoreboard (W18-VIS)"),
               fontsize=17, weight="bold", color=INK, transform=panel.transAxes)
    panel.text(0.02, 0.912,
               t("冻结基线 0.4091179943351143 与冻结头条 0.4766400383507876 一个字都不动；"
                 "下表只是各 lane 的自报 verdict。",
                 "Frozen baseline 0.4091179943351143 and frozen headline 0.4766400383507876 stay byte-identical; "
                 "this table only relays each lane self-reported verdict."),
               fontsize=9.6, color="#555555", transform=panel.transAxes)

    top = 0.845
    step = 0.082
    panel.text(0.03, top, t("lane", "lane"), fontsize=11.5, weight="bold", color=INK)
    panel.text(0.44, top, t("verdict", "verdict"), fontsize=11.5, weight="bold", color=INK)
    panel.text(0.60, top, t("关键读数", "key reading"), fontsize=11.5, weight="bold", color=INK)
    panel.plot([0.03, 0.98], [top - 0.016, top - 0.016], color=GRID, linewidth=1.2)

    for index, (lane, verdict, reading) in enumerate(rows):
        y = top - 0.045 - index * step
        if index % 2 == 0:
            panel.add_patch(plt.Rectangle((0.025, y - 0.026), 0.955, step - 0.012,
                                          facecolor="#f4f6f8", edgecolor="none",
                                          transform=panel.transAxes, zorder=0))
        panel.text(0.03, y, lane, fontsize=10.4, color=INK, zorder=2)
        colour = VERDICT_COLOURS.get(verdict, INK)
        panel.text(0.44, y, verdict, fontsize=10.4, weight="bold", color=colour, zorder=2)
        panel.text(0.60, y, reading, fontsize=10.0, color=INK, zorder=2)

    footer_y = top - 0.045 - len(rows) * step - 0.05
    panel.text(0.03, footer_y,
               t("锚点：冻结基线 0.4091 / 冻结头条 0.4766 / 单表示 0.6081（跨种子均值 0.5861，仅 seed 42 过 0.60）",
                 "Anchors: frozen baseline 0.4091 / frozen headline 0.4766 / single representation 0.6081 "
                 "(cross-seed mean 0.5861, only seed 42 clears 0.60)"),
               fontsize=9.8, color="#444444")
    panel.text(0.03, footer_y - 0.045,
               t("verdict 颜色：绿 = 成立 / 改善，琥珀 = 部分或端点升级，蓝 = 分域第二块记分牌，红 = refuted，灰 = 未落盘。",
                 "Verdict colours: green = confirmed/improved, amber = partial or endpoint upgrade, "
                 "blue = the domain second board, red = refuted, grey = not landed."),
               fontsize=9.4, color="#666666")
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return True


# ---------------------------------------------------------------------------
# pins and entry points
# ---------------------------------------------------------------------------
PINNED = {
    "frozen_baseline": FROZEN_BASELINE,
    "frozen_headline": FROZEN_HEADLINE,
    "frozen_single_representation": FROZEN_SINGLE_REPRESENTATION,
    "flex_cross_seed_reference": 0.5861142332208197,
    "flex_anchor_measured": 0.6080587938801277,
    "viscosity_family_mae": 0.17477197208762,
    "viscosity_row_level_mae": 0.15686276760094522,
    "viscosity_gate": 0.15,
    "domain_global_r2": 0.45401075998423623,
    "domain_d1_in_r2": 0.524012313223719,
}

TOLERANCE = 1e-9


def derive(data) -> dict:
    out = {
        "frozen_baseline": FROZEN_BASELINE,
        "frozen_headline": FROZEN_HEADLINE,
        "frozen_single_representation": FROZEN_SINGLE_REPRESENTATION,
    }
    c = data.get("flex")
    if c is not None:
        out["flex_cross_seed_reference"] = float(c["cross_seed"]["reference_lever4"])
        out["flex_anchor_measured"] = float(c["anchors"]["rows"][0]["measured"])
    v = data.get("viscosity")
    if v is not None:
        gate = v["primary_gate"]
        out["viscosity_family_mae"] = float(gate["family_level_mae"])
        out["viscosity_row_level_mae"] = float(gate["row_level_mae"])
        out["viscosity_gate"] = float(gate["threshold"])
    d = data.get("domain")
    if d is not None:
        out["domain_global_r2"] = float(d["endpoint"]["global"]["all"]["r2_mean"])
        out["domain_d1_in_r2"] = float(d["headline_vs_in_domain"]["D1_in_domain_r2"])
    return out


def check_pins(data, derived) -> list:
    failures = []
    for key, expected in PINNED.items():
        if key not in derived:
            failures.append(key + ": lane summary missing, cannot assert")
            continue
        observed = float(derived[key])
        if abs(observed - float(expected)) > TOLERANCE:
            failures.append(key + ": expected " + repr(expected) + " observed " + repr(observed))
    return failures


def render(data) -> tuple:
    configure_fonts()
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    jobs = (
        (FIG_ENDPOINT, fig_endpoint),
        (FIG_GRID, fig_grid),
        (FIG_ONSAGER, fig_onsager),
        (FIG_FLEX, fig_flex),
        (FIG_LOGSCALE, fig_logscale),
        (FIG_VISCOSITY, fig_viscosity),
        (FIG_DOMAIN, fig_domain),
        (FIG_SCOREBOARD, fig_scoreboard),
    )
    drawn = []
    missing = []
    for name, function in jobs:
        ok = function(data, ARTIFACTS / name)
        if ok:
            drawn.append(name)
        else:
            missing.append(name)
    return drawn, missing


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Week 18 lane visual pack.")
    parser.add_argument("--check", action="store_true",
                        help="validate inputs and the pinned literals without drawing")
    args = parser.parse_args(argv)

    data = load_inputs()
    derived = derive(data)

    if args.check:
        failures = check_pins(data, derived)
        if failures:
            print("FAIL")
            for failure in failures:
                print("  - " + failure)
            return 1
        print("PASS")
        print(json.dumps({
            "pins": len(PINNED),
            "lanes_present": sorted(k for k, v in data.items() if v is not None),
            "lanes_missing": sorted(k for k, v in data.items() if v is None),
            "zh_labels": ZH,
        }, ensure_ascii=False, sort_keys=True))
        return 0

    drawn, missing = render(data)
    print(json.dumps({"drawn": drawn, "missing": missing, "zh_labels": ZH},
                     ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
