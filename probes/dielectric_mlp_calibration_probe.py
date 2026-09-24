"""G3: MLP calibration probe -- fits intercept+slope within each training fold.

Pre-registered: this is a diagnostic probe, not a model selection step.
v1.0 frozen model is NOT changed regardless of outcome.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from sklearn.linear_model import LinearRegression
from sklearn.model_selection import RepeatedKFold
from sklearn.neural_network import MLPRegressor
from sklearn.preprocessing import StandardScaler

from electrolyte_ml.exporting import canonical_text_sha256
from probes.dielectric_representation_ablation import (
    N_REPEATS,
    N_SPLITS,
    PREDICTION_COLUMNS,
    REPEAT_COLUMNS,
    SEED,
    evaluate_repeat,
    physical_feature_matrix,
    read_modelling_rows,
    write_csv_rows,
)

REPRESENTATIONS = ("MLP_Physical",)
XGBOOST_R2 = 0.32009889379719636
XGBOOST_SPEARMAN = 0.8299874869382549


def log_dielectric(values):
    values = np.asarray(values, dtype=np.float64)
    if np.any(values < 1.0):
        raise ValueError("dielectric values must be >= 1")
    return np.log(values - 1.0)


def inverse_log_dielectric(values):
    return np.maximum(np.exp(np.asarray(values, dtype=np.float64)) + 1.0, 1.0)


def _fit_predict_with_calibration(features, target, train_indices, test_indices, *, seed):
    scaler = StandardScaler()
    train_feat = scaler.fit_transform(features[train_indices])
    test_feat = scaler.transform(features[test_indices])

    model = MLPRegressor(
        hidden_layer_sizes=(64,),
        activation="relu",
        solver="adam",
        alpha=1e-4,
        batch_size=32,
        learning_rate_init=1e-3,
        max_iter=2000,
        early_stopping=True,
        validation_fraction=0.2,
        n_iter_no_change=30,
        random_state=seed,
    )
    train_target_log = log_dielectric(target[train_indices])
    model.fit(train_feat, train_target_log)

    raw_train_pred = inverse_log_dielectric(model.predict(train_feat))
    raw_test_pred = inverse_log_dielectric(model.predict(test_feat))
    train_true = target[train_indices]

    cal = LinearRegression(fit_intercept=True)
    cal.fit(raw_train_pred.reshape(-1, 1), train_true)
    slope = float(cal.coef_[0])
    intercept = float(cal.intercept_)

    calibrated_test = cal.predict(raw_test_pred.reshape(-1, 1))
    return calibrated_test, slope, intercept


def _summarize(rows):
    grouped = defaultdict(list)
    for row in rows:
        grouped[str(row["representation"])].append(row)
    metric_names = (
        "mae", "rmse", "r2", "spearman",
        "auc_gt15", "auc_gt30",
        "mae_lt20", "mae_20_60", "mae_gt60",
    )
    result = {}
    for representation in REPRESENTATIONS:
        result[representation] = {}
        for metric in metric_names:
            values = np.asarray([float(row[metric]) for row in grouped[representation]], dtype=np.float64)
            finite = values[np.isfinite(values)]
            result[representation][metric] = {
                "mean": float(np.mean(finite)) if finite.size else None,
                "std": float(np.std(finite, ddof=1)) if finite.size > 1 else 0.0,
                "n": int(finite.size),
            }
    return result


def _write_plot(cal_summary, raw_summary, calibration_params, path):
    fig, axes = plt.subplots(1, 3, figsize=(14, 4.2))
    color = "#2563eb"
    
    name = "MLP_Physical"
    r2_raw = [float(raw_summary[name]["r2"]["mean"])]
    r2_cal = [float(cal_summary[name]["r2"]["mean"])]
    sp_raw = [float(raw_summary[name]["spearman"]["mean"])]
    sp_cal = [float(cal_summary[name]["spearman"]["mean"])]
    x = np.arange(1)
    width = 0.35

    ax = axes[0]
    ax.bar(x - width/2, r2_raw, width, label="Raw", color="#94a3b8")
    ax.bar(x + width/2, r2_cal, width, label="Calibrated", color=color)
    ax.axhline(y=0, color="gray", ls="--", lw=0.5)
    ax.set_xticks(x)
    ax.set_xticklabels([name], rotation=15)
    ax.set_title("R2: raw vs calibrated")
    ax.legend(fontsize=8)
    ax.grid(axis="y", alpha=0.25)

    ax = axes[1]
    ax.bar(x - width/2, sp_raw, width, label="Raw", color="#94a3b8")
    ax.bar(x + width/2, sp_cal, width, label="Calibrated", color=color)
    ax.set_xticks(x)
    ax.set_xticklabels([name], rotation=15)
    ax.set_title("Spearman: raw vs calibrated")
    ax.legend(fontsize=8)
    ax.grid(axis="y", alpha=0.25)

    ax = axes[2]
    slopes = [p["slope"] for p in calibration_params]
    ax.hist(slopes, bins=15, color=color, edgecolor="white", alpha=0.8)
    ax.axvline(x=1.0, color="gray", ls="--", lw=0.8, label="slope=1")
    ax.set_xlabel("Calibration slope")
    ax.set_ylabel("Count")
    ax.set_title("Slope distribution")
    ax.legend(fontsize=8)
    ax.grid(axis="y", alpha=0.25)

    fig.suptitle("MLP Calibration Probe (pre-registered)")
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=180)
    plt.close(fig)


def run(input_path, repeat_path, predictions_path, summary_path, plot_path):
    rows, failed, withheld = read_modelling_rows(input_path)
    target = np.asarray([float(row["dielectric"]) for row in rows], dtype=np.float64)
    physical = physical_feature_matrix(rows)
    features = {"MLP_Physical": physical}

    splitter = RepeatedKFold(n_splits=N_SPLITS, n_repeats=N_REPEATS, random_state=SEED)
    prediction_rows = []
    calib_params = []
    cal_predictions = {}
    raw_predictions = {}
    n = len(rows)

    for rep in range(N_REPEATS * N_SPLITS):
        for r_name in REPRESENTATIONS:
            cal_predictions[(r_name, rep // N_SPLITS)] = np.full(n, np.nan)
            raw_predictions[(r_name, rep // N_SPLITS)] = np.full(n, np.nan)

    for rep, (train_idx, test_idx) in enumerate(splitter.split(np.zeros(n))):
        fold = rep % N_SPLITS
        r_num = rep // N_SPLITS
        r_name = "MLP_Physical"
        
        scaler = StandardScaler()
        train_feat = scaler.fit_transform(features[r_name][train_idx])
        test_feat = scaler.transform(features[r_name][test_idx])

        mlp = MLPRegressor(
            hidden_layer_sizes=(64,), activation="relu", solver="adam",
            alpha=1e-4, batch_size=32, learning_rate_init=1e-3,
            max_iter=2000, early_stopping=True, validation_fraction=0.2,
            n_iter_no_change=30, random_state=SEED + rep,
        )
        mlp.fit(train_feat, log_dielectric(target[train_idx]))
        
        raw_train_pred = inverse_log_dielectric(mlp.predict(train_feat))
        raw_test_pred = inverse_log_dielectric(mlp.predict(test_feat))
        raw_predictions[(r_name, r_num)][test_idx] = raw_test_pred

        cal = LinearRegression(fit_intercept=True)
        cal.fit(raw_train_pred.reshape(-1, 1), target[train_idx])
        slope = float(cal.coef_[0])
        intercept = float(cal.intercept_)
        calib_params.append({"repeat": r_num, "fold": fold, "slope": slope, "intercept": intercept})

        cal_test = cal.predict(raw_test_pred.reshape(-1, 1))
        cal_predictions[(r_name, r_num)][test_idx] = cal_test

        for idx, pred in zip(test_idx, cal_test, strict=True):
            row = rows[int(idx)]
            prediction_rows.append({
                "representation": r_name, "repeat": r_num, "fold": fold,
                "inchikey": row["inchikey"], "name": row["name"], "smiles": row["smiles"],
                "T_K": row["T_K"], "target": f"{target[idx]:.12g}",
                "prediction": f"{pred:.12g}",
                "abs_error": f"{abs(target[idx] - pred):.12g}",
                "target_stratum": "lt20" if target[idx] < 20 else "20_60" if target[idx] <= 60 else "gt60",
            })

    # Calibrated repeat metrics
    cal_repeat_rows = []
    for r_name in REPRESENTATIONS:
        for r in range(N_REPEATS):
            preds = cal_predictions[(r_name, r)]
            if not np.isfinite(preds).all():
                raise ValueError(f"incomplete cal predictions {r_name}/{r}")
            metrics = evaluate_repeat(target, preds)
            cal_repeat_rows.append({"representation": r_name, "repeat": r, **metrics})

    # Raw repeat metrics
    raw_repeat_rows = []
    for r_name in REPRESENTATIONS:
        for r in range(N_REPEATS):
            preds = raw_predictions[(r_name, r)]
            if not np.isfinite(preds).all():
                raise ValueError(f"incomplete raw predictions {r_name}/{r}")
            metrics = evaluate_repeat(target, preds)
            raw_repeat_rows.append({"representation": r_name, "repeat": r, **metrics})

    cal_summary = _summarize(cal_repeat_rows)
    raw_summary = _summarize(raw_repeat_rows)

    merged = {}
    for r_name in REPRESENTATIONS:
        merged[r_name] = {}
        merged[r_name].update(cal_summary[r_name])
        for m in ("mae", "rmse", "r2", "spearman"):
            merged[r_name][f"{m}_before_calibration"] = raw_summary[r_name][m]

    payload = {
        "schema_version": 1,
        "probe_name": "mlp_calibration",
        "input_path": input_path.relative_to(REPOSITORY_ROOT).as_posix(),
        "input_sha256": canonical_text_sha256(input_path),
        "compound_count": len(rows),
        "failed_physical_feature_count": len(failed),
        "withheld_not_model_ready_count": len(withheld),
        "withheld_not_model_ready_names": [row["name"] for row in withheld],
        "representations": list(REPRESENTATIONS),
        "validation": {
            "strategy": "RepeatedKFold",
            "n_splits": N_SPLITS, "n_repeats": N_REPEATS, "random_state": SEED,
        },
        "calibration_params": calib_params,
        "summary": merged,
        "interpretation": (
            "If calibrated R2 > 0, MLP is a near-perfect ranker with correctable scale offset. "
            "If calibrated R2 <= 0, the negative R2 is not solely a calibration issue."
        ),
        "outputs": {
            "repeat_csv": repeat_path.relative_to(REPOSITORY_ROOT).as_posix(),
            "predictions_csv": predictions_path.relative_to(REPOSITORY_ROOT).as_posix(),
            "summary_json": summary_path.relative_to(REPOSITORY_ROOT).as_posix(),
            "plot": plot_path.relative_to(REPOSITORY_ROOT).as_posix(),
        },
    }

    write_csv_rows(repeat_path, REPEAT_COLUMNS, cal_repeat_rows)
    write_csv_rows(predictions_path, PREDICTION_COLUMNS, prediction_rows)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _write_plot(cal_summary, raw_summary, calib_params, plot_path)
    return payload


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=REPOSITORY_ROOT / "data" / "processed" / "dielectric_physical_features.csv")
    parser.add_argument("--repeat-output", type=Path, default=REPOSITORY_ROOT / "data" / "processed" / "dielectric_mlp_calibration_repeats.csv")
    parser.add_argument("--predictions-output", type=Path, default=REPOSITORY_ROOT / "data" / "processed" / "dielectric_mlp_calibration_predictions.csv")
    parser.add_argument("--summary-output", type=Path, default=REPOSITORY_ROOT / "probes" / "dielectric_mlp_calibration_summary.json")
    parser.add_argument("--plot", type=Path, default=REPOSITORY_ROOT / "probes" / "artifacts" / "dielectric_mlp_calibration.png")
    args = parser.parse_args()
    
    payload = run(
        input_path=args.input, repeat_path=args.repeat_output,
        predictions_path=args.predictions_output,
        summary_path=args.summary_output, plot_path=args.plot,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
