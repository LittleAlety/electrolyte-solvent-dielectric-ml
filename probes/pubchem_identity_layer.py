"""L0 identity layer: one resolution row per InChIKey, PubChem-backed.

Appendix AA of the execution manual splits the sourcing architecture into three
layers -- L0 identity, L1 open harvesting, L2 adjudication -- and puts PubChem
in the role of *harvester*, never judge. This probe builds L0 only: for every
InChIKey the project already talks about, it records the canonical PubChem
record (CID, formula, average molecular weight, canonical SMILES) together with
the provenance needed to re-check it later.

Coverage set
    the roster ``data/dielectric_v03.csv`` (246 rows, one row per InChIKey)
    union the keys of ``data/processed/dielectric_lowfreq_structures.csv`` and
    ``data/processed/ilthermo_new_compounds.csv``, which already carry a
    ``pubchem_cid`` for some compounds. Those two tables are read, never
    written: they stay the property of their own probes.

Discipline
    * Offline first. A cached response is served without touching the network;
      the cache stores the URL it came from, so a mis-keyed file can never be
      returned as evidence for a different request.
    * Throttled. PubChem asks for at most five requests per second without an
      API key; the default spacing is 0.25 s, and every request is retried with
      a bounded back-off.
    * Honest. A 404 is recorded as ``unresolved_no_pubchem_record``. A missing
      cache while offline is recorded as ``unresolved_offline`` -- never as a
      resolution, and never as an absence.
    * Idempotent. Re-running the resolution over the same cache produces
      byte-identical rows, which the probe verifies in-process and reports as
      ``run_idempotent``.
"""

from __future__ import annotations

import argparse
import csv
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

PUG_REST = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"
PROPERTY_LIST = "MolecularFormula,MolecularWeight,CanonicalSMILES,InChIKey"
USER_AGENT = "electrolyte-ml-research/1.0 (local reproducibility probe)"

DEFAULT_CACHE_DIR = REPOSITORY_ROOT / "data" / "external" / "g1plus" / "pubchem" / "identity_layer"
DEFAULT_OUTPUT = REPOSITORY_ROOT / "data" / "reference" / "identity_map.csv"
DEFAULT_SUMMARY = REPOSITORY_ROOT / "probes" / "pubchem_identity_layer_summary.json"
DEFAULT_HARVEST_LOG = DEFAULT_CACHE_DIR / "_harvest_runs.jsonl"

ROSTER_PATH = REPOSITORY_ROOT / "data" / "dielectric_v03.csv"
LOWFREQ_PATH = REPOSITORY_ROOT / "data" / "processed" / "dielectric_lowfreq_structures.csv"
ILTHERMO_PATH = REPOSITORY_ROOT / "data" / "processed" / "ilthermo_new_compounds.csv"
ALIAS_PATH = REPOSITORY_ROOT / "data" / "reference" / "dielectric_molecule_aliases.csv"

DEFAULT_THROTTLE_SECONDS = 0.25
DEFAULT_ATTEMPTS = 4

IDENTITY_COLUMNS: tuple[str, ...] = (
    "inchikey",
    "smiles",
    "name",
    "pubchem_cid",
    "molecular_formula",
    "molecular_weight",
    "source_url",
    "retrieved_at",
    "resolution_status",
    "resolved_from",
    "pubchem_smiles",
    "pubchem_inchikey",
    "identity_check",
    "smiles_match",
    "in_roster",
    "in_lowfreq_table",
    "in_ilthermo_table",
    "alias_names",
    "notes",
)


def _properties_url(inchikey: str) -> str:
    slug = urllib.parse.quote(inchikey, safe="")
    return f"{PUG_REST}/compound/inchikey/{slug}/property/{PROPERTY_LIST}/JSON"


def _utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


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
    cache_entries: int = 0


@dataclass
class PubChemClient:
    """Cached, throttled, offline-capable PUG-REST reader."""

    cache_dir: Path
    throttle_seconds: float = DEFAULT_THROTTLE_SECONDS
    attempts: int = DEFAULT_ATTEMPTS
    offline: bool = False
    sleep_fn: object = time.sleep
    stats: ClientStats = field(default_factory=ClientStats)
    _last_request_at: float | None = None

    def cache_path(self, inchikey: str) -> Path:
        return self.cache_dir / f"{urllib.parse.quote(inchikey, safe='')}.properties.json"

    def _read_cache(self, inchikey: str) -> dict[str, object] | None:
        path = self.cache_path(inchikey)
        marker = path.with_suffix(path.suffix + ".url")
        if not path.is_file() or not marker.is_file():
            return None
        recorded = marker.read_text(encoding="utf-8").strip()
        if recorded != _properties_url(inchikey):
            # A cache entry whose URL marker disagrees is not evidence for this
            # compound; treat it as absent rather than trusting the filename.
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def _write_cache(self, inchikey: str, payload: Mapping[str, object]) -> None:
        path = self.cache_path(inchikey)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        path.with_suffix(path.suffix + ".url").write_text(
            _properties_url(inchikey) + "\n", encoding="utf-8"
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

    def fetch(self, inchikey: str, *, refresh: bool = False) -> dict[str, object]:
        """Return ``{"cid": ..., ...}`` for a resolved key, or ``{"not_found": True}``.

        The returned dict is the raw parsed PubChem property record; callers
        must not read a missing field as a value.
        """

        if not refresh:
            cached = self._read_cache(inchikey)
            if cached is not None:
                self.stats.cache_hits += 1
                return cached
        if self.offline:
            raise OfflineError(f"offline client asked for {inchikey}")

        url = _properties_url(inchikey)
        last: Exception | None = None
        for attempt in range(self.attempts):
            self._throttle()
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            try:
                with urllib.request.urlopen(request, timeout=60) as response:
                    body = response.read().decode("utf-8")
            except urllib.error.HTTPError as error:
                self._last_request_at = time.monotonic()
                self.stats.network_calls += 1
                if error.code == 404:
                    payload: dict[str, object] = {"not_found": True, "http_status": 404}
                    self._write_cache(inchikey, payload)
                    return payload
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
            self._write_cache(inchikey, payload)
            return payload
        raise RuntimeError(f"PubChem request failed after {self.attempts} attempts: {url}") from last


def parse_property_record(payload: Mapping[str, object]) -> dict[str, str] | None:
    """Flatten a PUG-REST PropertyTable payload into plain strings.

    Returns ``None`` for a ``not_found`` payload and for a payload that carries
    no CID, so a malformed response can never masquerade as a resolution.
    """

    if payload.get("not_found"):
        return None
    table = payload.get("PropertyTable")
    if not isinstance(table, Mapping):
        return None
    properties = table.get("Properties")
    if not isinstance(properties, list) or not properties:
        return None
    first = properties[0]
    if not isinstance(first, Mapping):
        return None

    lowered = {str(key).lower(): value for key, value in first.items()}
    cid = lowered.get("cid")
    if cid in (None, ""):
        return None
    # PUG-REST answers a CanonicalSMILES request with the key
    # "ConnectivitySMILES" (verified against the live service), so all three
    # spellings are accepted rather than silently returning an empty SMILES.
    smiles = (
        lowered.get("smiles")
        or lowered.get("canonicalsmiles")
        or lowered.get("connectivitysmiles")
        or lowered.get("isomericsmiles")
        or ""
    )
    return {
        "cid": str(cid),
        "molecular_formula": str(lowered.get("molecularformula") or ""),
        "molecular_weight": str(lowered.get("molecularweight") or ""),
        "pubchem_smiles": str(smiles),
        "pubchem_inchikey": str(lowered.get("inchikey") or ""),
    }


# --------------------------------------------------------------------------
# Input tables.
# --------------------------------------------------------------------------


def _read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def load_roster() -> list[dict[str, str]]:
    return _read_rows(ROSTER_PATH)


def load_known_cids() -> dict[str, tuple[str, str]]:
    """InChIKey -> (cid, provenance) collected from the two existing tables."""

    known: dict[str, tuple[str, str]] = {}
    for row in _read_rows(LOWFREQ_PATH):
        key = (row.get("inchikey") or "").strip()
        cid = (row.get("pubchem_cid") or "").strip()
        if key and cid:
            known.setdefault(key, (cid, "lowfreq_structures_table"))
    for row in _read_rows(ILTHERMO_PATH):
        key = (row.get("resolved_inchikey") or "").strip()
        cid = (row.get("pubchem_cid") or "").strip()
        if key and cid:
            known.setdefault(key, (cid, "ilthermo_new_compounds_table"))
    return known


def load_aliases() -> dict[str, list[str]]:
    aliases: dict[str, list[str]] = {}
    for row in _read_rows(ALIAS_PATH):
        key = (row.get("inchikey") or "").strip()
        alias = (row.get("alias") or "").strip()
        if key and alias:
            aliases.setdefault(key, []).append(alias)
    return {key: sorted(set(values)) for key, values in aliases.items()}


def build_targets() -> list[dict[str, object]]:
    """The union coverage set, sorted by InChIKey for a deterministic output."""

    roster = {row["inchikey"]: row for row in load_roster()}
    known = load_known_cids()
    targets: dict[str, dict[str, object]] = {}
    for key, row in roster.items():
        targets[key] = {
            "inchikey": key,
            "name": row.get("name", ""),
            "smiles": row.get("smiles", ""),
            "in_roster": True,
            "in_lowfreq_table": False,
            "in_ilthermo_table": False,
        }
    for row in _read_rows(LOWFREQ_PATH):
        key = (row.get("inchikey") or "").strip()
        if not key:
            continue
        entry = targets.setdefault(
            key,
            {
                "inchikey": key,
                "name": row.get("name", ""),
                "smiles": row.get("resolved_smiles", ""),
                "in_roster": False,
                "in_lowfreq_table": False,
                "in_ilthermo_table": False,
            },
        )
        entry["in_lowfreq_table"] = True
    for row in _read_rows(ILTHERMO_PATH):
        key = (row.get("resolved_inchikey") or "").strip()
        if not key:
            continue
        entry = targets.setdefault(
            key,
            {
                "inchikey": key,
                "name": row.get("ilthermo_name", ""),
                "smiles": row.get("resolved_smiles", ""),
                "in_roster": False,
                "in_lowfreq_table": False,
                "in_ilthermo_table": False,
            },
        )
        entry["in_ilthermo_table"] = True
    for key, (_, provenance) in known.items():
        entry = targets.get(key)
        if entry is None:
            continue
        if provenance == "lowfreq_structures_table":
            entry["in_lowfreq_table"] = True
        else:
            entry["in_ilthermo_table"] = True
    return [targets[key] for key in sorted(targets)]


# --------------------------------------------------------------------------
# Resolution.
# --------------------------------------------------------------------------


def resolve_targets(
    targets: Sequence[Mapping[str, object]],
    client: PubChemClient,
    *,
    known_cids: Mapping[str, tuple[str, str]] | None = None,
    aliases: Mapping[str, Sequence[str]] | None = None,
    retrieved_at: str | None = None,
) -> list[dict[str, str]]:
    """Resolve every target to an identity row.

    ``retrieved_at`` is injected so that a test can pin it; the production
    caller passes the wall-clock stamp of the run.
    """

    known = known_cids if known_cids is not None else load_known_cids()
    alias_map = aliases if aliases is not None else load_aliases()
    stamp = retrieved_at or _utc_now()
    rows: list[dict[str, str]] = []

    for target in targets:
        key = str(target["inchikey"])
        local_cid, local_source = known.get(key, ("", ""))
        try:
            payload = client.fetch(key)
        except OfflineError:
            payload = {}
            offline = True
        else:
            offline = False
        parsed = parse_property_record(payload) if payload else None

        row = {column: "" for column in IDENTITY_COLUMNS}
        row["inchikey"] = key
        row["name"] = str(target.get("name", ""))
        row["in_roster"] = "true" if target.get("in_roster") else "false"
        row["in_lowfreq_table"] = "true" if target.get("in_lowfreq_table") else "false"
        row["in_ilthermo_table"] = "true" if target.get("in_ilthermo_table") else "false"
        row["alias_names"] = ";".join(alias_map.get(key, ()))

        if parsed is not None:
            row["pubchem_cid"] = parsed["cid"]
            row["molecular_formula"] = parsed["molecular_formula"]
            row["molecular_weight"] = parsed["molecular_weight"]
            row["pubchem_smiles"] = parsed["pubchem_smiles"]
            row["pubchem_inchikey"] = parsed["pubchem_inchikey"]
            row["smiles"] = str(target.get("smiles", "")) or parsed["pubchem_smiles"]
            row["source_url"] = _properties_url(key)
            row["retrieved_at"] = stamp
            row["resolution_status"] = "resolved_pubchem"
            row["resolved_from"] = "pubchem_pug_rest"
            if row["pubchem_inchikey"]:
                row["identity_check"] = (
                    "roundtrip_match" if row["pubchem_inchikey"] == key else "roundtrip_mismatch"
                )
            else:
                row["identity_check"] = "not_reported"
            if row["smiles"] and parsed["pubchem_smiles"]:
                row["smiles_match"] = _smiles_agreement(row["smiles"], parsed["pubchem_smiles"])
            if local_cid and local_cid != parsed["cid"]:
                row["notes"] = (
                    f"cid_conflict: local table says {local_cid} ({local_source}), "
                    f"PubChem says {parsed['cid']}"
                )
            elif local_cid:
                row["notes"] = f"cid_corroborated_by {local_source}"
        elif payload and payload.get("not_found"):
            row["smiles"] = str(target.get("smiles", ""))
            row["source_url"] = _properties_url(key)
            row["retrieved_at"] = stamp
            row["resolution_status"] = "unresolved_no_pubchem_record"
            row["resolved_from"] = "pubchem_pug_rest"
            row["pubchem_cid"] = local_cid
            if local_cid:
                row["notes"] = (
                    f"local table carries cid {local_cid} ({local_source}) but the "
                    "InChIKey is not in PubChem"
                )
        elif offline:
            row["smiles"] = str(target.get("smiles", ""))
            row["pubchem_cid"] = local_cid
            row["resolution_status"] = "unresolved_offline"
            row["resolved_from"] = local_source or "none"
            row["notes"] = "no cached PubChem response and the client is offline"
        else:
            row["smiles"] = str(target.get("smiles", ""))
            row["pubchem_cid"] = local_cid
            row["resolution_status"] = "unresolved_empty_response"
            row["resolved_from"] = local_source or "none"
            row["notes"] = "PubChem returned a payload with no usable CID"

        rows.append(row)

    return rows


def _canonical_smiles(smiles: str) -> str | None:
    """RDKit canonical form, or ``None`` when the string is not parseable."""

    try:
        from rdkit import Chem  # imported lazily: only this comparison needs it
    except ImportError:  # pragma: no cover - rdkit is a hard project dependency
        return None
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return None
    return Chem.MolToSmiles(mol)


def _smiles_agreement(local: str, pubchem: str) -> str:
    """Compare two SMILES as molecules, not as strings.

    PubChem returns its own canonicalisation (``CNc1ccccc1`` comes back as
    ``CNC1=CC=CC=C1``), so a raw string comparison would label almost every row
    "differ" and drown the signal. Both sides are therefore canonicalised with
    RDKit first; only a real structural disagreement is reported as ``differ``.
    """

    left = _canonical_smiles(local)
    right = _canonical_smiles(pubchem)
    if left is None or right is None:
        return "not_comparable"
    return "match" if left == right else "differ"


def write_rows(path: Path, rows: Sequence[Mapping[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(IDENTITY_COLUMNS), lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in IDENTITY_COLUMNS})


def summarize(
    rows: Sequence[Mapping[str, str]],
    stats: ClientStats,
    *,
    roster_keys: int,
    run_idempotent: bool,
) -> dict[str, object]:
    resolved = [row for row in rows if row.get("pubchem_cid")]
    unresolved = [
        {
            "inchikey": row["inchikey"],
            "name": row.get("name", ""),
            "resolution_status": row.get("resolution_status", ""),
            "in_roster": row.get("in_roster", ""),
        }
        for row in rows
        if not row.get("pubchem_cid")
    ]
    statuses: dict[str, int] = {}
    for row in rows:
        status = row.get("resolution_status", "")
        statuses[status] = statuses.get(status, 0) + 1
    roster_rows = [row for row in rows if row.get("in_roster") == "true"]
    return {
        "generated_at_utc": _utc_now(),
        "coverage_set": len(rows),
        "roster_keys": roster_keys,
        "roster_resolved_with_cid": sum(1 for row in roster_rows if row.get("pubchem_cid")),
        "resolved_with_cid": len(resolved),
        "unresolved": unresolved,
        "unresolved_count": len(unresolved),
        "resolution_status_counts": dict(sorted(statuses.items())),
        "cache_hits": stats.cache_hits,
        "network_calls": stats.network_calls,
        "retries": stats.retries,
        # The cache is the durable record of what the harvest actually cost:
        # a later cache-only re-run spends no requests, so the number of
        # populated entries (and the log written next to them) is what makes
        # the original cost auditable instead of invisible.
        "cache_entries_for_coverage_set": stats.cache_entries,
        "throttle_seconds": round(stats.throttle_seconds, 6),
        "throttled_requests": stats.throttled_requests,
        "run_idempotent": run_idempotent,
        "identity_check_counts": _counter(row.get("identity_check", "") for row in rows),
        "smiles_match_counts": _counter(row.get("smiles_match", "") for row in rows),
        "smiles_differing_keys": [
            {
                "inchikey": row["inchikey"],
                "name": row.get("name", ""),
                "local_smiles": row.get("smiles", ""),
                "pubchem_smiles": row.get("pubchem_smiles", ""),
                # PubChem answers a CanonicalSMILES request with its
                # ConnectivitySMILES, which carries no stereo layer. Rows whose
                # disagreement disappears once stereo is stripped are therefore
                # a reporting artefact; the rest are real structural
                # disagreements that need a human adjudication.
                "difference_kind": _difference_kind(
                    row.get("smiles", ""), row.get("pubchem_smiles", "")
                ),
            }
            for row in rows
            if row.get("smiles_match") == "differ"
        ],
        "pubchem_smiles_shared_by_several_keys": _shared_smiles(rows),
        "cid_conflicts": [
            {"inchikey": row["inchikey"], "notes": row["notes"]}
            for row in rows
            if row.get("notes", "").startswith("cid_conflict")
        ],
    }


def _difference_kind(local: str, pubchem: str) -> str:
    """``stereo_only`` or ``structural`` for two SMILES that disagree as drawn."""

    try:
        from rdkit import Chem
    except ImportError:  # pragma: no cover - rdkit is a hard project dependency
        return "unclassified"
    molecule = Chem.MolFromSmiles(local) if local else None
    counterpart = Chem.MolFromSmiles(pubchem) if pubchem else None
    if molecule is None or counterpart is None:
        return "unclassified"
    flat = Chem.MolToSmiles(molecule, isomericSmiles=False)
    return "stereo_only" if flat == Chem.MolToSmiles(counterpart) else "structural"


def _shared_smiles(rows: Sequence[Mapping[str, str]]) -> list[dict[str, object]]:
    """One PubChem SMILES shared by several InChIKeys.

    Cis/trans pairs are the worked case: two different InChIKeys come back with
    the same ConnectivitySMILES, so a SMILES-keyed join would silently collapse
    them into a single compound. This is the operational reason the identity
    layer is keyed on InChIKey.
    """

    grouped: dict[str, list[str]] = {}
    for row in rows:
        smiles = row.get("pubchem_smiles", "")
        if smiles:
            grouped.setdefault(smiles, []).append(row.get("inchikey", ""))
    return [
        {"pubchem_smiles": smiles, "inchikeys": sorted(keys)}
        for smiles, keys in sorted(grouped.items())
        if len(keys) > 1
    ]


def cache_population_window(cache_dir: Path, inchikeys: Iterable[str]) -> list[str]:
    """UTC window in which the cached responses were written.

    A cache-only re-run spends no requests, so the summary cannot describe the
    original harvest by counting its own calls. The file timestamps are the
    durable evidence of when the cache was actually filled, and they are
    reported instead of a remembered number.
    """

    stamps = []
    for inchikey in inchikeys:
        path = cache_dir / f"{urllib.parse.quote(inchikey, safe='')}.properties.json"
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


# --------------------------------------------------------------------------
# Entry point.
# --------------------------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument("--throttle-seconds", type=float, default=DEFAULT_THROTTLE_SECONDS)
    parser.add_argument("--offline", action="store_true", help="serve only from cache")
    parser.add_argument("--refresh", action="store_true", help="ignore the cache")
    parser.add_argument("--harvest-log", type=Path, default=DEFAULT_HARVEST_LOG)
    parser.add_argument("--dry-run", action="store_true", help="do not write the outputs")
    arguments = parser.parse_args(argv)

    targets = build_targets()
    roster_keys = len({row["inchikey"] for row in load_roster()})

    client = PubChemClient(
        cache_dir=arguments.cache_dir,
        throttle_seconds=arguments.throttle_seconds,
        offline=arguments.offline,
    )
    if arguments.refresh:
        for target in targets:
            client.cache_path(str(target["inchikey"])).unlink(missing_ok=True)
    # One timestamp for the whole run, so the idempotence comparison below is
    # not defeated by the clock ticking between the two passes.
    stamp = _utc_now()
    rows = resolve_targets(targets, client, retrieved_at=stamp)

    # Idempotence is checked against the cache the run just populated: a second
    # pass must return identical rows and must not spend another network call.
    before = client.stats.network_calls
    second = resolve_targets(targets, client, retrieved_at=stamp)
    if arguments.refresh:
        # A refreshing run rewrites every entry, so the second pass legitimately
        # differs in `retrieved_at`; compare everything else.
        def strip(sequence: Sequence[Mapping[str, str]]) -> list[dict[str, str]]:
            return [
                {key: value for key, value in row.items() if key != "retrieved_at"}
                for row in sequence
            ]

        run_idempotent = strip(second) == strip(rows)
    else:
        run_idempotent = second == rows
    run_idempotent = run_idempotent and client.stats.network_calls == before

    client.stats.cache_entries = sum(
        1 for target in targets if client.cache_path(str(target["inchikey"])).is_file()
    )
    summary = summarize(rows, client.stats, roster_keys=roster_keys, run_idempotent=run_idempotent)
    summary["throttle_seconds_per_request"] = arguments.throttle_seconds
    summary["cache_populated_between_utc"] = cache_population_window(
        arguments.cache_dir, (str(target["inchikey"]) for target in targets)
    )
    print(json.dumps({key: value for key, value in summary.items() if key != "unresolved"}, indent=2))
    if summary["unresolved"]:
        print(f"unresolved: {summary['unresolved_count']}")

    if not arguments.dry_run:
        record = {
            "generated_at_utc": summary["generated_at_utc"],
            "coverage_set": summary["coverage_set"],
            "network_calls": summary["network_calls"],
            "cache_hits": summary["cache_hits"],
            "retries": summary["retries"],
            "throttle_seconds": summary["throttle_seconds"],
            "offline": arguments.offline,
        }
        arguments.harvest_log.parent.mkdir(parents=True, exist_ok=True)
        with open(arguments.harvest_log, "a", encoding="utf-8", newline="") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
        summary["harvest_log_path"] = str(arguments.harvest_log)
        write_rows(arguments.output, rows)
        arguments.summary.parent.mkdir(parents=True, exist_ok=True)
        with open(arguments.summary, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())