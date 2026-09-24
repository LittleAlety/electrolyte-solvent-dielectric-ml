"""Build dielectric v0.3 from v0.2 plus audited public observations."""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import unicodedata
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from types import MappingProxyType
from typing import NamedTuple
from urllib.parse import unquote, urlsplit

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from electrolyte_ml.exporting import canonical_text_sha256
from electrolyte_ml.pathing import portable_relative_path

PUBLIC_REDISTRIBUTION_STATUSES = {"allowed", "public_domain"}
REVIEW_LICENSE_FIELDS = (
    "source_license",
    "license_url",
    "redistribution_conditions",
)
REVIEW_METADATA_FIELDS = (*REVIEW_LICENSE_FIELDS, "redistribution_status")
SOURCE_DOI_SEPARATOR = ";"
DOI_RESOLVER_HOSTS = frozenset({"doi.org", "dx.doi.org", "www.doi.org"})
DOI_PREFIX_PATTERN = re.compile(r"10\.\d{4,9}/")
SUPPLEMENTARY_PUBLIC_DOMAIN_DOIS = frozenset(
    {
        "10.6028/nbs.circ.514",
    }
)
PERCENT_ESCAPE_PATTERN = re.compile(r"%[0-9A-Fa-f]{2}")
PROVENANCE_PATCH_REQUIRED_FIELDS = ("inchikey", "field", "value", "rationale")
PROVENANCE_PATCH_PROTECTED_FIELDS = frozenset(
    {
        "inchikey",
        "name",
        "smiles",
        "dielectric",
        "T_K",
        "temperature_band",
        "model_ready",
        "dataset_origin",
    }
)
DOI_ASCII_CHARACTER = re.compile(r"[a-z0-9./:_-]")
MAX_UNQUOTE_PASSES = 8


def decode_percent_sequences(value: str) -> tuple[str, bool]:
    """Decode nested URL encoding and report unresolved percent escapes."""

    decoded = str(value)
    for _ in range(MAX_UNQUOTE_PASSES):
        decoded_next = unquote(decoded)
        if decoded_next == decoded:
            break
        decoded = decoded_next
    malformed = bool(PERCENT_ESCAPE_PATTERN.search(decoded))
    return decoded, malformed


def normalized_detection_text(value: str) -> str:
    """Normalize text for DOI containment detection."""

    decoded, _ = decode_percent_sequences(value)
    normalized = unicodedata.normalize(
        "NFKC",
        decoded,
    ).casefold()
    return "".join(
        character
        for character in normalized
        if DOI_ASCII_CHARACTER.fullmatch(character)
    )


def _without_doi_prefix(value: str) -> str:
    candidate = str(value).strip()
    if candidate[:4].casefold() == "doi:":
        candidate = candidate[4:].lstrip()
    return candidate


def _parsed_hostname(parsed) -> str:
    try:
        return (parsed.hostname or "").rstrip(".").casefold()
    except ValueError:
        return ""


def _url_like_parts(value: str) -> tuple[bool, str, str]:
    candidate = _without_doi_prefix(value)
    parsed = urlsplit(candidate)
    scheme = parsed.scheme.casefold()
    if scheme in {"http", "https"}:
        return True, _parsed_hostname(parsed), parsed.path
    if candidate.startswith("//"):
        network = urlsplit(candidate)
        return True, _parsed_hostname(network), network.path
    if DOI_PREFIX_PATTERN.match(normalized_detection_text(candidate)):
        return False, "", ""

    network = urlsplit(f"//{candidate}")
    host = _parsed_hostname(network)
    if "." in host and "/" in candidate:
        return True, host, network.path
    return False, "", ""


def canonicalize_doi(token: str) -> str:
    """Normalize DOI tokens and resolver URLs into a comparison key."""

    candidate = _without_doi_prefix(token)
    url_like, host, path = _url_like_parts(candidate)
    if url_like and host in DOI_RESOLVER_HOSTS:
        decoded_path, _ = decode_percent_sequences(path)
        candidate = decoded_path.strip("/")
    return normalized_detection_text(candidate)


class ReviewLicenseMetadata(NamedTuple):
    source_license: str
    license_url: str
    redistribution_conditions: str
    redistribution_status: str


REVIEW_LICENSE_METADATA = MappingProxyType(
    {
        "10.1002/smll.202504276": ReviewLicenseMetadata(
            "CC BY 4.0",
            "https://creativecommons.org/licenses/by/4.0/",
            "allowed_with_attribution",
            "allowed",
        ),
        "10.1002/smtd.202400183": ReviewLicenseMetadata(
            "CC BY-NC-ND 4.0",
            "https://creativecommons.org/licenses/by-nc-nd/4.0/",
            "allowed_noncommercial_no_derivatives",
            "allowed",
        ),
        "10.1039/d5sc06221g": ReviewLicenseMetadata(
            "CC BY 3.0",
            "https://creativecommons.org/licenses/by/3.0/",
            "allowed_with_attribution",
            "allowed",
        ),
        "10.1002/cssc.202402091": ReviewLicenseMetadata(
            "CC BY-NC 4.0",
            "https://creativecommons.org/licenses/by-nc/4.0/",
            "allowed_noncommercial",
            "allowed",
        ),
        "10.1016/j.isci.2026.115778": ReviewLicenseMetadata(
            "CC BY-NC 4.0",
            "https://creativecommons.org/licenses/by-nc/4.0/",
            "allowed_noncommercial",
            "allowed",
        ),
        "10.1002/adma.73388": ReviewLicenseMetadata(
            "CC BY 4.0",
            "https://creativecommons.org/licenses/by/4.0/",
            "allowed_with_attribution",
            "allowed",
        ),
    }
)

ROOM_TEMPERATURE_RANGE_K = (293.15, 303.15)
EXTENDED_TEMPERATURE_RANGE_K = (313.15, 323.15)
ADDITION_REQUIRED_FIELDS = (
    "inchikey",
    "smiles",
    "name",
    "T_K",
    "dielectric",
    "source_doi",
    "source_url",
    "source_citation",
    "source_table",
    "source_quality",
    "redistribution_status",
)
V03_FIELDS = (
    "dataset_origin",
    "temperature_band",
    "evidence_level",
    "temperature_source",
    "model_ready",
    "conflict_status",
    "source_url",
    "source_citation",
    "source_table",
    "redistribution_status",
    "source_license",
    "license_url",
    "redistribution_conditions",
    "notes",
)


def read_csv_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or ()), list(reader)


def write_csv_rows(
    path: Path,
    fieldnames: Sequence[str],
    rows: Sequence[Mapping[str, object]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fieldnames,
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def temperature_band(temperature_k: float) -> str:
    room_min, room_max = ROOM_TEMPERATURE_RANGE_K
    if room_min <= temperature_k <= room_max:
        return "room_temperature"
    extended_min, extended_max = EXTENDED_TEMPERATURE_RANGE_K
    if extended_min <= temperature_k <= extended_max:
        return "extended_temperature"
    raise ValueError(f"unsupported v0.3 temperature: {temperature_k} K")


def source_dois(row: Mapping[str, str]) -> tuple[str, ...]:
    """Return unique DOIs from source_doi and semicolon-separated source_dois_all."""

    values = (
        str(row.get("source_doi", "")),
        str(row.get("source_dois_all", "")),
    )
    dois = []
    for value in values:
        for doi in value.split(SOURCE_DOI_SEPARATOR):
            canonical_doi = canonicalize_doi(doi)
            if canonical_doi:
                dois.append(canonical_doi)
    return tuple(dict.fromkeys(dois))


def source_doi_format_errors(row: Mapping[str, str]) -> list[str]:
    """Reject hidden multi-DOI values and non-whitelisted resolver URLs."""

    raw_value = str(row.get("source_dois_all", ""))
    if not raw_value.strip():
        return []

    errors = []
    for token_index, token in enumerate(
        raw_value.split(SOURCE_DOI_SEPARATOR),
        start=1,
    ):
        stripped_token = token.strip()
        if not stripped_token:
            errors.append(f"source_dois_all token {token_index} is empty")
            continue
        if "," in stripped_token or "|" in stripped_token:
            errors.append(
                f"source_dois_all token {token_index} uses an unsupported separator"
            )

        detection_text = normalized_detection_text(stripped_token)
        if len(DOI_PREFIX_PATTERN.findall(detection_text)) > 1:
            errors.append(
                f"source_dois_all token {token_index} contains multiple DOI values"
            )

        url_like, host, _ = _url_like_parts(stripped_token)
        if url_like and host not in DOI_RESOLVER_HOSTS:
            errors.append(
                f"source_dois_all token {token_index} uses a non-whitelisted "
                f"DOI resolver URL: {host or stripped_token}"
            )
    return errors


def source_doi_encoding_errors(row: Mapping[str, str]) -> list[str]:
    """Report unresolved percent escapes in either DOI source field."""

    errors = []
    for field in ("source_doi", "source_dois_all"):
        _, malformed = decode_percent_sequences(str(row.get(field, "")))
        if malformed:
            errors.append(f"{field} contains unresolved percent-encoded octets")
    return errors


def review_license_errors(row: Mapping[str, str]) -> list[str]:
    """Return mapped-license and unsupported-review errors for one final row."""

    errors = source_doi_encoding_errors(row)
    errors.extend(source_doi_format_errors(row))
    detection_text = normalized_detection_text(
        " ".join(
            (
                str(row.get("source_doi", "")),
                str(row.get("source_dois_all", "")),
            )
        )
    )
    mapped_dois = [
        doi
        for doi in REVIEW_LICENSE_METADATA
        if doi in detection_text
    ]
    dois = source_dois(row)
    unknown_dois = []
    for doi in dois:
        if doi in SUPPLEMENTARY_PUBLIC_DOMAIN_DOIS:
            # Public-domain compilations (e.g. NBS Circular 514) may be cited
            # alongside a review-table row as independent corroboration.  They
            # carry no CC licence metadata, so they are exempt from the
            # review-DOI allowlist; the review DOI itself is still checked.
            continue
        expected = REVIEW_LICENSE_METADATA.get(doi)
        if expected is None:
            unknown_dois.append(doi)
            continue
        if doi not in mapped_dois:
            mapped_dois.append(doi)

    for doi in mapped_dois:
        expected = REVIEW_LICENSE_METADATA[doi]
        for field, expected_value in zip(
            REVIEW_METADATA_FIELDS,
            expected,
            strict=True,
        ):
            actual_value = str(row.get(field, ""))
            if not actual_value:
                errors.append(f"missing {field} for {doi}")
            elif actual_value != expected_value:
                errors.append(
                    f"{field} mismatch for {doi}: "
                    f"{actual_value!r} != expected {expected_value!r}"
                )

    is_review_addition = str(row.get("source_quality", "")).startswith(
        "open_access"
    ) or any(row.get(field) for field in REVIEW_LICENSE_FIELDS)
    if is_review_addition:
        if unknown_dois:
            errors.extend(
                f"unsupported review source_doi: {doi}"
                for doi in unknown_dois
            )
        elif not mapped_dois:
            errors.append("unsupported review source_doi: missing")
    return errors


def v03_license_errors(rows: Sequence[Mapping[str, str]]) -> list[str]:
    """Validate mapped DOI metadata across the complete final v0.3 row set."""

    errors = []
    for index, row in enumerate(rows, start=1):
        row_errors = review_license_errors(row)
        if not row_errors:
            continue
        row_label = str(row.get("inchikey", "")).strip() or f"row {index}"
        errors.extend(
            f"{row_label}: {error}"
            for error in row_errors
        )
    return errors


def _normalized_addition(row: Mapping[str, str]) -> dict[str, str]:
    missing = [field for field in ADDITION_REQUIRED_FIELDS if not row.get(field)]
    if missing:
        raise ValueError(f"addition is missing required fields: {', '.join(missing)}")
    redistribution_status = row["redistribution_status"]
    if redistribution_status not in PUBLIC_REDISTRIBUTION_STATUSES:
        raise ValueError(
            f"restricted observation cannot enter public v0.3: {row['name']}"
        )
    temperature_k = float(row["T_K"])
    dielectric = float(row["dielectric"])
    if temperature_k <= 0 or dielectric < 1:
        raise ValueError(f"nonphysical addition: {row['name']}")
    output = dict(row)
    output["dataset_origin"] = "v0.3_addition"
    output["temperature_band"] = temperature_band(temperature_k)
    output.setdefault("evidence_level", "primary")
    output.setdefault("temperature_source", "reported")
    output.setdefault("model_ready", "true")
    output.setdefault("conflict_status", "")
    return output


def apply_provenance_patches(
    rows: Sequence[Mapping[str, str]],
    patches: Sequence[Mapping[str, str]],
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Apply auditable row-level provenance overrides to assembled rows.

    Every patch names one InChIKey and one field, and carries its own
    rationale.  Patches are rejected when they target an unknown compound, a
    protected field, or an already-patched field.  Keeping provenance fixes in
    a checked-in patch file makes them reproducible from the build inputs, so
    regenerating the dataset cannot silently drop them -- which is exactly how
    the v0.3.2 revision reverted an earlier NBS upgrade.
    """

    patched = [dict(row) for row in rows]
    index = {row["inchikey"]: row for row in patched}
    seen: set[tuple[str, str]] = set()
    applied: list[dict[str, str]] = []
    for position, patch in enumerate(patches, start=1):
        missing = [
            field
            for field in PROVENANCE_PATCH_REQUIRED_FIELDS
            if not str(patch.get(field, "")).strip()
        ]
        if missing:
            raise ValueError(
                f"provenance patch {position} is missing: {', '.join(missing)}"
            )
        inchikey = patch["inchikey"].strip()
        field = patch["field"].strip()
        if field in PROVENANCE_PATCH_PROTECTED_FIELDS:
            raise ValueError(
                f"provenance patch {position} targets protected field {field!r}"
            )
        row = index.get(inchikey)
        if row is None:
            raise ValueError(
                f"provenance patch {position} targets unknown compound {inchikey}"
            )
        key = (inchikey, field)
        if key in seen:
            raise ValueError(
                f"provenance patch {position} repeats {inchikey} / {field}"
            )
        seen.add(key)
        previous = str(row.get(field, ""))
        row[field] = patch["value"]
        applied.append(
            {
                "inchikey": inchikey,
                "name": str(row.get("name", "")),
                "field": field,
                "previous_value": previous,
                "value": patch["value"],
                "rationale": patch["rationale"].strip(),
            }
        )
    return patched, applied


def build_v03_rows(
    v02_rows: Sequence[Mapping[str, str]],
    additions: Sequence[Mapping[str, str]],
    *,
    minimum_additions: int,
    excluded_model_keys: set[str] | None = None,
) -> list[dict[str, str]]:
    if len(additions) < minimum_additions:
        raise ValueError(
            f"v0.3 needs at least {minimum_additions} additions; found {len(additions)}"
        )

    excluded_model_keys = excluded_model_keys or set()
    rows = []
    for row in v02_rows:
        excluded = row["inchikey"] in excluded_model_keys
        rows.append(
            {
                **row,
                "dataset_origin": "v0.2",
                "temperature_band": temperature_band(float(row["T_K"])),
                "evidence_level": "v0.2_primary_or_critical_compilation",
                "temperature_source": "reported",
                "model_ready": "false" if excluded else "true",
                "conflict_status": (
                    "excluded_model_conflict" if excluded else ""
                ),
            }
        )
    keys = [row["inchikey"] for row in rows]
    for addition in additions:
        normalized = _normalized_addition(addition)
        if normalized["inchikey"] in excluded_model_keys:
            normalized["model_ready"] = "false"
            if not normalized["conflict_status"]:
                normalized["conflict_status"] = "excluded_model_conflict"
        if normalized["inchikey"] in keys:
            raise ValueError(f"duplicate InChIKey in v0.3: {normalized['inchikey']}")
        keys.append(normalized["inchikey"])
        rows.append(normalized)
    final_license_errors = v03_license_errors(rows)
    if final_license_errors:
        raise ValueError(
            "invalid v0.3 license metadata: "
            f"{'; '.join(final_license_errors)}"
        )
    return rows


def _parse_args() -> argparse.Namespace:
    data_dir = REPOSITORY_ROOT / "data"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--v02", type=Path, default=data_dir / "dielectric_v02.csv")
    parser.add_argument(
        "--additions",
        type=Path,
        default=data_dir
        / "processed"
        / "modern_solvent_public_observations.csv",
    )
    parser.add_argument(
        "--review-additions",
        type=Path,
        default=data_dir
        / "processed"
        / "modern_solvent_public_review_observations.csv",
    )
    parser.add_argument(
        "--model-exclusions",
        type=Path,
        default=data_dir / "processed" / "dielectric_v03_exclusions.csv",
    )
    parser.add_argument("--output", type=Path, default=data_dir / "dielectric_v03.csv")
    parser.add_argument(
        "--summary",
        type=Path,
        default=REPOSITORY_ROOT / "probes" / "dielectric_v03_summary.json",
    )
    parser.add_argument(
        "--provenance-patches",
        type=Path,
        default=data_dir / "processed" / "dielectric_v03_provenance_patches.csv",
    )
    parser.add_argument("--minimum-additions", type=int, default=30)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    v02_fields, v02_rows = read_csv_rows(args.v02)
    _, addition_rows = read_csv_rows(args.additions)
    _, review_addition_rows = read_csv_rows(args.review_additions)
    all_addition_rows = [*addition_rows, *review_addition_rows]
    _, exclusion_rows = read_csv_rows(args.model_exclusions)
    excluded_model_keys = {row["inchikey"] for row in exclusion_rows}
    rows = build_v03_rows(
        v02_rows,
        all_addition_rows,
        minimum_additions=args.minimum_additions,
        excluded_model_keys=excluded_model_keys,
    )
    patch_rows: list[dict[str, str]] = []
    if args.provenance_patches.is_file():
        _, patch_rows = read_csv_rows(args.provenance_patches)
    rows, applied_patches = apply_provenance_patches(rows, patch_rows)
    patched_license_errors = v03_license_errors(rows)
    if patched_license_errors:
        raise ValueError(
            "invalid v0.3 license metadata after provenance patches: "
            f"{'; '.join(patched_license_errors)}"
        )
    fields = list(v02_fields)
    fields.extend(field for field in V03_FIELDS if field not in fields)
    write_csv_rows(args.output, fields, rows)

    source_counts = Counter(row["dataset_origin"] for row in rows)
    band_counts = Counter(row["temperature_band"] for row in rows)
    evidence_counts = Counter(
        row.get("evidence_level", "v0.2") for row in rows
    )
    model_ready_count = sum(
        row.get("dataset_origin") == "v0.3_addition"
        and row.get("model_ready", "true").lower() == "true"
        for row in rows
    )
    conflict_count = sum(
        bool(row.get("conflict_status"))
        and row.get("dataset_origin") == "v0.3_addition"
        for row in rows
    )
    summary = {
        "schema_version": 3,
        "dataset_version": "0.3",
        "compound_count": len(rows),
        "v02_compound_count": len(v02_rows),
        "addition_count": len(all_addition_rows),
        "model_ready_addition_count": model_ready_count,
        "conflict_addition_count": conflict_count,
        "source_counts": dict(sorted(source_counts.items())),
        "evidence_counts": dict(sorted(evidence_counts.items())),
        "temperature_band_counts": dict(sorted(band_counts.items())),
        "temperature_ranges_K": {
            "room_temperature": list(ROOM_TEMPERATURE_RANGE_K),
            "extended_temperature": list(EXTENDED_TEMPERATURE_RANGE_K),
        },
        "provenance_patches": {
            "path": str(args.provenance_patches),
            "applied_count": len(applied_patches),
            "applied": applied_patches,
        },
        "inputs": {
            "provenance_patches_sha256": (
                canonical_text_sha256(args.provenance_patches)
                if args.provenance_patches.is_file()
                else None
            ),
            "v02_sha256": canonical_text_sha256(args.v02),
            "additions_sha256": canonical_text_sha256(args.additions),
            "review_additions_sha256": canonical_text_sha256(
                args.review_additions
            ),
            "model_exclusions_sha256": canonical_text_sha256(
                args.model_exclusions
            ),
        },
        "output": {
            "path": portable_relative_path(args.output, root=REPOSITORY_ROOT),
            "sha256": canonical_text_sha256(args.output),
        },
        "status": "built; independent verification required",
    }
    write_json(args.summary, summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
