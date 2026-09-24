from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

import pytest

from electrolyte_ml.exporting import canonical_text_sha256
from scripts.build_dielectric_v03 import (
    PROVENANCE_PATCH_PROTECTED_FIELDS,
    apply_provenance_patches,
    build_v03_rows,
    read_csv_rows,
)
from scripts.verify_dielectric_v03 import verify_v03_rows

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
REVIEW_OBSERVATIONS_PATH = (
    REPOSITORY_ROOT
    / "data"
    / "processed"
    / "modern_solvent_public_review_observations.csv"
)
V03_PATH = REPOSITORY_ROOT / "data" / "dielectric_v03.csv"
V03_SUMMARY_PATH = REPOSITORY_ROOT / "probes" / "dielectric_v03_summary.json"
EXPECTED_V03_SHA256 = (
    "88f0a1a609b4c462db51a507f72e2909a1a28de8eb4e887c936adaa6f74a7a33"
)
NONCANONICAL_CASSC_DOIS = (
    "10.1002/CSSC.202402091",
    "10.1002/ cssc.202402091",
    "doi:10.1002/CSSC.202402091",
    "https://doi.org/10.1002/CSSC.202402091",
    "http://dx.doi.org/10.1002/CSSC.202402091",
    "https://dx.doi.org/10.1002/cssc.202402091",
    "https://doi.org/10.1002/cssc.202402091/",
    "http://doi.org/10.1002/cssc.202402091",
    "HTTPS://DOI.ORG/10.1002/CSSC.202402091",
    "https://doi.org/10.1002/cssc.202402091?download=1#section",
    "https://doi.org/10.1002/cssc%20.202402091",
    "https://www.doi.org/10.1002/cssc.202402091",
    "doi.org/10.1002/cssc.202402091",
    "www.doi.org/10.1002/cssc.202402091",
    "https://doi.org:443/10.1002/cssc.202402091",
    "https://doi.org///10.1002/cssc.202402091///",
    "https://doi.org/10.1002/cssc%2520.202402091",
    "10.1002/cssc.2024\uFE0F02091",
    "10.1002/cssc.2024\u034F02091",
    "10.1002/cssc%2525252E202402091",
)
INVALID_SOURCE_DOI_ALL_VALUES = (
    "10.1000/unknown,10.1002/cssc.202402091",
    "10.1000/unknown|10.1002/cssc.202402091",
    "10.1000/unknown 10.1002/cssc.202402091",
    "https://example.org/10.1002/cssc.202402091",
)
ALL_CLI_HIDDEN_DOI_VALUES = (
    *NONCANONICAL_CASSC_DOIS,
    *INVALID_SOURCE_DOI_ALL_VALUES,
    "10.1002/cssc.202402091;10.1002/cssc.202402091",
)
MALFORMED_DOI_VALUES = (
    f"10.1002/cssc%{'25' * 12}2E202402091",
)

EXPECTED_REVIEW_SOURCES = {
    "10.1002/smll.202504276": {
        "source_citation": "Senthil et al. (2025) Small 21 e202504276",
        "source_license": "CC BY 4.0",
        "license_url": "https://creativecommons.org/licenses/by/4.0/",
        "redistribution_conditions": "allowed_with_attribution",
        "redistribution_status": "allowed",
    },
    "10.1002/smtd.202400183": {
        "source_citation": "Yue et al. (2024) Small Methods 8 e2400183",
        "source_license": "CC BY-NC-ND 4.0",
        "license_url": "https://creativecommons.org/licenses/by-nc-nd/4.0/",
        "redistribution_conditions": "allowed_noncommercial_no_derivatives",
        "redistribution_status": "allowed",
    },
    "10.1039/d5sc06221g": {
        "source_citation": "Karbak et al. (2025) Chemical Science 16 19398",
        "source_license": "CC BY 3.0",
        "license_url": "https://creativecommons.org/licenses/by/3.0/",
        "redistribution_conditions": "allowed_with_attribution",
        "redistribution_status": "allowed",
    },
    "10.1002/cssc.202402091": {
        "source_citation": "Souid et al. (2025) ChemSusChem 18 e202402091",
        "source_license": "CC BY-NC 4.0",
        "license_url": "https://creativecommons.org/licenses/by-nc/4.0/",
        "redistribution_conditions": "allowed_noncommercial",
        "redistribution_status": "allowed",
    },
    "10.1016/j.isci.2026.115778": {
        "source_citation": "Sun et al. (2026) iScience 29 115778",
        "source_license": "CC BY-NC 4.0",
        "license_url": "https://creativecommons.org/licenses/by-nc/4.0/",
        "redistribution_conditions": "allowed_noncommercial",
        "redistribution_status": "allowed",
    },
    "10.1002/adma.73388": {
        "source_citation": "Cui et al. (2026) Advanced Materials e73388",
        "source_license": "CC BY 4.0",
        "license_url": "https://creativecommons.org/licenses/by/4.0/",
        "redistribution_conditions": "allowed_with_attribution",
        "redistribution_status": "allowed",
    },
}


def _read_review_observations() -> list[dict[str, str]]:
    with REVIEW_OBSERVATIONS_PATH.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _write_csv(
    path: Path,
    fieldnames: list[str],
    rows: list[dict[str, str]],
) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _addition(**overrides: str) -> dict[str, str]:
    row = {
        "inchikey": "ZZZZZZZZZZZZZZ-UHFFFAOYSA-N",
        "smiles": "CC#N",
        "name": "example nitrile",
        "T_K": "298.15",
        "dielectric": "20.0",
        "uncertainty_value": "0.2",
        "uncertainty_kind": "standard",
        "confidence_level": "68",
        "source_doi": "10.1000/example",
        "source_url": "https://example.org/article",
        "source_citation": "Example (2000)",
        "source_table": "Table 1",
        "source_quality": "primary_experimental",
        "redistribution_status": "allowed",
    }
    row.update(overrides)
    return row


def _review_addition(
    doi: str,
    **overrides: str,
) -> dict[str, str]:
    metadata = EXPECTED_REVIEW_SOURCES[doi]
    row = {
        "source_quality": "open_access_review_table",
        **metadata,
        **overrides,
    }
    return _addition(
        source_doi=doi,
        **row,
    )


def test_review_observations_preserve_verified_source_metadata() -> None:
    # The open-access allowlist below only binds rows that claim an open-access
    # source.  v0.3.3 adds one documented row whose only access path is a non-CC
    # publisher supplement; it is checked separately by
    # test_mopn_secondary_compilation_row_claims_no_open_licence.
    rows = [
        row
        for row in _read_review_observations()
        if row["source_quality"].startswith("open_access")
    ]

    observed_dois = {row["source_doi"] for row in rows}
    assert observed_dois == set(EXPECTED_REVIEW_SOURCES)
    for doi, expected in EXPECTED_REVIEW_SOURCES.items():
        matching_rows = [row for row in rows if row["source_doi"] == doi]
        assert matching_rows
        for row in matching_rows:
            for field, expected_value in expected.items():
                assert row[field] == expected_value


def test_methyl_propionate_uses_chemical_science_table_1() -> None:
    rows = _read_review_observations()
    row = next(row for row in rows if row["name"] == "methyl propionate")

    assert row["source_doi"] == "10.1039/d5sc06221g"
    assert row["source_url"] == "https://pmc.ncbi.nlm.nih.gov/articles/PMC12558406/"
    assert row["source_citation"] == "Karbak et al. (2025) Chemical Science 16 19398"
    assert row["source_table"] == "Table 1"


def test_build_v03_appends_public_observation() -> None:
    rows = build_v03_rows([], [_addition()], minimum_additions=1)

    assert len(rows) == 1
    assert rows[0]["name"] == "example nitrile"
    assert rows[0]["dataset_origin"] == "v0.3_addition"
    assert rows[0]["temperature_band"] == "room_temperature"


def test_build_v03_rejects_restricted_observation() -> None:
    with pytest.raises(ValueError, match="restricted"):
        build_v03_rows(
            [],
            [_addition(redistribution_status="restricted")],
            minimum_additions=1,
        )


def test_build_v03_propagates_review_license_conditions() -> None:
    rows = build_v03_rows(
        [],
        [_review_addition("10.1002/smll.202504276")],
        minimum_additions=1,
    )

    assert rows[0]["source_license"] == "CC BY 4.0"
    assert rows[0]["license_url"] == "https://creativecommons.org/licenses/by/4.0/"
    assert rows[0]["redistribution_conditions"] == "allowed_with_attribution"


@pytest.mark.parametrize(
    ("doi", "overrides", "error_fragment"),
    [
        (
            "10.1002/smll.202504276",
            {
                "source_license": "UNKNOWN",
                "license_url": "https://example.org/not-a-license",
            },
            "source_license",
        ),
        (
            "10.1002/smtd.202400183",
            {"redistribution_conditions": "public_domain"},
            "redistribution_conditions",
        ),
        (
            "10.1016/j.isci.2026.115778",
            {"redistribution_conditions": "allowed_with_attribution"},
            "redistribution_conditions",
        ),
    ],
)
def test_build_v03_rejects_inconsistent_review_license_triplets(
    doi: str,
    overrides: dict[str, str],
    error_fragment: str,
) -> None:
    with pytest.raises(ValueError, match=error_fragment):
        build_v03_rows(
            [],
            [_review_addition(doi, **overrides)],
            minimum_additions=1,
        )


@pytest.mark.parametrize(
    ("doi", "field", "wrong_value"),
    [
        ("10.1002/smll.202504276", "source_license", "UNKNOWN"),
        ("10.1002/smtd.202400183", "redistribution_conditions", "public_domain"),
        (
            "10.1016/j.isci.2026.115778",
            "redistribution_conditions",
            "allowed_with_attribution",
        ),
    ],
)
def test_verify_v03_rejects_inconsistent_review_license_triplets(
    doi: str,
    field: str,
    wrong_value: str,
) -> None:
    rows = build_v03_rows(
        [],
        [_review_addition(doi)],
        minimum_additions=1,
    )
    rows[0][field] = wrong_value

    errors = verify_v03_rows(rows, minimum_additions=1)

    assert any(field in error and doi in error for error in errors)


def test_build_v03_validates_known_doi_even_when_not_marked_open_access() -> None:
    row = _review_addition(
        "10.1002/cssc.202402091",
        source_quality="primary_experimental",
        source_license="",
        license_url="",
        redistribution_conditions="",
    )

    with pytest.raises(ValueError, match="source_license"):
        build_v03_rows([], [row], minimum_additions=1)


def test_build_v03_rejects_known_doi_with_wrong_redistribution_status() -> None:
    row = _review_addition(
        "10.1002/smtd.202400183",
        redistribution_status="public_domain",
    )

    with pytest.raises(ValueError, match="redistribution_status"):
        build_v03_rows([], [row], minimum_additions=1)


def test_build_v03_rejects_unknown_open_access_review_doi() -> None:
    row = _addition(
        source_doi="10.1000/unknown",
        source_quality="open_access_review_table",
        source_license="CC BY 4.0",
        license_url="https://creativecommons.org/licenses/by/4.0/",
        redistribution_conditions="allowed_with_attribution",
    )

    with pytest.raises(ValueError, match="unsupported review source_doi"):
        build_v03_rows([], [row], minimum_additions=1)


@pytest.mark.parametrize(
    ("doi", "mutations", "error_fragment"),
    [
        (
            "10.1002/cssc.202402091",
            {
                "source_quality": "primary_experimental",
                "source_license": "",
                "license_url": "",
                "redistribution_conditions": "",
            },
            "source_license",
        ),
        (
            "10.1002/smtd.202400183",
            {"redistribution_status": "public_domain"},
            "redistribution_status",
        ),
        (
            "10.1002/smll.202504276",
            {"source_doi": "10.1000/unknown"},
            "source_doi",
        ),
    ],
)
def test_verify_v03_rejects_known_or_unknown_doi_metadata_violations(
    doi: str,
    mutations: dict[str, str],
    error_fragment: str,
) -> None:
    rows = build_v03_rows(
        [],
        [_review_addition(doi)],
        minimum_additions=1,
    )
    rows[0].update(mutations)

    errors = verify_v03_rows(rows, minimum_additions=1)

    assert any(error_fragment in error for error in errors)


@pytest.mark.parametrize("doi", EXPECTED_REVIEW_SOURCES)
def test_frozen_review_license_triplets_are_accepted(doi: str) -> None:
    rows = build_v03_rows(
        [],
        [_review_addition(doi)],
        minimum_additions=1,
    )

    assert verify_v03_rows(rows, minimum_additions=1) == []


def _mapped_doi_history_row(
    *,
    source_doi: str = "10.1000/unmapped",
    source_dois_all: str = "",
) -> dict[str, str]:
    return {
        "inchikey": "ZZZZZZZZZZZZZZ-UHFFFAOYSA-N",
        "T_K": "298.15",
        "source_doi": source_doi,
        "source_dois_all": source_dois_all,
        "source_quality": "open_access_article_text",
        "source_license": "",
        "license_url": "",
        "redistribution_conditions": "",
        "redistribution_status": "allowed",
    }


@pytest.mark.parametrize(
    "row",
    [
        _mapped_doi_history_row(source_doi="10.1002/cssc.202402091"),
        _mapped_doi_history_row(
            source_dois_all=(
                "10.1000/unmapped;10.1002/cssc.202402091;"
                "10.1000/another"
            )
        ),
    ],
)
def test_build_v03_rejects_mapped_doi_in_final_history_row(
    row: dict[str, str],
) -> None:
    with pytest.raises(ValueError, match="source_license"):
        build_v03_rows([row], [], minimum_additions=0)


@pytest.mark.parametrize(
    "row",
    [
        _mapped_doi_history_row(source_doi="10.1002/cssc.202402091"),
        _mapped_doi_history_row(
            source_dois_all=(
                "10.1000/unmapped;10.1002/cssc.202402091;"
                "10.1000/another"
            )
        ),
    ],
)
def test_verify_v03_rejects_mapped_doi_in_final_history_row(
    row: dict[str, str],
) -> None:
    expected_rows = [row]

    errors = verify_v03_rows(expected_rows, minimum_additions=0)

    assert any("source_license" in error for error in errors)


@pytest.mark.parametrize("doi_token", NONCANONICAL_CASSC_DOIS)
def test_noncanonical_mapped_doi_is_canonicalized_before_validation(
    doi_token: str,
) -> None:
    row = _review_addition("10.1002/cssc.202402091")
    row["source_doi"] = doi_token
    row["source_dois_all"] = doi_token

    rows = build_v03_rows([], [row], minimum_additions=1)

    assert verify_v03_rows(rows, minimum_additions=1) == []


@pytest.mark.parametrize("doi_value", INVALID_SOURCE_DOI_ALL_VALUES)
def test_source_dois_all_rejects_hidden_multiplicity_or_nonresolver(
    doi_value: str,
) -> None:
    row = _review_addition("10.1002/cssc.202402091")
    row["source_dois_all"] = doi_value

    with pytest.raises(ValueError, match="source_dois_all"):
        build_v03_rows([], [row], minimum_additions=1)


@pytest.mark.parametrize("doi_value", MALFORMED_DOI_VALUES)
def test_source_dois_all_reports_unresolved_percent_encoding(
    doi_value: str,
) -> None:
    row = _review_addition("10.1002/cssc.202402091")
    row["source_dois_all"] = doi_value

    with pytest.raises(ValueError, match="unresolved percent-encoded"):
        build_v03_rows([], [row], minimum_additions=1)


@pytest.mark.parametrize("doi_token", ALL_CLI_HIDDEN_DOI_VALUES)
def test_build_and_verify_cli_reject_mapped_doi_injected_through_v02(
    tmp_path,
    doi_token: str,
) -> None:
    v02_path = tmp_path / "v02.csv"
    additions_path = tmp_path / "additions.csv"
    review_path = tmp_path / "review.csv"
    exclusions_path = tmp_path / "exclusions.csv"
    output_path = tmp_path / "v03.csv"
    summary_path = tmp_path / "summary.json"

    _write_csv(
        v02_path,
        [
            "inchikey",
            "T_K",
            "source_doi",
            "source_dois_all",
            "source_quality",
            "source_license",
            "license_url",
            "redistribution_conditions",
            "redistribution_status",
        ],
        [
            _mapped_doi_history_row(
                source_dois_all=f"10.1000/unmapped;{doi_token}"
            )
        ],
    )
    _write_csv(additions_path, ["inchikey"], [])
    _write_csv(review_path, ["inchikey"], [])
    _write_csv(exclusions_path, ["inchikey"], [])
    _write_csv(
        output_path,
        ["inchikey", "T_K", "dataset_origin"],
        [
            {
                "inchikey": "ZZZZZZZZZZZZZZ-UHFFFAOYSA-N",
                "T_K": "298.15",
                "dataset_origin": "v0.2",
            }
        ],
    )
    summary_path.write_text("{}\n", encoding="utf-8")

    common_args = [
        "--v02",
        str(v02_path),
        "--additions",
        str(additions_path),
        "--review-additions",
        str(review_path),
        "--model-exclusions",
        str(exclusions_path),
        "--output",
        str(output_path),
        "--summary",
        str(summary_path),
        "--minimum-additions",
        "0",
    ]
    build_result = subprocess.run(
        [
            sys.executable,
            str(REPOSITORY_ROOT / "scripts" / "build_dielectric_v03.py"),
            *common_args,
        ],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    verify_result = subprocess.run(
        [
            sys.executable,
            str(REPOSITORY_ROOT / "scripts" / "verify_dielectric_v03.py"),
            *common_args,
        ],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert build_result.returncode != 0
    assert verify_result.returncode != 0
    assert "source_license" in f"{build_result.stdout}{build_result.stderr}"
    assert "source_license" in f"{verify_result.stdout}{verify_result.stderr}"


def test_current_v03_counts_and_sha_are_pinned() -> None:
    with V03_PATH.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    additions = [
        row for row in rows if row.get("dataset_origin") == "v0.3_addition"
    ]
    summary = json.loads(V03_SUMMARY_PATH.read_text(encoding="utf-8"))

    assert len(rows) == 246
    assert len(additions) == 36
    assert sum(row["model_ready"] == "true" for row in additions) == 31
    assert sum(bool(row["conflict_status"]) for row in additions) == 6
    assert canonical_text_sha256(V03_PATH) == EXPECTED_V03_SHA256
    assert summary["output"]["sha256"] == EXPECTED_V03_SHA256


def test_build_v03_rejects_duplicate_inchikey() -> None:
    with pytest.raises(ValueError, match="duplicate"):
        build_v03_rows([], [_addition(), _addition()], minimum_additions=1)


def test_build_v03_requires_minimum_additions() -> None:
    with pytest.raises(ValueError, match="at least 2"):
        build_v03_rows([], [_addition()], minimum_additions=2)


def test_verify_v03_accepts_complete_public_addition() -> None:
    rows = build_v03_rows([], [_addition()], minimum_additions=1)

    errors = verify_v03_rows(rows, minimum_additions=1)

    assert errors == []


def test_verify_v03_rejects_restricted_output_row() -> None:
    rows = build_v03_rows([], [_addition()], minimum_additions=1)
    rows[0]["redistribution_status"] = "restricted"

    errors = verify_v03_rows(rows, minimum_additions=1)

    assert any("restricted" in error for error in errors)


def test_verify_v03_rejects_missing_license_conditions_for_review_row() -> None:
    rows = build_v03_rows(
        [],
        [_review_addition("10.1002/smll.202504276")],
        minimum_additions=1,
    )
    rows[0]["redistribution_conditions"] = ""

    errors = verify_v03_rows(rows, minimum_additions=1)

    assert any("redistribution_conditions" in error for error in errors)


def test_build_v03_marks_conflicted_v02_row_not_model_ready() -> None:
    rows = build_v03_rows(
        [
            {
                "inchikey": "HBNYJWAFDZLWRS-UHFFFAOYSA-N",
                "T_K": "294.15",
            }
        ],
        [],
        minimum_additions=0,
        excluded_model_keys={"HBNYJWAFDZLWRS-UHFFFAOYSA-N"},
    )

    assert rows[0]["model_ready"] == "false"
    assert rows[0]["conflict_status"] == "excluded_model_conflict"


# ---------------------------------------------------------------------------
# Provenance patch layer
#
# The v0.3.2 revision restored four rows (PC, ethoxybenzene, methyl propionate,
# VC) by hand-editing the frozen CSV.  Those restorations were invisible to the
# build, so any rebuild silently dropped them -- the same failure mode that had
# already reverted an earlier NBS upgrade.  The patch layer exists to make such
# provenance edits reproducible; these tests are its regression net.
# ---------------------------------------------------------------------------

PROVENANCE_PATCHES_PATH = (
    REPOSITORY_ROOT / "data" / "processed" / "dielectric_v03_provenance_patches.csv"
)
V02_PATH = REPOSITORY_ROOT / "data" / "dielectric_v02.csv"
ADDITIONS_PATH = (
    REPOSITORY_ROOT / "data" / "processed" / "modern_solvent_public_observations.csv"
)
EXCLUSIONS_PATH = (
    REPOSITORY_ROOT / "data" / "processed" / "dielectric_v03_exclusions.csv"
)
V032_PATH = REPOSITORY_ROOT / "data" / "dielectric_v032.csv"


def _read_rows(path: Path) -> list[dict[str, str]]:
    _, rows = read_csv_rows(path)
    return rows


def _shipped_patch_rows() -> list[dict[str, str]]:
    return _read_rows(PROVENANCE_PATCHES_PATH)


def _rebuild_shipped_rows() -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Rebuild v0.3 exactly the way the CLI does, provenance patches included."""

    rows = build_v03_rows(
        _read_rows(V02_PATH),
        [*_read_rows(ADDITIONS_PATH), *_read_rows(REVIEW_OBSERVATIONS_PATH)],
        minimum_additions=30,
        excluded_model_keys={row["inchikey"] for row in _read_rows(EXCLUSIONS_PATH)},
    )
    return apply_provenance_patches(rows, _shipped_patch_rows())


def _one_row(inchikey: str = "AAAA-BBBB-C", **overrides: str) -> dict[str, str]:
    row = {"inchikey": inchikey, "name": "test compound", "notes": ""}
    row.update(overrides)
    return row


@pytest.mark.parametrize("field", sorted(PROVENANCE_PATCH_PROTECTED_FIELDS))
def test_provenance_patch_rejects_every_protected_field(field: str) -> None:
    patch = {
        "inchikey": "AAAA-BBBB-C",
        "field": field,
        "value": "tampered",
        "rationale": "should never be accepted",
    }

    with pytest.raises(ValueError, match="targets protected field"):
        apply_provenance_patches([_one_row()], [patch])


@pytest.mark.parametrize("missing", ["inchikey", "field", "value", "rationale"])
def test_provenance_patch_rejects_incomplete_patch(missing: str) -> None:
    patch = {
        "inchikey": "AAAA-BBBB-C",
        "field": "notes",
        "value": "value",
        "rationale": "why",
    }
    patch[missing] = ""

    with pytest.raises(ValueError, match=f"is missing: {missing}"):
        apply_provenance_patches([_one_row()], [patch])


def test_provenance_patch_rejects_unknown_compound() -> None:
    patch = {
        "inchikey": "ZZZZ-BBBB-C",
        "field": "notes",
        "value": "value",
        "rationale": "why",
    }

    with pytest.raises(ValueError, match="targets unknown compound"):
        apply_provenance_patches([_one_row()], [patch])


def test_provenance_patch_rejects_repeated_compound_field() -> None:
    patch = {
        "inchikey": "AAAA-BBBB-C",
        "field": "notes",
        "value": "value",
        "rationale": "why",
    }

    with pytest.raises(ValueError, match="repeats"):
        apply_provenance_patches([_one_row()], [patch, dict(patch)])


def test_provenance_patch_records_previous_value_and_leaves_input_untouched() -> None:
    original = [_one_row(notes="old note")]
    patch = {
        "inchikey": "AAAA-BBBB-C",
        "field": "notes",
        "value": "new note",
        "rationale": "because",
    }

    patched, applied = apply_provenance_patches(original, [patch])

    assert original[0]["notes"] == "old note"
    assert patched[0]["notes"] == "new note"
    assert applied == [
        {
            "inchikey": "AAAA-BBBB-C",
            "name": "test compound",
            "field": "notes",
            "previous_value": "old note",
            "value": "new note",
            "rationale": "because",
        }
    ]


def test_shipped_patch_file_is_complete_and_auditable() -> None:
    patches = _shipped_patch_rows()

    assert patches, "the shipped patch file must not be empty"
    for position, patch in enumerate(patches, start=1):
        assert set(patch) == {"inchikey", "field", "value", "rationale"}, position
        assert patch["value"].strip(), position
        assert patch["rationale"].strip(), position
        assert patch["field"] not in PROVENANCE_PATCH_PROTECTED_FIELDS, position
        assert "?" * 4 not in patch["value"], f"mojibake in patch {position}"


def test_shipped_patches_apply_cleanly_to_the_current_inputs() -> None:
    _, applied = _rebuild_shipped_rows()

    assert len(applied) == len(_shipped_patch_rows())
    assert len({(row["inchikey"], row["field"]) for row in applied}) == len(applied)


def test_shipped_patches_survive_a_full_rebuild() -> None:
    """P0-3 regression: a rebuild must not silently drop provenance patches."""

    with V03_PATH.open(encoding="utf-8", newline="") as handle:
        frozen = {row["inchikey"]: row for row in csv.DictReader(handle)}
    _, applied = _rebuild_shipped_rows()

    assert applied
    for record in applied:
        assert frozen[record["inchikey"]][record["field"]] == record["value"], record


def test_shipped_patches_are_metadata_only() -> None:
    """v0.3.3 is a provenance revision: it must not move modelling inputs."""

    _, applied = _rebuild_shipped_rows()

    touched = {row["field"] for row in applied}
    assert touched
    assert not touched & set(PROVENANCE_PATCH_PROTECTED_FIELDS)


def test_existing_model_ready_observations_are_stable_from_v032_to_v03() -> None:
    """No compound already usable in v0.3.2 may change value, temperature or
    readiness in v0.3.3.  If one did, every controlled benchmark number would
    have to be re-derived before any v0.3.3 claim could be made."""

    with V03_PATH.open(encoding="utf-8", newline="") as handle:
        current = {row["inchikey"]: row for row in csv.DictReader(handle)}
    with V032_PATH.open(encoding="utf-8", newline="") as handle:
        previous = {row["inchikey"]: row for row in csv.DictReader(handle)}

    compared = 0
    for inchikey, old_row in previous.items():
        if old_row["model_ready"] != "true":
            continue
        assert inchikey in current, inchikey
        new_row = current[inchikey]
        for field in ("dielectric", "T_K", "model_ready", "temperature_band"):
            assert new_row[field] == old_row[field], (inchikey, field)
        compared += 1

    assert compared > 200, compared


def test_build_summary_records_patch_provenance() -> None:
    summary = json.loads(V03_SUMMARY_PATH.read_text(encoding="utf-8"))

    assert summary["provenance_patches"]["applied_count"] == len(
        _shipped_patch_rows()
    )
    assert summary["inputs"]["provenance_patches_sha256"] == canonical_text_sha256(
        PROVENANCE_PATCHES_PATH
    )


KNOWN_NON_MODEL_READY_MODELLING_ROWS = frozenset(
    {
        # Vinylene carbonate is flagged model_ready=false / conflict_open in
        # v0.3.2, yet it is still present in the modelling feature file and is
        # therefore trained on today.  The modelling pipeline gates on the
        # exclusion list plus feature success, not on model_ready; recorded in
        # reports/v033_findings.md.  Fixing the wiring changes the benchmark and
        # must be a deliberate, separately reported decision.
        "VAYTZRYEBVHVLE-UHFFFAOYSA-N",
    }
)


def test_only_known_non_model_ready_rows_reach_the_modelling_feature_file() -> None:
    """Guard against quietly growing the model_ready / modelling-set mismatch."""

    features_path = (
        REPOSITORY_ROOT / "data" / "processed" / "dielectric_physical_features_v03.csv"
    )
    with V03_PATH.open(encoding="utf-8", newline="") as handle:
        dataset = {row["inchikey"]: row for row in csv.DictReader(handle)}
    with features_path.open(encoding="utf-8", newline="") as handle:
        features = list(csv.DictReader(handle))

    offenders = {
        row["inchikey"]
        for row in features
        if row.get("status") != "error"
        and dataset[row["inchikey"]]["model_ready"] != "true"
    }

    assert offenders == set(KNOWN_NON_MODEL_READY_MODELLING_ROWS)


def test_mopn_gap_row_is_recorded_but_held_out_of_the_model() -> None:
    with V03_PATH.open(encoding="utf-8", newline="") as handle:
        rows = {row["inchikey"]: row for row in csv.DictReader(handle)}

    mopn = rows["OOWFYDWAMOKVSF-UHFFFAOYSA-N"]
    assert mopn["dataset_origin"] == "v0.3_addition"
    assert mopn["dielectric"] == "36.0"
    assert mopn["T_K"] == "298.15"
    assert mopn["model_ready"] == "false"
    assert mopn["evidence_level"] == "secondary_compilation_unverified"
    assert mopn["conflict_status"] == "awaiting_primary_confirmation"
    assert mopn["source_dois_all"] == (
        "10.1016/j.electacta.2013.01.084;10.1002/adfm.202212342"
    )


def test_mopn_secondary_compilation_row_claims_no_open_licence() -> None:
    """MOPN must not borrow an open licence it does not have."""

    rows = _read_review_observations()
    mopn = next(
        row for row in rows if row["inchikey"] == "OOWFYDWAMOKVSF-UHFFFAOYSA-N"
    )

    assert mopn["source_quality"] == "secondary_compilation_publisher_si"
    assert mopn["source_doi"] == "10.1016/j.electacta.2013.01.084"
    assert mopn["source_license"] == ""
    assert mopn["license_url"] == ""
    assert mopn["redistribution_conditions"] == ""
    assert mopn["redistribution_status"] == "allowed"
    assert mopn["model_ready"] == "false"
    assert mopn["conflict_status"] == "awaiting_primary_confirmation"
