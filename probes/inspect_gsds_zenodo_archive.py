"""Inspect the GSDS Zenodo archive without downloading its 4.75 GB body.

The DC-200 per-molecule dielectric table behind the GSDS data descriptor was
never located, and `reports/decisions_log.md` recorded the remaining gap
explicitly: Zenodo record 21061162 holds a single 4.75 GB
`GSDS_Prior_Finetune.zip` that was never downloaded or unpacked, so nothing
could be said about its contents.

This probe closes that gap without the download. A ZIP keeps its central
directory at the end of the file and Zenodo serves HTTP range requests, so two
range GETs read every entry name, and one more reads the head of a chosen entry:

  * `--list` (default): 64 KiB tail + the central directory, then write the full
    entry listing and a summary of entries whose path names a dielectric or
    DC-200 artefact;
  * `--head <entry>`: fetch the first `--head-bytes` of that entry's compressed
    stream and inflate it in memory, which is enough to read a CSV header and its
    first rows.

Nothing else is fetched: the archive body is never downloaded. `zenodo.org`
does not resolve in this environment while `www.zenodo.org` does, so the
connection is pinned to an IP obtained from the resolving name while TLS keeps
SNI and certificate validation against `zenodo.org`.

Usage:
    python probes/inspect_gsds_zenodo_archive.py
    python probes/inspect_gsds_zenodo_archive.py --head <entry-name> --head-bytes 65536
    python probes/inspect_gsds_zenodo_archive.py --json
"""

from __future__ import annotations

import argparse
import json
import socket
import ssl
import struct
import sys
import zlib
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

RECORD_ID = "21061162"
RECORD_URL = f"https://zenodo.org/api/records/{RECORD_ID}"
FILE_NAME = "GSDS_Prior_Finetune.zip"
FILE_PATH = f"/api/records/{RECORD_ID}/files/{FILE_NAME}/content"
FILE_BYTES = 4_746_199_417
FILE_MD5 = "f1736827b1a9f31e85587ca2eae913a7"
TLS_HOST = "zenodo.org"
RESOLVER_HOST = "www.zenodo.org"

TAIL_BYTES = 65_536
EOCD_SIGNATURE = b"PK\x05\x06"
ZIP64_EOCD_SIGNATURE = b"PK\x06\x06"
ZIP64_LOCATOR_SIGNATURE = b"PK\x06\x07"
CENTRAL_ENTRY_SIGNATURE = b"PK\x01\x02"
LOCAL_ENTRY_SIGNATURE = b"PK\x03\x04"
CENTRAL_ENTRY_FIXED = 46
LOCAL_ENTRY_FIXED = 30
SENTINEL_32 = 0xFFFFFFFF
ZIP64_EXTRA_ID = 0x0001

#: Substrings that flag an entry as a dielectric / DC-200 candidate. The GSDS
#: tree abbreviates dielectric constant as `DielecConst`, so the short form must
#: be here: a hint list without it reports a misleading zero.
CANDIDATE_HINTS = (
    "dielec",
    "permittivity",
    "epsilon",
    "eps_r",
    "dc-200",
    "dc_200",
    "dc200",
    "mnsol",
    "input.csv",
    "input-1.csv",
)


def _zenodo_ip() -> str:
    return socket.gethostbyname(RESOLVER_HOST)


def fetch_range(start: int, end: int, *, ip: str | None = None, timeout: float = 180.0) -> bytes:
    """Fetch an inclusive byte range from the archive, pinned to a zenodo IP."""
    target = ip or _zenodo_ip()
    context = ssl.create_default_context()
    connection = socket.create_connection((target, 443), timeout=timeout)
    with connection, context.wrap_socket(connection, server_hostname=TLS_HOST) as tls:
        request = (
            f"GET {FILE_PATH} HTTP/1.1\r\n"
            f"Host: {TLS_HOST}\r\n"
            f"Range: bytes={start}-{end}\r\n"
            "User-Agent: dielectric-ml-archive-listing/1.0\r\n"
            "Connection: close\r\n\r\n"
        )
        tls.sendall(request.encode("ascii"))
        chunks: list[bytes] = []
        while True:
            chunk = tls.recv(1 << 16)
            if not chunk:
                break
            chunks.append(chunk)
    payload = b"".join(chunks)
    head, separator, body = payload.partition(b"\r\n\r\n")
    if not separator:
        raise RuntimeError("malformed HTTP response: no header terminator")
    status_line = head.split(b"\r\n", 1)[0].decode("latin-1")
    if "206" not in status_line:
        raise RuntimeError(f"range request was not honoured: {status_line}")
    return body


def parse_central_directory_offset(tail: bytes) -> tuple[int, int]:
    """Return (central_directory_offset, central_directory_size) from the tail."""
    locator = tail.rfind(ZIP64_LOCATOR_SIGNATURE)
    if locator >= 0:
        record = tail.rfind(ZIP64_EOCD_SIGNATURE)
        if record >= 0:
            fields = struct.unpack_from("<4sQ2H2L4Q", tail, record)
            return int(fields[9]), int(fields[8])
        raise RuntimeError(
            "zip64 locator present but its record is outside the fetched tail"
        )
    eocd = tail.rfind(EOCD_SIGNATURE)
    if eocd < 0:
        raise RuntimeError("no end-of-central-directory record in the fetched tail")
    fields = struct.unpack_from("<4s4H2LH", tail, eocd)
    return int(fields[6]), int(fields[5])


def _zip64_values(extra: bytes, wanted: list[str]) -> dict[str, int]:
    """Read the 0x0001 extra field, whose entries follow the sentinel order."""
    cursor = 0
    while cursor + 4 <= len(extra):
        header_id, size = struct.unpack_from("<HH", extra, cursor)
        payload = extra[cursor + 4 : cursor + 4 + size]
        if header_id == ZIP64_EXTRA_ID:
            values: dict[str, int] = {}
            offset = 0
            for field in wanted:
                if offset + 8 > len(payload):
                    break
                values[field] = struct.unpack_from("<Q", payload, offset)[0]
                offset += 8
            return values
        cursor += 4 + size
    return {}


def parse_central_directory(central_directory: bytes) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []
    cursor = 0
    while True:
        found = central_directory.find(CENTRAL_ENTRY_SIGNATURE, cursor)
        if found < 0:
            break
        (
            _signature,
            _vmade,
            _vneed,
            _flags,
            method,
            _mtime,
            _mdate,
            _crc,
            compressed_32,
            uncompressed_32,
            name_length,
            extra_length,
            comment_length,
            _disk,
            _internal,
            _external,
            local_offset_32,
        ) = struct.unpack_from("<4s6H3L5H2L", central_directory, found)
        name_at = found + CENTRAL_ENTRY_FIXED
        raw_name = central_directory[name_at : name_at + name_length]
        extra = central_directory[name_at + name_length : name_at + name_length + extra_length]

        wanted = []
        if uncompressed_32 == SENTINEL_32:
            wanted.append("uncompressed")
        if compressed_32 == SENTINEL_32:
            wanted.append("compressed")
        if local_offset_32 == SENTINEL_32:
            wanted.append("local_offset")
        zip64 = _zip64_values(extra, wanted) if wanted else {}

        entries.append(
            {
                "name": raw_name.decode("utf-8", errors="replace"),
                "method": int(method),
                "compressed_size": int(zip64.get("compressed", compressed_32)),
                "uncompressed_size": int(zip64.get("uncompressed", uncompressed_32)),
                "local_header_offset": int(zip64.get("local_offset", local_offset_32)),
            }
        )
        cursor = name_at + name_length + extra_length + comment_length
    return entries


def inflate_entry_head(
    entry: dict[str, object], head_bytes: int, *, fetcher=fetch_range
) -> tuple[str, bool]:
    """Fetch the start of one entry and inflate what arrived."""
    offset = int(entry["local_header_offset"])
    blob = fetcher(offset, offset + head_bytes - 1)
    if not blob.startswith(LOCAL_ENTRY_SIGNATURE):
        raise RuntimeError(f"entry does not start with a local file header: {offset}")
    name_length, extra_length = struct.unpack_from("<HH", blob, 26)
    data_at = LOCAL_ENTRY_FIXED + name_length + extra_length
    compressed = blob[data_at:]
    truncated = len(compressed) < int(entry["compressed_size"])
    if int(entry["method"]) == 0:
        return compressed.decode("utf-8", errors="replace"), truncated
    if int(entry["method"]) != 8:
        raise RuntimeError(f"unsupported compression method {entry['method']}")
    decompressor = zlib.decompressobj(-zlib.MAX_WBITS)
    try:
        inflated = decompressor.decompress(compressed)
    except zlib.error as exc:  # a truncated deflate stream can still be useful
        raise RuntimeError(f"could not inflate entry head: {exc}") from exc
    return inflated.decode("utf-8", errors="replace"), truncated


def build_listing(entries: list[dict[str, object]]) -> dict[str, object]:
    names = [str(entry["name"]) for entry in entries]
    candidates = [
        entry
        for entry, name in zip(entries, names)
        if any(hint in name.lower() for hint in CANDIDATE_HINTS)
    ]
    tops: dict[str, int] = {}
    for name in names:
        top = name.split("/", 1)[0]
        tops[top] = tops.get(top, 0) + 1
    suffixes: dict[str, int] = {}
    for name in names:
        suffix = Path(name).suffix.lower() or "<none>"
        suffixes[suffix] = suffixes.get(suffix, 0) + 1
    return {
        "record_id": RECORD_ID,
        "record_url": RECORD_URL,
        "file": FILE_NAME,
        "file_bytes": FILE_BYTES,
        "file_md5": FILE_MD5,
        "entry_count": len(names),
        "top_level_entries": dict(sorted(tops.items(), key=lambda item: (-item[1], item[0]))),
        "suffix_counts": dict(sorted(suffixes.items(), key=lambda item: (-item[1], item[0]))),
        "candidate_hints": list(CANDIDATE_HINTS),
        "candidate_count": len(candidates),
        "candidate_entries": candidates,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit the listing as JSON")
    parser.add_argument("--head", help="entry name whose head should be fetched and inflated")
    parser.add_argument("--head-bytes", type=int, default=262_144)
    parser.add_argument(
        "--entries-out",
        type=Path,
        default=REPOSITORY_ROOT / "probes" / "artifacts" / "gsds_zenodo_archive_entries.txt",
    )
    parser.add_argument(
        "--summary-out",
        type=Path,
        default=REPOSITORY_ROOT / "probes" / "artifacts" / "gsds_zenodo_archive_listing.json",
    )
    args = parser.parse_args(argv)

    tail = fetch_range(FILE_BYTES - TAIL_BYTES, FILE_BYTES - 1)
    cd_offset, cd_size = parse_central_directory_offset(tail)
    entries = parse_central_directory(fetch_range(cd_offset, cd_offset + cd_size - 1))
    listing = build_listing(entries)

    if args.head:
        match = next((e for e in entries if e["name"] == args.head), None)
        if match is None:
            print(f"entry not found: {args.head}", file=sys.stderr)
            return 2
        text, truncated = inflate_entry_head(match, args.head_bytes)
        print(f"# {args.head}")
        print(f"# method={match['method']} compressed={match['compressed_size']} "
              f"uncompressed={match['uncompressed_size']} head_truncated={truncated}")
        sys.stdout.write(text)
        if not text.endswith("\n"):
            print()
        return 0

    args.entries_out.parent.mkdir(parents=True, exist_ok=True)
    args.entries_out.write_text(
        "\n".join(entry["name"] for entry in entries) + "\n", encoding="utf-8", newline="\n"
    )
    args.summary_out.write_text(
        json.dumps(listing, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n"
    )
    if args.json:
        print(json.dumps(listing, indent=2, ensure_ascii=False))
    else:
        print(f"{FILE_NAME}: {listing['entry_count']} entries listed via 2 range GETs")
        print(f"suffixes: {listing['suffix_counts']}")
        print(f"candidate entries: {listing['candidate_count']}")
        for entry in listing["candidate_entries"][:20]:
            print(f"  - {entry['name']} ({entry['uncompressed_size']} bytes)")
        print(f"wrote {args.entries_out}")
        print(f"wrote {args.summary_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
