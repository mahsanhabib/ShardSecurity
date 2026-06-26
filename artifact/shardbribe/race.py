"""Monte-Carlo accountability-race simulator (Tsettle vs Tacc).

The race begins when the conflicting certificate exists (t=0).  Two latencies
compete:

    Tsettle = (destination receipt processing) + (withdrawal beyond clawback)
    Tacc    = (observe both certs) + (propagate proof)
            + (enforce slashing)   + (revert / quarantine branch)

Each is a sum of independent positive stage latencies; we model each stage as a
gamma random variable so that the totals are positive, right-skewed, and have a
tunable coefficient of variation.  ``pwin = Pr[Tsettle < Tacc]`` is estimated
by Monte-Carlo.  The simulator is parameterized by the *latency ratio*
``rho = E[Tacc] / E[Tsettle]`` so the threshold behaviour around ``rho = 1`` is
visible directly.
"""
from __future__ import annotations

import numpy as np


def _gamma_sum(rng, mean_total: float, n_stages: int, cv: float, size: int):
    """Sample a sum of ``n_stages`` i.i.d. gamma stages with given total mean
    and per-total coefficient of variation ``cv`` (std/mean)."""
    if mean_total <= 0:
        return np.zeros(size)
    # For a sum of n iid gammas, choose per-stage shape so the *total* has the
    # requested cv.  Total variance = n * (theta^2 * kshape); with equal stages
    # mean_total = n*kshape*theta, so cv_total = 1/sqrt(n*kshape).  Solve kshape.
    kshape = 1.0 / (n_stages * cv * cv)
    theta = mean_total / (n_stages * kshape)
    samples = rng.gamma(kshape, theta, size=(size, n_stages)).sum(axis=1)
    return samples


def simulate_pwin(rho: float, trials: int, seed: int,
                  settle_mean: float = 1.0,
                  settle_stages: int = 2, acc_stages: int = 4,
                  settle_cv: float = 0.3, acc_cv: float = 0.3,
                  gated: bool = False) -> dict:
    """Estimate pwin = Pr[Tsettle < Tacc] at latency ratio ``rho``.

    ``rho = E[Tacc]/E[Tsettle]``.  With ``gated=True`` the protocol enforces
    Tsettle >= Tacc on every value-bearing effect, so pwin is identically 0
    (the immunity baseline of Proposition 1).
    """
    rng = np.random.default_rng(seed)
    acc_mean = rho * settle_mean
    t_settle = _gamma_sum(rng, settle_mean, settle_stages, settle_cv, trials)
    t_acc = _gamma_sum(rng, acc_mean, acc_stages, acc_cv, trials)
    if gated:
        # finality-gate: clamp settlement to not precede accountability
        t_settle = np.maximum(t_settle, t_acc)
    wins = np.count_nonzero(t_settle < t_acc)
    return {
        "rho": rho,
        "trials": trials,
        "pwin": wins / trials,
        "settle_cv": settle_cv,
        "acc_cv": acc_cv,
        "gated": gated,
    }


def sweep_pwin(rhos, trials: int, seed: int, **kw) -> dict:
    """pwin across a sweep of latency ratios ``rhos``."""
    out = {"rho": list(map(float, rhos)), "pwin": [],
           "settle_cv": kw.get("settle_cv", 0.3),
           "gated": kw.get("gated", False)}
    for i, rho in enumerate(rhos):
        r = simulate_pwin(float(rho), trials, seed + i, **kw)
        out["pwin"].append(r["pwin"])
    return out
