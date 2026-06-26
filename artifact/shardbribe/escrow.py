"""A model PayToEquivocate escrow (local logic, never networked).

This is the local Python analogue of the illustrative on-chain contract in the
paper (Listing: PayToEquivocate).  It releases a per-validator bribe *only* on
submission of a valid equivocation proof by a registered validator.  It is a
model of the trustless-bribery mechanism, not deployable tooling: there is no
networking, no real currency, and no operational hardening.  Its purpose is to
make the "trustless" claim concrete and testable -- the escrow pays iff the
harness's ``verify_evidence`` accepts the proof.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .bft_harness import CommitteeHarness, EquivocationEvidence


@dataclass
class PayToEquivocate:
    """Local escrow: funds B, pays bribe_per on each distinct valid proof."""
    harness: CommitteeHarness
    bribe_per: float
    escrow: float
    registered: set = field(default_factory=set)
    paid: set = field(default_factory=set)
    payouts: list = field(default_factory=list)

    @classmethod
    def fund(cls, harness: CommitteeHarness, k: int, bribe_per: float):
        return cls(harness=harness, bribe_per=bribe_per,
                   escrow=k * bribe_per)

    def register(self, vid: int) -> None:
        self.registered.add(vid)

    def claim(self, ev: EquivocationEvidence) -> bool:
        """Release the bribe iff: registered, not already paid, the proof is a
        valid equivocation under the committee's verifier, and funds remain."""
        v = ev.validator
        if v not in self.registered or v in self.paid:
            return False
        if not self.harness.verify_evidence(ev):
            return False
        if self.escrow < self.bribe_per:
            return False
        self.paid.add(v)
        self.escrow -= self.bribe_per
        self.payouts.append((v, self.bribe_per))
        return True

    @property
    def total_paid(self) -> float:
        return sum(p for _, p in self.payouts)
