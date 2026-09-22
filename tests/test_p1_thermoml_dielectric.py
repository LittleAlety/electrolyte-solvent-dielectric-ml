from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from pathlib import Path

from thermoml_io import (
    Citation,
    Compound,
    DataPoint,
    DataSet,
    MeasuredValue,
    PropertyDefinition,
    SourceProvenance,
    ThermoMLDocument,
    Uncertainty,
    VariableDefinition,
)

from probes.export_week1_results import build_week1_report
from probes.p1_thermoml_dielectric import (
    _robust_histogram_upper_bound,
    build_source_metadata,
    classify_solvent_family,
    decide_mainline,
    extract_observations,
    summarize_observations,
)


def _document() -> ThermoMLDocument:
    compound = Compound(
        local_id=1,
        common_names=("ethylene carbonate",),
        formula="C3H4O3",
        standard_inchi_key="KMTRUDSVKNLOMY-UHFFFAOYSA-N",
    )
    property_definition = PropertyDefinition(
        number=1,
        name="Relative permittivity at zero frequency",
        phase="Liquid",
    )
    temperature = VariableDefinition(number=1, name="Temperature, K", phase="Liquid")
    data_set = DataSet(
        number=1,
        component_ids=(1,),
        properties=(property_definition,),
        variables=(temperature,),
        points=(
            DataPoint(
                index=1,
                variable_values=(MeasuredValue(1, Decimal("298.15"), "298.15"),),
                property_values=(
                    MeasuredValue(
                        1,
                        Decimal("89.78"),
                        "89.78",
                        uncertainties=(
                            Uncertainty(
                                kind="combined",
                                expanded_value=Decimal("0.05"),
                                confidence_level=Decimal(95),
                            ),
                        ),
                    ),
                ),
            ),
        ),
    )
    return ThermoMLDocument(
        version_major=4,
        version_minor=0,
        citation=Citation(
            title="Fixture",
            doi="10.0000/fixture",
            publication_name="Test",
            year=2026,
        ),
        compounds=(compound,),
        datasets=(data_set,),
        provenance=SourceProvenance(
            locator="fixture.xml",
            sha256="a" * 64,
        ),
    )


def test_extracts_observation_with_temperature_and_uncertainty() -> None:
    observations = extract_observations((_document(),))

    assert len(observations) == 1
    observation = observations[0]
    assert observation.property_family == "zero_frequency"
    assert observation.temperature_k == Decimal("298.15")
    assert observation.value == Decimal("89.78")
    assert observation.expanded_uncertainty == Decimal("0.05")
    assert observation.confidence_level == Decimal(95)
    assert observation.primary_inchi_key == "KMTRUDSVKNLOMY-UHFFFAOYSA-N"


def test_gate_thresholds_match_week_one_handbook() -> None:
    assert decide_mainline(300) == "mainline_go"
    assert decide_mainline(299) == "dielectric_viscosity_joint"
    assert decide_mainline(100) == "dielectric_viscosity_joint"
    assert decide_mainline(99) == "pivot_to_p3_or_p4"


def test_classifies_common_battery_solvent_families() -> None:
    assert classify_solvent_family("ethylene carbonate") == "carbonate"
    assert classify_solvent_family("1,2-dimethoxyethane") == "ether"
    assert classify_solvent_family("acetonitrile") == "nitrile"
    assert classify_solvent_family("sulfolane") == "sulfone"
    assert classify_solvent_family("unknown example") == "other"


def test_summary_counts_unique_components_by_family() -> None:
    first = extract_observations((_document(),))[0]
    second = replace(first, value=Decimal("90.0"))
    ether = replace(
        first,
        primary_name="1,2-dimethoxyethane",
        components=(
            {
                "name": "1,2-dimethoxyethane",
                "formula": "C4H10O2",
                "standard_inchi": "",
                "standard_inchi_key": "XTHFKEDIFFGKHM-UHFFFAOYSA-N",
                "cas_registry_number": "",
            },
        ),
    )

    summary = summarize_observations((first, second, ether))

    assert summary["unique_component_family_counts"] == {"carbonate": 1, "ether": 1}
    assert summary["zero_frequency_family_counts_near_center"] == {
        "carbonate": 1,
        "ether": 1,
    }


def test_mainline_gate_excludes_mixture_partners_at_decision_boundary() -> None:
    base = extract_observations((_document(),))[0]
    pure_observations = []
    for index in range(99):
        name = f"pure-component-{index}"
        component = {
            "name": name,
            "formula": "",
            "standard_inchi": "",
            "standard_inchi_key": f"PURE{index:04d}",
            "cas_registry_number": "",
        }
        pure_observations.append(
            replace(
                base,
                components=(component,),
                primary_name=name,
                primary_inchi_key=component["standard_inchi_key"],
            )
        )

    partner = {
        "name": "mixture-partner",
        "formula": "",
        "standard_inchi": "",
        "standard_inchi_key": "MIXTUREPARTNER",
        "cas_registry_number": "",
    }
    mixture = replace(
        base,
        component_count=2,
        is_pure=False,
        components=(pure_observations[0].components[0], partner),
    )

    summary = summarize_observations((*pure_observations, mixture))

    assert summary["unique_zero_frequency_components_near_center"] == 100
    assert summary["pure_zero_frequency_components_near_center"] == 99
    assert summary["mainline_gate_component_count"] == 99
    assert summary["mainline_decision"] == "pivot_to_p3_or_p4"


def test_fallback_source_metadata_marks_gate_provisional() -> None:
    metadata = build_source_metadata((), raw_dir=Path("data/raw/thermoml"))

    assert metadata["source_mode"] == "individual_xml_fallback"
    assert metadata["fallback_query_census"] is True
    assert metadata["complete_archive_available"] is False
    assert metadata["handbook_gate_executed"] is False
    assert metadata["decision_status"] == "provisional"
    assert "ThermoML.v2020-09-30.tgz" in metadata["source_limitation"]


def test_week_one_report_includes_gate_and_coverage() -> None:
    observation = extract_observations((_document(),))[0]
    summary = summarize_observations((observation,))

    report = build_week1_report(summary)

    assert "mainline_decision" in report
    assert "target_family_components_near_center" in report
    assert "P0 gate: PASS" in report


def test_week_one_report_labels_fallback_gate_provisional() -> None:
    observation = extract_observations((_document(),))[0]
    summary = summarize_observations((observation,))
    summary.update(build_source_metadata((), raw_dir=Path("data/raw/thermoml")))

    report = build_week1_report(summary)

    assert "P1 provisional decision" in report
    assert "P1 handbook gate: NOT formally executed" in report
    assert "decision_status: `provisional`" in report
    assert "handbook_gate_executed: `False`" in report
    assert "source_mode: `individual_xml_fallback`" in report
    assert "but do not enter the gate" in report.casefold()


def test_histogram_upper_bound_is_robust_to_extreme_outlier() -> None:
    values = [float(value) for value in range(1, 101)] + [568.0]
    upper_bound = _robust_histogram_upper_bound(values)

    assert 100.0 <= upper_bound < 568.0
