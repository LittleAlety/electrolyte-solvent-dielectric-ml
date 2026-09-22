from __future__ import annotations

import copy
import csv
import json
from pathlib import Path

from scripts.verify_dielectric_v01_ext import (
    _independent_nist,
    check_ec_summary,
    check_nist_compounds,
    check_nist_observations,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def _load():
    compound_rows = list(
        csv.DictReader(
            (REPOSITORY_ROOT / "data" / "dielectric_v01_ext.csv").open(
                encoding="utf-8",
                newline="",
            )
        )
    )
    observation_rows = list(
        csv.DictReader(
            (
                REPOSITORY_ROOT
                / "data"
                / "processed"
                / "dielectric_v01_ext_observations.csv"
            ).open(encoding="utf-8", newline="")
        )
    )
    summary = json.loads(
        (
            REPOSITORY_ROOT / "probes" / "dielectric_v01_ext_summary.json"
        ).read_text(encoding="utf-8")
    )
    return compound_rows, observation_rows, summary


def test_extension_verifier_rejects_nist_median_tampering() -> None:
    compound_rows, _, _ = _load()
    tampered = copy.deepcopy(compound_rows)
    tampered[0]["dielectric"] = str(float(tampered[0]["dielectric"]) + 1)

    result = check_nist_compounds(tampered, root=REPOSITORY_ROOT)

    assert result.passed is False
    assert "median" in result.detail


def test_extension_verifier_rejects_nist_source_hash_tampering() -> None:
    _, observation_rows, _ = _load()
    tampered = copy.deepcopy(observation_rows)
    first_p1 = next(
        index
        for index, row in enumerate(tampered)
        if row["dataset_source"] == "P1 ThermoML"
    )
    tampered[first_p1]["sha256"] = "0" * 64

    result = check_nist_observations(tampered, root=REPOSITORY_ROOT)

    assert result.passed is False
    assert "source hash" in result.detail


def test_extension_verifier_rejects_ec_metadata_tampering() -> None:
    _, _, summary = _load()
    tampered = copy.deepcopy(summary)
    tampered["ec_manual_entry"]["uncertainty_relative_percent_max"] = "2.0"

    result = check_ec_summary(tampered)

    assert result.passed is False
    assert "EC" in result.detail


def test_extension_verifier_normalizes_windows_source_file(tmp_path) -> None:
    processed = tmp_path / "data" / "processed"
    processed.mkdir(parents=True)
    (processed / "dielectric_raw.csv").write_text(
        "property_family,is_pure,temperature_k,primary_inchi,primary_name,"
        "value,source_file,source_sha256,doi,expanded_uncertainty,"
        "standard_uncertainty,uncertainty_kind,confidence_level\n"
        "zero_frequency,True,313.15,InChI=1S/CH4/h1H4,methane,1.8,"
        "C:\\data\\raw\\thermoml\\x.xml,abc,10.1000/example,,,, \n",
        encoding="utf-8",
    )

    _, observations = _independent_nist(tmp_path)

    assert observations[0]["source_file"] == "data/raw/thermoml/x.xml"
