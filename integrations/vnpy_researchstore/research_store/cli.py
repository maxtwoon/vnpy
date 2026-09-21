"""``qstore`` / ``python -m research_store`` command line interface.

Verbs: init, inspect, import, recover, recover-session, seal, replay,
coverage, quality, resolve-conflict, freeze, verify, export, report.

Conventions (execution contract):

* single JSON document on stdout; progress and diagnostics on stderr;
* safe errors with explicit exit statuses (see ``EXIT_*`` below);
* snapshot reads never touch sources and never write;
* recording verbs (recover-session / seal / replay) call the actual core
  session APIs and report typed results; a failed operation returns a
  truthful nonzero exit with actionable JSON — never an empty success,
  a demo substitute, or a pending swallowed as PASS;
* an import that publishes with conflicts exits ``EXIT_CONFLICT`` and reports
  every conflict id; conflicts are never auto-resolved.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from .coverage import fetch_by_source_labels, write_coverage_report
from .export import export_snapshot
from .importers.core_bridge import (
    build_jq_daily_spec,
    build_rq_etf_spec,
    build_rq_futures_spec,
    build_ssquant_spec,
)
from .importers.dominant_map import (
    ContractDateMapper,
    build_dominant_mapping,
    load_dominant_mapping,
    save_dominant_mapping,
)
from .importers.errors import ImporterError
from .importers.adapters import (
    import_jq_daily,
    import_rq_etf,
    import_rq_futures,
    import_ssquant_table,
    load_futures_universe,
)
from .importers.repair_index import load_repair_index
from .importers.safeio import file_sha256
from .importers.sqlite_source import (
    build_table_plan,
    capture_sqlite,
    connect_read_only,
    simnow_quarantine_keys,
)
from .importers.store_sink import StoreSink, candidate_reason_counts
from .importers.time_evidence import LabelEvidence, LabelProfile
from .models import (
    AssetClass,
    AssetRef,
    ConflictResolution,
    KnownGap,
    SealRequest,
    Selection,
    SnapshotRequest,
    StoreError,
)
from .quality import write_quality_report
from .report import write_report
from .revisions import recover, resolve_conflict
from .sealing import SealError, plan_seal
from .session_recovery import SessionRecoveryError
from .snapshots import freeze, load_snapshot_manifest, open_snapshot
from .store import Store, init_store, open_store

# Recording session APIs (WP08/WP09). These are the canonical public entry
# points; the CLI consumes only typed public results.
#
# recording02I corrected the canonical ``research_store.revisions
# .recover_session`` wrapper (re-exported top-level): it now forwards
# ``create_successor`` / ``successor_source_spec`` /
# ``successor_calendar_spec`` faithfully (verified signature), so the CLI
# calls the canonical public wrapper again — the earlier
# ``session_recovery`` direct call was only the interim state while the
# wrapper rejected the documented kwargs. No private attribute is read
# anywhere and no prose id is parsed.
from .journal import open_session
from .revisions import recover_session, seal as seal_session

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_NO_DATA = 2
EXIT_PENDING = 3
EXIT_CONFLICT = 4


def _progress(message: str) -> None:
    print(message, file=sys.stderr)


def _load_json_file(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _verified_asset(
    path: Path, asset_id: str, format: str, sidecar: Path | None = None
) -> AssetRef:
    """Hash the actual input; verify against a sidecar when one exists."""
    digest = file_sha256(path)
    if sidecar is not None and sidecar.is_file():
        from .importers.safeio import read_sha256_sidecar

        expected = read_sha256_sidecar(sidecar)
        if digest != expected:
            raise ImporterError(
                f"sha256 mismatch for {path}: sidecar {expected}, actual {digest}"
            )
    return AssetRef(
        asset_id=asset_id,
        origin=str(path),
        format=format,
        size=path.stat().st_size,
        sha256=digest,
    )


# ---------------------------------------------------------------------------
# import drivers
# ---------------------------------------------------------------------------


def _run_rq_etf(store: Store, config: dict[str, Any], args: argparse.Namespace) -> list[dict[str, Any]]:
    package = Path(config["source_root"])
    repair_index = None
    if not args.overlay and config.get("repair_index"):
        repair_index = load_repair_index(config["repair_index"]["package_dir"])
        _progress(f"repair index: {repair_index.stats()}")
    frequencies = [args.frequency] if args.frequency else config.get("frequencies", ["1m"])
    years: list[int] = args.years or []
    if args.smoke:
        smoke = config.get("smoke", {})
        frequencies = [smoke.get("frequency", "1m")]
        years = list(smoke.get("years", []))
        args.instruments = args.instruments or list(smoke.get("instruments", []))
    elif not years:
        for batch in config.get("batches", []):
            years.extend(batch.get("years", []))
        years = sorted(set(years))
    summaries = []
    for frequency in frequencies:
        prefix = "daily_increment_latest__" if args.overlay else ""
        if args.overlay and not args.years:
            # Overlay increments are a separate asset set: the config's
            # base-year plan must not scope their discovery.
            patterns = [f"{prefix}rqdatac_etf_lof_{frequency}_*.tar.zst"]
        elif years:
            patterns = [
                f"{prefix}rqdatac_etf_lof_{frequency}_{year}.tar.zst" for year in years
            ]
        else:
            patterns = [f"{prefix}rqdatac_etf_lof_{frequency}_*.tar.zst"]
        archives = sorted(
            {path for pattern in patterns for path in package.glob(pattern)}
        )
        if not archives:
            _progress(f"no {prefix}rqdatac_etf_lof_{frequency}_* archives — skipped")
            continue
        for archive in archives:
            _progress(f"importing {archive.name}")
            year_match = re.search(r"_(\d{4})\.tar\.zst$", archive.name)
            year = int(year_match.group(1)) if year_match else None
            asset = _verified_asset(
                archive,
                f"asset-{archive.stem}",
                "tar_zst_csv",
                sidecar=Path(str(archive) + ".sha256"),
            )
            spec = build_rq_etf_spec(frequency)
            instruments = set(args.instruments) if args.instruments else None
            batch_id = f"import-rq_etf-{archive.stem}"
            sink = StoreSink(
                store,
                asset,
                spec,
                adapter="rq_etf/0.1",
                config={
                    "archive": archive.name,
                    "frequency": frequency,
                    "overlay": str(bool(args.overlay)).lower(),
                    "instruments": ",".join(sorted(instruments or [])),
                },
                batch_id=batch_id,
            )
            receipt_adapter = import_rq_etf(
                package,
                sink,
                batch_id=batch_id,
                frequency=frequency,
                years=[year] if year is not None else None,
                instruments=instruments,
                repair_index=repair_index,
                overlay=args.overlay,
            )
            receipt = sink.publish()
            summary = sink.summary(receipt)
            summary["adapter_receipt"] = receipt_adapter.to_dict()
            summaries.append(summary)
            sink.cleanup_spool()
            _progress(
                f"{archive.name}: {summary['counts']} publish="
                f"{summary['publish']['state']}"
            )
    return summaries


def _run_jq_daily(store: Store, config: dict[str, Any], args: argparse.Namespace) -> list[dict[str, Any]]:
    directory = Path(config["source_root"])
    years: list[int] = args.years or []
    if not years:
        for batch in config.get("batches", []):
            years.extend(batch.get("years", []))
        years = sorted(set(years))
    summaries = []
    for year in years:
        files = sorted(directory.glob(f"all_a_daily_{year}.csv.gz"))
        if not files:
            _progress(f"no all_a_daily_{year}.csv.gz — skipped")
            continue
        for archive in files:
            _progress(f"importing {archive.name}")
            asset = _verified_asset(archive, f"asset-{archive.stem}", "gzip_csv")
            spec = build_jq_daily_spec()
            batch_id = f"import-jq_daily-{archive.stem}"
            sink = StoreSink(
                store,
                asset,
                spec,
                adapter="jq_daily/0.1",
                config={"archive": archive.name},
                batch_id=batch_id,
            )
            receipt_adapter = import_jq_daily(
                directory,
                sink,
                batch_id=batch_id,
                years=[year],
                instruments=set(args.instruments) if args.instruments else None,
            )
            receipt = sink.publish()
            summary = sink.summary(receipt)
            summary["adapter_receipt"] = receipt_adapter.to_dict()
            summaries.append(summary)
            sink.cleanup_spool()
            _progress(f"{archive.name}: publish={summary['publish']['state']}")
    return summaries


def _run_rq_futures(store: Store, config: dict[str, Any], args: argparse.Namespace) -> list[dict[str, Any]]:
    directory = Path(config["source_root"])
    dataset = args.dataset or config.get("smoke", {}).get("dataset", "dominant_1d_none")
    years: list[int] = args.years or list(config.get("smoke", {}).get("years", []))
    if dataset == "dominant_map":
        _progress("building dominant mapping artifact (no bar import)")
        mapping = build_dominant_mapping(
            directory, staging_dir=store.path.staging / "dominant_map", years=years or None
        )
        target = save_dominant_mapping(mapping, store.path.configs / "mappings")
        return [{"dominant_map": {**mapping.stats(), "path": str(target)}}]

    date_mapper = None
    map_path = args.dominant_map or config.get("dominant_map")
    if map_path and dataset.startswith("contract_"):
        date_mapper = ContractDateMapper(load_dominant_mapping(map_path))
        _progress(f"dominant map version {date_mapper.mapping.version[:12]} loaded")
    universe = None
    universe_csv = args.universe or config.get("universe", {}).get("csv")
    if universe_csv and dataset.startswith("contract_"):
        candidate = Path(universe_csv)
        if not candidate.is_absolute():
            candidate = directory / candidate
        universe = load_futures_universe(candidate)
        _progress(f"universe: {len(universe)} entries")

    frequency = "1m" if "_1m_" in dataset else "1d"
    interval_minutes = 0 if frequency == "1d" else 1
    summaries = []
    for year in years:
        pattern = f"rqdatac_{dataset}_{year}.tar.zst"
        archives = sorted(directory.glob(pattern))
        if not archives:
            _progress(f"no archive {pattern} — skipped")
            continue
        for archive in archives:
            _progress(f"importing {archive.name}")
            asset = _verified_asset(
                archive,
                f"asset-{archive.stem}",
                "tar_zst_parquet",
                sidecar=Path(str(archive) + ".sha256"),
            )
            spec = build_rq_futures_spec(dataset, frequency)
            batch_id = f"import-rq_futures-{archive.stem}"
            transform_version = "import-v1"
            if date_mapper is not None:
                transform_version += f";dominant_map={date_mapper.mapping.version[:12]}"
            sink = StoreSink(
                store,
                asset,
                spec,
                adapter="rq_futures/0.1",
                config={
                    "archive": archive.name,
                    "dataset": dataset,
                    "dominant_map_version": (
                        date_mapper.mapping.version if date_mapper else ""
                    ),
                },
                batch_id=batch_id,
                transform_version=transform_version,
            )
            receipt_adapter = import_rq_futures(
                directory,
                dataset,
                sink,
                batch_id=batch_id,
                staging_dir=store.path.staging / archive.stem,
                years=[year],
                max_spool_bytes=int(config.get("max_spool_bytes", 2 * 1024 * 1024 * 1024)),
                interval_minutes=interval_minutes,
                date_mapper=date_mapper,
                universe=universe,
            )
            receipt = sink.publish()
            summary = sink.summary(receipt)
            summary["adapter_receipt"] = receipt_adapter.to_dict()
            summaries.append(summary)
            sink.cleanup_spool()
            _progress(f"{archive.name}: publish={summary['publish']['state']}")
    return summaries


def _run_ssquant(store: Store, config: dict[str, Any], args: argparse.Namespace) -> list[dict[str, Any]]:
    capture_db: Path
    if args.capture_db:
        capture_db = Path(args.capture_db)
    else:
        source = Path(config["asset"]["origin"])
        _progress(f"capturing consistent snapshot of {source} (read-only)")
        receipt_capture = capture_sqlite(source, store.path.captures)
        capture_db = Path(receipt_capture.capture)
        _progress(f"capture {capture_db.name} sha256={receipt_capture.sha256[:16]}…")
    capture_sha256 = file_sha256(capture_db)

    profiles: dict[str, LabelProfile] = {}
    if args.label_evidence:
        for payload in _load_json_file(args.label_evidence):
            evidence = LabelEvidence.from_dict(payload["evidence"])
            if evidence.capture_sha256 and evidence.capture_sha256 != capture_sha256:
                raise ImporterError(
                    f"label evidence {evidence.evidence_id} binds capture "
                    f"{evidence.capture_sha256[:12]} but the capture hashes "
                    f"{capture_sha256[:12]}; refusing to apply"
                )
            for freq, minutes in (("1M", 1), ("5M", 5), ("15M", 15)):
                profiles[f"{evidence.symbol}_{freq}"] = LabelProfile(evidence, minutes)

    con = connect_read_only(capture_db)
    try:
        quarantine = simnow_quarantine_keys(con)
        _progress(f"simnow quarantine keys: {len(quarantine)}")
        plan = build_table_plan(con)
    finally:
        con.close()
    tables = [entry.table for entry in plan]
    if args.tables:
        wanted = set(args.tables)
        tables = [table for table in tables if table in wanted]
    months = set(args.months) if args.months else None

    summaries = []
    for table in tables:
        entry = next(e for e in plan if e.table == table)
        frequency = f"{entry.interval_minutes}m"
        profile = profiles.get(f"{entry.symbol.upper()}_{entry.frequency}")
        spec = build_ssquant_spec(
            frequency,
            entry.series_kind,
            time_label=profile.evidence.conclusion if profile else "unknown",
        )
        asset = AssetRef(
            asset_id=f"asset-ssquant-capture-{capture_sha256[:12]}",
            origin=str(capture_db),
            format="sqlite",
            size=capture_db.stat().st_size,
            sha256=capture_sha256,
        )
        batch_id = f"import-ssquant-{table}"
        transform_version = "import-v1"
        if profile is not None:
            transform_version += f";label_evidence={profile.evidence.evidence_id}"
        sink = StoreSink(
            store,
            asset,
            spec,
            adapter="ssquant/0.1",
            config={
                "table": table,
                "capture_sha256": capture_sha256,
                "months": ",".join(sorted(months or [])),
                "label_evidence": (
                    profile.evidence.evidence_id if profile is not None else ""
                ),
            },
            batch_id=batch_id,
            transform_version=transform_version,
        )
        _progress(f"importing table {table} (profile={'yes' if profile else 'no'})")
        receipt_adapter = import_ssquant_table(
            capture_db,
            table,
            sink,
            batch_id=batch_id,
            quarantine_keys=quarantine,
            months=months,
            label_profile=profile,
        )
        receipt = sink.publish()
        summary = sink.summary(receipt)
        summary["adapter_receipt"] = receipt_adapter.to_dict()
        summaries.append(summary)
        sink.cleanup_spool()
        _progress(f"{table}: publish={summary['publish']['state']}")
    return summaries


_IMPORT_DRIVERS = {
    "rq_etf": _run_rq_etf,
    "jq_daily": _run_jq_daily,
    "rq_futures": _run_rq_futures,
    "ssquant": _run_ssquant,
}


def _cmd_import(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    store = open_store(args.root)
    try:
        config = _load_json_file(args.config)
        adapter_key = str(config.get("adapter", "")).split("/")[0]
        driver = _IMPORT_DRIVERS.get(adapter_key)
        if driver is None:
            raise StoreError(f"no CLI import driver for adapter {config.get('adapter')!r}")
        summaries = driver(store, config, args)
    finally:
        store.close()
    conflicts = [
        conflict
        for summary in summaries
        for conflict in summary.get("publish", {}).get("conflicts", [])
    ]
    candidates = {
        summary["batch_id"]: candidate_reason_counts(summary["candidate_file"])
        for summary in summaries
        if summary.get("candidate_file")
    }
    payload: dict[str, Any] = {
        "status": "conflict" if conflicts else "ok",
        "config": str(args.config),
        "imports": summaries,
        "conflict_count": len(conflicts),
        "candidate_reason_counts": candidates,
    }
    return payload, (EXIT_CONFLICT if conflicts else EXIT_OK)


# ---------------------------------------------------------------------------
# other verbs
# ---------------------------------------------------------------------------


def _cmd_init(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    store = init_store(args.root)
    try:
        return {
            "status": "ok",
            "store_id": store.store_id,
            "root": str(store.root),
        }, EXIT_OK
    finally:
        store.close()


def _cmd_inspect(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    store = open_store(args.root)
    try:
        payload: dict[str, Any] = {
            "store_id": store.store_id,
            "root": str(store.root),
            "datasets": [
                {
                    "dataset_id": str(row["dataset_id"]),
                    "semantic": json.loads(str(row["semantic_json"])),
                    "created_at": str(row["created_at"]),
                }
                for row in store.catalog.query_all("SELECT * FROM datasets")
            ],
            "batches": [
                {
                    "batch_id": str(row["batch_id"]),
                    "dataset_id": str(row["dataset_id"]),
                    "adapter": str(row["adapter"]),
                    "state": str(row["state"]),
                    "input_rows": int(row["input_rows"]),
                    "accepted_rows": int(row["accepted_rows"]),
                    "created_at": str(row["created_at"]),
                }
                for row in store.catalog.query_all(
                    "SELECT * FROM batches ORDER BY created_at"
                )
            ],
            "partition_heads": [
                {
                    "dataset_id": str(row["dataset_id"]),
                    "partition": str(row["partition"]),
                    "revision_id": str(row["revision_id"]),
                    "updated_at": str(row["updated_at"]),
                }
                for row in store.catalog.query_all(
                    "SELECT * FROM partition_heads ORDER BY dataset_id, partition"
                )
            ],
            "snapshots": [
                {
                    "snapshot_id": str(row["snapshot_id"]),
                    "created_at": str(row["created_at"]),
                }
                for row in store.catalog.query_all(
                    "SELECT * FROM snapshots ORDER BY created_at"
                )
            ],
            "unresolved_issues": [
                {
                    "issue_id": str(row["issue_id"]),
                    "dataset_id": str(row["scope_dataset_id"]),
                    "partition": str(row["scope_partition"]),
                    "code": str(row["code"]),
                }
                for row in store.catalog.query_all(
                    "SELECT * FROM quality_issues WHERE resolution IS NULL"
                )
            ],
        }
        candidates_dir = store.path.reports / "candidates"
        payload["candidate_files"] = (
            {
                path.name: candidate_reason_counts(path)
                for path in sorted(candidates_dir.glob("*.jsonl.gz"))
            }
            if candidates_dir.is_dir()
            else {}
        )
        if args.source_label:
            if not args.dataset_id:
                raise StoreError("--source-label requires --dataset-id")
            payload["source_label_rows"] = fetch_by_source_labels(
                store, args.dataset_id, list(args.source_label)
            )
        return payload, EXIT_OK
    finally:
        store.close()


def _cmd_recover(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    store = open_store(args.root)
    try:
        report = recover(store, batch_id=args.batch_id)
        return {
            "status": "ok",
            "batches": [
                {
                    "batch_id": item.batch_id,
                    "prior_state": item.prior_state.value,
                    "action": item.action,
                    "error": item.error,
                }
                for item in report.batches
            ],
            "orphan_files": [str(p) for p in report.orphan_files],
        }, EXIT_OK
    finally:
        store.close()


def _cmd_recover_session(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    store = open_store(args.root)
    try:
        report = recover_session(
            store,
            args.session_id,
            create_successor=not args.no_successor,
            successor_source_spec=args.successor_source_spec,
            successor_calendar_spec=args.successor_calendar_spec,
        )
        payload: dict[str, Any] = {
            "status": "ok",
            "session": {
                "session_id": report.session_id,
                "prior_state": report.prior_status,
                "committed_seq": (
                    report.replayed_committed_seq[-1]
                    if report.replayed_committed_seq
                    else 0
                ),
                "committed_events": len(report.replayed_committed_seq),
                "predecessor_session_id": report.predecessor_session_id,
                "successor_session_id": report.successor_session_id,
                "last_error": report.last_error,
                "detail": report.detail,
            },
        }
        # A recovery that recovered the old session but failed to create the
        # requested successor is a partial failure: truthful nonzero exit.
        if report.last_error is not None:
            payload["status"] = "partial"
            return payload, EXIT_ERROR
        return payload, EXIT_OK
    except SessionRecoveryError as exc:
        return {
            "status": "error",
            "verb": "recover-session",
            "message": f"{type(exc).__name__}: {exc}",
        }, EXIT_ERROR
    finally:
        store.close()


def _cmd_seal(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    store = open_store(args.root)
    try:
        payload = _load_json_file(args.request)
        # Revised 02I SealRequest: asset_class/volume_unit/turnover_unit are
        # OPTIONAL with the honest OTHER/unknown defaults (never guessed
        # futures); explicit values must be valid (typed error otherwise).
        # The core validates the combination, the stored session
        # source_spec kind pin, and the source/calendar grammars — a
        # refusal is a typed SealError before any publication.
        required_fields = (
            "session_id",
            "committed_seq_start",
            "committed_seq_end",
            "transform_version",
            "source_spec",
            "calendar_spec",
        )
        missing = [field for field in required_fields if field not in payload]
        if missing:
            raise StoreError(
                f"seal request JSON missing required fields {missing}"
            )
        raw_asset_class = payload.get("asset_class")
        if raw_asset_class is None:
            asset_class = AssetClass.OTHER  # honest default; never guessed
        else:
            try:
                asset_class = AssetClass(str(raw_asset_class))
            except ValueError:
                raise StoreError(
                    f"unknown asset_class {raw_asset_class!r}; "
                    f"known: {[a.value for a in AssetClass]}"
                ) from None
        request = SealRequest(
            session_id=str(payload["session_id"]),
            committed_seq_start=int(payload["committed_seq_start"]),
            committed_seq_end=int(payload["committed_seq_end"]),
            transform_version=str(payload["transform_version"]),
            source_spec=str(payload["source_spec"]),
            calendar_spec=str(payload["calendar_spec"]),
            asset_class=asset_class,
            volume_unit=str(payload.get("volume_unit", "unknown")),
            turnover_unit=str(payload.get("turnover_unit", "unknown")),
        )
        # Pre-check with no side effects first so a refused range reports the
        # plan problem (empty range / beyond watermark / semantics) before any
        # publish.
        plan = plan_seal(store, request)
        receipt = seal_session(store, request)
        return {
            "status": "ok",
            "plan": {
                "committed_watermark": plan.committed_watermark,
                "event_count": plan.event_count,
                "idempotency_key": plan.idempotency_key,
            },
            "seal": {
                "session_id": receipt.session_id,
                "seal_id": receipt.seal_id,
                "dataset_id": receipt.dataset_id,
                "input_events": receipt.input_events,
                "accepted_rows": receipt.accepted_rows,
                "idempotent_replay": receipt.idempotent_replay,
                "partitions": [
                    {
                        "partition": p.partition,
                        "revision_id": p.revision_id,
                        "rows": p.rows,
                    }
                    for p in receipt.partitions
                ],
                "detail": receipt.detail,
            },
        }, EXIT_OK
    except SealError as exc:
        return {
            "status": "error",
            "verb": "seal",
            "message": f"{type(exc).__name__}: {exc}",
        }, EXIT_ERROR
    finally:
        store.close()


def _cmd_replay(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    store = open_store(args.root)
    try:
        # Readonly open accepts OPEN/CLOSED/UNCLEAN_END and never starts a
        # writer; replay yields committed events in (event_ts_ns, seq) order.
        session = open_session(store, args.session_id, readonly=True)
        try:
            events: list[dict[str, Any]] = []
            total = 0
            first_seq: int | None = None
            last_seq: int | None = None
            for event in session.replay_committed():
                total += 1
                first_seq = event.seq if first_seq is None else first_seq
                last_seq = event.seq
                if args.limit is None or len(events) < args.limit:
                    events.append(
                        {
                            "seq": event.seq,
                            "kind": event.kind,
                            "instrument": event.instrument,
                            "event_ts_ns": event.event_ts_ns,
                            "source_event_id": event.source_event_id,
                        }
                    )
        finally:
            session.close()
        return {
            "status": "ok",
            "session_id": args.session_id,
            "committed_events": total,
            "first_seq": first_seq,
            "last_seq": last_seq,
            "events": events,
            "truncated": args.limit is not None and total > len(events),
        }, EXIT_OK
    except StoreError as exc:
        return {
            "status": "error",
            "verb": "replay",
            "message": f"{type(exc).__name__}: {exc}",
        }, EXIT_ERROR
    finally:
        store.close()


def _cmd_coverage(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    store = open_store(args.root)
    try:
        report, path = write_coverage_report(store, args.dataset_id)
        return {
            "status": "ok",
            "report_path": str(path),
            "coverage": report,
        }, EXIT_OK
    finally:
        store.close()


def _cmd_quality(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    store = open_store(args.root)
    try:
        report, path = write_quality_report(
            store, args.dataset_id, partitions=args.partition or None
        )
        return {"status": "ok", "report_path": str(path), "quality": report}, EXIT_OK
    finally:
        store.close()


def _cmd_resolve_conflict(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    store = open_store(args.root)
    try:
        receipt = resolve_conflict(
            store,
            dataset_id=args.dataset_id,
            partition=args.partition,
            conflict_id=args.conflict_id,
            resolution=ConflictResolution(args.resolution),
            reason=args.reason,
        )
        return {
            "status": "ok",
            "revision_id": receipt.revision_id,
            "rows": receipt.rows,
        }, EXIT_OK
    finally:
        store.close()


def _cmd_freeze(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    store = open_store(args.root)
    try:
        payload = _load_json_file(args.request)
        selections = tuple(
            Selection(dataset_id=item[0], partition=item[1])
            for item in payload["selections"]
        )
        gaps = tuple(
            KnownGap(
                dataset_id=gap["dataset_id"],
                start_ns=int(gap["start_ns"]),
                end_ns=int(gap["end_ns"]),
                reason=gap["reason"],
            )
            for gap in payload.get("allow_known_gaps", [])
        )
        request = SnapshotRequest(
            selections=selections,
            required_fields=tuple(
                payload.get("required_fields", ("open", "high", "low", "close", "volume"))
            ),
            allow_known_gaps=gaps,
        )
        ref = freeze(store, request)
        result: dict[str, Any] = {
            "status": "ok",
            "snapshot_id": ref.snapshot_id,
            "manifest_path": str(ref.manifest_path),
            "datasets": list(ref.datasets),
            "created_at": ref.created_at,
        }
        manifest = load_snapshot_manifest(store, ref.snapshot_id)
        exclusions = manifest.get("default_qualified_exclusions", [])
        if exclusions:
            by_dataset: dict[str, int] = {}
            for entry in exclusions:
                by_dataset[entry["dataset_id"]] = (
                    by_dataset.get(entry["dataset_id"], 0) + 1
                )
            result["default_qualified_exclusions"] = {
                "total": len(exclusions),
                "by_dataset": by_dataset,
                "note": (
                    "default qualified reads refuse intersecting queries "
                    "unless the gap is explicitly allowed via "
                    "allow_known_gaps; allowed exclusions stay missing "
                    "from returned rows"
                ),
            }
        return result, EXIT_OK
    finally:
        store.close()


def _cmd_verify(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    from .objects import hash_file, verify_object

    store = open_store(args.root)
    try:
        failures: list[dict[str, str]] = []
        revisions_checked = 0
        objects_checked = 0
        for row in store.catalog.query_all("SELECT * FROM revisions"):
            manifest_path = Path(str(row["manifest_path"]))
            try:
                if not manifest_path.is_file():
                    raise StoreError(f"missing manifest {manifest_path}")
                if hash_file(manifest_path) != str(row["manifest_sha256"]):
                    raise StoreError(f"tampered manifest {manifest_path}")
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                for entry in manifest.get("files", []):
                    verify_object(store.root, str(entry["path"]), str(entry["sha256"]))
                    objects_checked += 1
                revisions_checked += 1
            except StoreError as exc:
                failures.append({"revision_id": str(row["revision_id"]), "error": str(exc)})
        snapshots_checked = 0
        if args.snapshot_id:
            reader = open_snapshot(store, args.snapshot_id)
            try:
                reader.check_integrity()
            finally:
                reader.close()
            snapshots_checked = 1
        else:
            for row in store.catalog.query_all("SELECT * FROM snapshots"):
                manifest_path = Path(str(row["manifest_path"]))
                try:
                    if not manifest_path.is_file():
                        raise StoreError(f"missing snapshot manifest {manifest_path}")
                    if hash_file(manifest_path) != str(row["manifest_sha256"]):
                        raise StoreError(f"tampered snapshot manifest {manifest_path}")
                    snapshots_checked += 1
                except StoreError as exc:
                    failures.append(
                        {"snapshot_id": str(row["snapshot_id"]), "error": str(exc)}
                    )
        return {
            "status": "ok" if not failures else "integrity_failures",
            "revisions_checked": revisions_checked,
            "objects_checked": objects_checked,
            "snapshots_checked": snapshots_checked,
            "failures": failures,
        }, (EXIT_OK if not failures else EXIT_ERROR)
    finally:
        store.close()


def _cmd_export(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    store = open_store(args.root)
    try:
        receipt = export_snapshot(store, args.snapshot_id, args.target, args.format)
        return {"status": "ok", "export": receipt}, EXIT_OK
    finally:
        store.close()


def _cmd_report(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    store = open_store(args.root)
    try:
        report, path = write_report(store, args.output)
        return {"status": "ok", "report_path": str(path), "report": report}, EXIT_OK
    finally:
        store.close()


# ---------------------------------------------------------------------------
# argument parsing
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="qstore",
        description="research_store command line interface (JSON stdout, "
        "progress on stderr)",
    )
    parser.add_argument("--root", help="store root directory")
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("init", help="initialize a store (empty dir or existing store)")

    inspect = commands.add_parser("inspect", help="catalog/assets/issues summary")
    inspect.add_argument("--dataset-id")
    inspect.add_argument(
        "--source-label",
        action="append",
        help="inspection query by ORIGINAL source label (needs --dataset-id); "
        "distinct from normalized bar-time queries",
    )

    imp = commands.add_parser("import", help="run an import config")
    imp.add_argument("--config", required=True, help="import config JSON")
    imp.add_argument("--smoke", action="store_true", help="run the config's smoke scope")
    imp.add_argument("--frequency")
    imp.add_argument("--years", type=int, nargs="*")
    imp.add_argument("--instruments", nargs="*")
    imp.add_argument("--tables", nargs="*", help="SSQuant tables (input work units)")
    imp.add_argument("--months", nargs="*", help="SSQuant YYYY-MM input units")
    imp.add_argument("--overlay", action="store_true", help="RQ ETF increment overlay archives")
    imp.add_argument("--capture-db", help="existing SSQuant capture path")
    imp.add_argument("--label-evidence", help="JSON file of scoped label evidence")
    imp.add_argument("--dataset", help="RQ futures dataset name")
    imp.add_argument("--dominant-map", help="dominant mapping artifact path")
    imp.add_argument("--universe", help="futures universe.csv path")

    recover_cmd = commands.add_parser("recover", help="recover interrupted imports")
    recover_cmd.add_argument("--batch-id")

    rs = commands.add_parser(
        "recover-session",
        help="recover an unclosed recording session (typed report, optional successor)",
    )
    rs.add_argument("--session-id", required=True)
    rs.add_argument(
        "--no-successor",
        action="store_true",
        help="only mark/report the old session; do not create a successor session",
    )
    rs.add_argument("--successor-source-spec", help="override successor source spec")
    rs.add_argument("--successor-calendar-spec", help="override successor calendar spec")

    seal_cmd = commands.add_parser("seal", help="seal a committed session range (WP09)")
    seal_cmd.add_argument("--request", required=True, help="SealRequest JSON")

    replay_cmd = commands.add_parser(
        "replay", help="replay committed recording events (readonly, no writer)"
    )
    replay_cmd.add_argument("--session-id", required=True)
    replay_cmd.add_argument(
        "--limit",
        type=int,
        default=None,
        help="cap the number of events listed in 'events' (counts stay exact)",
    )

    coverage_cmd = commands.add_parser("coverage", help="observed coverage report")
    coverage_cmd.add_argument("--dataset-id")

    quality_cmd = commands.add_parser("quality", help="observational quality report")
    quality_cmd.add_argument("--dataset-id", required=True)
    quality_cmd.add_argument("--partition", nargs="*")

    rc = commands.add_parser("resolve-conflict", help="resolve a same-key conflict")
    rc.add_argument("--dataset-id", required=True)
    rc.add_argument("--partition", required=True)
    rc.add_argument("--conflict-id", required=True)
    rc.add_argument(
        "--resolution", required=True, choices=("existing", "candidate", "quarantine")
    )
    rc.add_argument("--reason", required=True)

    freeze_cmd = commands.add_parser("freeze", help="freeze a snapshot")
    freeze_cmd.add_argument("--request", required=True, help="SnapshotRequest JSON")

    verify_cmd = commands.add_parser("verify", help="integrity check of store/snapshot")
    verify_cmd.add_argument("--snapshot-id")

    export_cmd = commands.add_parser("export", help="export a snapshot")
    export_cmd.add_argument("--snapshot-id", required=True)
    export_cmd.add_argument("--target", required=True)
    export_cmd.add_argument("--format", choices=("parquet", "sqlite", "alpha"), default="parquet")

    report_cmd = commands.add_parser("report", help="standalone HTML store report")
    report_cmd.add_argument("--output")
    return parser


_DISPATCH = {
    "init": _cmd_init,
    "inspect": _cmd_inspect,
    "import": _cmd_import,
    "recover": _cmd_recover,
    "recover-session": _cmd_recover_session,
    "seal": _cmd_seal,
    "replay": _cmd_replay,
    "coverage": _cmd_coverage,
    "quality": _cmd_quality,
    "resolve-conflict": _cmd_resolve_conflict,
    "freeze": _cmd_freeze,
    "verify": _cmd_verify,
    "export": _cmd_export,
    "report": _cmd_report,
}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.root:
        print(
            json.dumps({"status": "error", "message": "--root is required"}),
        )
        return EXIT_ERROR
    handler = _DISPATCH[args.command]
    try:
        payload, exit_code = handler(args)
    except (StoreError, ImporterError, ValueError, OSError) as exc:
        payload = {"status": "error", "message": f"{type(exc).__name__}: {exc}"}
        exit_code = EXIT_ERROR
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
