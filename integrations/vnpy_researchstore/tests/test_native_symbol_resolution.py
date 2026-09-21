"""Native symbol-resolution regressions (actual Kimi native06, synthetic fixtures).

Real RQ imports keep the vendor/source identity on disk (``510130.XSHG``),
while normal vnpy callers request the bare native symbol plus exchange
(``symbol=510130, exchange=Exchange.SSE`` / vt_symbol ``510130.SSE``). The
bridge resolves between the two at read time using the actual exchange labels
and the explicit exchange map — it never rewrites the store, never guesses an
exchange from leading digits, never strips arbitrary dotted symbols, and never
silently merges ambiguous bare+suffixed candidates into one native symbol.

Covered here:

* importer-shaped vendor-suffixed identity (``510130.XSHG``) served to a bare
  native request on BOTH the Database and BOTH ResearchAlphaLab load methods,
  with bars stamped under the native symbol and the stored identity preserved
  in ``bar.extra["source_identity"]``;
* existing bare-identity fixtures keep working unchanged;
* ambiguity (bare + vendor-suffixed rows for one native symbol in one dataset)
  is an explicit ``StoreError``, never a silent merge;
* unknown exchange label and wrong-exchange requests keep their explicit
  refusal / empty-result contracts;
* the ORIGINAL unknown-suffix observation, kept distinct from the bare-id
  unknown-label refusal: a stored identity whose suffix is not a declared
  label (``510131.XZZZ``) is never a candidate, so native requests for its
  prefix return no rows (not an error) while the overview diagnostics report
  the present-but-unmappable rows — never guessed, never stripped;
* the snapshot overview presents the NATIVE symbol for a vendor-suffixed
  identity whose suffix maps to the row's own exchange;
* qualified05 range/default-exclusion semantics are preserved on the resolved
  identity (a clean window loads; a window selecting an excluded key refuses).

All fixture data is synthetic and clearly labelled.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pytest

from research_store import (
    CoverageGapError,
    Store,
    StoreError,
)

from test_native_support import (
    DAILY_DATES,
    daily_rows,
    freeze_all,
    import_dataset,
    make_database,
    make_lab,
    vt_constants,
)

# Bound at test-run time, never at collection time (see test_native_database).
Exchange: Any = None
VtInterval: Any = None

# A vendor-suffixed identity in the shape real RQ imports produce.
SUFFIXED_ID = "510130.XSHG"
BARE_SYMBOL = "510130"


@pytest.fixture(scope="module", autouse=True)
def _bind_vnpy() -> None:
    global Exchange, VtInterval
    Exchange, VtInterval = vt_constants()


def _suffixed_rows(
    identity: str = SUFFIXED_ID,
    *,
    exchange: str = "XSHG",
    close0: float = 10.0,
) -> list[dict[str, Any]]:
    """Daily rows stored under one identity (RQ-suffixed or bare), sorted."""

    rows: list[dict[str, Any]] = []
    for i, day in enumerate(DAILY_DATES):
        row = {
            "dataset_id": "DATASET",
            "instrument_id": identity,
            "series_id": None,
            "symbol": identity,
            "exchange": exchange,
            "bar_start": 0,  # patched below
            "bar_end": 0,
            "trading_date": day,
            "source_label": None,
            "open": close0 + i,
            "high": close0 + i + 1,
            "low": close0 + i - 1,
            "close": close0 + i,
            "volume": 100.0,
            "turnover": 1000.0 + i,
            "open_interest": None,
            "completeness": "complete",
            "field_quality": None,
            "contract_id": None,
            "asset_id": "asset-fixture",
            "batch_id": "batch-fixture",
            "transform_version": "t0",
            "extensions_json": None,
        }
        from conftest import ns

        start = ns(day.year, day.month, day.day, 1, 30)
        row["bar_start"] = start
        row["bar_end"] = start + 60 * 1_000_000_000
        rows.append(row)
    return rows


def _mixed_identity_rows() -> list[dict[str, Any]]:
    """Bare + vendor-suffixed rows for one native symbol, sorted by identity key.

    The import requires the stream sorted by (identity, trading_date); the
    bare block sorts before the suffixed block, each internally date-ordered.
    """

    return _suffixed_rows(BARE_SYMBOL) + _suffixed_rows(SUFFIXED_ID)


def _native_dt(day: date) -> datetime:
    return datetime(day.year, day.month, day.day)


# ---------------------------------------------------------------------------
# (a) importer-shaped suffix id -> bare native request, both consumers
# ---------------------------------------------------------------------------


class TestSuffixedIdentityResolution:
    def test_database_bare_request_loads_suffixed_rows(
        self, store: Store, tmp_path: Path
    ) -> None:
        dataset_id = import_dataset(
            store,
            tmp_path,
            _suffixed_rows(),
            asset_name="suffixed-daily.csv",
        )
        snapshot_id = freeze_all(store, [dataset_id])
        db = make_database(store.root, snapshot_id)
        try:
            bars = db.load_bar_data(
                BARE_SYMBOL,
                Exchange.SSE,
                VtInterval.DAILY,
                _native_dt(DAILY_DATES[0]),
                _native_dt(DAILY_DATES[-1]),
            )
            assert len(bars) == len(DAILY_DATES)
            # Bars are stamped under the NATIVE symbol, not the stored id.
            assert all(b.symbol == BARE_SYMBOL for b in bars)
            assert all(b.exchange == Exchange.SSE for b in bars)
            assert all(b.vt_symbol == f"{BARE_SYMBOL}.SSE" for b in bars)
            # The immutable stored identity is preserved for provenance.
            assert all(b.extra["source_identity"] == SUFFIXED_ID for b in bars)
            assert all(b.extra["source_symbol"] == SUFFIXED_ID for b in bars)
            assert all(b.extra["source_exchange_label"] == "XSHG" for b in bars)
        finally:
            db.close()

    def test_alpha_load_bar_data_bare_vt_symbol(
        self, store: Store, tmp_path: Path
    ) -> None:
        dataset_id = import_dataset(
            store,
            tmp_path,
            _suffixed_rows(),
            asset_name="suffixed-daily.csv",
        )
        snapshot_id = freeze_all(store, [dataset_id])
        lab = make_lab(tmp_path / "lab", store, snapshot_id)
        try:
            bars = lab.load_bar_data(
                f"{BARE_SYMBOL}.SSE",
                VtInterval.DAILY,
                _native_dt(DAILY_DATES[0]),
                _native_dt(DAILY_DATES[-1]),
            )
            assert len(bars) == len(DAILY_DATES)
            assert all(b.symbol == BARE_SYMBOL for b in bars)
            assert all(b.exchange == Exchange.SSE for b in bars)
            assert all(b.extra["source_identity"] == SUFFIXED_ID for b in bars)
        finally:
            lab.close()

    def test_alpha_load_bar_df_bare_vt_symbol(
        self, store: Store, tmp_path: Path
    ) -> None:
        dataset_id = import_dataset(
            store,
            tmp_path,
            _suffixed_rows(),
            asset_name="suffixed-daily.csv",
        )
        snapshot_id = freeze_all(store, [dataset_id])
        lab = make_lab(tmp_path / "lab", store, snapshot_id)
        try:
            df = lab.load_bar_df(
                [f"{BARE_SYMBOL}.SSE"],
                VtInterval.DAILY,
                _native_dt(DAILY_DATES[0]),
                _native_dt(DAILY_DATES[-1]),
                0,
            )
            assert df is not None
            assert df.height == len(DAILY_DATES)
            # The dataframe carries the caller's NATIVE vt_symbol, never the
            # stored vendor-suffixed identity.
            assert set(df["vt_symbol"].to_list()) == {f"{BARE_SYMBOL}.SSE"}
        finally:
            lab.close()


# ---------------------------------------------------------------------------
# (b) existing bare-identity fixtures keep working unchanged
# ---------------------------------------------------------------------------


class TestBareIdentityStillSupported:
    def test_database_bare_identity_unchanged(
        self, store: Store, tmp_path: Path
    ) -> None:
        dataset_id = import_dataset(
            store,
            tmp_path,
            daily_rows("000001"),
            asset_name="bare-daily.csv",
        )
        snapshot_id = freeze_all(store, [dataset_id])
        db = make_database(store.root, snapshot_id)
        try:
            bars = db.load_bar_data(
                "000001",
                Exchange.SZSE,
                VtInterval.DAILY,
                _native_dt(DAILY_DATES[0]),
                _native_dt(DAILY_DATES[-1]),
            )
            assert len(bars) == len(DAILY_DATES)
            assert all(b.symbol == "000001" for b in bars)
            # Bare identity: the stored identity IS the native symbol.
            assert all(b.extra["source_identity"] == "000001" for b in bars)
        finally:
            db.close()

    def test_alpha_bare_identity_unchanged(
        self, store: Store, tmp_path: Path
    ) -> None:
        dataset_id = import_dataset(
            store,
            tmp_path,
            daily_rows("000001"),
            asset_name="bare-daily.csv",
        )
        snapshot_id = freeze_all(store, [dataset_id])
        lab = make_lab(tmp_path / "lab", store, snapshot_id)
        try:
            df = lab.load_bar_df(
                ["000001.SZSE"],
                VtInterval.DAILY,
                _native_dt(DAILY_DATES[0]),
                _native_dt(DAILY_DATES[-1]),
                0,
            )
            assert df is not None
            assert set(df["vt_symbol"].to_list()) == {"000001.SZSE"}
        finally:
            lab.close()


# ---------------------------------------------------------------------------
# (c) ambiguity: bare + vendor-suffixed rows for one native symbol in one
#     dataset is an explicit StoreError, never a silent merge
# ---------------------------------------------------------------------------


class TestAmbiguityRefused:
    def test_bare_and_suffixed_same_dataset_refuses(
        self, store: Store, tmp_path: Path
    ) -> None:
        dataset_id = import_dataset(
            store,
            tmp_path,
            _mixed_identity_rows(),
            asset_name="ambiguous-daily.csv",
        )
        snapshot_id = freeze_all(store, [dataset_id])
        db = make_database(store.root, snapshot_id)
        try:
            with pytest.raises(StoreError, match="ambiguous stored identities"):
                db.load_bar_data(
                    BARE_SYMBOL,
                    Exchange.SSE,
                    VtInterval.DAILY,
                    _native_dt(DAILY_DATES[0]),
                    _native_dt(DAILY_DATES[-1]),
                )
        finally:
            db.close()


# ---------------------------------------------------------------------------
# (d) unknown label / wrong exchange keep their explicit contracts
# ---------------------------------------------------------------------------


class TestLabelAndExchangeContracts:
    def test_unknown_exchange_label_refuses(
        self, store: Store, tmp_path: Path
    ) -> None:
        # The stored identity IS a candidate (bare 510131) but its exchange
        # label is unmapped: resolution must refuse, not guess or relabel.
        dataset_id = import_dataset(
            store,
            tmp_path,
            _suffixed_rows("510131", exchange="XZZZ"),
            asset_name="unknown-label.csv",
        )
        snapshot_id = freeze_all(store, [dataset_id])
        db = make_database(store.root, snapshot_id)
        try:
            with pytest.raises(StoreError, match="unmapped exchange label"):
                db.load_bar_data(
                    "510131",
                    Exchange.SSE,
                    VtInterval.DAILY,
                    _native_dt(DAILY_DATES[0]),
                    _native_dt(DAILY_DATES[-1]),
                )
        finally:
            db.close()

    def test_wrong_exchange_returns_empty(
        self, store: Store, tmp_path: Path
    ) -> None:
        dataset_id = import_dataset(
            store,
            tmp_path,
            _suffixed_rows(),
            asset_name="suffixed-daily.csv",
        )
        snapshot_id = freeze_all(store, [dataset_id])
        db = make_database(store.root, snapshot_id)
        try:
            # XSHG maps to SSE, not SZSE: a SZSE request finds no matching rows.
            bars = db.load_bar_data(
                BARE_SYMBOL,
                Exchange.SZSE,
                VtInterval.DAILY,
                _native_dt(DAILY_DATES[0]),
                _native_dt(DAILY_DATES[-1]),
            )
            assert bars == []
        finally:
            db.close()


# ---------------------------------------------------------------------------
# (d2) the ORIGINAL unknown-SUFFIX observation, kept distinct from the
#      bare-identity unknown-LABEL refusal above
# ---------------------------------------------------------------------------


class TestUnknownSuffixIdentityNotACandidate:
    def test_database_unknown_suffix_identity_returns_empty(
        self, store: Store, tmp_path: Path
    ) -> None:
        """Stored ``510131.XZZZ`` vs native request ``510131`` + SSE.

        The suffix label ``XZZZ`` is not declared by the explicit exchange
        map, so ``510131.XZZZ`` is never formed as a candidate for
        ``(510131, Exchange.SSE)`` (candidates are the bare symbol plus
        ``symbol.<declared-label>`` forms only). The instrument-filtered
        discovery scan therefore sees no rows at all and the load returns
        ``[]`` — an empty result, NOT the ``unmapped exchange label``
        refusal. That refusal (``test_unknown_exchange_label_refuses``)
        needs the stored identity itself to be a candidate (bare ``510131``)
        with only its exchange label unmapped. The bridge never guesses an
        exchange for the unknown suffix and never strips it to force a match.
        """
        dataset_id = import_dataset(
            store,
            tmp_path,
            _suffixed_rows("510131.XZZZ", exchange="XZZZ"),
            asset_name="unknown-suffix.csv",
        )
        snapshot_id = freeze_all(store, [dataset_id])
        db = make_database(store.root, snapshot_id)
        try:
            bars = db.load_bar_data(
                "510131",
                Exchange.SSE,
                VtInterval.DAILY,
                _native_dt(DAILY_DATES[0]),
                _native_dt(DAILY_DATES[-1]),
            )
            assert bars == []
            # Ordinary absence stays distinguishable from present-but-
            # unmappable data: the overview omits the rows (their label has
            # no native Exchange to present) but reports them in the declared
            # diagnostics surface with the verbatim unmapped label.
            assert [
                o for o in db.get_bar_overview() if o.interval == VtInterval.DAILY
            ] == []
            assert any("XZZZ" in note for note in db.diagnostics)
            assert any("does not declare" in note for note in db.diagnostics)
        finally:
            db.close()

    def test_alpha_unknown_suffix_identity_returns_empty(
        self, store: Store, tmp_path: Path
    ) -> None:
        dataset_id = import_dataset(
            store,
            tmp_path,
            _suffixed_rows("510131.XZZZ", exchange="XZZZ"),
            asset_name="unknown-suffix.csv",
        )
        snapshot_id = freeze_all(store, [dataset_id])
        lab = make_lab(tmp_path / "lab", store, snapshot_id)
        try:
            assert (
                lab.load_bar_data(
                    "510131.SSE",
                    VtInterval.DAILY,
                    _native_dt(DAILY_DATES[0]),
                    _native_dt(DAILY_DATES[-1]),
                )
                == []
            )
            assert (
                lab.load_bar_df(
                    ["510131.SSE"],
                    VtInterval.DAILY,
                    _native_dt(DAILY_DATES[0]),
                    _native_dt(DAILY_DATES[-1]),
                    0,
                )
                is None
            )
        finally:
            lab.close()


# ---------------------------------------------------------------------------
# (e) overview presents the native symbol for a vendor-suffixed identity
# ---------------------------------------------------------------------------


class TestOverviewNativeSymbol:
    def test_overview_shows_native_symbol_for_suffixed_identity(
        self, store: Store, tmp_path: Path
    ) -> None:
        dataset_id = import_dataset(
            store,
            tmp_path,
            _suffixed_rows(),
            asset_name="suffixed-daily.csv",
        )
        snapshot_id = freeze_all(store, [dataset_id])
        db = make_database(store.root, snapshot_id)
        try:
            overview = db.get_bar_overview()
            daily = [o for o in overview if o.interval == VtInterval.DAILY]
            assert len(daily) == 1
            entry = daily[0]
            # Presented under the NATIVE symbol, not the stored vendor id.
            assert entry.symbol == BARE_SYMBOL
            assert entry.exchange == Exchange.SSE
            assert entry.count == len(DAILY_DATES)
        finally:
            db.close()


# ---------------------------------------------------------------------------
# (f) qualified05 range/default-exclusion semantics preserved on resolved id
# ---------------------------------------------------------------------------


def _suffixed_rows_with_excluded_day() -> list[dict[str, Any]]:
    """Suffixed-identity rows; ONLY day 1 carries a deterministic-repair flag."""

    rows = _suffixed_rows()
    rows[0]["field_quality"] = json.dumps(
        {"flags": ["repaired_deterministic"], "repair": {"old": 1.0}}
    )
    return rows


class TestQualifiedSemanticsPreserved:
    def test_clean_range_loads_excluded_range_refuses(
        self, store: Store, tmp_path: Path
    ) -> None:
        dataset_id = import_dataset(
            store,
            tmp_path,
            _suffixed_rows_with_excluded_day(),
            asset_name="suffixed-qualified.csv",
        )
        snapshot_id = freeze_all(store, [dataset_id])
        db = make_database(store.root, snapshot_id)
        try:
            # Clean window (days 3-4) loads through the resolved identity.
            clean = db.load_bar_data(
                BARE_SYMBOL,
                Exchange.SSE,
                VtInterval.DAILY,
                _native_dt(DAILY_DATES[2]),
                _native_dt(DAILY_DATES[3]),
            )
            assert len(clean) == 2
            # Window selecting the excluded day refuses (qualified05 contract).
            with pytest.raises(CoverageGapError, match="default-qualified exclusion"):
                db.load_bar_data(
                    BARE_SYMBOL,
                    Exchange.SSE,
                    VtInterval.DAILY,
                    _native_dt(DAILY_DATES[0]),
                    _native_dt(DAILY_DATES[0]),
                )
        finally:
            db.close()
