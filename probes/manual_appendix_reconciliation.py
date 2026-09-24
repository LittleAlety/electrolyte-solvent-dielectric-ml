"""Re-derive the Appendix I/J molecular-roster claims from the frozen CSVs.

Appendix I section A concluded that propylene carbonate, ethylene carbonate,
the three glymes, glutaronitrile and 3-methoxypropionitrile were "absent from
all three versions".  Re-deriving that list by InChIKey shows that part of it
was a false negative: `data/dielectric_v01.csv` already carried the three
glymes and both dinitriles, but under IUPAC-type names such as
"2,5,8-trioxanonane" and "hexanedinitrile", so any search for "diglyme" or
"adiponitrile" returned nothing.

This reconciliation is therefore keyed on InChIKey, never on a common name, and
records for every target whether a common-name search would have found the row.
That column is the guard against repeating the false negative; the alias
registry it reads is `data/reference/dielectric_molecule_aliases.csv`.

A claim is only re-affirmed when the *whole* claim reproduces.  "PC absent from
three versions and added later" requires absence in v0.1, v0.2 **and** v0.3.1
plus a first sighting in v0.3.2; the EC claim additionally requires the row to
be in the extended temperature band.  A missing roster is refuted as soon as
any listed molecule is present anywhere, not only when all of them are.
"""

from __future__ import annotations

import argparse
import collections
import csv
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from electrolyte_ml.exporting import canonical_text_sha256

DATASET_VERSIONS = (
    ("v0.1", "data/dielectric_v01.csv"),
    ("v0.2", "data/dielectric_v02.csv"),
    ("v0.3.1", "data/dielectric_v031.csv"),
    ("v0.3.2", "data/dielectric_v032.csv"),
    ("v0.3", "data/dielectric_v03.csv"),
)
ALIAS_REGISTRY = "data/reference/dielectric_molecule_aliases.csv"
CURRENT_VERSION = "v0.3"
CLAIMED_ABSENT_VERSIONS = ("v0.1", "v0.2", "v0.3.1")

# The five Appendix I section A roster groups, in the wording the review used.
TARGET_GROUPS = {
    "pc": ("RUOJZAUFBMNUDX-UHFFFAOYSA-N",),
    "ec": ("KMTRUDSVKNLOMY-UHFFFAOYSA-N",),
    "glymes": (
        "SBZXBUIDTXKZTM-UHFFFAOYSA-N",
        "YFNKIDBQEZZDLK-UHFFFAOYSA-N",
        "ZUHZGEOKBKGPSW-UHFFFAOYSA-N",
    ),
    "dinitriles": (
        "BTGRAWJCKBQKAO-UHFFFAOYSA-N",
        "ZTOMUSMDRMJOTH-UHFFFAOYSA-N",
    ),
    "mopn": ("OOWFYDWAMOKVSF-UHFFFAOYSA-N",),
}

# Tokens too generic to prove that a literature name finds a stored name:
# "methyl formate" must not count as findable inside "ethyl methyl carbonate".
GENERIC_NAME_TOKENS = frozenset(
    {
        "methyl",
        "ethyl",
        "propyl",
        "butyl",
        "dimethyl",
        "diethyl",
        "ether",
        "acid",
        "glycol",
        "carbonate",
        "formate",
        "acetate",
        "oxide",
        "sulfone",
    }
)

# Stale sentences that must not survive in the working manual.  A line counts as
# stale unless it carries the *specific* correction a reader needs, not merely a
# marker word: every record names the evidence tokens its correction must show.
STALE_MANUAL_PHRASES = (
    {
        "phrase": "PC（碳酸丙烯酯）三版本全部缺席",
        "requires_all_of": (),
        "correction_requires_all_of": ("已对账更正", "v0.3.2", "真缺口"),
        "why": "Appendix I A.1 asserted PC was absent from three versions.  That was "
        "true of v0.1/v0.2/v0.3.1 and was closed in v0.3.2, so the sentence is "
        "historical, not current.",
    },
    {
        "phrase": "diglyme/triglyme/tetraglyme",
        "requires_all_of": ("连带缺失",),
        "correction_requires_all_of": ("已对账更正", "假阴性", "2,5,8-trioxanonane"),
        "why": "The three glymes were never absent: they are stored under "
        "IUPAC-type names and are present from v0.1 onward.",
    },
    {
        "phrase": "extended band 为空",
        "requires_all_of": (),
        "correction_requires_all_of": ("已对账更正", "v0.3.2"),
        "why": "True of v0.3.1 (0 extended rows) and closed in v0.3.2 "
        "(1 extended row, ethylene carbonate).",
    },
)

DEFAULT_MANUAL = Path(
    "E:/大二/d2qc/电解液（长期项目）/文献调研/执行手册_探针与周计划.md"
)

DETAIL_FIELDS = (
    "name",
    "T_K",
    "dielectric",
    "evidence_level",
    "model_ready",
    "temperature_band",
    "conflict_status",
    "dataset_origin",
    "source_doi",
)


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def dataset_snapshot(path: Path) -> dict[str, object]:
    """Summarize one dataset version without trusting its row order or names."""

    rows = read_csv_rows(path)
    keys = [row["inchikey"] for row in rows]
    has_band = bool(rows) and "temperature_band" in rows[0]
    return {
        "path": path.relative_to(REPOSITORY_ROOT).as_posix(),
        "rows": len(rows),
        "columns": len(rows[0]) if rows else 0,
        "unique_inchikeys": len(set(keys)),
        "duplicate_inchikeys": sorted(
            key for key, count in collections.Counter(keys).items() if count > 1
        ),
        "canonical_sha256": canonical_text_sha256(path),
        "temperature_band_column_present": has_band,
        "temperature_band_counts": (
            dict(
                sorted(
                    collections.Counter(
                        row.get("temperature_band", "") for row in rows
                    ).items()
                )
            )
            if has_band
            else None
        ),
        "rows_by_inchikey": {row["inchikey"]: row for row in rows},
    }


def load_alias_registry(path: Path) -> list[dict[str, str]]:
    return read_csv_rows(path)


def name_tokens(value: str) -> set[str]:
    """Tokenize a molecule name for the common-name search diagnostic."""

    return {token for token in re.split(r"[^a-z0-9]+", value.lower()) if len(token) >= 4}


def name_search_safety(
    inchikey: str,
    aliases: list[dict[str, str]],
    snapshot: dict[str, object],
) -> dict[str, object]:
    """Report whether a literature common-name search would locate this molecule.

    The failure this guards against is a *token-disjoint* stored name: the
    glymes live in the dataset as "2,5,8-trioxanonane" and the dinitriles as
    "hexanedinitrile", so a search for "diglyme" or "adiponitrile" returns
    nothing even though the row exists.  A stored name that shares a distinctive
    token with a registered common name is not a risk; a shared generic token
    ("methyl", "carbonate") proves nothing and is not counted.
    """

    rows = snapshot["rows_by_inchikey"]  # type: ignore[index]
    row = rows.get(inchikey)  # type: ignore[union-attr]
    dataset_name = row["name"] if row else None
    dataset_tokens = name_tokens(dataset_name) if dataset_name else set()
    probes = []
    for alias in aliases:
        if alias["alias_type"] != "common_name":
            continue
        overlap = dataset_tokens & name_tokens(alias["alias"])
        probes.append(
            {
                "alias": alias["alias"],
                "token_overlap": sorted(overlap),
                "distinctive_token_overlap": sorted(overlap - GENERIC_NAME_TOKENS),
                "substring_of_dataset_name": bool(
                    dataset_name and alias["alias"].lower() in dataset_name.lower()
                ),
            }
        )
    matches = [
        probe
        for probe in probes
        if probe["substring_of_dataset_name"] or probe["distinctive_token_overlap"]
    ]
    return {
        "dataset_name": dataset_name,
        "common_name_registered": bool(probes),
        "common_name_probes": probes,
        "common_name_matches_dataset_name": bool(matches),
        # None means "cannot be judged": the registry recorded no literature name.
        "name_search_would_miss": (not matches) if probes else None,
    }


def build_reconciliation(
    repo_root: Path = REPOSITORY_ROOT,
    manual_path: Path | None = DEFAULT_MANUAL,
) -> dict[str, object]:
    snapshots = {
        label: dataset_snapshot(repo_root / relative)
        for label, relative in DATASET_VERSIONS
    }
    current = snapshots[CURRENT_VERSION]
    aliases_by_key: dict[str, list[dict[str, str]]] = collections.defaultdict(list)
    registry_rows = load_alias_registry(repo_root / ALIAS_REGISTRY)
    for row in registry_rows:
        aliases_by_key[row["inchikey"]].append(row)

    targets = []
    for inchikey, aliases in aliases_by_key.items():
        presence = {
            label: inchikey in snapshots[label]["rows_by_inchikey"]  # type: ignore[operator]
            for label, _ in DATASET_VERSIONS
        }
        first_present = next(
            (label for label, _ in DATASET_VERSIONS if presence[label]), None
        )
        current_row = current["rows_by_inchikey"].get(inchikey)  # type: ignore[union-attr]
        targets.append(
            {
                "inchikey": inchikey,
                "aliases": [row["alias"] for row in aliases],
                "presence": presence,
                "first_present_version": first_present,
                "current_row": (
                    {field: current_row.get(field, "") for field in DETAIL_FIELDS}
                    if current_row
                    else None
                ),
                "name_search": name_search_safety(inchikey, aliases, current),
            }
        )
    targets.sort(key=lambda item: item["inchikey"])

    claims = _evaluate_claims(snapshots, targets)
    manual_probe = _probe_manual(manual_path)

    return {
        "schema_version": "manual_appendix_reconciliation/v1",
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "scope": {
            "question": "Which Appendix I section A roster claims survive a re-derivation "
            "from the committed CSVs?",
            "matching_key": "InChIKey. Common names are never used as the membership key.",
            "claim_rule": "A claim is re-affirmed only when every part of it "
            "reproduces; a roster is refuted by the first counterexample.",
            "network_used": False,
            "alias_registry": ALIAS_REGISTRY,
            "dataset_versions": [label for label, _ in DATASET_VERSIONS],
        },
        "datasets": [
            {
                "label": label,
                **{
                    key: value
                    for key, value in snapshots[label].items()
                    if key != "rows_by_inchikey"
                },
            }
            for label, _ in DATASET_VERSIONS
        ],
        "targets": targets,
        "claims": claims,
        "manual_probe": manual_probe,
        "summary": _summarize(claims, targets),
    }


def _evaluate_claims(
    snapshots: dict[str, dict[str, object]],
    targets: list[dict[str, object]],
) -> list[dict[str, object]]:
    by_key = {target["inchikey"]: target for target in targets}
    claims: list[dict[str, object]] = []

    def presence(keys: tuple[str, ...]) -> dict[str, bool]:
        return {
            label: all(by_key[key]["presence"][label] for key in keys)  # type: ignore[index]
            for label, _ in DATASET_VERSIONS
        }

    def first_present(keys: tuple[str, ...]) -> str | None:
        # Walk the declared version order: a lexicographic max() would compare
        # "v0.3.1" < "v0.3.2" correctly but would mis-order v0.9 against v0.10.
        for label, _ in DATASET_VERSIONS:
            if all(by_key[key]["presence"][label] for key in keys):
                return label
        return None

    def absence_then_addition(
        claim_id: str,
        keys: tuple[str, ...],
        text: str,
        extra_note: str = "",
        extra_ok: bool | None = None,
    ) -> dict[str, object]:
        observed = presence(keys)
        absent_before = all(
            observed[label] is False for label in CLAIMED_ABSENT_VERSIONS
        )
        first_seen = first_present(keys)
        closed = (
            absent_before
            and first_seen == "v0.3.2"
            and observed[CURRENT_VERSION] is True
            and extra_ok is not False
        )
        return {
            "claim_id": claim_id,
            "appendix": "I.A.1",
            "claim": text,
            "verdict": "confirmed_and_since_closed" if closed else "not_reproduced",
            "verdict_basis": (
                "absent in "
                + ", ".join(CLAIMED_ABSENT_VERSIONS)
                + f" = {absent_before}; first present version = {first_seen}; "
                + f"present in {CURRENT_VERSION} = {observed[CURRENT_VERSION]}"
                + (f"; {extra_note}" if extra_note else "")
            ),
            "evidence": {
                "presence": observed,
                "first_present_version": first_seen,
                "absent_in_claimed_versions": absent_before,
            },
        }

    # 1. Propylene carbonate: genuinely absent, then added by v0.3.2.
    claims.append(
        absence_then_addition(
            "appendix_i_a1_pc", TARGET_GROUPS["pc"], "PC（碳酸丙烯酯）三版本全部缺席"
        )
    )

    # 2. Ethylene carbonate: the claim also demands the extended temperature band.
    ec_row = by_key[TARGET_GROUPS["ec"][0]]["current_row"]  # type: ignore[index]
    ec_extended_ok = bool(
        ec_row
        and ec_row["temperature_band"] == "extended_temperature"
        and 313.0 <= float(ec_row["T_K"]) <= 323.0
    )
    claims.append(
        absence_then_addition(
            "appendix_i_a1_ec",
            TARGET_GROUPS["ec"],
            "EC 应入 313–323K 扩展表",
            extra_note=(
                "current row band="
                f"{ec_row['temperature_band'] if ec_row else None}, "
                f"T_K={ec_row['T_K'] if ec_row else None}; "
                "313-323 K extended band satisfied = "
                f"{ec_extended_ok}"
            ),
            extra_ok=ec_extended_ok,
        )
    )

    # 3. The empty extended-temperature band.
    v031_extended = _extended_rows(snapshots["v0.3.1"])
    current_extended = _extended_rows(snapshots[CURRENT_VERSION])
    claims.append(
        {
            "claim_id": "appendix_i_a1_ec_extended_band_empty",
            "appendix": "I.A.1",
            "claim": "extended band 为空",
            "verdict": (
                "confirmed_and_since_closed"
                if v031_extended == 0 and current_extended > 0
                else "not_reproduced"
            ),
            "verdict_basis": (
                f"extended_temperature rows = {v031_extended} in v0.3.1 and "
                f"{current_extended} in v0.3"
            ),
            "evidence": {
                "v0.3.1_extended_rows": v031_extended,
                "current_extended_rows": current_extended,
            },
        }
    )

    def roster_refutation(
        claim_id: str,
        keys: tuple[str, ...],
        text: str,
    ) -> dict[str, object]:
        """A "these molecules are missing" roster fails on any counterexample."""

        per_molecule = {key: by_key[key]["presence"] for key in keys}  # type: ignore[index]
        refuted_by = [
            {
                "inchikey": key,
                "versions_present": [
                    label for label, present in states.items() if present
                ],
            }
            for key, states in per_molecule.items()
            if any(states.values())
        ]
        everywhere = [
            key for key, states in per_molecule.items() if all(states.values())
        ]
        return {
            "claim_id": claim_id,
            "appendix": "I.A.1",
            "claim": text,
            "verdict": "false_negative" if refuted_by else "not_reproduced",
            "verdict_basis": (
                f"the claim is refuted by {len(refuted_by)} of {len(keys)} listed "
                "molecules; refutation needs only one"
            ),
            "evidence": {
                "presence_by_molecule": per_molecule,
                "refuted_by": refuted_by,
                "present_in_every_version": everywhere,
                "dataset_names": {
                    key: by_key[key]["name_search"]["dataset_name"]  # type: ignore[index]
                    for key in keys
                },
            },
        }

    # 4. The glymes: claimed absent, present in every version under IUPAC names.
    claims.append(
        roster_refutation(
            "appendix_i_a1_glymes_absent",
            TARGET_GROUPS["glymes"],
            "diglyme/triglyme/tetraglyme 缺席",
        )
    )

    # 5. Glutaronitrile: claimed absent, present in every version.
    claims.append(
        roster_refutation(
            "appendix_i_a1_glutaronitrile_absent",
            TARGET_GROUPS["dinitriles"][1:],
            "glutaronitrile 缺席",
        )
    )

    # 6. Methoxypropionitrile: genuinely absent until the v0.3 build added it.
    mopn_presence = presence(TARGET_GROUPS["mopn"])
    mopn_absent_before = all(
        mopn_presence[label] is False
        for label in (*CLAIMED_ABSENT_VERSIONS, "v0.3.2")
    )
    claims.append(
        {
            "claim_id": "appendix_i_a1_mopn_absent",
            "appendix": "I.A.1",
            "claim": "methoxypropionitrile 缺席",
            "verdict": (
                "confirmed_and_since_closed"
                if mopn_absent_before and mopn_presence[CURRENT_VERSION] is True
                else "not_reproduced"
            ),
            "verdict_basis": (
                "absent through v0.3.2 = "
                f"{mopn_absent_before}; present in {CURRENT_VERSION} = "
                f"{mopn_presence[CURRENT_VERSION]}; the added row stays outside "
                "the model-ready set"
            ),
            "evidence": {
                "presence": mopn_presence,
                "first_present_version": first_present(TARGET_GROUPS["mopn"]),
            },
        }
    )
    return claims


def _extended_rows(snapshot: dict[str, object]) -> int:
    counts = snapshot["temperature_band_counts"]
    if counts is None:
        return 0
    return int(counts.get("extended_temperature", 0))  # type: ignore[union-attr]


def _probe_manual(manual_path: Path | None) -> dict[str, object]:
    """Check whether the working manual still carries the stale sentences.

    A phrase is stale on any line that carries it (and its required context)
    unless that same line also carries every *substantive* correction token for
    that claim.  A bare "corrected" marker is not enough: the reader has to be
    shown the version and the counterexample.
    """

    if manual_path is None or not manual_path.exists():
        return {"available": False, "path": str(manual_path) if manual_path else None}
    text = manual_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    hits = []
    for record in STALE_MANUAL_PHRASES:
        matched_lines = []
        corrected_lines = []
        for index, line in enumerate(lines):
            if record["phrase"] not in line:
                continue
            if any(token not in line for token in record["requires_all_of"]):
                continue
            if all(token in line for token in record["correction_requires_all_of"]):
                corrected_lines.append(index + 1)
            else:
                matched_lines.append(index + 1)
        hits.append(
            {
                "phrase": record["phrase"],
                "requires_all_of": list(record["requires_all_of"]),
                "correction_requires_all_of": list(
                    record["correction_requires_all_of"]
                ),
                "why_stale": record["why"],
                "line_numbers": matched_lines,
                "corrected_line_numbers": corrected_lines,
            }
        )
    return {
        "available": True,
        "path": str(manual_path),
        "line_count": len(lines),
        "char_count": len(text),
        "stale_phrase_hits": hits,
        "stale_phrase_hit_count": sum(len(hit["line_numbers"]) for hit in hits),
        "corrected_phrase_hit_count": sum(
            len(hit["corrected_line_numbers"]) for hit in hits
        ),
    }


def _summarize(
    claims: list[dict[str, object]],
    targets: list[dict[str, object]],
) -> dict[str, object]:
    verdicts = collections.Counter(claim["verdict"] for claim in claims)
    missed_by_name = sorted(
        target["name_search"]["dataset_name"]  # type: ignore[index]
        for target in targets
        if target["name_search"]["name_search_would_miss"] is True  # type: ignore[index]
    )
    unjudged = sorted(
        target["name_search"]["dataset_name"]  # type: ignore[index]
        for target in targets
        if target["name_search"]["name_search_would_miss"] is None  # type: ignore[index]
    )
    return {
        "claim_count": len(claims),
        "verdict_counts": dict(sorted(verdicts.items())),
        "false_negative_claims": sorted(
            claim["claim_id"] for claim in claims if claim["verdict"] == "false_negative"
        ),
        "targets_missed_by_common_name_search": missed_by_name,
        "targets_without_a_registered_common_name": unjudged,
        "target_count": len(targets),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=REPOSITORY_ROOT / "probes" / "manual_appendix_reconciliation.json",
    )
    parser.add_argument(
        "--manual",
        type=Path,
        default=DEFAULT_MANUAL,
        help="Working manual probed for stale sentences; skipped when absent.",
    )
    parser.add_argument(
        "--summary-only",
        action="store_true",
        help="Print the summary block instead of writing the artifact.",
    )
    args = parser.parse_args(argv)

    report = build_reconciliation(manual_path=args.manual)
    if args.summary_only:
        json.dump(report["summary"], sys.stdout, indent=2, ensure_ascii=False)
        sys.stdout.write("\n")
        return 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(report, indent=2, ensure_ascii=False, sort_keys=False)
    args.output.write_text(payload + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {args.output.relative_to(REPOSITORY_ROOT).as_posix()}")
    for claim in report["claims"]:
        print(f"  {claim['verdict']:<32} {claim['claim_id']}")
    summary = report["summary"]
    print(
        f"  claims={summary['claim_count']} "
        f"false_negative={len(summary['false_negative_claims'])} "
        f"name_search_misses={len(summary['targets_missed_by_common_name_search'])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
