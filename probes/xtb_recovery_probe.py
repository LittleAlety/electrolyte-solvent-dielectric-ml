"""Recovery-feasibility probe for the four feature-failed v0.3 rows.

Companion to ``probes/xtb_fragment_geometry_defect.py``.  That probe
established the defect: four ``model_ready=true`` rows never enter the
236-row fit set because ``generate_3d_xyz()`` embeds a whole disconnected
graph in one ETKDG call, so the fragments sit on top of one another.  Packing
the fragments apart removes the overlap, yet all four rows still finish at
exit 128.

This probe asks the next question and nothing more: **is there a reproducible
protocol under which those species reach** ``normal termination of xtb``?
Answering it decides whether a v0.3.14 revision is worth attempting at all.

It is a feasibility probe.  No dataset cell, frozen feature table, digest,
exclusion list or export bundle is modified, and the four rows stay out of
the fit set.

Usage
-----
    python probes/xtb_recovery_probe.py --ion-pairs --write
    python probes/xtb_recovery_probe.py --fe-structures --write
    python probes/xtb_recovery_probe.py --report
    python probes/xtb_recovery_probe.py --check
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

from rdkit import Chem
from rdkit.Chem import AllChem

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
for _extra in (REPOSITORY_ROOT, REPOSITORY_ROOT / "src"):
    if str(_extra) not in sys.path:
        sys.path.insert(0, str(_extra))

from electrolyte_ml.xtb_features import XtbFeatureError, parse_xtb_output
from probes.xtb_fragment_geometry_defect import (
    TARGETS as DEFECT_TARGETS,
)
from probes.xtb_fragment_geometry_defect import (
    embed_fragments_separately,
)

EVIDENCE_PATH = Path(__file__).resolve().parent / "g1plus_xtb_recovery_probe.json"
DEFAULT_WORK_DIR = REPOSITORY_ROOT / "data" / "interim" / "xtb_recovery_probe"
DEFAULT_TIMEOUT_SECONDS = 150
NORMAL_TERMINATION = "normal termination of xtb"
TAIL_LINES = 25
# scripts/run_xtb_physical_features.py accepts a run without the stdout marker
# when this sentinel exists; xTB 6.7.1 prints the marker to stderr, so in
# practice the sentinel is what fires.
OPT_MARKER_FILE = ".xtboptok"
GEOOPT_CONVERGED = "GEOMETRY OPTIMIZATION CONVERGED"
GEOOPT_FAILED = "FAILED TO CONVERGE GEOMETRY OPTIMIZATION"
GRADIENT_NORM_RE = re.compile(
    r"GRADIENT NORM\s+([-+]?\d+(?:\.\d+)?(?:[Ee][-+]?\d+)?)"
)

ION_PAIR_KEYS = (
    "GSGLHYXFTXGIAQ-UHFFFAOYSA-M",
    "IXQYBUDWDLYNMA-UHFFFAOYSA-N",
    "JWFPQAXAGSAKRF-UHFFFAOYSA-N",
)
FE_KEY = "FYOFOKCECDGJBF-UHFFFAOYSA-N"

# Controls for the protocol-sensitivity experiment: rows that already succeed
# under the frozen protocol, so re-running them isolates the flag's effect.
CONTROL_KEYS = (
    "ALYCOCULEAWWJO-UHFFFAOYSA-N",
    "AFBPFSWMIHJQDM-UHFFFAOYSA-N",
    "BDERNNFJNOPAEC-UHFFFAOYSA-N",
)
CONTROL_STRATEGY_IDS = ("frozen", "etemp_5000")

# Exactly the frozen invocation built by scripts/run_xtb_physical_features.py.
FROZEN_FLAGS = ("--opt", "--gfn", "2", "--chrg", "0", "--uhf", "0")

# Every variant keeps the frozen flags and only *appends* to them, so any row
# of the evidence table can be replayed by hand from the recorded argv.
SCF_STRATEGIES: tuple[dict[str, object], ...] = (
    {
        "id": "frozen",
        "note": "control: the exact frozen invocation, no extra flags",
        "flags": (),
        "preopt_gfnff": False,
    },
    {
        "id": "etemp_1000",
        "note": "electronic temperature 1000 K (damps SCC oscillation)",
        "flags": ("--etemp", "1000"),
        "preopt_gfnff": False,
    },
    {
        "id": "etemp_5000",
        "note": "electronic temperature 5000 K",
        "flags": ("--etemp", "5000"),
        "preopt_gfnff": False,
    },
    {
        "id": "acc_5",
        "note": "looser SCC accuracy threshold (--acc 5.0)",
        "flags": ("--acc", "5.0"),
        "preopt_gfnff": False,
    },
    {
        "id": "etemp_5000_acc_5",
        "note": "electronic temperature 5000 K plus loose SCC accuracy",
        "flags": ("--etemp", "5000", "--acc", "5.0"),
        "preopt_gfnff": False,
    },
    {
        "id": "alpb_acetonitrile",
        "note": "ALPB continuum solvation, screening the charge separation",
        "flags": ("--alpb", "acetonitrile"),
        "preopt_gfnff": False,
    },
    {
        "id": "gfnff_preopt_then_gfn2",
        "note": "GFN-FF pre-optimisation, then GFN2 from that geometry",
        "flags": (),
        "preopt_gfnff": True,
    },
)

DSMILE = "O=C=[Fe](=C=O)(=C=O)(=C=O)=C=O"
FE_CANDIDATES: tuple[dict[str, str], ...] = (
    {
        "id": "stored",
        "note": "the frozen dataset value, transcribed from InChI=1S/5CO.Fe",
        "smiles": "[C]=O.[C]=O.[C]=O.[C]=O.[C]=O.[Fe]",
    },
    {
        "id": "double_bond_fe",
        "note": "Fe=C double bonds; the only form known to sanitise locally",
        "smiles": DSMILE,
    },
    {
        "id": "dative_single",
        "note": "one dative Fe<-CO ligand",
        "smiles": "[Fe]<-C#O",
    },
    {
        "id": "dative_five",
        "note": "five dative ligands around Fe",
        "smiles": "[Fe](<-C#O)(<-C#O)(<-C#O)(<-C#O)<-C#O",
    },
    {
        "id": "dative_neutral_bracket",
        "note": "five neutral bracketed CO ligands via dative bonds",
        "smiles": "[Fe](<-[C]=O)(<-[C]=O)(<-[C]=O)(<-[C]=O)<-[C]=O",
    },
    {
        "id": "dative_neutral_canonical",
        "note": "RDKit canonical form of the same dative complex",
        "smiles": "O=[C]->[Fe](<-[C]=O)(<-[C]=O)(<-[C]=O)<-[C]=O",
    },
    {
        "id": "single_bond_bracket",
        "note": "five single Fe-C bonds to bracketed CO ligands",
        "smiles": "[Fe]([C]=O)([C]=O)([C]=O)([C]=O)[C]=O",
    },
    {
        "id": "dative_charge_separated_bracket",
        "note": "charge-separated bracketed CO ligands via dative bonds",
        "smiles": "[Fe](<-[C-]=[O+])(<-[C-]=[O+])(<-[C-]=[O+])(<-[C-]=[O+])<-[C-]=[O+]",
    },
    {
        "id": "dative_five_alt",
        "note": "five dative ligands, written from the ligand side",
        "smiles": "O=C->[Fe](<-C=O)(<-C=O)(<-C=O)<-C=O",
    },
    {
        "id": "single_bonds",
        "note": "plain single Fe-C bonds",
        "smiles": "[Fe](C#O)(C#O)(C#O)(C#O)C#O",
    },
)


def _tail(text: str, count: int = TAIL_LINES) -> list[str]:
    """Return the last non-blank lines of an xTB log, verbatim."""

    lines = [line.rstrip() for line in text.splitlines() if line.strip()]
    return lines[-count:]


def resolve_xtb() -> Path:
    """Locate the xTB executable the same way the frozen runner does."""

    candidates: list[Path] = []
    if os.environ.get("XTB_EXE"):
        candidates.append(Path(os.environ["XTB_EXE"]))
    local = os.environ.get("LOCALAPPDATA")
    if local:
        candidates.append(
            Path(local)
            / "electrolyte-ml"
            / "tools"
            / "xtb-6.7.1"
            / "extracted"
            / "xtb-6.7.1"
            / "bin"
            / "xtb.exe"
        )
    found = shutil.which("xtb")
    if found:
        candidates.append(Path(found))
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise FileNotFoundError("xTB executable not found; set XTB_EXE")


def _run(command: list[str], run_dir: Path, timeout: int) -> tuple[int | None, str, str, float]:
    environment = os.environ.copy()
    environment["OMP_NUM_THREADS"] = "1"
    environment["MKL_NUM_THREADS"] = "1"
    start = time.perf_counter()
    try:
        completed = subprocess.run(
            command,
            cwd=run_dir,
            env=environment,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        code: int | None = completed.returncode
        stdout = completed.stdout.decode("utf-8", "replace")
        stderr = completed.stderr.decode("utf-8", "replace")
    except subprocess.TimeoutExpired as exc:
        code = None
        stdout = (exc.stdout or b"").decode("utf-8", "replace")
        stderr = (exc.stderr or b"").decode("utf-8", "replace")
    return code, stdout, stderr, round(time.perf_counter() - start, 2)


def frozen_verdict(*, run_dir: Path, stdout: str, exit_code: int | None) -> dict[str, object]:
    """Report what scripts/run_xtb_physical_features.py would make of this run.

    The frozen runner accepts a run when the exit code is zero, ``xtbopt.xyz``
    exists and either stdout carries the marker or the ``.xtboptok`` sentinel
    is present; it then requires every parsed feature.  This helper applies
    exactly that rule, so ``frozen_runner_accepts`` is the operative verdict.
    """

    marker = NORMAL_TERMINATION in stdout
    written = (run_dir / "xtbopt.xyz").is_file()
    sentinel = (run_dir / OPT_MARKER_FILE).is_file()
    verdict: dict[str, object] = {
        "normal_termination_in_stdout": marker,
        "opt_marker_file": sentinel,
        "optimized_geometry_written": written,
        "frozen_runner_accepts": bool(exit_code == 0 and written and (marker or sentinel)),
        "parsed_ok": False,
        "parse_error": "",
        "features": None,
        "geoopt_converged": GEOOPT_CONVERGED in stdout,
        "geoopt_failed": GEOOPT_FAILED in stdout,
        "gradient_norm_eh_per_alpha": None,
    }
    gradient = GRADIENT_NORM_RE.search(stdout)
    if gradient:
        verdict["gradient_norm_eh_per_alpha"] = float(gradient.group(1))
    if verdict["frozen_runner_accepts"] is not True:
        return verdict
    text = stdout if marker else f"{stdout}\n{NORMAL_TERMINATION}\n"
    try:
        parsed = parse_xtb_output(text)
    except XtbFeatureError as exc:
        verdict["parse_error"] = str(exc)
        verdict["frozen_runner_accepts"] = False
        return verdict
    verdict["parsed_ok"] = True
    verdict["features"] = {
        "total_energy_hartree": parsed.total_energy_hartree,
        "homo_lumo_gap_ev": parsed.homo_lumo_gap_ev,
        "dipole_debye": parsed.dipole_debye,
        "polarizability_au": parsed.polarizability_au,
    }
    return verdict


def run_strategy(
    key: str,
    strategy: dict[str, object],
    *,
    xtb: Path,
    work_dir: Path,
    timeout: int,
) -> dict[str, object]:
    """Run one SCF strategy for one ion pair from a packed start geometry."""

    smiles = str(DEFECT_TARGETS[key]["smiles"])
    run_dir = work_dir / f"{key}__{strategy['id']}"
    run_dir.mkdir(parents=True, exist_ok=True)
    # Stale artefacts from an earlier attempt would silently change the run.
    for stale in ("xtbrestart", "xtbopt.xyz", OPT_MARKER_FILE):
        path = run_dir / stale
        if path.exists():
            path.unlink()
    (run_dir / "input.xyz").write_text(
        embed_fragments_separately(smiles), encoding="utf-8", newline="\n"
    )

    outcome: dict[str, object] = {
        "strategy": strategy["id"],
        "note": strategy["note"],
        "start_geometry": "fragments packed apart by probes/xtb_fragment_geometry_defect.py",
        "stages": [],
    }
    geometry = "input.xyz"
    if strategy["preopt_gfnff"]:
        stage_command = [str(xtb), geometry, "--opt", "--gfnff"]
        code, stdout, stderr, elapsed = _run(stage_command, run_dir, timeout)
        (run_dir / "xtbff.out").write_text(stdout, encoding="utf-8", newline="\n")
        outcome["stages"].append(
            {
                "stage": "gfnff_preopt",
                "argv": stage_command[1:],
                "exit_code": code,
                "elapsed_seconds": elapsed,
                "stderr": stderr.strip(),
                "tail": _tail(stdout),
            }
        )
        if code != 0 or not (run_dir / "xtbopt.xyz").is_file():
            outcome.update(
                {
                    "argv": stage_command[1:],
                    "exit_code": code,
                    "elapsed_seconds": elapsed,
                    "recovered": False,
                    "frozen_runner_accepts": False,
                    "blocked_by": "gfnff_preopt",
                    "tail": _tail(stdout),
                }
            )
            return outcome
        # Keep the FF geometry under its own name and clear the FF sentinel,
        # otherwise the GFN2 stage would inherit a marker it did not earn.
        shutil.copyfile(run_dir / "xtbopt.xyz", run_dir / "ffopt.xyz")
        for stale in ("xtbopt.xyz", OPT_MARKER_FILE):
            path = run_dir / stale
            if path.exists():
                path.unlink()
        geometry = "ffopt.xyz"

    command = [str(xtb), geometry, *FROZEN_FLAGS, *strategy["flags"]]
    code, stdout, stderr, elapsed = _run(command, run_dir, timeout)
    (run_dir / "xtb.out").write_text(stdout, encoding="utf-8", newline="\n")
    verdict = frozen_verdict(run_dir=run_dir, stdout=stdout, exit_code=code)
    outcome["stages"].append(
        {
            "stage": "gfn2",
            "argv": command[1:],
            "exit_code": code,
            "elapsed_seconds": elapsed,
            "stderr": stderr.strip(),
            "tail": _tail(stdout),
        }
    )
    outcome.update(
        {
            "argv": command[1:],
            "exit_code": code,
            "elapsed_seconds": elapsed,
            "stderr": stderr.strip(),
            "tail": _tail(stdout),
            **verdict,
        }
    )
    outcome["recovered"] = bool(verdict["frozen_runner_accepts"])
    return outcome

def run_ion_pairs(
    *, xtb: Path, work_dir: Path, timeout: int, stop_on_success: bool
) -> dict[str, object]:
    """Run every SCF strategy for every ion pair."""

    results: dict[str, object] = {}
    for key in ION_PAIR_KEYS:
        record = DEFECT_TARGETS[key]
        attempts: list[dict[str, object]] = []
        recovered_by: str | None = None
        for strategy in SCF_STRATEGIES:
            attempt = run_strategy(
                key, strategy, xtb=xtb, work_dir=work_dir, timeout=timeout
            )
            attempts.append(attempt)
            if attempt["recovered"]:
                recovered_by = str(strategy["id"])
                if stop_on_success:
                    break
        results[key] = {
            "name": record["name"],
            "smiles": record["smiles"],
            "fragments": record["fragments"],
            "recovered": recovered_by is not None,
            "recovered_by": recovered_by,
            "attempts": attempts,
        }
    return results

def run_control(
    key: str, strategy: dict[str, object], *, xtb: Path, work_dir: Path, timeout: int
) -> dict[str, object]:
    """Re-run a frozen row from its own frozen start geometry under one strategy."""

    frozen_xyz = (
        REPOSITORY_ROOT / "data" / "interim" / "xtb_features" / key / "input.xyz"
    )
    run_dir = work_dir / f"control_{key}__{strategy['id']}"
    run_dir.mkdir(parents=True, exist_ok=True)
    for stale in ("xtbrestart", "xtbopt.xyz", OPT_MARKER_FILE):
        path = run_dir / stale
        if path.exists():
            path.unlink()
    (run_dir / "input.xyz").write_text(
        frozen_xyz.read_text(encoding="utf-8"), encoding="utf-8", newline="\n"
    )
    command = [str(xtb), "input.xyz", *FROZEN_FLAGS, *strategy["flags"]]
    code, stdout, stderr, elapsed = _run(command, run_dir, timeout)
    (run_dir / "xtb.out").write_text(stdout, encoding="utf-8", newline="\n")
    verdict = frozen_verdict(run_dir=run_dir, stdout=stdout, exit_code=code)
    return {
        "strategy": strategy["id"],
        "argv": command[1:],
        "exit_code": code,
        "elapsed_seconds": elapsed,
        "stderr": stderr.strip(),
        "recovered": bool(verdict["frozen_runner_accepts"]),
        **verdict,
    }


def run_protocol_sensitivity(
    *, xtb: Path, work_dir: Path, timeout: int
) -> dict[str, object]:
    """Quantify how much a recovery flag moves the features of frozen rows.

    Each control is re-run from *its own frozen start geometry*, once with the
    frozen flags and once with the ``--etemp 5000`` variant, so the only
    difference between the two runs is the flag.  Any movement is therefore
    attributable to the protocol, not to the geometry.
    """

    by_id = {str(strategy["id"]): strategy for strategy in SCF_STRATEGIES}
    controls: dict[str, object] = {}
    largest = 0.0
    fields: set[str] = set()
    for key in CONTROL_KEYS:
        frozen_xyz = (
            REPOSITORY_ROOT / "data" / "interim" / "xtb_features" / key / "input.xyz"
        )
        if not frozen_xyz.is_file():
            continue
        runs = {
            strategy_id: run_control(
                key, by_id[strategy_id], xtb=xtb, work_dir=work_dir, timeout=timeout
            )
            for strategy_id in CONTROL_STRATEGY_IDS
        }
        base = runs["frozen"].get("features")
        variant = runs["etemp_5000"].get("features")
        deltas = None
        if isinstance(base, dict) and isinstance(variant, dict):
            deltas = {}
            for field, value in base.items():
                change = abs(variant[field] - value)
                relative = change / abs(value) if value else None
                fields.add(field)
                if relative is not None and relative > largest:
                    largest = relative
                deltas[field] = {
                    "frozen_value": value,
                    "etemp_5000_value": variant[field],
                    "absolute_change": change,
                    "relative_change": relative,
                }
        controls[key] = {
            "source_input_xyz": "data/interim/xtb_features/"
            + key
            + "/input.xyz",
            "runs": runs,
            "feature_deltas": deltas,
        }
    return {
        "question": (
            "Do the recovery flags change features that the frozen protocol "
            "already produced, i.e. are recovered rows commensurate with the "
            "frozen feature table?"
        ),
        "controls": controls,
        "fields_compared": sorted(fields),
        "max_relative_change": round(largest, 6),
    }

def screen_fe_candidate(candidate: dict[str, str]) -> dict[str, object]:
    """Report whether one Fe(CO)5 candidate sanitises, embeds and bonds Fe-C."""

    smiles = candidate["smiles"]
    molecule = Chem.MolFromSmiles(smiles)
    record: dict[str, object] = {
        "id": candidate["id"],
        "note": candidate["note"],
        "smiles": smiles,
        "sanitises": molecule is not None,
    }
    if molecule is None:
        record["embed_return"] = None
        record["has_fe_c_bond"] = False
        record["fragments"] = None
        record["fe_c_bond_lengths_angstrom"] = []
        return record

    record["fragments"] = len(Chem.GetMolFrags(molecule))
    record["has_fe_c_bond"] = any(
        sorted((bond.GetBeginAtom().GetAtomicNum(), bond.GetEndAtom().GetAtomicNum()))
        == [6, 26]
        for bond in molecule.GetBonds()
    )
    working = Chem.AddHs(molecule)
    parameters = AllChem.ETKDGv3()
    parameters.randomSeed = 42
    embed = AllChem.EmbedMolecule(working, parameters)
    if embed < 0:
        parameters.useRandomCoords = True
        parameters.maxIterations = 200
        embed = AllChem.EmbedMolecule(working, parameters)
    record["embed_return"] = int(embed)
    lengths: list[float] = []
    if embed >= 0:
        conformer = working.GetConformer()
        for bond in working.GetBonds():
            numbers = sorted(
                (bond.GetBeginAtom().GetAtomicNum(), bond.GetEndAtom().GetAtomicNum())
            )
            if numbers == [6, 26]:
                first = conformer.GetAtomPosition(bond.GetBeginAtomIdx())
                second = conformer.GetAtomPosition(bond.GetEndAtomIdx())
                lengths.append(round(float(first.Distance(second)), 4))
    record["fe_c_bond_lengths_angstrom"] = lengths
    return record


def screen_fe_structures() -> dict[str, object]:
    candidates = [screen_fe_candidate(candidate) for candidate in FE_CANDIDATES]
    viable = [
        candidate
        for candidate in candidates
        if candidate["sanitises"]
        and candidate["has_fe_c_bond"]
        and isinstance(candidate["embed_return"], int)
        and candidate["embed_return"] >= 0
    ]
    return {
        "target": FE_KEY,
        "stored_smiles": DEFECT_TARGETS[FE_KEY]["smiles"],
        "candidates": candidates,
        "viable_candidate_ids": [candidate["id"] for candidate in viable],
        "viable_found": bool(viable),
    }


def build_payload(
    *,
    ion_pairs: dict[str, object] | None,
    fe_structures: dict[str, object] | None,
    protocol_sensitivity: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "probe": "xtb_recovery_probe",
        "question": (
            "Is there a reproducible protocol under which the four feature-failed "
            "model_ready=true rows reach 'normal termination of xtb'?"
        ),
        "scf_strategies": [
            {
                "id": strategy["id"],
                "note": strategy["note"],
                "flags": list(strategy["flags"]),
                "preopt_gfnff": strategy["preopt_gfnff"],
            }
            for strategy in SCF_STRATEGIES
        ],
        "frozen_flags": list(FROZEN_FLAGS),
        "ion_pairs": ion_pairs,
        "fe_structures": fe_structures,
        "protocol_sensitivity": protocol_sensitivity,
        "scope_note": (
            "Feasibility probe only. No dataset cell, frozen feature table, digest, "
            "exclusion list or export bundle is modified, and the four rows remain "
            "outside the fit set."
        ),
    }


def _read_committed() -> dict[str, object]:
    if not EVIDENCE_PATH.is_file():
        return {}
    return json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))


def check_payload(payload: dict[str, object]) -> list[str]:
    """Return every reason the committed evidence fails its own invariants."""

    problems: list[str] = []
    ion_pairs = payload.get("ion_pairs")
    if not isinstance(ion_pairs, dict):
        problems.append("ion_pairs section is missing")
    else:
        if set(ion_pairs) != set(ION_PAIR_KEYS):
            problems.append(
                f"ion_pairs covers {sorted(ion_pairs)} instead of {sorted(ION_PAIR_KEYS)}"
            )
        declared = {str(strategy["id"]) for strategy in SCF_STRATEGIES}
        for key, record in ion_pairs.items():
            if not isinstance(record, dict):
                problems.append(f"{key}: record is not an object")
                continue
            attempts = record.get("attempts")
            if not isinstance(attempts, list) or not attempts:
                problems.append(f"{key}: no attempts recorded")
                continue
            seen = {str(attempt["strategy"]) for attempt in attempts}
            if not seen <= declared:
                problems.append(f"{key}: unknown strategy in {sorted(seen - declared)}")
            winners = [
                str(attempt["strategy"])
                for attempt in attempts
                if attempt.get("recovered") is True
            ]
            if bool(record.get("recovered")) != bool(winners):
                problems.append(f"{key}: recovered flag disagrees with its attempts")
            if record.get("recovered_by") not in (None, *winners):
                problems.append(f"{key}: recovered_by is not a winning attempt")
            for attempt in attempts:
                base = (
                    attempt.get("exit_code") == 0
                    and attempt.get("optimized_geometry_written") is True
                    and (
                        attempt.get("normal_termination_in_stdout") is True
                        or attempt.get("opt_marker_file") is True
                    )
                )
                expected = bool(base and attempt.get("parsed_ok") is True)
                label = f"{key}/{attempt.get('strategy')}"
                if attempt.get("frozen_runner_accepts") is not expected:
                    problems.append(
                        f"{label}: frozen_runner_accepts disagrees with the frozen rule"
                    )
                if bool(attempt.get("recovered")) != expected:
                    problems.append(f"{label}: recovered flag disagrees with the frozen rule")
                if expected and attempt.get("features") is None:
                    problems.append(f"{label}: accepted run carries no parsed features")
    fe_structures = payload.get("fe_structures")
    if not isinstance(fe_structures, dict):
        problems.append("fe_structures section is missing")
    else:
        if fe_structures.get("target") != FE_KEY:
            problems.append("fe_structures.target is not the iron pentacarbonyl key")
        candidates = fe_structures.get("candidates")
        if not isinstance(candidates, list) or not candidates:
            problems.append("fe_structures has no candidates")
        else:
            viable = [
                candidate["id"]
                for candidate in candidates
                if candidate.get("sanitises")
                and candidate.get("has_fe_c_bond")
                and isinstance(candidate.get("embed_return"), int)
                and candidate["embed_return"] >= 0
            ]
            if list(fe_structures.get("viable_candidate_ids", [])) != viable:
                problems.append("fe_structures.viable_candidate_ids disagrees with the rows")
            if bool(fe_structures.get("viable_found")) != bool(viable):
                problems.append("fe_structures.viable_found disagrees with the rows")
    sensitivity = payload.get("protocol_sensitivity")
    if isinstance(sensitivity, dict):
        controls = sensitivity.get("controls")
        if not isinstance(controls, dict) or not controls:
            problems.append("protocol_sensitivity has no controls")
        else:
            for key, entry in controls.items():
                runs = entry.get("runs") if isinstance(entry, dict) else None
                if not isinstance(runs, dict) or set(runs) != set(CONTROL_STRATEGY_IDS):
                    problems.append(f"control {key}: runs do not cover both strategies")
                    continue
                if runs["frozen"].get("frozen_runner_accepts") is not True:
                    problems.append(
                        f"control {key}: the frozen run itself was not accepted, so the "
                        "comparison is invalid"
                    )
                if not isinstance(entry.get("feature_deltas"), dict):
                    problems.append(f"control {key}: no feature deltas recorded")
    if not payload.get("scope_note"):
        problems.append("scope_note is missing")
    return problems


def _print(payload: dict[str, object]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ion-pairs", action="store_true", help="run the SCF matrix")
    parser.add_argument(
        "--fe-structures", action="store_true", help="screen Fe(CO)5 structure candidates"
    )
    parser.add_argument(
        "--controls",
        action="store_true",
        help="measure how much the recovery flags move already-frozen features",
    )
    parser.add_argument("--write", action="store_true", help="write the evidence JSON")
    parser.add_argument("--check", action="store_true", help="validate the evidence JSON")
    parser.add_argument("--report", action="store_true", help="print the payload")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--work-dir", type=Path, default=DEFAULT_WORK_DIR)
    parser.add_argument("--xtb", type=Path, default=None)
    parser.add_argument(
        "--keep-going",
        action="store_true",
        help="keep running later strategies even after one recovers a molecule",
    )
    args = parser.parse_args(argv)

    if args.check:
        committed = _read_committed()
        if not committed:
            print("EVIDENCE MISSING", file=sys.stderr)
            return 1
        problems = check_payload(committed)
        for problem in problems:
            print(f"EVIDENCE MISMATCH: {problem}", file=sys.stderr)
        if problems:
            return 1
        print("evidence invariants hold")
        return 0

    committed = _read_committed()
    ion_pairs: dict[str, object] | None = committed.get("ion_pairs")  # type: ignore[assignment]
    fe_structures: dict[str, object] | None = committed.get("fe_structures")  # type: ignore[assignment]
    sensitivity: dict[str, object] | None = committed.get(  # type: ignore[assignment]
        "protocol_sensitivity"
    )

    if args.ion_pairs:
        xtb = args.xtb or resolve_xtb()
        print(f"running the SCF matrix with {xtb}", file=sys.stderr)
        ion_pairs = run_ion_pairs(
            xtb=xtb,
            work_dir=args.work_dir,
            timeout=args.timeout,
            stop_on_success=not args.keep_going,
        )
    if args.fe_structures:
        fe_structures = screen_fe_structures()
    if args.controls:
        xtb = args.xtb or resolve_xtb()
        sensitivity = run_protocol_sensitivity(
            xtb=xtb, work_dir=args.work_dir, timeout=args.timeout
        )

    payload = build_payload(
        ion_pairs=ion_pairs,
        fe_structures=fe_structures,
        protocol_sensitivity=sensitivity,
    )

    if args.write:
        EVIDENCE_PATH.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        print(f"wrote {EVIDENCE_PATH}")
        return 0

    _print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
