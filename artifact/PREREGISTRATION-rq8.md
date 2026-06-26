# Pre-Registration — RQ8: Measuring $q$, $T_{\text{acc}}$, $T_{\text{settle}}$ on deployed systems

**Tag to freeze before any data is touched:** `prereg/rq8-v1`
**Status:** frozen runbook. The estimators, $\varepsilon$, sample sizes, and the decision rule
below are committed *before* collection. Any post-hoc deviation goes in a dated
`DEVIATIONS.md`, never silently into this file.

This document closes the decisive gap flagged in `Paper/Section/limitations.tex` (3) and
`Paper/README.md` ("measure the two load-bearing quantities $q$ and $T_{\text{acc}}$ on one
concrete deployed sharded design, and exhibit or rule out a real open window"). It operationalizes
the "Live-measurement hook" paragraph already in `Paper/Section/experimental_setup.tex`.

---

## 1. Objective and the single success criterion

> On at least one genuinely deployed system we **measure** $q$, $T_{\text{acc}}$, and
> $T_{\text{settle}}$ (with uncertainty) under this pre-registered protocol, and **the same
> instrument** that returns **RULED-OUT** on a finality-gated cross-shard path (CometBFT/IBC)
> returns **OPEN-WINDOW** on a real ungated fast-settlement path. The model's safe/exposed
> dichotomy thereby becomes an instrument-calibrated empirical fact, and every deployed design
> gets an exact **distance-to-cliff** (the settlement speed at which it flips from safe to exposed).

This is a **two-target, dual-verdict** design on purpose. A string of RULE-OUTs is unfalsifiable
and does not change the paper's punchline; the design is credible only if one instrument fires
**both** verdicts on real paths, plus two controls calibrated to known outcomes.

---

## 2. Targets (frozen)

| Role | System / path | Expected verdict | Why |
|---|---|---|---|
| **Primary safe** | Cosmos Hub `cosmoshub-4` (CometBFT evidence + IBC) | RULED-OUT | Richest *real* equivocation-slashing data; IBC is structurally finality-gated ($T_{\text{settle}}\ge T_{\text{acc}}$). |
| **Primary open** | Across V3 SpokePool (deBridge DLN corroborator), source = CometBFT/EVM chain | OPEN-WINDOW | Only regime where a real value-realizing path has $T_{\text{settle}}\approx$ seconds $\ll T_{\text{acc}}$. |
| **Negative control** | Native IBC on a self-run two-zone devnet | must return RULED-OUT | Provably finality-gated; proves the instrument can return safe. |
| **Positive control** | Constructed fast-exit devnet (short unbonding + short evidence-age + ungated sink) | must return OPEN-WINDOW | The literal `realsystems.py` "Fast-exit (hypothetical)" row, now **measured**; the only place a low-$q$ regime is observable. |

**Demoted to a documented-parameter table only** (not live-measured, to keep this one-RA-feasible):
Polkadot, NEAR, MultiversX, Zilliqa, Harmony. NEAR/MultiversX have **no production slashing** →
their $q$ is reported as `N/A (kickout proxy)` in a *firewalled* sub-panel, never on the same
$q$-axis as slashing systems. These are corrected rows in `realsystems.py` (§7), not tracks.

**Construct-validity note (Cosmos is not itself sharded).** We map the paper's *accountability
layer* (observe → propagate → enforce → revert) onto the CometBFT consensus/evidence layer, which
is architecturally identical across sharded designs; sharding changes only $T_{\text{settle}}$ (the
cross-domain hop), which we measure via IBC as the cross-committee analogue **and** corroborate the
genuinely-sharded source→destination hop on the self-run **two-zone IBC devnet**.

---

## 3. What is measured, by what method, and why it equals the formal quantity

All records are emitted in the **exact `testbed.run_round` schema** so `estimate.py` and the
existing `measure_pwin` machinery run unchanged on real data. Extended record:

```
# existing testbed keys (verbatim): t_certA, t_certB, t_fork, t_detect, T_settle, T_acc, fork_formed
# new q-arm + settlement legs + provenance:
t_infraction, t_evidence_committed, t_slash_effective,
t_withdraw_unslashable, evidence_expiry_deadline,
t_src_cert, t_dst_receipt, t_withdraw_final,
src_chain, dst_chain, height, block_time, source, measurement_resolution_ms
```

**Triangulation rule (mandatory):** every quantity is measured by $\ge 2$ methods whenever a single
method has a proxy gap; each verdict must survive the bias direction working *against* it.

### 3.1 $q = \Pr[t_{\text{slash}} < t_{\text{withdraw}}]$ — split into two named estimands

The classic error is to measure $q$ against the 21-day **unbonding** wall-clock. Cosmos slashing
follows the stake through unbonding/redelegation, so the *true* unslashable deadline is the
**CometBFT evidence-expiry** (`MaxAgeDuration` $\approx 2$d / `MaxAgeNumBlocks`).

- **$q_{\max}$ (structural ceiling, no one races):** $\Pr[t_{\text{evidence\_committed}} <
  \text{evidence\_expiry\_deadline}]$.
  Measured **passively** from real Cosmos `DuplicateVoteEvidence` + tombstone events
  (self-run `gaiad` archive node: `/block`, `/block_results`, `/block_search?query=evidence`,
  `/tx_search`; cross-checked vs Numia/Mintscan). $t_{\text{infraction}}$ = `block.Time` at the
  infraction height inside the evidence; $t_{\text{slash\_effective}}$ = the BeginBlock
  `slash`+`tombstone` event. Reported as an **upper bound** on $q$ with a censoring-adjusted lower
  bound (see §4.1).
- **$q_{\text{attack}}$ (adversary-conditional, the thing that prices the bribe):** requires a
  validator that *attempts a timed exit* — **unmeasurable from accidental incidents**. Measured only
  on the **self-equivocation devnet** and the **fast-exit positive control**, where we initiate the
  equivocator's unbond at $t_{\text{infraction}}$ and observe whether the slash still catches the
  stake ($t_{\text{withdraw\_unslashable}}$ directly observed).

### 3.2 $T_{\text{acc}}$ — observe + propagate + enforce + revert

Reported as a **decomposed 4-vector**, never a single scalar, with two bounds:

- **$T_{\text{acc}}^{\text{lo}}$ (cooperative-detection floor):** from real Cosmos incidents
  (offenders cooperate → lower bound) **plus** real-internet propagation from **$\ge 4$
  geographically dispersed self-run full nodes** subscribed to consensus gossip (supplies the
  observe/propagate term that no simulator can).
- **$T_{\text{acc}}^{\text{hi}}$ (adversarial upper bound):** from a **shadow-fork / self-equivocation
  devnet evidence-suppression experiment** — withhold/delay evidence gossip and eclipse the
  would-be reporter to protocol tolerance, running the real `x/evidence`→`x/slashing` code paths.
- **Revert term:** deterministic-finality CometBFT blocks never revert. We report
  `t_revert = NA (no protocol revert)` **explicitly** and define the operative quantity as
  $T_{\text{acc}}^{\text{econ}}$ (slash applied) **plus** the measured **cross-domain quarantine**
  latency (destination IBC light-client freeze on the two-zone devnet) as the genuine
  "quarantine the bad branch" analogue. Governance-halt durations (e.g. Hub Prop #818) are a
  **separate, separately-reported channel** — never spliced into the protocol revert term.

### 3.3 $T_{\text{settle}}$ — destination receipt + withdrawal **beyond clawback**

Reported as **two legs**, never merged:

- **User leg** (the attacker's realized $V$): $t_{\text{dst\_receipt}}$ = the seconds-scale
  irreversible destination fill (`FilledV3Relay`). This is never clawed back from the recipient,
  even when the source reorgs — it **is** the realized value.
- **Solver leg** (clawback-gated): $t_{\text{withdraw\_final}}$ = solver repayment
  (`HubPool RootBundleExecuted` / DLN `ClaimedUnlock`), pinned to a **directly observed
  irreversibility test**, not inferred from fill latency:
  1. **Reorg natural-experiment** (mandatory): mine documented production reorgs (Ethereum
     7-block May-2022; Polygon deep reorgs) for `V3FundsDeposited` events later reorged-**out**, and
     check whether solver repayment fired anyway.
  2. **Config-read:** on-chain dispute/clawback constant (Across UMA $\approx$2h liveness;
     deBridge strict-finality wait).
  3. **Shadow-fork:** fork an L2, inject a reorg of a deposit block, observe whether solver-unlock
     correctly refuses → gives $q_{\text{solver}}=\Pr[\text{clawback lands}]$.
- Native IBC ($T_{\text{settle}}$, negative control): `SendPacket` finalized header →
  `UpdateClient`→`MsgRecvPacket` inclusion → `MsgAcknowledgement` past timeout. The destination
  acts only on a **final** source header ⇒ $T_{\text{settle}}\ge T_{\text{acc}}$ is structural.
- **Adversarial-tail calibration:** build the *attacker-realistic* fast tail from bridge-exploit /
  intent-bridge liquidity-exhaustion postmortems (Nomad/Wormhole/Multichain/Ronin/Horizon),
  timestamping value-creation → cash-out → any clawback.

---

## 4. Statistical and pre-registered falsification framework

Implemented in `shardbribe/estimate.py` (pure stats, **no network**), validated against
`testbed.measure_pwin` as a synthetic oracle (`estimate.self_test()` recovers the testbed's
`pwin_measured`/`rho_measured` within CI before any real data is touched).

### 4.1 Estimators
- **$q$:** Bernoulli $\hat q = (\text{enforced before unslashable})/n$, **exact Clopper–Pearson**
  95% CI; **Jeffreys** as robustness; **rule-of-three** upper bound for zero-event chains. Reported
  as the interval $[\text{conditional}, \text{evidence-age-cap-adjusted lower bound}]$; the point
  near 1 is labeled an **upper bound** (survivorship: $q_{\max}$ is conditioned on enforcement
  having happened; censored slow-detection mass bounded via the evidence-age cap and a
  liveness-fault-rate proxy for undetected infractions).
- **$T_{\text{acc}}$, $T_{\text{settle}}$:** dual track — (a) parametric Gamma + log-normal MLE,
  AIC-ranked, bootstrap KS / Anderson–Darling GOF; (b) **empirical CDF** + order-statistic
  quantiles; **Hill tail-index** when GOF rejects light tails (a heavy $T_{\text{acc}}$ tail is
  itself a finding — it widens windows). The decision statistic uses **nonparametric quantiles**
  ⇒ distribution-free.
- **$\rho = T_{\text{acc}}/T_{\text{settle}}$:** both mean-ratio (matches `measure_pwin`) and
  decision-quantile ratio; percentile-bootstrap CI on the ratio.
- **$p_{\text{win}}$:** for the open-window target use **paired** joint observations only
  (shadow-fork + self-fill episodes share $t=0$, network draw, epoch). Passive marginals from two
  different event populations are used **only** for distributional calibration — the
  independence/convolution assumption is explicitly **disowned**. $\hat p_{\text{win}}$ via **BCa
  bootstrap** ($B\ge 10{,}000$) + Wilson interval for the proportion.

### 4.2 Sample sizes / power
- Self-equivocation / shadow-fork episodes: **$N\ge 40$ per chain** (Wilson upper bound on
  $p_{\text{win}}=0$ is $\approx 0.09$ at $N{=}40$; rule-of-three: $N\ge 300$ zero-win runs ⇒ 95%
  upper bound $<0.01$ for a clean RULE-OUT). Feasible **only** on a private localnet where the
  equivocation is resettable (no permanent tombstone, no faucet rate-limit) — shared-testnet
  repetition is **not** used.
- $T_{\text{settle}}$ from real bridge transfers: **$N\ge 10^3$–$10^4$** (datasets provide
  $10^5$–$10^6$) so tail-quantile bootstrap half-width $<20\%$ of the decision gap.
- Passive $q$ / $T_{\text{acc}}$ incidents are single-digit-to-dozens ecosystem-wide ⇒ reported as
  **descriptive with wide CIs**; the quantile/TOST machinery is reserved for $T_{\text{settle}}$
  (large $n$) and the devnet pipeline (controlled $n$). We do **not** pre-register a
  quantile-separation test that single-digit $T_{\text{acc}}$ samples can never satisfy.

### 4.3 The exact decision rule (frozen; per value-realizing path; Holm-corrected across $K$ paths)

Let $T_{\text{acc}}^{\text{lo}}$ = cooperative lower bound, $T_{\text{acc}}^{\text{hi}}$ =
adversarial upper bound, $\varepsilon = 0.05$.

- **OPEN-WINDOW CONFIRMED** iff (evaluated conservatively against $T_{\text{acc}}^{\text{lo}}$ so we
  never over-claim with an inflated $T_{\text{acc}}$): one-sided 95% **upper** CI of
  $\hat p_{\text{win}} > \varepsilon$ **AND** 95% CI for $\text{median}(\rho)$ excludes 1 from below
  **AND** gate **G2** is clearable at the measured $q$ for a plausible reachable $V$.
- **WINDOW RULED OUT** iff (evaluated against $T_{\text{acc}}^{\text{hi}}$, the bias working against
  a rule-out): one-sided 95% **upper** bound of $\hat p_{\text{win}} \le \varepsilon$ across every
  settlement cell, **OR** the path is structurally finality-gated (assert $p_{\text{win}}=0$ by
  Proposition 1 and corroborate with $q_\alpha(T_{\text{acc}}) \le \text{median}(T_{\text{settle}})$).
- **INDETERMINATE** otherwise → report the CI and the additional sample size that would resolve it
  (never silently "no window").

**G2 re-derivation for the open path.** For the fast-bridge self-fill case the loss falls on the
**solver**, so we report **two economic gates**: (i) classic $B=(F{+}1)\,q\,(s{+}R)$ on validator
stake with measured $q\approx1$ (expensive bribe); (ii) a solver-grief gate where $V$ = solver-fronted
fill. We **explicitly test whether a plain reorg (no bribe) already grifts the solver** — if so, the
equivocation primitive is **not** load-bearing for the bridge window, and the bridge result is framed
as a **distinct** threat (relayer credit risk), separated from the committee-bribery attack. This
forecloses the "you just rediscovered bridge reorg risk" rejection.

### 4.4 Null result as a credible finding + distance-to-cliff
The expected Cosmos RULE-OUT is reported as a **TOST equivalence certificate** ("measured
$\hat q\in[\cdot,\cdot]$, $T_{\text{acc}}$/$T_{\text{settle}}$ distributions on $K$ real paths, and the
pre-registered $\text{upper-CI}(p_{\text{win}})<\varepsilon$ test PASSED at coverage $1-\alpha$").
Then, from the measured $T_{\text{acc}}$ distribution we compute the **distance-to-cliff**: the exact
settlement-speed threshold $T^{*}_{\text{settle}} = q_\alpha(T_{\text{acc}})$ at which each design
**flips** to exposed, and how close each real system sits to it. This converts "they are safe" into a
falsifiable, actionable cliff distance — the real-world bite the paper was missing.

---

## 5. Ethics, legality, coordinated disclosure

**The bribery/equivocation leg is NEVER executed on any mainnet or shared network.**

- **Passive arms:** read-only over already-public ledger data via documented public RPC/indexer APIs
  within rate limits, or (preferred) self-hosted archive nodes. Reading public chain state
  circumvents no access control. Heavy history uses a **paid indexer tier or self-run archive node**,
  not front-end scraping (ToS-clean).
- **Self-equivocation:** only our own validator key + our own faucet/genesis stake, on a **private
  isolated localnet / shadow-fork only**; the equivocation-trigger code is **chain-ID-gated** to
  localnet/fork IDs. No shared-testnet equivocation.
- **Shadow-fork:** private forked-state clone, new chain-id, never peers with mainnet.
- **Bridge measurement:** read-only event replay of ordinary already-settled transfers + our own
  funds on testnet; no fraudulent branch is broadcast to a live chain; we never bribe, never recruit
  $F{+}1$.
- **Coordinated disclosure** triggers **only if** the pipeline returns OPEN-WINDOW on a *named
  deployed system on a value-realizing path the attacker controls*: notify maintainers, embargo, gate
  exploit-enabling artifacts (consistent with `Paper/Section/ethical_considerations.tex`). The released
  artifact ships the measurement **harness + schema**, not a turnkey mainnet equivocation tool.
  Disclosure dry-run scheduled Week 7.

---

## 6. Threats to validity (with mitigations)

| # | Threat | Mitigation |
|---|---|---|
| T1 | $q$ is the defense-side counterfactual, not the model's $q$ | Split $q_{\max}$/$q_{\text{attack}}$; measure $q_{\text{attack}}$ only on devnet; label passive $q$ an upper bound. |
| T2 | Revert term unobservable ⇒ $T_{\text{acc}}$ biased low ⇒ invalid RULE-OUT | 4-vector with `t_revert=NA`; RULE-OUT uses **adversarial upper-bound** $T_{\text{acc}}$; measure cross-domain quarantine; never splice governance halts. |
| T3 | Adversarial vs accidental detection | Evidence-suppression/eclipse experiment ⇒ upper-bound $T_{\text{acc}}$; verdict robust across $[T_{\text{acc}}^{\text{lo}},T_{\text{acc}}^{\text{hi}}]$. |
| T4 | $q\approx1$ only; low-$q$ regime unmeasured | Fast-exit **positive control** measures a real low-$q$ window. |
| T5 | Open window isn't the paper's attack / prior-art reorg | Self-filler $V$-realization + re-derived G2 (solver-borne) + explicit plain-reorg test; framed as distinct threat if reorg alone suffices. |
| T6 | $T_{\text{settle}}$ to receipt, not beyond-clawback | Direct irreversibility test: reorged-deposit natural experiment + on-chain dispute constant + shadow-fork reorg injection. |
| T7 | $p_{\text{win}}$ by convolving independent marginals | $p_{\text{win}}$ only from **paired** joint observations; marginals for calibration only; independence disowned. |
| T8 | Testnet $\ne$ mainnet propagation/params | Real-topology multi-node propagation listening; mainnet params substituted; $\rho$ (a ratio) cancels common scale. |
| T9 | Shadow-fork propagation is netem-modeled | netem demoted to *stress overlay*; real propagation from multi-node listening; fork claims only enforcement-mechanism latency. |
| T10 | Block-time quantization corrupts sub-block deltas | Any delta $<\sim2$ block intervals refused from on-chain timestamps; require consensus-log sub-block instrumentation; `measurement_resolution_ms` on every latency; CIs propagate quantization. |
| T11 | Selection/survivorship inflates $q$, truncates $T_{\text{acc}}$ tail | $q$ as interval with evidence-age-cap lower bound; undetected-infraction-rate proxy. |
| T12 | Cross-system transfer of single-chain $T_{\text{acc}}$ to sharded | Measure the shard→destination leg on the two-zone IBC devnet; mark sharded $T_{\text{acc}}$ devnet-corroborated. |
| T13 | Cross-chain clock alignment at seconds scale | Anchor both chains to a shared L1 inclusion block / NTP-disciplined relayer observation with stated skew bounds. |
| T14 | No false-positive calibration | Mandatory negative (IBC) + positive (fast-exit) controls run end-to-end to known verdicts. |
| T15 | Stale `realsystems.py` | Regenerated from findings (§7). |
| T16 | 6×3 matrix infeasible for one RA | Cut to 1 safe + 1 open + 2 controls, single primary method per quantity; other systems documented-table only. |

---

## 7. Artifact engineering (preserves one-config, network-free reproduction)

**Invariant:** the reproduction path (`run_all.py → plot_figures.py → make_tables.py`) touches **no
network**, is seeded, one-config. All network collection is quarantined out of that path.

- **`shardbribe/estimate.py`** (NEW, pure stats, network-free): `clopper_pearson`, `wilson`,
  `rule_of_three`, `q_interval`, `fit_select` (Gamma/log-normal/empirical + GOF + Hill),
  `rho_summary`, `pwin_bca` (paired BCa), `power_pwin_zero`, `distance_to_cliff`,
  `apply_decision_rule` → frozen `Verdict` object. Validated against `testbed.measure_pwin` via
  `self_test()`.
- **`shardbribe/livemeasure.py`** (NEW, network-touching, **not imported by `run_all.py`**):
  adapters `cosmos_rpc`, `ibc_relayer`, `bridge_events`, `reorg_corpus`, `exploit_postmortem`, and
  the **chain-ID-gated** `equivocation_harness`. Emits the extended `testbed`-schema dict into
  `results/measured/<chain>.jsonl` with provenance + content hash.
- **`shardbribe/realsystems.py`** (CHANGE): add measured fields + `q_effective()` + a
  `slashing ∈ {full,none}` branch (so NEAR/MultiversX get `q='N/A'`); correct Zilliqa (de-sharded),
  Harmony/MultiversX (`window='gated'`). Emit documented **and** measured columns side by side.
- **`run_all.py`** (CHANGE): `rq8` block, if `results/measured/*.jsonl` present, calls
  `estimate.run(cfg)` and merges under `results['rq8']`; graceful no-op if absent (current behavior
  unchanged); stamp `prereg.hash` into `results/main.json`.
- **New figure** `fig_measured_race.pdf`: per path, paired $(T_{\text{settle}},T_{\text{acc}})$ ECDFs
  with measured $p_{\text{win}}$+CI, the $\rho{=}1$ line, the documented prediction as a hollow
  marker, both controls annotated (RULED_OUT / OPEN). **New table** `tab_measured.tex`:
  `System | sharded | slashing | n | q̂ (CI) | T_acc^lo/hi (med,P90) | T_settle (med,P90) |
  p_win (CI) | distance-to-cliff (s) | verdict`, NEAR/MultiversX firewalled.
- **Paper:** RQ7 stays "documented"; **RQ8** = "measured + pre-registered verdict". Limitation (3)
  rewritten from "we do not measure it on a live network" to the measured dual-verdict + distance-
  to-cliff statement. Promote the `experimental_setup.tex` live-measurement hook from "next step" to
  "executed in §RQ8".

---

## 8. Week-by-week plan (single RA, 4–8 weeks)

Critical path = passive Cosmos $q_{\max}$/$T_{\text{acc}}$ + bridge $T_{\text{settle}}$ + the two controls.

- **Week 0 (2–3 d):** confirm budget/disk for one `gaiad` archive node + one EVM archive RPC + paid
  indexer tier; verify devnet tooling (`in-place-testnet`, Hermes). **Freeze `prereg/rq8-v1`**
  (symbol↔timestamp map, estimators, $\varepsilon$, sample sizes, decision rule, admissible $V$
  paths). Draft + unit-test `estimate.py` on synthetic/testbed data only.
- **Week 1:** passive Cosmos arm (archive + indexer) → $q_{\max}$, $T_{\text{acc}}^{\text{report/applied}}$; stand up 4-node multi-region propagation listeners.
- **Week 2:** self-equivocation **private localnet** (two-nodes-one-key, chain-ID-gated, $N\ge40$)
  → $q_{\text{attack}}$, causal $T_{\text{acc}}$; build two-zone IBC devnet (negative control) → native $T_{\text{settle}}$ + quarantine latency.
- **Week 3:** bridge $T_{\text{settle}}$ — Across/deBridge event replay ($N\ge5\text{k}$ pairs) → user leg vs solver leg; reorg natural-experiment corpus; exploit-postmortem tail; UMA dispute-rate for $q_{\text{solver}}$.
- **Week 4:** fast-exit **positive control** devnet → low-$q$ + EXHIBIT calibration; shadow-fork reorg injection → $q_{\text{solver}}$; evidence-suppression experiment → $T_{\text{acc}}^{\text{hi}}$.
- **Week 5:** run `estimate.py` over all `*.jsonl`: fits, GOF, BCa, paired $p_{\text{win}}$, Holm-corrected decision rule, distance-to-cliff, both G2 gates; wire `run_all.py` rq8; regenerate figure+table.
- **Week 6:** cross-checks (fork slash latency vs historical; testnet→mainnet $\rho$ cancellation); correct `realsystems.py`; write RQ8 + rewrite Limitation (3) + abstract.
- **Week 7 (slack):** coordinated-disclosure dry-run (only if any OPEN on a deployed path); AEC packaging; ethics/IRB-exemption memo; deviations log.

**Minimum-viable fallback (if Weeks 3–4 slip):** ship the **passive Cosmos RULE-OUT** ($q_{\max}$+CI,
$T_{\text{acc}}$ floor+adversarial bound, native IBC $T_{\text{settle}}\ge T_{\text{acc}}$) **+ the
fast-bridge user-leg $T_{\text{settle}}$ from pure read-only event replay** ($N\ge5\text{k}$) **+ the
reorg natural-experiment** proving fills survive reversals. This alone yields one measured RULED-OUT
and one measured OPEN-WINDOW with the dual verdict and distance-to-cliff, using only read-only public
data and zero self-equivocation. The self-equivocation/shadow-fork arms are *enrichment* that harden
the RULE-OUT; if dropped, the RULE-OUT is reported against the cooperative-floor $T_{\text{acc}}$ with
that caveat stated, and downgrades to "ruled out against a non-suppressing adversary."

---

## 9. How this changes the paper's claims

**New contribution sentence (abstract):**

> We close the gap between model and reality by **measuring** the load-bearing quantities under a
> pre-registered protocol: on Cosmos Hub / CometBFT we measure $q$ (against the true evidence-expiry
> deadline, not unbonding), $T_{\text{acc}}$ (with a cooperative lower bound and an adversarial
> evidence-suppression upper bound), and $T_{\text{settle}}$, and the same instrument that returns a
> falsifiable RULED-OUT on finality-gated IBC settlement returns a measured OPEN-WINDOW
> ($T_{\text{settle}}\approx$ seconds $\ll T_{\text{acc}}$) on a real fast-intent-bridge value path —
> for which we re-derive the economic gate under solver-borne loss and isolate when the equivocation
> primitive is load-bearing versus a plain-reorg griefing distinct from prior bridge work; we further
> report, per deployed design, the exact settlement-speed cliff that would flip it from safe to exposed.

Net effect: (1) Limitation (3) discharged; (2) the safe-regime claim becomes an instrument-calibrated
equivalence certificate evaluated against the *adversarial upper-bound* $T_{\text{acc}}$; (3) the paper
now exhibits a real open window with the prior-art distinction settled; (4) every deployed system gains
an actionable distance-to-cliff.
