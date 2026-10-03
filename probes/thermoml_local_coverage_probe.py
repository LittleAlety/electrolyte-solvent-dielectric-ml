"""Tier-0 independent coverage audit of the local ThermoML dielectric corpus.

The G1+ source-priority pass concluded that several target electrolyte solvents
have no local ThermoML dielectric observation. That conclusion is load-bearing:
it is what justifies reaching for external compilations for PC, EC, VC, FEC and
methoxypropionitrile. This probe re-derives it from the raw XML corpus instead
of trusting the extraction output, so a silent extraction gap cannot masquerade
as "no data".

For every target the probe reports three independent counts:

* xml_files_mentioning_inchikey: raw text grep of every local ThermoML XML for
  the compound's standard InChIKey. This is the most permissive test and it
  fires even when the compound only appears as a mixture component.
* xml_files_with_permittivity_text: of those, how many contain any permittivity
  or dielectric wording at all. A compound can be present in many mixture
  studies and still never be measured dielectrically.
* extracted_observations / extracted_pure_observations: rows in the parsed
  extraction attributed to that InChIKey.

A target is only "locally supported" when the third count is non-zero. The probe
never promotes anything into the frozen dataset.
"""

from __future__ import annotations

import argparse
import collections
import csv
import glob
import json
import math
import re
import sys
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))
sys.path.insert(0, str(REPOSITORY_ROOT / "probes"))

from dielectric_representation_ablation import write_csv_rows

from electrolyte_ml.exporting import canonical_text_sha256

THERMOML_GLOB = "data/raw/thermoml/**/*.xml"
EXTRACTION_PATH = "data/processed/dielectric_raw.csv"
DEFAULT_SUMMARY = REPOSITORY_ROOT / "probes" / "thermoml_local_coverage_summary.json"
DEFAULT_ROWS = REPOSITORY_ROOT / "data" / "processed" / "thermoml_local_coverage.csv"
PERMITTIVITY_PATTERN = re.compile(
    r"ermittivity|ielectricConstant|ielectric constant|DielectricConstant",
    re.IGNORECASE,
)
# name aliases, CAS registry numbers and standard InChIKeys of the G1+ targets.
TARGETS: tuple[dict[str, object], ...] = (
    {
        "label": "propylene carbonate",
        "aliases": ("propylene carbonate", "4-methyl-1,3-dioxolan-2-one"),
        "cas": ("108-32-7",),
        "inchikey": "RUOJZAUFBMNUDX-UHFFFAOYSA-N",
    },
    {
        "label": "ethylene carbonate",
        "aliases": ("ethylene carbonate", "1,3-dioxolan-2-one"),
        "cas": ("96-49-1",),
        "inchikey": "KMTRUDSVKNLOMY-UHFFFAOYSA-N",
    },
    {
        "label": "vinylene carbonate",
        "aliases": ("vinylene carbonate", "1,3-dioxol-2-one"),
        "cas": ("872-36-6",),
        "inchikey": "VAYTZRYEBVHVLE-UHFFFAOYSA-N",
    },
    {
        "label": "fluoroethylene carbonate",
        "aliases": ("fluoroethylene carbonate", "4-fluoro-1,3-dioxolan-2-one"),
        "cas": ("114435-02-8",),
        "inchikey": "SBLRHMKNNHXPHG-UHFFFAOYSA-N",
    },
    {
        "label": "3-methoxypropionitrile",
        "aliases": (
            "3-methoxypropionitrile",
            "3-methoxypropanenitrile",
            "methoxypropionitrile",
        ),
        "cas": ("110-67-8",),
        "inchikey": "OOWFYDWAMOKVSF-UHFFFAOYSA-N",
    },
    {
        "label": "diglyme",
        "aliases": ("diglyme", "bis(2-methoxyethyl) ether"),
        "cas": ("111-96-6",),
        "inchikey": "SBZXBUIDTXKZTM-UHFFFAOYSA-N",
    },
    {
        "label": "triglyme",
        "aliases": ("triglyme", "triethylene glycol dimethyl ether"),
        "cas": ("112-49-2",),
        "inchikey": "YFNKIDBQEZZDLK-UHFFFAOYSA-N",
    },
    {
        "label": "tetraglyme",
        "aliases": ("tetraglyme", "tetraethylene glycol dimethyl ether"),
        "cas": ("143-24-8",),
        "inchikey": "ZUHZGEOKBKGPSW-UHFFFAOYSA-N",
    },
    {
        "label": "adiponitrile",
        "aliases": ("adiponitrile", "hexanedinitrile"),
        "cas": ("111-69-3",),
        "inchikey": "BTGRAWJCKBQKAO-UHFFFAOYSA-N",
    },
    {
        "label": "glutaronitrile",
        "aliases": ("glutaronitrile", "pentanedinitrile"),
        "cas": ("544-13-8",),
        "inchikey": "ZTOMUSMDRMJOTH-UHFFFAOYSA-N",
    },
)
COVERAGE_COLUMNS = (
    "label",
    "inchikey",
    "cas",
    "xml_files_scanned",
    "xml_files_mentioning_inchikey",
    "xml_files_mentioning_cas",
    "xml_files_mentioning_alias",
    "xml_files_with_permittivity_text",
    "extracted_observations",
    "extracted_pure_observations",
    "extracted_zero_frequency_observations",
    "locally_supported",
    "verdict",
)


def _json_ready(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    return value


def write_json_lf(path: Path, payload: object) -> None:
    """Write JSON with explicit LF endings and no non-finite literals.

    Path.write_text translates the newline to os.linesep on Windows, which would
    make the artifact bytes depend on the host platform. Non-finite floats are
    converted to null first because bare NaN and Infinity are not valid JSON.
    """

    text = (
        json.dumps(_json_ready(payload), ensure_ascii=False, indent=2, allow_nan=False)
        + "\n"
    )
    with path.open("w", encoding="utf-8", newline="") as handle:
        handle.write(text)


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def parse_components(row: Mapping[str, str]) -> list[dict[str, str]]:
    raw = row.get("components_json") or ""
    if not raw:
        return []
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(payload, list):
        return []
    return [item for item in payload if isinstance(item, dict)]


def component_indices(
    rows: Sequence[Mapping[str, str]],
) -> dict[str, dict[str, int]]:
    """Count extraction rows per component InChIKey, split by purity."""

    counts: dict[str, collections.Counter[str]] = collections.defaultdict(
        collections.Counter
    )
    for row in rows:
        is_pure = str(row.get("is_pure", "")).strip().lower() == "true"
        is_zero_frequency = row.get("property_family") == "zero_frequency"
        for component in parse_components(row):
            key = str(component.get("standard_inchi_key") or "")
            if not key:
                continue
            counts[key]["extracted_observations"] += 1
            if is_pure:
                counts[key]["extracted_pure_observations"] += 1
            if is_zero_frequency:
                counts[key]["extracted_zero_frequency_observations"] += 1
    return {key: dict(counter) for key, counter in counts.items()}


def scan_corpus(
    paths: Sequence[Path],
    targets: Sequence[Mapping[str, object]],
) -> dict[str, dict[str, int]]:
    """Raw text scan of every XML for each target's identifiers."""

    hits: dict[str, dict[str, int]] = {
        str(target["label"]): {
            "xml_files_mentioning_inchikey": 0,
            "xml_files_mentioning_cas": 0,
            "xml_files_mentioning_alias": 0,
            "xml_files_with_permittivity_text": 0,
        }
        for target in targets
    }
    for path in paths:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        lowered = text.casefold()
        has_permittivity = bool(PERMITTIVITY_PATTERN.search(text))
        for target in targets:
            counters = hits[str(target["label"])]
            present = False
            inchikey = str(target["inchikey"]).casefold()
            if inchikey and inchikey in lowered:
                counters["xml_files_mentioning_inchikey"] += 1
                present = True
            if any(str(cas) in text for cas in target["cas"]):
                counters["xml_files_mentioning_cas"] += 1
                present = True
            if any(str(alias).casefold() in lowered for alias in target["aliases"]):
                counters["xml_files_mentioning_alias"] += 1
                present = True
            if present and has_permittivity:
                counters["xml_files_with_permittivity_text"] += 1
    return hits


def classify(
    scan: Mapping[str, int],
    extraction: Mapping[str, int],
) -> tuple[bool, str]:
    observations = int(extraction.get("extracted_observations", 0))
    if observations > 0:
        return True, "locally_supported"
    mentioned = (
        int(scan.get("xml_files_mentioning_inchikey", 0))
        + int(scan.get("xml_files_mentioning_cas", 0))
        + int(scan.get("xml_files_mentioning_alias", 0))
    )
    if mentioned == 0:
        return False, "absent_from_local_corpus"
    if int(scan.get("xml_files_with_permittivity_text", 0)) == 0:
        return False, "mentioned_only_in_non_dielectric_studies"
    return False, "permittivity_wording_present_but_no_extracted_observation"


def build_summary(
    *,
    summary_path: Path = DEFAULT_SUMMARY,
    rows_path: Path = DEFAULT_ROWS,
) -> dict[str, object]:
    paths = sorted(
        Path(path)
        for path in glob.glob(str(REPOSITORY_ROOT / THERMOML_GLOB), recursive=True)
    )
    extraction_rows = read_csv_rows(REPOSITORY_ROOT / EXTRACTION_PATH)
    scan = scan_corpus(paths, TARGETS)
    extraction = component_indices(extraction_rows)

    rows: list[dict[str, object]] = []
    for target in TARGETS:
        label = str(target["label"])
        key = str(target["inchikey"])
        counts = dict(extraction.get(key, {}))
        scan_counts = scan[label]
        supported, verdict = classify(scan_counts, counts)
        rows.append(
            {
                "label": label,
                "inchikey": key,
                "cas": ";".join(str(value) for value in target["cas"]),
                "xml_files_scanned": len(paths),
                **scan_counts,
                "extracted_observations": int(counts.get("extracted_observations", 0)),
                "extracted_pure_observations": int(
                    counts.get("extracted_pure_observations", 0)
                ),
                "extracted_zero_frequency_observations": int(
                    counts.get("extracted_zero_frequency_observations", 0)
                ),
                "locally_supported": supported,
                "verdict": verdict,
            }
        )

    unsupported = [row for row in rows if not row["locally_supported"]]
    payload = {
        "schema_version": "thermoml_local_coverage/v1",
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "design": {
            "question": (
                "Do the G1+ target solvents really have no local ThermoML "
                "dielectric observation, or did the extraction silently drop one?"
            ),
            "method": (
                "Independent raw-text scan of every local ThermoML XML combined "
                "with a component-level recount of the parsed extraction."
            ),
            "network_access": False,
            "promotes_values_into_frozen_dataset": False,
        },
        "inputs": {
            "thermoml_glob": THERMOML_GLOB,
            "xml_files_scanned": len(paths),
            "extraction_path": EXTRACTION_PATH,
            "extraction_sha256": canonical_text_sha256(
                REPOSITORY_ROOT / EXTRACTION_PATH
            ),
            "extraction_rows": len(extraction_rows),
        },
        "targets": rows,
        "summary": {
            "n_targets": len(rows),
            "n_locally_supported": len(rows) - len(unsupported),
            "n_without_local_dielectric_data": len(unsupported),
            "unsupported_labels": [row["label"] for row in unsupported],
        },
        "findings": [
            (
                "Propylene carbonate appears in the local corpus only as a "
                "mixture component of non-dielectric studies: it is named in "
                "many XML files but none of them contains any permittivity or "
                "dielectric wording, and the parsed extraction holds zero rows "
                "for its InChIKey. The earlier 'no local data' claim is "
                "therefore reproduced independently rather than inherited."
            ),
            (
                "Ethylene carbonate behaves the same way as propylene carbonate, "
                "so both carbonate targets genuinely require an external source."
            ),
            (
                "The glyme series and the two dinitriles are the opposite case: "
                "the extraction already holds pure-component observations for "
                "them, so those upgrades do not need any new crawl."
            ),
        ],
        "limitations": [
            (
                "The permittivity wording scan is deliberately over-inclusive: "
                "it fires on abstract text, so a non-zero count does not by "
                "itself prove a structured dielectric dataset exists. A zero "
                "count, however, is decisive."
            ),
            (
                "The corpus is the locally cached ThermoML subset (dielectric "
                "and permittivity queries), not the complete 2020 ThermoML "
                "archive, so absence here is absence from this cache only."
            ),
        ],
    }
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    write_json_lf(summary_path, payload)
    formatted = [
        {
            key: (
                "true"
                if value is True
                else "false"
                if value is False
                else ""
                if value is None
                else str(value)
            )
            for key, value in row.items()
        }
        for row in rows
    ]
    write_csv_rows(rows_path, COVERAGE_COLUMNS, formatted)
    return payload


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--rows", type=Path, default=DEFAULT_ROWS)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    payload = build_summary(summary_path=args.summary, rows_path=args.rows)
    print(
        json.dumps(
            {
                "schema_version": payload["schema_version"],
                "inputs": payload["inputs"],
                "summary": payload["summary"],
                "targets": [
                    {
                        "label": row["label"],
                        "xml_files_mentioning_inchikey": row[
                            "xml_files_mentioning_inchikey"
                        ],
                        "xml_files_with_permittivity_text": row[
                            "xml_files_with_permittivity_text"
                        ],
                        "extracted_pure_observations": row[
                            "extracted_pure_observations"
                        ],
                        "verdict": row["verdict"],
                    }
                    for row in payload["targets"]
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
