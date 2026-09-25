"""Offline tests for the GSDS Zenodo archive inspector.

The inspector itself needs the network, but its two hard parts do not: locating
the central directory through the zip64 records, and inflating one entry from a
range of its bytes. Both are exercised here against zips built in memory, so a
regression in the parsers is caught without fetching the 4.75 GB archive.
"""

from __future__ import annotations

import io
import random
import struct
import zipfile

from probes.inspect_gsds_zenodo_archive import (
    ZIP64_EOCD_SIGNATURE,
    ZIP64_LOCATOR_SIGNATURE,
    _zip64_values,
    inflate_entry_head,
    parse_central_directory,
    parse_central_directory_offset,
)


def make_zip(entries: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, payload in entries.items():
            archive.writestr(name, payload)
    return buffer.getvalue()


def entries_of(blob: bytes) -> list[dict[str, object]]:
    offset, size = parse_central_directory_offset(blob[-65536:])
    return parse_central_directory(blob[offset : offset + size])


def test_the_central_directory_round_trips_entry_names() -> None:
    blob = make_zip({"a/one.csv": b"x;y\n1;2\n", "a/two.csv": b"h\n"})
    entries = entries_of(blob)
    assert [entry["name"] for entry in entries] == ["a/one.csv", "a/two.csv"]
    assert {entry["method"] for entry in entries} == {zipfile.ZIP_DEFLATED}


def test_sizes_and_offsets_point_at_the_local_headers() -> None:
    blob = make_zip({"only.csv": b"index;SMILES\n0;CCO\n"})
    (entry,) = entries_of(blob)
    offset = int(entry["local_header_offset"])
    assert blob[offset : offset + 4] == b"PK\x03\x04"
    assert int(entry["uncompressed_size"]) == len(b"index;SMILES\n0;CCO\n")


def test_a_truncated_head_still_yields_the_csv_header() -> None:
    """Partial inflate is the whole point: the header arrives before the tail.

    The body is incompressible on purpose, so 512 fetched bytes really are a
    truncated stream rather than the whole entry.
    """
    rng = random.Random(0)
    body = bytes(rng.getrandbits(8) for _ in range(4096))
    payload = b"index;SMILES;DN;DC;RedPot;OxPot\n0;CCO;20.25;17.71;1.91;4.85\n" + body
    blob = make_zip({"run/generation_0/Candidates.csv": payload})
    (entry,) = entries_of(blob)
    assert int(entry["compressed_size"]) > 512

    def fetcher(start: int, end: int) -> bytes:
        return blob[start : end + 1]

    text, truncated = inflate_entry_head(entry, 512, fetcher=fetcher)
    assert text.startswith("index;SMILES;DN;DC;RedPot;OxPot\n0;CCO;20.25;17.71;1.91;4.85\n")
    assert truncated is True


def test_a_complete_entry_reports_itself_as_untruncated() -> None:
    payload = b"index;SMILES\n0;CCO\n"
    blob = make_zip({"input.csv": payload})
    (entry,) = entries_of(blob)

    def fetcher(start: int, end: int) -> bytes:
        return blob[start : end + 1]

    text, truncated = inflate_entry_head(entry, 65_536, fetcher=fetcher)
    assert text == payload.decode()
    assert truncated is False


def test_zip64_extra_values_follow_the_sentinel_order() -> None:
    extra = struct.pack("<HH", 0x0001, 16) + struct.pack("<QQ", 11, 22)
    assert _zip64_values(extra, ["uncompressed", "compressed"]) == {
        "uncompressed": 11,
        "compressed": 22,
    }


def test_the_zip64_record_wins_over_the_classic_end_of_central_directory() -> None:
    """A >4 GB archive stores the real offsets only in the zip64 record."""
    record = struct.pack(
        "<4sQ2H2L4Q", ZIP64_EOCD_SIGNATURE, 44, 45, 45, 0, 0, 1, 1, 1234, 5678
    )
    locator = struct.pack("<4sLQL", ZIP64_LOCATOR_SIGNATURE, 0, 100, 1)
    classic = struct.pack("<4s4H2LH", b"PK\x05\x06", 0, 0, 1, 1, 999, 999, 0)
    assert parse_central_directory_offset(record + locator + classic) == (5678, 1234)
