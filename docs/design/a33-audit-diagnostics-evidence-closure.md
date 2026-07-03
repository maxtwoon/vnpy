# A33 Design: Audit Diagnostics Evidence Closure

**Task:** Close the H3/H4 evidence gaps in `audit_issue_diagnostics.py` so the audit report moves from "unavailable / unknown" to verifiable conclusions using real project inputs.

**Scope:** Design only. No implementation of strategy logic, signal formulas, position rules, or order interfaces.

**Background:**
- A32 wired real inputs for H1, H2, and M1.
- H3 ("背驰失效" branch reachability) is still `unavailable` because no real signal-history artifact exists.
- H4 (888 continuous-contract assumptions) is still `unknown` because no DB path was provided and no metadata inspection was performed.

**Deliverables after this design stage:**
- This design document.
- Updated `HANDOFF.md` ready for the dev stage.

---

## 1. H3 — Real Signal-History Evidence

### 1.1 Problem

The audit issue H3 asks whether the divergence-failure classification (`背驰V260615_失效`) is ever produced by the real signal pipeline on real historical data.

`audit_issue_diagnostics.analyze_divergence_failure_reachability()` expects a list of records like:

```json
{"dt": "2026-04-08 09:30:00", "signal": "30分钟_D1BI_背驰V260615_失效_任意_任意_20"}
```

A32 only scans existing diagnostics JSON files. None of the current diagnostics artifacts contain such a signal stream, so H3 is reported as `unavailable`.

### 1.2 Design Principle

Generate the signal history by **replaying real 1-minute K-line data through the actual CZSC objects and the existing `signal_divergence_status` function**. This:

- Uses the same code path that the strategy uses at runtime.
- Avoids hand-crafting fake bi structures (which the audit explicitly criticizes in `test_coverage_closure.py`).
- Produces a stable artifact that can be re-run whenever the DB or signal version changes.

### 1.3 Proposed Artifact

New script:

```text
examples/czsc_strategy/diagnostics/generate_signal_history.py
```

Output files (one per symbol, or one combined file — see decision below):

```text
examples/czsc_strategy/diagnostics/signal_history_{symbol}_{start}_{end}.json
examples/czsc_strategy/diagnostics/signal_history_{symbol}_{start}_{end}.md   # optional human summary
```

Recommended combined file to simplify downstream scanning:

```text
examples/czsc_strategy/diagnostics/signal_history_V260615_20220101_20260424.json
```

### 1.4 Record Schema

Each element in the output JSON must be an object with at least:

```json
{
  "dt": "2022-01-04 09:00:00",
  "symbol": "AP888",
  "price": 1234.5,
  "signal": "30分钟_D1BI_背驰V260615_无_任意_任意_0",
  "signal_key": "30分钟_D1BI_背驰V260615",
  "signal_value": "无_任意_任意_0",
  "divergence_status": "无",
  "source": "real_bar_replay",
  "data_version": "V260615"
}
```

For records where the signal value contains `失效`, `analyze_divergence_failure_reachability` will classify H3 as `detected` / `reachable=True`. The schema deliberately stores `signal` as a single string so it matches the existing collector logic.

### 1.5 Replay Procedure

The script should follow the same multi-timeframe setup used by `BacktestEngine.run()`:

1. Resolve DB path (same resolution chain as H4: `--db-path` → `CHAN_SQLITE_DB_PATH` → `chan_strategy.config.SQLITE_DB_PATH`).
2. For each requested symbol:
   a. Load 1-minute bars from `{symbol}_1M_raw` via `SqliteDataAdapter.load_raw_bars`.
   b. Resample to `STRATEGY_CONFIG["trade_freq"]` (currently `"30分钟"`) using `data_adapter.resample_bars`.
   c. Optionally resample to `STRATEGY_CONFIG["filter_freq"]` (currently `"日线"`) and maintain a daily CZSC object.
   d. Warm up a trade-period CZSC object with the first `warmup_bars` (default 100) trade bars.
   e. For each subsequent trade bar:
      - Update `czsc_trade` with the bar.
      - If daily CZSC is enabled, update it with any daily bars whose `dt <= bar.dt`.
      - Call `chan_strategy.signals.signal_divergence_status(czsc_trade, trade_freq_name)`.
      - Append a record containing the resulting signal string, bar dt, bar close, symbol, and metadata.
3. Write the JSON and optional Markdown summary.

The script must not call `BacktestEngine.run()` directly, because:

- `BacktestEngine.signal_history` only samples every 100 bars, which could miss a transient `失效` classification.
- Running the full engine triggers position/trade logic, which is unnecessary for H3 and much slower.

### 1.6 CLI

```bash
python examples/czsc_strategy/diagnostics/generate_signal_history.py \
  --symbols AP888,RB888,SC888,A888,ZN888 \
  --start-date 2022-01-01 \
  --end-date 2026-04-24 \
  --output-dir examples/czsc_strategy/diagnostics \
  --combined
```

Flags:

- `--symbols` — comma-separated list, default `"AP888,RB888,SC888,A888,ZN888"`.
- `--start-date` / `--end-date` — default to `BACKTEST_CONFIG["start_date"]` / `BACKTEST_CONFIG["end_date"]`.
- `--output-dir` — default `examples/czsc_strategy/diagnostics`.
- `--combined` — write one file; otherwise write one file per symbol.
- `--db-path` — override DB path.
- `--warmup-bars` — default 100.

### 1.7 Integration with Audit Diagnostic

`collect_signal_records_from_diagnostics` already scans all `.json` files in the diagnostics directory for records containing `背驰`. It will automatically pick up `signal_history_*.json` once the file exists.

Add a filename filter so the collector prioritizes files matching `signal_history_*.json` and reports `data_source = "signal_history_replay"` when records originate from those files.

Change in `audit_issue_diagnostics.py`:

- Introduce `SIGNAL_HISTORY_FILENAME_MARKERS = ("signal_history_",)`.
- In `build_audit_issue_report`, if `signal_records` are auto-collected and at least one source file matches the marker, set `h3["data_source"] = "signal_history_replay"`.

### 1.8 Edge Cases & Safeguards

- If the DB is missing or a symbol has no data, write an empty list for that symbol and a clear note in Markdown.
- If `czsc` or `chan_strategy` cannot be imported, the script exits non-zero with a message.
- The script must never send orders or connect to a broker.
- File size: full replay of five symbols over ~4 years of 30-minute bars is small (< 10 MB). Keep a `--max-file-mb` default of 50 MB for consistency.

### 1.9 Expected H3 Outcomes

After the artifact is generated:

- If any record contains `背驰V260615_失效` → H3 status = `detected`, `reachable = True`, `severity = info`.
- If records exist but none contain `失效` → H3 status = `detected`, `reachable = False`, `severity = high` (confirms the dead-branch concern from the audit report).
- If no artifact exists and no records are found → H3 status = `unavailable` (fallback).

---

## 2. H4 — DB Metadata Evidence for Continuous Contracts

### 2.1 Problem

The audit issue H4 asks whether the `888` continuous-contract data declares rollover / adjustment rules. The strategy consumes `{symbol}888_1M_raw` tables, but the code contains no documentation of how the 888 series is synthesized.

### 2.2 Design Principle

Inspect the actual SQLite DB for machine-readable evidence of:

1. **Rollover/splicing** — does the 888 table switch underlying contracts over time?
2. **Adjustment** — are there explicit adjustment-factor or back-adjust columns?
3. **Metadata tables** — are there tables that document continuous-contract rules?

Do not assume any particular synthesis method. Report exactly what the DB can prove.

### 2.3 DB Path Resolution Chain

`audit_issue_diagnostics.py` should resolve the DB path in this order:

1. Explicit `--db-path` argument.
2. `CHAN_SQLITE_DB_PATH` environment variable.
3. `chan_strategy.config.SQLITE_DB_PATH` (import the module; it already reads the env var).

If none resolve to an existing file, H4 status = `unavailable` and `db_path` records the attempted path.

### 2.4 Inspection Rules

For each symbol in `--symbols` (default `AP888,RB888,SC888,A888,ZN888`):

1. Identify the raw table name. Re-use `BacktestEngine._find_table` logic or a simplified heuristic:
   - Exact match `{lower(symbol)}_1m_raw`.
   - Prefix match `{lower(symbol)}_` if unique.
   - Skip if no unique table is found.
2. Inspect `PRAGMA table_info(table)` for columns whose names contain:
   - adjustment keywords: `adjust`, `factor`, `back_adjust`, `front_adjust`, `roll_adj`, `continuous_adj`.
   - rollover keywords: `rollover`, `roll_date`, `contract`, `real_symbol`, `source_symbol`, `active_contract`.
3. Query distinct values of any `real_symbol` / `source_symbol` column. If the count is > 1, the table is a **spliced continuous contract**.
4. Look for DB-level metadata tables whose names contain `meta`, `info`, `config`, `contract`, or `mapping`. If found, inspect their columns and sample rows.
5. Look for companion `{symbol}777_1M_raw` tables. Their presence indicates the data vendor stores both continuous (888) and individual-contract (777) series; record this as supporting evidence.

### 2.5 Status Mapping

`analyze_continuous_contract_assumptions` should return one of the following statuses:

| Status | Meaning |
|--------|---------|
| `found_adjusted` | At least one 888 table has an explicit adjustment-factor column or a metadata table describing adjustment rules. |
| `found_spliced` | The 888 table switches `real_symbol` over time and has no adjustment columns. This means the series is a raw splice (likely unadjusted). |
| `found_single_contract` | The 888 table contains only one `real_symbol` value, so there is no rollover evidence in the data window. |
| `no_evidence` | The DB exists, the tables exist, but none of the above evidence is found. |
| `unavailable` | The DB file is missing or no tables were found. |
| `unknown` | Reserved for when no DB path was resolved at all (kept for backward compatibility). |

The function should also report:

- `symbols` — list of symbols inspected.
- `db_path` — resolved path.
- `evidence` — list of strings like `{db_path}::{table}::{column}` for structural evidence.
- `real_symbol_transitions` — per symbol, count of distinct `real_symbol` values and first/last transition dates.
- `metadata_tables` — list of metadata tables found and their columns.
- `file_evidence` — existing diagnostics files that mention continuous-contract keywords (kept from A32).
- `silently_pass` — always `False`; H4 must never pass silently.

### 2.6 Expected H4 Outcomes

For the current project DB, the expected outcome is `found_spliced` because:

- Tables like `ap888_1M_raw` contain a `real_symbol` column with multiple distinct values (e.g., `AP205`, `AP210`, ...).
- No `adjustment_factor` column exists.
- A `simnow_bar_meta` table exists for SimNow tick aggregation, but it does not describe historical 888 synthesis.

This will produce a verifiable conclusion: **"The 888 series is a raw contract splice without documented adjustment; continuous-contract assumptions remain unverified."**

### 2.7 Interface Change in Audit Diagnostic

Modify `analyze_continuous_contract_assumptions` signature to keep backward compatibility:

```python
def analyze_continuous_contract_assumptions(
    db_path: str | Path | None,
    symbols: list[str],
    diagnostics_dir: Path | None = None,
    max_file_mb: float = 50.0,
) -> dict[str, Any]: ...
```

Add helper functions (design; implement in dev):

- `_resolve_db_path(db_path: str | Path | None, repo_root: Path | None) -> Path | None`
- `_find_symbol_table(adapter, symbol: str) -> str | None`
- `_inspect_table_for_rollover(adapter, table: str, symbol: str) -> dict[str, Any]`

---

## 3. File / Interface Change List

| File | Change | Rationale |
|------|--------|-----------|
| `examples/czsc_strategy/diagnostics/generate_signal_history.py` | **New** | Replays real bars to produce signal-history artifact. |
| `examples/czsc_strategy/diagnostics/audit_issue_diagnostics.py` | Update collectors and H3/H4 logic | Wire new artifacts and DB metadata. |
| `examples/czsc_strategy/tests/unit/test_audit_issue_diagnostics.py` | Add tests for H3 replay collector and H4 DB heuristics | Verify evidence closure. |
| `examples/czsc_strategy/tests/integration/test_realdb_placeholder.py` | Add or extend real-DB H4 test | Verify against actual DB when available. |
| `HANDOFF.md` | Update front matter and body | Reflect A33 task and acceptance criteria. |

**Files that must NOT change:**

- `chan_strategy/signals.py` — signal logic stays untouched.
- `chan_strategy/positions.py` — position/risk logic stays untouched.
- `chan_strategy/backtest_engine.py` — engine logic stays untouched (the replay script bypasses it).
- Any SimNow order interface.

---

## 4. Test Design

### 4.1 Unit Tests

Add to `tests/unit/test_audit_issue_diagnostics.py`:

1. `test_generate_signal_history_creates_expected_schema` — run the new generator against a temporary in-memory or file-backed synthetic DB and assert the output JSON schema and at least one `dt`/`signal` record.
2. `test_collect_signal_records_prefers_signal_history_files` — create a temp diagnostics dir with both `signal_history_*.json` and a generic file; assert the collector marks the source correctly.
3. `test_analyze_continuous_contract_found_spliced` — create a temp SQLite DB with an `ap888_1M_raw` table containing a `real_symbol` column with multiple values; assert H4 status = `found_spliced` and transitions are reported.
4. `test_analyze_continuous_contract_found_adjusted` — create a temp DB with `adjustment_factor` column; assert status = `found_adjusted`.
5. `test_analyze_continuous_contract_unavailable_missing_db` — pass a non-existent path; assert status = `unavailable`.
6. `test_resolve_db_path_cli_arg_over_env` — verify resolution order.

### 4.2 Integration / Real-DB Test

Extend `tests/integration/test_realdb_placeholder.py`:

- Add `@pytest.mark.realdb @pytest.mark.slow` test `test_real_db_continuous_contract_evidence`.
- It resolves the real DB path, runs H4 inspection for the default symbols, and asserts:
  - status is not `unknown` or `unavailable` when the DB exists.
  - `real_symbol_transitions` is non-empty for at least one symbol.
  - `silently_pass` is `False`.

This test is allowed to `pytest.skip` when the real DB is not present.

### 4.3 Acceptance Test for the Audit Report

After the dev stage, running:

```bash
python examples/czsc_strategy/diagnostics/generate_signal_history.py --combined
python examples/czsc_strategy/diagnostics/audit_issue_diagnostics.py
```

must produce a report where:

- H3 status is either `detected` with `reachable` True/False and `data_source` = `signal_history_replay`.
- H4 status is not `unknown` when the real DB is available.

### 4.4 Existing Tests Must Still Pass

After implementation, run:

```bash
pytest examples/czsc_strategy/tests/unit/test_audit_issue_diagnostics.py
python tools/sync_check.py
```

No existing assertions should be weakened. Existing H4 tests currently allow `("unknown", "unavailable")`; they should continue to pass because `unavailable` remains a valid fallback when no DB is provided.

---

## 5. Acceptance Criteria

1. `docs/design/a33-audit-diagnostics-evidence-closure.md` exists and covers H3, H4, file changes, tests, and acceptance criteria.
2. `HANDOFF.md` front matter reflects task "A33 Audit Diagnostics Evidence Closure", stage `design`, owner `claude-code`, and lists the design document as a deliverable.
3. Design specifies how to generate real signal history **without fake structures**.
4. Design specifies DB path resolution and continuous-contract metadata inspection heuristics.
5. Design lists exact status values and expected H4 outcome for the current project DB.
6. `python tools/handoff.py next` succeeds (advances to `dev` / `kimi-code`).

---

## 6. Dev Handoff Prompt

When you pick up this task as the dev agent:

1. Read `HANDOFF.md` and this design document.
2. Implement `examples/czsc_strategy/diagnostics/generate_signal_history.py` according to Section 1.
3. Update `audit_issue_diagnostics.py`:
   - Add DB-path resolution and H4 metadata inspection (Section 2).
   - Update H3 data-source labeling for signal-history files (Section 1.7).
4. Add/update unit tests per Section 4.
5. Run the new generator, then run the audit diagnostic, and confirm H3/H4 produce verifiable conclusions.
6. Ensure `pytest examples/czsc_strategy/tests/unit/test_audit_issue_diagnostics.py` passes and `python tools/sync_check.py` passes.
7. Do **not** modify strategy parameters, signal logic, position risk rules, or SimNow order interfaces.
8. When done, run `python tools/handoff.py next --summary "A33 evidence closure implemented"`.
