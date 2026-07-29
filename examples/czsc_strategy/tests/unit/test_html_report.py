"""Unit tests for the HTML visual backtest report (A105)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from czsc import Direction, Mark, Operate

from chan_strategy.backtest_engine import BacktestEngine
from chan_strategy.config import STRATEGY_CONFIG
from chan_strategy.html_report import (
    build_symbol_chart_payload,
    render_backtest_html_report,
)
from chan_strategy.portfolio_engine import PortfolioEngine


# ---------------------------------------------------------------------------
# Lightweight fake objects for HTML-report unit tests (no real DB/SimNow).
# ---------------------------------------------------------------------------


@dataclass
class FakeFX:
    dt: datetime
    mark: Mark
    fx: float
    high: float
    low: float


@dataclass
class FakeBI:
    fx_a: FakeFX
    fx_b: FakeFX
    direction: Direction
    high: float
    low: float
    sdt: datetime = field(init=False)
    edt: datetime = field(init=False)

    def __post_init__(self):
        self.sdt = self.fx_a.dt
        self.edt = self.fx_b.dt


@dataclass
class FakeBar:
    dt: datetime
    open: float
    close: float
    high: float
    low: float
    vol: float


@dataclass
class FakeCZSC:
    bi_list: list[FakeBI]
    bars_raw: list[Any] = field(default_factory=list)


@dataclass
class FakeStrategy:
    pairs: list[dict[str, Any]]

    def get_combined_trades(self) -> list[dict[str, Any]]:
        return list(self.pairs)


@dataclass
class FakeEngine:
    symbol: str
    trade_bars: list[FakeBar]
    czsc_trade: FakeCZSC
    strategy: FakeStrategy
    report: dict[str, Any]

    def generate_report(self) -> dict[str, Any]:
        return dict(self.report)


def _make_bars(start: datetime, n: int) -> list[FakeBar]:
    """Generate a simple oscillating price series."""
    bars: list[FakeBar] = []
    price = 100.0
    for i in range(n):
        dt = start + timedelta(minutes=i)
        delta = 0.5 if (i // 10) % 2 == 0 else -0.4
        open_ = price
        close = price + delta
        high = max(open_, close) + 0.2
        low = min(open_, close) - 0.2
        bars.append(FakeBar(dt=dt, open=open_, close=close, high=high, low=low, vol=1000 + i))
        price = close
    return bars


def _make_fake_bis(start: datetime) -> list[FakeBI]:
    """Return a short alternating BI list."""
    fxs = [
        FakeFX(dt=start, mark=Mark.D, fx=99.0, high=100.0, low=98.5),
        FakeFX(dt=start + timedelta(minutes=30), mark=Mark.G, fx=101.0, high=101.5, low=99.5),
        FakeFX(dt=start + timedelta(minutes=60), mark=Mark.D, fx=99.5, high=100.5, low=99.0),
        FakeFX(dt=start + timedelta(minutes=90), mark=Mark.G, fx=102.0, high=102.5, low=100.5),
    ]
    return [
        FakeBI(fx_a=fxs[0], fx_b=fxs[1], direction=Direction.Up, high=fxs[1].high, low=fxs[0].low),
        FakeBI(fx_a=fxs[1], fx_b=fxs[2], direction=Direction.Down, high=fxs[1].high, low=fxs[2].low),
        FakeBI(fx_a=fxs[2], fx_b=fxs[3], direction=Direction.Up, high=fxs[3].high, low=fxs[2].low),
    ]


def _make_pairs(start: datetime) -> list[dict[str, Any]]:
    """Return one long and one short closed pair."""
    return [
        {
            "strategy": "一买多头",
            "direction": "long",
            "open_dt": start,
            "close_dt": start + timedelta(minutes=20),
            "open_price": 100.0,
            "close_price": 101.0,
            "pnl_pct": 0.01,
            "pnl_currency": 100.0,
            "volume": 1,
            "bars_held": 5,
            "reason": "timeout",
            "reason_code": "timeout",
        },
        {
            "strategy": "一卖空头",
            "direction": "short",
            "open_dt": start + timedelta(minutes=40),
            "close_dt": start + timedelta(minutes=60),
            "open_price": 101.5,
            "close_price": 100.5,
            "pnl_pct": 0.009,
            "pnl_currency": 90.0,
            "volume": 1,
            "bars_held": 4,
            "reason": "stop_loss",
            "reason_code": "stop_loss",
        },
    ]


def _make_fake_engine(symbol: str = "TEST") -> FakeEngine:
    start = datetime(2024, 1, 2, 9, 0)
    bars = _make_bars(start, 120)
    bis = _make_fake_bis(start)
    czsc = FakeCZSC(bi_list=bis, bars_raw=bars)
    pairs = _make_pairs(start)
    report = {
        "symbol": symbol,
        "period": "2024-01-02 ~ 2024-01-02",
        "total_trades": len(pairs),
        "win_rate": 1.0,
        "total_return_pct": 1.5,
        "max_drawdown_pct": 0.5,
        "sharpe_ratio": 1.2,
    }
    return FakeEngine(
        symbol=symbol,
        trade_bars=bars,
        czsc_trade=czsc,
        strategy=FakeStrategy(pairs=pairs),
        report=report,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_build_symbol_chart_payload_shape():
    engine = _make_fake_engine("RB888")
    payload = build_symbol_chart_payload(engine)

    assert set(payload.keys()) == {
        "kline", "bi", "xd", "zs", "bs", "trades_table", "summary"
    }
    assert len(payload["kline"]) == len(engine.trade_bars)
    assert len(payload["bi"]) == len(engine.czsc_trade.bi_list) + 1
    assert payload["xd"] == []
    assert len(payload["zs"]) >= 1
    assert len(payload["bs"]) == 2 * len(engine.strategy.pairs)
    assert payload["summary"]["symbol"] == "RB888"


def test_build_symbol_chart_payload_bi_fields():
    engine = _make_fake_engine()
    payload = build_symbol_chart_payload(engine)
    bi = payload["bi"][0]
    assert {"dt", "fx_mark", "start_dt", "end_dt", "fx_high", "fx_low", "bi"} <= set(bi.keys())
    assert bi["fx_mark"] in {"d", "g"}


def test_build_symbol_chart_payload_bs_operate_values():
    engine = _make_fake_engine()
    payload = build_symbol_chart_payload(engine)
    ops = [b["op"] for b in payload["bs"]]
    assert Operate.LO in ops
    assert Operate.LE in ops
    assert Operate.SO in ops
    assert Operate.SE in ops

    long_opens = [b for b in payload["bs"] if b["op"] == Operate.LO]
    assert len(long_opens) == 1
    assert long_opens[0]["price"] == 100.0


def test_build_symbol_chart_payload_bs_labels_chronological():
    """B/S sequence numbers are assigned independently, in chronological order."""
    engine = _make_fake_engine()
    payload = build_symbol_chart_payload(engine)
    bs = payload["bs"]
    by_op = {(b["op"], b["dt"]): b["label"] for b in bs}

    long_pair, short_pair = engine.strategy.pairs
    assert by_op[(Operate.LO, long_pair["open_dt"])] == "B1"
    assert by_op[(Operate.LE, long_pair["close_dt"])] == "S1"
    assert by_op[(Operate.SO, short_pair["open_dt"])] == "S2"
    assert by_op[(Operate.SE, short_pair["close_dt"])] == "B2"


def test_render_backtest_html_report_shows_bs_labels(tmp_path: Path):
    engine = _make_fake_engine()
    payload = build_symbol_chart_payload(engine)
    out_path = tmp_path / "report.html"
    render_backtest_html_report({"TEST": payload}, out_path=out_path, title="Test Report")

    html = out_path.read_text(encoding="utf-8")
    assert "BS_LABEL" in html
    assert '\\"B1\\"' in html or '"B1"' in html
    assert '\\"S1\\"' in html or '"S1"' in html


def test_build_symbol_chart_payload_empty_bi_list():
    engine = _make_fake_engine()
    engine.czsc_trade.bi_list = []
    payload = build_symbol_chart_payload(engine)
    assert payload["bi"] == []
    assert payload["zs"] == []


def test_render_backtest_html_report_smoke(tmp_path: Path):
    engine_a = _make_fake_engine("A888")
    engine_b = _make_fake_engine("RB888")
    payloads = {
        "A888": build_symbol_chart_payload(engine_a),
        "RB888": build_symbol_chart_payload(engine_b),
    }
    out_path = tmp_path / "report.html"
    result = render_backtest_html_report(payloads, out_path=out_path, title="Test Report")

    assert result == out_path
    assert out_path.exists()
    html = out_path.read_text(encoding="utf-8")
    assert "A888" in html
    assert "RB888" in html
    assert "成交订单清单" in html
    assert "总交易次数" in html
    assert "1.50" in html or "1.5" in html
    assert '<div class="report-extra"' in html


def test_render_backtest_html_report_annotates_bi_zhongshu(tmp_path: Path):
    """P0 口径整改（docs/theory_code_crosscheck.md §1.2）：报告必须注明所报
    中枢为笔中枢，并声明周期仅为观察窗口、非递归级别。"""
    engine_a = _make_fake_engine("A888")
    payloads = {"A888": build_symbol_chart_payload(engine_a)}
    out_path = tmp_path / "report.html"
    render_backtest_html_report(payloads, out_path=out_path, title="Test Report")

    html = out_path.read_text(encoding="utf-8")
    assert "笔中枢" in html
    assert "不可混称" in html
    assert "观察窗口" in html


def test_render_backtest_html_report_embeds_echarts_js_no_cdn(tmp_path: Path):
    """Reports must not depend on the pyecharts CDN to render offline."""
    engine_a = _make_fake_engine("A888")
    payloads = {"A888": build_symbol_chart_payload(engine_a)}
    out_path = tmp_path / "report.html"
    render_backtest_html_report(payloads, out_path=out_path, title="Test Report")

    html = out_path.read_text(encoding="utf-8")
    assert "assets.pyecharts.org" not in html
    assert "<script>" in html and "echarts" in html.lower()
    # The vendored bundle is ~1MB; a report with it inlined should be well past that.
    assert len(html.encode("utf-8")) > 500_000


def test_render_backtest_html_report_single_symbol(tmp_path: Path):
    engine = _make_fake_engine("ZN888")
    payloads = {"ZN888": build_symbol_chart_payload(engine)}
    out_path = tmp_path / "single.html"
    render_backtest_html_report(payloads, out_path=out_path)

    html = out_path.read_text(encoding="utf-8")
    assert "ZN888" in html
    assert "function showChart" in html
    assert "report-extra" in html


def test_render_backtest_html_report_no_nested_extra(tmp_path: Path):
    """Regression test for the rejected review: the summary card + trade table
    must live inside the single ``report-extra`` wrapper injected by
    ``_inject_report_extras``; a second nested ``report-extra`` div would stay
    ``display: none`` forever because the CSS rule and JS hide-loop target the
    class name, but the JS only toggles the outer wrapper's inline style.
    """
    engine_a = _make_fake_engine("A888")
    engine_b = _make_fake_engine("RB888")
    payloads = {
        "A888": build_symbol_chart_payload(engine_a),
        "RB888": build_symbol_chart_payload(engine_b),
    }
    out_path = tmp_path / "report.html"
    render_backtest_html_report(payloads, out_path=out_path, title="Test Report")

    html = out_path.read_text(encoding="utf-8")
    # Exactly one report-extra opening tag per symbol; nested wrappers would double the count.
    assert html.count('<div class="report-extra"') == len(payloads)


def test_generate_report_unchanged_when_toggle_off(monkeypatch, memory_db: Path):
    monkeypatch.setitem(STRATEGY_CONFIG, "html_report_enabled", False)
    monkeypatch.setitem(STRATEGY_CONFIG, "trade_freq", "1分钟")

    engine = BacktestEngine(
        symbol="TEST",
        freq="1",
        start_date="2024-01-02",
        end_date="2024-01-02",
        db_path=str(memory_db),
        table_name="test_1M_raw",
    )
    report = engine.run(warmup_bars=10)
    assert "error" not in report
    assert "html_report_path" not in report


def test_generate_report_adds_html_path_when_toggle_on(monkeypatch, memory_db: Path, tmp_path: Path):
    monkeypatch.setitem(STRATEGY_CONFIG, "html_report_enabled", True)
    monkeypatch.setitem(STRATEGY_CONFIG, "html_report_dir", str(tmp_path))
    monkeypatch.setitem(STRATEGY_CONFIG, "trade_freq", "1分钟")

    engine = BacktestEngine(
        symbol="TEST",
        freq="1",
        start_date="2024-01-02",
        end_date="2024-01-02",
        db_path=str(memory_db),
        table_name="test_1M_raw",
    )
    report = engine.run(warmup_bars=10)
    assert "error" not in report
    assert "html_report_path" in report
    assert Path(report["html_report_path"]).exists()


def test_pair_direction_added_to_long_and_short():
    """Positions._close_long/_close_short add the additive direction field."""
    from chan_strategy.positions import Position

    pos_long = Position(name="test_long", symbol="TEST", opens=[])
    pos_long.pos = 1
    pos_long.cost = 100.0
    pos_long.volume = 1
    pos_long.contract_multiplier = 1
    pos_long.bars_since_open = 3
    pos_long.last_open_dt = datetime(2024, 1, 1)
    pos_long._close_long(101.0, datetime(2024, 1, 2), "test")
    assert pos_long.pairs[0]["direction"] == "long"

    pos_short = Position(name="test_short", symbol="TEST", opens=[])
    pos_short.pos = -1
    pos_short.cost = 100.0
    pos_short.volume = 1
    pos_short.contract_multiplier = 1
    pos_short.bars_since_open = 3
    pos_short.last_open_dt = datetime(2024, 1, 1)
    pos_short._close_short(99.0, datetime(2024, 1, 2), "test")
    assert pos_short.pairs[0]["direction"] == "short"


def test_portfolio_report_unchanged_when_toggle_off(monkeypatch, memory_db: Path):
    monkeypatch.setitem(STRATEGY_CONFIG, "html_report_enabled", False)
    monkeypatch.setitem(STRATEGY_CONFIG, "portfolio_risk", "off")
    monkeypatch.setitem(STRATEGY_CONFIG, "trade_freq", "1分钟")

    engine = PortfolioEngine(
        symbols=["TEST"],
        freq="1",
        start_date="2024-01-02",
        end_date="2024-01-02",
        db_path=str(memory_db),
        table_names={"TEST": "test_1M_raw"},
    )
    report = engine.run()
    assert "error" not in report
    assert "html_report_path" not in report


def test_portfolio_report_adds_html_path_when_toggle_on(monkeypatch, memory_db: Path, tmp_path: Path):
    monkeypatch.setitem(STRATEGY_CONFIG, "html_report_enabled", True)
    monkeypatch.setitem(STRATEGY_CONFIG, "html_report_dir", str(tmp_path))
    monkeypatch.setitem(STRATEGY_CONFIG, "portfolio_risk", "off")
    monkeypatch.setitem(STRATEGY_CONFIG, "trade_freq", "1分钟")

    engine = PortfolioEngine(
        symbols=["TEST"],
        freq="1",
        start_date="2024-01-02",
        end_date="2024-01-02",
        db_path=str(memory_db),
        table_names={"TEST": "test_1M_raw"},
    )
    report = engine.run()
    assert "error" not in report
    assert "html_report_path" in report
    assert Path(report["html_report_path"]).exists()
