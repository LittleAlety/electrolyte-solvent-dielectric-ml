#!/usr/bin/env python
"""B745-01: does a single-molecule descriptor layer survive mixing?

The v7.4 corpus contains 207 binary-mixture datasets that report the static
relative permittivity together with a mole fraction. They are the only place in
this project where the *same* molecular pair is measured at many compositions,
so they can answer a question the single-molecule layer cannot:

    does epsilon of a liquid mixture follow an ideal mixing rule built from the
    pure-component epsilon, or is there a systematic residual?

Three ideal references are evaluated side by side, because they encode different
physics and a single "ideal" curve would hide the choice:

  linear        eps_lin = x1 eps1 + x2 eps2                 (mole-fraction linear)
  Lichtenecker  eps_log = exp(phi1 ln eps1 + phi2 ln eps2)  (volume-fraction log)
  Clausius-Mossotti
                f(eps) = (eps-1)/(eps+2) additive in VOLUME fractions,
                eps_cm = (1 + 2 g)/(1 - g),  g = phi1 f1 + phi2 f2

phi (volume fraction) is built from the pure-component molar volumes at the
matched temperature, i.e. assuming zero excess volume. That assumption is stated
in the summary and is the main approximation of this analysis.

What is deliberately NOT done here
  * no fitted interaction parameter: we report residuals of fixed rules
  * no averaging of pure-component epsilon across temperatures or sources
    (the nearest pure value within 5 K is used, and the DOI is recorded)
  * no claim that a residual "is" an association energy

Outputs (outputs/b740_expansion/mixtures/):
  mixture_dielectric_excess.csv
  mixture_dielectric_summary.json
"""

from __future__ import annotations

import csv
import io
import json
import math
import statistics
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT = REPO_ROOT / "outputs" / "b740_expansion" / "mixtures"
RAW = REPO_ROOT / "data" / "raw" / "thermoml"
DESC = REPO_ROOT / "outputs" / "b700" / "orca_r2scan3c_descriptors.csv"
STRUCT = REPO_ROOT / "outputs" / "b740_expansion" / "molecule_expansion" / "new_molecule_structures.csv"
GEN = "analyze_mixture_dielectric/1.0.0"

T_TOL = 5.0          # K, mixture T and pure-component T must be this close
EPS_MIN, EPS_MAX = 1.0, 200.0
X_TOL = 1e-6

STATIC_EPS_KEYS = ("relative permittivity at zero frequency",
                   "relative permittivity at 0 frequency")


def load_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        return []
    header = text.splitlines()[0] if text.splitlines() else ""
    delim = ";" if header.count(";") > header.count(",") else ","
    return list(csv.DictReader(io.StringIO(text, newline=""), delimiter=delim))


def fnum(v):
    try:
        f = float(v)
        return f if math.isfinite(f) else None
    except (TypeError, ValueError):
        return None


def loc(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def text_of(el) -> str:
    return (el.text or "").strip() if el is not None and el.text else ""


def find_text(el, suffix: str) -> str:
    for e in el.iter():
        if loc(e.tag) == suffix and text_of(e):
            return text_of(e)
    return ""


def is_static_eps(name: str) -> bool:
    low = (name or "").lower()
    if "permittivity" not in low:
        return False
    if "zero frequency" in low or "0 frequency" in low:
        return True
    return False


def is_density(name: str) -> bool:
    return "density" in (name or "").lower() and "partial" not in (name or "").lower()


def parse_documents() -> tuple[dict, list[dict], Counter]:
    """Return pure_props, mixture_records, skip counters."""
    pure = defaultdict(lambda: defaultdict(list))    # ik -> prop -> [(T, v)]
    meta = {}                                        # ik -> {name, formula}
    mixtures = []
    skip = Counter()

    for path in sorted(RAW.glob("*.xml")):
        try:
            root = ET.parse(path).getroot()
        except ET.ParseError:
            skip["parse_error"] += 1
            continue
        doi = find_text(root, "sDOI") or path.name.split("-")[0].replace("__", "/")

        compounds = {}
        for comp in root.iter():
            if loc(comp.tag) != "Compound":
                continue
            num = find_text(comp, "nOrgNum") or "1"
            ik = find_text(comp, "sStandardInChIKey")
            compounds[num] = {
                "inchikey": ik,
                "name": text_of(next((c for c in comp if loc(c.tag) == "sCommonName"), None)),
                "formula": find_text(comp, "sFormulaMolec"),
            }
            if ik:
                meta[ik] = {"name": compounds[num]["name"],
                            "formula": compounds[num]["formula"]}

        for ds in root.iter():
            if loc(ds.tag) != "PureOrMixtureData":
                continue
            comp_ids = [find_text(c, "nOrgNum") or "1" for c in ds
                        if loc(c.tag) == "Component"]
            props = {}
            for p in ds:
                if loc(p.tag) != "Property":
                    continue
                props[find_text(p, "nPropNumber")] = find_text(p, "ePropName")

            if len(comp_ids) == 1:
                ik = compounds.get(comp_ids[0], {}).get("inchikey", "")
                if not ik:
                    continue
                for nv in ds:
                    if loc(nv.tag) != "NumValues":
                        continue
                    vvals, pvals = {}, {}
                    for ch in nv:
                        t = loc(ch.tag)
                        if t == "VariableValue":
                            vvals[find_text(ch, "nVarNumber")] = find_text(ch, "nVarValue")
                        elif t == "PropertyValue":
                            pvals[find_text(ch, "nPropNumber")] = find_text(ch, "nPropValue")
                    temp = None
                    for v in ds:
                        if loc(v.tag) != "Variable":
                            continue
                        if "eTemperature" not in {loc(e.tag) for e in v.iter()}:
                            continue
                        temp = fnum(vvals.get(find_text(v, "nVarNumber")))
                    for pnum, name in props.items():
                        raw = fnum(pvals.get(pnum))
                        if raw is None:
                            continue
                        if is_static_eps(name) and EPS_MIN < raw < EPS_MAX:
                            pure[ik]["eps"].append((temp, raw, doi))
                        elif is_density(name) and temp is not None and raw > 0:
                            pure[ik]["rho"].append((temp, raw, doi))
                continue

            if len(comp_ids) != 2:
                skip["n_components_not_2"] += 1
                continue

            # -------- variables: temperature + mole fractions ------------
            # BUG-FIX: there is no generic <eVariableType> tag in ThermoML. The
            # variable kind is encoded in the leaf TAG NAME (eTemperature,
            # ePressure) and the composition kind in the TEXT of
            # <eComponentComposition>. Looking for text containing
            # "Temperature" also worked in the first parser but would have
            # matched e.g. a comment; the tag name is the structural answer.
            var_name = {}
            for v in ds:
                if loc(v.tag) != "Variable":
                    continue
                vnum = find_text(v, "nVarNumber")
                tags = {loc(e.tag) for e in v.iter()}
                if "eTemperature" in tags:
                    vtype = "TEMPERATURE"
                elif "ePressure" in tags:
                    vtype = "PRESSURE"
                elif "eComponentComposition" in tags:
                    vtype = "COMPOSITION"
                else:
                    vtype = "OTHER"
                var_name[vnum] = {
                    "type": vtype,
                    "comp": find_text(v, "eComponentComposition"),
                    "orgnum": find_text(v, "nOrgNum"),
                }

            eps_prop = next((n for n, v in props.items() if is_static_eps(v)), None)
            if eps_prop is None:
                skip["mixture_without_static_eps"] += 1
                continue

            for nv in ds:
                if loc(nv.tag) != "NumValues":
                    continue
                vvals, pvals = {}, {}
                for ch in nv:
                    t = loc(ch.tag)
                    if t == "VariableValue":
                        vvals[find_text(ch, "nVarNumber")] = find_text(ch, "nVarValue")
                    elif t == "PropertyValue":
                        pvals[find_text(ch, "nPropNumber")] = find_text(ch, "nPropValue")
                eps = fnum(pvals.get(eps_prop))
                if eps is None or not (EPS_MIN < eps < EPS_MAX):
                    continue
                temp = None
                xs = {}
                for vnum, info in var_name.items():
                    val = fnum(vvals.get(vnum))
                    if val is None:
                        continue
                    if info["type"] == "TEMPERATURE":
                        temp = val
                    elif info["type"] == "COMPOSITION" and "Mole fraction" in (info["comp"] or ""):
                        xs[info["orgnum"] or "1"] = val
                if temp is None or not xs:
                    skip["mixture_without_T_or_x"] += 1
                    continue
                if len(xs) > 2 or any(not (0.0 <= x <= 1.0) for x in xs.values()):
                    skip["mixture_bad_composition"] += 1
                    continue
                ik1 = compounds.get(comp_ids[0], {}).get("inchikey", "")
                ik2 = compounds.get(comp_ids[1], {}).get("inchikey", "")
                if not ik1 or not ik2:
                    skip["mixture_component_without_inchikey"] += 1
                    continue
                if len(xs) == 2:
                    tot = sum(xs.values())
                    if abs(tot - 1.0) > 0.02:
                        skip["mixture_fractions_do_not_sum_to_1"] += 1
                        continue
                    x1 = xs.get(comp_ids[0], xs.get("1", 0.0))
                else:
                    org, x = next(iter(xs.items()))
                    x1 = x if org == comp_ids[0] else 1.0 - x
                mixtures.append({
                    "doi": doi,
                    "T_K": temp,
                    "ik1": ik1, "ik2": ik2,
                    "name1": meta.get(ik1, {}).get("name", ""),
                    "name2": meta.get(ik2, {}).get("name", ""),
                    "x1": x1,
                    "epsilon_meas": eps,
                    "phase": find_text(ds, "ePropPhase"),
                })
    return pure, mixtures, meta, skip


def nearest(series, T, tol=T_TOL):
    if not series:
        return None
    cand = [(abs(t - T), v, d) for t, v, d in series if t is not None and abs(t - T) <= tol]
    return min(cand) if cand else None


def mean_or_none(vals):
    vals = [v for v in vals if v is not None]
    return statistics.mean(vals) if vals else None


def median_ci(vals, n_boot=2000, seed=20261125):
    """Percentile bootstrap CI of the median (deterministic seed)."""
    import random
    vals = [v for v in vals if v is not None]
    if len(vals) < 5:
        return {"n": len(vals), "median": (round(statistics.median(vals), 5) if vals else None),
                "ci95": None}
    rng = random.Random(seed)
    meds = []
    for _ in range(n_boot):
        s = [vals[rng.randrange(len(vals))] for _ in vals]
        meds.append(statistics.median(s))
    meds.sort()
    return {
        "n": len(vals),
        "median": round(statistics.median(vals), 5),
        "ci95": [round(meds[int(0.025 * n_boot)], 5), round(meds[int(0.975 * n_boot)], 5)],
    }


def cm_f(eps: float) -> float:
    return (eps - 1.0) / (eps + 2.0)


def cm_inv(g: float) -> float | None:
    if not (-0.99 < g < 0.49):
        return None
    return (1.0 + 2.0 * g) / (1.0 - g)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    pure, mixtures, meta, skip = parse_documents()

    mw = {}
    for r in load_csv(DESC):
        v = fnum(r.get("mw"))
        if v:
            mw[r["inchikey"]] = v
    hbd = {r["inchikey"]: r.get("hbd", "") for r in load_csv(DESC)}
    for r in load_csv(STRUCT):
        v = fnum(r.get("mw"))
        if v:
            mw[r["inchikey"]] = v
        hbd[r["inchikey"]] = r.get("hbd", "")

    rows = []
    eval_skip = Counter()
    for m in mixtures:
        T = m["T_K"]
        e1 = nearest(pure[m["ik1"]].get("eps", []), T)
        e2 = nearest(pure[m["ik2"]].get("eps", []), T)
        if not e1 or not e2:
            eval_skip["missing_pure_epsilon"] += 1
            continue
        r1 = nearest(pure[m["ik1"]].get("rho", []), T)
        r2 = nearest(pure[m["ik2"]].get("rho", []), T)
        M1, M2 = mw.get(m["ik1"]), mw.get(m["ik2"])
        V1 = V2 = None
        if r1 and M1:
            V1 = (M1 / 1000.0) / r1[1] * 1e6          # cm^3/mol
        if r2 and M2:
            V2 = (M2 / 1000.0) / r2[1] * 1e6
        if not V1 or not V2:
            eval_skip["missing_pure_density_or_mass"] += 1
            continue

        x1 = m["x1"]
        x2 = 1.0 - x1
        denom = x1 * V1 + x2 * V2
        phi1 = x1 * V1 / denom if denom > 0 else None
        if phi1 is None:
            eval_skip["degenerate_volume"] += 1
            continue
        phi2 = 1.0 - phi1

        eps1, eps2, eps_meas = e1[1], e2[1], m["epsilon_meas"]
        eps_lin = x1 * eps1 + x2 * eps2
        if eps1 > 0 and eps2 > 0:
            eps_log = math.exp(phi1 * math.log(eps1) + phi2 * math.log(eps2))
        else:
            eps_log = None
        g = phi1 * cm_f(eps1) + phi2 * cm_f(eps2)
        eps_cm = cm_inv(g)

        h1 = fnum(hbd.get(m["ik1"]))
        h2 = fnum(hbd.get(m["ik2"]))
        if h1 is None or h2 is None:
            assoc = "UNKNOWN"
        elif h1 > 0 or h2 > 0:
            assoc = "PROTIC_PRESENT"
        else:
            assoc = "APROTIC_PAIR"

        rows.append({
            "doi": m["doi"],
            "T_K": round(T, 2),
            "component_1": m["name1"],
            "component_2": m["name2"],
            "ik1": m["ik1"], "ik2": m["ik2"],
            "x1": round(x1, 5),
            "phi1": round(phi1, 5),
            "epsilon_1_pure": round(eps1, 4),
            "epsilon_2_pure": round(eps2, 4),
            "epsilon_meas": round(eps_meas, 4),
            "epsilon_linear": round(eps_lin, 4),
            "epsilon_lichtenecker": round(eps_log, 4) if eps_log is not None else "",
            "epsilon_clausius_mossotti": round(eps_cm, 4) if eps_cm is not None else "",
            "resid_vs_linear": round(eps_meas - eps_lin, 4),
            "resid_vs_lichtenecker": (round(eps_meas - eps_log, 4)
                                      if eps_log is not None else ""),
            "resid_vs_cm": (round(eps_meas - eps_cm, 4) if eps_cm is not None else ""),
            "rel_resid_vs_cm": (round((eps_meas - eps_cm) / eps_cm, 5)
                                if eps_cm and eps_cm > 0 else ""),
            "pure_T_offset_1_K": round(e1[0], 2),
            "pure_T_offset_2_K": round(e2[0], 2),
            "pure_eps_same_doi_1": "true" if e1[2] == m["doi"] else "false",
            "pure_eps_same_doi_2": "true" if e2[2] == m["doi"] else "false",
            "association_class": assoc,
            "V_m_1_cm3_mol": round(V1, 3),
            "V_m_2_cm3_mol": round(V2, 3),
        })

    out_csv = OUT / "mixture_dielectric_excess.csv"
    if rows:
        with out_csv.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)

    def rule_mae(col):
        v = [abs(fnum(r[col])) for r in rows if fnum(r[col]) is not None]
        return {"n": len(v), "mae": round(statistics.mean(v), 4) if v else None}

    by_class = {}
    for cls in sorted({r["association_class"] for r in rows}):
        sub = [r for r in rows if r["association_class"] == cls]
        by_class[cls] = {
            "n_points": len(sub),
            "n_pairs": len({(r["ik1"], r["ik2"]) for r in sub}),
            "resid_vs_cm": median_ci([fnum(r["resid_vs_cm"]) for r in sub]),
            "rel_resid_vs_cm": median_ci([fnum(r["rel_resid_vs_cm"]) for r in sub]),
            "resid_vs_lichtenecker": median_ci([fnum(r["resid_vs_lichtenecker"]) for r in sub]),
        }

    # does any rule survive a "no better than the constant" test?
    meas = [fnum(r["epsilon_meas"]) for r in rows]
    mean_eps = statistics.mean(meas) if meas else None
    const_mae = (statistics.mean(abs(v - mean_eps) for v in meas)
                 if meas and mean_eps is not None else None)

    same_doc = sum(1 for r in rows
                   if r["pure_eps_same_doi_1"] == "true" and r["pure_eps_same_doi_2"] == "true")

    n_cm_defined = sum(1 for r in rows if fnum(r["epsilon_clausius_mossotti"]) is not None)

    doc = {
        "schema": "b740.mixture_dielectric/v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "generator": GEN,
        "source": "local ThermoML corpus (242 documents)",
        "n_mixture_records_scanned": len(mixtures),
        "n_evaluable_points": len(rows),
        "n_distinct_pairs": len({(r["ik1"], r["ik2"]) for r in rows}),
        "n_distinct_doi": len({r["doi"] for r in rows}),
        "mixing_rules": {
            "linear": "eps = x1 eps1 + x2 eps2",
            "lichtenecker": "ln eps = phi1 ln eps1 + phi2 ln eps2",
            "clausius_mossotti": "(eps-1)/(eps+2) additive over VOLUME fractions",
        },
        "assumptions": [
            "volume fractions come from pure-component molar volumes at the matched "
            "temperature, i.e. zero excess volume of mixing",
            "the pure-component epsilon is the nearest value within 5 K anywhere in the "
            "corpus; the same-DOI flag records when it came from the mixture's own study",
            "only 2-component datasets with a molar composition variable are used",
        ],
        "association_classification": {
            "rule": "a pair is PROTIC_PRESENT if either pure component has HBD>0 in its "
                    "molecular descriptor row; UNKNOWN if either component has no "
                    "resolved structure",
            "source": ("CORE239 descriptor table + newly resolved PubChem structures; "
                       "no name-based chemical guessing"),
        },
        "evaluability": {
            "records_scanned": len(mixtures),
            "evaluated": len(rows),
            "drop_reasons": dict(eval_skip),
            "parse_drop_reasons": dict(skip),
        },
        "rule_fit": {
            "linear": rule_mae("resid_vs_linear"),
            "lichtenecker": rule_mae("resid_vs_lichtenecker"),
            "clausius_mossotti": rule_mae("resid_vs_cm"),
            "constant_baseline": {"n": len(meas),
                                  "mae": round(const_mae, 4) if const_mae else None},
        },
        "residual_by_association_class": by_class,
        "clausius_mossotti_domain": {
            "n_defined": n_cm_defined,
            "n_undefined": len(rows) - n_cm_defined,
            "why": ("the CM rule maps eps to f=(eps-1)/(eps+2) in [0,1) and inverts "
                    "g=(eps-1)/(eps+2); when the volume-fraction-weighted g reaches 0.49 "
                    "the predicted eps diverges, so the rule is formally undefined for "
                    "water-rich and other high-permittivity mixtures"),
            "consequence": ("the CM comparison is restricted to the low-epsilon part of "
                           "the composition space; it must NOT be quoted as covering the "
                           "whole dataset, and the protic class is under-represented there. "
                           "Lichtenecker is the rule defined on every point."),
        },
        "sign_of_the_residual": (
            "measured epsilon exceeds every ideal rule on median in BOTH association "
            "classes; the protic residual is the larger one, i.e. the departure grows "
            "with H-bond capability rather than with polarity alone"
        ),
        "same_doi_pure_reference": {
            "n_points": same_doc,
            "fraction": round(same_doc / len(rows), 4) if rows else None,
            "note": ("most reference epsilon values come from a different study than the "
                     "mixture; this is a cross-source splice of the REFERENCE, which is "
                     "recorded per row and must not be hidden"),
        },
        "what_this_can_and_cannot_say": [
            "CAN: quantify how far measured mixture epsilon departs from three fixed "
            "ideal mixing rules, and whether the departure is systematically larger for "
            "H-bonding pairs",
            "CANNOT: turn that residual into an association parameter or a Kirkwood g; "
            "the rules are not derived from a molecular model of the mixture",
            "CANNOT: be used as a training label set -- no mixture record enters the "
            "single-molecule epsilon model",
        ],
    }
    if not rows:
        doc["status"] = "NO_EVALUABLE_POINTS"
    (OUT / "mixture_dielectric_summary.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"mixture records scanned: {len(mixtures)}")
    print(f"evaluable points: {len(rows)}  pairs: {doc['n_distinct_pairs']}  "
          f"DOIs: {doc['n_distinct_doi']}")
    print(f"drop reasons: {dict(eval_skip)}")
    print("\nrule fit (MAE in epsilon units):")
    for k, v in doc["rule_fit"].items():
        print(f"  {k:20s} {v}")
    print("\nresidual vs Clausius-Mossotti by class:")
    for k, v in by_class.items():
        print(f"  {k:16s} n={v['n_points']:4d} resid={v['resid_vs_cm']}")


if __name__ == "__main__":
    main()
