from __future__ import annotations

import json
import re
import urllib.error
from pathlib import Path

import pytest

from probes.g1plus_materials_project_probe import (
    TARGETS,
    load_api_key,
    probe_formula,
    query_formula,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

EVIDENCE_FILES = (
    "probes/g1plus_materials_project_evidence.json",
    "probes/g1plus_pubchem_evidence.json",
    "probes/g1plus_nist_webbook_evidence.json",
)

# The Materials Project token is a bare 32-character alphanumeric run. Used only
# to prove no token leaked into a committed artefact; the key itself is never
# written into the repository.
KEY_SHAPE = re.compile(r"[A-Za-z0-9]{32}")


def _evidence(name: str) -> dict:
    return json.loads((REPOSITORY_ROOT / name).read_text(encoding="utf-8"))


def test_api_key_file_is_read_when_present(tmp_path: Path) -> None:
    key_file = tmp_path / "materials_project_key.txt"
    key_file.write_text(
        "Your Materials Project API key\n0123456789abcdefghijklmnopqrstuv\n",
        encoding="utf-8",
    )

    assert load_api_key(key_file) == "0123456789abcdefghijklmnopqrstuv"


def test_api_key_loader_fails_loudly_when_absent(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_api_key(tmp_path / "missing.txt")


def test_api_key_loader_rejects_a_file_without_a_token(tmp_path: Path) -> None:
    key_file = tmp_path / "materials_project_key.txt"
    key_file.write_text("no key here\n", encoding="utf-8")

    with pytest.raises(ValueError):
        load_api_key(key_file)


def test_committed_evidence_shows_the_control_is_populated() -> None:
    payload = _evidence("probes/g1plus_materials_project_evidence.json")
    summary = payload["summary"]

    assert summary["control_status"] == "ok"
    assert summary["control_has_entries"] is True
    assert summary["targets_with_entries"] == []
    assert summary["target_count"] == len(TARGETS)
    assert len(summary["targets_confirmed_empty"]) == len(TARGETS)
    # Nothing may be filed as an "absence" unless it was a successful query.
    assert summary["targets_inconclusive"] == []

    control = payload["records"][0]
    assert control["group"] == "control"
    assert control["with_dielectric_field"], "the control must expose a dielectric field"
    for record in payload["records"][1:]:
        assert record["group"] == "target"
        assert record["total_doc"] == 0


def test_transient_http_error_is_never_summarised_as_an_absence(tmp_path: Path, monkeypatch) -> None:
    def boom(*args, **kwargs):
        raise urllib.error.HTTPError("https://example.invalid", 429, "rate limited", {}, None)

    monkeypatch.setattr("urllib.request.urlopen", boom)

    import pytest as _pytest

    with _pytest.raises(RuntimeError, match="transient HTTP 429"):
        probe_formula("adiponitrile", "C6H8N2", "key", tmp_path)


def test_non_transient_http_error_is_reported_not_hidden(tmp_path: Path, monkeypatch) -> None:
    def boom(*args, **kwargs):
        raise urllib.error.HTTPError("https://example.invalid", 403, "forbidden", {}, None)

    monkeypatch.setattr("urllib.request.urlopen", boom)

    record = probe_formula("adiponitrile", "C6H8N2", "key", tmp_path)

    assert record["status"] == "http_403"
    assert record["total_doc"] is None


def test_cache_is_only_reused_for_the_same_query(tmp_path: Path) -> None:
    payload = {"meta": {"total_doc": 0}, "data": []}
    # A body cached under one query must not answer a different one.
    cache = tmp_path / "C6H8N2.json"
    cache.write_text(json.dumps(payload), encoding="utf-8")
    marker = tmp_path / "C6H8N2.json.url"
    marker.write_text("https://api.materialsproject.org/materials/summary/?formula=OTHER\n", encoding="utf-8")

    called = {}

    def fake_urlopen(request, timeout=60):
        called["url"] = request.full_url

        class Response:
            def read(self) -> bytes:
                return json.dumps(payload).encode()

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        return Response()

    import urllib.request as _request

    original = _request.urlopen
    _request.urlopen = fake_urlopen
    try:
        query_formula("C6H8N2", "key", tmp_path)
    finally:
        _request.urlopen = original

    assert "formula=C6H8N2" in called["url"]


def test_a_cached_body_with_a_matching_url_costs_no_request(tmp_path: Path) -> None:
    payload = {"meta": {"total_doc": 7}, "data": [{"material_id": "mp-1", "e_total": 4.2}]}
    cache = tmp_path / "C6H8N2.json"
    cache.write_text(json.dumps(payload), encoding="utf-8")

    import urllib.parse as _parse

    from probes.g1plus_materials_project_probe import FIELDS, SUMMARY_ENDPOINT

    url = SUMMARY_ENDPOINT + "?" + _parse.urlencode(
        {"formula": "C6H8N2", "_fields": FIELDS, "_limit": 5}
    )
    (tmp_path / "C6H8N2.json.url").write_text(url + "\n", encoding="utf-8")

    def explode(*args, **kwargs):
        raise AssertionError("the cache should have been used")

    import urllib.request as _request

    original = _request.urlopen
    _request.urlopen = explode
    try:
        returned = query_formula("C6H8N2", "key", tmp_path)
    finally:
        _request.urlopen = original

    assert returned == payload


def _stub_payload(monkeypatch, payload: dict) -> None:
    class Response:
        def read(self) -> bytes:
            return json.dumps(payload).encode()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: Response())


def test_ok_response_without_a_document_count_is_not_an_absence(
    tmp_path: Path, monkeypatch
) -> None:
    # "ok" plus a missing meta block yields total_doc None. That is inconclusive,
    # never a confirmed absence.
    _stub_payload(monkeypatch, {"data": []})

    record = probe_formula("adiponitrile", "C6H8N2", "key", tmp_path, refresh=True)

    assert record["status"] == "ok"
    assert record["total_doc"] is None


def test_missing_meta_block_does_not_become_a_confirmed_absence(
    tmp_path: Path, monkeypatch
) -> None:
    _stub_payload(monkeypatch, {"data": []})

    record = probe_formula("adiponitrile", "C6H8N2", "key", tmp_path, refresh=True)

    confirmed = record["status"] == "ok" and record.get("total_doc") == 0
    assert confirmed is False


def test_summary_keeps_unparsable_document_counts_out_of_the_absence_list(
    tmp_path: Path, monkeypatch
) -> None:
    import probes.g1plus_materials_project_probe as probe_module
    from probes.g1plus_materials_project_probe import CONTROL, run

    key_file = tmp_path / "key.txt"
    key_file.write_text("0123456789abcdefghijklmnopqrstuv\n", encoding="utf-8")

    def fake_probe(name, formula, api_key, cache_dir, *, refresh=False, group="target"):
        total = 322 if group == "control" else None
        return {
            "name": name,
            "formula": formula,
            "group": group,
            "status": "ok",
            "total_doc": total,
        }

    monkeypatch.setattr(probe_module, "probe_formula", fake_probe)
    monkeypatch.setattr(probe_module.time, "sleep", lambda *_: None)

    payload = run(
        key_file=key_file,
        cache_dir=tmp_path / "cache",
        output_path=tmp_path / "out.json",
    )

    assert CONTROL[0] in [r["name"] for r in payload["records"] if r["group"] == "control"]
    assert payload["summary"]["targets_confirmed_empty"] == []
    assert len(payload["summary"]["targets_inconclusive"]) == len(TARGETS)


def test_an_unpopulated_positive_control_aborts_the_run(
    tmp_path: Path, monkeypatch
) -> None:
    import probes.g1plus_materials_project_probe as probe_module
    from probes.g1plus_materials_project_probe import run

    key_file = tmp_path / "key.txt"
    key_file.write_text("0123456789abcdefghijklmnopqrstuv\n", encoding="utf-8")

    def fake_probe(name, formula, api_key, cache_dir, *, refresh=False, group="target"):
        return {"name": name, "formula": formula, "group": group, "status": "ok", "total_doc": 0}

    monkeypatch.setattr(probe_module, "probe_formula", fake_probe)

    with pytest.raises(RuntimeError, match="not populated"):
        run(
            key_file=key_file,
            cache_dir=tmp_path / "cache",
            output_path=tmp_path / "out.json",
        )


def test_committed_evidence_never_contains_the_api_key() -> None:
    # Only the token itself must stay out; naming the HTTP header is fine.
    for name in EVIDENCE_FILES:
        raw = (REPOSITORY_ROOT / name).read_text(encoding="utf-8")
        assert KEY_SHAPE.search(raw) is None, name


def test_every_committed_evidence_file_is_lf_only() -> None:
    # `.gitattributes` normalises *.json to LF, so a CRLF working copy would
    # report a raw sha256 that no clean checkout reproduces.
    for name in EVIDENCE_FILES:
        raw = (REPOSITORY_ROOT / name).read_bytes()
        assert raw.count(b"\r\n") == 0, name
        assert raw.endswith(b"\n"), name
