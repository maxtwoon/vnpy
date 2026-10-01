"""A read-only CTA strategy showing use of the standard history loader."""

from vnpy.trader.constant import Interval
from vnpy.trader.object import BarData
from vnpy_ctastrategy import CtaTemplate


class DataSourceProbeStrategy(CtaTemplate):
    """Count initialization bars; this example never submits an order."""

    author = "Local research"
    bars_received = 0
    variables = ["bars_received"]

    def on_init(self) -> None:
        """CTA routes load_bar through Datafeed when no history gateway exists."""
        self.load_bar(60, interval=Interval.DAILY, callback=self.on_bar)

    def on_bar(self, bar: BarData) -> None:
        """Replace this callback with the research signal calculation."""
        self.bars_received += 1

