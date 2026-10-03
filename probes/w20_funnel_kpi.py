"""Week 20 -- W20-8: the funnel KPI board and the capped-ladder revision.

This module fits no model and takes no shot number.  It (1) *pins* the funnel
KPI board -- the three groups of ranking, coverage/cost and discipline items
that hang off the D6 ranking key -- and (2) reads the ranking KPIs out of an
*existing frozen* out-of-fold prediction table, so the board has a measured
anchor rather than only definitions.

No R2 KPI, on purpose
---------------------
The project diagnosis is "ranking is learned, magnitude is not".  R2 measures
magnitude, so it is excluded from the board by construction, not by omission.
AUC>15, AUC>30, Spearman and top-k enrichment measure order; they are the
items that stay.

The naming discipline
----------------------
The literature also uses the acronym KPI, for "Knowledge-based electrolyte
Property prediction Integration" (Gao et al., Angew. Chem. Int. Ed. 2024,
DOI 10.1002/anie.202416506) -- a framework name, not a metric.  This file keeps
only one sense, the funnel KPI *metrics* below, and labels the other
unmistakably as a literature framework name unrelated to these metrics.

The capped-ladder revision
---------------------------
The appendix X-2 ladder row "0.58-0.65" assumed the compound coverage would
double.  Week 17 refuted that premise: the open-licence roster is 153 compounds
with an upper bound of 157 (widest 161), a net-new bound of +4.  That row is
therefore marked ``capped`` here.

What this module does not do
----------------------------
It makes no main-scoreboard attempt (cumulative stays 11), writes no model, and
mutates no frozen artefact.  ``produces_reading`` is false and ``promoted`` is
false.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))
try:  # W40-B import shim: works as `probes.<mod>` and as a direct script
    from probes.export_results_common import write_json_stable
except ImportError:  # direct execution: probes/ is sys.path[0]
    from export_results_common import write_json_stable


PREDICTIONS_PATH = (
    REPOSITORY_ROOT
    / "probes"
    / "artifacts"
    / "dielectric_coverage_paired_benchmark_predictions.csv"
)
REPEATS_PATH = (
    REPOSITORY_ROOT / "data" / "processed" / "dielectric_representation_ablation_repeats.csv"
)
SUMMARY_PATH = REPOSITORY_ROOT / "probes" / "w20_funnel_kpi_summary.json"
FIGURE_PATH = REPOSITORY_ROOT / "probes" / "artifacts" / "w20_funnel_kpi_ranking.png"

#: The arm whose pooled out-of-fold R2 reproduces the frozen baseline
#: 0.4091179943351143 bit-for-bit.  Declared, not chosen after the fact.
ARM_PROTOCOL = "paired_base"
ARM_REPRESENTATION = "Morgan+Physical"
ARM_BASELINE_R2 = 0.4091179943351143

#: W18 added auc_gt15 / auc_gt30 to evaluate_repeat and to the *_repeats.csv
#: outputs; the repeats file is cited so the columns have a named owner.
AUC_COLUMN_OWNER = "probes/dielectric_representation_ablation.py::evaluate_repeat"
AUC_REPEATS_FILE = "data/processed/dielectric_representation_ablation_repeats.csv"

MAIN_SCOREBOARD_CUMULATIVE_ATTEMPTS = 11
W20_MAIN_SCOREBOARD_ATTEMPTS = 0
W20_LANES = 8
W20_PROMOTED_LANES = 0

RED_LINE_VIOLATIONS = 0

LITERATURE_KPI_FRAMEWORK: dict[str, str] = {
    "acronym": "KPI",
    "expansion": "Knowledge-based electrolyte Property prediction Integration",
    "kind": "literature framework name",
    "doi": "10.1002/anie.202416506",
    "disclaimer": "\u6587\u732e\u6846\u67b6\u540d\uff0c\u4e0e\u672c\u6587\u6307\u6807\u65e0\u5173",
}

#: The three KPI groups.  Each item is defined; measured items carry a value.
KPI_GROUPS: tuple[dict[str, Any], ...] = (
    {
        "group": "ranking",
        "label": "\u6392\u5e8f\u7c7b",
        "items": ("auc_gt15", "auc_gt30", "spearman", "top_k_enrichment"),
    },
    {
        "group": "coverage_cost",
        "label": "\u8986\u76d6\u4e0e\u6210\u672c\u7c7b",
        "items": (
            "scorable_compounds",
            "in_domain_coverage",
            "compute_cost_per_candidate",
            "experiment_cost_per_candidate",
        ),
    },
    {
        "group": "discipline",
        "label": "\u7eaa\u5f8b\u7c7b",
        "items": (
            "promoted_false_count",
            "main_scoreboard_attempts",
            "placebo_collapse",
            "redline_violations",
        ),
    },
)

FORBIDDEN_KPIS: tuple[str, ...] = ("r2",)
FORBIDDEN_KPI_REASON = (
    "the diagnosis is that ranking is learned and magnitude is not; R2 measures "
    "magnitude, so it is not a funnel KPI"
)

#: Appendix X-2, the row this revision caps.
LADDER_ROW_BEFORE: dict[str, str] = {
    "rung": "0.58\u20130.65",
    "carrier": (
        "\u5316\u5408\u7269\u8986\u76d6\u518d\u7ffb\u500d + \u76f2\u533a\u9776\u5411\u7279\u5f81 + \u76ee\u6807\u53d8\u6362"
    ),
    "premise": "\u5316\u5408\u7269\u8986\u76d6\u518d\u7ffb\u500d",
    "status_before": "next_rung",
    "source": "tests/fixtures/manual_appendix_j_snapshot.md::X-2",
}

#: The W17 refutation chain: widest bound 161, then 157, then the roster 153.
CAP_CHAIN: tuple[int, ...] = (161, 157, 153)
NET_NEW_UPPER_BOUND = 4
CAP_REASON = (
    'the open-licence roster is 153 compounds with an upper bound of 157 '
    '(widest 161); the doubled-compound premise is refuted, so the rung is capped'
)


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _safe_auc(target: list[int], score: list[float]) -> float | None:
    import numpy as np
    from sklearn.metrics import roc_auc_score

    labels = np.asarray(target, dtype=int)
    if labels.min() == labels.max():
        return None
    return float(roc_auc_score(labels, np.asarray(score, dtype=float)))


def _spearman(xs: list[float], ys: list[float]) -> float | None:
    from scipy.stats import spearmanr

    value = float(spearmanr(xs, ys).statistic)
    return None if math.isnan(value) else value


def _arm_rows(repeat: str | None = None) -> list[dict[str, str]]:
    rows = [
        row
        for row in read_rows(PREDICTIONS_PATH)
        if row["protocol"] == ARM_PROTOCOL and row["representation"] == ARM_REPRESENTATION
    ]
    if repeat is not None:
        rows = [row for row in rows if row["repeat"] == repeat]
    return rows


def pooled_ranking_kpis() -> dict[str, Any]:
    """AUC>15 / AUC>30 / Spearman over the whole frozen out-of-fold table."""

    rows = _arm_rows()
    target = [float(row["target"]) for row in rows]
    prediction = [float(row["prediction"]) for row in rows]
    return {
        "n_rows": len(rows),
        "auc_gt15": _safe_auc([int(value > 15.0) for value in target], prediction),
        "auc_gt30": _safe_auc([int(value > 30.0) for value in target], prediction),
        "spearman": _spearman(target, prediction),
        "source": "probes/artifacts/dielectric_coverage_paired_benchmark_predictions.csv",
    }


def top_k_enrichment(ks: Sequence[int] = (10, 20, 50), repeat: str = "0") -> dict[str, Any]:
    """Enrichment of epsilon > 30 in the top-k by prediction, per repeat."""

    rows = _arm_rows(repeat=repeat)
    target = [float(row["target"]) for row in rows]
    prediction = [float(row["prediction"]) for row in rows]
    order = sorted(range(len(rows)), key=lambda index: -prediction[index])
    positives = sum(1 for value in target if value > 30.0)
    base_rate = positives / len(target) if target else 0.0
    out: dict[str, Any] = {
        "repeat": repeat,
        "n_rows": len(rows),
        "positives_gt30": positives,
        "base_rate": base_rate,
    }
    for k in ks:
        hits = sum(1 for index in order[:k] if target[index] > 30.0)
        precision = hits / k if k else 0.0
        out[f"top{k}_hits_gt30"] = hits
        out[f"top{k}_precision"] = precision
        out[f"top{k}_enrichment"] = precision / base_rate if base_rate else 0.0
    return out


def repeats_file_auc_columns() -> dict[str, Any]:
    """Confirm the W18 AUC columns exist in the frozen repeats file."""

    with REPEATS_PATH.open("r", encoding="utf-8", newline="") as handle:
        fieldnames = list(csv.DictReader(handle).fieldnames or ())
    return {
        "path": "data/processed/dielectric_representation_ablation_repeats.csv",
        "has_auc_gt15": "auc_gt15" in fieldnames,
        "has_auc_gt30": "auc_gt30" in fieldnames,
        "owner": AUC_COLUMN_OWNER,
    }


def coverage_kpis() -> dict[str, Any]:
    """Coverage and cost items.  Frozen coverage is measured; cost is declared."""

    return {
        "scorable_compounds": 97.0,
        "in_domain_compounds": 57.0,
        "in_domain_coverage": 57.0 / 97.0,
        "coverage_source": "probes/dielectric_applicability_domain_summary.json#endpoint.D1",
        "compute_cost_per_candidate": None,
        "compute_cost_unit": "xTB single-point CPU-seconds (declared, uncalibrated)",
        "experiment_cost_per_candidate": None,
        "experiment_cost_unit": "one dielectric measurement (declared, uncalibrated)",
        "cost_status": "defined_not_measured",
    }


def discipline_kpis() -> dict[str, Any]:
    return {
        "promoted_false_count": W20_LANES - W20_PROMOTED_LANES,
        "w20_lanes": W20_LANES,
        "main_scoreboard_attempts": W20_MAIN_SCOREBOARD_ATTEMPTS,
        "cumulative_main_scoreboard_attempts": MAIN_SCOREBOARD_CUMULATIVE_ATTEMPTS,
        "placebo_collapse": (
            "each lane ships a placebo; the three governance lanes fit no model, "
            "so their placebo is a null ablation (no model, no reading to collapse)"
        ),
        "redline_violations": RED_LINE_VIOLATIONS,
    }


def capping_revision() -> dict[str, Any]:
    return {
        "row": dict(LADDER_ROW_BEFORE),
        "status_after": "capped",
        "cap_chain": list(CAP_CHAIN),
        "net_new_upper_bound": NET_NEW_UPPER_BOUND,
        "reason": CAP_REASON,
        "refuted_by": "Week 17 open-licence source sweep (reports/decisions_log.md 28.36 / 28.37)",
    }


def plan() -> dict[str, Any]:
    return {
        "schema_version": "w20_funnel_kpi_plan_v0",
        "task": "week20_w20_8_funnel_kpi_board",
        "status": "registered_no_model",
        "produces_reading": False,
        "promoted": False,
        "main_scoreboard_untouched": True,
        "scoreboard_attempts_delta": 0,
        "shot_number_taken": None,
        "kpi_groups": [dict(group) for group in KPI_GROUPS],
        "forbidden_kpis": list(FORBIDDEN_KPIS),
        "forbidden_kpi_reason": FORBIDDEN_KPI_REASON,
        "literature_kpi_framework": dict(LITERATURE_KPI_FRAMEWORK),
        "arm": {
            "protocol": ARM_PROTOCOL,
            "representation": ARM_REPRESENTATION,
            "baseline_r2": ARM_BASELINE_R2,
        },
        "auc_column_owner": AUC_COLUMN_OWNER,
        "capping_revision": capping_revision(),
    }


def run() -> dict[str, Any]:
    return {
        **plan(),
        "status": "executed_descriptive",
        "ranking": {
            "pooled": pooled_ranking_kpis(),
            "top_k": top_k_enrichment(),
            "auc_columns": repeats_file_auc_columns(),
        },
        "coverage_cost": coverage_kpis(),
        "discipline": discipline_kpis(),
    }


def write_figure(path: Path = FIGURE_PATH, repeat: str = "0") -> Path:
    """Draw the ranking-KPI story: strong order, no magnitude (no R2 KPI)."""

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    pooled = pooled_ranking_kpis()
    topk = top_k_enrichment(repeat=repeat)
    ks = [10, 20, 50]
    precision = [topk[f"top{k}_precision"] for k in ks]
    enrichment = [topk[f"top{k}_enrichment"] for k in ks]
    base_rate = topk["base_rate"]

    fig, (ax_left, ax_right) = plt.subplots(1, 2, figsize=(11.0, 4.8))

    ax_left.plot(ks, precision, "o-", color="#1f4e79", lw=2.0, ms=7,
                 label="top-k precision (epsilon > 30)")
    ax_left.axhline(base_rate, color="#b22222", ls="--", lw=1.3,
                    label=f"base rate = {base_rate:.5f}")
    for k, value in zip(ks, precision):
        ax_left.annotate(f"{value:.2f}", (k, value),
                         textcoords="offset points", xytext=(7, 7))
    ax_left.set_xlabel("k (candidates ranked by prediction)")
    ax_left.set_ylabel("precision in top-k (epsilon > 30)")
    ax_left.set_title("Top-k precision vs base rate")
    ax_left.set_xticks(ks)
    ax_left.set_ylim(0.0, 1.05)
    ax_left.grid(alpha=0.3)
    ax_left.legend(loc="lower right", fontsize=9)

    ax_right.bar([str(k) for k in ks], enrichment, color="#2e7d32", alpha=0.85)
    for index, value in enumerate(enrichment):
        ax_right.annotate(f"{value:.4f}", (index, value),
                          textcoords="offset points", xytext=(0, 4), ha="center")
    ax_right.axhline(1.0, color="#555555", ls=":", lw=1.0)
    ax_right.set_xlabel("k")
    ax_right.set_ylabel("enrichment over base rate")
    ax_right.set_title("Top-k enrichment (epsilon > 30)")
    ax_right.set_ylim(0.0, max(enrichment) * 1.95)
    ax_right.grid(alpha=0.3, axis="y")

    annotation = "\n".join([
        "Pooled ranking KPIs (frozen OOF, 4570 rows)",
        f"auc_gt15  = {pooled['auc_gt15']:.16f}",
        f"auc_gt30  = {pooled['auc_gt30']:.16f}",
        f"spearman  = {pooled['spearman']:.16f}",
        "",
        "Ranking is learned; magnitude is not.",
        "R2 is deliberately NOT a funnel KPI.",
    ])
    ax_right.text(0.02, 0.98, annotation, transform=ax_right.transAxes,
                  va="top", ha="left", fontsize=8.5, family="monospace",
                  bbox={"boxstyle": "round", "fc": "#f5f5f5", "ec": "#999999"})

    fig.suptitle("W20-8 funnel KPI board: ranking learned, magnitude not")
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, bbox_inches="tight", dpi=150)
    plt.close(fig)
    return path


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--plan", action="store_true", help="print the pinned plan and exit")
    parser.add_argument("--write-summary", action="store_true", help="write the summary JSON")
    parser.add_argument(
        "--write-figure", action="store_true", help="write the ranking KPI figure"
    )
    parser.add_argument("--summary", type=Path, default=SUMMARY_PATH)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.plan:
        print(json.dumps(plan(), ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    if args.write_figure:
        write_figure()
    summary = run()
    if args.write_summary:
        write_json_stable(args.summary, summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover - manual inspection helper
    raise SystemExit(main())
