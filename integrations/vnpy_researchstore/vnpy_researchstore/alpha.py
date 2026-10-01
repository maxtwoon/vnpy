"""ResearchAlphaLab — read-only snapshot-backed ``vnpy.alpha.AlphaLab``.

Market data comes from one immutable research_store snapshot instead of the
lab's parquet folders; market-data saves are prohibited. The lab result
directory is bound to the snapshot id: reusing a lab directory with a
different snapshot is rejected instead of silently mixing data lineages.

Native preprocessing semantics are preserved exactly: ``extended_days``
windowing, output column shape, OHLC first-close normalization, suspended-row
zero->NaN masking, and the distinct VWAP preprocessing (equity turnover/volume;
futures only with a verified effective multiplier and single-side lot volume).
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import polars as pl

from research_store import (
    ReadOnlyError,
    SnapshotReader,
    Store,
    StoreError,
    open_snapshot,
    open_store,
)
from research_store.snapshots import load_snapshot_manifest

from vnpy.alpha.dataset import to_datetime
from vnpy.alpha.lab import AlphaLab
from vnpy.trader.constant import Exchange, Interval
from vnpy.trader.object import BarData
from vnpy.trader.utility import extract_vt_symbol

from .native_common import (
    OI_NOT_APPLICABLE,
    VERIFIED_SINGLE_SIDE_VOLUME_UNITS,
    build_dataset_index,
    interval_diagnostics,
    load_bars,
    load_exchange_map,
    require_alpha_interval,
    resolve_bar_dataset,
    turnover_untrusted,
    validate_dataset_semantics,
)

BINDING_FILE = ".researchstore_snapshot"


class ResearchAlphaLab(AlphaLab):
    """AlphaLab whose market data is bound to one immutable snapshot."""

    def __init__(
        self,
        lab_path: str,
        store_root: str,
        snapshot_id: str,
        multipliers: dict[str, float] | None = None,
        allow_missing_auxiliary: bool = False,
        exchange_map_path: str | None = None,
    ) -> None:
        self._store: Store = open_store(store_root)
        self.snapshot_id: str = snapshot_id
        self._manifest: dict[str, Any] = load_snapshot_manifest(self._store, snapshot_id)
        self._reader: SnapshotReader = open_snapshot(self._store, snapshot_id)
        self._index = build_dataset_index(self._manifest)
        self._exchange_map = load_exchange_map(exchange_map_path)
        self._allow_missing_auxiliary = allow_missing_auxiliary
        #: Verified effective contract multipliers keyed by vt_symbol. Futures
        #: VWAP refuses to compute without an entry — never a guessed factor.
        self._multipliers: dict[str, float] = dict(multipliers or {})
        self.diagnostics: list[str] = interval_diagnostics(self._index)
        self.last_receipt: Any = None

        # Snapshot-bound result directory: the lab root records its snapshot
        # binding; a conflicting reuse is rejected.
        root = Path(lab_path)
        root.mkdir(parents=True, exist_ok=True)
        binding_path = root / BINDING_FILE
        if binding_path.exists():
            bound = json.loads(binding_path.read_text(encoding="utf-8"))
            if bound.get("snapshot_id") != snapshot_id:
                raise StoreError(
                    f"lab path {root} is bound to snapshot "
                    f"{bound.get('snapshot_id')}, refusing reuse with "
                    f"{snapshot_id}; use a separate lab directory per snapshot"
                )
        else:
            binding_path.write_text(
                json.dumps({"snapshot_id": snapshot_id}, indent=2) + "\n",
                encoding="utf-8",
            )
        super().__init__(str(root / snapshot_id))

    def close(self) -> None:
        self._reader.close()
        self._store.close()

    # -- read-only market data -------------------------------------------------

    def save_bar_data(self, bars: list[BarData]) -> None:
        raise ReadOnlyError(
            "ResearchAlphaLab market data is snapshot-bound and read-only; "
            "publish through research_store.import_asset instead"
        )

    # -- loading ---------------------------------------------------------------

    def _resolve(
        self, vt_symbol: str, interval: Interval
    ) -> tuple[str, Exchange, Any, str] | None:
        symbol, exchange = extract_vt_symbol(vt_symbol)
        interval_value = require_alpha_interval(interval)
        entry, stored_identity = resolve_bar_dataset(
            self._reader,
            self._index,
            symbol,
            exchange,
            interval_value,
            self._exchange_map,
        )
        if entry is None or stored_identity is None:
            return None
        validate_dataset_semantics(
            entry,
            purpose="alpha",
            allow_missing_auxiliary=self._allow_missing_auxiliary,
        )
        return symbol, exchange, entry, stored_identity

    def _check_alpha_time_semantics(self, bars: list[BarData], dataset_id: str) -> None:
        """Alpha backtest qualification refuses unknown trading-date semantics."""

        for bar in bars:
            extra = bar.extra or {}
            if extra.get("trading_date") is None:
                raise StoreError(
                    f"bar of {bar.vt_symbol} @ {bar.datetime} in {dataset_id} has "
                    "unknown trading_date; candidate data with ambiguous time "
                    "semantics cannot become qualified alpha/backtest input"
                )
            if turnover_untrusted(extra.get("field_quality") or {}):
                if self._allow_missing_auxiliary:
                    continue
                raise StoreError(
                    f"turnover of {bar.vt_symbol} @ {bar.datetime} in "
                    f"{dataset_id} is flagged untrusted; default alpha features "
                    "reject it"
                )

    def load_bar_data(
        self,
        vt_symbol: str,
        interval: Interval | str,
        start: datetime | str,
        end: datetime | str,
    ) -> list[BarData]:
        """Load bars from the bound snapshot (native inclusive-end contract)."""

        if isinstance(interval, str):
            interval = Interval(interval)
        start_dt = to_datetime(start)
        end_dt = to_datetime(end)

        resolved = self._resolve(vt_symbol, interval)
        if resolved is None:
            return []
        symbol, exchange, entry, stored_identity = resolved
        bars, receipt = load_bars(
            self._reader,
            entry,
            symbol,
            exchange,
            interval,
            start_dt,
            end_dt,
            stored_identity=stored_identity,
            allow_missing_auxiliary=self._allow_missing_auxiliary,
            exchange_map=self._exchange_map,
        )
        self._check_alpha_time_semantics(bars, entry.dataset_id)
        self.last_receipt = receipt
        return bars

    def load_bar_df(
        self,
        vt_symbols: list[str],
        interval: Interval | str,
        start: datetime | str,
        end: datetime | str,
        extended_days: int,
    ) -> pl.DataFrame | None:
        """Snapshot-backed drop-in for ``AlphaLab.load_bar_df``.

        Preserves the native extended_days windowing, column order, OHLC
        first-close normalization and suspended-row masking. VWAP is computed
        as turnover/volume for equity-like assets and
        turnover/(volume*multiplier) for futures with a verified effective
        multiplier and single-side lot volume; volume==0 yields a missing
        (NaN) VWAP, and missing/untrusted turnover or an unknown multiplier is
        an explicit refusal, not a fabricated value.
        """

        if not vt_symbols:
            return None

        if isinstance(interval, str):
            interval = Interval(interval)
        require_alpha_interval(interval)

        start_dt = to_datetime(start) - timedelta(days=extended_days)
        end_dt = to_datetime(end) + timedelta(days=extended_days // 10)

        dfs: list[pl.DataFrame] = []

        for vt_symbol in vt_symbols:
            resolved = self._resolve(vt_symbol, interval)
            if resolved is None:
                continue
            symbol, exchange, entry, stored_identity = resolved
            bars, receipt = load_bars(
                self._reader,
                entry,
                symbol,
                exchange,
                interval,
                start_dt,
                end_dt,
                stored_identity=stored_identity,
                allow_missing_auxiliary=self._allow_missing_auxiliary,
                exchange_map=self._exchange_map,
            )
            self._check_alpha_time_semantics(bars, entry.dataset_id)
            self.last_receipt = receipt
            if not bars:
                continue

            futures_like = entry.asset_class not in OI_NOT_APPLICABLE
            multiplier: float | None = None
            if futures_like:
                volume_unit = str(entry.semantic.get("volume_unit", ""))
                if volume_unit not in VERIFIED_SINGLE_SIDE_VOLUME_UNITS:
                    raise StoreError(
                        f"dataset {entry.dataset_id} volume unit "
                        f"{volume_unit!r} is not a verified single-side lot "
                        "unit; refusing futures VWAP"
                    )
                multiplier = self._multipliers.get(vt_symbol)
                if multiplier is None or not math.isfinite(multiplier) or multiplier <= 0:
                    raise StoreError(
                        f"no verified effective multiplier configured for "
                        f"{vt_symbol}; pass multipliers={{...}} — a guessed "
                        "factor is never applied"
                    )

            rows: list[dict[str, Any]] = []
            for bar in bars:
                turnover = bar.turnover
                volume = bar.volume
                if (
                    turnover is None
                    or (isinstance(turnover, float) and math.isnan(turnover))
                    or volume == 0
                ):
                    # Zero volume / degraded auxiliary => missing VWAP, never
                    # a fabricated number (float NaN, matching native dtype
                    # behavior in the suspended-row mask).
                    vwap = float("nan")
                elif futures_like:
                    vwap = turnover / (volume * multiplier)  # type: ignore[operator]
                else:
                    vwap = turnover / volume
                rows.append(
                    {
                        "datetime": bar.datetime,
                        "open": bar.open_price,
                        "high": bar.high_price,
                        "low": bar.low_price,
                        "close": bar.close_price,
                        "volume": volume,
                        "turnover": turnover,
                        "open_interest": bar.open_interest,
                        "vwap": vwap,
                    }
                )

            df = pl.DataFrame(rows)

            # Normalize prices (native OHLC first-close semantics)
            close_0: float = df.select(pl.col("close")).item(0, 0)
            df = df.with_columns(
                (pl.col("open") / close_0).alias("open"),
                (pl.col("high") / close_0).alias("high"),
                (pl.col("low") / close_0).alias("low"),
                (pl.col("close") / close_0).alias("close"),
            )

            # Convert zeros to NaN for suspended trading days (native masking)
            numeric_columns: list = df.columns[1:]

            mask: pl.Series = df[numeric_columns].sum_horizontal() == 0

            df = df.with_columns(
                [
                    pl.when(mask).then(float("nan")).otherwise(pl.col(col)).alias(col)
                    for col in numeric_columns
                ]
            )

            df = df.with_columns(pl.lit(vt_symbol).alias("vt_symbol"))

            dfs.append(df)

        if not dfs:
            return None
        result_df: pl.DataFrame = pl.concat(dfs)
        return result_df
