"""The single deterministic subprocess launcher for GFN2-xTB.

Why this module exists
----------------------
xTB 6.7.1 is built with OpenMP and parallelises the SCF and the analytic
gradient.  Floating-point addition is not associative, so the number of
reduction workers changes the converged gradient in its last digits, and two
runs that use the same number of workers above one can still reduce in a
different order.  ``--opt`` stops on a gradient-norm criterion, so that
perturbation moves the reported minimum: ``xtbopt.xyz`` comes out slightly
different, and every geometry-derived column (``molecular_volume_A3``,
``molar_volume_m3_mol``, ``mu_sq_over_Vm``, ``alpha_over_Vm``) moves with it.

Pinning the child to a single thread removes the reduction reordering, which
makes the SCF, the gradient and therefore the optimised geometry
bit-reproducible run to run.  The pin belongs in exactly one place -- here --
so the persisted feature paths cannot drift apart from one another.

The thread pin is necessary but not sufficient: xTB also reuses a leftover
``xtbrestart`` from an earlier run in the same working directory as an SCF
restart, which perturbs the converged gradient just as badly.  ``cwd`` must
therefore start free of xTB scratch files; the frozen runner does that with
``_clear_run_artifacts``.

``run_xtb_subprocess`` accepts ``environment`` as an explicit diagnostic escape
hatch because ``probes/xtb_thread_determinism_probe.py`` has to reproduce the
defective Week 11 invocation in order to measure it.  Every call site that
writes a feature table must leave it as ``None``; see
``tests/test_xtb_thread_determinism.py`` for the guard on that rule.
"""

from __future__ import annotations

import os
import re
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path

DETERMINISTIC_THREADS = 1
THREAD_ENVIRONMENT_VARIABLES = (
    "OMP_NUM_THREADS",
    "MKL_NUM_THREADS",
    "OMP_DYNAMIC",
    "MKL_DYNAMIC",
)


def xtb_thread_environment(
    base: Mapping[str, str] | None = None,
    *,
    threads: int = DETERMINISTIC_THREADS,
) -> dict[str, str]:
    """Environment for an xTB subprocess with the thread count pinned.

    ``base`` defaults to ``os.environ``; the four thread variables are then
    overwritten, so a caller's ``OMP_NUM_THREADS`` cannot leak into the
    calculation.  ``threads`` is exposed only so the determinism probe can
    build the defective comparison arm.
    """

    if threads < 1:
        raise ValueError("threads must be a positive integer")
    environment = dict(os.environ if base is None else base)
    for variable in THREAD_ENVIRONMENT_VARIABLES:
        environment.pop(variable, None)
    environment["OMP_NUM_THREADS"] = str(threads)
    environment["MKL_NUM_THREADS"] = str(threads)
    environment["OMP_DYNAMIC"] = "FALSE"
    environment["MKL_DYNAMIC"] = "FALSE"
    return environment


def xtb_optimisation_arguments(input_name: str, *, formal_charge: int) -> list[str]:
    """The frozen GFN2 geometry-optimisation arguments, without the executable."""

    return [
        input_name,
        "--opt",
        "--gfn",
        "2",
        "--chrg",
        str(formal_charge),
        "--uhf",
        "0",
    ]


def run_xtb_subprocess(
    executable: Path | str,
    arguments: Sequence[str],
    *,
    cwd: Path | str,
    timeout_seconds: int,
    environment: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess[bytes]:
    """Run xTB with captured output under the pinned thread environment."""

    resolved = xtb_thread_environment() if environment is None else dict(environment)
    return subprocess.run(
        [str(executable), *arguments],
        cwd=cwd,
        env=resolved,
        capture_output=True,
        timeout=timeout_seconds,
        check=False,
    )


def reported_omp_threads(text: str) -> int | None:
    """The ``omp threads`` count xTB echoes in its banner, if it printed one."""

    match = re.search(r"omp threads\s*:\s*(\d+)", text)
    return int(match.group(1)) if match else None
