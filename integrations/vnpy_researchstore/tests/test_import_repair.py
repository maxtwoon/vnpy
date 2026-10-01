from __future__ import annotations

import io
import json
from pathlib import Path

from research_store.importers.repair_index import (
    annotate_row,
    load_repair_index,
)


def _before_after(volume: str, amount: str, old_amount: str) -> dict[str, str]:
    base = {
        "order_book_id": "160105.XSHE",
        "datetime": "2017-09-19 13:01:00",
        "open": "1.0",
        "high": "1.0",
        "low": "1.0",
        "close": "1.0",
    }
    before = dict(base, volume=volume, amount=old_amount, num_trades="0.0")
    after = dict(base, volume=volume, amount=amount, num_trades="0.0")
    return {"before": json.dumps(before), "after": json.dumps(after)}


def _write_fixture(package: Path, *, disputed: bool) -> None:
    (package / "QUALITY_REPAIR_20260905.json").write_text(
        json.dumps(
            {
                "repair_date": "2026-09-05",
                "stats": {"changed_rows": 1},
                "archives": [],
            }
        ),
        encoding="utf-8",
    )
    changes_row = _before_after("15000", "0", "-100")
    changes_row.update(
        {
            "dataset": "etf_lof",
            "file": "2017/160105.XSHE.csv",
            "order_book_id": "160105.XSHE",
            "datetime": "2017-09-19 13:01:00",
            "reasons": "negative_turnover_or_volume_to_zero",
        }
    )
    import csv
    import io

    out = io.StringIO()
    writer = csv.DictWriter(
        out,
        fieldnames=[
            "dataset",
            "file",
            "order_book_id",
            "datetime",
            "reasons",
            "before",
            "after",
        ],
    )
    writer.writeheader()
    writer.writerow(changes_row)
    (package / "quality_repair_changes_20260905.csv").write_text(
        out.getvalue(), encoding="utf-8"
    )
    audit_dir = package / "RQDataC_customer_feedback_supplement_20260912" / "01_etf_lof"
    audit_dir.mkdir(parents=True, exist_ok=True)
    audit_row = {
        "dataset": "etf_lof",
        "original_file": "2017/160105.XSHE.csv",
        "order_book_id": "160105.XSHE",
        "datetime": "2017-09-19 13:01:00",
        "repair_rule": "negative_turnover_or_volume_to_zero",
        "validation_status": "passed",
        "open_old": "1",
        "open_new": "1",
        "open_upstream_refetch": "1",
        "high_old": "1",
        "high_new": "1",
        "high_upstream_refetch": "1",
        "low_old": "1",
        "low_new": "1",
        "low_upstream_refetch": "1",
        "close_old": "1",
        "close_new": "1",
        "close_upstream_refetch": "1",
        # repaired says 0/0; refetch observed 15000/15840 => disputed
        "volume_old": "15000",
        "volume_new": "0",
        "volume_upstream_refetch": "15000" if disputed else "0",
        "amount_old": "-100",
        "amount_new": "0",
        "amount_upstream_refetch": "15840" if disputed else "0",
        "num_trades_old": "0",
        "num_trades_new": "0",
        "num_trades_upstream_refetch": "0",
    }
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=list(audit_row))
    writer.writeheader()
    writer.writerow(audit_row)
    (audit_dir / "source_refetch_audit.csv").write_text(
        out.getvalue(), encoding="utf-8"
    )


def _sample_row() -> dict:
    from research_store.importers.normalize import normalize_rq_etf_row

    # Simulates a row read from the REPAIRED 2017 base archive: 0/0, while
    # the upstream refetch observed 15000/15840.
    return normalize_rq_etf_row(
        {
            "order_book_id": "160105.XSHE",
            "datetime": "2017-09-19 13:01:00",
            "open": "1.0",
            "high": "1.0",
            "low": "1.0",
            "close": "1.0",
            "volume": "0",
            "amount": "0",
            "num_trades": "0",
        },
        interval_minutes=1,
        archive="rqdatac_etf_lof_1m_2017.tar.zst",
        member="2017/160105.XSHE.csv",
        batch_id="b",
    )


def test_disputed_refetch_key_flagged(tmp_path: Path) -> None:
    _write_fixture(tmp_path, disputed=True)
    index = load_repair_index(tmp_path)
    assert index.repaired_count == 1
    assert index.disputed_count == 1
    row = annotate_row(_sample_row(), index)
    assert "disputed_upstream_refetch" in row["quality_flags"]
    repair = row["extensions"]["repair"]
    assert repair["upstream_refetch"]["volume"] == "15000"
    assert repair["upstream_refetch"]["amount"] == "15840"
    # repaired values stay current; old/upstream candidates are preserved
    assert row["turnover"] == 0.0
    assert row["volume"] == 0.0


def test_matching_repair_annotated_not_disputed(tmp_path: Path) -> None:
    _write_fixture(tmp_path, disputed=False)
    index = load_repair_index(tmp_path)
    assert index.disputed_count == 0
    row = annotate_row(_sample_row(), index)
    assert "repaired_deterministic" in row["quality_flags"]
    assert "disputed_upstream_refetch" not in row["quality_flags"]


def test_unrepaired_key_untouched(tmp_path: Path) -> None:
    _write_fixture(tmp_path, disputed=True)
    index = load_repair_index(tmp_path)
    row = _sample_row()
    row["instrument"] = "510300.XSHG"
    annotate_row(row, index)
    assert "repair" not in row["extensions"]


def test_num_trades_only_diff_is_auxiliary_dispute(tmp_path: Path) -> None:
    # mirrors the real 501003.XSHG 2018-01-15 14:48 key: OHLCV/amount match
    # upstream, only num_trades differs -> NOT a market-field dispute
    _write_fixture(tmp_path, disputed=False)
    package = tmp_path
    audit_dir = package / "RQDataC_customer_feedback_supplement_20260912" / "01_etf_lof"
    import csv as csv_mod

    audit_path = audit_dir / "source_refetch_audit.csv"
    with open(audit_path, encoding="utf-8", newline="") as fh:
        existing = list(csv_mod.DictReader(fh))
    header = list(existing[0].keys())
    audit_row = {name: "" for name in header}
    audit_row.update(
        {
            "order_book_id": "501003.XSHG",
            "datetime": "2018-01-15 14:48:00",
            "repair_rule": "negative_turnover_or_volume_to_zero",
            "open_new": "1",
            "open_upstream_refetch": "1",
            "high_new": "1",
            "high_upstream_refetch": "1",
            "low_new": "1",
            "low_upstream_refetch": "1",
            "close_new": "1",
            "close_upstream_refetch": "1",
            "volume_new": "100",
            "volume_upstream_refetch": "100",
            "amount_new": "100",
            "amount_upstream_refetch": "100",
            "num_trades_new": "0",
            "num_trades_upstream_refetch": "5",
        }
    )
    out = io.StringIO()
    writer = csv_mod.DictWriter(out, fieldnames=header)
    writer.writerow(audit_row)
    with open(audit_path, "a", encoding="utf-8", newline="") as fh:
        fh.write(out.getvalue())
    index = load_repair_index(package)
    assert index.disputed_count == 0
    assert len(index.auxiliary_disputed_keys) == 1
    row = _sample_row()
    row["instrument"] = "501003.XSHG"
    row["source_label"] = "2018-01-15 14:48:00"
    annotate_row(row, index)
    assert "disputed_upstream_refetch_auxiliary_only" in row["quality_flags"]
    assert "disputed_upstream_refetch" not in row["quality_flags"]
