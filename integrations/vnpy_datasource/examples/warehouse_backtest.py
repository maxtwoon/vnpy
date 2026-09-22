"""End-to-end check: local warehouse snapshot -> research SQLite -> vnpy CTA backtest.

Run from D:\\repo\\vnpy with the registered vnpy interpreter:

    C:/Python314/python.exe D:/repo/quant/scripts/runtime.py run vnpy -- integrations/vnpy_datasource/examples/warehouse_backtest.py <research-dir> --snapshot-id <id> --output <new-dir>

It points ``database.database`` at the research directory for this process only
(no global vt_setting.json change), loads bars through vnpy's own database layer and
runs DoubleMaStrategy on 159915.SZSE daily bars. The snapshot id printed at the end is
what should be written into any backtest result for reproducibility.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('research_dir', nargs='?', default='D:/repo/vnpy/research_data/wh_etf_sqlite')
    parser.add_argument('--snapshot-id', required=True, help='fixed warehouse snapshot; never current/latest')
    parser.add_argument('--output', type=Path, help='new result directory')
    parser.add_argument('--start', default='2024-01-01')
    parser.add_argument('--end', default='2026-09-18')
    args = parser.parse_args()
    start = datetime.fromisoformat(args.start).replace(tzinfo=ZoneInfo('Asia/Shanghai'))
    end = datetime.fromisoformat(args.end).replace(hour=23, minute=59, second=59, tzinfo=ZoneInfo('Asia/Shanghai'))
    if start >= end:
        raise ValueError('Start must precede end')
    if args.snapshot_id.lower() in {'latest', 'current'}:
        raise ValueError('A fixed snapshot identifier is required')
    RESEARCH_DIR = Path(args.research_dir).resolve()
    database_path = RESEARCH_DIR / 'database.db'
    if not database_path.is_file():
        raise ValueError('Research database missing; no simulated fallback')
    database_hash = hashlib.sha256(database_path.read_bytes()).hexdigest()
    from vnpy.trader.setting import SETTINGS
    SETTINGS['database.name'] = 'sqlite'
    SETTINGS['database.database'] = str(database_path)
    from vnpy.trader.constant import Exchange, Interval
    from vnpy.trader.database import get_database
    from vnpy_ctastrategy.backtesting import BacktestingEngine
    from vnpy_ctastrategy.strategies.double_ma_strategy import DoubleMaStrategy

    manifest = json.loads((RESEARCH_DIR / "datasource-manifest.json").read_text(encoding="utf-8"))
    receipts = [json.loads((RESEARCH_DIR / r).read_text(encoding="utf-8")) for r in manifest["receipts"]]
    snapshots = sorted({r.get("snapshot_id") for r in receipts if r.get("snapshot_id")})
    if snapshots != [args.snapshot_id] or any(r.get('storage_status') != 'verified' for r in receipts):
        raise ValueError('Receipts do not identify exactly the requested verified warehouse snapshot')
    if args.output:
        args.output.mkdir(parents=True, exist_ok=False)
    print("research dir:", RESEARCH_DIR)
    print("adjustment:", manifest["adjustment"], "| warehouse snapshot(s):", snapshots)

    db = get_database()
    overview = {(o.symbol, o.exchange.value, o.interval.value): (o.count, o.start, o.end) for o in db.get_bar_overview()}
    print("database overview:", overview)
    bars = db.load_bar_data("159915", Exchange.SZSE, Interval.DAILY, start, end)
    if not bars:
        print("no bars loaded from research database")
        return 1
    print(f"loaded {len(bars)} bars {bars[0].datetime.date()} -> {bars[-1].datetime.date()}, last close {bars[-1].close_price}")

    engine = BacktestingEngine()
    engine.set_parameters(vt_symbol="159915.SZSE", interval=Interval.DAILY,
                          start=start, end=end,
                          rate=0.0001, slippage=0.001, size=1, pricetick=0.001, capital=100_000)
    engine.add_strategy(DoubleMaStrategy, {"fast_window": 10, "slow_window": 20})
    # The installed SQLite adapter uses an exclusive upper bound. CTA's chunk
    # loader skips boundary dates with that adapter. Pin one complete read while
    # retaining the unmodified framework replay, matching and PnL calculation.
    if len({bar.datetime for bar in bars}) != len(bars):
        raise ValueError('Duplicate input bars')
    engine.history_data = bars
    engine.run_backtesting()
    if len(engine.daily_results) != len({bar.datetime.date() for bar in bars}):
        raise ValueError('CTA replay did not process the complete input')
    daily = engine.calculate_result()
    stats = engine.calculate_statistics(output=False)
    keys = ("start_date", "end_date", "total_days", "total_trade_count", "total_return", "annual_return", "max_ddpercent", "sharpe_ratio")
    print("backtest:", {k: stats.get(k) for k in keys})
    print("record in results ->", {"warehouse_snapshot_id": snapshots, "adjustment": manifest["adjustment"], "database": SETTINGS["database.database"]})
    if hashlib.sha256(database_path.read_bytes()).hexdigest() != database_hash:
        raise ValueError('Research input changed during backtest')
    if args.output:
        payload = {'warehouse_snapshot_id': args.snapshot_id, 'database_sha256': database_hash,
                   'adjustment': manifest['adjustment'], 'metrics': {k: stats.get(k) for k in keys},
                   'engine': 'vnpy_ctastrategy.BacktestingEngine',
                   'constraints': 'Daily limit-order bar matching; no exchange queue or ETF T+1/limit-up/down model. Research example only.',
                   'fee_rate': 0.0001, 'slippage': 0.001}
        payload.update(input_rows=len(bars), replay_rows=len(engine.history_data),
                       actual_start=bars[0].datetime.isoformat(), actual_end=bars[-1].datetime.isoformat(),
                       strategy='DoubleMaStrategy', contains_mock_data=False,
                       backtest_framework='vnpy', position_size=1, capital=100000)
        payload['input_adapter'] = 'single fixed SQLite read; bypass chunk boundary omission'
        payload['metrics'] = {k: v.item() if hasattr(v, 'item') else v for k, v in payload['metrics'].items()}
        daily.to_csv(args.output / 'daily.csv')
        (args.output / 'result.json').write_text(json.dumps(payload, ensure_ascii=False, default=str, indent=2), encoding='utf-8')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
