"""Reconfiguration-phase accountability races (epoch-boundary handoff).

This module extends the single-epoch model to committee rotation.  It encodes
the variables of the paper's reconfiguration section and evaluates expected
adversary profit E[Pi(a)] as a function of the attack time ``a`` within an
epoch of length ``tau`` (with remaining time ``r = tau - a``), for each of the
reconfiguration designs A--F.

Variables (paper notation):
    tau          epoch length
    a            attack time inside the epoch, 0 <= a <= tau
    r = tau - a  remaining time before nominal reconfiguration
    U            unbonding / withdrawal delay after validator exit
    Hreconf(a)   extra accountability delay from committee handoff / state
                 transfer / beacon processing / proof routing across epochs
    Tstate       time for the new committee to obtain & verify shard state
    Treceipt     time for old-epoch receipts/locks/withdrawal certs to become
                 executable in the next epoch
    Tevidence    time for old-epoch equivocation evidence to become enforceable
                 against globally bonded stake
    q(a)         Pr[evidence enforced before validator stake becomes unslashable]

Profit model:
    E[Pi(a)] = psucc(a) * pwin(a) * V - B(a) - Cop,   B(a) = (F+1) q(a) (s+R)

The key qualitative results this module produces (Figure 6 of the paper):
  * Hard cutoff (A): pwin(a) = Pr[Tsettle < min(Tacc, r)] -> profit collapses
    as a -> tau because r -> 0 (last-block attacks are weak).
  * Unsafe carryover / reconfiguration delay (C, "reconfig delay"): old-epoch
    artifacts survive and Hreconf(a) widens the deadline, so profit *rises*
    toward the boundary (Proposition: reconfiguration-residual vulnerability).
  * Accountability-gated carryover (the safe variant of B/C and design D/E done
    right): pwin(a) = 0 (Proposition: reconfiguration-safe handoff).
  * Rolling reconfiguration (F): no last-block cliff; a smooth optimum in a.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .race import _gamma_sum
from .model import equivocation_floor, F_of_N


# Canonical design identifiers (subset used in Figure 6 + full taxonomy A--F).
DESIGNS = [
    "hard_cutoff",          # A
    "unsafe_carryover",     # C immediate import (also B unsafe drain)
    "gated_carryover",      # accountability-gated (safe B/C, D/E done right)
    "reconfig_delay",       # carryover + large Hreconf(a)
    "rolling",              # F rolling / asynchronous reconfiguration
]


@dataclass
class ReconfigParams:
    N: int = 31
    V: float = 60.0
    s: float = 1.0
    R: float = 0.5
    Cop: float = 1.0
    q_base: float = 0.6          # mid-epoch enforcement probability
    phi: float = 0.5             # view split (psucc maximized at 0.5)
    psucc: float | None = None   # adversary's split-control reliability; if None,
                                 # falls back to the random-split binomial floor
    tau: float = 1.0             # epoch length (normalized)
    U: float = 0.15              # unbonding / withdrawal delay
    settle_mean: float = 0.35    # base cross-shard settlement time
    acc_mean: float = 0.55       # base accountability latency Tacc
    Treceipt: float = 0.10       # cross-epoch receipt-import latency
    Tstate: float = 0.08         # state-handoff time
    Hmax: float = 0.40           # max extra accountability delay at boundary
    settle_cv: float = 0.3
    acc_cv: float = 0.3
    trials: int = 40000
    seed: int = 7

    @property
    def k(self) -> int:
        return equivocation_floor(self.N)


def Hreconf(a: float, p: ReconfigParams) -> float:
    """Extra accountability delay from handoff, increasing toward the boundary.

    Evidence about an old-epoch fault produced near the end of the epoch must
    route across the boundary (new committee / beacon / state handoff), so the
    handoff penalty grows as ``a -> tau``."""
    frac = a / p.tau if p.tau > 0 else 0.0
    return p.Hmax * frac


def q_of_a(a: float, p: ReconfigParams, persistent: bool) -> float:
    """q(a) = Pr[evidence enforced before stake becomes unslashable].

    * ``persistent=True`` (robust PoS: stake stays globally bonded for at least
      the max evidence delay after rotation): q(a) ~ q_base, independent of a.
    * ``persistent=False`` (unsafe: immediate withdrawal after epoch): the stake
      becomes unslashable at ``r + U`` from t=0, while evidence becomes
      enforceable at ~Tevidence; we estimate q(a) as the probability evidence
      lands first.  As ``a -> tau`` (r -> 0) this shrinks toward Pr[Tevidence<U],
      lowering the bribe price near the boundary.
    """
    if persistent:
        return p.q_base
    rng = np.random.default_rng(p.seed + 991)
    r = p.tau - a
    # Tevidence: evidence enforceable latency (accountability path).
    t_ev = _gamma_sum(rng, p.acc_mean, 4, p.acc_cv, p.trials)
    deadline = r + p.U
    frac = np.count_nonzero(t_ev < deadline) / p.trials
    # scale by the mid-epoch q_base ceiling (enforcement is never more reliable
    # than the base mechanism)
    return p.q_base * frac


def _psucc(p: ReconfigParams) -> float:
    """Adversary success probability given the engineered split.

    If ``p.psucc`` is set it is used directly (the adversary's view-control
    reliability, ranging from the random-split floor to ~1 for full leader
    control).  Otherwise we fall back to the random-split binomial floor.
    """
    if p.psucc is not None:
        return p.psucc
    from .model import psucc_closed_form
    return psucc_closed_form(p.N, p.k, p.phi)


def pwin_design(design: str, a: float, p: ReconfigParams) -> float:
    """Window-open probability pwin(a) for a given reconfiguration design."""
    rng = np.random.default_rng(p.seed + DESIGNS.index(design))  # deterministic (not hash())
    r = p.tau - a
    t_settle = _gamma_sum(rng, p.settle_mean, 2, p.settle_cv, p.trials)
    t_acc = _gamma_sum(rng, p.acc_mean, 4, p.acc_cv, p.trials)
    H = Hreconf(a, p)

    if design == "hard_cutoff":
        # value must settle before BOTH accountability and the epoch boundary r
        deadline = np.minimum(t_acc, r)
        return np.count_nonzero(t_settle < deadline) / p.trials

    if design == "unsafe_carryover":
        # old-epoch receipt imported next epoch: settlement is delayed by the
        # cross-epoch import (Treceipt + Tstate) but the deadline is widened by
        # the handoff penalty Hreconf(a); no r cutoff (artifact survives).
        t_settle_ce = t_settle + p.Treceipt + p.Tstate
        deadline = t_acc + H
        return np.count_nonzero(t_settle_ce < deadline) / p.trials

    if design == "gated_carryover":
        # accountability-gated: execution cannot precede the accountability
        # window -> Tsettle >= Tacc by construction -> pwin = 0.
        return 0.0

    if design == "reconfig_delay":
        # carryover where the dominant effect is a large handoff delay that
        # inflates the effective accountability deadline.
        deadline = t_acc + 1.5 * H
        return np.count_nonzero(t_settle < deadline) / p.trials

    if design == "rolling":
        # gradual rotation: no single boundary cliff; deadline is the base
        # accountability latency with a mild handoff term, no min-with-r.
        deadline = t_acc + 0.5 * H
        return np.count_nonzero(t_settle < deadline) / p.trials

    raise ValueError(f"unknown design {design!r}")


def profit_over_epoch(design: str, p: ReconfigParams,
                      a_grid=None) -> dict:
    """E[Pi(a)] across the epoch for one design."""
    if a_grid is None:
        a_grid = np.linspace(0.0, p.tau, 41)
    persistent = design in ("hard_cutoff", "gated_carryover",
                            "reconfig_delay", "rolling")
    psucc = _psucc(p)
    profits, pwins, qs, Bs = [], [], [], []
    for a in a_grid:
        pw = pwin_design(design, float(a), p)
        qa = q_of_a(float(a), p, persistent)
        B = p.k * qa * (p.s + p.R)
        pi = psucc * pw * p.V - B - p.Cop
        profits.append(pi)
        pwins.append(pw)
        qs.append(qa)
        Bs.append(B)
    return {
        "design": design,
        "a": [float(x) for x in a_grid],
        "a_over_tau": [float(x / p.tau) for x in a_grid],
        "profit": profits,
        "pwin": pwins,
        "q": qs,
        "B": Bs,
        "psucc": psucc,
        "persistent_slashability": persistent,
    }


def all_designs(p: ReconfigParams, a_grid=None) -> dict:
    return {d: profit_over_epoch(d, p, a_grid) for d in DESIGNS}
