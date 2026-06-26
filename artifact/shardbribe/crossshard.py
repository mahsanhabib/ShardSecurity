"""Cross-shard receipt generation and delayed accountability processing.

This module models the *object* the accountability race is run over: a
value-bearing cross-shard receipt emitted by a (possibly fraudulent) source
certificate, and a destination/withdrawal pipeline that either settles the
value or is interdicted by an accountability event (equivocation evidence ->
slash -> revert/quarantine).

It also implements the central design knob of the paper: whether receipt
execution is *accountability-gated*.  A gated receipt cannot become executable
until the source shard is past its accountability window, which forces
Tsettle >= Tacc and (per the immunity proposition) pwin = 0.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Receipt:
    """A cross-shard receipt predicated on a source-shard certificate."""
    source_epoch: int
    source_height: int
    value: float
    source_value_root: str      # which branch ("A"/"B") it certifies
    gated: bool = False         # accountability-gated execution?


@dataclass
class RaceOutcome:
    settled: bool               # did value clear before accountability?
    t_settle: float
    t_acc: float
    slashed: bool               # were equivocators slashed (evidence enforced)?
    retained_value: float       # value the adversary keeps


def run_settlement(receipt: Receipt, t_settle: float, t_acc: float,
                   accountability_window: float = 0.0) -> RaceOutcome:
    """Resolve one receipt against the accountability race.

    Semantics:
      * If the receipt is accountability-gated, its earliest execution time is
        pushed to ``max(t_settle, accountability_window)``; with the gate set
        so that accountability_window >= t_acc this makes settlement never beat
        accountability (pwin = 0).
      * Otherwise the value settles iff ``t_settle < t_acc``.
      * Evidence is always enforced eventually (slashed = True): the bribed
        validators are punished regardless; the only question is whether the
        adversary already cashed out.
    """
    effective_settle = t_settle
    if receipt.gated:
        effective_settle = max(t_settle, accountability_window)
    settled = effective_settle < t_acc
    return RaceOutcome(
        settled=settled,
        t_settle=effective_settle,
        t_acc=t_acc,
        slashed=True,
        retained_value=receipt.value if settled else 0.0,
    )
