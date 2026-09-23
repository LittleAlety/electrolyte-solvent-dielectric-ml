"""Audit local and public dielectric-data sources without promoting search hits to data."""

from __future__ import annotations

import argparse
import csv
import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path

import requests

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
AUDIT_FIELDS = (
    "source",
    "source_type",
    "access_status",
    "query",
    "result_count",
    "known_trainable_additions",
    "decision",
    "evidence",
)
USER_AGENT = "electrolyte-ml-dielectric-audit/1.0"


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv_rows(
    path: Path,
    fieldnames: Sequence[str],
    rows: Sequence[Mapping[str, object]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _local_nbs_audit(root: Path) -> dict[str, object]:
    rows = read_csv_rows(root / "data" / "processed" / "nbs514_structure_candidates.csv")
    eligible = [row for row in rows if row["selection_eligible"].lower() == "true"]
    selected = [row for row in rows if row["selected_for_v02"].lower() == "true"]
    additional = [row for row in eligible if row["selected_for_v02"].lower() != "true"]
    return {
        "candidate_count": len(rows),
        "eligible_count": len(eligible),
        "selected_count": len(selected),
        "additional_eligible_count": len(additional),
        "additional_names": [row["compound_name"] for row in additional],
    }


def _local_context(root: Path) -> dict[str, object]:
    nbs = _local_nbs_audit(root)
    v02 = read_csv_rows(root / "data" / "dielectric_v02.csv")
    landolt = read_csv_rows(
        root / "data" / "processed" / "landolt_boernstein_2015_pure_liquid_queue.csv"
    )
    springer_summary_path = (
        root / "probes" / "springer_materials_crosscheck_summary.json"
    )
    springer_summary = (
        json.loads(springer_summary_path.read_text(encoding="utf-8"))
        if springer_summary_path.is_file()
        else {}
    )
    expansion_summary_path = root / "probes" / "data_expansion_summary.json"
    expansion_summary = (
        json.loads(expansion_summary_path.read_text(encoding="utf-8"))
        if expansion_summary_path.is_file()
        else {}
    )
    return {
        "v02_count": len(v02),
        "nbs514": nbs,
        "landolt_queue_count": len(landolt),
        "springer_summary": springer_summary,
        "expansion_summary": expansion_summary,
    }


def _fetch_json(
    url: str,
    *,
    params: Mapping[str, object] | None = None,
) -> dict[str, object]:
    response = requests.get(
        url,
        params=params,
        headers={"User-Agent": USER_AGENT},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise TypeError(f"expected JSON object from {url}")
    return payload


def _crossref_audit() -> dict[str, object]:
    payload = _fetch_json(
        "https://api.crossref.org/works",
        params={
            "query.title": "static dielectric constant pure liquids",
            "filter": "type:dataset",
            "rows": 5,
        },
    )
    message = payload["message"]
    records = message.get("items", [])
    return {
        "status": "reachable",
        "result_count": int(message.get("total-results", 0)),
        "top_records": [
            {
                "doi": record.get("DOI"),
                "title": " ".join(record.get("title", [])),
            }
            for record in records
            if isinstance(record, dict)
        ],
    }


def _datacite_audit() -> dict[str, object]:
    payload = _fetch_json(
        "https://api.datacite.org/dois",
        params={
            "query": "relative permittivity pure liquids dataset",
            "page[size]": 5,
        },
    )
    data = payload.get("data", [])
    return {
        "status": "reachable",
        "result_count": int(payload.get("meta", {}).get("total", 0)),
        "top_records": [
            {
                "doi": record.get("id"),
                "title": (
                    record.get("attributes", {}).get("titles", [{}])[0].get("title")
                    if isinstance(record, dict)
                    else None
                ),
            }
            for record in data
            if isinstance(record, dict)
        ],
    }


def _zenodo_audit() -> dict[str, object]:
    payload = _fetch_json(
        "https://zenodo.org/api/records",
        params={"q": "relative permittivity pure liquids dataset", "size": 5},
    )
    hits = payload.get("hits", {})
    records = hits.get("hits", [])
    return {
        "status": "reachable",
        "result_count": int(hits.get("total", 0)),
        "top_records": [
            {
                "doi": record.get("doi"),
                "title": record.get("metadata", {}).get("title"),
            }
            for record in records
            if isinstance(record, dict)
        ],
    }


def _safe_remote(name: str, function) -> dict[str, object]:
    try:
        result = function()
    except Exception as error:  # noqa: BLE001
        return {
            "status": "unavailable",
            "error": f"{type(error).__name__}: {error}",
        }
    return {"status": "reachable", **result}


def build_audit(root: Path) -> dict[str, object]:
    local = _local_context(root)
    nbs = local["nbs514"]
    remote = {
        "crossref": _safe_remote("crossref", _crossref_audit),
        "datacite": _safe_remote("datacite", _datacite_audit),
        "zenodo": _safe_remote("zenodo", _zenodo_audit),
    }
    rows: list[dict[str, object]] = [
        {
            "source": "dielectric_v02",
            "source_type": "local_training_dataset",
            "access_status": "available",
            "query": "committed pure-liquid relative-permittivity table",
            "result_count": local["v02_count"],
            "known_trainable_additions": 0,
            "decision": "current_training_base",
            "evidence": "data/dielectric_v02.csv",
        },
        {
            "source": "NBS Circular 514",
            "source_type": "local_public_candidate_pool",
            "access_status": "available",
            "query": "all resolved and selection-eligible records",
            "result_count": nbs["candidate_count"],
            "known_trainable_additions": 0,
            "decision": "four_candidates_pending_manual_review",
            "evidence": (
                f"{nbs['eligible_count']} eligible, {nbs['selected_count']} already "
                f"selected, {nbs['additional_eligible_count']} additional eligible "
                "but not yet promoted"
            ),
        },
        {
            "source": "Landolt-Bornstein 2015",
            "source_type": "closed_manual_queue",
            "access_status": "subscription_required",
            "query": "pure-liquid static dielectric chapter queue",
            "result_count": local["landolt_queue_count"],
            "known_trainable_additions": 0,
            "decision": "manual_transcription_only",
            "evidence": (
                "data/processed/landolt_boernstein_2015_pure_liquid_queue.csv"
            ),
        },
        {
            "source": "SpringerMaterials",
            "source_type": "restricted_crosscheck",
            "access_status": "authenticated_local_capture",
            "query": "name-matched dielectric datasets",
            "result_count": local["springer_summary"].get("matched_compounds", 0),
            "known_trainable_additions": 0,
            "decision": "crosscheck_only_do_not_promote_restricted_rows",
            "evidence": "data/restricted/springer_materials/",
        },
    ]
    expansion = local["expansion_summary"]
    nist = expansion.get("nist", {})
    chalklab = expansion.get("chalklab", {})
    chemdata = expansion.get("chemdataextractor", {})
    rows.extend(
        (
            {
                "source": "NIST ThermoML local snapshot",
                "source_type": "local_public_observations",
                "access_status": "available",
                "query": "relative permittivity at constant frequency",
                "result_count": nist.get("observations", 0),
                "known_trainable_additions": 0,
                "decision": "already_represented_in_v01_and_v02",
                "evidence": (
                    f"{nist.get('near_298_pure_keys', 0)} near-298 pure keys; "
                    "probes/data_expansion_summary.json"
                ),
            },
            {
                "source": "ChalkLab archive",
                "source_type": "local_public_archive",
                "access_status": "available",
                "query": "zero-frequency pure compounds",
                "result_count": chalklab.get("zero_frequency_pure_all_temperature", 0),
                "known_trainable_additions": 0,
                "decision": "no_new_near_room_training_compounds",
                "evidence": (
                    f"{chalklab.get('zero_frequency_pure_new', 0)} all-temperature "
                    f"new; {chalklab.get('zero_frequency_pure_near_298_new', 0)} "
                    "near-298 new"
                ),
            },
            {
                "source": "ChemDataExtractor",
                "source_type": "text_mined_records",
                "access_status": "available",
                "query": "dielectric records without independent temperature",
                "result_count": chemdata.get("records", 0),
                "known_trainable_additions": 0,
                "decision": "candidate_discovery_only",
                "evidence": f"{chemdata.get('compounds', 0)} compounds; no independent T",
            },
        )
    )
    for source, result in remote.items():
        rows.append(
            {
                "source": source,
                "source_type": "metadata_search",
                "access_status": result.get("status"),
                "query": "relative-permittivity / pure-liquid dataset search",
                "result_count": result.get("result_count", 0),
                "known_trainable_additions": 0,
                "decision": "requires_artifact_review_before_any_count",
                "evidence": json.dumps(result, ensure_ascii=False),
            }
        )
    return {
        "schema_version": 1,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "local_context": local,
        "remote": remote,
        "conclusion": (
            "No audited public source provides an automatic path to 300-400 "
            "training compounds. NBS Circular 514 has only four additional "
            "eligible resolved records beyond the current v0.2 selection."
        ),
        "rows": rows,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=REPOSITORY_ROOT)
    parser.add_argument(
        "--csv-output",
        type=Path,
        default=REPOSITORY_ROOT / "data" / "processed" / "database_recheck.csv",
    )
    parser.add_argument(
        "--json-output",
        type=Path,
        default=REPOSITORY_ROOT / "probes" / "database_recheck.json",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    result = build_audit(args.root)
    write_csv_rows(args.csv_output, AUDIT_FIELDS, result["rows"])
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
