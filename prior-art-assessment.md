# Prior-Art / Novelty Assessment — Sub-Threshold Committee Bribery & the Accountability Race

_Generated 2026-06-22. Complements `deep-research-report.md` (which is a full critical review); this
document focuses narrowly on **prior art the paper does not currently cite** and on how each piece
bears on the paper's novelty claim._

## 1. What the paper claims as novel

The paper explicitly disclaims inventing bribery, smart-contract bribery, small-committee cheapness,
or cross-shard/bridge value extraction. Its novelty is the **composition** of five axes — and it
states (Table 1, "Positioning") that *no prior work occupies the intersection*:

- **A. Sub-threshold committee bribery** — adversary globally below the 1/3 network threshold buys, after
  committee reveal, the `F+1` validators that quorum intersection makes *necessary* in one `N=3F+1`
  committee (`F+1` necessary, not sufficient; honest-split folded into `p_succ`).
- **B. Bribe priced by accountability latency** — `b_i ≳ q(s_i+R_i)`, `q` = Pr[fraud proof enforced
  before stake unslashable]. Cost of corruption is *endogenous* to accountability latency.
- **C. The accountability race** — extract irreversible value `V` via cross-shard/bridge settlement in
  `T_settle` before detect→propagate→slash→revert in `T_acc`. Gates: `T_settle < T_acc` and `V > B + C_op`.
  `T_acc` is the "master variable."
- **D. Immunity by finality-gating** — gating cross-shard acceptance on finality forces `p_win = 0`.
- **E. Reconfiguration handoff** — epoch-boundary rotation/handoff relocates (not eliminates) the race;
  safe-handoff vs residual-vulnerability theorems.

## 2. Bottom line  _(revised after §9 verification — see §9R)_

- **The intersection survives.** Across ~140 verified works, **no work occupies the full A–E
  intersection**. The composition is defensible.
- **BUT two top-venue works are "high"-threat single-axis omissions and are now the most dangerous gaps:**
  (1) **Camael / "Realizing Corrupted-Shard Tolerance"** (CCS'25) occupies axis A's *sharded
  sub-threshold-compromise* setting almost exactly (a shard up to 2/3 corrupt while global stays <1/3),
  though as a *defense* it omits B/C/D; (2) **"Economic Censorship Games in Fraud Proofs"** (EC'25) is
  the closest published instance of your B–C core — **bribing to deplete a defender's accountability
  *time budget*** — though in an optimistic-rollup challenge-period setting with no committee/quorum
  structure (A), sharding, finality-gating (D), or reconfiguration (E). Both **must** be cited and
  sharply distinguished; their omission would read as missing the nearest neighbors.
- **But the perimeter is crowded, and several load-bearing ideas are anticipated in works the paper does
  not cite.** The economic gate (`V > B + C_op` ≈ cost-of-corruption > profit-from-corruption), the
  "accountability/slashing latency is the binding constraint" thesis, and "finality-gating caps attacker
  profit" all have strong, citable antecedents. Leaving them out is the single biggest prior-art risk:
  a reviewer in this area will know them.
- **The bribery citation lineage has gaps.** The paper cites McCorry/Winzer/Tran/Karakostas/Sooki-Tóth
  but omits the seminal Bonneau ("rent not buy"), the Judmayer "Pay-To-Win" line, the P+ε ancestor, and
  the out-of-band-collusion contract paper. For a bribery paper these are expected.
- **Two relevant works are already in your `Related Paper/` folder but missing from `reference.bib`:**
  **Free2Shard** (2005.09610) and the cited Karakostas (2402.06352, this one *is* in the bib).

## 3. Priority tier — closest neighbors (cite AND distinguish; "medium" threat)

These hit the paper's *load-bearing* ideas. Each must be cited with an explicit "we differ because…".

| # | Work | Venue / ID | Hits axes | What it anticipates | What the paper still adds |
|---|------|-----------|-----------|---------------------|---------------------------|
| 1 | **STAKESURE: PoS Mechanisms with Strong Cryptoeconomic Safety** — Deb, Raynor, Kannan | arXiv:2401.05797 (2024) | econ-gate (B/C framing), D | Separates cost-of-corruption vs profit-from-corruption (its Eq.1 ≈ your `V > B+C_op`); bounds profit by bridge/CEX value extractable within a **reversion period** `T_rev`; "secure confirmation rule" + "provably safe bridging" cap profit by gating value release on finality. | No sharding/committee structure (A); bribe not priced by slashing **latency** `q` (B); assumes ~immediate slashing, so no `T_settle<T_acc` race (C); no reconfiguration (E). |
| 2 | **The Economic Limits of Permissionless Consensus** — Budish, Lewis-Pye, Roughgarden | EC'24, arXiv:2405.09173 | C (foundation) | Formalizes EAAC; proves under partial synchrony, adversary ≥1/3 ⇒ no protocol is EAAC because the violator "can sell off resources and avoid punishment in the meantime" — the abstract impossibility behind "`T_acc` is the master variable." Reasons explicitly about double-spend / short-position off-chain gains. | Adversary **owns** stake (no bribery mechanism, no `b_i≳q(s+R)`); monolithic (no committees/sharding, A); abstract impossibility, not a concrete cross-shard settlement race (C); no D/E. **The single most important must-cite.** Cite its precursor too: Budish, "The Economic Limits of Bitcoin and the Blockchain," NBER WP 24717 (2018) / QJE 2024. |
| 3 | **Bitcoin-Enhanced PoS Security ("Babylon")** — Tas, Tse, Gai, Kannan, Maddah-Ali, Yu | IEEE S&P'23, arXiv:2207.08392 | C, D | Makes the **unbonding/withdrawal delay** the operative security variable; frames the race as "slash before the validator withdraws"; Bitcoin-checkpoint finality-gating to upgrade accountable→slashable safety (reduces unbonding from ~21 days to <5h). | Needs a **supermajority** using already-withdrawn keys (posterior corruption), not a sub-threshold committee bribe (A); no per-validator bribe equilibrium (B); its race is slash-before-withdrawal, not monetize-cross-shard-settlement-before-revert (C); single-chain (E). |
| 4 | **CoBRA: Universal Strategyproof Confirmation for Quorum PoS** — Avarikioti, Kokoris-Kogias, Neiheiser, Stefo | arXiv:2503.16783 (2025) | C (econ-gate), D | "Stake-bounded finalization rule" caps value finalized per synchrony window below total slashable stake (`V ≤ B`) so a rational validator's double-spend gain can't exceed its bond — independently arrives at your "value vs bond" reasoning; finality gadget removes forking profit. | No briber / no bribe pricing at all (B); global static fraction, not post-reveal committee-local buying (A); throttles throughput rather than modeling irreversible cross-shard/bridge extraction in a timing race (C); E deferred. |

## 4. Bribery lineage — expected citations currently missing

| Work | Venue / ID | Note | Threat |
|------|-----------|------|--------|
| **Why Buy When You Can Rent? Bribery Attacks on Bitcoin-Style Consensus** — Bonneau | FC'16, LNCS 9604 | Seminal: transient/**rented** majority has no long-term stake to protect ⇒ corruption is cheap. Acknowledged ancestor of the entire bribery line you cite. | medium |
| **Breaking Blockchain Rationality with Out-of-Band Collusion** — Zhang, Bastankhah, Merino, Estrada-Galiñanes, Ford | FC'23 WTSC, arXiv:2305.00554 | Generic out-of-band bribery contract that makes defection the strict Nash equilibrium for a sub-threshold coalition; §5.3 even gestures at evading slashing by censoring the proof. Closest "bribery-contract flips rational nodes" reference. | medium |
| **Pay To Win: Cheap, Crowdfundable, Cross-chain Algorithmic Incentive Manipulation Attacks** — Judmayer, Stifter, Zamyatin, Tsabary, Eyal, Gaži, Meiklejohn, Weippl | FC'21 WTSC, ePrint 2019/775 | Trustless, crowdfundable, **cross-chain** bribery funding double-spends ~10× cheaper than "whale" bribes; pays collaborators even on failure. | medium |
| **SoK: Algorithmic Incentive Manipulation Attacks on Permissionless PoW** — Judmayer et al. | FC'21, ePrint 2020/1614 | The systematization of bribery/incentive-manipulation. A bribery paper omitting the field's SoK is conspicuous. | medium |
| **Commitment Attacks on Ethereum's Reward Mechanism** — Sarenche, Tas, Monnot, Schwarz-Schilling, Preneel | arXiv:2407.19479 (2024) | Bribery via **credible commitments** (burn collateral > inclusion reward) coerces prior-slot attesters into conflicting blocks → reorgs. Modern conditional-bribery mechanism. | medium |
| **BriDe Arbitrager** — Yang, Li, Zhang, Asheralieva, Wei, Goh | arXiv:2407.08537 (2024) | *Implemented* sub-threshold (<1/4) validator bribery for MEV; explicitly "triggers no slashing." Best **contrast** baseline: monetizes a window by *avoiding* slashing rather than *racing* it. | medium |
| **Decentralization Cheapens Corruptive Majority Attacks** — Newman | AFT'23, arXiv:2310.01546 | Equilibrium per-validator bribe falls far below the naive Budish bound via low pivotality + externalized cost — supports your "F+1 necessary-not-sufficient" + sub-stake bribe. | medium |
| **The P + ε Attack** — Buterin | EF blog, 2015 | Canonical conditional-bribery primitive (pay-only-if-you-lose ⇒ near-zero realized cost). Conceptual ancestor of "cost of corruption ≪ stake." | low |
| **Rationality is Self-Defeating in Permissionless Systems** — Ford, Böhme | arXiv:1910.08820 (2019) | Argues external value dominates in-protocol penalty ⇒ rational-security assumptions self-defeating. Motivates treating `V` as external/unbounded. | low |
| **The Cryptoeconomics of Slashing** — Kannan, Deb (a16z, 2023) | a16z research | Slashing raises cost-of-corruption to ~`(N/3)·S` (static magnitude, no latency). Background for B. | low |
| **Discouragement Attacks** — Buterin (2018) | ETH Research | Griefing-factor framework; two-step "drive out validators then cheap 51%." Background for B. | low |

## 5. Accountability / slashable-safety foundations (the substrate `T_acc` abstracts)

| Work | Venue / ID | Note | Threat |
|------|-----------|------|--------|
| **BFT Protocol Forensics** — Sheng, Wang, Nayak, Kannan, Viswanath | CCS'21, arXiv:2010.06785 | Per-protocol forensic support `(m,k,d)`: exactly how many of the `F+1` equivocators are *provably* catchable. Sharpens your `q` and the feasibility of D. | medium |
| **Polygraph: Accountable Byzantine Agreement** — Civit, Gilbert, Gramoli | ICDCS'21, ePrint 2019/587 | First accountable BA: on a fork, identify ≥ n/3 culprits via certificates. The detection primitive your slashing presumes. | medium |
| **The Availability-Accountability Dilemma & Accountability Gadgets** — Neu, Tas, Tse | FC'22, arXiv:2105.06075 | Theoretical basis for finality-gating (accountably-finalized prefix `LOG_acc`). Underpins your D / `p_win=0`. | medium |
| **Recover from Excessive Faults in PS BFT SMR** — Gong, Camilo, Nayak, Lewis-Pye, Kate | USENIX Sec'25, ePrint 2025/083 | State-of-the-art deterministic detect-then-recover/revert (complete+sound culprit detection up to n−2) — the machinery whose *latency* you abstract as `T_acc`. Shows `T_acc` is not a free scalar. | medium |
| **Proof of Diligence: Cryptoeconomic Security for Rollups** — Sheng, Rana, Bala, Tyagi, Viswanath | AFT'24, arXiv:2402.07241 | Rational **watchtowers** race verification/finality against the rollup withdrawal/challenge window — punishment-vs-settlement latency, structurally your race in the rollup setting. | low–med |
| **Accountable Safety Implies Finality** — Neu, Tas, Tse (2023) | short paper | Formal backbone for "finality-gating ⇒ conflicting commits impossible below threshold" (D). | low |
| **Accountable Liveness** — Lewis-Pye, Neu, Roughgarden, Zanolini, Tas et al. (2025) | — | Extends accountability from safety to liveness; bounds what/how-fast fraud proofs attribute (the `T_acc` side). | low |

## 6. Restaking / shared-security economics (the economic gate, adjacent literature)

| Work | Venue / ID | Note | Threat |
|------|-----------|------|--------|
| **Robust Restaking Networks** — Durvasula, Roughgarden | ITCS'25, arXiv:2407.21785 | Overcollateralization / robust-security condition `(1+γ)·π ≤ σ` parallels your economic gate; one stake underwriting many services ≈ "same stake vs many settlements." | medium |
| **Economic Security of Multiple Shared Security Protocols** — Nag, Bodani, Kumar | arXiv:2505.03843 (2025) | Weakest-SSP min attack cost `θ·min Δ_j`; §4 bribery condition endogenous to **slashing magnitude** (not latency); "globally secure but locally lethal" flavor adjacent to A. | medium |
| **The Cost of Secure Restaking vs. Proof-of-Stake** — Mamageishvili, Sudakov (2025) | — | How much stake a configuration needs to keep CoC large; shared/overlapping stake cheap at the weakest point. | low |

## 7. Sharding security, cross-shard & reconfiguration (axes A / E *setting*)

| Work | Venue / ID | Note | Threat |
|------|-----------|------|--------|
| **Free2Shard** — Rana, Kannan, Tse, Viswanath | SIGMETRICS/POMACS'22, arXiv:2005.09610 | Sub-network-threshold **adaptive** adversary concentrates corruption to capture one shard; defense = honest self-reallocation. Canonical A-setting reference. **Already in your `Related Paper/` folder but not in the bib.** | medium |
| **Divide & Scale: Formalization … / Roadmap to Robust Sharding** — Avarikioti, Desjardins, Kokoris-Kogias, Wattenhofer | arXiv:1910.10434 | Canonical formal sharding model; fully-adaptive ⇒ can't scale, epoch-adaptive ⇒ scales with succinct epoch-boundary proofs (E setting). | low |
| **SoK: Public Blockchain Sharding** — Al Barat, Li, Du, Hou, Lou | IEEE ICBC'24, arXiv:2405.20521 | Recent sharding-security SoK: cross-shard tx taxonomy + committee reconfiguration. Good background/threat-landscape cite. | low |
| **Optimal Sharding / "Arete"** — Zhang, Luo, Ramesh, Kate | PVLDB'25, arXiv:2406.08252 | Deconstructed SMR; consensusless processing shards tolerate <1/2; epoch reconfiguration for adaptive resistance + liveness recovery. | low |
| **Front-running in Sharded Blockchains / "Haechi"** — Zhang, Chen, Luo, Gong, Hong, Kate | NDSS'24, arXiv:2306.06299 | Cross-shard execution-**ordering** attack + fair-ordering defense. Contrast attack class (ordering vs safety/accountability). | low |
| **Cross-shard leader accountability (CSLAP)** — Du, Zhang, Liu, Fu | Nature Sci. Rep. 14:14953 (2024) | Cross-shard 2PC + leader-accountability with explicit detection latency; closest "sharding + cross-shard + accountability + latency" published title. | low |
| **ZLB: A Blockchain Tolerating Colluding Majorities** — Ranchal-Pedrosa, Gramoli | DSN'24 (Best Paper), arXiv:2305.02498 | Detect-exclude-recover beyond n/3; "zero-loss" reimbursement is the *opposite* of your irreversible-extraction premise — sharp contrast point. | low |
| **Better Safe than Sorry: Recovering after Adversarial Majority** — Sridhar, Zindros, Tse | arXiv:2310.06338 (2023); successor "Consensus Under Adversary Majority Done Right," FC'25 | Safety-first recovery gadget; prevents the violation your race exploits. Contrast. | low |
| **Stake-Bleeding Attacks on PoS** — Gaži, Kiayias, Russell (2018) | — | Long-range/posterior corruption: old keys = unslashable stake = the endpoint of your `q`-term and E residual-vulnerability. | low |
| **Halting the Solana Blockchain with ε Stake** — Kniep, Sliwinski, Wattenhofer (2024) | — | Sub-threshold leader equivocates so honest stake splits below switch threshold — mirrors "F+1 necessary + honest-split `p_succ`" in spirit. | low |

## 8. Bridge / reorg / settlement-timing (axes C / D)

| Work | Venue / ID | Note | Threat |
|------|-----------|------|--------|
| **Defending Against Malicious Reorgs in Tezos PoS** — Neuder, Moroz, Rao, Parkes (2020) | — | Quantifies reorg feasibility → double-spend window; protocol-parameter defenses shrink it. C premise. | low |
| **Goldfish: No More Attacks on Ethereum?!** — D'Amato, Neu, Tas, Tse (2024) | — | Reorg-resilient fork choice; removes deviation surface by construction (analogue of D). | low |
| **Trustless Bridges via Random Sampling Light Clients** — Bhatt, Shirazi, Stewart (2025) | — | Cross-chain acceptance gated on source-chain BFT/finality — D in the bridge setting. | low |
| **Exploiting Liquidity-Exhaustion in Intent-Based Cross-Chain Bridges** — Augusto, Torres, Vasconcelos, Correia (2026) | — | Value fronted before settlement finalizes — same act-before-settlement gap as C, in intent bridges. | low |
| **Unaligned Incentives: Pricing Attacks Against Rollups** — Chaliasos, Swann, Pilehchiha, Mohnblatt, Livshits, Kattis | arXiv:2509.17126 (2025) | Concurrent: treats **finality-delay as an economic attack surface** (griefing/DoS via TFM mispricing, not bribery). One-line cite-and-distinguish to preempt "concurrent work." | low |

## 9R. §9 leads — RESOLVED (verified 2026-06-22)

All confirmed real. Two are "high"-threat (top-venue nearest neighbors); the rest are medium/low/none.

| Work | Venue / ID | Axes | Threat | Why it matters / how to distinguish |
|------|-----------|------|--------|-------------------------------------|
| **Realizing Corrupted-Shard Tolerance ("Camael")** — Liu, Liu, Pan, Hu, Lu et al. | **CCS'25**, DOI 10.1145/3719027.3765132 | A, E | **HIGH** | Tolerates a shard up to **2/3 corrupt** while global = 1/3; detect (snapshot/conviction) → replace nodes → reconfigure. *Your exact sub-threshold-single-shard setting, in sharding, at CCS.* Distinguish: it's a **defense** with no bribe pricing (B), no cross-shard value-extraction race (C), no finality-gating (D); its snapshot/conviction latency **is itself an instance of `T_acc`**. |
| **Economic Censorship Games in Fraud Proofs** — Berger, Felten, Mamageishvili, Sudakov | **EC'25**, arXiv:2502.20334 | B, C | **HIGH** | Bribe proposers to censor a defender's challenge txns and **deplete the challenge-period time budget**; bounds the attacker/defender budget ratio that decides who wins the race. *Closest published instance of "bribe to beat the accountability window."* Distinguish: L1→L2 single-defender censorship, **no** `N=3F+1` quorum/`F+1`/`p_succ` (A), bribe not priced by `q(s+R)` (B's formula), no cross-shard `V`/finality-gating (D)/reconfig (E). **Engage this directly.** |
| **Bitcoin Staking / "Remote Staking with Optimal Economic Safety"** — Dong, Litos, Tas, Tse, Woll, Yang, Yu | arXiv:2408.01896 (≠ Babylon 2207.08392) | B, C, E | medium | The **"remote unbonding protocol" = slash-before-unbond race** = your `T_acc` vs withdrawal; ≥1/3-slash guarantee. Primary baseline for "slash before stake becomes unslashable." Distinguish: proves *sufficiency* of slashing for a 1/3 adversary; no sub-threshold bribe pricing, no cross-shard `V` race, no finality-gating. |
| **Hollow Victory: Malicious Proposers Exploit Validator Incentives in OR Dispute Games** — Suhyeon Lee | WTSC'25, arXiv:2504.05094 | B, C | medium | Winning a fraud challenge may be **unprofitable** ⇒ accountability fails to deter — directly your `q` / enforcement-may-not-pay intuition. Distinguish: single OR proposer vs validators, no committee/sharding/cross-shard race. |
| **Aegis: Tethering a Blockchain with Primary-Chain Stake** — Bar-On, Bar-Zur, Ben-Porat, Cohen, Eyal, Sitbon | **CCS'25**, arXiv:2406.05904 | C, E | low | "Correct **until withdrawal**" collateral + **committee resets**/checkpoints — adjacent to your withdrawal-timing (C) and reconfiguration (E). No bribery/finality-gating. |
| **GearBox: Optimal-size Shard Committees** — David, Magri, Matt, Nielsen, Tschudi | CCS'22, ePrint 2021/211 | A, E | low | Canonical committee-size-vs-security via safety/liveness split. **Useful framing: GearBox-style small committees *amplify* your axis-A bribery threat.** No economics/accountability. |
| **Three Attacks on Proof-of-Stake Ethereum** — Schwarz-Schilling, Neu, Monnot, Asgaonkar, Tas, Tse | FC'22, arXiv:2110.10086 | A, C | low | Reorg-for-profit + balancing/finality-delay with tiny stake. Background for reorg-for-value (C) and why finality-gating matters (D-contrast). Single-chain, owned stake — opposite mechanism. |
| **Quantifying Blockchain Extractable Value** — Qin, Zhou, Gervais | IEEE S&P'22, arXiv:2101.05511 | C | low | Empirical MEV magnitudes (~$540M); anchor for bounding `V`. Also: MEV incentivizes rational forking. |
| **SoK: Cross-Domain MEV** — McMenamin | arXiv:2308.04159 | C, D | low | Best cross-domain framing for situating cross-shard `V`; intrinsic vs time-extractable value. |
| **Divide and Scale** — Avarikioti, Desjardins, Kokoris-Kogias, Wattenhofer | SIROCCO'23, arXiv:1910.10434 | A, E | low | (re-confirmed) epoch-adaptive adversary justifies *why* reconfiguration is needed (E); committee-size bounds (A). |
| **Foundations of TFM Design** — Chung, Shi | SODA'23, arXiv:2111.03151 | B | low | Side-contract-/collusion-proofness impossibility — proposer-user side contracts are a fundamental limit (B background). |
| **Transaction Fee Mechanism Design** — Roughgarden | EC'21, arXiv:2106.01340 | B | low | OCA-proofness (off-chain proposer-user collusion) vocabulary (B background). |
| **Byzantine Attacks Exploiting Penalties in Ethereum PoS** — Pavloff, Amoussou-Genou, Tucci-Piergiovanni | DSN'24, arXiv:2404.16363 | A | low | Penalty/slashing mechanism can *backfire* past 1/3. Optional background. |
| **Sharding-Based PoS Blockchain Protocols** — Hafid, Hafid, Makrakis | Sensors'23, arXiv:2108.05835 | A | low | Classic committee-takeover ("1% attack") probability via hypergeometric sampling — the static-fraction baseline you contrast against. |
| **Double-Spending Attacks in Cross-Blockchain Ecosystems** — Mukherjee, Olivieri, Chaki, Cortesi | BCRA'25, DOI 10.1016/j.bcra.2025.100378 | C | low | Cross-**chain** (not cross-shard) double-spend survey; only 3 forms remain feasible. Contrast threat model. |
| **Disincentivizing Double Spend Across Interoperable Blockchains** — Sai, Tipper | IEEE TPS-ISA'19 | C | low | "Observer" defense for cross-chain DS (basis of the Mukherjee survey). |
| **SoK: Evolution of MEV (Miners→Cross-Chain)** — Mancino, Sevim | arXiv:2603.07716 (2026) | C | low | Very recent cross-chain-MEV survey; optional landscape cite. |
| **SpiralShard** (Lin, Li, Zhang, ToN'25, arXiv:2407.08651); **DynaShard** (Liu et al., arXiv:2411.06895) | — | — | none | Scalability/performance sharding designs; no economics/accountability. Optional "recent design" cites. |
| **Majority is Not Required (sub-majority private double-spend)** — Georghiades et al. | arXiv:2312.07709 | — | none | PoW sub-50% reorg double-spend; different "sub-threshold" meaning. Ignore unless contrasting terminology. |

Also confirmed earlier: **NEAR blog "How Unrealistic is Bribing Frequently Rotated Validators?"** (Skidanov, 2020) — informal but argues rotation does not stop bribery (A/E spirit); cite if a non-academic source is acceptable.

_Net change to the verdict: the full A–E intersection is still unoccupied, but the "no high-threat work"
finding is **revised** — Camael (CCS'25, axis A) and Economic Censorship Games (EC'25, axes B–C) are
high-threat single-axis neighbors that must be cited and distinguished._

## 10. Recommended actions

1. **Add §3 (STAKESURE, ELPC+Budish'18, Babylon, CoBRA) to Related Work and the positioning table** with
   an explicit row each — these are the works a reviewer is most likely to raise. The honest framing:
   "prior work establishes the cost-vs-profit gate, the latency-bounded limit of accountability, and
   finality-gating-caps-profit in *monolithic/single-chain/restaking* settings; we are the first to
   instantiate them as **committee-local sub-threshold bribery in sharded BFT with a cross-shard
   settlement-vs-slashing race**."
2. **Round out the bribery lineage** (§4): Bonneau, Judmayer ×2, out-of-band collusion, P+ε, commitment
   attacks, BriDe (as contrast). Cheap to add, closes an obvious gap.
3. **Cite the accountability substrate** (§5: BFT Forensics, Polygraph, Accountability Gadgets, Gong'25)
   when you introduce `T_acc` — these show `T_acc` is a real, non-trivial quantity, not an assumption.
4. **Add Free2Shard + Divide & Scale** to the sharding background (you already have Free2Shard's PDF).
5. **Verify the §9 leads** (esp. "Three Attacks on PoS Ethereum", "Realizing Corrupted-Shard Tolerance",
   the cross-shard double-spend titles, and the NEAR rotation-bribery post) before final submission.

_Method note: 12 parallel literature-angle finders → 116 hits / 70 unique → adversarial verification of
high/medium-closeness candidates. No verified work occupied the full A–E intersection or scored "high"
threat; ~32 verifications were truncated by a session rate limit (see §9)._
