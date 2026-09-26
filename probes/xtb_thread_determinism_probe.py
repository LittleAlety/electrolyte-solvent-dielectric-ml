"""Does the xTB-derived dielectric volume column depend on the thread count?

Week 11 recorded that ``data/processed/dielectric_physical_features_v11plus_new.csv``
is not bit-reproducible: at ``OMP_NUM_THREADS`` 1/2/4/8/16 the two volume export
columns moved between 93.392 and 93.432 A^3 (and 60.632-60.640 A^3).  RDKit's
``ComputeMolVolume`` had already been cleared by ten repeats and ``generate_3d_xyz``
by five, so the drift had to enter on the xTB geometry-optimisation path.  This
probe measures that claim directly.

Design
------
Two arms, same start ``input.xyz``, same command line; only the child environment
differs (see ``--arms``):

``unpinned``
    ``os.environ.copy()`` with ``OMP_NUM_THREADS``/``MKL_NUM_THREADS`` set to the
    requested value -- the Week-11 invocation, reproduced verbatim.
``pinned``
    ``electrolyte_ml.xtb_runner.run_xtb_subprocess``, which pins the child to one
    OpenMP thread.  For this arm the *parent* environment is deliberately set to
    the requested thread count first, so the arm also demonstrates that a caller's
    setting can no longer leak into the numbers.

Every (arm, requested thread count) is repeated ``--repeats`` times.  That
separates two different failures: a *cross-thread* shift (different thread counts
land on different geometries) from plain *run-to-run* instability (one thread
count lands on different geometries).

Each repetition gets a working directory cleared of xTB scratch files, because a
leftover ``xtbrestart`` is reused as an SCF restart and perturbs the gradient even
at one thread.

The probe writes only ``probes/xtb_thread_determinism_probe_summary.json`` and a
scratch work directory; it never touches a feature table.
"""

from __future__ import annotations

import argparse
import contextlib
import csv
import hashlib
import json
import os
import sys
import time
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
for _extra in (REPOSITORY_ROOT / "src", REPOSITORY_ROOT / "scripts"):
    if str(_extra) not in sys.path:
        sys.path.insert(0, str(_extra))

from run_xtb_physical_features import (
    _clear_run_artifacts,
    _parse_xtb_run,
    _resolve_xtb,
)

from electrolyte_ml.xtb_features import (
    clausius_mossotti_proxy,
    molecular_volume_A3,
    onsager_proxy,
)
from electrolyte_ml.xtb_runner import (
    DETERMINISTIC_THREADS,
    reported_omp_threads,
    run_xtb_subprocess,
    xtb_optimisation_arguments,
)

AVOGADRO = 6.02214076e23
SUMMARY_PATH = REPOSITORY_ROOT / "probes" / "xtb_thread_determinism_probe_summary.json"
FROZEN_CACHE = REPOSITORY_ROOT / "data" / "interim" / "xtb_features_v11plus"
RECORDED_FEATURES = (
    REPOSITORY_ROOT / "data" / "processed" / "dielectric_physical_features_v11plus_new.csv"
)
DEFAULT_WORK_ROOT = REPOSITORY_ROOT / "data" / "interim" / "xtb_thread_determinism"
ARMS = ("unpinned", "pinned")
VOLUME_COLUMNS = (
    "molecular_volume_A3",
    "molar_volume_m3_mol",
    "mu_sq_over_Vm",
    "alpha_over_Vm",
)

# The two frozen rows whose volume columns the Week 11 rerun could not reproduce.
TARGETS = (
    {
        "name": "2-chloro-2-methylpropane",
        "inchikey": "NBRKLOOSMBRFMH-UHFFFAOYSA-N",
        "smiles": "CC(C)(C)Cl",
    },
    {
        "name": "1,1,1-trifluoroethane",
        "inchikey": "UJPMYEOUBPIPHQ-UHFFFAOYSA-N",
        "smiles": "CC(F)(F)F",
    },
)


def frozen_run_dir(inchikey: str) -> Path:
    """The single cached run directory for a frozen row."""

    matches = sorted(
        path
        for path in FROZEN_CACHE.glob(f"{inchikey}*")
        if (path / "cache_manifest.json").is_file()
    )
    if len(matches) != 1:
        raise SystemExit(
            f"expected one cached run for {inchikey}, found {len(matches)}"
        )
    return matches[0]


def recorded_columns(inchikey: str) -> dict[str, float]:
    """The four volume-derived columns as committed in the frozen feature table."""

    with RECORDED_FEATURES.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if row["inchikey"] == inchikey:
                return {name: float(row[name]) for name in VOLUME_COLUMNS}
    raise SystemExit(f"{inchikey} is missing from {RECORDED_FEATURES}")


def week11_environment(threads: int) -> dict[str, str]:
    """The pre-fix child environment, reproduced verbatim from Week 11."""

    environment = os.environ.copy()
    environment["OMP_NUM_THREADS"] = str(threads)
    environment["MKL_NUM_THREADS"] = str(threads)
    return environment


@contextlib.contextmanager
def parent_thread_setting(threads: int):
    """Pollute the parent's thread setting for the duration of the block."""

    names = ("OMP_NUM_THREADS", "MKL_NUM_THREADS")
    saved = {name: os.environ.get(name) for name in names}
    os.environ["OMP_NUM_THREADS"] = str(threads)
    os.environ["MKL_NUM_THREADS"] = str(threads)
    try:
        yield
    finally:
        for name, value in saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def relative_spread(values: list[float]) -> float:
    """(max - min) / |mean|, or 0.0 when every value is identical."""

    low, high = min(values), max(values)
    if low == high:
        return 0.0
    mean = sum(values) / len(values)
    if mean == 0:
        return float("inf")
    return (high - low) / abs(mean)


def measure(
    *,
    arm: str,
    target: dict[str, str],
    requested_threads: int,
    repeats: int,
    work_root: Path,
    xtb: Path,
    timeout: int,
) -> dict[str, object]:
    """Repeat one (arm, molecule, thread count) cell and summarise it."""

    inchikey = target["inchikey"]
    run_dir = frozen_run_dir(inchikey)
    manifest = json.loads((run_dir / "cache_manifest.json").read_text(encoding="utf-8"))
    start_geometry = (run_dir / "input.xyz").read_text(encoding="utf-8")
    arguments = xtb_optimisation_arguments(
        "input.xyz", formal_charge=int(manifest["formal_charge"])
    )
    repetitions: list[dict[str, object]] = []
    for repeat in range(repeats):
        cell = work_root / arm / f"{inchikey}_{requested_threads}_{repeat}"
        cell.mkdir(parents=True, exist_ok=True)
        # A leftover xtbrestart is reused as an SCF restart and perturbs the
        # converged gradient even at one thread; the frozen runner clears the
        # run directory for the same reason.
        _clear_run_artifacts(cell)
        (cell / "input.xyz").write_text(start_geometry, encoding="utf-8", newline="\n")
        start = time.perf_counter()
        with contextlib.ExitStack() as stack:
            if arm == "pinned":
                stack.enter_context(parent_thread_setting(requested_threads))
                completed = run_xtb_subprocess(
                    xtb, arguments, cwd=cell, timeout_seconds=timeout
                )
            else:
                completed = run_xtb_subprocess(
                    xtb,
                    arguments,
                    cwd=cell,
                    timeout_seconds=timeout,
                    environment=week11_environment(requested_threads),
                )
        seconds = time.perf_counter() - start
        output_text = completed.stdout.decode("utf-8", errors="replace")
        optimized_path = cell / "xtbopt.xyz"
        optimized_xyz = optimized_path.read_text(encoding="utf-8", errors="replace")
        parsed = _parse_xtb_run(output_text, optimized_path)
        volume = molecular_volume_A3(optimized_xyz)
        molar_volume = volume * 1e-30 * AVOGADRO
        repetitions.append(
            {
                "repeat": repeat,
                "returncode": completed.returncode,
                "reported_omp_threads": reported_omp_threads(output_text),
                "optimized_sha256": hashlib.sha256(
                    optimized_xyz.encode("utf-8")
                ).hexdigest(),
                "seconds": round(seconds, 3),
                "columns": {
                    "molecular_volume_A3": volume,
                    "molar_volume_m3_mol": molar_volume,
                    "mu_sq_over_Vm": onsager_proxy(parsed.dipole_debye, molar_volume),
                    "alpha_over_Vm": clausius_mossotti_proxy(
                        parsed.polarizability_au, volume
                    ),
                },
            }
        )
    geometry_hashes = {str(item["optimized_sha256"]) for item in repetitions}
    return {
        "requested_threads": requested_threads,
        "repeats": repeats,
        "distinct_optimized_geometries": len(geometry_hashes),
        "reported_omp_threads": sorted(
            {
                item["reported_omp_threads"]
                for item in repetitions
                if item["reported_omp_threads"] is not None
            }
        ),
        "returncodes": sorted({int(item["returncode"]) for item in repetitions}),
        "columns": {
            name: {
                "values": [item["columns"][name] for item in repetitions],
                "relative_spread": relative_spread(
                    [item["columns"][name] for item in repetitions]
                ),
            }
            for name in VOLUME_COLUMNS
        },
        "repetitions": repetitions,
    }


def parse_threads(value: str) -> list[int]:
    threads = [int(part) for part in value.split(",") if part.strip()]
    if not threads or any(thread < 1 for thread in threads):
        raise argparse.ArgumentTypeError("thread counts must be positive integers")
    return threads


def parse_arms(value: str) -> list[str]:
    arms = [part.strip() for part in value.split(",") if part.strip()]
    unknown = [arm for arm in arms if arm not in ARMS]
    if not arms or unknown:
        raise argparse.ArgumentTypeError(f"arms must be drawn from {ARMS}")
    return arms


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--threads", type=parse_threads, default=parse_threads("1,2,4,8,16"))
    parser.add_argument("--arms", type=parse_arms, default=parse_arms(",".join(ARMS)))
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--xtb", type=Path, default=None)
    parser.add_argument("--work-dir", type=Path, default=DEFAULT_WORK_ROOT)
    parser.add_argument("--output", type=Path, default=SUMMARY_PATH)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.repeats < 1:
        raise SystemExit("--repeats must be at least 1")
    xtb = args.xtb or _resolve_xtb(None)
    work_root = args.work_dir
    work_root.mkdir(parents=True, exist_ok=True)

    arms: dict[str, dict[str, object]] = {}
    for arm in args.arms:
        arms[arm] = {}
        for target in TARGETS:
            cells: dict[str, object] = {}
            for threads in args.threads:
                cell = measure(
                    arm=arm,
                    target=target,
                    requested_threads=threads,
                    repeats=args.repeats,
                    work_root=work_root,
                    xtb=xtb,
                    timeout=args.timeout,
                )
                cells[str(threads)] = cell
                print(
                    json.dumps(
                        {
                            "arm": arm,
                            "molecule": target["name"],
                            "requested_threads": threads,
                            "distinct_geometries": cell["distinct_optimized_geometries"],
                            "max_relative_spread": max(
                                value["relative_spread"]
                                for value in cell["columns"].values()  # type: ignore[union-attr]
                            ),
                        }
                    ),
                    flush=True,
                )
            arms[arm][target["name"]] = cells

    frozen_rows = []
    for target in TARGETS:
        run_dir = frozen_run_dir(target["inchikey"])
        manifest = json.loads((run_dir / "cache_manifest.json").read_text(encoding="utf-8"))
        frozen_rows.append(
            {
                "name": target["name"],
                "inchikey": target["inchikey"],
                "smiles": target["smiles"],
                "seed": manifest["seed"],
                "cache_dir": str(run_dir.relative_to(REPOSITORY_ROOT)),
                "input_sha256": manifest["input_sha256"],
                "frozen_optimized_sha256": manifest["optimized_sha256"],
                "frozen_columns": recorded_columns(target["inchikey"]),
            }
        )

    def spread(arm: str, molecule: str) -> tuple[float, int]:
        worst = 0.0
        geometries = 0
        for cell in arms[arm][molecule].values():  # type: ignore[union-attr]
            geometries = max(geometries, int(cell["distinct_optimized_geometries"]))
            for value in cell["columns"].values():
                worst = max(worst, float(value["relative_spread"]))
        return worst, geometries

    pinned_worst = 0.0
    unpinned_worst = 0.0
    pinned_geometries = 0
    unpinned_geometries = 0
    for target in TARGETS:
        if "pinned" in arms:
            worst, count = spread("pinned", target["name"])
            pinned_worst = max(pinned_worst, worst)
            pinned_geometries = max(pinned_geometries, count)
        if "unpinned" in arms:
            worst, count = spread("unpinned", target["name"])
            unpinned_worst = max(unpinned_worst, worst)
            unpinned_geometries = max(unpinned_geometries, count)

    threshold = 1e-3
    payload: dict[str, object] = {
        "probe": "xtb_thread_determinism_probe",
        "schema_version": 1,
        "question": "Do the xTB-derived dielectric volume columns depend on the thread count?",
        "root_cause": (
            "xTB 6.7.1 parallelises the SCF and the analytic gradient over OpenMP "
            "threads; floating-point reduction is not associative, so the converged "
            "gradient carries a thread-count- and run-dependent perturbation. --opt "
            "stops on a gradient-norm criterion, which turns that perturbation into a "
            "slightly different xtbopt.xyz, and RDKit's ComputeMolVolume quantises on a "
            "0.008 A^3 grid, so one flipped grid cell moves the volume column."
        ),
        "fix": (
            "electrolyte_ml.xtb_runner.run_xtb_subprocess pins the child to "
            f"OMP_NUM_THREADS={DETERMINISTIC_THREADS} (plus MKL_NUM_THREADS, "
            "OMP_DYNAMIC=FALSE, MKL_DYNAMIC=FALSE) and is now the only xTB launcher."
        ),
        "method": {
            "start_geometry": "the frozen cached input.xyz of each row",
            "command": "xtb input.xyz --opt --gfn 2 --chrg <q> --uhf 0",
            "arms": {
                "unpinned": "child env OMP_NUM_THREADS/MKL_NUM_THREADS = requested value (Week 11 invocation)",
                "pinned": "parent env is set to the requested value, launcher overrides it to 1",
            },
            "columns": list(VOLUME_COLUMNS),
        },
        "xtb": {
            "executable": str(xtb),
            "sha256": hashlib.sha256(xtb.read_bytes()).hexdigest(),
        },
        "deterministic_threads": DETERMINISTIC_THREADS,
        "requested_thread_sweep": args.threads,
        "arms_requested": args.arms,
        "repeats": args.repeats,
        "frozen_rows": frozen_rows,
        "arms": arms,
        "verdict": {
            "acceptance_threshold_relative": threshold,
            "pinned_max_relative_spread": pinned_worst,
            "pinned_max_distinct_geometries": pinned_geometries,
            "unpinned_max_relative_spread": unpinned_worst,
            "unpinned_max_distinct_geometries": unpinned_geometries,
            "acceptance_passed": (
                "pinned" in arms and pinned_worst <= threshold and pinned_geometries == 1
            ),
            "note": (
                "pinned_max_distinct_geometries is the largest number of distinct "
                "xtbopt.xyz seen within one (molecule, requested threads) cell; 1 means "
                "bit-reproducible, and across the whole pinned sweep it also means "
                "cross-thread stable."
            ),
        },
    }
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps(payload["verdict"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
