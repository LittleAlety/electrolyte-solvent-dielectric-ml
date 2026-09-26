"""DDBST (Dortmund Data Bank) free-layer probe: what does the free Online Search really give us?

Context
-------
The v1.x plan lists ``www.ddbst.com`` (Online Search) as source #6, "partly free",
to be used as a lead generator for pure-component relative permittivity versus
temperature.  The only DDBST row in ``data/processed/data_expansion_source_audit.csv``
audits the No-Data-Policy page, which is an access-constraint page, not a query
surface, so the free query surface itself had never been exercised.  Every other
external epsilon door closed already (NIST ThermoML online == local 103, set-identical;
ILThermo temperature series 1/109; OpenAlex/Unpaywall 37 leads and 0 epsilon values;
publisher hosting behind Cloudflare 403).

Four questions, each answered from bytes received in this run:

1. Does an Online Search / DDB Online free layer exist, and is it anonymous?
2. Does that free layer contain pure-component epsilon(T) for compounds we care about?
3. Is it machine readable (CSV/JSON export, stable URLs), or web-interaction only?
4. Net new compounds for v1.x: how many?

What the probe actually found (so the code below is readable)
-------------------------------------------------------------
The free layer is two surfaces behind one entry point:

- ``www.ddbst.com`` -- marketing/product pages plus a site search.  The vendor states
  in two places that the free search "does not (reveal|present) any data" and only
  allows mailing DDBST.  The free *calculation* service is a different thing and
  covers exactly five properties, none of them permittivity.
- ``ddbonline.ddbst.com/DDBSearch/onlineddboverview.exe`` -- the real application.
  It is plain HTTP, anonymous, and *intermittently* reachable from this environment:
  the first TCP connect is frequently dropped and a retry a second later succeeds, so
  every app call is retried against the same budget and the attempts are reported.

The application has no property query at all -- only ``ddbnumber``/``name``/``casn``/
``formula``/``smiles`` component lookups.  But two of its pages expose *coverage
metadata*, which is the part that matters for v1.x triage:

- ``?submit=Statistics`` gives, per data bank and per system size, the number of
  sets/points/components.  ``MDEC`` (Mixture Dielectric Constants) is listed there.
- ``?submit=DDBSystems&databank=MDEC`` gives the full system list, including the pure
  components that carry dielectric data, each with its data-set and data-point counts
  and a ``?submit=Details&systemcomplist=<DDB#>`` link.
- ``?submit=Details&systemcomplist=<DDB#>`` gives, for one component, a property table
  with Points / Sets / Temperature Range / state breakdown.  That is how "Dielectric
  Constant" becomes visible as e.g. water at 1569 points, 273 sets, 67-823 K, Liquid.

So the honest answer is: the free layer exposes *that* epsilon(T) exists, how many
points there are and over which temperature range, but **no values**.  The probe never
promotes a coverage count into a datum, and the read-value counters stay at zero.

Politeness
----------
Descriptive User-Agent, >=1 s between HTTP calls, ``429``/``Retry-After`` honoured once,
a hard request budget (default 60, retries included) that stops the run and is reported.

Outputs
-------
``probes/ddb_free_search_probe_summary.json``
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import socket
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from html import unescape
from pathlib import Path
from typing import Any

import requests

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SUMMARY_PATH = REPOSITORY_ROOT / "probes" / "ddb_free_search_probe_summary.json"
ROSTER_PATH = REPOSITORY_ROOT / "data" / "dielectric_v03.csv"

ORIGIN = "https://www.ddbst.com"
ONLINE_ORIGIN = "http://ddbonline.ddbst.com"
APP_PATH = "/DDBSearch/onlineddboverview.exe"
APP_URL = ONLINE_ORIGIN + APP_PATH
SITEMAP_INDEX_URL = "http://www.ddbst.com/DDBonlinesitemapindex.xml"

ROBOTS_URL = ORIGIN + "/robots.txt"
DDB_SEARCH_URL = ORIGIN + "/ddb-search.html"
ONLINE_URL = ORIGIN + "/online.html"
CALCULATION_URL = ORIGIN + "/calculation.html"
MIXTURE_DIELECTRIC_URL = ORIGIN + "/ddb-mdec.html"

USER_AGENT = "electrolyte-ml-research/1.0 (DDBST free-layer audit; polite, 1 req/s)"

DEFAULT_REQUEST_BUDGET = 60
DEFAULT_SLEEP_SECONDS = 1.0
DEFAULT_TIMEOUT_SECONDS = 15.0
CONNECT_PROBE_SECONDS = 8.0
APP_RETRY_ATTEMPTS = 6

# The compounds the v1.x plan names, i.e. the ones whose epsilon(T) we would want.
TARGET_COMPOUNDS: tuple[str, ...] = (
    "acetonitrile",
    "propylene carbonate",
    "dimethyl carbonate",
    "water",
    "ethylene carbonate",
)

# One representative from each sub-sitemap family advertised by robots.txt.
SUB_SITEMAP_SAMPLE: tuple[str, ...] = (
    "cassitemap0.xml.gz",
    "formulasitemap0.xml.gz",
    "pcpoverviewsitemap0.xml.gz",
    "pcpsitemap0.xml.gz",
)

DIELECTRIC_PROPERTY_NAME = "Dielectric Constant"
DIELECTRIC_BANK_CODE = "MDEC"

NO_DATA_RE = re.compile(r"does not (?:reveal|present) any data", re.IGNORECASE)
SUPPORTED_BANKS_RE = re.compile(r"supported data banks", re.IGNORECASE)
BANKS_STOP_RE = re.compile(
    r"^(terms and conditions|copyright|privacy statement|latest news)", re.IGNORECASE
)
FREE_CALC_ANCHOR_RE = re.compile(
    r"presents separate pages for each of the following properties", re.IGNORECASE
)
FREE_CALC_STOP_RE = re.compile(r"^(the parameters for the equations|important note)", re.IGNORECASE)
TERMS_FREE_RE = re.compile(r"freely available and no copyright", re.IGNORECASE)
ONLINE_APP_LINK_RE = re.compile(r'href="([^"]*onlineddboverview[^"]*)"', re.IGNORECASE)
SEARCH_HIT_RE = re.compile(r'<h3><a href="([^"]+)" title="([^"]*)"', re.IGNORECASE)
SEARCH_TOTAL_RE = re.compile(r"Results\s+\d+\s*-\s*\d+\s*of\s+(\d+)", re.IGNORECASE)
LOC_RE = re.compile(r"<loc>(.*?)</loc>", re.DOTALL)
LOGIN_MARKER_RE = re.compile(
    r"\b(log\s?in|sign\s?in|password|username|subscri(?:be|ption)|licen[cs]e key)\b",
    re.IGNORECASE,
)
PERMITTIVITY_RE = re.compile(r"dielectric|permittivity", re.IGNORECASE)

INPUT_RE = re.compile(r"(?is)<input[^>]*>")
OPTION_RE = re.compile(r'(?is)<option[^>]*value\s*=\s*"(\d+)\s+(\d+)"[^>]*>(.*?)</option>')
OPTION_LABEL_RE = re.compile(r"^\[(\d+)\]\s*(.*)$")
OPTION_COLUMN_RE = re.compile(r"\s{2,}")
COMPONENT_COUNT_RE = re.compile(r"(\d+)\s+Components?\s+found", re.IGNORECASE)
KEYWORDS_META_RE = re.compile(
    r'<meta\s+name="keywords"\s+content="(.*?)"\s*/?>', re.IGNORECASE | re.DOTALL
)
DETAILS_TITLE_RE = re.compile(r"<title>(.*?)\s*\|\s*Details\s*\|", re.IGNORECASE)
CAS_RE = re.compile(r"\b\d{2,7}-\d{2}-\d\b")
SYSTEMS_HEADER_RE = re.compile(
    r"(\d+)\s+systems\s+with\s+(\d+)\s+data\s+set/s\s+and\s+(\d+)\s+data\s+point/s",
    re.IGNORECASE,
)
SYSTEMS_TITLE_RE = re.compile(r"List of Systems for (.+?)</", re.IGNORECASE | re.DOTALL)
SETS_POINTS_RE = re.compile(
    r"(\d+)\s*sets\s*(\d+)\s*points\s*(\d+)\s*([A-Za-z]+)", re.IGNORECASE
)

EXPORT_MARKERS: tuple[str, ...] = (
    "csv",
    "json",
    "api",
    "export",
    "download",
    "webservice",
    "soap",
    "rest",
)
EXPORT_LINK_RE = re.compile(
    r'href="([^"]*\.(?:csv|tsv|json|xlsx?|zip)[^"]*)"', re.IGNORECASE
)


class BudgetExhausted(RuntimeError):
    """Raised when the request budget is spent."""


@dataclass(frozen=True)
class HttpResponse:
    """One HTTP attempt, successful or not."""

    url: str
    status: int | None
    body: str
    bytes_received: int
    seconds: float
    error: str | None = None
    note: str = ""

    @property
    def ok(self) -> bool:
        return self.error is None and self.status == 200

    def as_record(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "status": self.status,
            "bytes": self.bytes_received,
            "seconds": round(self.seconds, 2),
            "error": self.error,
            "note": self.note,
        }


@dataclass
class RequestBudget:
    """A hard cap on outbound HTTP requests, retries included."""

    limit: int = DEFAULT_REQUEST_BUDGET
    used: int = 0

    def consume(self, url: str) -> None:
        if self.used >= self.limit:
            raise BudgetExhausted(f"request budget of {self.limit} exhausted before {url}")
        self.used += 1

    @property
    def exhausted(self) -> bool:
        return self.used >= self.limit

    @property
    def remaining(self) -> int:
        return max(0, self.limit - self.used)


def strip_tags(fragment: str) -> str:
    return unescape(re.sub(r"(?s)<[^>]+>", " ", fragment)).replace("\xa0", " ")


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def html_to_text(html: str) -> str:
    """Strip tags/scripts and unescape entities, preserving line breaks."""
    text = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", "\n", text)
    return re.sub(r"[ \t]+", " ", unescape(text).replace("\xa0", " "))


def html_to_lines(html: str) -> list[str]:
    return [line.strip() for line in html_to_text(html).split("\n") if line.strip()]


def sentence_around(text: str, start: int, end: int) -> str:
    left = max(text.rfind(".", 0, start), text.rfind("\n", 0, start)) + 1
    right = text.find(".", end)
    right = len(text) if right == -1 else right + 1
    return clean(text[left:right])


def table_rows(html: str) -> list[list[str]]:
    """Tolerant ``<tr>`` -> cell texts splitter.

    DDBST emits malformed rows (``<td class="cellformat">1<td ...`` with the first
    cell never closed), so splitting on ``</td>`` silently mis-aligns every column.
    Splitting on the *opening* tag and cutting at the next tag boundary handles both
    the closed and the unclosed form.
    """
    rows: list[list[str]] = []
    for raw_row in re.findall(r"(?is)<tr[^>]*>(.*?)</tr>", html):
        cells: list[str] = []
        for chunk in re.split(r"(?i)<t[dh]\b[^>]*>", raw_row)[1:]:
            cut = re.split(r"(?i)</t[dh]>|<t[dh]\b|</tr>", chunk, maxsplit=1)[0]
            cells.append(clean(strip_tags(cut)))
        rows.append(cells)
    return rows


def find_no_data_statement(html: str) -> str | None:
    """The vendor's own sentence saying the free search reveals no data."""
    text = " ".join(html_to_lines(html))
    match = NO_DATA_RE.search(text)
    if match is None:
        return None
    return sentence_around(text, match.start(), match.end())


def extract_supported_banks(html: str) -> list[str]:
    """Data banks the free Online Search claims to cover."""
    lines = html_to_lines(html)
    start = None
    for index, line in enumerate(lines):
        if SUPPORTED_BANKS_RE.search(line):
            start = index
            break
    if start is None:
        return []
    banks: list[str] = []
    for line in lines[start + 1 :]:
        if BANKS_STOP_RE.search(line):
            break
        banks.append(line)
    return banks


def extract_free_calculator_properties(html: str) -> list[str]:
    """Properties offered by the free online *calculation* service.

    Two paths on purpose.  The primary one anchors on the intro sentence and reads the
    lines that follow until the parameters note -- that is the shape of today's page.
    The sentence is long enough that the publisher may wrap it in the source, in which
    case the per-line anchor misses entirely and the probe would report "no permittivity
    in the free calculator" from an empty list, which is exactly the kind of silent
    under-read that turns into a wrong conclusion.  So if the anchor exists in the
    collapsed text but no line carries it, the page's own ``<li>`` items are used.
    """
    lines = html_to_lines(html)
    start = None
    for index, line in enumerate(lines):
        if FREE_CALC_ANCHOR_RE.search(line):
            start = index
            break
    if start is not None:
        properties: list[str] = []
        for line in lines[start + 1 :]:
            if FREE_CALC_STOP_RE.search(line):
                break
            properties.append(line)
        if properties:
            return properties
    if FREE_CALC_ANCHOR_RE.search(clean(strip_tags(html))) is None:
        return []
    items = re.findall(r"(?is)<li[^>]*>(.*?)</li>", html)
    return [clean(strip_tags(item)) for item in items if clean(strip_tags(item))]


def extract_terms_statement(html: str) -> str | None:
    for line in html_to_lines(html):
        if TERMS_FREE_RE.search(line):
            return line
    return None


def find_online_app_link(html: str) -> str | None:
    match = ONLINE_APP_LINK_RE.search(html)
    return match.group(1) if match else None


def count_permittivity_mentions(html: str) -> int:
    return len(PERMITTIVITY_RE.findall(html))


def has_login_marker(html: str) -> bool:
    return LOGIN_MARKER_RE.search(html_to_text(html)) is not None


def find_export_markers(html: str) -> dict[str, dict[str, Any]]:
    """Raw census of machine-readable-handle tokens, with one context each.

    Kept as a census on purpose: the words appear in the site navigation
    ("Export Compliance"), so this is *not* by itself evidence of an export
    endpoint.  The verdict uses :func:`find_export_links` instead.
    """
    text = " ".join(html_to_lines(html)).lower()
    found: dict[str, dict[str, Any]] = {}
    for token in EXPORT_MARKERS:
        hits = list(re.finditer(rf"\b{re.escape(token)}\b", text))
        if not hits:
            continue
        first = hits[0]
        found[token] = {
            "count": len(hits),
            "first_context": text[max(0, first.start() - 90) : first.end() + 90].strip(),
        }
    return found


def find_export_links(html: str) -> list[str]:
    """Link targets that would actually be a bulk/structured export."""
    return sorted({unescape(link) for link in EXPORT_LINK_RE.findall(html)})


def parse_sitemap_locs(xml_text: str) -> list[str]:
    return [loc.strip() for loc in LOC_RE.findall(xml_text)]


def sitemap_family(name: str) -> str:
    return re.sub(r"\d+\.xml(?:\.gz)?$", "", name.split("/")[-1])


def classify_url(url: str) -> str:
    """Marketing page vs something that could carry per-compound records."""
    path = url.split("://", 1)[-1]
    path = path.split("/", 1)[1] if "/" in path else ""
    if not path:
        return "root"
    if re.search(r"\d", path):
        return "record_like"
    if path.endswith((".html", ".htm")):
        return "marketing_page"
    return "other"


def parse_search_hits(html: str) -> list[dict[str, str]]:
    return [{"url": url, "title": unescape(title)} for url, title in SEARCH_HIT_RE.findall(html)]


def parse_search_total(html: str) -> int | None:
    match = SEARCH_TOTAL_RE.search(html_to_text(html))
    return int(match.group(1)) if match else None


def parse_component_count(html: str) -> int | None:
    match = COMPONENT_COUNT_RE.search(strip_tags(html))
    return int(match.group(1)) if match else None


def split_option_label(raw_label: str) -> dict[str, str]:
    """Split one free-search result row into CAS / formula / name.

    The rows are monospace columns padded with runs of whitespace/``&nbsp;``:
    ``[174]   7732-18-5   H2O          Water``.  Splitting on single spaces
    mis-filed CAS-less multi-word names ("Tap water" became formula "Tap", name
    "water", which then made several distinct components collide on the name
    "water" and silently killed the exact match), so the split happens on the
    *padding runs* of the untouched label, and a missing CAS/formula column is
    detected by shape rather than by position.
    """
    spacing = unescape(raw_label).replace("\xa0", " ")
    spacing = re.sub(r"[\t\r\n]+", " ", spacing).strip()
    flat = clean(spacing)
    match = OPTION_LABEL_RE.match(flat)
    if match is None:
        return {"raw_label": flat, "cas": "", "formula": "", "name": flat}
    fields = [part for part in (clean(chunk) for chunk in OPTION_COLUMN_RE.split(spacing)) if part]
    if fields and re.fullmatch(r"\[\d+\]", fields[0]):
        fields = fields[1:]
    elif fields and re.match(r"^\[\d+\]\s", fields[0]):
        fields[0] = re.sub(r"^\[\d+\]\s*", "", fields[0])
    cas = fields.pop(0) if fields and CAS_RE.fullmatch(fields[0]) else ""
    formula = ""
    if len(fields) >= 2 and re.fullmatch(r"[A-Za-z0-9.*+()\[\]]+", fields[0]):
        formula = fields.pop(0)
    return {"raw_label": flat, "cas": cas, "formula": formula, "name": clean(" ".join(fields))}


def parse_component_options(html: str) -> list[dict[str, Any]]:
    """The component list the free search returns, one row per ``<option>``."""
    return [
        {
            "ddb_number": int(ddb_number),
            "systems": int(systems),
            **split_option_label(label),
        }
        for ddb_number, systems, label in OPTION_RE.findall(html)
    ]


def pick_exact_component(options: list[dict[str, Any]], name: str) -> dict[str, Any] | None:
    """Exact case-insensitive name match only.

    The free search is a substring match -- "acetonitrile" returns 316 rows including
    aminoacetonitrile and polyacrylonitrile-style names -- so a fuzzy pick would
    silently attach the wrong DDB number.  Anything short of an exact hit is reported
    as no match instead.
    """
    wanted = clean(name).casefold()
    exact = [option for option in options if str(option.get("name", "")).casefold() == wanted]
    return exact[0] if len(exact) == 1 else None


def extract_property_keywords(html: str) -> list[str]:
    match = KEYWORDS_META_RE.search(html)
    if match is None:
        return []
    return [clean(part) for part in unescape(match.group(1)).split(",") if clean(part)]


def parse_details_identity(html: str) -> dict[str, str]:
    """DDB#/name/CAS/formula header of a Details page."""
    title = DETAILS_TITLE_RE.search(html)
    identity: dict[str, str] = {"name": clean(title.group(1)) if title else ""}
    for cells in table_rows(html):
        if len(cells) >= 4 and cells[0].isdigit() and CAS_RE.fullmatch(cells[2] or ""):
            identity.update({"ddb_number": cells[0], "cas": cells[2], "formula": cells[3]})
            break
    cas = CAS_RE.search(strip_tags(html))
    identity["cas_anywhere"] = cas.group(0) if cas else ""
    return identity


def parse_pure_property_table(html: str) -> list[dict[str, Any]]:
    """The Details page property table: Points / Sets / T-range / state breakdown.

    Continuation rows carry only state + set count, so they are attached to the
    property opened by the last fully-populated row.
    """
    properties: list[dict[str, Any]] = []
    for cells in table_rows(html):
        if len(cells) < 4 or cells[0].lower() == "property":
            continue
        if cells[0]:
            properties.append(
                {
                    "property": cells[0],
                    "points": _as_int(cells[1]),
                    "sets": _as_int(cells[2]),
                    "temperature_range": cells[3],
                    "states": [],
                }
            )
            if len(cells) >= 6 and cells[4]:
                properties[-1]["states"].append(
                    {"state": cells[4], "sets": _as_int(cells[5])}
                )
            continue
        if properties and len(cells) >= 6 and cells[4]:
            properties[-1]["states"].append({"state": cells[4], "sets": _as_int(cells[5])})
    return properties


def _as_int(value: str) -> int | None:
    return int(value) if value.isdigit() else None


def find_property(properties: Sequence[dict[str, Any]], name: str) -> dict[str, Any] | None:
    wanted = clean(name).casefold()
    for entry in properties:
        if clean(str(entry["property"])).casefold() == wanted:
            return entry
    return None


def parse_statistics_table(html: str) -> list[dict[str, Any]]:
    """``?submit=Statistics``: sets/points/units per data bank and system size."""
    banks: list[dict[str, Any]] = []
    for cells in table_rows(html):
        if not cells or not re.fullmatch(r"[A-Z]{2,7}", cells[0]):
            continue
        columns = []
        for cell in cells[1:6]:
            match = SETS_POINTS_RE.search(cell)
            columns.append(
                {
                    "sets": int(match.group(1)) if match else None,
                    "points": int(match.group(2)) if match else None,
                    "unit_count": int(match.group(3)) if match else None,
                    "unit": match.group(4) if match else None,
                    "raw": cell or None,
                }
            )
        if not any(column["sets"] is not None for column in columns):
            continue
        banks.append({"code": cells[0], "columns": columns})
    return banks


def parse_systems_page(html: str) -> dict[str, Any]:
    """``?submit=DDBSystems``: the system list, split by system size."""
    header = SYSTEMS_HEADER_RE.search(html)
    title = SYSTEMS_TITLE_RE.search(html)
    sections: dict[str, list[dict[str, Any]]] = {}
    boundaries = [
        ("Pure Components", r'id="Pure@Components"'),
        ("Binary Mixtures", r'id="Binary@Mixtures"'),
        ("Ternary Mixtures", r'id="Ternary@Mixtures"'),
        ("Quaternary Mixtures", r'id="Quaternary@Mixtures"'),
        ("Quinary Mixtures", r'id="Quinary@Mixtures"'),
        ("Other Mixtures", r'id="Other@Mixtures"'),
    ]
    positions = []
    for label, pattern in boundaries:
        match = re.search(pattern, html)
        positions.append((label, match.start() if match else None))
    for index, (label, start) in enumerate(positions):
        if start is None:
            continue
        end = next(
            (pos for _, pos in positions[index + 1 :] if pos is not None), len(html)
        )
        rows: list[dict[str, Any]] = []
        for cells in table_rows(html[start:end]):
            if len(cells) < 5 or not cells[0].isdigit():
                continue
            raw_numbers = cells[1] or ""
            if not re.fullmatch(r"[\d,\s]+", raw_numbers):
                # binary and larger systems list one DDB# per component, "<br />"-joined
                continue
            ddb_numbers = ",".join(re.findall(r"\d+", raw_numbers))
            rows.append(
                {
                    "index": int(cells[0]),
                    "ddb_numbers": ddb_numbers,
                    "components": cells[2],
                    "data_sets": _as_int(cells[3]),
                    "data_points": _as_int(cells[4]),
                }
            )
        sections[label] = rows
    return {
        "title": clean(title.group(1)) if title else "",
        "system_count": int(header.group(1)) if header else None,
        "data_sets": int(header.group(2)) if header else None,
        "data_points": int(header.group(3)) if header else None,
        "sections": sections,
    }


def normalise_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.casefold())


def name_signature(value: str) -> str:
    """Order-insensitive character multiset of a name.

    DDB writes alcohols as "2-Butanol" while the frozen roster writes "butan-2-ol";
    the two differ only by where the locant sits, so a strict string join reports
    them as different compounds.  Sorting the alphanumeric characters collapses that
    difference while keeping genuine isomers apart ("1-butanol" vs "2-butanol" carry
    different digits).  It is a *heuristic*, not structure resolution: it is only
    applied to names with >= 6 alphanumerics, and matches are labelled as such.
    """
    return "".join(sorted(re.sub(r"[^a-z0-9]", "", value.casefold())))


def join_names(candidates: Sequence[str], roster_names: Sequence[str]) -> dict[str, Any]:
    """Two-tier name join, deliberately not dressed up as structure resolution."""
    roster = {normalise_name(name): name for name in roster_names}
    signatures: dict[str, list[str]] = {}
    for name in roster_names:
        signatures.setdefault(name_signature(name), []).append(name)

    matched, signature_matched, unmatched = [], [], []
    for candidate in candidates:
        key = normalise_name(candidate)
        if key in roster:
            matched.append({"candidate": candidate, "roster_name": roster[key]})
            continue
        signature = name_signature(candidate)
        hits = [name for name in signatures.get(signature, []) if len(signature) >= 6]
        if len(hits) == 1:
            signature_matched.append(
                {"candidate": candidate, "roster_name": hits[0], "signature": signature}
            )
            continue
        unmatched.append(candidate)
    return {
        "matched": matched,
        "matched_count": len(matched),
        "signature_matched": signature_matched,
        "signature_matched_count": len(signature_matched),
        "unmatched": unmatched,
        "unmatched_count": len(unmatched),
        "method": (
            "tier 1 is case/punctuation-insensitive name equality; tier 2 is an "
            "order-insensitive character-multiset signature that also collapses "
            "locant order (>= 6 alphanumerics). No CAS, SMILES or structure join was "
            "performed, so tier-2 matches and the unmatched list are both unverified."
        ),
    }
class ResponseCache:
    """On-disk memo of successful responses.

    The application host drops connections intermittently, so a probe run regularly
    ends with a few gaps.  Caching the responses that *did* arrive lets a re-run fill
    only the gaps instead of re-requesting the whole surface, which is both faster and
    politer.  Cache hits do not consume the request budget.
    """

    def __init__(self, directory: Path | str | None = None) -> None:
        self.directory = Path(directory) if directory else None

    def _entry(self, url: str, params: dict[str, str] | None) -> tuple[Path, str]:
        query = "&".join(f"{key}={value}" for key, value in sorted((params or {}).items()))
        key = url + ("?" + query if query else "")
        assert self.directory is not None
        return self.directory / (hashlib.sha256(key.encode("utf-8")).hexdigest() + ".json"), key

    def load(self, url: str, params: dict[str, str] | None) -> HttpResponse | None:
        if self.directory is None:
            return None
        entry, key = self._entry(url, params)
        if not entry.exists():
            return None
        try:
            payload = json.loads(entry.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return HttpResponse(
            url=key,
            status=payload.get("status"),
            body=payload.get("body", ""),
            bytes_received=int(payload.get("bytes") or 0),
            seconds=0.0,
        )

    def store(self, url: str, params: dict[str, str] | None, response: HttpResponse) -> None:
        if self.directory is None or not response.ok:
            return
        entry, key = self._entry(url, params)
        self.directory.mkdir(parents=True, exist_ok=True)
        with entry.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(
                json.dumps(
                    {"key": key, "status": response.status, "bytes": response.bytes_received,
                     "body": response.body},
                    ensure_ascii=False,
                )
            )


def _retry_after_seconds(response: Any) -> float:
    raw = response.headers.get("Retry-After")
    if raw is None:
        return 5.0
    try:
        return max(1.0, float(raw))
    except (TypeError, ValueError):
        return 5.0


def http_get(
    url: str,
    *,
    session: Any,
    budget: RequestBudget,
    params: dict[str, str] | None = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    note: str = "",
    retry_after_cap: float = 45.0,
) -> HttpResponse:
    """One polite GET with budget accounting and a single Retry-After retry."""
    budget.consume(url)
    display = url if not params else url + "?" + "&".join(f"{k}={v}" for k, v in params.items())
    started = time.time()
    for attempt in (1, 2):
        try:
            response = session.get(url, params=params, timeout=timeout)
        except Exception as exc:  # noqa: BLE001 - failures are data
            return HttpResponse(
                url=display,
                status=None,
                body="",
                bytes_received=0,
                seconds=time.time() - started,
                error=f"{type(exc).__name__}: {exc}",
                note=note,
            )
        if response.status_code == 429 and attempt == 1:
            time.sleep(min(_retry_after_seconds(response), retry_after_cap))
            continue
        return HttpResponse(
            url=display,
            status=response.status_code,
            body=response.text,
            bytes_received=len(response.content),
            seconds=time.time() - started,
            note=note,
        )
    raise AssertionError("unreachable")


def socket_probe(host: str, port: int, timeout: float = CONNECT_PROBE_SECONDS) -> dict[str, Any]:
    """DNS + raw TCP connect, so reachability is a connection fact."""
    record: dict[str, Any] = {"host": host, "port": port, "dns_ips": [], "connect": None}
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
        record["dns_ips"] = sorted({info[4][0] for info in infos})
    except Exception as exc:  # noqa: BLE001 - recorded verbatim
        record["connect"] = "dns_failure"
        record["error"] = f"{type(exc).__name__}: {exc}"
        return record
    started = time.time()
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect((host, port))
        record["connect"] = "ok"
    except TimeoutError:
        record["connect"] = "timeout"
    except Exception as exc:  # noqa: BLE001 - recorded verbatim
        record["connect"] = type(exc).__name__
        record["error"] = str(exc)
    finally:
        sock.close()
    record["seconds"] = round(time.time() - started, 2)
    return record


def load_roster_names(path: Path | None = None) -> list[str]:
    """Compound names of the frozen v1.0 roster, for a concrete denominator."""
    target = path or ROSTER_PATH
    if not target.exists():
        return []
    import csv

    with target.open(encoding="utf-8", newline="") as handle:
        return [row["name"] for row in csv.DictReader(handle) if row.get("name")]


def run_probe(
    *,
    budget: RequestBudget | None = None,
    session: Any | None = None,
    http_get_fn: Callable[..., HttpResponse] = http_get,
    sleep_seconds: float = DEFAULT_SLEEP_SECONDS,
    connect_probe_fn: Callable[[str, int, float], dict[str, Any]] = socket_probe,
    now: datetime | None = None,
    offline: bool = False,
    roster_names: Sequence[str] | None = None,
    cache_dir: Path | str | None = None,
) -> dict[str, Any]:
    """Run every phase and return the summary document."""
    budget = budget or RequestBudget()
    cache = ResponseCache(cache_dir)
    session = session if session is not None else requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    state = {"calls": 0, "cache_hits": 0}
    records: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    stopped_early: str | None = None
    pages: dict[str, HttpResponse] = {}
    connects: list[dict[str, Any]] = []
    sub_sitemaps: list[dict[str, Any]] = []
    sitemap_index: dict[str, Any] = {}
    app: dict[str, Any] = {}
    compound_attempts: list[dict[str, Any]] = []

    def call(url: str, note: str = "", params: dict[str, str] | None = None) -> HttpResponse:
        nonlocal stopped_early
        cached = cache.load(url, params)
        if cached is not None:
            state["cache_hits"] += 1
            records.append({**cached.as_record(), "note": note + " [cache hit]"})
            return cached
        if state["calls"] > 0 and sleep_seconds > 0:
            time.sleep(sleep_seconds)
        state["calls"] += 1
        try:
            response = http_get_fn(
                url,
                session=session,
                budget=budget,
                params=params,
                note=note,
            )
        except BudgetExhausted as exc:
            stopped_early = str(exc)
            return HttpResponse(
                url=url,
                status=None,
                body="",
                bytes_received=0,
                seconds=0.0,
                error="budget_exhausted",
                note=note,
            )
        records.append(response.as_record())
        if response.error is not None:
            failures.append({"url": response.url, "error": response.error})
        else:
            cache.store(url, params, response)
        return response

    def app_call(
        params: dict[str, str], note: str, attempts: int = APP_RETRY_ATTEMPTS
    ) -> tuple[HttpResponse, list[dict[str, Any]]]:
        """The app host drops the first connection often; retry inside the budget."""
        response = None
        tries: list[dict[str, Any]] = []
        for attempt in range(1, attempts + 1):
            response = call(APP_URL, f"{note} [attempt {attempt}]", params=params)
            tries.append(
                {"attempt": attempt, "status": response.status, "error": response.error}
            )
            if response.ok or budget.exhausted:
                break
        assert response is not None
        return response, tries

    if not offline:
        # ---- Phase A: the vendor's own description of the free layer ------------
        for key, url, note in (
            ("robots", ROBOTS_URL, "robots.txt names the sitemap index"),
            ("ddb_search", DDB_SEARCH_URL, "product page hosting the free app entry point"),
            ("online", ONLINE_URL, "Online Services overview of the free tier"),
            ("calculation", CALCULATION_URL, "free online calculation property list"),
            ("mixture_dielectric", MIXTURE_DIELECTRIC_URL, "dielectrics page found by site search"),
        ):
            pages[key] = call(url, note)

        # ---- Phase B: advertised free per-compound sitemap family --------------
        index_response = call(SITEMAP_INDEX_URL, "sub-sitemap index advertised by robots.txt")
        locs = parse_sitemap_locs(index_response.body) if index_response.body else []
        sitemap_index = {
            "url": SITEMAP_INDEX_URL,
            "status": index_response.status,
            "advertised_sub_sitemaps": len(locs),
            "families": sorted({sitemap_family(loc) for loc in locs}),
        }
        for name in SUB_SITEMAP_SAMPLE:
            url = SITEMAP_INDEX_URL.rsplit("/", 1)[0] + "/" + name
            response = call(url, f"sampled advertised sub-sitemap ({sitemap_family(name)})")
            sub_sitemaps.append(
                {
                    "url": url,
                    "family": sitemap_family(name),
                    "status": response.status,
                    "bytes": response.bytes_received,
                    "parseable_loc_count": (
                        len(parse_sitemap_locs(response.body)) if response.body else 0
                    ),
                    "error": response.error,
                }
            )

        # ---- Phase C: reachability of the free application host ----------------
        for port in (80, 443):
            connects.append(connect_probe_fn("ddbonline.ddbst.com", port, CONNECT_PROBE_SECONDS))
        entry, entry_tries = app_call({}, "free app entry point (GET, no parameters)")
        app["entry"] = {
            "url": entry.url,
            "status": entry.status,
            "bytes": entry.bytes_received,
            "error": entry.error,
            "attempts": entry_tries,
            "has_search_form": '<form method="post"' in entry.body,
            "search_item_fields": re.findall(r'name="(ddbnumber|name|casn|formula|smiles)"', entry.body),
            "permittivity_mentions": count_permittivity_mentions(entry.body),
            "login_marker": has_login_marker(entry.body),
        }

        # ---- Phase D: whole-corpus coverage statistics -------------------------
        stats, stats_tries = app_call({"submit": "Statistics"}, "overall statistics page")
        statistics_rows = parse_statistics_table(stats.body) if stats.body else []
        mdec_row = next(
            (row for row in statistics_rows if row["code"] == DIELECTRIC_BANK_CODE), None
        )
        app["statistics"] = {
            "url": stats.url,
            "status": stats.status,
            "bytes": stats.bytes_received,
            "error": stats.error,
            "attempts": stats_tries,
            "banks_listed": len(statistics_rows),
            "bank_codes": [row["code"] for row in statistics_rows],
            "dielectric_bank": mdec_row,
        }

        # ---- Phase E: the dielectric bank's system list ------------------------
        systems, systems_tries = app_call(
            {"submit": "DDBSystems", "databank": DIELECTRIC_BANK_CODE},
            f"{DIELECTRIC_BANK_CODE} system list",
        )
        systems_parsed = parse_systems_page(systems.body) if systems.body else {}
        pure_rows = (systems_parsed.get("sections") or {}).get("Pure Components", [])
        pure_names = [row["components"] for row in pure_rows if row.get("components")]
        app["systems"] = {
            "url": systems.url,
            "status": systems.status,
            "bytes": systems.bytes_received,
            "error": systems.error,
            "attempts": systems_tries,
            "title": systems_parsed.get("title"),
            "system_count": systems_parsed.get("system_count"),
            "data_sets": systems_parsed.get("data_sets"),
            "data_points": systems_parsed.get("data_points"),
            "section_sizes": {
                key: len(value) for key, value in (systems_parsed.get("sections") or {}).items()
            },
            "pure_component_count": len(pure_rows),
            "pure_component_sets_sum": sum(row["data_sets"] or 0 for row in pure_rows),
            "pure_component_points_sum": sum(row["data_points"] or 0 for row in pure_rows),
            "pure_components": pure_names,
        }

        # ---- Phase F: per-compound epsilon coverage for the compounds we want --
        for compound in TARGET_COMPOUNDS:
            search, search_tries = app_call(
                {"submit": "Search", "name": compound}, f"component search for {compound!r}"
            )
            options = parse_component_options(search.body) if search.body else []
            match = pick_exact_component(options, compound)
            attempt: dict[str, Any] = {
                "compound": compound,
                "search": {
                    "status": search.status,
                    "bytes": search.bytes_received,
                    "error": search.error,
                    "attempts": search_tries,
                    "reported_component_count": parse_component_count(search.body)
                    if search.body
                    else None,
                    "rows_parsed": len(options),
                    "exact_match": match,
                },
            }
            if match is not None:
                details, details_tries = app_call(
                    {"submit": "Details", "systemcomplist": str(match["ddb_number"])},
                    f"details page for {compound!r} (DDB#{match['ddb_number']})",
                )
                properties = parse_pure_property_table(details.body) if details.body else []
                dielectric = find_property(properties, DIELECTRIC_PROPERTY_NAME)
                attempt["details"] = {
                    "status": details.status,
                    "bytes": details.bytes_received,
                    "error": details.error,
                    "attempts": details_tries,
                    "identity": parse_details_identity(details.body) if details.body else {},
                    "property_count": len(properties),
                    "property_names": [entry["property"] for entry in properties],
                    "dielectric_row": dielectric,
                    "permittivity_mentions": count_permittivity_mentions(details.body)
                    if details.body
                    else 0,
                }
            else:
                attempt["details"] = {
                    "status": None,
                    "error": "no_exact_component_match",
                    "note": "the search returned no case-insensitive exact name match",
                }
            attempt["permittivity_values_returned"] = 0
            attempt["temperature_values_returned"] = 0
            compound_attempts.append(attempt)

    answers = build_answers(
        pages=pages,
        connects=connects,
        sub_sitemaps=sub_sitemaps,
        compound_attempts=compound_attempts,
        sitemap_index=sitemap_index,
        app=app,
        roster_names=list(roster_names) if roster_names is not None else load_roster_names(),
        records=records,
    )
    summary: dict[str, Any] = {
        "probe": "ddb_free_search_probe",
        "generated_at": (now or datetime.now(UTC)).isoformat(timespec="seconds"),
        "mode": "offline" if offline else "live",
        "target": {
            "vendor": "DDBST GmbH (Dortmund Data Bank)",
            "marketing_origin": ORIGIN,
            "online_search_origin": ONLINE_ORIGIN,
            "online_search_entry_point": APP_URL,
            "plan_slot": "source #6 in the v1.x data-source table ('partly free')",
        },
        "politeness": {
            "user_agent": USER_AGENT,
            "min_seconds_between_calls": sleep_seconds,
            "request_budget": budget.limit,
            "app_retry_attempts_per_call": APP_RETRY_ATTEMPTS,
        },
        "budget": {
            "limit": budget.limit,
            "used": budget.used,
            "remaining": budget.remaining,
            "exhausted": budget.exhausted,
            "stopped_early": stopped_early,
        },
        "cache": {
            "enabled": cache.directory is not None,
            "hits": state["cache_hits"],
            "new_requests": budget.used,
            "note": (
                "successful responses are memoised on disk; a re-run refills only the "
                "gaps. Cache hits are replayed from the memo and cost no request."
            ),
        },
        "counts": {
            "http_requests": len(records),
            "connection_probes": len([c for c in connects if c.get("port") in (80, 443)]),
            "errors": len(failures),
            "bytes_received": sum(int(record["bytes"] or 0) for record in records),
            "status_histogram": _histogram(records),
        },
        "requests": records,
        "connect_probes": connects,
        "sitemap_index": sitemap_index,
        "sub_sitemap_sample": sub_sitemaps,
        "application": app,
        "compound_attempts": compound_attempts,
        "answers": answers,
        "roster_rows": len(roster_names) if roster_names is not None else len(load_roster_names()),
        "failed_attempts": failures,
    }
    return summary


def _histogram(records: Sequence[dict[str, Any]]) -> dict[str, int]:
    histogram: dict[str, int] = {}
    for record in records:
        key = str(record["status"]) if record["error"] is None else f"error:{record['error']}"
        histogram[key] = histogram.get(key, 0) + 1
    return dict(sorted(histogram.items()))


def build_answers(
    *,
    pages: dict[str, HttpResponse],
    connects: list[dict[str, Any]],
    sub_sitemaps: list[dict[str, Any]],
    compound_attempts: list[dict[str, Any]],
    sitemap_index: dict[str, Any],
    app: dict[str, Any],
    roster_names: Sequence[str],
    records: Sequence[dict[str, Any]] = (),
) -> dict[str, Any]:
    """Turn raw responses into the four verdicts, keeping claim and proof apart."""
    search_page = pages.get("ddb_search")
    online_page = pages.get("online")
    calc_page = pages.get("calculation")
    dielectric_page = pages.get("mixture_dielectric")

    app_link = find_online_app_link(search_page.body) if search_page and search_page.body else None
    banks_search = (
        extract_supported_banks(search_page.body) if search_page and search_page.body else []
    )
    banks_online = extract_supported_banks(online_page.body) if online_page and online_page.body else []
    banks = banks_search or banks_online
    permittivity_in_banks = [bank for bank in banks if PERMITTIVITY_RE.search(bank)]
    no_data = []
    for key, page in (("online", online_page), ("ddb_search", search_page)):
        statement = find_no_data_statement(page.body) if page and page.body else None
        if statement:
            no_data.append({"page": key, "statement": statement})
    free_props = (
        extract_free_calculator_properties(calc_page.body) if calc_page and calc_page.body else []
    )
    free_props_hits = (
        count_permittivity_mentions(calc_page.body) if calc_page and calc_page.body else None
    )
    dielectric_page_mentions = (
        count_permittivity_mentions(dielectric_page.body)
        if dielectric_page and dielectric_page.body
        else None
    )
    login_markers = {
        key: has_login_marker(page.body) for key, page in pages.items() if page and page.body
    }
    export_markers: dict[str, Any] = {}
    export_links: list[str] = []
    for key, page in pages.items():
        if page is None or not page.body:
            continue
        markers = find_export_markers(page.body)
        if markers:
            export_markers[key] = markers
        export_links.extend(find_export_links(page.body))

    app_connects = [c for c in connects if c.get("port") in (80, 443)]
    tcp_ok = any(c.get("connect") == "ok" for c in app_connects)
    entry = app.get("entry") or {}
    statistics = app.get("statistics") or {}
    systems = app.get("systems") or {}
    statistics_ok = statistics.get("status") == 200
    systems_ok = systems.get("status") == 200
    probed = bool(pages) or bool(compound_attempts) or bool(app)
    unknown = "unknown_no_requests_made"

    dielectric_rows = [
        {
            "compound": attempt["compound"],
            "ddb_number": (attempt.get("details") or {}).get("identity", {}).get("ddb_number"),
            "property": (attempt["details"].get("dielectric_row") or {}).get("property"),
            "points": (attempt["details"].get("dielectric_row") or {}).get("points"),
            "sets": (attempt["details"].get("dielectric_row") or {}).get("sets"),
            "temperature_range": (attempt["details"].get("dielectric_row") or {}).get(
                "temperature_range"
            ),
            "states": (attempt["details"].get("dielectric_row") or {}).get("states"),
        }
        for attempt in compound_attempts
        if (attempt.get("details") or {}).get("dielectric_row")
    ]
    compounds_with_epsilon_coverage = [row["compound"] for row in dielectric_rows]
    pure_names = list(systems.get("pure_components") or [])
    join = join_names(pure_names, list(roster_names)) if pure_names and roster_names else None

    sub_sitemap_reachable = [s for s in sub_sitemaps if s["status"] == 200]
    values_read = sum(int(a["permittivity_values_returned"]) for a in compound_attempts)
    app_host = ONLINE_ORIGIN.split("//")[1]
    app_attempts = [
        r
        for r in records
        if app_host in str(r.get("url", "")) and "[cache hit]" not in str(r.get("note", ""))
    ]
    app_answers = [r for r in app_attempts if r["status"] == 200]
    app_reliability = {
        "attempts": len(app_attempts),
        "answered_200": len(app_answers),
        "first_attempt_success_rate": (
            round(len(app_answers) / len(app_attempts), 3) if app_attempts else None
        ),
        "note": (
            "the app host frequently drops a connection; retries are counted here as "
            "separate attempts, and a failed socket probe can coexist with successful "
            "HTTP answers in the same run"
        ),
    }

    if not probed:
        verdict_q1 = unknown
    elif app_link is None:
        verdict_q1 = "no_free_entry_point_found"
    elif app_answers:
        verdict_q1 = "exists_free_of_charge_anonymous_and_usable_with_retries"
    elif tcp_ok:
        verdict_q1 = "exists_free_of_charge_but_the_application_never_answered"
    else:
        verdict_q1 = "exists_and_free_of_charge_but_unreachable_from_this_environment"

    if not probed:
        verdict_q2 = unknown
    elif values_read > 0:
        verdict_q2 = "values_retrievable"
    elif dielectric_rows:
        verdict_q2 = "temperature_resolved_coverage_visible_but_no_values_returned"
    elif no_data:
        verdict_q2 = "the_free_layer_reveals_no_data"
    else:
        verdict_q2 = "not_established"

    if not probed:
        verdict_q3 = unknown
    elif export_links:
        verdict_q3 = "machine_readable_export_present"
    elif systems_ok or statistics_ok:
        verdict_q3 = "html_tables_only_no_export_endpoint"
    else:
        verdict_q3 = "no_machine_readable_surface_reached"

    metadata_new = join["unmatched_count"] if join else 0
    if not probed:
        verdict_q4 = unknown
    elif values_read > 0:
        verdict_q4 = "increment_present_needs_roster_join"
    elif metadata_new > 0:
        verdict_q4 = "coverage_metadata_only_name_level_candidates"
    else:
        verdict_q4 = "no_net_increment"

    q1 = {
        "question": "does a free, anonymous Online Search layer exist and can it be used?",
        "entry_point_found_on_marketing_site": app_link is not None,
        "entry_point_url": app_link,
        "vendor_free_access_claim": (
            "online.html / ddb-search.html: 'allows everybody world-wide to search the content "
            "of the Dortmund Data Bank online'"
        ),
        "login_or_licence_prompt_on_marketing_pages": any(login_markers.values()),
        "login_marker_pages": [key for key, value in login_markers.items() if value],
        "app_host_dns": next((c.get("dns_ips") for c in app_connects if c.get("port") == 80), None),
        "app_host_tcp_connect": [
            {"port": c.get("port"), "connect": c.get("connect"), "seconds": c.get("seconds")}
            for c in app_connects
        ],
        "app_entry_status": entry.get("status"),
        "app_entry_bytes": entry.get("bytes"),
        "app_entry_attempts": entry.get("attempts"),
        "app_entry_is_anonymous_component_search": bool(entry.get("has_search_form"))
        and not entry.get("login_marker", True),
        "app_search_axes": entry.get("search_item_fields"),
        "app_reliability": app_reliability,
        "app_has_no_property_query": True,
        "free_quota_documented": False,
        "free_quota_note": (
            "no request/token quota is published; the only stated limit is that the app host "
            "frequently drops the first TCP connection, so callers must retry"
        ),
        "verdict": verdict_q1,
    }

    q2 = {
        "question": "does the free layer contain pure-component epsilon(T)?",
        "permittivity_named_in_supported_data_banks": permittivity_in_banks,
        "ddb_carries_pure_component_permittivity": bool(permittivity_in_banks),
        "vendor_pure_component_claim": (
            "ddb-mdec.html: 'Pure component dielectric constants have been part of the PCP data "
            "bank from its start in 1994'"
        ),
        "vendor_says_free_layer_shows_no_data": bool(no_data),
        "no_data_statements": no_data,
        "permittivity_mentions_on_dielectric_product_page": dielectric_page_mentions,
        "free_calculator_properties": free_props,
        "free_calculator_property_count": len(free_props),
        "free_calculator_permittivity_mentions": free_props_hits,
        "free_calculator_covers_permittivity": bool(free_props_hits),
        "dielectric_bank_statistics": statistics.get("dielectric_bank"),
        "dielectric_bank_system_list": {
            "title": systems.get("title"),
            "system_count": systems.get("system_count"),
            "data_sets": systems.get("data_sets"),
            "data_points": systems.get("data_points"),
            "section_sizes": systems.get("section_sizes"),
            "pure_component_count": systems.get("pure_component_count"),
            "pure_component_sets_sum": systems.get("pure_component_sets_sum"),
            "pure_component_points_sum": systems.get("pure_component_points_sum"),
        },
        "per_compound_attempts": compound_attempts,
        "dielectric_property_rows": dielectric_rows,
        "compounds_with_visible_dielectric_coverage": compounds_with_epsilon_coverage,
        "permittivity_values_read": values_read,
        "temperature_values_read": 0,
        "property_name_returned": DIELECTRIC_PROPERTY_NAME,
        "units_returned": "temperature ranges in K; points are counted, not listed",
        "verdict": verdict_q2,
    }

    q3 = {
        "question": "is the free layer machine readable?",
        "export_link_targets_found": sorted(set(export_links)),
        "csv_or_json_export_endpoint_found": bool(export_links),
        "bulk_export_documented": False,
        "export_markers_raw_census": export_markers,
        "data_surface_type": (
            "server-rendered HTML tables on a Windows executable endpoint (.exe); "
            "no documented API"
        ),
        "stable_url_scheme": {
            "component_search": APP_URL + "?submit=Search&name=<name>",
            "details": APP_URL + "?submit=Details&systemcomplist=<DDB#>",
            "statistics": APP_URL + "?submit=Statistics",
            "systems": APP_URL + "?submit=DDBSystems&databank=<CODE>",
        },
        "parsing_notes": [
            "rows are malformed: the first <td> of each <tr> is never closed",
            (
                "the Details property table puts Points/Sets/T-range on the first row of each "
                "property and state breakdowns on unlabelled continuation rows"
            ),
        ],
        "only_value_retrieval_path": (
            "manual mail request to DDBST ('A quote for experimental literature data about the "
            "component can be obtained via email')"
        ),
        "verdict": verdict_q3,
    }

    q4 = {
        "question": "net new compounds for v1.x?",
        "target_compounds_tried": list(TARGET_COMPOUNDS),
        "compounds_with_any_permittivity_value_read": 0,
        "compounds_with_temperature_series_read": 0,
        "compounds_with_visible_dielectric_coverage": compounds_with_epsilon_coverage,
        "dielectric_bank_pure_components": len(pure_names),
        "roster_rows": len(roster_names),
        "roster_join": join,
        "net_new_compounds": 0,
        "net_new_compounds_at_coverage_metadata_level": metadata_new,
        "reason": (
            "no requests were made, so nothing is claimed"
            if not probed
            else "no permittivity value of any kind was returned. The free layer does expose "
            "per-compound dielectric coverage (datasets, points, temperature range) and the "
            "dielectric bank's complete pure-component list, but those rows carry no values "
            "and are joinable only by name"
        ),
        "verdict": verdict_q4,
    }

    phases_completed = {
        "marketing_pages_answered": sum(1 for page in pages.values() if page.ok),
        "marketing_pages_attempted": len(pages),
        "sub_sitemap_samples_reachable": len(sub_sitemap_reachable),
        "sub_sitemap_samples_attempted": len(sub_sitemaps),
        "app_entry_answered": entry.get("status") == 200,
        "statistics_answered": statistics_ok,
        "dielectric_bank_list_answered": systems_ok,
        "compound_searches_answered": sum(
            1 for a in compound_attempts if (a.get("search") or {}).get("status") == 200
        ),
        "compound_details_answered": sum(
            1 for a in compound_attempts if (a.get("details") or {}).get("status") == 200
        ),
        "compound_attempts": len(compound_attempts),
        "note": (
            "``failed_attempts`` lists individual dropped connections; this block shows "
            "which phases nonetheless produced usable content, so an empty-phase gap "
            "cannot hide behind a successful retry"
        ),
    }

    return {
        "phases_completed": phases_completed,
        "q1_free_layer_exists": q1,
        "q2_contains_permittivity_temperature": q2,
        "q3_machine_readable": q3,
        "q4_net_new_compounds": q4,
        "app_reliability": app_reliability,
        "sub_sitemap_reachable_samples": len(sub_sitemap_reachable),
        "sitemap_sub_families_advertised": sitemap_index.get("advertised_sub_sitemaps", 0),
    }


def write_summary(summary: dict[str, Any], path: Path | None = None) -> Path:
    target = path or SUMMARY_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(summary, indent=2, ensure_ascii=False) + "\n")
    return target


def format_console(summary: dict[str, Any]) -> str:
    answers = summary["answers"]
    budget = summary["budget"]
    counts = summary["counts"]
    q1 = answers["q1_free_layer_exists"]
    q2 = answers["q2_contains_permittivity_temperature"]
    q3 = answers["q3_machine_readable"]
    q4 = answers["q4_net_new_compounds"]
    lines = [
        (
            f"DDBST free-layer probe [{summary['mode']}] "
            f"new_requests={budget['used']}/{budget['limit']} "
            f"cache_hits={summary['cache']['hits']} "
            f"errors={counts['errors']} bytes={counts['bytes_received']}"
        ),
        f"  status histogram: {counts['status_histogram']}",
        f"  Q1 free layer: {q1['verdict']}",
        (
            f"  Q2 permittivity: {q2['verdict']} "
            f"(values read={q2['permittivity_values_read']}, "
            f"coverage rows={len(q2['dielectric_property_rows'])})"
        ),
        f"  Q3 machine readable: {q3['verdict']}",
        (
            f"  Q4 net new compounds: {q4['net_new_compounds']} "
            f"(coverage-metadata candidates={q4['net_new_compounds_at_coverage_metadata_level']}, "
            f"{q4['verdict']})"
        ),
    ]
    return "\n".join(lines)


def _force_utf8_stdout() -> None:
    stream = sys.stdout
    encoding = getattr(stream, "encoding", "") or ""
    if hasattr(stream, "buffer") and encoding.lower() not in ("utf-8", "utf8"):
        import io

        sys.stdout = io.TextIOWrapper(stream.buffer, encoding="utf-8", errors="replace")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--offline", action="store_true", help="no network I/O at all")
    parser.add_argument("--budget", type=int, default=DEFAULT_REQUEST_BUDGET)
    parser.add_argument("--sleep", type=float, default=DEFAULT_SLEEP_SECONDS)
    parser.add_argument("--output", type=Path, default=SUMMARY_PATH)
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=None,
        help="memo directory for successful responses; gaps are refilled on a re-run",
    )
    parser.add_argument("--json", action="store_true", help="print the whole summary")
    args = parser.parse_args(argv)

    _force_utf8_stdout()
    summary = run_probe(
        budget=RequestBudget(limit=args.budget),
        sleep_seconds=args.sleep,
        offline=args.offline,
        cache_dir=args.cache_dir,
    )
    path = write_summary(summary, args.output)
    print(format_console(summary))
    print(f"summary -> {path}")
    if args.json:
        print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())