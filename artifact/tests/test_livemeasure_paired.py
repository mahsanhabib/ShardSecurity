"""Offline tests for the arm-B PAIRED real-client-code race (no live localnet).

Exercise the pure pieces of the paired backend:
  * assemble_paired_record -- combines a real settlement leg (t_src_cert->t_dst_receipt)
    with a real source slash (t_infraction->t_slash) into ONE paired record, and sets
    structurally_gated for the Proposition-1 twin.
  * estimate_path over the assembled records -- the OPEN arm must return OPEN-WINDOW and
    the GATED twin must return RULED_OUT, with the SAME frozen decision rule.

Load-bearing invariants:
  - OPEN: T_settle << T_acc on every episode => p_win=1, rho>1, not gated => OPEN.
  - GATED: relayer waits past the accountability horizon => structurally_gated => the
    decision rule returns RULED_OUT (immunity by construction), one knob flipped.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shardbribe.livemeasure import assemble_paired_record  # noqa: E402
from shardbribe.estimate import estimate_path               # noqa: E402

_passed = []


def check(name, cond):
    assert cond, f"FAILED: {name}"
    _passed.append(name)
    print("ok ", name)


def _open_rec(i):
    """One OPEN episode: fast ungated fill (T_settle ~0.3s) beats the cooperative
    slash (T_acc ~1.4-1.6s)."""
    return assemble_paired_record(
        t_infraction=0.0, t_slash=1400.0 + (i % 5) * 40.0,
        t_src_cert_ms=0.0, t_dst_receipt_ms=280.0 + (i % 7) * 20.0,
        gated=False, gate_depth=1, fill_amount=8_000_000.0,
        src_chain="shardbribe-localnet-1", dst_chain="ibc-devnet-zone-b",
        measurement_resolution_ms=200.0)


def _gated_rec(i):
    """One GATED-twin episode: relayer waits past the slash horizon before filling
    (T_settle ~5s >> T_acc ~1.5s) AND marks the path structurally gated (Prop. 1)."""
    return assemble_paired_record(
        t_infraction=0.0, t_slash=1500.0 + (i % 5) * 40.0,
        t_src_cert_ms=0.0, t_dst_receipt_ms=5000.0 + (i % 7) * 50.0,
        gated=True, gate_depth=12, fill_amount=8_000_000.0,
        src_chain="shardbribe-localnet-1", dst_chain="ibc-devnet-zone-b",
        measurement_resolution_ms=200.0)


def test_open_record_fields():
    r = _open_rec(0)
    check("open_T_settle", r.T_settle == 280.0)
    check("open_T_acc", r.T_acc == 1400.0)
    check("open_race_won", r.T_settle < r.T_acc)
    check("open_not_gated", r.structurally_gated is False)
    check("open_tacc_bound_lo", r.tacc_bound == "lo")        # conservative slash
    check("open_user_leg_irreversible", r.reorg_survived is True)
    check("open_legs_present", r.t_src_cert == 0.0 and r.t_dst_receipt == 280.0)


def test_gated_record_fields():
    r = _gated_rec(0)
    check("gated_flag", r.structurally_gated is True)
    check("gated_race_lost", r.T_settle >= r.T_acc)


def test_missing_slash_leaves_tacc_none():
    # If no slash is observed (t_slash None), T_acc is None and the episode is dropped
    # from the paired set rather than scored as a spurious win.
    r = assemble_paired_record(
        t_infraction=0.0, t_slash=None, t_src_cert_ms=0.0, t_dst_receipt_ms=300.0,
        gated=False, src_chain="shardbribe-localnet-1", dst_chain="ibc-devnet-zone-b",
        measurement_resolution_ms=200.0)
    check("no_slash_tacc_none", r.T_acc is None)
    check("no_slash_settle_ok", r.T_settle == 300.0)


def test_estimate_open_verdict():
    recs = [_open_rec(i).to_dict() for i in range(40)]
    out = estimate_path(recs, system="Across V3 (self-fill)",
                        path="paired self-fill (real code)",
                        structurally_gated=False, g2_classic_clearable=True,
                        g2_solver_clearable=True, B=2000, seed=1)
    check("open_pwin_point", out["p_win"]["p_win"] == 1.0)
    check("open_pwin_n", out["p_win"]["n"] == 40)
    check("open_rho_excludes_1", out["rho"]["median_ratio_ci"][0] > 1.0)
    check("open_verdict", out["verdict"] == "OPEN")


def test_estimate_gated_twin_ruled_out():
    recs = [_gated_rec(i).to_dict() for i in range(40)]
    out = estimate_path(recs, system="Across V3 (gated twin)",
                        path="finality-gated relayer (Prop.1)",
                        structurally_gated=True, g2_classic_clearable=True,
                        g2_solver_clearable=True, B=2000, seed=1)
    check("gated_verdict", out["verdict"] == "RULED_OUT")
    check("gated_prop1_rationale", "Prop.1" in out["rationale"])


def test_open_paired_arm_demonstrates_immunity_knob():
    # The SAME records, same g2 flags -- only the gate knob differs -- must flip the
    # verdict. This is the live Proposition-1 demonstration the paper claims.
    op = estimate_path([_open_rec(i).to_dict() for i in range(40)],
                       system="x", path="open", structurally_gated=False,
                       g2_classic_clearable=True, B=2000, seed=2)
    ga = estimate_path([_gated_rec(i).to_dict() for i in range(40)],
                       system="x", path="gated", structurally_gated=True,
                       g2_classic_clearable=True, B=2000, seed=2)
    check("knob_flips_verdict", op["verdict"] == "OPEN" and ga["verdict"] == "RULED_OUT")


if __name__ == "__main__":
    test_open_record_fields()
    test_gated_record_fields()
    test_missing_slash_leaves_tacc_none()
    test_estimate_open_verdict()
    test_estimate_gated_twin_ruled_out()
    test_open_paired_arm_demonstrates_immunity_knob()
    print(f"\n{len(_passed)} checks passed.")
