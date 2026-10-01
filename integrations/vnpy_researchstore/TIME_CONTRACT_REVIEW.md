I read `TASK_CLAUDE_TIME_CONTRACT.md`, `IMPLEMENTATION_PLAN.md` (incl. mandatory amendments), `INTERFACES.md`, `research_store/schemas.py`, and the importer files (`normalize.py`, `core_bridge.py`, `adapters.py`, `sink.py`, `quality.py`, `coverage.py`). `.coordination/opencode-core-requests.md` doesn't exist yet. I also found `.coordination/claude-time-contract.jsonl` — a prior CLI session transcript — and stopped after confirming its type, per the task's read boundary (this task's Write tool is disabled for me this session, so I can't save a plan file or use ExitPlanMode; here is the clarification directly).

## Genuine gap, but it's two different things conflated as one

`core_bridge.to_core_row` raises the same `CoreBridgeError` for two distinct failure classes, because `BARS_SCHEMA_V1` marks `bar_start`/`bar_end`/`trading_date` all `NOT NULL`:

| row family | local label | bar_start/bar_end | trading_date | note |
|---|---|---|---|---|
| RQ ETF, RQ futures `dominant_*`, JQ daily | verified | known | known | not in dispute |
| RQ futures `contract_1m_none` (real contract) | END, verified for RQ | **known** (computed via `end_label_bounds_ns`) | **unknown** (no `trading_date` column, no calendar lookup allowed) | flagged `trading_date_unknown_no_calendar` |
| SSQuant (all tables) | ambiguous BEGIN/END, unverified | **unknown** | **unknown** (follows from bounds) | flagged `source_time_label_unknown` |

`bar_start`/`bar_end` are the bar's actual identity/ordering key (`KEY_COLUMNS["bars"] = ("bar_start",)`) — SSQuant correctly can't enter `BARS_SCHEMA_V1` v1; that's the plan's "candidate research data, not executable synthetic contract" rule working as intended, not a bug. But `trading_date` is **not** a key column for minute bars — only the daily case needs "daily key = trading_date." So a fully-evidenced RQ futures real-contract row is being blocked from core publish (and therefore from any query access) purely by an over-broad `NOT NULL`, contradicting "real imports work when sufficient selected-scope evidence exists" and "candidate observation query access without masquerading as qualified backtest input."

## Minimal resolution (3 points)

1. **`research_store/schemas.py` (Kimi):** make `trading_date` nullable in `BARS_SCHEMA_V1`/`TICKS_SCHEMA_V1`. Leave `bar_start`/`bar_end` `NOT NULL` — unchanged, no key/CAS impact.
2. **Publish-time invariant (Kimi, `research_store/revisions.py`/`import_asset` validation):** when `spec.interval == Interval.D1`, reject any batch with a null `trading_date` at import time. This is where "daily key = trading_date" actually needs to live now that the column itself is nullable; minute intervals have no such requirement.
3. **`research_store/importers/core_bridge.py` (OpenCode):** split the single `CoreBridgeError` check — keep raising for null `bar_start`/`bar_end` (SSQuant unchanged), but once (1)+(2) land, stop raising for null `trading_date` alone; pass it through as `None` with the existing `trading_date_unknown_no_calendar` flag preserved in `field_quality` so native consumers can refuse it per their own "refuse ambiguous time semantics" rule.

## Which paths proceed now vs need real metadata

- **Proceeds now once (1)+(3) land, no new metadata needed:** RQ futures `contract_1m_none` real-contract minute bars.
- **Stays blocked, correctly, no code change requested:** SSQuant (all tables) — a bounds problem, not a nullability problem. RQ ETF/JQ daily/RQ `dominant_*` are unaffected either way.

**Invariants/tests to add:** (a) `BARS_SCHEMA_V1` batch with `trading_date=None` + valid bounds round-trips through publish/read unchanged; (b) `Interval.D1` batch with null `trading_date` is rejected at `import_asset`, not later at read; (c) `to_core_row` no longer raises for RQ futures contract rows and preserves the quality flag, while still raising for SSQuant; (d) assert no code path infers `trading_date` from `bar_start` or date text.

This is a design clarification only — Codex should relay points 1–3 to Kimi/OpenCode; no product code was touched, and no implementation is being accepted or rejected here.
