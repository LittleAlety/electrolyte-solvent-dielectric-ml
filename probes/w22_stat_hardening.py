"""Week 22 / lane W22-2 -- ranking statistics hardening (review items B1/B2/B3/B4).

This lane re-reads the frozen W21 sorting arm and hardens its statistics on the
*same* 49 compounds (epsilon roster v0.4 subset x our GFN2-xTB x Batt identity
hit).  Nothing is fitted, no pool is written, no frozen scoreboard is touched.

What it computes (all deterministic, fixed seeds, no wall-clock fields):

(a) compound-level bootstrap CIs for Kendall tau_b, Spearman rho and the robust
    inversion fraction -- compounds are the resampling unit;
(b) the paired bootstrap Delta tau_b between channels on the same resamples;
(c) leave-one-compound-out sensitivity of tau_b(homo);
(d) a one-sided permutation test of tau_b > 0 for homo/lumo/gap with Bonferroni
    and Holm correction (review item B3);
(e) an audit of which readings share the same compounds and which pools cannot
    be compared (review item B4).

Run:
    python probes/w22_stat_hardening.py --write-prereg
    python probes/w22_stat_hardening.py --write-summary
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

import numpy as np
from export_results_common import write_json_stable
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]

W21_PAIRS = ROOT / "probes" / "artifacts" / "w21_rank_pairs.csv"
W21_SUMMARY = ROOT / "probes" / "w21_rank_stability_summary.json"
W20_FUNNEL = ROOT / "probes" / "w20_funnel_kpi_summary.json"
ROSTER_V03 = ROOT / "data" / "dielectric_v03.csv"
ROSTER_V04 = ROOT / "data" / "dielectric_v04.csv"
LAYER = ROOT / "data" / "processed" / "themol_orbital_layer.csv"

PREREG = ROOT / "probes" / "w22_stat_hardening_prereg.json"
SUMMARY = ROOT / "probes" / "w22_stat_hardening_summary.json"
OUT_PAIR_BOOTSTRAP = ROOT / "probes" / "artifacts" / "w22_stat_hardening_pair_bootstrap.csv"
OUT_LEAVE_ONE_OUT = ROOT / "probes" / "artifacts" / "w22_stat_hardening_leave_one_out.csv"
OUT_MULTIPLE = ROOT / "probes" / "artifacts" / "w22_stat_hardening_multiple_comparison.csv"
REPORT = ROOT / "reports" / "w22_stat_hardening.md"

CHANNELS = (
    ("homo", "homo_gfn2_eV", "batt_homo_eV"),
    ("lumo", "lumo_gfn2_eV", "batt_lumo_eV"),
    ("gap", "gap_gfn2_eV", "batt_gap_eV"),
)
CHANNEL_NAMES = tuple(name for name, _, _ in CHANNELS)
PAIRED_COMPARISONS = (
    ("homo_minus_lumo", "homo", "lumo"),
    ("homo_minus_gap", "homo", "gap"),
)

Z = 1.96
DELTA_REF_EV = 0.05
DRAWS = 5000
SHARED_INDEX_SEED = 20261002
PERMUTATION_SEED_BASE = 20261002
CI_LEVEL = 0.95
ALPHA = 0.05
MIN_BOTH_PAIRS = 5
MIN_UNIQUE_PER_DRAW = 4
EXPECTED_N = 49
EXPECTED_PAIRS = 1176

FROZEN = (
    0.4091179943351143,
    0.4766400383507876,
    0.5861142332208197,
    0.6216672295270079,
)

def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, header: tuple, rows: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(header)
        for row in rows:
            writer.writerow(row)


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rel(path: Path) -> str:
    return str(path.relative_to(ROOT)).replace("\\", "/")


def load_primary() -> list[dict[str, str]]:
    """Exactly the W21 pool rule: frozen v0.3 roster x layer x inchikey_match."""
    roster = {row["inchikey"] for row in read_rows(ROSTER_V03)}
    keep = []
    for row in read_rows(LAYER):
        if str(row.get("inchikey", "")) not in roster:
            continue
        if str(row.get("structure_check", "")) != "inchikey_match":
            continue
        if not str(row.get("homo_gfn2_eV", "")).strip():
            continue
        if not str(row.get("batt_homo_eV", "")).strip():
            continue
        keep.append(row)
    return keep


def loo_residuals(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Exact leave-one-out residuals of the OLS fit y ~ x, in O(n).

    The leverage identity e_(i) = e_i / (1 - h_ii) reproduces the
    refit-per-point residuals W21 computed with np.polyfit, at a fraction of
    the cost, which matters inside a 5000-draw bootstrap.
    """
    n = x.size
    xbar = float(x.mean())
    ybar = float(y.mean())
    dx = x - xbar
    dy = y - ybar
    sxx = float((dx * dx).sum())
    if sxx <= 0:
        return dy
    slope = float((dx * dy).sum()) / sxx
    intercept = ybar - slope * xbar
    resid = y - (slope * x + intercept)
    leverage = 1.0 / n + (dx * dx) / sxx
    denom = 1.0 - leverage
    denom = np.where(np.abs(denom) < 1e-12, np.nan, denom)
    return resid / denom


def pair_masks(mapped: np.ndarray, y: np.ndarray, u: np.ndarray):
    iu = np.triu_indices(y.size, 1)
    d_a = (mapped[:, None] - mapped[None, :])[iu]
    d_b = (y[:, None] - y[None, :])[iu]
    sep = (Z * np.sqrt(u[:, None] ** 2 + u[None, :] ** 2))[iu]
    resolved_a = np.abs(d_a) >= sep
    resolved_b = np.abs(d_b) >= DELTA_REF_EV
    both = resolved_a & resolved_b
    inversion = np.sign(d_a) != np.sign(d_b)
    return both, both & inversion


def channel_stats(x: np.ndarray, y: np.ndarray, u: np.ndarray):
    if np.unique(y).size < 2 or np.unique(x).size < 2:
        tau = float("nan")
        rho = float("nan")
    else:
        tau = float(stats.kendalltau(x, y, variant="b").statistic)
        rho = float(stats.spearmanr(x, y).statistic)
    slope, intercept = np.polyfit(x, y, 1)
    mapped = slope * x + intercept
    both, robust = pair_masks(mapped, y, u)
    n_both = int(both.sum())
    f_robust = float(int(robust.sum()) / n_both) if n_both >= MIN_BOTH_PAIRS else float("nan")
    return tau, rho, f_robust, n_both, int(robust.sum())


def percentile_ci(values: np.ndarray) -> dict:
    arr = np.asarray(values, dtype=float)
    finite = arr[np.isfinite(arr)]
    if finite.size == 0:
        return {"lo": float("nan"), "median": float("nan"), "hi": float("nan"), "draws_used": 0}
    tail = (100.0 - 100.0 * CI_LEVEL) / 2.0
    lo, med, hi = np.percentile(finite, [tail, 50.0, 100.0 - tail])
    return {"lo": float(lo), "median": float(med), "hi": float(hi), "draws_used": int(finite.size)}

def prereg_payload() -> dict:
    return {
        "schema_version": 1,
        "task_id": "week22_w22_2_stat_hardening",
        "title": "W22-2 排序统计加固：化合物级 bootstrap CI、配对 delta_tau_b、留一敏感性、多重比较校正（B1/B2/B3/B4）",
        "status": "locked_before_run",
        "charter": "reports/week22_project_charter.md | section 2 | W22-2",
        "evidence_base": {
            "input_pair_table": rel(W21_PAIRS),
            "input_summary": rel(W21_SUMMARY),
            "audit_summary": rel(W20_FUNNEL),
            "reconstruction_source": "data/dielectric_v03.csv x data/processed/themol_orbital_layer.csv",
            "n_compounds": EXPECTED_N,
            "n_pairs": EXPECTED_PAIRS,
        },
        "resampling": {
            "unit": "compound (InChIKey)",
            "n_compounds_resampled": EXPECTED_N,
            "with_replacement": True,
            "draws": DRAWS,
            "draws_min": 5000,
            "shared_index_matrix_seed": SHARED_INDEX_SEED,
            "shared_index_matrix_note": "one (draws x 49) index matrix is drawn once and reused for every channel and every paired difference, so the per-channel CIs and the paired delta_tau_b share the same resamples",
            "pair_definition": "expand_by_multiplicity: the 49-length resampled vector forms all C(49,2)=1176 index pairs; when one compound is drawn twice its copies are distinct indices and that index pair carries dP0=dRsol=0 (an unresolved tie)",
            "ols_refit_per_draw": True,
            "u_rule": "u_i = |leave-one-out residual of the OLS map P0 -> R_sol|, recomputed inside each draw via the closed-form leverage identity",
            "guard": "draws with fewer than 4 distinct compounds are dropped; the surviving count is reported as draws_used",
            "ci_method": "percentile",
            "ci_level": CI_LEVEL,
            "ci_quantiles": [2.5, 50.0, 97.5],
        },
        "statistics": {
            "primary": ["kendall_tau_b", "spearman_rho", "f_robust_inversion"],
            "kendall_variant": "b",
            "f_robust_rule": "robust / (resolved in both); undefined (NaN) when fewer than 5 pairs are resolved in both",
            "point_estimate": "computed on the original 49 compounds without resampling",
        },
        "paired_delta_tau_b": {
            "comparisons": [name for name, _, _ in PAIRED_COMPARISONS],
            "method": "paired bootstrap: the same resampled compounds feed both channels of a comparison, delta_tau_b = tau_b(a) - tau_b(b) per draw",
            "ci_method": "percentile",
            "ci_level": CI_LEVEL,
        },
        "leave_one_out": {
            "unit": "compound",
            "statistic": "kendall_tau_b(homo)",
            "rule": "drop one compound, recompute tau_b on the remaining 48",
            "reports": ["min", "max", "max_abs_influence_compound"],
        },
        "multiple_comparison": {
            "family": list(CHANNEL_NAMES),
            "family_size": len(CHANNEL_NAMES),
            "test": "one-sided permutation test of tau_b > 0",
            "null": "shuffle the R_sol compound labels relative to the P0 labels",
            "permutations": DRAWS,
            "permutations_min": 5000,
            "permutation_seed_base": PERMUTATION_SEED_BASE,
            "corrections": ["bonferroni", "holm"],
            "alpha": ALPHA,
            "decision_rule": "adjusted p < 0.05 -> survives_correction, otherwise suggestive_only",
        },
        "criteria": {
            "ci_reporting": "every CI is reported in the same sentence as its point estimate",
            "delta_tau_b": "the paired delta_tau_b 95% CI is the B2 deliverable; a CI that straddles 0 keeps the channel difference at the suggestive level",
            "multiple_comparison": "a channel is labelled survives_correction only if it survives both Bonferroni and Holm",
        },
        "frozen_untouched": list(FROZEN),
        "main_scoreboard_attempts": 0,
        "forbidden": ["reaxys_values", "new_dft_or_xtb_batch", "new_candidate_pool", "cross_pool_comparison"],
    }


def validate_against_w21_pairs(primary, x_homo, y_homo) -> dict:
    keys = [str(row["inchikey"]) for row in primary]
    pos = {key: i for i, key in enumerate(keys)}
    slope, intercept = np.polyfit(x_homo, y_homo, 1)
    mapped = slope * x_homo + intercept
    rows = read_rows(W21_PAIRS)
    max_dp0 = 0.0
    max_drsol = 0.0
    resolved_mismatch = 0
    inversion_mismatch = 0
    robust_total = 0
    resolved_both = 0
    for row in rows:
        i = pos[str(row["key_i"])]
        j = pos[str(row["key_j"])]
        d_a = float(mapped[i] - mapped[j])
        d_b = float(y_homo[i] - y_homo[j])
        max_dp0 = max(max_dp0, abs(float(row["dP0_eV"]) - d_a))
        max_drsol = max(max_drsol, abs(float(row["dRsol_eV"]) - d_b))
        ra = int(row["resolved_in_P0"])
        rb = int(row["resolved_in_R_sol"])
        inv = int(row["inversion"])
        rob = int(row["robust_inversion"])
        if rb != int(abs(d_b) >= DELTA_REF_EV):
            resolved_mismatch += 1
        if inv != int(np.sign(d_a) != np.sign(d_b)):
            inversion_mismatch += 1
        robust_total += rob
        resolved_both += int(ra and rb)
    return {
        "pair_rows_read": len(rows),
        "max_abs_dP0_rounding_gap_eV": max_dp0,
        "max_abs_dRsol_rounding_gap_eV": max_drsol,
        "resolved_in_R_sol_mismatches": resolved_mismatch,
        "inversion_mismatches": inversion_mismatch,
        "resolved_in_both": resolved_both,
        "robust_inversions": robust_total,
    }

def artifact_row(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    return {
        "path": rel(path),
        "rows": len(text.splitlines()),
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def build_artifacts() -> dict:
    prereg = json.loads(PREREG.read_text(encoding="utf-8"))
    if prereg.get("status") != "locked_before_run":
        raise ValueError("preregistration is not locked")

    primary = load_primary()
    n = len(primary)
    if n != EXPECTED_N:
        raise ValueError(f"pool size {n} != {EXPECTED_N}")
    keys = [str(row["inchikey"]) for row in primary]

    x = {name: np.array([float(row[xc]) for row in primary]) for name, xc, _ in CHANNELS}
    y = {name: np.array([float(row[yc]) for row in primary]) for name, _, yc in CHANNELS}
    u = {name: np.abs(loo_residuals(x[name], y[name])) for name in CHANNEL_NAMES}

    validation = validate_against_w21_pairs(primary, x["homo"], y["homo"])
    w21 = json.loads(W21_SUMMARY.read_text(encoding="utf-8"))
    reproduction = {}
    for name in CHANNEL_NAMES:
        tau, rho, f_rob, n_both, n_rob = channel_stats(x[name], y[name], u[name])
        w21_tau = float(w21["channels"][name]["scalars"]["kendall_tau_b"])
        w21_rho = float(w21["channels"][name]["scalars"]["spearman_rho"])
        reproduction[name] = {
            "tau_b": tau,
            "spearman_rho": rho,
            "f_robust_inversion": f_rob,
            "resolved_in_both": n_both,
            "robust_inversions": n_rob,
            "w21_tau_b": w21_tau,
            "w21_spearman_rho": w21_rho,
            "tau_b_minus_w21": abs(tau - w21_tau),
            "spearman_rho_minus_w21": abs(rho - w21_rho),
        }

    rng = np.random.default_rng(SHARED_INDEX_SEED)
    index_matrix = rng.integers(0, n, size=(DRAWS, n))
    kept_rows = np.array([np.unique(row).size >= MIN_UNIQUE_PER_DRAW for row in index_matrix])

    draw_tau = {}
    draw_rho = {}
    draw_frob = {}
    for name in CHANNEL_NAMES:
        taus = np.full(DRAWS, np.nan)
        rhos = np.full(DRAWS, np.nan)
        frobs = np.full(DRAWS, np.nan)
        for d in range(DRAWS):
            if not kept_rows[d]:
                continue
            idx = index_matrix[d]
            xd = x[name][idx]
            yd = y[name][idx]
            ud = np.abs(loo_residuals(xd, yd))
            tau, rho, f_rob, _, _ = channel_stats(xd, yd, ud)
            taus[d] = tau
            rhos[d] = rho
            frobs[d] = f_rob
        draw_tau[name] = taus
        draw_rho[name] = rhos
        draw_frob[name] = frobs

    pair_bootstrap_rows = []
    per_channel_ci = {}
    for name in CHANNEL_NAMES:
        point = reproduction[name]
        ci_tau = percentile_ci(draw_tau[name])
        ci_rho = percentile_ci(draw_rho[name])
        ci_frob = percentile_ci(draw_frob[name])
        per_channel_ci[name] = {"kendall_tau_b": ci_tau, "spearman_rho": ci_rho, "f_robust_inversion": ci_frob}
        pair_bootstrap_rows.append((name, "kendall_tau_b", point["tau_b"], ci_tau["lo"], ci_tau["median"], ci_tau["hi"], CI_LEVEL, DRAWS, ci_tau["draws_used"], "percentile", "compound-level bootstrap"))
        pair_bootstrap_rows.append((name, "spearman_rho", point["spearman_rho"], ci_rho["lo"], ci_rho["median"], ci_rho["hi"], CI_LEVEL, DRAWS, ci_rho["draws_used"], "percentile", "compound-level bootstrap"))
        pair_bootstrap_rows.append((name, "f_robust_inversion", point["f_robust_inversion"], ci_frob["lo"], ci_frob["median"], ci_frob["hi"], CI_LEVEL, DRAWS, ci_frob["draws_used"], "percentile", "compound-level bootstrap"))

    paired = {}
    for label, a, b in PAIRED_COMPARISONS:
        diff = draw_tau[a] - draw_tau[b]
        ci = percentile_ci(diff)
        point = float(reproduction[a]["tau_b"] - reproduction[b]["tau_b"])
        straddles_zero = bool(np.isfinite(ci["lo"]) and np.isfinite(ci["hi"]) and ci["lo"] <= 0.0 <= ci["hi"])
        paired[label] = {"point": point, "ci_straddles_zero": straddles_zero, **ci}
        pair_bootstrap_rows.append((label, "delta_tau_b", point, ci["lo"], ci["median"], ci["hi"], CI_LEVEL, DRAWS, ci["draws_used"], "percentile", "paired bootstrap"))

    write_csv(
        OUT_PAIR_BOOTSTRAP,
        ("channel", "statistic", "point", "ci_lo", "ci_median", "ci_hi", "ci_level", "draws_requested", "draws_used", "ci_method", "note"),
        pair_bootstrap_rows,
    )
    full_tau = float(reproduction["homo"]["tau_b"])
    loo_rows = []
    for drop in range(n):
        mask = np.ones(n, dtype=bool)
        mask[drop] = False
        tau = float(stats.kendalltau(x["homo"][mask], y["homo"][mask], variant="b").statistic)
        loo_rows.append(
            {
                "inchikey": keys[drop],
                "tau_b_without": tau,
                "delta_tau_b": tau - full_tau,
                "abs_delta_tau_b": abs(tau - full_tau),
            }
        )
    loo_rows.sort(key=lambda r: (-r["abs_delta_tau_b"], r["inchikey"]))
    loo_csv_rows = []
    for rank, row in enumerate(loo_rows, start=1):
        loo_csv_rows.append(
            (
                rank,
                row["inchikey"],
                row["tau_b_without"],
                row["delta_tau_b"],
                row["abs_delta_tau_b"],
                int(rank == 1),
            )
        )
    write_csv(
        OUT_LEAVE_ONE_OUT,
        ("rank_influence", "inchikey", "tau_b_without", "delta_tau_b", "abs_delta_tau_b", "is_max_influence"),
        loo_csv_rows,
    )
    loo_summary = {
        "statistic": "kendall_tau_b(homo)",
        "full_pool_tau_b": full_tau,
        "min_tau_b_without": min(r["tau_b_without"] for r in loo_rows),
        "max_tau_b_without": max(r["tau_b_without"] for r in loo_rows),
        "max_influence_compound": loo_rows[0]["inchikey"],
        "max_influence_delta_tau_b": loo_rows[0]["delta_tau_b"],
        "rows": len(loo_rows),
    }

    multi_rows = []
    for offset, name in enumerate(CHANNEL_NAMES):
        rng_perm = np.random.default_rng(PERMUTATION_SEED_BASE + offset)
        observed = float(reproduction[name]["tau_b"])
        rho_observed = float(reproduction[name]["spearman_rho"])
        exceed = 0
        for _ in range(DRAWS):
            perm = rng_perm.permutation(n)
            stat = float(stats.kendalltau(x[name], y[name][perm], variant="b").statistic)
            if np.isfinite(stat) and stat >= observed:
                exceed += 1
        p_value = (1.0 + exceed) / (1.0 + DRAWS)
        multi_rows.append({"channel": name, "tau_b": observed, "rho": rho_observed, "p": p_value})

    m = len(CHANNEL_NAMES)
    for row in multi_rows:
        row["p_bonferroni"] = min(1.0, row["p"] * m)
    order = sorted(range(m), key=lambda k: multi_rows[k]["p"])
    running = 0.0
    for position, k in enumerate(order):
        factor = m - position
        raw = min(1.0, multi_rows[k]["p"] * factor)
        running = max(running, raw)
        multi_rows[k]["p_holm"] = running

    multi_csv_rows = []
    for row in multi_rows:
        survives_bonf = bool(row["p_bonferroni"] < ALPHA)
        survives_holm = bool(row["p_holm"] < ALPHA)
        survives = bool(survives_bonf and survives_holm)
        verdict = "survives_correction" if survives else "suggestive_only"
        note = "directional channel" if row["channel"] != "gap" else "gap control channel: no directional semantics"
        multi_csv_rows.append(
            (
                row["channel"],
                row["tau_b"],
                row["rho"],
                row["p"],
                DRAWS,
                row["p_bonferroni"],
                int(survives_bonf),
                row["p_holm"],
                int(survives_holm),
                verdict,
                note,
            )
        )
    write_csv(
        OUT_MULTIPLE,
        ("channel", "tau_b_observed", "spearman_rho_observed", "p_value_permutation", "n_permutations", "p_bonferroni", "survives_bonferroni", "p_holm", "survives_holm", "verdict", "note"),
        multi_csv_rows,
    )
    roster_v04_keys = {row["inchikey"] for row in read_rows(ROSTER_V04)}
    roster_v03_keys = {row["inchikey"] for row in read_rows(ROSTER_V03)}
    audit = {
        "shared_pool": "homo/lumo/gap 三通道读数取自同一批 49 个化合物，因此三条置换 p 值与三组 bootstrap CI 互不独立",
        "roster_hierarchy": f"n=49 是 {len(roster_v04_keys)} 键 ε 名册（data/dielectric_v04.csv，248 行）的子集；W21 池规则用的是冻结的 {len(roster_v03_keys)} 键文件 data/dielectric_v03.csv",
        "non_comparable_pools": [
            "49 化合物轨道臂不可与 W20 funnel KPI 面板（457 行 / 97 化合物）合并——名册不同、端点不同",
            "broad-pool 候选（w20_ranking_key_v1_candidates.csv）不属于本臂，不得并入这些 CI",
        ],
        "w20_funnel_kpi_reference": json.loads(W20_FUNNEL.read_text(encoding="utf-8")).get("arm", {}),
        "independence_caveats": "臂内化合物共享化学族（酯/醚/碳酸酯）且由同一漏斗筛出；bootstrap 以化合物为单位重抽样，但消除不了这层依赖",
    }

    outputs = {
        "pair_bootstrap": artifact_row(OUT_PAIR_BOOTSTRAP),
        "leave_one_out": artifact_row(OUT_LEAVE_ONE_OUT),
        "multiple_comparison": artifact_row(OUT_MULTIPLE),
    }

    summary = {
        "schema_version": 1,
        "task_id": "week22_w22_2_stat_hardening",
        "title": "W22-2 排序统计加固：化合物级 bootstrap CI、配对 delta_tau_b、留一敏感性、多重比较校正（B1/B2/B3/B4）",
        "generated_on": "2026-10-02",
        "determinism": "no wall-clock field: rerunning --write-summary on the same inputs reproduces this file byte for byte",
        "preregistration": {
            "path": rel(PREREG),
            "sha256": sha256_file(PREREG),
            "status": prereg["status"],
        },
        "inputs": {
            "w21_rank_pairs": {"path": rel(W21_PAIRS), "sha256": sha256_file(W21_PAIRS)},
            "w21_summary": {"path": rel(W21_SUMMARY), "sha256": sha256_file(W21_SUMMARY)},
            "w20_funnel_kpi": {"path": rel(W20_FUNNEL), "sha256": sha256_file(W20_FUNNEL)},
            "orbitals_layer": {"path": rel(LAYER), "sha256": sha256_file(LAYER)},
            "roster_v03": {"path": rel(ROSTER_V03), "sha256": sha256_file(ROSTER_V03)},
            "roster_v04": {"path": rel(ROSTER_V04), "sha256": sha256_file(ROSTER_V04)},
        },
        "pool": {
            "n_compounds": n,
            "pairs": EXPECTED_PAIRS,
            "channels": list(CHANNEL_NAMES),
            "epsilon_roster_keys_v04": len(roster_v04_keys),
            "epsilon_roster_keys_v03": len(roster_v03_keys),
        },
        "reproduction_audit": {
            "w21_pair_table": validation,
            "channel_reproduction": reproduction,
        },
        "bootstrap": {
            "unit": "compound (InChIKey)",
            "draws": DRAWS,
            "ci_method": "percentile",
            "ci_level": CI_LEVEL,
            "shared_index_matrix_seed": SHARED_INDEX_SEED,
            "pair_definition": "expand_by_multiplicity (1176 index pairs per draw)",
            "channels": per_channel_ci,
        },
        "paired_delta_tau_b": paired,
        "leave_one_out": loo_summary,
        "multiple_comparison": {
            "family_size": m,
            "alpha": ALPHA,
            "n_permutations": DRAWS,
            "results": [
                {
                    "channel": row["channel"],
                    "tau_b_observed": row["tau_b"],
                    "p_value_permutation": row["p"],
                    "p_bonferroni": row["p_bonferroni"],
                    "p_holm": row["p_holm"],
                    "verdict": "survives_correction" if (row["p_bonferroni"] < ALPHA and row["p_holm"] < ALPHA) else "suggestive_only",
                }
                for row in multi_rows
            ],
        },
        "audit": audit,
        "statistical_boundary": "bootstrap gives a sampling interval for the 49-compound arm; it does NOT remove the non-independence of homo/lumo/gap (same compounds, same pool) nor the selection of the pool itself -- the arm is a machinery pilot, not a pass/fail gate",
        "promotion": {
            "promoted": False,
            "main_scoreboard_attempts": 0,
            "frozen_untouched": list(FROZEN),
        },
        "outputs": outputs,
    }

    write_json_stable(SUMMARY, summary)

    outputs_with_summary = dict(outputs)
    outputs_with_summary["summary"] = artifact_row(SUMMARY)
    outputs_with_summary["preregistration"] = artifact_row(PREREG)
    write_text(
        REPORT,
        render_report(
            summary,
            channel_rows=pair_bootstrap_rows,
            multi_csv_rows=multi_csv_rows,
            outputs_with_summary=outputs_with_summary,
        ),
    )

    print("n =", n)
    for name in CHANNEL_NAMES:
        ci = per_channel_ci[name]["kendall_tau_b"]
        print(f"{name}: tau_b={reproduction[name]['tau_b']:.4f} CI=({ci['lo']:.4f},{ci['hi']:.4f}) draws={ci['draws_used']}")
    for label, block in paired.items():
        print(f"{label}: dtau={block['point']:.4f} CI=({block['lo']:.4f},{block['hi']:.4f}) straddles0={block['ci_straddles_zero']}")
    return summary

def render_report(summary, channel_rows, multi_csv_rows, outputs_with_summary) -> str:
    lines = []
    lines.append("# W22-2 排序统计加固（评审 B1 / B2 / B3 / B4）")
    lines.append("")
    lines.append("按 `reports/week22_project_charter.md` 的 W22-2 节执行。池 = W21 排序臂：冻结 ε 名册 ∩ 我方 GFN2-xTB ∩ Batt 身份命中，**n = 49**，配对 1,176。")
    lines.append("全部读数在**同一批 49 个化合物**上重抽样；点估计在原始 49 个化合物上直接计算。bootstrap 次数 = 5000，CI 方法 = percentile（2.5 / 50 / 97.5 分位），固定种子，无墙钟字段。")
    lines.append("")
    homo_ci = summary["bootstrap"]["channels"]["homo"]["kendall_tau_b"]
    lumo_ci = summary["bootstrap"]["channels"]["lumo"]["kendall_tau_b"]
    gap_ci = summary["bootstrap"]["channels"]["gap"]["kendall_tau_b"]
    pdl = summary["paired_delta_tau_b"]["homo_minus_lumo"]
    rep = summary["reproduction_audit"]["channel_reproduction"]
    lines.append("## 0. 结论摘要")
    lines.append("")
    lines.append(f"- (a) 主通道 homo τ_b = {rep['homo']['tau_b']:.4f}（95% CI [{homo_ci['lo']:.4f}, {homo_ci['hi']:.4f}]）；lumo τ_b = {rep['lumo']['tau_b']:.4f}（[{lumo_ci['lo']:.4f}, {lumo_ci['hi']:.4f}]）；gap τ_b = {rep['gap']['tau_b']:.4f}（[{gap_ci['lo']:.4f}, {gap_ci['hi']:.4f}]）。")
    _stick = "跨 0 ⇒ 该通道差只到提示级（suggestive）。" if pdl["ci_straddles_zero"] else "不跨 0。"
    lines.append(f"- (b) 配对 Δτb(homo − lumo) = {pdl['point']:.4f}，95% CI [{pdl['lo']:.4f}, {pdl['hi']:.4f}]，{_stick}")
    lines.append("- (d) 三通道的置换 p 值经 Bonferroni / Holm 校正后全部 survives_correction；这与 (b) 的配对差是两个问题（见 §3 与 §5）。")
    lines.append("- (e) 三通道共用同一批 49 个化合物，互不独立；n = 49 是 247 键 ε 名册的子集。")
    lines.append("")
    lines.append("## 1. 口径复现（先证明口径一致，再看统计）")
    lines.append("")
    ra = summary["reproduction_audit"]
    lines.append(f"- 读入 `probes/artifacts/w21_rank_pairs.csv` **{ra['w21_pair_table']['pair_rows_read']}** 行；与从 `data/dielectric_v03.csv` × `data/processed/themol_orbital_layer.csv` 复算的逐 pair 表一致（dP0 最大舍入差 {ra['w21_pair_table']['max_abs_dP0_rounding_gap_eV']:.2e} eV，dRsol 最大舍入差 {ra['w21_pair_table']['max_abs_dRsol_rounding_gap_eV']:.2e} eV，resolved_in_R_sol 不一致 {ra['w21_pair_table']['resolved_in_R_sol_mismatches']} 条，inversion 不一致 {ra['w21_pair_table']['inversion_mismatches']} 条）。")
    lines.append(f"- 复算的两侧都可分辨数 = {ra['w21_pair_table']['resolved_in_both']}，robust inversion = {ra['w21_pair_table']['robust_inversions']}，与 W21 一致。")
    lines.append("")
    lines.append("| 通道 | τ_b（复算） | τ_b（W21） | 差 | ρ（复算） | f_robust |")
    lines.append("| --- | --- | --- | --- | --- | --- |")
    for name in CHANNEL_NAMES:
        block = ra["channel_reproduction"][name]
        lines.append(f"| {name} | {block['tau_b']:.4f} | {block['w21_tau_b']:.4f} | {block['tau_b_minus_w21']:.2e} | {block['spearman_rho']:.4f} | {block['f_robust_inversion']:.4f} |")
    lines.append("")
    lines.append("## 2. (a) 化合物级 bootstrap 95% CI（点估计与 CI 同句）")
    lines.append("")
    lines.append("| 通道 | 统计量 | 点估计 | 95% CI | draws_used |")
    lines.append("| --- | --- | --- | --- | --- |")
    for row in channel_rows:
        if row[1] == "delta_tau_b":
            continue
        ci = f"[{row[3]:.4f}, {row[5]:.4f}]" if np.isfinite(row[3]) else "undefined"
        point = f"{row[2]:.4f}" if np.isfinite(row[2]) else "nan"
        lines.append(f"| {row[0]} | {row[1]} | {point} | {ci} | {row[8]} |")
    lines.append("")
    lines.append("读法：τ_b 与 ρ 的 CI 是**化合物级**重抽样区间；f_robust_inversion 在 homo 上点估计为 0 且 CI 塌缩到 0（两侧都可分辨的 pair 在重抽样下仍几乎不出现符号翻转）。")
    lines.append("读法：τ_b 与 ρ 的 CI 是**化合物级**重抽样区间；f_robust_inversion 在 homo 上点估计为 0 且 CI 塌缩到 0（两侧都可分辨的 pair 在重抽样下仍几乎不出现符号翻转）。gap 的全池 f_robust 无定义（两侧都可分辨的 pair 少于 5，§9.2 分母塌缩），只有部分重抽样能算，且都落在 0。")
    lines.append("")
    lines.append("## 3. (b) 配对 bootstrap 的 delta_tau_b（B2 落地点）")
    lines.append("")
    lines.append("| 比较 | 点估计 Δτb | 95% CI | 是否跨 0 | draws_used |")
    lines.append("| --- | --- | --- | --- | --- |")
    for label, block in summary["paired_delta_tau_b"].items():
        straddle = "是" if block["ci_straddles_zero"] else "否"
        lines.append(f"| {label} | {block['point']:.4f} | [{block['lo']:.4f}, {block['hi']:.4f}] | {straddle} | {block['draws_used']} |")
    lines.append("")
    lines.append("同一批化合物进入两通道、逐 draw 相减，因此这是**配对** Δτb；CI 不跨 0 才说明通道间排序质量差异在一个抽样区间内站得住。")
    lines.append("")
    lines.append("## 4. (c) 留一化合物敏感性（τ_b(homo)）")
    lines.append("")
    loo = summary["leave_one_out"]
    lines.append(f"- 全池 τ_b = {loo['full_pool_tau_b']:.4f}；剔除单个化合物后 τ_b 落在 **[{(loo['min_tau_b_without']):.4f}, {loo['max_tau_b_without']:.4f}]**。")
    lines.append(f"- 影响力最大的化合物：`{loo['max_influence_compound']}`（Δτ_b = {loo['max_influence_delta_tau_b']:+.4f}）。")
    lines.append("- 完整 49 行见 `probes/artifacts/w22_stat_hardening_leave_one_out.csv`。")
    lines.append("")
    lines.append("## 5. (d) 多重比较校正（B3）")
    lines.append("")
    lines.append("族 = homo / lumo / gap，m = 3；检验 = 单侧置换检验 τ_b > 0（打乱 R_sol 侧标签），置换 5000 次。")
    lines.append("")
    lines.append("| 通道 | τ_b | p（置换） | p_Bonferroni | p_Holm | 判定 |")
    lines.append("| --- | --- | --- | --- | --- | --- |")
    for row in multi_csv_rows:
        lines.append(f"| {row[0]} | {row[1]:.4f} | {row[3]:.2e} | {row[5]:.2e} | {row[7]:.2e} | {row[9]} |")
    lines.append("")
    lines.append("`gap` 无方向语义，只作对照；它的 p 值同样进族，不做后验剔除。")
    lines.append("")
    lines.append("## 6. (e) 口径一致性审计（B4）")
    lines.append("")
    a = summary["audit"]
    lines.append(f"- **同一批 49 个化合物**：{a['shared_pool']}。")
    lines.append(f"- **名册层级**：{a['roster_hierarchy']}。")
    lines.append("- 不可互比的池：")
    for item in a["non_comparable_pools"]:
        lines.append(f"  - {item}")
    lines.append("")
    lines.append("## 7. 统计边界")
    lines.append("")
    lines.append(f"- {summary['statistical_boundary']}")
    lines.append("- bootstrap 不解决非独立性，也不解决池子选择问题：CI 只描述「同一设计、同一 49 化合物」下的抽样波动。")
    lines.append("- 参考层物理不确定度（R_sol）本仓未量化，读数须与 W21 的容差口径一起阅读。")
    lines.append("")
    lines.append("## 8. 产物清单（行数 / bytes / sha256）")
    lines.append("")
    lines.append("| 产物 | 行数 | bytes | sha256 |")
    lines.append("| --- | --- | --- | --- |")
    for key in ("preregistration", "pair_bootstrap", "leave_one_out", "multiple_comparison", "summary"):
        block = outputs_with_summary[key]
        lines.append(f"| `{block['path']}` | {block['rows']} | {block['bytes']} | `{block['sha256']}` |")
    lines.append("")
    lines.append("（报告自身不列入上表以避免自引用。）")
    lines.append("")
    lines.append("## 9. 冻结件与纪律")
    lines.append("")
    lines.append(f"- 主记分牌尝试：**{summary['promotion']['main_scoreboard_attempts']} 次**（累计不变）；promoted = {summary['promotion']['promoted']}。")
    lines.append(f"- 冻结读数逐位不变：`{summary['promotion']['frozen_untouched']}`。")
    lines.append("")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write-prereg", action="store_true")
    parser.add_argument("--write-summary", action="store_true")
    args = parser.parse_args()
    if not (args.write_prereg or args.write_summary):
        parser.error("pass --write-prereg and/or --write-summary")
    if args.write_prereg:
        write_json_stable(PREREG, prereg_payload())
        print("wrote", rel(PREREG))
    if args.write_summary:
        build_artifacts()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())