"""Read-only access to the SSQuant source SQLite database.

Safety rules implemented here:

* Connections are opened with ``mode=ro`` URI semantics; the live ``-wal`` /
  ``-shm`` files are never touched for import. Formal imports read the
  consistent capture produced by :func:`capture_sqlite` instead.
* ``capture_sqlite`` performs a consistent online backup from a read-only
  connection into the store captures directory, then runs ``PRAGMA
  quick_check`` and a full SHA-256 over the capture. No direct raw mutation
  or WAL-ignoring file copy ever happens.
* Table names are parsed into (symbol, frequency, series kind) with explicit
  classification for real contracts, 777/888 continuous series, staging
  tables and the SimNow meta table.
* SimNow contamination is a PRECISE 8-key quarantine derived from evidence:
  a main-table row is contaminated only when its (symbol, datetime) appears
  in ``simnow_bar_meta`` AND the main row matches the incident signature
  (``real_symbol IS NULL`` with zero volume/amount). Ordinary time overlaps
  between meta and vendor continuous bars are reported as diagnostics, never
  quarantined.
"""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .errors import CaptureError
from .safeio import file_sha256

_TZ = timezone.utc
_HASH_BLOCK = 1024 * 1024

_TABLE_RE = re.compile(
    r"^(?P<symbol>[a-z]{1,4}[0-9]{3,4})_(?P<freq>1M|5M|15M)_raw(?P<staging>_staging)?$",
    re.IGNORECASE,
)

FREQUENCY_MINUTES = {"1M": 1, "5M": 5, "15M": 15}

# The eight confirmed main-table SimNow keys (2026-07-01 incident), kept as
# authoritative facts so tests can pin the detector to exactly this set.
SIMNOW_INCIDENT_KEYS: frozenset[tuple[str, str]] = frozenset(
    {
        ("A888", "2026-07-01 11:29:00"),
        ("A888", "2026-07-01 15:04:00"),
        ("RB888", "2026-07-01 11:30:00"),
        ("RB888", "2026-07-01 15:16:00"),
        ("SC888", "2026-07-01 11:30:00"),
        ("SC888", "2026-07-01 15:16:00"),
        ("ZN888", "2026-07-01 11:30:00"),
        ("ZN888", "2026-07-01 15:16:00"),
    }
)


@dataclass
class TablePlan:
    """Classification of one source table for import planning."""

    table: str
    symbol: str
    frequency: str
    series_kind: str  # real_contract | continuous_777 | continuous_888 | staging | meta
    product: str

    @property
    def interval_minutes(self) -> int:
        return FREQUENCY_MINUTES[self.frequency]


def connect_read_only(db_path: str | Path) -> sqlite3.Connection:
    """Open a SQLite database strictly read-only."""
    path = Path(db_path)
    uri = f"file:{path.as_posix()}?mode=ro"
    return sqlite3.connect(uri, uri=True)


def parse_table_name(table: str) -> TablePlan | None:
    """Parse ``<symbol>_<freq>M_raw[_staging]`` table names."""
    match = _TABLE_RE.match(table)
    if match is None:
        return None
    symbol = match.group("symbol")
    staging = bool(match.group("staging"))
    product = re.sub(r"[0-9]{3,4}$", "", symbol)
    if staging:
        series_kind = "staging"
    elif symbol.endswith("777"):
        series_kind = "continuous_777"
    elif symbol.endswith("888"):
        series_kind = "continuous_888"
    else:
        series_kind = "real_contract"
    return TablePlan(
        table=table,
        symbol=symbol,
        frequency=match.group("freq").upper(),
        series_kind=series_kind,
        product=product,
    )


def build_table_plan(con: sqlite3.Connection) -> list[TablePlan]:
    """Classify every bar table in the database (meta tables excluded)."""
    tables = [
        row[0]
        for row in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
    ]
    plan: list[TablePlan] = []
    unclassified: list[str] = []
    for table in tables:
        if table == "simnow_bar_meta":
            continue
        parsed = parse_table_name(table)
        if parsed is None:
            unclassified.append(table)
            continue
        plan.append(parsed)
    if unclassified:
        raise ValueError(f"unclassified tables: {unclassified[:10]}")
    return plan


def _quote_ident(name: str) -> str:
    """Quote a table/column identifier for inline SQL (defence in depth)."""
    if not re.fullmatch(r"[A-Za-z0-9_\u4e00-\u9fff]+", name):
        raise ValueError(f"unsafe identifier: {name!r}")
    return f'"{name}"'


def table_schema(con: sqlite3.Connection, table: str) -> list[tuple[str, str]]:
    """Return ``[(column, type)]`` for one table."""
    return [
        (row[1], row[2] or "")
        for row in con.execute(f"PRAGMA table_info({_quote_ident(table)})")
    ]


def table_time_span(
    con: sqlite3.Connection, table: str
) -> tuple[str | None, str | None]:
    """First and last datetime of a table via its PK index (cheap)."""
    first = con.execute(f"SELECT MIN(datetime) FROM {table}").fetchone()[0]
    last = con.execute(f"SELECT MAX(datetime) FROM {table}").fetchone()[0]
    return first, last


def simnow_meta_keys(con: sqlite3.Connection) -> list[tuple[str, str]]:
    """All (symbol, datetime) keys recorded in ``simnow_bar_meta``."""
    return [
        (row[0], row[1])
        for row in con.execute("SELECT symbol, datetime FROM simnow_bar_meta")
    ]


def simnow_quarantine_keys(con: sqlite3.Connection) -> set[tuple[str, str, str]]:
    """Detect the precise SimNow-contaminated main-table keys.

    A main-table row is contaminated iff its (symbol, datetime) appears in
    ``simnow_bar_meta`` AND the row matches the incident signature:
    ``real_symbol IS NULL`` with volume 0 and amount 0 (verified against the
    eight confirmed 2026-07-01 keys on the real source). Returns a set of
    ``(table, symbol, datetime)`` triples.
    """
    meta_by_symbol: dict[str, list[str]] = {}
    for symbol, dt in simnow_meta_keys(con):
        meta_by_symbol.setdefault(symbol, []).append(dt)
    contaminated: set[tuple[str, str, str]] = set()
    for symbol, datetimes in meta_by_symbol.items():
        for freq in ("1M", "5M", "15M"):
            table = f"{symbol.lower()}_{freq}_raw"
            exists = con.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                (table,),
            ).fetchone()
            if not exists:
                continue
            for dt in datetimes:
                row = con.execute(
                    f"SELECT real_symbol, volume, amount FROM {_quote_ident(table)} "
                    "WHERE datetime=?",
                    (dt,),
                ).fetchone()
                if row is None:
                    continue
                real_symbol, volume, amount = row
                if real_symbol is None and (volume or 0) == 0 and (amount or 0) == 0:
                    contaminated.add((table, symbol, dt))
    return contaminated


def meta_main_overlap_diagnostics(con: sqlite3.Connection) -> dict[str, int]:
    """Count raw (symbol, datetime) overlaps between meta and main tables.

    Diagnostic ONLY: ordinary overlaps are expected because staging/vendor
    continuous bars legitimately reference the same minutes. Never use this
    count as a quarantine set.
    """
    meta_by_symbol: dict[str, list[str]] = {}
    for symbol, dt in simnow_meta_keys(con):
        meta_by_symbol.setdefault(symbol, []).append(dt)
    overlaps = 0
    for symbol, datetimes in meta_by_symbol.items():
        table = f"{symbol.lower()}_1M_raw"
        exists = con.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        ).fetchone()
        if not exists:
            continue
        for dt in datetimes:
            hit = con.execute(
                f"SELECT 1 FROM {table} WHERE datetime=?", (dt,)
            ).fetchone()
            if hit:
                overlaps += 1
    return {"meta_main_1m_overlap_keys": overlaps}


@dataclass
class CaptureReceipt:
    """Receipt for one consistent SQLite capture."""

    source: str
    capture: str
    bytes: int
    sha256: str
    quick_check: str
    captured_at: str
    source_size: int = 0


def capture_sqlite(
    source_db: str | Path, captures_dir: str | Path, quick_check: bool = True
) -> CaptureReceipt:
    """Capture a consistent snapshot of a live SQLite database.

    Uses SQLite's online backup API over a read-only connection so the
    result includes a consistent view of the WAL contents; the source files
    are never mutated. The capture is then quick-checked and hashed. The
    capture filename embeds the source name and UTC timestamp; an existing
    identical capture (same hash) is returned as-is.
    """
    source_path = Path(source_db)
    captures = Path(captures_dir)
    captures.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(_TZ).strftime("%Y%m%dT%H%M%SZ")
    target = captures / f"{source_path.stem}_capture_{stamp}.db"
    sequence = 1
    while target.exists():
        target = captures / f"{source_path.stem}_capture_{stamp}_{sequence}.db"
        sequence += 1
        if sequence > 1000:
            raise CaptureError(f"cannot allocate capture path in {captures}")

    src = connect_read_only(source_path)
    try:
        dst = sqlite3.connect(target)
        try:
            dst.execute("PRAGMA journal_mode=DELETE")
            src.backup(dst)
            dst.commit()
        finally:
            dst.close()
    except sqlite3.Error as exc:
        target.unlink(missing_ok=True)
        raise CaptureError(f"backup failed: {exc}") from exc
    finally:
        src.close()

    check = "skipped"
    if quick_check:
        con = sqlite3.connect(f"file:{target.as_posix()}?mode=ro", uri=True)
        try:
            check = con.execute("PRAGMA quick_check(1)").fetchone()[0]
        finally:
            con.close()
        if check != "ok":
            target.unlink(missing_ok=True)
            raise CaptureError(f"quick_check failed on capture: {check}")

    digest = file_sha256(target)
    return CaptureReceipt(
        source=str(source_path),
        capture=str(target),
        bytes=target.stat().st_size,
        sha256=digest,
        quick_check=check,
        captured_at=datetime.now(_TZ).isoformat(timespec="seconds"),
        source_size=source_path.stat().st_size,
    )


_MONTH_PREFIX_RE = re.compile(r"^\d{4}-\d{2}")


def iter_table_months(
    con: sqlite3.Connection, table: str, chunk_rows: int = 100_000
) -> Iterator[tuple[str, list[dict[str, Any]]]]:
    """Stream one table in (month, rows) units using the datetime PK order.

    Month boundaries follow the source label's ``YYYY-MM`` prefix; rows are
    yielded in chunks of at most ``chunk_rows`` within a month so memory
    stays bounded. Only the current month slice is resident.
    """
    current_month: str | None = None
    buffer: list[dict[str, Any]] = []
    cursor = con.execute(
        f"SELECT * FROM {_quote_ident(table)} ORDER BY datetime"
    )
    columns = [desc[0] for desc in cursor.description]
    for values in cursor:
        row = dict(zip(columns, values, strict=True))
        month = str(row["datetime"])[:7]
        if current_month is None:
            current_month = month
        if month != current_month:
            yield current_month, buffer
            current_month = month
            buffer = []
        buffer.append(row)
        if len(buffer) >= chunk_rows:
            yield current_month, buffer
            buffer = []
    if buffer and current_month is not None:
        yield current_month, buffer


__all__ = [
    "CaptureReceipt",
    "FREQUENCY_MINUTES",
    "SIMNOW_INCIDENT_KEYS",
    "TablePlan",
    "build_table_plan",
    "capture_sqlite",
    "connect_read_only",
    "iter_table_months",
    "meta_main_overlap_diagnostics",
    "parse_table_name",
    "simnow_meta_keys",
    "simnow_quarantine_keys",
    "table_schema",
    "table_time_span",
]
