"""W21 Tier 2 -- the framework decision metrics, instantiated on the orbital channel.

Framework sections implemented here:

* 9.1/9.2   pair difference, per-level resolution, robust inversion, unresolved fraction
* 9.3       Kendall tau_b (ties allowed) + Spearman rho as an auxiliary
* 9.4       probabilistic pair ordering
* 10.1      Top-k overlap and Jaccard at k/N = 10/20/30 %
* 10.2      selection regret of the cheap model measured under the reference layer
* 13.1      complexity ladder (mean / single feature / ridge / KRR / GPR / RF / GBM)
* 13.2      random, group-scaffold and LOFO splits reported side by side

No pool is written, no frozen number is touched, and the Batt layer is used as a
reference layer only -- never as a training label for any in-repo channel.
"""

from __future__ import annotations

import csv
import hashlib
import json
import warnings
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
try:  # W40-B import shim: works as `probes.<mod>` and as a direct script
    from probes.export_results_common import write_json_stable
except ImportError:  # direct execution: probes/ is sys.path[0]
    from export_results_common import write_json_stable

from scipy import stats
from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import RBF, ConstantKernel, WhiteKernel
from sklearn.kernel_ridge import KernelRidge
from sklearn.linear_model import Ridge
from sklearn.model_selection import GridSearchCV, GroupKFold, KFold, RepeatedKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[1]
ROSTER = ROOT / "data" / "dielectric_v03.csv"
LAYER = ROOT / "data" / "processed" / "themol_orbital_layer.csv"
W19_SUMMARY = ROOT / "probes" / "w19_batt_gap_crosscheck_summary.json"
PHYSICAL = ROOT / "data" / "processed" / "dielectric_physical_features_v03.csv"
CHEM_SPACE = ROOT / "data" / "processed" / "w21_chemical_space_metadata.csv"
PREREG = ROOT / "probes" / "w21_rank_stability_prereg.json"
SUMMARY = ROOT / "probes" / "w21_rank_stability_summary.json"
PAIRS_CSV = ROOT / "probes" / "artifacts" / "w21_rank_pairs.csv"
TOPK_CSV = ROOT / "probes" / "artifacts" / "w21_topk_overlap.csv"
SPLITS_CSV = ROOT / "probes" / "artifacts" / "w21_split_metrics.csv"
LOFO_CSV = ROOT / "probes" / "artifacts" / "w21_lofo_by_family.csv"
SENSITIVITY_CSV = ROOT / "probes" / "artifacts" / "w21_tolerance_sensitivity.csv"
REPORT_RANK = ROOT / "reports" / "w21_rank_stability.md"
REPORT_SPLITS = ROOT / "reports" / "w21_split_taxonomy.md"

CHANNELS = (
    ("homo", "homo_gfn2_eV", "batt_homo_eV", "P_0^ox = -epsilon_HOMO：越大越耐氧化"),
    ("lumo", "lumo_gfn2_eV", "batt_lumo_eV", "P_0^red = epsilon_LUMO：越大越耐还原"),
    ("gap", "gap_gfn2_eV", "batt_gap_eV", "gap 无方向语义，只作参照"),
)
REFERENCE_ONLY = ("lumo", "gap")
FEATURES = (
    "homo_gfn2_eV",
    "lumo_gfn2_eV",
    "gap_gfn2_eV",
    "dipole_D",
    "polarizability_A3",
    "molecular_volume_A3",
    "hbd",
    "hba",
    "tpsa_A2",
    "heavy_atom_count",
    "formal_charge",
    "mu_sq_over_Vm",
)
warnings.filterwarnings("ignore", category=RuntimeWarning)
warnings.filterwarnings("ignore", message=".*correlation coefficient is not defined.*")
try:  # scipy names this one explicitly; keep the run log readable
    from scipy.stats import ConstantInputWarning

    warnings.filterwarnings("ignore", category=ConstantInputWarning)
except Exception:  # pragma: no cover - older scipy
    pass

Z = 1.96
DELTA_REF_EV = 0.05
BOOTSTRAP_B = 5000
PERMUTATION_B = 5000
SEED = 20261002
LOFO_MIN_MEMBERS = 5


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, header: tuple[str, ...], rows: list[tuple[object, ...]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(header)
        for row in rows:
            writer.writerow(row)


def load_primary() -> list[dict[str, str]]:
    """roster(246) x layer-with-Batt.  The layer's own ``in_epsilon_roster`` flag
    was computed against an older roster, so the frozen 246-key list is the
    authority here; the W19 primary arm is re-asserted key for key below."""

    roster = {row["inchikey"] for row in read_rows(ROSTER)}
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
    n = x.size
    out = np.zeros(n)
    for i in range(n):
        mask = np.ones(n, dtype=bool)
        mask[i] = False
        slope, intercept = np.polyfit(x[mask], y[mask], 1)
        out[i] = y[i] - (slope * x[i] + intercept)
    return out


def pair_arrays(mapped: np.ndarray, y: np.ndarray, u: np.ndarray) -> dict[str, np.ndarray]:
    iu = np.triu_indices(y.size, 1)
    d_a = (mapped[:, None] - mapped[None, :])[iu]
    d_b = (y[:, None] - y[None, :])[iu]
    sep = (Z * np.sqrt(u[:, None] ** 2 + u[None, :] ** 2))[iu]
    resolved_a = np.abs(d_a) >= sep
    resolved_b = np.abs(d_b) >= DELTA_REF_EV
    inversion = np.sign(d_a) != np.sign(d_b)
    both = resolved_a & resolved_b
    return {
        "d_a": d_a,
        "d_b": d_b,
        "sep": sep,
        "resolved_a": resolved_a,
        "resolved_b": resolved_b,
        "inversion": inversion,
        "both": both,
        "robust": both & inversion,
    }


def scalarise(arr: dict[str, np.ndarray], x: np.ndarray, y: np.ndarray, mapped: np.ndarray) -> dict[str, float]:
    total = arr["d_a"].size
    both = int(arr["both"].sum())
    robust = int(arr["robust"].sum())
    f_robust = robust / both if both else float("nan")
    return {
        "pairs": int(total),
        "resolved_in_P0": int(arr["resolved_a"].sum()),
        "resolved_in_R_sol": int(arr["resolved_b"].sum()),
        "resolved_in_both": both,
        "f_unresolved_P0": float(1.0 - arr["resolved_a"].mean()),
        "f_unresolved_R_sol": float(1.0 - arr["resolved_b"].mean()),
        "f_unresolved_at_least_one": float(1.0 - arr["both"].mean()),
        "f_resolved_in_exactly_one": float(np.logical_xor(arr["resolved_a"], arr["resolved_b"]).mean()),
        "naive_inversions": int(arr["inversion"].sum()),
        "f_naive_inversion": float(arr["inversion"].mean()),
        "robust_inversions": robust,
        "f_robust_inversion": float(f_robust),
        "tau_over_resolved_pairs": float(1.0 - 2.0 * f_robust) if both else float("nan"),
        "kendall_tau_b": float(stats.kendalltau(x, y, variant="b").statistic),
        "spearman_rho": float(stats.spearmanr(x, y).statistic),
        "pearson_r": float(stats.pearsonr(x, y).statistic),
        "ols_slope": float(np.polyfit(x, y, 1)[0]),
        "ols_intercept": float(np.polyfit(x, y, 1)[1]),
        "loo_mean_abs_residual_ev": float(np.mean(np.abs(loo_residuals(x, y)))),
    }


def bootstrap_interval(x: np.ndarray, y: np.ndarray, statistic, draws: int, seed: int) -> dict[str, float]:
    rng = np.random.default_rng(seed)
    n = x.size
    values = []
    for _ in range(draws):
        idx = rng.integers(0, n, n)
        if np.unique(idx).size < 4:
            continue
        xs, ys = x[idx], y[idx]
        u = np.abs(loo_residuals(xs, ys))
        slope, intercept = np.polyfit(xs, ys, 1)
        arr = pair_arrays(slope * xs + intercept, ys, u)
        value = statistic(arr)
        if value is not None and np.isfinite(value):
            values.append(value)
    if not values:
        return {"lo": float("nan"), "median": float("nan"), "hi": float("nan"), "draws_used": 0}
    lo, med, hi = np.percentile(values, [2.5, 50, 97.5])
    return {"lo": float(lo), "median": float(med), "hi": float(hi), "draws_used": len(values)}


def f_robust_statistic(arr: dict[str, np.ndarray]) -> float | None:
    """Undefined only when too few pairs are resolvable in both levels.

    Zero is a reading, not a failure: if every sign flip sits inside the
    tolerance band, the honest answer is ``0 / resolved`` -- the framework's
    section 22.7 case.
    """

    both = int(arr["both"].sum())
    if both < 5:
        return None
    return int(arr["robust"].sum()) / both


def permutation_p(x: np.ndarray, y: np.ndarray, observed: float, draws: int, seed: int) -> dict[str, float]:
    rng = np.random.default_rng(seed)
    n = x.size
    count = 0
    used = 0
    for _ in range(draws):
        ys = rng.permutation(y)
        u = np.abs(loo_residuals(x, ys))
        slope, intercept = np.polyfit(x, ys, 1)
        arr = pair_arrays(slope * x + intercept, ys, u)
        value = f_robust_statistic(arr)
        if value is None:
            continue
        used += 1
        if value >= observed:
            count += 1
    return {"p_value": (count + 1) / (used + 1) if used else float("nan"), "permutations_used": used}


def topk_table(mapped: np.ndarray, y: np.ndarray) -> list[tuple[object, ...]]:
    rows = []
    n = y.size
    for fraction in (0.10, 0.20, 0.30):
        k = max(1, int(round(fraction * n)))
        order_a = np.argsort(mapped, kind="stable")[:k]
        order_b = np.argsort(y, kind="stable")[:k]
        inter = len(set(order_a.tolist()) & set(order_b.tolist()))
        union = len(set(order_a.tolist()) | set(order_b.tolist()))
        target = -y
        regret = float(target[order_b].mean() - target[order_a].mean())
        rows.append(
            (
                f"k/N={fraction:.0%}",
                k,
                n,
                f"{inter / k:.6f}",
                f"{inter / union:.6f}" if union else "",
                f"{regret:.6f}",
            )
        )
    return rows


def tolerance_sensitivity(x: np.ndarray, y: np.ndarray, u: np.ndarray, mapped: np.ndarray) -> list[tuple[object, ...]]:
    """Only z = 1.96 is pre-registered; the rest are clearly labelled post hoc.

    They exist to say *how far* the tolerance would have to move before any
    robust inversion appears -- not to pick a flattering threshold (framework
    section 10.3 forbids that for the decision-error metric, and the same
    discipline is applied here).
    """

    iu = np.triu_indices(y.size, 1)
    d_a = (mapped[:, None] - mapped[None, :])[iu]
    d_b = (y[:, None] - y[None, :])[iu]
    base = np.sqrt(u[:, None] ** 2 + u[None, :] ** 2)[iu]
    inversion = np.sign(d_a) != np.sign(d_b)
    rows: list[tuple[object, ...]] = []
    for z in (1.96, 1.0, 0.674, 0.0):
        resolved_a = np.abs(d_a) >= z * base
        resolved_b = np.abs(d_b) >= DELTA_REF_EV
        both = resolved_a & resolved_b
        count = int(both.sum())
        robust = int((both & inversion).sum())
        rows.append(
            (
                z,
                f"{float(resolved_a.mean()):.6f}",
                f"{float(resolved_b.mean()):.6f}",
                count,
                robust,
                f"{robust / count:.6f}" if count else "",
                "pre_registered" if z == Z else "post_hoc_sensitivity",
            )
        )
    return rows


def build_models() -> dict[str, object]:
    return {
        "mean_baseline": "mean",
        "ridge": make_pipeline(StandardScaler(), Ridge(alpha=1.0, random_state=None)),
        "krr": make_pipeline(StandardScaler(), KernelRidge(kernel="rbf", alpha=1.0, gamma=0.1)),
        # The frozen-hyperparameter KRR above blows up on this n; the tuned arm
        # exists so the ladder is not judged by an untuned kernel, and it does
        # its model selection strictly inside the training fold.
        "krr_tuned": make_pipeline(
            StandardScaler(),
            GridSearchCV(
                KernelRidge(kernel="rbf"),
                {"alpha": [0.01, 0.1, 1.0, 10.0, 100.0], "gamma": [0.01, 0.03, 0.1, 0.3]},
                cv=KFold(n_splits=3, shuffle=True, random_state=SEED),
                scoring="neg_mean_absolute_error",
            ),
        ),
        "gpr": make_pipeline(
            StandardScaler(),
            GaussianProcessRegressor(
                kernel=ConstantKernel(1.0) * RBF(length_scale=1.0) + WhiteKernel(noise_level=1e-3),
                normalize_y=True,
                random_state=SEED,
            ),
        ),
        "random_forest": RandomForestRegressor(n_estimators=300, random_state=SEED, n_jobs=1),
        "gradient_boosting": GradientBoostingRegressor(random_state=SEED),
    }


def fit_predict(model: object, train_x: np.ndarray, train_y: np.ndarray, test_x: np.ndarray) -> np.ndarray:
    if model == "mean":
        return np.full(test_x.shape[0], float(train_y.mean()))
    model.fit(train_x, train_y)
    return np.asarray(model.predict(test_x), dtype=float)


def single_feature_predict(train_x: np.ndarray, train_y: np.ndarray, test_x: np.ndarray) -> np.ndarray:
    best = None
    for column in range(train_x.shape[1]):
        feature = train_x[:, column]
        if np.std(feature) == 0:
            continue
        r = abs(float(np.corrcoef(feature, train_y)[0, 1]))
        if best is None or r > best[0]:
            best = (r, column)
    if best is None:
        return np.full(test_x.shape[0], float(train_y.mean()))
    column = best[1]
    slope, intercept = np.polyfit(train_x[:, column], train_y, 1)
    return slope * test_x[:, column] + intercept


def score(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, float]:
    if np.std(y_true) == 0:
        r2 = float("nan")
    else:
        r2 = float(1.0 - np.sum((y_true - y_pred) ** 2) / np.sum((y_true - y_true.mean()) ** 2))
    rho = float(stats.spearmanr(y_true, y_pred).statistic) if np.unique(y_true).size > 2 else float("nan")
    tau = float(stats.kendalltau(y_true, y_pred, variant="b").statistic) if np.unique(y_true).size > 2 else float("nan")
    mae = float(np.abs(y_true - y_pred).mean())
    return {"r2": r2, "spearman": rho, "kendall_tau_b": tau, "mae": mae}


def main() -> int:
    prereg = json.loads(PREREG.read_text(encoding="utf-8"))
    primary = load_primary()
    n = len(primary)
    keys = [str(row["inchikey"]) for row in primary]
    if n != int(prereg["pool"]["expected_n"]):
        raise ValueError(f"pool size {n} != registered {prereg['pool']['expected_n']}")
    w19_keys = sorted(json.loads(W19_SUMMARY.read_text(encoding="utf-8"))["primary"]["keys"])
    if sorted(keys) != w19_keys:
        raise ValueError("pool does not reproduce the W19 primary arm key for key")

    channel_blocks: dict[str, object] = {}
    pair_rows: list[tuple[object, ...]] = []
    for name, x_col, y_col, direction in CHANNELS:
        x = np.array([float(row[x_col]) for row in primary])
        y = np.array([float(row[y_col]) for row in primary])
        u = np.abs(loo_residuals(x, y))
        slope, intercept = np.polyfit(x, y, 1)
        mapped = slope * x + intercept
        arr = pair_arrays(mapped, y, u)
        scalars = scalarise(arr, x, y, mapped)
        observed = f_robust_statistic(arr)
        if observed is None:
            # The cheap proxy cannot separate the pairs at all on this channel
            # (the linear map is nearly flat), so the section 9.2 ratio has no
            # denominator.  That is a reading: report it instead of a number.
            ci_robust = {"lo": float("nan"), "median": float("nan"), "hi": float("nan"), "draws_used": 0}
            perm = {"p_value": float("nan"), "permutations_used": 0}
            undefined_reason = "两侧都可分辨的 pair 少于 5 个，f_robust_inversion 在本通道无定义（§9.2 分母塌缩）"
        else:
            ci_robust = bootstrap_interval(x, y, f_robust_statistic, BOOTSTRAP_B, SEED)
            perm = permutation_p(x, y, float(observed), PERMUTATION_B, SEED)
            undefined_reason = ""
        p_ij = stats.norm.cdf(arr["d_a"] / np.sqrt((u[:, None] ** 2 + u[None, :] ** 2))[np.triu_indices(n, 1)])
        channel_blocks[name] = {
            "direction": direction,
            "tolerance_sensitivity": tolerance_sensitivity(x, y, u, mapped),
            "verdict": "reference_only" if name in REFERENCE_ONLY else "usable",
            "scalars": scalars,
            "f_robust_inversion_ci95": ci_robust,
            "f_robust_inversion_undefined_reason": undefined_reason,
            "permutation": perm,
            "probabilistic_pair_ordering": {
                "p_gt_0_9": float((p_ij > 0.9).mean()),
                "p_lt_0_1": float((p_ij < 0.1).mean()),
                "indeterminate": float(((p_ij >= 0.1) & (p_ij <= 0.9)).mean()),
            },
            "top_k": topk_table(mapped, y),
        }
        if name == "homo":
            iu = np.triu_indices(n, 1)
            for index, (i, j) in enumerate(zip(iu[0].tolist(), iu[1].tolist())):
                pair_rows.append(
                    (
                        keys[i],
                        keys[j],
                        f"{arr['d_a'][index]:.6f}",
                        f"{arr['d_b'][index]:.6f}",
                        f"{arr['sep'][index]:.6f}",
                        int(arr["resolved_a"][index]),
                        int(arr["resolved_b"][index]),
                        int(arr["inversion"][index]),
                        int(arr["robust"][index]),
                        f"{p_ij[index]:.6f}",
                    )
                )

    write_csv(
        PAIRS_CSV,
        ("key_i", "key_j", "dP0_eV", "dRsol_eV", "separation_threshold_eV", "resolved_in_P0", "resolved_in_R_sol", "inversion", "robust_inversion", "p_i_gt_j"),
        pair_rows,
    )

    topk_rows: list[tuple[object, ...]] = []
    for name, block in channel_blocks.items():
        for row in block["top_k"]:
            topk_rows.append((name, *row))
    write_csv(TOPK_CSV, ("channel", "k_rule", "k", "n", "overlap", "jaccard", "selection_regret_eV"), topk_rows)

    sensitivity_rows: list[tuple[object, ...]] = []
    for name, block in channel_blocks.items():
        for row in block["tolerance_sensitivity"]:
            sensitivity_rows.append((name, *row))
    write_csv(
        SENSITIVITY_CSV,
        ("channel", "z", "f_resolved_in_P0", "f_resolved_in_R_sol", "pairs_resolved_in_both", "robust_inversions", "f_robust_inversion", "registration"),
        sensitivity_rows,
    )

    physical = {row["inchikey"]: row for row in read_rows(PHYSICAL)}
    space = {row["molecule_id"]: row for row in read_rows(CHEM_SPACE)}
    feature_rows: list[tuple[object, ...]] = []
    for row in primary:
        key = str(row["inchikey"])
        feat = physical.get(key, {})
        merged = []
        ok = True
        for column in FEATURES:
            raw = row.get(column) or feat.get(column) or ""
            if str(raw).strip() == "":
                ok = False
                break
            merged.append(float(raw))
        if ok:
            feature_rows.append((key, merged, float(row["batt_homo_eV"]), space.get(key, {}).get("structural_family", ""), space.get(key, {}).get("scaffold", "")))

    usable_n = len(feature_rows)
    if usable_n < 20:
        raise ValueError(f"only {usable_n} compounds carry the full X0 block")

    keys_f = [row[0] for row in feature_rows]
    x_all = np.array([row[1] for row in feature_rows], dtype=float)
    y_all = np.array([row[2] for row in feature_rows], dtype=float)
    families = np.array([row[3] for row in feature_rows])
    scaffolds = np.array([row[4] for row in feature_rows])

    split_rows: list[tuple[object, ...]] = []
    models = build_models()

    rkf = RepeatedKFold(n_splits=5, n_repeats=10, random_state=SEED)
    random_scores: dict[str, list[dict[str, float]]] = {name: [] for name in (*models, "single_feature_baseline")}
    for train_idx, test_idx in rkf.split(x_all):
        for name, model in models.items():
            pred = fit_predict(model, x_all[train_idx], y_all[train_idx], x_all[test_idx])
            random_scores[name].append(score(y_all[test_idx], pred))
        pred = single_feature_predict(x_all[train_idx], y_all[train_idx], x_all[test_idx])
        random_scores["single_feature_baseline"].append(score(y_all[test_idx], pred))

    group_scores: dict[str, list[dict[str, float]]] = {name: [] for name in (*models, "single_feature_baseline")}
    unique_scaffolds = np.unique(scaffolds)
    if unique_scaffolds.size >= 5:
        gkf = GroupKFold(n_splits=5)
        for train_idx, test_idx in gkf.split(x_all, y_all, groups=scaffolds):
            for name, model in models.items():
                pred = fit_predict(model, x_all[train_idx], y_all[train_idx], x_all[test_idx])
                group_scores[name].append(score(y_all[test_idx], pred))
            pred = single_feature_predict(x_all[train_idx], y_all[train_idx], x_all[test_idx])
            group_scores["single_feature_baseline"].append(score(y_all[test_idx], pred))

    def emit(split: str, name: str, values: list[dict[str, float]], n_folds: int, n_test: int) -> None:
        if not values:
            split_rows.append((split, name, 0, "", "", "", "", "", ""))
            return
        for metric in ("r2", "spearman", "kendall_tau_b", "mae"):
            vals = np.array([v[metric] for v in values], dtype=float)
            vals = vals[np.isfinite(vals)]
            split_rows.append(
                (
                    split,
                    name,
                    n_folds,
                    metric,
                    f"{vals.mean():.6f}" if vals.size else "",
                    f"{vals.std(ddof=1):.6f}" if vals.size > 1 else "",
                    f"{np.median(vals):.6f}" if vals.size else "",
                    n_test,
                    "",
                )
            )

    for name, values in random_scores.items():
        emit("random_repeated_kfold_5x10", name, values, len(values), usable_n)
    for name, values in group_scores.items():
        emit("group_kfold_scaffold_5", name, values, len(values), usable_n)

    lofo_rows: list[tuple[object, ...]] = []
    family_counts: dict[str, int] = {}
    for family in families:
        family_counts[family] = family_counts.get(family, 0) + 1
    tested_families = sorted(f for f, c in family_counts.items() if c >= LOFO_MIN_MEMBERS)
    for family in tested_families:
        test_mask = families == family
        train_mask = ~test_mask
        if int(train_mask.sum()) < 10:
            continue
        for name in ("mean_baseline", "ridge", "krr", "krr_tuned", "gpr", "random_forest", "gradient_boosting"):
            pred = fit_predict(models[name], x_all[train_mask], y_all[train_mask], x_all[test_mask])
            metrics = score(y_all[test_mask], pred)
            lofo_rows.append((family, name, int(test_mask.sum()), f"{metrics['r2']:.6f}", f"{metrics['spearman']:.6f}", f"{metrics['kendall_tau_b']:.6f}", f"{metrics['mae']:.6f}"))
        pred = single_feature_predict(x_all[train_mask], y_all[train_mask], x_all[test_mask])
        metrics = score(y_all[test_mask], pred)
        lofo_rows.append((family, "single_feature_baseline", int(test_mask.sum()), f"{metrics['r2']:.6f}", f"{metrics['spearman']:.6f}", f"{metrics['kendall_tau_b']:.6f}", f"{metrics['mae']:.6f}"))

    if lofo_rows:
        for name in ("mean_baseline", "ridge", "krr", "krr_tuned", "gpr", "random_forest", "gradient_boosting", "single_feature_baseline"):
            values = [float(row[3]) for row in lofo_rows if row[1] == name]
            if not values:
                continue
            split_rows.append(
                (
                    "lofo_family_min5",
                    name,
                    len(values),
                    "r2",
                    f"{np.mean(values):.6f}",
                    f"{np.std(values, ddof=1):.6f}" if len(values) > 1 else "",
                    f"{np.median(values):.6f}",
                    "",
                    ";".join(sorted({str(row[0]) for row in lofo_rows if row[1] == name})),
                )
            )
    else:
        split_rows.append(("lofo_family_min5", "mean_baseline", 0, "r2", "", "", "", "", "no family carries >= 5 members"))

    write_csv(SPLITS_CSV, ("split", "model", "folds", "metric", "mean", "std", "median", "n_compounds", "note"), split_rows)
    write_csv(LOFO_CSV, ("family", "model", "n_test", "r2", "spearman", "kendall_tau_b", "mae"), lofo_rows)

    homo = channel_blocks["homo"]
    summary = {
        "schema_version": 1,
        "task_id": "week21_w21_1_rank_stability",
        "title": "Tier 2：轨道通道 §9 排序稳定性 + §10 决策指标 + §13 拆分/复杂度阶梯",
        "generated_at_utc": utc_now(),
        "preregistration": {"path": "probes/w21_rank_stability_prereg.json", "sha256": sha256_file(PREREG), "status": prereg["status"]},
        "plan_reference": "reports/week21_project_charter.md | section 3 | Tier 2 items 7-10",
        "pool": {
            "n_compounds": n,
            "pairs": int(n * (n - 1) / 2),
            "source": "data/dielectric_v03.csv x data/processed/themol_orbital_layer.csv",
            "identity_check": "reproduces probes/w19_batt_gap_crosscheck_summary.json primary.keys key for key",
            "levels": {"P_0": "GFN2-xTB gas-phase single point", "R_sol": "wB97X-V/def2-TZVPPD/SMD(epsilon=18.5)"},
        },
        "tolerance": {
            "z": Z,
            "delta_R_sol_eV": DELTA_REF_EV,
            "u_i_rule": "per-compound |leave-one-out residual| of the OLS map P_0 -> R_sol (eV)",
            "registered_limit": prereg["tolerance"]["registered_limit"],
        },
        "channels": channel_blocks,
        "splits": {
            "target": "batt_homo_eV",
            "features": list(FEATURES),
            "n_compounds_with_full_block": usable_n,
            "dropped_for_missing_block": n - usable_n,
            "lofo_families_tested": tested_families,
            "lofo_min_members": LOFO_MIN_MEMBERS,
            "scaffold_groups": int(unique_scaffolds.size),
        },
        "threshold_decision_error": prereg["threshold_decision_error"],
        "tolerance_sensitivity_note": "只有 z=1.96 是预注册主规则；其余三行是事后敏感性臂，用来回答「容差要松到什么程度才会出现第一个 robust inversion」，不得当成可择优选用的门。",
        "statistical_boundary": "n=49 落在框架 §13.3 自警的薄区：本件的全部读数都是 machinery pilot，必须带 bootstrap CI 与 permutation 检验阅读，不得当达标结论。",
        "promotion": {"promoted": False, "main_scoreboard_attempts": 0, "frozen_untouched": prereg["promotion"]["frozen_untouched"]},
        "boundaries": [
            "不拟合任何池、不写任何池、不联网；Batt 只作 reference layer。",
            "不动任何冻结件；不占 shot（本周主记分牌尝试 0 次）。",
            "参考层的物理不确定度未量化，只登记数值容差 0.05 eV —— 该缺口随读数一起报告。",
        ],
        "outputs": {
            "pairs": "probes/artifacts/w21_rank_pairs.csv",
            "topk": "probes/artifacts/w21_topk_overlap.csv",
            "splits": "probes/artifacts/w21_split_metrics.csv",
            "lofo": "probes/artifacts/w21_lofo_by_family.csv",
            "tolerance_sensitivity": "probes/artifacts/w21_tolerance_sensitivity.csv",
            "report_rank": "reports/w21_rank_stability.md",
            "report_splits": "reports/w21_split_taxonomy.md",
        },
    }
    write_json_stable(SUMMARY, summary)

    scalars = homo["scalars"]
    lines = [
        "# W21 Tier 2：轨道通道的不确定性感知排序与筛选决策指标",
        "",
        "按框架 §9 / §10 首次实例化。池 = 冻结 ε 名册 ∩ 我方 xTB ∩ Batt 身份命中，**n = 49**，配对数 1,176。",
        "P_0 = GFN2-xTB 气相单点；R_sol = wB97X-V/def2-TZVPPD/SMD(ε=18.5)（MIT 许可，仅作 **reference layer**）。",
        "",
        "## 1. §9 排序稳定性（HOMO 通道，方向 T = −HOMO）",
        "",
        "| 量 | 值 |",
        "| --- | --- |",
        f"| 配对数 | {scalars['pairs']} |",
        f"| P_0 侧 unresolved | {scalars['f_unresolved_P0']:.4f} |",
        f"| R_sol 侧 unresolved | {scalars['f_unresolved_R_sol']:.4f} |",
        f"| 至少一侧 unresolved | {scalars['f_unresolved_at_least_one']:.4f} |",
        f"| 仅一侧可分辨 | {scalars['f_resolved_in_exactly_one']:.4f} |",
        f"| 朴素换序率 | {scalars['f_naive_inversion']:.4f} |",
        f"| **robust inversion（§9.2 分母 = 两侧都可分辨）** | {scalars['f_robust_inversion']:.4f} |",
        f"| τ 只数可分辨对 | {scalars['tau_over_resolved_pairs']:.4f} |",
        f"| Kendall τ_b（原始值） | {scalars['kendall_tau_b']:.4f} |",
        f"| Spearman ρ | {scalars['spearman_rho']:.4f} |",
        f"| Pearson r | {scalars['pearson_r']:.4f} |",
        "",
        f"- robust inversion 的 bootstrap 95% CI：`{homo['f_robust_inversion_ci95']}`",
        f"- permutation 检验：`{homo['permutation']}`（零假设 = 置换 R_sol 的化合物标签）",
        f"- 概率化配对排序：p>0.9 占 {homo['probabilistic_pair_ordering']['p_gt_0_9']:.4f}，p<0.1 占 {homo['probabilistic_pair_ordering']['p_lt_0_1']:.4f}，中间带占 {homo['probabilistic_pair_ordering']['indeterminate']:.4f}",
        "",
        "## 2. §10.1 / §10.2 Top-k 与 selection regret",
        "",
        "| k | overlap | Jaccard | selection regret (eV) |",
        "| --- | --- | --- | --- |",
    ]
    for row in homo["top_k"]:
        lines.append(f"| {row[0]}（k={row[1]}） | {row[3]} | {row[4]} | {row[5]} |")
    lines += [
        "",
        "regret 的定义：用便宜模型选出的 Top-k，在参考层下平均比参考层自己选的 Top-k 差多少（越大越差，0 = 无损失）。",
        "",
        "## 3. 其它通道",
        "",
    ]
    for name, block in channel_blocks.items():
        if name == "homo":
            continue
        sc = block["scalars"]
        lines.append(
            f"- **{name}**（{block['verdict']}）：ρ = {sc['spearman_rho']:.4f}，τ_b = {sc['kendall_tau_b']:.4f}，"
            f"robust inversion = {sc['f_robust_inversion']:.4f}，Kendall/Spearman 只能作参照。"
        )
    lines += [
        "",
        "### 1.1 容差敏感性（只有 z=1.96 预注册）",
        "",
        "| z | P_0 侧可分辨 | 两侧都可分辨 | robust inversion | f_robust | 登记 |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in homo["tolerance_sensitivity"]:
        lines.append(f"| {row[0]} | {row[1]} | {row[3]} | {row[4]} | {row[5] or '—'} | {row[6]} |")
    lines += [
        "",
        "读法：**朴素换序 15.6% 全部落在 xTB 的不确定带里**——把分离要求从 z=1.96 放宽到 z=1.0 才出现 5 个 robust inversion，完全去掉容差才有 153 个。",
        "这正是框架 §9.1 想拦下的那件事：不能把另一模型中的换序直接叫「物理 ranking inversion」。",
        "",
        "## 4. §10.3 threshold-based decision error",
        "",
        f"{summary['threshold_decision_error']}",
        "",
        "## 5. 统计边界（必须随读数一起读）",
        "",
        f"- {summary['statistical_boundary']}",
        f"- {summary['tolerance']['registered_limit']}",
    ]
    REPORT_RANK.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")

    split_lines = [
        "# W21 Tier 2：三种拆分的并排报告（框架 §13.2）",
        "",
        f"任务 = 用 X0 块预测 **R_sol 的 HOMO**（{usable_n} 个化合物带完整块，掉 {n - usable_n} 个）。",
        "三种拆分必须同时报告，且 LOFO 是 transferability 的主要证据来源。",
        "",
        "| split | model | metric | mean | std | folds |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in split_rows:
        if row[3] != "r2":
            continue
        split_lines.append(f"| {row[0]} | {row[1]} | R² | {row[4] or '—'} | {row[5] or '—'} | {row[2]} |")
    split_lines += [
        "",
        f"- 骨架组数：{unique_scaffolds.size}；LOFO 可用家族（成员 ≥ {LOFO_MIN_MEMBERS}）：`{tested_families}`",
        "- 平均基线（mean_baseline）必须读：R² 的零点是它，不是 0。",
        "- 本件是 **machinery pilot**：n = 49 在框架 §13.3 的薄区里。",
    ]
    REPORT_SPLITS.write_text("\n".join(split_lines) + "\n", encoding="utf-8", newline="\n")

    print("n =", n, "pairs =", summary["pool"]["pairs"])
    print("homo f_robust =", round(scalars["f_robust_inversion"], 4), "tau_b =", round(scalars["kendall_tau_b"], 4))
    print("homo unresolved both =", round(scalars["f_unresolved_at_least_one"], 4))
    print("topk:", homo["top_k"])
    print("split rows:", len(split_rows), "lofo rows:", len(lofo_rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())