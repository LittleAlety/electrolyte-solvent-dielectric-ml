"""W22-3 / B5 / D7 -- the broad-pool minimum-information-budget demonstration.

One question, one pre-registered criterion, one number the reviewer asked for:
*on the 115,756-row ranking-key candidate pool, how many compounds does the
cheap layer say are worth promoting to an expensive layer, and how much of the
naive "promote everything" budget does that save?*

The criterion is locked in ``w22_broad_pool_budget_prereg.json`` before this
script runs and may not be swapped afterwards.  The script refuses to run if the
input file no longer matches the sha256 recorded at lock time.

Everything is streamed: the pool is 45 MB / 115,757 lines and is never loaded
into memory.  The summary carries no wall-clock timestamp so it, too, is
byte-reproducible.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path

SCHEMA_VERSION = 1
ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "probes" / "artifacts" / "w20_ranking_key_v1_candidates.csv"
PREREG = ROOT / "probes" / "w22_broad_pool_budget_prereg.json"
SUMMARY = ROOT / "probes" / "w22_broad_pool_budget_summary.json"

TRUE_TOKENS = {"true", "1", "yes", "y", "t"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def is_true(value: str) -> bool:
    return (value or "").strip().lower() in TRUE_TOKENS


def scan_pool(path: Path) -> dict:
    total = 0
    in_domain = 0
    on_front = 0
    key_score_present = 0
    criterion_upgrade = 0
    domain_and_front = 0
    excluded_reasons: dict = {}
    ranking_channels: dict = {}
    both_key_dimensions = 0
    ranked_rows = 0
    with path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            total += 1
            dom = (row.get("domain") or "").strip()
            front = is_true(row.get("on_front"))
            scored = bool((row.get("key_score") or "").strip())
            if dom == "in_domain":
                in_domain += 1
            if front:
                on_front += 1
            if scored:
                key_score_present += 1
            if dom == "in_domain" and front:
                domain_and_front += 1
            if dom == "in_domain" and front and scored:
                criterion_upgrade += 1
            reason = (row.get("excluded_reason") or "").strip() or "(none)"
            excluded_reasons[reason] = excluded_reasons.get(reason, 0) + 1
            channel = (row.get("ranking_channels") or "").strip() or "(none)"
            ranking_channels[channel] = ranking_channels.get(channel, 0) + 1
            if (row.get("HOMO_eV") or "").strip() and (row.get("LUMO_eV") or "").strip():
                both_key_dimensions += 1
            if (row.get("rank") or "").strip():
                ranked_rows += 1
    return {
        "candidates_total": total,
        "in_domain": in_domain,
        "on_front": on_front,
        "key_score_present": key_score_present,
        "in_domain_and_on_front": domain_and_front,
        "criterion_upgrade": criterion_upgrade,
        "filtered_out": total - criterion_upgrade,
        "excluded_reasons": excluded_reasons,
        "ranking_channels": ranking_channels,
        "both_key_dimensions": both_key_dimensions,
        "ranked_rows": ranked_rows,
    }


def build_summary(prereg: dict, stats: dict, digest: str, size: int) -> dict:
    total = stats["candidates_total"]
    upgrade = stats["criterion_upgrade"]
    savings_ratio = 0.0 if total == 0 else 1.0 - (upgrade / total)
    return {
        "schema_version": SCHEMA_VERSION,
        "task_id": "week22_w22_3_broad_pool_budget",
        "title": "broad-pool 最小信息预算演示（B5 / D7）：唯一升级判据下的候选数与节省比例",
        "preregistration": {
            "path": "probes/w22_broad_pool_budget_prereg.json",
            "sha256": sha256_file(PREREG),
            "status": prereg["prereg_status"],
        },
        "plan_reference": "reports/week22_project_charter.md | W22-3",
        "locked_criterion": prereg["locked_criterion"],
        "input": {
            "path": "probes/artifacts/w20_ranking_key_v1_candidates.csv",
            "sha256": digest,
            "bytes": size,
            "sha256_matches_prereg": True,
        },
        "funnel": {
            "candidates_total": total,
            "in_domain": stats["in_domain"],
            "on_front": stats["on_front"],
            "key_score_present": stats["key_score_present"],
            "in_domain_and_on_front": stats["in_domain_and_on_front"],
            "criterion_upgrade": upgrade,
            "filtered_out": stats["filtered_out"],
        },
        "savings": {
            "upgrade_all_baseline": total,
            "criterion_upgrade": upgrade,
            "calls_avoided": total - upgrade,
            "savings_ratio": savings_ratio,
            "definition": "savings_ratio = 1 - criterion_upgrade / candidates_total",
        },
        "diagnostics": {
            "note": "以下为分解读数，不是判据变体；判据在跑前锁定且跑后未改。",
            "domain_gate_rejections": total - stats["in_domain"],
            "rows_with_both_key_dimensions": stats["both_key_dimensions"],
            "ranked_rows": stats["ranked_rows"],
            "excluded_reason_histogram": dict(sorted(stats["excluded_reasons"].items())),
            "ranking_channels_histogram": dict(sorted(stats["ranking_channels"].items())),
        },
        "readings": [
            {"name": "candidates_total", "value": total,
             "source": "probes/artifacts/w20_ranking_key_v1_candidates.csv | 行数"},
            {"name": "in_domain", "value": stats["in_domain"],
             "source": "同表 | column=domain == 'in_domain'"},
            {"name": "on_front", "value": stats["on_front"],
             "source": "同表 | column=on_front 为真"},
            {"name": "key_score_present", "value": stats["key_score_present"],
             "source": "同表 | column=key_score 非空"},
            {"name": "criterion_upgrade", "value": upgrade,
             "source": "同表 | domain=='in_domain' 且 on_front 为真 且 key_score 非空"},
            {"name": "filtered_out", "value": stats["filtered_out"],
             "source": "同表 | candidates_total - criterion_upgrade"},
            {"name": "savings_ratio", "value": savings_ratio,
             "source": "同表 | 1 - criterion_upgrade / candidates_total"},
        ],
        "discipline": {
            "produces_reading": False,
            "promoted": False,
            "main_scoreboard_untouched": True,
            "new_expensive_calculations": 0,
            "criterion_swapped_after_run": False,
            "honest_scope": (
                "该池为 Tier C 单点筛查池：按发布前锁定的 D1 域规则（NumHDonors>=1 且 "
                "TPSA>=20）全部判域外，故没有候选获得 key_score、前沿为空。节省比例 1.0 "
                "由域闸门承担，而不是由排序键承担；这一点必须与排序质量分开叙述。"
            ),
        },
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Broad-pool minimum-information-budget demo (W22-3).")
    parser.add_argument("--check", action="store_true", help="recompute and compare with the on-disk summary")
    args = parser.parse_args(argv)

    prereg = json.loads(PREREG.read_text(encoding="utf-8"))
    digest = sha256_file(INPUT)
    if digest != prereg["input"]["sha256"]:
        print(f"[guard] input sha256 mismatch: disk={digest} prereg={prereg['input']['sha256']}")
        return 2

    summary = build_summary(prereg, scan_pool(INPUT), digest, INPUT.stat().st_size)
    payload = json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n"

    if args.check:
        if not SUMMARY.exists():
            print(f"[check] MISSING {SUMMARY}")
            return 2
        if SUMMARY.read_text(encoding="utf-8") == payload:
            print("[check] OK")
            return 0
        print("[check] DRIFT")
        return 1

    SUMMARY.write_text(payload, encoding="utf-8", newline="\n")
    print(f"[build] wrote {SUMMARY} ({len(payload.encode('utf-8'))} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())