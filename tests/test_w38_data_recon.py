# Guards for the Week 38-D lane: the data reconnaissance registry.
#
# W38-D is the only outward-facing lane of Week 38.  Its job is not to model anything
# but to make two claims falsifiable and re-runnable:
#   1. the roster hit counts are measured (RDKit 27-char InChIKey set intersection),
#   2. nothing with an NC / ND / proprietary license is allowed anywhere near the pool.
# The tests below therefore pin the measured counts, the byte-identity of the files that
# are "already in library", and the red-line self-consistency of the channel table.
from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUMMARY = ROOT / 'probes' / 'artifacts' / 'w38_recon_summary.json'
HITS = ROOT / 'probes' / 'artifacts' / 'w38_recon_hits.csv'
CHANNELS = ROOT / 'probes' / 'artifacts' / 'w38_recon_channels.csv'
FIGURE = ROOT / 'probes' / 'artifacts' / 'w38_recon_hits.png'
REPORT = ROOT / 'reports' / 'w38_data_recon.md'

RED_CLASSES = {'NC', 'ND', 'proprietary', 'restricted', 'unknown'}


def _summary() -> dict:
    return json.loads(SUMMARY.read_text(encoding='utf-8'))


def _hits() -> dict:
    with HITS.open('r', encoding='utf-8', newline='') as handle:
        return {row['source_key']: row for row in csv.DictReader(handle)}


def _channels() -> list:
    with CHANNELS.open('r', encoding='utf-8', newline='') as handle:
        return list(csv.DictReader(handle))


def test_ledger_and_inputs_untouched() -> None:
    payload = _summary()
    assert payload['task'] == 'week38_data_recon'
    assert payload['ledger']['main_scoreboard_shots_this_week'] == 0
    assert payload['ledger']['cumulative_main_scoreboard_attempts_after'] == 19
    assert payload['inputs_unchanged'] is True
    assert payload['frozen_readings_untouched'] == [0.4091179943351143, 0.4766400383507876,
                                                    0.5861142332208197, 0.6216672295270079]


def test_all_nine_criteria_pass() -> None:
    verdicts = _summary()['criteria']
    assert [item['id'] for item in verdicts] == ['H38d1', 'H38d2', 'H38d3', 'H38d4',
                                                 'H38d5', 'H38d6', 'H38d7', 'H38d8',
                                                 'H38d9']
    assert all(item['verdict'] == '成立' for item in verdicts)
    assert _summary()['registered_negatives'] == []


def test_roster_denominator_is_locked_at_241() -> None:
    payload = _summary()
    assert payload['roster_total'] == 241
    assert payload['roster_unique_inchikey'] == 241


def test_measured_hit_counts_reproduce_the_recon_report() -> None:
    hits = _hits()
    assert int(hits['batt_p30k']['roster_hits']) == 73
    assert int(hits['batt_slm_smi']['roster_hits']) == 79
    assert int(hits['batt_slm_rx392']['roster_hits']) == 10
    assert int(hits['solvfunc_87']['roster_hits']) == 26
    assert int(hits['chew_viscosity_supp2']['roster_hits']) == 140
    assert int(hits['chew_viscosity_supp3']['roster_hits']) == 24
    assert int(hits['chodera_dielectric']['roster_hits']) == 45
    assert all(int(row['roster_total']) == 241 for row in hits.values())


def test_three_batt_slm_files_are_already_in_library() -> None:
    hits = _hits()
    for key in ('batt_slm_smi', 'batt_slm_rx392', 'solvfunc_87'):
        row = hits[key]
        assert row['pre_existing'] == 'True'
        assert row['byte_identical_upstream'] == 'True'
        assert row['local_sha256'] == row['upstream_sha256']
    for key in ('batt_slm_cpi_features', 'batt_slm_cpi_features_nof'):
        assert hits[key]['pre_existing'] == 'False'
        assert hits[key]['byte_identical_upstream'] == 'True'


def test_nc_source_is_registered_but_cannot_enter_the_pool() -> None:
    hits = _hits()
    chew = hits['chew_viscosity_supp2']
    assert chew['license'] == 'CC BY-NC 4.0'
    assert chew['can_enter_pool'] == 'False'
    # it is still the widest eta source on the roster: the point is the trade-off
    assert int(chew['roster_hits']) == 140


def test_no_non_permissive_channel_may_enter_the_pool() -> None:
    channels = _channels()
    assert channels
    for row in channels:
        if row['can_enter_pool'] == 'True':
            assert row['license_class'] in ('permissive', 'n/a'), row['channel_key']
        if row['license_class'] in RED_CLASSES:
            assert row['can_enter_pool'] == 'False', row['channel_key']


def test_omol25_is_not_an_orbital_source() -> None:
    channels = {row['channel_key']: row for row in _channels()}
    assert channels['colabfit_omol25_train']['holds_orbital'] == 'False'
    permissive_orbital = [row for row in channels.values()
                          if row['holds_orbital'] == 'True'
                          and row['license_class'] == 'permissive']
    assert len(permissive_orbital) >= 2
    assert 'molssiai_pubchemqc_b3lyp' in {row['channel_key'] for row in permissive_orbital}


def test_figure_and_report_exist() -> None:
    assert FIGURE.is_file() and FIGURE.stat().st_size > 0
    assert REPORT.is_file()
    text = REPORT.read_text(encoding='utf-8')
    assert '名册命中实测' in text
    assert '渠道红线登记' in text
