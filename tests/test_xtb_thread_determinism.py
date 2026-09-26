"""Guards for the xTB thread-determinism fix.

The bug: ``xtbopt.xyz`` -- and therefore every geometry-derived column of the
dielectric feature table -- was not reproducible, because xTB's OpenMP reduction
order depends on the thread count (and, above one thread, on the run).  The fix
routes every xTB subprocess through ``electrolyte_ml.xtb_runner``, which pins the
child to one thread.

Most of these tests never launch xTB; they assert the properties that make the
pin effective.  The last test really runs xTB when the git-ignored local cache is
present, so a laptop run also checks the end-to-end reproduction gate.
"""

from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

import pytest

from electrolyte_ml.xtb_features import molecular_volume_A3
from electrolyte_ml.xtb_runner import (
    DETERMINISTIC_THREADS,
    reported_omp_threads,
    run_xtb_subprocess,
    xtb_optimisation_arguments,
    xtb_thread_environment,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CACHE_ROOT = REPOSITORY_ROOT / "data" / "interim" / "xtb_features_v11plus"
TARGET_CACHE = CACHE_ROOT / "UJPMYEOUBPIPHQ-UHFFFAOYSA-N__c8f8438509d0"

SAMPLE_XTB_OUTPUT = """
          omp threads                :                     1
         ::::::::::::::::::::::::::::::::::::::::::::::::::::::
         :: total energy              -8.226118333165 Eh    ::
         ::::::::::::::::::::::::::::::::::::::::::::::::::::::
                  HL-Gap            0.4814543 Eh           13.1010 eV
   Mol. alpha(0) /au     :         21.569029
molecular dipole:
                 x           y           z       tot (Debye)
 q only:       -0.089       0.430       0.280
   full:       -0.074       0.627       0.411       1.915
normal termination of xtb
"""


# --- the pin itself ---------------------------------------------------------


def test_thread_environment_overrides_a_leaked_parent_setting() -> None:
    """A caller's ``OMP_NUM_THREADS`` must not survive into the child."""

    leaked = {"OMP_NUM_THREADS": "8", "MKL_NUM_THREADS": "8", "PATH": "/usr/bin"}
    environment = xtb_thread_environment(leaked)

    assert environment["OMP_NUM_THREADS"] == str(DETERMINISTIC_THREADS)
    assert environment["MKL_NUM_THREADS"] == str(DETERMINISTIC_THREADS)
    assert environment["OMP_DYNAMIC"] == "FALSE"
    assert environment["MKL_DYNAMIC"] == "FALSE"
    assert environment["PATH"] == "/usr/bin"
    assert leaked["OMP_NUM_THREADS"] == "8", "the caller's mapping is not mutated"


def test_thread_environment_rejects_a_non_positive_thread_count() -> None:
    with pytest.raises(ValueError, match="positive integer"):
        xtb_thread_environment({}, threads=0)


def test_run_xtb_subprocess_passes_the_pinned_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("OMP_NUM_THREADS", "8")
    seen: dict[str, object] = {}

    def fake_run(*args, **kwargs) -> subprocess.CompletedProcess[bytes]:
        seen["args"] = args
        seen["kwargs"] = kwargs
        return subprocess.CompletedProcess(args=args, returncode=0, stdout=b"", stderr=b"")

    monkeypatch.setattr("electrolyte_ml.xtb_runner.subprocess.run", fake_run)
    run_xtb_subprocess(
        tmp_path / "xtb.exe",
        ["input.xyz", "--opt"],
        cwd=tmp_path,
        timeout_seconds=17,
    )

    environment = seen["kwargs"]["env"]  # type: ignore[index]
    assert environment["OMP_NUM_THREADS"] == str(DETERMINISTIC_THREADS)
    assert environment["MKL_NUM_THREADS"] == str(DETERMINISTIC_THREADS)
    assert seen["args"] == ([str(tmp_path / "xtb.exe"), "input.xyz", "--opt"],)
    assert seen["kwargs"]["cwd"] == tmp_path  # type: ignore[index]
    assert seen["kwargs"]["timeout"] == 17  # type: ignore[index]
    assert seen["kwargs"]["capture_output"] is True  # type: ignore[index]
    assert seen["kwargs"]["check"] is False  # type: ignore[index]


def test_run_xtb_subprocess_honours_an_explicit_diagnostic_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The probe needs the defective invocation; the escape hatch must work."""

    seen: dict[str, object] = {}

    def fake_run(*args, **kwargs) -> subprocess.CompletedProcess[bytes]:
        seen.update(kwargs)
        return subprocess.CompletedProcess(args=args, returncode=0, stdout=b"", stderr=b"")

    monkeypatch.setattr("electrolyte_ml.xtb_runner.subprocess.run", fake_run)
    run_xtb_subprocess(
        tmp_path / "xtb.exe",
        ["input.xyz"],
        cwd=tmp_path,
        timeout_seconds=1,
        environment={"OMP_NUM_THREADS": "8"},
    )

    assert seen["env"] == {"OMP_NUM_THREADS": "8"}


def test_optimisation_arguments_match_the_frozen_command_line() -> None:
    assert xtb_optimisation_arguments("input.xyz", formal_charge=-1) == [
        "input.xyz",
        "--opt",
        "--gfn",
        "2",
        "--chrg",
        "-1",
        "--uhf",
        "0",
    ]


def test_reported_omp_threads_reads_the_banner() -> None:
    assert reported_omp_threads(SAMPLE_XTB_OUTPUT) == 1
    assert reported_omp_threads("          omp threads                :   16") == 16
    assert reported_omp_threads("no banner here") is None


# --- the frozen feature runner goes through the pin -------------------------


def test_feature_runner_pins_the_child_despite_a_leaked_parent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """End-to-end: ``run_xtb`` -> launcher -> a one-thread child environment."""

    from scripts.run_xtb_physical_features import run_xtb

    monkeypatch.setenv("OMP_NUM_THREADS", "8")
    monkeypatch.setenv("MKL_NUM_THREADS", "8")
    environments: list[dict[str, str]] = []
    arguments: list[list[str]] = []

    def fake_run(*args, **kwargs) -> subprocess.CompletedProcess[bytes]:
        environments.append(kwargs["env"])
        arguments.append(list(args[0]))
        run_dir = Path(kwargs["cwd"])
        (run_dir / "xtbopt.xyz").write_text(
            (run_dir / "input.xyz").read_text(encoding="utf-8"), encoding="utf-8"
        )
        (run_dir / ".xtboptok").touch()
        return subprocess.CompletedProcess(
            args=args, returncode=0, stdout=SAMPLE_XTB_OUTPUT.encode(), stderr=b""
        )

    monkeypatch.setattr("electrolyte_ml.xtb_runner.subprocess.run", fake_run)
    (tmp_path / "xtb.exe").write_bytes(b"fake executable")

    result = run_xtb(
        smiles="CO",
        label="methanol",
        xtb_executable=tmp_path / "xtb.exe",
        work_dir=tmp_path,
        seed=42,
        timeout_seconds=60,
    )

    assert result["status"] == "ok"
    assert len(environments) == 1
    assert environments[0]["OMP_NUM_THREADS"] == str(DETERMINISTIC_THREADS)
    assert environments[0]["MKL_NUM_THREADS"] == str(DETERMINISTIC_THREADS)
    assert arguments[0][1:] == xtb_optimisation_arguments("input.xyz", formal_charge=0)


def test_feature_runner_clears_the_run_directory_before_launching(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A leftover ``xtbrestart`` perturbs the gradient even at one thread."""

    from scripts.run_xtb_physical_features import _cache_key, run_xtb

    def fake_run(*args, **kwargs) -> subprocess.CompletedProcess[bytes]:
        run_dir = Path(kwargs["cwd"])
        (run_dir / "xtbopt.xyz").write_text(
            (run_dir / "input.xyz").read_text(encoding="utf-8"), encoding="utf-8"
        )
        (run_dir / ".xtboptok").touch()
        return subprocess.CompletedProcess(
            args=args, returncode=0, stdout=SAMPLE_XTB_OUTPUT.encode(), stderr=b""
        )

    monkeypatch.setattr("electrolyte_ml.xtb_runner.subprocess.run", fake_run)
    (tmp_path / "xtb.exe").write_bytes(b"fake executable")

    run_dir = tmp_path / f"methanol__{_cache_key('CO', 0, 42)[:12]}"
    run_dir.mkdir(parents=True)
    (run_dir / "xtbrestart").write_text("stale", encoding="utf-8")

    run_xtb(
        smiles="CO",
        label="methanol",
        xtb_executable=tmp_path / "xtb.exe",
        work_dir=tmp_path,
        seed=42,
        timeout_seconds=60,
    )

    assert not (run_dir / "xtbrestart").is_file()
    assert (run_dir / "xtbopt.xyz").is_file()


def test_feature_runner_cli_no_longer_exposes_a_thread_knob() -> None:
    """The knob is what let the thread count into a persisted table."""

    from scripts.run_xtb_physical_features import _parse_args

    original = sys.argv
    sys.argv = ["run_xtb_physical_features.py", "--threads", "8"]
    try:
        with pytest.raises(SystemExit):
            _parse_args()
    finally:
        sys.argv = original


def test_migration_probe_reports_the_pinned_thread_count(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from probes.xtb_protocol_migration_probe import describe_run_environment

    executable = tmp_path / "xtb.exe"
    executable.write_bytes(b"fake executable")

    def fake_run(*args, **kwargs) -> subprocess.CompletedProcess[bytes]:
        return subprocess.CompletedProcess(
            args=args, returncode=0, stdout=b"* xtb version 6.7.1pre\n", stderr=b""
        )

    monkeypatch.setattr("electrolyte_ml.xtb_runner.subprocess.run", fake_run)
    environment = describe_run_environment(executable)

    assert environment["threads"] == DETERMINISTIC_THREADS
    assert isinstance(environment["threads"], int)


@pytest.mark.parametrize(
    "relative_path",
    (
        "scripts/run_xtb_physical_features.py",
        "probes/xtb_recovery_probe.py",
        "probes/xtb_protocol_migration_probe.py",
    ),
)
def test_only_the_launcher_runs_a_subprocess(relative_path: str) -> None:
    """One launcher, so the pin cannot be forgotten at a new call site."""

    source = (REPOSITORY_ROOT / relative_path).read_text(encoding="utf-8")
    assert "subprocess.run(" not in source
    assert "run_xtb_subprocess(" in source


def test_probe_defect_arm_reproduces_the_week11_invocation() -> None:
    from probes.xtb_thread_determinism_probe import week11_environment

    environment = week11_environment(8)

    assert environment["OMP_NUM_THREADS"] == "8"
    assert environment["MKL_NUM_THREADS"] == "8"
    assert "OMP_DYNAMIC" not in environment
    assert environment["OMP_NUM_THREADS"] != str(DETERMINISTIC_THREADS)


# --- with a local xTB, the real reproduction gate ---------------------------


@pytest.mark.skipif(
    not (TARGET_CACHE / "input.xyz").is_file(),
    reason="git-ignored xTB cache is absent (CI)",
)
def test_pinned_xtb_is_bit_reproducible_across_thread_settings(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Same input, parent asking for 8 threads and for 1: identical geometry.

    Reproduces the acceptance gate (``< 0.1 %``) on one molecule without the
    probe: the volume column must be bit-identical, not merely close.
    """

    from scripts.run_xtb_physical_features import _clear_run_artifacts, _resolve_xtb

    xtb = _resolve_xtb(None)
    start_geometry = (TARGET_CACHE / "input.xyz").read_text(encoding="utf-8")
    arguments = xtb_optimisation_arguments("input.xyz", formal_charge=0)

    observed: dict[str, tuple[str, float]] = {}
    for requested in ("8", "1"):
        cell = tmp_path / f"threads_{requested}"
        cell.mkdir(parents=True, exist_ok=True)
        _clear_run_artifacts(cell)
        (cell / "input.xyz").write_text(
            start_geometry, encoding="utf-8", newline="\n"
        )
        monkeypatch.setenv("OMP_NUM_THREADS", requested)
        monkeypatch.setenv("MKL_NUM_THREADS", requested)
        completed = run_xtb_subprocess(
            xtb, arguments, cwd=cell, timeout_seconds=600
        )
        assert completed.returncode == 0
        output = completed.stdout.decode("utf-8", errors="replace")
        assert reported_omp_threads(output) == DETERMINISTIC_THREADS
        optimized = (cell / "xtbopt.xyz").read_text(encoding="utf-8")
        observed[requested] = (
            hashlib.sha256(optimized.encode("utf-8")).hexdigest(),
            molecular_volume_A3(optimized),
        )

    first, second = observed["8"], observed["1"]
    assert first[0] == second[0], "xtbopt.xyz differs between thread settings"
    relative = abs(first[1] - second[1]) / abs(first[1])
    assert relative < 1e-3
    assert relative == 0.0
