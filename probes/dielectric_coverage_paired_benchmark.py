"""Strictly paired coverage benchmark for the v1.x dielectric observation table.

This is the acceptance experiment of the v1.x line. W11 opened the temperature
gate on the local ThermoML cache, W12 showed that more temperature points do not
move grouped R2, and the compound-coverage curve showed the lever sits in
*compound* coverage instead. The frequency-gate probe then produced 435 extra
rows on 50 compounds that the v11 table never carried. This probe asks the only
question that still matters for the line: with the scored rows, the folds and the
denominator held fixed, what does that extra compound coverage buy as *training*
material?

Three things are held constant across the fixed-pool family, which is what makes
the deltas readable:

* the scored rows - the 457 room-band rows of the 97 v11 compounds that have xTB
  features;
* the fold assignment - dealt once over those 97 compounds and reused by every
  variant, so the scored side of every fold is identical;
* the metric denominators - a paired R2 delta therefore has exactly one cause.

Family 1 (fixed pool, the verdict) widens only the training material::

    protocol                training material                        scored rows
    paired_base             the 457 v11 room rows                    457 / 97 cpds
    paired_plus_coverage    + the 127 room rows of all 50 new cpds   457 / 97 cpds
    paired_plus_new_xtb     + only the 39 freshly run xTB cpds       457 / 97 cpds
    paired_plus_v03_block   + only the 11 frozen-v03-block cpds      457 / 97 cpds

The last two split the expansion by where the xTB features came from, so no claim
about "the newly admitted chemistry" can be carried by compounds the frozen v03
block already described.

Family 2 (extended pool) scores every room-band row of the merged table, grouped
over every compound that has features. Its target-pool variance is reported next
to every number because it is *not* the same denominator as family 1, and the two
families are therefore never ranked against each other.

`band_room_only` is re-run first and must reproduce the published Hybrid
R2 = 0.4091179943351143 bit for bit. If it does not, the probe still reports what
it measured but stamps the result unverified, because a coverage delta read off a
drifted pipeline would be worthless.

The probe is read-only with respect to every released artefact. It writes only
`probes/dielectric_coverage_paired_benchmark_summary.json` and the three
`probes/artifacts/dielectric_coverage_paired_benchmark_*.csv` tables. It performs
no network I/O. A row-level `random_row` splitter appears exactly once, clearly
labelled as a leak reference, and never enters a verdict.
"""

from __future__ import annotations

import argparse
import io
import json
import sys
from collections import Counter, defaultdict
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))
sys.path.insert(0, str(REPOSITORY_ROOT / "probes"))

import numpy as np
from dielectric_band_ablation import (
    INERT_TOLERANCE,
    MIN_TEST_ROWS_PER_FOLD,
    ROOM_BAND,
    classify,
    drop_thin_folds,
    effective_repeats,
)
from dielectric_observations_grouped_benchmark import (
    FEATURES_PATH,
    FOLD_COLUMNS,
    METRIC_NAMES,
    OBSERVATIONS_PATH,
    PREDICTION_COLUMNS,
    build_matrices,
    load_table,
    random_row_folds,
    run_protocol,
    summarize_repeats,
    write_csv_rows,
)
from dielectric_representation_ablation import (
    N_REPEATS,
    N_SPLITS,
    PHYSICAL_COLUMNS,
    REPRESENTATIONS,
    SEED,
    read_csv_rows,
)
from dielectric_room_window_paired import (
    HYBRID,
    PAIRED_METRICS,
    audit_masks,
    masked_splits,
    paired_delta,
    scored_fold_signature,
    target_pool_stats,
)

from electrolyte_ml.exporting import canonical_text_sha256
from electrolyte_ml.pathing import portable_relative_path

COVERAGE_PATH = REPOSITORY_ROOT / "data" / "processed" / "dielectric_observations_v11plus.csv"
COVERAGE_SUMMARY_PATH = (
    REPOSITORY_ROOT / "probes" / "dielectric_observations_v11plus_summary.json"
)
NEW_FEATURES_PATH = (
    REPOSITORY_ROOT / "data" / "processed" / "dielectric_physical_features_v11plus_new.csv"
)
ROOM_WINDOW_SUMMARY_PATH = (
    REPOSITORY_ROOT / "probes" / "dielectric_room_window_paired_summary.json"
)
SUMMARY_PATH = (
    REPOSITORY_ROOT / "probes" / "dielectric_coverage_paired_benchmark_summary.json"
)
ARTIFACTS_DIR = REPOSITORY_ROOT / "probes" / "artifacts"
ARTIFACT_STEM = "dielectric_coverage_paired_benchmark"

ZERO_FREQUENCY_ORIGIN = "thermoml_zero_frequency"
LOW_FREQUENCY_ORIGIN = "thermoml_low_frequency"
FROZEN_SOURCE = "frozen_v03"
NEW_XTB_SOURCE = "new_xtb"

#: The published `band_room_only` Hybrid R2 this probe has to reproduce before it
#: may call its own numbers verified. Pinned as a literal as well as read from the
#: reference JSON, so a drifting JSON cannot silently redefine the target.
ROOM_BAND_HYBRID_R2_REFERENCE = 0.4091179943351143
ROOM_BAND_REFERENCE_PROTOCOL = "band_room_only"

FIXED_POOL_PROTOCOLS = (
    "paired_base",
    "paired_plus_coverage",
    "paired_plus_new_xtb",
    "paired_plus_v03_block",
)
EXTENDED_POOL_PROTOCOLS = ("extended_pool_room",)
LEAK_REFERENCE_PROTOCOL = "extended_pool_room_random_row"
#: Protocols that share one fold assignment and one scored row set.
FIXED_POOL_SHARED = (
    "paired_base",
    "paired_plus_coverage",
    "paired_plus_new_xtb",
    "paired_plus_v03_block",
)
#: The paired steps, as (base, widened) protocol pairs.
FIXED_POOL_CHAIN = (
    ("paired_base", "paired_plus_coverage"),
    ("paired_base", "paired_plus_new_xtb"),
    ("paired_base", "paired_plus_v03_block"),
)

PROTOCOL_DESCRIPTIONS = {
    "band_room_only": (
        "the frozen room-band reference protocol: train and score on the 457 v11 room rows, "
        "grouped 10x5, re-run here to prove this probe inherits the frozen pipeline"
    ),
    "paired_base": "train and score on the frozen v11 room-temperature rows, grouped 10x5",
    "paired_plus_coverage": (
        "train on the v11 room rows plus the room rows of every new compound the frequency gate "
        "admitted; score the same frozen v11 room rows on the same folds"
    ),
    "paired_plus_new_xtb": (
        "same scored rows and folds as paired_base, training widened only by the new compounds "
        "whose xTB features were computed in this round"
    ),
    "paired_plus_v03_block": (
        "same scored rows and folds as paired_base, training widened only by the new compounds "
        "whose features already sat in the frozen v03 block"
    ),
    "extended_pool_room": (
        "train and score on every room-temperature row of the merged table, grouped over every "
        "compound that has features"
    ),
    LEAK_REFERENCE_PROTOCOL: (
        "LEAK REFERENCE ONLY: same rows as extended_pool_room but split by row, so one compound "
        "reaches both sides of a fold. Never a conclusion number."
    ),
}

FINGERPRINT_COLUMNS = ("inchikey", "T_K", "epsilon", "smiles", "source_doi", "source_row_index")


def _use_utf8_stdout() -> None:
    """Windows consoles are GBK, so force UTF-8 before printing the report."""

    encoding = (getattr(sys.stdout, "encoding", "") or "").lower()
    if "utf-8" in encoding or "utf8" in encoding:
        return
    buffer = getattr(sys.stdout, "buffer", None)
    if buffer is not None:
        sys.stdout = io.TextIOWrapper(buffer, encoding="utf-8", errors="replace")


def row_fingerprint(
    row: Mapping[str, object],
    columns: Sequence[str] = FINGERPRINT_COLUMNS,
) -> tuple[str, ...]:
    """A stable identity for an observation row, used for cross-table checks."""

    return tuple(str(row[column]) for column in columns)


def read_feature_block(
    path: Path,
    *,
    source: str,
) -> tuple[dict[str, dict[str, str]], dict[str, object]]:
    """Read one xTB feature block, keeping only rows a model can actually use.

    A row is usable when its `status` is not `error` and every physical column
    is non-empty. The frozen v03 reader in
    `dielectric_representation_ablation.read_modelling_rows` refuses an
    incomplete row by raising; here the row is counted and skipped instead, so a
    block that is thinner than advertised shows up as a number rather than as a
    crash halfway through a benchmark.
    """

    usable: dict[str, dict[str, str]] = {}
    errored: list[str] = []
    incomplete: list[str] = []
    duplicates: list[str] = []
    for row in read_csv_rows(path):
        key = row["inchikey"]
        if row.get("status") == "error":
            errored.append(key)
            continue
        if any(not row.get(column, "").strip() for column in PHYSICAL_COLUMNS):
            incomplete.append(key)
            continue
        if key in usable:
            duplicates.append(key)
            continue
        usable[key] = {**row, "_feature_source": source}
    return usable, {
        "path": portable_relative_path(path, root=REPOSITORY_ROOT),
        "sha256": canonical_text_sha256(path),
        "source": source,
        "usable": len(usable),
        "errored": len(errored),
        "errored_keys": sorted(errored),
        "incomplete": len(incomplete),
        "incomplete_keys": sorted(incomplete),
        "duplicate_keys": sorted(duplicates),
    }


def merge_feature_blocks(
    frozen_path: Path = FEATURES_PATH,
    new_path: Path = NEW_FEATURES_PATH,
) -> tuple[dict[str, dict[str, str]], dict[str, object]]:
    """Merge the frozen v03 block with this round's xTB run.

    The frozen block wins on overlap: it is the released one, and the new run
    exists only to fill the holes v03 left. Overlapping keys are still compared
    column by column, so an overlap that disagrees is reported instead of being
    hidden behind the precedence rule.
    """

    frozen, frozen_report = read_feature_block(frozen_path, source=FROZEN_SOURCE)
    new, new_report = read_feature_block(new_path, source=NEW_XTB_SOURCE)
    merged: dict[str, dict[str, str]] = dict(frozen)
    overlap: list[str] = []
    for key, row in new.items():
        if key in merged:
            overlap.append(key)
            continue
        merged[key] = row
    disagreements: dict[str, list[str]] = {}
    for key in sorted(overlap):
        different = [
            column
            for column in PHYSICAL_COLUMNS
            if frozen[key].get(column, "").strip() != new[key].get(column, "").strip()
        ]
        if different:
            disagreements[key] = different
    return merged, {
        "frozen": frozen_report,
        "new": new_report,
        "merged_usable": len(merged),
        "usable_from_frozen": len(frozen) - len(overlap),
        "usable_from_new": len(new) - len(overlap),
        "overlap_keys": sorted(overlap),
        "overlap_physical_column_disagreements": disagreements,
    }


def load_coverage_table(
    observations_path: Path,
    features: Mapping[str, Mapping[str, str]],
) -> tuple[list[dict[str, object]], dict[str, int]]:
    """The merged observation table, gated exactly like the frozen W12 loader.

    Same gates in the same order as
    `dielectric_observations_grouped_benchmark.load_table`: a usable xTB feature
    row, a non-empty SMILES, and every physical column present. Reproducing the
    frozen loader rather than inventing a new one is what lets the base protocol be
    compared to the published `band_room_only` number at all.
    """

    kept: list[dict[str, object]] = []
    dropped: dict[str, int] = defaultdict(int)
    for row in read_csv_rows(observations_path):
        feature = features.get(row["inchikey"])
        if feature is None:
            dropped["no_xtb_features"] += 1
            continue
        if not row["smiles"].strip():
            dropped["no_smiles"] += 1
            continue
        kept.append(
            {
                **row,
                "_features": feature,
                "_feature_source": feature["_feature_source"],
            }
        )
    return kept, {key: int(value) for key, value in dropped.items()}


def frozen_table_agreement(
    v11_rows: Sequence[Mapping[str, object]],
    coverage_rows: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    """Prove the merged table's v11 block is the frozen loader's own output.

    The base protocol is only bit-comparable to `band_room_only` if its rows are
    the same rows in the same order, because XGBoost's subsampling draws depend on
    row order. This compares the merged table's zero-frequency block against
    `load_table(v11)` by fingerprint, in order and as a set.
    """

    frozen = [row_fingerprint(row) for row in v11_rows]
    zero_frequency = [
        row_fingerprint(row)
        for row in coverage_rows
        if str(row["observation_origin"]) == ZERO_FREQUENCY_ORIGIN
    ]
    return {
        "frozen_loader_rows": len(frozen),
        "coverage_zero_frequency_rows": len(zero_frequency),
        "order_identical": frozen == zero_frequency,
        "set_identical": set(frozen) == set(zero_frequency),
    }


def new_compound_inventory(
    coverage_rows: Sequence[Mapping[str, object]],
    v11_keys: set[str],
) -> dict[str, object]:
    """Every compound the merged table adds, with the room rows it can train on."""

    per: dict[str, dict[str, object]] = {}
    for row in coverage_rows:
        key = str(row["inchikey"])
        if key in v11_keys:
            continue
        entry = per.get(key)
        if entry is None:
            entry = {
                "name": str(row["name"]),
                "feature_source": str(row["_feature_source"]),
                "rows_total": 0,
                "rows_by_band": defaultdict(int),
                "room_rows": 0,
                "source_dois": set(),
            }
            per[key] = entry
        entry["rows_total"] = int(entry["rows_total"]) + 1
        band = str(row["temperature_band"])
        rows_by_band = entry["rows_by_band"]
        assert isinstance(rows_by_band, defaultdict)
        rows_by_band[band] += 1
        if band == ROOM_BAND:
            entry["room_rows"] = int(entry["room_rows"]) + 1
        source_dois = entry["source_dois"]
        assert isinstance(source_dois, set)
        source_dois.add(str(row["source_doi"]))

    compounds: dict[str, dict[str, object]] = {}
    for key, entry in per.items():
        compounds[key] = {
            "name": entry["name"],
            "feature_source": entry["feature_source"],
            "rows_total": entry["rows_total"],
            "rows_by_band": dict(sorted(entry["rows_by_band"].items())),  # type: ignore[arg-type]
            "room_rows": entry["room_rows"],
            "source_dois": sorted(entry["source_dois"]),  # type: ignore[arg-type]
        }
    room_rows = np.asarray([int(item["room_rows"]) for item in compounds.values()], dtype=int)
    by_source = Counter(str(item["feature_source"]) for item in compounds.values())
    return {
        "compounds": len(compounds),
        "compounds_by_feature_source": dict(sorted(by_source.items())),
        "rows_total": int(sum(int(item["rows_total"]) for item in compounds.values())),
        "room_rows_total": int(room_rows.sum()) if room_rows.size else 0,
        "compounds_with_a_room_row": int((room_rows > 0).sum()) if room_rows.size else 0,
        "room_row_histogram": {
            str(count): int(frequency)
            for count, frequency in sorted(Counter(room_rows.tolist()).items())
        },
        "per_compound": dict(sorted(compounds.items())),
    }


def featureless_compound_report(
    observations_path: Path,
    features: Mapping[str, Mapping[str, str]],
) -> dict[str, object]:
    """Compounds the merged feature set cannot describe, and what each one costs.

    A compound with no xTB row is not a modelling row, so its observations reach
    neither family. Reporting them by name and by band is what stops the coverage
    story from being told over a silently shrunken compound pool.
    """

    by_compound: dict[str, dict[str, object]] = {}
    for row in read_csv_rows(observations_path):
        key = row["inchikey"]
        if key in features:
            continue
        entry = by_compound.get(key)
        if entry is None:
            entry = {
                "name": row["name"],
                "origins": set(),
                "rows_by_band": defaultdict(int),
                "rows_total": 0,
            }
            by_compound[key] = entry
        origins = entry["origins"]
        assert isinstance(origins, set)
        origins.add(row["observation_origin"])
        rows_by_band = entry["rows_by_band"]
        assert isinstance(rows_by_band, defaultdict)
        rows_by_band[row["temperature_band"]] += 1
        entry["rows_total"] = int(entry["rows_total"]) + 1
    return {
        "compounds": len(by_compound),
        "rows_total": int(sum(int(item["rows_total"]) for item in by_compound.values())),
        "per_compound": {
            key: {
                "name": item["name"],
                "origins": sorted(item["origins"]),  # type: ignore[arg-type]
                "rows_by_band": dict(sorted(item["rows_by_band"].items())),  # type: ignore[arg-type]
                "rows_total": item["rows_total"],
            }
            for key, item in sorted(by_compound.items())
        },
    }


def own_mode_random_row_splits(
    mask: Sequence[bool],
    *,
    n_splits: int = N_SPLITS,
    n_repeats: int = N_REPEATS,
    seed: int = SEED,
) -> Iterator[tuple[int, int, np.ndarray, np.ndarray]]:
    """A row-level splitter over a masked row pool, for the leak reference only."""

    index_mask = np.asarray(mask, dtype=bool)
    local = np.flatnonzero(index_mask)
    for repeat, fold, train_local, test_local in random_row_folds(
        int(local.size), n_splits=n_splits, n_repeats=n_repeats, seed=seed
    ):
        yield repeat, fold, local[train_local], local[test_local]


def run_coverage_protocol(
    protocol: str,
    *,
    splitter: str,
    morgan: np.ndarray,
    physical: np.ndarray,
    target: np.ndarray,
    temperatures: Sequence[float],
    groups: Sequence[str],
    score_mask: Sequence[bool],
    train_mask: Sequence[bool],
    n_splits: int,
    n_repeats: int,
    seed: int,
) -> dict[str, object]:
    """Run one protocol and return its rows, its mask audit and its splits.

    The splitter is selected rather than assumed: `grouped` holds whole compounds
    out and is the only mode a conclusion may be drawn from, while `random_row`
    exists to measure the leak it creates and is stamped as such by the caller.
    """

    if splitter not in ("grouped", "random_row"):
        raise ValueError(f"unknown splitter: {splitter}")
    group_array = np.asarray(groups)
    score = np.asarray(score_mask, dtype=bool)
    train = np.asarray(train_mask, dtype=bool)
    if target.size != group_array.size:
        raise ValueError("target and group arrays must describe the same rows")
    compound_count = int(np.unique(group_array[score]).size)
    repeats, note = effective_repeats(compound_count, n_splits=n_splits, requested=n_repeats)
    meta: dict[str, object] = {
        "description": PROTOCOL_DESCRIPTIONS[protocol],
        "splitter": splitter,
        "scored_rows": int(score.sum()),
        "compounds_scored": compound_count,
        "train_pool_rows": int(train.sum()),
        "train_pool_compounds": int(np.unique(group_array[train]).size),
        "requested_repeats": n_repeats,
        "executed_repeats": repeats,
        "note": note,
    }
    if repeats == 0:
        meta.update(
            {
                "folds": 0,
                "train_rows_mean": None,
                "train_compounds_mean": None,
                "test_rows_mean": None,
                "test_compounds_mean": None,
            }
        )
        return {
            "meta": meta,
            "audit": {"note": note, "folds": 0},
            "fold_rows": [],
            "repeat_rows": [],
            "prediction_rows": [],
            "splits": [],
        }

    if splitter == "grouped":
        raw = masked_splits(
            groups,
            score_mask=score,
            train_mask=train,
            n_splits=n_splits,
            n_repeats=repeats,
            seed=seed,
        )
    else:
        raw = own_mode_random_row_splits(score, n_splits=n_splits, n_repeats=repeats, seed=seed)
    splits = list(drop_thin_folds(raw, min_test_rows=MIN_TEST_ROWS_PER_FOLD))
    if not splits:
        raise ValueError(f"{protocol}: no fold survived the thin-fold filter")
    audit = audit_masks(groups, score_mask=score, train_mask=train, splits=splits)
    if audit["scored_rows_outside_the_score_mask"]:
        raise ValueError(f"{protocol}: a scored row sits outside the score mask")
    if splitter == "grouped" and audit["folds_with_a_straddling_compound"]:
        raise ValueError(f"{protocol}: a compound straddles the fold boundary")

    meta.update(
        {
            "folds": len(splits),
            "train_rows_mean": float(np.mean([item[2].size for item in splits])),
            "train_compounds_mean": float(
                np.mean([np.unique(group_array[item[2]]).size for item in splits])
            ),
            "test_rows_mean": float(np.mean([item[3].size for item in splits])),
            "test_compounds_mean": float(
                np.mean([np.unique(group_array[item[3]]).size for item in splits])
            ),
        }
    )
    fold_rows, repeat_rows, prediction_rows, leak = run_protocol(
        protocol,
        iter(splits),
        morgan=morgan,
        physical=physical,
        target=target,
        temperatures=temperatures,
        groups=groups,
    )
    return {
        "meta": meta,
        "audit": audit,
        "fold_rows": fold_rows,
        "repeat_rows": repeat_rows,
        "prediction_rows": prediction_rows,
        "splits": splits,
        "run_protocol_leak": leak,
    }


def run_protocol_family(
    protocols: Sequence[str],
    *,
    splitters: Mapping[str, str],
    morgan: np.ndarray,
    physical: np.ndarray,
    target: np.ndarray,
    temperatures: Sequence[float],
    groups: Sequence[str],
    masks: Mapping[str, tuple[Sequence[bool], Sequence[bool]]],
    n_splits: int,
    n_repeats: int,
    seed: int,
) -> dict[str, object]:
    """Run a group of protocols, sharing one fold assignment across the family."""

    fold_rows: list[dict[str, object]] = []
    repeat_rows: list[dict[str, object]] = []
    prediction_rows: list[dict[str, object]] = []
    meta: dict[str, object] = {}
    audits: dict[str, object] = {}
    splits_by_protocol: dict[str, list[tuple[int, int, np.ndarray, np.ndarray]]] = {}
    for protocol in protocols:
        score_mask, train_mask = masks[protocol]
        result = run_coverage_protocol(
            protocol,
            splitter=splitters[protocol],
            morgan=morgan,
            physical=physical,
            target=target,
            temperatures=temperatures,
            groups=groups,
            score_mask=score_mask,
            train_mask=train_mask,
            n_splits=n_splits,
            n_repeats=n_repeats,
            seed=seed,
        )
        meta[protocol] = result["meta"]
        audits[protocol] = result["audit"]
        splits_by_protocol[protocol] = result["splits"]  # type: ignore[assignment]
        fold_rows.extend(result["fold_rows"])  # type: ignore[arg-type]
        repeat_rows.extend(result["repeat_rows"])  # type: ignore[arg-type]
        prediction_rows.extend(result["prediction_rows"])  # type: ignore[arg-type]

    shared = [name for name in protocols if name in FIXED_POOL_SHARED]
    signatures = {
        name: scored_fold_signature(splits_by_protocol[name])
        for name in shared
        if splits_by_protocol.get(name)
    }
    return {
        "protocols": meta,
        "audits": audits,
        "summary": summarize_repeats(repeat_rows),
        "target_pools": {
            name: target_pool_stats(target[np.asarray(masks[name][0], dtype=bool)])
            for name in protocols
        },
        "fold_rows": fold_rows,
        "repeat_rows": repeat_rows,
        "prediction_rows": prediction_rows,
        "splits_by_protocol": splits_by_protocol,
        "folds_shared_by": shared,
        "shared_fold_basis": "the scored room-band rows of every fold, repeat by repeat",
        "folds_are_shared": len(set(signatures.values())) == 1
        and len(signatures) == len(shared),
    }


def read_room_band_reference(
    path: Path = ROOM_WINDOW_SUMMARY_PATH,
) -> dict[str, object]:
    """Read the published `band_room_only` metrics this probe must reproduce."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    try:
        published = payload["window_family"]["summary"][ROOM_BAND_REFERENCE_PROTOCOL]
        hybrid_r2 = float(published[HYBRID]["r2"]["mean"])
    except (KeyError, TypeError) as error:
        raise ValueError(f"cannot read the frozen room-band reference: {error}") from error
    return {
        "path": portable_relative_path(path, root=REPOSITORY_ROOT),
        "sha256": canonical_text_sha256(path),
        "protocol": ROOM_BAND_REFERENCE_PROTOCOL,
        "published": published,
        "published_hybrid_r2": hybrid_r2,
        "matches_literal": hybrid_r2 == ROOM_BAND_HYBRID_R2_REFERENCE,
    }


def compare_room_band_reference(
    summary: Mapping[str, Mapping[str, Mapping[str, Mapping[str, float]]]],
    reference: Mapping[str, object],
) -> dict[str, object]:
    """Diff this probe's re-run of `band_room_only` against the published numbers."""

    published = reference.get("published") or {}
    mine = summary.get(ROOM_BAND_REFERENCE_PROTOCOL)
    if not mine or not isinstance(published, Mapping):
        return {"available": False, "bit_exact": None, "reason": "reference or re-run missing"}
    per_representation: dict[str, object] = {}
    for representation in REPRESENTATIONS:
        if representation not in mine or representation not in published:
            continue
        deltas: dict[str, float] = {}
        for metric in METRIC_NAMES:
            other = published[representation].get(metric)  # type: ignore[union-attr]
            if metric not in mine[representation]:
                continue
            if not isinstance(other, Mapping) or other.get("mean") is None:
                continue
            deltas[metric] = float(mine[representation][metric]["mean"]) - float(other["mean"])
        per_representation[representation] = {
            "deltas": deltas,
            "max_abs_delta": max((abs(value) for value in deltas.values()), default=0.0),
            # An empty delta dict is not a pass: it is an unverifiable comparison.
            "bit_exact": bool(deltas) and all(value == 0.0 for value in deltas.values()),
        }
    hybrid = mine.get(HYBRID, {}).get("r2", {}).get("mean")
    return {
        "available": bool(per_representation),
        "protocol": ROOM_BAND_REFERENCE_PROTOCOL,
        "representations": per_representation,
        "max_abs_delta": max(
            (float(item["max_abs_delta"]) for item in per_representation.values()),
            default=0.0,
        ),
        "bit_exact": bool(per_representation)
        and all(bool(item["bit_exact"]) for item in per_representation.values()),
        "hybrid_r2": None if hybrid is None else float(hybrid),
        "hybrid_r2_expected": reference.get("published_hybrid_r2"),
    }


def protocol_block(*, seed: int, n_repeats: int) -> dict[str, object]:
    return {
        "validation": (
            "group K-fold by InChIKey: a fresh permutation of the sorted compound keys per "
            "repeat, dealt round-robin, whole compounds held out"
        ),
        "leak_reference": "row-level random_row, reported once to size the leak it creates",
        "n_splits": N_SPLITS,
        "n_repeats": n_repeats,
        "random_state": seed,
        "model": "XGBRegressor with the frozen v1.0 hyper-parameters",
        "representations": list(REPRESENTATIONS),
        "physical_block": "frozen xTB vector with T_K replaced by the observation's T_K",
        "min_test_rows_per_fold": MIN_TEST_ROWS_PER_FOLD,
        "paired_rule": (
            "folds are dealt over the compounds of the scored mask only, so protocols that score "
            "the same rows share one fold assignment even when their training pools differ"
        ),
    }


def metric_mean(
    summary: Mapping[str, Mapping[str, Mapping[str, Mapping[str, float]]]],
    protocol: str,
    representation: str,
    metric: str,
) -> float:
    return float(summary[protocol][representation][metric]["mean"])



def room_gate_audit(
    observations_path: Path,
    features: Mapping[str, Mapping[str, str]],
) -> dict[str, object]:
    """Room-band rows before and after the xTB gate, split by origin.

    A compound that never got an xTB row cannot be modelled, so its observations
    leave the pool silently unless they are counted. The three ionic liquids in
    the local cache are exactly this case, and they belong to the *v11* side, not
    to the newly admitted one, which is why the new-compound coverage is not
    understated by their absence.
    """

    before: Counter = Counter()
    after: Counter = Counter()
    lost: dict[str, dict[str, object]] = {}
    for row in read_csv_rows(observations_path):
        if row["temperature_band"] != ROOM_BAND:
            continue
        origin = row["observation_origin"]
        before[origin] += 1
        if row["inchikey"] in features:
            after[origin] += 1
            continue
        entry = lost.setdefault(
            row["inchikey"],
            {"name": row["name"], "origin": origin, "room_rows": 0},
        )
        entry["room_rows"] = int(entry["room_rows"]) + 1
    return {
        "before_the_feature_gate": dict(sorted(before.items())),
        "after_the_feature_gate": dict(sorted(after.items())),
        "before_total": int(sum(before.values())),
        "after_total": int(sum(after.values())),
        "compounds_losing_room_rows": dict(sorted(lost.items())),
    }


def value_stats(values: np.ndarray) -> dict[str, object]:
    """Summary of one block of permittivity targets."""

    values = np.asarray(values, dtype=float)
    if values.size == 0:
        return {"rows": 0}
    return {
        "rows": int(values.size),
        "mean": float(values.mean()),
        "var": float(values.var()),
        "min": float(values.min()),
        "p25": float(np.quantile(values, 0.25)),
        "median": float(np.median(values)),
        "p75": float(np.quantile(values, 0.75)),
        "max": float(values.max()),
        "rows_above_60": int((values > 60.0).sum()),
    }


def added_row_targets(
    masks: Mapping[str, tuple[Sequence[bool], Sequence[bool]]],
    target: np.ndarray,
    keys: np.ndarray,
) -> dict[str, object]:
    """The permittivity distribution of the rows each widening step adds.

    A widening step can only move the metric by changing what the trees see, so
    the added targets are reported next to the delta: a pool that shifts towards
    the low end dilutes the high-permittivity end the model is scored on.
    """

    base_train = np.asarray(masks["paired_base"][1], dtype=bool)
    out: dict[str, object] = {
        "paired_base_pool": value_stats(np.asarray(target, dtype=float)[base_train]),
    }
    for protocol in FIXED_POOL_PROTOCOLS:
        if protocol == "paired_base":
            continue
        train_mask = np.asarray(masks[protocol][1], dtype=bool)
        added = train_mask & ~base_train
        out[protocol] = {
            "rows_added": int(added.sum()),
            "compounds_added": int(np.unique(keys[added]).size),
            "added": value_stats(np.asarray(target, dtype=float)[added]),
        }
    return out

def training_expansion(
    masks: Mapping[str, tuple[Sequence[bool], Sequence[bool]]],
    *,
    splits_by_protocol: Mapping[str, Sequence[tuple[int, int, np.ndarray, np.ndarray]]],
) -> dict[str, object]:
    """How much training material each widening step actually adds.

    `rows_added_over_base` is the pool-level widening; `extra_rows_fitted_per_fold_mean`
    is counted from the folds that were really run, so it cannot disagree with the
    benchmark. The two differ whenever the added rows belong to compounds outside the
    scored pool: those carry no fold, so every fold may fit all of them.
    """

    base_train = np.asarray(masks["paired_base"][1], dtype=bool)
    base_splits = splits_by_protocol["paired_base"]
    if not base_splits:
        raise ValueError("paired_base produced no folds to measure the widening against")
    table: dict[str, object] = {}
    for protocol in FIXED_POOL_PROTOCOLS:
        train_mask = np.asarray(masks[protocol][1], dtype=bool)
        splits = splits_by_protocol[protocol]
        extras: list[int] = []
        for base_split, split in zip(base_splits, splits, strict=False):
            if (split[0], split[1]) != (base_split[0], base_split[1]):
                raise ValueError(f"{protocol}: fold order does not match paired_base")
            extras.append(int(split[2].size - base_split[2].size))
        table[protocol] = {
            "train_pool_rows": int(train_mask.sum()),
            "rows_added_over_base": int(train_mask.sum() - base_train.sum()),
            "folds_compared": len(extras),
            "extra_rows_fitted_per_fold_mean": float(np.mean(extras)) if extras else 0.0,
            "extra_rows_fitted_per_fold_min": int(min(extras)) if extras else 0,
            "extra_rows_fitted_per_fold_max": int(max(extras)) if extras else 0,
            "extra_rows_fitted_total": int(sum(extras)),
        }
    return table


def splitter_contract(block: Mapping[str, object]) -> dict[str, object]:
    """Re-derive the shared-scored-row contract of the fixed-pool family."""

    protocols = block["protocols"]
    assert isinstance(protocols, Mapping)
    names = list(FIXED_POOL_PROTOCOLS)
    scored = {int(protocols[name]["scored_rows"]) for name in names}  # type: ignore[index]
    compounds = {int(protocols[name]["compounds_scored"]) for name in names}  # type: ignore[index]
    folds = {int(protocols[name]["folds"]) for name in names}  # type: ignore[index]
    return {
        "protocols": names,
        "scored_rows_identical": len(scored) == 1,
        "scored_rows": sorted(scored),
        "compounds_scored_identical": len(compounds) == 1,
        "compounds_scored": sorted(compounds),
        "fold_counts_identical": len(folds) == 1,
        "fold_counts": sorted(folds),
        "folds_are_shared": bool(block.get("folds_are_shared")),
    }


def leak_comparison(
    summary: Mapping[str, Mapping[str, Mapping[str, Mapping[str, float]]]],
    audits: Mapping[str, Mapping[str, object]],
) -> dict[str, object]:
    """Size the leak a row-level splitter creates on the same rows, and nothing more."""

    grouped = "extended_pool_room"
    reference = LEAK_REFERENCE_PROTOCOL
    if grouped not in summary or reference not in summary:
        return {"available": False}
    grouped_audit = audits[grouped]
    reference_audit = audits[reference]
    folds = max(int(grouped_audit["folds"]), 1)
    return {
        "available": True,
        "scored_rows_per_fold": int(grouped_audit["scored_rows_total"]) // folds,
        "grouped": {
            metric: metric_mean(summary, grouped, HYBRID, metric) for metric in PAIRED_METRICS
        },
        "random_row": {
            metric: metric_mean(summary, reference, HYBRID, metric) for metric in PAIRED_METRICS
        },
        "inflation": {
            metric: metric_mean(summary, reference, HYBRID, metric)
            - metric_mean(summary, grouped, HYBRID, metric)
            for metric in PAIRED_METRICS
        },
        "grouped_folds_with_a_straddling_compound": int(
            grouped_audit["folds_with_a_straddling_compound"]
        ),
        "random_row_folds_with_a_straddling_compound": int(
            reference_audit["folds_with_a_straddling_compound"]
        ),
        "grouped_max_straddling_compounds_in_a_fold": int(
            grouped_audit["max_straddling_compounds_in_a_fold"]
        ),
        "random_row_max_straddling_compounds_in_a_fold": int(
            reference_audit["max_straddling_compounds_in_a_fold"]
        ),
        "note": "reported to size the leak only; never a conclusion number",
    }


def build_verdict(
    chain: Sequence[Mapping[str, object]],
    *,
    integrity: Mapping[str, object],
    added_compounds: int,
) -> dict[str, object]:
    """Turn the primary paired delta into the line's accept-or-reject decision."""

    primary = next((item for item in chain if item.get("widened") == "paired_plus_coverage"), None)
    integrity_ok = bool(integrity.get("ok"))
    if primary is None or not primary.get("available"):
        return {
            "integrity_ok": integrity_ok,
            "available": False,
            "decision": "not run",
            "statement": "the primary paired step did not run",
        }
    delta_r2 = float(primary["delta_r2"])  # type: ignore[arg-type]
    decision = classify(delta_r2, tolerance=INERT_TOLERANCE) if integrity_ok else "unverified"
    metrics = primary["metrics"]
    assert isinstance(metrics, Mapping)
    return {
        "integrity_ok": integrity_ok,
        "available": True,
        "primary_step": "paired_base -> paired_plus_coverage",
        "representation": HYBRID,
        "tolerance": INERT_TOLERANCE,
        "delta_r2": delta_r2,
        "delta_mae": float(metrics["mae"]["delta"]),  # type: ignore[index]
        "delta_spearman": float(metrics["spearman"]["delta"]),  # type: ignore[index]
        "decision": decision,
        "statement": (
            f"{added_compounds} compounds added to the training material move grouped {HYBRID} R2 "
            f"by {delta_r2:+.4f} ({decision})"
        ),
    }

def format_report(summary: Mapping[str, object]) -> list[str]:
    """Render the console report, in the order the question was asked."""

    inputs = summary["inputs"]
    agreement = summary["frozen_table_agreement"]
    reference = summary["reference_check"]
    fixed = summary["fixed_pool_family"]
    extended = summary["extended_pool_family"]
    inventory = summary["new_compound_inventory"]
    assert isinstance(inputs, Mapping)
    assert isinstance(agreement, Mapping)
    assert isinstance(reference, Mapping)
    assert isinstance(fixed, Mapping)
    assert isinstance(extended, Mapping)
    assert isinstance(inventory, Mapping)

    lines: list[str] = []
    lines.append("v1.x coverage acceptance - what do the newly admitted compounds buy?")
    lines.append("")
    lines.append(
        "inputs        : {rows} modelling rows / {cpds} compounds "
        "({low} low-frequency rows / {lowc} compounds on top of v11)".format(
            rows=inputs["coverage_rows"],
            cpds=inputs["coverage_compounds"],
            low=inputs["low_frequency_rows"],
            lowc=inputs["low_frequency_compounds"],
        )
    )
    lines.append(
        "row identity  : merged v11 block order-identical to the frozen loader: {}".format(
            agreement["order_identical"]
        )
    )
    lines.append(
        "reference     : band_room_only Hybrid R2 = {} (expected {}), bit_exact={}".format(
            reference.get("hybrid_r2"),
            reference.get("hybrid_r2_expected"),
            reference.get("bit_exact"),
        )
    )
    lines.append(
        "                paired_base re-run vs the same published numbers: bit_exact={}".format(
            summary["paired_base_check"]["bit_exact"]
        )
    )
    lines.append("")
    lines.append(
        "fixed pool    : {rows} scored rows / {cpds} compounds, pool var {var:.4f}, "
        "one fold assignment shared by {n} protocols".format(
            rows=fixed["protocols"]["paired_base"]["scored_rows"],
            cpds=fixed["protocols"]["paired_base"]["compounds_scored"],
            var=fixed["target_pools"]["paired_base"]["var"],
            n=len(fixed["folds_shared_by"]),
        )
    )
    contract = fixed["scored_row_contract"]
    lines.append(
        "                scored rows / compounds / fold counts identical: {}/{}/{}".format(
            contract["scored_rows_identical"],
            contract["compounds_scored_identical"],
            contract["fold_counts_identical"],
        )
    )
    block = fixed["summary"]
    for protocol in FIXED_POOL_PROTOCOLS:
        meta = fixed["protocols"][protocol]
        lines.append(
            "  {name:23s} R2 {r2:7.4f}  MAE {mae:6.3f}  rho {rho:6.4f}  "
            "train {rows:5d} rows / {cpds:3d} cpds".format(
                name=protocol,
                r2=metric_mean(block, protocol, HYBRID, "r2"),
                mae=metric_mean(block, protocol, HYBRID, "mae"),
                rho=metric_mean(block, protocol, HYBRID, "spearman"),
                rows=meta["train_pool_rows"],
                cpds=meta["train_pool_compounds"],
            )
        )
    lines.append("")
    for step in fixed["chain"]:
        if not step.get("available"):
            continue
        metrics = step["metrics"]
        lines.append(
            "  delta {base} -> {widened}: dR2 {dr2:+.4f} (dMAE {dmae:+.4f}, "
            "drho {drho:+.4f}) -> {verdict}".format(
                base=step["base"],
                widened=step["widened"],
                dr2=step["delta_r2"],
                dmae=metrics["mae"]["delta"],
                drho=metrics["spearman"]["delta"],
                verdict=step["verdict"],
            )
        )
    lines.append("")
    lines.append(
        "extended pool : {rows} scored rows / {cpds} compounds, pool var {var:.4f} "
        "(NOT comparable to the {ref:.4f} pool of the fixed family)".format(
            rows=extended["protocols"]["extended_pool_room"]["scored_rows"],
            cpds=extended["protocols"]["extended_pool_room"]["compounds_scored"],
            var=extended["target_pools"]["extended_pool_room"]["var"],
            ref=fixed["target_pools"]["paired_base"]["var"],
        )
    )
    lines.append(
        "  extended_pool_room           R2 {r2:7.4f}  MAE {mae:6.3f}  rho {rho:6.4f}".format(
            r2=metric_mean(extended["summary"], "extended_pool_room", HYBRID, "r2"),
            mae=metric_mean(extended["summary"], "extended_pool_room", HYBRID, "mae"),
            rho=metric_mean(extended["summary"], "extended_pool_room", HYBRID, "spearman"),
        )
    )
    leak = extended["leak_reference"]
    if leak.get("available"):
        lines.append(
            "  random_row leak reference    R2 {r2:7.4f}  (inflation {d:+.4f}; grouped straddles "
            "{g}, random_row straddles {rr})".format(
                r2=leak["random_row"]["r2"],
                d=leak["inflation"]["r2"],
                g=leak["grouped_folds_with_a_straddling_compound"],
                rr=leak["random_row_folds_with_a_straddling_compound"],
            )
        )
    lines.append("")
    lines.append(
        "new compounds : {n} compounds, {rows} rows, {room} room rows; provenance {prov}".format(
            n=inventory["compounds"],
            rows=inventory["rows_total"],
            room=inventory["room_rows_total"],
            prov=inventory["compounds_by_feature_source"],
        )
    )
    lines.append(
        "                room rows -> compounds (histogram): {hist}".format(
            hist=inventory["room_row_histogram"]
        )
    )
    gate = summary["room_gate_audit"]
    assert isinstance(gate, Mapping)
    lines.append(
        "feature gate  : room rows {before} -> {after} ({lost} compound(s) have no xTB row)".format(
            before=gate["before_total"],
            after=gate["after_total"],
            lost=len(gate["compounds_losing_room_rows"]),
        )
    )
    added = fixed["added_targets"]["paired_plus_coverage"]["added"]
    lines.append(
        "                added rows carry mean eps {mean:.3f} (var {var:.3f}, "
        "{hi} above 60) vs the base pool mean {bmean:.3f}".format(
            mean=added["mean"],
            var=added["var"],
            hi=added["rows_above_60"],
            bmean=fixed["added_targets"]["paired_base_pool"]["mean"],
        )
    )
    expansion = fixed["training_expansion"]["paired_plus_coverage"]
    lines.append(
        "                effective training expansion: +{rows} pool rows, +{fold:.1f} rows "
        "actually fitted per fold, +{total} fitted rows across {n} folds".format(
            rows=expansion["rows_added_over_base"],
            fold=expansion["extra_rows_fitted_per_fold_mean"],
            total=expansion["extra_rows_fitted_total"],
            n=expansion["folds_compared"],
        )
    )
    lines.append("")
    verdict = summary["verdict"]
    lines.append("integrity     : {}".format("PASS" if verdict["integrity_ok"] else "FAILED"))
    lines.append("verdict       : {}".format(verdict["decision"]))
    lines.append(str(verdict["statement"]))
    return lines

def build_summary(
    *,
    seed: int,
    n_repeats: int,
    v11_rows: Sequence[Mapping[str, object]],
    v11_dropped: Mapping[str, int],
    coverage_rows: Sequence[Mapping[str, object]],
    coverage_dropped: Mapping[str, int],
    coverage_summary: Mapping[str, object],
    feature_report: Mapping[str, object],
    inventory: Mapping[str, object],
    featureless: Mapping[str, object],
    agreement: Mapping[str, object],
    room_gate: Mapping[str, object],
    added_targets: Mapping[str, object],
    reference: Mapping[str, object],
    reference_run: Mapping[str, object],
    fixed_family: Mapping[str, object],
    extended_family: Mapping[str, object],
    v11_compounds: int,
    low_frequency_rows: int,
    low_frequency_compounds: int,
) -> dict[str, object]:
    reference_check = compare_room_band_reference(reference_run["summary"], reference)  # type: ignore[arg-type]
    paired_base_check = compare_room_band_reference(
        {"band_room_only": fixed_family["summary"]["paired_base"]},  # type: ignore[index]
        reference,
    )
    chain = [
        paired_delta(fixed_family["summary"], base=base, widened=widened)  # type: ignore[arg-type]
        for base, widened in FIXED_POOL_CHAIN
    ]
    fixed_protocols = fixed_family["protocols"]
    assert isinstance(fixed_protocols, Mapping)
    integrity = {
        "merged_v11_block_order_identical": bool(agreement["order_identical"]),
        "reference_json_matches_the_pinned_literal": bool(reference["matches_literal"]),
        "band_room_only_bit_exact": bool(reference_check["bit_exact"]),
        "paired_base_bit_exact": bool(paired_base_check["bit_exact"]),
        "fixed_pool_protocols_all_grouped": all(
            str(fixed_protocols[name]["splitter"]) == "grouped"  # type: ignore[index]
            for name in FIXED_POOL_PROTOCOLS
        ),
    }
    integrity["ok"] = all(bool(value) for value in integrity.values())
    verdict = build_verdict(chain, integrity=integrity, added_compounds=int(inventory["compounds"]))
    fixed_summary = fixed_family["summary"]
    extended_summary = extended_family["summary"]
    assert isinstance(fixed_summary, Mapping)
    assert isinstance(extended_summary, Mapping)
    upstream_bands = coverage_summary.get("band_counts_by_origin")
    declared_room = (
        upstream_bands[LOW_FREQUENCY_ORIGIN]["room_temperature"]
        if isinstance(upstream_bands, Mapping)
        else None
    )
    return {
        "schema_version": 1,
        "seed": seed,
        "protocol": protocol_block(seed=seed, n_repeats=n_repeats),
        "inputs": {
            "observations": portable_relative_path(COVERAGE_PATH, root=REPOSITORY_ROOT),
            "observations_sha256": canonical_text_sha256(COVERAGE_PATH),
            "v11_observations": portable_relative_path(OBSERVATIONS_PATH, root=REPOSITORY_ROOT),
            "v11_observations_sha256": canonical_text_sha256(OBSERVATIONS_PATH),
            "frozen_features": portable_relative_path(FEATURES_PATH, root=REPOSITORY_ROOT),
            "new_features": portable_relative_path(NEW_FEATURES_PATH, root=REPOSITORY_ROOT),
            "upstream_summary": portable_relative_path(COVERAGE_SUMMARY_PATH, root=REPOSITORY_ROOT),
            "upstream_declared": {
                "rows": coverage_summary.get("rows"),
                "compounds": coverage_summary.get("compounds"),
                "compounds_added_over_v11": coverage_summary.get("compounds_added_over_v11"),
                "low_frequency_room_rows": declared_room,
            },
            "coverage_rows": len(coverage_rows),
            "coverage_compounds": len({str(row["inchikey"]) for row in coverage_rows}),
            "v11_modelling_rows": len(v11_rows),
            "v11_compounds": v11_compounds,
            "low_frequency_rows": low_frequency_rows,
            "low_frequency_compounds": low_frequency_compounds,
            "dropped_by_the_v11_loader": dict(v11_dropped),
            "dropped_by_the_coverage_loader": dict(coverage_dropped),
        },
        "feature_blocks": feature_report,
        "frozen_table_agreement": agreement,
        "room_gate_audit": room_gate,
        "new_compound_inventory": inventory,
        "featureless_compounds": featureless,
        "reference": {
            "path": reference["path"],
            "sha256": reference["sha256"],
            "protocol": reference["protocol"],
            "published_hybrid_r2": reference["published_hybrid_r2"],
            "pinned_literal": ROOM_BAND_HYBRID_R2_REFERENCE,
            "matches_literal": reference["matches_literal"],
        },
        "reference_check": reference_check,
        "paired_base_check": paired_base_check,
        "fixed_pool_family": {
            "protocols": fixed_family["protocols"],
            "audits": fixed_family["audits"],
            "summary": fixed_summary,
            "target_pools": fixed_family["target_pools"],
            "chain": chain,
            "folds_shared_by": fixed_family["folds_shared_by"],
            "shared_fold_basis": fixed_family["shared_fold_basis"],
            "folds_are_shared": fixed_family["folds_are_shared"],
            "scored_row_contract": splitter_contract(fixed_family),
            "training_expansion": fixed_family["training_expansion"],
            "added_targets": added_targets,
            "comparability": (
                "the scored rows, the folds and the denominator are identical across every "
                "protocol here, so each delta has exactly one cause"
            ),
        },
        "extended_pool_family": {
            "protocols": extended_family["protocols"],
            "audits": extended_family["audits"],
            "summary": extended_summary,
            "target_pools": extended_family["target_pools"],
            "leak_reference": leak_comparison(
                extended_summary,  # type: ignore[arg-type]
                extended_family["audits"],  # type: ignore[arg-type]
            ),
            "comparability": (
                "a different scored pool from the fixed-pool family, so its R2 is NOT comparable "
                "to the 0.4091 of band_room_only; the pool variance is reported for that reason"
            ),
        },
        "integrity": integrity,
        "verdict": verdict,
        "outputs": {},
    }


def write_artifacts(
    path_dir: Path,
    stem: str,
    *,
    fold_rows: Sequence[Mapping[str, object]],
    repeat_rows: Sequence[Mapping[str, object]],
    prediction_rows: Sequence[Mapping[str, object]],
) -> dict[str, str]:
    """Write the three LF-only CSV tables and return their portable paths."""

    outputs = {
        "folds": path_dir / (stem + "_folds.csv"),
        "repeats": path_dir / (stem + "_repeats.csv"),
        "predictions": path_dir / (stem + "_predictions.csv"),
    }
    write_csv_rows(outputs["folds"], FOLD_COLUMNS, fold_rows)
    write_csv_rows(
        outputs["repeats"],
        ("protocol", "representation", "repeat", *METRIC_NAMES),
        repeat_rows,
    )
    write_csv_rows(outputs["predictions"], PREDICTION_COLUMNS, prediction_rows)
    return {name: portable_relative_path(path, root=REPOSITORY_ROOT) for name, path in outputs.items()}


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repeats", type=int, default=N_REPEATS, help="grouped repeats")
    parser.add_argument("--seed", type=int, default=SEED, help="fold-dealing seed")
    parser.add_argument("--summary", type=Path, default=SUMMARY_PATH)
    parser.add_argument("--artifacts-dir", type=Path, default=ARTIFACTS_DIR)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    _use_utf8_stdout()
    seed = int(args.seed)
    n_repeats = int(args.repeats)

    v11_rows, _frozen_features, v11_dropped = load_table(OBSERVATIONS_PATH, FEATURES_PATH)
    merged, feature_report = merge_feature_blocks()
    coverage_rows, coverage_dropped = load_coverage_table(COVERAGE_PATH, merged)
    agreement = frozen_table_agreement(v11_rows, coverage_rows)
    featureless = featureless_compound_report(COVERAGE_PATH, merged)
    v11_keys = {str(row["inchikey"]) for row in v11_rows}
    inventory = new_compound_inventory(coverage_rows, v11_keys)
    coverage_summary = json.loads(COVERAGE_SUMMARY_PATH.read_text(encoding="utf-8"))

    morgan, physical, target, temperatures, groups = build_matrices(coverage_rows)
    origin = np.asarray([str(row["observation_origin"]) for row in coverage_rows])
    band = np.asarray([str(row["temperature_band"]) for row in coverage_rows])
    keys = np.asarray([str(row["inchikey"]) for row in coverage_rows])
    zero = origin == ZERO_FREQUENCY_ORIGIN
    room = band == ROOM_BAND
    per_compound = inventory["per_compound"]
    assert isinstance(per_compound, Mapping)
    new_keys = set(per_compound)
    new_xtb_keys = {
        str(key)
        for key, item in per_compound.items()
        if isinstance(item, Mapping) and item.get("feature_source") == NEW_XTB_SOURCE
    }
    is_new = np.asarray([str(key) in new_keys for key in keys])
    is_new_xtb = np.asarray([str(key) in new_xtb_keys for key in keys])

    fixed_score = zero & room
    fixed_masks = {
        "paired_base": (fixed_score, fixed_score),
        "paired_plus_coverage": (fixed_score, room & (zero | is_new)),
        "paired_plus_new_xtb": (fixed_score, room & (zero | is_new_xtb)),
        "paired_plus_v03_block": (fixed_score, room & (zero | (is_new & ~is_new_xtb))),
    }
    reference_masks = {ROOM_BAND_REFERENCE_PROTOCOL: (fixed_score, fixed_score)}
    extended_masks = {
        "extended_pool_room": (room, room),
        LEAK_REFERENCE_PROTOCOL: (room, room),
    }

    def run(protocols, masks, splitters):
        return run_protocol_family(
            protocols,
            splitters=splitters,
            morgan=morgan,
            physical=physical,
            target=target,
            temperatures=temperatures,
            groups=groups,
            masks=masks,
            n_splits=N_SPLITS,
            n_repeats=n_repeats,
            seed=seed,
        )

    reference_run = run(
        (ROOM_BAND_REFERENCE_PROTOCOL,),
        reference_masks,
        {ROOM_BAND_REFERENCE_PROTOCOL: "grouped"},
    )
    fixed_family = run(
        FIXED_POOL_PROTOCOLS,
        fixed_masks,
        {name: "grouped" for name in FIXED_POOL_PROTOCOLS},
    )
    fixed_family["training_expansion"] = training_expansion(
        fixed_masks, splits_by_protocol=fixed_family["splits_by_protocol"]
    )
    extended_family = run(
        (*EXTENDED_POOL_PROTOCOLS, LEAK_REFERENCE_PROTOCOL),
        extended_masks,
        {
            **{name: "grouped" for name in EXTENDED_POOL_PROTOCOLS},
            LEAK_REFERENCE_PROTOCOL: "random_row",
        },
    )

    room_gate = room_gate_audit(COVERAGE_PATH, merged)
    added_targets = added_row_targets(fixed_masks, target, keys)
    low_frequency = origin == LOW_FREQUENCY_ORIGIN
    reference = read_room_band_reference()
    summary = build_summary(
        seed=seed,
        n_repeats=n_repeats,
        v11_rows=v11_rows,
        v11_dropped=v11_dropped,
        coverage_rows=coverage_rows,
        coverage_dropped=coverage_dropped,
        coverage_summary=coverage_summary,
        feature_report=feature_report,
        inventory=inventory,
        featureless=featureless,
        agreement=agreement,
        room_gate=room_gate,
        added_targets=added_targets,
        reference=reference,
        reference_run=reference_run,
        fixed_family=fixed_family,
        extended_family=extended_family,
        v11_compounds=len(v11_keys),
        low_frequency_rows=int(low_frequency.sum()),
        low_frequency_compounds=len(set(keys[low_frequency].tolist())),
    )
    outputs = write_artifacts(
        Path(args.artifacts_dir),
        ARTIFACT_STEM,
        fold_rows=[*fixed_family["fold_rows"], *extended_family["fold_rows"]],
        repeat_rows=[*fixed_family["repeat_rows"], *extended_family["repeat_rows"]],
        prediction_rows=[*fixed_family["prediction_rows"], *extended_family["prediction_rows"]],
    )
    summary["outputs"] = {"summary": portable_relative_path(Path(args.summary), root=REPOSITORY_ROOT), **outputs}

    summary_path = Path(args.summary)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    for line in format_report(summary):
        print(line)
    print()
    print("summary  : " + str(summary["outputs"]["summary"]))
    for name, path in outputs.items():
        print(f"{name:9s}: {path}")
    return 0 if summary["verdict"]["integrity_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())