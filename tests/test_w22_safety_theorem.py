"""Guards for W22-1: the leakage ("safety") theorem really is off by a factor of two.

The reading this file protects is uncomfortable for the draft.  With a *single-cell*
budget ``A_axis`` the rule ``|d0| >= A_axis`` leaks: in the bounded Monte-Carlo arm the
worst trial loses about 1.3% of the pairs it declared safe, and in the leave-one-rung-out
probe it declares 12.7% of the actually-flipped pairs safe.  Widening to ``2 A_axis``
removes every leak in the bounded arm.  If a later change makes the m=1 arm leak-free
without touching the criterion, this arm has silently changed its meaning.

Two sentences are kept apart on purpose and both are asserted here:

* the THEOREM is the analytic bound ``|delta d| <= 2 A_axis`` (section 1 of the report);
* the SIMULATION is the empirical zero-leak reading at m=2 (section 2).

The simulation may never be quoted as proof of the theorem.
"""

from __future__ import annotations

import json
from pathlib import Path

from probes import w22_safety_theorem as probe

ROOT = Path(__file__).resolve().parents[1]
PREREG = ROOT / "probes/w22_safety_theorem_prereg.json"
SUMMARY = ROOT / "probes/w22_safety_theorem_summary.json"
REPORT = ROOT / "reports/w22_safety_theorem.md"
FIG_LEAKAGE = ROOT / "probes/artifacts/w22_safety_theorem_leakage.png"
FIG_COVERAGE = ROOT / "probes/artifacts/w22_safety_theorem_coverage.png"
PAIRS_CSV = ROOT / "probes/artifacts/w21_rank_pairs.csv"


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _summary() -> dict:
    return _json(SUMMARY)


def test_prereg_is_locked_and_pins_the_design() -> None:
    prereg = _json(PREREG)
    assert prereg["status"] == "locked_before_run"
    assert prereg["prereg_status"] == "locked_before_run"
    design = prereg["design"]
    assert design["n_molecules"] == 200
    assert design["pairs_enumerated"] == 19900
    assert design["trials_per_arm"] == 200
    assert design["m_values"] == [1, 2]
    assert design["r_rungs"] == 10
    assert design["seed"] == 20261002
    assert design["a_axis_ev"] == 0.152
    assert "not verifiable in-repo" in design["a_axis_provenance"]
    assert {item["id"] for item in prereg["registered_criteria"]} == {
        "criterion_m1_must_leak",
        "criterion_m2_must_not_leak",
        "factor_two_is_tight",
        "prospective_loro_factor_two",
        "normal_support_caveat",
    }
    assert prereg["models_fitted"] == 0
    assert prereg["shot_number_taken"] is None
    assert "two_sentence_rule" in prereg


def test_the_theorem_is_the_analytic_triangle_bound() -> None:
    summary = _summary()
    analytic = summary["analytic"]
    assert "triangle inequality" in analytic["theorem_statement"]
    assert "2 A_axis" in analytic["theorem_statement"]
    assert analytic["pair_level_redefinition"]["identity"] == "A_pair <= 2 A_axis"
    assert analytic["pair_level_redefinition"]["criterion_under_redefinition"] == "|d0| >= A_pair"
    assert "A_axis = max_i" in analytic["single_cell_reading"]
    assert "A_pair = max_{i,j}" in analytic["pair_level_reading"]
    assert analytic["tightness"]["uniform_arm_bound_violations"] == 0


def test_the_bound_is_attained_not_conservative() -> None:
    uniform = _summary()["monte_carlo"]["arms"]["uniform_bounded"]
    tight = uniform["tightness_abs_delta_d_over_2A"]
    assert tight["max"] <= 1.0
    assert tight["max"] > 0.95
    assert uniform["bound_violations_per_trial"]["max"] == 0
    witness = uniform["witness"]
    assert witness["opposite_signs"] is True
    assert witness["flipped"] is True
    # a leak witness must sit in the [A, 2A) band and actually cross zero
    assert abs(witness["delta_d"]) <= 2 * 0.152 + 1e-12
    assert abs(witness["d0"]) >= 0.152
    assert abs(witness["d0"]) < 2 * 0.152


def test_bounded_arm_leaks_at_m1_and_never_at_m2() -> None:
    uniform = _summary()["monte_carlo"]["arms"]["uniform_bounded"]
    assert uniform["m1"]["leak_rate_mean"] > 0.0
    assert uniform["m1"]["trials_with_any_leak"] == uniform["trials"] == 200
    assert uniform["m1"]["leak_rate_max"] > uniform["m1"]["leak_rate_mean"]
    assert uniform["m2"]["leak_rate_max"] == 0.0
    assert uniform["m2"]["leak_rate_mean"] == 0.0
    assert uniform["m2"]["trials_with_any_leak"] == 0
    assert uniform["m2"]["total_leak_events"] == 0
    assert uniform["m2"]["mean_safe_pairs"] < uniform["m1"]["mean_safe_pairs"]
    assert uniform["bounded_support"] is True


def test_unbounded_arm_records_the_boundary_of_the_theorem() -> None:
    normal = _summary()["monte_carlo"]["arms"]["normal_unbounded"]
    assert normal["bounded_support"] is False
    assert normal["premise_violations_per_trial"]["trials_with_any"] > 0
    # the premise |delta e_i| <= A fails, so 2A is conditional rather than unconditional
    assert normal["m2"]["leak_rate_max"] > 0.0
    assert normal["m2"]["leak_rate_max"] < normal["m1"]["leak_rate_max"]
    caveat = _summary()["analytic"]["normal_arm_support_caveat"]
    assert caveat["m2_leak_rate_max"] == normal["m2"]["leak_rate_max"]


def test_leave_one_rung_out_predicts_before_spending() -> None:
    loro = _summary()["prospective_loro"]["aggregate"]
    assert loro["predicted_at_2Ahat"]["recall"] >= 0.999
    assert loro["predicted_at_2Ahat"]["precision"] >= 0.99
    assert loro["predicted_at_Ahat"]["recall"] < 0.6
    assert loro["flips_declared_safe_m2"] == 0
    assert loro["flips_declared_safe_m1"] > 1000
    assert loro["flip_capture_recall_m2"] == 1.0
    assert loro["flip_capture_recall_m1"] < 0.9
    assert len(_summary()["prospective_loro"]["per_rung"]) == 10


def test_empirical_cost_of_the_tightening_is_reported() -> None:
    empirical = _summary()["empirical_pair_set"]
    assert empirical["pairs"] == 1176
    assert empirical["source_sha256"] == probe.sha256_file(PAIRS_CSV)
    m1 = empirical["by_multiplier"]["m1"]["on_abs_dP0_eV"]
    m2 = empirical["by_multiplier"]["m2"]["on_abs_dP0_eV"]
    assert m1["safe_pairs"] == 1013
    assert m2["safe_pairs"] == 874
    assert empirical["tightening_cost"]["safe_pairs_lost"] == m1["safe_pairs"] - m2["safe_pairs"] == 139
    assert abs(m1["safe_fraction"] - 1013 / 1176) < 1e-09
    # the criterion is about d0, so the cross-check proxy is reported too
    assert empirical["by_multiplier"]["m1"]["on_separation_threshold_eV"]["safe_pairs"] == 1149


def test_verdicts_are_computed_from_the_readings() -> None:
    verdict = _summary()["verdicts"]
    assert verdict["A3_factor_two_confirmed"] is True
    assert verdict["criterion_m1_must_leak"]["holds"] is True
    assert verdict["criterion_m2_must_not_leak"]["holds"] is True
    assert verdict["factor_two_is_tight"]["holds"] is True
    assert verdict["prospective_loro_factor_two"]["holds"] is True
    assert verdict["refuted_claims"] == []


def test_summary_is_timestamp_free_and_figures_exist() -> None:
    text = SUMMARY.read_text(encoding="utf-8")
    assert "locked_at_utc" not in text
    assert "generated_at" not in text
    assert bytes([13, 10]) not in SUMMARY.read_bytes()
    assert bytes([13, 10]) not in PREREG.read_bytes()
    assert FIG_LEAKAGE.stat().st_size > 5000
    assert FIG_COVERAGE.stat().st_size > 5000
    assert (ROOT / "probes/w22_safety_theorem.py").stat().st_size > 20000


def test_report_keeps_theorem_and_simulation_apart() -> None:
    text = REPORT.read_text(encoding="utf-8")
    for needle in (
        "定理（解析严格界）",
        "仿真（经验读数）",
        "永远不能用来反证或证明",
        "A3 因子 2 成立",
        "sha256",
    ):
        assert needle in text, needle


def test_summary_is_reproducible_byte_for_byte(capsys) -> None:
    assert probe.main(["--write-summary", "--summary", str(SUMMARY)]) == 0
    first = SUMMARY.read_bytes()
    assert probe.main(["--write-summary", "--summary", str(SUMMARY)]) == 0
    second = SUMMARY.read_bytes()
    assert first == second
    assert probe.main(["--check", "--summary", str(SUMMARY)]) == 0
    assert "CHECK OK" in capsys.readouterr().out
    # and an independently built summary matches the file on disk
    assert probe.dumps(probe.build_summary()) == first.decode("utf-8")