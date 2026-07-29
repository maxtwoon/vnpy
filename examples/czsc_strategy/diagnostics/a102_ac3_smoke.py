"""
A102 AC3 目标组合端到端冒烟（只读诊断）
=========================================
目标组合：trade_freq="5分钟" + filter_freq="30分钟" + resonance_filter="daily_4h"。

窗口说明（HANDOFF 决策记录）：设计 AC3 未指定窗口；受单次会话算力约束，
本冒烟用 2025-01-01 ~ 2025-03-31（3个月，覆盖 5分钟 bar ~6k~9k 根/品种，
warmup_bars=1500 保证 30分钟/4H 过滤层预热充足）。目的是验证"管线端到端
跑通 + 级别标签正确 + profile 生效 + 降级计数"，不构成任何绩效结论。

用法：python diagnostics/a102_ac3_smoke.py <SYMBOL>
输出：diagnostics/a102_ac3_<symbol>_20260729.json

铁律：只读；RESEARCH-ONLY；不作为盈利能力证明。
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from chan_strategy.backtest_engine import BacktestEngine  # noqa: E402
from chan_strategy.config import STRATEGY_CONFIG, BACKTEST_CONFIG  # noqa: E402

WINDOW = ("2025-01-01", "2025-03-31")
WARMUP_BARS = 1500


def main(symbol: str) -> int:
    table = f"{symbol.lower()}_1m_raw"
    original = dict(STRATEGY_CONFIG)
    try:
        STRATEGY_CONFIG["trade_freq"] = "5分钟"
        STRATEGY_CONFIG["filter_freq"] = "30分钟"
        STRATEGY_CONFIG["resonance_filter"] = "daily_4h"
        engine = BacktestEngine(
            symbol, start_date=WINDOW[0], end_date=WINDOW[1], table_name=table,
        )
        report = engine.run(warmup_bars=WARMUP_BARS)
    finally:
        STRATEGY_CONFIG.clear()
        STRATEGY_CONFIG.update(original)

    if "error" in report:
        print(f"!! {symbol} 回测失败: {report['error']}")

    # 冒烟附加统计：级别标签存在性 + 成本占比（设计 §6 风险2）
    extra = {
        "ac3_window": list(WINDOW),
        "ac3_warmup_bars": WARMUP_BARS,
        "ac3_config": {"trade_freq": "5分钟", "filter_freq": "30分钟",
                       "resonance_filter": "daily_4h"},
    }
    if "error" not in report:
        keys = set()
        for rec in engine.signal_history:
            keys.update(rec["signals"])
        extra["label_check"] = {
            "has_5min_keys": any(k.startswith("5分钟_") for k in keys),
            "has_30min_filter_keys": any(k.startswith("30分钟_") for k in keys),
            "has_4h_keys": any(k.startswith("240分钟_") for k in keys),
            "has_daily_keys": any(k.startswith("日线_") for k in keys),
        }
        trades = report.get("total_trades", 0)
        if trades:
            cost = (2 * BACKTEST_CONFIG["commission_rate"] + BACKTEST_CONFIG["slippage"]) * 100
            extra["round_trip_cost_pct_per_trade"] = round(cost, 4)
    report = {**report, **extra}

    out = Path(__file__).parent / f"a102_ac3_{symbol.lower()}_20260729.json"
    out.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    print(f"落盘: {out}")
    if "error" not in report:
        print(f"  trades={report.get('total_trades')} 标签检查={extra.get('label_check')}")
    return 0 if "error" not in report else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
