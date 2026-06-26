#!/usr/bin/env bash
# Genesis a SINGLE-NODE destination "bridge" zone for the arm-B paired race: the
# value sink the relayer fronts the fill into. No equivocation happens here -- it
# only needs to produce fast blocks and accept a real `gaiad tx bank send`.
# Usage: setup_destzone.sh   (reads CHAIN_B_DST / ports / DST_TIMEOUT_COMMIT from env.sh)
#
# Accounts (keyring-backend test, in the dst home):
#   dstval  -- the single validator (majority power; keeps the zone live)
#   solver  -- funded with many fills' worth; the relayer sends FROM here (the
#              solver/attacker fronting V on the fast leg)
#   sink    -- where each fill lands = the attacker's REALISED value V (irreversible
#              to the recipient even if the source branch is later slashed)
#
# AUTHORED AGAINST THE DOCUMENTED v0.50/gaiad-v19 RECIPE (mirrors setup_localnet.sh);
# run it on the gaiad-capable host, not here.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$HERE/env.sh"; source "$HERE/lib.sh"

CHAIN="$CHAIN_B_DST"
preflight "$CHAIN"                       # dst chain-id is in the allowlist too (harmless)

HD="$WORK_DST/dstval"
rm -rf "$WORK_DST"; mkdir -p "$WORK_DST"
KR=(--keyring-backend test)

log "[B/$CHAIN] init destination bridge zone (single validator)"
"$GAIAD" init dstval --chain-id "$CHAIN" --home "$HD" >/dev/null 2>&1
"$GAIAD" keys add dstval "${KR[@]}" --home "$HD" >/dev/null 2>&1
"$GAIAD" keys add solver "${KR[@]}" --home "$HD" >/dev/null 2>&1
"$GAIAD" keys add sink   "${KR[@]}" --home "$HD" >/dev/null 2>&1
AVAL="$("$GAIAD" keys show dstval -a "${KR[@]}" --home "$HD")"
ASOLVER="$("$GAIAD" keys show solver -a "${KR[@]}" --home "$HD")"
ASINK="$("$GAIAD" keys show sink   -a "${KR[@]}" --home "$HD")"

# fund: validator stake; solver gets EPISODES worth of fills + fees; sink starts ~0.
SOLVER_FUND=$(( (B_FILL_AMT + B_FILL_FEES) * (EPISODES + 5) ))
"$GAIAD" genesis add-genesis-account "$AVAL"    "$((VAL0_STAKE*2))$DENOM" --home "$HD" >/dev/null
"$GAIAD" genesis add-genesis-account "$ASOLVER" "${SOLVER_FUND}$DENOM"    --home "$HD" >/dev/null
"$GAIAD" genesis add-genesis-account "$ASINK"   "1$DENOM"                 --home "$HD" >/dev/null

G="$HD/config/genesis.json"
json_edit "$G" ".app_state.staking.params.bond_denom = \"$DENOM\""
# feemarket surgery, identical to setup_localnet.sh: disable so 0-fee uatom txs pass.
if "$JQ" -e '.app_state.feemarket.params' "$G" >/dev/null 2>&1; then
  json_edit "$G" ".app_state.feemarket.params.fee_denom = \"$DENOM\""
  json_edit "$G" ".app_state.feemarket.params.min_base_gas_price = \"0.000000000000000001\""
  json_edit "$G" ".app_state.feemarket.params.enabled = false"
  json_edit "$G" ".app_state.feemarket.state.base_gas_price = \"0.000000000000000001\""
fi

"$GAIAD" genesis gentx dstval "$VAL0_STAKE$DENOM" --chain-id "$CHAIN" "${KR[@]}" \
  --home "$HD" --ip 127.0.0.1 >/dev/null 2>&1
"$GAIAD" genesis collect-gentxs --home "$HD" >/dev/null 2>&1
"$GAIAD" genesis validate-genesis --home "$HD" >/dev/null 2>&1 || log "WARN: validate-genesis complained"

# fast sub-second blocks so an ungated fill confirms well inside the source slash;
# keep state, tx index on, 0 min-gas-price (uatom).
c="$HD/config/config.toml"; a="$HD/config/app.toml"
sed -i \
  -e "s#^laddr = \"tcp://127.0.0.1:26657\"#laddr = \"tcp://0.0.0.0:$P_DST_RPC\"#" \
  -e "s#^laddr = \"tcp://0.0.0.0:26656\"#laddr = \"tcp://0.0.0.0:$P_DST_P2P\"#" \
  -e "s#^timeout_commit = \"5s\"#timeout_commit = \"$DST_TIMEOUT_COMMIT\"#" \
  -e "s#^indexer = \"null\"#indexer = \"kv\"#" \
  "$c"
sed -i -e "s#^pruning = \"default\"#pruning = \"nothing\"#" \
       -e "s#^minimum-gas-prices = \"\"#minimum-gas-prices = \"0$DENOM\"#" \
       -e "s#^enable = true#enable = false#" "$a"     # gRPC off (we use the RPC laddr)

echo "$CHAIN" > "$WORK_DST/.chain"
echo "$ASOLVER" > "$WORK_DST/.solver"
echo "$ASINK"   > "$WORK_DST/.sink"
log "[B] destination zone genesis ready under $WORK_DST (solver=$ASOLVER sink=$ASINK)"
