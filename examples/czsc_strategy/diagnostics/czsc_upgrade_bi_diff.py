"""Compare czsc 0.9.51 vs 1.0.0rc8 structural outputs on real historical data.

<!-- RESEARCH-ONLY / NOT PROMOTION EVIDENCE -->
This diagnostic script is research-only. It loads real 1-minute futures data,
resamples to the strategy's 30-minute trade frequency, and records the structural
outputs (fx, bi, zhongshu, signals) produced by the installed czsc version.
Run it once under czsc==0.9.51 to capture a golden fixture, then again under
czsc==1.0.0rc8 to quantify the behavioral differences introduced by the Rust
rewrite.

Two important environment-aware behaviours are baked in so the report can
disclose them honestly:

* ``CZSC_MAX_BI_NUM`` is read at import time.  The script records the value
  actually used, so the downstream report can state whether the default cap
  of 50 was binding for this dataset.
* Signal history is captured **per bar** by incrementally updating a ``CZSC``
  object.  This gives "trigger count + timestamp" statistics instead of a
  single terminal snapshot.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# Make chan_strategy importable regardless of cwd.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import czsc  # noqa: E402
from chan_strategy.config import SQLITE_DB_PATH, STRATEGY_CONFIG  # noqa: E402
from chan_strategy.data_adapter import SqliteDataAdapter, resample_bars  # noqa: E402
from chan_strategy.sell_signals import get_all_signals  # noqa: E402
from chan_strategy.zhongshu import build_zhongshu_from_bis  # noqa: E402
from czsc import CZSC, Freq, RawBar  # noqa: E402


SYMBOLS: list[str] = list(STRATEGY_CONFIG.get("contract_specs", {}).keys())
TRADE_FREQ_MINUTES: int = 30
TRADE_FREQ_LABEL: str = "30分钟"
START_DATE: str = "2023-01-01"
END_DATE: str = "2025-12-31"

# czsc reads this at import time; re-export the effective value for the report.
_MAX_BI_NUM_ENV = os.environ.get("CZSC_MAX_BI_NUM")
MAX_BI_NUM_USED: int = czsc.envs.get_max_bi_num()


def _table_name(symbol: str) -> str:
    return f"{symbol.lower()}_1M_raw"


def _load_trade_bars(symbol: str) -> list[RawBar]:
    adapter = SqliteDataAdapter(SQLITE_DB_PATH)
    table = _table_name(symbol)
    minute_bars = adapter.load_raw_bars(
        symbol=symbol,
        freq="1",
        start_date=START_DATE,
        end_date=END_DATE,
        table_name=table,
    )
    if not minute_bars:
        raise ValueError(f"No 1-minute data loaded for {symbol}")
    trade_bars = resample_bars(
        minute_bars,
        target_freq=Freq.F30,
        target_minutes=TRADE_FREQ_MINUTES,
        daily_agg=STRATEGY_CONFIG.get("daily_agg", "natural"),
        night_session_start_hour=STRATEGY_CONFIG.get("night_session_start_hour", 20),
    )
    return trade_bars


def _serialize_fx(fx: Any) -> dict[str, Any]:
    return {
        "dt": fx.dt.isoformat() if hasattr(fx, "dt") else None,
        "mark": str(fx.mark) if hasattr(fx, "mark") else None,
        "high": float(fx.high) if hasattr(fx, "high") else None,
        "low": float(fx.low) if hasattr(fx, "low") else None,
    }


def _serialize_bar(bar: RawBar) -> dict[str, Any]:
    return {
        "dt": bar.dt.isoformat(),
        "open": float(bar.open),
        "close": float(bar.close),
        "high": float(bar.high),
        "low": float(bar.low),
        "vol": float(bar.vol),
    }


def _serialize_bi(bi: Any) -> dict[str, Any]:
    return {
        "direction": str(bi.direction) if hasattr(bi, "direction") else None,
        "sdt": bi.sdt.isoformat() if hasattr(bi, "sdt") else None,
        "edt": bi.edt.isoformat() if hasattr(bi, "edt") else None,
        "high": float(bi.high) if hasattr(bi, "high") else None,
        "low": float(bi.low) if hasattr(bi, "low") else None,
        "power": float(bi.power) if hasattr(bi, "power") else None,
    }


def _serialize_zs(zs: Any) -> dict[str, Any]:
    return {
        "zg": float(zs.zg) if hasattr(zs, "zg") else None,
        "zd": float(zs.zd) if hasattr(zs, "zd") else None,
        "gg": float(zs.gg) if hasattr(zs, "gg") else None,
        "dd": float(zs.dd) if hasattr(zs, "dd") else None,
        "n_bis": len(zs.bis) if hasattr(zs, "bis") else None,
        "sdt": zs.start_dt.isoformat() if hasattr(zs, "start_dt") else None,
        "edt": zs.end_dt.isoformat() if hasattr(zs, "end_dt") else None,
    }


def _filter_signal_keys(signals: dict[str, str]) -> dict[str, str]:
    """Retain only signal keys that describe buy/sell/divergence/risk events."""
    kept: dict[str, str] = {}
    for key, value in signals.items():
        lower_key = key.lower()
        if any(tok in lower_key for tok in ("一买", "二买", "三买", "一卖", "二卖", "三卖", "背驰", "风控", "结构失效")):
            kept[key] = value
    return kept


def _signal_transitions(bars: list[RawBar]) -> list[dict[str, Any]]:
    """Return every (bar_dt, key, old_value, new_value) change for filtered signals.

    ``CZSC`` cannot be constructed from an empty bar list in either 0.9.51 or
    1.0.0rc8, so the first bar seeds the object and every subsequent bar is fed
    via ``update``.  The first snapshot is treated as the baseline.
    """
    if not bars:
        return []

    czsc_obj = CZSC([bars[0]])
    prev = _filter_signal_keys(get_all_signals(czsc_obj, freq=TRADE_FREQ_LABEL))
    transitions: list[dict[str, Any]] = []

    for bar in bars[1:]:
        czsc_obj.update(bar)
        cur = _filter_signal_keys(get_all_signals(czsc_obj, freq=TRADE_FREQ_LABEL))
        for key, new_value in cur.items():
            old_value = prev.get(key)
            if old_value != new_value:
                transitions.append(
                    {
                        "dt": bar.dt.isoformat(),
                        "key": key,
                        "old": old_value,
                        "new": new_value,
                    }
                )
        prev = cur

    return transitions


def analyze_symbol(symbol: str) -> dict[str, Any]:
    trade_bars = _load_trade_bars(symbol)
    czsc_obj = CZSC(trade_bars)

    bis = list(czsc_obj.bi_list) if hasattr(czsc_obj, "bi_list") else []
    fx_list = list(czsc_obj.fx_list) if hasattr(czsc_obj, "fx_list") else []

    # Use the same confirmed-bi logic as the production signal path.
    confirmed_bis = list(czsc_obj.finished_bis) if hasattr(czsc_obj, "finished_bis") else bis
    if confirmed_bis and hasattr(czsc_obj, "last_bi_extend") and czsc_obj.last_bi_extend:
        confirmed_bis = confirmed_bis[:-1]

    zs_list = build_zhongshu_from_bis(confirmed_bis) if confirmed_bis else []
    terminal_signals = get_all_signals(czsc_obj, freq=TRADE_FREQ_LABEL)

    return {
        "symbol": symbol,
        "czsc_version": czsc.__version__,
        "bars_count": len(trade_bars),
        "first_bar_dt": trade_bars[0].dt.isoformat() if trade_bars else None,
        "last_bar_dt": trade_bars[-1].dt.isoformat() if trade_bars else None,
        "fx_count": len(fx_list),
        "bi_count": len(bis),
        "confirmed_bi_count": len(confirmed_bis),
        "zs_count": len(zs_list),
        "bars_raw": [_serialize_bar(bar) for bar in trade_bars],
        "fx_list": [_serialize_fx(fx) for fx in fx_list],
        "bi_list": [_serialize_bi(bi) for bi in bis],
        "zs_list": [_serialize_zs(zs) for zs in zs_list],
        "signals": _filter_signal_keys(terminal_signals),
        "signal_transitions": _signal_transitions(trade_bars),
    }


def _analyze_one(symbol: str, out_dir: Path) -> dict[str, Any]:
    print(f"Analyzing {symbol} ...")
    result = analyze_symbol(symbol)
    out_path = out_dir / f"{symbol}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"  wrote {out_path}")
    return {
        "bars_count": result["bars_count"],
        "fx_count": result["fx_count"],
        "bi_count": result["bi_count"],
        "confirmed_bi_count": result["confirmed_bi_count"],
        "zs_count": result["zs_count"],
        "signal_transitions": len(result["signal_transitions"]),
    }


def _regenerate_summary(out_dir: Path) -> None:
    """Rebuild summary.json from existing symbol JSON files."""
    summary: dict[str, Any] = {
        "czsc_version": czsc.__version__,
        "generated_at": datetime.now().isoformat(),
        "symbols": [],
        "trade_freq_label": TRADE_FREQ_LABEL,
        "trade_freq_minutes": TRADE_FREQ_MINUTES,
        "start_date": START_DATE,
        "end_date": END_DATE,
        "max_bi_num_used": MAX_BI_NUM_USED,
        "max_bi_num_env": _MAX_BI_NUM_ENV,
        "symbol_summaries": {},
    }
    for path in sorted(out_dir.glob("*.json")):
        if path.name == "summary.json":
            continue
        symbol = path.stem
        data = json.loads(path.read_text(encoding="utf-8"))
        summary["symbols"].append(symbol)
        summary["symbol_summaries"][symbol] = {
            "bars_count": data["bars_count"],
            "fx_count": data["fx_count"],
            "bi_count": data["bi_count"],
            "confirmed_bi_count": data["confirmed_bi_count"],
            "zs_count": data["zs_count"],
            "signal_transitions": len(data["signal_transitions"]),
        }
    summary_path = out_dir / "summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"Summary written to {summary_path}")


def main(argv: list[str] | None = None) -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Capture czsc structural/signal fixtures")
    parser.add_argument("--symbol", default=None, help="Analyze only this symbol")
    parser.add_argument(
        "--regenerate-summary",
        action="store_true",
        help="Rebuild summary.json from existing symbol fixtures",
    )
    args = parser.parse_args(argv)

    version_slug = czsc.__version__.replace(".", "_")
    out_dir = Path(__file__).resolve().parent / "czsc_upgrade_fixtures" / version_slug
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.regenerate_summary:
        _regenerate_summary(out_dir)
        return

    symbols = [args.symbol] if args.symbol else SYMBOLS
    for symbol in symbols:
        _analyze_one(symbol, out_dir)

    if not args.symbol:
        _regenerate_summary(out_dir)


if __name__ == "__main__":
    main()
