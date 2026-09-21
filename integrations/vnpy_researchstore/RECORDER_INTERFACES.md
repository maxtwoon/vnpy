# Recorder interfaces — vnpy_researchstore recorder bridge (03C/03D scope)

Status: IMPLEMENTED and covered by `tests/test_recorder*.py` and
`tests/test_cli.py` (all offline/simulated). This file covers the recorder
bridge, stop-barrier engine, app facade, Qt status UI and the launcher —
including the 03D additions (typed WP09 status wiring, recovery/successor
surfacing, packaged launcher entry points, CLI recording verbs). The journal
foundation contract lives in `JOURNAL_INTERFACES.md`; the recording
journal/aggregation/sealing contract lives in `RECORDING_INTERFACES.md`; the
native snapshot consumer contract lives in `NATIVE_INTERFACES.md`.

Explicitly pending (gate, not omission):

* Final wheel/sdist noneditable E2E and final affected offline
  record/stop/recover/replay/seal/freeze/query acceptance wait for the
  released corrected recording core (02I) and stable native handoffs (06).
* The canonical `research_store.recover_session` wrapper does not yet forward
  `create_successor` / `successor_*` kwargs; until the core owner releases
  the fix, the CLI and app call the documented public implementation
  `research_store.session_recovery.recover_session` (see
  `.coordination/recorder03d-opencode-core-requests.md`). No private API is
  read anywhere.

## Package rule

`vnpy_researchstore` keeps its lazy package init: importing the package has
no vnpy/Qt side effects. All recorder modules import `vnpy` lazily or live
behind the launcher bootstrap, which pins the repo path and isolated runtime
cwd BEFORE anything transitively imports `vnpy.trader.utility`.

## Modules

### `vnpy_researchstore.recorder`

```python
RecorderInstrument(symbol: str, exchange: str)   # vt_symbol property
RecorderConfig(source_id, source_kind, calendar_spec, instruments,
               event_kinds=("tick",), gateway_type="",
               session_id=None, predecessor_session_id=None)
RecorderState: IDLE | RECORDING | STOPPED | STOP_FAILED
RecorderAdmission(accepted, assigned_seq, reason, vt_symbol, kind)
RecorderSnapshot(state, source_id, source_kind, instruments, event_kinds,
                 gateway_type, session_id, journal_path, journal_state,
                 accepted_seq, committed_seq, backlog, rejected, errors,
                 last_error_detail, last_admission=None)
ResearchRecorder(store: Store, config: RecorderConfig)
    .start() -> str                    # session id
    .stop(*, timeout=10.0) -> bool     # True only on exact CLOSED cutoff
    .retry_stop(*, timeout=10.0) -> bool
    .release() -> None                # OS lock/connection, no state change
    .admit_tick(tick) / .admit_trade(trade) / .admit_bar(bar) -> RecorderAdmission
    .snapshot() -> RecorderSnapshot   # non-blocking, any thread
```

Behaviour contract:

* Only explicitly configured instruments on explicit real exchanges are
  admitted; `Exchange.LOCAL` synthetic contracts are refused at config time.
* Simulated and production source identities are separate configs and
  separate sessions; the durable `source_spec` records
  `source_id;source_kind;gateway_type`.
* A CTP (or any provider) `TickData` is recorded as kind `"tick"` with
  `payload["observation"] == "quote_snapshot"` — never trade-by-trade.
* Payloads are deep-copied by the bridge before admission and by the journal
  at admission/replay; mutating the original event object after the callback
  cannot change the durable record.
* `snapshot().rejected` combines journal-level rejections with bridge-level
  refusals; `snapshot().errors` is the journal's real error count, never a
  fabricated zero. `snapshot().last_error_detail` is the typed
  `JournalStatus.last_error` (WP09): the journal's own detail of the most
  recent writer/admission error, `None` when there is none, and the honest
  `UNAVAILABLE` marker only when no session is attached at all.
* The bridge never connects a gateway/account and never loads a strategy.

### `vnpy_researchstore.recording_engine`

```python
EVENT_RECORDER_STOP_BARRIER = "eRecorderStopBarrier"
STOP_WAIT_TIMEOUT_S = 10.0
BARRIER_DISPATCH_TIMEOUT_S = 10.0
StopResult: CLOSED | STOP_FAILED | NOT_RECORDING
StopReport(result, session_id, accepted_seq, committed_seq, detail)
RecorderStopBarrier(attempt: int)
RecorderStopError(Exception)
RecordingMainEngine(event_engine: EventEngine | None = None)
    .add_recorder(recorder) -> None
    .close() -> StopReport        # binding protocol; see below
    .retry_stop() -> StopReport
    .recorder_snapshot() -> RecorderSnapshot | None
    .parent_closed: bool
    .recorder_registered: bool
```

Binding stop protocol (amendment B1 of IMPLEMENTATION_PLAN.md):

1. `close()` enqueues `RecorderStopBarrier` BEFORE any parent close or
   `EventEngine.stop()`, so every tick queued earlier is dispatched first.
2. The barrier handler runs on the still-running dispatch thread, unregisters
   the recorder callbacks THERE, then runs the journal close
   (`close_at_cutoff` on attempt 1, `retry_close` on retries — same cutoff).
3. The controlling thread waits at most `BARRIER_DISPATCH_TIMEOUT_S` (10 s)
   for the barrier outcome, which is CLOSED only when the journal reports
   `committed == accepted` cutoff and state CLOSED.
4. Only on CLOSED does it call `super().close()` and release the journal OS
   lock. On STOP_FAILED the parent close is withheld, the event engine and
   process stay usable, and `retry_stop()` re-attempts the same cutoff.
5. `close()`/`retry_stop()` called ON the dispatch thread raise
   `RecorderStopError` instead of deadlocking.

### `vnpy_researchstore.app`

```python
RecorderAppConfig(store_root, source_id, source_kind, calendar_spec,
                  instruments, event_kinds=("tick",), gateway_type="",
                  session_id=None, predecessor_session_id=None)
load_recorder_config(path) -> RecorderAppConfig   # unknown keys refused
ResearchRecorderApp(config)
    .start_recording() -> str
    .stop_recording() -> StopReport
    .retry_stop() -> StopReport
    .status() -> RecorderSnapshot
    .recover_session(session_id, *, create_successor=True) -> SessionRecoveryReport
    .last_recovery -> SessionRecoveryReport | None
    .engine / .recorder properties
```

`recover_session` calls the public core recovery API and keeps only the typed
report (`successor_session_id` / `last_error` are consumed as typed fields;
no prose is parsed). It raises `SessionRecoveryError` for unknown or
unrecoverable sessions.

Config keys: `store_root`, `source_id`, `source_kind`
(`simulated`|`production`), `calendar_spec`, `instruments`
(`[{symbol, exchange}]`), `event_kinds`, `gateway_type` (declarative only),
`session_id`, `predecessor_session_id`, plus launcher-only `repo_path` and
`runtime_dir`.

### `vnpy_researchstore.ui.recorder_window`

```python
RecorderStatusWidget(app: ResearchRecorderApp, parent=None)
```

* Shows source / instruments / session id / journal path / recorder state /
  journal state / accepted / committed / backlog / rejected / errors /
  typed last error detail / last admission, plus the typed
  `successor_session_id` and a summary line of the most recent recovery
  report, plus Start, Stop (barrier close) and Retry stop buttons.
* The Recover row takes an unclosed session id and runs
  `app.recover_session(...)`: the typed successor id is rendered in the
  grid; failures are surfaced in the status line with a nonzero concept —
  never swallowed.
* Status rendering runs on a 500 ms QTimer and only reads the non-blocking
  `RecorderSnapshot` — it never blocks the shared event-dispatch thread.
* Stop/retry run on a QThread worker so the Qt loop is not parked inside the
  10-second barrier wait.
* `closeEvent` honours a failed stop: while a stop is in progress, while the
  recorder is still RECORDING (it triggers the barrier stop and vetoes), or
  after STOP_FAILED, the close is ignored; the window may only close after a
  CLOSED (or never-started) stop.

### `vnpy_researchstore.launcher` (packaged entry point)

```python
bootstrap_runtime(repo_path, runtime_dir, *, integration_root=None) -> Path
main(argv=None) -> int
```

Entry points to the SAME module:

```bash
vnpy-recorder --config <cfg>            # console script (installed wheel)
python -m vnpy_researchstore --config <cfg>
python tools/recorder_launcher.py --config configs/recorder_simulated.json   # repo shim
```

Bootstrap order: parse config → put the optional integration path (repo-run
only) + explicit repo path on `sys.path`, chdir into the configured isolated
runtime dir (creating `runtime_dir/.vntrader`) BEFORE any transitive
`vnpy.trader.utility` import → import vnpy and assert `vnpy.__file__` is
under the configured repo path → only then build the app/engine. No gateway
is connected, no strategy loaded, no settings file edited, no `~/.vntrader`
/ SQLite fallback.

Binding stop contract in the launcher (B1):

* `--status` tears down ONLY after verifying the probe never recorded
  (IDLE, no attached session, accepted==committed==0); the plain parent
  close then releases the engine. With any attached work the launcher
  parks — nothing is torn down.
* `--stop` runs the binding protocol: STOP_FAILED withholds the parent
  close AND `EventEngine.stop`; each further input line is one public
  `retry_close` against the SAME accepted cutoff until the journal
  durably reports committed==cutoff CLOSED. stdin EOF is NOT an exit
  authorization: the launcher prints truthful guidance and parks with the
  dispatch/controller alive and the session exactly as-is (retryable).
  There is no `os._exit`/`SystemExit`/engine-stop/parent-close shortcut on
  a failed stop; only the operator/OS can terminate a parked process, and
  normal exits happen solely after CLOSED (exit 0) or a verified
  never-recorded probe.
* Qt mode: while the recorder is RECORDING or STOP_FAILED, a returned Qt
  loop is re-entered with a restored status window so the Retry control
  stays usable; the launcher exits only after CLOSED or a verified probe.

`RecorderConfig` / `load_recorder_config` grammar-check `calendar_spec`
against the revised 02I seal contract (`""`, IANA zone, or `tz:<IANA>` —
timezone-only is display/normalization evidence, never a trading-calendar
claim; legacy strings like `CN.FUTURES.DAY` are refused at config time).

## CLI recording verbs (`research_store.cli`, shipped entry `qstore` / `python -m research_store`)

```bash
qstore --root <store> recover-session --session-id <sid> [--no-successor]
       [--successor-source-spec S] [--successor-calendar-spec C]
qstore --root <store> replay --session-id <sid> [--limit N]
qstore --root <store> seal --request <SealRequest JSON>
```

* `recover-session` reports the typed recovery fields (`prior_state`,
  `committed_seq`, `committed_events`, `successor_session_id`, `last_error`)
  and exits nonzero when the report carries a typed `last_error` (e.g. the
  successor could not be created) or the session is unknown — never a fake
  success.
* `replay` opens the session readonly and lists committed events in
  `(event_ts_ns, seq)` order; `--limit` caps only the listed events while
  `committed_events`/`first_seq`/`last_seq`/`truncated` stay exact.
* `seal` takes the revised-02I `SealRequest` JSON — `asset_class`,
  `volume_unit` and `turnover_unit` are OPTIONAL with the honest
  OTHER/unknown defaults (never guessed futures); an invalid
  `asset_class` VALUE is a typed CLI error, and the core then validates
  the combination, the stored session source_spec kind pin, and the
  source/calendar grammars via `plan_seal` before any publication.
  Sealed canonical bars exclude unevidenced partial tails (F1): ticks are
  always published, tail minutes without independent completion evidence
  are not. Repeat seal of the same range is idempotent
  (`idempotent_replay=true`, same `seal_id`/`dataset_id`).
* Unknown sessions/ranges return `status=error` with actionable messages and
  exit `1`; conflicts keep their dedicated exit status.

## Known interface gaps (honest status)

* The canonical `research_store.recover_session` wrapper does not yet forward
  `create_successor` / `successor_source_spec` / `successor_calendar_spec`
  (documented kwargs). Until the core owner releases the wrapper fix, the
  CLI and the app call the documented public implementation module
  `research_store.session_recovery` — the exact function the wrapper
  delegates to. Tracked in
  `.coordination/recorder03d-opencode-core-requests.md`; no private
  attribute is read and no prose is parsed anywhere.
* Final noneditable installed E2E and the affected offline
  record/stop/recover/replay/seal/freeze/query acceptance are gated on the
  released corrected recording core (02I) and native06 handoffs; the
  independent scoped tests above cover the current released semantics only.
