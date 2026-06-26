# Assessment — *Priced to Equivocate: Sub-Threshold Committee Bribery and the Accountability Race in Sharded Blockchains*

_Reviewer-style meta-assessment, 2026-06-24. Scope: the current single-attack draft in `Paper/Section/*.tex` + the `artifact/` code. Method: full primary read of all sections and the core artifact modules; a multi-agent audit (threat-model and novelty dimensions completed; math/eval/rq8/writing were cut off by a session rate-limit and are covered here from my own primary reading); plus one load-bearing finding I re-derived and reproduced against the artifact's own code._

---

## Bottom line

This is a **genuinely good paper with a sharp, honest thesis** — sharding doesn't change *whether* a committee can be made to equivocate, it changes the *economics*, and the only thing that decides consequence is whether value settles before accountability lands (the `Tsettle < Tacc` race), with finality-gating as an immunity rule. The framing is disciplined, the prior-art positioning is unusually careful, and the artifact is real. It is much further along than the older `deep-research-report.md` (which reviewed a sprawling 5-attack draft) implies.

But it is **not yet acceptance-ready at a top venue**, for three reasons that compound:

1. **A real correctness bug in a load-bearing equation** (the `psucc` feasibility band, Eq. 5–6) that the validation harness is structurally blind to.
2. **The headline profitability numbers quietly assume the adversary's hardest capability** (reliable view control) is free — the "bounded probability" lever is never priced into `E[Π]`.
3. **The attack's enabling assumption holds in zero documented production systems** — by the paper's own RQ7, every deployed system is finality-gated — so the live threat reduces to a single fast-bridge value path, which the (heavily hedged, partly rehearsed) RQ8 measurement carries more weight than the framing admits.

None of these sink the *defensive* thesis (they mostly make the attack look harder than claimed, which strengthens "deployed systems are safe"). But #1 is a fixable bug a sharp artifact evaluator will catch, and #2–#3 are framing/calibration issues that a top-venue reviewer will press hard.

**Verdict: major revision.** After the fixes below it is a credible CCS / USENIX Security submission and a plausible IEEE S&P one.

---

## What the paper does (one paragraph)

An adversary below the *network-wide* 1/3 corruption bound, but able to reach one committee's *local* threshold after membership is revealed, buys the `F+1` validators that quorum intersection makes **necessary** for two conflicting `2F+1` certificates in an `N=3F+1` committee. `F+1` is necessary but **not sufficient**: honest validators must also split across branches (probability `psucc`). The violation only pays if cross-shard/bridge settlement (`Tsettle`) beats detect→slash→revert (`Tacc`), factored into a window gate `Tsettle<Tacc` and an economic gate `V>B+Cop`, with bribe `B=(F+1)·q·(s+R)` priced by the enforcement probability `q`. Finality-gating forces `pwin=0` (immunity). A reconfiguration analysis extends this across epoch boundaries (safe-handoff vs. residual-vulnerability theorems). Evidence: closed-form model + Monte-Carlo + a discrete-event BFT testbed with real Ed25519 + a 6-system case study + a pre-registered RQ8 live measurement.

---

## Strengths (verified)

- **The novelty claim is defensible as a composition, and honestly framed.** No single prior work occupies the full intersection {committee-local sub-threshold bribery + quorum-intersection floor + latency-priced bribe + cross-shard settlement race + finality-gating immunity + reconfiguration handoff}. The paper explicitly disclaims inventing any individual ingredient ([introduction.tex:139-147](Paper/Section/introduction.tex#L139-L147)).
- **The nearest neighbors are all cited *and* sharply distinguished.** Camael / corrupted-shard tolerance (CCS'25), Economic Censorship Games (EC'25), STAKESURE, Budish ELPC, CoBRA, Bitcoin-enhanced PoS, and remote-staking (Dong'24) are each given a "we differ because…" ([related_work.tex:29-36](Paper/Section/related_work.tex#L29-L36), [:73-111](Paper/Section/related_work.tex#L73-L111)). The closest race/latency neighbor (remote staking) is *not* sandbagged in the positioning table — it gets the accountability-race and latency-`q` columns it deserves. The immunity idea is **not** over-claimed: the paper credits the accountable-finalized-prefix antecedent and positions its result as a specialization ([related_work.tex:95-96](Paper/Section/related_work.tex#L95-L96)).
- **The "necessary not sufficient" discipline is real, not cosmetic.** The artifact confirms a sub-floor purchase (`k<F+1`) yields conflicting finality in *zero* trials, and the floor `psucc` is correctly reported as modest (0.176 at N=31). This is materially better than the consensus-mistake version of the claim.
- **The network-wide-vs-committee-local "sub-threshold" distinction is load-bearing and applied consistently** (threat model → motivation → lemma → cost model → reconfiguration), and the paper carefully does *not* claim the adversary is below the *local* threshold.
- **Treating committee assignment as "given" (no randomness control) is the conservative direction** — the attack is shown to work *without* biasing assignment.
- **The artifact is honest in shape**: one source-of-truth model module, an independent MC estimator, a testbed that derives latencies from event timing with genuine Ed25519 evidence objects, a one-command seeded pipeline, and tables generated (not hand-typed). The relationship-to-known-attacks discussion cleanly separates this from cross-shard replay and opportunistic bridge reorgs ([discussion.tex:94-102](Paper/Section/discussion.tex#L94-L102)).

---

## Weaknesses

### 🔴 Major — Correctness bug in the `psucc` feasibility band (Eq. 5–6), invisible to the validation harness — ✅ NOW FIXED

> **Resolution (applied to this repo, 2026-06-24/25).** [model.py](artifact/shardbribe/model.py) band corrected to `[Q−k, N−Q]` (`hi = H − max(Q−k,0)`); the [run_all.py](artifact/run_all.py) validation and [test_model.py](artifact/tests/test_model.py) were extended to cross-check `k>F+1` (all 21 tests pass; regeneration `max|psucc_mc−psucc_cf| = 0.0061`); [plot_figures.py](artifact/plot_figures.py) now overlays Monte-Carlo on every curve; the artifact was regenerated (`fig_psucc` k=F+2 peak 0.497→**0.352**, k=F+3 0.712→**0.518**, MC matching); and the downstream prose was corrected to "k≈F+6 (≈1.45×)". The diagnosis below remains for the record.

**This is the most important finding and I verified it three ways (re-derivation, code trace, and against the artifact's own functions).**

The closed form models two conflicting certificates from `k` equivocators (who sign both branches) plus an honest split `h_A ~ Binomial(H, φ)`, `H=N−k`. Both branches certify iff `k+h_A ≥ Q` **and** `k+(H−h_A) ≥ Q`. The second constraint gives

```
h_A ≤ H − (Q − k) = N − Q = F          (independent of k)
```

so the true feasible band is **`[Q−k, F]`**, width `k−F`. But the paper and code use **`hi = k−1`** (band width "`2k−2F−1`"):

- Prose: [methodology.tex:80-86](Paper/Section/methodology.tex#L80-L86) ("`Q−k ≤ h_A ≤ k−1`", width `2k−2F−1`).
- Code: [model.py:83](artifact/shardbribe/model.py#L83) `hi = k - 1`.

`k−1` only equals `F` at the floor `k=F+1`; for `k>F+1` it is **too large**. The `bft_harness` Monte-Carlo path is *correct* — `conflicting_finality` requires both certs to reach `Q` ([bft_harness.py:163-167](artifact/shardbribe/bft_harness.py#L163-L167)) — so the closed form and the (correct) simulator **diverge for every `k>F+1`**.

**Magnitude (N=31, k=F+2=12, φ=½):**

| quantity | band | `psucc` |
|---|---|---|
| closed form (`model.py`) | `[9, 11]` | **0.497** |
| true / what the MC harness produces | `[9, 10]` | **0.352** |

A **0.14 absolute (≈41% relative) overstatement — 7× the artifact's own 0.02 tolerance.** Concrete falsification: at `h_A=11`, branch B has `k+(H−h_A)=12+8=20 < Q=21`, so it does **not** certify; the closed form wrongly counts it.

**Why nobody caught it:** the validation loop runs **only at `k=equivocation_floor(N)=F+1`** ([run_all.py:54](artifact/run_all.py#L54)), and the figure's MC overlay is computed **only at `k=F+1`** ([run_all.py:132](artifact/run_all.py#L132)) — the one place the buggy and correct bands coincide. `tests/test_model.py::test_mc_matches_closed_form` likewise only checks the floor. So the paper's headline methodological claim — "the testbed/MC agreement is a *genuine cross-validation rather than a tautology*" ([implementation.tex:9-13](Paper/Section/implementation.tex#L9-L13)) — is only ever established at the single point where the two formulas are equal by construction. `fig_psucc` plots closed-form curves for `k∈{F+1,F+2,F+3}` but overlays MC dots only on the `F+1` curve, so the divergence is never shown.

**Downstream impact:**
- The repeated cost claim "reaching `psucc≈0.85` needs `k≈F+5`" ([methodology.tex:96-98](Paper/Section/methodology.tex#L96-L98), [evaluation.tex:82-83](Paper/Section/evaluation.tex#L82-L83), [limitations.tex:20-21](Paper/Section/limitations.tex#L20-L21)) is computed from the *inflated* formula, so the true bribe needed to reach a given `psucc` by purchase is **higher** than stated.
- Direction is **attacker-favorable** (overstates attack feasibility) → the defensive conclusion is unaffected or strengthened. So this is not thesis-breaking, but it is a real bug in a published equation plus a validation-coverage gap, which is exactly what an artifact-evaluation committee looks for.

**Fix:** in [model.py](artifact/shardbribe/model.py), `hi = (N - quorum_of_N(N))` i.e. `hi = H - max(Q-k, 0)` (clamp `hi=min(hi,H)`); correct the width to `k−F` and the count formula in [methodology.tex:84-86](Paper/Section/methodology.tex#L84-L86); **re-run the MC validation at `k=F+2,F+3` too** and re-plot `fig_psucc` with MC overlays on every curve; then recompute the "`k≈F+?` to reach 0.85" sentence. (At N=31 the corrected first `k` clearing 0.85 will be larger than F+5.)

### 🟠 Major — Headline profit numbers price the adversary's hardest capability at zero

RQ3 (phase diagram) and the RQ5 defense baseline (`E[Π]=+38.9`) fix `psucc=0.85` while using `B=8.25`, which is the bribe for buying **exactly the `F+1` floor** (`bribe_total(31, q=0.5, R=0.5) = 11·0.5·1.5 = 8.25`, [model.py:98-110](artifact/shardbribe/model.py#L98-L110)). But `psucc=0.85` at the floor bribe is achievable *only* in the "view-control" regime — where the adversary reliably occupies the leader / forces a near-even split — which the threat model grants only **"with bounded probability"** ([threat_model.tex:8-9](Paper/Section/threat_model.tex#L8-L9)). That `Pr[adversary controls the view this epoch]` is **never multiplied into `E[Π]`**; it is implicitly 1 in every headline figure. The paper *says* it "brackets" results against the uncontrolled-split floor ([methodology.tex:99-102](Paper/Section/methodology.tex#L99-L102)), but Fig. 3 and the RQ5 table report only the 0.85 point.

**Fix:** add an explicit `p_view < 1` factor to `E[Π]` and sweep it, or carry **both** the floor-bribe/uncontrolled-`psucc` point and the view-control point as a visible band in every headline figure. State plainly that `B=8.25` and `psucc=0.85` coexist only under *reliable* (not bounded-probability) view control.

### 🟠 Major — The immunity proposition is near-definitional, and its enabling assumption holds in no deployed system

`pwin := Pr[Tsettle<Tacc]`, so Prop. 1 ("if `Tsettle≥Tacc` then `pwin=0`") is essentially the definition restated; the proof substitutes the hypothesis directly ([methodology.tex:207-212](Paper/Section/methodology.tex#L207-L212)). The paper half-admits this ("a design rule as much as a theorem", [methodology.tex:214](Paper/Section/methodology.tex#L214)) but should say it outright. More substantively, **Assumption 3 (asynchronous/ungated settlement)** is what opens the window, and "an open window exists" is close to the attack's thesis — yet RQ7 finds **every** surveyed deployed system is finality-gated ([evaluation.tex:181-196](Paper/Section/evaluation.tex#L181-L196)), i.e. Assumption 3 fails for all of them. So the live threat does not exist in any documented production system; it lives entirely in the fast-exit/ungated-bridge path, which RQ8 measures.

**Fix:** reframe the contribution as "*which* real cross-shard/bridge designs violate gating, and by how much," foreground the RQ8 fast-bridge result as the load-bearing evidence, and label Prop. 1 explicitly as a checkable design rule rather than a substantive safety theorem.

### 🟠 Major — Recruitment/coordination of `F+1` specific validators is abstracted away

The operationally hardest step — identifying and getting `F+1` *specific, named* revealed committee members to all register-and-equivocate within one epoch — is the most idealized. Assumption 1 prices a *single* validator ([threat_model.tex:42-45](Paper/Section/threat_model.tex#L42-L45)); the algorithm treats "recruit `F+1`" as one atomic step ([methodology.tex:245](Paper/Section/methodology.tex#L245)); the escrow handles payment trustlessness but not the n-of-n simultaneity or the **first-defector / whistleblower** problem (a single honest validator who reports first can break the attack and may earn a counter-bounty > the bribe; cf. `kelkar2025omerta`, conceded at [limitations.tex:45-48](Paper/Section/limitations.tex#L45-L48)).

**Fix:** add at least a qualitative coordination-game treatment — a recruitment-success factor `p_recruit` folded into `E[Π]`, and the whistleblower/counter-bribe equilibrium. Even a back-of-envelope bound would raise realism.

### 🟡 Minor

- ~~**"`k≈F+5` at `1.36×`" is internally inconsistent.**~~ **Retracted** (was an agent miscount that I initially propagated): F+5 = 15 and 15/11 = 1.36×, so the *ratio* was consistent. The real issue was the `psucc` *value* — under the corrected band k=F+5 gives only `psucc≈0.79`, and reaching 0.85 needs **k≈F+6 (≈1.45×)**. Already fixed as part of the band correction above.
- **Capability (iv) conflates two non-equivalent levers.** "Induce asynchrony" only *randomizes* the honest split (modest `psucc` gain) while "occupy the leader" can *deterministically* force `φ≈½` (high `psucc`); the binomial-`φ` model can't tell them apart, yet the `Cov(psucc,pwin)≥0` argument ([methodology.tex:155-160](Paper/Section/methodology.tex#L155-L160)) leans on treating them as one.
- **Positioning-table caption over-reaches slightly.** "The only row populated across every dimension" ([related_work.tex:161](Paper/Section/related_work.tex#L161)) is partly an artifact of choosing the contribution axes as the columns. The uniqueness is *real* (no neighbor holds {committee-local + cross-shard-V + immunity + impl}) and not achieved by sandbagging, but the caption should be softened to "across the dimensions that jointly define this attack class" to match the honest prose in the introduction.
- **A few low-threat adjacents remain uncited** (Nag et al. multi-SSP economic security; Proof of Diligence watchtowers) — optional one-line cite-and-distinguish to pre-empt the restaking reviewer; not required.

---

## RQ8 measurement section — honesty audit (my read)

This is the highest-reputational-risk section, and on the whole it is **commendably careful** — but it is doing a lot of hedging, and a reviewer will need to read it twice to learn what was actually done. Strengths: it cleanly separates **real-data arms** (passive Cosmos double-sign/tombstone events; 1,721 Across V3 bridge fills; native-IBC Cosmos→Osmosis) from **in-process "shadow" rehearsals** (the paired race, the fast-exit positive control), and the abstract's "the paired race and dual verdict are an in-process rehearsal … not a production run" ([abstract.tex:19-22](Paper/Section/abstract.tex#L19-L22)) matches the body and limitations. The `q_max` story is honest about being an enforcement-conditional **upper bound** dominated by a single 51-evidence batch enforced ~25 days late, and reports the per-incident ≈0.97 alongside ([measured_evaluation.tex:74-86](Paper/Section/measured_evaluation.tex#L74-L86)). The bias-control design (`Tacc^hi` against rule-outs, `Tacc^lo` against open-windows) is a genuinely good idea.

Concerns to address before submission:
- ~~**Numerous `\providecommand{...}{[pending]}` placeholders** are not yet filled.~~ **Retracted** (refuted by the audit's adversarial verification, which ran `pdftotext` on the compiled `main.pdf` and found **zero** `[pending]` strings): those `\providecommand` lines are compile-safety *fallbacks*, overridden by the artifact-generated `Paper/Section/_generated/tab_summary.tex` (input *before* `measured_evaluation.tex`), so the compiled PDF carries real numbers throughout (q_max=0.32 CI [0.22,0.44], bridge `Tsettle` median 5.0s, verdicts ruled-out/open-window). The residual risk is only a *build-hygiene* one: the generated dir must be committed/regenerated, since the table is `\IfFileExists`-gated and would silently vanish if stale (worth a CI guard).
- The section "**substantially advances but does not fully discharge**" limitation (3) ([measured_evaluation.tex:186-188](Paper/Section/measured_evaluation.tex#L186-L188)) — honest, but given that the live threat reduces to this one path (see the immunity-framing point above), the burden on it is heavier than the prose concedes. The real-client-code localnet run that "remains owed" is closer to load-bearing than optional.
- The decision rule is well-specified, but verify it isn't *ceremony around a foregone conclusion* — the structural finality-gating argument already determines the Cosmos verdict before any measurement, so make explicit which verdicts the data could actually have flipped.

---

## Presentation

The thesis lands and the title is good. The main presentation risk is **density**: the prose (especially `measured_evaluation.tex`) stacks nested hedges to the point where rigor starts to read as defensiveness — e.g. the single sentence at [measured_evaluation.tex:44-46](Paper/Section/measured_evaluation.tex#L44-L46) carries four parenthetical qualifications. For a conference page budget the paper is also table/figure-heavy (15+ floats across 16 sections + appendices). Consider: (a) tightening the RQ8 hedging into a short "provenance" table + plain claims; (b) merging the two reconfiguration propositions' prose; (c) moving the documented-parameter RQ7 table to an appendix now that RQ8 measures the same quantities. The contribution list is well-calibrated to what is delivered.

---

## Prioritized fixes

**Must-fix (blocking):**
1. ~~**Correct the `psucc` band**~~ — ✅ **DONE** (`hi = H − max(Q−k,0)` → band `[Q−k, N−Q]`; validation + unit tests extended to `k>F+1` and passing at max_err 0.0061; `fig_psucc` re-plotted with MC overlays on every curve; artifact regenerated; prose → "k≈F+6, 1.45×").
2. **Price the view-control capability**: put an explicit `p_view<1` (or `p_recruit`) factor into `E[Π]`, or show both regimes as a band in Fig. 3 / RQ5.
3. ~~**Fill the RQ8 `[pending]` scalars**~~ — **retracted** (the compiled PDF already carries real numbers; see RQ8 section). Replace with: **reconcile the abstract with the regenerated body** (RQ8-1 below) and **add a build guard** that fails if any `\Artifact` RQ8 macro is still `[pending]`.
4. **Reframe Prop. 1 and Assumption 3** as a checkable design rule + foreground the fast-bridge path as the actual live evidence (the audit confirms Prop. 1's content is the reduction `E[Π]=−(B+Cop)`, not the definitional `pwin=0` step).

**Should-fix:**
5. Add a qualitative recruitment/whistleblower coordination treatment.
6. Fix the `F+5`/`1.36×` inconsistency and separate the two capability-(iv) levers.
7. Soften the positioning-table caption; optionally add Nag / Proof-of-Diligence cites.
8. Cut RQ8 hedging density; trim float count.

---

## Venue read

- **As-is:** reject (bug + `[pending]` results + the calibration gaps).
- **After must-fixes:** a credible **CCS / USENIX Security** submission — the composition novelty is defensible, prior art is well-handled, and the artifact (once the band is fixed and re-validated) is a real asset. **IEEE S&P** is reachable if the theory statements are tightened (Prop. 1 reframed) and the RQ8 real-client-code run is completed so the one live threat path is measured, not rehearsed.

---

## Completer audit — integrated 6-dimension findings (adversarially verified)

_Added 2026-06-25 after the completer pass (math / RQ8 / presentation reviewers + a synthesis over all six dimensions). The `eval` reviewer dropped out on a schema-retry cap; its concerns are covered by the math and threat dimensions. Each critical/major finding got an independent skeptic; verdicts below reflect that verification._

**Integrated verdict: major-revision** (both passes agree). Headline: *a novel, mathematically sound reframing with an honest real-data audit, held back by an abstract↔body provenance inconsistency, the still-rehearsal status of the load-bearing paired-race empirics, and an over-floated/over-hedged presentation — correctable without new experiments.*

**Math is independently sound (verdict: strong).** A second reviewer re-derived every load-bearing result: the quorum Lemma (`2(2F+1)−(3F+1)=F+1`); the `Cov≥0 ⇒ factored product is a lower bound ⇒ V* is a conservative upper bound` argument (sign correct, i.e. non-overclaiming); **both** reconfiguration proofs deliver a *strict* (not merely non-decreasing) increase on the boundary region; the gamma-stage race CV algebra (`kshape=1/(n·cv²)`, verified empirically); and the bribe summation. The **band fix is confirmed resolved** and the corrected `k≈F+6 / 1.45×` numbers are internally consistent across all four sections, with the test guards in place.

**The verification corrected three of my own (and the first pass's) harsher findings — recorded honestly:**
- ❌ **Refuted — RQ8 "`[pending]` placeholders":** the compiled `main.pdf` contains **zero** `[pending]`; they are overridden fallbacks (see retraction above). Downgraded to a build-hygiene note.
- ⬇️ **Downgraded — RQ8 over-hedging "major":** two of the three "worst offender" sentences are actually well-structured, load-bearing scoping (the abstract's rehearsal-vs-production line is *required* disclosure); only one dense parenthetical ([measured_evaluation.tex:42-46](Paper/Section/measured_evaluation.tex#L42-L46)) is a genuine prose nit. **Minor.**
- ⬇️ **Downgraded — float/length "major":** counts are right (23 body floats; eval alone has 7 figs + 3 tables) but the paper is a **~22-page full version**, so floats aren't "crowding out prose"; the real issue is body length vs. a ~13-page conference budget. **Minor (but real).**

**New verified findings not in my solo pass:**
- 🟠 **Major (RQ8-2) — the load-bearing OPEN-race evidence is still a shadow rehearsal.** The decisive paired `pwin=1.00` that flips the bridge to OPEN comes from an in-process `shadow` backend; the real-client arms are thin (a single gaiad localnet double-sign, n=1; a q-only 40-episode fast-exit unbond, no paired race). The Cosmos `ruled-out` is structurally pre-determined by Prop. 1 before any data. So "dual verdict on real paths" reads stronger than the evidence — though the paper discloses this consistently, so it's a scope-framing fix, not misrepresentation. (Aligns with my "the live threat lives only in the fast-bridge path" point.)
- 🟡 **Minor (RQ8-1) — abstract↔body provenance inconsistency (an *under*claim).** [abstract.tex:19-21](Paper/Section/abstract.tex#L19-L21) blankets the fast-exit positive control as "an in-process rehearsal … not a production run on consensus client code," but the regenerated macros ([tab_summary.tex], [tab_measured.tex]) now report it on **real gaiad v19 client code** on a private localnet. One-sentence sync fix (ideally drive the abstract line from the same `\Artifact` macros).
- 🟡 **Minor (RQ8-4) — bridge `Tsettle` n mismatch.** Prose cites "1,721 Across V3 fills," but the 5.0s median was fit on **n=1592** after dropping 129 zero/degenerate fills (raw median 4.0s). Report the analyzed n and reconcile 4.0s-raw vs 5.0s-fit.
- 🟡 **Minor (F7) — V\* definitional split.** [model.py](artifact/shardbribe/model.py) / `tab_breakeven` use `V*=B+Cop` (the `psucc=pwin=1` limit) while the prose says `V*∼1/(psucc·pwin)`; write the general `V*=(B+Cop)/(psucc·pwin)` once and label the table as the deterministic special case.
- ✅ **Minor (F8) — `k≤Q` validity note: DONE.** Added a comment to `psucc_closed_form` noting the `hi=N−Q` derivation assumes `k≤Q` and that `k>Q` correctly degenerates to `psucc=1`.
- 🟡 Other should-fixes: a build guard that fails on any residual `[pending]` macro (RQ8-3); log the negative-control public-channel substitution in a dated `DEVIATIONS.md` per the prereg's own rule (RQ8-5); update the stale `MEASUREMENT.md` runbook expectations (`q_max~1.0`, `~8s`) to the executed values (RQ8-6); state Prop. 1's content is the reduction `E[Π]=−(B+Cop)` to pre-empt the "tautology" read (F2).

**Net change vs. my solo assessment:** verdict unchanged (major-revision); the math is now *independently* confirmed sound; my band finding is fixed and verified; two of my findings were corrected by adversarial verification; and the must-fix list is sharpened to **(1) reconcile the abstract's provenance, (2) scope the paired-race contribution precisely** — both correctable without new experiments.

---

### Provenance of this assessment
All six dimensions now have a completed reviewer pass with an independent adversarial-verification stage (threat + novelty from the first run; math + RQ8 + presentation from the completer; `eval` covered by math/threat after its reviewer dropped on a schema-retry cap). The `psucc` band bug and the validation-coverage gap were **my own**, derived and reproduced against `artifact/` code — and have now been **fixed, re-validated (all 21 tests green, max_err 0.0061 above the floor), and the artifact regenerated**. Where the verification refuted or downgraded a finding (including two of mine), I have marked it inline rather than quietly dropping it.
