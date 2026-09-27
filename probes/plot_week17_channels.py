"""Week 17 data-expansion visual pack for the four core channels.

Six figures, all redrawn from committed artifacts only: nothing here fits a
model, opens the network or touches the frozen main scoreboard.  Every plotted
number is re-read from its owning artifact at run time; the literals in PINNED
are the values --check asserts against, never a drawing input.

Figures (written into probes/artifacts/):
  w17_channels_gate_board.png        MAE-style readouts normalised to their own
                                     gate, next to the R2 readouts
  w17_themol_tier_delivery.png       the 5,117-key roster by tier and the honest
                                     partial delivery
  w17_themol_calibration_parity.png  GFN2-xTB vs wB97X-V parity with y = x, the
                                     2-fold fit and both fold fits
  w17_themol_level_offsets.png       GFN2 - wB97X-V offset spread per level
  w17_channels_label_inventory.png   how many labels each channel actually has
  w17_reaxys_round_tally.png         this round's Reaxys card-walk tally

Labels are Chinese when a CJK font is present on the machine and English
otherwise, so the PNGs never ship tofu boxes.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import Patch

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "probes/artifacts"

LAYER_CSV = ROOT / "data/processed/themol_orbital_layer_expanded.csv"
BOARD_CSV = ROOT / "data/processed/four_channel_coverage.csv"
THEMOL_LAYER_SUMMARY = ROOT / "probes/themol_orbital_layer_expanded_summary.json"
THEMOL_ROSTER_SUMMARY = ROOT / "probes/themol_registry_expansion_roster_summary.json"
FOUR_CHANNEL_SUMMARY = ROOT / "probes/four_channel_coverage_summary.json"
REAXYS_SUMMARY = ROOT / "probes/reaxys_v1x_stocking_query_summary.json"
HOMO_LUMO_SUMMARY = ROOT / "models/homo_lumo_baselines.json"

FIG_GATE = "w17_channels_gate_board.png"
FIG_TIER = "w17_themol_tier_delivery.png"
FIG_PARITY = "w17_themol_calibration_parity.png"
FIG_OFFSET = "w17_themol_level_offsets.png"
FIG_LABELS = "w17_channels_label_inventory.png"
FIG_REAXYS = "w17_reaxys_round_tally.png"
FIGURE_FILES = (FIG_GATE, FIG_TIER, FIG_PARITY, FIG_OFFSET, FIG_LABELS, FIG_REAXYS)

GREEN = "#2f7d4f"
RED = "#a3320b"
ACCENT = "#c8a45c"
INK = "#3a3a3a"
GRID = "#d8d8d8"
PLANNED = "#b9c4cc"
LEAK = "#8a8f95"

TIER_COLOURS = {
    "no_reference_orbital": "#2f6f4e",
    "flagship_dielectric": "#3f7fbf",
    "named_core_channel": "#c8a45c",
    "calibration_bulk": "#b9c4cc",
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


def configure_fonts() -> None:
    families = [CJK_FONT] if CJK_FONT else []
    families.append("DejaVu Sans")
    plt.rcParams["font.family"] = "sans-serif"
    plt.rcParams["font.sans-serif"] = families
    plt.rcParams["axes.unicode_minus"] = False


def num(value):
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def load_inputs() -> dict:
    board_rows = load_csv(BOARD_CSV)
    return {
        "board": {(row["channel"], row["metric"]): row for row in board_rows},
        "board_rows": board_rows,
        "layer": load_csv(LAYER_CSV),
        "themol": load_json(THEMOL_LAYER_SUMMARY),
        "roster": load_json(THEMOL_ROSTER_SUMMARY),
        "four": load_json(FOUR_CHANNEL_SUMMARY),
        "reaxys": load_json(REAXYS_SUMMARY),
        "homo_lumo": load_json(HOMO_LUMO_SUMMARY),
    }


# ---------------------------------------------------------------------------
# The pins that --check asserts.  Only frozen artifacts are pinned literally:
# the four-channel board, the frozen 5,117-key roster and the DN coverage
# counters.  data/processed/themol_orbital_layer_expanded.csv and its summary
# are still being rebuilt while the arm harvests, so their calibration and
# offset numbers move between reads and are checked structurally (row counts
# and the run_status rule), never as literals.
# ---------------------------------------------------------------------------
PINNED = {
    "dielectric_r2": 0.4091179943351143,
    "dielectric_r2_headline": 0.4766400383507876,
    "viscosity_r2": 0.7481271437772365,
    "viscosity_mae": 0.17477197208762,
    "homo_mae": 0.19050925839013938,
    "lumo_mae": 0.13855083976437643,
    "ip_mae": 0.2010970559642009,
    "ea_mae": 0.23415453202842548,
    "redox_ox_mae": 0.2905180517963865,
    "redox_red_mae": 0.4096241620366996,
    "redox_rx392": 392.0,
    "dn_covered": 0.0,
    "dn_target": 1043.0,
    "roster_rows": 5117.0,
    "tier_no_reference": 421.0,
    "tier_flagship": 54.0,
    "tier_named": 68.0,
    "tier_calibration": 4574.0,
}

CALIBRATION_LEVELS = ("homo", "lumo", "gap")


def derive(data: dict) -> dict:
    board = data["board"]
    pin = data["four"]["pinned"]
    themol = data["themol"]
    roster = data["roster"]
    tiers = roster["rows_by_tier"]
    offsets = themol["level_offsets_gfn2_minus_batt"]
    calib = themol["calibration"]

    def board_value(channel: str, metric: str):
        return num(board[(channel, metric)]["value"])

    return {
        "dielectric_r2": board_value("dielectric", "main_scoreboard_baseline_grouped_r2"),
        "dielectric_r2_headline": board_value(
            "dielectric", "main_scoreboard_headline_grouped_r2"
        ),
        "viscosity_r2": board_value("viscosity", "group_key_r2"),
        "viscosity_mae": board_value("viscosity", "group_key_mae_log10_cP"),
        "homo_mae": board_value("homo_lumo", "HOMO_fold_mean_mae"),
        "lumo_mae": board_value("homo_lumo", "LUMO_fold_mean_mae"),
        "ip_mae": board_value("homo_lumo", "IP_fold_mean_mae"),
        "ea_mae": board_value("homo_lumo", "EA_fold_mean_mae"),
        "redox_ox_mae": board_value("redox", "oxidation_free_energy_mae"),
        "redox_red_mae": board_value("redox", "reduction_free_energy_mae"),
        "redox_rx392": float(pin["redox_rx392_rows"]),
        "dn_covered": float(pin["dn_covered_keys"]),
        "dn_target": float(pin["dn_target_keys"]),
        "roster_rows": float(roster["roster_rows"]),
        "tier_no_reference": float(tiers["no_reference_orbital"]),
        "tier_flagship": float(tiers["flagship_dielectric"]),
        "tier_named": float(tiers["named_core_channel"]),
        "tier_calibration": float(tiers["calibration_bulk"]),
        "delivered_rows": float(themol["delivered_rows"]),
        "completion_share": float(themol["completion_share"]),
        "calib_pairs": float(calib["homo"]["n"]),
        "homo_r": calib["homo"]["pearson_r_in_sample"],
        "homo_oos_mae": calib["homo"]["mae_out_of_sample_eV"],
        "lumo_r": calib["lumo"]["pearson_r_in_sample"],
        "lumo_oos_mae": calib["lumo"]["mae_out_of_sample_eV"],
        "gap_r": calib["gap"]["pearson_r_in_sample"],
        "gap_oos_mae": calib["gap"]["mae_out_of_sample_eV"],
        "offset_homo_mean": offsets["homo"]["mean_eV"],
        "offset_homo_sigma": offsets["homo"]["sigma_eV"],
        "offset_lumo_mean": offsets["lumo"]["mean_eV"],
        "offset_lumo_sigma": offsets["lumo"]["sigma_eV"],
    }


def check_pins(data: dict, derived: dict) -> list[str]:
    failures = []
    for key, expected in PINNED.items():
        got = derived.get(key)
        if got is None:
            failures.append(f"{key}: missing")
            continue
        scale = max(abs(expected), 1e-12)
        if abs(got - expected) > 1e-6 * scale:
            failures.append(f"{key}: derived {got!r} != pinned {expected!r}")

    # The rebuild-in-progress layer: hold it to its own internal story rather
    # than to the brief's snapshot literals.
    layer_rows = len(data["layer"])
    themol = data["themol"]
    if themol["delivered_rows"] != layer_rows:
        failures.append("delivered_rows does not match the layer row count")
    expected_status = "complete" if layer_rows == data["roster"]["roster_rows"] else "partial"
    if themol["run_status"] != expected_status:
        failures.append(f"run_status {themol['run_status']!r} != {expected_status!r}")
    for level in CALIBRATION_LEVELS:
        n_calib = themol["calibration"][level]["n"]
        if n_calib != themol["pair_counts"][level]:
            failures.append(f"{level}: calibration n {n_calib} != pair_count")
        if themol["level_offsets_gfn2_minus_batt"][level]["n"] != n_calib:
            failures.append(f"{level}: offset n != calibration n")
        if n_calib > layer_rows:
            failures.append(f"{level}: calibration pairs exceed the delivered rows")
    return failures


def style(axes) -> None:
    axes.grid(True, color=GRID, linewidth=0.6, alpha=0.8)
    axes.set_axisbelow(True)
    for side in ("top", "right"):
        axes.spines[side].set_visible(False)


# ---------------------------------------------------------------------------
# Figure 1: the four-channel gate board
# ---------------------------------------------------------------------------
def fig_gate_board(data: dict, path: Path) -> None:
    board = data["board"]
    fig, (left, right) = plt.subplots(
        1, 2, figsize=(14.2, 6.4), gridspec_kw={"width_ratios": [2.1, 1.0]}
    )
    specs = (
        (("viscosity", "group_key_mae_log10_cP"),
         t("eta 黏度 组键 MAE", "viscosity group-key MAE"), "lower"),
        (("homo_lumo", "HOMO_fold_mean_mae"), "HOMO MAE", "lower"),
        (("homo_lumo", "LUMO_fold_mean_mae"), "LUMO MAE", "lower"),
        (("homo_lumo", "IP_fold_mean_mae"), "IP MAE", "lower"),
        (("homo_lumo", "EA_fold_mean_mae"), "EA MAE", "lower"),
        (("redox", "oxidation_free_energy_mae"),
         t("redox 氧化 MAE", "redox oxidation MAE"), "lower"),
        (("redox", "reduction_free_energy_mae"),
         t("redox 还原 MAE", "redox reduction MAE"), "lower"),
        (("dn", "admissible_coverage_fraction"), t("DN 覆盖", "DN coverage"), "higher"),
    )
    names, ratios, colours, notes = [], [], [], []
    for (channel, metric), label, direction in specs:
        row = board[(channel, metric)]
        value = num(row["value"])
        gate = num(row["gate_threshold"])
        status = row["gate_status"]
        names.append(label)
        ratios.append(value / gate if gate else float("nan"))
        colours.append(GREEN if status == "green" else RED)
        arrow = "\u2193" if direction == "lower" else "\u2191"
        notes.append(f"{value:g} / {t('门', 'gate')} {gate:g} {arrow}")
    ys = list(range(len(names)))
    left.barh(ys, ratios, color=colours, height=0.62)
    left.axvline(1.0, color=INK, linestyle="--", linewidth=1.3)
    left.text(1.02, -0.7, t("门 = 1.0", "gate = 1.0"), color=INK, fontsize=9, va="center")
    for y, ratio, note in zip(ys, ratios, notes):
        left.text(ratio + 0.03, y, note, va="center", fontsize=8.5, color=INK)
    left.set_yticks(ys)
    left.set_yticklabels(names, fontsize=9.5)
    left.invert_yaxis()
    left.set_xlim(0, max(ratios) * 1.28)
    left.set_xlabel(t("读数 / 门限（跨单位归一，1.0 即门）",
                      "readout / gate (unit-free; 1.0 is the gate)"))
    left.set_title(t("MAE 类读数对门限（绿=过门，红=未过）\n"
                     "\u2193 = 越小越好，\u2191 = 越大越好",
                     "MAE-style readouts vs their gates (green = pass, red = fail)\n"
                     "\u2193 lower is better, \u2191 higher is better"),
                   fontsize=11)
    left.legend(handles=[Patch(color=GREEN, label=t("过门", "pass")),
                         Patch(color=RED, label=t("未过门", "fail"))],
                frameon=False, fontsize=9, loc="lower right")
    style(left)

    # The epsilon scoreboard is quoted twice on purpose: the promoted headline and the
    # frozen baseline it was measured against.  They are the same pool, so they are drawn
    # side by side in the same colour, with the frozen one hatched -- never merged.
    r2_specs = (
        (("dielectric", "main_scoreboard_headline_grouped_r2"),
         t("ε 头条 R2\n（提升后）", "ε headline R2\n(promoted)"), ACCENT, False),
        (("dielectric", "main_scoreboard_baseline_grouped_r2"),
         t("ε 基线 R2\n（冻结）", "ε baseline R2\n(frozen)"), ACCENT, True),
        (("viscosity", "group_key_r2"),
         t("eta 组键 R2", "eta group-key R2"), RED, False),
        (("dielectric", "random_row_leak_reference_r2"),
         t("行级泄漏\n参照 R2", "row-level leak\nreference R2"), LEAK, True),
    )
    labels = [spec[1] for spec in r2_specs]
    values = [num(board[spec[0]]["value"]) for spec in r2_specs]
    colours = [spec[2] for spec in r2_specs]
    bars = right.bar(range(len(labels)), values, color=colours, width=0.6)
    for bar, spec in zip(bars, r2_specs, strict=True):
        if spec[3]:
            bar.set_hatch("//")
            bar.set_edgecolor(INK)
            bar.set_alpha(0.55)
    for index, value in enumerate(values):
        right.text(index, value + 0.02, f"{value:.3f}", ha="center", fontsize=9, color=INK)
    right.annotate(
        t("头条 = W17-6 合并枪；基线逐位未动", "headline = W17-6 merge arm; baseline bit-identical"),
        xy=(0.5, 0.62), xycoords="data", ha="center", fontsize=8.5, color=INK,
    )
    right.set_xticks(range(len(labels)))
    right.set_xticklabels(labels, fontsize=8)
    right.set_ylim(0, 1.0)
    right.set_ylabel("R2")
    right.set_title(t("R2 类读数（口径不同，不与左图混比）\n"
                      "斜纹 = 冻结/参照档，实心 = 当前头条",
                      "R2 readouts (different scale; not comparable to the left panel)\n"
                      "hatched = frozen or reference; solid = current headline"),
                    fontsize=10)
    style(right)

    fig.suptitle(t("W17 四通道看板：哪几门红了（ε 头条已提升至合并配置）",
                   "Week 17 four-channel board: which gates are red "
                   "(epsilon headline promoted to the merged configuration)"), fontsize=14)
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    fig.savefig(path, dpi=150)
    plt.close(fig)


# ---------------------------------------------------------------------------
# Figure 2: THEMol roster by tier and the honest partial delivery
# ---------------------------------------------------------------------------
def fig_tier_delivery(data: dict, path: Path) -> None:
    roster = data["roster"]
    themol = data["themol"]
    tiers = roster["tier_order"]
    planned = [roster["rows_by_tier"][tier] for tier in tiers]
    delivered = [themol["rows_by_tier"].get(tier, 0) for tier in tiers]
    names = {
        "no_reference_orbital": t("无参考轨道", "no reference orbital"),
        "flagship_dielectric": t("旗舰 epsilon 名册", "flagship epsilon roster"),
        "named_core_channel": t("其他核心通道", "other core channels"),
        "calibration_bulk": t("Batt 标定主体", "Batt calibration bulk"),
    }
    labels = [names[tier] for tier in tiers]
    total = roster["roster_rows"]

    fig, (top, bottom) = plt.subplots(
        2, 1, figsize=(12.6, 8.4), gridspec_kw={"height_ratios": [1.0, 1.9]}
    )

    cursor = 0.0
    for tier, value in zip(tiers, planned):
        top.barh([0], [value], left=cursor, color=TIER_COLOURS[tier], height=0.5,
                 edgecolor="white", linewidth=1.0)
        if value / total >= 0.05:
            top.text(cursor + value / 2, 0, f"{value:,}", ha="center", va="center",
                     fontsize=9, color="white" if tier != "calibration_bulk" else INK)
        cursor += value
    top.set_xlim(0, total)
    top.set_ylim(-0.6, 0.6)
    top.set_yticks([])
    top.set_xlabel(t("分子数", "molecules"))
    top.set_title(t(f"冻结名册 {total:,} 键的分层构成",
                    f"the frozen {total:,}-key roster by tier"), fontsize=11)
    top.legend(handles=[Patch(color=TIER_COLOURS[tier],
                              label=f"{labels[index]} ({roster['rows_by_tier'][tier]:,})")
                        for index, tier in enumerate(tiers)],
               frameon=False, fontsize=9, ncol=4, loc="upper center",
               bbox_to_anchor=(0.5, -0.28))
    style(top)

    ys = list(range(len(tiers)))
    bottom.barh([y + 0.2 for y in ys], planned, height=0.38, color=PLANNED,
                label=t("名册目标", "roster target"))
    bottom.barh([y - 0.2 for y in ys], delivered, height=0.38, color=GREEN,
                label=t("实际交付（带 GFN2 数）", "delivered with a GFN2 number"))
    bottom.set_xscale("log")
    bottom.set_xlim(0.8, max(planned) * 3.0)
    for y, plan, done in zip(ys, planned, delivered):
        share = done / plan if plan else 0.0
        bottom.text(plan * 1.15, y + 0.2, f"{plan:,}", va="center", fontsize=8.5, color=INK)
        bottom.text(done * 1.15, y - 0.2, f"{done:,}  ({share:.1%})", va="center",
                    fontsize=8.5, color=GREEN)
    bottom.set_yticks(ys)
    bottom.set_yticklabels(labels, fontsize=9.5)
    bottom.invert_yaxis()
    bottom.set_xlabel(t("分子数（对数轴）", "molecules (log scale)"))
    bottom.set_title(t("分层交付占比", "delivery share by tier"), fontsize=11)
    bottom.legend(frameon=False, fontsize=9, loc="upper right")
    style(bottom)

    status = themol["run_status"]
    share = themol["completion_share"]
    stamp = t(f"诚实标注：run_status = {status}  —— 交付 {themol['delivered_rows']:,} / "
              f"{total:,} = {share:.2%}，不是跑完",
              f"honest stamp: run_status = {status}  --  delivered {themol['delivered_rows']:,} of "
              f"{total:,} = {share:.2%}, not finished")
    fig.text(0.5, 0.005, stamp, ha="center", fontsize=10, color=RED)
    fig.suptitle(t("THEMol 扩展臂名册分层与实际交付（W17-17）",
                   "THEMol expansion arm: roster tiers vs actual delivery (W17-17)"),
                 fontsize=14)
    fig.tight_layout(rect=(0, 0.03, 1, 0.95))
    fig.savefig(path, dpi=150)
    plt.close(fig)


# ---------------------------------------------------------------------------
# Figure 3: cross-level calibration parity
# ---------------------------------------------------------------------------
def paired(rows: list[dict[str, str]], x_key: str, y_key: str):
    points = []
    for row in rows:
        x = num(row[x_key])
        y = num(row[y_key])
        if x is not None and y is not None:
            points.append((x, y))
    return points


def fig_calibration_parity(data: dict, path: Path) -> None:
    rows = data["layer"]
    calib = data["themol"]["calibration"]
    specs = (
        ("homo", "homo_gfn2_eV", "batt_homo_eV", "HOMO"),
        ("lumo", "lumo_gfn2_eV", "batt_lumo_eV", "LUMO"),
        ("gap", "gap_gfn2_eV", "batt_gap_eV", t("gap 能隙", "gap")),
    )
    fig, panels = plt.subplots(1, 3, figsize=(16.0, 5.6))
    for panel, (channel, x_key, y_key, label) in zip(panels, specs):
        stats = calib[channel]
        points = paired(rows, x_key, y_key)
        xs = [point[0] for point in points]
        ys = [point[1] for point in points]
        panel.scatter(xs, ys, s=12, alpha=0.5, color=GREEN, linewidths=0)
        low = min(min(xs), min(ys)) - 1.0
        high = max(max(xs), max(ys)) + 1.0
        panel.plot([low, high], [low, high], color=RED, linewidth=1.1,
                   linestyle="--", label="y = x")
        panel.plot([low, high],
                   [stats["slope"] * low + stats["intercept"],
                    stats["slope"] * high + stats["intercept"]],
                   color=ACCENT, linewidth=1.8, label=t("总体 2 折拟合", "overall 2-fold fit"))
        for fold in stats["fold_fits"]:
            start = fold["slope"] * low + fold["intercept"]
            stop = fold["slope"] * high + fold["intercept"]
            panel.plot([low, high], [start, stop], color=INK, linewidth=1.0,
                       linestyle=":", alpha=0.85,
                       label=t(f"折 {fold['held_out_fold']} 折外拟合",
                               f"fold {fold['held_out_fold']} out-of-fold fit"))
        panel.set_xlabel(t(f"GFN2-xTB {label} (eV)", f"GFN2-xTB {label} (eV)"))
        panel.set_ylabel(t(f"wB97X-V {label} (eV)", f"wB97X-V {label} (eV)"))
        panel.set_title(
            f"{label}: n={stats['n']}  r={stats['pearson_r_in_sample']:.3f}\n"
            f"MAE={stats['mae_out_of_sample_eV']:.3f} eV  -> {stats['status']}",
            fontsize=10,
        )
        panel.legend(frameon=False, fontsize=7.5, loc="upper left")
        style(panel)
    pairs = calib["homo"]["n"]
    fig.suptitle(t(f"跨水平标定：GFN2-xTB 对 wB97X-V（{pairs} 对，全部为折外点）",
                   f"Cross-level calibration: GFN2-xTB vs wB97X-V "
                   f"({pairs} pairs, all out-of-fold)"), fontsize=13)
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    fig.savefig(path, dpi=150)
    plt.close(fig)


# ---------------------------------------------------------------------------
# Figure 4: level offsets GFN2 - wB97X-V
# ---------------------------------------------------------------------------
def fig_level_offsets(data: dict, path: Path) -> None:
    rows = data["layer"]
    offsets = data["themol"]["level_offsets_gfn2_minus_batt"]
    specs = (
        ("homo", "gfn2_minus_batt_homo_eV", "HOMO"),
        ("lumo", "gfn2_minus_batt_lumo_eV", "LUMO"),
        ("gap", "gfn2_minus_batt_gap_eV", t("gap 能隙", "gap")),
    )
    fig, panels = plt.subplots(1, 3, figsize=(15.0, 5.0))
    for panel, (channel, key, label) in zip(panels, specs):
        deltas = [num(row[key]) for row in rows if num(row[key]) is not None]
        panel.hist(deltas, bins=32, color=GREEN, alpha=0.85)
        stats = offsets[channel]
        panel.axvline(stats["mean_eV"], color=RED, linewidth=1.4,
                      label=t(f"均值 {stats['mean_eV']:+.3f} eV",
                              f"mean {stats['mean_eV']:+.3f} eV"))
        panel.set_xlabel(t(f"GFN2 - wB97X-V {label} (eV)", f"GFN2 - wB97X-V {label} (eV)"))
        panel.set_ylabel(t("分子数", "molecules"))
        panel.set_title(f"{label}: sigma = {stats['sigma_eV']:.3f} eV  (n={stats['n']})",
                        fontsize=10)
        panel.legend(frameon=False, fontsize=8.5)
        style(panel)
    sigma_h = offsets["homo"]["sigma_eV"]
    sigma_l = offsets["lumo"]["sigma_eV"]
    fig.suptitle(t(f"能级偏移分布：HOMO sigma {sigma_h:.3f} eV（可整体平移）；"
                   f"LUMO sigma {sigma_l:.3f} eV（离散）",
                   f"level offset spread: HOMO sigma {sigma_h:.3f} eV (shiftable); "
                   f"LUMO sigma {sigma_l:.3f} eV (dispersed)"), fontsize=12)
    fig.tight_layout(rect=(0, 0, 1, 0.9))
    fig.savefig(path, dpi=150)
    plt.close(fig)


# ---------------------------------------------------------------------------
# Figure 5: label inventory per channel
# ---------------------------------------------------------------------------
def fig_label_inventory(data: dict, path: Path) -> None:
    pin = data["four"]["pinned"]
    homo_lumo = data["homo_lumo"]
    pool = homo_lumo["targets"]["HOMO"]["training_pool_rows"]
    group_count = homo_lumo["source_dataset"]["group_count"]
    bars = (
        (t("epsilon 介电（行）", "epsilon dielectric (rows)"), float(pin["dielectric_scoreboard_rows"])),
        (t("eta 黏度（行）", "eta viscosity (rows)"), float(pin["viscosity_v01_rows"])),
        ("HOMO", float(pool)),
        ("LUMO", float(pool)),
        ("IP", float(pool)),
        ("EA", float(pool)),
        (t("氧化还原 redox（标签行）", "redox (labelled rows)"), float(pin["redox_rx392_rows"])),
    )
    fig, (left, right) = plt.subplots(
        1, 2, figsize=(14.2, 6.0), gridspec_kw={"width_ratios": [2.4, 1.0]}
    )
    names = [item[0] for item in bars]
    values = [item[1] for item in bars]
    ys = list(range(len(names)))
    colours = [ACCENT] * 2 + [GREEN] * 4 + [RED]
    left.barh(ys, values, color=colours, height=0.62)
    left.set_xscale("log")
    left.set_xlim(0.5, max(values) * 3.0)
    for y, value in zip(ys, values):
        left.text(value * 1.12, y, f"{value:,.0f}", va="center", fontsize=9, color=INK)
    left.set_yticks(ys)
    left.set_yticklabels(names, fontsize=9.5)
    left.invert_yaxis()
    left.set_xlabel(t("标签条数（对数轴）", "labeled rows (log scale)"))
    left.set_title(t(f"各通道标签量（Batt 池 {group_count:,} 组，训练池 {pool:,} 行）",
                     f"labels per channel (Batt pool {group_count:,} groups, "
                     f"training pool {pool:,} rows)"), fontsize=10.5)
    style(left)

    dn_gate = num(data["board"][("dn", "admissible_coverage_fraction")]["gate_threshold"])
    dn_value = float(pin["dn_covered_keys"])
    dn_target = float(pin["dn_target_keys"])
    right.bar([0], [dn_gate], color=PLANNED, width=0.5,
              label=t(f"门 {dn_gate:.2f}", f"gate {dn_gate:.2f}"))
    right.bar([0], [dn_value], color=RED, width=0.5, label=t("可采信覆盖", "admissible coverage"))
    right.text(0, dn_gate + 0.01, f"{dn_gate:.2f}", ha="center", fontsize=9, color=INK)
    right.text(0.3, dn_gate / 2, t(f"可采信 {dn_value:g} / {dn_target:,.0f}\n= 0.00%\n不入特征表",
                                   f"admissible {dn_value:g} / {dn_target:,.0f}\n= 0.00%\n"
                                   f"stays out of the feature table"),
               va="center", ha="left", fontsize=9.5, color=RED)
    right.set_xlim(-0.6, 1.4)
    right.set_ylim(0, 0.42)
    right.set_xticks([])
    right.set_ylabel(t("覆盖比例", "coverage fraction"))
    right.set_title(t("DN 覆盖：0.00%（门 0.30，红）",
                      "DN coverage: 0.00% (gate 0.30, red)"), fontsize=10.5)
    right.legend(frameon=False, fontsize=9, loc="upper right")
    style(right)

    fig.suptitle(t("四通道数据可用性：每个通道到底有多少条标签",
                   "four-channel data availability: how many labels each channel has"),
                 fontsize=13)
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    fig.savefig(path, dpi=150)
    plt.close(fig)


# ---------------------------------------------------------------------------
# Figure 6: this round's Reaxys card-walk tally
# ---------------------------------------------------------------------------
def fig_reaxys_tally(data: dict, path: Path) -> None:
    summary = data["reaxys"]
    tally = summary["channel_tally"]
    order = ("eps", "eta", "hp", "redox")
    names = {
        "eps": t("epsilon 介电", "epsilon dielectric"),
        "eta": t("eta 黏度", "eta viscosity"),
        "hp": t("IP / 量化计算", "IP / QC calculations"),
        "redox": t("氧化还原", "redox"),
    }
    labels = [names[key] for key in order]
    axes_series = (
        (t("行数", "rows"), "rows", "#b9c4cc"),
        (t("有效值行", "valued rows"), "valued_rows", ACCENT),
        (t("点值", "point values"), "point_values", GREEN),
    )
    fig, panel = plt.subplots(figsize=(12.4, 6.0))
    width = 0.26
    positions = list(range(len(order)))
    for index, (label, key, colour) in enumerate(axes_series):
        values = [tally[channel][key] for channel in order]
        offset = (index - 1) * width
        panel.bar([p + offset for p in positions], values, width=width, color=colour,
                  label=label)
        for p, value in zip(positions, values):
            panel.text(p + offset, value + 1.5, str(value), ha="center", fontsize=8.5,
                       color=INK)
    panel.set_xticks(positions)
    panel.set_xticklabels(labels, fontsize=10)
    panel.set_ylabel(t("条数", "count"))
    panel.set_title(
        t(f"Reaxys W17-16 本轮卡片普查（{summary['substances_queried']} 个物质；"
          f"值不入 data / 池 / 特征表）",
          f"Reaxys W17-16 this-round card walk ({summary['substances_queried']} substances; "
          f"values enter no data / pool / feature table)"),
        fontsize=11.5,
    )
    panel.legend(frameon=False, fontsize=9.5)
    style(panel)
    fig.tight_layout(rect=(0, 0, 1, 1))
    fig.savefig(path, dpi=150)
    plt.close(fig)


def render(data: dict) -> None:
    configure_fonts()
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    fig_gate_board(data, ARTIFACTS / FIG_GATE)
    fig_tier_delivery(data, ARTIFACTS / FIG_TIER)
    fig_calibration_parity(data, ARTIFACTS / FIG_PARITY)
    fig_level_offsets(data, ARTIFACTS / FIG_OFFSET)
    fig_label_inventory(data, ARTIFACTS / FIG_LABELS)
    fig_reaxys_tally(data, ARTIFACTS / FIG_REAXYS)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
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
                print(f"  - {failure}")
            return 1
        print("PASS")
        print(json.dumps({"pins": len(PINNED), "layer_rows": len(data["layer"]),
                          "delivered_rows": int(derived["delivered_rows"]),
                          "calibration_pairs": int(derived["calib_pairs"]),
                          "run_status": data["themol"]["run_status"], "zh_labels": ZH},
                         sort_keys=True))
        return 0

    render(data)
    print(json.dumps({"figures": list(FIGURE_FILES), "layer_rows": len(data["layer"]),
                      "run_status": data["themol"]["run_status"], "zh_labels": ZH},
                     ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
