"""Cross-check v0.2 dielectric values against restricted SpringerMaterials data."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import unicodedata
from collections.abc import Mapping, Sequence
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = (
    REPOSITORY_ROOT
    / "data"
    / "restricted"
    / "springer_materials"
    / "interactive_v02_dielectric_export.json"
)
DEFAULT_OUTPUT_DIR = (
    REPOSITORY_ROOT / "data" / "restricted" / "springer_materials"
)


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv_rows(
    path: Path,
    fieldnames: Sequence[str],
    rows: Sequence[Mapping[str, object]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _normalize_name(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).casefold()
    value = value.replace("_", " ").strip()
    value = re.sub(r"\s+", " ", value)
    return value


def _pure_name(value: str) -> str:
    name = re.sub(
        r"^\s*dielectric constant (?:of|for)\s+",
        "",
        value,
        flags=re.IGNORECASE,
    )
    name = re.sub(r"\s*\(pure\)\s*$", "", name, flags=re.IGNORECASE)
    for prefix in ("dl-", "d-", "l-", "cis-", "trans-"):
        if name.casefold().startswith(prefix):
            name = name[len(prefix) :]
    return _normalize_name(name)


def _float(value: object) -> float | None:
    if value in {"", None, "-"}:
        return None
    try:
        return float(str(value))
    except ValueError:
        return None


def _dataset_near_temperature_values(
    dataset: Mapping[str, object],
    *,
    target_temperature: float,
    max_delta_temperature: float,
) -> list[float]:
    values: list[float] = []
    rows = dataset.get("rows", [])
    if not isinstance(rows, list):
        return values
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        temperature = _float(row.get("temperature_K"))
        dielectric = _float(row.get("dielectric"))
        if temperature is None or dielectric is None:
            continue
        if abs(temperature - target_temperature) <= max_delta_temperature:
            values.append(dielectric)
    return values


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_plot(rows: Sequence[Mapping[str, object]], path: Path) -> None:
    target = np.asarray([float(row["v02_dielectric"]) for row in rows])
    observed = np.asarray([float(row["smi_median_dielectric"]) for row in rows])
    delta = observed - target
    figure, axes = plt.subplots(1, 2, figsize=(11, 4.5))
    axes[0].scatter(target, observed, alpha=0.75, color="#0f766e")
    lower = min(float(target.min()), float(observed.min()))
    upper = max(float(target.max()), float(observed.max()))
    axes[0].plot([lower, upper], [lower, upper], color="#b91c1c", linewidth=1.2)
    axes[0].set_xlabel("v0.2 dielectric")
    axes[0].set_ylabel("SpringerMaterials median near T")
    axes[0].set_title("Restricted cross-check")
    axes[0].grid(alpha=0.2)
    axes[1].hist(delta, bins=min(12, max(4, len(delta) // 2)), color="#1d4ed8", alpha=0.8)
    axes[1].axvline(0, color="#b91c1c", linewidth=1.2)
    axes[1].set_xlabel("SpringerMaterials - v0.2")
    axes[1].set_ylabel("Compounds")
    axes[1].set_title("Signed difference")
    axes[1].grid(alpha=0.2)
    figure.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=180)
    plt.close(figure)


def build_crosscheck(
    v02_rows: Sequence[Mapping[str, str]],
    datasets: Sequence[Mapping[str, object]],
    *,
    max_delta_temperature: float,
) -> list[dict[str, object]]:
    v02_by_name: dict[str, Mapping[str, str]] = {}
    for row in v02_rows:
        v02_by_name[_normalize_name(row["name"])] = row

    rows: list[dict[str, object]] = []
    for dataset in datasets:
        title = str(dataset.get("title", ""))
        v02_row = v02_by_name.get(_pure_name(title))
        if v02_row is None:
            continue
        target_temperature = float(v02_row["T_K"])
        target_value = float(v02_row["dielectric"])
        values = _dataset_near_temperature_values(
            dataset,
            target_temperature=target_temperature,
            max_delta_temperature=max_delta_temperature,
        )
        if not values:
            continue
        median_value = float(np.median(values))
        abs_delta = abs(median_value - target_value)
        rows.append(
            {
                "doc_id": dataset["doc_id"],
                "name": v02_row["name"],
                "inchikey": v02_row["inchikey"],
                "v02_T_K": f"{target_temperature:.6g}",
                "v02_dielectric": f"{target_value:.6g}",
                "smi_near_rows": str(len(values)),
                "smi_median_dielectric": f"{median_value:.6g}",
                "signed_delta": f"{median_value - target_value:.6g}",
                "absolute_delta": f"{abs_delta:.6g}",
                "source_url": dataset["url"],
            }
        )
    rows.sort(key=lambda row: float(row["absolute_delta"]), reverse=True)
    return rows


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--v02",
        type=Path,
        default=REPOSITORY_ROOT / "data" / "dielectric_v02.csv",
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--summary",
        type=Path,
        default=REPOSITORY_ROOT / "probes" / "springer_materials_crosscheck_summary.json",
    )
    parser.add_argument("--max-delta-temperature", type=float, default=5.0)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    if not args.input.is_file():
        raise SystemExit(f"restricted input not found: {args.input}")
    v02_rows = read_csv_rows(args.v02)
    payload = json.loads(args.input.read_text(encoding="utf-8"))
    datasets = payload.get("datasets", [])
    if not isinstance(datasets, list):
        raise TypeError("restricted Springer export has no datasets list")
    rows = build_crosscheck(
        v02_rows,
        datasets,
        max_delta_temperature=args.max_delta_temperature,
    )
    if not rows:
        raise SystemExit("no matched compounds with near-temperature data")
    abs_delta = np.asarray([float(row["absolute_delta"]) for row in rows])
    signed_delta = np.asarray([float(row["signed_delta"]) for row in rows])
    fieldnames = (
        "doc_id",
        "name",
        "inchikey",
        "v02_T_K",
        "v02_dielectric",
        "smi_near_rows",
        "smi_median_dielectric",
        "signed_delta",
        "absolute_delta",
        "source_url",
    )
    csv_path = args.output_dir / "v02_crosscheck.csv"
    plot_path = args.output_dir / "v02_crosscheck.png"
    write_csv_rows(csv_path, fieldnames, rows)
    _write_plot(rows, plot_path)
    summary = {
        "source": "SpringerMaterials Interactive (restricted)",
        "input_path": args.input.relative_to(REPOSITORY_ROOT).as_posix(),
        "input_sha256": _sha256_file(args.input),
        "v02_path": args.v02.relative_to(REPOSITORY_ROOT).as_posix(),
        "v02_sha256": _sha256_file(args.v02),
        "max_delta_temperature_K": args.max_delta_temperature,
        "matched_compounds": len(rows),
        "median_absolute_delta": float(np.median(abs_delta)),
        "p90_absolute_delta": float(np.quantile(abs_delta, 0.9)),
        "max_absolute_delta": float(np.max(abs_delta)),
        "mean_signed_delta": float(np.mean(signed_delta)),
        "redistribution_status": "restricted",
        "outputs": {
            "crosscheck_csv": csv_path.relative_to(REPOSITORY_ROOT).as_posix(),
            "plot": plot_path.relative_to(REPOSITORY_ROOT).as_posix(),
        },
    }
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
