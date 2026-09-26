"""Resolve ILThermo's pure compounds into structural identifiers (ILThermo -> PubChem).

Why this file exists
--------------------
probes/ilthermo_probe.py established that NIST ILThermo (SRD 147) carries a
'Relative permittivity' property (key TGKW) for 76 pure compounds, 58 of which are
new to data/dielectric_v03.csv. It also established the hard limitation: ILThermo
publishes no CAS, no SMILES and no InChIKey -- only a display name, a molecular
formula and a structure image key. A compound that cannot be named in
machine-readable form cannot enter a coverage list, so this probe closes that gap
with the only free structural source at hand: PubChem PUG-REST name lookup.

Three honesty rules are enforced in code, not just in prose:

1. A shared molecular formula is never a match. Constitutional isomers share a
   formula -- ILThermo's '1-methyl-3-propylimidazolium
   bis[(trifluoromethyl)sulfonyl]imide' versus the roster's
   '1-ethyl-2,3-dimethylimidazolium bis(trifluoromethylsulfonyl)imide' is exactly
   that case -- so a formula hit is recorded as a collision flag and routed to
   needs_manual_review.
2. The roster join is by InChIKey. Membership is decided by the resolved InChIKey,
   with the normalised name join kept as a secondary channel. This is what
   recovers compounds the roster stores under a different spelling.
3. Nothing is invented. An unresolved name stays unresolved with its reason
   attached (HTTP status, transport failure, ambiguity), and a temperature span is
   written only when a real ilset payload was read.

The temperature question is answered from the same ilset payloads that carry the
formulas, so the CSVs temperature columns are read, not assumed.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
import urllib.parse
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import requests

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:  # allow both script and package import
    sys.path.insert(0, str(REPOSITORY_ROOT))

from probes.ilthermo_probe import (
    DATASET_PATH,
    ORIGIN,
    BudgetExhausted,
    HttpResponse,
    RequestBudget,
    extract_observations,
    formula_signature,
    http_get_with_backoff,
    is_ionic_liquid_name,
    load_roster,
    normalize_name,
    parse_dataset_payload,
    rdkit_formula,
    write_summary,
)

USER_AGENT = "electrolyte-ml-research/1.0 (ILThermo->PubChem structure resolution)"
PUBCHEM_NAME_URL = "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name"
PUBCHEM_PROPERTIES = "SMILES,InChIKey,MolecularFormula"
HTTP_TIMEOUT_SECONDS = 60

DEFAULT_REQUEST_BUDGET = 120
DEFAULT_SET_BUDGET = 130
DEFAULT_SLEEP_SECONDS = 0.35
BACKOFF_SECONDS = (5.0, 15.0)
MAX_BACKOFF_SECONDS = 45.0

DEFAULT_PROBE_SUMMARY = REPOSITORY_ROOT / "probes" / "ilthermo_probe_summary.json"
ROSTER_PATH = REPOSITORY_ROOT / "data" / "dielectric_v03.csv"
DEFAULT_OUTPUT_CSV = REPOSITORY_ROOT / "data" / "processed" / "ilthermo_new_compounds.csv"
DEFAULT_SUMMARY_JSON = REPOSITORY_ROOT / "probes" / "ilthermo_structure_resolution_summary.json"

# A compound is only said to carry a temperature *series* when its span clears this
# cut. The duplicated ILThermo sets sit within 2 K of one another (296.15/298.10/
# 298.15 K), so a 5 K cut separates a real temperature dependence from set scatter.
SERIES_SPAN_THRESHOLD_K = 5.0

RESOLVED = "resolved"
UNRESOLVED = "unresolved"
AMBIGUOUS = "ambiguous"
NOT_QUERIED = "not_queried"

# ILThermo ships a few names with typos that defeat a PubChem name lookup. The
# repair is applied only to a secondary *lookup variant*; the recorded ILThermo
# name is never rewritten.
NAME_TYPO_FIXES: tuple[tuple[str, str], ...] = (
    ("trifluromethyl", "trifluoromethyl"),
    ("trifluromethanesulfonyl", "trifluoromethanesulfonyl"),
)

CSV_FIELDS: tuple[str, ...] = (
    "ilthermo_name",
    "ilthermo_formula",
    "formula_source",
    "resolved_inchikey",
    "resolved_smiles",
    "resolution_status",
    "resolution_source",
    "pubchem_cid",
    "pubchem_candidate_count",
    "formula_check",
    "rdkit_formula",
    "in_roster",
    "roster_join_basis",
    "roster_match_name",
    "roster_verdict",
    "roster_out_of_scope",
    "needs_manual_review",
    "needs_manual_review_reason",
    "roster_formula_collisions",
    "n_epsilon_sets",
    "n_datapoints",
    "temperature_span_K",
    "temperature_min_K",
    "temperature_max_K",
    "n_distinct_temperatures",
    "temperature_span_class",
    "n_sets_temperature_read",
    "is_ionic_liquid",
    "ilthermo_setids",
    "source_url",
    "notes",
)


@dataclass(frozen=True)
class PureCompound:
    """One pure compound of the ilsearch census, with its dataset accounting."""

    name: str
    setids: tuple[str, ...]
    n_epsilon_sets: int
    n_datapoints: int
    references: tuple[str, ...]
    is_ionic_liquid: bool


@dataclass(frozen=True)
class SetFacts:
    """What one ilset payload actually said (formula, temperatures, epsilon range)."""

    setid: str
    formula: str
    n_rows: int
    has_temperature_column: bool
    temperatures: tuple[float, ...]
    epsilon_min: float | None
    epsilon_max: float | None
    n_zero_frequency_rows: int
    n_frequency_rows_above_zero: int
    reference: str
    method: str
    url: str
    http_status: int


@dataclass(frozen=True)
class PubChemCandidate:
    cid: int | None
    smiles: str
    inchikey: str
    formula: str


@dataclass(frozen=True)
class Resolution:
    status: str
    inchikey: str = ""
    smiles: str = ""
    cid: int | None = None
    n_candidates: int = 0
    note: str = ""
    source: str = ""


@dataclass(frozen=True)
class RosterVerdict:
    in_roster: bool
    basis: str
    roster_name: str
    out_of_scope: bool


# --------------------------------------------------------------------------- #
# Pure helpers (offline unit-testable)
# --------------------------------------------------------------------------- #


def parse_probe_pure_compounds(summary: Mapping[str, Any]) -> list[PureCompound]:
    """One entry per pure compound in the probe's pure_component census."""
    census = summary.get("dataset_census")
    if not isinstance(census, Mapping):
        raise TypeError("probe summary carries no dataset_census block")
    by_key = census.get("by_key")
    if not isinstance(by_key, Mapping):
        raise TypeError("probe summary carries no dataset_census.by_key block")
    pure = by_key.get("pure_component")
    if not isinstance(pure, Mapping) or not isinstance(pure.get("sets"), list):
        raise TypeError("probe summary carries no pure_component set list")

    grouped: dict[str, dict[str, Any]] = {}
    for entry in pure["sets"]:
        if not isinstance(entry, Mapping):
            continue
        components = [str(name) for name in (entry.get("components") or [])]
        if len(components) != 1:
            continue
        record = grouped.setdefault(
            components[0], {"setids": [], "datapoints": 0, "references": []}
        )
        record["setids"].append(str(entry.get("setid") or ""))
        record["datapoints"] += int(entry.get("datapoints") or 0)
        reference = str(entry.get("reference") or "")
        if reference:
            record["references"].append(reference)

    compounds = [
        PureCompound(
            name=name,
            setids=tuple(record["setids"]),
            n_epsilon_sets=len(record["setids"]),
            n_datapoints=record["datapoints"],
            references=tuple(dict.fromkeys(record["references"])),
            is_ionic_liquid=is_ionic_liquid_name(name),
        )
        for name, record in grouped.items()
    ]
    compounds.sort(key=lambda compound: (-compound.n_epsilon_sets, compound.name))
    return compounds


def sample_formulas(summary: Mapping[str, Any]) -> dict[str, str]:
    """name -> formula, from whatever ilset payloads the probe kept (a few rows)."""
    formulas: dict[str, str] = {}
    sample = summary.get("sample")
    if not isinstance(sample, Mapping):
        return formulas
    for entry in sample.get("sets") or []:
        if not isinstance(entry, Mapping):
            continue
        for component in entry.get("components") or []:
            if not isinstance(component, Mapping):
                continue
            name = str(component.get("name") or "")
            formula = str(component.get("formula") or "")
            if name and formula:
                formulas.setdefault(name, formula)
    return formulas


def repair_lookup_name(name: str) -> str:
    """Typo-repaired spelling used only as a secondary PubChem lookup variant."""
    text = name
    for source, replacement in NAME_TYPO_FIXES:
        text = text.replace(source, replacement)
    return text


def lookup_variants(name: str) -> tuple[str, ...]:
    variants = [name.strip()]
    repaired = repair_lookup_name(name).strip()
    if repaired and repaired not in variants:
        variants.append(repaired)
    return tuple(variants)


def build_pubchem_url(name: str) -> str:
    encoded = urllib.parse.quote(name, safe="")
    return f"{PUBCHEM_NAME_URL}/{encoded}/property/{PUBCHEM_PROPERTIES}/JSON"


def parse_pubchem_payload(payload: Any) -> list[PubChemCandidate]:
    """Pull candidates out of a PUG-REST PropertyTable payload."""
    if not isinstance(payload, Mapping):
        return []
    table = payload.get("PropertyTable")
    if not isinstance(table, Mapping):
        return []
    properties = table.get("Properties")
    if not isinstance(properties, list):
        return []
    candidates: list[PubChemCandidate] = []
    for item in properties:
        if not isinstance(item, Mapping):
            continue
        smiles = str(
            item.get("SMILES")
            or item.get("ConnectivitySMILES")
            or item.get("CanonicalSMILES")
            or ""
        ).strip()
        inchikey = str(item.get("InChIKey") or "").strip()
        if not smiles and not inchikey:
            continue
        raw_cid = item.get("CID")
        cid: int | None = None
        if isinstance(raw_cid, bool):
            cid = None
        elif isinstance(raw_cid, int):
            cid = raw_cid
        elif str(raw_cid or "").strip().isdigit():
            cid = int(str(raw_cid).strip())
        candidates.append(
            PubChemCandidate(
                cid=cid,
                smiles=smiles,
                inchikey=inchikey,
                formula=str(item.get("MolecularFormula") or "").strip(),
            )
        )
    return candidates


def classify_candidates(
    candidates: Sequence[PubChemCandidate],
    expected_formula: str,
    formula_of_smiles: Callable[[str], str | None] = rdkit_formula,
) -> Resolution:
    """Decide what a name lookup actually proved.

    One distinct InChIKey means the name resolved. Several mean the name is
    ambiguous unless exactly one of them reproduces ILThermo's own molecular
    formula -- in which case the choice is recorded as a formula-based
    disambiguation rather than dressed up as a clean hit.
    """
    usable = [candidate for candidate in candidates if candidate.inchikey]
    if not usable:
        return Resolution(
            status=UNRESOLVED,
            n_candidates=len(candidates),
            note="PubChem returned no candidate carrying an InChIKey",
        )
    grouped: dict[str, list[PubChemCandidate]] = {}
    for candidate in usable:
        grouped.setdefault(candidate.inchikey, []).append(candidate)
    if len(grouped) == 1:
        inchikey, group = next(iter(grouped.items()))
        chosen = min(group, key=lambda candidate: len(candidate.smiles))
        return Resolution(
            status=RESOLVED,
            inchikey=inchikey,
            smiles=chosen.smiles,
            cid=chosen.cid,
            n_candidates=len(usable),
        )

    expected = formula_signature(expected_formula) if expected_formula else ""
    matched: list[tuple[str, PubChemCandidate]] = []
    if expected:
        for inchikey, group in grouped.items():
            chosen = min(group, key=lambda candidate: len(candidate.smiles))
            computed = formula_of_smiles(chosen.smiles) if chosen.smiles else None
            if computed and formula_signature(computed) == expected:
                matched.append((inchikey, chosen))
    if len(matched) == 1:
        inchikey, chosen = matched[0]
        others = ", ".join(sorted(key for key in grouped if key != inchikey))
        return Resolution(
            status=RESOLVED,
            inchikey=inchikey,
            smiles=chosen.smiles,
            cid=chosen.cid,
            n_candidates=len(usable),
            note=(
                "disambiguated by the ILThermo molecular formula; "
                f"other candidate InChIKeys: {others}"
            ),
        )
    return Resolution(
        status=AMBIGUOUS,
        n_candidates=len(usable),
        note=(
            f"{len(grouped)} distinct InChIKeys under this name and none uniquely "
            f"matches the ILThermo formula: {', '.join(sorted(grouped))}"
        ),
    )


def formula_check(ilthermo_formula: str, computed_formula: str | None) -> str:
    if not ilthermo_formula or not computed_formula:
        return "not_checked"
    return (
        "match"
        if formula_signature(ilthermo_formula) == formula_signature(computed_formula)
        else "mismatch"
    )


def roster_indexes(roster: Any) -> tuple[dict[str, str], dict[str, str]]:
    """InChIKey -> display name, and InChIKey skeleton -> display name."""
    by_inchikey: dict[str, str] = {}
    by_skeleton: dict[str, str] = {}
    for key, inchikey in roster.inchikey_by_name.items():
        display = roster.by_name.get(key, key)
        if not inchikey:
            continue
        by_inchikey.setdefault(inchikey, display)
        by_skeleton.setdefault(inchikey.split("-")[0], display)
    return by_inchikey, by_skeleton


def load_roster_smiles(path: Path | str = ROSTER_PATH) -> dict[str, str]:
    """normalised name -> SMILES, read straight from the roster (read-only)."""
    smiles_by_name: dict[str, str] = {}
    with open(path, encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            name = (row.get("name") or "").strip()
            smiles = (row.get("smiles") or "").strip()
            if name and smiles:
                smiles_by_name.setdefault(normalize_name(name), smiles)
    return smiles_by_name


def reconcile_roster(
    name: str,
    resolution: Resolution,
    roster: Any,
    indexes: tuple[Mapping[str, str], Mapping[str, str]],
) -> RosterVerdict:
    """Roster membership: normalised name first, resolved InChIKey second."""
    by_inchikey, _ = indexes
    key = normalize_name(name)
    if key in roster.by_name:
        roster_name = roster.by_name[key]
        return RosterVerdict(
            in_roster=True,
            basis="name",
            roster_name=roster_name,
            out_of_scope=roster_name in set(roster.out_of_scope_names),
        )
    if resolution.inchikey and resolution.inchikey in by_inchikey:
        roster_name = by_inchikey[resolution.inchikey]
        return RosterVerdict(
            in_roster=True,
            basis="inchikey",
            roster_name=roster_name,
            out_of_scope=roster_name in set(roster.out_of_scope_names),
        )
    return RosterVerdict(in_roster=False, basis="none", roster_name="", out_of_scope=False)


def review_reasons(
    resolution: Resolution,
    verdict: RosterVerdict,
    check: str,
    ilthermo_formula: str,
    roster: Any,
    indexes: tuple[Mapping[str, str], Mapping[str, str]],
) -> list[str]:
    """Manual-review tags. An identity settled by InChIKey needs no review."""
    if verdict.in_roster:
        return []
    _, by_skeleton = indexes
    reasons: list[str] = []
    if resolution.status == AMBIGUOUS:
        reasons.append("ambiguous_pubchem_name")
    if check == "mismatch":
        reasons.append("formula_mismatch_vs_ilthermo")
    signature = formula_signature(ilthermo_formula) if ilthermo_formula else ""
    if signature and signature in roster.by_formula:
        reasons.append(f"isomer_formula_collision_with_roster:{roster.by_formula[signature]}")
    if resolution.inchikey and resolution.inchikey.split("-")[0] in by_skeleton:
        reasons.append(
            f"shared_skeleton_with_roster:{by_skeleton[resolution.inchikey.split('-')[0]]}"
        )
    return reasons


def format_number(value: float | None, digits: int = 2) -> str:
    if value is None:
        return ""
    return f"{value:.{digits}f}"


def bool_text(value: bool) -> str:
    return "true" if value else "false"


def facts_from_set_payload(
    payload: Mapping[str, Any],
    setid: str,
    *,
    url: str,
    http_status: int,
) -> SetFacts:
    dataset = parse_dataset_payload(payload, setid)
    observations = extract_observations(dataset)
    temperatures = tuple(
        sorted({obs.temperature_k for obs in observations if obs.temperature_k is not None})
    )
    epsilons = [
        obs.relative_permittivity for obs in observations if obs.relative_permittivity is not None
    ]
    frequencies = [obs.frequency_mhz for obs in observations if obs.frequency_mhz is not None]
    formula = dataset.components[0].formula if dataset.components else ""
    return SetFacts(
        setid=setid,
        formula=formula,
        n_rows=len(dataset.rows),
        has_temperature_column=any(
            header[0].strip().lower() == "temperature, k" for header in dataset.column_headers
        ),
        temperatures=temperatures,
        epsilon_min=min(epsilons) if epsilons else None,
        epsilon_max=max(epsilons) if epsilons else None,
        n_zero_frequency_rows=sum(1 for value in frequencies if value == 0.0),
        n_frequency_rows_above_zero=sum(1 for value in frequencies if value > 0.0),
        reference=dataset.reference_full or dataset.reference_title,
        method=dataset.method,
        url=url,
        http_status=http_status,
    )


def compound_formula(
    compound: PureCompound,
    facts: Mapping[str, SetFacts],
    inline: Mapping[str, str],
) -> tuple[str, str]:
    for setid in compound.setids:
        fact = facts.get(setid)
        if fact is not None and fact.formula:
            return fact.formula, "ilset"
    if compound.name in inline:
        return inline[compound.name], "probe_summary_sample"
    return "", "not_read"


def span_class(n_distinct: int, span: float | None, *, threshold_k: float = SERIES_SPAN_THRESHOLD_K) -> str:
    """single_temperature / near_single / temperature_series, by span."""
    if n_distinct <= 1 or span is None:
        return "single_temperature"
    return "temperature_series" if span > threshold_k else "near_single"


def compound_temperature(compound: PureCompound, facts: Mapping[str, SetFacts]) -> dict[str, Any]:
    values: set[float] = set()
    read = 0
    for setid in compound.setids:
        fact = facts.get(setid)
        if fact is None:
            continue
        read += 1
        values.update(fact.temperatures)
    ordered = sorted(values)
    span = (ordered[-1] - ordered[0]) if ordered else None
    return {
        "n_sets_temperature_read": read,
        "n_distinct_temperatures": len(ordered),
        "temperature_min_K": ordered[0] if ordered else None,
        "temperature_max_K": ordered[-1] if ordered else None,
        "temperature_span_K": span,
        "temperature_span_class": span_class(len(ordered), span),
    }


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def set_facts_to_dict(fact: SetFacts) -> dict[str, Any]:
    """Serialise one set's facts so a later run can be replayed without network."""
    return {
        "setid": fact.setid,
        "formula": fact.formula,
        "n_rows": fact.n_rows,
        "has_temperature_column": fact.has_temperature_column,
        "temperatures": list(fact.temperatures),
        "epsilon_min": fact.epsilon_min,
        "epsilon_max": fact.epsilon_max,
        "n_zero_frequency_rows": fact.n_zero_frequency_rows,
        "n_frequency_rows_above_zero": fact.n_frequency_rows_above_zero,
        "reference": fact.reference,
        "method": fact.method,
        "url": fact.url,
        "http_status": fact.http_status,
    }


def set_facts_from_dict(payload: Mapping[str, Any]) -> SetFacts:
    return SetFacts(
        setid=str(payload.get("setid") or ""),
        formula=str(payload.get("formula") or ""),
        n_rows=int(payload.get("n_rows") or 0),
        has_temperature_column=bool(payload.get("has_temperature_column")),
        temperatures=tuple(float(value) for value in payload.get("temperatures") or []),
        epsilon_min=_optional_float(payload.get("epsilon_min")),
        epsilon_max=_optional_float(payload.get("epsilon_max")),
        n_zero_frequency_rows=int(payload.get("n_zero_frequency_rows") or 0),
        n_frequency_rows_above_zero=int(payload.get("n_frequency_rows_above_zero") or 0),
        reference=str(payload.get("reference") or ""),
        method=str(payload.get("method") or ""),
        url=str(payload.get("url") or ""),
        http_status=int(payload.get("http_status") or 0),
    )


def read_facts_replay(path: Path | str) -> dict[str, SetFacts]:
    """Replay the per-set facts stored by an earlier run (zero HTTP requests)."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    entries = payload.get("set_facts")
    if not isinstance(entries, list) or not entries:
        raise ValueError(f"{path} carries no set_facts block to replay")
    facts: dict[str, SetFacts] = {}
    for entry in entries:
        if not isinstance(entry, Mapping):
            continue
        fact = set_facts_from_dict(entry)
        if fact.setid:
            facts[fact.setid] = fact
    if not facts:
        raise ValueError(f"{path} carries no usable set_facts entries")
    return facts


# --------------------------------------------------------------------------- #
# Live transport
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


def logging_get(
    http_get: Callable[..., HttpResponse],
    log: list[dict[str, Any]],
    phase: str,
) -> Callable[..., HttpResponse]:
    def getter(url: str, params: Mapping[str, str] | None = None) -> HttpResponse:
        response = http_get(url, params)
        log.append(
            {
                "phase": phase,
                "url": response.url or url,
                "status": response.status,
                "bytes": len(response.body),
            }
        )
        return response

    return getter


def fetch_set_facts(
    setids: Sequence[str],
    *,
    http_get: Callable[..., HttpResponse],
    budget: RequestBudget,
    sleep: Callable[[float], None],
    delay_seconds: float,
    log: list[dict[str, Any]],
) -> tuple[dict[str, SetFacts], list[dict[str, Any]]]:
    """Read every ilset payload we were allowed to read; record every failure."""
    facts: dict[str, SetFacts] = {}
    failures: list[dict[str, Any]] = []
    skipped: list[str] = []
    getter = logging_get(http_get, log, "ilthermo_set")
    for setid in setids:
        url = f"{ORIGIN}{DATASET_PATH}"
        try:
            response = http_get_with_backoff(
                getter,
                url,
                {"set": setid},
                budget=budget,
                sleep=sleep,
                backoff=BACKOFF_SECONDS,
                ceiling=MAX_BACKOFF_SECONDS,
            )
        except BudgetExhausted:
            # One summary entry, not one entry per skipped set: the budget is a
            # single fact about the run, and 100 identical lines would bury the
            # real failures.
            skipped.append(setid)
            continue
        except Exception as exc:  # noqa: BLE001 - every transport failure is an outcome
            failures.append(
                {
                    "stage": "ilthermo_set",
                    "setid": setid,
                    "detail": f"{type(exc).__name__}: {exc}",
                }
            )
            continue
        if delay_seconds > 0:
            sleep(delay_seconds)
        if response.status != 200:
            failures.append(
                {"stage": "ilthermo_set", "setid": setid, "detail": f"HTTP {response.status}"}
            )
            continue
        try:
            payload = response.json()
        except (ValueError, json.JSONDecodeError) as exc:
            failures.append(
                {"stage": "ilthermo_set", "setid": setid, "detail": f"unparsable JSON: {exc}"}
            )
            continue
        if not isinstance(payload, Mapping):
            failures.append(
                {"stage": "ilthermo_set", "setid": setid, "detail": "payload is not an object"}
            )
            continue
        facts[setid] = facts_from_set_payload(
            payload,
            setid,
            url=f"{url}?set={setid}",
            http_status=response.status,
        )
    if skipped:
        failures.append(
            {
                "stage": "ilthermo_set",
                "setid": "",
                "detail": f"{len(skipped)} sets were not fetched: request budget exhausted",
                "setids_skipped": skipped,
            }
        )
    return facts, failures


def lookup_pubchem(
    name: str,
    *,
    http_get: Callable[..., HttpResponse],
    budget: RequestBudget,
    sleep: Callable[[float], None],
    delay_seconds: float,
    expected_formula: str,
    formula_of_smiles: Callable[[str], str | None],
    status_counts: Counter,
) -> Resolution:
    """Name -> structure, with every failure path recorded rather than guessed."""
    last_note = "no lookup variant produced a structure"
    for variant in lookup_variants(name):
        url = build_pubchem_url(variant)
        try:
            response = http_get_with_backoff(
                http_get,
                url,
                None,
                budget=budget,
                sleep=sleep,
                backoff=BACKOFF_SECONDS,
                ceiling=MAX_BACKOFF_SECONDS,
            )
        except BudgetExhausted:
            return Resolution(
                status=NOT_QUERIED,
                note="request budget exhausted before this name was queried",
            )
        except Exception as exc:  # noqa: BLE001 - transport failures are outcomes
            return Resolution(
                status=UNRESOLVED,
                note=f"network_error:{type(exc).__name__}:{exc}",
            )
        if delay_seconds > 0:
            sleep(delay_seconds)
        status_counts[response.status] += 1
        if response.status == 404:
            last_note = f"HTTP 404: PubChem has no record under the name '{variant}'"
            continue
        if response.status != 200:
            last_note = f"HTTP {response.status}: name lookup failed"
            continue
        try:
            payload = response.json()
        except (ValueError, json.JSONDecodeError) as exc:
            return Resolution(status=UNRESOLVED, note=f"unparsable JSON payload: {exc}")
        resolution = classify_candidates(
            parse_pubchem_payload(payload), expected_formula, formula_of_smiles
        )
        if resolution.status == RESOLVED:
            return replace(resolution, source="pubchem")
        if resolution.status == AMBIGUOUS:
            return replace(resolution, source="pubchem")
        last_note = resolution.note or last_note
    return Resolution(status=UNRESOLVED, note=last_note)


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #


def run_resolution(
    *,
    http_get: Callable[..., HttpResponse],
    probe_summary_path: Path | str = DEFAULT_PROBE_SUMMARY,
    roster_path: Path | str = ROSTER_PATH,
    offline: bool = False,
    request_budget_limit: int = DEFAULT_REQUEST_BUDGET,
    set_budget_limit: int = DEFAULT_SET_BUDGET,
    sleep: Callable[[float], None] = time.sleep,
    delay_seconds: float = DEFAULT_SLEEP_SECONDS,
    formula_of_smiles: Callable[[str], str | None] = rdkit_formula,
    max_names: int | None = None,
    facts_replay: Mapping[str, SetFacts] | None = None,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    summary = json.loads(Path(probe_summary_path).read_text(encoding="utf-8"))
    compounds = parse_probe_pure_compounds(summary)
    inline_formulas = sample_formulas(summary)
    roster = load_roster(roster_path, formula_of_smiles=formula_of_smiles)
    indexes = roster_indexes(roster)
    roster_smiles = load_roster_smiles(roster_path)

    log: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    pubchem_budget = RequestBudget(limit=request_budget_limit)
    set_budget = RequestBudget(limit=set_budget_limit)
    status_counts: Counter = Counter()

    facts: dict[str, SetFacts] = {}
    if facts_replay is not None:
        facts = dict(facts_replay)
    elif not offline:
        setids = [setid for compound in compounds for setid in compound.setids]
        facts, set_failures = fetch_set_facts(
            setids,
            http_get=http_get,
            budget=set_budget,
            sleep=sleep,
            delay_seconds=delay_seconds,
            log=log,
        )
        failures.extend(set_failures)

    lookup_names: list[str] = []
    for compound in compounds:
        if normalize_name(compound.name) not in roster.by_name and normalize_name(
            compound.name
        ) not in {normalize_name(name) for name in lookup_names}:
            lookup_names.append(compound.name)
    if max_names is not None:
        lookup_names = lookup_names[:max_names]
    lookup_set = set(lookup_names)

    rows: list[dict[str, str]] = []
    resolutions: dict[str, Resolution] = {}
    for compound in compounds:
        key = normalize_name(compound.name)
        formula, formula_source = compound_formula(compound, facts, inline_formulas)
        if key in roster.by_name:
            resolution = Resolution(
                status=RESOLVED,
                inchikey=roster.inchikey_by_name.get(key, ""),
                smiles=roster_smiles.get(key, ""),
                note="InChIKey taken from the roster name join; no PubChem call was made",
                source="roster_name_join",
            )
        elif offline:
            resolution = Resolution(
                status=NOT_QUERIED,
                note="offline: PubChem name lookup not attempted",
            )
        elif compound.name not in lookup_set:
            resolution = Resolution(
                status=NOT_QUERIED,
                note="not queried: --max-names cut this row from the lookup list",
            )
        else:
            resolution = lookup_pubchem(
                compound.name,
                http_get=logging_get(http_get, log, "pubchem_name"),
                budget=pubchem_budget,
                sleep=sleep,
                delay_seconds=delay_seconds,
                expected_formula=formula,
                formula_of_smiles=formula_of_smiles,
                status_counts=status_counts,
            )
        resolutions[compound.name] = resolution

        computed = formula_of_smiles(resolution.smiles) if resolution.smiles else None
        check = formula_check(formula, computed)
        verdict = reconcile_roster(compound.name, resolution, roster, indexes)
        reasons = review_reasons(resolution, verdict, check, formula, roster, indexes)
        temperature = compound_temperature(compound, facts)

        notes: list[str] = []
        if resolution.note:
            notes.append(resolution.note)
        if formula_source == "not_read":
            notes.append("ILThermo formula not read (no ilset payload for this compound)")
        if temperature["n_sets_temperature_read"] < compound.n_epsilon_sets:
            notes.append(
                f"temperature read from {temperature['n_sets_temperature_read']} of "
                f"{compound.n_epsilon_sets} ilset payloads"
            )

        rows.append(
            {
                "ilthermo_name": compound.name,
                "ilthermo_formula": formula,
                "formula_source": formula_source,
                "resolved_inchikey": resolution.inchikey,
                "resolved_smiles": resolution.smiles,
                "resolution_status": resolution.status,
                "resolution_source": resolution.source,
                "pubchem_cid": "" if resolution.cid is None else str(resolution.cid),
                "pubchem_candidate_count": str(resolution.n_candidates),
                "formula_check": check,
                "rdkit_formula": computed or "",
                "in_roster": bool_text(verdict.in_roster),
                "roster_join_basis": verdict.basis,
                "roster_match_name": verdict.roster_name,
                "roster_verdict": "in_roster" if verdict.in_roster else "new_compound",
                "roster_out_of_scope": bool_text(verdict.out_of_scope),
                "needs_manual_review": bool_text(bool(reasons)),
                "needs_manual_review_reason": "; ".join(reasons),
                "roster_formula_collisions": roster.by_formula.get(
                    formula_signature(formula) if formula else "", ""
                ),
                "n_epsilon_sets": str(compound.n_epsilon_sets),
                "n_datapoints": str(compound.n_datapoints),
                "temperature_span_K": format_number(temperature["temperature_span_K"]),
                "temperature_min_K": format_number(temperature["temperature_min_K"]),
                "temperature_max_K": format_number(temperature["temperature_max_K"]),
                "n_distinct_temperatures": str(temperature["n_distinct_temperatures"]),
                "temperature_span_class": temperature["temperature_span_class"],
                "n_sets_temperature_read": str(temperature["n_sets_temperature_read"]),
                "is_ionic_liquid": bool_text(compound.is_ionic_liquid),
                "ilthermo_setids": ";".join(compound.setids),
                "source_url": (
                    f"{ORIGIN}{DATASET_PATH}?set={compound.setids[0]}"
                    if compound.setids
                    else ""
                ),
                "notes": " | ".join(notes),
            }
        )

    in_roster_rows = [row for row in rows if row["in_roster"] == "true"]
    in_roster_by_name_rows = [row for row in rows if row["roster_join_basis"] == "name"]
    new_by_name_rows = [row for row in rows if row["roster_join_basis"] != "name"]
    new_rows = [row for row in rows if row["roster_verdict"] == "new_compound"]
    # Lookup-eligible rows: every compound the normalised name join could not
    # place, whether or not the budget or --max-names actually let us query it.
    lookup_rows = new_by_name_rows
    queried_rows = [row for row in rows if row["resolution_source"] == "pubchem"]
    resolved_new = [row for row in queried_rows if row["resolution_status"] == RESOLVED]
    recovered = [row for row in queried_rows if row["in_roster"] == "true"]
    review_rows = [row for row in rows if row["needs_manual_review"] == "true"]
    reason_counts: Counter = Counter()
    for row in review_rows:
        for reason in row["needs_manual_review_reason"].split("; "):
            if reason:
                reason_counts[reason.split(":")[0]] += 1

    temperature_read_rows = [row for row in rows if int(row["n_sets_temperature_read"]) > 0]
    varying_sets = [fact for fact in facts.values() if len(fact.temperatures) > 1]
    varying_compounds = [row for row in rows if row["temperature_span_class"] != "single_temperature"]
    series_compounds = [row for row in rows if row["temperature_span_class"] == "temperature_series"]
    histogram = Counter(row["n_distinct_temperatures"] for row in rows)

    record: dict[str, Any] = {
        "probe": "ilthermo_structure_resolution",
        "origin": ORIGIN,
        "generated_utc": (generated_at or datetime.now(UTC)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "user_agent": USER_AGENT,
        "offline": offline,
        "inputs": {
            "probe_summary": str(probe_summary_path),
            "roster": str(roster_path),
            "pubchem_endpoint": PUBCHEM_NAME_URL,
        },
        "population": {
            "n_pure_compounds": len(compounds),
            "n_epsilon_sets": sum(compound.n_epsilon_sets for compound in compounds),
            "n_datapoints": sum(compound.n_datapoints for compound in compounds),
            "n_in_roster_by_name": len(in_roster_by_name_rows),
            "n_new_to_roster_by_name": len(new_by_name_rows),
            "n_in_roster_total": len(in_roster_rows),
            "n_new_compound_total": len(new_rows),
        },
        "requests": {
            "pubchem": {
                "limit": pubchem_budget.limit,
                "used": pubchem_budget.used,
                "remaining": pubchem_budget.remaining,
            },
            "ilthermo_sets": {
                "limit": set_budget.limit,
                "used": set_budget.used,
                "remaining": set_budget.remaining,
            },
            "response_status_counts": {str(k): v for k, v in sorted(status_counts.items())},
            "total_bytes_transferred": sum(entry["bytes"] for entry in log),
        },
        "resolution": {
            "n_names_queried": len(lookup_names),
            "status_counts": dict(sorted(Counter(row["resolution_status"] for row in
                                                 lookup_rows).items())),
            "resolved_new_compounds": len(resolved_new),
            "resolved_rate_of_queried": (
                round(len(resolved_new) / len(lookup_names), 4) if lookup_names else None
            ),
            "recovered_into_roster_by_inchikey": [row["ilthermo_name"] for row in recovered],
            "formula_check_counts": dict(sorted(Counter(row["formula_check"] for row in
                                                        rows).items())),
            "failure_reason_counts": dict(
                sorted(
                    Counter(
                        row["notes"].split(":")[0]
                        for row in lookup_rows
                        if row["resolution_status"] != RESOLVED
                    ).items()
                )
            ),
        },
        "roster_reconciliation": {
            "in_roster_total": len(in_roster_rows),
            "new_compound_total": len(new_rows),
            "out_of_scope_rows": [row["ilthermo_name"] for row in rows
                                  if row["roster_out_of_scope"] == "true"],
            "needs_manual_review": len(review_rows),
            "needs_manual_review_reasons": dict(sorted(reason_counts.items())),
        },
        "temperature": {
            "facts_source": "replay" if facts_replay is not None else ("live" if facts else "none"),
            "n_sets_read": len(facts),
            "n_sets_with_temperature_column": sum(
                1 for fact in facts.values() if fact.has_temperature_column
            ),
            "n_sets_varying_temperature": len(varying_sets),
            "n_compounds_with_temperature_read": len(temperature_read_rows),
            "n_compounds_with_multiple_set_temperatures": len(varying_compounds),
            "n_compounds_with_temperature_series": len(series_compounds),
            "series_span_threshold_K": SERIES_SPAN_THRESHOLD_K,
            "n_distinct_temperatures_histogram": dict(sorted(histogram.items())),
            "epsilon_read": {
                "n_compounds": len(temperature_read_rows),
                "n_sets": len(facts),
                "n_rows": sum(fact.n_rows for fact in facts.values()),
            },
            "verdict": (
                "not read: no ilset payload was fetched"
                if not facts
                else (
                    f"{len(series_compounds)} of {len(rows)} pure compounds carry a temperature "
                    f"span above {SERIES_SPAN_THRESHOLD_K:g} K"
                    f" ({len(varying_compounds)} differ at all between sets); "
                    "epsilon coverage alone is "
                    f"{len(temperature_read_rows)} of {len(rows)} compounds"
                )
            ),
        },
        "new_compounds": [
            {
                "ilthermo_name": row["ilthermo_name"],
                "ilthermo_formula": row["ilthermo_formula"],
                "resolution_status": row["resolution_status"],
                "resolved_inchikey": row["resolved_inchikey"],
                "in_roster": row["in_roster"] == "true",
                "n_epsilon_sets": int(row["n_epsilon_sets"]),
                "n_datapoints": int(row["n_datapoints"]),
                "temperature_span_K": row["temperature_span_K"],
            }
            for row in new_rows
        ],
        "set_facts": [
            set_facts_to_dict(fact) for fact in sorted(facts.values(), key=lambda f: f.setid)
        ],
        "failures": failures,
        "request_log": log,
        "rows": rows,
    }
    return record


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
        description="Resolve ILThermo pure compounds into InChIKeys via PubChem"
    )
    parser.add_argument("--probe-summary", default=str(DEFAULT_PROBE_SUMMARY))
    parser.add_argument("--roster", default=str(ROSTER_PATH))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_CSV))
    parser.add_argument("--summary", default=str(DEFAULT_SUMMARY_JSON))
    parser.add_argument("--budget", type=int, default=DEFAULT_REQUEST_BUDGET)
    parser.add_argument("--set-budget", type=int, default=DEFAULT_SET_BUDGET)
    parser.add_argument("--sleep", type=float, default=DEFAULT_SLEEP_SECONDS)
    parser.add_argument("--max-names", type=int, default=None)
    parser.add_argument(
        "--facts-from",
        default=None,
        help="replay the set_facts block of an earlier summary instead of re-reading ILThermo",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="no network at all: parse the stored probe summary and write the unqueried table",
    )
    args = parser.parse_args(argv)

    record = run_resolution(
        http_get=default_http_get,
        probe_summary_path=args.probe_summary,
        roster_path=args.roster,
        offline=args.offline,
        request_budget_limit=args.budget,
        set_budget_limit=args.set_budget,
        delay_seconds=args.sleep,
        max_names=args.max_names,
        facts_replay=read_facts_replay(args.facts_from) if args.facts_from else None,
    )
    csv_path = write_csv(args.output, record["rows"])
    payload = {key: value for key, value in record.items() if key != "rows"}
    json_path = write_summary(args.summary, payload)

    resolution = record["resolution"]
    print(f"ILThermo structure resolution -> {csv_path}")
    print(f"  summary: {json_path}")
    print(
        f"  pure compounds: {record['population']['n_pure_compounds']} "
        f"({record['population']['n_new_to_roster_by_name']} new to the roster by name)"
    )
    print(
        f"  pubchem requests: {record['requests']['pubchem']['used']}/"
        f"{record['requests']['pubchem']['limit']} "
        f"statuses={record['requests']['response_status_counts']}"
    )
    print(
        f"  ilthermo ilset requests: {record['requests']['ilthermo_sets']['used']}/"
        f"{record['requests']['ilthermo_sets']['limit']} "
        f"failures={len(record['failures'])}"
    )
    print(f"  resolution statuses: {resolution['status_counts']}")
    print(f"  formula checks: {resolution['formula_check_counts']}")
    print(
        f"  recovered into roster by InChIKey: "
        f"{len(resolution['recovered_into_roster_by_inchikey'])}"
    )
    print(f"  needs manual review: {record['roster_reconciliation']['needs_manual_review']}")
    print(f"  temperature verdict: {record['temperature']['verdict']}")
    for failure in record["failures"][:10]:
        print(f"  FAILURE {failure}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
