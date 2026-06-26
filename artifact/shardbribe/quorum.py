"""Monte-Carlo BFT committee/quorum simulator.

Drives the ``bft_harness`` over many seeded rounds and measures the empirical
probability that ``k`` equivocators yield two conflicting certificates.  This
is the simulated counterpart of ``model.psucc_closed_form``; ``run_all``
asserts the two agree to within Monte-Carlo error, which validates both the
harness and the closed form.

It also confirms the equivocation *floor* empirically: with ``k < F+1`` the
empirical success probability is exactly 0 for every seed and every split.
"""
from __future__ import annotations

import numpy as np

from .bft_harness import CommitteeHarness
from .model import F_of_N


def simulate_psucc(N: int, k: int, phi: float, trials: int,
                   seed: int) -> dict:
    """Return empirical psucc and a validity audit over ``trials`` rounds.

    For each trial we build a fresh committee, designate ``k`` equivocators,
    run one commit round with view-split ``phi``, and check whether two
    conflicting certificates of size >= Q both formed.  We also re-verify every
    equivocation-evidence object the harness produced, so the run doubles as a
    test that the fraud proofs are valid.
    """
    rng = np.random.default_rng(seed)
    F = F_of_N(N)
    Q = 2 * F + 1
    successes = 0
    evidence_count = 0
    evidence_valid = 0

    for _ in range(trials):
        harness = CommitteeHarness(N, rng)
        equivocators = list(range(k))            # any k validators
        cert_a, cert_b, evidence = harness.run_round(equivocators, phi, rng)
        if CommitteeHarness.conflicting_finality(cert_a, cert_b, Q):
            successes += 1
        for ev in evidence:
            evidence_count += 1
            if harness.verify_evidence(ev):
                evidence_valid += 1

    return {
        "N": N,
        "k": k,
        "F": F,
        "Q": Q,
        "phi": phi,
        "trials": trials,
        "psucc_mc": successes / trials,
        "evidence_count": evidence_count,
        "evidence_all_valid": evidence_count == evidence_valid,
    }


def sweep_split(N: int, k: int, phis, trials: int, seed: int) -> dict:
    """Empirical psucc across a range of view-split values ``phis``."""
    out = {"N": N, "k": k, "phi": list(phis), "psucc_mc": []}
    for i, phi in enumerate(phis):
        r = simulate_psucc(N, k, float(phi), trials, seed + i)
        out["psucc_mc"].append(r["psucc_mc"])
    return out
