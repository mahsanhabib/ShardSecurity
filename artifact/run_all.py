#!/usr/bin/env python3
"""Run every simulation/analysis and write results to results/main.json.

Usage:
    python run_all.py --config configs/main.yaml
    python run_all.py --config configs/main.yaml --quick   # fewer MC trials

The script is deterministic given the seeds in the config.  It also performs
two *self-validation* checks and fails loudly if either breaks:

  1. The Monte-Carlo quorum harness must reproduce the closed-form psucc to
     within Monte-Carlo error (validates bft_harness + model).
  2. Every equivocation-evidence object produced by the harness must verify
     (validates the PoC fraud-proof / escrow path).

No network is contacted.  All outputs land under results/.
"""
from __future__ import annotations

import argparse
import json
import os
import time

import numpy as np
import yaml

from shardbribe import model, quorum, race, reconfig, realsystems
from shardbribe import estimate
from shardbribe import testbed as tb
from shardbribe.bft_harness import CommitteeHarness
from shardbribe.escrow import PayToEquivocate


HERE = os.path.dirname(os.path.abspath(__file__))


def load_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        if path.endswith((".yaml", ".yml")):
            return yaml.safe_load(fh)
        return json.load(fh)


# --------------------------------------------------------------------------
# RQ0: validate the harness against the closed form, and exercise the PoC.
# --------------------------------------------------------------------------
def validate_and_poc(cfg: dict) -> dict:
    trials = cfg["validation"]["trials"]
    seed = cfg["seed"]
    checks = []
    max_err = 0.0
    for N in cfg["validation"]["N_values"]:
        F = model.F_of_N(N)
        # Cross-check at the floor AND above it (k = F+1, F+2, F+3, capped at
        # the quorum Q): the closed-form band is [Q-k, N-Q], so the agreement
        # must hold for k > F+1, not only at the floor where it is trivial.
        ks = [k for k in (F + 1, F + 2, F + 3) if k <= 2 * F + 1]
        for k in ks:
            for phi in cfg["validation"]["phi_values"]:
                mc = quorum.simulate_psucc(N, k, phi, trials, seed)
                cf = model.psucc_closed_form(N, k, phi)
                err = abs(mc["psucc_mc"] - cf)
                max_err = max(max_err, err)
                assert mc["evidence_all_valid"], "harness produced invalid evidence"
                checks.append({"N": N, "k": k, "phi": phi,
                               "psucc_mc": mc["psucc_mc"], "psucc_cf": cf,
                               "abs_err": err})
    tol = cfg["validation"]["tolerance"]
    assert max_err <= tol, f"psucc MC vs closed-form error {max_err} > {tol}"

    # Floor check: k < F+1 must give exactly zero success, every seed.
    floor_ok = True
    for N in cfg["validation"]["N_values"]:
        kbad = model.equivocation_floor(N) - 1
        if kbad >= 0:
            mc = quorum.simulate_psucc(N, kbad, 0.5, max(trials // 4, 200), seed)
            floor_ok = floor_ok and (mc["psucc_mc"] == 0.0)
    assert floor_ok, "sub-floor k produced a conflicting certificate (impossible)"

    # End-to-end PoC: build a committee, equivocate with F+1, drive a split,
    # produce evidence, and have the escrow pay only on valid proofs.
    rng = np.random.default_rng(seed + 1)
    Npoc = cfg["poc"]["N"]
    h = CommitteeHarness(Npoc, rng)
    k = model.equivocation_floor(Npoc)
    # The adversary engineers a usable view split (leader equivocation), so the
    # F+1 floor is *sufficient* here: both branches reach quorum.
    cert_a, cert_b, evidence = h.run_round(list(range(k)), phi=0.5, rng=rng,
                                           engineered_split=True)
    escrow = PayToEquivocate.fund(h, k, bribe_per=cfg["poc"]["bribe_per"])
    for v in range(k):
        escrow.register(v)
    paid = sum(1 for ev in evidence if escrow.claim(ev))
    # a forged proof (swap a signature) must be rejected
    forged = evidence[0]
    bad = type(forged)(forged.validator, forged.epoch, forged.height,
                       forged.rnd, forged.vote_a, forged.vote_a)  # not a conflict
    forged_rejected = not escrow.harness.verify_evidence(bad)

    return {
        "psucc_validation": checks,
        "max_abs_err": max_err,
        "tolerance": tol,
        "floor_check_passed": floor_ok,
        "poc": {
            "N": Npoc, "k": k,
            "conflicting_finality": CommitteeHarness.conflicting_finality(
                cert_a, cert_b, h.Q),
            "cert_a_size": cert_a.size, "cert_b_size": cert_b.size,
            "evidence_produced": len(evidence),
            "bribes_paid": paid,
            "escrow_remaining": escrow.escrow,
            "forged_proof_rejected": forged_rejected,
        },
    }


# --------------------------------------------------------------------------
# Floor experiment: psucc vs view-split phi for k = F+1, F+2, F+3, with a
# Monte-Carlo overlay that validates the closed form.  Demonstrates that the
# F+1 floor is necessary-but-not-sufficient and that each extra purchased
# equivocator widens the success band.
# --------------------------------------------------------------------------
def floor_experiment(cfg: dict) -> dict:
    c = cfg["floor"]
    N = c["N"]
    F = model.F_of_N(N)
    phis = np.linspace(0.02, 0.98, c["points"])
    mc_phis = c["mc_phis"]
    curves = {}
    mc_curves = {}
    for extra in c["extra_equivocators"]:
        k = (F + 1) + extra
        label = f"k=F+{1+extra}"
        curves[label] = [model.psucc_closed_form(N, k, float(ph))
                         for ph in phis]
        # Monte-Carlo overlay for THIS k (not only the floor), so the
        # closed-form/simulator agreement is shown on every plotted curve --
        # the feasible-split band is [Q-k, N-Q], which the harness enforces by
        # requiring both certificates to reach Q.
        mc_curves[label] = [
            quorum.simulate_psucc(N, k, float(ph), c["mc_trials"],
                                  cfg["seed"] + extra * 100 + i)["psucc_mc"]
            for i, ph in enumerate(mc_phis)]
    return {"N": N, "F": F, "phi": [float(x) for x in phis],
            "curves": curves, "mc_phis": mc_phis, "mc_curves": mc_curves}


# --------------------------------------------------------------------------
# RQ1: window-open probability pwin vs latency ratio rho.
# --------------------------------------------------------------------------
def rq1_pwin(cfg: dict) -> dict:
    c = cfg["rq1"]
    rhos = np.linspace(c["rho_min"], c["rho_max"], c["points"])
    curves = {}
    for cv in c["settle_cv_values"]:
        curves[f"cv={cv}"] = race.sweep_pwin(
            rhos, c["trials"], cfg["seed"], settle_cv=cv, acc_cv=cv)["pwin"]
    gated = race.sweep_pwin(rhos, c["trials"], cfg["seed"],
                            settle_cv=c["settle_cv_values"][0], gated=True)["pwin"]
    return {"rho": [float(x) for x in rhos], "curves": curves, "gated": gated}


# --------------------------------------------------------------------------
# RQ2: bribe cost B vs committee size N for several q.
# --------------------------------------------------------------------------
def rq2_cost(cfg: dict) -> dict:
    c = cfg["rq2"]
    Ns = c["N_values"]
    out = {"N": Ns, "k": [model.equivocation_floor(N) for N in Ns],
           "R": c["R"], "s": c["s"], "curves": {}}
    for q in c["q_values"]:
        out["curves"][f"q={q}"] = [
            model.bribe_total(N, q, s=c["s"], R=c["R"]) for N in Ns]
    return out


# --------------------------------------------------------------------------
# RQ3: profitability regions.
# --------------------------------------------------------------------------
def rq3_profit(cfg: dict) -> dict:
    c = cfg["rq3"]
    seed = cfg["seed"]
    # pwin(rho) curve reused for the phase diagram
    rhos = np.linspace(c["rho_min"], c["rho_max"], c["rho_points"])
    pwin_rho = np.array(race.sweep_pwin(rhos, c["trials"], seed,
                                        settle_cv=c["settle_cv"])["pwin"])
    Vs = np.linspace(c["V_min"], c["V_max"], c["V_points"])
    N = c["N"]
    q = c["q"]
    s, R, Cop = c["s"], c["R"], c["Cop"]
    # psucc = adversary's split-control reliability (parameter); the random-
    # split binomial floor is reported separately in the psucc figure.
    psucc = c["psucc"]
    psucc_floor = model.psucc_closed_form(N, model.equivocation_floor(N), c["phi"])
    B = model.bribe_total(N, q, s=s, R=R)
    # E[Pi] over (rho, V)
    Z = np.empty((len(Vs), len(rhos)))
    for i, V in enumerate(Vs):
        for j, pw in enumerate(pwin_rho):
            Z[i, j] = model.expected_profit(V, psucc, pw, B, Cop)
    # heatmap over (q, V) at fixed rho (window open)
    qs = np.linspace(c["q_min"], c["q_max"], c["q_points"])
    pw_fixed = float(pwin_rho[np.argmin(np.abs(rhos - c["rho_fixed"]))])
    ZqV = np.empty((len(Vs), len(qs)))
    for i, V in enumerate(Vs):
        for j, qq in enumerate(qs):
            Bq = model.bribe_total(N, qq, s=s, R=R)
            ZqV[i, j] = model.expected_profit(V, psucc, pw_fixed, Bq, Cop)
    # psucc sensitivity: break-even V (profit=0) at the window-open slice, as a
    # function of the adversary's split-control reliability psucc.
    psucc_vals = [0.2, 0.4, 0.6, 0.8, 1.0]
    breakeven_V_vs_psucc = [
        (B + Cop) / (ps * pw_fixed) if ps * pw_fixed > 0 else float("inf")
        for ps in psucc_vals]
    return {
        "rho": [float(x) for x in rhos], "V": [float(x) for x in Vs],
        "psucc": psucc, "psucc_floor": psucc_floor, "B": B, "N": N, "q": q,
        "Cop": Cop, "profit_rho_V": Z.tolist(),
        "q_grid": [float(x) for x in qs],
        "profit_q_V": ZqV.tolist(),
        "pwin_fixed": pw_fixed, "rho_fixed": c["rho_fixed"],
        "psucc_sensitivity": {"psucc": psucc_vals,
                              "breakeven_V": breakeven_V_vs_psucc},
    }


# --------------------------------------------------------------------------
# RQ4: reconfiguration -- E[Pi(a)] across the epoch for each design.
# --------------------------------------------------------------------------
def rq4_reconfig(cfg: dict) -> dict:
    c = cfg["rq4"]
    p = reconfig.ReconfigParams(
        N=c["N"], V=c["V"], s=c["s"], R=c["R"], Cop=c["Cop"],
        q_base=c["q_base"], phi=c["phi"], psucc=c.get("psucc"),
        tau=c["tau"], U=c["U"],
        settle_mean=c["settle_mean"], acc_mean=c["acc_mean"],
        Treceipt=c["Treceipt"], Tstate=c["Tstate"], Hmax=c["Hmax"],
        settle_cv=c["settle_cv"], acc_cv=c["acc_cv"],
        trials=c["trials"], seed=cfg["seed"])
    a_grid = np.linspace(0.0, p.tau, c["a_points"])
    data = reconfig.all_designs(p, a_grid)
    return {"params": c, "designs": data}


# --------------------------------------------------------------------------
# RQ5: which defenses close the attack? (effect of each lever on E[Pi])
# --------------------------------------------------------------------------
def rq5_defenses(cfg: dict) -> dict:
    c = cfg["rq5"]
    seed = cfg["seed"]
    N, q, V = c["N"], c["q"], c["V"]
    s, R, Cop = c["s"], c["R"], c["Cop"]
    phi = c["phi"]
    psucc = c["psucc"]

    def pwin_at(rho, cv=0.3, gated=False):
        return race.simulate_pwin(rho, c["trials"], seed,
                                  settle_cv=cv, acc_cv=cv, gated=gated)["pwin"]

    rho0 = c["rho_baseline"]
    base_pwin = pwin_at(rho0)
    base_B = model.bribe_total(N, q, s=s, R=R)
    base_profit = model.expected_profit(V, psucc, base_pwin, base_B, Cop)

    rows = []
    rows.append({"defense": "baseline", "pwin": base_pwin, "q": q, "B": base_B,
                 "N": N, "profit": base_profit,
                 "affects": "--"})
    # A: finality-gated receipts -> pwin = 0
    rows.append({"defense": "Finality-gated receipts", "pwin": 0.0, "q": q,
                 "B": base_B, "N": N,
                 "profit": model.expected_profit(V, psucc, 0.0, base_B, Cop),
                 "affects": "pwin"})
    # B: persistent slashability across rotation -> keeps q high (here q->1)
    qhi = min(1.0, q * c["persistent_q_mult"])
    Bhi = model.bribe_total(N, qhi, s=s, R=R)
    rows.append({"defense": "Persistent slashability", "pwin": base_pwin,
                 "q": qhi, "B": Bhi, "N": N,
                 "profit": model.expected_profit(V, psucc, base_pwin, Bhi, Cop),
                 "affects": "q, B"})
    # C/D: fast evidence -> lower Tacc -> lower rho -> lower pwin AND higher q
    rho_fast = rho0 * c["fast_evidence_rho_mult"]
    pw_fast = pwin_at(rho_fast)
    rows.append({"defense": "Fast evidence (lower Tacc)", "pwin": pw_fast,
                 "q": qhi, "B": Bhi, "N": N,
                 "profit": model.expected_profit(V, psucc, pw_fast, Bhi, Cop),
                 "affects": "pwin, q, B"})
    # F: value-aware committee sizing -> larger N -> larger B (linear in F+1)
    Nbig = c["large_N"]
    Bbig = model.bribe_total(Nbig, q, s=s, R=R)
    rows.append({"defense": "Larger committee", "pwin": base_pwin, "q": q,
                 "B": Bbig, "N": Nbig,
                 "profit": model.expected_profit(V, psucc, base_pwin,
                                                 Bbig, Cop),
                 "affects": "B (linear in F+1)"})
    return {"V": V, "psucc": psucc, "rows": rows}


# --------------------------------------------------------------------------
# RQ6: discrete-event testbed -- MEASURED pwin vs the closed form.
# --------------------------------------------------------------------------
def rq6_testbed(cfg: dict) -> dict:
    c = cfg["rq6"]
    seed = cfg["seed"]
    base = tb.TestbedParams(
        N=c["N"], link_mean_ms=c["link_mean_ms"], link_cv=c["link_cv"],
        enforce_delay_ms=c["enforce_delay_ms"],
        dest_interval_ms=c["dest_interval_ms"], clawback_ms=c["clawback_ms"])
    sig = tb.signature_costs(c["N"], seed)
    baseline = tb.measure_pwin(base, c["runs"], seed)
    scales = np.logspace(np.log10(c["settle_scale_min"]),
                         np.log10(c["settle_scale_max"]), c["points"])
    sweep = tb.sweep_measured_pwin(base, scales, c["runs"], seed + 7)
    # analytical pwin at each measured rho, for overlay
    analytic = [race.simulate_pwin(float(r), c["analytic_trials"], seed + 3)["pwin"]
                for r in sweep["rho_measured"]]
    return {
        "signature": sig,
        "baseline": baseline,
        "rho_measured": sweep["rho_measured"],
        "pwin_measured": sweep["pwin_measured"],
        "pwin_analytic": analytic,
    }


# --------------------------------------------------------------------------
# RQ7: real-systems case study (documented parameters -> exposure).
# --------------------------------------------------------------------------
def rq7_realsystems(cfg: dict) -> dict:
    return {"rows": realsystems.analyze(R_frac=cfg["rq7"]["R_frac"])}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=os.path.join("configs", "main.yaml"))
    ap.add_argument("--out", default=os.path.join("results", "main.json"))
    ap.add_argument("--quick", action="store_true",
                    help="scale down MC trials ~10x for a fast smoke run")
    args = ap.parse_args()

    cfg = load_config(args.config)
    if args.quick:
        # Scale down the heavy RQ sweeps for a fast smoke run, but NOT the
        # validation gate: its tolerance (0.02) is calibrated for the full
        # trial count, so fewer trials would let Monte-Carlo noise spuriously
        # trip the correctness assert.
        for key in ("rq1", "rq3", "rq4", "rq5"):
            if "trials" in cfg.get(key, {}):
                cfg[key]["trials"] = max(cfg[key]["trials"] // 10, 500)

    t0 = time.time()
    print("[run_all] validating harness + PoC ...")
    results = {"config": cfg, "validation": validate_and_poc(cfg)}
    print("           max |psucc_mc - psucc_cf| = "
          f"{results['validation']['max_abs_err']:.4f}  (tol "
          f"{results['validation']['tolerance']})")
    print("[run_all] floor psucc(phi) ..."); results["floor"] = floor_experiment(cfg)
    print("[run_all] RQ1 pwin(rho) ...");   results["rq1"] = rq1_pwin(cfg)
    print("[run_all] RQ2 bribe(N) ...");    results["rq2"] = rq2_cost(cfg)
    print("[run_all] RQ3 profit regions ..."); results["rq3"] = rq3_profit(cfg)
    print("[run_all] RQ4 reconfiguration ..."); results["rq4"] = rq4_reconfig(cfg)
    print("[run_all] RQ5 defenses ...");    results["rq5"] = rq5_defenses(cfg)
    print("[run_all] RQ6 testbed (measured) ..."); results["rq6"] = rq6_testbed(cfg)
    print("           testbed baseline: rho="
          f"{results['rq6']['baseline']['rho_measured']:.2f}, pwin="
          f"{results['rq6']['baseline']['pwin_measured']:.2f}")
    print("[run_all] RQ7 real systems ..."); results["rq7"] = rq7_realsystems(cfg)
    # RQ8: measured q / T_acc / T_settle from committed results/measured/*.jsonl.
    # Network-free and graceful: no-ops (does not alter any other result) until a
    # real measurement has been collected per PREREGISTRATION-rq8.md.
    print("[run_all] RQ8 measured (pre-registered) ...")
    results["rq8"] = estimate.run(cfg)
    print(f"           {results['rq8'].get('status')}")
    results["runtime_sec"] = time.time() - t0

    os.makedirs(os.path.dirname(os.path.join(HERE, args.out)), exist_ok=True)
    outpath = os.path.join(HERE, args.out)
    with open(outpath, "w", encoding="utf-8") as fh:
        json.dump(results, fh, indent=2)
    print(f"[run_all] wrote {outpath}  ({results['runtime_sec']:.1f}s)")


if __name__ == "__main__":
    main()
