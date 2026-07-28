"""Vendored ``czsc.utils.echarts_plot.kline_pro`` for czsc 1.0 compatibility.

<!-- RESEARCH-ONLY / NOT PROMOTION EVIDENCE -->
This module is a vendored copy of the ``kline_pro`` function from czsc 0.9.51,
which was removed in czsc 1.0. The vendored implementation is confined to the
minimum functionality required by ``chan_strategy.html_report``:

- ``kline_pro`` returning a pyecharts ``Grid`` chart with K-line, volume, MACD,
  笔/分型 overlays, and long/short operation markers.
- The simple ``SMA`` and ``MACD`` helpers originally imported from
  ``czsc.utils.ta`` (also removed in czsc 1.0).

Changes from the original 0.9.51 source:
- ``Operate`` is imported from the top-level ``czsc`` namespace (czsc 1.0 no
  longer exposes it under ``czsc.objects`` or ``czsc.enum``).
- Only ``kline_pro``, ``SMA``, and ``MACD`` are kept; other plot helpers are
  omitted because ``chan_strategy`` does not use them.

Original source license: MIT (czsc project, https://github.com/waditu/czsc).
"""
from __future__ import annotations


import numpy as np
from pyecharts import options as opts
from pyecharts.charts import Bar, Grid, Kline, Line, Scatter
from pyecharts.commons.utils import JsCode

from czsc import Operate


def SMA(close: np.ndarray, timeperiod: int = 5) -> np.ndarray:
    """简单移动平均（兼容 czsc 0.9.51 ``utils.ta.SMA``）。"""
    res = []
    for i in range(len(close)):
        if i < timeperiod:
            seq = close[0 : i + 1]
        else:
            seq = close[i - timeperiod + 1 : i + 1]
        res.append(seq.mean())
    return np.array(res, dtype=np.double).round(4)


def EMA(close: np.ndarray, timeperiod: int = 5) -> np.ndarray:
    """指数移动平均（兼容 czsc 0.9.51 ``utils.ta.EMA``）。"""
    res = []
    for i in range(len(close)):
        if i < 1:
            res.append(close[i])
        else:
            ema = (2 * close[i] + res[i - 1] * (timeperiod - 1)) / (timeperiod + 1)
            res.append(ema)
    return np.array(res, dtype=np.double).round(4)


def MACD(
    close: np.ndarray,
    fastperiod: int = 12,
    slowperiod: int = 26,
    signalperiod: int = 9,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """MACD 异同移动平均线（兼容 czsc 0.9.51 ``utils.ta.MACD``）。"""
    ema12 = EMA(close, timeperiod=fastperiod)
    ema26 = EMA(close, timeperiod=slowperiod)
    diff = ema12 - ema26
    dea = EMA(diff, timeperiod=signalperiod)
    macd = (diff - dea) * 2
    return diff.round(4), dea.round(4), macd.round(4)


def kline_pro(
    kline: list[dict],
    fx: list[dict] | None = None,
    bi: list[dict] | None = None,
    xd: list[dict] | None = None,
    bs: list[dict] | None = None,
    title: str = "缠中说禅K线分析",
    t_seq: list[int] | None = None,
    width: str = "1400px",
    height: str = "580px",
) -> Grid:
    """绘制缠中说禅K线分析结果。

    参数与返回值语义与 czsc 0.9.51 的 ``czsc.utils.echarts_plot.kline_pro``
    保持一致，确保 ``chan_strategy.html_report`` 升级后渲染结果不变。
    """
    fx = fx or []
    bi = bi or []
    xd = xd or []
    bs = bs or []

    bg_color = "#1f212d"
    up_color = "#F9293E"
    down_color = "#00aa3b"

    init_opts = opts.InitOpts(
        bg_color=bg_color,
        width=width,
        height=height,
        animation_opts=opts.AnimationOpts(False),
    )
    title_opts = opts.TitleOpts(
        title=title,
        pos_top="1%",
        title_textstyle_opts=opts.TextStyleOpts(color=up_color, font_size=20),
        subtitle_textstyle_opts=opts.TextStyleOpts(color=down_color, font_size=12),
    )

    label_show_opts = opts.LabelOpts(is_show=True)
    label_not_show_opts = opts.LabelOpts(is_show=False)
    legend_not_show_opts = opts.LegendOpts(is_show=False)
    red_item_style = opts.ItemStyleOpts(color=up_color)
    green_item_style = opts.ItemStyleOpts(color=down_color)
    k_style_opts = opts.ItemStyleOpts(
        color=up_color,
        color0=down_color,
        border_color=up_color,
        border_color0=down_color,
        opacity=0.8,
    )

    legend_opts = opts.LegendOpts(
        is_show=True,
        pos_top="1%",
        pos_left="30%",
        item_width=14,
        item_height=8,
        textstyle_opts=opts.TextStyleOpts(font_size=12, color="#0e99e2"),
    )
    brush_opts = opts.BrushOpts(
        tool_box=["rect", "polygon", "keep", "clear"],
        x_axis_index="all",
        brush_link="all",
        out_of_brush={"colorAlpha": 0.1},
        brush_type="lineX",
    )

    axis_pointer_opts = opts.AxisPointerOpts(is_show=True, link=[{"xAxisIndex": "all"}])

    dz_inside = opts.DataZoomOpts(
        False, "inside", xaxis_index=[0, 1, 2], range_start=80, range_end=100
    )
    dz_slider = opts.DataZoomOpts(
        True,
        "slider",
        xaxis_index=[0, 1, 2],
        pos_top="96%",
        pos_bottom="0%",
        range_start=80,
        range_end=100,
    )

    yaxis_opts = opts.AxisOpts(
        is_scale=True,
        min_="dataMin",
        max_="dataMax",
        splitline_opts=opts.SplitLineOpts(is_show=False),
        axislabel_opts=opts.LabelOpts(color="#c7c7c7", font_size=8, position="inside"),
    )

    grid0_xaxis_opts = opts.AxisOpts(
        type_="category",
        grid_index=0,
        axislabel_opts=label_not_show_opts,
        split_number=20,
        min_="dataMin",
        max_="dataMax",
        is_scale=True,
        boundary_gap=False,
        splitline_opts=opts.SplitLineOpts(is_show=False),
        axisline_opts=opts.AxisLineOpts(is_on_zero=False),
    )

    tool_tip_opts = opts.TooltipOpts(
        trigger="axis",
        axis_pointer_type="cross",
        background_color="rgba(245, 245, 245, 0.8)",
        border_width=1,
        border_color="#ccc",
        position=JsCode(
            """
            function (pos, params, el, elRect, size) {
                var obj = {top: 10};
                obj[['left', 'right'][+(pos[0] < size.viewSize[0] / 2)]] = 30;
                return obj;
            }
            """
        ),
        textstyle_opts=opts.TextStyleOpts(color="#000"),
    )

    dts = [x["dt"] for x in kline]
    k_data = [
        opts.CandleStickItem(name=i, value=[x["open"], x["close"], x["low"], x["high"]])
        for i, x in enumerate(kline)
    ]

    vol = []
    for i, row in enumerate(kline):
        item_style = red_item_style if row["close"] > row["open"] else green_item_style
        bar = opts.BarItem(
            name=i,
            value=row["vol"],
            itemstyle_opts=item_style,
            label_opts=label_not_show_opts,
        )
        vol.append(bar)

    close = np.array([x["close"] for x in kline], dtype=np.double)
    diff, dea, macd = MACD(close)
    macd_bar = []
    for i, v in enumerate(macd.tolist()):
        item_style = red_item_style if v > 0 else green_item_style
        bar = opts.BarItem(
            name=i,
            value=round(v, 4),
            itemstyle_opts=item_style,
            label_opts=label_not_show_opts,
        )
        macd_bar.append(bar)

    diff = diff.round(4)
    dea = dea.round(4)

    chart_k = Kline()
    chart_k.add_xaxis(xaxis_data=dts)
    chart_k.add_yaxis(series_name="Kline", y_axis=k_data, itemstyle_opts=k_style_opts)

    chart_k.set_global_opts(
        legend_opts=legend_opts,
        datazoom_opts=[dz_inside, dz_slider],
        yaxis_opts=yaxis_opts,
        tooltip_opts=tool_tip_opts,
        axispointer_opts=axis_pointer_opts,
        brush_opts=brush_opts,
        title_opts=title_opts,
        xaxis_opts=grid0_xaxis_opts,
    )

    if bs:
        long_opens = {"i": [], "val": []}
        long_exits = {"i": [], "val": []}
        short_opens = {"i": [], "val": []}
        short_exits = {"i": [], "val": []}

        for op in bs:
            _dt = op["dt"]
            _price = round(op["price"], 4)
            _info = f"{op['op_desc']} - 价格{_price}"

            if op["op"] in {Operate.LO}:
                long_opens["i"].append(_dt)
                long_opens["val"].append([_price, _info])

            if op["op"] in {Operate.LE}:
                long_exits["i"].append(_dt)
                long_exits["val"].append([_price, _info])

            if op["op"] in {Operate.SO}:
                short_opens["i"].append(_dt)
                short_opens["val"].append([_price, _info])

            if op["op"] in {Operate.SE}:
                short_exits["i"].append(_dt)
                short_exits["val"].append([_price, _info])

        chart_lo = (
            Scatter()
            .add_xaxis(xaxis_data=long_opens["i"])
            .add_yaxis(
                series_name="多头操作",
                y_axis=long_opens["val"],
                symbol_size=25,
                symbol="diamond",
                label_opts=opts.LabelOpts(is_show=False),
                itemstyle_opts=opts.ItemStyleOpts(color="#ff461f"),
                tooltip_opts=opts.TooltipOpts(
                    textstyle_opts=opts.TextStyleOpts(font_size=12),
                    formatter=JsCode("function (params) {return params.value[2];}"),
                ),
            )
        )
        chart_le = (
            Scatter()
            .add_xaxis(xaxis_data=long_exits["i"])
            .add_yaxis(
                series_name="多头操作",
                y_axis=long_exits["val"],
                symbol_size=25,
                symbol="diamond",
                label_opts=opts.LabelOpts(is_show=False),
                itemstyle_opts=opts.ItemStyleOpts(color="#afdd22"),
                tooltip_opts=opts.TooltipOpts(
                    textstyle_opts=opts.TextStyleOpts(font_size=12),
                    formatter=JsCode("function (params) {return params.value[2];}"),
                ),
            )
        )
        chart_so = (
            Scatter()
            .add_xaxis(xaxis_data=short_opens["i"])
            .add_yaxis(
                series_name="空头订单",
                y_axis=short_opens["val"],
                symbol_size=25,
                symbol="triangle",
                label_opts=opts.LabelOpts(is_show=False),
                itemstyle_opts=opts.ItemStyleOpts(color="#ff461f"),
                tooltip_opts=opts.TooltipOpts(
                    textstyle_opts=opts.TextStyleOpts(font_size=12),
                    formatter=JsCode("function (params) {return params.value[2];}"),
                ),
            )
        )
        chart_se = (
            Scatter()
            .add_xaxis(xaxis_data=short_exits["i"])
            .add_yaxis(
                series_name="空头订单",
                y_axis=short_exits["val"],
                symbol_size=25,
                symbol="triangle",
                label_opts=opts.LabelOpts(is_show=False),
                itemstyle_opts=opts.ItemStyleOpts(color="#afdd22"),
                tooltip_opts=opts.TooltipOpts(
                    textstyle_opts=opts.TextStyleOpts(font_size=12),
                    formatter=JsCode("function (params) {return params.value[2];}"),
                ),
            )
        )

        chart_k = chart_k.overlap(chart_lo)
        chart_k = chart_k.overlap(chart_le)
        chart_k = chart_k.overlap(chart_so)
        chart_k = chart_k.overlap(chart_se)

    chart_ma = Line()
    chart_ma.add_xaxis(xaxis_data=dts)
    if not t_seq:
        t_seq = [5, 13, 21]

    ma_keys = {}
    for t in t_seq:
        ma_keys[f"MA{t}"] = SMA(close, timeperiod=t)

    for _i, (name, ma) in enumerate(ma_keys.items()):
        chart_ma.add_yaxis(
            series_name=name,
            y_axis=ma,
            is_smooth=True,
            symbol_size=0,
            label_opts=label_not_show_opts,
            linestyle_opts=opts.LineStyleOpts(opacity=0.8, width=1),
        )

    chart_ma.set_global_opts(xaxis_opts=grid0_xaxis_opts, legend_opts=legend_not_show_opts)
    chart_k = chart_k.overlap(chart_ma)

    if fx:
        fx_dts = [x["dt"] for x in fx]
        fx_val = [round(x["fx"], 2) for x in fx]
        chart_fx = Line()
        chart_fx.add_xaxis(fx_dts)
        chart_fx.add_yaxis(
            series_name="FX",
            y_axis=fx_val,
            symbol="circle",
            symbol_size=6,
            label_opts=label_show_opts,
            itemstyle_opts=opts.ItemStyleOpts(color="rgba(152, 147, 193, 1.0)"),
        )

        chart_fx.set_global_opts(xaxis_opts=grid0_xaxis_opts, legend_opts=legend_not_show_opts)
        chart_k = chart_k.overlap(chart_fx)

    if bi:
        bi_dts = [x["dt"] for x in bi]
        bi_val = [round(x["bi"], 2) for x in bi]
        chart_bi = Line()
        chart_bi.add_xaxis(bi_dts)
        chart_bi.add_yaxis(
            series_name="BI",
            y_axis=bi_val,
            symbol="diamond",
            symbol_size=10,
            label_opts=label_show_opts,
            itemstyle_opts=opts.ItemStyleOpts(color="rgba(184, 117, 225, 1.0)"),
            linestyle_opts=opts.LineStyleOpts(width=1.5),
        )

        chart_bi.set_global_opts(xaxis_opts=grid0_xaxis_opts, legend_opts=legend_not_show_opts)
        chart_k = chart_k.overlap(chart_bi)

    if xd:
        xd_dts = [x["dt"] for x in xd]
        xd_val = [x["xd"] for x in xd]
        chart_xd = Line()
        chart_xd.add_xaxis(xd_dts)
        chart_xd.add_yaxis(
            series_name="XD",
            y_axis=xd_val,
            symbol="triangle",
            symbol_size=10,
            itemstyle_opts=opts.ItemStyleOpts(color="rgba(37, 141, 54, 1.0)"),
        )

        chart_xd.set_global_opts(xaxis_opts=grid0_xaxis_opts, legend_opts=legend_not_show_opts)
        chart_k = chart_k.overlap(chart_xd)

    chart_vol = Bar()
    chart_vol.add_xaxis(dts)
    chart_vol.add_yaxis(series_name="Volume", y_axis=vol, bar_width="60%")
    chart_vol.set_global_opts(
        xaxis_opts=opts.AxisOpts(
            type_="category",
            grid_index=1,
            boundary_gap=False,
            axislabel_opts=opts.LabelOpts(is_show=True, font_size=8, color="#9b9da9"),
        ),
        yaxis_opts=yaxis_opts,
        legend_opts=legend_not_show_opts,
    )

    chart_macd = Bar()
    chart_macd.add_xaxis(dts)
    chart_macd.add_yaxis(series_name="MACD", y_axis=macd_bar, bar_width="60%")
    chart_macd.set_global_opts(
        xaxis_opts=opts.AxisOpts(
            type_="category",
            grid_index=2,
            axislabel_opts=opts.LabelOpts(is_show=False),
            splitline_opts=opts.SplitLineOpts(is_show=False),
        ),
        yaxis_opts=opts.AxisOpts(
            grid_index=2,
            split_number=4,
            axisline_opts=opts.AxisLineOpts(is_on_zero=False),
            axistick_opts=opts.AxisTickOpts(is_show=False),
            splitline_opts=opts.SplitLineOpts(is_show=False),
            axislabel_opts=opts.LabelOpts(is_show=True, color="#c7c7c7"),
        ),
        legend_opts=opts.LegendOpts(is_show=False),
    )

    line = Line()
    line.add_xaxis(dts)
    line.add_yaxis(
        series_name="DIFF",
        y_axis=diff,
        label_opts=label_not_show_opts,
        is_symbol_show=False,
        linestyle_opts=opts.LineStyleOpts(opacity=0.8, width=1.0, color="#da6ee8"),
    )
    line.add_yaxis(
        series_name="DEA",
        y_axis=dea,
        label_opts=label_not_show_opts,
        is_symbol_show=False,
        linestyle_opts=opts.LineStyleOpts(opacity=0.8, width=1.0, color="#39afe6"),
    )

    chart_macd = chart_macd.overlap(line)

    grid0_opts = opts.GridOpts(pos_left="0%", pos_right="1%", pos_top="12%", height="58%")
    grid1_opts = opts.GridOpts(pos_left="0%", pos_right="1%", pos_top="74%", height="8%")
    grid2_opts = opts.GridOpts(pos_left="0%", pos_right="1%", pos_top="86%", height="10%")

    grid_chart = Grid(init_opts)
    grid_chart.add(chart_k, grid_opts=grid0_opts)
    grid_chart.add(chart_vol, grid_opts=grid1_opts)
    grid_chart.add(chart_macd, grid_opts=grid2_opts)
    return grid_chart
