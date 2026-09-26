"""Independent verifier for the eta-epsilon joint observation table.

This module recomputes what it can from the sources instead of trusting the
builder's summary.  The expected 27-column schema is read from the locked
``probes/eta_epsilon_joint_schema_prereg.json``, the source-row universe is
re-enumerated from the files, and the manifest is rebuilt from the bytes on
disk.

It implements the whole of ``verification_contract.checks``:

1. every required column is present and non-empty according to its rule;
2. ``unit`` is consistent with ``property`` on every row;
3. ``pure_or_mixture`` agrees with ``n_components``;
4. ``quality_layer=publishable_core`` implies a measurement ``source_kind`` and
   a non-empty ``source_doi``;
5. ``redistributable=false`` rows are enumerated by source in the manifest;
6. the primary key has no duplicates;
7. every excluded row has an exclusion record;

plus a SHA256 manifest over the built table, the exclusions file and the builder
script, and four supplementary checks (enum integrity, row digests against the
sources, summary agreement and the evaluation contract).

Usage::

    python probes/verify_eta_epsilon_joint_table.py [--table PATH] [--exclusions PATH]

Exit code 0 means PASS, 1 means FAIL.  Nothing here writes to the repository.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

PREREG_PATH = REPOSITORY_ROOT / "probes" / "eta_epsilon_joint_schema_prereg.json"
DEFAULT_TABLE_PATH = REPOSITORY_ROOT / "data" / "processed" / "eta_epsilon_joint_observations.csv"
DEFAULT_EXCLUSIONS_PATH = (
    REPOSITORY_ROOT / "data" / "processed" / "eta_epsilon_joint_exclusions.csv"
)
DEFAULT_SUMMARY_PATH = REPOSITORY_ROOT / "probes" / "eta_epsilon_joint_summary.json"
BUILDER_PATH = REPOSITORY_ROOT / "probes" / "build_eta_epsilon_joint_table.py"

PUBCHEM_SUFFIX = ".experimental_properties.json"

SOURCES: tuple[dict[str, str], ...] = (
    {
        "dataset_id": "epsilon_observations_v11plus",
        "path": "data/processed/dielectric_observations_v11plus.csv",
        "kind": "csv",
    },
    {
        "dataset_id": "thermoml_viscosity",
        "path": "data/processed/viscosity_observations_thermoml.csv",
        "kind": "csv",
    },
    {
        "dataset_id": "schrodinger_viscosity_v01_open_subset",
        "path": "data/viscosity_v01.csv",
        "kind": "csv",
    },
    {
        "dataset_id": "pubchem_liquid_window_harvest",
        "path": "data/external/g1plus/pubchem/liquid_window",
        "kind": "json_dir",
    },
)

PROPERTY_UNIT: dict[str, str] = {"epsilon": "1", "viscosity": "Pa*s"}
PROPERTY_FAMILY: dict[str, str] = {
    "epsilon": "dielectric_constant",
    "viscosity": "dynamic_viscosity",
}
MEASUREMENT_SOURCE_KINDS = frozenset(
    {"primary_thermoml_measurement", "published_supplement_open_subset"}
)
SOURCE_KINDS = frozenset(
    {
        "primary_thermoml_measurement",
        "published_supplement_open_subset",
        "compilation",
    }
)
QUALITY_LAYERS = frozenset({"publishable_core", "filter_only"})
LICENCES = frozenset({"thermoml_open", "cc_by_4_0", "publisher_terms_see_source"})
PURE_OR_MIXTURE = frozenset({"pure", "mixture"})
TRUTHY = frozenset({"true", "1", "yes"})
FALSY = frozenset({"false", "0", "no"})

PINNED_DIGEST_PATTERN = re.compile(r"^(?P<path>\S+)\s+digest\s+(?P<sha256>[0-9a-f]{64})$")

def sha256_of(path: Path) -> str:
    """SHA256 of a file, or an empty string when it is not on disk."""

    if not Path(path).is_file():
        return ""
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()

def read_table(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    """Return ``(header, rows)`` for a CSV artefact, or ``([], [])`` when absent."""

    if not Path(path).is_file():
        return [], []
    with Path(path).open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), [dict(row) for row in reader]

def display_path(path: Path) -> str:
    """Repository-relative POSIX path, or the absolute path when outside the repo."""

    resolved = Path(path).resolve()
    try:
        return resolved.relative_to(REPOSITORY_ROOT).as_posix()
    except ValueError:
        return resolved.as_posix()

def count_pubchem_value_rows(payload: Mapping[str, Any]) -> int:
    """Count the harvested value rows of one PubChem record.

    The traversal is an explicit stack rather than the builder's recursion, so a
    change in the builder's walk order cannot silently agree with itself here.
    """

    total = 0
    stack: list[Any] = [payload]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            if "TOCHeading" in node:
                for information in node.get("Information") or []:
                    container = information.get("Value") or {}
                    total += len(container.get("StringWithMarkup") or [])
            for key, child in node.items():
                if key in ("Information", "Reference"):
                    continue
                if isinstance(child, (dict, list)):
                    stack.append(child)
        elif isinstance(node, list):
            stack.extend(node)
    return total

def source_universe() -> tuple[set[tuple[str, str, int]], dict[str, int]]:
    """Re-enumerate every source row the builder had available.

    Returns the universe as ``(dataset_id, source_file, source_row_index)``
    triples together with the per-source row counts.
    """

    universe: set[tuple[str, str, int]] = set()
    counts: dict[str, int] = {}
    for source in SOURCES:
        dataset_id = source["dataset_id"]
        path = REPOSITORY_ROOT / source["path"]
        if source["kind"] == "csv":
            source_file = display_path(path)
            rows = read_csv_rows(path)
            counts[dataset_id] = len(rows)
            for index in range(len(rows)):
                universe.add((dataset_id, source_file, index))
            continue
        total = 0
        for json_path in sorted(path.glob(f"*{PUBCHEM_SUFFIX}")):
            payload = json.loads(json_path.read_text(encoding="utf-8"))
            count = count_pubchem_value_rows(payload)
            total += count
            source_file = display_path(json_path)
            for index in range(count):
                universe.add((dataset_id, source_file, index))
        counts[dataset_id] = total
    return universe, counts

def read_csv_rows(path: Path) -> list[dict[str, str]]:
    """Read a CSV into a list of dicts, or an empty list when the file is absent."""

    if not Path(path).is_file():
        return []
    with Path(path).open("r", encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]

CONTRACTS: tuple[str, ...] = (
    "every required column is present and non-empty according to its rule",
    "unit is consistent with property on every row",
    "pure_or_mixture agrees with n_components",
    "quality_layer=publishable_core implies source_kind is a measurement and source_doi is non-empty",
    "redistributable=false rows are enumerated by source in the manifest",
    "the primary key has no duplicates",
    "every excluded row has an exclusion record",
)

SUPPLEMENTS: tuple[str, ...] = (
    "every row carries a source_file_sha256 that re-digests to the source file it names",
    "every enumerated value is inside its frozen enum (property, source_kind, quality_layer, licence)",
    "the summary reproduces from the table and the exclusions file",
    "the evaluation contract is present and the grouped assertion holds",
)

def check_result(
    check_id: str,
    contract: str,
    passed: bool,
    detail: Mapping[str, Any],
) -> dict[str, Any]:
    """Build one check record."""

    return {"id": check_id, "contract": contract, "passed": bool(passed), "detail": dict(detail)}

def prereg_primary_key(prereg: Mapping[str, Any]) -> tuple[str, ...]:
    """Read the primary key out of the locked identity rule."""

    match = re.search(r"\(([^()]*)\)", prereg["observation_schema"]["identity_rule"])
    if match is None:
        raise RuntimeError("cannot read the primary key from the prereg identity rule")
    return tuple(part.strip() for part in match.group(1).split(","))

def check_required_columns(
    header: Sequence[str],
    rows: Sequence[Mapping[str, str]],
    expected_columns: Sequence[str],
    required_columns: Sequence[str],
    numeric_required: Sequence[str],
) -> dict[str, Any]:
    """Contract check 1: the schema is exactly the locked one, with no empty cells."""

    detail: dict[str, Any] = {
        "expected_columns": list(expected_columns),
        "expected_column_count": len(expected_columns),
        "actual_columns": list(header),
        "actual_column_count": len(header),
        "rows": len(rows),
    }
    problems: list[dict[str, Any]] = []
    if list(header) != list(expected_columns):
        missing = [column for column in expected_columns if column not in header]
        extra = [column for column in header if column not in expected_columns]
        problems.append({"issue": "header_mismatch", "missing": missing, "extra": extra})
    empties: Counter[str] = Counter()
    unparsable: list[dict[str, str]] = []
    for row in rows:
        for column in required_columns:
            if not str(row.get(column, "")).strip():
                empties[column] += 1
        for column in numeric_required:
            text = str(row.get(column, "")).strip()
            if not text:
                continue
            try:
                float(text)
            except ValueError:
                unparsable.append({"column": column, "value": text})
    if empties:
        problems.append({"issue": "empty_required_cells", "counts": dict(empties)})
    if unparsable:
        problems.append({"issue": "unparsable_numeric_cells", "examples": unparsable[:5]})
    detail["problems"] = problems
    return check_result("C1", CONTRACTS[0], not problems, detail)

def check_unit_matches_property(rows: Sequence[Mapping[str, str]]) -> dict[str, Any]:
    """Contract check 2: the canonical unit is a function of the property."""

    offenders: list[dict[str, str]] = []
    seen: Counter[tuple[str, str]] = Counter()
    for row in rows:
        prop = str(row.get("property", "")).strip()
        unit = str(row.get("unit", "")).strip()
        seen[(prop, unit)] += 1
        if PROPERTY_UNIT.get(prop) != unit and len(offenders) < 5:
            offenders.append({"property": prop, "unit": unit})
    return check_result(
        "C2",
        CONTRACTS[1],
        not offenders,
        {
            "expected": PROPERTY_UNIT,
            "observed": {f"{key[0]}|{key[1]}": value for key, value in sorted(seen.items())},
            "offenders": offenders,
        },
    )

def check_pure_or_mixture(rows: Sequence[Mapping[str, str]]) -> dict[str, Any]:
    """Contract check 3: ``pure_or_mixture`` must follow from ``n_components``."""

    offenders: list[dict[str, str]] = []
    for row in rows:
        text = str(row.get("n_components", "")).strip()
        label = str(row.get("pure_or_mixture", "")).strip()
        expected = "pure" if text == "1" else "mixture"
        mismatch = bool(text) and label != expected
        unknown_label = bool(label) and label not in PURE_OR_MIXTURE
        if (mismatch or unknown_label) and len(offenders) < 5:
            offenders.append({"n_components": text, "pure_or_mixture": label})
    return check_result("C3", CONTRACTS[2], not offenders, {"offenders": offenders})

def check_publishable_core(rows: Sequence[Mapping[str, str]]) -> dict[str, Any]:
    """Contract check 4: a core row needs a measurement kind and a first-hand DOI."""

    offenders: list[dict[str, str]] = []
    core = 0
    for row in rows:
        if str(row.get("quality_layer", "")).strip() != "publishable_core":
            continue
        core += 1
        source_kind = str(row.get("source_kind", "")).strip()
        doi = str(row.get("source_doi", "")).strip()
        if (source_kind not in MEASUREMENT_SOURCE_KINDS or not doi) and len(offenders) < 5:
            offenders.append({"source_kind": source_kind, "source_doi": doi})
    return check_result(
        "C4",
        CONTRACTS[3],
        not offenders,
        {"publishable_core_rows": core, "measurement_source_kinds": sorted(MEASUREMENT_SOURCE_KINDS), "offenders": offenders},
    )

def check_redistributable_manifest(
    rows: Sequence[Mapping[str, str]],
    summary: Mapping[str, Any],
) -> dict[str, Any]:
    """Contract check 5: non-redistributable rows are enumerated by source."""

    recomputed = Counter(
        str(row.get("source_file", ""))
        for row in rows
        if str(row.get("redistributable", "")).strip().lower() in FALSY
    )
    declared = dict((summary.get("manifest") or {}).get("redistributable_false_by_source") or {})
    total = sum(recomputed.values())
    undeclared = sorted(set(recomputed) - set(declared))
    detail = {
        "non_redistributable_rows": total,
        "recomputed_by_source": dict(sorted(recomputed.items())),
        "declared_by_source": declared,
        "sources_missing_from_manifest": undeclared,
        "manifest_matches_recomputation": dict(sorted(recomputed.items())) == declared,
    }
    passed = total == 0 or (not undeclared and detail["manifest_matches_recomputation"])
    return check_result("C5", CONTRACTS[4], passed, detail)

def check_primary_key_unique(
    rows: Sequence[Mapping[str, str]],
    primary_key: Sequence[str],
) -> dict[str, Any]:
    """Contract check 6: a duplicate on the identity key is a defect, not a merge."""

    counts = Counter(tuple(str(row.get(column, "")) for column in primary_key) for row in rows)
    duplicates = [key for key, value in counts.items() if value > 1]
    return check_result(
        "C6",
        CONTRACTS[5],
        not duplicates,
        {
            "primary_key": list(primary_key),
            "distinct_keys": len(counts),
            "duplicate_keys": len(duplicates),
            "examples": [list(key) for key in duplicates[:5]],
        },
    )

def check_no_silent_drops(
    rows: Sequence[Mapping[str, str]],
    exclusions: Sequence[Mapping[str, str]],
    universe: set[tuple[str, str, int]],
    source_counts: Mapping[str, int],
) -> dict[str, Any]:
    """Contract check 7: every source row is either in the table or has a record."""

    in_table = {
        (str(row.get("dataset_id", "")), str(row.get("source_file", "")), int(row["source_row_index"]))
        for row in rows
        if str(row.get("source_row_index", "")).strip()
    }
    recorded = {
        (str(row.get("dataset_id", "")), str(row.get("source_file", "")), int(row["source_row_index"]))
        for row in exclusions
        if str(row.get("source_row_index", "")).strip()
    }
    covered = in_table | recorded
    missing = sorted(universe - covered)
    phantom = sorted(covered - universe)
    return check_result(
        "C7",
        CONTRACTS[6],
        not missing and not phantom,
        {
            "universe_rows": len(universe),
            "universe_rows_by_dataset": dict(sorted(source_counts.items())),
            "source_rows_in_table": len(in_table),
            "source_rows_with_exclusion_record": len(recorded),
            "source_rows_covered": len(covered),
            "source_rows_without_any_record": len(missing),
            "records_for_rows_outside_the_universe": len(phantom),
            "missing_examples": [list(item) for item in missing[:5]],
            "phantom_examples": [list(item) for item in phantom[:5]],
        },
    )

def check_source_digests(
    rows: Sequence[Mapping[str, str]],
    exclusions: Sequence[Mapping[str, str]],
) -> dict[str, Any]:
    """Supplementary check: every row re-digests to the file it names."""

    declared: dict[str, set[str]] = {}
    for row in list(rows) + list(exclusions):
        source_file = str(row.get("source_file", ""))
        declared.setdefault(source_file, set()).add(str(row.get("source_file_sha256", "")))
    mismatches: list[dict[str, Any]] = []
    checked = 0
    for source_file, digests in sorted(declared.items()):
        if not source_file:
            mismatches.append({"source_file": source_file, "issue": "empty_source_file"})
            continue
        actual = sha256_of(Path(source_file))
        checked += 1
        if not actual:
            mismatches.append({"source_file": source_file, "issue": "source_missing"})
            continue
        if digests != {actual}:
            mismatches.append(
                {
                    "source_file": source_file,
                    "declared": sorted(digests),
                    "actual": actual,
                }
            )
    return check_result(
        "S1",
        SUPPLEMENTS[0],
        not mismatches,
        {"source_files_checked": checked, "mismatches": mismatches[:5]},
    )

def check_enums(
    rows: Sequence[Mapping[str, str]],
    dataset_ids: Sequence[str],
) -> dict[str, Any]:
    """Supplementary check: property, layer, kind and licence stay inside their enums."""

    offenders: list[dict[str, str]] = []
    for row in rows:
        prop = str(row.get("property", "")).strip()
        problems = []
        if prop not in PROPERTY_UNIT:
            problems.append("property")
        if str(row.get("property_family", "")).strip() != PROPERTY_FAMILY.get(prop):
            problems.append("property_family")
        if str(row.get("dataset_id", "")).strip() not in set(dataset_ids):
            problems.append("dataset_id")
        if str(row.get("source_kind", "")).strip() not in SOURCE_KINDS:
            problems.append("source_kind")
        if str(row.get("quality_layer", "")).strip() not in QUALITY_LAYERS:
            problems.append("quality_layer")
        if str(row.get("licence", "")).strip() not in LICENCES:
            problems.append("licence")
        expected_row_id = f"{row.get('dataset_id', '')}:{row.get('source_row_index', '')}"
        if str(row.get("row_id", "")).strip() != expected_row_id:
            problems.append("row_id")
        if str(row.get("redistributable", "")).strip().lower() not in TRUTHY | FALSY:
            problems.append("redistributable")
        if problems and len(offenders) < 5:
            offenders.append({"problems": ",".join(problems), "property": prop})
    return check_result(
        "S2",
        SUPPLEMENTS[1],
        not offenders,
        {
            "dataset_ids": list(dataset_ids),
            "source_kinds": sorted(SOURCE_KINDS),
            "quality_layers": sorted(QUALITY_LAYERS),
            "licences": sorted(LICENCES),
            "offenders": offenders,
        },
    )

def check_summary_agreement(
    rows: Sequence[Mapping[str, str]],
    exclusions: Sequence[Mapping[str, str]],
    summary: Mapping[str, Any],
) -> dict[str, Any]:
    """Supplementary check: the committed summary re-derives from the artefacts."""

    if not summary:
        return check_result("S3", SUPPLEMENTS[2], False, {"error": "summary missing or unreadable"})
    counts = summary.get("row_counts") or {}
    distribution = summary.get("distribution") or {}
    recomputed = {
        "observations": len(rows),
        "exclusions": len(exclusions),
        "property": counter_of(rows, "property"),
        "dataset_id": counter_of(rows, "dataset_id"),
        "pure_or_mixture": counter_of(rows, "pure_or_mixture"),
        "quality_layer": counter_of(rows, "quality_layer"),
        "source_kind": counter_of(rows, "source_kind"),
        "licence": counter_of(rows, "licence"),
        "unit": counter_of(rows, "unit"),
    }
    mismatches: list[dict[str, Any]] = []
    if counts.get("observations") != recomputed["observations"]:
        mismatches.append({"field": "row_counts.observations"})
    if counts.get("exclusions") != recomputed["exclusions"]:
        mismatches.append({"field": "row_counts.exclusions"})
    for name in (
        "property",
        "dataset_id",
        "pure_or_mixture",
        "quality_layer",
        "source_kind",
        "licence",
        "unit",
    ):
        if dict(distribution.get(name) or {}) != recomputed[name]:
            mismatches.append({"field": f"distribution.{name}"})
    core = sum(1 for row in rows if str(row.get("quality_layer", "")) == "publishable_core")
    if (summary.get("publishable_headline") or {}).get("rows") != core:
        mismatches.append({"field": "publishable_headline.rows"})
    return check_result(
        "S3",
        SUPPLEMENTS[2],
        not mismatches,
        {"mismatches": mismatches, "recomputed": {k: v for k, v in recomputed.items()}},
    )

def counter_of(rows: Sequence[Mapping[str, str]], column: str) -> dict[str, int]:
    """Sorted value counts for one column."""

    return dict(sorted(Counter(str(row.get(column, "")) for row in rows).items()))

def check_evaluation_contract(summary: Mapping[str, Any]) -> dict[str, Any]:
    """Supplementary check: the grouped splitter ran and did not leak a group."""

    evaluation = dict(summary.get("evaluation_contract") or {})
    random_row = dict(evaluation.get("random_row") or {})
    problems: list[str] = []
    if evaluation.get("splitter") != "GroupKFold by InChIKey":
        problems.append("splitter")
    if evaluation.get("group_key") != "inchikey":
        problems.append("group_key")
    if evaluation.get("max_group_overlap") != 0:
        problems.append("max_group_overlap")
    if evaluation.get("assertion_passed") is not True:
        problems.append("assertion_passed")
    if "never enters a verdict" not in str(random_row.get("role", "")):
        problems.append("random_row_role")
    return check_result(
        "S4",
        SUPPLEMENTS[3],
        not problems,
        {
            "problems": problems,
            "splitter": evaluation.get("splitter"),
            "max_group_overlap": evaluation.get("max_group_overlap"),
            "subset_rows": evaluation.get("subset_rows"),
            "random_row_role": random_row.get("role"),
            "folds": evaluation.get("folds"),
        },
    )

def check_manifest(
    table_path: Path,
    exclusions_path: Path,
    summary: Mapping[str, Any],
    prereg: Mapping[str, Any],
    prereg_path: Path,
    builder_path: Path,
) -> dict[str, Any]:
    """Rebuild the SHA256 manifest and compare it with the summary and the prereg."""

    actual = {
        "table": {"path": display_path(table_path), "sha256": sha256_of(table_path)},
        "exclusions": {
            "path": display_path(exclusions_path),
            "sha256": sha256_of(exclusions_path),
        },
        "builder": {"path": display_path(builder_path), "sha256": sha256_of(builder_path)},
        "prereg": {"path": display_path(prereg_path), "sha256": sha256_of(prereg_path)},
    }
    declared = dict(summary.get("manifest") or {})
    comparisons: list[dict[str, Any]] = []
    for name in ("table", "exclusions", "builder", "prereg"):
        declared_sha = str((declared.get(name) or {}).get("sha256", ""))
        comparisons.append(
            {
                "artefact": name,
                "declared_sha256": declared_sha,
                "actual_sha256": actual[name]["sha256"],
                "match": bool(declared_sha) and declared_sha == actual[name]["sha256"],
            }
        )
    pinned: list[dict[str, Any]] = []
    for entry in prereg.get("frozen_red_lines_untouched") or []:
        match = PINNED_DIGEST_PATTERN.match(str(entry))
        if match is None:
            pinned.append({"entry": str(entry), "recheckable": False})
            continue
        path = REPOSITORY_ROOT / match.group("path")
        digest = sha256_of(path)
        pinned.append(
            {
                "path": match.group("path"),
                "expected_sha256": match.group("sha256"),
                "actual_sha256": digest,
                "match": digest == match.group("sha256"),
            }
        )
    passed = all(item["match"] for item in comparisons) and all(
        item.get("match", True) for item in pinned
    )
    return check_result(
        "M1",
        "a SHA256 manifest over the built table, the exclusions file and the builder script",
        passed,
        {"artefacts": comparisons, "pinned_red_lines": pinned, "manifest": actual},
    )

AUDIT_COLUMNS: tuple[str, ...] = (
    "exclusion_id",
    "dataset_id",
    "source_file",
    "source_row_index",
    "segment_index",
    "reason_code",
    "reason",
)

def check_exclusion_auditability(
    header: Sequence[str],
    exclusions: Sequence[Mapping[str, str]],
) -> dict[str, Any]:
    """Supplementary check: an exclusion record says where it came from and why."""

    missing_columns = [column for column in AUDIT_COLUMNS if column not in header]
    empty_reasons = sum(1 for row in exclusions if not str(row.get("reason_code", "")).strip())
    empty_sources = sum(1 for row in exclusions if not str(row.get("source_file", "")).strip())
    problems = {
        "missing_columns": missing_columns,
        "rows_without_reason_code": empty_reasons,
        "rows_without_source_file": empty_sources,
    }
    passed = not missing_columns and not empty_reasons and not empty_sources
    return check_result(
        "S5",
        "every exclusion record names its source row and its reason",
        passed,
        {**problems, "columns": list(header), "rows": len(exclusions)},
    )

def required_column_rules(
    prereg: Mapping[str, Any],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Split the locked schema into the required columns and the numeric ones."""

    columns = (prereg.get("observation_schema") or {}).get("columns") or []
    required = tuple(str(column["name"]) for column in columns if column.get("required"))
    numeric = tuple(
        str(column["name"])
        for column in columns
        if column.get("required") and column.get("dtype") in ("float", "int")
    )
    return required, numeric

def load_json(path: Path) -> dict[str, Any]:
    """Read a JSON object, or an empty dict when the file is absent."""

    if not Path(path).is_file():
        return {}
    return json.loads(Path(path).read_text(encoding="utf-8"))

def verify(
    *,
    table_path: Path = DEFAULT_TABLE_PATH,
    exclusions_path: Path = DEFAULT_EXCLUSIONS_PATH,
    summary_path: Path = DEFAULT_SUMMARY_PATH,
    prereg_path: Path = PREREG_PATH,
    builder_path: Path = BUILDER_PATH,
) -> dict[str, Any]:
    """Run every contract check against the given artefacts and return a report."""

    prereg = load_json(prereg_path)
    summary = load_json(summary_path)
    expected_columns = tuple(
        str(column["name"])
        for column in (prereg.get("observation_schema") or {}).get("columns") or []
    )
    required, numeric_required = required_column_rules(prereg)
    dataset_ids = tuple((prereg.get("merge_rules") or {}).get("dataset_id_enum") or [])
    primary_key = prereg_primary_key(prereg) if prereg else ()

    header, rows = read_table(table_path)
    exclusion_header, exclusions = read_table(exclusions_path)
    universe, source_counts = source_universe()

    checks = [
        check_required_columns(
            header, rows, expected_columns, required, numeric_required
        ),
        check_unit_matches_property(rows),
        check_pure_or_mixture(rows),
        check_publishable_core(rows),
        check_redistributable_manifest(rows, summary),
        check_primary_key_unique(rows, primary_key),
        check_no_silent_drops(rows, exclusions, universe, source_counts),
    ]
    supplementary = [
        check_source_digests(rows, exclusions),
        check_enums(rows, dataset_ids),
        check_summary_agreement(rows, exclusions, summary),
        check_evaluation_contract(summary),
        check_exclusion_auditability(exclusion_header, exclusions),
    ]
    manifest = check_manifest(
        table_path, exclusions_path, summary, prereg, prereg_path, builder_path
    )
    every = [*checks, *supplementary, manifest]
    failures = [item["id"] for item in every if not item["passed"]]
    return {
        "status": "PASS" if not failures else "FAIL",
        "generated_at_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "prereg": {
            "path": display_path(prereg_path),
            "sha256": sha256_of(prereg_path),
            "columns": list(expected_columns),
            "primary_key": list(primary_key),
        },
        "table": {
            "path": display_path(table_path),
            "sha256": sha256_of(table_path),
            "columns": list(header),
            "rows": len(rows),
        },
        "exclusions": {
            "path": display_path(exclusions_path),
            "sha256": sha256_of(exclusions_path),
            "columns": list(exclusion_header),
            "rows": len(exclusions),
        },
        "checks": checks,
        "supplementary_checks": supplementary,
        "manifest_check": manifest,
        "failures": failures,
    }

def main(argv: Sequence[str] | None = None) -> int:
    """Entry point: print the check table and return 0 for PASS, 1 for FAIL."""

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--table", type=Path, default=DEFAULT_TABLE_PATH)
    parser.add_argument("--exclusions", type=Path, default=DEFAULT_EXCLUSIONS_PATH)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY_PATH)
    parser.add_argument("--prereg", type=Path, default=PREREG_PATH)
    parser.add_argument("--builder", type=Path, default=BUILDER_PATH)
    parser.add_argument("--json", action="store_true", help="print the full report as JSON")
    arguments = parser.parse_args(argv)

    report = verify(
        table_path=arguments.table,
        exclusions_path=arguments.exclusions,
        summary_path=arguments.summary,
        prereg_path=arguments.prereg,
        builder_path=arguments.builder,
    )
    if arguments.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        for item in [*report["checks"], *report["supplementary_checks"], report["manifest_check"]]:
            marker = "PASS" if item["passed"] else "FAIL"
            print(f"[{marker}] {item['id']}  {item['contract']}")
        print(
            f"table rows={report['table']['rows']} "
            f"exclusions rows={report['exclusions']['rows']} "
            f"table sha256={report['table']['sha256'][:16]}"
        )
        print(f"{report['status']}: {len(report['failures'])} failing check(s) {report['failures']}")
    return 0 if report["status"] == "PASS" else 1

if __name__ == "__main__":
    raise SystemExit(main())
