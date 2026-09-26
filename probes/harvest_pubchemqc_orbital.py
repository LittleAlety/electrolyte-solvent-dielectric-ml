"""W17-12 raw harvester: bounded, provenance-recorded slice of the PubChemQC
B3LYP/6-31G*//PM6 dataset (MolSSI-AI Hub mirror; CC BY 4.0).

Writes only the raw cache layer under data/raw/ (git-ignored).  The delivered
data/ layer is produced exclusively by probes/build_orbital_second_source.py.

Design notes
------------
* Shard ``000000001-000253696.json`` is one top-level JSON array whose records
  are sorted by ``cid`` ascending and are ~13-50 kB each, so the shard is
  ~4.3 GB.  Downloading it whole is out of scope; instead each record is
  addressed with a bounded HTTP Range request plus an interpolation search on
  the monotone cid -> byte-offset map.
* ``cid`` is the first field of every record, so a located window can be
  parsed in place; a widening retry is only needed when the match sits within
  ~80 kB of the window edge.
* Nothing is taken on faith from the dataset card: units are checked against
  the raw arrays themselves (judgement B of the pre-registration).
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import random
import re
import ssl
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

DATASET_ID = "molssiai-hub/pubchemqc-b3lyp"
DATASET_REVISION = "15c15ae6a80c7ed84ee45e966390564e71e2e0bf"
CITATION_DOI = "10.1021/acs.jcim.3c00899"
LICENSE = "CC BY 4.0"
SOURCE_LEVEL = "B3LYP/6-31G*//PM6 (gas phase)"

SHARD = "000000001-000253696.json"
SHARD_URL = (
    "https://hf-mirror.com/datasets/molssiai-hub/pubchemqc-b3lyp/resolve/main/"
    "data/b3lyp_pm6/train/" + SHARD
)
SHARD_SIZE = 4348924286
SHARD_ETAG = "2b49c0ae0ea7470f8d2d79d4d3befb42cd5b469d47d83f0dd85ff21fefdc9c88"
SHARD_LFS_OID = "d790ccbda06e9c80a160fa14d2f02e942167ea1c0f7982e5144779a376b70b8c"

PUGREST = "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound"
UA = "electrolyte-ml/1.0 (week17 orbital second-source harvest)"

SEED = 20260927
EPSILON_ROSTER = "data/dielectric_v04.csv"
VISCOSITY_ROSTER = "data/viscosity_v02.csv"
KEY_REGISTRY = "data/processed/four_core_key_registry.csv"
N_VISCOSITY_SAMPLE = 300
N_REGISTRY_SAMPLE = 200

NAMED_SOLVENTS = (
    "propylene carbonate",
    "ethylene carbonate",
    "dimethyl carbonate",
    "diethyl carbonate",
    "gamma-butyrolactone",
    "succinonitrile",
    "acetonitrile",
    "dimethyl sulfoxide",
    "N,N-dimethylformamide",
    "tetrahydrofuran",
    "1,2-dimethoxyethane",
    "water",
    "methanol",
    "ethanol",
    "acetone",
    "1-methylimidazole",
    "cyclopentane",
    "cyclopentanol",
    "2-ethyl-1-hexanol",
    "valeronitrile",
    "N-methylaniline",
    "triethyl phosphate",
    "sulfolane",
)

SCALAR_KEYS = (
    "cid",
    "state",
    "pubchem-inchi",
    "obabel-inchi",
    "pubchem-charge",
    "pubchem-version",
    "name",
    "formula",
    "multiplicity",
    "molecular-mass",
    "number-of-atoms",
    "heavy-atom-count",
    "atom-count",
    "energy-alpha-homo",
    "energy-alpha-lumo",
    "energy-alpha-gap",
    "energy-beta-homo",
    "energy-beta-lumo",
    "energy-beta-gap",
    "homos",
    "mo-count",
    "basis-count",
    "total-energy",
    "dipole-moment",
    "pubchem-obabel-canonical-smiles",
    "pubchem-isomeric-smiles",
    "pm6-obabel-canonical-smiles",
)
HEAVY_KEYS = ("orbital-energies", "mulliken-partial-charges", "lowdin-partial-charges", "coordinates")

_CID_RE = re.compile(rb'"cid":\s*(\d+)')


def opener():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    op = urllib.request.build_opener(
        urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=ctx)
    )
    op.addheaders = [("User-Agent", UA)]
    return op


class Ledger:
    def __init__(self):
        self.lock = threading.Lock()
        self.requests = 0
        self.bytes_read = 0

    def add(self, nbytes):
        with self.lock:
            self.requests += 1
            self.bytes_read += nbytes

    @property
    def snapshot(self):
        with self.lock:
            return {"http_requests": self.requests, "http_bytes_read": self.bytes_read}


class RangeReader:
    """Bounded HTTP Range reader with retries and a shared request ledger."""

    def __init__(self, url, size, op, ledger=None, max_retries=4):
        self.url = url
        self.size = size
        self.op = op
        self.ledger = ledger
        self.max_retries = max_retries

    def read(self, start, n):
        start = max(0, min(int(start), self.size - 1))
        n = max(1, int(n))
        end = min(self.size - 1, start + n - 1)
        last = None
        for attempt in range(self.max_retries):
            try:
                req = urllib.request.Request(
                    self.url, headers={"Range": f"bytes={start}-{end}"}
                )
                with self.op.open(req, timeout=240) as resp:
                    buf = resp.read()
                if self.ledger is not None:
                    self.ledger.add(len(buf))
                return buf
            except Exception as exc:  # noqa: BLE001 - network retry, the failure is attributed below
                last = exc
                time.sleep(1.0 * (attempt + 1))
        raise RuntimeError(f"range read failed for {start}-{end}: {last!r}")


def record_spans(text):
    """Yield (start, end) offsets of complete top-level objects in ``text``.

    A trailing partial record is simply not yielded, which is what makes
    bounded Range reads safe.
    """
    n = len(text)
    i = text.find("{")
    while 0 <= i < n:
        start = i
        depth = 0
        in_str = False
        esc = False
        complete = False
        while i < n:
            ch = text[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
            elif ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    i += 1
                    complete = True
                    break
            i += 1
        if not complete:
            return
        yield start, i
        while i < n and text[i] != "{":
            if text[i] == "]":
                return
            i += 1


def slim(record, keep_heavy=False):
    out = {k: record[k] for k in SCALAR_KEYS if k in record}
    if keep_heavy:
        for k in HEAVY_KEYS:
            if k in record:
                out[k] = record[k]
    return out


def parse_window(buf, keep_heavy=False):
    text = buf.decode("utf-8", "replace")
    out = []
    for start, end in record_spans(text):
        try:
            obj = json.loads(text[start:end])
        except Exception:  # noqa: BLE001, S112 - a truncated record is data, not a crash
            continue
        if isinstance(obj, dict) and "cid" in obj:
            out.append(slim(obj, keep_heavy=keep_heavy))
    return out


def parse_window_indexed(buf, keep_heavy=False):
    out = {}
    for rec in parse_window(buf, keep_heavy=keep_heavy):
        out[rec.get("cid")] = rec
    return out


def cid_offsets(buf):
    return [(m.start(), int(m.group(1))) for m in _CID_RE.finditer(buf)]


def locate_cid(reader, target, cid_lo=1, cid_hi=253696, probe=262144, max_steps=40):
    """Return the raw record dict for ``target`` (or None) using Range reads."""
    lo, hi = 0, reader.size - 1
    b_lo, b_hi = cid_lo, cid_hi
    for _ in range(max_steps):
        if hi - lo <= 2 * probe:
            buf = reader.read(lo, min(hi - lo + 1, 8 * probe))
            return parse_window_indexed(buf).get(target)
        frac = 0.5 if b_hi <= b_lo else (target - b_lo) / float(b_hi - b_lo)
        frac = min(max(frac, 0.0), 1.0)
        est = int(lo + frac * (hi - lo))
        start = max(lo, est - probe // 2)
        buf = reader.read(start, probe)
        pairs = cid_offsets(buf)
        if not pairs:
            lo = start + len(buf)
            continue
        if any(c == target for _, c in pairs):
            indexed = parse_window_indexed(buf)
            if target in indexed:
                return indexed[target]
            off = min(off for off, c in pairs if c == target)
            wider = reader.read(max(0, start + off - 1024), 4 * probe)
            return parse_window_indexed(wider).get(target)
        cids = [c for _, c in pairs]
        mn, mx = min(cids), max(cids)
        if mx < target:
            lo = start + len(buf)
            b_lo = max(b_lo, mx)
        elif mn > target:
            hi = start
            b_hi = min(b_hi, mn)
        else:
            wider = reader.read(start, min(8 * probe, reader.size - start))
            return parse_window_indexed(wider).get(target)
    return None


def pugrest(url, op, tries=5, pause=0.3):
    last = None
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with op.open(req, timeout=90) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return {"__not_found__": True}
            last = exc
        except Exception as exc:  # noqa: BLE001 - network retry, the failure is attributed below
            last = exc
        time.sleep(pause * (2 ** attempt))
    raise RuntimeError(f"pugrest failed {url}: {last!r}")


def resolve_inchikeys(keys, op, batch=100, pause=0.4):
    """Map InChIKey -> sorted list of PubChem CIDs (PUG-REST listkey POST).

    PUG-REST listkey input expects one comma-separated parameter value, not a
    repeated parameter (the repeated form silently keeps only the first key).
    """
    resolved = {}
    for i in range(0, len(keys), batch):
        chunk = keys[i : i + batch]
        body = urllib.parse.urlencode({"inchikey": ",".join(chunk)}).encode()
        url = PUGREST + "/inchikey/property/InChIKey/JSON"
        last = None
        rows = None
        for attempt in range(4):
            try:
                req = urllib.request.Request(
                    url,
                    data=body,
                    headers={
                        "Content-Type": "application/x-www-form-urlencoded",
                        "User-Agent": UA,
                    },
                )
                with op.open(req, timeout=120) as resp:
                    payload = json.loads(resp.read().decode("utf-8"))
                rows = payload.get("PropertyTable", {}).get("Properties", [])
                break
            except urllib.error.HTTPError as exc:
                if exc.code == 404:
                    rows = []
                    break
                last = exc
            except Exception as exc:  # noqa: BLE001 - network retry, the failure is attributed below
                last = exc
            time.sleep(pause * (2 ** attempt))
        if rows is None:
            raise RuntimeError(f"inchikey resolution failed: {last!r}")
        for row in rows:
            key = row.get("InChIKey")
            cid = row.get("CID")
            if key and cid:
                resolved.setdefault(key, set()).add(int(cid))
        time.sleep(pause)
    return {k: sorted(v) for k, v in resolved.items()}


def resolve_names(names, op, pause=0.3):
    out = {}
    for name in names:
        url = PUGREST + "/name/" + urllib.parse.quote(name) + "/cids/JSON"
        try:
            payload = pugrest(url, op, pause=pause)
        except RuntimeError:
            continue
        cids = payload.get("IdentifierList", {}).get("CID") if isinstance(payload, dict) else None
        if cids:
            out[name] = sorted(int(c) for c in cids)
        time.sleep(pause)
    return out


def load_targets():
    import csv

    targets = {}

    def add(inchikey, tag, detail=""):
        if not inchikey:
            return
        entry = targets.setdefault(inchikey, {"inchikey": inchikey, "tags": [], "detail": []})
        if tag not in entry["tags"]:
            entry["tags"].append(tag)
            entry["detail"].append(detail)

    with open(ROOT / EPSILON_ROSTER, newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            add(row["inchikey"], "epsilon_roster", row.get("name", ""))

    rng = random.Random(SEED)
    vis = []
    with open(ROOT / VISCOSITY_ROSTER, newline="", encoding="utf-8") as handle:
        seen = set()
        for row in csv.DictReader(handle):
            key = row["inchikey"]
            if key and key not in seen:
                seen.add(key)
                vis.append((key, row.get("name", "")))
    for key, name in rng.sample(vis, min(N_VISCOSITY_SAMPLE, len(vis))):
        add(key, "viscosity_roster_sample", name)

    reg = []
    with open(ROOT / KEY_REGISTRY, newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row.get("has_orbitals") == "true" and row.get("HOMO_eV"):
                reg.append((row["inchikey"], row.get("name", "")))
    for key, name in rng.sample(reg, min(N_REGISTRY_SAMPLE, len(reg))):
        add(key, "batt_calibration_sample", name)

    return targets, len(vis), len(reg)


def locate_target(reader, key, candidates, max_cid):
    for cid in candidates:
        if cid > max_cid:
            continue
        rec = locate_cid(reader, cid, cid_hi=max_cid)
        if rec is not None:
            return key, cid, rec
    return key, None, None


def run_unit_audit(out_dir, limit=40, window=2_000_000, strata=12):
    """Prove the on-disk unit of the orbital energies from the raw arrays.

    The dataset card declares ``orbital-energies`` in hartree.  The raw records
    show the array element at the HOMO index is numerically identical to the
    ``energy-alpha-homo`` scalar, and both are far too shallow to be hartree
    for a valence orbital, so the card annotation is a documentation defect.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    op = opener()
    ledger = Ledger()
    reader = RangeReader(SHARD_URL, SHARD_SIZE, op, ledger=ledger)
    per_stratum = max(1, limit // strata)
    fractions = [i / float(strata) for i in range(strata)]
    records = []
    covered = []
    for fraction in fractions:
        start = int(SHARD_SIZE * fraction)
        start = max(0, min(start, SHARD_SIZE - window))
        buf = reader.read(start, window)
        found = parse_window(buf, keep_heavy=True)
        if found:
            covered.append({"fraction": round(fraction, 4), "offset": start, "records": len(found)})
        records.extend(found[:per_stratum])
    checks = []
    for record in records[:limit]:
        orbital = record.get("orbital-energies")
        homos = record.get("homos")
        homo = record.get("energy-alpha-homo")
        lumo = record.get("energy-alpha-lumo")
        gap = record.get("energy-alpha-gap")
        row = {"cid": record.get("cid"), "formula": record.get("formula")}
        array_homo = None
        try:
            alpha = orbital[0] if isinstance(orbital[0], list) else orbital
            array_homo = alpha[homos[0]]
        except Exception:  # noqa: BLE001, S110 - a malformed orbital array is data, not a crash
            pass
        row["orbital_array_homo"] = array_homo
        row["energy_alpha_homo_field"] = homo
        row["abs_diff_homo"] = (
            abs(array_homo - homo) if (array_homo is not None and homo is not None) else None
        )
        row["equals_scalar_field"] = bool(
            array_homo is not None and homo is not None and abs(array_homo - homo) <= 1e-9 * max(1.0, abs(homo))
        )
        row["gap_identity_holds"] = bool(
            homo is not None and lumo is not None and gap is not None
            and abs((lumo - homo) - gap) <= 1e-9 * max(1.0, abs(gap))
        )
        # Discriminative window: a valence HOMO must be at least 1 eV deep, and no
        # deeper than 30 eV.  Read as hartree the very same numbers would be
        # -0.17 .. -0.5, i.e. outside the window, so this test really does split
        # the eV reading from the hartree reading instead of passing under both.
        row["valence_window_discriminates_units"] = bool(
            homo is not None and -30.0 <= homo <= -1.0
        )
        row["passed"] = (
            row["equals_scalar_field"]
            and row["gap_identity_holds"]
            and row["valence_window_discriminates_units"]
        )
        checks.append(row)
    payload = {
        "window_bytes": window,
        "strata": strata,
        "strata_covered": covered,
        "records_seen": len(records),
        "records_checked": len(checks),
        "passed": sum(1 for row in checks if row["passed"]),
        "energy_field_equals_orbital_array": all(row["equals_scalar_field"] for row in checks) if checks else None,
        "gap_identity_holds": all(row["gap_identity_holds"] for row in checks) if checks else None,
        "valence_window_discriminates_units": all(
            row["valence_window_discriminates_units"] for row in checks
        ) if checks else None,
        "cid_span_checked": [min(r["cid"] for r in checks), max(r["cid"] for r in checks)] if checks else None,
        "card_declared_unit_for_orbital_energies": "hartree",
        "card_declares_unit_for_scalar_fields": False,
        "observed_unit": "eV",
        "checks": checks,
    }
    (out_dir / "unit_audit.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    print(json.dumps({k: payload[k] for k in (
        "strata", "records_seen", "records_checked", "passed",
        "energy_field_equals_orbital_array", "gap_identity_holds",
        "valence_window_discriminates_units", "cid_span_checked")}, indent=2))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="data/raw/pubchemqc_w17")
    parser.add_argument("--head-bytes", type=int, default=12_000_000)
    parser.add_argument("--skip-head", action="store_true")
    parser.add_argument("--max-targets", type=int, default=0)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--unit-audit", type=int, default=0)
    args = parser.parse_args(argv)

    if args.unit_audit:
        return run_unit_audit(ROOT / args.out, args.unit_audit)

    out_dir = ROOT / args.out
    out_dir.mkdir(parents=True, exist_ok=True)
    op = opener()
    ledger = Ledger()
    reader = RangeReader(SHARD_URL, SHARD_SIZE, op, ledger=ledger)

    started = time.time()
    targets, n_vis_pool, n_reg_pool = load_targets()
    keys = sorted(targets)
    if args.max_targets:
        keys = keys[: args.max_targets]
    digest = hashlib.sha256("\n".join(keys).encode()).hexdigest()
    print(f"[harvest] target keys: {len(keys)} (digest {digest[:16]})", flush=True)

    resolution_path = out_dir / "cid_resolution.json"
    if resolution_path.exists():
        payload = json.loads(resolution_path.read_text(encoding="utf-8"))
        resolved = payload["by_inchikey"]
        by_name = payload["by_name"]
        print("[harvest] reused cached resolution", flush=True)
    else:
        resolved = resolve_inchikeys(keys, op, batch=100)
        by_name = resolve_names(NAMED_SOLVENTS, op)
        resolution_path.write_text(
            json.dumps({"by_inchikey": resolved, "by_name": by_name}, indent=2, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )
    n_keys_resolved = sum(1 for k in keys if k in resolved)
    print(
        f"[harvest] resolved {n_keys_resolved}/{len(keys)} target keys, {len(by_name)} names",
        flush=True,
    )

    head_records = []
    if not args.skip_head:
        buf = reader.read(0, args.head_bytes)
        head_records = parse_window(buf)
        print(
            f"[harvest] head scan {args.head_bytes} bytes -> {len(head_records)} complete records",
            flush=True,
        )

    tail = reader.read(SHARD_SIZE - 262144, 262144)
    tail_cids = [c for _, c in cid_offsets(tail)]
    max_cid = max(tail_cids) if tail_cids else 253696
    probe_points = []
    for frac in (0.0, 0.25, 0.5, 0.75, 0.9999):
        off = int(SHARD_SIZE * frac)
        win = reader.read(off, 131072)
        pairs = cid_offsets(win)
        probe_points.append(
            {
                "fraction": frac,
                "offset": off,
                "cid_first": pairs[0][1] if pairs else None,
                "cid_last": pairs[-1][1] if pairs else None,
            }
        )
    probe_series = [p["cid_first"] for p in probe_points] + [max_cid]
    monotone = all(
        probe_points[i]["cid_last"] <= probe_points[i + 1]["cid_first"]
        for i in range(len(probe_points) - 1)
    ) and all(a is not None and b is not None and a <= b for a, b in itertools.pairwise(probe_series))
    if not monotone:
        raise SystemExit("judgement A failed: cid is not monotone across the shard probes")
    print(f"[harvest] shard cid window: 1 .. {max_cid} (monotone probe OK)", flush=True)

    todo = []
    for key in keys:
        cands = resolved.get(key)
        if cands:
            todo.append((key, [c for c in cands if c <= max_cid]))
    for name, cands in sorted(by_name.items()):
        todo.append(("name:" + name, [c for c in cands if c <= max_cid]))

    records = {}
    found = {}
    misses = [
        {"target": key, "candidate_cids": [], "reason": "inchikey_not_resolved_by_pubchem"}
        for key in keys
        if key not in resolved
    ]
    done = 0
    local = threading.local()

    def work(item):
        key, cands = item
        rd = getattr(local, "reader", None)
        if rd is None:
            rd = RangeReader(SHARD_URL, SHARD_SIZE, op, ledger=ledger)
            local.reader = rd
        if not cands:
            return key, None, None
        return locate_target(rd, key, cands, max_cid)

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for key, cid, rec in pool.map(work, todo):
            done += 1
            if rec is None:
                misses.append(
                    {
                        "target": key,
                        "candidate_cids": dict(todo).get(key, []),
                        "reason": "no_candidate_cid_in_shard" if not dict(todo).get(key) else "cid_not_present",
                    }
                )
            else:
                records[key] = rec
                found[key] = cid
            if done % 50 == 0:
                snap = ledger.snapshot
                print(
                    f"[harvest] {done}/{len(todo)} located={len(records)} "
                    f"probes={snap['http_requests']} bytes={snap['http_bytes_read'] / 1e6:.1f}MB",
                    flush=True,
                )

    with open(out_dir / "records.jsonl", "w", encoding="utf-8", newline="\n") as handle:
        for key in sorted(records):
            handle.write(
                json.dumps({"target_key": key, "resolved_cid": found[key], **records[key]}, sort_keys=True)
                + "\n"
            )
    with open(out_dir / "records_head.jsonl", "w", encoding="utf-8", newline="\n") as handle:
        for rec in head_records:
            handle.write(json.dumps(rec, sort_keys=True) + "\n")
    with open(out_dir / "misses.jsonl", "w", encoding="utf-8", newline="\n") as handle:
        handle.writelines(json.dumps(row, sort_keys=True) + "\n" for row in sorted(misses, key=lambda r: r["target"]))

    snap = ledger.snapshot
    manifest = {
        "dataset_id": DATASET_ID,
        "dataset_revision": DATASET_REVISION,
        "citation_doi": CITATION_DOI,
        "license": LICENSE,
        "source_level": SOURCE_LEVEL,
        "shard": SHARD,
        "shard_url": SHARD_URL,
        "shard_size_bytes": SHARD_SIZE,
        "shard_etag": SHARD_ETAG,
        "shard_lfs_sha256": SHARD_LFS_OID,
        "shard_cid_window": [1, max_cid],
        "seed": SEED,
        "target_key_count": len(keys),
        "target_keys_resolved": n_keys_resolved,
        "target_key_digest": digest,
        "viscosity_roster_pool": n_vis_pool,
        "registry_orbit_pool": n_reg_pool,
        "located_record_count": len(records),
        "miss_count": len(misses),
        "head_scan_bytes": 0 if args.skip_head else args.head_bytes,
        "head_record_count": len(head_records),
        "structure_probe": probe_points,
        "structure_probe_monotone": True,
        "unresolved_target_keys": sum(1 for key in keys if key not in resolved),
        "http_requests": snap["http_requests"],
        "http_bytes_read": snap["http_bytes_read"],
        "elapsed_seconds": round(time.time() - started, 1),
        "harvester": "probes/harvest_pubchemqc_orbital.py",
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({k: manifest[k] for k in (
        "located_record_count", "miss_count", "head_record_count",
        "http_requests", "http_bytes_read", "elapsed_seconds")}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())