from __future__ import annotations

import subprocess
import sys
from pathlib import Path

VALID_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<DataReport xmlns="http://www.iupac.org/namespaces/ThermoML">
  <Version>
    <nVersionMajor>2</nVersionMajor>
    <nVersionMinor>0</nVersionMinor>
  </Version>
  <Citation>
    <sTitle>Empty but valid fixture</sTitle>
    <sDOI>10.0000/empty</sDOI>
  </Citation>
</DataReport>
"""


def test_parse_errors_do_not_overwrite_existing_output(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    (raw_dir / "valid.xml").write_text(VALID_XML, encoding="utf-8")
    (raw_dir / "broken.xml").write_text("<DataReport>", encoding="utf-8")

    output = tmp_path / "processed" / "normalized.csv"
    output.parent.mkdir()
    output.write_text("last-known-good\n", encoding="utf-8")
    script = Path(__file__).resolve().parents[1] / "scripts" / "normalize_thermoml.py"

    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--raw-dir",
            str(raw_dir),
            "--csv",
            str(output),
            "--provenance",
            str(output.with_suffix(".provenance.json")),
        ],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert output.read_text(encoding="utf-8") == "last-known-good\n"
