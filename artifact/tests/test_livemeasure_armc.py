"""Offline tests for the arm-C real-unbond / observed-completion path.

These exercise the pure pieces of the rpc backend without a live localnet:
  * parse_complete_unbonding  -- reads the staking `complete_unbonding` event.
  * _arm_c_exit               -- encodes the real escape/caught outcome into the two
                                 timestamps the FROZEN estimator compares
                                 (t_slash_effective < t_withdraw_unslashable == enforced).

The load-bearing invariant: for every scenario, (t_slash < t_withdraw) must equal the
real `caught` verdict, so estimate.py's q reflects what the chain actually did.
"""
import base64
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shardbribe.livemeasure import parse_complete_unbonding, _arm_c_exit  # noqa: E402

INTERVAL = 1000.0
LEAD = 60_000.0
_passed = []


def check(name, cond):
    assert cond, f"FAILED: {name}"
    _passed.append(name)
    print("ok ", name)


def _br(events):
    return {"result": {"finalize_block_events": events}}


def test_parse_plaintext():
    comps = parse_complete_unbonding(_br([
        {"type": "transfer", "attributes": []},
        {"type": "complete_unbonding", "attributes": [
            {"key": "amount", "value": "20000000uatom"},
            {"key": "validator", "value": "cosmosvaloper1abc"},
            {"key": "delegator", "value": "cosmos1abc"}]},
    ]))
    check("parse_plaintext_one", len(comps) == 1)
    check("parse_plaintext_amount", comps[0]["amount"] == 20000000.0)
    check("parse_plaintext_val", comps[0]["validator"] == "cosmosvaloper1abc")


def test_parse_base64():
    b64 = lambda s: base64.b64encode(s.encode()).decode()
    comps = parse_complete_unbonding(_br([
        {"type": "complete_unbonding", "attributes": [
            {"key": b64("amount"), "value": b64("19000000uatom")}]},
    ]))
    check("parse_base64_amount", comps and comps[0]["amount"] == 19000000.0)


def test_parse_filter_and_empty():
    ev = [{"type": "complete_unbonding", "attributes": [
        {"key": "amount", "value": "5uatom"},
        {"key": "validator", "value": "cosmosvaloper1abc"}]}]
    check("parse_filter_match", len(parse_complete_unbonding(
        _br(ev), validator="cosmosvaloper1abc")) == 1)
    check("parse_filter_miss", len(parse_complete_unbonding(
        _br(ev), validator="cosmosvaloper1other")) == 0)
    check("parse_no_event", len(parse_complete_unbonding(
        _br([{"type": "slash", "attributes": []}]))) == 0)


def _enforced(t_slash, t_withdraw):
    """estimate.py's frozen q rule for one record."""
    return t_slash is not None and t_withdraw is not None and t_slash < t_withdraw


def test_caught_same_block():
    # slash lands in the same block the unbond would mature (BeginBlock before EndBlock)
    tw, tc, caught = _arm_c_exit(
        t_inf=1000.0, t_slash=2000.0, h_slash=164,
        t_complete=2000.0, h_complete=164, returned=20e6, unbond_amount=20e6,
        block_interval_ms=INTERVAL, unbond_lead_ms=LEAD)
    check("same_block_caught", caught is True)
    check("same_block_invariant", _enforced(2000.0, tw) == caught)


def test_escaped_matures_earlier():
    # unbonding completed (full amount) two blocks before the slash -> escape
    tw, tc, caught = _arm_c_exit(
        t_inf=1000.0, t_slash=3000.0, h_slash=166,
        t_complete=1000.0, h_complete=164, returned=20e6, unbond_amount=20e6,
        block_interval_ms=INTERVAL, unbond_lead_ms=LEAD)
    check("escaped_not_caught", caught is False)
    check("escaped_withdraw_is_completion", tw == 1000.0 and tc == 1000.0)
    check("escaped_invariant", _enforced(3000.0, tw) == caught)


def test_clawback_by_amount():
    # returned < submitted => the slash clawed the exiting stake, even if completion
    # block came after the slash scan window edge
    tw, tc, caught = _arm_c_exit(
        t_inf=1000.0, t_slash=3000.0, h_slash=166,
        t_complete=4000.0, h_complete=168, returned=19e6, unbond_amount=20e6,
        block_interval_ms=INTERVAL, unbond_lead_ms=LEAD)
    check("clawback_caught", caught is True)
    check("clawback_invariant", _enforced(3000.0, tw) == caught)


def test_never_matured():
    # no completion observed within the watch window, but a slash landed -> still
    # slashable/pending => caught
    tw, tc, caught = _arm_c_exit(
        t_inf=1000.0, t_slash=2000.0, h_slash=164,
        t_complete=None, h_complete=None, returned=None, unbond_amount=20e6,
        block_interval_ms=INTERVAL, unbond_lead_ms=LEAD)
    check("never_matured_caught", caught is True)
    check("never_matured_invariant", _enforced(2000.0, tw) == caught)


def test_no_slash_no_completion():
    # neither a slash nor a completion observed -> indeterminate (caught None)
    tw, tc, caught = _arm_c_exit(
        t_inf=1000.0, t_slash=None, h_slash=None,
        t_complete=None, h_complete=None, returned=None, unbond_amount=20e6,
        block_interval_ms=INTERVAL, unbond_lead_ms=LEAD)
    check("no_slash_caught_none", caught is None)
    check("no_slash_fallback_analytic", tw == 1000.0 + LEAD)


if __name__ == "__main__":
    for fn in list(globals().values()):
        if callable(fn) and getattr(fn, "__name__", "").startswith("test_"):
            fn()
    print(f"\n{len(_passed)} checks passed")
