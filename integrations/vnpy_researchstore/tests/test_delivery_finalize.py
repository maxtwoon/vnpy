"""Focused tests for tools/delivery_finalize.py (phase 1 helper).

Native-independent: no vnpy import, no real store, no network. Everything
runs against tmp_path fixtures so the matrix/config rules are covered
deterministically.
"""

from __future__ import annotations

import json
from pathlib import Path

from tools.delivery_finalize import (
    EVIDENCE_MISSING,
    LIVE_NOT_RUN,
    MEASURED,
    OPEN_STATUSES,
    PENDING,
    build_matrix,
    check_configs,
    render_html,
    select_fact,
)

# ---------------------------------------------------------------------------
# fact extraction
# ---------------------------------------------------------------------------


def test_select_fact_dotted_paths() -> None:
    data = {"a": {"b": [{"c": 1}, {"c": 2}]}, "list": [10, 20]}
    assert select_fact(data, "a.b.1.c") == 2
    assert select_fact(data, "list.0") == 10
    assert select_fact(data, "a.b.5.c") is None
    assert select_fact(data, "missing.path") is None
    assert select_fact(data, "a.b") == [{"c": 1}, {"c": 2}]


def test_select_fact_length_suffix() -> None:
    spec = {"evidence": []}
    # length handling lives in build_matrix via ".length" suffix; here we just
    # pin that select_fact does not understand it (returns None).
    assert select_fact({"x": [1, 2, 3]}, "x.length") is None
    assert spec["evidence"] == []


# ---------------------------------------------------------------------------
# matrix assembly
# ---------------------------------------------------------------------------


def _write_json(path: Path, payload: dict) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return str(path)


def test_build_matrix_extracts_facts_and_binds_evidence(tmp_path: Path) -> None:
    evidence = _write_json(
        tmp_path / "ev" / "loop.json",
        {"status": "PASS", "store_id": "store-x", "checks": [1, 2, 3]},
    )
    matrix = build_matrix(
        [
            {
                "wp": "WP04",
                "check_id": "loop",
                "dimension": "d",
                "status": MEASURED,
                "evidence": [evidence],
                "facts": {
                    "status": "status",
                    "store_id": "store_id",
                    "checks_total": "checks.length",
                    "missing_fact": "no.such.path",
                },
                "note": "n",
            }
        ]
    )
    entry = matrix["entries"][0]
    assert entry["status"] == MEASURED
    assert entry["facts"]["status"] == "PASS"
    assert entry["facts"]["store_id"] == "store-x"
    assert entry["facts"]["checks_total"] == 3
    assert entry["facts"]["missing_fact"] is None
    assert entry["evidence"][0]["sha256"]
    assert entry["evidence"][0]["json"] is True
    assert matrix["status_counts"] == {MEASURED: 1}


def test_build_matrix_degrades_on_missing_evidence(tmp_path: Path) -> None:
    matrix = build_matrix(
        [
            {
                "wp": "WP03",
                "check_id": "gone",
                "dimension": "d",
                "status": MEASURED,
                "evidence": [str(tmp_path / "nope" / "missing.json")],
                "facts": {"x": "y"},
                "note": "n",
            },
            {
                "wp": "WP07",
                "check_id": "pending-stays",
                "dimension": "d",
                "status": PENDING,
                "evidence": [str(tmp_path / "nope" / "missing2.json")],
                "facts": {},
                "note": "n",
            },
            {
                "wp": "WP10",
                "check_id": "live",
                "dimension": "d",
                "status": LIVE_NOT_RUN,
                "evidence": [],
                "facts": {},
                "note": "n",
            },
        ]
    )
    by_id = {e["check_id"]: e for e in matrix["entries"]}
    assert by_id["gone"]["status"] == EVIDENCE_MISSING
    assert any("missing evidence file" in d for d in by_id["gone"]["degradation"])
    # OPEN statuses are truthful already and never degrade/upgrade
    assert by_id["pending-stays"]["status"] == PENDING
    assert by_id["live"]["status"] == LIVE_NOT_RUN
    assert matrix["status_counts"] == {
        EVIDENCE_MISSING: 1,
        PENDING: 1,
        LIVE_NOT_RUN: 1,
    }


def test_open_statuses_constant() -> None:
    assert OPEN_STATUSES == {
        "PENDING",
        "NOT_RUN",
        "UNKNOWN",
        "LIVE_NOT_RUN",
        "EVIDENCE_MISSING",
    }


def test_render_html_contains_statuses_and_escapes(tmp_path: Path) -> None:
    matrix = build_matrix(
        [
            {
                "wp": "WP04",
                "check_id": "x<script>",
                "dimension": "d",
                "status": MEASURED,
                "evidence": [],
                "facts": {},
                "note": "keep <b>raw</b>",
            }
        ]
    )
    html = render_html(matrix)
    assert "x&lt;script&gt;" in html
    assert "keep &lt;b&gt;raw&lt;/b&gt;" in html
    assert "#0a7d32" in html  # MEASURED color present


# ---------------------------------------------------------------------------
# instance-config validation
# ---------------------------------------------------------------------------


def _make_store(tmp_path: Path) -> tuple[Path, str]:
    store_root = tmp_path / "store"
    (store_root / "manifests" / "snapshots").mkdir(parents=True)
    (store_root / "store.json").write_text(
        json.dumps({"store_id": "store-test"}), encoding="utf-8"
    )
    manifest = {
        "snapshot_id": "snap-test",
        "selections": [
            {"dataset_id": "ds-1", "partition": "2016"},
            {"dataset_id": "ds-2", "partition": "XSHG/2016-01/bucket-03"},
        ],
    }
    (store_root / "manifests" / "snapshots" / "snap-test.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    return store_root, "snap-test"


def test_check_snapshot_request_selections(tmp_path: Path) -> None:
    store_root, _ = _make_store(tmp_path)
    configs = tmp_path / "configs"
    configs.mkdir()
    (configs / "smoke_snapshot.json").write_text(
        json.dumps(
            {
                "selections": [["ds-1", "2016"], ["ds-9", "9999"]],
                "required_fields": ["open", "close"],
            }
        ),
        encoding="utf-8",
    )
    result = check_configs(configs, store_root)
    r = result["results"][0]
    assert r["kind"] == "snapshot_request"
    assert r["checks"]["selection ds-1 2016"] == "published"
    assert any("ds-9" in item for item in r["pending_items"])
    assert r["problems"] == []
    assert result["store_id"] == "store-test"


def test_check_import_config_reports_missing_paths(tmp_path: Path) -> None:
    store_root, _ = _make_store(tmp_path)
    configs = tmp_path / "configs"
    configs.mkdir()
    (configs / "smoke_import.json").write_text(
        json.dumps(
            {
                "adapter": "rq_etf/0.1",
                "source_root": str(tmp_path / "no-such-root"),
                "repair_index": {"audit_csv": str(tmp_path / "no-audit.csv")},
                "batches": [{"frequency": "1d", "years": [2016]}],
            }
        ),
        encoding="utf-8",
    )
    result = check_configs(configs, store_root)
    r = result["results"][0]
    assert r["kind"] == "import_config"
    assert r["checks"]["source_root_exists"] is False
    assert r["checks"]["repair_index_csv_exists"] is False
    assert len(r["problems"]) == 2
    assert result["configs_with_problems"] == 1


def test_check_bootstrap_config_snapshot_manifest(tmp_path: Path) -> None:
    store_root, snap = _make_store(tmp_path)
    configs = tmp_path / "configs"
    configs.mkdir()
    (configs / "backtest_profile.json").write_text(
        json.dumps(
            {
                "store_root": str(store_root),
                "snapshot_id": snap,
                "runtime_dir": str(tmp_path / "rt"),
                "repo_path": str(tmp_path),
                "integration_path": str(tmp_path),
            }
        ),
        encoding="utf-8",
    )
    (configs / "bad_profile.json").write_text(
        json.dumps(
            {
                "store_root": str(store_root),
                "snapshot_id": "snap-does-not-exist",
                "runtime_dir": str(tmp_path / "rt2"),
                "repo_path": str(tmp_path),
                "integration_path": str(tmp_path),
            }
        ),
        encoding="utf-8",
    )
    result = check_configs(configs, store_root)
    by_name = {Path(r["config"]).name: r for r in result["results"]}
    assert by_name["backtest_profile.json"]["kind"] == "bootstrap_config"
    assert by_name["backtest_profile.json"]["checks"]["snapshot_manifest"] == "present"
    assert by_name["backtest_profile.json"]["problems"] == []
    assert any("snap-does-not-exist" in p for p in by_name["bad_profile.json"]["problems"])


def test_check_loop_config_dataset_publication(tmp_path: Path) -> None:
    store_root, _ = _make_store(tmp_path)
    configs = tmp_path / "configs"
    configs.mkdir()
    (configs / "loop.json").write_text(
        json.dumps(
            {
                "store_root": str(store_root),
                "snapshot_id": "snap-test",
                "runtime_dir": str(tmp_path / "rt"),
                "repo_path": "x",
                "symbols": ["S.SSE"],
                "windows": {"minute": {"start": "a", "end": "b"}},
                "lab_path": str(tmp_path / "lab"),
                "dataset_ids": {"daily": "ds-1", "minute": "ds-404"},
            }
        ),
        encoding="utf-8",
    )
    result = check_configs(configs, store_root)
    r = result["results"][0]
    assert r["kind"] == "loop_config"
    assert r["checks"]["dataset_ids.daily"] == "published"
    assert r["checks"]["dataset_ids.minute"] == "not published"
    assert any("ds-404" in p for p in r["problems"])


def test_check_configs_ignores_private_and_unknown(tmp_path: Path) -> None:
    store_root, _ = _make_store(tmp_path)
    configs = tmp_path / "configs"
    configs.mkdir()
    (configs / "_note.json").write_text("{}", encoding="utf-8")
    (configs / "mystery.json").write_text(json.dumps({"weird": 1}), encoding="utf-8")
    result = check_configs(configs, store_root)
    assert result["configs_checked"] == 1
    assert result["results"][0]["kind"] == "unknown"
    assert any("not recognized" in p for p in result["results"][0]["problems"])
