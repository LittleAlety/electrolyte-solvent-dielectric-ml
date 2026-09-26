"""Run GFN2-xTB physical-feature calculations for v0.2 dielectric compounds.

Every xTB subprocess goes through ``electrolyte_ml.xtb_runner``, which pins the
child to a single OpenMP thread.  Without that pin the optimised geometry, and
therefore every volume-derived column, is not reproducible; see
``reports/xtb_thread_determinism.md``.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import sys
import time
from collections.abc import Mapping, Sequence
from dataclasses import asdict
from pathlib import Path

from rdkit import Chem
from rdkit.Chem import Lipinski, rdMolDescriptors

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from electrolyte_ml.xtb_features import (
    XtbFeatureError,
    XtbParsed,
    clausius_mossotti_proxy,
    generate_3d_xyz,
    molecular_volume_A3,
    onsager_proxy,
    parse_xtb_output,
)
from electrolyte_ml.xtb_runner import (
    run_xtb_subprocess,
    xtb_optimisation_arguments,
)

AVOGADRO = 6.02214076e23
BENCHMARK_MOLECULES = {
    "ethylene_carbonate": "C1COC(=O)O1",
    "dimethyl_carbonate": "COC(=O)OC",
    "dimethoxyethane": "COCCOC",
    "propylene_carbonate": "CC1COC(=O)O1",
    "fluoroethylene_carbonate": "O=C1OCC(F)O1",
}
FEATURE_FIELDS = (
    "inchikey",
    "name",
    "smiles",
    "T_K",
    "dielectric",
    "formal_charge",
    "heavy_atom_count",
    "hbd",
    "hba",
    "tpsa_A2",
    "molecular_volume_A3",
    "molar_volume_m3_mol",
    "dipole_D",
    "polarizability_au",
    "polarizability_A3",
    "mu_sq_over_Vm",
    "alpha_over_Vm",
    "total_energy_hartree",
    "homo_lumo_gap_ev",
    "xtb_seconds",
    "xtb_version",
    "status",
    "error",
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
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _resolve_xtb(explicit: Path | None) -> Path:
    candidates = []
    if explicit is not None:
        candidates.append(explicit)
    if os.environ.get("XTB_EXE"):
        candidates.append(Path(os.environ["XTB_EXE"]))
    discovered = shutil.which("xtb")
    if discovered:
        candidates.append(Path(discovered))
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        candidates.append(
            Path(local_app_data)
            / "electrolyte-ml"
            / "tools"
            / "xtb-6.7.1"
            / "extracted"
            / "xtb-6.7.1"
            / "bin"
            / "xtb.exe"
        )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(
        "xTB executable not found; pass --xtb or set XTB_EXE"
    )


def _slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_")[:120]


def _xtb_version(output: str) -> str:
    match = re.search(r"xtb version\s+(\S+)", output)
    return match.group(1) if match else ""


def _text_sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _canonical_smiles(smiles: str) -> str:
    molecule = Chem.MolFromSmiles(smiles)
    if molecule is None:
        raise XtbFeatureError(f"invalid SMILES: {smiles!r}")
    return Chem.MolToSmiles(molecule, canonical=True)


def _cache_key(smiles: str, formal_charge: int, seed: int) -> str:
    payload = f"{_canonical_smiles(smiles)}|{formal_charge}|{seed}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _xyz_symbols(xyz_block: str) -> list[str]:
    lines = xyz_block.strip().splitlines()
    if not lines:
        raise XtbFeatureError("empty XYZ block")
    try:
        atom_count = int(lines[0])
    except ValueError as error:
        raise XtbFeatureError("invalid XYZ atom count") from error
    if len(lines) < atom_count + 2:
        raise XtbFeatureError("truncated XYZ block")
    return [lines[index + 2].split()[0] for index in range(atom_count)]


def _molecule_symbols(smiles: str) -> list[str]:
    molecule = Chem.MolFromSmiles(smiles)
    if molecule is None:
        raise XtbFeatureError(f"invalid SMILES: {smiles!r}")
    molecule = Chem.AddHs(molecule)
    return [atom.GetSymbol() for atom in molecule.GetAtoms()]


def _executable_fingerprint(path: Path) -> dict[str, object]:
    stat = path.stat()
    return {
        "path": str(path.resolve()),
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
    }


def _manifest_path(run_dir: Path) -> Path:
    return run_dir / "cache_manifest.json"


def _read_manifest(run_dir: Path) -> dict[str, object] | None:
    path = _manifest_path(run_dir)
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _write_manifest(
    run_dir: Path,
    *,
    smiles: str,
    formal_charge: int,
    seed: int,
    input_xyz: str,
    optimized_xyz: str,
    output_text: str,
    xtb_executable: Path,
) -> None:
    payload = {
        "cache_key": _cache_key(smiles, formal_charge, seed),
        "canonical_smiles": _canonical_smiles(smiles),
        "formal_charge": formal_charge,
        "seed": seed,
        "input_sha256": _text_sha256(input_xyz),
        "optimized_sha256": _text_sha256(optimized_xyz),
        "output_sha256": _text_sha256(output_text),
        "xtb_version": _xtb_version(output_text),
        "xtb_executable": _executable_fingerprint(xtb_executable),
    }
    _manifest_path(run_dir).write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _valid_cache(
    run_dir: Path,
    *,
    smiles: str,
    formal_charge: int,
    seed: int,
    expected_input_xyz: str,
    xtb_executable: Path,
) -> tuple[Path, str, str] | None:
    output_path = run_dir / "xtb.out"
    optimized_path = run_dir / "xtbopt.xyz"
    if not output_path.is_file() or not optimized_path.is_file():
        return None
    output_text = output_path.read_bytes().decode("utf-8", errors="replace")
    optimized_xyz = optimized_path.read_text(encoding="utf-8", errors="replace")
    manifest = _read_manifest(run_dir)
    if manifest is None:
        input_path = run_dir / "input.xyz"
        if not input_path.is_file():
            return None
        existing_input = input_path.read_text(encoding="utf-8", errors="replace")
        if existing_input != expected_input_xyz:
            return None
        if _xyz_symbols(optimized_xyz) != _molecule_symbols(smiles):
            return None
        try:
            _parse_xtb_run(output_text, optimized_path)
        except XtbFeatureError:
            return None
        _write_manifest(
            run_dir,
            smiles=smiles,
            formal_charge=formal_charge,
            seed=seed,
            input_xyz=existing_input,
            optimized_xyz=optimized_xyz,
            output_text=output_text,
            xtb_executable=xtb_executable,
        )
        manifest = _read_manifest(run_dir)
    if manifest is None:
        return None
    expected_manifest = {
        "cache_key": _cache_key(smiles, formal_charge, seed),
        "canonical_smiles": _canonical_smiles(smiles),
        "formal_charge": formal_charge,
        "seed": seed,
        "input_sha256": _text_sha256(expected_input_xyz),
        "optimized_sha256": _text_sha256(optimized_xyz),
        "output_sha256": _text_sha256(output_text),
        "xtb_version": _xtb_version(output_text),
        "xtb_executable": _executable_fingerprint(xtb_executable),
    }
    if manifest != expected_manifest:
        return None
    return output_path, optimized_path, output_text


def _clear_run_artifacts(run_dir: Path) -> None:
    for path in run_dir.iterdir():
        if path.is_file() or path.is_symlink():
            path.unlink()


def _parse_xtb_run(output_text: str, optimized_path: Path) -> XtbParsed:
    if "normal termination of xtb" in output_text:
        return parse_xtb_output(output_text)
    if optimized_path.with_name(".xtboptok").is_file():
        return parse_xtb_output(
            f"{output_text}\nnormal termination of xtb\n"
        )
    return parse_xtb_output(output_text)


def run_xtb(
    *,
    smiles: str,
    label: str,
    xtb_executable: Path,
    work_dir: Path,
    seed: int,
    timeout_seconds: int,
) -> dict[str, object]:
    molecule = Chem.MolFromSmiles(smiles)
    if molecule is None:
        raise XtbFeatureError(f"invalid SMILES for {label}: {smiles!r}")
    formal_charge = Chem.GetFormalCharge(molecule)
    cache_key = _cache_key(smiles, formal_charge, seed)
    expected_input_xyz = generate_3d_xyz(smiles, seed=seed)
    legacy_run_dir = work_dir / _slug(label)
    keyed_run_dir = work_dir / f"{_slug(label)}__{cache_key[:12]}"
    run_dir = legacy_run_dir if _valid_cache(
        legacy_run_dir,
        smiles=smiles,
        formal_charge=formal_charge,
        seed=seed,
        expected_input_xyz=expected_input_xyz,
        xtb_executable=xtb_executable,
    ) else keyed_run_dir
    run_dir.mkdir(parents=True, exist_ok=True)
    output_path = run_dir / "xtb.out"
    optimized_path = run_dir / "xtbopt.xyz"
    cached = _valid_cache(
        run_dir,
        smiles=smiles,
        formal_charge=formal_charge,
        seed=seed,
        expected_input_xyz=expected_input_xyz,
        xtb_executable=xtb_executable,
    )
    if cached is not None:
        _, _, output_text = cached
        try:
            parsed = _parse_xtb_run(output_text, optimized_path)
        except XtbFeatureError:
            pass
        else:
            return {
                **asdict(parsed),
                "optimized_xyz": optimized_path.read_text(
                    encoding="utf-8",
                    errors="replace",
                ),
                "xtb_seconds": 0.0,
                "xtb_version": _xtb_version(output_text),
                "status": "cached",
                "error": "",
            }

    _clear_run_artifacts(run_dir)
    input_path = run_dir / "input.xyz"
    input_path.write_text(expected_input_xyz, encoding="utf-8")
    start = time.perf_counter()
    completed = run_xtb_subprocess(
        xtb_executable,
        xtb_optimisation_arguments(input_path.name, formal_charge=formal_charge),
        cwd=run_dir,
        timeout_seconds=timeout_seconds,
    )
    elapsed = time.perf_counter() - start
    output_path.write_bytes(completed.stdout)
    if completed.returncode != 0:
        raise XtbFeatureError(
            f"xTB failed for {label} with exit code {completed.returncode}"
        )
    if not optimized_path.is_file():
        raise XtbFeatureError(f"xTB did not produce expected files for {label}")
    output_text = completed.stdout.decode("utf-8", errors="replace")
    optimized_xyz = optimized_path.read_text(encoding="utf-8", errors="replace")
    if _xyz_symbols(optimized_xyz) != _molecule_symbols(smiles):
        raise XtbFeatureError(f"xTB optimized atom symbols changed for {label}")
    parsed = _parse_xtb_run(output_text, optimized_path)
    _write_manifest(
        run_dir,
        smiles=smiles,
        formal_charge=formal_charge,
        seed=seed,
        input_xyz=expected_input_xyz,
        optimized_xyz=optimized_xyz,
        output_text=output_text,
        xtb_executable=xtb_executable,
    )
    return {
        **asdict(parsed),
        "optimized_xyz": optimized_xyz,
        "xtb_seconds": elapsed,
        "xtb_version": _xtb_version(output_text),
        "status": "ok",
        "error": "",
    }


def _feature_row(
    source_row: Mapping[str, str],
    result: Mapping[str, object],
) -> dict[str, object]:
    molecule = Chem.MolFromSmiles(source_row["smiles"])
    if molecule is None:
        raise XtbFeatureError(f"invalid v0.2 SMILES for {source_row['name']}")
    optimized_xyz = str(result["optimized_xyz"])
    volume = molecular_volume_A3(optimized_xyz)
    molar_volume = volume * 1e-30 * AVOGADRO
    dipole = float(result["dipole_debye"])
    polarizability_au = float(result["polarizability_au"])
    polarizability_A3 = polarizability_au * 0.148184743
    return {
        "inchikey": source_row["inchikey"],
        "name": source_row["name"],
        "smiles": source_row["smiles"],
        "T_K": source_row["T_K"],
        "dielectric": source_row["dielectric"],
        "formal_charge": str(Chem.GetFormalCharge(molecule)),
        "heavy_atom_count": str(molecule.GetNumHeavyAtoms()),
        "hbd": str(Lipinski.NumHDonors(molecule)),
        "hba": str(Lipinski.NumHAcceptors(molecule)),
        "tpsa_A2": f"{rdMolDescriptors.CalcTPSA(molecule):.8g}",
        "molecular_volume_A3": f"{volume:.8g}",
        "molar_volume_m3_mol": f"{molar_volume:.8g}",
        "dipole_D": f"{dipole:.8g}",
        "polarizability_au": f"{polarizability_au:.8g}",
        "polarizability_A3": f"{polarizability_A3:.8g}",
        "mu_sq_over_Vm": f"{onsager_proxy(dipole, molar_volume):.8g}",
        "alpha_over_Vm": f"{clausius_mossotti_proxy(polarizability_au, volume):.8g}",
        "total_energy_hartree": f"{float(result['total_energy_hartree']):.12g}",
        "homo_lumo_gap_ev": f"{float(result['homo_lumo_gap_ev']):.8g}",
        "xtb_seconds": f"{float(result['xtb_seconds']):.8g}",
        "xtb_version": str(result["xtb_version"]),
        "status": str(result["status"]),
        "error": str(result["error"]),
    }


def _error_feature_row(
    source_row: Mapping[str, str],
    error: str,
) -> dict[str, object]:
    return {
        **{field: "" for field in FEATURE_FIELDS},
        "inchikey": source_row["inchikey"],
        "name": source_row["name"],
        "smiles": source_row["smiles"],
        "T_K": source_row["T_K"],
        "dielectric": source_row["dielectric"],
        "status": "error",
        "error": error,
    }


def run_benchmark(
    *,
    xtb_executable: Path,
    work_dir: Path,
    timeout_seconds: int,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for index, (name, smiles) in enumerate(BENCHMARK_MOLECULES.items()):
        start = time.perf_counter()
        result = run_xtb(
            smiles=smiles,
            label=f"benchmark_{name}",
            xtb_executable=xtb_executable,
            work_dir=work_dir,
            seed=42 + index,
            timeout_seconds=timeout_seconds,
        )
        rows.append(
            {
                "name": name,
                "smiles": smiles,
                "atom_count": str(
                    Chem.AddHs(Chem.MolFromSmiles(smiles)).GetNumAtoms()
                ),
                "heavy_atom_count": str(Chem.MolFromSmiles(smiles).GetNumHeavyAtoms()),
                "seconds": f"{time.perf_counter() - start:.6f}",
                "total_energy_hartree": f"{float(result['total_energy_hartree']):.12g}",
                "dipole_D": f"{float(result['dipole_debye']):.8g}",
                "polarizability_au": f"{float(result['polarizability_au']):.8g}",
                "status": str(result["status"]),
            }
        )
    return rows


def run_features(
    *,
    input_rows: Sequence[Mapping[str, str]],
    exclusion_keys: set[str],
    xtb_executable: Path,
    work_dir: Path,
    output_path: Path,
    timeout_seconds: int,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for index, source_row in enumerate(input_rows):
        if source_row["inchikey"] in exclusion_keys:
            continue
        try:
            result = run_xtb(
                smiles=source_row["smiles"],
                label=source_row["inchikey"],
                xtb_executable=xtb_executable,
                work_dir=work_dir,
                seed=42 + index,
                timeout_seconds=timeout_seconds,
            )
            output_row = _feature_row(source_row, result)
        except Exception as error:  # noqa: BLE001
            output_row = _error_feature_row(source_row, str(error))
        rows.append(output_row)
        write_csv_rows(output_path, FEATURE_FIELDS, rows)
        print(
            json.dumps(
                {
                    "processed": index + 1,
                    "total_input": len(input_rows),
                    "name": source_row["name"],
                    "status": output_row["status"],
                }
            )
        )
    return rows


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=REPOSITORY_ROOT / "data" / "dielectric_v02.csv",
    )
    parser.add_argument(
        "--exclusions",
        type=Path,
        default=REPOSITORY_ROOT / "data" / "processed" / "dielectric_v02_exclusions.csv",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=REPOSITORY_ROOT
        / "data"
        / "processed"
        / "dielectric_physical_features.csv",
    )
    parser.add_argument(
        "--work-dir",
        type=Path,
        default=REPOSITORY_ROOT / "data" / "interim" / "xtb_features",
    )
    parser.add_argument(
        "--benchmark-output",
        type=Path,
        default=REPOSITORY_ROOT / "probes" / "p5b_xtb_timing.csv",
    )
    parser.add_argument("--xtb", type=Path, default=None)
    parser.add_argument("--benchmark", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--timeout", type=int, default=600)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    xtb_executable = _resolve_xtb(args.xtb)
    if args.benchmark:
        rows = run_benchmark(
            xtb_executable=xtb_executable,
            work_dir=args.work_dir / "benchmark",
            timeout_seconds=args.timeout,
        )
        fields = (
            "name",
            "smiles",
            "atom_count",
            "heavy_atom_count",
            "seconds",
            "total_energy_hartree",
            "dipole_D",
            "polarizability_au",
            "status",
        )
        write_csv_rows(args.benchmark_output, fields, rows)
        print(json.dumps({"benchmark": rows}, ensure_ascii=False, indent=2))
        return 0

    input_rows = read_csv_rows(args.input)
    if args.limit > 0:
        input_rows = input_rows[: args.limit]
    exclusions = read_csv_rows(args.exclusions) if args.exclusions.is_file() else []
    exclusion_keys = {row["inchikey"] for row in exclusions}
    rows = run_features(
        input_rows=input_rows,
        exclusion_keys=exclusion_keys,
        xtb_executable=xtb_executable,
        work_dir=args.work_dir,
        output_path=args.output,
        timeout_seconds=args.timeout,
    )
    failures = [row for row in rows if row["status"] == "error"]
    result = {
        "input_compounds": len(input_rows),
        "excluded_compounds": len(exclusion_keys),
        "processed_compounds": len(rows),
        "successful_compounds": len(rows) - len(failures),
        "failed_compounds": len(failures),
        "output": str(args.output),
        "xtb": str(xtb_executable),
    }
    print(json.dumps(result, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
