"""Shared anchor-compound definitions for spot checks and cross-verification.

Two groups live here on purpose:

``SPOT_CHECK_ANCHORS``
    A verbatim copy of the Week 1 spot-check anchors, which still live inline
    in ``scripts/build_week1_closure.py``.  That script feeds a
    byte-reproducible artifact: ``scripts/verify_week1.py`` pins it by
    hardcoded counts and the Week 1 export manifest hashes it, so refactoring
    it to import from here would have a large blast radius for no functional
    gain.  Instead ``tests/test_anchor_definitions.py`` extracts the inline
    tuple with ``ast`` and asserts the two definitions stay identical, which
    gives the same drift protection without touching the artifact.  The entries
    stay plain mappings because ``build_week1_closure`` indexes them by key.

``V02_CROSSCHECK_ANCHORS``
    The v0.2 anchor set (benzene, methanol, acetonitrile, ethylene
    carbonate, propylene carbonate, DMC, DEC).  It is a strict superset
    in intent but a separate constant: adding entries to
    ``SPOT_CHECK_ANCHORS`` would add rows to ``p1_spot_check.csv`` and
    break ``scripts/verify_week1.py``.
"""

from __future__ import annotations

from dataclasses import dataclass

SPOT_CHECK_ANCHORS: tuple[dict[str, object], ...] = (
    {
        "anchor_id": "water_297K",
        "name": "water",
        "aliases": ("water",),
        "property_family": "zero_frequency",
        "expected_value": 78.4,
        "expected_temperature": 297.15,
        "frequency": 0.0,
        "tolerance": 0.5,
        "selection_rule": (
            "Exact component name; zero-frequency; 297.15 K; prefer pure component."
        ),
    },
    {
        "anchor_id": "acetonitrile_298K_1MHz",
        "name": "acetonitrile",
        "aliases": ("acetonitrile",),
        "property_family": "frequency_dependent",
        "expected_value": 35.9,
        "expected_temperature": 298.15,
        "frequency": 1.0,
        "tolerance": 0.5,
        "selection_rule": (
            "Exact component name; frequency-dependent 1 MHz; 298.15 K; "
            "prefer pure component."
        ),
    },
    {
        "anchor_id": "sulfolane_303K",
        "name": "sulfolane",
        "aliases": ("sulfolane",),
        "property_family": "zero_frequency",
        "expected_value": 43.3,
        "expected_temperature": 303.15,
        "frequency": 0.0,
        "tolerance": 0.5,
        "selection_rule": (
            "Exact component name; zero-frequency; 303.15 K; prefer pure component."
        ),
    },
    {
        "anchor_id": "dmc_298K",
        "name": "dimethyl carbonate",
        "aliases": ("dimethyl carbonate", "dmc"),
        "property_family": "zero_frequency",
        "expected_value": 3.09,
        "expected_temperature": 298.15,
        "frequency": 0.0,
        "tolerance": 0.05,
        "selection_rule": (
            "Exact component name; zero-frequency; 298.15 K; prefer pure component."
        ),
    },
    {
        "anchor_id": "methanol_298K",
        "name": "methanol",
        "aliases": ("methanol",),
        "property_family": "zero_frequency",
        "expected_value": 32.6,
        "expected_temperature": 298.15,
        "frequency": 0.0,
        "tolerance": 0.2,
        "selection_rule": (
            "Exact component name; zero-frequency; 298.15 K; prefer pure component."
        ),
    },
    {
        "anchor_id": "propylene_carbonate_298K",
        "name": "propylene carbonate",
        "aliases": ("propylene carbonate", "pc"),
        "property_family": "zero_frequency",
        "expected_value": 64.9,
        "expected_temperature": 298.15,
        "frequency": 0.0,
        "tolerance": 0.5,
        "selection_rule": (
            "Exact component name; zero-frequency; 298.15 K; no manual row is fabricated."
        ),
    },
)

EC_TEMPERATURE_GUARD: dict[str, object] = {
    "anchor_id": "ethylene_carbonate_temperature_guard",
    "name": "ethylene carbonate",
    "gate_flags": "temperature_gate|exclude_liquid_298K",
    "selection_rule": (
        "Do not accept EC as a liquid pure solvent near 298.15 K because its "
        "melting point is about 309.5 K."
    ),
    "notes": (
        "Guard row retained so the near-298 K liquid gate cannot silently admit EC."
    ),
}


@dataclass(frozen=True, slots=True)
class CrosscheckAnchor:
    """One v0.2 anchor compound and how to recognise it in each source table."""

    anchor_id: str
    name: str
    inchikey: str
    aliases: tuple[str, ...]
    reference_value: float | None
    reference_temperature_K: float | None
    reference_frequency_MHz: float | None
    tolerance: float
    blocking_reason: str


V02_CROSSCHECK_ANCHORS: tuple[CrosscheckAnchor, ...] = (
    CrosscheckAnchor(
        anchor_id="benzene_298K",
        name="benzene",
        inchikey="UHOVQNZJYSORNB-UHFFFAOYSA-N",
        aliases=("benzene",),
        reference_value=2.284,
        reference_temperature_K=293.15,
        reference_frequency_MHz=0.0,
        tolerance=0.05,
        blocking_reason=(
            "in-window NIST rows are a single-temperature composition series "
            "from 10.1021/acs.jced.5b00369 (2.288-3.404 at 298.15 K); "
            "correctly rejected by the is_pure gate"
        ),
    ),
    CrosscheckAnchor(
        anchor_id="methanol_298K",
        name="methanol",
        inchikey="OKKJLVBELUTLKV-UHFFFAOYSA-N",
        aliases=("methanol",),
        reference_value=32.6,
        reference_temperature_K=298.15,
        reference_frequency_MHz=0.0,
        tolerance=0.2,
        blocking_reason="",
    ),
    CrosscheckAnchor(
        anchor_id="acetonitrile_298K_1MHz",
        name="acetonitrile",
        inchikey="WEVYAHXRMPXWCK-UHFFFAOYSA-N",
        aliases=("acetonitrile",),
        reference_value=35.9,
        reference_temperature_K=298.15,
        reference_frequency_MHz=1.0,
        tolerance=0.5,
        blocking_reason=(
            "all 111 NIST rows are frequency_dependent (110 at 1 MHz, 1 at 0.01 MHz); "
            "correctly excluded by the zero_frequency gate"
        ),
    ),
    CrosscheckAnchor(
        anchor_id="ethylene_carbonate_313K_1MHz",
        name="ethylene carbonate",
        inchikey="KMTRUDSVKNLOMY-UHFFFAOYSA-N",
        aliases=("ethylene carbonate",),
        reference_value=90.5,
        reference_temperature_K=313.15,
        reference_frequency_MHz=1.0,
        tolerance=0.5,
        blocking_reason=(
            "no NIST ThermoML rows at all; sole datum is a manual literature row "
            "at 313.15 K / 1 MHz; mp ~309.5 K puts it outside the near-room liquid window"
        ),
    ),
    CrosscheckAnchor(
        anchor_id="propylene_carbonate_298K",
        name="propylene carbonate",
        inchikey="RUOJZAUFBMNUDX-UHFFFAOYSA-N",
        aliases=("propylene carbonate", "pc"),
        reference_value=64.9,
        reference_temperature_K=298.15,
        reference_frequency_MHz=0.0,
        tolerance=0.5,
        blocking_reason=(
            "no NIST ThermoML rows at all; the 64.9 manual reference has no traceable source"
        ),
    ),
    CrosscheckAnchor(
        anchor_id="dmc_298K",
        name="dimethyl carbonate",
        inchikey="IEJIGPNLZYLLBP-UHFFFAOYSA-N",
        aliases=("dimethyl carbonate", "dmc"),
        reference_value=3.09,
        reference_temperature_K=298.15,
        reference_frequency_MHz=0.0,
        tolerance=0.05,
        blocking_reason="",
    ),
    CrosscheckAnchor(
        anchor_id="dec_298K",
        name="diethyl carbonate",
        inchikey="OIFBSDVPJOWBCH-UHFFFAOYSA-N",
        aliases=("diethyl carbonate", "dec"),
        reference_value=2.834,
        reference_temperature_K=298.15,
        reference_frequency_MHz=0.0,
        tolerance=0.05,
        blocking_reason="",
    ),
)
