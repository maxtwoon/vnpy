"""HTTP fixtures verify payloads, units, restrictions and safe failures."""

import json
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
import requests

from vnpy_datasource import providers_http as http


def response(payload: Any = None, *, text: str | None = None, status: int = 200) -> requests.Response:
    result = requests.Response()
    result.status_code = status
    result.encoding = "utf-8"
    result._content = json.dumps(payload).encode() if text is None else text.encode("gbk")
    return result


@pytest.fixture
def context() -> dict[str, Any]:
    return {"root": "unused", "db": {"sources": {}}, "secrets": {}, "timeout": 5, "proxy_url": None}


@pytest.fixture
def transport(monkeypatch: pytest.MonkeyPatch) -> tuple[list[Any], list[dict[str, Any]]]:
    queue: list[Any] = []
    calls: list[dict[str, Any]] = []

    class Session:
        def __init__(self) -> None:
            self.trust_env = True
            self.headers: dict[str, str] = {}

        def __enter__(self) -> "Session":
            return self

        def __exit__(self, *args: Any) -> None:
            pass

        def request(self, method: str, url: str, **kwargs: Any) -> requests.Response:
            calls.append({"method": method, "url": url, "trust_env": self.trust_env, **kwargs})
            assert queue, "Unexpected HTTP call"
            item = queue.pop(0)
            if isinstance(item, Exception):
                raise item
            return item

    monkeypatch.setattr(http.requests, "Session", Session)
    return queue, calls


def tencent_line(code: str, name: str = "fixture") -> str:
    parts = ["0"] * 40
    for index, value in {1: name, 2: code[2:], 3: "12.5", 4: "12", 5: "12.2", 6: "123",
                         30: "20260915145958", 33: "12.8", 34: "12.1", 37: "45.6"}.items():
        parts[index] = value
    return f'v_{code}="' + "~".join(parts) + '";'


def ts_response(fields: list[str], rows: list[list[Any]]) -> requests.Response:
    return response({"code": 0, "data": {"fields": fields, "items": rows}})


def ts_context(context: dict[str, Any]) -> dict[str, Any]:
    context["secrets"] = {"TUSHARE_TOKEN": "test-secret-value", "TUSHARE_API_URL": "https://fixture.example/api"}
    return context


def history_params(**extra: Any) -> dict[str, Any]:
    return {"symbol": "600519.SSE", "start": "2026-09-01", "end": "2026-09-15", **extra}


def test_tencent_batch_converts_native_units_and_matches_symbols(transport: Any, context: dict[str, Any]) -> None:
    queue, calls = transport
    queue.append(response(text=tencent_line("sh600519") + tencent_line("sz159915")))
    result = http.query("tencent", "quote_realtime_batch", {"symbols": ["600519.SSE", "159915.SZSE"]}, context)
    assert [row["symbol"] for row in result["records"]] == ["600519.SSE", "159915.SZSE"]
    assert result["records"][0]["volume"] == 12300
    assert result["records"][0]["turnover"] == 456000
    assert result["records"][0]["datetime"] == "2026-09-15T14:59:58+08:00"
    assert calls[0]["url"] == "https://qt.gtimg.cn/q=sh600519,sz159915"
    assert calls[0]["trust_env"] is False
    assert calls[0]["allow_redirects"] is False
    assert calls[0]["timeout"] == 5


def test_tencent_incomplete_batch_is_visible(transport: Any, context: dict[str, Any]) -> None:
    queue, _ = transport
    queue.append(response(text=tencent_line("sh600519")))
    with pytest.raises(http.ProviderError, match="^incomplete_quotes$"):
        http.query("tencent", "quote_realtime_batch", {"symbols": ["600519.SSE", "159915.SZSE"]}, context)


def test_sina_preserves_share_and_yuan_units_with_referer(transport: Any, context: dict[str, Any]) -> None:
    queue, calls = transport
    parts = ["0"] * 32
    for index, value in {0: "测试", 1: "12", 2: "11", 3: "13", 4: "14", 5: "10",
                         8: "1200", 9: "15000", 30: "2026-09-15", 31: "15:00:00"}.items():
        parts[index] = value
    queue.append(response(text='var hq_str_sh600519="' + ",".join(parts) + '";'))
    result = http.query("sina", "quote_realtime", {"symbol": "600519.SSE"}, context)
    assert result["records"][0]["name"] == "测试"
    assert result["records"][0]["volume"] == 1200
    assert result["records"][0]["turnover"] == 15000
    assert calls[0]["headers"]["Referer"] == "https://finance.sina.com.cn"


def test_xueqiu_missing_amount_stays_missing(transport: Any, context: dict[str, Any]) -> None:
    queue, _ = transport
    stamp = int(datetime(2026, 9, 15, 15, tzinfo=timezone(timedelta(hours=8))).timestamp() * 1000)
    queue.append(response({"data": [{"symbol": "SH600519", "current": 1500, "timestamp": stamp}]}))
    result = http.query("xueqiu", "quote_realtime_batch", {"symbol": "600519.SSE"}, context)
    assert result["records"][0]["last_price"] == 1500
    assert "turnover" not in result["records"][0]
    assert "turnover" in result["metadata"]["missing_fields"]
    assert "volume" in result["metadata"]["missing_fields"]


def test_intraday_keeps_price_series_without_fabricated_ohlcv(transport: Any, context: dict[str, Any]) -> None:
    queue, _ = transport
    queue.append(response({"code": 0, "data": {"sh600519": {"data": {
        "date": "20260915", "data": ["0930 1500.0 100", "0931 1501.0 250"],
    }}}}))
    result = http.query("tencent", "minute_bars", {"symbol": "600519.SSE"}, context)
    assert result["kind"] == "intraday"
    assert result["metadata"]["historical_ohlcv"] is False
    assert result["records"][1]["cumulative_volume"] == 250
    assert result["records"][1]["price"] == 1501
    assert not ({"open", "high", "low", "close", "volume"} & result["records"][1].keys())


def test_intraday_cannot_satisfy_a_different_historical_day(transport: Any, context: dict[str, Any]) -> None:
    queue, _ = transport
    queue.append(response({"code": 0, "data": {"sh600519": {"data": {
        "date": "20260915", "data": ["0930 1500.0 100"],
    }}}}))
    result = http.query("tencent", "minute_bars", history_params(end="2026-09-14"), context)
    assert result["records"] == []
    assert result["metadata"]["provider_session"] == "2026-09-15"


@pytest.mark.parametrize("params,code", [
    ({"symbol": "sh600519&secret=x"}, "invalid_symbol"),
    ({"symbol": "600519.SSE", "url": "https://other.example"}, "unsupported_parameter"),
    ({"symbol": "600519.SSE", "asset": "index"}, "unsupported_asset"),
])
def test_quote_inputs_are_bounded_before_http(params: dict[str, Any], code: str, transport: Any, context: dict[str, Any]) -> None:
    with pytest.raises(http.ProviderError, match=f"^{code}$"):
        http.query("tencent", "quote_realtime_batch", params, context)
    assert transport[1] == []


@pytest.mark.parametrize("owner", ["tencent", "eastmoney"])
def test_final_url_blocking_checks_source_and_shared_ledger(owner: str, transport: Any, context: dict[str, Any]) -> None:
    context["db"]["sources"][owner] = {"endpoint_status": {"qt.gtimg.cn/q=": {"status": "blocked"}}}
    with pytest.raises(http.ProviderError, match="^blocked_endpoint$"):
        http.query("tencent", "quote_realtime_batch", {"symbol": "600519.SSE"}, context)
    assert transport[1] == []


def test_redirect_is_not_followed_with_credentials(transport: Any, context: dict[str, Any]) -> None:
    queue, calls = transport
    queue.append(response(status=302))
    with pytest.raises(http.ProviderError, match="^unexpected_redirect$"):
        http.query("tushare", "daily_ohlcv", history_params(), ts_context(context))
    assert len(calls) == 1
    assert calls[0]["allow_redirects"] is False


def test_tushare_daily_converts_lots_and_thousands_of_yuan(transport: Any, context: dict[str, Any]) -> None:
    queue, calls = transport
    queue.append(ts_response(["ts_code", "trade_date", "open", "high", "low", "close", "vol", "amount"], [
        ["600519.SH", "20260915", 10, 12, 9, 11, 123, 14.5],
        ["600519.SH", "20260914", 9, 11, 8, 10, 100, 10],
    ]))
    result = http.query("tushare", "daily_ohlcv", history_params(), ts_context(context))
    assert result["kind"] == "bars"
    assert [row["datetime"] for row in result["records"]] == ["2026-09-14", "2026-09-15"]
    assert result["records"][1]["volume"] == 12300
    assert result["records"][1]["turnover"] == 14500
    assert result["metadata"]["adjustment"] == "none"
    assert calls[0]["json"]["params"] == {"ts_code": "600519.SH", "start_date": "20260901", "end_date": "20260915"}


def test_tushare_absent_amount_is_not_zero(transport: Any, context: dict[str, Any]) -> None:
    queue, _ = transport
    queue.append(ts_response(["ts_code", "trade_date", "open", "high", "low", "close", "vol"], [
        ["600519.SH", "20260915", 10, 12, 9, 11, 123],
    ]))
    result = http.query("tushare", "daily_ohlcv", history_params(), ts_context(context))
    assert "turnover" not in result["records"][0]
    assert result["metadata"]["missing_fields"] == ["turnover"]


@pytest.mark.parametrize("adjustment", ["qfq", "hfq"])
def test_tushare_does_not_relabel_raw_prices_as_adjusted(adjustment: str, transport: Any, context: dict[str, Any]) -> None:
    with pytest.raises(http.ProviderError, match="^unsupported_adjustment$"):
        http.query("tushare", "daily_ohlcv", history_params(adjust=adjustment), ts_context(context))
    assert transport[1] == []


@pytest.mark.parametrize("code,day,error", [
    ("000001.SZ", "20260915", "symbol_mismatch"),
    ("600519.SH", "20260916", "out_of_range_data"),
])
def test_tushare_wrong_security_or_date_fails(code: str, day: str, error: str, transport: Any, context: dict[str, Any]) -> None:
    queue, _ = transport
    queue.append(ts_response(["ts_code", "trade_date", "open", "high", "low", "close", "vol"], [
        [code, day, 10, 12, 9, 11, 123],
    ]))
    with pytest.raises(http.ProviderError, match=f"^{error}$"):
        http.query("tushare", "daily_ohlcv", history_params(), ts_context(context))


def test_tushare_margin_filters_exchange_after_fetch(transport: Any, context: dict[str, Any]) -> None:
    queue, calls = transport
    queue.append(ts_response(["trade_date", "exchange_id", "rzye", "rqye"], [
        ["20260915", "SSE", 100, 200], ["20260915", "SZSE", 300, 400],
    ]))
    result = http.query("tushare", "margin", {"start": "2026-09-01", "end": "2026-09-15", "exchange": "SZSE"}, ts_context(context))
    assert "exchange" not in calls[0]["json"]["params"]
    assert [row["exchange_id"] for row in result["records"]] == ["SZSE"]


def test_tushare_calendar_returns_actual_table(transport: Any, context: dict[str, Any]) -> None:
    queue, calls = transport
    queue.append(ts_response(["exchange", "cal_date", "is_open"], [["SSE", "20260915", 1]]))
    result = http.query("tushare", "trade_calendar", {"start": "2026-09-15", "end": "2026-09-15"}, ts_context(context))
    assert result["records"] == [{"exchange": "SSE", "cal_date": "20260915", "is_open": 1}]
    assert calls[0]["json"]["api_name"] == "trade_cal"


@pytest.mark.parametrize("factor,error", [(0, "invalid_values"), (-1, "invalid_values"), (float("inf"), "schema_changed")])
def test_tushare_invalid_adjustment_factor_is_not_returned(factor: float, error: str, transport: Any, context: dict[str, Any]) -> None:
    queue, _ = transport
    queue.append(ts_response(["ts_code", "trade_date", "adj_factor"], [["600519.SH", "20260915", factor]]))
    with pytest.raises(http.ProviderError, match=f"^{error}$"):
        http.query("tushare", "adj_factor", history_params(), ts_context(context))


def test_tushare_moneyflow_preserves_negative_net_flow(transport: Any, context: dict[str, Any]) -> None:
    queue, _ = transport
    queue.append(ts_response(["ts_code", "trade_date", "buy_sm_amount", "sell_sm_amount", "net_mf_amount"], [
        ["600519.SH", "20260915", 10, 20, -10],
    ]))
    result = http.query("tushare", "moneyflow_stock", history_params(), ts_context(context))
    assert result["records"][0]["net_mf_amount"] == -10


def test_tushare_stock_basic_needs_no_artificial_date_window(transport: Any, context: dict[str, Any]) -> None:
    queue, calls = transport
    queue.append(ts_response(["ts_code", "symbol", "name", "list_date"], [["600519.SH", "600519", "fixture", "20010827"]]))
    result = http.query("tushare", "stock_basic", {"symbol": "600519.SSE"}, ts_context(context))
    assert result["records"][0]["ts_code"] == "600519.SH"
    assert "start_date" not in calls[0]["json"]["params"]


def test_tushare_financial_response_outside_announced_period_fails(transport: Any, context: dict[str, Any]) -> None:
    queue, _ = transport
    queue.append(ts_response(["ts_code", "ann_date", "end_date", "revenue"], [["600519.SH", "20260916", "20260630", 100]]))
    with pytest.raises(http.ProviderError, match="^out_of_range_data$"):
        http.query("tushare", "financial_statement", history_params(), ts_context(context))


def test_miaoxiang_returns_actual_partial_markdown_records(transport: Any, context: dict[str, Any]) -> None:
    queue, calls = transport
    context["secrets"] = {"MX_APIKEY": "fixture-api-key"}
    table = "| 股票代码 | 股票名称 | DDX(%) |\n| --- | --- | --- |\n| 600519 | 名称\\|含分隔符 | 0.3 |\n"
    queue.append(response({"success": True, "data": {"data": {"securityCount": 10, "partialResults": table}}}))
    result = http.query("miaoxiang", "ddx_ddy", {}, context)
    assert result["records"] == [{"股票代码": "600519", "股票名称": "名称|含分隔符", "DDX(%)": "0.3"}]
    assert result["metadata"]["partial"] is True
    assert result["metadata"]["reported_total"] == 10
    assert result["metadata"]["time_label"] == "not_provided"
    assert calls[0]["json"] == {"keyword": "DDX大于0的股票"}
    assert calls[0]["url"].endswith("/stock-screen")


def test_miaoxiang_does_not_confuse_prose_with_data(transport: Any, context: dict[str, Any]) -> None:
    queue, _ = transport
    context["secrets"] = {"MX_APIKEY": "fixture-api-key"}
    queue.append(response({"success": True, "data": {"data": {"securityCount": 10, "partialResults": "Found ten stocks"}}}))
    with pytest.raises(http.ProviderError, match="^schema_changed$"):
        http.query("miaoxiang", "screen", {}, context)


def test_credentials_are_not_copied_from_provider_error_or_table(transport: Any, context: dict[str, Any]) -> None:
    queue, _ = transport
    context = ts_context(context)
    queue.append(response({"code": 403, "msg": "test-secret-value"}))
    with pytest.raises(http.ProviderError, match="^provider_business_error$"):
        http.query("tushare", "stock_basic", {}, context)
    queue.append(ts_response(["ts_code", "symbol", "name", "list_date"], [
        ["600519.SH", "600519", "test-secret-value", "20010827"],
    ]))
    with pytest.raises(http.ProviderError, match="^unsafe_provider_response$"):
        http.query("tushare", "stock_basic", {}, context)


def test_timeout_has_only_fixed_error_code(transport: Any, context: dict[str, Any]) -> None:
    queue, _ = transport
    queue.append(requests.exceptions.Timeout("credential-in-original-error"))
    with pytest.raises(http.ProviderError, match="^timeout$"):
        http.query("tencent", "quote_realtime_batch", {"symbol": "600519.SSE"}, context)
