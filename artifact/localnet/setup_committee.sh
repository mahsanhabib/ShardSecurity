#!/usr/bin/env bash
# Genesis a fresh N=4 (F=1, Q=3, floor k=F+1=2) committee and stage the 6-node
# partitioned topology for the faithful committee-fork experiment. Usage:
#   setup_committee.sh
#
# Validator set (4 equal-power validators, 25% each):
#   e1, e2 -- the TWO distinct equivocators (quorum-intersection floor, Lemma 1)
#   h1     -- honest, will commit branch A
#   h2     -- honest, will commit branch B
# Node homes (6): each equivocator runs TWO nodes sharing ONE consensus key
# (two-nodes-one-key x2), so it can precommit BOTH branches at the same (H,round):
#   partition A: e1a, e2a, h1     (peer only within A)
#   partition B: e1b, e2b, h2     (peer only within B)
# Each partition holds 3/4 = 75% >= 2/3 -> each commits its OWN block at height H.
# run_committee.sh then injects a different spend of the SAME coins in each partition
# (a real shard-local double-spend), reads the two conflicting /commit certs, heals
# the partition, and collects the real slash of BOTH e1 and e2.
#
# Genesis surgery is cosmos-sdk v0.50 / gaiad v19. AUTHORED against the documented
# recipe (same as setup_localnet.sh, which the A/C/B arms ran), NOT executed here.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$HERE/env.sh"; source "$HERE/lib.sh"

CHAIN="$CHAIN_N4"; WORK="$WORK_N4"
preflight "$CHAIN"

# 6 node homes (validator-set members e1,e2,h1,h2; e1b/e2b carry e1/e2's keys)
H_E1A="$WORK/e1a"; H_E2A="$WORK/e2a"; H_H1="$WORK/h1"
H_E1B="$WORK/e1b"; H_E2B="$WORK/e2b"; H_H2="$WORK/h2"
rm -rf "$WORK"; mkdir -p "$WORK"
KR=(--keyring-backend test)
HUB="$H_E1A"                                  # the home we build genesis on

log "[N4/$CHAIN] init validator homes e1a,e2a,h1,h2"
for pair in "e1:$H_E1A" "e2:$H_E2A" "h1:$H_H1" "h2:$H_H2"; do
  name="${pair%%:*}"; home="${pair##*:}"
  "$GAIAD" init "$name" --chain-id "$CHAIN" --home "$home" >/dev/null 2>&1
  # each validator's ACCOUNT key lives in its own home so `genesis gentx <name> --home`
  # can sign, and the double-spend tx can be signed from e1's home at run time.
  "$GAIAD" keys add "$name" "${KR[@]}" --home "$home" >/dev/null 2>&1
done
A_E1="$("$GAIAD" keys show e1 -a "${KR[@]}" --home "$H_E1A")"
A_E2="$("$GAIAD" keys show e2 -a "${KR[@]}" --home "$H_E2A")"
A_H1="$("$GAIAD" keys show h1 -a "${KR[@]}" --home "$H_H1")"
A_H2="$("$GAIAD" keys show h2 -a "${KR[@]}" --home "$H_H2")"

# Fund all four on the hub genesis. e1 gets EXTRA unbonded balance: at run time it
# spends the SAME surplus two ways (recipient_A in partition A, recipient_B in B) ->
# the conflicting certs encode a real double-spend, not just two empty blocks.
log "[N4] add-genesis-account (4 validators, equal stake; e1 funded for the double-spend)"
"$GAIAD" genesis add-genesis-account "$A_E1" "$((N4_VAL_STAKE*2 + N4_DOUBLESPEND_AMT*4))$DENOM" --home "$HUB" >/dev/null
"$GAIAD" genesis add-genesis-account "$A_E2" "$((N4_VAL_STAKE*2))$DENOM" --home "$HUB" >/dev/null
"$GAIAD" genesis add-genesis-account "$A_H1" "$((N4_VAL_STAKE*2))$DENOM" --home "$HUB" >/dev/null
"$GAIAD" genesis add-genesis-account "$A_H2" "$((N4_VAL_STAKE*2))$DENOM" --home "$HUB" >/dev/null

G="$HUB/config/genesis.json"
log "[N4] params: bond_denom / unbonding=$N4_UNBONDING / evidence_age=$N4_EVIDENCE_AGE / slash=$SLASH_DOUBLE_SIGN"
json_edit "$G" ".app_state.staking.params.bond_denom = \"$DENOM\""
json_edit "$G" ".app_state.staking.params.unbonding_time = \"$N4_UNBONDING\""
json_edit "$G" ".app_state.slashing.params.slash_fraction_double_sign = \"$SLASH_DOUBLE_SIGN\""
# evidence params: .consensus.params.evidence (v0.50) or .consensus_params.evidence (older)
if "$JQ" -e '.consensus.params.evidence' "$G" >/dev/null 2>&1; then EVP=".consensus.params.evidence";
elif "$JQ" -e '.consensus_params.evidence' "$G" >/dev/null 2>&1; then EVP=".consensus_params.evidence";
else die "cannot locate evidence params in genesis (check gaiad version)"; fi
json_edit "$G" "$EVP.max_age_duration = \"$(( ${N4_EVIDENCE_AGE%s} * 1000000000 ))\""   # ns
json_edit "$G" "$EVP.max_age_num_blocks = \"$N4_EVIDENCE_NUMBLOCKS\""
# feemarket: point at our denom, tiny-positive base price, disabled (same as arm A/C)
if "$JQ" -e '.app_state.feemarket.params' "$G" >/dev/null 2>&1; then
  json_edit "$G" ".app_state.feemarket.params.fee_denom = \"$DENOM\""
  json_edit "$G" ".app_state.feemarket.params.min_base_gas_price = \"0.000000000000000001\""
  json_edit "$G" ".app_state.feemarket.params.enabled = false"
  json_edit "$G" ".app_state.feemarket.state.base_gas_price = \"0.000000000000000001\""
fi

# 4 gentxs (equal self-bond) against the SAME funded genesis, collected on the hub.
log "[N4] gentx e1,e2,h1,h2 (equal power 25% each)"
cp "$G" "$H_E2A/config/genesis.json"; cp "$G" "$H_H1/config/genesis.json"; cp "$G" "$H_H2/config/genesis.json"
"$GAIAD" genesis gentx e1 "$N4_VAL_STAKE$DENOM" --chain-id "$CHAIN" "${KR[@]}" --home "$H_E1A" --ip 127.0.0.1 >/dev/null 2>&1
"$GAIAD" genesis gentx e2 "$N4_VAL_STAKE$DENOM" --chain-id "$CHAIN" "${KR[@]}" --home "$H_E2A" --ip 127.0.0.1 >/dev/null 2>&1
"$GAIAD" genesis gentx h1 "$N4_VAL_STAKE$DENOM" --chain-id "$CHAIN" "${KR[@]}" --home "$H_H1"  --ip 127.0.0.1 >/dev/null 2>&1
"$GAIAD" genesis gentx h2 "$N4_VAL_STAKE$DENOM" --chain-id "$CHAIN" "${KR[@]}" --home "$H_H2"  --ip 127.0.0.1 >/dev/null 2>&1
cp "$H_E2A"/config/gentx/*.json "$HUB"/config/gentx/
cp "$H_H1"/config/gentx/*.json  "$HUB"/config/gentx/
cp "$H_H2"/config/gentx/*.json  "$HUB"/config/gentx/
"$GAIAD" genesis collect-gentxs --home "$HUB" >/dev/null 2>&1
"$GAIAD" genesis validate-genesis --home "$HUB" >/dev/null 2>&1 || log "WARN: validate-genesis complained"

# clone e1a -> e1b and e2a -> e2b: init a CLEAN home FIRST (fresh node_key +
# priv_validator_state), THEN graft the genesis and the SHARED consensus key.
log "[N4] clone e1a->e1b, e2a->e2b (two-nodes-one-key x2, fresh node_key each)"
"$GAIAD" init e1b --chain-id "$CHAIN" --home "$H_E1B" --overwrite >/dev/null 2>&1
"$GAIAD" init e2b --chain-id "$CHAIN" --home "$H_E2B" --overwrite >/dev/null 2>&1
for h in "$H_E1A" "$H_E2A" "$H_H1" "$H_E1B" "$H_E2B" "$H_H2"; do
  cp "$HUB/config/genesis.json" "$h/config/genesis.json"
done
cp "$H_E1A/config/priv_validator_key.json" "$H_E1B/config/priv_validator_key.json"   # SAME key as e1a
cp "$H_E2A/config/priv_validator_key.json" "$H_E2B/config/priv_validator_key.json"   # SAME key as e2a
printf '{"height":"0","round":0,"step":0}' > "$H_E1B/data/priv_validator_state.json"
printf '{"height":"0","round":0,"step":0}' > "$H_E2B/data/priv_validator_state.json"

# node ids for partition-internal peering
id() { "$GAIAD" comet show-node-id --home "$1" 2>/dev/null || "$GAIAD" tendermint show-node-id --home "$1"; }
ID_E1A="$(id "$H_E1A")"; ID_E2A="$(id "$H_E2A")"; ID_H1="$(id "$H_H1")"
ID_E1B="$(id "$H_E1B")"; ID_E2B="$(id "$H_E2B")"; ID_H2="$(id "$H_H2")"
P_E1A="$ID_E1A@127.0.0.1:$P_E1A_P2P"; P_E2A="$ID_E2A@127.0.0.1:$P_E2A_P2P"; P_H1p="$ID_H1@127.0.0.1:$P_H1_P2P"
P_E1B="$ID_E1B@127.0.0.1:$P_E1B_P2P"; P_E2B="$ID_E2B@127.0.0.1:$P_E2B_P2P"; P_H2p="$ID_H2@127.0.0.1:$P_H2_P2P"

# common config: bind ports, INTRA-partition peers only (the split), dsc=0, fast
# blocks, keep state (pruning=nothing), tx index on, dup ips, gRPC/API off.
cfg() { # cfg <home> <rpc> <p2p> <peers> <commit>
  local home="$1" rpc="$2" p2p="$3" peers="$4" tc="$5"
  local c="$home/config/config.toml" a="$home/config/app.toml"
  sed -i \
    -e "s#^laddr = \"tcp://127.0.0.1:26657\"#laddr = \"tcp://0.0.0.0:$rpc\"#" \
    -e "s#^laddr = \"tcp://0.0.0.0:26656\"#laddr = \"tcp://0.0.0.0:$p2p\"#" \
    -e "s#^persistent_peers = \"\"#persistent_peers = \"$peers\"#" \
    -e "s#^allow_duplicate_ip = false#allow_duplicate_ip = true#" \
    -e "s#^addr_book_strict = true#addr_book_strict = false#" \
    -e "s#^double_sign_check_height = .*#double_sign_check_height = 0#" \
    -e "s#^timeout_commit = \"5s\"#timeout_commit = \"$tc\"#" \
    -e "s#^indexer = \"null\"#indexer = \"kv\"#" \
    "$c"
  sed -i -e "s#^pruning = \"default\"#pruning = \"nothing\"#" \
         -e "s#^minimum-gas-prices = \"\"#minimum-gas-prices = \"0$DENOM\"#" \
         -e "s#^enable = true#enable = false#" "$a"
}
# partition A members peer with the other two A members; B likewise. NO cross-partition
# peer here -- that is the network split. run_committee.sh adds cross peers to HEAL.
cfg "$H_E1A" "$P_E1A_RPC" "$P_E1A_P2P" "$P_E2A,$P_H1p"  "$N4_TIMEOUT_COMMIT"
cfg "$H_E2A" "$P_E2A_RPC" "$P_E2A_P2P" "$P_E1A,$P_H1p"  "$N4_TIMEOUT_COMMIT"
cfg "$H_H1"  "$P_H1_RPC"  "$P_H1_P2P"  "$P_E1A,$P_E2A"  "$N4_TIMEOUT_COMMIT"
cfg "$H_E1B" "$P_E1B_RPC" "$P_E1B_P2P" "$P_E2B,$P_H2p"  "$N4_TIMEOUT_COMMIT"
cfg "$H_E2B" "$P_E2B_RPC" "$P_E2B_P2P" "$P_E1B,$P_H2p"  "$N4_TIMEOUT_COMMIT"
cfg "$H_H2"  "$P_H2_RPC"  "$P_H2_P2P"  "$P_E1B,$P_E2B"  "$N4_TIMEOUT_COMMIT"

# record the cross-partition peer strings so run_committee.sh can heal by appending.
{
  echo "CHAIN=$CHAIN"
  echo "A_PEERS=$P_E1A,$P_E2A,$P_H1p"
  echo "B_PEERS=$P_E1B,$P_E2B,$P_H2p"
  echo "ACCT_E1=$A_E1"
} > "$WORK/.committee"
echo "$CHAIN" > "$WORK/.chain"
log "[N4] genesis ready under $WORK (e1,e2 equivocators; h1|h2 split; partitions isolated)"
