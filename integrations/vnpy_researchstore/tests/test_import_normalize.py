from __future__ import annotations

from datetime import datetime, timezone

from research_store.importers.normalize import (
    apply_numeric_fields,
    daily_bounds_ns,
    end_label_bounds_ns,
    normalize_jq_daily_row,
    normalize_rq_etf_row,
    normalize_rq_futures_row,
    normalize_ssquant_row,
    parse_label,
    raw_is_nonfinite,
    to_float,
)


def test_end_label_conversion_first_morning_bar() -> None:
    # 09:31 END label => bar covers 09:30-09:31 Shanghai = 01:30-01:31 UTC
    start_ns, end_ns = end_label_bounds_ns(parse_label("2026-07-31 09:31:00"), 1)
    utc_start = datetime.fromtimestamp(start_ns / 1e9, tz=timezone.utc)
    utc_end = datetime.fromtimestamp(end_ns / 1e9, tz=timezone.utc)
    assert utc_start.strftime("%Y-%m-%d %H:%M") == "2026-07-31 01:30"
    assert utc_end.strftime("%Y-%m-%d %H:%M") == "2026-07-31 01:31"
    assert end_ns - start_ns == 60 * 1_000_000_000


def test_daily_bounds_keyed_on_trading_date() -> None:
    start_ns, end_ns = daily_bounds_ns(parse_label("2016-02-29"))
    assert end_ns - start_ns == 24 * 3600 * 1_000_000_000
    row = normalize_rq_etf_row(
        {
            "order_book_id": "161225.XSHE",
            "date": "2016-02-29",
            "open": "0.849",
            "high": "0.849",
            "low": "0.849",
            "close": "0.849",
            "volume": "0.0",
            "amount": "-4.0",
        },
        interval_minutes=0,
        archive="rqdatac_etf_lof_1d_2016.tar.zst",
        member="2016/161225.XSHE.csv",
        batch_id="b1",
    )
    assert row["trading_date"] == "2016-02-29"
    assert row["bar_start_ns"] == start_ns
    assert row["bar_end_ns"] == end_ns
    assert row["turnover"] == -4.0
    assert "negative:turnover" in row["quality_flags"]


def test_rq_etf_minute_no_midday_filler_and_nulls_preserved() -> None:
    row = normalize_rq_etf_row(
        {
            "order_book_id": "510300.XSHG",
            "datetime": "2026-07-31 13:01:00",
            "open": "",
            "high": "4.683",
            "low": "4.676",
            "close": "4.683",
            "volume": "47330601.0",
            "amount": "221543322.0",
            "num_trades": "5558.0",
        },
        interval_minutes=1,
        archive="a.tar.zst",
        member="2026/510300.XSHG.csv",
        batch_id="b1",
    )
    assert row["open"] is None  # empty stays missing, never 0
    assert row["extensions"]["num_trades"] == 5558.0
    assert row["exchange"] == "XSHG"
    # 13:01 label -> 13:00-13:01 local -> 05:00-05:01 UTC
    start = datetime.fromtimestamp(row["bar_start_ns"] / 1e9, tz=timezone.utc)
    assert start.strftime("%H:%M") == "05:00"


def test_nonfinite_input_becomes_explicit_missing() -> None:
    assert raw_is_nonfinite("nan") and raw_is_nonfinite("inf")
    assert to_float("nan") is None
    row = {
        "open": None,
        "high": None,
        "low": None,
        "close": None,
        "quality_flags": [],
    }
    apply_numeric_fields(row, {"open": "nan"}, {"open": "open"})
    assert row["open"] is None
    assert row["quality_flags"] == ["nonfinite:open"]


def test_jq_daily_preserves_all_33_column_semantics() -> None:
    raw = {
        "date": "2025-01-02",
        "code": "000001.XSHE",
        "open": "11.73",
        "close": "11.43",
        "high": "11.77",
        "low": "11.39",
        "volume": "181959699.0",
        "money": "2102923078.11",
        "pre_close": "11.7",
        "high_limit": "12.87",
        "low_limit": "10.53",
        "paused": "0.0",
        "factor": "1.0",
        "market_cap": "2218.0965",
        "circulating_market_cap": "2218.0621",
        "turnover_ratio": "0.9377",
        "pe_ratio": "4.7651",
        "pb_ratio": "0.5275",
        "ps_ratio": "1.4922",
        "industry_sw_l1": "801780.0",
        "industry_sw_l2": "801783.0",
        "is_st": "0",
        "change_pct": "",
        "net_amount_main": "",
        "net_pct_main": "",
        "net_amount_xl": "",
        "net_pct_xl": "",
        "net_amount_l": "",
        "net_pct_l": "",
        "net_amount_m": "",
        "net_pct_m": "",
        "net_amount_s": "",
        "net_pct_s": "",
    }
    row = normalize_jq_daily_row(raw, archive="all_a_daily_2025.csv.gz", batch_id="b")
    assert row["trading_date"] == "2025-01-02"
    assert row["turnover"] == 2102923078.11
    assert row["extensions"]["paused"] == "0.0"
    assert row["extensions"]["factor"] == "1.0"
    assert row["extensions"]["net_amount_main"] == ""  # no NULL->0 fill
    assert (
        row["extensions"]["adjustment_status"] == "unknown_factor_all_one"
    )


def test_ssquant_unknown_label_semantics_and_passthrough() -> None:
    raw = {
        "datetime": "2026-02-24 13:30:00",
        "symbol": "rb2605",
        "real_symbol": "rb2605",
        "open": 3036.0,
        "high": 3036.0,
        "low": 3027.0,
        "close": 3029.0,
        "volume": 8387.0,
        "amount": 254157290.0,
        "openint": -1305.0,
        "cumulative_openint": 2031110.0,
        "多开": 2051.0,
        "B": 2499.0,
    }
    row = normalize_ssquant_row(raw, table="rb2605_1M_raw", batch_id="b", series_kind="real_contract")
    assert row["bar_start_ns"] is None and row["bar_end_ns"] is None
    assert "source_time_label_unknown" in row["quality_flags"]
    assert "trading_date_unknown_no_calendar" in row["quality_flags"]
    assert row["open_interest"] == -1305.0
    assert "negative:open_interest" in row["quality_flags"]
    assert row["extensions"]["cumulative_openint"] == 2031110.0
    assert row["extensions"]["real_symbol"] == "rb2605"
    assert row["extensions"]["多开"] == 2051.0
    assert row["extensions"]["amount_untrusted"] is True


def test_rq_futures_dominant_preserves_identity() -> None:
    record = {
        "underlying_symbol": "RB",
        "datetime": "2026-07-31 21:00:00",
        "trading_date": "2026-08-03 00:00:00",
        "dominant_id": "RB2610",
        "open": 3200.0,
        "close": 3201.0,
        "high": 3202.0,
        "low": 3199.0,
        "total_turnover": 1.0,
        "volume": 100.0,
        "open_interest": 180000.0,
    }
    row = normalize_rq_futures_row(
        record,
        dataset="dominant_1m_none",
        archive="rqdatac_dominant_1m_none_2026.tar.zst",
        member="2026/unit_0000.parquet",
        batch_id="b",
        interval_minutes=1,
    )
    assert row["instrument"] == "RB2610"
    assert row["series_kind"] == "continuous_dominant"
    # date-level source evidence transfers independently of label direction
    assert row["trading_date"] == "2026-08-03"
    assert row["extensions"]["underlying_symbol"] == "RB"
    # FUTURES_TIME_REVIEW_04IB: minute label direction UNKNOWN by default —
    # no canonical bounds, no silent END/START choice; original label kept
    assert row["bar_start_ns"] is None and row["bar_end_ns"] is None
    assert "source_time_label_unknown" in row["quality_flags"]
    assert row["source_label"] == "2026-07-31 21:00:00"


def test_rq_futures_contract_trading_date_stays_unknown() -> None:
    record = {
        "order_book_id": "RB2605",
        "datetime": "2026-02-24 13:30:00",
        "open": 1.0,
        "high": 1.0,
        "low": 1.0,
        "close": 1.0,
        "volume": 1.0,
        "amount": 1.0,
        "open_interest": 1.0,
    }
    row = normalize_rq_futures_row(
        record,
        dataset="contract_1m_none",
        archive="a.tar.zst",
        member="m",
        batch_id="b",
        interval_minutes=1,
    )
    assert row["trading_date"] is None
    assert "trading_date_unknown_no_calendar" in row["quality_flags"]
    assert row["series_kind"] == "instrument"


def test_indx_namespace_not_mapped_to_exchange() -> None:
    # .INDX is its own namespace; exchange stays the raw suffix, no SSE/SZSE
    # guess is made anywhere in the importer.
    row = normalize_rq_etf_row(
        {
            "order_book_id": "000300.INDX",
            "date": "2026-07-31",
            "open": "1",
            "high": "1",
            "low": "1",
            "close": "1",
            "volume": "1",
            "amount": "1",
        },
        interval_minutes=0,
        archive="a",
        member="m",
        batch_id="b",
    )
    assert row["exchange"] == "INDX"
