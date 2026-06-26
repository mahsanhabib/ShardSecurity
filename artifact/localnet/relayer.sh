#!/usr/bin/env bash
# Arm-B fill relayer -- the SINGLE knob that flips OPEN <-> RULED_OUT.
#
# Watches the SOURCE localnet live for the conflicting certificate (the equivocation
# evidence), then -- predicated on that source cert -- fronts a real value fill on the
# destination "bridge" zone, exactly as a fast intent-bridge solver does. The knob is
# GATE_DEPTH: how many source confirmations the relayer waits before it fills.
#
#   GATE_DEPTH small (ungated)  -> fills on the source commit, before accountability
#                                  resolves -> T_settle << T_acc  -> OPEN.
#   GATE_DEPTH large (finality-gated, >= the slash horizon) -> fills only after the
#                                  source cert is past T_acc      -> T_settle >= T_acc.
#
# Timing is taken on the relayer's OWN monotonic wall clock for BOTH endpoints
# (t_src_cert when it first SEES the cert; t_dst_receipt when the fill confirms), so
# T_settle is a single-clock delta with no cross-chain skew (prereg T13). T_acc is read
# later from the source chain by collect_devnet (real x/evidence->x/slashing).
#
# Usage: relayer.sh <gate_depth> <gated 0|1> <watch_from_height> <out_json>
# Writes ONE JSON object to <out_json> and echoes the observed infraction height.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$HERE/env.sh"; source "$HERE/lib.sh"

GATE_DEPTH="${1:?gate_depth}"; GATED="${2:?gated 0|1}"
FROM="${3:?watch_from_height}"; OUT="${4:?out_json}"
now_ms() { date +%s%3N; }                       # epoch milliseconds (single clock)

SRC="$VAL0_RPC"
DSTHOME="$WORK_DST/dstval"
SINK="$(cat "$WORK_DST/.sink")"

# 1) watch the source live for the conflicting cert; stamp t_src_cert on first sight.
log "[B/relayer] watching $SRC for the source cert from height $FROM (gate=$GATE_DEPTH) ..."
H_INF=""
for _ in $(seq 1 "$DBLSIGN_TIMEOUT"); do
  if H_INF="$(find_evidence_height "$SRC" "$FROM")"; then break; fi
  H_INF=""; sleep "$(awk "BEGIN{print $B_RELAYER_POLL_MS/1000}")"
done
[ -n "$H_INF" ] || die "[B/relayer] no source cert within ${DBLSIGN_TIMEOUT}s"
T_SRC_MS="$(now_ms)"
log "[B/relayer] source cert observed at height $H_INF (t_src_cert=$T_SRC_MS)"

# 2) wait GATE_DEPTH source confirmations past the cert (the finality-gate knob).
target=$(( H_INF + GATE_DEPTH ))
while [ "$(rpc_height "$SRC")" -lt "$target" ]; do sleep 0.2; done

# 3) front the fill on the destination zone (real `gaiad tx bank send`), then poll for
#    inclusion and stamp t_dst_receipt = the realised, irreversible value V.
log "[B/relayer] filling ${B_FILL_AMT}${DENOM} solver->sink on $DST_RPC"
TXJSON="$("$GAIAD" tx bank send solver "$SINK" "${B_FILL_AMT}${DENOM}" \
    --from solver --keyring-backend test --home "$DSTHOME" --chain-id "$CHAIN_B_DST" \
    --node "$DST_RPC" --gas 200000 --fees "${B_FILL_FEES}${DENOM}" \
    --broadcast-mode sync -y -o json 2>"$WORK_DST/fill.err" || true)"
TXHASH="$(echo "$TXJSON" | "$JQ" -r '.txhash // empty' 2>/dev/null || true)"
[ -n "$TXHASH" ] || die "[B/relayer] fill broadcast failed (see $WORK_DST/fill.err): $(head -c 300 "$WORK_DST/fill.err" 2>/dev/null)"
TXCODE="$(echo "$TXJSON" | "$JQ" -r '.code // 0' 2>/dev/null || echo 0)"
[ "$TXCODE" = "0" ] || die "[B/relayer] fill rejected at CheckTx (code=$TXCODE): $(echo "$TXJSON" | "$JQ" -r '.raw_log' 2>/dev/null)"
T_DST_MS=""
for _ in $(seq 1 60); do
  HH="$("$GAIAD" query tx "$TXHASH" --node "$DST_RPC" -o json 2>/dev/null \
        | "$JQ" -r '.height // empty' 2>/dev/null || true)"
  if [ -n "$HH" ] && [ "$HH" != "0" ]; then T_DST_MS="$(now_ms)"; break; fi
  sleep 0.1
done
[ -n "$T_DST_MS" ] || die "[B/relayer] fill tx $TXHASH never confirmed on the dst zone"
log "[B/relayer] fill confirmed (t_dst_receipt=$T_DST_MS); T_settle=$(( T_DST_MS - T_SRC_MS )) ms"

# 4) emit ONE relayer episode record for collect_devnet --paired-records.
"$JQ" -n \
  --argjson infraction_height "$H_INF" \
  --argjson t_src_cert_ms "$T_SRC_MS" \
  --argjson t_dst_receipt_ms "$T_DST_MS" \
  --argjson gate_depth "$GATE_DEPTH" \
  --argjson fill_amount "$B_FILL_AMT" \
  --argjson measurement_resolution_ms "$B_RELAYER_POLL_MS" \
  --argjson gated "$([ "$GATED" = "1" ] && echo true || echo false)" \
  '{infraction_height:$infraction_height, t_src_cert_ms:$t_src_cert_ms,
    t_dst_receipt_ms:$t_dst_receipt_ms, gate_depth:$gate_depth, fill_amount:$fill_amount,
    measurement_resolution_ms:$measurement_resolution_ms, gated:$gated}' > "$OUT"
echo "$H_INF"
