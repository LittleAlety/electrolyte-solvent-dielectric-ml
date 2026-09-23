"""P4 redox probes for the RX-392 and Batt-P30K datasets."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path

import h5py
import matplotlib.pyplot as plt
import numpy as np
from rdkit import Chem, RDLogger
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import RBF, ConstantKernel, WhiteKernel
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.preprocessing import StandardScaler

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from electrolyte_ml.exporting import canonical_text_sha256
from electrolyte_ml.standardize import standardize_molecule
from probes.dielectric_gpr_baseline import deterministic_split

RX_SOURCE_COMMIT = "a5101e30c6975552d97e34f1e93461126715c862"
RX_SOURCE_URL = (
    "https://raw.githubusercontent.com/Teoroo-CMC/Batt-SLM/"
    f"{RX_SOURCE_COMMIT}/Redox-Pot/Redox-Ener/RX-392.csv"
)
RX_UPSTREAM_SCRIPT_URL = (
    "https://raw.githubusercontent.com/Teoroo-CMC/Batt-SLM/"
    f"{RX_SOURCE_COMMIT}/Redox-Pot/Redox-Ener/redox_free_ener.py"
)
RX_SOURCE_SHA256 = "d30ec1ffccba15538bac0b67157c14e045f1721441be23837c6195eca24a5d87"
RX_SOURCE_SIZE = 248404
BATT_SLM_DOI = "10.1021/acsnano.6c06255"
RX_SOURCE_ROWS = 392
P30K_ROWS = 29519
FP_RADIUS = 2
FP_SIZE = 2048
SPLIT_SEED = 42
TEST_FRACTION = 0.2
GATE_MAE_THRESHOLD = 0.15
TARGETS = ("oxidation_free_energy", "reduction_free_energy")
TARGET_FEATURES = {
    "oxidation_free_energy": "IP",
    "reduction_free_energy": "EA",
}
MODEL_NAMES = ("linear", "scalar_gpr", "fingerprint_gpr")

MERGED_COLUMNS = (
    "row_id",
    "source",
    "inchikey",
    "smiles",
    "name",
    "IP",
    "EA",
    "HOMO",
    "LUMO",
    "dipole",
    "oxidation_free_energy",
    "reduction_free_energy",
    "source_doi",
    "method",
    "status",
)
PREDICTION_COLUMNS = (
    "row_id",
    "target_name",
    "model",
    "source",
    "inchikey",
    "smiles",
    "split",
    "used_for_metrics",
    "target",
    "prediction",
    "std",
    "abs_error",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _select_dielectric_18(value: str, field: str) -> float:
    matches: list[float] = []
    for item in value.split("&"):
        if ":" not in item:
            continue
        key, raw_value = item.rsplit(":", 1)
        if "DIELECTRIC=18" in key:
            matches.append(float(raw_value))
    if len(matches) != 1:
        raise ValueError(
            f"expected exactly one DIELECTRIC=18 value for {field}, got {len(matches)}"
        )
    return matches[0]


def _inchi_to_identity(inchi: str) -> tuple[str, str]:
    molecule = Chem.MolFromInchi(inchi)
    if molecule is None:
        raise ValueError(f"RDKit could not parse InChI: {inchi!r}")
    canonical = Chem.MolToSmiles(molecule, canonical=True, isomericSmiles=True)
    standardized = standardize_molecule(canonical)
    return standardized.smiles, standardized.inchikey


def parse_rx_text(text: str) -> list[dict[str, object]]:
    lines = text.splitlines()
    if not lines:
        raise ValueError("RX-392 text is empty")
    header = lines[0].split("$")
    required = {
        "MolId",
        "Inchi",
        "UniqueLevel",
        "dictIEs",
        "dictEAs",
        "dictOxPots",
        "dictRedPots",
    }
    missing = required - set(header)
    if missing:
        raise ValueError(f"RX-392 header is missing columns: {sorted(missing)}")

    rows: list[dict[str, object]] = []
    for line_number, line in enumerate(lines[1:], start=2):
        if not line.strip():
            continue
        values = dict(zip(header, line.split("$")))
        ip = _select_dielectric_18(values["dictIEs"], "dictIEs")
        raw_ea = _select_dielectric_18(values["dictEAs"], "dictEAs")
        oxidation_potential = _select_dielectric_18(
            values["dictOxPots"],
            "dictOxPots",
        )
        reduction_potential = _select_dielectric_18(
            values["dictRedPots"],
            "dictRedPots",
        )
        smiles, inchikey = _inchi_to_identity(values["Inchi"])
        rows.append(
            {
                "row_id": f"rx392:{values['MolId']}",
                "source": "RX-392",
                "inchikey": inchikey,
                "smiles": smiles,
                "name": values["MolId"],
                "IP": ip,
                "EA": -raw_ea,
                "HOMO": "",
                "LUMO": "",
                "dipole": "",
                "oxidation_free_energy": oxidation_potential + 4.44,
                "reduction_free_energy": -(reduction_potential + 4.44),
                "source_doi": BATT_SLM_DOI,
                "method": (
                    "wB97X-V/def2-TZVPPD/SMD(DIELECTRIC=18.5); "
                    "redox_free_ener.py free-energy convention"
                ),
                "status": "source_native_dft",
                "_line_number": line_number,
                "_raw_EA": raw_ea,
                "_oxidation_potential": oxidation_potential,
                "_reduction_potential": reduction_potential,
            }
        )
    return rows


def read_rx(path: Path) -> list[dict[str, object]]:
    if path.stat().st_size != RX_SOURCE_SIZE:
        raise ValueError(
            f"RX-392 size mismatch: {path.stat().st_size} != {RX_SOURCE_SIZE}"
        )
    actual_hash = sha256_file(path)
    if actual_hash != RX_SOURCE_SHA256:
        raise ValueError(f"RX-392 SHA256 mismatch: {actual_hash}")
    return parse_rx_text(path.read_text(encoding="utf-8"))


def _group_sort_key(name: str) -> tuple[int, str]:
    prefix = "CompMol"
    if not name.startswith(prefix):
        return (10**9, name)
    try:
        return (int(name[len(prefix) :]), name)
    except ValueError:
        return (10**9, name)


def _scalar_dataset(group: h5py.Group, name: str) -> float:
    if name not in group:
        raise ValueError(f"Batt-P30K group is missing {name}")
    value = np.asarray(group[name][...], dtype=float)
    if value.size != 1 or not np.isfinite(value).all():
        raise ValueError(f"Batt-P30K {name} must contain one finite value")
    return float(value.reshape(-1)[0])


def _smiles_from_dataset(group: h5py.Group) -> str:
    if "smiles" not in group:
        raise ValueError("Batt-P30K group is missing smiles")
    raw = group["smiles"][0]
    if isinstance(raw, bytes):
        return raw.decode("utf-8")
    return str(raw)


def read_batt_p30k(path: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    RDLogger.DisableLog("rdApp.*")
    with h5py.File(path, "r") as handle:
        for key in sorted(handle.keys(), key=_group_sort_key):
            group = handle[key]
            smiles = _smiles_from_dataset(group)
            standardized = standardize_molecule(smiles)
            if "dipole" not in group:
                raise ValueError(f"Batt-P30K {key} is missing dipole")
            dipole = np.asarray(group["dipole"][...], dtype=float)
            if dipole.shape != (3,) or not np.isfinite(dipole).all():
                raise ValueError(f"Batt-P30K {key}/dipole must be a finite vector")
            rows.append(
                {
                    "row_id": f"batt-p30k:{key}",
                    "source": "Batt-P30K",
                    "inchikey": standardized.inchikey,
                    "smiles": standardized.smiles,
                    "name": key,
                    "IP": _scalar_dataset(group, "ip"),
                    "EA": _scalar_dataset(group, "ea"),
                    "HOMO": _scalar_dataset(group, "homo"),
                    "LUMO": _scalar_dataset(group, "lumo"),
                    "dipole": float(np.linalg.norm(dipole)),
                    "oxidation_free_energy": "",
                    "reduction_free_energy": "",
                    "source_doi": BATT_SLM_DOI,
                    "method": "wB97X-V/def2-TZVPPD/SMD(epsilon=18.5)",
                    "status": "source_native_dft",
                }
            )
    return rows


def regression_metrics(
    target: np.ndarray,
    prediction: np.ndarray,
) -> dict[str, float]:
    target = np.asarray(target, dtype=float)
    prediction = np.asarray(prediction, dtype=float)
    return {
        "mae": float(mean_absolute_error(target, prediction)),
        "rmse": float(np.sqrt(mean_squared_error(target, prediction))),
        "r2": float(r2_score(target, prediction)),
    }


def _morgan_count_features(smiles_values: Sequence[str]) -> np.ndarray:
    generator = Chem.rdFingerprintGenerator.GetMorganGenerator(
        radius=FP_RADIUS,
        fpSize=FP_SIZE,
    )
    rows: list[np.ndarray] = []
    for smiles in smiles_values:
        molecule = Chem.MolFromSmiles(smiles)
        if molecule is None:
            raise ValueError(f"cannot parse SMILES: {smiles!r}")
        rows.append(generator.GetCountFingerprintAsNumPy(molecule))
    return np.vstack(rows).astype(np.float32, copy=False)


def _scalar_gpr() -> GaussianProcessRegressor:
    kernel = ConstantKernel(1.0) * RBF(length_scale=1.0) + WhiteKernel(
        noise_level=1e-3
    )
    return GaussianProcessRegressor(
        kernel=kernel,
        alpha=1e-6,
        normalize_y=True,
        n_restarts_optimizer=2,
        random_state=SPLIT_SEED,
    )


def _fingerprint_gpr() -> GaussianProcessRegressor:
    kernel = ConstantKernel(1.0) * RBF(length_scale=10.0) + WhiteKernel(
        noise_level=1.0
    )
    return GaussianProcessRegressor(
        kernel=kernel,
        alpha=1e-6,
        normalize_y=True,
        n_restarts_optimizer=2,
        random_state=SPLIT_SEED,
    )


def _fit_predictions(
    model_name: str,
    train_features: np.ndarray,
    train_target: np.ndarray,
    all_features: np.ndarray,
    test_indices: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, str]:
    if model_name == "linear":
        model = LinearRegression()
        model.fit(train_features, train_target)
        prediction = np.asarray(model.predict(all_features), dtype=float)
        std = np.full(len(all_features), np.nan, dtype=float)
        config = (
            f"LinearRegression; coefficients={model.coef_.tolist()}; "
            f"intercept={float(model.intercept_)}"
        )
        return prediction, std, config

    if model_name == "scalar_gpr":
        scaler = StandardScaler()
        train_scaled = scaler.fit_transform(train_features)
        all_scaled = scaler.transform(all_features)
        model = _scalar_gpr()
    elif model_name == "fingerprint_gpr":
        scaler = StandardScaler()
        train_scaled = scaler.fit_transform(train_features)
        all_scaled = scaler.transform(all_features)
        model = _fingerprint_gpr()
    else:
        raise ValueError(f"unknown redox model: {model_name}")

    model.fit(train_scaled, train_target)
    prediction, std = model.predict(all_scaled, return_std=True)
    config = (
        "StandardScaler + GaussianProcessRegressor; "
        f"initial_kernel={model.kernel}; final_kernel={model.kernel_}; "
        f"alpha={model.alpha}; normalize_y={model.normalize_y}; "
        f"n_restarts_optimizer={model.n_restarts_optimizer}; "
        f"random_state={model.random_state}"
    )
    return np.asarray(prediction, dtype=float), np.asarray(std, dtype=float), config


def _write_csv(path: Path, rows: Sequence[Mapping[str, object]], fields: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _plot_linear(rows: Sequence[Mapping[str, object]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    figure, axes = plt.subplots(1, 2, figsize=(11.0, 4.8))
    for axis, target_name, feature_name in (
        (axes[0], "oxidation_free_energy", "IP"),
        (axes[1], "reduction_free_energy", "EA"),
    ):
        x = np.asarray([float(row[feature_name]) for row in rows], dtype=float)
        y = np.asarray([float(row[target_name]) for row in rows], dtype=float)
        slope, intercept = np.polyfit(x, y, 1)
        prediction = slope * x + intercept
        axis.scatter(x, y, s=18, alpha=0.65, color="#1d4ed8")
        x_line = np.linspace(float(x.min()), float(x.max()), 200)
        axis.plot(x_line, slope * x_line + intercept, color="#dc2626", linewidth=1.5)
        axis.set_xlabel(f"{feature_name} (eV)")
        axis.set_ylabel(f"{target_name.replace('_', ' ')} (eV)")
        axis.set_title(
            f"{feature_name} linear fit: MAE={mean_absolute_error(y, prediction):.3f} eV"
        )
    figure.tight_layout()
    figure.savefig(path, dpi=180)
    plt.close(figure)


def _plot_parity(
    prediction_rows: Sequence[Mapping[str, object]],
    path: Path,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    figure, axes = plt.subplots(2, 3, figsize=(15.0, 8.5), sharex=False, sharey=False)
    for row_index, target_name in enumerate(TARGETS):
        for column_index, model_name in enumerate(MODEL_NAMES):
            rows = [
                row
                for row in prediction_rows
                if row["target_name"] == target_name
                and row["model"] == model_name
                and row["used_for_metrics"] == "true"
            ]
            target = np.asarray([float(row["target"]) for row in rows], dtype=float)
            prediction = np.asarray(
                [float(row["prediction"]) for row in rows],
                dtype=float,
            )
            metrics = regression_metrics(target, prediction)
            axis = axes[row_index, column_index]
            axis.scatter(target, prediction, s=18, alpha=0.7, color="#2563eb")
            lower = min(float(target.min()), float(prediction.min()))
            upper = max(float(target.max()), float(prediction.max()))
            axis.plot([lower, upper], [lower, upper], color="#dc2626", linewidth=1.2)
            axis.set_xlabel("Observed redox free energy (eV)")
            axis.set_ylabel("Predicted redox free energy (eV)")
            axis.set_title(
                f"{target_name.replace('_', ' ')}\n"
                f"{model_name}: MAE={metrics['mae']:.3f}, R2={metrics['r2']:.3f}"
            )
    figure.tight_layout()
    figure.savefig(path, dpi=180)
    plt.close(figure)


def _test_id_hash(rows: Sequence[Mapping[str, object]], test_indices: Sequence[int]) -> str:
    payload = "|".join(str(rows[int(index)]["row_id"]) for index in sorted(test_indices))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def run_baseline(
    *,
    rx_path: Path,
    batt_path: Path,
    merged_path: Path,
    predictions_path: Path,
    summary_path: Path,
    linear_plot_path: Path,
    parity_plot_path: Path,
) -> dict[str, object]:
    rx_rows = read_rx(rx_path)
    p30k_rows = read_batt_p30k(batt_path)
    if len(rx_rows) != RX_SOURCE_ROWS:
        raise ValueError(f"RX-392 row count mismatch: {len(rx_rows)}")
    if len(p30k_rows) != P30K_ROWS:
        raise ValueError(f"Batt-P30K row count mismatch: {len(p30k_rows)}")

    merged_rows = [
        {field: row.get(field, "") for field in MERGED_COLUMNS}
        for row in (*rx_rows, *p30k_rows)
    ]
    _write_csv(merged_path, merged_rows, MERGED_COLUMNS)

    numeric_rows = [row for row in rx_rows if isinstance(row["IP"], float)]
    fingerprint_features = _morgan_count_features(
        [str(row["smiles"]) for row in numeric_rows]
    )
    train_indices, test_indices = deterministic_split(
        len(numeric_rows),
        test_fraction=TEST_FRACTION,
        seed=SPLIT_SEED,
    )
    prediction_rows: list[dict[str, object]] = []
    metrics: dict[str, dict[str, dict[str, float]]] = {}
    model_configs: dict[str, str] = {}
    for target_name in TARGETS:
        target = np.asarray(
            [float(row[target_name]) for row in numeric_rows],
            dtype=float,
        )
        scalar_features = np.asarray(
            [[float(row[TARGET_FEATURES[target_name]])] for row in numeric_rows],
            dtype=float,
        )
        metrics[target_name] = {}
        for model_name in MODEL_NAMES:
            features = (
                fingerprint_features
                if model_name == "fingerprint_gpr"
                else scalar_features
            )
            prediction, std, config = _fit_predictions(
                model_name,
                features[train_indices],
                target[train_indices],
                features,
                test_indices,
            )
            model_configs[f"{target_name}:{model_name}"] = config
            for row_index, row in enumerate(numeric_rows):
                prediction_rows.append(
                    {
                        "row_id": row["row_id"],
                        "target_name": target_name,
                        "model": model_name,
                        "source": row["source"],
                        "inchikey": row["inchikey"],
                        "smiles": row["smiles"],
                        "split": (
                            "train" if row_index in set(train_indices) else "test"
                        ),
                        "used_for_metrics": (
                            "true" if row_index in set(test_indices) else "false"
                        ),
                        "target": target[row_index],
                        "prediction": prediction[row_index],
                        "std": "" if np.isnan(std[row_index]) else std[row_index],
                        "abs_error": abs(target[row_index] - prediction[row_index]),
                    }
                )
            test_predictions = prediction[test_indices]
            metrics[target_name][model_name] = regression_metrics(
                target[test_indices],
                test_predictions,
            )
    _write_csv(predictions_path, prediction_rows, PREDICTION_COLUMNS)
    _plot_linear(numeric_rows, linear_plot_path)
    _plot_parity(prediction_rows, parity_plot_path)

    best_model_mae = {
        target_name: min(
            metrics[target_name][model_name]["mae"] for model_name in MODEL_NAMES
        )
        for target_name in TARGETS
    }
    summary = {
        "schema_version": 1,
        "source_commit": RX_SOURCE_COMMIT,
        "sources": {
            "rx_392": {
                "path": rx_path.relative_to(REPOSITORY_ROOT).as_posix(),
                "url": RX_SOURCE_URL,
                "upstream_script_url": RX_UPSTREAM_SCRIPT_URL,
                "sha256": sha256_file(rx_path),
                "size_bytes": rx_path.stat().st_size,
                "rows": len(rx_rows),
                "source_doi": BATT_SLM_DOI,
                "condition": "DIELECTRIC=18.5",
                "target_unit": "eV",
                "status": "source_native_dft",
            },
            "batt_p30k": {
                "path": batt_path.relative_to(REPOSITORY_ROOT).as_posix(),
                "sha256": sha256_file(batt_path),
                "rows": len(p30k_rows),
                "source_doi": BATT_SLM_DOI,
                "condition": "wB97X-V/def2-TZVPPD/SMD(epsilon=18.5)",
                "status": "source_native_dft",
            },
            "ecw_308": {
                "status": "unavailable",
                "rows": 0,
                "reason": "Wiley/Cloudflare blocked; no open machine-readable dataset",
            },
        },
        "merged": {
            "path": merged_path.relative_to(REPOSITORY_ROOT).as_posix(),
            "sha256": canonical_text_sha256(merged_path),
            "rows": len(merged_rows),
            "source_counts": dict(Counter(row["source"] for row in merged_rows)),
            "rx_redox_target_rows": len(numeric_rows),
        },
        "units": {
            "IP": "eV",
            "EA": "eV",
            "HOMO": "eV",
            "LUMO": "eV",
            "dipole": "atomic_units (e*bohr)",
            "oxidation_free_energy": "eV",
            "reduction_free_energy": "eV",
            "note": (
                "RX-392 free energies follow upstream redox_free_ener.py. "
                "A potential of 4.44 V vs H+/H is applied as 4.44 eV in the "
                "electron free-energy convention; the numeric gate threshold "
                "0.15 is not mixed with a separately converted volt scale."
            ),
        },
        "split": {
            "method": "deterministic permutation",
            "seed": SPLIT_SEED,
            "test_fraction": TEST_FRACTION,
            "train_count": len(train_indices),
            "test_count": len(test_indices),
            "test_id_hash": _test_id_hash(numeric_rows, test_indices),
        },
        "model_configs": model_configs,
        "metrics": metrics,
        "gate": {
            "threshold_mae": GATE_MAE_THRESHOLD,
            "unit": "eV",
            "criterion": "best model per target has held-out MAE below threshold",
            "best_model_mae": best_model_mae,
            "passed": all(value < GATE_MAE_THRESHOLD for value in best_model_mae.values()),
        },
        "outputs": {
            "merged_csv": merged_path.relative_to(REPOSITORY_ROOT).as_posix(),
            "predictions_csv": predictions_path.relative_to(REPOSITORY_ROOT).as_posix(),
            "summary_json": summary_path.relative_to(REPOSITORY_ROOT).as_posix(),
            "linear_plot": linear_plot_path.relative_to(REPOSITORY_ROOT).as_posix(),
            "parity_plot": parity_plot_path.relative_to(REPOSITORY_ROOT).as_posix(),
        },
    }
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--rx",
        type=Path,
        default=REPOSITORY_ROOT / "data" / "external" / "Batt-SLM-RX-392.csv",
    )
    parser.add_argument(
        "--batt",
        type=Path,
        default=REPOSITORY_ROOT / "data" / "raw" / "batt" / "Batt-P30K.h5",
    )
    parser.add_argument(
        "--merged",
        type=Path,
        default=REPOSITORY_ROOT / "data" / "processed" / "redox_merged.csv",
    )
    parser.add_argument(
        "--predictions",
        type=Path,
        default=REPOSITORY_ROOT / "data" / "processed" / "p4_redox_predictions.csv",
    )
    parser.add_argument(
        "--summary",
        type=Path,
        default=REPOSITORY_ROOT / "probes" / "p4_redox_summary.json",
    )
    parser.add_argument(
        "--linear-plot",
        type=Path,
        default=REPOSITORY_ROOT / "probes" / "artifacts" / "p4_redox_linear.png",
    )
    parser.add_argument(
        "--parity-plot",
        type=Path,
        default=REPOSITORY_ROOT / "probes" / "artifacts" / "p4_redox_parity.png",
    )
    args = parser.parse_args(argv)
    summary = run_baseline(
        rx_path=args.rx,
        batt_path=args.batt,
        merged_path=args.merged,
        predictions_path=args.predictions,
        summary_path=args.summary,
        linear_plot_path=args.linear_plot,
        parity_plot_path=args.parity_plot,
    )
    print(json.dumps(summary["metrics"], indent=2))
    print(json.dumps(summary["gate"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
