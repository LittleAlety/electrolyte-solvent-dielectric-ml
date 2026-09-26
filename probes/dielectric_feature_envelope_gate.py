"""Feature-envelope applicability gate: the track-B fix Week 13's L3 pilot asked for.

Week 13's L3 stage-1 pilot scored ethylene carbonate (EC) and propylene
carbonate (PC) at 23.1 and 17.0 against measured 90.5 and 64.9, and not one
gate fired.  The repository's only applicability rule is structural
(src/electrolyte_ml/applicability.py): it flags a liquid whose molecules can
donate a hydrogen bond, i.e. associating liquids whose static permittivity is
governed by the Kirkwood correlation factor.  EC and PC carry no O-H, so the
rule is structurally blind to them, and the model was quietly wrong with no
flag at all.

This probe builds the missing flag as an envelope check on the descriptor
space: a candidate is raised if it leaves the region the model was fitted on.
Two rules, both frozen in probes/dielectric_feature_envelope_gate_prereg.json
before this file existed:

* robust_interval_fence -- per descriptor, median +/- 1.5 * IQR over the
  training domain; any descriptor outside its fence raises the flag.
* knn_distance_fence -- after standardising the descriptors on the training
  domain, a candidate whose distance to its nearest training compound exceeds
  the 95th percentile of the training domain's own leave-one-out
  nearest-neighbour distances is raised.

Nothing here is tuned against the outcome.  k = 1.5 and the 95th percentile are
copied from the pre-registration, and no target value ever enters a rule: the
descriptors are physical features of the molecule, the envelope is a statement
about the fitting domain, and the flags are computable before any prediction
exists.

Scope, honestly
---------------
The gate does not rank.  Its only action is to remove a candidate from the
ranking channel and route it to measurement or a physical estimate
(action_when_flagged).  Its envelope is calibrated on the 236-compound pilot
pool; the real funnel sees a 29.5k candidate pool, where a rule of the same
shape catches a different fraction, so every rate below is a 236-pool rate.

Outputs
-------
probes/dielectric_feature_envelope_gate_summary.json
probes/artifacts/dielectric_feature_envelope_gate_descriptor_envelope.csv
probes/artifacts/dielectric_feature_envelope_gate_pool_loo.csv
probes/artifacts/dielectric_feature_envelope_gate_ec_pc.csv
reports/dielectric_feature_envelope_gate.md
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

import numpy as np

from electrolyte_ml.applicability import H_BOND_DONOR_SMARTS, count_hbond_donors
from electrolyte_ml.exporting import canonical_text_sha256, sha256_file
from electrolyte_ml.pathing import portable_relative_path

PREREG_PATH = REPOSITORY_ROOT / "probes" / "dielectric_feature_envelope_gate_prereg.json"
POOL_PATH = REPOSITORY_ROOT / "probes" / "l3_stage1_pilot_pool.csv"
FEATURES_PATH = (
    REPOSITORY_ROOT / "data" / "processed" / "dielectric_physical_features_v03.csv"
)
FEATURES_NEW_PATH = (
    REPOSITORY_ROOT / "data" / "processed" / "dielectric_physical_features_v11plus_new.csv"
)
SUMMARY_PATH = REPOSITORY_ROOT / "probes" / "dielectric_feature_envelope_gate_summary.json"
REPORT_PATH = REPOSITORY_ROOT / "reports" / "dielectric_feature_envelope_gate.md"
ARTIFACT_DIR = REPOSITORY_ROOT / "probes" / "artifacts"
ENVELOPE_CSV_PATH = (
    ARTIFACT_DIR / "dielectric_feature_envelope_gate_descriptor_envelope.csv"
)
POOL_LOO_CSV_PATH = ARTIFACT_DIR / "dielectric_feature_envelope_gate_pool_loo.csv"
EC_PC_CSV_PATH = ARTIFACT_DIR / "dielectric_feature_envelope_gate_ec_pc.csv"

#: The pilot pool is frozen to disk; the digest is asserted before any rule runs.
POOL_SHA256 = "b838febbca4d65975d1820ae9275215288968979b78756611cb031eb7c408b18"
EXPECTED_POOL_ROWS = 236

#: descriptor order is the pre-registration's list, verbatim.
DESCRIPTORS = (
    "dipole_D",
    "mu_sq_over_Vm",
    "molecular_volume_A3",
    "tpsa_A2",
    "hba",
    "hbd",
    "heavy_atom_count",
    "homo_lumo_gap_ev",
)

#: locked constants, copied from the pre-registration and never re-chosen here.
FENCE_K = 1.5
KNN_PERCENTILE = 95.0
MAX_SECONDARY_FLAG_RATE = 0.20
KILL_LINE_FLAG_RATE = 0.50

#: the two held-out candidates of the primary check, with the pilot's inchikeys.
PRIMARY_CHAMPIONS = (
    ("EC", "KMTRUDSVKNLOMY-UHFFFAOYSA-N"),
    ("PC", "RUOJZAUFBMNUDX-UHFFFAOYSA-N"),
)

SHOTS = 1
LABEL = "week14_feature_envelope_gate"

ENVELOPE_FIELDS = (
    "descriptor",
    "median",
    "q1",
    "q3",
    "iqr",
    "lower_fence",
    "upper_fence",
    "training_rows",
)
POOL_LOO_FIELDS = (
    "inchikey",
    "name",
    "list",
    "rule_a_flagged",
    "rule_a_hits",
    "rule_a_max_abs_iqr_units",
    "rule_b_flagged",
    "rule_b_nn_distance",
    "rule_b_threshold",
    "flagged_any",
    "in_primary_held_out_set",
)
EC_PC_FIELDS = (
    "champion",
    "name",
    "inchikey",
    "training_rows",
    "rule_a_flagged",
    "rule_a_hits",
    "rule_a_max_abs_iqr_units",
    "rule_b_flagged",
    "rule_b_nn_distance",
    "rule_b_threshold",
    "flagged_any",
    "smarts_donor_count",
    "smarts_structural_gate_fires",
)


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def write_csv_lf(
    path: Path,
    fieldnames: Sequence[str],
    rows: Sequence[Mapping[str, object]],
) -> None:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    _write_text(path, buffer.getvalue())


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_prereg() -> dict:
    payload = _read_json(PREREG_PATH)
    if payload.get("status") != "locked_before_run":
        raise ValueError("the feature-envelope pre-registration is not locked")
    locked = {rule["id"] for rule in payload["rules"]}
    if locked != {"robust_interval_fence", "knn_distance_fence"}:
        raise ValueError(f"unexpected rule ids in the pre-registration: {sorted(locked)}")
    return payload


def load_pool() -> list[dict[str, str]]:
    rows = read_csv_rows(POOL_PATH)
    digest = sha256_file(POOL_PATH)
    if digest != POOL_SHA256:
        raise ValueError(
            f"pool digest changed: {digest} != frozen {POOL_SHA256}"
        )
    if len(rows) != EXPECTED_POOL_ROWS:
        raise ValueError(f"pool row count changed: {len(rows)} != {EXPECTED_POOL_ROWS}")
    return rows


def load_descriptors() -> tuple[dict[str, list[float]], dict[str, str], list[str]]:
    """Return descriptor vectors, the source file, and keys skipped as incomplete."""

    features: dict[str, list[float]] = {}
    source: dict[str, str] = {}
    incomplete: list[str] = []
    for path in (FEATURES_PATH, FEATURES_NEW_PATH):
        if not path.is_file():
            continue
        for row in read_csv_rows(path):
            key = (row.get("inchikey") or "").strip()
            if not key or key in features:
                continue
            values = []
            complete = True
            for name in DESCRIPTORS:
                raw = (row.get(name) or "").strip()
                if raw == "":
                    complete = False
                    break
                values.append(float(raw))
            if not complete:
                incomplete.append(key)
                continue
            features[key] = values
            source[key] = portable_relative_path(path, root=REPOSITORY_ROOT)
    return features, source, sorted(set(incomplete))


def descriptor_matrix(keys: Sequence[str], features: Mapping[str, list[float]]):
    return np.asarray([features[key] for key in keys], dtype=float)


def descriptor_envelope(matrix) -> tuple:
    median = np.median(matrix, axis=0)
    q1 = np.percentile(matrix, 25, axis=0)
    q3 = np.percentile(matrix, 75, axis=0)
    return median, q1, q3, q3 - q1


def rule_a_hits(value, median, iqr) -> list[dict[str, float]]:
    """Descriptors whose value leaves the median +/- k * IQR fence."""

    hits: list[dict[str, float]] = []
    for index, name in enumerate(DESCRIPTORS):
        spread = float(iqr[index])
        if spread <= 0.0:
            if value[index] != median[index]:
                hits.append(
                    {
                        "descriptor": name,
                        "value": float(value[index]),
                        "median": float(median[index]),
                        "iqr_units": float("nan"),
                        "fence_low": float(median[index]),
                        "fence_high": float(median[index]),
                    }
                )
            continue
        low = float(median[index] - FENCE_K * spread)
        high = float(median[index] + FENCE_K * spread)
        if value[index] < low or value[index] > high:
            hits.append(
                {
                    "descriptor": name,
                    "value": float(value[index]),
                    "median": float(median[index]),
                    "iqr_units": float((value[index] - median[index]) / spread),
                    "fence_low": low,
                    "fence_high": high,
                }
            )
    return hits


def _loo_nearest_neighbour_distances(z):
    count = z.shape[0]
    out = np.empty(count)
    for index in range(count):
        distances = np.sqrt(np.sum((z - z[index]) ** 2, axis=1))
        distances[index] = np.inf
        out[index] = distances.min()
    return out


def knn_fence(matrix) -> tuple:
    """Standardise on the training domain and take its 95th-percentile LOO radius."""

    mean = matrix.mean(axis=0)
    std = matrix.std(axis=0, ddof=1)
    std = np.where(std > 0.0, std, 1.0)
    z = (matrix - mean) / std
    loo = _loo_nearest_neighbour_distances(z)
    threshold = float(np.percentile(loo, KNN_PERCENTILE))
    return mean, std, z, threshold, loo


def knn_distance(value, mean, std, train_z) -> float:
    z = (value - mean) / std
    return float(np.sqrt(np.sum((train_z - z) ** 2, axis=1)).min())


def _rule_a_summary(hits: Sequence[Mapping[str, object]]) -> tuple[str, float]:
    text = ";".join(
        "{descriptor}:{units:+.3f}".format(
            descriptor=hit["descriptor"], units=float(hit["iqr_units"])
        )
        for hit in hits
    )
    magnitudes = [abs(float(hit["iqr_units"])) for hit in hits if hit["iqr_units"] == hit["iqr_units"]]
    return text, (max(magnitudes) if magnitudes else 0.0)


def run_gate(pool_rows: Sequence[Mapping[str, str]], features: Mapping[str, list[float]], source: Mapping[str, str]) -> dict:
    """Run both rules.  No target value is read here, by construction."""

    keys = [row["inchikey"] for row in pool_rows]
    absent = sorted({key for key in keys if key not in features})
    if absent:
        raise ValueError(f"pool members without complete descriptors: {absent}")
    matrix = descriptor_matrix(keys, features)
    index = {key: position for position, key in enumerate(keys)}

    champions = {short: key for short, key in PRIMARY_CHAMPIONS}
    missing = [key for key in champions.values() if key not in index]
    if missing:
        raise ValueError(f"held-out candidates absent from the pool: {missing}")
    champion_keys = set(champions.values())

    # ---- primary check: EC and PC held out exactly as the stage-1 pilot did.
    train_mask = np.asarray([key not in champion_keys for key in keys])
    train_matrix = matrix[train_mask]
    median, q1, q3, iqr = descriptor_envelope(train_matrix)
    mean, std, train_z, threshold, loo = knn_fence(train_matrix)

    primary: dict[str, dict] = {}
    primary_rows: list[dict[str, object]] = []
    for short, key in champions.items():
        row = next(row for row in pool_rows if row["inchikey"] == key)
        value = matrix[index[key]]
        hits = rule_a_hits(value, median, iqr)
        distance = knn_distance(value, mean, std, train_z)
        donors = count_hbond_donors(row["smiles"])
        text, magnitude = _rule_a_summary(hits)
        flagged = bool(hits) or distance > threshold
        primary[short] = {
            "inchikey": key,
            "name": row["name"],
            "rule_a_flagged": bool(hits),
            "rule_a_hits": hits,
            "rule_a_max_abs_iqr_units": magnitude,
            "rule_b_flagged": bool(distance > threshold),
            "rule_b_nn_distance": distance,
            "rule_b_threshold": threshold,
            "flagged": flagged,
            "smarts_donor_count": int(donors),
            "smarts_structural_gate_fires": bool(donors >= 1),
        }
        primary_rows.append(
            {
                "champion": short,
                "name": row["name"],
                "inchikey": key,
                "training_rows": int(train_mask.sum()),
                "rule_a_flagged": bool(hits),
                "rule_a_hits": text,
                "rule_a_max_abs_iqr_units": f"{magnitude:.6f}",
                "rule_b_flagged": bool(distance > threshold),
                "rule_b_nn_distance": f"{distance:.6f}",
                "rule_b_threshold": f"{threshold:.6f}",
                "flagged_any": flagged,
                "smarts_donor_count": int(donors),
                "smarts_structural_gate_fires": bool(donors >= 1),
            }
        )

    envelope_rows = [
        {
            "descriptor": name,
            "median": f"{float(median[i]):.10g}",
            "q1": f"{float(q1[i]):.10g}",
            "q3": f"{float(q3[i]):.10g}",
            "iqr": f"{float(iqr[i]):.10g}",
            "lower_fence": f"{float(median[i] - FENCE_K * iqr[i]):.10g}",
            "upper_fence": f"{float(median[i] + FENCE_K * iqr[i]):.10g}",
            "training_rows": int(train_mask.sum()),
        }
        for i, name in enumerate(DESCRIPTORS)
    ]

    # ---- secondary check: leave-one-out sweep over the whole pool.
    loo_rows: list[dict[str, object]] = []
    flags_a = flags_b = flags_any = 0
    smarts_by_key: dict[str, int] = {}
    for position, key in enumerate(keys):
        row = pool_rows[position]
        mask = np.ones(len(keys), dtype=bool)
        mask[position] = False
        sub = matrix[mask]
        median_i, _, _, iqr_i = descriptor_envelope(sub)
        hits_i = rule_a_hits(matrix[position], median_i, iqr_i)
        mean_i, std_i, sub_z, threshold_i, _ = knn_fence(sub)
        distance_i = knn_distance(matrix[position], mean_i, std_i, sub_z)
        flagged_a = bool(hits_i)
        flagged_b = bool(distance_i > threshold_i)
        flags_a += flagged_a
        flags_b += flagged_b
        flags_any += flagged_a or flagged_b
        text_i, magnitude_i = _rule_a_summary(hits_i)
        donors = count_hbond_donors(row["smiles"])
        smarts_by_key[key] = int(donors)
        loo_rows.append(
            {
                "inchikey": key,
                "name": row["name"],
                "list": row.get("list", ""),
                "rule_a_flagged": flagged_a,
                "rule_a_hits": text_i,
                "rule_a_max_abs_iqr_units": f"{magnitude_i:.6f}",
                "rule_b_flagged": flagged_b,
                "rule_b_nn_distance": f"{distance_i:.6f}",
                "rule_b_threshold": f"{threshold_i:.6f}",
                "flagged_any": bool(flagged_a or flagged_b),
                "in_primary_held_out_set": bool(key in champion_keys),
            }
        )

    total = len(keys)
    rate_a = flags_a / total
    rate_b = flags_b / total
    rate_any = flags_any / total

    # ---- contrast with the existing structural SMARTS gate.
    old_fires = {key for key, donors in smarts_by_key.items() if donors >= 1}
    new_fires = {row["inchikey"] for row in loo_rows if row["flagged_any"]}
    smarts_contrast = {
        "smarts": H_BOND_DONOR_SMARTS,
        "old_gate_definition": "hbd_smarts_donor_count >= 1",
        "counts": {
            "old_only": len(old_fires - new_fires),
            "both": len(old_fires & new_fires),
            "new_only": len(new_fires - old_fires),
            "neither": total - len(old_fires | new_fires),
        },
        "held_out_under_old_gate": {
            short: {
                "donor_count": primary[short]["smarts_donor_count"],
                "structural_gate_fires": primary[short]["smarts_structural_gate_fires"],
            }
            for short in champions
        },
    }

    primary_met = all(primary[short]["flagged"] for short in champions)
    secondary_met = rate_any <= MAX_SECONDARY_FLAG_RATE
    unflagged_targets = [s for s in champions if not primary[s]["flagged"]]
    kill_line = bool(unflagged_targets) or rate_any > KILL_LINE_FLAG_RATE
    if primary_met and secondary_met:
        verdict = "pass"
    elif kill_line:
        verdict = "kill_line_triggered"
    elif primary_met:
        verdict = "primary_met_secondary_not_met"
    else:
        verdict = "targets_missed"

    return {
        "primary": primary,
        "primary_rows": primary_rows,
        "envelope_rows": envelope_rows,
        "loo_rows": loo_rows,
        "feature_source": dict(source),
        "readings": {
            "primary_training_rows": int(train_mask.sum()),
            "primary_envelope_k": FENCE_K,
            "primary_knn_percentile": KNN_PERCENTILE,
            "primary_knn_threshold": threshold,
            "primary_knn_loo_median": float(np.median(loo)),
            "secondary_total_rows": total,
            "secondary_rule_a_flags": flags_a,
            "secondary_rule_b_flags": flags_b,
            "secondary_any_flags": flags_any,
            "secondary_rule_a_rate": rate_a,
            "secondary_rule_b_rate": rate_b,
            "secondary_any_rate": rate_any,
        },
        "criteria": {
            "primary_met": primary_met,
            "secondary_met": secondary_met,
            "unflagged_targets": unflagged_targets,
            "kill_line_triggered": kill_line,
            "verdict": verdict,
        },
        "smarts_contrast": smarts_contrast,
    }


def build_report(summary: Mapping[str, object]) -> str:
    readings = summary["readings"]
    criteria = summary["criteria"]
    primary = summary["primary_check"]
    contrast = summary["smarts_contrast"]
    counts = contrast["counts"]

    def hit_line(short: str) -> str:
        entry = primary[short]
        pieces = []
        for hit in entry["rule_a_hits"]:
            pieces.append(
                "{name} = {value:.6g} (median {median:.6g}, fence [{low:.6g}, {high:.6g}], {units:+.3f} IQR)".format(
                    name=hit["descriptor"],
                    value=hit["value"],
                    median=hit["median"],
                    low=hit["fence_low"],
                    high=hit["fence_high"],
                    units=hit["iqr_units"],
                )
            )
        return "; ".join(pieces) if pieces else "none"

    lines = []
    lines.append("# Feature-envelope applicability gate (Week 14, track B)")
    lines.append("")
    lines.append(
        "Pre-registered in probes/dielectric_feature_envelope_gate_prereg.json "
        "before this probe ran.  k = 1.5 and the 95th percentile are the locked "
        "constants; nothing was tuned after seeing the result."
    )
    lines.append("")
    lines.append("## Verdict")
    lines.append("")
    lines.append(f"- Overall: **{criteria['verdict']}**")
    lines.append(f"- Primary criterion met: {criteria['primary_met']}")
    lines.append(f"- Secondary criterion met: {criteria['secondary_met']}")
    lines.append(f"- Kill line triggered: {criteria['kill_line_triggered']}")
    lines.append(f"- Raised by the leave-one-out sweep: {readings['secondary_any_flags']} of "
                 f"{readings['secondary_total_rows']} rows "
                 f"({readings['secondary_any_rate']:.4f})")
    lines.append("")
    lines.append("## Rule A (robust interval fence, median +/- 1.5 IQR)")
    lines.append("")
    for short in ("EC", "PC"):
        entry = primary[short]
        lines.append(
            f"- {short}: flagged={entry['rule_a_flagged']}; {hit_line(short)}"
        )
    lines.append("")
    lines.append("## Rule B (kNN distance fence, 95th-percentile LOO radius)")
    lines.append("")
    lines.append(
        f"- Training-domain threshold: {readings['primary_knn_threshold']:.4f} "
        f"(median LOO nearest-neighbour distance {readings['primary_knn_loo_median']:.4f})"
    )
    for short in ("EC", "PC"):
        entry = primary[short]
        lines.append(
            f"- {short}: distance {entry['rule_b_nn_distance']:.4f}, "
            f"flagged={entry['rule_b_flagged']}"
        )
    lines.append("")
    lines.append("## Leave-one-out control over the 236-compound pool")
    lines.append("")
    lines.append(
        f"- Rule A alone: {readings['secondary_rule_a_flags']} / "
        f"{readings['secondary_total_rows']} = {readings['secondary_rule_a_rate']:.4f}"
    )
    lines.append(
        f"- Rule B alone: {readings['secondary_rule_b_flags']} / "
        f"{readings['secondary_total_rows']} = {readings['secondary_rule_b_rate']:.4f}"
    )
    lines.append(
        f"- Combined (either rule): {readings['secondary_any_flags']} / "
        f"{readings['secondary_total_rows']} = {readings['secondary_any_rate']:.4f}"
    )
    lines.append("")
    lines.append("## Why the existing SMARTS gate stayed silent")
    lines.append("")
    lines.append(
        f"The applicability rule's association branch fires when {contrast['old_gate_definition']}. "
        f"For the two held-out candidates: "
        + "; ".join(
            f"{short} donor_count={details['donor_count']}, "
            f"structural_gate_fires={details['structural_gate_fires']}"
            for short, details in contrast["held_out_under_old_gate"].items()
        )
        + ". A gate that needs a donor site cannot fire on a carbonate."
    )
    lines.append(
        f"Cross-tab over the pool (old = structural branch, new = this gate): "
        f"both {counts['both']}, old only {counts['old_only']}, "
        f"new only {counts['new_only']}, neither {counts['neither']}."
    )
    lines.append("")
    lines.append("## Honest boundaries")
    lines.append("")
    lines.append(
        "1. Scaling: the envelope is calibrated on the 236-compound pilot pool. "
        "The real funnel scores a 29.5k candidate pool, where recall for a fixed "
        "enveloping rule is systematically different. Every rate above is a "
        "236-pool rate and must travel with that count."
    )
    lines.append(
        "2. The gate does not rank. Its only action is to remove a candidate from "
        "the ranking channel and route it to measurement or a physical estimate. "
        "It says nothing about how good a retained candidate is."
    )
    lines.append(
        "3. If EC or PC had not been raised, that would be reported as a failed "
        "envelope. No k or percentile was moved to rescue either one."
    )
    return "\n".join(lines) + "\n"


def build_summary(
    prereg: dict,
    pool: Sequence[Mapping[str, str]],
    result: dict,
    source: Mapping[str, str],
    incomplete: Sequence[str],
) -> dict:
    return {
        "schema_version": 1,
        "task": prereg["task"],
        "title": prereg["title"],
        "label": LABEL,
        "shots": SHOTS,
        "generated_by": "probes/dielectric_feature_envelope_gate.py",
        # flat pins, so the repository-wide pin guard
        # (tests/test_repo_hygiene.py) resolves and audits them
        "prereg_path": portable_relative_path(PREREG_PATH, root=REPOSITORY_ROOT),
        "prereg_sha256": sha256_file(PREREG_PATH),
        "pool_path": portable_relative_path(POOL_PATH, root=REPOSITORY_ROOT),
        "pool_sha256": sha256_file(POOL_PATH),
        "features_v03_path": portable_relative_path(FEATURES_PATH, root=REPOSITORY_ROOT),
        "features_v03_sha256": sha256_file(FEATURES_PATH),
        "prereg": {
            "path": portable_relative_path(PREREG_PATH, root=REPOSITORY_ROOT),
            "sha256": sha256_file(PREREG_PATH),
            "sha256_canonical_text": canonical_text_sha256(PREREG_PATH),
            "locked_at_utc": prereg["locked_at_utc"],
            "status": prereg["status"],
        },
        "criteria_snapshot_verbatim": {
            "primary_criterion": prereg["primary_criterion"],
            "secondary_criterion": prereg["secondary_criterion"],
            "kill_line": prereg["kill_line"],
        },
        "inputs": {
            "training_domain": {
                "path": portable_relative_path(POOL_PATH, root=REPOSITORY_ROOT),
                "sha256": sha256_file(POOL_PATH),
                "sha256_raw_bytes": sha256_file(POOL_PATH),
                "rows": len(pool),
                "distinct_inchikeys": len({row["inchikey"] for row in pool}),
                "line_ending": (
                    "LF" if b"\r\n" not in POOL_PATH.read_bytes() else "CRLF"
                ),
            },
            "features": {
                "path": portable_relative_path(FEATURES_PATH, root=REPOSITORY_ROOT),
                "sha256": sha256_file(FEATURES_PATH),
            },
            "features_fallback": {
                "path": portable_relative_path(FEATURES_NEW_PATH, root=REPOSITORY_ROOT),
                "sha256": sha256_file(FEATURES_NEW_PATH)
                if FEATURES_NEW_PATH.is_file()
                else None,
                "used": False,
            },
            "descriptors": list(DESCRIPTORS),
            "feature_source_by_compound": result["feature_source"],
            "feature_rows_skipped_incomplete": list(incomplete),
            "pool_members_without_complete_descriptors": [],
        },
        "rules": {
            "robust_interval_fence": {"k": FENCE_K, "statistic": "median +/- k * IQR"},
            "knn_distance_fence": {
                "percentile": KNN_PERCENTILE,
                "metric": "euclidean_after_standardising_on_the_training_domain",
            },
        },
        "readings": result["readings"],
        "primary_check": result["primary"],
        "secondary_check": {
            "flag_rate_rule_a": result["readings"]["secondary_rule_a_rate"],
            "flag_rate_rule_b": result["readings"]["secondary_rule_b_rate"],
            "flag_rate_combined": result["readings"]["secondary_any_rate"],
            "threshold": MAX_SECONDARY_FLAG_RATE,
            "criterion_uses": "combined (either rule), matching the primary criterion's 'at least one rule'",
        },
        "criteria": result["criteria"],
        "smarts_contrast": result["smarts_contrast"],
        "action_when_flagged": prereg["action_when_flagged"],
        "scaling_note": prereg["scaling_note"],
        "target_leakage": {
            "rule_inputs": "physical descriptors of the candidate molecule only",
            "target_read_by_rules": False,
            "note": "no target_dielectric or T_K value is read anywhere in run_gate",
        },
        "outputs": {
            "summary": portable_relative_path(SUMMARY_PATH, root=REPOSITORY_ROOT),
            "report": portable_relative_path(REPORT_PATH, root=REPOSITORY_ROOT),
            "descriptor_envelope_csv": portable_relative_path(
                ENVELOPE_CSV_PATH, root=REPOSITORY_ROOT
            ),
            "pool_loo_csv": portable_relative_path(POOL_LOO_CSV_PATH, root=REPOSITORY_ROOT),
            "held_out_csv": portable_relative_path(EC_PC_CSV_PATH, root=REPOSITORY_ROOT),
        },
        "frozen_red_lines_untouched": prereg["frozen_red_lines_untouched"],
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="recompute and compare against the on-disk summary without writing",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    prereg = load_prereg()
    pool = load_pool()
    features, source, incomplete = load_descriptors()
    result = run_gate(pool, features, source)
    summary = build_summary(prereg, pool, result, source, incomplete)
    report = build_report(summary)

    if args.check:
        on_disk = _read_json(SUMMARY_PATH)
        same = json.dumps(on_disk, sort_keys=True) == json.dumps(summary, sort_keys=True)
        print("summary matches" if same else "summary DIFFERS")
        return 0 if same else 1

    write_csv_lf(ENVELOPE_CSV_PATH, ENVELOPE_FIELDS, result["envelope_rows"])
    write_csv_lf(POOL_LOO_CSV_PATH, POOL_LOO_FIELDS, result["loo_rows"])
    write_csv_lf(EC_PC_CSV_PATH, EC_PC_FIELDS, result["primary_rows"])
    _write_text(SUMMARY_PATH, json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    _write_text(REPORT_PATH, report)

    readings = result["readings"]
    print(f"training rows (primary)          : {readings['primary_training_rows']}")
    print(f"EC flagged                       : {result['primary']['EC']['flagged']}")
    print(f"PC flagged                       : {result['primary']['PC']['flagged']}")
    print(f"LOO flag rate (combined)         : {readings['secondary_any_rate']:.4f}")
    print(f"verdict                          : {result['criteria']['verdict']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())