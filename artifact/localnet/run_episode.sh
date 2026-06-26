#!/usr/bin/env bash
# One episode: start the localnet, induce a real double-sign, capture the
# infraction height, and fold the resulting record into a JSONL via the
# already-implemented `collect_devnet.py --backend rpc` path.
# Usage: run_episode.sh <A|C> <out_jsonl> <unbond_lead_ms>
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$HERE/env.sh"; source "$HERE/lib.sh"
ARM="${1:?arm}"; OUT="${2:?out jsonl}"; LEAD_MS="${3:?unbond_lead_ms}"
# Arm B (paired race) overloads $3 as the relayer GATE_DEPTH and $4 as the gated flag.
GATE_DEPTH="${3:-1}"; GATED="${4:-0}"

# Arm B SOURCE is arm A's mainnet-like equivocating localnet (real q~1 slash); the
# window is opened only by the settlement gate. The destination "bridge" zone is set up
# ONCE per arm by run_arm.sh and is already running on $DST_RPC.
SETUP_ARM="$ARM"; [ "$ARM" = "B" ] && SETUP_ARM="A"
bash "$HERE/setup_localnet.sh" "$SETUP_ARM"
CHAIN="$(cat "$WORK/.chain")"
H0="$WORK/val0"; H1="$WORK/val1a"; H2="$WORK/val1b"

start_node() { # start_node <home>
  local home="$1"
  nohup "$GAIAD" start --home "$home" --x-crisis-skip-assert-invariants \
    >"$home/node.log" 2>&1 &
  echo $! > "$home/node.pid"
}

trap teardown EXIT
pkill -f "$WORK" 2>/dev/null || true; sleep 1   # clear any orphan bound to our ports
log "[$ARM] starting val0 + val1a"
start_node "$H0"; start_node "$H1"
wait_rpc "$VAL0_RPC"
# let the chain produce a few blocks so val1 is actively signing
target=$(( $(rpc_height "$VAL0_RPC") + 3 ))
while [ "$(rpc_height "$VAL0_RPC")" -lt "$target" ]; do sleep 1; done

# Arm C: submit a REAL unbond of part of val1's self-delegation a few blocks BEFORE
# the double-sign. With C_UNBONDING < the enforcement latency it matures (full amount
# returned, creation_height < infraction) before the evidence is processed, so the
# stake escapes on real client code. q_attack is then measured from the OBSERVED
# complete_unbonding vs the observed slash, not an analytic deadline.
UNBOND_H=""; UNBOND_AMT=""
if [ "$ARM" = "C" ]; then
  VALOPER="$("$GAIAD" keys show val1 --bech val -a --keyring-backend test --home "$H1")"
  UNBOND_AMT=$(( VAL1_STAKE * C_UNBOND_PCT / 100 ))
  log "[C] submitting REAL unbond of ${UNBOND_AMT}${DENOM} from val1 ($VALOPER)"
  # fixed gas (no --gas auto): the simulation round-trip is flaky on a fresh localnet
  # and gRPC is disabled; min-gas-price is 0 so a small fee suffices. stderr -> a file
  # (|| true) so a failed broadcast is surfaced by die, not swallowed by set -e.
  TXJSON="$("$GAIAD" tx staking unbond "$VALOPER" "${UNBOND_AMT}${DENOM}" \
      --from val1 --keyring-backend test --home "$H1" --chain-id "$CHAIN" \
      --node "$VAL0_RPC" --gas 400000 --fees "${UNBOND_FEES}${DENOM}" \
      --broadcast-mode sync -y -o json 2>"$H1/unbond.err" || true)"
  TXHASH="$(echo "$TXJSON" | "$JQ" -r '.txhash // empty' 2>/dev/null || true)"
  [ -n "$TXHASH" ] || die "[C] unbond broadcast failed (see $H1/unbond.err): $(head -c 300 "$H1/unbond.err" 2>/dev/null)"
  # broadcast-mode sync returns a txhash even when CheckTx REJECTS the tx (code!=0);
  # catch that here with the raw_log instead of later as an opaque "never landed".
  TXCODE="$(echo "$TXJSON" | "$JQ" -r '.code // 0' 2>/dev/null || echo 0)"
  [ "$TXCODE" = "0" ] || die "[C] unbond rejected at CheckTx (code=$TXCODE): $(echo "$TXJSON" | "$JQ" -r '.raw_log' 2>/dev/null)"
  for _ in $(seq 1 30); do
    UNBOND_H="$("$GAIAD" query tx "$TXHASH" --node "$VAL0_RPC" -o json 2>/dev/null \
                | "$JQ" -r '.height // empty' 2>/dev/null || true)"
    [ -n "$UNBOND_H" ] && [ "$UNBOND_H" != "0" ] && break
    UNBOND_H=""; sleep 1
  done
  [ -n "$UNBOND_H" ] || die "[C] unbond tx $TXHASH never landed (see $H1/node.log)"
  log "[C] unbond at height $UNBOND_H; waiting $C_UNBOND_LEAD_BLOCKS block(s) so it matures pre-infraction"
  pre=$(( UNBOND_H + C_UNBOND_LEAD_BLOCKS ))
  while [ "$(rpc_height "$VAL0_RPC")" -lt "$pre" ]; do sleep 1; done
fi

from=$(rpc_height "$VAL0_RPC")
log "[$ARM] starting val1b (duplicate consensus key) to induce conflicting votes"
start_node "$H2"

# --- Arm B: paired race. The relayer (started watching from $from) catches the source
#     cert live, fronts the dst fill at GATE_DEPTH, and writes one episode record; then
#     we let the real slash settle and fold a PAIRED record (real T_settle vs real T_acc).
if [ "$ARM" = "B" ]; then
  RJSON="$WORK/relayer-episode.json"; rm -f "$RJSON"
  H_inf="$(bash "$HERE/relayer.sh" "$GATE_DEPTH" "$GATED" "$from" "$RJSON")" \
    || { log "[B] relayer produced no fill (no cert?). Skipping episode."; exit 3; }
  log "[B] relayer filled for infraction height $H_inf; letting slashing settle ($SLASH_WINDOW_BLOCKS blocks)"
  settle=$(( H_inf + SLASH_WINDOW_BLOCKS ))
  while [ "$(rpc_height "$VAL0_RPC")" -lt "$settle" ]; do sleep 1; done
  GATEDFLAG=(); [ "$GATED" = "1" ] && GATEDFLAG=(--gated)
  ( cd "$ARTIFACT_DIR" && "$PYTHON" collect_devnet.py \
      --chain-id "$CHAIN" --rpc "$VAL0_RPC" --paired-records "$RJSON" \
      --dst-chain "$CHAIN_B_DST" --slash-window "$SLASH_WINDOW_BLOCKS" \
      --block-interval-ms "$BLOCK_INTERVAL_MS" ${GATEDFLAG[@]+"${GATEDFLAG[@]}"} \
      --append --out "$OUT" ) \
    || die "collect_devnet --paired-records failed for height $H_inf"
  echo "$H_inf"; exit 0
fi

log "[$ARM] watching val0 for DuplicateVoteEvidence (timeout ${DBLSIGN_TIMEOUT}s) ..."
H_inf=""
for _ in $(seq 1 "$DBLSIGN_TIMEOUT"); do
  if H_inf="$(find_evidence_height "$VAL0_RPC" "$from")"; then break; fi
  H_inf=""; sleep 1
done
[ -n "$H_inf" ] || { log "[$ARM] no evidence within timeout (see $H2/node.log). Skipping episode."; exit 3; }
log "[$ARM] DuplicateVoteEvidence at height $H_inf; letting slashing settle ($SLASH_WINDOW_BLOCKS blocks)"
settle=$(( H_inf + SLASH_WINDOW_BLOCKS ))
while [ "$(rpc_height "$VAL0_RPC")" -lt "$settle" ]; do sleep 1; done

# fold THIS episode into the JSONL via the real-code rpc backend (reads /block,
# /block_results, /consensus_params at H_inf; q_attack=0 if no slash lands).
# Arm C: hand the real unbond height/amount to the collector so q_attack is measured
# from the OBSERVED unbonding completion (real client code), not an analytic deadline.
EXTRA=()
if [ "$ARM" = "C" ]; then
  EXTRA=(--unbond-height "$UNBOND_H" --unbond-amount "$UNBOND_AMT" \
         --unbond-watch "$UNBOND_WATCH_BLOCKS")
fi
( cd "$ARTIFACT_DIR" && "$PYTHON" collect_devnet.py --backend rpc \
    --chain-id "$CHAIN" --rpc "$VAL0_RPC" --evidence-heights "$H_inf" \
    --unbond-lead-ms "$LEAD_MS" --slash-window "$SLASH_WINDOW_BLOCKS" \
    --block-interval-ms "$BLOCK_INTERVAL_MS" ${EXTRA[@]+"${EXTRA[@]}"} \
    --append --out "$OUT" ) \
  || die "collect_devnet --backend rpc failed for height $H_inf"
echo "$H_inf"
