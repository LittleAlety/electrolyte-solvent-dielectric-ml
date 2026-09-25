"""Check that the paper drafts agree with the frozen data artifacts.

The manuscript quotes row counts, benchmark metrics, conflict counts and
verifier results that are produced elsewhere in the repository. This checker
re-derives those values from the committed artifacts and fails when a paper file
disagrees, so prose cannot silently drift away from the data.

Usage:
    python scripts/check_paper_artifact_consistency.py
    python scripts/check_paper_artifact_consistency.py --json
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

import numpy as np
from sklearn.metrics import mean_absolute_error, r2_score

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))

from probes.dielectric_representation_ablation import read_modelling_rows
from scripts.build_paper_full_draft import PAPER_DIR, render_full_draft

DATA_DIR = REPOSITORY_ROOT / "data"
PROBES_DIR = REPOSITORY_ROOT / "probes"

SECTION_FILES = (
    "abstract_and_intro.md",
    "methods_data_records.md",
    "technical_validation.md",
    "benchmark_and_figures.md",
    "code_and_data.md",
    "outline.md",
)

# The release the manuscript advertises. The dataset inside it is v0.3.3, but the
# release line names the versioned release, which Zenodo archives.
CURRENT_RELEASE_VERSION = "1.0"

# Version label -> the CSV that holds that version's row count.
# Plain "0.3" maps to the v0.3.1 file because the v0.3 lineage produced 243 rows;
# the confusingly named dielectric_v03.csv is the current v0.3.3 candidate.
VERSION_TO_FILE = {
    "0.1": "dielectric_v01.csv",
    "0.2": "dielectric_v02.csv",
    "0.3": "dielectric_v031.csv",
    "0.3.1": "dielectric_v031.csv",
    "0.3.2": "dielectric_v032.csv",
    "0.3.3": "dielectric_v03.csv",
}

NUMBER_WORDS = {
    "zero": 0,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
}

RAW_BENCHMARK_KEYS = {
    "Morgan (ECFP4)": "Morgan",
    "Physical (13-dim)": "Physical",
    "Morgan+Physical": "Morgan+Physical",
}
LOG_BENCHMARK_KEYS = {
    "Morgan": "Morgan",
    "Physical": "Physical",
    "Morgan+Physical": "Morgan+Physical",
}
CONSTANT_ROW_LABEL = "Constant (train-fold mean)"

SCAFFOLD_KEYS = {
    "Morgan": "Morgan",
    "Physical": "Physical",
    "Morgan+Physical": "Morgan+Physical",
}
SCAFFOLD_TARGETS = {"raw": "raw", "log(eps-1)": "log_epsilon_minus_one"}

STALE_PHRASES = (
    # A candidate release must not be advertised as an immutable release commit.
    ("immutable release commit", "call the commit a candidate, not immutable"),
    # Superseded conflict accounting that a previous draft hard-coded.
    ("Five compounds with unresolved", "the conflict accounting is 7 / 6 / 4"),
    # The applicability trigger is structural. A predicted-dielectric threshold
    # reads the model output the boundary exists to qualify, so it is circular.
    (
        "predicted dielectric `> 60`",
        "the applicability trigger is structural, not a predicted-dielectric threshold",
    ),
    (
        "Onsager-estimated static dielectric above 60 are flagged",
        "the Onsager variant was measured and rejected; the adopted trigger is structural",
    ),
    # Superseded benchmark tables. The coverage table's historical rows are
    # labelled "pre-gate (superseded)" and carry no row-count suffix, so these
    # phrases only match prose that still presents the old numbers as current.
    ("237-row", "the model_ready gate took every v0.3 lineage to 236 fitted rows"),
    ("237 rows", "the model_ready gate took every v0.3 lineage to 236 fitted rows"),
    (
        "Morgan (ECFP4 count)",
        (
            "the duplicate per-section ablation table was replaced by a pointer "
            "to the checked main benchmark table"
        ),
    ),
)


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def paper_texts(paper_dir: Path) -> dict[str, str]:
    texts: dict[str, str] = {}
    for name in SECTION_FILES:
        path = paper_dir / name
        if path.is_file():
            texts[name] = path.read_text(encoding="utf-8-sig")
    return texts


def row_counts() -> dict[str, int]:
    counts = {}
    for name in sorted(set(VERSION_TO_FILE.values())):
        counts[name] = len(read_csv_rows(DATA_DIR / name))
    return counts


def _line_of(text: str, match: re.Match[str]) -> int:
    return text.count("\n", 0, match.start()) + 1


def check_row_count_claims(paper_dir: Path) -> list[str]:
    """Every "N compounds" claim attached to a file or version must be true."""
    counts = row_counts()
    patterns = (
        (re.compile(r"data/(dielectric_v\d+\.csv)\s*\((\d+) compounds?\)"), "file"),
        (re.compile(r"(dielectric_v\d+\.csv)\s+#[^\n]*?(\d+) compounds?"), "file"),
        (re.compile(r"(dielectric_v\d+\.csv)\s+#[^\n]*?\((\d+),"), "file"),
        (re.compile(r"\bv(0\.\d(?:\.\d)?) \((\d+) compounds?\)"), "version"),
        (re.compile(r"\bv(0\.\d(?:\.\d)?), (\d+) compounds?"), "version"),
    )
    errors: list[str] = []
    for name, text in paper_texts(paper_dir).items():
        for pattern, kind in patterns:
            for match in pattern.finditer(text):
                key, claimed = match.group(1), int(match.group(2))
                filename = key if kind == "file" else VERSION_TO_FILE.get(key)
                if filename is None or filename not in counts:
                    continue
                if counts[filename] != claimed:
                    errors.append(
                        f"{name}:{_line_of(text, match)} claims {claimed} compounds for "
                        f"{key}, but {filename} has {counts[filename]}"
                    )
    return errors


def check_conflict_counts(paper_dir: Path) -> list[str]:
    """The spelled-out conflict counts must match the current table."""
    rows = read_csv_rows(DATA_DIR / "dielectric_v03.csv")
    conflicts = [r for r in rows if (r.get("conflict_status") or "").strip()]
    flagged = [r for r in rows if str(r.get("model_ready", "")).strip().lower() == "false"]

    errors: list[str] = []
    pattern = re.compile(
        r"([A-Za-z]+) rows carry an explicit conflict_status "
        r"and ([A-Za-z]+) are flagged model_ready=false"
    )
    for name, text in paper_texts(paper_dir).items():
        flat = re.sub(r"\s+", " ", text)
        for match in pattern.finditer(flat):
            word_conflict = match.group(1).lower()
            word_flagged = match.group(2).lower()
            if NUMBER_WORDS.get(word_conflict) != len(conflicts):
                errors.append(
                    f"{name}: claims {word_conflict} conflict rows, table has {len(conflicts)}"
                )
            if NUMBER_WORDS.get(word_flagged) != len(flagged):
                errors.append(
                    f"{name}: claims {word_flagged} model_ready=false rows, "
                    f"table has {len(flagged)}"
                )
    return errors


def _table_after_heading(text: str, heading: str) -> list[list[str]]:
    lines = text.split("\n")
    start = next((i for i, line in enumerate(lines) if line.startswith(heading)), None)
    if start is None:
        raise KeyError(heading)
    table: list[list[str]] = []
    for line in lines[start + 1 :]:
        stripped = line.strip()
        if not stripped.startswith("|"):
            if table:
                break
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        table.append(cells)
    return table


def _tables(text: str) -> list[list[list[str]]]:
    """Every markdown table in the text, as a list of rows of stripped cells."""
    tables: list[list[list[str]]] = []
    current: list[list[str]] = []
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped.startswith("|"):
            current.append([cell.strip() for cell in stripped.strip("|").split("|")])
            continue
        if current:
            tables.append(current)
            current = []
    if current:
        tables.append(current)
    return tables


def _table_with_header(text: str, header: tuple[str, ...]) -> list[list[str]]:
    """The first table whose header row matches `header` exactly."""
    for table in _tables(text):
        if tuple(cell.replace("*", "").strip() for cell in table[0]) == header:
            return table
    raise KeyError(" | ".join(header))


def _decimals(cell: str) -> int | None:
    value = cell.replace("*", "").strip()
    if not re.fullmatch(r"-?\d+\.\d+", value):
        return None
    return len(value.split(".")[1])


def _compare(
    errors: list[str],
    where: str,
    label: str,
    metric: str,
    cell: str,
    value: float,
) -> None:
    places = _decimals(cell)
    if places is None or value is None:
        return
    expected = f"{value:.{places}f}"
    if expected != cell.replace("*", "").strip():
        errors.append(f"{where}: {label} {metric} is {cell}, artifact says {expected}")


def constant_baseline_metrics() -> dict[str, float]:
    """Fold-matched constant baseline on the frozen 10x5 assignment.

    Predicts the training-fold mean for every held-out compound, using the fold
    assignment recorded in the committed v0.3.2 predictions file, and averages
    the ten repeat-level values exactly as the ablation summary does.

    The target map is built through the same `model_ready` gate the models use.
    Reading the feature table directly would add the withheld vinylene carbonate
    row back in and make the reference row cover 237 compounds while every model
    covers 236.
    """
    modelling_rows, _, _ = read_modelling_rows(
        DATA_DIR / "processed" / "dielectric_physical_features_v03.csv"
    )
    target = {row["inchikey"]: float(row["dielectric"]) for row in modelling_rows}
    predictions = read_csv_rows(DATA_DIR / "processed" / "v032_ablation_predictions.csv")
    morgan = [row for row in predictions if row["representation"] == "Morgan"]

    per_repeat: list[dict[str, float]] = []
    for repeat in sorted({row["repeat"] for row in morgan}, key=int):
        held_out: dict[str, float] = {}
        for row in morgan:
            if row["repeat"] != repeat:
                continue
            test_keys = {
                other["inchikey"] for other in morgan if other["repeat"] == repeat
                and other["fold"] == row["fold"]
            }
            train = [key for key in target if key not in test_keys]
            mean = float(np.mean([target[key] for key in train]))
            for key in test_keys:
                held_out[key] = mean
        keys = sorted(held_out)
        y_true = np.array([target[key] for key in keys])
        y_pred = np.array([held_out[key] for key in keys])
        low = y_true < 20
        per_repeat.append(
            {
                "r2": float(r2_score(y_true, y_pred)),
                "mae": float(mean_absolute_error(y_true, y_pred)),
                "mae_lt20": float(mean_absolute_error(y_true[low], y_pred[low])),
            }
        )
    return {metric: float(np.mean([r[metric] for r in per_repeat])) for metric in per_repeat[0]}


def _means(entry: dict) -> dict[str, float]:
    """Flatten {"metric": {"mean": x, "std": y}} into {"metric": x}."""
    return {
        metric: float(values["mean"])
        for metric, values in entry.items()
        if isinstance(values, dict) and "mean" in values
    }


def check_main_benchmark_table(paper_dir: Path) -> list[str]:
    errors: list[str] = []
    text = (paper_dir / "benchmark_and_figures.md").read_text(encoding="utf-8-sig")
    table = _table_after_heading(text, "## Main benchmark")
    raw = read_json(PROBES_DIR / "v032_ablation_summary.json")["summary"]
    log_summary = read_json(PROBES_DIR / "v032_target_scaffold_summary.json")["summary"][
        "random_repeated_kfold"
    ]["log_epsilon_minus_one"]
    constant = constant_baseline_metrics()

    metric_columns = {
        2: "r2",
        3: "mae",
        4: "spearman",
        5: "auc_gt30",
        6: "mae_lt20",
    }
    for cells in table[1:]:
        if len(cells) < 7 or set("".join(cells)) <= {"-"}:
            continue
        label, mode = cells[0], cells[1]
        values: dict[str, float | None] = {}
        if mode == "raw" and label in RAW_BENCHMARK_KEYS:
            values = _means(raw[RAW_BENCHMARK_KEYS[label]])
        elif mode == "log(eps-1)" and label in LOG_BENCHMARK_KEYS:
            values = _means(log_summary[LOG_BENCHMARK_KEYS[label]])
        elif mode == "raw" and label == CONSTANT_ROW_LABEL:
            values = constant
        else:
            errors.append(f"benchmark_and_figures.md: unrecognised row {label!r}/{mode!r}")
            continue
        for index, metric in metric_columns.items():
            value = values.get(metric)
            if value is None:
                continue
            _compare(errors, "benchmark_and_figures.md", label, metric, cells[index], value)
    return errors


def check_abstract_ceiling_numbers(paper_dir: Path) -> list[str]:
    """Pin the abstract's representation-ceiling numbers to the frozen artifact.

    The ceiling sentence is prose, so the table checker never inspected it and a
    pre-gate copy of all six numbers survived review until M-1. Each value is
    matched by a regex that only fits that one sentence, so a rewrite of the
    sentence fails loudly instead of silently dropping the guard.
    """
    errors: list[str] = []
    text = (paper_dir / "abstract_and_intro.md").read_text(encoding="utf-8-sig")
    raw = read_json(PROBES_DIR / "v032_ablation_summary.json")["summary"]
    checks = (
        (r"Spearman ([0-9.]+) for Physical alone", "Physical", "spearman"),
        (r"for Physical alone vs\. ([0-9.]+) for Morgan", "Morgan", "spearman"),
        (r"complementary breadth \(R2 ([0-9.]+) vs\.", "Morgan", "r2"),
        (r"complementary breadth \(R2 [0-9.]+ vs\. ([0-9.]+)\)", "Physical", "r2"),
        (r"outperforms either alone \(R2 ([0-9.]+),", "Morgan+Physical", "r2"),
        (
            r"outperforms either alone \(R2 [0-9.]+, Spearman ([0-9.]+)\)",
            "Morgan+Physical",
            "spearman",
        ),
    )
    for pattern, model, metric in checks:
        match = re.search(pattern, text)
        if match is None:
            errors.append(
                f"abstract_and_intro.md: ceiling sentence no longer matches {pattern!r}; "
                "update this guard with the rewritten sentence"
            )
            continue
        _compare(
            errors,
            "abstract_and_intro.md",
            model,
            metric,
            match.group(1),
            _means(raw[model]).get(metric),
        )
    return errors


def check_scaffold_table(paper_dir: Path) -> list[str]:
    errors: list[str] = []
    text = (paper_dir / "benchmark_and_figures.md").read_text(encoding="utf-8-sig")
    table = _table_after_heading(text, "## Extrapolation")
    summary = read_json(PROBES_DIR / "v032_target_scaffold_summary.json")["summary"][
        "scaffold_cluster_5fold"
    ]
    for cells in table[1:]:
        if len(cells) < 5 or set("".join(cells)) <= {"-"}:
            continue
        label = cells[0].replace("*", "").strip()
        mode = cells[1].replace("*", "").strip()
        if label not in SCAFFOLD_KEYS or mode not in SCAFFOLD_TARGETS:
            errors.append(
                f"benchmark_and_figures.md: unrecognised scaffold row {label!r}/{mode!r}"
            )
            continue
        entry = summary[SCAFFOLD_TARGETS[mode]][SCAFFOLD_KEYS[label]]
        for index, metric in ((2, "r2"), (3, "mae"), (4, "spearman")):
            cell = cells[index].strip()
            if "+/-" not in cell:
                errors.append(
                    f"benchmark_and_figures.md: {label}/{mode} {metric} is {cell!r}, "
                    "which carries no +/- uncertainty to verify"
                )
                continue
            mean_cell, std_cell = (part.strip() for part in cell.split("+/-"))
            _compare(errors, "benchmark_and_figures.md", f"{label}/{mode}", metric, mean_cell,
                     entry[metric]["mean"])
            _compare(errors, "benchmark_and_figures.md", f"{label}/{mode}", f"{metric} std",
                     std_cell, entry[metric]["std"])
    return errors


def check_applicability_trigger_rate(paper_dir: Path) -> list[str]:
    """The quoted trigger rate and coverage must equal the recorded summary.

    The applicability boundary was re-derived once already, and the prose kept
    quoting the retired rule. This check re-reads
    `probes/applicability_domain_summary.json` and fails when a paper section
    quotes a different trigger rate or a different flagged-row count than the
    artifact records.
    """

    summary = read_json(PROBES_DIR / "applicability_domain_summary.json")
    rate = float(summary["trigger_rate"])
    outside = int(summary["outside_count"])
    total = int(summary["row_count"])

    errors: list[str] = []
    for name, text in paper_texts(paper_dir).items():
        flat = re.sub(r"\s+", " ", text)
        for match in re.finditer(r"(\d+(?:\.\d+)?)%", flat):
            window = flat[max(0, match.start() - 220) : match.end() + 220]
            if "out-of-fold" not in window or "trigger" not in window:
                continue
            claimed = float(match.group(1))
            if abs(claimed - rate * 100.0) > 0.01:
                errors.append(
                    f"{name}: claims a {claimed:.2f}% applicability trigger rate, "
                    f"but the summary records {rate * 100.0:.2f}%"
                )
        for match in re.finditer(
            r"([\d,]+) of (?:the )?([\d,]+) out-of-fold rows",
            flat,
        ):
            claimed_rows = int(match.group(1).replace(",", ""))
            claimed_total = int(match.group(2).replace(",", ""))
            if claimed_total != total:
                errors.append(
                    f"{name}: claims {claimed_total} out-of-fold rows, "
                    f"but the summary records {total}"
                )
            elif claimed_rows != outside:
                errors.append(
                    f"{name}: claims {claimed_rows} rows outside the domain, "
                    f"but the summary records {outside}"
                )
    return errors


def check_modelling_set_and_controlled_delta(paper_dir: Path) -> list[str]:
    """The fitted-row count and the controlled PC/EC gain must match the artifacts.

    Both numbers moved once already: enforcing `model_ready` took the fitted set
    from 237 to 236 rows and the paired hybrid gain from +0.0265 to +0.0059. This
    check re-derives them and fails the build if the prose drifts again.
    """

    ablation = read_json(PROBES_DIR / "v032_ablation_summary.json")
    fitted = int(ablation["compound_count"])
    withheld = int(ablation.get("withheld_not_model_ready_count", 0))
    accounted = (
        fitted
        + withheld
        + int(ablation["failed_physical_feature_count"])
        + int(ablation["excluded_count"])
    )
    errors: list[str] = []
    if accounted != int(ablation["source_count"]):
        errors.append(
            "v032_ablation_summary.json does not balance: "
            f"{accounted} != {ablation['source_count']}"
        )

    paired = read_json(PROBES_DIR / "v032_controlled_comparison_summary.json")[
        "paired_deltas"
    ]["Morgan+Physical"]["r2"]
    delta = float(paired["delta_mean"])
    low, high = (float(value) for value in paired["delta_ci95"])

    for name, text in paper_texts(paper_dir).items():
        flat = re.sub(r"\s+", " ", text)
        for match in re.finditer(r"(\d+) fitted rows", flat):
            if int(match.group(1)) != fitted:
                errors.append(
                    f"{name}: claims {match.group(1)} fitted rows, but "
                    f"v032_ablation_summary.json records {fitted}"
                )
        for match in re.finditer(r"attributes[^.]{0,40}?([+-]\d+\.\d{3,4})", flat):
            if abs(float(match.group(1)) - delta) > 5e-5:
                errors.append(
                    f"{name}: claims a {match.group(1)} controlled R2 gain, but "
                    f"the paired control records {delta:+.4f}"
                )
        for match in re.finditer(
            r"95% CI ([+-]\d+\.\d{3}) to ([+-]\d+\.\d{3})",
            flat,
        ):
            if abs(float(match.group(1)) - low) > 5e-4 or abs(float(match.group(2)) - high) > 5e-4:
                errors.append(
                    f"{name}: quotes a controlled CI of [{match.group(1)}, "
                    f"{match.group(2)}], but the probe records [{low:+.3f}, {high:+.3f}]"
                )
    return errors


def check_coverage_sensitivity_table(paper_dir: Path) -> list[str]:
    """The per-version coverage table must match the gate-fixed ablation summaries.

    Two rows of that table moved in v0.3.4: the fitted-row counts (235/237 -> 236
    in both v0.3 lineages) and the metrics themselves. Rows the prose marks
    `pre-gate (superseded)` are historical and are not re-derived, but every
    current row is checked against the artifact that produced it.
    """

    header = ("Dataset", "Fitted rows", "Morgan R2", "Physical R2", "Hybrid R2")
    sources = {
        "v0.2": ("dielectric_representation_ablation_summary.json", "Morgan"),
        "gate enforced": ("v032_ablation_summary.json", "Morgan"),
    }
    text = (paper_dir / "technical_validation.md").read_text(encoding="utf-8-sig")
    try:
        table = _table_with_header(text, header)
    except KeyError:
        return [
            (
                "technical_validation.md: the coverage-sensitivity table is "
                "missing or its header changed"
            )
        ]

    errors: list[str] = []
    for cells in table[2:]:
        if len(cells) < 5:
            continue
        label = cells[0].replace("*", "").strip()
        if "pre-gate" in label:
            continue
        source = next(
            (name for key, (name, _) in sources.items() if key in label), None
        )
        if source is None:
            errors.append(
                f"technical_validation.md: unrecognised coverage row {label!r}"
            )
            continue
        summary = read_json(PROBES_DIR / source)
        fitted = int(summary["compound_count"])
        claimed = cells[1].replace("*", "").strip()
        if not claimed.isdigit() or int(claimed) != fitted:
            errors.append(
                f"technical_validation.md: row {label!r} claims {claimed} fitted "
                f"rows, but {source} records {fitted}"
            )
        for index, metric in ((2, "r2"), (3, "r2"), (4, "r2")):
            representation = ("Morgan", "Physical", "Morgan+Physical")[index - 2]
            _compare(
                errors,
                "technical_validation.md",
                label,
                representation,
                cells[index],
                float(summary["summary"][representation][metric]["mean"]),
            )
    return errors


def check_external_holdout(paper_dir: Path) -> list[str]:
    """The quoted PC/EC external-holdout predictions must match the probe.

    The pre-gate run predicted 29.8 +/- 1.1 for PC and 50.3 +/- 2.2 for EC;
    withholding vinylene carbonate moved them to 21.6 +/- 0.4 and 33.7 +/- 1.5.
    The prose kept the old numbers, so this check exists to keep them pinned.
    """

    holdout = read_json(PROBES_DIR / "v032_controlled_comparison_summary.json")[
        "pc_ec_external_holdout"
    ]["Morgan+Physical"]
    by_name = {entry["name"]: entry for entry in holdout.values()}
    patterns = (
        (re.compile(r"predicts ([\d.]+) \+/- ([\d.]+) for PC \(true ([\d.]+)\)"), "propylene carbonate"),
        (re.compile(r"([\d.]+) \+/- ([\d.]+) for EC \(true ([\d.]+)\)"), "ethylene carbonate"),
    )
    errors: list[str] = []
    for name, text in paper_texts(paper_dir).items():
        flat = re.sub(r"\s+", " ", text)
        for pattern, compound in patterns:
            entry = by_name.get(compound)
            if entry is None:
                continue
            for match in pattern.finditer(flat):
                _compare(
                    errors,
                    name,
                    f"external holdout {compound}",
                    "mean",
                    match.group(1),
                    float(entry["prediction_mean"]),
                )
                _compare(
                    errors,
                    name,
                    f"external holdout {compound}",
                    "std",
                    match.group(2),
                    float(entry["prediction_std"]),
                )
                _compare(
                    errors,
                    name,
                    f"external holdout {compound}",
                    "true",
                    match.group(3),
                    float(entry["target"]),
                )
    return errors


def check_release_version(paper_dir: Path) -> list[str]:
    text = (paper_dir / "code_and_data.md").read_text(encoding="utf-8-sig")
    marker = f"**Release:** v{CURRENT_RELEASE_VERSION}"
    if marker not in text:
        return [f"code_and_data.md: release line does not match v{CURRENT_RELEASE_VERSION}"]
    return []


def check_full_draft(paper_dir: Path) -> list[str]:
    target = paper_dir / "full_draft.md"
    if not target.is_file():
        return ["paper/full_draft.md is missing; run scripts/build_paper_full_draft.py"]
    actual = target.read_text(encoding="utf-8-sig")
    actual = actual.replace("\r\n", "\n").replace("\r", "\n").lstrip("\ufeff")
    if actual != render_full_draft(paper_dir):
        return ["paper/full_draft.md is stale; run scripts/build_paper_full_draft.py"]
    return []


def check_stale_phrases(paper_dir: Path) -> list[str]:
    errors: list[str] = []
    for name, text in paper_texts(paper_dir).items():
        for phrase, hint in STALE_PHRASES:
            if phrase in text:
                errors.append(f"{name}: contains stale phrase {phrase!r} ({hint})")
    return errors


def verify_paper(paper_dir: Path = PAPER_DIR) -> list[str]:
    errors: list[str] = []
    for check in (
        check_row_count_claims,
        check_conflict_counts,
        check_main_benchmark_table,
        check_abstract_ceiling_numbers,
        check_scaffold_table,
        check_release_version,
        check_applicability_trigger_rate,
        check_modelling_set_and_controlled_delta,
        check_coverage_sensitivity_table,
        check_external_holdout,
        check_full_draft,
        check_stale_phrases,
    ):
        errors.extend(check(paper_dir))
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--paper-dir", type=Path, default=PAPER_DIR)
    parser.add_argument("--json", action="store_true", help="emit a JSON report")
    args = parser.parse_args(argv)

    errors = verify_paper(args.paper_dir)
    if args.json:
        print(json.dumps({"passed": not errors, "errors": errors}, indent=2))
    elif errors:
        for error in errors:
            print(error, file=sys.stderr)
    else:
        print("paper drafts agree with the frozen artifacts")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())