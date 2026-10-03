"""W27 -- the dielectric-response descriptor block as a fourth representation family.

Week 26 measured the dielectric response law on a 242-compound roster that turns
out to be 242 of the 246 compounds of the dielectric modelling roster, and it
left every per-compound response number on disk.  That is a representation family
this scoreboard has never seen: not a static descriptor (dipole, polarizability,
gap) but the *response* of the electronic structure to a continuum dielectric,
measured on a 14-point epsilon grid and fitted per compound.

This probe asks one pre-registered question on the frozen main scoreboard pool
(2029 base training rows / 457 scored rows over 97 compounds): appended to the
dense lever-4 physical block, does that response block move the Physical
representation?

Nothing frozen moves.  The pool, the score mask, the group splitter, the fitter
(XGB_PARAMS: max_depth 2, 200 trees) and the five-seed set are the ones that
produced 0.5433111678100043 for full_table_lever4 at seed 42.  Seed 42 has to
reproduce that anchor bit for bit, otherwise this probe refuses to report.

Two disciplines are declared here rather than discovered later:

* missing rows are NOT imputed.  The block carries NaN where the compound is
  outside the W26 roster and XGBoost's own missing-value handling applies.  No
  fold statistics are computed, so no fold statistic can leak;
* no column of the block touches the measured dielectric constant.  Every column
  is a response of the neutral or ionised solute to a continuum that was given an
  epsilon, never the epsilon the scoreboard is trying to predict.

Run:
    .venv/Scripts/python.exe probes/w27_dielectric_response.py --jobs 8
    .venv/Scripts/python.exe probes/w27_dielectric_response.py --seeds 42 --jobs 8
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
import time
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))
sys.path.insert(0, str(REPOSITORY_ROOT / "probes"))
import dielectric_coordination_block as v1
import dielectric_pool_expansion_benchmark as bn
import dielectric_representation_seed_robustness as sr
import numpy as np
from dielectric_representation_ablation import REPRESENTATIONS
from export_results_common import write_json_stable

from electrolyte_ml.pathing import portable_relative_path

PREREG_PATH = REPOSITORY_ROOT / "probes" / "w27_dielectric_response_prereg.json"
SUMMARY_PATH = REPOSITORY_ROOT / "probes" / "w27_dielectric_response_summary.json"
PLACEBO_SUMMARY_PATH = REPOSITORY_ROOT / "probes" / "w27_dielectric_response_placebo_summary.json"
REPORT_PATH = REPOSITORY_ROOT / "reports" / "w27_dielectric_response.md"
ARTIFACTS_DIR = REPOSITORY_ROOT / "probes" / "artifacts"
BLOCK_CSV = ARTIFACTS_DIR / "w27_dielectric_response_block.csv"
REPEATS_CSV = ARTIFACTS_DIR / "w27_dielectric_response_repeats.csv"
FOLDS_CSV = ARTIFACTS_DIR / "w27_dielectric_response_folds.csv"
FIGURE_PATH = ARTIFACTS_DIR / "w27_dielectric_response.png"

W26_SCAN = ARTIFACTS_DIR / "w26_dielectric_scan.csv"
W26_BORN = ARTIFACTS_DIR / "w26_born_fit.csv"
W26_GATE = ARTIFACTS_DIR / "w26_anion_gate.csv"
W26_LAYER = REPOSITORY_ROOT / "data" / "processed" / "w21_li_coordination_layer.csv"

SCHEMA = "w27_dielectric_response/summary@1"

#: The 13 response columns.  Orders are frozen here; the pre-registration quotes
#: this tuple verbatim and the guard test re-reads it.
RESPONSE_COLUMNS = (
    "born_c_neutral_eV",
    "born_c_cation_eV",
    "born_c_anion_eV",
    "born_resid_cation_200_eV",
    "born_resid_anion_200_eV",
    "born_band_cv_cation",
    "born_band_cv_anion",
    "ea_gas_eV",
    "ea_at_80p4_eV",
    "ea_window_eV",
    "homo_slope_neutral_eV",
    "lumo_slope_neutral_eV",
    "gap_slope_neutral_eV",
)

BLOCK_HEADER = ("inchikey", "status", "missing_columns") + RESPONSE_COLUMNS

SEEDS = (42, 1234, 2026, 31337, 7)
ANCHOR_SEED = 42
ANCHOR_L4 = 0.5433111678100043
REPRODUCTION_TOLERANCE = 1e-09

BAND_START = 20.0
MIN_SLOPE_POINTS = 3

PASS_DELTA = 0.0200
KILL_DELTA = 0.0050
PLACEBO_TOLERANCE = 0.0050
PLACEBO_RNG_SEED = 2026
PLACEBO_SEEDS = (ANCHOR_SEED,)

SCOREBOARD_ROWS = 457
SCOREBOARD_COMPOUNDS = 97

ARM_ANCHOR = "lever4"
ARM_BLOCK = "lever4_plus_dielectric_response"
ARM_PLACEBO = "lever4_plus_shuffled_response"
PRIMARY_REPRESENTATION = "Morgan+Physical"
SECONDARY_REPRESENTATION = "Physical"

SCOREBOARD_SHOTS_THIS_WEEK = 1
CUMULATIVE_MAIN_SCOREBOARD_ATTEMPTS = 13

CLAIM = "介电响应描述符块（W26 的 13 列 ddCOSMO 响应列）接在稠密 lever4 物理块之后，五种子均值是否把 Physical 表示推过 +0.02 的确认线"


def utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_rows(path: Path) -> list[dict[str, str]]:
    with Path(path).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, header: Sequence[str], rows: Sequence[Sequence[object]]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(list(header))
        for row in rows:
            writer.writerow(["" if value is None else value for value in row])


def as_float(text: object) -> float | None:
    if text is None:
        return None
    value = str(text).strip()
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def ols_slope(xs: Sequence[float], ys: Sequence[float]) -> float | None:
    """Ordinary least squares slope of y on x; None when x has no spread."""

    if len(xs) < MIN_SLOPE_POINTS or len(xs) != len(ys):
        return None
    x = np.asarray(xs, dtype=float)
    y = np.asarray(ys, dtype=float)
    if not np.all(np.isfinite(x)) or not np.all(np.isfinite(y)):
        return None
    if float(np.ptp(x)) <= 0.0:
        return None
    return float(np.polyfit(x, y, 1)[0])


def orbital_slopes(scan_rows: Sequence[Mapping[str, str]]) -> dict[str, dict[str, float]]:
    """Per-compound d(homo/lumo/gap)/d(1/epsilon) for the neutral state, band only."""

    table: dict[str, dict[str, tuple[float, float, float]]] = {}
    for row in scan_rows:
        if str(row.get("charge_state")) != "neutral":
            continue
        if str(row.get("status")) != "ok":
            continue
        epsilon = as_float(row.get("epsilon"))
        homo = as_float(row.get("homo_eV"))
        lumo = as_float(row.get("lumo_eV"))
        gap = as_float(row.get("gap_eV"))
        if epsilon is None or epsilon < BAND_START:
            continue
        if homo is None or lumo is None or gap is None:
            continue
        table.setdefault(str(row["inchikey"]), {})[epsilon] = (homo, lumo, gap)
    slopes: dict[str, dict[str, float]] = {}
    for inchikey, points in table.items():
        epsilons = sorted(points)
        if len(epsilons) < MIN_SLOPE_POINTS:
            continue
        x = [1.0 / epsilon for epsilon in epsilons]
        homo = ols_slope(x, [points[epsilon][0] for epsilon in epsilons])
        lumo = ols_slope(x, [points[epsilon][1] for epsilon in epsilons])
        gap = ols_slope(x, [points[epsilon][2] for epsilon in epsilons])
        if homo is None or lumo is None or gap is None:
            continue
        slopes[inchikey] = {
            "homo_slope_neutral_eV": homo,
            "lumo_slope_neutral_eV": lumo,
            "gap_slope_neutral_eV": gap,
        }
    return slopes


def birth_block(born_rows: Sequence[Mapping[str, str]]) -> dict[str, dict[str, float]]:
    """The Born-side columns: one curve per (compound, charge state) in W26."""

    wanted = {
        "neutral": ("born_c_neutral_eV", None, None),
        "cation": ("born_c_cation_eV", "born_resid_cation_200_eV", "born_band_cv_cation"),
        "anion": ("born_c_anion_eV", "born_resid_anion_200_eV", "born_band_cv_anion"),
    }
    table: dict[str, dict[str, float]] = {}
    for row in born_rows:
        state = str(row.get("charge_state"))
        if state not in wanted:
            continue
        c_column, resid_column, cv_column = wanted[state]
        entry = table.setdefault(str(row["inchikey"]), {})
        c_value = as_float(row.get("C_eV"))
        if c_value is not None:
            entry[c_column] = abs(c_value)
        if resid_column is not None:
            resid = as_float(row.get("residual_born_200_eV"))
            if resid is not None:
                entry[resid_column] = resid
        if cv_column is not None:
            cv = as_float(row.get("band_cv"))
            if cv is not None:
                entry[cv_column] = cv
    return table


def gate_block(gate_rows: Sequence[Mapping[str, str]]) -> dict[str, dict[str, float]]:
    table: dict[str, dict[str, float]] = {}
    for row in gate_rows:
        entry: dict[str, float] = {}
        gas = as_float(row.get("gas_ea_eV"))
        at_80 = as_float(row.get("ea_at_80p4_eV"))
        at_1000 = as_float(row.get("ea_at_1000_eV"))
        if gas is not None:
            entry["ea_gas_eV"] = gas
        if at_80 is not None:
            entry["ea_at_80p4_eV"] = at_80
        if gas is not None and at_1000 is not None:
            entry["ea_window_eV"] = at_1000 - gas
        table[str(row["inchikey"])] = entry
    return table


def build_block() -> tuple[list[dict[str, object]], dict[str, object]]:
    """Assemble the per-compound block from the frozen W26 artefacts."""

    scan = read_rows(W26_SCAN)
    born = read_rows(W26_BORN)
    gate = read_rows(W26_GATE)
    slopes = orbital_slopes(scan)
    born_table = birth_block(born)
    gate_table = gate_block(gate)

    keys = sorted({str(row["inchikey"]) for row in scan})
    rows: list[dict[str, object]] = []
    complete = 0
    for inchikey in keys:
        entry: dict[str, object] = {"inchikey": inchikey}
        merged: dict[str, float] = {}
        merged.update(born_table.get(inchikey, {}))
        merged.update(gate_table.get(inchikey, {}))
        merged.update(slopes.get(inchikey, {}))
        missing = [column for column in RESPONSE_COLUMNS if column not in merged]
        for column in RESPONSE_COLUMNS:
            entry[column] = merged.get(column)
        entry["status"] = "ok" if not missing else "partial"
        entry["missing_columns"] = ",".join(missing)
        if not missing:
            complete += 1
        rows.append(entry)
    total = len(rows)
    report = {
        "compounds_in_the_block": total,
        "compounds_complete": complete,
        "compounds_partial": total - complete,
        "columns": list(RESPONSE_COLUMNS),
        "slope_rule": "以中性态、epsilon >= " + str(BAND_START) + " 的网格点做 y 对 1/epsilon 的最小二乘斜率，至少 " + str(MIN_SLOPE_POINTS) + " 点",
        "sources": {
            "scan": {"path": portable_relative_path(W26_SCAN, root=REPOSITORY_ROOT), "sha256": sha256_file(W26_SCAN)},
            "born": {"path": portable_relative_path(W26_BORN, root=REPOSITORY_ROOT), "sha256": sha256_file(W26_BORN)},
            "gate": {"path": portable_relative_path(W26_GATE, root=REPOSITORY_ROOT), "sha256": sha256_file(W26_GATE)},
        },
    }
    return rows, report


def response_matrix(
    pool_rows: Sequence[Mapping[str, object]],
    block_rows: Sequence[Mapping[str, object]],
) -> tuple[np.ndarray, dict[str, object]]:
    """Broadcast the per-compound block onto pool rows.  A missing compound stays NaN."""

    table = {str(row["inchikey"]): row for row in block_rows}
    matrix = np.full((len(pool_rows), len(RESPONSE_COLUMNS)), np.nan, dtype=float)
    resolved = 0
    unresolved: set[str] = set()
    partial: set[str] = set()
    for index, row in enumerate(pool_rows):
        key = str(row["inchikey"])
        entry = table.get(key)
        if entry is None:
            unresolved.add(key)
            continue
        if str(entry.get("status")) != "ok":
            partial.add(key)
            continue
        matrix[index] = [float(entry[column]) for column in RESPONSE_COLUMNS]
        resolved += 1
    return matrix, {
        "rows_with_the_block": resolved,
        "rows_without_the_block": len(pool_rows) - resolved,
        "compounds_absent_from_the_block": len(unresolved),
        "compounds_present_but_partial": len(partial),
        "block_row_coverage": (resolved / float(len(pool_rows))) if pool_rows else 0.0,
    }


def shuffled_response(matrix: np.ndarray, seed: int) -> np.ndarray:
    """The placebo: the same columns, with the compound rows permuted.

    Declared before the run.  A placebo that is re-drawn until it looks harmless
    is not a placebo, so the generator seed is frozen in the pre-registration.
    """

    rng = np.random.default_rng(seed)
    order = rng.permutation(matrix.shape[0])
    return matrix[order]


def repeats_to_r2(repeat_rows: Sequence[Mapping[str, object]], representation: str) -> list[float]:
    return [
        float(str(row["r2"]))
        for row in repeat_rows
        if str(row.get("representation")) == representation
    ]


def evaluate_seed(
    seed: int,
    context: Mapping[str, object],
    levers: Mapping[str, np.ndarray],
    jobs: int,
) -> tuple[dict[str, dict[str, list[float]]], list[dict[str, object]], bool, dict[str, dict[str, int]]]:
    groups = list(context["groups"])
    scored = np.asarray(context["scored"], dtype=bool)
    full_base = np.asarray(context["full_base"], dtype=bool)
    morgan = np.asarray(context["morgan"])
    splits = sr.splits_for(seed, groups, scored, full_base)
    signature_ok = True
    if seed == ANCHOR_SEED:
        frozen = bn.fold_signature(context["frozen_splits"])
        if bn.fold_signature(splits) != frozen:
            signature_ok = False
    collected: dict[str, dict[str, list[float]]] = {}
    spreadsheet: list[dict[str, object]] = []
    leakage: dict[str, dict[str, int]] = {}
    for arm, physical in levers.items():
        clock = time.perf_counter()
        result = v1.evaluate_arm(
            arm + "@seed" + str(seed),
            morgan=morgan,
            physical=physical,
            target=np.asarray(context["target"]),
            temperatures=np.asarray(context["temperatures"]),
            groups=groups,
            splits=splits,
            jobs=jobs,
        )
        repeat_rows = list(result["repeat_rows"])
        collected[arm] = {
            representation: repeats_to_r2(repeat_rows, representation)
            for representation in REPRESENTATIONS
        }
        spreadsheet.extend(dict(row) for row in repeat_rows)
        leak_block = result["leak"]
        assert isinstance(leak_block, Mapping)
        leakage[arm] = {str(key): int(value) for key, value in leak_block.items()}
        summary_block = result["summary"]
        assert isinstance(summary_block, Mapping)
        print(
            "  seed " + str(seed) + " | " + arm + " | "
            + format(bn.arm_r2(summary_block), ".6f")
            + "  (" + format(time.perf_counter() - clock, ".1f") + "s)",
            flush=True,
        )
    return collected, spreadsheet, signature_ok, leakage


def configure_fonts():
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager

    available = {font.name for font in font_manager.fontManager.ttflist}
    for candidate in ("Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "DejaVu Sans"):
        if candidate in available:
            plt.rcParams["font.sans-serif"] = [candidate]
            break
    plt.rcParams["axes.unicode_minus"] = False
    return plt


def render_figure(per_seed, summary) -> bool:
    try:
        plt = configure_fonts()
    except Exception as error:
        print("font setup failed: " + type(error).__name__, flush=True)
        return False
    try:
        seeds = sorted(per_seed)
        anchor = [per_seed[seed]["anchor"] for seed in seeds]
        block = [per_seed[seed]["block"] for seed in seeds]
        delta = [per_seed[seed]["delta"] for seed in seeds]
        figure, axes = plt.subplots(1, 2, figsize=(12.6, 4.8))
        positions = np.arange(len(seeds), dtype=float)
        axes[0].plot(positions, anchor, "o-", label="lever4（锚）", color="#1f3b63")
        axes[0].plot(positions, block, "s-", label="lever4+介电响应块", color="#c0392b")
        axes[0].axhline(0.60, color="#7f8c8d", linestyle="--", linewidth=1.0, label="0.60 参考线")
        axes[0].set_xticks(positions)
        axes[0].set_xticklabels([str(seed) for seed in seeds])
        axes[0].set_xlabel("折随机种子")
        axes[0].set_ylabel("Physical 表示 R²（10 次重复均值）")
        axes[0].set_title("A 各种子读数")
        axes[0].legend(fontsize=8)
        axes[0].grid(alpha=0.25)
        colors = ["#27ae60" if value >= PASS_DELTA else ("#f39c12" if value >= KILL_DELTA else "#95a5a6") for value in delta]
        axes[1].bar(positions, delta, color=colors)
        axes[1].axhline(PASS_DELTA, color="#27ae60", linestyle="--", linewidth=1.0, label="确认线 +" + format(PASS_DELTA, ".3f"))
        axes[1].axhline(KILL_DELTA, color="#f39c12", linestyle=":", linewidth=1.0, label="部分线 +" + format(KILL_DELTA, ".3f"))
        axes[1].axhline(0.0, color="#2c3e50", linewidth=0.8)
        axes[1].set_xticks(positions)
        axes[1].set_xticklabels([str(seed) for seed in seeds])
        axes[1].set_xlabel("折随机种子")
        axes[1].set_ylabel("增 R²（块 减 锚）")
        axes[1].set_title("B 逐种子增量")
        axes[1].legend(fontsize=8)
        axes[1].grid(alpha=0.25, axis="y")
        figure.suptitle("W27 介电响应描述符块：五种子主记分牌读数（shot = 1，累计 13）", fontsize=11)
        figure.tight_layout(rect=(0, 0, 1, 0.94))
        FIGURE_PATH.parent.mkdir(parents=True, exist_ok=True)
        figure.savefig(FIGURE_PATH, dpi=150)
        plt.close(figure)
        return True
    except Exception as error:
        print("figure failure: " + type(error).__name__ + ": " + str(error), flush=True)
        plt.close("all")
        return False


def fmt(value, digits: int = 6) -> str:
    number = as_float(value)
    if number is None:
        return "n/a"
    return format(number, "." + str(digits) + "f")


def tick(text) -> str:
    return "`" + str(text) + "`"


def format_report(summary) -> str:
    lines: list[str] = []
    lines.append("# W27 结题报告：介电响应描述符块接入冻结主记分牌池")
    lines.append("")
    lines.append("- 预注册 probes/w27_dielectric_response_prereg.json（status = locked_before_run）")
    lines.append("- 臂：" + tick(ARM_ANCHOR) + "（冻结锚，full_table_lever4）对 " + tick(ARM_BLOCK) + "（锚 + 13 列 ddCOSMO 响应块）")
    lines.append("- 池：冻结主记分牌池，评分 " + str(SCOREBOARD_ROWS) + " 行 / " + str(SCOREBOARD_COMPOUNDS) + " 化合物；训练池 full_base")
    lines.append("- 主记分牌 shot：" + str(SCOREBOARD_SHOTS_THIS_WEEK) + "（累计 " + str(CUMULATIVE_MAIN_SCOREBOARD_ATTEMPTS) + "）")
    lines.append("")
    lines.append("## 1. 裁决表")
    lines.append("")
    lines.append("| 判据 | 读数 | 阈值 | 裁决 |")
    lines.append("| --- | --- | --- | --- |")
    for entry in summary["verdicts"]:
        lines.append(
            "| " + str(entry["id"]) + " " + str(entry["claim"]) + " | " + fmt(entry["value"])
            + " | " + fmt(entry["threshold"]) + " | " + str(entry["verdict"]) + " |"
        )
    lines.append("")
    lines.append("## 2. 读数")
    lines.append("")
    lines.append("| 种子 | 锚（M+P） | 块（M+P） | 增量 | 锚（P） | 块（P） | 增量（P） |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- |")
    per_seed = summary["per_seed"]
    for seed in sorted(per_seed, key=lambda item: int(item)):
        block = per_seed[seed]
        lines.append(
            "| " + str(seed) + " | " + fmt(block["anchor"]) + " | " + fmt(block["block"])
            + " | " + fmt(block["delta"]) + " | " + fmt(block["anchor_physical"])
            + " | " + fmt(block["block_physical"]) + " | " + fmt(block["delta_physical"]) + " |"
        )
    lines.append("")
    lines.append("- 主读数（" + str(summary["primary_representation"]) + "）：五种子均值 锚 " + fmt(summary["anchor_mean"])
                 + "，块 " + fmt(summary["block_mean"]) + "，增量均值 " + fmt(summary["delta_mean"]))
    lines.append("- 次读数（" + str(summary["secondary_representation"]) + "）：五种子增量均值 " + fmt(summary["delta_physical_mean"])
                 + "，最小 " + fmt(summary["delta_physical_min"]))
    lines.append("- 五种子增量：最小 " + fmt(summary["delta_min"]) + "，最大 " + fmt(summary["delta_max"]))
    lines.append("- 安慰剂（行重排）增量：" + fmt(summary["placebo_delta"]) + "（阈值 < " + fmt(PLACEBO_TOLERANCE) + "）")
    lines.append("- 覆盖：块覆盖评分化合物 " + str(summary["coverage"]["scored_compounds_with_the_block"])
                 + " / " + str(SCOREBOARD_COMPOUNDS) + "；行级覆盖 " + fmt(summary["coverage"]["block_row_coverage"], 4))
    lines.append("")
    lines.append("## 3. 口径与边界")
    lines.append("")
    for note in summary["notes"]:
        lines.append("- " + str(note))
    lines.append("")
    return "\n".join(lines) + "\n"


def build_verdict(criteria_id, claim, value, threshold, holds):
    return {"id": criteria_id, "claim": claim, "value": value, "threshold": threshold,
            "verdict": "成立" if holds else "判否"}


def dump_json(path: Path, payload) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json_stable(path, payload)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="W27 dielectric-response descriptor block")
    parser.add_argument("--jobs", type=int, default=8)
    parser.add_argument("--seeds", default=",".join(str(seed) for seed in SEEDS))
    return parser.parse_args(argv)


def parse_seeds(text) -> tuple[int, ...]:
    values = []
    for part in str(text).split(","):
        if part.strip():
            values.append(int(part.strip()))
    if not values:
        raise ValueError("no seeds")
    return tuple(values)


def main(argv=None) -> int:
    args = parse_args(argv)
    started = time.perf_counter()
    jobs = max(1, int(args.jobs))
    seeds = parse_seeds(args.seeds)

    if not PREREG_PATH.is_file():
        print("MISSING " + str(PREREG_PATH))
        return 1
    prereg = json.loads(PREREG_PATH.read_text(encoding="utf-8"))
    if str(prereg.get("status")) != "locked_before_run":
        print("the pre-registration is not locked_before_run")
        return 1

    block_rows, block_report = build_block()
    write_csv(BLOCK_CSV, BLOCK_HEADER,
              [[row.get(column) for column in BLOCK_HEADER] for row in block_rows])
    print("block: " + str(block_report["compounds_in_the_block"]) + " compounds, "
          + str(block_report["compounds_complete"]) + " complete", flush=True)

    context = sr.build_context()
    groups = [str(item) for item in context["groups"]]
    pool_rows = [{"inchikey": group} for group in groups]
    scored = np.asarray(context["scored"], dtype=bool)
    matrix, coverage = response_matrix(pool_rows, block_rows)
    scored_compounds = sorted({group for group, flag in zip(groups, scored) if flag})
    complete_keys = {str(row["inchikey"]) for row in block_rows if str(row["status"]) == "ok"}
    coverage["scored_compounds_with_the_block"] = sum(
        1 for key in scored_compounds if key in complete_keys
    )
    coverage["scored_compounds"] = len(scored_compounds)
    print("pool: " + str(len(pool_rows)) + " rows | block covers " + str(coverage["rows_with_the_block"])
          + " rows and " + str(coverage["scored_compounds_with_the_block"]) + "/"
          + str(len(scored_compounds)) + " scored compounds", flush=True)

    lever4 = np.asarray(context["physical_lever4"])
    levers = {ARM_ANCHOR: lever4, ARM_BLOCK: np.hstack([lever4, matrix])}

    per_seed = {}
    spreadsheet = []
    leakage = {}
    for seed in seeds:
        collected, rows, signature_ok, leak = evaluate_seed(seed, context, levers, jobs)
        if not signature_ok:
            print("seed " + str(seed) + ": the fold assignment moved; refusing to continue")
            return 1
        for arm, block in leak.items():
            leakage[str(seed) + ":" + arm] = block
        anchor_reading = float(np.mean(collected[ARM_ANCHOR][PRIMARY_REPRESENTATION]))
        block_reading = float(np.mean(collected[ARM_BLOCK][PRIMARY_REPRESENTATION]))
        anchor_physical = float(np.mean(collected[ARM_ANCHOR][SECONDARY_REPRESENTATION]))
        block_physical = float(np.mean(collected[ARM_BLOCK][SECONDARY_REPRESENTATION]))
        per_seed[seed] = {"anchor": anchor_reading, "block": block_reading,
                          "delta": block_reading - anchor_reading,
                          "anchor_physical": anchor_physical, "block_physical": block_physical,
                          "delta_physical": block_physical - anchor_physical}
        spreadsheet.extend(rows)

    anchor_ok = True
    anchor_gap = None
    if ANCHOR_SEED in per_seed:
        anchor_gap = abs(per_seed[ANCHOR_SEED]["anchor"] - ANCHOR_L4)
        anchor_ok = anchor_gap <= REPRODUCTION_TOLERANCE
    if not anchor_ok:
        print("the seed-42 lever4 anchor did not reproduce; refusing to report anything else")
        return 1

    placebo_delta = None
    if ANCHOR_SEED in seeds:
        placebo_matrix = shuffled_response(matrix, PLACEBO_RNG_SEED)
        placebo_levers = {ARM_PLACEBO: np.hstack([lever4, placebo_matrix])}
        collected, _, _, _ = evaluate_seed(ANCHOR_SEED, context, placebo_levers, jobs)
        placebo_arm = float(np.mean(collected[ARM_PLACEBO][PRIMARY_REPRESENTATION]))
        placebo_delta = placebo_arm - per_seed[ANCHOR_SEED]["anchor"]

    deltas = [per_seed[seed]["delta"] for seed in sorted(per_seed)]
    delta_mean = float(np.mean(deltas)) if deltas else float("nan")
    delta_min = float(np.min(deltas)) if deltas else float("nan")
    delta_max = float(np.max(deltas)) if deltas else float("nan")
    physical_deltas = [per_seed[seed]["delta_physical"] for seed in sorted(per_seed)]
    delta_physical_mean = float(np.mean(physical_deltas)) if physical_deltas else float("nan")
    delta_physical_min = float(np.min(physical_deltas)) if physical_deltas else float("nan")
    anchor_mean = float(np.mean([per_seed[s]["anchor"] for s in sorted(per_seed)])) if per_seed else float("nan")
    block_mean = float(np.mean([per_seed[s]["block"] for s in sorted(per_seed)])) if per_seed else float("nan")

    leak_folds = sum(block["folds_with_a_straddling_compound"] for block in leakage.values())
    placebo_clean = bool(placebo_delta is not None and abs(placebo_delta) < PLACEBO_TOLERANCE)

    verdicts = [
        build_verdict("H27a", "seed 42 锚（full_table_lever4，Physical）逐位复现", anchor_gap,
                      REPRODUCTION_TOLERANCE, bool(anchor_ok)),
        build_verdict("H27b", "跨折泄漏：含跨界化合物的折数（全部种子、两个臂）", float(leak_folds), 0.0,
                      bool(leak_folds == 0)),
        build_verdict("H27c", "确认线：五种子 Morgan+Physical 增量均值 >= +0.02", delta_mean, PASS_DELTA,
                      bool(np.isfinite(delta_mean) and delta_mean >= PASS_DELTA)),
        build_verdict("H27d", "部分线：五种子 Morgan+Physical 增量均值 >= +0.005", delta_mean, KILL_DELTA,
                      bool(np.isfinite(delta_mean) and delta_mean >= KILL_DELTA)),
        build_verdict("H27e", "安慰剂惰性：行重排后的增量绝对值 < 0.005", placebo_delta, PLACEBO_TOLERANCE,
                      placebo_clean),
        build_verdict("H27f", "覆盖纪律：块覆盖评分化合物 97/97", float(coverage["scored_compounds_with_the_block"]),
                      float(SCOREBOARD_COMPOUNDS),
                      bool(coverage["scored_compounds_with_the_block"] == SCOREBOARD_COMPOUNDS)),
        build_verdict("H27g", "次读数（描述性）：五种子 Physical 表示增量均值 >= +0.005", delta_physical_mean,
                      KILL_DELTA, bool(np.isfinite(delta_physical_mean) and delta_physical_mean >= KILL_DELTA)),
    ]

    notes = [
        "本臂把 W26 的 13 列 ddCOSMO 响应列接在稠密 lever4 块之后；池、评分掩码、分组切分器、拟合器（max_depth 2 / 200 树）与五种子集合全部未动。",
        "缺行不插补：块在 W26 名册之外的化合物上留 NaN，交给 XGBoost 自带的缺失值处理；不计算任何折内统计量，因此没有折统计量可以泄漏。",
        "块里没有任何一列触及被测的介电常数：每一列都是中性或离子化溶质对给定 epsilon 连续介质的响应，不是scoreboard 要预测的那个 epsilon。",
        "安慰剂的行重排生成器种子在预注册里冻结（" + str(PLACEBO_RNG_SEED) + "）；重排只在给定种子下做一次，不重抽到达标。",
        "主记分牌 shot = " + str(SCOREBOARD_SHOTS_THIS_WEEK) + "（累计 " + str(CUMULATIVE_MAIN_SCOREBOARD_ATTEMPTS) + "）；四个冻结读数（0.4091179943351143 / 0.4766400383507876 / 0.5861142332208197 / 0.6216672295270079）未动。",
        "本臂交付的是主记分牌读数，不外推到其他名册；W26 的 242 分子池与主记分牌池的化合物集合不同，覆盖只按本报告第 2 节给出的口径宣读。",
    ]

    summary = {
        "schema": SCHEMA,
        "task": "week27_dielectric_response_block",
        "generated_at_utc": utc_now(),
        "elapsed_seconds": time.perf_counter() - started,
        "preregistration": {
            "path": portable_relative_path(PREREG_PATH, root=REPOSITORY_ROOT),
            "sha256": sha256_file(PREREG_PATH),
            "status": str(prereg.get("status")),
        },
        "claim": CLAIM,
        "pool": {"rows": len(pool_rows), "scored_rows": int(scored.sum()),
                 "scored_compounds": len(scored_compounds),
                 "matches_preregistration": bool(int(scored.sum()) == SCOREBOARD_ROWS
                                                 and len(scored_compounds) == SCOREBOARD_COMPOUNDS)},
        "block": block_report,
        "coverage": coverage,
        "seeds": list(seeds),
        "per_seed": {str(seed): per_seed[seed] for seed in sorted(per_seed)},
        "anchor_expected": ANCHOR_L4,
        "anchor_gap": anchor_gap,
        "anchor_mean": anchor_mean,
        "block_mean": block_mean,
        "primary_representation": PRIMARY_REPRESENTATION,
        "secondary_representation": SECONDARY_REPRESENTATION,
        "delta_mean": delta_mean,
        "delta_physical_mean": delta_physical_mean,
        "delta_physical_min": delta_physical_min,
        "delta_min": delta_min,
        "delta_max": delta_max,
        "placebo_delta": placebo_delta,
        "placebo_rng_seed": PLACEBO_RNG_SEED,
        "leakage": leakage,
        "verdicts": verdicts,
        "notes": notes,
        "main_scoreboard_attempts_delta": SCOREBOARD_SHOTS_THIS_WEEK,
        "cumulative_main_scoreboard_attempts": CUMULATIVE_MAIN_SCOREBOARD_ATTEMPTS,
        "figures": {"main": FIGURE_PATH.name},
        "artifacts": {"block": BLOCK_CSV.name, "repeats": REPEATS_CSV.name},
    }

    write_csv(REPEATS_CSV,
              ["arm", "representation", "repeat", "r2", "mae", "rmse", "spearman",
               "mae_lt20", "mae_20_60", "mae_gt60"],
              [[row.get("arm"), row.get("representation"), row.get("repeat"), row.get("r2"),
                row.get("mae"), row.get("rmse"), row.get("spearman"),
                row.get("mae_lt20"), row.get("mae_20_60"), row.get("mae_gt60")]
               for row in spreadsheet])

    figures_ok = render_figure(per_seed, summary)
    report = format_report(summary)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with REPORT_PATH.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(report)
    summary["figures"]["written"] = bool(figures_ok)

    dump_json(SUMMARY_PATH, summary)
    dump_json(PLACEBO_SUMMARY_PATH, {
        "schema": SCHEMA,
        "task": "week27_dielectric_response_block_placebo",
        "generated_at_utc": utc_now(),
        "rng_seed": PLACEBO_RNG_SEED,
        "anchor_arm": ARM_ANCHOR,
        "placebo_arm": ARM_PLACEBO,
        "placebo_delta": placebo_delta,
        "tolerance": PLACEBO_TOLERANCE,
        "clean": placebo_clean,
    })

    for entry in verdicts:
        print("  " + str(entry["id"]) + " " + str(entry["verdict"]) + " " + fmt(entry["value"])
              + " (阈值 " + fmt(entry["threshold"]) + ")", flush=True)
    print("delta_mean " + fmt(delta_mean) + " | placebo " + fmt(placebo_delta)
          + " | report " + portable_relative_path(REPORT_PATH, root=REPOSITORY_ROOT), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
