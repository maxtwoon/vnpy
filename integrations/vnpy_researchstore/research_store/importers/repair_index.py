"""Repair and refetch-conflict indexes for the RQ ETF/LOF dataset.

Facts encoded here (from the source evidence, not assumptions):

* The 133 deterministic repairs (QUALITY_REPAIR_20260905.json +
  ``quality_repair_changes_20260905.csv``) are ALREADY inside the rebuilt
  2016/2017/2018 base archives. The importer loads this index BEFORE the base
  archive so repaired keys can be annotated as repaired observations rather
  than raw vendor output.
* The 2026-09-12 refetch audit
  (``source_refetch_audit.csv``) carries, per repaired key, the old value,
  the repaired value and an independent upstream refetch observation. Rows
  where the repaired value differs from the upstream refetch are DISPUTED:
  candidates are preserved, never silently resolved, and default backtests
  must exclude them leaving visible coverage gaps.
"""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_COMPARE_FIELDS = ("open", "high", "low", "close", "volume", "amount", "num_trades")
# Market fields define default-backtest disputes (the documented 118 keys);
# num_trades-only differences are auxiliary-metadata disputes.
_MARKET_FIELDS = ("open", "high", "low", "close", "volume", "amount")


@dataclass
class RepairEntry:
    """One repaired key with old/new/upstream candidates."""

    instrument: str
    label: str
    rule: str
    old: dict[str, Any]
    new: dict[str, Any]
    upstream: dict[str, Any] | None = None

    @property
    def disputed(self) -> bool:
        """True when repaired MARKET values differ from the upstream refetch.

        Market fields are open/high/low/close/volume/amount; a num_trades-only
        difference (auxiliary metadata) does not dispute the bar's traded
        values - it is counted separately in
        :attr:`disputed_auxiliary_only`.
        """
        return self._differs_on(_MARKET_FIELDS)

    @property
    def disputed_auxiliary_only(self) -> bool:
        """True when only non-market fields (num_trades) differ."""
        return not self.disputed and self._differs_on(_COMPARE_FIELDS)

    def differs_on(self, fields: tuple[str, ...]) -> bool:
        """Public field-subset variant of the dispute check."""
        return self._differs_on(fields)

    def _differs_on(self, fields: tuple[str, ...]) -> bool:
        if self.upstream is None:
            return False
        for name in fields:
            if name in self.new and f"{name}_upstream_refetch" in self.upstream:
                if float(self.new[name]) != float(
                    self.upstream[f"{name}_upstream_refetch"]
                ):
                    return True
        return False

    def key(self) -> tuple[str, str]:
        return (self.instrument, self.label)


@dataclass
class RepairIndex:
    """Lookup index over repaired keys, keyed by (instrument, label)."""

    repair_date: str
    entries: dict[tuple[str, str], RepairEntry] = field(default_factory=dict)
    disputed_keys: set[tuple[str, str]] = field(default_factory=set)
    auxiliary_disputed_keys: set[tuple[str, str]] = field(default_factory=set)

    @property
    def repaired_count(self) -> int:
        return len(self.entries)

    @property
    def disputed_count(self) -> int:
        return len(self.disputed_keys)

    @property
    def disputed_volume_amount_count(self) -> int:
        """Disputed keys whose volume/amount differ (the documented 118)."""
        return sum(
            1
            for key in self.disputed_keys
            if self.entries[key].differs_on(("volume", "amount"))
        )

    def get(self, instrument: str, label: str) -> RepairEntry | None:
        return self.entries.get((instrument, label.strip()))

    def stats(self) -> dict[str, Any]:
        return {
            "repair_date": self.repair_date,
            "repaired_keys": self.repaired_count,
            "disputed_keys": self.disputed_count,
            "disputed_volume_amount_keys": self.disputed_volume_amount_count,
            "auxiliary_only_disputed_keys": len(self.auxiliary_disputed_keys),
        }


def load_repair_index(
    package_dir: str | Path,
    audit_csv: str | Path | None = None,
) -> RepairIndex:
    """Load the repair index for one RQ ETF/LOF package directory.

    Reads ``QUALITY_REPAIR_*.json`` for provenance and the changes CSV for
    per-key before/after values. When ``audit_csv`` (the 2026-09-12
    ``source_refetch_audit.csv``) is provided or auto-discovered in the
    customer-feedback supplement directory, upstream refetch candidates are
    attached and disputed keys flagged.
    """
    package = Path(package_dir)
    repair_json = sorted(package.glob("QUALITY_REPAIR_*.json"))
    if not repair_json:
        raise FileNotFoundError(f"no QUALITY_REPAIR_*.json in {package}")
    meta = json.loads(repair_json[0].read_text(encoding="utf-8"))
    index = RepairIndex(repair_date=str(meta.get("repair_date", "")))

    changes_csv = sorted(package.glob("quality_repair_changes_*.csv"))
    if changes_csv:
        text = changes_csv[0].read_text(encoding="utf-8")
        for row in csv.DictReader(io.StringIO(text)):
            entry = RepairEntry(
                instrument=row["order_book_id"],
                label=row["datetime"],
                rule=row.get("reasons", ""),
                old=json.loads(row["before"]),
                new=json.loads(row["after"]),
            )
            index.entries[entry.key()] = entry

    audit_path = Path(audit_csv) if audit_csv else _find_audit_csv(package)
    if audit_path is not None:
        _attach_audit(index, audit_path)
    return index


def _find_audit_csv(package: Path) -> Path | None:
    candidates = sorted(
        package.glob(
            "RQDataC_customer_feedback_supplement_*/**/source_refetch_audit.csv"
        )
    )
    return candidates[0] if candidates else None


def _attach_audit(index: RepairIndex, audit_path: Path) -> None:
    text = audit_path.read_text(encoding="utf-8")
    for row in csv.DictReader(io.StringIO(text)):
        key = (row["order_book_id"], row["datetime"])
        entry = index.entries.get(key)
        if entry is None:
            entry = RepairEntry(
                instrument=row["order_book_id"],
                label=row["datetime"],
                rule=row.get("repair_rule", ""),
                old={},
                new={},
            )
            index.entries[key] = entry
        entry.rule = row.get("repair_rule", entry.rule)
        for name in _COMPARE_FIELDS:
            old_key = f"{name}_old"
            new_key = f"{name}_new"
            if old_key in row:
                entry.old[name] = row[old_key]
            if new_key in row:
                entry.new[name] = row[new_key]
        entry.upstream = row
        if entry.disputed:
            index.disputed_keys.add(key)
        elif entry.disputed_auxiliary_only:
            index.auxiliary_disputed_keys.add(key)


def annotate_row(row: dict[str, Any], index: RepairIndex) -> dict[str, Any]:
    """Attach repair provenance to a canonical row in place.

    Repaired keys keep current (repaired) values; the annotation records the
    repair rule, old values and upstream refetch candidate so a later
    resolution step can pick candidates explicitly. Disputed keys are flagged
    so coverage/backtest layers can exclude them by default.
    """
    entry = index.get(row["instrument"], row["source_label"])
    if entry is None:
        return row
    row["extensions"]["repair"] = {
        "rule": entry.rule,
        "repair_date": index.repair_date,
        "old": {
            k: v
            for k, v in entry.old.items()
            if k in _COMPARE_FIELDS
        },
        "upstream_refetch": (
            {
                key.removesuffix("_upstream_refetch"): value
                for key, value in entry.upstream.items()
                if key.endswith("_upstream_refetch")
            }
            if entry.upstream is not None
            else None
        ),
    }
    if entry.disputed:
        row["quality_flags"].append("disputed_upstream_refetch")
    elif entry.disputed_auxiliary_only:
        row["quality_flags"].append("disputed_upstream_refetch_auxiliary_only")
    else:
        row["quality_flags"].append("repaired_deterministic")
    return row
