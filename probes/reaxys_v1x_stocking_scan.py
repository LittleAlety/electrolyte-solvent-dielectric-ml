"""Generate the v1.x Reaxys stocking scan artifacts.

Two halves, kept deliberately separate:

1. ``stocking_queue`` -- deterministic and recomputed on every run from the
   frozen L3 pool and the local observation table: every pool member whose
   observation rows carry fewer than two distinct temperatures. This is the
   hand-off list for any future temperature-resolved expansion.

2. ``reaxys_probe`` -- the hand-transcribed result of manual, per-compound
   queries run on 2026-09-26 inside the user's logged-in Edge session. These
   numbers are ``restricted_crosscheck_only`` and must never be joined back
   into ``data/`` or into the pool.

Only the queue half is derived; the probe half is a transcription, and that
transcription *does* carry a machine-readable mirror of the restricted numeric
fields it read (``readings[].rendered_rows`` and ``net_new_detail[].value``).
That mirror lives only in this repository and in the week13 bundle; it must not
be redistributed and must not be joined into any distributable dataset. Saying
otherwise would be false, which is why the compliance string names it.
"""

import argparse
import collections
import csv
import io
import json
import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
POOL_PATH = REPO_ROOT / "probes" / "l3_stage1_pilot_pool.csv"
OBS_PATH = REPO_ROOT / "data" / "processed" / "dielectric_observations_v11plus.csv"
QUEUE_PATH = REPO_ROOT / "probes" / "reaxys_v1x_stocking_queue.csv"
SUMMARY_PATH = REPO_ROOT / "probes" / "reaxys_v1x_stocking_scan_summary.json"
REPORT_PATH = REPO_ROOT / "reports" / "reaxys_v1x_stocking_scan.md"

POOL_SHA256 = "b838febbca4d65975d1820ae9275215288968979b78756611cb031eb7c408b18"
OBS_SHA256 = "159b928f800a55969963da275ed05c30ce8a19cffc48353a9c490eec68a49af9"
PROBE_DATE = "2026-09-26"
BROWSER = "Edge (user-logged-in Reaxys session), manual per-record queries"
QUEUE_FIELDS = [
    "queue_rank", "inchikey", "name", "smiles", "target_dielectric", "target_T_K",
    "local_rows", "local_distinct_T", "family_tag", "is_champion", "champion_short",
    "model_ready", "probed_in_this_round", "stocking_priority", "access",
]

# Ordered rules. Two ordering facts are load-bearing and were wrong before:
#   * whole-molecule classes (ionic_liquid) must be tested before the
#     functional-group rule ``fluorinated``, otherwise a fluorinated anion drags
#     an imidazolium salt into ``fluorinated``;
#   * ``oxa`` matches "disiloxane", so the siloxane guard has to come before
#     ``glyme_ether``.
FAMILY_RULES = [
    ("carbonate", ("carbonate",)),
    ("lactone", ("lactone", "butyrolactone")),
    ("nitrile", ("nitrile", "acetonitrile", "propionitrile")),
    ("sulfoxide_sulfone", ("sulfoxide", "sulfone", "sulfolane")),
    ("ionic_liquid", ("imidazolium", "imidazol-3-ium", "azolium", "pyrrolidinium", "piperidinium",
                      "ammonium", "phosphonium", "sulfonium")),
    ("siloxane", ("siloxane",)),
    ("glyme_ether", ("glyme", "glycol dimethyl ether", "oxa", "dimethoxyethane", "dioxolane", "oxolane", "tetrahydrofuran", "furan", "ether")),
    ("fluorinated", ("fluoro", "trifluoro")),
    ("alcohol_amine", ("-ol", "ol ", "amine", "hydroxy")),
]

# Suffix-only catches what the substring rules cannot see ("1,2-ethanediol"
# carries no "-ol" / "ol " token). Thiols also end in "ol" but are not alcohols.
ALCOHOL_SUFFIXES = ("ol", "diol")

# Hand transcription of the manual Reaxys reads. Column order of ``rendered_rows``
# follows the Reaxys "Dielectric Constant" table:
# value, Frequency (Hz), Temperature (C), Location, Comment, Reference.
READINGS = [
    {
        "compound": "ethylene carbonate",
        "short": "EC",
        "cas": "96-49-1",
        "reaxys_registry_number": "106249",
        "query": "ethylene carbonate dielectric constant permittivity",
        "reaxys_dielectric_entries": 4,
        "entries_rendered": 4,
        "temperature_series": False,
        "temperature_points_C": [25],
        "rendered_rows": [
            ["5.4", "", "25", "", "", "Segura-Ramirez, Yutzil; Sole-Daura, Albert; Gomez-Mingot, Maria; Fontecave, Marc; Sanchez-Sanchez, Carlos M. - ChemSusChem"],
            ["89.78", "", "", "supporting information", "", "Xu, Caili; Zhang, Ming; Li, Pengyu; Chen, Cheng; Zhou, Haiping; Zhang, Shu; Wu, Mengqiang - Chinese Chemical Letters, 2026"],
            ["89.78", "", "25", "", "", "Schroeder; Hubaud; Vaughey - Materials Research Bulletin, 2014, vol. 49, #1, p. 614-617"],
            ["", "", "", "", "", "Maquestian et al. - Bulletin des Societes Chimiques Belges, 1971, vol. 80, p. 17,22; D'Aprano - Gazzetta Chimica Italiana"],
        ],
        "local_registered_distinct_T": 1,
        "local_registered_scope": "frozen_table_v03",
        "local_T_K": [313.15],
        "net_new_temperature_points": 0,
        "verdict": "no_temperature_series",
        "note": (
            "只有 25 C 标签。5.4 @ 25 C 这一条与同物质其余三条差一个数量级，疑为异质测量或单位混入，"
            "只作可疑条目登记、不作数值使用。89.78 这条**不能按 Reaxys 标的 25 C 读**：本仓库既有溯源"
            "（reports/jstage_corroboration.md）把同一个 89.78 记为 **40 C = 313.15 K**，正好是 EC 的冻结温度，"
            "相对偏差 0.80%；而 EC 熔点 36.4 C，25 C 本就不是液态。Reaxys 的温度标注在这里是错的，"
            "这本身就是「Reaxys 温度栏不可信」的内部证据（见第 5 节）。"
        ),
    },
    {
        "compound": "propylene carbonate",
        "short": "PC",
        "cas": "108-32-7",
        "reaxys_registry_number": "107913",
        "query": "propylene carbonate dielectric constant permittivity",
        "reaxys_dielectric_entries": 10,
        "entries_rendered": 7,
        "temperature_series": False,
        "temperature_points_C": [20, 25, 25, 25, 25, 35],
        "rendered_rows": [
            ["64.9", "", "25", "", "", "Segura-Ramirez, Yutzil; Sole-Daura, Albert; Gomez-Mingot, Maria; Fontecave, Marc; Sanchez-Sanchez, Carlos M. - ChemSusChem"],
            ["64.92", "", "", "supporting information", "", "Xu, Caili; Zhang, Ming; Li, Pengyu; Chen, Cheng; Zhou, Haiping; Zhang, Shu; Wu, Mengqiang - Chinese Chemical Letters, 2026"],
            ["64", "", "", "supporting information", "", "Segato, Jacopo; Baratta, Walter; Belanzoni, Paola; Belpassi, Leonardo; Del Zotto, Alessandro; Zuccaccia, Daniele - Inorganica Chimica Acta, 2021, vol. 522"],
            ["69", "", "25", "", "Liquid", "Sun, Yihan; Huang, Jinxia; Guo, Zhiguang - Chemical Communications, 2019, vol. 55, #92, p. 13876-13879"],
            ["64.92", "", "25", "", "", "Schroeder; Hubaud; Vaughey - Materials Research Bulletin, 2014, vol. 49, #1, p. 614-617"],
            ["62.93", "2E+06", "20", "", "", "Laurence, Christian; Nicolet, Pierre; Dalati, M. Tawfik; Abboud, Jose-Luis M.; Notario, Rafael - Journal of Physical Chemistry, 1994, vol. 98, #23, p. 5807-5816"],
            ["63.41", "2E+06", "35", "", "", "Ritzoulis, George - Canadian Journal of Chemistry, 1989, vol. 67, p. 1105-1108"],
        ],
        "local_registered_distinct_T": 1,
        "local_registered_scope": "frozen_table_v03",
        "local_T_K": [298.15],
        "net_new_detail": [
            {"temperature_C": 20.0, "value": 62.93, "frequency_Hz": "2E+06",
             "source": "Laurence, Christian; Nicolet, Pierre; Dalati, M. Tawfik; Abboud, Jose-Luis M.; Notario, Rafael - Journal of Physical Chemistry, 1994, vol. 98, #23, p. 5807-5816"},
            {"temperature_C": 35.0, "value": 63.41, "frequency_Hz": "2E+06",
             "source": "Ritzoulis, George - Canadian Journal of Chemistry, 1989, vol. 67, p. 1105-1108"},
        ],
        "net_new_qualifier": "2 MHz AC；本地 PC 只有一个 298.15 K 点，故这两点相对本地是新温度点，但频率口径不同",
        "verdict": "cross_check_ok_plus_two_frequency_qualified_points",
        "note": (
            "Reaxys 侧有两条 25 C 条目（64.9 与 64.92）与冻结冠军真值 64.9 @ 298.15 K 相符，"
            "但**这不是独立测量旁证**：本仓库既有溯源（reports/jstage_corroboration.md）已证明 64.92 "
            "来自 Nanbu 2007 转引的 Riddick《Organic Solvents》4th ed. 汇编值，属「汇编转述一致」。"
            "详见第 5 节。另有 20 C / 35 C 两点，但都标在 2 MHz，是否可入 v1.x 观测表受频率口径约束，"
            "本产物只报线索，不做入库判断。"
        ),
    },
    {
        "compound": "tetraethylene glycol dimethyl ether",
        "short": "tetraglyme",
        "cas": "143-24-8",
        "reaxys_registry_number": "1760005",
        "query": "tetraethylene glycol dimethyl ether dielectric constant permittivity",
        "reaxys_dielectric_entries": 8,
        "entries_rendered": 7,
        "temperature_series": True,
        "temperature_points_C": [14.99, 19.99, 24.99, 29.99, 34.99, 44.99, 54.99],
        "rendered_rows": [
            ["8.03", "1E+06", "14.99", "", "temperature dependence", "Rivas; Iglesias; Pereira; Banerji - Journal of Chemical Thermodynamics, 2006, vol. 38, #3, p. 245-256"],
            ["7.9", "1E+06", "19.99", "", "", "Rivas; Iglesias; Pereira; Banerji - Journal of Chemical Thermodynamics, 2006, vol. 38, #3, p. 245-256"],
            ["7.79", "1E+06", "24.99", "", "", "Rivas; Iglesias; Pereira; Banerji - Journal of Chemical Thermodynamics, 2006, vol. 38, #3, p. 245-256"],
            ["7.67", "1E+06", "29.99", "", "", "Rivas; Iglesias; Pereira; Banerji - Journal of Chemical Thermodynamics, 2006, vol. 38, #3, p. 245-256"],
            ["7.55", "1E+06", "34.99", "", "", "Rivas; Iglesias; Pereira; Banerji - Journal of Chemical Thermodynamics, 2006, vol. 38, #3, p. 245-256"],
            ["7.31", "1E+06", "44.99", "", "", "Rivas; Iglesias; Pereira; Banerji - Journal of Chemical Thermodynamics, 2006, vol. 38, #3, p. 245-256"],
            ["7.07", "1E+06", "54.99", "", "", "Rivas; Iglesias; Pereira; Banerji - Journal of Chemical Thermodynamics, 2006, vol. 38, #3, p. 245-256"],
        ],
        "local_registered_distinct_T": 5,
        "local_registered_scope": "observation_table",
        "local_T_K": [288.15, 293.15, 298.15, 303.15, 308.15],
        "net_new_detail": [
            {"temperature_C": 44.99, "value": 7.31, "frequency_Hz": "1E+06",
             "source": "Rivas; Iglesias; Pereira; Banerji - Journal of Chemical Thermodynamics, 2006, vol. 38, #3, p. 245-256"},
            {"temperature_C": 54.99, "value": 7.07, "frequency_Hz": "1E+06",
             "source": "Rivas; Iglesias; Pereira; Banerji - Journal of Chemical Thermodynamics, 2006, vol. 38, #3, p. 245-256"},
        ],
        "net_new_qualifier": "1 MHz AC；本地 tetraglyme 的温度序列到 308.15 K 为止，这两点是高端延伸",
        "verdict": "net_new_temperature_points_from_a_new_primary_source",
        "note": (
            "本轮唯一的净新增温度点来源。Reaxys 侧 7 个已渲染温度点里，前 5 个与本地 288.15-308.15 K "
            "逐点重合（差 0.01 K，属摄氏/开氏换算舍入），可作本地两条 JCT/TCA 来源的独立复现；"
            "净新增为高端 318.14 K 与 328.14 K 两点，一手出处 Rivas et al., J. Chem. Thermodynamics, "
            "2006, 38(3), 245-256（1 MHz）。全部 7 点均来自该单一来源，因此新增点的独立性只体现在"
            "「与本地已有点的方法不同」上，不构成第二个独立来源。"
        ),
    },
    {
        "compound": "triethylene glycol dimethyl ether",
        "short": "triglyme",
        "cas": "112-49-2",
        "reaxys_registry_number": "1700630",
        "query": "triethylene glycol dimethyl ether dielectric constant permittivity",
        "reaxys_dielectric_entries": 1,
        "entries_rendered": 1,
        "temperature_series": False,
        "temperature_points_C": [],
        "rendered_rows": [
            ["", "", "", "", "", "Ugelstad et al. - Acta Chemica Scandinavica (1947), 1965, vol. 19, p. 208,214; King; Pews - Canadian Journal of Chemistry"],
        ],
        "local_registered_distinct_T": 5,
        "local_registered_scope": "observation_table",
        "local_T_K": [288.15, 298.15, 308.15, 318.15, 328.15],
        "net_new_temperature_points": 0,
        "verdict": "reaxys_weaker_than_local",
        "note": "唯一一条是「提及级」条目：值/频率/温度/Location/Comment 五列全空，只有引文。本地 5 点温度序列严格更强。",
    },
    {
        "compound": "adiponitrile (hexanedinitrile)",
        "short": "adiponitrile",
        "cas": "111-69-3",
        "reaxys_registry_number": "1740005",
        "query": "adiponitrile dielectric constant permittivity",
        "reaxys_dielectric_entries": 1,
        "entries_rendered": 1,
        "temperature_series": False,
        "temperature_points_C": [],
        "rendered_rows": [
            ["", "", "", "", "", "Sears et al. - Journal of Physical Chemistry, 1967, vol. 71, p. 905,907; Schwarz et al. - Journal of Chemical and Engineering Data, 1970, vol. 15, p. 341,343-346"],
        ],
        "local_registered_distinct_T": 31,
        "local_registered_scope": "observation_table",
        "local_T_K": [278.15, 353.15],
        "net_new_temperature_points": 0,
        "verdict": "reaxys_weaker_than_local",
        "note": (
            "同样只有一条五列全空的提及级条目。本地 dielectric_observations_v11plus.csv 里该物质"
            "（登记名 hexanedinitrile，BTGRAWJCKBQKAO-UHFFFAOYSA-N）已有 278.15-353.15 K 共 31 个温度点——"
            "这条也修正了本轮早先按俗名 adiponitrile 做的覆盖度误判。"
        ),
    },
    {
        "compound": "diglyme (diethylene glycol dimethyl ether)",
        "short": "diglyme",
        "cas": "111-96-6",
        "reaxys_registry_number": "",
        "query": "diglyme diethylene glycol dimethyl ether dielectric constant permittivity",
        "reaxys_dielectric_entries": 0,
        "entries_rendered": 0,
        "temperature_series": False,
        "temperature_points_C": [],
        "rendered_rows": [],
        "local_registered_distinct_T": 6,
        "local_registered_scope": "observation_table",
        "local_T_K": [288.15, 298.15, 308.15, 318.15, 328.15, 338.15],
        "net_new_temperature_points": 0,
        "verdict": "absent_in_reaxys",
        "note": "Reaxys 侧 Property: dielectric constant 命中 0 个物质（PubChem 侧 7 个）。本地 6 点温度序列严格更强。",
    },
    {
        "compound": "1,1,2,2-tetrafluoroethyl 2,2,2-trifluoroethyl ether",
        "short": "TTE",
        "cas": "",
        "reaxys_registry_number": "",
        "query": "1,1,2,2-tetrafluoroethyl 2,2,2-trifluoroethyl ether dielectric constant permittivity",
        "reaxys_dielectric_entries": 0,
        "entries_rendered": 0,
        "temperature_series": False,
        "temperature_points_C": [],
        "rendered_rows": [],
        "local_registered_distinct_T": 1,
        "local_registered_scope": "observation_table_single_point",
        "local_T_K": [298.15],
        "net_new_temperature_points": 0,
        "verdict": "absent_in_reaxys_and_local_is_single_point",
        "note": (
            "Reaxys 侧 0 个物质（PubChem 侧 5 个）。本地池内该物质（CWIFAKBLLXGZIC-UHFFFAOYSA-N）"
            "只有一个 298.15 K 点，因此它是真缺口——但 Reaxys 补不上，这一条维持未闭合。"
        ),
    },
]


def classify(name: str) -> str:
    low = (name or "").lower()
    for tag, needles in FAMILY_RULES:
        if any(n in low for n in needles):
            return tag
    if low.endswith("thiol"):
        return "other"
    if low.endswith(ALCOHOL_SUFFIXES):
        return "alcohol_amine"
    return "other"


def observation_temperature_counts() -> tuple[dict[str, int], dict[str, int], int]:
    """(rows per InChIKey, distinct rounded T per InChIKey, observation row count).

    The scope matters: these counts are over the whole observation table, not over
    the frozen pool. Conflating the two is exactly what produced the "106 vs 69"
    mistake this function now makes impossible to repeat silently.
    """
    with OBS_PATH.open(encoding="utf-8", newline="") as fh:
        obs = list(csv.DictReader(fh))
    temps: dict[str, set[float]] = collections.defaultdict(set)
    rows: dict[str, int] = collections.Counter()
    for r in obs:
        key = r["inchikey"]
        rows[key] += 1
        try:
            temps[key].add(round(float(r["T_K"]), 2))
        except (TypeError, ValueError):
            pass
    return dict(rows), {k: len(v) for k, v in temps.items()}, len(obs)


def build_queue() -> tuple[list[dict], dict]:
    with POOL_PATH.open(encoding="utf-8", newline="") as fh:
        pool = list(csv.DictReader(fh))
    rows, distinct, n_obs_rows = observation_temperature_counts()

    probed = {r["compound"].split(" (")[0]: r for r in READINGS}
    alias = {
        "KMTRUDSVKNLOMY-UHFFFAOYSA-N": "ethylene carbonate",
        "RUOJZAUFBMNUDX-UHFFFAOYSA-N": "propylene carbonate",
        "ZUHZGEOKBKGPSW-UHFFFAOYSA-N": "tetraethylene glycol dimethyl ether",
        "YFNKIDBQEZZDLK-UHFFFAOYSA-N": "triethylene glycol dimethyl ether",
        "BTGRAWJCKBQKAO-UHFFFAOYSA-N": "adiponitrile (hexanedinitrile)",
        "SBZXBUIDTXKZTM-UHFFFAOYSA-N": "diglyme (diethylene glycol dimethyl ether)",
        "CWIFAKBLLXGZIC-UHFFFAOYSA-N": "1,1,2,2-tetrafluoroethyl 2,2,2-trifluoroethyl ether",
    }

    queue = []
    for r in pool:
        key = r["inchikey"]
        n_distinct = distinct.get(key, 0)
        if n_distinct >= 2:
            continue
        family = classify(r["name"])
        probed_here = "yes" if alias.get(key, r["name"]) in probed else "no"
        queue.append({
            "inchikey": key,
            "name": r["name"],
            "smiles": r["smiles"],
            "target_dielectric": r["target_dielectric"],
            "target_T_K": r["T_K"],
            "local_rows": rows.get(key, 0),
            "local_distinct_T": n_distinct,
            "family_tag": family,
            "is_champion": r["is_champion"],
            "champion_short": r["champion_short"],
            "model_ready": r["model_ready"],
            "probed_in_this_round": probed_here,
            "stocking_priority": (
                # P1 is *defined* as the champion rows. Deriving it from the pool
                # flag rather than hard-coding two names keeps the rule from
                # drifting away from the data it claims to encode.
                "P1" if str(r["is_champion"]).strip().lower() == "true"
                else "P2" if family in {"carbonate", "lactone", "glyme_ether", "fluorinated"}
                and str(r["model_ready"]).strip().lower() == "true"
                else "P3"
            ),
            # The access label is per row, not a blanket claim: only rows that were
            # actually probed by hand may say so.
            "access": (
                "public_local_metadata_plus_manual_reaxys_probe" if probed_here == "yes"
                else "public_local_metadata_only_not_yet_probed"
            ),
        })
    queue.sort(key=lambda d: ({"P1": 0, "P2": 1, "P3": 2}[d["stocking_priority"]], d["family_tag"], d["inchikey"]))

    pool_keys = {r["inchikey"] for r in pool}
    pool_with_series = sum(1 for k in pool_keys if distinct.get(k, 0) >= 2)
    stats = {
        "pool_rows": len(pool),
        "pool_distinct_keys": len(pool_keys),
        "observation_rows": n_obs_rows,
        "observation_compounds": len(distinct),
        # Two different universes. Both counts are reported, each with its scope in
        # the key name, and the identity below is asserted rather than trusted.
        "observation_table_compounds_with_two_or_more_distinct_T": sum(
            1 for v in distinct.values() if v >= 2),
        "pool_members_with_two_or_more_distinct_T": pool_with_series,
        "queue_size": len(queue),
        "p1_equals_champion_rows": all(
            (d["stocking_priority"] == "P1") == (str(d["is_champion"]).strip().lower() == "true")
            for d in queue),
        "model_ready_filter_is_vacuous_on_this_queue": all(
            str(d["model_ready"]).strip().lower() == "true" for d in queue),
        # P2 is a *family* heuristic, so a broad substring family drags in rows
        # that are not battery-relevant at all. Report the size of that leak
        # instead of letting the label read as a usability claim.
        "p2_is_a_family_heuristic_not_a_usability_claim": True,
        "p2_rows_in_the_fluorinated_family": sum(
            1 for d in queue
            if d["stocking_priority"] == "P2" and d["family_tag"] == "fluorinated"),
        "p2_fluorinated_examples": sorted(
            d["name"] for d in queue
            if d["stocking_priority"] == "P2" and d["family_tag"] == "fluorinated")[:6],
        "queue_by_priority": dict(collections.Counter(d["stocking_priority"] for d in queue)),
        "queue_by_family": dict(sorted(collections.Counter(d["family_tag"] for d in queue).items())),
    }
    assert stats["queue_size"] + stats["pool_members_with_two_or_more_distinct_T"] == stats["pool_distinct_keys"], (
        "queue and pool temperature-series counts do not partition the pool")
    assert stats["p1_equals_champion_rows"], "P1 is no longer exactly the champion rows"
    return queue, stats


# InChIKey of every compound that was probed by hand. This is the only bridge
# between the hand transcription and the local tables, so it is declared once.
PROBED_INCHIKEY = {
    "ethylene carbonate": "KMTRUDSVKNLOMY-UHFFFAOYSA-N",
    "propylene carbonate": "RUOJZAUFBMNUDX-UHFFFAOYSA-N",
    "tetraethylene glycol dimethyl ether": "ZUHZGEOKBKGPSW-UHFFFAOYSA-N",
    "triethylene glycol dimethyl ether": "YFNKIDBQEZZDLK-UHFFFAOYSA-N",
    "adiponitrile (hexanedinitrile)": "BTGRAWJCKBQKAO-UHFFFAOYSA-N",
    "diglyme (diethylene glycol dimethyl ether)": "SBZXBUIDTXKZTM-UHFFFAOYSA-N",
    "1,1,2,2-tetrafluoroethyl 2,2,2-trifluoroethyl ether": "CWIFAKBLLXGZIC-UHFFFAOYSA-N",
}


def resolved_readings(obs_distinct: dict[str, int] | None = None) -> list[dict]:
    """Readings with the derived fields recomputed from their own details.

    Three things are recomputed rather than trusted:
      * the net-new scalar follows its per-point detail list, so the two can never
        drift apart, and a scalar without a list is a transcription error;
      * ``entries_rendered`` must equal the number of rows actually transcribed;
      * ``observation_table_distinct_T`` is read straight from the local
        observation table, which is what exposes that EC/PC are *not* in it even
        though the frozen table carries a row for each.
    """
    if obs_distinct is None:
        _, obs_distinct, _ = observation_temperature_counts()
    out = []
    for r in READINGS:
        d = dict(r)
        if "net_new_detail" in d:
            d["net_new_temperature_points"] = len(d["net_new_detail"])
        else:
            d["net_new_temperature_points"] = int(d["net_new_temperature_points"])
            if d["net_new_temperature_points"]:
                raise ValueError(f"{d['short']}: net-new points declared without a detail list")
        if d["entries_rendered"] != len(d["rendered_rows"]):
            raise ValueError(
                f"{d['short']}: entries_rendered={d['entries_rendered']} but "
                f"{len(d['rendered_rows'])} rows were transcribed")
        d["observation_table_distinct_T"] = int(
            obs_distinct.get(PROBED_INCHIKEY[d["compound"]], 0))
        d["provenance"] = {
            "route": "reaxys_ui_manual_query",
            "restriction": "restricted_crosscheck_only",
            "redistribution": "not_permitted",
            "declares_channel_availability": False,
        }
        out.append(d)
    return out


def net_new_headline(readings: list[dict]) -> list[dict]:
    headline = []
    for r in readings:
        detail = r.get("net_new_detail") or []
        if not detail:
            continue
        sources = []
        for point in detail:
            if point["source"] not in sources:
                sources.append(point["source"])
        headline.append({
            "short": r["short"],
            "substance": r["compound"],
            "n_points": len(detail),
            "temperature_points_C": [p["temperature_C"] for p in detail],
            "frequency_Hz": sorted({p["frequency_Hz"] for p in detail}),
            "sources": sources,
            "qualifier": r.get("net_new_qualifier", ""),
        })
    return headline


def build_probe() -> dict:
    readings = resolved_readings()
    net_new = net_new_headline(readings)
    return {
        "task": "reaxys_v1x_stocking_scan",
        "date": PROBE_DATE,
        "browser": BROWSER,
        "compliance": (
            "手动逐条查询（无批量抓取、无导出、无自动化遍历）；全部取值 restricted_crosscheck_only，"
            "永不并入 data/ 或池、永不作为任何冻结读数的替代；"
            "**本产物确实含受限数值字段的机器可读镜像**（人工转录）——readings[].rendered_rows 与 "
            "net_new_detail[].value 就是 Reaxys 渲染表里的介电常数 / 频率 / 温度列的逐值转录；"
            "该镜像只存于本仓库与 week13 交付包内，禁止再次分发"
        ),
        "restricted_values_contract": {
            "route": "reaxys_ui_manual_query_in_logged_in_edge_session",
            "provenance": "reaxys<-bibliographic_citation",
            "provenance_note": (
                "Reaxys 的 Dielectric Constant 渲染表只给文献题录（作者/刊名/卷/页/年），不给 DOI，"
                "所以 provenance 只能到题录一级，写成 reaxys<-primary_doi 是不准确的"
            ),
            "machine_readable_mirror_present": True,
            "mirror_fields": ["readings[].rendered_rows", "net_new_detail[].value"],
            "redistribution": "not_permitted",
            "may_join_into_data_or_pool": False,
            "declares_channel_availability": False,
        },
        "pool_sha256": POOL_SHA256,
        "observation_sha256": OBS_SHA256,
        "reaxys_data_model_recap": {
            "Static Dielectric Constant": ["value", "Temperature (C)", "Location", "Comment", "Reference"],
            "Dielectric Constant": ["value", "Frequency (Hz)", "Temperature (C)", "Location", "Comment", "Reference"],
            "method_field": "不存在（Reaxys 不建模测量方法）",
        },
        "readings": readings,
        "net_new_temperature_points": net_new,
        "cross_checks": [
            {
                "champion": "PC",
                "frozen_truth": "64.9 @ 298.15 K",
                "reaxys_corroboration": [
                    "64.9 @ 25 C (Segura-Ramirez, ChemSusChem)",
                    "64.92 @ 25 C (Schroeder; Hubaud; Vaughey, Mater. Res. Bull. 2014, 49(1), 614-617)",
                ],
                "verdict": "compilation_restatement_agrees",
                "evidence_chain": {
                    "summary": "2 条互异题录，但同值且都指回同一部汇编 —— 转述一致，非独立测量",
                    "n_reaxys_sources": 2,
                    "distinct_sources": True,
                    "shared_provenance": (
                        "两条 25 C 值（64.9 / 64.92）与本仓库既有的汇编转述同值；"
                        "reports/jstage_corroboration.md 已证明该值来自 Nanbu 2007 转引的 "
                        "Riddick《Organic Solvents》4th ed. 汇编，即汇编转述而非新测量"
                    ),
                    "cross_reference": "reports/jstage_corroboration.md",
                    "cross_reference_quote": (
                        "Corroboration here means *agreement with a compilation restatement*, "
                        "not independent measurement."
                    ),
                    "reading": (
                        "两条 25 C 条目与冻结真值相符，但这是**汇编转述一致**，不是两个独立测量。"
                        "按本项目的证据纪律降级为 `compilation_restatement_agrees`，不得写成「独立旁证」。"
                    ),
                },
            },
            {
                "champion": "EC",
                "frozen_truth": "90.5 @ 313.15 K",
                "reaxys_corroboration": [
                    "89.78 @ 25 C (Schroeder; Hubaud; Vaughey, Mater. Res. Bull. 2014, 49(1), 614-617)",
                ],
                "verdict": "value_matches_but_reaxys_temperature_label_conflicts",
                "evidence_chain": {
                    "summary": "同一条 89.78：本仓库溯源记 40 C = 313.15 K，Reaxys 标 25 C —— 温度栏自相矛盾",
                    "n_reaxys_sources": 1,
                    "distinct_sources": True,
                    "value_matches_open_literature": True,
                    "reaxys_temperature_label_C": 25,
                    "open_literature_temperature_C": 40,
                    "open_literature_temperature_K": 313.15,
                    "frozen_truth_temperature_K": 313.15,
                    "relative_deviation_vs_frozen_truth": 0.008,
                    "cross_reference": "reports/jstage_corroboration.md",
                    "cross_reference_quote": (
                        "| Ethylene carbonate | **90.5** at 313.15 K (40 C) | 89.78 at 40 C | "
                        "yes | 0.72 | 0.802% |"
                    ),
                    "reading": (
                        "89.78 就是本仓库已经溯源过的那个 89.78，但它属于 **40 C = 313.15 K**"
                        "（= EC 冻结温度，相对偏差 0.80%）。Reaxys 把它标成 25 C，而 EC 熔点 36.4 C、"
                        "25 C 根本不是液态，所以既不记为「一致」，也不记为「不冲突」，"
                        "而记为「数值相符但 Reaxys 温度标注错」。这条同时是「Reaxys 温度栏不可信」的内部证据。"
                    ),
                },
            },
        ],
        "corrections_made_this_round": [
            (
                "早先按俗名 adiponitrile / diglyme / triglyme / tetraglyme 做的覆盖度匹配全部误判为「本地 0 行」；"
                "本地表用 IUPAC 登记名（hexanedinitrile、2,5,8-trioxanonane、2,5,8,11-tetraoxadodecane、"
                "2,5,8,11,14-pentaoxapentadecane）登记，实际 glyme 系与己二腈本地早有温度序列。"
            ),
            "stocking_queue 因此改为按 InChIKey 重算，不再依赖名称匹配。",
        ],
        "open_items": [
            (
                "tetraglyme 侧 Reaxys 声明 Dielectric Constant - 8 hits out of 8，但表内只渲染 7 行；"
                "缺失的那一条（疑为 39.99 C = 313.14 K）本轮未读到，属未闭合项。"
            ),
            "EC 的 5.4 @ 25 C 条目与同物质其余三条差一个数量级，未判定归属，只登记为可疑条目。",
            "PC 的 20 C / 35 C 两点在 2 MHz，能否进 v1.x 观测表取决于频率口径，本产物不作入库判断。",
            (
                "PC 侧 Reaxys 声明 Dielectric Constant 10 hits，但表内只渲染 7 行（差 3 行）；"
                "未读到的 3 行本轮未闭合。"
            ),
            (
                "EC / PC 在**观测表**里是 0 行（observation_table_distinct_T = 0），"
                "人工转录的 1 个温度点取自 **v03 冻结表**冠军行 —— 两个计数口径不同，不可混用。"
            ),
            "1,1,2,2-tetrafluoroethyl 2,2,2-trifluoroethyl ether（TTE）在 Reaxys 与本地都只有单点，缺口未闭合。",
        ],
    }


def write_queue(queue: list[dict]) -> None:
    with QUEUE_PATH.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=QUEUE_FIELDS, lineterminator="\n")
        w.writeheader()
        for i, row in enumerate(queue, start=1):
            w.writerow({"queue_rank": i, **row})


def write_summary(queue: list[dict], stats: dict) -> dict:
    summary = build_probe()
    summary["queue_stats"] = stats
    summary["queue_head"] = [
        {"rank": i, "name": r["name"], "inchikey": r["inchikey"], "family_tag": r["family_tag"],
         "stocking_priority": r["stocking_priority"], "local_distinct_T": r["local_distinct_T"]}
        for i, r in enumerate(queue[:20], start=1)
    ]
    summary["pipelines_not_run"] = (
        "本产物只做数据侧探测：不训练模型、不写 data/、不修改池、不产出任何 L3 读数的替代值。"
    )
    SUMMARY_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=1, sort_keys=False) + "\n",
                            encoding="utf-8", newline="\n")
    return summary


def write_report(summary: dict) -> None:
    stats = summary["queue_stats"]
    readings = summary["readings"]
    headline = summary["net_new_temperature_points"]
    n_points = sum(h["n_points"] for h in headline)
    n_sources = len({src for h in headline for src in h["sources"]})
    headline_txt = "；".join(f"{h['short']} {h['n_points']} 条 @{h['frequency_Hz'][0]}" for h in headline)
    lines: list[str] = []
    add = lines.append
    add("# Reaxys v1.x 备货扫描（第二刀补）")
    add("")
    add(f"**日期**：{PROBE_DATE}")
    add(f"**浏览器**：{summary['browser']}")
    add("**方法合规**：手动逐条查询（无批量抓取 / 无导出 / 无自动化遍历）；所有取值 `restricted_crosscheck_only`，"
        "永不进可分发数据集。**本产物确实含受限数值的机器可读镜像**（`readings[].rendered_rows` 与 "
        "`net_new_detail[].value` 是渲染表数值列的逐值转录），只存于本仓库与 week13 包内，禁止再次分发。")
    add("**产物**：`probes/reaxys_v1x_stocking_queue.csv`、`probes/reaxys_v1x_stocking_scan_summary.json`、"
        "`probes/reaxys_v1x_stocking_scan.py`、`probes/verify_reaxys_v1x_stocking_scan.py`")
    add("")
    add("## 0 结论速览")
    add("")
    add("| 问题 | 答案 |")
    add("| --- | --- |")
    add(f"| v1.x 温度线还缺多少？（**池内**口径） | 池内 {stats['pool_distinct_keys']} 个溶剂里，有 "
        f"**{stats['queue_size']}** 个在本地观测表里没有温度序列（<2 个不同温度）；池内**有**温度序列的是 "
        f"{stats['pool_members_with_two_or_more_distinct_T']} 个"
        f"（{stats['queue_size']} + {stats['pool_members_with_two_or_more_distinct_T']} = {stats['pool_distinct_keys']}） |")
    add(f"| 另有一个更大的计数是什么？（**全表**口径） | 观测表**全表** {stats['observation_compounds']} 个物质里"
        f"有温度序列的是 {stats['observation_table_compounds_with_two_or_more_distinct_T']} 个。"
        f"**这与上一行不是一个口径**（上一行只数池内成员），两者不可混用 |")
    add(f"| Reaxys 能补多少？ | 本轮探测 7 个物质，**净新增带温度的介电条目 {n_points} 条**"
        f"（{len(headline)} 个物质、{n_sources} 篇一手文献）：{headline_txt} |")
    add("| 冠军真值有没有被旁证？ | **没有独立旁证**。PC 那两条 25 C 是「汇编转述一致」"
        "（最终都指回 Riddick 4th ed. 汇编，见第 5 节）；EC 那条 89.78 被 Reaxys 标成 25 C，"
        "而本仓库既有溯源记为 40 C = 313.15 K —— 温度栏自相矛盾 |")
    add("| 前面的外部源全证伪结论要不要改？ | **不用改**。Reaxys 的净增益与「外部免费 ε(T) 扩张收官」的四源"
        "（ThermoML 在线 / ILThermo 温度维度 / DDB 免费层 / OA 直读）同向，都是极小。"
        "该四源结论各自的证据见 `reports/thermoml_online_topup_round6.md`、`reports/ilthermo_probe.md`、"
        "`reports/ddb_free_search_probe.md`、`reports/al_round3.md` |")
    add("")
    add("## 1 本轮先修正了一个自己的错")
    add("")
    add("按俗名（`adiponitrile` / `diglyme` / `triglyme` / `tetraglyme`）去本地表做覆盖度匹配，会**全部误判成 0 行**："
        "本地观测表用 IUPAC 登记名。真实情况是——")
    add("")
    add("| 物质 | 本地登记名 | 观测表温度点数（自动重算） | 已登记温度点数（人工转录） | 该计数取自哪张表 | 温度范围 |")
    add("| --- | --- | ---: | ---: | --- | --- |")
    for r in readings:
        if r["short"] in ("diglyme", "triglyme", "tetraglyme", "adiponitrile"):
            span = r["local_T_K"]
            span_txt = f"{span[0]}-{span[-1]} K" if len(span) > 1 else f"{span[0]} K"
            add(f"| {r['short']} | {r['compound']} | {r['observation_table_distinct_T']} | "
                f"{r['local_registered_distinct_T']} | `{r['local_registered_scope']}` | {span_txt} |")
    add("")
    add("`stocking_queue` 因此改为按 **InChIKey** 重算，不再依赖名称匹配。这条与本项目「新特征先过覆盖率检查」"
        "是同一类教训的另一面：**覆盖度检查本身也要用不依赖命名的键**。")
    add("")
    add("## 2 v1.x 备货队列（自动重算）")
    add("")
    add(f"- 池：`probes/l3_stage1_pilot_pool.csv`，{stats['pool_rows']} 行 / {stats['pool_distinct_keys']} 个 InChIKey"
        f"（sha256 复核 `{POOL_SHA256[:16]}...`）")
    add(f"- 观测表：`data/processed/dielectric_observations_v11plus.csv`，{stats['observation_rows']} 行 / "
        f"{stats['observation_compounds']} 个物质（sha256 复核 `{OBS_SHA256[:16]}...`）")
    add(f"- 队列：**{stats['queue_size']}** 个池成员没有温度序列；池内**有**温度序列的 "
        f"{stats['pool_members_with_two_or_more_distinct_T']} 个（两个数相加 = 池内 "
        f"{stats['pool_distinct_keys']} 个成员，脚本内已断言）")
    add(f"- 优先级口径：**P1 ≡ 池内 `is_champion=true` 的行**（本队列 {stats['queue_by_priority'].get('P1', 0)} 行），"
        f"不是硬编码物质名；P2 的 `model_ready` 条件在本队列上恒真"
        f"（{stats['model_ready_filter_is_vacuous_on_this_queue']}），因此 P2 实际只由族决定")
    add(f"- **P2 是族级复核顺序，不是可用性判断**：族集合 {{carbonate, lactone, glyme_ether, fluorinated}} 里的 "
        f"`fluorinated` 是子串规则，会把非电解液芳烃（{ '、'.join(stats['p2_fluorinated_examples']) } 等 "
        f"{stats['p2_rows_in_the_fluorinated_family']} 行）一并排进 P2。这些行只是**先被复核**，"
        f"不代表任何电池可用性；`stocking_priority` 全文都不得读成可用性结论")
    add("")
    add("优先级分布：" + "、".join(f"`{k}` {v}" for k, v in stats["queue_by_priority"].items()))
    add("")
    add("族分布：" + "、".join(f"`{k}` {v}" for k, v in stats["queue_by_family"].items()))
    add("")
    add("队列前 20（完整表见 CSV）：")
    add("")
    add("| # | 物质 | 族 | 优先级 | 本地温度点数 |")
    add("| ---: | --- | --- | --- | ---: |")
    for h in summary["queue_head"]:
        add(f"| {h['rank']} | {h['name']} | `{h['family_tag']}` | {h['stocking_priority']} | {h['local_distinct_T']} |")
    add("")
    add("## 3 Reaxys 探测读数（人工转录）")
    add("")
    add("| 物质 | CAS | Reaxys 声明条目 | 实际渲染行 | 温度序列？ | 观测表温度点数（自动） | "
        "已登记温度点数（人工） | 净新增温度点 | 判决 |")
    add("| --- | --- | ---: | ---: | --- | ---: | ---: | ---: | --- |")
    for r in readings:
        add(f"| {r['short']} | {r['cas'] or '—'} | {r['reaxys_dielectric_entries']} | {r['entries_rendered']} | "
            f"{'是' if r['temperature_series'] else '否'} | {r['observation_table_distinct_T']} | "
            f"{r['local_registered_distinct_T']}（`{r['local_registered_scope']}`） | "
            f"{r['net_new_temperature_points']} | `{r['verdict']}` |")
    add("")
    add("**两张表的「本地温度点数」不是一回事**（本报告上一版把 236 / 167 / 106 三个数写混，根因就在这里）："
        "EC / PC 在**观测表**里是 0 行 0 个温度点，人工转录的那 1 个点取自 **v03 冻结表**的冠军行；"
        "glyme 系与己二腈取自观测表，两张表计数恰好相同。列名已按来源分开，读者不应把两列相加。")
    add("### 3.1 逐物质要点")
    add("")
    for r in readings:
        add(f"**{r['short']}**（{r['compound']}，CAS {r['cas'] or '—'}）——{r['note']}")
        add("")
    add(f"## 4 净新增：{n_points} 条 / {len(headline)} 个物质 / {n_sources} 篇一手文献")
    add("")
    add("| 物质 | 净新增条目 | 温度点 (C) | 频率 (Hz) | 一手出处 | 口径限定 |")
    add("| --- | ---: | --- | --- | --- | --- |")
    for h in headline:
        add(f"| {h['short']} | {h['n_points']} | {h['temperature_points_C']} | {h['frequency_Hz']} | "
            + "<br>".join(h["sources"]) + f" | {h['qualifier']} |")
    add("")
    add("**口径限定（PC）**：PC 的「净新增 2 条」以 **v03 冻结表冠军行**（64.9 @ 298.15 K）为基线——"
        "PC 在**观测表**里是 0 行（`observation_table_distinct_T = 0`）。换成观测表基线这两条同样是净新增，"
        "但「本地已有 1 个点」这句话只对冻结表成立，基线切换在上一版里没有声明。")
    add("")
    add("**频率口径**：4 条净新增点全部带给定频率（PC 两条 2 MHz、tetraglyme 两条 1 MHz），"
        "与本地常温序列不是同一频率口径；能否并入 v1.x 观测表由 v1.x 的频率口径决定，本产物不作判断。")
    add("")
    add("tetraglyme 的 7 个已渲染温度点（1 MHz，14.99-54.99 C）里，前 5 个与本地 288.15-308.15 K 逐点重合"
        "（差 0.01 K，摄氏/开氏换算舍入），因此**可当本地两条 JCT/TCA 来源的独立复现**；净新增只有高端的 "
        "318.14 K 与 328.14 K。且这 7 点全部来自同一篇（Rivas et al. 2006, J. Chem. Thermodynamics, 38(3), 245-256），"
        "所以新增点的「独立性」只体现在测量方法与本地已有点不同，**不构成第二个独立来源**。")
    add("")
    add("## 5 冠军核对（判决按证据强度降级）")
    add("")
    add("| 冠军 | 冻结真值 | Reaxys 侧条目 | 判决 | 证据链要点 |")
    add("| --- | --- | --- | --- | --- |")
    for c in summary["cross_checks"]:
        add(f"| {c['champion']} | {c['frozen_truth']} | " + "；".join(c["reaxys_corroboration"])
            + f" | `{c['verdict']}` | {c['evidence_chain']['summary']} |")
    add("")
    for c in summary["cross_checks"]:
        chain = c["evidence_chain"]
        add(f"**{c['champion']}**：{chain['reading']}")
        add("")
        add(f"> 交叉引用 `{chain['cross_reference']}`：{chain['cross_reference_quote']}")
        add("")
    add("上一版把 PC 写成两个互相独立来源的复现，与本仓库自己的溯源结论相反："
        "`reports/jstage_corroboration.md` 已写明该值来自汇编转述。本轮把判决降级为 "
        "`compilation_restatement_agrees` 并把证据链写成机读字段，同时补上 EC 那条被漏用的既有事实。")
    add("")
    add("## 6 未闭合项")
    add("")
    for item in summary["open_items"]:
        add(f"- {item}")
    add("")
    add("## 7 纪律")
    add("")
    add("- 本产物**只做数据侧探测**：不训练模型、不写 `data/`、不改池、不产出任何 L3 读数的替代值；")
    add("- Reaxys 取值一律 `restricted_crosscheck_only`，provenance 为 `reaxys<-bibliographic_citation`"
        "（Reaxys 渲染表只给文献题录、不给 DOI，写成 `reaxys<-primary_doi` 不准确），需用时可回到一手文献；")
    add("- **本产物确实含受限数值的机器可读镜像**（`readings[].rendered_rows`、`net_new_detail[].value`）："
        "它只存于本仓库与 week13 交付包内，**禁止再次分发**，也不得并入任何可分发数据集；")
    add("- 队列 CSV 里的 `target_dielectric` / `target_T_K` 是**本地冻结表**的值，不是受限值；")
    add("- **本产物不产生任何通道可用性声明**：它不说介电通道可用、不说任何家族过门、"
        "不替代任何冻结读数、不改变任何 L3 结论；§5 的判决是**证据强度**判决，不是通道判决；")
    add(f"与「外部免费 ε(T) 扩张收官」的既有结论关系：**方向一致，不改结论**——Reaxys 的净增益是 "
        f"{n_points} 条 / {len(headline)} 个物质 / {n_sources} 篇一手文献，4 条全部带给定频率口径"
        f"（PC 2 MHz、tetraglyme 1 MHz）。")
    add("")
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8", newline="\n")


def main() -> int:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true", help="build in memory and report sizes without writing")
    args = ap.parse_args()

    queue, stats = build_queue()
    if args.check:
        print(f"queue_size={stats['queue_size']} by_priority={stats['queue_by_priority']}")
        print(f"by_family={stats['queue_by_family']}")
        return 0

    write_queue(queue)
    summary = write_summary(queue, stats)
    write_report(summary)
    print(f"wrote {QUEUE_PATH.name} rows={len(queue)}")
    print(f"wrote {SUMMARY_PATH.name} readings={len(summary['readings'])}")
    print(f"wrote {REPORT_PATH.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())