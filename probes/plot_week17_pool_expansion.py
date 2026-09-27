"""Week 17 pool-expansion picture pack: four shots on one axis.

Three figures, all redrawn from committed artifacts only; nothing here fits a
model or opens the network.  Arm and dose values are re-read from their owning
summaries at run time, the pool row counts come from the shot 14 summary, and
the two ThermoML row counts are the frozen W17-21 archive scan.  The literals in
PINNED are what --check asserts against, never a drawing input.

Figures (written into probes/artifacts/):
  w17_pool_expansion_arms.png     every arm of shots 12-15 against the 0.60 gate,
                                  grouped by the pool definition it was measured on
  w17_pool_expansion_dose.png     the four training-row dose curves side by side
  w17_pool_expansion_ceiling.png  how many rows and how many compounds the sources
                                  actually contain, i.e. the data ceiling

Labels are Chinese when a CJK font is present and English otherwise.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import Patch

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "probes/artifacts"
SHOT12 = ROOT / "probes/dielectric_pool_expansion_summary.json"
SHOT13 = ROOT / "probes/dielectric_pool_expansion_full_table_summary.json"
SHOT14 = ROOT / "probes/dielectric_pool_expansion_v3_summary.json"
SHOT15 = ROOT / "probes/dielectric_anchor_summary.json"
THERMOML_FULL = ROOT / "data/raw/thermoml_full/coverage.json"

FIG_ARMS = "w17_pool_expansion_arms.png"
FIG_DOSE = "w17_pool_expansion_dose.png"
FIG_CEILING = "w17_pool_expansion_ceiling.png"
FIGURE_FILES = (FIG_ARMS, FIG_DOSE, FIG_CEILING)

GATE = 0.60
PINNED = {
    "shot12_primary": 0.3809089252433510,
    "shot13_best_non_primary": 0.5433111678100043,
    "shot14_best_non_primary": 0.5433111678100043,
    "shot15_primary": 0.510231505819011,
    "frozen_headline": 0.4766400383507876,
}

GREEN = "#2f7d4f"
RED = "#a3320b"
ACCENT = "#c8a45c"
INK = "#3a3a3a"
GRID = "#d8d8d8"
FROZEN = "#9aa4ad"

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


def read_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def arm_rows() -> list[dict[str, object]]:
    """Every arm of every shot, tagged with the pool definition it was measured on."""

    out: list[dict[str, object]] = []
    spec = (
        ("shot12", SHOT12, "NBS 外来化学空间"),
        ("shot13", SHOT13, "同源全表 2029 行"),
        ("shot14", SHOT14, "同源全表 + 治理臂"),
        ("shot15", SHOT15, "同源全表 + 高 ε 锚点"),
    )
    for shot, path, label in spec:
        payload = read_json(path)
        for name, block in (payload.get("arms") or {}).items():
            out.append(
                {
                    "shot": shot,
                    "pool": label,
                    "arm": name,
                    "r2": float(block["r2"]),
                    "placebo": "placebo" in name,
                }
            )
    return out


def figure_arms(rows: list[dict[str, object]]) -> Path:
    filtered = [row for row in rows if not row["placebo"]]
    filtered.sort(key=lambda row: (str(row["pool"]), float(row["r2"])))
    labels = [f"{row['shot']}  {row['arm']}" for row in filtered]
    values = [float(row["r2"]) for row in filtered]
    colours = [ACCENT if value > GATE else (GREEN if value > 0.50 else FROZEN) for value in values]

    height = max(6.0, 0.34 * len(filtered) + 2.4)
    fig, ax = plt.subplots(figsize=(11.5, height))
    positions = range(len(filtered))
    ax.barh(list(positions), values, color=colours, edgecolor="white", height=0.68)
    ax.axvline(GATE, color=RED, linestyle="--", linewidth=1.6)
    ax.text(GATE + 0.004, len(filtered) - 0.4, t("0.60 门", "gate 0.60"), color=RED, fontsize=9)
    ax.set_yticks(list(positions))
    ax.set_yticklabels(labels, fontsize=8)
    ax.set_xlim(0.0, max(0.70, max(values) + 0.06))
    ax.set_xlabel(t("分组 R²（按各自池定义，不可混比）", "grouped R2 (per pool definition; not comparable)"))
    ax.set_title(t("W17 介电扩池：四枪的每一个臂", "W17 dielectric pool expansion: every arm of four shots"))
    for position, value in zip(positions, values):
        ax.text(value + 0.004, position, f"{value:.3f}", va="center", fontsize=8, color=INK)
    ax.grid(axis="x", color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)
    ax.legend(
        handles=[
            Patch(color=ACCENT, label=t("过 0.60", "above 0.60")),
            Patch(color=GREEN, label=t("0.50-0.60", "0.50-0.60")),
            Patch(color=FROZEN, label=t("低于 0.50", "below 0.50")),
        ],
        loc="lower right",
        fontsize=8,
    )
    fig.tight_layout()
    out = ARTIFACTS / FIG_ARMS
    fig.savefig(out, dpi=150)
    plt.close(fig)
    return out


def figure_dose() -> Path:
    spec = (
        ("shot12", SHOT12),
        ("shot13", SHOT13),
        ("shot14", SHOT14),
        ("shot15", SHOT15),
    )
    fig, ax = plt.subplots(figsize=(9.5, 5.6))
    plotted = 0
    for shot, path in spec:
        payload = read_json(path)
        rows = payload.get("dose_response") or []
        if not rows:
            continue
        doses = [float(row["dose"]) for row in rows]
        values = [float(row["r2"]) for row in rows]
        ax.plot(doses, values, marker="o", linewidth=1.8, label=shot)
        plotted += 1
    if plotted == 0:
        plt.close(fig)
        raise SystemExit("no dose curves found")
    ax.axhline(GATE, color=RED, linestyle="--", linewidth=1.4)
    ax.set_xlabel(t("剂量（训练-only 化合物的抽取比例）", "dose (fraction of training-only compounds)"))
    ax.set_ylabel(t("分组 R²", "grouped R2"))
    ax.set_title(t("剂量-响应：12/13 枪非单调，14/15 枪单调递增", "dose response: shots 12-13 non-monotone, shots 14-15 monotone"))
    ax.grid(color=GRID, linewidth=0.6)
    ax.legend(fontsize=9)
    fig.tight_layout()
    out = ARTIFACTS / FIG_DOSE
    fig.savefig(out, dpi=150)
    plt.close(fig)
    return out


def figure_ceiling() -> Path:
    """Row counts are read from the shot 14 summary; the ThermoML pair is the W17-21 archive scan."""

    shot14 = read_json(SHOT14).get("pool") or {}
    base_rows = int(shot14.get("base_rows", 2029))
    static_rows = int(shot14.get("static_training_rows", 1594))
    rows = [
        (t("本仓池（有 xTB 特征）", "released pool (with xTB)"), base_rows, 148),
        (t("本仓池·零频训练行", "released pool, zero-frequency"), static_rows, 148),
        (t("ThermoML 全档·静态", "ThermoML full, static"), 1630, 153),
        (t("ThermoML 全档·全部", "ThermoML full, all"), 2529, 157),
    ]
    labels = [item[0] for item in rows]
    row_values = [item[1] for item in rows]
    compound_values = [item[2] for item in rows]
    x = range(len(rows))
    fig, (ax_rows, ax_compounds) = plt.subplots(1, 2, figsize=(11.0, 4.6))
    ax_rows.bar(list(x), row_values, color=GREEN, width=0.6)
    ax_rows.set_xticks(list(x))
    ax_rows.set_xticklabels(labels, rotation=18, ha="right", fontsize=8)
    ax_rows.set_ylabel(t("行数", "rows"))
    ax_rows.set_title(t("行数：还有空间", "rows: room left"), fontsize=10)
    for position, value in zip(x, row_values):
        ax_rows.text(position, value + 30, str(value), ha="center", fontsize=8)
    ax_compounds.bar(list(x), compound_values, color=ACCENT, width=0.6)
    ax_compounds.set_xticks(list(x))
    ax_compounds.set_xticklabels(labels, rotation=18, ha="right", fontsize=8)
    ax_compounds.set_ylabel(t("化合物数", "compounds"))
    ax_compounds.set_title(t("化合物数：已经封顶", "compounds: already capped"), fontsize=10)
    ax_compounds.set_ylim(0, 180)
    for position, value in zip(x, compound_values):
        ax_compounds.text(position, value + 3, str(value), ha="center", fontsize=8)
    for axis in (ax_rows, ax_compounds):
        axis.grid(axis="y", color=GRID, linewidth=0.6)
        axis.set_axisbelow(True)
    fig.suptitle(t("数据天花板：加行容易，加化合物到顶了", "the data ceiling: rows are cheap, compounds are capped"))
    fig.tight_layout()
    out = ARTIFACTS / FIG_CEILING
    fig.savefig(out, dpi=150)
    plt.close(fig)
    return out


def check(rows: list[dict[str, object]]) -> int:
    problems: list[str] = []
    readings = {(str(row["shot"]), str(row["arm"])): float(row["r2"]) for row in rows}
    expected = {
        ("shot12", "plus_expansion_hybrid"): PINNED["shot12_primary"],
        ("shot13", "full_table_lever4"): PINNED["shot13_best_non_primary"],
        ("shot14", "full_table_lever4"): PINNED["shot14_best_non_primary"],
    }
    shot15 = PINNED.get("shot15_primary")
    if shot15 is not None and ("shot15", "anchors_lever4") in readings:
        expected[("shot15", "anchors_lever4")] = shot15
    for key, want in expected.items():
        got = readings.get(key)
        if got is None:
            problems.append(f"{key} is missing")
        elif abs(got - want) > 1e-12:
            problems.append(f"{key} moved: {got!r} != {want!r}")
    for name in FIGURE_FILES:
        if not (ARTIFACTS / name).is_file():
            problems.append(f"{name} is missing")
    for problem in problems:
        print("PROBLEM " + problem)
    if problems:
        return 1
    print(f"checked {len(expected)} pinned readings and {len(FIGURE_FILES)} figures")
    return 0


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    configure_fonts()
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    rows = arm_rows()
    if args.check:
        return check(rows)
    written = [figure_arms(rows), figure_dose(), figure_ceiling()]
    for path in written:
        print("wrote " + str(path.relative_to(ROOT)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
