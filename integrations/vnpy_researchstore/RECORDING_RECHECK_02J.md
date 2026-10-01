No drift. Final report below.

---

# RECORDING_RECHECK_02J — independent Claude findings

**Scope:** recording02H F1–F4 recheck + 02IA calendar/null-time/zero correction + coordinator's retention/excluded-event concern, against `research_store/aggregation.py`, `sealing.py`, `journal.py`, `models.py`, `revisions.py`, `retention.py` and owned tests, per `TASK_CLAUDE_RECORDING_RECHECK_02J.md`. All 31 files in `.coordination/claude-recording02j-input-hashes.json` verified byte-identical (sha256, re-checked again at the end — **no drift**, before and after review). Reused unchanged original 02H repros (`.coordination/review-recording02h/`); new evidence under `.coordination/review-recording02j/` (`repro_excluded_event_retention.py`, `repro_calendar_friday.py`). No product/Git/journal/memory writes; all repro work in a temp store dir or the plugin `.venv`.

## F1–F4 verdicts

**F1 (tail PARTIAL / CLOSED ≠ interval-complete) — CLOSED.** `aggregation.py:445-454` now requires independent completion evidence (later event `event_ts_ns >= bar_end_ns`, or explicit `completion_boundary_ns`); `session_is_open` alone still forces provisional, but CLOSED alone never clears PARTIAL. Original repro A confirms: `tail bar PARTIAL present after CLOSED ...? -> True` (was `False` in 02H). `sealing.py:651-653` excludes PARTIAL bars from canonical bar publication; raw ticks always publish.

**F2 (seal identity/range) — CLOSED.** `sealing.py:500-527` (`_spec`) excludes `committed_seq_start/end`/`session_id` from `SemanticSpec`; range lives only in `seal_idempotency_key` (sealing.py:230-253). Reran original repro C: seal `[1,3]` then `[1,6]` of the same session → **same** `dataset_id=ds-1580665302e3e51d9b70ef2f7d777ffc` (was two disconnected ids in 02H). `test_f2_range_extension_same_dataset_new_revision_with_lineage` proves real `parent_revision` lineage + dedup, not just hash coincidence.

**F3 (admission lateness) — CLOSED.** `_detect_late_events` (aggregation.py:273-299) computes lateness from ingest-seq order vs. running max `event_ts_ns` pre-replay; `received_ts_ns` is never compared to `event_ts_ns` (matches disposition item 3's explicit correction of the reviewer's own imprecise wording). Reran repro B: `flags the late-admitted seq3 (T1 arriving after T10)? -> True`, and confirmed the fix for the join-case bug the 02I handoff itself flagged in Kimi's partial work (LATE now applies whether the event creates or joins the bar).

**F4 (asset/unit/source semantics) — CLOSED.** `SealRequest.asset_class` defaults to `AssetClass.OTHER` (models.py:422), never FUTURES; `sealing._validate_asset_semantics` (sealing.py:280-331) rejects an asset class inconsistent with the session's stored `source_spec` kind, and rejects unknown volume/turnover units. `source_spec`/`calendar_spec` grammars are validated (`SealError` on refusal), not silently coerced. Top-level `research_store.recover_session` now forwards `create_successor`/`successor_*_spec` (revisions.py:1237-1263), closing 03D's smoke finding; regression test present and passing.

**Calendar clarification (02IA) — CLOSED.** Reran a fresh Friday-night 2024-01-05 21:00 Asia/Shanghai repro (synthetic, labelled): with no source `trading_date`, the bar stays `trading_date=None` + `trading_date_unknown` status (never a natural-date inference); with an explicit `payload["trading_date"]="2024-01-08"`, the bar correctly carries the source-evidenced date with provenance. `STATUS_OUT_OF_SESSION` is defined but **never assigned anywhere** in the codebase — confirmed reserved, not emitted from absence.

**Null-time / zero-preservation — CLOSED.** `sealing._tick_rows` uses explicit `is None` fallbacks for `last_price`/`turnover` (never `or`-truthiness) — a genuine `0.0` survives. Committed events with `event_ts_ns=None` are filtered out of `publishable` in `seal()` (sealing.py:641) before materialization and never reach `ts=0`; `test_02ia_unknown_event_time_tick_excluded_never_epoch_zero` passes and independently confirmed via repro.

## New finding: excluded missing-time events can be certified "verified complete" and deleted — REPRODUCED (confirms the coordinator's concern)

`retention._verified_seals()` (retention.py:85-121) marks a seal "verified" purely from **catalog batch state == PUBLISHED** for the ticks/bars parts. It never compares the number of rows actually published against the number of committed events in the sealed range, and the durable seal record persisted to `session_meta["seals"]` (sealing.py:681-705) carries no `unknown_time_excluded` field — the exclusion count exists only in the transient `SealReceipt.detail` string returned to the caller, which is never persisted or consulted by retention.

Repro (`.coordination/review-recording02j/repro_excluded_event_retention.py`): a 2-event session where event 2 has `event_ts_ns=None` seals with `receipt.detail` correctly reporting `"excluded 1 tick(s) with unknown event time"`, yet the durable `session_meta["seals"]` record has both `ticks` and `bars` `state: "published"` with **no trace** of the exclusion. After aging the seal 15 days (identical pattern to the accepted `test_aged_verified_seal_eligible_and_cleanup`):
```
evaluate_retention.eligible: True
evaluate_retention.reason: 1 verified seal(s); newest 15d old
apply_retention.eligible: True
journal file exists after apply_retention: False
```
The only copy of the excluded event (`seq=2`, `source_event_id="unknown-time-2"`) is now permanently gone. `RECORDING_INTERFACES.md:579` documents eligibility criterion 2 as "all seal batches PUBLISHED in catalog; a conflicted/partial publication is NOT verified" — this documented definition itself conflates *batch-publish success* with *row-completeness*, so the current behavior matches its own (incorrect) spec. No existing test (`tests/test_retention.py::test_partial_seal_refused` only corrupts batch **state**, never tests a legitimately-published-but-row-incomplete seal) or 02I/02IA handoff prose discloses or tests this interaction — it is a real, undisclosed gap, not an accepted/known limitation.

- **Trigger:** `research_store/retention.py:107-113` (`_verified_seals`, no row-completeness check) + `research_store/sealing.py:681-705` (durable seal record omits the exclusion count).
- **Minimum fix:** persist `unknown_time_excluded` (and/or `input_events` vs. `accepted_rows`) in the durable `seals` record, and have `_verified_seals` treat any seal with a nonzero exclusion count as NOT fully verified (or require an explicit acknowledged-loss flag before it counts toward retention eligibility).

## Commands run
```
.venv/Scripts/python.exe .coordination/review-recording02h/repro_late_and_partial.py        # F1/F3, unchanged repro
.venv/Scripts/python.exe .coordination/review-recording02h/repro_seal_identity.py           # F2, unchanged repro
.venv/Scripts/python.exe .coordination/review-recording02h/repro_retention_traversal.py     # traversal, unchanged repro
.venv/Scripts/python.exe .coordination/review-recording02j/repro_calendar_friday.py         # new, calendar clarification
.venv/Scripts/python.exe .coordination/review-recording02j/repro_excluded_event_retention.py # new, coordinator concern
.venv/Scripts/python.exe -m pytest tests/test_aggregation.py tests/test_sealing.py tests/test_retention.py \
  tests/test_session_recovery.py tests/test_core_models.py tests/test_journal.py \
  tests/test_journal_lock.py tests/test_journal_fix02g.py -q
  -> 81 passed
D:/veighna_studio/python.exe -m ruff check research_store tests demo_seal_freeze_query.py   -> All checks passed!
.venv/Scripts/mypy.exe research_store/{aggregation,sealing,journal,revisions,models}.py      -> Success: no issues found in 5 source files
```

## Limits
- Junction/symlink retention escape: NOT independently re-exercised this round (already verified once by the developer on this host per handoff; original path-traversal repro reran and still refuses). No new evidence either way beyond what's inherited — recorded as inherited-verified, not re-proven.
- LIVE gateway recording: LIVE_NOT_RUN, unchanged scope boundary.
- CLI/UI/native/packaging/WP10/full-gateway acceptance: separate, not touched or claimed.
- No Git mutation, no memory/product writes; only `.coordination/review-recording02j/*.py` created (temp, ephemeral, safe to discard).

## Hash re-verification
All 31 frozen inputs in `claude-recording02j-input-hashes.json` re-hashed at the end of review: **0 mismatches, no drift** (identical before and after).

## FINAL_VERDICT
**scopedFAIL.** F1–F4 and the calendar/null-time/zero corrections are all genuinely fixed and reproducibly verified (CLOSED). However, the coordinator's specific concern — that an excluded missing-time journal event can be silently certified "verified complete" and become eligible for permanent retention deletion — is **reproduced, not refuted**: it is a real, currently-live data-loss defect in the interaction between `sealing.py`'s 02IA exclusion path and `retention.py`'s completeness check, undisclosed in any 02I/02IA handoff or test. This is a distinct, directly-affected recording-correctness defect within scope, not a presumed or manufactured finding.
