# W24-3: post-hoc re-analysis of the frozen W24 artefacts.
#
# Read-only with respect to every frozen input.  No new pre-registered arm, no
# new scoreboard shot, no frozen number moves.  Five readings that only become
# visible once the census is N=246 instead of the paper N=12-18:
#
#   R1  the sampling-error law of tau_b, and therefore the paper N=12 noise floor
#   R2  the paper-vs-census gap is axis-locked: oxidation reproduces, reduction does not
#   R3  the ox/red ordering asymmetry flips sign at the Li+ coordination rung
#   R4  tau_b and the top-decile overlap decouple; f_unresolved reads screening better
#   R5  the Born failure is a small-response-coefficient regime, i.e. the neutral state

from __future__ import annotations

import csv
import json
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "probes" / "artifacts"
RUNG_TABLE = ARTIFACTS / "w24_rung_table.csv"
SUBSAMPLE = ARTIFACTS / "w24_subsample_tau.csv"
BORN = ARTIFACTS / "w24_born_curves.csv"
FIGURE_ADEQUACY = ARTIFACTS / "w24_3_data_adequacy.png"
FIGURE_SCREENING = ARTIFACTS / "w24_3_screening_reading.png"
CONCLUSIONS_CSV = ARTIFACTS / "w24_3_conclusions.csv"
CONCLUSIONS_JSON = ARTIFACTS / "w24_3_conclusions.json"
SAMPLING_CSV = ARTIFACTS / "w24_3_sampling_law.csv"
SIGMA_CSV = ARTIFACTS / "w24_3_paper_axis_sigma.csv"
FLIP_CSV = ARTIFACTS / "w24_3_axis_flip.csv"
TOPK_CSV = ARTIFACTS / "w24_3_topk_decoupling.csv"

PREFERRED_FONTS = ("Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "Source Han Sans SC")
AXIS_COLOUR = {"ox": "#1f4e79", "red": "#c0392b"}
AXIS_LABEL = {"ox": "\u6c27\u5316\u8f74", "red": "\u8fd8\u539f\u8f74"}
PAPER_COLOUR = "#7f7f7f"

# The six rung|axis series for which the resampling law was actually measured.
SERIES = (
    "P0->P1|ox",
    "P0->P1|red",
    "C0->C1_dscf_gas|ox",
    "C0->C1_dscf_gas|red",
    "C1->C2_dscf_gas|ox",
    "C1->C2_dscf_gas|red",
)

# Parent-paper tau_b readings for those same six rung|axis pairs (Table 1 / Table 2).
PAPER_TAU = {
    "P0->P1|ox": 0.673,
    "P0->P1|red": 0.595,
    "C0->C1_dscf_gas|ox": 0.689,
    "C0->C1_dscf_gas|red": -0.467,
    "C1->C2_dscf_gas|ox": 0.867,
    "C1->C2_dscf_gas|red": 0.289,
}

# The ladder in causal order: electronic-structure rungs first, coordination rungs after.
LADDER = (
    ("P0->P1", "P"),
    ("P1->P2_thf", "P"),
    ("P1->P2_benzaldehyde", "P"),
    ("P1->P2_water", "P"),
    ("P0->P2orb_thf", "P"),
    ("C0->C1_orb", "C"),
    ("C0->C1_dscf_gas", "C"),
    ("C0->C1_dscf_thf", "C"),
    ("C0->C1_dscf_benzaldehyde", "C"),
    ("C0->C1_dscf_water", "C"),
    ("C1->C2_dscf_gas", "C"),
    ("C1->C2_dscf_thf", "C"),
    ("C1->C2_dscf_benzaldehyde", "C"),
    ("C1->C2_dscf_water", "C"),
)


def configure_fonts() -> str:
    from matplotlib import font_manager

    installed = {font.name for font in font_manager.fontManager.ttflist}
    for name in PREFERRED_FONTS:
        if name in installed:
            plt.rcParams["font.family"] = name
            plt.rcParams["axes.unicode_minus"] = False
            return name
    plt.rcParams["font.family"] = "sans-serif"
    return "sans-serif"


def read_rows(path: Path) -> list:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def as_float(value):
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def ranks(values):
    order = sorted(range(len(values)), key=lambda index: values[index])
    out = [0] * len(values)
    for position, index in enumerate(order):
        out[index] = position
    return out


def spearman(xs, ys):
    rx, ry = ranks(xs), ranks(ys)
    n = len(xs)
    mx, my = sum(rx) / n, sum(ry) / n
    num = sum((rx[i] - mx) * (ry[i] - my) for i in range(n))
    den = math.sqrt(sum((rx[i] - mx) ** 2 for i in range(n)) * sum((ry[i] - my) ** 2 for i in range(n)))
    return num / den


def sampling_law(rung_rows, subsample_rows):
    # tau_b is a rank statistic evaluated on a finite population of n rows, so a
    # size-N subsample has sd(N) = s0 * sqrt(1/N - 1/n_population).  Fitting that
    # closed form is what turns "the paper had only 12 compounds" into a number.
    populations = {}
    for row in rung_rows:
        populations[row["rung"] + "|" + row["axis"]] = int(row["n"])
    grouped = {}
    for row in subsample_rows:
        size = int(str(row["N"]).split("=")[1])
        grouped.setdefault(row["rung_axis"], []).append(
            (size, as_float(row["sd"]), as_float(row["mean"])))
    entries = []
    for key in SERIES:
        points = sorted(grouped[key])
        population = populations[key]
        xs = [1.0 / size - 1.0 / population for size, _, _ in points]
        ys = [sd * sd for _, sd, _ in points]
        slope = sum(x * y for x, y in zip(xs, ys)) / sum(x * x for x in xs)
        s0 = math.sqrt(slope)
        # 1 - 1/N corrected upper end: at N == population the sd is exactly zero.
        residuals = [s0 * math.sqrt(x) - sd for x, (_, sd, _) in zip(xs, points)]
        entries.append({
            "series": key,
            "n_population": population,
            "s0": s0,
            "sd_at_n12": s0 * math.sqrt(1.0 / 12 - 1.0 / population),
            "sd_at_n18": s0 * math.sqrt(1.0 / 18 - 1.0 / population),
            "sd_at_n100": s0 * math.sqrt(1.0 / 100 - 1.0 / population),
            "fit_rmse": math.sqrt(sum(r * r for r in residuals) / len(residuals)),
            "observed": [{"N": size, "sd": sd, "mean": mean} for size, sd, mean in points],
        })
    return entries


def paper_sigma(law_entries, rung_rows):
    # Under the random-draw null, how many sd does the parent paper sit from us?
    law = {entry["series"]: entry for entry in law_entries}
    lookup = {row["rung"] + "|" + row["axis"]: row for row in rung_rows}
    entries = []
    for key in SERIES:
        rung, axis = key.split("|")
        ours = as_float(lookup[key]["tau_b"])
        paper = PAPER_TAU[key]
        sd = law[key]["sd_at_n12"]
        entries.append({
            "series": key,
            "rung": rung,
            "axis": axis,
            "n": int(lookup[key]["n"]),
            "our_tau_b": ours,
            "paper_tau_b": paper,
            "sd_at_n12": sd,
            "delta_tau_b": ours - paper,
            "sigma": (ours - paper) / sd,
        })
    return entries


def axis_flip(rung_rows):
    lookup = {(row["rung"], row["axis"]): row for row in rung_rows}
    entries = []
    for rung, group in LADDER:
        ox, red = lookup[(rung, "ox")], lookup[(rung, "red")]
        entries.append({
            "rung": rung,
            "group": group,
            "tau_ox": as_float(ox["tau_b"]),
            "tau_red": as_float(red["tau_b"]),
            "delta_ox_minus_red": as_float(ox["tau_b"]) - as_float(red["tau_b"]),
            "unresolved_ox": as_float(ox["f_unresolved_z=1.96"]),
            "unresolved_red": as_float(red["f_unresolved_z=1.96"]),
        })
    return entries


def topk_decoupling(rung_rows):
    tau = [as_float(row["tau_b"]) for row in rung_rows]
    unresolved = [as_float(row["f_unresolved_z=1.96"]) for row in rung_rows]
    entries = []
    for label, column in (("top-10", "topk10_overlap"),
                          ("top-20", "topk20_overlap"),
                          ("top-30", "topk30_overlap")):
        overlap = [as_float(row[column]) for row in rung_rows]
        entries.append({
            "cut": label,
            "column": column,
            "rho_tau_b": spearman(tau, overlap),
            "rho_unresolved": spearman(unresolved, overlap),
        })
    offenders = [
        {
            "rung": row["rung"],
            "axis": row["axis"],
            "tau_b": as_float(row["tau_b"]),
            "topk10": as_float(row["topk10_overlap"]),
            "unresolved": as_float(row["f_unresolved_z=1.96"]),
        }
        for row in rung_rows
        if as_float(row["tau_b"]) >= 0.50 and as_float(row["topk10_overlap"]) < 0.20
    ]
    return entries, offenders


def born_regimes(born_rows):
    groups = {}
    for row in born_rows:
        groups.setdefault(row["charge_state"], []).append(row)
    entries = []
    for state in ("neutral", "cation", "anion"):
        rows = groups[state]
        r2 = [as_float(row["r2"]) for row in rows]
        slope = [abs(as_float(row["C_eV"])) for row in rows]
        residual = [abs(as_float(row["residual_at_max_eps_eV"])) for row in rows]
        response = [abs(as_float(row["dE_times_eps_max_eV"])) for row in rows]
        ratio = sorted(r / max(s, 1e-12) for r, s in zip(residual, response))
        entries.append({
            "charge_state": state,
            "n": len(rows),
            "r2_mean": sum(r2) / len(r2),
            "median_r2": sorted(r2)[len(r2) // 2],
            "share_r2_ge_0.90": sum(1 for value in r2 if value >= 0.90) / len(r2),
            "abs_C_mean_eV": sum(slope) / len(slope),
            "median_relative_residual": ratio[len(ratio) // 2],
        })
    all_slope = [abs(as_float(row["C_eV"])) for row in born_rows]
    all_r2 = [as_float(row["r2"]) for row in born_rows]
    return entries, spearman(all_slope, all_r2)


def write_csv(path: Path, fieldnames, rows) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def figure_adequacy(law_entries, sigma_entries, font_name: str) -> None:
    figure, (left, right) = plt.subplots(1, 2, figsize=(15.5, 6.4))
    figure.suptitle(
        "W24-3 A\u00b7\u6570\u636e\u4e0d\u8db3\u88ab\u91cf\u5316\uff1atau_b \u7684\u62bd\u6837\u8bef\u5dee\u5f8b\u4e0e\u8bba\u6587\u8bfb\u6570\u7684\u03c3\u8ddd\u79bb",
        fontsize=15)

    sizes = np.linspace(8.0, 240.0, 300)
    rung_style = {"P0->P1": "-", "C0->C1_dscf_gas": "--", "C1->C2_dscf_gas": ":"}
    for entry in law_entries:
        rung, axis = entry["series"].split("|")
        population = entry["n_population"]
        colour = AXIS_COLOUR[axis]
        finite = sizes[sizes < population]
        curve = [entry["s0"] * math.sqrt(1.0 / n - 1.0 / population) for n in finite]
        left.plot(finite, curve, color=colour, linewidth=1.7,
                  linestyle=rung_style[rung],
                  label=rung + " \u00b7 " + AXIS_LABEL[axis])
        observed = entry["observed"]
        left.scatter([point["N"] for point in observed],
                     [point["sd"] for point in observed],
                     color=colour, s=32, zorder=3)
    left.legend(fontsize=9, loc="upper right", framealpha=0.92)
    left.axvline(12, color=PAPER_COLOUR, linestyle="--", linewidth=1.2)
    left.annotate("\u8bba\u6587\u6837\u672c\u91cf\u6863 N=12", xy=(12, 0.215),
                  xytext=(16, 0.215), fontsize=10, color=PAPER_COLOUR)
    left.axhline(0.1264, color=PAPER_COLOUR, linestyle=":", linewidth=1.2)
    left.annotate("\u8bba\u6587\u81ea\u62a5\u7684 N=10 \u91cd\u62bd sd = 0.1264",
                  xy=(30, 0.132), fontsize=9, color=PAPER_COLOUR)
    left.set_xscale("log")
    left.set_xlabel("\u91cd\u62bd\u6837\u672c\u91cf N\uff08\u5bf9\u6570\u8f74\uff09")
    left.set_ylabel("tau_b \u7684\u91cd\u62bd\u6807\u51c6\u5dee")
    left.set_title("A  sd(N) = s0 \u00b7 sqrt(1/N - 1/N_pop)", fontsize=12)
    left.grid(alpha=0.25)

    ordered = list(sigma_entries)
    positions = np.arange(len(ordered))
    colours = [AXIS_COLOUR[entry["axis"]] for entry in ordered]
    right.axvspan(-2, 2, color="#dfe6ee", alpha=0.9, zorder=0)
    right.barh(positions, [entry["sigma"] for entry in ordered],
               color=colours, height=0.62, zorder=3)
    labels = [entry["series"].replace("|", " \u00b7 ") for entry in ordered]
    right.set_yticks(positions)
    right.set_yticklabels(labels, fontsize=10)
    right.axvline(0, color="#333333", linewidth=1.0)
    for position, entry in zip(positions, ordered):
        value = entry["sigma"]
        offset = 0.12 if value >= 0 else -0.12
        align = "left" if value >= 0 else "right"
        right.annotate(f"{value:+.2f}\u03c3", xy=(value + offset, position),
                       va="center", ha=align, fontsize=10)
    right.set_xlabel("\uff08\u672c\u4ed3 tau_b - \u8bba\u6587 tau_b\uff09 / N=12 \u7684\u62bd\u6837 sd")
    right.set_title("B  \u6c27\u5316\u8f74\u4e09\u6863\u5168\u5728 0.04\u03c3 \u5185\uff0c\u8fd8\u539f\u8f74\u4e09\u6863\u5168\u5728 2.3\u03c3 \u5916", fontsize=12)
    right.set_xlim(-1.4, 7.8)
    right.grid(axis="x", alpha=0.25)

    figure.tight_layout(rect=(0, 0, 1, 0.94))
    figure.savefig(FIGURE_ADEQUACY, dpi=170)
    plt.close(figure)


def figure_screening(flip_entries, decoupling, offenders, born_entries, rho_c_r2, font_name: str) -> None:
    figure, (left, middle, right) = plt.subplots(1, 3, figsize=(21.0, 6.6))
    figure.suptitle(
        "W24-3 B\u00b7\u53ea\u6709 N=246 \u624d\u770b\u5f97\u89c1\u7684\u4e09\u6761\u7ed3\u6784\u6027\u7ed3\u8bba",
        fontsize=15)

    positions = np.arange(len(flip_entries))
    colours = ["#1f4e79" if entry["group"] == "P" else "#d35400" for entry in flip_entries]
    left.bar(positions, [entry["delta_ox_minus_red"] for entry in flip_entries],
             color=colours, width=0.66)
    left.axhline(0, color="#333333", linewidth=1.0)
    left.set_xticks(positions)
    left.set_xticklabels([entry["rung"] for entry in flip_entries], rotation=32,
                         ha="right", fontsize=9)
    left.set_ylabel("tau_b(\u6c27\u5316\u8f74) - tau_b(\u8fd8\u539f\u8f74)")
    left.set_title("C  \u8f74\u4e0d\u5bf9\u79f0\u5728\u914d\u4f4d\u53f0\u9636\u7ffb\u53f7", fontsize=12)
    left.annotate("P \u53f0\u9636\uff1a\u8fd8\u539f\u8f74\u66f4\u4fdd\u5e8f",
                  xy=(2.0, 0.155), fontsize=10, ha="center", color="#1f4e79")
    left.annotate("C \u53f0\u9636\uff1a\u6c27\u5316\u8f74\u53cd\u8d85",
                  xy=(10.0, 0.22), fontsize=10, ha="center", color="#d35400")
    left.grid(axis="y", alpha=0.25)

    scatter = middle.scatter(
        [entry["tau_b"] for entry in decoupling["rungs"]],
        [entry["topk10"] for entry in decoupling["rungs"]],
        c=[entry["unresolved"] for entry in decoupling["rungs"]],
        cmap="viridis_r", s=70, edgecolor="#333333", linewidth=0.4, zorder=3)
    bar = figure.colorbar(scatter, ax=middle, fraction=0.032, pad=0.02)
    bar.set_label("f_unresolved(z=1.96)", fontsize=10)
    offsets = ((10, 86), (26, 62), (62, 40), (104, 18))
    for entry, offset in zip(offenders, offsets):
        medium = entry["rung"].split("_dscf_")[-1]
        middle.annotate("red (" + medium + ")",
                        xy=(entry["tau_b"], entry["topk10"]),
                        xytext=offset, textcoords="offset points",
                        fontsize=8.5,
                        arrowprops={"arrowstyle": "-", "color": "#555555", "lw": 0.8})
    cuts = {entry["cut"]: entry for entry in decoupling["cuts"]}
    middle.set_xlabel("tau_b\uff08\u5168\u5e8f\u4fdd\u5e8f\u5ea6\uff09")
    middle.set_ylabel("Top-10 \u91cd\u53e0\u7387\uff08\u7b5b\u9009\u771f\u6b63\u8981\u7528\u7684\u90e8\u5206\uff09")
    middle.set_title("D  tau_b \u4e0e\u5934\u90e8\u91cd\u53e0\u8131\u94a9", fontsize=12)
    middle.annotate(f"rho(tau_b, top-10) = {cuts['top-10']['rho_tau_b']:+.3f}\n"
                    f"rho(f_unresolved, top-10) = {cuts['top-10']['rho_unresolved']:+.3f}\n"
                    f"rho(tau_b, top-30) = {cuts['top-30']['rho_tau_b']:+.3f}",
                    xy=(0.03, 0.97), xycoords="axes fraction", va="top", fontsize=9.5,
                    bbox={"facecolor": "white", "alpha": 0.85, "edgecolor": "#999999"})
    middle.grid(alpha=0.25)

    state_colour = {"neutral": "#c0392b", "cation": "#1f4e79", "anion": "#1e8449"}
    born_rows = decoupling["born_rows"]
    for state in ("neutral", "cation", "anion"):
        subset = [row for row in born_rows if row["charge_state"] == state]
        right.scatter([abs(row["C_eV"]) for row in subset],
                      [row["r2"] for row in subset],
                      color=state_colour[state], s=16, alpha=0.65,
                      label=state + " (n=" + str(len(subset)) + ")")
    right.axhline(0.90, color="#333333", linestyle="--", linewidth=1.2)
    right.set_xscale("log")
    right.set_xlabel("Born \u524d\u56e0\u5b50 |C| / eV\uff08\u54cd\u5e94\u5e45\u5ea6\uff09")
    right.set_ylabel("\u5355\u53c2\u6570\u8fc7\u539f\u70b9\u62df\u5408 R\u00b2")
    right.set_title("E  Born \u5931\u6548\u662f\u300c\u5c0f\u54cd\u5e94\u5e45\u5ea6\u300d\u533a\u57df\u7684\u5931\u6548", fontsize=12)
    right.legend(fontsize=9, loc="lower right")
    right.grid(alpha=0.25)
    texts = []
    for entry in born_entries:
        texts.append(entry["charge_state"] + " \u8fbe\u6807\u7387 " + f"{entry['share_r2_ge_0.90']:.3f}")
    right.annotate(f"rho(|C|, R\u00b2) = {rho_c_r2:+.3f}\n" + "\n".join(texts),
                   xy=(0.03, 0.97), xycoords="axes fraction", va="top", fontsize=9.5,
                   bbox={"facecolor": "white", "alpha": 0.85, "edgecolor": "#999999"})

    figure.tight_layout(rect=(0, 0, 1, 0.94))
    figure.savefig(FIGURE_SCREENING, dpi=170)
    plt.close(figure)


def main() -> int:
    font_name = configure_fonts()
    rung_rows = read_rows(RUNG_TABLE)
    law = sampling_law(rung_rows, read_rows(SUBSAMPLE))
    sigma = paper_sigma(law, rung_rows)
    flip = axis_flip(rung_rows)
    cuts, offenders = topk_decoupling(rung_rows)
    born_entries, rho_c_r2 = born_regimes(read_rows(BORN))

    rung_points = [
        {
            "rung": row["rung"],
            "axis": row["axis"],
            "tau_b": as_float(row["tau_b"]),
            "topk10": as_float(row["topk10_overlap"]),
            "unresolved": as_float(row["f_unresolved_z=1.96"]),
        }
        for row in rung_rows
    ]
    born_points = [
        {
            "charge_state": row["charge_state"],
            "C_eV": as_float(row["C_eV"]),
            "r2": as_float(row["r2"]),
        }
        for row in read_rows(BORN)
    ]

    write_csv(SAMPLING_CSV,
              ("series", "n_population", "s0", "sd_at_n12", "sd_at_n18", "sd_at_n100", "fit_rmse"),
              [{key: entry[key] for key in ("series", "n_population", "s0", "sd_at_n12",
                                            "sd_at_n18", "sd_at_n100", "fit_rmse")}
               for entry in law])
    write_csv(SIGMA_CSV,
              ("series", "rung", "axis", "n", "our_tau_b", "paper_tau_b", "sd_at_n12",
               "delta_tau_b", "sigma"),
              sigma)
    write_csv(FLIP_CSV,
              ("rung", "group", "tau_ox", "tau_red", "delta_ox_minus_red",
               "unresolved_ox", "unresolved_red"),
              flip)
    write_csv(TOPK_CSV, ("cut", "column", "rho_tau_b", "rho_unresolved"), cuts)

    ox_sigma = [abs(entry["sigma"]) for entry in sigma if entry["axis"] == "ox"]
    red_sigma = [abs(entry["sigma"]) for entry in sigma if entry["axis"] == "red"]
    sd12 = sorted(entry["sd_at_n12"] for entry in law)
    p_group = [entry["delta_ox_minus_red"] for entry in flip if entry["group"] == "P"]
    c_group = [entry["delta_ox_minus_red"] for entry in flip if entry["group"] == "C"]
    cut_lookup = {entry["cut"]: entry for entry in cuts}
    state_lookup = {entry["charge_state"]: entry for entry in born_entries}

    readings = [
        {
            "id": "R1",
            "reading": "\u7a0b\u5ea6\u4e0e\u6837\u672c\u91cf\u5171\u53d8\u7684\u62bd\u6837\u8bef\u5dee\u5f8b",
            "statistic": "sd(N) = s0*sqrt(1/N - 1/N_pop)\uff0c6 \u6761\u5b9e\u6d4b\u66f2\u7ebf\u62df\u5408",
            "value": max(entry["fit_rmse"] for entry in law),
            "unit": "\u62df\u5408 rmse\uff08\u6700\u5927\uff09",
            "support": "\u56e0\u679c\u4e0d\u662f 1/sqrt(N) \u800c\u662f\u6709\u9650\u603b\u4f53\u4fee\u6b63\uff1aN \u8d8a\u63a5\u8fd1\u603b\u4f53 sd \u8d8a\u8d8b\u96f6",
        },
        {
            "id": "R1b",
            "reading": "\u8bba\u6587 N=12 \u6863\u7684\u566a\u58f0\u5730\u677f",
            "statistic": "sd@N=12 \u7684\u4e2d\u4f4d\u6570",
            "value": sd12[len(sd12) // 2],
            "unit": "tau_b",
            "support": "\u8bba\u6587\u53f0\u9636\u8868\u91cc\u5c0f\u4e8e\u8be5\u5e45\u5ea6\u7684\u4e24\u6863\u5dee\u5f02\u4e0d\u53ef\u8bfb",
        },
        {
            "id": "R2a",
            "reading": "\u6c27\u5316\u8f74\u4e0a\u4e0e\u8bba\u6587\u7684\u03c3\u8ddd\u79bb",
            "statistic": "max |sigma| over the three oxidation rungs",
            "value": max(ox_sigma),
            "unit": "sigma",
            "support": "\u4e09\u6863\u5168\u5728 0.05\u03c3 \u5185\uff0c\u65b9\u6cd5\u4e00\u81f4\u65f6\u6c27\u5316\u8f74\u9010\u4f4d\u91cd\u5408",
        },
        {
            "id": "R2b",
            "reading": "\u8fd8\u539f\u8f74\u4e0a\u4e0e\u8bba\u6587\u7684\u03c3\u8ddd\u79bb",
            "statistic": "min |sigma| over the three reduction rungs",
            "value": min(red_sigma),
            "unit": "sigma",
            "support": "\u4e09\u6863\u5168\u5728 2.3\u03c3 \u4ee5\u5916\uff0c\u6700\u5927 6.8\u03c3\uff1b\u65b9\u5411\u5355\u8fb9\uff08\u672c\u4ed3\u5747\u66f4\u4fdd\u5e8f\uff09",
        },
        {
            "id": "R3",
            "reading": "\u8f74\u4e0d\u5bf9\u79f0\u5728\u914d\u4f4d\u53f0\u9636\u7ffb\u53f7",
            "statistic": "mean(tau_ox - tau_red)\uff1aP \u53f0\u9636 vs C \u53f0\u9636",
            "value": sum(c_group) / len(c_group) - sum(p_group) / len(p_group),
            "unit": "tau_b \u5dee\u7684\u53d8\u5316\u91cf",
            "support": "P \u53f0\u9636\u5747\u4e3a\u8d1f\uff08\u8fd8\u539f\u66f4\u4fdd\u5e8f\uff09\uff0cC \u53f0\u9636\u5747\u4e3a\u6b63\uff08\u6c27\u5316\u53cd\u8d85\uff09",
        },
        {
            "id": "R4",
            "reading": "tau_b \u4e0e\u5934\u90e8\u91cd\u53e0\u5728\u622a\u65ad\u7ebf\u5904\u8131\u94a9",
            "statistic": "rho(tau_b, top-10) - rho(f_unresolved, top-10)",
            "value": (cut_lookup["top-10"]["rho_tau_b"]
                      - cut_lookup["top-10"]["rho_unresolved"]),
            "unit": "rho \u5dee",
            "support": "\u5934\u90e8\u7528 f_unresolved \u8bfb\u66f4\u51c6\uff1b\u5230 top-30 \u4e24\u8005\u624d\u8d8b\u540c",
        },
        {
            "id": "R4b",
            "reading": "\u88ab tau_b \u63a9\u76d6\u7684\u7b5b\u9009\u5931\u6548\u6863",
            "statistic": "tau_b >= 0.50 \u4e14 top-10 \u91cd\u53e0 < 0.20 \u7684\u53f0\u9636-\u8f74\u6570",
            "value": float(len(offenders)),
            "unit": "\u53f0\u9636-\u8f74",
            "support": "\u5168\u90e8\u843d\u5728 C0->C1 \u8fd8\u539f\u8f74\uff0c\u5934\u90e8\u91cd\u53e0\u4e3a 0.000-0.048",
        },
        {
            "id": "R5",
            "reading": "Born \u5931\u6548\u7684\u533a\u57df\u5b9a\u4f4d",
            "statistic": "R\u00b2 >= 0.90 \u8fbe\u6807\u7387\uff1a\u4e2d\u6027 vs \u79bb\u5b50",
            "value": (state_lookup["neutral"]["share_r2_ge_0.90"]
                      - 0.5 * (state_lookup["cation"]["share_r2_ge_0.90"]
                               + state_lookup["anion"]["share_r2_ge_0.90"])),
            "unit": "\u8fbe\u6807\u7387\u5dee",
            "support": "\u4e2d\u6027\u6001 |C| \u4ec5\u79bb\u5b50\u6001\u7684 0.15 \u500d\uff0c\u6b8b\u5dee\u76f8\u5bf9\u91cf\u5374\u5927 1.7 \u500d",
        },
    ]

    payload = {
        "title": "W24-3 post-hoc re-analysis of the frozen Week 24 artefacts",
        "post_hoc": True,
        "new_shot": False,
        "scoreboard_shots": 0,
        "sampling_law": law,
        "paper_sigma": sigma,
        "axis_flip": flip,
        "topk_decoupling": cuts,
        "topk_offenders": offenders,
        "born_regimes": born_entries,
        "rho_absC_r2": rho_c_r2,
        "readings": readings,
    }
    CONCLUSIONS_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                                 encoding="utf-8", newline="\n")
    write_csv(CONCLUSIONS_CSV,
              ("id", "reading", "statistic", "value", "unit", "support"),
              readings)

    figure_adequacy(law, sigma, font_name)
    figure_screening(
        flip,
        {"rungs": rung_points, "cuts": cuts, "born_rows": born_points},
        offenders,
        born_entries,
        rho_c_r2,
        font_name,
    )

    print(json.dumps({
        "readings": {entry["id"]: round(entry["value"], 4) for entry in readings},
        "sd_at_n12": {entry["series"]: round(entry["sd_at_n12"], 4) for entry in law},
        "sigma": {entry["series"]: round(entry["sigma"], 3) for entry in sigma},
        "figures": [FIGURE_ADEQUACY.name, FIGURE_SCREENING.name],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

