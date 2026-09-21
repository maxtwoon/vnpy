"""Read-only native ``BaseDatabase`` over one immutable research_store snapshot.

Activated through ``SETTINGS["database.name"] = "researchstore"`` so that
``vnpy.trader.database.get_database`` resolves ``vnpy_researchstore.Database``
(see ``bootstrap.py`` for the guarded process setup). There is intentionally
NO SQLite fallback: if this module cannot be imported, the bootstrap fails
loudly instead of silently binding the default database.

Scope (v0.1): native 1m/1h/1d bars from the bound snapshot only; ticks are an
explicit ``UnsupportedCapabilityError``; every save/delete is a
``ReadOnlyError``. The overview is computed from the bound snapshot manifest
and its pinned files alone.
"""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Any

from research_store import (
    ReadOnlyError,
    SnapshotReader,
    Store,
    StoreError,
    UnsupportedCapabilityError,
    open_snapshot,
    open_store,
)
from research_store.snapshots import load_snapshot_manifest

from vnpy.trader.constant import Exchange, Interval
from vnpy.trader.database import BarOverview, BaseDatabase, TickOverview
from vnpy.trader.object import BarData, TickData
from vnpy.trader.setting import SETTINGS

from .native_common import (
    NATIVE_INTERVALS,
    _ns_to_native_datetime,
    build_dataset_index,
    interval_diagnostics,
    load_bars,
    load_exchange_map,
    map_exchange,
    resolve_bar_dataset,
    validate_dataset_semantics,
)

SETTING_ROOT = "researchstore.root"
SETTING_SNAPSHOT = "researchstore.snapshot_id"
SETTING_ALLOW_MISSING_AUX = "researchstore.allow_missing_auxiliary"
SETTING_EXCHANGE_MAP = "researchstore.exchange_map"


def _native_symbol_for_identity(
    identity: str,
    exchange: Exchange,
    exchange_map: dict[str, str],
) -> str:
    """Present a stored identity under its native symbol when unambiguous.

    A dotted identity whose suffix is a label the explicit exchange map knows
    AND that maps to the row's own mapped exchange is the vendor-suffixed form
    of the prefix — present the prefix (the native symbol). Anything else
    (bare id, unknown suffix, suffix mapping to a different exchange) is kept
    verbatim: visible, never silently stripped or relabelled.
    """

    if "." not in identity:
        return identity
    prefix, _, suffix = identity.rpartition(".")
    if not prefix:
        return identity
    if exchange_map.get(suffix) == exchange.value:
        return prefix
    return identity


class Database(BaseDatabase):
    """Snapshot-bound read-only database plugin (class name required by
    ``vnpy.trader.database.get_database``)."""

    def __init__(self) -> None:
        root = SETTINGS.get(SETTING_ROOT)
        snapshot_id = SETTINGS.get(SETTING_SNAPSHOT)
        if not root or not snapshot_id:
            raise StoreError(
                f"researchstore database requires SETTINGS[{SETTING_ROOT!r}] and "
                f"SETTINGS[{SETTING_SNAPSHOT!r}]; run vnpy_researchstore.bootstrap "
                "to configure an isolated process"
            )
        self._allow_missing_auxiliary = bool(
            SETTINGS.get(SETTING_ALLOW_MISSING_AUX, False)
        )
        self._exchange_map = load_exchange_map(SETTINGS.get(SETTING_EXCHANGE_MAP))

        self._store: Store = open_store(str(root))
        self.snapshot_id: str = str(snapshot_id)
        self._manifest: dict[str, Any] = load_snapshot_manifest(
            self._store, self.snapshot_id
        )
        self._reader: SnapshotReader = open_snapshot(self._store, self.snapshot_id)
        self._index = build_dataset_index(self._manifest)
        #: Human-readable notes about snapshot datasets the native bridge
        #: cannot represent (5m/15m intervals, non-bar records, unmapped
        #: exchange labels).
        self.diagnostics: list[str] = interval_diagnostics(self._index)
        #: Receipt of the most recent load_bar_data call.
        self.last_receipt: Any = None

    def close(self) -> None:
        self._reader.close()
        self._store.close()

    # -- read-only contract ---------------------------------------------------

    def save_bar_data(self, bars: list[BarData], stream: bool = False) -> bool:
        raise ReadOnlyError(
            "researchstore Database is a read-only snapshot view; publish new "
            "revisions through research_store.import_asset instead"
        )

    def save_tick_data(self, ticks: list[TickData], stream: bool = False) -> bool:
        raise ReadOnlyError(
            "researchstore Database is a read-only snapshot view; publish new "
            "revisions through research_store.import_asset instead"
        )

    def delete_bar_data(
        self, symbol: str, exchange: Exchange, interval: Interval
    ) -> int:
        raise ReadOnlyError(
            "researchstore Database is a read-only snapshot view; snapshots are "
            "immutable by design"
        )

    def delete_tick_data(self, symbol: str, exchange: Exchange) -> int:
        raise ReadOnlyError(
            "researchstore Database is a read-only snapshot view; snapshots are "
            "immutable by design"
        )

    # -- queries --------------------------------------------------------------

    def load_bar_data(
        self,
        symbol: str,
        exchange: Exchange,
        interval: Interval,
        start: datetime,
        end: datetime,
    ) -> list[BarData]:
        """Load bars with the native INCLUSIVE end contract.

        The final bar timestamp may equal ``end`` and survives (converted
        exactly to the core half-open range plus precise ``<= end`` filtering).
        """
        interval_value = NATIVE_INTERVALS.get(interval)
        if interval_value is None:
            raise UnsupportedCapabilityError(
                f"native interval {interval.value!r} is not served by the "
                "researchstore bridge (5m/15m store data is never relabelled)"
            )
        entry, stored_identity = resolve_bar_dataset(
            self._reader,
            self._index,
            symbol,
            exchange,
            interval_value,
            self._exchange_map,
        )
        if entry is None or stored_identity is None:
            return []
        validate_dataset_semantics(
            entry,
            purpose="database",
            allow_missing_auxiliary=self._allow_missing_auxiliary,
        )
        bars, receipt = load_bars(
            self._reader,
            entry,
            symbol,
            exchange,
            interval,
            start,
            end,
            stored_identity=stored_identity,
            allow_missing_auxiliary=self._allow_missing_auxiliary,
            exchange_map=self._exchange_map,
        )
        self.last_receipt = receipt
        return bars

    def load_tick_data(
        self, symbol: str, exchange: Exchange, start: datetime, end: datetime
    ) -> list[TickData]:
        raise UnsupportedCapabilityError(
            "native tick loading is unsupported in v0.1; query the core "
            "SnapshotReader.ticks() observation path directly"
        )

    # -- overviews (snapshot-only) ---------------------------------------------

    def get_bar_overview(self) -> list[BarOverview]:
        """Per-symbol overview of the bound snapshot; never reads live heads.

        Store datasets at intervals vnpy cannot represent (5m/15m) are omitted
        here and reported in ``self.diagnostics`` — never relabelled as 1m.

        DAILY start/end (and the date identity behind count) use each row's
        ``trading_date`` at midnight — the same native convention
        ``load_bar_data`` uses — never the tz-converted ``bar_start`` (a
        night-session bar may start on a different calendar day than its
        trading day). MINUTE/HOUR entries keep real ``bar_start`` semantics.

        The overview presents the DEFAULT QUALIFIED view: rows excluded by
        the snapshot's default-qualified policy (repaired/disputed keys) are
        omitted from counts and reported in ``self.diagnostics`` — the same
        rows ``load_bar_data`` refuses to return by default.

        Symbols are presented under their NATIVE form: a stored vendor-suffixed
        identity (e.g. ``510130.XSHG``) whose suffix maps to the row's own
        exchange is shown as the bare native symbol (``510130``); any other
        identity is kept verbatim — visible, never silently stripped or
        relabelled.
        """
        overviews: dict[tuple[str, Exchange, Interval], BarOverview] = {}
        for entry in sorted(self._index.values(), key=lambda e: e.dataset_id):
            if str(entry.semantic.get("record_kind", "")) != "bars":
                continue
            native_interval = next(
                (k for k, v in NATIVE_INTERVALS.items() if v == entry.interval), None
            )
            if native_interval is None:
                continue  # recorded in self.diagnostics
            daily = native_interval == Interval.DAILY
            # The overview presents the DEFAULT QUALIFIED view; a snapshot
            # that predates the policy capture cannot present any row as
            # qualified (qualified-fix05 F3).
            if self._reader.default_qualified_status(entry.dataset_id) == "legacy_unqualified":
                raise StoreError(
                    f"dataset {entry.dataset_id} is bound to snapshot "
                    f"{self.snapshot_id} which predates the default-qualified "
                    "policy capture (legacy manifest format); the overview "
                    "cannot present its rows as qualified — re-freeze from "
                    "the current published heads to capture the policy"
                )
            exclusions = self._reader.default_qualified_exclusions(entry.dataset_id)
            excluded_keys = {
                (str(e["instrument"]), int(e["start_ns"]), int(e["end_ns"]))
                for e in exclusions
            }
            omitted = 0
            unmapped_rows = 0
            unmapped_labels: set[str] = set()
            stream = self._reader.bars(
                entry.dataset_id,
                required_fields=(),
                allow_missing_auxiliary=True,
                include_default_excluded=True,
            )
            for batch in stream:
                identities = batch.column("instrument_id").to_pylist()
                series = batch.column("series_id").to_pylist()
                labels = batch.column("exchange").to_pylist()
                starts = batch.column("bar_start").to_pylist()
                ends = batch.column("bar_end").to_pylist()
                trading_dates = batch.column("trading_date").to_pylist() if daily else None
                for i in range(batch.num_rows):
                    identity = identities[i] if identities[i] is not None else series[i]
                    if (
                        identity is not None
                        and starts[i] is not None
                        and ends[i] is not None
                        and (str(identity), int(starts[i]), int(ends[i])) in excluded_keys
                    ):
                        omitted += 1
                        continue
                    exchange = map_exchange(labels[i], self._exchange_map)
                    if identity is None or exchange is None:
                        if identity is not None and labels[i] is not None:
                            # Present but not presentable natively: the label
                            # is not declared by the explicit exchange map.
                            # Keep it distinguishable from ordinary absence
                            # via the declared diagnostics surface below.
                            unmapped_rows += 1
                            unmapped_labels.add(str(labels[i]))
                        continue
                    native_symbol = _native_symbol_for_identity(
                        str(identity), exchange, self._exchange_map
                    )
                    key = (native_symbol, exchange, native_interval)
                    if daily:
                        trading = trading_dates[i] if trading_dates is not None else None
                        if trading is None:
                            raise StoreError(
                                f"daily bar of {identity} in {entry.dataset_id} "
                                "has NULL trading_date; the daily overview "
                                "identity is trading_date (matching "
                                "load_bar_data), never bar_start"
                            )
                        dt = datetime.combine(
                            trading
                            if isinstance(trading, date)
                            else date.fromisoformat(str(trading)),
                            time.min,
                        )
                    else:
                        dt = _ns_to_native_datetime(int(starts[i]))
                    overview = overviews.get(key)
                    if overview is None:
                        overviews[key] = BarOverview(
                            symbol=native_symbol,
                            exchange=exchange,
                            interval=native_interval,
                            count=1,
                            start=dt,
                            end=dt,
                        )
                    else:
                        overview.count += 1
                        if overview.start is None or dt < overview.start:
                            overview.start = dt
                        if overview.end is None or dt > overview.end:
                            overview.end = dt
            if omitted:
                self.diagnostics.append(
                    f"dataset {entry.dataset_id}: {omitted} default-qualified "
                    "excluded row(s) omitted from the overview (repaired/"
                    "disputed keys; load_bar_data refuses them by default)"
                )
            if unmapped_rows:
                self.diagnostics.append(
                    f"dataset {entry.dataset_id}: {unmapped_rows} row(s) carry "
                    f"exchange labels {sorted(unmapped_labels)!r} that the "
                    "native exchange map does not declare; they are omitted "
                    "from the native overview and native requests for their "
                    "symbols find no candidate rows (the stored identities "
                    "stay verbatim in the snapshot; extend the map explicitly "
                    "instead of guessing)"
                )
        return sorted(
            overviews.values(),
            key=lambda o: (o.symbol, o.exchange.value if o.exchange else ""),
        )

    def get_tick_overview(self) -> list[TickOverview]:
        """No native tick view in v0.1 (see load_tick_data)."""
        return []
