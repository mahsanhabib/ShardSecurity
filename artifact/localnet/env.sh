#!/usr/bin/env bash
# Shared configuration for the RQ8 self-equivocation localnet kit (arms A & C).
# Source this from the run scripts: `source env.sh`.
#
# Target environment (matches results/measured/devnet-rpc-gaiad.meta.json):
#   WSL2 Ubuntu, userspace `gaiad v19.2.0` on PATH, no sudo, no Docker.
# Everything runs under $WORK (a scratch dir); nothing touches the system.
set -euo pipefail

# --- binaries -------------------------------------------------------------
GAIAD="${GAIAD:-gaiad}"          # override: GAIAD=/path/to/gaiad
JQ="${JQ:-jq}"
PYTHON="${PYTHON:-python3}"

# --- repo / output --------------------------------------------------------
# artifact/ dir (one level up from this kit). Used to write results + fold-in.
ARTIFACT_DIR="${ARTIFACT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
WORK="${WORK:-${TMPDIR:-/tmp}/rq8-localnet}"     # scratch root for node homes

# --- chain identity (MUST be in livemeasure.ALLOWED_EQUIVOCATION_CHAINS) ---
# arm A (mainnet-like) and arm C (fast-exit) use different chain-ids/params.
CHAIN_A="${CHAIN_A:-shardbribe-localnet-1}"
CHAIN_C="${CHAIN_C:-fastexit-devnet-positive}"

# --- ports (val0 honest, val1a/val1b the duplicated equivocator) ----------
# High range on purpose: avoids colliding with a separately-running localnet on the
# standard 26656/26657/9090 ports (e.g. a hand-run two-nodes-one-key devnet). If the
# kit bound the standard ports it could silently attach to the wrong chain.
P_VAL0_RPC="${P_VAL0_RPC:-36657}"; P_VAL0_P2P="${P_VAL0_P2P:-36656}"
P_VAL1A_RPC="${P_VAL1A_RPC:-36757}"; P_VAL1A_P2P="${P_VAL1A_P2P:-36756}"
P_VAL1B_RPC="${P_VAL1B_RPC:-36857}"; P_VAL1B_P2P="${P_VAL1B_P2P:-36856}"
VAL0_RPC="http://127.0.0.1:${P_VAL0_RPC}"        # the reporter we read from

# --- staking so the chain SURVIVES val1's tombstone -----------------------
# val0 must keep >2/3 voting power alone, else the chain halts when val1 is
# jailed and we never observe the slash land. Powers are in stake (uatom).
DENOM="${DENOM:-uatom}"
VAL0_STAKE="${VAL0_STAKE:-100000000}"            # ~80% power: liveness after val1 jail
VAL1_STAKE="${VAL1_STAKE:-25000000}"             # the equivocator (minority)
SLASH_DOUBLE_SIGN="${SLASH_DOUBLE_SIGN:-0.05}"   # 5%, as in the n=1 run

# --- per-arm consensus params (jq-set into genesis; see setup_localnet.sh) -
# Arm A: mainnet-like — long unbonding, 48h evidence age. Slash always catches
#        the stake (q_attack -> 1): corroborates the SAFE side on real code.
A_UNBONDING="${A_UNBONDING:-1814400s}"           # 21 d
A_EVIDENCE_AGE="${A_EVIDENCE_AGE:-172800s}"      # 48 h
A_EVIDENCE_NUMBLOCKS="${A_EVIDENCE_NUMBLOCKS:-1000000}"
# Arm C: fast-exit positive control — unbonding SHORTER than enforcement, so the
#        stake exits before the slash lands (q_attack -> 0 -> OPEN). This is the
#        literal "fast-exit hypothetical" row, now on real client code.
C_UNBONDING="${C_UNBONDING:-1s}"                 # < the ~1-2 block enforcement
C_EVIDENCE_AGE="${C_EVIDENCE_AGE:-3s}"           # short: evidence can expire unslashed
C_EVIDENCE_NUMBLOCKS="${C_EVIDENCE_NUMBLOCKS:-3}"
# Arm C REAL unbond (observed completion). The equivocator unbonds part of its
# self-delegation a few blocks BEFORE the double-sign so the unbonding matures
# (creation_height < infraction; full amount returned) before the evidence is
# processed -> the stake escapes on real client code. q_attack is then measured from
# the observed complete_unbonding vs the observed slash (NOT an analytic deadline).
C_UNBOND_PCT="${C_UNBOND_PCT:-80}"               # % of val1 self-delegation to unbond
C_UNBOND_LEAD_BLOCKS="${C_UNBOND_LEAD_BLOCKS:-2}"  # submit unbond N blocks before the double-sign
UNBOND_WATCH_BLOCKS="${UNBOND_WATCH_BLOCKS:-30}" # blocks to scan for complete_unbonding
UNBOND_FEES="${UNBOND_FEES:-2000}"               # tx fee (uatom); localnet min-gas-price=0

# --- timing knobs ---------------------------------------------------------
EPISODES="${EPISODES:-40}"                       # N >= 40 (Wilson upper on p=0 ~0.09)
DBLSIGN_TIMEOUT="${DBLSIGN_TIMEOUT:-120}"        # s to wait for evidence per episode
SLASH_WINDOW_BLOCKS="${SLASH_WINDOW_BLOCKS:-8}"  # blocks to scan for the applied slash
BLOCK_INTERVAL_MS="${BLOCK_INTERVAL_MS:-1000}"   # ~1s blocks on the localnet

# --- Arm B: PAIRED settlement-vs-accountability race (real client code) -----
# Adds a second single-node "bridge" zone (the value sink) and a relayer that fills
# it on the SOURCE conflicting cert. ONE knob -- the relayer's finality-gate depth --
# flips OPEN <-> RULED_OUT, the live demonstration of Proposition 1:
#   B-open  : relayer fills after B_GATE_DEPTH_OPEN source confirmations (ungated/fast)
#             -> T_settle (~sub-second dst fill) << T_acc (cooperative slash) -> OPEN.
#   B-gated : relayer waits B_GATE_DEPTH_GATED confirmations (past the slash horizon)
#             before filling -> T_settle >= T_acc, structurally_gated -> RULED_OUT.
# The SOURCE zone is arm A's two-nodes-one-key localnet (mainnet-like accountability,
# real q~1 slash) -- the openness comes ONLY from the settlement gate, not weak slashing.
CHAIN_B_SRC="${CHAIN_B_SRC:-$CHAIN_A}"            # source = arm-A equivocating localnet
CHAIN_B_DST="${CHAIN_B_DST:-ibc-devnet-zone-b}"  # destination "bridge" zone (value sink)
# The dst zone PERSISTS across the arm's episodes (it only receives fills, never
# tombstones) so it lives under its OWN work dir -- the per-episode source teardown
# (pkill -f "$WORK") must never reach it.
WORK_DST="${WORK_DST:-${TMPDIR:-/tmp}/rq8-destzone}"
# destination zone ports (its own 38xxx range; never collides with src 36xxx).
P_DST_RPC="${P_DST_RPC:-38657}"; P_DST_P2P="${P_DST_P2P:-38656}"
DST_RPC="http://127.0.0.1:${P_DST_RPC}"
# destination blocks are FAST (sub-second commit) so an ungated fill confirms well
# inside the cooperative source slash (~1-2 src blocks) -> a clean, wide OPEN margin.
DST_TIMEOUT_COMMIT="${DST_TIMEOUT_COMMIT:-200ms}"
B_GATE_DEPTH_OPEN="${B_GATE_DEPTH_OPEN:-1}"      # ungated: fill on the 1st src confirmation
B_GATE_DEPTH_GATED="${B_GATE_DEPTH_GATED:-12}"   # finality-gated: wait past the slash horizon
B_FILL_AMT="${B_FILL_AMT:-8000000}"              # value V the relayer fronts on the dst zone
B_FILL_FEES="${B_FILL_FEES:-2000}"               # dst tx fee (uatom); dst min-gas-price=0
B_RELAYER_POLL_MS="${B_RELAYER_POLL_MS:-50}"     # src poll interval (== T_settle resolution)
# Arm B source uses arm-A (mainnet-like) accountability params so the slash is REAL and
# q~1 -- the window is opened by the settlement gate alone.
B_UNBONDING="${B_UNBONDING:-$A_UNBONDING}"
B_EVIDENCE_AGE="${B_EVIDENCE_AGE:-$A_EVIDENCE_AGE}"
B_EVIDENCE_NUMBLOCKS="${B_EVIDENCE_NUMBLOCKS:-$A_EVIDENCE_NUMBLOCKS}"

log() { printf '[localnet] %s\n' "$*" >&2; }
die() { printf '[localnet] ERROR: %s\n' "$*" >&2; exit 1; }
