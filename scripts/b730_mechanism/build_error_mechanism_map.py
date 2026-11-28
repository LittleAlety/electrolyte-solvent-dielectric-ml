#!/usr/bin/env python
"""B734-01: molecule-level error mechanism map for all 239 molecules.

The v7.1 E4 diagnostics produced ONE dominant mechanism per family. That is too
coarse: a family can fail for two reasons at once, and a molecule can carry
several independent problems. This builds a per-molecule table where each row can
carry MULTIPLE mechanism tags, computed from data rather than assigned by hand:

  TARGET_EXTRAPOLATION    epsilon above the training-set 95th percentile
                          (the model must extrapolate upward, not interpolate)
  STRUCTURAL_EXTRAPOLATION nearest-neighbour distance > pool 90th percentile
  LEVEL_BIAS_FAMILY       family-level mean residual large relative to its sd
  RANKING_FAILURE_FAMILY  within-family Spearman < 0.3
  CONFORMER_SENSITIVE     C_mu > 0.5 (only for the 39 conformer molecules)
  ASSOCIATION_HEAVY       hbd+hba >= 2 (hydrogen-bond network not representable)
  LOW_POLARITY_HIGH_EPS   eps >= 20 while mu < 0.5 D (physics the dipole misses)

Tags are not mutually exclusive and no molecule is called "an outlier": the map
is a description of WHICH mechanism is in play, with the raw evidence attached so
a reader can disagree with the tagging.

Outputs (outputs/b730_mechanism/error_mechanism/):
  molecule_error_mechanism_map.csv
  mechanism_summary.json
"""

from __future__ import annotations

import csv
import io
import json
import math
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT = REPO_ROOT / "outputs" / "b730_mechanism" / "error_mechanism"
GEN = "build_error_mechanism_map/1.0.0"

DESC = REPO_ROOT / "outputs" / "b700" / "orca_r2scan3c_descriptors.csv"
LOFO = REPO_ROOT / "outputs" / "b700" / "B706_E4_lofo_predictions.csv"
CONF = REPO_ROOT / "outputs" / "b730_mechanism" / "conformer_mechanism" / "conformer_dipole_statistics.csv"
PHYS = REPO_ROOT / "outputs" / "b730_mechanism" / "dielectric_physics" / "dielectric_physics_decomposition.csv"

STRUCT_COLS = ["heavy_atom_count", "hbd", "hba", "tpsa_A2", "molar_volume_m3_mol",
               "formal_charge", "n_rings", "n_rotatable", "fraction_csp3",
               "n_aromatic_atoms", "n_hetero", "n_halogen", "morgan2_nbits", "mw"]


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
    except Exception:
        return None


def spearman(a, b):
    n = len(a)
    if n < 3:
        return None

    def rk(v):
        o = sorted(range(n), key=lambda i: v[i])
        r = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and v[o[j + 1]] == v[o[i]]:
                j += 1
            av = (i + j) / 2.0 + 1
            for k in range(i, j + 1):
                r[o[k]] = av
            i = j + 1
        return r

    ra, rb = rk(a), rk(b)
    ma, mb = sum(ra) / n, sum(rb) / n
    num = sum((ra[i] - ma) * (rb[i] - mb) for i in range(n))
    da = math.sqrt(sum((v - ma) ** 2 for v in ra))
    db = math.sqrt(sum((v - mb) ** 2 for v in rb))
    return num / (da * db) if da and db else None


def pct(vals, p):
    s = sorted(vals)
    if not s:
        return None
    return s[min(int(p * (len(s) - 1)), len(s) - 1)]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    desc = {r["inchikey"]: r for r in load_csv(DESC)}
    lofo = {r["inchikey"]: r for r in load_csv(LOFO)}
    conf = {r["inchikey"]: r for r in load_csv(CONF)}
    phys = {r["inchikey"]: r for r in load_csv(PHYS)}

    # ---------------- standardised structural space for NN distance --------
    pool, ids = [], []
    for ik, d in desc.items():
        xs, ok = [], True
        for c in STRUCT_COLS:
            v = fnum(d.get(c))
            if v is None:
                ok = False
                break
            xs.append(v)
        if ok:
            pool.append(xs)
            ids.append(ik)
    means = [statistics.mean([p[j] for p in pool]) for j in range(len(pool[0]))]
    sds = [statistics.pstdev([p[j] for p in pool]) or 1.0 for j in range(len(pool[0]))]
    Z = {ik: [(pool[i][j] - means[j]) / sds[j] for j in range(len(pool[0]))]
         for i, ik in enumerate(ids)}
    nn = {}
    for ik, z in Z.items():
        best = float("inf")
        for other, zo in Z.items():
            if other == ik:
                continue
            dd = math.sqrt(sum((z[j] - zo[j]) ** 2 for j in range(len(z))))
            best = min(best, dd)
        nn[ik] = best

    eps_vals = [fnum(d.get("epsilon")) for d in desc.values()]
    eps_vals = [v for v in eps_vals if v is not None]
    eps_p95 = pct(eps_vals, 0.95)
    nn_p90 = pct(list(nn.values()), 0.90)

    # ---------------- family-level statistics -----------------------------
    by_fam = defaultdict(list)
    for ik, r in lofo.items():
        by_fam[r["family"]].append(r)
    fam_stats = {}
    for fam, rs in by_fam.items():
        e = [fnum(r["epsilon"]) for r in rs]
        p = [fnum(r["lofo_pred"]) for r in rs]
        prs = [(a, b) for a, b in zip(e, p) if a is not None and b is not None]
        if len(prs) < 3:
            continue
        yy = [q[0] for q in prs]
        pp = [q[1] for q in prs]
        resid = [pp[i] - yy[i] for i in range(len(yy))]
        bias = statistics.mean(resid)
        sd = statistics.pstdev(resid) if len(resid) > 1 else 0.0
        fam_stats[fam] = {
            "n": len(prs),
            "bias": bias,
            "resid_sd": sd,
            "bias_ratio": abs(bias) / sd if sd else None,
            "spearman": spearman(yy, pp),
            "mae": statistics.mean(abs(v) for v in resid),
        }

    # ---------------- per-molecule map ------------------------------------
    rows = []
    for ik, d in desc.items():
        eps = fnum(d.get("epsilon"))
        mu = fnum(d.get("dipole_D_v7"))
        fam = d.get("family", "")
        lr = lofo.get(ik, {})
        resid = fnum(lr.get("resid"))
        pred = fnum(lr.get("lofo_pred"))
        hbd = fnum(d.get("hbd")) or 0
        hba = fnum(d.get("hba")) or 0
        cmu = fnum(conf.get(ik, {}).get("C_mu"))
        g = fnum(phys.get(ik, {}).get("apparent_gk"))

        tags = []
        evidence = {}

        if eps is not None and eps_p95 is not None and eps > eps_p95:
            tags.append("TARGET_EXTRAPOLATION")
            evidence["eps_vs_p95"] = f"{eps:.2f} > {eps_p95:.2f}"

        if nn.get(ik) is not None and nn_p90 is not None and nn[ik] > nn_p90:
            tags.append("STRUCTURAL_EXTRAPOLATION")
            evidence["nn_vs_p90"] = f"{nn[ik]:.3f} > {nn_p90:.3f}"

        fs = fam_stats.get(fam)
        if fs and fs["bias_ratio"] is not None and fs["bias_ratio"] > 0.7:
            tags.append("LEVEL_BIAS_FAMILY")
            evidence["family_bias"] = round(fs["bias"], 3)
        if fs and fs["spearman"] is not None and fs["spearman"] < 0.3:
            tags.append("RANKING_FAILURE_FAMILY")
            evidence["family_spearman"] = round(fs["spearman"], 3)

        if cmu is not None and cmu > 0.5:
            tags.append("CONFORMER_SENSITIVE")
            evidence["C_mu"] = round(cmu, 3)

        if hbd + hba >= 2:
            tags.append("ASSOCIATION_HEAVY")
            evidence["hbd_plus_hba"] = int(hbd + hba)

        if eps is not None and mu is not None and eps >= 20 and mu < 0.5:
            tags.append("LOW_POLARITY_HIGH_EPS")
            evidence["eps_mu"] = f"eps={eps:.1f}, mu={mu:.2f}"

        rows.append({
            "inchikey": ik,
            "name": d.get("name", ""),
            "family": fam,
            "epsilon": eps if eps is not None else "",
            "lofo_pred": pred if pred is not None else "",
            "residual": resid if resid is not None else "",
            "abs_residual": round(abs(resid), 4) if resid is not None else "",
            "nn_distance": round(nn[ik], 4) if ik in nn else "",
            "dipole_D": mu if mu is not None else "",
            "polarizability_au": fnum(d.get("polarizability_au_v7")) or "",
            "C_mu": cmu if cmu is not None else "",
            "apparent_gk": g if g is not None else "",
            "hbd": int(hbd),
            "hba": int(hba),
            "n_rotatable": fnum(d.get("n_rotatable")) or "",
            "molecular_volume_A3": fnum(d.get("molecular_volume_A3")) or "",
            "n_mechanism_tags": len(tags),
            "mechanism_tags": ";".join(tags) if tags else "NONE",
            "evidence": json.dumps(evidence, ensure_ascii=False),
        })

    out_csv = OUT / "molecule_error_mechanism_map.csv"
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    # ---------------- summary ---------------------------------------------
    tag_counts = Counter()
    for r in rows:
        if r["mechanism_tags"] == "NONE":
            tag_counts["NONE"] += 1
        else:
            for t in r["mechanism_tags"].split(";"):
                tag_counts[t] += 1

    with_resid = [r for r in rows if r["abs_residual"] != ""]
    big = sorted(with_resid, key=lambda r: -float(r["abs_residual"]))[:20]
    tag_by_fam = defaultdict(Counter)
    for r in rows:
        if r["mechanism_tags"] == "NONE":
            continue
        for t in r["mechanism_tags"].split(";"):
            tag_by_fam[r["family"]][t] += 1

    doc = {
        "schema": "b730.error_mechanism_map/v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "generator": GEN,
        "n_molecules": len(rows),
        "tag_definitions": {
            "TARGET_EXTRAPOLATION": f"epsilon > pool 95th percentile ({eps_p95:.2f})",
            "STRUCTURAL_EXTRAPOLATION": f"NN distance > pool 90th percentile ({nn_p90:.3f})",
            "LEVEL_BIAS_FAMILY": "family |bias|/sd > 0.7",
            "RANKING_FAILURE_FAMILY": "family Spearman < 0.3",
            "CONFORMER_SENSITIVE": "C_mu > 0.5 (39 conformer molecules only)",
            "ASSOCIATION_HEAVY": "hbd+hba >= 2",
            "LOW_POLARITY_HIGH_EPS": "eps >= 20 with mu < 0.5 D",
        },
        "tags_are_not_exclusive": True,
        "tag_counts": dict(tag_counts),
        "families_with_mechanisms": {k: dict(v) for k, v in tag_by_fam.items()},
        "family_statistics": {k: {kk: (round(vv, 4) if isinstance(vv, float) else vv)
                                  for kk, vv in v.items()}
                              for k, v in fam_stats.items()},
        "top20_abs_residual": [
            {"name": r["name"], "family": r["family"],
             "abs_residual": r["abs_residual"], "tags": r["mechanism_tags"]}
            for r in big],
        "n_with_no_mechanism_tag": tag_counts.get("NONE", 0),
        "interpretation_guard": (
            "a molecule with a tag is not an error case; the tag says WHICH mechanism "
            "is in play. TARGET_EXTRAPOLATION in particular is a property of the label "
            "distribution, not of the molecule."
        ),
    }
    (OUT / "mechanism_summary.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Wrote {out_csv}")
    print(f"Wrote {OUT / 'mechanism_summary.json'}")
    print(f"n = {len(rows)}")
    print(f"eps p95 = {eps_p95:.2f}, NN p90 = {nn_p90:.3f}")
    print()
    print("tag counts:")
    for t, c in tag_counts.most_common():
        print(f"  {t:26s} {c}")
    print()
    print("top 12 |residual|:")
    for r in big[:12]:
        print(f"  {r['name'][:30]:30s} {r['family'][:18]:18s} "
              f"|res|={r['abs_residual']:>8}  {r['mechanism_tags']}")


if __name__ == "__main__":
    main()
