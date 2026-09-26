"""Guards for the W17-RX Reaxys four-channel crosscheck.

Offline only: every assertion reads a checked-in artifact or a shipped repository file.
Nothing here touches the network or Reaxys.
"""

from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from probes.reaxys_core_four_crosscheck import (
    ACCESS,
    OBSERVATIONS,
    RESOLUTION,
    build_summary,
    queue_key_audit,
)

CSV_PATH = REPOSITORY_ROOT / "probes" / "reaxys_core_four_crosscheck.csv"
SUMMARY_PATH = REPOSITORY_ROOT / "probes" / "reaxys_core_four_crosscheck_summary.json"
REPORT_PATH = REPOSITORY_ROOT / "reports" / "reaxys_core_four_crosscheck.md"
PROBE_PATH = REPOSITORY_ROOT / "probes" / "reaxys_core_four_crosscheck.py"

FROZEN_CSV_ROWS = 80


def _summary() -> dict:
    return json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))


def _csv_rows() -> list[dict]:
    with CSV_PATH.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _report() -> str:
    return REPORT_PATH.read_text(encoding="utf-8")


# --------------------------------------------------------------------------------------
# Compliance: restricted Reaxys content must not leak into data/ or into any pool.
# --------------------------------------------------------------------------------------


def test_artifacts_live_outside_data() -> None:
    data_root = (REPOSITORY_ROOT / "data").resolve()
    for path in (CSV_PATH, SUMMARY_PATH, REPORT_PATH, PROBE_PATH):
        assert path.exists(), f"missing artifact: {path}"
        assert data_root not in path.resolve().parents


def test_every_observation_row_is_restricted_crosscheck_only() -> None:
    rows = _csv_rows()
    assert len(rows) == FROZEN_CSV_ROWS
    assert all(row["access"] == ACCESS for row in rows)
    assert all(row["reaxys_crosscheck_only"] == "TRUE" for row in rows)
    assert all(row["access"] == "restricted_crosscheck_only" for row in OBSERVATIONS)


def test_no_reaxys_value_is_written_under_data() -> None:
    summary = _summary()
    compliance = summary["compliance"]
    assert compliance["values_written_under_data"] is False
    assert compliance["values_entered_any_pool"] is False
    assert compliance["values_entered_any_split"] is False
    assert compliance["redistributable"] is False
    assert compliance["averaging_performed"] is False
    assert compliance["batch_crawling"] is False
    assert all(not entry.startswith("data/") for entry in compliance["files_written"])


def test_the_probe_writes_only_its_own_artifacts() -> None:
    text = PROBE_PATH.read_text(encoding="utf-8")
    assert 'REPOSITORY_ROOT / "data"' not in text.split("def write_csv")[1]
    assert "newline=\"\\n\"" in text


# --------------------------------------------------------------------------------------
# Verdicts: the answer the arm exists to give.
# --------------------------------------------------------------------------------------


def test_channel_verdicts() -> None:
    verdicts = {item["channel"]: item for item in _summary()["channel_verdicts"]}
    assert verdicts["dielectric_epsilon"]["verdict"] == "usable_numeric"
    assert verdicts["viscosity_eta"]["verdict"] == "usable_numeric"
    assert verdicts["homo_lumo"]["verdict"] == "reference_only"
    assert verdicts["redox_potential"]["verdict"] == "reference_only"
    assert verdicts["homo_lumo"]["numeric_rows"] == 0
    assert verdicts["redox_potential"]["numeric_rows"] == 0
    assert verdicts["homo_lumo"]["numeric_share"] == 0.0


def test_no_homo_lumo_or_redox_row_carries_a_number() -> None:
    for row in OBSERVATIONS:
        if row["channel"] in ("homo_lumo", "redox"):
            assert row["value_raw"] == "", row
            assert row["row_kind"] == "reference_only", row


def test_the_ionization_potential_finding_is_pinned() -> None:
    dmc_ip = [
        row for row in OBSERVATIONS
        if row["substance"] == "dimethyl carbonate" and row["reaxys_category"] == "Ionization Potential"
    ]
    assert len(dmc_ip) == 2
    assert all(row["value_raw"] == "" for row in dmc_ip)
    assert any("Reference column and NO value column" in row["note"] for row in dmc_ip)
    assert all("reference-only" in row["note"] or "Reference column" in row["note"] for row in dmc_ip)


# --------------------------------------------------------------------------------------
# Crosschecks against the shipped repository files.
# --------------------------------------------------------------------------------------


def test_every_crosscheck_agrees() -> None:
    checks = _summary()["crosschecks"]
    assert len(checks) == 7
    failed = [check["name"] for check in checks if not check["agree"]]
    assert failed == []


def test_gvl_main_leg_matches_the_single_reaxys_row() -> None:
    checks = {check["name"]: check for check in _summary()["crosschecks"]}
    assert checks["gvl_dielectric_value"]["local_value"] == "36.9"
    assert checks["gvl_dielectric_value"]["reaxys_value"] == "36.9"
    assert checks["gvl_dielectric_location"]["reaxys_value"] == "supporting information"
    assert checks["gvl_dual_row_not_averaged"]["local_value"] == "36.1; 36.9"
    assert checks["gvl_dual_row_not_averaged"]["reaxys_value"] == "36.9 only"


def test_ec_anchors_match() -> None:
    checks = {check["name"]: check for check in _summary()["crosschecks"]}
    assert checks["ec_static_dielectric_value_and_temperature"]["local_value"] == "90.5 at 313.15 K"
    assert checks["ec_static_dielectric_value_and_temperature"]["reaxys_value"] == "90.5 at 313.15 K"
    assert checks["ec_melting_point"]["local_value"] == 36.4
    assert checks["ec_melting_point"]["reaxys_value"] == "36.4"


# --------------------------------------------------------------------------------------
# Lessons.
# --------------------------------------------------------------------------------------


def test_lesson_a_the_gvl_miskey_is_not_reaxys() -> None:
    lessons = {item["lesson"]: item for item in _summary()["lessons"]}
    lesson = lessons["A_gvl_inchikey"]
    assert lesson["finding"] == "not_reproduced"
    assert RESOLUTION["JYVATQXCHBTGRN-UHFFFAOYSA-N"]["substances"] == 0
    assert RESOLUTION["GAEKPEKOJKCEMS-UHFFFAOYSA-N"]["substances"] == 4
    assert "reaxys_dielectric_queue_first_cut.csv" in lesson["attribution"]


def test_lesson_b_the_ec_temperature_label_reproduces() -> None:
    lessons = {item["lesson"]: item for item in _summary()["lessons"]}
    assert lessons["B_ec_temperature_label"]["finding"] == "reproduced"
    assert "36.4" in lessons["B_ec_temperature_label"]["evidence"]
    assert "25 C" in lessons["B_ec_temperature_label"]["evidence"]


def test_lesson_c_8978_is_not_an_ec_melting_point() -> None:
    lessons = {item["lesson"]: item for item in _summary()["lessons"]}
    assert lessons["C_ec_8978_as_melting_point"]["finding"] == "not_reproduced"
    melting = [row for row in OBSERVATIONS if row["reaxys_category"] == "Melting Point"]
    assert all(not row["value_raw"].startswith("89") for row in melting)
    assert "36.4" in [row["value_raw"] for row in melting]


def test_the_transcription_slip_is_labelled_as_ours() -> None:
    controls = {item["key"]: item for item in _summary()["controls"]}
    slip = controls["JBTWLSYIZRCDFA-UHFFFAOYSA-N"]
    assert slip["true_key"] == "JBTWLSYIZRCDFO-UHFFFAOYSA-N"
    assert "transcription error" in slip["meaning"]


# --------------------------------------------------------------------------------------
# Queue key audit.
# --------------------------------------------------------------------------------------


def test_queue_keys_are_sound() -> None:
    audit = queue_key_audit()
    assert len(audit) == 14
    assert [item["substance"] for item in audit if item["verdict"] == "mismatch"] == []
    assert all(item["verdict"] == item["expected_verdict"] for item in audit)
    gvl = next(item for item in audit if item["substance"] == "gamma-valerolactone")
    assert gvl["queue_key"] == "GAEKPEKOJKCEMS-UHFFFAOYSA-N"
    assert gvl["queue_key_source"] == "queue_file"
    emc = next(item for item in audit if item["substance"] == "ethyl methyl carbonate")
    assert emc["queue_key"] == "JBTWLSYIZRCDFO-UHFFFAOYSA-N"
    assert emc["rdkit_key"] == emc["queue_key"]


# --------------------------------------------------------------------------------------
# Reproducibility and prose pins.
# --------------------------------------------------------------------------------------


def test_summary_reproduces_from_the_module() -> None:
    expected = build_summary()
    on_disk = _summary()
    expected["observations_sha256"] = on_disk["observations_sha256"]
    assert json.dumps(on_disk, ensure_ascii=False, sort_keys=True) == json.dumps(
        expected, ensure_ascii=False, sort_keys=True
    )


def test_check_mode_passes_offline() -> None:
    completed = subprocess.run(
        [sys.executable, str(PROBE_PATH), "--check"],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["passed"] is True
    assert payload["csv_rows"] == FROZEN_CSV_ROWS


PINNED_PROSE = [
    "80 observation rows",
    "restricted_crosscheck_only",
    "5.4 at 25 C",
    "89.78 at 25 C",
    "90.5 at 40 C",
    "77.3 at 70 C",
    "0.0193 P at 40 C",
    "1.93 mPa*s",
    "0.0251 P at 25 C",
    "0.0212 St at 25 C",
    "36.9",
    "1.45 mPa*s",
    "0.02591 P at 60 C",
    "2.46, 2.591 and 2.76 mPa*s",
    "2.76 - 60.83",
    "3.11 at 25 C",
    "0.00439 - 0.00669 P",
    "14 matched, 0 mismatched",
    "36.4 C",
]


def test_report_prose_carries_the_pinned_numbers() -> None:
    report = _report()
    missing = [token for token in PINNED_PROSE if token not in report]
    assert missing == []


def test_report_states_the_homo_lumo_answer_plainly() -> None:
    report = _report()
    assert "reference_only" in report
    assert "not one of them carries a number" in report
    assert "No row\nstarts with 89" in report or "No row starts with 89" in report


def test_report_is_lf_and_utf8_without_bom() -> None:
    for path in (REPORT_PATH, CSV_PATH, SUMMARY_PATH):
        raw = path.read_bytes()
        assert b"\r\n" not in raw, path
        assert not raw.startswith(b"\xef\xbb\xbf"), path