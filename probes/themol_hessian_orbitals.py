"""Harvest THEMol Hessian geometries into a third GFN2-xTB orbital source (W17-14).

Why this arm exists
-------------------
Week 17's orbital channel has exactly two sources: ``data/raw/batt/Batt-P30K.h5``
(wB97X-V/def2-TZVPPD/SMD(eps=18.5), 29,519 molecules) and the W17-12 PubChemQC
layer (B3LYP/6-31G*//PM6, CC BY 4.0).  The author asked whether ByteDance-Seed's
THEMol -- 2,695,304 Hessian molecules whose dataset card advertises
``electrolytes`` and ``ionic liquids`` -- could supply a third one.

THEMol itself stores **no orbital quantity**.  Each HDF5 group carries
``atomic_numbers``, ``coords`` and ``hessian`` only; there is no eigenvalue, no
gap, no IP/EA column anywhere in the five subsets.  What THEMol does store is a
DFT-relaxed geometry for every molecule, and those geometries are reachable by
HTTP range reads: ``h5py`` is handed a seekable file-like object that fetches
only the byte windows it needs, so one molecule costs ~2.9 MB instead of the
4.79 GB shard it lives in.  This probe therefore does the only thing THEMol
supports: read the geometry, run exactly one GFN2-xTB single point, report
HOMO/LUMO/gap.

What this probe is not
----------------------
GFN2-xTB is a semi-empirical tight-binding Hamiltonian, not DFT, and the level
of theory does not match either existing source.  Nothing produced here may be
mixed into the orbital channel without the cross-level calibration performed by
``probes/build_themol_orbital_layer.py``; the raw table this probe writes is
evidence, not delivery data.

Licence and provenance
----------------------
THEMol data is **CC BY-NC 4.0** (code Apache-2.0).  The geometry is the
derivative-work input, so the harvested table is non-commercial and is written
under ``data/raw/`` -- a directory the repository deliberately ignores.  Only
aggregate, calibrated numbers may enter ``data/processed/``.

Determinism
-----------
Every xTB call goes through ``electrolyte_ml.xtb_runner``, which pins
``OMP_NUM_THREADS=1`` and clears the four thread variables; each molecule gets a
private scratch directory so a leftover ``xtbrestart`` cannot become an SCF
restart.  The geometry actually used is hashed into ``geometry_sha256``, so a
re-run that disagrees is detectable without trusting the record index.
"""

from __future__ import annotations

import argparse
import contextlib
import csv
import hashlib
import io
import json
import os
import re
import shutil
import sys
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from electrolyte_ml.xtb_runner import reported_omp_threads, run_xtb_subprocess

HF_MIRROR_BASE = "https://hf-mirror.com/datasets/ByteDance-Seed/THEMol/resolve/main/"
HESSIAN_INDEX_OBJECT = "Hessian/hessian_dataset.csv"
DEFAULT_INDEX_PATH = REPOSITORY_ROOT / "data" / "raw" / "themol" / "themol_registry_index.csv"
DEFAULT_ROSTER_PATH = REPOSITORY_ROOT / "data" / "dielectric_v04.csv"
DEFAULT_OUTPUT_PATH = REPOSITORY_ROOT / "data" / "raw" / "themol" / "themol_orbital_harvest.csv"
DEFAULT_SCRATCH_ROOT = REPOSITORY_ROOT / "data" / "raw" / "themol" / "scratch"

INDEX_FIELDS = ("canonical_smiles", "uuid", "h5_file")
HARVEST_FIELDS = (
    "name",
    "inchikey",
    "smiles",
    "canonical_smiles",
    "roster_value",
    "roster_source",
    "themol_uuid",
    "themol_h5_file",
    "natoms",
    "geometry_sha256",
    "xtb_version",
    "xtb_omp_threads",
    "homo_eV",
    "lumo_eV",
    "gap_eV",
    "returncode",
    "fetched_bytes",
    "elapsed_seconds",
    "status",
)

HOMO_PATTERN = re.compile(r"(-?\d+\.\d+)\s*\(HOMO\)")
LUMO_PATTERN = re.compile(r"(-?\d+\.\d+)\s*\(LUMO\)")
VERSION_PATTERN = re.compile(r"xtb version\s+(\S+)")


def canonical_smiles(value: str | None) -> str | None:
    """RDKit canonical SMILES, or ``None`` when the input cannot be parsed."""

    if not value:
        return None
    from rdkit import Chem, RDLogger

    RDLogger.DisableLog("rdApp.*")
    molecule = Chem.MolFromSmiles(value)
    if molecule is None:
        return None
    return Chem.MolToSmiles(molecule)


def load_registry_index(path: Path) -> dict[str, list[tuple[str, str]]]:
    """``canonical_smiles -> [(uuid, h5_file), ...]`` from the THEMol index."""

    index: dict[str, list[tuple[str, str]]] = {}
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        missing = [field for field in INDEX_FIELDS if field not in (reader.fieldnames or ())]
        if missing:
            raise ValueError(f"{path} is missing columns: {missing}")
        for row in reader:
            key = row["canonical_smiles"]
            index.setdefault(key, []).append((row["uuid"], row["h5_file"]))
    return index


def iter_roster_targets(
    roster_paths: Sequence[Path],
    index: dict[str, list[tuple[str, str]]],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Join one or more roster CSVs against the THEMol index on canonical SMILES.

    Returns the matched targets in roster order plus the counts that make the
    join auditable (how many rows were unparsable, how many are not in THEMol).
    A molecule named by two rosters is kept once: the first roster wins and the
    repeat is counted as a duplicate key.
    """

    targets: list[dict[str, Any]] = []
    counters = {"rows": 0, "unparsable": 0, "uncovered": 0, "matched": 0, "duplicate_keys": 0}
    seen: set[str] = set()
    for roster_path in roster_paths:
        with roster_path.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                counters["rows"] += 1
                canonical = canonical_smiles(row.get("smiles"))
                if canonical is None:
                    counters["unparsable"] += 1
                    continue
                hits = index.get(canonical)
                if not hits:
                    counters["uncovered"] += 1
                    continue
                if canonical in seen:
                    counters["duplicate_keys"] += 1
                    continue
                seen.add(canonical)
                counters["matched"] += 1
                targets.append(
                    {
                        "name": row.get("name") or "",
                        "inchikey": row.get("inchikey") or "",
                        "smiles": row.get("smiles") or "",
                        "canonical_smiles": canonical,
                        "roster_value": row.get("dielectric") or row.get("roster_value") or "",
                        "roster_source": roster_path.name,
                        "themol_uuid": hits[0][0],
                        "themol_h5_file": hits[0][1],
                    }
                )
    return targets, counters


class HttpRangeFile(io.RawIOBase):
    """A seekable, read-only file view over HTTP range requests.

    ``h5py`` needs ``seek``/``tell``/``readinto``.  Every byte window is cached
    per instance, so the HDF5 superblock walk and the dataset read share one
    fetch, and ``fetched_bytes`` reports the true network cost of a molecule
    rather than the shard size.
    """

    def __init__(self, url: str, session: Any, timeout: float = 60.0) -> None:
        self.url = url
        self._session = session
        self._timeout = timeout
        self._cache: dict[tuple[int, int], bytes] = {}
        self._pos = 0
        self._fetches = 0
        self.fetched_bytes = 0
        probe = session.get(url, headers={"Range": "bytes=0-0"}, timeout=timeout)
        content_range = probe.headers.get("Content-Range")
        if content_range:
            self.size = int(content_range.split("/")[-1])
        else:
            self.size = int(probe.headers.get("Content-Length") or 0)

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def writable(self) -> bool:
        return False

    def tell(self) -> int:
        return self._pos

    def seek(self, offset: int, whence: int = 0) -> int:
        if whence == 0:
            self._pos = offset
        elif whence == 1:
            self._pos += offset
        else:
            self._pos = self.size + offset
        return self._pos

    def read(self, size: int = -1) -> bytes:
        if size is None or size < 0:
            size = self.size - self._pos
        if size <= 0:
            return b""
        start = self._pos
        end = min(self._pos + size, self.size) - 1
        if end < start:
            return b""
        key = (start, end)
        payload = self._cache.get(key)
        if payload is None:
            response = self._session.get(
                self.url,
                headers={"Range": f"bytes={start}-{end}"},
                timeout=self._timeout,
            )
            response.raise_for_status()
            payload = response.content
            self._cache[key] = payload
            self._fetches += 1
            self.fetched_bytes += len(payload)
        self._pos += len(payload)
        return payload

    def readinto(self, buffer: Any) -> int:
        data = self.read(len(buffer))
        buffer[: len(data)] = data
        return len(data)


def shard_targets(
    targets: Sequence[dict[str, Any]],
    *,
    shard: int,
    nshards: int,
) -> list[dict[str, Any]]:
    """Split by H5 shard file so each worker owns disjoint network connections.

    Molecules are grouped by their ``hessian_N.h5`` container and whole groups
    are dealt round-robin; a target list cut in roster order would instead have
    every worker open all 47 shards.
    """

    if not 0 <= shard < nshards:
        raise ValueError(f"shard must be in [0, {nshards}); got {shard}")
    groups: dict[str, list[dict[str, Any]]] = {}
    for target in targets:
        groups.setdefault(target["themol_h5_file"], []).append(target)
    shard_files = sorted(groups)
    selected: list[dict[str, Any]] = []
    for position, name in enumerate(shard_files):
        if position % nshards == shard:
            selected.extend(groups[name])
    return selected


def write_xyz(path: Path, atomic_numbers: Any, coordinates: Any, comment: str) -> str:
    """Write a plain XYZ file and return the sha256 of its exact bytes."""

    lines = [str(len(atomic_numbers)), comment]
    for number, xyz in zip(atomic_numbers, coordinates, strict=True):
        lines.append(f"{int(number):<3d} {xyz[0]:16.8f} {xyz[1]:16.8f} {xyz[2]:16.8f}")
    text = "\n".join(lines) + "\n"
    payload = text.encode("utf-8")
    path.write_bytes(payload)
    return hashlib.sha256(payload).hexdigest()


def parse_orbitals(text: str) -> tuple[float | None, float | None]:
    """Pull the HOMO and LUMO eigenvalues out of an xTB single-point log."""

    homo: float | None = None
    lumo: float | None = None
    for line in text.splitlines():
        match = HOMO_PATTERN.search(line)
        if match:
            homo = float(match.group(1))
        match = LUMO_PATTERN.search(line)
        if match:
            lumo = float(match.group(1))
    return homo, lumo


def harvest(
    *,
    targets: Sequence[dict[str, Any]],
    output_path: Path,
    xtb_executable: Path,
    scratch_root: Path,
    timeout_seconds: int,
    keep_scratch: bool,
    log: Any = print,
) -> dict[str, Any]:
    """Run one GFN2-xTB single point per target and stream rows to ``output_path``."""

    import h5py
    import requests

    session = requests.Session()
    session.trust_env = False
    session.headers.update({"User-Agent": "Mozilla/5.0", "Accept-Encoding": "identity"})

    output_path.parent.mkdir(parents=True, exist_ok=True)
    scratch_root.mkdir(parents=True, exist_ok=True)
    grouped: dict[str, list[dict[str, Any]]] = {}
    for target in targets:
        grouped.setdefault(target["themol_h5_file"], []).append(target)

    started = time.time()
    rows_written = 0
    failed = 0
    total_fetched = 0
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=HARVEST_FIELDS, lineterminator="\n")
        writer.writeheader()
        for h5_name in sorted(grouped):
            url = HF_MIRROR_BASE + "Hessian/" + h5_name
            remote = HttpRangeFile(url, session)
            row_fetched = 0
            try:
                container = h5py.File(remote, "r")
            except Exception as error:  # noqa: BLE001 - one bad shard must not abort the run
                log(f"open failed {h5_name}: {error!r}")
                for target in grouped[h5_name]:
                    writer.writerow(
                        {**target, "status": f"h5_open_failed:{type(error).__name__}"}
                    )
                    failed += 1
                handle.flush()
                continue
            for target in grouped[h5_name]:
                record: dict[str, Any] = {
                    key: target[key]
                    for key in (
                        "name",
                        "inchikey",
                        "smiles",
                        "canonical_smiles",
                        "roster_value",
                        "roster_source",
                        "themol_uuid",
                        "themol_h5_file",
                    )
                }
                before = remote.fetched_bytes
                molecule_started = time.time()
                try:
                    group = container[target["themol_uuid"]]
                    atomic_numbers = group["atomic_numbers"][:].ravel()
                    coordinates = group["coords"][:]
                    workdir = scratch_root / target["themol_uuid"][:12]
                    if workdir.exists() and not keep_scratch:
                        shutil.rmtree(workdir)
                    workdir.mkdir(parents=True, exist_ok=True)
                    xyz_path = workdir / "mol.xyz"
                    digest = write_xyz(
                        xyz_path, atomic_numbers, coordinates, target["themol_uuid"]
                    )
                    completed = run_xtb_subprocess(
                        xtb_executable,
                        ["mol.xyz", "--gfn", "2", "--sp"],
                        cwd=workdir,
                        timeout_seconds=timeout_seconds,
                    )
                    text = completed.stdout.decode("utf-8", "replace") + completed.stderr.decode(
                        "utf-8", "replace"
                    )
                    homo, lumo = parse_orbitals(text)
                    version = VERSION_PATTERN.search(text)
                    record.update(
                        {
                            "natoms": len(atomic_numbers),
                            "geometry_sha256": digest,
                            "xtb_version": version.group(1) if version else "",
                            "xtb_omp_threads": reported_omp_threads(text),
                            "homo_eV": homo,
                            "lumo_eV": lumo,
                            "gap_eV": (
                                round(lumo - homo, 6)
                                if homo is not None and lumo is not None
                                else None
                            ),
                            "returncode": completed.returncode,
                            "status": "ok" if homo is not None and lumo is not None else "no_orbitals",
                        }
                    )
                    if not keep_scratch:
                        shutil.rmtree(workdir, ignore_errors=True)
                except Exception as error:  # noqa: BLE001 - record the failure, keep going
                    record["status"] = f"error:{type(error).__name__}"
                    record["returncode"] = None
                    record["natoms"] = None
                    failed += 1
                    log(f"  failed {target['name']!r}: {error!r}")
                record["fetched_bytes"] = remote.fetched_bytes - before
                record["elapsed_seconds"] = round(time.time() - molecule_started, 3)
                record.setdefault("homo_eV", None)
                record.setdefault("lumo_eV", None)
                record.setdefault("gap_eV", None)
                record.setdefault("returncode", None)
                record.setdefault("natoms", None)
                record.setdefault("geometry_sha256", "")
                record.setdefault("xtb_version", "")
                record.setdefault("xtb_omp_threads", None)
                writer.writerow(record)
                handle.flush()
                rows_written += 1
                row_fetched += record["fetched_bytes"]
                if rows_written % 10 == 0 or rows_written <= 2:
                    log(
                        f"  [{rows_written}/{len(targets)}] {target['name']}: "
                        f"HOMO={record['homo_eV']} LUMO={record['lumo_eV']} "
                        f"rc={record['returncode']} "
                        f"({(time.time() - started) / 60:.1f} min, "
                        f"shard cache {row_fetched / 1e6:.1f} MB)"
                    )
            total_fetched += remote.fetched_bytes
            with contextlib.suppress(Exception):
                container.close()
            log(f"shard {h5_name} done ({remote.fetched_bytes / 1e6:.1f} MB transferred)")

    return {
        "rows": rows_written,
        "failed": failed,
        "targets": len(targets),
        "fetched_bytes": total_fetched,
        "elapsed_seconds": round(time.time() - started, 3),
    }


def rebuild_registry_index(
    *,
    registry_path: Path,
    output_path: Path,
    hf_base: str = HF_MIRROR_BASE,
    log: Any = print,
) -> dict[str, Any]:
    """Stream the 1.47 GB THEMol Hessian index and keep rows our registry knows.

    This is the provenance path for ``data/raw/themol/themol_registry_index.csv``.
    It re-downloads the object rather than trusting the copy on disk, so the
    committed coverage numbers can be regenerated from the published dataset.
    """

    import requests
    from rdkit import Chem, RDLogger

    RDLogger.DisableLog("rdApp.*")
    wanted: dict[str, str] = {}
    with registry_path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            molecule = Chem.MolFromSmiles(row.get("smiles") or "")
            if molecule is None:
                continue
            wanted[Chem.MolToSmiles(molecule)] = row["smiles"]

    session = requests.Session()
    session.trust_env = False
    url = hf_base + HESSIAN_INDEX_OBJECT
    kept: list[tuple[str, str, str]] = []
    scanned = 0
    with session.get(url, stream=True, timeout=120) as response:
        response.raise_for_status()
        text_stream = io.TextIOWrapper(response.raw, encoding="utf-8", errors="replace")
        reader = csv.DictReader(text_stream)
        columns = reader.fieldnames or []
        for name in ("mapped_nonisomeric_smiles", "uuid", "h5_file"):
            if name not in columns:
                raise ValueError(f"THEMol index is missing column {name!r}; got {columns}")
        for row in reader:
            scanned += 1
            molecule = Chem.MolFromSmiles(row["mapped_nonisomeric_smiles"] or "")
            if molecule is None:
                continue
            key = Chem.MolToSmiles(molecule)
            if key in wanted:
                kept.append((key, row["uuid"], row["h5_file"]))
            if scanned % 250_000 == 0:
                log(f"  scanned {scanned:,} rows, {len(kept)} matched")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    unique = sorted(set(kept))
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(INDEX_FIELDS)
        writer.writerows(unique)
    return {"scanned": scanned, "matched": len(unique), "path": str(output_path)}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--index", type=Path, default=DEFAULT_INDEX_PATH)
    parser.add_argument("--roster", type=Path, nargs="+", default=[DEFAULT_ROSTER_PATH])
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--xtb", type=Path, default=None, help="xTB executable override")
    parser.add_argument("--scratch-root", type=Path, default=DEFAULT_SCRATCH_ROOT)
    parser.add_argument("--timeout-seconds", type=int, default=900)
    parser.add_argument("--keep-scratch", action="store_true")
    parser.add_argument("--shard", type=int, default=0)
    parser.add_argument("--nshards", type=int, default=1)
    parser.add_argument("--limit", type=int, default=None, help="stop after N targets (timing)")
    parser.add_argument(
        "--rebuild-index",
        action="store_true",
        help="re-stream the published THEMol index instead of harvesting",
    )
    parser.add_argument(
        "--registry",
        type=Path,
        default=REPOSITORY_ROOT / "data" / "processed" / "four_core_key_registry.csv",
    )
    return parser


def resolve_xtb(explicit: Path | None) -> Path:
    candidates: list[Path] = []
    if explicit is not None:
        candidates.append(explicit)
    if os.environ.get("XTB_EXE"):
        candidates.append(Path(os.environ["XTB_EXE"]))
    discovered = shutil.which("xtb")
    if discovered:
        candidates.append(Path(discovered))
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        candidates.append(
            Path(local_app_data)
            / "electrolyte-ml"
            / "tools"
            / "xtb-6.7.1"
            / "extracted"
            / "xtb-6.7.1"
            / "bin"
            / "xtb.exe"
        )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise FileNotFoundError("xTB executable not found; pass --xtb or set XTB_EXE")


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.rebuild_index:
        report = rebuild_registry_index(registry_path=args.registry, output_path=args.index)
        print(json.dumps(report, indent=2))
        return 0

    index = load_registry_index(args.index)
    targets, counters = iter_roster_targets(args.roster, index)
    selected = shard_targets(targets, shard=args.shard, nshards=args.nshards)
    if args.limit is not None:
        selected = selected[: args.limit]

    print(
        f"rosters={[path.name for path in args.roster]} rows={counters['rows']} "
        f"matched={counters['matched']} "
        f"uncovered={counters['uncovered']} unparsable={counters['unparsable']} "
        f"duplicate_keys={counters['duplicate_keys']}"
    )
    print(f"shard {args.shard}/{args.nshards}: {len(selected)} targets -> {args.out}")

    outcome = harvest(
        targets=selected,
        output_path=args.out,
        xtb_executable=resolve_xtb(args.xtb),
        scratch_root=args.scratch_root,
        timeout_seconds=args.timeout_seconds,
        keep_scratch=args.keep_scratch,
    )
    print(json.dumps({**outcome, "counters": counters, "shard": args.shard}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())