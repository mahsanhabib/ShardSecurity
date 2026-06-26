#!/usr/bin/env bash
# Genesis a fresh 2-validator localnet for one episode and configure the
# two-nodes-one-key equivocator. Usage: setup_localnet.sh <A|C>
#
# Topology (from devnet-rpc-gaiad.meta.json):
#   val0  -- honest, majority power (keeps the chain alive after val1 is jailed)
#   val1a -- the equivocator validator (minority power)
#   val1b -- a SECOND node carrying val1's SAME priv_validator_key.json with a
#            fresh node_key and double_sign_check_height=0 (the operator footgun).
# val1a and val1b both peer to val0 but NOT to each other, so they sign
# conflicting precommits -> val0 reports real DuplicateVoteEvidence.
#
# NB: this performs cosmos-sdk v0.50 / gaiad v19 genesis surgery. Genesis JSON
# paths and the `gaiad genesis|comet` subcommands are version-sensitive; they
# are flagged below. AUTHORED AGAINST THE DOCUMENTED RECIPE, not run here.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$HERE/env.sh"; source "$HERE/lib.sh"

ARM="${1:?usage: setup_localnet.sh <A|C>}"
case "$ARM" in
  A) CHAIN="$CHAIN_A"; UNBONDING="$A_UNBONDING"; EV_AGE="$A_EVIDENCE_AGE"; EV_NB="$A_EVIDENCE_NUMBLOCKS";;
  C) CHAIN="$CHAIN_C"; UNBONDING="$C_UNBONDING"; EV_AGE="$C_EVIDENCE_AGE"; EV_NB="$C_EVIDENCE_NUMBLOCKS";;
  *) die "arm must be A or C";;
esac
preflight "$CHAIN"

H0="$WORK/val0"; H1="$WORK/val1a"; H2="$WORK/val1b"
rm -rf "$WORK"; mkdir -p "$WORK"
KR=(--keyring-backend test)

log "[$ARM/$CHAIN] init val0 + val1a homes"
"$GAIAD" init val0  --chain-id "$CHAIN" --home "$H0" >/dev/null 2>&1
"$GAIAD" init val1a --chain-id "$CHAIN" --home "$H1" >/dev/null 2>&1
"$GAIAD" keys add val0 "${KR[@]}" --home "$H0" >/dev/null 2>&1
# val1's ACCOUNT key must live in val1a's home (H1): `genesis gentx val1 --home H1`
# signs with it, and arm C later runs `tx staking unbond --from val1 --home H1`.
"$GAIAD" keys add val1 "${KR[@]}" --home "$H1" >/dev/null 2>&1
A0="$("$GAIAD" keys show val0 -a "${KR[@]}" --home "$H0")"
A1="$("$GAIAD" keys show val1 -a "${KR[@]}" --home "$H1")"

# fund both accounts (genesis subcommand namespace is v0.50)
"$GAIAD" genesis add-genesis-account "$A0" "$((VAL0_STAKE*2))$DENOM" --home "$H0" >/dev/null
"$GAIAD" genesis add-genesis-account "$A1" "$((VAL1_STAKE*2))$DENOM" --home "$H0" >/dev/null

G="$H0/config/genesis.json"
log "[$ARM] set bond_denom / unbonding=$UNBONDING / evidence_age=$EV_AGE / slash=$SLASH_DOUBLE_SIGN"
json_edit "$G" ".app_state.staking.params.bond_denom = \"$DENOM\""
json_edit "$G" ".app_state.staking.params.unbonding_time = \"$UNBONDING\""
json_edit "$G" ".app_state.slashing.params.slash_fraction_double_sign = \"$SLASH_DOUBLE_SIGN\""
# evidence params moved to .consensus.params.evidence in v0.50 (was .consensus_params)
if "$JQ" -e '.consensus.params.evidence' "$G" >/dev/null 2>&1; then EVP=".consensus.params.evidence";
elif "$JQ" -e '.consensus_params.evidence' "$G" >/dev/null 2>&1; then EVP=".consensus_params.evidence";
else die "cannot locate evidence params in genesis (check gaiad version)"; fi
json_edit "$G" "$EVP.max_age_duration = \"$(( ${EV_AGE%s} * 1000000000 ))\""   # ns
json_edit "$G" "$EVP.max_age_num_blocks = \"$EV_NB\""
# gaiad v19 ships x/feemarket (EIP-1559) defaulting to fee_denom=stake and a non-zero
# min base gas price, which rejects our uatom fees with "error resolving denom". Point
# it at our denom, zero the price, and disable it so 0-fee localnet txs pass CheckTx.
if "$JQ" -e '.app_state.feemarket.params' "$G" >/dev/null 2>&1; then
  # feemarket ValidateGenesis requires the base gas price to be strictly POSITIVE, so
  # use a tiny non-zero value (not 0) and disable the module: with enabled=false the
  # feemarket ante is bypassed and the node's 0uatom min-gas-price governs, so our
  # uatom-fee localnet txs pass CheckTx.
  json_edit "$G" ".app_state.feemarket.params.fee_denom = \"$DENOM\""
  json_edit "$G" ".app_state.feemarket.params.min_base_gas_price = \"0.000000000000000001\""
  json_edit "$G" ".app_state.feemarket.params.enabled = false"
  json_edit "$G" ".app_state.feemarket.state.base_gas_price = \"0.000000000000000001\""
fi

# both validators gentx against the SAME funded genesis (copy to val1a home)
cp "$G" "$H1/config/genesis.json"
log "[$ARM] gentx val0 (majority) + val1a (minority equivocator)"
"$GAIAD" genesis gentx val0 "$VAL0_STAKE$DENOM" --chain-id "$CHAIN" "${KR[@]}" --home "$H0" \
  --ip 127.0.0.1 >/dev/null 2>&1
"$GAIAD" genesis gentx val1 "$VAL1_STAKE$DENOM" --chain-id "$CHAIN" "${KR[@]}" --home "$H1" \
  --ip 127.0.0.1 >/dev/null 2>&1
cp "$H1"/config/gentx/*.json "$H0"/config/gentx/
"$GAIAD" genesis collect-gentxs --home "$H0" >/dev/null 2>&1
"$GAIAD" genesis validate-genesis --home "$H0" >/dev/null 2>&1 || log "WARN: validate-genesis complained"

# val0 node id for peering (v0.50: `gaiad comet show-node-id`, older: tendermint)
ID0="$("$GAIAD" comet show-node-id --home "$H0" 2>/dev/null || "$GAIAD" tendermint show-node-id --home "$H0")"
PEER0="$ID0@127.0.0.1:$P_VAL0_P2P"

# common config tweaks: fast blocks, keep state (pruning=nothing so /block_results
# survive), tx index on, allow localhost dup ips.
cfg() { # cfg <home> <rpc_port> <p2p_port> <peers> <dscheight>
  local home="$1" rpc="$2" p2p="$3" peers="$4" dsc="$5"
  local c="$home/config/config.toml" a="$home/config/app.toml"
  sed -i \
    -e "s#^laddr = \"tcp://127.0.0.1:26657\"#laddr = \"tcp://0.0.0.0:$rpc\"#" \
    -e "s#^laddr = \"tcp://0.0.0.0:26656\"#laddr = \"tcp://0.0.0.0:$p2p\"#" \
    -e "s#^persistent_peers = \"\"#persistent_peers = \"$peers\"#" \
    -e "s#^allow_duplicate_ip = false#allow_duplicate_ip = true#" \
    -e "s#^addr_book_strict = true#addr_book_strict = false#" \
    -e "s#^double_sign_check_height = .*#double_sign_check_height = $dsc#" \
    -e "s#^timeout_commit = \"5s\"#timeout_commit = \"1s\"#" \
    -e "s#^indexer = \"null\"#indexer = \"kv\"#" \
    "$c"
  sed -i -e "s#^pruning = \"default\"#pruning = \"nothing\"#" \
         -e "s#^minimum-gas-prices = \"\"#minimum-gas-prices = \"0$DENOM\"#" \
         -e "s#^enable = true#enable = false#" "$a"   # disable gRPC (9090): all 3
  # nodes would otherwise fight over it (we read only via the RPC laddr). API is
  # off by default. The in-process app needs no proxy_app socket.
}

# val1b = duplicate of val1a: same genesis + SAME priv_validator_key, fresh node_key.
log "[$ARM] clone val1a -> val1b (two-nodes-one-key footgun, fresh node_key)"
# Init val1b on a CLEAN home FIRST: this creates its own node_key.json (distinct p2p
# peer) AND a valid data/priv_validator_state.json. Only THEN graft on val0's genesis
# and val1a's consensus key. (Running `init` on a home that already holds a copied
# priv_validator_key but no priv_validator_state makes gaiad init fail with
# "open .../priv_validator_state.json: no such file or directory".)
"$GAIAD" init val1b --chain-id "$CHAIN" --home "$H2" --overwrite >/dev/null 2>&1
cp "$H0/config/genesis.json" "$H1/config/genesis.json"
cp "$H0/config/genesis.json" "$H2/config/genesis.json"
cp "$H1/config/priv_validator_key.json" "$H2/config/priv_validator_key.json"   # SAME consensus key (footgun)
printf '{"height":"0","round":0,"step":0}' > "$H2/data/priv_validator_state.json"

cfg "$H0" "$P_VAL0_RPC"  "$P_VAL0_P2P"  ""                 0
cfg "$H1" "$P_VAL1A_RPC" "$P_VAL1A_P2P" "$PEER0"           0
cfg "$H2" "$P_VAL1B_RPC" "$P_VAL1B_P2P" "$PEER0"           0

echo "$CHAIN" > "$WORK/.chain"
log "[$ARM] genesis ready under $WORK (val0 majority, val1a+val1b share a key)"
