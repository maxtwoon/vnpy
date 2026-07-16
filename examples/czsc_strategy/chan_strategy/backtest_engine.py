"""
缠论择时策略回测引擎

核心流程：
1. 从SQLite数据库加载K线数据（1分钟期货数据）
2. 使用czsc CZSC对象进行缠论分析
3. 生成标准信号字典
4. 驱动Position子策略执行交易
5. 输出绩效报告

数据库结构:
- 表名格式: {symbol}_1M_raw (如 sc888_1M_raw)
- 列: datetime(TEXT), symbol(TEXT), open/high/low/close/volume/amount(REAL)
- 数据为1分钟K线，需要合成更高周期
"""
import sys
from collections.abc import Generator
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import Any
import pandas as pd
import numpy as np

# 确保可以导入chan_strategy
sys.path.insert(0, str(Path(__file__).parent.parent))

from czsc import CZSC
from czsc.objects import RawBar, Freq

from chan_strategy.config import SQLITE_DB_PATH, STRATEGY_CONFIG, BACKTEST_CONFIG
from chan_strategy.data_adapter import SqliteDataAdapter, resample_bars
from chan_strategy.limit_config import (
    SYMBOL_LIMIT_CONFIG,
    _bar_at_limit,
    _daily_prev_close_map,
    _limit_pct_for_date,
)
from chan_strategy.rollover_config import (
    _detect_transitions,
    _exclusion_dates,
    _pair_in_exclusion_window,
    _trading_dates_from_bars,
)
from chan_strategy.sell_signals import get_all_signals
from chan_strategy.positions import ChanTimingStrategy
from chan_strategy.positions import _research_symbol_key as _position_symbol_key


def _research_symbol_key(symbol: str) -> str:
    return "".join(ch for ch in str(symbol).upper() if ch.isalnum())


@contextmanager
def formal_evaluation_config():
    """Temporarily override STRATEGY_CONFIG for a formal-evaluation run.

    Formal evaluation uses real contract-multiplier/margin-constrained sizing
    (``sizing_model="risk"``), rejects fills at unexecutable limit/halt
    bands (``limit_halt_model="enforce"``), blocks new opens inside rollover
    windows (``rollover_open_gating="on"``), checks stop-loss against bar
    extremes (``stop_execution_model="intrabar"``), and maps night-session
    bars past midnight to the next trading day (``daily_agg="trading_calendar"``).
    The original config values are saved and restored on exit, including when
    the wrapped code raises.

    This intentionally mutates the shared ``STRATEGY_CONFIG`` dict because
    ``BacktestEngine`` reads these knobs directly from the module-level dict
    at multiple points at runtime; there is no per-instance constructor
    parameter to override them.
    """
    keys = (
        "sizing_model",
        "limit_halt_model",
        "rollover_open_gating",
        "stop_execution_model",
        "daily_agg",
    )
    overrides = {
        "sizing_model": "risk",
        "limit_halt_model": "enforce",
        "rollover_open_gating": "on",
        "stop_execution_model": "intrabar",
        "daily_agg": "trading_calendar",
    }
    saved: dict[str, str] = {}
    for key in keys:
        saved[key] = STRATEGY_CONFIG.get(key)
    try:
        STRATEGY_CONFIG.update(overrides)
        yield
    finally:
        for key in keys:
            if saved[key] is None:
                STRATEGY_CONFIG.pop(key, None)
            else:
                STRATEGY_CONFIG[key] = saved[key]


def _apply_symbol_position_overrides(pos_weights: dict[str, float], symbol: str) -> dict[str, float]:
    overrides = STRATEGY_CONFIG.get("symbol_position_overrides") or {}
    item = overrides.get(_research_symbol_key(symbol), None)
    if not isinstance(item, dict):
        return pos_weights
    updated = dict(pos_weights)
    key_map = {
        "pos_1buy": "一买多头",
        "pos_2buy": "二买多头",
        "pos_3buy": "三买多头",
        "pos_1sell": "一卖空头",
        "pos_2sell": "二卖空头",
        "pos_3sell": "三卖空头",
    }
    for config_key, strategy_name in key_map.items():
        if config_key in item:
            updated[strategy_name] = float(item[config_key])
    return updated


def _compute_mode_label(
    sizing_model: str,
    limit_halt_model: str,
    portfolio_risk: str,
    rollover_open_gating: str,
) -> str:
    """Compute the backtest mode label from execution/risk config knobs.

    The pure-default configuration (research sizing + limit/halt off +
    portfolio risk off + rollover open gating off) is labeled
    RESEARCH_BASELINE so readers cannot mistake the output for
    production-tradable results. Any deviation is reported explicitly with
    the dimension name and current value.
    """
    defaults = {
        "sizing": ("sizing_model", "research"),
        "limit_halt": ("limit_halt_model", "off"),
        "portfolio_risk": ("portfolio_risk", "off"),
        "rollover_open_gating": ("rollover_open_gating", "off"),
    }
    actuals = {
        "sizing": sizing_model,
        "limit_halt": limit_halt_model,
        "portfolio_risk": portfolio_risk,
        "rollover_open_gating": rollover_open_gating,
    }
    deviations = [
        (dim, actuals[dim])
        for dim in ("sizing", "limit_halt", "portfolio_risk", "rollover_open_gating")
        if actuals[dim] != defaults[dim][1]
    ]
    if not deviations:
        return "RESEARCH_BASELINE"
    parts = [f"{defaults[dim][0]}={value}" for dim, value in deviations]
    return f"PARTIAL_PRODUCTION_FEATURES({','.join(parts)})"


def assert_not_research_baseline(report: dict) -> None:
    """Raise unless ``report`` carries a known-safe mode label.

    This guard is fail-closed: only ``mode_label`` values matching the
    ``"PARTIAL_PRODUCTION_FEATURES("`` prefix produced by ``_compute_mode_label()``
    are accepted as non-research evidence. Anything else — missing key,
    ``None``, empty string, ``"RESEARCH_BASELINE"``, or any unrecognized
    string — raises ``ValueError``.

    Future promotion/acceptance logic should call this guard before treating
    any backtest report as production-tradable evidence.

    :raises ValueError: if ``mode_label`` is missing or not a known-safe value.
    """
    mode_label = report.get("mode_label")
    if not isinstance(mode_label, str) or not mode_label.startswith(
        "PARTIAL_PRODUCTION_FEATURES("
    ):
        raise ValueError(
            f"Report mode_label {mode_label!r} is missing, empty, or not a "
            "known-safe production feature label and cannot be consumed as "
            "production-tradable or promotion evidence."
        )


def unified_acceptance_gate(
    oos_verdict: dict[str, Any],
    perturbation_verdict: dict[str, Any],
    cost_verdict: dict[str, Any],
    report: dict[str, Any],
) -> dict[str, Any]:
    """Return a single top-level pass/warn/fail judgment for a backtest report.

    Combines the ``overall_status`` values from the three A71 verdict gates
    (OOS, risk-parameter perturbation, cost sensitivity) with the report's
    ``mode_label``. The combination rules are:

    1. ``mode_label`` is not a known-safe production feature label -> ``"fail"``.
    2. Any input ``overall_status == "fail"`` -> ``"fail"``.
    3. Any input ``overall_status == "warn"`` and no ``"fail"`` -> ``"warn"``.
    4. Otherwise -> ``"pass"``.

    The mode-label check reuses ``assert_not_research_baseline()`` so the
    allow-list logic is not duplicated. No verdict thresholds are invented or
    modified here; this is a thin combining layer.

    :param oos_verdict: result of ``oos_gate_verdict()``.
    :param perturbation_verdict: result of ``perturbation_gate_verdict()``.
    :param cost_verdict: result of ``cost_sensitivity_gate_verdict()``.
    :param report: the backtest report whose ``mode_label`` is checked.
    :return: dict with ``overall_status`` (``"pass"|"warn"|"fail"``) and
        ``reasons`` (list of human-readable strings).
    """
    reasons: list[str] = []

    try:
        assert_not_research_baseline(report)
    except ValueError as exc:
        reasons.append(str(exc))
        return {"overall_status": "fail", "reasons": reasons}

    statuses = [
        oos_verdict.get("overall_status", "pass"),
        perturbation_verdict.get("overall_status", "pass"),
        cost_verdict.get("overall_status", "pass"),
    ]

    if any(status == "fail" for status in statuses):
        overall = "fail"
    elif any(status == "warn" for status in statuses):
        overall = "warn"
    else:
        overall = "pass"

    for label, verdict in (
        ("oos", oos_verdict),
        ("perturbation", perturbation_verdict),
        ("cost", cost_verdict),
    ):
        status = verdict.get("overall_status", "pass")
        if status != "pass":
            for reason in verdict.get("reasons", []):
                reasons.append(f"{label}: {reason}")

    return {"overall_status": overall, "reasons": reasons}


class BacktestEngine:
    """缠论择时策略回测引擎"""

    def __init__(
        self,
        symbol: str,
        freq: str = "1",
        start_date: str = None,
        end_date: str = None,
        initial_capital: float = 1000000,
        commission_rate: float | None = None,
        slippage: float | None = None,
        db_path: str = None,
        table_name: str = None,
        enable_short: bool | None = None,
    ):
        """
        初始化回测引擎

        :param symbol: 股票/期货代码 (如 sc888)
        :param freq: K线频率标识 ('1'=1分钟原始数据)
        :param start_date: 回测开始日期 YYYY-MM-DD
        :param end_date: 回测结束日期 YYYY-MM-DD
        :param initial_capital: 初始资金
        :param commission_rate: 手续费率
        :param slippage: 滑点
        :param db_path: 数据库路径，默认使用config中的路径
        :param table_name: 指定数据表名，默认自动推断
        """
        self.symbol = symbol
        self.freq = freq
        self.start_date = start_date or BACKTEST_CONFIG["start_date"]
        self.end_date = end_date or BACKTEST_CONFIG["end_date"]
        self.initial_capital = initial_capital
        self.commission_rate = commission_rate if commission_rate is not None else BACKTEST_CONFIG["commission_rate"]
        self.slippage = slippage if slippage is not None else BACKTEST_CONFIG["slippage"]
        self.db_path = db_path or SQLITE_DB_PATH
        self.table_name = table_name
        self.enable_short = enable_short

        # 初始化运行状态；_reset_state 也会在 run() 开头被调用以保证幂等
        self._reset_state()

    def load_data(self) -> bool:
        """加载数据"""
        adapter = SqliteDataAdapter(self.db_path)
        try:
            # 确定表名
            table = self.table_name
            if not table:
                table = self._find_table(adapter)
            if not table:
                print(f"错误: 找不到品种 {self.symbol} 对应的数据表")
                return False

            print(f"使用数据表: {table}")

            # 加载原始K线数据
            unparseable_count: list[int] = [0]
            self.bars = adapter.load_raw_bars(
                symbol=self.symbol,
                freq=self.freq,
                start_date=self.start_date,
                end_date=self.end_date,
                table_name=table,
                unparseable_count=unparseable_count,
            )
            self.unparseable_rows_skipped = unparseable_count[0]
            print(f"加载数据: {self.symbol}, 频率={self.freq}, "
                  f"范围={self.start_date}~{self.end_date}, "
                  f"共{len(self.bars)}根K线"
                  f"(跳过无法解析行数={self.unparseable_rows_skipped})")
            return len(self.bars) > 0
        except Exception as e:
            print(f"数据加载失败: {e}")
            import traceback
            traceback.print_exc()
            return False
        finally:
            adapter.close()

    def _find_table(self, adapter: SqliteDataAdapter) -> str | None:
        """根据symbol查找对应的数据表"""
        tables = adapter.get_tables()
        if not tables:
            return None

        # 规范化: 统一小写，去除首尾空格
        norm_symbol = self.symbol.lower().strip()

        # 1. 精确匹配: {symbol}_1M_raw / {symbol}_1min_raw 等常见命名 (不区分大小写)
        exact_patterns = [
            f"{norm_symbol}_1m_raw",
            f"{norm_symbol}_1min_raw",
            f"{norm_symbol}_5m_raw",
            f"{norm_symbol}_5min_raw",
            f"{norm_symbol}_raw",
            norm_symbol,
        ]
        exact_candidates = []
        for table in tables:
            if table.lower().strip() in exact_patterns:
                exact_candidates.append(table)

        # 2. 如果无精确匹配，尝试匹配 "{symbol}_" 前缀（唯一前缀匹配）
        prefix_candidates = []
        if not exact_candidates:
            for table in tables:
                if table.lower().strip().startswith(norm_symbol + "_"):
                    prefix_candidates.append(table)

        # 3. 决策
        if exact_candidates:
            if len(exact_candidates) == 1:
                return exact_candidates[0]
            raise ValueError(
                f"品种 '{self.symbol}' 在数据库中找到多个精确匹配表: {exact_candidates}"
            )

        if prefix_candidates:
            if len(prefix_candidates) == 1:
                return prefix_candidates[0]
            raise ValueError(
                f"品种 '{self.symbol}' 在数据库中找到多个前缀匹配表: {prefix_candidates}"
            )

        # 无任何匹配，报错
        raise ValueError(
            f"品种 '{self.symbol}' 在数据库中未找到匹配的数据表。"
            f"可用表: {tables}"
        )

    def _reset_state(self) -> None:
        """重置运行状态，使 run() 可重复调用而结果不被污染。"""
        self.equity_curve = []
        self.signal_history = []
        self._cum_realized_pnl = {}
        self._cum_realized_pnl_currency: dict[str, float] = {}
        self._pair_counts = {}
        self.trade_bars = []
        self.czsc_obj = None
        self.strategy = None
        # A76: per-run rollover open-gating audit state
        self._rollover_rejected_opens: dict[str, int] = {}
        self._rollover_unavailable_reason: str | None = None
        # A80: honest data-quality reporting for rows skipped during bar loading
        self.unparseable_rows_skipped = 0
        # 清空 bars 强制重新加载，避免日期/参数修改后仍使用旧数据
        self.bars = []

    def bar_generator(
        self, warmup_bars: int = 100
    ) -> "Generator[tuple[str, Any, float, float, float], tuple[float, float] | None, dict] | dict":
        """
        构建逐 bar 可步进的回测生成器（A86）。

        执行与 run() 完全相同的初始化（数据加载、多周期K线合成、CZSC对象
        与策略初始化、各开关解析），然后返回一个驱动主循环的生成器对象，
        而不是像 run() 那样一次性跑完。

        生成器在每根交易 bar 的两个既有权益/保证金计算点各 yield 一次：
          - ("pre_open", dt, price, equity, margin): 当根开盘前（按 bar.open
            计算），计算值用于当根 bar 执行的待执行信号的开仓 sizing；
          - ("post_bar", dt, price, equity, margin): 当根信号生成后（按
            bar.close 计算），计算值用于当根 bar 的权益曲线记录（仅
            sizing_model="risk" 路径）。
        外部驱动可对任一个 yield 点 .send((equity, total_open_margin)) 注入
        覆盖值；.send(None) 表示不覆盖，引擎沿用自身计算值（与 run() 的
        默认行为完全一致）。生成器耗尽时通过 StopIteration.value 返回回测
        报告字典（与 run() 的返回值相同）。

        若数据加载或预热检查失败，与 run() 的早退路径一致，直接返回错误
        字典而非生成器。

        :param warmup_bars: 预热K线数量（以交易周期计）
        :return: 逐 bar 生成器（正常路径）或错误字典（早退路径）
        """
        # 重置状态，保证 run() 幂等
        self._reset_state()

        if not self.load_data():
            return {"error": "数据加载失败"}

        if len(self.bars) < 100:
            return {"error": f"数据不足: 实际{len(self.bars)}根K线"}

        # --- 多级别K线合成 ---
        trade_freq_name = STRATEGY_CONFIG.get("trade_freq", "30分钟")
        filter_freq_name = STRATEGY_CONFIG.get("filter_freq", "日线")

        # 确定交易周期的分钟数
        trade_minutes = self._freq_to_minutes(trade_freq_name)

        # 从1分钟K线合成交易周期K线
        trade_freq_obj = self._freq_name_to_czsc_freq(trade_freq_name)
        trade_bars = resample_bars(self.bars, trade_freq_obj, trade_minutes)
        self.trade_bars = trade_bars  # 保存供外部验证使用
        print(f"K线合成: {len(self.bars)}根1分钟 → {len(trade_bars)}根{trade_freq_name}")

        # 从1分钟K线合成日线K线（用于趋势过滤）
        daily_agg = STRATEGY_CONFIG.get("daily_agg", "natural")
        night_session_start_hour = STRATEGY_CONFIG.get("night_session_start_hour", 20)
        daily_bars = resample_bars(
            self.bars, Freq.D, target_minutes=None,
            daily_agg=daily_agg,
            night_session_start_hour=night_session_start_hour,
        )
        print(f"K线合成: {len(self.bars)}根1分钟 → {len(daily_bars)}根日线")

        # 从1分钟K线合成4H K线（仅用于 A44 daily_4h 共振模式）
        resonance_filter = STRATEGY_CONFIG.get("resonance_filter", "off")
        freq_4h_name = STRATEGY_CONFIG.get("resonance_freq_4h", "240分钟")
        h4_bars: list[RawBar] = []
        czsc_4h = None
        if resonance_filter == "daily_4h":
            h4_minutes = self._freq_to_minutes(freq_4h_name)
            h4_freq_obj = self._freq_name_to_czsc_freq(freq_4h_name)
            h4_bars = resample_bars(self.bars, h4_freq_obj, h4_minutes)
            print(f"K线合成: {len(self.bars)}根1分钟 → {len(h4_bars)}根{freq_4h_name}")

        if len(trade_bars) < warmup_bars + 10:
            return {"error": f"交易周期数据不足: 需要至少{warmup_bars+10}根{trade_freq_name}K线，"
                    f"实际{len(trade_bars)}根"}

        # --- 初始化多级别CZSC对象 ---
        # 交易周期CZSC（主分析对象）
        czsc_trade = CZSC(trade_bars[:warmup_bars])

        # 日线CZSC（趋势过滤）- 找到warmup对应的日线范围
        warmup_dt = trade_bars[warmup_bars - 1].dt if warmup_bars <= len(trade_bars) else trade_bars[-1].dt
        daily_warmup_bars = [b for b in daily_bars if b.dt <= warmup_dt]
        czsc_daily = CZSC(daily_warmup_bars) if len(daily_warmup_bars) >= 3 else None
        enable_daily_filter = STRATEGY_CONFIG.get("filter_freq") == "日线" and czsc_daily is not None
        if STRATEGY_CONFIG.get("filter_freq") == "日线" and czsc_daily is None:
            print("日线趋势过滤不可用: 日线预热数据不足，已自动禁用日线过滤")

        # 4H CZSC（A44 daily_4h 共振）- 找到warmup对应的4H范围
        h4_bar_idx = 0
        if resonance_filter == "daily_4h" and h4_bars:
            h4_warmup_bars = [b for b in h4_bars if b.dt <= warmup_dt]
            czsc_4h = CZSC(h4_warmup_bars) if len(h4_warmup_bars) >= 3 else None
            h4_bar_idx = len(h4_warmup_bars)
            if czsc_4h is None:
                print("4H共振过滤不可用: 4H预热数据不足，已自动禁用4H过滤")

        # 初始化策略（使用交易周期频率名）
        self.strategy = ChanTimingStrategy(
            symbol=self.symbol, freq=trade_freq_name,
            commission_rate=self.commission_rate, slippage=self.slippage,
            enable_daily_filter=enable_daily_filter,
            enable_short=self.enable_short,
        )

        # 构建日线bar时间索引，用于增量更新日线CZSC
        daily_bar_idx = len(daily_warmup_bars)

        # --- 回测主循环（按交易周期K线驱动） ---
        # 实现"延迟一根bar成交": 信号在当根产生，下一根bar开盘价成交
        # 止损/超时等风控仍当根bar.close立即执行
        print(f"开始回测: 预热{warmup_bars}根{trade_freq_name}K线, "
              f"交易{len(trade_bars)-warmup_bars}根K线")

        pending_signals = None  # 上一根bar产生的待执行信号
        sizing_model = STRATEGY_CONFIG.get("sizing_model", "research")
        risk_mode = sizing_model == "risk"

        # A51/A67: pre-compute daily previous-close map for limit-band tagging/gating.
        limit_halt_model = STRATEGY_CONFIG.get("limit_halt_model", "off")
        limit_active = limit_halt_model in ("aware", "enforce")
        prev_close_map = _daily_prev_close_map(trade_bars) if limit_active else {}
        if limit_active:
            symbol_key = _position_symbol_key(self.symbol)
            symbol_limit = SYMBOL_LIMIT_CONFIG.get(symbol_key)
            if symbol_limit is None:
                raise ValueError(
                    f"limit_halt_model='{limit_halt_model}' requires a SYMBOL_LIMIT_CONFIG entry for "
                    f"normalized symbol {symbol_key!r} (raw symbol={self.symbol!r}). "
                    f"Add the symbol to limit_config.py or use limit_halt_model='off'."
                )

        # A76: pre-compute rollover exclusion window when gating is active.
        rollover_open_gating = STRATEGY_CONFIG.get("rollover_open_gating", "off")
        rollover_gating_active = rollover_open_gating == "on"
        excluded_dates: set[date] = set()
        if rollover_gating_active:
            try:
                transitions = _detect_transitions(
                    Path(self.db_path), self.symbol, self.start_date, self.end_date
                )
            except Exception as e:  # pragma: no cover - defensive best-effort fallback
                self._rollover_unavailable_reason = f"detection_failed: {e}"
                transitions = {"unavailable": self._rollover_unavailable_reason}
            if transitions.get("unavailable"):
                self._rollover_unavailable_reason = transitions["unavailable"]
                print(
                    f"[!] rollover_open_gating='on' but rollover detection unavailable: "
                    f"{transitions['unavailable']}; gating disabled for this run"
                )
            else:
                trading_dates = _trading_dates_from_bars(Path(self.db_path), self.symbol)
                excluded_dates, _ = _exclusion_dates(
                    transitions.get("transition_dates", []), trading_dates
                )
                if not excluded_dates:
                    print(
                        "[!] rollover_open_gating='on' but no rollover exclusion dates "
                        "found in the current window"
                    )

        def _bar_loop() -> Generator[tuple[str, Any, float, float, float], tuple[float, float] | None, dict]:
            nonlocal pending_signals, daily_bar_idx, h4_bar_idx, excluded_dates

            for i in range(warmup_bars, len(trade_bars)):
                bar = trade_bars[i]
                rollover_open_blocked = rollover_gating_active and (bar.dt.date() in excluded_dates)

                # A51/A67: compute per-bar directional limit-band flags for entry/exit tagging/gating.
                entry_at_limit: tuple[bool, bool] | None = None
                exit_at_limit: tuple[bool, bool] | None = None
                if limit_active:
                    # Local import avoids the backtest_engine <-> portfolio_engine cycle.
                    from chan_strategy.portfolio_engine import _trading_day

                    bar_trading_day = _trading_day(
                        bar.dt, daily_agg="trading_calendar", night_session_start_hour=night_session_start_hour
                    )
                    limit_pct = _limit_pct_for_date(symbol_key, bar_trading_day)
                    if limit_pct is None:
                        raise ValueError(
                            f"limit_halt_model='{limit_halt_model}' requires a SYMBOL_LIMIT_CONFIG entry for "
                            f"normalized symbol {symbol_key!r} (raw symbol={self.symbol!r}). "
                            f"Add the symbol to limit_config.py or use limit_halt_model='off'."
                        )
                    prev_close, _ = prev_close_map.get(bar_trading_day, (None, None))
                    touched_upper, touched_lower, _, _ = _bar_at_limit(bar, prev_close, limit_pct)
                    # Pass both directional touches down to the position layer; each
                    # position resolves the touch that matters for its own side.
                    entry_at_limit = (touched_upper, touched_lower)
                    exit_at_limit = (touched_upper, touched_lower)

                # Pre-update equity/margin for A40 risk-mode sizing (no lookahead).
                # Uses bar.open, the same delayed-fill execution price used by opens.
                equity_at_entry = None
                total_open_margin = None
                if risk_mode:
                    equity_at_entry, total_open_margin = self._compute_equity_and_margin(bar.open)
                    override = yield ("pre_open", bar.dt, bar.open, equity_at_entry, total_open_margin)
                    if override is not None:
                        equity_at_entry, total_open_margin = override

                # 1. 先执行上一根bar产生的待执行信号（用当根开盘价成交）
                update_kwargs = {
                    "execution_price": bar.open,
                    "czsc_obj": czsc_trade,
                    "bar_high": bar.high,
                    "bar_low": bar.low,
                    "equity_at_entry": equity_at_entry,
                    "total_open_margin": total_open_margin,
                    "rollover_open_blocked": rollover_open_blocked,
                }
                # A51/A67 flags are injected under "aware" and "enforce"; "off" keeps
                # the legacy call signature unchanged.
                if limit_active:
                    update_kwargs["entry_at_limit"] = entry_at_limit
                    update_kwargs["exit_at_limit"] = exit_at_limit

                if pending_signals is not None:
                    self.strategy.update(
                        pending_signals, bar.close, bar.dt,
                        **update_kwargs,
                    )
                    pending_signals = None
                else:
                    # 无待执行信号时，仍需更新风控（止损/超时检查用当前价格）
                    # 传入空信号字典，只触发风控逻辑
                    # intrabar 触价止损用当根 bar 的 high/low（仅当前bar，无未来函数）
                    self.strategy.update({}, bar.close, bar.dt, **update_kwargs)

                # 2. 更新交易周期CZSC
                czsc_trade.update(bar)

                # 3. 增量更新日线CZSC（当有新的日线bar时）
                if czsc_daily is not None:
                    while daily_bar_idx < len(daily_bars) and daily_bars[daily_bar_idx].dt <= bar.dt:
                        czsc_daily.update(daily_bars[daily_bar_idx])
                        daily_bar_idx += 1

                # 4. 增量更新4H CZSC（当有新的4H bar时，dt <= 当前bar，无未来函数）
                if czsc_4h is not None:
                    while h4_bar_idx < len(h4_bars) and h4_bars[h4_bar_idx].dt <= bar.dt:
                        czsc_4h.update(h4_bars[h4_bar_idx])
                        h4_bar_idx += 1

                # 5. 生成当根信号（但不立即成交，存储到pending_signals）
                # 传递一买/一卖锚点信息，使二买/二卖信号能严格绑定上下文
                buy1_anchor = self.strategy.get_last_buy1_anchor() if self.strategy else None
                sell1_anchor = self.strategy.get_last_sell1_anchor() if self.strategy else None
                signals = get_all_signals(
                    czsc_trade, trade_freq_name,
                    buy1_anchor=buy1_anchor,
                    sell1_anchor=sell1_anchor,
                )

                # 添加日线趋势过滤信号（由 positions.py / ChanTimingStrategy 消费）
                if czsc_daily is not None and czsc_daily.bi_list:
                    daily_signals = get_all_signals(czsc_daily, filter_freq_name)
                    signals.update(daily_signals)

                # 添加4H共振过滤信号（A44 daily_4h 模式消费）
                if czsc_4h is not None and czsc_4h.bi_list:
                    h4_signals = get_all_signals(czsc_4h, freq_4h_name)
                    signals.update(h4_signals)

                # 记录信号历史（每100根记录一次，避免内存过大）
                if i % 100 == 0 or i == len(trade_bars) - 1:
                    self.signal_history.append({
                        "dt": bar.dt,
                        "price": bar.close,
                        "signals": signals.copy()
                    })

                # 5. 存储信号，下一根bar再执行
                pending_signals = signals

                if risk_mode:
                    # A40 real-money equity curve: incrementally track currency PnL,
                    # then compute equity and margin at this bar's close.
                    self._update_realized_currency()
                    equity, total_open_margin_now = self._compute_equity_and_margin(bar.close)
                    override = yield ("post_bar", bar.dt, bar.close, equity, total_open_margin_now)
                    if override is not None:
                        equity, total_open_margin_now = override
                    margin_utilization_pct = (
                        total_open_margin_now / equity if equity > 0 else 0.0
                    )

                    long_exposure = 0.0
                    short_exposure = 0.0
                    for pos in self.strategy.positions:
                        if pos.pos == 0 or pos.cost <= 0:
                            continue
                        spec = self._contract_spec_for_position(pos)
                        multiplier = int(spec.get("multiplier", 1))
                        notional = pos.volume * pos.cost * multiplier
                        if equity > 0:
                            if pos.pos > 0:
                                long_exposure += notional / equity
                            else:
                                short_exposure += notional / equity

                    net_exposure = long_exposure - short_exposure
                    gross_exposure = long_exposure + short_exposure

                    self.equity_curve.append({
                        "dt": bar.dt,
                        "price": bar.close,
                        "equity": equity,
                        "positions": sum(p.pos for p in self.strategy.positions),
                        "long_exposure": long_exposure,
                        "short_exposure": short_exposure,
                        "net_exposure": net_exposure,
                        "gross_exposure": gross_exposure,
                        "both_long_short": long_exposure > 0 and short_exposure > 0,
                        "sizing_model": sizing_model,
                        "total_open_margin": total_open_margin_now,
                        "margin_utilization_pct": margin_utilization_pct,
                    })
                else:
                    # 计算当前权益（增量更新，避免每根bar遍历全部历史pairs）
                    pos_weights = {
                        "一买多头": STRATEGY_CONFIG.get("pos_1buy", 0.10),
                        "二买多头": STRATEGY_CONFIG.get("pos_2buy", 0.20),
                        "三买多头": STRATEGY_CONFIG.get("pos_3buy", 0.30),
                        "一卖空头": STRATEGY_CONFIG.get("pos_1sell", 0.10),
                        "二卖空头": STRATEGY_CONFIG.get("pos_2sell", 0.20),
                        "三卖空头": STRATEGY_CONFIG.get("pos_3sell", 0.30),
                    }
                    weight_symbol = self.table_name.split("_")[0] if self.table_name else self.symbol
                    pos_weights = _apply_symbol_position_overrides(pos_weights, weight_symbol)
                    total_pnl = 0
                    long_exposure = 0.0
                    short_exposure = 0.0
                    for pos in self.strategy.positions:
                        weight = pos_weights.get(pos.name, 0.10)
                        if pos.pos > 0:
                            long_exposure += weight
                        elif pos.pos < 0:
                            short_exposure += weight
                        prev_count = self._pair_counts.get(pos.name, 0)
                        curr_count = len(pos.pairs)
                        # 只有当 pair 数量增加时，才累加新增 pair 的盈亏
                        if curr_count > prev_count:
                            new_pairs = pos.pairs[prev_count:curr_count]
                            new_pnl = sum(p["pnl_pct"] for p in new_pairs) * self.initial_capital * weight
                            self._cum_realized_pnl[pos.name] = self._cum_realized_pnl.get(pos.name, 0.0) + new_pnl
                            self._pair_counts[pos.name] = curr_count
                        realized_pnl = self._cum_realized_pnl.get(pos.name, 0.0)
                        # 加入未实现盈亏
                        if pos.pos != 0 and pos.cost > 0:
                            if pos.pos > 0:
                                unrealized_pnl = (bar.close - pos.cost) / pos.cost
                            else:
                                unrealized_pnl = (pos.cost - bar.close) / pos.cost
                            realized_pnl += unrealized_pnl * self.initial_capital * weight
                        total_pnl += realized_pnl

                    equity = self.initial_capital + total_pnl
                    net_exposure = long_exposure - short_exposure
                    gross_exposure = long_exposure + short_exposure

                    self.equity_curve.append({
                        "dt": bar.dt,
                        "price": bar.close,
                        "equity": equity,
                        "positions": sum(p.pos for p in self.strategy.positions),
                        "long_exposure": long_exposure,
                        "short_exposure": short_exposure,
                        "net_exposure": net_exposure,
                        "gross_exposure": gross_exposure,
                        "both_long_short": long_exposure > 0 and short_exposure > 0,
                        "sizing_model": sizing_model,
                    })

                # 进度提示
                if (i - warmup_bars) % 500 == 0 and i > warmup_bars:
                    pct = (i - warmup_bars) / (len(trade_bars) - warmup_bars) * 100
                    print(f"  进度: {pct:.1f}% ({i-warmup_bars}/{len(trade_bars)-warmup_bars})")

            # 保存CZSC对象供外部使用
            self.czsc_obj = czsc_trade

            # A52: post-loop rollover-window tagging only when explicitly enabled.
            # "off" skips this entirely, keeping the legacy path byte-identical.
            if STRATEGY_CONFIG.get("rollover_stat_tagging", "off") == "on":
                excluded_dates = self._rollover_excluded_dates()
                for pos in self.strategy.positions:
                    for pair in pos.pairs:
                        pair["is_rollover_window"] = _pair_in_exclusion_window(pair, excluded_dates)

            # 生成报告
            return self.generate_report()

        return _bar_loop()

    def run(self, warmup_bars: int = 100) -> dict:
        """
        执行回测 - 多级别协同分析

        修复: 原实现只用单一CZSC对象分析1分钟K线。
        现在从1分钟基础数据合成交易周期(30分钟)和日线，
        分别创建CZSC对象进行缠论分析，综合多周期信号。

        A86 起，本方法是 bar_generator() 的默认耗尽包装：全程 send(None)
        （不注入任何覆盖值），行为与重构前逐字节一致。

        :param warmup_bars: 预热K线数量（以交易周期计）
        :return: 回测结果字典
        """
        gen = self.bar_generator(warmup_bars)
        if isinstance(gen, dict):
            # 早退路径（数据加载失败/数据不足）：bar_generator 直接返回错误字典
            return gen
        try:
            to_send = None
            while True:
                gen.send(to_send)
                to_send = None  # 默认耗尽：永不注入覆盖值，行为与重构前一致
        except StopIteration as stop:
            return stop.value

    def _compute_equity_and_margin(self, price: float) -> tuple[float, float]:
        """Compute running equity and total open initial margin in currency terms.

        Used by A40 risk-mode sizing and equity-curve reporting.  Reads only the
        current open positions and closed pairs known up to this bar.
        """
        realized_pnl = 0.0
        for pos in self.strategy.positions:
            realized_pnl += self._cum_realized_pnl_currency.get(pos.name, 0.0)

        unrealized_pnl = 0.0
        total_open_margin = 0.0
        for pos in self.strategy.positions:
            if pos.pos == 0 or pos.cost <= 0:
                continue
            spec = self._contract_spec_for_position(pos)
            multiplier = int(spec.get("multiplier", 1))
            margin_rate = float(spec.get("margin_rate", 0.0))
            notional = pos.volume * pos.cost * multiplier
            if pos.pos > 0:
                unrealized_pnl += (price - pos.cost) * pos.volume * multiplier
            else:
                unrealized_pnl += (pos.cost - price) * pos.volume * multiplier
            total_open_margin += notional * margin_rate

        equity = self.initial_capital + realized_pnl + unrealized_pnl
        return equity, total_open_margin

    def _contract_spec_for_position(self, pos) -> dict:
        """Resolve A40 contract spec for a Position's symbol."""
        from chan_strategy.positions import _research_contract_spec
        return _research_contract_spec(pos.symbol)

    def _rollover_excluded_dates(self) -> set[date]:
        """Return the set of dates in any rollover exclusion window for the symbol."""
        try:
            transitions = _detect_transitions(
                Path(self.db_path), self.symbol, self.start_date, self.end_date
            )
        except Exception:
            # Tagging is best-effort: if the metadata DB is missing or malformed,
            # fall back to no tags rather than failing the backtest.
            return set()
        if transitions.get("unavailable"):
            return set()
        trading_dates = _trading_dates_from_bars(Path(self.db_path), self.symbol)
        excluded, _ = _exclusion_dates(transitions.get("transition_dates", []), trading_dates)
        return excluded

    def _update_realized_currency(self) -> None:
        """Incrementally track closed-pair currency PnL for risk-mode accounting."""
        for pos in self.strategy.positions:
            prev_count = self._pair_counts.get(pos.name, 0)
            curr_count = len(pos.pairs)
            if curr_count > prev_count:
                new_pairs = pos.pairs[prev_count:curr_count]
                new_pnl = sum(p.get("pnl_currency", 0.0) for p in new_pairs)
                self._cum_realized_pnl_currency[pos.name] = (
                    self._cum_realized_pnl_currency.get(pos.name, 0.0) + new_pnl
                )
                self._pair_counts[pos.name] = curr_count

    @staticmethod
    def _freq_to_minutes(freq_name: str) -> int:
        """将频率名转换为分钟数"""
        freq_minutes_map = {
            "1分钟": 1, "5分钟": 5, "15分钟": 15,
            "30分钟": 30, "60分钟": 60, "120分钟": 120,
            "240分钟": 240,
        }
        return freq_minutes_map.get(freq_name, 30)

    @staticmethod
    def _freq_name_to_czsc_freq(freq_name: str) -> Freq:
        """将频率名转换为czsc Freq对象"""
        name_to_freq = {
            "1分钟": Freq.F1, "5分钟": Freq.F5, "15分钟": Freq.F15,
            "30分钟": Freq.F30, "60分钟": Freq.F60, "120分钟": Freq.F120,
            "240分钟": Freq.F120,  # czsc 没有 F240；仅作为元数据，不影响信号生成
            "日线": Freq.D, "周线": Freq.W, "月线": Freq.M,
        }
        return name_to_freq.get(freq_name, Freq.F30)

    def generate_report(self) -> dict:
        """生成回测报告"""
        if not self.equity_curve:
            return {"error": "未执行回测"}

        sizing_model = STRATEGY_CONFIG.get("sizing_model", "research")
        limit_halt_model = STRATEGY_CONFIG.get("limit_halt_model", "off")
        portfolio_risk = STRATEGY_CONFIG.get("portfolio_risk", "off")
        rollover_open_gating = STRATEGY_CONFIG.get("rollover_open_gating", "off")

        # 基础信息
        report = {
            "symbol": self.symbol,
            "freq": self.freq,
            "sizing_model": sizing_model,
            "limit_halt_model": limit_halt_model,
            "exit_event_semantics": STRATEGY_CONFIG.get("exit_event_semantics", "legacy"),
            "stop_execution_model": STRATEGY_CONFIG.get("stop_execution_model", "close"),
            "stop_penalty_bp": STRATEGY_CONFIG.get("stop_penalty_bp", 0),
            "resonance_filter": STRATEGY_CONFIG.get("resonance_filter", "off"),
            "portfolio_risk": portfolio_risk,
            "rollover_open_gating": rollover_open_gating,
            "weighting": STRATEGY_CONFIG.get("weighting", "fixed"),
            "period": f"{self.start_date} ~ {self.end_date}",
            "total_bars": len(self.bars),
            "unparseable_rows_skipped": self.unparseable_rows_skipped,
            "traded_bars": len(self.equity_curve),
            "mode_label": _compute_mode_label(
                sizing_model, limit_halt_model, portfolio_risk, rollover_open_gating
            ),
        }

        # 各子策略绩效
        report["sub_strategies"] = self.strategy.evaluate_all()

        report["max_long_exposure"] = max((e.get("long_exposure", 0.0) for e in self.equity_curve), default=0.0)
        report["max_short_exposure"] = max((e.get("short_exposure", 0.0) for e in self.equity_curve), default=0.0)
        report["max_gross_exposure"] = max((e.get("gross_exposure", 0.0) for e in self.equity_curve), default=0.0)
        report["both_long_short_bars"] = sum(1 for e in self.equity_curve if e.get("both_long_short", False))

        if STRATEGY_CONFIG.get("sizing_model", "research") == "risk":
            report["max_total_open_margin"] = max(
                (e.get("total_open_margin", 0.0) for e in self.equity_curve), default=0.0
            )
            report["max_margin_utilization_pct"] = max(
                (e.get("margin_utilization_pct", 0.0) for e in self.equity_curve), default=0.0
            )
            report["final_total_open_margin"] = (
                self.equity_curve[-1].get("total_open_margin", 0.0) if self.equity_curve else 0.0
            )

        # A76: surface rollover open-gating audit state so degraded/unavailable
        # detection is not silently indistinguishable from "gating worked".
        if rollover_open_gating == "on":
            positions = getattr(self.strategy, "positions", []) if self.strategy else []
            report["rollover_open_gating_rejected_opens"] = {
                pos.name: pos._rollover_rejected_opens for pos in positions
            }
            report["rollover_open_gating_unavailable"] = self._rollover_unavailable_reason

        # sizing_model caveat: surfaced in report body so readers of the file see it
        sizing_model = report["sizing_model"]
        if sizing_model == "research":
            report["sizing_caveat"] = (
                "当前为信号研究模式（方向型仓位+事后加权），"
                "未建模合约乘数/资金上限/复利，仅评估信号有效性。"
            )
        else:
            report["sizing_caveat"] = None

        # 总体绩效
        all_pairs = self.strategy.get_combined_trades()
        report["total_trades"] = len(all_pairs)

        if all_pairs:
            pnls = [p["pnl_pct"] for p in all_pairs]
            wins = [p for p in pnls if p > 0]
            losses = [p for p in pnls if p <= 0]

            report["win_rate"] = len(wins) / len(pnls)
            report["avg_profit_pct"] = np.mean(wins) * 100 if wins else 0
            report["avg_loss_pct"] = np.mean(losses) * 100 if losses else 0
            report["profit_factor"] = (
                sum(wins) / abs(sum(losses)) if losses and sum(losses) != 0 else float('inf')
            )
            report["max_profit_pct"] = max(pnls) * 100
            report["max_loss_pct"] = min(pnls) * 100
            report["avg_bars_held"] = np.mean([p["bars_held"] for p in all_pairs])

            # 计算最大回撤
            equity_values = [e["equity"] for e in self.equity_curve]
            report["final_equity"] = equity_values[-1]
            report["total_return_pct"] = (equity_values[-1] / self.initial_capital - 1) * 100

            peak = equity_values[0]
            max_dd = 0
            for eq in equity_values:
                peak = max(peak, eq)
                dd = (peak - eq) / peak
                max_dd = max(max_dd, dd)
            report["max_drawdown_pct"] = max_dd * 100

            # 夏普比率（修复: 先聚合为日收益率，再年化）
            # 原实现用每根bar的收益率×√252，但bar是交易周期(30分钟)级别
            # 正确做法: 按日聚合权益曲线，计算日收益率，再×√252年化
            if len(equity_values) > 1:
                equity_series = pd.Series(
                    equity_values,
                    index=[e["dt"] for e in self.equity_curve]
                )
                # 按日取最后一个值
                daily_equity = equity_series.groupby(
                    equity_series.index.map(lambda dt: dt.date())
                ).last()
                daily_returns = daily_equity.pct_change().dropna()
                if len(daily_returns) > 1 and daily_returns.std() > 0:
                    report["sharpe_ratio"] = float(
                        (daily_returns.mean() / daily_returns.std()) * np.sqrt(252)
                    )
                else:
                    report["sharpe_ratio"] = 0
            else:
                report["sharpe_ratio"] = 0
        else:
            report["win_rate"] = 0
            report["total_return_pct"] = 0
            report["max_drawdown_pct"] = 0
            report["sharpe_ratio"] = 0
            report["final_equity"] = self.initial_capital

        return report

    def _get_freq_name(self) -> str:
        """将数据库频率标识转换为信号频率名"""
        freq_map = {
            "1": "1分钟", "5": "5分钟", "15": "15分钟",
            "30": "30分钟", "60": "60分钟", "120": "120分钟",
            "d": "日线", "w": "周线", "m": "月线",
            "1min": "1分钟", "5min": "5分钟", "15min": "15分钟",
            "30min": "30分钟", "60min": "60分钟",
            "daily": "日线", "day": "日线", "D": "日线",
        }
        return freq_map.get(str(self.freq).lower(), "1分钟")

    def print_report(self, report: dict = None):  # pragma: no cover - presentation helper
        """打印格式化的回测报告"""
        if report is None:
            report = self.generate_report()

        if "error" in report:
            print(f"错误: {report['error']}")
            return

        print("\n" + "=" * 60)
        print("缠论择时策略回测报告")
        print("=" * 60)
        mode_label = report.get("mode_label", "UNKNOWN")
        print(f"模式标签: {mode_label}")
        if mode_label == "RESEARCH_BASELINE":
            print("[!] 本报告为 RESEARCH_BASELINE（研究基线），不构成生产/可交易证据。")
        print(f"标的: {report['symbol']}")
        print(f"频率: {report['freq']}")
        print(f"仓位模型: {report.get('sizing_model', 'research')}")
        print(f"退出事件语义: {report.get('exit_event_semantics', 'legacy')}")
        print(f"回测区间: {report['period']}")
        print(f"K线总数: {report['total_bars']}")
        print(f"跳过无法解析行数: {report.get('unparseable_rows_skipped', 0)}")
        print(f"交易K线: {report['traded_bars']}")
        print(f"手续费率: {self.commission_rate}")
        print(f"滑点: {self.slippage}")
        print(f"止损执行模型: {report.get('stop_execution_model', 'close')} "
              f"(penalty={report.get('stop_penalty_bp', 0)}bp)")
        print("-" * 60)
        print(f"总交易次数: {report['total_trades']}")
        print(f"胜率: {report.get('win_rate', 0)*100:.1f}%")
        if report['total_trades'] > 0:
            print(f"平均盈利: {report.get('avg_profit_pct', 0):.2f}%")
            print(f"平均亏损: {report.get('avg_loss_pct', 0):.2f}%")
            print(f"盈亏比: {report.get('profit_factor', 0):.2f}")
            print(f"平均持仓K线: {report.get('avg_bars_held', 0):.0f}")
        print("-" * 60)
        print(f"总收益率: {report.get('total_return_pct', 0):.2f}%")
        print(f"最大回撤: {report.get('max_drawdown_pct', 0):.2f}%")
        print(f"夏普比率: {report.get('sharpe_ratio', 0):.2f}")
        print(f"最终权益: {report.get('final_equity', 0):,.0f}")
        print(f"最大多头敞口: {report.get('max_long_exposure', 0)*100:.1f}%")
        print(f"最大空头敞口: {report.get('max_short_exposure', 0)*100:.1f}%")
        print(f"最大总敞口: {report.get('max_gross_exposure', 0)*100:.1f}%")
        print(f"多空同时持仓bar数: {report.get('both_long_short_bars', 0)}")
        if report.get('sizing_model') == "risk":
            print(f"最大开仓保证金: {report.get('max_total_open_margin', 0):,.0f}")
            print(f"最大保证金占用率: {report.get('max_margin_utilization_pct', 0)*100:.1f}%")
        print("-" * 60)

        # 子策略详情
        if "sub_strategies" in report:
            print("\n子策略绩效:")
            for name, stats in report["sub_strategies"].items():
                if stats["total_trades"] > 0:
                    print(f"  [{name}] 交易{stats['total_trades']}次, "
                          f"胜率{stats['win_rate']*100:.1f}%, "
                          f"盈亏比{stats['profit_factor']:.2f}")
                else:
                    print(f"  [{name}] 无交易")

        print("-" * 60)
        if report.get('sizing_model') == "risk":
            print("注: 当前为A40风险仓位模型（整数手+合约乘数+保证金上限）。")
            print("    pnl_currency/保证金数字使用 contract_specs 中交易所最低保证金率，")
            print("    仅为回测研究，不是生产可用资金分配建议。")
        else:
            print("注: 当前为信号研究模式（方向型仓位+事后加权），")
            print("    未建模合约乘数/资金上限/复利，仅评估信号有效性。")
        print("=" * 60)


def run_single_backtest(
    symbol: str,
    freq: str = "1",
    start_date: str = None,
    end_date: str = None,
    table_name: str = None,
    **kwargs
) -> dict:
    """便捷函数：运行单个品种回测"""
    engine = BacktestEngine(
        symbol=symbol,
        freq=freq,
        start_date=start_date,
        end_date=end_date,
        table_name=table_name,
        **kwargs
    )
    report = engine.run()
    engine.print_report(report)
    return report


def run_formal_evaluation(
    symbol: str,
    freq: str = "1",
    start_date: str = None,
    end_date: str = None,
    table_name: str = None,
    **kwargs
) -> dict:
    """Run a single backtest under formal-evaluation defaults.

    This entry point temporarily enables ``sizing_model="risk"``,
    ``limit_halt_model="enforce"``, ``rollover_open_gating="on"``,
    ``stop_execution_model="intrabar"``, and ``daily_agg="trading_calendar"``
    for the duration of the run and restores the original values afterward.
    It is the explicit "formal evaluation" path recommended by the third-party
    audit without changing the library defaults in ``config.py``.
    """
    with formal_evaluation_config():
        return run_single_backtest(
            symbol=symbol,
            freq=freq,
            start_date=start_date,
            end_date=end_date,
            table_name=table_name,
            **kwargs,
        )


def run_batch_backtest(
    symbols: list[str],
    freq: str = "1",
    start_date: str = None,
    end_date: str = None,
    **kwargs
) -> pd.DataFrame:
    """批量回测多个品种"""
    results = []
    for symbol in symbols:
        print(f"\n{'=' * 40}")
        print(f"回测: {symbol}")
        engine = BacktestEngine(
            symbol=symbol,
            freq=freq,
            start_date=start_date,
            end_date=end_date,
            **kwargs
        )
        report = engine.run()
        if "error" not in report:
            report_flat = {
                "symbol": symbol,
                "total_trades": report["total_trades"],
                "win_rate": report.get("win_rate", 0),
                "profit_factor": report.get("profit_factor", 0),
                "total_return_pct": report.get("total_return_pct", 0),
                "max_drawdown_pct": report.get("max_drawdown_pct", 0),
                "sharpe_ratio": report.get("sharpe_ratio", 0),
            }
            results.append(report_flat)
        else:
            results.append({"symbol": symbol, "error": report["error"]})

    return pd.DataFrame(results)


def run_portfolio_backtest(
    symbols: list[str],
    freq: str = "1",
    start_date: str = None,
    end_date: str = None,
    initial_capital: float = None,
    commission_rate: float | None = None,
    slippage: float | None = None,
    db_path: str = None,
    enable_short: bool | None = None,
) -> dict:
    """Run a multi-symbol backtest under the P8b portfolio coordinator.

    This is a thin wrapper around ``chan_strategy.portfolio_engine`` so the
    portfolio entry point lives next to ``run_single_backtest`` and
    ``run_batch_backtest``.  The import is deferred to avoid a circular
    dependency between the two modules.
    """
    from chan_strategy.portfolio_engine import PortfolioEngine

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
    )
    return engine.run()
