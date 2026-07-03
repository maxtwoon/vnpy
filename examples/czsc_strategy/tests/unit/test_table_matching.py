import pytest

from chan_strategy.backtest_engine import BacktestEngine


class Adapter:
    def __init__(self, tables):
        self._tables = tables

    def get_tables(self):
        return self._tables


def test_find_table_exact_and_prefix():
    assert BacktestEngine("AP888")._find_table(Adapter(["ap888_1M_raw"])) == "ap888_1M_raw"
    assert BacktestEngine("AP888")._find_table(Adapter(["ap888_custom"])) == "ap888_custom"
    with pytest.raises(ValueError, match="未找到"):
        BacktestEngine("SC")._find_table(Adapter(["sc888_1M_raw"]))


def test_find_table_error_branches():
    assert BacktestEngine("AP888")._find_table(Adapter([])) is None
    with pytest.raises(ValueError, match="未找到"):
        BacktestEngine("NOPE")._find_table(Adapter(["ap888_1M_raw"]))
    with pytest.raises(ValueError, match="多个精确"):
        BacktestEngine("AP888")._find_table(Adapter(["ap888_1M_raw", "AP888_1min_raw"]))
    with pytest.raises(ValueError, match="多个前缀"):
        BacktestEngine("AP888")._find_table(Adapter(["ap888_a", "ap888_b"]))
