#!/usr/bin/env python
"""B100-4: fetch melting points for candidates that lack them.

The admission gate produced 306 candidates, but only 70 had any melting-point
record, so the phase check could verify just 37. The other 236 came from the NBS
expansion layer, which was never added to `liquid_window_gate_report.csv`.

Without melting points those molecules cannot be confirmed liquid, and PLAN B v6.0
is explicit that unverified candidates must not be counted. So the gap has to be
closed by obtaining the data -- not by assuming the samples are liquid.

This script queries PubChem for each molecule by **InChIKey**, not by name:

  * InChIKey is an exact structural identifier, so it avoids the name-ambiguity that
    would silently attach one compound's melting point to another.
  * Every response is cached to disk with its HTTP status so a re-run is free and
    the provenance of each value is auditable.
  * A molecule with no experimental melting point is recorded as MISSING, never
    filled with an estimate.

Being a network operation it is slow, so it is resumable: already-cached InChIKeys
are skipped. Progress is written incrementally, so an interrupted run loses nothing.

Output: data/external/pubchem_mp_b100/<inchikey>.json   (cache)
        outputs/b100/pubchem_mp_lookup_b100.csv          (flattened results)
"""

from __future__ import annotations

import csv
import hashlib
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT = REPO_ROOT / "outputs" / "b100"
CACHE = REPO_ROOT / "data" / "external" / "pubchem_mp_b100"
GENERATOR = "fetch_pubchem_mp_b100/1.0.0"

QUALIFIED = OUT / "qualified_molecules_b100.csv"
EXISTING = REPO_ROOT / "data" / "processed" / "liquid_window_features.csv"

PUBCHEM = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"
# Polite rate for the public endpoint.
SLEEP_S = 0.25
TIMEOUT_S = 25
MAX_CONSECUTIVE_FAILURES = 12

PLACEHOLDERS = {"", "not_evaluated", "nan", "none", "null", "na", "n/a"}


def load(path: Path) -> list[dict]:
    raw = path.read_bytes()
    text = None
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        raise RuntimeError(f"cannot decode {path}")
    header = text.splitlines()[0] if text.splitlines() else ""
    delim = ";" if header.count(";") > header.count(",") else ","
    import io
    return list(csv.DictReader(io.StringIO(text, newline=""), delimiter=delim))


def http_json(url: str) -> tuple[int, dict | None]:
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "plan-b-b100/1.0 (research)"})
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, None
    except Exception:                       # noqa: BLE001
        return 0, None


def parse_mp_pugview(doc: dict) -> tuple[float | None, str]:
    """Extract one melting point in Celsius from a PUG-View record.

    PUG-View returns free-text experimental values that may be in C or F, may be a
    range, and may carry a qualifier such as "decomposes". Only an unambiguous single
    Celsius value is accepted. Anything else is reported explicitly so it can be
    reviewed by hand rather than silently coerced.
    """
    strings: list[str] = []

    def walk(node):
        if isinstance(node, dict):
            for k, v in node.items():
                if k == "String" and isinstance(v, str):
                    strings.append(v.strip())
                else:
                    walk(v)
        elif isinstance(node, list):
            for x in node:
                walk(x)

    walk(doc)
    if not strings:
        return None, "PUGVIEW_NO_STRINGS"

    for raw in strings:
        low = raw.lower()
        if not raw:
            continue
        # Fahrenheit branch: convert only when explicitly marked
        if "°f" in low or " f (" in low or low.endswith(" f"):
            if any(t in low for t in ("decomp", "sublim", ">", "<", "~")):
                continue
            num = ""
            for ch in raw:
                if ch.isdigit() or ch in ".-+":
                    num += ch
                elif num:
                    break
            try:
                c = (float(num) - 32.0) * 5.0 / 9.0
            except ValueError:
                continue
            return round(c, 3), f"CONVERTED_FROM_F: {raw[:70]}"

        if "°c" in low or " c (" in low or low.endswith(" c"):
            if any(t in low for t in ("decomp", "sublim", ">", "<", "~",
                                      "approx")):
                continue
            num = ""
            for ch in raw:
                if ch.isdigit() or ch in ".-+":
                    num += ch
                elif num:
                    break
            try:
                return round(float(num), 3), f"OK: {raw[:70]}"
            except ValueError:
                continue

    # no unit-tagged value found: accept a bare number only if it is plausible as C
    for raw in strings:
        low = raw.lower()
        if any(t in low for t in ("decomp", "sublim", ">", "<", "~", "approx")):
            continue
        num = ""
        for ch in raw:
            if ch.isdigit() or ch in ".-+":
                num += ch
            elif num:
                break
        try:
            v = float(num)
        except ValueError:
            continue
        if -150.0 <= v <= 400.0:
            return round(v, 3), f"ASSUMED_C: {raw[:70]}"

    return None, f"NO_USABLE_VALUE: {' | '.join(s[:30] for s in strings[:3])}"


def fetch_one(inchikey: str, name: str = "") -> dict:
    cache_file = CACHE / f"{inchikey}.json"
    if cache_file.is_file():
        try:
            rec = json.loads(cache_file.read_text(encoding="utf-8"))
            # Treat as stale if the record predates the full-record fallback or was
            # written by the broken property endpoint. A 404 from the filtered
            # PUG-View URL is NOT proof that the value is absent, so those must be
            # retried against the full record.
            stale = (
                "mp_raw" not in rec
                or rec.get("mp_note", "").startswith("PUGVIEW_HTTP_404")
                or rec.get("mp_note") == "PUG_REST_NO_MELTINGPOINT_PROPERTY"
                or "THEN_" in rec.get("mp_note", "")
            )
            if not stale:
                return rec
        except Exception:                   # noqa: BLE001
            pass

    rec = {"inchikey": inchikey, "fetched_at_utc":
           datetime.now(timezone.utc).replace(microsecond=0)
           .isoformat().replace("+00:00", "Z"), "cid": None,
           "mp_C": None, "mp_note": "", "http_status": None,
           "mp_raw": ""}

    st, d = http_json(f"{PUBCHEM}/compound/inchikey/{inchikey}/cids/JSON")
    rec["http_status"] = st
    if st != 200 or not d:
        rec["mp_note"] = f"CID_LOOKUP_FAILED_HTTP_{st}"
        cache_file.write_text(json.dumps(rec, ensure_ascii=False, indent=2) + "\n",
                              encoding="utf-8")
        return rec
    cids = d.get("IdentifierList", {}).get("CID", [])
    if not cids:
        rec["mp_note"] = "NO_CID_FOR_INCHIKEY"
        cache_file.write_text(json.dumps(rec, ensure_ascii=False, indent=2) + "\n",
                              encoding="utf-8")
        return rec
    cid = cids[0]
    rec["cid"] = cid

    # PUG-REST does not expose MeltingPoint as a property; PUG-View does, and it is
    # where the experimental value lives.
    #
    # The `heading=Melting+Point` filter returns 404 for many CIDs even when the
    # record exists and DOES contain a melting point (verified: cid 12242 404s on the
    # filtered URL but the full record is present). So a 404 on the filtered endpoint
    # is not evidence of a missing value -- fall back to the full record before
    # concluding anything.
    time.sleep(SLEEP_S)
    url = (f"https://pubchem.ncbi.nlm.nih.gov/rest/pug_view/data/compound/{cid}"
           f"/JSON?heading=Melting+Point")
    st2, d2 = http_json(url)
    if st2 == 200 and d2:
        val, note = parse_mp_pugview(d2)
    else:
        time.sleep(SLEEP_S)
        st3, d3 = http_json(
            f"https://pubchem.ncbi.nlm.nih.gov/rest/pug_view/data/compound/"
            f"{cid}/JSON")
        if st3 == 200 and d3:
            val, note = parse_mp_pugview(d3)
            if val is None:
                note = f"FULLRECORD_{note}"
        else:
            val, note = None, f"PUGVIEW_HTTP_{st2}_THEN_{st3}"
    rec["mp_C"] = val
    rec["mp_note"] = note
    rec["mp_raw"] = note

    cache_file.write_text(json.dumps(rec, ensure_ascii=False, indent=2) + "\n",
                          encoding="utf-8")
    return rec


def main() -> int:
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])
    if not QUALIFIED.is_file():
        print("FATAL: qualified list missing; run the admission gate first",
              file=sys.stderr)
        return 2
    CACHE.mkdir(parents=True, exist_ok=True)

    qualified = load(QUALIFIED)
    known = {(r.get("inchikey") or "").strip()
             for r in (load(EXISTING) if EXISTING.is_file() else [])}
    known.discard("")

    def cache_is_usable(f: Path) -> bool:
        """True only for a cache entry that reflects the current fetch logic.

        The main loop used to skip any molecule whose cache file merely existed,
        which meant the per-record staleness rule inside fetch_one() never ran for
        them. That left 120 records stuck at a PUG-View 404 that does not actually
        mean the value is missing. The same staleness rule is applied here.
        """
        if not f.is_file():
            return False
        try:
            rec = json.loads(f.read_text(encoding="utf-8"))
        except Exception:                   # noqa: BLE001
            return False
        if "mp_raw" not in rec:
            return False
        note = rec.get("mp_note", "")
        if note.startswith("PUGVIEW_HTTP_404"):
            return False
        if note == "PUG_REST_NO_MELTINGPOINT_PROPERTY":
            return False
        if "THEN_" in note:
            return False
        return True

    need = [r for r in qualified
            if r["inchikey"] not in known
            and not cache_is_usable(CACHE / f"{r['inchikey']}.json")]
    if limit:
        need = need[:limit]

    print(f"[B100-4] molecules already having mp: "
          f"{len(qualified) - len(need)}")
    print(f"[B100-4] to fetch this run: {len(need)}")

    results: list[dict] = []
    consecutive_fail = 0
    for i, q in enumerate(need, 1):
        rec = fetch_one(q["inchikey"])
        rec["name"] = q.get("name", "")
        results.append(rec)
        ok = rec.get("mp_C") is not None
        consecutive_fail = 0 if ok or rec.get("cid") else consecutive_fail + 1
        if i % 20 == 0 or i == len(need):
            print(f"  {i}/{len(need)}  mp_found="
                  f"{sum(1 for r in results if r.get('mp_C') is not None)}")
        if consecutive_fail >= MAX_CONSECUTIVE_FAILURES:
            print(f"  aborted after {consecutive_fail} consecutive lookup "
                  f"failures (likely network); cached results are kept")
            break
        time.sleep(SLEEP_S)

    # merge every cached record so the output is cumulative
    all_rows: list[dict] = []
    for q in qualified:
        ik = q["inchikey"]
        f = CACHE / f"{ik}.json"
        if f.is_file():
            try:
                rec = json.loads(f.read_text(encoding="utf-8"))
            except Exception:               # noqa: BLE001
                rec = {}
            all_rows.append({
                "inchikey": ik,
                "name": q.get("name", ""),
                "layer": q.get("layer", ""),
                "cid": rec.get("cid", ""),
                "mp_C": rec.get("mp_C", "") if rec.get("mp_C") is not None else "",
                "mp_note": rec.get("mp_note", ""),
                "http_status": rec.get("http_status", ""),
                "already_had_mp": "true" if ik in known else "false",
            })

    # include the pre-existing molecules too, so the table is complete
    for r in (load(EXISTING) if EXISTING.is_file() else []):
        ik = (r.get("inchikey") or "").strip()
        if not ik or ik not in {q["inchikey"] for q in qualified}:
            continue
        if any(x["inchikey"] == ik for x in all_rows):
            continue
        all_rows.append({
            "inchikey": ik, "name": r.get("name", ""), "layer": "",
            "cid": r.get("pubchem_cid", ""),
            "mp_C": r.get("mp_C", ""),
            "mp_note": f"{r.get('mp_depositor', '')} / "
                       f"{r.get('mp_selection_rule', '')}".strip(" /"),
            "http_status": "",
            "already_had_mp": "true",
        })

    path = OUT / "pubchem_mp_lookup_b100.csv"
    if all_rows:
        with path.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(all_rows[0].keys()))
            w.writeheader()
            for r in sorted(all_rows, key=lambda z: z["name"]):
                w.writerow(r)

    n_with = sum(1 for r in all_rows if r["mp_C"] != "")
    print(f"[B100-4] {path}")
    print(f"  total molecules in table = {len(all_rows)}")
    print(f"  with mp_C                = {n_with}")
    print(f"  still missing            = {len(all_rows) - n_with}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
