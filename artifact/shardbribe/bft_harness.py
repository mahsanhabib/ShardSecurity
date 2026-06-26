"""An abstract HotStuff/Tendermint-style committee harness (local PoC).

This is a *safe, local-only* proof of concept.  It does not implement a real
networked consensus protocol; it implements the single round that matters for
this paper -- a commit vote over a value at a given (epoch, height, round) --
with real (toy) signatures, so that equivocation produces a genuine,
verifiable cryptographic evidence object of the same shape an accountable BFT
system would emit (cf. Casper/Tendermint duplicate-vote evidence).

Signatures are HMAC-SHA256 over a canonical encoding of the vote.  They are
*toy* in the sense that the "secret key" is a per-validator random seed and we
do not use a real signature scheme -- but the accountability semantics
(attributable, transferable, verifiable conflicting votes) are faithful, which
is all the attack needs.  No key here protects anything of value.
"""
from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass, field

from .model import F_of_N


def _canonical(epoch: int, height: int, rnd: int, value: str) -> bytes:
    return f"{epoch}|{height}|{rnd}|{value}".encode()


@dataclass(frozen=True)
class Vote:
    validator: int
    epoch: int
    height: int
    rnd: int
    value: str          # the block / state root the validator commits to
    sig: bytes

    def message(self) -> bytes:
        return _canonical(self.epoch, self.height, self.rnd, self.value)


@dataclass
class Validator:
    vid: int
    _sk: bytes                      # secret seed (local only; protects nothing)
    bonded: bool = True             # globally bonded & slashable?
    stake: float = 1.0

    def sign(self, epoch: int, height: int, rnd: int, value: str) -> Vote:
        msg = _canonical(epoch, height, rnd, value)
        sig = hmac.new(self._sk, msg, hashlib.sha256).digest()
        return Vote(self.vid, epoch, height, rnd, value, sig)

    def pubcheck(self, vote: Vote) -> bool:
        """Public verification (the harness knows each validator's seed; in a
        real system this is a signature check against a registered pubkey)."""
        expect = hmac.new(self._sk, vote.message(), hashlib.sha256).digest()
        return hmac.compare_digest(expect, vote.sig)


@dataclass
class EquivocationEvidence:
    """Two conflicting votes by the same validator at the same slot."""
    validator: int
    epoch: int
    height: int
    rnd: int
    vote_a: Vote
    vote_b: Vote

    def is_conflict(self) -> bool:
        return (self.vote_a.validator == self.vote_b.validator
                and (self.vote_a.epoch, self.vote_a.height, self.vote_a.rnd)
                == (self.vote_b.epoch, self.vote_b.height, self.vote_b.rnd)
                and self.vote_a.value != self.vote_b.value)


@dataclass
class Certificate:
    value: str
    votes: list = field(default_factory=list)

    @property
    def size(self) -> int:
        return len(self.votes)


class CommitteeHarness:
    """A single BFT committee of N = 3F+1 validators running one commit round."""

    def __init__(self, N: int, rng):
        self.N = N
        self.F = F_of_N(N)
        self.Q = 2 * self.F + 1
        self.validators = [
            Validator(vid=i, _sk=rng.bytes(16)) for i in range(N)
        ]

    # -- verification helpers ------------------------------------------------
    def verify(self, vote: Vote) -> bool:
        return self.validators[vote.validator].pubcheck(vote)

    def verify_evidence(self, ev: EquivocationEvidence) -> bool:
        """A fraud proof is valid iff both votes verify and they conflict."""
        return (ev.is_conflict()
                and self.verify(ev.vote_a)
                and self.verify(ev.vote_b))

    # -- the attack round ----------------------------------------------------
    def run_round(self, equivocators: list, phi: float, rng,
                  epoch: int = 0, height: int = 1, rnd: int = 0,
                  engineered_split: bool = False):
        """Drive one round in which ``equivocators`` sign both branches.

        Honest validators each commit to branch "A" or "B".  Two modes:

        * Random split (default): each honest validator commits to "A" with
          probability ``phi`` (network/leader-induced view divergence the
          adversary does not fully control).  This is the model behind
          ``model.psucc_closed_form``.
        * Engineered split (``engineered_split=True``): the adversary, by
          controlling the leader / inducing a partition, deterministically
          drives exactly the minimum honest split needed for both branches to
          reach quorum (the first ``Q - k`` honest validators to "A", the next
          ``Q - k`` to "B").  This realizes the *sufficient* condition with
          ``k = F+1`` and demonstrates the end-to-end attack succeeding.

        Returns the two certificates and the equivocation-evidence objects
        actually produced.
        """
        eq = set(equivocators)
        cert_a = Certificate(value="A")
        cert_b = Certificate(value="B")
        evidence = []
        honest_seen = 0
        need_per_branch = self.Q - len(eq)   # honest votes each branch needs

        for v in self.validators:
            if v.vid in eq:
                va = v.sign(epoch, height, rnd, "A")
                vb = v.sign(epoch, height, rnd, "B")
                cert_a.votes.append(va)
                cert_b.votes.append(vb)
                evidence.append(EquivocationEvidence(
                    v.vid, epoch, height, rnd, va, vb))
            else:
                if engineered_split:
                    # first need_per_branch honest -> A, next need_per_branch -> B
                    if honest_seen < need_per_branch:
                        branch = "A"
                    elif honest_seen < 2 * need_per_branch:
                        branch = "B"
                    else:
                        branch = "A"
                    honest_seen += 1
                else:
                    branch = "A" if rng.random() < phi else "B"
                vote = v.sign(epoch, height, rnd, branch)
                (cert_a if branch == "A" else cert_b).votes.append(vote)

        return cert_a, cert_b, evidence

    @staticmethod
    def conflicting_finality(cert_a: Certificate, cert_b: Certificate,
                             Q: int) -> bool:
        """Two conflicting certificates form iff both reach the quorum Q."""
        return cert_a.size >= Q and cert_b.size >= Q
