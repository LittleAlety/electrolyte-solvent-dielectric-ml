# -*- coding: utf-8 -*-
"""W46-C：tau_b 的噪声地板与功效分析工具（只读工具，不接主记分牌）。

动机。Gate 1 的阈 0.9 在 n = 7（21 对）下只允许至多 1 对不一致，观测到 tau_b = 0.4286；
调研报告的 P4 指出「机制脱节」与「功效不足」这两个解释必须**定量并列**，而不是文字并列。
本工具把这件事变成可复用件，三个方向：

* 正问题：给定 (tau_true, alpha, power) 求达到该功效所需的最小锚点数 n_min；
* 反问题：给定 n 求可检测最小 tau（MDE 曲线）；
* 回顾性功效：Gate 1（n = 7）在 tau_true in {0.4, 0.6, 0.8} 下的功效，以及「越过 0.9 阈」的概率。

统计口径（与 W33-B 同规格）。
* 零分布：Kendall tau_b（无并列）与逆序数 K 一一对应 `tau = 1 - 4K/(n(n-1))`，K 的
  Mahonian 分布由 `prod_{i=1..n}(1 + x + ... + x^{i-1})` 精确给出；精确 p 值用 Fraction 算。
* 替代模型（shifted-null）：`tau_alt = tau_true + (1 - tau_true) * tau_null`。tau_true = 0 时
  退化为零分布本身，故拒绝率与精确零分布逐点一致；`E[tau_alt] = tau_true`（零分布均值为 0）。
* 连续化：精确零分布是离散的，alpha = 0.05 一般落在两个网格点之间（n = 7 时精确拒绝率是
  174/5040 = 0.034524）。本工具把精确 `p_upper` 在 tau 网格上做**分段线性插值**，网格点上取值
  与精确值逐位相同（H46c2 的检查点），连续化之后 alpha 水平可精确达到（H46c1 的检查点）。
* 有限总体地板：`sd(N) = s0 * sqrt(1/N - 1/N_pop)`（R1 闭式，来自 W32 的 s0 与 N_pop）。
  闭式对应**有限总体**，精确零分布对应**无限总体**——两者只在同一 N 上并排展示，不相互替换。

只读；不写标签池或特征列；不占主记分牌 shot。
"""

from __future__ import annotations

import argparse
import json
import math
import random
from fractions import Fraction
from functools import lru_cache
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = REPOSITORY_ROOT / "probes" / "artifacts"
RANK_JSON = ARTIFACTS / "w32_rank_stability.json"

CHANNELS = ("dielectric", "orbital", "redox", "viscosity")
DEFAULT_ALPHA = 0.05
DEFAULT_POWER = 0.80
GATE1_N = 7
GATE1_THRESHOLD = 0.90
DEFAULT_N_GRID = (5, 6, 7, 8, 9, 10, 12, 15, 20, 25, 30)
RETROSPECTIVE_TAU_TRUE = (0.4, 0.6, 0.8)


# ---------------------------------------------------------------- 精确零分布

@lru_cache(maxsize=None)
def mahonian_counts(n: int) -> tuple:
    """逆序数为 K 的排列数（K = 0..n(n-1)/2），精确整数（不可变，内部缓存）。"""
    if n < 2:
        raise ValueError("n 必须 >= 2")
    counts = (1,)
    for size in range(2, n + 1):
        limit = size * (size - 1) // 2
        nxt = [0] * (limit + 1)
        for index, value in enumerate(counts):
            if value:
                for offset in range(size):
                    nxt[index + offset] += value
        counts = tuple(nxt)
    return counts


def tau_from_inversions(inversions: int, n: int) -> float:
    return 1.0 - 4.0 * inversions / (n * (n - 1))


def exact_sd(n: int) -> float:
    return math.sqrt(2.0 * (2 * n + 5) / (9.0 * n * (n - 1)))


_TAU_GRID_CACHE: dict = {}


def tau_grid(n: int) -> list:
    """返回 [(tau, count, p_upper_exact), ...]，K 由小到大（tau 由大到小，p 由小到大）。"""
    cached = _TAU_GRID_CACHE.get(n)
    if cached is not None:
        return cached
    counts = mahonian_counts(n)
    total = sum(counts)
    rows = []
    for inversions, count in enumerate(counts):
        rows.append((tau_from_inversions(inversions, n), count,
                     float(Fraction(sum(counts[:inversions + 1]), total))))
    _TAU_GRID_CACHE[n] = rows
    return rows


def exact_p_upper(n: int, tau: float) -> float:
    """精确 P(tau_null >= tau)（Fraction -> float），与 W33-B 同规格。"""
    if tau > 1.0:
        return 0.0
    if tau <= -1.0:
        return 1.0
    counts = mahonian_counts(n)
    total = sum(counts)
    keep = Fraction(0)
    for inversions, count in enumerate(counts):
        if tau_from_inversions(inversions, n) >= tau - 1e-12:
            keep += Fraction(count, total)
    return float(keep)


def critical_tau(n: int, alpha: float) -> float:
    """精确（离散）单侧临界 tau：累积概率仍 <= alpha 的最大 K 对应值。"""
    counts = mahonian_counts(n)
    total = sum(counts)
    target = Fraction(alpha).limit_denominator(10 ** 9)
    best = None
    cumulative = 0
    for inversions, count in enumerate(counts):
        cumulative += count
        if Fraction(cumulative, total) <= target:
            best = inversions
    return float("nan") if best is None else tau_from_inversions(best, n)


def exact_rejection_rate(n: int, alpha: float) -> float:
    """离散精确口径下 tau_true = 0 的拒绝率（保守，一般 < alpha）。"""
    crit = critical_tau(n, alpha)
    if math.isnan(crit):
        return 0.0
    return exact_p_upper(n, crit)


# ------------------------------------------------------- 连续化零分布与功效

def continuous_p_upper(n: int, tau: float) -> float:
    """精确 p_upper 在 tau 网格上的分段线性插值；网格点上与精确值逐位相同。"""
    if tau >= 1.0:
        return 0.0
    if tau <= -1.0:
        return 1.0
    rows = tau_grid(n)
    for index in range(len(rows) - 1):
        tau_hi, _count_hi, p_hi = rows[index]
        tau_lo, _count_lo, p_lo = rows[index + 1]
        if tau_lo <= tau <= tau_hi:
            if tau_hi == tau_lo:
                return p_hi
            weight = (tau_hi - tau) / (tau_hi - tau_lo)
            return p_hi + weight * (p_lo - p_hi)
    return 1.0


def continuous_null_quantile(n: int, tail_probability: float) -> float:
    """连续化零分布的逆 CDF：给定 U(0,1) 尾概率，返回对应 tau。

    `p_upper` 随 tau 递减，故 `p_upper(quantile(u)) = u` 在网格点上精确成立。
    """
    if tail_probability <= 0.0:
        return 1.0
    if tail_probability >= 1.0:
        return -1.0
    rows = tau_grid(n)
    if tail_probability <= rows[0][2]:
        return rows[0][0]
    for index in range(len(rows) - 1):
        tau_hi, _count_hi, p_hi = rows[index]
        tau_lo, _count_lo, p_lo = rows[index + 1]
        if p_hi <= tail_probability <= p_lo:
            if p_lo == p_hi:
                return tau_hi
            weight = (tail_probability - p_hi) / (p_lo - p_hi)
            return tau_hi + weight * (tau_lo - tau_hi)
    return rows[-1][0]


def continuous_critical_tau(n: int, alpha: float) -> float:
    """连续化口径下的 alpha 水平临界 tau（解 p_upper_cont(tau) = alpha）。"""
    return continuous_null_quantile(n, alpha)


def power(n: int, tau_true: float, alpha: float = DEFAULT_ALPHA) -> float:
    """shifted-null 模型下、连续化零分布上的检验功效 P(tau_alt >= crit)。"""
    if not 0.0 <= tau_true <= 1.0:
        raise ValueError("tau_true 必须在 [0, 1]")
    crit = continuous_critical_tau(n, alpha)
    if tau_true >= 1.0:
        return 1.0
    shifted = (crit - tau_true) / (1.0 - tau_true)
    return continuous_p_upper(n, shifted)


def power_discrete(n: int, tau_true: float, alpha: float = DEFAULT_ALPHA) -> float:
    """离散精确口径下的功效（保守下界），供并排展示。"""
    crit = critical_tau(n, alpha)
    if math.isnan(crit):
        return 0.0
    if tau_true >= 1.0:
        return 1.0
    shifted = (crit - tau_true) / (1.0 - tau_true)
    return exact_p_upper(n, shifted)


def prob_clear_threshold(n: int, tau_true: float, threshold: float) -> float:
    """P(tau_obs >= threshold)：观测值越过某个**实用阈值**（如 Gate 1 的 0.9）的概率。"""
    if tau_true >= 1.0:
        return 1.0
    shifted = (threshold - tau_true) / (1.0 - tau_true)
    return continuous_p_upper(n, shifted)


def mde(n: int, alpha: float = DEFAULT_ALPHA, power_target: float = DEFAULT_POWER,
        lo: float = 0.0, hi: float = 1.0, iterations: int = 200) -> float:
    """可检测最小 tau：满足 power(n, tau) >= power_target 的最小 tau。"""
    if power(n, 0.0, alpha) >= power_target:
        return 0.0
    for _ in range(iterations):
        mid = 0.5 * (lo + hi)
        if power(n, mid, alpha) >= power_target:
            hi = mid
        else:
            lo = mid
    return hi


def required_n(tau_true: float, alpha: float = DEFAULT_ALPHA,
               power_target: float = DEFAULT_POWER, n_max: int = 200) -> dict:
    """达到指定功效所需的最小锚点数；n_max 内不可达时 reachable=False。"""
    for n in range(2, n_max + 1):
        if power(n, tau_true, alpha) >= power_target:
            return {"n_min": n, "reachable": True, "n_max": n_max}
    return {"n_min": None, "reachable": False, "n_max": n_max}


def rejection_rate_mc(n: int, tau_true: float, alpha: float = DEFAULT_ALPHA,
                      draws: int = 200000, seed: int = 20261004) -> float:
    """蒙特卡洛拒绝率：从连续化零分布逆 CDF 抽样，套 shifted-null 与临界值判等。"""
    crit = continuous_critical_tau(n, alpha)
    rng = random.Random(seed)
    rejections = 0
    for _ in range(draws):
        tau_null = continuous_null_quantile(n, rng.random())
        tau_alt = tau_true + (1.0 - tau_true) * tau_null
        if tau_alt >= crit:
            rejections += 1
    return rejections / draws


def inversion_count(values) -> int:
    count = 0
    for index, value in enumerate(values):
        for other in values[index + 1:]:
            if value > other:
                count += 1
    return count


def rejection_rate_mc_permutation(n: int, tau_true: float, alpha: float = DEFAULT_ALPHA,
                                  draws: int = 100000, seed: int = 20261004) -> float:
    """离散精确零分布上的蒙特卡洛拒绝率：直接抽随机排列（真零分布，非连续化）。

    判等用**离散精确临界值**（operational exact test），所以 tau_true = 0 时结果应收敛到
    `exact_rejection_rate(n, alpha)`，而不是名义 alpha——这正是离散口径的保守缺口。
    """
    crit = critical_tau(n, alpha)
    if math.isnan(crit):
        return 0.0
    rng = random.Random(seed)
    base = list(range(n))
    rejections = 0
    for _ in range(draws):
        tau_null = tau_from_inversions(inversion_count(rng.sample(base, n)), n)
        tau_alt = tau_true + (1.0 - tau_true) * tau_null
        if tau_alt >= crit:
            rejections += 1
    return rejections / draws


# ------------------------------------------------------------ 有限总体地板

def load_channels() -> dict:
    if not RANK_JSON.is_file():
        return {}
    payload = json.loads(RANK_JSON.read_text(encoding="utf-8-sig"))
    out = {}
    for row in payload.get("channels", []):
        out[row["channel"]] = {"label": row["label"], "s0": float(row["s0_median"]),
                              "n_population": float(row["n_population_median"])}
    return out


def finite_population_sd(n: int, s0: float, n_population: float) -> float:
    """R1 闭式：sd(N) = s0 * sqrt(1/N - 1/N_pop)（有限总体）。"""
    inner = 1.0 / n - 1.0 / n_population
    return s0 * math.sqrt(inner) if inner > 0 else float("nan")


def required_n_for_delta(s0: float, n_population: float, delta_tau: float,
                         factor: float = 2.80 * math.sqrt(2.0)) -> dict:
    """给定目标可分辨差 Delta tau，闭式反解所需 N（80% 功效口径）。"""
    inner = (delta_tau / (factor * s0)) ** 2 + 1.0 / n_population
    if inner <= 0:
        return {"required_n": float("inf"), "reachable": False}
    value = 1.0 / inner
    return {"required_n": value, "reachable": bool(value <= n_population)}


# --------------------------------------------------------------------- CLI

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("table", "power", "mde", "required-n", "retro", "mc"),
                        default="retro")
    parser.add_argument("--n", type=int, default=GATE1_N)
    parser.add_argument("--tau-true", type=float, default=0.6)
    parser.add_argument("--alpha", type=float, default=DEFAULT_ALPHA)
    parser.add_argument("--power", type=float, default=DEFAULT_POWER)
    parser.add_argument("--threshold", type=float, default=GATE1_THRESHOLD)
    parser.add_argument("--draws", type=int, default=200000)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    if args.mode == "table":
        payload = [{"n": n, "tau": tau, "count": count, "p_upper_exact": p}
                   for n in (args.n,) for (tau, count, p) in tau_grid(n)]
    elif args.mode == "power":
        payload = {"n": args.n, "tau_true": args.tau_true, "alpha": args.alpha,
                   "power": power(args.n, args.tau_true, args.alpha),
                   "power_discrete": power_discrete(args.n, args.tau_true, args.alpha),
                   "critical_tau_continuous": continuous_critical_tau(args.n, args.alpha),
                   "critical_tau_discrete": critical_tau(args.n, args.alpha)}
    elif args.mode == "mde":
        payload = {"n": args.n, "alpha": args.alpha, "power_target": args.power,
                   "mde": mde(args.n, args.alpha, args.power)}
    elif args.mode == "required-n":
        payload = required_n(args.tau_true, args.alpha, args.power)
    elif args.mode == "mc":
        payload = {"n": args.n, "tau_true": args.tau_true, "alpha": args.alpha,
                   "draws": args.draws,
                   "rejection_rate": rejection_rate_mc(args.n, args.tau_true, args.alpha,
                                                       args.draws)}
    else:
        payload = {"n": args.n, "alpha": args.alpha, "threshold": args.threshold,
                   "rows": [{"tau_true": t, "power": power(args.n, t, args.alpha),
                             "prob_clear_threshold": prob_clear_threshold(args.n, t, args.threshold)}
                            for t in RETROSPECTIVE_TAU_TRUE]}
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
