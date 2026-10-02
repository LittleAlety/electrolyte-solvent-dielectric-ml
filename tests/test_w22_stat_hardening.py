"""Guards for the Week 22 / lane W22-2 statistics-hardening pass (review B1-B4).

The readings this file protects:

* the compound-level bootstrap CIs are computed on the SAME 49 compounds and the
  SAME resample matrix for every channel;
* the paired delta_tau_b(homo - lumo) 95% CI straddles zero -- the reviewer's B2
  point -- so a silent change that makes the channel gap look sharp is caught;
* the three permutation p-values survive BOTH Bonferroni and Holm;
* the artefacts recorded in the summary hash exactly to the files on disk.
"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PREREG = ROOT / "probes/w22_stat_hardening_prereg.json"
SUMMARY = ROOT / "probes/w22_stat_hardening_summary.json"
PAIR_BOOT = ROOT / "probes/artifacts/w22_stat_hardening_pair_bootstrap.csv"
LOO = ROOT / "probes/artifacts/w22_stat_hardening_leave_one_out.csv"
MULTI = ROOT / "probes/artifacts/w22_stat_hardening_multiple_comparison.csv"
REPORT = ROOT / "reports/w22_stat_hardening.md"
W21_PAIRS = ROOT / "probes/artifacts/w21_rank_pairs.csv"
FROZEN = (
    0.4091179943351143,
    0.4766400383507876,
    0.5861142332208197,
    0.6216672295270079,
)


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _rows(path: Path) -> list:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_prereg_is_locked_with_the_registered_resampling_spec() -> None:
    prereg = _json(PREREG)
    assert prereg["status"] == "locked_before_run"
    res = prereg["resampling"]
    assert res["unit"].startswith("compound")
    assert res["draws"] >= 5000
    assert res["ci_method"] == "percentile"
    assert res["with_replacement"] is True
    assert res["n_compounds_resampled"] == 49
    assert "expand_by_multiplicity" in res["pair_definition"]
    assert prereg["multiple_comparison"]["alpha"] == 0.05
    assert prereg["main_scoreboard_attempts"] == 0


def test_input_pair_table_is_read_and_reproduced_key_for_key() -> None:
    summary = _json(SUMMARY)
    tab = summary["reproduction_audit"]["w21_pair_table"]
    assert tab["pair_rows_read"] == len(_rows(W21_PAIRS)) == 1176
    assert tab["resolved_in_both"] == 451
    assert tab["robust_inversions"] == 0
    assert tab["resolved_in_R_sol_mismatches"] == 0
    assert tab["inversion_mismatches"] == 0
    assert tab["max_abs_dRsol_rounding_gap_eV"] < 1e-06


def test_bootstrap_uses_5000_draws_and_percentile_cis() -> None:
    summary = _json(SUMMARY)
    boot = summary["bootstrap"]
    assert boot["draws"] == 5000
    assert boot["ci_method"] == "percentile"
    for name in ("homo", "lumo", "gap"):
        ci = boot["channels"][name]["kendall_tau_b"]
        assert ci["draws_used"] == 5000
        assert ci["lo"] <= ci["median"] <= ci["hi"]
    homo = boot["channels"]["homo"]["kendall_tau_b"]
    assert homo["lo"] < 0.6887755102040816 < homo["hi"]


def test_paired_delta_tau_b_ci_is_reported_and_straddles_zero() -> None:
    paired = _json(SUMMARY)["paired_delta_tau_b"]
    d = paired["homo_minus_lumo"]
    assert abs(d["point"] - (0.6887755102040816 - 0.46598639455782304)) < 1e-09
    assert d["lo"] <= d["point"] <= d["hi"]
    assert d["ci_straddles_zero"] is True
    assert d["lo"] < 0.0


def test_leave_one_out_has_49_rows_and_records_the_influential_compound() -> None:
    rows = _rows(LOO)
    assert len(rows) == 49
    assert sum(int(r["is_max_influence"]) for r in rows) == 1
    summary = _json(SUMMARY)["leave_one_out"]
    assert summary["rows"] == 49
    assert summary["min_tau_b_without"] <= summary["max_tau_b_without"]
    assert rows[0]["inchikey"] == summary["max_influence_compound"]
    assert float(rows[0]["tau_b_without"]) == summary["max_tau_b_without"]


def test_multiple_comparison_survives_both_corrections() -> None:
    rows = _rows(MULTI)
    assert len(rows) == 3
    for row in rows:
        assert row["verdict"] == "survives_correction"
        assert int(row["survives_bonferroni"]) == 1
        assert int(row["survives_holm"]) == 1
        assert float(row["p_bonferroni"]) >= float(row["p_value_permutation"]) - 1e-12
        assert float(row["p_holm"]) <= float(row["p_bonferroni"]) + 1e-12


def test_output_hashes_in_the_summary_match_the_files_on_disk() -> None:
    summary = _json(SUMMARY)
    for key in ("pair_bootstrap", "leave_one_out", "multiple_comparison"):
        block = summary["outputs"][key]
        path = ROOT / block["path"]
        assert _sha(path) == block["sha256"]
        assert path.stat().st_size == block["bytes"]
    assert REPORT.exists()
    assert (ROOT / "probes/w22_stat_hardening.py").exists()


def test_frozen_scoreboard_is_untouched() -> None:
    summary = _json(SUMMARY)
    assert summary["promotion"]["promoted"] is False
    assert summary["promotion"]["main_scoreboard_attempts"] == 0
    assert [float(v) for v in summary["promotion"]["frozen_untouched"]] == list(FROZEN)