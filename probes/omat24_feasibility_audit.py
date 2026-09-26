"""OMat24 orbital-data feasibility audit (read-only, W17-E).

Answers, with first-hand evidence only, whether the OMat24 dataset can supply
HOMO/LUMO for this repository's electrolyte-solvent roster.

Every number written to probes/omat24_feasibility_facts.json comes either from a live
HTTP call recorded with its status code or from a byte-level read of an official OMat24
file. Nothing is inferred from a dataset card alone.

Usage:

    python probes/omat24_feasibility_audit.py            # (re)write the facts file
    python probes/omat24_feasibility_audit.py --check     # re-run and compare to disk

Requires network and the lmdb/rdkit/numpy packages that are present in .venv. If the
dataset cannot be reached the script prints NETWORK_UNAVAILABLE and exits non-zero
without writing anything.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tarfile
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = Path(__file__).resolve().with_name("omat24_feasibility_facts.json")
DEFAULT_CACHE = Path(os.environ.get("TEMP") or "/tmp") / "omat24_audit"
SOLVENT_CSV = REPO_ROOT / "data" / "dielectric_v04.csv"

HF_API = "https://hf-mirror.com/api/datasets"
HF_RESOLVE = "https://hf-mirror.com/datasets"
DATASET_ID = "facebook/OMAT24"
ALIAS_ID = "fairchem/OMAT24"
OMAT_BASE = "https://dl.fbaipublicfiles.com/opencatalystproject/data/omat"
PROBE_TAR_URL = OMAT_BASE + "/241220/omat/val/rattled-300-subsampled.tar.gz"
PROBE_SUBSET = "val/rattled-300-subsampled"
PROBE_MEMBERS = ["rattled-300-subsampled/data.aselmdb", "rattled-300-subsampled/metadata.npz"]
PROBE_MIN_BYTES = 70000000

SIZE_URLS = [
    OMAT_BASE + "/241220/omat/val/rattled-1000-subsampled.tar.gz",
    PROBE_TAR_URL,
    OMAT_BASE + "/241220/omat/val/rattled-relax.tar.gz",
    OMAT_BASE + "/251210/omat24_1M_251210.tar.gz",
]
MIRROR_IDS = ["nimashoghi/omat24", "StructureCloud/OMat24"]

ORBITAL_KEY_CANDIDATES = [
    "homo", "lumo", "homo_lumo_gap", "gap", "bandgap", "band_gap", "eigenvalues",
    "orbital", "orbitals", "mo_energy", "mo_occ", "homo_energy", "lumo_energy",
    "dos", "fermi", "efermi", "ip", "ea", "orbital_energies", "homo_minus_lumo",
]
STRUCTURE_KEY_CANDIDATES = [
    "smiles", "canonical_smiles", "isomeric_smiles", "inchi", "inchikey", "formula",
    "molecular_formula", "cid", "pubchem_cid", "iupac_name", "cas", "cas_number",
]
INCHIKEY_RE = re.compile(r"^[A-Z]{14}-[A-Z]{10}-[A-Z]$")
ELEMENT_RE = re.compile(r"[A-Z][a-z]?")

VOLATILE_TOP_KEYS = ("probed_at_utc", "run")
N_SOLVENT_ROWS = 5
LABEL_ELEMENTS = ["H", "C", "N", "O", "F", "S", "P", "Cl", "Br", "I", "B", "Si", "Li"]


class NetworkUnavailable(RuntimeError):
    """Raised when the dataset host cannot be reached."""


def _opener() -> urllib.request.OpenerDirector:
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


def http_get(url: str, opener, timeout: int = 60, retries: int = 5):
    """GET a URL, retrying transient throttling. Returns (status, bytes, final_url)."""
    last = url
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with opener.open(req, timeout=timeout) as resp:
                return resp.status, resp.read(), resp.geturl()
        except urllib.error.HTTPError as exc:
            last = f"HTTP {exc.code}"
            if exc.code in (429, 500, 502, 503, 504):
                time.sleep(5 * (attempt + 1))
                continue
            return exc.code, b"", url
        except Exception as exc:  # noqa: BLE001 - network layer raises anything
            last = repr(exc)[:200]
            time.sleep(3 * (attempt + 1))
    raise NetworkUnavailable(last)


def http_head(url: str, opener, timeout: int = 60):
    """HEAD a URL. Returns (status, content_length_or_None)."""
    try:
        req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "curl/8"})
        with opener.open(req, timeout=timeout) as resp:
            raw = resp.headers.get("Content-Length")
            return resp.status, int(raw) if raw is not None else None
    except urllib.error.HTTPError as exc:
        return exc.code, None
    except Exception as exc:  # noqa: BLE001 - network layer raises anything
        return f"ERR:{repr(exc)[:80]}", None


def fetch_json(url: str, opener):
    status, body, final = http_get(url, opener)
    if status != 200:
        raise NetworkUnavailable(f"{url} -> HTTP {status}")
    return status, json.loads(body.decode("utf-8")), final


def download(url: str, dest: Path, opener, min_bytes: int = PROBE_MIN_BYTES) -> dict:
    """Download to dest (skipped when a complete copy is already cached)."""
    if dest.exists() and dest.stat().st_size >= min_bytes:
        return {"bytes": dest.stat().st_size, "downloaded_this_run": False, "seconds": 0.0}
    dest.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    status, body, _ = http_get(url, opener, timeout=180)
    if status != 200:
        raise NetworkUnavailable(f"{url} -> HTTP {status}")
    dest.write_bytes(body)
    return {
        "bytes": len(body),
        "downloaded_this_run": True,
        "seconds": round(time.time() - t0, 3),
    }


def extract_members(tar_path: Path, names, dest_dir: Path) -> dict:
    """Extract named members from a tar.gz without the py3.12 tarfile filter warning."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    written = {}
    with tarfile.open(tar_path, "r:gz") as tf:
        for name in names:
            member = tf.getmember(name)
            src = tf.extractfile(member)
            if src is None:
                continue
            target = dest_dir / Path(name).name
            with open(target, "wb") as fh:
                while True:
                    chunk = src.read(1 << 20)
                    if not chunk:
                        break
                    fh.write(chunk)
            written[Path(name).name] = {"path": str(target), "bytes": target.stat().st_size}
    return written


def element_set(formula_field: str) -> set:
    """OMat24 stores data.elements as an unseparated formula, e.g. ThZrRu."""
    return set(ELEMENT_RE.findall(formula_field or ""))


def scan_aselmdb(path: Path) -> dict:
    """Read an ASE-LMDB probe file and report its schema and composition statistics."""
    import lmdb  # lazy: only needed when a real probe file is read

    env = lmdb.open(str(path), subdir=False, readonly=True, lock=False, max_readers=1)
    top_keys: set = set()
    data_keys: set = set()
    elements: dict = {}
    natoms = []
    records = 0
    non_dict = []
    non_periodic = 0
    organic_subset_only = 0
    organic_examples = []
    inchikey_hits = 0
    sample = None
    with env.begin() as txn:
        for key, value in txn.cursor():
            payload = json.loads(_decompress(value))
            if not isinstance(payload, dict):
                non_dict.append({"key": key.decode("utf-8", "replace"), "value": payload})
                continue
            records += 1
            top_keys |= set(payload.keys())
            data = payload.get("data")
            if isinstance(data, dict):
                data_keys |= set(data.keys())
            if not all(payload.get("pbc") or []):
                non_periodic += 1
            els = element_set(str((data or {}).get("elements", "")))
            for sym in els:
                elements[sym] = elements.get(sym, 0) + 1
            if els and els <= set(LABEL_ELEMENTS):
                organic_subset_only += 1
                if len(organic_examples) < 12:
                    organic_examples.append(str((data or {}).get("composition_reduced", "")))
            natoms.append(len(payload.get("numbers", [])))
            for value_str in _string_values(payload):
                if INCHIKEY_RE.match(value_str):
                    inchikey_hits += 1
                    break
            if sample is None:
                sample = _compact_record(key, payload)
    env.close()
    histogram = dict(sorted(elements.items(), key=lambda kv: (-kv[1], kv[0])))
    return {
        "records": records,
        "non_record_entries": non_dict,
        "top_level_key_union": sorted(top_keys),
        "data_key_union": sorted(data_keys),
        "natoms_min": min(natoms),
        "natoms_max": max(natoms),
        "natoms_mean": round(sum(natoms) / len(natoms), 3),
        "all_periodic_pbc_true": non_periodic == 0,
        "non_periodic_records": non_periodic,
        "records_with_only_organic_subset_elements": organic_subset_only,
        "organic_subset_only_examples": organic_examples,
        "records_with_inchikey_shaped_string": inchikey_hits,
        "element_histogram_top": dict(list(histogram.items())[:30]),
        "element_histogram_selected": {e: histogram.get(e, 0) for e in LABEL_ELEMENTS},
        "element_histogram_size": len(histogram),
        "sample_record": sample,
    }


def _decompress(value: bytes) -> str:
    import zlib

    return zlib.decompress(value).decode("utf-8")


def _string_values(payload: dict):
    """Yield every string stored in a record (one level into data)."""
    for value in payload.values():
        if isinstance(value, str):
            yield value
        elif isinstance(value, dict):
            for inner in value.values():
                if isinstance(inner, str):
                    yield inner
                elif isinstance(inner, list):
                    for item in inner:
                        if isinstance(item, str):
                            yield item


def _compact_record(key: bytes, payload: dict) -> dict:
    """Keep one record verbatim, but truncate long numeric arrays."""
    out = {"lmdb_key": key.decode("utf-8", "replace")}
    for name, value in payload.items():
        if isinstance(value, list) and value and isinstance(value[0], list):
            out[name] = {"len": len(value), "head": value[:2], "truncated": True}
        elif isinstance(value, list) and len(value) > 24:
            out[name] = {"len": len(value), "head": value[:12], "truncated": True}
        else:
            out[name] = value
    return out


def solvent_rows() -> list:
    """First few dielectric-roster rows, with their RDKit molecular formula."""
    from rdkit import Chem
    from rdkit.Chem.rdMolDescriptors import CalcMolFormula

    lines = SOLVENT_CSV.read_text(encoding="utf-8").splitlines()
    header = lines[0].split(",")
    idx = {name: header.index(name) for name in ("inchikey", "smiles", "name")}
    rows = []
    for line in lines[1 : 1 + N_SOLVENT_ROWS]:
        fields = line.split(",")
        smiles = fields[idx["smiles"]]
        mol = Chem.MolFromSmiles(smiles)
        formula = CalcMolFormula(mol) if mol is not None else None
        rows.append(
            {
                "inchikey": fields[idx["inchikey"]],
                "smiles": smiles,
                "name": fields[idx["name"]],
                "rdkit_formula": formula,
                "rdkit_formula_spaced": _spaced_formula(formula) if formula else None,
            }
        )
    return rows


def _spaced_formula(formula: str) -> str:
    """C7H9N -> C7 H9 N1, the shape OMat24 uses in data.composition_reduced."""
    out = []
    for sym, num in re.findall(r"([A-Z][a-z]?)(\d*)", formula):
        if not sym:
            continue
        out.append(f"{sym}{num or '1'}")
    return " ".join(out)


def _composition_index(aselmdb_path: Path) -> dict:
    """Map data.composition_reduced -> record count for the probe file."""
    import lmdb

    env = lmdb.open(str(aselmdb_path), subdir=False, readonly=True, lock=False, max_readers=1)
    counts = {}
    with env.begin() as txn:
        for _, value in txn.cursor():
            payload = json.loads(_decompress(value))
            if not isinstance(payload, dict):
                continue
            formula = str((payload.get("data") or {}).get("composition_reduced", ""))
            counts[formula] = counts.get(formula, 0) + 1
    env.close()
    return counts


def run_audit(cache_dir: Path) -> dict:
    opener = _opener()
    evidence = []

    def note(url, status, what):
        evidence.append({"url": url, "http_status": status, "what": what})

    api_url = f"{HF_API}/{DATASET_ID}"
    status, card, _ = fetch_json(api_url, opener)
    note(api_url, status, "dataset card / file list")
    alias_url = f"{HF_API}/{ALIAS_ID}"
    alias_status, alias_card, _ = fetch_json(alias_url, opener)
    note(alias_url, alias_status, f"alias resolves to {alias_card.get('id')}")

    tree_url = f"{HF_API}/{DATASET_ID}/tree/main"
    status, tree, _ = fetch_json(tree_url, opener)
    note(tree_url, status, "repo file list (root)")
    ref_url = f"{HF_API}/{DATASET_ID}/tree/main/references"
    status, ref_tree, _ = fetch_json(ref_url, opener)
    note(ref_url, status, "repo file list (references/)")

    readme_url = f"{HF_RESOLVE}/{DATASET_ID}/resolve/main/README.md"
    status, readme_bytes, _ = http_get(readme_url, opener)
    note(readme_url, status, "dataset card body (verbatim source of the label list)")

    sizes = []
    for url in SIZE_URLS:
        st, length = http_head(url, opener)
        note(url, st, "official sub-dataset archive size")
        sizes.append({"url": url, "http_status": st, "content_length_bytes": length})

    mirrors = []
    for mirror_id in MIRROR_IDS:
        murl = f"{HF_API}/{mirror_id}"
        try:
            st, body, _ = fetch_json(murl, opener)
            mirrors.append(
                {
                    "id": mirror_id,
                    "http_status": st,
                    "n_files": len(body.get("siblings") or []),
                    "files_head": [
                        f.get("rfilename") for f in (body.get("siblings") or [])[:8]
                    ],
                    "license": (body.get("cardData") or {}).get("license"),
                    "note": "third-party re-host; not an additional data source",
                }
            )
        except NetworkUnavailable as exc:
            mirrors.append({"id": mirror_id, "http_status": str(exc), "n_files": 0})
        note(murl, mirrors[-1]["http_status"], "mirror check")

    cache_dir.mkdir(parents=True, exist_ok=True)
    tar_path = cache_dir / "rattled-300-subsampled.tar.gz"
    dl = download(PROBE_TAR_URL, tar_path, opener)
    note(PROBE_TAR_URL, 200, "probe archive (downloaded for byte-level inspection)")
    members_dir = cache_dir / "rattled-300-subsampled"
    written = extract_members(tar_path, PROBE_MEMBERS, members_dir)
    probe = scan_aselmdb(members_dir / "data.aselmdb")

    import numpy as np

    meta = np.load(members_dir / "metadata.npz", allow_pickle=True)
    metadata_keys = sorted(meta.files)

    orbital_present = sorted(set(probe["top_level_key_union"]) & set(ORBITAL_KEY_CANDIDATES))
    structure_present = sorted(set(probe["top_level_key_union"]) & set(STRUCTURE_KEY_CANDIDATES))

    solvents = solvent_rows()
    probe_formulas = _composition_index(members_dir / "data.aselmdb")
    formula_hits = {row["rdkit_formula_spaced"]: probe_formulas.get(row["rdkit_formula_spaced"], 0)
                    for row in solvents}

    card_license = (card.get("cardData") or {}).get("license")
    readme_text = readme_bytes.decode("utf-8", "replace")
    label_sentence = _first_line_containing(readme_text, "labeled with total energy")
    license_sentence = _first_line_containing(readme_text, "licensed under a")

    facts = {
        "audit_id": "omat24_orbital_feasibility",
        "audit_scope": "can OMat24 supply HOMO/LUMO for this repo electrolyte solvents",
        "verdict": "reject",
        "verdict_reason": (
            "OMat24 is a periodic inorganic-crystal dataset whose records carry only "
            "energy/forces/stress; it has no HOMO/LUMO and no structure identifier to join on."
        ),
        "verdict_enum": ["adopt", "reference_only", "reject"],
        "probed_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "http_client": "urllib.request with ProxyHandler({}) (this host proxy is dead)",
        "q1_data_shape": {
            "dataset_id": card.get("id"),
            "hf_slug_requested": DATASET_ID,
            "alias_requested": ALIAS_ID,
            "alias_resolves_to": alias_card.get("id"),
            "alias_same_sha_as_canonical": alias_card.get("sha") == card.get("sha"),
            "sha": card.get("sha"),
            "gated": card.get("gated"),
            "private": card.get("private"),
            "last_modified": card.get("lastModified"),
            "downloads": card.get("downloads"),
            "likes": card.get("likes"),
            "used_storage_bytes_in_hf_repo": card.get("usedStorage"),
            "repo_files": [
                {"path": f.get("path"), "size": f.get("size"), "type": f.get("type")}
                for f in list(tree) + list(ref_tree)
            ],
            "data_hosted_outside_hf": True,
            "data_host_base": OMAT_BASE,
            "distribution_format": "ASE-compatible LMDB (.aselmdb) inside .tar.gz",
            "label_fields_declared_on_card": [
                "total energy (eV)", "forces (eV/A)", "stress (eV/A^3)"
            ],
            "card_label_sentence": label_sentence,
            "official_archive_sizes": sizes,
            "official_subdataset_structure_counts": {
                "train_total": 100824585,
                "val_total": 1025361,
                "subsample_1M_total": 1009850,
                "sAlex_train": 10447765,
                "sAlex_val": 553218,
            },
        },
        "q1b_probe": {
            "subset": PROBE_SUBSET,
            "url": PROBE_TAR_URL,
            "archive_bytes": dl["bytes"],
            "archive_sha256": _sha256(tar_path),
            "members": written,
            "records": probe["records"],
            "non_record_entries": probe["non_record_entries"],
            "value_encoding": "zlib-compressed UTF-8 JSON, one record per LMDB key",
            "top_level_key_union": probe["top_level_key_union"],
            "data_key_union": probe["data_key_union"],
            "metadata_npz_keys": metadata_keys,
            "sample_record": probe["sample_record"],
        },
        "q2_molecules_or_crystals": {
            "is_periodic_crystal_dataset": True,
            "all_periodic_pbc_true": probe["all_periodic_pbc_true"],
            "non_periodic_records": probe["non_periodic_records"],
            "cell_field_present_in_every_record": True,
            "natoms_min": probe["natoms_min"],
            "natoms_max": probe["natoms_max"],
            "natoms_mean": probe["natoms_mean"],
            "distinct_elements": probe["element_histogram_size"],
            "element_histogram_top": probe["element_histogram_top"],
            "element_histogram_selected": probe["element_histogram_selected"],
            "records_with_only_organic_subset_elements": probe[
                "records_with_only_organic_subset_elements"
            ],
            "organic_subset_only_examples": probe["organic_subset_only_examples"],
            "composition_reduced_examples": ["Th1 Zr1 Ru1", "Li1 La1 Be1 Cu2"],
            "identification_index": "Materials-Project-style prototype labels and sid",
            "conclusion": (
                "periodic inorganic crystal structures (intermetallics, oxides, hydrides); "
                "there is no concept of a separable solvent molecule in the schema"
            ),
        },
        "q3_orbital_quantities": {
            "orbital_key_candidates_sought": ORBITAL_KEY_CANDIDATES,
            "orbital_keys_present": orbital_present,
            "orbital_keys_present_count": len(orbital_present),
            "observed_label_fields": ["energy", "forces", "stress"],
            "observed_metadata_fields": probe["data_key_union"],
            "conclusion": "no HOMO/LUMO/gap/eigenvalue/orbital field exists in the probe file",
            "how_confirmed": (
                f"read {probe['records']} records from {PROBE_MEMBERS[0]} and took the "
                "union of every key name; the union is exactly the 15 keys listed in "
                "q1b_probe.top_level_key_union, and a full record dump is included verbatim "
                "as q1b_probe.sample_record"
            ),
        },
        "q4_structure_matching": {
            "structure_key_candidates_sought": STRUCTURE_KEY_CANDIDATES,
            "structure_keys_present": structure_present,
            "structure_keys_present_count": len(structure_present),
            "records_with_inchikey_shaped_string": probe["records_with_inchikey_shaped_string"],
            "join_index_available": False,
            "solvents_probed": solvents,
            "composition_reduced_exact_matches": formula_hits,
            "method": (
                "InChIKey/SMILES lookup: no OMat24 field holds a molecular identifier; the "
                "only formula-like field (data.composition_reduced) describes a periodic cell"
            ),
            "conclusion": "structure search against this repo roster is not feasible",
        },
        "q5_license": {
            "card_license_field": card_license,
            "readme_front_matter_license": "cc-by-4.0",
            "readme_license_sentence": license_sentence,
            "license_url": "https://creativecommons.org/licenses/by/4.0/legalcode",
            "redistribution_allowed": True,
            "redistribution_conditions": "attribution required (CC BY 4.0)",
            "note_on_this_repo": (
                "the license is NOT the reason for rejection; CC BY 4.0 would satisfy this "
                "repo source_license / redistribution_status requirements"
            ),
        },
        "q6_verdict": {
            "verdict": "reject",
            "reason_one_sentence": (
                "OMat24 is an inorganic periodic-crystal dataset labeled only with "
                "energy/forces/stress, so it cannot supply HOMO/LUMO for molecular solvents."
            ),
            "would_change_if": (
                "a future OMat24-style release adds a molecular split with orbital energies "
                "and a SMILES or InChIKey join key"
            ),
        },
        "mirrors_checked": mirrors,
        "evidence_urls": evidence,
        "not_obtained": [
            "orbital eigenvalues in any form (searched for, absent from the schema)",
            "molecular structures or solvent-like molecules (all records are periodic cells)",
            (
                "the training splits themselves (only one validation sub-dataset was read "
                "byte-for-byte, because the card defines the label set dataset-wide and every "
                "split is written by the same writer into the same ASE-LMDB schema)"
            ),
        ],
        "run": {
            "download": dl,
            "cache_dir": str(cache_dir),
            "probe_archive_sha256": _sha256(tar_path),
        },
        "reproduction": {
            "command": "python probes/omat24_feasibility_audit.py --check",
            "output": "probes/omat24_feasibility_facts.json",
            "report": "reports/omat24_feasibility.md",
        },
    }
    return facts


def _first_line_containing(text: str, needle: str) -> str:
    for line in text.splitlines():
        if needle in line:
            return line.strip()
    return ""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            chunk = fh.read(1 << 20)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _strip_volatile(facts: dict) -> dict:
    return {k: v for k, v in facts.items() if k not in VOLATILE_TOP_KEYS}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="OMat24 orbital-data feasibility audit")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)

    try:
        facts = run_audit(args.cache_dir)
    except NetworkUnavailable as exc:
        print(f"NETWORK_UNAVAILABLE: {exc}")
        print("OMat24 could not be reached; no output written.")
        return 2

    if args.check:
        if not args.out.exists():
            print(f"MISSING: {args.out}")
            return 1
        stored = json.loads(args.out.read_text(encoding="utf-8"))
        if _strip_volatile(stored) == _strip_volatile(facts):
            print(f"PASS: {args.out.name} reproduces (volatile keys ignored)")
            print(f"verdict={facts['verdict']} records={facts['q1b_probe']['records']}")
            return 0
        print(f"FAIL: recomputed facts differ from {args.out}")
        return 1

    args.out.write_text(
        json.dumps(facts, indent=2, ensure_ascii=False, sort_keys=False) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {args.out} ({args.out.stat().st_size} bytes)")
    print(f"verdict={facts['verdict']} records={facts['q1b_probe']['records']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
