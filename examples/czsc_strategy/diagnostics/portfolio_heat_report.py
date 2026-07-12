"""A48 P8b — Portfolio heat diagnostic report.

Reads the post-2026-04-24 honest baseline window and reports cluster gross
exposure over time, daily-loss-limit trigger days, and risk-parity vs fixed
weights.  This script is read-only evidence; it does not select or tune
``cluster_gross_cap``, ``daily_loss_limit_pct`` or ``corr_clusters`` membership.

RESEARCH-ONLY — Diagnostic only, not a trading recommendation.
"""
from __future__ import annotations

import argparse
import copy
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from chan_strategy.config import SQLITE_DB_PATH, STRATEGY_CONFIG  # noqa: E402
from chan_strategy.portfolio_engine import PortfolioEngine  # noqa: E402
from diagnostics.backtest_matrix_report import DEFAULT_SYMBOLS, _dominant_symbol  # noqa: E402


WINDOW_START = "2026-04-24"
WINDOW_END = "2026-07-09"


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    if isinstance(value, tuple):
        return [_json_safe(v) for v in value]
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return str(value)
    return value


def _fmt_pct(value: float | int | None) -> str:
    if value is None:
        return "-"
    return f"{float(value) * 100:.2f}%"


def _fmt_num(value: float | int | None, digits: int = 2) -> str:
    if value is None:
        return "-"
    if isinstance(value, int):
        return f"{value:,}"
    return f"{float(value):,.{digits}f}"


def _resolve_table_names(db_path: Path, symbols: list[str], start: str, end: str) -> dict[str, str]:
    """Resolve explicit 1M raw table names to avoid ambiguous auto-detection.

    The returned dict keeps the original requested ``symbol`` as the key so that
    downstream reports and the portfolio coordinator refer to symbols with the
    canonical casing used everywhere else (e.g. AP888, RB888).  The actual
    stored symbol casing does not matter because the data adapter matches with
    ``COLLATE NOCASE``.
    """
    table_names: dict[str, str] = {}
    for symbol in symbols:
        table_name = f"{symbol.lower()}_1M_raw"
        # Validate that the table has data for the requested range, but keep
        # the original symbol as the canonical key.
        _dominant_symbol(db_path, table_name, start, end)
        table_names[symbol] = table_name
    return table_names


def _run_scenario(
    db_path: Path,
    symbols: list[str],
    start: str,
    end: str,
    weighting: str,
) -> dict[str, Any]:
    """Run PortfolioEngine under portfolio_risk='on' with the given weighting."""
    original = copy.deepcopy(STRATEGY_CONFIG)
    try:
        STRATEGY_CONFIG["portfolio_risk"] = "on"
        STRATEGY_CONFIG["weighting"] = weighting

        table_names = _resolve_table_names(db_path, symbols, start, end)
        engine = PortfolioEngine(
            symbols=list(table_names.keys()),
            db_path=str(db_path),
            start_date=start,
            end_date=end,
            table_names=table_names,
        )
        report = engine.run()

        # Aggregate cluster exposure series.
        cluster_series: dict[str, list[tuple[str, float]]] = {}
        daily_max_exposure: dict[str, dict[str, float]] = {}
        for row in report["equity_curve"]:
            day = str(row["dt"].date())
            for cluster, exposure in (row.get("cluster_exposure") or {}).items():
                cluster_series.setdefault(cluster, []).append((day, exposure))
                daily_max_exposure.setdefault(cluster, {})[day] = max(
                    daily_max_exposure.get(cluster, {}).get(day, 0.0),
                    exposure,
                )

        # Final average symbol weights (risk parity only meaningful when online).
        avg_weights: dict[str, float] = {}
        if report["equity_curve"]:
            for symbol in report["symbols"]:
                values = [
                    row.get("symbol_weights", {}).get(symbol, 0.0)
                    for row in report["equity_curve"]
                ]
                avg_weights[symbol] = float(np.mean(values)) if values else 0.0

        return {
            "weighting": weighting,
            "equity_curve": report["equity_curve"],
            "pairs": report["pairs"],
            "blocked_opens": report.get("blocked_opens", []),
            "loss_limit_triggers": report.get("loss_limit_triggers", []),
            "flat_events": report.get("flat_events", []),
            "cluster_series": cluster_series,
            "daily_max_cluster_exposure": daily_max_exposure,
            "avg_symbol_weights": avg_weights,
            "symbol_errors": report.get("symbol_errors", {}),
            "successful_symbols": report.get("symbols", []),
        }
    finally:
        STRATEGY_CONFIG.clear()
        STRATEGY_CONFIG.update(original)


def _cluster_summary(daily_max: dict[str, dict[str, float]]) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    for cluster, days in daily_max.items():
        values = list(days.values())
        out[cluster] = {
            "max": max(values) if values else 0.0,
            "mean": float(np.mean(values)) if values else 0.0,
            "days_over_50pct": sum(1 for v in values if v > 0.5),
            "days_over_80pct": sum(1 for v in values if v > 0.8),
        }
    return out


def _equity_metrics(equity_curve: list[dict[str, Any]]) -> dict[str, float]:
    if not equity_curve:
        return {"total_return_pct": 0.0, "max_drawdown_pct": 0.0}
    values = pd.Series(
        [r["equity"] for r in equity_curve],
        index=[r["dt"] for r in equity_curve],
    )
    total_return = float(values.iloc[-1] / values.iloc[0] - 1)
    peak = values.cummax()
    dd = (peak - values) / peak
    return {
        "total_return_pct": total_return * 100,
        "max_drawdown_pct": float(dd.max()) * 100,
    }


def build_report(
    db_path: Path,
    symbols: list[str],
    start: str,
    end: str,
) -> dict[str, Any]:
    fixed = _run_scenario(db_path, symbols, start, end, "fixed")
    risk_parity = _run_scenario(db_path, symbols, start, end, "risk_parity")

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "db_path": str(db_path),
        "window_start": start,
        "window_end": end,
        "symbols": symbols,
        "successful_symbols": fixed["successful_symbols"],
        "symbol_errors": fixed["symbol_errors"],
        "cluster_gross_cap": STRATEGY_CONFIG.get("cluster_gross_cap", 1.0),
        "daily_loss_limit_pct": STRATEGY_CONFIG.get("daily_loss_limit_pct", 0.03),
        "corr_clusters": dict(STRATEGY_CONFIG.get("corr_clusters") or {}),
        "fixed": {
            "metrics": _equity_metrics(fixed["equity_curve"]),
            "cluster_summary": _cluster_summary(fixed["daily_max_cluster_exposure"]),
            "loss_limit_days": len(fixed["loss_limit_triggers"]),
            "blocked_open_count": len(fixed["blocked_opens"]),
            "avg_symbol_weights": fixed["avg_symbol_weights"],
        },
        "risk_parity": {
            "metrics": _equity_metrics(risk_parity["equity_curve"]),
            "cluster_summary": _cluster_summary(risk_parity["daily_max_cluster_exposure"]),
            "loss_limit_days": len(risk_parity["loss_limit_triggers"]),
            "blocked_open_count": len(risk_parity["blocked_opens"]),
            "avg_symbol_weights": risk_parity["avg_symbol_weights"],
        },
        "raw_fixed": fixed,
        "raw_risk_parity": risk_parity,
    }


def write_markdown(payload: dict[str, Any], path: Path) -> None:
    lines = [
        "# Portfolio Heat Report",
        "",
        "**RESEARCH-ONLY — Diagnostic only, not a trading recommendation.**",
        "",
        f"- Generated at: {payload['generated_at']}",
        f"- Window: `{payload['window_start']}` ~ `{payload['window_end']}`",
        f"- Symbols: `{' / '.join(payload['symbols'])}`",
        f"- Cluster cap: `{payload['cluster_gross_cap']}`",
        f"- Daily loss limit: `{payload['daily_loss_limit_pct'] * 100:.2f}%`",
        f"- Clusters: `{json.dumps(payload['corr_clusters'], ensure_ascii=False)}`",
        "",
        "## Symbol Availability",
        "",
    ]
    errors = payload.get("symbol_errors", {})
    successful = set(payload.get("successful_symbols", []))
    for symbol in payload["symbols"]:
        if symbol in errors:
            lines.append(f"- **{symbol}**: excluded — {errors[symbol]}")
        elif symbol in successful:
            lines.append(f"- **{symbol}**: included")
        else:
            lines.append(f"- **{symbol}**: excluded — no data")
    lines.append("")

    lines.extend([
        "## Fixed vs Risk-Parity Weights",
        "",
        "Weights are shown relative to the set of successfully backtested symbols.",
        "",
        "| Symbol | Fixed weight | Risk-parity avg weight |",
        "|---|---:|---:|",
    ])
    for symbol in payload.get("successful_symbols", payload["symbols"]):
        fixed_w = payload["fixed"]["avg_symbol_weights"].get(symbol, 0.0)
        rp_w = payload["risk_parity"]["avg_symbol_weights"].get(symbol, 0.0)
        lines.append(f"| {symbol} | {_fmt_pct(fixed_w)} | {_fmt_pct(rp_w)} |")

    lines.extend([
        "",
        "## Portfolio-Level Metrics",
        "",
        "| Weighting | Total return | Max drawdown | Loss-limit days | Blocked opens |",
        "|---|---:|---:|---:|---:|",
    ])
    for key, label in [("fixed", "fixed"), ("risk_parity", "risk_parity")]:
        section = payload[key]
        metrics = section["metrics"]
        lines.append(
            f"| {label} | {_fmt_pct(metrics['total_return_pct'] / 100)} | "
            f"{_fmt_pct(metrics['max_drawdown_pct'] / 100)} | "
            f"{_fmt_num(section['loss_limit_days'], 0)} | "
            f"{_fmt_num(section['blocked_open_count'], 0)} |"
        )

    lines.extend([
        "",
        "## Cluster Gross Exposure Summary",
        "",
        "| Cluster | Weighting | Max daily gross | Mean daily gross | Days > 50% | Days > 80% |",
        "|---|---|---:|---:|---:|---:|",
    ])
    for key, label in [("fixed", "fixed"), ("risk_parity", "risk_parity")]:
        for cluster, stats in payload[key]["cluster_summary"].items():
            lines.append(
                f"| {cluster} | {label} | {_fmt_pct(stats['max'])} | "
                f"{_fmt_pct(stats['mean'])} | {_fmt_num(stats['days_over_50pct'], 0)} | "
                f"{_fmt_num(stats['days_over_80pct'], 0)} |"
            )

    lines.extend([
        "",
        "## Loss-Limit Trigger Days",
        "",
    ])
    for key, label in [("fixed", "fixed"), ("risk_parity", "risk_parity")]:
        triggers = payload[f"raw_{key}"]["loss_limit_triggers"]
        lines.append(f"### {label}")
        if not triggers:
            lines.append("_No loss-limit triggers in this window._")
        else:
            lines.extend([
                "| Date | Equity | Day PnL |",
                "|---|---:|---:|",
            ])
            for t in triggers:
                lines.append(
                    f"| {t['trading_day']} | {_fmt_num(t['equity'])} | {_fmt_pct(t['day_pnl_pct'])} |"
                )
        lines.append("")

    lines.extend([
        "",
        "## Notes",
        "",
        "- This report is evidence-only.  It is not used to select or tune ",
        "  ``cluster_gross_cap``, ``daily_loss_limit_pct`` or ``corr_clusters`` membership.",
        "- Risk-parity weights are estimated online from rolling per-symbol volatility;",
        "  no future bars are used.",
        "- The coordinator is backtest-only and does not route live orders.",
        "",
    ])

    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Portfolio heat diagnostic report (P8b).")
    parser.add_argument("--db-path", type=Path, default=Path(SQLITE_DB_PATH))
    parser.add_argument("--symbols", nargs="+", default=DEFAULT_SYMBOLS)
    parser.add_argument("--start", default=WINDOW_START)
    parser.add_argument("--end", default=WINDOW_END)
    parser.add_argument("--out-json", type=Path, default=None)
    parser.add_argument("--out-md", type=Path, default=None)
    args = parser.parse_args()

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out_json = args.out_json or Path(__file__).with_name(f"portfolio_heat_report_{today}.json")
    out_md = args.out_md or Path(__file__).with_name(f"portfolio_heat_report_{today}.md")

    payload = build_report(args.db_path, args.symbols, args.start, args.end)
    out_json.write_text(json.dumps(_json_safe(payload), ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(payload, out_md)
    print(f"wrote {out_json}")
    print(f"wrote {out_md}")


if __name__ == "__main__":
    main()
