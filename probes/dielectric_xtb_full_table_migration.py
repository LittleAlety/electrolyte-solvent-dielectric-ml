"""Whole-table migration verdict for the v0.4 conformer-averaged xTB protocol.

Appendix X, lever 4.  The frozen v0.3 xTB block describes every compound by a
*single* ETKDGv3 conformer (seed 42 + row index) relaxed under GFN2 with
--opt, and reads the dipole off that one minimum.  A flexible molecule has no
single minimum: the gas-phase dipole of a glyme or a dinitrile is a conformer
ensemble average, so the frozen column is a sample of size one.  This probe asks
the two questions the migration decision actually rests on.

1. **What does the v0.4 protocol cost?**  MAX_CONFORMERS ETKDGv3 conformers per
   compound, each relaxed with MMFF94 (UFF as fallback, exactly as
   generate_3d_xyz does), then one GFN2 *single point* per conformer through the
   frozen single-thread launcher.  The probe measures the wall clock on the real
   roster rather than extrapolating from a couple of molecules, and reports the
   per-compound distribution and a heavy-atom regression so a future table can
   be priced.
2. **Does it move the main scoreboard?**  The scored side never changes: the 457
   room-band rows of the 97 v11 compounds, GroupKFold by InChIKey, 5x10, seed 42,
   the frozen XGB_PARAMS.  Only dipole_D and its derived mu_sq_over_Vm are
   swapped for the conformer-averaged values, because that is the one column the
   protocol change is about.  The volumes, the polarizability and the HOMO-LUMO
   gap stay frozen -- the geometry migration is registered as pending rather
   than smuggled in.

The fold dealing is never re-invented here: the masks come from
dielectric_coverage_paired_benchmark and the splitter is its own
run_coverage_protocol, so paired_base is re-run through the identical code path
and must reproduce 0.4091179943351143 before any delta may be quoted.

Two guards are carried over from the lever pre-registration tradition.  A
shuffled_conformer_dipole control permutes the conformer means across the
migrated compounds on the same folds; a migration whose delta the control also
produces is reported as noise.  A row-level random_row splitter appears exactly
once, clearly labelled as a leak reference, and never enters a verdict.

Read-only with respect to every released artefact: the frozen feature tables and
data/dielectric_v03.csv are read, never written.  The probe writes only
probes/dielectric_xtb_full_table_migration_summary.json, the three
probes/artifacts/dielectric_xtb_full_table_migration_*.csv tables, and xTB
scratch under the git-ignored data/interim/xtb_conformer_migration.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import shutil
import statistics
import sys
import time
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))
sys.path.insert(0, str(REPOSITORY_ROOT / "probes"))

import dielectric_coverage_paired_benchmark as coverage
import numpy as np
from dielectric_observations_grouped_benchmark import (
    FEATURES_PATH,
    OBSERVATIONS_PATH,
    build_matrices,
    load_table,
)
from dielectric_representation_ablation import (
    N_REPEATS,
    N_SPLITS,
    PHYSICAL_COLUMNS,
    SEED,
)
from rdkit import Chem
from rdkit.Chem import AllChem
from xtb_recovery_probe import resolve_xtb

from electrolyte_ml.exporting import canonical_text_sha256
from electrolyte_ml.pathing import portable_relative_path
from electrolyte_ml.xtb_features import (
    XtbFeatureError,
    XtbParsed,
    parse_xtb_output,
)
from electrolyte_ml.xtb_runner import run_xtb_subprocess

PREREG_PATH = REPOSITORY_ROOT / "probes" / "dielectric_r2_levers_prereg.json"
SUMMARY_PATH = REPOSITORY_ROOT / "probes" / "dielectric_xtb_full_table_migration_summary.json"
ARTIFACTS_DIR = REPOSITORY_ROOT / "probes" / "artifacts"
ARTIFACT_STEM = "dielectric_xtb_full_table_migration"
WORK_DIR = REPOSITORY_ROOT / "data" / "interim" / "xtb_conformer_migration"
FROZEN_TIMING_PATH = REPOSITORY_ROOT / "probes" / "p5b_xtb_timing.csv"

#: The published paired_base Hybrid R2 the baseline arm has to reproduce.  Pinned as a
#: literal, not only read from the JSON, so a drifting upstream file cannot redefine it.
REFERENCE_R2 = 0.4091179943351143
REFERENCE_TOLERANCE = 1e-9
HYBRID = "Morgan+Physical"

#: Appendix X lever 4 expects +0.01 to +0.03.  There is no locked pre-registration for this
#: lever (that file covers levers 2, 3 and 7), so the criterion is stated here, before the
#: run, at the low end of the expected band rather than somewhere inside it.
PASS_DELTA_R2 = 0.0100
INERT_DELTA_R2 = 0.0000

#: The v0.4 protocol, frozen in writing before the run.
MAX_CONFORMERS = 8
CONFORMER_SEED_BASE = 42
BOLTZMANN_TEMPERATURE_K = 298.15
HARTREE_TO_J = 4.3597447222071e-18
BOLTZMANN_J_PER_K = 1.380649e-23

#: Wall-clock ceiling for the xTB part of the run.  Above it the probe falls back to a
#: bounded pilot instead of pretending the whole table was priced.
TIME_BUDGET_SECONDS = 40 * 60

#: The columns the migration is allowed to touch.  Everything else stays frozen on purpose.
MIGRATED_COLUMNS = ("dipole_D", "mu_sq_over_Vm")

CONFORMER_COLUMNS = (
    "order",
    "inchikey",
    "name",
    "smiles",
    "heavy_atom_count",
    "is_scored",
    "status",
    "n_conformers",
    "force_field",
    "dipole_D_frozen",
    "dipole_D_conformer_mean",
    "dipole_D_conformer_std",
    "dipole_D_conformer_range",
    "dipole_D_conformer_boltzmann",
    "dipole_D_conformer_min",
    "dipole_D_conformer_max",
    "molar_volume_m3_mol_frozen",
    "mu_sq_over_Vm_frozen",
    "mu_sq_over_Vm_conformer_mean",
    "embed_seconds",
    "xtb_seconds_total",
    "xtb_seconds_median",
    "xtb_seconds_max",
    "error",
)


def _use_utf8_stdout() -> None:
    """Windows consoles are GBK, so force UTF-8 before printing the report."""

    encoding = (getattr(sys.stdout, "encoding", "") or "").lower()
    if "utf-8" in encoding or "utf8" in encoding:
        return
    buffer = getattr(sys.stdout, "buffer", None)
    if buffer is not None:
        sys.stdout = io.TextIOWrapper(buffer, encoding="utf-8", errors="replace")


def _slug(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in "._-" else "_" for char in value)
    return cleaned.strip("_")[:120] or "compound"


def write_csv_rows(
    path: Path,
    fieldnames: Sequence[str],
    rows: Sequence[Mapping[str, object]],
) -> None:
    """Write an LF-only CSV; .gitattributes pins *.csv to eol=lf."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({name: row.get(name, "") for name in fieldnames})


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def xtb_single_point_arguments(input_name: str, *, formal_charge: int) -> list[str]:
    """The frozen electronic-structure arguments with the geometry step removed.

    The v0.4 protocol takes the RDKit/MMFF geometry as given, so --opt is dropped and the
    rest of the frozen prefix (--gfn 2 --chrg <q> --uhf 0) is kept verbatim.
    """

    return [input_name, "--gfn", "2", "--chrg", str(formal_charge), "--uhf", "0"]


def parse_single_point_output(text: str) -> XtbParsed:
    """Parse a single-point log.

    xTB only prints its "normal termination of xtb" banner when it ran a geometry
    optimisation, so the frozen parser is fed the completion marker the single point does
    print.  The same idiom is already used for optimisations that end on .xtboptok.
    """

    if "finished run on" not in text:
        raise XtbFeatureError("xTB single point did not report a finished run")
    return parse_xtb_output(text + "\nnormal termination of xtb\n")


def boltzmann_weights(
    energies_hartree: Sequence[float],
    *,
    temperature_k: float = BOLTZMANN_TEMPERATURE_K,
) -> np.ndarray:
    """Boltzmann weights over conformer energies, shifted by the lowest energy."""

    energies = np.asarray(energies_hartree, dtype=float)
    if energies.size == 0:
        raise ValueError("no conformer energies to weight")
    if not np.isfinite(energies).all():
        raise ValueError("conformer energies must be finite")
    kt_hartree = BOLTZMANN_J_PER_K * temperature_k / HARTREE_TO_J
    scaled = (energies - float(energies.min())) / kt_hartree
    weights = np.exp(-scaled)
    return weights / float(weights.sum())


def summarize_conformer_dipoles(
    dipoles_debye: Sequence[float],
    energies_hartree: Sequence[float],
) -> dict[str, float | int]:
    """Mean, spread and Boltzmann average of one compound's conformer dipoles."""

    dipoles = np.asarray(dipoles_debye, dtype=float)
    if dipoles.size == 0:
        raise ValueError("no conformer dipoles to summarise")
    if not np.isfinite(dipoles).all():
        raise ValueError("conformer dipoles must be finite")
    weights = boltzmann_weights(energies_hartree)
    summary: dict[str, float | int] = {
        "n_conformers": int(dipoles.size),
        "dipole_D_conformer_mean": float(dipoles.mean()),
        "dipole_D_conformer_std": float(dipoles.std(ddof=0)),
        "dipole_D_conformer_range": float(dipoles.max() - dipoles.min()),
        "dipole_D_conformer_boltzmann": float(np.dot(weights, dipoles)),
        "dipole_D_conformer_min": float(dipoles.min()),
        "dipole_D_conformer_max": float(dipoles.max()),
        "dipole_D_conformer_std_ddof1": (
            float(dipoles.std(ddof=1)) if dipoles.size > 1 else 0.0
        ),
    }
    return summary


def embed_conformer_geometries(
    smiles: str,
    *,
    seed: int,
    max_conformers: int = MAX_CONFORMERS,
) -> tuple[Chem.Mol, str]:
    """ETKDGv3 multi-conformer embedding plus the force field generate_3d_xyz uses.

    Returns the molecule with its conformers and the force field that was applied, so the
    per-compound table records whether MMFF94 or the UFF fallback produced the geometry.
    """

    molecule = Chem.MolFromSmiles(smiles)
    if molecule is None:
        raise XtbFeatureError(f"invalid SMILES: {smiles!r}")
    molecule = Chem.AddHs(molecule)
    parameters = AllChem.ETKDGv3()
    parameters.randomSeed = int(seed)
    parameters.useRandomCoords = True
    conformer_ids = AllChem.EmbedMultipleConfs(
        molecule,
        numConfs=int(max_conformers),
        params=parameters,
    )
    if len(conformer_ids) == 0:
        raise XtbFeatureError(f"RDKit could not embed SMILES: {smiles!r}")
    if AllChem.MMFFHasAllMoleculeParams(molecule):
        AllChem.MMFFOptimizeMoleculeConfs(molecule, maxIters=1000)
        force_field = "MMFF94"
    else:
        AllChem.UFFOptimizeMoleculeConfs(molecule, maxIters=1000)
        force_field = "UFF"
    return molecule, force_field


def run_conformer_compound(
    *,
    inchikey: str,
    smiles: str,
    xtb_executable: Path,
    work_dir: Path,
    seed: int,
    max_conformers: int = MAX_CONFORMERS,
    timeout_seconds: int = 600,
) -> dict[str, object]:
    """One compound under the v0.4 protocol: embed, then one single point per conformer.

    Every single point runs in its own freshly cleared directory, because a leftover
    xtbrestart from the previous conformer would be reused as an SCF restart and perturb
    the converged dipole -- the same failure mode run_xtb_physical_features clears away,
    for the same reason.
    """

    flat = Chem.MolFromSmiles(smiles)
    if flat is None:
        raise XtbFeatureError(f"invalid SMILES: {smiles!r}")
    formal_charge = Chem.GetFormalCharge(flat)
    embed_start = time.perf_counter()
    molecule, force_field = embed_conformer_geometries(
        smiles, seed=seed, max_conformers=max_conformers
    )
    embed_seconds = time.perf_counter() - embed_start

    dipoles: list[float] = []
    energies: list[float] = []
    seconds: list[float] = []
    for conformer_index in range(molecule.GetNumConformers()):
        run_dir = work_dir / _slug(inchikey) / f"conf{conformer_index}"
        if run_dir.exists():
            shutil.rmtree(run_dir)
        run_dir.mkdir(parents=True, exist_ok=True)
        input_name = "input.xyz"
        (run_dir / input_name).write_text(
            Chem.MolToXYZBlock(molecule, confId=conformer_index), encoding="utf-8"
        )
        start = time.perf_counter()
        completed = run_xtb_subprocess(
            xtb_executable,
            xtb_single_point_arguments(input_name, formal_charge=formal_charge),
            cwd=run_dir,
            timeout_seconds=timeout_seconds,
        )
        seconds.append(time.perf_counter() - start)
        if completed.returncode != 0:
            raise XtbFeatureError(
                f"xTB single point failed for {inchikey} conformer {conformer_index} "
                f"with exit code {completed.returncode}"
            )
        text = completed.stdout.decode("utf-8", errors="replace")
        (run_dir / "xtb.out").write_bytes(completed.stdout)
        parsed = parse_single_point_output(text)
        dipoles.append(parsed.dipole_debye)
        energies.append(parsed.total_energy_hartree)

    summary = summarize_conformer_dipoles(dipoles, energies)
    return {
        **summary,
        "force_field": force_field,
        "dipoles_debye": dipoles,
        "energies_hartree": energies,
        "per_conformer_seconds": seconds,
        "embed_seconds": embed_seconds,
        "xtb_seconds_total": float(sum(seconds)),
        "xtb_seconds_median": float(statistics.median(seconds)),
        "xtb_seconds_max": float(max(seconds)),
        "status": "ok",
        "error": "",
    }


def build_roster(
    features: Mapping[str, Mapping[str, str]],
    scored_keys: set[str],
) -> list[dict[str, object]]:
    """Every compound of the merged feature block, scored ones first and small ones first.

    The ordering is what makes --limit a *representative* bounded pilot rather than an
    alphabetical accident: the compounds it keeps first are the ones the main scoreboard is
    actually scored on, smallest first, so a truncated run still prices what matters.
    """

    roster: list[dict[str, object]] = []
    for inchikey, row in features.items():
        smiles = str(row.get("smiles", "")).strip()
        heavy = row.get("heavy_atom_count", "").strip()
        roster.append(
            {
                "inchikey": str(inchikey),
                "name": str(row.get("name", "")),
                "smiles": smiles,
                "heavy_atom_count": int(float(heavy)) if heavy else 0,
                "is_scored": str(inchikey) in scored_keys,
                "feature_source": str(row.get("_feature_source", "")),
                "dipole_D_frozen": str(row.get("dipole_D", "")),
                "molar_volume_m3_mol_frozen": str(row.get("molar_volume_m3_mol", "")),
                "mu_sq_over_Vm_frozen": str(row.get("mu_sq_over_Vm", "")),
            }
        )
    roster.sort(
        key=lambda item: (
            0 if item["is_scored"] else 1,
            int(item["heavy_atom_count"]),
            str(item["inchikey"]),
        )
    )
    return roster


def build_physical_matrix_v04(
    rows: Sequence[Mapping[str, object]],
    *,
    dipole_map: Mapping[str, float],
) -> tuple[np.ndarray, dict[str, int]]:
    """The frozen physical block with only the dipole-derived columns migrated.

    Rebuilds the matrix exactly the way build_matrices does -- the observation's own T_K
    over every frozen xTB column -- and then substitutes dipole_D and mu_sq_over_Vm for the
    compounds that have a v0.4 row.  mu_sq_over_Vm is the Onsager dipole-density term
    dipole**2 / V_m, so it has to follow dipole_D or the block would carry two disagreeing
    copies of the same physics.  The molar volume is left at the frozen value on purpose;
    the geometry migration is a separate, unrun change.
    """

    dipole_index = PHYSICAL_COLUMNS.index("dipole_D")
    mu_index = PHYSICAL_COLUMNS.index("mu_sq_over_Vm")
    matrix = np.asarray(
        [
            [
                float(str(row["T_K"]))
                if column == "T_K"
                else float(str(row["_features"][column]))  # type: ignore[index]
                for column in PHYSICAL_COLUMNS
            ]
            for row in rows
        ],
        dtype=np.float64,
    )
    if not np.isfinite(matrix).all():
        raise ValueError("physical feature matrix contains non-finite values")

    migrated_rows = 0
    missing_volume_rows = 0
    migrated_compounds: set[str] = set()
    for index, row in enumerate(rows):
        key = str(row["inchikey"])
        dipole = dipole_map.get(key)
        if dipole is None:
            continue
        features = row["_features"]
        volume_text = str(features.get("molar_volume_m3_mol", ""))  # type: ignore[union-attr]
        matrix[index, dipole_index] = float(dipole)
        if volume_text.strip():
            matrix[index, mu_index] = float(dipole) ** 2 / float(volume_text)
        else:
            missing_volume_rows += 1
        migrated_rows += 1
        migrated_compounds.add(key)
    return matrix, {
        "migrated_rows": migrated_rows,
        "migrated_compounds": len(migrated_compounds),
        "unmigrated_rows": int(matrix.shape[0]) - migrated_rows,
        "rows_without_a_frozen_molar_volume": missing_volume_rows,
        "migrated_columns": list(MIGRATED_COLUMNS),
    }


def shuffled_dipole_map(
    dipole_map: Mapping[str, float],
    *,
    seed: int = SEED,
) -> dict[str, float]:
    """Permute the conformer means across compounds: the placebo for the migration arm.

    The permuted block carries exactly the same marginal distribution of dipoles, attached
    to the wrong molecules.  A delta the shuffle also produces is the model reading the
    value distribution, not the per-compound physics.
    """

    keys = sorted(dipole_map)
    values = np.asarray([dipole_map[key] for key in keys], dtype=float)
    rng = np.random.default_rng(seed)
    permuted = rng.permutation(values)
    return {key: float(value) for key, value in zip(keys, permuted, strict=True)}


def heavy_atom_cost_regression(
    per_compound_seconds: Sequence[tuple[int, float]],
) -> dict[str, float | int]:
    """Least-squares xTB seconds against heavy-atom count, for pricing a future table."""

    pairs = [(float(size), float(seconds)) for size, seconds in per_compound_seconds]
    if len(pairs) < 2:
        return {"n": len(pairs), "slope_seconds_per_heavy_atom": 0.0, "intercept_seconds": 0.0}
    sizes = np.asarray([size for size, _ in pairs], dtype=float)
    times = np.asarray([seconds for _, seconds in pairs], dtype=float)
    slope, intercept = np.polyfit(sizes, times, 1)
    return {
        "n": len(pairs),
        "slope_seconds_per_heavy_atom": float(slope),
        "intercept_seconds": float(intercept),
        "mean_seconds_per_compound": float(times.mean()),
        "median_seconds_per_compound": float(np.median(times)),
    }


def protocol_metrics(
    result: Mapping[str, object],
    protocol: str,
    representation: str = HYBRID,
) -> Mapping[str, object]:
    summary = result["summary"]
    assert isinstance(summary, Mapping)
    block = summary[protocol]  # type: ignore[index]
    assert isinstance(block, Mapping)
    metrics = block[representation]  # type: ignore[index]
    assert isinstance(metrics, Mapping)
    return metrics


def metric_mean(result: Mapping[str, object], protocol: str, name: str) -> float:
    return float(protocol_metrics(result, protocol)[name]["mean"])  # type: ignore[index]


def register_protocol_descriptions() -> None:
    """Teach the coverage benchmark's own runner about this probe's three arms.

    run_coverage_protocol reads its human description out of a module-level dict.  The arms
    are added in memory at run time rather than by editing that frozen file, so the coverage
    probe's published output stays byte-identical.
    """

    coverage.PROTOCOL_DESCRIPTIONS.update(
        {
            "paired_base_conformer_dipole": (
                "same scored rows and folds as paired_base; the physical block carries the "
                "v0.4 conformer-averaged dipole_D and its recomputed mu_sq_over_Vm"
            ),
            "paired_base_conformer_dipole_shuffled": (
                "PLACEBO: same migration as paired_base_conformer_dipole but the conformer "
                "means are permuted across compounds; never a conclusion number"
            ),
            "paired_base_random_row_leak": (
                "LEAK REFERENCE ONLY: paired_base rows split by row, so one compound reaches "
                "both sides of a fold; never a conclusion number"
            ),
        }
    )


def run_scored_protocol(
    protocol: str,
    *,
    splitter: str,
    morgan: np.ndarray,
    physical: np.ndarray,
    target: np.ndarray,
    temperatures: Sequence[float],
    groups: Sequence[str],
    score_mask: Sequence[bool],
    train_mask: Sequence[bool],
    n_splits: int,
    n_repeats: int,
    seed: int,
) -> dict[str, object]:
    """Run one arm through the coverage benchmark's own runner, and summarise it.

    run_coverage_protocol returns the fold, repeat and prediction tables but leaves the
    per-protocol metric roll-up to its family-level caller.  summarise_repeats is the frozen
    function that caller uses, so the numbers here are produced by the same code as the
    published paired_base reading.
    """

    result = coverage.run_coverage_protocol(
        protocol,
        splitter=splitter,
        morgan=morgan,
        physical=physical,
        target=target,
        temperatures=temperatures,
        groups=groups,
        score_mask=score_mask,
        train_mask=train_mask,
        n_splits=n_splits,
        n_repeats=n_repeats,
        seed=seed,
    )
    result["summary"] = coverage.summarize_repeats(result["repeat_rows"])
    return result


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--repeats", type=int, default=N_REPEATS)
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="bounded pilot: run only the first N roster compounds (0 = the whole table)",
    )
    parser.add_argument("--max-conformers", type=int, default=MAX_CONFORMERS)
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--time-budget", type=float, default=TIME_BUDGET_SECONDS)
    parser.add_argument("--xtb", type=Path, default=None)
    parser.add_argument("--work-dir", type=Path, default=WORK_DIR)
    parser.add_argument("--summary", type=Path, default=SUMMARY_PATH)
    parser.add_argument("--artifacts-dir", type=Path, default=ARTIFACTS_DIR)
    parser.add_argument("--skip-migration-diff", action="store_true")
    return parser.parse_args(argv)


def build_summary(
    *,
    seed: int,
    n_repeats: int,
    max_conformers: int,
    baseline_result: Mapping[str, object],
    migration_result: Mapping[str, object] | None,
    shuffled_result: Mapping[str, object] | None,
    leak_result: Mapping[str, object] | None,
    conformer_rows: Sequence[Mapping[str, object]],
    roster_size: int,
    scored_total: int,
    measured_scored: int,
    migration_account: Mapping[str, int] | None,
    cost: Mapping[str, object],
    pending: Sequence[Mapping[str, object]],
    bounded_pilot: bool,
    inputs: Mapping[str, object],
) -> dict[str, object]:
    baseline_r2 = metric_mean(baseline_result, "paired_base", "r2")
    reproduced = abs(baseline_r2 - REFERENCE_R2) <= REFERENCE_TOLERANCE
    readings: dict[str, object] = {
        "baseline_reproduced": bool(reproduced),
        "baseline_r2": baseline_r2,
        "published_r2": REFERENCE_R2,
        "reference_tolerance": REFERENCE_TOLERANCE,
        "baseline": {
            name: metric_mean(baseline_result, "paired_base", name)
            for name in ("r2", "mae", "rmse", "spearman", "mae_lt20", "mae_20_60", "mae_gt60")
        },
    }

    delta: float | None = None
    if migration_result is None:
        verdict_state = "not_run"
    else:
        migration_block = {
            name: metric_mean(migration_result, "paired_base_conformer_dipole", name)
            for name in ("r2", "mae", "rmse", "spearman", "mae_lt20", "mae_20_60", "mae_gt60")
        }
        delta = float(migration_block["r2"]) - baseline_r2
        readings["migration"] = migration_block
        readings["delta_r2"] = delta
        if shuffled_result is not None:
            shuffled_r2 = metric_mean(
                shuffled_result, "paired_base_conformer_dipole_shuffled", "r2"
            )
            readings["control"] = {
                "shuffled_r2": shuffled_r2,
                "control_delta_r2": shuffled_r2 - baseline_r2,
                "control_collapsed": bool(abs(shuffled_r2 - baseline_r2) <= 0.02),
            }
        if not reproduced:
            verdict_state = "unverified"
        elif delta >= PASS_DELTA_R2:
            verdict_state = "pass"
        elif delta > INERT_DELTA_R2:
            verdict_state = "partial"
        else:
            verdict_state = "fail"

    if bounded_pilot:
        completeness = "bounded_pilot"
    elif measured_scored >= scored_total:
        completeness = "whole_table"
    else:
        completeness = "partial_coverage"
    readings["completeness"] = completeness
    readings["scored_compounds_migrated"] = measured_scored
    readings["scored_compounds_total"] = scored_total

    if leak_result is not None:
        readings["leak_reference"] = {
            "protocol": "paired_base_random_row_leak",
            "r2": metric_mean(leak_result, "paired_base_random_row_leak", "r2"),
            "note": "row-level split of the same 457 rows; never enters a pass or a fail",
        }

    if verdict_state == "pass":
        statement = (
            "the v0.4 conformer-averaged dipole migrates the main scoreboard by "
            f"{delta:+.4f} R2, at or above the +{PASS_DELTA_R2:.4f} the lever was written for"
        )
    elif verdict_state == "partial":
        statement = (
            f"the migration moves the scoreboard by {delta:+.4f} R2, below the "
            f"+{PASS_DELTA_R2:.4f} criterion: a real but sub-criterion gain, reported as partial"
        )
    elif verdict_state == "fail":
        statement = (
            f"the migration does not move the scoreboard ({delta:+.4f} R2): the lever is dead "
            "on this scoreboard and 0.5454 stands"
        )
    elif verdict_state == "not_run":
        statement = "the migration arm was not run"
    else:
        statement = (
            "the baseline arm did not reproduce the published 0.4091179943351143, so no delta "
            "from this run may be quoted"
        )

    return {
        "schema_version": 1,
        "task": "week14_lever4_xtb_full_table_migration",
        "shots": 1,
        "seed": seed,
        "n_repeats": n_repeats,
        "max_conformers": max_conformers,
        "protocol": {
            "id": "v0.4_conformer_averaged_dipole",
            "frozen_prefix": "xtb <input.xyz> --gfn 2 --chrg <q> --uhf 0 (no --opt)",
            "geometry": (
                f"RDKit ETKDGv3, numConfs={max_conformers}, MMFF94 (UFF fallback), "
                "seed 42 + roster order"
            ),
            "aggregation": (
                "arithmetic mean over conformers; the Boltzmann average is reported alongside"
            ),
            "migrated_columns": list(MIGRATED_COLUMNS),
            "untouched_columns": [
                column for column in PHYSICAL_COLUMNS if column not in MIGRATED_COLUMNS
            ],
            "scoreboard": coverage.ROOM_BAND_REFERENCE_PROTOCOL,
            "scoreboard_r2_reference": REFERENCE_R2,
            "criterion": {
                "pass_delta_r2": PASS_DELTA_R2,
                "inert_delta_r2": INERT_DELTA_R2,
                "source": (
                    "appendix X lever 4 expectation +0.01 to +0.03; stated here because the "
                    "lever pre-registration covers levers 2, 3 and 7 only"
                ),
            },
            "control": "paired_base_conformer_dipole_shuffled on the identical folds",
        },
        "inputs": dict(inputs),
        "main_scoreboard": {
            "rows_scored": int(baseline_result["meta"]["scored_rows"]),  # type: ignore[index]
            "compounds_scored": int(baseline_result["meta"]["compounds_scored"]),  # type: ignore[index]
            "folds": int(baseline_result["meta"]["folds"]),  # type: ignore[index]
            "splitter": "GroupKFold by InChIKey, dealt by the coverage benchmark's masked_splits",
            "fold_source": (
                "probes/dielectric_coverage_paired_benchmark.py (anchored on the paired_base masks)"
            ),
            "mask_reused_not_rebuilt": True,
        },
        "cost": dict(cost),
        "conformer_coverage": {
            "roster_compounds": roster_size,
            "compounds_run": len(conformer_rows),
            "status_counts": dict(
                sorted(Counter(str(row["status"]) for row in conformer_rows).items())
            ),
            "scored_compounds_migrated": measured_scored,
            "scored_compounds_total": scored_total,
        },
        "migration_account": dict(migration_account or {}),
        "readings": readings,
        "verdict": {"state": verdict_state, "delta_r2": delta, "statement": statement},
        "pending": [dict(item) for item in pending],
        "outputs": {},
    }


def write_artifacts(
    artifacts_dir: Path,
    *,
    conformer_rows: Sequence[Mapping[str, object]],
    fold_rows: Sequence[Mapping[str, object]],
    prediction_rows: Sequence[Mapping[str, object]],
) -> dict[str, str]:
    outputs = {
        "conformers": artifacts_dir / f"{ARTIFACT_STEM}_conformers.csv",
        "folds": artifacts_dir / f"{ARTIFACT_STEM}_folds.csv",
        "predictions": artifacts_dir / f"{ARTIFACT_STEM}_predictions.csv",
    }
    write_csv_rows(outputs["conformers"], CONFORMER_COLUMNS, conformer_rows)
    write_csv_rows(
        outputs["folds"],
        (
            "protocol",
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
        ),
        fold_rows,
    )
    write_csv_rows(
        outputs["predictions"],
        (
            "protocol",
            "representation",
            "repeat",
            "fold",
            "inchikey",
            "T_K",
            "target",
            "prediction",
        ),
        prediction_rows,
    )
    return {
        name: portable_relative_path(path, root=REPOSITORY_ROOT)
        for name, path in outputs.items()
    }


def format_report(summary: Mapping[str, object]) -> list[str]:
    readings = summary["readings"]
    cost = summary["cost"]
    protocol = summary["protocol"]
    scoreboard = summary["main_scoreboard"]
    assert isinstance(readings, Mapping)
    assert isinstance(cost, Mapping)
    assert isinstance(protocol, Mapping)
    assert isinstance(scoreboard, Mapping)
    lines = [
        "v0.4 xTB full-table migration -- lever 4",
        "",
        "protocol      : {} ({} conformers, single point, no --opt)".format(
            protocol["id"], summary["max_conformers"]
        ),
        "scoreboard    : {} rows / {} compounds, GroupKFold by InChIKey, {} folds x {} repeats".format(
            scoreboard["rows_scored"], scoreboard["compounds_scored"], scoreboard["folds"],
            summary["n_repeats"],
        ),
        "",
        "baseline      : R2 {:.10f}  published {:.10f}  reproduced {}".format(
            readings["baseline_r2"], readings["published_r2"], readings["baseline_reproduced"]
        ),
    ]
    if "migration" in readings:
        migration = readings["migration"]
        assert isinstance(migration, Mapping)
        lines.append(
            "migration arm : R2 {:.10f}  delta {:+.4f}".format(
                migration["r2"], readings["delta_r2"]
            )
        )
    if "control" in readings:
        control = readings["control"]
        assert isinstance(control, Mapping)
        lines.append(
            "control       : R2 {:.4f}  delta {:+.4f}  collapsed {}".format(
                control["shuffled_r2"], control["control_delta_r2"], control["control_collapsed"]
            )
        )
    if "leak_reference" in readings:
        leak = readings["leak_reference"]
        assert isinstance(leak, Mapping)
        lines.append(
            "leak (labelled, not a conclusion): random_row R2 {:.4f}".format(leak["r2"])
        )
    lines.append("")
    lines.append(
        "cost          : {} compounds, xTB {:.1f} s, embed {:.1f} s, mean {:.2f} s/compound".format(
            cost.get("compounds_measured"),
            float(cost.get("xtb_seconds_total", 0.0)),
            float(cost.get("embed_seconds_total", 0.0)),
            float(cost.get("mean_xtb_seconds_per_compound", 0.0)),
        )
    )
    lines.append(
        "                wall clock {:.1f} s ({:.1f} min); budget {:.0f} s".format(
            float(cost.get("measured_wall_clock_seconds", 0.0)),
            float(cost.get("measured_wall_clock_seconds", 0.0)) / 60.0,
            float(cost.get("time_budget_seconds", 0.0)),
        )
    )
    lines.append("")
    lines.append(
        "integrity     : {}".format(
            "PASS" if readings.get("baseline_reproduced") else "FAILED"
        )
    )
    lines.append("verdict       : {}".format(summary["verdict"]["state"]))
    lines.append(str(summary["verdict"]["statement"]))
    return lines


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    _use_utf8_stdout()
    seed = int(args.seed)
    n_repeats = int(args.repeats)
    max_conformers = int(args.max_conformers)
    register_protocol_descriptions()

    v11_rows, _frozen, v11_dropped = load_table(OBSERVATIONS_PATH, FEATURES_PATH)
    merged, feature_report = coverage.merge_feature_blocks()
    coverage_rows, coverage_dropped = coverage.load_coverage_table(coverage.COVERAGE_PATH, merged)
    morgan, physical, target, temperatures, groups = build_matrices(coverage_rows)
    origin = np.asarray([str(row["observation_origin"]) for row in coverage_rows])
    band = np.asarray([str(row["temperature_band"]) for row in coverage_rows])
    keys = np.asarray([str(row["inchikey"]) for row in coverage_rows])
    fixed_score = np.asarray(
        (origin == coverage.ZERO_FREQUENCY_ORIGIN) & (band == coverage.ROOM_BAND), dtype=bool
    )
    scored_keys = sorted(set(keys[fixed_score].tolist()))

    baseline = run_scored_protocol(
        "paired_base",
        splitter="grouped",
        morgan=morgan,
        physical=physical,
        target=target,
        temperatures=temperatures,
        groups=groups,
        score_mask=fixed_score,
        train_mask=fixed_score,
        n_splits=N_SPLITS,
        n_repeats=n_repeats,
        seed=seed,
    )
    baseline_r2 = metric_mean(baseline, "paired_base", "r2")
    reproduced = abs(baseline_r2 - REFERENCE_R2) <= REFERENCE_TOLERANCE
    print(
        f"baseline paired_base R2 = {baseline_r2:.10f} (published {REFERENCE_R2:.10f}, reproduced {reproduced})"
    )

    roster = build_roster(merged, set(scored_keys))
    roster_size = len(roster)
    bounded_pilot = False
    if 0 < int(args.limit) < len(roster):
        roster = roster[: int(args.limit)]
        bounded_pilot = True

    xtb_executable = Path(args.xtb) if args.xtb is not None else resolve_xtb()
    conformers_measured = 0
    conformer_rows: list[dict[str, object]] = []
    dipole_map: dict[str, float] = {}
    wall_start = time.perf_counter()
    for order, item in enumerate(roster):
        inchikey = str(item["inchikey"])
        base = {
            "order": order,
            "inchikey": inchikey,
            "name": item["name"],
            "smiles": item["smiles"],
            "heavy_atom_count": item["heavy_atom_count"],
            "is_scored": "yes" if item["is_scored"] else "no",
            "dipole_D_frozen": item["dipole_D_frozen"],
            "molar_volume_m3_mol_frozen": item["molar_volume_m3_mol_frozen"],
            "mu_sq_over_Vm_frozen": item["mu_sq_over_Vm_frozen"],
        }
        try:
            result = run_conformer_compound(
                inchikey=inchikey,
                smiles=str(item["smiles"]),
                xtb_executable=xtb_executable,
                work_dir=Path(args.work_dir),
                seed=CONFORMER_SEED_BASE + order,
                max_conformers=max_conformers,
                timeout_seconds=int(args.timeout),
            )
        except Exception as error:  # noqa: BLE001 - every failure is data, not a crash
            conformer_rows.append({**base, "status": "error", "error": str(error)})
            print(json.dumps({"order": order, "inchikey": inchikey, "status": "error"}))
            continue
        volume = (
            float(item["molar_volume_m3_mol_frozen"])
            if item["molar_volume_m3_mol_frozen"]
            else 0.0
        )
        conformer_rows.append(
            {
                **base,
                **{
                    name: result[name]
                    for name in (
                        "n_conformers",
                        "force_field",
                        "dipole_D_conformer_mean",
                        "dipole_D_conformer_std",
                        "dipole_D_conformer_range",
                        "dipole_D_conformer_boltzmann",
                        "dipole_D_conformer_min",
                        "dipole_D_conformer_max",
                        "embed_seconds",
                        "xtb_seconds_total",
                        "xtb_seconds_median",
                        "xtb_seconds_max",
                        "status",
                        "error",
                    )
                },
                "mu_sq_over_Vm_conformer_mean": (
                    float(result["dipole_D_conformer_mean"]) ** 2 / volume if volume else ""
                ),
            }
        )
        conformers_measured += 1
        dipole_map[inchikey] = float(result["dipole_D_conformer_mean"])
        print(
            json.dumps(
                {
                    "order": order,
                    "inchikey": inchikey,
                    "scored": bool(item["is_scored"]),
                    "heavy": item["heavy_atom_count"],
                    "n_conformers": result["n_conformers"],
                    "dipole_mean": round(float(result["dipole_D_conformer_mean"]), 4),
                    "dipole_std": round(float(result["dipole_D_conformer_std"]), 4),
                    "xtb_s": round(float(result["xtb_seconds_total"]), 2),
                }
            )
        )
        if time.perf_counter() - wall_start > float(args.time_budget):
            print("time budget exhausted; stopping the roster here")
            bounded_pilot = True
            break
    wall_seconds = time.perf_counter() - wall_start

    cost_pairs = [
        (int(row["heavy_atom_count"]), float(row["xtb_seconds_total"]))
        for row in conformer_rows
        if row.get("status") == "ok"
    ]
    per_compound = [seconds for _, seconds in cost_pairs]
    xtb_total = float(sum(per_compound))
    embed_total = float(
        sum(float(row["embed_seconds"]) for row in conformer_rows if row.get("status") == "ok")
    )
    cost: dict[str, object] = {
        "compounds_measured": len(cost_pairs),
        "compounds_roster": roster_size,
        "xtb_seconds_total": xtb_total,
        "embed_seconds_total": embed_total,
        "measured_wall_clock_seconds": wall_seconds,
        "time_budget_seconds": float(args.time_budget),
        "mean_xtb_seconds_per_compound": float(np.mean(per_compound)) if per_compound else 0.0,
        "median_xtb_seconds_per_compound": (
            float(np.median(per_compound)) if per_compound else 0.0
        ),
        "max_xtb_seconds_per_compound": float(np.max(per_compound)) if per_compound else 0.0,
        "min_xtb_seconds_per_compound": float(np.min(per_compound)) if per_compound else 0.0,
        "regression": heavy_atom_cost_regression(cost_pairs),
        "whole_table_projections": {
            "roster_compounds": roster_size,
            "compounds_measured": len(cost_pairs),
            "measured_extrapolated_to_roster_seconds": (
                float(np.mean(per_compound)) * roster_size if per_compound else 0.0
            ),
            "assumption": (
                "linear in compound count at the measured mean; the roster tops out at 28 heavy "
                "atoms, so no heavier chemistry is hidden behind the extrapolation"
            ),
        },
        "frozen_opt_reference": (
            {
                "path": portable_relative_path(FROZEN_TIMING_PATH, root=REPOSITORY_ROOT),
                "sha256": canonical_text_sha256(FROZEN_TIMING_PATH),
                "rows": read_csv_rows(FROZEN_TIMING_PATH),
                "note": (
                    "the frozen v0.3 protocol also ran --opt, so this table is the cold-cache "
                    "cost of one conformer, not an apples-to-apples ratio"
                ),
            }
            if FROZEN_TIMING_PATH.is_file()
            else {}
        ),
    }

    scored_migrated = sum(
        1
        for row in conformer_rows
        if row.get("status") == "ok" and row.get("is_scored") == "yes"
    )
    print(
        f"conformer run finished: {len(cost_pairs)}/{len(roster)} compounds ok in {wall_seconds:.1f} s wall (xTB {xtb_total:.1f} s)"
    )

    migration_result = None
    shuffled_result = None
    leak_result = None
    migration_account: dict[str, int] | None = None
    prediction_rows: list[dict[str, object]] = []
    fold_rows: list[dict[str, object]] = []
    if not args.skip_migration_diff:
        physical_v04, migration_account = build_physical_matrix_v04(
            coverage_rows, dipole_map=dipole_map
        )
        migration_result = run_scored_protocol(
            "paired_base_conformer_dipole",
            splitter="grouped",
            morgan=morgan,
            physical=physical_v04,
            target=target,
            temperatures=temperatures,
            groups=groups,
            score_mask=fixed_score,
            train_mask=fixed_score,
            n_splits=N_SPLITS,
            n_repeats=n_repeats,
            seed=seed,
        )
        physical_shuffled, _ = build_physical_matrix_v04(
            coverage_rows, dipole_map=shuffled_dipole_map(dipole_map, seed=seed)
        )
        shuffled_result = run_scored_protocol(
            "paired_base_conformer_dipole_shuffled",
            splitter="grouped",
            morgan=morgan,
            physical=physical_shuffled,
            target=target,
            temperatures=temperatures,
            groups=groups,
            score_mask=fixed_score,
            train_mask=fixed_score,
            n_splits=N_SPLITS,
            n_repeats=n_repeats,
            seed=seed,
        )
        leak_result = run_scored_protocol(
            "paired_base_random_row_leak",
            splitter="random_row",
            morgan=morgan,
            physical=physical,
            target=target,
            temperatures=temperatures,
            groups=groups,
            score_mask=fixed_score,
            train_mask=fixed_score,
            n_splits=N_SPLITS,
            n_repeats=n_repeats,
            seed=seed,
        )
        for result in (baseline, migration_result, shuffled_result, leak_result):
            fold_rows.extend(result["fold_rows"])  # type: ignore[arg-type]
            prediction_rows.extend(result["prediction_rows"])  # type: ignore[arg-type]

    featureless = coverage.featureless_compound_report(coverage.COVERAGE_PATH, merged)
    pending: list[dict[str, object]] = [
        {
            "item": "geometry migration (molecular_volume_A3, molar_volume_m3_mol, alpha_over_Vm)",
            "reason": (
                "this probe migrates only the dipole-derived columns; re-deriving the volumes "
                "from the v0.4 conformers is a separate change and is not priced here"
            ),
        },
        {
            "item": "observation-table compounds with no xTB feature block",
            "reason": (
                "multi-component ionic-liquid SMILES the frozen runner could not embed; no xTB "
                "row exists for them, so no migration can reach them"
            ),
            "compounds": sorted(
                str(entry["name"]) for entry in featureless["per_compound"].values()  # type: ignore[index]
            ),
            "observation_rows": int(featureless["rows_total"]),  # type: ignore[index]
        },
    ]
    if bounded_pilot:
        pending.append(
            {
                "item": "compounds left unrun by the bounded pilot",
                "reason": "the run stopped at --limit or the wall-clock budget",
                "compounds_remaining": roster_size - len(cost_pairs),
            }
        )

    inputs = {
        "observations": portable_relative_path(coverage.COVERAGE_PATH, root=REPOSITORY_ROOT),
        "observations_sha256": canonical_text_sha256(coverage.COVERAGE_PATH),
        "v11_observations": portable_relative_path(OBSERVATIONS_PATH, root=REPOSITORY_ROOT),
        "v11_observations_sha256": canonical_text_sha256(OBSERVATIONS_PATH),
        "frozen_features": portable_relative_path(FEATURES_PATH, root=REPOSITORY_ROOT),
        "frozen_features_sha256": canonical_text_sha256(FEATURES_PATH),
        "new_features": portable_relative_path(coverage.NEW_FEATURES_PATH, root=REPOSITORY_ROOT),
        "new_features_sha256": canonical_text_sha256(coverage.NEW_FEATURES_PATH),
        "prereg": portable_relative_path(PREREG_PATH, root=REPOSITORY_ROOT),
        "prereg_sha256": canonical_text_sha256(PREREG_PATH),
        "frozen_v03_dataset_sha256": canonical_text_sha256(
            REPOSITORY_ROOT / "data" / "dielectric_v03.csv"
        ),
        "frozen_table_agreement_order_identical": bool(
            coverage.frozen_table_agreement(v11_rows, coverage_rows)["order_identical"]
        ),
        "feature_blocks": {
            "merged_usable": feature_report["merged_usable"],
            "frozen_usable": feature_report["frozen"]["usable"],  # type: ignore[index]
            "new_usable": feature_report["new"]["usable"],  # type: ignore[index]
        },
        "dropped_by_the_v11_loader": dict(v11_dropped),
        "dropped_by_the_coverage_loader": dict(coverage_dropped),
        "xtb_executable": str(xtb_executable),
        "scored_keys": scored_keys,
    }

    summary = build_summary(
        seed=seed,
        n_repeats=n_repeats,
        max_conformers=max_conformers,
        baseline_result=baseline,
        migration_result=migration_result,
        shuffled_result=shuffled_result,
        leak_result=leak_result,
        conformer_rows=conformer_rows,
        roster_size=roster_size,
        scored_total=len(scored_keys),
        measured_scored=scored_migrated,
        migration_account=migration_account,
        cost=cost,
        pending=pending,
        bounded_pilot=bounded_pilot,
        inputs=inputs,
    )
    outputs = write_artifacts(
        Path(args.artifacts_dir),
        conformer_rows=conformer_rows,
        fold_rows=fold_rows,
        prediction_rows=prediction_rows,
    )
    summary["outputs"] = {
        "summary": portable_relative_path(Path(args.summary), root=REPOSITORY_ROOT),
        **outputs,
    }
    summary_path = Path(args.summary)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    for line in format_report(summary):
        print(line)
    print()
    print("summary  : " + str(summary["outputs"]["summary"]))
    for name, path in outputs.items():
        print(f"{name:11s}: {path}")
    return 0 if summary["verdict"]["state"] != "unverified" else 1


if __name__ == "__main__":
    raise SystemExit(main())
