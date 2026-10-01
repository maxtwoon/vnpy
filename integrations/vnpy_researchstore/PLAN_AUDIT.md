# Claude Code plan audit

Session: 30c8e062-f2aa-42a3-9eb0-9b7ba03dc88a

I've completed the read-only audit. The plan file write tool isn't available in this session, so here is the full audit for the coordinator to save directly.

---

# Independent audit — STORE-20260916 execution contract v0.1 (`vnpy_researchstore/IMPLEMENTATION_PLAN.md`)

Audited by: Claude Code, read-only, as the auditor explicitly named in the plan's own "Authority and scope" section. No files edited, no code executed, no credentials touched. Evidence below cites current repo state (`D:\repo\vnpy`) as of 2026-09-16.

## Blocking issues (must be corrected before Kimi/OpenCode start development)

**B1. Recorder shutdown ordering is ambiguous and, read literally, causes the exact silent data loss the plan forbids elsewhere.**
`vnpy/event/engine.py:55-64,97-103` shows `EventEngine.stop()` sets `_active=False` and joins the thread, but `_run()`'s loop only rechecks `_active` *after* finishing whatever `queue.get()` call is in flight — it never drains a backlog. Anything still queued when `_active` flips is discarded, not delivered. `MainEngine.close()` (`vnpy/trader/engine.py:310-319`) calls `event_engine.stop()` as its literal first statement, before any engine's own `close()` runs.
The plan's Recording→Shutdown paragraph lists these two facts in this order: "existing MainEngine.close stops EventEngine first. Local RecordingMainEngine override issues RecorderStopBarrier while event thread active." Read in that order, a developer could plausibly call `super().close()` (which stops the event engine immediately) and only *then* try to fix a cutoff — at which point the queue has already been discarded and the "last accepted seq" is no longer recoverable. That directly contradicts the plan's own "no silent drop" and "CLOSED only committed==accepted" guarantees.
**Fix required:** state explicitly, as a hard ordering requirement, that `RecordingMainEngine.close()` must (1) put the `RecorderStopBarrier` event and unregister recorder callbacks **while the base event engine is still active**, (2) block/poll until the writer thread reports committed==accepted for that barrier's cutoff (10s timeout → `STOP_FAILED`), and only then (3) call `super().close()` / let `event_engine.stop()` run. This must be unambiguous in the contract text, not left to be inferred from undocumented event-engine internals.

**B2. AlphaLab's native contract is inclusive-end; the plan only assigns the inclusive→half-open conversion duty to the `Database(BaseDatabase)` bridge, not to `ResearchAlphaLab`.**
`vnpy/alpha/lab.py:130` filters with `(pl.col("datetime") >= start) & (pl.col("datetime") <= end)` — confirmed inclusive. `vnpy/alpha/strategy/backtesting.py:130,443` call `self.lab.load_bar_data(vt_symbol, self.interval, self.start, self.end)` with `self.end` defaulting to `datetime.now()` or an explicit boundary that routinely lands on a real bar timestamp (daily bars especially). The plan's `reader.bars/ticks` contract is explicitly half-open `[start, end)`. The plan's WP07 paragraph states the inclusive→half-open bridging rule only for the native `Database(BaseDatabase)` class and says nothing about `ResearchAlphaLab.load_bar_data`/`load_bar_df`, which overrides the *same* inclusive-end AlphaLab methods. Implemented literally as scoped, `ResearchAlphaLab` would pass its inclusive `end` straight into the half-open store reader and silently drop the final bar whenever `end` coincides with a real timestamp — exactly the kind of silent truncation the plan is otherwise careful to prohibit.
**Fix required:** extend the same inclusive-end→half-open conversion requirement explicitly to the `ResearchAlphaLab` paragraph (both `load_bar_data` and `load_bar_df`).

**B3. Recording-session recovery/sealing has no named entry point in the Public API or CLI, so WP08/WP09 have nothing concrete to implement or test against.**
Core contracts §Public API lists exactly one `recover(root, batch_id?) -> RecoveryReport`, scoped by the Publishing paragraph to import-batch recovery. The CLI verb list repeats the same single `recover`. But §Recording defines a materially different lifecycle — unclosed-session `UNCLEAN_END` replay with predecessor linking, plus a separate "sealing" step with its own idempotency key (`session+watermark range+transform`) that publishes final files. WP09 is titled "aggregation/sealing" as its own work package, yet the contract names no function or CLI verb for it. The Required-tests list even separates "shutdown barrier," "killed-process recovery," and "replay deterministic" from the batch-recovery tests, confirming this is meant to be a distinct mechanism.
**Fix required:** add explicit Public API and CLI entries (e.g. `recover_session(root, session_id?) -> SessionRecoveryReport` and `seal(SealRequest) -> SealReceipt`, plus corresponding `qstore` verbs) distinct from the import-batch `recover`/`freeze` pair.

## Nonblocking improvements

- **N1.** `integrations/vnpy_datasource/vnpy_datasource/__pycache__/` contains both `cpython-313` and `cpython-314` compiled artifacts, while the plan and existing README both assert Studio is Python 3.13 only. Confirm which interpreter(s) actually ran this code before WP00 records a baseline.
- **N2.** `BaseDatabase.get_bar_overview()` has no stated behavior for a dataset that only has 5m/15m bars (Interval enum has no such members, per `vnpy/trader/constant.py:152-160`). State explicitly whether such partitions are omitted from the native overview.
- **N3.** `freeze` reads multiple datasets' heads into one snapshot manifest, but no read-consistency scope is defined across datasets (only single-dataset CAS is specified for publish). State either "freeze reads all target heads in one short read transaction" or "no concurrent import during freeze," so it's intentional rather than accidental.
- **N4.** `.coordination/claude-plan-audit.jsonl` (~305KB) is a stale Claude Code CLI session transcript (`rate_limit_event`, `out_of_credits`), not authored guidance or a completed prior audit — recommend the coordinator delete or relabel it.
- **N5.** Confirm `integrations/vnpy_datasource` is actually untracked (as the plan asserts) with `git status --porcelain` before WP00 "baselines" it.

## What checks out (spot-verified, no changes needed)

- `_normalized_rows()`/`to_bars()` do turn missing turnover into `0.0` (`storage.py:50-68`) — bypassing them for `target=store` is correct and necessary.
- `MainEngine.close()` really does stop `EventEngine` before closing engines — matches the plan's premise (ordering gap addressed in B1).
- `Interval` enum has no 5m/15m members — already a load-bearing, shipped constraint in the existing `vnpy_datasource` README, so the plan is inheriting an established convention, not inventing one.
- The cited `peewee`/`empyrical-reloaded`/`vnpy_sqlite` version conflict matches the already-resolved pin in `requirements-studio-alpha.txt`.
- `AlphaLab.load_bar_data`/`load_bar_df` already restrict to `DAILY`/`MINUTE` only — `ResearchAlphaLab` overriding the same methods with the same restriction is consistent with the existing class shape.
- `research_store`/`vnpy_researchstore` packages don't exist yet (only `IMPLEMENTATION_PLAN.md`/`TASKS.md` present) — confirms this is genuinely pre-implementation.

## Scope compliance

No enterprise infrastructure demanded; no reopening of archived Chan/ETF work. Nothing in the plan requires infrastructure disproportionate to a personal single-machine research setup once B1–B3 are corrected.

## Verdict

**ACCEPT_WITH_REQUIRED_CHANGES.**

The plan is detailed and internally coherent on almost every axis, and correctly inherits several already-battle-tested constraints from the existing `vnpy_datasource` integration. It should not be rewritten. But B1–B3 are concrete, evidence-backed gaps that would cause silent data loss (B1), silent bar truncation (B2), or an unimplementable/untestable work package (B3) if left for developers to resolve on their own. Incorporate the three corrections above, then development may start.
