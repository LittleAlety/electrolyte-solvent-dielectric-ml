"""Multi-fragment start-geometry defect probe for the four GFN2-xTB feature failures.

The frozen v0.3 dataset declares 240 rows ``model_ready=true``, yet only 236 of
them enter the frozen fit set.  The four-row gap is accounted for in the roster
arithmetic as ``failed_physical_feature_count = 4`` and the four molecule names
are already listed in ``probes/dielectric_v03_representation_ablation_summary.json``
and ``probes/artifacts/v03_features_baseline_input.csv`` (status ``error``).

What those artefacts do **not** record is *why* the four rows failed.  This probe
records the defect and one demonstrated partial remedy.

Confirmed defect
----------------
All four failing molecules are multi-fragment species (three charge-separated
ionic-liquid ion pairs and one six-fragment metal carbonyl).  ``generate_3d_xyz``
in ``scripts/run_xtb_physical_features.py`` embeds the whole disconnected graph
in a single ETKDG call, and RDKit then lays the fragments on top of one another.
The closest atom pair in every committed start geometry is therefore an
**inter-fragment** contact at 0.000-0.840 A, far below any physical contact.
The recorded xTB reactions split into two classes: it refuses the geometry
outright ("Some atoms in the start geometry are *very* close"), or the SCF
started from it never converges ("Self consistent charge iterator did not
converge").  This establishes the defect and shows it can make xTB refuse a
start geometry, but it does not establish that the defect is the sole cause
of the SCF failures.

Remedy status
-------------
Embedding and packing each fragment separately, with a padding derived from the
fragment's own radius, removes the inter-fragment overlap: the shortest distance
between two *different* fragments rises from 0.000 / 0.163 / 0.762 / 0.840 A to
3.000 / 3.850 / 4.328 / 4.136 A.  After packing, the closest contact in every
molecule is again an ordinary intra-fragment bond.  It does **not** by itself
recover the rows:

* the three ionic liquids still fail SCC from a valid start geometry, so a
  separate SCF strategy is required; and
* iron pentacarbonyl cannot be repaired this way at all, because its stored
  structure (``[C]=O.[C]=O.[C]=O.[C]=O.[C]=O.[Fe]``, from
  ``InChI=1S/5CO.Fe``) encodes five isolated CO molecules plus a free iron atom
  and therefore carries no Fe-C bonding.  Not every alternative is rejected:
  ``O=C=[Fe](=C=O)(=C=O)(=C=O)=C=O`` sanitises but will not embed, so a
  structure path that both sanitises and embeds is still needed.

Nothing here changes the frozen dataset.  The four rows stay out of the fit set
until a v0.3.14 revision both fixes the embedding step and resolves the SCF and
structure problems.

Usage
-----
    python probes/xtb_fragment_geometry_defect.py --report
    python probes/xtb_fragment_geometry_defect.py --write
    python probes/xtb_fragment_geometry_defect.py --check-cache
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import cast

import numpy as np
from rdkit import Chem
from rdkit.Chem import AllChem
from rdkit.Geometry import Point3D

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_PATH = Path(__file__).resolve().parent / "g1plus_xtb_fragment_geometry_defect.json"
CACHE_ROOT = REPOSITORY_ROOT / "data" / "interim" / "xtb_features"
BASELINE_INPUT = REPOSITORY_ROOT / "probes" / "artifacts" / "v03_features_baseline_input.csv"
PADDING_ANGSTROM = 3.0

# Recorded from the committed, git-ignored xTB cache (data/interim/xtb_features)
# and from the stored xTB stdout of the frozen v0.3 feature run.
TARGETS: dict[str, dict[str, object]] = {
    "GSGLHYXFTXGIAQ-UHFFFAOYSA-M": {
        "name": "1,3-dimethylimidazolium dimethylphosphate",
        "smiles": "COP(=O)([O-])OC.Cn1cc[n+](C)c1",
        "fragments": 2,
        "fragment_atom_counts": [16, 13],
        "cached_min_pair_angstrom": 0.163,
        "cached_min_pair_is_inter_fragment": True,
        "cached_pairs_below_0p5_angstrom": 2,
        "xtb_error_stage": "scf_not_converged",
        "xtb_error_verbatim": "scf: Self consistent charge iterator did not converge",
        "packed_min_inter_fragment_angstrom": 3.850,
        "xtb_rerun_from_packed_geometry": "exit 128, still SCC not converged",
    },
    "IXQYBUDWDLYNMA-UHFFFAOYSA-N": {
        "name": "1-butyl-3-methylimidazolium hexafluorophosphate",
        "smiles": "CCCCn1cc[n+](C)c1.F[P-](F)(F)(F)(F)F",
        "fragments": 2,
        "fragment_atom_counts": [25, 7],
        "cached_min_pair_angstrom": 0.762,
        "cached_min_pair_is_inter_fragment": True,
        "cached_pairs_below_0p5_angstrom": 0,
        "xtb_error_stage": "scf_not_converged",
        "xtb_error_verbatim": "scf: Self consistent charge iterator did not converge",
        "packed_min_inter_fragment_angstrom": 4.328,
        "xtb_rerun_from_packed_geometry": "exit 128, still SCC not converged",
    },
    "JWFPQAXAGSAKRF-UHFFFAOYSA-N": {
        "name": "1-butyl-2,3-dimethylimidazolium hexafluorophosphate",
        "smiles": "CCCCn1cc[n+](C)c1C.F[P-](F)(F)(F)(F)F",
        "fragments": 2,
        "fragment_atom_counts": [28, 7],
        "cached_min_pair_angstrom": 0.840,
        "cached_min_pair_is_inter_fragment": True,
        "cached_pairs_below_0p5_angstrom": 0,
        "xtb_error_stage": "geometry_then_scf",
        "xtb_error_verbatim": "xtb_geoopt: Geometry optimization did not converge",
        "packed_min_inter_fragment_angstrom": 4.136,
        "xtb_rerun_from_packed_geometry": "exit 128, still SCC not converged",
    },
    "FYOFOKCECDGJBF-UHFFFAOYSA-N": {
        "name": "Iron pentacarbonyl",
        "smiles": "[C]=O.[C]=O.[C]=O.[C]=O.[C]=O.[Fe]",
        "fragments": 6,
        "fragment_atom_counts": [2, 2, 2, 2, 2, 1],
        "cached_min_pair_angstrom": 0.0,
        "cached_min_pair_is_inter_fragment": True,
        "cached_pairs_below_0p5_angstrom": 20,
        "xtb_error_stage": "degenerate_start_geometry",
        "xtb_error_verbatim": "Found *very* short distance of  0.000E+00 for O8-O10",
        "packed_min_inter_fragment_angstrom": 3.000,
        "xtb_rerun_from_packed_geometry": "exit 128, still SCC not converged",
    },
}


def positions_from_xyz(xyz_block: str) -> np.ndarray:
    """Return the (n, 3) coordinate array of an XYZ block."""

    lines = xyz_block.strip().splitlines()
    if not lines:
        raise ValueError("empty XYZ block")
    atom_count = int(lines[0])
    body = lines[2 : 2 + atom_count]
    if len(body) != atom_count:
        raise ValueError(
            f"truncated XYZ block: header declares {atom_count} atoms, found {len(body)}"
        )
    return np.array(
        [[float(value) for value in line.split()[1:4]] for line in body],
        dtype=float,
    )


def pairwise_distances(xyz_block: str) -> np.ndarray:
    """Return the full pairwise distance matrix with the diagonal set to +inf."""

    positions = positions_from_xyz(xyz_block)
    matrix = np.linalg.norm(positions[:, None, :] - positions[None, :, :], axis=-1)
    np.fill_diagonal(matrix, np.inf)
    return matrix


def fragment_index(smiles: str) -> dict[int, int]:
    """Map each heavy-atom index of the H-added molecule to its fragment index."""

    molecule = Chem.AddHs(Chem.MolFromSmiles(smiles))
    mapping: dict[int, int] = {}
    for index, atoms in enumerate(Chem.GetMolFrags(molecule, asMols=False)):
        for atom in atoms:
            mapping[int(atom)] = index
    return mapping


def closest_pair(xyz_block: str) -> tuple[float, int, int]:
    """Return (distance, atom_i, atom_j) for the closest pair in an XYZ block."""

    matrix = pairwise_distances(xyz_block)
    i, j = np.unravel_index(int(np.argmin(matrix)), matrix.shape)
    return float(matrix[i, j]), int(i), int(j)


def min_inter_fragment_distance(smiles: str, xyz_block: str) -> float:
    """Return the shortest distance between any two different fragments."""

    mapping = fragment_index(smiles)
    matrix = pairwise_distances(xyz_block)
    best = float("inf")
    for i in range(len(mapping)):
        for j in range(len(mapping)):
            if mapping[i] != mapping[j] and matrix[i, j] < best:
                best = float(matrix[i, j])
    if best == float("inf"):
        raise ValueError("molecule has a single fragment")
    return best


def embed_fragments_separately(
    smiles: str,
    *,
    seed: int = 42,
    padding: float = PADDING_ANGSTROM,
) -> str:
    """Embed every disconnected fragment on its own, then pack them apart.

    Each fragment is embedded and force-field optimised independently, centred
    on its own centroid, and then placed along +x so that consecutive fragments
    are separated by at least ``padding`` angstrom beyond their own radii.
    This is the demonstrated removal of the inter-fragment overlap; it is used
    by this probe only and does not touch the frozen feature pipeline.
    """

    molecule = Chem.AddHs(Chem.MolFromSmiles(smiles))
    if molecule is None:
        raise ValueError(f"invalid SMILES: {smiles!r}")
    fragments = Chem.GetMolFrags(molecule, asMols=True, sanitizeFrags=True)
    indices = Chem.GetMolFrags(molecule, asMols=False)
    conformer = Chem.Conformer(molecule.GetNumAtoms())

    placed: list[tuple[tuple[int, ...], np.ndarray, float]] = []
    for fragment, atoms in zip(fragments, indices):
        if fragment.GetNumAtoms() == 1:
            coordinates = np.zeros((1, 3))
            radius = 0.8
        else:
            working = Chem.Mol(fragment)
            Chem.SanitizeMol(working)
            embedded = AllChem.EmbedMolecule(working, randomSeed=seed) == 0
            if not embedded:
                embedded = (
                    AllChem.EmbedMolecule(
                        working, useRandomCoords=True, randomSeed=seed
                    )
                    == 0
                )
            if not embedded:
                raise ValueError(f"RDKit could not embed fragment of {smiles!r}")
            if AllChem.MMFFHasAllMoleculeParams(working):
                AllChem.MMFFOptimizeMolecule(working, maxIters=2000)
            else:
                AllChem.UFFOptimizeMolecule(working, maxIters=2000)
            coordinates = np.array(working.GetConformer().GetPositions(), dtype=float)
            coordinates -= coordinates.mean(axis=0)
            radius = float(np.linalg.norm(coordinates, axis=1).max())
        placed.append((tuple(int(a) for a in atoms), coordinates, radius))

    cursor = 0.0
    for atoms, coordinates, radius in placed:
        centre = cursor + radius
        for position, coordinate in zip(atoms, coordinates, strict=True):
            conformer.SetAtomPosition(
                position,
                Point3D(
                    float(coordinate[0] + centre),
                    float(coordinate[1]),
                    float(coordinate[2]),
                ),
            )
        cursor = centre + radius + padding

    molecule.AddConformer(conformer, assignId=True)
    return Chem.MolToXYZBlock(molecule)


def measure_cache(cache_root: Path = CACHE_ROOT) -> dict[str, dict[str, object]]:
    """Measure the committed xTB start geometries, if the cache is present."""

    observations: dict[str, dict[str, object]] = {}
    for key, record in TARGETS.items():
        xyz_path = cache_root / key / "input.xyz"
        if not xyz_path.is_file():
            continue
        xyz_block = xyz_path.read_text(encoding="utf-8", errors="replace")
        distance, i, j = closest_pair(xyz_block)
        mapping = fragment_index(str(record["smiles"]))
        matrix = pairwise_distances(xyz_block)
        observations[key] = {
            "min_pair_angstrom": round(distance, 4),
            "atoms": [i, j],
            "closest_pair_fragments": [mapping[i], mapping[j]],
            "molecule_fragments": len(set(mapping.values())),
            "is_inter_fragment": mapping[i] != mapping[j],
            "pairs_below_0p5_angstrom": int(((matrix < 0.5).sum()) / 2),
        }
    return observations


def compare_cache(measured: dict[str, dict[str, object]]) -> list[str]:
    """Compare a live cache measurement against the recorded constants.

    Returns one human-readable mismatch per divergence; an empty list means the
    recorded numbers reproduce exactly.  A missing cache entry is a mismatch, so
    a partial cache can never be reported as a pass.
    """

    problems: list[str] = []
    for key, record in TARGETS.items():
        observation = measured.get(key)
        if observation is None:
            problems.append(f"{key}: no cached start geometry found")
            continue
        if observation["is_inter_fragment"] is not True:
            problems.append(
                f"{key}: closest pair is no longer inter-fragment "
                f"({observation['closest_pair_fragments']})"
            )
        recorded_inter = bool(record["cached_min_pair_is_inter_fragment"])
        if recorded_inter != bool(observation["is_inter_fragment"]):
            problems.append(
                f"{key}: cached_min_pair_is_inter_fragment recorded "
                f"{recorded_inter} but measured {bool(observation['is_inter_fragment'])}"
            )
        recorded_distance = float(record["cached_min_pair_angstrom"])
        measured_distance = float(observation["min_pair_angstrom"])
        if abs(recorded_distance - measured_distance) > 5e-4:
            problems.append(
                f"{key}: min_pair_angstrom recorded {recorded_distance:.3f} "
                f"but measured {measured_distance:.3f}"
            )
        recorded_pairs = int(record["cached_pairs_below_0p5_angstrom"])
        measured_pairs = int(observation["pairs_below_0p5_angstrom"])
        if recorded_pairs != measured_pairs:
            problems.append(
                f"{key}: pairs_below_0p5_angstrom recorded {recorded_pairs} "
                f"but measured {measured_pairs}"
            )
        recorded_fragments = int(record["fragments"])
        measured_fragments = int(observation["molecule_fragments"])
        if recorded_fragments != measured_fragments:
            problems.append(
                f"{key}: fragment count recorded {recorded_fragments} "
                f"but measured {measured_fragments}"
            )
    return problems


def build_payload(cache_root: Path = CACHE_ROOT) -> dict[str, object]:
    """Assemble the probe evidence payload."""

    return {
        "schema_version": 1,
        "probe": "xtb_fragment_geometry_defect",
        "question": (
            "Why do four rows with model_ready=true never enter the 236-row fit set?"
        ),
        "answer": (
            "All four failing molecules are multi-fragment species. The frozen "
            "feature pipeline embeds the whole disconnected graph in one ETKDG "
            "call, so RDKit superimposes the fragments and the xTB start geometry "
            "contains inter-fragment contacts of 0.000-0.840 A. The recorded xTB "
            "reactions split into two classes: it refuses the geometry outright, or "
            "the SCF started from it never converges. That establishes the defect, "
            "but not that it is the sole cause of the SCF failures. Separating the "
            "fragments removes the overlap but does not by itself recover the "
            "rows: the three ionic liquids still fail SCC, and iron pentacarbonyl "
            "additionally needs a structure that actually expresses Fe-C bonding."
        ),
        "roster_arithmetic": {
            "dataset_rows": 246,
            "model_ready_true": 240,
            "feature_rows_status_error": 4,
            "fit_rows": 236,
            "identity": "model_ready_true - feature_errors = fit_rows -> 240 - 4 = 236",
        },
        "defect_location": (
            "scripts/run_xtb_physical_features.py :: generate_3d_xyz "
            "(src/electrolyte_ml/xtb_features.py) -- one EmbedMolecule call for the "
            "entire disconnected multi-fragment graph"
        ),
        "targets": TARGETS,
        "padding_angstrom": PADDING_ANGSTROM,
        "scope_note": (
            "Diagnostic only. No frozen artefact, dataset cell, digest or export "
            "is modified; the four rows remain out of the fit set."
        ),
    }


def verify_evidence(
    committed: dict[str, object], *, cache_root: Path = CACHE_ROOT
) -> list[str]:
    """Return the problems that make a committed evidence file non-verifiable.

    A committed ``cache_measurement`` is treated as a *claim* and is never
    copied into the expected payload, so a forged block cannot be compared
    against itself.  The claim has to be a complete measurement that agrees
    with the recorded constants, and, when the local xTB cache is present, it
    also has to agree with a live re-measurement.
    """

    problems: list[str] = []
    committed = dict(committed)
    claimed = committed.pop("cache_measurement", None)
    if committed != build_payload(cache_root):
        problems.append("committed evidence differs from a freshly built payload")
    if claimed is None:
        return problems
    if not isinstance(claimed, dict):
        problems.append("committed cache_measurement is not an object")
        return problems
    problems.extend(
        f"cache_measurement: {problem}"
        for problem in compare_cache(cast("dict[str, dict[str, object]]", claimed))
    )
    measured = measure_cache(cache_root)
    if not measured:
        problems.append(
            "cache_measurement is present but the local xTB cache is absent, "
            "so it cannot be independently re-measured"
        )
    elif measured != claimed:
        problems.append("cache_measurement differs from a live re-measurement")
    return problems


def _print(payload: dict[str, object]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", action="store_true", help="print the payload")
    parser.add_argument("--write", action="store_true", help="write the evidence JSON")
    parser.add_argument(
        "--check-cache",
        action="store_true",
        help="re-measure the git-ignored xTB cache and compare with the record",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="compare the committed evidence with a freshly built payload",
    )
    args = parser.parse_args(argv)

    payload = build_payload()

    if args.write:
        EVIDENCE_PATH.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        print(f"wrote {EVIDENCE_PATH}")
        return 0

    if args.check:
        committed = json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))
        problems = verify_evidence(committed)
        if problems:
            for problem in problems:
                print(f"EVIDENCE MISMATCH: {problem}", file=sys.stderr)
            return 1
        print("evidence matches")
        return 0

    if args.check_cache:
        measured = measure_cache()
        payload["cache_measurement"] = measured
        problems = compare_cache(measured)
        _print(payload)
        if problems:
            for problem in problems:
                print(f"CACHE MISMATCH: {problem}", file=sys.stderr)
            return 1
        print(f"cache reproduces all {len(TARGETS)} recorded start geometries")
        return 0

    if args.report or not any((args.write, args.check)):
        _print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
