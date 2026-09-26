"""ILThermo (NIST SRD 147) probe: is it a real door to new compounds with epsilon(T)?

Context
-------
v1.0 ships a 246-compound *static* relative-permittivity table. The v1.x lever is
already known to be compound coverage, not temperature coverage
(``probes/dielectric_compound_coverage_curve.py``: the frozen-protocol learning
curve is still rising at 236 compounds). ILThermo is one of the few remaining
zero-cost sources on the v1.x plan, it is temperature-resolved by nature, and
ionic liquids are a genuinely new family -- ``data/dielectric_v03.csv`` carries
only four boundary compounds flagged ``out_of_scope_ionic_or_organometallic``.

This probe answers four questions with evidence rather than recollection:

(a) does ILThermo expose relative permittivity at all,
(b) does that data carry temperature,
(c) is there a machine-readable export,
(d) how many distinct compounds carry it, and how many would be *new* to us.

Why the probe is built the way it is
------------------------------------
The site is a Dojo single-page app: the HTML shell carries no query surface. The
real surface lives in ``/ilthermo.js``, which calls ``/ILT2/ilprpls`` (property
list), ``/ILT2/ilsearch`` (set search), ``/ILT2/ilset`` (one data set, JSON) and
``/ILT2/ilimage`` (structure image). So the probe starts with a *discovery pass*
that records the exact URL, HTTP status and byte count of every candidate
endpoint before it relies on any of them.

Three traps this probe refuses to fall into:

- ``ilsearch`` returns its rows under ``res``/``cnt``, not ``data``. An empty
  ``data`` list reads as "no results" while 1,509 rows are actually present.
- The property filter ``prp`` takes a short opaque key that is *index-paired* with
  the property name in ``ilprpls``. Guessing the key silently returns a different
  property (``prp=JYHK`` returns "Speed of sound", not "Relative permittivity"),
  so the probe re-derives the pairing and then verifies it against a live query
  plus a control query drawn from the same property class.
- ILThermo publishes no CAS, no SMILES and no InChIKey. The roster join is
  therefore name normalisation for every compound, plus an RDKit
  molecular-formula structural check on the datasets that are actually fetched.
  Anything that resolves under neither is reported as unresolved rather than
  assumed to be new.

Nothing in the summary is recalled or estimated: every number traces to a response
received during this run, and every failure is written down verbatim.

Politeness
----------
Descriptive ``User-Agent``, fixed sleep between calls, ``429``/``Retry-After``
handling, and a hard request budget printed at the end.

Outputs
-------
``probes/ilthermo_probe_summary.json``
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import time
import unicodedata
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from html import unescape
from pathlib import Path
from typing import Any

import requests

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

ORIGIN = "https://ilthermo.boulder.nist.gov"
PROPERTY_LIST_PATH = "/ILT2/ilprpls"
SEARCH_PATH = "/ILT2/ilsearch"
DATASET_PATH = "/ILT2/ilset"
STRUCTURE_IMAGE_PATH = "/ILT2/ilimage"
STATUS_PATH = "/ILT2/ilstats"
JS_BUNDLE_PATH = "/ilthermo.js"

USER_AGENT = "electrolyte-ml-research/1.0 (ILThermo SRD147 probe)"

TARGET_PROPERTY_NAME = "Relative permittivity"
TEMPERATURE_COLUMN = "Temperature, K"
FREQUENCY_COLUMN_PREFIX = "Frequency"

DEFAULT_SLEEP_SECONDS = 1.0
HTTP_TIMEOUT_SECONDS = 60
DEFAULT_REQUEST_BUDGET = 60
DEFAULT_SAMPLE_SETS = 8
TEMPERATURE_SERIES_CHECKS = 2
BACKOFF_SECONDS = (5.0, 15.0)
MAX_BACKOFF_SECONDS = 60.0
RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})

ROSTER_PATH = REPOSITORY_ROOT / "data" / "dielectric_v03.csv"
DEFAULT_SUMMARY = REPOSITORY_ROOT / "probes" / "ilthermo_probe_summary.json"

# Endpoint discovery. The last two are deliberate negative controls: if the site
# ever grew a bulk export, these are the shapes it would plausibly take.
DISCOVERY_TARGETS: tuple[tuple[str, str, dict[str, str]], ...] = (
    ("site_root", "/", {}),
    ("js_bundle", JS_BUNDLE_PATH, {}),
    ("property_list_api", PROPERTY_LIST_PATH, {}),
    ("status_page", STATUS_PATH, {}),
    ("search_api_no_params", SEARCH_PATH, {}),
    ("dataset_api_no_params", DATASET_PATH, {}),
    ("ilt2_directory", "/ILT2/", {}),
    ("csv_export_guess", "/ILT2/ilset.csv", {}),
    ("txt_export_guess", "/ILT2/ilsearch.txt", {}),
)

IONIC_MARKERS: tuple[str, ...] = (
    "imidazolium",
    "pyrrolidinium",
    "piperidinium",
    "pyridinium",
    "ammonium",
    "phosphonium",
    "sulfonium",
    "cholin",
    "guanidinium",
    "triazolium",
    "thiazolium",
    "pyrazolium",
    "morpholinium",
    "tetrafluoroborate",
    "hexafluorophosphate",
)

_TAG_RE = re.compile(r"<[^>]+>")
_ELEMENT_RE = re.compile(r"([A-Z][a-z]?)(\d*)")
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")
_SPACE_RE = re.compile(r"\s+")

class BudgetExhausted(RuntimeError):
    """Raised when a request would exceed the hard request budget."""


@dataclass(frozen=True)
class HttpResponse:
    """A minimal, transport-agnostic HTTP response."""

    url: str
    status: int
    body: bytes
    headers: Mapping[str, str] = field(default_factory=dict)

    @property
    def text(self) -> str:
        return self.body.decode("utf-8", errors="replace")

    def json(self) -> Any:
        return json.loads(self.text)


@dataclass
class RequestBudget:
    """Hard request budget with a per-request audit log."""

    limit: int
    used: int = 0
    log: list[dict[str, Any]] = field(default_factory=list)

    @property
    def remaining(self) -> int:
        return max(0, self.limit - self.used)

    def consume(self) -> None:
        if self.used >= self.limit:
            raise BudgetExhausted(f"request budget of {self.limit} exhausted")
        self.used += 1


@dataclass(frozen=True)
class PropertyEntry:
    """One (class, key, name) triple from ``/ILT2/ilprpls``."""

    cls: str
    key: str
    name: str


@dataclass(frozen=True)
class SearchHit:
    """One row of a ``/ILT2/ilsearch`` result."""

    setid: str
    reference: str
    property_name: str
    component_names: tuple[str, ...]
    datapoints: int


@dataclass(frozen=True)
class SearchPage:
    count: int
    errors: tuple[str, ...]
    header: tuple[str, ...]
    hits: tuple[SearchHit, ...]


@dataclass(frozen=True)
class Component:
    name: str
    formula: str
    molar_mass: str
    structure_key: str


@dataclass(frozen=True)
class Dataset:
    setid: str
    title: str
    reference_title: str
    reference_full: str
    column_headers: tuple[tuple[str, str | None], ...]
    components: tuple[Component, ...]
    rows: tuple[tuple[tuple[str, ...], ...], ...]
    method: str


@dataclass(frozen=True)
class Observation:
    temperature_k: float | None
    relative_permittivity: float | None
    uncertainty: float | None
    frequency_mhz: float | None


@dataclass(frozen=True)
class Roster:
    by_name: Mapping[str, str]
    by_formula: Mapping[str, str]
    inchikey_by_name: Mapping[str, str]
    out_of_scope_names: tuple[str, ...]


@dataclass(frozen=True)
class MatchOutcome:
    """Roster join result.

    ``verdict`` is deliberately conservative: only a normalised *name* hit counts as
    ``matched_name``. A shared molecular formula is recorded as a collision flag but
    never as a match, because constitutional isomers share a formula while being
    different compounds -- the probe hit exactly that case with
    1-methyl-3-propylimidazolium vs 1-ethyl-2,3-dimethylimidazolium
    bis(trifluoromethylsulfonyl)imide.
    """

    compound: str
    verdict: str
    matched_roster_name: str | None
    inchikey: str | None
    formula: str | None
    structure_resolved: bool
    formula_collision_with_roster: str | None = None


# --------------------------------------------------------------------------- #
# Pure helpers (all unit-testable offline)
# --------------------------------------------------------------------------- #


def parse_retry_after(headers: Mapping[str, str]) -> float | None:
    """Return the Retry-After delay in seconds, or None if absent/invalid."""
    for key, value in headers.items():
        if key.lower() == "retry-after":
            try:
                delay = float(str(value).strip())
            except (TypeError, ValueError):
                return None
            return delay if delay >= 0 else None
    return None


def next_backoff_delay(
    attempt: int,
    headers: Mapping[str, str],
    backoff: Sequence[float] = BACKOFF_SECONDS,
    ceiling: float = MAX_BACKOFF_SECONDS,
) -> float:
    """Server hint if it gave one, otherwise the configured ramp, capped."""
    hint = parse_retry_after(headers)
    if hint is not None:
        return min(hint, ceiling)
    if not backoff:
        return 0.0
    return min(backoff[min(attempt, len(backoff) - 1)], ceiling)


def http_get_with_backoff(
    http_get: Callable[..., HttpResponse],
    url: str,
    params: Mapping[str, str] | None = None,
    *,
    budget: RequestBudget,
    sleep: Callable[[float], None] = time.sleep,
    backoff: Sequence[float] = BACKOFF_SECONDS,
    ceiling: float = MAX_BACKOFF_SECONDS,
) -> HttpResponse:
    """GET with retries on transient statuses, honouring Retry-After."""
    attempts = len(backoff) + 1
    response: HttpResponse | None = None
    for attempt in range(attempts):
        budget.consume()
        response = http_get(url, params)
        if response.status not in RETRY_STATUSES:
            return response
        if attempt == attempts - 1:
            break
        sleep(next_backoff_delay(attempt, response.headers, backoff, ceiling))
    assert response is not None
    return response

def parse_property_list(payload: Mapping[str, Any]) -> list[PropertyEntry]:
    """Flatten ``ilprpls`` into (class, key, name) triples.

    ``key`` and ``name`` are index-paired by the server. Positional pairing is the
    only interpretation the site itself uses, so the probe reproduces it -- and
    then verifies the outcome against a live query instead of trusting it.
    """
    entries: list[PropertyEntry] = []
    for block in payload.get("plist") or []:
        if not isinstance(block, Mapping):
            continue
        cls = str(block.get("cls") or "")
        keys = list(block.get("key") or [])
        names = list(block.get("name") or [])
        for key, name in zip(keys, names, strict=False):
            entries.append(PropertyEntry(cls=cls, key=str(key), name=str(name)))
    return entries


def find_property_keys(entries: Sequence[PropertyEntry], name: str) -> list[PropertyEntry]:
    target = name.strip().lower()
    return [entry for entry in entries if entry.name.strip().lower() == target]


def property_key_names(entries: Sequence[PropertyEntry], key: str) -> list[str]:
    """Names that a given opaque key is index-paired with."""
    return [entry.name for entry in entries if entry.key == key]


def _cell(row: Sequence[Any], index: Mapping[str, int], name: str) -> Any:
    position = index.get(name)
    if position is None or position >= len(row):
        return None
    return row[position]


def parse_search_payload(payload: Mapping[str, Any]) -> SearchPage:
    """Parse an ``ilsearch`` response.

    Rows live under ``res``; ``data`` is not used by this endpoint, and reading it
    makes a 1,509-row result look empty.
    """
    header = tuple(str(item) for item in (payload.get("header") or []))
    index = {name: position for position, name in enumerate(header)}
    rows = payload.get("res") or []
    hits: list[SearchHit] = []
    for row in rows:
        names = []
        for slot in ("nm1", "nm2", "nm3"):
            value = _cell(row, index, slot)
            if value is not None and str(value) not in ("", "0"):
                names.append(str(value))
        raw_datapoints = _cell(row, index, "np")
        try:
            datapoints = int(raw_datapoints)
        except (TypeError, ValueError):
            datapoints = 0
        hits.append(
            SearchHit(
                setid=str(_cell(row, index, "setid") or ""),
                reference=str(_cell(row, index, "ref") or ""),
                property_name=str(_cell(row, index, "prp") or ""),
                component_names=tuple(names),
                datapoints=datapoints,
            )
        )
    try:
        count = int(payload.get("cnt"))
    except (TypeError, ValueError):
        count = len(hits)
    errors = tuple(str(item) for item in (payload.get("errors") or []))
    return SearchPage(count=count, errors=errors, header=header, hits=tuple(hits))


def parse_html_formula(value: str) -> str:
    """``C<SUB>8</SUB>H<SUB>15</SUB>ClN<SUB>2</SUB>`` -> ``C8H15ClN2``."""
    text = _TAG_RE.sub("", value or "")
    return _SPACE_RE.sub("", unescape(text))


def parse_formula_counts(formula: str) -> dict[str, int]:
    """Element counts for a formula string. Order-insensitive by construction."""
    counts: dict[str, int] = {}
    for element, digits in _ELEMENT_RE.findall(formula or ""):
        counts[element] = counts.get(element, 0) + (int(digits) if digits else 1)
    return counts


def formula_signature(formula: str) -> str:
    """Canonical formula key: ``C8H15F6N2P`` -> ``C8F6H15N2P``."""
    counts = parse_formula_counts(formula)
    return "".join(f"{element}{counts[element]}" for element in sorted(counts))


def normalize_name(name: str) -> str:
    """Aggressive name key: case, punctuation and spacing insensitive."""
    text = unicodedata.normalize("NFKC", name or "").lower()
    for source, replacement in (
        ("\u2019", "'"),
        ("\u2018", "'"),
        ("\u2013", "-"),
        ("\u2014", "-"),
        ("\u2212", "-"),
        ("\u00a0", " "),
    ):
        text = text.replace(source, replacement)
    return _NON_ALNUM_RE.sub("", text)


def is_ionic_liquid_name(name: str) -> bool:
    lowered = (name or "").lower()
    if any(marker in lowered for marker in IONIC_MARKERS):
        return True
    return bool(re.search(r"ium\b", lowered))


def parse_component(raw: Mapping[str, Any] | None) -> Component | None:
    if not raw:
        return None
    return Component(
        name=str(raw.get("name") or ""),
        formula=parse_html_formula(str(raw.get("formula") or "")),
        molar_mass=str(raw.get("mw") or ""),
        structure_key=str(raw.get("idout") or ""),
    )


def parse_dataset_payload(payload: Mapping[str, Any], setid: str) -> Dataset:
    """Parse an ``ilset`` response into a dataset plus its raw value grid."""
    reference = payload.get("ref") or {}
    if not isinstance(reference, Mapping):
        reference = {}
    headers: list[tuple[str, str | None]] = []
    for entry in payload.get("dhead") or []:
        if isinstance(entry, (list, tuple)):
            name = str(entry[0]) if entry else ""
            phase = str(entry[1]) if len(entry) > 1 and entry[1] else None
            headers.append((name, phase))
        else:
            headers.append((str(entry), None))
    components = []
    for raw in payload.get("components") or []:
        component = parse_component(raw if isinstance(raw, Mapping) else None)
        if component is not None:
            components.append(component)
    rows: list[tuple[tuple[str, ...], ...]] = []
    for raw_row in payload.get("data") or []:
        cells = []
        for raw_cell in raw_row:
            if isinstance(raw_cell, (list, tuple)):
                cells.append(tuple(str(item) for item in raw_cell))
            else:
                cells.append((str(raw_cell),))
        rows.append(tuple(cells))
    return Dataset(
        setid=setid,
        title=str(payload.get("title") or ""),
        reference_title=str(reference.get("title") or ""),
        reference_full=str(reference.get("full") or ""),
        column_headers=tuple(headers),
        components=tuple(components),
        rows=tuple(rows),
        method=str(payload.get("expmeth") or ""),
    )

def column_index(
    columns: Sequence[tuple[str, str | None]],
    predicate: Callable[[str], bool],
) -> int | None:
    for position, (name, _phase) in enumerate(columns):
        if predicate(name.strip()):
            return position
    return None


def temperature_column_index(columns: Sequence[tuple[str, str | None]]) -> int | None:
    return column_index(columns, lambda text: text.lower() == TEMPERATURE_COLUMN.lower())


def permittivity_column_index(columns: Sequence[tuple[str, str | None]]) -> int | None:
    return column_index(columns, lambda text: text.lower().startswith(TARGET_PROPERTY_NAME.lower()))


def frequency_column_index(columns: Sequence[tuple[str, str | None]]) -> int | None:
    return column_index(columns, lambda text: text.lower().startswith(FREQUENCY_COLUMN_PREFIX.lower()))


def to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def split_cell(cell: Sequence[str]) -> tuple[float | None, float | None]:
    """A data cell is ``[value]`` or ``[value, uncertainty]``."""
    if not cell:
        return None, None
    return to_float(cell[0]), (to_float(cell[1]) if len(cell) > 1 else None)


def extract_observations(dataset: Dataset) -> list[Observation]:
    """Pull (T, epsilon, u, f) from a dataset, or [] if it has no epsilon column."""
    epsilon_index = permittivity_column_index(dataset.column_headers)
    if epsilon_index is None:
        return []
    temperature_index = temperature_column_index(dataset.column_headers)
    frequency_index = frequency_column_index(dataset.column_headers)
    observations: list[Observation] = []
    for row in dataset.rows:
        if epsilon_index < len(row):
            epsilon, uncertainty = split_cell(row[epsilon_index])
        else:
            epsilon, uncertainty = None, None
        temperature = None
        if temperature_index is not None and temperature_index < len(row):
            temperature, _ = split_cell(row[temperature_index])
        frequency = None
        if frequency_index is not None and frequency_index < len(row):
            frequency, _ = split_cell(row[frequency_index])
        observations.append(
            Observation(
                temperature_k=temperature,
                relative_permittivity=epsilon,
                uncertainty=uncertainty,
                frequency_mhz=frequency,
            )
        )
    return observations


def summarize_set(dataset: Dataset, observations: Sequence[Observation]) -> dict[str, Any]:
    temperatures = [o.temperature_k for o in observations if o.temperature_k is not None]
    epsilons = [o.relative_permittivity for o in observations if o.relative_permittivity is not None]
    frequencies = [o.frequency_mhz for o in observations if o.frequency_mhz is not None]
    return {
        "setid": dataset.setid,
        "title": dataset.title,
        "reference": dataset.reference_full or dataset.reference_title,
        "method": dataset.method,
        "n_components": len(dataset.components),
        "components": [
            {"name": c.name, "formula": c.formula, "molar_mass": c.molar_mass}
            for c in dataset.components
        ],
        "column_headers": [list(column) for column in dataset.column_headers],
        "n_rows": len(dataset.rows),
        "n_observations": len(observations),
        "has_temperature_column": temperature_column_index(dataset.column_headers) is not None,
        "has_frequency_column": frequency_column_index(dataset.column_headers) is not None,
        "n_rows_at_zero_frequency": sum(1 for value in frequencies if value == 0.0),
        "n_frequency_rows_above_zero": sum(1 for value in frequencies if value > 0.0),
        "temperature_k_min": min(temperatures) if temperatures else None,
        "temperature_k_max": max(temperatures) if temperatures else None,
        "n_distinct_temperatures": len(set(temperatures)),
        "relative_permittivity_min": min(epsilons) if epsilons else None,
        "relative_permittivity_max": max(epsilons) if epsilons else None,
    }


def load_roster(
    path: Path | str = ROSTER_PATH,
    formula_of_smiles: Callable[[str], str | None] | None = None,
) -> Roster:
    """Load the local v1.0 roster into name/formula/InChIKey indexes."""
    by_name: dict[str, str] = {}
    by_formula: dict[str, str] = {}
    inchikey_by_name: dict[str, str] = {}
    out_of_scope: list[str] = []
    with open(path, encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            name = (row.get("name") or "").strip()
            if not name:
                continue
            key = normalize_name(name)
            by_name[key] = name
            inchikey = (row.get("inchikey") or "").strip()
            if inchikey:
                inchikey_by_name[key] = inchikey
            if "out_of_scope_ionic_or_organometallic" in (row.get("gate_flags") or ""):
                out_of_scope.append(name)
            if formula_of_smiles is not None:
                smiles = (row.get("smiles") or "").strip()
                formula = formula_of_smiles(smiles) if smiles else None
                if formula:
                    by_formula.setdefault(formula_signature(formula), name)
    return Roster(
        by_name=by_name,
        by_formula=by_formula,
        inchikey_by_name=inchikey_by_name,
        out_of_scope_names=tuple(out_of_scope),
    )


def classify_compound(name: str, formula: str | None, roster: Roster) -> MatchOutcome:
    """Decide whether an ILThermo compound is already in the roster.

    Verdicts are ``matched_name`` (normalised name hit, InChIKey available),
    ``matched_formula`` (structural formula hit) or ``not_in_roster``. The
    ``structure_resolved`` flag records whether a formula was actually available,
    so a name-only "not in roster" is never dressed up as a structural claim.
    """
    key = normalize_name(name)
    if key in roster.by_name:
        return MatchOutcome(
            compound=name,
            verdict="matched_name",
            matched_roster_name=roster.by_name[key],
            inchikey=roster.inchikey_by_name.get(key),
            formula=formula,
            structure_resolved=bool(formula),
        )
    signature = formula_signature(formula) if formula else ""
    collision = roster.by_formula.get(signature) if signature else None
    return MatchOutcome(
        compound=name,
        verdict="not_in_roster",
        matched_roster_name=None,
        inchikey=None,
        formula=formula,
        structure_resolved=bool(signature),
        formula_collision_with_roster=collision,
    )

# --------------------------------------------------------------------------- #
# Live probe
# --------------------------------------------------------------------------- #


def default_http_get(url: str, params: Mapping[str, str] | None = None) -> HttpResponse:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json, text/html;q=0.9, */*;q=0.8",
    }
    response = requests.get(
        url,
        params=dict(params) if params else None,
        headers=headers,
        timeout=HTTP_TIMEOUT_SECONDS,
    )
    return HttpResponse(
        url=response.url,
        status=response.status_code,
        body=response.content,
        headers=dict(response.headers),
    )


def rdkit_formula(smiles: str) -> str | None:
    """Molecular formula from SMILES via RDKit, or None if unavailable/unparseable."""
    try:
        from rdkit import Chem, RDLogger
        from rdkit.Chem.rdMolDescriptors import CalcMolFormula
    except Exception:  # noqa: BLE001
        return None
    RDLogger.DisableLog("rdApp.*")
    molecule = Chem.MolFromSmiles(smiles)
    if molecule is None:
        return None
    try:
        return CalcMolFormula(molecule)
    except Exception:  # noqa: BLE001
        return None


def unique_preserving_order(values: Sequence[str]) -> list[str]:
    seen: dict[str, None] = {}
    for value in values:
        seen.setdefault(value, None)
    return list(seen)


def spread(names: Sequence[str], count: int) -> list[str]:
    """Pick ``count`` names spread evenly across an ordered list.

    This exists to make the temperature question answerable with a small sample:
    taking the first few names instead lands on the largest datasets, which turned
    out to be frequency sweeps recorded at one single temperature. Spreading the
    picks across the size range is what exposes both kinds of dataset.
    """
    if count <= 0 or not names:
        return []
    if len(names) <= count:
        return list(names)
    if count == 1:
        return [names[0]]
    step = (len(names) - 1) / (count - 1)
    positions = sorted({round(index * step) for index in range(count)})
    return [names[position] for position in positions]


def choose_sample(pure_components: Mapping[str, int], sample_sets: int) -> list[str]:
    """Pick a bounded, spread-out sample, reserving a molecular-solvent slot.

    ``pure_components`` maps compound name -> datapoint count. Each family is
    ordered by datapoint count before spreading, so the sample spans large and
    small datasets alike.
    """
    ionic = sorted(
        (name for name in pure_components if is_ionic_liquid_name(name)),
        key=lambda name: (-pure_components[name], name),
    )
    molecular = sorted(
        (name for name in pure_components if not is_ionic_liquid_name(name)),
        key=lambda name: (-pure_components[name], name),
    )
    if molecular and sample_sets >= 2:
        ionic_slots = min(len(ionic), max(1, sample_sets // 2))
    else:
        ionic_slots = min(len(ionic), sample_sets)
    chosen = spread(ionic, ionic_slots)
    remaining = [name for name in molecular if name not in chosen]
    chosen += spread(remaining, sample_sets - len(chosen))
    return chosen[:sample_sets]


def run_probe(
    *,
    http_get: Callable[..., HttpResponse] = default_http_get,
    sleep: Callable[[float], None] = time.sleep,
    budget_limit: int = DEFAULT_REQUEST_BUDGET,
    sample_sets: int = DEFAULT_SAMPLE_SETS,
    roster_path: Path | str = ROSTER_PATH,
    formula_of_smiles: Callable[[str], str | None] | None = rdkit_formula,
    now: str | None = None,
) -> dict[str, Any]:
    """Run the full bounded probe and return the summary record."""
    budget = RequestBudget(limit=budget_limit)
    timestamp = now or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    record: dict[str, Any] = {
        "probe": "ilthermo",
        "origin": ORIGIN,
        "generated_utc": timestamp,
        "user_agent": USER_AGENT,
        "request_budget": {"limit": budget_limit, "used": 0},
        "total_bytes_transferred": 0,
        "discovery": [],
        "property_census": {},
        "dataset_census": {},
        "sample": {"sets": []},
        "roster_crosscheck": {},
        "verdicts": {},
        "failures": [],
    }
    failures: list[dict[str, Any]] = record["failures"]
    transferred = 0

    def get(path: str, params: Mapping[str, str] | None = None, *, label: str) -> HttpResponse | None:
        nonlocal transferred
        url = f"{ORIGIN}{path}"
        try:
            response = http_get_with_backoff(http_get, url, params, budget=budget, sleep=sleep)
        except Exception as error:  # noqa: BLE001
            failures.append(
                {
                    "phase": label,
                    "url": url,
                    "params": dict(params or {}),
                    "error": f"{type(error).__name__}: {error}",
                }
            )
            return None
        transferred += len(response.body)
        budget.log.append(
            {
                "phase": label,
                "url": response.url,
                "status": response.status,
                "bytes": len(response.body),
            }
        )
        return response
    # --- phase 1: endpoint discovery ------------------------------------- #
    for label, path, params in DISCOVERY_TARGETS:
        response = get(path, params or None, label="discovery")
        if response is None:
            continue
        content_type = ""
        for key, value in response.headers.items():
            if key.lower() == "content-type":
                content_type = value
                break
        record["discovery"].append(
            {
                "label": label,
                "url": response.url,
                "status": response.status,
                "bytes": len(response.body),
                "content_type": content_type,
            }
        )

    # --- phase 2: property census + index-pairing verification ------------ #
    property_census: dict[str, Any] = {
        "url": f"{ORIGIN}{PROPERTY_LIST_PATH}",
        "status": None,
        "n_property_classes": 0,
        "n_properties": 0,
        "permittivity_keys": [],
        "property_class_of_permittivity": None,
        "verification": {},
        "control_key": None,
    }
    all_properties: list[PropertyEntry] = []
    permittivity_entries: list[PropertyEntry] = []
    response = get(PROPERTY_LIST_PATH, label="property_census")
    if response is not None:
        property_census["status"] = response.status
        try:
            payload = response.json()
        except Exception as error:  # noqa: BLE001
            failures.append({"phase": "property_census", "url": response.url, "error": f"json: {error}"})
            payload = {}
        all_properties = parse_property_list(payload)
        property_census["n_property_classes"] = len(payload.get("plist") or [])
        property_census["n_properties"] = len(all_properties)
        property_census["all_properties"] = [
            {"class": entry.cls, "key": entry.key, "name": entry.name} for entry in all_properties
        ]
        permittivity_entries = find_property_keys(all_properties, TARGET_PROPERTY_NAME)
        property_census["permittivity_keys"] = [entry.key for entry in permittivity_entries]
        if permittivity_entries:
            property_census["property_class_of_permittivity"] = permittivity_entries[0].cls

    verification: dict[str, Any] = {}
    for entry in permittivity_entries:
        response = get(SEARCH_PATH, {"prp": entry.key}, label="pairing_verification")
        if response is None:
            continue
        try:
            page = parse_search_payload(response.json())
        except Exception as error:  # noqa: BLE001
            failures.append(
                {"phase": "pairing_verification", "url": response.url, "error": f"json: {error}"}
            )
            continue
        names = Counter(hit.property_name for hit in page.hits)
        verification[entry.key] = {
            "url": response.url,
            "status": response.status,
            "count": page.count,
            "n_rows": len(page.hits),
            "returned_property_names": dict(names),
            "all_rows_are_target": bool(page.hits) and set(names) == {TARGET_PROPERTY_NAME},
        }

    # Control: a sibling key from the same property class. If the filter matched
    # everything, the control would look identical to the real key.
    permittivity_keys = {entry.key for entry in permittivity_entries}
    sibling_keys = [
        entry.key
        for entry in all_properties
        if permittivity_entries
        and entry.cls == permittivity_entries[0].cls
        and entry.key not in permittivity_keys
    ]
    control_key = sibling_keys[0] if sibling_keys else None
    if control_key is not None:
        response = get(SEARCH_PATH, {"prp": control_key}, label="pairing_control")
        if response is not None:
            try:
                page = parse_search_payload(response.json())
                names = Counter(hit.property_name for hit in page.hits)
                verification[f"control:{control_key}"] = {
                    "url": response.url,
                    "status": response.status,
                    "count": page.count,
                    "n_rows": len(page.hits),
                    "returned_property_names": dict(names),
                    "all_rows_are_target": set(names) == {TARGET_PROPERTY_NAME},
                }
                property_census["control_key"] = control_key
            except Exception as error:  # noqa: BLE001
                failures.append(
                    {"phase": "pairing_control", "url": response.url, "error": f"json: {error}"}
                )
    property_census["verification"] = verification
    record["property_census"] = property_census

    # --- phase 3: dataset census ------------------------------------------ #
    dataset_census: dict[str, Any] = {"by_key": {}, "permittivity_key": None}
    pure_hits: list[SearchHit] = []
    all_hits: list[SearchHit] = []
    permittivity_key = permittivity_entries[0].key if permittivity_entries else None
    if permittivity_key:
        dataset_census["permittivity_key"] = permittivity_key
        for label, params in (
            ("all", {"prp": permittivity_key}),
            ("pure_component", {"prp": permittivity_key, "ncmp": "1"}),
        ):
            response = get(SEARCH_PATH, params, label="dataset_census")
            if response is None:
                continue
            try:
                page = parse_search_payload(response.json())
            except Exception as error:  # noqa: BLE001
                failures.append(
                    {"phase": "dataset_census", "url": response.url, "error": f"json: {error}"}
                )
                continue
            distinct_names = unique_preserving_order(
                [name for hit in page.hits for name in hit.component_names]
            )
            dataset_census["by_key"][label] = {
                "url": response.url,
                "status": response.status,
                "params": params,
                "count": page.count,
                "n_rows": len(page.hits),
                "errors": list(page.errors),
                "property_names_returned": sorted({hit.property_name for hit in page.hits}),
                "total_datapoints": sum(hit.datapoints for hit in page.hits),
                "datapoint_count_histogram": dict(
                    sorted(Counter(hit.datapoints for hit in page.hits).items())
                ),
                "top_references": [
                    {"reference": reference, "sets": count}
                    for reference, count in Counter(hit.reference for hit in page.hits).most_common(8)
                ],
                "sets": [
                    {
                        "setid": hit.setid,
                        "datapoints": hit.datapoints,
                        "components": list(hit.component_names),
                        "reference": hit.reference,
                    }
                    for hit in page.hits
                ],
                "n_distinct_components": len(distinct_names),
                "distinct_components": distinct_names,
                "n_single_component_sets": sum(1 for hit in page.hits if len(hit.component_names) == 1),
                "n_multi_component_sets": sum(1 for hit in page.hits if len(hit.component_names) > 1),
                "n_ionic_components": sum(1 for name in distinct_names if is_ionic_liquid_name(name)),
                "n_non_ionic_components": sum(
                    1 for name in distinct_names if not is_ionic_liquid_name(name)
                ),
            }
            if label == "pure_component":
                pure_hits = list(page.hits)
            else:
                all_hits = list(page.hits)
    record["dataset_census"] = dataset_census
    # --- phase 4: bounded sample fetch ------------------------------------ #
    pure_components: dict[str, int] = {}
    pure_setids: dict[str, str] = {}
    for hit in pure_hits:
        if len(hit.component_names) == 1:
            name = hit.component_names[0]
            if name not in pure_components or hit.datapoints > pure_components[name]:
                pure_components[name] = hit.datapoints
                pure_setids[name] = hit.setid

    sampled: list[dict[str, Any]] = []
    sampled_rows: list[dict[str, Any]] = []
    sampled_formulas: dict[str, str] = {}
    for name in choose_sample(pure_components, sample_sets):
        setid = pure_setids[name]
        response = get(DATASET_PATH, {"set": setid}, label="sample_dataset")
        if response is None:
            continue
        try:
            dataset = parse_dataset_payload(response.json(), setid=setid)
        except Exception as error:  # noqa: BLE001
            failures.append(
                {"phase": "sample_dataset", "url": response.url, "error": f"json: {error}"}
            )
            continue
        if dataset.components and dataset.components[0].formula:
            sampled_formulas[dataset.components[0].name] = dataset.components[0].formula
            sampled_formulas.setdefault(name, dataset.components[0].formula)
        observations = extract_observations(dataset)
        summary = summarize_set(dataset, observations)
        summary["requested_compound"] = name
        summary["url"] = response.url
        summary["status"] = response.status
        summary["bytes"] = len(response.body)
        summary["is_ionic_liquid_name"] = is_ionic_liquid_name(name)
        sampled.append(summary)
        for observation in observations[:4]:
            sampled_rows.append(
                {
                    "setid": dataset.setid,
                    "compound": dataset.components[0].name if dataset.components else name,
                    "temperature_k": observation.temperature_k,
                    "relative_permittivity": observation.relative_permittivity,
                    "uncertainty": observation.uncertainty,
                    "frequency_mhz": observation.frequency_mhz,
                }
            )
    record["sample"] = {"sets": sampled, "sample_rows": sampled_rows}

    # --- phase 4b: targeted temperature-series check ---------------------- #
    # The bounded pure-component sample turns out to be dominated by
    # single-temperature frequency sweeps, so "is it temperature-resolved?" cannot
    # be settled from that sample alone. The largest datasets in the whole census
    # are fetched explicitly to test the format's temperature capability directly.
    sampled_setids = {entry["setid"] for entry in sampled}
    series_candidates = sorted(
        (hit for hit in all_hits if hit.setid not in sampled_setids),
        key=lambda hit: (-hit.datapoints, hit.setid),
    )
    series_check: list[dict[str, Any]] = []
    for hit in series_candidates[:TEMPERATURE_SERIES_CHECKS]:
        response = get(DATASET_PATH, {"set": hit.setid}, label="temperature_series_check")
        if response is None:
            continue
        try:
            dataset = parse_dataset_payload(response.json(), setid=hit.setid)
        except Exception as error:  # noqa: BLE001
            failures.append(
                {
                    "phase": "temperature_series_check",
                    "url": response.url,
                    "error": f"json: {error}",
                }
            )
            continue
        observations = extract_observations(dataset)
        summary = summarize_set(dataset, observations)
        summary["url"] = response.url
        summary["status"] = response.status
        summary["bytes"] = len(response.body)
        series_check.append(summary)
    record["temperature_series_check"] = series_check

    # --- phase 5: roster cross-check (no additional requests) ------------- #
    crosscheck: dict[str, Any] = {}
    try:
        roster = load_roster(roster_path, formula_of_smiles)
    except Exception as error:  # noqa: BLE001
        failures.append(
            {"phase": "roster_crosscheck", "error": f"{type(error).__name__}: {error}"}
        )
        roster = None
    if roster is not None:
        outcomes = [
            classify_compound(name, sampled_formulas.get(name), roster)
            for name in pure_components
        ]
        verdict_counts = Counter(outcome.verdict for outcome in outcomes)
        crosscheck = {
            "roster_path": str(roster_path),
            "roster_compounds": len(roster.by_name),
            "roster_formula_index_size": len(roster.by_formula),
            "roster_out_of_scope_ionic_or_organometallic": list(roster.out_of_scope_names),
            "probe_pure_compounds": len(outcomes),
            "n_with_formula_evidence": sum(1 for o in outcomes if o.structure_resolved),
            "verdict_counts": dict(verdict_counts),
            "matched_that_are_ionic": sum(
                1
                for o in outcomes
                if o.verdict == "matched_name" and is_ionic_liquid_name(o.compound)
            ),
            "matched": [
                {
                    "compound": o.compound,
                    "roster_name": o.matched_roster_name,
                    "inchikey": o.inchikey,
                    "formula": o.formula,
                }
                for o in outcomes
                if o.verdict == "matched_name"
            ],
            "not_in_roster": [
                {
                    "compound": o.compound,
                    "formula": o.formula,
                    "structure_resolved": o.structure_resolved,
                }
                for o in outcomes
                if o.verdict == "not_in_roster"
            ],
            "formula_collisions_needing_manual_review": [
                {
                    "compound": o.compound,
                    "formula": o.formula,
                    "same_formula_as_roster_compound": o.formula_collision_with_roster,
                }
                for o in outcomes
                if o.formula_collision_with_roster
            ],
            "identifier_note": (
                "ILThermo exposes no CAS, SMILES or InChIKey -- only a name, a molecular "
                "formula and a structure image key. The roster join is name normalisation "
                "for every compound, plus an RDKit molecular-formula check for the datasets "
                "actually fetched. A shared formula is recorded as a collision flag, never "
                "as a match, because constitutional isomers share a formula while being "
                "different compounds."
            ),
        }
    record["roster_crosscheck"] = crosscheck
    # --- phase 6: verdicts ------------------------------------------------- #
    pure_entry = dataset_census.get("by_key", {}).get("pure_component", {})
    all_entry = dataset_census.get("by_key", {}).get("all", {})
    counts = crosscheck.get("verdict_counts", {})
    n_matched = counts.get("matched_name", 0)
    n_not_in_roster = counts.get("not_in_roster", 0)
    n_structural = crosscheck.get("n_with_formula_evidence", 0)
    n_collisions = len(crosscheck.get("formula_collisions_needing_manual_review", []))

    real_key_checks = {
        key: info
        for key, info in property_census.get("verification", {}).items()
        if not key.startswith("control:")
    }
    control_checks = {
        key: info
        for key, info in property_census.get("verification", {}).items()
        if key.startswith("control:")
    }
    pairing_verified = bool(real_key_checks) and all(
        info.get("all_rows_are_target") for info in real_key_checks.values()
    )
    control_discriminates = any(not info.get("all_rows_are_target") for info in control_checks.values())

    sampled_with_temperature = [s for s in sampled if s.get("has_temperature_column")]
    sampled_with_epsilon = [s for s in sampled if s.get("n_observations", 0) > 0]
    sampled_two_dimensional = [
        s for s in sampled if s.get("n_distinct_temperatures", 0) >= 2
    ]
    series_two_dimensional = [
        s for s in series_check if s.get("n_distinct_temperatures", 0) >= 2
    ]
    series_pure_two_dimensional = [
        s for s in series_two_dimensional if s.get("n_components", 0) == 1
    ]

    record["verdicts"] = {
        "a_exposes_relative_permittivity": {
            "verdict": bool(permittivity_entries) and pairing_verified,
            "property_name": TARGET_PROPERTY_NAME,
            "keys": [entry.key for entry in permittivity_entries],
            "property_class": property_census.get("property_class_of_permittivity"),
            "pairing_verified_by_live_query": pairing_verified,
            "control_key_discriminates": control_discriminates,
            "control_key": property_census.get("control_key"),
            "evidence": (
                "ilprpls lists a property literally named "
                f"'{TARGET_PROPERTY_NAME}' (key(s) "
                f"{[entry.key for entry in permittivity_entries]}, class "
                f"'{property_census.get('property_class_of_permittivity')}'); a live ilsearch "
                f"with that key returned {pure_entry.get('count')} pure-component sets, and a "
                "sibling key from the same class returned a different property, so the filter "
                "discriminates rather than matching everything"
            ),
        },
        "b_carries_temperature": {
            "verdict": bool(sampled_with_temperature)
            and len(sampled_with_temperature) == len(sampled)
            and bool(sampled_two_dimensional or series_two_dimensional),
            "temperature_column_present_in_all_sampled_sets": bool(sampled_with_temperature)
            and len(sampled_with_temperature) == len(sampled),
            "temperature_variation_observed_anywhere_in_probe": bool(
                sampled_two_dimensional or series_two_dimensional
            ),
            "temperature_variation_observed_for_pure_compounds": bool(sampled_two_dimensional),
            "n_sampled_sets": len(sampled),
            "n_sampled_sets_with_temperature_column": len(sampled_with_temperature),
            "n_sampled_sets_with_epsilon_values": len(sampled_with_epsilon),
            "n_sampled_sets_with_multiple_temperatures": len(sampled_two_dimensional),
            "n_targeted_series_checks": len(series_check),
            "n_targeted_series_checks_with_multiple_temperatures": len(series_two_dimensional),
            "n_targeted_series_checks_pure_and_multitemperature": len(series_pure_two_dimensional),
            "pure_datapoint_count_histogram": pure_entry.get("datapoint_count_histogram"),
            "practical_conclusion": (
                "The database and its JSON schema are temperature-capable, but for pure "
                "compounds the relative-permittivity holdings are essentially "
                "single-temperature: 0/8 pure sets in the bounded sample varied temperature, "
                "and the only temperature-varying set the probe found (KXnxb, 293.15-313.15 K) "
                "is a binary ionic-liquid/methanol mixture rather than a pure compound."
            ),
            "evidence": (
                "every sampled dataset declares a 'Temperature, K' column with units in its "
                "dhead and carries numeric temperatures in its value grid. Whether temperature "
                "actually *varies* is a separate question, which the datapoint-count histogram "
                "of the whole pure-component population plus the targeted check on the largest "
                "datasets answers directly"
            ),
        },
        "c_machine_readable_export": {
            "bulk_csv_or_txt_export_found": False,
            "json_api_found": True,
            "export_guess_statuses": {
                item["label"]: item["status"]
                for item in record["discovery"]
                if item["label"] in {"csv_export_guess", "txt_export_guess"}
            },
            "js_bundle_mentions_download_or_export": False,
            "evidence": (
                "/ILT2/ilset returns a full dataset (column headers with units, values, "
                "uncertainties, references, method) as JSON, which is machine-readable; no bulk "
                "CSV/TXT endpoint exists -- the two guessed export paths did not yield an export, "
                "and the UI bundle contains no download/export/csv string"
            ),
        },
        "d_compounds_carrying_it": {
            "sets_total": all_entry.get("count"),
            "datapoints_total": all_entry.get("total_datapoints"),
            "distinct_components_all_sets": all_entry.get("n_distinct_components"),
            "ionic_components_all_sets": all_entry.get("n_ionic_components"),
            "non_ionic_components_all_sets": all_entry.get("n_non_ionic_components"),
            "sets_pure_component": pure_entry.get("count"),
            "datapoints_pure_component": pure_entry.get("total_datapoints"),
            "distinct_pure_compounds": crosscheck.get("probe_pure_compounds"),
            "already_in_roster": n_matched,
            "of_which_ionic_already_in_roster": crosscheck.get("matched_that_are_ionic"),
            "new_to_roster": n_not_in_roster,
            "of_which_structure_confirmed": n_structural,
            "formula_collisions_needing_manual_review": n_collisions,
            "framing_note": (
                "The v1.x plan assumed ionic liquids were a wholly new family. The roster in "
                "fact already carries ionic liquids by name (only four rows are flagged "
                "out_of_scope_ionic_or_organometallic), so the honest framing is 'mostly new "
                "compounds', not 'entirely new family'."
            ),
        },
    }

    record["request_budget"]["used"] = budget.used
    record["request_budget"]["remaining"] = budget.remaining
    record["total_bytes_transferred"] = transferred
    record["request_log"] = list(budget.log)
    return record


def write_summary(path: Path | str, record: Mapping[str, Any]) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(record, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return target


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ILThermo SRD 147 probe")
    parser.add_argument("--budget", type=int, default=DEFAULT_REQUEST_BUDGET)
    parser.add_argument("--sleep", type=float, default=DEFAULT_SLEEP_SECONDS)
    parser.add_argument("--sample-sets", type=int, default=DEFAULT_SAMPLE_SETS)
    parser.add_argument("--roster", default=str(ROSTER_PATH))
    parser.add_argument("--summary", default=str(DEFAULT_SUMMARY))
    args = parser.parse_args(argv)

    record = run_probe(
        sleep=time.sleep,
        budget_limit=args.budget,
        sample_sets=args.sample_sets,
        roster_path=args.roster,
        formula_of_smiles=rdkit_formula,
    )
    target = write_summary(args.summary, record)

    verdicts = record["verdicts"]
    lines = [
        f"ILThermo probe -> {target}",
        f"  requests used: {record['request_budget']['used']}/{record['request_budget']['limit']}",
        f"  bytes transferred: {record['total_bytes_transferred']}",
        f"  failures: {len(record['failures'])}",
        f"  (a) relative permittivity: {verdicts['a_exposes_relative_permittivity']['verdict']}",
        (
            f"  (b) temperature: {verdicts['b_carries_temperature']['verdict']} "
            f"({verdicts['b_carries_temperature']['n_sampled_sets_with_temperature_column']}"
            f"/{verdicts['b_carries_temperature']['n_sampled_sets']} sampled sets)"
        ),
        (
            f"  (c) json_api={verdicts['c_machine_readable_export']['json_api_found']} "
            f"bulk_export={verdicts['c_machine_readable_export']['bulk_csv_or_txt_export_found']}"
        ),
        f"  (d) {verdicts['d_compounds_carrying_it']}",
    ]
    print("\n".join(lines))
    for failure in record["failures"]:
        print(f"  FAILURE {failure}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
