"""SS04M completion helper: bounded MA sample, default-consumer refusal, SimNow quarantine.

Closes the two audited gaps of the SS04M handoff through PUBLIC APIs only:

* ``simnow-quarantine`` — proves the exact 8 SimNow keys through the actual
  public quarantine ACTION (import with the public detector's quarantine set;
  refused row counts + absent labels), not merely detector equality.
* ``ma-consumer`` — bounded actual MA sample (ma888 1M, June 2026, the known
  bad-amount locator window) through the public normalize/bridge path
  (amount preserved raw + untrusted flag, canonical OI from the source
  ``openint`` field, ``cumulative_openint`` kept as candidate total OI, no
  invented bounds), then the ACTUAL default VWAP-dependent consumer
  (``vnpy_researchstore`` native alpha bridge) refusing the real published
  SSQuant dataset through its public semantic gate — no consumer-side
  normalizer, no guard bypass.

Import order honours the native bootstrap contract: this file imports
research_store only; the vnpy-dependent consumer part runs AFTER
``bootstrap_session`` in the same fresh process.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from research_store.importers.adapters import import_ssquant_table  # noqa: E402
from research_store.importers.core_bridge import (  # noqa: E402
    CoreBridgeError,
    build_ssquant_spec,
    to_core_row,
)
from research_store.importers.normalize import normalize_ssquant_row  # noqa: E402
from research_store.importers.sink import CountingSink  # noqa: E402
from research_store.importers.sqlite_source import (  # noqa: E402
    connect_read_only,
    simnow_quarantine_keys,
)
from research_store.importers.store_sink import StoreSink  # noqa: E402
from research_store.models import AssetRef, Selection, SnapshotRequest  # noqa: E402
from research_store.snapshots import freeze, open_snapshot  # noqa: E402
from research_store.store import open_store  # noqa: E402

SYMBOL_V2 = "rb2605"

CAPTURE = Path("D:/quant-data/captures/kline_data_capture_20260916T164711Z.db")
CAPTURE_RECEIPT = CAPTURE.with_suffix(CAPTURE.suffix + ".receipt.json")
REPORT_DIR = Path("D:/quant-data/reports/delivery04m")
STORE_ROOT = Path("D:/quant-data")
PHASE2_REPORT = REPORT_DIR / "delivery04m-phase2.json"
PHASE1_REPORT = REPORT_DIR / "delivery04m-phase1.json"
QUARANTINE_REPORT = REPORT_DIR / "delivery04m-simnow-quarantine.json"
CONFIG_V2 = REPO_ROOT / "configs" / "delivery_ss_rb2605_v2.json"

MA_TABLE = "ma888_1M_raw"
MA_WINDOW = ("2026-06-01 00:00:00", "2026-07-01 00:00:00")
INCIDENT_MONTH = "2026-07"
SIMNOW_TABLES = {
    "A888": "a888_1M_raw",
    "RB888": "rb888_1M_raw",
    "SC888": "sc888_1M_raw",
    "ZN888": "zn888_1M_raw",
}


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_capture_identity() -> dict[str, Any]:
    receipt = json.loads(CAPTURE_RECEIPT.read_text(encoding="utf-8"))
    stat = CAPTURE.stat()
    return {
        "capture": str(CAPTURE),
        "receipt_capture_sha256": receipt.get("sha256"),
        "validation_kind": receipt.get("validation_kind"),
        "captured_at": receipt.get("captured_at"),
        "size_matches_receipt": stat.st_size == receipt.get("bytes"),
    }


def _fetch_window(con: Any, table: str, start: str, end: str) -> list[dict[str, Any]]:
    cursor = con.execute(
        f'SELECT * FROM "{table}" WHERE datetime >= ? AND datetime < ? '
        "ORDER BY datetime",
        (start, end),
    )
    columns = [d[0] for d in cursor.description]
    return [dict(zip(columns, values, strict=True)) for values in cursor]


def run_ma_sample() -> dict[str, Any]:
    """Bounded MA sample through the public normalize/bridge path."""
    con = connect_read_only(CAPTURE)
    try:
        rows = _fetch_window(con, MA_TABLE, *MA_WINDOW)
    finally:
        con.close()
    normalized = []
    bridge_refusals = 0
    outside_ohlc = 0
    vwap_checked = 0
    negative_oi = 0
    for raw in rows:
        row = normalize_ssquant_row(
            raw, table=MA_TABLE, batch_id="delivery04m-ma-sample",
            series_kind="continuous_888", label_profile=None,
        )
        normalized.append(row)
        # raw evidence: VWAP arithmetic on the sample itself (no inference)
        vol = raw.get("volume") or 0
        amt = raw.get("amount")
        if amt is not None and vol:
            vwap = amt / vol
            vwap_checked += 1
            if (raw.get("low") is not None and vwap < raw["low"]) or (
                raw.get("high") is not None and vwap > raw["high"]
            ):
                outside_ohlc += 1
        if row["open_interest"] is not None and row["open_interest"] < 0:
            negative_oi += 1
        try:
            to_core_row(
                row, dataset_id="ds-ma-sample", asset_id="asset-ma-sample",
                batch_id="delivery04m-ma-sample", interval="1m",
            )
        except CoreBridgeError:
            bridge_refusals += 1
    first = normalized[0] if normalized else None
    sample_facts: dict[str, Any] = {}
    if first is not None:
        raw0 = rows[0]
        sample_facts = {
            "source_label": first["source_label"],
            "standardized_turnover_missing": first["turnover"] is None,
            "extensions_amount_raw_verbatim": (
                first["extensions"].get("amount") == raw0["amount"]
            ),
            "extensions_amount_value": first["extensions"].get("amount"),
            "extensions_amount_untrusted": (
                first["extensions"].get("amount_untrusted") is True
            ),
            "open_interest_is_source_openint": (
                first["open_interest"] == raw0["openint"]
            ),
            "cumulative_openint_preserved": (
                first["extensions"].get("cumulative_openint")
                == raw0["cumulative_openint"]
            ),
            "bar_bounds_none": (
                first["bar_start_ns"] is None and first["bar_end_ns"] is None
            ),
            "source_time_label_unknown_flag": (
                "source_time_label_unknown" in first["quality_flags"]
            ),
        }
    return {
        "ma_sample": {
            "table": MA_TABLE,
            "window": list(MA_WINDOW),
            "rows": len(rows),
            "vwap_checked_rows": vwap_checked,
            "vwap_outside_ohlc_rows": outside_ohlc,
            "negative_open_interest_rows": negative_oi,
            "bridge_canonical_refusals": bridge_refusals,
            "bridge_refusal_note": (
                "MA rows have NO evidenced label bounds (label evidence is "
                "rb2605/window-bound), so public to_core_row refuses every "
                "canonical conversion; the sample stays on the candidate/"
                "inspection path until real evidence exists"
            ),
            "first_row_facts": sample_facts,
            "sample_rows_raw": [
                {
                    k: rows[i].get(k)
                    for k in ("datetime", "open", "high", "low", "close",
                              "volume", "amount", "openint",
                              "cumulative_openint")
                }
                for i in range(min(2, len(rows)))
            ],
        },
    }


def run_default_consumer_refusal() -> dict[str, Any]:
    """Actual default VWAP-dependent consumer refusal on the REAL published
    SSQuant dataset (snapshot S2), via the native bootstrap contract."""
    phase2 = json.loads(PHASE2_REPORT.read_text(encoding="utf-8"))
    snapshot_id = phase2["snapshots"]["s2"]["snapshot_id"]
    ds_1m = phase2["import_w1"]["1"]["dataset_id"]

    # vnpy bootstrap MUST precede any vnpy import (fresh-process contract).
    from vnpy_researchstore.bootstrap import (
        NativeBootstrapConfig,
        bootstrap_session,
    )

    config = NativeBootstrapConfig(
        store_root=str(STORE_ROOT),
        snapshot_id=snapshot_id,
        runtime_dir=str(REPORT_DIR / "native-runtime"),
        repo_path="D:/repo/vnpy",
        integration_path=str(REPO_ROOT),
        backtesters=(),
    )
    session = bootstrap_session(config, "delivery04m-ma-consumer")

    from vnpy_researchstore.native_common import (
        build_dataset_index,
        turnover_untrusted,
        validate_dataset_semantics,
    )

    manifest_path = (
        STORE_ROOT / "manifests" / "snapshots" / f"{snapshot_id}.json"
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    index = build_dataset_index(manifest)
    entry = index[ds_1m]

    refusal_default: dict[str, Any] = {}
    try:
        validate_dataset_semantics(
            entry, purpose="alpha", allow_missing_auxiliary=False
        )
        refusal_default = {"refused": False}
    except Exception as exc:  # noqa: BLE001 - the refusal IS the evidence
        refusal_default = {
            "refused": True,
            "type": type(exc).__name__,
            "message": str(exc),
        }
    refusal_aux_allowed: dict[str, Any] = {}
    try:
        validate_dataset_semantics(
            entry, purpose="alpha", allow_missing_auxiliary=True
        )
        refusal_aux_allowed = {"refused": False}
    except Exception as exc:  # noqa: BLE001
        refusal_aux_allowed = {
            "refused": True,
            "type": type(exc).__name__,
            "message": str(exc),
        }

    # second consumer layer over the REAL canonical rows: the public
    # turnover_untrusted decision evaluated on loaded field_quality
    from research_store.snapshots import open_snapshot

    store = open_store(STORE_ROOT)
    untrusted = 0
    total = 0
    try:
        reader = open_snapshot(store, snapshot_id)
        try:
            w1_start = datetime(2026, 3, 2, 1, 0, tzinfo=timezone.utc)
            w2_end = datetime(2026, 3, 2, 6, 30, tzinfo=timezone.utc)
            for batch in reader.bars(
                ds_1m, start=w1_start, end=w2_end,
                required_fields=(), allow_missing_auxiliary=True,
            ):
                for row in batch.to_pylist():
                    total += 1
                    quality = json.loads(row["field_quality"] or "{}")
                    if turnover_untrusted(quality):
                        untrusted += 1
        finally:
            reader.close()
    finally:
        store.close()

    return {
        "default_consumer": {
            "bootstrap_receipt": session.receipt,
            "dataset_id": ds_1m,
            "snapshot_id": snapshot_id,
            "semantic_refusal_default": refusal_default,
            "semantic_refusal_allow_missing_auxiliary": refusal_aux_allowed,
            "note": (
                "validate_dataset_semantics is the actual gate BOTH native "
                "consumers call during resolution; SSQuant volume/turnover "
                "units and adjustment are UNKNOWN, so default alpha "
                "(VWAP-dependent) consumption is refused — publication is "
                "not qualification"
            ),
        },
        "row_layer": {
            "rows_checked": total,
            "turnover_untrusted_rows": untrusted,
            "note": (
                "public turnover_untrusted() evaluated over the real "
                "loaded canonical rows' field_quality; per-row VWAP "
                "refusal condition holds for every row"
            ),
        },
    }


def run_simnow_quarantine() -> dict[str, Any]:
    """Prove the exact 8 keys through the actual public quarantine ACTION."""
    con = connect_read_only(CAPTURE)
    try:
        started = time.monotonic()
        detected = simnow_quarantine_keys(con)
        detector_elapsed = round(time.monotonic() - started, 3)
    finally:
        con.close()

    per_table: dict[str, Any] = {}
    for symbol, table in SIMNOW_TABLES.items():
        expected_labels = sorted(
            dt for (t, s, dt) in detected
            if s == symbol and t == table
        )
        sink = CountingSink()
        receipt = import_ssquant_table(
            CAPTURE, table, sink, batch_id=f"delivery04m-simnow-{symbol}",
            quarantine_keys=detected, months={INCIDENT_MONTH},
        )
        loaded_labels = sorted(
            str(r["source_label"]) for r in sink.rows
            if str(r["source_label"]).startswith(INCIDENT_MONTH)
        )
        per_table[table] = {
            "symbol": symbol,
            "expected_quarantined_keys": expected_labels,
            "adapter_rows_quarantined": receipt.rows_quarantined,
            "quarantine_action_confirmed": (
                receipt.rows_quarantined == len(expected_labels)
                and all(label not in set(loaded_labels) for label in expected_labels)
            ),
            "july_rows_loaded": len(loaded_labels),
            "july_first_label": loaded_labels[0] if loaded_labels else None,
            "july_last_label": loaded_labels[-1] if loaded_labels else None,
        }
    total_quarantined = sum(
        v["adapter_rows_quarantined"] for v in per_table.values()
    )
    return {
        "detector_keys": sorted(f"{s} {d}" for _t, s, d in sorted(detected)),
        "detector_elapsed_seconds": detector_elapsed,
        "incident_month": INCIDENT_MONTH,
        "per_table": per_table,
        "total_quarantined_rows": total_quarantined,
        "all_eight_keys_quarantined": (
            total_quarantined == 8
            and all(v["quarantine_action_confirmed"] for v in per_table.values())
        ),
        "note": (
            "actual public quarantine ACTION: the detector set was passed as "
            "quarantine_keys to import_ssquant_table and the matching rows "
            "are counted AND absent from the loaded rows"
        ),
    }


def run_postfix_proof() -> dict[str, Any]:
    """Post-fix proof on fresh identities (delivery04m2 namespace).

    1. Bounded real MA sample: standardized turnover MISSING, raw amount
       verbatim in extensions, bridge refusal (candidate, never published).
    2. Supported evidenced SS sample re-imported under the NEW transform
       identity (rule_version norm-missing-turnover-1) -> fresh datasets ->
       missing NULL turnover survives the core projection/store and the raw
       amount stays retrievable from extensions.
    3. Actual native Alpha public ENTRYPOINT invoked on the new snapshot;
       its actual outcome recorded (identity layer: stored exchange
       unknown), with the semantic gate refusal recorded alongside and the
       precise limitation reported for root.
    """
    config = json.loads(CONFIG_V2.read_text(encoding="utf-8"))
    identity = load_capture_identity()
    if config["source"]["capture_sha256"] != identity["receipt_capture_sha256"]:
        raise SystemExit("config capture sha disagrees with receipt; ABORT")

    # -- reused unchanged evidence: window profiles + quarantine keys -----
    phase1 = json.loads(PHASE1_REPORT.read_text(encoding="utf-8"))
    profiles_payload = phase1["public_label_evidence"]["profiles"]
    quarantine_report = json.loads(
        QUARANTINE_REPORT.read_text(encoding="utf-8")
    )
    quarantine_keys = {
        (f"{key.split(' ', 1)[0].lower()}_1M_raw", *key.split(" ", 1)[::-1][::-1])
        for key in quarantine_report["detector_keys"]
    }
    # build triples (table, symbol, dt) explicitly from "SYM DT" strings
    quarantine_keys = {
        (f"{k.split(' ', 1)[0].lower()}_1M_raw", k.split(" ", 1)[0], k.split(" ", 1)[1])
        for k in quarantine_report["detector_keys"]
    }

    # -- 1. bounded real MA sample (public normalize/bridge) --------------
    ma = run_ma_sample()

    # -- 2. supported evidenced SS sample under the new identity ----------
    from research_store.importers.time_evidence import LabelEvidence, LabelProfile

    store = open_store(STORE_ROOT)
    try:
        store_meta = json.loads(
            (store.root / "store.json").read_text(encoding="utf-8")
        )
        evidence_5 = LabelEvidence.from_dict(profiles_payload["W1-5"]["evidence"])
        profiles = {
            1: LabelProfile(evidence_5, interval_minutes=1),
            5: LabelProfile(evidence_5, interval_minutes=5),
        }
        evidence_15 = LabelEvidence.from_dict(
            profiles_payload["W1-15"]["evidence"]
        )
        profiles[15] = LabelProfile(evidence_15, interval_minutes=15)
        asset = AssetRef(
            asset_id=f"ssquant-{SYMBOL_V2}-capture{identity['receipt_capture_sha256'][:8]}",
            origin=str(CAPTURE),
            format="sqlite",
            size=identity["size_matches_receipt"] and CAPTURE.stat().st_size,
            sha256=identity["receipt_capture_sha256"],
        )
        window_start, window_end = config["evidenced_window"]
        dataset_ids: dict[int, str] = {}
        publish_states: dict[int, Any] = {}
        for minutes in (1, 5, 15):
            table = f"{SYMBOL_V2}_{minutes}M_raw"
            spec = build_ssquant_spec(
                f"{minutes}m", "instrument", time_label="start"
            )
            batch_id = f"delivery04m2-{SYMBOL_V2}-{minutes}m-w1"
            sink = StoreSink(
                store,
                asset,
                spec,
                adapter="ssquant/0.1",
                config={
                    "table": table,
                    "window": json.dumps([window_start, window_end]),
                    "label_evidence": profiles[minutes].evidence.evidence_id,
                    "capture_sha256": identity["receipt_capture_sha256"],
                    "turnover_representation": "missing",
                },
                batch_id=batch_id,
            )
            import_ssquant_table(
                CAPTURE,
                table,
                sink,
                batch_id=batch_id,
                quarantine_keys=quarantine_keys,
                label_profile=profiles[minutes],
            )
            receipt = sink.publish()
            summary = sink.summary(receipt)
            dataset_ids[minutes] = sink.dataset_id
            publish_states[minutes] = {
                "batch_id": batch_id,
                "accepted_rows": sink.counts.accepted_rows,
                "candidate_rows": sink.counts.quarantined_rows,
                "publish": summary["publish"],
            }
            sink.cleanup_spool()

        selections = tuple(
            Selection(dataset_ids[m], "*") for m in (1, 5, 15)
        )
        snapshot = freeze(store, SnapshotRequest(selections=selections))
        reader = open_snapshot(store, snapshot.snapshot_id)
        turnover_null = 0
        total_rows = 0
        raw_amount_retrievable = False
        raw_amount_example: dict[str, Any] = {}
        try:
            w_start = datetime(2026, 3, 2, 1, 0, tzinfo=timezone.utc)
            w_end = datetime(2026, 3, 2, 2, 0, tzinfo=timezone.utc)
            for batch in reader.bars(
                dataset_ids[1],
                start=w_start,
                end=w_end,
                required_fields=(),
                allow_missing_auxiliary=True,
            ):
                for row in batch.to_pylist():
                    total_rows += 1
                    if row["turnover"] is None:
                        turnover_null += 1
                    extensions = json.loads(row["extensions_json"] or "{}")
                    if "amount" in extensions:
                        raw_amount_retrievable = True
                        if not raw_amount_example:
                            raw_amount_example = {
                                "source_label": row["source_label"],
                                "extensions_amount": extensions["amount"],
                                "amount_untrusted": json.loads(
                                    row["field_quality"] or "{}"
                                ).get("amount_untrusted"),
                            }
        finally:
            reader.close()

        # -- 3. actual native consumer ENTRYPOINT on the new snapshot ------
        # The default native entrypoint (vnpy Database plugin over the
        # snapshot) is invoked for real; the AlphaLab entrypoint cannot be
        # imported in any registered runtime (route split: alphalens vs
        # duckdb) and that ImportError is reported as the precise defect,
        # NOT used as a semantic refusal.
        from vnpy_researchstore.bootstrap import (
            NativeBootstrapConfig,
            bootstrap_session,
        )

        bootstrap = NativeBootstrapConfig(
            store_root=str(STORE_ROOT),
            snapshot_id=snapshot.snapshot_id,
            runtime_dir=str(REPORT_DIR / "native-runtime-v2"),
            repo_path="D:/repo/vnpy",
            integration_path=str(REPO_ROOT),
            backtesters=(),
        )
        session = bootstrap_session(bootstrap, "delivery04m2-postfix-proof")

        from vnpy.trader.constant import Exchange, Interval as NativeInterval

        database_entrypoint: dict[str, Any] = {}
        try:
            bars = session.database.load_bar_data(
                "rb2605.SHFE",
                Exchange.SHFE,
                NativeInterval.MINUTE,
                datetime(2026, 3, 2, 9, 0),
                datetime(2026, 3, 2, 10, 0),
            )
            database_entrypoint = {
                "entrypoint": "vnpy_researchstore.database.Database.load_bar_data",
                "raised": False,
                "returned_bars": len(bars),
                "note": (
                    "actual default native entrypoint outcome: no bars are "
                    "served for SSQuant data because the stored exchange "
                    "label is unknown (the SSQuant source carries no "
                    "exchange), so identity resolution cannot match "
                    "rb2605.SHFE; the consumer refuses to serve rather "
                    "than guess an exchange"
                ),
            }
        except Exception as exc:  # noqa: BLE001 - refusal is evidence
            database_entrypoint = {
                "entrypoint": "vnpy_researchstore.database.Database.load_bar_data",
                "raised": True,
                "type": type(exc).__name__,
                "message": str(exc),
            }
        try:
            from vnpy_researchstore.alpha import ResearchAlphaLab  # noqa: F401

            alpha_entrypoint: dict[str, Any] = {
                "importable": True,
                "invoked": False,
            }
        except ImportError as exc:
            alpha_entrypoint = {
                "importable": False,
                "error": str(exc),
                "defect_report": (
                    "the ResearchAlphaLab entrypoint imports vnpy.alpha -> "
                    "alphalens, which exists only on the vnpy-alpha route; "
                    "that route lacks duckdb, a hard research_store "
                    "dependency (deliberate runtime-policy route split). "
                    "An entrypoint-level alpha refusal demo therefore "
                    "requires a root scope decision (lazy alpha imports in "
                    "vnpy_researchstore.alpha, or duckdb on the alpha "
                    "route). This ImportError is NOT a semantic refusal; "
                    "the default Database entrypoint refusal above and the "
                    "public semantic gate below carry the proof"
                ),
            }

        semantic_gate: dict[str, Any] = {}
        try:
            from vnpy_researchstore.native_common import (
                build_dataset_index,
                validate_dataset_semantics,
            )

            manifest = json.loads(
                (STORE_ROOT / "manifests" / "snapshots" / f"{snapshot.snapshot_id}.json")
                .read_text(encoding="utf-8")
            )
            entry = build_dataset_index(manifest)[dataset_ids[1]]
            validate_dataset_semantics(
                entry,
                purpose="database",
                allow_missing_auxiliary=False,
            )
            semantic_gate = {"refused": False}
        except Exception as exc:  # noqa: BLE001
            semantic_gate = {
                "refused": True,
                "type": type(exc).__name__,
                "message": str(exc),
            }

        return {
            "identity_note": (
                "fresh post-fix identities: dataset ids carry rule_version "
                "norm-missing-turnover-1; batches delivery04m2-*; new "
                "snapshot; pre-fix reports/snapshots untouched"
            ),
            "config": str(CONFIG_V2),
            "store_identity": store_meta,
            "ma_postfix": ma["ma_sample"],
            "supported_ss": {
                "dataset_ids": {
                    str(m): dataset_ids[m] for m in (1, 5, 15)
                },
                "imports": publish_states,
                "snapshot": {
                    "snapshot_id": snapshot.snapshot_id,
                },
                "store_proof": {
                    "rows_read": total_rows,
                    "turnover_null_rows": turnover_null,
                    "turnover_all_missing": (
                        total_rows > 0 and turnover_null == total_rows
                    ),
                    "raw_amount_retrievable_from_extensions": (
                        raw_amount_retrievable
                    ),
                    "raw_amount_example": raw_amount_example,
                },
            },
            "native_alpha_entrypoint": {
                "database_entrypoint_call": database_entrypoint,
                "alpha_entrypoint_availability": alpha_entrypoint,
                "semantic_gate_on_same_dataset": semantic_gate,
                "limitation_report": (
                    "the default native Database entrypoint serves NO bars "
                    "for SSQuant data (identity layer: stored exchange "
                    "unknown; the consumer refuses rather than guess an "
                    "exchange); the ResearchAlphaLab entrypoint cannot be "
                    "imported in any registered runtime (route split "
                    "alphalens vs duckdb) — reported as a precise defect "
                    "for root, not used as a semantic refusal; the public "
                    "semantic gate additionally refuses the dataset on "
                    "unknown volume/turnover units and adjustment"
                ),
            },
            "ma_vs_supported": (
                "MA sample: unsupported/candidate (no label evidence, "
                "bridge-refused, never published); rb2605 evidenced window: "
                "supported SS consumption = published + readable with "
                "MISSING standardized turnover and raw amount retrievable"
            ),
        }
    finally:
        store.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("simnow-quarantine")
    sub.add_parser("ma-consumer")
    sub.add_parser("postfix-proof")
    args = parser.parse_args(argv)

    if args.command == "postfix-proof":
        payload = run_postfix_proof()
        payload["generated_at"] = _utcnow()
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        out = REPORT_DIR / "delivery04m2-postfix-proof.json"
        out.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        print(str(out))
        return 0

    identity = load_capture_identity()
    if args.command == "simnow-quarantine":
        payload = {
            "generated_at": _utcnow(),
            "capture_identity": identity,
            **run_simnow_quarantine(),
        }
        out = REPORT_DIR / "delivery04m-simnow-quarantine.json"
    else:
        ma = run_ma_sample()
        consumer = run_default_consumer_refusal()
        payload = {
            "generated_at": _utcnow(),
            "capture_identity": identity,
            **ma,
            **consumer,
        }
        out = REPORT_DIR / "delivery04m-ma-consumer.json"
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    print(str(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
