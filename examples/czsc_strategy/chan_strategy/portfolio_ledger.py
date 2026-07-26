"""A87 — Shared portfolio ledger for the joint-clock multi-symbol replay.

:class:`PortfolioLedger` tracks the shared, currency-based portfolio state
(equity, per-symbol / per-cluster margin occupancy, trading-day bookkeeping)
while the joint driver in :meth:`PortfolioEngine._build_joint_report` steps
every symbol's :meth:`BacktestEngine.bar_generator` through a single merged
clock.  It is the online, in-replay counterpart of A83's post-hoc ledger
report (``diagnostics/portfolio_ledger_report.py``).

**Dual meaning of the shared config keys (intentional, not an oversight).**
``max_margin_pct``, ``cluster_gross_cap`` and ``daily_loss_limit_pct`` are
also consumed by the *weight-based* :class:`PortfolioCoordinator`
(``portfolio_engine.py``) when ``portfolio_risk="on"`` and
``sizing_model!="risk"``.  :class:`PortfolioLedger` reinterprets the same key
names in *margin/currency* terms for the ``sizing_model="risk"`` +
``portfolio_risk="on"`` joint-replay path.  The two paths are strictly
mutually exclusive (gated by ``sizing_model`` in ``PortfolioEngine.run()``),
so at any given config snapshot only one interpretation is ever active.

**Gating mechanism (the only one; do not invent another).**
``Position._size_open()`` already caps opens via
``pre_open_margin + volume * required_margin_for_one > equity * max_margin_pct``.
Feeding the *true* shared ``equity`` / ``total_open_margin`` at the
``"pre_open"`` yield therefore makes ``max_margin_pct`` act as a
total-portfolio margin cap with no new code.  To block opens for one of the
additional reasons the ledger tracks (daily-loss-limit active, per-symbol
cap, cluster cap), :meth:`pre_open_injection_for` returns a *deliberately
saturated* ``total_open_margin`` (``= equity * max_margin_pct``) so the
existing formula rejects the open (``max_fit <= 0``) without knowing why;
the "why" is recorded separately by the driver in its ``blocked_opens``
diagnostic list.

Scope: **block-new-opens only, on the ledger side**.  This class itself never
closes positions; the A90 forced liquidation on a daily-loss breach lives in
the joint driver (``PortfolioEngine._build_joint_report``), which acts on the
``daily_loss_limit_active`` False→True transition this class reports (see
``docs/design/a89-forced-liquidation-design.md``).

RESEARCH-ONLY, not a trading recommendation.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from chan_strategy.config import STRATEGY_CONFIG


class PortfolioLedger:
    """Shared portfolio state for the joint-clock replay (A87).

    Each per-symbol engine is constructed with the *same* ``initial_capital``
    as the portfolio (matching A83/A84's verified methodology — capital is
    NOT divided per symbol).  Every symbol's PnL contribution is therefore
    ``computed_equity_from_yield - initial_capital`` and the shared equity is
    ``initial_capital + sum(contributions)`` — ``initial_capital`` is counted
    exactly once.

    A symbol that has not started yet contributes zero margin; a symbol whose
    bar range has ended contributes zero margin again from the first tick
    after its final bar (A83's "not carried past symbol end" semantics),
    while its PnL contribution stays frozen at its last known value.

    See the module docstring for the dual meaning of the shared config keys
    and for the saturated-margin gating mechanism.
    """

    def __init__(
        self,
        symbols: list[str],
        initial_capital: float,
        corr_clusters: dict[str, list[str]] | None = None,
        config: dict[str, Any] | None = None,
    ):
        self.symbols = list(dict.fromkeys(symbols))  # preserve order, dedupe
        self.initial_capital = float(initial_capital)
        self.cfg = dict(STRATEGY_CONFIG)
        if config is not None:
            self.cfg.update(config)

        self.max_margin_pct = float(self.cfg["max_margin_pct"])
        self.max_symbol_margin_pct = float(self.cfg["max_symbol_margin_pct"])
        self.cluster_gross_cap = float(self.cfg["cluster_gross_cap"])
        self.daily_loss_limit_pct = float(self.cfg["daily_loss_limit_pct"])
        # None (default) disables the breaker entirely — opt-in, research-only.
        # Unlike daily_loss_limit_pct this measures drawdown from the running
        # equity peak and does NOT reset on a trading-day rollover (see A87+
        # docstring above and config.py for the "chronic bleed" rationale).
        raw_breaker_pct = self.cfg.get("max_drawdown_breaker_pct")
        self.max_drawdown_breaker_pct = (
            float(raw_breaker_pct) if raw_breaker_pct is not None else None
        )
        self.daily_agg = self.cfg["daily_agg"]
        self.night_session_start_hour = int(self.cfg["night_session_start_hour"])

        self.corr_clusters = dict(corr_clusters or {})
        # Local import: diagnostics.portfolio_ledger_report imports
        # chan_strategy.portfolio_engine, which itself imports this module —
        # a top-level import here would be circular.
        from diagnostics.portfolio_ledger_report import _symbol_clusters
        self._cluster_map: dict[str, list[str]] = _symbol_clusters(self.corr_clusters, self.symbols)

        # Shared online state (updated once per symbol-tick by the driver).
        self.equity: float = self.initial_capital
        self.margin_by_symbol: dict[str, float] = {s: 0.0 for s in self.symbols}
        self.margin_total: float = 0.0
        self.margin_by_cluster: dict[str, float] = {name: 0.0 for name in self.corr_clusters}

        # Day-rollover bookkeeping for the daily loss limit.
        self.trading_day: date | None = None
        self.day_start_equity: float = self.initial_capital
        self.daily_loss_limit_active: bool = False
        self.loss_limit_triggers: list[dict[str, Any]] = []
        self._last_dt: datetime | None = None

        # Persistent (non-daily-reset) drawdown breaker state — see
        # max_drawdown_breaker_pct above.  peak_equity only ever increases;
        # once drawdown_breaker_active flips True it stays True for the rest
        # of the replay (a circuit breaker, not a daily-reset limit).
        self.peak_equity: float = self.initial_capital
        self.drawdown_breaker_active: bool = False
        self.drawdown_breaker_triggers: list[dict[str, Any]] = []

    # ------------------------------------------------------------------ helpers
    def _trading_day(self, dt: datetime) -> date:
        # Local import avoids the portfolio_engine <-> portfolio_ledger cycle.
        from chan_strategy.portfolio_engine import _trading_day
        return _trading_day(dt, self.daily_agg, self.night_session_start_hour)

    # ------------------------------------------------------------------ updates
    def update_trading_day(self, dt: datetime) -> None:
        """Advance the trading-day clock; call once per joint tick (before any symbol).

        On a trading-day change the daily loss limit resets and the new
        ``day_start_equity`` is the equity as of the previous tick's close.
        """
        self._last_dt = dt
        trading_day = self._trading_day(dt)
        if trading_day != self.trading_day:
            self.trading_day = trading_day
            self.day_start_equity = self.equity
            self.daily_loss_limit_active = False

    def update_equity(self, pnl_contributions: dict[str, float]) -> None:
        """Recompute shared equity from every symbol's latest PnL contribution."""
        self.equity = self.initial_capital + sum(pnl_contributions.values())
        if self.equity > self.peak_equity:
            self.peak_equity = self.equity

    def update_symbol_margin(self, symbol: str, margin: float) -> None:
        """Record one symbol's margin and recompute total / per-cluster sums."""
        self.margin_by_symbol[symbol] = float(margin)
        self.margin_total = sum(self.margin_by_symbol.values())
        self.margin_by_cluster = {
            name: sum(
                self.margin_by_symbol[s]
                for s in self.symbols
                if name in self._cluster_map.get(s, [])
            )
            for name in self.corr_clusters
        }

    def check_daily_loss_limit(self) -> None:
        """Arm the daily loss limit once the day PnL breaches the configured limit.

        Call after :meth:`update_equity`.  Records the trigger in
        ``loss_limit_triggers``.  **Does not flatten anything itself** — the
        A90 forced liquidation is performed by the joint driver on the
        False→True transition of ``daily_loss_limit_active`` (see module
        docstring).
        """
        if self.daily_loss_limit_active or self.day_start_equity <= 0:
            return
        day_pnl_pct = (self.equity - self.day_start_equity) / self.day_start_equity
        if day_pnl_pct <= -self.daily_loss_limit_pct:
            self.daily_loss_limit_active = True
            self.loss_limit_triggers.append({
                "dt": self._last_dt.isoformat(sep=" ") if self._last_dt else None,
                "trading_day": str(self.trading_day) if self.trading_day else None,
                "equity": self.equity,
                "day_pnl_pct": day_pnl_pct,
            })

    def check_drawdown_breaker(self) -> None:
        """Arm the persistent drawdown breaker once equity draws down from its
        running peak by ``max_drawdown_breaker_pct`` or more.

        No-op when ``max_drawdown_breaker_pct`` is ``None`` (disabled, the
        default).  Call after :meth:`update_equity`.  Unlike
        :meth:`check_daily_loss_limit`, once armed this **never auto-resets**
        (no trading-day rollover clears it) — it is a circuit breaker for
        chronic multi-day bleed, not a daily limit.  Does not flatten
        anything itself; the driver (``PortfolioEngine._build_joint_report``)
        performs forced liquidation on the False->True transition, mirroring
        the A90 daily-loss-limit wiring.
        """
        if self.max_drawdown_breaker_pct is None:
            return
        if self.drawdown_breaker_active or self.peak_equity <= 0:
            return
        drawdown_pct = (self.equity - self.peak_equity) / self.peak_equity
        if drawdown_pct <= -self.max_drawdown_breaker_pct:
            self.drawdown_breaker_active = True
            self.drawdown_breaker_triggers.append({
                "dt": self._last_dt.isoformat(sep=" ") if self._last_dt else None,
                "trading_day": str(self.trading_day) if self.trading_day else None,
                "equity": self.equity,
                "peak_equity": self.peak_equity,
                "drawdown_pct": drawdown_pct,
            })

    # ------------------------------------------------------------------ gating
    def pre_open_injection_for(self, symbol: str) -> tuple[float, float, str | None]:
        """Return ``(equity, total_open_margin, blocked_reason)`` for one ``"pre_open"`` yield.

        When nothing is breached this returns the true shared
        ``(self.equity, self.margin_total)`` and ``None``.  When the
        persistent drawdown breaker or the daily loss limit is active, or the
        symbol's own margin share exceeds ``equity * max_symbol_margin_pct``,
        or any cluster containing the symbol exceeds
        ``equity * cluster_gross_cap``, it returns the saturated
        ``(self.equity, self.equity * max_margin_pct, reason)`` so the
        existing ``Position._size_open()`` formula rejects the open.
        Reasons are checked drawdown-breaker first (most severe/persistent),
        then daily-loss, then per-symbol, then cluster (first true wins) so
        the reason string is deterministic when several constraints are
        breached simultaneously.
        """
        reason: str | None = None
        if self.drawdown_breaker_active:
            reason = "drawdown_breaker"
        elif self.daily_loss_limit_active:
            reason = "daily_loss_limit"
        elif self.margin_by_symbol.get(symbol, 0.0) > self.equity * self.max_symbol_margin_pct:
            reason = "symbol_margin_cap"
        else:
            for cluster in sorted(self._cluster_map.get(symbol, [])):
                if self.margin_by_cluster.get(cluster, 0.0) > self.equity * self.cluster_gross_cap:
                    reason = f"cluster_gross_cap:{cluster}"
                    break
        if reason is not None:
            return self.equity, self.equity * self.max_margin_pct, reason
        return self.equity, self.margin_total, None
