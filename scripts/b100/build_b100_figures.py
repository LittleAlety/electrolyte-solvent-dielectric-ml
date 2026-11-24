#!/usr/bin/env python
"""B100-16: generate the eight chart types required by PLAN B v6.0 §8.

Required charts:
  1. 家族覆盖率图            family coverage vs target bands
  2. 介电常数分布图          epsilon distribution
  3. xTB-DFT 对照图          BLOCKED (no DFT) -- emitted as an explicit placeholder
  4. 构象效应图              conformer effect on dipole
  5. 适用域边界图            error vs structural similarity
  6. MD 偶极关联图           BLOCKED (no MD) -- explicit placeholder
  7. MAE 与 Top-k regret 对照  error vs screening benefit
  8. 计算失败与补救记录图    computation status / failure record

Charts that cannot be drawn are drawn as a labelled "NOT COMPUTED" panel with the
reason, rather than silently skipped: a missing figure invites the reader to assume it
was never attempted, while a placeholding figure states that the underlying
calculation is unavailable in this environment.

Pure matplotlib, no seaborn, no external assets.
"""

from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT = REPO_ROOT / "outputs" / "b100"
FIG = OUT / "figures"
GENERATOR = "build_b100_figures/1.0.0"


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


def jload(p: Path):
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else None


def fnum(v):
    s = (v or "").strip()
    if s.lower() in ("", "nan", "none", "null", "na", "n/a"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def setup():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    # Prefer a CJK-capable font when one exists; fall back silently so the script
    # runs on a bare system. Labels degrade to boxes only in the fallback case.
    for name in ("Microsoft YaHei", "SimHei", "DejaVu Sans"):
        try:
            if any(name.lower() in f.name.lower()
                   for f in font_manager.fontManager.ttflist):
                plt.rcParams["font.sans-serif"] = [name, "DejaVu Sans"]
                break
        except Exception:                   # noqa: BLE001
            pass
    plt.rcParams["axes.unicode_minus"] = False
    return plt


def placeholder(plt, path: Path, title: str, reason: str) -> None:
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.axis("off")
    ax.text(0.5, 0.72, "NOT COMPUTED", ha="center", va="center",
            fontsize=22, weight="bold", color="#b22")
    ax.text(0.5, 0.48, title, ha="center", va="center", fontsize=13)
    ax.text(0.5, 0.22, reason, ha="center", va="center", fontsize=9,
            wrap=True, color="#444")
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)


def main() -> int:
    FIG.mkdir(parents=True, exist_ok=True)
    plt = setup()
    written: list[dict] = []

    def done(name: str, kind: str) -> None:
        written.append({"figure": name, "kind": kind,
                        "bytes": (FIG / name).stat().st_size})

    matrix = load(OUT / "model_matrix_b100.csv")
    fam = jload(OUT / "family_coverage_b100.json") or {}
    e1 = jload(OUT / "e1_manifest_b100.json") or {}
    e4 = jload(OUT / "e4_manifest_b100.json") or {}
    e6 = jload(OUT / "e6_manifest_b100.json") or {}
    conf = load(OUT / "conformer_ensemble_b100.csv")
    ood = load(OUT / "e4_structural_ood_b100.csv")
    xtc = jload(OUT / "xtb_coverage_b100.json") or {}
    dft = jload(OUT / "deliverables" / "dft_descriptors_b100.json") or {}
    mdm = jload(OUT / "deliverables" / "md_dielectric_b100.json") or {}
    e2_man = jload(OUT / "e2_xtb_vs_dft_b100.json") or {}

    # ---- 1. family coverage ----
    rows = fam.get("family_coverage", [])
    if rows:
        names = [r["family"] for r in rows]
        present = [r["n_phase_verified"] for r in rows]
        lows = [r["target_low"] for r in rows]
        highs = [r["target_high"] for r in rows]
        fig, ax = plt.subplots(figsize=(10, 5.5))
        x = range(len(names))
        ax.bar(x, present, color="#3b7", label="phase-verified")
        ax.plot(x, lows, "r_", markersize=18, label="target low")
        ax.plot(x, highs, "b_", markersize=18, label="target high")
        ax.set_xticks(list(x))
        ax.set_xticklabels(names, rotation=40, ha="right", fontsize=8)
        ax.set_ylabel("molecules")
        ax.set_title("B100 family coverage vs PLAN B v6.0 target bands\n"
                     "(neutral single molecules only; ionic liquids excluded)")
        ax.legend(fontsize=8)
        ax.grid(axis="y", alpha=0.3)
        fig.tight_layout()
        fig.savefig(FIG / "fig1_family_coverage.png", dpi=140)
        plt.close(fig)
        done("fig1_family_coverage.png", "REAL")

    # ---- 2. epsilon distribution ----
    eps = [fnum(r.get("epsilon")) for r in matrix]
    eps = [e for e in eps if e is not None]
    if eps:
        fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))
        axes[0].hist(eps, bins=30, color="#37a", edgecolor="white")
        axes[0].set_xlabel(r"static relative permittivity $\varepsilon_r$")
        axes[0].set_ylabel("molecules")
        axes[0].set_title(f"epsilon distribution (n={len(eps)})")
        axes[0].grid(alpha=0.3)
        bands = Counter(r.get("epsilon_band", "") for r in matrix)
        labels = ["LOW_lt5", "MID_5to20", "HIGH_ge20"]
        vals = [bands.get(l, 0) for l in labels]
        axes[1].bar(labels, vals, color=["#48a", "#3b7", "#a55"])
        for i, v in enumerate(vals):
            axes[1].text(i, v, str(v), ha="center", va="bottom", fontsize=9)
        axes[1].set_ylabel("molecules")
        axes[1].set_title("epsilon bands (all three populated)")
        axes[1].grid(axis="y", alpha=0.3)
        fig.tight_layout()
        fig.savefig(FIG / "fig2_epsilon_distribution.png", dpi=140)
        plt.close(fig)
        done("fig2_epsilon_distribution.png", "REAL")

    # ---- 3. xTB vs DFT : real if the DFT layer has been computed ----
    dft_rows = [r for r in load(OUT / "deliverables" / "dft_descriptors_b100.csv")
                if r.get("status") == "OK"
                and fnum(r.get("dft_dipole_D")) is not None
                and fnum(r.get("xtb_dipole_D")) is not None]
    if dft_rows:
        xt = [fnum(r["xtb_dipole_D"]) for r in dft_rows]
        dt = [fnum(r["dft_dipole_D"]) for r in dft_rows]
        fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.8))
        axes[0].scatter(xt, dt, s=22, alpha=0.7, color="#26a")
        hi = max(max(xt), max(dt)) * 1.05
        axes[0].plot([0, hi], [0, hi], "k--", lw=1, label="y = x")
        axes[0].set_xlabel("GFN2-xTB dipole (D)")
        axes[0].set_ylabel("B3LYP/def2-SVP dipole (D)")
        ev = e2_man.get("dipole_xtb_vs_dft") or {}
        axes[0].set_title(
            f"xTB vs DFT dipole (n={len(dft_rows)})\n"
            f"r={ev.get('pearson_r')}  MAE={ev.get('mean_abs_difference_D')} D")
        axes[0].legend(fontsize=8)
        axes[0].grid(alpha=0.3)
        diff = [a - b for a, b in zip(xt, dt)]
        axes[1].hist(diff, bins=35, color="#c73", edgecolor="white")
        axes[1].axvline(0, color="k", lw=1)
        axes[1].set_xlabel("xTB - DFT dipole (D)")
        axes[1].set_ylabel("molecules")
        axes[1].set_title(
            f"systematic bias = {ev.get('systematic_bias_D')} D\n"
            f"(xTB over-predicts when positive)")
        axes[1].grid(alpha=0.3)
        fig.tight_layout()
        fig.savefig(FIG / "fig3_xtb_vs_dft.png", dpi=140)
        plt.close(fig)
        done("fig3_xtb_vs_dft.png", "REAL")
    else:
        placeholder(plt, FIG / "fig3_xtb_vs_dft.png",
                    "xTB - DFT comparison",
                    dft.get("reason", "no DFT program available"))
        done("fig3_xtb_vs_dft.png", "EXPLICIT_NOT_COMPUTED")

    # ---- 4. conformer effect ----
    crows = [r for r in conf if r.get("status") == "OK"
             and fnum(r.get("boltzmann_dipole")) is not None
             and fnum(r.get("single_conformer_dipole")) is not None]
    if crows:
        single = [fnum(r["single_conformer_dipole"]) for r in crows]
        bolt = [fnum(r["boltzmann_dipole"]) for r in crows]
        verdicts = [r.get("verdict", "") for r in crows]
        fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.8))
        colors = ["#3b7" if v == "SINGLE_CONFORMER_RELIABLE"
                  else "#888" if v == "NONPOLAR_CONFORMATION_INSENSITIVE"
                  else "#c33" for v in verdicts]
        axes[0].scatter(bolt, single, c=colors, s=36, alpha=0.85)
        hi = max(max(single), max(bolt)) * 1.05
        axes[0].plot([0, hi], [0, hi], "k--", lw=1, label="y = x")
        axes[0].set_xlabel(r"Boltzmann-averaged dipole (D)")
        axes[0].set_ylabel(r"single-conformer dipole (D)")
        axes[0].set_title(f"conformer effect (n={len(crows)})\n"
                          "green=reliable, red=unreliable, grey=nonpolar")
        axes[0].legend(fontsize=8)
        axes[0].grid(alpha=0.3)
        spread = [fnum(r.get("dipole_spread")) or 0.0 for r in crows]
        axes[1].hist(spread, bins=15, color="#c73", edgecolor="white")
        axes[1].set_xlabel("dipole spread across conformers (D)")
        axes[1].set_ylabel("molecules")
        axes[1].set_title("conformer spread distribution")
        axes[1].grid(alpha=0.3)
        fig.tight_layout()
        fig.savefig(FIG / "fig4_conformer_effect.png", dpi=140)
        plt.close(fig)
        done("fig4_conformer_effect.png", "REAL")

    # ---- 5. applicability domain ----
    o = [r for r in ood if fnum(r.get("nn_tanimoto")) is not None
         and fnum(r.get("abs_error")) is not None]
    if o:
        sim = [fnum(r["nn_tanimoto"]) for r in o]
        err = [fnum(r["abs_error"]) for r in o]
        thr = e4.get("structural_ood", {}).get("ad_threshold", 0.5)
        fig, ax = plt.subplots(figsize=(8.5, 5))
        ax.scatter(sim, err, s=28, alpha=0.7, color="#26a")
        ax.axvline(thr, color="r", ls="--", lw=1.2,
                   label=f"AD threshold = {thr}")
        so = e4.get("structural_ood", {})
        ax.set_xlabel("nearest-neighbour Tanimoto similarity")
        ax.set_ylabel(r"|prediction error| in $\varepsilon_r$")
        ax.set_title(
            "applicability domain\n"
            f"in-domain MAE {so.get('mae_in_domain')} vs "
            f"out-of-domain {so.get('mae_out_domain')} "
            f"(ratio {so.get('out_over_in_ratio')})")
        ax.legend(fontsize=8)
        ax.grid(alpha=0.3)
        fig.tight_layout()
        fig.savefig(FIG / "fig5_applicability_domain.png", dpi=140)
        plt.close(fig)
        done("fig5_applicability_domain.png", "REAL")

    # ---- 6. MD : blocked ----
    placeholder(plt, FIG / "fig6_md_dipole_correlation.png",
                "liquid MD / Kirkwood dipole correlation",
                mdm.get("reason", "no MD engine available"))
    done("fig6_md_dipole_correlation.png", "EXPLICIT_NOT_COMPUTED")

    # ---- 7. MAE vs regret ----
    blocks = e1.get("blocks", [])
    if blocks and e6:
        fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.8))
        names = [b["block"] for b in blocks]
        maes = [b["nested_loo_mae"] for b in blocks]
        base = blocks[0]["constant_baseline_mae"] if blocks else None
        ypos = range(len(names))
        axes[0].barh(list(ypos), maes, color="#37a")
        if base:
            axes[0].axvline(base, color="r", ls="--",
                            label=f"constant baseline = {base:.2f}")
        axes[0].set_yticks(list(ypos))
        axes[0].set_yticklabels(names, fontsize=8)
        axes[0].set_xlabel("nested LOO MAE")
        axes[0].set_title("E1 feature-block comparison\n(same 221-molecule set)")
        axes[0].legend(fontsize=8)
        axes[0].grid(axis="x", alpha=0.3)
        # regret panel
        k = e6.get("k")
        oracle = e6.get("oracle_topk_mean")
        model = e6.get("model_topk_mean")
        pool = e6.get("pool_mean")
        if None not in (oracle, model, pool):
            axes[1].bar(["pool mean", "model Top-k", "oracle Top-k"],
                        [pool, model, oracle], color=["#999", "#37a", "#3b7"])
            axes[1].set_ylabel(r"mean $\varepsilon_r$")
            axes[1].set_title(
                f"E6 Top-{k}: regret = {e6.get('regret'):.2f}\n"
                f"P(random >= model) = "
                f"{e6.get('p_random_at_least_as_good'):.4f}")
            for i, v in enumerate([pool, model, oracle]):
                axes[1].text(i, v, f"{v:.1f}", ha="center", va="bottom",
                             fontsize=9)
            axes[1].grid(axis="y", alpha=0.3)
        fig.tight_layout()
        fig.savefig(FIG / "fig7_mae_vs_regret.png", dpi=140)
        plt.close(fig)
        done("fig7_mae_vs_regret.png", "REAL")

    # ---- 8. computation status / failure record ----
    xt = xtc.get("coverage", {})
    nl = xtc.get("failures", [])
    fig, ax = plt.subplots(figsize=(9, 4.8))
    labels = ["xTB ok", "xTB error", "xTB reused", "xTB new",
              "conformer ok", "DFT", "MD"]
    vals = [xt.get("n_with_xtb", 0), xt.get("n_error", 0),
            xt.get("n_from_existing_run", 0), xt.get("n_newly_computed", 0),
            len([r for r in conf if r.get("status") == "OK"]), 0, 0]
    colors = ["#3b7", "#c33", "#48a", "#37a", "#3b7", "#bbb", "#bbb"]
    bars = ax.bar(labels, vals, color=colors)
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width() / 2, v, str(v),
                ha="center", va="bottom", fontsize=9)
    ax.set_ylabel("molecules / systems")
    ax.set_title("computation status and failure record\n"
                 "DFT and MD are zero because the engines are unavailable, "
                 "not because they failed")
    ax.tick_params(axis="x", labelrotation=20, labelsize=8)
    ax.grid(axis="y", alpha=0.3)
    if nl:
        ax.text(0.99, 0.95, f"xTB failures recorded: {len(nl)}",
                transform=ax.transAxes, ha="right", va="top", fontsize=8,
                color="#c33")
    fig.tight_layout()
    fig.savefig(FIG / "fig8_computation_status.png", dpi=140)
    plt.close(fig)
    done("fig8_computation_status.png", "REAL_OR_EXPLICIT_ZERO")

    doc = {
        "schema": "b100.figures/v1",
        "generator": GENERATOR,
        "n_required": 8,
        "n_written": len(written),
        "figures": written,
        "blocked_figures": [
            {"figure": "fig3_xtb_vs_dft.png",
             "reason": dft.get("reason", "no DFT program")},
            {"figure": "fig6_md_dipole_correlation.png",
             "reason": mdm.get("reason", "no MD engine")},
        ],
        "note": ("无法计算的图渲染为明确的 NOT COMPUTED 面板并附原因, "
                 "而不是省略 —— 缺失图会让读者以为是没做过, "
                 "占位图则明确说明该计算在本环境不可用."),
    }
    (FIG / "figures_manifest.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"[B100-16] {FIG}")
    for w in written:
        print(f"   {w['kind']:22s} {w['figure']:36s} {w['bytes']:,} bytes")
    print(f"   {len(written)}/8 figures written "
          f"(2 are explicit NOT_COMPUTED panels)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
