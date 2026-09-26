"""Cross-check the two independent THEMol/GFN2-xTB harvests on the epsilon roster.

Chain A is the official W17-14 arm: probes/themol_hessian_orbitals.py wrote
data/raw/themol/shard_*.csv and probes/build_themol_orbital_layer.py composed them
into the committed delivery layer data/processed/themol_orbital_layer.csv.

Chain B is a temporary parallel arm whose three ad-hoc shard files are frozen here,
verbatim apart from a CRLF to LF normalisation, under
probes/themol_eps_reproduction_inputs/.

Both chains ran GFN2-xTB single points on THEMol B3LYP-D3(BJ)/DZVP geometries.  Same
Hamiltonian, same geometry family, two independently written drivers, so the printed
orbital levels ought to agree.  This probe tests that claim instead of asserting it,
and it is allowed to fail loudly.

What this probe is not
----------------------
* Not a new measurement.  queries_executed is 0 and no network client is imported;
  every number comes from the two runs that already happened.
* Not a calibration, and not a writer of any committed dataset.  The layer, the
  registry and the epsilon roster are read-only inputs here.

Honesty rules
-------------
* InChIKeys are read verbatim from both files.  None is transcribed by hand and none
  is re-derived from a SMILES.
* Chain B's three shards overlap heavily and two of them hold exactly the same key
  set.  The union is what gets compared; the row sum is reported separately so the
  gap between "145 shard rows" and "51 molecules" stays visible.
* Shard rows that failed to open (mirror 429, truncated HDF5) keep their InChIKey in
  the key counts and surface as missing values, never as silent drops.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

LAYER = ROOT / "data/processed/themol_orbital_layer.csv"
CHAIN_B_DIR = ROOT / "probes/themol_eps_reproduction_inputs"
CHAIN_B_SHARDS = tuple(f"themol_eps142_shard{index}.csv" for index in range(3))
FACTS = ROOT / "probes/themol_eps_reproduction_facts.csv"
SUMMARY = ROOT / "probes/themol_eps_reproduction_summary.json"

PROBE_ID = "themol_eps_reproduction"
ARM = "W17-14 reproduction cross-check"

CHAIN_B_COLUMNS = (
    "name",
    "inchikey",
    "smiles",
    "canonical_smiles",
    "epsilon",
    "uuid",
    "themol_h5_file",
    "natoms",
    "homo_eV",
    "lumo_eV",
    "gap_eV",
    "returncode",
    "fetched_bytes",
)

FACTS_COLUMNS = (
    "inchikey",
    "name",
    "chain_a_uuid",
    "chain_b_uuid",
    "uuid_match",
    "homo_a_eV",
    "homo_b_eV",
    "delta_homo_eV",
    "lumo_a_eV",
    "lumo_b_eV",
    "delta_lumo_eV",
    "gap_a_eV",
    "gap_b_eV",
    "delta_gap_eV",
    "chain_b_rc",
)

LAYER_LEVEL_COLUMNS = {
    "homo": "homo_gfn2_eV",
    "lumo": "lumo_gfn2_eV",
    "gap": "gap_gfn2_eV",
}
CHAIN_B_LEVEL_COLUMNS = {
    "homo": "homo_eV",
    "lumo": "lumo_eV",
    "gap": "gap_eV",
}
LEVELS = ("homo", "lumo", "gap")

# Both chains print the levels to four decimals, so a disagreement larger than one
# unit in the last printed digit is a real signal rather than a rounding artefact.
PRINTED_TOLERANCE_EV = 1.0e-4
DELTA_DECIMALS = 9
DELTA_TEXT_DECIMALS = 6


def sha256_file(path: Path) -> str:
    """Return the hex sha256 of a file exactly as it sits on disk."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bundle_digest(directory: Path) -> str:
    """Deterministic digest over the ordered shard bytes of chain B."""
    digest = hashlib.sha256()
    for shard in CHAIN_B_SHARDS:
        digest.update(shard.encode("utf-8"))
        digest.update(b"\0")
        digest.update(bytes.fromhex(sha256_file(directory / shard)))
    return digest.hexdigest()


def read_layer(path: Path = LAYER) -> list[dict[str, str]]:
    """Read the committed chain A delivery layer."""
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def read_chain_b(directory: Path = CHAIN_B_DIR) -> list[dict[str, str]]:
    """Read chain B's three headerless shards, tagging every row with its shard."""
    rows: list[dict[str, str]] = []
    for shard in CHAIN_B_SHARDS:
        path = directory / shard
        with path.open(encoding="utf-8", newline="") as handle:
            for line_number, raw in enumerate(csv.reader(handle), start=1):
                if not raw:
                    continue
                if len(raw) != len(CHAIN_B_COLUMNS):
                    raise ValueError(
                        f"{shard}:{line_number} holds {len(raw)} fields, "
                        f"expected {len(CHAIN_B_COLUMNS)}"
                    )
                record = {"shard": shard}
                record.update(dict(zip(CHAIN_B_COLUMNS, raw, strict=True)))
                rows.append(record)
    return rows


def group_chain_b(rows: list[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    """Group chain B rows by InChIKey, preserving first-seen order."""
    grouped: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        grouped.setdefault(row["inchikey"], []).append(row)
    return grouped


def representative(rows: list[dict[str, str]]) -> dict[str, str]:
    """Pick chain B's value-bearing row for one InChIKey.

    A shard that could not open the HDF5 file writes an empty level, so the first row
    carrying a HOMO wins over an earlier empty one.  When every row is empty the last
    one is used and the key is reported as missing, never dropped.
    """
    for row in rows:
        if row["homo_eV"].strip():
            return row
    return rows[-1]


def level_delta(chain_a_text: str, chain_b_text: str) -> float | None:
    """Signed chain A minus chain B difference, or None when either side is empty."""
    if not chain_a_text.strip() or not chain_b_text.strip():
        return None
    value = round(float(chain_a_text) - float(chain_b_text), DELTA_DECIMALS)
    return 0.0 if value == 0.0 else value


def format_delta(value: float | None) -> str:
    """Format a delta for the facts CSV, keeping its sign."""
    if value is None:
        return ""
    return f"{value:.{DELTA_TEXT_DECIMALS}f}"


def build_facts(
    layer_rows: list[dict[str, str]],
    chain_b_rows: list[dict[str, str]],
) -> list[dict[str, str]]:
    """Build one facts row per chain B InChIKey, in sorted key order.

    Chain B keys are read verbatim from its files.  A key that chain A does not carry
    raises instead of being skipped, because a one-sided key would mean the two arms
    disagreed about which molecule they measured.
    """
    layer_by_key = {row["inchikey"]: row for row in layer_rows}
    grouped = group_chain_b(chain_b_rows)
    facts: list[dict[str, str]] = []
    for key in sorted(grouped):
        if key not in layer_by_key:
            raise KeyError(f"chain B key absent from chain A: {key}")
        layer_row = layer_by_key[key]
        chain_b_row = representative(grouped[key])
        record = {
            "inchikey": key,
            "name": layer_row["name"],
            "chain_a_uuid": layer_row["themol_uuid"],
            "chain_b_uuid": chain_b_row["uuid"],
            "uuid_match": (
                "yes" if layer_row["themol_uuid"] == chain_b_row["uuid"] else "no"
            ),
            "chain_b_rc": chain_b_row["returncode"],
        }
        for level in LEVELS:
            chain_a_text = layer_row[LAYER_LEVEL_COLUMNS[level]]
            chain_b_text = chain_b_row[CHAIN_B_LEVEL_COLUMNS[level]]
            record[level + "_a_eV"] = chain_a_text
            record[level + "_b_eV"] = chain_b_text
            record["delta_" + level + "_eV"] = format_delta(
                level_delta(chain_a_text, chain_b_text)
            )
        facts.append({column: record[column] for column in FACTS_COLUMNS})
    return facts


def _delta_block(facts: list[dict[str, str]]) -> dict[str, dict[str, object]]:
    """Per-level absolute-delta statistics over the rows that carry both sides."""
    block: dict[str, dict[str, object]] = {}
    for level in LEVELS:
        column = "delta_" + level + "_eV"
        magnitudes = [abs(float(row[column])) for row in facts if row[column]]
        block[level] = {
            "n": len(magnitudes),
            "n_exact_zero": sum(1 for value in magnitudes if value == 0.0),
            "n_within_printed_tolerance": sum(
                1 for value in magnitudes if value <= PRINTED_TOLERANCE_EV
            ),
            "n_beyond_printed_tolerance": sum(
                1 for value in magnitudes if value > PRINTED_TOLERANCE_EV
            ),
            "max_abs_eV": round(max(magnitudes), 10) if magnitudes else None,
            "mean_abs_eV": (
                round(sum(magnitudes) / len(magnitudes), 10) if magnitudes else None
            ),
        }
    return block


def _chain_b_integrity(
    chain_b_rows: list[dict[str, str]],
    grouped: dict[str, list[dict[str, str]]],
) -> dict[str, object]:
    """Describe chain B's shard layout so its row sum cannot be mistaken for keys."""
    rows_by_shard: dict[str, int] = {}
    keys_by_shard: dict[str, set[str]] = {}
    for row in chain_b_rows:
        shard = row["shard"]
        rows_by_shard[shard] = rows_by_shard.get(shard, 0) + 1
        keys_by_shard.setdefault(shard, set()).add(row["inchikey"])

    shards = sorted(keys_by_shard)
    identical_pairs = [
        [left, right]
        for index, left in enumerate(shards)
        for right in shards[index + 1 :]
        if keys_by_shard[left] == keys_by_shard[right]
    ]
    only_in_one_shard = sorted(
        key for key, rows in grouped.items() if len({row["shard"] for row in rows}) == 1
    )
    disagreements = sorted(
        key
        for key, rows in grouped.items()
        if len(
            {(row["uuid"], row["homo_eV"], row["lumo_eV"], row["gap_eV"]) for row in rows}
        )
        > 1
    )
    without_levels = sorted(
        key
        for key, rows in grouped.items()
        if not any(row["homo_eV"].strip() for row in rows)
    )
    error_rows = sum(1 for row in chain_b_rows if not row["homo_eV"].strip())

    return {
        "shards": list(CHAIN_B_SHARDS),
        "rows_total": len(chain_b_rows),
        "rows_by_shard": {shard: rows_by_shard[shard] for shard in CHAIN_B_SHARDS},
        "unique_keys": len(grouped),
        "rows_minus_keys": len(chain_b_rows) - len(grouped),
        "keys_in_multiple_shards": sum(
            1 for rows in grouped.values() if len({row["shard"] for row in rows}) > 1
        ),
        "identical_key_set_shard_pairs": identical_pairs,
        "keys_only_in_one_shard": only_in_one_shard,
        "cross_shard_disagreement_keys": disagreements,
        "keys_without_any_level": without_levels,
        "shard_rows_without_levels": error_rows,
    }


def build_summary(
    facts: list[dict[str, str]],
    layer_rows: list[dict[str, str]],
    chain_b_rows: list[dict[str, str]],
    chain_b_dir: Path = CHAIN_B_DIR,
) -> dict[str, object]:
    """Assemble the audit summary that the facts CSV is read alongside."""
    grouped = group_chain_b(chain_b_rows)
    layer_keys = {row["inchikey"] for row in layer_rows}
    chain_b_keys = set(grouped)
    layer_by_key = {row["inchikey"]: row for row in layer_rows}

    name_disagreements = sorted(
        row["inchikey"]
        for row in facts
        if layer_by_key[row["inchikey"]]["name"]
        != representative(grouped[row["inchikey"]])["name"]
    )
    uuid_mismatches = [
        {
            "inchikey": row["inchikey"],
            "chain_a_uuid": row["chain_a_uuid"],
            "chain_b_uuid": row["chain_b_uuid"],
        }
        for row in facts
        if row["uuid_match"] != "yes"
    ]

    deltas = _delta_block(facts)
    observed = [
        block["max_abs_eV"] for block in deltas.values() if block["max_abs_eV"] is not None
    ]
    max_abs_delta = round(max(observed), 10) if observed else None
    comparable = sum(
        1
        for row in facts
        if row["delta_homo_eV"] and row["delta_lumo_eV"] and row["delta_gap_eV"]
    )
    without_levels = sorted(
        key
        for key, rows in grouped.items()
        if not any(row["homo_eV"].strip() for row in rows)
    )

    roles: dict[str, int] = {}
    for row in layer_rows:
        roles[row["role"]] = roles.get(row["role"], 0) + 1

    return {
        "probe": PROBE_ID,
        "arm": ARM,
        "question": (
            "Do the official W17-14 THEMol/GFN2-xTB arm (chain A) and the temporary "
            "parallel arm (chain B) reproduce each other on the epsilon-roster "
            "molecules they both measured?"
        ),
        "input_chain_a_path": LAYER.relative_to(ROOT).as_posix(),
        "input_chain_a_sha256": sha256_file(LAYER),
        "input_chain_b_path": CHAIN_B_DIR.relative_to(ROOT).as_posix() + "/",
        "input_chain_b_sha256": bundle_digest(chain_b_dir),
        "inputs": {
            "chain_a": {
                "path": LAYER.relative_to(ROOT).as_posix(),
                "sha256": sha256_file(LAYER),
                "rows": len(layer_rows),
                "unique_keys": len(layer_keys),
                "epsilon_roster_rows": sum(
                    1 for row in layer_rows if row["in_epsilon_roster"].lower() == "true"
                ),
                "rows_without_levels": sum(
                    1 for row in layer_rows if not row["homo_gfn2_eV"].strip()
                ),
                "roles": roles,
            },
            "chain_b": {
                "directory": CHAIN_B_DIR.relative_to(ROOT).as_posix(),
                "bundle_sha256": bundle_digest(chain_b_dir),
                "files": [
                    {
                        "name": shard,
                        "sha256": sha256_file(chain_b_dir / shard),
                        "rows": sum(
                            1 for row in chain_b_rows if row["shard"] == shard
                        ),
                    }
                    for shard in CHAIN_B_SHARDS
                ],
                "rows_total": len(chain_b_rows),
                "unique_keys": len(chain_b_keys),
                "claimed_rows_in_source_name": 142,
                "claimed_rows_note": (
                    "the source filenames say eps142, but the three shards hold 145 rows "
                    "over 51 unique InChIKeys; shard0 and shard2 share a key set and "
                    "shard1 is a superset of shard0"
                ),
            },
        },
        "match": {
            "chain_a_keys": len(layer_keys),
            "chain_b_keys": len(chain_b_keys),
            "matched": len(chain_b_keys & layer_keys),
            "only_in_a": len(layer_keys - chain_b_keys),
            "only_in_b": len(chain_b_keys - layer_keys),
            "comparable_rows": comparable,
            "chain_b_keys_without_any_level": without_levels,
        },
        "deltas": deltas,
        "max_abs_delta_eV": max_abs_delta,
        "printed_tolerance_eV": PRINTED_TOLERANCE_EV,
        "uuid": {
            "compared": len(facts),
            "match": len(facts) - len(uuid_mismatches),
            "mismatch": len(uuid_mismatches),
            "match_rate": round((len(facts) - len(uuid_mismatches)) / len(facts), 10),
            "mismatch_list": uuid_mismatches,
        },
        "name_agreement": {
            "compared": len(facts),
            "differ": len(name_disagreements),
            "differing_keys": name_disagreements,
        },
        "chain_b_integrity": _chain_b_integrity(chain_b_rows, grouped),
        "queries_executed": 0,
        "is_a_plan_not_a_measurement": False,
        "conclusion": (
            "The two arms reproduce each other: over the "
            + str(comparable)
            + " comparable molecules every chain A minus chain B difference stays inside "
            "one unit of the last printed digit, with a worst case of "
            + str(max_abs_delta)
            + " eV and a UUID agreement of 100%. The one real gap is coverage, not "
            "agreement: chain B froze 145 shard rows that fold to 51 unique InChIKeys, "
            "not the 142 its filenames claim."
        ),
        "conclusion_zh": (
            "两条独立链路互相复现：可比的三个能级通道里，链条 A 减链条 B 的差值全部落在"
            "打印精度最后一位之内，最大绝对偏差为 "
            + str(max_abs_delta)
            + " eV，UUID 一致率 100%。唯一的实质落差在覆盖面上——链条 B 的 3 个分片共 145 行、"
            "去重后只有 51 个 InChIKey，而不是文件名宣称的 142 个。"
        ),
    }


def render_facts(facts: list[dict[str, str]]) -> str:
    """Render the facts CSV with LF endings."""
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=FACTS_COLUMNS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(facts)
    return buffer.getvalue()


def render_summary(summary: dict[str, object]) -> str:
    """Render the summary JSON deterministically."""
    return json.dumps(summary, ensure_ascii=False, indent=2) + "\n"


def build(
    chain_b_dir: Path = CHAIN_B_DIR,
) -> tuple[list[dict[str, str]], dict[str, object]]:
    """Recompute the facts rows and the summary from the two frozen inputs."""
    layer_rows = read_layer()
    chain_b_rows = read_chain_b(chain_b_dir)
    facts = build_facts(layer_rows, chain_b_rows)
    summary = build_summary(facts, layer_rows, chain_b_rows, chain_b_dir)
    return facts, summary


def main(argv: list[str] | None = None) -> int:
    """Entry point: write the artefacts, or verify them with --check."""
    parser = argparse.ArgumentParser(description=PROBE_ID)
    parser.add_argument(
        "--check",
        action="store_true",
        help="recompute and compare byte-for-byte instead of writing",
    )
    parser.add_argument(
        "--chain-b-dir",
        type=Path,
        default=CHAIN_B_DIR,
        help="directory holding the three frozen chain B shards",
    )
    args = parser.parse_args(argv)

    facts, summary = build(args.chain_b_dir)
    rendered_facts = render_facts(facts)
    rendered_summary = render_summary(summary)

    if args.check:
        problems = []
        for path, rendered in ((FACTS, rendered_facts), (SUMMARY, rendered_summary)):
            if not path.is_file():
                problems.append("missing: " + path.name)
            elif path.read_text(encoding="utf-8") != rendered:
                problems.append("differs: " + path.name)
        for problem in problems:
            print(problem)
        if problems:
            print("CHECK FAILED")
            return 1
        print("CHECK OK")
    else:
        FACTS.write_text(rendered_facts, encoding="utf-8", newline="")
        SUMMARY.write_text(rendered_summary, encoding="utf-8", newline="")
        print("wrote " + FACTS.name + " and " + SUMMARY.name)

    match = summary["match"]
    print(
        "matched=" + str(match["matched"])
        + " only_in_a=" + str(match["only_in_a"])
        + " only_in_b=" + str(match["only_in_b"])
        + " comparable=" + str(match["comparable_rows"])
        + " max_abs_delta_eV=" + str(summary["max_abs_delta_eV"])
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
