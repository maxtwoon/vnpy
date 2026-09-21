"""Synthetic offline demo: seal → freeze → query.

Creates a temporary store, records synthetic tick events into a journal
session, seals the committed range, freezes a snapshot over the published
dataset, and queries it back through the public reader API. Prints evidence
IDs and row counts.

Run from package root:
    .venv/Scripts/python.exe demo_seal_freeze_query.py
"""

from __future__ import annotations

import tempfile
import time
from pathlib import Path

from research_store import (
    AssetClass,
    SealRequest,
    Selection,
    SnapshotRequest,
    freeze,
    init_store,
    open_snapshot,
    open_store,
    plan_seal,
    seal,
)
from research_store.journal import create_session
from research_store.journal_models import JournalEvent

BASE = 1_700_000_000_000_000_000
NS_MINUTE = 60 * 1_000_000_000
NS_30S = 30 * 1_000_000_000


def make_tick(seq: int, ts_ns: int, price: float, volume: float) -> JournalEvent:
    return JournalEvent(
        kind="tick",
        instrument="IF2403.CFFEX",
        event_ts_ns=ts_ns,
        source_event_id=f"ctp:{seq}",
        payload={"last_price": price, "volume": volume, "turnover": price * volume},
    )


def drain(session, n: int, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if session.status().committed_seq >= n:
            return
        time.sleep(0.01)
    raise AssertionError(f"committed_seq did not reach {n}: {session.status()}")


def main() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="rs-demo-"))
    store_root = tmp / "store"
    init_store(store_root)
    store = open_store(store_root)

    # ── Record 6 ticks across 3 minutes ──────────────────────────────
    # Typed source semantics (F4): "<kind>:<name>[@<version>]" declares the
    # asset class the sealer will require; volume is contracts for futures.
    session = create_session(store, "futures:demo-synthetic@v1", "Asia/Shanghai")
    session_id = session.session_id
    print(f"session created: {session_id}")

    for i in range(6):
        ts = BASE + i * NS_30S
        session.admit(make_tick(i + 1, ts, 3800.0 + i, 100 + i * 10))
    drain(session, 6)

    result = session.close_at_cutoff(timeout=5.0)
    print(f"close_at_cutoff: state={result.state.value}, "
          f"accepted={result.accepted_seq}, committed={result.committed_seq}")
    session.close()

    # ── Seal the committed range ─────────────────────────────────────
    req = SealRequest(
        session_id=session_id,
        committed_seq_start=1,
        committed_seq_end=6,
        transform_version="agg-v1",
        source_spec="futures:demo-synthetic@v1",
        calendar_spec="Asia/Shanghai",
        asset_class=AssetClass.FUTURES,
        volume_unit="contracts",
        turnover_unit="CNY",
    )
    plan = plan_seal(store, req)
    print(f"\nplan_seal: event_count={plan.event_count}, "
          f"range=[{plan.committed_seq_start}, {plan.committed_seq_end}], "
          f"watermark={plan.committed_watermark}")

    receipt = seal(store, req)
    print("seal receipt:")
    print(f"  seal_id       = {receipt.seal_id}")
    print(f"  dataset_id    = {receipt.dataset_id}")
    print(f"  input_events  = {receipt.input_events}")
    print(f"  accepted_rows = {receipt.accepted_rows}")
    print(f"  partitions    = {receipt.partitions}")
    print(f"  idempotent    = {receipt.idempotent_replay}")
    print(f"  detail        = {receipt.detail}")

    # Idempotent replay: same request → same identity.
    receipt2 = seal(store, req)
    print(f"\nidempotent replay: seal_id={receipt2.seal_id}, "
          f"idempotent={receipt2.idempotent_replay}, "
          f"detail={receipt2.detail}")

    # ── Freeze a snapshot over the sealed dataset ────────────────────
    snap_req = SnapshotRequest(selections=(Selection(receipt.dataset_id, "*"),))
    snap = freeze(store, snap_req)
    print(f"\nfreeze: snapshot_id={snap.snapshot_id}, "
          f"datasets={snap.datasets}")

    # ── Query back through the public reader API ─────────────────────
    with open_snapshot(store, snap.snapshot_id) as reader:
        tick_rows = [
            r for b in reader.ticks(receipt.dataset_id, required_fields=())
            for r in b.to_pylist()
        ]
    print(f"\nquery: {len(tick_rows)} tick rows")
    if tick_rows:
        print(f"first row keys: {sorted(tick_rows[0].keys())}")
        for r in tick_rows[:3]:
            print(f"  session={r.get('session_id')} seq={r.get('seq')} "
                  f"last_price={r.get('last_price')}")

    # ── Recovery: non-existent session raises typed error ────────────
    from research_store import SessionRecoveryError, recover_session
    try:
        recover_session(store, "no-such-session")
    except SessionRecoveryError as exc:
        print(f"\nrecover_session typed error (expected): {exc}")

    store.close()
    print(f"\nstore root: {store_root}")


if __name__ == "__main__":
    main()
