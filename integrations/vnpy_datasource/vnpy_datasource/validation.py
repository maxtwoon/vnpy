"""Time, price and unit checks shared by the isolated worker and tests."""

from datetime import datetime, time, timedelta
import math
import re
from zoneinfo import ZoneInfo

SHANGHAI = ZoneInfo("Asia/Shanghai")
INTERVALS = {"d": 0, "1m": 1, "5m": 5, "15m": 15, "30m": 30, "1h": 60}


def local_time(value: str) -> datetime:
    """Interpret naive request timestamps in the Chinese exchange timezone."""
    value = str(value)
    stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return stamp.replace(tzinfo=SHANGHAI) if stamp.tzinfo is None else stamp.astimezone(SHANGHAI)


def history_params(symbol: str, start: str, end: str, interval: str, adjust: str, asset: str | None) -> dict:
    """Require explicit exchange identity and a supported historical interval."""
    if not re.fullmatch(r"\d{6}\.(SSE|SZSE|BSE)", symbol):
        raise ValueError("use_vt_symbol_with_exchange")
    if interval not in INTERVALS:
        raise ValueError("unsupported_interval")
    if adjust not in {"none", "qfq", "hfq"}:
        raise ValueError("unsupported_adjustment")
    begin, finish = local_time(str(start)), local_time(str(end))
    if begin > finish:
        raise ValueError("start_after_end")
    code, exchange = symbol.split(".")
    if asset is None:
        asset = "index" if (exchange == "SSE" and code.startswith("000")) or (exchange == "SZSE" and code.startswith("399")) else "etf" if code.startswith(("51", "56", "58", "15")) else "stock"
    if asset not in {"stock", "etf", "index"}:
        raise ValueError("unsupported_asset")
    return {"symbol": symbol, "start": str(start), "end": str(end), "interval": interval, "adjust": adjust, "asset": asset}


def validate_bars(result: dict, params: dict, now: datetime | None = None) -> dict:
    """Reject incompatible series and malformed bars; report clipping explicitly."""
    if result.get("kind") != "bars":
        raise ValueError("unsupported_not_ohlcv")
    meta = dict(result.get("metadata", {}))
    interval = params.get("interval", "d")
    if interval not in INTERVALS or meta.get("interval") != interval:
        raise ValueError("unsupported_interval_mismatch")
    if meta.get("adjustment") != params.get("adjust", "none"):
        raise ValueError("unsupported_adjustment_mismatch")
    if interval != "d" and meta.get("time_label") != "start":
        raise ValueError("unsupported_bar_time_label")
    expected_units = {"share", "shares", "股", "份", "shares/units", "shares_or_units", "unit", "units"}
    if meta.get("volume_unit") not in expected_units:
        raise ValueError("unverified_volume_unit")
    if meta.get("turnover_unit") not in {"CNY", "元"}:
        raise ValueError("unverified_turnover_unit")
    begin, end = local_time(params["start"]), local_time(params["end"])
    if len(params["end"]) == 10:
        end = datetime.combine(end.date(), time.max, SHANGHAI)
    now = now or datetime.now(SHANGHAI)
    now = now.replace(tzinfo=SHANGHAI) if now.tzinfo is None else now.astimezone(SHANGHAI)
    seen: dict[str, dict] = {}
    excluded = {"outside_request": 0, "unfinished": 0, "duplicate_identical": 0}
    missing = set(meta.get("missing_fields", []))
    for raw in result.get("records", []):
        dt = local_time(raw["datetime"])
        if interval == "d":
            dt = datetime.combine(dt.date(), time(), SHANGHAI)
        if not begin <= dt <= end:
            excluded["outside_request"] += 1
            continue
        available = datetime.combine(dt.date(), time(15, 15), SHANGHAI) if interval == "d" else dt + timedelta(minutes=INTERVALS[interval] + 1)
        if available > now:
            excluded["unfinished"] += 1
            continue
        bar = {"datetime": dt.isoformat()}
        for field in ("open", "high", "low", "close", "volume"):
            value = float(raw[field])
            if not math.isfinite(value) or value < 0 or (field != "volume" and value == 0):
                raise ValueError("invalid_bar_numeric_value")
            bar[field] = value
        if bar["low"] > min(bar["open"], bar["close"]) or bar["high"] < max(bar["open"], bar["close"]) or bar["low"] > bar["high"]:
            raise ValueError("invalid_ohlc_order")
        for field in ("turnover", "open_interest"):
            value = raw.get(field, 0 if field == "open_interest" else None)
            if value is None:
                missing.add(field)
                bar[field] = None
            else:
                value = float(value)
                if not math.isfinite(value) or value < 0:
                    raise ValueError("invalid_bar_numeric_value")
                bar[field] = value
        key = bar["datetime"]
        if key in seen:
            if seen[key] != bar:
                raise ValueError("conflicting_duplicate_bar")
            excluded["duplicate_identical"] += 1
        seen[key] = bar
    bars = [seen[key] for key in sorted(seen)]
    meta.update(timezone="Asia/Shanghai", missing_fields=sorted(missing), excluded=excluded,
                closed_bars_only=True, time_label="date" if interval == "d" else "start",
                coverage="observed_rows_only_not_calendar_verified", gap_fill=False,
                actual_start=bars[0]["datetime"] if bars else None, actual_end=bars[-1]["datetime"] if bars else None)
    if interval == "d":
        meta["availability_policy"] = "date is a label; current day usable after 15:15 Shanghai"
    return {**result, "records": bars, "metadata": meta}
