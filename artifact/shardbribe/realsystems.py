"""Case study: apply the model to documented parameters of real systems.

This module grounds the analysis in named, deployed sharded/BFT systems using
their *publicly documented* parameters (committee size, block/finality time,
unbonding period, cross-shard/bridge settlement style). It does NOT measure live
networks; the parameters are approximate public figures (confirm against current
specs before camera-ready). The point is to place real configurations on the
two gates of the model and report the verdict, rather than to claim any deployed
system is exploitable.

Key derived quantities per system:
  q_est          : Pr[evidence enforced before stake unslashable]. With unbonding
                   U of days/weeks and an evidence delay of minutes, q -> 1.
  breakeven_V    : (F+1) * q * (1 + R_frac), the break-even extractable value in
                   units of one validator's stake-at-risk (gate G2).
  window         : whether cross-shard/bridge settlement is finality-gated
                   ("gated" => p_win ~ 0, gate G1 closed) or can execute before
                   source accountability ("open"/"depends").
  verdict        : the regime the system sits in.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from .model import equivocation_floor


@dataclass
class SystemSpec:
    name: str
    sharded: bool
    committee_N: int            # committee / attestation-committee size (approx)
    block_s: float              # block/round time (s)
    finality_blocks: float      # blocks to finality
    unbonding_days: float       # unbonding / withdrawal delay
    evidence_delay_min: float   # time for equivocation evidence to be enforceable
    settlement: str             # cross-shard/bridge settlement style
    window: str                 # "gated" | "open" | "depends"
    note: str = ""

    @property
    def k(self) -> int:
        return equivocation_floor(self.committee_N)

    def q_est(self) -> float:
        # evidence delay (min) vs unbonding (days): q = 1 - exp(-U/evd)
        u_min = self.unbonding_days * 24 * 60
        if self.evidence_delay_min <= 0:
            return 1.0
        return 1.0 - math.exp(-u_min / self.evidence_delay_min)

    def breakeven_V_stakes(self, R_frac: float = 0.5) -> float:
        """Break-even V in units of one validator's stake-at-risk s."""
        return self.k * self.q_est() * (1.0 + R_frac)

    def verdict(self) -> str:
        if self.window == "gated":
            return "immune: finality-gated settlement (G1 closed)"
        # window open or depends: economics decides
        if self.q_est() > 0.99:
            return "G2 hard: long unbonding ($q\\!\\approx\\!1$)"
        return "potentially exposed: short slashability, open window"


def default_systems() -> list:
    """Approximate public parameters (as of 2026; confirm for camera-ready)."""
    return [
        SystemSpec(
            name="Harmony", sharded=True, committee_N=250, block_s=2.0,
            finality_blocks=1, unbonding_days=7.0, evidence_delay_min=1.0,
            settlement="async cross-shard receipts", window="open",
            note="receipt executes on destination after source finality"),
        SystemSpec(
            name="MultiversX", sharded=True, committee_N=400, block_s=6.0,
            finality_blocks=1, unbonding_days=10.0, evidence_delay_min=1.0,
            settlement="async cross-shard via metachain", window="depends",
            note="metachain notarizes shard blocks"),
        SystemSpec(
            name="Zilliqa", sharded=True, committee_N=600, block_s=40.0,
            finality_blocks=1, unbonding_days=14.0, evidence_delay_min=2.0,
            settlement="DS-epoch cross-shard", window="depends",
            note="pBFT shards + directory service"),
        SystemSpec(
            name="Cosmos Hub", sharded=False, committee_N=180, block_s=6.0,
            finality_blocks=1, unbonding_days=21.0, evidence_delay_min=1.0,
            settlement="IBC light-client (cross-chain)", window="gated",
            note="IBC verifies source finality before acting"),
        SystemSpec(
            name="Ethereum PoS", sharded=False, committee_N=128, block_s=12.0,
            finality_blocks=64, unbonding_days=1.1, evidence_delay_min=13.0,
            settlement="rollup/bridge dependent", window="depends",
            note="attestation committees; 2-epoch finality"),
        SystemSpec(
            name="Polkadot", sharded=True, committee_N=300, block_s=6.0,
            finality_blocks=1, unbonding_days=28.0, evidence_delay_min=1.0,
            settlement="XCMP via relay finality", window="gated",
            note="relay-chain GRANDPA finality gates messages"),
        SystemSpec(
            name="Fast-exit design (hypothetical)", sharded=True,
            committee_N=64, block_s=2.0, finality_blocks=1,
            unbonding_days=0.002, evidence_delay_min=10.0,
            settlement="ungated fast bridge", window="open",
            note="ILLUSTRATIVE non-deployed design: immediate post-epoch "
                 "withdrawal + ungated settlement; the danger quadrant"),
    ]


def analyze(systems=None, R_frac: float = 0.5) -> list:
    systems = systems or default_systems()
    rows = []
    for s in systems:
        rows.append({
            "name": s.name,
            "sharded": s.sharded,
            "N": s.committee_N,
            "k": s.k,
            "unbonding_days": s.unbonding_days,
            "q_est": s.q_est(),
            "breakeven_V_stakes": s.breakeven_V_stakes(R_frac),
            "window": s.window,
            "settlement": s.settlement,
            "verdict": s.verdict(),
            "note": s.note,
        })
    return rows
