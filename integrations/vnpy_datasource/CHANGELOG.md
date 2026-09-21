# Changelog

## 0.2.0 — 2026-09-21

- Read the dataSource local backtest warehouse first (`WarehouseReader`: DuckDB over fixed Parquet snapshots, `snapshot_id` on every result and receipt); the isolated online process remains the fallback.
- Add `load-warehouse` CLI to bulk-load symbols from a (pinnable) snapshot into an independent SQLite/Alpha research directory via the existing verified `save_history` path.
- Add `examples/warehouse_backtest.py` (warehouse → SQLite → vnpy database → CTA backtest) and tests for mapping, minute relabelling, paused/missing-volume handling and live snapshot reproducibility.
- Settings: `datafeed.datasource_prefer_warehouse` (default true), `datafeed.datasource_snapshot`.

## 0.1.0 — 2026-09-16

- Connect VeighNa Datafeed and research scripts to the current local dataSource registry through its maintained runtime.
- Add allowlisted read-only providers, explicit status/fallback results, closed-bar validation and provenance.
- Add independent SQLite/Alpha exports, CLI, examples and real-data verification.
- Exclude unverified Chinese minute data and preserve the archived Chan project boundary.
