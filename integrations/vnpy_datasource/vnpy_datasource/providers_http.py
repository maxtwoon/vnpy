"""Read-only HTTP adapters for the recipes in the dataSource registry."""

import math
import re
from datetime import date, datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlsplit

import requests


SUPPORTED: dict[str, list[str]] = {
    "tencent": ["quote_realtime_batch", "minute_bars"],
    "sina": ["quote_realtime"],
    "xueqiu": ["quote_realtime_batch"],
    "tushare": [
        "daily_ohlcv", "adj_factor", "trade_calendar", "stock_basic",
        "financial_statement", "moneyflow_stock", "margin",
    ],
    "miaoxiang": ["screen", "ddx_ddy", "zt_pool", "moneyflow_stock", "fundamental"],
}
CN_TIMEZONE = timezone(timedelta(hours=8))
_MARKETS = {"SSE": "sh", "SZSE": "sz", "BSE": "bj"}
_HOST_SYMBOL = re.compile(r"^(\d{6})\.(SSE|SZSE|BSE)$")


class ProviderError(ValueError):
    """Expose only a fixed error code, never provider text or credentials."""


def _require(condition: bool, code: str = "schema_changed") -> None:
    if not condition:
        raise ProviderError(code)


def _number(value: Any, *, nonnegative: bool = False) -> float:
    _require(not isinstance(value, bool))
    number = float(value)
    _require(math.isfinite(number) and (not nonnegative or number >= 0), "invalid_values")
    return number


def _day(value: Any) -> str:
    _require(isinstance(value, str), "invalid_date")
    value = value.strip()
    if re.fullmatch(r"\d{8}", value):
        value = f"{value[:4]}-{value[4:6]}-{value[6:]}"
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError:
        raise ProviderError("invalid_date") from None


def _period(params: dict[str, Any]) -> tuple[str, str]:
    start, end = _day(params.get("start")), _day(params.get("end"))
    _require(start <= end, "invalid_date_range")
    return start, end


def _symbols(params: dict[str, Any], *, single: bool = False) -> list[str]:
    _require(not ("symbols" in params and "symbol" in params), "ambiguous_symbols")
    raw = params.get("symbols")
    if raw is None:
        raw = [params.get("symbol")]
    _require(isinstance(raw, list) and 0 < len(raw) <= 100, "invalid_symbols")
    _require(not single or len(raw) == 1, "single_symbol_required")
    _require(all(isinstance(value, str) and _HOST_SYMBOL.fullmatch(value) for value in raw), "invalid_symbol")
    _require(len(set(raw)) == len(raw), "duplicate_symbols")
    return raw


def _native(symbol: str, *, upper: bool = False) -> str:
    code, market = symbol.split(".")
    prefix = _MARKETS[market]
    return (prefix.upper() if upper else prefix) + code


def _ts_symbol(symbol: str) -> str:
    code, market = symbol.split(".")
    return code + "." + {"SSE": "SH", "SZSE": "SZ", "BSE": "BJ"}[market]


def _blocked(url: str, source: str, context: dict[str, Any]) -> bool:
    target = urlsplit(url)
    sources = context.get("db", {}).get("sources", {})
    for owner in (sources.get(source, {}), sources.get("eastmoney", {})):
        for endpoint, state in (owner.get("endpoint_status") or {}).items():
            status = state.get("status") if isinstance(state, dict) else state
            if status != "blocked":
                continue
            block = urlsplit(endpoint if "://" in endpoint else "https://" + endpoint)
            if target.hostname == block.hostname and target.path.startswith(block.path):
                return True
    return False


def _request(source: str, url: str, context: dict[str, Any], *, method: str = "GET", **kwargs: Any) -> requests.Response:
    _require(not _blocked(url, source, context), "blocked_endpoint")
    timeout = min(20.0, max(1.0, float(context.get("timeout", 20))))
    with requests.Session() as session:
        session.trust_env = False
        session.headers.update({"User-Agent": "Mozilla/5.0", "Accept": "*/*"})
        response = session.request(method, url, timeout=timeout, allow_redirects=False, **kwargs)
    if response.status_code in (401, 403):
        raise ProviderError("access_denied")
    if response.status_code == 429:
        raise ProviderError("rate_limited")
    if 300 <= response.status_code < 400:
        raise ProviderError("unexpected_redirect")
    _require(response.status_code == 200, "http_error")
    return response


def _json(response: requests.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError:
        raise ProviderError("schema_changed") from None
    _require(isinstance(payload, dict))
    return payload


def _business(payload: dict[str, Any], key: str, *, optional: bool = False) -> None:
    _require(optional or key in payload)
    if key in payload:
        _require(payload[key] in (0, "0"), "provider_business_error")


def _result(kind: str, records: list[dict[str, Any]], **metadata: Any) -> dict[str, Any]:
    return {"kind": kind, "records": records, "metadata": metadata}


def _check_params(params: dict[str, Any], allowed: set[str]) -> None:
    _require(isinstance(params, dict) and set(params).issubset(allowed), "unsupported_parameter")


def _quote_metadata(params: dict[str, Any]) -> dict[str, Any]:
    asset = params.get("asset", "stock")
    _require(asset in ("stock", "etf"), "unsupported_asset")
    return {
        "asset": asset, "timezone": "Asia/Shanghai", "time_label": "timestamp",
        "volume_unit": "shares", "turnover_unit": "CNY", "adjustment": "none",
    }


def _tencent_quotes(params: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    _check_params(params, {"symbol", "symbols", "asset"})
    symbols, metadata = _symbols(params), _quote_metadata(params)
    requested = {_native(symbol): symbol for symbol in symbols}
    response = _request("tencent", "https://qt.gtimg.cn/q=" + ",".join(requested), context)
    response.encoding = "gbk"
    matches = re.findall(r'v_((?:sh|sz|bj)\d{6})\s*=\s*"([^"\r\n]*)"', response.text)
    _require(len(matches) == len(requested) and {key for key, _ in matches} == set(requested), "incomplete_quotes")
    records = []
    for key, raw in matches:
        fields = raw.split("~")
        _require(len(fields) > 37 and fields[2] == key[2:])
        stamp = datetime.strptime(fields[30], "%Y%m%d%H%M%S").replace(tzinfo=CN_TIMEZONE)
        records.append({
            "symbol": requested[key], "datetime": stamp.isoformat(), "name": fields[1],
            "last_price": _number(fields[3], nonnegative=True),
            "pre_close": _number(fields[4], nonnegative=True),
            "open_price": _number(fields[5], nonnegative=True),
            "high_price": _number(fields[33], nonnegative=True),
            "low_price": _number(fields[34], nonnegative=True),
            "volume": _number(fields[6], nonnegative=True) * 100,
            "turnover": _number(fields[37], nonnegative=True) * 10000,
        })
    metadata.update(volume_conversion="provider_lots * 100", turnover_conversion="provider_10k_CNY * 10000")
    return _result("quotes", records, **metadata)


def _sina_quotes(params: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    _check_params(params, {"symbol", "symbols", "asset"})
    symbols, metadata = _symbols(params), _quote_metadata(params)
    requested = {_native(symbol): symbol for symbol in symbols}
    response = _request("sina", "https://hq.sinajs.cn/list=" + ",".join(requested), context,
                        headers={"Referer": "https://finance.sina.com.cn"})
    response.encoding = "gbk"
    matches = re.findall(r'hq_str_((?:sh|sz|bj)\d{6})\s*=\s*"([^"\r\n]*)"', response.text)
    _require(len(matches) == len(requested) and {key for key, _ in matches} == set(requested), "incomplete_quotes")
    records = []
    for key, raw in matches:
        fields = raw.split(",")
        _require(len(fields) >= 32)
        stamp = datetime.strptime(f"{fields[30]} {fields[31]}", "%Y-%m-%d %H:%M:%S").replace(tzinfo=CN_TIMEZONE)
        records.append({
            "symbol": requested[key], "datetime": stamp.isoformat(), "name": fields[0],
            "last_price": _number(fields[3], nonnegative=True),
            "pre_close": _number(fields[2], nonnegative=True),
            "open_price": _number(fields[1], nonnegative=True),
            "high_price": _number(fields[4], nonnegative=True),
            "low_price": _number(fields[5], nonnegative=True),
            "volume": _number(fields[8], nonnegative=True),
            "turnover": _number(fields[9], nonnegative=True),
        })
    return _result("quotes", records, **metadata)


def _xueqiu_quotes(params: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    _check_params(params, {"symbol", "symbols", "asset"})
    symbols, metadata = _symbols(params), _quote_metadata(params)
    requested = {_native(symbol, upper=True): symbol for symbol in symbols}
    payload = _json(_request("xueqiu", "https://stock.xueqiu.com/v5/stock/realtime/quotec.json", context,
                            params={"symbol": ",".join(requested)}, headers={"Referer": "https://xueqiu.com"}))
    _business(payload, "error_code", optional=True)
    rows = payload.get("data")
    _require(isinstance(rows, list) and all(isinstance(row, dict) for row in rows))
    _require(len(rows) == len(requested) and {row.get("symbol") for row in rows} == set(requested), "incomplete_quotes")
    records = []
    missing = set()
    optional = {"open": "open_price", "high": "high_price", "low": "low_price", "last_close": "pre_close",
                "volume": "volume", "amount": "turnover"}
    for row in rows:
        stamp = datetime.fromtimestamp(_number(row["timestamp"], nonnegative=True) / 1000, CN_TIMEZONE)
        record = {"symbol": requested[row["symbol"]], "datetime": stamp.isoformat(),
                  "last_price": _number(row["current"], nonnegative=True)}
        if isinstance(row.get("name"), str):
            record["name"] = row["name"]
        for origin, target in optional.items():
            if row.get(origin) is None:
                missing.add(target)
            else:
                record[target] = _number(row[origin], nonnegative=True)
        records.append(record)
    metadata["missing_fields"] = sorted(missing)
    return _result("quotes", records, **metadata)


def _tencent_intraday(params: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    _check_params(params, {"symbol", "symbols", "start", "end", "interval", "adjust", "asset"})
    symbol = _symbols(params, single=True)[0]
    _require(params.get("adjust", "none") == "none", "unsupported_adjustment")
    _require(params.get("asset", "stock") in ("stock", "etf"), "unsupported_asset")
    native = _native(symbol)
    payload = _json(_request("tencent", "https://web.ifzq.gtimg.cn/appstock/app/minute/query", context,
                            params={"code": native}))
    _business(payload, "code")
    block = payload["data"][native]["data"]
    day = _day(block["date"])
    raw = block["data"]
    _require(isinstance(raw, list))
    records = []
    seen = set()
    for line in raw:
        _require(isinstance(line, str))
        fields = line.split()
        _require(len(fields) >= 3 and bool(re.fullmatch(r"\d{4}", fields[0])))
        stamp = datetime.strptime(f"{day} {fields[0]}", "%Y-%m-%d %H%M").replace(tzinfo=CN_TIMEZONE).isoformat()
        _require(stamp not in seen, "duplicate_timestamp")
        seen.add(stamp)
        records.append({"symbol": symbol, "datetime": stamp, "price": _number(fields[1], nonnegative=True),
                        "cumulative_volume": _number(fields[2], nonnegative=True)})
    if "start" in params or "end" in params:
        start, end = _period(params)
        if not start <= day <= end:
            records = []
    records.sort(key=lambda row: row["datetime"])
    return _result("intraday", records, timezone="Asia/Shanghai", time_label="timestamp",
                   interval="intraday_series", adjustment="none", volume_unit="provider_native",
                   provider_session=day, missing_fields=["open", "high", "low", "close", "turnover"],
                   volume_semantics="provider_cumulative_volume; not per-bar volume", historical_ohlcv=False)


def _tushare_url(context: dict[str, Any]) -> str:
    url = context.get("secrets", {}).get("TUSHARE_API_URL") or "https://fastapic.stockai888.top"
    _require(isinstance(url, str), "invalid_configuration")
    parsed = urlsplit(url)
    _require(parsed.scheme in ("http", "https") and bool(parsed.hostname)
             and not parsed.username and not parsed.password and not parsed.query and not parsed.fragment,
             "invalid_configuration")
    return url


def _tushare(recipe: str, params: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    allowed = {"symbol", "start", "end", "interval", "adjust", "asset", "exchange", "list_status", "statement"}
    _check_params(params, allowed)
    token = context.get("secrets", {}).get("TUSHARE_TOKEN")
    _require(isinstance(token, str) and bool(token), "credential_missing")
    _require(params.get("asset", "stock") == "stock", "unsupported_asset")
    _require(params.get("adjust", "none") == "none", "unsupported_adjustment")
    _require(params.get("interval", "d") in ("d", "1d", "daily"), "unsupported_interval")
    start, end = (None, None) if recipe == "stock_basic" else _period(params)
    period = {} if start is None else {"start_date": start.replace("-", ""), "end_date": end.replace("-", "")}
    symbol = params.get("symbol")
    if recipe not in ("trade_calendar", "margin", "stock_basic") or symbol is not None:
        symbol = _symbols(params, single=True)[0]
    exchange = params.get("exchange", "SSE" if recipe == "trade_calendar" else "")
    _require(exchange in ("", "SSE", "SZSE", "BSE"), "invalid_exchange")
    api = {"daily_ohlcv": "daily", "adj_factor": "adj_factor", "trade_calendar": "trade_cal",
           "stock_basic": "stock_basic", "financial_statement": "income",
           "moneyflow_stock": "moneyflow", "margin": "margin"}[recipe]
    request_params = dict(period)
    if recipe == "trade_calendar":
        request_params["exchange"] = exchange
    elif recipe == "margin":
        pass  # This gateway requires client-side exchange filtering.
    elif recipe == "stock_basic":
        listing = params.get("list_status", "L")
        _require(listing in ("L", "D", "P"), "invalid_list_status")
        request_params.update(exchange=exchange, list_status=listing)
    if symbol and recipe not in ("trade_calendar", "margin"):
        request_params["ts_code"] = _ts_symbol(symbol)
    if recipe == "financial_statement":
        _require(params.get("statement", "income") == "income", "unsupported_statement")
    payload = _json(_request("tushare", _tushare_url(context), context, method="POST",
                            json={"api_name": api, "token": token, "params": request_params, "fields": ""}))
    _business(payload, "code")
    data = payload["data"]
    fields, items = data["fields"], data["items"]
    _require(isinstance(fields, list) and all(isinstance(field, str) for field in fields)
             and len(set(fields)) == len(fields) and isinstance(items, list))
    required = {
        "daily_ohlcv": {"ts_code", "trade_date", "open", "high", "low", "close", "vol"},
        "adj_factor": {"ts_code", "trade_date", "adj_factor"},
        "trade_calendar": {"exchange", "cal_date", "is_open"},
        "stock_basic": {"ts_code", "symbol", "name", "list_date"},
        "financial_statement": {"ts_code", "ann_date", "end_date", "revenue"},
        "moneyflow_stock": {"ts_code", "trade_date", "buy_sm_amount", "sell_sm_amount", "net_mf_amount"},
        "margin": {"trade_date", "exchange_id", "rzye", "rqye"},
    }[recipe]
    _require(required.issubset(fields))
    _require(all(isinstance(row, list) and len(row) == len(fields) for row in items))
    rows = [dict(zip(fields, row, strict=True)) for row in items]
    if symbol and "ts_code" in required:
        _require(all(row["ts_code"] == _ts_symbol(symbol) for row in rows), "symbol_mismatch")
    if "trade_date" in required:
        _require(all(start <= _day(row["trade_date"]) <= end for row in rows), "out_of_range_data")
    if recipe == "margin" and exchange:
        rows = [row for row in rows if row["exchange_id"] == exchange]
    if recipe == "trade_calendar":
        _require(all(start <= _day(row["cal_date"]) <= end and str(row["is_open"]) in ("0", "1")
                     and row["exchange"] == exchange for row in rows), "invalid_values")
    if recipe == "financial_statement":
        _require(all(start <= _day(row["ann_date"]) <= end for row in rows), "out_of_range_data")
    if recipe == "adj_factor":
        _require(all(_number(row["adj_factor"]) > 0 for row in rows), "invalid_values")
    if recipe == "moneyflow_stock":
        for row in rows:
            _number(row["buy_sm_amount"], nonnegative=True)
            _number(row["sell_sm_amount"], nonnegative=True)
            _number(row["net_mf_amount"])
    if recipe == "margin":
        for row in rows:
            _number(row["rzye"], nonnegative=True)
            _number(row["rqye"], nonnegative=True)
    if recipe == "daily_ohlcv":
        bars, missing = [], set()
        for row in rows:
            bar = {"symbol": symbol, "datetime": _day(row["trade_date"]),
                   **{key: _number(row[key], nonnegative=True) for key in ("open", "high", "low", "close")},
                   "volume": _number(row["vol"], nonnegative=True) * 100}
            _require(min(bar[key] for key in ("open", "high", "low", "close")) > 0
                     and bar["high"] >= max(bar["open"], bar["close"], bar["low"])
                     and bar["low"] <= min(bar["open"], bar["close"], bar["high"]), "invalid_values")
            if row.get("amount") is None:
                missing.add("turnover")
            else:
                bar["turnover"] = _number(row["amount"], nonnegative=True) * 1000
            bars.append(bar)
        _require(len({bar["datetime"] for bar in bars}) == len(bars), "duplicate_timestamp")
        bars.sort(key=lambda row: row["datetime"])
        return _result("bars", bars, interval="d", adjustment="none", volume_unit="shares", turnover_unit="CNY",
                       time_label="date", timezone="Asia/Shanghai", missing_fields=sorted(missing),
                       volume_conversion="provider_lots * 100", turnover_conversion="provider_1000_CNY * 1000")
    return _result("table", rows, api=api, fields=fields, time_label="provider_fields",
                   adjustment="none", units="provider_native", pagination="single_response",
                   point_in_time_guarantee=False if recipe == "financial_statement" else None)


def _markdown_rows(table: Any) -> list[dict[str, str]]:
    _require(isinstance(table, str))
    lines = [line.strip() for line in table.splitlines() if "|" in line]
    _require(len(lines) >= 2)

    def cells(line: str) -> list[str]:
        if line.startswith("|"):
            line = line[1:]
        if line.endswith("|") and not line.endswith(r"\|"):
            line = line[:-1]
        return [part.strip().replace(r"\|", "|") for part in re.split(r"(?<!\\)\|", line)]

    for index in range(len(lines) - 1):
        separator = cells(lines[index + 1])
        if not separator or not all(re.fullmatch(r":?-{3,}:?", part) for part in separator):
            continue
        headers = cells(lines[index])
        _require(len(headers) == len(separator) and all(headers) and len(set(headers)) == len(headers))
        records = []
        for line in lines[index + 2:]:
            values = cells(line)
            if len(values) != len(headers):
                break
            _require(any(re.search(r"(?<!\d)\d{6}(?!\d)", value) for value in values))
            records.append(dict(zip(headers, values, strict=True)))
        return records
    raise ProviderError("schema_changed")


def _miaoxiang(recipe: str, params: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    _check_params(params, {"keyword"})
    token = context.get("secrets", {}).get("MX_APIKEY")
    _require(isinstance(token, str) and bool(token), "credential_missing")
    defaults = {"screen": "市盈率小于20的白酒股", "fundamental": "市盈率小于20的白酒股",
                "ddx_ddy": "DDX大于0的股票", "zt_pool": "今日涨停的股票", "moneyflow_stock": "主力净流入前10的股票"}
    keyword = params.get("keyword", defaults[recipe])
    _require(isinstance(keyword, str) and 0 < len(keyword.strip()) <= 500 and "\x00" not in keyword, "invalid_keyword")
    payload = _json(_request("miaoxiang", "https://mkapi2.dfcfs.com/finskillshub/api/claw/stock-screen", context,
                            method="POST", headers={"apikey": token}, json={"keyword": keyword}))
    _require(payload.get("success") is True, "provider_business_error")
    data = payload["data"]["data"]
    count = _number(data["securityCount"], nonnegative=True)
    _require(count.is_integer())
    records = _markdown_rows(data.get("partialResults")) if count else []
    _require(count >= len(records) and (count == 0 or bool(records)))
    return _result("table", records, fields=list(records[0]) if records else [], reported_total=int(count),
                   partial=len(records) < count, units="in_column_headers", time_label="not_provided",
                   point_in_time_guarantee=False, pagination="provider_partial_results")


def _check_result_secrets(result: dict[str, Any], context: dict[str, Any]) -> None:
    sensitive = [value for key, value in context.get("secrets", {}).items()
                 if isinstance(value, str) and value and re.search(r"TOKEN|PASSWORD|API_?KEY|SECRET", key, re.I)]

    def check(value: Any) -> None:
        if isinstance(value, str):
            _require(not any(secret in value if len(secret) >= 4 else secret == value for secret in sensitive),
                     "unsafe_provider_response")
        elif isinstance(value, float):
            _require(math.isfinite(value), "invalid_values")
        elif isinstance(value, dict):
            for key, child in value.items():
                check(key)
                check(child)
        elif isinstance(value, list):
            for child in value:
                check(child)

    check(result)


def query(source: str, recipe: str, params: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    """Fetch a fixed read-only recipe and return actual records with their units."""
    _require(recipe in SUPPORTED.get(source, []), "unsupported_capability")
    try:
        if source == "tencent":
            result = _tencent_quotes(params, context) if recipe == "quote_realtime_batch" else _tencent_intraday(params, context)
        elif source == "sina":
            result = _sina_quotes(params, context)
        elif source == "xueqiu":
            result = _xueqiu_quotes(params, context)
        elif source == "tushare":
            result = _tushare(recipe, params, context)
        else:
            result = _miaoxiang(recipe, params, context)
        _check_result_secrets(result, context)
        return result
    except ProviderError:
        raise
    except requests.exceptions.Timeout:
        raise ProviderError("timeout") from None
    except requests.exceptions.RequestException:
        raise ProviderError("network_error") from None
    except (KeyError, IndexError, TypeError, ValueError, OverflowError, AttributeError):
        raise ProviderError("schema_changed") from None
