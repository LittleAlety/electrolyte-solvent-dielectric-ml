"""L1 liquid-window harvest: PubChem experimental MP / BP / FP (+ density) per InChIKey.

The execution manual splits sourcing into L0 identity, L1 open harvesting and L2
adjudication, and keeps PubChem in the role of *harvester*, never judge. The L0
probe (``probes/pubchem_identity_layer.py``) already pinned one canonical CID per
InChIKey and verified the InChIKey round trip. This probe takes that identity map
as read-only input and harvests the **liquid window** of every compound -- the
melting point, boiling point and flash point, plus density where it is deposited
-- from the PUG-View ``Experimental Properties`` section, one scoped request per
CID.

What this probe does and does not claim
    PUG-View values are a *compilation*: PubChem copies them from depositor
    databases (HSDB, CAMEO Chemicals, ICSCs, OSHA, ...), each of which cites its
    own upstream reference. Every harvested value therefore carries
    ``source_kind="compilation"`` and ``quality_layer="filter_only"``, the
    depositor (``SourceName``), the cited reference and the measurement condition
    where the depositor stated one. A value from this probe may screen and rank
    compounds inside the funnel; it is **not** a first-hand, citable core value
    and must never be promoted to one without independent adjudication.

Coverage set
    every row of ``data/reference/identity_map.csv`` (314 InChIKeys, each with a
    PubChem CID that L0 resolved by InChIKey round trip). The map is read, never
    written, and its CIDs are reused so this probe never re-resolves identity.

Discipline (mirrors the L0 probe)
    * Offline first. A cached response is served without touching the network;
      the cache stores the URL it came from, so a mis-keyed file can never be
      returned as evidence for a different request.
    * Throttled. PubChem asks automation to stay at or below five requests per
      second without an API key. The default spacing is 0.25 s (4 req/s), an even
      margin below that ceiling; every request is retried with bounded back-off.
    * Honest. A scoped PUG-View 404 is recorded as
      ``no_experimental_properties_section`` -- never as a value and never as a
      fabricated absence. A missing cache while offline is ``unresolved_offline``.
      A value that cannot be parsed keeps its raw text and a note.
    * Idempotent. Re-running the harvest over the same cache produces
      byte-identical rows and spends no second request, which the probe verifies
      in-process and reports as ``run_idempotent``.
    * Cost is logged. ``_harvest_runs.jsonl`` receives one line per run, the
      harvesting run included, so the request cost stays auditable from the log
      alone instead of only from a later cache-only re-run.

Everything this probe writes lives under the git-ignored cache directory, next
to the raw responses that justify it; no ``data/processed`` or ``data/reference``
file is touched.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

PUG_VIEW = "https://pubchem.ncbi.nlm.nih.gov/rest/pug_view/data/compound"
EXPERIMENTAL_HEADING = "Experimental Properties"
USER_AGENT = "electrolyte-ml-research/1.0 (local reproducibility probe)"

DEFAULT_CACHE_DIR = REPOSITORY_ROOT / "data" / "external" / "g1plus" / "pubchem" / "liquid_window"
DEFAULT_VALUES = DEFAULT_CACHE_DIR / "liquid_window_values.csv"
DEFAULT_SELECTED = DEFAULT_CACHE_DIR / "liquid_window_selected.csv"
DEFAULT_SUMMARY = REPOSITORY_ROOT / "probes" / "pubchem_liquid_window_harvest_summary.json"
DEFAULT_HARVEST_LOG = DEFAULT_CACHE_DIR / "_harvest_runs.jsonl"
IDENTITY_MAP_PATH = REPOSITORY_ROOT / "data" / "reference" / "identity_map.csv"

DEFAULT_THROTTLE_SECONDS = 0.25
DEFAULT_ATTEMPTS = 4
CACHE_SUFFIX = ".experimental_properties.json"

SOURCE_KIND = "compilation"
QUALITY_LAYER = "filter_only"
QUALITY_LAYER_NOTE = (
    "PubChem PUG-View values are depositor compilations; they may be used to "
    "screen and rank compounds in the funnel filter layer only, and must not be "
    "treated as first-hand citable core values."
)

PROPERTY_HEADINGS: dict[str, str] = {
    "Melting Point": "melting_point",
    "Boiling Point": "boiling_point",
    "Flash Point": "flash_point",
    "Density": "density",
}
LIQUID_WINDOW_PROPERTIES: tuple[str, ...] = (
    "melting_point",
    "boiling_point",
    "flash_point",
    "density",
)
TEMPERATURE_PROPERTIES: tuple[str, ...] = ("melting_point", "boiling_point", "flash_point")

HARVEST_STATUSES: tuple[str, ...] = (
    "harvested",
    "harvested_without_target_properties",
    "no_experimental_properties_section",
    "request_failed",
    "unresolved_offline",
    "unresolved_empty_response",
)

VALUE_COLUMNS: tuple[str, ...] = (
    "inchikey",
    "name",
    "pubchem_cid",
    "property",
    "section_heading",
    "value_raw",
    "value_numeric",
    "unit",
    "temperature_c",
    "condition_raw",
    "pressure_mmhg",
    "subtype",
    "depositor",
    "reference",
    "reference_number",
    "peer_reviewed",
    "source_kind",
    "quality_layer",
    "source_url",
    "retrieved_at",
    "notes",
)

SELECTED_COLUMNS: tuple[str, ...] = (
    "inchikey",
    "name",
    "pubchem_cid",
    "property",
    "value_raw",
    "value_numeric",
    "unit",
    "temperature_c",
    "depositor",
    "reference",
    "reference_number",
    "peer_reviewed",
    "subtype",
    "n_values_seen",
    "n_parsed_values",
    "selection_rule",
    "source_kind",
    "quality_layer",
    "source_url",
    "retrieved_at",
)

TEMPERATURE_SELECTION_RULE = "peer_reviewed_first_then_lower_median"
DENSITY_SELECTION_RULE = "absolute_then_relative_then_unspecified; peer_reviewed_first; lower_median"
_DENSITY_SUBTYPE_ORDER: dict[str, int] = {"absolute": 0, "relative": 1, "unspecified": 2}


def _heading_url(cid: str) -> str:
    query = urllib.parse.urlencode({"heading": EXPERIMENTAL_HEADING})
    return f"{PUG_VIEW}/{urllib.parse.quote(str(cid), safe='')}/JSON?{query}"


def _utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _normalise_signs(text: str) -> str:
    """Fold the Unicode minus/en-dash variants PUG-View mixes into ASCII."""

    return text.replace("\u2212", "-").replace("\u2013", "-").replace("\u2014", "-")


def _format_number(value: object) -> str:
    if value is None or value == "":
        return ""
    number = round(float(value), 4)
    if number == int(number):
        return str(int(number))
    return str(number)


# --------------------------------------------------------------------------
# HTTP layer.
# --------------------------------------------------------------------------


class OfflineError(RuntimeError):
    """Raised when a network call is attempted while the client is offline."""


@dataclass
class ClientStats:
    network_calls: int = 0
    cache_hits: int = 0
    throttle_seconds: float = 0.0
    retries: int = 0
    throttled_requests: int = 0
    missing_records: int = 0
    cache_entries: int = 0


def build_opener(proxy: str = "none") -> urllib.request.OpenerDirector:
    """An opener that is explicit about proxies.

    ``"none"`` connects directly (the default: the workstation that produced the
    committed run carried a stale ``HTTP(S)_PROXY`` that refused connections),
    ``"env"`` honours the environment, and any other value is used as an
    explicit proxy URL.
    """

    if proxy == "env":
        return urllib.request.build_opener()
    if proxy in ("", "none"):
        return urllib.request.build_opener(urllib.request.ProxyHandler({}))
    return urllib.request.build_opener(
        urllib.request.ProxyHandler({"http": proxy, "https": proxy})
    )


@dataclass
class PubChemClient:
    """Cached, throttled, offline-capable PUG-View reader."""

    cache_dir: Path
    throttle_seconds: float = DEFAULT_THROTTLE_SECONDS
    attempts: int = DEFAULT_ATTEMPTS
    offline: bool = False
    sleep_fn: object = time.sleep
    opener: object = None
    stats: ClientStats = field(default_factory=ClientStats)
    _last_request_at: float | None = None

    def __post_init__(self) -> None:
        if self.opener is None:
            self.opener = build_opener("none")

    def cache_path(self, inchikey: str) -> Path:
        return self.cache_dir / f"{urllib.parse.quote(inchikey, safe='')}{CACHE_SUFFIX}"

    def _read_cache(self, inchikey: str, cid: str) -> dict[str, object] | None:
        path = self.cache_path(inchikey)
        marker = path.with_suffix(path.suffix + ".url")
        if not path.is_file() or not marker.is_file():
            return None
        recorded = marker.read_text(encoding="utf-8").strip()
        if recorded != _heading_url(cid):
            # A cache entry whose URL marker disagrees is not evidence for this
            # compound; treat it as absent rather than trusting the filename.
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return None
        return payload

    def _write_cache(self, inchikey: str, cid: str, payload: Mapping[str, object]) -> None:
        path = self.cache_path(inchikey)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
        path.with_suffix(path.suffix + ".url").write_text(
            _heading_url(cid) + "\n", encoding="utf-8"
        )

    def _throttle(self) -> None:
        if self._last_request_at is None or self.throttle_seconds <= 0:
            return
        elapsed = time.monotonic() - self._last_request_at
        remaining = self.throttle_seconds - elapsed
        if remaining > 0:
            self.stats.throttled_requests += 1
            self.stats.throttle_seconds += remaining
            self.sleep_fn(remaining)  # type: ignore[operator]

    def fetch(self, inchikey: str, cid: str, *, refresh: bool = False) -> dict[str, object]:
        """Return the scoped PUG-View record, or a ``not_found`` marker payload.

        A 404 on the scoped heading request is cached as a ``not_found`` payload
        whose ``resolution_status`` is ``no_experimental_properties_section``:
        the CID itself is guaranteed to exist by the L0 identity layer, so the
        scoped 404 means the section is absent, not that the compound is.
        """

        if not refresh:
            cached = self._read_cache(inchikey, cid)
            if cached is not None:
                self.stats.cache_hits += 1
                return cached
        if self.offline:
            raise OfflineError(f"offline client asked for {inchikey}")

        url = _heading_url(cid)
        last: Exception | None = None
        for attempt in range(self.attempts):
            self._throttle()
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            try:
                with self.opener.open(request, timeout=120) as response:  # type: ignore[attr-defined]
                    body = response.read().decode("utf-8")
            except urllib.error.HTTPError as error:
                self._last_request_at = time.monotonic()
                self.stats.network_calls += 1
                if error.code == 404:
                    payload: dict[str, object] = {
                        "not_found": True,
                        "http_status": 404,
                        "fault_code": _fault_code(error),
                        "resolution_status": "no_experimental_properties_section",
                    }
                    self.stats.missing_records += 1
                    self._write_cache(inchikey, cid, payload)
                    return payload
                if error.code != 429 and error.code < 500:
                    # A malformed request will not become valid by repeating
                    # it, so it is reported instead of retried.
                    raise RuntimeError(
                        f"PubChem PUG-View returned HTTP {error.code} for {url}"
                    ) from error
                last = error
                self.stats.retries += 1
                self.sleep_fn(1.5 * (attempt + 1))  # type: ignore[operator]
                continue
            except urllib.error.URLError as error:
                self._last_request_at = time.monotonic()
                self.stats.network_calls += 1
                last = error
                self.stats.retries += 1
                self.sleep_fn(1.5 * (attempt + 1))  # type: ignore[operator]
                continue
            self._last_request_at = time.monotonic()
            self.stats.network_calls += 1
            payload = json.loads(body)
            self._write_cache(inchikey, cid, payload)
            return payload
        raise RuntimeError(
            f"PubChem PUG-View request failed after {self.attempts} attempts: {url}"
        ) from last


def _fault_code(error: urllib.error.HTTPError) -> str:
    try:
        payload = json.loads(error.read().decode("utf-8"))
    except (OSError, ValueError):  # pragma: no cover - the body is normally valid JSON
        return ""
    fault = payload.get("Fault") if isinstance(payload, Mapping) else None
    if isinstance(fault, Mapping):
        return str(fault.get("Code") or "")
    return ""

# --------------------------------------------------------------------------
# Input table.
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Target:
    inchikey: str
    name: str
    cid: str
    identity_check: str


def load_targets(path: Path = IDENTITY_MAP_PATH) -> list[Target]:
    """Read the L0 identity map; sorted by InChIKey for a deterministic run."""

    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    targets = []
    for row in rows:
        inchikey = (row.get("inchikey") or "").strip()
        cid = (row.get("pubchem_cid") or "").strip()
        if not inchikey or not cid:
            continue
        targets.append(
            Target(
                inchikey=inchikey,
                name=(row.get("name") or "").strip(),
                cid=cid,
                identity_check=(row.get("identity_check") or "").strip(),
            )
        )
    return sorted(targets, key=lambda target: target.inchikey)


# --------------------------------------------------------------------------
# PUG-View parsing.
# --------------------------------------------------------------------------


def iter_sections(sections: object) -> Iterator[Mapping[str, object]]:
    if not isinstance(sections, list):
        return
    for section in sections:
        if not isinstance(section, Mapping):
            continue
        yield section
        yield from iter_sections(section.get("Section"))


def find_property_sections(
    record: Mapping[str, object],
) -> list[tuple[str, str, Mapping[str, object]]]:
    """The (property, heading, section) triples this probe cares about, in order."""

    found: dict[str, tuple[str, str, Mapping[str, object]]] = {}
    for section in iter_sections(record.get("Section")):
        heading = str(section.get("TOCHeading") or "")
        property_name = PROPERTY_HEADINGS.get(heading)
        if property_name and property_name not in found:
            found[property_name] = (property_name, heading, section)
    return [found[name] for name in LIQUID_WINDOW_PROPERTIES if name in found]


def value_text(info: Mapping[str, object]) -> tuple[str, str]:
    """Flatten one PUG-View ``Information`` entry to (text, kind).

    ``kind`` is ``"string"`` for an ordinary value, ``"number"`` for a bare
    structured number (unit unknown, so it is not parsed into a value) and
    ``"inline_table"`` for an embedded table, which is left unparsed on purpose.
    """

    value = info.get("Value")
    if not isinstance(value, Mapping):
        return "", "missing"
    strings = value.get("StringWithMarkup")
    if isinstance(strings, list) and strings and isinstance(strings[0], Mapping):
        return str(strings[0].get("String") or ""), "string"
    numbers = value.get("Number")
    if isinstance(numbers, list) and numbers:
        return "; ".join(str(number) for number in numbers), "number"
    if "Binary" in value:
        return "", "inline_table"
    return "", "unknown"


_TEMPERATURE = re.compile(
    r"(?P<value>(?<![0-9.])[-+]?\d+(?:\.\d+)?)\s*"
    r"(?:(?:\u00b0|deg(?:rees?)?\.?\s*)\s*(?P<unit>[CFK])|(?P<kelvin>K))"
    r"(?![A-Za-z])"
)
_PRESSURE = re.compile(
    r"(?P<value>\d+(?:\.\d+)?)\s*"
    r"(?P<unit>mm\s*Hg|torr|kPa|hPa|mbar|bar|atm|Pa)(?![A-Za-z])",
    re.IGNORECASE,
)
_PRESSURE_TO_MMHG: dict[str, float] = {
    "mmhg": 1.0,
    "torr": 1.0,
    "kpa": 7.500617,
    "hpa": 0.7500617,
    "mbar": 0.7500617,
    "bar": 750.0617,
    "atm": 760.0,
    "pa": 0.007500617,
}
_CONDITION = re.compile(r"(?<![A-Za-z])(?:at|@)\s+(?P<clause>[^;()\[\]]+)", re.IGNORECASE)
_QUANTITY_LABEL = re.compile(r"(?P<label>[A-Za-z][A-Za-z0-9 ,/()'\-]{0,60}?)\s*:")
_TEMPERATURE_LABEL_TOKENS = frozenset(
    {
        "melting",
        "boiling",
        "flash",
        "freezing",
        "point",
        "temperature",
        "mp",
        "bp",
        "fp",
    }
)
_NARRATIVE_WORDS = ("decompos", "burn", "explos", "polymeriz", "sublim", "ignit")
_SENTENCE_BREAK = re.compile(r";\s|\.\s")
_TABLE_REFERENCE = re.compile(r"\[[^\]]*\]")


def _to_celsius(value: float, unit: str) -> float:
    if unit == "F":
        return (value - 32.0) * 5.0 / 9.0
    if unit == "K":
        return value - 273.15
    return value


def normalize_temperature(text: str) -> dict[str, object]:
    """The temperature PUG-View reported, in Celsius, with the matched token.

    Celsius is preferred when the depositor gives both scales (``42 °F (6 °C)``
    is one reading, not two), so no conversion error is introduced where the
    depositor already stated Celsius.
    """

    matches = list(_TEMPERATURE.finditer(_normalise_signs(text)))
    for wanted in ("C", "F", "K"):
        for match in matches:
            unit = match.group("unit") or ("K" if match.group("kelvin") else "")
            if unit == wanted:
                value = float(match.group("value"))
                return {
                    "celsius": _to_celsius(value, wanted),
                    "reported_unit": wanted,
                    "raw": match.group(0).strip(),
                    "converted": wanted != "C",
                    "span": [match.start(), match.end()],
                }
    return {"celsius": None, "reported_unit": "", "raw": "", "converted": False, "span": None}


def normalize_pressure(text: str) -> dict[str, object]:
    match = _PRESSURE.search(_normalise_signs(text))
    if match is None:
        return {"mmhg": None, "raw": ""}
    unit = re.sub(r"\s+", "", match.group("unit")).lower()
    factor = _PRESSURE_TO_MMHG.get(unit)
    if factor is None:
        return {"mmhg": None, "raw": match.group(0).strip()}
    return {"mmhg": float(match.group("value")) * factor, "raw": match.group(0).strip()}


def extract_condition(text: str) -> dict[str, object]:
    """The ``at ...`` clauses of a value: measurement temperature and pressure."""

    clauses = []
    for match in _CONDITION.finditer(_normalise_signs(text)):
        clause = match.group("clause").strip()
        if clause:
            clauses.append(clause)
    condition = "; ".join(clauses)
    if not condition:
        return {"condition_raw": "", "temperature_c": None, "pressure_mmhg": None}
    return {
        "condition_raw": condition,
        "temperature_c": normalize_temperature(condition)["celsius"],
        "pressure_mmhg": normalize_pressure(condition)["mmhg"],
    }


def _clause_bounds(text: str, index: int) -> tuple[int, int]:
    """Clause bounds around ``index``, treating only "; " and ". " as breaks.

    A bare ``.`` must not count: HSDB writes decimals (``38.8``) inside the
    same clause, and a decimal point is not a sentence boundary.
    """

    start = 0
    for match in _SENTENCE_BREAK.finditer(text, 0, index):
        start = match.end()
    end = len(text)
    for match in _SENTENCE_BREAK.finditer(text, index):
        end = match.start()
        break
    return start, end


def is_narrative_temperature(text: str, span: Sequence[int]) -> bool:
    """True when the matched temperature is a sentence clause, not the property.

    HSDB deposits narrative lines inside the melting and boiling sections, for
    example ``Burns with luminous flame; dielectric constant: 38.8 at 20 °C``.
    The 20 °C belongs to a different quantity, so the value is left unparsed
    rather than recorded as a boiling point.
    """

    start, _ = _clause_bounds(text, span[0])
    clause = text[start : span[1]].lower()
    if any(word in clause for word in _NARRATIVE_WORDS):
        return True
    labels = _QUANTITY_LABEL.findall(text[start : span[0]])
    if not labels:
        return False
    tokens = set(re.findall(r"[a-z]+", labels[-1].lower()))
    return not (tokens & _TEMPERATURE_LABEL_TOKENS)


def flatten_temperature_value(text: str) -> dict[str, object]:
    """A melting/boiling/flash point row, in Celsius, with its condition."""

    condition = extract_condition(text)
    result: dict[str, object] = {
        "value_numeric": None,
        "unit": "",
        "temperature_c": None,
        "condition_raw": condition["condition_raw"],
        "pressure_mmhg": condition["pressure_mmhg"],
        "subtype": "",
        "notes": "",
    }
    notes = []
    normalized = normalize_temperature(text)
    span = normalized["span"]
    if normalized["celsius"] is None or span is None:
        notes.append("no_parseable_temperature")
    else:
        raw = _normalise_signs(text)
        if is_narrative_temperature(raw, span):
            notes.append("narrative_entry_not_parsed")
        else:
            result["value_numeric"] = normalized["celsius"]
            result["unit"] = "degC"
            result["temperature_c"] = normalized["celsius"]
            if normalized["converted"]:
                notes.append(f"converted_from_deg{normalized['reported_unit']}")
    result["notes"] = "; ".join(notes)
    return result


_DENSITY_UNIT = re.compile(
    r"(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>"
    r"g\s*/\s*(?:cu\s*cm|cm3|cm\^3|cm\u00b3|cc|mL|ml)|"
    r"kg\s*/\s*m\s*3|kg\s*/\s*m\^3|kg\s*/\s*m\u00b3|"
    r"lb\s*/\s*(?:cu\s*ft|ft3)|"
    r"g\s*/\s*l(?![a-z]))",
    re.IGNORECASE,
)
_DENSITY_FACTORS: dict[str, float] = {
    "g/cucm": 1.0,
    "g/cm3": 1.0,
    "g/cm^3": 1.0,
    "g/cm\u00b3": 1.0,
    "g/cc": 1.0,
    "g/ml": 1.0,
    "kg/m3": 0.001,
    "kg/m^3": 0.001,
    "kg/m\u00b3": 0.001,
    "lb/cuft": 0.016018463,
    "lb/ft3": 0.016018463,
    "g/l": 0.001,
}
_VAPOUR_WORDS = ("vapor", "vapour", "gas", "air")
_RELATIVE_WORDS = ("specific gravity", "relative density", "water = 1", "water=1")
_DENSITY_LABEL_TOKENS = frozenset(
    {"density", "densities", "gravity", "specific", "relative"}
)
# Labels that mark a number which is not a liquid density at all.
_DENSITY_EXCLUSION_TOKENS = frozenset(
    {
        "bulk",
        "capacity",
        "coefficient",
        "compressibility",
        "conductance",
        "conductivity",
        "constant",
        "correction",
        "critical",
        "cubical",
        "expansion",
        "gal",
        "gradient",
        "heat",
        "index",
        "pressure",
        "refractive",
        "resistivity",
        "solubility",
        "tension",
        "viscosity",
        "volume",
        "wt",
    }
)
_BULK_WORDS = ("bulk dens",)
_NUMBER = re.compile(r"\d+(?:\.\d+)?")
_TEMPERATURE_SUFFIX = re.compile(r"^\s*(?:\u00b0|deg(?:rees?)?\.?\s*)[CFK]\b")


def _is_excluded_quantity(text: str, index: int) -> bool:
    """True when the number belongs to a labelled non-density quantity.

    Under the Density heading HSDB also dumps lines such as ``Coefficient of
    cubical expansion: 9.56X10-7 ...`` or ``critical density: 0.2734``. A
    colon label that is neither a density word nor absent marks the number as
    belonging to a different quantity, so it is skipped rather than recorded.
    """

    start, _ = _clause_bounds(text, index)
    head = text[start:index]
    if any(word in head.lower() for word in _NARRATIVE_WORDS):
        return True
    labels = _QUANTITY_LABEL.findall(head)
    if not labels:
        return False
    tokens = set(re.findall(r"[a-z]+", labels[-1].lower()))
    if tokens & _DENSITY_EXCLUSION_TOKENS:
        return True
    return not (tokens & _DENSITY_LABEL_TOKENS)


def _first_quantity_number(text: str) -> float | None:
    """First bare number, skipping asides, temperature tokens and narratives."""

    cleaned = _TABLE_REFERENCE.sub(" ", _normalise_signs(text))
    cleaned = re.sub(r"\([^)]*\)", " ", cleaned)
    for match in _NUMBER.finditer(cleaned):
        tail = cleaned[match.end() :]
        if tail.lstrip().startswith("%"):
            continue
        if _TEMPERATURE_SUFFIX.match(tail):
            continue
        if _is_excluded_quantity(cleaned, match.start()):
            continue
        return float(match.group(0))
    return None


def normalize_density(text: str) -> dict[str, object]:
    """Classify and normalise one Density entry.

    Subtypes matter because the Density section also carries vapour and relative
    densities: a vapour/air entry is excluded outright, ``specific gravity`` and
    ``relative density`` are kept but flagged, and a bare number under the
    Density heading is recorded as ``unspecified`` rather than silently treated
    as g/cm3.
    """

    condition = extract_condition(text)
    result: dict[str, object] = {
        "value_numeric": None,
        "unit": "",
        "temperature_c": condition["temperature_c"],
        "condition_raw": condition["condition_raw"],
        "pressure_mmhg": condition["pressure_mmhg"],
        "subtype": "",
        "notes": "",
    }
    lowered = text.lower()
    if any(word in lowered for word in _BULK_WORDS):
        result["subtype"] = "excluded_bulk"
        result["notes"] = "bulk_density_is_not_a_liquid_density"
        return result
    if any(word in lowered for word in _VAPOUR_WORDS):
        result["subtype"] = "excluded_vapour"
        result["notes"] = "vapour_or_air_density_is_not_a_liquid_density"
        return result
    match = _DENSITY_UNIT.search(_normalise_signs(text))
    if match is not None:
        key = re.sub(r"\s+", "", match.group("unit")).lower()
        factor = _DENSITY_FACTORS.get(key)
        if factor is not None:
            result["value_numeric"] = float(match.group("value")) * factor
            result["unit"] = "g/cm3"
            result["subtype"] = "absolute"
            if factor != 1.0:
                result["notes"] = f"converted_from {key}"
            return result
    number = _first_quantity_number(text)
    if number is None:
        result["subtype"] = "unparsed"
        result["notes"] = "no_numeric_density_found"
        return result
    if any(word in lowered for word in _RELATIVE_WORDS):
        result["value_numeric"] = number
        result["unit"] = "relative"
        result["subtype"] = "relative"
        result["notes"] = "relative_density_referenced_to_water_not_an_absolute_density"
        return result
    result["value_numeric"] = number
    result["unit"] = "unspecified"
    result["subtype"] = "unspecified"
    result["notes"] = "unit_not_stated_by_the_depositor"
    return result

# --------------------------------------------------------------------------
# Harvesting.
# --------------------------------------------------------------------------


def build_value_rows(
    target: Target,
    record: Mapping[str, object],
    *,
    source_url: str,
    retrieved_at: str,
) -> list[dict[str, str]]:
    """One row per deposited value, each with its depositor and reference."""

    depositors: dict[object, str] = {}
    references = record.get("Reference")
    if isinstance(references, list):
        for entry in references:
            if isinstance(entry, Mapping) and "ReferenceNumber" in entry:
                depositors[entry["ReferenceNumber"]] = str(entry.get("SourceName") or "")

    rows: list[dict[str, str]] = []
    for property_name, heading, section in find_property_sections(record):
        information = section.get("Information")
        if not isinstance(information, list):
            continue
        for info in information:
            if not isinstance(info, Mapping):
                continue
            text, kind = value_text(info)
            reference_number = info.get("ReferenceNumber")
            row = {column: "" for column in VALUE_COLUMNS}
            row["inchikey"] = target.inchikey
            row["name"] = target.name
            row["pubchem_cid"] = target.cid
            row["property"] = property_name
            row["section_heading"] = heading
            row["value_raw"] = text
            row["reference_number"] = (
                str(reference_number) if reference_number is not None else ""
            )
            row["depositor"] = depositors.get(reference_number, "")
            citations = info.get("Reference")
            if isinstance(citations, list) and citations:
                row["reference"] = str(citations[0])
            row["peer_reviewed"] = (
                "true"
                if "PEER REVIEWED" in str(info.get("Description") or "").upper()
                else "false"
            )
            row["source_kind"] = SOURCE_KIND
            row["quality_layer"] = QUALITY_LAYER
            row["source_url"] = source_url
            row["retrieved_at"] = retrieved_at

            notes = []
            if kind != "string":
                notes.append(f"value_kind={kind}")
                if kind in ("number", "inline_table"):
                    notes.append("structured_value_not_parsed")
            else:
                flat = (
                    flatten_temperature_value(text)
                    if property_name in TEMPERATURE_PROPERTIES
                    else normalize_density(text)
                )
                notes.append(str(flat["notes"]))
                row["value_numeric"] = _format_number(flat["value_numeric"])
                row["unit"] = str(flat["unit"])
                row["temperature_c"] = _format_number(flat["temperature_c"])
                row["condition_raw"] = str(flat["condition_raw"])
                row["pressure_mmhg"] = _format_number(flat["pressure_mmhg"])
                row["subtype"] = str(flat["subtype"])
            row["notes"] = "; ".join(note for note in notes if note)
            rows.append(row)
    return rows


def harvest_compound(
    target: Target,
    client: PubChemClient,
    *,
    retrieved_at: str,
) -> tuple[list[dict[str, str]], str]:
    """Harvest one compound. Returns (value rows, harvest status)."""

    try:
        payload = client.fetch(target.inchikey, target.cid)
    except OfflineError:
        return [], "unresolved_offline"
    if payload.get("not_found"):
        return [], str(payload.get("resolution_status") or "no_experimental_properties_section")
    record = payload.get("Record")
    if not isinstance(record, Mapping):
        return [], "unresolved_empty_response"
    sections = find_property_sections(record)
    if not sections:
        return [], "harvested_without_target_properties"
    rows = build_value_rows(
        target,
        record,
        source_url=_heading_url(target.cid),
        retrieved_at=retrieved_at,
    )
    return rows, "harvested"


def harvest_targets(
    targets: Sequence[Target],
    client: PubChemClient,
    *,
    retrieved_at: str,
    failures: dict[str, str] | None = None,
) -> tuple[list[dict[str, str]], dict[str, str]]:
    """Harvest every target, recording a failed request instead of aborting.

    A single unretryable request must not sink the batch: the key is recorded
    as ``request_failed`` with its reason and the run continues, so the
    failure stays visible in the summary instead of being replaced by a value.
    """

    rows: list[dict[str, str]] = []
    statuses: dict[str, str] = {}
    for target in targets:
        try:
            target_rows, status = harvest_compound(target, client, retrieved_at=retrieved_at)
        except RuntimeError as error:
            status = "request_failed"
            target_rows = []
            if failures is not None:
                failures[target.inchikey] = str(error)
        rows.extend(target_rows)
        statuses[target.inchikey] = status
    return rows, statuses


def select_values(rows: Sequence[Mapping[str, str]]) -> list[dict[str, str]]:
    """One representative value per (InChIKey, property).

    The rule is deterministic and is stated in every row: peer-reviewed entries
    first; for density the most absolute subtype wins (absolute, then relative,
    then unspecified); among the remaining candidates the lower median is taken
    and its own depositor, reference and condition travel with it.
    """

    grouped: dict[tuple[str, str], list[Mapping[str, str]]] = {}
    for row in rows:
        grouped.setdefault((row["inchikey"], row["property"]), []).append(row)

    selected: list[dict[str, str]] = []
    for (_, property_name), group in sorted(grouped.items()):
        parsed = [row for row in group if row["value_numeric"]]
        if not parsed:
            continue
        if property_name == "density":
            best = min(_DENSITY_SUBTYPE_ORDER.get(row["subtype"], 9) for row in parsed)
            pool = [row for row in parsed if _DENSITY_SUBTYPE_ORDER.get(row["subtype"], 9) == best]
            rule = DENSITY_SELECTION_RULE
        else:
            pool = parsed
            rule = TEMPERATURE_SELECTION_RULE
        reviewed = [row for row in pool if row["peer_reviewed"] == "true"] or pool
        ordered = sorted(
            reviewed,
            key=lambda row: (
                float(row["value_numeric"]),
                row["depositor"],
                row["reference_number"],
            ),
        )
        pick = ordered[(len(ordered) - 1) // 2]
        entry = {column: str(pick.get(column, "")) for column in SELECTED_COLUMNS}
        entry["n_values_seen"] = str(len(group))
        entry["n_parsed_values"] = str(len(parsed))
        entry["selection_rule"] = rule
        selected.append(entry)
    return selected


# --------------------------------------------------------------------------
# Outputs.
# --------------------------------------------------------------------------


def write_rows(path: Path, rows: Sequence[Mapping[str, str]], columns: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(columns), lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in columns})


def cache_population_window(cache_dir: Path, inchikeys: Iterable[str]) -> list[str]:
    """UTC window in which the cached responses were written.

    A cache-only re-run spends no requests, so the file timestamps are the
    durable evidence of when the cache was actually filled.
    """

    stamps = []
    for inchikey in inchikeys:
        path = cache_dir / f"{urllib.parse.quote(inchikey, safe='')}{CACHE_SUFFIX}"
        if path.is_file():
            stamps.append(path.stat().st_mtime)
    if not stamps:
        return []
    return [
        datetime.fromtimestamp(min(stamps), UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        datetime.fromtimestamp(max(stamps), UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    ]


def _counter(values: Iterable[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        if not value:
            continue
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def _numeric_range(rows: Sequence[Mapping[str, str]]) -> dict[str, object]:
    numbers = [float(row["value_numeric"]) for row in rows if row["value_numeric"]]
    if not numbers:
        return {"n": 0, "min": None, "max": None}
    return {"n": len(numbers), "min": round(min(numbers), 4), "max": round(max(numbers), 4)}


def summarize(
    rows: Sequence[Mapping[str, str]],
    selected: Sequence[Mapping[str, str]],
    statuses: Mapping[str, str],
    stats: ClientStats,
    *,
    targets: Sequence[Target],
    run_idempotent: bool,
    request_failures: Mapping[str, str] | None = None,
) -> dict[str, object]:
    property_coverage: dict[str, dict[str, int]] = {}
    depositor_counts: dict[str, dict[str, int]] = {}
    ranges: dict[str, dict[str, object]] = {}
    for property_name in LIQUID_WINDOW_PROPERTIES:
        property_rows = [row for row in rows if row["property"] == property_name]
        property_coverage[property_name] = {
            "keys_with_value": len({row["inchikey"] for row in property_rows}),
            "keys_with_parsed_value": len(
                {row["inchikey"] for row in property_rows if row["value_numeric"]}
            ),
            "value_rows": len(property_rows),
            "peer_reviewed_rows": sum(
                1 for row in property_rows if row["peer_reviewed"] == "true"
            ),
            "unparsed_rows": sum(1 for row in property_rows if not row["value_numeric"]),
        }
        depositor_counts[property_name] = _counter(row["depositor"] for row in property_rows)
        ranges[property_name] = _numeric_range(property_rows)

    temperatures_by_key: dict[str, set[str]] = {}
    for row in rows:
        if row["value_numeric"] and row["property"] in TEMPERATURE_PROPERTIES:
            temperatures_by_key.setdefault(row["inchikey"], set()).add(row["property"])

    def key_entry(target: Target) -> dict[str, str]:
        return {
            "inchikey": target.inchikey,
            "name": target.name,
            "pubchem_cid": target.cid,
            "harvest_status": statuses.get(target.inchikey, ""),
        }

    unresolved = [
        key_entry(target) for target in targets if statuses.get(target.inchikey) != "harvested"
    ]
    missing_temperatures = [
        key_entry(target) for target in targets if target.inchikey not in temperatures_by_key
    ]
    notes = [row["notes"] for row in rows]
    return {
        "generated_at_utc": _utc_now(),
        "coverage_set": len(targets),
        "targets_with_cid": sum(1 for target in targets if target.cid),
        "cache_hits": stats.cache_hits,
        "network_calls": stats.network_calls,
        "retries": stats.retries,
        "throttle_seconds": round(stats.throttle_seconds, 6),
        "throttled_requests": stats.throttled_requests,
        # The cache is the durable record of what the harvest actually cost: a
        # later cache-only re-run spends no requests, so the populated entries
        # (and the log line written next to them) keep the original cost
        # auditable instead of invisible.
        "cache_entries_for_coverage_set": stats.cache_entries,
        "throttle_seconds_per_request": stats.throttle_seconds,
        "run_idempotent": run_idempotent,
        "harvest_status_counts": _counter(statuses.get(target.inchikey, "") for target in targets),
        "property_coverage": property_coverage,
        "keys_with_any_temperature": len(temperatures_by_key),
        "keys_with_all_three_temperatures": sum(
            1 for properties in temperatures_by_key.values() if len(properties) == 3
        ),
        "keys_with_mp_bp_fp": {
            property_name: len(
                {
                    row["inchikey"]
                    for row in rows
                    if row["property"] == property_name and row["value_numeric"]
                }
            )
            for property_name in TEMPERATURE_PROPERTIES
        },
        "value_rows": len(rows),
        "selected_rows": len(selected),
        "peer_reviewed_rows": sum(1 for row in rows if row["peer_reviewed"] == "true"),
        "unparsed_value_rows": sum(1 for row in rows if not row["value_numeric"]),
        "narrative_entries_skipped": sum(
            1 for note in notes if "narrative_entry_not_parsed" in note
        ),
        "temperature_unit_conversions": {
            "stated_in_degC": sum(1 for row in rows if row["unit"] == "degC" and "converted" not in row["notes"]),
            "converted_to_degC": sum(1 for row in rows if "converted_from_deg" in row["notes"]),
        },
        "density_subtype_counts": _counter(
            row["subtype"] for row in rows if row["property"] == "density"
        ),
        "depositor_counts_by_property": depositor_counts,
        "numeric_ranges_by_property": ranges,
        "missing_temperature_keys": missing_temperatures,
        "missing_temperature_key_count": len(missing_temperatures),
        "unresolved": unresolved,
        "unresolved_count": len(unresolved),
        "request_failures": dict(sorted((request_failures or {}).items())),
        "source_kind": SOURCE_KIND,
        "quality_layer": QUALITY_LAYER,
        "quality_layer_note": QUALITY_LAYER_NOTE,
        "values_path": "",
        "selected_path": "",
        "harvest_log_path": "",
        "recorded_harvest_cost_from_log": {},
    }


REQUIRED_RUN_RECORD_KEYS: tuple[str, ...] = (
    "generated_at_utc",
    "coverage_set",
    "network_calls",
    "requests",
    "retries",
    "throttle_seconds",
    "cache_hits",
    "keys_harvested",
    "value_rows",
    "selected_rows",
    "offline",
)


def build_run_record(summary: Mapping[str, object], *, offline: bool) -> dict[str, object]:
    """One ``_harvest_runs.jsonl`` line, written on every real run."""

    status_counts = summary.get("harvest_status_counts")
    harvested = 0
    if isinstance(status_counts, Mapping):
        harvested = int(status_counts.get("harvested", 0))
    return {
        "generated_at_utc": summary["generated_at_utc"],
        "coverage_set": summary["coverage_set"],
        "network_calls": summary["network_calls"],
        "requests": summary["network_calls"],
        "retries": summary["retries"],
        "throttle_seconds": summary["throttle_seconds"],
        "cache_hits": summary["cache_hits"],
        "keys_harvested": harvested,
        "value_rows": summary["value_rows"],
        "selected_rows": summary["selected_rows"],
        "offline": offline,
    }


def recorded_harvest_cost(path: Path) -> dict[str, object]:
    """The harvest cost recovered from ``_harvest_runs.jsonl``.

    A cache-only re-run spends no requests, so its own counts cannot
    describe the harvest. The log holds one line per run, the harvesting run
    included, and the most expensive line is the durable record of what the
    harvest cost -- which is why every run must write a line.
    """

    empty: dict[str, object] = {
        "logged_runs": 0,
        "max_network_calls": 0,
        "retries_at_max": 0,
        "throttle_seconds_at_max": 0.0,
    }
    if not path.is_file():
        return empty
    runs = 0
    best: Mapping[str, object] | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except ValueError:  # pragma: no cover - the probe only writes valid JSON
            continue
        if not isinstance(record, Mapping):
            continue
        runs += 1
        if best is None or float(record.get("network_calls", 0)) > float(
            best.get("network_calls", 0)
        ):
            best = record
    if best is None:
        return empty
    return {
        "logged_runs": runs,
        "max_network_calls": int(best.get("network_calls", 0)),
        "retries_at_max": int(best.get("retries", 0)),
        "throttle_seconds_at_max": float(best.get("throttle_seconds", 0.0)),
    }


def append_run_log(path: Path, record: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8", newline="") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


# --------------------------------------------------------------------------
# Entry point.
# --------------------------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--identity-map", type=Path, default=IDENTITY_MAP_PATH)
    parser.add_argument("--values", type=Path, default=DEFAULT_VALUES)
    parser.add_argument("--selected", type=Path, default=DEFAULT_SELECTED)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument("--harvest-log", type=Path, default=DEFAULT_HARVEST_LOG)
    parser.add_argument("--throttle-seconds", type=float, default=DEFAULT_THROTTLE_SECONDS)
    parser.add_argument("--attempts", type=int, default=DEFAULT_ATTEMPTS)
    parser.add_argument(
        "--proxy",
        default="none",
        help="'none' (direct), 'env' (honour HTTP(S)_PROXY) or an explicit proxy URL",
    )
    parser.add_argument("--limit", type=int, default=0, help="harvest only the first N keys")
    parser.add_argument("--offline", action="store_true", help="serve only from cache")
    parser.add_argument("--refresh", action="store_true", help="ignore the cache")
    parser.add_argument("--dry-run", action="store_true", help="do not write the outputs")
    arguments = parser.parse_args(argv)

    targets = load_targets(arguments.identity_map)
    if arguments.limit:
        targets = targets[: arguments.limit]

    client = PubChemClient(
        cache_dir=arguments.cache_dir,
        throttle_seconds=arguments.throttle_seconds,
        attempts=arguments.attempts,
        offline=arguments.offline,
        opener=build_opener(arguments.proxy),
    )
    if arguments.refresh:
        for target in targets:
            client.cache_path(target.inchikey).unlink(missing_ok=True)

    # One timestamp for the whole run, so the idempotence comparison below is
    # not defeated by the clock ticking between the two passes.
    stamp = _utc_now()
    failures: dict[str, str] = {}
    rows, statuses = harvest_targets(targets, client, retrieved_at=stamp, failures=failures)

    # The second pass is the cache check: identical rows and no new request.
    before = client.stats.network_calls
    second_rows, second_statuses = harvest_targets(targets, client, retrieved_at=stamp)
    run_idempotent = (
        second_rows == rows
        and second_statuses == statuses
        and client.stats.network_calls == before
    )

    client.stats.cache_entries = sum(
        1 for target in targets if client.cache_path(target.inchikey).is_file()
    )
    selected = select_values(rows)
    summary = summarize(
        rows,
        selected,
        statuses,
        client.stats,
        targets=targets,
        run_idempotent=run_idempotent,
        request_failures=failures,
    )
    summary["throttle_seconds_per_request"] = arguments.throttle_seconds
    summary["cache_populated_between_utc"] = cache_population_window(
        arguments.cache_dir, (target.inchikey for target in targets)
    )
    if not arguments.dry_run:
        # The log line is written on every real run, the harvesting run
        # included, so its request cost is recoverable from the log alone.
        append_run_log(arguments.harvest_log, build_run_record(summary, offline=arguments.offline))
        write_rows(arguments.values, rows, VALUE_COLUMNS)
        write_rows(arguments.selected, selected, SELECTED_COLUMNS)
        summary["values_path"] = str(arguments.values)
        summary["selected_path"] = str(arguments.selected)
        summary["harvest_log_path"] = str(arguments.harvest_log)
        # A cache-only re-run spends nothing, so the summary states both its
        # own request count and the harvest cost recovered from the log.
        summary["recorded_harvest_cost_from_log"] = recorded_harvest_cost(
            arguments.harvest_log
        )
        arguments.summary.parent.mkdir(parents=True, exist_ok=True)
        with open(arguments.summary, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(summary, indent=2, sort_keys=True) + "\n")

    print(json.dumps({key: value for key, value in summary.items() if key != "unresolved"}, indent=2))
    if summary["unresolved"]:
        print(f"unresolved: {summary['unresolved_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
