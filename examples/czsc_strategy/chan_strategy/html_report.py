"""HTML visual backtest report for chan_strategy.

This module builds a reusable, interactive HTML report for every backtest run,
showing candlesticks, 笔 (bi), 中枢 (zhongshu), long/short entry/exit markers,
and a trade/order list table. It is intentionally decoupled from trading logic
so it can be unit-tested with small synthetic fixtures.

The ``xd`` (线段 / duan) payload key is reserved and intentionally left empty
this task; see ``docs/design/a105-html-backtest-visual-report.md`` Background
item 1 for the scope decision.

The chart base is rendered by a vendored copy of czsc 0.9.51's ``kline_pro``
(see ``chan_strategy.vendor.echarts_plot``), because upstream removed both
``czsc.enum`` and ``czsc.utils.echarts_plot`` in czsc 1.0.0rc8.
"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any

from czsc import CZSC
from czsc import Mark, Operate

from chan_strategy.vendor.echarts_plot import kline_pro
from pyecharts.charts import Tab

from chan_strategy.zhongshu import build_zhongshu_from_bis


# Vendored copy of echarts.min.js (Apache-2.0), so generated reports render
# without depending on the pyecharts CDN at view time. See _inline_echarts_js.
_VENDORED_ECHARTS_JS_PATH = Path(__file__).resolve().parent / "vendor" / "echarts.min.js"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_symbol_chart_payload(engine: Any, report: dict[str, Any] | None = None) -> dict[str, Any]:
    """Map a finished :class:`BacktestEngine` to a ``kline_pro``-shaped payload.

    The returned dict mirrors the contract expected by ``kline_pro`` and adds
    the zhongshu overlay, trade table and summary data consumed by the HTML
    renderer.

    :param report: Pre-computed report dict. When omitted, ``engine.generate_report()``
        is called. Pass an explicit report when calling this function from inside
        ``generate_report()`` to avoid recursion.
    """
    czsc_trade: CZSC = engine.czsc_trade
    if report is None:
        report = engine.generate_report()

    pairs: list[dict[str, Any]] = list(engine.strategy.get_combined_trades())

    return {
        "kline": _build_kline_payload(engine.trade_bars),
        "bi": _build_bi_payload(czsc_trade),
        # ``xd`` is intentionally left empty this task (线段 / duan construction
        # is out of scope); the key is reserved so a future task can wire it in
        # without changing report/chart code.
        "xd": [],
        "zs": _build_zs_payload(czsc_trade),
        "bs": _build_bs_payload(pairs),
        "trades_table": pairs,
        "summary": _build_summary(report),
    }


def render_backtest_html_report(
    symbol_payloads: dict[str, dict[str, Any]],
    out_path: Path,
    title: str = "缠论策略回测报告",
) -> Path:
    """Render one multi-tab HTML report for the given symbol payloads.

    Each symbol becomes one tab containing the K-line chart plus a summary card
    and trade list table. The report file is written to ``out_path``.
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    tab = Tab(page_title=title)
    chart_ids: list[str] = []
    extras: dict[str, str] = {}

    for symbol, payload in symbol_payloads.items():
        grid_chart = _build_symbol_grid_chart(payload, title=f"{symbol} {title}")
        tab.add(grid_chart, symbol)
        chart_id = grid_chart.chart_id
        chart_ids.append(chart_id)
        extras[chart_id] = _build_symbol_extra_html(symbol, payload)

    tmp_path = out_path.with_suffix(".tmp.html")
    tab.render(str(tmp_path))

    html = tmp_path.read_text(encoding="utf-8")
    html = _inject_head_style(html)
    html = _inject_report_extras(html, extras)
    html = _inject_tab_sync_script(html)
    html = _inline_echarts_js(html)

    out_path.write_text(html, encoding="utf-8")
    tmp_path.unlink(missing_ok=True)
    return out_path


# ---------------------------------------------------------------------------
# Payload builders
# ---------------------------------------------------------------------------


def _build_kline_payload(trade_bars: list[Any]) -> list[dict[str, Any]]:
    """Return ``kline_pro``-shaped kline records."""
    return [
        {
            "dt": bar.dt,
            "open": float(bar.open),
            "close": float(bar.close),
            "high": float(bar.high),
            "low": float(bar.low),
            "vol": float(bar.vol),
        }
        for bar in trade_bars
    ]


def _build_bi_payload(czsc_trade: CZSC) -> list[dict[str, Any]]:
    """Return ``kline_pro``-shaped 笔 payload.

    Follows the construction pattern in ``CZSC.to_echarts()``: one point per
    confirmed-BI start分型 plus the last BI's end分型, enriched with the
    full field set documented by ``kline_pro``.
    """
    bi_list = getattr(czsc_trade, "bi_list", [])
    if not bi_list:
        return []

    payload: list[dict[str, Any]] = []
    for bi in bi_list:
        fx_a = bi.fx_a
        payload.append(
            {
                "dt": fx_a.dt,
                "fx_mark": _mark_value(fx_a.mark),
                "start_dt": fx_a.dt,
                "end_dt": bi.fx_b.dt,
                "fx_high": float(bi.high),
                "fx_low": float(bi.low),
                "bi": float(fx_a.fx),
            }
        )

    last_bi = bi_list[-1]
    fx_b = last_bi.fx_b
    payload.append(
        {
            "dt": fx_b.dt,
            "fx_mark": _mark_value(fx_b.mark),
            "start_dt": last_bi.fx_a.dt,
            "end_dt": fx_b.dt,
            "fx_high": float(last_bi.high),
            "fx_low": float(last_bi.low),
            "bi": float(fx_b.fx),
        }
    )
    return payload


def _build_zs_payload(czsc_trade: CZSC) -> list[dict[str, Any]]:
    """Return display-mode 中枢 payload for the markArea overlay.

    Uses ``mode="segment"`` for deterministic, non-overlapping historical
    centers rather than the ``mode="recent"`` used by live signal evaluation.
    """
    bi_list = getattr(czsc_trade, "bi_list", [])
    centers = build_zhongshu_from_bis(bi_list, mode="segment")
    return [
        {
            "start_dt": center["bis"][0].fx_a.dt,
            "end_dt": center["bis"][-1].fx_b.dt,
            "zd": float(center["zd"]),
            "zg": float(center["zg"]),
        }
        for center in centers
    ]


def _build_bs_payload(pairs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return buy/sell marker payload from closed trade pairs.

    Each marker also carries a ``label`` field (``"B1"``, ``"S1"``, ``"B2"``, ...)
    so the chart can annotate buy/sell points with a chronological sequence
    number. ``B`` = a buy-side fill (open long / close short); ``S`` = a
    sell-side fill (close long / open short). Buy and sell sequences are
    numbered independently, in chronological order of ``dt``.
    """
    bs: list[dict[str, Any]] = []
    for pair in pairs:
        direction = pair.get("direction")
        if direction == "short":
            open_op = Operate.SO
            close_op = Operate.SE
            open_desc = "开空"
            close_desc = "平空"
        else:
            # Fallback for legacy pairs without direction; treat as long.
            open_op = Operate.LO
            close_op = Operate.LE
            open_desc = "开多"
            close_desc = "平多"

        bs.append(
            {
                "dt": pair["open_dt"],
                "price": float(pair["open_price"]),
                "op": open_op,
                "op_desc": open_desc,
            }
        )
        bs.append(
            {
                "dt": pair["close_dt"],
                "price": float(pair["close_price"]),
                "op": close_op,
                "op_desc": close_desc,
            }
        )

    bs.sort(key=lambda row: row["dt"])
    buy_ops = {Operate.LO, Operate.SE}
    b_count = 0
    s_count = 0
    for row in bs:
        if row["op"] in buy_ops:
            b_count += 1
            row["label"] = f"B{b_count}"
        else:
            s_count += 1
            row["label"] = f"S{s_count}"
    return bs


def _build_summary(report: dict[str, Any]) -> dict[str, Any]:
    """Return a per-symbol summary card sourced only from existing report fields."""
    return {
        "symbol": report.get("symbol", ""),
        "period": report.get("period", ""),
        "total_trades": report.get("total_trades", 0),
        "win_rate": report.get("win_rate", 0.0),
        "total_return_pct": report.get("total_return_pct", 0.0),
        "max_drawdown_pct": report.get("max_drawdown_pct", 0.0),
        "sharpe_ratio": report.get("sharpe_ratio", 0.0),
    }


# ---------------------------------------------------------------------------
# Chart builders
# ---------------------------------------------------------------------------


def _build_symbol_grid_chart(payload: dict[str, Any], title: str) -> Any:
    """Build a pyecharts Grid chart for one symbol with zhongshu overlay."""
    kline = payload["kline"]
    bi = payload["bi"]
    xd = payload["xd"]
    bs = payload["bs"]
    zs = payload["zs"]

    grid_chart = kline_pro(
        kline=kline,
        bi=bi,
        xd=xd,
        bs=bs,
        title=title,
    )

    if zs:
        dts = [row["dt"] for row in kline]
        markarea_series = _zhongshu_markarea_series(zs, dts)
        grid_chart.options["series"].append(markarea_series)

    if bs:
        label_series = _bs_label_series(bs)
        grid_chart.options["series"].append(label_series)

    return grid_chart


def _zhongshu_markarea_series(zs_payload: list[dict[str, Any]], _dts: list[Any]) -> dict[str, Any]:
    """Build an echarts series dict that renders zhongshu boxes via markArea."""
    data: list[list[dict[str, Any]]] = []
    for z in zs_payload:
        data.append(
            [
                {"xAxis": z["start_dt"], "yAxis": z["zd"]},
                {"xAxis": z["end_dt"], "yAxis": z["zg"]},
            ]
        )

    return {
        "name": "ZS",
        "type": "line",
        "xAxisIndex": 0,
        "yAxisIndex": 0,
        "data": [],
        "markArea": {
            "silent": True,
            "data": data,
            "itemStyle": {
                "color": "rgba(255, 215, 0, 0.15)",
                "borderColor": "#FFD700",
                "borderWidth": 1,
            },
            "label": {"show": False},
        },
    }


# ---------------------------------------------------------------------------
# HTML builders / post-render injection
# ---------------------------------------------------------------------------


def _bs_label_series(bs_payload: list[dict[str, Any]]) -> dict[str, Any]:
    """Build an overlay series showing B/S sequence numbers via ``markPoint``.

    ``kline_pro``'s own long/short markers render as colored diamond/triangle
    icons with tooltip-only detail (no visible on-chart text). This attaches
    ECharts' ``markPoint`` feature — the standard, well-supported mechanism
    for annotating specific points on a chart with a label — to an empty
    dummy series, mirroring how ``_zhongshu_markarea_series`` attaches
    ``markArea`` to an empty ``"line"`` series rather than a real data series.

    An earlier version used a synthetic scatter series with ``symbol: "none"``
    to draw label-only text at each (dt, price) point. That silently failed
    in the vendored echarts build: the point still rendered as a default
    circle marker (colored per direction, so buy/sell dots were visible) but
    the attached label text never appeared — a known ECharts compatibility
    gap between "no symbol" and "label anchored to that symbol". ``markPoint``
    with an explicit ``pin`` symbol does not depend on that mechanism.
    """
    buy_ops = {Operate.LO, Operate.SE}
    mark_data = []
    for row in bs_payload:
        is_buy = row["op"] in buy_ops
        label = row.get("label", "")
        mark_data.append(
            {
                "name": label,
                "coord": [row["dt"], row["price"]],
                "value": label,
                "symbol": "pin",
                "symbolSize": 32,
                "itemStyle": {"color": "#ff461f" if is_buy else "#00aa3b"},
                "label": {
                    "show": True,
                    "color": "#fff",
                    "fontSize": 10,
                    "fontWeight": "bold",
                },
            }
        )
    return {
        "name": "BS_LABEL",
        "type": "line",
        "xAxisIndex": 0,
        "yAxisIndex": 0,
        "data": [],
        "markPoint": {
            "silent": True,
            "data": mark_data,
        },
    }


def _build_symbol_extra_html(symbol: str, payload: dict[str, Any]) -> str:
    """Return the HTML block (summary card + trade table) for one symbol tab.

    The caller (``_inject_report_extras``) wraps this content in the single
    ``report-extra`` div that the tab-sync script shows/hides. Do not add a
    second nested ``report-extra`` wrapper here: the CSS hides every element
    with that class, and the JS only toggles the outer wrapper's inline style.
    """
    summary_html = _summary_card_html(symbol, payload["summary"])
    table_html = _trades_table_html(payload["trades_table"])
    return f"""
{summary_html}
{table_html}
"""


def _summary_card_html(symbol: str, summary: dict[str, Any]) -> str:
    """Render a per-symbol summary stat card."""
    return f"""
<div class="summary-card">
    <h3>{symbol} 回测摘要</h3>
    <p>
        <span>总交易次数: <strong>{summary['total_trades']}</strong></span>
        <span>胜率: <strong>{summary['win_rate'] * 100:.2f}%</strong></span>
        <span>总收益: <strong>{summary['total_return_pct']:.2f}%</strong></span>
        <span>最大回撤: <strong>{summary['max_drawdown_pct']:.2f}%</strong></span>
        <span>夏普比率: <strong>{summary['sharpe_ratio']:.2f}</strong></span>
        <span>周期: <strong>{summary['period']}</strong></span>
    </p>
    <p style="margin:6px 0 0;color:#999;font-size:12px;">
        口径说明：本报告所有中枢均为<strong>笔中枢</strong>（由笔构建；czsc 1.0.0rc8
        不提供线段中枢，笔中枢与线段中枢级别不同，不可混称）；K 线周期仅为观察窗口，不代表递归级别。
    </p>
</div>
"""


def _trades_table_html(trades_table: list[dict[str, Any]]) -> str:
    """Render the 成交订单清单 as a plain HTML table."""
    columns = [
        ("strategy", "子策略"),
        ("direction", "方向"),
        ("open_dt", "开仓时间"),
        ("open_price", "开仓价"),
        ("close_dt", "平仓时间"),
        ("close_price", "平仓价"),
        ("volume", "成交量"),
        ("pnl_pct", "盈亏%"),
        ("pnl_currency", "盈亏金额"),
        ("bars_held", "持有K线"),
        ("reason", "平仓原因"),
    ]

    rows_html = ""
    for pair in trades_table:
        cells = ""
        for key, _label in columns:
            value = pair.get(key, "")
            if key in ("open_dt", "close_dt") and isinstance(value, datetime):
                value = value.strftime("%Y-%m-%d %H:%M")
            elif key == "pnl_pct":
                value = f"{float(value) * 100:.2f}%"
            elif key in ("open_price", "close_price", "pnl_currency"):
                value = f"{float(value):.2f}"
            elif key == "direction":
                value = str(value) if value else "long"
            cells += f"<td>{value}</td>"
        rows_html += f"<tr>{cells}</tr>\n"

    if not rows_html:
        rows_html = '<tr><td colspan="11" style="text-align:center">无成交记录</td></tr>'

    header = "".join(f"<th>{label}</th>" for _key, label in columns)
    return f"""
<div class="trade-table-wrapper">
    <h4>成交订单清单</h4>
    <table class="trade-table">
        <thead><tr>{header}</tr></thead>
        <tbody>
            {rows_html}
        </tbody>
    </table>
</div>
"""


def _inline_echarts_js(html: str) -> str:
    """Replace pyecharts' CDN <script src="...echarts.min.js"> with an inline copy.

    pyecharts renders a <script src="https://assets.pyecharts.org/..."> tag by
    default, so the chart never draws when the viewer has no route to that CDN
    (offline, corporate proxy, GFW-adjacent networks, etc.) — only the
    plain-HTML summary card/trade table would render. Inlining a vendored copy
    makes each report a genuinely self-contained file. Falls back to leaving
    the CDN tag untouched (with a one-line comment) if the vendored asset is
    missing, rather than failing report generation outright.
    """
    if not _VENDORED_ECHARTS_JS_PATH.exists():
        return html.replace(
            "</head>",
            "<!-- vendored echarts.min.js not found; falling back to CDN script tag -->\n</head>",
            1,
        )
    js_content = _VENDORED_ECHARTS_JS_PATH.read_text(encoding="utf-8")
    # Use a callable replacement, not an f-string: a plain string replacement
    # would have re.sub reinterpret literal backslash sequences inside the
    # minified JS (e.g. "\d") as regex backreferences and raise re.error.
    return re.sub(
        r'<script[^>]*src="[^"]*echarts\.min\.js"[^>]*></script>',
        lambda _match: f"<script>{js_content}</script>",
        html,
        count=1,
    )


def _inject_head_style(html: str) -> str:
    """Inject report-extra CSS into the HTML head."""
    style = """
<style>
.report-extra {
    display: none;
    padding: 16px 24px;
    background-color: #fafafa;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
}
.summary-card {
    margin-bottom: 16px;
    padding: 12px;
    background-color: #fff;
    border: 1px solid #e0e0e0;
    border-radius: 4px;
}
.summary-card h3 {
    margin: 0 0 8px 0;
    font-size: 16px;
}
.summary-card span {
    display: inline-block;
    margin-right: 20px;
    font-size: 13px;
    color: #333;
}
.trade-table-wrapper {
    background-color: #fff;
    border: 1px solid #e0e0e0;
    border-radius: 4px;
    padding: 12px;
}
.trade-table-wrapper h4 {
    margin: 0 0 10px 0;
    font-size: 14px;
}
.trade-table {
    border-collapse: collapse;
    width: 100%;
    font-size: 12px;
}
.trade-table th, .trade-table td {
    border: 1px solid #ddd;
    padding: 6px 8px;
    text-align: left;
}
.trade-table th {
    background-color: #f2f2f2;
    font-weight: 600;
}
.trade-table tr:nth-child(even) {
    background-color: #f9f9f9;
}
</style>
"""
    head_close = html.find("</head>")
    if head_close == -1:
        return html + style
    return html[:head_close] + style + html[head_close:]


def _inject_report_extras(html: str, extras: dict[str, str]) -> str:
    """Insert a report-extra block after each chart-container div."""
    for chart_id, extra_html in extras.items():
        pattern = re.compile(
            rf'(<div id="{re.escape(chart_id)}" class="chart-container"[^>]*></div>)'
        )
        html = pattern.sub(
            rf'\1\n<div class="report-extra" data-chart-id="{chart_id}">{extra_html}</div>',
            html,
            count=1,
        )
    return html


def _inject_tab_sync_script(html: str) -> str:
    """Add a script that keeps report-extra blocks in sync with tab switching."""
    script = """
<script>
(function() {
    var origShowChart = window.showChart;
    window.showChart = function(evt, chartID) {
        if (typeof origShowChart === "function") {
            origShowChart(evt, chartID);
        }
        var extras = document.getElementsByClassName("report-extra");
        for (var i = 0; i < extras.length; i++) {
            extras[i].style.display = "none";
        }
        var active = document.querySelector('.report-extra[data-chart-id="' + chartID + '"]');
        if (active) {
            active.style.display = "block";
        }
    };
    var extras = document.getElementsByClassName("report-extra");
    if (extras.length > 0) {
        extras[0].style.display = "block";
    }
})();
</script>
"""
    body_close = html.rfind("</body>")
    if body_close == -1:
        return html + script
    return html[:body_close] + script + html[body_close:]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mark_value(mark: Mark) -> str:
    """Return the single-letter mark value used by ``kline_pro``."""
    value = getattr(mark, "value", str(mark))
    if value == "底分型":
        return "d"
    if value == "顶分型":
        return "g"
    # Defensive fallback for enum objects that compare equal to the string.
    if "D" in str(mark).upper() or str(mark).upper() == "底分型":
        return "d"
    return "g"


def default_html_report_dir() -> Path:
    """Return the default directory for HTML backtest reports."""
    return Path(__file__).resolve().parents[1] / "diagnostics"
