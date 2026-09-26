"""Turn the low-frequency-gate compounds into structurally complete rows.

Why this file exists
--------------------
probes/dielectric_lowfreq_gate_probe.py recovered 435 low-frequency (1 kHz-1 MHz)
relative-permittivity rows for 50 pure compounds that
data/processed/dielectric_observations_v11.csv cannot see, because the frozen
v0.3 admission gate takes zero-frequency rows only. Thirty-nine of those 50
compounds are not in data/dielectric_v03.csv, and their `smiles` column in the
candidate table is empty: they are observations, not modelling samples.

This probe closes the structure gap with the same free source the ILThermo line
used -- PubChem PUG-REST -- but keyed on InChIKey rather than on a display name,
because the candidate table already carries an exact InChIKey. Keyed lookup
removes the name-normalisation failure mode entirely.

Four honesty rules, enforced in code rather than in prose:

1. A hit is a hit for the InChIKey that was requested. The lookup path is the
   key itself, so there is no name spelling to repair and no isomer to guess.
2. Two different structures returned for one InChIKey are recorded as
   `ambiguous` with the competing SMILES in `notes`; nothing is picked silently.
   An unresolved compound stays unresolved with its HTTP status attached.
3. The candidate table ships no molecular formula column, so the formula
   cross-check is RDKit(SMILES) versus PubChem's own reported MolecularFormula,
   plus -- where the compound occurs in the ThermoML cache -- versus the formula
   ThermoML itself carries. When neither is available the cell reads
   `not_checked`, never `match`.
4. `needs_xtb` means "structure is in hand but no geometry/descriptor set exists
   yet". It is computed from the frozen feature table, not asserted. A compound
   whose descriptors are already frozen is *not* marked as needing xTB, even
   though it still has to be admitted to the observation table by other means.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
import urllib.parse
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import requests

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:  # allow both script and package import
    sys.path.insert(0, str(REPOSITORY_ROOT))

from probes.ilthermo_probe import (
    BudgetExhausted,
    HttpResponse,
    RequestBudget,
    formula_signature,
    http_get_with_backoff,
    rdkit_formula,
    write_summary,
)

USER_AGENT = "electrolyte-ml-research/1.0 (low-frequency gate -> PubChem InChIKey resolution)"
PUBCHEM_INCHIKEY_URL = "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/inchikey"
PUBCHEM_PROPERTIES = "SMILES,ConnectivitySMILES,MolecularFormula"
HTTP_TIMEOUT_SECONDS = 60

DEFAULT_REQUEST_BUDGET = 120
DEFAULT_SLEEP_SECONDS = 0.30
BACKOFF_SECONDS = (5.0, 15.0)
MAX_BACKOFF_SECONDS = 45.0

DATA_DIR = REPOSITORY_ROOT / "data"
DEFAULT_CANDIDATES_CSV = DATA_DIR / "processed" / "dielectric_lowfreq_candidates.csv"
DEFAULT_RAW_CSV = DATA_DIR / "processed" / "dielectric_raw.csv"
DEFAULT_OBSERVATIONS_CSV = DATA_DIR / "processed" / "dielectric_observations_v11.csv"
DEFAULT_FEATURES_CSV = DATA_DIR / "processed" / "dielectric_physical_features_v03.csv"
DEFAULT_ROSTER_CSV = DATA_DIR / "dielectric_v03.csv"
DEFAULT_OUTPUT_CSV = DATA_DIR / "processed" / "dielectric_lowfreq_structures.csv"
DEFAULT_SUMMARY_JSON = REPOSITORY_ROOT / "probes" / "dielectric_lowfreq_structures_summary.json"

ACCEPTED_GATE_PREFIX = "accepted"

RESOLVED = "resolved"
UNRESOLVED = "unresolved"
AMBIGUOUS = "ambiguous"
NOT_QUERIED = "not_queried"

RESOLUTION_STATUSES: tuple[str, ...] = (RESOLVED, UNRESOLVED, AMBIGUOUS, NOT_QUERIED)

SOURCE_CANDIDATE_TABLE = "candidate_table"
SOURCE_PUBCHEM = "pubchem"
SOURCE_NONE = ""

CSV_FIELDS: tuple[str, ...] = (
    "inchikey",
    "name",
    "resolved_smiles",
    "resolution_status",
    "resolution_source",
    "pubchem_cid",
    "pubchem_formula",
    "thermoml_formula",
    "rdkit_formula",
    "formula_check",
    "inchikey_roundtrip",
    "thermoml_formula_match",
    "in_roster",
    "roster_smiles",
    "roster_smiles_match",
    "has_v11_rows",
    "n_v11_rows",
    "v11_absence_reason",
    "n_accepted_lowfreq_rows",
    "lowfreq_gates",
    "temperature_min_K",
    "temperature_max_K",
    "temperature_span_K",
    "has_frozen_physical_features",
    "needs_xtb",
    "needs_manual_review",
    "source_url",
    "notes",
)

# --------------------------------------------------------------------------- #
# Inputs
# --------------------------------------------------------------------------- #


def read_csv_rows(path: Path | str) -> tuple[list[str], list[dict[str, str]]]:
    with open(path, encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or ()), list(reader)


def _optional_float(value: Any) -> float | None:
    text = ("" if value is None else str(value)).strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def bool_text(value: bool) -> str:
    return "true" if value else "false"


def format_number(value: float | None, digits: int = 4) -> str:
    if value is None:
        return ""
    text = f"{value:.{digits}f}".rstrip("0").rstrip(".")
    return text or "0"


@dataclass(frozen=True)
class AcceptedCompound:
    """One compound the low-frequency gate let through, deduplicated."""

    inchikey: str
    name: str
    candidate_smiles: str
    in_roster: bool
    n_accepted_rows: int
    gates: tuple[str, ...]
    temperature_min_K: float | None
    temperature_max_K: float | None
    source_dois: tuple[str, ...]

    @property
    def temperature_span_K(self) -> float | None:
        if self.temperature_min_K is None or self.temperature_max_K is None:
            return None
        return round(self.temperature_max_K - self.temperature_min_K, 4)


def load_accepted_compounds(path: Path | str = DEFAULT_CANDIDATES_CSV) -> list[AcceptedCompound]:
    """Deduplicate the accepted low-frequency rows into one record per compound."""
    _, rows = read_csv_rows(path)
    grouped: dict[str, dict[str, Any]] = {}
    for row in rows:
        gate = (row.get("gate") or "").strip()
        if not gate.startswith(ACCEPTED_GATE_PREFIX):
            continue
        key = (row.get("inchikey") or "").strip()
        if not key:
            continue
        entry = grouped.setdefault(
            key,
            {
                "names": Counter(),
                "smiles": [],
                "in_roster": (row.get("in_roster") or "").strip().lower() == "true",
                "gates": set(),
                "dois": set(),
                "temperatures": [],
                "n_rows": 0,
            },
        )
        entry["n_rows"] += 1
        name = (row.get("name") or "").strip()
        if name:
            entry["names"][name] += 1
        smiles = (row.get("smiles") or "").strip()
        if smiles and smiles not in entry["smiles"]:
            entry["smiles"].append(smiles)
        entry["gates"].add(gate)
        doi = (row.get("source_doi") or "").strip()
        if doi:
            entry["dois"].add(doi)
        temperature = _optional_float(row.get("T_K"))
        if temperature is not None:
            entry["temperatures"].append(temperature)

    compounds: list[AcceptedCompound] = []
    for key, entry in grouped.items():
        names = entry["names"]
        name = min(names.items(), key=lambda item: (-item[1], item[0]))[0] if names else ""
        temperatures = entry["temperatures"]
        compounds.append(
            AcceptedCompound(
                inchikey=key,
                name=name,
                candidate_smiles=entry["smiles"][0] if entry["smiles"] else "",
                in_roster=entry["in_roster"],
                n_accepted_rows=entry["n_rows"],
                gates=tuple(sorted(entry["gates"])),
                temperature_min_K=min(temperatures) if temperatures else None,
                temperature_max_K=max(temperatures) if temperatures else None,
                source_dois=tuple(sorted(entry["dois"])),
            )
        )
    compounds.sort(key=lambda compound: compound.inchikey)
    return compounds


@dataclass(frozen=True)
class RawEvidence:
    """What the ThermoML cache itself says about one compound."""

    inchikey: str
    n_rows: int
    n_zero_frequency_total: int
    n_zero_frequency_pure: int
    n_zero_frequency_mixture: int
    n_frequency_dependent_pure: int
    n_frequency_dependent_mixture: int
    pure_frequencies_mhz: tuple[str, ...]
    thermoml_formula: str


def load_raw_doi_set(path: Path | str = DEFAULT_RAW_CSV) -> set[str]:
    _, rows = read_csv_rows(path)
    return {
        (row.get("doi") or "").strip().lower() for row in rows if (row.get("doi") or "").strip()
    }


def scan_raw_evidence(
    path: Path | str = DEFAULT_RAW_CSV,
    *,
    keys: Iterable[str] | None = None,
) -> dict[str, RawEvidence]:
    """Count the raw rows that contain each compound, in any component slot.

    `primary_inchi_key` only carries component 0, so a mixture's non-first
    components would be invisible. Membership is therefore decided from
    `components_json`, which is the only complete view of a raw row.
    """
    wanted = {key for key in keys} if keys is not None else None
    tallies: dict[str, dict[str, Any]] = {}
    _, rows = read_csv_rows(path)
    for row in rows:
        try:
            components = json.loads(row.get("components_json") or "[]")
        except (TypeError, ValueError):
            components = []
        if not isinstance(components, list):
            continue
        is_pure = (row.get("is_pure") or "").strip().lower() == "true"
        family = (row.get("property_family") or "").strip()
        frequency = (row.get("frequency_mhz") or "").strip()
        for component in components:
            if not isinstance(component, Mapping):
                continue
            key = (component.get("standard_inchi_key") or "").strip()
            if not key or (wanted is not None and key not in wanted):
                continue
            entry = tallies.setdefault(
                key,
                {
                    "n_rows": 0,
                    "zero_total": 0,
                    "zero_pure": 0,
                    "zero_mixture": 0,
                    "freq_pure": 0,
                    "freq_mixture": 0,
                    "frequencies": set(),
                    "formulas": Counter(),
                },
            )
            entry["n_rows"] += 1
            formula = (component.get("formula") or "").strip()
            if formula:
                entry["formulas"][formula] += 1
            if family == "zero_frequency":
                entry["zero_total"] += 1
                entry["zero_pure" if is_pure else "zero_mixture"] += 1
            elif family == "frequency_dependent":
                entry["freq_pure" if is_pure else "freq_mixture"] += 1
            if is_pure and family == "frequency_dependent" and frequency:
                entry["frequencies"].add(frequency)

    evidence: dict[str, RawEvidence] = {}
    for key, entry in tallies.items():
        formula = ""
        if entry["formulas"]:
            formula = min(entry["formulas"].items(), key=lambda item: (-item[1], item[0]))[0]
        evidence[key] = RawEvidence(
            inchikey=key,
            n_rows=entry["n_rows"],
            n_zero_frequency_total=entry["zero_total"],
            n_zero_frequency_pure=entry["zero_pure"],
            n_zero_frequency_mixture=entry["zero_mixture"],
            n_frequency_dependent_pure=entry["freq_pure"],
            n_frequency_dependent_mixture=entry["freq_mixture"],
            pure_frequencies_mhz=tuple(sorted(entry["frequencies"])),
            thermoml_formula=formula,
        )
    return evidence


def load_observation_counts(
    path: Path | str = DEFAULT_OBSERVATIONS_CSV,
    *,
    keys: Iterable[str] | None = None,
) -> Counter[str]:
    _, rows = read_csv_rows(path)
    counter: Counter[str] = Counter()
    wanted = {key for key in keys} if keys is not None else None
    for row in rows:
        key = (row.get("inchikey") or "").strip()
        if not key or (wanted is not None and key not in wanted):
            continue
        counter[key] += 1
    return counter


@dataclass(frozen=True)
class RosterEntry:
    inchikey: str
    name: str
    smiles: str
    source_doi: str
    source_scope: str
    model_ready: bool
    temperature_K: float | None
    dielectric: float | None


def load_roster_entries(
    path: Path | str = DEFAULT_ROSTER_CSV,
    *,
    keys: Iterable[str],
) -> dict[str, RosterEntry]:
    wanted = {key for key in keys}
    _, rows = read_csv_rows(path)
    entries: dict[str, RosterEntry] = {}
    for row in rows:
        key = (row.get("inchikey") or "").strip()
        if key not in wanted or key in entries:
            continue
        entries[key] = RosterEntry(
            inchikey=key,
            name=(row.get("name") or "").strip(),
            smiles=(row.get("smiles") or "").strip(),
            source_doi=(row.get("source_doi") or "").strip(),
            source_scope=(row.get("source_scope") or "").strip(),
            model_ready=(row.get("model_ready") or "").strip().lower() == "true",
            temperature_K=_optional_float(row.get("T_K")),
            dielectric=_optional_float(row.get("dielectric")),
        )
    return entries


def load_feature_keys(
    path: Path | str = DEFAULT_FEATURES_CSV,
    *,
    keys: Iterable[str] | None = None,
) -> set[str]:
    _, rows = read_csv_rows(path)
    wanted = {key for key in keys} if keys is not None else None
    found: set[str] = set()
    for row in rows:
        key = (row.get("inchikey") or "").strip()
        if key and (wanted is None or key in wanted):
            found.add(key)
    return found


def derive_absence_suffix(evidence: RawEvidence | None) -> str:
    """Name the ThermoML-side reason a compound produced no v11 row."""
    if evidence is None or evidence.n_rows == 0:
        return "thermoml_cache_does_not_mention_the_compound"
    if evidence.n_zero_frequency_total == 0:
        return "thermoml_has_no_zero_frequency_rows"
    if evidence.n_zero_frequency_pure == 0:
        return "thermoml_zero_frequency_rows_are_all_mixtures"
    return "thermoml_has_zero_frequency_pure_rows_but_none_were_admitted"


def build_absence_reason(
    *,
    has_v11_rows: bool,
    in_roster: bool,
    roster_entry: RosterEntry | None,
    raw_doi_set: set[str],
    evidence: RawEvidence | None,
) -> str:
    if has_v11_rows:
        return ""
    suffix = derive_absence_suffix(evidence)
    if not in_roster:
        return f"not_in_roster|{suffix}"
    doi = roster_entry.source_doi if roster_entry is not None else ""
    if not doi:
        return f"roster_value_source_unknown|{suffix}"
    where = "absent_from" if doi.lower() not in raw_doi_set else "present_in"
    return f"roster_value_source_{where}_thermoml_raw:{doi}|{suffix}"


# --------------------------------------------------------------------------- #
# PubChem PUG-REST (InChIKey -> SMILES + MolecularFormula)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class PubChemRecord:
    cid: str
    smiles: str
    connectivity_smiles: str
    formula: str

    def as_dict(self) -> dict[str, str]:
        return {
            "cid": self.cid,
            "smiles": self.smiles,
            "connectivity_smiles": self.connectivity_smiles,
            "formula": self.formula,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> PubChemRecord:
        return cls(
            cid=str(payload.get("cid") or ""),
            smiles=str(payload.get("smiles") or ""),
            connectivity_smiles=str(payload.get("connectivity_smiles") or ""),
            formula=str(payload.get("formula") or ""),
        )


def build_pubchem_url(inchikey: str) -> str:
    quoted = urllib.parse.quote(inchikey, safe="")
    return f"{PUBCHEM_INCHIKEY_URL}/{quoted}/property/{PUBCHEM_PROPERTIES}/JSON"


def parse_pubchem_payload(payload: Any) -> list[PubChemRecord]:
    """Read a PUG-REST PropertyTable payload; a Fault payload yields no records."""
    if not isinstance(payload, Mapping):
        return []
    table = payload.get("PropertyTable")
    if not isinstance(table, Mapping):
        return []
    properties = table.get("Properties")
    if not isinstance(properties, list):
        return []
    records: list[PubChemRecord] = []
    for entry in properties:
        if not isinstance(entry, Mapping):
            continue
        records.append(
            PubChemRecord(
                cid=str(entry.get("CID") or ""),
                smiles=str(entry.get("SMILES") or "").strip(),
                connectivity_smiles=str(entry.get("ConnectivitySMILES") or "").strip(),
                formula=str(entry.get("MolecularFormula") or "").strip(),
            )
        )
    return records


def fault_message(payload: Any) -> str:
    if isinstance(payload, Mapping):
        fault = payload.get("Fault")
        if isinstance(fault, Mapping):
            text = str(fault.get("Message") or fault.get("Details") or "").strip()
            if text:
                return " ".join(text.split())
    return ""


def canonical_smiles(smiles: str) -> str | None:
    """RDKit canonical SMILES, or None when RDKit is unavailable/unparseable."""
    if not smiles.strip():
        return None
    try:
        from rdkit import Chem, RDLogger
    except Exception:  # noqa: BLE001
        return None
    RDLogger.DisableLog("rdApp.*")
    molecule = Chem.MolFromSmiles(smiles)
    if molecule is None:
        return None
    return Chem.MolToSmiles(molecule)


def distinct_structures(records: Sequence[PubChemRecord]) -> list[str]:
    """Distinct SMILES across records, canonicalised when possible."""
    seen: list[str] = []
    for record in records:
        candidate = record.smiles or record.connectivity_smiles
        if not candidate:
            continue
        identity = canonical_smiles(candidate) or candidate
        if identity not in seen:
            seen.append(identity)
    return seen


def resolve_from_records(
    records: Sequence[PubChemRecord],
    *,
    fallback_smiles: str = "",
) -> tuple[str, str, str]:
    """Return (status, smiles, note) for the records returned for one InChIKey."""
    if not records:
        return (UNRESOLVED, fallback_smiles, "")
    structures = distinct_structures(records)
    if len(structures) > 1:
        return (
            AMBIGUOUS,
            fallback_smiles,
            "pubchem_returned_distinct_structures:" + ";".join(structures),
        )
    for record in records:
        candidate = record.smiles or record.connectivity_smiles
        if candidate:
            return (RESOLVED, candidate, "")
    return (UNRESOLVED, fallback_smiles, "")


def check_formula(smiles: str, reference_formula: str) -> tuple[str, str]:
    """Return (verdict, rdkit_formula) comparing RDKit(SMILES) with a reference."""
    if not smiles.strip():
        return ("not_checked_no_structure", "")
    computed = rdkit_formula(smiles)
    if not computed:
        return ("not_checked_rdkit_unparseable", "")
    if not reference_formula.strip():
        return ("not_checked_no_reference_formula", computed)
    if formula_signature(computed) == formula_signature(reference_formula):
        return ("match", computed)
    return (f"mismatch:{computed}!={reference_formula}", computed)


def check_roster_smiles(roster_smiles: str, resolved_smiles: str) -> str:
    """Compare a roster SMILES with the resolved one by canonical form."""
    if not roster_smiles.strip():
        return "no_roster_smiles"
    if not resolved_smiles.strip():
        return "no_resolved_smiles"
    left = canonical_smiles(roster_smiles)
    right = canonical_smiles(resolved_smiles)
    if left is None or right is None:
        return "not_comparable_rdkit_unavailable"
    return "match" if left == right else "mismatch"


def check_inchikey_roundtrip(inchikey: str, smiles: str) -> str:
    """Recompute the InChIKey from the resolved SMILES and compare it to the query.

    This is the strongest identity check available offline: an InChIKey search
    that returns a structure whose recomputed InChIKey is the query itself is
    self-consistent by construction.
    """
    if not smiles.strip():
        return "not_checked_no_structure"
    if not inchikey.strip():
        return "not_checked_no_input_key"
    try:
        from rdkit import Chem, RDLogger
    except Exception:  # noqa: BLE001
        return "not_checked_rdkit_unavailable"
    RDLogger.DisableLog("rdApp.*")
    molecule = Chem.MolFromSmiles(smiles)
    if molecule is None:
        return "unparseable_smiles"
    try:
        computed = Chem.MolToInchiKey(molecule)
    except Exception:  # noqa: BLE001
        return "not_checked_inchi_unavailable"
    if not computed:
        return "not_checked_inchi_unavailable"
    return "match" if computed == inchikey else f"mismatch:{computed}"


def fetch_pubchem_records(
    http_get: Callable[..., HttpResponse],
    inchikey: str,
    *,
    budget: RequestBudget,
    sleep: Callable[[float], None] = time.sleep,
    backoff: Sequence[float] = BACKOFF_SECONDS,
    ceiling: float = MAX_BACKOFF_SECONDS,
) -> tuple[list[PubChemRecord], int, str]:
    """Look one InChIKey up at PubChem; return (records, http_status, note)."""
    url = build_pubchem_url(inchikey)
    try:
        response = http_get_with_backoff(
            http_get,
            url,
            None,
            budget=budget,
            sleep=sleep,
            backoff=backoff,
            ceiling=ceiling,
        )
    except BudgetExhausted as error:
        return ([], 0, f"budget_exhausted:{error}")
    if response.status != 200:
        return ([], response.status, f"http_status_{response.status}")
    try:
        payload = json.loads(response.body.decode("utf-8", errors="replace"))
    except ValueError:
        return ([], response.status, "payload_not_json")
    records = parse_pubchem_payload(payload)
    if not records:
        message = fault_message(payload)
        if message:
            return ([], response.status, f"no_property_table:{message}")
        return ([], response.status, "no_property_table")
    return (records, response.status, "")


def default_http_get(url: str, params: Mapping[str, str] | None = None) -> HttpResponse:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
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


def read_facts_replay(path: Path | str) -> dict[str, dict[str, Any]]:
    """Replay the `pubchem_records` block of an earlier summary (zero requests)."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    block = payload.get("pubchem_records")
    if not isinstance(block, Mapping):
        raise TypeError(f"{path} has no pubchem_records block to replay")
    replay: dict[str, dict[str, Any]] = {}
    for key, value in block.items():
        if not isinstance(value, Mapping):
            continue
        records = value.get("records") or []
        replay[str(key)] = {
            "status": int(value.get("status") or 0),
            "note": str(value.get("note") or ""),
            "records": [
                PubChemRecord.from_dict(record) for record in records if isinstance(record, Mapping)
            ],
        }
    return replay


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #


@dataclass
class RunState:
    rows: list[dict[str, str]] = field(default_factory=list)
    pubchem_records: dict[str, dict[str, Any]] = field(default_factory=dict)
    failures: list[dict[str, Any]] = field(default_factory=list)
    status_counts: Counter = field(default_factory=Counter)


def resolve_one(
    *,
    compound: AcceptedCompound,
    key: str,
    index: int,
    http_get: Callable[..., HttpResponse],
    budget: RequestBudget,
    sleep: Callable[[float], None],
    delay_seconds: float,
    offline: bool,
    replay_entry: Mapping[str, Any] | None,
) -> tuple[str, str, str, list[PubChemRecord], int, str]:
    """Resolve one compound. Returns (status, smiles, source, records, http, note)."""
    records: list[PubChemRecord] = []
    http_status = 0
    note = ""
    if offline:
        smiles = compound.candidate_smiles
        status = RESOLVED if smiles else NOT_QUERIED
        source = SOURCE_CANDIDATE_TABLE if smiles else SOURCE_NONE
        return (status, smiles, source, records, 0, "offline_no_network")

    if replay_entry is not None:
        records = list(replay_entry.get("records") or [])
        http_status = int(replay_entry.get("status") or 0)
        note = str(replay_entry.get("note") or "")
    else:
        if index:
            sleep(delay_seconds)
        records, http_status, note = fetch_pubchem_records(
            http_get, key, budget=budget, sleep=sleep
        )

    status, smiles, record_note = resolve_from_records(records)
    note = ";".join(part for part in (note, record_note) if part)
    if smiles:
        return (status, smiles, SOURCE_PUBCHEM, records, http_status, note)
    fallback = compound.candidate_smiles
    if fallback:
        return (
            RESOLVED if status != AMBIGUOUS else status,
            fallback,
            SOURCE_CANDIDATE_TABLE,
            records,
            http_status,
            note,
        )
    return (status, "", SOURCE_NONE, records, http_status, note)


def run_probe(
    *,
    http_get: Callable[..., HttpResponse],
    candidates_path: Path | str = DEFAULT_CANDIDATES_CSV,
    raw_path: Path | str = DEFAULT_RAW_CSV,
    observations_path: Path | str = DEFAULT_OBSERVATIONS_CSV,
    features_path: Path | str = DEFAULT_FEATURES_CSV,
    roster_path: Path | str = DEFAULT_ROSTER_CSV,
    offline: bool = False,
    request_budget_limit: int = DEFAULT_REQUEST_BUDGET,
    sleep: Callable[[float], None] = time.sleep,
    delay_seconds: float = DEFAULT_SLEEP_SECONDS,
    max_compounds: int | None = None,
    facts_replay: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    compounds = load_accepted_compounds(candidates_path)
    if max_compounds is not None:
        compounds = compounds[:max_compounds]
    keys = [compound.inchikey for compound in compounds]

    evidence = scan_raw_evidence(raw_path, keys=keys)
    raw_doi_set = load_raw_doi_set(raw_path)
    observation_counts = load_observation_counts(observations_path, keys=keys)
    roster_entries = load_roster_entries(roster_path, keys=keys)
    feature_keys = load_feature_keys(features_path, keys=keys)

    budget = RequestBudget(limit=request_budget_limit)
    status_histogram: Counter = Counter()
    state = RunState()

    for index, compound in enumerate(compounds):
        key = compound.inchikey
        replay_entry = facts_replay.get(key) if facts_replay is not None else None
        status, resolved_smiles, source, records, http_status, note = resolve_one(
            compound=compound,
            key=key,
            index=index,
            http_get=http_get,
            budget=budget,
            sleep=sleep,
            delay_seconds=delay_seconds,
            offline=offline,
            replay_entry=replay_entry,
        )
        if http_status:
            status_histogram[http_status] += 1
        if status not in RESOLUTION_STATUSES:
            status = UNRESOLVED
        state.status_counts[status] += 1

        reference_formula = records[0].formula if records else ""
        formula_verdict, computed_formula = check_formula(resolved_smiles, reference_formula)
        thermoml = evidence.get(key)
        thermoml_verdict = check_formula(
            resolved_smiles, thermoml.thermoml_formula if thermoml else ""
        )[0]
        roundtrip_verdict = check_inchikey_roundtrip(key, resolved_smiles)

        n_v11_rows = observation_counts.get(key, 0)
        has_v11_rows = n_v11_rows > 0
        has_features = key in feature_keys
        absence = build_absence_reason(
            has_v11_rows=has_v11_rows,
            in_roster=compound.in_roster,
            roster_entry=roster_entries.get(key),
            raw_doi_set=raw_doi_set,
            evidence=thermoml,
        )
        needs_xtb = bool(resolved_smiles) and not has_features
        # A compound that ThermoML carries as a pure zero-frequency row, yet
        # never reached the v11 table, is the one shape that would mean the
        # admission gate misfired rather than a source gap. Surface it.
        absence_anomaly = absence.endswith(
            "thermoml_has_zero_frequency_pure_rows_but_none_were_admitted"
        )
        needs_review = (
            status in (UNRESOLVED, AMBIGUOUS)
            or formula_verdict.startswith("mismatch")
            or roundtrip_verdict.startswith("mismatch")
            or absence_anomaly
        )

        roster_smiles = roster_entries[key].smiles if key in roster_entries else ""
        notes: list[str] = []
        if note:
            notes.append(note)
        if not compound.candidate_smiles:
            notes.append("candidate_table_smiles_empty")
        if thermoml is not None:
            notes.append(
                f"thermoml_rows={thermoml.n_rows}"
                f";zero_freq={thermoml.n_zero_frequency_total}"
                f"(pure={thermoml.n_zero_frequency_pure},mixture={thermoml.n_zero_frequency_mixture})"
                f";freq_dep_pure={thermoml.n_frequency_dependent_pure}"
            )
            if thermoml.pure_frequencies_mhz:
                notes.append("pure_freqs_mhz=" + ",".join(thermoml.pure_frequencies_mhz))
        if has_features:
            notes.append("frozen_physical_features_present")
        if status == RESOLVED and not has_v11_rows:
            notes.append("structurally_ready_but_not_admitted_to_the_v11_table")
        if thermoml_verdict.startswith("mismatch"):
            notes.append(f"thermoml_formula_check={thermoml_verdict}")

        state.rows.append(
            {
                "inchikey": key,
                "name": compound.name,
                "resolved_smiles": resolved_smiles,
                "resolution_status": status,
                "resolution_source": source,
                "pubchem_cid": records[0].cid if records else "",
                "pubchem_formula": reference_formula,
                "thermoml_formula": thermoml.thermoml_formula if thermoml else "",
                "rdkit_formula": computed_formula,
                "formula_check": formula_verdict,
                "inchikey_roundtrip": roundtrip_verdict,
                "thermoml_formula_match": thermoml_verdict,
                "in_roster": bool_text(compound.in_roster),
                "roster_smiles": roster_smiles,
                "roster_smiles_match": check_roster_smiles(roster_smiles, resolved_smiles),
                "has_v11_rows": bool_text(has_v11_rows),
                "n_v11_rows": str(n_v11_rows),
                "v11_absence_reason": absence,
                "n_accepted_lowfreq_rows": str(compound.n_accepted_rows),
                "lowfreq_gates": ";".join(compound.gates),
                "temperature_min_K": format_number(compound.temperature_min_K),
                "temperature_max_K": format_number(compound.temperature_max_K),
                "temperature_span_K": format_number(compound.temperature_span_K),
                "has_frozen_physical_features": bool_text(has_features),
                "needs_xtb": bool_text(needs_xtb),
                "needs_manual_review": bool_text(needs_review),
                "source_url": build_pubchem_url(key),
                "notes": ";".join(notes),
            }
        )
        state.pubchem_records[key] = {
            "status": http_status,
            "note": note,
            "records": [record.as_dict() for record in records],
        }
        if note.startswith(("http_status_", "payload_not_json")):
            state.failures.append({"inchikey": key, "note": note, "http_status": http_status})

    return summarise(
        state=state,
        compounds=compounds,
        evidence=evidence,
        roster_entries=roster_entries,
        feature_keys=feature_keys,
        budget=budget,
        status_histogram=status_histogram,
        offline=offline,
        facts_replay=facts_replay is not None,
    )


def summarise(
    *,
    state: RunState,
    compounds: Sequence[AcceptedCompound],
    evidence: Mapping[str, RawEvidence],
    roster_entries: Mapping[str, RosterEntry],
    feature_keys: set[str],
    budget: RequestBudget,
    status_histogram: Counter,
    offline: bool,
    facts_replay: bool,
) -> dict[str, Any]:
    rows = state.rows
    resolved = [row for row in rows if row["resolution_status"] == RESOLVED]
    structurally_complete = [row for row in resolved if row["resolved_smiles"]]
    formula_mismatches = [row for row in rows if row["formula_check"].startswith("mismatch")]
    new_compounds = [row for row in rows if row["in_roster"] == "false"]
    roster_compounds = [row for row in rows if row["in_roster"] == "true"]
    needs_xtb = [row for row in rows if row["needs_xtb"] == "true"]
    needs_review = [row for row in rows if row["needs_manual_review"] == "true"]
    absence_histogram = Counter(
        row["v11_absence_reason"] for row in rows if row["v11_absence_reason"]
    )
    roster_absence: dict[str, Any] = {}
    for row in roster_compounds:
        key = row["inchikey"]
        entry = roster_entries.get(key)
        raw = evidence.get(key)
        roster_absence[key] = {
            "name": row["name"],
            "roster_smiles": row["roster_smiles"],
            "roster_smiles_match": row["roster_smiles_match"],
            "roster_source_doi": entry.source_doi if entry else "",
            "roster_source_scope": entry.source_scope if entry else "",
            "model_ready": entry.model_ready if entry else False,
            "n_v11_rows": int(row["n_v11_rows"]),
            "v11_absence_reason": row["v11_absence_reason"],
            "thermoml_rows": raw.n_rows if raw else 0,
            "thermoml_zero_frequency_total": raw.n_zero_frequency_total if raw else 0,
            "thermoml_zero_frequency_pure": raw.n_zero_frequency_pure if raw else 0,
            "thermoml_zero_frequency_mixture": raw.n_zero_frequency_mixture if raw else 0,
            "n_accepted_lowfreq_rows": int(row["n_accepted_lowfreq_rows"]),
            "lowfreq_gates": row["lowfreq_gates"],
        }
    return {
        "generated_by": "probes/dielectric_lowfreq_structures.py",
        "mode": {"offline": offline, "facts_replay": facts_replay},
        "population": {
            "n_accepted_compounds": len(compounds),
            "n_new_to_roster": len(new_compounds),
            "n_in_roster": len(roster_compounds),
            "n_accepted_lowfreq_rows": sum(compound.n_accepted_rows for compound in compounds),
            "candidate_table_has_formula_column": False,
        },
        "resolution": {
            "status_counts": dict(state.status_counts),
            "n_structurally_complete": len(structurally_complete),
            "n_still_needing_manual_work": len(needs_review),
            "needs_manual_review": [
                {
                    "inchikey": row["inchikey"],
                    "name": row["name"],
                    "status": row["resolution_status"],
                    "note": row["notes"],
                }
                for row in needs_review
            ],
        },
        "formula_checks": {
            "match": len([row for row in rows if row["formula_check"] == "match"]),
            "mismatch": len(formula_mismatches),
            "mismatch_detail": [
                {"inchikey": row["inchikey"], "name": row["name"], "verdict": row["formula_check"]}
                for row in formula_mismatches
            ],
            "not_checked": len(
                [row for row in rows if row["formula_check"].startswith("not_checked")]
            ),
            "thermoml_match": len(
                [row for row in rows if row["thermoml_formula_match"] == "match"]
            ),
            "thermoml_mismatch": [
                {
                    "inchikey": row["inchikey"],
                    "name": row["name"],
                    "verdict": row["thermoml_formula_match"],
                }
                for row in rows
                if row["thermoml_formula_match"].startswith("mismatch")
            ],
            "reference": "PubChem MolecularFormula (the candidate table ships no formula column)",
        },
        "identity_checks": {
            "inchikey_roundtrip_match": len(
                [row for row in rows if row["inchikey_roundtrip"] == "match"]
            ),
            "inchikey_roundtrip_not_confirmed": [
                {
                    "inchikey": row["inchikey"],
                    "name": row["name"],
                    "verdict": row["inchikey_roundtrip"],
                }
                for row in rows
                if row["inchikey_roundtrip"] != "match"
            ],
            "method": "RDKit MolToInchiKey(resolved SMILES) versus the InChIKey that was queried",
        },
        "v11_absence": {
            "reason_counts": dict(absence_histogram),
            "roster_compounds": roster_absence,
        },
        "coverage": {
            "n_needs_xtb": len(needs_xtb),
            "needs_xtb": [{"inchikey": row["inchikey"], "name": row["name"]} for row in needs_xtb],
            "n_with_frozen_features": len(
                [row for row in rows if row["has_frozen_physical_features"] == "true"]
            ),
            "n_with_any_v11_row": len([row for row in rows if row["has_v11_rows"] == "true"]),
            "n_roster_smiles_match": len(
                [row for row in rows if row["roster_smiles_match"] == "match"]
            ),
            "n_roster_smiles_mismatch": len(
                [row for row in rows if row["roster_smiles_match"] == "mismatch"]
            ),
        },
        "requests": {
            "used": budget.used,
            "limit": budget.limit,
            "remaining": budget.remaining,
            "response_status_counts": dict(status_histogram),
        },
        "failures": state.failures,
        "pubchem_records": state.pubchem_records,
        "rows": rows,
    }


def write_csv(path: Path | str, rows: Sequence[Mapping[str, str]]) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="\n") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(CSV_FIELDS), lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return target


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Resolve the low-frequency gate compounds into modelling-ready structures"
    )
    parser.add_argument("--candidates", default=str(DEFAULT_CANDIDATES_CSV))
    parser.add_argument("--raw", default=str(DEFAULT_RAW_CSV))
    parser.add_argument("--observations", default=str(DEFAULT_OBSERVATIONS_CSV))
    parser.add_argument("--features", default=str(DEFAULT_FEATURES_CSV))
    parser.add_argument("--roster", default=str(DEFAULT_ROSTER_CSV))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_CSV))
    parser.add_argument("--summary", default=str(DEFAULT_SUMMARY_JSON))
    parser.add_argument("--budget", type=int, default=DEFAULT_REQUEST_BUDGET)
    parser.add_argument("--sleep", type=float, default=DEFAULT_SLEEP_SECONDS)
    parser.add_argument("--max-compounds", type=int, default=None)
    parser.add_argument(
        "--facts-from",
        default=None,
        help="replay the pubchem_records block of an earlier summary instead of re-querying",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="no network at all: use only the structures already on disk",
    )
    args = parser.parse_args(argv)

    record = run_probe(
        http_get=default_http_get,
        candidates_path=args.candidates,
        raw_path=args.raw,
        observations_path=args.observations,
        features_path=args.features,
        roster_path=args.roster,
        offline=args.offline,
        request_budget_limit=args.budget,
        delay_seconds=args.sleep,
        max_compounds=args.max_compounds,
        facts_replay=read_facts_replay(args.facts_from) if args.facts_from else None,
    )
    csv_path = write_csv(args.output, record["rows"])
    payload = {key: value for key, value in record.items() if key != "rows"}
    json_path = write_summary(args.summary, payload)

    resolution = record["resolution"]
    print(f"low-frequency structure resolution -> {csv_path}")
    print(f"  summary: {json_path}")
    print(
        f"  accepted compounds: {record['population']['n_accepted_compounds']} "
        f"(new to roster {record['population']['n_new_to_roster']}, "
        f"in roster {record['population']['n_in_roster']})"
    )
    print(
        f"  pubchem requests: {record['requests']['used']}/{record['requests']['limit']} "
        f"statuses={record['requests']['response_status_counts']}"
    )
    print(f"  resolution statuses: {resolution['status_counts']}")
    print(f"  structurally complete: {resolution['n_structurally_complete']}")
    print(f"  formula checks: {record['formula_checks']}")
    print(f"  needs xTB: {record['coverage']['n_needs_xtb']}")
    print(f"  needs manual review: {resolution['n_still_needing_manual_work']}")
    for failure in record["failures"][:10]:
        print(f"  FAILURE {failure}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
