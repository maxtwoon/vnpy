"""Read ETF research inputs from the configured VeighNa datafeed; no orders."""

from datetime import date, datetime, timedelta
import json

from vnpy.trader.constant import Exchange, Interval
from vnpy.trader.datafeed import get_datafeed
from vnpy.trader.object import HistoryRequest


def main() -> None:
    """Print an input-data summary suitable for a timing/rotation strategy."""
    feed = get_datafeed()
    end = date.today() - timedelta(days=1)
    req = HistoryRequest(symbol="159915", exchange=Exchange.SZSE, interval=Interval.DAILY,
                         start=datetime.combine(end - timedelta(days=60), datetime.min.time()),
                         end=datetime.combine(end, datetime.min.time()))
    bars = feed.query_bar_history(req)
    if not bars:
        raise SystemExit("ETF历史数据不可用，请查看dataSource失败原因")
    result = feed.last_result
    print(json.dumps({"symbol": "159915.SZSE", "bars": len(bars), "first": bars[0].datetime.isoformat(),
                      "last": bars[-1].datetime.isoformat(), "last_close": bars[-1].close_price,
                      "source": result["source"], "adjustment": result["metadata"]["adjustment"],
                      "missing_fields": result["metadata"]["missing_fields"]}, ensure_ascii=False, indent=2))
    calendar = feed.client.query("交易日历", {"start": (end - timedelta(days=14)).isoformat(), "end": end.isoformat()})
    if calendar["status"] != "ok":
        raise SystemExit("交易日历查询失败，不能静默使用过期日历")
    print(json.dumps({"calendar_source": calendar["source"], "open_dates": [row["date"] for row in calendar["records"] if row["is_open"]]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

