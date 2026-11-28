#!/usr/bin/env python
"""B720-01: recover the LiquidBenchmark dielectric tables from the pinned commit.

Why a pinned commit: the repository's last push was 2017-02-03, and later edits to
`tables/` would silently change what "LiquidBenchmark" means. Pinning the SHA makes
the recovered numbers reproducible and the licence/vintage auditable.

Licence: the repo is GPL-2.0. GPL-2.0 permits redistribution of the data WITH the
licence, so the raw CSVs are stored under data/external_raw/liquidbenchmark/ along
with the LICENSE text. We do not relicense them and we do not modify them.

Transport note: raw.githubusercontent.com resets the connection from this host, so
the GitHub contents API (which returns base64) is used instead. Every downloaded
file's SHA256 is recorded so a later disagreement is detectable.

Outputs:
  data/external_raw/liquidbenchmark/<file>          (unmodified)
  data/external_raw/liquidbenchmark/PROVENANCE.json (commit, hashes, licence)
"""

from __future__ import annotations

import base64
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEST = REPO_ROOT / "data" / "external_raw" / "liquidbenchmark"
GEN = "recover_liquidbenchmark/1.0.0"

OWNER_REPO = "choderalab/LiquidBenchmark"
# Pinned to the last commit that touched tables/ history (2017-02-03).
COMMIT = "215ca63a6651625afa96975eedb820f806eb59cd"
FILES = [
    "README.md",
    "LICENSE",
    "tables/data_dielectric.csv",
    "tables/data_with_metadata.csv",
]


def fetch_via_api(path: str) -> bytes:
    url = (f"https://api.github.com/repos/{OWNER_REPO}/contents/{path}"
           f"?ref={COMMIT}")
    r = subprocess.run(["curl", "-sS", "-m", "120", url],
                       capture_output=True)
    if r.returncode != 0:
        raise RuntimeError(f"curl failed for {path}: {r.stderr[:200]!r}")
    payload = json.loads(r.stdout.decode("utf-8"))
    if "content" not in payload:
        raise RuntimeError(f"no content for {path}: {str(payload)[:300]}")
    enc = payload.get("encoding")
    if enc != "base64":
        raise RuntimeError(f"unexpected encoding {enc} for {path}")
    return base64.b64decode(payload["content"])


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def main() -> None:
    DEST.mkdir(parents=True, exist_ok=True)
    records = {}
    for rel in FILES:
        # keep the repo-relative name but flatten tables/ into the dest dir
        name = rel.replace("tables/", "")
        data = fetch_via_api(rel)
        out = DEST / name
        out.write_bytes(data)
        records[rel] = {
            "saved_as": str(out.relative_to(REPO_ROOT)).replace("\\", "/"),
            "bytes": len(data),
            "sha256": sha256_bytes(data),
        }
        print(f"  {rel:40s} {len(data):>9d} bytes  {records[rel]['sha256'][:16]}")

    prov = {
        "schema": "b720.liquidbenchmark_provenance/v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "generator": GEN,
        "repository": f"https://github.com/{OWNER_REPO}",
        "pinned_commit": COMMIT,
        "commit_date": "2017-02-03T23:42:23Z",
        "repository_last_push": "2017-02-03T23:42:24Z",
        "licence": "GPL-2.0",
        "licence_note": (
            "GPL-2.0 permits redistribution with the licence text; LICENSE is stored "
            "alongside the data and the files are otherwise unmodified."
        ),
        "associated_paper": (
            "Beauchamp et al., J. Phys. Chem. B 2015 — 'Toward Automated Tools to "
            "Practice Computational Chemistry: Dielectric Constants and Densities "
            "of Organic Liquids'"
        ),
        "transport": (
            "GitHub contents API (base64) because raw.githubusercontent.com resets "
            "connections from this host; pinned ?ref=<commit> so the payload is the "
            "same bytes a git checkout would give."
        ),
        "files": records,
        "immutability": "files stored byte-identical; never edited in place",
    }
    (DEST / "PROVENANCE.json").write_text(
        json.dumps(prov, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nWrote {DEST / 'PROVENANCE.json'}")
    print(f"commit {COMMIT[:12]}, licence GPL-2.0, {len(records)} files")


if __name__ == "__main__":
    main()
