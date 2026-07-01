# Paper Review — What's Lacking ("Priced to Equivocate")

_Reviewer-grade gap analysis, written 2026-06-29. Target venues: S&P / CCS / USENIX._

Overall: the theory, framing, positioning table, and reproducibility are top-venue quality.
The gaps below are the ones a tough PC would actually fight over — ordered by severity.
The single decisive gap is **Tier 1 #1**: the *composed* attack is never realized end-to-end
on real client code.

---

## Tier 1 — would drive a "major revision / reject" debate

### 1. The composed attack is never realized end-to-end on real client code  ← THE big one
The paper demonstrates the two halves **separately, in different harnesses**:

- **Attack side** ($F{+}1$ distinct equivocators + honest-vote split → *two conflicting
  certificates*) exists only in the discrete-event testbed
  ([implementation.tex](Paper/Section/implementation.tex), [evaluation.tex:154](Paper/Section/evaluation.tex#L154)) — i.e. simulation.
- **Accountability side** (real slashing latency $\Tacc$) is measured on a Cosmos localnet that
  is **two-nodes-one-key self-equivocation** ([measured_evaluation.tex:88-92](Paper/Section/measured_evaluation.tex#L88)).
  That is a *degenerate committee*: $N{=}2$, one key signing twice. It never exercises quorum
  intersection (Lemma 1), never recruits $F{+}1$ **distinct** validators, and never produces
  $\psucc$ (the honest split).
- The experiment that would close this — the **Arm B paired race on real client code** (Prop. 1
  live, one knob flipped) — is **still pending**. The paper still reads as `shadow rehearsal` /
  `[pending]` (data-gated macros at [measured_evaluation.tex:7-25](Paper/Section/measured_evaluation.tex#L7) not flipped).

**Reviewer one-liner:** _"They show bridges settle fast (known) and Cosmos slashes (known), but
never the composed attack producing value on real client code."_

### 2. $\psucc$ (the honest split) is load-bearing but never grounded in a real leader-driven protocol
- Closed form models honest votes as iid $\mathrm{Binomial}(H,\varphi)$
  ([methodology.tex:88](Paper/Section/methodology.tex#L88)) — real BFT honest validators follow one
  leader's proposal, not independent coin flips.
- Headline profitability ($\psucc{=}0.85$) lives entirely in the **"view-control regime,"** granted
  "with bounded probability" ([threat_model.tex:8](Paper/Section/threat_model.tex#L8)) but the bound
  is **never quantified** for any concrete protocol (Tendermint/HotStuff w/ random leader rotation).
- The Monte-Carlo "validation" checks the closed form against the *same* binomial assumption — not
  against a real protocol's leader schedule. Internally consistent, externally ungrounded.

### 3. The prescribed defense has no deployment-cost analysis
Finality-gating cross-shard receipts (Prop. 1) taxes **every** cross-shard tx with $\Tacc$ latency,
not just attacked ones. Paper says "at the cost of added cross-shard latency"
([discussion.tex:16](Paper/Section/discussion.tex#L16)) but never quantifies the throughput/UX hit on
a real system. "Here's the fix that makes you immune" needs "and here's what deploying it costs."

---

## Tier 2 — reviewers will push hard here

### 4. Novelty delta vs. closest works isn't airtight
- **Camael ([liu2025camael], concurrent)** "formalizes exactly our structural premise"
  ([related_work.tex:29](Paper/Section/related_work.tex#L29)). Concurrent + same premise ⇒ brutal
  delta scrutiny. "Corruption-budget vs. economic-procurement event" is thin; the *pricing-by-$\Tacc$*
  and the *race* must carry all the novelty. Engage whether finality-gating subsumes/differs from
  Camael's snapshot-and-conviction pipeline.
- **STAKESURE / CoBRA** already gate value release on a reversion window. Immunity result ≈
  STAKESURE-for-shards. Prop. 1 is **near-definitional** (define window closed ⇒ window closed) —
  the real content is the coupling + measured placement; don't let Prop. 1 be mistaken for the contribution.

### 5. Bribe-cost model is too clean for an economist reviewer
$B=(F{+}1)q(s{+}R)$ assumes:
- (a) **homogeneous stake** $s_i{=}s$ — real sets are skewed; targeting cheapest/colluding $F{+}1$ changes economics.
- (b) **no recruitment/coordination cost** (acknowledged Limitation 4, not modeled).
- (c) cited **pivotality** result ([newman2023decentralization]) says bribes fall *below* naive
  expected loss — cuts *for* the attacker, against the formula, unreconciled.
- (d) **whistleblowing/Omertà** counter-forces cited, not integrated.
- $\Eval$ is exogenous "reachable liquidity" with no MEV/competition/slippage on the extraction leg.

### 6. The "weak accountability" leg (what opens the window) is least substantiated
Adversarial $\Tacc^{\mathrm{hi}}$ rests on **one accidental** sentinelhub-2 batch enforced ~25 days
late ([measured_evaluation.tex:100-104](Paper/Section/measured_evaluation.tex#L100)). The **active
evidence-suppression experiment** (withhold/delay gossip, eclipse reporter) is "specified but not yet
executed." So the open-window story is supported by an accident, not an adversary. $q_{\max}$ is an
enforcement-*conditional upper bound* dominated by that single batch (drops to ~0.97 per-incident).

---

## Tier 3 — credibility / polish, cheap to weaponize against you

### 7. Deployed-systems table self-certifies as unverified
[evaluation.tex:200](Paper/Section/evaluation.tex#L200): "approximate public figures as of 2026;
confirm ... before camera-ready." Only 6 systems; NEAR/MultiversX firewalled out (no production
slashing), shrinking the analyzable set.

### 8. RQ8 reads as "we didn't finish"
[measured_evaluation.tex](Paper/Section/measured_evaluation.tex) spends nearly as much space caveating
(`[pending]`, "rehearsal not production," "owed," "remains") as reporting. Honesty is a virtue but PC
may read it as incomplete. Statistical power thin throughout (n=1 hand-run, n=40 arm-C, $q_{\max}$ on one batch).

### 9. Submission-process risk (not content, but a paper-killer)
GitHub repo `ShardSecurity` is under the real name and contains the compiled PDFs. **If public, the
submission is deanonymized** (double-blind desk-reject). Resolve before submitting: private repo, or
`git rm` the `Paper/` tree + history rewrite.

---

## Net
Theory/framing/reproducibility are top-venue. What's *lacking* is the empirical payoff the paper keeps
promising: a single real-client-code run where the composed attack ($F{+}1$ real equivocators → two
conflicting certificates → value across a real settlement layer) **wins** the race with the knob open
and **loses** it with the knob closed. That one experiment (pending Arm B) is the difference between
"interesting model with partial measurements" and "demonstrated attack."

---

## Prioritized implementation plan (highest leverage first)

- [ ] **P0 — Real-committee localnet ($N{=}4$, $F{=}1$).** Replace two-nodes-one-key self-equivocation
      with a real $N{=}3F{+}1$ committee that exercises quorum intersection: $F{+}1{=}2$ distinct
      validators equivocate, honest nodes split, two conflicting certificates form on real client code.
      Closes Tier 1 #1 (attack side on real code).
- [ ] **P0 — Run Arm B paired race on real client code** end-to-end (knob-open → OPEN, knob-gated →
      RULED_OUT), fold real `results/measured/*` in so the data-gated macros flip off `shadow`/`[pending]`.
- [ ] **P1 — Ground $\psucc$ against a real leader-driven protocol** (Tier 1 #2): measure the actual
      honest-split distribution in the testbed under a realistic leader schedule; bound view-control feasibility.
- [ ] **P1 — Defense deployment-cost analysis** (Tier 1 #3): quantify added cross-shard latency/throughput
      of finality-gating on a concrete system.
- [ ] **P2 — Active evidence-suppression experiment** (Tier 2 #6): demonstrate an adversary *causing*
      slow accountability, not relying on the sentinelhub-2 accident.
- [ ] **P2 — Tighten novelty delta** vs. Camael / STAKESURE / CoBRA (Tier 2 #4); reconcile pivotality +
      stake heterogeneity in the bribe model (Tier 2 #5).
- [ ] **P3 — Verify RQ7 deployed-system numbers**; de-hedge RQ8 prose once real arms land.
- [ ] **P3 — Resolve double-blind deanonymization risk** before submission (Tier 3 #9).
