"""Import adapter drivers.

Each driver streams one source into a sink using the readers and
normalisers, and returns a receipt dict with input/accepted/duplicate/
quarantine/parse-failure counts plus provenance (archive/member/table/range).

Drivers are streaming and incremental: any subset of years/instruments can
be imported first (smoke), then the remaining archives later through the
same API - never hard-coded sample-only paths.
"""

from __future__ import annotations

import csv
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from .errors import AmbiguousSymbolError, MemberReadError
from .normalize import (
    FuturesLabelScope,
    normalize_jq_daily_row,
    normalize_rq_etf_row,
    normalize_rq_futures_row,
    normalize_ssquant_row,
)
from .readers import (
    MemberStats,
    ParquetSpoolBudget,
    iter_tar_zst_csv,
    iter_tar_zst_parquet,
)
from .repair_index import RepairIndex, annotate_row
from .safeio import iter_gzip_csv_chunks, open_tar_zst, spool_member, validate_member
from .sink import ImportSink
from .sqlite_source import (
    connect_read_only,
    iter_table_months,
    parse_table_name,
    table_time_span,
)


@dataclass
class AdapterReceipt:
    source: str
    adapter: str
    batch_id: str
    archives: list[str] = field(default_factory=list)
    members_ok: int = 0
    members_failed: int = 0
    rows_read: int = 0
    rows_accepted: int = 0
    rows_quarantined: int = 0
    extras: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "adapter": self.adapter,
            "batch_id": self.batch_id,
            "archives": self.archives,
            "members_ok": self.members_ok,
            "members_failed": self.members_failed,
            "rows_read": self.rows_read,
            "rows_accepted": self.rows_accepted,
            "rows_quarantined": self.rows_quarantined,
            "extras": self.extras,
        }


def _should_take_member(
    member_name: str, instruments: set[str] | None
) -> bool:
    if instruments is None:
        return True
    stem = Path(member_name).stem
    return stem in instruments


def import_rq_etf(
    package_dir: str | Path,
    sink: ImportSink,
    batch_id: str,
    frequency: str = "1m",
    years: list[int] | None = None,
    instruments: set[str] | None = None,
    repair_index: RepairIndex | None = None,
    chunk_rows: int = 100_000,
    overlay: bool = False,
) -> AdapterReceipt:
    """Stream RQ ETF/LOF bars from yearly ``tar.zst`` archives into ``sink``.

    Minute labels are END labels converted to half-open UTC ns bounds; daily
    rows key on trading_date. The repair index (already-applied 133-key
    deterministic repairs plus the 2026-09-12 refetch audit) must be loaded
    BEFORE the base archive per the execution contract and annotates matching
    rows; disputed keys are flagged, not silently resolved.

    ``overlay=True`` reads the ``daily_increment_latest__*`` increment
    archives instead of the base archives. Overlays are imported as SEPARATE
    assets with their own verified hashes; same-key/different-value rows
    surface through the core conflict machinery (never last-wins), and the
    uncovered August 2026 window stays a visible coverage gap.
    """
    package = Path(package_dir)
    interval = 0 if frequency == "1d" else 1
    if frequency not in {"1m", "1d"}:
        raise ValueError(f"unsupported frequency: {frequency}")
    if overlay:
        pattern = f"daily_increment_latest__rqdatac_etf_lof_{frequency}_*.tar.zst"
    else:
        pattern = f"rqdatac_etf_lof_{frequency}_*.tar.zst"
    archives = sorted(package.glob(pattern))
    if years is not None:
        wanted = {f"{year}.tar.zst" for year in years}
        archives = [a for a in archives if a.name.endswith(tuple(wanted))]
    receipt = AdapterReceipt(
        source=str(package), adapter="rq_etf", batch_id=batch_id
    )
    for archive in archives:
        receipt.archives.append(archive.name)
        seen_members: set[str] = set()
        failed_members: set[str] = set()
        member_filter = (
            (lambda name: _should_take_member(name, instruments))
            if instruments is not None
            else None
        )
        for stats, chunk in iter_tar_zst_csv(
            archive, chunk_rows=chunk_rows, member_filter=member_filter
        ):
            if chunk is None:
                sink.fail_member(
                    f"{archive.name}:{stats.member}", stats.error or "unknown"
                )
                receipt.members_failed += 1
                failed_members.add(stats.member)
                continue
            member_key = stats.member
            if member_key in failed_members:
                continue  # earlier chunk of this member already failed loudly
            if member_key not in seen_members:
                seen_members.add(member_key)
                sink.open_member(
                    f"{archive.name}:{member_key}",
                    {"rows_so_far": stats.rows_read},
                )
            rows = []
            try:
                for raw in chunk.rows:
                    row = normalize_rq_etf_row(
                        raw,
                        interval_minutes=interval,
                        archive=archive.name,
                        member=member_key,
                        batch_id=batch_id,
                    )
                    if repair_index is not None:
                        annotate_row(row, repair_index)
                    rows.append(row)
            except (KeyError, ValueError, TypeError) as exc:
                sink.fail_member(
                    f"{archive.name}:{member_key}", f"normalize failed: {exc}"
                )
                receipt.members_failed += 1
                failed_members.add(member_key)
                continue
            receipt.rows_read += len(rows)
            receipt.rows_accepted += sink.accept(rows)
        receipt.members_ok += len(seen_members - failed_members)
    if repair_index is not None:
        receipt.extras["repair_stats"] = repair_index.stats()
    return receipt


def import_jq_daily(
    daily_dir: str | Path,
    sink: ImportSink,
    batch_id: str,
    years: list[int] | None = None,
    instruments: set[str] | None = None,
    chunk_rows: int = 100_000,
) -> AdapterReceipt:
    """Stream JoinQuant holographic daily gzip CSVs into ``sink``.

    All 33 columns are preserved; adjustment stays unknown (factor all 1.0);
    empty moneyflow/ST/industry fields stay empty strings in extensions and
    are never coerced to zero.
    """
    directory = Path(daily_dir)
    files = sorted(directory.glob("all_a_daily_*.csv.gz"))
    if years is not None:
        wanted_years = set(years)

        def _year_of(name: str) -> int | None:
            year_match = re.search(r"(\d{4})\.csv\.gz$", name)
            return int(year_match.group(1)) if year_match else None

        files = [f for f in files if _year_of(f.name) in wanted_years]
    receipt = AdapterReceipt(
        source=str(directory), adapter="jq_daily", batch_id=batch_id
    )
    for archive in files:
        receipt.archives.append(archive.name)
        sink.open_member(archive.name, {})
        for chunk in iter_gzip_csv_chunks(archive, chunk_rows=chunk_rows):
            rows = []
            for raw in chunk:
                if instruments is not None and raw["code"] not in instruments:
                    continue
                rows.append(
                    normalize_jq_daily_row(raw, archive=archive.name, batch_id=batch_id)
                )
            receipt.rows_read += len(rows)
            receipt.rows_accepted += sink.accept(rows)
        receipt.members_ok += 1
    return receipt


def import_ssquant_table(
    capture_db: str | Path,
    table: str,
    sink: ImportSink,
    batch_id: str,
    quarantine_keys: set[tuple[str, str, str]] | None = None,
    months: set[str] | None = None,
    chunk_rows: int = 100_000,
    label_profile: Any = None,
) -> AdapterReceipt:
    """Stream one SSQuant table from the consistent capture into ``sink``.

    ``quarantine_keys`` carries ``(table, symbol, datetime)`` triples from
    :func:`simnow_quarantine_keys`; matching rows are counted as quarantined
    and NOT sent to the sink (visible gap, never zero-filled). Real contract
    tables keep their ``real_symbol`` identity; staging tables stream as a
    separate simulated source.

    ``label_profile`` is an optional scoped
    :class:`~research_store.importers.time_evidence.LabelProfile`: rows inside
    its capture/symbol/range scope receive evidenced bar bounds; rows outside
    stay honest candidates with original labels preserved.
    """
    plan = parse_table_name(table)
    if plan is None:
        raise ValueError(f"not a bar table: {table}")
    con = connect_read_only(capture_db)
    try:
        first, last = table_time_span(con, table)
        receipt = AdapterReceipt(
            source=f"{capture_db}::{table}",
            adapter="ssquant",
            batch_id=batch_id,
            extras={
                "symbol": plan.symbol,
                "frequency": plan.frequency,
                "series_kind": plan.series_kind,
                "time_span": [first, last],
            },
        )
        sink.open_member(table, {"series_kind": plan.series_kind})
        receipt.members_ok = 1
        for month, rows_raw in iter_table_months(con, table, chunk_rows=chunk_rows):
            if months is not None and month not in months:
                continue
            rows = []
            for raw in rows_raw:
                key = (table, str(raw.get("symbol", "")).upper(), str(raw["datetime"]))
                if quarantine_keys and key in quarantine_keys:
                    receipt.rows_quarantined += 1
                    continue
                rows.append(
                    normalize_ssquant_row(
                        raw,
                        table=table,
                        batch_id=batch_id,
                        series_kind=plan.series_kind,
                        label_profile=label_profile,
                    )
                )
            receipt.rows_read += len(rows)
            receipt.rows_accepted += sink.accept(rows)
        return receipt
    finally:
        con.close()


def _iter_scoped_member_parquet(
    archive: Path,
    staging_dir: Path,
    members: set[str],
    max_spool_bytes: int,
    slice_rows: int = 500_000,
) -> Iterator[tuple[MemberStats, list[dict[str, Any]] | None]]:
    """Yield ``(MemberStats, rows | None)`` for exactly the named members.

    Built from the same public safeio primitives the full reader applies
    (``open_tar_zst`` / ``validate_member`` / ``spool_member``), restricted
    to the caller's member allow-list so a bounded import never spools or
    parses neighbouring members. Requested names that do not exist in the
    archive raise :class:`MemberReadError` after the scan — never a silent
    skip. Yields the same shapes as ``iter_tar_zst_parquet``.
    """
    import pyarrow.parquet as pq

    budget = ParquetSpoolBudget(max_spool_bytes)
    staging = Path(staging_dir)
    staging.mkdir(parents=True, exist_ok=True)
    seen: set[str] = set()
    tf = open_tar_zst(archive)
    try:
        for member in tf:
            if member.isdir():
                continue
            validate_member(member)
            if member.name not in members:
                continue
            seen.add(member.name)
            stats = MemberStats(member=member.name)
            spool_path: Path | None = None
            try:
                budget.charge(member.size)
                spool_path = spool_member(tf, member, staging)
                with open(spool_path, "rb") as probe:
                    if probe.read(4) != b"PAR1":
                        stats.parse_failed = True
                        stats.error = "missing parquet magic"
                        yield stats, None
                        continue
                table = pq.read_table(spool_path)
                total = table.num_rows
                offset = 0
                while offset < total:
                    end = min(offset + slice_rows, total)
                    stats.rows_read += end - offset
                    yield stats, table.slice(offset, end - offset).to_pylist()
                    offset = end
            except Exception as exc:  # noqa: BLE001 - isolated per member
                stats.parse_failed = True
                stats.error = f"scoped member read failed: {exc}"
                yield stats, None
            finally:
                if spool_path is not None:
                    spool_path.unlink(missing_ok=True)
                    budget.release(member.size)
    finally:
        tf.close()
    missing = members - seen
    if missing:
        raise MemberReadError(
            f"requested member(s) {sorted(missing)} not found in {archive.name}"
        )


def _verify_futures_label_pairing(
    sink: ImportSink,
    dataset: str,
    interval_minutes: int,
    label_scope: FuturesLabelScope | None,
) -> None:
    """Public adapter verification of declared semantics versus evidence.

    A sink that declares its spec (like :class:`StoreSink`) must agree with
    the applied evidence: no scope -> the spec must declare UNKNOWN;
    a scope -> the spec must declare exactly the scope's conclusion. This
    keeps dataset semantic identity and row-level provenance consistent and
    refuses any silent END/START promotion without evidence.
    """
    if interval_minutes == 0 and label_scope is not None:
        raise ValueError(
            "daily futures imports keep date-level semantics; "
            "label_scope applies to minute datasets only"
        )
    if label_scope is not None and not isinstance(label_scope, FuturesLabelScope):
        raise TypeError(
            "label_scope must be a research_store.importers.normalize."
            f"FuturesLabelScope, got {type(label_scope).__name__}"
        )
    if label_scope is not None and label_scope.dataset != dataset:
        raise ValueError(
            f"label_scope targets dataset {label_scope.dataset!r}, "
            f"import targets {dataset!r}"
        )
    spec = getattr(sink, "spec", None)
    if spec is None:
        return
    expected = label_scope.conclusion if label_scope is not None else "unknown"
    actual = getattr(spec.source_time_label, "value", None)
    if actual != expected:
        raise ValueError(
            "sink spec declares source_time_label="
            f"{actual!r} but the import would apply {expected!r}; build the "
            "spec with build_rq_futures_spec(dataset, frequency, "
            "time_label=...) matching the evidence pairing"
        )


def import_rq_futures(
    category_dir: str | Path,
    dataset: str,
    sink: ImportSink,
    batch_id: str,
    staging_dir: str | Path,
    years: list[int] | None = None,
    max_spool_bytes: int = 2 * 1024 * 1024 * 1024,
    interval_minutes: int = 1,
    date_mapper: Any = None,
    universe: list[dict[str, str]] | None = None,
    label_scope: FuturesLabelScope | None = None,
    members: set[str] | None = None,
) -> AdapterReceipt:
    """Stream RQ futures Parquet members into ``sink``.

    ``dominant_*`` datasets preserve ``trading_date``/``dominant_id``/
    ``underlying_symbol``; ``contract_1m_none`` preserves contract identity.
    With a ``date_mapper`` (:class:`ContractDateMapper`), contract rows whose
    exact ``(order_book_id == dominant_id, source datetime)`` key exists in
    the dominant mapping receive the source trading_date with explicit
    lineage (``trading_date_source`` extension + map version); unmatched keys
    keep ``trading_date=None`` and are counted, never propagated. The date
    transfer is independent of label qualification: it applies to candidate
    rows (unknown minute labels) exactly as to canonical ones. With a
    ``universe`` table, three-digit Zhengzhou-style codes are resolved by
    unique universe/date match (never a decade guess); ambiguous codes are
    flagged and counted, keeping their original symbol identity.

    Minute label semantics default to UNKNOWN: rows without a covering
    ``label_scope`` keep their original labels, carry no canonical bounds
    and route to the sink's candidate path. ``label_scope`` must be a typed
    :class:`~research_store.importers.normalize.FuturesLabelScope` whose
    dataset matches and whose conclusion matches the sink spec's declared
    ``source_time_label`` (see :func:`_verify_futures_label_pairing`);
    mismatched pairings raise before any row is read.

    ``members`` optionally restricts the run to named archive members
    (bounded representative imports); names are matched exactly and absent
    names fail loudly. ``years`` keeps filtering whole archives.
    """
    _verify_futures_label_pairing(sink, dataset, interval_minutes, label_scope)
    directory = Path(category_dir)
    pattern = f"rqdatac_{dataset}_*.tar.zst"
    archives = sorted(directory.glob(pattern))
    if years is not None:
        wanted = {f"{year}.tar.zst" for year in years}
        archives = [a for a in archives if a.name.endswith(tuple(wanted))]
    receipt = AdapterReceipt(
        source=str(directory), adapter="rq_futures", batch_id=batch_id
    )
    if label_scope is not None:
        receipt.extras["label_scope_identity"] = label_scope.identity
        receipt.extras["label_conclusion"] = label_scope.conclusion
    if members is not None:
        receipt.extras["members_filter"] = sorted(members)
    resolution_stats: dict[str, int] = {"resolved": 0, "ambiguous": 0, "unmatched": 0}
    for archive in archives:
        receipt.archives.append(archive.name)
        seen: set[str] = set()
        if members is not None:
            member_iter = _iter_scoped_member_parquet(
                archive,
                Path(staging_dir) / archive.stem,
                set(members),
                max_spool_bytes,
            )
        else:
            member_iter = iter_tar_zst_parquet(
                archive,
                staging_dir=Path(staging_dir) / archive.stem,
                max_spool_bytes=max_spool_bytes,
            )
        for stats, rows in member_iter:
            if rows is None:
                if stats.parse_failed:
                    sink.fail_member(
                        f"{archive.name}:{stats.member}", stats.error or "unknown"
                    )
                    receipt.members_failed += 1
                continue
            if stats.member not in seen:
                seen.add(stats.member)
                sink.open_member(f"{archive.name}:{stats.member}", {})
            normalized = []
            for record in rows:
                row = normalize_rq_futures_row(
                    record,
                    dataset=dataset,
                    archive=archive.name,
                    member=stats.member,
                    batch_id=batch_id,
                    interval_minutes=interval_minutes,
                    label_scope=label_scope,
                )
                if not dataset.startswith("dominant_"):
                    if date_mapper is not None:
                        _apply_date_mapper(row, date_mapper)
                    if universe is not None:
                        _apply_universe_resolution(row, universe, resolution_stats)
                normalized.append(row)
            receipt.rows_read += len(normalized)
            receipt.rows_accepted += sink.accept(normalized)
        receipt.members_ok += len(seen)
    if date_mapper is not None:
        receipt.extras["trading_date_transfer"] = date_mapper.stats()
    if universe is not None:
        receipt.extras["identity_resolution"] = resolution_stats
    return receipt


def _apply_date_mapper(row: dict[str, Any], date_mapper: Any) -> None:
    """Transfer a source trading_date by exact dominant-map key, or not."""
    trading_date = date_mapper.lookup(row["instrument"], str(row["source_label"]))
    if trading_date is None:
        return
    row["trading_date"] = trading_date
    row["extensions"]["trading_date_source"] = {
        "method": "dominant_map_exact_key",
        "map_version": date_mapper.mapping.version,
        "key": [row["instrument"], str(row["source_label"])],
    }
    if "trading_date_unknown_no_calendar" in row["quality_flags"]:
        row["quality_flags"].remove("trading_date_unknown_no_calendar")


def _apply_universe_resolution(
    row: dict[str, Any],
    universe: list[dict[str, str]],
    stats: dict[str, int],
) -> None:
    """Resolve contract identity against the universe by unique date match.

    Three-digit codes are tried against every plausible date basis (mapped
    trading_date when present, else the label's natural date and the next day
    for night sessions); the resolution is accepted only when ONE universe
    entry matches across all bases. Four-digit codes resolve by exact
    ``order_book_id`` for exchange attribution. Ambiguity never resolves.
    """
    symbol = str(row["instrument"]).upper()
    dates: list[str] = []
    trading_date = row.get("trading_date")
    if trading_date:
        dates.append(str(trading_date)[:10])
    label_day = str(row.get("source_label") or "")[:10]
    if label_day:
        dates.append(label_day)
        try:
            next_day = (
                date.fromisoformat(label_day) + timedelta(days=1)
            ).isoformat()
            if next_day not in dates:
                dates.append(next_day)
        except ValueError:
            pass
    if not dates:
        stats["unmatched"] += 1
        row["quality_flags"].append("symbol_resolution_no_date_basis")
        return
    if _THREE_DIGIT_RE.match(symbol):
        common: set[str] | None = None
        matched_rows: dict[str, dict[str, str]] = {}
        for day in dates:
            found = {
                entry["order_book_id"].upper(): entry
                for entry in resolve_three_digit_symbol(symbol, day, universe)
            }
            matched_rows.update(found)
            keys = set(found)
            common = keys if common is None else common & keys
        if common is not None and len(common) == 1:
            resolved = matched_rows[next(iter(common))]
            _resolve_into_row(row, resolved, dates)
            stats["resolved"] += 1
        else:
            stats["ambiguous"] += 1
            row["quality_flags"].append("symbol_resolution_ambiguous")
        return
    exact = [u for u in universe if u["order_book_id"].upper() == symbol]
    if len(exact) == 1:
        _resolve_into_row(row, exact[0], dates)
        stats["resolved"] += 1
    elif len(exact) > 1:
        stats["ambiguous"] += 1
        row["quality_flags"].append("symbol_resolution_ambiguous")
    else:
        stats["unmatched"] += 1
        row["quality_flags"].append("symbol_resolution_unmatched")


def _resolve_into_row(
    row: dict[str, Any], universe_entry: dict[str, str], dates: list[str]
) -> None:
    resolved_id = universe_entry["order_book_id"].upper()
    original = str(row["instrument"])
    row["extensions"]["identity_resolution"] = {
        "method": "universe_unique_date",
        "date_bases": dates,
        "source_symbol": original,
    }
    if resolved_id != original:
        row["extensions"]["source_symbol"] = original
        row["instrument"] = resolved_id
    exchange = universe_entry.get("exchange")
    if exchange:
        row["exchange"] = exchange


def load_futures_universe(universe_csv: str | Path) -> list[dict[str, str]]:
    """Load the RQ futures ``universe.csv`` instrument metadata."""
    with open(universe_csv, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


_THREE_DIGIT_RE = re.compile(r"^([A-Z]{1,2})(\d{3})$")


def _valid_date_bound(bound: str | None) -> str | None:
    if not bound or bound in ("null", "None", "0000-00-00"):
        return None
    return bound


def resolve_three_digit_symbol(
    symbol: str, date: str, universe: list[dict[str, str]]
) -> list[dict[str, str]]:
    """Resolve a three-digit contract code against the universe by date.

    Zhengzhou-style codes like ``TA605`` are ambiguous across decades; the
    only safe resolution is the unique universe entry whose
    ``listed_date <= date <= de_listed_date``. Returns matching entries;
    zero or multiple matches raise :class:`AmbiguousSymbolError` at the
    caller (never guess a decade).
    """
    match = _THREE_DIGIT_RE.match(symbol.upper())
    if match is None:
        return [row for row in universe if row["order_book_id"] == symbol.upper()]
    product = match.group(1)
    suffix = match.group(2)
    candidates = []
    for row in universe:
        order_book_id = row["order_book_id"].upper()
        id_match = re.match(r"^([A-Z]{1,2})(\d{3,4})$", order_book_id)
        if not id_match or id_match.group(1) != product:
            continue
        if not id_match.group(2).endswith(suffix):
            continue
        listed = _valid_date_bound(row.get("listed_date"))
        delisted = _valid_date_bound(row.get("de_listed_date"))
        if listed and listed > date:
            continue
        if delisted and date > delisted:
            continue
        candidates.append(row)
    return candidates


def resolve_unique_symbol(
    symbol: str, date: str, universe: list[dict[str, str]]
) -> dict[str, str]:
    """Unique-date variant of :func:`resolve_three_digit_symbol`."""
    candidates = resolve_three_digit_symbol(symbol, date, universe)
    if len(candidates) == 1:
        return candidates[0]
    raise AmbiguousSymbolError(
        f"symbol {symbol!r} on {date}: {len(candidates)} universe matches "
        "(need unique listed/delisted window)"
    )


__all__ = [
    "AdapterReceipt",
    "import_jq_daily",
    "import_rq_etf",
    "import_rq_futures",
    "import_ssquant_table",
    "load_futures_universe",
    "resolve_three_digit_symbol",
    "resolve_unique_symbol",
]
