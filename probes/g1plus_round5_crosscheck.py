"""G1+ crawl round-5 cross-check of the v0.3 targets against restricted captures.

This probe answers one question per frozen G1+ target: the restricted
SpringerMaterials records that sit near the stored temperature, are they an
independent measurement or a compilation of the very source the dataset already
cites?  Round 5 found that this distinction matters: for the dinitriles the
Landolt-Boernstein / SpringerMaterials record cites the same 2013 ThermoML
paper (Crossref reference-count = 1), so it confirms transcription rather than
independent agreement.

Restricted inputs live under data/restricted/ and are never committed.  Only the
redistribution-safe aggregates produced here are tracked, next to the individual
cross-check values that earlier tracked reports already cite.

Run:  python -m probes.g1plus_round5_crosscheck
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
RESTRICTED_DIR = REPOSITORY_ROOT / "data" / "restricted" / "springer_materials"
DEFAULT_SUMMARY = REPOSITORY_ROOT / "probes" / "g1plus_round5_crosscheck_summary.json"

DATASET = REPOSITORY_ROOT / "data" / "dielectric_v03.csv"
RAW = REPOSITORY_ROOT / "data" / "processed" / "dielectric_raw.csv"

INTERACTIVE_JSON = RESTRICTED_DIR / "interactive_v02_dielectric_export.json"
CATALOG_JSON = RESTRICTED_DIR / "interactive_pure_dielectric_catalog.json"
TARGET_CAPTURE_JSON = RESTRICTED_DIR / "g1_capture.json"
MODERN_VALUES_CSV = RESTRICTED_DIR / "modern_battery_solvent_values.csv"
RESTRICTED_DETAIL = RESTRICTED_DIR / "v03_g1plus_crosscheck.csv"

# Ambient pressure band.  The NMP pressure series runs 100 kPa -> 250 MPa from a
# single reference (Uosaki 1996); only the 100 kPa anchor may be compared with a
# 101.325 kPa dataset row.  A row whose pressure is unknown is treated as ambient
# and counted in smi_pressure_unknown_rows rather than silently accepted.
AMBIENT_PRESSURE_MIN_KPA = 90.0
AMBIENT_PRESSURE_MAX_KPA = 110.0

# The temperature window is CLOSED: a row counts as near the stored temperature
# when |T - T_stored| <= MAX_DELTA_TEMPERATURE_K (the comparison uses ">").
MAX_DELTA_TEMPERATURE_K = 5.0

# DOI -> "Surname (year)" of the measurement the dataset row rests on.  Every
# entry below was re-confirmed against Crossref in round 5; DOIs that were not
# confirmed on Crossref are deliberately left out and reported as unmapped.
DATASET_SOURCE_ATTRIBUTION: dict[str, str] = {
    "10.1021/je300958c": "Swiergiel (2013)",
    "10.1016/j.jct.2008.09.006": "Lago (2009)",
    "10.1016/j.jct.2010.09.008": "Riadigos (2011)",
    "10.1021/j100702a008": "Simeral (1970)",
    "10.1021/je050341y": "Chernyak (2006)",
    "10.1016/j.electacta.2013.01.084": "Perricone (2013)",
    "10.1016/j.tca.2012.10.024": "Rivas (2012)",
}

# Frozen G1+ targets: inchikey -> SpringerMaterials pure-substance names.
G1PLUS_TARGETS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("OOWFYDWAMOKVSF-UHFFFAOYSA-N", ("3-methoxypropionitrile",)),
    ("VAYTZRYEBVHVLE-UHFFFAOYSA-N", ("vinylene carbonate",)),
    (
        "SBLRHMKNNHXPHG-UHFFFAOYSA-N",
        ("4-fluoro-1,3-dioxolan-2-one", "fluoroethylene carbonate"),
    ),
    ("YFNKIDBQEZZDLK-UHFFFAOYSA-N", ("2,5,8,11-tetraoxadodecane",)),
    ("ZUHZGEOKBKGPSW-UHFFFAOYSA-N", ("2,5,8,11,14-pentaoxapentadecane",)),
    ("SBZXBUIDTXKZTM-UHFFFAOYSA-N", ("2,5,8-trioxanonane",)),
    ("BTGRAWJCKBQKAO-UHFFFAOYSA-N", ("hexanedinitrile",)),
    ("ZTOMUSMDRMJOTH-UHFFFAOYSA-N", ("glutaronitrile", "pentanedinitrile")),
    (
        "RUOJZAUFBMNUDX-UHFFFAOYSA-N",
        ("4-methyl-1,3-dioxolan-2-one", "propylene carbonate"),
    ),
    ("KMTRUDSVKNLOMY-UHFFFAOYSA-N", ("1,3-dioxolan-2-one",)),
    ("GAEKPEKOJKCEMS-UHFFFAOYSA-N", ("5-methyloxolan-2-one", "gamma-valerolactone")),
    (
        "XTHFKEDIFFGKHM-UHFFFAOYSA-N",
        ("2,5-dioxahexane", "1,2-dimethoxyethane"),
    ),
    ("HXJUTPCZVOIRIF-UHFFFAOYSA-N", ("sulfolane", "thiolane 1,1-dioxide")),
    ("WEVYAHXRMPXWCK-UHFFFAOYSA-N", ("acetonitrile",)),
    ("WYURNTSHIVDZCO-UHFFFAOYSA-N", ("tetrahydrofuran",)),
    ("SECXISVLQFMRJM-UHFFFAOYSA-N", ("1-methylpyrrolidin-2-one",)),
)

# The last two entries belong to the source-priority pass on review-table rows
# (THF and NMP entered the dataset from an open-access review, not from a
# primary measurement); every other entry is a frozen G1+ target.
SOURCE_PRIORITY_TARGETS: frozenset[str] = frozenset(
    {
        "WYURNTSHIVDZCO-UHFFFAOYSA-N",
        "SECXISVLQFMRJM-UHFFFAOYSA-N",
    }
)


def _normalize(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).casefold()
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = re.sub(r"[^a-z0-9 ,()\-]+", "", value)
    return re.sub(r"\s+", " ", value).strip()


def pure_name(value: str) -> str:
    """Strip the collection prefix/suffix from a SpringerMaterials title."""

    name = re.sub(
        r"^\s*dielectric constant (?:of|for)\s+",
        "",
        value,
        flags=re.IGNORECASE,
    )
    name = re.sub(r"\s*\(pure\)\s*$", "", name, flags=re.IGNORECASE)
    return _normalize(name)


def attribution(label: str) -> str:
    """Normalise a reference label to "Surname (year)".

    Handles diacritics (Swiergiel/Malecki), "et al." and co-author lists such as
    "Simeral & Amey (1970)", always keeping the first listed surname.
    """

    text = unicodedata.normalize("NFKD", label or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    pattern = re.compile(
        r"([A-Za-z][A-Za-z\-']*(?:\s*(?:&|,|and)\s*[A-Za-z][A-Za-z\-']*)*)"
        r"(?:\s+et\.?\s*al\.?)?\s*\((1[6-9]\d{2}|20\d{2})\)"
    )
    match = pattern.search(text)
    if not match:
        return ""
    surname = match.group(1).split()[0]
    return f"{surname[0].upper()}{surname[1:].lower()} ({match.group(2)})"


def _float(value: object) -> float | None:
    if value in {"", None, "-"}:
        return None
    try:
        return float(str(value))
    except ValueError:
        return None


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _describe_detail_path(path: Path) -> str:
    """Describe the restricted detail file even when it lives outside the repo.

    The cross-check is regularly re-run into a scratch directory to prove it is
    reproducible, and a scratch directory is normally outside REPOSITORY_ROOT.
    Path.relative_to raises ValueError in that case, so fall back to the
    resolved absolute path instead of failing the run.
    """

    resolved = path.resolve()
    try:
        return resolved.relative_to(REPOSITORY_ROOT).as_posix()
    except ValueError:
        return resolved.as_posix()


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def load_dataset_rows(path: Path = DATASET) -> dict[str, dict[str, str]]:
    wanted = {key for key, _ in G1PLUS_TARGETS}
    return {
        row["inchikey"]: row
        for row in _read_csv(path)
        if row["inchikey"] in wanted
    }


def load_restricted_observations(
    interactive_path: Path = INTERACTIVE_JSON,
    capture_path: Path = TARGET_CAPTURE_JSON,
    modern_path: Path = MODERN_VALUES_CSV,
) -> list[dict[str, object]]:
    """Return every restricted pure-liquid observation in one flat shape."""

    observations: list[dict[str, object]] = []
    if interactive_path.is_file():
        payload = json.loads(interactive_path.read_text(encoding="utf-8"))
        for dataset in payload.get("datasets", []):
            title = str(dataset.get("title", ""))
            for row in dataset.get("rows", []):
                if not isinstance(row, Mapping):
                    continue
                observations.append(
                    {
                        "capture": "interactive_export",
                        "doc_id": dataset.get("doc_id"),
                        "title": title,
                        "pure_name": pure_name(title),
                        "dielectric": _float(row.get("dielectric")),
                        "pressure_kpa": _float(row.get("pressure_kPa")),
                        "temperature_k": _float(row.get("temperature_K")),
                        "reference": str(row.get("reference", "")),
                        "compilation": str(row.get("compilation", "")),
                    }
                )
    if capture_path.is_file():
        payload = json.loads(capture_path.read_text(encoding="utf-8"))
        for record in payload.get("records", []):
            rows = record.get("rows", [])
            if not rows:
                continue
            header = [str(cell) for cell in rows[0]]
            for row in rows[1:]:
                cells = dict(zip(header, [str(cell) for cell in row], strict=False))
                observations.append(
                    {
                        "capture": "target_capture",
                        "doc_id": record.get("doc_id"),
                        "title": str(record.get("title", record.get("compound", ""))),
                        "pure_name": pure_name(str(record.get("compound", ""))),
                        "dielectric": _float(cells.get("Dielectric Constant")),
                        "pressure_kpa": _float(cells.get("System Pressure\n(kPa)")),
                        "temperature_k": _float(cells.get("System Temperature\n(K)")),
                        "reference": cells.get("Reference", ""),
                        "compilation": cells.get("Compilation", ""),
                    }
                )
    if modern_path.is_file():
        for row in _read_csv(modern_path):
            observations.append(
                {
                    "capture": "modern_battery_values",
                    "doc_id": row.get("candidate_id", ""),
                    "title": row.get("name", ""),
                    "pure_name": _normalize(row.get("name", "")),
                    "dielectric": _float(row.get("dielectric")),
                    "pressure_kpa": None,
                    "temperature_k": _float(row.get("T_K")),
                    "reference": row.get("primary_reference", ""),
                    "compilation": row.get("compilation_reference", ""),
                }
            )
    return observations


def load_catalog(path: Path = CATALOG_JSON) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    return list(payload.get("records", []))


def catalog_lookup(
    catalog: Sequence[Mapping[str, str]],
    names: Iterable[str],
) -> dict[str, object]:
    wanted = {_normalize(name) for name in names}
    hits = [
        record
        for record in catalog
        if pure_name(str(record.get("title", ""))) in wanted
    ]
    system_ids = []
    for record in hits:
        match = re.search(r"systemId=(\d+)", str(record.get("page_link", "")))
        if match:
            system_ids.append(match.group(1))
    return {
        "catalog_present": bool(hits),
        "catalog_doc_ids": [str(record.get("doc_id")) for record in hits],
        "catalog_system_ids": system_ids,
    }


def thermoml_same_temperature_values(
    raw_rows: Sequence[Mapping[str, str]],
    inchikey: str,
    *,
    temperature_k: float,
    max_delta_temperature: float = MAX_DELTA_TEMPERATURE_K,
) -> list[dict[str, object]]:
    """Pure, ambient, zero-frequency ThermoML observations near the target."""

    values: list[dict[str, object]] = []
    for row in raw_rows:
        if row.get("primary_inchi_key") != inchikey:
            continue
        if str(row.get("is_pure", "")).lower() not in {"true", "1"}:
            continue
        temperature = _float(row.get("temperature_k"))
        pressure = _float(row.get("pressure_kpa"))
        dielectric = _float(row.get("value"))
        frequency = _float(row.get("frequency_mhz"))
        if temperature is None or dielectric is None:
            continue
        if abs(temperature - temperature_k) > max_delta_temperature:
            continue
        if pressure is not None and not (
            AMBIENT_PRESSURE_MIN_KPA <= pressure <= AMBIENT_PRESSURE_MAX_KPA
        ):
            continue
        if frequency not in {None, 0.0}:
            continue
        values.append(
            {
                "doi": row.get("doi", ""),
                "temperature_k": temperature,
                "dielectric": dielectric,
                "expanded_uncertainty": _float(row.get("expanded_uncertainty")),
            }
        )
    return values


def dataset_attributions(row: Mapping[str, str]) -> tuple[set[str], list[str]]:
    """Author-year labels the dataset row can be traced to, plus unmapped DOIs."""

    found: set[str] = set()
    unmapped: list[str] = []
    dois = [part for part in (row.get("source_doi", "") or "").split(";") if part]
    for doi in dois:
        label = DATASET_SOURCE_ATTRIBUTION.get(doi.strip())
        if label:
            found.add(label)
        else:
            unmapped.append(doi.strip())
    citation = attribution(row.get("source_citation", ""))
    if citation:
        found.add(citation)
    return found, unmapped


def classify_sources(
    dataset_labels: set[str],
    observed_labels: Iterable[str],
    *,
    row_count: int = 0,
) -> str:
    """Relationship between the dataset row and the restricted observations.

    ``no_capture`` means there was nothing to compare.  ``unattributable_reference``
    means there *were* near rows but not one reference string could be reduced to
    a "Surname (year)" label, so the relationship is unknown rather than absent.
    """

    observed = {label for label in observed_labels if label}
    if not observed:
        return "unattributable_reference" if row_count else "no_capture"
    if not dataset_labels:
        return "unmapped_dataset_source"
    shared = observed & dataset_labels
    if shared and shared == observed:
        return "same_source_confirmation"
    if shared:
        return "mixed_same_and_independent"
    return "independent_sources_only"


def build_crosscheck(
    dataset_rows: Mapping[str, Mapping[str, str]],
    raw_rows: Sequence[Mapping[str, str]],
    observations: Sequence[Mapping[str, object]],
    catalog: Sequence[Mapping[str, str]],
    *,
    max_delta_temperature: float = MAX_DELTA_TEMPERATURE_K,
) -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    for inchikey, names in G1PLUS_TARGETS:
        row = dataset_rows.get(inchikey)
        entry: dict[str, object] = {
            "inchikey": inchikey,
            "smi_names": list(names),
            "group": (
                "source_priority_pass"
                if inchikey in SOURCE_PRIORITY_TARGETS
                else "g1plus"
            ),
            "dataset_present": row is not None,
        }
        entry.update(catalog_lookup(catalog, names))
        if row is None:
            entry["source_relationship"] = "not_in_dataset"
            results.append(entry)
            continue

        temperature_k = float(row["T_K"])
        entry["name"] = row["name"]
        entry["T_K"] = temperature_k
        entry["dielectric"] = float(row["dielectric"])
        entry["evidence_level"] = row.get("evidence_level", "")
        entry["model_ready"] = row.get("model_ready", "")

        dataset_labels, unmapped = dataset_attributions(row)
        entry["dataset_source_labels"] = sorted(dataset_labels)
        entry["unmapped_source_dois"] = unmapped

        thermoml = thermoml_same_temperature_values(
            raw_rows,
            inchikey,
            temperature_k=temperature_k,
            max_delta_temperature=max_delta_temperature,
        )
        entry["thermoml_same_temperature_values"] = thermoml
        entry["thermoml_same_temperature_mean"] = (
            round(sum(item["dielectric"] for item in thermoml) / len(thermoml), 6)
            if thermoml
            else None
        )

        wanted = {_normalize(name) for name in names}
        near: list[dict[str, object]] = []
        pressurised = 0
        unknown_pressure = 0
        for observation in observations:
            if observation.get("pure_name") not in wanted:
                continue
            temperature = observation.get("temperature_k")
            dielectric = observation.get("dielectric")
            if temperature is None or dielectric is None:
                continue
            if not isinstance(temperature, float) or not isinstance(dielectric, float):
                continue
            pressure = observation.get("pressure_kpa")
            if abs(temperature - temperature_k) > max_delta_temperature:
                continue
            if pressure is None:
                unknown_pressure += 1
            elif not (
                AMBIENT_PRESSURE_MIN_KPA <= pressure <= AMBIENT_PRESSURE_MAX_KPA
            ):
                pressurised += 1
                continue
            near.append(
                {
                    "capture": observation.get("capture", ""),
                    "doc_id": observation.get("doc_id"),
                    "temperature_k": temperature,
                    "dielectric": dielectric,
                    "reference": observation.get("reference", ""),
                    "compilation": observation.get("compilation", ""),
                }
            )
        entry["smi_near_rows"] = len(near)
        by_capture: dict[str, int] = {}
        for item in near:
            key = str(item.get("capture", ""))
            by_capture[key] = by_capture.get(key, 0) + 1
        entry["smi_near_rows_by_capture"] = by_capture
        entry["smi_pressurised_rows_excluded"] = pressurised
        entry["smi_pressure_unknown_rows"] = unknown_pressure
        entry["smi_unattributable_rows"] = sum(
            1
            for item in near
            if str(item.get("reference", "")) and not attribution(str(item["reference"]))
        )
        entry["smi_reference_labels"] = sorted(
            {attribution(str(item["reference"])) for item in near if item["reference"]}
        )
        entry["source_relationship"] = classify_sources(
            dataset_labels,
            (attribution(str(item["reference"])) for item in near),
            row_count=len(near),
        )
        if near:
            dielectric_values = sorted(float(item["dielectric"]) for item in near)
            middle = len(dielectric_values) // 2
            median = (
                dielectric_values[middle]
                if len(dielectric_values) % 2
                else round(
                    (dielectric_values[middle - 1] + dielectric_values[middle]) / 2,
                    6,
                )
            )
            entry["smi_near_median"] = median
            entry["smi_near_min"] = dielectric_values[0]
            entry["smi_near_max"] = dielectric_values[-1]
        results.append(entry)
    return results


def _restricted_detail_rows(
    dataset_rows: Mapping[str, Mapping[str, str]],
    observations: Sequence[Mapping[str, object]],
    *,
    max_delta_temperature: float,
) -> list[dict[str, object]]:
    detail: list[dict[str, object]] = []
    for inchikey, names in G1PLUS_TARGETS:
        row = dataset_rows.get(inchikey)
        if row is None:
            continue
        temperature_k = float(row["T_K"])
        wanted = {_normalize(name) for name in names}
        for observation in observations:
            if observation.get("pure_name") not in wanted:
                continue
            temperature = observation.get("temperature_k")
            dielectric = observation.get("dielectric")
            if not isinstance(temperature, float) or not isinstance(dielectric, float):
                continue
            if abs(temperature - temperature_k) > max_delta_temperature:
                continue
            detail.append(
                {
                    "inchikey": inchikey,
                    "dataset_name": row["name"],
                    "dataset_T_K": f"{temperature_k:.6g}",
                    "dataset_dielectric": row["dielectric"],
                    "doc_id": observation.get("doc_id"),
                    "capture": observation.get("capture", ""),
                    "smi_T_K": f"{temperature:.6g}",
                    "smi_dielectric": f"{dielectric:.6g}",
                    "smi_pressure_kPa": observation.get("pressure_kpa"),
                    "smi_reference": observation.get("reference", ""),
                    "smi_compilation": observation.get("compilation", ""),
                }
            )
    return detail


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--detail", type=Path, default=RESTRICTED_DETAIL)
    parser.add_argument("--max-delta-temperature", type=float, default=MAX_DELTA_TEMPERATURE_K)
    args = parser.parse_args(argv)

    dataset_rows = load_dataset_rows()
    raw_rows = _read_csv(RAW)
    restricted_available = (
        INTERACTIVE_JSON.is_file()
        or TARGET_CAPTURE_JSON.is_file()
        or MODERN_VALUES_CSV.is_file()
    )
    observations = load_restricted_observations() if restricted_available else []
    catalog = load_catalog()

    crosscheck = build_crosscheck(
        dataset_rows,
        raw_rows,
        observations,
        catalog,
        max_delta_temperature=args.max_delta_temperature,
    )

    detail_rows = (
        _restricted_detail_rows(
            dataset_rows,
            observations,
            max_delta_temperature=args.max_delta_temperature,
        )
        if observations
        else []
    )
    if detail_rows:
        args.detail.parent.mkdir(parents=True, exist_ok=True)
        with args.detail.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(detail_rows[0]))
            writer.writeheader()
            writer.writerows(detail_rows)

    summary = {
        "schema_version": 1,
        "probe": "g1plus_round5_crosscheck",
        "source": "SpringerMaterials Interactive (restricted) + local ThermoML extraction",
        "redistribution_status": "aggregates_only",
        "max_delta_temperature_K": args.max_delta_temperature,
        "ambient_pressure_window_kPa": [
            AMBIENT_PRESSURE_MIN_KPA,
            AMBIENT_PRESSURE_MAX_KPA,
        ],
        "dataset_path": DATASET.relative_to(REPOSITORY_ROOT).as_posix(),
        "dataset_sha256": sha256_file(DATASET),
        "raw_path": RAW.relative_to(REPOSITORY_ROOT).as_posix(),
        "raw_sha256": sha256_file(RAW),
        "restricted_inputs_available": restricted_available,
        "restricted_detail_path": (
            _describe_detail_path(args.detail) if detail_rows else None
        ),
        "results": crosscheck,
        "relationship_counts": {
            label: sum(
                1 for entry in crosscheck if entry["source_relationship"] == label
            )
            for label in sorted(
                {str(entry["source_relationship"]) for entry in crosscheck}
            )
        },
    }
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps(summary["relationship_counts"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
