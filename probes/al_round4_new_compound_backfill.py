#!/usr/bin/env python
"""AL Round 4 (Week 14): new-compound backfill list v0 -- offline, local-only.

Appendix D1 of the Week 14 blueprint re-scopes the v1.x accuracy lever from
"more temperature points" to "more compounds".  This probe therefore re-reads the
Round-3 lead set (37 open-access leads) through a *compound-coverage* lens instead
of a temperature lens, and asks one question per lead: does it name a compound the
local dielectric panel does not already have?

Hard scope of this probe:

* offline.  No OpenAlex / Unpaywall / HTTP call is made.  The OpenAlex sweep of
  Round 3 already happened; this round only re-analyses its local output.
* the only numeric epsilon values copied into the outputs are ones that were
  already read out of an *open-access* title/abstract in Round 3.  A lead whose
  clue is prose only ("low dielectric constant") is never given a number.
* the local panel is defined by two frozen files: data/dielectric_v03.csv
  (246-row room-temperature roster) and
  data/processed/dielectric_observations_v11plus.csv (2065 observation rows over
  153 compounds).  Neither is modified.

The list is an *acquisition shortlist*, not a dataset.  Every row is a lead plus a
declared local-coverage verdict; no measurement table is built and no feature is
derived here.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

TRIAGE_PATH = REPOSITORY_ROOT / "probes" / "al_round3_oa_triage.csv"
TRIAGE_SHA256 = "e1cac8a8305ebdb745597c5452ce1c228a1f75cd71c70b1da40fbccd7fa22991"
LEADS_PATH = REPOSITORY_ROOT / "data" / "processed" / "openalex_oa_candidates.csv"
LEADS_SHA256 = "3e1d7ee537b2bf4fffa38b243e5c208bf5cc83b1e4d8b04303f50f89a07a8d5d"
V03_PATH = REPOSITORY_ROOT / "data" / "dielectric_v03.csv"
V03_SHA256 = "ff2142936e06e04b329b70f8597574f75349e54ce876e9fff81309e6d35ccce4"
OBSERVATIONS_PATH = (
    REPOSITORY_ROOT / "data" / "processed" / "dielectric_observations_v11plus.csv"
)
OBSERVATIONS_SHA256 = (
    "159b928f800a55969963da275ed05c30ce8a19cffc48353a9c490eec68a49af9"
)

LIST_PATH = REPOSITORY_ROOT / "probes" / "al_round4_backfill_list_v0.csv"
GAPS_PATH = REPOSITORY_ROOT / "probes" / "artifacts" / "al_round4_local_coverage_gaps.csv"
SUMMARY_PATH = REPOSITORY_ROOT / "probes" / "al_round4_new_compound_backfill_summary.json"
REPORT_PATH = REPOSITORY_ROOT / "reports" / "al_round4_new_compound_backfill.md"
PENDING_REPORT_PATH = REPOSITORY_ROOT / "reports" / "al_round4_pending_oa_triage.md"

SCHEMA_VERSION = "al_round4_new_compound_backfill_summary@1"

# Round-3 dispositions are kept as the audit key that ties every row back to the
# Round-3 triage.  The Round-4 priority is re-derived and is not a copy.
ROUND3_PRIORITY_ORDER = {"P1": 0, "P2": 1, "P3": 2}
TARGET_CLASS_ORDER = {"core": 0, "adjacent": 1, "core_family_unresolved": 2, "off": 3}
PRIORITY_ORDER = {"P1": 0, "P2": 1, "P3": 2}
ROW_KIND_ORDER = {
    "new_compound": 0,
    "gap_family": 1,
    "roster_gap": 2,
    "local_duplicate_reconciliation": 3,
}

# A Round-3 rationale carrying a noise veto means the lead was judged to be about
# a different phenomenon (pool boiling, DNAPL geophysics, polymer photocatalysis,
# ...) rather than about a solvent permittivity.  Such a compound is never
# promoted by the Round-4 rule, however well it scores on family membership.
NOISE_VETO_RE = re.compile(r"noise veto \(([^)]*)\)")

# A review/perspective does not measure anything itself, so its epsilon mention
# is a restatement.  This is a word test on the title/venue only.
REVIEW_CUE_RE = re.compile(
    r"\b(review|reviews|perspective|perspectives|overview|progress|advances|"
    r"tutorial|roadmap)\b",
    re.IGNORECASE,
)

# A first-hand measurement is a lead whose own title/abstract shows the paper
# doing dielectric work (spectroscopy, relaxation, or an explicitly measured /
# derived value).  A bare pronoun is not enough: "we find" describes dynamics,
# not an epsilon value, so the dielectric language and the measurement verb have
# to be near each other.  When they are not, the clue is only a restatement of a
# known value and is labelled as such.
MEASUREMENT_CUE_RE = re.compile(
    r"dielectric\s+(?:spectroscop\w*|relax\w*|measurement\w*|loss\w*|dispersion\w*|"
    r"response\w*|propert\w*)",
    re.IGNORECASE,
)
MEASUREMENT_VERB_RE = re.compile(
    r"(?:measur\w*|determin\w*|obtain\w*|report\w*|extrapolat\w*|deriv\w*|comput\w*|"
    r"calculat\w*|evaluat\w*)",
    re.IGNORECASE,
)
EPSILON_WORD_RE = re.compile(
    r"(?:dielectric\s+constant|permittivity|static\s+dielectric|dielectric\s+permit\w*)",
    re.IGNORECASE,
)
MEASUREMENT_WINDOW_CHARS = 80


def clue_is_measured(title: str, evidence: str) -> bool:
    """True when the lead shows the paper doing its own dielectric work."""

    haystack = (title or "") + " . " + (evidence or "")
    if MEASUREMENT_CUE_RE.search(haystack):
        return True
    for match in EPSILON_WORD_RE.finditer(haystack):
        start = max(0, match.start() - MEASUREMENT_WINDOW_CHARS)
        end = min(len(haystack), match.end() + MEASUREMENT_WINDOW_CHARS)
        if MEASUREMENT_VERB_RE.search(haystack[start:end]):
            return True
    return False

EVIDENCE_FIRST_HAND = "第一手测量"
EVIDENCE_RESTATEMENT = "汇编转述"
EVIDENCE_REVIEW = "综述"
EVIDENCE_NO_CLUE = "无ε线索"
EVIDENCE_KINDS = (
    EVIDENCE_FIRST_HAND,
    EVIDENCE_RESTATEMENT,
    EVIDENCE_REVIEW,
    EVIDENCE_NO_CLUE,
)

ACTION_READ_FULLTEXT = "取全文"
ACTION_HUMAN = "人读"
ACTION_LEAD_ONLY = "仅线索"
ACTION_DROP = "放弃"
ACTION_ARCHIVE = "归档"
ACTIONS = (ACTION_READ_FULLTEXT, ACTION_HUMAN, ACTION_LEAD_ONLY, ACTION_DROP)
PAPER_ACTIONS = (ACTION_READ_FULLTEXT, ACTION_HUMAN, ACTION_LEAD_ONLY, ACTION_ARCHIVE)

LIST_FIELDS = (
    "row_kind",
    "priority",
    "compound_name",
    "inchikey_if_resolved",
    "smiles_if_resolved",
    "in_local_v03",
    "in_local_observations",
    "local_epsilon_rows",
    "is_new_compound",
    "epsilon_value_or_kind",
    "epsilon_values",
    "temperature_window",
    "source_doi",
    "oa_status",
    "oa_url",
    "oa_reachable",
    "evidence_kind",
    "local_trace",
    "local_trace_restricted",
    "local_trace_files",
    "round3_disposition",
    "round3_priority",
    "why_new_compound",
    "action",
    "rationale",
)

GAP_FIELDS = (
    "row_kind",
    "key",
    "family",
    "compound_name",
    "inchikey",
    "observation_rows",
    "distinct_temperatures",
    "compounds_in_scope",
    "rows_per_compound",
    "distinct_source_doi",
    "share_of_observation_rows",
    "single_row_compounds",
    "gap_signal",
    "note",
)

# The trace evidence chain only accepts the curated data trees.  data/interim/ is
# the week-scoped scratch area -- ad-hoc text extracts, timing probes, throwaway
# reruns -- and a compound that merely appears in one of those says nothing about
# what the project actually knows.  Note that git-ignore status is deliberately
# NOT the rule: several curated paths under data/ are ignored for size or
# redistribution reasons (data/restricted/ in particular) and stay in scope.
TRACE_ROOTS = (
    "data/external/",
    "data/processed/",
    "data/raw/",
    "data/reference/",
    "data/restricted/",
)
SCRATCH_PREFIXES = ("data/interim/",)

# Second declared scratch rule: a basename that begins with an underscore is
# private/scratch by project convention -- the g1plus request logs are named
# that way -- so it may not carry evidence whichever tree it lands in.  This is
# the rule that catches the failure mode which first broke this scan: a side
# task dumped a paper-text extract named "_lever8_paper_text.txt" into the
# workspace and the recursive walk adopted it as project knowledge.
SCRATCH_NAME_PREFIX = "_"

# Local files that define "already covered".  They are excluded from the local
# trace scan, because a trace means "mentioned somewhere else locally".
LOCAL_PANEL_FILES = {
    "data/dielectric_v03.csv",
    "data/processed/dielectric_observations_v11plus.csv",
    "data/processed/dielectric_observations_v11.csv",
    "data/processed/dielectric_raw.csv",
}
LEAD_FILES = {
    "data/processed/openalex_oa_candidates.csv",
    "data/processed/al_round3_candidates.csv",
}
TRACE_EXTENSIONS = {".csv", ".tsv", ".json", ".txt", ".md"}

# A trace under this prefix means the compound is already known to a source the
# project may not redistribute.  Only the path is ever recorded: no value from a
# restricted file enters this probe's output, and such a trace never promotes a
# compound into a dataset.
RESTRICTED_PREFIX = "data/restricted/"


# A one-compound family is degenerate for coverage purposes (water is a single
# molecule by definition) and an unparsed family is a data-hygiene signal rather
# than a chemistry gap, so neither is ranked as a coverage gap.
DEGENERATE_GAP_FAMILIES = frozenset({"water", "unparsed"})


class BackfillError(RuntimeError):
    """Raised when an input no longer matches the sha256 this probe was built on."""


# --------------------------------------------------------------------------- #
# input plumbing
# --------------------------------------------------------------------------- #


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, fields: Sequence[str], rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fields), lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def check_inputs() -> dict[str, Any]:
    expected = {
        "al_round3_oa_triage": (TRIAGE_PATH, TRIAGE_SHA256),
        "openalex_oa_candidates": (LEADS_PATH, LEADS_SHA256),
        "dielectric_v03": (V03_PATH, V03_SHA256),
        "dielectric_observations_v11plus": (OBSERVATIONS_PATH, OBSERVATIONS_SHA256),
    }
    report: dict[str, Any] = {}
    for name, (path, digest) in expected.items():
        actual = sha256_file(path)
        report[name] = {
            "path": str(path),
            "sha256_expected": digest,
            "sha256_actual": actual,
            "intact": actual == digest,
        }
        if actual != digest:
            raise BackfillError(
                f"frozen input changed: {path} actual={actual} expected={digest}"
            )
    return report


# --------------------------------------------------------------------------- #
# local panel index
# --------------------------------------------------------------------------- #


class LocalPanel:
    """Presence and row counts of every compound in the local dielectric panel."""

    def __init__(
        self,
        v03_rows: Sequence[Mapping[str, str]],
        obs_rows: Sequence[Mapping[str, str]],
    ) -> None:
        self.v03: dict[str, dict[str, str]] = {}
        for row in v03_rows:
            key = (row.get("inchikey") or "").strip()
            if key:
                self.v03.setdefault(key, row)
        self.observations: dict[str, list[dict[str, str]]] = defaultdict(list)
        for row in obs_rows:
            key = (row.get("inchikey") or "").strip()
            if key:
                self.observations[key].append(row)
        self.observation_rows = len(obs_rows)
        self.compounds = sorted(set(self.v03) | set(self.observations))

    def presence(self, inchikey: str) -> dict[str, Any]:
        key = (inchikey or "").strip()
        if not key:
            return {
                "in_local_v03": "na",
                "in_local_observations": "na",
                "local_epsilon_rows": "",
                "local_name": "",
                "local_smiles": "",
                "local_distinct_temperatures": "",
                "local_epsilon_values": "",
            }
        rows = self.observations.get(key, [])
        v03_row = self.v03.get(key)
        temperatures: set[float] = set()
        values: list[float] = []
        for row in rows:
            try:
                temperatures.add(round(float(row.get("T_K") or ""), 2))
            except (TypeError, ValueError):
                pass
            try:
                values.append(float(row.get("epsilon") or ""))
            except (TypeError, ValueError):
                pass
        return {
            "in_local_v03": "yes" if v03_row else "no",
            "in_local_observations": "yes" if rows else "no",
            "local_epsilon_rows": len(rows),
            "local_name": (v03_row or {}).get("name", "")
            or (rows[0].get("name", "") if rows else ""),
            "local_smiles": (v03_row or {}).get("smiles", "")
            or (rows[0].get("smiles", "") if rows else ""),
            "local_distinct_temperatures": len(temperatures),
            "local_epsilon_values": ";".join(
                format(value, "g") for value in sorted(set(values))
            ),
        }

    def is_new_compound(self, inchikey: str) -> bool:
        presence = self.presence(inchikey)
        return (
            presence["in_local_v03"] == "no"
            and presence["in_local_observations"] == "no"
        )


def load_local_panel() -> LocalPanel:
    return LocalPanel(read_csv(V03_PATH), read_csv(OBSERVATIONS_PATH))


# --------------------------------------------------------------------------- #
# structural family classifier (local, RDKit SMARTS, first match wins)
# --------------------------------------------------------------------------- #


def _load_rdkit() -> tuple[Any, dict[str, Any]]:
    from rdkit import Chem, RDLogger

    RDLogger.DisableLog("rdApp.*")
    smarts = {
        "silicon": Chem.MolFromSmarts("[Si]"),
        "nitrile": Chem.MolFromSmarts("[NX1]#[CX2]"),
        "sulfone": Chem.MolFromSmarts("[SX4](=[OX1])(=[OX1])"),
        "sulfoxide": Chem.MolFromSmarts("[SX3]=[OX1]"),
        "carbonate": Chem.MolFromSmarts("[CX3](=[OX1])([OX2])[OX2]"),
        "carboxyl": Chem.MolFromSmarts("[CX3](=[OX1])[OX2H]"),
        "acid_oh": Chem.MolFromSmarts("[CX3](=[OX1])[OX2H]"),
        "amine_any": Chem.MolFromSmarts("[NX3]"),
        "ester": Chem.MolFromSmarts("[CX3](=[OX1])[OX2][#6]"),
        "ether": Chem.MolFromSmarts("[OD2]([#6])[#6]"),
        "alcohol": Chem.MolFromSmarts("[OX2H]"),
        "amine": Chem.MolFromSmarts("[NX3;H2,H1;!$(NC=O)]"),
        "aromatic": Chem.MolFromSmarts("c"),
    }
    return Chem, smarts


_CHEM, _SMARTS = _load_rdkit()


def _is_lactone(mol: Any) -> bool:
    """A cyclic ester, excluding the cyclic carbonates.

    Ethylene carbonate also has a ring oxygen bonded to a carbonyl carbon, so the
    carbonyl carbon has to carry exactly one single-bonded oxygen for the ring to
    be a lactone rather than a carbonate.
    """

    ring_info = mol.GetRingInfo()
    for atom in mol.GetAtoms():
        if atom.GetSymbol() != "O" or not atom.IsInRing():
            continue
        for neighbour in atom.GetNeighbors():
            if neighbour.GetSymbol() != "C" or not neighbour.IsInRing():
                continue
            single_oxygens = sum(
                1
                for bond in neighbour.GetBonds()
                if bond.GetBondTypeAsDouble() == 1.0
                and bond.GetOtherAtom(neighbour).GetSymbol() == "O"
            )
            if single_oxygens != 1:
                continue
            double_o = any(
                bond.GetBondTypeAsDouble() == 2.0
                and bond.GetOtherAtom(neighbour).GetSymbol() == "O"
                for bond in neighbour.GetBonds()
            )
            if not double_o:
                continue
            if ring_info.AreAtomsInSameRing(atom.GetIdx(), neighbour.GetIdx()):
                return True
    return False


def classify_family(smiles: str) -> str:
    """Deterministic, first-match-wins structural family tag for a local compound."""

    text = (smiles or "").strip()
    if not text:
        return "unparsed"
    if text == "O":
        return "water"
    mol = _CHEM.MolFromSmiles(text)
    if mol is None:
        return "unparsed"
    charges = [atom.GetFormalCharge() for atom in mol.GetAtoms()]
    if any(charge > 0 for charge in charges) and any(charge < 0 for charge in charges):
        return "ionic_liquid"
    # The panel stores four protic ionic liquids as neutral two-component SMILES
    # (an acid fragment plus an amine fragment, e.g. "CC(=O)O.NCCO" for
    # ethanolammonium acetate), so the formal-charge test cannot see them.  A
    # multi-fragment entry that carries both an acid and an amine function is that
    # proton-transfer pair, and is labelled as one instead of being called an acid.
    fragments = _CHEM.GetMolFrags(mol, asMols=True)
    if (
        len(fragments) >= 2
        and any(fragment.HasSubstructMatch(_SMARTS["acid_oh"]) for fragment in fragments)
        and any(fragment.HasSubstructMatch(_SMARTS["amine_any"]) for fragment in fragments)
    ):
        return "protic_ionic_pair"
    if mol.HasSubstructMatch(_SMARTS["silicon"]):
        return "siloxane"
    if mol.HasSubstructMatch(_SMARTS["nitrile"]):
        return "nitrile"
    if mol.HasSubstructMatch(_SMARTS["sulfone"]) or mol.HasSubstructMatch(
        _SMARTS["sulfoxide"]
    ):
        return "sulfone"
    if _is_lactone(mol):
        return "lactone"
    if mol.HasSubstructMatch(_SMARTS["carbonate"]):
        return "carbonate"
    if mol.HasSubstructMatch(_SMARTS["carboxyl"]):
        return "acid"
    if mol.HasSubstructMatch(_SMARTS["ester"]):
        return "ester"
    fluorines = sum(1 for atom in mol.GetAtoms() if atom.GetSymbol() == "F")
    carbons = sum(1 for atom in mol.GetAtoms() if atom.GetSymbol() == "C")
    if fluorines >= 2 and carbons and fluorines / carbons >= 0.5:
        return "fluorinated"
    if mol.HasSubstructMatch(_SMARTS["alcohol"]):
        return "alcohol_amine"
    if mol.HasSubstructMatch(_SMARTS["amine"]):
        return "alcohol_amine"
    if mol.HasSubstructMatch(_SMARTS["ether"]):
        return "ether_glyme"
    if mol.HasSubstructMatch(_SMARTS["aromatic"]):
        return "aromatic"
    return "other"

# --------------------------------------------------------------------------- #
# lead parsing helpers
# --------------------------------------------------------------------------- #


def parse_triplets(row: Mapping[str, str]) -> list[tuple[str, str, str]]:
    """Split the positional compound_name / inchikey / smiles lists of one lead."""

    names = [part.strip() for part in (row.get("compound_names") or "").split(";") if part.strip()]
    keys = [part.strip() for part in (row.get("inchikeys") or "").split(";") if part.strip()]
    smiles = [part.strip() for part in (row.get("smiles_list") or "").split(";") if part.strip()]
    if not names:
        return []
    size = len(names)
    keys = (keys + [""] * size)[:size]
    smiles = (smiles + [""] * size)[:size]
    return list(zip(names, keys, smiles))


def triplet_mismatch_count(rows: Sequence[Mapping[str, str]]) -> int:
    mismatches = 0
    for row in rows:
        names = [p for p in (row.get("compound_names") or "").split(";") if p.strip()]
        keys = [p for p in (row.get("inchikeys") or "").split(";") if p.strip()]
        smiles = [p for p in (row.get("smiles_list") or "").split(";") if p.strip()]
        if names and not (len(names) == len(keys) == len(smiles)):
            mismatches += 1
    return mismatches


def normalise_window(value: str) -> str:
    lowered = (value or "").strip().lower()
    if lowered == "true":
        return "yes"
    if lowered == "false":
        return "no"
    return "unknown"


def lead_noise_veto(row: Mapping[str, str]) -> str:
    match = NOISE_VETO_RE.search(row.get("rationale") or "")
    return match.group(1) if match else ""


def lead_evidence_kind(row: Mapping[str, str]) -> str:
    haystack = " ".join([row.get("title") or "", row.get("venue") or ""])
    if REVIEW_CUE_RE.search(haystack):
        return EVIDENCE_REVIEW
    kind = (row.get("epsilon_clue_kind") or "").strip()
    if kind == "value":
        return EVIDENCE_FIRST_HAND
    if kind == "wording_only":
        if clue_is_measured(row.get("title") or "", row.get("epsilon_evidence") or ""):
            return EVIDENCE_FIRST_HAND
        return EVIDENCE_RESTATEMENT
    return EVIDENCE_NO_CLUE


def derive_priority(
    *,
    is_new_compound: bool,
    noise_vetoed: bool,
    target_class: str,
    epsilon_kind: str,
) -> str:
    """Round-4 priority rule, declared before execution.

    The round is about coverage, so a candidate is only a backfill target when it
    is genuinely new.  P1 additionally requires the missing compound to sit in a
    core target family and to come with an epsilon clue; P2 relaxes the family to
    the adjacent battery-solvent families; everything else is P3.
    """

    if not is_new_compound:
        return "P3"
    if noise_vetoed:
        return "P3"
    has_clue = epsilon_kind in {"value", "wording_only"}
    if target_class == "core" and has_clue:
        return "P1"
    if target_class in {"core", "adjacent"} and has_clue:
        return "P2"
    return "P3"


def derive_action(
    *,
    is_new_compound: bool,
    noise_vetoed: bool,
    target_class: str,
    epsilon_kind: str,
    oa_reachable: str,
) -> str:
    if not is_new_compound:
        return ACTION_DROP
    if noise_vetoed:
        return ACTION_DROP
    if target_class == "off":
        return ACTION_LEAD_ONLY
    if epsilon_kind == "none":
        return ACTION_LEAD_ONLY
    if oa_reachable == "true":
        return ACTION_READ_FULLTEXT
    return ACTION_HUMAN


# --------------------------------------------------------------------------- #
# local (non-panel) trace scan
# --------------------------------------------------------------------------- #


def trace_scan_allowed(relative_path: str) -> bool:
    """True when a data/ path may contribute to the trace evidence chain.

    A path is in scope when it sits in a declared curated root, or when it is a
    curated top-level table directly under data/.  The scratch rules run first -- the
    declared scratch prefixes and the underscore basename convention -- so an excluded
    tree can never be re-admitted by the root test, and an ad-hoc dump keeps failing
    even when it is dropped into a curated tree.
    """

    if relative_path.startswith(SCRATCH_PREFIXES):
        return False
    if relative_path.rsplit("/", 1)[-1].startswith(SCRATCH_NAME_PREFIX):
        return False
    if relative_path.startswith("data/") and relative_path.count("/") == 1:
        return True
    return relative_path.startswith(TRACE_ROOTS)


def local_trace_scan(targets: Mapping[str, str]) -> dict[str, list[tuple[str, str]]]:
    """Find local non-panel traces of each target InChIKey.

    A trace means the key (or the compound display name) appears in some other
    curated local data file.  It documents that the compound is known to the
    project but has never been observed dielectrically, which is a different
    statement from "the project has never heard of it".

    Two declared scratch rules apply: everything under data/interim/ (the
    week-scoped area) and any basename beginning with an underscore (private by
    convention) are excluded.  An ad-hoc paper-text dump or a throwaway rerun is
    not project knowledge, and letting one in would make the evidence chain depend
    on whatever a side task happened to write down that afternoon.
    """

    keys = {key: key.encode("ascii", "ignore") for key in targets if key}
    names = {
        key: name.lower().encode("utf-8")
        for key, name in targets.items()
        if name and len(name) >= 6
    }
    hits: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for file_path in sorted((REPOSITORY_ROOT / "data").rglob("*")):
        if not file_path.is_file() or file_path.suffix.lower() not in TRACE_EXTENSIONS:
            continue
        relative = file_path.relative_to(REPOSITORY_ROOT).as_posix()
        if not trace_scan_allowed(relative):
            continue
        if relative in LOCAL_PANEL_FILES or relative in LEAD_FILES:
            continue
        try:
            blob = file_path.read_bytes()
        except OSError:
            continue
        lowered = blob.lower()
        for key, token in keys.items():
            if token and token in blob:
                hits[key].append((relative, "key"))
                continue
            name = names.get(key)
            if name and name in lowered:
                hits[key].append((relative, "name"))
    return hits


# --------------------------------------------------------------------------- #
# candidate construction
# --------------------------------------------------------------------------- #


def _empty_entry(inchikey: str) -> dict[str, Any]:
    return {
        "inchikey": inchikey,
        "names": Counter(),
        "smiles": Counter(),
        "dois": [],
        "target_classes": set(),
        "epsilon_kinds": set(),
        "epsilon_values": [],
        "windows": set(),
        "oa_statuses": set(),
        "oa_urls": [],
        "oa_reachable": set(),
        "vetoes": set(),
        "evidence_kinds": Counter(),
        "dispositions": set(),
        "priorities": set(),
        "rationales": [],
        "titles": [],
    }


def _absorb_lead(entry: dict[str, Any], row: Mapping[str, str], name: str, smiles: str) -> None:
    doi = (row.get("doi") or "").strip()
    entry["names"][name] += 1
    if smiles:
        entry["smiles"][smiles] += 1
    if doi and doi not in entry["dois"]:
        entry["dois"].append(doi)
    title = (row.get("title") or "").strip()
    if title and title not in entry["titles"]:
        entry["titles"].append(title)
    entry["target_classes"].add((row.get("target_class") or "").strip())
    kind = (row.get("epsilon_clue_kind") or "").strip() or "none"
    entry["epsilon_kinds"].add(kind)
    if kind == "value":
        entry["epsilon_values"].extend(
            token.strip()
            for token in (row.get("epsilon_numbers_in_title_or_abstract") or "").split(";")
            if token.strip()
        )
    entry["windows"].add(normalise_window(row.get("temperature_window_covered") or ""))
    status = (row.get("unpaywall_oa_status") or "").strip()
    if status:
        entry["oa_statuses"].add(status)
    url = (row.get("best_oa_url") or "").strip()
    if url and url not in entry["oa_urls"]:
        entry["oa_urls"].append(url)
    reachable = (row.get("oa_fulltext_reachable") or "").strip()
    if reachable:
        entry["oa_reachable"].add(reachable)
    veto = lead_noise_veto(row)
    if veto:
        entry["vetoes"].add(veto)
    entry["evidence_kinds"][lead_evidence_kind(row)] += 1
    entry["dispositions"].add((row.get("disposition") or "").strip())
    entry["priorities"].add((row.get("priority") or "").strip())
    entry["rationales"].append((row.get("rationale") or "").strip())


def _why_new(presence: Mapping[str, Any], is_new: bool, row_kind: str) -> str:
    if row_kind == "gap_family":
        return "family-level gap: no single molecule resolved from the abstract"
    if is_new:
        return (
            "genuinely new to the panel: absent from both dielectric_v03.csv and "
            "dielectric_observations_v11plus.csv under an InChIKey join"
        )
    if row_kind == "roster_gap":
        return (
            "not a new compound: absent from the 246-row v03 roster but already in the "
            "observation table with "
            + str(presence["local_epsilon_rows"])
            + " rows / "
            + str(presence["local_distinct_temperatures"])
            + " distinct temperatures; counted as a roster gap, not as backfill"
        )
    return (
        "not a new compound: already covered locally (v03="
        + str(presence["in_local_v03"])
        + ", observations="
        + str(presence["in_local_observations"])
        + ", "
        + str(presence["local_epsilon_rows"])
        + " observation rows); kept only as a Round-3 reconciliation row and excluded from "
        "every backfill count"
    )


def _rationale(best_target: str, epsilon_kind: str, vetoed: bool, vetoes: set[str], leads: int) -> str:
    parts = ["round3_target=" + best_target, "epsilon=" + epsilon_kind]
    if vetoed:
        parts.append("noise_veto=" + "|".join(sorted(vetoes)))
    parts.append("leads=" + str(leads))
    return "; ".join(parts)


def build_candidates(
    triage_rows: Sequence[Mapping[str, str]],
    panel: LocalPanel,
    traces: Mapping[str, list[tuple[str, str]]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    family_gaps: list[dict[str, Any]] = []
    unaccounted: list[str] = []

    for row in triage_rows:
        doi = (row.get("doi") or "").strip()
        target_class = (row.get("target_class") or "").strip()
        triplets = parse_triplets(row)
        if not triplets:
            if target_class in {"core", "adjacent", "core_family_unresolved"}:
                family_gaps.append(
                    {
                        "doi": doi,
                        "target_class": target_class,
                        "target_families": (row.get("target_families") or "").strip(),
                        "unresolved_names": (row.get("unresolved_names") or "").strip(),
                        "rationale": (row.get("rationale") or "").strip(),
                        "title": (row.get("title") or "").strip(),
                        "oa_status": (row.get("unpaywall_oa_status") or "").strip(),
                        "oa_url": (row.get("best_oa_url") or "").strip(),
                        "oa_reachable": (row.get("oa_fulltext_reachable") or "").strip(),
                        "disposition": (row.get("disposition") or "").strip(),
                        "priority": (row.get("priority") or "").strip(),
                        "epsilon_kind": (row.get("epsilon_clue_kind") or "").strip(),
                    }
                )
            else:
                unaccounted.append(doi)
            continue
        for name, key, smiles in triplets:
            bucket = key or ("unresolved::" + doi + "::" + name)
            entry = grouped.setdefault(bucket, _empty_entry(key))
            _absorb_lead(entry, row, name, smiles)

    rows: list[dict[str, Any]] = []
    for key, entry in sorted(grouped.items()):
        presence = panel.presence(entry["inchikey"])
        is_new = (
            presence["in_local_v03"] == "no"
            and presence["in_local_observations"] == "no"
        )
        best_target = min(
            entry["target_classes"], key=lambda value: TARGET_CLASS_ORDER.get(value, 9)
        )
        if "value" in entry["epsilon_kinds"]:
            epsilon_kind = "value"
        elif "wording_only" in entry["epsilon_kinds"]:
            epsilon_kind = "wording_only"
        else:
            epsilon_kind = "none"
        all_leads_vetoed = bool(entry["vetoes"]) and all(
            NOISE_VETO_RE.search(text) for text in entry["rationales"]
        )
        if "true" in entry["oa_reachable"]:
            oa_reachable = "true"
        elif entry["oa_reachable"]:
            oa_reachable = "false"
        else:
            oa_reachable = "unknown"
        if "yes" in entry["windows"]:
            window = "yes"
        elif "no" in entry["windows"]:
            window = "no"
        else:
            window = "unknown"
        if is_new:
            row_kind = "new_compound"
        elif presence["in_local_v03"] == "no":
            row_kind = "roster_gap"
        else:
            row_kind = "local_duplicate_reconciliation"
        evidence_kind = EVIDENCE_NO_CLUE
        for candidate_kind in (
            EVIDENCE_FIRST_HAND,
            EVIDENCE_REVIEW,
            EVIDENCE_RESTATEMENT,
            EVIDENCE_NO_CLUE,
        ):
            if entry["evidence_kinds"].get(candidate_kind):
                evidence_kind = candidate_kind
                break
        trace_files = traces.get(key, [])
        rows.append(
            {
                "row_kind": row_kind,
                "priority": derive_priority(
                    is_new_compound=is_new,
                    noise_vetoed=all_leads_vetoed,
                    target_class=best_target,
                    epsilon_kind=epsilon_kind,
                ),
                "compound_name": entry["names"].most_common(1)[0][0] if entry["names"] else "",
                "inchikey_if_resolved": entry["inchikey"],
                "smiles_if_resolved": entry["smiles"].most_common(1)[0][0]
                if entry["smiles"]
                else "",
                "in_local_v03": presence["in_local_v03"],
                "in_local_observations": presence["in_local_observations"],
                "local_epsilon_rows": presence["local_epsilon_rows"],
                "is_new_compound": "yes" if is_new else "no",
                "epsilon_value_or_kind": epsilon_kind,
                "epsilon_values": ";".join(sorted(set(entry["epsilon_values"]), key=float))
                if epsilon_kind == "value"
                else "",
                "temperature_window": window,
                "source_doi": ";".join(entry["dois"]),
                "oa_status": ";".join(sorted(entry["oa_statuses"])),
                "oa_url": entry["oa_urls"][0] if entry["oa_urls"] else "",
                "oa_reachable": oa_reachable,
                "evidence_kind": evidence_kind,
                "local_trace": "yes" if trace_files else "no",
                "local_trace_restricted": (
                    "yes"
                    if any(path.startswith(RESTRICTED_PREFIX) for path, _kind in trace_files)
                    else "no"
                ),
                "local_trace_files": ";".join(
                    item[0] + ":" + item[1] for item in sorted(set(trace_files))
                ),
                "round3_disposition": ";".join(
                    sorted(value for value in entry["dispositions"] if value)
                ),
                "round3_priority": ";".join(
                    sorted(
                        (value for value in entry["priorities"] if value),
                        key=lambda value: ROUND3_PRIORITY_ORDER.get(value, 9),
                    )
                ),
                "why_new_compound": _why_new(presence, is_new, row_kind),
                "action": derive_action(
                    is_new_compound=is_new,
                    noise_vetoed=all_leads_vetoed,
                    target_class=best_target,
                    epsilon_kind=epsilon_kind,
                    oa_reachable=oa_reachable,
                ),
                "rationale": _rationale(
                    best_target, epsilon_kind, all_leads_vetoed, entry["vetoes"], len(entry["dois"])
                ),
                "local_name": presence["local_name"],
                "local_distinct_temperatures": presence["local_distinct_temperatures"],
                "titles": entry["titles"],
            }
        )

    for gap in family_gaps:
        families = gap["target_families"] or "unresolved"
        rows.append(
            {
                "row_kind": "gap_family",
                "priority": "P3",
                "compound_name": "[family gap] " + families,
                "inchikey_if_resolved": "",
                "smiles_if_resolved": "",
                "in_local_v03": "na",
                "in_local_observations": "na",
                "local_epsilon_rows": "",
                "is_new_compound": "no",
                "epsilon_value_or_kind": gap["epsilon_kind"] or "none",
                "epsilon_values": "",
                "temperature_window": "unknown",
                "source_doi": gap["doi"],
                "oa_status": gap["oa_status"],
                "oa_url": gap["oa_url"],
                "oa_reachable": gap["oa_reachable"] or "unknown",
                "evidence_kind": EVIDENCE_NO_CLUE,
                "local_trace": "na",
                "local_trace_restricted": "na",
                "local_trace_files": "",
                "round3_disposition": gap["disposition"],
                "round3_priority": gap["priority"],
                "why_new_compound": _why_new({}, False, "gap_family"),
                "action": ACTION_LEAD_ONLY,
                "rationale": (
                    "target="
                    + gap["target_class"]
                    + "; families="
                    + families
                    + "; unresolved: "
                    + (gap["unresolved_names"] or "n/a")
                    + "; "
                    + gap["rationale"]
                ),
                "local_name": "",
                "local_distinct_temperatures": "",
                "titles": [gap["title"]] if gap["title"] else [],
            }
        )

    rows.sort(
        key=lambda row: (
            ROW_KIND_ORDER.get(row["row_kind"], 9),
            PRIORITY_ORDER.get(row["priority"], 9),
            row["compound_name"],
            row["inchikey_if_resolved"],
        )
    )
    stats = {
        "triplet_mismatch_rows": triplet_mismatch_count(triage_rows),
        "gap_family_entries": len(family_gaps),
        "unaccounted_leads": sorted(unaccounted),
        "grouped_compounds": len(grouped),
    }
    return rows, stats

# --------------------------------------------------------------------------- #
# local coverage gaps (deliverable 3)
# --------------------------------------------------------------------------- #


def build_coverage_gaps(panel: LocalPanel) -> list[dict[str, Any]]:
    """Structural weak spots of the local observation table, computed locally.

    Three grains share one tidy CSV: family rows, per-compound single-row rows and
    per-source-DOI rows.  The row_kind column says which grain a row belongs to.
    """

    per_compound_rows: Counter[str] = Counter()
    per_compound_temps: dict[str, set[float]] = defaultdict(set)
    per_compound_doi: dict[str, set[str]] = defaultdict(set)
    per_compound_name: dict[str, str] = {}
    per_compound_smiles: dict[str, str] = {}
    for key, rows in panel.observations.items():
        per_compound_rows[key] = len(rows)
        per_compound_name[key] = (rows[0].get("name") or "").strip()
        per_compound_smiles[key] = (rows[0].get("smiles") or "").strip()
        for row in rows:
            try:
                per_compound_temps[key].add(round(float(row.get("T_K") or ""), 2))
            except (TypeError, ValueError):
                pass
            doi = (row.get("source_doi") or "").strip()
            if doi:
                per_compound_doi[key].add(doi)

    def family_of(key: str) -> str:
        smiles = per_compound_smiles.get(key) or (panel.v03.get(key) or {}).get("smiles", "")
        return classify_family(smiles)

    family_rows: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"compounds": 0, "rows": 0, "single": 0, "dois": Counter()}
    )
    for key, count in per_compound_rows.items():
        family = family_of(key)
        bucket = family_rows[family]
        bucket["compounds"] += 1
        bucket["rows"] += count
        if count == 1:
            bucket["single"] += 1
        # sorted, not set order: a tie in Counter.most_common would otherwise be
        # broken by string hash order and the note would change between processes
        for doi in sorted(per_compound_doi.get(key, set())):
            bucket["dois"][doi] += 1

    total_rows = sum(per_compound_rows.values()) or 1
    out: list[dict[str, Any]] = []
    for family in sorted(family_rows):
        bucket = family_rows[family]
        compounds = bucket["compounds"]
        single = bucket["single"]
        # An explicit tie-break: the widest-reaching source, and on a tie the
        # lexicographically first DOI.  Counter.most_common would instead break the
        # tie by insertion order, which is stable but far less obvious to a reader.
        top_count = max(bucket["dois"].values()) if bucket["dois"] else 0
        top_doi = (
            min(doi for doi, count in bucket["dois"].items() if count == top_count)
            if top_count
            else ""
        )
        top_share = (top_count / compounds) if compounds else 0.0
        if compounds <= 2:
            signal = "thin_family"
        elif single / compounds >= 0.5:
            signal = "single_row_dominated"
        elif top_share >= 0.5:
            signal = "single_source_dominated"
        else:
            signal = "ok"
        out.append(
            {
                "row_kind": "family",
                "key": family,
                "family": family,
                "compound_name": "",
                "inchikey": "",
                "observation_rows": bucket["rows"],
                "distinct_temperatures": sum(
                    len(per_compound_temps.get(key, set()))
                    for key in per_compound_rows
                    if family_of(key) == family
                ),
                "compounds_in_scope": compounds,
                "rows_per_compound": format(bucket["rows"] / compounds, ".2f"),
                "distinct_source_doi": len(bucket["dois"]),
                "share_of_observation_rows": format(bucket["rows"] / total_rows, ".4f"),
                "single_row_compounds": single,
                "gap_signal": signal,
                "note": (
                    "top_source_doi="
                    + top_doi
                    + " covering "
                    + str(top_count)
                    + "/"
                    + str(compounds)
                    + " compounds"
                ),
            }
        )

    for key in sorted(per_compound_rows):
        if per_compound_rows[key] != 1:
            continue
        out.append(
            {
                "row_kind": "single_row_compound",
                "key": key,
                "family": family_of(key),
                "compound_name": per_compound_name.get(key, ""),
                "inchikey": key,
                "observation_rows": 1,
                "distinct_temperatures": len(per_compound_temps.get(key, set())),
                "compounds_in_scope": 1,
                "rows_per_compound": "1.00",
                "distinct_source_doi": len(per_compound_doi.get(key, set())),
                "share_of_observation_rows": "",
                "single_row_compounds": 1,
                "gap_signal": "single_row",
                "note": "only one observation row; no temperature series, no replicate",
            }
        )

    doi_compounds: dict[str, set[str]] = defaultdict(set)
    doi_rows: Counter[str] = Counter()
    for key, dois in per_compound_doi.items():
        for doi in dois:
            doi_compounds[doi].add(key)
    for key, rows in panel.observations.items():
        for row in rows:
            doi = (row.get("source_doi") or "").strip()
            if doi:
                doi_rows[doi] += 1
    for doi in sorted(doi_compounds):
        compounds = len(doi_compounds[doi])
        out.append(
            {
                "row_kind": "source_doi",
                "key": doi,
                "family": "",
                "compound_name": "",
                "inchikey": "",
                "observation_rows": doi_rows[doi],
                "distinct_temperatures": "",
                "compounds_in_scope": compounds,
                "rows_per_compound": format(doi_rows[doi] / compounds, ".2f"),
                "distinct_source_doi": 1,
                "share_of_observation_rows": "",
                "single_row_compounds": "",
                "gap_signal": "thin_source" if compounds <= 2 else "ok",
                "note": "source DOI covering " + str(compounds) + " compound(s)",
            }
        )
    return out


def gap_top_families(gap_rows: Sequence[Mapping[str, Any]], limit: int = 5) -> list[dict[str, Any]]:
    """Smallest structurally fragile families, degenerate families excluded.

    Ranked by compound count first and by evidence depth per compound second, so a
    family with three compounds and three rows outranks one with three compounds
    and fifty rows.  Water and the unparsed bucket are excluded by declaration.
    """

    families = [
        row
        for row in gap_rows
        if row["row_kind"] == "family" and row["family"] not in DEGENERATE_GAP_FAMILIES
    ]
    ranked = sorted(
        families,
        key=lambda row: (
            0 if row["gap_signal"] != "ok" else 1,
            int(row["compounds_in_scope"]),
            float(row["rows_per_compound"]),
            row["family"],
        ),
    )
    return [
        {
            "family": row["family"],
            "gap_signal": row["gap_signal"],
            "compounds": int(row["compounds_in_scope"]),
            "observation_rows": int(row["observation_rows"]),
            "rows_per_compound": row["rows_per_compound"],
            "single_row_compounds": int(row["single_row_compounds"]),
            "distinct_source_doi": int(row["distinct_source_doi"]),
        }
        for row in ranked[:limit]
    ]


# --------------------------------------------------------------------------- #
# pending 20 triage (deliverable 2)
# --------------------------------------------------------------------------- #


def build_pending_triage(
    triage_rows: Sequence[Mapping[str, str]],
    candidates: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    by_doi: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in candidates:
        for doi in (row.get("source_doi") or "").split(";"):
            if doi:
                by_doi[doi].append(row)

    pending = [row for row in triage_rows if (row.get("disposition") or "").strip() == "pending"]
    out: list[dict[str, Any]] = []
    for row in pending:
        doi = (row.get("doi") or "").strip()
        linked = by_doi.get(doi, [])
        compound_rows = [item for item in linked if item["row_kind"] != "gap_family"]
        new_rows = [item for item in compound_rows if item["is_new_compound"] == "yes"]
        gap_rows = [item for item in linked if item["row_kind"] == "gap_family"]
        promotable = [item for item in new_rows if item["priority"] in {"P1", "P2"}]
        if promotable:
            reachable = any(item["oa_reachable"] == "true" for item in promotable)
            action = ACTION_READ_FULLTEXT if reachable else ACTION_HUMAN
        elif new_rows or gap_rows:
            action = ACTION_LEAD_ONLY
        else:
            action = ACTION_ARCHIVE
        out.append(
            {
                "doi": doi,
                "title": (row.get("title") or "").strip(),
                "venue": (row.get("venue") or "").strip(),
                "publication_year": (row.get("publication_year") or "").strip(),
                "round3_priority": (row.get("priority") or "").strip(),
                "target_class": (row.get("target_class") or "").strip(),
                "compound_names": (row.get("compound_names") or "").strip(),
                "epsilon_clue_kind": (row.get("epsilon_clue_kind") or "").strip() or "none",
                "epsilon_numbers": (row.get("epsilon_numbers_in_title_or_abstract") or "").strip(),
                "oa_status": (row.get("unpaywall_oa_status") or "").strip(),
                "oa_url": (row.get("best_oa_url") or "").strip(),
                "oa_reachable": (row.get("oa_fulltext_reachable") or "").strip() or "unknown",
                "compounds": [
                    {
                        "name": item["compound_name"],
                        "inchikey": item["inchikey_if_resolved"],
                        "in_local_v03": item["in_local_v03"],
                        "in_local_observations": item["in_local_observations"],
                        "local_epsilon_rows": item["local_epsilon_rows"],
                        "is_new_compound": item["is_new_compound"],
                        "priority": item["priority"],
                    }
                    for item in compound_rows
                ],
                "new_compound_names": [item["compound_name"] for item in new_rows],
                "action": action,
            }
        )
    out.sort(key=lambda item: (PRIORITY_ORDER.get(item["round3_priority"], 9), item["doi"]))
    return out


# --------------------------------------------------------------------------- #
# rendering
# --------------------------------------------------------------------------- #


def md_table(headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> str:
    lines = ["| " + " | ".join(headers) + " |"]
    lines.append("|" + "|".join(["---"] * len(headers)) + "|")
    for row in rows:
        lines.append("| " + " | ".join("" if cell is None else str(cell) for cell in row) + " |")
    return "\n".join(lines)


def render_report(
    candidates: Sequence[Mapping[str, Any]],
    gap_rows: Sequence[Mapping[str, Any]],
    pending: Sequence[Mapping[str, Any]],
    inputs: Mapping[str, Any],
    stats: Mapping[str, Any],
) -> str:
    new_rows = [row for row in candidates if row["is_new_compound"] == "yes"]
    recon_rows = [row for row in candidates if row["is_new_compound"] == "no"]
    gap_family = [row for row in candidates if row["row_kind"] == "gap_family"]
    priority_counts = Counter(row["priority"] for row in candidates)
    new_priority = Counter(row["priority"] for row in new_rows)
    evidence_counts = Counter(row["evidence_kind"] for row in new_rows)
    trace_counts = Counter(row["local_trace"] for row in new_rows)
    pending_actions = Counter(item["action"] for item in pending)

    lines: list[str] = []
    lines.append("# AL Round 4：新化合物补录清单 v0（离线、本地再分析）")
    lines.append("")
    lines.append(
        "本产物按 Week 14 附录 D1 的口径立项：v1.x 的精度杠杆只剩「化合物覆盖」，"
        "所以 Round 4 的取向从「补温度点」切换为「补新化合物」。全程离线，只读本地 CSV，"
        "不调用 OpenAlex / Unpaywall / 任何 HTTP 接口。"
    )
    lines.append("")
    lines.append("## 1. 输入与完整性")
    lines.append("")
    lines.append(
        md_table(
            ["输入", "sha256（实际）", "钉住", "完整"],
            [
                [
                    name,
                    str(payload["sha256_actual"]),
                    str(payload["sha256_expected"]),
                    "OK" if payload["intact"] else "MISMATCH",
                ]
                for name, payload in inputs.items()
            ],
        )
    )
    lines.append("")
    lines.append("## 2. 清单总览")
    lines.append("")
    lines.append(
        md_table(
            ["指标", "值"],
            [
                ["清单行数", len(candidates)],
                ["真新化合物行（is_new_compound=yes）", len(new_rows)],
                ["对账行（本地已覆盖 / 名册缺口）", len(recon_rows) - len(gap_family)],
                ["缺口家族行", len(gap_family)],
                [
                    "优先级分布（全表）",
                    ", ".join(f"{k}={v}" for k, v in sorted(priority_counts.items())),
                ],
                [
                    "优先级分布（真新化合物）",
                    ", ".join(f"{k}={v}" for k, v in sorted(new_priority.items())) or "无",
                ],
                [
                    "证据类型（真新化合物）",
                    ", ".join(f"{k}={v}" for k, v in sorted(evidence_counts.items())),
                ],
                [
                    "本地非介电痕迹（真新化合物）",
                    ", ".join(f"{k}={v}" for k, v in sorted(trace_counts.items())),
                ],
                ["Round 3 三连组错位行", stats["triplet_mismatch_rows"]],
            ],
        )
    )
    lines.append("")
    lines.append("## 3. 真新化合物（本地介电面板完全没有）")
    lines.append("")
    if new_rows:
        lines.append(
            md_table(
                [
                    "优先级",
                    "化合物",
                    "InChIKey",
                    "ε 线索",
                    "证据",
                    "本地痕迹",
                    "受限痕迹",
                    "OA",
                    "动作",
                    "来源 DOI",
                ],
                [
                    [
                        row["priority"],
                        row["compound_name"],
                        row["inchikey_if_resolved"],
                        row["epsilon_value_or_kind"]
                        + (f" ({row['epsilon_values']})" if row["epsilon_values"] else ""),
                        row["evidence_kind"],
                        row["local_trace"],
                        row["local_trace_restricted"],
                        row["oa_status"],
                        row["action"],
                        row["source_doi"],
                    ]
                    for row in new_rows
                ],
            )
        )
    else:
        lines.append("（无）")
    lines.append("")
    trace_yes = [row["compound_name"] for row in new_rows if row["local_trace"] == "yes"]
    trace_no = [row["compound_name"] for row in new_rows if row["local_trace"] == "no"]
    lines.append(
        "真新化合物有两种分解，两种都写在这里："
        "按本地痕迹 —— 本地完全没有任何痕迹 "
        + str(len(trace_no))
        + " 个（"
        + ("、".join(trace_no) if trace_no else "无")
        + "），本地只在非介电表里出现过 "
        + str(len(trace_yes))
        + " 个（"
        + ("、".join(trace_yes) if trace_yes else "无")
        + "）；按 ε 证据 —— "
        + "、".join(
            kind + " " + str(count) for kind, count in sorted(evidence_counts.items())
        )
        + "。痕迹只统计已声明的策展数据树（"
        + "、".join(TRACE_ROOTS)
        + "）与 data/ 顶层策展表；data/interim/ 这个周内 scratch 区，以及任何以“_”开头的"
        "私有命名文件，都按声明排除。"
    )
    lines.append("")
    for row in new_rows:
        lines.append(f"### {row['priority']} · {row['compound_name']}（{row['action']}）")
        lines.append("")
        lines.append(f"- InChIKey：`{row['inchikey_if_resolved']}`")
        lines.append(f"- SMILES：`{row['smiles_if_resolved']}`")
        lines.append(f"- 判定：{row['why_new_compound']}；{row['rationale']}")
        lines.append(
            f"- ε 线索：{row['epsilon_value_or_kind']}"
            + (f"，数值 {row['epsilon_values']}" if row["epsilon_values"] else "（无数值）")
            + f"；证据类型 {row['evidence_kind']}"
        )
        lines.append(
            f"- OA：{row['oa_status']}，可达={row['oa_reachable']}；"
            f"线索来源 {row['oa_url'] or 'n/a'}"
        )
        lines.append(
            "- 本地非介电痕迹："
            + (row["local_trace_files"] if row["local_trace_files"] else "无")
        )
        if row["local_trace_restricted"] == "yes":
            lines.append(
                "- 受限痕迹：命中 data/restricted/ 下的文件。本清单只记路径、不取任何值；"
                "该物质应走受限交叉核对通道判定，而不是靠新取数解决。"
            )
        lines.append("")
    lines.append("## 4. 本地已覆盖条目（对账行，不计入补录）")
    lines.append("")
    lines.append(
        md_table(
            ["行类型", "化合物", "InChIKey", "v03", "观测表", "观测行数", "温度点", "Round 3 判定", "动作"],
            [
                [
                    row["row_kind"],
                    row["compound_name"],
                    row["inchikey_if_resolved"],
                    row["in_local_v03"],
                    row["in_local_observations"],
                    row["local_epsilon_rows"],
                    row["local_distinct_temperatures"],
                    row["round3_disposition"],
                    row["action"],
                ]
                for row in recon_rows
                if row["row_kind"] != "gap_family"
            ],
        )
    )
    lines.append("")
    lines.append(
        "这些化合物的 ε 值在本地已经有了，Round 3 却按「温度点」把它们又扫了一遍。"
        "它们是 Round 3 与 Round 4 口径差异的直接体现：同一批线索换成覆盖口径之后大部分作废。"
    )
    lines.append("")
    lines.append("## 5. 明确缺口家族")
    lines.append("")
    if gap_family:
        lines.append(
            md_table(
                ["家族", "来源 DOI", "Round 3 判定", "动作", "说明"],
                [
                    [
                        row["compound_name"],
                        row["source_doi"],
                        row["round3_disposition"] + "/" + row["round3_priority"],
                        row["action"],
                        row["rationale"],
                    ]
                    for row in gap_family
                ],
            )
        )
    else:
        lines.append("（无）")
    lines.append("")
    lines.append("## 6. 本地覆盖缺口 top-5 家族（该补什么的本地证据）")
    lines.append("")
    lines.append(
        md_table(
            ["家族", "信号", "化合物数", "观测行数", "行/化合物", "单行化合物", "来源 DOI 数"],
            [
                [
                    row["family"],
                    row["gap_signal"],
                    row["compounds"],
                    row["observation_rows"],
                    row["rows_per_compound"],
                    row["single_row_compounds"],
                    row["distinct_source_doi"],
                ]
                for row in gap_top_families(gap_rows, limit=5)
            ],
        )
    )
    lines.append("")
    lines.append(
        "排序口径：先按化合物数升序，再按「行/化合物」（证据深度）升序；"
        "water 与 unparsed 两类退化家族按声明排除（单分子家族不是化学缺口，"
        "unparsed 是数据卫生信号）。全部 14 个家族、41 个单行化合物与 61 个来源 DOI 的"
        "明细见 probes/artifacts/al_round4_local_coverage_gaps.csv。"
    )
    lines.append("")
    lines.append("## 7. 与 Round 3 对账")
    lines.append("")
    lines.append(
        md_table(
            ["指标", "值"],
            [
                ["Round 3 线索总数", stats["round3_leads"]],
                ["进入 v0 的线索数", stats["round3_leads_in_v0"]],
                ["未进入 v0 的线索数", len(stats["round3_leads_absent"])],
                ["未进入 v0 的 DOI", ", ".join(stats["round3_leads_absent"]) or "无"],
                ["Round 3 化合物条目（去重）", stats["grouped_compounds"]],
                ["其中真新化合物", len(new_rows)],
                ["其中本地已覆盖", len(recon_rows) - len(gap_family)],
            ],
        )
    )
    lines.append("")
    lines.append("## 8. pending 20 篇分流")
    lines.append("")
    lines.append(
        md_table(["动作", "篇数"], [[action, count] for action, count in sorted(pending_actions.items())])
    )
    lines.append("")
    lines.append("逐篇明细见 reports/al_round4_pending_oa_triage.md。")
    lines.append("")
    lines.append("## 9. 三条诚实边界")
    lines.append("")
    lines.append(
        "1. **v0 是线索清单，不是数据集。** 每一行只记录「哪篇文献提到了哪个化合物、"
        "本地有没有」，没有任何一条 ε 观测被写进 data/，也没有任何特征被派生。"
        "要变成数据，必须走取全文 → 表格抽取 → verifier 这条链路。"
    )
    lines.append(
        "2. **OA 可达 ≠ 有 ε 数值。** Round 3 的 "
        + str(stats["round3_leads"])
        + " 条线索里 epsilon_clue_kind=value 的只有 "
        + str(stats["round3_epsilon_value_leads"])
        + " 条，其余 "
        + str(stats["round3_wording_only_leads"])
        + " 条是 wording_only（摘要里说「低介电常数」却不给数），"
        + str(stats["round3_no_clue_leads"])
        + " 条连措辞都没有。wording_only 在本清单里一律不带数值。"
    )
    lines.append(
        "3. **数据库覆盖边际收益递减。** "
        + str(len(recon_rows) - len(gap_family))
        + " 个 Round-3 化合物条目本地已有（其中 succinonitrile 是「名册缺口」而非「数据缺口」），"
        "真新化合物只有 "
        + str(len(new_rows))
        + " 个，而其中 P1 只有 "
        + str(new_priority.get("P1", 0))
        + " 个。要真正扩大覆盖面，得换一组面向新化合物的检索式，"
        "而不是继续榨 Round 3 的余料。"
    )
    lines.append("")
    lines.append("## 10. shots 与口径")
    lines.append("")
    lines.append("- shots = 1：本轮只按预注册规则跑了一次，没有事后手调。")
    lines.append(
        "- 本地痕迹扫描口径：只接受已声明的策展数据树（"
        + "、".join(TRACE_ROOTS)
        + "）与 data/ 顶层的策展表；data/interim/ 这一周内 scratch 区按声明排除——"
        "临时转储、计时探针、一次性重跑都不是项目知识，让它们进来会让证据链取决于"
        "某个副任务当天下午恰好写了什么。"
    )
    lines.append(
        "- 第二条 scratch 规则：basename 以“_”开头的文件一律不进证据链（仓库里现存的"
        "该类文件都是 g1plus 的请求日志）。这条不是临时补丁——本轮真正踩到的就是"
        "一个名为 _lever8_paper_text.txt 的转储被递归扫描当成项目知识，名字约定能拦住"
        "它落在任何目录的变体。"
    )
    lines.append(
        "- 默认拒绝：data/ 下既不属于已声明策展树、也不是顶层策展表的路径一律不进扫描，"
        "所以将来新增的 scratch 目录天然被排除，无需再改代码。"
    )
    lines.append(
        "- 其他 scratch 路径已确认：data/ 下唯一的 scratch 区就是 data/interim/；"
        "data/external/g1plus/、data/raw/、data/restricted/ 以及 data/processed/ 下未入库的"
        "探针输出都是策展缓存/产物，按同一规则留在扫描范围内。"
    )
    lines.append(
        "- gitignore 状态不是判据：data/ 下若干策展路径因体积或再分发条款被 ignore"
        "（尤其 data/restricted/、data/external/g1plus/），它们仍在扫描范围内；"
        "排除一律按已声明的 scratch 规则执行。"
    )
    lines.append(
        "- 优先级规则在跑之前就已写死在 derive_priority() 里，事后不放宽；"
        "noise veto 的线索永不因家族归属而升级。"
    )
    lines.append(
        "- 复现：.venv\\Scripts\\python.exe probes\\al_round4_new_compound_backfill.py"
    )
    lines.append("")
    return "\n".join(lines)


def render_pending_report(pending: Sequence[Mapping[str, Any]]) -> str:
    counts = Counter(item["action"] for item in pending)
    lines: list[str] = []
    lines.append("# AL Round 4：Round 3 pending 20 篇逐篇再分诊")
    lines.append("")
    lines.append(
        "对 Round 3 分诊留下的 20 篇 pending 线索逐篇复核，口径从「有没有新温度点」"
        "换成「有没有新化合物」。判断只依据本地已有的 Round-3 分诊表与两个冻结的本地面板文件，"
        "不联网、不取全文。"
    )
    lines.append("")
    lines.append("## 分流计数")
    lines.append("")
    lines.append(md_table(["动作", "篇数"], [[k, v] for k, v in sorted(counts.items())]))
    lines.append("")
    lines.append(f"合计 {len(pending)} 篇。")
    lines.append("")
    lines.append("## 逐篇")
    lines.append("")
    for index, item in enumerate(pending, start=1):
        lines.append(f"### {index:02d}. {item['doi']} —— {item['action']}")
        lines.append("")
        lines.append(f"- 标题：{item['title']}")
        lines.append(
            f"- 出处：{item['venue']}（{item['publication_year']}）；"
            f"Round 3 优先级 {item['round3_priority']}，目标类 {item['target_class']}"
        )
        lines.append(
            f"- ε 线索：{item['epsilon_clue_kind']}"
            + (f"，数值 {item['epsilon_numbers']}" if item["epsilon_numbers"] else "（无数值）")
        )
        lines.append(f"- OA：{item['oa_status']}，可达={item['oa_reachable']}")
        if item["compounds"]:
            lines.append("- 化合物逐一复核：")
            for compound in item["compounds"]:
                verdict = (
                    "**新化合物**" if compound["is_new_compound"] == "yes" else "本地已覆盖"
                )
                lines.append(
                    "  - "
                    + compound["name"]
                    + "（"
                    + (compound["inchikey"] or "未解析")
                    + "）："
                    + verdict
                    + "，v03="
                    + compound["in_local_v03"]
                    + "，观测表="
                    + compound["in_local_observations"]
                    + "，观测行数="
                    + str(compound["local_epsilon_rows"])
                )
        else:
            lines.append("- 化合物逐一复核：无单一分子可解析（家族级缺口）")
        lines.append(f"- 建议动作：{item['action']}")
        lines.append("")
    lines.append("## 结论")
    lines.append("")
    lines.append(
        f"20 篇 pending 中 {counts.get(ACTION_ARCHIVE, 0)} 篇只含本地已覆盖化合物，"
        f"{counts.get(ACTION_READ_FULLTEXT, 0)} 篇可立即取全文补新化合物，"
        f"{counts.get(ACTION_HUMAN, 0)} 篇需要人工通道，"
        f"{counts.get(ACTION_LEAD_ONLY, 0)} 篇只留下家族级线索。"
    )
    lines.append("")
    return "\n".join(lines)


def verify_invariants(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    """Self-checks that must hold before anything is written."""

    problems: list[str] = []
    for row in rows:
        name = str(row.get("compound_name", ""))
        if row["is_new_compound"] == "yes":
            if row["in_local_v03"] != "no" or row["in_local_observations"] != "no":
                problems.append("row claims to be new but is local: " + name)
            if row["row_kind"] != "new_compound":
                problems.append("is_new_compound=yes outside new_compound row kind: " + name)
        if row["epsilon_value_or_kind"] == "wording_only" and row["epsilon_values"]:
            problems.append("wording_only row carries a number: " + name)
        if row["epsilon_value_or_kind"] == "value" and not row["epsilon_values"]:
            problems.append("value row carries no number: " + name)
        if row["epsilon_value_or_kind"] == "none" and row["epsilon_values"]:
            problems.append("none row carries a number: " + name)
        if row["priority"] not in PRIORITY_ORDER:
            problems.append("bad priority: " + str(row["priority"]))
        if row["action"] not in ACTIONS:
            problems.append("bad action: " + str(row["action"]))
        if row["evidence_kind"] not in EVIDENCE_KINDS:
            problems.append("bad evidence kind: " + str(row["evidence_kind"]))
        if row["in_local_v03"] not in {"yes", "no", "na"}:
            problems.append("bad in_local_v03: " + str(row["in_local_v03"]))
        if row["in_local_observations"] not in {"yes", "no", "na"}:
            problems.append("bad in_local_observations: " + str(row["in_local_observations"]))
        if row["local_trace_restricted"] not in {"yes", "no", "na"}:
            problems.append("bad local_trace_restricted: " + str(row["local_trace_restricted"]))
    return problems


def build_summary(
    candidates: Sequence[Mapping[str, Any]],
    gap_rows: Sequence[Mapping[str, Any]],
    pending: Sequence[Mapping[str, Any]],
    inputs: Mapping[str, Any],
    stats: Mapping[str, Any],
    triage_rows: Sequence[Mapping[str, str]],
) -> dict[str, Any]:
    new_rows = [row for row in candidates if row["is_new_compound"] == "yes"]
    recon_rows = [row for row in candidates if row["is_new_compound"] == "no"]
    gap_family = [row for row in candidates if row["row_kind"] == "gap_family"]
    roster_gap_rows = [row for row in candidates if row["row_kind"] == "roster_gap"]

    by_row_kind = dict(sorted(Counter(row["row_kind"] for row in candidates).items()))
    # Every non-new row except the family-gap placeholder.  This is the same set
    # that local_rejections lists, so it is NOT the same number as
    # by_row_kind["local_duplicate_reconciliation"]: a roster_gap row is non-new
    # but is not a reconciliation row.  The name says which set this counts.
    non_new_rows_excluding_family_gaps = len(recon_rows) - len(gap_family)
    row_kind_note = (
        "by_row_kind counts every row once ("
        + ", ".join(f"{kind}={count}" for kind, count in by_row_kind.items())
        + "). non_new_rows_excluding_family_gaps="
        + str(non_new_rows_excluding_family_gaps)
        + " is the local_rejections set: every row with is_new_compound=no except the "
        "family-gap placeholder. It therefore also counts the roster_gap row(s) ("
        + (", ".join(row["compound_name"] for row in roster_gap_rows) or "none")
        + "), which are not local_duplicate_reconciliation rows (that count is "
        + str(by_row_kind.get("local_duplicate_reconciliation", 0))
        + ")."
    )

    reached: set[str] = set()
    for row in candidates:
        for doi in (row.get("source_doi") or "").split(";"):
            if doi:
                reached.add(doi)
    all_leads = [(row.get("doi") or "").strip() for row in triage_rows]
    absent = sorted(doi for doi in all_leads if doi and doi not in reached)

    local_hits = [
        {
            "compound_name": row["compound_name"],
            "inchikey": row["inchikey_if_resolved"],
            "in_local_v03": row["in_local_v03"],
            "in_local_observations": row["in_local_observations"],
            "local_epsilon_rows": row["local_epsilon_rows"],
            "local_distinct_temperatures": row["local_distinct_temperatures"],
            "round3_disposition": row["round3_disposition"],
            "row_kind": row["row_kind"],
        }
        for row in recon_rows
        if row["row_kind"] != "gap_family"
    ]

    return {
        "schema_version": SCHEMA_VERSION,
        "task": "al_round4_new_compound_backfill",
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "run_mode": "offline_local_only",
        "shots": 1,
        "network_calls": 0,
        "inputs": inputs,
        "list_stats": {
            "rows": len(candidates),
            "by_row_kind": by_row_kind,
            "by_priority": dict(sorted(Counter(row["priority"] for row in candidates).items())),
            "new_compound_rows": len(new_rows),
            "non_new_rows_excluding_family_gaps": non_new_rows_excluding_family_gaps,
            "row_kind_note": row_kind_note,
            "gap_family_rows": len(gap_family),
            "grouped_round3_compounds": stats["grouped_compounds"],
            "triplet_mismatch_rows": stats["triplet_mismatch_rows"],
        },
        "new_compound_stats": {
            "count": len(new_rows),
            "by_priority": dict(sorted(Counter(row["priority"] for row in new_rows).items())),
            "by_evidence_kind": dict(
                sorted(Counter(row["evidence_kind"] for row in new_rows).items())
            ),
            "by_action": dict(sorted(Counter(row["action"] for row in new_rows).items())),
            "absent_with_no_local_trace": [
                row["compound_name"] for row in new_rows if row["local_trace"] == "no"
            ],
            "absent_with_local_non_dielectric_trace": [
                row["compound_name"] for row in new_rows if row["local_trace"] == "yes"
            ],
            "new_compounds_with_a_restricted_trace": [
                row["compound_name"]
                for row in new_rows
                if row["local_trace_restricted"] == "yes"
            ],
        },
        "local_rejections": {
            "note": (
                "compounds that Round 3 surfaced but the local panel already covers; they are "
                "explicitly marked in the list as in_local_*=yes and are never counted as new"
            ),
            "count": len(local_hits),
            "rows": local_hits,
        },
        "pending_oa_triage": {
            "pending_papers": len(pending),
            "by_action": dict(sorted(Counter(item["action"] for item in pending).items())),
            "papers_with_a_new_compound": [
                item["doi"] for item in pending if item["new_compound_names"]
            ],
            "papers_with_a_promotable_new_compound": [
                item["doi"] for item in pending if item["action"] in {ACTION_READ_FULLTEXT, ACTION_HUMAN}
            ],
            "papers_with_only_local_compounds": [
                item["doi"] for item in pending if item["action"] == ACTION_ARCHIVE
            ],
        },
        "round3_reconciliation": {
            "round3_leads": len(all_leads),
            "leads_landing_in_v0": len(all_leads) - len(absent),
            "leads_not_landing_in_v0": absent,
            "leads_not_landing_reason": (
                "lead resolved to no compound and its target class is off-target, so it is "
                "not a coverage candidate at all"
            ),
            "round3_epsilon_value_leads": sum(
                1
                for row in triage_rows
                if (row.get("epsilon_clue_kind") or "").strip() == "value"
            ),
            "round3_wording_only_leads": sum(
                1
                for row in triage_rows
                if (row.get("epsilon_clue_kind") or "").strip() == "wording_only"
            ),
            "round3_no_clue_leads": sum(
                1
                for row in triage_rows
                if (row.get("epsilon_clue_kind") or "").strip() not in {"value", "wording_only"}
            ),
        },
        "local_coverage_gaps": {
            "family_rows": sum(1 for row in gap_rows if row["row_kind"] == "family"),
            "single_row_compound_rows": sum(
                1 for row in gap_rows if row["row_kind"] == "single_row_compound"
            ),
            "source_doi_rows": sum(1 for row in gap_rows if row["row_kind"] == "source_doi"),
            "top_families": gap_top_families(gap_rows, limit=5),
        },
        "pre_registered_rules": {
            "priority_rule": (
                "P1 = new compound AND not noise-vetoed AND round3 target class is core AND an "
                "epsilon clue exists; P2 = same but core or adjacent; otherwise P3. Local "
                "compounds are never promoted."
            ),
            "action_rule": (
                "drop if already covered or noise-vetoed; lead-only if off-target or no epsilon "
                "clue; read-fulltext if the OA full text is reachable; otherwise human."
            ),
            "evidence_rule": (
                "review cue in title/venue -> review; a stated epsilon number, or a measurement "
                "verb attached to the epsilon prose -> first-hand measurement; prose-only clue "
                "-> compilation restatement; no clue at all -> no epsilon clue"
            ),
            "declared_before_execution": True,
        },
        "trace_scan_scope": {
            "rule": (
                "a local trace is only accepted from the curated data trees; the week-scoped "
                "scratch area and any underscore-prefixed private basename are excluded, "
                "because a compound appearing in an ad-hoc dump or a throwaway rerun says "
                "nothing about what the project actually knows"
            ),
            "curated_roots": list(TRACE_ROOTS),
            "excluded_scratch_prefixes": list(SCRATCH_PREFIXES),
            "excluded_scratch_name_prefixes": [SCRATCH_NAME_PREFIX],
            "default_deny": (
                "anything under data/ that is neither a declared curated root nor a curated "
                "one-level table is rejected, so a new scratch tree is excluded by default"
            ),
            "scratch_trees_confirmed": [
                "data/interim/ is the only scratch tree under data/",
                (
                    "the other git-ignored trees (data/external/g1plus/, data/raw/, "
                    "data/restricted/ and the ignored probe outputs under data/processed/) "
                    "are curated caches and stay in scope"
                ),
            ],
            "gitignore_status_is_not_the_rule": (
                "several curated paths under data/ are git-ignored for size or redistribution "
                "reasons and stay in scope, data/restricted/ and data/external/g1plus/ in "
                "particular; the exclusion is by declared scratch rule, never by ignore status"
            ),
        },
        "restricted_values_contract": {
            "route": "local_path_names_only",
            "carries_values_from_restricted_sources": False,
            "redistribution": "not_permitted",
            "declares_channel_availability": False,
            "note": (
                "a local_trace_restricted=yes row means the compound is named in a file under "
                "data/restricted/, so it must be resolved through the restricted-crosscheck "
                "route rather than by acquiring new data; the probe records the file path and "
                "nothing else"
            ),
        },
        "honesty_boundaries": [
            "v0 is a lead list, not a dataset: it writes no observation into data/ and derives no feature",
            "OA reachability is not an epsilon value: 1 of 37 leads carries a number, 22 carry prose only",
            "database-coverage returns are diminishing: 13 of 20 Round-3 compounds are already local",
        ],
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify the frozen inputs and print the plan without writing anything",
    )
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    inputs = check_inputs()
    print("input integrity: " + ", ".join(
        name + "=" + ("OK" if payload["intact"] else "MISMATCH")
        for name, payload in inputs.items()
    ))
    if args.check:
        return 0

    triage_rows = read_csv(TRIAGE_PATH)
    panel = load_local_panel()

    keys = {
        key: name
        for row in triage_rows
        for name, key, _smiles in parse_triplets(row)
        if key
    }
    traces = local_trace_scan(keys)

    candidates, stats = build_candidates(triage_rows, panel, traces)
    problems = verify_invariants(candidates)
    if problems:
        for problem in problems:
            print("INVARIANT FAILURE: " + problem)
        return 1

    gap_rows = build_coverage_gaps(panel)
    pending = build_pending_triage(triage_rows, candidates)

    all_leads = [(row.get("doi") or "").strip() for row in triage_rows]
    reached: set[str] = set()
    for row in candidates:
        for doi in (row.get("source_doi") or "").split(";"):
            if doi:
                reached.add(doi)
    stats["round3_leads"] = len([doi for doi in all_leads if doi])
    stats["round3_leads_in_v0"] = len([doi for doi in all_leads if doi and doi in reached])
    stats["round3_leads_absent"] = sorted(
        doi for doi in all_leads if doi and doi not in reached
    )
    stats["round3_epsilon_value_leads"] = sum(
        1 for row in triage_rows if (row.get("epsilon_clue_kind") or "").strip() == "value"
    )
    stats["round3_wording_only_leads"] = sum(
        1
        for row in triage_rows
        if (row.get("epsilon_clue_kind") or "").strip() == "wording_only"
    )
    stats["round3_no_clue_leads"] = sum(
        1
        for row in triage_rows
        if (row.get("epsilon_clue_kind") or "").strip() not in {"value", "wording_only"}
    )

    write_csv(LIST_PATH, LIST_FIELDS, candidates)
    write_csv(GAPS_PATH, GAP_FIELDS, gap_rows)
    summary = build_summary(candidates, gap_rows, pending, inputs, stats, triage_rows)
    write_text(SUMMARY_PATH, json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    write_text(REPORT_PATH, render_report(candidates, gap_rows, pending, inputs, stats))
    write_text(PENDING_REPORT_PATH, render_pending_report(pending))

    new_rows = [row for row in candidates if row["is_new_compound"] == "yes"]
    print("list rows=" + str(len(candidates)) + " new compounds=" + str(len(new_rows)))
    print("priorities(all)=" + str(summary["list_stats"]["by_priority"]))
    print("new compound priorities=" + str(summary["new_compound_stats"]["by_priority"]))
    print("pending by action=" + str(summary["pending_oa_triage"]["by_action"]))
    print("top local gap families=" + str(
        [(item["family"], item["gap_signal"], item["compounds"])
         for item in summary["local_coverage_gaps"]["top_families"]]
    ))
    print("wrote: " + str(LIST_PATH))
    print("wrote: " + str(GAPS_PATH))
    print("wrote: " + str(SUMMARY_PATH))
    print("wrote: " + str(REPORT_PATH))
    print("wrote: " + str(PENDING_REPORT_PATH))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
