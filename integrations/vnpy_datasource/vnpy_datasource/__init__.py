"""Research client is independent of the optional VeighNa runtime."""

from .client import DataSourceClient, DataSourceError

__all__ = ["DataSourceClient", "DataSourceError", "Datafeed"]
__version__ = "0.2.0"


def __getattr__(name: str):
    """Import the framework adapter only when requested by VeighNa."""
    if name == "Datafeed":
        from .datafeed import DataSourceDatafeed
        return DataSourceDatafeed
    raise AttributeError(name)

