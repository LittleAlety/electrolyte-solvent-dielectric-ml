"""Independently verify the dielectric v0.2 dataset and its provenance."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TextIO

from rdkit import Chem

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from electrolyte_ml.standardize import GATE_FLAGS

NBS514_SCOPE = "nbs514_manual_static_293.15_303.15K"
NBS514_DOI = "10.6028/nbs.circ.514"
EXPECTED_NBS514_PDF_SHA256 = (
    "cb3fa9239fd977d7fa85389fbc219baea69667d5cc7c9e5382b09157fda40683"
)


@dataclass(frozen=True, slots=True)
class Check:
    name: str
    passed: bool
    detail: str


def read_csv_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or ()), list(reader)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path) -> Mapping[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise TypeError(f"JSON object required: {path}")
    return payload


def check_dataset_size(
    rows: Sequence[Mapping[str, str]],
    summary: Mapping[str, object],
) -> Check:
    keys = [row.get("inchikey", "") for row in rows]
    unique_keys = set(keys)
    if len(rows) != int(summary.get("compound_count", -1)):
        return Check("v0.2 size", False, "summary compound_count mismatch")
    if len(rows) < 200:
        return Check("v0.2 size", False, f"only {len(rows)} compounds")
    if len(keys) != len(unique_keys):
        return Check("v0.2 size", False, "duplicate InChIKeys")
    return Check("v0.2 size", True, f"{len(rows)} unique compounds")


def check_v01_subset(
    v01_rows: Sequence[Mapping[str, str]],
    v02_rows: Sequence[Mapping[str, str]],
) -> Check:
    v02_by_key = {row["inchikey"]: row for row in v02_rows}
    shared_fields = [
        "smiles",
        "name",
        "T_K",
        "dielectric",
        "source_doi",
        "source_dois_all",
        "n_observations",
        "n_historical_observations",
        "source_scope",
        "crosscheck_available",
        "gate_flags",
    ]
    for v01_row in v01_rows:
        v02_row = v02_by_key.get(v01_row["inchikey"])
        if v02_row is None:
            return Check("v0.2 v0.1 subset", False, f"missing {v01_row['inchikey']}")
        for field in shared_fields:
            if v02_row.get(field) != v01_row.get(field):
                return Check(
                    "v0.2 v0.1 subset",
                    False,
                    f"{field} changed for {v01_row['inchikey']}",
                )
    return Check("v0.2 v0.1 subset", True, f"{len(v01_rows)} v0.1 rows unchanged")


def check_nbs_candidate_join(
    v02_rows: Sequence[Mapping[str, str]],
    candidates: Sequence[Mapping[str, str]],
) -> Check:
    selected = [
        row
        for row in candidates
        if row.get("selected_for_v02") == "true"
    ]
    v02_nbs = [row for row in v02_rows if row.get("source_scope") == NBS514_SCOPE]
    if len(v02_nbs) != len(selected):
        return Check(
            "v0.2 NBS join",
            False,
            f"v0.2 NBS={len(v02_nbs)} selected candidates={len(selected)}",
        )
    by_source_id = {row["source_record_id"]: row for row in v02_nbs}
    if len(by_source_id) != len(v02_nbs):
        return Check("v0.2 NBS join", False, "duplicate source_record_id")
    fields = {
        "compound_name": "name",
        "dielectric": "dielectric",
        "T_K": "T_K",
        "smiles": "smiles",
        "inchikey": "inchikey",
        "resolution_source": "structure_resolution_source",
    }
    for candidate in selected:
        row = by_source_id.get(candidate["source_id"])
        if row is None:
            return Check("v0.2 NBS join", False, f"missing {candidate['source_id']}")
        for candidate_field, row_field in fields.items():
            if row.get(row_field) != candidate.get(candidate_field):
                return Check(
                    "v0.2 NBS join",
                    False,
                    f"{row_field} mismatch for {candidate['source_id']}",
                )
    return Check("v0.2 NBS join", True, f"{len(selected)} selected NBS rows reproduced")


def check_nbs_source_rows(
    candidates: Sequence[Mapping[str, str]],
    source_rows: Sequence[Mapping[str, str]],
) -> Check:
    source_by_id = {row["source_id"]: row for row in source_rows}
    if len(source_by_id) != len(source_rows):
        return Check("v0.2 NBS source join", False, "duplicate source_id in source parts")
    fields = ("source_page", "formula", "compound_name", "dielectric", "t_C", "T_K", "source_quality")
    for candidate in candidates:
        if candidate.get("selected_for_v02") != "true":
            continue
        source = source_by_id.get(candidate["source_id"])
        if source is None:
            return Check(
                "v0.2 NBS source join",
                False,
                f"source row missing: {candidate['source_id']}",
            )
        for field in fields:
            if source.get(field) != candidate.get(field):
                return Check(
                    "v0.2 NBS source join",
                    False,
                    f"{field} mismatch for {candidate['source_id']}",
                )
    return Check(
        "v0.2 NBS source join",
        True,
        "selected rows match the transcribed source parts",
    )


def check_temperature_window(
    rows: Sequence[Mapping[str, str]],
) -> Check:
    outside = [
        row["inchikey"]
        for row in rows
        if not 293.15 <= float(row["T_K"]) <= 303.15
    ]
    if outside:
        return Check("v0.2 temperature window", False, f"outside: {outside[:5]}")
    return Check("v0.2 temperature window", True, "all rows in 293.15-303.15 K")


def check_structure_identity(
    rows: Sequence[Mapping[str, str]],
) -> Check:
    for row in rows:
        molecule = Chem.MolFromSmiles(row["smiles"])
        if molecule is None:
            return Check("v0.2 structures", False, f"invalid SMILES: {row['name']}")
        actual = Chem.MolToInchiKey(molecule)
        if actual != row["inchikey"]:
            return Check("v0.2 structures", False, f"InChIKey mismatch: {row['name']}")
        if float(row["dielectric"]) <= 0:
            return Check("v0.2 structures", False, f"nonpositive dielectric: {row['name']}")
    return Check("v0.2 structures", True, f"{len(rows)} structures reproduced")


def check_nbs_metadata(
    rows: Sequence[Mapping[str, str]],
) -> Check:
    nbs_rows = [row for row in rows if row.get("source_scope") == NBS514_SCOPE]
    if len(nbs_rows) < 100:
        return Check("v0.2 NBS metadata", False, f"only {len(nbs_rows)} NBS rows")
    for row in nbs_rows:
        if row.get("source_doi") != NBS514_DOI:
            return Check("v0.2 NBS metadata", False, f"wrong DOI: {row['name']}")
        if not row.get("source_record_id") or not row.get("source_page"):
            return Check("v0.2 NBS metadata", False, f"missing source id/page: {row['name']}")
        if row.get("source_quality") not in {"three_figures", "four_figures"}:
            return Check("v0.2 NBS metadata", False, f"weak source quality: {row['name']}")
        if row.get("uncertainty_kind") != "not_reported":
            return Check("v0.2 NBS metadata", False, f"unexpected uncertainty: {row['name']}")
        if row.get("n_observations") != "1":
            return Check("v0.2 NBS metadata", False, f"wrong observation count: {row['name']}")
    quality_counts = Counter(row["source_quality"] for row in nbs_rows)
    return Check(
        "v0.2 NBS metadata",
        True,
        f"{len(nbs_rows)} rows; quality={dict(quality_counts)}",
    )


def check_gate_flag_vocabulary(
    rows: Sequence[Mapping[str, str]],
) -> Check:
    """Every label used by v0.2 must exist in the shared enum.

    This check exists because it did not: ``nbs514_circular_514`` shipped in the
    committed dataset while being absent from ``GATE_FLAGS``, and nothing here
    noticed.  Downstream validators that test membership in ``GATE_FLAGS`` would
    have rejected the row, so the drift was a latent inconsistency.
    """

    allowed = frozenset(GATE_FLAGS)
    used = Counter(
        flag
        for row in rows
        for flag in row.get("gate_flags", "").split("|")
        if flag
    )
    unknown = {flag: count for flag, count in used.items() if flag not in allowed}
    if unknown:
        return Check(
            "v0.2 gate flags",
            False,
            f"labels absent from GATE_FLAGS: {unknown}",
        )
    return Check(
        "v0.2 gate flags",
        True,
        f"{len(used)} distinct labels, all registered",
    )


def check_summary_hashes(
    summary: Mapping[str, object],
    *,
    v01_path: Path,
    candidate_path: Path,
    v02_path: Path,
) -> Check:
    inputs = summary.get("inputs")
    output = summary.get("output")
    if not isinstance(inputs, Mapping) or not isinstance(output, Mapping):
        return Check("v0.2 summary hashes", False, "missing summary input/output maps")
    expected = {
        "v01": inputs.get("v01_sha256"),
        "candidate": inputs.get("candidate_sha256"),
        "output": output.get("sha256"),
    }
    actual = {
        "v01": sha256_file(v01_path),
        "candidate": sha256_file(candidate_path),
        "output": sha256_file(v02_path),
    }
    if expected != actual:
        return Check("v0.2 summary hashes", False, f"expected={expected}, actual={actual}")
    nbs = summary.get("nbs514")
    if not isinstance(nbs, Mapping) or nbs.get("pdf_sha256") != EXPECTED_NBS514_PDF_SHA256:
        return Check("v0.2 summary hashes", False, "NBS PDF hash mismatch")
    return Check("v0.2 summary hashes", True, "input, output, and source hashes match")


def run_checks(root: Path = REPOSITORY_ROOT) -> list[Check]:
    v01_path = root / "data" / "dielectric_v01.csv"
    candidate_path = root / "data" / "processed" / "nbs514_structure_candidates.csv"
    v02_path = root / "data" / "dielectric_v02.csv"
    summary_path = root / "probes" / "dielectric_v02_summary.json"
    source_part_paths = sorted(
        (root / "data" / "interim").glob("nbs514_organic_part*.csv")
    )
    paths = [v01_path, candidate_path, v02_path, summary_path, *source_part_paths]
    missing = [str(path) for path in paths if not path.is_file()]
    if missing:
        return [Check("v0.2 artifacts", False, f"missing: {missing}")]
    _, v01_rows = read_csv_rows(v01_path)
    _, candidates = read_csv_rows(candidate_path)
    _, v02_rows = read_csv_rows(v02_path)
    summary = _load_json(summary_path)
    source_rows = [
        row
        for path in source_part_paths
        for _, rows in [read_csv_rows(path)]
        for row in rows
    ]
    checks = [
        check_dataset_size(v02_rows, summary),
        check_v01_subset(v01_rows, v02_rows),
        check_nbs_candidate_join(v02_rows, candidates),
        check_nbs_source_rows(candidates, source_rows),
        check_temperature_window(v02_rows),
        check_structure_identity(v02_rows),
        check_nbs_metadata(v02_rows),
        check_gate_flag_vocabulary(v02_rows),
        check_summary_hashes(
            summary,
            v01_path=v01_path,
            candidate_path=candidate_path,
            v02_path=v02_path,
        ),
    ]
    return checks


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=REPOSITORY_ROOT)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    checks = run_checks(args.root)
    failures = [check for check in checks if not check.passed]
    if args.json:
        print(
            json.dumps(
                {"passed": not failures, "checks": [asdict(check) for check in checks]},
                indent=2,
            )
        )
    else:
        output: TextIO = sys.stdout
        for check in checks:
            marker = "PASS" if check.passed else "FAIL"
            print(f"[{marker}] {check.name}: {check.detail}", file=output)
        print(f"\n{len(checks) - len(failures)}/{len(checks)} checks passed", file=output)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
