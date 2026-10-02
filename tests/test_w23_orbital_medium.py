"""Guards for the Week 23-1 ALPB dielectric-ladder arm (framework Axis A P_2).

Three things in this file are deliberately uncomfortable and must not be
smoothed over by a later edit:

* H5 passes exactly (max |delta| = 0.0 eV against the committed W21 gas layer),
  so the three-rung shift is a pure medium effect -- but
* H1 is *falsified* on the free state (the mean shift, 0.01-0.05 eV, is far
  smaller than the per-compound spread, 0.16-0.30 eV) and *inverted* on the
  Li+ state (both orbitals move UP by 3-4 eV, 100% of 216 compounds), which
  means the pre-registered textbook sign was written for the wrong charge
  state, not that the medium does nothing;
* H4 holds for every free-state rung (rho >= 0.984) but breaks for the Li+
  state at the water rung (0.8441 / 0.8161 below the 0.90 line).
"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUMMARY = ROOT / "probes/w23_orbital_medium_summary.json"
PREREG = ROOT / "probes/w23_orbital_medium_prereg.json"
LAYER = ROOT / "data/processed/w23_orbital_medium_layer.csv"
W21_LAYER = ROOT / "data/processed/w21_li_coordination_layer.csv"
DELTA = ROOT / "probes/artifacts/w23_orbital_medium_delta_stats.csv"
MONO = ROOT / "probes/artifacts/w23_orbital_medium_monotonicity.csv"
RANK = ROOT / "probes/artifacts/w23_orbital_medium_rank_pairs.csv"
TOPK = ROOT / "probes/artifacts/w23_orbital_medium_topk.csv"
BATT = ROOT / "probes/artifacts/w23_orbital_medium_batt_step.csv"
QC = ROOT / "probes/artifacts/w23_orbital_medium_qc.csv"
ANCHOR = ROOT / "probes/artifacts/w23_orbital_medium_gas_anchor.csv"
RETRY = ROOT / "probes/artifacts/w23_orbital_medium_scf_retry_posthoc.csv"
FIGURE = ROOT / "probes/artifacts/w23_orbital_medium_shift.png"
REPORT = ROOT / "reports/w23_orbital_medium.md"
CHARTER = ROOT / "reports/week23_project_charter.md"
FROZEN = (
    0.4091179943351143,
    0.4766400383507876,
    0.5861142332208197,
    0.6216672295270079,
)
ARTIFACTS = (LAYER, DELTA, MONO, RANK, TOPK, BATT, QC, ANCHOR, RETRY)
ARMS = (
    "gas_free", "gas_li",
    "free_thf", "free_benzaldehyde", "free_water",
    "li_thf", "li_benzaldehyde", "li_water",
)
MEDIA = ("thf", "benzaldehyde", "water")


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _rows(path: Path) -> list:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _header(path: Path) -> list:
    with path.open(encoding="utf-8", newline="") as handle:
        return next(csv.reader(handle))


def test_prereg_is_locked_and_the_arm_accounting_is_internally_consistent() -> None:
    prereg = _json(PREREG)
    assert prereg["status"] == "locked_before_run"
    assert prereg["arms"]["planned_runs"] == 1968
    assert prereg["arms"]["count_per_compound"] == 8
    assert len(prereg["arms"]["list"]) == 8
    # the 1968 is not free-floating: 8 arms x 246 compounds, and the media are
    # declared in ascending dielectric order so the ladder means what it says
    assert prereg["arms"]["planned_runs"] == (
        prereg["arms"]["count_per_compound"] * prereg["inputs"]["roster"]["rows"]
    )
    epsilons = [item["epsilon"] for item in prereg["xtb_protocol"]["media"]]
    assert epsilons == sorted(epsilons)
    assert prereg["main_scoreboard_attempts_delta"] == 0


def test_summary_is_the_render_of_the_locked_prereg() -> None:
    summary = _json(SUMMARY)
    assert summary["prereg"]["status"] == "locked_before_run"
    assert summary["prereg"]["sha256"] == hashlib.sha256(PREREG.read_bytes()).hexdigest()
    pool = summary["pool"]
    assert pool["n_compounds"] == 246
    assert pool["arms_per_compound"] == 8
    assert tuple(pool["arm_keys"]) == ARMS
    assert pool["actual_runs"] == 1968
    assert pool["matches_prereg"] is True
    assert pool["xtb_version"].startswith("6.7.1")
    assert [item["key"] for item in pool["media"]] == list(MEDIA)
    assert summary["main_scoreboard_attempts_delta"] == 0


def test_the_gas_rung_reproduces_the_committed_w21_layer_bit_for_bit() -> None:
    """H5: the medium shift must not be contaminated by a geometry change."""

    summary = _json(SUMMARY)
    assert summary["hypotheses"]["H5"]["verdict"] == "成立"
    assert summary["anchor"]["holds"] is True
    # 244 of 246 rows carry at least one comparable cell; the other two fail on
    # both sides (W21 and this arm), so they are neither evidence nor counter-evidence
    assert summary["anchor"]["n_compounds_compared"] == 244
    assert summary["anchor"]["max_abs_delta_eV"] <= 1e-6
    mine = {row["inchikey"]: row for row in _rows(LAYER)}
    theirs = {row["inchikey"]: row for row in _rows(W21_LAYER)}
    compared = 0
    for key, row in theirs.items():
        if key not in mine:
            continue
        for ours_column, previous_column in (
            ("gas_free_homo_eV", "homo_free_eV"),
            ("gas_free_lumo_eV", "lumo_free_eV"),
            ("gas_free_gap_eV", "gap_free_eV"),
            ("gas_li_homo_eV", "homo_li_eV"),
            ("gas_li_lumo_eV", "lumo_li_eV"),
            ("gas_li_gap_eV", "gap_li_eV"),
        ):
            a, b = mine[key][ours_column], row[previous_column]
            if not a.strip() or not b.strip():
                continue
            assert abs(float(a) - float(b)) <= 1e-6, (key, ours_column)
            compared += 1
    assert compared >= 1400


def test_h1_is_falsified_and_the_two_failure_modes_are_not_the_same() -> None:
    summary = _json(SUMMARY)
    by_arm = summary["hypotheses"]["H1"]["by_arm"]
    assert by_arm["free_thf"]["share_homo_up_and_lumo_down"] < 0.10
    assert by_arm["li_water"]["share_homo_up_and_lumo_down"] == 0.0
    assert summary["hypotheses"]["H1"]["verdict"] == "判否"
    # free state: the mean is smaller than the spread -> sign-incoherent
    free = summary["channel_shifts"]["free"]["water"]
    assert abs(free["homo"]["delta_mean_eV"]) < free["homo"]["delta_sd_eV"] / 3.0
    # Li+ state: the sign is not absent, it is INVERTED -- every compound moves up
    for medium in MEDIA:
        li = summary["channel_shifts"]["li"][medium]
        assert li["homo"]["share_positive"] == 1.0
        assert li["lumo"]["share_positive"] == 1.0
        assert li["homo"]["delta_mean_eV"] > 2.5
        assert li["lumo"]["delta_mean_eV"] > 2.5


def test_h2_holds_only_for_the_li_dgap_rung() -> None:
    summary = _json(SUMMARY)
    assert summary["hypotheses"]["H2"]["verdict"] == "判否"
    assert summary["monotonicity"]["free"]["homo"]["strictly_increasing_count"] == 7
    assert summary["monotonicity"]["free"]["gap"]["strictly_increasing_count"] == 14
    li_gap = summary["monotonicity"]["li"]["gap"]
    assert li_gap["strictly_increasing_count"] == 147
    assert li_gap["holds"] is True
    assert li_gap["binom_p_greater"] < 1e-6
    assert summary["monotonicity"]["li"]["homo"]["holds"] is False


def test_h3_records_the_medium_shift_as_a_second_order_effect() -> None:
    summary = _json(SUMMARY)
    h3 = summary["h3"]
    assert h3["holds"] is True
    assert summary["hypotheses"]["H3"]["verdict"] == "成立"
    assert h3["n"] == 216
    assert 0.01 < h3["var_ratio_medium_over_gas"] < 0.02
    assert 0.17 < h3["var_ratio_coordination_over_gas"] < 0.18
    assert h3["var_ratio_medium_over_gas"] < h3["var_ratio_coordination_over_gas"] / 5.0


def test_h4_holds_for_the_free_state_and_breaks_for_li_at_the_water_rung() -> None:
    summary = _json(SUMMARY)
    entries = {(item["state"], item["channel"], item["medium"]): item["rho"]
               for item in summary["h4"]["entries"]}
    assert len(entries) == 12
    for medium in MEDIA:
        for channel in ("homo", "lumo"):
            assert entries[("free", channel, medium)] >= 0.98
    assert entries[("li", "homo", "thf")] >= 0.90
    assert entries[("li", "lumo", "benzaldehyde")] >= 0.90
    assert entries[("li", "homo", "water")] < 0.90
    assert entries[("li", "lumo", "water")] < 0.90
    assert summary["hypotheses"]["H4"]["verdict"] == "判否"
    assert abs(summary["h4"]["min_rho"] - 0.8161) < 0.001


def test_the_batt_subset_improves_monotonically_with_the_dielectric_rung() -> None:
    summary = _json(SUMMARY)
    arms = summary["batt"]["arms"]
    assert summary["batt"]["n"] == 49
    assert all(payload["robust_inversions"] == 0 for payload in arms.values())
    for name in arms:
        assert arms[name]["spearman_rho"] == arms[name]["spearman_rho"]
    assert arms["C0_gas"]["spearman_rho"] < arms["C0_thf"]["spearman_rho"]
    assert arms["C1_gas"]["spearman_rho"] < arms["C1_thf"]["spearman_rho"]
    assert abs(arms["C0_thf"]["spearman_rho"] - 0.8798) < 0.001
    assert abs(arms["C1_water"]["spearman_rho"] - 0.9226) < 0.001
    assert arms["C1_water"]["spearman_rho"] == max(
        payload["spearman_rho"] for payload in arms.values()
    )
    # the section 9 battery must still reproduce its W21 predecessor rows
    assert abs(arms["P0_themol_geometry_w21_1"]["spearman_rho"] - 0.8640) < 0.001
    assert arms["P0_themol_geometry_w21_1"]["resolved_in_both"] == 451


def test_failures_and_the_scf_retry_stay_labelled_post_hoc() -> None:
    summary = _json(SUMMARY)
    assert summary["failures"]["total"] == 42
    assert summary["retry"]["attempted"] == 42
    assert summary["retry"]["recovered"] == 11
    assert summary["retry"]["post_hoc"] == "not_preregistered"
    rows = _rows(RETRY)
    assert len(rows) == 42
    assert sum(1 for row in rows if row["recovered"] == "yes") == 11


def test_no_frozen_reading_moved_and_nothing_was_promoted() -> None:
    summary = _json(SUMMARY)
    assert summary["main_scoreboard_attempts_delta"] == 0
    text = REPORT.read_text(encoding="utf-8")
    for reading in FROZEN:
        assert repr(reading) not in text
    assert "主记分牌尝试 0 次" in text


def test_artifacts_exist_with_the_expected_headers() -> None:
    for path in ARTIFACTS:
        assert path.is_file(), path
    assert FIGURE.is_file() and FIGURE.stat().st_size > 50_000
    assert _header(DELTA) == ["state", "medium", "channel", "n", "delta_mean_eV",
                              "delta_sd_eV", "var_ratio_shift_over_gas", "share_positive",
                              "share_negative"]
    assert _header(MONO) == ["state", "channel", "n", "strictly_increasing_count", "share",
                             "binom_p_greater", "threshold", "holds"]
    assert _header(BATT)[0] == "arm"
    assert _header(QC) == ["medium", "intact", "loose", "dissociated", "not_available",
                           "median_li_dist_A", "median_li_q"]
    assert _header(ANCHOR) == ["inchikey", "name", "max_abs_delta_eV"]
    assert len(_rows(RANK)) == 36
    assert len(_rows(LAYER)) == 246


def test_the_layer_columns_are_the_ones_the_summary_declares() -> None:
    header = _header(LAYER)
    for arm in ARMS:
        for suffix in ("_homo_eV", "_lumo_eV", "_gap_eV", "_status"):
            assert arm + suffix in header, arm + suffix
    for arm in ("free_thf", "free_benzaldehyde", "free_water",
                "li_thf", "li_benzaldehyde", "li_water"):
        for suffix in ("_d_homo_eV", "_d_lumo_eV", "_d_gap_eV"):
            assert arm + suffix in header, arm + suffix
    assert "gas_anchor_max_abs_delta_eV" in header
    assert len(header) == len(set(header))


def test_no_artifact_carries_crlf_or_a_bom() -> None:
    for path in ARTIFACTS + (SUMMARY, PREREG, FIGURE, REPORT, CHARTER):
        payload = path.read_bytes()
        assert not payload.startswith(b"\xef\xbb\xbf"), path
        if path.suffix in (".csv", ".json", ".md"):
            assert b"\r\n" not in payload, path


def test_the_report_states_the_boundary_and_both_directions() -> None:
    text = REPORT.read_text(encoding="utf-8")
    for section in (
        "## 1. 池、执行与判据总览",
        "## 2. H5 · 几何同源回归锚",
        "## 3. H1 + R1 · 三档介质的位移分布",
        "## 4. H2 · eps 单调性（逐化合物，非均值）",
        "## 5. H4 + R3 · 排序稳定性（气相 → 介质；介质两两）",
        "## 6. H3 · 介质位移是二阶效应",
        "## 7. R4 · 态 x 介质 均值表（HOMO / LUMO / gap, eV）",
        "## 8. R5 · §9 Batt 子集九层并排",
        "## 9. R6 · gap 与 v03 物理块的一致性核验",
        "## 10. R7 · Li+ 臂质控（与 W21 同判据）",
        "## 11. R8 · 失败与重试登记",
        "## 12. 判词与边界",
    ):
        assert section in text, section
    assert "符号不成体系" in text
    assert "符号被反转" in text
    assert "不是 DFT/SMD" in text
    assert "同 eps 不同隐式模型" in text
    assert "单调改善" in text
