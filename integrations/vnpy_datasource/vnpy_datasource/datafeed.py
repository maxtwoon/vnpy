"""VeighNa standard historical-data adapter and explicit research client."""

from collections.abc import Callable
from datetime import datetime
import hashlib
import json
from uuid import uuid4

from vnpy.trader.constant import Exchange, Interval
from vnpy.trader.datafeed import BaseDatafeed
from vnpy.trader.object import BarData, HistoryRequest, TickData
from vnpy.trader.setting import SETTINGS
from vnpy.trader.utility import get_folder_path

from .client import DataSourceClient
from .validation import local_time
from .warehouse import WarehouseReader


def to_bars(result: dict, symbol: str) -> list[BarData]:
    """Translate checked records; retain missing-field/provenance information."""
    if result.get("status") != "ok" or result.get("kind") != "bars":
        return []
    requested_symbol = result.get("request", {}).get("params", {}).get("symbol")
    if requested_symbol and requested_symbol != symbol:
        raise ValueError("history_symbol_mismatch")
    intervals = {"d": Interval.DAILY, "1m": Interval.MINUTE, "1h": Interval.HOUR}
    interval = intervals.get(result["metadata"]["interval"])
    if interval is None:
        raise ValueError("vnpy_has_no_enum_for_this_interval")
    code, exchange = symbol.split(".")
    bars = []
    for row in result["records"]:
        bar = BarData(symbol=code, exchange=Exchange(exchange), datetime=local_time(row["datetime"]),
                      interval=interval, open_price=row["open"], high_price=row["high"], low_price=row["low"], close_price=row["close"],
                      volume=row["volume"], turnover=row.get("turnover") or 0, open_interest=row.get("open_interest") or 0,
                      gateway_name="DATASOURCE")
        bar.extra = {"source": result.get("source"), "recipe": result.get("recipe"), "fetched_at": result.get("fetched_at"),
                     "registry_sha256": result.get("registry_sha256"), "adjustment": result["metadata"].get("adjustment"),
                     "snapshot_id": result.get("snapshot_id"),
                     "missing_fields": [key for key in ("turnover", "open_interest") if row.get(key) is None]}
        bars.append(bar)
    return bars


class DataSourceDatafeed(BaseDatafeed):
    """Local warehouse snapshot first; the isolated online dataSource process as fallback."""

    def __init__(self) -> None:
        root = SETTINGS.get("datafeed.datasource_root", "D:/repo/dataSource")
        self.client = DataSourceClient(root, float(SETTINGS.get("datafeed.datasource_timeout", 90)))
        # datafeed.datasource_prefer_warehouse=false forces the online path; datafeed.datasource_snapshot pins a snapshot id.
        self.prefer_warehouse = bool(SETTINGS.get("datafeed.datasource_prefer_warehouse", True))
        self.warehouse = WarehouseReader(root, SETTINGS.get("datafeed.datasource_snapshot") or None)
        self.last_result: dict = {}

    def init(self, output: Callable = print) -> bool:
        """Check local readiness; does not assert that every provider is online."""
        try:
            return bool(self.client.describe()["runtime_ready"])
        except (OSError, ValueError, KeyError):
            output("dataSource初始化失败：请检查台账路径和维护环境")
            return False

    def query_bar_history(self, req: HistoryRequest, output: Callable = print) -> list[BarData]:
        """Return raw closed bars compatible with strategy loaders and DataManager."""
        try:
            if req.interval not in {Interval.DAILY, Interval.MINUTE, Interval.HOUR}:
                raise ValueError("unsupported_interval")
            begin = local_time(req.start.isoformat())
            end = local_time((req.end or datetime.now().astimezone()).isoformat())
            start_value = begin.date().isoformat() if req.interval == Interval.DAILY else begin.isoformat()
            end_value = end.date().isoformat() if req.interval == Interval.DAILY else end.isoformat()
            vt_symbol = f"{req.symbol}.{req.exchange.value}"
            self.last_result = {}
            if self.prefer_warehouse and self.warehouse.available():
                self.last_result = self.warehouse.history(vt_symbol, start_value, end_value, req.interval.value)
                if self.last_result["status"] != "ok":
                    output(f"本地回测库无此数据 [{self.last_result.get('reason')}]，改走在线源")
            if self.last_result.get("status") != "ok":
                self.last_result = self.client.history(vt_symbol, start_value, end_value, req.interval.value)
            if self.last_result["status"] != "ok":
                reason = self.last_result.get("reason") or "; ".join(f"{a['source']}: {a.get('reason') or a['status']}" for a in self.last_result["attempts"])
                output(f"dataSource查询未成功 [{self.last_result['status']}] {reason}")
                return []
            # Standard SQLite drops BarData.extra: retain one compact receipt
            # for GUI downloads and strategy initialization outside that table.
            receipt = {key: value for key, value in self.last_result.items() if key != "records"}
            receipt["row_count"] = len(self.last_result["records"])
            receipt["records_sha256"] = hashlib.sha256(json.dumps(self.last_result["records"], sort_keys=True).encode()).hexdigest()
            receipt["turnover_missing_dates"] = [row["datetime"] for row in self.last_result["records"] if row.get("turnover") is None]
            receipt_path = get_folder_path("datasource_receipts") / (datetime.now().strftime("%Y%m%dT%H%M%S") + "-" + uuid4().hex[:8] + ".json")
            receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
            self.last_result["receipt"] = str(receipt_path)
            return to_bars(self.last_result, vt_symbol)
        except (ValueError, KeyError, OSError) as exc:
            self.last_result = {"status": "error", "reason": type(exc).__name__, "records": []}
            output("dataSource查询失败：请求参数或本地运行环境无效")
            return []

    def query_tick_history(self, req: HistoryRequest, output: Callable = print) -> list[TickData]:
        """Snapshots and intraday points must not masquerade as historical ticks."""
        self.last_result = {"status": "unsupported", "reason": "historical_tick_not_supported", "records": []}
        output("dataSource尚无可用A股历史逐笔适配；实时快照请调用client.query")
        return []
