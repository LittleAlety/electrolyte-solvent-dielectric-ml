from __future__ import annotations

import subprocess
from pathlib import Path

from scripts.run_xtb_physical_features import run_xtb

SAMPLE_XTB_OUTPUT = """
         ::::::::::::::::::::::::::::::::::::::::::::::::::::::
         :: total energy              -8.226118333165 Eh    ::
         ::::::::::::::::::::::::::::::::::::::::::::::::::::::
                  HL-Gap            0.4814543 Eh           13.1010 eV
   Mol. alpha(0) /au     :         21.569029
molecular dipole:
                 x           y           z       tot (Debye)
 q only:       -0.089       0.430       0.280
   full:       -0.074       0.627       0.411       1.915
"""


def test_run_xtb_saves_stdout_and_reuses_valid_cache(
    tmp_path: Path,
    monkeypatch,
) -> None:
    calls = 0

    def fake_run(*args, **kwargs) -> subprocess.CompletedProcess[bytes]:
        nonlocal calls
        calls += 1
        assert kwargs["capture_output"] is True
        run_dir = Path(kwargs["cwd"])
        (run_dir / "xtbopt.xyz").write_text(
            (run_dir / "input.xyz").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        (run_dir / ".xtboptok").touch()
        return subprocess.CompletedProcess(
            args=args,
            returncode=0,
            stdout=SAMPLE_XTB_OUTPUT.encode(),
            stderr=b"",
        )

    monkeypatch.setattr(
        "scripts.run_xtb_physical_features.subprocess.run",
        fake_run,
    )
    (tmp_path / "xtb.exe").write_bytes(b"fake executable")
    kwargs = {
        "smiles": "CO",
        "label": "methanol",
        "xtb_executable": tmp_path / "xtb.exe",
        "work_dir": tmp_path,
        "seed": 42,
        "timeout_seconds": 60,
        "threads": 1,
    }

    first = run_xtb(**kwargs)
    second = run_xtb(**kwargs)

    assert first["status"] == "ok"
    assert second["status"] == "cached"
    assert calls == 1
    run_dirs = [path for path in tmp_path.iterdir() if path.is_dir()]
    assert len(run_dirs) == 1
    assert (run_dirs[0] / "xtb.out").read_text() == SAMPLE_XTB_OUTPUT

    different_molecule = run_xtb(**{**kwargs, "smiles": "CCO", "seed": 43})

    assert different_molecule["status"] == "ok"
    assert calls == 2
    run_dirs = [path for path in tmp_path.iterdir() if path.is_dir()]
    assert len(run_dirs) == 2
