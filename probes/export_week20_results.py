"""Export the Week 20 deliverables (gate -> channel fact, and the intersection fill).

Week 19 closed the literal question the Week 18 charter left open: no lane was promoted and
the main scoreboard stayed at eleven cumulative attempts.  Week 20 changes what the project
buys.  It stops buying epsilon representation levers -- Weeks 16 to 18 killed those
systematically -- and buys two things instead:

* turning "a gate was passed once" into a channel-level fact (W20-1 for eta, W20-2 for safety);
* filling in the multi-channel intersection with features and predictions (W20-3), so the
  four-channel intersection of 7 molecules stops being the binding constraint.

The lanes:

* W20-1 -- eta fairness re-run: budget-aligned in-service arm, GroupKFold 5 folds x 5 repeats;
* W20-2 -- safety channel: Step 1 influence ablation (no shot) and Step 2 modelability (shot);
* W20-3 -- ranking key v1 plus intersection fill over the 115,756 Batt-SLM candidates;
* W20-4 -- the bounded epsilon 0.60 gun: single pre-registered arm, cross-seed mean >= 0.60
           and a five-seed lower bound > 0.55;
* W20-5 -- a formal refusal rule for the epsilon > 60 zone;
* W20-6 -- ceiling probes: Org-Mol provenance, NBS-514 same-source temperature rows, CEP Tier C;
* W20-7 -- the three-layer label rule and a per-cell provenance sidecar;
* W20-8 -- funnel KPI board and the capped threshold-table revision;
* W20-9 -- the governance preconditions and the v1.2.1 archive correction.

Nothing on the frozen side moves.  The frozen baseline 0.4091179943351143, the frozen headline
0.4766400383507876, the leak reference 0.7385332681453336, the single-representation reading
0.6080587938801277 and its cross-seed mean 0.5861142332208197 keep their own definitions.
W20-4 is the only lane allowed to touch the main scoreboard, and it may only do so through the
pre-registered rule it froze before running.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from probes.export_results_common import (
    DEFAULT_OUTPUT_ROOT,
    copy_artifacts,
    read_json,
    run_verifiers,
    write_json,
    write_sha256s,
)

WEEK = "week20"

FROZEN_RED_LINES = {
    "data/dielectric_v03.csv": "ff2142936e06e04b329b70f8597574f75349e54ce876e9fff81309e6d35ccce4",
    "probes/l3_stage1_pilot_pool.csv": "b838febbca4d65975d1820ae9275215288968979b78756611cb031eb7c408b18",
    "probes/l3_backvalidation_prereg.json": "77f61a83b82de346292ff055c4f4c52003bccb6bfc98bf11813048abc6f0db98",
    "data/processed/dielectric_observations_v11plus.csv": "159b928f800a55969963da275ed05c30ce8a19cffc48353a9c490eec68a49af9",
    "probes/dielectric_r2_levers_prereg.json": "ab3503c037f05ac398b3c0c59d0e4845943d49fa5a5349fa46b8944f2bc1bdaa",
    "data/viscosity_v01.csv": "12dfa03f34284c93204d1054f75b5a342fd82094da0ca17cee372b4c581c5b26",
}

MAIN_SCOREBOARD = 0.4091179943351143
MAIN_SCOREBOARD_VERSION = "v2"
MAIN_SCOREBOARD_HEADLINE_R2 = 0.4766400383507876
MAIN_SCOREBOARD_HEADLINE_DELTA_R2 = 0.0675220440156733
MAIN_SCOREBOARD_PROMOTED_AT_UTC = "2026-09-27T01:34:06Z"
MAIN_SCOREBOARD_CUMULATIVE_ATTEMPTS = 12
RANDOM_ROW_LEAK_REFERENCE_R2 = 0.7385332681453336
FROZEN_SINGLE_REPRESENTATION_R2 = 0.6080587938801277
FROZEN_SINGLE_REPRESENTATION_CROSS_SEED = 0.5861142332208197

# Week 20 has exactly one lane that may touch the main scoreboard: W20-4, and only through the
# rule it froze before running (cross-seed mean >= 0.60 AND a five-seed lower bound > 0.55).
# This constant records what that lane actually did, so a reader can tell a passing week from
# a week that merely ran a grid.  W20-4 met the rule, so this week took one attempt.
W20_MAIN_SCOREBOARD_ATTEMPTS = 1

W20_SEEDS = (42, 1234, 2026, 31337, 7)

# Every Week 20 lane is a separate pre-registration with its own pool and its own decision
# rule.  W20-4 is the only lane whose pass rule can add an attempt to the main scoreboard.
LANE_KEYS = (
    "w20_1_eta_fairness",
    "w20_2_safety_ablation",
    "w20_2_safety_model",
    "w20_3_ranking_key_v1",
    "w20_4_epsilon_second_stage",
    "w20_5_refusal",
    "w20_6a_orgmol_provenance",
    "w20_6b_nbs514_rows",
    "w20_6c_cep_tierc",
    "w20_7_label_provenance",
    "w20_8_funnel_kpi",
    "w20_9_governance_and_release",
)

# Lanes written by a parallel worker.  They are registered here so the package picks them up
# the moment they land; until then they are reported as entries of `lanes_missing`, which is a
# reportable state and never a crash.
PENDING_LANES = ()

# `measured` lanes carry a machine-readable summary; `documented` lanes carry only a report;
# `registered` lanes are named but their verdict is not pinned here.
LANE_KIND = {
    "w20_1_eta_fairness": "measured",
    "w20_2_safety_ablation": "registered",
    "w20_2_safety_model": "measured",
    "w20_3_ranking_key_v1": "measured",
    "w20_4_epsilon_second_stage": "measured",
    "w20_5_refusal": "measured",
    "w20_6a_orgmol_provenance": "measured",
    "w20_6b_nbs514_rows": "measured",
    "w20_6c_cep_tierc": "measured",
    "w20_7_label_provenance": "measured",
    "w20_8_funnel_kpi": "measured",
    "w20_9_governance_and_release": "documented",
}

# A lane whose summary carries no top-level verdict token is pinned here as a literal, and the
# test asserts that literal, so a rewritten report cannot silently decouple from this constant.
DOCUMENTED_VERDICTS: dict[str, str] = {}

MEASURED_VERDICT_FALLBACK: dict[str, str] = {}

RECORDED_VERDICTS = {**DOCUMENTED_VERDICTS, **MEASURED_VERDICT_FALLBACK}

LANE_SOURCES = {
    "w20_1_eta_fairness": {
        "probe": "probes/w20_eta_fairness.py",
        "prereg": "probes/w20_eta_fairness_prereg.json",
        "summary": "probes/w20_eta_fairness_summary.json",
        "report": "reports/w20_eta_fairness.md",
        "tests": ("tests/test_w20_eta_fairness.py",),
        "artifacts": ("probes/artifacts/w20_eta_fairness_repeats.csv",),
    },
    "w20_2_safety_ablation": {
        "probe": "probes/w20_safety_ablation.py",
        "prereg": "probes/w20_safety_ablation_prereg.json",
        "summary": "probes/w20_safety_ablation_summary.json",
        "report": "reports/w20_safety_ablation.md",
        "tests": ("tests/test_w20_safety_ablation.py",),
        "artifacts": ("probes/artifacts/w20_safety_ablation_arms.csv",),
    },
    "w20_2_safety_model": {
        "probe": "probes/w20_safety_model.py",
        "prereg": "probes/w20_safety_model_prereg.json",
        "summary": "probes/w20_safety_model_summary.json",
        "report": "reports/w20_safety_model.md",
        "tests": ("tests/test_w20_safety_model.py",),
        "artifacts": ("probes/artifacts/w20_safety_model_repeats.csv",),
    },
    "w20_3_ranking_key_v1": {
        "probe": "probes/w20_ranking_key_v1.py",
        "prereg": "probes/w20_ranking_key_v1_prereg.json",
        "summary": "probes/w20_ranking_key_v1_summary.json",
        "report": "reports/w20_ranking_key_v1_spec.md",
        "tests": ("tests/test_w20_ranking_key_v1.py",),
        "artifacts": ("probes/artifacts/w20_ranking_key_v1_candidates.csv",),
    },
    "w20_4_epsilon_second_stage": {
        "probe": "probes/w20_epsilon_second_stage.py",
        "prereg": "probes/w20_epsilon_second_stage_prereg.json",
        "summary": "probes/w20_epsilon_second_stage_summary.json",
        "report": "reports/w20_epsilon_second_stage.md",
        "tests": ("tests/test_w20_epsilon_second_stage.py",),
        "artifacts": (
            "probes/artifacts/w20_epsilon_second_stage_repeats.csv",
            "probes/w20_epsilon_second_stage_placebo_summary.json",
        ),
    },
    "w20_5_refusal": {
        "probe": "probes/w20_refusal.py",
        "prereg": "probes/w20_refusal_prereg.json",
        "summary": "probes/w20_refusal_summary.json",
        "report": "reports/w20_refusal.md",
        "tests": ("tests/test_w20_refusal.py",),
        "artifacts": ("probes/artifacts/w20_refusal_rule.json",),
    },
    "w20_6a_orgmol_provenance": {
        "probe": "probes/w20_orgmol_provenance.py",
        "prereg": "probes/w20_orgmol_provenance_prereg.json",
        "summary": "probes/w20_orgmol_provenance_summary.json",
        "report": "reports/w20_orgmol_provenance.md",
        "tests": ("tests/test_w20_orgmol_provenance.py",),
        "artifacts": ("probes/artifacts/w20_orgmol_provenance_rows.csv",),
    },
    "w20_6b_nbs514_rows": {
        "probe": "probes/w20_nbs514_rows.py",
        "prereg": "probes/w20_nbs514_rows_prereg.json",
        "summary": "probes/w20_nbs514_rows_summary.json",
        "report": "reports/w20_nbs514_rows.md",
        "tests": ("tests/test_w20_nbs514_rows.py",),
        "artifacts": ("probes/artifacts/w20_nbs514_rows.csv",),
    },
    "w20_6c_cep_tierc": {
        "probe": "probes/w20_cep_tierc.py",
        "prereg": "probes/w20_cep_tierc_prereg.json",
        "summary": "probes/w20_cep_tierc_summary.json",
        "report": "reports/w20_cep_tierc.md",
        "tests": ("tests/test_w20_cep_tierc.py",),
        "artifacts": (),
    },
    "w20_7_label_provenance": {
        "probe": "probes/w20_label_provenance.py",
        "prereg": "probes/w20_label_provenance_prereg.json",
        "summary": "probes/w20_label_provenance_summary.json",
        "report": "reports/w20_label_provenance.md",
        "tests": ("tests/test_w20_label_provenance.py",),
        "artifacts": ("probes/artifacts/w20_label_provenance_sidecar.csv",),
    },
    "w20_8_funnel_kpi": {
        "probe": "probes/w20_funnel_kpi.py",
        "prereg": "probes/w20_funnel_kpi_prereg.json",
        "summary": "probes/w20_funnel_kpi_summary.json",
        "report": "reports/w20_funnel_kpi.md",
        "tests": ("tests/test_w20_funnel_kpi.py",),
        "artifacts": (),
    },
    "w20_9_governance_and_release": {
        "probe": None,
        "prereg": None,
        "summary": None,
        "report": "reports/week20_project_charter.md",
        "tests": (),
        "artifacts": (),
    },
}

CARRY_FORWARD = (
    ("README.md", "README.md"),
    ("reports/decisions_log.md", "decisions_log.md"),
    ("data/dielectric_v03.csv", "dielectric_v03.csv"),
    ("data/dielectric_v04.csv", "dielectric_v04.csv"),
    ("data/viscosity_v02.csv", "viscosity_v02.csv"),
    ("probes/four_channel_coverage_summary.json", "four_channel_coverage_summary.json"),
    ("probes/homo_lumo_baselines_summary.json", "homo_lumo_baselines_summary.json"),
    ("probes/walden_dn_channel_summary.json", "walden_dn_channel_summary.json"),
    ("probes/dielectric_applicability_domain_summary.json", "dielectric_applicability_domain_summary.json"),
    ("reports/dielectric_applicability_domain.md", "dielectric_applicability_domain.md"),
    ("probes/dielectric_coordination_block_v3_summary.json", "dielectric_coordination_block_v3_summary.json"),
    ("probes/dielectric_splitters_auc_summary.json", "dielectric_splitters_auc_summary.json"),
    ("reports/dielectric_splitters_auc.md", "dielectric_splitters_auc.md"),
    ("data/external/SolvFunc-87.csv", "SolvFunc-87.csv"),
    ("data/external/Batt-SLM-RX-392.csv", "Batt-SLM-RX-392.csv"),
    ("reports/week20_project_charter.md", "week20_project_charter.md"),
    ("paper/release_notes_v1.2.1.md", "release_notes_v1.2.1.md"),
)


def _exists(relative: object) -> bool:
    if relative is None:
        return False
    return (REPOSITORY_ROOT / str(relative)).is_file()


def _declared_files(key: str) -> tuple[str, ...]:
    """Every repository path a lane bundle claims, present or not."""

    sources = LANE_SOURCES[key]
    files: list[str] = []
    for field in ("probe", "prereg", "summary", "report"):
        value = sources[field]
        if value is not None:
            files.append(str(value))
    files.extend(str(item) for item in sources["tests"])
    files.extend(str(item) for item in sources["artifacts"])
    return tuple(files)


def _missing_lane_keys() -> tuple[str, ...]:
    """A lane is missing when its report is not on disk yet."""

    return tuple(key for key in LANE_KEYS if not _exists(LANE_SOURCES[key]["report"]))


def _lane_tests(key: str) -> tuple[str, ...]:
    return tuple(str(item) for item in LANE_SOURCES[key]["tests"] if _exists(item))


def _verifier_tests() -> tuple[str, ...]:
    ordered: list[str] = []
    for key in LANE_KEYS:
        for relative in _lane_tests(key):
            if relative not in ordered:
                ordered.append(relative)
    return tuple(ordered)


def _lane_artifacts() -> tuple[tuple[str, str], ...]:
    """Flatten every lane bundle into (source, destination) copy pairs.

    Files a parallel lane has not landed yet are skipped here so a missing report is
    reported through `lanes_missing` instead of raising from the copy step.
    """

    pairs: list[tuple[str, str]] = []
    for key in LANE_KEYS:
        sources = LANE_SOURCES[key]
        for field in ("probe", "prereg", "summary", "report"):
            relative = sources[field]
            if _exists(relative):
                name = str(relative)
                pairs.append((name, Path(name).name))
        for relative in sources["tests"]:
            name = str(relative)
            if _exists(name):
                pairs.append((name, Path(name).name))
        for relative in sources["artifacts"]:
            name = str(relative)
            if _exists(name):
                pairs.append((name, Path(name).name))
    return tuple(pairs)


def _figures() -> tuple[str, ...]:
    """Week 20 figures, discovered from disk so a renamed plot cannot drop out."""

    directory = REPOSITORY_ROOT / "probes" / "artifacts"
    if not directory.is_dir():
        return ()
    return tuple(
        sorted(
            path.relative_to(REPOSITORY_ROOT).as_posix()
            for path in directory.glob("w20_*.png")
        )
    )


FIGURES = _figures()

ARTIFACTS = CARRY_FORWARD + _lane_artifacts()

VERIFIER_TESTS = _verifier_tests()

VERIFIERS = (
    "scripts/verify_dielectric_v04.py",
    "scripts/verify_orbital_second_source.py --check",
    "scripts/verify_themol_orbital_layer.py --check",
    "scripts/verify_themol_orbital_layer_expanded.py --check",
    "scripts/verify_four_core_registry.py --check",
    "scripts/verify_reaxys_v1x_stocking_probe_roster.py --check",
    "scripts/verify_liquid_window_gate.py --check",
    "scripts/verify_walden_dn_channel.py --check",
    "probes/verify_unimol_probe_spec.py --check",
    (
        "-m pytest tests/test_repo_hygiene.py "
        + " ".join(VERIFIER_TESTS)
        + " -q -p no:cacheprovider"
    ),
)


def _sha256(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _head_commit(source_root: Path) -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=source_root,
        capture_output=True,
        text=True,
        check=False,
    )
    return (completed.stdout or "").strip()


def _worktree_status(source_root: Path) -> tuple[bool, int]:
    completed = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=source_root,
        capture_output=True,
        text=True,
        check=False,
    )
    lines = [line for line in (completed.stdout or "").splitlines() if line.strip()]
    return bool(lines), len(lines)


def _frozen_red_lines() -> dict[str, dict[str, object]]:
    result: dict[str, dict[str, object]] = {}
    for relative, expected in FROZEN_RED_LINES.items():
        path = REPOSITORY_ROOT / relative
        measured = _sha256(path) if path.is_file() else None
        result[relative] = {
            "expected_sha256": expected,
            "measured_sha256": measured,
            "intact": measured == expected,
        }
    return result


CARRY_FIELDS = (
    "verdict",
    "verdict_statement",
    "promoted",
    "role",
    "pool",
    "pools",
    "gate",
    "produces_reading",
    "prereg_status",
    "promotes_no_reading",
    "main_scoreboard_untouched",
    "scoreboard_attempts_delta",
    "shot_number_taken",
    "three_questions",
    "honest_boundary",
    "honest_boundaries",
    "cross_level",
    "shot_accounting_judgement",
    "boundary_revision",
)


def _lane_prereg(key: str) -> dict[str, object]:
    """Read a lane pre-registration and prove it was locked before the run."""

    relative = str(LANE_SOURCES[key]["prereg"])
    path = REPOSITORY_ROOT / relative
    payload = read_json(path)
    # `status` is the canonical key; `prereg_status` is accepted as an alias so a
    # pre-registration that declares the same fact under the other name is still
    # recognised as locked instead of aborting the whole package.
    prereg_status = payload.get("status", payload.get("prereg_status"))
    return {
        "path": relative,
        "sha256": _sha256(path),
        "status": prereg_status,
        "locked_before_run": prereg_status == "locked_before_run",
        "seeds": payload.get("seeds"),
    }


def _lane_payload(key: str) -> dict[str, object]:
    """Read one lane bundle and surface the fields the package quotes."""

    sources = LANE_SOURCES[key]
    report_relative = str(sources["report"])
    report_path = REPOSITORY_ROOT / report_relative
    payload: dict[str, object] = {
        "kind": LANE_KIND[key],
        "report": report_relative,
        "report_present": report_path.is_file(),
        "report_sha256": _sha256(report_path) if report_path.is_file() else None,
        "probe": str(sources["probe"]) if sources["probe"] is not None else None,
        "tests": [str(item) for item in sources["tests"]],
        "tests_present": [str(item) for item in _lane_tests(key)],
        "artifacts": [str(item) for item in sources["artifacts"]],
        "declared_files": list(_declared_files(key)),
        "declared_files_missing": [item for item in _declared_files(key) if not _exists(item)],
        "prereg": _lane_prereg(key) if _exists(sources["prereg"]) else None,
        "summary_path": str(sources["summary"]) if sources["summary"] is not None else None,
        "summary_sha256": None,
        "summary_top_level_keys": [],
        "fields": {},
    }
    carried: dict[str, object] = {}
    verdict = None
    promoted = None
    verdict_source = None
    summary_relative = sources["summary"]
    if _exists(summary_relative):
        summary = read_json(REPOSITORY_ROOT / str(summary_relative))
        verdict = summary.get("verdict")
        promoted = summary.get("promoted")
        if verdict is not None:
            verdict_source = "summary"
        # Lane summaries do not share one schema: some carry the decision at the top
        # level, some nest it under a container.  Walk the known containers so a lane
        # cannot silently report promote=True by omission.
        for container_name, verdict_field, promoted_field in (
            ("decision", "verdict", "promotable"),
            ("primary_gate", "verdict", None),
            ("decisions", "verdict", "promotable"),
            ("promotion", None, "promoted"),
        ):
            container = summary.get(container_name)
            if not isinstance(container, dict):
                continue
            if verdict is None and verdict_field is not None:
                verdict = container.get(verdict_field)
                if verdict is not None:
                    verdict_source = "summary." + container_name + "." + verdict_field
            if promoted is None and promoted_field is not None:
                promoted = container.get(promoted_field)
        for field in CARRY_FIELDS:
            if field in summary:
                carried[field] = summary[field]
        payload["summary_sha256"] = _sha256(REPOSITORY_ROOT / str(summary_relative))
        payload["summary_top_level_keys"] = sorted(str(name) for name in summary)
    if verdict is None and key in RECORDED_VERDICTS:
        verdict = RECORDED_VERDICTS[key]
        verdict_source = "recorded_lane_verdict"
    carried["verdict"] = verdict
    carried["promoted"] = bool(promoted) if promoted is not None else False
    carried["verdict_source"] = verdict_source
    payload["fields"] = carried
    return payload


def export_results(*, output_root: Path, overwrite: bool) -> dict:
    import shutil

    week_root = output_root / WEEK
    if week_root.exists() and not overwrite:
        raise FileExistsError(str(week_root) + " already exists; pass --overwrite")

    frozen = _frozen_red_lines()
    if not all(bool(entry["intact"]) for entry in frozen.values()):
        broken = sorted(name for name, entry in frozen.items() if not entry["intact"])
        raise ValueError("a frozen red line moved: " + ", ".join(broken))

    worktree_dirty, dirty_paths = _worktree_status(REPOSITORY_ROOT)
    head_commit = _head_commit(REPOSITORY_ROOT)

    lanes_missing = list(_missing_lane_keys())
    lanes = {key: _lane_payload(key) for key in LANE_KEYS}
    for key, payload in lanes.items():
        prereg = payload["prereg"]
        if prereg is not None and not bool(dict(prereg)["locked_before_run"]):
            raise ValueError("lane " + key + " has no locked pre-registration")

    copied = copy_artifacts(REPOSITORY_ROOT, week_root, ARTIFACTS)

    figures: list[str] = []
    for relative in FIGURES:
        source = REPOSITORY_ROOT / relative
        if not source.is_file():
            continue
        destination = week_root / Path(relative).name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        figures.append(destination.relative_to(week_root).as_posix())

    verification = run_verifiers(REPOSITORY_ROOT, VERIFIERS)

    verdicts = {
        key: {
            "verdict": dict(payload["fields"]).get("verdict"),
            "promoted": dict(payload["fields"]).get("promoted"),
        }
        for key, payload in lanes.items()
    }
    promoted_lanes = sorted(key for key, block in verdicts.items() if bool(block["promoted"]))

    summary = {
        "schema_version": 1,
        "week": WEEK,
        "generated_at_utc": _utc_now(),
        "source_root": str(REPOSITORY_ROOT),
        "artifacts_commit": head_commit,
        "worktree_dirty": worktree_dirty,
        "worktree_dirty_paths": dirty_paths,
        "provenance_note": (
            "artifacts_commit is the commit that identifies the delivered bytes; a dirty "
            "worktree means no commit identifies them, so this field must be re-read "
            "after the close-out commit"
        ),
        "main_scoreboard": {
            "schema_version": 2,
            "version": MAIN_SCOREBOARD_VERSION,
            "baseline": {
                "value": MAIN_SCOREBOARD,
                "status": "retained_unchanged",
                "still_used_as_the_comparability_anchor": True,
            },
            "headline": {
                "value": MAIN_SCOREBOARD_HEADLINE_R2,
                "delta_vs_baseline": MAIN_SCOREBOARD_HEADLINE_DELTA_R2,
                "promoted_at_utc": MAIN_SCOREBOARD_PROMOTED_AT_UTC,
                "configuration": (
                    "hybrid Morgan+Physical 0.5*(Morgan+Physical) plus lever 4 (conformer-average "
                    "dipole, 2 columns) plus lever 8 (Li+ coordination block, 5 columns)"
                ),
                "pool": "457 rows / 97 compounds / 276 distinct (compound, temperature) pairs",
                "folds": "GroupKFold by InChIKey, 10 repeats x 5 folds, seed 42",
            },
            "touched_this_week": True,
            "touched_by": (
                "W20-4 (section 28.60) added one attempt through the rule it froze before running: "
                "the registered arm hp2_d4_n200_lr0.05_mcw5_ss0.8_cs0.8_bin128 cleared a cross-seed "
                "mean of 0.6216672295270079 (>= 0.60) with a five-seed lower bound of "
                "0.5999547508973201 (> 0.55). The attempt is recorded on the ledger; the frozen "
                "headline and the frozen baseline are not rewritten by it. See "
                "shots.main_scoreboard_attempts."
            ),
            "mixing_rule": (
                "the headline and the baseline may appear together only with this block own "
                "configuration lines; they are never divided, added, or compared as two "
                "models, and neither is ever compared with the v1.0 headline 0.364"
            ),
        },
        "shots": {
            "main_scoreboard_attempts": W20_MAIN_SCOREBOARD_ATTEMPTS,
            "cumulative_main_scoreboard_attempts": MAIN_SCOREBOARD_CUMULATIVE_ATTEMPTS,
            "cumulative_note": (
                "Week 14 read 10, Week 17 added one, Weeks 18 and 19 added none, and Week 20 "
                "added the one attempt the W20-4 lane took when its registered arm cleared the "
                "frozen gate; the cumulative total is the running total."
            ),
        },
        "main_scoreboard_attempts_this_week": W20_MAIN_SCOREBOARD_ATTEMPTS,
        "cumulative_main_scoreboard_attempts": MAIN_SCOREBOARD_CUMULATIVE_ATTEMPTS,
        "frozen_reference_readings": {
            "baseline_r2": MAIN_SCOREBOARD,
            "headline_r2": MAIN_SCOREBOARD_HEADLINE_R2,
            "single_representation_r2": FROZEN_SINGLE_REPRESENTATION_R2,
            "single_representation_cross_seed_mean": FROZEN_SINGLE_REPRESENTATION_CROSS_SEED,
            "random_row_leak_reference_r2": RANDOM_ROW_LEAK_REFERENCE_R2,
        },
        "week20_seeds": list(W20_SEEDS),
        "lanes": lanes,
        "lane_verdicts": verdicts,
        "promoted_lanes": promoted_lanes,
        "no_lane_promotes": promoted_lanes == [],
        "lanes_missing": lanes_missing,
        "pending_lanes": list(PENDING_LANES),
        "figures_present": figures,
        "frozen_red_lines": frozen,
        "frozen_red_lines_all_intact": all(bool(entry["intact"]) for entry in frozen.values()),
        "verification": verification,
        "verification_passed": bool(verification.get("passed")),
        "artifacts": copied,
    }

    write_json(week_root / "week20_summary.json", summary)
    write_json(week_root / "verification.json", verification)
    (week_root / "README.md").write_text(README_TEXT, encoding="utf-8", newline=chr(10))
    write_sha256s(week_root)
    return summary


README_TEXT = """# Week 20 交付包（通道线 · 排序线 · 数据线 · 治理：ε 有界达标枪过门 / η 公平性复核 / 安全通道 / 排序键 v1 / 高 ε 拒答 / 封顶探针 / 标签溯源 / 漏斗 KPI）

数据血缘: 冻结表 `data/dielectric_v03.csv` **未改动**（digest `ff2142936e…35ccce4`）；Week 17 / 18 / 19 已发布工件与 week1–week19 交付包未被触碰。
冻结**基线 `0.4091179943351143`** 与冻结**头条 `0.4766400383507876`**（v2：Morgan+Physical ＋ 杠杆 4 ＋ 杠杆 8；**457** 行 / **97** 化合物 = **276** 个（化合物, T）对；训练侧全表 **2029** 行）**一个字都不动**。
Week 20 十二条 lane 里**只有 W20-4 晋升**：预注册臂跨种子均值 **0.6216672295270079** ≥ 0.60、五种子下界 **0.5999547508973201** > 0.55 ⇒ 本周主记分牌**尝试 1 次、累计 12 次**（本仓第 12 次）。其余十一条 lane **各自贡献 0 次**、`promoted = false`。
生成脚本: `probes/export_week20_results.py`

## 头条（逐条照实，不许外推）

1. **W20-4（§28.60）ε「有界达标枪」过门并晋升 —— 本周唯一晋升，也是本仓第 12 次主记分牌尝试**。单臂预注册 `hp2_d4_n200_lr0.05_mcw5_ss0.8_cs0.8_bin128`（depth 4 / 200 树 / lr 0.05 / mcw 5 / bin 128）在 `Physical(lever4)` 上跨种子均值 **0.6216672295270079**、五种子下界 **0.5999547508973201**（4/5 种子单种子即 ≥ 0.60）。机制：当年冻结的 depth 2 超参是为 2048 维稀疏 Morgan 定的，稠密 13–15 列物理特征下几乎必然欠拟合。
2. **W20-4 的纪律比读数更重要**：网格内**更高**的旁臂 `…mcw5…bin64`（跨种子均值 **0.6249509650342622**）**没有**被用来改判；判词只由预注册臂一个数决定，其余 8 臂 × 5 种子 = 40 个读数只作附带信息。
3. **W20-4 锚点逐位复现 + placebo 塌缩**：seed 42 / `xgb_reference` = `0.6080587938801277`，|gap| = 0.0（容差 1e-9）；泄漏审计 50 折全 0；seed 2026 置换靶值后注册臂跨种子均值塌到 **0.41179237661783363**（< 0.60 且 < 真实同臂均值），`collapsed = true`。
4. **W20-1（§28.57）η 公平性复核：在役臂补齐调参与多种子预算后仍输给 Chemprop**。组内 5 折 × 5 重复、池 4151 行 / 976 键：Chemprop **0.1054414994165841** vs 在役（三配置网格 + 训练行内 GroupKFold(3) 选择 + 三种子集成）**0.15963939692814613**，Δ = **-0.05419789751156204**（门 0.15；三种子分别为 -0.055427 / -0.054354 / -0.052812，全部超过 ±0.02 容差）⇒ `eta_crosses_gate_out_of_fold`。
5. **W20-1 族级池给出不同判词、主判词只看行级**：族级 3582 行 / 957 键，Chemprop `0.1014586835798006` vs 在役 `0.1471395849716971`（两侧都过 0.15）⇒ `incumbent_budget_closes_gate`。本件不晋升、不占 shot 编号、主记分牌贡献 0 次。
6. **W20-1 的 placebo 未塌缩，照实登记**：置换靶值后网格 MAE **0.3952143564868206** vs 常数组内预测器 **0.39910182316678505**，`collapsed = false`（单侧塌缩检查、本次未塌缩），不得当作塌缩证据引用。
7. **W20-1 授权 W20-3 把 η 并入排序键 —— 但键没有加宽**。按 W20-3 锁定预注册：键加宽需**新预注册**钉 η 的键列与方向，且模块内 η 的门读数仍取**族级**冻结值 `0.17477197208762`（> 0.15，未过）⇒ `extension_status.viscosity = {verdict_present: true, verdict: eta_crosses_gate_out_of_fold, merged: false}`，键仍只有 HOMO / LUMO 两维等权。
8. **W20-3（§28.59）排序键 v1 + Tier C 交集填充：空前沿**。Batt-SLM **115,756** 候选在 D1 域规则下**全部域外**（`in_domain = 0`、`front_size = 0`、`top_20 = []`）；候选 CSV 16 列、45,093,401 B、sha256 `b52f720bfa904a1c71e730e0d8fb2bb7ec7d4041ce9aae7ce7b1835c518ae6c5`。**空前沿是机制在正确工作、不是失败**：域外**不给分**，而不是给一个会被误读的低分。
9. **W20-2 Step 1（§28.58）安全通道影响力消融：液窗过滤把排序头整体搬走，但提升主要来自域包含**。head purity@10/20/50 = arm0 `0.0 / 0.0 / 0.02`、arm1 **`1.0 / 1.0 / 0.98`**；池内参考密度 `0.002642365933805346` vs `0.9142857142857143`（差 **346.05×**）；Jaccard@10/20/50 = `0.0 / 0.0 / 0.010101010101010102`，候选清单改变 **20 / 40 / 98**。消融池：注册表液窗通道 218 行、轨道可评分 29,519 行、两者交集 **70** 行。
10. **W20-2 Step 2（§28.58，shot 22）安全通道可建模、但不晋升**：三目标共用 **186** 行，281 维特征（Morgan count r2 256 + 25 个 RDKit 描述符）、ExtraTreesRegressor(300)、GroupKFold by InChIKey 5 折 × 5 种子。跨种子均值 MAE：mp **24.97767123875773 K** / bp **25.395136749805708 K** / fp **18.93154740989103 K**，对各自**折内均值基线** `40.645869505093216 / 51.918480354950496 / 41.417524232531726 K`；placebo 全塌缩（mp 48.36 / bp 59.37 / fp 47.20 K，**均高于**自己的基线）。判 `modelable_all`、`blocking_conditions = []`。**样本差照实声明**：约 **19–23×** 少于 Angew 2024 参考（3,504–4,235 行），两个 MAE 尺度不可比、不作优越性声明。
11. **W20-5（§28.61）高 ε 区正式拒答机制**：冻结注册表 **31,949** 行、带 ε **247** 行、被拒 **187** 行 ⇒ ε 拒答率 **0.757085020242915**；高 ε 规则 9 行、D1 域规则 183 行、两规则同时命中 5 行、可排序 60 行；出口码 `refused_experimental_queue`（进实验测量队列、不进短名单）。
12. **W20-6（§28.62）三条封顶探针：全部不破封顶**。① Org-Mol 溯源 `inadmissible`（CC BY-NC-ND 4.0、数据未发布、冻结引用里无该表、无 InChIKey）；② NBS Circular 514 转录 **636** 行 → 名册命中 121 → 候选 **28** → **可用 26**（连通块唯一 25），三关全过但 `ceiling_break = false`；③ CEP 88k DFPT 句柄 `not_identifiable`、许可 `not_verifiable`、仅 Tier C。
13. **W20-7（§28.63）标签来源分层**：封闭 role 词汇表（`primary_reference` / `calibrated_estimate` / `reference_only` / `feature_only`）+ **11** 行 sidecar；注册表覆盖 34,131 键（density 2,178 / dielectric 247 / liquid_window 218 / orbitals 29,868 / redox_label 392 / viscosity 1,228）。**ML 预测值永不入池；受限许可值永不入池；同通道标签必须同源同水平。**
14. **W20-8（§28.64）漏斗 KPI 定板 + 封顶修订**：pooled `auc_gt15 = 0.8947205768486257`、`auc_gt30 = 0.9392420870425322`、Spearman `0.7737616891926036`、top20 精度 **0.95**（base rate `0.26258205689277897`）。阶梯表 `0.58–0.65` 档前提（化合物覆盖再翻倍）已被 W17 证否 ⇒ 标 **`capped`**；封顶链 **161 → 157 → 153**、净新增上界 **+4**。
15. **W20-9（§28.65）治理与发布登记**：v1.2.1 归档更正发布（tag `102198d`、Zenodo 记录 **23006276**、DOI `10.5281/zenodo.23006276`）、shot 编号冻结、发布线冻结（W20 期间不移动任何 tag、不编辑任何 Release 正文）、台账规则入册。**收口时回填**：W20-4 过门 ⇒ 本周尝试 1 次 / 累计 12 次，W20-4 为 W20 第二支产读数枪、取 **shot 23**。
16. **诚实边界未变**：ε 的诚实**单表示跨种子端点**仍是 **0.5861142332208197**，**永不**与冻结头条 `0.4766400383507876` 或本次晋升读数 `0.6216672295270079` 混比 —— 各是各的口径；诊断总纲仍是「**排序学会了、量级学不会**」（R² 量后者、AUC 量前者）。`0.70` 在现有法律与物理约束下**无路径**。

## 交付内容

- 十二条 lane 各自的 `probe / prereg / summary / report / tests / artifacts`（见 `week20_summary.json` 的 `lanes`；缺件记在 `lanes_missing`，本周应为空）。
- 图（`probes/artifacts/` 下全部 `w20_*.png`：`w20_epsilon_second_stage_cross_seed.png`、`w20_eta_fairness_delta.png`、`w20_funnel_kpi_ranking.png`）。
- 冻结证据与红线清单（`frozen_red_lines`，逐文件 sha256 实测比对）。
- `verification.json`：逐条校验命令退出码。
- `decisions_log.md`：含 §28.57–§28.65 九段。
- `week20_summary.json` 的 `promoted_lanes` = `["w20_4_epsilon_second_stage"]`。

*Week 20 交付包 · 生成脚本 `probes/export_week20_results.py` · 全部 lane 独立预注册 · 本周 1 次主记分牌尝试（W20-4，累计 12）· 冻结基线 0.4091179943351143 与冻结头条 0.4766400383507876 未动*
"""


def _utc_now() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    result = export_results(output_root=args.output_root, overwrite=args.overwrite)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    missing = [str(item) for item in result.get("lanes_missing", [])]
    if missing:
        print("lanes_missing: " + ", ".join(missing))
    return 0 if result["verification_passed"] and not missing else 1


if __name__ == "__main__":
    raise SystemExit(main())
