# Guards for the Week 42 lane W42-D: the four-layer orbital sampling law and the
# domain-ratio bootstrap/permutation.  The closed form sd(N) = s0*sqrt(1/N - 1/N_pop) is
# fitted on six layer pairs; s0 turns out to be a function of rank fidelity.  The W40-C
# domain ratio is reproduced bit-for-bit and given a paired bootstrap CI and a permutation
# null.  Everything is read-only offline computation.
from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / 'probes' / 'artifacts'
SUMMARY = ART / 'w42_sampling_law_summary.json'
LAW = ART / 'w42_sampling_law.csv'
FITS = ART / 'w42_sampling_fits.csv'
DOMAIN = ART / 'w42_domain_bootstrap.csv'
FIGURE = ART / 'w42_sampling_law.png'
REPORT = ROOT / 'reports' / 'w42_sampling_law.md'
PROBE = ROOT / 'probes' / 'w42_sampling_law.py'
PREREG = ROOT / 'probes' / 'w42_registry_transfer_prereg.json'

CRITERIA_IDS = ['H42d' + str(index) for index in range(1, 12)]
REGISTERED_NEGATIVES: list = []
FROZEN_READINGS = [0.4091179943351143, 0.4766400383507876, 0.5861142332208197,
                   0.6216672295270079]
RMSE_MAX = 0.008403007964252352
FIDELITY_SPEARMAN = 0.942857142857143
S0_XTB_QM9 = 0.41928727987978265
S0_XTB_BATT = 0.6474516704403749
NOISE_FLOOR_XTB_QM9 = 0.11376879232114509
DOMAIN_RATIO = 2.5817133416784355
DOMAIN_CI = (2.1219707314118583, 3.227142039452895)
DOMAIN_SD = 0.30331824925889
DOMAIN_P = 0.0004997501249375312
SEQUENCES = ['xtb-qm9', 'xtb-pubchemqc', 'xtb-batt', 'qm9-pubchemqc', 'qm9-batt',
             'pubchemqc-batt']


def _summary() -> dict:
    return json.loads(SUMMARY.read_text(encoding='utf-8'))


def _rows(path: Path) -> list:
    with path.open('r', encoding='utf-8', newline='') as handle:
        return list(csv.DictReader(handle))


def test_ledger_and_inputs_untouched() -> None:
    payload = _summary()
    assert payload['schema'] == 'w42_sampling_law/summary@1'
    assert payload['ledger']['main_scoreboard_shots_this_week'] == 0
    assert payload['ledger']['cumulative_main_scoreboard_attempts_after'] == 19
    assert payload['inputs_unchanged'] is True
    assert payload['frozen_readings_untouched'] == FROZEN_READINGS


def test_eleven_criteria_all_hold() -> None:
    payload = _summary()
    criteria = payload['criteria']
    assert [item['id'] for item in criteria] == CRITERIA_IDS
    assert [item['verdict'] for item in criteria] == ['成立'] * 11
    assert payload['registered_negatives'] == REGISTERED_NEGATIVES


def test_six_sequences_fit_the_closed_form() -> None:
    payload = _summary()
    fits = {row['sequence']: row for row in payload['sampling_law']['fit_rows']}
    assert sorted(fits) == sorted(SEQUENCES)
    assert abs(payload['sampling_law']['rmse_max'] - RMSE_MAX) < 1e-12
    assert abs(fits['xtb-qm9']['s0'] - S0_XTB_QM9) < 1e-12
    assert abs(fits['xtb-batt']['s0'] - S0_XTB_BATT) < 1e-12
    assert abs(fits['xtb-qm9']['noise_floor_n12'] - NOISE_FLOOR_XTB_QM9) < 1e-12
    assert all(row['rmse'] <= 0.012 for row in fits.values())


def test_s0_tracks_rank_fidelity() -> None:
    payload = _summary()
    assert abs(payload['sampling_law']['fidelity_spearman'] - FIDELITY_SPEARMAN) < 1e-12
    assert payload['sampling_law']['fidelity_spearman'] >= 0.9


def test_law_grid_has_the_registered_sizes() -> None:
    rows = _rows(LAW)
    assert len(rows) == 26
    sizes = sorted({int(row['N']) for row in rows})
    assert sizes == [10, 18, 25, 49, 100]
    assert all(float(row['s0_at_N']) > 0.0 for row in rows)


def test_domain_ratio_reproduces_the_w40_anchor() -> None:
    payload = _summary()
    domain = payload['domain']
    assert abs(domain['ratio'] - DOMAIN_RATIO) < 1e-9
    assert domain['n_a'] == 160 and domain['n_b'] == 67
    assert domain['corrected_inside_ci'] is True


def test_domain_bootstrap_and_permutation_bounds() -> None:
    payload = _summary()
    domain = payload['domain']
    assert abs(domain['ci_lo'] - DOMAIN_CI[0]) < 1e-9
    assert abs(domain['ci_hi'] - DOMAIN_CI[1]) < 1e-9
    assert abs(domain['bootstrap_sd'] - DOMAIN_SD) < 1e-9
    assert abs(domain['permutation_p'] - DOMAIN_P) < 1e-12
    assert domain['permutation_count_ge'] == 0
    assert domain['ci_lo'] > 1.0


def test_artifacts_and_report_exist_and_are_lf_only() -> None:
    for path in (SUMMARY, LAW, FITS, DOMAIN, FIGURE, REPORT, PROBE, PREREG):
        assert path.is_file(), path
    for path in (SUMMARY, LAW, FITS, DOMAIN, REPORT, PROBE, PREREG):
        assert b'\r\n' not in path.read_bytes(), path
    assert FIGURE.stat().st_size > 5000
