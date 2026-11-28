#!/usr/bin/env python
"""B740-01: scan the LOCAL ThermoML corpus for dielectric / density / RI records.

Structure of a ThermoML document (verified against the files, not guessed):

  <DataReport>
    <Citation>            sDOI, sTitle, sAuthor...
    <Compound>            sStandardInChIKey, sCommonName, sFormulaMolec
    <PureOrMixtureData>
      <Property>          <nPropNumber>, <ePropName> inside a typed PropertyGroup
      <Variable>          <nVarNumber>, eTemperature/ePressure wrappers
      <NumValues>         one row: several <VariableValue> (nVarNumber) and
                          <PropertyValue> (nPropNumber + nPropValue)

Key correctness points (got wrong on the first attempt, which returned 0 records):

  * property names live in typed wrapper elements, so the name is found by a
    recursive search for a tag ending in "ePropName", not by a fixed path;
  * values live inside <NumValues>, not as direct children of PropertyValue;
  * ID tags are nPropNumber / nVarNumber, NOT "VariableID"/"PropertyID";
  * a mixture is a PureOrMixtureData with >1 <Component>; pure liquids have one.

Outputs (outputs/b740_expansion/thermoml/):
  thermoml_local_scan.csv
  thermoml_coverage.json
"""

from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree as ET

REPO_ROOT = Path(__file__).resolve().parents[2]
RAW = REPO_ROOT / "data" / "raw" / "thermoml"
OUT = REPO_ROOT / "outputs" / "b740_expansion" / "thermoml"
GEN = "recover_thermoml_archive/2.0.0"

# CRITICAL: "Relative permittivity at zero frequency" is the STATIC epsilon this
# project models. "Relative permittivity at various frequencies" is a DIFFERENT
# property (dispersion) and must never be pooled with it. An earlier version of
# this map collapsed both to "dielectric_constant", which silently turned 1109
# non-static records into static labels. They are now mapped separately.
PROP_MAP = {
    "relative permittivity at zero frequency": "dielectric_constant_static",
    "static relative permittivity": "dielectric_constant_static",
    "dielectric constant": "dielectric_constant_static",
    "relative permittivity at various frequencies": "dielectric_constant_frequency_dependent",
    "relative permittivity": "dielectric_constant_frequency_dependent",
    "density": "density",
    "refractive index": "refractive_index",
    "enthalpy of vaporization": "enthalpy_of_vaporization",
    "enthalpy of vapourisation": "enthalpy_of_vaporization",
    "excess molar volume": "excess_molar_volume",
    "molar volume": "molar_volume",
}


def loc(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def text_of(el) -> str:
    return (el.text or "").strip() if el is not None and el.text else ""


def find_text(el, suffix: str) -> str:
    for e in el.iter():
        if loc(e.tag) == suffix and e.text and e.text.strip():
            return e.text.strip()
    return ""


def map_property(name: str):
    """Longest key first so 'at zero frequency' wins over the generic fallbacks."""
    low = (name or "").lower()
    for key in sorted(PROP_MAP, key=len, reverse=True):
        if key in low:
            return PROP_MAP[key]
    return None


def parse_doc(path: Path) -> dict:
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as exc:
        return {"error": str(exc), "records": []}

    doi = find_text(root, "sDOI") or path.name.split("-")[0].replace("__", "/")
    title = find_text(root, "sTitle")

    compounds = {}
    for comp in root.iter():
        if loc(comp.tag) != "Compound":
            continue
        norg = find_text(comp, "nOrgNum") or "1"
        ik = find_text(comp, "sStandardInChIKey")
        names = [text_of(c) for c in comp
                 if loc(c.tag) == "sCommonName" and text_of(c)]
        compounds[norg] = {
            "inchikey": ik,
            "name": names[0] if names else "",
            "formula": find_text(comp, "sFormulaMolec"),
        }

    records = []
    for ds in root.iter():
        if loc(ds.tag) != "PureOrMixtureData":
            continue

        comp_ids = [find_text(c, "nOrgNum") or "1" for c in ds
                    if loc(c.tag) == "Component"]
        is_mixture = len(comp_ids) > 1

        props = {}
        for p in ds:
            if loc(p.tag) != "Property":
                continue
            pnum = find_text(p, "nPropNumber")
            props[pnum] = {
                "name": find_text(p, "ePropName"),
                "phase": find_text(p, "ePropPhase"),
                "method": find_text(p, "eMethodName"),
            }
            props[pnum]["mapped"] = map_property(props[pnum]["name"])
        if not props:
            continue

        vars_ = {}
        for v in ds:
            if loc(v.tag) != "Variable":
                continue
            vnum = find_text(v, "nVarNumber")
            vtype = ""
            for e in v.iter():
                txt = text_of(e)
                if txt and ("Temperature" in txt or "Pressure" in txt
                            or "Frequency" in txt):
                    vtype = txt
                    break
            vars_[vnum] = vtype

        for nv in ds:
            if loc(nv.tag) != "NumValues":
                continue
            vvals, pvals = {}, {}
            for ch in nv:
                t = loc(ch.tag)
                if t == "VariableValue":
                    vvals[find_text(ch, "nVarNumber")] = find_text(ch, "nVarValue")
                elif t == "PropertyValue":
                    pvals[find_text(ch, "nPropNumber")] = {
                        "value": find_text(ch, "nPropValue"),
                        "uncertainty": find_text(ch, "nCombExpandUncertValue"),
                    }
            temp = press = freq = ""
            for vnum, vtype in vars_.items():
                val = vvals.get(vnum, "")
                if "Temperature" in vtype:
                    temp = val
                elif "Frequency" in vtype:
                    freq = val
                elif "Pressure" in vtype:
                    press = val
            for pnum, payload in pvals.items():
                pd = props.get(pnum, {})
                if not pd.get("mapped"):
                    continue
                cinfo = compounds.get(comp_ids[0] if comp_ids else "", {})
                records.append({
                    "doi": doi,
                    "title": title[:160],
                    "inchikey": cinfo.get("inchikey", ""),
                    "name": cinfo.get("name", ""),
                    "formula": cinfo.get("formula", ""),
                    "n_components": len(comp_ids),
                    "is_mixture": "true" if is_mixture else "false",
                    "property": pd["mapped"],
                    "property_raw": pd["name"],
                    "phase": pd["phase"],
                    "method": pd["method"],
                    "value": payload["value"],
                    "uncertainty": payload["uncertainty"],
                    "temperature_K": temp,
                    "pressure_kPa": press,
                    "frequency_hz": freq,
                    "has_frequency": "true" if freq else "false",
                    "source_file": path.name,
                })
    return {"doi": doi, "records": records}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    files = sorted(RAW.glob("*.xml"))
    all_records, per_doc, errors = [], [], []
    for f in files:
        res = parse_doc(f)
        if "error" in res:
            errors.append({"file": f.name, "error": res["error"]})
            continue
        per_doc.append({"file": f.name, "doi": res["doi"],
                        "n_records": len(res["records"]), "sha256": sha256(f)})
        all_records.extend(res["records"])

    out_csv = OUT / "thermoml_local_scan.csv"
    if all_records:
        with out_csv.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(all_records[0].keys()))
            w.writeheader()
            w.writerows(all_records)

    by_prop = Counter(r["property"] for r in all_records)
    pure = [r for r in all_records if r["is_mixture"] == "false"]
    mixt = [r for r in all_records if r["is_mixture"] == "true"]
    diesel = [r for r in pure if r["property"] == "dielectric_constant_static"]
    diesel_fd = [r for r in pure
                 if r["property"] == "dielectric_constant_frequency_dependent"]
    dens = [r for r in pure if r["property"] == "density"]
    ri = [r for r in pure if r["property"] == "refractive_index"]
    hvap = [r for r in pure if r["property"] == "enthalpy_of_vaporization"]

    ik_d = {r["inchikey"] for r in diesel if r["inchikey"]}
    ik_rho = {r["inchikey"] for r in dens if r["inchikey"]}
    ik_ri = {r["inchikey"] for r in ri if r["inchikey"]}
    ik_h = {r["inchikey"] for r in hvap if r["inchikey"]}

    doc = {
        "schema": "b740.thermoml_local_scan/v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "generator": GEN,
        "n_documents": len(files),
        "n_documents_parsed": len(per_doc),
        "n_parse_errors": len(errors),
        "parse_errors": errors[:10],
        "n_records": len(all_records),
        "records_by_property": dict(by_prop),
        "n_pure_records": len(pure),
        "n_mixture_records": len(mixt),
        "mixture_policy": ("mixture records are tagged is_mixture=true and are NEVER "
                           "used as pure-liquid epsilon labels"),
        "dielectric_static": {
            "n_pure_records": len(diesel),
            "n_unique_molecules": len(ik_d),
            "n_with_frequency_field": sum(1 for r in diesel
                                          if r["has_frequency"] == "true"),
            "definition": "Relative permittivity at zero frequency (ThermoML wording)",
        },
        "dielectric_frequency_dependent": {
            "n_pure_records": len(diesel_fd),
            "n_unique_molecules": len({r["inchikey"] for r in diesel_fd if r["inchikey"]}),
            "definition": ("Relative permittivity at various frequencies -- NOT the "
                           "static label; excluded from every modelling set"),
        },
        "density": {"n_pure_records": len(dens), "n_unique_molecules": len(ik_rho)},
        "refractive_index": {"n_pure_records": len(ri),
                             "n_unique_molecules": len(ik_ri)},
        "enthalpy_of_vaporization": {"n_pure_records": len(hvap),
                                     "n_unique_molecules": len(ik_h)},
        "molecules_with_dielectric_and_density": len(ik_d & ik_rho),
        "molecules_with_dielectric_density_and_ri": len(ik_d & ik_rho & ik_ri),
        "molecules_with_dielectric_and_hvap": len(ik_d & ik_h),
        "note_on_completeness": (
            "242 parsed documents out of the full ThermoML archive. This is a SUBSET: "
            "absence of a DOI here does not mean it is absent from ThermoML."
        ),
    }
    (OUT / "thermoml_coverage.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Wrote {out_csv}")
    print(f"Wrote {OUT / 'thermoml_coverage.json'}")
    print(f"documents: {len(files)}, parsed: {len(per_doc)}, errors: {len(errors)}")
    print(f"records: {len(all_records)}  by property: {dict(by_prop)}")
    print(f"pure: {len(pure)}, mixture: {len(mixt)}")
    print(f"dielectric STATIC: {len(diesel)} rec / {len(ik_d)} mol "
          f"({doc['dielectric_static']['n_with_frequency_field']} with frequency field)")
    print(f"dielectric FREQ-DEP: {len(diesel_fd)} rec "
          f"(excluded from static labels)")
    print(f"density: {len(dens)} rec / {len(ik_rho)} mol")
    print(f"refractive index: {len(ri)} rec / {len(ik_ri)} mol")
    print(f"enthalpy of vap: {len(hvap)} rec / {len(ik_h)} mol")
    print(f"eps+rho: {len(ik_d & ik_rho)}  eps+rho+RI: {len(ik_d & ik_rho & ik_ri)}")


if __name__ == "__main__":
    main()
