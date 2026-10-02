"""Guards for the Week 23-2 dSCF redox arm (framework Axis A P_1).

Three readings in this file are deliberately uncomfortable and must not be
smoothed over by a later edit:

* H1 and H2 hold with the textbook sign and near-unanimity (dIP < 0 for 100%,
  99.6%, 100% of 238 compounds; dEA > 0 for 100% of 237), and H4 holds: 78.0%
  of the gas-phase anions carry a positive highest-occupied-orbital energy at
  the gas rung against 33.2% under water.  So the arm does measure solvation of
  the ionic states;
* H3 is falsified: only 11 of 238 compounds have |dIP| increasing with eps, and
  the channel means are not ordered either (|mean dIP(thf)| = 1.957 eV is LARGER
  than |mean dIP(benzaldehyde)| = 1.793 eV although eps(thf) < eps(benzaldehyde));
* H5 is falsified on the ordering, not on the offset: the mean signed difference
  against RX-392 is 6.777 eV (so the pre-registered magnitude condition is met)
  but Spearman rho is 0.345 against the 0.60 line, and the EA comparison is
  negative (-0.248).  Solvation improves the agreement monotonically without
  ever reaching the line, which is the honest summary of the whole arm.

H6 is the load-bearing control: the 12 neutral arms reproduce the committed
Week 23-1 layer bit for bit (max |delta| = 0.0 eV), so the ionisation energies
are not contaminated by a geometry change.
"""

from __future__ import annotations

import csv
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

SUMMARY = ROOT / "probes/w23_redox_dscf_summary.json"
PREREG = ROOT / "probes/w23_redox_dscf_prereg.json"
LAYER = ROOT / "data/processed/w23_redox_dscf_layer.csv"
MEDIUM_LAYER = ROOT / "data/processed/w23_orbital_medium_layer.csv"
REFERENCE = ROOT / "data/processed/redox_merged.csv"
DELTA = ROOT / "probes/artifacts/w23_redox_dscf_delta_stats.csv"
MONO = ROOT / "probes/artifacts/w23_redox_dscf_monotonicity.csv"
KOOPMANS = ROOT / "probes/artifacts/w23_redox_dscf_koopmans.csv"
ANION = ROOT / "probes/artifacts/w23_redox_dscf_anion_bound_signature.csv"
RANK = ROOT / "probes/artifacts/w23_redox_dscf_rank_pairs.csv"
TOPK = ROOT / "probes/artifacts/w23_redox_dscf_topk.csv"
STEP = ROOT / "probes/artifacts/w23_redox_dscf_reference_step.csv"
ANCHOR = ROOT / "probes/artifacts/w23_redox_dscf_neutral_anchor.csv"
RETRY = ROOT / "probes/artifacts/w23_redox_dscf_scf_retry_posthoc.csv"
QC = ROOT / "probes/artifacts/w23_redox_dscf_qc.csv"
FIGURE = ROOT / "probes/artifacts/w23_redox_dscf_shift.png"
REPORT = ROOT / "reports/w23_redox_dscf.md"
CHARTER = ROOT / "reports/week23_2_project_charter.md"
PROBE = ROOT / "probes/w23_redox_dscf.py"

FROZEN = (
    0.4091179943351143,
    0.4766400383507876,
    0.5861142332208197,
    0.6216672295270079,
)

ARTIFACTS = (LAYER, DELTA, MONO, KOOPMANS, ANION, RANK, TOPK, STEP, ANCHOR, RETRY, QC)

MEDIA = ("gas", "thf", "benzaldehyde", "water")
SOLVENTS = ("thf", "benzaldehyde", "water")
STATES = ("neutral", "cation", "anion")
ARMS = tuple(
    medium + "_" + state for medium in MEDIA for state in STATES
)


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
    assert prereg["arms"]["count_per_compound"] == 12
    assert len(prereg["arms"]["list"]) == 12
    assert prereg["arms"]["planned_runs"] == 2952
    # the 2952 is not free-floating: 4 media x 3 charge states x 246 compounds
    assert prereg["arms"]["planned_runs"] == (
        prereg["arms"]["count_per_compound"] * prereg["inputs"]["roster"]["rows"]
    )
    assert prereg["inputs"]["roster"]["rows"] == 246
    epsilons = [item["epsilon"] for item in prereg["xtb_protocol"]["media"]]
    assert epsilons == sorted(epsilons)
    assert [item["key"] for item in prereg["xtb_protocol"]["media"]] == list(MEDIA)
    # the declared arm list really is the full cross product
    declared = {(item["medium"], item["role"]) for item in prereg["arms"]["list"]}
    assert declared == {(medium, state) for medium in MEDIA for state in STATES}
    assert prereg["main_scoreboard_attempts_delta"] == 0


def test_the_open_shell_sibling_leaves_the_frozen_closed_shell_builder_alone() -> None:
    from electrolyte_ml.xtb_runner import (
        xtb_open_shell_arguments,
        xtb_optimisation_arguments,
    )

    # the frozen builder still hard-codes the closed-shell spin state
    assert xtb_optimisation_arguments("m.xyz", formal_charge=1) == [
        "m.xyz", "--opt", "--gfn", "2", "--chrg", "1", "--uhf", "0",
    ]
    # and the Week 23-2 sibling is the same command line with the spin made explicit
    assert xtb_open_shell_arguments(
        "m.xyz", formal_charge=1, unpaired_electrons=1
    ) == ["m.xyz", "--opt", "--gfn", "2", "--chrg", "1", "--uhf", "1"]
    assert xtb_open_shell_arguments(
        "m.xyz", formal_charge=-1, unpaired_electrons=1
    ) == ["m.xyz", "--opt", "--gfn", "2", "--chrg", "-1", "--uhf", "1"]
    try:
        xtb_open_shell_arguments("m.xyz", formal_charge=0, unpaired_electrons=-1)
    except ValueError:
        pass
    else:  # pragma: no cover - the guard is the point of the function
        raise AssertionError("a negative spin population must be refused")


def test_summary_is_the_render_of_the_locked_prereg() -> None:
    summary = _json(SUMMARY)
    assert summary["prereg"]["status"] == "locked_before_run"
    assert summary["prereg"]["sha256"] == hashlib.sha256(PREREG.read_bytes()).hexdigest()
    pool = summary["pool"]
    assert pool["n_compounds"] == 246
    assert pool["arms_per_compound"] == 12
    assert tuple(pool["arm_keys"]) == ARMS
    assert pool["planned_runs"] == 2952
    assert pool["actual_runs"] == 2952
    assert pool["matches_prereg"] is True
    assert pool["xtb_version"].startswith("6.7.1")
    assert [item["key"] for item in pool["media"]] == list(MEDIA)
    assert summary["main_scoreboard_attempts_delta"] == 0
    # the roster carries no net-charged record, so the charged-class statistics
    # are empty rather than withheld; the ionic liquids enter as neutral salt pairs
    assert pool["charge_classes"] == {"neutral": 246}
    assert pool["n_charge_class_charged"] == 0


def test_h6_the_neutral_arms_reproduce_the_committed_w23_1_layer_bit_for_bit() -> None:
    summary = _json(SUMMARY)
    assert summary["hypotheses"]["H6"]["verdict"] == "成立"
    assert summary["anchor"]["holds"] is True
    assert summary["anchor"]["n_compounds_compared"] == 243
    assert summary["anchor"]["max_abs_delta_eV"] <= 1e-6
    mine = {row["inchikey"]: row for row in _rows(LAYER)}
    theirs = {row["inchikey"]: row for row in _rows(MEDIUM_LAYER)}
    compared = 0
    for key, row in theirs.items():
        if key not in mine:
            continue
        for channel in ("homo", "lumo", "gap"):
            pairs = [("gas_neutral_" + channel + "_eV", "gas_free_" + channel + "_eV")]
            pairs += [
                (medium + "_neutral_" + channel + "_eV", "free_" + medium + "_" + channel + "_eV")
                for medium in SOLVENTS
            ]
            for ours_column, previous_column in pairs:
                a, b = mine[key][ours_column], row[previous_column]
                if not a.strip() or not b.strip():
                    continue
                assert abs(float(a) - float(b)) <= 1e-6, (key, ours_column)
                compared += 1
    assert compared >= 2000


def test_h1_and_h2_hold_with_the_textbook_sign() -> None:
    summary = _json(SUMMARY)
    assert summary["hypotheses"]["H1"]["verdict"] == "成立"
    assert summary["hypotheses"]["H2"]["verdict"] == "成立"
    for medium in SOLVENTS:
        ip = summary["displacements"]["ip_" + medium]
        ea = summary["displacements"]["ea_" + medium]
        assert ip["share_negative"] >= 0.99
        assert ip["mean_eV"] < -1.5
        assert ea["share_positive"] == 1.0
        assert ea["mean_eV"] > 1.8
    # the magnitudes: solvation pulls the ionisation energy down by ~2 eV and
    # stabilises the anion by ~2 eV, which is the expected sign and size
    assert summary["ip_ea_stats"]["ip"]["gas"]["mean_eV"] > summary["ip_ea_stats"]["ip"]["water"]["mean_eV"]
    assert summary["ip_ea_stats"]["ea"]["gas"]["mean_eV"] < summary["ip_ea_stats"]["ea"]["water"]["mean_eV"]


def test_h3_is_falsified_and_the_channel_means_are_not_even_monotone() -> None:
    summary = _json(SUMMARY)
    assert summary["hypotheses"]["H3"]["verdict"] == "判否"
    monotonicity = summary["monotonicity"]
    assert monotonicity["n"] == 238
    assert monotonicity["strictly_increasing_count"] == 11
    assert monotonicity["holds"] is False
    assert monotonicity["share"] < 0.05
    assert monotonicity["binom_p_greater"] > 0.99
    # and the reason is visible in the means themselves: benzaldehyde has a
    # higher dielectric constant than thf but a SMALLER |mean shift|
    thf = abs(summary["displacements"]["ip_thf"]["mean_eV"])
    benz = abs(summary["displacements"]["ip_benzaldehyde"]["mean_eV"])
    water = abs(summary["displacements"]["ip_water"]["mean_eV"])
    assert thf > benz
    assert water > benz
    measured = {"thf": 7.58, "benzaldehyde": 18.0, "water": 80.4}
    assert measured["thf"] < measured["benzaldehyde"] < measured["water"]


def test_h4_the_anion_signature_separates_the_gas_rung_from_water() -> None:
    summary = _json(SUMMARY)
    assert summary["hypotheses"]["H4"]["verdict"] == "成立"
    assert summary["anion_signature"]["holds"] is True
    gas = summary["anion_signature"]["by_medium"]["gas"]
    water = summary["anion_signature"]["by_medium"]["water"]
    assert gas["n"] == 241 and gas["unbound"] == 188
    assert abs(gas["share"] - 0.7801) < 0.001
    assert abs(water["share"] - 0.3320) < 0.001
    assert abs(summary["anion_signature"]["gas_minus_water"] - 0.4481) < 0.001
    # the three solvent rungs sit together, far below the gas rung
    for medium in SOLVENTS:
        assert 0.30 < summary["anion_signature"]["by_medium"][medium]["share"] < 0.40


def test_h5_is_falsified_on_the_ordering_not_on_the_offset() -> None:
    summary = _json(SUMMARY)
    step = summary["reference_step"]
    assert step["usable"] is True
    assert step["n"] == 10
    assert summary["hypotheses"]["H5"]["verdict"] == "判否"
    assert step["H5_holds"] is False
    gas = step["ip_gas"]
    # the magnitude half of the criterion IS met ...
    assert abs(gas["mean_signed_difference_eV"]) >= 1.0
    assert abs(gas["mean_signed_difference_eV"] - 6.7770) < 0.01
    # ... but the ordering half is not: 0.345 against the 0.60 line
    assert gas["spearman_rho"] < 0.60
    assert abs(gas["spearman_rho"] - 0.3455) < 0.001
    # solvation improves the agreement monotonically and still never reaches it
    assert gas["spearman_rho"] < step["ip_thf"]["spearman_rho"]
    assert step["ip_thf"]["spearman_rho"] < 0.60
    assert step["ip_water"]["spearman_rho"] < 0.60
    # the EA comparison does not even have the right sign
    assert step["ea_water"]["spearman_rho"] < 0.0
    # the reference layer is the free-energy convention, so this is not a pure
    # method error and the report must say so
    assert "自由能" in REPORT.read_text(encoding="utf-8")


def test_the_medium_shift_nearly_rigidly_translates_the_ordering() -> None:
    summary = _json(SUMMARY)
    rows = summary["rank_rows"]
    assert len(rows) == 12
    assert {(row["channel"], row["charge_class"]) for row in rows} == {
        ("ip", "neutral"), ("ea", "neutral"),
    }
    for row in rows:
        assert row["n"] in (237, 238)
        assert row["spearman_rho"] >= 0.94
        assert row["topk_10"] >= 0.83
    # gas -> solvent is the weakest pair and solvent -> solvent the strongest,
    # i.e. the medium shift is close to a rigid translation of the same ordering
    gas_pairs = [row["spearman_rho"] for row in rows if row["left"] == "gas"]
    solvent_pairs = [row["spearman_rho"] for row in rows if row["left"] != "gas"]
    assert min(gas_pairs) < min(solvent_pairs)
    assert max(gas_pairs) < max(solvent_pairs)


def test_the_koopmans_offset_shrinks_with_the_dielectric_ladder() -> None:
    summary = _json(SUMMARY)
    koopmans = summary["koopmans"]
    ip_offsets = [koopmans[medium]["ip_vs_koopmans"]["mean_offset_eV"] for medium in MEDIA]
    ea_offsets = [koopmans[medium]["ea_vs_koopmans"]["mean_offset_eV"] for medium in MEDIA]
    assert abs(ip_offsets[0] - 2.9463) < 0.01
    assert abs(ip_offsets[-1] - 0.6671) < 0.01
    assert abs(ea_offsets[0] + 3.2452) < 0.01
    assert abs(ea_offsets[-1] + 0.9504) < 0.01
    # the gas rung carries the largest offset and the water rung the smallest;
    # the middle two are NOT ordered by eps, which is the same non-monotonicity
    # that falsifies H3
    assert abs(ip_offsets[0]) > abs(ip_offsets[1])
    assert abs(ip_offsets[0]) > abs(ip_offsets[2])
    assert abs(ip_offsets[0]) > abs(ip_offsets[3])
    assert abs(ip_offsets[3]) < abs(ip_offsets[1])
    assert abs(ea_offsets[0]) > abs(ea_offsets[-1])
    # the dSCF value tracks the orbital energy closely in rank terms
    assert koopmans["gas"]["ip_vs_koopmans"]["spearman_rho"] > 0.84
    assert koopmans["gas"]["ea_vs_koopmans"]["spearman_rho"] > 0.94


def test_failures_and_the_scf_retry_stay_labelled_post_hoc() -> None:
    summary = _json(SUMMARY)
    assert summary["failures"]["total"] == 45
    assert sum(summary["failures"]["by_arm"].values()) == 45
    assert summary["retry"]["attempted"] == 45
    assert summary["retry"]["recovered"] == 13
    assert summary["retry"]["post_hoc"] == "not_preregistered"
    rows = _rows(RETRY)
    assert len(rows) == 45
    assert sum(1 for row in rows if row["recovered"] == "yes") == 13
    # the retry is never folded back into a pre-registered reading
    assert "post_hoc" in REPORT.read_text(encoding="utf-8")


def test_no_frozen_reading_moved_and_nothing_was_promoted() -> None:
    summary = _json(SUMMARY)
    assert summary["main_scoreboard_attempts_delta"] == 0
    text = REPORT.read_text(encoding="utf-8")
    for reading in FROZEN:
        assert repr(reading) not in text
    assert "主记分牌尝试 0 次" in text
    assert "不是 DFT 级" in text


def test_artifacts_exist_with_the_expected_headers() -> None:
    for path in ARTIFACTS:
        assert path.is_file(), path
    assert FIGURE.is_file() and FIGURE.stat().st_size > 50_000
    assert _header(DELTA) == ["channel", "medium", "n", "mean_eV", "sd_eV", "share_negative",
                              "share_positive", "share_in_predicted_direction", "threshold",
                              "holds"]
    assert _header(MONO) == ["channel", "n", "strictly_increasing_count", "share",
                             "binom_p_greater", "threshold", "holds"]
    assert _header(ANION) == ["medium", "n", "unbound", "share"]
    assert _header(ANCHOR) == ["inchikey", "name", "max_abs_delta_eV"]
    assert _header(STEP)[0] == "comparison"
    assert _header(QC) == ["medium", "neutral_ok", "cation_ok", "anion_ok",
                           "anion_unbound_share"]
    assert len(_rows(RANK)) == 12
    assert len(_rows(TOPK)) == 12
    assert len(_rows(KOOPMANS)) == 8
    assert len(_rows(LAYER)) == 246


def test_the_layer_columns_are_the_ones_the_summary_declares() -> None:
    header = _header(LAYER)
    for arm in ARMS:
        for suffix in ("_homo_eV", "_lumo_eV", "_gap_eV", "_total_E_hartree", "_status"):
            assert arm + suffix in header, arm + suffix
    for medium in MEDIA:
        for column in ("ip_" + medium + "_eV", "ea_" + medium + "_eV",
                       "ip_koopmans_offset_" + medium + "_eV",
                       "anion_unbound_" + medium):
            assert column in header, column
    for medium in SOLVENTS:
        assert "d_ip_" + medium + "_eV" in header
        assert "d_ea_" + medium + "_eV" in header
    assert "neutral_anchor_max_abs_delta_eV" in header
    assert len(header) == len(set(header))
    # no column is declared and then never filled: either it carries a value
    # somewhere or it does not exist
    empty = [name for name in header if all(not (row[name] or "").strip() for row in _rows(LAYER))]
    assert empty == [], empty


def test_no_artifact_carries_crlf_or_a_bom() -> None:
    for path in ARTIFACTS + (SUMMARY, PREREG, FIGURE, REPORT, CHARTER, PROBE):
        payload = path.read_bytes()
        assert not payload.startswith(b"\xef\xbb\xbf"), path
        if path.suffix in (".csv", ".json", ".md", ".py"):
            assert b"\r\n" not in payload, path


def test_the_report_states_the_boundary_and_both_directions() -> None:
    text = REPORT.read_text(encoding="utf-8")
    for section in (
        "## 1. 池、执行与判据总览",
        "## 2. H6 · 中性臂回归锚（与 W23-1 逐位比对）",
        "## 3. R1 · IP / EA 的四介质分布（中性分子）",
        "## 4. H1 / H2 · 溶剂化位移",
        "## 5. H3 · |dIP| 随 eps 逐化合物单调递增",
        "## 6. R3 · Koopmans 对照",
        "## 7. H4 · 阴离子束缚签名",
        "## 8. R5 · 排序稳定性（IP / EA 在介质之间）",
        "## 9. R6 · RX-392 外部对照",
        "## 10. R8 · 失败与重试登记",
        "## 11. 判词与边界",
    ):
        assert section in text, section
    assert "绝热口径" in text
    assert "不得" in text
    assert "判否" in text
