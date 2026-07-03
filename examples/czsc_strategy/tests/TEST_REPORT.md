# Chan Strategy Test Report

## 1. Scope

This report covers the test suite added for `examples/czsc_strategy/chan_strategy`.

The suite is split into two layers:

- `unit`: fast deterministic tests using synthetic bars, fake CZSC objects, and in-memory SQLite databases.
- `integration`: skip-able/manual checks for the local historical SQLite data source.

Coverage gating is applied only to the unit layer and only to the core strategy modules.

## 2. Coverage Configuration

Coverage configuration is stored in `.coveragerc`.

Measured source:

- `examples/czsc_strategy/chan_strategy/backtest_engine.py`
- `examples/czsc_strategy/chan_strategy/config.py`
- `examples/czsc_strategy/chan_strategy/data_adapter.py`
- `examples/czsc_strategy/chan_strategy/positions.py`
- `examples/czsc_strategy/chan_strategy/signals.py`

Excluded from the coverage gate:

- `validation.py`
- `run_*.py`
- `__init__.py`
- `utils.py`

Reason: these files are either orchestration/reporting entrypoints or non-core helpers; the 100% gate is intended for deterministic core behavior.

## 3. Test Files

### Shared Fixtures

- `tests/conftest.py`

Provides:

- `FakeBI` and `FakeCZSC`
- synthetic `RawBar` and BI factories
- synthetic 1-minute bar generator
- mini backtest bars
- in-memory SQLite database
- real DB path fixture using `CHAN_SQLITE_DB_PATH` or the local default path
- pytest markers: `realdb`, `slow`

### Unit Tests

- `test_signal_contract.py`

Validates signal string contracts, key/value parsing assumptions, and signal classification invariants.

- `test_signal_properties.py`

Property-style scan for complete classification signals. It feeds multiple synthetic BI/Zhongshu structures into `get_all_signals` and asserts that every complete classification signal returns exactly one legal class value.

- `test_signals.py`

Covers main signal behavior for BI direction, Zhongshu position, data sufficiency, divergence, first buy, second buy, third buy, and risk-control signals.

- `test_branch_completion.py`

Covers branch-heavy edge cases across data loading, signals, position logic, report generation, and backtest entrypoints.

- `test_coverage_closure.py`

Completes remaining branch coverage with focused tests for:

- SQLite adapter edge cases
- raw bar parsing fallback paths
- backtest daily-filter increment path
- report boundary metrics
- long/short position risk branches
- injected Zhongshu structures for signal branch isolation
- buy1 anchor fallback/matching behavior
- combined strategy trade aggregation

- `test_data_adapter.py`

Covers resampling, date parsing, schema discovery, table inspection, symbol discovery, and raw bar conversion.

- `test_table_matching.py`

Covers `_find_table` exact/prefix matching and failure modes.

- `test_daily_filter.py`

Validates daily trend filter wiring and first-buy strictness relaxation versus second/third-buy strict filters.

- `test_daily_no_lookahead.py`

Validates that the daily filter cannot see the current day's completed daily bar before that daily bar's timestamp has been reached by the intraday trade bar.

- `test_execution_timing.py`

Validates delayed execution semantics: signal generated on one bar is executed on the next bar open.

- `test_positions.py`

Covers Signal/Factor/Event matching, Position open/close, stop loss, timeout, trailing stop, daily filter events, and sub-strategy behavior.

- `test_report_metrics.py`

Validates generated report metrics with injected known trades/equity curves.

- `test_portfolio_accounting.py`

Golden-number test for portfolio-level realized PnL accounting. It verifies the 10% / 20% / 30% sub-strategy weights, `_cum_realized_pnl`, `_pair_counts`, and final equity aggregation.

- `test_backtest_entrypoints.py`

Smoke tests convenience entrypoints and backtest state reset/idempotency behavior.

- `test_more_coverage.py`

Additional regression and edge coverage for adapter/report/position paths.

- `test_strategy_state_replay.py`

Strategy-level replay test. It compares incremental `ChanTimingStrategy.update()` state against rebuilding from the beginning for each prefix, covering `buy1_anchor`, `buy1_history`, positions, and pairs.

- `test_regressions.py`

Named regression tests for historical bug classes, including CZSC confirmed-BI API contract, extending-tail filtering, daily-filter disabled construction, second-buy-without-anchor behavior, and buy1 anchor price extraction.

### Integration Tests

- `integration/test_realdb_placeholder.py`

Checks that the configured real historical SQLite DB exists and is non-empty.

This test is marked `realdb` and `slow`. It belongs to integration/business validation, not the unit coverage gate.

- `integration/test_real_data_matrix.py`

Runs the real DB matrix for `AP888`, `RB888`, `SC888`, `A888`, and `ZN888`.

Default windows:

- Matrix/repeatability: `2024-01-01` to `2024-03-31`
- In-sample smoke: `2024-01-01` to `2024-06-30`
- Out-of-sample smoke: `2024-07-01` to `2024-12-31`

The test auto-selects the actual `symbol` value stored in each `{symbol}_1M_raw` table for the requested date range, because the real DB contains at least one known case of symbol-case drift: `ap888_1M_raw` stores `AP888` historically and `ap888` later.

### Performance Tests

- `performance/test_performance_smoke.py`

Performance smoke for real DB replay. It is skipped by default and runs only when `RUN_CHAN_PERF=1` is set.

Default performance window:

- symbol: `AP888`
- table: `ap888_1M_raw`
- period: `2024-01-01` to `2024-12-31`
- assertion: two consecutive `run()` calls are repeatable and complete under `CHAN_PERF_MAX_SECONDS` seconds.

## 4. Executed Commands

Unit coverage gate:

```powershell
pytest examples/czsc_strategy/tests/unit --cov --cov-report=term-missing --cov-fail-under=100 -q
```

Result:

```text
62 passed
Required test coverage of 100% reached. Total coverage: 100.00%
```

Coverage table:

```text
Name                                                      Stmts   Miss Branch BrPart  Cover
-----------------------------------------------------------------------------------------------------
examples\czsc_strategy\chan_strategy\backtest_engine.py     219      0     68      0   100%
examples\czsc_strategy\chan_strategy\config.py                6      0      0      0   100%
examples\czsc_strategy\chan_strategy\data_adapter.py        164      0     70      0   100%
examples\czsc_strategy\chan_strategy\positions.py           337      0    144      0   100%
examples\czsc_strategy\chan_strategy\signals.py             390      0    132      0   100%
-----------------------------------------------------------------------------------------------------
TOTAL                                                      1116      0    414      0   100%
```

Integration:

```powershell
pytest examples/czsc_strategy/tests/integration -q
```

Result:

```text
11 passed
```

Full test directory:

```powershell
pytest examples/czsc_strategy/tests -q
```

Result:

```text
73 passed, 1 skipped
```

Performance smoke:

```powershell
$env:RUN_CHAN_PERF='1'
pytest examples/czsc_strategy/tests/performance -q
```

Result:

```text
1 passed in 9.40s
```

## 5. Coverage Notes

Some branches are explicitly marked with `pragma` annotations.

These annotations are narrowly scoped to:

- presentation helpers, such as report printing
- interactive DB inspection helper
- branch-coverage artifacts where loop state guarantees a group is populated
- mutually exclusive position-direction branches after a risk trigger
- compound signal guards where the branch represents a structural sub-condition, not an independently meaningful execution path

No broad `except` exclusion was added. The report does not rely on globally hiding exception paths.

## 6. Verified Historical Bug Classes

The test suite now covers the bug classes discussed during review:

- no future-function fallback to unconfirmed BI
- daily trend filter wiring
- first-buy relaxed daily filter versus strict second/third-buy filter
- `_find_table` failing loudly instead of silently falling back
- delayed execution on next bar open
- report metric boundaries and golden-number style checks
- idempotent repeated `run()`
- cost/slippage propagation into positions
- buy1 anchor extraction from confirmed down BI
- second-buy dependency on buy1 anchor context
- third-buy leave/retrace/confirm branches
- real DB validation separated from coverage gate
- strategy-level state replay consistency
- daily-filter no-lookahead behavior
- complete classification signal exhaustiveness
- CZSC `finished_bis` / `last_bi_extend` API contract guard
- portfolio accounting golden number for 10% / 20% / 30% sub-strategy weights

## 7. Real DB Business Validation

The real database was used by `integration/test_real_data_matrix.py`.

Default real-data matrix window:

- `start_date = 2024-01-01`
- `end_date = 2024-03-31`
- data frequency: `1M`
- trade frequency: strategy default `30分钟`
- symbols: `AP888`, `RB888`, `SC888`, `A888`, `ZN888`

Observed matrix summary from the local DB:

```text
AP888: bars=12375, traded_bars=340, total_trades=0, 一买=0, 二买=0, 三买=0
RB888: bars=19768, traded_bars=588, total_trades=0, 一买=0, 二买=0, 三买=0
SC888: bars=31450, traded_bars=980, total_trades=0, 一买=0, 二买=0, 三买=0
A888 : bars=19768, traded_bars=588, total_trades=1, 一买=1, 二买=0, 三买=0
ZN888: bars=26488, traded_bars=812, total_trades=1, 一买=1, 二买=0, 三买=0
```

Important interpretation:

- The strategy now has real-DB smoke coverage and repeatability coverage.
- However, this default 2024Q1 window shows very sparse trades.
- Second-buy and third-buy produced zero trades in this window.
- This is a business validation warning, not a unit-test failure.

Before SimNow-style deployment, the real-data matrix should be expanded to longer windows and reviewed by sub-strategy:

- whether one-buy trade count is sufficient;
- whether second-buy / third-buy are over-filtered;
- whether daily filter strictness suppresses too many signals;
- whether the chosen default periods are representative.

## 8. Resolved Semantic Fixes

Third-buy confirmation semantics were reviewed and fixed.

Previous behavior:

`signal_third_buy` could classify a natural confirming upward BI as a new "leave" BI when that BI also broke above the Zhongshu upper bound.

Current behavior:

- third-buy detection now uses an explicit `leave -> retrace -> confirm` state machine;
- the confirming upward BI is no longer reclassified as a new leave BI;
- a later downward BI that falls back into the Zhongshu invalidates the third-buy setup;
- regression coverage is provided by `test_third_buy_confirm_bi_is_not_reclassified_as_new_leave`.

The 2024Q1 real-data matrix still shows zero third-buy trades for the default five-symbol window, so the semantic bug fix did not by itself make third-buy active in that period.

Another data-source observation:

The real DB contains multiple frequency tables for the same symbol, such as `ap888_1M_raw`, `ap888_5M_raw`, and `ap888_15M_raw`. The business matrix explicitly passes the `1M` table name. Calling `BacktestEngine` without `table_name` remains intentionally strict and will raise on ambiguous matches.

## 9. Mutation Testing

Mutation tooling has been wired into the repo:

- `cosmic-ray.signals.toml`
- `[tool.mutmut]` in `pyproject.toml`
- `cosmic-ray` and `mutmut` are listed under the `dev` optional dependencies.

Environment notes:

- `mutmut` does not run natively on Windows and exits with: `To run mutmut on Windows, please use the WSL`.
- `cosmic-ray` runs natively on this Windows environment.

Executed checks:

```powershell
cosmic-ray baseline cosmic-ray.signals.toml
```

Result: passed.

Initial mutation session against `signals.py`:

```text
total mutants: 1058
completed within 5-minute interactive budget: 59
survived: 32
incompetent: 27
pending: 999
```

Interpretation:

- This confirms the earlier warning that 100% branch coverage is necessary but not sufficient.
- The first surviving mutants point to weak assertions around `signal_second_buy`, `signal_third_buy`, and `build_zhongshu_from_bis`.
- A full mutation pass should be run in WSL or a nightly job because the complete `signals.py` mutation session is too slow for an interactive turn.

Recommended full run:

```powershell
Remove-Item -LiteralPath cosmic-ray.sqlite -ErrorAction SilentlyContinue
cosmic-ray init --force cosmic-ray.signals.toml cosmic-ray.sqlite
cosmic-ray exec cosmic-ray.signals.toml cosmic-ray.sqlite
cosmic-ray dump cosmic-ray.sqlite
```

The current partial mutation result is intentionally not treated as a release gate yet.
