# 4 — (Optional, full rigor) the private-devnet arms

**Why only you:** standing up real client binaries / a private devnet needs Docker,
disk, and infra an offline assistant can't provision. Skip this for the
minimum-viable result; do it for the strongest version of the paper.

The runnable `shadow` backend already stands in for these (it produces the paired
episodes, `q_attack`, and `T_acc^hi`). These tasks replace simulation with the real
code paths.

## 4a. Native-IBC negative control (real cross-shard hop)
- [x] **Done** via a real *public* IBC channel (Cosmos Hub→Osmosis): `python collect_ibc_public.py`
      auto-discovers recent matched packets read-only and writes
      `results/measured/ibc-cosmoshub-osmosis-negative.jsonl` (median `T_settle`≈12 s, estimates
      **RULED_OUT**). This fills `\ArtifactTsettleIBC`. Disclosed in the paper as a deviation from
      the pre-registered self-run two-zone devnet.
- [ ] *Optional stronger version:* reproduce on a self-run two-zone devnet — spin up two
      CometBFT/Cosmos-SDK zones + a Hermes/`rly` relayer, open a channel, send a few packets, find
      the `send_packet`/`recv_packet` heights, set `rq8.endpoints.ibc.*`, and run
      `python measure_all.py --only ibc` (writes `ibc-devnet-negative.jsonl`).

## 4b. Real-binary equivocation backend → q_attack, T_acc^hi on real code
- [ ] Genesis a single-chain localnet with the target's mainnet params
      (`UnbondingTime`, `evidence.max_age_duration`); chain-id must be in
      `livemeasure.ALLOWED_EQUIVOCATION_CHAINS` (extend the allowlist for your id).
- [ ] Run **two nodes sharing one consensus key** with `double_sign_check_height=0`
      so they double-sign (the documented operator footgun — no exploit).
- [ ] Implement the body of `livemeasure._equivocation_rpc` to drive episodes and read
      `/block`, `/block_results`, `/consensus_params` via the existing `cosmos_rpc`
      parsers (the recipe is in that function's docstring).
- [ ] For `T_acc^hi`: withhold/delay evidence gossip and eclipse the reporter to
      protocol tolerance.
- **Done when:** `python collect_devnet.py --backend rpc --chain-id <localnet>` yields
      real-code paired episodes; the shadow numbers are corroborated.

## Safety
The equivocation leg runs **only** on a private chain-id in the allowlist; the gate
refuses any mainnet/shared id. Never run this against a shared testnet or mainnet.

---
**Next:** [5-finalize-paper.md](5-finalize-paper.md).
