"""W19 · N2 Batt-P30K 轨道能交叉核对：交付件一致性测试（离线，不读网络）。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PREREG_PATH = REPOSITORY_ROOT / "probes" / "w19_batt_gap_crosscheck_prereg.json"
SUMMARY_PATH = REPOSITORY_ROOT / "probes" / "w19_batt_gap_crosscheck_summary.json"
SCRIPT_PATH = REPOSITORY_ROOT / "probes" / "w19_batt_gap_crosscheck.py"
REPORT_PATH = REPOSITORY_ROOT / "reports" / "w19_batt_gap_crosscheck.md"

REPORT_HEADLINE = (
    "# W19 · N2 直接交叉核对：我方 GFN2-xTB 轨道能 vs Batt-P30K 轨道能"
    "（名册命中化合物）"
)

REPORT_REQUIRED_NUMBERS = (
    "49",
    "78",
    "0.8223",
    "0.4663",
    "0.1921",
    "0.3475",
    "0.1984",
    "0.7445",
    "0.35",
    "0.80",
    "1.0708",
    "6.8704",
    "0.5293",
    "4668",
    "0.3033",
    "0.6141",
    "0.4343",
    "0.0919",
    "0.8078",
)

REPORT_REQUIRED_PHRASES = (
    "只读复核",
    "models_fitted",
    "promoted = false",
    "cross_level",
    "Reaxys",
)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def load_summary() -> dict:
    return json.loads(read_text(SUMMARY_PATH))


def test_all_five_deliverables_exist() -> None:
    for path in (SCRIPT_PATH, PREREG_PATH, SUMMARY_PATH, REPORT_PATH):
        assert path.is_file(), str(path)
    assert (REPOSITORY_ROOT / "tests" / "test_w19_batt_gap_crosscheck.py").is_file()


def test_deliverables_are_utf8_without_bom_and_lf_only() -> None:
    for path in (SCRIPT_PATH, PREREG_PATH, SUMMARY_PATH, REPORT_PATH):
        raw = path.read_bytes()
        assert not raw.startswith(b"\xef\xbb\xbf"), str(path)
        assert b"\r" not in raw, str(path)


def test_report_first_line_is_the_registered_headline() -> None:
    first = read_text(REPORT_PATH).splitlines()[0]
    assert first == REPORT_HEADLINE


def test_report_pins_every_headline_number() -> None:
    text = read_text(REPORT_PATH)
    for token in REPORT_REQUIRED_NUMBERS:
        assert token in text, token


def test_report_pins_discipline_phrases() -> None:
    text = read_text(REPORT_PATH)
    for token in REPORT_REQUIRED_PHRASES:
        assert token in text, token
    assert "主记分牌尝试 0 次" in text
    assert "不引用 Reaxys 数值" in text


def test_report_states_usable_and_reference_only_per_channel() -> None:
    text = read_text(REPORT_PATH)
    assert "homo：verdict = usable" in text
    assert "lumo：verdict = reference_only" in text
    assert "gap：verdict = reference_only" in text


def test_summary_declares_read_only_and_no_pool_writes() -> None:
    summary = load_summary()
    assert summary["read_only"] is True
    assert summary["reaxys_values_used"] is False
    assert summary["writes_any_pool"] is False
    assert summary["promoted"] is False
    assert summary["main_scoreboard_attempts"] == 0
    assert summary["cross_level"] is True
    assert summary["models_fitted"] == 7


def test_summary_gate_thresholds_unchanged() -> None:
    summary = load_summary()
    assert summary["gate"]["loo_mae_ev_max"] == 0.35
    assert summary["gate"]["pearson_r_min"] == 0.80


def test_summary_pool_matches_the_frozen_denominators() -> None:
    pool = load_summary()["pool"]
    assert pool["roster_rows"] == 246
    assert pool["roster_unique_inchikeys"] == 246
    assert pool["batt_groups_scanned"] == 29519
    assert pool["batt_parsed_records"] == 29519
    assert pool["batt_sha256_matches_registered"] is True
    assert pool["hits"] == 78
    assert pool["hits_match_direct_hit_summary"] is True
    assert pool["primary_n"] == 49
    assert pool["uncovered_hits"] == 29


def test_primary_channel_verdicts() -> None:
    channels = load_summary()["primary"]["channels"]
    assert channels["homo"]["verdict"] == "usable"
    assert channels["lumo"]["verdict"] == "reference_only"
    assert channels["gap"]["verdict"] == "reference_only"
    assert channels["homo"]["pearson_r"] >= 0.80
    assert channels["homo"]["loo_mae_mean"] <= 0.35
    assert channels["lumo"]["pearson_r"] < 0.80
    assert channels["gap"]["pearson_r"] < 0.80


def test_lumo_mae_pass_is_hollow_against_the_constant_baseline() -> None:
    lumo = load_summary()["primary"]["channels"]["lumo"]
    assert lumo["loo_mae_mean"] < lumo["loo_mae_constant_baseline_mean"]
    assert lumo["skill_vs_constant_loo"] < 0.10
    gap = load_summary()["primary"]["channels"]["gap"]
    assert gap["skill_vs_constant_loo"] < 0.0


def test_homo_pass_is_borderline_and_registered_as_such() -> None:
    homo = load_summary()["primary"]["channels"]["homo"]
    assert homo["loo_mae_mean"] <= 0.35
    assert 0.35 - homo["loo_mae_mean"] < 0.01
    assert homo["gate_loo_mae_le_0_35"] is True
    assert homo["gate_pearson_r_ge_0_80"] is True
    assert homo["loo_folds_error_gt_gate"] > 0


def test_consistency_checks_are_within_tolerance() -> None:
    checks = load_summary()["checks"]
    assert checks["batt_gap_identity_n"] == 29519
    assert checks["batt_gap_equals_lumo_minus_homo_max_abs_dev"] < 1e-5
    assert checks["layer_batt_columns_max_abs_dev"] < 1e-5
    assert checks["layer_batt_columns_n"] == 222
    assert checks["expanded_batt_columns_max_abs_dev"] < 1e-5
    assert checks["expanded_batt_columns_n"] == 14004
    assert checks["identity_checked"] == 49
    assert checks["identity_smiles_identical"] == 49
    assert checks["identity_smiles_mismatch"] == 0


def test_prereg_is_locked_before_run_with_the_same_gate() -> None:
    prereg = json.loads(read_text(PREREG_PATH))
    assert prereg["status"] == "locked_before_run"
    thresholds = prereg["gate"]["thresholds"]
    assert thresholds["loo_mae_ev_max"] == 0.35
    assert thresholds["pearson_r_min"] == 0.80
    assert prereg["reaxys_values_used"] is False
    assert prereg["promoted"] is False
    assert prereg["main_scoreboard_attempts"] == 0


def test_summary_and_prereg_are_linked_by_digest() -> None:
    recorded = load_summary()["prereg"]["sha256"]
    assert hashlib.sha256(PREREG_PATH.read_bytes()).hexdigest() == recorded
