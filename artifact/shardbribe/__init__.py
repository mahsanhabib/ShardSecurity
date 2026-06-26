"""shardbribe: a local, safe simulation/analysis library for the paper

    "Priced to Equivocate: Sub-Threshold Committee Bribery and the
     Accountability Race in Sharded Blockchains."

The package is intentionally self-contained and depends only on the Python
standard library plus numpy (the plotting/driver layer additionally uses
matplotlib and pyyaml). It contains:

  model      -- closed-form analytical model: equivocation floor, success
                probability psucc, bribe cost, the accountability race pwin,
                expected profit, and the two viability gates.
  quorum     -- Monte-Carlo BFT committee/quorum simulator that empirically
                reproduces the analytical psucc, validating the model.
  bft_harness-- an abstract HotStuff/Tendermint-style committee harness with
                real (toy) signatures that *produces* equivocation evidence.
  escrow     -- a model PayToEquivocate escrow that releases a bribe only on a
                valid equivocation proof (local logic, never networked).
  crossshard -- cross-shard receipt generation and delayed accountability
                processing; the object the race is run over.
  race       -- Monte-Carlo accountability-race simulator (Tsettle vs Tacc).
  reconfig   -- epoch-boundary state/receipt handoff model and the per-design
                expected profit E[Pi(a)] across the epoch.

NOTHING in this package contacts a network. All randomness is seeded for
reproducibility.
"""

__all__ = [
    "model",
    "quorum",
    "bft_harness",
    "escrow",
    "crossshard",
    "race",
    "reconfig",
]

__version__ = "1.0.0"
