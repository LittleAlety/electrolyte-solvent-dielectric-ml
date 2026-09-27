"""Build the frozen Uni-Mol embedding block for the W18-P5 lane.

This script is deliberately standalone: it imports only the standard library and
numpy at module level, and reaches for uni-mol-tools lazily inside the one
function that needs it.  That lets it run under an isolated interpreter that
carries the pre-trained runtime, while the scoring lane itself keeps running
under the pinned project interpreter.  The two never share a process.

Input:  probes/artifacts/dielectric_xtb_full_table_migration_conformers.csv
        (columns inchikey, smiles -- the conformer roster)
Output: probes/artifacts/dielectric_unimol_embedding.csv
        (columns inchikey, smiles, dim_000 ... dim_{D-1})

Run:
    python probes/build_unimol_embeddings.py --limit 3      # smoke test
    python probes/build_unimol_embeddings.py                # full roster
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
import time
from collections.abc import Mapping, Sequence
from pathlib import Path

import numpy as np

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS_DIR = REPOSITORY_ROOT / "probes" / "artifacts"
ROSTER_PATH = ARTIFACTS_DIR / "dielectric_xtb_full_table_migration_conformers.csv"
OUTPUT_PATH = ARTIFACTS_DIR / "dielectric_unimol_embedding.csv"

CHECKPOINT_ENVIRONMENT_VARIABLE = "UNIMOL_WEIGHTS_PATH"
CHECKPOINT_FILENAME = "mol_pre_all_h_220816.pt"
DICTIONARY_FILENAME = "mol.dict.txt"
ID_COLUMNS = ("inchikey", "smiles")


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--roster", type=Path, default=ROSTER_PATH)
    parser.add_argument("--out", type=Path, default=OUTPUT_PATH)
    parser.add_argument("--checkpoint", type=Path, default=None)
    parser.add_argument("--limit", type=int, default=0)
    return parser.parse_args(argv)


def checkpoint_search_paths(override: Path | None) -> tuple[Path, ...]:
    candidates: list[Path] = []
    if override is not None:
        candidates.append(override)
    environment = os.environ.get(CHECKPOINT_ENVIRONMENT_VARIABLE, "").strip()
    if environment:
        candidates.append(Path(environment))
    home = Path.home()
    candidates.append(home / ".unimol" / CHECKPOINT_FILENAME)
    candidates.append(home / ".cache" / "unimol" / CHECKPOINT_FILENAME)
    candidates.append(ARTIFACTS_DIR / CHECKPOINT_FILENAME)
    return tuple(candidates)


def locate_checkpoint(override: Path | None) -> Path:
    for candidate in checkpoint_search_paths(override):
        try:
            if candidate.is_file() and candidate.stat().st_size > 0:
                return candidate
        except OSError:
            continue
    raise SystemExit(
        "no checkpoint found; searched "
        + ", ".join(str(path) for path in checkpoint_search_paths(override))
    )


def read_roster(path: Path) -> dict[str, str]:
    table: dict[str, str] = {}
    with path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            key = str(row.get("inchikey", "")).strip()
            value = str(row.get("smiles", "")).strip()
            if key and value and key not in table:
                table[key] = value
    return table


def write_table(path: Path, columns: Sequence[str], rows: Sequence[Mapping[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(columns), lineterminator=chr(10))
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row[column] for column in columns})


def install_checkpoint(path: Path) -> Path:
    """uni-mol-tools resolves both the weights and mol.dict.txt through
    UNIMOL_WEIGHT_DIR; point it at the directory that actually holds them."""

    os.environ["UNIMOL_WEIGHT_DIR"] = str(path.parent)
    return path


def embed(smiles: Sequence[str], checkpoint: Path) -> np.ndarray:
    from unimol_tools import UniMolRepr

    install_checkpoint(checkpoint)
    options: dict[str, object] = {
        "data_type": "molecule",
        "remove_hs": False,
        "use_cuda": False,
        "pretrained_model_path": str(checkpoint),
        "save_path": str(checkpoint.parent),
    }
    dictionary = checkpoint.parent / DICTIONARY_FILENAME
    if dictionary.is_file():
        options["pretrained_dict_path"] = str(dictionary)
    encoder = UniMolRepr(**options)
    representation = encoder.get_repr(list(smiles), return_atomic_reprs=False)
    if isinstance(representation, dict):
        array = np.asarray(representation.get("cls_repr", []), dtype=float)
    else:
        array = np.asarray(representation, dtype=float)
    if array.ndim == 3:
        array = array[0]
    if array.ndim != 2 or array.shape[0] != len(smiles):
        raise SystemExit(
            "unexpected embedding shape " + str(array.shape) + " for " + str(len(smiles))
        )
    return array


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    started = time.time()
    if not args.roster.is_file():
        print("MISSING " + str(args.roster))
        return 1
    checkpoint = locate_checkpoint(args.checkpoint)
    print("checkpoint " + str(checkpoint) + " bytes=" + str(checkpoint.stat().st_size))
    roster = read_roster(args.roster)
    keys = sorted(roster)
    if args.limit > 0:
        keys = keys[: args.limit]
    print("roster compounds=" + str(len(keys)))
    array = embed([roster[key] for key in keys], checkpoint)
    columns = list(ID_COLUMNS) + [
        "dim_" + format(index, "03d") for index in range(array.shape[1])
    ]
    rows: list[dict[str, object]] = []
    for index, key in enumerate(keys):
        row: dict[str, object] = {"inchikey": key, "smiles": roster[key]}
        for position in range(array.shape[1]):
            row[columns[2 + position]] = float(array[index, position])
        rows.append(row)
    write_table(args.out, columns, rows)
    print(
        "wrote "
        + str(args.out)
        + " rows="
        + str(len(rows))
        + " dim="
        + str(array.shape[1])
        + " in "
        + str(round(time.time() - started, 1))
        + "s",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
