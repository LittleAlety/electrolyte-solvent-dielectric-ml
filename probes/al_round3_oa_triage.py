#!/usr/bin/env python
"""Week 12 "weekend buffer" side branch: title/abstract-level OA triage.

Takes the 37 open-access leads Week 11 left behind (``al_round3_candidates.csv``)
and turns them into an acquisition shortlist for AL Round 3.

Hard scope of this probe:

* title/abstract level only - no full text is read, and nothing is downloaded
  beyond a small ranged probe whose only purpose is to read an HTTP status code;
* OA availability is re-verified against Unpaywall ``is_oa`` + ``best_oa_location``;
* abstracts come from OpenAlex (Crossref as a fallback) and are searched only for
  a permittivity cue and for an *explicit* temperature window;
* every failure is recorded verbatim with its status code - nothing is invented.

Restricted values and restricted full texts never enter any output.  The CSV and
the JSON carry DOIs, titles, OA status flags and short title/abstract snippets
only; no measurement table is built and no feature is derived here.
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import io
import json
import re
import sys
import time
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

# The Week 11 candidate list lives outside the repository, under the weekly
# delivery tree.  The tracked copy under data/processed/ is byte-identical and
# serves as the fallback so a clean clone can still re-run this probe.
DEFAULT_LEADS = REPOSITORY_ROOT.parent / "\u6210\u679c\u8f93\u51fa" / "week11" / "al_round3_candidates.csv"
FALLBACK_LEADS = REPOSITORY_ROOT / "data" / "processed" / "al_round3_candidates.csv"
REFERENCE_ROUND3_SCRIPT = REPOSITORY_ROOT / "probes" / "al_round3_candidates.py"

DEFAULT_CSV_OUTPUT = REPOSITORY_ROOT / "probes" / "al_round3_oa_triage.csv"
DEFAULT_JSON_OUTPUT = REPOSITORY_ROOT / "probes" / "al_round3_oa_triage_summary.json"
DEFAULT_REPORT_OUTPUT = REPOSITORY_ROOT / "reports" / "al_round3_oa_triage.md"

USER_AGENT = "electrolyte-ml-research/1.0 (AL round-3 title/abstract triage; mailto:codex@local)"
DEFAULT_MAILTO = "codex@local"

UNPAYWALL_ENDPOINT = "https://api.unpaywall.org/v2"
OPENALEX_WORKS_ENDPOINT = "https://api.openalex.org/works"
CROSSREF_WORKS_ENDPOINT = "https://api.crossref.org/works"

HTTP_TIMEOUT_SECONDS = 60
DEFAULT_SLEEP_SECONDS = 1.0
DEFAULT_REQUEST_LIMIT = 220
JSON_BODY_MAX_BYTES = 4_000_000
OA_PROBE_MAX_BYTES = 8192
BACKOFF_SECONDS = (5.0, 15.0)
MAX_BACKOFF_SECONDS = 45.0
EVIDENCE_CHAR_CAP = 400
SNIPPET_CHAR_CAP = 200

# The temperature window the target compounds are missing data for.
WINDOW_MIN_K = 253.0
WINDOW_MAX_K = 333.0

# Target taxonomy.  "core" families are the compounds the round is hunting for
# (missing epsilon(T)); "adjacent" families are battery solvents that are already
# partly covered, so they are worth a look but are not the point of the round.
TARGET_FAMILY_BY_COMPOUND: Mapping[str, str] = {
    "1,2-dimethoxyethane": "glyme",
    "diglyme": "glyme",
    "triglyme": "glyme",
    "tetraglyme": "glyme",
    "1,2-dimethoxypropane": "glyme",
    "succinonitrile": "nitrile",
    "glutaronitrile": "nitrile",
    "adiponitrile": "nitrile",
    "malononitrile": "nitrile",
    "3-methoxypropionitrile": "nitrile",
    "sulfolane": "sulfone",
    "methoxy-nonafluorobutane": "fluorinated_ether",
    "ethoxy-nonafluorobutane": "fluorinated_ether",
    "1,1,2,2-tetrafluoroethyl 2,2,2-trifluoroethyl ether": "fluorinated_ether",
    "ethylene carbonate": "carbonate_ester",
    "propylene carbonate": "carbonate_ester",
    "ethyl methyl carbonate": "carbonate_ester",
    "dimethyl carbonate": "carbonate_ester",
    "diethyl carbonate": "carbonate_ester",
    "tripropylene glycol": "glycol_ether",
    # Resolved, but explicitly not battery solvents.  Listing them keeps a brand
    # name in a title ("Novec") from being read as a target family when the
    # molecule it actually names is, say, a perfluoroalkane.
    "water": "water",
    "1-butanol": "alcohol",
    "ethane-1,2-diol": "diol",
    "2,2,2-trifluoroethanol": "fluoroalcohol",
    "hexafluoroisopropanol": "fluoroalcohol",
    "decafluoropentane": "fluoroalkane",
    "perfluorohexane": "fluoroalkane",
}
CORE_FAMILIES = frozenset({"glyme", "nitrile", "sulfone", "fluorinated_ether"})
ADJACENT_FAMILIES = frozenset({"carbonate_ester", "glycol_ether"})

# Compounds the task names explicitly but the Week 11 hand-curated table lacks.
# They are added here (with the same "one unambiguous molecule" rule) so that a
# title or abstract naming them resolves instead of falling through.
SUPPLEMENTARY_COMPOUNDS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("sulfolane", "O=S1(=O)CCCC1", ("sulfolane", "tetramethylene sulfone")),
    (
        "3-methoxypropionitrile",
        "COCCC#N",
        ("3-methoxypropionitrile", "methoxypropionitrile", "mopn"),
    ),
    (
        "1,1,2,2-tetrafluoroethyl 2,2,2-trifluoroethyl ether",
        "FC(F)C(F)(F)OCC(F)(F)F",
        ("hfe-347", "hfe 347"),
    ),
)

# Text-level family cues, used only when no single molecule resolved.  Order
# matters: core families are tested before adjacent ones.
FAMILY_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "glyme",
        ("glyme", "glymes", "dimethoxyethane", "diglyme", "triglyme", "tetraglyme"),
    ),
    (
        "nitrile",
        (
            "dinitrile",
            "dinitriles",
            "adiponitrile",
            "succinonitrile",
            "glutaronitrile",
            "malononitrile",
            "nitrile",
            "nitriles",
        ),
    ),
    ("sulfone", ("sulfolane", "sulfone", "sulfones")),
    (
        "fluorinated_ether",
        (
            "fluorinated ether",
            "fluorinated ethers",
            "fluoroether",
            "fluoroethers",
            "hydrofluoroether",
            "hydrofluoroethers",
        ),
    ),
    ("carbonate_ester", ("carbonate", "carbonates", "ester solvent", "ester solvents")),
    ("glycol_ether", ("glycol ether", "glycol ethers", "polyglyme")),
)

# A permittivity number has to survive these filters, otherwise a digit inside a
# chemical formula ("G4", "LiClO4"), a ratio ("EC:EMC 3:7") or a unit ("4.3 V")
# is mistaken for a dielectric constant.  Week 11's line-level helper is too
# permissive for abstract prose, so abstracts get their own stricter rule.
EPS_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")
# A permittivity number has to be *assigned* to the cue, not merely near it.
# The pattern is anchored right after the cue and allows one connector word
# ("of", "is", "extrapolated to", "=" ...) plus at most two filler words, so
# the "6" of "LiPF 6" is never reachable from "dielectric constant of".
EPS_ASSIGN_RE = re.compile(
    r"[\s,:;]*"
    r"(?:(?:(?:of|for|is|was|were|are|equals?|equal\s+to|reaches?|reaching|about|around|"
    r"approximately|approx\.?|to|near)\s+)|(?:[=\u2248~\u223c]\s*))?"
    r"(?:[\w\-\u2019'=\u2248~]+\s+){0,2}?"
    r"(\d+(?:\.\d+)?)",
    re.IGNORECASE,
)
EPS_NUMBER_WINDOW = 120
MIN_PLAUSIBLE_EPSILON = 1.0
MAX_PLAUSIBLE_EPSILON = 500.0
EPS_UNIT_AFTER_RE = re.compile(
    r"^\s*(?:(?:\u00d7|x(?=\s*10))|\u2212|V\b|mV\b|kV\b|M\b|mM\b|mol\b|mmol\b|K\b|[\u00b0]\s*C|[\u2103]|%|wt|w/w|v/v|vol"
    r"|GPa\b|MPa\b|kPa\b|Pa\b|bar\b|atm\b|nm\b|um\b|\u03bcm\b|mm\b|cm\b|m\b|mA\b|\u00b5A\b"
    r"|S\s*cm|S/cm|S\b|g\b|kg\b|mg\b|h\b|min\b|s\b|Hz\b|kHz\b|MHz\b|GHz\b|ppm\b)"
)

# A "28 K superheat" is a temperature *difference*, not an absolute
# temperature.  Every token inside such a sentence is dropped so the triage
# never claims "outside the window" from a difference.
TEMPERATURE_DIFFERENCE_MARKERS = (
    "superheat",
    "superheating",
    "subcool",
    "undercool",
    "onset of boiling",
    "temperature difference",
    "temperature rise",
    "temperature drop",
    "temperature jump",
    "temperature increase",
    "temperature decrease",
    "temperature depression",
    "excess temperature",
    "delta t",
    "\u0394t",
)
MIN_ABSOLUTE_KELVIN = 60.0

# A 2xx HTML body smaller than this is a landing page, not the article.
LANDING_PAGE_BYTES = 20_000

ROOM_TEMPERATURE_CUES = (
    "room temperature",
    "ambient temperature",
    "ambient conditions",
    "at 25 c",
)

# Explicit temperature syntax.  Only a unit-bearing number counts; "room
# temperature" is deliberately not converted into a numeric window.
_TEMP_UNIT = r"(?:K|[\u00b0]\s*C|[\u2103]|degrees?\s*C|deg\s*C)"
TEMP_RANGE_RE = re.compile(
    r"(\d{1,4}(?:\.\d+)?)\s*(?:-|\u2013|\u2014|\u2212|to|through|~)\s*"
    r"(\d{1,4}(?:\.\d+)?)\s*(" + _TEMP_UNIT + r")(?![A-Za-z0-9])",
    re.IGNORECASE,
)
TEMP_COMPARATOR_RE = re.compile(
    r"(\d{1,4}(?:\.\d+)?)\s*(" + _TEMP_UNIT + r")?\s*[<\u2264]\s*T\s*[<\u2264]\s*"
    r"(\d{1,4}(?:\.\d+)?)\s*(" + _TEMP_UNIT + r")",
    re.IGNORECASE,
)
TEMP_POINT_RE = re.compile(
    r"(?<![\d.])(\d{1,4}(?:\.\d+)?)\s*(" + _TEMP_UNIT + r")(?![A-Za-z0-9])",
    re.IGNORECASE,
)
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?;])\s+(?=[A-Z0-9(\u201c\u2018])")
JATS_TAG_RE = re.compile(r"<[^>]+>")

OUTPUT_COLUMNS: tuple[str, ...] = (
    "doi",
    "title",
    "publication_year",
    "venue",
    "query_label",
    "week11_disposition",
    "week11_http_status",
    "compound_names",
    "inchikeys",
    "smiles_list",
    "compound_resolution",
    "unresolved_names",
    "target_class",
    "target_families",
    "target_reason",
    "epsilon_clue",
    "epsilon_clue_kind",
    "epsilon_numbers_in_title_or_abstract",
    "epsilon_evidence",
    "temperature_window_covered",
    "temperature_evidence_kind",
    "temperature_evidence",
    "temperature_skipped_non_absolute",
    "abstract_source",
    "abstract_read",
    "abstract_chars",
    "abstract_http_status",
    "abstract_note",
    "unpaywall_is_oa",
    "unpaywall_oa_status",
    "unpaywall_http_status",
    "best_oa_url",
    "best_oa_url_for_pdf",
    "best_oa_host_type",
    "best_oa_version",
    "best_oa_license",
    "oa_probe_method",
    "oa_probe_http_status",
    "oa_probe_final_url",
    "oa_probe_content_type",
    "oa_probe_bytes_read",
    "oa_probe_bot_check",
    "oa_probe_looks_like_landing_page",
    "oa_fulltext_reachable",
    "oa_note",
    "score_target",
    "score_epsilon",
    "score_temperature",
    "score_oa",
    "priority_score",
    "priority",
    "disposition",
    "rationale",
)
# ---------------------------------------------------------------------------
# Reference helpers reused from the Week 11 probe.
# ---------------------------------------------------------------------------


def load_reference_module(path: Path = REFERENCE_ROUND3_SCRIPT) -> Any:
    """Import the Week 11 candidate probe to reuse its curated compound table.

    Reusing it (rather than copying the name -> SMILES table) keeps the compound
    identities identical across the two rounds.
    """

    spec = importlib.util.spec_from_file_location("al_round3_candidates_ref", path)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise RuntimeError(f"cannot import reference probe at {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def build_compound_library(reference: Any) -> tuple[Any, ...]:
    """Week 11 curated entries plus the task-named supplementary compounds."""

    entries = list(reference.COMPOUND_LIBRARY)
    known = {entry.name for entry in entries}
    for name, smiles, _aliases in SUPPLEMENTARY_COMPOUNDS:
        if name not in known:
            entries.append(reference.CompoundEntry(name, smiles))
    return tuple(entries)


def build_alias_map(reference: Any) -> dict[str, tuple[str, ...]]:
    """Extra title spellings for the supplementary compounds only."""

    aliases = dict(reference.COMPOUND_ALIASES)
    for name, _smiles, extra in SUPPLEMENTARY_COMPOUNDS:
        merged = list(aliases.get(name, ()))
        for alias in extra:
            if alias not in merged and alias != name:
                merged.append(alias)
        aliases[name] = tuple(merged)
    return aliases


def smiles_by_name(reference: Any) -> dict[str, str]:
    table = {entry.name: entry.smiles for entry in reference.COMPOUND_LIBRARY}
    for name, smiles, _aliases in SUPPLEMENTARY_COMPOUNDS:
        table.setdefault(name, smiles)
    return table


# ---------------------------------------------------------------------------
# Title/abstract level analysis.
# ---------------------------------------------------------------------------


def split_sentences(text: str) -> list[str]:
    """Split an abstract into sentences without breaking decimals like 35.2."""

    parts = SENTENCE_SPLIT_RE.split(text)
    return [part.strip() for part in parts if part.strip()]


def snippet(text: str, cap: int = EVIDENCE_CHAR_CAP) -> str:
    """Collapse whitespace and cap a verbatim snippet.  Never paraphrased."""

    flat = re.sub(r"\s+", " ", text).strip()
    if len(flat) <= cap:
        return flat
    return flat[:cap].rstrip() + " ... [truncated]"


def to_kelvin(value: float, unit: str) -> float:
    unit_key = re.sub(r"\s+", "", unit).lower().replace("degrees", "deg")
    if unit_key in {"k"}:
        return value
    return value + 273.15


def _extract_temperatures(sentence: str) -> tuple[list[tuple[float, float]], list[float]]:
    """Unit-bearing temperatures in one sentence, ranges before points."""

    intervals: list[tuple[float, float]] = []
    points: list[float] = []
    spans: list[tuple[int, int]] = []

    for match in TEMP_COMPARATOR_RE.finditer(sentence):
        low = to_kelvin(float(match.group(1)), match.group(2) or match.group(4))
        high = to_kelvin(float(match.group(3)), match.group(4))
        intervals.append((min(low, high), max(low, high)))
        spans.append(match.span())

    for match in TEMP_RANGE_RE.finditer(sentence):
        if any(low <= match.start() < high for low, high in spans):
            continue
        first = to_kelvin(float(match.group(1)), match.group(3))
        second = to_kelvin(float(match.group(2)), match.group(3))
        intervals.append((min(first, second), max(first, second)))
        spans.append(match.span())

    for match in TEMP_POINT_RE.finditer(sentence):
        if any(low <= match.start() < high for low, high in spans):
            continue
        points.append(to_kelvin(float(match.group(1)), match.group(2)))

    return intervals, points


def _is_difference_sentence(sentence: str) -> bool:
    lowered = sentence.lower()
    return any(marker in lowered for marker in TEMPERATURE_DIFFERENCE_MARKERS)


def analyze_temperature(text: str) -> dict[str, Any]:
    """Classify the explicit temperature evidence in a title/abstract.

    ``temperature_window_covered``:

    * ``true``    - an explicit unit-bearing absolute temperature lies inside
      253-333 K;
    * ``false``   - unit-bearing absolute temperatures exist and every one of
      them lies outside 253-333 K;
    * ``unknown`` - no usable absolute temperature.  This covers both "nothing
      was said" and "only a temperature difference or a bare *room temperature*
      was said"; neither is converted into a window.

    Sentences that talk about a superheat / temperature difference are dropped
    wholesale, and Kelvin values below ``MIN_ABSOLUTE_KELVIN`` are ignored, so a
    "28 K wall superheat" can never masquerade as a 28 K measurement.
    """

    if not text:
        return {"covered": "unknown", "kind": "none", "evidence": "", "values_k": [], "skipped": []}

    intervals: list[tuple[float, float]] = []
    points: list[float] = []
    evidence = ""
    kind = "none"
    skipped: list[str] = []

    for sentence in split_sentences(text) or [text]:
        local_intervals, local_points = _extract_temperatures(sentence)
        if not local_intervals and not local_points:
            continue
        absolute_intervals = [pair for pair in local_intervals if pair[1] >= MIN_ABSOLUTE_KELVIN]
        absolute_points = [value for value in local_points if value >= MIN_ABSOLUTE_KELVIN]
        if _is_difference_sentence(sentence) or not absolute_intervals and not absolute_points:
            skipped.append(snippet(sentence, SNIPPET_CHAR_CAP))
            continue
        if len(absolute_intervals) != len(local_intervals) or len(absolute_points) != len(local_points):
            skipped.append(snippet(sentence, SNIPPET_CHAR_CAP))
        intervals.extend(absolute_intervals)
        points.extend(absolute_points)
        if not evidence:
            evidence = snippet(sentence, SNIPPET_CHAR_CAP)
            kind = "explicit_range" if absolute_intervals else "explicit_point"

    covered = "unknown"
    if intervals or points:
        inside = any(low <= WINDOW_MAX_K and high >= WINDOW_MIN_K for low, high in intervals) or any(
            WINDOW_MIN_K <= value <= WINDOW_MAX_K for value in points
        )
        covered = "true" if inside else "false"
    elif skipped:
        kind = "non_absolute_temperature_only"
        evidence = skipped[0]
    else:
        lowered = text.lower()
        if any(cue in lowered for cue in ROOM_TEMPERATURE_CUES):
            kind = "room_temperature_only"
            row = next(
                (
                    sentence
                    for sentence in split_sentences(text)
                    if "room temperature" in sentence.lower()
                ),
                "",
            )
            evidence = snippet(row or text, SNIPPET_CHAR_CAP)

    return {
        "covered": covered,
        "kind": kind,
        "evidence": evidence,
        "values_k": sorted({round(value, 2) for value in points}),
        "skipped": skipped,
    }


def _epsilon_number_is_clean(text: str, start: int, end: int) -> bool:
    """Reject numbers that belong to a formula, a ratio or a physical unit."""

    before = text[start - 1] if start > 0 else " "
    if before.isalpha():
        return False
    # Tails of scientific notation ("\u00d710", "\u22123") and signs are not
    # permittivities.
    if before in "-\u2212\u00d7\u00b1\u2013\u2014":
        return False
    # Second digit of a chemical-name prefix such as "1,2-" or of a ratio "3:7".
    if before in ":," and start >= 2 and text[start - 2].isdigit():
        return False
    if end < len(text):
        nxt = text[end]
        # "G4", "LiClO4": the digit is glued to a letter or another digit.
        if nxt.isalpha() or nxt.isdigit():
            return False
        # "1,2-" / "2,2,2-" / "1,2-dimethoxypropane"
        if nxt in ",-" and end + 1 < len(text) and text[end + 1].isalnum():
            return False
        # "EC:EMC 3:7"
        if nxt == ":":
            return False
    return not EPS_UNIT_AFTER_RE.match(text[end:])


def epsilon_numbers_near_cue(sentence: str, reference: Any) -> tuple[float, ...]:
    """Plausible permittivity numbers assigned to a permittivity cue."""

    values: list[float] = []
    for cue in reference.CONTEXT_CUE.finditer(sentence):
        window = sentence[cue.end():cue.end() + EPS_NUMBER_WINDOW]
        match = EPS_ASSIGN_RE.match(window)
        if match is None:
            continue
        start = cue.end() + match.start(1)
        end = cue.end() + match.end(1)
        value = float(match.group(1))
        if not (MIN_PLAUSIBLE_EPSILON <= value <= MAX_PLAUSIBLE_EPSILON):
            continue
        if not _epsilon_number_is_clean(sentence, start, end):
            continue
        values.append(value)
    return tuple(values)


def analyze_epsilon(text: str, reference: Any) -> dict[str, Any]:
    """Look for a permittivity clue at title/abstract level.

    ``kind`` is ``value`` only when a permittivity cue and a plausible
    permittivity number share a sentence *and* the number survives the
    formula/ratio/unit filters.  ``wording_only`` means the abstract talks about
    the dielectric constant without stating a number.  This is a lead, never a
    measurement claim: the sentence is kept verbatim so a human can judge it.
    """

    value_sentence = ""
    wording_sentence = ""
    numbers: tuple[float, ...] = ()
    for sentence in split_sentences(text):
        if not reference.CONTEXT_CUE.search(sentence):
            continue
        found = epsilon_numbers_near_cue(sentence, reference)
        if found and not value_sentence:
            value_sentence, numbers = sentence, found
        elif not wording_sentence:
            wording_sentence = sentence
    if value_sentence:
        return {
            "kind": "value",
            "evidence": snippet(value_sentence),
            "numbers": tuple(numbers),
        }
    if wording_sentence:
        return {"kind": "wording_only", "evidence": snippet(wording_sentence), "numbers": ()}
    return {"kind": "none", "evidence": "", "numbers": ()}


def resolve_compounds(
    *,
    title: str,
    abstract: str,
    reference: Any,
    library: Sequence[Any],
    alias_map: Mapping[str, tuple[str, ...]],
) -> tuple[list[Any], list[tuple[str, str]], list[str]]:
    """Resolve compounds named in the title or the abstract.

    ``find_compound_mentions`` reads the module-level alias table, so the
    supplementary aliases are patched in around the call and restored after.
    """

    original = reference.COMPOUND_ALIASES
    matches: list[Any] = []
    seen: set[str] = set()
    try:
        reference.COMPOUND_ALIASES = alias_map
        for text in (title, abstract):
            if not text:
                continue
            for match in reference.find_compound_mentions(text, library):
                if match.name not in seen:
                    seen.add(match.name)
                    matches.append(match)
    finally:
        reference.COMPOUND_ALIASES = original

    unresolved: list[tuple[str, str]] = []
    unresolved_seen: set[str] = set()
    for text in (title, abstract):
        if not text:
            continue
        for fragment, reason in reference.find_unresolved_names(text):
            if fragment not in unresolved_seen:
                unresolved_seen.add(fragment)
                unresolved.append((fragment, reason))
    return matches, unresolved, sorted(seen)


def keyword_hit(text_lower: str, keyword: str) -> bool:
    """Whole-token keyword test, so "hfe" cannot fire inside a longer word."""

    pattern = r"(?<![a-z0-9])" + re.escape(keyword) + r"(?![a-z0-9])"
    return re.search(pattern, text_lower) is not None


def classify_target(
    compound_names: Sequence[str],
    text: str,
) -> tuple[str, list[str], str]:
    """Return ``(target_class, families, reason)`` for one lead.

    A resolved molecule is authoritative: once any named compound maps to a
    known family the keyword scan is skipped, so a fluoroalkane heat-transfer
    fluid is never promoted to "fluorinated ether" by the brand name "Novec".
    The keyword scan therefore only serves titles/abstracts that name a family
    ("glyme-based electrolytes") without naming a single molecule.
    """

    families: list[str] = []
    for name in compound_names:
        family = TARGET_FAMILY_BY_COMPOUND.get(name)
        if family and family not in families:
            families.append(family)

    core = [family for family in families if family in CORE_FAMILIES]
    if core:
        return "core", families, "resolved compound in a core target family: " + ";".join(core)

    adjacent = [family for family in families if family in ADJACENT_FAMILIES]
    if adjacent:
        return (
            "adjacent",
            families,
            "resolved compound in an adjacent battery-solvent family: " + ";".join(adjacent),
        )

    if families:
        return (
            "off",
            families,
            "every resolved compound maps to a non-target family: " + ";".join(families),
        )

    lowered = text.lower()
    for family, keywords in FAMILY_KEYWORDS:
        hit = next((keyword for keyword in keywords if keyword_hit(lowered, keyword)), "")
        if not hit:
            continue
        families = [family]
        klass = "core_family_unresolved" if family in CORE_FAMILIES else "adjacent_family_unresolved"
        return (
            klass,
            families,
            f"no single molecule resolved, but the text names the {family} family (\u201c{hit}\u201d)",
        )
    return "off", families, "no target or adjacent solvent family detected in the title or abstract"


def score_lead(
    *,
    target_class: str,
    epsilon_kind: str,
    temperature_covered: str,
    oa_reachable: str,
) -> dict[str, Any]:
    """Deterministic, auditable scoring behind the P0-P3 ladder."""

    score_target = {
        "core": 3,
        "core_family_unresolved": 2,
        "adjacent": 1,
        "adjacent_family_unresolved": 1,
        "off": 0,
    }[target_class]
    score_epsilon = {"value": 3, "wording_only": 1, "none": 0}[epsilon_kind]
    score_temperature = {"true": 2, "unknown": 0, "false": -1}[temperature_covered]
    score_oa = {"true": 2, "unknown": 1, "false": 0}[oa_reachable]

    total = score_target + score_epsilon + score_temperature + score_oa
    if score_target >= 3 and score_epsilon >= 3 and total >= 8:
        priority = "P0"
    elif total >= 5 and score_target >= 1:
        priority = "P1"
    elif total >= 2:
        priority = "P2"
    else:
        priority = "P3"
    return {
        "score_target": score_target,
        "score_epsilon": score_epsilon,
        "score_temperature": score_temperature,
        "score_oa": score_oa,
        "priority_score": total,
        "priority": priority,
    }
# ---------------------------------------------------------------------------
# Polite HTTP layer.  Every request is counted; every failure is recorded.
# ---------------------------------------------------------------------------


@dataclass
class HttpResult:
    url: str
    status: int | None
    body: bytes
    content_type: str
    final_url: str
    error: str | None


class RequestBudget:
    """Hard cap on outbound requests, with a per-kind audit log."""

    def __init__(self, limit: int) -> None:
        self.limit = limit
        self.used = 0
        self.log: list[dict[str, Any]] = []

    def can_spend(self) -> bool:
        return self.used < self.limit

    def spend(self, kind: str, url: str, status: int | None, error: str | None = None) -> None:
        self.used += 1
        self.log.append({"kind": kind, "url": url, "status": status, "error": error})

    def counts_by_kind(self) -> dict[str, int]:
        return dict(Counter(entry["kind"] for entry in self.log))

    def status_counts(self) -> dict[str, int]:
        return dict(
            Counter(
                str(entry["status"]) if entry["status"] is not None else "error"
                for entry in self.log
            )
        )

    def failures(self) -> list[dict[str, Any]]:
        return [
            {"kind": entry["kind"], "url": entry["url"], "status": entry["status"], "error": entry["error"]}
            for entry in self.log
            if entry["error"] is not None or (entry["status"] is not None and entry["status"] >= 400)
        ]


class Throttle:
    """Keep at least ``sleep_seconds`` between two outbound requests."""

    def __init__(self, sleep_seconds: float, sleeper: Callable[[float], None] = time.sleep) -> None:
        self.sleep_seconds = sleep_seconds
        self._sleeper = sleeper
        self._last_started: float | None = None

    def wait(self) -> None:
        if self._last_started is not None and self.sleep_seconds > 0:
            elapsed = time.monotonic() - self._last_started
            if elapsed < self.sleep_seconds:
                self._sleeper(self.sleep_seconds - elapsed)
        self._last_started = time.monotonic()


def parse_retry_after(value: Any) -> float | None:
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return None
    return max(0.0, min(seconds, MAX_BACKOFF_SECONDS))


def http_get(
    url: str,
    *,
    params: Mapping[str, Any] | None,
    budget: RequestBudget,
    throttle: Throttle,
    kind: str,
    max_bytes: int,
    range_header: str | None = None,
    transport: Callable[..., HttpResult] | None = None,
) -> HttpResult:
    """Single outbound GET.  The only network touchpoint of this probe."""

    if not budget.can_spend():
        return HttpResult(url, None, b"", "", url, "request_budget_exhausted")

    throttle.wait()
    headers = {"User-Agent": USER_AGENT, "Accept": "*/*"}
    if range_header:
        headers["Range"] = range_header

    if transport is None:
        result = _requests_get(url, params=params, headers=headers, max_bytes=max_bytes)
    else:
        result = transport(url, params=params, headers=headers, max_bytes=max_bytes)

    budget.spend(kind, url, result.status, result.error)
    return result


def _requests_get(
    url: str,
    *,
    params: Mapping[str, Any] | None,
    headers: Mapping[str, str],
    max_bytes: int,
) -> HttpResult:
    import requests

    try:
        response = requests.get(
            url,
            params=dict(params) if params else None,
            headers=dict(headers),
            timeout=HTTP_TIMEOUT_SECONDS,
            stream=True,
            allow_redirects=True,
        )
    except Exception as exc:  # noqa: BLE001 - recorded verbatim, never swallowed
        detail = f"{type(exc).__name__}: {exc}"
        return HttpResult(url, None, b"", "", url, detail[:300])

    status = response.status_code
    content_type = response.headers.get("Content-Type", "")
    final_url = response.url
    error: str | None = None
    body = b""
    try:
        if max_bytes <= 0:
            body = response.content
        else:
            body = response.raw.read(max_bytes, decode_content=True) or b""
    except Exception as exc:  # noqa: BLE001
        error = f"{type(exc).__name__}: {exc}"[:300]
    finally:
        response.close()
    if status == 200 and max_bytes <= 0:
        body = response.content if body == b"" else body
    return HttpResult(url, status, body, content_type, final_url, error)


def http_get_with_backoff(
    url: str,
    *,
    params: Mapping[str, Any] | None,
    budget: RequestBudget,
    throttle: Throttle,
    kind: str,
    max_bytes: int,
    sleeper: Callable[[float], None] = time.sleep,
    transport: Callable[..., HttpResult] | None = None,
) -> HttpResult:
    """GET with a bounded 429 retry that honours Retry-After."""

    result = http_get(
        url,
        params=params,
        budget=budget,
        throttle=throttle,
        kind=kind,
        max_bytes=max_bytes,
        transport=transport,
    )
    for attempt in range(len(BACKOFF_SECONDS)):
        if result.status != 429:
            break
        delay = BACKOFF_SECONDS[attempt]
        sleeper(delay)
        result = http_get(
            url,
            params=params,
            budget=budget,
            throttle=throttle,
            kind=kind,
            max_bytes=max_bytes,
            transport=transport,
        )
    return result


def decode_json(result: HttpResult) -> Any:
    if result.status != 200 or not result.body:
        return None
    try:
        return json.loads(result.body.decode("utf-8", "replace"))
    except (ValueError, UnicodeDecodeError):
        return None


def fetch_unpaywall(
    doi: str,
    *,
    budget: RequestBudget,
    throttle: Throttle,
    mailto: str,
    transport: Callable[..., HttpResult] | None = None,
) -> dict[str, Any]:
    url = f"{UNPAYWALL_ENDPOINT}/{quote(doi)}"
    result = http_get_with_backoff(
        url,
        params={"email": mailto},
        budget=budget,
        throttle=throttle,
        kind="unpaywall",
        max_bytes=JSON_BODY_MAX_BYTES,
        transport=transport,
    )
    return {"http_status": result.status, "error": result.error, "payload": decode_json(result)}


def fetch_openalex(
    doi: str,
    *,
    budget: RequestBudget,
    throttle: Throttle,
    mailto: str,
    transport: Callable[..., HttpResult] | None = None,
) -> dict[str, Any]:
    url = f"{OPENALEX_WORKS_ENDPOINT}/doi:{quote(doi)}"
    result = http_get_with_backoff(
        url,
        params={"mailto": mailto},
        budget=budget,
        throttle=throttle,
        kind="openalex",
        max_bytes=JSON_BODY_MAX_BYTES,
        transport=transport,
    )
    return {"http_status": result.status, "error": result.error, "payload": decode_json(result)}


def fetch_crossref(
    doi: str,
    *,
    budget: RequestBudget,
    throttle: Throttle,
    mailto: str,
    transport: Callable[..., HttpResult] | None = None,
) -> dict[str, Any]:
    url = f"{CROSSREF_WORKS_ENDPOINT}/{quote(doi)}"
    result = http_get_with_backoff(
        url,
        params={"mailto": mailto},
        budget=budget,
        throttle=throttle,
        kind="crossref",
        max_bytes=JSON_BODY_MAX_BYTES,
        transport=transport,
    )
    return {"http_status": result.status, "error": result.error, "payload": decode_json(result)}


def invert_abstract(index: Any) -> str:
    """Rebuild an OpenAlex ``abstract_inverted_index`` into plain text."""

    if not isinstance(index, Mapping):
        return ""
    positions: dict[int, str] = {}
    for word, indexes in index.items():
        if not isinstance(indexes, Sequence):
            continue
        for position in indexes:
            if isinstance(position, int):
                positions[position] = word
    if not positions:
        return ""
    return " ".join(positions[key] for key in sorted(positions))


def crossref_abstract_text(payload: Any) -> str:
    """Pull the Crossref abstract and strip its JATS markup."""

    if not isinstance(payload, Mapping):
        return ""
    message = payload.get("message")
    if not isinstance(message, Mapping):
        return ""
    raw = message.get("abstract")
    if not isinstance(raw, str):
        return ""
    text = JATS_TAG_RE.sub(" ", raw)
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    return re.sub(r"\s+", " ", text).strip()


def probe_oa_location(
    url: str,
    *,
    budget: RequestBudget,
    throttle: Throttle,
    reference: Any,
    transport: Callable[..., HttpResult] | None = None,
) -> dict[str, Any]:
    """Read an HTTP status for an OA location without downloading the article.

    A ranged GET capped at ``OA_PROBE_MAX_BYTES`` is used instead of HEAD because
    several publishers answer HEAD with 405.  The body is never kept: only the
    status code, the content type and a bot-check flag are recorded.
    """

    result = http_get(
        url,
        params=None,
        budget=budget,
        throttle=throttle,
        kind="oa_probe",
        max_bytes=OA_PROBE_MAX_BYTES,
        range_header=f"bytes=0-{OA_PROBE_MAX_BYTES - 1}",
        transport=transport,
    )
    text = ""
    if result.body and ("text" in result.content_type.lower() or "html" in result.content_type.lower()
                        or not result.content_type):
        text = result.body.decode("utf-8", "replace")
    bot_check = bool(text) and reference.is_bot_check(text)

    content_type_lower = result.content_type.lower()
    looks_like_landing = (
        result.status is not None
        and 200 <= result.status < 300
        and result.status != 206
        and "html" in content_type_lower
        and len(result.body) < OA_PROBE_MAX_BYTES
        and len(result.body) < LANDING_PAGE_BYTES
    )

    if result.error:
        reachable = "false"
        note = f"probe transport error: {result.error}"
    elif result.status is not None and 200 <= result.status < 300:
        if bot_check:
            reachable = "false"
            note = "bot-check page returned"
        elif looks_like_landing:
            reachable = "unknown"
            note = (
                f"2xx HTML body of only {len(result.body)} bytes "
                "(no Range support): looks like a landing page, not the article"
            )
        else:
            reachable = "true"
            note = "2xx and not a bot-check page"
    else:
        reachable = "false"
        note = f"probe HTTP {result.status}"

    return {
        "method": "ranged_get_0_8191",
        "http_status": result.status,
        "final_url": result.final_url if result.final_url != url else "",
        "content_type": result.content_type,
        "bytes_read": len(result.body),
        "bot_check": bot_check,
        "looks_like_landing": looks_like_landing,
        "reachable": reachable,
        "note": note,
        "error": result.error,
    }
# ---------------------------------------------------------------------------
# Per-lead triage.
# ---------------------------------------------------------------------------

DISPOSITION_BY_PRIORITY: Mapping[str, str] = {
    "P0": "human_reading_list",
    "P1": "human_reading_list",
    "P2": "pending",
    "P3": "discard",
}


@dataclass
class TriageContext:
    reference: Any
    library: tuple[Any, ...]
    alias_map: Mapping[str, tuple[str, ...]]
    smiles: Mapping[str, str]
    budget: RequestBudget
    throttle: Throttle
    mailto: str
    offline: bool = False
    transport: Callable[..., HttpResult] | None = None


def _bool_text(value: Any) -> str:
    if value is True:
        return "true"
    if value is False:
        return "false"
    return ""


def triage_lead(lead: Mapping[str, str], ctx: TriageContext) -> dict[str, str]:
    """Title/abstract-level triage for one Week 11 lead."""

    row = {column: "" for column in OUTPUT_COLUMNS}
    doi = (lead.get("doi") or "").strip()
    title = (lead.get("title") or "").strip()
    row["doi"] = doi
    row["title"] = title
    row["publication_year"] = (lead.get("publication_year") or "").strip()
    row["query_label"] = (lead.get("query_label") or "").strip()
    row["week11_disposition"] = (lead.get("disposition") or "").strip()
    row["week11_http_status"] = (lead.get("http_status") or "").strip()

    # -- metadata + abstract -------------------------------------------------
    openalex: dict[str, Any] = {"http_status": None, "error": None, "payload": None}
    crossref: dict[str, Any] = {"http_status": None, "error": None, "payload": None}
    unpaywall: dict[str, Any] = {"http_status": None, "error": None, "payload": None}
    if not ctx.offline:
        openalex = fetch_openalex(
            doi,
            budget=ctx.budget,
            throttle=ctx.throttle,
            mailto=ctx.mailto,
            transport=ctx.transport,
        )
        unpaywall = fetch_unpaywall(
            doi,
            budget=ctx.budget,
            throttle=ctx.throttle,
            mailto=ctx.mailto,
            transport=ctx.transport,
        )

    abstract = ""
    abstract_source = "not read"
    payload = openalex.get("payload")
    if isinstance(payload, Mapping):
        primary = payload.get("primary_location") or {}
        source = (primary.get("source") or {}) if isinstance(primary, Mapping) else {}
        row["venue"] = (source.get("display_name") or "") if isinstance(source, Mapping) else ""
        if not row["publication_year"] and payload.get("publication_year"):
            row["publication_year"] = str(payload["publication_year"])
        abstract = invert_abstract(payload.get("abstract_inverted_index"))
        if abstract:
            abstract_source = "openalex"

    abstract_note = ""
    abstract_status = ""
    if abstract:
        abstract_status = "" if openalex["http_status"] is None else str(openalex["http_status"])
        if ctx.offline:
            abstract_status = ""
    else:
        reason_bits = []
        if ctx.offline:
            abstract_source = "offline"
            reason_bits.append("offline run: no API request issued")
        else:
            reason_bits.append(
                f"OpenAlex HTTP {openalex['http_status'] if openalex['http_status'] is not None else 'error'}"
                + (f" ({openalex['error']})" if openalex.get("error") else "")
                + ": no abstract_inverted_index"
            )
            if ctx.budget.can_spend():
                crossref = fetch_crossref(
                    doi,
                    budget=ctx.budget,
                    throttle=ctx.throttle,
                    mailto=ctx.mailto,
                    transport=ctx.transport,
                )
                abstract = crossref_abstract_text(crossref.get("payload"))
                if abstract:
                    abstract_source = "crossref"
                    abstract_status = str(crossref["http_status"])
                reason_bits.append(
                    f"Crossref HTTP {crossref['http_status'] if crossref['http_status'] is not None else 'error'}"
                    + (f" ({crossref['error']})" if crossref.get("error") else "")
                    + (": abstract present" if abstract else ": no abstract field")
                )
            else:
                reason_bits.append("Crossref not attempted: request budget exhausted")
        if not abstract:
            abstract_source = "offline" if ctx.offline else "not read"
            abstract_note = "abstract not read: " + "; ".join(reason_bits)

    row["abstract_source"] = abstract_source
    row["abstract_read"] = "true" if abstract else "false"
    row["abstract_chars"] = str(len(abstract))
    row["abstract_http_status"] = abstract_status
    row["abstract_note"] = abstract_note

    combined = " ".join(part for part in (title, abstract) if part)

    # -- compound mapping ----------------------------------------------------
    matches, unresolved, names = resolve_compounds(
        title=title,
        abstract=abstract,
        reference=ctx.reference,
        library=ctx.library,
        alias_map=ctx.alias_map,
    )
    row["compound_names"] = ";".join(match.name for match in matches)
    row["inchikeys"] = ";".join(match.inchikey for match in matches)
    row["smiles_list"] = ";".join(ctx.smiles.get(match.name, "") for match in matches)
    if matches and not unresolved:
        row["compound_resolution"] = "resolved"
    elif matches and unresolved:
        row["compound_resolution"] = "partially_resolved"
    else:
        row["compound_resolution"] = "unresolved"
    row["unresolved_names"] = ";".join(f"{frag}={reason}" for frag, reason in unresolved)

    target_class, families, target_reason = classify_target(names, combined)
    row["target_class"] = target_class
    row["target_families"] = ";".join(families)
    row["target_reason"] = target_reason

    # -- epsilon / temperature ----------------------------------------------
    epsilon = analyze_epsilon(combined, ctx.reference)
    row["epsilon_clue"] = "yes" if epsilon["kind"] in {"value", "wording_only"} else "no"
    row["epsilon_clue_kind"] = epsilon["kind"]
    row["epsilon_numbers_in_title_or_abstract"] = ";".join(
        f"{value:g}" for value in epsilon["numbers"]
    )
    row["epsilon_evidence"] = epsilon["evidence"]

    temperature = analyze_temperature(combined)
    row["temperature_window_covered"] = temperature["covered"]
    row["temperature_evidence_kind"] = temperature["kind"]
    row["temperature_evidence"] = temperature["evidence"]
    row["temperature_skipped_non_absolute"] = (
        temperature["skipped"][0] if temperature["skipped"] else ""
    )

    # -- OA verification -----------------------------------------------------
    up = unpaywall.get("payload")
    up_payload = up if isinstance(up, Mapping) else {}
    is_oa = up_payload.get("is_oa")
    best = up_payload.get("best_oa_location")
    best_location = best if isinstance(best, Mapping) else {}
    row["unpaywall_is_oa"] = _bool_text(is_oa)
    row["unpaywall_oa_status"] = str(up_payload.get("oa_status") or "")
    row["unpaywall_http_status"] = (
        "" if unpaywall["http_status"] is None else str(unpaywall["http_status"])
    )
    row["best_oa_url"] = str(best_location.get("url") or "")
    row["best_oa_url_for_pdf"] = str(best_location.get("url_for_pdf") or "")
    row["best_oa_host_type"] = str(best_location.get("host_type") or "")
    row["best_oa_version"] = str(best_location.get("version") or "")
    row["best_oa_license"] = str(best_location.get("license") or "")

    probe_url = row["best_oa_url_for_pdf"] or row["best_oa_url"]
    probe: dict[str, Any]
    if ctx.offline:
        probe = {
            "method": "not_attempted_offline",
            "http_status": None,
            "final_url": "",
            "content_type": "",
            "bytes_read": 0,
            "bot_check": False,
            "looks_like_landing": False,
            "reachable": "unknown",
            "note": "offline run: OA location not probed",
            "error": None,
        }
    elif is_oa is True and probe_url:
        probe = probe_oa_location(
            probe_url,
            budget=ctx.budget,
            throttle=ctx.throttle,
            reference=ctx.reference,
            transport=ctx.transport,
        )
    elif is_oa is False:
        probe = {
            "method": "not_attempted_not_oa",
            "http_status": None,
            "final_url": "",
            "content_type": "",
            "bytes_read": 0,
            "bot_check": False,
            "looks_like_landing": False,
            "reachable": "false",
            "note": "Unpaywall reports is_oa=false, so no OA full text exists to fetch",
            "error": None,
        }
    elif is_oa is True:
        probe = {
            "method": "not_attempted_no_location",
            "http_status": None,
            "final_url": "",
            "content_type": "",
            "bytes_read": 0,
            "bot_check": False,
            "looks_like_landing": False,
            "reachable": "unknown",
            "note": "Unpaywall reports is_oa=true but returned no best_oa_location URL",
            "error": None,
        }
    else:
        status = unpaywall["http_status"]
        probe = {
            "method": "not_attempted_unpaywall_failed",
            "http_status": None,
            "final_url": "",
            "content_type": "",
            "bytes_read": 0,
            "bot_check": False,
            "looks_like_landing": False,
            "reachable": "unknown",
            "note": "Unpaywall lookup failed"
            + (f" (HTTP {status})" if status is not None else "")
            + "; OA status unknown, so nothing was probed",
            "error": unpaywall.get("error"),
        }

    row["oa_probe_method"] = str(probe["method"])
    row["oa_probe_http_status"] = "" if probe["http_status"] is None else str(probe["http_status"])
    row["oa_probe_final_url"] = str(probe["final_url"])
    row["oa_probe_content_type"] = str(probe["content_type"])
    row["oa_probe_bytes_read"] = str(probe["bytes_read"])
    row["oa_probe_bot_check"] = _bool_text(probe["bot_check"])
    row["oa_probe_looks_like_landing_page"] = _bool_text(probe["looks_like_landing"])
    row["oa_fulltext_reachable"] = str(probe["reachable"])
    row["oa_note"] = str(probe["note"])

    # -- scoring and disposition --------------------------------------------
    scores = score_lead(
        target_class=target_class,
        epsilon_kind=epsilon["kind"],
        temperature_covered=temperature["covered"],
        oa_reachable=probe["reachable"],
    )
    priority = scores["priority"]
    noise_rules = ctx.reference.classify_noise(title) if title else ()
    if noise_rules:
        priority = "P3"
        veto = "noise veto (" + ", ".join(noise_rules) + ")"
    elif target_class == "off" and epsilon["kind"] == "none":
        priority = "P3"
        veto = "veto: neither a target/adjacent solvent family nor a permittivity clue"
    else:
        veto = ""

    row["score_target"] = str(scores["score_target"])
    row["score_epsilon"] = str(scores["score_epsilon"])
    row["score_temperature"] = str(scores["score_temperature"])
    row["score_oa"] = str(scores["score_oa"])
    row["priority_score"] = str(scores["priority_score"])
    row["priority"] = priority
    row["disposition"] = DISPOSITION_BY_PRIORITY[priority]
    row["rationale"] = "; ".join(
        part
        for part in (
            f"target={target_class}",
            f"epsilon={epsilon['kind']}",
            f"temperature={temperature['covered']}",
            f"oa={probe['reachable']}",
            f"score={scores['priority_score']}",
            veto,
        )
        if part
    )
    return row


def write_csv(path: Path, rows: Sequence[Mapping[str, str]]) -> None:
    """Write the triage CSV with LF terminators and a UTF-8 (no BOM) encoding."""

    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=list(OUTPUT_COLUMNS), lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({column: row.get(column, "") for column in OUTPUT_COLUMNS})
    text = buffer.getvalue()
    path.write_text(text, encoding="utf-8", newline="\n")
# ---------------------------------------------------------------------------
# Summary, verification and report.
# ---------------------------------------------------------------------------


def _counts(values: Sequence[str]) -> dict[str, int]:
    return dict(sorted(Counter(values).items()))


def verify_outputs(
    *,
    rows: Sequence[Mapping[str, str]],
    leads: Sequence[Mapping[str, str]],
    csv_path: Path,
    json_path: Path,
    report_path: Path,
    budget: RequestBudget,
    check_report: bool = True,
) -> dict[str, Any]:
    """Self-checks that must hold before the triage is called verified."""

    checks: list[dict[str, Any]] = []

    def check(name: str, passed: bool, detail: str) -> None:
        checks.append({"check": name, "passed": bool(passed), "detail": detail})

    lead_dois = [(lead.get("doi") or "").strip() for lead in leads]
    row_dois = [row["doi"] for row in rows]
    check(
        "row_count_matches_input",
        len(rows) == len(leads) == 37,
        f"rows={len(rows)} leads={len(leads)} expected=37",
    )
    check(
        "doi_set_matches_input",
        set(row_dois) == set(lead_dois),
        f"missing={sorted(set(lead_dois) - set(row_dois))} extra={sorted(set(row_dois) - set(lead_dois))}",
    )
    check("doi_unique", len(set(row_dois)) == len(row_dois), f"unique={len(set(row_dois))}")

    priority_counts = Counter(row["priority"] for row in rows)
    disposition_counts = Counter(row["disposition"] for row in rows)
    check(
        "priority_counts_sum_to_row_count",
        sum(priority_counts.values()) == len(rows),
        f"{dict(priority_counts)}",
    )
    check(
        "disposition_counts_sum_to_row_count",
        sum(disposition_counts.values()) == len(rows),
        f"{dict(disposition_counts)}",
    )
    check(
        "priority_in_domain",
        all(row["priority"] in {"P0", "P1", "P2", "P3"} for row in rows),
        "P0/P1/P2/P3 only",
    )
    check(
        "disposition_in_domain",
        all(row["disposition"] in {"human_reading_list", "pending", "discard"} for row in rows),
        "human_reading_list/pending/discard only",
    )
    check(
        "disposition_follows_priority",
        all(
            row["disposition"]
            == DISPOSITION_BY_PRIORITY[row["priority"]]
            for row in rows
        ),
        "P0/P1 -> human_reading_list, P2 -> pending, P3 -> discard",
    )

    raw = csv_path.read_bytes()
    check("csv_is_utf8_no_bom", not raw.startswith(b"\xef\xbb\xbf"), "no UTF-8 BOM")
    check("csv_is_lf_only", b"\r" not in raw, f"CR bytes={raw.count(chr(13).encode())}")
    parsed = list(csv.DictReader(io.StringIO(raw.decode("utf-8"), newline="")))
    check(
        "csv_header_matches_schema",
        tuple(parsed[0].keys()) == OUTPUT_COLUMNS if parsed else False,
        f"columns={len(parsed[0]) if parsed else 0}",
    )
    check("csv_row_count", len(parsed) == len(rows), f"parsed={len(parsed)} rows={len(rows)}")

    evidence_columns = ("epsilon_evidence", "temperature_evidence", "temperature_skipped_non_absolute")
    over_cap = [
        row["doi"]
        for row in rows
        for column in evidence_columns
        if len(row[column]) > EVIDENCE_CHAR_CAP + 32
    ]
    check("evidence_snippets_capped", not over_cap, f"over_cap={over_cap}")

    abstract_sources = {row["abstract_source"] for row in rows}
    check(
        "abstract_source_in_domain",
        abstract_sources <= {"openalex", "crossref", "not read", "offline"},
        f"sources={sorted(abstract_sources)}",
    )
    inconsistent = [
        row["doi"]
        for row in rows
        if (row["abstract_read"] == "true") != (row["abstract_source"] in {"openalex", "crossref"})
    ]
    check("abstract_read_flag_consistent", not inconsistent, f"inconsistent={inconsistent}")
    unread_without_reason = [
        row["doi"]
        for row in rows
        if row["abstract_read"] == "false" and "abstract not read" not in row["abstract_note"]
    ]
    check(
        "unread_abstracts_state_a_reason",
        not unread_without_reason,
        f"missing reason={unread_without_reason}",
    )

    restricted = (REPOSITORY_ROOT / "paper").resolve()
    restricted_data = (REPOSITORY_ROOT / "data" / "restricted").resolve()
    outside = []
    for path in (csv_path, json_path, report_path):
        resolved = path.resolve()
        if restricted in resolved.parents or restricted_data in resolved.parents:
            outside.append(str(resolved))
    check("outputs_outside_restricted_trees", not outside, f"violations={outside}")

    probe_ok = 0
    probe_bot = 0
    for row in rows:
        if row["oa_fulltext_reachable"] == "true":
            probe_ok += 1
        if row["oa_probe_bot_check"] == "true":
            probe_bot += 1
    check(
        "oa_reachable_requires_a_2xx_probe",
        probe_ok
        == sum(
            1
            for row in rows
            if row["oa_probe_http_status"].isdigit()
            and 200 <= int(row["oa_probe_http_status"]) < 300
            and row["oa_probe_bot_check"] != "true"
            and row["oa_probe_looks_like_landing_page"] != "true"
        ),
        f"reachable={probe_ok} bot_check_2xx={probe_bot}",
    )
    check(
        "request_budget_respected",
        budget.used <= budget.limit,
        f"used={budget.used} limit={budget.limit}",
    )
    if check_report:
        check("report_written", report_path.exists(), str(report_path))

    passed = all(item["passed"] for item in checks)
    return {"checks": checks, "verification_passed": passed}


LIMITATIONS: tuple[str, ...] = (
    "标题/摘要级判断：没有读全文，也没有下载任何受限全文；本清单只用于决定“谁值得人工去读”。",
    (
        "化合物身份来自 Week 11 手工维护的 name/alias -> SMILES 表，加上本脚本补充的 3 个目标化合物"
        "（sulfolane / 3-methoxypropionitrile / HFE-347）。它只能回答“标题或摘要里点名了哪个分子”，"
        "不是从正文抽结构；泛指 glyme、类别名词、聚合物、盐、品牌名一律记为 unresolved。"
    ),
    (
        "ε 线索只是“摘要里出现了介电措辞 + 一个合理数值”，不是测量值，也不区分“本文实测”与“引用文献值”。"
        "数值必须通过“不是化学式里的数字（G4、LiClO4）、不是配比（EC:EMC 3:7）、不带单位（4.3 V）”的过滤；"
        "日常实践中它仍会漏掉写成“ε 值约为某数”的句子，也可能误收对比句里的数字。"
    ),
    (
        "温度判定只认带单位的显式绝对温度（K/°C）。整句谈论 superheat / 温差的句子被整体丢弃，"
        "低于 60 K 的开尔文值也不算绝对温度，避免把“28 K 过热度”当成实测温度。"
        "只写 room temperature / ambient 的一律记为 unknown，不做 298 K 换算；"
        "false 的含义是“标题/摘要里出现的绝对温度全部在 253-333 K 之外”，不等于“正文里没有该窗口的数据”。"
    ),
    (
        "OA 可得性以 Unpaywall 的 is_oa + best_oa_location 为准，再对该 OA 链接发一次 ≤ 8 KB 的范围 GET 取状态码，"
        "**响应体不保留**。reachable=true 只表示“匿名请求拿到 2xx、不是机器人校验页、也不是一片小于 20 KB 的 HTML 落地页”，"
        "不等于“全文可解析、能取到 ε 数值”；状态码 206 表示服务器支持 Range，看不到总大小。"
    ),
    (
        "Unpaywall 说 is_oa=false 的条目没有探测 OA 链接，reachable 记为 false，含义是“不存在可匿名获取的 OA 全文”，"
        "不代表机构订阅也拿不到。"
    ),
    (
        "API 失败按实际状态码/异常原文记录；本次运行碰到的 403 大多是出版商的 Cloudflare 拦截，"
        "匿名 UA 下无法区分“内容受保护”与“拒绝机器人访问”。"
    ),
    "本支线只产线索清单，不建数据集、不建特征；任何受限值都没有进入本报告或产物文件。",
)


def build_summary(
    *,
    rows: Sequence[Mapping[str, str]],
    leads: Sequence[Mapping[str, str]],
    budget: RequestBudget,
    offline: bool,
    leads_path: Path,
    csv_path: Path,
    json_path: Path,
    report_path: Path,
    elapsed_seconds: float,
    check_report: bool = True,
) -> dict[str, Any]:
    verification = verify_outputs(
        rows=rows,
        leads=leads,
        csv_path=csv_path,
        json_path=json_path,
        report_path=report_path,
        budget=budget,
        check_report=check_report,
    )
    return {
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "run_mode": "offline" if offline else "online",
        "elapsed_seconds": round(elapsed_seconds, 2),
        "lead_count": len(rows),
        "inputs": {"leads": str(leads_path), "reference_probe": str(REFERENCE_ROUND3_SCRIPT)},
        "priority_counts": _counts([row["priority"] for row in rows]),
        "disposition_counts": _counts([row["disposition"] for row in rows]),
        "epsilon_clue_counts": _counts([row["epsilon_clue"] for row in rows]),
        "epsilon_clue_kind_counts": _counts([row["epsilon_clue_kind"] for row in rows]),
        "epsilon_numeric_clue_count": sum(1 for row in rows if row["epsilon_clue_kind"] == "value"),
        "temperature_window_counts": _counts([row["temperature_window_covered"] for row in rows]),
        "oa_fulltext_reachable_counts": _counts([row["oa_fulltext_reachable"] for row in rows]),
        "unpaywall_is_oa_counts": _counts(
            [row["unpaywall_is_oa"] or "unknown" for row in rows]
        ),
        "target_class_counts": _counts([row["target_class"] for row in rows]),
        "abstract_source_counts": _counts([row["abstract_source"] for row in rows]),
        "abstract_read_counts": _counts([row["abstract_read"] for row in rows]),
        "compound_resolution_counts": _counts([row["compound_resolution"] for row in rows]),
        "oa_probe_status_counts": _counts(
            [row["oa_probe_http_status"] or "not_probed" for row in rows]
        ),
        "api": {
            "request_limit": budget.limit,
            "requests_used": budget.used,
            "requests_by_kind": budget.counts_by_kind(),
            "responses_by_status": budget.status_counts(),
            "failures": budget.failures()[:60],
            "failure_count": len(budget.failures()),
            "sleep_seconds_between_requests": DEFAULT_SLEEP_SECONDS,
            "user_agent": USER_AGENT,
            "mailto": DEFAULT_MAILTO,
        },
        "unread_abstracts": [
            {"doi": row["doi"], "reason": row["abstract_note"]}
            for row in rows
            if row["abstract_read"] == "false"
        ],
        "verification": verification,
        "verification_passed": verification["verification_passed"],
        "limitations": list(LIMITATIONS),
        "outputs": {
            "csv": str(csv_path),
            "summary_json": str(json_path),
            "report": str(report_path),
            "script": str(REPOSITORY_ROOT / "probes" / "al_round3_oa_triage.py"),
        },
    }


def _md_cell(value: str) -> str:
    return (value or "").replace("|", "\\|").replace("\n", " ")


def _short(value: str, limit: int) -> str:
    flat = re.sub(r"\s+", " ", value or "").strip()
    return flat if len(flat) <= limit else flat[: limit - 1] + "\u2026"

PRIORITY_ORDER = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}

TARGET_CLASS_LABEL = {
    "core": "core 目标",
    "core_family_unresolved": "core 族(未定位分子)",
    "adjacent": "相邻(碳酸酯/酯)",
    "adjacent_family_unresolved": "相邻族(未定位分子)",
    "off": "非目标",
}

EPSILON_LABEL = {"value": "有(数值)", "wording_only": "仅措辞", "none": "无"}

TEMPERATURE_LABEL = {"true": "覆盖", "false": "在外", "unknown": "未知"}

DISPOSITION_LABEL = {
    "human_reading_list": "进人工阅读清单",
    "pending": "待定",
    "discard": "丢弃",
}


def _priority_table(rows: Sequence[Mapping[str, str]]) -> list[str]:
    header = (
        "| # | DOI | 化合物/体系 | 目标类 | \u03b5 \u7ebf\u7d22 | \u6e29\u7a97 253\u2013333 K "
        "| OA \u5168\u6587 | \u4f18\u5148\u7ea7 | \u5206\u6d41 |"
    )
    lines = [header, "|---|---|---|---|---|---|---|---|---|"]
    for index, row in enumerate(rows, start=1):
        oa = row["oa_fulltext_reachable"]
        oa_label = {"true": "\u53ef\u5f97", "false": "\u4e0d\u53ef\u5f97", "unknown": "\u672a\u77e5"}[oa]
        if row["oa_probe_http_status"]:
            oa_label += f" ({row['oa_probe_http_status']})"
        if row["oa_probe_looks_like_landing_page"] == "true":
            oa_label += " 落地页"
        lines.append(
            "| {} | `{}` | {} | {} | {} | {} | {} | {} | {} |".format(
                index,
                _md_cell(row["doi"]),
                _md_cell(_short(row["compound_names"] or "unresolved", 46)),
                TARGET_CLASS_LABEL.get(row["target_class"], row["target_class"]),
                EPSILON_LABEL.get(row["epsilon_clue_kind"], row["epsilon_clue_kind"]),
                TEMPERATURE_LABEL.get(
                    row["temperature_window_covered"], row["temperature_window_covered"]
                ),
                oa_label,
                row["priority"],
                DISPOSITION_LABEL.get(row["disposition"], row["disposition"]),
            )
        )
    return lines


def _evidence_table(rows: Sequence[Mapping[str, str]]) -> list[str]:
    lines = [
        "| DOI | \u03b5 \u8bc1\u636e\uff08\u6807\u9898/\u6458\u8981\u9010\u5b57\uff09 | \u6e29\u5ea6\u8bc1\u636e\uff08\u9010\u5b57\uff09 | \u6765\u6e90 |",
        "|---|---|---|---|",
    ]
    for row in rows:
        source = row["abstract_source"]
        lines.append(
            "| `{}` | {} | {} | {} |".format(
                _md_cell(row["doi"]),
                _md_cell(row["epsilon_evidence"] or "(\u65e0)"),
                _md_cell(row["temperature_evidence"] or "(\u65e0)"),
                source,
            )
        )
    return lines


def render_report(summary: Mapping[str, Any], rows: Sequence[Mapping[str, str]]) -> str:
    ordered = sorted(
        enumerate(rows, start=1),
        key=lambda pair: (PRIORITY_ORDER[pair[1]["priority"]], pair[0]),
    )
    ordered_rows = [row for _index, row in ordered]

    reading = [row for row in ordered_rows if row["disposition"] == "human_reading_list"]
    pending = [row for row in ordered_rows if row["disposition"] == "pending"]
    discard = [row for row in ordered_rows if row["disposition"] == "discard"]

    priority_counts = summary["priority_counts"]
    disposition_counts = summary["disposition_counts"]
    temperature_counts = summary["temperature_window_counts"]
    oa_counts = summary["oa_fulltext_reachable_counts"]
    epsilon_counts = summary["epsilon_clue_kind_counts"]

    lines: list[str] = []
    lines.append("# AL Round 3 \u5468\u672b\u7f13\u51b2\u652f\u7ebf\uff1a37 \u6761 OA \u7ebf\u7d22\u7684\u6807\u9898/\u6458\u8981\u7ea7\u5206\u6d41")
    lines.append("")
    lines.append(
        f"- \u751f\u6210\u65f6\u95f4\uff1a`{summary['generated_at']}`\uff08\u8fd0\u884c\u6a21\u5f0f `{summary['run_mode']}`\uff0c\u8017\u65f6 {summary['elapsed_seconds']} s\uff09"
    )
    lines.append(
        f"- \u8f93\u5165\uff1a`{summary['inputs']['leads']}`\uff08Week 11 \u7559\u4e0b\u7684 37 \u6761 OA \u7ebf\u7d22\uff09"
    )
    lines.append(
        f"- \u4ea7\u7269\uff1a`{summary['outputs']['csv']}`\u3001`{summary['outputs']['summary_json']}`"
    )
    lines.append(f"- \u811a\u672c\uff1a`{summary['outputs']['script']}`")
    lines.append(
        f"- \u6821\u9a8c\uff1a`verification_passed = {str(summary['verification_passed']).lower()}`"
        f"\uff08{sum(1 for c in summary['verification']['checks'] if c['passed'])}/{len(summary['verification']['checks'])} \u9879\u81ea\u68c0\u901a\u8fc7\uff09"
    )
    lines.append("")
    lines.append(
        "**\u4e00\u53e5\u8bdd\u7ed3\u8bba\uff1a37 \u6761\u91cc {} \u6761\u8fdb\u4eba\u5de5\u9605\u8bfb\u6e05\u5355\uff08P0={} / P1={}\uff09\uff0c"
        "{} \u6761\u5f85\u5b9a\uff0c{} \u6761\u4e22\u5f03\uff1b\u5176\u4e2d\u6807\u9898/\u6458\u8981\u5c42\u9762\u771f\u6b63\u7ed9\u51fa \u03b5 \u6570\u503c\u7ebf\u7d22\u7684\u53ea\u6709 {} \u6761\uff0c"
        "\u660e\u786e\u8986\u76d6 253\u2013333 K \u7684\u6709 {} \u6761\u3002**".format(
            len(reading),
            priority_counts.get("P0", 0),
            priority_counts.get("P1", 0),
            len(pending),
            len(discard),
            summary["epsilon_numeric_clue_count"],
            temperature_counts.get("true", 0),
        )
    )
    lines.append("")

    # 1. method
    lines.append("## 1. \u65b9\u6cd5\u4e0e\u53e3\u5f84")
    lines.append("")
    lines.append(
        "\u672c\u652f\u7ebf**\u53ea\u505a\u6807\u9898/\u6458\u8981\u7ea7\u5224\u65ad**\uff1a\u4e0d\u8bfb\u5168\u6587\u3001\u4e0d\u4e0b\u8f7d\u53d7\u9650\u5168\u6587\u3002\u6bcf\u6761\u7ebf\u7d22\u8d70\u56db\u6b65\uff1a"
    )
    lines.append("")
    lines.append(
        "1. **\u5316\u5408\u7269/\u4f53\u7cfb**\uff1a\u6807\u9898 + \u6458\u8981\u91cc\u7684\u540d\u79f0\u5339\u914d Week 11 \u624b\u5de5\u7ef4\u62a4\u7684 name/alias -> SMILES \u8868"
        "\uff08\u672c\u811a\u672c\u53e6\u8865 3 \u4e2a\u4efb\u52a1\u70b9\u540d\u7684\u76ee\u6807\u5316\u5408\u7269\uff09\uff0c\u7528 RDKit \u7b97 InChIKey\uff1b"
        "\u6307\u4e0d\u51fa\u5355\u4e00\u5206\u5b50\u7684\uff08\u6cdb\u6307 glyme\u3001\u805a\u5408\u7269\u3001\u76d0\u3001\u54c1\u724c\u540d\uff09\u8bb0\u4e3a unresolved\uff0c\u4e0d\u731c\u3002"
    )
    lines.append(
        "2. **\u03b5 \u7ebf\u7d22**\uff1a\u5728\u6807\u9898+\u6458\u8981\u91cc\u627e\u300c\u4ecb\u7535\u63aa\u8f9e + \u5408\u7406\u6570\u503c\u300d\u540c\u53e5\u7684\u53e5\u5b50\uff0c\u9010\u5b57\u4fdd\u7559\uff1b\u53ea\u6709\u65b9\u6cd5\u8bba\u63aa\u8f9e\u6ca1\u6570\u503c\u7684\u8bb0\u4e3a\u300c\u4ec5\u63aa\u8f9e\u300d\u3002"
    )
    lines.append(
        "3. **\u6e29\u5ea6\u7a97\u53e3**\uff1a\u53ea\u8ba4\u5e26\u5355\u4f4d\u7684\u663e\u5f0f\u6e29\u5ea6\uff08K/\u00b0C\uff09\u3002\u4e0e 253\u2013333 K \u76f8\u4ea4 -> `true`\uff1b"
        "\u663e\u5f0f\u6e29\u5ea6\u5168\u90e8\u5728\u7a97\u5916 -> `false`\uff1b\u53ea\u5199 room temperature \u6216\u5b8c\u5168\u6ca1\u63d0 -> `unknown`\uff08\u4e0d\u505a 298 K \u6362\u7b97\uff09\u3002"
    )
    lines.append(
        "4. **OA \u5168\u6587\u662f\u5426\u53ef\u5f97**\uff1a\u7528 Unpaywall \u7684 `is_oa` + `best_oa_location` \u590d\u6838\uff0c\u518d\u5bf9\u8be5 OA \u94fe\u63a5\u53d1\u4e00\u6b21"
        "\u2264 8 KB \u7684\u8303\u56f4 GET\uff0c\u53ea\u8bb0\u5f55 HTTP \u72b6\u6001\u7801\u3001Content-Type\u3001\u5b57\u8282\u6570\u3001"
        "\u662f\u5426\u4e3a\u673a\u5668\u4eba\u6821\u9a8c\u9875\u3001\u4ee5\u53ca\u662f\u5426\u53ea\u662f\u4e00\u4e2a < 20 KB \u7684 HTML \u843d\u5730\u9875\uff1b**\u54cd\u5e94\u4f53\u4e0d\u4fdd\u7559**\u3002"
    )
    lines.append("")
    lines.append(
        "- **数值过滤**：ε 数值必须通过「不是化学式里的数字（G4、LiClO4）、不是配比（EC:EMC 3:7）、不是电压/单位（4.3 V）」这一关，"
        "否则「介电常数」字样会顺手把分子式里的数字算成 ε。"
    )
    lines.append(
        "- **温度过滤**：整句在讲 superheat／温差的句子被整体丢弃，低于 60 K 的 K 值也不算绝对温度 —— "
        "「28 K 过热度」不会被当成 28 K 的实测温度。"
    )
    lines.append("")
    lines.append("**\u4f18\u5148\u7ea7\u68af\u5b50**\uff08\u53ef\u5ba1\u8ba1\uff1a\u5206\u91cf\u4e4b\u548c = `priority_score`\uff09")
    lines.append("")
    lines.append("| \u5206\u91cf | \u53d6\u503c |")
    lines.append("|---|---|")
    lines.append("| score_target | core \u76ee\u6807=3\uff1bcore \u65cf\u672a\u5b9a\u4f4d=2\uff1b\u76f8\u90bb\u7535\u6c60\u6eb6\u5242=1\uff1b\u975e\u76ee\u6807=0 |")
    lines.append("| score_epsilon | \u6570\u503c\u7ebf\u7d22=3\uff1b\u4ec5\u63aa\u8f9e=1\uff1b\u65e0=0 |")
    lines.append("| score_temperature | \u8986\u76d6=True 2\uff1bunknown=0\uff1b\u5728\u5916=-1 |")
    lines.append("| score_oa | 2xx \u4e14\u975e\u6821\u9a8c\u9875=2\uff1b\u672a\u77e5=1\uff1b\u4e0d\u53ef\u5f97=0 |")
    lines.append("")
    lines.append(
        "- `P0` = core \u76ee\u6807 \u4e14 \u03b5 \u6570\u503c\u7ebf\u7d22 \u4e14 \u603b\u5206 \u2265 8\uff1b`P1` = \u603b\u5206 \u2265 5 \u4e14\u5e26\u76ee\u6807\u65cf\uff1b`P2` = \u603b\u5206 \u2265 2\uff1b\u5176\u4f59 `P3`\u3002"
    )
    lines.append(
        "- \u4e24\u4e2a\u5426\u51b3\uff1a\u547d\u4e2d Week 11 \u566a\u58f0\u89c4\u5219\uff1b\u6216\u300c\u65e2\u4e0d\u662f\u76ee\u6807/\u76f8\u90bb\u6eb6\u5242\u65cf\u3001\u4e5f\u6ca1\u6709 \u03b5 \u7ebf\u7d22\u300d\u3002\u5426\u51b3\u4f1a\u628a\u6700\u7ec8\u4f18\u5148\u7ea7\u538b\u5230 `P3`\uff0c\u5206\u6570\u5217\u4ecd\u4fdd\u7559\u539f\u59cb\u5206\u91cf\u4f9b\u590d\u6838\u3002"
    )
    lines.append(
        "- \u5206\u6d41\uff1a`P0/P1 -> \u8fdb\u4eba\u5de5\u9605\u8bfb\u6e05\u5355`\uff1b`P2 -> \u5f85\u5b9a`\uff1b`P3 -> \u4e22\u5f03`\u3002"
    )
    lines.append("")
    lines.append(
        "**\u5408\u89c4**\uff1a\u53d7\u9650\u503c\u4e0e\u53d7\u9650\u5168\u6587\u53ea\u4f5c\u4e3a\u7ebf\u7d22\uff0c\u6c38\u4e0d\u8fdb\u53ef\u5206\u53d1\u6570\u636e\u96c6\uff1b\u62a5\u544a\u4e0e\u4ea7\u7269\u53ea\u8bb0 DOI / \u6807\u9898 / OA \u72b6\u6001 / \u6807\u9898\u6458\u8981\u7247\u6bb5\u3002"
        "\u672c\u6b21\u8fd0\u884c\u5171\u53d1\u51fa {} \u6b21\u8bf7\u6c42\uff08\u4e0a\u9650 {}\uff09\uff0c\u8be6\u89c1 summary JSON \u7684 `api` \u6bb5\u3002".format(
            summary["api"]["requests_used"], summary["api"]["request_limit"]
        )
    )
    lines.append("")

    # 2. stats
    lines.append("## 2. \u6c47\u603b\u7edf\u8ba1")
    lines.append("")
    lines.append("| \u7ef4\u5ea6 | \u8ba1\u6570 |")
    lines.append("|---|---|")
    lines.append(
        "| \u603b\u7ebf\u7d22 | {} |".format(summary["lead_count"])
    )
    for key in ("P0", "P1", "P2", "P3"):
        lines.append(f"| \u4f18\u5148\u7ea7 {key} | {priority_counts.get(key, 0)} |")
    lines.append(
        "| \u5206\u6d41\uff1a\u8fdb\u4eba\u5de5\u9605\u8bfb\u6e05\u5355 | {} |".format(
            disposition_counts.get("human_reading_list", 0)
        )
    )
    lines.append(
        "| \u5206\u6d41\uff1a\u5f85\u5b9a | {} |".format(disposition_counts.get("pending", 0))
    )
    lines.append(
        "| \u5206\u6d41\uff1a\u4e22\u5f03 | {} |".format(disposition_counts.get("discard", 0))
    )
    lines.append(
        "| \u03b5 \u6570\u503c\u7ebf\u7d22\uff08\u6807\u9898/\u6458\u8981\uff09 | {} |".format(
            summary["epsilon_numeric_clue_count"]
        )
    )
    lines.append(
        "| \u03b5 \u4ec5\u63aa\u8f9e\u3001\u65e0\u6570\u503c | {} |".format(
            epsilon_counts.get("wording_only", 0)
        )
    )
    lines.append(
        "| \u5b8c\u5168\u65e0 \u03b5 \u7ebf\u7d22 | {} |".format(epsilon_counts.get("none", 0))
    )
    lines.append(
        "| \u6e29\u7a97\u8986\u76d6=true | {} |".format(temperature_counts.get("true", 0))
    )
    lines.append(
        "| \u6e29\u7a97\u5728\u5916=false | {} |".format(temperature_counts.get("false", 0))
    )
    lines.append(
        "| \u6e29\u7a97 unknown | {} |".format(temperature_counts.get("unknown", 0))
    )
    lines.append(
        "| OA \u5168\u6587\u53ef\u5f97=true | {} |".format(oa_counts.get("true", 0))
    )
    lines.append(
        "| OA \u5168\u6587\u4e0d\u53ef\u5f97=false | {} |".format(oa_counts.get("false", 0))
    )
    lines.append(
        "| OA \u5168\u6587\u672a\u77e5 | {} |".format(oa_counts.get("unknown", 0))
    )
    lines.append(
        "| \u6458\u8981\u6210\u529f\u8bfb\u5230 | {} |".format(
            summary["abstract_read_counts"].get("true", 0)
        )
    )
    lines.append(
        "| \u6458\u8981\u672a\u8bfb\u5230 | {} |".format(
            summary["abstract_read_counts"].get("false", 0)
        )
    )
    lines.append(
        "| \u5316\u5408\u7269\u5b8c\u6574\u6307\u8ba4 | {} |".format(
            summary["compound_resolution_counts"].get("resolved", 0)
        )
    )
    lines.append(
        "| \u5316\u5408\u7269\u672a\u89e3\u6790 | {} |".format(
            summary["compound_resolution_counts"].get("unresolved", 0)
        )
    )
    lines.append("")
    lines.append("API \u8bf7\u6c42\uff1a")
    lines.append("")
    lines.append("| \u7c7b\u578b | \u6b21\u6570 |")
    lines.append("|---|---|")
    for kind, count in sorted(summary["api"]["requests_by_kind"].items()):
        lines.append(f"| {kind} | {count} |")
    lines.append(f"| \u5408\u8ba1 | {summary['api']['requests_used']} |")
    lines.append("")
    lines.append(
        "\u54cd\u5e94\u72b6\u6001\u7801\u5206\u5e03\uff1a`{}`".format(summary["api"]["responses_by_status"])
    )
    lines.append("")    # 3. per-lead table
    lines.append("## 3. \u9010\u6761\u5206\u7ea7\u8868\uff0837 \u6761\uff0c\u6309\u4f18\u5148\u7ea7\u6392\u5e8f\uff09")
    lines.append("")
    lines.extend(_priority_table(ordered_rows))
    lines.append("")
    lines.append(
        "\u6ce8\uff1a`\u76ee\u6807\u7c7b` \u91cc\u7684 core \u65cf = glyme / \u4e8c\u8148 / \u78fa\u783a / \u6c1f\u4ee3\u919a\uff1b"
        "\u76f8\u90bb = \u78b3\u9178\u916f\u4e0e\u916f / \u9187\u919a\uff1b\u975e\u76ee\u6807 = \u6c34\u3001\u9187\u3001\u6c1f\u4ee3\u70f7\u3001\u4f20\u70ed\u6d41\u4f53\u7b49\u3002"
        "`OA \u5168\u6587` \u5217\u62ec\u53f7\u91cc\u662f\u5b9e\u6d4b\u5230\u7684\u7ad9\u70b9 HTTP \u72b6\u6001\u7801\u3002"
    )
    lines.append("")

    # 4. reading list
    lines.append(f"## 4. \u8fdb\u4eba\u5de5\u9605\u8bfb\u6e05\u5355\uff08{len(reading)} \u6761\uff09")
    lines.append("")
    if reading:
        lines.append("| DOI | \u5316\u5408\u7269/\u4f53\u7cfb | \u4f18\u5148\u7ea7 | \u5206\u6570 | OA \u72b6\u6001 | \u5206\u6d41\u7406\u7531 |")
        lines.append("|---|---|---|---|---|---|")
        for row in reading:
            lines.append(
                "| `{}` | {} | {} | {} | is_oa={} / oa_status={} / probe={} ({} B{}) | {} |".format(
                    _md_cell(row["doi"]),
                    _md_cell(_short(row["compound_names"] or "unresolved", 40)),
                    row["priority"],
                    row["priority_score"],
                    row["unpaywall_is_oa"] or "unknown",
                    row["unpaywall_oa_status"] or "-",
                    row["oa_probe_http_status"] or "not probed",
                    row["oa_probe_bytes_read"] or "0",
                    "\uff0c\u843d\u5730\u9875" if row["oa_probe_looks_like_landing_page"] == "true" else "",
                    _md_cell(row["rationale"]),
                )
            )
        lines.append("")
        lines.append("### 4.1 \u9010\u5b57\u8bc1\u636e\uff08\u6807\u9898/\u6458\u8981\u7ea7\uff09")
        lines.append("")
        lines.extend(_evidence_table(reading))
    else:
        lines.append("\u672c\u8f6e\u6ca1\u6709\u4efb\u4f55\u7ebf\u7d22\u8fbe\u5230 P0/P1\u3002")
    lines.append("")

    # 5. pending
    lines.append(f"## 5. \u5f85\u5b9a\uff08{len(pending)} \u6761\uff09")
    lines.append("")
    if pending:
        lines.append("| DOI | \u5316\u5408\u7269/\u4f53\u7cfb | \u76ee\u6807\u7c7b | \u4f18\u5148\u7ea7 | \u5206\u6570 | \u5206\u6d41\u7406\u7531 |")
        lines.append("|---|---|---|---|---|---|")
        for row in pending:
            lines.append(
                "| `{}` | {} | {} | {} | {} | {} |".format(
                    _md_cell(row["doi"]),
                    _md_cell(_short(row["compound_names"] or "unresolved", 40)),
                    TARGET_CLASS_LABEL.get(row["target_class"], row["target_class"]),
                    row["priority"],
                    row["priority_score"],
                    _md_cell(row["rationale"]),
                )
            )
    else:
        lines.append("\u65e0\u3002")
    lines.append("")

    # 6. discard
    lines.append(f"## 6. \u4e22\u5f03\uff08{len(discard)} \u6761\uff09")
    lines.append("")
    if discard:
        lines.append("| DOI | \u6807\u9898 | \u4f18\u5148\u7ea7 | \u5206\u6570 | \u5206\u6d41\u7406\u7531 |")
        lines.append("|---|---|---|---|---|")
        for row in discard:
            lines.append(
                "| `{}` | {} | {} | {} | {} |".format(
                    _md_cell(row["doi"]),
                    _md_cell(_short(row["title"], 62)),
                    row["priority"],
                    row["priority_score"],
                    _md_cell(row["rationale"]),
                )
            )
    else:
        lines.append("\u65e0\u3002")
    lines.append("")

    # 7. honest boundaries
    lines.append("## 7. \u8bda\u5b9e\u8fb9\u754c\u4e0e\u6ca1\u8bfb\u5230\u7684\u5185\u5bb9")
    lines.append("")
    for item in summary["limitations"]:
        lines.append(f"- {item}")
    lines.append("")
    unread = summary["unread_abstracts"]
    lines.append(f"### 7.1 \u6458\u8981\u672a\u8bfb\u5230\u7684\u6761\u76ee\uff08{len(unread)} \u6761\uff09")
    lines.append("")
    if unread:
        lines.append("| DOI | \u539f\u56e0 |")
        lines.append("|---|---|")
        for item in unread:
            lines.append(f"| `{_md_cell(item['doi'])}` | {_md_cell(item['reason'])} |")
    else:
        lines.append("\u5168\u90e8 37 \u6761\u90fd\u8bfb\u5230\u4e86\u6458\u8981\u3002")
    lines.append("")
    failures = summary["api"]["failures"]
    lines.append("### 7.2 API \u5931\u8d25\uff08{} \u6761\uff0c\u5c55\u793a\u524d 60\uff09".format(summary["api"]["failure_count"]))
    lines.append("")
    if failures:
        lines.append("| \u7c7b\u578b | URL | \u72b6\u6001\u7801 | \u9519\u8bef |")
        lines.append("|---|---|---|---|")
        for item in failures:
            lines.append(
                "| {} | {} | {} | {} |".format(
                    item["kind"],
                    _md_cell(_short(item["url"], 90)),
                    "" if item["status"] is None else item["status"],
                    _md_cell(_short(item["error"] or "", 90)),
                )
            )
    else:
        lines.append("\u65e0 API \u5931\u8d25\u3002")
    lines.append("")

    # 8. reproduction
    lines.append("## 8. \u590d\u73b0")
    lines.append("")
    lines.append("```")
    lines.append(r".\.venv\Scripts\python.exe probes\al_round3_oa_triage.py --offline   # \u96f6\u8bf7\u6c42\uff0c\u53ea\u9a8c\u5206\u6790/\u5206\u7ea7\u94fe\u8def")
    lines.append(r".\.venv\Scripts\python.exe probes\al_round3_oa_triage.py             # \u771f\u5b9e\u8054\u7f51\uff0cOpenAlex + Unpaywall + \u53ef\u9009 Crossref")
    lines.append("```")
    lines.append("")
    lines.append(
        "\u79bb\u7ebf\u6a21\u5f0f\u4e0d\u53d1\u4efb\u4f55\u8bf7\u6c42\uff1a\u5206\u6790\u5217\u7167\u7b97\uff0c\u53ea\u662f\u5404\u4e2a API \u5217\u5199\u6210 `offline` / `unknown`\uff0c"
        "\u4e0d\u4f1a\u7f16\u9020\u6458\u8981\u3001\u4e5f\u4e0d\u4f1a\u7f16\u9020 OA \u72b6\u6001\u3002"
    )
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Pipeline and CLI.
# ---------------------------------------------------------------------------


def load_leads(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def resolve_leads_path(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit)
    if DEFAULT_LEADS.exists():
        return DEFAULT_LEADS
    return FALLBACK_LEADS


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=False) + "\n"
    path.write_text(text, encoding="utf-8", newline="\n")


def run_pipeline(
    *,
    leads_path: Path,
    csv_path: Path,
    json_path: Path,
    report_path: Path,
    offline: bool = False,
    sleep_seconds: float = DEFAULT_SLEEP_SECONDS,
    request_limit: int = DEFAULT_REQUEST_LIMIT,
    mailto: str = DEFAULT_MAILTO,
    limit: int | None = None,
    sleeper: Callable[[float], None] = time.sleep,
    transport: Callable[..., HttpResult] | None = None,
) -> dict[str, Any]:
    started = time.monotonic()
    reference = load_reference_module()
    library = build_compound_library(reference)
    alias_map = build_alias_map(reference)
    smiles = smiles_by_name(reference)

    leads = load_leads(leads_path)
    if limit is not None:
        leads = leads[:limit]

    budget = RequestBudget(request_limit)
    throttle = Throttle(0.0 if offline else sleep_seconds, sleeper)
    context = TriageContext(
        reference=reference,
        library=library,
        alias_map=alias_map,
        smiles=smiles,
        budget=budget,
        throttle=throttle,
        mailto=mailto,
        offline=offline,
        transport=transport,
    )

    rows = [triage_lead(lead, context) for lead in leads]
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    write_csv(csv_path, rows)

    elapsed = time.monotonic() - started
    summary = build_summary(
        rows=rows,
        leads=leads,
        budget=budget,
        offline=offline,
        leads_path=leads_path,
        csv_path=csv_path,
        json_path=json_path,
        report_path=report_path,
        elapsed_seconds=elapsed,
        check_report=False,
    )
    report_path.write_text(render_report(summary, rows), encoding="utf-8", newline="\n")

    summary["verification"] = verify_outputs(
        rows=rows,
        leads=leads,
        csv_path=csv_path,
        json_path=json_path,
        report_path=report_path,
        budget=budget,
        check_report=True,
    )
    summary["verification_passed"] = summary["verification"]["verification_passed"]
    summary["elapsed_seconds"] = round(time.monotonic() - started, 2)
    report_path.write_text(render_report(summary, rows), encoding="utf-8", newline="\n")
    write_json(json_path, summary)
    return summary


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--leads", default=None, help="Week 11 candidate CSV")
    parser.add_argument("--csv-output", default=str(DEFAULT_CSV_OUTPUT))
    parser.add_argument("--json-output", default=str(DEFAULT_JSON_OUTPUT))
    parser.add_argument("--report-output", default=str(DEFAULT_REPORT_OUTPUT))
    parser.add_argument("--offline", action="store_true", help="do not issue any HTTP request")
    parser.add_argument("--sleep", type=float, default=DEFAULT_SLEEP_SECONDS)
    parser.add_argument("--request-limit", type=int, default=DEFAULT_REQUEST_LIMIT)
    parser.add_argument("--mailto", default=DEFAULT_MAILTO)
    parser.add_argument("--limit", type=int, default=None, help="debug: only the first N leads")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    args = parse_args(argv)
    summary = run_pipeline(
        leads_path=resolve_leads_path(args.leads),
        csv_path=Path(args.csv_output),
        json_path=Path(args.json_output),
        report_path=Path(args.report_output),
        offline=args.offline,
        sleep_seconds=args.sleep,
        request_limit=args.request_limit,
        mailto=args.mailto,
        limit=args.limit,
    )
    printable = {
        "run_mode": summary["run_mode"],
        "lead_count": summary["lead_count"],
        "priority_counts": summary["priority_counts"],
        "disposition_counts": summary["disposition_counts"],
        "epsilon_numeric_clue_count": summary["epsilon_numeric_clue_count"],
        "temperature_window_counts": summary["temperature_window_counts"],
        "oa_fulltext_reachable_counts": summary["oa_fulltext_reachable_counts"],
        "api_requests_used": summary["api"]["requests_used"],
        "api_requests_by_kind": summary["api"]["requests_by_kind"],
        "verification_passed": summary["verification_passed"],
    }
    print(json.dumps(printable, ensure_ascii=False, indent=2))
    return 0 if summary["verification_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())