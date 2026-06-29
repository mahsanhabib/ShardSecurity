"""Offline tests for the N4 COMMITTEE-FORK arm (no live localnet).

Exercise the pure pieces of the committee backend, which prove the attack's
necessary-and-sufficient condition realized on real client code:

  * parse_commit_signers     -- extract the flag-2 (committed) signer set + block-id +
    (height, round) from a CometBFT /commit, excluding absent/nil signers.
  * parse_committee_fork      -- combine the two partitions' conflicting commits into a
    structural fork: F+1 distinct equivocators (quorum-intersection floor, Lemma 1) +
    the honest split, only when the certs genuinely conflict at one (H, round).
  * assemble_committee_record -- fold one fork + the real slashes into a MeasuredRecord
    (committee_size, n_equivocators, n_slashed, T_acc) that round-trips to JSON.

Load-bearing invariants (N=4, F=1, Q=3, floor k=F+1=2):
  - HAPPY: certs conflict at the same (H, r0); intersection = {e1,e2} (2 distinct
    equivocators); honest split h1|h2; both slashed => quorum_intersection_ok, n_slashed=2.
  - NEGATIVES that must FAIL the floor: identical block-ids (no conflict); different
    rounds (not a duplicate vote); only 1 shared signer (< F+1).
  - The equivocation backend is hard-gated to the localnet allowlist.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shardbribe.livemeasure import (                       # noqa: E402
    parse_commit_signers, parse_committee_fork, assemble_committee_record,
    committee_harness, MeasuredRecord)

_passed = []


def check(name, cond):
    assert cond, f"FAILED: {name}"
    _passed.append(name)
    print("ok ", name)


# --- synthetic /commit responses --------------------------------------------
def _sig(addr, flag, ts="2026-06-29T00:00:01.100000000Z"):
    return {"block_id_flag": flag, "validator_address": addr,
            "timestamp": ts, "signature": "deadbeef"}


def _commit(height, rnd, block_id, commit_signers, *, nil=(), absent=(), ts_base=1.1):
    """A CometBFT /commit?height response. ``commit_signers`` sign THIS block (flag 2);
    ``nil`` are flag-3, ``absent`` flag-1 (must be excluded from the cert)."""
    sigs = []
    for i, a in enumerate(commit_signers):
        sigs.append(_sig(a, 2, ts=f"2026-06-29T00:00:0{int(ts_base)}.{100000000 + i:09d}Z"))
    sigs += [_sig(a, 3) for a in nil]
    sigs += [_sig(a, 1) for a in absent]
    return {"result": {"signed_header": {
        "header": {"height": str(height)},
        "commit": {"height": str(height), "round": rnd,
                   "block_id": {"hash": block_id}, "signatures": sigs}}}}


# partition A committed block AAAA at (H=163, r0) with {e1,e2,h1};
# partition B committed block BBBB at the same (H=163, r0) with {e1,e2,h2}.
E1, E2, H1, H2 = "E1ADDR", "E2ADDR", "H1ADDR", "H2ADDR"
COMMIT_A = _commit(163, 0, "AAAA", [E1, E2, H1], absent=[H2])
COMMIT_B = _commit(163, 0, "BBBB", [E1, E2, H2], absent=[H1])


def test_parse_commit_signers():
    a = parse_commit_signers(COMMIT_A)
    check("signers_flag2_only", a["signers"] == {E1, E2, H1})       # H2 absent excluded
    check("block_id", a["block_id"] == "AAAA")
    check("height", a["height"] == 163)
    check("round", a["round"] == 0)
    check("timestamps_present", set(a["signer_timestamps"]) == {E1, E2, H1})


def test_fork_happy():
    f = parse_committee_fork(COMMIT_A, COMMIT_B, F=1)
    check("equivocators_are_the_intersection", f["equivocators"] == {E1, E2})
    check("two_distinct_equivocators", f["n_equivocators"] == 2)    # the F+1 floor, distinct
    check("honest_split_a", f["honest_a"] == {H1})
    check("honest_split_b", f["honest_b"] == {H2})
    check("n_honest_split", f["n_honest_split"] == 2)
    check("certs_conflict", f["conflicting_certs"] is True)         # AAAA != BBBB
    check("same_height", f["same_height"] is True)
    check("same_round", f["same_round"] is True)
    check("quorum_a_is_Q", f["quorum_a"] == 3)                      # Q = 2F+1
    check("quorum_b_is_Q", f["quorum_b"] == 3)
    check("quorum_intersection_ok", f["quorum_intersection_ok"] is True)


def test_record_happy():
    f = parse_committee_fork(COMMIT_A, COMMIT_B, F=1)
    rec = assemble_committee_record(
        f, t_fork_ms=1000.0,
        slashed=[{"validator_address": E1, "t_slash_ms": 2300.0},
                 {"validator_address": E2, "t_slash_ms": 2450.0}],
        N=4, src_chain="shardbribe-localnet-1", measurement_resolution_ms=1000.0)
    check("rec_committee_size", rec.committee_size == 4)
    check("rec_quorum_size", rec.quorum_size == 3)
    check("rec_n_equivocators", rec.n_equivocators == 2)
    check("rec_n_honest_split", rec.n_honest_split == 2)
    check("rec_quorum_intersection_ok", rec.quorum_intersection_ok is True)
    check("rec_conflicting_certs", rec.conflicting_certs is True)
    check("rec_both_slashed", rec.n_slashed == 2)
    # T_acc measured to when the LAST equivocator is caught (2450 - 1000)
    check("rec_T_acc_to_last_slash", rec.T_acc == 1450.0)
    check("rec_fork_formed", rec.fork_formed is True)
    check("rec_tacc_bound_lo", rec.tacc_bound == "lo")             # cooperative slash
    # round-trips to JSON with the new fields
    d = json.loads(json.dumps(rec.to_dict()))
    check("rec_json_roundtrip", d["n_equivocators"] == 2 and d["committee_size"] == 4)


def test_partial_slash():
    """Only e1 caught: n_slashed=1, T_acc still set from the one slash time."""
    f = parse_committee_fork(COMMIT_A, COMMIT_B, F=1)
    rec = assemble_committee_record(
        f, t_fork_ms=1000.0,
        slashed=[{"validator_address": E1, "t_slash_ms": 2300.0}],
        N=4, src_chain="shardbribe-localnet-1", measurement_resolution_ms=1000.0)
    check("partial_n_slashed", rec.n_slashed == 1)
    check("partial_T_acc", rec.T_acc == 1300.0)


def test_negative_no_conflict():
    """Identical block-ids in both partitions => no double-spend => floor fails."""
    same_b = _commit(163, 0, "AAAA", [E1, E2, H2])
    f = parse_committee_fork(COMMIT_A, same_b, F=1)
    check("no_conflict_flag", f["conflicting_certs"] is False)
    check("no_conflict_floor_fails", f["quorum_intersection_ok"] is False)


def test_negative_different_rounds():
    """Conflicting but at different rounds => NOT a duplicate vote => floor fails."""
    b_r1 = _commit(163, 1, "BBBB", [E1, E2, H2])
    f = parse_committee_fork(COMMIT_A, b_r1, F=1)
    check("diff_round_conflicts", f["conflicting_certs"] is True)
    check("diff_round_not_same_round", f["same_round"] is False)
    check("diff_round_floor_fails", f["quorum_intersection_ok"] is False)


def test_negative_single_equivocator():
    """Only e1 shared across branches => 1 < F+1 => floor fails. (On a real N=4 this
    cannot arise for two true Q=3 certs -- Lemma 1 forces >=2 -- so it models a
    degenerate capture, e.g. the old two-nodes-one-key single double-signer; we still
    assert the code fails the floor on it.)"""
    b_one = _commit(163, 0, "BBBB", [E1, "H3ADDR", "H4ADDR"])   # shares only E1 with A
    f = parse_committee_fork(COMMIT_A, b_one, F=1)
    check("single_equiv_count", f["n_equivocators"] == 1)
    check("single_equiv_floor_fails", f["quorum_intersection_ok"] is False)


def test_gate_refuses_mainnet():
    """The equivocation backend is hard-gated to the localnet allowlist."""
    raised = False
    try:
        committee_harness("cosmoshub-4", rpc_a="http://x", rpc_b="http://y", height=1)
    except RuntimeError:
        raised = True
    check("gate_refuses_mainnet", raised)


if __name__ == "__main__":
    test_parse_commit_signers()
    test_fork_happy()
    test_record_happy()
    test_partial_slash()
    test_negative_no_conflict()
    test_negative_different_rounds()
    test_negative_single_equivocator()
    test_gate_refuses_mainnet()
    print(f"\n{len(_passed)} checks passed.")
