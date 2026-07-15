"""
缠论择时策略 - Factor/Event/Position 子策略层

架构: Signal → Factor → Event → Position
使用自定义轻量实现，兼容 czsc 框架的 dict 配置格式
"""
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from enum import Enum
from datetime import datetime
from math import floor

from czsc.objects import Direction

from chan_strategy.config import BACKTEST_CONFIG, STRATEGY_CONFIG


def _resolve_limit_flag(
    flag: bool | tuple[bool, bool] | None,
    side: int,
    is_entry: bool,
) -> bool:
    """Translate a directional limit touch into the boolean relevant for ``side``.

    :param flag: ``None`` (no touch), a plain bool (legacy callers), or a
        ``(touched_upper, touched_lower)`` pair from ``_bar_at_limit``.
    :param side: ``+1`` for long, ``-1`` for short.  ``0`` is treated as flat.
    :param is_entry: ``True`` for open, ``False`` for close.

    For an entry, the adverse/unexecutable limit is:
      * long  -> upper (limit-up means you cannot buy favorably)
      * short -> lower (limit-down means you cannot sell favorably)

    For an exit, the adverse/unexecutable limit is:
      * long  -> lower (limit-down means you cannot sell to close)
      * short -> upper (limit-up means you cannot buy to cover)
    """
    if flag is None:
        return False
    if isinstance(flag, tuple):
        touched_upper, touched_lower = flag
        if side > 0:
            return bool(touched_upper) if is_entry else bool(touched_lower)
        if side < 0:
            return bool(touched_lower) if is_entry else bool(touched_upper)
        return False
    return bool(flag)


def _daily_trend_filter_signals(direction: str = "long", strict: bool = True) -> dict:
    """日线趋势过滤信号

    在开仓 Event 的 signals_all/signals_not 中显式引用日线键，
    使 positions.py 成为日线趋势过滤的直接消费方。

    :param direction: long 使用向上趋势过滤；short 使用向下趋势过滤。
    :param strict: 是否要求日线方向同向。二买/三买/二卖/三卖属于右侧顺势信号，
        使用严格过滤；一买/一卖是左侧背驰试仓，只排除高级别明确反向。
    """
    if direction not in {"long", "short"}:
        raise ValueError(f"不支持的日线过滤方向: {direction}")
    trend = "向上" if direction == "long" else "向下"
    blocked_position = "中枢下方" if direction == "long" else "中枢上方"
    return {
        "signals_all": [
            f"日线_D1BI_方向V260615_{trend}_任意_任意_0",
        ] if strict else [],
        "signals_not": [
            f"日线_D1ZS_位置V260615_{blocked_position}_任意_任意_0",
        ],
    }


def _resonance_filter_signals(direction: str = "long", level: str = "日线") -> dict:
    """多级共振过滤信号

    :param direction: long 使用向上趋势过滤；short 使用向下趋势过滤。
    :param level: 高级别频率标签，如 "日线" 或 "240分钟"。
    :return: 包含 signals_all 与 signals_not 的字典，用于开仓 Event。

    "constructive" 复用现有 categorical 信号：
    - 多：方向=向上 且 位置 in {中枢上方, 中枢内}
    - 空：方向=向下 且 位置 in {中枢下方, 中枢内}
    不引入新的数值阈值。
    """
    if direction not in {"long", "short"}:
        raise ValueError(f"不支持的共振过滤方向: {direction}")
    trend = "向上" if direction == "long" else "向下"
    blocked_position = "中枢下方" if direction == "long" else "中枢上方"
    return {
        "signals_all": [
            f"{level}_D1BI_方向V260615_{trend}_任意_任意_0",
        ],
        "signals_not": [
            f"{level}_D1ZS_位置V260615_{blocked_position}_任意_任意_0",
            f"{level}_D1ZS_位置V260615_无中枢_任意_任意_0",
        ],
    }


def _higher_level_filter_signals(direction: str = "long", strict: bool = True) -> dict:
    """Combine daily trend filter with the optional A44 resonance filter.

    When ``resonance_filter`` is ``"off"`` this returns exactly the legacy daily
    filter (byte-identical), preserving the original ``strict`` semantics used by
    each sub-strategy.  ``"daily"`` requires strictly-positive daily structure.
    ``"daily_4h"`` additionally requires constructive 4H structure.
    """
    resonance_filter = STRATEGY_CONFIG.get("resonance_filter", "off")
    if resonance_filter == "off":
        return _daily_trend_filter_signals(direction=direction, strict=strict)

    daily = _resonance_filter_signals(direction=direction, level="日线")
    if resonance_filter == "daily":
        return daily

    # "daily_4h"
    freq_4h = STRATEGY_CONFIG.get("resonance_freq_4h", "240分钟")
    h4 = _resonance_filter_signals(direction=direction, level=freq_4h)
    return {
        "signals_all": daily["signals_all"] + h4["signals_all"],
        "signals_not": daily["signals_not"] + h4["signals_not"],
    }


def _resonance_holds(
    signals_dict: dict,
    direction: str = "long",
    force_resonance: bool = False,
) -> bool:
    """Check whether the configured higher-level resonance filter is satisfied.

    Reuses the same signal strings produced by ``_higher_level_filter_signals``
    so P5/A44 logic is not duplicated.

    When ``force_resonance`` is True, the ``resonance_filter="off"`` fallback to
    the legacy daily trend filter is bypassed and the actual P5 resonance
    condition is enforced: daily level (and 4H when configured as ``daily_4h``).
    """
    if force_resonance:
        resonance_filter = STRATEGY_CONFIG.get("resonance_filter", "off")
        if resonance_filter == "daily_4h":
            freq_4h = STRATEGY_CONFIG.get("resonance_freq_4h", "240分钟")
            daily = _resonance_filter_signals(direction=direction, level="日线")
            h4 = _resonance_filter_signals(direction=direction, level=freq_4h)
            filters = {
                "signals_all": daily["signals_all"] + h4["signals_all"],
                "signals_not": daily["signals_not"] + h4["signals_not"],
            }
        else:
            filters = _resonance_filter_signals(direction=direction, level="日线")
    else:
        filters = _higher_level_filter_signals(direction=direction, strict=True)

    for s in filters.get("signals_all", []):
        if not Signal(s).is_match(signals_dict):
            return False
    for s in filters.get("signals_not", []):
        if Signal(s).is_match(signals_dict):
            return False
    return True


def _atr_filter_signals(freq: str) -> dict:
    """Universal ATR chop filter signals added to every open Event.

    When ``atr_chop_filter`` is ``"off"`` (default) this returns empty lists,
    keeping the legacy behavior byte-identical.
    """
    if STRATEGY_CONFIG.get("atr_chop_filter") != "on":
        return {"signals_all": [], "signals_not": []}
    return {
        "signals_all": [f"{freq}_ATR_波动V260615_扩张_任意_任意_100"],
        "signals_not": [],
    }


# ========== 轻量级自定义实现 ==========

class Operate(Enum):
    """操作类型"""
    LO = "开多"   # Long Open
    LC = "平多"   # Long Close
    SO = "开空"   # Short Open
    SC = "平空"   # Short Close
    HO = "持有"   # Hold


@dataclass
class Signal:
    """信号对象"""
    value: str  # 完整信号字符串 k1_k2_k3_v1_v2_v3_score

    @property
    def key(self) -> str:
        parts = self.value.split("_")
        return f"{parts[0]}_{parts[1]}_{parts[2]}"

    @property
    def signal_value(self) -> str:
        parts = self.value.split("_")
        return f"{parts[3]}_{parts[4]}_{parts[5]}_{parts[6]}"

    def is_match(self, signals_dict: dict) -> bool:
        """检查信号是否匹配当前信号字典"""
        key = self.key
        if key not in signals_dict:
            return False
        # 检查值匹配（支持"任意"通配）
        expected_parts = self.signal_value.split("_")
        actual_parts = signals_dict[key].split("_")
        for exp, act in zip(expected_parts[:3], actual_parts[:3]):
            if exp != "任意" and exp != act:
                return False
        return True


@dataclass
class Factor:
    """因子 - 信号的组合"""
    name: str
    signals_all: List[Signal] = field(default_factory=list)
    signals_any: List[Signal] = field(default_factory=list)
    signals_not: List[Signal] = field(default_factory=list)

    def is_match(self, signals_dict: dict) -> bool:
        """检查因子是否匹配"""
        # all 条件必须全部满足
        if self.signals_all:
            if not all(s.is_match(signals_dict) for s in self.signals_all):
                return False
        # any 条件至少满足一个
        if self.signals_any:
            if not any(s.is_match(signals_dict) for s in self.signals_any):
                return False
        # not 条件必须全部不满足
        if self.signals_not:
            if any(s.is_match(signals_dict) for s in self.signals_not):
                return False
        return True

    @classmethod
    def load(cls, config: dict) -> 'Factor':
        return cls(
            name=config.get("name", ""),
            signals_all=[Signal(s) for s in config.get("signals_all", [])],
            signals_any=[Signal(s) for s in config.get("signals_any", [])],
            signals_not=[Signal(s) for s in config.get("signals_not", [])],
        )


@dataclass
class Event:
    """事件 - Factor组合 + 操作"""
    name: str
    operate: Operate
    factors: List[Factor] = field(default_factory=list)
    signals_all: List[Signal] = field(default_factory=list)
    signals_any: List[Signal] = field(default_factory=list)
    signals_not: List[Signal] = field(default_factory=list)
    is_structural: bool = field(default=False, compare=False)
    is_partial_tp: bool = field(default=False, compare=False)

    def is_match(self, signals_dict: dict) -> bool:
        """检查事件是否触发"""
        # 事件级别的信号条件
        if self.signals_all:
            if not all(s.is_match(signals_dict) for s in self.signals_all):
                return False
        if self.signals_any:
            if not any(s.is_match(signals_dict) for s in self.signals_any):
                return False
        if self.signals_not:
            if any(s.is_match(signals_dict) for s in self.signals_not):
                return False

        # 至少一个因子满足
        if self.factors:
            return any(f.is_match(signals_dict) for f in self.factors)
        return True

    @classmethod
    def load(cls, config: dict) -> 'Event':
        operate_map = {
            "开多": Operate.LO, "平多": Operate.LC,
            "开空": Operate.SO, "平空": Operate.SC,
        }
        return cls(
            name=config.get("name", ""),
            operate=operate_map.get(config.get("operate", ""), Operate.HO),
            factors=[Factor.load(f) for f in config.get("factors", [])],
            signals_all=[Signal(s) for s in config.get("signals_all", [])],
            signals_any=[Signal(s) for s in config.get("signals_any", [])],
            signals_not=[Signal(s) for s in config.get("signals_not", [])],
        )


@dataclass
class TradeRecord:
    """交易记录"""
    dt: datetime
    operate: Operate
    price: float
    volume: float = 1.0
    reason: str = ""


REASON_CODE_MAP = {
    "移动止损": "trailing_stop",
    "绉诲姩姝㈡崯": "trailing_stop",
    "ATR移动止损": "atr_trailing_stop",
    "止损": "stop_loss",
    "姝㈡崯": "stop_loss",
    "超时": "timeout",
    "瓒呮椂": "timeout",
}


def normalize_exit_reason(reason: str) -> str:
    """Normalize human-readable exit reason to a stable enum-like code."""
    if reason in REASON_CODE_MAP:
        return REASON_CODE_MAP[reason]
    if reason.startswith("信号平仓") or reason.startswith("淇″彿骞仓"):
        return "signal_exit"
    if reason.startswith("部分止盈"):
        return "partial_tp"
    if "风控" in reason or "风险" in reason:
        return "risk_exit"
    if reason:
        return "other"
    return "unknown"


def _research_symbol_key(symbol: str) -> str:
    """Normalize symbol for research-only per-symbol config maps."""
    return str(symbol or "").upper().split(".")[0]


def _research_contract_spec(symbol: str) -> dict:
    """Return contract spec for a symbol, falling back to unit multiplier.

    Keys are matched case-insensitively against STRATEGY_CONFIG['contract_specs'].
    """
    specs = STRATEGY_CONFIG.get("contract_specs") or {}
    key = _research_symbol_key(symbol)
    if key in specs:
        return dict(specs[key])
    # Fallback: try the raw upper-cased symbol as well.
    if str(symbol or "").upper() in specs:
        return dict(specs[str(symbol or "").upper()])
    return {"multiplier": 1, "tick": 0.01, "margin_rate": 0.0}


def _research_trailing_params(symbol: str) -> tuple[int, float]:
    """Return trailing params, optionally overridden per symbol for diagnostics."""
    overrides = STRATEGY_CONFIG.get("trailing_overrides") or {}
    item = overrides.get(_research_symbol_key(symbol), None)
    if isinstance(item, dict):
        return (
            item.get("trailing_start_bp", STRATEGY_CONFIG.get("trailing_start_bp", 300)),
            item.get("trailing_drawback_pct", STRATEGY_CONFIG.get("trailing_drawback_pct", 0.25)),
        )
    if isinstance(item, (list, tuple)) and len(item) == 2:
        return item[0], item[1]
    return (
        STRATEGY_CONFIG.get("trailing_start_bp", 300),
        STRATEGY_CONFIG.get("trailing_drawback_pct", 0.25),
    )


def _research_second_buy_allowed(
    symbol: str,
    buy1_anchor: dict | None,
    execution_price: float | None,
    signals_dict: dict | None = None,
    freq: str | None = None,
) -> bool:
    """Research-only gate for second-buy opens; defaults to allowing all symbols.

    A45 P6 adds ``second_buy_mode``:
    - ``"off"`` blocks all new second-buy opens (existing positions still exit).
    - ``"gated"`` requires P4 MACD divergence, P5 resonance and ATR expansion.
    - ``"baseline"`` keeps the legacy behavior.
    """
    mode = STRATEGY_CONFIG.get("second_buy_mode", "baseline")

    if mode == "off":
        return False

    if mode == "gated":
        if signals_dict is None or freq is None:
            return False

        # P4 MACD divergence signal (amplitude or macd model depending on config).
        div_key = f"{freq}_D1BI_背驰V260615"
        div_val = signals_dict.get(div_key, "")
        if not (div_val.startswith("疑似") or div_val.startswith("确认")):
            return False

        # P5 resonance filter (actual resonance, never the legacy daily filter fallback).
        if not _resonance_holds(signals_dict, direction="long", force_resonance=True):
            return False

        # ATR expansion (not in chop).
        atr_key = f"{freq}_ATR_波动V260615"
        atr_val = signals_dict.get(atr_key, "")
        if not atr_val.startswith("扩张"):
            return False

    # Legacy baseline checks.
    enabled = STRATEGY_CONFIG.get("enable_2buy_symbols")
    if enabled is not None:
        enabled_keys = {_research_symbol_key(x) for x in enabled}
        if _research_symbol_key(symbol) not in enabled_keys:
            return False

    max_entry = STRATEGY_CONFIG.get("max_2buy_entry_vs_anchor_pct")
    if max_entry is not None and buy1_anchor and buy1_anchor.get("price") and execution_price:
        entry_vs_anchor = execution_price / buy1_anchor["price"] - 1
        if entry_vs_anchor > max_entry + 1e-12:
            return False

    return True


def _research_first_buy_allowed(symbol: str, signals_dict: dict) -> bool:
    """Research-only gate for first-buy opens; defaults to allowing all symbols."""
    enabled = STRATEGY_CONFIG.get("enable_1buy_symbols")
    if enabled is not None:
        enabled_keys = {_research_symbol_key(x) for x in enabled}
        if _research_symbol_key(symbol) not in enabled_keys:
            return False

    daily_direction = signals_dict.get("日线_D1BI_方向V260615", "")
    daily_position = signals_dict.get("日线_D1ZS_位置V260615", "")

    if STRATEGY_CONFIG.get("block_1buy_daily_down") and daily_direction.startswith("向下"):
        return False
    if STRATEGY_CONFIG.get("block_1buy_daily_not_up") and not daily_direction.startswith("向上"):
        return False
    if STRATEGY_CONFIG.get("block_1buy_daily_below_zs") and daily_position.startswith("中枢下方"):
        return False
    return True


def _research_short_open_allowed(
    symbol: str,
    signals_dict: dict,
    freq: str,
) -> bool:
    """Research-only gate for short opens; enforces P4/P5 symmetry.

    Short opens require:
    - P4 MACD 顶背驰 (or amplitude divergence when divergence_model="amplitude"),
      encoded as the ``{freq}_D1BI_背驰V260615`` signal not being "无".
    - P5 short-side resonance: daily (and 4H when configured) direction=向下
      and position in {中枢下方, 中枢内}.

    This gate is applied symmetrically to all short sub-strategies so that the
    short side uses the same P4/P5 rigor already shipped for the long side in
    A43/A44.
    """
    if signals_dict is None or freq is None:
        return False

    # P4 MACD/top divergence signal (amplitude or macd model depending on config).
    div_key = f"{freq}_D1BI_背驰V260615"
    div_val = signals_dict.get(div_key, "")
    if not (div_val.startswith("疑似") or div_val.startswith("确认")):
        return False

    # P5 short-side resonance filter (actual resonance, not legacy daily fallback).
    if not _resonance_holds(signals_dict, direction="short", force_resonance=True):
        return False

    return True


def _build_exit_events(
    name: str,
    operate: str,
    legacy_signals_any: list[str],
    directional_factors: list[dict],
    restructured_structural_signal_key: str,
    restructured_extra_signals_any: list[str] | None = None,
) -> list[Event]:
    """Build exit event(s) according to STRATEGY_CONFIG['exit_event_semantics'].

    ``legacy`` emits a single event gated by ``legacy_signals_any`` AND one of
    the directional factors (current Phase 1 behavior). ``restructured`` emits
    two independent events: a standalone structural exit and a standalone
    directional exit.

    When ``exit_model`` is ``"structural_atr"``, a partial-take-profit event is
    additionally emitted from the directional factors.  Position.update splits
    full-close exits from partial-tp events so that profit-side scaling only
    occurs when the center-boundary / measured-target conditions are met.
    """
    semantics = STRATEGY_CONFIG.get("exit_event_semantics", "legacy")
    exit_model = STRATEGY_CONFIG.get("exit_model", "legacy")
    events: list[Event] = []

    if semantics == "legacy":
        events.append(Event.load({
            "name": name,
            "operate": operate,
            "signals_all": [],
            "signals_any": legacy_signals_any,
            "signals_not": [],
            "factors": directional_factors,
        }))
    else:
        # restructured: standalone structural exit + standalone directional exit
        structural_signals_any = [
            f"{restructured_structural_signal_key}_结构失效_任意_任意_0",
        ]
        if restructured_extra_signals_any:
            structural_signals_any.extend(restructured_extra_signals_any)
        structural_event = Event.load({
            "name": f"{name}-结构",
            "operate": operate,
            "signals_all": [],
            "signals_any": structural_signals_any,
            "signals_not": [],
            "factors": [],
        })
        structural_event.is_structural = True
        events.append(structural_event)

        directional_event = Event.load({
            "name": f"{name}-方向",
            "operate": operate,
            "signals_all": [],
            "signals_any": [],
            "signals_not": [],
            "factors": directional_factors,
        })
        events.append(directional_event)

    if exit_model == "structural_atr":
        # partial TP triggers on directional factors alone (the "target").
        partial_tp_event = Event.load({
            "name": f"{name}-部分止盈",
            "operate": operate,
            "signals_all": [],
            "signals_any": [],
            "signals_not": [],
            "factors": directional_factors,
        })
        partial_tp_event.is_partial_tp = True
        events.append(partial_tp_event)

    return events


class Position:
    """
    持仓子策略

    【仓位模式说明】
    当前为"信号研究模式"：
    - pos 只表示方向: 1=持有多头, -1=持有空头, 0=空仓
    - volume 恒为 1 手（不计算实际手数）
    - 盈亏以百分比(pnl_pct)记录，不涉及合约乘数或资金管理
    - 实际资金加权在 BacktestEngine 的权益曲线中完成（事后加权）

    这种设计适用于:
    - 信号验证阶段：验证买卖点信号是否有效
    - 策略研究阶段：评估策略的方向判断能力
    - 参数优化阶段：快速迭代无需精确资金建模

    如需升级为"资金管理模式"（实盘/仿真前）：
    - 需添加 capital_per_unit、contract_multiplier 参数
    - volume 应基于 capital * weight / (price * multiplier) 动态计算
    - 需实现资金上限检查和复利再投资逻辑

    支持移动止损（trailing stop）机制
    """

    def __init__(
        self,
        name: str,
        symbol: str,
        opens: List[Event],
        exits: List[Event] = None,
        interval: int = 0,
        timeout: int = 1000,
        stop_loss: int = 1000,
        trailing_start: int = 150,           # 启动移动止损的盈利阈值(BP) 1.5%
        trailing_drawback_pct: float = 0.4,  # 移动止损回撤容忍比例(40%=从最高回撤40%平仓)
        T0: bool = False,
        commission_rate: float | None = None,     # 手续费率(万一)
        slippage: float | None = None,            # 滑点(0.05%)
    ):
        self.name = name
        self.symbol = symbol
        self.opens = opens
        all_exit_events = exits or []
        self.exits = [e for e in all_exit_events if not e.is_partial_tp]
        self.partial_tp_events = [e for e in all_exit_events if e.is_partial_tp]
        self.interval = interval  # 同类开仓间隔（秒）
        # timeout 按交易周期 bar 计数；当前交易周期为 30 分钟
        self.timeout = timeout    # 超时K线数（交易周期级别，如 600 根 30 分钟 K 线 ≈ 12.5 个交易日）
        self.stop_loss = stop_loss  # 止损BP (1BP=0.01%)
        self.trailing_start = trailing_start  # 移动止损启动阈值(BP)
        self.trailing_drawback_pct = trailing_drawback_pct  # 移动止损回撤容忍比例
        self.T0 = T0
        self.commission_rate = commission_rate if commission_rate is not None else BACKTEST_CONFIG["commission_rate"]
        self.slippage = slippage if slippage is not None else BACKTEST_CONFIG["slippage"]

        # 运行状态
        self.pos = 0  # 当前仓位
        self.cost = 0.0  # 持仓成本
        self.volume = 1  # 持仓手数（A40; research=1, risk= sized lots）
        self.contract_multiplier = 1  # 合约乘数（A40; research=1, risk=from spec）
        self.bars_since_open = 0  # 开仓后经过的K线数
        self.last_open_dt = None  # 最后开仓时间
        self.trades: List[TradeRecord] = []  # 交易记录
        self.pairs: List[dict] = []  # 配对交易
        self.opens_allowed: bool = True  # A46: regime router can suppress new opens

        # A40 sizing skip counters
        self.size_zero_skip = 0
        self.margin_cap_skip = 0

        # 移动止损状态
        self.max_profit_bp = 0  # 持仓期间最大盈利(BP)
        self.trailing_active = False  # 移动止损是否激活

        # A47 structural_atr exit-model state
        self._peak_price: float = 0.0  # 最有利价格（多=最高，空=最低）
        self._partial_tp_done: bool = False  # 是否已执行部分止盈

        # A51 limit-up/down/halt tagging state (tagging only, no fill-path changes)
        self._pending_entry_at_limit: bool = False  # entry bar limit flag for the open position
        self._pending_exit_at_limit: bool = False  # exit bar limit flag for the current bar

        # A67 enforce-mode rejection audit trail (set when a fill is skipped this bar)
        self._pending_fill_rejected_at_limit: bool = False

    def _reject_fill_at_limit(
        self,
        flag: bool | tuple[bool, bool] | None,
        side: int,
        is_entry: bool,
    ) -> bool:
        """Return True if this fill should be skipped under ``limit_halt_model='enforce'``.

        When the fill is blocked, the rejection is recorded on the position so the
        eventual closed pair can carry an audit trail.  ``off`` and ``aware`` never
        block fills through this helper.
        """
        if STRATEGY_CONFIG.get("limit_halt_model", "off") != "enforce":
            return False
        blocked = _resolve_limit_flag(flag, side, is_entry)
        if blocked:
            self._pending_fill_rejected_at_limit = True
        return blocked

    def update(self, signals_dict: dict, price: float, dt: datetime,
               bar_count: int = 1, execution_price: float = None,
               bar_high: float = None, bar_low: float = None,
               equity_at_entry: float | None = None,
               total_open_margin: float | None = None,
               atr: float | None = None,
               entry_at_limit: bool | None = None,
               exit_at_limit: bool | None = None):
        """
        根据当前信号更新持仓状态

        :param signals_dict: 当前信号字典
        :param price: 当前价格（用于风控检查和未实现盈亏）
        :param dt: 当前时间
        :param bar_count: K线计数增量
        :param execution_price: 信号驱动交易的成交价（延迟成交时为下一根开盘价）
                                如果为None，则使用price作为成交价（向后兼容）
        :param bar_high: 当根bar最高价（仅 stop_execution_model="intrabar" 时用于触价止损）
        :param bar_low: 当根bar最低价（仅 stop_execution_model="intrabar" 时用于触价止损）
                        为 None 时（旧调用方/close模型）固定止损回退到收盘价检查，保持基线一致
        :param equity_at_entry: A40 risk-mode equity basis for lot sizing
        :param total_open_margin: A40 risk-mode pre-open margin across all positions
        :param atr: A47 current ATR value for the structural_atr trailing stop.
                    Ignored when exit_model is ``"legacy"``.
        :param entry_at_limit: A51 flag: ``(touched_upper, touched_lower)`` for the
                               execution bar, or a legacy plain bool.
        :param exit_at_limit: A51 flag: ``(touched_upper, touched_lower)`` for the
                              current bar, or a legacy plain bool.
        """
        self._pending_exit_at_limit = _resolve_limit_flag(exit_at_limit, self.pos, is_entry=False)
        trade_price = execution_price if execution_price is not None else price
        operate, event_name = self._get_operate(signals_dict, price, dt)

        # A67: gate entries and exits when the fill direction is unexecutable at the limit band.
        if operate == Operate.LO and self.pos == 0:
            if not self._reject_fill_at_limit(entry_at_limit, 1, is_entry=True):
                self._open_long(trade_price, dt, event_name, equity_at_entry, total_open_margin, entry_at_limit)
        elif operate == Operate.LC and self.pos > 0:
            if not self._reject_fill_at_limit(exit_at_limit, self.pos, is_entry=False):
                self._close_long(trade_price, dt, f"信号平仓-{event_name}" if event_name else "信号平仓")
        elif operate == Operate.SO and self.pos == 0:
            if not self._reject_fill_at_limit(entry_at_limit, -1, is_entry=True):
                self._open_short(trade_price, dt, event_name, equity_at_entry, total_open_margin, entry_at_limit)
        elif operate == Operate.SC and self.pos < 0:
            if not self._reject_fill_at_limit(exit_at_limit, self.pos, is_entry=False):
                self._close_short(trade_price, dt, f"信号平仓-{event_name}" if event_name else "信号平仓")

        # 更新K线计数和移动止损
        if self.pos != 0:
            self.bars_since_open += bar_count

            # 更新最大盈利追踪（用实际价格，非成交价）
            self._update_trailing(price)

            exit_model = STRATEGY_CONFIG.get("exit_model", "legacy")
            if exit_model == "legacy":
                # 历史基线路径：百分比回撤移动止损 > 固定止损 > 超时
                # 信号平仓已在上面处理，保持最高优先级。
                if self._check_trailing_stop(price):
                    if not self._reject_fill_at_limit(exit_at_limit, self.pos, is_entry=False):
                        if self.pos > 0:  # pragma: no branch - pos direction is mutually exclusive after trigger
                            self._close_long(price, dt, "移动止损")
                        elif self.pos < 0:  # pragma: no branch - complementary side of the triggered position
                            self._close_short(price, dt, "移动止损")
                # 检查固定止损 - close 模型用收盘价，intrabar 模型用当根 low/high 触价
                elif self._stop_triggered(price, bar_high, bar_low):
                    stop_fill = self._stop_fill(price, bar_high, bar_low)
                    if not self._reject_fill_at_limit(exit_at_limit, self.pos, is_entry=False):
                        if self.pos > 0:  # pragma: no branch - pos direction is mutually exclusive after trigger
                            self._close_long(stop_fill, dt, "止损")
                        elif self.pos < 0:  # pragma: no branch - complementary side of the triggered position
                            self._close_short(stop_fill, dt, "止损")
                # 检查超时 - 风控立即执行
                elif self.bars_since_open >= self.timeout:
                    if not self._reject_fill_at_limit(exit_at_limit, self.pos, is_entry=False):
                        if self.pos > 0:  # pragma: no branch - pos direction is mutually exclusive after trigger
                            self._close_long(price, dt, "超时")
                        elif self.pos < 0:  # pragma: no branch - complementary side of the triggered position
                            self._close_short(price, dt, "超时")
            else:
                # A47 structural_atr: 结构止损/信号平仓已在上面处理；
                # 风险侧：固定止损 > 超时；盈利侧：部分止盈 > ATR trailing。
                if self._stop_triggered(price, bar_high, bar_low):
                    stop_fill = self._stop_fill(price, bar_high, bar_low)
                    if not self._reject_fill_at_limit(exit_at_limit, self.pos, is_entry=False):
                        if self.pos > 0:  # pragma: no branch
                            self._close_long(stop_fill, dt, "止损")
                        elif self.pos < 0:  # pragma: no branch
                            self._close_short(stop_fill, dt, "止损")
                elif self.bars_since_open >= self.timeout:
                    if not self._reject_fill_at_limit(exit_at_limit, self.pos, is_entry=False):
                        if self.pos > 0:  # pragma: no branch
                            self._close_long(price, dt, "超时")
                        elif self.pos < 0:  # pragma: no branch
                            self._close_short(price, dt, "超时")
                elif not self._partial_tp_done:
                    partial_event = self._get_partial_tp_event(signals_dict)
                    if partial_event:
                        self._scale_out(price, dt, f"部分止盈-{partial_event.name}")
                elif self._check_atr_trailing_stop(price, atr):
                    if not self._reject_fill_at_limit(exit_at_limit, self.pos, is_entry=False):
                        if self.pos > 0:  # pragma: no branch
                            self._close_long(price, dt, "ATR移动止损")
                        elif self.pos < 0:  # pragma: no branch
                            self._close_short(price, dt, "ATR移动止损")

    def _get_operate(self, signals_dict: dict, price: float, dt: datetime) -> Tuple[Optional[Operate], str]:
        """获取当前应执行的操作"""
        # 先检查平仓事件（优先级高）
        if self.pos != 0:
            for event in self.exits:
                if event.is_match(signals_dict):
                    if self.pos > 0:
                        return Operate.LC, event.name  # 返回操作和事件名
                    elif self.pos < 0:  # pragma: no branch - position sign is fixed entering this block
                        return Operate.SC, event.name

        # 再检查开仓事件
        if self.pos == 0:
            # A46: regime router can suppress new opens while still allowing exits.
            if not self.opens_allowed:
                return None, ""

            # 检查开仓间隔
            if self.last_open_dt and self.interval > 0:
                elapsed = (dt - self.last_open_dt).total_seconds()
                if elapsed < self.interval:
                    return None, ""

            for event in self.opens:
                if event.is_match(signals_dict):
                    return event.operate, event.name

        return None, ""

    def _update_trailing(self, price: float):
        """更新移动止损追踪"""
        if self.cost == 0:
            return
        if self.pos > 0:
            profit_bp = (price - self.cost) / self.cost * 10000
            if price > self._peak_price:
                self._peak_price = price
        elif self.pos < 0:
            profit_bp = (self.cost - price) / self.cost * 10000
            if price < self._peak_price or self._peak_price == 0:
                self._peak_price = price
        else:
            return

        if profit_bp > self.max_profit_bp:
            self.max_profit_bp = profit_bp

        # 激活移动止损
        if self.max_profit_bp >= self.trailing_start:
            self.trailing_active = True

    def _check_trailing_stop(self, price: float) -> bool:
        """检查是否触发移动止损（百分比回撤）"""
        if not self.trailing_active or self.cost == 0:
            return False

        if self.pos > 0:
            profit_bp = (price - self.cost) / self.cost * 10000
        elif self.pos < 0:
            profit_bp = (self.cost - price) / self.cost * 10000
        else:
            return False

        # 从最高盈利回撤超过 max_profit * drawback_pct 则触发
        # 例如: 最高盈利300BP, 回撤容忍40%, 则回撤120BP即平仓
        drawback = self.max_profit_bp - profit_bp
        tolerance = self.max_profit_bp * self.trailing_drawback_pct
        return drawback >= tolerance

    def _get_partial_tp_event(self, signals_dict: dict) -> Event | None:
        """Return the first matching partial-take-profit event, if any."""
        for event in self.partial_tp_events:
            if event.is_match(signals_dict):
                return event
        return None

    def _check_atr_trailing_stop(self, price: float, atr: float | None) -> bool:
        """检查是否触发 ATR 移动止损（structural_atr 模式）。"""
        if atr is None or atr <= 0 or self.cost == 0 or self.pos == 0:
            return False
        mult = STRATEGY_CONFIG.get("atr_trail_mult", 3.0)
        if self.pos > 0:
            trail = self._peak_price - mult * atr
            return price <= trail
        else:
            trail = self._peak_price + mult * atr
            return price >= trail

    def _check_stop_loss(self, price: float) -> bool:
        """检查是否触发固定止损"""
        if self.cost == 0:
            return False
        if self.pos > 0:
            loss_bp = (self.cost - price) / self.cost * 10000
            return loss_bp >= self.stop_loss
        elif self.pos < 0:
            loss_bp = (price - self.cost) / self.cost * 10000
            return loss_bp >= self.stop_loss
        return False

    def _stop_triggered(self, price: float, bar_high: float = None,
                        bar_low: float = None) -> bool:
        """固定止损是否触发。

        - close 模型（默认）：完全委托给 ``_check_stop_loss(price)``，与历史基线字节一致。
        - intrabar 模型：多头看当根 bar_low 是否触及止损位，空头看 bar_high。
          当 intrabar 被请求但缺少对应 bar 极值（旧调用方）时，安全回退到收盘价检查。
        """
        if STRATEGY_CONFIG.get("stop_execution_model", "close") == "intrabar" and self.cost != 0:
            if self.pos > 0 and bar_low is not None:
                return bar_low <= self.cost * (1 - self.stop_loss / 10000)
            if self.pos < 0 and bar_high is not None:
                return bar_high >= self.cost * (1 + self.stop_loss / 10000)
        return self._check_stop_loss(price)

    def _stop_fill(self, price: float, bar_high: float = None,
                   bar_low: float = None) -> float:
        """固定止损成交价。

        - close 模型（默认）或缺少 bar 极值：成交价 = price（收盘价），与基线一致。
        - intrabar 模型：多头 = min(触发位, 收盘价)，空头 = max(触发位, 收盘价)，
          再叠加 ``stop_penalty_bp`` 不利滑点。跳空穿透时 fill 退化为更差的收盘价。
        """
        if STRATEGY_CONFIG.get("stop_execution_model", "close") != "intrabar" or self.cost == 0:
            return price
        penalty = STRATEGY_CONFIG.get("stop_penalty_bp", 0) / 10000
        if self.pos > 0 and bar_low is not None:
            trigger = self.cost * (1 - self.stop_loss / 10000)
            return min(trigger, price) * (1 - penalty)
        if self.pos < 0 and bar_high is not None:
            trigger = self.cost * (1 + self.stop_loss / 10000)
            return max(trigger, price) * (1 + penalty)
        return price

    def _scale_out(self, price: float, dt: datetime, reason: str):
        """Scale out ``partial_tp_frac`` of the current position.

        Records a partial pair, reduces ``self.volume``, and keeps the remainder
        open for the ATR trailing stop.  Transaction costs are scaled by the
        same fraction so total costs remain consistent when the remainder is
        later closed.
        """
        if self.pos == 0 or self.cost == 0 or self.volume <= 0:
            return

        partial_tp_frac = STRATEGY_CONFIG.get("partial_tp_frac", 0.5)
        if partial_tp_frac <= 0 or partial_tp_frac >= 1:
            return

        scale_volume = self.volume * partial_tp_frac
        if STRATEGY_CONFIG.get("sizing_model", "research") == "risk":
            scale_volume = int(floor(scale_volume))
            if scale_volume < 1 or scale_volume >= self.volume:
                # Lot flooring made a real partial scale-out impossible this
                # lifecycle.  Treat it as "already resolved" so the subsequent
                # ATR trailing-stop branch in Position.update remains reachable.
                self._partial_tp_done = True
                return

        if self.pos > 0:
            gross_pnl = (price - self.cost) / self.cost
        else:
            gross_pnl = (self.cost - price) / self.cost

        full_transaction_cost = 2 * self.commission_rate + self.slippage
        # Use the undivided per-unit round-trip cost rate, matching _close_long/
        # _close_short.  The * scale_volume term in pnl_currency already scales
        # the cost to the portion actually closed (A55 fix).
        transaction_cost = full_transaction_cost
        pnl = gross_pnl - transaction_cost
        pnl_currency = (
            gross_pnl * self.cost * scale_volume * self.contract_multiplier
            - transaction_cost * self.cost * scale_volume * self.contract_multiplier
        )

        pair: dict = {
            "open_dt": self.last_open_dt,
            "close_dt": dt,
            "open_price": self.cost,
            "close_price": price,
            "pnl_pct": pnl,
            "pnl_currency": pnl_currency,
            "volume": scale_volume,
            "contract_multiplier": self.contract_multiplier,
            "bars_held": self.bars_since_open,
            "reason": reason,
            "reason_code": normalize_exit_reason(reason),
            "is_partial_tp": True,
        }
        limit_halt_model = STRATEGY_CONFIG.get("limit_halt_model", "off")
        if limit_halt_model in ("aware", "enforce"):
            pair["is_entry_at_limit"] = self._pending_entry_at_limit
            pair["is_exit_at_limit"] = self._pending_exit_at_limit
        if limit_halt_model == "enforce":
            pair["fill_rejected_at_limit"] = self._pending_fill_rejected_at_limit
        self.pairs.append(pair)
        self.trades.append(TradeRecord(dt=dt, operate=Operate.LC if self.pos > 0 else Operate.SC,
                                       price=price, volume=scale_volume, reason=reason))
        self.volume -= scale_volume
        self._partial_tp_done = True

    def _open_long(self, price: float, dt: datetime, reason: str = "开多",
                   equity_at_entry: float | None = None,
                   total_open_margin: float | None = None,
                   entry_at_limit: bool | None = None):
        if STRATEGY_CONFIG.get("sizing_model", "research") == "risk":
            self.volume, self.contract_multiplier = self._size_open(
                price, equity_at_entry, total_open_margin
            )
            if self.volume < 1:
                return
        else:
            self.volume = 1
            self.contract_multiplier = 1

        self.pos = 1
        self.cost = price
        self.bars_since_open = 0
        self.last_open_dt = dt
        self.max_profit_bp = 0
        self.trailing_active = False
        self._peak_price = price
        self._partial_tp_done = False
        self._pending_entry_at_limit = _resolve_limit_flag(entry_at_limit, 1, is_entry=True)
        self.trades.append(TradeRecord(dt=dt, operate=Operate.LO, price=price, volume=self.volume, reason=reason))

    def _size_open(self, price: float, equity_at_entry: float | None,
                   total_open_margin: float | None) -> Tuple[int, int]:
        """Compute integer-lot size under A40 risk-mode sizing model.

        Returns (volume, contract_multiplier).  volume < 1 means the open should be skipped.
        """
        spec = _research_contract_spec(self.symbol)
        multiplier = int(spec.get("multiplier", 1))
        margin_rate = float(spec.get("margin_rate", 0.0))

        equity_mode = STRATEGY_CONFIG.get("equity_mode", "fixed")
        if equity_mode == "compound":
            raise NotImplementedError(
                'equity_mode="compound" is documented but not yet implemented'
            )

        equity = equity_at_entry if equity_at_entry is not None else 0.0
        risk_pct = STRATEGY_CONFIG.get("risk_per_trade_pct", 0.005)
        max_margin_pct = STRATEGY_CONFIG.get("max_margin_pct", 0.50)

        stop_distance = price * self.stop_loss / 10000
        if stop_distance <= 0 or equity <= 0 or multiplier <= 0:
            return 0, multiplier

        risk_amount = equity * risk_pct
        raw_volume = risk_amount / (stop_distance * multiplier)
        volume = int(floor(raw_volume))
        if volume < 1:
            self.size_zero_skip += 1
            return 0, multiplier

        # Margin cap: reduce to the largest lot count that fits, or skip.
        pre_open_margin = total_open_margin if total_open_margin is not None else 0.0
        margin_cap = equity * max_margin_pct
        required_margin_for_one = price * multiplier * margin_rate
        if required_margin_for_one <= 0:
            return volume, multiplier

        if pre_open_margin + volume * required_margin_for_one > margin_cap:
            max_fit = int(floor((margin_cap - pre_open_margin) / required_margin_for_one))
            if max_fit >= 1:
                volume = max_fit
            else:
                self.margin_cap_skip += 1
                return 0, multiplier

        return volume, multiplier

    def _close_long(self, price: float, dt: datetime, reason: str = ""):
        gross_pnl = (price - self.cost) / self.cost
        transaction_cost = 2 * self.commission_rate + self.slippage  # 开平两次手续费 + 滑点
        pnl = gross_pnl - transaction_cost
        pnl_currency = (
            (price - self.cost) * self.volume * self.contract_multiplier
            - transaction_cost * self.cost * self.volume * self.contract_multiplier
        )
        pair: dict = {
            "open_dt": self.last_open_dt,
            "close_dt": dt,
            "open_price": self.cost,
            "close_price": price,
            "pnl_pct": pnl,
            "pnl_currency": pnl_currency,
            "volume": self.volume,
            "contract_multiplier": self.contract_multiplier,
            "bars_held": self.bars_since_open,
            "reason": reason,
            "reason_code": normalize_exit_reason(reason),
        }
        limit_halt_model = STRATEGY_CONFIG.get("limit_halt_model", "off")
        if limit_halt_model in ("aware", "enforce"):
            pair["is_entry_at_limit"] = self._pending_entry_at_limit
            pair["is_exit_at_limit"] = self._pending_exit_at_limit
        if limit_halt_model == "enforce":
            pair["fill_rejected_at_limit"] = self._pending_fill_rejected_at_limit
        self.pairs.append(pair)
        # Append the closing trade record BEFORE resetting state so the logged
        # volume reflects the actual closed lots instead of the default 1
        # (A55 bundled audit-log fix).
        self.trades.append(TradeRecord(dt=dt, operate=Operate.LC, price=price, volume=self.volume, reason=reason))
        self.pos = 0
        self.cost = 0
        self.volume = 1
        self.contract_multiplier = 1
        self.bars_since_open = 0
        self.max_profit_bp = 0
        self.trailing_active = False
        self._peak_price = 0.0
        self._partial_tp_done = False
        self._pending_entry_at_limit = False
        self._pending_exit_at_limit = False
        self._pending_fill_rejected_at_limit = False

    def _open_short(self, price: float, dt: datetime, reason: str = "开空",
                    equity_at_entry: float | None = None,
                    total_open_margin: float | None = None,
                    entry_at_limit: bool | None = None):
        if STRATEGY_CONFIG.get("sizing_model", "research") == "risk":
            self.volume, self.contract_multiplier = self._size_open(
                price, equity_at_entry, total_open_margin
            )
            if self.volume < 1:
                return
        else:
            self.volume = 1
            self.contract_multiplier = 1

        self.pos = -1
        self.cost = price
        self.bars_since_open = 0
        self.last_open_dt = dt
        self.max_profit_bp = 0
        self.trailing_active = False
        self._peak_price = price
        self._partial_tp_done = False
        self._pending_entry_at_limit = _resolve_limit_flag(entry_at_limit, -1, is_entry=True)
        self.trades.append(TradeRecord(dt=dt, operate=Operate.SO, price=price, volume=self.volume, reason=reason))

    def _close_short(self, price: float, dt: datetime, reason: str = ""):
        gross_pnl = (self.cost - price) / self.cost
        transaction_cost = 2 * self.commission_rate + self.slippage
        pnl = gross_pnl - transaction_cost
        pnl_currency = (
            (self.cost - price) * self.volume * self.contract_multiplier
            - transaction_cost * self.cost * self.volume * self.contract_multiplier
        )
        pair: dict = {
            "open_dt": self.last_open_dt,
            "close_dt": dt,
            "open_price": self.cost,
            "close_price": price,
            "pnl_pct": pnl,
            "pnl_currency": pnl_currency,
            "volume": self.volume,
            "contract_multiplier": self.contract_multiplier,
            "bars_held": self.bars_since_open,
            "reason": reason,
            "reason_code": normalize_exit_reason(reason),
        }
        limit_halt_model = STRATEGY_CONFIG.get("limit_halt_model", "off")
        if limit_halt_model in ("aware", "enforce"):
            pair["is_entry_at_limit"] = self._pending_entry_at_limit
            pair["is_exit_at_limit"] = self._pending_exit_at_limit
        if limit_halt_model == "enforce":
            pair["fill_rejected_at_limit"] = self._pending_fill_rejected_at_limit
        self.pairs.append(pair)
        # Append the closing trade record BEFORE resetting state so the logged
        # volume reflects the actual closed lots instead of the default 1
        # (A55 bundled audit-log fix).
        self.trades.append(TradeRecord(dt=dt, operate=Operate.SC, price=price, volume=self.volume, reason=reason))
        self.pos = 0
        self.cost = 0
        self.volume = 1
        self.contract_multiplier = 1
        self.bars_since_open = 0
        self.max_profit_bp = 0
        self.trailing_active = False
        self._peak_price = 0.0
        self._partial_tp_done = False
        self._pending_entry_at_limit = False
        self._pending_exit_at_limit = False
        self._pending_fill_rejected_at_limit = False

    def evaluate(self) -> dict:
        """评估策略绩效"""
        if not self.pairs:
            return {"total_trades": 0, "win_rate": 0, "profit_factor": 0}

        wins = [p for p in self.pairs if p["pnl_pct"] > 0]
        losses = [p for p in self.pairs if p["pnl_pct"] <= 0]

        total_profit = sum(p["pnl_pct"] for p in wins) if wins else 0
        total_loss = abs(sum(p["pnl_pct"] for p in losses)) if losses else 0

        return {
            "total_trades": len(self.pairs),
            "win_count": len(wins),
            "loss_count": len(losses),
            "win_rate": len(wins) / len(self.pairs) if self.pairs else 0,
            "avg_profit": total_profit / len(wins) if wins else 0,
            "avg_loss": total_loss / len(losses) if losses else 0,
            "profit_factor": total_profit / total_loss if total_loss > 0 else float('inf'),
            "max_pnl": max(p["pnl_pct"] for p in self.pairs),
            "min_pnl": min(p["pnl_pct"] for p in self.pairs),
            "avg_bars_held": sum(p["bars_held"] for p in self.pairs) / len(self.pairs),
        }


# ========== 持仓子策略创建函数 ==========

def create_first_buy_position(symbol: str, freq: str = "30分钟",
                              commission_rate: float | None = None,
                              slippage: float | None = None,
                              enable_daily_filter: bool = True) -> Position:
    """
    一买多头持仓子策略

    定位: 左侧试仓
    特点: 小仓位、较紧止损、较短超时

    :param commission_rate: 手续费率（由外部传入，统一使用config值）
    :param slippage: 滑点（由外部传入，统一使用config值）
    :param enable_daily_filter: 是否启用日线趋势过滤（默认 True）
    """
    daily_filter = (
        _higher_level_filter_signals(direction="long", strict=False)
        if enable_daily_filter else {"signals_all": [], "signals_not": []}
    )
    opens = [
        Event.load({
            "name": "一买确认开多",
            "operate": "开多",
            "signals_all": [
                f"{freq}_D1ZS_数据状态V260615_充分_任意_任意_0",
                f"{freq}_D1ZS_结构状态V260615_已确认_任意_任意_0",
                *daily_filter.get("signals_all", []),
                *_atr_filter_signals(freq)["signals_all"],
            ],
            "signals_any": [],
            "signals_not": [
                *daily_filter.get("signals_not", []),
            ],
            "factors": [{
                "name": "一买底背驰确认",
                "signals_all": [
                    f"{freq}_D1BSP_一买V260615_一买确认_任意_任意_0",
                    f"{freq}_D1BI_方向V260615_向上_任意_任意_0",
                ],
                "signals_any": [],
                "signals_not": [],
            }],
        }),
    ]

    exits = _build_exit_events(
        name="一买平多",
        operate="平多",
        legacy_signals_any=[
            f"{freq}_D1BSP_风控V260615_结构失效_任意_任意_0",
            f"{freq}_D1BSP_风控V260615_震荡超限_任意_任意_0",
        ],
        directional_factors=[{
            "name": "方向反转平仓",
            "signals_all": [
                f"{freq}_D1BI_方向V260615_向下_任意_任意_0",
            ],
            "signals_any": [
                f"{freq}_D1ZS_位置V260615_中枢下方_任意_任意_0",
                f"{freq}_D1ZS_位置V260615_中枢内_任意_任意_0",
            ],
            "signals_not": [],
        }],
        restructured_structural_signal_key=f"{freq}_D1BSP_风控RV260615",
        restructured_extra_signals_any=[
            f"{freq}_D1BSP_风控V260615_震荡超限_任意_任意_0",
        ],
    )

    trailing_start, trailing_drawback = _research_trailing_params(symbol)

    return Position(
        name="一买多头",
        symbol=symbol,
        opens=opens,
        exits=exits,
        interval=STRATEGY_CONFIG.get("interval_1buy", 3600 * 24),
        timeout=STRATEGY_CONFIG.get("timeout_1buy", 600),
        stop_loss=STRATEGY_CONFIG.get("stop_loss_1buy", 200),
        trailing_start=trailing_start,
        trailing_drawback_pct=trailing_drawback,
        T0=STRATEGY_CONFIG.get("T0", False),
        commission_rate=commission_rate,
        slippage=slippage,
    )


def create_second_buy_position(symbol: str, freq: str = "30分钟",
                               commission_rate: float | None = None,
                               slippage: float | None = None,
                               enable_daily_filter: bool = True) -> Position:
    """
    二买多头持仓子策略

    定位: 回抽确认
    特点: 以一买低点为结构失效位

    优化要点:
    1. 排除中枢下方开多（趋势过滤）
    2. 二买本身由一买锚点与回抽不破低确认，不额外要求当前背驰
    3. 加大开仓间隔减少过度交易
    4. 收紧止损提高盈亏比

    :param commission_rate: 手续费率（由外部传入，统一使用config值）
    :param slippage: 滑点（由外部传入，统一使用config值）
    :param enable_daily_filter: 是否启用日线趋势过滤（默认 True）
    """
    daily_filter = (
        _higher_level_filter_signals(direction="long", strict=True)
        if enable_daily_filter else {"signals_all": [], "signals_not": []}
    )
    opens = [
        Event.load({
            "name": "二买确认开多",
            "operate": "开多",
            "signals_all": [
                f"{freq}_D1ZS_数据状态V260615_充分_任意_任意_0",
                f"{freq}_D1ZS_结构状态V260615_已确认_任意_任意_0",
                *daily_filter.get("signals_all", []),
                *_atr_filter_signals(freq)["signals_all"],
            ],
            "signals_any": [
                # 必须在中枢上方或中枢内（趋势配合方向）
                f"{freq}_D1ZS_位置V260615_中枢上方_任意_任意_0",
                f"{freq}_D1ZS_位置V260615_中枢内_任意_任意_0",
            ],
            "signals_not": [
                # 排除中枢下方开多
                f"{freq}_D1ZS_位置V260615_中枢下方_任意_任意_0",
                # 排除无中枢状态
                f"{freq}_D1ZS_位置V260615_无中枢_任意_任意_0",
                *daily_filter.get("signals_not", []),
            ],
            "factors": [{
                "name": "二买回抽确认",
                "signals_all": [
                    f"{freq}_D1BSP_二买V260615_二买确认_任意_任意_0",
                    f"{freq}_D1BI_方向V260615_向上_任意_任意_0",
                ],
                "signals_any": [],
                "signals_not": [],
            }],
        }),
    ]

    exits = _build_exit_events(
        name="二买平多",
        operate="平多",
        legacy_signals_any=[
            f"{freq}_D1BSP_风控V260615_结构失效_任意_任意_0",
        ],
        directional_factors=[{
            "name": "跌破一买低点",
            "signals_all": [
                f"{freq}_D1BI_方向V260615_向下_任意_任意_0",
                f"{freq}_D1ZS_位置V260615_中枢下方_任意_任意_0",
            ],
            "signals_any": [],
            "signals_not": [],
        }],
        restructured_structural_signal_key=f"{freq}_D1BSP_风控RV260615",
    )

    trailing_start, trailing_drawback = _research_trailing_params(symbol)

    return Position(
        name="二买多头",
        symbol=symbol,
        opens=opens,
        exits=exits,
        interval=STRATEGY_CONFIG.get("interval_2buy", 3600 * 24),
        timeout=STRATEGY_CONFIG.get("timeout_2buy", 1000),
        stop_loss=STRATEGY_CONFIG.get("stop_loss_2buy", 300),
        trailing_start=trailing_start,
        trailing_drawback_pct=trailing_drawback,
        T0=STRATEGY_CONFIG.get("T0", False),
        commission_rate=commission_rate,
        slippage=slippage,
    )


def create_third_buy_position(symbol: str, freq: str = "30分钟",
                              commission_rate: float | None = None,
                              slippage: float | None = None,
                              enable_daily_filter: bool = True) -> Position:
    """
    三买多头持仓子策略

    定位: 趋势跟随
    特点: 以中枢ZG或回抽低点为失效位

    优化要点:
    1. 放宽条件: "回抽不入中枢"阶段即可开仓（不需要等三买确认）
    2. 增加"离开中枢"+"向上"作为更宽松的触发条件
    3. 不要求同时满足位置信号（三买信号本身已隐含位置）

    :param commission_rate: 手续费率（由外部传入，统一使用config值）
    :param slippage: 滑点（由外部传入，统一使用config值）
    :param enable_daily_filter: 是否启用日线趋势过滤（默认 True）
    """
    daily_filter = (
        _higher_level_filter_signals(direction="long", strict=True)
        if enable_daily_filter else {"signals_all": [], "signals_not": []}
    )
    opens = [
        Event.load({
            "name": "三买确认开多",
            "operate": "开多",
            "signals_all": [
                f"{freq}_D1ZS_数据状态V260615_充分_任意_任意_0",
                f"{freq}_D1ZS_结构状态V260615_已确认_任意_任意_0",
                *daily_filter.get("signals_all", []),
                *_atr_filter_signals(freq)["signals_all"],
            ],
            "signals_any": [],
            "signals_not": [
                # 排除中枢下方
                f"{freq}_D1ZS_位置V260615_中枢下方_任意_任意_0",
                *daily_filter.get("signals_not", []),
            ],
            "factors": [{
                "name": "三买完整确认",
                "signals_all": [
                    f"{freq}_D1BSP_三买阶段V260615_三买确认_任意_任意_0",
                    f"{freq}_D1BI_方向V260615_向上_任意_任意_0",
                ],
                "signals_any": [],
                "signals_not": [],
            }],
        }),
    ]

    exits = _build_exit_events(
        name="三买平多",
        operate="平多",
        legacy_signals_any=[
            f"{freq}_D1BSP_风控V260615_结构失效_任意_任意_0",
        ],
        directional_factors=[{
            "name": "回落入中枢",
            "signals_all": [
                f"{freq}_D1ZS_位置V260615_中枢内_任意_任意_0",
                f"{freq}_D1BI_方向V260615_向下_任意_任意_0",
            ],
            "signals_any": [],
            "signals_not": [],
        }, {
            "name": "跌破中枢",
            "signals_all": [
                f"{freq}_D1ZS_位置V260615_中枢下方_任意_任意_0",
            ],
            "signals_any": [],
            "signals_not": [],
        }],
        restructured_structural_signal_key=f"{freq}_D1BSP_风控RV260615",
    )

    trailing_start, trailing_drawback = _research_trailing_params(symbol)

    return Position(
        name="三买多头",
        symbol=symbol,
        opens=opens,
        exits=exits,
        interval=STRATEGY_CONFIG.get("interval_3buy", 3600 * 24),
        timeout=STRATEGY_CONFIG.get("timeout_3buy", 1500),
        stop_loss=STRATEGY_CONFIG.get("stop_loss_3buy", 350),
        trailing_start=trailing_start,
        trailing_drawback_pct=trailing_drawback,
        T0=STRATEGY_CONFIG.get("T0", False),
        commission_rate=commission_rate,
        slippage=slippage,
    )


def create_first_sell_position(symbol: str, freq: str = "30分钟",
                               commission_rate: float | None = None,
                               slippage: float | None = None,
                               enable_daily_filter: bool = True) -> Position:
    """一卖空头持仓子策略；一卖为顶部左侧试仓，只排除日线明确强势。"""
    daily_filter = (
        _higher_level_filter_signals(direction="short", strict=False)
        if enable_daily_filter else {"signals_all": [], "signals_not": []}
    )
    opens = [
        Event.load({
            "name": "一卖确认开空",
            "operate": "开空",
            "signals_all": [
                f"{freq}_D1ZS_数据状态V260615_充分_任意_任意_0",
                f"{freq}_D1ZS_结构状态V260615_已确认_任意_任意_0",
                *daily_filter.get("signals_all", []),
                *_atr_filter_signals(freq)["signals_all"],
            ],
            "signals_any": [],
            "signals_not": [
                *daily_filter.get("signals_not", []),
            ],
            "factors": [{
                "name": "一卖顶背驰确认",
                "signals_all": [
                    f"{freq}_D1BSP_一卖V260615_一卖确认_任意_任意_0",
                    f"{freq}_D1BI_方向V260615_向下_任意_任意_0",
                ],
                "signals_any": [],
                "signals_not": [],
            }],
        }),
    ]

    exits = _build_exit_events(
        name="一卖平空",
        operate="平空",
        legacy_signals_any=[
            f"{freq}_D1BSP_空头风控V260615_结构失效_任意_任意_0",
            f"{freq}_D1BSP_空头风控V260615_震荡超限_任意_任意_0",
        ],
        directional_factors=[{
            "name": "方向反转平空",
            "signals_all": [
                f"{freq}_D1BI_方向V260615_向上_任意_任意_0",
            ],
            "signals_any": [
                f"{freq}_D1ZS_位置V260615_中枢上方_任意_任意_0",
                f"{freq}_D1ZS_位置V260615_中枢内_任意_任意_0",
            ],
            "signals_not": [],
        }],
        restructured_structural_signal_key=f"{freq}_D1BSP_空头风控RV260615",
        restructured_extra_signals_any=[
            f"{freq}_D1BSP_空头风控V260615_震荡超限_任意_任意_0",
        ],
    )

    trailing_start, trailing_drawback = _research_trailing_params(symbol)

    return Position(
        name="一卖空头",
        symbol=symbol,
        opens=opens,
        exits=exits,
        interval=STRATEGY_CONFIG.get("interval_1sell", STRATEGY_CONFIG.get("interval_1buy", 3600 * 24)),
        timeout=STRATEGY_CONFIG.get("timeout_1sell", STRATEGY_CONFIG.get("timeout_1buy", 600)),
        stop_loss=STRATEGY_CONFIG.get("stop_loss_1sell", STRATEGY_CONFIG.get("stop_loss_1buy", 200)),
        trailing_start=trailing_start,
        trailing_drawback_pct=trailing_drawback,
        T0=STRATEGY_CONFIG.get("T0", False),
        commission_rate=commission_rate,
        slippage=slippage,
    )


def create_second_sell_position(symbol: str, freq: str = "30分钟",
                                commission_rate: float | None = None,
                                slippage: float | None = None,
                                enable_daily_filter: bool = True) -> Position:
    """二卖空头持仓子策略；必须有一卖锚点上下文支撑。"""
    daily_filter = (
        _higher_level_filter_signals(direction="short", strict=True)
        if enable_daily_filter else {"signals_all": [], "signals_not": []}
    )
    opens = [
        Event.load({
            "name": "二卖确认开空",
            "operate": "开空",
            "signals_all": [
                f"{freq}_D1ZS_数据状态V260615_充分_任意_任意_0",
                f"{freq}_D1ZS_结构状态V260615_已确认_任意_任意_0",
                *daily_filter.get("signals_all", []),
                *_atr_filter_signals(freq)["signals_all"],
            ],
            "signals_any": [
                f"{freq}_D1ZS_位置V260615_中枢下方_任意_任意_0",
                f"{freq}_D1ZS_位置V260615_中枢内_任意_任意_0",
            ],
            "signals_not": [
                f"{freq}_D1ZS_位置V260615_中枢上方_任意_任意_0",
                f"{freq}_D1ZS_位置V260615_无中枢_任意_任意_0",
                f"{freq}_D1BI_背驰V260615_无_任意_任意_0",
                *daily_filter.get("signals_not", []),
            ],
            "factors": [{
                "name": "二卖反抽确认",
                "signals_all": [
                    f"{freq}_D1BSP_二卖V260615_二卖确认_任意_任意_0",
                    f"{freq}_D1BI_方向V260615_向下_任意_任意_0",
                ],
                "signals_any": [],
                "signals_not": [],
            }],
        }),
    ]

    exits = _build_exit_events(
        name="二卖平空",
        operate="平空",
        legacy_signals_any=[
            f"{freq}_D1BSP_空头风控V260615_结构失效_任意_任意_0",
        ],
        directional_factors=[{
            "name": "突破一卖高点",
            "signals_all": [
                f"{freq}_D1BI_方向V260615_向上_任意_任意_0",
                f"{freq}_D1ZS_位置V260615_中枢上方_任意_任意_0",
            ],
            "signals_any": [],
            "signals_not": [],
        }],
        restructured_structural_signal_key=f"{freq}_D1BSP_空头风控RV260615",
    )

    trailing_start, trailing_drawback = _research_trailing_params(symbol)

    return Position(
        name="二卖空头",
        symbol=symbol,
        opens=opens,
        exits=exits,
        interval=STRATEGY_CONFIG.get("interval_2sell", STRATEGY_CONFIG.get("interval_2buy", 3600 * 24)),
        timeout=STRATEGY_CONFIG.get("timeout_2sell", STRATEGY_CONFIG.get("timeout_2buy", 1000)),
        stop_loss=STRATEGY_CONFIG.get("stop_loss_2sell", STRATEGY_CONFIG.get("stop_loss_2buy", 300)),
        trailing_start=trailing_start,
        trailing_drawback_pct=trailing_drawback,
        T0=STRATEGY_CONFIG.get("T0", False),
        commission_rate=commission_rate,
        slippage=slippage,
    )


def create_third_sell_position(symbol: str, freq: str = "30分钟",
                               commission_rate: float | None = None,
                               slippage: float | None = None,
                               enable_daily_filter: bool = True) -> Position:
    """三卖空头持仓子策略；趋势跟随型向下离开后反抽确认。"""
    daily_filter = (
        _higher_level_filter_signals(direction="short", strict=True)
        if enable_daily_filter else {"signals_all": [], "signals_not": []}
    )
    opens = [
        Event.load({
            "name": "三卖确认开空",
            "operate": "开空",
            "signals_all": [
                f"{freq}_D1ZS_数据状态V260615_充分_任意_任意_0",
                f"{freq}_D1ZS_结构状态V260615_已确认_任意_任意_0",
                *daily_filter.get("signals_all", []),
                *_atr_filter_signals(freq)["signals_all"],
            ],
            "signals_any": [],
            "signals_not": [
                f"{freq}_D1ZS_位置V260615_中枢上方_任意_任意_0",
                *daily_filter.get("signals_not", []),
            ],
            "factors": [{
                "name": "三卖完整确认",
                "signals_all": [
                    f"{freq}_D1BSP_三卖阶段V260615_三卖确认_任意_任意_0",
                    f"{freq}_D1BI_方向V260615_向下_任意_任意_0",
                ],
                "signals_any": [],
                "signals_not": [],
            }],
        }),
    ]

    exits = _build_exit_events(
        name="三卖平空",
        operate="平空",
        legacy_signals_any=[
            f"{freq}_D1BSP_空头风控V260615_结构失效_任意_任意_0",
        ],
        directional_factors=[{
            "name": "反弹入中枢",
            "signals_all": [
                f"{freq}_D1ZS_位置V260615_中枢内_任意_任意_0",
                f"{freq}_D1BI_方向V260615_向上_任意_任意_0",
            ],
            "signals_any": [],
            "signals_not": [],
        }, {
            "name": "突破中枢",
            "signals_all": [
                f"{freq}_D1ZS_位置V260615_中枢上方_任意_任意_0",
            ],
            "signals_any": [],
            "signals_not": [],
        }],
        restructured_structural_signal_key=f"{freq}_D1BSP_空头风控RV260615",
    )

    trailing_start, trailing_drawback = _research_trailing_params(symbol)

    return Position(
        name="三卖空头",
        symbol=symbol,
        opens=opens,
        exits=exits,
        interval=STRATEGY_CONFIG.get("interval_3sell", STRATEGY_CONFIG.get("interval_3buy", 3600 * 24)),
        timeout=STRATEGY_CONFIG.get("timeout_3sell", STRATEGY_CONFIG.get("timeout_3buy", 1500)),
        stop_loss=STRATEGY_CONFIG.get("stop_loss_3sell", STRATEGY_CONFIG.get("stop_loss_3buy", 350)),
        trailing_start=trailing_start,
        trailing_drawback_pct=trailing_drawback,
        T0=STRATEGY_CONFIG.get("T0", False),
        commission_rate=commission_rate,
        slippage=slippage,
    )


# ========== 策略基类 ==========

class ChanTimingStrategy:
    """
    缠论择时策略

    组合多个独立的Position子策略

    一买上下文机制:
    - 维护buy1_history记录已确认的一买信号
    - 二买子策略仅在一买子策略有过历史交易记录后才生效
    - 这确保了"二买回抽确认"有真实的一买锚点支撑

    一卖上下文机制:
    - 维护sell1_history记录已确认的一卖信号
    - 二卖子策略仅在一卖子策略有过历史交易记录后才生效
    """

    def __init__(self, symbol: str, freq: str = "30分钟",
                 commission_rate: float = None, slippage: float = None,
                 enable_daily_filter: Optional[bool] = None,
                 enable_short: Optional[bool] = None):
        """
        初始化缠论择时策略

        :param symbol: 品种代码
        :param freq: 交易周期频率名
        :param commission_rate: 手续费率（从config或engine传入，不再硬编码）
        :param slippage: 滑点（从config或engine传入，不再硬编码）
        :param enable_daily_filter: 是否启用日线趋势过滤；None 时按配置决定
        :param enable_short: 是否启用一卖/二卖/三卖空头子策略；None 时按配置决定
        """
        from chan_strategy.config import BACKTEST_CONFIG
        self.symbol = symbol
        self.freq = freq
        self.enable_daily_filter = (
            STRATEGY_CONFIG.get("filter_freq") == "日线"
            if enable_daily_filter is None else enable_daily_filter
        )
        self.enable_short = (
            STRATEGY_CONFIG.get("enable_short", False)
            if enable_short is None else enable_short
        )
        if enable_short is None and self.enable_short:
            enabled_short_symbols = STRATEGY_CONFIG.get("enable_short_symbols")
            if enabled_short_symbols is not None:
                enabled_keys = {_research_symbol_key(x) for x in enabled_short_symbols}
                self.enable_short = _research_symbol_key(symbol) in enabled_keys
        # 修复问题4: 从外部接收成本参数，而非硬编码
        self.commission_rate = commission_rate if commission_rate is not None else BACKTEST_CONFIG["commission_rate"]
        self.slippage = slippage if slippage is not None else BACKTEST_CONFIG["slippage"]
        self._positions = None
        # 一买历史记录（用于二买上下文判断）
        # 记录完整锚点信息: dt, price, zs_zd, zs_zg
        self.buy1_history: List[dict] = []
        self._last_buy1_anchor: Optional[dict] = None
        # 一卖历史记录（用于二卖上下文判断）
        # 记录完整锚点信息: dt, price, zs_zd, zs_zg
        self.sell1_history: List[dict] = []
        self._last_sell1_anchor: Optional[dict] = None

        # A45 ATR chop-filter state tracker (updated every trade-frequency bar).
        from chan_strategy.signals import AtrStateTracker
        self._atr_tracker = AtrStateTracker(
            period=STRATEGY_CONFIG.get("atr_period", 14),
            lookback=STRATEGY_CONFIG.get("atr_lookback", 100),
            floor=STRATEGY_CONFIG.get("atr_percentile_floor", 0.30),
        )

    def get_last_buy1_anchor(self) -> Optional[dict]:
        """获取最近的一买锚点信息（供二买信号绑定使用）"""
        return self._last_buy1_anchor

    def get_last_sell1_anchor(self) -> Optional[dict]:
        """获取最近的一卖锚点信息（供二卖信号绑定使用）"""
        return self._last_sell1_anchor

    def _log_daily_trend(self, signals_dict: dict, dt: datetime):
        """记录日线趋势状态（供调试与验证过滤是否生效）"""
        if STRATEGY_CONFIG.get("filter_freq") != "日线":
            return

        bi_key = "日线_D1BI_方向V260615"
        zs_key = "日线_D1ZS_位置V260615"
        if bi_key not in signals_dict:
            return

        direction = signals_dict[bi_key].split("_")[0]
        position = signals_dict.get(zs_key, "").split("_")[0] or "无"
        bullish = direction == "向上" and position != "中枢下方"
        status = "看多" if bullish else "不看多"
        # 仅在状态变化时打印，避免日志刷屏
        if getattr(self, "_last_daily_trend_status", None) != status:
            self._last_daily_trend_status = status
            self.write_log(f"[日线趋势] {dt}: 方向={direction}, 位置={position} -> {status}")

    def _daily_regime(self, signals_dict: dict) -> str:
        """Classify the current daily regime for the A46 router.

        :return: "long" (daily up + not below center),
                 "short" (daily down + not above center),
                 or "ambiguous" (inside center, no center, or conflicting).
        """
        direction = (signals_dict.get("日线_D1BI_方向V260615", "") or "").split("_")[0]
        position = (signals_dict.get("日线_D1ZS_位置V260615", "") or "").split("_")[0]

        if direction == "向上" and position != "中枢下方":
            return "long"
        if direction == "向下" and position != "中枢上方":
            return "short"
        return "ambiguous"

    def _record_buy1_anchor(self, signals_dict: dict, price: float, dt: datetime,
                             czsc_obj=None):
        """记录一买锚点信息

        修复: 原实现记录 bar.close 作为一买锚点价格，但一买锚点应是一买结构中
        向下离开笔的真实低点。现在优先从 CZSC 对象的 bi_list 中提取最近向下笔的低点。
        """
        # 检查一买确认信号
        for k, v in signals_dict.items():
            if "一买V260615" in k and "一买确认" in v:
                # 优先从 CZSC 对象提取一买结构真实低点和结束时间
                anchor_price = price
                anchor_dt = dt
                if czsc_obj is not None:  # pragma: no branch - fallback path is covered through direct price anchoring
                    # 与信号层保持同一口径，剔除可能仍在延伸的末笔
                    from chan_strategy.signals import _get_confirmed_bi_list
                    bis = _get_confirmed_bi_list(czsc_obj)
                    # 寻找最近的向下笔，取其低点和结束时间作为一买锚点
                    for bi in reversed(bis):  # pragma: no branch - loop exits on first confirmed down bi
                        if bi.direction == Direction.Down:
                            anchor_price = bi.low
                            anchor_dt = bi.edt
                            break

                # 避免重复记录同一时刻的一买
                if self.buy1_history and self.buy1_history[-1]["dt"] == anchor_dt:
                    return

                anchor = {
                    "dt": anchor_dt,
                    "price": anchor_price,
                    "zs_zd": None,   # 将在 update 中补充
                    "zs_zg": None,   # 将在 update 中补充
                }
                self.buy1_history.append(anchor)
                self._last_buy1_anchor = anchor
                return

    def _record_sell1_anchor(self, signals_dict: dict, price: float, dt: datetime,
                             czsc_obj=None):
        """记录一卖锚点信息；锚点价格取一卖结构中向上离开笔的真实高点。"""
        for k, v in signals_dict.items():
            if "一卖V260615" in k and "一卖确认" in v:
                anchor_price = price
                anchor_dt = dt
                if czsc_obj is not None:
                    from chan_strategy.signals import _get_confirmed_bi_list
                    bis = _get_confirmed_bi_list(czsc_obj)
                    for bi in reversed(bis):
                        if bi.direction == Direction.Up:
                            anchor_price = bi.high
                            anchor_dt = bi.edt
                            break

                if self.sell1_history and self.sell1_history[-1]["dt"] == anchor_dt:
                    return

                anchor = {
                    "dt": anchor_dt,
                    "price": anchor_price,
                    "zs_zd": None,
                    "zs_zg": None,
                }
                self.sell1_history.append(anchor)
                self._last_sell1_anchor = anchor
                return

    @property
    def positions(self) -> List[Position]:
        if self._positions is None:
            positions = [
                create_first_buy_position(self.symbol, self.freq,
                                          self.commission_rate, self.slippage,
                                          enable_daily_filter=self.enable_daily_filter),
                create_second_buy_position(self.symbol, self.freq,
                                           self.commission_rate, self.slippage,
                                           enable_daily_filter=self.enable_daily_filter),
                create_third_buy_position(self.symbol, self.freq,
                                          self.commission_rate, self.slippage,
                                          enable_daily_filter=self.enable_daily_filter),
            ]
            if self.enable_short:
                positions.extend([
                    create_first_sell_position(self.symbol, self.freq,
                                               self.commission_rate, self.slippage,
                                               enable_daily_filter=self.enable_daily_filter),
                    create_second_sell_position(self.symbol, self.freq,
                                                self.commission_rate, self.slippage,
                                                enable_daily_filter=self.enable_daily_filter),
                    create_third_sell_position(self.symbol, self.freq,
                                               self.commission_rate, self.slippage,
                                               enable_daily_filter=self.enable_daily_filter),
                ])
            self._positions = positions
        return self._positions

    def update(self, signals_dict: dict, price: float, dt: datetime,
               execution_price: float = None, czsc_obj=None,
               bar_high: float = None, bar_low: float = None,
               equity_at_entry: float | None = None,
               total_open_margin: float | None = None,
               entry_at_limit: bool | None = None,
               exit_at_limit: bool | None = None):
        """
        更新所有持仓子策略

        :param signals_dict: 当前信号字典
        :param price: 当前价格（用于风控）
        :param dt: 当前时间
        :param execution_price: 信号驱动交易的成交价（延迟成交时为下一根开盘价）
        :param czsc_obj: 可选的 CZSC 对象，用于补充一买锚点中的中枢信息
        :param bar_high: 当根bar最高价，透传给各子策略用于 intrabar 触价止损
        :param bar_low: 当根bar最低价，透传给各子策略用于 intrabar 触价止损
        :param equity_at_entry: A40 risk-mode equity basis for lot sizing
        :param total_open_margin: A40 risk-mode pre-open margin across all positions
        :param entry_at_limit: A51 flag passed to each Position for entry tagging.
        :param exit_at_limit: A51 flag passed to each Position for exit tagging.
        """
        # A51/A67: forward limit flags under "aware" and "enforce"; "off" keeps
        # the legacy Position.update call signature byte-identical.
        limit_kwargs: dict = {}
        if STRATEGY_CONFIG.get("limit_halt_model", "off") in ("aware", "enforce"):
            limit_kwargs["entry_at_limit"] = entry_at_limit
            limit_kwargs["exit_at_limit"] = exit_at_limit

        # 记录日线趋势状态（便于验证日线过滤是否生效）
        self._log_daily_trend(signals_dict, dt)

        # 记录一买/一卖锚点（在信号生成后、策略更新前）
        self._record_buy1_anchor(signals_dict, price, dt, czsc_obj=czsc_obj)
        self._record_sell1_anchor(signals_dict, price, dt, czsc_obj=czsc_obj)

        # 如果有 CZSC 对象，补充最近一买锚点的中枢信息
        if czsc_obj is not None and self._last_buy1_anchor is not None:
            if self._last_buy1_anchor.get("zs_zd") is None:
                from chan_strategy.signals import build_zhongshu_from_bis, _get_confirmed_bi_list
                bi_list = _get_confirmed_bi_list(czsc_obj)
                zhongshu_list = build_zhongshu_from_bis(bi_list) if bi_list else []
                anchor_low = self._last_buy1_anchor.get("price")
                if zhongshu_list and anchor_low is not None:  # pragma: no branch - empty structures keep anchor unfilled by design
                    # 修复: 一买锚点应绑定到“被向下离开突破”的那个中枢，
                    # 即满足 zs_zd > anchor_low 的最近中枢。
                    matched_zs = None
                    for zs in reversed(zhongshu_list):
                        if zs["zd"] > anchor_low:
                            matched_zs = zs
                            break
                    if matched_zs is None:
                        # fallback：如果没有中枢满足条件，使用最近中枢
                        matched_zs = zhongshu_list[-1]
                    self._last_buy1_anchor["zs_zd"] = matched_zs["zd"]
                    self._last_buy1_anchor["zs_zg"] = matched_zs["zg"]

        # 如果有 CZSC 对象，补充最近一卖锚点的中枢信息
        if czsc_obj is not None and self._last_sell1_anchor is not None:
            if self._last_sell1_anchor.get("zs_zg") is None:
                from chan_strategy.signals import build_zhongshu_from_bis, _get_confirmed_bi_list
                bi_list = _get_confirmed_bi_list(czsc_obj)
                zhongshu_list = build_zhongshu_from_bis(bi_list) if bi_list else []
                anchor_high = self._last_sell1_anchor.get("price")
                if zhongshu_list and anchor_high is not None:
                    # 一卖锚点应绑定到“被向上离开突破”的那个中枢，
                    # 即满足 zs_zg < anchor_high 的最近中枢。
                    matched_zs = None
                    for zs in reversed(zhongshu_list):
                        if zs["zg"] < anchor_high:
                            matched_zs = zs
                            break
                    if matched_zs is None:
                        matched_zs = zhongshu_list[-1]
                    self._last_sell1_anchor["zs_zd"] = matched_zs["zd"]
                    self._last_sell1_anchor["zs_zg"] = matched_zs["zg"]

        # A45: update incremental ATR state every trade-frequency bar.
        # The ATR signal is injected only when it is actually needed:
        #   - atr_chop_filter="on" gates all new opens, or
        #   - second_buy_mode="gated" needs the ATR expansion check.
        # A47: the current ATR value is also passed to each Position for the
        # structural_atr trailing stop.
        atr_state = self._atr_tracker.update(
            high=bar_high if bar_high is not None else price,
            low=bar_low if bar_low is not None else price,
            close=price,
        )
        current_atr = atr_state.get("atr")
        inject_atr = (
            STRATEGY_CONFIG.get("atr_chop_filter") == "on"
            or STRATEGY_CONFIG.get("second_buy_mode") == "gated"
        )
        if inject_atr:
            signals_dict = dict(signals_dict)
            signals_dict.update(self._atr_tracker.signal(self.freq))

        # A46: regime router decides which side is allowed to open NEW positions.
        # Existing positions always exit normally because opens_allowed only blocks
        # open events (pos == 0).
        regime_model = STRATEGY_CONFIG.get("regime_model", "independent")
        if regime_model == "router":
            regime = self._daily_regime(signals_dict)
            current_long = any(p.pos > 0 for p in self.positions)
            current_short = any(p.pos < 0 for p in self.positions)
            for pos in self.positions:
                if pos.pos != 0:
                    pos.opens_allowed = True
                    continue
                if "多头" in pos.name:
                    pos.opens_allowed = (regime == "long" and not current_short)
                elif "空头" in pos.name:
                    pos.opens_allowed = (regime == "short" and not current_long)
                else:
                    pos.opens_allowed = False
        else:
            for pos in self.positions:
                pos.opens_allowed = True

        # A46: symmetric P4/P5 gating for short opens (applied in both modes).
        short_open_allowed = (
            _research_short_open_allowed(self.symbol, signals_dict, self.freq)
            if self.enable_short else False
        )

        # 更新各子策略
        buy1_pos = self.positions[0]  # 一买子策略
        buy2_pos = self.positions[1]  # 二买子策略
        buy3_pos = self.positions[2]  # 三买子策略

        # 一买和三买正常更新
        if buy1_pos.pos != 0 or _research_first_buy_allowed(self.symbol, signals_dict):
            buy1_pos.update(signals_dict, price, dt, execution_price=execution_price, bar_high=bar_high, bar_low=bar_low,
                            equity_at_entry=equity_at_entry, total_open_margin=total_open_margin, atr=current_atr,
                            **limit_kwargs)
        else:
            buy1_pos.update({}, price, dt, execution_price=execution_price, bar_high=bar_high, bar_low=bar_low,
                            equity_at_entry=equity_at_entry, total_open_margin=total_open_margin, atr=current_atr,
                            **limit_kwargs)
        buy3_pos.update(signals_dict, price, dt, execution_price=execution_price, bar_high=bar_high, bar_low=bar_low,
                        equity_at_entry=equity_at_entry, total_open_margin=total_open_margin, atr=current_atr,
                        **limit_kwargs)

        # 二买需要一买上下文: 仅当一买子策略有过历史交易记录或有一买锚点时才生效
        if buy1_pos.pairs or self.buy1_history:
            # 有一买交易记录或一买信号历史，二买可以正常运行；
            # 研究参数只拦截新开仓，已有二买持仓仍接收退出/风控信号。
            trade_price = execution_price if execution_price is not None else price
            if buy2_pos.pos != 0 or _research_second_buy_allowed(
                self.symbol, self._last_buy1_anchor, trade_price, signals_dict, self.freq
            ):
                buy2_pos.update(signals_dict, price, dt, execution_price=execution_price, bar_high=bar_high, bar_low=bar_low,
                                equity_at_entry=equity_at_entry, total_open_margin=total_open_margin, atr=current_atr,
                                **limit_kwargs)
            else:
                buy2_pos.update({}, price, dt, execution_price=execution_price, bar_high=bar_high, bar_low=bar_low,
                                equity_at_entry=equity_at_entry, total_open_margin=total_open_margin, atr=current_atr,
                                **limit_kwargs)
        else:
            # 无一买上下文，二买仅执行风控（传空信号，不触发开仓）
            buy2_pos.update({}, price, dt, execution_price=execution_price, bar_high=bar_high, bar_low=bar_low,
                            equity_at_entry=equity_at_entry, total_open_margin=total_open_margin, atr=current_atr,
                            **limit_kwargs)

        if self.enable_short:
            sell1_pos = self.positions[3]  # 一卖子策略
            sell2_pos = self.positions[4]  # 二卖子策略
            sell3_pos = self.positions[5]  # 三卖子策略

            # 一卖和三卖正常更新（已有持仓仍接收退出/风控；新仓受 P4/P5 门控）
            if sell1_pos.pos != 0 or short_open_allowed:
                sell1_pos.update(signals_dict, price, dt, execution_price=execution_price, bar_high=bar_high, bar_low=bar_low,
                                 equity_at_entry=equity_at_entry, total_open_margin=total_open_margin, atr=current_atr,
                                 **limit_kwargs)
            else:
                sell1_pos.update({}, price, dt, execution_price=execution_price, bar_high=bar_high, bar_low=bar_low,
                                 equity_at_entry=equity_at_entry, total_open_margin=total_open_margin, atr=current_atr,
                                 **limit_kwargs)

            if sell3_pos.pos != 0 or short_open_allowed:
                sell3_pos.update(signals_dict, price, dt, execution_price=execution_price, bar_high=bar_high, bar_low=bar_low,
                                 equity_at_entry=equity_at_entry, total_open_margin=total_open_margin, atr=current_atr,
                                 **limit_kwargs)
            else:
                sell3_pos.update({}, price, dt, execution_price=execution_price, bar_high=bar_high, bar_low=bar_low,
                                 equity_at_entry=equity_at_entry, total_open_margin=total_open_margin, atr=current_atr,
                                 **limit_kwargs)

            # 二卖需要一卖上下文
            if sell1_pos.pairs or self.sell1_history:
                if sell2_pos.pos != 0 or short_open_allowed:
                    sell2_pos.update(signals_dict, price, dt, execution_price=execution_price, bar_high=bar_high, bar_low=bar_low,
                                     equity_at_entry=equity_at_entry, total_open_margin=total_open_margin, atr=current_atr,
                                     **limit_kwargs)
                else:
                    sell2_pos.update({}, price, dt, execution_price=execution_price, bar_high=bar_high, bar_low=bar_low,
                                     equity_at_entry=equity_at_entry, total_open_margin=total_open_margin, atr=current_atr,
                                     **limit_kwargs)
            else:
                sell2_pos.update({}, price, dt, execution_price=execution_price, bar_high=bar_high, bar_low=bar_low,
                                 equity_at_entry=equity_at_entry, total_open_margin=total_open_margin, atr=current_atr,
                                 **limit_kwargs)

    def get_total_pos(self) -> int:
        """获取总仓位方向"""
        return sum(p.pos for p in self.positions)

    def flatten_all_positions(self, price: float, dt: datetime, reason: str = "flatten") -> None:
        """Close all open positions immediately (used by portfolio daily loss limit)."""
        for pos in self.positions:
            if pos.pos > 0:
                pos._close_long(price, dt, reason)
            elif pos.pos < 0:
                pos._close_short(price, dt, reason)

    def evaluate_all(self) -> dict:
        """评估所有子策略"""
        results = {}
        for pos in self.positions:
            results[pos.name] = pos.evaluate()
        return results

    def get_combined_trades(self) -> List[dict]:
        """获取所有子策略的配对交易"""
        all_pairs = []
        for pos in self.positions:
            for pair in pos.pairs:
                pair_copy = pair.copy()
                pair_copy["strategy"] = pos.name
                all_pairs.append(pair_copy)
        return sorted(all_pairs, key=lambda x: x["open_dt"])

    def write_log(self, msg: str):
        """打印策略日志"""
        print(msg)
