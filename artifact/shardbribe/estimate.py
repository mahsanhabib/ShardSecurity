r"""RQ8 estimation + pre-registered falsification engine (network-free).

This module turns measured latency/enforcement samples -- produced by
``livemeasure.py`` on real systems, or by ``testbed.py`` as a synthetic oracle --
into the paper's load-bearing quantities and a *frozen* verdict, exactly per
``PREREGISTRATION-rq8.md`` (tag ``prereg/rq8-v1``).

It contacts no network and depends only on the standard library + numpy, so it
sits on the reproducible path: ``run_all.py`` may call ``run()`` over committed
``results/measured/*.jsonl`` and the figures/tables regenerate deterministically.

Quantities (definitions verbatim from the paper):
  q          = Pr[t_slash < t_withdraw]          (Clopper-Pearson / Wilson / rule-of-three)
  T_acc      = detect -> propagate -> enforce -> revert   (decomposed; lo/hi bounds)
  T_settle   = dest receipt + withdrawal beyond clawback
  rho        = T_acc / T_settle
  p_win      = Pr[T_settle < T_acc]              (PAIRED only; BCa + Wilson upper)

Decision rule (frozen, PREREGISTRATION-rq8.md sec 4.3):
  OPEN      iff  upperCI(p_win) > eps  AND  CI(median rho) excludes 1 from below
                 AND  G2 clearable           [evaluated against T_acc_lo]
  RULED_OUT iff  structurally finality-gated  OR  upperCI(p_win) <= eps everywhere
                 [evaluated against T_acc_hi]
  INDETERMINATE otherwise (never a silent "no window").
"""
from __future__ import annotations

import json
import math
import statistics
from dataclasses import dataclass, field, asdict
from pathlib import Path

import numpy as np

EPS_DEFAULT = 0.05
ALPHA_DEFAULT = 0.05


# ==========================================================================
# scipy-free special functions (only what the estimators need)
# ==========================================================================
def _norm_cdf(x: float) -> float:
    return 0.5 * math.erfc(-x / math.sqrt(2.0))


def _norm_ppf(p: float) -> float:
    """Inverse standard-normal CDF (Acklam's rational approximation)."""
    if not 0.0 < p < 1.0:
        return -math.inf if p <= 0.0 else math.inf
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00]
    plow, phigh = 0.02425, 1 - 0.02425
    if p < plow:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
               ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    if p > phigh:
        q = math.sqrt(-2 * math.log(1 - p))
        return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
                ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    q = p - 0.5
    r = q * q
    return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q / \
           (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)


def _betacf(a: float, b: float, x: float) -> float:
    MAXIT, EPS, FPMIN = 200, 3e-12, 1e-300
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < FPMIN:
        d = FPMIN
    d = 1.0 / d
    h = d
    for m in range(1, MAXIT + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < FPMIN:
            d = FPMIN
        c = 1.0 + aa / c
        if abs(c) < FPMIN:
            c = FPMIN
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < FPMIN:
            d = FPMIN
        c = 1.0 + aa / c
        if abs(c) < FPMIN:
            c = FPMIN
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < EPS:
            break
    return h


def betainc(a: float, b: float, x: float) -> float:
    """Regularized incomplete beta I_x(a,b)."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    lbeta = math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
    bt = math.exp(lbeta + a * math.log(x) + b * math.log(1.0 - x))
    if x < (a + 1.0) / (a + b + 2.0):
        return bt * _betacf(a, b, x) / a
    return 1.0 - bt * _betacf(b, a, 1.0 - x) / b


def betainv(p: float, a: float, b: float) -> float:
    """Inverse of I_x(a,b) by bisection (robust, monotone)."""
    if p <= 0.0:
        return 0.0
    if p >= 1.0:
        return 1.0
    lo, hi = 0.0, 1.0
    for _ in range(100):
        mid = 0.5 * (lo + hi)
        if betainc(a, b, mid) < p:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def _gammp(a: float, x: float) -> float:
    """Regularized lower incomplete gamma P(a,x) (series + continued fraction)."""
    if x <= 0.0:
        return 0.0
    if x < a + 1.0:                       # series
        ap, total, term = a, 1.0 / a, 1.0 / a
        for _ in range(300):
            ap += 1.0
            term *= x / ap
            total += term
            if abs(term) < abs(total) * 1e-12:
                break
        return total * math.exp(-x + a * math.log(x) - math.lgamma(a))
    # continued fraction for Q(a,x), then P = 1-Q
    FPMIN = 1e-300
    b = x + 1.0 - a
    c = 1.0 / FPMIN
    d = 1.0 / b
    h = d
    for i in range(1, 300):
        an = -i * (i - a)
        b += 2.0
        d = an * d + b
        if abs(d) < FPMIN:
            d = FPMIN
        c = b + an / c
        if abs(c) < FPMIN:
            c = FPMIN
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 1e-12:
            break
    q = math.exp(-x + a * math.log(x) - math.lgamma(a)) * h
    return 1.0 - q


# ==========================================================================
# q : Bernoulli enforcement-before-unslashable
# ==========================================================================
def clopper_pearson(k: int, n: int, alpha: float = ALPHA_DEFAULT) -> tuple:
    """Exact two-sided Clopper-Pearson CI for a binomial proportion."""
    if n == 0:
        return (0.0, 1.0)
    lo = 0.0 if k == 0 else betainv(alpha / 2, k, n - k + 1)
    hi = 1.0 if k == n else betainv(1 - alpha / 2, k + 1, n - k)
    return (lo, hi)


def wilson(k: int, n: int, alpha: float = ALPHA_DEFAULT, one_sided: bool = False) -> tuple:
    """Wilson score interval; one_sided=True returns the (one-sided) upper bound
    using z_{1-alpha} (well-behaved at p_hat = 0 / 1, used by the decision rule)."""
    if n == 0:
        return (0.0, 1.0)
    z = _norm_ppf(1 - alpha) if one_sided else _norm_ppf(1 - alpha / 2)
    p = k / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = (z / denom) * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (max(0.0, center - half), min(1.0, center + half))


def rule_of_three(n: int, conf: float = 0.95) -> float:
    """Upper bound on a proportion when 0 events were observed (~3/n at 95%)."""
    if n == 0:
        return 1.0
    return 1.0 - (1.0 - conf) ** (1.0 / n)


def q_interval(k_enforced: int, n: int, *, age_cap_undetected: float = 0.0,
               alpha: float = ALPHA_DEFAULT) -> dict:
    """q reported as an interval per PREREGISTRATION sec 4.1.

    point/ci : Clopper-Pearson on the *detected* incidents (an UPPER bound on q,
               since these are conditioned on enforcement having happened).
    lower_adjusted : deflates the point by an evidence-age-cap / undetected-
               infraction proxy mass in [0,1] (share of infractions that plausibly
               never produced enforceable evidence in time).
    """
    point = (k_enforced / n) if n else float("nan")
    lo, hi = clopper_pearson(k_enforced, n, alpha)
    if k_enforced == 0:
        hi = max(hi, rule_of_three(n))
    lower_adjusted = point * (1.0 - age_cap_undetected) if n else float("nan")
    return {"q_point_upper_bound": point, "ci": [lo, hi], "n": n,
            "lower_adjusted": lower_adjusted, "method": "clopper_pearson+age_cap",
            "note": "point is an UPPER bound on q (survivorship-conditioned)"}


# ==========================================================================
# distributions : fit + GOF + tail index for T_acc / T_settle
# ==========================================================================
def ecdf(x):
    xs = np.sort(np.asarray(x, float))
    return xs, np.arange(1, len(xs) + 1) / len(xs)


def quantile(x, p: float) -> float:
    return float(np.percentile(np.asarray(x, float), 100 * p))


def _gamma_cdf(x, shape, scale):
    return np.array([_gammp(shape, max(v, 0.0) / scale) for v in np.atleast_1d(x)])


def _lognorm_cdf(x, mu, sigma):
    x = np.atleast_1d(np.asarray(x, float))
    out = np.zeros_like(x)
    pos = x > 0
    out[pos] = 0.5 * np.array([math.erfc(-(math.log(v) - mu) / (sigma * math.sqrt(2)))
                               for v in x[pos]])
    return out


def ks_stat(x, cdf_fn) -> float:
    xs, emp = ecdf(x)
    theo = np.asarray(cdf_fn(xs), float)
    return float(np.max(np.abs(emp - theo)))


def hill_index(x, tail_frac: float = 0.1) -> float:
    """Hill estimator of the tail index; small => heavy tail (a finding: heavy
    T_acc tails widen the window). Returns inf for a light/degenerate tail."""
    xs = np.sort(np.asarray(x, float))
    k = max(2, int(len(xs) * tail_frac))
    top = xs[-k:]
    if top[0] <= 0:
        return float("inf")
    logs = np.log(top) - math.log(top[0])
    m = float(np.mean(logs[1:])) if len(logs) > 1 else 0.0
    return float("inf") if m <= 0 else 1.0 / m


def fit_select(x) -> dict:
    """Fit Gamma (MoM) and log-normal (MLE), rank by AIC + report KS, empirical
    quantiles, and the Hill tail index. The decision statistic uses the EMPIRICAL
    quantiles (distribution-free); the parametric fit is descriptive."""
    x = np.asarray(x, float)
    x = x[np.isfinite(x) & (x > 0)]
    n = len(x)
    out = {"n": n, "empirical_quantiles": {}}
    if n == 0:
        return out
    # Empirical quantiles are well-defined for any n>=1 (a single real measurement
    # is its own quantile); only the parametric fit / tail index need n>=3.
    for p in (0.05, 0.5, 0.9, 0.95, 0.99):
        out["empirical_quantiles"][str(p)] = quantile(x, p)
    if n < 3:
        return out
    out["hill_tail_index"] = hill_index(x)

    mean, var = float(np.mean(x)), float(np.var(x, ddof=1))
    g_shape = mean * mean / var if var > 0 else float("inf")
    g_scale = var / mean if mean > 0 else float("inf")
    if math.isfinite(g_shape):
        ll_g = float(np.sum((g_shape - 1) * np.log(x) - x / g_scale
                            - g_shape * math.log(g_scale) - math.lgamma(g_shape)))
        out["gamma"] = {"shape": g_shape, "scale": g_scale,
                        "aic": 2 * 2 - 2 * ll_g,
                        "ks": ks_stat(x, lambda z: _gamma_cdf(z, g_shape, g_scale))}
    lx = np.log(x)
    mu, sigma = float(np.mean(lx)), float(np.std(lx, ddof=1))
    if sigma > 0:
        ll_l = float(np.sum(-np.log(x * sigma * math.sqrt(2 * math.pi))
                            - (lx - mu) ** 2 / (2 * sigma * sigma)))
        out["lognormal"] = {"mu": mu, "sigma": sigma, "aic": 2 * 2 - 2 * ll_l,
                            "ks": ks_stat(x, lambda z: _lognorm_cdf(z, mu, sigma))}
    aics = {k: v["aic"] for k, v in out.items()
            if isinstance(v, dict) and "aic" in v}
    if aics:
        out["best_by_aic"] = min(aics, key=aics.get)
    return out


# ==========================================================================
# p_win (PAIRED) and rho
# ==========================================================================
def pwin_point(settle, acc) -> float:
    s, a = np.asarray(settle, float), np.asarray(acc, float)
    return float(np.mean(s < a))


def _bca_ci(samples, stat_fn, theta_hat, B, alpha, rng):
    """Bias-corrected & accelerated bootstrap CI for a paired statistic.
    `samples` is an (n, d) array of paired rows; stat_fn(rows)->float."""
    n = len(samples)
    boots = np.empty(B)
    for b in range(B):
        idx = rng.integers(0, n, n)
        boots[b] = stat_fn(samples[idx])
    prop = float(np.mean(boots < theta_hat))
    prop = min(max(prop, 1.0 / (B + 1)), 1.0 - 1.0 / (B + 1))
    z0 = _norm_ppf(prop)
    # jackknife acceleration
    jack = np.empty(n)
    allidx = np.arange(n)
    for i in range(n):
        jack[i] = stat_fn(samples[allidx != i])
    jbar = float(np.mean(jack))
    num = float(np.sum((jbar - jack) ** 3))
    den = 6.0 * (float(np.sum((jbar - jack) ** 2)) ** 1.5) + 1e-300
    a_acc = num / den
    def adj(z):
        return _norm_cdf(z0 + (z0 + z) / (1 - a_acc * (z0 + z)))
    a1 = adj(_norm_ppf(alpha / 2))
    a2 = adj(_norm_ppf(1 - alpha / 2))
    lo = float(np.percentile(boots, 100 * a1))
    hi = float(np.percentile(boots, 100 * a2))
    return lo, hi, float(np.mean(boots))


def pwin_bca(settle, acc, B: int = 10000, alpha: float = ALPHA_DEFAULT,
             seed: int = 0) -> dict:
    """Paired p_win = Pr[T_settle < T_acc] with BCa CI (shape robustness) AND a
    one-sided Wilson upper bound on the win proportion (used by the decision rule).
    Requires PAIRED observations (same t=0, network draw, epoch)."""
    s = np.asarray(settle, float)
    a = np.asarray(acc, float)
    assert len(s) == len(a) and len(s) > 0, "p_win requires paired, non-empty data"
    rows = np.column_stack([s, a])
    theta = pwin_point(s, a)
    rng = np.random.default_rng(seed)
    lo, hi, mean_b = _bca_ci(rows, lambda r: pwin_point(r[:, 0], r[:, 1]),
                             theta, B, alpha, rng)
    wins = int(np.sum(s < a))
    w_lo, w_hi = wilson(wins, len(s), alpha, one_sided=False)
    _, upper_1s = wilson(wins, len(s), alpha, one_sided=True)
    return {"p_win": theta, "n": len(s), "wins": wins,
            "bca_ci": [lo, hi], "bca_mean": mean_b,
            "wilson_ci": [w_lo, w_hi], "wilson_upper_one_sided": upper_1s}


def rho_summary(settle, acc, B: int = 10000, alpha: float = ALPHA_DEFAULT,
                seed: int = 0) -> dict:
    """rho = T_acc / T_settle: mean-ratio (matches testbed.measure_pwin) and
    median-ratio, each with a percentile-bootstrap CI. The decision rule asks
    whether the median-ratio CI excludes 1 from below."""
    s = np.asarray(settle, float)
    a = np.asarray(acc, float)
    n = len(s)
    mean_ratio = float(np.mean(a) / np.mean(s))
    med_ratio = float(np.median(a) / np.median(s))
    rng = np.random.default_rng(seed)
    bm, bmed = np.empty(B), np.empty(B)
    for b in range(B):
        idx = rng.integers(0, n, n)
        bm[b] = np.mean(a[idx]) / np.mean(s[idx])
        bmed[b] = np.median(a[idx]) / np.median(s[idx])
    return {"mean_ratio": mean_ratio, "median_ratio": med_ratio,
            "mean_ratio_ci": [float(np.percentile(bm, 100 * alpha / 2)),
                              float(np.percentile(bm, 100 * (1 - alpha / 2)))],
            "median_ratio_ci": [float(np.percentile(bmed, 100 * alpha / 2)),
                                float(np.percentile(bmed, 100 * (1 - alpha / 2)))]}


def power_pwin_zero(n: int, alpha: float = ALPHA_DEFAULT) -> float:
    """Wilson one-sided upper bound on p_win when 0 wins are observed in n paired
    runs -- the planning quantity behind the 'N>=40' / 'N>=300' sample sizes."""
    _, upper = wilson(0, n, alpha, one_sided=True)
    return upper


def distance_to_cliff(t_acc_samples, t_settle_samples,
                      alpha: float = ALPHA_DEFAULT) -> dict:
    """T*_settle = q_alpha(T_acc): the settlement speed at which the design flips
    to exposed, and how far the measured T_settle sits above it.

    Only T_acc is required to locate the cliff (T*_settle = q_alpha(T_acc)); the
    settlement leg is optional. For a finality-gated path that carries only the
    accountability arm (e.g. passive Cosmos q_max), the cliff is still defined --
    median_T_settle/margin are simply reported as None when no T_settle exists."""
    if t_acc_samples is None or len(t_acc_samples) == 0:
        return {}
    t_star = quantile(t_acc_samples, alpha)
    has_settle = t_settle_samples is not None and len(t_settle_samples) > 0
    med_settle = quantile(t_settle_samples, 0.5) if has_settle else None
    margin = (med_settle - t_star) if med_settle is not None else None
    return {"T_star_settle": t_star, "median_T_settle": med_settle,
            "margin": margin,
            "exposed_if_settle_below": t_star}


# ==========================================================================
# frozen verdict
# ==========================================================================
@dataclass
class Verdict:
    system: str
    path: str
    verdict: str                       # OPEN | RULED_OUT | INDETERMINATE
    q: dict = field(default_factory=dict)
    p_win: dict = field(default_factory=dict)
    rho: dict = field(default_factory=dict)
    T_acc_lo: dict = field(default_factory=dict)
    T_acc_hi: dict = field(default_factory=dict)
    T_settle: dict = field(default_factory=dict)
    distance_to_cliff: dict = field(default_factory=dict)
    g2_classic_clearable: bool = False
    g2_solver_clearable: bool = False
    reorg_alone_suffices: bool = False
    rationale: str = ""

    def to_dict(self):
        return asdict(self)


def apply_decision_rule(*, system: str, path: str,
                        pwin_stats: dict, rho_stats: dict, q_stats: dict,
                        structurally_gated: bool,
                        g2_classic_clearable: bool,
                        g2_solver_clearable: bool = False,
                        reorg_alone_suffices: bool = False,
                        eps: float = EPS_DEFAULT) -> Verdict:
    """The frozen rule of PREREGISTRATION-rq8.md sec 4.3.

    NOTE on bias direction (load-bearing): the caller must supply `pwin_stats`
    computed against T_acc_lo for the OPEN branch and against T_acc_hi for the
    RULED_OUT branch (each uses the bound working *against* its own claim). In
    practice run two pwin computations and pass the relevant one; this function
    applies the inequalities.
    """
    upper = pwin_stats.get("wilson_upper_one_sided", 1.0)
    pwin_n = pwin_stats.get("n", 0)
    med_ci_lo = (rho_stats.get("median_ratio_ci") or [0, 0])[0]
    # A path is only evaluable for p_win when paired (T_settle,T_acc) data exist.
    # A settlement-only marginal (e.g. passive bridge replay) must NOT collapse to
    # RULED_OUT -- the paired p_win comes from the devnet self-fill arm (prereg 4.1).
    open_window = (pwin_n > 0 and upper > eps and med_ci_lo > 1.0
                   and g2_classic_clearable)
    ruled_out = structurally_gated or (pwin_n > 0 and upper <= eps)

    if structurally_gated or (ruled_out and not open_window):
        v, why = "RULED_OUT", (
            "structurally finality-gated (Prop.1)" if structurally_gated
            else f"upperCI(p_win)={upper:.3f} <= eps={eps} against adversarial T_acc")
    elif open_window and not ruled_out:
        v, why = "OPEN", (
            f"upperCI(p_win)={upper:.3f} > eps, median-rho CI lower bound "
            f"{med_ci_lo:.2f} > 1, G2 clearable")
    elif pwin_n == 0 and not structurally_gated:
        v, why = "INDETERMINATE", (
            "settlement marginal only; paired (T_settle,T_acc) self-fill episodes "
            "needed for a p_win verdict (prereg 4.1)")
    else:
        v, why = "INDETERMINATE", (
            f"upperCI(p_win)={upper:.3f}, median-rho CI lower={med_ci_lo:.2f}; "
            "report CI and additional N needed")
    return Verdict(system=system, path=path, verdict=v,
                   q=q_stats, p_win=pwin_stats, rho=rho_stats,
                   g2_classic_clearable=g2_classic_clearable,
                   g2_solver_clearable=g2_solver_clearable,
                   reorg_alone_suffices=reorg_alone_suffices, rationale=why)


# ==========================================================================
# driver over committed measured records (called by run_all.py if present)
# ==========================================================================
def _load_jsonl(path: Path) -> list:
    rows = []
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def estimate_path(records: list, *, system: str, path: str,
                  structurally_gated: bool, g2_classic_clearable: bool,
                  g2_solver_clearable: bool = False,
                  reorg_alone_suffices: bool = False,
                  B: int = 10000, alpha: float = ALPHA_DEFAULT,
                  eps: float = EPS_DEFAULT, seed: int = 0) -> dict:
    """Full estimation for one value-realizing path from extended-schema records.

    Records may carry only the q/T_acc arm (passive Cosmos), only the settlement
    arm (bridge replay), or both (devnet episodes). p_win/rho are computed only
    over records with BOTH legs paired; q is computed from the q-arm independently;
    the latency fits use whichever leg is present.
    """
    live = [r for r in records if r.get("fork_formed", True)]
    paired = [(r["T_settle"], r["T_acc"]) for r in live
              if r.get("T_settle") is not None and r.get("T_acc") is not None]
    if paired:
        settle = [p[0] for p in paired]
        acc_p = [p[1] for p in paired]
        pw = pwin_bca(settle, acc_p, B=B, alpha=alpha, seed=seed)
        rs = rho_summary(settle, acc_p, B=B, alpha=alpha, seed=seed)
    else:                                   # no paired observations on this path
        pw = {"p_win": 0.0, "n": 0, "wins": 0, "wilson_upper_one_sided": 0.0,
              "note": "no paired (T_settle,T_acc) records on this path"}
        rs = {"median_ratio": None, "median_ratio_ci": [0.0, 0.0],
              "note": "n/a (unpaired)"}
    acc = [r["T_acc"] for r in live if r.get("T_acc") is not None]
    settle = [r["T_settle"] for r in live if r.get("T_settle") is not None]
    # q from the q-arm fields when present
    enforced = [1 for r in records
                if r.get("t_slash_effective") is not None
                and r.get("t_withdraw_unslashable") is not None
                and r["t_slash_effective"] < r["t_withdraw_unslashable"]]
    n_q = sum(1 for r in records if r.get("t_slash_effective") is not None)
    qd = q_interval(len(enforced), n_q) if n_q else {"q_point_upper_bound": None}
    # Arm-C provenance: whether the unslashable deadline on this path is an OBSERVED
    # unbonding completion (real client code, run_arm.sh C) rather than an analytic
    # exit, plus the caught (clawback) rate. Lets make_tables flip the positive-control
    # wording to "observed unbonding completion" only when the data actually carries it.
    n_unbond = sum(1 for r in records if r.get("unbond_caught") is not None)
    n_caught = sum(1 for r in records if r.get("unbond_caught") is True)
    unbond_observed = any(r.get("t_unbond_complete") is not None for r in records)
    verdict = apply_decision_rule(
        system=system, path=path, pwin_stats=pw, rho_stats=rs, q_stats=qd,
        structurally_gated=structurally_gated,
        g2_classic_clearable=g2_classic_clearable,
        g2_solver_clearable=g2_solver_clearable,
        reorg_alone_suffices=reorg_alone_suffices, eps=eps)
    out = verdict.to_dict()
    out["T_acc_fit"] = fit_select(acc)
    out["T_settle_fit"] = fit_select(settle)
    out["distance_to_cliff"] = (distance_to_cliff(acc, settle, alpha)
                                if acc else {})
    out["unbond_observed"] = unbond_observed
    out["n_unbond"] = n_unbond
    out["unbond_caught_frac"] = (n_caught / n_unbond) if n_unbond else None
    return out


def run(cfg: dict) -> dict:
    """Entry point for run_all.py. Reads cfg['rq8'] and committed measured
    records; returns the per-path verdicts. Graceful no-op if absent so the
    existing reproduction path is unchanged when no measurement has been run."""
    rq8 = (cfg or {}).get("rq8")
    if not rq8:
        return {"status": "skipped: no rq8 config"}
    mdir = Path(rq8.get("measured_dir", "results/measured"))
    if not mdir.exists():
        return {"status": f"skipped: {mdir} absent (no measurement yet)"}
    B = int(rq8.get("bootstrap_resamples", 10000))
    eps = float(rq8.get("epsilon", EPS_DEFAULT))
    seed = int(cfg.get("seed", 0))
    paths_cfg = rq8.get("paths", {})
    results = {}
    for f in sorted(mdir.glob("*.jsonl")):
        records = _load_jsonl(f)
        if not records:
            continue
        meta = paths_cfg.get(f.stem, {})
        results[f.stem] = estimate_path(
            records, system=meta.get("system", f.stem),
            path=meta.get("path", f.stem),
            structurally_gated=bool(meta.get("structurally_gated", False)),
            g2_classic_clearable=bool(meta.get("g2_classic_clearable", False)),
            g2_solver_clearable=bool(meta.get("g2_solver_clearable", False)),
            reorg_alone_suffices=bool(meta.get("reorg_alone_suffices", False)),
            B=B, eps=eps, seed=seed)
    return {"status": "ok", "paths": results}


# ==========================================================================
# self-test: validate the estimators against testbed.measure_pwin as an oracle
# ==========================================================================
def collect_from_testbed(p, runs: int, seed: int) -> dict:
    """Loop testbed.run_round into PAIRED (T_settle, T_acc) arrays."""
    from .testbed import run_round
    settle, acc = [], []
    for i in range(runs):
        r = run_round(p, seed + i)
        if r["fork_formed"]:
            settle.append(r["T_settle"]); acc.append(r["T_acc"])
    return {"settle": settle, "acc": acc}


def self_test(runs: int = 300, seed: int = 20240917) -> dict:
    """estimate.py must recover testbed.measure_pwin's pwin/rho within CI before
    any real data is trusted. Returns the comparison; raises on mismatch."""
    from .testbed import TestbedParams, measure_pwin
    p = TestbedParams()
    oracle = measure_pwin(p, runs, seed)
    paired = collect_from_testbed(p, runs, seed)
    pw = pwin_bca(paired["settle"], paired["acc"], B=2000, seed=seed)
    rs = rho_summary(paired["settle"], paired["acc"], B=2000, seed=seed)
    assert abs(pw["p_win"] - oracle["pwin_measured"]) < 1e-9, "p_win definition drift"
    assert abs(rs["mean_ratio"] - oracle["rho_measured"]) < 1e-9, "rho definition drift"
    return {"ok": True, "oracle_pwin": oracle["pwin_measured"],
            "estimate_pwin": pw["p_win"], "pwin_bca_ci": pw["bca_ci"],
            "oracle_rho": oracle["rho_measured"], "estimate_rho": rs["mean_ratio"]}


if __name__ == "__main__":
    print(json.dumps(self_test(), indent=2))
