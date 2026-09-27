"""Week 19 D5: the eta channel under a second model family (Chemprop D-MPNN vs the incumbent XGB).

The incumbent viscosity model (probes/viscosity_baseline.py, MorganTemperatureXGBoost) reads
MAE 0.15686276760094522 on the row-level pool under the group-key split, against a gate of 0.15
on log10(cP).  Week 19 asks whether that gap is a representation ceiling or a data bottleneck:
retrain a Chemprop D-MPNN on the same pool, under the same split, and compare.

Every rule is imported and never re-implemented:

* the pools come from probes/viscosity_row_level_unfreeze.py::build_pools;
* the split comes from probes/viscosity_baseline.py::_group_key_split;
* the target and the metric are the frozen log10(cP) MAE.

The run is void unless the recomputed (train_id_hash, test_id_hash) equal the incumbent hashes
bit-for-bit, so a silent split drift cannot be reported as a model difference.

Nothing here reads or writes the frozen epsilon numbers 0.4091179943351143 /
0.4766400383507876, nothing here uses Reaxys values, and nothing here is promoted: the shot
produces one channel reading only.
"""

from __future__ import annotations

import argparse
import csv
import json
import platform
import sys
import time
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))
sys.path.insert(0, str(REPOSITORY_ROOT / "probes"))

import numpy as np
import viscosity_baseline as frozen
import viscosity_row_level_unfreeze as unfreeze

from electrolyte_ml.exporting import canonical_text_sha256

TASK_ID = "week19_w19d5_chemprop_viscosity_crosscheck"

PREREG_PATH = REPOSITORY_ROOT / "probes" / "w19_chemprop_viscosity_prereg.json"
SUMMARY_PATH = REPOSITORY_ROOT / "probes" / "w19_chemprop_viscosity_summary.json"
ARTIFACTS_DIR = REPOSITORY_ROOT / "probes" / "artifacts"
REPEATS_PATH = ARTIFACTS_DIR / "w19_chemprop_viscosity_repeats.csv"
FIGURE_PATH = ARTIFACTS_DIR / "w19_chemprop_viscosity.png"
REPORT_PATH = REPOSITORY_ROOT / "reports" / "w19_chemprop_viscosity.md"

POOL_PRIMARY = "row_level"
POOL_SECONDARY = "family_level"
POOL_ORDER: tuple[str, ...] = (POOL_PRIMARY, POOL_SECONDARY)

ENSEMBLE_SEEDS: tuple[int, ...] = (42, 1234, 2026)
EPOCHS = 60
BATCH_SIZE = 64
MESSAGE_HIDDEN_DIM = 300
MESSAGE_DEPTH = 3
FFN_HIDDEN_DIM = 300
FFN_NUM_LAYERS = 1
GRADIENT_CLIP = 5.0

MAE_GATE = 0.15
TOLERANCE = 0.02
INCUMBENT_REPRODUCTION_TOLERANCE = 1e-9

INCUMBENT_MODEL = "MorganTemperatureXGBoost"
INCUMBENT_TRAIN_ID_HASH: Mapping[str, str] = {
    POOL_PRIMARY: "48b17e76c1edcdce0369d8118ad21ea0beb1b472ec744cee3c579c02fa6e3111",
    POOL_SECONDARY: "e9a63ff49a3f54380ad1241be8db156c8bd7f4c3c9c0308859f8dcaa121c9506",
}
INCUMBENT_TEST_ID_HASH: Mapping[str, str] = {
    POOL_PRIMARY: "2dedfc6ae3ac3dae98e7404556535030d5d3fd000b8119c25d230db791507119",
    POOL_SECONDARY: "dfea9aa151cd5b0f86eede1d6929b8fe5a1e0ab34926a851e90d3f7de6d4d63f",
}
INCUMBENT_MAE: Mapping[str, float] = {
    POOL_PRIMARY: 0.15686276760094522,
    POOL_SECONDARY: 0.17477197208762,
}
INCUMBENT_R2: Mapping[str, float] = {
    POOL_PRIMARY: 0.752682215223955,
    POOL_SECONDARY: 0.7481271437772365,
}
INCUMBENT_TEST_ROWS: Mapping[str, int] = {POOL_PRIMARY: 838, POOL_SECONDARY: 708}

EXTRA_DESCRIPTOR_NAMES = ("T_K", "1000_over_T_K")

def utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_pool_frame(
    pools: Mapping[str, list[dict[str, object]]],
    census: Mapping[str, object],
    pool_name: str,
) -> dict[str, Any]:
    """The frozen pool rows in table order, with the target and the extra descriptors."""

    rows = pools[pool_name]
    temperatures = np.asarray([float(row["T_K"]) for row in rows], dtype=float)
    viscosity_pa_s = np.asarray(
        [float(row["viscosity_Pa_s"]) for row in rows], dtype=float
    )
    keys = [str(row["inchikey"]) for row in rows]
    return {
        "pool": pool_name,
        "rows": len(rows),
        "keys": len(set(keys)),
        "smiles": [str(row["smiles"]) for row in rows],
        "keys_list": keys,
        "temperatures": temperatures,
        "target": np.log10(viscosity_pa_s * 1000.0),
        "descriptors": np.column_stack([temperatures, 1000.0 / temperatures]),
        "census": dict(census),
    }


def regression_metrics(target: np.ndarray, prediction: np.ndarray) -> dict[str, float]:
    """MAE / RMSE / R2 in log10(cP), on the rows handed in."""

    residual = prediction - target
    denominator = float(np.sum((target - float(target.mean())) ** 2))
    r2 = float("nan") if denominator <= 0.0 else float(1.0 - np.sum(residual**2) / denominator)
    return {
        "mae_log10_cP": float(np.mean(np.abs(residual))),
        "rmse_log10_cP": float(np.sqrt(np.mean(residual**2))),
        "r2_log10_cP": r2,
    }


def predict_chemprop_member(
    frame: Mapping[str, Any],
    train_indices: np.ndarray,
    test_indices: np.ndarray,
    seed: int,
    epochs: int,
) -> tuple[np.ndarray, float]:
    """One D-MPNN member: a fixed epoch budget, no validation fold, no early stopping.

    The extra temperature descriptors are standardized on the TRAIN rows only, so no test
    statistic reaches the fit.
    """

    import torch
    from chemprop.data import MoleculeDatapoint, MoleculeDataset, build_dataloader
    from chemprop.models import MPNN
    from chemprop.nn import MAE, BondMessagePassing, NormAggregation, RegressionFFN
    from lightning.pytorch import Trainer

    torch.manual_seed(seed)

    descriptors = np.asarray(frame["descriptors"], dtype=float)
    centre = descriptors[train_indices].mean(axis=0)
    spread = descriptors[train_indices].std(axis=0)
    spread = np.where(spread == 0.0, 1.0, spread)
    scaled = (descriptors - centre) / spread

    target = np.asarray(frame["target"], dtype=float)
    datapoints = [
        MoleculeDatapoint.from_smi(
            str(smiles),
            y=np.asarray([float(value)], dtype=float),
            x_d=np.asarray(scaled[index], dtype=float),
        )
        for index, (smiles, value) in enumerate(zip(frame["smiles"], target))
    ]
    train_dataset = MoleculeDataset([datapoints[int(index)] for index in train_indices])
    test_dataset = MoleculeDataset([datapoints[int(index)] for index in test_indices])
    train_loader = build_dataloader(
        train_dataset, batch_size=BATCH_SIZE, shuffle=True, seed=seed
    )
    test_loader = build_dataloader(test_dataset, batch_size=BATCH_SIZE, shuffle=False)

    message_passing = BondMessagePassing(d_h=MESSAGE_HIDDEN_DIM, depth=MESSAGE_DEPTH)
    predictor = RegressionFFN(
        n_tasks=1,
        input_dim=message_passing.output_dim + len(EXTRA_DESCRIPTOR_NAMES),
        hidden_dim=FFN_HIDDEN_DIM,
        n_layers=FFN_NUM_LAYERS,
    )
    model = MPNN(
        message_passing,
        NormAggregation(),
        predictor,
        batch_norm=False,
        metrics=[MAE()],
        warmup_epochs=2,
        init_lr=1e-4,
        max_lr=1e-3,
        final_lr=1e-4,
    )
    trainer = Trainer(
        max_epochs=epochs,
        enable_checkpointing=False,
        enable_progress_bar=False,
        enable_model_summary=False,
        logger=False,
        gradient_clip_val=GRADIENT_CLIP,
        accelerator="cpu",
        devices=1,
    )
    started = time.perf_counter()
    trainer.fit(model, train_dataloaders=train_loader)
    elapsed = time.perf_counter() - started

    model.eval()
    chunks: list[np.ndarray] = []
    with torch.no_grad():
        for batch in test_loader:
            output = model(batch.bmg, batch.V_d, batch.X_d)
            chunks.append(output.detach().cpu().numpy().reshape(-1))
    return np.concatenate(chunks), float(elapsed)

def evaluate_pool(
    frame: Mapping[str, Any],
    seeds: Sequence[int],
    epochs: int,
    reproduce_incumbent: bool,
) -> dict[str, Any]:
    """The grouped split, the identity gate, the incumbent reproduction, then the members."""

    pool = str(frame["pool"])
    keys = [str(key) for key in frame["keys_list"]]
    train_indices, test_indices = frozen._group_key_split(keys)
    train_hash = frozen._split_hash(keys, train_indices)
    test_hash = frozen._split_hash(keys, test_indices)
    split_verified = bool(
        train_hash == INCUMBENT_TRAIN_ID_HASH[pool]
        and test_hash == INCUMBENT_TEST_ID_HASH[pool]
    )
    if not split_verified:
        raise RuntimeError(
            "the recomputed grouped split does not reproduce the incumbent hashes: run void"
        )

    target = np.asarray(frame["target"], dtype=float)
    train_keys = {keys[int(index)] for index in train_indices}
    test_keys = {keys[int(index)] for index in test_indices}

    reproduction: dict[str, object] | None = None
    if reproduce_incumbent:
        features, _names = frozen.build_feature_matrix(
            [str(smile) for smile in frame["smiles"]],
            [float(value) for value in frame["temperatures"]],
        )
        incumbent_prediction = frozen._fit_predict(
            INCUMBENT_MODEL, features, target, train_indices, test_indices
        )
        observed_mae = float(np.mean(np.abs(target[test_indices] - incumbent_prediction)))
        reproduction = {
            "model": INCUMBENT_MODEL,
            "mae_log10_cP": observed_mae,
            "frozen_mae_log10_cP": INCUMBENT_MAE[pool],
            "abs_gap": abs(observed_mae - INCUMBENT_MAE[pool]),
            "matches_frozen": bool(
                abs(observed_mae - INCUMBENT_MAE[pool]) <= INCUMBENT_REPRODUCTION_TOLERANCE
            ),
        }

    members: list[dict[str, object]] = []
    member_predictions: list[np.ndarray] = []
    for seed in seeds:
        prediction, elapsed = predict_chemprop_member(
            frame, train_indices, test_indices, int(seed), int(epochs)
        )
        member_predictions.append(prediction)
        member = {"seed": int(seed), "epochs": int(epochs), "fit_seconds": elapsed}
        member.update(regression_metrics(target[test_indices], prediction))
        members.append(member)
    ensemble = np.mean(np.asarray(member_predictions), axis=0)
    ensemble_metrics = regression_metrics(target[test_indices], ensemble)
    delta = float(ensemble_metrics["mae_log10_cP"] - INCUMBENT_MAE[pool])
    if delta <= -TOLERANCE:
        verdict = "chemprop_better"
    elif delta >= TOLERANCE:
        verdict = "incumbent_confirmed"
    else:
        verdict = "consistency_confirmed"

    return {
        "pool": pool,
        "rows": int(frame["rows"]),
        "keys": int(frame["keys"]),
        "train_rows": len(train_indices),
        "test_rows": len(test_indices),
        "train_keys": len(train_keys),
        "test_keys": len(test_keys),
        "group_overlap_keys": len(train_keys & test_keys),
        "split_verified_against_incumbent": split_verified,
        "train_id_hash": train_hash,
        "test_id_hash": test_hash,
        "incumbent": {
            "model": INCUMBENT_MODEL,
            "mae_log10_cP": INCUMBENT_MAE[pool],
            "r2_log10_cP": INCUMBENT_R2[pool],
            "reference": "probes/viscosity_row_level_summary.json",
        },
        "incumbent_reproduction": reproduction,
        "chemprop": {
            "members": members,
            "ensemble_mae_log10_cP": ensemble_metrics["mae_log10_cP"],
            "ensemble_rmse_log10_cP": ensemble_metrics["rmse_log10_cP"],
            "ensemble_r2_log10_cP": ensemble_metrics["r2_log10_cP"],
        },
        "delta_mae_log10_cP": delta,
        "gate_0_15_passed_by_chemprop": bool(
            ensemble_metrics["mae_log10_cP"] < MAE_GATE
        ),
        "gate_0_15_passed_by_incumbent": bool(INCUMBENT_MAE[pool] < MAE_GATE),
        "verdict": verdict,
        "_test_prediction": ensemble,
        "_test_target": target[test_indices],
    }

def build_summary(
    *,
    prereg_sha256: str,
    pool_results: Mapping[str, dict[str, Any]],
    config: Mapping[str, object],
    telemetry: Mapping[str, object],
) -> dict[str, Any]:
    """The summary carries the readings only; the prediction arrays stay out of the JSON."""

    clean: dict[str, Any] = {}
    for name, record in pool_results.items():
        clean[name] = {key: value for key, value in record.items() if not key.startswith("_")}
    primary = clean[POOL_PRIMARY]
    return {
        "schema_version": 1,
        "task_id": TASK_ID,
        "generated_at_utc": utc_now(),
        "preregistration": {
            "path": "probes/w19_chemprop_viscosity_prereg.json",
            "sha256": prereg_sha256,
            "status": "locked_before_run",
        },
        "plan_reference": "Week19 plan section W19-3",
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "chemprop": _package_version("chemprop"),
            "torch": _package_version("torch"),
            "lightning": _package_version("lightning"),
            "numpy": _package_version("numpy"),
        },
        "registered_config": dict(config),
        "pools": clean,
        "verdict": primary["verdict"],
        "delta_mae_log10_cP": primary["delta_mae_log10_cP"],
        "gate_log10_cP": MAE_GATE,
        "tolerance": TOLERANCE,
        "promoted": False,
        "main_scoreboard_attempts_added": 0,
        "uses_no_reaxys_numbers": True,
        "telemetry": dict(telemetry),
        "honest_boundaries": HONEST_BOUNDARIES,
        "outputs": {
            "summary": "probes/w19_chemprop_viscosity_summary.json",
            "repeats": "probes/artifacts/w19_chemprop_viscosity_repeats.csv",
            "report": "reports/w19_chemprop_viscosity.md",
            "figure": "probes/artifacts/w19_chemprop_viscosity.png",
        },
    }


def _package_version(name: str) -> str:
    try:
        module = __import__(name)
    except ImportError:  # pragma: no cover - the environment probe records the absence
        return "absent"
    return str(getattr(module, "__version__", "unknown"))

HONEST_BOUNDARIES: tuple[str, ...] = (
    (
        "The eta channel is a separate channel from epsilon: its row and compound counts "
        "are never mixed with 457 / 97 / 276 / 2029."
    ),
    (
        "The grouped split here is GroupShuffleSplit(test_size=0.2, seed=42), not the "
        "50-fold GroupKFold used by the epsilon scoreboard; it is the incumbent viscosity "
        "split, reproduced bit-for-bit and asserted before any member is fitted."
    ),
    (
        "The Chemprop members use a fixed epoch budget and no validation fold, so no "
        "test-fold information can select a hyperparameter or a checkpoint."
    ),
    "The timing probe is not a reading; only the registered epoch budget is a reading.",
    (
        "The incumbent is a frozen single-configuration, single-seed XGBoost while the "
        "Chemprop arm is a three-seed ensemble, so part of the gap can be ensembling or "
        "re-tuning rather than representation. The W18 hyperparameter arm moved the "
        "incumbent model family by only 0.01370607964226378 on the epsilon channel, so "
        "pure tuning is an unlikely explanation for a delta of this size, but the "
        "confound is not removable from this design."
    ),
    (
        "The grouped protocol here is a single 20 percent hold-out draw, so there is no "
        "fold-level variance. The three Chemprop seeds probe initialization variance "
        "only, not split variance."
    ),
    (
        "The Chemprop configuration was registered before the run and was never "
        "searched: this is an untuned neural arm against a frozen fingerprint arm, not "
        "the best that either family can do."
    ),
    (
        "A verdict of chemprop_better opens a follow-up lane. It does not by itself "
        "promote the eta channel, and it moves no epsilon number."
    ),
)


VERDICT_NOTES: dict[str, str] = {
    "consistency_confirmed": (
        "The delta sits inside the band, so the two model families agree on this "
        "channel and the gap to the gate is not a representation artifact. Agreement is "
        "not evidence that either model has crossed the gate."
    ),
    "chemprop_better": (
        "The learned graph representation wins by more than the tolerance, so under "
        "this registered protocol the representation layer was the ceiling on this "
        "channel. That is the trigger for a follow-up lane, not a promotion."
    ),
    "incumbent_confirmed": (
        "The frozen fingerprint model wins by more than the tolerance, so the "
        "bottleneck sits in the data and the density pairing rather than in the "
        "representation layer."
    ),
}


def format_report(summary: Mapping[str, Any]) -> list[str]:
    """The markdown report, written from the summary and nothing else."""

    delta = float(summary["delta_mae_log10_cP"])
    lines: list[str] = [
        "# W19-D5: the eta channel under a second model family (Chemprop D-MPNN)",
        "",
        "Task `" + str(summary["task_id"]) + "`, generated " + str(summary["generated_at_utc"]),
        "",
        "## 0. A correction registered before the run",
        "",
        (
            "The W19 plan said the kinematic residue was 214 rows still frozen and that "
            "this shot would use only thawed rows. Both halves of that sentence are wrong: "
            "214 is a family-level exclusion count, the row-level residue is 86 rows, and "
            "`reports/decisions_log.md` 28.38 already unfroze those rows and judged the arm "
            "refuted. This probe reuses the unfrozen pools as they stand and re-thaws "
            "nothing."
        ),
        "",
        "## 1. What was compared",
        "",
        "| item | incumbent | this shot |",
        "| --- | --- | --- |",
        (
            "| model | Morgan count 2048 plus a temperature block, XGBoost | Chemprop "
            "D-MPNN, learned graph representation |"
        ),
        "| extra inputs | T_K, 1000/T_K | T_K, 1000/T_K, the same two, standardized |",
        "| split | GroupShuffleSplit by InChIKey, seed 42 | identical, hashes asserted |",
        "| target | log10(cP) | log10(cP) |",
        "| gate | 0.15 | 0.15, reported rather than used as the criterion |",
        "",
        "## 2. Readings, grouped split only",
        "",
        "| pool | rows | keys | test rows | incumbent MAE | Chemprop MAE | delta | verdict |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for name in POOL_ORDER:
        record = summary["pools"].get(name)
        if not record:
            continue
        cells = [
            name,
            str(record["rows"]),
            str(record["keys"]),
            str(record["test_rows"]),
            str(record["incumbent"]["mae_log10_cP"]),
            str(record["chemprop"]["ensemble_mae_log10_cP"]),
            str(record["delta_mae_log10_cP"]),
            str(record["verdict"]),
        ]
        lines.append("| " + " | ".join(cells) + " |")
    lines.extend([
        "",
        (
            "Every pool reports `split_verified_against_incumbent = true`, so both models "
            "see the same train rows and the same test rows."
        ),
        "",
        "## 3. Verdict",
        "",
        "Primary pool `" + POOL_PRIMARY + "`: delta = " + repr(delta) + " log10(cP) against "
        "the registered tolerance of +/-" + repr(TOLERANCE) + " -> **"
        + str(summary["verdict"]) + "**.",
        "",
        VERDICT_NOTES.get(str(summary["verdict"]), ""),
        "",
        "Gate context on the primary pool: the Chemprop ensemble reads "
        + str(summary["pools"][POOL_PRIMARY]["chemprop"]["ensemble_mae_log10_cP"])
        + " and the incumbent reads "
        + str(summary["pools"][POOL_PRIMARY]["incumbent"]["mae_log10_cP"])
        + " against the registered gate of " + repr(MAE_GATE) + ".",
        "",
        "## 4. Boundaries",
        "",
    ])
    for boundary in summary["honest_boundaries"]:
        lines.append("- " + " ".join(str(boundary).split()))
    lines.append("")
    lines.append("Nothing here is promoted and no main-scoreboard attempt is spent.")
    return lines

def write_repeats_csv(path: Path, pool_results: Mapping[str, dict[str, Any]]) -> None:
    """One row per (pool, member), plus one ensemble row per pool."""

    fieldnames = [
        "pool", "member", "seed", "epochs", "train_rows", "test_rows",
        "mae_log10_cP", "rmse_log10_cP", "r2_log10_cP", "fit_seconds",
        "delta_vs_incumbent", "verdict",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for name, record in pool_results.items():
            incumbent_mae = float(record["incumbent"]["mae_log10_cP"])
            for member in record["chemprop"]["members"]:
                writer.writerow({
                    "pool": name,
                    "member": "seed-" + str(member["seed"]),
                    "seed": member["seed"],
                    "epochs": member["epochs"],
                    "train_rows": record["train_rows"],
                    "test_rows": record["test_rows"],
                    "mae_log10_cP": member["mae_log10_cP"],
                    "rmse_log10_cP": member["rmse_log10_cP"],
                    "r2_log10_cP": member["r2_log10_cP"],
                    "fit_seconds": round(float(member["fit_seconds"]), 3),
                    "delta_vs_incumbent": member["mae_log10_cP"] - incumbent_mae,
                    "verdict": record["verdict"],
                })
            ensemble = record["chemprop"]
            writer.writerow({
                "pool": name,
                "member": "ensemble",
                "seed": 0,
                "epochs": record["chemprop"]["members"][0]["epochs"],
                "train_rows": record["train_rows"],
                "test_rows": record["test_rows"],
                "mae_log10_cP": ensemble["ensemble_mae_log10_cP"],
                "rmse_log10_cP": ensemble["ensemble_rmse_log10_cP"],
                "r2_log10_cP": ensemble["ensemble_r2_log10_cP"],
                "fit_seconds": "",
                "delta_vs_incumbent": record["delta_mae_log10_cP"],
                "verdict": record["verdict"],
            })


def write_figure(path: Path, pool_results: Mapping[str, dict[str, Any]]) -> bool:
    """Predicted vs observed on the grouped test fold, plus the MAE comparison."""

    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return False

    primary = pool_results[POOL_PRIMARY]
    figure, axes = plt.subplots(1, 2, figsize=(11.5, 4.8))
    observed = np.asarray(primary["_test_target"], dtype=float)
    predicted = np.asarray(primary["_test_prediction"], dtype=float)
    low = float(min(observed.min(), predicted.min())) - 0.2
    high = float(max(observed.max(), predicted.max())) + 0.2
    axes[0].scatter(observed, predicted, s=8, alpha=0.55, color="#2b6cb0")
    axes[0].plot([low, high], [low, high], "--", color="#c53030", linewidth=1.0)
    axes[0].set_xlim(low, high)
    axes[0].set_ylim(low, high)
    axes[0].set_xlabel("observed log10(viscosity / cP)")
    axes[0].set_ylabel("Chemprop ensemble prediction")
    axes[0].set_title(
        "row-level pool, grouped test fold\nMAE "
        + format(float(primary["chemprop"]["ensemble_mae_log10_cP"]), ".4f")
        + " vs incumbent "
        + format(float(primary["incumbent"]["mae_log10_cP"]), ".4f"),
        fontsize=9,
    )

    names = [name for name in POOL_ORDER if name in pool_results]
    positions = np.arange(len(names))
    width = 0.36
    incumbent_maes = [float(pool_results[name]["incumbent"]["mae_log10_cP"]) for name in names]
    chemprop_maes = [
        float(pool_results[name]["chemprop"]["ensemble_mae_log10_cP"]) for name in names
    ]
    axes[1].bar(positions - width / 2, incumbent_maes, width, label="incumbent XGB", color="#718096")
    axes[1].bar(positions + width / 2, chemprop_maes, width, label="Chemprop D-MPNN", color="#2b6cb0")
    axes[1].axhline(MAE_GATE, color="#c53030", linestyle="--", linewidth=1.0)
    axes[1].text(
        0.02, MAE_GATE + 0.002, "gate 0.15", color="#c53030", fontsize=8, transform=axes[1].get_yaxis_transform()
    )
    axes[1].set_xticks(positions)
    axes[1].set_xticklabels(names, fontsize=9)
    axes[1].set_ylabel("MAE on log10(cP)")
    axes[1].set_title("grouped split only", fontsize=9)
    axes[1].legend(fontsize=8)

    figure.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=160)
    plt.close(figure)
    return True

def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="W19-D5 Chemprop viscosity cross-check")
    parser.add_argument("--jobs", type=int, default=2, help="torch intra-op threads (max 2)")
    parser.add_argument("--epochs", type=int, default=EPOCHS)
    parser.add_argument("--seeds", type=int, nargs="+", default=list(ENSEMBLE_SEEDS))
    parser.add_argument("--pools", nargs="+", default=list(POOL_ORDER))
    parser.add_argument("--smoke", action="store_true", help="5 epochs, one seed, no writes")
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="rebuild the report and re-stamp the summary from the stored readings",
    )
    parser.add_argument("--no-incumbent-reproduction", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args(argv)


def _write_text(path: Path, text: str) -> None:
    """LF-only, UTF-8, no BOM: the repository hygiene test pins all three."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def regenerate_report() -> int:
    """Rebuild the report from the stored readings, without re-fitting anything."""

    summary = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
    summary["honest_boundaries"] = list(HONEST_BOUNDARIES)
    summary["boundary_revision"] = (
        "boundaries and the verdict paragraph were regenerated from the stored readings; "
        "no model was re-fitted and no number moved"
    )
    _write_text(REPORT_PATH, "\n".join(format_report(summary)) + "\n")
    summary["artifacts"]["w19_chemprop_viscosity.md"] = canonical_text_sha256(REPORT_PATH)
    _write_text(SUMMARY_PATH, json.dumps(summary, indent=2) + "\n")
    print("regenerated " + str(REPORT_PATH), flush=True)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)

    if args.report_only:
        return regenerate_report()

    import torch

    threads = max(1, int(args.jobs))
    torch.set_num_threads(threads)

    seeds: tuple[int, ...] = (
        (ENSEMBLE_SEEDS[0],) if args.smoke else tuple(int(value) for value in args.seeds)
    )
    epochs = 5 if args.smoke else int(args.epochs)
    pool_names = (POOL_PRIMARY,) if args.smoke else tuple(str(name) for name in args.pools)
    reproduce = not args.smoke and not args.no_incumbent_reproduction

    if not args.smoke and SUMMARY_PATH.exists() and not args.overwrite:
        raise SystemExit("summary already exists; pass --overwrite to replace it")

    pools, census = unfreeze.build_pools()
    started = time.perf_counter()
    results: dict[str, dict[str, Any]] = {}
    for name in pool_names:
        frame = build_pool_frame(pools, census, name)
        results[name] = evaluate_pool(frame, seeds, epochs, reproduce)
        record = results[name]
        print(
            "pool " + name
            + " | rows " + str(record["rows"])
            + " | chemprop MAE " + repr(record["chemprop"]["ensemble_mae_log10_cP"])
            + " | incumbent " + repr(record["incumbent"]["mae_log10_cP"])
            + " | delta " + repr(record["delta_mae_log10_cP"])
            + " | " + str(record["verdict"]),
            flush=True,
        )
    elapsed = time.perf_counter() - started

    if args.smoke:
        print(
            "smoke elapsed_s " + repr(round(elapsed, 1)) + " for " + str(len(seeds))
            + " member(s) at " + str(epochs) + " epochs",
            flush=True,
        )
        return 0

    prereg_sha256 = canonical_text_sha256(PREREG_PATH)
    config = {
        "pools_run": list(pool_names),
        "ensemble_seeds": [int(value) for value in seeds],
        "epochs": int(epochs),
        "batch_size": BATCH_SIZE,
        "message_hidden_dim": MESSAGE_HIDDEN_DIM,
        "message_depth": MESSAGE_DEPTH,
        "ffn_hidden_dim": FFN_HIDDEN_DIM,
        "ffn_num_layers": FFN_NUM_LAYERS,
        "gradient_clip": GRADIENT_CLIP,
        "extra_descriptors": list(EXTRA_DESCRIPTOR_NAMES),
        "descriptor_scaling": "StandardScaler fitted on train rows only",
        "validation_fold": "none (fixed epoch budget)",
        "torch_threads": threads,
    }
    telemetry = {
        "total_seconds": elapsed,
        "fit_seconds_by_pool_member": {
            name: [round(float(row["fit_seconds"]), 3) for row in record["chemprop"]["members"]]
            for name, record in results.items()
        },
    }
    summary = build_summary(
        prereg_sha256=prereg_sha256,
        pool_results=results,
        config=config,
        telemetry=telemetry,
    )
    summary["figure_written"] = write_figure(FIGURE_PATH, results)
    write_repeats_csv(REPEATS_PATH, results)
    summary["artifacts"] = {
        "w19_chemprop_viscosity_repeats.csv": canonical_text_sha256(REPEATS_PATH),
    }
    _write_text(REPORT_PATH, "\n".join(format_report(summary)) + "\n")
    summary["artifacts"]["w19_chemprop_viscosity.md"] = canonical_text_sha256(REPORT_PATH)
    _write_text(SUMMARY_PATH, json.dumps(summary, indent=2) + "\n")
    print("wrote " + str(SUMMARY_PATH), flush=True)
    print(
        "verdict " + str(summary["verdict"]) + " delta " + repr(summary["delta_mae_log10_cP"]),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
