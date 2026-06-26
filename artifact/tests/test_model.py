"""Unit tests for the analytical model and the BFT harness.

Run with:  python -m pytest tests/        (or: python tests/test_model.py)
These tests encode the load-bearing claims of the paper so that a regression
in the model is caught immediately.
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shardbribe import model, quorum, race          # noqa: E402
from shardbribe.bft_harness import CommitteeHarness  # noqa: E402
from shardbribe.escrow import PayToEquivocate        # noqa: E402


def test_quorum_floor_values():
    # N = 3F+1 -> F = floor((N-1)/3); floor k = F+1
    assert model.F_of_N(4) == 1 and model.equivocation_floor(4) == 2
    assert model.F_of_N(7) == 2 and model.equivocation_floor(7) == 3
    assert model.F_of_N(31) == 10 and model.equivocation_floor(31) == 11
    assert model.quorum_of_N(31) == 21          # 2F+1


def test_psucc_floor_is_necessary_not_sufficient():
    # With k < F+1 conflicting finality is impossible.
    for N in (4, 7, 16, 31):
        k = model.equivocation_floor(N) - 1
        assert model.psucc_closed_form(N, k, 0.5) == 0.0
    # With k = F+1, success is possible but < 1 even at the optimal split.
    assert 0.0 < model.psucc_closed_form(31, 11, 0.5) < 1.0


def test_psucc_widens_with_extra_equivocators():
    N = 31
    F = model.F_of_N(N)
    p1 = model.psucc_closed_form(N, F + 1, 0.5)
    p2 = model.psucc_closed_form(N, F + 2, 0.5)
    p3 = model.psucc_closed_form(N, F + 3, 0.5)
    assert p1 < p2 < p3


def test_psucc_maximized_at_balanced_split():
    N = 31; k = model.equivocation_floor(N)
    center = model.psucc_closed_form(N, k, 0.5)
    assert center >= model.psucc_closed_form(N, k, 0.3)
    assert center >= model.psucc_closed_form(N, k, 0.7)


def test_mc_matches_closed_form():
    # The Monte-Carlo harness reproduces the closed form (validates both) --
    # at the floor AND above it.  The feasible-split band is [Q-k, N-Q]
    # (width k-F); a stale upper bound of k-1 would overstate psucc for k>F+1
    # and diverge from the harness here, so this guards against that regression.
    for N in (7, 16, 31):
        F = model.F_of_N(N)
        for k in (k for k in (F + 1, F + 2, F + 3) if k <= 2 * F + 1):
            for phi in (0.3, 0.5, 0.7):
                cf = model.psucc_closed_form(N, k, phi)
                mc = quorum.simulate_psucc(N, k, phi, 20000, seed=1)["psucc_mc"]
                assert abs(cf - mc) < 0.02, (N, k, phi, cf, mc)


def test_psucc_band_upper_bound_is_N_minus_Q():
    # Direct check of the corrected feasibility band: at k=F+2, h_A=F+1 must
    # NOT count (branch B falls one short of quorum), so psucc equals the
    # Binomial mass on [Q-k, N-Q] only -- not on [Q-k, k-1].
    from math import comb
    N, phi = 31, 0.5
    F = model.F_of_N(N); Q = 2 * F + 1
    for k in (F + 1, F + 2, F + 3):
        H = N - k
        lo, hi = max(Q - k, 0), H - max(Q - k, 0)   # [Q-k, N-Q]
        want = sum(comb(H, h) * phi**h * (1 - phi)**(H - h)
                   for h in range(lo, hi + 1))
        assert abs(model.psucc_closed_form(N, k, phi) - want) < 1e-12
        assert hi == N - Q                          # upper bound is N-Q, not k-1


def test_bribe_cost_linear_in_floor():
    # B = (F+1) q (s+R): doubling F+1 doubles B at fixed q, s, R.
    b1 = model.bribe_total(31, 0.5, s=1.0, R=0.5)        # k=11
    b2 = model.bribe_total(64, 0.5, s=1.0, R=0.5)        # k=22
    assert abs(b2 / b1 - 22 / 11) < 1e-9


def test_immunity_gives_zero_pwin():
    r = race.simulate_pwin(3.0, 50000, seed=2, gated=True)
    assert r["pwin"] == 0.0
    # ungated at rho>1 has substantial pwin
    r2 = race.simulate_pwin(3.0, 50000, seed=2, gated=False)
    assert r2["pwin"] > 0.5


def test_pwin_threshold_near_one():
    lo = race.simulate_pwin(0.4, 50000, seed=3)["pwin"]
    hi = race.simulate_pwin(3.0, 50000, seed=3)["pwin"]
    mid = race.simulate_pwin(1.0, 50000, seed=3)["pwin"]
    assert lo < 0.2 < mid < 0.85 < hi


def test_immunity_proposition_profit_negative():
    # pwin = 0 -> profit = -B - Cop < 0 for any V.
    pi = model.expected_profit(V=1e6, psucc=0.9, pwin=0.0, B=8.25, Cop=1.0)
    assert pi < 0


def test_poc_end_to_end_attack_and_escrow():
    rng = np.random.default_rng(7)
    N = 31
    h = CommitteeHarness(N, rng)
    k = model.equivocation_floor(N)
    ca, cb, ev = h.run_round(list(range(k)), phi=0.5, rng=rng,
                             engineered_split=True)
    # both branches reach quorum -> conflicting finality
    assert CommitteeHarness.conflicting_finality(ca, cb, h.Q)
    assert len(ev) == k and all(h.verify_evidence(e) for e in ev)
    # escrow pays exactly k valid proofs and drains
    esc = PayToEquivocate.fund(h, k, bribe_per=0.6)
    for v in range(k):
        esc.register(v)
    paid = sum(1 for e in ev if esc.claim(e))
    assert paid == k
    # double claim is rejected
    assert not esc.claim(ev[0])


def test_testbed_reproduces_threshold():
    from shardbribe import testbed as tb
    base = tb.TestbedParams(N=16)
    # fast settlement -> window open; slow settlement -> window closed
    fast = tb.TestbedParams(**{**base.__dict__, "settle_scale": 0.03})
    slow = tb.TestbedParams(**{**base.__dict__, "settle_scale": 1.0})
    mf = tb.measure_pwin(fast, 200, seed=1)
    ms = tb.measure_pwin(slow, 200, seed=1)
    assert mf["rho_measured"] > 1.0 and mf["pwin_measured"] > 0.7
    assert ms["rho_measured"] < 1.0 and ms["pwin_measured"] < 0.3
    sig = tb.signature_costs(16, 1)
    assert sig["sig_bytes"] == 64 and sig["evidence_valid"]


def test_realsystems_deployed_are_safe():
    from shardbribe import realsystems
    rows = realsystems.analyze()
    for r in rows:
        if "hypothetical" in r["name"]:
            assert "exposed" in r["verdict"]            # the danger case
        else:
            # every deployed system: q high (long unbonding) or gated
            assert r["q_est"] > 0.9 or r["window"] == "gated"
            assert "exposed" not in r["verdict"]


if __name__ == "__main__":
    fns = [v for kname, v in sorted(globals().items())
           if kname.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed")
