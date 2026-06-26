r"""RQ8 live-measurement collectors (NETWORK-TOUCHING -- quarantined skeleton).

THIS MODULE IS DELIBERATELY NOT IMPORTED BY ``run_all.py``. The reproducible
paper path (run_all -> plot_figures -> make_tables) must stay network-free and
seeded. This module is run *separately* by the RA to collect real measurements
into ``results/measured/<path>.jsonl`` using the extended ``testbed.run_round``
schema, after which the network-free ``estimate.py`` consumes the committed
JSONL on the reproducible path.

Everything here is a scaffold with the exact record schema, adapter signatures,
and the safety rails fixed by ``PREREGISTRATION-rq8.md``. The body of each
collector is left as a clearly-marked TODO because it requires real
infrastructure (an archive node, an indexer key, a private devnet); the *schema*
and the *ethical gates* are concrete so the collected data drops straight into
``estimate.py`` with zero glue.

SAFETY RAILS (enforced here, not just documented):
  * ``assert_localnet_only`` GATES every equivocation-inducing call to a private
    chain-id; it raises on any mainnet/shared-testnet chain-id. The bribery /
    equivocation leg is NEVER executed on a shared network.
  * All mainnet adapters are READ-ONLY (query public/archived state only).
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path

# Chain-ids on which inducing equivocation is permitted (private/isolated only).
# Extend with your own localnet/shadow-fork ids. Mainnet/shared-testnet ids must
# NEVER appear here.
ALLOWED_EQUIVOCATION_CHAINS = {
    "shardbribe-localnet-1",
    "fastexit-devnet-positive",
    "ibc-devnet-zone-a",
    "ibc-devnet-zone-b",
}
FORBIDDEN_SUBSTRINGS = ("cosmoshub", "mainnet", "osmosis-1", "theta-testnet",
                        "polkadot", "ethereum", "mainnet-beta")

# Some public RPCs/indexers 403 a bare urllib request; send a normal User-Agent.
_USER_AGENT = "shardbribe-rq8-collector/1.0 (read-only measurement)"


def assert_localnet_only(chain_id: str) -> None:
    """Hard gate: equivocation-inducing code may only run on a private chain-id."""
    cid = (chain_id or "").lower()
    if chain_id not in ALLOWED_EQUIVOCATION_CHAINS or any(s in cid for s in FORBIDDEN_SUBSTRINGS):
        raise RuntimeError(
            f"REFUSING to induce equivocation on chain-id {chain_id!r}: not in the "
            f"private-localnet allowlist. The attack leg is never run on a shared network.")


# --------------------------------------------------------------------------
# extended record schema (superset of testbed.run_round; estimate.py consumes it)
# --------------------------------------------------------------------------
@dataclass
class MeasuredRecord:
    # --- existing testbed keys (verbatim) ---
    t_certA: float | None = None
    t_certB: float | None = None
    t_fork: float | None = None
    t_detect: float | None = None
    T_settle: float | None = None       # ms; dest receipt + withdrawal-beyond-clawback
    T_acc: float | None = None          # ms; observe+propagate+enforce+revert
    fork_formed: bool = True
    # --- q-arm ---
    t_infraction: float | None = None
    t_evidence_committed: float | None = None
    t_slash_effective: float | None = None
    t_withdraw_unslashable: float | None = None     # TRUE unslashable deadline
    evidence_expiry_deadline: float | None = None   # MaxAgeDuration/MaxAgeNumBlocks horizon
    # --- settlement legs ---
    t_src_cert: float | None = None
    t_dst_receipt: float | None = None              # user leg (the realized V)
    t_withdraw_final: float | None = None           # solver leg (clawback-gated)
    # --- T_acc decomposition + bound label ---
    t_propagate: float | None = None
    t_enforce: float | None = None
    t_revert: float | None = None                   # NA on deterministic-finality chains
    tacc_bound: str = "lo"                          # "lo" cooperative | "hi" adversarial
    # --- provenance ---
    src_chain: str = ""
    dst_chain: str = ""
    height: int | None = None
    block_time: float | None = None
    source: str = ""                                # rpc | indexer | devnet | corpus
    measurement_resolution_ms: float | None = None  # block-time quantization
    structurally_gated: bool = False
    reorg_survived: bool | None = None              # fill settled despite a source reorg
    solver_repaid: bool | None = None               # solver leg clawback landed
    # --- arm C (real unbond, observed completion) ---
    t_unbond_complete: float | None = None          # observed unbonding maturity (ms)
    unbond_caught: bool | None = None               # slash reached the exiting stake (clawback)

    def to_dict(self) -> dict:
        return asdict(self)


def write_jsonl(records: list, out: Path) -> Path:
    """Write records + a sidecar content hash for provenance/reproducibility."""
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = "\n".join(json.dumps(r.to_dict() if isinstance(r, MeasuredRecord) else r,
                                   sort_keys=True) for r in records)
    out.write_text(payload + "\n")
    digest = hashlib.sha256(payload.encode()).hexdigest()
    out.with_suffix(".sha256").write_text(digest + "\n")
    return out


# --------------------------------------------------------------------------
# READ-ONLY mainnet/archive adapters (passive arms)
# --------------------------------------------------------------------------
# ---- pure parsers (offline-testable; no network) -------------------------
def parse_rfc3339_ms(s: str) -> float:
    """CometBFT RFC3339 (nanosecond) timestamp -> epoch milliseconds (UTC).
    Truncates sub-microsecond digits that datetime cannot parse."""
    from datetime import datetime, timezone
    s = s.strip().replace("Z", "+00:00")
    if "." in s:
        head, frac = s.split(".", 1)
        tz = ""
        for sep in ("+", "-"):
            if sep in frac:
                frac, tz = frac.split(sep, 1)
                tz = sep + tz
                break
        frac = frac[:6]                       # microseconds max
        s = f"{head}.{frac}{tz}"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp() * 1000.0


def parse_block_time_ms(block_json: dict) -> float:
    return parse_rfc3339_ms(block_json["result"]["block"]["header"]["time"])


def parse_duplicate_vote_evidence(block_json: dict) -> list:
    """Extract DuplicateVoteEvidence from a /block response -> list of dicts with
    the consensus validator address and the infraction time."""
    ev_container = (block_json.get("result", {}).get("block", {})
                    .get("evidence", {}) or {})
    items = ev_container.get("evidence", []) or []
    out = []
    for ev in items:
        val = ev.get("value", ev)
        vote_a = val.get("vote_a") or val.get("VoteA") or {}
        ts = (val.get("timestamp") or val.get("Timestamp")
              or vote_a.get("timestamp"))
        addr = (vote_a.get("validator_address")
                or val.get("validator_address"))
        if ts is None:
            continue
        out.append({"validator_address": addr,
                    "t_infraction": parse_rfc3339_ms(ts),
                    "total_voting_power": val.get("total_voting_power"),
                    "validator_power": val.get("validator_power")})
    return out


def parse_slash_events(block_results_json: dict) -> list:
    """Slash/tombstone events from a /block_results response."""
    res = block_results_json.get("result", {})
    buckets = (res.get("finalize_block_events")
               or (res.get("begin_block_events", []) + res.get("end_block_events", [])))
    out = []
    for ev in buckets or []:
        if any(tag in ev.get("type", "") for tag in ("slash", "tombstone", "liveness")):
            attrs = {a.get("key"): a.get("value") for a in ev.get("attributes", [])}
            out.append({"type": ev["type"], "attributes": attrs})
    return out


def evidence_expiry_ms(consensus_params_json: dict) -> float:
    """Evidence-age horizon (the TRUE unslashable deadline) in ms, from
    consensus params MaxAgeDuration (nanoseconds)."""
    ev = consensus_params_json["result"]["consensus_params"]["evidence"]
    return float(ev["max_age_duration"]) / 1e6     # ns -> ms


def build_incident_record(evidence: dict, t_evidence_committed: float,
                          t_slash_effective: float, expiry_ms: float,
                          *, block_interval_ms: float, src_chain: str,
                          source: str = "rpc") -> MeasuredRecord:
    """Assemble one passive q_max/T_acc^lo incident into a MeasuredRecord.
    T_acc^lo = enforce - infraction (cooperative detection).  The unslashable
    deadline used for q is the EVIDENCE-EXPIRY horizon, not unbonding (T1)."""
    t_inf = evidence["t_infraction"]
    deadline = t_inf + expiry_ms
    return MeasuredRecord(
        t_infraction=t_inf,
        t_evidence_committed=t_evidence_committed,
        t_slash_effective=t_slash_effective,
        t_withdraw_unslashable=deadline,          # estimate.py: q = Pr[t_slash<deadline]
        evidence_expiry_deadline=deadline,
        t_detect=t_evidence_committed,
        T_acc=(t_slash_effective - t_inf) if t_slash_effective else None,
        t_revert=None,                            # NA on deterministic finality
        tacc_bound="lo",                          # cooperative detection
        fork_formed=True,
        src_chain=src_chain, source=source,
        measurement_resolution_ms=block_interval_ms,
        structurally_gated=True)                  # native IBC path is finality-gated


# ---- network orchestration (READ-ONLY; self-run archive node preferred) ----
def _rpc_get(base_url: str, path: str, params: dict | None = None,
             timeout: float = 20.0) -> dict:
    """Read-only CometBFT RPC GET via the standard library (no extra deps)."""
    import urllib.parse
    import urllib.request
    url = base_url.rstrip("/") + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={
        "Accept": "application/json", "User-Agent": _USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:   # nosec: read-only public RPC
        return json.loads(resp.read().decode())


def cosmos_rpc(rpc_url: str, evidence_heights, *, slash_window: int = 4,
               block_interval_ms: float = 6000.0, src_chain: str = "cosmoshub-4",
               min_delta_blocks: float = 2.0) -> list:
    """PASSIVE q_max + T_acc^lo from real CometBFT DuplicateVoteEvidence (read-only).

    `evidence_heights` are heights known (from an indexer / block_search) to carry
    DuplicateVoteEvidence. For each: read /block (infraction time + carrying-block
    time), scan the next `slash_window` blocks' /block_results for the slash event,
    and read /consensus_params for the evidence-expiry deadline. Deltas below
    `min_delta_blocks` block intervals are dropped (block-time quantization, T10).
    Returns MeasuredRecord list ready for estimate.estimate_path.
    """
    cp = _rpc_get(rpc_url, "/consensus_params")
    expiry = evidence_expiry_ms(cp)
    records = []
    for h in evidence_heights:
        blk = _rpc_get(rpc_url, "/block", {"height": h})
        evs = parse_duplicate_vote_evidence(blk)
        if not evs:
            continue
        t_committed = parse_block_time_ms(blk)
        t_slash = None
        for dh in range(0, slash_window + 1):
            br = _rpc_get(rpc_url, "/block_results", {"height": h + dh})
            if parse_slash_events(br):
                t_slash = parse_block_time_ms(_rpc_get(rpc_url, "/block",
                                                       {"height": h + dh}))
                break
        for ev in evs:
            rec = build_incident_record(
                ev, t_committed, t_slash, expiry,
                block_interval_ms=block_interval_ms, src_chain=src_chain)
            if rec.T_acc is not None and rec.T_acc < min_delta_blocks * block_interval_ms:
                continue                          # below resolution -> drop
            records.append(rec)
    return records


def _maybe_b64(x):
    """CometBFT <=0.34 base64-encodes event attribute keys/values; >=0.37 uses
    plaintext. Decode only strings that are unambiguously base64 (pure charset,
    length multiple of 4, printable result) so plaintext tokens pass through."""
    if not isinstance(x, str):
        return x
    import base64
    import re
    if len(x) % 4 == 0 and re.fullmatch(r"[A-Za-z0-9+/]+={0,2}", x):
        try:
            d = base64.b64decode(x).decode("utf-8")
            if d.isprintable():
                return d
        except Exception:
            pass
    return x


def _coin_amount(s) -> float | None:
    """Leading integer of a coin string like '20000000uatom' -> 20000000.0."""
    if s is None:
        return None
    import re
    m = re.match(r"\s*(\d+)", str(s))
    return float(m.group(1)) if m else None


def parse_complete_unbonding(block_results_json: dict, *, validator: str | None = None,
                             delegator: str | None = None) -> list:
    """Matured unbonding-delegation completions from a /block_results response.

    The staking EndBlocker emits a ``complete_unbonding`` event with the returned
    ``amount`` when an unbonding-delegation entry matures and its tokens are paid
    back to the (now liquid, unslashable) account. On a single-equivocator localnet
    leave ``validator``/``delegator`` None to match the only unbonding in flight.
    Handles base64-encoded attributes (CometBFT <= 0.34)."""
    res = block_results_json.get("result", {})
    buckets = (res.get("finalize_block_events")
               or (res.get("begin_block_events", []) + res.get("end_block_events", [])))
    out = []
    for ev in buckets or []:
        if "complete_unbonding" not in ev.get("type", ""):
            continue
        attrs = {_maybe_b64(a.get("key")): _maybe_b64(a.get("value"))
                 for a in ev.get("attributes", [])}
        if validator and attrs.get("validator") not in (None, validator):
            continue
        if delegator and attrs.get("delegator") not in (None, delegator):
            continue
        out.append({"amount": _coin_amount(attrs.get("amount")),
                    "validator": attrs.get("validator"),
                    "delegator": attrs.get("delegator")})
    return out


def _arm_c_exit(t_inf, t_slash, h_slash, t_complete, h_complete, returned,
                unbond_amount, *, block_interval_ms: float, unbond_lead_ms: float):
    """Encode an arm-C episode's real escape/caught outcome for the frozen q rule.

    Pure (offline-tested). The equivocator unbonds part of its stake and we observe,
    on real client code, whether the slash reached that exiting stake:

      * caught (clawback): the unbonding entry still existed when the slash was
        processed (``h_slash <= h_complete`` -- evidence runs in BeginBlock, before
        the staking EndBlocker that completes the unbond in the same block), OR the
        returned amount came back reduced. The stake never became unslashable before
        the slash, so we place ``t_withdraw_unslashable`` just AFTER the slash.
      * escaped: the unbonding matured and its full amount was paid out in a strictly
        earlier block than the slash (``h_complete < h_slash``). ``t_withdraw`` is the
        real observed completion time, which precedes ``t_slash``.

    Returns ``(t_withdraw_unslashable, t_unbond_complete, caught)``; caught feeds the
    frozen estimator's ``t_slash_effective < t_withdraw_unslashable`` (= enforced) rule.
    """
    if h_complete is None:
        caught = True if h_slash is not None else None   # never matured -> still slashable
    else:
        caught = bool(
            (returned is not None and unbond_amount is not None
             and returned < unbond_amount - 1e-9)             # observed clawback
            or (h_slash is not None and h_slash <= h_complete))  # slash hit the live UBD
    if caught:
        base = t_slash if t_slash is not None else t_inf
        t_withdraw = (base if base is not None else 0.0) + block_interval_ms
    elif t_complete is not None:
        t_withdraw = t_complete                               # strictly before the slash
    else:
        t_withdraw = (t_inf or 0.0) + unbond_lead_ms          # fallback: analytic lead
    return t_withdraw, t_complete, caught


def parse_ibc_events(block_results_json: dict, event_type: str) -> list:
    """Extract IBC packet events ({sequence, channel}) of `event_type`
    (send_packet / recv_packet / acknowledge_packet) from a /block_results
    response, scanning block- and tx-level events. Handles base64 attributes."""
    res = block_results_json.get("result", {})
    out = []

    def scan(events):
        for ev in events or []:
            if ev.get("type") != event_type:
                continue
            a = {}
            for at in ev.get("attributes", []):
                a[_maybe_b64(at.get("key"))] = _maybe_b64(at.get("value"))
            seq = a.get("packet_sequence")
            if seq is not None:
                out.append({"sequence": str(seq),
                            "channel": a.get("packet_src_channel")
                            or a.get("packet_dst_channel")})
    scan(res.get("finalize_block_events"))
    scan(res.get("begin_block_events"))
    scan(res.get("end_block_events"))
    for tr in res.get("txs_results") or []:
        scan(tr.get("events"))
    return out


def correlate_ibc(sends: list, recvs: list, acks=None) -> list:
    """Correlate IBC send_packet (source) with recv_packet (dest) by
    (channel, sequence). Each item is {sequence, channel, t (ms), ...}. Native IBC
    acts only on a finalized source header, so records are structurally_gated=True
    (T_settle >= T_acc by construction): the negative control must return RULED_OUT."""
    recv_by, ack_by = {}, {}
    for r in recvs:
        recv_by[(str(r.get("channel") or ""), str(r["sequence"]))] = r
    for a in (acks or []):
        ack_by[(str(a.get("channel") or ""), str(a["sequence"]))] = a
    recs = []
    for s in sends:
        key = (str(s.get("channel") or ""), str(s["sequence"]))
        r = recv_by.get(key) or recv_by.get(("", str(s["sequence"])))
        if not r:
            continue
        t_src, t_dst = s["t"], r["t"]
        if t_dst < t_src:
            continue
        a = ack_by.get(key)
        recs.append(MeasuredRecord(
            t_src_cert=t_src, t_dst_receipt=t_dst,
            t_withdraw_final=(a["t"] if a else None),
            T_settle=t_dst - t_src, T_acc=None, fork_formed=True,
            src_chain=str(s.get("src_chain", "")), dst_chain=str(s.get("dst_chain", "")),
            source="ibc-relayer", structurally_gated=True))
    return recs


def ibc_relayer(src_rpc: str, dst_rpc: str, *, src_heights, dst_heights,
                channel: str | None = None, src_chain: str = "ibc-devnet-zone-a",
                dst_chain: str = "ibc-devnet-zone-b") -> list:
    """Native-IBC T_settle (negative control). READ-ONLY. Reads send_packet on the
    source and recv_packet/acknowledge_packet on the destination (by block height),
    correlates by packet sequence, and returns structurally-gated records. On a
    two-zone devnet supply the heights carrying the packet events (or discover them
    via block_search for 'send_packet'/'recv_packet')."""
    def collect(rpc, heights, etype, stamp_chain=False):
        items = []
        for h in heights:
            t = parse_block_time_ms(_rpc_get(rpc, "/block", {"height": h}))
            for e in parse_ibc_events(_rpc_get(rpc, "/block_results", {"height": h}), etype):
                if channel and e.get("channel") not in (None, channel):
                    continue
                e = dict(e); e["t"] = t
                if stamp_chain:
                    e["src_chain"] = src_chain; e["dst_chain"] = dst_chain
                items.append(e)
        return items
    sends = collect(src_rpc, src_heights, "send_packet", stamp_chain=True)
    recvs = collect(dst_rpc, dst_heights, "recv_packet")
    acks = collect(src_rpc, src_heights, "acknowledge_packet")
    return correlate_ibc(sends, recvs, acks)


def _sec_to_ms(ts) -> float:
    """Unix-seconds timestamp (int/str/float, subgraph-style) -> epoch ms."""
    return float(ts) * 1000.0


def _first_present(d: dict, *keys):
    for k in keys:
        if d.get(k) is not None:
            return d[k]
    return None


# ---- pure correlator (offline-testable; no network) ----------------------
def correlate_across(deposits: list, fills: list, repayments=None, *,
                     protocol: str = "across-v3") -> list:
    """Correlate bridge deposits with their fills (and optional solver repayments)
    by deposit id, producing T_settle records. The USER leg (deposit->fill) is the
    irreversible value the attacker realizes; the SOLVER leg (deposit->repayment)
    is clawback-gated. Records carry T_settle = USER leg and T_acc = None: the
    settlement marginal. (Paired p_win comes from the devnet self-fill arm.)"""
    fills_by_id: dict = {}
    for f in fills:
        did = _first_present(f, "depositId", "depositID", "deposit_id", "id")
        if did is not None:
            fills_by_id.setdefault(str(did), []).append(f)
    rep_by_id: dict = {}
    for r in (repayments or []):
        did = _first_present(r, "depositId", "depositID", "deposit_id", "id")
        if did is not None:
            rep_by_id.setdefault(str(did), []).append(r)

    def ts_of(x):
        return _sec_to_ms(_first_present(x, "timestamp", "blockTimestamp", "time"))

    recs = []
    for d in deposits:
        did = _first_present(d, "depositId", "depositID", "deposit_id", "id")
        if did is None:
            continue
        matches = fills_by_id.get(str(did))
        if not matches:
            continue
        f = min(matches, key=ts_of)                  # earliest fill
        t_src, t_dst = ts_of(d), ts_of(f)
        if t_dst < t_src:                            # implausible pairing; skip
            continue
        rep = rep_by_id.get(str(did))
        t_wd = ts_of(rep[0]) if rep else None
        recs.append(MeasuredRecord(
            t_src_cert=t_src, t_dst_receipt=t_dst, t_withdraw_final=t_wd,
            T_settle=t_dst - t_src,                  # USER leg = realized V (ms)
            T_acc=None,                              # marginal; paired in devnet arm
            fork_formed=True,
            src_chain=str(_first_present(d, "originChainId", "origin_chain", "src_chain") or protocol),
            dst_chain=str(_first_present(d, "destinationChainId", "dest_chain") or ""),
            source="graph", structurally_gated=False))
    return recs


# A best-effort paginated subgraph query; entity/field names vary by deployment,
# so verify against the live schema and override with --query if needed.
DEFAULT_ACROSS_QUERY = """
query($first:Int!,$skip:Int!){
  deposits: v3FundsDepositeds(first:$first, skip:$skip, orderBy:timestamp, orderDirection:asc){
    depositId originChainId destinationChainId timestamp amount
  }
  fills: filledV3Relays(first:$first, skip:$skip, orderBy:timestamp, orderDirection:asc){
    depositId originChainId destinationChainId timestamp
  }
}
"""


def _graphql(url: str, query: str, variables=None, timeout: float = 30.0) -> dict:
    """Read-only GraphQL POST via the standard library (no extra deps)."""
    import urllib.request
    body = json.dumps({"query": query, "variables": variables or {}}).encode()
    req = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": "application/json", "Accept": "application/json",
                 "User-Agent": _USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:   # nosec: read-only
        return json.loads(resp.read().decode())


def bridge_events(graph_url: str, *, query: str | None = None,
                  deposits_key: str = "deposits", fills_key: str = "fills",
                  repayments_key: str | None = None, page_size: int = 1000,
                  max_records: int = 20000, protocol: str = "across-v3") -> list:
    """PASSIVE T_settle (open-window target) from a fast/intent bridge subgraph.
      t_src_cert    = source deposit (e.g. Across V3FundsDeposited)
      t_dst_receipt = destination fill (FilledV3Relay) -- seconds-scale USER leg
      t_withdraw_final = solver repayment (RootBundleExecuted / DLN ClaimedUnlock)
    Returns the settlement marginal; the open-window claim rests on the user leg,
    and a paired p_win is formed later from devnet self-fill episodes (prereg 4.1).
    """
    query = query or DEFAULT_ACROSS_QUERY
    deposits, fills, repayments = [], [], []
    skip = 0
    while len(deposits) < max_records:
        resp = _graphql(graph_url, query, {"first": page_size, "skip": skip})
        if resp.get("errors"):
            raise RuntimeError(f"subgraph query error: {resp['errors']}; "
                               "check the schema and pass --query")
        data = resp.get("data") or {}
        dd = data.get(deposits_key, []) or []
        ff = data.get(fills_key, []) or []
        if not dd and not ff:
            break
        deposits += dd
        fills += ff
        if repayments_key:
            repayments += data.get(repayments_key, []) or []
        if len(dd) < page_size and len(ff) < page_size:
            break
        skip += page_size
    return correlate_across(deposits, fills, repayments or None, protocol=protocol)


def reorg_corpus(incidents: list, *, protocol: str = "reorg-natural-experiment") -> list:
    """Reorg natural-experiment (T6): the direct 'beyond clawback' irreversibility
    test. Each incident is a deposit whose SOURCE was later reorged-out; we record
    whether the destination FILL settled anyway (user leg irreversible to the
    recipient) and whether the SOLVER repayment fired (clawback-gated solver leg).

    incident dict fields (assemble from explorers / bridge-exploit postmortems):
      chain, t_deposit_s, t_fill_s, t_repay_s(optional),
      reorged_out: bool, solver_repaid: bool(optional)
    """
    recs = []
    for it in incidents:
        t_dep = _sec_to_ms(it["t_deposit_s"]) if it.get("t_deposit_s") is not None else None
        t_fill = _sec_to_ms(it["t_fill_s"]) if it.get("t_fill_s") is not None else None
        t_rep = _sec_to_ms(it["t_repay_s"]) if it.get("t_repay_s") is not None else None
        T_settle = (t_fill - t_dep) if (t_fill is not None and t_dep is not None) else None
        reorged = bool(it.get("reorged_out"))
        recs.append(MeasuredRecord(
            t_src_cert=t_dep, t_dst_receipt=t_fill, t_withdraw_final=t_rep,
            T_settle=T_settle, T_acc=None, fork_formed=True,
            # True/False only for reorged deposits (the experiment); None otherwise.
            reorg_survived=((t_fill is not None) if reorged else None),
            solver_repaid=(bool(it.get("solver_repaid")) if "solver_repaid" in it
                           else (t_rep is not None)),
            src_chain=str(it.get("chain", protocol)), source="reorg-corpus",
            structurally_gated=False))
    return recs


def load_corpus(path: str, bool_fields=()) -> list:
    """Load a curated corpus from .json (list of dicts) or .csv (header row).
    CSV: empty -> None, ``bool_fields`` -> bool, ``t_*`` columns -> float."""
    p = Path(path)
    if p.suffix.lower() == ".json":
        data = json.loads(p.read_text())
        return data if isinstance(data, list) else data.get("incidents", [])
    import csv
    rows = []
    with open(p, newline="") as fh:
        for row in csv.DictReader(fh):
            out = {}
            for k, v in row.items():
                if v in ("", None):
                    out[k] = None
                elif k in bool_fields:
                    out[k] = str(v).strip().lower() in ("1", "true", "yes", "y")
                elif k.startswith("t_"):
                    out[k] = float(v)
                else:
                    out[k] = v
            rows.append(out)
    return rows


def load_reorg_corpus(path: str) -> list:
    """Load a curated reorg corpus (.json or .csv)."""
    return load_corpus(path, bool_fields=("reorged_out", "solver_repaid"))


def exploit_postmortem(incidents: list, *, protocol: str = "exploit-postmortem") -> list:
    """Adversarial T_settle fast-tail from bridge-exploit / intent liquidity-
    exhaustion postmortems. Each incident times value-creation -> cash-out -> any
    clawback; T_settle (cash-out minus value-creation) calibrates how FAST a real
    adversary monetizes (the honest-transfer marginal is biased slow). Marginal /
    corroborative (T_acc=None).

    incident fields: name/chain, t_value_created_s, t_cashout_s,
      t_clawback_s (optional), clawback_landed (optional bool).
    """
    recs = []
    for it in incidents:
        t_v = _sec_to_ms(it["t_value_created_s"]) if it.get("t_value_created_s") is not None else None
        t_c = _sec_to_ms(it["t_cashout_s"]) if it.get("t_cashout_s") is not None else None
        t_cb = _sec_to_ms(it["t_clawback_s"]) if it.get("t_clawback_s") is not None else None
        T_settle = (t_c - t_v) if (t_c is not None and t_v is not None) else None
        recs.append(MeasuredRecord(
            t_src_cert=t_v, t_dst_receipt=t_c, t_withdraw_final=t_cb,
            T_settle=T_settle, T_acc=None, fork_formed=True,
            solver_repaid=(bool(it.get("clawback_landed")) if "clawback_landed" in it
                           else (t_cb is not None)),
            src_chain=str(it.get("chain") or it.get("name") or protocol),
            source="exploit-postmortem", structurally_gated=False))
    return recs


def load_postmortem_corpus(path: str) -> list:
    """Load an exploit-postmortem corpus from .json or .csv (header row)."""
    return load_corpus(path, bool_fields=("clawback_landed",))


# --------------------------------------------------------------------------
# PRIVATE-DEVNET equivocation harness (q_attack, T_acc^hi) -- gated
# --------------------------------------------------------------------------
def equivocation_harness(chain_id: str, *, backend: str = "shadow",
                         episodes: int = 40, suppress_evidence: bool = False,
                         suppress_ms: float = 180_000.0,
                         unbond_lead_ms: float = 60_000.0,
                         bridge_fill_mean_ms: float = 8_000.0,
                         acc_enforce_ms: float = 260_000.0,
                         link_mean_ms: float = 80.0, N: int = 31, seed: int = 0,
                         rpc_url: str | None = None, evidence_heights=None,
                         src_chain: str | None = None,
                         block_interval_ms: float = 6000.0, slash_window: int = 8,
                         unbond_height: int | None = None,
                         unbond_amount: float | None = None,
                         unbond_watch: int = 30) -> list:
    """q_attack + adversarial T_acc^hi + paired (T_settle,T_acc) self-fill episodes
    on a PRIVATE chain ONLY. Hard-gated to the localnet allowlist.

    backend="shadow" (default, runnable): an in-process discrete-event rehearsal
    built on the validated ``testbed`` (RQ6). Each episode drives one equivocation
    round; T_settle is the bridge user-leg fill (``bridge_fill_mean_ms``), T_acc the
    source accountability (``acc_enforce_ms``, +``suppress_ms`` when the adversary
    withholds evidence -> tacc_bound='hi'). The equivocator unbonds at the infraction,
    so q_attack = Pr[slash lands before ``unbond_lead_ms``]: a short lead (fast-exit)
    yields a low q. This is the prereg's drop-in rehearsal; it emits the SAME schema
    as the real backend.

    backend="rpc" (production): drives a real cometbft two-nodes-one-key localnet and
    reads the real x/evidence -> x/slashing events via the cosmos_rpc parsers. Needs a
    running private devnet (see _equivocation_rpc).
    """
    assert_localnet_only(chain_id)     # hard refusal on any shared/mainnet chain-id
    if backend == "rpc":
        return _equivocation_rpc(
            chain_id, episodes=episodes, suppress_evidence=suppress_evidence,
            rpc_url=rpc_url, evidence_heights=evidence_heights,
            unbond_lead_ms=unbond_lead_ms, src_chain=src_chain,
            block_interval_ms=block_interval_ms, slash_window=slash_window,
            unbond_height=unbond_height, unbond_amount=unbond_amount,
            unbond_watch=unbond_watch)
    if backend != "shadow":
        raise ValueError(f"unknown backend {backend!r} (use 'shadow' or 'rpc')")

    from .testbed import TestbedParams, run_round
    p = TestbedParams(N=N, link_mean_ms=link_mean_ms,
                      enforce_delay_ms=acc_enforce_ms,
                      dest_interval_ms=bridge_fill_mean_ms, clawback_ms=0.0)
    recs = []
    for i in range(episodes):
        r = run_round(p, seed + i)
        if not r["fork_formed"]:
            continue
        sup = suppress_ms if suppress_evidence else 0.0
        t_inf = r["t_fork"]                          # conflicting cert exists (race t=0)
        t_evid = r["t_detect"] + sup
        t_slash = r["T_acc"] + sup                   # absolute slash time
        t_unsla = t_inf + unbond_lead_ms             # equivocator's stake exit
        recs.append(MeasuredRecord(
            t_certA=r["t_certA"], t_certB=r["t_certB"], t_fork=r["t_fork"],
            t_detect=t_evid, t_infraction=t_inf, t_evidence_committed=t_evid,
            t_slash_effective=t_slash, t_withdraw_unslashable=t_unsla,
            evidence_expiry_deadline=t_unsla,
            T_settle=r["T_settle"], T_acc=t_slash,
            t_revert=None, tacc_bound="hi" if suppress_evidence else "lo",
            src_chain=chain_id, source="devnet-shadow", fork_formed=True,
            measurement_resolution_ms=link_mean_ms, structurally_gated=False))
    return recs


def _equivocation_rpc(chain_id: str, *, episodes: int, suppress_evidence: bool,
                      rpc_url: str | None = None, evidence_heights=None,
                      unbond_lead_ms: float = 60_000.0, slash_window: int = 8,
                      src_chain: str | None = None,
                      block_interval_ms: float = 6000.0,
                      unbond_height: int | None = None,
                      unbond_amount: float | None = None,
                      unbond_watch: int = 30) -> list:
    """Real-client-code backend: ATTACK-CONDITIONAL q_attack + causal T_acc from a
    PRIVATE self-equivocation localnet (full recipe in artifact/LOCALNET-RQ8.md).
    Read-only over the localnet RPC; reuses the same parsers as the passive
    ``cosmos_rpc`` arm. NOT exercised by the network-free tests (needs live nodes).

    Operator-managed (Python cannot do these through the RPC alone): the
    two-nodes-one-key node setup; the per-episode double-sign trigger, unbond
    submission, and localnet reset; and (for T_acc^hi) the netem/iptables evidence
    suppression + reporter eclipse. The operator passes the infraction heights they
    triggered via ``evidence_heights``; this reads the resulting evidence/slash
    timing and assembles attack-conditional records.

    The unslashable deadline (t_withdraw_unslashable) has two regimes:

      * Arm A (no ``unbond_height``): the analytic stake exit ``t_infraction +
        unbond_lead_ms`` (= the localnet's mainnet-like UnbondingTime, e.g. 21 d).
        For arm A the slash (~1-2 blocks) trivially beats a 21 d exit, so q->1; we do
        not stage a 21 d real unbond -- the inequality is not in question.
      * Arm C (``unbond_height`` set): the OBSERVED unbonding completion. The
        equivocator submits a real ``MsgUndelegate``; we scan ``unbond_watch`` blocks
        from ``unbond_height`` for the staking ``complete_unbonding`` event and read
        the real maturity time and returned amount. ``_arm_c_exit`` then decides, from
        real client code, whether the slash reached the exiting stake (clawback) or it
        escaped, and encodes that into t_withdraw_unslashable for the frozen q rule.
        For a genuine escape the unbond must MATURE before the evidence is processed:
        on stock Cosmos an unbonding with creation_height >= infraction is clawed back,
        so stage the unbond a couple of blocks BEFORE the double-sign (run_episode.sh's
        C_UNBOND_LEAD_BLOCKS) and keep UnbondingTime < the enforcement latency.

    Differs from ``cosmos_rpc`` (passive q_max): records are not structurally gated and
    use the attacker's stake exit (above), not the evidence-expiry horizon, as the
    unslashable deadline; tacc_bound='hi' when the suppression/eclipse arm produced them.
    """
    assert_localnet_only(chain_id)            # hard refusal on any shared/mainnet id
    if not rpc_url:
        raise NotImplementedError(
            "backend='rpc' needs a running private cometbft two-nodes-one-key localnet. "
            "Pass rpc_url=http://<localnet>:26657 (and evidence_heights from the episodes "
            "you triggered), or use backend='shadow' for the in-process rehearsal. "
            "See artifact/LOCALNET-RQ8.md.")
    heights = list(evidence_heights or [])
    if not heights:
        raise ValueError(
            "backend='rpc' needs evidence_heights: the infraction heights of the "
            "self-equivocation episodes you triggered on the localnet (Python cannot "
            "trigger a double-sign through the RPC). See LOCALNET-RQ8.md arm A.")
    cp = _rpc_get(rpc_url, "/consensus_params")          # also validates reachability
    expiry = evidence_expiry_ms(cp)
    src = src_chain or chain_id
    recs = []
    for h in heights[:episodes]:
        blk = _rpc_get(rpc_url, "/block", {"height": h})
        evs = parse_duplicate_vote_evidence(blk)
        if not evs:
            continue                                     # no self-equivocation at h
        # t_infraction is the evidence's embedded vote timestamp (the block time at
        # the *infraction* height), NOT this carrying block's header time. The
        # height passed in is the block that CARRIES the evidence (== the slash
        # block); using its header time would make T_acc collapse to ~0 whenever the
        # slash lands in the same block as the evidence. This mirrors the passive
        # cosmos_rpc/build_incident_record path and reproduces the hand-run n=1
        # (infraction 163 -> slash 164 = 1325 ms).
        t_inf = min(ev["t_infraction"] for ev in evs)
        t_slash = None
        h_slash = None
        for dh in range(0, slash_window + 1):
            if parse_slash_events(_rpc_get(rpc_url, "/block_results",
                                           {"height": h + dh})):
                h_slash = h + dh
                t_slash = parse_block_time_ms(
                    _rpc_get(rpc_url, "/block", {"height": h_slash}))
                break
        # Arm C: if the equivocator submitted a real unbond, the stake exit is the
        # OBSERVED unbonding completion (real client code), not an analytic deadline.
        t_unbond_complete = None
        unbond_caught = None
        if unbond_height is not None:
            t_complete = h_complete = returned = None
            for dh in range(0, unbond_watch + 1):
                hc = unbond_height + dh
                comps = parse_complete_unbonding(
                    _rpc_get(rpc_url, "/block_results", {"height": hc}))
                if comps:
                    h_complete = hc
                    t_complete = parse_block_time_ms(
                        _rpc_get(rpc_url, "/block", {"height": hc}))
                    returned = comps[0]["amount"]
                    break
            t_withdraw, t_unbond_complete, unbond_caught = _arm_c_exit(
                t_inf, t_slash, h_slash, t_complete, h_complete, returned,
                unbond_amount, block_interval_ms=block_interval_ms,
                unbond_lead_ms=unbond_lead_ms)
        else:
            t_withdraw = t_inf + unbond_lead_ms          # arm A: analytic exit (e.g. 21 d)
        recs.append(MeasuredRecord(
            t_infraction=t_inf, t_evidence_committed=t_slash, t_detect=t_slash,
            t_slash_effective=t_slash,
            t_withdraw_unslashable=t_withdraw,
            evidence_expiry_deadline=t_inf + expiry,
            T_acc=(t_slash - t_inf) if t_slash is not None else None,
            T_settle=None,                               # q-arm; pair the value path separately
            t_revert=None, tacc_bound="hi" if suppress_evidence else "lo",
            t_unbond_complete=t_unbond_complete, unbond_caught=unbond_caught,
            src_chain=src, source="devnet-rpc", fork_formed=True,
            measurement_resolution_ms=block_interval_ms, structurally_gated=False))
    return recs


# --------------------------------------------------------------------------
# PAIRED real-client-code arm (T_settle vs T_acc on ONE episode) -- gated
# --------------------------------------------------------------------------
def assemble_paired_record(*, t_infraction, t_slash, t_src_cert_ms, t_dst_receipt_ms,
                           gated: bool, gate_depth=None, fill_amount=None,
                           src_chain: str, dst_chain: str,
                           measurement_resolution_ms: float,
                           reorg_survived: bool = True,
                           source: str = "devnet-paired-rpc") -> MeasuredRecord:
    """Assemble ONE paired real-client-code episode: a real settlement leg
    (``t_src_cert`` -> ``t_dst_receipt``, the relayer's single monotonic clock so no
    cross-chain skew, prereg T13) racing the real source accountability
    (``t_infraction`` -> ``t_slash``, source-chain block times via the same parsers as
    arm A). Pure -- offline-tested in tests/test_livemeasure_paired.py.

      T_settle = t_dst_receipt - t_src_cert   (relayer clock; sub-block)
      T_acc    = t_slash       - t_infraction (real x/evidence->x/slashing)
      episode p_win = T_settle < T_acc

    Both are DURATIONS from the same source conflicting-cert event (t=0), so the race
    is apples-to-apples even though T_settle is wall-clock and T_acc is block-time; the
    relayer-poll offset is carried in ``measurement_resolution_ms`` (T10/T13).

    The OPEN arm fills ungated (small ``gate_depth``) so T_settle << T_acc and
    ``structurally_gated`` is False -> the decision rule can return OPEN-WINDOW (and the
    rho-median CI excludes 1 from below). The GATED twin waits past the accountability
    horizon before filling (``gated=True``), so T_settle >= T_acc AND
    ``structurally_gated`` -> the decision rule returns RULED_OUT by Proposition 1: the
    LIVE demonstration of immunity-by-construction on real client code, one knob flipped.
    Evaluated against the cooperative (un-suppressed) slash, so ``tacc_bound='lo'`` --
    the conservative T_acc the prereg requires for an OPEN claim (sec 4.3)."""
    T_settle = ((t_dst_receipt_ms - t_src_cert_ms)
                if (t_dst_receipt_ms is not None and t_src_cert_ms is not None) else None)
    T_acc = ((t_slash - t_infraction)
             if (t_slash is not None and t_infraction is not None) else None)
    return MeasuredRecord(
        t_infraction=t_infraction, t_slash_effective=t_slash,
        t_evidence_committed=t_slash, t_detect=t_slash,
        t_src_cert=t_src_cert_ms, t_dst_receipt=t_dst_receipt_ms,
        t_withdraw_final=None,                # solver leg is the clawback-gated arm
        T_settle=T_settle, T_acc=T_acc,
        t_revert=None, tacc_bound="lo",       # race the COOPERATIVE slash (conservative)
        src_chain=src_chain, dst_chain=dst_chain, source=source,
        fork_formed=True,
        measurement_resolution_ms=measurement_resolution_ms,
        structurally_gated=bool(gated),       # gated twin -> RULED_OUT by Prop. 1
        reorg_survived=reorg_survived)        # user-leg fill irreversible despite source slash


def _paired_rpc(chain_id: str, *, rpc_url: str, relayer_records: list,
                gated: bool = False, src_chain: str | None = None,
                dst_chain: str = "ibc-devnet-zone-b",
                block_interval_ms: float = 1000.0, slash_window: int = 8) -> list:
    """Real-client-code PAIRED backend. For each relayer episode, read the REAL source
    slash (``T_acc``, reusing the passive parsers) and combine it with the relayer's
    REAL settlement leg (``T_settle``) via ``assemble_paired_record``. Read-only over
    the source localnet RPC; the fill itself is a real ``gaiad tx bank send`` the
    relayer already broadcast on the destination zone (localnet/relayer.sh).

    ``relayer_records``: one dict per episode, written by relayer.sh --
      {infraction_height, t_src_cert_ms, t_dst_receipt_ms, gate_depth, fill_amount,
       measurement_resolution_ms, gated(optional)}.
    Python cannot trigger a double-sign or broadcast the fill through the RPC; the
    operator/kit owns those (mirrors ``_equivocation_rpc``)."""
    assert_localnet_only(chain_id)            # hard refusal on any shared/mainnet id
    if not rpc_url:
        raise NotImplementedError(
            "backend='paired' needs the SOURCE two-nodes-one-key localnet RPC plus the "
            "relayer episode records (localnet/run_arm.sh B-open|B-gated). "
            "See artifact/LOCALNET-RQ8-PAIRED.md.")
    if not relayer_records:
        raise ValueError(
            "paired backend needs relayer_records: one per episode, written by relayer.sh "
            "(t_src_cert_ms/t_dst_receipt_ms + infraction_height). Python cannot fill the "
            "destination through the RPC. See LOCALNET-RQ8-PAIRED.md.")
    _rpc_get(rpc_url, "/consensus_params")    # validate reachability before the loop
    src = src_chain or chain_id
    recs = []
    for rr in relayer_records:
        h = int(rr["infraction_height"])
        evs = parse_duplicate_vote_evidence(_rpc_get(rpc_url, "/block", {"height": h}))
        if not evs:
            continue                          # no self-equivocation at h -> skip episode
        t_inf = min(ev["t_infraction"] for ev in evs)
        t_slash = None
        for dh in range(0, slash_window + 1):
            if parse_slash_events(_rpc_get(rpc_url, "/block_results", {"height": h + dh})):
                t_slash = parse_block_time_ms(_rpc_get(rpc_url, "/block", {"height": h + dh}))
                break
        recs.append(assemble_paired_record(
            t_infraction=t_inf, t_slash=t_slash,
            t_src_cert_ms=rr.get("t_src_cert_ms"), t_dst_receipt_ms=rr.get("t_dst_receipt_ms"),
            gated=gated or bool(rr.get("gated")), gate_depth=rr.get("gate_depth"),
            fill_amount=rr.get("fill_amount"), src_chain=src, dst_chain=dst_chain,
            measurement_resolution_ms=float(
                rr.get("measurement_resolution_ms", block_interval_ms))))
    return recs


def paired_harness(chain_id: str, *, rpc_url: str, relayer_records: list,
                   gated: bool = False, src_chain: str | None = None,
                   dst_chain: str = "ibc-devnet-zone-b",
                   block_interval_ms: float = 1000.0, slash_window: int = 8) -> list:
    """Gated entry point for the paired arm (mirrors ``equivocation_harness``)."""
    assert_localnet_only(chain_id)
    return _paired_rpc(chain_id, rpc_url=rpc_url, relayer_records=relayer_records,
                       gated=gated, src_chain=src_chain, dst_chain=dst_chain,
                       block_interval_ms=block_interval_ms, slash_window=slash_window)


if __name__ == "__main__":
    # smoke test of the safety gate + schema only (no network).
    rec = MeasuredRecord(T_settle=8200.0, T_acc=540000.0, src_chain="across-v3",
                         source="graph", tacc_bound="lo")
    p = write_jsonl([rec], Path("results/measured/_smoke.jsonl"))
    print("wrote", p)
    for cid in ("shardbribe-localnet-1", "cosmoshub-4"):
        try:
            assert_localnet_only(cid)
            print(f"  {cid}: allowed")
        except RuntimeError as ex:
            print(f"  {cid}: REFUSED -> {ex}".split(":")[0])
