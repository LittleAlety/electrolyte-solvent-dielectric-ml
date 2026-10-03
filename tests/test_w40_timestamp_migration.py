# Guards for the Week 40 lane B: migrating the timestamped-writer fleet to the
# stable writer.
#
# W40-B is a hygiene lane.  It fits nothing and takes no main-scoreboard shot
# (the cumulative ledger stays at 19).  Its job is to make three claims
# re-runnable:
#   1. every tracked JSON that carries `generated_at_utc` has had its writer
#      moved to `probes/export_results_common.write_json_stable` (95 / 121),
#   2. the rows that could not be migrated are exactly the registered ones --
#      seven hand-authored evidence blobs whose generator is not in the
#      repository, one writer that builds its filename at run time, and 19
#      rows whose writer is registered as an EXEMPT_WRITERS entry with a
#      reason (frozen digest pins / append-mode logs / allow_nan=False),
#   3. re-running three migrated probes twice produces no new dirty path.
from __future__ import annotations

import csv
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUMMARY = ROOT / 'probes' / 'artifacts' / 'w40_timestamp_migration_summary.json'
INVENTORY = ROOT / 'probes' / 'artifacts' / 'w40_timestamp_inventory.csv'
REPORT = ROOT / 'reports' / 'w40_timestamp_migration.md'
PROBE = ROOT / 'probes' / 'w40_timestamp_migration.py'
W38_INVENTORY = ROOT / 'probes' / 'artifacts' / 'w38_timestamp_inventory.csv'

W38_INVENTORY_SHA256 = '6a9ff0c7ebe22a79ce30d6374311efb8103cdf1cd7181f15cbb94584b08d92fa'

CRITERIA_IDS = ['H40b1', 'H40b2', 'H40b3', 'H40b4', 'H40b5', 'H40b6', 'H40b7', 'H40b8',
                'H40b9']
REGISTERED_NEGATIVES: list[str] = []
FROZEN_READINGS = [0.4091179943351143, 0.4766400383507876]

STATUS_MIGRATED = '已迁移稳定写入'
STATUS_PENDING = '待迁移'
STATUS_LEGACY = '无写入器（历史产物）'
STATUS_EXEMPT = '有理由不迁移（例外登记）'

#: 例外登记：这些 owner 的字节被冻结摘要 / 锁前预注册钉死，或它的写入站点不是「整篇改写 JSON」。
#: 迁移它们会让已交付的脚本摘要失效、把追加写降级成覆盖写、或丢掉 allow_nan=False。
EXEMPT_WRITERS = [
    'probes/build_eta_epsilon_joint_table.py',
    'probes/dielectric_association_features_probe.py',
    'probes/dielectric_bagging_probe.py',
    'probes/dielectric_hybrid_shap.py',
    'probes/dielectric_knowledge_purity_sweep.py',
    'probes/dielectric_knowledge_purity_sweep_erratum.py',
    'probes/dielectric_merge_arm_probe.py',
    'probes/dielectric_split_conformal_probe.py',
    'probes/dielectric_target_transform_probe.py',
    'probes/identity_smiles_drawing_decision.py',
    'probes/kpi_funnel_cross_run.py',
    'probes/pubchem_identity_layer.py',
    'probes/pubchem_liquid_window_harvest.py',
    'probes/thermoml_local_coverage_probe.py',
    'probes/thermoml_viscosity_coverage_probe.py',
    'probes/viscosity_row_level_unfreeze.py',
    'probes/w19_chemprop_viscosity.py',
    'probes/w20_safety_ablation.py',
    'probes/w21_li_coordination.py',
    'probes/w24_2_orca_dft.py',
    'probes/w24_condition_redox.py',
    'probes/walden_dn_channel.py',
]
EXEMPT_ROWS = 19
INVENTORY_FIELDS = ['tracked_json', 'has_timestamp', 'writers',
                    'writers_using_stable_helper', 'status']

LEGACY = [
    'probes/g1plus_crawl_round2_evidence.json',
    'probes/g1plus_crawl_round3_evidence.json',
    'probes/g1plus_crawl_round4_evidence.json',
    'probes/g1plus_tier0_evidence.json',
    'probes/jstage_corroboration_evidence.json',
    'probes/w19_safety_channel_registry.json',
    'probes/w19_shots_ledger.json',
]
DYNAMIC = ['probes/dielectric_onsager_delta_w18_placebo_summary.json']
DYNAMIC_WRITER = 'probes/dielectric_onsager_delta_w18.py'

MIGRATED_FILES_UNDER_GUARD = [
    'probes/w36_gate_admission.py',
    'probes/w36_endpoint_rule.py',
    'probes/w36_channel_noise_floor.py',
    'probes/w29_dense_binning.py',
    'probes/homo_lumo_baselines.py',
    'probes/w35_redox_gate_consumers.py',
    'scripts/lookup_primary_dielectric_references.py',
    'probes/w26_dielectric_law.py',
]
VOLATILE_CALL = re.compile(r'(?<![\w_])write_json\s*\(')


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _summary() -> dict:
    return json.loads(SUMMARY.read_text(encoding='utf-8'))


def _rows() -> list:
    with INVENTORY.open('r', encoding='utf-8', newline='') as handle:
        return list(csv.DictReader(handle))


def _w38_rows() -> list:
    with W38_INVENTORY.open('r', encoding='utf-8', newline='') as handle:
        return list(csv.DictReader(handle))


def test_ledger_and_inputs_untouched() -> None:
    payload = _summary()
    assert payload['task'] == 'week40_timestamp_migration'
    assert payload['ledger']['main_scoreboard_shots_this_week'] == 0
    assert payload['ledger']['cumulative_main_scoreboard_attempts_after'] == 19
    assert payload['inputs_unchanged'] is True
    assert payload['frozen_readings_untouched'] == FROZEN_READINGS
    assert payload['helper']['path'] == 'probes/export_results_common.write_json_stable'
    assert payload['helper']['volatile_keys'] == ['generated_at_utc', 'elapsed_seconds']
    assert payload['input_fingerprints']['w38_inventory_sha256'] == W38_INVENTORY_SHA256
    assert sha256_file(W38_INVENTORY) == W38_INVENTORY_SHA256


def test_eight_criteria_all_hold() -> None:
    payload = _summary()
    criteria = payload['criteria']
    assert [item['id'] for item in criteria] == CRITERIA_IDS
    verdicts = {item['id']: item['verdict'] for item in criteria}
    assert [key for key, value in verdicts.items() if value != '成立'] == REGISTERED_NEGATIVES
    assert payload['registered_negatives'] == REGISTERED_NEGATIVES


def test_inventory_matches_the_w38_schema_and_counts() -> None:
    rows = _rows()
    assert list(rows[0].keys()) == INVENTORY_FIELDS
    assert len(rows) == 121
    assert all(row['has_timestamp'] == 'True' for row in rows)
    counts = _summary()['inventory_counts']
    assert counts['total'] == 121
    assert counts[STATUS_MIGRATED] == 95
    assert counts[STATUS_EXEMPT] == EXEMPT_ROWS
    assert counts[STATUS_PENDING] == 0
    assert counts[STATUS_LEGACY] == 7
    statuses = {row['status'] for row in rows}
    assert statuses == {STATUS_MIGRATED, STATUS_EXEMPT, STATUS_LEGACY}
    assert all(row['writers_using_stable_helper'] for row in rows if row['status'] == STATUS_MIGRATED)


def test_every_w38_pending_row_is_resolved() -> None:
    live = {row['tracked_json']: row['status'] for row in _rows()}
    pending = [row['tracked_json'] for row in _w38_rows() if row['status'] == STATUS_PENDING]
    assert len(pending) == 110
    still_pending = [name for name in pending if live.get(name) == STATUS_PENDING]
    assert still_pending == []
    unresolved = {name: live.get(name) for name in pending if live.get(name) == STATUS_LEGACY}
    assert sorted(unresolved) == sorted(LEGACY)


def test_exempt_writers_are_registered_with_a_reason() -> None:
    """H40b9: the exemption registry must not be a place to hide un-migrated writers."""

    payload = _summary()
    exempt = payload['exempt']
    assert exempt['count'] == EXEMPT_ROWS
    assert sorted(exempt['registry']) == sorted(EXEMPT_WRITERS)
    assert all(reason.strip() for reason in exempt['registry'].values())
    assert sorted(exempt['categories']) == ['append_log', 'pinned_bytes', 'strict_json']
    assert len(exempt['rows']) == EXEMPT_ROWS
    for row in exempt['rows']:
        owners = [owner for owner in row['writers'].split(';') if owner]
        assert owners and set(owners) <= set(EXEMPT_WRITERS), row
        assert row['reasons'].strip(), row
        for owner in owners:
            source = (ROOT / owner).read_text(encoding='utf-8')
            assert 'write_json_stable(' not in source, owner
    assert payload['registered_negatives'] == []


def test_no_named_volatile_writer_remains() -> None:
    payload = _summary()
    assert payload['named_volatile_writers'] == []
    assert payload['criteria'][2]['id'] == 'H40b3'
    assert payload['criteria'][2]['value'] == 0.0


def test_legacy_rows_carry_mechanical_evidence() -> None:
    payload = _summary()
    checks = payload['residual_checks']
    assert sorted(payload['residual']['legacy_without_writer']) == sorted(LEGACY)
    assert checks['legacy_without_writer_clean'] is True
    assert len(checks['legacy_without_writer']) == 7
    for item in checks['legacy_without_writer']:
        assert item['owners'], item['tracked_json']
        assert item['owners_naming_it_in_a_write'] == []
        assert (ROOT / item['tracked_json']).is_file()


def test_dynamic_path_writer_is_registered_and_stable() -> None:
    payload = _summary()
    assert payload['residual']['dynamic_path_migrated'] == DYNAMIC
    checks = payload['residual_checks']['dynamic_path']
    assert len(checks) == 1
    item = checks[0]
    assert item['writer'] == DYNAMIC_WRITER
    assert item['writer_uses_stable_helper'] is True
    assert item['writer_builds_name_at_runtime'] is True
    assert payload['residual_checks']['dynamic_path_clean'] is True
    source = (ROOT / DYNAMIC_WRITER).read_text(encoding='utf-8')
    assert 'with_name(' in source and 'write_json_stable(summary_path, summary)' in source


def test_sampling_two_runs_produce_no_new_dirty_path() -> None:
    sampling = _summary()['sampling']
    assert sampling['runs_per_probe'] == 2
    assert sampling['clean'] is True
    assert len(sampling['results']) == 3
    for item in sampling['results']:
        assert item['timeout'] is False
        assert item['new_dirty_paths'] == [], item['probe']
        assert item['artifact_dirty_after'] is False, item['probe']
        assert [run['exit_code'] for run in item['runs']] == [0, 0], item['probe']
    probes = {item['probe'] for item in sampling['results']}
    assert probes == {'probes/w36_gate_admission.py', 'probes/w36_endpoint_rule.py',
                      'probes/w36_channel_noise_floor.py'}


def test_migrated_writers_use_the_stable_helper() -> None:
    for relative in MIGRATED_FILES_UNDER_GUARD:
        source = (ROOT / relative).read_text(encoding='utf-8')
        assert 'write_json_stable(' in source, relative
        assert 'from export_results_common import write_json_stable' in source, relative
        assert VOLATILE_CALL.search(source) is None, relative


def test_probe_writes_its_summary_with_the_stable_writer() -> None:
    """AF-12 family: a replay must not dirty the tracked summary via its timestamps."""

    source = PROBE.read_text(encoding='utf-8')
    assert 'write_json_stable(SUMMARY_PATH, summary)' in source
    assert 'SUMMARY_PATH.write_text' not in source


def test_report_documents_the_residuals() -> None:
    assert REPORT.is_file()
    text = REPORT.read_text(encoding='utf-8')
    assert 'W40-B' in text
    assert 'H40b3' in text and 'H40b7' in text
    assert '无写入器（历史产物）' in text
    assert '有理由不迁移（例外登记）' in text
    assert 'probes/w19_shots_ledger.json' in text
    assert 'probes/dielectric_onsager_delta_w18.py' in text
    assert '新增脏路径' in text
