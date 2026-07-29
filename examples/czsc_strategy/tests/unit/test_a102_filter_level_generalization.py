"""A102 — 5分钟交易级别 + 过滤层泛化 tests.

Covers:
- D2 trade_freq_profiles 机制（get_strategy_param 覆盖/兜底、白名单 fail-closed）
- D1/D3 过滤层标签跟随 filter_freq（默认 "日线" 字节一致）
- AC5 分钟级过滤层时序纪律（未完结 bar 不进入过滤层索引）
- 端到端：filter_freq="30分钟" 引擎跑通且信号键带 "30分钟" 前缀；
  regime_model="router" 时日线 regime 键独立存在
"""
from datetime import datetime

import pytest
from czsc import Freq

from chan_strategy.backtest_engine import BacktestEngine
from chan_strategy.config import (
    STRATEGY_CONFIG,
    get_strategy_param,
    validate_trade_freq_profiles,
)
from chan_strategy.data_adapter import resample_bars
from chan_strategy.positions import (
    _daily_trend_filter_signals,
    _higher_level_filter_signals,
    _resonance_holds,
)




def _make_rw_bars(days=30, per_day=180, start=datetime(2024, 1, 2, 9, 0), seed=42):
    """带5日级趋势交替的随机游走1分钟数据——保证 30/60分钟与日线级别均能成笔，
    使引擎的过滤层信号合并分支（czsc_filter.bi_list 非空）可达。"""
    import random
    from datetime import timedelta
    from tests.conftest import make_raw_bar

    rng = random.Random(seed)
    bars = []
    price = 100.0
    i = 0
    for d in range(days):
        day = start.date() + timedelta(days=d)
        session_start = datetime.combine(day, start.time())
        drift = 0.35 if (d // 5) % 2 == 0 else -0.30
        for m in range(per_day):
            dt = session_start + timedelta(minutes=m)
            delta = drift + rng.gauss(0, 0.15)
            bars.append(make_raw_bar(i, dt, open_=price, close=price + delta))
            price += delta
            i += 1
    return bars


@pytest.fixture
def config_guard():
    original = dict(STRATEGY_CONFIG)
    yield
    STRATEGY_CONFIG.clear()
    STRATEGY_CONFIG.update(original)


# ---------- D2 profile 机制 ----------

def test_get_strategy_param_default_matches_base_config(config_guard):
    """trade_freq="30分钟"（无 profile）时与直接读 STRATEGY_CONFIG 完全一致。"""
    STRATEGY_CONFIG["trade_freq"] = "30分钟"
    for key in ("stop_loss_1buy", "timeout_2buy", "trailing_start_bp",
                "structural_invalidation_pct"):
        assert get_strategy_param(key) == STRATEGY_CONFIG[key]


def test_get_strategy_param_5min_profile_overrides(config_guard):
    STRATEGY_CONFIG["trade_freq"] = "5分钟"
    assert get_strategy_param("stop_loss_1buy") == 87
    assert get_strategy_param("timeout_1buy") == 3600
    assert get_strategy_param("structural_invalidation_pct") == 0.0218
    # 未覆盖键回落基线
    assert get_strategy_param("pos_1buy") == STRATEGY_CONFIG["pos_1buy"]


def test_validate_trade_freq_profiles_rejects_non_whitelist(config_guard):
    # 整体替换而非原位改嵌套 dict（浅拷贝 restore 无法回收嵌套污染）
    STRATEGY_CONFIG["trade_freq_profiles"] = {"5分钟": {"commission_rate": 0.001}}
    with pytest.raises(ValueError, match="非白名单"):
        validate_trade_freq_profiles()


# ---------- D1/D3 标签泛化 ----------

def test_filter_signals_default_daily_byte_identical(config_guard):
    STRATEGY_CONFIG["filter_freq"] = "日线"
    STRATEGY_CONFIG["resonance_filter"] = "off"
    sig = _daily_trend_filter_signals(direction="long", strict=True)
    assert sig["signals_all"] == ["日线_D1BI_方向V260615_向上_任意_任意_0"]
    assert sig["signals_not"] == ["日线_D1ZS_位置V260615_中枢下方_任意_任意_0"]


def test_filter_signals_follow_minute_filter_freq(config_guard):
    STRATEGY_CONFIG["filter_freq"] = "30分钟"
    sig = _daily_trend_filter_signals(direction="long", strict=True)
    assert sig["signals_all"] == ["30分钟_D1BI_方向V260615_向上_任意_任意_0"]
    assert sig["signals_not"] == ["30分钟_D1ZS_位置V260615_中枢下方_任意_任意_0"]

    # resonance 第一腿同样跟随 filter_freq
    STRATEGY_CONFIG["resonance_filter"] = "daily_4h"
    combined = _higher_level_filter_signals(direction="long")
    assert "30分钟_D1BI_方向V260615_向上_任意_任意_0" in combined["signals_all"]
    assert "240分钟_D1BI_方向V260615_向上_任意_任意_0" in combined["signals_all"]

    # _resonance_holds 用同一套键判定
    signals_dict = {
        "30分钟_D1BI_方向V260615": "向上_任意_任意_50",
        "30分钟_D1ZS_位置V260615": "中枢内_任意_任意_50",
        "240分钟_D1BI_方向V260615": "向上_任意_任意_50",
        "240分钟_D1ZS_位置V260615": "中枢上方_任意_任意_50",
    }
    assert _resonance_holds(signals_dict, direction="long", force_resonance=True)
    signals_dict["240分钟_D1ZS_位置V260615"] = "中枢下方_任意_任意_50"
    assert not _resonance_holds(signals_dict, direction="long", force_resonance=True)


# ---------- AC5 分钟级过滤层时序纪律 ----------

def test_minute_filter_level_does_not_see_bar_before_it_closes(synthetic_1m_bars):
    """过滤层（30分钟）bar 时间戳是该组最后一根1m bar；索引只在
    ``filter_bar.dt <= current_bar.dt`` 时推进——与 4H/日线同一纪律。
    """
    bars = synthetic_1m_bars(days=2, per_day=240, start=datetime(2024, 1, 2, 0, 0))
    filter_bars = resample_bars(bars, Freq.F30, 30)
    assert len(filter_bars) >= 2

    first = filter_bars[0]
    assert first.dt == bars[29].dt  # 组内最后一根1m bar

    idx = 1
    current_intrabar = bars[30 + 15]  # 第二组 30分钟 bar 未完结
    seen = []
    while idx < len(filter_bars) and filter_bars[idx].dt <= current_intrabar.dt:
        seen.append(filter_bars[idx])
        idx += 1
    assert seen == [] and idx == 1

    current_at_close = filter_bars[1]
    while idx < len(filter_bars) and filter_bars[idx].dt <= current_at_close.dt:
        seen.append(filter_bars[idx])
        idx += 1
    assert seen == [filter_bars[1]] and idx == 2


# ---------- 端到端：分钟级过滤层引擎 ----------

def test_backtest_engine_runs_with_minute_filter_freq(config_guard):
    """filter_freq="60分钟"（与交易级别 30分钟 不同）时引擎跑通，
    信号字典含 "60分钟" 前缀的过滤层键——该前缀只能来自过滤层路径。
    """
    STRATEGY_CONFIG["filter_freq"] = "60分钟"
    engine = BacktestEngine("TEST", db_path="none")
    bars = _make_rw_bars()
    engine.load_data = lambda: setattr(engine, "bars", bars) or True
    # warmup 需覆盖足够的过滤层 bar（warmup_bars=24 → warmup_dt 进入第5日）
    report = engine.run(warmup_bars=24)
    assert "error" not in report
    keys = set()
    for rec in engine.signal_history:
        keys.update(rec["signals"])
    assert any(k.startswith("60分钟_D1BI_方向V260615") for k in keys)
    assert not any(k.startswith("日线_") for k in keys)


def test_backtest_engine_router_keeps_independent_daily(config_guard):
    """regime_model="router" + filter_freq="60分钟"：日线 regime 键独立合成，
    与过滤层 "60分钟" 键共存（设计 §6.1）。
    """
    STRATEGY_CONFIG["filter_freq"] = "60分钟"
    STRATEGY_CONFIG["regime_model"] = "router"
    engine = BacktestEngine("TEST", db_path="none")
    bars = _make_rw_bars()
    engine.load_data = lambda: setattr(engine, "bars", bars) or True
    # warmup_bars=24 → warmup_dt 进入第5日，日线预热≥4根、60分钟预热充足
    report = engine.run(warmup_bars=24)
    assert "error" not in report
    keys = set()
    for rec in engine.signal_history:
        keys.update(rec["signals"])
    assert any(k.startswith("60分钟_D1BI_方向V260615") for k in keys)
    assert any(k.startswith("日线_D1BI_方向V260615") for k in keys)


def test_backtest_engine_default_daily_filter_unchanged(config_guard):
    """默认 filter_freq="日线"：过滤层键仍为 "日线" 前缀（基线语义不变）。"""
    engine = BacktestEngine("TEST", db_path="none")
    bars = _make_rw_bars()
    engine.load_data = lambda: setattr(engine, "bars", bars) or True
    report = engine.run(warmup_bars=24)
    assert "error" not in report
    keys = set()
    for rec in engine.signal_history:
        keys.update(rec["signals"])
    assert any(k.startswith("日线_D1BI_方向V260615") for k in keys)
