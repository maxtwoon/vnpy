"""Portfolio-level coordinator for multi-symbol backtests.

P8b (A48) adds a backtest-only cross-symbol coordination layer above the
existing per-symbol :class:`BacktestEngine`.  The coordinator is gated by the
``portfolio_risk`` config key (default ``"off"`` keeps current behavior
byte-identical).  When ``"on"`` it enforces:

* ``weighting="risk_parity"`` – symbol-level weights proportional to 1/vol,
  with sub-strategy weights inside a symbol preserving the legacy 1:2:3 ratio.
* ``corr_clusters`` + ``cluster_gross_cap`` – blocks new opens that would push
  a cluster's summed gross exposure above the cap.
* ``daily_loss_limit_pct`` – flattens all open positions and blocks new opens
  for the remainder of the trading day once the portfolio day-PnL breaches the
  limit.

The coordinator never reads future bars; volatility, daily PnL and cluster
exposure are computed from information known at the current bar only.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd

from chan_strategy.backtest_engine import BacktestEngine
from chan_strategy.config import BACKTEST_CONFIG, STRATEGY_CONFIG
from chan_strategy.portfolio_ledger import PortfolioLedger
from chan_strategy.positions import _research_symbol_key


def _trading_day(
    dt: datetime,
    daily_agg: str = "natural",
    night_session_start_hour: int = 20,
) -> datetime.date:
    """Map a bar timestamp to its trading day.

    Mirrors the semantics used by ``data_adapter.resample_bars`` for the
    ``daily_agg`` config so that portfolio daily boundaries align with the
    strategy's own daily filter.
    """
    if daily_agg == "trading_calendar" and dt.hour >= night_session_start_hour:
        return (dt.date() + timedelta(days=1))
    return dt.date()


def _sub_strategy_relative_weights() -> dict[str, float]:
    """Relative weights inside one symbol: 一买=1, 二买=2, 三买=3, normalized."""
    return {
        "一买多头": 1.0 / 6.0,
        "二买多头": 2.0 / 6.0,
        "三买多头": 3.0 / 6.0,
        "一卖空头": 1.0 / 6.0,
        "二卖空头": 2.0 / 6.0,
        "三卖空头": 3.0 / 6.0,
    }


def _strategy_weight_fixed(strategy: str, symbol: str | None = None) -> float:
    """Legacy fixed weight driven by ``pos_1buy/2buy/3buy`` config keys."""
    overrides = STRATEGY_CONFIG.get("symbol_position_overrides") or {}
    key_map = {
        "一买多头": "pos_1buy",
        "二买多头": "pos_2buy",
        "三买多头": "pos_3buy",
        "一卖空头": "pos_1sell",
        "二卖空头": "pos_2sell",
        "三卖空头": "pos_3sell",
    }
    config_key = key_map.get(strategy, "pos_1buy")
    if symbol is not None:
        item = overrides.get(_research_symbol_key(symbol), None)
        if isinstance(item, dict) and config_key in item:
            return float(item[config_key])
    return float(STRATEGY_CONFIG.get(config_key, 0.10))


def _position_sign(strategy: str) -> int:
    """Return +1 for long sub-strategies and -1 for short sub-strategies."""
    return -1 if "空头" in strategy else 1


class PortfolioCoordinator:
    """Stateful cross-symbol coordinator used during a portfolio replay.

    The coordinator is intentionally decoupled from :class:`BacktestEngine` so
    it can be unit-tested with constructed trade sequences without running a
    full backtest.
    """

    def __init__(
        self,
        symbols: list[str],
        initial_capital: float,
        config: dict[str, Any] | None = None,
    ):
        self.symbols = list(dict.fromkeys(symbols))  # preserve order, dedupe
        self.initial_capital = float(initial_capital)
        self.cfg = config if config is not None else STRATEGY_CONFIG

        self.daily_agg = self.cfg.get("daily_agg", "natural")
        self.night_session_start_hour = int(self.cfg.get("night_session_start_hour", 20))
        self.cluster_gross_cap = float(self.cfg.get("cluster_gross_cap", 1.0))
        self.daily_loss_limit_pct = float(self.cfg.get("daily_loss_limit_pct", 0.03))
        self.lookback = int(self.cfg.get("risk_parity_lookback", 60))
        self.corr_clusters = dict(self.cfg.get("corr_clusters") or {})

        # Online state
        self.symbol_weights: dict[str, float] = {s: 1.0 / len(self.symbols) for s in self.symbols}
        self.return_windows: dict[str, list[float]] = {s: [] for s in self.symbols}
        self.last_prices: dict[str, float] = {}
        self.open_positions: dict[tuple[str, str], dict[str, Any]] = {}
        self.cluster_exposure: dict[str, float] = {name: 0.0 for name in self.corr_clusters}

        self.daily_loss_limit_active: bool = False
        self.current_trading_day: datetime.date | None = None
        self.prev_day_close_equity: float = self.initial_capital
        self.current_equity: float = self.initial_capital

        # Evidence / diagnostics
        self.blocked_opens: list[dict[str, Any]] = []
        self.loss_limit_triggers: list[dict[str, Any]] = []
        self.flat_events: list[dict[str, Any]] = []

    # ------------------------------------------------------------------ helpers
    def _trading_day(self, dt: datetime) -> datetime.date:
        return _trading_day(dt, self.daily_agg, self.night_session_start_hour)

    def _clusters_for_symbol(self, symbol: str) -> list[str]:
        key = str(symbol).upper()
        return [name for name, members in self.corr_clusters.items() if key in {str(m).upper() for m in members}]

    def _position_weight(self, symbol: str, strategy: str) -> float:
        """Signed weight assigned to a new position in (symbol, strategy).

        Long sub-strategies return positive weights, short sub-strategies
        return negative weights.  Cluster exposure and PnL accounting use
        ``abs(weight)`` for gross magnitude while net exposure preserves sign.
        """
        if self.cfg.get("weighting") == "risk_parity":
            rel = _sub_strategy_relative_weights().get(strategy, 1.0 / 6.0)
            return self.symbol_weights.get(symbol, 0.0) * rel * _position_sign(strategy)
        return _strategy_weight_fixed(strategy, symbol) * _position_sign(strategy)

    # ------------------------------------------------------------------ updates
    def _update_volatility(self, dt: datetime, prices: dict[str, float]) -> None:
        """Update rolling volatility and symbol weights using only past bars."""
        for symbol in self.symbols:
            price = prices.get(symbol)
            if price is None:
                continue
            last = self.last_prices.get(symbol)
            if last is not None and last > 0:
                ret = (price - last) / last
                window = self.return_windows[symbol]
                window.append(ret)
                if len(window) > self.lookback:
                    window.pop(0)
            self.last_prices[symbol] = price

        if self.cfg.get("weighting") == "risk_parity":
            inv_vols: dict[str, float] = {}
            for symbol in self.symbols:
                window = self.return_windows.get(symbol, [])
                if len(window) >= 2:
                    vol = float(np.std(window, ddof=0))
                else:
                    vol = 0.0
                inv_vols[symbol] = 1.0 / vol if vol > 0 else 0.0
            total = sum(inv_vols.values())
            if total > 0:
                self.symbol_weights = {s: inv_vols[s] / total for s in self.symbols}
            else:
                self.symbol_weights = {s: 1.0 / len(self.symbols) for s in self.symbols}
        else:
            n = len(self.symbols)
            self.symbol_weights = {s: 1.0 / n for s in self.symbols}

    def _new_trading_day(self, trading_day: datetime.date) -> None:
        self.daily_loss_limit_active = False
        self.current_trading_day = trading_day
        self.prev_day_close_equity = self.current_equity

    def on_bar(
        self,
        dt: datetime,
        prices: dict[str, float],
        per_symbol_equity: dict[str, float] | None = None,
        portfolio_equity: float | None = None,
    ) -> None:
        """Advance the coordinator by one bar.

        :param dt: current bar timestamp.
        :param prices: symbol -> current price (close) for symbols that have a bar.
        :param per_symbol_equity: symbol -> standalone BacktestEngine equity for
            the bar.  Used only when ``portfolio_equity`` is not supplied.
        :param portfolio_equity: optional coordinated portfolio equity computed by
            the caller.  When supplied it overrides the per-symbol estimate so
            daily-loss decisions are based on the coordinated replay ledger.
        """
        trading_day = self._trading_day(dt)
        if trading_day != self.current_trading_day:
            self._new_trading_day(trading_day)

        self._update_volatility(dt, prices)

        if portfolio_equity is not None:
            self.current_equity = float(portfolio_equity)
        elif per_symbol_equity:
            # Portfolio equity: weighted average of normalized per-symbol equities.
            weighted = 0.0
            weight_sum = 0.0
            for symbol in self.symbols:
                eq = per_symbol_equity.get(symbol)
                if eq is None:
                    continue
                norm = eq / self.initial_capital
                w = self.symbol_weights.get(symbol, 0.0)
                weighted += norm * w
                weight_sum += w
            if weight_sum > 0:
                self.current_equity = self.initial_capital * (weighted / weight_sum)
            else:
                self.current_equity = self.prev_day_close_equity

        # Daily loss limit trigger check.
        if self.prev_day_close_equity > 0 and not self.daily_loss_limit_active:
            day_pnl_pct = (self.current_equity - self.prev_day_close_equity) / self.prev_day_close_equity
            if day_pnl_pct <= -self.daily_loss_limit_pct:
                self.daily_loss_limit_active = True
                self.loss_limit_triggers.append({
                    "dt": dt.isoformat(sep=" "),
                    "trading_day": str(trading_day),
                    "equity": self.current_equity,
                    "day_pnl_pct": day_pnl_pct,
                })
                self._flatten_all(dt, prices)

    def allow_open(self, symbol: str, strategy: str, dt: datetime, price: float) -> bool:
        """Return True if a new position may be opened under portfolio rules."""
        if self.daily_loss_limit_active:
            return False

        weight = self._position_weight(symbol, strategy)
        for cluster in self._clusters_for_symbol(symbol):
            new_exposure = self.cluster_exposure.get(cluster, 0.0) + abs(weight)
            if new_exposure > self.cluster_gross_cap + 1e-12:
                self.blocked_opens.append({
                    "dt": dt.isoformat(sep=" "),
                    "symbol": symbol,
                    "strategy": strategy,
                    "cluster": cluster,
                    "weight": weight,
                    "cluster_exposure_before": self.cluster_exposure.get(cluster, 0.0),
                    "reason": "cluster_gross_cap",
                })
                return False
        return True

    def record_open(self, symbol: str, strategy: str, dt: datetime, price: float) -> None:
        """Record an allowed open and update cluster exposure."""
        weight = self._position_weight(symbol, strategy)
        self.open_positions[(symbol, strategy)] = {
            "open_dt": dt,
            "open_price": price,
            "weight": weight,
        }
        for cluster in self._clusters_for_symbol(symbol):
            self.cluster_exposure[cluster] = self.cluster_exposure.get(cluster, 0.0) + abs(weight)

    def record_close(self, symbol: str, strategy: str, dt: datetime, price: float) -> None:
        """Record a close; no-op if the position was blocked or flattened earlier."""
        pos = self.open_positions.pop((symbol, strategy), None)
        if pos is None:
            return
        for cluster in self._clusters_for_symbol(symbol):
            self.cluster_exposure[cluster] = max(
                0.0, self.cluster_exposure.get(cluster, 0.0) - abs(pos["weight"])
            )

    def _flatten_all(self, dt: datetime, prices: dict[str, float]) -> None:
        """Flatten every open position when the daily loss limit is hit."""
        if not self.open_positions:
            return
        keys = list(self.open_positions.keys())
        for symbol, strategy in keys:
            pos = self.open_positions.pop((symbol, strategy))
            price = prices.get(symbol, pos["open_price"])
            self.flat_events.append({
                "dt": dt.isoformat(sep=" "),
                "symbol": symbol,
                "strategy": strategy,
                "open_dt": pos["open_dt"].isoformat(sep=" "),
                "open_price": pos["open_price"],
                "flat_price": price,
                "weight": pos["weight"],
            })
            for cluster in self._clusters_for_symbol(symbol):
                self.cluster_exposure[cluster] = max(
                    0.0, self.cluster_exposure.get(cluster, 0.0) - abs(pos["weight"])
                )


class PortfolioEngine:
    """Run a coordinated multi-symbol backtest.

    When ``portfolio_risk`` is ``"off"`` the engine simply aggregates independent
    per-symbol :class:`BacktestEngine` results, reproducing current behavior
    byte-for-byte.  When ``"on"`` it replays the per-symbol trade sequences under
    the portfolio coordinator and produces a coordinated portfolio report.
    """

    def __init__(
        self,
        symbols: list[str],
        freq: str = "1",
        start_date: str | None = None,
        end_date: str | None = None,
        initial_capital: float | None = None,
        commission_rate: float | None = None,
        slippage: float | None = None,
        db_path: str | None = None,
        table_names: dict[str, str] | None = None,
        enable_short: bool | None = None,
    ):
        self.symbols = list(dict.fromkeys(symbols))
        self.freq = freq
        self.start_date = start_date or BACKTEST_CONFIG["start_date"]
        self.end_date = end_date or BACKTEST_CONFIG["end_date"]
        self.initial_capital = initial_capital if initial_capital is not None else BACKTEST_CONFIG["initial_capital"]
        self.commission_rate = commission_rate if commission_rate is not None else BACKTEST_CONFIG["commission_rate"]
        self.slippage = slippage if slippage is not None else BACKTEST_CONFIG["slippage"]
        self.db_path = db_path
        self.table_names = table_names or {}
        self.enable_short = enable_short

    def _make_symbol_engine(self, symbol: str) -> BacktestEngine:
        """Construct the per-symbol BacktestEngine (shared by all replay modes)."""
        return BacktestEngine(
            symbol=symbol,
            freq=self.freq,
            start_date=self.start_date,
            end_date=self.end_date,
            initial_capital=self.initial_capital,
            commission_rate=self.commission_rate,
            slippage=self.slippage,
            db_path=self.db_path,
            table_name=self.table_names.get(symbol),
            enable_short=self.enable_short,
        )

    def _run_per_symbol(self) -> dict[str, dict[str, Any]]:
        """Run an independent BacktestEngine for every symbol."""
        results: dict[str, dict[str, Any]] = {}
        for symbol in self.symbols:
            engine = self._make_symbol_engine(symbol)
            report = engine.run()
            if "error" in report:
                results[symbol] = {"engine": engine, "report": report, "error": report["error"]}
            else:
                results[symbol] = {"engine": engine, "report": report}
        return results

    @staticmethod
    def _portfolio_curve(curves: list[pd.Series]) -> pd.Series:
        """Equal-weight average of normalized symbol equity curves."""
        if not curves:
            return pd.Series(dtype=float)
        df = pd.concat(curves, axis=1).sort_index().ffill().dropna(how="any")
        if df.empty:
            return pd.Series(dtype=float)
        return df.mean(axis=1)

    def _build_off_report(self, symbol_results: dict[str, dict[str, Any]]) -> dict[str, Any]:
        """Aggregate independent per-symbol runs without any coordination."""
        curves: list[pd.Series] = []
        all_pairs: list[dict[str, Any]] = []
        symbol_reports: dict[str, dict[str, Any]] = {}
        errors: dict[str, str] = {}

        for symbol, sr in symbol_results.items():
            engine = sr["engine"]
            report = sr["report"]
            symbol_reports[symbol] = report
            if "error" in report:
                errors[symbol] = report["error"]
                continue

            eq = pd.Series(
                [e["equity"] / engine.initial_capital for e in engine.equity_curve],
                index=[e["dt"] for e in engine.equity_curve],
                name=symbol,
            )
            curves.append(eq)

            for pair in engine.strategy.get_combined_trades():
                pair_copy = pair.copy()
                pair_copy["symbol"] = symbol
                all_pairs.append(pair_copy)

        if not curves:
            return {
                "portfolio_risk": "off",
                "error": "no symbol produced valid equity curve",
                "symbol_errors": errors,
                "symbol_reports": symbol_reports,
            }

        all_pairs.sort(key=lambda x: x["open_dt"])
        portfolio_curve = self._portfolio_curve(curves)
        equity_curve = [
            {"dt": dt, "equity": value * self.initial_capital}
            for dt, value in portfolio_curve.items()
        ]

        sizing_caveat = None
        for sr in symbol_results.values():
            report = sr.get("report", {})
            if "error" not in report and report.get("sizing_caveat"):
                sizing_caveat = report["sizing_caveat"]
                break

        return {
            "portfolio_risk": "off",
            "weighting": STRATEGY_CONFIG.get("weighting", "fixed"),
            "initial_capital": self.initial_capital,
            "period": f"{self.start_date} ~ {self.end_date}",
            "symbols": list(symbol_results.keys()),
            "symbol_reports": symbol_reports,
            "symbol_errors": errors,
            "equity_curve": equity_curve,
            "pairs": all_pairs,
            "sizing_caveat": sizing_caveat,
        }

    def _build_on_report(self, symbol_results: dict[str, dict[str, Any]]) -> dict[str, Any]:
        """Replay per-symbol trades under the portfolio coordinator."""
        successful_symbols = [s for s in self.symbols if "error" not in symbol_results[s].get("report", {})]
        if not successful_symbols:
            return {
                "portfolio_risk": "on",
                "error": "no symbol produced valid equity curve",
                "symbol_errors": {s: sr["report"].get("error", "unknown") for s, sr in symbol_results.items()},
                "symbol_reports": {s: sr["report"] for s, sr in symbol_results.items()},
            }

        coordinator = PortfolioCoordinator(successful_symbols, self.initial_capital, STRATEGY_CONFIG)

        # Price / standalone-equity lookups per symbol.
        price_by_symbol: dict[str, dict[datetime, float]] = {s: {} for s in successful_symbols}
        equity_by_symbol: dict[str, dict[datetime, float]] = {s: {} for s in successful_symbols}
        for symbol in successful_symbols:
            for e in symbol_results[symbol]["engine"].equity_curve:
                price_by_symbol[symbol][e["dt"]] = e["price"]
                equity_by_symbol[symbol][e["dt"]] = e["equity"]

        # Build chronological open/close event lists.
        open_events: list[tuple[datetime, str, str, dict[str, Any]]] = []
        close_events: list[tuple[datetime, str, str, dict[str, Any]]] = []
        for symbol in successful_symbols:
            engine = symbol_results[symbol]["engine"]
            for pair in engine.strategy.get_combined_trades():
                open_events.append((pair["open_dt"], symbol, pair["strategy"], pair))
                close_events.append((pair["close_dt"], symbol, pair["strategy"], pair))
        open_events.sort(key=lambda x: (x[0], x[1], x[2]))
        close_events.sort(key=lambda x: (x[0], x[1], x[2]))

        all_dts = sorted({dt for s in successful_symbols for dt in price_by_symbol[s]})
        open_idx = 0
        close_idx = 0
        flat_events_seen = 0

        open_positions: dict[tuple[str, str], dict[str, Any]] = {}
        coordinated_pairs: list[dict[str, Any]] = []
        coordinated_equity_curve: list[dict[str, Any]] = []

        for dt in all_dts:
            prices = {s: price_by_symbol[s].get(dt) for s in successful_symbols}
            per_symbol_equity = {s: equity_by_symbol[s].get(dt) for s in successful_symbols}

            # Process opens at this dt.
            while open_idx < len(open_events) and open_events[open_idx][0] == dt:
                _, symbol, strategy, pair = open_events[open_idx]
                open_idx += 1
                if coordinator.allow_open(symbol, strategy, dt, pair["open_price"]):
                    signed_weight = coordinator._position_weight(symbol, strategy)
                    coordinator.record_open(symbol, strategy, dt, pair["open_price"])
                    open_positions[(symbol, strategy)] = {
                        "symbol": symbol,
                        "open_dt": dt,
                        "open_price": pair["open_price"],
                        "weight": signed_weight,
                        "sign": _position_sign(strategy),
                    }

            # Process closes at this dt.
            while close_idx < len(close_events) and close_events[close_idx][0] == dt:
                _, symbol, strategy, pair = close_events[close_idx]
                close_idx += 1
                pos = open_positions.pop((symbol, strategy), None)
                if pos is None:
                    continue
                coordinated_pairs.append({
                    "symbol": symbol,
                    "strategy": strategy,
                    "open_dt": pos["open_dt"],
                    "close_dt": dt,
                    "open_price": pos["open_price"],
                    "close_price": pair["close_price"],
                    "pnl_pct": pair["pnl_pct"],
                    "weight": pos["weight"],
                    "bars_held": pair.get("bars_held"),
                    "reason": pair.get("reason"),
                    "reason_code": pair.get("reason_code"),
                })
                coordinator.record_close(symbol, strategy, dt, pair["close_price"])

            # Recompute portfolio equity from filtered trades.
            realized = sum(
                p["pnl_pct"] * abs(p["weight"]) * self.initial_capital for p in coordinated_pairs
            )
            unrealized = 0.0
            for pos in open_positions.values():
                price = prices.get(pos["symbol"])
                if price is None or pos["open_price"] <= 0:
                    continue
                market_return = (price - pos["open_price"]) / pos["open_price"]
                upnl_pct = pos["sign"] * market_return
                unrealized += upnl_pct * abs(pos["weight"]) * self.initial_capital
            portfolio_equity = self.initial_capital + realized + unrealized

            # Update coordinator state using the coordinated portfolio equity so the
            # daily-loss-limit decision is based on the replay ledger, not the
            # standalone per-symbol equity curves.
            coordinator.on_bar(dt, prices, per_symbol_equity, portfolio_equity)

            # Apply coordinator flat events so the reported portfolio state reflects
            # the daily-loss-limit close.
            flattened_this_bar = False
            while flat_events_seen < len(coordinator.flat_events):
                ev = coordinator.flat_events[flat_events_seen]
                flat_events_seen += 1
                symbol = ev["symbol"]
                strategy = ev["strategy"]
                pos = open_positions.pop((symbol, strategy), None)
                if pos is None:
                    continue
                flat_price = ev["flat_price"]
                sign = pos["sign"]
                gross_pnl = sign * (flat_price - pos["open_price"]) / pos["open_price"]
                # Deduct round-trip costs so flatten pairs are net-of-cost, matching
                # every other coordinated_pairs entry sourced from Position.
                net_pnl = gross_pnl - (2 * self.commission_rate + self.slippage)
                coordinated_pairs.append({
                    "symbol": symbol,
                    "strategy": strategy,
                    "open_dt": pos["open_dt"],
                    "close_dt": dt,
                    "open_price": pos["open_price"],
                    "close_price": flat_price,
                    "pnl_pct": net_pnl,
                    "weight": pos["weight"],
                    "bars_held": None,
                    "reason": "portfolio_daily_loss_limit",
                    "reason_code": "portfolio_daily_loss_limit",
                })
                flattened_this_bar = True

            if flattened_this_bar:
                # Recompute equity with no unrealized PnL since all positions are flat.
                realized = sum(
                    p["pnl_pct"] * abs(p["weight"]) * self.initial_capital for p in coordinated_pairs
                )
                portfolio_equity = self.initial_capital + realized

            coordinated_equity_curve.append({
                "dt": dt,
                "equity": portfolio_equity,
                "gross_exposure": sum(abs(p["weight"]) for p in open_positions.values()),
                "net_exposure": sum(pos["sign"] * abs(pos["weight"]) for pos in open_positions.values()),
                "cluster_exposure": dict(coordinator.cluster_exposure),
                "loss_limit_active": coordinator.daily_loss_limit_active,
                "symbol_weights": dict(coordinator.symbol_weights),
            })

        sizing_caveat = None
        for s in successful_symbols:
            report = symbol_results[s]["report"]
            if report.get("sizing_caveat"):
                sizing_caveat = report["sizing_caveat"]
                break

        return {
            "portfolio_risk": "on",
            "weighting": STRATEGY_CONFIG.get("weighting", "fixed"),
            "initial_capital": self.initial_capital,
            "period": f"{self.start_date} ~ {self.end_date}",
            "symbols": successful_symbols,
            "symbol_reports": {s: symbol_results[s]["report"] for s in successful_symbols},
            "symbol_errors": {s: sr["report"].get("error", "unknown") for s, sr in symbol_results.items() if "error" in sr.get("report", {})},
            "equity_curve": coordinated_equity_curve,
            "pairs": coordinated_pairs,
            "blocked_opens": coordinator.blocked_opens,
            "loss_limit_triggers": coordinator.loss_limit_triggers,
            "flat_events": coordinator.flat_events,
            "sizing_caveat": sizing_caveat,
        }

    def _build_joint_report(self) -> dict[str, Any]:
        """Run the A87 joint-clock replay (``sizing_model='risk' + portfolio_risk='on'``).

        Steps every symbol's :meth:`BacktestEngine.bar_generator` through a
        single merged clock (union of bar timestamps, sorted; per-tick ties
        broken by ``sorted(symbol)``).  A shared :class:`PortfolioLedger`
        tracks currency-based equity and margin across symbols; each
        ``"pre_open"`` yield receives either the true shared
        ``(equity, total_open_margin)`` — which makes the existing
        ``max_margin_pct`` act as a total-portfolio cap — or a deliberately
        saturated value that forces ``Position._size_open()`` to reject the
        open when the daily loss limit, the per-symbol cap or a cluster cap
        is breached.  Scope is block-new-opens only: no position is ever
        force-closed here (forced liquidation is deferred to A89).
        """
        engines: dict[str, BacktestEngine] = {}
        generators: dict[str, Any] = {}
        pending: dict[str, Any] = {}
        symbol_reports: dict[str, dict[str, Any]] = {}
        symbol_errors: dict[str, str] = {}

        # 1-2. Build one engine per symbol (same construction as
        # _run_per_symbol), start its bar generator with run()'s default
        # warmup, and prime it to its first "pre_open" yield.
        for symbol in self.symbols:
            engine = self._make_symbol_engine(symbol)
            gen = engine.bar_generator()  # default warmup_bars=100, same as run()
            if isinstance(gen, dict):
                # Data-load error path, recorded exactly as _run_per_symbol does.
                symbol_reports[symbol] = gen
                symbol_errors[symbol] = gen.get("error", "unknown")
                continue
            engines[symbol] = engine
            generators[symbol] = gen
            try:
                pending[symbol] = next(gen)
            except StopIteration as stop:  # defensive; length checks make this unlikely
                pending[symbol] = None
                symbol_errors[symbol] = "empty_bar_generator"
                symbol_reports[symbol] = (
                    stop.value if isinstance(stop.value, dict) else {"error": "empty_bar_generator"}
                )

        successful_symbols = [s for s in self.symbols if s in generators]
        if not successful_symbols:
            return {
                "portfolio_risk": "on",
                "sizing_model": "risk",
                "error": "no symbol produced valid equity curve",
                "symbol_errors": symbol_errors,
                "symbol_reports": symbol_reports,
            }

        # 3. One shared ledger across all successfully-started symbols.
        ledger = PortfolioLedger(
            successful_symbols,
            self.initial_capital,
            dict(STRATEGY_CONFIG.get("corr_clusters") or {}),
        )

        # 4. Joint clock loop.
        pnl_contributions: dict[str, float] = {s: 0.0 for s in successful_symbols}
        ended: dict[str, Any] = {}  # symbol -> its final bar dt (margin zeroed after it)
        blocked_opens: list[dict[str, Any]] = []
        joint_equity_curve: list[dict[str, Any]] = []

        while any(item is not None for item in pending.values()):
            current_dt = min(item[1] for item in pending.values() if item is not None)
            ledger.update_trading_day(current_dt)
            # A83 range semantics: a symbol whose bar range ended before this
            # tick contributes zero margin (its last margin is not carried
            # forward); its PnL contribution stays frozen at the last value.
            for symbol, end_dt in ended.items():
                if end_dt < current_dt and ledger.margin_by_symbol.get(symbol, 0.0) != 0.0:
                    ledger.update_symbol_margin(symbol, 0.0)

            tick_symbols = sorted(
                s for s in successful_symbols
                if pending.get(s) is not None and pending[s][1] == current_dt
            )
            for symbol in tick_symbols:
                item = pending[symbol]
                assert item[0] == "pre_open", (
                    f"joint driver invariant violated: expected 'pre_open' for "
                    f"{symbol} at {current_dt}, got {item[0]!r}"
                )
                equity, margin, reason = ledger.pre_open_injection_for(symbol)
                if reason is not None:
                    # Speculative record of gating pressure: an open attempted
                    # at this tick would have been forced to fail (mirrors how
                    # PortfolioCoordinator.blocked_opens already works).
                    blocked_opens.append({
                        "dt": current_dt.isoformat(sep=" "),
                        "symbol": symbol,
                        "reason": reason,
                    })
                gen = generators[symbol]
                post_item = gen.send((equity, margin))
                assert post_item[0] == "post_bar" and post_item[1] == current_dt, (
                    f"joint driver invariant violated: expected 'post_bar' for "
                    f"{symbol} at {current_dt}, got {post_item!r}"
                )
                ledger.update_symbol_margin(symbol, float(post_item[4]))
                pnl_contributions[symbol] = float(post_item[3]) - engines[symbol].initial_capital
                ledger.update_equity(pnl_contributions)
                try:
                    # Feed the shared portfolio view back so the engine's own
                    # recorded equity_curve entry reflects the joint replay.
                    pending[symbol] = gen.send((ledger.equity, ledger.margin_total))
                except StopIteration as stop:
                    symbol_reports[symbol] = stop.value
                    pending[symbol] = None
                    ended[symbol] = current_dt
                ledger.check_daily_loss_limit()

            # One entry per unique tick: ledger state has converged by the end
            # of the tick's symbol loop, so this is well-defined.
            joint_equity_curve.append({
                "dt": current_dt,
                "equity": ledger.equity,
                "total_open_margin": ledger.margin_total,
                "margin_utilization_pct": (
                    ledger.margin_total / ledger.equity if ledger.equity > 0 else 0.0
                ),
            })

        # 5. Assemble the joint report.
        all_pairs: list[dict[str, Any]] = []
        for symbol in successful_symbols:
            for pair in engines[symbol].strategy.get_combined_trades():
                pair_copy = pair.copy()
                pair_copy["symbol"] = symbol
                all_pairs.append(pair_copy)
        all_pairs.sort(key=lambda x: x["open_dt"])

        sizing_caveat = None
        for s in successful_symbols:
            report = symbol_reports.get(s) or {}
            if report.get("sizing_caveat"):
                sizing_caveat = report["sizing_caveat"]
                break

        return {
            "portfolio_risk": "on",
            "sizing_model": "risk",
            "weighting": STRATEGY_CONFIG.get("weighting", "fixed"),
            "initial_capital": self.initial_capital,
            "period": f"{self.start_date} ~ {self.end_date}",
            "symbols": successful_symbols,
            "symbol_reports": symbol_reports,
            "symbol_errors": symbol_errors,
            "equity_curve": joint_equity_curve,
            "pairs": all_pairs,
            "blocked_opens": blocked_opens,
            "loss_limit_triggers": ledger.loss_limit_triggers,
            # A87 scope is block-new-opens only; no forced liquidation happens
            # in this path (deferred to A89), so there is deliberately no
            # "flat_events" field.
            "flatten_on_breach": "not_implemented_see_A89",
            "sizing_caveat": sizing_caveat,
        }

    def run(self) -> dict[str, Any]:
        """Run the portfolio backtest and return the report."""
        sizing_model = STRATEGY_CONFIG.get("sizing_model", "research")
        portfolio_risk = STRATEGY_CONFIG.get("portfolio_risk", "off")
        if sizing_model == "risk" and portfolio_risk == "on":
            return self._build_joint_report()
        symbol_results = self._run_per_symbol()
        if portfolio_risk == "off":
            return self._build_off_report(symbol_results)
        return self._build_on_report(symbol_results)


def run_portfolio_backtest(
    symbols: list[str],
    freq: str = "1",
    start_date: str | None = None,
    end_date: str | None = None,
    initial_capital: float | None = None,
    commission_rate: float | None = None,
    slippage: float | None = None,
    db_path: str | None = None,
    enable_short: bool | None = None,
    table_names: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Convenience entry point matching ``run_batch_backtest`` style."""
    engine = PortfolioEngine(
        symbols=symbols,
        freq=freq,
        start_date=start_date,
        end_date=end_date,
        initial_capital=initial_capital,
        commission_rate=commission_rate,
        slippage=slippage,
        db_path=db_path,
        enable_short=enable_short,
        table_names=table_names,
    )
    return engine.run()
