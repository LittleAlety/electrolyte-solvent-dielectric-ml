"""Probe the live NIST/TRC ThermoML API for new compound coverage.

The local ThermoML cache for this project is a dead end in two different ways, and this
probe is what closes the question rather than repeating it.

First, the cached bulk archive (data/raw/thermoml_archive/ThermoML.v2020-09-30.tgz) is
corrupt. It is not a gzip member at all: its first and last bytes are zero, and all but a
single 8 MiB block of its 189 MB is zero fill. That signature is a preallocated or
interrupted download, and no amount of re-reading recovers it.

Second, the bulk archive cannot simply be re-fetched. The trc.nist.gov/ThermoML site no
longer serves a static directory; it is a JavaScript application backed by a JSON search
API at /ThermoML-API/objects. So "refresh the archive" has to mean "query the API", and
the honest question becomes: query it for what, at what byte cost, and for how many new
compounds?

The headline the probe produces is deliberately the *tight* one. A compound only counts if
the online record carries a pure-component, liquid-phase, zero-frequency permittivity --
the same gate the local extraction uses -- and only if its InChIKey is absent from the
local roster. A looser "appears somewhere in a dielectric record" count is reported
alongside it so the two can never be confused.

Nothing here promotes data into the frozen dataset. The probe only measures.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import inspect
import json
import re
import sys
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from electrolyte_ml.thermoml import (
    _dielectric_kind,
    _is_dielectric_property,
)

ARCHIVE_DIR = REPOSITORY_ROOT / "data" / "raw" / "thermoml_archive"
ARCHIVE_PATH = ARCHIVE_DIR / "ThermoML.v2020-09-30.tgz"
API_BASE = "https://trc.nist.gov/ThermoML-API/objects"
SITE_BASE = "https://trc.nist.gov/ThermoML/"
API_OBJECT_PREFIX = "20.5000.trc.thermoml/"
LEGACY_ARCHIVE_URLS: tuple[str, ...] = (
    "https://trc.nist.gov/ThermoML/ThermoML.v2021-03-31.tgz",
    "https://trc.nist.gov/ThermoML/ThermoML.bib",
    "https://trc.nist.gov/ThermoML/ThermoML_Data.xml",
)
# The two bare single words. They are logged for the record only: the search engine behaves
# like a phrase index, so a bare word under-returns badly (dielectric finds 93 records while
# dielectric constant finds 1,850). They must never drive the headline.
API_QUERIES: tuple[str, ...] = ("permittivity", "dielectric")
# The surgical queries: exact quoted property names. Small, precise, and aimed straight at
# the structured ThermoML property field.
API_PHRASE_QUERIES: tuple[str, ...] = (
    '"Relative permittivity at zero frequency"',
    '"Relative permittivity at various frequencies"',
    '"Relative permittivity"',
)
# Matches every record, so the whole-corpus denominator costs about 6 KB with pageSize=1.
TOTAL_RECORDS_QUERY = "*"
DEFAULT_SUMMARY = REPOSITORY_ROOT / "probes" / "thermoml_online_topup_summary.json"
USER_AGENT = "electrolyte-ml/0.0.0 (+https://trc.nist.gov/ThermoML/)"
HTTP_TIMEOUT_SECONDS = 60
GZIP_MAGIC = b"\x1f\x8b"
TAR_MAGIC_OFFSET = 257
TAR_MAGIC = b"ustar"
MIN_ARCHIVE_BYTES = 512
DOWNLOAD_BUDGET_LIMIT = 40
KNOWN_KEY_SOURCES: tuple[Path, ...] = (
    REPOSITORY_ROOT / "data" / "dielectric_v03.csv",
    REPOSITORY_ROOT / "data" / "processed" / "dielectric_raw.csv",
)
KNOWN_KEY_COLUMNS = ("inchikey", "primary_inchi_key")
MANIFEST_SIZE_KEYS = ("expected_size", "expected_bytes", "size", "content_length", "total_bytes")

INCHIKEY_PATTERN = re.compile(r"^[A-Z]{14}-[A-Z]{10}-[A-Z]$")
PERMITTIVITY_WORDING = re.compile(r"ermittivity|ielectric", re.IGNORECASE)
INCHIKEY_FIELDS = ("sStandardInChIKey", "sInChIKey")


class BudgetExhausted(RuntimeError):
    """Raised when the probe tries to spend more requests than its budget allows."""


class ThermoMLSearchError(RuntimeError):
    """Raised when the search API answers with a non-200 status or a non-JSON body."""


# --------------------------------------------------------------------------------------
# Local archive diagnosis
# --------------------------------------------------------------------------------------


def sha256_file(path: Path, chunk_size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def zone_scan(data: bytes) -> dict[str, Any]:
    """Locate the zero and non-zero regions of an in-memory buffer."""

    size = len(data)
    nonzero = 0
    first: int | None = None
    last: int | None = None
    for index, byte in enumerate(data):
        if byte:
            nonzero += 1
            if first is None:
                first = index
            last = index
    return {
        "size": size,
        "zero_bytes": size - nonzero,
        "nonzero_bytes": nonzero,
        "first_nonzero_offset": first,
        "last_nonzero_offset": last,
        "zero_filled": size > 0 and nonzero == 0,
        "zero_fraction": (size - nonzero) / size if size else 0.0,
    }


def scan_file_zones(
    path: Path, chunk_size: int = 1 << 20, max_bytes: int | None = None
) -> dict[str, Any]:
    """Stream the zone scan over a file so a 189 MB payload never lands in memory."""

    size = path.stat().st_size
    limit = size if max_bytes is None else min(size, max_bytes)
    nonzero = 0
    first: int | None = None
    last: int | None = None
    consumed = 0
    with path.open("rb") as handle:
        while consumed < limit:
            chunk = handle.read(min(chunk_size, limit - consumed))
            if not chunk:
                break
            for index, byte in enumerate(chunk):
                if byte:
                    nonzero += 1
                    if first is None:
                        first = consumed + index
                    last = consumed + index
            consumed += len(chunk)
    return {
        "size": consumed,
        "zero_bytes": consumed - nonzero,
        "nonzero_bytes": nonzero,
        "first_nonzero_offset": first,
        "last_nonzero_offset": last,
        "zero_filled": consumed > 0 and nonzero == 0,
        "zero_fraction": (consumed - nonzero) / consumed if consumed else 0.0,
    }


def classify_archive_payload(first_bytes: bytes, size: int) -> dict[str, Any]:
    """Decide whether a payload is a usable archive.

    The ordering matters: magic bytes win outright, and a zero-prefixed payload is reported
    as corrupt rather than waved through. A non-gzip payload is never an ok verdict.
    """

    gzip_magic = first_bytes[:2] == GZIP_MAGIC
    tar_magic = first_bytes[TAR_MAGIC_OFFSET : TAR_MAGIC_OFFSET + len(TAR_MAGIC)] == TAR_MAGIC
    zero_prefixed = bool(first_bytes) and not any(first_bytes)
    if size == 0:
        verdict = "empty"
    elif gzip_magic:
        verdict = "ok_gzip"
    elif tar_magic:
        verdict = "ok_tar"
    elif size < MIN_ARCHIVE_BYTES:
        verdict = "too_small"
    elif zero_prefixed:
        verdict = "zero_filled"
    else:
        verdict = "not_an_archive"
    return {
        "gzip_magic": gzip_magic,
        "tar_magic": tar_magic,
        "zero_prefixed": zero_prefixed,
        "verdict": verdict,
    }


def is_salvageable(verdict: str) -> bool:
    return verdict in {"ok_gzip", "ok_tar"}


def expected_size_from_manifest(archive_path: Path) -> int | None:
    """Read a promised download size from any sidecar manifest, if one exists."""

    directory = archive_path.parent
    if not directory.is_dir():
        return None
    stem = archive_path.name[: -len(archive_path.suffix)] if archive_path.suffix else archive_path.name
    candidates = [
        archive_path.with_name(archive_path.name + ".meta.json"),
        archive_path.with_name(stem + ".meta.json"),
        archive_path.with_suffix(".meta.json"),
        archive_path.with_suffix(".json"),
        directory / "download.json",
    ]
    candidates.extend(sorted(directory.glob("*.meta.json")))
    for candidate in candidates:
        try:
            if not candidate.is_file():
                continue
            payload = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(payload, Mapping):
            continue
        for key in MANIFEST_SIZE_KEYS:
            value = payload.get(key)
            if isinstance(value, bool):
                continue
            if isinstance(value, int):
                return value
            if isinstance(value, str) and value.strip().isdigit():
                return int(value.strip())
    return None


def _read_head(path: Path, count: int) -> bytes:
    with path.open("rb") as handle:
        return handle.read(count)


def _read_tail(path: Path, count: int) -> bytes:
    size = path.stat().st_size
    with path.open("rb") as handle:
        handle.seek(max(0, size - count))
        return handle.read(count)


def _empty_zones() -> dict[str, Any]:
    return zone_scan(b"")


def diagnose_local_archive(path: Path, *, head_bytes: int = 32) -> dict[str, Any]:
    """Full, honest verdict on the cached archive."""

    if not path.is_file():
        return {
            "path": str(path),
            "exists": False,
            "size": 0,
            "sha256": "",
            "head_hex": "",
            "tail_hex": "",
            "zones": _empty_zones(),
            "classification": classify_archive_payload(b"", 0),
            "manifest_expected_size": None,
            "salvageable": False,
            "diagnosis": f"archive not found at {path}",
        }
    size = path.stat().st_size
    head = _read_head(path, head_bytes)
    tail = _read_tail(path, head_bytes)
    zones = scan_file_zones(path)
    classification = classify_archive_payload(head, size)
    salvageable = is_salvageable(classification["verdict"])
    manifest_expected_size = expected_size_from_manifest(path)
    if salvageable:
        diagnosis = f"{classification['verdict']} archive of {size} bytes; readable"
    elif classification["verdict"] == "zero_filled":
        diagnosis = (
            f"corrupt: {size} bytes with an all-zero header and only "
            f"{zones['nonzero_bytes']} non-zero bytes, so this is a zero-filled or "
            "interrupted download, not a gzip stream"
        )
    else:
        diagnosis = f"corrupt: header is not a gzip or tar member ({classification['verdict']})"
    return {
        "path": str(path),
        "exists": True,
        "size": size,
        "sha256": sha256_file(path),
        "head_hex": head.hex(),
        "tail_hex": tail.hex(),
        "zones": zones,
        "classification": classification,
        "manifest_expected_size": manifest_expected_size,
        "salvageable": salvageable,
        "diagnosis": diagnosis,
    }


# --------------------------------------------------------------------------------------
# Injectable HTTP layer
# --------------------------------------------------------------------------------------


@dataclass
class HttpResponse:
    status_code: int
    headers: Mapping[str, str]
    body: bytes

    @property
    def text(self) -> str:
        return self.body.decode("utf-8", errors="replace")

    def json(self) -> Any:
        return json.loads(self.body.decode("utf-8"))


HttpGet = Callable[..., HttpResponse]


def default_http_get(
    url: str,
    params: Mapping[str, Any] | None = None,
    *,
    method: str = "GET",
    headers: Mapping[str, str] | None = None,
    timeout: int = HTTP_TIMEOUT_SECONDS,
) -> HttpResponse:
    """Real transport. A transport failure becomes a status-0 response, not an exception."""

    import requests

    merged_headers = {"User-Agent": USER_AGENT, **dict(headers or {})}
    try:
        response = requests.request(
            method,
            url,
            params=dict(params) if params else None,
            headers=merged_headers,
            timeout=timeout,
        )
    except requests.RequestException:
        return HttpResponse(0, {}, b"")
    return HttpResponse(response.status_code, dict(response.headers), response.content)


class RequestBudget:
    """A hard ceiling on how many requests the probe may make."""

    def __init__(self, limit: int = DOWNLOAD_BUDGET_LIMIT) -> None:
        self.limit = limit
        self.used = 0
        self.bytes_transferred = 0

    def spend(self) -> None:
        if self.used >= self.limit:
            raise BudgetExhausted(f"request budget of {self.limit} is exhausted")
        self.used += 1

    def record(self, status_code: int, n_bytes: int = 0) -> None:
        del status_code
        self.bytes_transferred += n_bytes

    def remaining(self) -> int:
        return max(0, self.limit - self.used)


def log_entry(url: str, method: str, response: HttpResponse) -> dict[str, Any]:
    return {
        "url": url,
        "method": method,
        "status": response.status_code,
        "bytes": len(response.body),
        "ok": 200 <= response.status_code < 400,
    }


def _http_get_supports_method(http_get: HttpGet) -> bool:
    """Fakes are often declared as (url, params); do not force the kwarg on them."""

    try:
        signature = inspect.signature(http_get)
    except (TypeError, ValueError):
        return True
    for parameter in signature.parameters.values():
        if parameter.kind is inspect.Parameter.VAR_KEYWORD:
            return True
        if parameter.name == "method":
            return True
    return False


def request(
    http_get: HttpGet,
    url: str,
    *,
    budget: RequestBudget,
    method: str = "GET",
    params: Mapping[str, Any] | None = None,
) -> tuple[HttpResponse, dict[str, Any]]:
    budget.spend()
    if _http_get_supports_method(http_get):
        response = http_get(url, params, method=method)
    else:
        response = http_get(url, params)
    budget.record(response.status_code, len(response.body))
    return response, log_entry(url, method, response)


def discover_endpoints(http_get: HttpGet, budget: RequestBudget) -> list[dict[str, Any]]:
    """Cheaply establish which endpoints still exist today."""

    entries: list[dict[str, Any]] = []
    for url in (SITE_BASE, *LEGACY_ARCHIVE_URLS):
        _, entry = request(http_get, url, budget=budget, method="HEAD")
        entries.append(entry)
    _, entry = request(
        http_get,
        API_BASE,
        budget=budget,
        method="HEAD",
        params={"query": TOTAL_RECORDS_QUERY, "pageSize": 1, "pageNum": 0},
    )
    entry["kind"] = "total"
    entries.append(entry)
    return entries


# --------------------------------------------------------------------------------------
# Search + record parsing
# --------------------------------------------------------------------------------------


def api_search(
    http_get: HttpGet,
    query: str,
    *,
    budget: RequestBudget,
    page_size: int | None = None,
    page_num: int = 0,
) -> tuple[dict[str, Any], dict[str, Any]]:
    params: dict[str, Any] = {"query": query}
    if page_size is not None:
        params["pageSize"] = page_size
        params["pageNum"] = page_num
    response, entry = request(http_get, API_BASE, budget=budget, params=params)
    entry["query"] = query
    if response.status_code != 200:
        raise ThermoMLSearchError(f"query {query!r} returned HTTP {response.status_code}")
    try:
        payload = response.json()
    except ValueError as exc:
        raise ThermoMLSearchError(f"query {query!r} returned a non-JSON body: {exc}") from exc
    if not isinstance(payload, Mapping):
        raise ThermoMLSearchError(f"query {query!r} returned {type(payload).__name__}")
    entry["size"] = payload.get("size")
    entry["records_returned"] = len(payload.get("results") or [])
    return dict(payload), entry


def iter_records(payload: Mapping[str, Any]) -> Iterator[dict[str, Any]]:
    results = payload.get("results")
    if not isinstance(results, Sequence) or isinstance(results, (str, bytes)):
        return
    for record in results:
        if not isinstance(record, Mapping):
            continue
        object_id = record.get("id")
        content = record.get("content")
        if not isinstance(object_id, str) or not object_id:
            continue
        if not isinstance(content, Mapping):
            continue
        doi = object_id.removeprefix(API_OBJECT_PREFIX)
        yield {"object_id": object_id, "doi": doi, "content": content}


def record_dois(payload: Mapping[str, Any]) -> list[str]:
    return [record["doi"] for record in iter_records(payload)]


def _as_sequences(value: Any) -> list[Mapping[str, Any]]:
    """ThermoML repeats a single element as a dict; normalise both shapes to a list."""

    if isinstance(value, Mapping):
        return [value]
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return [item for item in value if isinstance(item, Mapping)]
    return []


def _compound_entries(content: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return _as_sequences(content.get("Compound"))


def _pure_or_mixture_blocks(content: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return _as_sequences(content.get("PureOrMixtureData"))


def _first_inchikey(entry: Mapping[str, Any]) -> str:
    for field in INCHIKEY_FIELDS:
        value = entry.get(field)
        if isinstance(value, str) and value.strip():
            return value.strip().upper()
    return ""


def extract_inchikeys(content: Mapping[str, Any]) -> set[str]:
    keys: set[str] = set()
    for compound in _compound_entries(content):
        key = _first_inchikey(compound)
        if key:
            keys.add(key)
    return keys


def is_inchikey(value: str) -> bool:
    return bool(value) and bool(INCHIKEY_PATTERN.match(value))


def _property_group(property_entry: Mapping[str, Any]) -> Mapping[str, Any]:
    method_id = property_entry.get("Property-MethodID")
    if not isinstance(method_id, Mapping):
        return {}
    group = method_id.get("PropertyGroup")
    if not isinstance(group, Mapping):
        return {}
    for name, value in group.items():
        if name == "tml_elements":
            continue
        if isinstance(value, Mapping):
            return value
    return {}


def property_names(content: Mapping[str, Any]) -> list[str]:
    names: list[str] = []
    for block in _pure_or_mixture_blocks(content):
        for property_entry in _as_sequences(block.get("Property")):
            name = _property_group(property_entry).get("ePropName")
            if isinstance(name, str) and name:
                names.append(name)
    return names


def mentions_permittivity(content: Mapping[str, Any]) -> bool:
    for name in property_names(content):
        if _is_dielectric_property(name):
            return True
    try:
        serialized = json.dumps(content, default=str)
    except (TypeError, ValueError):
        return False
    return bool(PERMITTIVITY_WORDING.search(serialized))


def classify_online_property(name: str, frequency_value: str = "") -> str:
    return _dielectric_kind(name, frequency_value)


def _frequency_value(block: Mapping[str, Any]) -> str:
    for constraint in _as_sequences(block.get("Constraint")):
        constraint_id = constraint.get("ConstraintID")
        if not isinstance(constraint_id, Mapping):
            continue
        constraint_type = constraint_id.get("ConstraintType")
        if not isinstance(constraint_type, Mapping):
            continue
        for name, value in constraint_type.items():
            if name == "tml_elements":
                continue
            if "frequency" in str(name).lower() or "frequency" in str(value).lower():
                raw = constraint.get("nConstraintValue")
                return "" if raw is None else str(raw)
    return ""


def _has_liquid_phase(block: Mapping[str, Any]) -> bool:
    for phase in _as_sequences(block.get("PhaseID")):
        if "liquid" in str(phase.get("ePhase", "")).lower():
            return True
    return False


def _compound_name_for(content: Mapping[str, Any], inchikey: str) -> str:
    for compound in _compound_entries(content):
        if _first_inchikey(compound) != inchikey:
            continue
        for field in ("sCommonName", "sSysName"):
            value = compound.get(field)
            if isinstance(value, str) and value:
                return value
    return ""


def _compound_registries(
    content: Mapping[str, Any],
) -> tuple[dict[int, str], list[str]]:
    """Index the record's Compound table two ways so data-set components can be resolved.

    The inline sStandardInChIKey on a data-set Component cannot be trusted. When a record
    holds more than one compound the NIST JSON collapses every Component reference onto the
    FIRST compound's key, so naively reading it silently attributes a 27-compound study to a
    single molecule. The RegNum counter and the /Compound/<n> path are the reliable
    pointers, and they are what the local extraction already follows.
    """

    by_org_num: dict[int, str] = {}
    by_index: list[str] = []
    for index, compound in enumerate(_compound_entries(content)):
        key = _first_inchikey(compound)
        by_index.append(key)
        if not key:
            continue
        reg_num = compound.get("RegNum")
        if isinstance(reg_num, Mapping):
            org = reg_num.get("nOrgNum")
            if isinstance(org, bool):
                continue
            if isinstance(org, int):
                by_org_num[org] = key
            elif isinstance(org, str) and org.strip().isdigit():
                by_org_num[int(org.strip())] = key
    return by_org_num, by_index


def _resolve_component_key(
    component: Mapping[str, Any], by_org_num: Mapping[int, str], by_index: Sequence[str]
) -> str:
    """Resolve one data-set Component to its InChIKey, preferring the pointer over the copy."""

    reg_num = component.get("RegNum")
    if isinstance(reg_num, Mapping):
        org = reg_num.get("nOrgNum")
        number: int | None = None
        if isinstance(org, bool):
            number = None
        elif isinstance(org, int):
            number = org
        elif isinstance(org, str) and org.strip().isdigit():
            number = int(org.strip())
        if number is not None and number in by_org_num:
            return by_org_num[number]
    path = component.get("path")
    if isinstance(path, str) and path.startswith("/Compound/"):
        tail = path[len("/Compound/") :]
        if tail.isdigit() and int(tail) < len(by_index):
            key = by_index[int(tail)]
            if key:
                return key
    return _first_inchikey(component)


def pure_zero_frequency_liquid_epsilon_rows(
    content: Mapping[str, Any], doi: str
) -> list[dict[str, Any]]:
    """The tight gate: pure component, liquid phase, zero-frequency permittivity.

    This mirrors the local extraction gate exactly, because the property decision is
    delegated to _dielectric_kind, so online and local rows share one rule.
    """

    rows: list[dict[str, Any]] = []
    by_org_num, by_index = _compound_registries(content)
    for block in _pure_or_mixture_blocks(content):
        components = _as_sequences(block.get("Component"))
        if len(components) != 1:
            continue
        inchikey = _resolve_component_key(components[0], by_org_num, by_index)
        if not inchikey:
            continue
        if not _has_liquid_phase(block):
            continue
        frequency = _frequency_value(block)
        for property_entry in _as_sequences(block.get("Property")):
            name = _property_group(property_entry).get("ePropName")
            if not isinstance(name, str) or not name:
                continue
            if not _is_dielectric_property(name):
                continue
            if classify_online_property(name, frequency) != "static_or_zero_frequency":
                continue
            rows.append(
                {
                    "inchikey": inchikey,
                    "compound_name": _compound_name_for(content, inchikey),
                    "doi": doi,
                    "property_name": name,
                    "frequency_value": frequency,
                    "phase": "Liquid",
                }
            )
    return rows


# --------------------------------------------------------------------------------------
# Roster comparison
# --------------------------------------------------------------------------------------


def load_known_inchikeys(paths: Sequence[Path] | None = None) -> set[str]:
    sources = KNOWN_KEY_SOURCES if paths is None else tuple(paths)
    keys: set[str] = set()
    for source in sources:
        path = Path(source)
        if not path.is_file():
            continue
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            fieldnames = reader.fieldnames or []
            column = next((name for name in KNOWN_KEY_COLUMNS if name in fieldnames), None)
            if column is None:
                continue
            for row in reader:
                value = (row.get(column) or "").strip().upper()
                if value:
                    keys.add(value)
    return keys


def coverage_delta(online_keys: Iterable[str], known_keys: Iterable[str]) -> dict[str, Any]:
    online = {key for key in online_keys if key}
    known = {key for key in known_keys if key}
    new_keys = sorted(online - known)
    return {
        "online_total": len(online),
        "known_total": len(known),
        "overlap": len(online & known),
        "new_keys": new_keys,
        "new_count": len(new_keys),
    }


# --------------------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------------------


def build_summary(
    *,
    archive_path: Path = ARCHIVE_PATH,
    http_get: HttpGet | None = None,
    budget: RequestBudget | None = None,
    known_key_sources: Sequence[Path] | None = None,
) -> dict[str, Any]:
    getter: HttpGet = http_get if http_get is not None else default_http_get
    request_budget = budget if budget is not None else RequestBudget()
    failures: list[dict[str, Any]] = []

    local_archive = diagnose_local_archive(archive_path)

    endpoints = discover_endpoints(getter, request_budget)
    for entry in endpoints:
        if not entry["ok"]:
            failures.append(
                {
                    "url": entry["url"],
                    "status": entry["status"],
                    "detail": f"{entry['method']} did not succeed",
                }
            )

    queries: list[dict[str, Any]] = []
    total_records_online: int | None = None
    try:
        payload, entry = api_search(
            getter, TOTAL_RECORDS_QUERY, budget=request_budget, page_size=1
        )
        total_records_online = payload.get("size")
        entry["kind"] = "total"
        queries.append(entry)
    except (ThermoMLSearchError, BudgetExhausted) as exc:
        failures.append({"url": API_BASE, "status": 0, "detail": str(exc)})

    loose_keys: set[str] = set()
    tight_rows: list[dict[str, Any]] = []
    seen_tight: set[str] = set()

    for kind, query_list in (("bare", API_QUERIES), ("phrase", API_PHRASE_QUERIES)):
        for query in query_list:
            try:
                payload, entry = api_search(getter, query, budget=request_budget)
            except (ThermoMLSearchError, BudgetExhausted) as exc:
                failures.append({"url": API_BASE, "status": 0, "detail": f"{query!r}: {exc}"})
                continue
            entry["kind"] = kind
            queries.append(entry)
            for record in iter_records(payload):
                content = record["content"]
                if mentions_permittivity(content):
                    loose_keys |= extract_inchikeys(content)
                for row in pure_zero_frequency_liquid_epsilon_rows(content, record["doi"]):
                    if row["inchikey"] in seen_tight:
                        continue
                    seen_tight.add(row["inchikey"])
                    tight_rows.append(row)

    known_keys = load_known_inchikeys(known_key_sources)
    tight_keys = {row["inchikey"] for row in tight_rows}
    tight_delta = coverage_delta(tight_keys, known_keys)
    loose_delta = coverage_delta(loose_keys, known_keys)

    headline_statement = (
        f"{tight_delta['new_count']} new InChIKey(s) with a pure zero-frequency liquid "
        f"permittivity beyond the {tight_delta['known_total']}-key local roster "
        f"(online tight total {tight_delta['online_total']})"
    )

    return {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "probe": "thermoml_online_topup_probe",
        "local_archive": local_archive,
        "online": {
            "api_base": API_BASE,
            "endpoints": endpoints,
            "total_records_online": total_records_online,
            "queries": queries,
            "request_budget": {"limit": request_budget.limit, "used": request_budget.used},
            "bytes_transferred": request_budget.bytes_transferred,
        },
        "coverage": {
            "known_keys": tight_delta["known_total"],
            "tight_online_keys": tight_delta["online_total"],
            "new_keys_with_zero_frequency_epsilon": tight_delta["new_count"],
            "new_keys_list": tight_delta["new_keys"],
            "loose_online_keys": loose_delta["online_total"],
            "loose_new_keys": loose_delta["new_count"],
            "loose_new_keys_list": loose_delta["new_keys"],
            "tight_overlap": tight_delta["overlap"],
            "tight_rows": [
                {
                    "inchikey": row["inchikey"],
                    "compound_name": row["compound_name"],
                    "doi": row["doi"],
                    "property_name": row["property_name"],
                }
                for row in sorted(tight_rows, key=lambda item: item["inchikey"])
            ],
        },
        "headline": {
            "new_inchikeys": tight_delta["new_count"],
            "statement": headline_statement,
        },
        "failures": failures,
    }


def _write_summary(summary: Mapping[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(summary, indent=2, ensure_ascii=False) + "\n"
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def _print_report(summary: Mapping[str, Any]) -> None:
    local = summary["local_archive"]
    online = summary["online"]
    coverage = summary["coverage"]
    print(f"local archive : {local['diagnosis']}")
    print(f"salvageable   : {local['salvageable']}")
    print(f"records online: {online['total_records_online']}")
    for entry in online["queries"]:
        print(
            f"  [{entry.get('kind', '?'):6}] {entry.get('query')!r:52} "
            f"status={entry['status']:>3} size={entry.get('size')!s:>5} bytes={entry['bytes']:>8}"
        )
    print(f"known roster  : {coverage['known_keys']}")
    print(f"tight online  : {coverage['tight_online_keys']}")
    print(f"NEW (tight)   : {coverage['new_keys_with_zero_frequency_epsilon']}")
    for key in coverage["new_keys_list"]:
        print(f"  + {key}")
    print(f"loose online  : {coverage['loose_online_keys']}  NEW={coverage['loose_new_keys']}")
    print(
        f"budget        : {online['request_budget']['used']}/{online['request_budget']['limit']} "
        f"requests, {online['bytes_transferred']} bytes"
    )
    print(f"failures      : {len(summary['failures'])}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Probe the live ThermoML API for new compounds.")
    parser.add_argument("--archive", type=Path, default=ARCHIVE_PATH)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--budget", type=int, default=DOWNLOAD_BUDGET_LIMIT)
    args = parser.parse_args(argv)

    summary = build_summary(
        archive_path=args.archive,
        budget=RequestBudget(limit=args.budget),
    )
    _write_summary(summary, args.summary)
    _print_report(summary)
    print(f"summary written to {args.summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
