"""W32 呈现层的离线测试：只读冻结产物，不占 shot、不产生新读数。

四张图是对 `probes/artifacts/w32_rank_stability.json` 与
`probes/w32_regularization_ladder_summary.json` 的纯呈现。这里断言：冻结读数确实被
逐字钉住（不是手抄）、里程碑数字来自 JSON 而不是打字进去、图名在
`probes/artifacts/` 下且渲染出真实字节。无网络、无模型拟合、不跑 xTB。
"""

from __future__ import annotations

import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))

from probes import w32_presentation_figures as figures

EXPECTED_FIGURES = (
    "w32_fig_noise_floor.png",
    "w32_fig_fidelity_law.png",
    "w32_fig_milestones.png",
    "w32_fig_regularization_curves.png",
)


def test_figure_names_are_w32_prefixed_and_declared_under_artifacts() -> None:
    declared = tuple(path.name for path in (
        figures.FIG_NOISE, figures.FIG_LAW, figures.FIG_MILESTONE, figures.FIG_CURVES))
    assert declared == EXPECTED_FIGURES
    for path in (figures.FIG_NOISE, figures.FIG_LAW, figures.FIG_MILESTONE, figures.FIG_CURVES):
        assert path.parent == figures.ARTIFACTS
        assert path.name.startswith("w32_fig_") and path.name.endswith(".png")


def test_frozen_readings_are_pinned_in_the_preregistrations() -> None:
    figures.verify_pins()
    assert figures.GATE == 0.60
    assert figures.SD_TARGET == 0.05


def test_milestone_numbers_come_from_the_summary_not_from_typing() -> None:
    ladder = figures.read_json(figures.LADDER_JSON)
    readings = ladder["readings"]
    assert figures.FROZEN_BASELINE != figures.FROZEN_HEADLINE
    assert float(ladder["cross_seed"]["anch_frozen_d2"]) == float(
        readings["frozen_mean"])
    assert float(readings["registered_mean"]) == float(
        figures.read_json(figures.LADDER_JSON)["readings"]["registered_mean"])
    assert float(readings["global_best_mean"]) > float(readings["registered_mean"])
    assert abs(float(readings["ceiling_delta"])
               - (float(readings["global_best_mean"]) - float(readings["registered_mean"]))) < 1e-12


def test_inputs_are_the_frozen_w32_products() -> None:
    rank = figures.read_json(figures.RANK_JSON)
    assert len(rank["records"]) == 26
    assert {row["channel"] for row in rank["channels"]} == set(figures.CHANNEL_ORDER)
    ladder = figures.read_json(figures.LADDER_JSON)
    assert len(ladder["configs"]) == 9
    assert len(ladder["seeds"]) == 5


def test_the_capstone_renders_real_bytes(tmp_path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    figures.use_chinese_font(plt)
    rank = figures.read_json(figures.RANK_JSON)
    ladder = figures.read_json(figures.LADDER_JSON)
    originals = (figures.FIG_NOISE, figures.FIG_LAW, figures.FIG_MILESTONE, figures.FIG_CURVES)
    try:
        figures.FIG_NOISE = tmp_path / "a.png"
        figures.FIG_LAW = tmp_path / "b.png"
        figures.FIG_MILESTONE = tmp_path / "c.png"
        figures.FIG_CURVES = tmp_path / "d.png"
        written = (figures.figure_noise_floor(rank, plt), figures.figure_fidelity_law(rank, plt),
                   figures.figure_milestones(ladder, plt),
                   figures.figure_regularization_curves(ladder, plt))
    finally:
        (figures.FIG_NOISE, figures.FIG_LAW, figures.FIG_MILESTONE, figures.FIG_CURVES) = originals
    for path in written:
        assert path.is_file() and path.stat().st_size > 20000, path