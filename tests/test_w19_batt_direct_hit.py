"""Guards for the D2 deliverable: the Batt-P30K direct-hit cross-check.

The frozen numbers are pinned literally, the two containment fields that were born with
mismatched universes are pinned in their repaired form, and the roster the probe reads is
pinned by digest so it cannot drift.  Nothing here refits anything: the landed summary is
read, and the only recomputation is a cheap re-derivation of the anchor count straight from
the committed orbital layer.
"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pytest

from probes import w19_batt_direct_hit as probe

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

ROSTER_SHA256 = "ff2142936e06e04b329b70f8597574f75349e54ce876e9fff81309e6d35ccce4"
BATT_SHA256 = "587f1490613a008b91f45ee9de607a2e057c88c301fa9e5c9d7785b1968d118d"
ALTERNATE_ROSTER = REPOSITORY_ROOT / "probes" / "artifacts" / "v03_features_baseline_input.csv"
REPORT_PATH = REPOSITORY_ROOT / "reports" / "w19_batt_direct_hit.md"

RUNGS_LITERAL = (
    "verbatim_raw_smiles",
    "rdkit_canonical_smiles_isomeric_true",
    "inchikey_full_27_bare_rdkit",
    "inchikey_skeleton_14_bare_rdkit",
    "inchikey_full_27_desalted_uncharged",
    "inchikey_skeleton_14_desalted_uncharged",
)
LADDER_LITERAL = {
    "verbatim_raw_smiles": 77,
    "rdkit_canonical_smiles_isomeric_true": 78,
    "inchikey_full_27_bare_rdkit": 78,
    "inchikey_skeleton_14_bare_rdkit": 78,
    "inchikey_full_27_desalted_uncharged": 78,
    "inchikey_skeleton_14_desalted_uncharged": 78,
}


@pytest.fixture(scope="module")
def summary() -> dict:
    return json.loads(probe.DEFAULT_SUMMARY.read_text(encoding="utf-8"))


def read_rows(path: Path) -> list[dict[str, str]]:
    with open(path, encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def test_the_ladder_and_the_recipe_are_declared_in_the_probe() -> None:
    assert probe.RUNGS == RUNGS_LITERAL
    assert probe.VERBATIM_RUNG == "verbatim_raw_smiles"
    assert probe.PRIMARY_RUNG == "inchikey_full_27_bare_rdkit"
    assert probe.MAX_RUNG == "inchikey_skeleton_14_desalted_uncharged"
    assert set(probe.NORMALIZATION_RECIPE) >= set(RUNGS_LITERAL)
    assert "isomericSmiles=True" in probe.NORMALIZATION_RECIPE["isomeric_smiles"]
    assert "27" in probe.NORMALIZATION_RECIPE["inchikey_full_27_bare_rdkit"]


def test_the_probe_reads_the_named_frozen_inputs() -> None:
    assert probe.DEFAULT_ROSTER.name == "dielectric_v03.csv"
    assert probe.DEFAULT_SUMMARY.name == "w19_batt_direct_hit_summary.json"
    assert probe.EXPECTED_BATT_SHA256 == BATT_SHA256


def test_the_batt_asset_identity_is_pinned(summary: dict) -> None:
    block = summary["batt_h5"]
    assert block["sha256"] == BATT_SHA256
    assert block["sha256_matches_registered"] is True
    assert block["groups_scanned"] == 29519
    assert block["groups_without_smiles"] == 0
    assert block["partial_scan"] is False
    assert summary["batt_molecules"] == 29519


def test_the_frozen_roster_is_untouched_and_carries_246_rows() -> None:
    digest = hashlib.sha256(probe.DEFAULT_ROSTER.read_bytes()).hexdigest()
    assert digest == ROSTER_SHA256
    rows = read_rows(probe.DEFAULT_ROSTER)
    assert len(rows) == 246
    assert len({row["inchikey"] for row in rows}) == 246


def test_the_two_direct_hit_readings_are_pinned(summary: dict) -> None:
    assert summary["roster_rows"] == 246
    assert summary["roster_unique_inchikeys"] == 246
    assert summary["verbatim_hits"] == 77
    assert summary["normalized_hits"] == 78
    assert summary["inclusive_hits_max_rung"] == 78
    assert summary["verbatim_ratio"] == pytest.approx(77 / 246, abs=1e-15)
    assert summary["hit_ratio"] == pytest.approx(78 / 246, abs=1e-15)


def test_the_ladder_is_monotone_and_matches_the_literals(summary: dict) -> None:
    ladder = summary["ladder"]
    assert tuple(ladder["rung_order"]) == RUNGS_LITERAL
    assert ladder["rung_cumulative_hits"] == LADDER_LITERAL
    values = [ladder["rung_cumulative_hits"][name] for name in RUNGS_LITERAL]
    assert values == sorted(values)
    assert ladder["rung_cumulative_hits"][RUNGS_LITERAL[0]] == summary["verbatim_hits"]


def test_normalization_buys_exactly_one_compound(summary: dict) -> None:
    lost = summary["lost_by_verbatim"]
    assert len(lost) == 1
    assert lost[0]["inchikey"] == "HCBRSIIGBBDDCD-UHFFFAOYSA-N"
    assert lost[0]["first_rung"] == "rdkit_canonical_smiles_isomeric_true"
    assert len(summary["misses_still"]) == 168
    assert 77 + len(lost) + len(summary["misses_still"]) == 246


def test_the_anchor_count_is_re_derived_from_the_committed_layer(summary: dict) -> None:
    layer = REPOSITORY_ROOT / "data" / "processed" / "orbital_second_source_layer.csv"
    anchors = {
        row["inchikey"]
        for row in read_rows(layer)
        if row["role"] == "paired_anchor" and row["batt_homo_eV"].strip()
    }
    assert len(anchors) == 111
    assert summary["anchor_containment"]["anchors"] == len(anchors)


def test_the_containment_verdict_is_pinned(summary: dict) -> None:
    block = summary["anchor_containment"]
    assert block["anchors_in_batt_primary_key_set"] == 111
    assert block["anchors_subset_of_batt_primary_key_set"] is True
    assert block["anchors_in_roster"] == 75
    assert block["anchors_in_roster_hit_keys"] == 75
    assert block["anchors_in_verbatim_hit_keys"] == 75
    assert block["anchors_subset_of_roster_hit_keys"] is False
    assert block["roster_hit_keys"] == 78
    assert block["roster_hit_keys_not_in_anchors"] == 3
    assert block["anchors_not_in_roster"] == 36
    assert 75 + 36 == 111


def test_the_repaired_fields_stay_in_one_universe(summary: dict) -> None:
    block = summary["anchor_containment"]
    # 这两格曾经拿 27 位 InChIKey 去比 14 位骨架集、拿命中集去减锚点集，得 0 与 -33。
    assert block["anchors_skeleton_in_max_rung_key_set"] == 111
    assert block["roster_hit_keys_not_in_anchors"] == 3
    assert block["roster_hit_keys_not_in_anchors"] >= 0
    assert "anchors_in_max_rung_key_set" not in block


def test_the_registry_crosscheck_agrees_with_the_batt_keys(summary: dict) -> None:
    block = summary["registry_crosscheck"]
    assert block["registry_orbit_keys"] == 29868
    assert block["registry_orbit_keys_found_in_batt"] == 29519
    assert block["batt_keys_subset_of_registry_orbit"] is True


def test_the_239_row_roster_does_not_reproduce_76(summary: dict) -> None:
    alternate = summary["alternate_roster"]
    assert Path(alternate["path"]).name == "v03_features_baseline_input.csv"
    assert ALTERNATE_ROSTER.name == "v03_features_baseline_input.csv"
    assert alternate["rows"] == 239
    cumulative = alternate["rung_cumulative_hits"]
    assert cumulative["verbatim_raw_smiles"] == 70
    assert cumulative["inchikey_full_27_bare_rdkit"] == 71
    assert cumulative["verbatim_raw_smiles"] != 76


def test_nothing_was_fitted_and_no_restricted_value_entered(summary: dict) -> None:
    assert summary["read_only"] is True
    assert summary["models_fitted"] == 0
    assert summary["reaxys_values_used"] is False
    assert summary["writes_any_pool"] is False
    assert "r2" not in json.dumps(summary["ladder"]).lower()


def test_the_shot_question_is_left_to_the_author(summary: dict) -> None:
    block = summary["shot_accounting_judgement"]
    assert block["author_decision_required"] is True
    assert block["does_not_self_assign_shot_number"] is True
    assert block["basis"]


def test_the_report_carries_the_same_literals() -> None:
    raw = REPORT_PATH.read_bytes()
    assert raw[:3] != b"\xef\xbb\xbf"
    assert b"\r\n" not in raw
    text = raw.decode("utf-8")
    for literal in ("77", "78", "246", "111", "75", "36", "Batt-P30K"):
        assert literal in text
    assert "分母口径分歧" in text
