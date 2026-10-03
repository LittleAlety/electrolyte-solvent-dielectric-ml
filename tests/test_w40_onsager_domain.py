# Guards for the Week 40 lane C: the Onsager domain rule refinement plus the
# dipole double-mu read-out.
#
# W40-C is a post hoc audit lane.  It fits nothing and takes no main-scoreboard shot
# (the cumulative ledger stays at 19).  Its job is to make three claims re-runnable:
#   1. the donor domain is now defined mechanically from structure (H on N/O/F, neutral
#      heteroatom, not an amide N-H) instead of inheriting the RDKit Lipinski donor
#      count -- which is what kept water (eps = 78.87) in the "g close to 1" domain
#      because NumHDonors(H2O) == 0;
#   2. the W38-C anchor ratio 2.5016162961750874 is reproduced bit-for-bit, so the old
#      and new domains are strictly comparable;
#   3. the g_rel verdict is read out against two independent dipole sources (local xTB
#      and the QM9 B3LYP layer from W39) and against the measured ~0.39 D dipole bias.
#      The bias correction is NOT stable at the 10 percent level (H40c10) and water is
#      NOT an extreme donor by this metric (H40c11); both are registered negatives.
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUMMARY = ROOT / 'probes' / 'artifacts' / 'w40_onsager_domain_summary.json'
COMPOUNDS = ROOT / 'probes' / 'artifacts' / 'w40_onsager_domain_compounds.csv'
DOMAIN_CSV = ROOT / 'probes' / 'artifacts' / 'w40_onsager_domain_summary.csv'
FIGURE = ROOT / 'probes' / 'artifacts' / 'w40_onsager_domain.png'
REPORT = ROOT / 'reports' / 'w40_onsager_domain.md'
ROSTER = ROOT / 'data' / 'processed' / 'dielectric_physical_features_v03.csv'
OVERLAP = ROOT / 'probes' / 'artifacts' / 'w39_qm9_overlap.csv'
PROBE = ROOT / 'probes' / 'w40_onsager_domain.py'

ROSTER_SHA256 = 'b36d3439560e4381b7779565b9950eed379832e832b72ea6a3a010662ed24fa3'
OVERLAP_SHA256 = '7bdbfc52ef0cd07360b1a0e8680694605cf9beff86cad65cd589e41de6c3dfc7'

CRITERIA_IDS = ['H40c1', 'H40c2', 'H40c3', 'H40c4', 'H40c5', 'H40c6', 'H40c7',
                'H40c8', 'H40c9', 'H40c10', 'H40c11', 'H40c12', 'H40c13']
REGISTERED_NEGATIVES = ['H40c10', 'H40c11']
FROZEN_READINGS = [0.4091179943351143, 0.4766400383507876, 0.5861142332208197,
                   0.6216672295270079]
W38C_ANCHOR = 2.5016162961750874
W39_SIGNED_DELTA_MEDIAN_D = -0.3914000000000001


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _summary() -> dict:
    return json.loads(SUMMARY.read_text(encoding='utf-8'))


def _rows(path: Path) -> list:
    with path.open('r', encoding='utf-8', newline='') as handle:
        return list(csv.DictReader(handle))


def test_ledger_and_inputs_untouched() -> None:
    payload = _summary()
    assert payload['task'] == 'week40_onsager_domain'
    assert payload['ledger']['main_scoreboard_shots_this_week'] == 0
    assert payload['ledger']['cumulative_main_scoreboard_attempts_after'] == 19
    assert payload['inputs_unchanged'] is True
    assert payload['frozen_readings_untouched'] == FROZEN_READINGS


def test_thirteen_criteria_with_two_registered_negatives() -> None:
    payload = _summary()
    criteria = payload['criteria']
    assert [item['id'] for item in criteria] == CRITERIA_IDS
    verdicts = {item['id']: item['verdict'] for item in criteria}
    assert [key for key, value in verdicts.items() if value != '成立'] == REGISTERED_NEGATIVES
    assert verdicts['H40c10'] == '判否'
    assert verdicts['H40c11'] == '判否'
    assert payload['registered_negatives'] == REGISTERED_NEGATIVES


def test_roster_and_overlap_inputs_are_the_pinned_bytes() -> None:
    assert sha256_file(ROSTER) == ROSTER_SHA256
    assert sha256_file(OVERLAP) == OVERLAP_SHA256


def test_rule_is_mechanical_and_reproduces_the_w38c_anchor() -> None:
    payload = _summary()
    rule = payload['domain_rule']
    assert rule['rule_reads_eps'] is False
    assert rule['amide_smarts'] == '[NX3][CX3]=[OX1]'
    assert 'N / O / F' in rule['new']
    assert 'N/O/F' in rule['new']
    assert '酰胺' in rule['new']
    assert rule['agreement_with_rdkit_hbd'] == 1.0
    assert rule['n_paired_with_rdkit_hbd'] == 237
    ratio = payload['ratio']
    assert ratio['old_rule'] == W38C_ANCHOR
    assert ratio['w38c_anchor'] == W38C_ANCHOR
    assert ratio['anchor_reproduced'] is True
    assert ratio['new_rule'] == 2.5817133416784355
    assert ratio['new_rule'] >= 1.5


def test_domain_sizes_and_new_rule_readings() -> None:
    payload = _summary()
    new = payload['domains']['new_rule']
    old = payload['domains']['old_rule']
    assert old['A']['n'] == 159 and old['B']['n'] == 68
    assert new['A']['n'] == 160 and new['B']['n'] == 67
    assert new['A']['median_L_over_x'] == 1.873456264075279e-05
    assert new['B']['median_L_over_x'] == 4.8367270320141854e-05
    assert new['A']['r2_through_origin'] == 0.2556588879704714
    assert new['B']['median_g_rel'] == 2.5817133416784355
    assert new['A']['median_g_rel'] == 1.0


def test_water_is_the_reclassification_that_matters() -> None:
    payload = _summary()
    water = payload['water']
    assert water['smiles'] == 'O'
    assert water['rdkit_hbd'] == 0
    assert water['hbd_old'] == 0.0
    assert water['donor_h_new'] == 2
    assert water['domain_old'] == 'A'
    assert water['domain_new'] == 'B'
    assert water['g_rel_old_domain'] == 2.2187037404468413
    assert water['g_rel_new_domain'] == 2.2506355383874768
    assert water['g_rel_new_domain'] == 2.2506355383874768
    assert water['domain_reference_median_L_over_x_new'] == 1.873456264075279e-05


def test_reclassification_census_and_rule_boundaries() -> None:
    payload = _summary()['reclassification']
    assert payload['n_changed'] == 3
    assert {item['name'] for item in payload['changed']} == {'water', '1-Butanethiol', '1-Pentanethiol'}
    assert [item['change_dir'] for item in payload['changed']].count('A->B') == 1
    assert [item['change_dir'] for item in payload['changed']].count('B->A') == 2
    assert payload['thiol_names_removed_from_donor_domain'] == ['1-Butanethiol', '1-Pentanethiol']
    assert payload['positive_heteroatom_h_compounds'] == ['ethanolammonium nitrate']
    assert payload['amide_nh_compounds_on_roster_spellings'] == 0
    assert payload['include_amide_nh_flips'] == 0
    assert payload['tautomer_canonical_flips'] == ['N-methylacetamide', 'formamide']


def test_tautomer_normalisation_keeps_the_sign_of_the_conclusion() -> None:
    ratio = _summary()['ratio']
    assert ratio['new_rule_canonical_tautomer'] == 2.472578733643757
    assert ratio['new_rule_canonical_tautomer'] >= 1.5
    assert ratio['new_rule_include_amide_nh'] == ratio['new_rule']


def test_high_eps_family_shows_the_old_rule_overestimated_the_split() -> None:
    family = _summary()['high_eps_family']
    variants = family['variants']
    assert family['threshold'] == 60.0
    assert family['n'] == 8
    assert variants['old']['ratio'] == 15.650359815921144
    assert variants['new']['ratio'] == 13.404447543209601
    assert variants['new']['ratio'] >= 2.0
    assert variants['new']['ratio'] < variants['old']['ratio']
    assert variants['old']['n_donor'] == 4 and variants['old']['n_acceptor'] == 4
    assert variants['new']['n_donor'] == 5 and variants['new']['n_acceptor'] == 3
    water = [item for item in family['members'] if item['name'] == 'water']
    assert len(water) == 1
    assert water[0]['domain_old'] == 'A' and water[0]['domain_new'] == 'B'
    assert water[0]['donor_h_new'] == 2


def test_double_mu_readings_are_rank_consistent() -> None:
    payload = _summary()['double_mu']
    assert payload['n_hits'] == 103
    assert payload['n_both_ge_1D'] == 76
    assert payload['our_mu']['ratio'] == 2.8917368760859308
    assert payload['qm9_mu']['ratio'] == 2.8856771361763895
    assert payload['our_mu']['ratio'] >= 1.5
    assert payload['qm9_mu']['ratio'] >= 1.5
    assert payload['spearman_g_rel'] == 0.8006835269993164
    assert payload['spearman_g_rel'] >= 0.6
    tolerance = abs(payload['our_mu']['ratio'] - payload['qm9_mu']['ratio']) / payload['our_mu']['ratio']
    assert tolerance <= 0.05
    assert payload['median_g_rel_ratio_qm9_over_our'] == 1.483861178304416
    assert payload['median_abs_rank_shift'] == 5.5


def test_dipole_bias_is_the_w39_value_and_is_not_stable_at_ten_percent() -> None:
    bias = _summary()['dipole_bias']
    assert bias['signed_delta_median_D'] == W39_SIGNED_DELTA_MEDIAN_D
    assert bias['expected_signed_delta_median_D'] == W39_SIGNED_DELTA_MEDIAN_D
    assert bias['n_agreeing'] == 90
    assert bias['n_dropped_mu_nonpositive'] == 16
    assert bias['corrected_ratio'] == 3.1132529110752816
    assert bias['corrected_ratio'] >= 1.5
    assert bias['relative_change'] == 0.20588636267854554
    assert bias['relative_change'] > 0.10


def test_compounds_csv_covers_the_whole_roster() -> None:
    rows = _rows(COMPOUNDS)
    assert len(rows) == 241
    assert sum(1 for row in rows if row['usable'] == 'True') == 227
    assert sum(1 for row in rows if row['changed'] == 'True') == 3
    header = set(rows[0].keys())
    for field in ('inchikey', 'name', 'smiles', 'hbd_old', 'rdkit_hbd', 'donor_h_new',
                  'domain_old', 'domain_new', 'dipole_D', 'dipole_D_qm9', 'in_qm9',
                  'mu_corr_D', 'mu_sq_over_Vm', 'L_over_x', 'g_rel_new', 'g_rel_old',
                  'L_over_x_corr', 'g_rel_corr', 'tautomer_flip', 'canonical_donor_h'):
        assert field in header
    water = [row for row in rows if row['name'] == 'water']
    assert len(water) == 1
    assert water[0]['donor_h_new'] == '2'
    assert water[0]['domain_old'] == 'A' and water[0]['domain_new'] == 'B'
    assert water[0]['rdkit_hbd'] == '0'
    assert 103 == sum(1 for row in rows if row['in_qm9'] == 'True')


def test_domain_csv_reports_both_mu_sources_and_both_rules() -> None:
    rows = _rows(DOMAIN_CSV)
    keys = {(row['rule'], row['mu_source'], row['scope'], row['domain']) for row in rows}
    assert ('old_hbd', 'xtb_dipole_D', 'roster', 'A') in keys
    assert ('new_donor', 'xtb_dipole_D', 'roster', 'B') in keys
    assert ('new_donor', 'qm9_dipole_D', 'qm9_subset_mu_ge_1D', 'B') in keys
    assert ('new_donor', 'xtb_dipole_D_bias_corrected', 'roster', 'B') in keys
    assert ('new_donor', 'xtb_dipole_D', 'roster_canonical_tautomer', 'B') in keys
    qm9 = [row for row in rows
           if row['mu_source'] == 'qm9_dipole_D' and row['scope'] == 'qm9_subset_mu_ge_1D']
    assert len(qm9) == 2
    assert all(abs(float(row['ratio_donor_over_acceptor']) - 2.8856771361763895) < 1e-12 for row in qm9)


def test_probe_writes_its_summary_with_the_stable_writer() -> None:
    """AF-12 family: a replay must not dirty the tracked summary via its timestamps."""

    source = PROBE.read_text(encoding='utf-8')
    assert 'write_json_stable(SUMMARY_PATH, summary)' in source
    assert 'SUMMARY_PATH.write_text' not in source


def test_figure_and_report_exist() -> None:
    assert FIGURE.is_file() and FIGURE.stat().st_size > 0
    assert REPORT.is_file()
    text = REPORT.read_text(encoding='utf-8')
    assert 'W40-C' in text
    assert 'H40c10' in text and 'H40c11' in text
    assert '判否' in text
    assert 'water' in text
    assert '2.2506' in text
    assert 'NumHDonors(H2O)' in text
    assert '103' in text and '76' in text
