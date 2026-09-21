"""Scoped source time-label evidence for SSQuant bars.

Per the time-contract disposition (2026-09-16): neither a global START guess
nor a permanent blanket rejection of SSQuant is acceptable. Label semantics
are established by CAPTURE/TABLE/RANGE-bound evidence: the fine (1M) and
coarse (5M/15M) tables of the same symbol are compared over an explicit
source-label range, and whichever hypothesis (START or END labels) reproduces
every coarse bar from the fine bars becomes the evidenced convention for
exactly that scope. The evidence identity participates in the transform
version and receipts.

Rows outside the evidenced scope are NOT converted: they keep their original
labels and payload as honest candidates on the inspection path
(``source_time_label_unknown`` / ``outside_label_evidence_scope`` flags), and
can never be published as canonical bars with invented bounds. Minute rows
with evidenced bounds publish with ``trading_date=NULL`` when no calendar
evidence exists (disposition corrections 1-3).
"""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from .errors import ImporterError
from .sqlite_source import parse_table_name

_TZ = timezone.utc


class LabelEvidenceError(ImporterError):
    """Label evidence is inconclusive or misused; no convention is guessed."""


@dataclass(frozen=True)
class LabelEvidence:
    """Capture/table/range-bound label-convention evidence."""

    evidence_id: str
    source_id: str
    capture_sha256: str
    symbol: str
    table_fine: str
    table_coarse: str
    range_start: str  # inclusive source-label bound (YYYY-MM-DD[ HH:MM:SS])
    range_end: str  # exclusive source-label bound
    conclusion: str  # "start" | "end"
    method: str
    bars_compared: int
    coarse_unmatched_fine: int
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_dict(payload: dict[str, Any]) -> LabelEvidence:
        return LabelEvidence(**payload)


@dataclass(frozen=True)
class LabelProfile:
    """Application scope of one :class:`LabelEvidence`.

    Covers exactly one capture (by sha256), one symbol's table family and the
    evidenced source-label range. ``interval_minutes`` is the frequency of the
    table being normalised (1/5/15), read from that table's own name.
    """

    evidence: LabelEvidence
    interval_minutes: int

    def covers(self, table: str, source_label: str) -> bool:
        plan = parse_table_name(table)
        if plan is None:
            return False
        if plan.interval_minutes != self.interval_minutes:
            return False
        if plan.symbol.upper() != self.evidence.symbol.upper():
            return False
        label = str(source_label)
        return self.evidence.range_start <= label < self.evidence.range_end

    @property
    def conclusion(self) -> str:
        return self.evidence.conclusion


def _fetch_rows(
    con: sqlite3.Connection, table: str, start: str, end: str
) -> list[dict[str, Any]]:
    cursor = con.execute(
        f'SELECT * FROM "{table}" WHERE datetime >= ? AND datetime < ? '
        "ORDER BY datetime",
        (start, end),
    )
    columns = [desc[0] for desc in cursor.description]
    return [dict(zip(columns, values, strict=True)) for values in cursor]


def _aggregate(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Aggregate fine bars into one coarse bar (OHLC + summed volume)."""
    if not rows:
        return None
    return {
        "open": rows[0]["open"],
        "high": max(r["high"] for r in rows),
        "low": min(r["low"] for r in rows),
        "close": rows[-1]["close"],
        "volume": sum((r["volume"] or 0) for r in rows),
    }


def _close(a: Any, b: Any) -> bool:
    if a is None or b is None:
        return a is None and b is None
    return math.isclose(float(a), float(b), rel_tol=1e-9, abs_tol=1e-9)


def _matches(coarse: dict[str, Any], aggregated: dict[str, Any] | None) -> bool:
    if aggregated is None:
        return False
    return all(_close(coarse[field], aggregated[field]) for field in ("open", "high", "low", "close", "volume"))


def _evidence_id(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return f"ev-{hashlib.sha256(canonical.encode('utf-8')).hexdigest()[:16]}"


def build_label_evidence(
    con: sqlite3.Connection,
    table_fine: str,
    table_coarse: str,
    range_start: str,
    range_end: str,
    capture_sha256: str = "",
    source_id: str = "ssquant",
) -> LabelEvidence:
    """Establish the label convention for one capture/symbol/range.

    For every coarse bar labelled ``T`` with interval ``m`` minutes, the fine
    bars are aggregated under both hypotheses — START: labels in
    ``[T, T+m)``; END: labels in ``(T-m, T]`` — and compared on
    open/high/low/close/volume. The conclusion is the hypothesis that
    reproduces EVERY coarse bar in the range. If neither hypothesis is
    perfect (or the range has no coarse bars), :class:`LabelEvidenceError`
    is raised: inconclusive evidence never becomes a convention.
    """
    fine_plan = parse_table_name(table_fine)
    coarse_plan = parse_table_name(table_coarse)
    if fine_plan is None or coarse_plan is None:
        raise LabelEvidenceError(f"not bar tables: {table_fine} / {table_coarse}")
    if fine_plan.symbol.upper() != coarse_plan.symbol.upper():
        raise LabelEvidenceError(
            f"table family mismatch: {table_fine} vs {table_coarse}"
        )
    if fine_plan.interval_minutes >= coarse_plan.interval_minutes:
        raise LabelEvidenceError(
            f"fine table {table_fine} must be finer than {table_coarse}"
        )
    step = coarse_plan.interval_minutes
    fine_rows = _fetch_rows(con, table_fine, range_start, range_end)
    coarse_rows = _fetch_rows(con, table_coarse, range_start, range_end)
    if not coarse_rows:
        raise LabelEvidenceError(
            f"no coarse bars of {table_coarse} in [{range_start}, {range_end}); "
            "evidence scope must contain comparable bars"
        )
    fine_by_label = {str(r["datetime"]): r for r in fine_rows}

    def window(label: str, hypothesis: str) -> list[dict[str, Any]]:
        moment = datetime.strptime(label, "%Y-%m-%d %H:%M:%S")
        labels = []
        for offset in range(step):
            if hypothesis == "start":
                delta = offset
            else:  # "end": labels (T - step, T]
                delta = offset - (step - 1)
            candidate = moment + timedelta(minutes=delta)
            row = fine_by_label.get(candidate.strftime("%Y-%m-%d %H:%M:%S"))
            if row is not None:
                labels.append(row)
        return labels

    start_matches = 0
    end_matches = 0
    for coarse in coarse_rows:
        label = str(coarse["datetime"])
        if _matches(coarse, _aggregate(window(label, "start"))):
            start_matches += 1
        if _matches(coarse, _aggregate(window(label, "end"))):
            end_matches += 1
    total = len(coarse_rows)
    if start_matches == total and end_matches != total:
        conclusion = "start"
    elif end_matches == total and start_matches != total:
        conclusion = "end"
    else:
        raise LabelEvidenceError(
            f"inconclusive label evidence for {table_fine}/{table_coarse} over "
            f"[{range_start}, {range_end}): {start_matches}/{total} START vs "
            f"{end_matches}/{total} END matches; refusing to guess"
        )

    evidence_id = _evidence_id(
        {
            "source_id": source_id,
            "capture_sha256": capture_sha256,
            "symbol": fine_plan.symbol.upper(),
            "table_fine": table_fine,
            "table_coarse": table_coarse,
            "range_start": range_start,
            "range_end": range_end,
            "conclusion": conclusion,
            "fine_labels": sorted(fine_by_label),
            "coarse_labels": [str(r["datetime"]) for r in coarse_rows],
        }
    )
    return LabelEvidence(
        evidence_id=evidence_id,
        source_id=source_id,
        capture_sha256=capture_sha256,
        symbol=fine_plan.symbol.upper(),
        table_fine=table_fine,
        table_coarse=table_coarse,
        range_start=range_start,
        range_end=range_end,
        conclusion=conclusion,
        method=f"aggregate {fine_plan.frequency} -> {coarse_plan.frequency} "
        "OHLCV comparison over the evidenced range",
        bars_compared=total,
        coarse_unmatched_fine=total - max(start_matches, end_matches),
        created_at=datetime.now(_TZ).isoformat(timespec="seconds"),
    )


__all__ = [
    "LabelEvidence",
    "LabelEvidenceError",
    "LabelProfile",
    "build_label_evidence",
]
