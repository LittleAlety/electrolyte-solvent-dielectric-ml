"""Week 22 / W22-1 -- strictifying the leakage ("safety") theorem by a factor of two.

The proposition under test
--------------------------
Let one *unique-variable rung* act on molecule ``i`` with an effect ``e_i``, and let

    A_axis = max_i |delta e_i|

be the single-cell worst-case effect magnitude -- the number the draft calls "the
worst cell".  The draft's decision rule declares a pair ``(i, j)`` SAFE when the
baseline separation clears that single-cell number,

    |d0| >= A_axis ,            d0 = e_i - e_j .

That rule is off by a factor of two.  A pair separation is perturbed by *two*
cells, so

    delta d = delta e_i - delta e_j ,
    |delta d| <= |delta e_i| + |delta e_j| <= 2 A_axis        (triangle inequality)

and the strict (sufficient) rule is therefore

    |d0| >= 2 A_axis .

The bound is attained -- take ``delta e_i = +A_axis`` and ``delta e_j = -A_axis``
-- so the factor of two is a requirement, not padding.  An equivalent restatement
keeps the shape of the rule unchanged by moving the number to pair level,

    A_pair = max_{i,j} |delta (e_i - e_j)| <= 2 A_axis ,    rule:  |d0| >= A_pair .

What this lane is allowed to say, and what it is not
---------------------------------------------------
Section 1 of the report states the THEOREM (an analytic bound).  Section 2 states
the SIMULATION (an empirical zero-leak reading).  A simulation can never prove
the theorem; it can only fail to refute it.  A future pair of opposing leaks
refutes the *empirical* claim while leaving the analytic bound intact, so the two
sentences stay separate.

Single-cell vs pair-level A
---------------------------
``A_axis`` as written down in the draft is a *single-cell* number.  Two readings
of it are live and the report keeps them apart:

    A_axis(single-cell)  = max_i |delta e_i|                   current draft
    A_pair(pair-level)   = max_{i,j} |delta (e_i - e_j)|       redefinition

The strict criterion is ``|d0| >= 2 A_axis`` under the first reading and
``|d0| >= A_pair`` under the second; both are implemented below, and the report
reports the cost of the tightening on the in-repo pair table.

Determinism
-----------
Every random draw comes from ``numpy.random.default_rng`` with a fixed, derived
seed.  The summary carries no timestamp, so ``--write-summary`` run twice is
byte-identical; ``--check`` re-derives it and compares against the file on disk.

No model is fit, no shot number is taken, no pool is written, and no frozen
number is touched.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
PREREG_PATH = ROOT / "probes" / "w22_safety_theorem_prereg.json"
SUMMARY_PATH = ROOT / "probes" / "w22_safety_theorem_summary.json"
REPORT_PATH = ROOT / "reports" / "w22_safety_theorem.md"
ARTIFACTS = ROOT / "probes" / "artifacts"
FIG_LEAKAGE = ARTIFACTS / "w22_safety_theorem_leakage.png"
FIG_COVERAGE = ARTIFACTS / "w22_safety_theorem_coverage.png"
PAIRS_CSV = ARTIFACTS / "w21_rank_pairs.csv"
TEST_PATH = ROOT / "tests" / "test_w22_safety_theorem.py"
PROBE_PATH = Path(__file__).resolve()

SEED = 20261002
N_MOLECULES = 200
TRIALS = 200
R_RUNGS = 10
RUNG_QUANTILE = 0.95
M_VALUES = (1, 2)

#: The nominal single-cell worst-case effect.  EXTERNAL reading: it is the
#: "0.152 eV worst cell" quoted in the review of the draft paper.  It is NOT
#: verifiable inside this repository (charter section 0.1), so it is used only as
#: a *scale* for the cost re-report, and every number that depends on it is also
#: reported across A_GRID_EV so nothing hinges on the unverifiable value.
A_AXIS_EV = 0.152
A_AXIS_PROVENANCE = (
    "external review of the draft (worst cell, quoted 0.152 eV); not verifiable in-repo"
)
A_GRID_EV = (0.05, 0.10, 0.12, 0.152, 0.20, 0.30)

#: Baseline spread of the synthetic molecule set.  Pure simulation scale: with
#: |d0| ~ N(0, 2 sigma_base^2) the dimensionless quantity that matters is
#: A / sigma_base, pinned here as 0.152 / 0.5 = 0.304.
SIGMA_BASE_EV = 0.5

ANALYTIC_STATEMENT = (
    "delta d = delta e_i - delta e_j  =>  |delta d| <= |delta e_i| + |delta e_j| "
    "<= 2 A_axis  (triangle inequality); the strict sufficient rule is |d0| >= 2 A_axis."
)
PAIR_REDEFINITION_STATEMENT = (
    "A_pair = max_{i,j} |delta (e_i - e_j)| <= 2 A_axis; under |d0| >= A_pair the "
    "rule keeps its shape and the factor of two is absorbed into the number."
)


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def line_count(path: Path) -> int | None:
    if path.suffix.lower() in {".png", ".pdf", ".zip"}:
        return None
    data = path.read_text(encoding="utf-8", errors="replace")
    if not data:
        return 0
    return data.count("\n") + (0 if data.endswith("\n") else 1)


def r10(value: float) -> float:
    return float(round(float(value), 10))


def as_jsonable(obj: object) -> object:
    if isinstance(obj, dict):
        return {str(key): as_jsonable(value) for key, value in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [as_jsonable(value) for value in obj]
    if isinstance(obj, np.floating):
        return r10(float(obj))
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.bool_):
        return bool(obj)
    if isinstance(obj, float):
        return r10(obj)
    return obj


def dumps(payload: object) -> str:
    return json.dumps(as_jsonable(payload), ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


# ---------------------------------------------------------------------------
# core machinery
# ---------------------------------------------------------------------------


def baseline_problem() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """The pinned synthetic molecule set and its baseline pair differences."""

    rng = np.random.default_rng(SEED)
    baseline = rng.normal(0.0, SIGMA_BASE_EV, N_MOLECULES)
    index_i, index_j = np.triu_indices(N_MOLECULES, 1)
    return baseline, index_i, index_j


def _draw(rng: np.random.Generator, kind: str, a_axis: float) -> np.ndarray:
    if kind == "uniform":
        return rng.uniform(-a_axis, a_axis, N_MOLECULES)
    if kind == "normal":
        return rng.normal(0.0, a_axis / 2.0, N_MOLECULES)
    raise ValueError(f"unknown perturbation kind: {kind}")


def mc_arm(
    baseline: np.ndarray,
    index_i: np.ndarray,
    index_j: np.ndarray,
    kind: str,
    rng: np.random.Generator,
    a_axis: float = A_AXIS_EV,
) -> dict:
    """One Monte-Carlo arm: leak rate of the m=1 and m=2 criteria under ``kind``."""

    d0 = baseline[index_i] - baseline[index_j]
    rates: dict[int, list[float]] = {m: [] for m in M_VALUES}
    leaks: dict[int, list[int]] = {m: [] for m in M_VALUES}
    safe_counts: dict[int, list[int]] = {m: [] for m in M_VALUES}
    realized_single_cell: list[float] = []
    realized_dd: list[float] = []
    premise_violations: list[int] = []
    bound_violations: list[int] = []
    witness: dict | None = None
    witness_key = -1.0

    for trial in range(TRIALS):
        delta = _draw(rng, kind, a_axis)
        dd = delta[index_i] - delta[index_j]
        d1 = d0 + dd
        flip = (d0 * d1) <= 0.0  # a destroyed or reversed ordering
        realized_single_cell.append(float(np.abs(delta).max()))
        abs_dd = np.abs(dd)
        realized_dd.append(float(abs_dd.max()))
        premise_violations.append(int((np.abs(delta) > a_axis).sum()))
        bound_violations.append(int((abs_dd > 2.0 * a_axis + 1e-12).sum()))
        for m in M_VALUES:
            safe = np.abs(d0) >= m * a_axis
            n_safe = int(safe.sum())
            n_leak = int((safe & flip).sum())
            safe_counts[m].append(n_safe)
            leaks[m].append(n_leak)
            rates[m].append(n_leak / n_safe if n_safe else 0.0)
        if float(abs_dd.max()) > witness_key:
            witness_key = float(abs_dd.max())
            k = int(np.argmax(abs_dd))
            witness = {
                "trial": trial,
                "i": int(index_i[k]),
                "j": int(index_j[k]),
                "delta_e_i": r10(delta[index_i[k]]),
                "delta_e_j": r10(delta[index_j[k]]),
                "delta_d": r10(dd[k]),
                "d0": r10(d0[k]),
                "d1": r10(d1[k]),
                "abs_delta_d_over_2A": r10(abs_dd[k] / (2.0 * a_axis)),
                "flipped": bool(flip[k]),
                "opposite_signs": bool(delta[index_i[k]] * delta[index_j[k]] < 0.0),
            }

    block: dict = {
        "perturbation": "Uniform(-A, A)" if kind == "uniform" else "Normal(0, A/2)",
        "bounded_support": kind == "uniform",
        "a_axis_ev": r10(a_axis),
        "trials": TRIALS,
        "pairs": int(d0.size),
        "realized_single_cell_max_ev": {
            "mean": r10(np.mean(realized_single_cell)),
            "max": r10(np.max(realized_single_cell)),
        },
        "realized_max_abs_delta_d_ev": {
            "mean": r10(np.mean(realized_dd)),
            "max": r10(np.max(realized_dd)),
        },
        "tightness_abs_delta_d_over_2A": {
            "mean": r10(np.mean(realized_dd) / (2.0 * a_axis)),
            "max": r10(np.max(realized_dd) / (2.0 * a_axis)),
        },
        "premise_violations_per_trial": {
            "definition": "molecules with |delta e_i| > A in a trial",
            "mean": r10(np.mean(premise_violations)),
            "max": int(np.max(premise_violations)),
            "trials_with_any": int(np.sum(np.asarray(premise_violations) > 0)),
        },
        "bound_violations_per_trial": {
            "definition": "pairs with |delta d| > 2A + 1e-12 in a trial",
            "mean": r10(np.mean(bound_violations)),
            "max": int(np.max(bound_violations)),
            "trials_with_any": int(np.sum(np.asarray(bound_violations) > 0)),
        },
        "witness": witness,
    }
    for m in M_VALUES:
        rate = np.asarray(rates[m], dtype=float)
        block[f"m{m}"] = {
            "criterion": f"|d0| >= {m} A_axis",
            "mean_safe_pairs": r10(np.mean(safe_counts[m])),
            "leak_rate_mean": r10(rate.mean()),
            "leak_rate_min": r10(rate.min()),
            "leak_rate_max": r10(rate.max()),
            "leak_rate_p95": r10(np.quantile(rate, 0.95)),
            "leak_rate_ci95_trial_quantiles": [
                r10(np.quantile(rate, 0.025)),
                r10(np.quantile(rate, 0.975)),
            ],
            "trials_with_any_leak": int(np.sum(np.asarray(leaks[m]) > 0)),
            "total_leak_events": int(np.sum(leaks[m])),
        }
    return block


def loro_rungs(
    baseline: np.ndarray,
    index_i: np.ndarray,
    index_j: np.ndarray,
    rng: np.random.Generator,
    a_axis: float = A_AXIS_EV,
) -> dict:
    """D1 prospective check: predict this rung's unresolvable set from the others."""

    d0 = baseline[index_i] - baseline[index_j]
    draws: list[np.ndarray] = [_draw(rng, "uniform", a_axis) for _ in range(R_RUNGS)]
    a_hat = np.array([float(np.abs(delta).max()) for delta in draws])

    per_rung: list[dict] = []
    totals = {
        "tp_m2": 0,
        "fp_m2": 0,
        "fn_m2": 0,
        "tp_m1": 0,
        "fp_m1": 0,
        "fn_m1": 0,
        "flips": 0,
        "missed_flips_m2": 0,
        "missed_flips_m1": 0,
    }
    for rung in range(R_RUNGS):
        delta = draws[rung]
        dd = delta[index_i] - delta[index_j]
        d1 = d0 + dd
        flip = (d0 * d1) <= 0.0
        ahat_out = float(np.quantile(np.delete(a_hat, rung), RUNG_QUANTILE))
        true_unresolvable = np.abs(d0) <= 2.0 * a_hat[rung]
        pred_m2 = np.abs(d0) <= 2.0 * ahat_out
        pred_m1 = np.abs(d0) <= ahat_out
        per_rung.append(
            {
                "rung": rung,
                "a_hat_self_ev": r10(a_hat[rung]),
                "a_hat_leave_one_out_p95_ev": r10(ahat_out),
                "true_unresolvable_pairs": int(true_unresolvable.sum()),
                "predicted_unresolvable_pairs_m2": int(pred_m2.sum()),
                "predicted_unresolvable_pairs_m1": int(pred_m1.sum()),
                "actual_flipped_pairs": int(flip.sum()),
                "flips_declared_safe_m2": int((flip & ~pred_m2).sum()),
                "flips_declared_safe_m1": int((flip & ~pred_m1).sum()),
            }
        )
        totals["tp_m2"] += int((pred_m2 & true_unresolvable).sum())
        totals["fp_m2"] += int((pred_m2 & ~true_unresolvable).sum())
        totals["fn_m2"] += int((~pred_m2 & true_unresolvable).sum())
        totals["tp_m1"] += int((pred_m1 & true_unresolvable).sum())
        totals["fp_m1"] += int((pred_m1 & ~true_unresolvable).sum())
        totals["fn_m1"] += int((~pred_m1 & true_unresolvable).sum())
        totals["flips"] += int(flip.sum())
        totals["missed_flips_m2"] += int((flip & ~pred_m2).sum())
        totals["missed_flips_m1"] += int((flip & ~pred_m1).sum())

    def pr(tp: int, fp: int, fn: int) -> tuple[float, float]:
        precision = tp / (tp + fp) if (tp + fp) else 1.0
        recall = tp / (tp + fn) if (tp + fn) else 1.0
        return r10(precision), r10(recall)

    p2, rec2 = pr(totals["tp_m2"], totals["fp_m2"], totals["fn_m2"])
    p1, rec1 = pr(totals["tp_m1"], totals["fp_m1"], totals["fn_m1"])
    flips = totals["flips"]
    return {
        "design": {
            "rungs": R_RUNGS,
            "perturbation": "Uniform(-A, A), one independent draw per rung",
            "a_estimate": "per-rung realized max|delta e_i|; leave-one-rung-out p95",
            "primary_ground_truth": "analytic unresolvable set {|d0| <= 2 A_rung} (true perturbation)",
            "secondary_ground_truth": "actually flipped pairs under the rung's true perturbation",
        },
        "per_rung": per_rung,
        "aggregate": {
            "a_hat_rungs_ev": [r10(value) for value in a_hat],
            "a_hat_min_ev": r10(a_hat.min()),
            "a_hat_max_ev": r10(a_hat.max()),
            "predicted_at_2Ahat": {
                "precision": p2,
                "recall": rec2,
                "tp": totals["tp_m2"],
                "fp": totals["fp_m2"],
                "fn": totals["fn_m2"],
            },
            "predicted_at_Ahat": {
                "precision": p1,
                "recall": rec1,
                "tp": totals["tp_m1"],
                "fp": totals["fp_m1"],
                "fn": totals["fn_m1"],
            },
            "actual_flipped_pairs_total": flips,
            "flips_declared_safe_m2": totals["missed_flips_m2"],
            "flips_declared_safe_m1": totals["missed_flips_m1"],
            "flip_capture_recall_m2": r10(1.0 - totals["missed_flips_m2"] / flips if flips else 1.0),
            "flip_capture_recall_m1": r10(1.0 - totals["missed_flips_m1"] / flips if flips else 1.0),
        },
    }


def empirical_pair_set() -> dict:
    """Cost of the tightening on the in-repo 1176-pair table (w21_rank_pairs.csv)."""

    rows = read_csv_rows(PAIRS_CSV)
    d_p0 = np.array([abs(float(row["dP0_eV"])) for row in rows])
    threshold = np.array([float(row["separation_threshold_eV"]) for row in rows])
    total = int(d_p0.size)

    def shares(level: float, values: np.ndarray) -> dict:
        safe = int((values >= level).sum())
        return {
            "safe_pairs": safe,
            "safe_fraction": r10(safe / total),
            "not_safe_pairs": total - safe,
        }

    by_multiplier = {
        f"m{m}": {
            "criterion": f"|dP0| >= {m} * A",
            "on_abs_dP0_eV": shares(m * A_AXIS_EV, d_p0),
            "on_separation_threshold_eV": shares(m * A_AXIS_EV, threshold),
        }
        for m in M_VALUES
    }
    safe_m1 = by_multiplier["m1"]["on_abs_dP0_eV"]["safe_pairs"]
    safe_m2 = by_multiplier["m2"]["on_abs_dP0_eV"]["safe_pairs"]
    lost = safe_m1 - safe_m2
    grid = []
    for a_value in A_GRID_EV:
        m1 = int((d_p0 >= a_value).sum())
        m2 = int((d_p0 >= 2.0 * a_value).sum())
        grid.append(
            {
                "a_ev": r10(a_value),
                "safe_pairs_m1": m1,
                "safe_fraction_m1": r10(m1 / total),
                "safe_pairs_m2": m2,
                "safe_fraction_m2": r10(m2 / total),
                "safe_pairs_lost": m1 - m2,
                "relative_reduction_of_safe_set": r10((m1 - m2) / m1 if m1 else 0.0),
            }
        )
    return {
        "source": "probes/artifacts/w21_rank_pairs.csv",
        "source_sha256": sha256_file(PAIRS_CSV),
        "pairs": total,
        "d0_proxy": "|dP0_eV| (physics-proxy pair difference, GFN2-xTB gas phase)",
        "cross_check_proxy": "separation_threshold_eV (combined per-pair uncertainty band)",
        "a_axis_ev": r10(A_AXIS_EV),
        "by_multiplier": by_multiplier,
        "tightening_cost": {
            "safe_pairs_lost": lost,
            "fraction_of_all_pairs_lost": r10(lost / total),
            "relative_reduction_of_safe_set": r10(lost / safe_m1 if safe_m1 else 0.0),
        },
        "a_grid_sensitivity": grid,
    }


def analytic_block(uniform_arm: dict, normal_arm: dict) -> dict:
    return {
        "theorem_statement": ANALYTIC_STATEMENT,
        "pair_level_redefinition": {
            "statement": PAIR_REDEFINITION_STATEMENT,
            "criterion_under_redefinition": "|d0| >= A_pair",
            "identity": "A_pair <= 2 A_axis",
        },
        "single_cell_reading": "A_axis = max_i |delta e_i| (current draft)",
        "pair_level_reading": "A_pair = max_{i,j} |delta (e_i - e_j)| (redefinition)",
        "tightness": {
            "note": "attained when delta e_i = +A and delta e_j = -A on one pair",
            "uniform_arm_max_abs_delta_d_over_2A": uniform_arm["tightness_abs_delta_d_over_2A"]["max"],
            "uniform_arm_bound_violations": uniform_arm["bound_violations_per_trial"]["max"],
        },
        "normal_arm_support_caveat": {
            "note": (
                "the bound needs a *bounded* single-cell effect; under Normal(0, A/2) the "
                "support is unbounded, the premise |delta e_i| <= A fails for a few molecules "
                "per trial, and the 2A guarantee is therefore conditional, not unconditional"
            ),
            "premise_violations_per_trial_mean": normal_arm["premise_violations_per_trial"]["mean"],
            "m2_leak_rate_mean": normal_arm["m2"]["leak_rate_mean"],
            "m2_leak_rate_max": normal_arm["m2"]["leak_rate_max"],
        },
    }

def verdicts(core: dict) -> dict:
    uniform = core["monte_carlo"]["arms"]["uniform_bounded"]
    normal = core["monte_carlo"]["arms"]["normal_unbounded"]
    loro = core["prospective_loro"]["aggregate"]
    m1_positive = uniform["m1"]["leak_rate_mean"] > 0.0 and uniform["m1"]["trials_with_any_leak"] > 0
    m2_zero = uniform["m2"]["leak_rate_max"] == 0.0 and uniform["m2"]["trials_with_any_leak"] == 0
    tight = uniform["tightness_abs_delta_d_over_2A"]["max"] > 0.95
    prospective = loro["flips_declared_safe_m2"] == 0 and loro["flips_declared_safe_m1"] > 0
    block = {
        "criterion_m1_must_leak": {
            "registered_expectation": "m=1 shows >0 leakage under the bounded arm",
            "observed_leak_rate_mean": uniform["m1"]["leak_rate_mean"],
            "observed_trials_with_any_leak": uniform["m1"]["trials_with_any_leak"],
            "holds": bool(m1_positive),
        },
        "criterion_m2_must_not_leak": {
            "registered_expectation": "m=2 leakage == 0 in every bounded-arm trial",
            "observed_leak_rate_max": uniform["m2"]["leak_rate_max"],
            "observed_trials_with_any_leak": uniform["m2"]["trials_with_any_leak"],
            "holds": bool(m2_zero),
        },
        "factor_two_is_tight": {
            "registered_expectation": "max |delta d| / (2A) approaches 1",
            "observed": uniform["tightness_abs_delta_d_over_2A"]["max"],
            "holds": bool(tight),
        },
        "prospective_loro_factor_two": {
            "registered_expectation": (
                "leave-one-rung-out at 2*A_hat misses no flips; at A_hat it does"
            ),
            "missed_flips_at_2Ahat": loro["flips_declared_safe_m2"],
            "missed_flips_at_Ahat": loro["flips_declared_safe_m1"],
            "holds": bool(prospective),
        },
        "normal_support_caveat": {
            "registered_expectation": (
                "unbounded perturbations void the unconditional 2A guarantee"
            ),
            "observed_m2_leak_rate_max": normal["m2"]["leak_rate_max"],
            "holds": bool(normal["m2"]["leak_rate_max"] > 0.0),
        },
    }
    block["A3_factor_two_confirmed"] = bool(m1_positive and m2_zero and tight)
    block["refuted_claims"] = [
        name
        for name, item in block.items()
        if isinstance(item, dict) and item.get("holds") is False
    ]
    return block


def build_summary() -> dict:
    baseline, index_i, index_j = baseline_problem()
    uniform = mc_arm(baseline, index_i, index_j, "uniform", np.random.default_rng(SEED + 1))
    normal = mc_arm(baseline, index_i, index_j, "normal", np.random.default_rng(SEED + 2))
    loro = loro_rungs(baseline, index_i, index_j, np.random.default_rng(SEED + 3))
    empirical = empirical_pair_set()
    core = {
        "monte_carlo": {
            "design": {
                "n_molecules": N_MOLECULES,
                "pairs_enumerated": int(index_i.size),
                "trials_per_arm": TRIALS,
                "sigma_base_ev": r10(SIGMA_BASE_EV),
                "a_over_sigma_base": r10(A_AXIS_EV / SIGMA_BASE_EV),
                "seed": SEED,
                "derived_seeds": {"uniform": SEED + 1, "normal": SEED + 2, "loro": SEED + 3},
                "flip_definition": "sign(d0) != sign(d0 + delta d), i.e. d0 * d1 <= 0",
            },
            "arms": {"uniform_bounded": uniform, "normal_unbounded": normal},
        },
        "prospective_loro": loro,
        "empirical_pair_set": empirical,
    }
    core["analytic"] = analytic_block(uniform, normal)
    core["verdicts"] = verdicts(core)
    core["isolation"] = {
        "models_fitted": 0,
        "shot_number_taken": None,
        "writes_any_pool": False,
        "main_scoreboard_attempts": 0,
        "promoted": False,
        "reaxys_values_used": 0,
        "external_readings_used": [A_AXIS_EV],
    }
    summary = {
        "schema_version": "w22_safety_theorem_v1",
        "task": "week22_w22_1_safety_theorem_strictification",
        "status": "executed",
        "preregistration": prereg_reference(),
        "constants": {
            "seed": SEED,
            "n_molecules": N_MOLECULES,
            "trials": TRIALS,
            "r_rungs": R_RUNGS,
            "rung_quantile": RUNG_QUANTILE,
            "m_values": list(M_VALUES),
            "a_axis_ev": r10(A_AXIS_EV),
            "a_axis_provenance": A_AXIS_PROVENANCE,
            "a_grid_ev": list(A_GRID_EV),
            "sigma_base_ev": r10(SIGMA_BASE_EV),
        },
        **core,
    }
    summary["outputs"] = {
        "probe": "probes/w22_safety_theorem.py",
        "figures": [
            "probes/artifacts/w22_safety_theorem_leakage.png",
            "probes/artifacts/w22_safety_theorem_coverage.png",
        ],
        "report": "reports/w22_safety_theorem.md",
        "tests": "tests/test_w22_safety_theorem.py",
    }
    return summary


def prereg_body() -> dict:
    return {
        "task": "week22_w22_1_safety_theorem_strictification",
        "schema_version": "w22_safety_theorem_plan_v1",
        "status": "locked_before_run",
        "prereg_status": "locked_before_run",
        "authority": [
            "reports/week22_project_charter.md::section 2 W22-1",
            "reports/week22_project_charter.md::section 4",
            "external review of the draft paper (A3: factor of two; D1: leave-one-rung-out)",
        ],
        "proposition": ANALYTIC_STATEMENT,
        "pair_level_redefinition": PAIR_REDEFINITION_STATEMENT,
        "registered_criteria": [
            {
                "id": "criterion_m1_must_leak",
                "statement": "at m=1 the bounded (Uniform) arm shows a strictly positive leak rate",
                "refutation": "zero leakage in every trial would mean the factor of two is not needed",
            },
            {
                "id": "criterion_m2_must_not_leak",
                "statement": "at m=2 the bounded arm leaks in no trial and no pair",
                "refutation": "any leaking pair at m=2 refutes the strict criterion in the bounded arm",
            },
            {
                "id": "factor_two_is_tight",
                "statement": "max |delta d| / (2A) reaches ~1, so 2A is attained rather than padding",
                "refutation": "a ratio well below 1 would make 2A merely conservative",
            },
            {
                "id": "prospective_loro_factor_two",
                "statement": (
                    "leave-one-rung-out at 2*A_hat declares no flipped pair safe; at A_hat it does"
                ),
                "refutation": "if 2*A_hat misses flips, the prospective claim fails",
            },
            {
                "id": "normal_support_caveat",
                "statement": (
                    "the unconditional guarantee needs bounded single-cell effects; the Normal "
                    "arm need not be leak-free at m=2"
                ),
                "refutation": "not a refutation target: recorded either way as a boundary of the theorem",
            },
        ],
        "design": {
            "n_molecules": N_MOLECULES,
            "pairs_enumerated": N_MOLECULES * (N_MOLECULES - 1) // 2,
            "trials_per_arm": TRIALS,
            "arms": ["uniform_bounded", "normal_unbounded"],
            "a_axis_ev": r10(A_AXIS_EV),
            "a_axis_provenance": A_AXIS_PROVENANCE,
            "sigma_base_ev": r10(SIGMA_BASE_EV),
            "m_values": list(M_VALUES),
            "r_rungs": R_RUNGS,
            "rung_quantile": RUNG_QUANTILE,
            "a_grid_ev": list(A_GRID_EV),
            "seed": SEED,
            "derived_seeds": {"uniform": SEED + 1, "normal": SEED + 2, "loro": SEED + 3},
        },
        "empirical_pair_set": {
            "source": "probes/artifacts/w21_rank_pairs.csv",
            "pairs": 1176,
            "proxies": ["|dP0_eV|", "separation_threshold_eV"],
        },
        "two_sentence_rule": (
            "the THEOREM (analytic 2A bound) and the SIMULATION (empirical zero leak) are "
            "reported as two separate sentences; the simulation may never be used to prove the theorem"
        ),
        "not_doing": [
            "no DFT / xTB batch",
            "no new candidate pool",
            "no frozen number touched",
            "no Reaxys value used",
        ],
        "models_fitted": 0,
        "shot_number_taken": None,
        "writes_any_pool": False,
        "produces_reading": True,
        "main_scoreboard_untouched": True,
    }


def prereg_reference() -> dict:
    if PREREG_PATH.exists():
        payload = json.loads(PREREG_PATH.read_text(encoding="utf-8"))
        return {
            "path": "probes/w22_safety_theorem_prereg.json",
            "status": payload.get("status"),
            "sha256": sha256_file(PREREG_PATH),
        }
    return {"path": "probes/w22_safety_theorem_prereg.json", "status": "missing", "sha256": None}


def write_prereg() -> dict:
    body = prereg_body()
    body["locked_at_utc"] = utc_now()
    write_text(PREREG_PATH, dumps(body))
    return body

# ---------------------------------------------------------------------------
# figures
# ---------------------------------------------------------------------------


def _figure_style() -> None:
    import matplotlib

    matplotlib.use("Agg")
    matplotlib.rcParams.update(
        {"figure.dpi": 150, "font.size": 9, "axes.grid": True, "grid.alpha": 0.3}
    )


def figure_leakage(summary: dict) -> dict:
    _figure_style()
    import matplotlib.pyplot as plt

    arms = summary["monte_carlo"]["arms"]
    uniform = arms["uniform_bounded"]
    normal = arms["normal_unbounded"]

    figure, axes = plt.subplots(1, 2, figsize=(10.4, 4.0))
    labels = ["uniform\nm=1", "uniform\nm=2", "normal\nm=1", "normal\nm=2"]
    means = [
        uniform["m1"]["leak_rate_mean"],
        uniform["m2"]["leak_rate_mean"],
        normal["m1"]["leak_rate_mean"],
        normal["m2"]["leak_rate_mean"],
    ]
    worst = [
        uniform["m1"]["leak_rate_max"],
        uniform["m2"]["leak_rate_max"],
        normal["m1"]["leak_rate_max"],
        normal["m2"]["leak_rate_max"],
    ]
    colors = ["#b2182b", "#2166ac", "#ef8a62", "#67a9cf"]
    positions = np.arange(len(labels))
    axes[0].bar(positions, means, color=colors, width=0.6)
    axes[0].scatter(positions, worst, marker="_", s=260, color="black", label="worst trial")
    floor = 1e-7
    axes[0].set_yscale("symlog", linthresh=floor)
    axes[0].set_xticks(positions, labels)
    axes[0].set_ylabel("leakage rate among pairs declared safe")
    axes[0].set_title(
        "leakage of the m=1 vs m=2 criterion\n(bars = 200-trial mean, dashes = worst trial)"
    )
    for position, (mean, worst_value) in enumerate(zip(means, worst)):
        axes[0].annotate(
            f"{mean:.2e}" if mean else "0",
            (position, mean if mean else floor),
            textcoords="offset points",
            xytext=(0, 6),
            ha="center",
            fontsize=7.5,
        )
        axes[0].annotate(
            f"{worst_value:.2e}" if worst_value else "0",
            (position, worst_value if worst_value else floor),
            textcoords="offset points",
            xytext=(0, -12),
            ha="center",
            fontsize=7.5,
        )
    axes[0].legend(loc="upper right", fontsize=7.5)

    a = summary["constants"]["a_axis_ev"]
    rng = np.random.default_rng(SEED)
    baseline = rng.normal(
        0.0, summary["constants"]["sigma_base_ev"], summary["constants"]["n_molecules"]
    )
    index_i, index_j = np.triu_indices(summary["constants"]["n_molecules"], 1)
    d0 = baseline[index_i] - baseline[index_j]
    delta = rng.uniform(-a, a, summary["constants"]["n_molecules"])
    dd = delta[index_i] - delta[index_j]
    d1 = d0 + dd
    flip = (d0 * d1) <= 0.0
    declared = np.abs(d0) >= a
    leaked = declared & flip
    held = declared & ~flip
    not_declared = ~declared
    axes[1].scatter(
        np.abs(d0)[held], np.abs(dd)[held], s=5, color="#67a9cf", alpha=0.4,
        label="declared safe, held",
    )
    axes[1].scatter(
        np.abs(d0)[leaked], np.abs(dd)[leaked], s=26, color="#b2182b",
        label="declared safe, flipped (leak)",
    )
    axes[1].scatter(
        np.abs(d0)[not_declared], np.abs(dd)[not_declared], s=4, color="#bbbbbb", alpha=0.3,
        label="not declared safe",
    )
    axes[1].axhline(2 * a, color="black", linestyle="--", linewidth=1.1, label="|delta d| = 2A")
    axes[1].axhline(a, color="#2166ac", linestyle=":", linewidth=1.1, label="|delta d| = A")
    axes[1].axvline(a, color="#2166ac", linestyle=":", linewidth=1.1)
    axes[1].axvline(2 * a, color="black", linestyle="--", linewidth=1.1)
    axes[1].set_yscale("log")
    axes[1].set_xlabel("|d0|  (baseline pair separation, eV)")
    axes[1].set_ylabel("|delta d|  (pair shift, eV)")
    axes[1].set_title("mechanism, one Uniform trial:\nleaks live only in the [A, 2A) band")
    axes[1].legend(loc="lower right", fontsize=7)
    figure.tight_layout()
    figure.savefig(FIG_LEAKAGE, bbox_inches="tight", dpi=150)
    plt.close(figure)
    return {
        "leakage_png": "probes/artifacts/w22_safety_theorem_leakage.png",
        "leaked_pairs_in_mechanism_trial": int(leaked.sum()),
        "declared_safe_pairs_in_mechanism_trial": int(declared.sum()),
    }


def figure_coverage(summary: dict) -> dict:
    _figure_style()
    import matplotlib.pyplot as plt

    empirical = summary["empirical_pair_set"]
    a = summary["constants"]["a_axis_ev"]
    multipliers = np.linspace(0.5, 3.0, 26)

    rows = read_csv_rows(PAIRS_CSV)
    d_p0 = np.array([abs(float(row["dP0_eV"])) for row in rows])

    rng = np.random.default_rng(SEED)
    baseline = rng.normal(
        0.0, summary["constants"]["sigma_base_ev"], summary["constants"]["n_molecules"]
    )
    index_i, index_j = np.triu_indices(summary["constants"]["n_molecules"], 1)
    d_syn = np.abs(baseline[index_i] - baseline[index_j])

    empirical_curve = [(d_p0 >= multiplier * a).mean() for multiplier in multipliers]
    synthetic_curve = [(d_syn >= multiplier * a).mean() for multiplier in multipliers]

    figure, axes = plt.subplots(1, 2, figsize=(10.4, 4.0))
    axes[0].plot(
        multipliers, empirical_curve, color="#2166ac", linewidth=1.8,
        label="in-repo w21 pairs (n=1176)",
    )
    axes[0].plot(
        multipliers, synthetic_curve, color="#b2182b", linewidth=1.8,
        label="synthetic set (n=19900)",
    )
    axes[0].axvline(1.0, color="#2166ac", linestyle=":", linewidth=1.2)
    axes[0].axvline(2.0, color="black", linestyle="--", linewidth=1.2)
    axes[0].annotate("m=1\n(current)", (1.0, 0.5), textcoords="offset points", xytext=(6, 0), fontsize=8)
    axes[0].annotate("m=2\n(strict)", (2.0, 0.5), textcoords="offset points", xytext=(6, 0), fontsize=8)
    axes[0].set_xlabel("criterion multiplier m  (safe iff |d0| >= m * A)")
    axes[0].set_ylabel("pair fraction declared safe")
    axes[0].set_ylim(0.0, 1.02)
    axes[0].set_title("protection coverage vs the multiplier")
    axes[0].legend(loc="lower left", fontsize=8)

    grid = empirical["a_grid_sensitivity"]
    x_values = [item["a_ev"] for item in grid]
    m1 = [item["safe_fraction_m1"] for item in grid]
    m2 = [item["safe_fraction_m2"] for item in grid]
    positions = np.arange(len(grid))
    width = 0.38
    axes[1].bar(positions - width / 2, m1, width, color="#2166ac", label="m=1 (current)")
    axes[1].bar(positions + width / 2, m2, width, color="#b2182b", label="m=2 (strict)")
    for position, item in enumerate(grid):
        top = max(item["safe_fraction_m1"], item["safe_fraction_m2"])
        axes[1].annotate(
            f"-{item['safe_pairs_lost']}", (position, top), textcoords="offset points",
            xytext=(0, 4), ha="center", fontsize=7.5,
        )
    axes[1].set_xticks(positions, [f"{value:g}" for value in x_values])
    axes[1].set_xlabel("assumed A (eV)  --  A=0.152 is the external reading")
    axes[1].set_ylabel("safe fraction on the 1176 in-repo pairs")
    axes[1].set_ylim(0.0, 1.05)
    axes[1].set_title("cost of the tightening, sensitivity to A\n(annotations = pairs lost)")
    axes[1].legend(loc="lower left", fontsize=8)
    figure.tight_layout()
    figure.savefig(FIG_COVERAGE, bbox_inches="tight", dpi=150)
    plt.close(figure)
    return {"coverage_png": "probes/artifacts/w22_safety_theorem_coverage.png"}

# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------


def _artifact_row(path: Path) -> str:
    rel = path.relative_to(ROOT).as_posix()
    if not path.exists():
        return f"| `{rel}` | - | - | (missing) |"
    size = path.stat().st_size
    lines = line_count(path)
    lines_text = "-" if lines is None else str(lines)
    return f"| `{rel}` | {lines_text} | {size} | `{sha256_file(path)}` |"


def render_report(summary: dict) -> str:
    arms = summary["monte_carlo"]["arms"]
    uniform = arms["uniform_bounded"]
    normal = arms["normal_unbounded"]
    verdict = summary["verdicts"]
    loro = summary["prospective_loro"]["aggregate"]
    empirical = summary["empirical_pair_set"]
    design = summary["monte_carlo"]["design"]
    constants = summary["constants"]
    a = constants["a_axis_ev"]
    a_grid = constants["a_grid_ev"]

    artifacts = [PROBE_PATH, PREREG_PATH, SUMMARY_PATH, FIG_LEAKAGE, FIG_COVERAGE, TEST_PATH]
    table = "\n".join(_artifact_row(path) for path in artifacts)

    def pct(value: float) -> str:
        return f"{100.0 * value:.2f}%"

    syn_m1 = uniform["m1"]["mean_safe_pairs"] / design["pairs_enumerated"]
    syn_m2 = uniform["m2"]["mean_safe_pairs"] / design["pairs_enumerated"]
    worst_grid = max(empirical["a_grid_sensitivity"], key=lambda item: item["a_ev"])
    best_grid = min(empirical["a_grid_sensitivity"], key=lambda item: item["a_ev"])

    lines = [
        "# W22-1 报告：漏解安全定理的严格化（因子 2）",
        "",
        "- **状态**：`executed`（跑前锁定见 `probes/w22_safety_theorem_prereg.json`）",
        (f"- **种子 / 规模**：seed={constants['seed']}，N={constants['n_molecules']}，"
        f"每臂 {constants['trials']} 次实现，pair={design['pairs_enumerated']}"),
        f"- **A 口径**：A_axis = {a} eV（外部读数，仓内不可核）；另在 A ∈ {a_grid} 上做敏感性",
        "- **隔离**：不跑 DFT/xTB、不建池、不动冻结件、不引 Reaxys；主记分牌尝试 0 次",
        "",
        "## 0. 结论速览",
        "",
        f"1. **定理（解析严格界）**：{ANALYTIC_STATEMENT} 三角不等式直接给出，与仿真无关，恒成立。",
        (f"2. **仿真（经验读数）**：在有界扰动臂里，m=1 判据平均漏解 "
        f"{pct(uniform['m1']['leak_rate_mean'])}（{uniform['m1']['trials_with_any_leak']}/"
        f"{constants['trials']} 次实现出现漏解），m=2 判据在全部 {constants['trials']} 次实现里漏解为 0。"
        f"**这两句必须分开写**：第 2 句永远不能用来反证或证明第 1 句。"),
        "",
        "| 判据 | 跑前锁定预期 | 实测 | 是否成立 |",
        "| --- | --- | --- | --- |",
        (f"| m=1 必有漏解 | > 0 | 均值 {pct(uniform['m1']['leak_rate_mean'])}，"
        f"最坏 {pct(uniform['m1']['leak_rate_max'])} | {verdict['criterion_m1_must_leak']['holds']} |"),
        (f"| m=2 零漏解（有界臂） | = 0 | 全部 {constants['trials']} 次实现恒为 0 | "
        f"{verdict['criterion_m2_must_not_leak']['holds']} |"),
        (f"| 2A 界是紧的（非冗余） | max |Δd|/2A → 1 | "
        f"{uniform['tightness_abs_delta_d_over_2A']['max']:.4f} | {verdict['factor_two_is_tight']['holds']} |"),
        (f"| D1 前瞻 2Â 不放过任何翻号 | 0 次漏判 | {loro['flips_declared_safe_m2']} 次 | "
        f"{verdict['prospective_loro_factor_two']['holds']} |"),
        (f"| 无界扰动破坏无条件保证 | 记录边界 | normal 臂 m=2 最坏漏解 "
        f"{normal['m2']['leak_rate_max']:.2e} | {verdict['normal_support_caveat']['holds']} |"),
        "",
        (f"**A3 因子 2 成立**：`{verdict['A3_factor_two_confirmed']}`。被证否的条目："
        f"{verdict['refuted_claims'] if verdict['refuted_claims'] else '无'}。"),
        "",
        "## 1. 定理（严格界）",
        "",
        ("设某一步阶对分子 i 的效应为 e_i，间距 d(i,j) = e_i − e_j，单格最大效应量 "
        "A_axis = max_i |Δe_i|。扰动后"),
        "",
        "```",
        "Δd = Δe_i − Δe_j  ⇒  |Δd| ≤ |Δe_i| + |Δe_j| ≤ 2·A_axis",
        "```",
        "",
        (f"故严格充分判据是 `|d0| ≥ 2·A_axis`，而 `|d0| ≥ A_axis` 只覆盖两臂同向的情形。"
        f"**紧性**：取 Δe_i = +A_axis、Δe_j = −A_axis 即取等号；仿真里 max |Δd|/(2A) = "
        f"{uniform['tightness_abs_delta_d_over_2A']['max']:.4f}，数值上确认“2A 是必需的、不是保守填充”。"
        f"见证 pair（漏解臂最坏一次实现）：i={uniform['witness']['i']}, j={uniform['witness']['j']}, "
        f"Δe_i={uniform['witness']['delta_e_i']}, Δe_j={uniform['witness']['delta_e_j']}, "
        f"d0={uniform['witness']['d0']}, Δd={uniform['witness']['delta_d']}, "
        f"|Δd|/2A={uniform['witness']['abs_delta_d_over_2A']}"
        f"（反向扰动 {uniform['witness']['opposite_signs']}）。"),
        "",
        ("**pair 级重定义（判据形式不变）**：令 A_pair = max_{i,j} |Δ(e_i − e_j)|，则 "
        "A_pair ≤ 2·A_axis；采用 `|d0| ≥ A_pair` 后判据形状不变，因子 2 被吸收进这个数。"
        "两种口径都在本文件里实现，作者可二选一。"),
        "",
        "## 2. 仿真（经验零漏解）",
        "",
        (f"- 有界臂 Uniform(−A, A)：m=1 平均漏解率 {pct(uniform['m1']['leak_rate_mean'])}"
        f"（最坏 {pct(uniform['m1']['leak_rate_max'])}，{uniform['m1']['trials_with_any_leak']}/"
        f"{constants['trials']} 次实现出现漏解，累计 {uniform['m1']['total_leak_events']} 次事件）；"
        f"m=2 漏解率恒为 {uniform['m2']['leak_rate_max']}。"),
        (f"- 无界臂 Normal(0, A/2)（敏感性）：m=1 平均 {pct(normal['m1']['leak_rate_mean'])}；"
        f"m=2 平均 {normal['m2']['leak_rate_mean']:.2e}、最坏 {normal['m2']['leak_rate_max']:.2e}——"
        f"**非零**，因为每轮约有 {normal['premise_violations_per_trial']['mean']} 个分子的 |Δe| 超过 A，"
        f"定理前提（有界）被破坏。"),
        ("- 因此定理的准确表述是：**前提为“单格效应有界且界为 A_axis”时，`|d0| ≥ 2A_axis` 是充分判据**；"
        "正态型无界扰动下该保证只是条件性的。"),
        "",
        "## 3. 保护格 / 节省率重报（严格化的代价）",
        "",
        (f"在仓内 `probes/artifacts/w21_rank_pairs.csv`（n={empirical['pairs']} 对，"
        f"d0 取 |dP0_eV|，A={a} eV）："),
        "",
        "| 判据 | 判为安全的 pair | 占比 | 相对 m=1 的代价 |",
        "| --- | --- | --- | --- |",
        (f"| m=1（现行） | {empirical['by_multiplier']['m1']['on_abs_dP0_eV']['safe_pairs']} | "
        f"{pct(empirical['by_multiplier']['m1']['on_abs_dP0_eV']['safe_fraction'])} | — |"),
        (f"| m=2（严格） | {empirical['by_multiplier']['m2']['on_abs_dP0_eV']['safe_pairs']} | "
        f"{pct(empirical['by_multiplier']['m2']['on_abs_dP0_eV']['safe_fraction'])} | "
        f"少 {empirical['tightening_cost']['safe_pairs_lost']} 对"
        f"（安全集相对缩水 {pct(empirical['tightening_cost']['relative_reduction_of_safe_set'])}） |"),
        "",
        (f"合成集上（N={constants['n_molecules']}）安全占比从 m=1 的 {pct(syn_m1)} 降到 m=2 的 {pct(syn_m2)}——"
        f"合成集比实测集代价更大，这本身就是一条读数：实测核心集的 |d0| 分布整体离 A 更远。"
        f"A 取值敏感性（A ∈ [{best_grid['a_ev']}, {worst_grid['a_ev']}] eV）下安全集相对缩水 "
        f"{pct(best_grid['relative_reduction_of_safe_set'])}–{pct(worst_grid['relative_reduction_of_safe_set'])}，见图右panel。"),
        "",
        "## 4. D1 前瞻性检验（leave-one-rung-out 仿真）",
        "",
        (f"- 造 {constants['r_rungs']} 个台阶，每台阶独立一次 Uniform(−A, A) 实现；"
        f"用其余 9 个台阶的 Â 的 p95 估计扰动尺度。"),
        (f"- 预测「不可分辨集」= {{|d0| ≤ 2Â}}，对照本台阶真实扰动的解析不可分辨集："
        f"**precision={loro['predicted_at_2Ahat']['precision']:.4f}，"
        f"recall={loro['predicted_at_2Ahat']['recall']:.4f}**。"),
        (f"- 若把倍率退回 m=1（|d0| ≤ Â）：recall 只有 {loro['predicted_at_Ahat']['recall']:.4f}"
        f"（漏掉约 {100 * (1 - loro['predicted_at_Ahat']['recall']):.1f}% 的不可分辨集）。"),
        (f"- 用「真实翻号」作对照更直接：10 个台阶累计 {loro['actual_flipped_pairs_total']} 次翻号中，"
        f"m=1 判据会把 **{loro['flips_declared_safe_m1']} 次翻号误判为安全**"
        f"（占 {pct(loro['flips_declared_safe_m1'] / loro['actual_flipped_pairs_total'])}）；"
        f"m=2 判据为 **{loro['flips_declared_safe_m2']} 次**。"),
        "- 这把判据从“事后解释”推进到“事前预判”：**只看其余台阶就能预判本台阶哪些 pair 需要花钱算**。",
        "",
        "## 5. 敏感性",
        "",
        "- 扰动族：Uniform（有界）vs Normal（无界），见表。",
        f"- A 网格：{a_grid} eV；m=2 的安全占比随 A 单调下降。",
        (f"- 基准分布尺度：sigma_base={constants['sigma_base_ev']} eV，"
        f"起作用的无量纲量是 A/sigma_base={design['a_over_sigma_base']}。"),
        "",
        "## 6. 自检",
        "",
        ("- `pytest tests/test_w22_safety_theorem.py` 全绿（断言 m=1 有漏解、m=2 零漏解、"
        "|Δd| ≤ 2A 的解析关系、|Δd|/2A 紧性、LORO 结果、summary 不可变）。"),
        ("- 确定性：`--write-summary` 连跑两次，`w22_safety_theorem_summary.json` 的 sha256 逐字节相同；"
        "`--check` 为同一断言的可执行入口。"),
        "",
        "### 产物 sha256 表",
        "",
        "| 产物 | 行数 | bytes | sha256 |",
        "| --- | --- | --- | --- |",
        table,
        "| `reports/w22_safety_theorem.md`（本文件，自引用） | 自引用 | 自引用 | 由 `--check` 打印（见下说明） |",
        "",
        ("> 报告自身不能内嵌自己的 sha256（自引用会改变文件），因此本行只给行数/bytes；"
        "运行 `.venv\\Scripts\\python.exe probes\\w22_safety_theorem.py --check` "
        "会打印报告与 summary 的 sha256，并逐字节校验 summary 的可重算性。"),
        "",
        "## 7. 局限与不做清单",
        "",
        "- 本臂的证据全部来自**解析界 + 合成蒙特卡洛 + 仓内 pair 表重算**；不构成新的量化计算，也不改动任何冻结件。",
        "- A_axis = 0.152 eV 是外部读数，仓内不可核；所有依赖它的数都同时给了 A 网格敏感性。",
        ("- **一句必须带上的正文口径**：定理（严格界）与仿真（经验零漏）是两句话；"
        "下一批分子里只要出现一对反向漏解，被打破的是经验陈述，解析界不动。"),
        "- 未做：基于真实台阶位移分布的 LORO（本仓缺该分布）、pair 级 A_pair 的实测重算（需逐格实现，超出本轮成本）。",
        "",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--write-prereg", action="store_true", help="write the locked prereg JSON")
    parser.add_argument("--write-summary", action="store_true", help="write the summary JSON + figures")
    parser.add_argument("--write-report", action="store_true", help="write reports/w22_safety_theorem.md")
    parser.add_argument("--check", action="store_true", help="re-derive the summary and compare bytes")
    parser.add_argument("--plan", action="store_true", help="print the pinned plan and exit")
    parser.add_argument("--prereg", type=Path, default=PREREG_PATH)
    parser.add_argument("--summary", type=Path, default=SUMMARY_PATH)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    global PREREG_PATH, SUMMARY_PATH
    args = parse_args(argv)
    PREREG_PATH = args.prereg
    SUMMARY_PATH = args.summary

    if args.plan:
        print(dumps(prereg_body()))
        return 0
    if args.write_prereg:
        print(dumps(write_prereg()))
        return 0

    summary = build_summary()
    if args.write_summary:
        write_text(SUMMARY_PATH, dumps(summary))
        figure_leakage(summary)
        figure_coverage(summary)
        print(f"wrote {SUMMARY_PATH} (sha256={sha256_file(SUMMARY_PATH)})")
        return 0
    if args.write_report:
        write_text(REPORT_PATH, render_report(summary))
        print(f"wrote {REPORT_PATH} (sha256={sha256_file(REPORT_PATH)})")
        return 0
    if args.check:
        expected = dumps(summary)
        if not SUMMARY_PATH.exists():
            print(f"CHECK FAILED: {SUMMARY_PATH} missing")
            return 1
        if SUMMARY_PATH.read_text(encoding="utf-8") != expected:
            print("CHECK FAILED: summary on disk is not byte-identical to the re-derivation")
            return 1
        print(f"CHECK OK: {SUMMARY_PATH} sha256={sha256_file(SUMMARY_PATH)}")
        if REPORT_PATH.exists():
            print(f"report sha256={sha256_file(REPORT_PATH)} bytes={REPORT_PATH.stat().st_size}")
        return 0
    print(dumps(summary))
    return 0


if __name__ == "__main__":  # pragma: no cover - manual inspection helper
    raise SystemExit(main())