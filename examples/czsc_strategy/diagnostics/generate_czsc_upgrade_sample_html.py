"""Generate a sample HTML report from czsc 1.0.0rc8 fixtures.

<!-- RESEARCH-ONLY / NOT PROMOTION EVIDENCE -->
This script builds a minimal HTML report using the same ``html_report.py`` path
as production backtests, but fed from the 1.0.0rc8 diagnostic fixtures. It exists
only to provide a visual smoke-test artifact for the czsc 1.0 upgrade.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from chan_strategy.html_report import render_backtest_html_report  # noqa: E402


FIXTURES_DIR = ROOT / "diagnostics" / "czsc_upgrade_fixtures" / "1_0_0rc8"
OUT_PATH = ROOT / "diagnostics" / "czsc_upgrade_sample_report.html"


def _build_payload(symbol: str, data: dict[str, Any], max_bars: int = 2000) -> dict[str, Any]:
    """Convert a fixture JSON into the payload expected by html_report."""
    raw_bars = data.get("bars_raw", [])
    if len(raw_bars) > max_bars:
        raw_bars = raw_bars[-max_bars:]

    kline = [
        {
            "dt": datetime.fromisoformat(bar["dt"]),
            "open": bar["open"],
            "close": bar["close"],
            "high": bar["high"],
            "low": bar["low"],
            "vol": bar["vol"],
        }
        for bar in raw_bars
    ]

    bi = []
    for b in data.get("bi_list", []):
        # html_report expects one point per分型 + last end; emulate with end points.
        bi.append(
            {
                "dt": datetime.fromisoformat(b["edt"]),
                "fx_mark": "d" if b["direction"] == "Direction.Up" else "g",
                "start_dt": datetime.fromisoformat(b["sdt"]),
                "end_dt": datetime.fromisoformat(b["edt"]),
                "fx_high": b["high"],
                "fx_low": b["low"],
                "bi": b["high"] if b["direction"] == "Direction.Up" else b["low"],
            }
        )

    zs = [
        {
            "start_dt": datetime.fromisoformat(z["sdt"]),
            "end_dt": datetime.fromisoformat(z["edt"]),
            "zd": z["zd"],
            "zg": z["zg"],
        }
        for z in data.get("zs_list", [])
        if z.get("sdt") and z.get("edt")
    ]

    return {
        "kline": kline,
        "bi": bi,
        "xd": [],
        "zs": zs,
        "bs": [],
        "trades_table": [],
        "summary": {
            "symbol": symbol,
            "period": f"{data['first_bar_dt']} ~ {data['last_bar_dt']}",
            "total_trades": 0,
            "win_rate": 0.0,
            "total_return_pct": 0.0,
            "max_drawdown_pct": 0.0,
            "sharpe_ratio": 0.0,
        },
    }


def main() -> None:
    payloads: dict[str, dict[str, Any]] = {}
    for path in sorted(FIXTURES_DIR.glob("*.json")):
        if path.name == "summary.json":
            continue
        symbol = path.stem
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        payloads[symbol] = _build_payload(symbol, data)
        break  # single-symbol sample to keep artifact size reasonable

    render_backtest_html_report(payloads, out_path=OUT_PATH, title="czsc 1.0.0rc8 升级样本报告")
    print(f"Sample HTML report written to {OUT_PATH}")


if __name__ == "__main__":
    main()
