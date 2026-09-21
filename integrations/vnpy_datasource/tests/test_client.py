"""Tests for routing decisions and the process boundary, without network access."""

from copy import deepcopy
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from vnpy_datasource.client import DataSourceClient, DataSourceError
from vnpy_datasource.registry import unavailable
from vnpy_datasource.validation import SHANGHAI, validate_bars


def registry() -> dict:
    source = {"status": "verified", "verified_on": datetime.now(timezone.utc).isoformat(),
              "invoke": {"quote_realtime": {"call": "quote()"}, "quote_realtime_batch": {"call": "quote()"}, "daily_ohlcv": {"call": "history()"}},
              "monitoring": {"observations": {}}}
    return {"sources": {"sina": deepcopy(source), "tencent": deepcopy(source)},
            "routing": {"实时行情_单只": {"primary": "tencent", "fallbacks": ["sina"],
                        "recipe": {"tencent": "quote_realtime_batch", "sina": "quote_realtime"}}}}


def test_real_failures_fallback_and_preserve_first_cause() -> None:
    client = DataSourceClient()
    ok = {"status": "ok", "kind": "quotes", "records": [{"last_price": 1}], "metadata": {}}
    with patch("vnpy_datasource.client.read_registry", return_value=(registry(), "digest")), \
            patch.object(client, "_runtime_ready", return_value=True), \
            patch.object(client, "_run", side_effect=[DataSourceError("provider_timeout"), ok]):
        result = client.query("实时行情_单只", {"symbol": "159915.SZSE"})
    assert result["source"] == "sina"
    assert result["attempts"][0]["reason"] == "provider_timeout"
    assert result["attempts"][1]["status"] == "ok"


@pytest.mark.parametrize("mutate,reason", [
    (lambda s: s.update(status="credential_invalid"), "credential_invalid"),
    (lambda s: s.update(verified_on="2000-01-01"), "stale_verification"),
    (lambda s: s["monitoring"]["observations"].update(daily_ohlcv={"status": "UNKNOWN"}), "latest_capability_unknown"),
    (lambda s: s["invoke"]["daily_ohlcv"].update(enabled=False), "recipe_disabled"),
    (lambda s: s.update(blocked_functions={"history": {}}), "blocked_function"),
])
def test_unavailable_prevents_execution(mutate, reason) -> None:
    db = registry()
    mutate(db["sources"]["sina"])
    assert unavailable(db, "sina", "daily_ohlcv") == reason


def test_skip_does_not_invent_failure() -> None:
    db = registry()
    db["sources"]["sina"]["monitoring"]["observations"]["daily_ohlcv"] = {"status": "SKIP"}
    assert unavailable(db, "sina", "daily_ohlcv") is None


def sample() -> tuple[dict, dict]:
    return ({"kind": "bars", "records": [{"datetime": "2026-09-11", "open": 1, "high": 2, "low": 1, "close": 2, "volume": 123, "turnover": None}],
             "metadata": {"interval": "d", "adjustment": "none", "volume_unit": "shares", "turnover_unit": "CNY", "time_label": "date"}},
            {"start": "2026-09-11", "end": "2026-09-15", "interval": "d", "adjust": "none"})


def test_closed_daily_excludes_current_session_and_marks_missing() -> None:
    result, params = sample()
    result["records"].append({**result["records"][0], "datetime": "2026-09-15"})
    checked = validate_bars(result, params, datetime(2026, 9, 15, 14, tzinfo=SHANGHAI))
    assert len(checked["records"]) == 1
    assert checked["metadata"]["excluded"]["unfinished"] == 1
    assert checked["records"][0]["turnover"] is None
    assert checked["metadata"]["missing_fields"] == ["turnover"]


def test_bar_conflict_is_not_silently_overwritten() -> None:
    result, params = sample()
    result["records"].append({**result["records"][0], "volume": 124})
    with pytest.raises(ValueError, match="conflicting_duplicate"):
        validate_bars(result, params)


def test_intraday_points_cannot_become_bars() -> None:
    with pytest.raises(ValueError, match="not_ohlcv"):
        validate_bars({"kind": "intraday", "records": [{"price": 2}]}, {})


def test_five_minute_is_not_one_minute() -> None:
    result, params = sample()
    params["interval"] = "1m"
    result["metadata"]["interval"] = "5m"
    with pytest.raises(ValueError, match="interval_mismatch"):
        validate_bars(result, params)


def test_adjusted_price_never_satisfies_raw_request() -> None:
    result, params = sample()
    result["metadata"]["adjustment"] = "qfq"
    with pytest.raises(ValueError, match="adjustment_mismatch"):
        validate_bars(result, params)


def test_timeout_kills_tree_and_does_not_return_sdk_output() -> None:
    import subprocess
    from unittest.mock import MagicMock
    process = MagicMock(pid=987654)
    process.communicate.side_effect = [subprocess.TimeoutExpired("worker", 1), ("SECRET", "SECRET")]
    with patch("vnpy_datasource.client.subprocess.Popen", return_value=process), \
            patch("vnpy_datasource.client.subprocess.run", return_value=MagicMock(returncode=0)) as kill:
        with pytest.raises(DataSourceError, match="^provider_timeout$"):
            DataSourceClient()._run({}, 1)
    assert kill.call_args.args[0] == ["taskkill", "/PID", "987654", "/T", "/F"]


def test_timeout_cleanup_failure_still_attempts_reap() -> None:
    import subprocess
    from unittest.mock import MagicMock
    process = MagicMock(pid=987654)
    process.communicate.side_effect = [subprocess.TimeoutExpired("worker", 1), ("SECRET", "SECRET")]
    with patch("vnpy_datasource.client.subprocess.Popen", return_value=process), \
            patch("vnpy_datasource.client.subprocess.run", side_effect=subprocess.TimeoutExpired("kill", 1)):
        with pytest.raises(DataSourceError, match="^provider_cleanup_failed$"):
            DataSourceClient()._run({}, 1)
    assert process.communicate.call_count == 2
    process.kill.assert_called_once()


def test_daily_framework_dates_are_converted_to_shanghai_first() -> None:
    from vnpy_datasource.datafeed import DataSourceDatafeed
    from vnpy.trader.constant import Exchange, Interval
    from vnpy.trader.object import HistoryRequest
    feed = DataSourceDatafeed()
    feed.prefer_warehouse = False  # this test is about the online path's date handling
    req = HistoryRequest(symbol="600519", exchange=Exchange.SSE, interval=Interval.DAILY,
                         start=datetime(2026, 9, 10, 16, tzinfo=timezone.utc),
                         end=datetime(2026, 9, 11, 16, tzinfo=timezone.utc))
    with patch.object(feed.client, "history", return_value={"status": "no_data", "attempts": []}) as query:
        assert feed.query_bar_history(req, lambda message: None) == []
    assert query.call_args.args[1:3] == ("2026-09-11", "2026-09-12")


def test_datafeed_prefers_warehouse_and_falls_back_online() -> None:
    from vnpy_datasource.datafeed import DataSourceDatafeed
    from vnpy.trader.constant import Exchange, Interval
    from vnpy.trader.object import HistoryRequest
    feed = DataSourceDatafeed()
    req = HistoryRequest(symbol="159915", exchange=Exchange.SZSE, interval=Interval.DAILY,
                         start=datetime(2026, 9, 1), end=datetime(2026, 9, 18))
    local = {"status": "ok", "kind": "bars", "source": "warehouse", "recipe": "bars_etf_1d", "snapshot_id": "SNAP",
             "records": [{"datetime": "2026-09-18", "open": 3.3, "high": 3.4, "low": 3.2, "close": 3.391, "volume": 1.0, "turnover": None}],
             "metadata": {"interval": "d", "adjustment": "none"}, "request": {"params": {"symbol": "159915.SZSE"}}}
    with patch.object(feed.warehouse, "available", return_value=True),          patch.object(feed.warehouse, "history", return_value=local),          patch.object(feed.client, "history") as online:
        bars = feed.query_bar_history(req, lambda message: None)
    assert online.call_count == 0 and len(bars) == 1 and bars[0].extra["snapshot_id"] == "SNAP"
    with patch.object(feed.warehouse, "available", return_value=True),          patch.object(feed.warehouse, "history", return_value={"status": "no_data", "reason": "dataset_not_in_warehouse:x", "records": []}),          patch.object(feed.client, "history", return_value={"status": "no_data", "attempts": []}) as online:
        assert feed.query_bar_history(req, lambda message: None) == []
    assert online.call_count == 1


def test_worker_malformed_output_cannot_leak_secret() -> None:
    from unittest.mock import MagicMock
    process = MagicMock(returncode=0)
    process.communicate.return_value = ("SECRET not json", "secret stderr")
    with patch("vnpy_datasource.client.subprocess.Popen", return_value=process):
        with pytest.raises(DataSourceError, match="^invalid_worker_response$"):
            DataSourceClient()._run({}, 1)


def test_recipe_lists_require_explicit_selection() -> None:
    db = registry()
    db["routing"]["ambiguous"] = {"primary": "sina", "recipe": {"sina": ["x", "y"]}}
    with patch("vnpy_datasource.client.read_registry", return_value=(db, "digest")):
        with pytest.raises(ValueError, match="explicit_recipe"):
            DataSourceClient().query("ambiguous")
