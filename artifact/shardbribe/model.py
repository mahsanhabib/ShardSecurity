"""Closed-form analytical model for sub-threshold committee bribery.

This module is the single source of truth for the paper's equations. Every
quantity here has a Monte-Carlo counterpart elsewhere in the package
(``quorum`` validates ``psucc``; ``race`` validates ``pwin``), and the drivers
check that the closed form and the simulation agree.

Notation (matches the paper):
    N = 3F + 1   committee size
    Q = 2F + 1   commit quorum
    k            number of purchased equivocators (k >= F+1 is necessary)
    s            slashable stake per validator (normalized to 1 by default)
    R            continuation / reputation / future-reward value per validator
    q            Pr[equivocation evidence enforced before the validator's stake
                 becomes unslashable]
    V            extractable cross-shard / bridge value
    Cop          operational cost (gas, infra, stake acquisition)
    psucc        Pr[conflicting finality | k equivocators and a view split]
    pwin         Pr[Tsettle < Tacc]
"""
from __future__ import annotations

from dataclasses import dataclass
from math import comb


# --------------------------------------------------------------------------
# Committee / quorum structure
# --------------------------------------------------------------------------
def F_of_N(N: int) -> int:
    """Tolerated faults F for a committee of size N (F = floor((N-1)/3))."""
    if N < 1:
        raise ValueError("N must be >= 1")
    return (N - 1) // 3


def quorum_of_N(N: int) -> int:
    """Commit quorum Q = N - F (= 2F+1 when N = 3F+1)."""
    return N - F_of_N(N)


def equivocation_floor(N: int) -> int:
    """Equivocation floor k_min = F+1 (Lemma: quorum-intersection minimum).

    Two commit quorums of size Q=2F+1 drawn from N=3F+1 validators intersect in
    at least 2Q - N = F+1 signers; each such signer must have signed both
    branches.  Hence at least F+1 validators must equivocate.  This is the
    *necessary* condition; sufficiency additionally requires an honest split
    (captured by ``psucc``).
    """
    return F_of_N(N) + 1


# --------------------------------------------------------------------------
# psucc : probability that k equivocators yield conflicting finality
# --------------------------------------------------------------------------
def psucc_closed_form(N: int, k: int, phi: float) -> float:
    """Probability that k equivocators produce two conflicting certificates.

    Model.  k validators equivocate (sign both branches A and B).  The
    remaining ``H = N - k`` honest validators each vote for exactly one branch;
    a validator votes for A independently with probability ``phi`` (the
    *view-split* parameter set by leader equivocation / network delay /
    transient asynchrony).  Let ``h_A ~ Binomial(H, phi)`` be the honest votes
    on A.  Branch A finalizes iff ``k + h_A >= Q`` and branch B finalizes iff
    ``k + (H - h_A) >= Q`` with ``Q = 2F+1``.  Conflicting finality requires
    *both*.  Rearranging the branch-B constraint, ``h_A <= H - (Q - k) = N - Q
    = F`` (independent of k), so the feasible band is

        Q - k  <=  h_A  <=  N - Q  (= F).

    The width of this band is ``k - F`` (= 1 when k = F+1, the tight single
    point h_A = F), so each equivocator bought beyond the floor widens the
    success window by exactly one feasible split.  psucc is maximized at
    ``phi = 1/2`` (a balanced split).  This matches the ``bft_harness`` quorum
    rule (both certificates must reach Q); ``run_all`` cross-checks the two at
    k >= F+1, not only at the floor.

    Returns 0 when k < F+1 (the floor is not met) or when the band is empty.
    """
    F = F_of_N(N)
    Q = 2 * F + 1
    H = N - k
    if k < F + 1 or H < 0:
        return 0.0
    lo = max(Q - k, 0)       # h_A >= Q - k  so that branch A reaches quorum
    hi = H - max(Q - k, 0)   # h_A <= H - (Q-k) = N - Q  so that branch B does
    # The "hi = N - Q (independent of k)" derivation holds for F+1 <= k <= Q.
    # For k > Q the equivocators alone already meet quorum on each branch, so
    # the band degenerates to [0, H] and psucc = 1 (whole-committee / super-
    # quorum equivocation); the expression below handles that case correctly.
    if lo > hi:
        return 0.0
    # P(lo <= Binomial(H, phi) <= hi)
    total = 0.0
    for h in range(lo, hi + 1):
        total += comb(H, h) * (phi ** h) * ((1.0 - phi) ** (H - h))
    return total


# --------------------------------------------------------------------------
# Bribe cost
# --------------------------------------------------------------------------
def bribe_total(N: int, q: float, s: float = 1.0, R: float = 0.0,
                k: int | None = None) -> float:
    """Total minimum bribe B = k * q * (s + R), k = F+1 by default.

    Each rational validator's individual participation constraint is
    ``b_i >= q (s_i + R_i)``; summing over the k = F+1 required equivocators in
    the homogeneous case gives B = (F+1) q (s+R).  The adversary pays for F+1
    validators (not the whole committee) and pays a *fraction* q of each one's
    stake-at-risk, not its face value.
    """
    if k is None:
        k = equivocation_floor(N)
    return k * q * (s + R)


def breakeven_value(N: int, q: float, s: float = 1.0, R: float = 0.0,
                    Cop: float = 0.0, k: int | None = None) -> float:
    """Break-even extractable value V* = B + Cop (gate G2 holds iff V > V*)."""
    return bribe_total(N, q, s=s, R=R, k=k) + Cop


# --------------------------------------------------------------------------
# Expected profit and the two viability gates
# --------------------------------------------------------------------------
def expected_profit(V: float, psucc: float, pwin: float,
                    B: float, Cop: float = 0.0) -> float:
    """Guided-bribe expected profit  E[Pi] = psucc * pwin * V - B - Cop."""
    return psucc * pwin * V - B - Cop


def expected_profit_effective(V: float, psucc: float, pwin: float,
                              B_succ: float, B_fail: float = 0.0,
                              Cop: float = 0.0) -> float:
    """Effective- (success-conditional-) bribe expected profit.

    E[Pi] = psucc (pwin V - B_succ) - (1 - psucc) B_fail - Cop.
    """
    return psucc * (pwin * V - B_succ) - (1.0 - psucc) * B_fail - Cop


def gate_window(Tsettle: float, Tacc: float) -> bool:
    """Gate G1 (window): there is a settlement window iff Tsettle < Tacc."""
    return Tsettle < Tacc


def gate_economics(V: float, N: int, q: float, s: float = 1.0,
                   R: float = 0.0, Cop: float = 0.0) -> bool:
    """Gate G2 (economics): profitable iff V > B + Cop."""
    return V > breakeven_value(N, q, s=s, R=R, Cop=Cop)


@dataclass
class Scenario:
    """A fully specified attack scenario; ``profit`` evaluates E[Pi]."""
    N: int
    q: float
    V: float
    s: float = 1.0
    R: float = 0.0
    Cop: float = 0.0
    phi: float = 0.5
    pwin: float = 1.0
    k: int | None = None

    @property
    def k_eff(self) -> int:
        return self.k if self.k is not None else equivocation_floor(self.N)

    @property
    def psucc(self) -> float:
        return psucc_closed_form(self.N, self.k_eff, self.phi)

    @property
    def B(self) -> float:
        return bribe_total(self.N, self.q, s=self.s, R=self.R, k=self.k_eff)

    def profit(self) -> float:
        return expected_profit(self.V, self.psucc, self.pwin, self.B, self.Cop)

    def gates(self) -> dict:
        return {
            "G2_economics": self.V > self.B + self.Cop,
            "breakeven_V": self.B + self.Cop,
            "psucc": self.psucc,
            "B": self.B,
            "profit": self.profit(),
        }
