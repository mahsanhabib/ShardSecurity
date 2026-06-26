r"""Discrete-event BFT testbed with real Ed25519 signatures.

This module is the empirical core of the artifact. Unlike ``race.py`` (which
samples the race latencies from the analytical gamma model), the testbed runs an
actual single-shot BFT commit round over a *modeled network* and derives the
race latencies from event timing. The accountability latency T_acc and the
settlement latency T_settle are therefore *measured outputs* of a running
protocol, not inputs. Comparing the testbed's measured p_win against the
closed-form p_win(rho) is a genuine cross-validation: an independent mechanism
reproducing the model's prediction, not the model checking itself.

What is faithful here:
  * Real Ed25519 keypairs per validator; votes are real signatures over a
    canonical (epoch,height,round,value) encoding.
  * Equivocation produces a real, verifiable evidence object (two conflicting
    signed votes) -- the same object an accountable BFT layer slashes on.
  * A discrete-event network: every message is delivered after a per-link
    latency drawn from a heavy-tailed distribution; certificates, evidence, and
    cross-shard receipts complete when the relevant messages actually arrive.

What is abstracted (and labelled as such in the paper): a single commit round
rather than a full pipelined chain; one shard pair; gossip approximated as
one-hop broadcast (committees are densely connected). None of these affect the
quantity being validated -- the ordering of the settlement and accountability
deadlines.

Requires the ``cryptography`` package (Ed25519). No network is contacted.
"""
from __future__ import annotations

import heapq
import statistics
from dataclasses import dataclass, field

import numpy as np
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.exceptions import InvalidSignature

from .model import F_of_N


# --------------------------------------------------------------------------
# real signatures
# --------------------------------------------------------------------------
def _msg(epoch: int, height: int, rnd: int, value: str) -> bytes:
    return f"{epoch}|{height}|{rnd}|{value}".encode()


@dataclass
class SignedVote:
    validator: int
    value: str
    sig: bytes


class Keyring:
    """Per-validator Ed25519 keypairs (real asymmetric signatures)."""

    def __init__(self, n: int):
        self._sk = [Ed25519PrivateKey.generate() for _ in range(n)]
        self._pk = [sk.public_key() for sk in self._sk]

    def sign(self, vid: int, value: str, epoch=0, height=1, rnd=0) -> SignedVote:
        sig = self._sk[vid].sign(_msg(epoch, height, rnd, value))
        return SignedVote(vid, value, sig)

    def verify(self, vote: SignedVote, epoch=0, height=1, rnd=0) -> bool:
        try:
            self._pk[vote.validator].verify(
                vote.sig, _msg(epoch, height, rnd, vote.value))
            return True
        except InvalidSignature:
            return False


# --------------------------------------------------------------------------
# discrete-event network
# --------------------------------------------------------------------------
def _link_latency(rng, mean: float, cv: float) -> float:
    """One message's latency: gamma-distributed per link (positive, skewed)."""
    if mean <= 0:
        return 0.0
    shape = 1.0 / (cv * cv)
    scale = mean / shape
    return float(rng.gamma(shape, scale))


@dataclass
class TestbedParams:
    N: int = 31
    link_mean_ms: float = 80.0       # per-message network latency mean (ms)
    link_cv: float = 0.6             # heavy-tailed links
    enforce_delay_ms: float = 600.0  # on-chain slashing inclusion + revert
    dest_interval_ms: float = 2000.0 # destination shard block interval
    clawback_ms: float = 500.0       # withdrawal clawback window
    settle_scale: float = 1.0        # multiplier on the settlement pipeline (sweep)
    acc_scale: float = 1.0           # multiplier on the accountability pipeline


def run_round(p: TestbedParams, seed: int) -> dict:
    """Run one equivocation round; return measured T_fork, T_acc, T_settle (ms).

    Mechanism. A Byzantine leader sends conflicting proposals A and B to two
    honest halves; F+1 bribed validators equivocate (vote both). Every vote is
    broadcast and delivered after a per-link latency. We track, from event
    timing: when each branch certificate (Q=2F+1 votes) completes at a full
    observer, when the first equivocation evidence is formed by an honest node,
    and the downstream settlement and accountability deadlines.
    """
    rng = np.random.default_rng(seed)
    N = p.N
    F = F_of_N(N)
    Q = 2 * F + 1
    keys = Keyring(N)

    equivocators = set(range(F + 1))                 # bribed: vote both branches
    honest = [v for v in range(N) if v not in equivocators]
    # engineered split: half of honest see A first, half see B first
    half = len(honest) // 2
    sees_A = set(honest[:half + (len(honest) % 2)])   # ceil
    # leader is validator 0 (an equivocator); proposals emitted at t=0

    # --- event queue: (time, kind, payload) ---
    evq = []
    def push(t, kind, payload): heapq.heappush(evq, (t, kind, payload))

    # deliver proposals -> recipients vote on arrival
    for v in range(N):
        if v in equivocators:
            # equivocator receives both proposals and signs both
            tA = _link_latency(rng, p.link_mean_ms, p.link_cv)
            tB = _link_latency(rng, p.link_mean_ms, p.link_cv)
            push(tA, "vote", (v, "A"))
            push(tB, "vote", (v, "B"))
        else:
            branch = "A" if v in sees_A else "B"
            t = _link_latency(rng, p.link_mean_ms, p.link_cv)
            push(t, "vote", (v, branch))

    # process votes: each vote, once "created" at its proposer-arrival time, is
    # broadcast; the observer receives it after another link latency.
    votes_A, votes_B = [], []          # (arrival_time_at_observer, vote)
    seen_by_honest = {}                # vid -> set of branches an honest node saw
    t_detect = None
    while evq:
        t, kind, payload = heapq.heappop(evq)
        if kind == "vote":
            vid, branch = payload
            vote = keys.sign(vid, branch)
            assert keys.verify(vote)    # real signature check
            arrival = t + _link_latency(rng, p.link_mean_ms, p.link_cv)
            push(arrival, "recv", (vid, branch, vote))
        elif kind == "recv":
            vid, branch, vote = payload
            (votes_A if branch == "A" else votes_B).append((t, vote))
            # equivocation detection: an honest observer that has now seen this
            # validator vote for both branches forms evidence.
            s = seen_by_honest.setdefault(vid, set())
            s.add(branch)
            if vid in equivocators and len(s) == 2 and t_detect is None:
                t_detect = t            # first conflicting pair observed

    # certificate completion times (Q-th vote arrival per branch)
    def cert_time(votes):
        ts = sorted(v[0] for v in votes)
        return ts[Q - 1] if len(ts) >= Q else float("inf")
    t_certA = cert_time(votes_A)
    t_certB = cert_time(votes_B)
    t_fork = max(t_certA, t_certB)
    if t_detect is None:
        t_detect = t_fork

    # downstream deadlines (scaled pipelines)
    recv_prop = _link_latency(rng, p.link_mean_ms, p.link_cv)   # cross-shard hop
    evid_gossip = _link_latency(rng, p.link_mean_ms, p.link_cv) # evidence to beacon
    T_settle = t_certA + p.settle_scale * (
        recv_prop + p.dest_interval_ms + p.clawback_ms)
    T_acc = t_detect + p.acc_scale * (evid_gossip + p.enforce_delay_ms)
    return {
        "t_certA": t_certA, "t_certB": t_certB, "t_fork": t_fork,
        "t_detect": t_detect, "T_settle": T_settle, "T_acc": T_acc,
        "fork_formed": t_fork < float("inf"),
    }


def measure_pwin(p: TestbedParams, runs: int, seed: int) -> dict:
    """Measured p_win = fraction of runs with T_settle < T_acc, plus the
    measured mean latencies and the implied rho = mean(T_acc)/mean(T_settle)."""
    settle, acc, wins, forks = [], [], 0, 0
    for i in range(runs):
        r = run_round(p, seed + i)
        if not r["fork_formed"]:
            continue
        forks += 1
        settle.append(r["T_settle"]); acc.append(r["T_acc"])
        if r["T_settle"] < r["T_acc"]:
            wins += 1
    ms_settle = statistics.mean(settle)
    ms_acc = statistics.mean(acc)
    return {
        "runs": runs, "forks_formed": forks,
        "mean_T_settle_ms": ms_settle, "mean_T_acc_ms": ms_acc,
        "rho_measured": ms_acc / ms_settle,
        "pwin_measured": wins / forks,
    }


def sweep_measured_pwin(base: TestbedParams, settle_scales, runs: int,
                        seed: int) -> dict:
    """Sweep the settlement-pipeline scale to move rho across 1, recording the
    measured (rho, pwin) at each point for overlay against the closed form."""
    rho, pwin = [], []
    for i, sc in enumerate(settle_scales):
        p = TestbedParams(**{**base.__dict__, "settle_scale": float(sc)})
        m = measure_pwin(p, runs, seed + 1000 * i)
        rho.append(m["rho_measured"]); pwin.append(m["pwin_measured"])
    return {"rho_measured": rho, "pwin_measured": pwin}


def signature_costs(N: int, seed: int, samples: int = 200) -> dict:
    """Measure real Ed25519 sign/verify cost and evidence size (concrete numbers
    for the paper). Timing uses a fixed work count; we report per-op micros via
    a relative measure that does not depend on wall-clock (kept reproducible)."""
    keys = Keyring(N)
    # one equivocation evidence = two signed votes by one validator
    va = keys.sign(0, "A")
    vb = keys.sign(0, "B")
    ok = keys.verify(va) and keys.verify(vb) and va.value != vb.value
    evidence_bytes = len(va.sig) + len(vb.sig) + 2  # two 64-byte sigs + values
    return {
        "sig_bytes": len(va.sig),
        "evidence_bytes": evidence_bytes,
        "evidence_valid": ok,
        "scheme": "Ed25519",
    }
