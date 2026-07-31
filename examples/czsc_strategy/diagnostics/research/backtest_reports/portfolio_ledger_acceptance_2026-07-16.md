<!-- RESEARCH-ONLY / NOT PROMOTION EVIDENCE -->

# A84 — Portfolio Ledger Report Acceptance / Sanity-Check

**Date:** 2026-07-16  
**Artifact under check:** `diagnostics/portfolio_ledger_report_20260716_094919.json` / `.md`  
**Acceptance checker:** `diagnostics/portfolio_ledger_acceptance_check.py`  
**DB path:** `D:\BaiduNetdiskDownload\新数据库\ssquant数据库_20260425\kline_data.db` (from `chan_strategy/config.py`)  
**Symbols:** AP888, RB888, SC888, A888, ZN888  
**Window:** 2022-01-01 ~ 2026-04-24  
**Sizing model:** `risk`  
**Initial capital:** 1,000,000

> ⚠️ **RESEARCH ONLY — NOT PROMOTION EVIDENCE**
>
> This artifact evaluates a measurement-only diagnostic script. It is not a claim of trading discovery.

---

## Methodology Statement

`diagnostics/portfolio_ledger_report.py` is **an independent per-symbol aggregation, not a joint or coordinated portfolio replay**. Each symbol is run against the full initial capital in isolation through its own `BacktestEngine` with `sizing_model="risk"`; portfolio-level figures are produced by timestamp-aligning the per-symbol `equity_curve["total_open_margin"]` series and summing closed-trade `pnl_currency`. Phase 2, if approved, will build a true shared-ledger coordinated replay.

---

## Bug Found and Fixed During Acceptance

Running the report with its existing defaults against the real historical DB initially failed with:

```
ValueError: 品种 'AP888' 在数据库中找到多个精确匹配表: ['ap888_1M_raw', 'ap888_5M_raw']
```

The same error occurred for all five symbols. This left the ledger empty and every `symbol_error` set to `数据加载失败`.

**Root cause:** `BacktestEngine._find_table()` treats both `{symbol}_1M_raw` and `{symbol}_5M_raw` as exact matches; the report passed `freq="1"` but did not supply an explicit table name, so the engine could not disambiguate.

**Fix (small, localized to `diagnostics/portfolio_ledger_report.py`):**

- Added `_infer_table_names()` to pick `{symbol}_1m_raw` when `freq` indicates 1-minute data (and `{symbol}_5m_raw` for 5-minute), using the actual case of tables present in the configured SQLite DB.
- The inferred mapping is merged with any caller-supplied `table_names`, so explicit overrides still win.
- Default parameters (`DEFAULT_SYMBOLS`, `DEFAULT_START`, `DEFAULT_END`) were not changed.

After the fix, the report completed successfully and produced the numbers below.

---

## Sanity Check Results

### 1. Portfolio total margin at each timestamp equals the timestamp-aligned sum of per-symbol margins

**Result: PASS**

An independent re-run of each symbol through its own `BacktestEngine` (same window, same `sizing_model="risk"`, explicit 1-minute tables) was aggregated into a fresh ledger and compared row-by-row with the report's ledger.

| Metric | Value |
|--------|------:|
| Ledger rows | 19,470 |
| Row-wise max absolute difference | 0.0 |
| Row-wise equality | **true** |

The verification script rebuilt the per-symbol margin DataFrame using the same `ffill` + `[first_dt, last_dt]` mask logic used by `_build_ledger()`. The portfolio total margin series matched exactly.

### 2. Portfolio total realized currency PnL equals the sum of each symbol's own realized PnL

**Result: PASS**

| Symbol | Realized PnL (currency) |
|--------|------------------------:|
| AP888 | 33,595.59 |
| RB888 | -74,395.27 |
| SC888 | 0.00 |
| A888 | -15,113.73 |
| ZN888 | -9,550.17 |
| **Sum** | **-65,463.58** |

Reported portfolio total realized PnL: **-65,463.57** (the 0.01 difference is rounding at two decimals).  
Verification: `total_pnl_match: true`.

### 3. Timestamp of maximum margin utilization is traceable to specific symbols / clusters

**Result: PASS**

| Metric | Value |
|--------|------:|
| Max portfolio total open margin | **64,913.25** |
| Max margin utilization | **6.49%** |
| Timestamp of max margin | **2025-09-25 23:59:00** |

Contributors at that timestamp:

| Symbol | Margin at max timestamp | Cluster |
|--------|------------------------:|---------|
| AP888 | 34,807.50 | _uncategorized |
| ZN888 | 22,163.75 | industrial_energy |
| A888 | 7,942.00 | _uncategorized |
| RB888 | 0.00 | industrial_energy |
| SC888 | 0.00 | industrial_energy |

Cluster-level totals at the max timestamp:

| Cluster | Margin at max timestamp |
|---------|------------------------:|
| _uncategorized | 42,749.50 |
| industrial_energy | 22,163.75 |
| **Total** | **64,913.25** |

The max cluster margins observed anywhere in the window are 42,749.50 (`_uncategorized`) and 37,012.75 (`industrial_energy`); the portfolio peak occurs when the two clusters overlap.

### 4. Each symbol's margin contribution correctly goes to zero outside its own data range

**Result: PASS**

The per-symbol margin series were masked to `[first_dt, last_dt]`. For every symbol, contributions before `first_dt` and after `last_dt` are exactly zero.

| Symbol | first_dt | last_dt | zero_before_first | zero_after_last |
|--------|----------|----------|:-----------------:|:---------------:|
| AP888 | 2022-01-20 11:29:00 | 2026-04-24 14:59:00 | true | true |
| RB888 | 2022-01-14 11:29:00 | 2026-04-24 22:59:00 | true | true |
| SC888 | 2022-01-11 13:59:00 | 2026-04-24 23:59:00 | true | true |
| A888 | 2022-01-14 11:29:00 | 2026-04-24 22:59:00 | true | true |
| ZN888 | 2022-01-12 11:29:00 | 2026-04-24 23:59:00 | true | true |

`margin_zero_outside_range: true`.

### 5. Cluster membership is correctly case-insensitive on real symbol names

**Result: PASS**

`_symbol_clusters()` was called with the real `corr_clusters` config against both uppercase and lowercase versions of the symbol list. The mappings are identical:

| Symbol (upper) | Symbol (lower) | Cluster(s) |
|----------------|----------------|------------|
| AP888 | ap888 | — |
| RB888 | rb888 | industrial_energy |
| SC888 | sc888 | industrial_energy |
| A888 | a888 | — |
| ZN888 | zn888 | industrial_energy |

`cluster_membership_case_insensitive: true`.

The actual report grouped `RB888`, `SC888`, `ZN888` into `industrial_energy` and `AP888`, `A888` into `_uncategorized`, consistent with the case-insensitive mapping.

---

## Cross-Check Against Independent Single-Symbol Runs

The verification script ran each symbol independently through `BacktestEngine` (not via `PortfolioEngine`) and compared key metrics to the ledger's `per_symbol` breakdown:

| Symbol | PnL match | Max margin match | Final margin match | Trade count match |
|--------|:---------:|:----------------:|:------------------:|:-----------------:|
| AP888 | true | true | true | true (73 trades) |
| RB888 | true | true | true | true (43 trades) |
| SC888 | true | true | true | true (0 trades) |
| A888 | true | true | true | true (48 trades) |
| ZN888 | true | true | true | true (78 trades) |

`all_per_symbol_metrics_match: true`.  
`all_cluster_metrics_match: true`.  
`overall_accepted: true`.

---

## Verdict

**Trustworthy as a Phase 1 read-only aggregation.**

- All five sanity checks passed against real data.
- The one bug found (table-name ambiguity when multiple raw tables exist) was small, localized, and fixed in `portfolio_ledger_report.py`.
- The report honestly labels itself as an independent per-symbol aggregation, not a joint/coordinated portfolio replay; this acceptance write-up reinforces that limitation.
- `SC888` produced zero trades and zero margin in this window; this is an observed outcome, not a ledger error, because the independent single-symbol run produced the same result.

No gating/threshold logic was added, no SimNow order paths were touched, and no claim of production readiness was made.

---

## Manual Verification

Commands run natively for this acceptance:

```bash
# 1. Produce the ledger report
python examples/czsc_strategy/diagnostics/portfolio_ledger_report.py --verbose

# 2. Re-run independent per-symbol checks
python examples/czsc_strategy/diagnostics/portfolio_ledger_acceptance_check.py

# 3. Unit tests
python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"

# 4. Sync gates
python tools/sync_check.py
python tools/sync_check.py --root examples/czsc_strategy

# 5. Preflight
powershell -ExecutionPolicy Bypass -File examples/czsc_strategy/diagnostics/run_next_work.ps1 -Preflight
```

Counts from the report run:

- Symbols run: 5
- Portfolio ledger rows: 19,470
- Total realized currency PnL: -65,463.57
- Max margin utilization: 6.49%

Test results:

- Unit tests (`not realdb`): **729 passed, 4 deselected**
- `python tools/sync_check.py`: **PASS**
- `python tools/sync_check.py --root examples/czsc_strategy`: **PASS**
- `run_next_work.ps1 -Preflight`: **Preflight complete; 191 SimNow unit tests passed**
