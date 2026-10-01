"""Allowlisted, read-only SDK queries for the local data-source adapter.

SDKs are imported lazily. The caller owns process isolation, timeouts and proxy
configuration; this module never changes environment variables or sessions.
"""

from __future__ import annotations

import importlib
import math
import re
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo


SHANGHAI = ZoneInfo("Asia/Shanghai")
INTERVALS = {"d": None, "1m": 1, "5m": 5, "15m": 15, "30m": 30, "1h": 60}
ADJUSTMENTS = {"none": "3", "qfq": "2", "hfq": "1"}
_ERROR_CODES = {
    "unsupported_sdk_value", "invalid_sdk_schema", "invalid_bar_value", "invalid_datetime",
    "missing_date_range", "invalid_date_range", "unsupported_symbol", "unsupported_adjustment",
    "unsupported_interval", "invalid_bar_schema", "invalid_ohlcv", "invalid_turnover",
    "conflicting_duplicate_bar", "unsupported_tencent_legacy_volume_schema", "baostock_business_error",
    "missing_symbol", "missing_financial_period", "invalid_financial_period", "invalid_dividend_period",
    "baostock_login_failed", "invalid_calendar", "unsupported_exchange", "unexpected_symbol",
    "unsupported_yfinance_adjustment", "invalid_symbols", "unsupported_statement", "unsupported_recipe",
    "invalid_query", "unsupported_mixed_market_batch",
}
_BS_TABLES = {
    "stock_basic": ("query_stock_basic", "basic"),
    "all_stock": ("query_all_stock", "day"),
    "financial_profit": ("query_profit_data", "quarter"),
    "financial_operation": ("query_operation_data", "quarter"),
    "financial_growth": ("query_growth_data", "quarter"),
    "financial_balance": ("query_balance_data", "quarter"),
    "financial_cashflow": ("query_cash_flow_data", "quarter"),
    "financial_dupont": ("query_dupont_data", "quarter"),
    "forecast_report": ("query_forecast_report", "period"),
    "performance_express": ("query_performance_express_report", "period"),
    "dividend_history": ("query_dividend_data", "dividend"),
    "adjust_factor": ("query_adjust_factor", "period"),
    "industry": ("query_stock_industry", "industry"),
    "index_sz50": ("query_sz50_stocks", "date"),
    "index_hs300": ("query_hs300_stocks", "date"),
    "index_zz500": ("query_zz500_stocks", "date"),
}
SUPPORTED: dict[str, list[str]] = {
    "sina": ["daily_ohlcv", "index_ohlcv", "etf_ohlcv", "etf_realtime", "trade_calendar"],
    "tencent": ["daily_ohlcv", "daily_adjusted", "index_ohlcv"],
    "baostock": ["daily_adjusted", "daily_ohlcv", "minute_bars", "trade_calendar", "valuation_history", *_BS_TABLES],
    "yfinance": ["daily_ohlcv", "index_ohlcv", "hk_us_quote", "minute_bars", "corporate_action",
                 "financial_statement", "metadata", "fx_quote", "batch_download"],
}


def _clean(value: Any) -> Any:
    """Convert SDK scalars to JSON values without serializing opaque objects."""
    if value is None:
        return None
    if isinstance(value, dict):
        return {str(k): _clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(v) for v in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if hasattr(value, "item"):
        return _clean(value.item())
    if str(value) in ("NaT", "<NA>"):
        return None
    raise ValueError("unsupported_sdk_value")


def _records(frame: Any, *, index: bool = False) -> list[dict]:
    if frame is None:
        return []
    if isinstance(frame, list):
        if not all(isinstance(row, dict) for row in frame):
            raise ValueError("invalid_sdk_schema")
        return _clean(frame)
    if getattr(frame, "empty", False):
        return []
    if index:
        frame = frame.reset_index()
    return _clean(frame.to_dict(orient="records"))


def _table(frame: Any, **metadata: Any) -> dict:
    return {"kind": "table", "records": _records(frame), "metadata": metadata}


def _number(value: Any, *, optional: bool = False) -> float | None:
    if value is None or value == "":
        if optional:
            return None
        raise ValueError("invalid_bar_value")
    try:
        result = float(value)
    except (ValueError, TypeError, OverflowError):
        raise ValueError("invalid_bar_value") from None
    if not math.isfinite(result):
        if optional:
            return None
        raise ValueError("invalid_bar_value")
    return result


def _datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        result = value
    elif isinstance(value, date):
        result = datetime.combine(value, time())
    else:
        raw = str(value).strip()
        try:
            if re.fullmatch(r"\d{17}", raw):
                result = datetime.strptime(raw, "%Y%m%d%H%M%S%f")
            elif re.fullmatch(r"\d{14}", raw):
                result = datetime.strptime(raw, "%Y%m%d%H%M%S")
            elif re.fullmatch(r"\d{8}", raw):
                result = datetime.strptime(raw, "%Y%m%d")
            else:
                result = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            raise ValueError("invalid_datetime") from None
    return result.replace(tzinfo=SHANGHAI) if result.tzinfo is None else result.astimezone(SHANGHAI)


def _period(params: dict) -> tuple[datetime, datetime]:
    start_value, end_value = params.get("start", params.get("start_date")), params.get("end", params.get("end_date"))
    if not start_value or not end_value:
        raise ValueError("missing_date_range")
    start, end = _datetime(start_value), _datetime(end_value)
    if len(str(end_value)) in (8, 10):
        end = end.replace(hour=23, minute=59, second=59, microsecond=999999)
    if start > end:
        raise ValueError("invalid_date_range")
    return start, end


def _symbol(value: Any) -> tuple[str, str]:
    """Return an explicit CN exchange and six-digit code; never infer ambiguous codes."""
    raw = str(value or "").strip().upper()
    match = re.fullmatch(r"(\d{6})\.(SSE|SZSE|BSE|SH|SZ|BJ|SS)", raw)
    if match:
        code, exchange = match.groups()
        return {"SSE": "sh", "SH": "sh", "SS": "sh", "SZSE": "sz", "SZ": "sz", "BSE": "bj", "BJ": "bj"}[exchange], code
    match = re.fullmatch(r"(SH|SZ|BJ)\.?([0-9]{6})", raw)
    if match:
        return match[1].lower(), match[2]
    raise ValueError("unsupported_symbol")


def _cn_symbol(params: dict, separator: str = "") -> str:
    market, code = _symbol(params.get("symbol", params.get("code")))
    return market + separator + code


def _adjust(params: dict) -> str:
    value = str(params.get("adjust", "none"))
    if value not in ADJUSTMENTS:
        raise ValueError("unsupported_adjustment")
    return value


def _interval(params: dict) -> str:
    value = str(params.get("interval", "d"))
    if value not in INTERVALS:
        raise ValueError("unsupported_interval")
    return value


def _bars(
    rows: list[dict], params: dict, *, interval: str, adjustment: str,
    date_key: str = "date", volume_key: str = "volume", amount_key: str | None = "amount",
    volume_factor: float = 1, amount_factor: float = 1, end_label: bool = False,
) -> dict:
    start, end = _period(params)
    output: dict[str, dict] = {}
    missing: set[str] = set()
    for row in rows:
        if date_key not in row:
            raise ValueError("invalid_bar_schema")
        dt = _datetime(row[date_key])
        if end_label:
            dt -= timedelta(minutes=INTERVALS[interval] or 0)
        if interval == "d":
            in_range = start.date() <= dt.date() <= end.date()
            label = dt.date().isoformat()
        else:
            in_range = start <= dt <= end
            label = dt.isoformat()
        if not in_range:
            continue
        try:
            opening, high, low, closing = (_number(row[k]) for k in ("open", "high", "low", "close"))
            volume = _number(row[volume_key]) * volume_factor
        except KeyError:
            raise ValueError("invalid_bar_schema") from None
        if (min(opening, high, low, closing) <= 0 or volume < 0
                or high < max(opening, closing, low) or low > min(opening, closing)):
            raise ValueError("invalid_ohlcv")
        amount = _number(row.get(amount_key), optional=True) if amount_key else None
        if amount is None:
            missing.add("turnover")
        else:
            amount *= amount_factor
            if amount < 0:
                raise ValueError("invalid_turnover")
        record = dict(datetime=label, open=opening, high=high, low=low, close=closing,
                      volume=volume, turnover=amount)
        if label in output and output[label] != record:
            raise ValueError("conflicting_duplicate_bar")
        output[label] = record
    return {
        "kind": "bars", "records": [output[k] for k in sorted(output)],
        "metadata": {"interval": interval, "adjustment": adjustment, "volume_unit": "shares",
                     "turnover_unit": "CNY", "time_label": "date" if interval == "d" else "start",
                     "missing_fields": sorted(missing)},
    }


def _sina(recipe: str, params: dict, context: dict) -> dict:
    ak = importlib.import_module("akshare")
    if recipe == "trade_calendar":
        start, end = _period(params)
        rows = _records(ak.tool_trade_date_hist_sina())
        records = [{"date": _datetime(r["trade_date"]).date().isoformat(), "is_open": True}
                   for r in rows if start.date() <= _datetime(r["trade_date"]).date() <= end.date()]
        return {"kind": "table", "records": records, "metadata": {"calendar_kind": "open_dates_only"}}
    if recipe == "etf_realtime":
        rows = _records(ak.fund_etf_category_sina(symbol="ETF基金"))
        wanted = _cn_symbol(params) if params.get("symbol") else None
        if wanted:
            rows = [r for r in rows if str(r.get("代码", "")).lower() in (wanted, wanted[2:])]
        return {"kind": "quotes", "records": rows,
                "metadata": {"volume_unit": "shares", "turnover_unit": "CNY",
                             "source_timestamp": None, "missing_fields": ["source_timestamp"],
                             "scope": "current_etf_list_and_quotes"}}
    if _interval(params) != "d":
        raise ValueError("unsupported_interval")
    symbol, adjustment = _cn_symbol(params), _adjust(params)
    start, end = _period(params)
    if recipe == "daily_ohlcv":
        frame = ak.stock_zh_a_daily(symbol=symbol, start_date=start.strftime("%Y%m%d"),
                                   end_date=end.strftime("%Y%m%d"), adjust="" if adjustment == "none" else adjustment)
    elif recipe == "index_ohlcv":
        if adjustment != "none":
            raise ValueError("unsupported_adjustment")
        frame = ak.stock_zh_index_daily(symbol=symbol)
    else:
        if adjustment != "none":
            raise ValueError("unsupported_adjustment")
        frame = ak.fund_etf_hist_sina(symbol=symbol)
    return _bars(_records(frame), params, interval="d", adjustment=adjustment)


def _tencent(recipe: str, params: dict, context: dict) -> dict:
    if _interval(params) != "d":
        raise ValueError("unsupported_interval")
    ak = importlib.import_module("akshare")
    symbol, adjustment = _cn_symbol(params), _adjust(params)
    start, end = _period(params)
    kwargs = dict(symbol=symbol, start_date=start.strftime("%Y%m%d"), end_date=end.strftime("%Y%m%d"))
    if recipe == "index_ohlcv":
        if adjustment != "none":
            raise ValueError("unsupported_adjustment")
        rows = _records(ak.stock_zh_index_daily_tx(**kwargs))
        # This API's `amount` is traded lots, not money. 2026-09-11 SH000001
        # cross-check: Tencent 579123145 lots == Sina 57912314500 shares.
        return _bars(rows, params, interval="d", adjustment="none", volume_key="amount",
                     amount_key=None, volume_factor=100)
    frame = ak.stock_zh_a_hist_tx(**kwargs, adjust="" if adjustment == "none" else adjustment,
                                timeout=context.get("timeout", 20))
    rows = _records(frame)
    if rows and "volume" not in rows[0]:
        # Legacy AKShare returned `amount` for raw Tencent lots. Refuse an
        # ambiguous unit instead of silently mislabeling it as currency/shares.
        raise ValueError("unsupported_tencent_legacy_volume_schema")
    factor = 1
    # AKShare 1.18.94 accidentally excludes all sz000 stocks from its lots-to-
    # shares conversion. Pin the correction to the observed version, not all
    # future releases. 2026-09-11: TX 832461 lots vs BaoStock 83246084 shares.
    version = str(getattr(ak, "__version__", "unknown"))
    if version == "1.18.94" and symbol.startswith("sz000"):
        factor = 100
    result = _bars(rows, params, interval="d", adjustment=adjustment, volume_factor=factor)
    result["metadata"].update(sdk_version=version)
    if factor != 1:
        result["metadata"]["volume_correction"] = "akshare_1_18_94_sz000_lots_to_shares"
    return result


def _bs_frame(result: Any) -> list[dict]:
    if result is None or str(getattr(result, "error_code", "")) != "0":
        raise ValueError("baostock_business_error")
    frame = result.get_data()
    if str(getattr(result, "error_code", "")) != "0":
        raise ValueError("baostock_business_error")
    return _records(frame)


def _bs_table_kwargs(mode: str, params: dict) -> dict:
    today = date.today().isoformat()
    requested_date = _datetime(params.get("date", params.get("day", params.get("end", params.get("end_date", today))))).date().isoformat()
    if mode == "day":
        return {"day": requested_date}
    if mode == "date":
        return {"date": requested_date}
    code = _cn_symbol(params, ".") if params.get("symbol") or params.get("code") else ""
    if mode == "basic":
        return {"code": code}
    if mode == "industry":
        return {"code": code, "date": requested_date}
    if not code:
        raise ValueError("missing_symbol")
    if mode == "quarter":
        try:
            year, quarter = int(params["year"]), int(params["quarter"])
        except (KeyError, TypeError, ValueError):
            raise ValueError("missing_financial_period") from None
        if not 1990 <= year <= 2200 or quarter not in (1, 2, 3, 4):
            raise ValueError("invalid_financial_period")
        return {"code": code, "year": year, "quarter": quarter}
    if mode == "dividend":
        year = str(params.get("year", ""))
        year_type = params.get("yearType", params.get("year_type", "report"))
        if not re.fullmatch(r"\d{4}", year) or year_type not in ("report", "operate"):
            raise ValueError("invalid_dividend_period")
        return {"code": code, "year": year, "yearType": year_type}
    start, end = _period(params)
    return {"code": code, "start_date": start.date().isoformat(), "end_date": end.date().isoformat()}


def _baostock(recipe: str, params: dict, context: dict) -> dict:
    bs = importlib.import_module("baostock")
    login = bs.login()
    if str(getattr(login, "error_code", "")) != "0":
        raise ValueError("baostock_login_failed")
    try:
        if recipe == "trade_calendar":
            start, end = _period(params)
            rows = _bs_frame(bs.query_trade_dates(start_date=str(start.date()), end_date=str(end.date())))
            records = []
            for row in rows:
                if str(row.get("is_trading_day")) not in ("0", "1"):
                    raise ValueError("invalid_calendar")
                records.append({"date": _datetime(row["calendar_date"]).date().isoformat(),
                                "is_open": str(row["is_trading_day"]) == "1"})
            return {"kind": "table", "records": records, "metadata": {"calendar_kind": "all_dates"}}
        if recipe in _BS_TABLES:
            function, mode = _BS_TABLES[recipe]
            # The method name is exclusively from the static map, never user input.
            rows = _bs_frame(getattr(bs, function)(**_bs_table_kwargs(mode, params)))
            return {"kind": "table", "records": rows, "metadata": {"recipe": recipe}}
        if recipe == "valuation_history":
            start, end = _period(params)
            rows = _bs_frame(bs.query_history_k_data_plus(
                _cn_symbol(params, "."), "date,code,peTTM,pbMRQ,psTTM,pcfNcfTTM,turn,tradestatus,isST",
                start_date=str(start.date()), end_date=str(end.date()), frequency="d", adjustflag="3",
            ))
            return {"kind": "table", "records": rows, "metadata": {"recipe": recipe}}
        interval, adjustment = _interval(params), _adjust(params)
        if interval == "1m":
            raise ValueError("unsupported_interval")
        if recipe == "minute_bars" and interval == "d":
            raise ValueError("unsupported_interval")
        start, end = _period(params)
        code = _cn_symbol(params, ".")
        if code.startswith("bj."):
            raise ValueError("unsupported_exchange")
        fields = "date,code,open,high,low,close,volume,amount,adjustflag"
        if interval != "d":
            fields = "date,time,code,open,high,low,close,volume,amount,adjustflag"
        rows = _bs_frame(bs.query_history_k_data_plus(
            code, fields, start_date=str(start.date()), end_date=str(end.date()),
            frequency="d" if interval == "d" else str(INTERVALS[interval]), adjustflag=ADJUSTMENTS[adjustment],
        ))
        if any(str(row.get("code", code)).lower() != code for row in rows):
            raise ValueError("unexpected_symbol")
        return _bars(rows, params, interval=interval, adjustment=adjustment,
                     date_key="date" if interval == "d" else "time", end_label=interval != "d")
    finally:
        try:
            bs.logout()
        except Exception:
            pass


def _yf_symbol(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        raise ValueError("missing_symbol")
    try:
        market, code = _symbol(raw)
    except ValueError:
        if not re.fullmatch(r"[A-Za-z0-9^][A-Za-z0-9.^=\-]{0,31}", raw):
            raise ValueError("unsupported_symbol") from None
        return raw
    if market == "bj":
        raise ValueError("unsupported_exchange")
    return code + (".SS" if market == "sh" else ".SZ")


def _yf_history(ticker: Any, params: dict, context: dict) -> dict:
    interval, adjustment = _interval(params), _adjust(params)
    if adjustment != "none":
        raise ValueError("unsupported_yfinance_adjustment")
    try:
        _symbol(params.get("symbol"))
        chinese = True
    except ValueError:
        chinese = False
    if chinese and interval != "d":
        # 2026-09-14 ETF sample contained 89 non-session rows and minute volume
        # summing to 3.4x independently verified daily volume. Do not promote it
        # into the CN historical-bar contract merely because the endpoint works.
        raise ValueError("unsupported_yfinance_cn_minute_quality")
    start, end = _period(params)
    yahoo_interval = "60m" if interval == "1h" else "1d" if interval == "d" else interval
    frame = ticker.history(start=str(start.date()), end=str(end.date() + timedelta(days=1)),
                           interval=yahoo_interval, auto_adjust=False, actions=False,
                           raise_errors=True,
                           timeout=context.get("timeout", 20))
    raw_rows = _records(frame, index=True)
    rows = []
    for raw in raw_rows:
        row = {str(k).lower(): v for k, v in raw.items()}
        stamp = row.get("datetime", row.get("date", row.get("index")))
        row["datetime"] = stamp
        rows.append(row)
    if not chinese:
        # Foreign exchange sessions and units are not the mainland bar contract.
        # Preserve source timestamps instead of applying Shanghai date/session rules.
        native = []
        for row in rows:
            native.append({"datetime": row["datetime"],
                           **{k: _number(row[k]) for k in ("open", "high", "low", "close", "volume")},
                           "turnover": None})
        return {"kind": "native_bars", "records": native,
                "metadata": {"interval": interval, "adjustment": "none", "auto_adjust": False,
                             "volume_unit": "provider_native", "turnover_unit": None,
                             "time_label": "provider_date" if interval == "d" else "provider_start",
                             "timezone": "provider", "market_scope": "non_cn",
                             "missing_fields": ["turnover"], "native_interval": yahoo_interval}}
    result = _bars(rows, params, interval=interval, adjustment="none", date_key="datetime", amount_key=None)
    result["metadata"].update(auto_adjust=False, native_interval=yahoo_interval)
    return result


def _yf_query(yf: Any, session: Any, recipe: str, params: dict, context: dict) -> dict:
    if recipe == "batch_download":
        symbols = params.get("symbols")
        if not isinstance(symbols, list) or not 1 <= len(symbols) <= 100:
            raise ValueError("invalid_symbols")
        rows = []
        metadata = {}
        kind = None
        for symbol in symbols:
            result = _yf_history(yf.Ticker(_yf_symbol(symbol), session=session), {**params, "symbol": symbol}, context)
            if kind is not None and kind != result["kind"]:
                raise ValueError("unsupported_mixed_market_batch")
            kind = result["kind"]
            rows.extend({"symbol": symbol, **row} for row in result["records"])
            metadata = result["metadata"]
        batch_kind = "bar_batch" if kind == "bars" else "native_bar_batch"
        return {"kind": batch_kind, "records": rows, "metadata": {**metadata, "batch": True}}
    ticker = yf.Ticker(_yf_symbol(params.get("symbol")), session=session)
    if recipe in ("daily_ohlcv", "index_ohlcv", "hk_us_quote", "minute_bars", "fx_quote"):
        if recipe == "minute_bars" and _interval(params) == "d":
            raise ValueError("unsupported_interval")
        return _yf_history(ticker, params, context)
    if recipe == "corporate_action":
        frame = ticker.actions
        rows = _records(frame, index=True)
        return {"kind": "table", "records": rows, "metadata": {"scope": "provider_actions"}}
    if recipe == "metadata":
        return {"kind": "table", "records": [_clean(dict(ticker.fast_info))],
                "metadata": {"scope": "current_metadata"}}
    statements = {"income": "income_stmt", "balance": "balance_sheet", "cashflow": "cashflow",
                  "quarterly_income": "quarterly_income_stmt", "quarterly_balance": "quarterly_balance_sheet",
                  "quarterly_cashflow": "quarterly_cashflow"}
    statement = params.get("statement", "income")
    if statement not in statements:
        raise ValueError("unsupported_statement")
    frame = getattr(ticker, statements[statement])
    # Financial frames have metric names on the index and reporting dates on columns.
    records = _records(frame.T, index=True) if not frame.empty else []
    return {"kind": "table", "records": records,
            "metadata": {"scope": "current_restatement", "point_in_time": False, "statement": statement}}


def _yfinance(recipe: str, params: dict, context: dict) -> dict:
    """Use the caller's explicit proxy with a bounded, privately owned session."""
    yf = importlib.import_module("yfinance")
    curl = importlib.import_module("curl_cffi.requests")
    timeout = max(1, min(20, float(context.get("timeout", 20))))
    session = curl.Session(impersonate="chrome", proxy=context.get("proxy_url"), trust_env=False, timeout=timeout)
    original_request = session.request

    def bounded_request(*args: Any, **kwargs: Any) -> Any:
        kwargs["timeout"] = timeout
        return original_request(*args, **kwargs)

    session.request = bounded_request
    try:
        return _yf_query(yf, session, recipe, params, {**context, "timeout": timeout})
    finally:
        session.close()


def query(source: str, recipe: str, params: dict, context: dict) -> dict:
    """Run one explicitly supported read-only recipe and return JSON-safe data."""
    if recipe not in SUPPORTED.get(source, []):
        raise ValueError("unsupported_recipe")
    if not isinstance(params, dict) or not isinstance(context, dict):
        raise ValueError("invalid_query")
    if source == "tencent" and recipe == "daily_adjusted" and "adjust" not in params:
        params = {**params, "adjust": "qfq"}
    handlers = {"sina": _sina, "tencent": _tencent, "baostock": _baostock, "yfinance": _yfinance}
    try:
        result = handlers[source](recipe, params, context)
    except ImportError:
        raise ValueError("sdk_missing") from None
    except Exception as exc:
        if isinstance(exc, ValueError) and (str(exc) in _ERROR_CODES or str(exc) == "unsupported_yfinance_cn_minute_quality"):
            raise
        raise ValueError("sdk_query_failed") from None
    result["metadata"].update(source=source, recipe=recipe)
    return result
