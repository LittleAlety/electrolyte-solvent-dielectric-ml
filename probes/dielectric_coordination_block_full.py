"""Top up the Li+ coordination block (lever 8) so it covers the whole pool.

Shot 13 measured ``full_table_lever4_lever8`` at 0.4915 against
``full_table_lever4`` at 0.5433 and the diagnosis was coverage, not physics:
the released ``dielectric_coordination_block_features.csv`` was built for the 97
scored compounds only, so half of the widened training rows carried NaN in the
block.  This probe extends the same five columns to every compound of the
pool, using the frozen-pipeline row whenever a cached xTB run reproduces the
released feature row and a fresh pinned-thread GFN2 relaxation otherwise.

The stoichiometry of the block is unchanged: same four Li+ seeds, same
``build_li_complex_xyz``, same binding-energy definition.  Rows are written to
a **new** artifact so the released table stays byte-identical.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Mapping, Sequence
from pathlib import Path

PROBES_DIR = Path(__file__).resolve().parent
if str(PROBES_DIR) not in sys.path:
    sys.path.insert(0, str(PROBES_DIR))

import dielectric_coordination_block as v1

from electrolyte_ml.pathing import portable_relative_path
from electrolyte_ml.xtb_features import generate_3d_xyz
from electrolyte_ml.xtb_runner import run_xtb_subprocess, xtb_optimisation_arguments

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = v1.ARTIFACTS_DIR / "dielectric_coordination_block_features_full.csv"
SUMMARY_PATH = REPOSITORY_ROOT / "probes" / "dielectric_coordination_block_full_summary.json"
REFERENCE_PATHS = (v1.FEATURES_PATH, v1.NEW_FEATURES_PATH)
FRESH_SEED_BASE = 42


def _utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def release_references() -> dict[str, dict[str, float]]:
    """The released rows of both feature blocks, keyed by InChIKey."""

    references: dict[str, dict[str, float]] = {}
    for path in REFERENCE_PATHS:
        for row in v1.read_csv_rows(path):
            try:
                references[row["inchikey"]] = {
                    "polarizability_au": float(row["polarizability_au"]),
                    "dipole_D": float(row["dipole_D"]),
                    "total_energy_hartree": float(row["total_energy_hartree"]),
                }
            except (KeyError, TypeError, ValueError):
                continue
    return references


def pool_compounds() -> dict[str, dict[str, str]]:
    scoreboard = v1.build_scoreboard()
    compounds: dict[str, dict[str, str]] = {}
    for row in scoreboard["rows"]:  # type: ignore[index]
        key = str(row["inchikey"])
        compounds.setdefault(key, {"name": str(row.get("name", "")), "smiles": str(row.get("smiles", ""))})
    return compounds


def fresh_relaxation(
    *,
    inchikey: str,
    smiles: str,
    xtb_executable: Path,
    work_root: Path,
    charge: int,
    seed: int,
    timeout_seconds: int,
) -> dict[str, object]:
    """One pinned-thread GFN2 optimisation of the isolated solvent."""

    run_dir = work_root / inchikey / "fresh"
    run_dir.mkdir(parents=True, exist_ok=True)
    v1._clear_directory(run_dir)
    xyz = generate_3d_xyz(smiles, seed=seed)
    (run_dir / "input.xyz").write_text(xyz, encoding="utf-8", newline="\n")
    start = time.perf_counter()
    completed = run_xtb_subprocess(
        xtb_executable,
        xtb_optimisation_arguments("input.xyz", formal_charge=charge),
        cwd=run_dir,
        timeout_seconds=timeout_seconds,
    )
    seconds = time.perf_counter() - start
    text = completed.stdout.decode("utf-8", errors="replace")
    (run_dir / "xtb.out").write_text(text, encoding="utf-8", newline="\n")
    relaxed = v1._total_energy_hartree(text)
    if relaxed is None or not (run_dir / "xtbopt.xyz").is_file():
        raise RuntimeError("the fresh relaxation produced no converged geometry")
    charges = v1.solvent_charge_features(run_dir)
    return {
        "run_dir": run_dir,
        "relaxed_energy_hartree": relaxed,
        "charges": charges,
        "seconds": seconds,
    }


def build_row(
    *,
    inchikey: str,
    name: str,
    smiles: str,
    references: Mapping[str, Mapping[str, float]],
    xtb_executable: Path,
    work_root: Path,
    order: int,
    timeout_seconds: int,
    li_plus_energy: float,
) -> dict[str, object]:
    from rdkit import Chem

    charge = int(Chem.GetFormalCharge(Chem.MolFromSmiles(smiles)))
    row: dict[str, object] = {
        "inchikey": inchikey,
        "name": name,
        "smiles": smiles,
        "complex_charge": charge + 1,
        "solvent_frozen_energy_hartree": "",
        "solvent_relaxed_energy_hartree": "",
        "li_plus_energy_hartree": "",
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
        "conformers_attempted": 0,
        "conformers_converged": 0,
        "best_seed": "",
        "hetero_atoms_within_2_6_a": "",
        "xtb_seconds": "0.000000",
        "status": "error",
        "error": "",
    }
    reference = references.get(inchikey)
    resolved = None
    if reference is not None:
        row["solvent_frozen_energy_hartree"] = f"{reference['total_energy_hartree']:.12g}"
        resolved = v1.resolve_solvent_run(inchikey, reference)
    if resolved is not None and resolved["run"] is not None:
        row["solvent_run"] = str(resolved["matches"][0])
        row["solvent_match_basis"] = str(resolved["match_basis"])
        row["solvent_run_candidates_considered"] = int(resolved["considered"])
        row["solvent_run_matches"] = len(resolved["matches"])
        relaxed = float(resolved["relaxed_energy_hartree"])
        charges = v1.solvent_charge_features(Path(str(resolved["run"])))
    else:
        fresh = fresh_relaxation(
            inchikey=inchikey,
            smiles=smiles,
            xtb_executable=xtb_executable,
            work_root=work_root,
            charge=charge,
            seed=FRESH_SEED_BASE + order,
            timeout_seconds=timeout_seconds,
        )
        row["solvent_run"] = portable_relative_path(Path(str(fresh["run_dir"])), root=REPOSITORY_ROOT)
        row["solvent_match_basis"] = "fresh GFN2 relaxation (no frozen run on disk)"
        row["solvent_run_candidates_considered"] = 0
        row["solvent_run_matches"] = 0
        relaxed = float(fresh["relaxed_energy_hartree"])
        charges = fresh["charges"]
    row["solvent_relaxed_energy_hartree"] = f"{relaxed:.12g}"
    row.update({column: f"{float(value):.10g}" for column, value in charges.items()})

    result = v1.run_li_complex(
        {
            "inchikey": inchikey,
            "name": name,
            "smiles": smiles,
            "xtb": str(xtb_executable),
            "work_root": str(work_root),
            "timeout_seconds": timeout_seconds,
        }
    )
    row["conformers_attempted"] = result.get("conformers_attempted", 0)
    row["conformers_converged"] = result.get("conformers_converged", 0)
    row["best_seed"] = result.get("best_seed", "")
    row["hetero_atoms_within_2_6_a"] = result.get("hetero_atoms_within_2_6_a", "")
    row["xtb_seconds"] = f"{float(result.get('xtb_seconds', 0.0)):.6f}"
    if result.get("status") != "ok":
        row["status"] = str(result.get("status", "error"))
        row["error"] = str(result.get("error", ""))
        return row
    complex_energy = float(result["complex_energy_hartree"])
    delta = complex_energy - relaxed - float(li_plus_energy)
    row["li_plus_energy_hartree"] = f"{float(li_plus_energy):.12g}"
    row["complex_energy_hartree"] = f"{complex_energy:.12g}"
    row["li_binding_energy_ev"] = f"{delta * v1.HARTREE_TO_EV:.10g}"
    row["li_binding_distance_a"] = f"{float(result['li_binding_distance_a']):.10g}"
    row["status"] = "ok"
    row["error"] = ""
    return row


_WORKER_STATE: dict[str, object] = {}


def _init_topup_worker(
    references: Mapping[str, Mapping[str, float]],
    xtb_executable: str,
    work_root: str,
    li_plus_energy: float,
) -> None:
    _WORKER_STATE["references"] = references
    _WORKER_STATE["xtb"] = xtb_executable
    _WORKER_STATE["work_root"] = work_root
    _WORKER_STATE["li_plus_energy"] = li_plus_energy


def _topup_worker(task: tuple[int, str, str, str]) -> dict[str, object]:
    order, key, name, smiles = task
    try:
        return build_row(
            inchikey=key,
            name=name,
            smiles=smiles,
            references=_WORKER_STATE["references"],  # type: ignore[arg-type]
            xtb_executable=Path(str(_WORKER_STATE["xtb"])),
            work_root=Path(str(_WORKER_STATE["work_root"])),
            order=order,
            timeout_seconds=v1.XTB_TIMEOUT_SECONDS,
            li_plus_energy=float(_WORKER_STATE["li_plus_energy"]),
        )
    except Exception as error:  # noqa: BLE001 - a failed compound is data, not a crash
        return {
            "inchikey": key,
            "name": name,
            "smiles": smiles,
            "status": "error",
            "error": str(error),
        }

def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jobs", type=int, default=8)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--xtb", type=str, default="")
    parser.add_argument("--work-root", type=str, default="")
    args = parser.parse_args(argv)

    xtb_executable = Path(args.xtb) if args.xtb else v1.resolve_xtb(None)
    work_root = Path(args.work_root) if args.work_root else v1._default_work_root() / "lever8_topup"
    work_root.mkdir(parents=True, exist_ok=True)
    jobs = max(1, int(args.jobs))
    started = time.perf_counter()

    existing = {row["inchikey"]: row for row in v1.read_csv_rows(v1.ARTIFACTS_DIR / "dielectric_coordination_block_features.csv")}
    compounds = pool_compounds()
    todo = [key for key in sorted(compounds) if existing.get(key, {}).get("status") != "ok"]
    if int(args.limit) > 0:
        todo = todo[: int(args.limit)]
    print(f"xTB: {xtb_executable}")
    print(f"pool compounds {len(compounds)}; already ok {len(existing)} rows; to compute {len(todo)}")

    li_plus_energy = float(
        v1.ensure_li_plus_energy(
            xtb_executable, work_root, timeout_seconds=v1.XTB_TIMEOUT_SECONDS
        )["energy_hartree"]
    )
    print(f"Li+ reference energy {li_plus_energy:.12f} hartree")

    references = release_references()
    tasks = [
        (order, key, compounds[key]["name"], compounds[key]["smiles"]) for order, key in enumerate(todo)
    ]

    rows = v1._parallel_map(
        _topup_worker,
        tasks,
        jobs,
        initializer=_init_topup_worker,
        initargs=(references, str(xtb_executable), str(work_root), float(li_plus_energy)),
    )


    merged = list(existing.values())
    known = set(existing)
    for row in rows:
        key = str(row.get("inchikey"))
        if key in known:
            continue
        merged.append(row)
        known.add(key)
    merged.sort(key=lambda item: str(item.get("inchikey", "")))
    v1.write_csv_rows(OUTPUT_PATH, v1.FEATURE_TABLE_COLUMNS, merged)

    ok = sum(1 for row in merged if str(row.get("status")) == "ok")
    status_counts: dict[str, int] = {}
    for row in merged:
        name = str(row.get("status", "error"))
        status_counts[name] = status_counts.get(name, 0) + 1
    payload = {
        "schema_version": 1,
        "task": "dielectric_coordination_block_full",
        "generated_at_utc": _utc_now(),
        "pool_compounds": len(compounds),
        "computed_here": len(rows),
        "compounds_ok": ok,
        "status_counts": status_counts,
        "output": portable_relative_path(OUTPUT_PATH, root=REPOSITORY_ROOT),
        "wall_seconds": time.perf_counter() - started,
        "jobs": jobs,
    }
    SUMMARY_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n"
    )
    print(f"ok {ok} / {len(merged)} rows written to {OUTPUT_PATH}")
    print(f"status counts {status_counts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
