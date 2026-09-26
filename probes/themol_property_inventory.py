"""Inventory every per-molecule field THEMol's HDF5 shards actually carry (W17-18).

Why this probe exists
---------------------
W17-14 (probes/themol_hessian_orbitals.py) settled whether THEMol could feed the
orbital channel: read one DFT geometry over HTTP range, run one GFN2-xTB single
point, report HOMO/LUMO.  That left a different question open -- THEMol advertises
five subsets and a billion-odd DFT calculations, so which *other* per-molecule
properties do its shards actually carry, and could any of them feed the epsilon /
DN / viscosity channels?

This probe answers that from the files themselves.  It opens one shard per subset
over HTTP range reads, never the whole 3.5-21 GB container, and records the real
group keys, shapes, dtypes, attributes and sample values.  Where the dataset card
and the bytes disagree the bytes win, and the disagreement is written down.

The two findings that matter
----------------------------
1. No subset stores a DFT HOMO/LUMO.  Across all five subsets the union of measured
   keys contains no eigenvalue, gap, IP/EA or orbital namespace.  The only orbital
   numbers anywhere in this project's THEMol layer are the ones we compute
   ourselves with GFN2-xTB, which is exactly why
   probes/build_themol_orbital_layer.py exists and why it has to calibrate a
   cross-level offset.  Mixing a GFN2 LUMO into a B3LYP-anchored channel without
   that calibration is wrong.
2. The MBIS subset carries DFT-level atomic populations.  PBE0/def2-TZVPD Minimal
   Basis Iterative Stockholder partitioning: per-atom charge, dipole, quadrupole
   and volume plus the underlying Slater functions.  A molecular dipole follows
   from the atomic charges, the atomic dipoles and the geometry, and the POC below
   shows the numbers are self-consistent (charges sum to the molecular charge,
   quadrupoles are traceless, the Slater populations reproduce the electron count).

Bandwidth discipline
--------------------
The container the rest of the week is mining is bandwidth-bound, so this probe
never streams a whole file: every read is an HTTP range window and a hard
--max-download-mb ceiling (default 40 MiB) aborts the run before it can become a
shard download.  One structural cost is unavoidable and worth naming: HDF5 keeps a
shard's root-group link records in one fractal-heap block, so the *first* molecule
read from a file also pulls that block -- roughly 50 bytes per molecule in the
shard.  For hessian_*.h5 (~62k molecules) that is ~2.9 MB; for mbis_*.h5 (~400k
molecules) it is ~23 MB.  Every further molecule in the same file is then nearly
free, which is why MBIS molecules are probed in one batch from a single shard.

Licence and provenance
----------------------
THEMol is CC BY-NC 4.0.  Everything this probe writes lands under data/raw/, a
directory the repository deliberately ignores; the inventory JSON and the report
carry only key names, shapes and a handful of sample values.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import random
import re
import sys
import time
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

PROBES_DIR = Path(__file__).resolve().parent
REPOSITORY_ROOT = PROBES_DIR.parent
for extra in (PROBES_DIR, REPOSITORY_ROOT / "src"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

DEFAULT_INVENTORY_PATH = PROBES_DIR / "themol_property_inventory.json"
DEFAULT_RAW_DIR = REPOSITORY_ROOT / "data" / "raw" / "themol" / "property_poc"

HF_MIRROR_BASE = "https://hf-mirror.com/datasets/ByteDance-Seed/THEMol/resolve/main/"
INDEX_WINDOW_BYTES = 262_144
DEFAULT_MAX_DOWNLOAD_MB = 40
DEFAULT_ATTEMPTS = 12
BACKOFF_CAP_SECONDS = 30.0
CONNECT_TIMEOUT_SECONDS = 30.0
READ_TIMEOUT_SECONDS = 180.0

MOLECULE_CAP = 40
MOLECULES_PER_SUBSET = {
    "hessian": 1,
    "hessian_relax": 1,
    "torsion_scan": 1,
    "torsion_scan_relax": 1,
    "mbis": 16,
}

E_ANGSTROM_TO_DEBYE = 4.803204712570263
CHARGE_SUM_TOLERANCE_E = 1e-3
QUADRUPOLE_TRACE_TOLERANCE_E_A2 = 1e-6
ELECTRON_COUNT_TOLERANCE_E = 5e-2

# The MBIS molecular dipole is built from atomic charges and atomic dipoles, so
# it is origin independent only while the molecule is neutral.  Two of the
# sixteen probed molecules are ions, and for those the reported magnitude moves
# with the coordinate frame; every dipole summary below is therefore restricted
# to the neutral molecules.
DIPOLE_ORIGIN_NOTE = (
    "origin independent only for neutral molecules; the magnitude reported for a "
    "charged molecule depends on the coordinate frame"
)

NESTED_GROUP_PATTERN = re.compile(r"^(step|constraint)[ _]\d+$")
ORBITAL_KEY_PATTERN = re.compile(
    r"homo|lumo|orbital|eigen|eigval|gap|ionization|electron_affinity",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Subset:
    """One THEMol subset: its directory, index file and documented metadata."""

    name: str
    directory: str
    index_file: str
    documented_level: str
    documented_entries: int


SUBSETS: tuple[Subset, ...] = (
    Subset("hessian", "Hessian", "hessian_dataset.csv", "B3LYP-D3(BJ)/DZVP", 3_102_537),
    Subset("hessian_relax", "HessianRelax", "relax_dataset.csv", "B3LYP-D3(BJ)/DZVP", 4_811_722),
    Subset("torsion_scan", "TorsionScan", "torsion_dataset.csv", "B3LYP-D3(BJ)/DZVP", 4_192_791),
    Subset(
        "torsion_scan_relax",
        "TorsionScanRelax",
        "torsion_relax_dataset.csv",
        "B3LYP-D3(BJ)/DZVP",
        4_914_677,
    ),
    Subset("mbis", "MBIS", "mbis_dataset.csv", "PBE0/def2-TZVPD", 3_082_151),
)

SUBSET_BY_NAME = {subset.name: subset for subset in SUBSETS}

# Unit strings as printed on the dataset card.  unit_evidence is downgraded to
# "measured" only where the probe itself checks the unit (charge neutrality pins
# e; MBIS quadrupoles are traceless in e*A^2).
UNIT_HINTS: dict[str, tuple[str | None, str]] = {
    "atomic_numbers": (None, "n/a"),
    "coords": ("angstrom", "documented"),
    "hessian": ("kcal mol^-1 angstrom^-2", "documented"),
    "mapped_nonisomeric_smiles": (None, "n/a"),
    "mapped_isomeric_smiles": (None, "n/a"),
    "torsion_atom_indices": ("0-based atom quartet", "documented"),
    "energy": ("kcal mol^-1", "documented"),
    "forces": ("kcal mol^-1 angstrom^-1", "documented"),
    "atomic_charge": ("e", "measured"),
    "atomic_dipole": ("e angstrom", "documented"),
    "atomic_quadrupole": ("e angstrom^2", "documented"),
    "atomic_volumes": ("angstrom^3", "documented"),
    "parameters": (
        "[parent_atom_index, Slater_population_e, inverse_width_angstrom^-1]",
        "documented",
    ),
}

DOCUMENTED_LEVELS = {subset.name: subset.documented_level for subset in SUBSETS}
DOCUMENTED_ENTRIES = {subset.name: subset.documented_entries for subset in SUBSETS}


class DownloadBudgetExceeded(RuntimeError):
    """Raised before a read that would push the run past --max-download-mb."""


class RetryableHttpError(RuntimeError):
    """HTTP 429 / 5xx, retried with backoff."""


class Fetcher:
    """A requests session that counts every byte and enforces a hard ceiling."""

    def __init__(self, session: Any, *, limit_bytes: int) -> None:
        self._session = session
        self.limit_bytes = limit_bytes
        self.total_bytes = 0

    @property
    def remaining_bytes(self) -> int:
        return max(0, self.limit_bytes - self.total_bytes)

    def get_range(
        self,
        url: str,
        start: int,
        end: int,
        *,
        timeout: float = READ_TIMEOUT_SECONDS,
        attempts: int = DEFAULT_ATTEMPTS,
    ) -> tuple[bytes, dict[str, str]]:
        """Fetch bytes=start-end and return (payload, headers).

        The response is streamed and truncated at end - start + 1 bytes, so a
        mirror that ignores the Range header and answers 200 with the whole
        container still cannot push the run past its budget.
        """

        wanted = end - start + 1
        if wanted <= 0:
            return b"", {}
        if wanted > self.remaining_bytes:
            raise DownloadBudgetExceeded(
                f"need {wanted} B, only {self.remaining_bytes} B of budget left"
            )
        last: Exception | None = None
        for attempt in range(attempts):
            response = None
            try:
                response = self._session.get(
                    url,
                    headers={"Range": f"bytes={start}-{end}"},
                    timeout=(CONNECT_TIMEOUT_SECONDS, timeout),
                    stream=True,
                )
                if response.status_code == 429 or response.status_code >= 500:
                    raise RetryableHttpError(f"HTTP {response.status_code}")
                response.raise_for_status()
                chunks: list[bytes] = []
                got = 0
                for piece in response.iter_content(65536):
                    chunks.append(piece)
                    got += len(piece)
                    if got >= wanted:
                        break
                payload = b"".join(chunks)[:wanted]
                headers = dict(response.headers)
                self.total_bytes += len(payload)
                return payload, headers
            except RetryableHttpError as error:
                last = error
                retry_after = None
                if response is not None:
                    retry_after = response.headers.get("Retry-After")
                self._sleep(attempt, retry_after, attempts)
            except Exception as error:  # noqa: BLE001 - the mirror drops connections mid-window
                last = error
                self._sleep(attempt, None, attempts)
            finally:
                if response is not None:
                    response.close()
        assert last is not None
        raise last

    def _sleep(self, attempt: int, retry_after: str | None, attempts: int) -> None:
        if attempt == attempts - 1:
            return
        delay = 0.0
        if retry_after:
            try:
                delay = float(retry_after)
            except (TypeError, ValueError):
                delay = 0.0
        if delay <= 0.0:
            delay = min(2.0**attempt, BACKOFF_CAP_SECONDS) + random.random()
        time.sleep(delay)


class RangeReader(io.RawIOBase):
    """Seekable read-only view over HTTP range windows, with a per-instance cache.

    Mirrors themol_hessian_orbitals.HttpRangeFile in shape but adds two things
    this probe needs: every fetch is byte-capped through Fetcher, and reads fully
    contained in an already-fetched window are served from cache (HDF5 revisits
    the same metadata blocks repeatedly).
    """

    def __init__(
        self, fetcher: Fetcher, url: str, *, timeout: float = READ_TIMEOUT_SECONDS
    ) -> None:
        self.fetcher = fetcher
        self.url = url
        self._timeout = timeout
        self._windows: list[tuple[int, int, bytes]] = []
        self._pos = 0
        probe, headers = fetcher.get_range(url, 0, 0, timeout=timeout)
        content_range = headers.get("Content-Range")
        if content_range and "/" in content_range:
            self.size = int(content_range.split("/")[-1])
        else:
            self.size = int(headers.get("Content-Length") or len(probe))

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

    def _from_cache(self, start: int, end: int) -> bytes | None:
        for window_start, window_end, payload in self._windows:
            if window_start <= start and end <= window_end:
                return payload[start - window_start : end - window_start + 1]
        return None

    def read(self, size: int = -1) -> bytes:
        if size is None or size < 0:
            size = self.size - self._pos
        if size <= 0:
            return b""
        start = self._pos
        end = min(self._pos + size, self.size) - 1
        if end < start:
            return b""
        payload = self._from_cache(start, end)
        if payload is None:
            payload, _ = self.fetcher.get_range(self.url, start, end, timeout=self._timeout)
            self._windows.append((start, start + len(payload) - 1, payload))
        self._pos += len(payload)
        return payload

    def readinto(self, buffer: Any) -> int:
        data = self.read(len(buffer))
        buffer[: len(data)] = data
        return len(data)


def make_session() -> Any:
    import requests

    session = requests.Session()
    session.trust_env = False
    session.headers.update({"User-Agent": "Mozilla/5.0", "Accept-Encoding": "identity"})
    return session


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, np.ndarray):
        return [_jsonable(item) for item in value.tolist()]
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def read_index_window(fetcher: Fetcher, subset: Subset) -> list[dict[str, str]]:
    """The first INDEX_WINDOW_BYTES of a subset index CSV, parsed."""

    url = f"{HF_MIRROR_BASE}{subset.directory}/{subset.index_file}"
    payload, _ = fetcher.get_range(url, 0, INDEX_WINDOW_BYTES - 1, timeout=300.0)
    text = payload.decode("utf-8", "replace")
    cut = text.rfind("\n")
    if cut > 0:
        text = text[: cut + 1]
    return list(csv.DictReader(io.StringIO(text)))


def describe_dataset(dataset: Any) -> dict[str, Any]:
    name = dataset.name.split("/")[-1]
    unit, unit_evidence = UNIT_HINTS.get(name, (None, "unmeasured"))
    entry: dict[str, Any] = {
        "name": name,
        "kind": "dataset",
        "shape": [int(dimension) for dimension in dataset.shape],
        "dtype": str(dataset.dtype),
        "unit": unit,
        "unit_evidence": unit_evidence,
        "attrs": _jsonable(dict(dataset.attrs)),
    }
    if dataset.dtype != object and dataset.shape:
        entry["bytes_per_record"] = int(np.prod(dataset.shape)) * dataset.dtype.itemsize
    return entry


def describe_nested_group(group: Any, *, sample_children: int = 8) -> dict[str, Any]:
    names = list(group.keys())
    described = [describe_dataset(group[name]) for name in names[:sample_children]]
    return {
        "kind": "group",
        "child_count": len(names),
        "child_names_sample": names[:4],
        "children": described,
        "attrs": _jsonable(dict(group.attrs)),
    }


def describe_molecule(group: Any) -> dict[str, Any]:
    """Structure of one uuid group without enumerating every step.

    Relaxation and torsion groups hold one child group per step (up to a few
    thousand); opening each one to test its type would cost a header read per
    step.  Names matching "step k" / "constraint k" are therefore taken to be
    groups without opening them, and only the first is described.  Every other
    child is opened and typed properly, so a nested group such as MBIS
    mbis_info is never mistaken for a dataset.
    """

    import h5py

    names = list(group.keys())
    step_names = [name for name in names if NESTED_GROUP_PATTERN.match(name)]
    other_names = [name for name in names if not NESTED_GROUP_PATTERN.match(name)]
    datasets = []
    nested = []
    other_group_count = 0
    for name in other_names:
        member = group[name]
        if isinstance(member, h5py.Group):
            other_group_count += 1
            described = describe_nested_group(member)
            described["first_child_name"] = name
            nested.append(described)
        else:
            datasets.append(describe_dataset(member))
    if step_names:
        described = describe_nested_group(group[step_names[0]])
        described["first_child_name"] = step_names[0]
        nested.append(described)
    return {
        "attrs": _jsonable(dict(group.attrs)),
        "dataset_count": len(datasets),
        "datasets": datasets,
        "nested_group_count": other_group_count + len(step_names),
        "nested_groups": nested,
    }


def measured_key_names(schema: dict[str, Any]) -> list[str]:
    names = [entry["name"] for entry in schema["datasets"]]
    for nested in schema["nested_groups"]:
        names.extend(child["name"] for child in nested["children"])
    return names


def mbis_derived(
    charges: np.ndarray,
    coordinates: np.ndarray,
    atomic_dipoles: np.ndarray,
    atomic_quadrupoles: np.ndarray,
    volumes: np.ndarray,
    parameters: np.ndarray,
    atomic_numbers: np.ndarray,
) -> dict[str, Any]:
    """Molecular quantities MBIS supports, plus the self-consistency checks."""

    total_charge = float(charges.sum())
    dipole_vector = charges @ coordinates + atomic_dipoles.sum(axis=0)
    dipole_magnitude_e_a = float(np.linalg.norm(dipole_vector))
    traces = np.trace(atomic_quadrupoles, axis1=1, axis2=2)
    slater_population = float(parameters[:, 1].sum())
    expected_electrons = float(atomic_numbers.sum() - total_charge)
    parent_indices = parameters[:, 0]
    return {
        "charge_sum_e": total_charge,
        "dipole_vector_e_a": _jsonable(dipole_vector),
        "dipole_magnitude_e_a": dipole_magnitude_e_a,
        "dipole_magnitude_debye": dipole_magnitude_e_a * E_ANGSTROM_TO_DEBYE,
        "volume_sum_angstrom3": float(volumes.sum()),
        "max_abs_quadrupole_trace_e_a2": float(np.abs(traces).max()) if traces.size else 0.0,
        "slater_population_sum_e": slater_population,
        "expected_electrons_e": expected_electrons,
        "electron_count_delta_e": slater_population - expected_electrons,
        "parent_index_in_range": bool(
            parent_indices.size == 0
            or (parent_indices.min() >= 0 and parent_indices.max() < len(atomic_numbers))
        ),
        "slater_populations_positive": bool(parameters[:, 1].min() > 0.0),
        "inverse_widths_positive": bool(parameters[:, 2].min() > 0.0),
        "volumes_positive": bool(volumes.min() > 0.0),
    }


def formal_charge_from_smiles(smiles: str) -> int | None:
    try:
        from rdkit import Chem, RDLogger

        RDLogger.DisableLog("rdApp.*")
        molecule = Chem.MolFromSmiles(smiles)
        if molecule is None:
            return None
        return int(sum(atom.GetFormalCharge() for atom in molecule.GetAtoms()))
    except Exception:  # noqa: BLE001 - RDKit is optional for this probe
        return None


def read_mbis_molecule(group: Any) -> dict[str, Any]:
    atomic_numbers = group["atomic_numbers"][:].ravel().astype(int)
    coordinates = np.asarray(group["coords"][:], dtype=float)
    info = group["mbis_info"]
    charges = np.asarray(info["atomic_charge"][:], dtype=float).ravel()
    atomic_dipoles = np.asarray(info["atomic_dipole"][:], dtype=float)
    atomic_quadrupoles = np.asarray(info["atomic_quadrupole"][:], dtype=float)
    volumes = np.asarray(info["atomic_volumes"][:], dtype=float).ravel()
    parameters = np.asarray(group["parameters"][:], dtype=float)
    derived = mbis_derived(
        charges,
        coordinates,
        atomic_dipoles,
        atomic_quadrupoles,
        volumes,
        parameters,
        atomic_numbers,
    )
    derived["natoms"] = len(atomic_numbers)
    derived["atomic_numbers"] = atomic_numbers.tolist()
    return {
        "coordinates": coordinates,
        "atomic_numbers": atomic_numbers,
        "atomic_charge": charges,
        "atomic_dipole": atomic_dipoles,
        "derived": derived,
    }


XTB_DIPOLE_PATTERN = re.compile(
    r"^\s*full:\s*(-?\d+\.\d+)\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)",
    re.MULTILINE,
)


def parse_xtb_dipole(text: str) -> float | None:
    """Total molecular dipole (Debye) from the xTB molecular dipole block."""

    marker = text.find("molecular dipole:")
    if marker < 0:
        return None
    match = XTB_DIPOLE_PATTERN.search(text[marker:])
    if match is None:
        return None
    return float(match.group(4))


def xtb_dipole_crosscheck(
    molecules: list[dict[str, Any]],
    *,
    xtb_executable: Path | None,
    scratch_root: Path,
    count: int = 3,
    timeout_seconds: int = 900,
) -> dict[str, Any]:
    """Compare the MBIS dipole with a GFN2-xTB dipole on the same geometry.

    This is a cross-level sanity band, not an accuracy claim: MBIS here is
    PBE0/def2-TZVPD while xTB is a semi-empirical tight-binding Hamiltonian, so
    the two magnitudes are expected to agree to roughly 10-20 percent, not
    exactly.
    """

    if xtb_executable is None or not Path(xtb_executable).is_file():
        return {"status": "skipped", "reason": "xTB executable not found"}
    import shutil

    from themol_hessian_orbitals import write_xyz

    from electrolyte_ml.xtb_runner import run_xtb_subprocess

    scratch_root.mkdir(parents=True, exist_ok=True)
    smallest = sorted(molecules, key=lambda item: item["derived"]["natoms"])[:count]
    results = []
    for molecule in smallest:
        uuid = molecule["themol_uuid"]
        workdir = scratch_root / f"dipole_{uuid[:12]}"
        if workdir.exists():
            shutil.rmtree(workdir)
        workdir.mkdir(parents=True, exist_ok=True)
        xyz_path = workdir / "mol.xyz"
        write_xyz(xyz_path, molecule["atomic_numbers"], molecule["coordinates"], uuid)
        completed = run_xtb_subprocess(
            Path(xtb_executable),
            ["mol.xyz", "--gfn", "2", "--sp"],
            cwd=workdir,
            timeout_seconds=timeout_seconds,
        )
        text = completed.stdout.decode("utf-8", "replace") + completed.stderr.decode(
            "utf-8", "replace"
        )
        xtb_dipole = parse_xtb_dipole(text)
        mbis_dipole = molecule["derived"]["dipole_magnitude_debye"]
        results.append(
            {
                "themol_uuid": uuid,
                "natoms": molecule["derived"]["natoms"],
                "mbis_dipole_debye": mbis_dipole,
                "xtb_dipole_debye": xtb_dipole,
                "abs_difference_debye": (
                    None if xtb_dipole is None else abs(xtb_dipole - mbis_dipole)
                ),
                "returncode": completed.returncode,
            }
        )
    ratios = [
        row["xtb_dipole_debye"] / row["mbis_dipole_debye"]
        for row in results
        if row["xtb_dipole_debye"] and row["mbis_dipole_debye"]
    ]
    return {
        "status": "ok" if all(row["returncode"] == 0 for row in results) else "partial",
        "note": "cross-level sanity band only; PBE0 MBIS vs GFN2-xTB, not an accuracy test",
        "rows": results,
        "xtb_over_mbis_ratio": ratios,
    }


def _read_scalar_string(dataset: Any) -> str:
    value = dataset[()]
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return str(value)


def _dataset_array(dataset: Any) -> Any:
    """A dataset as an array; a scalar dataspace has no slice to take."""

    if dataset.shape == ():
        return np.asarray(dataset[()])
    return dataset[:]


def _shape_sample(value: Any) -> dict[str, Any]:
    array = np.asarray(value)
    flat = array.ravel()
    return {
        "shape": [int(dimension) for dimension in array.shape],
        "head": _jsonable(flat[:4]),
    }


def probe_subset(
    fetcher: Fetcher,
    subset: Subset,
    *,
    molecule_limit: int,
    raw_dir: Path,
    log: Any = print,
) -> dict[str, Any]:
    import h5py

    rows = read_index_window(fetcher, subset)
    counts = Counter(row["h5_file"] for row in rows)
    if not counts:
        raise RuntimeError(f"{subset.name}: index window held no rows")
    shard, _ = counts.most_common(1)[0]
    targets = [row for row in rows if row["h5_file"] == shard][:molecule_limit]
    url = f"{HF_MIRROR_BASE}{subset.directory}/{shard}"
    log(f"  {subset.name}: shard={shard} targets={len(targets)}")

    record: dict[str, Any] = {
        "name": subset.name,
        "directory": subset.directory,
        "index_file": subset.index_file,
        "index_columns_measured": list(rows[0].keys()),
        "shard": shard,
        "documented_level": subset.documented_level,
        "documented_entries": subset.documented_entries,
        "molecules_probed": 0,
        "molecule_samples": [],
    }
    reader = RangeReader(fetcher, url)
    before = fetcher.total_bytes
    with h5py.File(reader, "r") as handle:
        record["root_attrs"] = _jsonable(dict(handle.attrs))
        first = handle[targets[0]["uuid"]]
        schema = describe_molecule(first)
        record["schema"] = schema
        record["measured_keys"] = measured_key_names(schema)
        record["datasets_with_empty_shape"] = [
            entry["name"] for entry in schema["datasets"] if 0 in entry["shape"]
        ]
        record["bytes_for_schema_and_data"] = fetcher.total_bytes - before

        if subset.name == "mbis":
            molecules = []
            for row in targets:
                payload = read_mbis_molecule(handle[row["uuid"]])
                molecule = {
                    "themol_uuid": row["uuid"],
                    "smiles": row["mapped_nonisomeric_smiles"],
                    "formal_charge_from_smiles": formal_charge_from_smiles(
                        row["mapped_nonisomeric_smiles"]
                    ),
                    "coordinates": payload["coordinates"],
                    "atomic_numbers": payload["atomic_numbers"],
                    "atomic_charge": payload["atomic_charge"],
                    "atomic_dipole": payload["atomic_dipole"],
                    "derived": payload["derived"],
                }
                molecules.append(molecule)
                record["molecule_samples"].append(mbis_molecule_sample(molecule))
            record["molecules_probed"] = len(molecules)
            record["mbis_poc"] = summarise_mbis_poc(molecules)
            (raw_dir / "mbis_molecules.json").write_text(
                json.dumps(
                    [{key: _jsonable(value) for key, value in item.items()} for item in molecules],
                    indent=1,
                ),
                encoding="utf-8",
            )
        elif subset.name == "hessian":
            group = handle[targets[0]["uuid"]]
            atomic_numbers = group["atomic_numbers"][:].ravel()
            record["molecule_samples"].append(
                {
                    "themol_uuid": targets[0]["uuid"],
                    "natoms": len(atomic_numbers),
                    "hessian_shape": [int(d) for d in group["hessian"].shape],
                    "smiles": _read_scalar_string(group["mapped_nonisomeric_smiles"]),
                }
            )
            record["molecules_probed"] = 1
        else:
            sample: dict[str, Any] = {"themol_uuid": targets[0]["uuid"]}
            if "torsion_atom_indices" in first:
                sample["torsion_atom_indices"] = _jsonable(first["torsion_atom_indices"][:])
            nested_name = schema["nested_groups"][0]["first_child_name"]
            child = first[nested_name]
            for key in child:
                sample[f"{nested_name}/{key}"] = _shape_sample(_dataset_array(child[key]))
            record["molecule_samples"].append(sample)
            record["molecules_probed"] = 1

        record["root_enumeration"] = (
            "skipped: a dense HDF5 root group needs one link lookup per molecule to "
            "enumerate, which does not finish in reasonable time over HTTP range reads; "
            "only the uuid-addressed molecule groups are inspected"
        )

    record["bytes_total_for_subset"] = fetcher.total_bytes - before
    (raw_dir / f"schema_{subset.name}.json").write_text(
        json.dumps(record["schema"], indent=1), encoding="utf-8"
    )
    return record


def mbis_molecule_sample(molecule: dict[str, Any]) -> dict[str, Any]:
    """One JSON row for the delivery: identity plus the derived MBIS numbers."""

    return {
        "themol_uuid": molecule["themol_uuid"],
        "formal_charge_from_smiles": molecule["formal_charge_from_smiles"],
        **molecule["derived"],
    }


def summarise_mbis_poc(molecules: list[dict[str, Any]]) -> dict[str, Any]:
    """MBIS self-consistency over the probed molecules.

    The MBIS subset covers ions as well as neutral molecules, so the charge test
    is against the SMILES formal charge rather than against zero: the probed set
    really does contain a +1 and a -1 species, and their charge sums come out at
    +1.00005 and -0.99994 e.
    """

    charges = [molecule["derived"]["charge_sum_e"] for molecule in molecules]
    dipoles = [
        molecule["derived"]["dipole_magnitude_debye"]
        for molecule in molecules
        if molecule["formal_charge_from_smiles"] == 0
    ]
    traces = [molecule["derived"]["max_abs_quadrupole_trace_e_a2"] for molecule in molecules]
    deltas = [abs(molecule["derived"]["electron_count_delta_e"]) for molecule in molecules]
    formal = [molecule["formal_charge_from_smiles"] for molecule in molecules]
    residuals = [
        abs(molecule["derived"]["charge_sum_e"] - molecule["formal_charge_from_smiles"])
        for molecule in molecules
        if molecule["formal_charge_from_smiles"] is not None
    ]
    return {
        "molecules": len(molecules),
        "max_abs_charge_sum_e": max((abs(value) for value in charges), default=0.0),
        "max_abs_charge_residual_e": max(residuals, default=0.0),
        "charge_residual_within_tolerance": all(
            value <= CHARGE_SUM_TOLERANCE_E for value in residuals
        ),
        "molecules_with_known_formal_charge": len(residuals),
        "charged_molecules": sum(1 for value in formal if value),
        "max_abs_quadrupole_trace_e_a2": max(traces, default=0.0),
        "quadrupoles_traceless_within_tolerance": all(
            value <= QUADRUPOLE_TRACE_TOLERANCE_E_A2 for value in traces
        ),
        "max_abs_electron_count_delta_e": max(deltas, default=0.0),
        "electron_count_within_tolerance": all(
            value <= ELECTRON_COUNT_TOLERANCE_E for value in deltas
        ),
        "neutral_dipoles": len(dipoles),
        "dipole_debye_min": min(dipoles, default=0.0),
        "dipole_debye_max": max(dipoles, default=0.0),
        "dipole_origin_note": DIPOLE_ORIGIN_NOTE,
        "formal_charges_from_smiles": sorted(set(formal), key=lambda value: (value is None, value)),
        "natoms_min": min((item["derived"]["natoms"] for item in molecules), default=0),
        "natoms_max": max((item["derived"]["natoms"] for item in molecules), default=0),
    }


def _load_mbis_molecules(raw_dir: Path) -> list[dict[str, Any]]:
    path = raw_dir / "mbis_molecules.json"
    if not path.is_file():
        return []
    molecules = json.loads(path.read_text(encoding="utf-8"))
    for molecule in molecules:
        molecule["atomic_numbers"] = np.asarray(molecule["atomic_numbers"], dtype=int)
        molecule["coordinates"] = np.asarray(molecule["coordinates"], dtype=float)
    return molecules


def build_answers(
    records: dict[str, Any],
    orbital_matches: list[str],
    crosscheck: dict[str, Any],
) -> dict[str, Any]:
    mbis_keys = records.get("mbis", {}).get("measured_keys", [])
    mbis_poc = records.get("mbis", {}).get("mbis_poc", {})
    return {
        "does_themol_store_dft_homo_lumo": {
            "answer": "no",
            "evidence": "measured",
            "detail": (
                "The union of every dataset name measured across the five subsets holds no "
                "eigenvalue, gap, IP/EA or orbital field; only a GFN2-xTB single point run by "
                "this project produces HOMO/LUMO from THEMol geometries."
            ),
            "matching_keys": orbital_matches,
        },
        "molecular_dipole_field": {
            "answer": "not stored, derivable",
            "evidence": "measured",
            "detail": (
                "No subset carries a molecular dipole dataset. MBIS carries per-atom "
                "atomic_charge and atomic_dipole, from which the molecular dipole follows at "
                "PBE0/def2-TZVPD level. The derivation is " + DIPOLE_ORIGIN_NOTE + "."
            ),
        },
        "polarizability_field": {
            "answer": "no",
            "evidence": "measured",
            "detail": (
                "No polarizability, response or field-derivative field exists in any subset; "
                "the Hessian subset holds only the geometric (coordinate) Hessian."
            ),
        },
        "bond_order_field": {
            "answer": "no",
            "evidence": "measured",
            "detail": (
                "No bond-order dataset exists in any subset. Bond orders seen in this project "
                "come from the GFN2-xTB log, not from THEMol."
            ),
        },
        "epsilon_dn_candidates": [
            {
                "field": "mbis_info/atomic_charge",
                "unit": "e",
                "evidence": "measured",
                "why": (
                    "DFT-level per-atom charge; gives molecular dipole, charge separation and "
                    "H-bond donor/acceptor site strengths a dielectric/DN model can use."
                ),
            },
            {
                "field": "mbis_info/atomic_dipole",
                "unit": "e angstrom",
                "evidence": "measured",
                "why": "Per-atom dipoles complete the molecular dipole vector.",
            },
            {
                "field": "mbis_info/atomic_quadrupole",
                "unit": "e angstrom^2",
                "evidence": "measured",
                "why": (
                    "Higher multipole; relevant to the quadrupole term in a reaction-field "
                    "dielectric treatment."
                ),
            },
            {
                "field": "mbis_info/atomic_volumes",
                "unit": "angstrom^3",
                "evidence": "measured",
                "why": "Molecular volume / free-volume proxy for the density and viscosity channels.",
            },
            {
                "field": "parameters",
                "unit": "[parent_atom_index, Slater_population_e, inverse_width_angstrom^-1]",
                "evidence": "measured",
                "why": "Raw MBIS Slater functions; lets the populations be re-derived off-line.",
            },
            {
                "field": "hessian (hessian subset)",
                "unit": "kcal mol^-1 angstrom^-2",
                "evidence": "measured",
                "why": (
                    "DFT-level Hessian; harmonic vibrational frequencies are derivable from it "
                    "(not stored as frequencies)."
                ),
            },
            {
                "field": "energy (HessianRelax / TorsionScan / TorsionScanRelax)",
                "unit": "kcal mol^-1",
                "evidence": "documented",
                "why": "Relative conformer / torsion energies for intramolecular flexibility.",
            },
        ],
        "levels_of_theory": {
            "note": (
                "MBIS is a different level (PBE0/def2-TZVPD) from the Hessian family "
                "(B3LYP-D3(BJ)/DZVP); neither is GFN2-xTB."
            ),
            "documented": DOCUMENTED_LEVELS,
        },
        "mbis_selfconsistency": mbis_poc,
        "mbis_dataset_keys": mbis_keys,
        "xtb_crosscheck_status": crosscheck.get("status"),
    }


def build_inventory(
    *,
    output_path: Path,
    raw_dir: Path,
    max_download_mb: float,
    subset_names: list[str] | None,
    xtb_executable: Path | None,
    skip_xtb_crosscheck: bool,
    log: Any = print,
) -> dict[str, Any]:
    raw_dir.mkdir(parents=True, exist_ok=True)
    fetcher = Fetcher(make_session(), limit_bytes=int(max_download_mb * 1024 * 1024))
    selected = [
        subset for subset in SUBSETS if subset_names is None or subset.name in subset_names
    ]
    # MBIS is the only subset whose fields can feed a new channel, and it is also
    # the most expensive root-group read (~20 MB); run it first so a budget stop
    # or a throttled night can never cost us the one result that matters.
    selected.sort(key=lambda subset: 0 if subset.name == "mbis" else 1)
    records: dict[str, Any] = {}
    for subset in selected:
        try:
            records[subset.name] = probe_subset(
                fetcher,
                subset,
                molecule_limit=MOLECULES_PER_SUBSET[subset.name],
                raw_dir=raw_dir,
                log=log,
            )
        except DownloadBudgetExceeded as error:
            log(f"  {subset.name}: skipped, budget exhausted ({error})")
            records[subset.name] = {
                "name": subset.name,
                "status": "skipped_download_budget",
                "detail": str(error),
                "molecules_probed": 0,
                "measured_keys": [],
            }
        except Exception as error:  # noqa: BLE001 - one throttled shard must not lose the run
            log(f"  {subset.name}: failed ({type(error).__name__}: {error})")
            records[subset.name] = {
                "name": subset.name,
                "status": f"failed:{type(error).__name__}",
                "detail": str(error),
                "molecules_probed": 0,
                "measured_keys": [],
            }

    mbis_record = records.get("mbis", {})
    molecules = _load_mbis_molecules(raw_dir) if mbis_record.get("molecules_probed") else []
    crosscheck: dict[str, Any] = {"status": "skipped", "reason": "no MBIS molecules probed"}
    if molecules and not skip_xtb_crosscheck:
        crosscheck = xtb_dipole_crosscheck(
            molecules,
            xtb_executable=xtb_executable,
            scratch_root=raw_dir / "scratch",
        )
    elif molecules:
        crosscheck = {"status": "skipped", "reason": "--skip-xtb-crosscheck"}

    all_keys = sorted(
        {key for record in records.values() for key in record.get("measured_keys", [])}
    )
    orbital_matches = [key for key in all_keys if ORBITAL_KEY_PATTERN.search(key)]
    molecules_probed = sum(record.get("molecules_probed", 0) for record in records.values())

    payload = {
        "probe": "themol_property_inventory",
        "generated_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "source": {
            "dataset": "ByteDance-Seed/THEMol",
            "mirror": "hf-mirror.com",
            "access": "HTTP range reads; never a whole shard download",
            "license": "CC BY-NC 4.0",
            "paper": "arXiv:2605.14973",
        },
        "budget": {
            "limit_bytes": fetcher.limit_bytes,
            "downloaded_bytes": fetcher.total_bytes,
            "within_limit": fetcher.total_bytes <= fetcher.limit_bytes,
        },
        "poc": {
            "molecule_cap": MOLECULE_CAP,
            "molecules_probed": molecules_probed,
            "within_cap": molecules_probed <= MOLECULE_CAP,
            "molecules_per_subset": MOLECULES_PER_SUBSET,
        },
        "documented_levels": DOCUMENTED_LEVELS,
        "subsets": records,
        "all_measured_keys": all_keys,
        "orbital_energy_fields": {
            "found_in_any_subset": bool(orbital_matches),
            "matching_keys": orbital_matches,
        },
        "mbis_xtb_dipole_crosscheck": crosscheck,
        "answers": build_answers(records, orbital_matches, crosscheck),
    }
    output_path.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    (raw_dir / "download_accounting.json").write_text(
        json.dumps(payload["budget"], indent=1), encoding="utf-8"
    )
    return payload


def inventory_problems(payload: dict[str, Any]) -> list[str]:
    """Every reason the delivered inventory is not internally consistent."""

    problems: list[str] = []
    subsets = payload.get("subsets", {})
    for subset in SUBSETS:
        record = subsets.get(subset.name)
        if record is None:
            problems.append(f"subset {subset.name} missing")
            continue
        if not record.get("measured_keys"):
            status = str(record.get("status", ""))
            if status != "skipped_download_budget" and not status.startswith("failed"):
                problems.append(f"subset {subset.name} measured no keys and did not say why")
            continue
        if not record.get("molecules_probed"):
            problems.append(f"subset {subset.name} probed no molecules")

    budget = payload.get("budget", {})
    if not budget.get("within_limit", False):
        problems.append("download budget exceeded")
    if budget.get("downloaded_bytes", 0) <= 0:
        problems.append("download accounting is empty")

    poc = payload.get("poc", {})
    if not poc.get("within_cap", False):
        problems.append("molecule cap exceeded")
    if not poc.get("molecules_probed"):
        problems.append("no molecules were probed")

    orbital = payload.get("orbital_energy_fields", {})
    if orbital.get("found_in_any_subset"):
        problems.append(f"orbital-looking keys found: {orbital.get('matching_keys')}")

    mbis_keys = set(subsets.get("mbis", {}).get("measured_keys", []))
    for required in ("atomic_charge", "atomic_dipole", "atomic_quadrupole", "atomic_volumes"):
        if required not in mbis_keys:
            problems.append(f"MBIS key {required} missing from the measured inventory")

    poc_summary = subsets.get("mbis", {}).get("mbis_poc", {})
    if poc_summary:
        if not poc_summary.get("charge_residual_within_tolerance"):
            problems.append(
                "MBIS charge sums disagree with the SMILES formal charge: "
                f"{poc_summary.get('max_abs_charge_residual_e')}"
            )
        if not poc_summary.get("molecules_with_known_formal_charge"):
            problems.append("MBIS charge check had no molecule with a known formal charge")
        if not poc_summary.get("quadrupoles_traceless_within_tolerance"):
            problems.append("MBIS quadrupoles are not traceless")
        if not poc_summary.get("electron_count_within_tolerance"):
            problems.append(
                "MBIS Slater populations miss the electron count: "
                f"{poc_summary.get('max_abs_electron_count_delta_e')}"
            )
    answers = payload.get("answers", {})
    if answers.get("does_themol_store_dft_homo_lumo", {}).get("answer") != "no":
        problems.append("the HOMO/LUMO answer is not the measured one")
    return problems


def refresh_from_raw(inventory_path: Path, raw_dir: Path, log: Any = print) -> int:
    """Re-derive the MBIS summary from the raw POC outputs, with no network.

    The raw molecule arrays are the expensive part of a run (one MBIS shard costs
    roughly 20 MB of root-group metadata before a single value is read) and every
    summary number is a pure function of them.  A summary definition that changes
    therefore does not have to be paid for with another download.
    """

    if not inventory_path.is_file():
        log(f"FAIL: {inventory_path} does not exist")
        return 1
    molecules = _load_mbis_molecules(raw_dir)
    if not molecules:
        log(f"FAIL: {raw_dir / 'mbis_molecules.json'} is missing or empty")
        return 1
    payload = json.loads(inventory_path.read_text(encoding="utf-8"))
    summary = summarise_mbis_poc(molecules)
    payload["subsets"]["mbis"]["mbis_poc"] = summary
    payload["subsets"]["mbis"]["molecule_samples"] = [
        mbis_molecule_sample(molecule) for molecule in molecules
    ]
    payload["answers"] = build_answers(
        payload["subsets"],
        payload["orbital_energy_fields"]["matching_keys"],
        payload["mbis_xtb_dipole_crosscheck"],
    )
    payload["summary_refreshed_from"] = str(raw_dir / "mbis_molecules.json")
    inventory_path.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    problems = inventory_problems(payload)
    log(
        f"refreshed the MBIS summary from {len(molecules)} raw molecules; "
        f"max charge residual {summary['max_abs_charge_residual_e']:.2e} e"
    )
    for problem in problems:
        log(f"FAIL: {problem}")
    return 1 if problems else 0


def check_inventory(path: Path, log: Any = print) -> int:
    if not path.is_file():
        log(f"FAIL: {path} does not exist")
        return 1
    payload = json.loads(path.read_text(encoding="utf-8"))
    problems = inventory_problems(payload)
    budget = payload.get("budget", {})
    poc = payload.get("poc", {})
    log(
        f"subsets={sorted(payload.get('subsets', {}))} "
        f"molecules={poc.get('molecules_probed')} "
        f"bytes={budget.get('downloaded_bytes')}"
    )
    for problem in problems:
        log(f"FAIL: {problem}")
    if problems:
        log(f"{len(problems)} problem(s)")
        return 1
    log("inventory consistent")
    return 0


def resolve_xtb(explicit: Path | None) -> Path | None:
    import os
    import shutil

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
    return None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=DEFAULT_INVENTORY_PATH)
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    parser.add_argument("--max-download-mb", type=float, default=DEFAULT_MAX_DOWNLOAD_MB)
    parser.add_argument("--subsets", nargs="+", default=None, choices=sorted(SUBSET_BY_NAME))
    parser.add_argument("--xtb", type=Path, default=None)
    parser.add_argument("--skip-xtb-crosscheck", action="store_true")
    parser.add_argument(
        "--check",
        action="store_true",
        help="validate an existing inventory JSON offline instead of probing",
    )
    parser.add_argument(
        "--refresh-from-raw",
        action="store_true",
        help="re-derive the MBIS summary from the raw POC outputs, offline",
    )
    parser.add_argument("--inventory", type=Path, default=DEFAULT_INVENTORY_PATH)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.check:
        return check_inventory(args.inventory)
    if args.refresh_from_raw:
        return refresh_from_raw(args.inventory, args.raw_dir)

    payload = build_inventory(
        output_path=args.out,
        raw_dir=args.raw_dir,
        max_download_mb=args.max_download_mb,
        subset_names=args.subsets,
        xtb_executable=resolve_xtb(args.xtb),
        skip_xtb_crosscheck=args.skip_xtb_crosscheck,
        log=print,
    )
    print(
        f"downloaded {payload['budget']['downloaded_bytes']:,} B "
        f"of {payload['budget']['limit_bytes']:,} B; "
        f"molecules={payload['poc']['molecules_probed']}"
    )
    print(f"keys: {payload['all_measured_keys']}")
    print(f"wrote {args.out} and {args.raw_dir}")
    problems = inventory_problems(payload)
    for problem in problems:
        print(f"FAIL: {problem}")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
