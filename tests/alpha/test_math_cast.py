from datetime import datetime

import polars as pl

from vnpy.alpha.dataset.math_function import cast_to_int
from vnpy.alpha.dataset.utility import DataProxy, calculate_by_expression


def test_cast_preserves_nulls_index_and_input() -> None:
    """Boolean conversion must keep unknown values and original row identities."""
    source = pl.DataFrame({
        "datetime": [datetime(2026, 1, 2), datetime(2026, 1, 1), datetime(2026, 1, 3)],
        "vt_symbol": ["B", "A", "B"],
        "flag": [True, False, None],
    })
    proxy = DataProxy(source)
    result = cast_to_int(proxy).df
    assert result["data"].dtype == pl.Int32
    assert result["data"].to_list() == [1, 0, None]
    assert result.select("datetime", "vt_symbol").equals(source.select("datetime", "vt_symbol"))
    assert proxy.df["data"].dtype == pl.Boolean
    assert source["flag"].to_list() == [True, False, None]


def test_cast_is_available_to_expression_evaluation() -> None:
    """The built-in expression name must support arithmetic and preserve nulls."""
    source = pl.DataFrame({
        "datetime": [datetime(2026, 1, 1)] * 3,
        "vt_symbol": ["A", "B", "C"],
        "flag": [True, False, None],
    })
    result = calculate_by_expression(source, "cast_to_int(flag) * -1")
    assert result["data"].to_list() == [-1, 0, None]
