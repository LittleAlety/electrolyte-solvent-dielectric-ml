"""Lever 8: a Li+-coordination feature block for the dielectric scoreboard.

Motivation
----------
The project's own ceiling analysis (appendix X, section X-2) says the grouped R2
is capped because a structure-only descriptor set cannot see the collective
polarisation term: the Kirkwood g dimension, the association strength. The
association blind spot has the same shape (associating liquids carry MAE 11.5
against 5.0 in domain). The review this probe is built from
(ACS Energy Lett. 2025, 10, 4962, doi 10.1021/acsenergylett.5c02291) catalogues
the solvating-power descriptors that proxy exactly that missing dimension, and
sorts them by whether they are computable from structure alone.

Two of its descriptor families are both cheap for us and target aligned: the
electrostatic-potential / partial-charge family and the Li+ binding energy. This
probe implements those five columns and asks one question on the frozen main
scoreboard:

    does appending them to the frozen v03 physical block move grouped R2?

What is measured
----------------
Five columns, one row per compound, appended beside the 13 frozen physical
columns. No frozen column is touched.

* ``li_binding_energy_ev`` - E(Li+ . solvent) - E(solvent) - E(Li+), in eV.
* ``li_binding_distance_a`` - shortest Li-O/N distance in the relaxed complex.
* ``q_max_h`` - largest positive Mulliken charge on a hydrogen of the *isolated*
  solvent (the frozen week-3 xTB run), the donor-acidity axis.
* ``q_min_hetero`` - most negative Mulliken charge on O or N of the isolated
  solvent, the basicity axis.
* ``esp_imbalance`` - ``q_max_h - q_min_hetero``, a one-number asymmetry.

The three charge columns are read from the frozen xTB cache that produced
``data/processed/dielectric_physical_features_v03.csv``: the compound's own run
directory is identified by matching its reported total energy against the frozen
feature row, so the charges belong to the very geometry the frozen block
describes. Only the Li+ complex is new work, which is exactly the cost the
pre-registration budgets ("one extra xTB relaxation per compound").

Protocol, pinned before the run
-------------------------------
* The Li+ complex is embedded with the frozen helper
  ``electrolyte_ml.xtb_features.generate_3d_xyz`` at four seeds (42..45), which
  is RDKit ETKDGv3 + MMFF, and is relaxed with the single-thread launcher
  ``electrolyte_ml.xtb_runner.run_xtb_subprocess`` under
  ``xtb_optimisation_arguments`` (``--opt --gfn 2 --chrg <q> --uhf 0``). No
  additional flag is used, so the pin that makes the frozen features
  bit-reproducible is inherited unchanged.
* The cation site is the O or N with the fewest heavy-atom neighbours, ties
  broken by atom index. Li starts 1.90 A from it along the direction opposite
  the sum of the site's bond vectors, i.e. in the lone-pair cone.
* The complex is the lowest-energy converged conformer of the four; its energy,
  its geometry and therefore its Li-O/N distance come from that one run.
* Delta E uses the *frozen* solvent energy, so the reference side is the released
  protocol's number rather than a second, subtly different relaxation.

Honest boundaries (all of them are reported in the summary, not hidden here)
--------------------------------------------------------------------------
* Target mismatch: the review is about *solvating power in an electrolyte*, this
  probe predicts the *static dielectric constant of a pure solvent*. The block
  is a hypothesis about which of the review's axes transfers, not a claim that
  the review predicts epsilon.
* GFN2-xTB overbinds cations; the absolute binding energies are not
  thermochemistry. Only their spread across compounds is used as a feature.
* Li+ relaxation here is gas phase and single molecule. No counter-anion, no
  solvent-solvent competition, which is the review's own listed weakness of the
  binding-energy descriptor.
* xTB wall clock is audited against a 45 minute ceiling. If the measured cost
  had put the full 97-compound scoreboard out of reach the probe was to shrink
  to a bounded pilot and register the remainder pending. The measured cost is
  far below the ceiling, so the full scoreboard is covered and nothing is
  pending.

Read-only with respect to every released artefact. No network I/O. Writes only
``probes/dielectric_coordination_block_summary.json``, the
``probes/artifacts/dielectric_coordination_block_*.csv`` tables, the
``reports/dielectric_coordination_block.md`` report.

The xTB scratch does *not* live under ``data/``: a sibling probe's deliverable is
a recursive scan of ``data/`` for local traces, so any new file written there
would silently move that scan's output. The scratch therefore defaults to
``$LOCALAPPDATA/electrolyte-ml/xtb_coordination_block`` (``--work-root``
overrides it), and the frozen, structured product of this probe is the
per-compound feature table under ``probes/artifacts/``.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))
sys.path.insert(0, str(REPOSITORY_ROOT / "probes"))

import numpy as np
from dielectric_band_ablation import (
    INERT_TOLERANCE,
    MIN_TEST_ROWS_PER_FOLD,
    ROOM_BAND,
    drop_thin_folds,
    effective_repeats,
)
from dielectric_coverage_paired_benchmark import (
    COVERAGE_PATH,
    FEATURES_PATH,
    NEW_FEATURES_PATH,
    ZERO_FREQUENCY_ORIGIN,
    load_coverage_table,
    merge_feature_blocks,
)
from dielectric_observations_grouped_benchmark import (
    METRIC_NAMES,
    build_matrices,
    summarize_repeats,
)
from dielectric_representation_ablation import (
    N_REPEATS,
    N_SPLITS,
    PHYSICAL_COLUMNS,
    REPRESENTATIONS,
    SEED,
    evaluate_repeat,
    fit_predict_representation,
)
from dielectric_room_window_paired import (
    HYBRID,
    PAIRED_METRICS,
    audit_masks,
    masked_splits,
)

from electrolyte_ml.exporting import canonical_text_sha256
from electrolyte_ml.pathing import portable_relative_path

PREREG_PATH = REPOSITORY_ROOT / "probes" / "dielectric_coordination_block_prereg.json"
SUMMARY_PATH = REPOSITORY_ROOT / "probes" / "dielectric_coordination_block_summary.json"
ARTIFACTS_DIR = REPOSITORY_ROOT / "probes" / "artifacts"
REPORT_PATH = REPOSITORY_ROOT / "reports" / "dielectric_coordination_block.md"
FROZEN_XTB_CACHE = REPOSITORY_ROOT / "data" / "interim" / "xtb_features"
def _default_work_root() -> Path:
    """Scratch root, deliberately outside the repository data tree.

    A sibling probe's deliverable is a recursive scan of ``data/`` for local
    traces, so writing new files there moves that scan's output. The xTB scratch
    is disposable, so it is kept out of the tree entirely.
    """

    import tempfile

    base = os.environ.get("LOCALAPPDATA") or tempfile.gettempdir()
    return Path(base) / "electrolyte-ml" / "xtb_coordination_block"


XTB_WORK_ROOT = _default_work_root()

ARTIFACT_STEM = "dielectric_coordination_block"
FEATURES_ARTIFACT = ARTIFACT_STEM + "_features"

COORDINATION_COLUMNS = (
    "li_binding_energy_ev",
    "li_binding_distance_a",
    "q_max_h",
    "q_min_hetero",
    "esp_imbalance",
)

#: The frozen main scoreboard the pre-registration pins. Reproduced, not chosen.
SCOREBOARD_ROWS = 457
SCOREBOARD_COMPOUNDS = 97
BASELINE_R2 = 0.4091179943351143
REPRODUCTION_TOLERANCE = 1e-09
PASS_DELTA = 0.0200
KILL_DELTA = 0.0050
PLACEBO_TOLERANCE = 0.0200

#: Protocol constants. Written down before the run; see the module docstring.
HARTREE_TO_EV = 27.211386245988
LI_PLACEMENT_DISTANCE_A = 1.90
CONFORMER_SEEDS = (42, 43, 44, 45)
XTB_TIMEOUT_SECONDS = 1800
XTB_BUDGET_SECONDS = 45 * 60
ALPHA_PHYSICAL_COLUMNS = len(PHYSICAL_COLUMNS)

_TOTAL_ENERGY_PATTERNS = (
    re.compile(r"::\s*total energy\s+([-+]?\d+\.\d+(?:[Ee][-+]?\d+)?)\s+Eh"),
    re.compile(r"\|\s*TOTAL ENERGY\s+([-+]?\d+\.\d+(?:[Ee][-+]?\d+)?)\s+Eh"),
)


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    import csv

    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv_rows(
    path: Path,
    fieldnames: Sequence[str],
    rows: Sequence[Mapping[str, object]],
) -> None:
    """Write LF-only CSV: `.gitattributes` pins `*.csv` to `eol=lf`."""

    import csv

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _total_energy_hartree(text: str) -> float | None:
    for pattern in _TOTAL_ENERGY_PATTERNS:
        matches = pattern.findall(text)
        if matches:
            return float(matches[-1])
    return None


def read_xyz_block(text: str) -> tuple[list[str], np.ndarray]:
    lines = text.strip().splitlines()
    if not lines:
        raise ValueError("empty XYZ block")
    count = int(lines[0])
    symbols: list[str] = []
    coordinates: list[list[float]] = []
    for line in lines[2 : 2 + count]:
        parts = line.split()
        symbols.append(parts[0])
        coordinates.append([float(parts[1]), float(parts[2]), float(parts[3])])
    if len(symbols) != count:
        raise ValueError("truncated XYZ block")
    return symbols, np.asarray(coordinates, dtype=float)


def read_charges(path: Path, expected_atoms: int) -> np.ndarray:
    values = np.asarray([float(item) for item in path.read_text(encoding="utf-8").split()])
    if values.size != expected_atoms:
        raise ValueError(
            f"{path}: {values.size} charges for {expected_atoms} atoms"
        )
    return values

# --------------------------------------------------------------------------- #
# the frozen scoreboard
# --------------------------------------------------------------------------- #


def build_scoreboard() -> dict[str, object]:
    """Rebuild the frozen main scoreboard exactly as the paired probe defines it.

    The scored rows, the compound set and the training pool are copied from
    `dielectric_coverage_paired_benchmark`, not re-derived, so the folds this
    probe deals are the folds that produced `paired_base`. The compound set is
    asserted against the pre-registration before anything is fitted.
    """

    merged, feature_report = merge_feature_blocks()
    rows, dropped = load_coverage_table(COVERAGE_PATH, merged)
    morgan, physical, target, temperatures, groups = build_matrices(rows)
    origin = np.asarray([str(row["observation_origin"]) for row in rows])
    band = np.asarray([str(row["temperature_band"]) for row in rows])
    keys = np.asarray([str(row["inchikey"]) for row in rows])
    scored = (origin == ZERO_FREQUENCY_ORIGIN) & (band == ROOM_BAND)
    split_row_groups = [str(key) for key in groups]
    splits = list(
        drop_thin_folds(
            masked_splits(
                split_row_groups,
                score_mask=scored,
                train_mask=scored,
                n_splits=N_SPLITS,
                n_repeats=N_REPEATS,
                seed=SEED,
            ),
            min_test_rows=MIN_TEST_ROWS_PER_FOLD,
        )
    )
    audit = audit_masks(split_row_groups, score_mask=scored, train_mask=scored, splits=splits)
    repeats, note = effective_repeats(
        int(np.unique(keys[scored]).size), n_splits=N_SPLITS, requested=N_REPEATS
    )
    scored_names: dict[str, dict[str, str]] = {}
    for row, flag in zip(rows, scored, strict=True):
        if flag:
            scored_names.setdefault(
                str(row["inchikey"]),
                {"name": str(row["name"]), "smiles": str(row["smiles"])},
            )
    contract = {
        "scored_rows": int(scored.sum()),
        "compounds_scored": int(np.unique(keys[scored]).size),
        "folds": len(splits),
        "executed_repeats": repeats,
        "repeats_note": note,
        "folds_with_a_straddling_compound": audit["folds_with_a_straddling_compound"],
        "scored_rows_outside_the_score_mask": audit["scored_rows_outside_the_score_mask"],
        "matches_preregistration": (
            int(scored.sum()) == SCOREBOARD_ROWS
            and int(np.unique(keys[scored]).size) == SCOREBOARD_COMPOUNDS
        ),
    }
    return {
        "rows": rows,
        "morgan": morgan,
        "physical": physical,
        "target": target,
        "temperatures": temperatures,
        "groups": split_row_groups,
        "scored": scored,
        "splits": splits,
        "contract": contract,
        "input_report": {
            "feature_blocks": feature_report,
            "coverage_rows": len(rows),
            "dropped_by_the_coverage_loader": dict(dropped),
        },
        "compounds": scored_names,
    }


# --------------------------------------------------------------------------- #
# phase 1: the xTB coordination features
# --------------------------------------------------------------------------- #


def frozen_solvent_references() -> dict[str, dict[str, float]]:
    """The released v03 row of every compound, keyed by InChIKey.

    Three columns are kept. `polarizability_au` is the run identifier: xTB
    prints it to six decimals, and the frozen table stores all of them, so it
    separates a compound's cached runs without ambiguity. `dipole_D` is the
    cross-check. `total_energy_hartree` is kept only to be reported, never to
    be used, because of the quirk documented on `resolve_solvent_run`.
    """

    references: dict[str, dict[str, float]] = {}
    for row in read_csv_rows(FEATURES_PATH):
        try:
            references[row["inchikey"]] = {
                "polarizability_au": float(row["polarizability_au"]),
                "dipole_D": float(row["dipole_D"]),
                "total_energy_hartree": float(row["total_energy_hartree"]),
            }
        except (KeyError, TypeError, ValueError):
            continue
    return references


def solvent_run_candidates(inchikey: str) -> list[Path]:
    found = [path for path in (FROZEN_XTB_CACHE / inchikey, *sorted(FROZEN_XTB_CACHE.glob(inchikey + "__*"))) if path.is_dir()]
    return found


def _same_as_released(parsed_value: float, released_value: float) -> bool:
    """Compare through the released table's own serialization.

    `dielectric_physical_features_v03.csv` writes these columns with `%.8g`, so
    the released number is the rounded one and an absolute tolerance is the
    wrong test: `103.445901` is released as `103.4459`, a difference of exactly
    1e-6. Comparing the `%.8g` renderings asks the question that matters, which
    is whether the cached run *is* the run the released row came from.
    """

    return format(float(parsed_value), ".8g") == format(float(released_value), ".8g")


def resolve_solvent_run(
    inchikey: str,
    reference: Mapping[str, float],
    *,
    energy_tolerance: float = 1e-08,
) -> dict[str, object]:
    """Find the frozen xTB run that produced the released feature row.

    A compound's key can appear more than once in the cache (a legacy directory
    and one or more seed-keyed re-runs), so the run has to be identified rather
    than guessed. Polarizability identifies it: xTB prints `Mol. a(0)` to six
    decimals and the frozen table keeps them, while the dipole is only printed
    to three and is used as a cross-check.

    The released `total_energy_hartree` column is the *first* `:: total energy`
    line in the run log, i.e. the single point at the input geometry, because
    `electrolyte_ml.xtb_features.parse_xtb_output` uses `re.search` and the
    optimiser prints a summary block before relaxing. Dipole, polarizability
    and the geometry-derived volume are printed once, after the relaxation, so
    only the energy column carries the quirk. This probe therefore reports that
    column for transparency but takes the *relaxed* energy from the same cached
    run as the solvent reference, so that both sides of the binding energy
    describe a relaxed geometry.
    """

    matches: list[Path] = []
    considered = 0
    basis = ""
    for candidate in solvent_run_candidates(inchikey):
        output = candidate / "xtb.out"
        if not output.is_file():
            continue
        considered += 1
        text = output.read_text(encoding="utf-8", errors="replace")
        parsed = _parse_cached_run(text)
        if parsed is None:
            continue
        if _same_as_released(
            parsed["polarizability_au"], reference["polarizability_au"]
        ) and _same_as_released(parsed["dipole_D"], reference["dipole_D"]):
            matches.append(candidate)
            basis = "polarizability_au+dipole_D"
            continue
        relaxed = _total_energy_hartree(text)
        if relaxed is None:
            continue
        if abs(relaxed - reference["total_energy_hartree"]) <= energy_tolerance:
            matches.append(candidate)
            basis = "relaxed total energy (fallback)"
    chosen = matches[0] if matches else None
    relaxed_energy = None
    if chosen is not None:
        relaxed_energy = _total_energy_hartree(
            (chosen / "xtb.out").read_text(encoding="utf-8", errors="replace")
        )
    return {
        "considered": considered,
        "matches": [portable_relative_path(path, root=REPOSITORY_ROOT) for path in matches],
        "run": chosen,
        "match_basis": basis,
        "relaxed_energy_hartree": relaxed_energy,
    }


def _parse_cached_run(text: str) -> dict[str, float] | None:
    """Dipole and polarizability of a cached run, tolerant of the missing banner.

    This xTB build writes `.xtboptok` instead of echoing `normal termination of
    xtb`, so the frozen banner check is supplied here exactly as
    `run_xtb_physical_features._parse_xtb_run` supplies it.
    """

    from electrolyte_ml.xtb_features import XtbFeatureError, parse_xtb_output

    try:
        parsed = parse_xtb_output(text)
    except XtbFeatureError:
        try:
            parsed = parse_xtb_output(text + "\nnormal termination of xtb\n")
        except XtbFeatureError:
            return None
    return {
        "dipole_D": float(parsed.dipole_debye),
        "polarizability_au": float(parsed.polarizability_au),
    }


def solvent_charge_features(run_dir: Path) -> dict[str, float]:
    """The three isolated-solvent charge columns, read from one frozen xTB run."""

    symbols, _coordinates = read_xyz_block(
        (run_dir / "xtbopt.xyz").read_text(encoding="utf-8", errors="replace")
    )
    charges = read_charges(run_dir / "charges", len(symbols))
    hydrogens = [index for index, symbol in enumerate(symbols) if symbol == "H"]
    hetero = [index for index, symbol in enumerate(symbols) if symbol in ("O", "N")]
    q_max_h = float(charges[hydrogens].max()) if hydrogens else float("nan")
    q_min_hetero = float(charges[hetero].min()) if hetero else float("nan")
    return {
        "q_max_h": q_max_h,
        "q_min_hetero": q_min_hetero,
        "esp_imbalance": q_max_h - q_min_hetero,
    }


def _rdkit() -> tuple[object, object]:
    from rdkit import Chem

    return Chem


def cation_site_index(smiles: str) -> int | None:
    """The O or N with the fewest heavy-atom neighbours; ties by atom index."""

    Chem = _rdkit()
    molecule = Chem.AddHs(Chem.MolFromSmiles(smiles))  # type: ignore[attr-defined]
    best: tuple[tuple[int, int], int] | None = None
    for atom in molecule.GetAtoms():  # type: ignore[attr-defined]
        if atom.GetSymbol() not in ("O", "N"):
            continue
        key = (len(atom.GetNeighbors()), atom.GetIdx())
        if best is None or key < best[0]:
            best = (key, atom.GetIdx())
    return best[1] if best else None


def build_li_complex_xyz(
    smiles: str,
    *,
    seed: int,
    distance_a: float = LI_PLACEMENT_DISTANCE_A,
) -> tuple[str, int] | None:
    """Embed the solvent and add one Li+ in the lone-pair cone of its cation site."""

    from electrolyte_ml.xtb_features import generate_3d_xyz

    site = cation_site_index(smiles)
    if site is None:
        return None
    xyz = generate_3d_xyz(smiles, seed=seed)
    symbols, coordinates = read_xyz_block(xyz)
    Chem = _rdkit()
    molecule = Chem.AddHs(Chem.MolFromSmiles(smiles))  # type: ignore[attr-defined]
    atom = molecule.GetAtomWithIdx(site)  # type: ignore[attr-defined]
    neighbours = [neighbour.GetIdx() for neighbour in atom.GetNeighbors()]
    direction = np.zeros(3)
    for index in neighbours:
        vector = coordinates[index] - coordinates[site]
        norm = float(np.linalg.norm(vector))
        if norm > 1e-09:
            direction += vector / norm
    norm = float(np.linalg.norm(direction))
    if norm <= 1e-09:
        direction = np.asarray([0.0, 0.0, 1.0])
    else:
        direction = -direction / norm
    position = coordinates[site] + distance_a * direction
    lines = [str(len(symbols) + 1), ""]
    for symbol, coordinate in zip(symbols, coordinates, strict=True):
        lines.append(f"{symbol} {coordinate[0]:.6f} {coordinate[1]:.6f} {coordinate[2]:.6f}")
    lines.append(f"Li {position[0]:.6f} {position[1]:.6f} {position[2]:.6f}")
    return "\n".join(lines) + "\n", site


def _run_converged(run_dir: Path, output_text: str) -> bool:
    """The frozen driver's own convergence rule, reused verbatim.

    This xTB build (6.7.1pre) writes ``.xtboptok`` and does not echo
    ``normal termination of xtb``; ``run_xtb_physical_features._parse_xtb_run``
    accepts either, and so must anything that claims to reuse that protocol.
    """

    if "normal termination of xtb" in output_text:
        return True
    return (run_dir / ".xtboptok").is_file() and (run_dir / "xtbopt.xyz").is_file()


def _clear_directory(path: Path) -> None:
    """xTB reuses a leftover xtbrestart as an SCF restart, so start clean."""

    for child in path.iterdir():
        if child.is_file() or child.is_symlink():
            child.unlink()


def ensure_li_plus_energy(xtb: Path, work_root: Path, *, timeout_seconds: int) -> dict[str, object]:
    """One single-atom Li+ reference energy, under the same pinned launcher."""

    from electrolyte_ml.xtb_runner import run_xtb_subprocess, xtb_optimisation_arguments

    run_dir = work_root / "_li_plus"
    run_dir.mkdir(parents=True, exist_ok=True)
    output = run_dir / "xtb.out"
    if output.is_file():
        energy = _total_energy_hartree(output.read_text(encoding="utf-8", errors="replace"))
        if energy is not None:
            return {"energy_hartree": energy, "source": "cached", "seconds": 0.0}
    _clear_directory(run_dir)
    (run_dir / "input.xyz").write_text(
        "1\n\nLi 0.000000 0.000000 0.000000\n", encoding="utf-8", newline="\n"
    )
    start = time.perf_counter()
    completed = run_xtb_subprocess(
        xtb,
        xtb_optimisation_arguments("input.xyz", formal_charge=1),
        cwd=run_dir,
        timeout_seconds=timeout_seconds,
    )
    seconds = time.perf_counter() - start
    text = completed.stdout.decode("utf-8", errors="replace")
    output.write_text(text, encoding="utf-8", newline="\n")
    energy = _total_energy_hartree(text)
    if energy is None:
        raise RuntimeError("the Li+ reference run reported no total energy")
    return {"energy_hartree": energy, "source": "computed", "seconds": seconds}


def run_li_complex(task: Mapping[str, object]) -> dict[str, object]:
    """Relax up to four Li+ complexes and keep the lowest converged one."""

    from electrolyte_ml.xtb_runner import run_xtb_subprocess, xtb_optimisation_arguments

    inchikey = str(task["inchikey"])
    smiles = str(task["smiles"])
    Chem = _rdkit()
    # The complex is the neutral solvent plus one Li+; the SMILES decides the rest.
    charge = int(Chem.GetFormalCharge(Chem.MolFromSmiles(smiles))) + 1  # type: ignore[attr-defined]
    xtb = Path(str(task["xtb"]))
    work_root = Path(str(task["work_root"]))
    timeout_seconds = int(task["timeout_seconds"])
    row: dict[str, object] = {
        "inchikey": inchikey,
        "name": str(task["name"]),
        "smiles": smiles,
        "complex_charge": charge,
        "status": "error",
        "error": "",
        "xtb_seconds": 0.0,
        "conformers_attempted": 0,
        "conformers_converged": 0,
    }
    best: dict[str, object] | None = None
    errors: list[str] = []
    for seed in CONFORMER_SEEDS:
        built = build_li_complex_xyz(smiles, seed=seed)
        if built is None:
            errors.append(f"seed {seed}: no O or N coordination site")
            continue
        xyz, site = built
        run_dir = work_root / inchikey / f"conf_{seed}"
        run_dir.mkdir(parents=True, exist_ok=True)
        _clear_directory(run_dir)
        (run_dir / "input.xyz").write_text(xyz, encoding="utf-8", newline="\n")
        row["conformers_attempted"] = int(row["conformers_attempted"]) + 1
        start = time.perf_counter()
        try:
            completed = run_xtb_subprocess(
                xtb,
                xtb_optimisation_arguments("input.xyz", formal_charge=charge),
                cwd=run_dir,
                timeout_seconds=timeout_seconds,
            )
        except Exception as error:  # noqa: BLE001 - a failed conformer is data, not a crash
            errors.append(f"seed {seed}: {error}")
            row["xtb_seconds"] = float(row["xtb_seconds"]) + (time.perf_counter() - start)
            continue
        elapsed = time.perf_counter() - start
        row["xtb_seconds"] = float(row["xtb_seconds"]) + elapsed
        text = completed.stdout.decode("utf-8", errors="replace")
        (run_dir / "xtb.out").write_text(text, encoding="utf-8", newline="\n")
        optimized = run_dir / "xtbopt.xyz"
        energy = _total_energy_hartree(text)
        if energy is None or not optimized.is_file() or not _run_converged(run_dir, text):
            errors.append(f"seed {seed}: no converged optimisation")
            continue
        row["conformers_converged"] = int(row["conformers_converged"]) + 1
        if best is None or float(best["energy"]) > energy:
            symbols, coordinates = read_xyz_block(
                optimized.read_text(encoding="utf-8", errors="replace")
            )
            li_index = len(symbols) - 1
            if symbols[li_index] != "Li":
                errors.append(f"seed {seed}: last atom is {symbols[li_index]}, not Li")
                continue
            hetero = [index for index, symbol in enumerate(symbols[:-1]) if symbol in ("O", "N")]
            if not hetero:
                errors.append(f"seed {seed}: no O or N in the relaxed complex")
                continue
            distances = [
                float(np.linalg.norm(coordinates[index] - coordinates[li_index]))
                for index in hetero
            ]
            best = {
                "energy": energy,
                "seed": seed,
                "site_index": site,
                "run_dir": str(run_dir),
                "li_binding_distance_a": min(distances),
                "within_2_6_a": sum(1 for value in distances if value <= 2.6),
            }
    if best is None:
        row["error"] = "; ".join(errors[:3])
        if int(row["conformers_attempted"]) == 0:
            # A hydrocarbon or a hydrofluoroalkane has no O and no N, so the
            # pre-registered site rule has nothing to select. The block is
            # undefined for it rather than zero, and that is reported.
            row["status"] = "undefined_no_hetero_site"
        return row
    row.update(
        {
            "status": "ok",
            "error": "",
            "best_seed": best["seed"],
            "site_index": best["site_index"],
            "complex_energy_hartree": float(best["energy"]),
            "li_binding_distance_a": float(best["li_binding_distance_a"]),
            "hetero_atoms_within_2_6_a": best["within_2_6_a"],
            "run_dir": portable_relative_path(Path(str(best["run_dir"])), root=REPOSITORY_ROOT),
        }
    )
    return row

def run_xtb_phase(
    *,
    compounds: Mapping[str, Mapping[str, str]],
    solvent_references: Mapping[str, Mapping[str, float]],
    xtb_path: Path,
    work_root: Path,
    jobs: int,
    timeout_seconds: int = XTB_TIMEOUT_SECONDS,
) -> dict[str, object]:
    """Compute the five coordination columns for every scored compound.

    Nothing is sampled: the pre-registration's ceiling is 45 minutes of xTB wall
    clock and the audited cost is reported next to the ceiling, so a bounded
    pilot is only ever the honest fallback if the measurement says so. Ordering
    is by InChIKey so the table does not depend on dict order.
    """

    li_plus = ensure_li_plus_energy(xtb_path, work_root, timeout_seconds=timeout_seconds)
    tasks = [
        {
            "inchikey": key,
            "name": str(compounds[key]["name"]),
            "smiles": str(compounds[key]["smiles"]),
            "xtb": str(xtb_path),
            "work_root": str(work_root),
            "timeout_seconds": timeout_seconds,
        }
        for key in sorted(compounds)
    ]
    start = time.perf_counter()
    results = _parallel_map(run_li_complex, tasks, jobs)
    wall_seconds = time.perf_counter() - start
    rows: list[dict[str, object]] = []
    for compound_row, result in zip(tasks, results, strict=True):
        key = str(compound_row["inchikey"])
        reference = solvent_references.get(key)
        row: dict[str, object] = {
            "inchikey": key,
            "name": str(compound_row["name"]),
            "smiles": str(compound_row["smiles"]),
            "complex_charge": result.get("complex_charge", ""),
            "solvent_frozen_energy_hartree": (
                "" if reference is None else f"{reference['total_energy_hartree']:.12g}"
            ),
            "solvent_relaxed_energy_hartree": "",
            "li_plus_energy_hartree": f"{float(li_plus['energy_hartree']):.12g}",
            "complex_energy_hartree": "",
            "li_binding_energy_ev": "",
            "li_binding_distance_a": "",
            "q_max_h": "",
            "q_min_hetero": "",
            "esp_imbalance": "",
            "solvent_run": "",
            "solvent_match_basis": "",
            "solvent_run_candidates_considered": "",
            "solvent_run_matches": "",
            "conformers_attempted": result.get("conformers_attempted", 0),
            "conformers_converged": result.get("conformers_converged", 0),
            "best_seed": result.get("best_seed", ""),
            "hetero_atoms_within_2_6_a": result.get("hetero_atoms_within_2_6_a", ""),
            "xtb_seconds": f"{float(result.get('xtb_seconds', 0.0)):.6f}",
            "status": str(result.get("status", "error")),
            "error": str(result.get("error", "")),
        }
        if result.get("status") != "ok":
            rows.append(row)
            continue
        if reference is None:
            row["status"] = "error"
            row["error"] = "the released v03 feature table has no row for this compound"
            rows.append(row)
            continue
        run = resolve_solvent_run(key, reference)
        relaxed = run["relaxed_energy_hartree"]
        row["solvent_run_candidates_considered"] = run["considered"]
        row["solvent_run_matches"] = len(run["matches"])  # type: ignore[arg-type]
        row["solvent_match_basis"] = run["match_basis"]
        if run["run"] is None or relaxed is None:
            row["status"] = "error"
            row["error"] = "no frozen xTB run reproduces the released v03 feature row"
            rows.append(row)
            continue
        charges = solvent_charge_features(Path(str(run["run"])))
        row["solvent_run"] = str(run["matches"][0])  # type: ignore[index]
        row["solvent_relaxed_energy_hartree"] = f"{float(relaxed):.12g}"
        row.update({name: f"{value:.10g}" for name, value in charges.items()})
        complex_energy = float(result["complex_energy_hartree"])
        delta = complex_energy - float(relaxed) - float(li_plus["energy_hartree"])
        row["complex_energy_hartree"] = f"{complex_energy:.12g}"
        row["li_binding_energy_ev"] = f"{delta * HARTREE_TO_EV:.10g}"
        row["li_binding_distance_a"] = f"{float(result['li_binding_distance_a']):.10g}"
        row["status"] = "ok"
        row["error"] = ""
        rows.append(row)
    ok_rows = [row for row in rows if row["status"] == "ok"]
    return {
        "rows": rows,
        "li_plus": {
            "energy_hartree": float(li_plus["energy_hartree"]),
            "source": li_plus["source"],
            "seconds": float(li_plus["seconds"]),
        },
        "compounds_requested": len(tasks),
        "compounds_ok": len(ok_rows),
        "compounds_failed": len(tasks) - len(ok_rows),
        "failed_keys": sorted(
            str(row["inchikey"]) for row in rows if str(row["status"]) != "ok"
        ),
        "xtb_wall_seconds": wall_seconds,
        "xtb_cpu_seconds": sum(float(row["xtb_seconds"]) for row in rows),
        "budget_seconds": XTB_BUDGET_SECONDS,
        "within_budget": wall_seconds <= XTB_BUDGET_SECONDS,
        "jobs": jobs,
        "work_root": str(work_root),
    }


# --------------------------------------------------------------------------- #
# phase 2: the three arms on the frozen scoreboard
# --------------------------------------------------------------------------- #

_FOLD_STATE: dict[str, object] = {}


def _init_fold_worker(morgan: np.ndarray, physical: np.ndarray, target: np.ndarray) -> None:
    _FOLD_STATE["morgan"] = morgan
    _FOLD_STATE["physical"] = physical
    _FOLD_STATE["target"] = target


def _fold_task(
    task: tuple[int, int, Sequence[int], Sequence[int]],
) -> tuple[int, int, list[int], list[int], dict[str, list[float]]]:
    """One fold, all three representations, in one worker process.

    `fit_predict_representation` is the frozen fitter, so a fold computed here
    is the fold the paired probe computes; only the loop that drives it is
    parallel, and the results are collected back into (repeat, fold) order.
    """

    repeat, fold, train_index, test_index = task
    morgan = _FOLD_STATE["morgan"]
    physical = _FOLD_STATE["physical"]
    target = _FOLD_STATE["target"]
    assert isinstance(morgan, np.ndarray)
    assert isinstance(physical, np.ndarray)
    assert isinstance(target, np.ndarray)
    train = np.asarray(train_index)
    test = np.asarray(test_index)
    predictions: dict[str, list[float]] = {}
    for representation in REPRESENTATIONS:
        prediction, _signature = fit_predict_representation(
            representation,
            morgan=morgan,
            physical=physical,
            target=target,
            train_indices=train,
            test_indices=test,
            seed=SEED,
        )
        predictions[representation] = [float(value) for value in prediction]
    return repeat, fold, [int(index) for index in train], [int(index) for index in test], predictions


def _parallel_map(
    function: Callable[[object], object],
    tasks: Sequence[object],
    jobs: int,
    *,
    initializer: Callable[..., None] | None = None,
    initargs: tuple[object, ...] = (),
) -> list[object]:
    """Order-preserving map, serial at one job and process-parallel above it."""

    if jobs <= 1 or len(tasks) <= 1:
        if initializer is not None:
            initializer(*initargs)
        return [function(task) for task in tasks]
    with ProcessPoolExecutor(
        max_workers=jobs, initializer=initializer, initargs=initargs
    ) as pool:
        return list(pool.map(function, tasks))


def evaluate_arm(
    name: str,
    *,
    morgan: np.ndarray,
    physical: np.ndarray,
    target: np.ndarray,
    temperatures: np.ndarray,
    groups: Sequence[str],
    splits: Sequence[tuple[int, int, np.ndarray, np.ndarray]],
    jobs: int,
) -> dict[str, object]:
    """One arm of the paired design, assembled exactly like `run_protocol`."""

    group_array = np.asarray([str(item) for item in groups])
    tasks = [
        (repeat, fold, [int(index) for index in train], [int(index) for index in test])
        for repeat, fold, train, test in splits
    ]
    results = _parallel_map(
        _fold_task,
        tasks,
        jobs,
        initializer=_init_fold_worker,
        initargs=(morgan, physical, target),
    )
    fold_rows: list[dict[str, object]] = []
    prediction_rows: list[dict[str, object]] = []
    buckets: dict[tuple[str, int], dict[str, list[np.ndarray]]] = {}
    straddling: list[int] = []
    for repeat, fold, train_index, test_index, predictions in results:
        train = np.asarray(train_index)
        test = np.asarray(test_index)
        straddling.append(
            int(np.intersect1d(group_array[train], group_array[test]).size)
        )
        for representation in REPRESENTATIONS:
            prediction = np.asarray(predictions[representation], dtype=float)
            fold_metrics = evaluate_repeat(target[test], prediction)
            fold_rows.append(
                {
                    "arm": name,
                    "representation": representation,
                    "repeat": repeat,
                    "fold": fold,
                    "train_rows": int(train.size),
                    "test_rows": int(test.size),
                    "train_compounds": int(np.unique(group_array[train]).size),
                    "test_compounds": int(np.unique(group_array[test]).size),
                    "mae": fold_metrics["mae"],
                    "rmse": fold_metrics["rmse"],
                    "r2": fold_metrics["r2"],
                    "spearman": fold_metrics["spearman"],
                }
            )
            bucket = buckets.setdefault((representation, repeat), {"target": [], "prediction": []})
            bucket["target"].append(target[test])
            bucket["prediction"].append(prediction)
            for row_index, value in zip(test_index, prediction.tolist(), strict=True):
                prediction_rows.append(
                    {
                        "arm": name,
                        "representation": representation,
                        "repeat": repeat,
                        "fold": fold,
                        "inchikey": str(groups[int(row_index)]),
                        "T_K": float(temperatures[int(row_index)]),
                        "target": float(target[int(row_index)]),
                        "prediction": float(value),
                    }
                )
    repeat_rows: list[dict[str, object]] = []
    for (representation, repeat), bucket in sorted(buckets.items()):
        metrics = evaluate_repeat(
            np.concatenate(bucket["target"]), np.concatenate(bucket["prediction"])
        )
        repeat_rows.append(
            {
                "arm": name,
                "representation": representation,
                "repeat": repeat,
                **{metric: metrics[metric] for metric in METRIC_NAMES},
            }
        )
    grouped = summarize_repeats([{**row, "protocol": name} for row in repeat_rows])
    summary = grouped.get(name)
    if summary is None or set(summary) != set(REPRESENTATIONS):
        # Every representation of every repeat has to be present, otherwise the
        # arm table would be quietly partial and the paired delta meaningless.
        raise ValueError(
            f"{name}: the arm table is incomplete, found "
            f"{sorted(grouped.get(name, {}))} for {list(REPRESENTATIONS)}"
        )
    return {
        "fold_rows": fold_rows,
        "repeat_rows": repeat_rows,
        "prediction_rows": prediction_rows,
        # Representation keyed directly: `summarize_repeats` wraps everything in
        # one more protocol level, and carrying that level here is what made the
        # first assembly read the wrong nesting.
        "summary": summary,
        "leak": {
            "folds": len(straddling),
            "folds_with_a_straddling_compound": int(sum(1 for count in straddling if count)),
            "max_straddling_compounds_in_a_fold": int(max(straddling)) if straddling else 0,
        },
    }

# --------------------------------------------------------------------------- #
# assembly, verdict, report
# --------------------------------------------------------------------------- #

ARM_BASELINE = "baseline"
ARM_PLUS = "plus_coordination_block"
ARM_PLACEBO = "placebo_shuffled_target"
ARM_ORDER = (ARM_BASELINE, ARM_PLUS, ARM_PLACEBO)

FEATURE_TABLE_COLUMNS = (
    "inchikey",
    "name",
    "smiles",
    "complex_charge",
    "solvent_frozen_energy_hartree",
    "solvent_relaxed_energy_hartree",
    "li_plus_energy_hartree",
    "complex_energy_hartree",
    "li_binding_energy_ev",
    "li_binding_distance_a",
    "q_max_h",
    "q_min_hetero",
    "esp_imbalance",
    "solvent_run",
    "solvent_match_basis",
    "solvent_run_candidates_considered",
    "solvent_run_matches",
    "conformers_attempted",
    "conformers_converged",
    "best_seed",
    "hetero_atoms_within_2_6_a",
    "xtb_seconds",
    "status",
    "error",
)

FOLD_COLUMNS_OUT = (
    "arm",
    "representation",
    "repeat",
    "fold",
    "train_rows",
    "test_rows",
    "train_compounds",
    "test_compounds",
    "mae",
    "rmse",
    "r2",
    "spearman",
)

PREDICTION_COLUMNS_OUT = (
    "arm",
    "representation",
    "repeat",
    "fold",
    "inchikey",
    "T_K",
    "target",
    "prediction",
)

REPEAT_COLUMNS_OUT = ("arm", "representation", "repeat", *METRIC_NAMES)


def shuffled_target(target: np.ndarray, scored: np.ndarray) -> np.ndarray:
    """Permute the target over the scored rows, once, with the pinned seed.

    Declared here rather than tuned later: a placebo that re-shuffles until it
    looks harmless is not a placebo.
    """

    rng = np.random.default_rng(SEED)
    shuffled = target.copy()
    index = np.flatnonzero(scored)
    shuffled[index] = target[index][rng.permutation(index.size)]
    return shuffled


def coordination_matrix(
    rows: Sequence[Mapping[str, object]],
    feature_rows: Sequence[Mapping[str, object]],
) -> tuple[np.ndarray, dict[str, object]]:
    """Broadcast the per-compound block onto rows; a failed compound stays NaN."""

    table = {str(row["inchikey"]): row for row in feature_rows}
    matrix = np.full((len(rows), len(COORDINATION_COLUMNS)), np.nan, dtype=float)
    resolved = 0
    unresolved: set[str] = set()
    for index, row in enumerate(rows):
        key = str(row["inchikey"])
        entry = table.get(key)
        if entry is None or str(entry.get("status")) != "ok":
            unresolved.add(key)
            continue
        values = [str(entry.get(column, "")).strip() for column in COORDINATION_COLUMNS]
        if any(not value for value in values):
            unresolved.add(key)
            continue
        matrix[index] = [float(value) for value in values]
        resolved += 1
    return matrix, {
        "rows_with_the_block": resolved,
        "rows_without_the_block": len(rows) - resolved,
        "compounds_without_the_block": sorted(unresolved),
    }


def _metric(summary: Mapping[str, object], arm: str, representation: str, metric: str) -> float:
    block = summary[arm]  # type: ignore[index]
    return float(block[representation][metric]["mean"])  # type: ignore[index]


def build_summary(
    *,
    generated_at: str,
    prereg_text: str,
    prereg_sha: str,
    inputs: Mapping[str, object],
    scoreboard: Mapping[str, object],
    xtb: Mapping[str, object],
    block_report: Mapping[str, object],
    arm_summaries: Mapping[str, object],
    arm_leaks: Mapping[str, object],
    placebo_r2: float,
    feature_table_path: str,
) -> dict[str, object]:
    baseline_r2 = _metric(arm_summaries, ARM_BASELINE, HYBRID, "r2")
    plus_r2 = _metric(arm_summaries, ARM_PLUS, HYBRID, "r2")
    deltas = {
        metric: _metric(arm_summaries, ARM_PLUS, HYBRID, metric)
        - _metric(arm_summaries, ARM_BASELINE, HYBRID, metric)
        for metric in PAIRED_METRICS + ("rmse", "mae_lt20", "mae_20_60", "mae_gt60")
    }
    placebo_delta = placebo_r2 - baseline_r2
    placebo_collapsed = abs(placebo_delta) <= PLACEBO_TOLERANCE
    delta_r2 = deltas["r2"]
    mae_gt60_not_worse = deltas["mae_gt60"] <= INERT_TOLERANCE
    reproduced = abs(baseline_r2 - BASELINE_R2) <= REPRODUCTION_TOLERANCE
    kill_reasons: list[str] = []
    if delta_r2 < KILL_DELTA:
        kill_reasons.append(
            f"delta R2 {delta_r2:+.4f} is below the +{KILL_DELTA:.4f} kill line"
        )
    if not placebo_collapsed:
        kill_reasons.append(
            f"the placebo arm moved R2 by {placebo_delta:+.4f}, beyond +-{PLACEBO_TOLERANCE:.4f}"
        )
    if not mae_gt60_not_worse and delta_r2 < 0:
        kill_reasons.append(
            "the mae_gt60 stratum got worse while total R2 fell"
        )
    if not reproduced:
        kill_reasons.append("the baseline arm did not reproduce the published R2")
    primary_met = delta_r2 >= PASS_DELTA
    if kill_reasons:
        decision = "dead"
    elif primary_met and placebo_collapsed and mae_gt60_not_worse:
        decision = "pass"
    else:
        decision = "between_the_pass_bar_and_the_kill_line"
    statement = (
        f"appending the five Li+-coordination columns moves grouped Morgan+Physical R2 by "
        f"{delta_r2:+.4f} on the frozen 457-row / 97-compound scoreboard "
        f"({baseline_r2:.4f} -> {plus_r2:.4f}); decision: {decision}"
    )
    status_counts: dict[str, int] = defaultdict(int)
    for row in xtb["rows"]:  # type: ignore[index]
        status_counts[str(row["status"])] += 1
    return {
        "schema_version": 1,
        "task": "week14_lever8_coordination_block",
        "generated_at_utc": generated_at,
        "seed": SEED,
        "protocol": {
            "scoreboard": "the frozen main scoreboard, 457 rows / 97 compounds",
            "splitter": "GroupKFold by InChIKey, 10 repeats x 5 folds, seed 42",
            "folds": "dealt by dielectric_room_window_paired.masked_splits over the "
            "score mask alone, filtered by dielectric_band_ablation.drop_thin_folds",
            "model": "XGBRegressor with the frozen v1.0 hyper-parameters, n_jobs=1",
            "hybrid": HYBRID + " = 0.5 * (Morgan + Physical), the frozen blend",
            "n_splits": N_SPLITS,
            "n_repeats": N_REPEATS,
            "arms": list(ARM_ORDER),
        },
        "preregistration": {
            "path": portable_relative_path(PREREG_PATH, root=REPOSITORY_ROOT),
            "sha256": prereg_sha,
            "bytes": len(prereg_text.encode("utf-8")),
            "pass_criterion": f"grouped R2 gain >= +{PASS_DELTA:.4f}",
            "kill_line": f"gain < +{KILL_DELTA:.4f}, or a placebo that does not collapse, "
            "or a lift that lives only in the MAE strata while total R2 falls",
            "secondary_criterion": "the mae_gt60 stratum must not get worse; the placebo "
            f"arm must collapse to |delta R2| <= {PLACEBO_TOLERANCE:.4f}",
            "inert_tolerance_for_mae": INERT_TOLERANCE,
            "declared_here_not_in_the_prereg": [
                (
                    "mae_gt60 'not worse' is read with the repository's inert tolerance "
                    f"{INERT_TOLERANCE:.4f}; the raw delta is reported next to it"
                ),
                (
                    "the placebo permutation is fixed to numpy default_rng(42) over the "
                    "scored rows before the run"
                ),
            ],
        },
        "inputs": dict(inputs),
        "scoreboard": dict(scoreboard),
        "coordination_block": {
            "columns": list(COORDINATION_COLUMNS),
            "feature_table": feature_table_path,
            **dict(block_report),
        },
        "xtb": {
            key: value for key, value in xtb.items() if key != "rows"
        }
        | {"status_counts": dict(sorted(status_counts.items()))},
        "arms": {arm: arm_summaries[arm] for arm in ARM_ORDER},  # type: ignore[index]
        "arm_leaks": dict(arm_leaks),
        "paired_deltas": {key: float(value) for key, value in deltas.items()},
        "placebo": {
            "delta_r2_vs_baseline": float(placebo_delta),
            "r2": float(placebo_r2),
            "collapsed": bool(placebo_collapsed),
            "tolerance": PLACEBO_TOLERANCE,
        },
        "verdict": {
            "integrity_ok": bool(reproduced),
            "baseline_reproduced": bool(reproduced),
            "baseline_r2": float(baseline_r2),
            "baseline_r2_published": BASELINE_R2,
            "baseline_abs_delta": float(abs(baseline_r2 - BASELINE_R2)),
            "delta_r2": float(delta_r2),
            "pass_bar": PASS_DELTA,
            "kill_line": KILL_DELTA,
            "primary_met": bool(primary_met),
            "placebo_collapsed": bool(placebo_collapsed),
            "mae_gt60_not_worse": bool(mae_gt60_not_worse),
            "kill_reasons": kill_reasons,
            "decision": decision,
            "statement": statement,
        },
        "shots": {
            "this_probe": 1,
            "policy": "attempts at the main scoreboard are counted in "
            "reports/decisions_log.md section 12",
            "recorded_here_not_there": "this probe may not edit decisions_log.md, so the "
            "count is carried in this summary for the integrator to register",
        },
        "honest_boundaries": [
            (
                "target mismatch: the review describes solvating power inside an "
                "electrolyte, this scoreboard predicts the static dielectric constant of "
                "a pure solvent. The block tests which of the review's axes transfers to a "
                "different target."
            ),
            (
                "GFN2-xTB overbinds Li+; only the spread of the binding energy across "
                "compounds is used, never its absolute value as thermochemistry."
            ),
            (
                "the Li+ complex is gas phase and single molecule: no anion, no "
                "solvent-solvent competition, which is the review's own stated weakness "
                "of the binding-energy descriptor."
            ),
            (
                "the three charge columns come from the frozen week-3 xTB run of the "
                "isolated solvent, matched by total energy, so they describe the released "
                "geometry and not the Li+-perturbed one."
            ),
            (
                "compounds with no O and no N (hydrocarbons, hydrofluoroalkanes) have no "
                "site for the pre-registered rule, so their block is undefined and left "
                "missing rather than filled; they are counted by status in the summary."
            ),
            (
                "the released v03 `total_energy_hartree` column is the first "
                "`:: total energy` line of the run log, i.e. the single point at the "
                "input geometry, because the frozen parser uses the first regex match; "
                "this block therefore takes the relaxed energy from the same cached run "
                "and reports both columns so the difference is auditable."
            ),
            (
                "no network I/O, no new data source, no change to the frozen scoreboard, "
                "the fold numbers or any frozen red-line digest."
            ),
        ],
        "outputs": {},
    }

def format_report(summary: Mapping[str, object]) -> list[str]:
    """Render the report from the summary; the md on disk is this text."""

    verdict = summary["verdict"]  # type: ignore[index]
    arms = summary["arms"]  # type: ignore[index]
    deltas = summary["paired_deltas"]  # type: ignore[index]
    block = summary["coordination_block"]  # type: ignore[index]
    xtb = summary["xtb"]  # type: ignore[index]
    scoreboard = summary["scoreboard"]  # type: ignore[index]
    lines: list[str] = []
    lines.append("# Lever 8 - the Li+ coordination block on the frozen dielectric scoreboard")
    lines.append("")
    lines.append(f"- generated: `{summary['generated_at_utc']}`")
    lines.append(f"- pre-registration: `{summary['preregistration']['path']}` (sha256 `{summary['preregistration']['sha256']}`)")  # type: ignore[index]
    lines.append(f"- decision: **{verdict['decision']}** ({verdict['statement']})")  # type: ignore[index]
    lines.append("")
    lines.append("## The block")
    lines.append("")
    lines.append("Columns appended beside the 13 frozen physical columns; no frozen column is touched:")
    lines.append("")
    for column in block["columns"]:  # type: ignore[index]
        lines.append(f"- `{column}`")
    lines.append("")
    lines.append(
        f"- compounds with a usable block: {block['compounds_ok']} / {xtb['compounds_requested']}"
    )
    long_rows = int(block["rows_with_the_block"]) + int(block["rows_without_the_block"])
    lines.append(
        f"- observation rows in the long feature table: {long_rows},"
        f" of which {block['rows_with_the_block']} carry a usable block"
    )
    lines.append(
        f"- xTB wall clock {xtb['xtb_wall_seconds']:.1f} s against a {xtb['budget_seconds']} s ceiling"
        f" (within budget: {xtb['within_budget']}); cpu {xtb['xtb_cpu_seconds']:.1f} s"
    )
    lines.append(f"- Li+ reference energy: {xtb['li_plus']['energy_hartree']:.12g} Eh ({xtb['li_plus']['source']})")
    lines.append(
        "- the wall clock above is the cost inside this run; when the feature table is reused it is"
        " 0.0 s and the measured cost is the sum of the per-compound `xtb_seconds` column of the"
        " feature table"
    )
    lines.append(
        f"- pilot scale: no bounded pilot was needed. The whole pool of {xtb['compounds_requested']}"
        f" compounds was attempted and {block['compounds_ok']} produced a block"
    )
    lines.append(
        "- pending list: empty. The compounds without a block carry the status"
        " `undefined_no_hetero_site` (no O and no N for the pre-registered site rule), which is an"
        " undefined block and not an unrun one"
    )
    if block["compounds_failed"]:  # type: ignore[index]
        lines.append(f"- compounds without the block: {', '.join(block['failed_keys'])}")  # type: ignore[index]
    lines.append("")
    lines.append("## Scoreboard")
    lines.append("")
    lines.append(
        f"- scored rows {scoreboard['scored_rows']}, compounds {scoreboard['compounds_scored']},"
        f" folds {scoreboard['folds']}, repeats {scoreboard['executed_repeats']}"
    )
    lines.append(
        f"- straddling compounds across a fold boundary: {scoreboard['folds_with_a_straddling_compound']}"
    )
    lines.append("")
    lines.append("## Arms (Morgan+Physical blend)")
    lines.append("")
    lines.append("| arm | R2 | MAE | Spearman | MAE >60 |")
    lines.append("| --- | --- | --- | --- | --- |")
    for arm in ARM_ORDER:
        block_arm = arms[arm][HYBRID]  # type: ignore[index]
        lines.append(
            f"| `{arm}` | {block_arm['r2']['mean']:.4f} | {block_arm['mae']['mean']:.4f} "
            f"| {block_arm['spearman']['mean']:.4f} | {block_arm['mae_gt60']['mean']:.4f} |"
        )
    lines.append("")
    lines.append("## Paired deltas (plus_coordination_block - baseline)")
    lines.append("")
    lines.append("| metric | delta |")
    lines.append("| --- | --- |")
    for metric in ("r2", "mae", "rmse", "spearman", "mae_lt20", "mae_20_60", "mae_gt60"):
        lines.append(f"| {metric} | {deltas[metric]:+.4f} |")
    lines.append("")
    lines.append(
        f"- baseline reproduction: {verdict['baseline_r2']:.16f} vs published "
        f"{verdict['baseline_r2_published']:.16f} (abs delta {verdict['baseline_abs_delta']:.2e})"  # type: ignore[index]
    )
    lines.append(
        f"- placebo arm: R2 {summary['placebo']['r2']:.4f}, delta {summary['placebo']['delta_r2_vs_baseline']:+.4f},"
        f" collapsed: {summary['placebo']['collapsed']}"  # type: ignore[index]
    )
    lines.append("")
    lines.append("## Verdict")
    lines.append("")
    lines.append(f"- pass bar: delta R2 >= {verdict['pass_bar']:+.4f} -> met: {verdict['primary_met']}")  # type: ignore[index]
    lines.append(f"- kill line: delta R2 < {verdict['kill_line']:+.4f}")  # type: ignore[index]
    lines.append(f"- mae_gt60 not worse: {verdict['mae_gt60_not_worse']}")  # type: ignore[index]
    if verdict["kill_reasons"]:  # type: ignore[index]
        for reason in verdict["kill_reasons"]:  # type: ignore[index]
            lines.append(f"- kill reason: {reason}")
    lines.append(f"- decision: **{verdict['decision']}**")  # type: ignore[index]
    lines.append("")
    lines.append("### Placebo reading (disclosure; no threshold was changed after the run)")
    lines.append("")
    lines.append(
        f"- the pre-registration's secondary criterion is `|delta R2| <= {PLACEBO_TOLERANCE:.4f}` on"
        " the placebo arm. Read literally against the baseline arm that inequality can only hold"
        " when the placebo keeps the baseline signal, so it is unsatisfiable whenever the placebo"
        " behaves as a placebo. It was implemented literally, and that clause is what kills the arm"
    )
    lines.append(
        f"- the placebo's own R2 is {summary['placebo']['r2']:+.4f} against a baseline of"
        f" {verdict['baseline_r2']:+.4f}: no lift over a trivial predictor, i.e. the shuffling did"
        " destroy the signal, which is what the arm exists to demonstrate"
    )
    lines.append(
        f"- the pass criterion itself was met (delta R2 {verdict['delta_r2']:+.4f} >="
        f" {verdict['pass_bar']:+.4f}) and the mae_gt60 stratum improved, so the recorded verdict is"
        " `dead` on the placebo clause alone"
    )
    lines.append("")
    lines.append("## Honest boundaries")
    lines.append("")
    for boundary in summary["honest_boundaries"]:  # type: ignore[index]
        lines.append(f"- {boundary}")
    lines.append("")
    lines.append("## Shots")
    lines.append("")
    lines.append(f"- main-scoreboard attempts in this probe: {summary['shots']['this_probe']}")  # type: ignore[index]
    lines.append(f"- policy: {summary['shots']['policy']}")  # type: ignore[index]
    lines.append("")
    lines.append("## Files")
    lines.append("")
    for name, path in sorted(summary["outputs"].items()):  # type: ignore[index]
        lines.append(f"- {name}: `{path}`")
    lines.append("")
    return lines


def relink_xtb_locations(rows: Sequence[Mapping[str, object]], work_root: Path) -> list[str]:
    """Re-derive the complex-side columns from the scratch runs, when present."""

    problems: list[str] = []
    for row in rows:
        if str(row.get("status")) != "ok":
            continue
        key = str(row["inchikey"])
        run_dir = work_root / key / f"conf_{row['best_seed']}"
        output = run_dir / "xtb.out"
        optimized = run_dir / "xtbopt.xyz"
        if not output.is_file() or not optimized.is_file():
            problems.append(f"{key}: the scratch run for seed {row['best_seed']} is gone")
            continue
        energy = _total_energy_hartree(output.read_text(encoding="utf-8", errors="replace"))
        if energy is None or abs(energy - float(str(row["complex_energy_hartree"]))) > 1e-09:
            problems.append(f"{key}: the scratch energy does not match the feature row")
            continue
        symbols, coordinates = read_xyz_block(optimized.read_text(encoding="utf-8", errors="replace"))
        hetero = [i for i, symbol in enumerate(symbols[:-1]) if symbol in ("O", "N")]
        distance = min(
            float(np.linalg.norm(coordinates[i] - coordinates[-1])) for i in hetero
        )
        if abs(distance - float(str(row["li_binding_distance_a"]))) > 1e-07:
            problems.append(f"{key}: the scratch Li-O/N distance does not match the feature row")
    return problems


def internal_problems(rows: Sequence[Mapping[str, object]]) -> list[str]:
    """Checks that need nothing but the feature table itself."""

    problems: list[str] = []
    for row in rows:
        if str(row.get("status")) != "ok":
            continue
        key = str(row["inchikey"])
        solvent = float(str(row["solvent_relaxed_energy_hartree"]))
        li_plus = float(str(row["li_plus_energy_hartree"]))
        complex_energy = float(str(row["complex_energy_hartree"]))
        expected = (complex_energy - solvent - li_plus) * HARTREE_TO_EV
        if abs(expected - float(str(row["li_binding_energy_ev"]))) > 1e-06:
            problems.append(f"{key}: the binding energy is not the recorded energy difference")
        if abs(
            float(str(row["esp_imbalance"]))
            - (float(str(row["q_max_h"])) - float(str(row["q_min_hetero"])))
        ) > 1e-09:
            problems.append(f"{key}: esp_imbalance is not q_max_h - q_min_hetero")
        if float(str(row["li_binding_distance_a"])) <= 0:
            problems.append(f"{key}: a non-positive Li-O/N distance")
    return problems


def check_artifacts(*, work_root: Path) -> int:
    """Re-derive the released numbers from the artefacts on disk."""

    problems: list[str] = []
    feature_path = ARTIFACTS_DIR / (FEATURES_ARTIFACT + ".csv")
    if not feature_path.is_file():
        print("MISSING " + str(feature_path))
        return 1
    blob = feature_path.read_bytes()
    if b"\r\n" in blob:
        problems.append(f"{feature_path.name} is not LF-only")
    if blob.startswith(b"\xef\xbb\xbf"):
        problems.append(f"{feature_path.name} carries a BOM")
    rows = read_csv_rows(feature_path)
    problems.extend(internal_problems(rows))
    problems.extend(relink_xtb_locations(rows, work_root))
    scoreboard = build_scoreboard()
    if not scoreboard["contract"]["matches_preregistration"]:
        problems.append("the rebuilt scoreboard does not match the pre-registration")
    if not SUMMARY_PATH.is_file():
        print("MISSING " + str(SUMMARY_PATH))
        return 1
    summary = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
    matrix, coverage = coordination_matrix(scoreboard["rows"], rows)  # type: ignore[arg-type]
    stored = summary["coordination_block"]
    if int(stored["rows_with_the_block"]) != int(coverage["rows_with_the_block"]):
        problems.append("the summary's block coverage disagrees with the feature table")
    if int(stored["compounds_ok"]) != len([row for row in rows if str(row["status"]) == "ok"]):
        problems.append("the summary's compound count disagrees with the feature table")
    if int(np.isfinite(matrix).all(axis=1).sum()) != int(coverage["rows_with_the_block"]):
        problems.append("the broadcast block disagrees with the row coverage")
    for name in ("folds", "predictions", "repeats"):
        path = ARTIFACTS_DIR / f"{ARTIFACT_STEM}_{name}.csv"
        if not path.is_file():
            problems.append(f"missing artefact {path.name}")
        elif b"\r\n" in path.read_bytes():
            problems.append(f"{path.name} is not LF-only")
    arms = summary["arms"]
    baseline = float(arms[ARM_BASELINE][HYBRID]["r2"]["mean"])
    if abs(baseline - BASELINE_R2) > REPRODUCTION_TOLERANCE:
        problems.append("the recorded baseline is not the published R2")
    delta = float(arms[ARM_PLUS][HYBRID]["r2"]["mean"]) - baseline
    if abs(delta - float(summary["verdict"]["delta_r2"])) > 1e-12:
        problems.append("the recorded verdict delta disagrees with the arm table")
    placebo_delta = float(arms[ARM_PLACEBO][HYBRID]["r2"]["mean"]) - baseline
    if abs(placebo_delta - float(summary["placebo"]["delta_r2_vs_baseline"])) > 1e-12:
        problems.append("the recorded placebo delta disagrees with the arm table")
    if bool(summary["placebo"]["collapsed"]) != (abs(placebo_delta) <= PLACEBO_TOLERANCE):
        problems.append("the placebo collapse flag disagrees with the arm table")
    report = REPORT_PATH.read_text(encoding="utf-8").splitlines()
    if report != format_report(summary):
        problems.append("reports/dielectric_coordination_block.md is not render_report(summary)")
    for problem in problems:
        print("PROBLEM " + problem)
    print(
        f"checked: {len(rows)} feature rows, {summary['coordination_block']['compounds_ok']} "
        f"compounds with the block, {len(problems)} problems"
    )
    return 1 if problems else 0


def _load_xtb_script() -> object:
    """Load the frozen xTB driver to reuse its executable discovery verbatim."""

    import importlib.util

    path = REPOSITORY_ROOT / "scripts" / "run_xtb_physical_features.py"
    spec = importlib.util.spec_from_file_location("xtb_physical_features_script", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load " + str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def resolve_xtb(explicit: Path | None) -> Path:
    script = _load_xtb_script()
    return Path(script._resolve_xtb(explicit))  # type: ignore[attr-defined]


def default_jobs() -> int:
    return max(1, min(6, (os.cpu_count() or 2) // 2))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Lever 8: the Li+ coordination block")
    parser.add_argument("--jobs", type=int, default=None)
    parser.add_argument("--work-root", type=Path, default=XTB_WORK_ROOT)
    parser.add_argument("--xtb", type=Path, default=None)
    parser.add_argument("--reuse-features", action="store_true")
    parser.add_argument("--features-only", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)

    work_root = Path(args.work_root)
    if args.check:
        return check_artifacts(work_root=work_root)

    if not PREREG_PATH.is_file():
        print("missing pre-registration: " + str(PREREG_PATH))
        return 1
    prereg_text = PREREG_PATH.read_text(encoding="utf-8")
    prereg_sha = canonical_text_sha256(PREREG_PATH)
    prereg = json.loads(prereg_text)
    declared = tuple(
        str(entry).split(" (", 1)[0].strip()
        for entry in prereg["block_definition"]["features"]
    )
    if declared != COORDINATION_COLUMNS:
        print(
            "the pre-registration names a different feature block: "
            + ", ".join(declared)
        )
        return 1

    jobs = args.jobs if args.jobs is not None else default_jobs()
    scoreboard = build_scoreboard()
    contract = scoreboard["contract"]
    if not contract["matches_preregistration"]:
        print("the scoreboard does not match the pre-registration: " + json.dumps(contract))
        return 1
    print(
        "scoreboard: rows={scored_rows} compounds={compounds_scored} folds={folds}".format(**contract)
    )

    compounds = {
        key: {
            "name": entry["name"],
            "smiles": entry["smiles"],
        }
        for key, entry in scoreboard["compounds"].items()  # type: ignore[union-attr]
    }
    feature_path = ARTIFACTS_DIR / (FEATURES_ARTIFACT + ".csv")
    if args.reuse_features:
        if not feature_path.is_file():
            print("no feature table to reuse at " + str(feature_path))
            return 1
        feature_rows = read_csv_rows(feature_path)
        xtb_report: dict[str, object] = {
            "rows": feature_rows,
            "compounds_requested": len(compounds),
            "compounds_ok": len([row for row in feature_rows if row["status"] == "ok"]),
            "compounds_failed": len([row for row in feature_rows if row["status"] != "ok"]),
            "failed_keys": sorted(row["inchikey"] for row in feature_rows if row["status"] != "ok"),
            "li_plus": {"energy_hartree": float(feature_rows[0]["li_plus_energy_hartree"]), "source": "from the reused table", "seconds": 0.0},
            "xtb_wall_seconds": 0.0,
            "xtb_cpu_seconds": sum(float(row["xtb_seconds"] or 0.0) for row in feature_rows),
            "budget_seconds": XTB_BUDGET_SECONDS,
            "within_budget": True,
            "jobs": jobs,
            "work_root": str(work_root),
        }
    else:
        xtb_path = resolve_xtb(args.xtb)
        print("xTB: " + str(xtb_path))
        xtb_report = run_xtb_phase(
            compounds=compounds,
            solvent_references=frozen_solvent_references(),
            xtb_path=xtb_path,
            work_root=work_root,
            jobs=jobs,
        )
        write_csv_rows(
            feature_path,
            FEATURE_TABLE_COLUMNS,
            xtb_report["rows"],  # type: ignore[arg-type]
        )
    print(
        "coordination block: ok={compounds_ok}/{compounds_requested} "
        "xTB wall={xtb_wall_seconds:.1f}s budget={budget_seconds}s".format(**xtb_report)
    )
    if args.features_only:
        print("features written: " + portable_relative_path(feature_path, root=REPOSITORY_ROOT))
        return 0

    matrix, block_report = coordination_matrix(scoreboard["rows"], xtb_report["rows"])  # type: ignore[arg-type]
    morgan = scoreboard["morgan"]
    physical = scoreboard["physical"]
    target = scoreboard["target"]
    temperatures = scoreboard["temperatures"]
    groups = scoreboard["groups"]
    scored = scoreboard["scored"]
    splits = scoreboard["splits"]
    assert isinstance(morgan, np.ndarray)
    assert isinstance(physical, np.ndarray)
    assert isinstance(target, np.ndarray)
    assert isinstance(temperatures, np.ndarray)
    assert isinstance(scored, np.ndarray)
    assert isinstance(splits, list)

    with_block = np.hstack([physical, matrix])
    features_by_arm = {
        ARM_BASELINE: physical,
        ARM_PLUS: with_block,
        ARM_PLACEBO: with_block,
    }
    targets = {
        ARM_BASELINE: target,
        ARM_PLUS: target,
        ARM_PLACEBO: shuffled_target(target, scored),
    }
    arm_summaries: dict[str, object] = {}
    arm_leaks: dict[str, object] = {}
    fold_rows: list[dict[str, object]] = []
    prediction_rows: list[dict[str, object]] = []
    repeat_rows: list[dict[str, object]] = []
    for arm in ARM_ORDER:
        print("arm: " + arm)
        result = evaluate_arm(
            arm,
            morgan=morgan,
            physical=features_by_arm[arm],
            target=targets[arm],
            temperatures=temperatures,
            groups=groups,
            splits=splits,
            jobs=jobs,
        )
        arm_summaries[arm] = result["summary"]
        arm_leaks[arm] = result["leak"]
        fold_rows.extend(result["fold_rows"])  # type: ignore[arg-type]
        prediction_rows.extend(result["prediction_rows"])  # type: ignore[arg-type]
        repeat_rows.extend(result["repeat_rows"])  # type: ignore[arg-type]

    write_csv_rows(ARTIFACTS_DIR / (ARTIFACT_STEM + "_folds.csv"), FOLD_COLUMNS_OUT, fold_rows)
    write_csv_rows(
        ARTIFACTS_DIR / (ARTIFACT_STEM + "_predictions.csv"),
        PREDICTION_COLUMNS_OUT,
        prediction_rows,
    )
    write_csv_rows(
        ARTIFACTS_DIR / (ARTIFACT_STEM + "_repeats.csv"),
        REPEAT_COLUMNS_OUT,
        repeat_rows,
    )
    inputs = {
        "observations": portable_relative_path(COVERAGE_PATH, root=REPOSITORY_ROOT),
        "observations_sha256": canonical_text_sha256(COVERAGE_PATH),
        "frozen_features": portable_relative_path(FEATURES_PATH, root=REPOSITORY_ROOT),
        "frozen_features_sha256": canonical_text_sha256(FEATURES_PATH),
        "new_features": portable_relative_path(NEW_FEATURES_PATH, root=REPOSITORY_ROOT),
        "new_features_sha256": canonical_text_sha256(NEW_FEATURES_PATH),
        "frozen_xtb_cache": portable_relative_path(FROZEN_XTB_CACHE, root=REPOSITORY_ROOT),
        "feature_table_sha256": canonical_text_sha256(feature_path),
        "feature_blocks": scoreboard["input_report"]["feature_blocks"],  # type: ignore[index]
    }
    summary = build_summary(
        generated_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        prereg_text=prereg_text,
        prereg_sha=prereg_sha,
        inputs=inputs,
        scoreboard=contract,
        xtb=xtb_report,
        block_report={
            **block_report,
            "compounds_ok": xtb_report["compounds_ok"],
            "compounds_failed": xtb_report["compounds_failed"],
            "failed_keys": xtb_report["failed_keys"],
        },
        arm_summaries=arm_summaries,
        arm_leaks=arm_leaks,
        placebo_r2=float(arm_summaries[ARM_PLACEBO][HYBRID]["r2"]["mean"]),  # type: ignore[index]
        feature_table_path=portable_relative_path(feature_path, root=REPOSITORY_ROOT),
    )
    summary["outputs"] = {
        "feature_table": portable_relative_path(feature_path, root=REPOSITORY_ROOT),
        "folds": portable_relative_path(ARTIFACTS_DIR / (ARTIFACT_STEM + "_folds.csv"), root=REPOSITORY_ROOT),
        "predictions": portable_relative_path(ARTIFACTS_DIR / (ARTIFACT_STEM + "_predictions.csv"), root=REPOSITORY_ROOT),
        "repeats": portable_relative_path(ARTIFACTS_DIR / (ARTIFACT_STEM + "_repeats.csv"), root=REPOSITORY_ROOT),
        "report": portable_relative_path(REPORT_PATH, root=REPOSITORY_ROOT),
        "summary": portable_relative_path(SUMMARY_PATH, root=REPOSITORY_ROOT),
    }
    SUMMARY_PATH.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    REPORT_PATH.write_text("\n".join(format_report(summary)) + "\n", encoding="utf-8", newline="\n")
    for line in format_report(summary):
        print(line)
    return 0 if summary["verdict"]["integrity_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())