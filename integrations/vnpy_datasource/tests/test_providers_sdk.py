"""Small offline contract tests; no SDK installation or network required."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase, main
from unittest.mock import Mock, patch


MODULE = Path(__file__).resolve().parents[1] / "vnpy_datasource" / "providers_sdk.py"
spec = importlib.util.spec_from_file_location("providers_sdk_under_test", MODULE)
sdk = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sdk)


class Frame:
    def __init__(self, rows):
        self.rows = rows
        self.empty = not rows

    def to_dict(self, orient):
        assert orient == "records"
        return self.rows

    def reset_index(self):
        return self


def result(rows, code="0"):
    return SimpleNamespace(error_code=code, get_data=lambda: Frame(rows))


PARAMS = {"symbol": "600519.SSE", "start": "2026-01-02", "end": "2026-01-05", "interval": "d", "adjust": "none"}
BAR = dict(date="2026-01-02", open=10, high=12, low=9, close=11, volume=200, amount=2100)


class ProviderTests(TestCase):
    def run_with(self, module, source, recipe, params=None):
        session = SimpleNamespace(request=Mock(), close=Mock())
        curl = SimpleNamespace(Session=Mock(return_value=session))
        def load(name):
            return curl if name == "curl_cffi.requests" else module
        with patch.object(sdk.importlib, "import_module", side_effect=load):
            return sdk.query(source, recipe, params or PARAMS, {"timeout": 12})

    def test_unknown_recipe_cannot_dispatch_arbitrary_method(self):
        with patch.object(sdk.importlib, "import_module") as load:
            with self.assertRaisesRegex(ValueError, "^unsupported_recipe$"):
                sdk.query("baostock", "send_order", {}, {})
            load.assert_not_called()

    def test_sina_raw_explicitly_overrides_ledger_qfq_example(self):
        ak = SimpleNamespace(stock_zh_a_daily=Mock(return_value=Frame([BAR])))
        output = self.run_with(ak, "sina", "daily_ohlcv")
        self.assertEqual(ak.stock_zh_a_daily.call_args.kwargs["adjust"], "")
        self.assertEqual(output["records"][0]["turnover"], 2100)
        self.assertEqual(output["metadata"]["adjustment"], "none")

    def test_sina_etf_filters_range_and_keeps_missing_turnover(self):
        rows = [{**BAR, "date": "2025-12-31"}, {k: v for k, v in BAR.items() if k != "amount"}]
        ak = SimpleNamespace(fund_etf_hist_sina=Mock(return_value=Frame(rows)))
        output = self.run_with(ak, "sina", "etf_ohlcv", {**PARAMS, "symbol": "159915.SZSE", "asset": "etf"})
        self.assertEqual(len(output["records"]), 1)
        self.assertIsNone(output["records"][0]["turnover"])
        self.assertEqual(output["metadata"]["missing_fields"], ["turnover"])

    def test_sina_etf_rejects_unprovided_adjustment(self):
        with self.assertRaisesRegex(ValueError, "^unsupported_adjustment$"):
            self.run_with(SimpleNamespace(), "sina", "etf_ohlcv", {**PARAMS, "adjust": "qfq"})

    def test_sina_calendar_does_not_invent_closed_dates(self):
        ak = SimpleNamespace(tool_trade_date_hist_sina=Mock(return_value=Frame([
            {"trade_date": "2026-01-02"}, {"trade_date": "2026-01-05"}, {"trade_date": "2026-01-06"},
        ])))
        output = self.run_with(ak, "sina", "trade_calendar")
        self.assertEqual(output["records"], [{"date": "2026-01-02", "is_open": True}, {"date": "2026-01-05", "is_open": True}])

    def test_tencent_current_sdk_volume_is_not_multiplied_twice(self):
        ak = SimpleNamespace(stock_zh_a_hist_tx=Mock(return_value=Frame([BAR])))
        output = self.run_with(ak, "tencent", "daily_ohlcv")
        self.assertEqual(output["records"][0]["volume"], 200)
        self.assertEqual(output["records"][0]["turnover"], 2100)
        self.assertEqual(ak.stock_zh_a_hist_tx.call_args.kwargs["timeout"], 12)

    def test_tencent_legacy_amount_is_not_silently_treated_as_money(self):
        ak = SimpleNamespace(stock_zh_a_hist_tx=Mock(return_value=Frame([{k: v for k, v in BAR.items() if k != "volume"}])))
        with self.assertRaisesRegex(ValueError, "^unsupported_tencent_legacy_volume_schema$"):
            self.run_with(ak, "tencent", "daily_ohlcv")

    def test_tencent_index_amount_is_quantity_and_turnover_missing(self):
        ak = SimpleNamespace(stock_zh_index_daily_tx=Mock(return_value=Frame([{k: v for k, v in BAR.items() if k != "volume"}])))
        output = self.run_with(ak, "tencent", "index_ohlcv", {**PARAMS, "symbol": "000001.SSE", "asset": "index"})
        self.assertEqual(output["records"][0]["volume"], 210000)
        self.assertIsNone(output["records"][0]["turnover"])

    def test_tencent_adjusted_recipe_alias_defaults_to_qfq(self):
        ak = SimpleNamespace(stock_zh_a_hist_tx=Mock(return_value=Frame([BAR])))
        output = self.run_with(ak, "tencent", "daily_adjusted", {k: v for k, v in PARAMS.items() if k != "adjust"})
        self.assertEqual(ak.stock_zh_a_hist_tx.call_args.kwargs["adjust"], "qfq")
        self.assertEqual(output["metadata"]["adjustment"], "qfq")

    def test_tencent_known_sz000_sdk_bug_has_version_scoped_correction(self):
        for version, volume in (("1.18.94", 20000), ("1.18.95", 200)):
            ak = SimpleNamespace(__version__=version, stock_zh_a_hist_tx=Mock(return_value=Frame([BAR])))
            output = self.run_with(ak, "tencent", "daily_ohlcv", {**PARAMS, "symbol": "000001.SZSE"})
            self.assertEqual(output["records"][0]["volume"], volume)

    def test_baostock_five_minute_end_label_converted_to_start(self):
        bs = SimpleNamespace(login=Mock(return_value=result([])), logout=Mock(),
                             query_history_k_data_plus=Mock(return_value=result([
                                 {**BAR, "time": "20260102093500000", "code": "sh.600519"},
                             ])))
        output = self.run_with(bs, "baostock", "minute_bars", {**PARAMS, "interval": "5m"})
        self.assertEqual(output["records"][0]["datetime"], "2026-01-02T09:30:00+08:00")
        self.assertEqual(bs.query_history_k_data_plus.call_args.kwargs["frequency"], "5")
        self.assertEqual(bs.query_history_k_data_plus.call_args.kwargs["adjustflag"], "3")
        bs.logout.assert_called_once()

    def test_baostock_does_not_substitute_five_minutes_for_one(self):
        bs = SimpleNamespace(login=Mock(return_value=result([])), logout=Mock(), query_history_k_data_plus=Mock())
        with self.assertRaisesRegex(ValueError, "^unsupported_interval$"):
            self.run_with(bs, "baostock", "minute_bars", {**PARAMS, "interval": "1m"})
        bs.query_history_k_data_plus.assert_not_called()
        bs.logout.assert_called_once()

    def test_baostock_business_error_keeps_message_out_and_logs_out(self):
        bs = SimpleNamespace(login=Mock(return_value=result([])), logout=Mock(),
                             query_history_k_data_plus=Mock(return_value=result([], "SECRET_SERVER_TEXT")))
        with self.assertRaisesRegex(ValueError, "^baostock_business_error$"):
            self.run_with(bs, "baostock", "daily_adjusted")
        bs.logout.assert_called_once()

    def test_baostock_financial_query_only_uses_fixed_function_and_parameters(self):
        bs = SimpleNamespace(login=Mock(return_value=result([])), logout=Mock(),
                             query_profit_data=Mock(return_value=result([{"roeAvg": "0.2"}])))
        self.run_with(bs, "baostock", "financial_profit", {**PARAMS, "year": 2025, "quarter": 4, "method": "send_order"})
        bs.query_profit_data.assert_called_once_with(code="sh.600519", year=2025, quarter=4)

    def test_baostock_all_stock_honors_explicit_day(self):
        bs = SimpleNamespace(login=Mock(return_value=result([])), logout=Mock(), query_all_stock=Mock(return_value=result([])))
        self.run_with(bs, "baostock", "all_stock", {"day": "2026-01-02"})
        bs.query_all_stock.assert_called_once_with(day="2026-01-02")

    def test_external_sdk_exception_does_not_expose_response_or_credentials(self):
        ak = SimpleNamespace(stock_zh_a_daily=Mock(side_effect=ValueError("token=private-value")))
        with self.assertRaisesRegex(ValueError, "^sdk_query_failed$"):
            self.run_with(ak, "sina", "daily_ohlcv")

    def test_yahoo_cn_minutes_rejected_after_live_quality_failure(self):
        ticker = SimpleNamespace(history=Mock(return_value=Frame([
            {"Datetime": "2026-01-02T01:30:00+00:00", "Open": 10, "High": 12, "Low": 9, "Close": 11, "Volume": 200},
        ])))
        yf = SimpleNamespace(Ticker=Mock(return_value=ticker))
        with self.assertRaisesRegex(ValueError, "^unsupported_yfinance_cn_minute_quality$"):
            self.run_with(yf, "yfinance", "minute_bars", {**PARAMS, "interval": "1m"})
        ticker.history.assert_not_called()

    def test_yahoo_refuses_adjustment_semantics_it_cannot_supply(self):
        ticker = SimpleNamespace(history=Mock())
        with self.assertRaisesRegex(ValueError, "^unsupported_yfinance_adjustment$"):
            self.run_with(SimpleNamespace(Ticker=Mock(return_value=ticker)), "yfinance", "daily_ohlcv", {**PARAMS, "adjust": "hfq"})
        ticker.history.assert_not_called()

    def test_yahoo_foreign_bars_keep_native_session_and_timestamp(self):
        ticker = SimpleNamespace(history=Mock(return_value=Frame([
            {"Datetime": "2026-01-02T09:30:00-05:00", "Open": 10, "High": 12, "Low": 9, "Close": 11, "Volume": 200},
        ])))
        output = self.run_with(SimpleNamespace(Ticker=Mock(return_value=ticker)), "yfinance", "minute_bars",
                               {**PARAMS, "symbol": "AAPL", "interval": "1m"})
        self.assertEqual(output["kind"], "native_bars")
        self.assertEqual(output["records"][0]["datetime"], "2026-01-02T09:30:00-05:00")
        self.assertEqual(output["metadata"]["market_scope"], "non_cn")

    def test_yahoo_uses_explicit_proxy_bounded_request_and_closes_session(self):
        original_request = Mock(return_value="response")
        session = SimpleNamespace(request=original_request, close=Mock())
        curl = SimpleNamespace(Session=Mock(return_value=session))
        def history(**kwargs):
            session.request("GET", "https://example.invalid", timeout=999)
            return Frame([])
        ticker = SimpleNamespace(history=Mock(side_effect=history))
        yf = SimpleNamespace(Ticker=Mock(return_value=ticker))
        with patch.object(sdk.importlib, "import_module", side_effect=lambda name: curl if name == "curl_cffi.requests" else yf):
            sdk.query("yfinance", "daily_ohlcv", PARAMS, {"proxy_url": "http://127.0.0.1:7897", "timeout": 90})
        curl.Session.assert_called_once_with(impersonate="chrome", proxy="http://127.0.0.1:7897", trust_env=False, timeout=20)
        yf.Ticker.assert_called_once_with("600519.SS", session=session)
        self.assertEqual(original_request.call_args.kwargs["timeout"], 20)
        session.close.assert_called_once()

    def test_yahoo_sdk_failure_closes_session_and_surfaces_error(self):
        session = SimpleNamespace(request=Mock(), close=Mock())
        curl = SimpleNamespace(Session=Mock(return_value=session))
        yf = SimpleNamespace(Ticker=Mock(return_value=SimpleNamespace(history=Mock(side_effect=RuntimeError("private_response")))))
        with patch.object(sdk.importlib, "import_module", side_effect=lambda name: curl if name == "curl_cffi.requests" else yf):
            with self.assertRaisesRegex(ValueError, "^sdk_query_failed$"):
                sdk.query("yfinance", "daily_ohlcv", PARAMS, {"timeout": 12})
        session.close.assert_called_once()

    def test_yahoo_cn_batch_keeps_symbols_and_uses_batch_kind(self):
        ticker = SimpleNamespace(history=Mock(return_value=Frame([
            {"Date": "2026-01-02", "Open": 10, "High": 12, "Low": 9, "Close": 11, "Volume": 200},
        ])))
        output = self.run_with(SimpleNamespace(Ticker=Mock(return_value=ticker)), "yfinance", "batch_download",
                               {**PARAMS, "symbols": ["600519.SSE", "159915.SZSE"]})
        self.assertEqual(output["kind"], "bar_batch")
        self.assertTrue(output["metadata"]["batch"])
        self.assertEqual([row["symbol"] for row in output["records"]], ["600519.SSE", "159915.SZSE"])

    def test_yahoo_foreign_batch_uses_native_batch_kind(self):
        ticker = SimpleNamespace(history=Mock(return_value=Frame([
            {"Date": "2026-01-02", "Open": 10, "High": 12, "Low": 9, "Close": 11, "Volume": 200},
        ])))
        output = self.run_with(SimpleNamespace(Ticker=Mock(return_value=ticker)), "yfinance", "batch_download",
                               {**PARAMS, "symbols": ["AAPL", "MSFT"]})
        self.assertEqual(output["kind"], "native_bar_batch")

    def test_invalid_ohlc_and_conflicting_duplicate_fail(self):
        for rows in ([{**BAR, "high": 5}], [BAR, {**BAR, "close": 10.5}]):
            ak = SimpleNamespace(stock_zh_a_daily=Mock(return_value=Frame(rows)))
            with self.assertRaises(ValueError):
                self.run_with(ak, "sina", "daily_ohlcv")


if __name__ == "__main__":
    main()
