"""AL Round-3 acquisition candidates from the W13 open-access sweep (v1.x W13).

Round-6 of the G1+ sweep produced 37 open-access *leads* for temperature-resolved
static permittivity, but read no number out of any of them.  The v1.x lever is
now known to be compound coverage rather than temperature coverage, so the job
here is to turn those leads into an actionable acquisition list:

1. **Which compounds is the paper about?**  Compound names are matched against a
   curated name/alias -> SMILES table, and the InChIKey is computed locally with
   RDKit.  A name that is not a single identifiable molecule (a polymer, a
   protein, a brand name, a generic "glyme", a salt, a class noun) is recorded as
   unresolved with the reason.  Nothing is guessed.
2. **Is the full text genuinely reachable?**  The Open Access location is fetched
   with a hard per-document byte cap, a hard total byte cap and a hard request
   budget, and the HTTP status, content type, final URL and byte count are
   recorded.  A 200 that carries a bot check or a landing page is *not* a full
   text and is classified as blocked, not as reachable.
3. **Are there actually permittivity-with-temperature numbers?**  If the full
   text *is* reachable it is parsed and searched for lines that carry both a
   permittivity cue and an explicit temperature (with a K or degree-Celsius
   unit).  Those lines are stored with page provenance.  A value is only ever a
   number that was actually seen in extracted text; when nothing can be read the
   row says value_not_read and why.

The HTTP layer is injected, so every pure function (name resolution, noise
classification, disposition rules, snippet extraction, payload shaping) is
unit-testable offline with canned fixtures.

Outputs:
- data/processed/al_round3_candidates.csv
- probes/al_round3_summary.json
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
import time
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import lru_cache
from html import unescape as html_unescape
from pathlib import Path
from typing import Any

import requests

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_INPUT = REPOSITORY_ROOT / "data" / "processed" / "openalex_oa_candidates.csv"
DEFAULT_ROSTER = REPOSITORY_ROOT / "data" / "dielectric_v03.csv"
DEFAULT_OBSERVATIONS = REPOSITORY_ROOT / "data" / "processed" / "dielectric_observations_v11.csv"
DEFAULT_OUTPUT = REPOSITORY_ROOT / "data" / "processed" / "al_round3_candidates.csv"
DEFAULT_SUMMARY = REPOSITORY_ROOT / "probes" / "al_round3_summary.json"

USER_AGENT = "electrolyte-ml-research/1.0 (AL round-3 acquisition list; mailto:codex@local)"
HTTP_TIMEOUT_SECONDS = 60
DEFAULT_SLEEP_SECONDS = 1.0
DEFAULT_REQUEST_LIMIT = 90
DEFAULT_PUBCHEM_REQUEST_LIMIT = 30
DEFAULT_MAX_BYTES_PER_DOC = 12_000_000
DEFAULT_TOTAL_BYTE_BUDGET = 200_000_000
BACKOFF_SECONDS = (5.0, 15.0)
MAX_BACKOFF_SECONDS = 45.0

# HTML smaller than this is a landing page, an error page or a bot check rather
# than a full text.  The threshold is deliberately conservative: a real HTML
# article body is an order of magnitude larger.
HTML_FULLTEXT_MIN_CHARS = 60_000
# How many characters of an HTML body are inspected for bot-check markers.
BOT_CHECK_WINDOW = 6000

PUBCHEM_INCHIKEY_URL = "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/inchikey"

# Lines are stored verbatim, so how many of them are written per lead is capped
# to keep the CSV readable.  The cap is recorded in the summary.
MAX_EVIDENCE_LINES = 5
# A permittivity number is only accepted when it sits this close (characters) to
# the permittivity wording.  This narrows the window rather than closing it, so
# every extracted line is stored verbatim next to the number for human review.
CUE_PROXIMITY_CHARS = 40
# Plausible static relative permittivity range for a molecular solvent.
MIN_PLAUSIBLE_EPSILON = 1.0
MAX_PLAUSIBLE_EPSILON = 500.0

OUTPUT_COLUMNS: tuple[str, ...] = (
    "doi",
    "title",
    "publication_year",
    "query_label",
    "oa_url",
    "oa_host_type",
    "oa_version",
    "license",
    "disposition",
    "value_status",
    "epsilon_values_read",
    "value_not_read_reason",
    "noise_rules",
    "title_compounds",
    "unresolved_names",
    "n_compounds_resolved",
    "roster_status",
    "compounds_new",
    "in_roster",
    "in_observations_v11",
    "fetch_attempted",
    "fetch_skip_reason",
    "http_status",
    "content_type",
    "final_url",
    "bytes_fetched",
    "byte_cap_hit",
    "text_extractor",
    "text_chars",
    "permittivity_context_lines",
    "pubchem_crosscheck",
    "epsilon_evidence",
    "fetch_error",
)


# ---------------------------------------------------------------------------
# curated compound table
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CompoundEntry:
    """One identifiable solvent, with the aliases that name it in titles."""

    name: str
    smiles: str


# Hand-curated name -> structure table.  Every entry is a single, unambiguous
# molecule that a title can name directly.  Ambiguous names ("glyme" without a
# chain-length prefix, a brand such as "Novec" on its own, salt anions, polymers,
# proteins) are deliberately absent and are handled by UNRESOLVED_PATTERNS.
COMPOUND_LIBRARY: tuple[CompoundEntry, ...] = (
    CompoundEntry("1,2-dimethoxyethane", "COCCOC"),
    CompoundEntry("diglyme", "COCCOCCOC"),
    CompoundEntry("triglyme", "COCCOCCOCCOC"),
    CompoundEntry("tetraglyme", "COCCOCCOCCOCCOC"),
    CompoundEntry("1,2-dimethoxypropane", "COCC(C)OC"),
    CompoundEntry("succinonitrile", "N#CCCC#N"),
    CompoundEntry("glutaronitrile", "N#CCCCC#N"),
    CompoundEntry("adiponitrile", "N#CCCCCC#N"),
    CompoundEntry("malononitrile", "N#CCC#N"),
    CompoundEntry("ethylene carbonate", "O=C1OCCO1"),
    CompoundEntry("propylene carbonate", "CC1COC(=O)O1"),
    CompoundEntry("ethyl methyl carbonate", "CCOC(=O)OC"),
    CompoundEntry("dimethyl carbonate", "COC(=O)OC"),
    CompoundEntry("diethyl carbonate", "CCOC(=O)OCC"),
    CompoundEntry("1-butanol", "CCCCO"),
    CompoundEntry("water", "O"),
    CompoundEntry("ethane-1,2-diol", "OCCO"),
    CompoundEntry("tripropylene glycol", "CC(O)COCC(C)OCC(C)O"),
    CompoundEntry("2,2,2-trifluoroethanol", "OCC(F)(F)F"),
    CompoundEntry("hexafluoroisopropanol", "OC(C(F)(F)F)C(F)(F)F"),
    CompoundEntry("methoxy-nonafluorobutane", "COC(F)(F)C(F)(F)C(F)(F)C(F)(F)F"),
    CompoundEntry("ethoxy-nonafluorobutane", "CCOC(F)(F)C(F)(F)C(F)(F)C(F)(F)F"),
    CompoundEntry("decafluoropentane", "FC(F)(F)C(F)(F)C(F)C(F)C(F)(F)F"),
    CompoundEntry("perfluorohexane", "FC(F)(F)C(F)(F)C(F)(F)C(F)(F)C(F)(F)C(F)(F)F"),
)

# Extra title spellings that map onto a library entry.  Kept separate from the
# canonical name so the CSV always reports the same name for a given structure.
COMPOUND_ALIASES: Mapping[str, tuple[str, ...]] = {
    "1,2-dimethoxyethane": (
        "1,2:dimethoxyethane",
        "dimethoxyethane",
        "monoglyme",
        "ethylene glycol dimethyl ether",
    ),
    "diglyme": ("2,5,8-trioxanonane", "diethylene glycol dimethyl ether"),
    "triglyme": ("2,5,8,11-tetraoxadodecane",),
    "tetraglyme": ("2,5,8,11,14-pentaoxapentadecane",),
    "1,2-dimethoxypropane": ("dimethoxypropane",),
    "succinonitrile": ("butanedinitrile",),
    "glutaronitrile": ("pentanedinitrile",),
    "adiponitrile": ("hexanedinitrile",),
    "malononitrile": ("propanedinitrile",),
    "1-butanol": ("butanol", "n-butanol"),
    "ethane-1,2-diol": ("ethylene glycol",),
    "2,2,2-trifluoroethanol": ("trifluoroethanol",),
    "methoxy-nonafluorobutane": (
        "methyl nonafluorobutyl ether",
        "hfe-7100",
        "novec 7100",
        "novec-7100",
    ),
    "ethoxy-nonafluorobutane": (
        "ethyl nonafluorobutyl ether",
        "hfe-7200",
        "novec 7200",
    ),
    "decafluoropentane": ("novec 649", "novec-649"),
    "perfluorohexane": ("fc-72",),
}

# Title fragments that name something which is *not* a single identifiable
# solvent molecule.  Recording them keeps "we found no compound" honest instead
# of looking like an empty title.
UNRESOLVED_PATTERNS: tuple[tuple[str, str], ...] = (
    ("glyme", "generic glyme without a chain-length prefix; oligomer length unnamed"),
    ("pvdf", "polymer (PVDF-HFP), not a single solvent molecule"),
    ("trifluoromethylation", "unnamed trifluoromethylated adiponitrile derivative"),
    ("dnapl", "non-specific chlorinated-solvent mixture; no single compound named"),
    ("synaptotagmin", "protein, not a solvent"),
    ("mscs", "membrane protein channel, not a solvent"),
    ("polymer photocatalyst", "polymer, not a molecular solvent"),
    ("self-rewetting fluid", "fluid not specified"),
    ("dielectric liquid", "fluid not specified"),
    ("plastic crystal", "material class, no compound named"),
    ("molecular triad", "not a solvent"),
    ("polymer electrolyte", "composite solid polymer electrolyte, not a pure solvent"),
    ("ionic liquid", "ionic liquid family, no single compound named"),
)

# Title-only evidence for "this paper is not about the static permittivity of a
# solvent as a function of temperature".  Each rule is a literal substring of a
# title, so the classification is auditable.
NOISE_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "pool_boiling_heat_transfer",
        (
            "pool boiling",
            "nucleate boiling",
            "boiling enhancement",
            "boiling heat transfer",
            "immersion cooling",
            "heat transfer",
        ),
    ),
    ("geophysics_dnapl", ("dnapl",)),
    ("polymer_photocatalyst", ("photocatalyst", "sacrificial hydrogen")),
    (
        "biophysics_peptide_or_protein",
        (
            "peptide",
            "protein",
            "mechanosensitive",
            "synaptotagmin",
            "subunit interaction",
        ),
    ),
)

# Content that is a bot check rather than a document.
BOT_CHECK_MARKERS: tuple[str, ...] = (
    "just a moment",
    "cf-browser-verification",
    "cloudflare",
    "enable javascript",
    "verify you are human",
    "attention required",
    "access denied",
    "403 forbidden",
    "checking your browser",
)

CONTEXT_CUE = re.compile(
    r"dielectric\s+constant|dielectric\s+permittivity|relative\s+permittivity"
    r"|static\s+permittivity|permittivity|dielectric\s+relaxation"
    r"|dielectric\s+spectroscop|\bepsilon\b|[\u03b5\u03f5]",
    re.IGNORECASE,
)
VALUE_CUE = re.compile(
    r"dielectric\s+constant|dielectric\s+permittivity|relative\s+permittivity"
    r"|static\s+permittivity|\bepsilon\b|[\u03b5\u03f5]",
    re.IGNORECASE,
)
TEMPERATURE_TOKEN = re.compile(
    r"\d{1,4}(?:\.\d+)?\s*(?:K\b|[\u00b0]\s*C|[\u2103]|degrees?\s*C\b|deg\s*C\b)",
    re.IGNORECASE,
)
# A table names its unit in the header, so the caption window may hold "T / K"
# rather than a full "298.15 K" token on every row.
TEMPERATURE_UNIT = re.compile(
    r"T\s*/\s*K|\bK\b|[\u00b0]\s*C|[\u2103]|degrees?\s*C\b|deg\s*C\b",
    re.IGNORECASE,
)
NUMBER_TOKEN = re.compile(r"[-+]?\d+(?:\.\d+)?")
NON_ALNUM = re.compile(r"[^a-z0-9]+")
SCRIPT_TAG = re.compile(r"<(script|style)\b.*?</\1>", re.IGNORECASE | re.DOTALL)
ANY_TAG = re.compile(r"<[^>]+>")

GET_DISPOSITIONS: tuple[str, ...] = (
    "value_read",
    "table_candidate_needs_review",
    "fulltext_no_value",
    "no_oa_url",
    "skipped_noise_prefilter",
    "skipped_budget",
    "not_attempted_offline",
    "blocked_fetch_error",
    "blocked_bot_check",
    "blocked_html_landing",
    "blocked_pdf_unparsed",
    "blocked_unexpected_content_type",
)


# ---------------------------------------------------------------------------
# pure helpers
# ---------------------------------------------------------------------------


def normalize_title(value: str) -> str:
    """Lower-case a title and squeeze it to single-spaced alphanumeric tokens."""

    return NON_ALNUM.sub(" ", value.lower()).strip()


def resolve_inchikey(smiles: str) -> str | None:
    """Compute the standard InChIKey for a SMILES string, or None if unparsable."""

    from rdkit import Chem

    molecule = Chem.MolFromSmiles(smiles)
    if molecule is None:
        return None
    return str(Chem.MolToInchiKey(molecule))


def molecular_formula(smiles: str) -> str | None:
    """Return the Hill formula for a SMILES string, or None if unparsable."""

    from rdkit import Chem
    from rdkit.Chem import rdMolDescriptors

    molecule = Chem.MolFromSmiles(smiles)
    if molecule is None:
        return None
    return str(rdMolDescriptors.CalcMolFormula(molecule))


def aliases_for(entry: CompoundEntry) -> tuple[str, ...]:
    """All title spellings for one library entry, longest first."""

    spellings = set(COMPOUND_ALIASES.get(entry.name, ())) | {entry.name}
    return tuple(sorted(spellings, key=len, reverse=True))


@dataclass(frozen=True, slots=True)
class CompoundMatch:
    """A library entry named by a title, with the alias that matched."""

    name: str
    alias: str
    inchikey: str


def find_compound_mentions(
    title: str,
    library: Sequence[CompoundEntry] = COMPOUND_LIBRARY,
) -> tuple[CompoundMatch, ...]:
    """Return the library compounds named in a title.

    Matching is whole-token and longest-alias-first, and each matched span is
    blanked before shorter aliases are tried.  "tetraglyme" therefore matches
    tetraglyme and never a bare "glyme".  Each compound is reported at most once.
    """

    remaining = f" {title.lower()} "
    pairs: list[tuple[str, CompoundEntry]] = []
    for entry in library:
        for alias in aliases_for(entry):
            if len(alias) >= 4:
                pairs.append((alias, entry))
    pairs.sort(key=lambda pair: (-len(pair[0]), pair[0]))

    matches: list[CompoundMatch] = []
    seen: set[str] = set()
    for alias, entry in pairs:
        if entry.name in seen:
            continue
        pattern = re.compile(r"(?<![a-z0-9])" + re.escape(alias) + r"(?![a-z0-9])")
        found = pattern.search(remaining)
        if found is None:
            continue
        inchikey = resolve_inchikey(entry.smiles)
        if inchikey is None:
            continue
        matches.append(CompoundMatch(entry.name, alias, inchikey))
        seen.add(entry.name)
        start, end = found.span()
        remaining = remaining[:start] + " " * (end - start) + remaining[end:]
    return tuple(matches)


def find_unresolved_names(
    title: str,
    patterns: Sequence[tuple[str, str]] = UNRESOLVED_PATTERNS,
) -> tuple[tuple[str, str], ...]:
    """Return (fragment, reason) for title fragments that name no single compound."""

    haystack = normalize_title(title)
    hits: list[tuple[str, str]] = []
    for fragment, reason in patterns:
        needle = normalize_title(fragment)
        # Whole-token, but tolerant of a plural: "molecular triad" must fire on
        # "molecular triads", which a naive padded-substring test misses.
        pattern = re.compile(r"(?<![a-z0-9])" + re.escape(needle) + r"(?:s)?(?![a-z0-9])")
        if pattern.search(haystack):
            hits.append((fragment, reason))
    return tuple(hits)


def classify_noise(title: str) -> tuple[str, ...]:
    """Return the noise rules the title triggers, in declaration order."""

    haystack = normalize_title(title)
    hits = []
    for rule, needles in NOISE_RULES:
        if any(normalize_title(needle) in haystack for needle in needles):
            hits.append(rule)
    return tuple(hits)


def roster_status(keys: Sequence[str], roster_keys: frozenset[str]) -> str:
    """Summarise roster coverage for one lead's resolved compounds."""

    if not keys:
        return "unresolved"
    new = [key for key in keys if key not in roster_keys]
    if not new:
        return "all_in_roster"
    if len(new) == len(keys):
        return "all_new"
    return "some_new"


def plausible_permittivity_values(line: str) -> tuple[float, ...]:
    """Numbers on a line that could be a static relative permittivity.

    Temperature tokens are masked out first, so "298.15 K" never yields 298.15
    as a permittivity.  Only numbers close enough to a permittivity cue survive.
    """

    cue_spans = [match.span() for match in VALUE_CUE.finditer(line)]
    if not cue_spans:
        return ()
    masked = list(line)
    for match in TEMPERATURE_TOKEN.finditer(line):
        start, end = match.span()
        for index in range(start, end):
            masked[index] = " "
    values: list[float] = []
    for match in NUMBER_TOKEN.finditer("".join(masked)):
        value = float(match.group())
        if not (MIN_PLAUSIBLE_EPSILON <= value <= MAX_PLAUSIBLE_EPSILON):
            continue
        near = any(
            min(abs(match.start() - end), abs(match.end() - start)) <= CUE_PROXIMITY_CHARS
            for start, end in cue_spans
        )
        if near:
            values.append(value)
    return tuple(values)


@dataclass(frozen=True, slots=True)
class Evidence:
    """One extracted line, with its provenance."""

    kind: str  # "value" or "table"
    page: int
    line_number: int
    text: str
    temperature_tokens: tuple[str, ...]
    values: tuple[float, ...]

    def render(self) -> str:
        label = "value" if self.kind == "value" else "table"
        return f"p{self.page}L{self.line_number}[{label}] {self.text}"


@dataclass(frozen=True, slots=True)
class EvidenceReport:
    """Everything the extractor found, plus the counters the reasons need."""

    items: tuple[Evidence, ...]
    permittivity_context_lines: int
    lines_with_temperature: int

    @property
    def values(self) -> tuple[Evidence, ...]:
        return tuple(item for item in self.items if item.kind == "value")

    @property
    def tables(self) -> tuple[Evidence, ...]:
        return tuple(item for item in self.items if item.kind == "table")


def clean_lines(text: str) -> list[str]:
    """Split extracted text into whitespace-collapsed lines."""

    return [" ".join(line.split()) for line in text.splitlines()]


def extract_evidence(pages: Sequence[str], *, lookahead: int = 3) -> EvidenceReport:
    """Find permittivity-with-temperature evidence in already-extracted page text.

    A "value" line carries a permittivity cue, an explicit temperature with a
    unit, and a plausible permittivity number next to the cue.  A "table" line
    carries a permittivity cue and is followed, inside the lookahead window, by a
    temperature (a token, or a bare unit in a table header) and at least two
    numbers -- the shape of a table block a human still has to read.  Both are
    stored as extracted, with the whitespace collapsed but nothing else altered.
    """

    items: list[Evidence] = []
    context_lines = 0
    temperature_lines = 0
    for page_index, page_text in enumerate(pages, start=1):
        lines = clean_lines(page_text)
        for offset, line in enumerate(lines):
            if not line:
                continue
            if TEMPERATURE_TOKEN.search(line):
                temperature_lines += 1
            if not CONTEXT_CUE.search(line):
                continue
            context_lines += 1
            temperatures = tuple(match.group() for match in TEMPERATURE_TOKEN.finditer(line))
            values = plausible_permittivity_values(line)
            if temperatures and values:
                items.append(
                    Evidence("value", page_index, offset + 1, line, temperatures, values)
                )
                continue
            if temperatures:
                continue
            window = [line]
            for following in lines[offset + 1 :]:
                if not following:
                    continue
                window.append(following)
                if len(window) > lookahead:
                    break
            tail = " ".join(window[1:])
            window_text = " ".join(window)
            has_temperature = bool(
                TEMPERATURE_TOKEN.search(window_text) or TEMPERATURE_UNIT.search(window_text)
            )
            if has_temperature and len(NUMBER_TOKEN.findall(tail)) >= 2:
                items.append(
                    Evidence(
                        "table",
                        page_index,
                        offset + 1,
                        " // ".join(window),
                        tuple(
                            match.group()
                            for match in TEMPERATURE_TOKEN.finditer(window_text)
                        ),
                        (),
                    )
                )
    return EvidenceReport(tuple(items), context_lines, temperature_lines)


def value_outcome(report: EvidenceReport) -> tuple[str, str]:
    """Map an EvidenceReport to (value_status, reason)."""

    if report.values:
        return "value_read", ""
    if report.tables:
        return "table_candidate", "table_like_block_with_no_inline_value"
    if report.permittivity_context_lines == 0:
        return "value_not_read", "no_permittivity_wording_in_extracted_text"
    return (
        "value_not_read",
        "permittivity_wording_present_but_no_explicit_temperature_with_unit",
    )


def classify_disposition(
    *,
    oa_url: str,
    fetch_attempted: bool,
    skip_reason: str,
    fetch_error: str,
    fulltext: bool,
    block_reason: str,
    value_status: str,
) -> str:
    """Decide the single disposition for one lead, most informative first."""

    if not oa_url:
        return "no_oa_url"
    if fetch_attempted:
        if fetch_error:
            return "blocked_fetch_error"
        if not fulltext:
            return f"blocked_{block_reason}" if block_reason else "blocked_unexpected_content_type"
        if value_status == "value_read":
            return "value_read"
        if value_status == "table_candidate":
            return "table_candidate_needs_review"
        return "fulltext_no_value"
    if skip_reason == "noise_prefilter":
        return "skipped_noise_prefilter"
    if skip_reason == "offline":
        return "not_attempted_offline"
    return "skipped_budget"


def looks_like_pdf(body: bytes, content_type: str) -> bool:
    return body[:5] == b"%PDF-" or "pdf" in content_type.lower()


def is_bot_check(text: str) -> bool:
    window = text[:BOT_CHECK_WINDOW].lower()
    return any(marker in window for marker in BOT_CHECK_MARKERS)


def extract_html_text(body: bytes) -> str:
    """Best-effort visible text of an HTML document.  Never raises."""

    decoded = body.decode("utf-8", errors="replace")
    without_scripts = SCRIPT_TAG.sub(" ", decoded)
    with_breaks = ANY_TAG.sub("\n", without_scripts)
    return html_unescape(with_breaks)


def extract_pdf_pages(data: bytes) -> tuple[tuple[str, ...], str | None]:
    """Per-page text of a PDF, plus an error string.  Never raises."""

    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - pypdf is present in the venv
        return (), f"pypdf unavailable: {exc}"
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception as exc:  # noqa: BLE001 - reported, never raised
                return (), f"encrypted pdf: {exc}"
        pages = tuple((page.extract_text() or "") for page in reader.pages)
    except Exception as exc:  # noqa: BLE001 - a corrupt PDF must not kill the run
        return (), f"{type(exc).__name__}: {exc}"
    return pages, None


def classify_fulltext(body: bytes, content_type: str) -> tuple[bool, str, str, tuple[str, ...], str]:
    """Classify a fetched body.

    Returns (is_fulltext, block_reason, text_extractor, pages, error).  A PDF is a
    full text when it parses; an HTML body is a full text only when it is large
    enough to be an article and is not a bot check.
    """

    if not body:
        return False, "empty_body", "", (), "no bytes were fetched"
    if looks_like_pdf(body, content_type):
        pages, error = extract_pdf_pages(body)
        if error is not None:
            return False, "pdf_unparsed", "pypdf", (), error
        return True, "", "pypdf", pages, ""
    text = extract_html_text(body)
    if is_bot_check(text):
        return False, "bot_check", "", (), "response body is a bot check, not a document"
    if len(text) < HTML_FULLTEXT_MIN_CHARS:
        return (
            False,
            "html_landing",
            "",
            (),
            (
                f"html body of {len(text)} chars is below the "
                f"{HTML_FULLTEXT_MIN_CHARS}-char full-text threshold"
            ),
        )
    return True, "", "html", (text,), ""


def pubchem_formula_from_payload(payload: Any) -> tuple[int | None, str]:
    """Pull (cid, molecular_formula) out of a PubChem property payload."""

    if not isinstance(payload, Mapping):
        return None, ""
    table = payload.get("PropertyTable")
    if not isinstance(table, Mapping):
        return None, ""
    properties = table.get("Properties")
    if not isinstance(properties, Sequence) or not properties:
        return None, ""
    first = properties[0]
    if not isinstance(first, Mapping):
        return None, ""
    cid = first.get("CID")
    return (cid if isinstance(cid, int) else None), str(first.get("MolecularFormula") or "")


def pubchem_slug(inchikey: str) -> str:
    return inchikey.strip().upper()


def shape_crosscheck(inchikey: str, local_formula: str | None, payload: Any) -> str:
    """One key=outcome string describing the PubChem cross-check."""

    cid, formula = pubchem_formula_from_payload(payload)
    if cid is None:
        return f"{inchikey}=unavailable"
    if local_formula and formula and local_formula == formula:
        return f"{inchikey}=cid{cid}:formula_match"
    if formula:
        return f"{inchikey}=cid{cid}:formula_mismatch({formula})"
    return f"{inchikey}=cid{cid}:formula_unknown"


def load_key_column(path: Path, column: str = "inchikey") -> frozenset[str]:
    if not path.is_file():
        return frozenset()
    with path.open(encoding="utf-8", newline="") as handle:
        return frozenset(
            value for row in csv.DictReader(handle) if (value := (row.get(column) or "").strip())
        )


def load_leads(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


# ---------------------------------------------------------------------------
# transport
# ---------------------------------------------------------------------------


@dataclass
class HttpResponse:
    """A transport-level result; only default_http_get touches requests."""

    status_code: int
    final_url: str = ""
    content_type: str = ""
    body: bytes = b""
    truncated: bool = False
    error: str = ""
    retry_after: float | None = None


@dataclass
class RequestBudget:
    """Hard cap on outbound HTTP calls, with a per-status tally."""

    limit: int
    used: int = 0
    statuses: Counter[int] = field(default_factory=Counter)

    def spend(self) -> bool:
        if self.used >= self.limit:
            return False
        self.used += 1
        return True

    def record(self, status_code: int, *, key: int | None = None) -> None:
        self.statuses[status_code if key is None else key] += 1

    @property
    def remaining(self) -> int:
        return max(self.limit - self.used, 0)


HttpGet = Callable[[str], HttpResponse]
Transport = Callable[..., HttpResponse]
Sleeper = Callable[[float], None]


def parse_retry_after(value: Any) -> float | None:
    if value is None:
        return None
    try:
        seconds = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    return seconds if seconds >= 0 else None


def next_backoff_delay(response: HttpResponse, attempt: int, sleep_seconds: float) -> float:
    scheduled = BACKOFF_SECONDS[attempt] if attempt < len(BACKOFF_SECONDS) else sleep_seconds
    if response.retry_after is None:
        return scheduled
    return min(max(response.retry_after, scheduled), MAX_BACKOFF_SECONDS)


def default_http_get(url: str, *, max_bytes: int) -> HttpResponse:
    """Real transport, capped at max_bytes of body.  The only network touchpoint."""

    headers = {"User-Agent": USER_AGENT, "Accept": "*/*"}
    try:
        response = requests.get(
            url,
            headers=headers,
            timeout=HTTP_TIMEOUT_SECONDS,
            stream=True,
            allow_redirects=True,
        )
    except requests.RequestException as exc:
        return HttpResponse(0, "", "", b"", False, f"{type(exc).__name__}: {exc}")

    with response:
        status = response.status_code
        content_type = response.headers.get("Content-Type", "") or ""
        final_url = response.url
        if status != 200:
            snippet = next(response.iter_content(4096), b"")
            detail = snippet[:300].decode("utf-8", errors="replace")
            return HttpResponse(
                status,
                final_url,
                content_type,
                b"",
                False,
                f"HTTP {status}: {detail}",
                parse_retry_after(response.headers.get("Retry-After")),
            )
        chunks: list[bytes] = []
        total = 0
        truncated = False
        for chunk in response.iter_content(65536):
            if not chunk:
                continue
            remaining = max_bytes - total
            if len(chunk) >= remaining:
                chunks.append(chunk[:remaining])
                total += remaining
                truncated = True
                break
            chunks.append(chunk)
            total += len(chunk)
        return HttpResponse(status, final_url, content_type, b"".join(chunks), truncated, "")


def http_get_with_backoff(
    url: str,
    *,
    http_get: HttpGet,
    budget: RequestBudget,
    sleeper: Sleeper,
    sleep_seconds: float,
) -> HttpResponse:
    """One logical request: sleep politely, spend budget, retry 429 a few times."""

    sleeper(sleep_seconds)
    response = HttpResponse(0, error="request budget exhausted before the call")
    for attempt in range(len(BACKOFF_SECONDS) + 1):
        if not budget.spend():
            return HttpResponse(0, error="request budget exhausted")
        response = http_get(url)
        budget.record(response.status_code)
        if response.status_code != 429:
            return response
        if attempt < len(BACKOFF_SECONDS):
            sleeper(next_backoff_delay(response, attempt, sleep_seconds))
    return response


def missing_transport(_url: str) -> HttpResponse:  # pragma: no cover - guard only
    return HttpResponse(0, error="no HTTP transport configured")


# ---------------------------------------------------------------------------
# pipeline
# ---------------------------------------------------------------------------


@dataclass
class LeadOutcome:
    row: dict[str, Any]
    evidence: tuple[Evidence, ...]
    failures: tuple[dict[str, str], ...]


def process_lead(
    lead: Mapping[str, str],
    *,
    roster_keys: frozenset[str],
    observation_keys: frozenset[str],
    http_get: HttpGet | None,
    budget: RequestBudget,
    sleeper: Sleeper,
    sleep_seconds: float,
    fetch_noise: bool,
    offline: bool,
    crosscheck: bool,
    crosscheck_budget: RequestBudget | None,
    crosscheck_cache: dict[str, str] | None = None,
) -> LeadOutcome:
    """Resolve, fetch and inspect one lead.  Never raises on network trouble."""

    doi = (lead.get("doi") or "").strip()
    title = lead.get("title") or ""
    oa_url = (lead.get("oa_url") or "").strip()
    failures: list[dict[str, str]] = []

    matches = find_compound_mentions(title)
    unresolved = find_unresolved_names(title)
    keys = [match.inchikey for match in matches]
    noise = classify_noise(title)

    fetch_attempted = False
    skip_reason = ""
    response = HttpResponse(0, error="")
    fulltext = False
    block_reason = ""
    text_extractor = ""
    report = EvidenceReport((), 0, 0)
    text_chars = 0

    if not oa_url:
        skip_reason = "no_oa_url"
    elif noise and not fetch_noise:
        skip_reason = "noise_prefilter"
    elif offline:
        skip_reason = "offline"
    elif budget.remaining <= 0:
        skip_reason = "request_budget"
    else:
        fetch_attempted = True
        response = http_get_with_backoff(
            oa_url,
            http_get=http_get if http_get is not None else missing_transport,
            budget=budget,
            sleeper=sleeper,
            sleep_seconds=sleep_seconds,
        )
        if response.status_code != 200:
            failures.append(
                {
                    "doi": doi,
                    "stage": "fetch",
                    "detail": response.error or f"HTTP {response.status_code}",
                }
            )
        else:
            fulltext, block_reason, text_extractor, pages, parse_error = classify_fulltext(
                response.body, response.content_type
            )
            text_chars = sum(len(page) for page in pages)
            if parse_error and not fulltext:
                failures.append({"doi": doi, "stage": "parse", "detail": parse_error})
            if fulltext:
                report = extract_evidence(pages)

    value_status, reason = value_outcome(report) if fulltext else ("not_attempted", "")
    disposition = classify_disposition(
        oa_url=oa_url,
        fetch_attempted=fetch_attempted,
        skip_reason=skip_reason,
        fetch_error=response.error if response.status_code != 200 else "",
        fulltext=fulltext,
        block_reason=block_reason,
        value_status=value_status,
    )

    # An offline run must not touch the network at all, cross-checks included.
    crosscheck_text = ""
    if crosscheck and not offline and crosscheck_budget is not None and keys:
        crosscheck_text = run_crosschecks(
            keys,
            budget=crosscheck_budget,
            http_get=http_get,
            sleeper=sleeper,
            sleep_seconds=sleep_seconds,
            failures=failures,
            doi=doi,
            cache=crosscheck_cache,
        )

    row: dict[str, Any] = {
        "doi": doi,
        "title": title,
        "publication_year": lead.get("publication_year", ""),
        "query_label": lead.get("query_label", ""),
        "oa_url": oa_url,
        "oa_host_type": lead.get("oa_host_type", ""),
        "oa_version": lead.get("oa_version", ""),
        "license": lead.get("license", ""),
        "disposition": disposition,
        "value_status": value_status,
        "epsilon_values_read": len(report.values),
        "value_not_read_reason": reason,
        "noise_rules": "|".join(noise),
        "title_compounds": ";".join(f"{match.name}={match.inchikey}" for match in matches),
        "unresolved_names": ";".join(f"{name}:{why}" for name, why in unresolved),
        "n_compounds_resolved": len(matches),
        "roster_status": roster_status(keys, roster_keys),
        "compounds_new": ";".join(
            match.name for match in matches if match.inchikey not in roster_keys
        ),
        "in_roster": str(bool(keys) and all(key in roster_keys for key in keys)),
        "in_observations_v11": str(any(key in observation_keys for key in keys)),
        "fetch_attempted": str(fetch_attempted),
        "fetch_skip_reason": skip_reason,
        "http_status": response.status_code if fetch_attempted else "",
        "content_type": response.content_type if fetch_attempted else "",
        "final_url": response.final_url if fetch_attempted else "",
        "bytes_fetched": len(response.body) if fetch_attempted else "",
        "byte_cap_hit": str(response.truncated) if fetch_attempted else "",
        "text_extractor": text_extractor,
        "text_chars": text_chars,
        "permittivity_context_lines": report.permittivity_context_lines,
        "pubchem_crosscheck": crosscheck_text,
        "epsilon_evidence": " || ".join(
            item.render() for item in report.items[:MAX_EVIDENCE_LINES]
        ),
        "fetch_error": response.error if fetch_attempted else "",
    }
    return LeadOutcome(row, report.items, tuple(failures))


def run_crosschecks(
    keys: Sequence[str],
    *,
    budget: RequestBudget,
    http_get: HttpGet | None,
    sleeper: Sleeper,
    sleep_seconds: float,
    failures: list[dict[str, str]],
    doi: str,
    cache: dict[str, str] | None = None,
) -> str:
    """Cross-check locally computed InChIKeys against PubChem, budget permitting.

    Results are memoised in the cache, so a compound named by several leads is
    resolved against PubChem once rather than once per lead.
    """

    parts: list[str] = []
    for key in dict.fromkeys(keys):
        if cache is not None and key in cache:
            parts.append(cache[key])
            continue
        if budget.remaining <= 0:
            parts.append(f"{key}=budget_exhausted")
            failures.append(
                {"doi": doi, "stage": "pubchem", "detail": f"budget exhausted before {key}"}
            )
            continue
        url = f"{PUBCHEM_INCHIKEY_URL}/{pubchem_slug(key)}/property/MolecularFormula/JSON"
        outcome = fetch_crosscheck(
            key,
            url,
            budget=budget,
            http_get=http_get,
            sleeper=sleeper,
            sleep_seconds=sleep_seconds,
            failures=failures,
            doi=doi,
        )
        if cache is not None and not outcome.endswith(("budget_exhausted", "unavailable")):
            cache[key] = outcome
        parts.append(outcome)
    return ";".join(parts)


def fetch_crosscheck(
    key: str,
    url: str,
    *,
    budget: RequestBudget,
    http_get: HttpGet | None,
    sleeper: Sleeper,
    sleep_seconds: float,
    failures: list[dict[str, str]],
    doi: str,
) -> str:
    if http_get is None:
        return f"{key}=unavailable"
    sleeper(sleep_seconds)
    if not budget.spend():
        return f"{key}=budget_exhausted"
    response = http_get(url)
    budget.record(response.status_code, key=1000 + response.status_code)
    if response.status_code != 200:
        failures.append(
            {"doi": doi, "stage": "pubchem", "detail": f"{key}: HTTP {response.status_code}"}
        )
        return f"{key}=http{response.status_code}"
    try:
        payload = json.loads(response.body.decode("utf-8", errors="replace"))
    except ValueError as exc:
        failures.append({"doi": doi, "stage": "pubchem", "detail": f"{key}: {exc}"})
        return f"{key}=unparsable"
    return shape_crosscheck(key, local_formula_for(key), payload)


@lru_cache(maxsize=1)
def formula_by_key() -> dict[str, str]:
    formulas: dict[str, str] = {}
    for entry in COMPOUND_LIBRARY:
        key = resolve_inchikey(entry.smiles)
        formula = molecular_formula(entry.smiles)
        if key and formula:
            formulas[key] = formula
    return formulas


def local_formula_for(inchikey: str) -> str | None:
    return formula_by_key().get(inchikey)


def skipped_row(
    lead: Mapping[str, str],
    reason: str,
    roster_keys: frozenset[str],
    observation_keys: frozenset[str],
) -> dict[str, Any]:
    """A row for a lead that was never fetched."""

    title = lead.get("title") or ""
    matches = find_compound_mentions(title)
    keys = [match.inchikey for match in matches]
    return {
        "doi": lead.get("doi", ""),
        "title": title,
        "publication_year": lead.get("publication_year", ""),
        "query_label": lead.get("query_label", ""),
        "oa_url": lead.get("oa_url", ""),
        "oa_host_type": lead.get("oa_host_type", ""),
        "oa_version": lead.get("oa_version", ""),
        "license": lead.get("license", ""),
        "disposition": classify_disposition(
            oa_url=lead.get("oa_url", ""),
            fetch_attempted=False,
            skip_reason=reason,
            fetch_error="",
            fulltext=False,
            block_reason="",
            value_status="not_attempted",
        ),
        "value_status": "not_attempted",
        "epsilon_values_read": 0,
        "value_not_read_reason": reason,
        "noise_rules": "|".join(classify_noise(title)),
        "title_compounds": ";".join(f"{match.name}={match.inchikey}" for match in matches),
        "unresolved_names": ";".join(
            f"{name}:{why}" for name, why in find_unresolved_names(title)
        ),
        "n_compounds_resolved": len(matches),
        "roster_status": roster_status(keys, roster_keys),
        "compounds_new": ";".join(
            match.name for match in matches if match.inchikey not in roster_keys
        ),
        "in_roster": str(bool(keys) and all(key in roster_keys for key in keys)),
        "in_observations_v11": str(any(key in observation_keys for key in keys)),
        "fetch_attempted": "False",
        "fetch_skip_reason": reason,
        "http_status": "",
        "content_type": "",
        "final_url": "",
        "bytes_fetched": "",
        "byte_cap_hit": "",
        "text_extractor": "",
        "text_chars": "",
        "permittivity_context_lines": "",
        "pubchem_crosscheck": "",
        "epsilon_evidence": "",
        "fetch_error": "",
    }


def relative_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPOSITORY_ROOT).as_posix()
    except ValueError:
        return str(path)


def build_summary(
    *,
    rows: Sequence[Mapping[str, Any]],
    outcomes: Sequence[LeadOutcome],
    budget: RequestBudget,
    crosscheck_budget: RequestBudget,
    roster_keys: frozenset[str],
    observation_keys: frozenset[str],
    bytes_fetched: int,
    max_bytes_per_doc: int,
    total_byte_budget: int,
    paths: Mapping[str, Path],
    run_mode: Mapping[str, Any],
) -> dict[str, Any]:
    """Assemble the summary JSON from the finished rows."""

    failures = [failure for outcome in outcomes for failure in outcome.failures]
    disposition_counts = Counter(str(row["disposition"]) for row in rows)
    value_counts = Counter(str(row["value_status"]) for row in rows)
    roster_counts = Counter(str(row["roster_status"]) for row in rows)
    noise_rule_counts = Counter(
        rule for row in rows for rule in str(row["noise_rules"]).split("|") if rule
    )

    values_read = [
        {
            "doi": row["doi"],
            "title": row["title"],
            "title_compounds": row["title_compounds"],
            "evidence": [item.render() for item in outcome.evidence if item.kind == "value"],
        }
        for row, outcome in zip(rows, outcomes, strict=True)
        if any(item.kind == "value" for item in outcome.evidence)
    ]

    resolved: dict[str, str] = {}
    new: dict[str, str] = {}
    for row in rows:
        for pair in str(row["title_compounds"]).split(";"):
            if not pair:
                continue
            name, _, key = pair.partition("=")
            resolved[key] = name
            if key not in roster_keys:
                new[key] = name

    family_counts: dict[str, dict[str, int]] = {}
    for row in rows:
        entry = family_counts.setdefault(
            str(row["query_label"]), {"leads": 0, "noise": 0, "non_noise": 0}
        )
        entry["leads"] += 1
        entry["noise" if row["noise_rules"] else "non_noise"] += 1

    return {
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "run_mode": dict(run_mode),
        "inputs": {
            "candidates": relative_path(paths["input"]),
            "roster": relative_path(paths["roster"]),
            "observations": relative_path(paths["observations"]),
            "roster_keys": len(roster_keys),
            "observation_keys": len(observation_keys),
        },
        "budget": {
            "request_limit": budget.limit,
            "requests_used": budget.used,
            "requests_remaining": budget.remaining,
            "status_counts": {str(k): v for k, v in sorted(budget.statuses.items())},
            "pubchem_request_limit": crosscheck_budget.limit,
            "pubchem_requests_used": crosscheck_budget.used,
            "pubchem_status_counts": {
                str(k): v for k, v in sorted(crosscheck_budget.statuses.items())
            },
            "max_bytes_per_doc": max_bytes_per_doc,
            "total_byte_budget": total_byte_budget,
            "bytes_fetched": bytes_fetched,
        },
        "lead_count": len(rows),
        "disposition_counts": dict(sorted(disposition_counts.items())),
        "value_status_counts": dict(sorted(value_counts.items())),
        "roster_status_counts": dict(sorted(roster_counts.items())),
        "noise_lead_count": sum(1 for row in rows if row["noise_rules"]),
        "noise_rule_counts": dict(sorted(noise_rule_counts.items())),
        "family_counts": family_counts,
        "compounds": {
            "unique_resolved": len(resolved),
            "unique_in_roster": len(resolved) - len(new),
            "unique_new": len(new),
            "new": dict(sorted(new.items())),
            "all_resolved": dict(sorted(resolved.items())),
        },
        "values_read": values_read,
        "evidence_cap_per_lead": MAX_EVIDENCE_LINES,
        "failures": failures,
        "limitations": [
            (
                "Compound resolution comes from a hand-curated name/alias -> SMILES table, "
                "not from the paper text; a title that names a compound indirectly is "
                "unresolved."
            ),
            (
                "Permittivity numbers are extracted lines kept for human review, not validated "
                "measurements; each one carries its page and line number."
            ),
            (
                "A value is only claimed when a permittivity cue, an explicit temperature unit "
                "and a plausible number appear on the same extracted line."
            ),
            (
                "Evidence text has its whitespace collapsed, so it is verbatim in wording but "
                "not in layout."
            ),
            "PDF text extraction depends on pypdf; a truncated or scanned PDF yields no text.",
            (
                "HTML bodies below the full-text threshold are treated as landing pages, so a "
                "genuine short HTML article would be misclassified as blocked."
            ),
            (
                "Noise leads are classified from the title and are not fetched by default, so "
                "their reachability is deliberately unknown."
            ),
        ],
        "outputs": {
            "candidates_csv": relative_path(paths["output"]),
            "summary_json": relative_path(paths["summary"]),
        },
    }


def run_pipeline(
    *,
    input_path: Path = DEFAULT_INPUT,
    roster_path: Path = DEFAULT_ROSTER,
    observations_path: Path = DEFAULT_OBSERVATIONS,
    output_path: Path = DEFAULT_OUTPUT,
    summary_path: Path = DEFAULT_SUMMARY,
    http_get: Transport | None = None,
    sleeper: Sleeper | None = None,
    sleep_seconds: float = DEFAULT_SLEEP_SECONDS,
    request_limit: int = DEFAULT_REQUEST_LIMIT,
    crosscheck_limit: int = DEFAULT_PUBCHEM_REQUEST_LIMIT,
    max_bytes_per_doc: int = DEFAULT_MAX_BYTES_PER_DOC,
    total_byte_budget: int = DEFAULT_TOTAL_BYTE_BUDGET,
    fetch_noise: bool = False,
    offline: bool = False,
    crosscheck: bool = True,
    lead_limit: int | None = None,
) -> dict[str, Any]:
    """Run the whole round-3 pass and write both outputs."""

    transport: Transport = http_get if http_get is not None else default_http_get
    sleeper = sleeper if sleeper is not None else time.sleep
    leads = load_leads(input_path)
    if lead_limit is not None:
        leads = leads[:lead_limit]

    roster_keys = load_key_column(roster_path)
    observation_keys = load_key_column(observations_path)

    budget = RequestBudget(request_limit)
    crosscheck_budget = RequestBudget(crosscheck_limit)
    crosscheck_cache: dict[str, str] = {}

    def bound_get(url: str) -> HttpResponse:
        return transport(url, max_bytes=max_bytes_per_doc)

    outcomes: list[LeadOutcome] = []
    bytes_fetched = 0
    for lead in leads:
        if bytes_fetched >= total_byte_budget:
            outcomes.append(
                LeadOutcome(
                    skipped_row(lead, "byte_budget", roster_keys, observation_keys),
                    (),
                    (
                        {
                            "doi": lead.get("doi", ""),
                            "stage": "fetch",
                            "detail": f"total byte budget {total_byte_budget} exhausted",
                        },
                    ),
                )
            )
            continue
        outcome = process_lead(
            lead,
            roster_keys=roster_keys,
            observation_keys=observation_keys,
            http_get=bound_get,
            budget=budget,
            sleeper=sleeper,
            sleep_seconds=sleep_seconds,
            fetch_noise=fetch_noise,
            offline=offline,
            crosscheck=crosscheck and not offline,
            crosscheck_budget=crosscheck_budget,
            crosscheck_cache=crosscheck_cache,
        )
        bytes_fetched += int(outcome.row["bytes_fetched"] or 0)
        outcomes.append(outcome)

    rows = [outcome.row for outcome in outcomes]
    summary = build_summary(
        rows=rows,
        outcomes=outcomes,
        budget=budget,
        crosscheck_budget=crosscheck_budget,
        roster_keys=roster_keys,
        observation_keys=observation_keys,
        bytes_fetched=bytes_fetched,
        max_bytes_per_doc=max_bytes_per_doc,
        total_byte_budget=total_byte_budget,
        paths={
            "input": input_path,
            "roster": roster_path,
            "observations": observations_path,
            "output": output_path,
            "summary": summary_path,
        },
        run_mode={
            "offline": offline,
            "fetch_noise": fetch_noise,
            "crosscheck": crosscheck and not offline,
            "lead_limit": lead_limit,
            "sleep_seconds": sleep_seconds,
            "request_limit": request_limit,
        },
    )
    write_outputs(rows, summary, output_path=output_path, summary_path=summary_path)
    return summary


def write_outputs(
    rows: Sequence[Mapping[str, Any]],
    summary: Mapping[str, Any],
    *,
    output_path: Path,
    summary_path: Path,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(OUTPUT_COLUMNS), lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in OUTPUT_COLUMNS})
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def render_report(summary: Mapping[str, Any]) -> str:
    """Plain-text budget and disposition summary, printed at the end of a run."""

    budget = summary["budget"]
    lines = [
        f"leads processed: {summary['lead_count']}",
        (
            f"requests used: {budget['requests_used']}/{budget['request_limit']} "
            f"(pubchem {budget['pubchem_requests_used']}/{budget['pubchem_request_limit']})"
        ),
        (
            f"bytes fetched: {budget['bytes_fetched']} "
            f"(per-doc cap {budget['max_bytes_per_doc']}, "
            f"total cap {budget['total_byte_budget']})"
        ),
        f"http statuses: {budget['status_counts']}",
        "dispositions:",
    ]
    lines.extend(f"  {name}: {count}" for name, count in summary["disposition_counts"].items())
    lines.append(f"failures: {len(summary['failures'])}")
    return "\n".join(lines)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--roster", type=Path, default=DEFAULT_ROSTER)
    parser.add_argument("--observations", type=Path, default=DEFAULT_OBSERVATIONS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--request-limit", type=int, default=DEFAULT_REQUEST_LIMIT)
    parser.add_argument("--crosscheck-limit", type=int, default=DEFAULT_PUBCHEM_REQUEST_LIMIT)
    parser.add_argument("--max-bytes-per-doc", type=int, default=DEFAULT_MAX_BYTES_PER_DOC)
    parser.add_argument("--total-byte-budget", type=int, default=DEFAULT_TOTAL_BYTE_BUDGET)
    parser.add_argument("--sleep", type=float, default=DEFAULT_SLEEP_SECONDS)
    parser.add_argument("--lead-limit", type=int, default=None)
    parser.add_argument("--fetch-noise", action="store_true")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--no-crosscheck", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    summary = run_pipeline(
        input_path=args.input,
        roster_path=args.roster,
        observations_path=args.observations,
        output_path=args.output,
        summary_path=args.summary,
        sleep_seconds=args.sleep,
        request_limit=args.request_limit,
        crosscheck_limit=args.crosscheck_limit,
        max_bytes_per_doc=args.max_bytes_per_doc,
        total_byte_budget=args.total_byte_budget,
        fetch_noise=args.fetch_noise,
        offline=args.offline,
        crosscheck=not args.no_crosscheck,
        lead_limit=args.lead_limit,
    )
    print(render_report(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
