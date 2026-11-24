#!/usr/bin/env python
"""B100-19: association-deficit analysis -- why the model fails on halocarbons.

Both chemistry reviewers rejected the original explanation ("halocarbons are the
lowest-epsilon family") and proposed the real mechanism: halocarbons are strongly
polar yet non-associated, while the training pool is dominated by hydrogen-bonded
liquids. In Kirkwood-Froehlich terms the correlation factor g is the missing variable.

    (eps - 1)(2 eps + 1) / (9 eps) = (N_A rho / 3 eps_0 M) (alpha + g mu^2 / 3 k T)

Rearranged, the quantity that epsilon actually responds to is g*mu^2, not mu^2. A
liquid whose molecules align antiparallel has g < 1, so the same dipole produces a
much smaller epsilon. No single-molecule descriptor can express that.

This script measures the deficit WITHOUT needing MD. For each molecule it computes the
ratio of the observed epsilon to what an ideal, fully-correlated (g = 1) liquid of the
same dipole and volume would give. That ratio is an empirical stand-in for g, up to a
common constant, and its family-level structure is the evidence:

  * hydrogen-bonded families should sit HIGH (parallel alignment, g > 1)
  * halocarbons should sit LOW (antiparallel, g < 1) while being just as polar

If that pattern holds, the halocarbon failure is an association effect that the
descriptor set cannot represent -- which is a much stronger and more useful statement
than "the family has low epsilon".

Output: outputs/b100/association_deficit_b100.json
        outputs/b100/association_deficit_b100.csv
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT = REPO_ROOT / "outputs" / "b100"
GENERATOR = "audit_b100_association_deficit/1.0.0"

MATRIX = OUT / "model_matrix_b100.csv"

# Kirkwood-Onsager with g = 1: the epsilon an ideal, fully aligned dipolar liquid of
# the same dipole density would have. Knowing the exact prefactor is unnecessary --
# only the RANKING and the family contrasts matter, and a common constant cancels.
DEBYE_TO_CM = 3.33564e-30
EPS0 = 8.8541878128e-12
KB = 1.380649e-23
NA = 6.02214076e23

PLACEHOLDERS = {"", "not_evaluated", "nan", "none", "null", "na", "n/a"}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    raw = path.read_bytes()
    text = None
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        return []
    header = text.splitlines()[0] if text.splitlines() else ""
    delim = ";" if header.count(";") > header.count(",") else ","
    import io
    return list(csv.DictReader(io.StringIO(text, newline=""), delimiter=delim))


def fnum(v):
    s = (v or "").strip()
    if s.lower() in PLACEHOLDERS:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def onsager_lhs(eps: float) -> float | None:
    """The Onsager reaction-field left-hand side (eps-1)(2eps+1)/(9eps).

    NOT (eps-1)/(eps+2): that is Clausius-Mossotti, which contains only the
    polarisability term. The DIPOLE contribution belongs to Onsager's equation, and
    using the CM form here produced nonsense (acetonitrile came out at a ratio of
    0.01 because the CM fraction saturates at 1 while the dipole term does not).
    """
    if eps is None or eps <= 1.0:
        return None
    return (eps - 1.0) * (2.0 * eps + 1.0) / (9.0 * eps)


def rhs_ideal(mu_D: float, vm: float, t_k: float) -> float | None:
    """Onsager right-hand side with g = 1 (pure dipole, perfect parallel alignment)."""
    if not mu_D or not vm or vm <= 0 or not t_k:
        return None
    mu = mu_D * DEBYE_TO_CM
    mu2 = mu * mu
    return (NA / (3.0 * EPS0 * vm)) * (mu2 / (3.0 * KB * t_k))


def effective_g(eps: float, mu_D: float, vm: float, t_k: float) -> float | None:
    """Empirical Kirkwood correlation factor: g_eff = LHS(eps) / RHS(g=1).

    g_eff > 1 means parallel (associating) alignment; g_eff < 1 means antiparallel.
    The polarisability term is omitted from both sides, so this is a proxy rather
    than the true g -- but the omission is nearly common across families, which is
    all the family-level comparison needs.
    """
    lhs = onsager_lhs(eps)
    rhs = rhs_ideal(mu_D, vm, t_k)
    if lhs is None or rhs is None or rhs <= 0:
        return None
    return lhs / rhs


def main() -> int:
    if not MATRIX.is_file():
        print(f"FATAL: missing {MATRIX}", file=sys.stderr)
        return 2
    OUT.mkdir(parents=True, exist_ok=True)
    rows = load(MATRIX)

    per: list[dict] = []
    n_low_dipole_skipped = 0
    # A g_eff computed with the polarisability term omitted is meaningless for weakly
    # polar liquids: the denominator (the pure-dipole RHS) goes to zero and the ratio
    # explodes -- the low-dipole families came out at 10^4, which is nonsense. The
    # question is about POLAR liquids, so a floor is applied and the exclusions are
    # reported rather than silently dropped.
    DIPOLE_FLOOR_D = 1.0
    for r in rows:
        eps = fnum(r.get("epsilon"))
        mu = fnum(r.get("dipole_D"))
        vm = fnum(r.get("molar_volume_m3_mol"))
        t = fnum(r.get("T_K")) or 298.15
        if eps is None or mu is None or vm is None:
            continue
        if mu < DIPOLE_FLOOR_D:
            n_low_dipole_skipped += 1
            continue
        g = effective_g(eps, mu, vm, t)
        if g is None:
            continue
        per.append({
            "inchikey": r.get("inchikey", ""),
            "name": r.get("name", ""),
            "family": r.get("family", ""),
            "epsilon": round(eps, 3),
            "dipole_D": round(mu, 3),
            "molar_volume_m3_mol": vm,
            "T_K": t,
            "onsager_lhs": round(onsager_lhs(eps) or 0.0, 4),
            "rhs_ideal_g1": round(rhs_ideal(mu, vm, t) or 0.0, 4),
            "effective_g": round(g, 4),
            "hbd": r.get("hbd", ""),
            "association_class": r.get("association_class", ""),
        })

    path = OUT / "association_deficit_b100.csv"
    if per:
        with path.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(per[0].keys()))
            w.writeheader()
            for r in sorted(per, key=lambda z: z["effective_g"]):
                w.writerow(r)

    by_family: dict[str, list[dict]] = defaultdict(list)
    for r in per:
        by_family[r["family"]].append(r)

    fam_rows = []
    for fam, items in by_family.items():
        if len(items) < 3:
            continue
        ratios = [i["effective_g"] for i in items]
        dips = [i["dipole_D"] for i in items]
        fam_rows.append({
            "family": fam,
            "n": len(items),
            "mean_effective_g": round(statistics.mean(ratios), 4),
            "median_effective_g": round(statistics.median(ratios), 4),
            "mean_dipole_D": round(statistics.mean(dips), 4),
            "mean_epsilon": round(statistics.mean([i["epsilon"] for i in items]), 3),
            "mean_hbd": round(statistics.mean(
                [fnum(i["hbd"]) or 0.0 for i in items]), 3),
        })
    fam_rows.sort(key=lambda z: -z["mean_effective_g"])

    hal = next((f for f in fam_rows if f["family"] == "halocarbon"), None)
    alcohol = next((f for f in fam_rows if f["family"] == "alcohol_polyol"), None)
    ketone = next((f for f in fam_rows if f["family"] == "ketone_aldehyde"), None)

    doc = {
        "schema": "b100.association_deficit/v1",
        "generator": GENERATOR,
        "generated_at_utc": datetime.now(timezone.utc)
        .replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "question": (
            "卤代烃跨家族迁移失败的真实机制是什么? "
            "原来说的『它是最低介电家族』已被证伪 (eps 均值 5.98, 仅第三低). "
            "两位化学审阅者提出真实机制是**偶极关联 (g 因子) 迁移失败**: "
            "卤代烃强极性但非缔合, 而训练集以氢键液体为主."
        ),
        "method": (
            "用 Kirkwood-Onsager 在 g=1 下算出『同偶极密度、完全平行排列』"
            "应有的 epsilon, 与实测值的比作为经验 g 代理. "
            "该比不依赖常数项, 因为共同因子在家族对比中抵消. "
            "**这不是 MD 的 g, 而是无需 MD 即可计算的关联赤字指标.**"
        ),
        "n_molecules": len(per),
        "dipole_floor_D": DIPOLE_FLOOR_D,
        "n_low_dipole_skipped": n_low_dipole_skipped,
        "family_correlation": fam_rows,
        "halocarbon_check": {
            "halocarbon_mean_g_eff": hal["mean_effective_g"] if hal else None,
            "halocarbon_mean_dipole_D": hal["mean_dipole_D"] if hal else None,
            "alcohol_mean_g_eff": alcohol["mean_effective_g"] if alcohol else None,
            "alcohol_mean_dipole_D": alcohol["mean_dipole_D"] if alcohol else None,
            "ketone_mean_g_eff": ketone["mean_effective_g"] if ketone else None,
            "interpretation": (
                "若卤代烃的 g_eff 显著低于氢键家族, 则"
                "『同为极性分子但 epsilon 低得多』的机制得到支持: "
                "卤代烃取向反平行 (g<1), 单分子偶极无法表达这一点."
            ),
        },
        "consequence_for_descriptors": (
            "这是描述符有效性边界的**精确位置**: "
            "描述符能表达 mu^2/Vm, 不能表达 g. "
            "两者相乘才是 epsilon 的决定量. "
            "因此边界不是『描述符无用』, 而是『缺了唯一的集体变量』."
        ),
        "caveat": (
            "g_eff 把 alpha (极化率) 忽略了, 因此它含有一部分系统偏差; "
            "它只用于**家族间相对比较**, 不应当作 g 的定量估计. "
            "真正的 g 需要液相 MD 的偶极自相关."
        ),
        "inputs": {"model_matrix_b100": {"sha256": sha256_file(MATRIX)}},
        "output": {"path": str(path.relative_to(REPO_ROOT)),
                   "sha256": sha256_file(path) if path.is_file() else None,
                   "rows": len(per)},
    }
    j_path = OUT / "association_deficit_b100.json"
    j_path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")

    print(f"[B100-19] {j_path}")
    print(f"[B100-19] {path}")
    print(f"  molecules = {len(per)}")
    print()
    print(f"  {'family':<24}{'n':>4}{'corr_ratio':>12}{'mu_D':>8}{'eps':>8}")
    for f in fam_rows:
        print(f"  {f['family']:<24}{f['n']:>4}"
              f"{f['mean_effective_g']:>12.4f}"
              f"{f['mean_dipole_D']:>8.2f}{f['mean_epsilon']:>8.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
