"""CLI end-to-end tests over a synthetic ETF package and a real store.

Covers the verb surface: init / import (smoke config, overlay with conflict
exit status) / inspect / coverage / quality / freeze / verify / export /
report / resolve-conflict / recover, plus the REAL recording verbs
(recover-session / replay / seal) against actual journal sessions — typed
results, truthful nonzero exits, idempotent repeat seal. No pending
capability is asserted anywhere: every verb either succeeds with typed
output or fails with actionable JSON and a nonzero exit.
"""

from __future__ import annotations

import io
import json
import tarfile
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from _rs_import_bootstrap import PYARROW_AVAILABLE, ZSTANDARD_AVAILABLE

from research_store.cli import (
    EXIT_CONFLICT,
    EXIT_ERROR,
    EXIT_OK,
    main,
)
from research_store.importers.core_bridge import build_rq_etf_spec
from research_store.models import compute_dataset_id

if TYPE_CHECKING:
    from research_store.journal_models import JournalEvent

pytestmark = pytest.mark.skipif(
    not (ZSTANDARD_AVAILABLE and PYARROW_AVAILABLE),
    reason="zstandard and pyarrow required",
)


def _write_tar_zst(path: Path, entries: list[tuple[str, bytes]]) -> None:
    import zstandard

    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as tf:
        for name, data in entries:
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
    payload = zstandard.ZstdCompressor().compress(buffer.getvalue())
    path.write_bytes(payload)
    import hashlib

    Path(str(path) + ".sha256").write_text(
        f"{hashlib.sha256(payload).hexdigest()}  {path.name}\n", encoding="utf-8"
    )


def _etf_csv(rows: list[str]) -> bytes:
    header = "order_book_id,datetime,open,high,low,close,volume,amount,num_trades\n"
    return (header + "\n".join(rows) + "\n").encode()


@pytest.fixture()
def workspace(tmp_path: Path) -> dict[str, Any]:
    package = tmp_path / "etf"
    package.mkdir()
    _write_tar_zst(
        package / "rqdatac_etf_lof_1m_2016.tar.zst",
        [("2016/510300.XSHG.csv", _etf_csv([
            "510300.XSHG,2016-02-29 09:31:00,1,1.2,0.9,1.1,100,500,3",
            "510300.XSHG,2016-02-29 09:32:00,1.1,1.3,1.0,1.2,90,365,2",
        ]))],
    )
    _write_tar_zst(
        package / "daily_increment_latest__rqdatac_etf_lof_1m_2026.tar.zst",
        [("2026/510300.XSHG.csv", _etf_csv([
            # conflicts with the base row below (corrected close)
            "510300.XSHG,2026-07-31 09:32:00,4.05,4.1,4.0,4.09,90,365,2",
        ]))],
    )
    _write_tar_zst(
        package / "rqdatac_etf_lof_1m_2026.tar.zst",
        [("2026/510300.XSHG.csv", _etf_csv([
            "510300.XSHG,2026-07-31 09:32:00,4.05,4.1,4.0,4.08,90,365,2",
        ]))],
    )
    config = {
        "adapter": "rq_etf/0.1",
        "source_root": str(package),
        "frequencies": ["1m"],
        "batches": [{"frequency": "1m", "years": [2016]}],
        "smoke": {"frequency": "1m", "years": [2016], "instruments": ["510300.XSHG"]},
    }
    config_path = tmp_path / "import_rq_etf.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    return {
        "root": str(tmp_path / "store"),
        "config": str(config_path),
        "package": package,
        "tmp": tmp_path,
    }


def _run(args: list[str], capsys: pytest.CaptureFixture) -> tuple[int, dict]:
    code = main(args)
    out = capsys.readouterr()
    return code, json.loads(out.out)


def test_cli_full_flow(workspace: dict[str, Any], capsys: pytest.CaptureFixture) -> None:
    root = workspace["root"]
    code, payload = _run(["--root", root, "init"], capsys)
    assert code == EXIT_OK and payload["status"] == "ok"

    code, payload = _run(
        ["--root", root, "import", "--config", workspace["config"], "--smoke"],
        capsys,
    )
    assert code == EXIT_OK, payload
    assert payload["status"] == "ok"
    summary = payload["imports"][0]
    assert summary["publish"]["state"] == "published"
    assert summary["counts"]["accepted_rows"] == 2

    # idempotent re-import of the same config replays to the same batch
    code, payload = _run(
        ["--root", root, "import", "--config", workspace["config"], "--smoke"],
        capsys,
    )
    assert code == EXIT_OK
    assert payload["imports"][0]["publish"]["core_batch_id"] == summary["publish"]["core_batch_id"]

    dataset_id = compute_dataset_id(build_rq_etf_spec("1m"))

    code, payload = _run(["--root", root, "inspect"], capsys)
    assert code == EXIT_OK
    assert payload["datasets"][0]["dataset_id"] == dataset_id

    code, payload = _run(
        ["--root", root, "inspect", "--dataset-id", dataset_id,
         "--source-label", "2016-02-29 09:31:00"],
        capsys,
    )
    assert code == EXIT_OK
    assert len(payload["source_label_rows"]) == 1

    code, payload = _run(["--root", root, "coverage"], capsys)
    assert code == EXIT_OK
    assert payload["coverage"]["expected_status"] == "unknown"
    assert Path(payload["report_path"]).is_file()

    code, payload = _run(["--root", root, "quality", "--dataset-id", dataset_id], capsys)
    assert code == EXIT_OK
    assert payload["quality"]["rows_checked"] == 2
    assert payload["quality"]["required_fields"]["fully_populated"] is True

    freeze_request = workspace["tmp"] / "freeze.json"
    freeze_request.write_text(
        json.dumps({"selections": [[dataset_id, "*"]]}), encoding="utf-8"
    )
    code, payload = _run(
        ["--root", root, "freeze", "--request", str(freeze_request)], capsys
    )
    assert code == EXIT_OK, payload
    snapshot_id = payload["snapshot_id"]

    code, payload = _run(["--root", root, "verify"], capsys)
    assert code == EXIT_OK
    assert payload["objects_checked"] >= 1
    assert payload["failures"] == []

    export_target = workspace["tmp"] / "export"
    code, payload = _run(
        ["--root", root, "export", "--snapshot-id", snapshot_id,
         "--target", str(export_target), "--format", "parquet"],
        capsys,
    )
    assert code == EXIT_OK, payload
    assert payload["export"]["datasets"][dataset_id]["readback"] == "verified"

    code, payload = _run(["--root", root, "report"], capsys)
    assert code == EXIT_OK
    assert Path(payload["report_path"]).is_file()
    assert payload["report"]["recording"]["status"] == "no_recording_sessions"

    code, payload = _run(["--root", root, "recover"], capsys)
    assert code == EXIT_OK
    assert all(b["action"] == "returned_prior_receipt" for b in payload["batches"])


def test_cli_overlay_conflict_exit_and_resolution(
    workspace: dict[str, Any], capsys: pytest.CaptureFixture
) -> None:
    root = workspace["root"]
    _run(["--root", root, "init"], capsys)
    # base 2026 archive first
    code, payload = _run(
        ["--root", root, "import", "--config", workspace["config"], "--years", "2026"],
        capsys,
    )
    assert code == EXIT_OK, payload
    # overlay: corrected value at the same key -> conflict exit status
    code, payload = _run(
        ["--root", root, "import", "--config", workspace["config"], "--overlay"],
        capsys,
    )
    assert code == EXIT_CONFLICT
    assert payload["status"] == "conflict"
    conflict = payload["imports"][0]["publish"]["conflicts"][0]

    dataset_id = compute_dataset_id(build_rq_etf_spec("1m"))
    code, payload = _run(
        ["--root", root, "resolve-conflict", "--dataset-id", dataset_id,
         "--partition", conflict["partition"], "--conflict-id",
         conflict["conflict_id"], "--resolution", "existing",
         "--reason", "base archive values verified against sidecar"],
        capsys,
    )
    assert code == EXIT_OK, payload


# ---------------------------------------------------------------------------
# recording verbs (recover-session / replay / seal) over REAL journal sessions
# ---------------------------------------------------------------------------

BASE_NS = 1_700_000_000_000_000_000
_NS_30S = 30_000_000_000

# Timezone-only calendar (revised 02I grammar): display/normalization
# evidence ONLY — never a trading-calendar claim; trading_date stays
# unknown unless explicit source evidence exists.
CAL = "tz:Asia/Shanghai"


def _tick_event(i: int) -> JournalEvent:
    from research_store.journal_models import JournalEvent

    return JournalEvent(
        kind="tick",
        instrument="IF2403.CFFEX",
        event_ts_ns=BASE_NS + i * _NS_30S,
        source_event_id=f"ctp:{i}",
        payload={"last_price": 100.0 + i, "volume": 10.0, "turnover": 1000.0},
    )


def _drain(session: Any, n: int, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if session.status().committed_seq >= n:
            return
        time.sleep(0.01)
    raise AssertionError(f"committed_seq did not reach {n}: {session.status()}")


@pytest.fixture()
def cli_store(tmp_path: Path) -> dict[str, Any]:
    """An initialized store root touched by the CLI only afterwards."""

    from research_store import init_store

    root = str(tmp_path / "store")
    init_store(root).close()
    return {"root": root, "tmp": tmp_path}


def _open_cli_store(root: str) -> Any:
    from research_store import open_store

    return open_store(root)


def test_cli_recover_session_creates_typed_successor(
    cli_store: dict[str, Any], capsys: pytest.CaptureFixture
) -> None:
    from research_store.journal import create_session

    root = cli_store["root"]
    store = _open_cli_store(root)
    session = create_session(
        store, "futures:cli-sim", "Asia/Shanghai", session_id="sess-cli-crash"
    )
    session.admit(_tick_event(0))
    session.admit(_tick_event(1))
    _drain(session, 2)
    session.close()  # release lock only: crash-like OPEN session on disk
    store.close()

    code, payload = _run(
        ["--root", root, "recover-session", "--session-id", "sess-cli-crash"],
        capsys,
    )
    assert code == EXIT_OK, payload
    body = payload["session"]
    assert body["session_id"] == "sess-cli-crash"
    assert body["prior_state"] == "OPEN"
    assert body["committed_seq"] == 2
    assert body["committed_events"] == 2
    assert body["last_error"] is None
    successor = body["successor_session_id"]
    assert isinstance(successor, str) and successor.startswith("sess-")
    # The successor is linked to the recovered session (typed value, not prose).
    store = _open_cli_store(root)
    try:
        from research_store.journal import open_session

        succ = open_session(store, successor)
        try:
            assert succ.predecessor_session_id == "sess-cli-crash"
            assert succ.source_spec == "futures:cli-sim"
            assert succ.calendar_spec == "Asia/Shanghai"
        finally:
            succ.close()
    finally:
        store.close()

    # Idempotent re-report without a successor: prior state is now UNCLEAN_END.
    code, payload = _run(
        [
            "--root", root, "recover-session",
            "--session-id", "sess-cli-crash", "--no-successor",
        ],
        capsys,
    )
    assert code == EXIT_OK, payload
    body = payload["session"]
    assert body["prior_state"] == "UNCLEAN_END"
    assert body["committed_events"] == 2
    assert body["successor_session_id"] is None


def test_cli_recover_session_overrides_and_unknown(
    cli_store: dict[str, Any], capsys: pytest.CaptureFixture
) -> None:
    from research_store.journal import create_session

    root = cli_store["root"]
    store = _open_cli_store(root)
    session = create_session(store, "futures:cli-sim", "Asia/Shanghai")
    session_id = session.session_id
    session.admit(_tick_event(0))
    _drain(session, 1)
    session.close()
    store.close()

    code, payload = _run(
        [
            "--root", root, "recover-session", "--session-id", session_id,
            "--successor-source-spec", "futures:cli-next",
            "--successor-calendar-spec", "UTC",
        ],
        capsys,
    )
    assert code == EXIT_OK, payload
    successor = payload["session"]["successor_session_id"]
    store = _open_cli_store(root)
    try:
        from research_store.journal import open_session

        succ = open_session(store, successor)
        try:
            assert succ.source_spec == "futures:cli-next"
            assert succ.calendar_spec == "UTC"
        finally:
            succ.close()
    finally:
        store.close()

    # Unknown session: actionable typed error, nonzero exit — never a fake OK.
    code, payload = _run(
        ["--root", root, "recover-session", "--session-id", "sess-missing"],
        capsys,
    )
    assert code == EXIT_ERROR
    assert payload["status"] == "error"
    assert "sess-missing" in payload["message"]


def test_cli_replay_committed_events(
    cli_store: dict[str, Any], capsys: pytest.CaptureFixture
) -> None:
    from research_store.journal import create_session

    root = cli_store["root"]
    store = _open_cli_store(root)
    session = create_session(store, "futures:cli-sim", "Asia/Shanghai")
    session_id = session.session_id
    for i in range(3):
        session.admit(_tick_event(i))
    _drain(session, 3)
    result = session.close_at_cutoff(timeout=5.0)
    assert result.state.value == "CLOSED"
    session.close()
    store.close()

    code, payload = _run(
        ["--root", root, "replay", "--session-id", session_id], capsys
    )
    assert code == EXIT_OK, payload
    assert payload["status"] == "ok"
    assert payload["committed_events"] == 3
    assert payload["first_seq"] == 1
    assert payload["last_seq"] == 3
    assert payload["truncated"] is False
    assert [e["seq"] for e in payload["events"]] == [1, 2, 3]
    assert payload["events"][0]["source_event_id"] == "ctp:0"

    # --limit caps only the listed events; counts stay exact and honest.
    code, payload = _run(
        ["--root", root, "replay", "--session-id", session_id, "--limit", "1"],
        capsys,
    )
    assert code == EXIT_OK, payload
    assert payload["committed_events"] == 3
    assert len(payload["events"]) == 1
    assert payload["truncated"] is True

    # Unknown session: nonzero exit with actionable JSON.
    code, payload = _run(
        ["--root", root, "replay", "--session-id", "sess-missing"], capsys
    )
    assert code == EXIT_ERROR
    assert payload["status"] == "error"
    assert "sess-missing" in payload["message"]


def _write_seal_request(
    tmp_path: Path, session_id: str, end: int, **overrides: Any
) -> Path:
    path = tmp_path / f"seal_{session_id}_{end}.json"
    body: dict[str, Any] = {
        "session_id": session_id,
        "committed_seq_start": 1,
        "committed_seq_end": end,
        "transform_version": "agg-v1",
        "source_spec": "futures:cli-sim",
        "calendar_spec": CAL,
        "asset_class": "futures",
        "volume_unit": "lots",
        "turnover_unit": "CNY",
    }
    body.update(overrides)
    for key, value in list(body.items()):
        if value is None:
            del body[key]  # explicit None = omit the optional field
    path.write_text(json.dumps(body), encoding="utf-8")
    return path


def _committed_closed_session(root: str, n: int = 6) -> str:
    from research_store.journal import create_session

    store = _open_cli_store(root)
    session = create_session(store, "futures:cli-sim", CAL)
    session_id = session.session_id
    for i in range(n):
        session.admit(_tick_event(i))
    _drain(session, n)
    result = session.close_at_cutoff(timeout=5.0)
    assert result.state.value == "CLOSED"
    session.close()
    store.close()
    return session_id


def test_cli_seal_committed_range_is_idempotent(
    cli_store: dict[str, Any], capsys: pytest.CaptureFixture
) -> None:
    root = cli_store["root"]
    session_id = _committed_closed_session(root, n=6)
    request = _write_seal_request(cli_store["tmp"], session_id, end=6)

    code, payload = _run(["--root", root, "seal", "--request", str(request)], capsys)
    assert code == EXIT_OK, payload
    seal = payload["seal"]
    assert seal["session_id"] == session_id
    assert seal["input_events"] == 6
    # Revised 02I F1: 6 verbatim ticks + 2 EVIDENCED minute bars. The third
    # (tail) minute has no later committed event crossing its end, so it
    # stays unevidenced and is deliberately NOT published as canonical.
    assert seal["accepted_rows"] == 8
    assert seal["dataset_id"]
    assert seal["idempotent_replay"] is False
    assert payload["plan"]["event_count"] == 6

    # Repeat seal of the SAME range: idempotent replay, same identity.
    code, payload = _run(["--root", root, "seal", "--request", str(request)], capsys)
    assert code == EXIT_OK, payload
    assert payload["seal"]["idempotent_replay"] is True
    assert payload["seal"]["seal_id"] == seal["seal_id"]
    assert payload["seal"]["dataset_id"] == seal["dataset_id"]
    assert payload["seal"]["accepted_rows"] == seal["accepted_rows"]


def test_cli_seal_errors_are_truthful(
    cli_store: dict[str, Any], capsys: pytest.CaptureFixture
) -> None:
    root = cli_store["root"]
    session_id = _committed_closed_session(root, n=2)

    # Range beyond the committed watermark: refused before any publish.
    beyond = _write_seal_request(cli_store["tmp"], session_id, end=5)
    code, payload = _run(["--root", root, "seal", "--request", str(beyond)], capsys)
    assert code == EXIT_ERROR, payload
    assert payload["status"] == "error"
    assert "exceeds committed watermark" in payload["message"]

    # Empty range: refused.
    empty = _write_seal_request(cli_store["tmp"], session_id, end=0)
    code, payload = _run(["--root", root, "seal", "--request", str(empty)], capsys)
    assert code == EXIT_ERROR
    assert "empty seal range" in payload["message"]

    # Optional semantics fields omitted: the CLI keeps the honest
    # OTHER/unknown defaults (never guessed futures); the CORE then refuses
    # the combination against the session's stored futures source kind.
    incomplete = _write_seal_request(
        cli_store["tmp"], session_id, end=2,
        asset_class=None, volume_unit=None, turnover_unit=None,
    )
    code, payload = _run(
        ["--root", root, "seal", "--request", str(incomplete)], capsys
    )
    assert code == EXIT_ERROR
    assert payload["status"] == "error"
    assert "not consistent" in payload["message"]

    # An invalid asset_class VALUE is a typed CLI error naming the gap.
    invalid = _write_seal_request(
        cli_store["tmp"], session_id, end=2, asset_class="spaceships",
    )
    code, payload = _run(
        ["--root", root, "seal", "--request", str(invalid)], capsys
    )
    assert code == EXIT_ERROR
    assert "unknown asset_class" in payload["message"]


def test_cli_report_recording_section_is_honest(
    cli_store: dict[str, Any], capsys: pytest.CaptureFixture
) -> None:
    """The report verb runs cleanly and reports the recording section.

    NOTE (honest scope): durable recording-session registration into the
    catalog table the report reads is a recording-core obligation tracked
    in .coordination/recorder03d-opencode-core-requests.md; until that
    lands, journal sessions exist without appearing as sessions_present, so
    asserting sessions_present here would fabricate integration evidence.
    """

    root = cli_store["root"]
    code, payload = _run(["--root", root, "report"], capsys)
    assert code == EXIT_OK
    assert payload["report"]["recording"]["status"] == "no_recording_sessions"

    _committed_closed_session(root, n=2)
    code, payload = _run(["--root", root, "report"], capsys)
    assert code == EXIT_OK
    assert payload["report"]["recording"]["status"] in (
        "no_recording_sessions",
        "sessions_present",
    )


def test_cli_errors_are_safe(workspace: dict[str, Any], capsys: pytest.CaptureFixture) -> None:
    # unknown store
    code, payload = _run(
        ["--root", str(workspace["tmp"] / "nope"), "inspect"], capsys
    )
    assert code == 1
    assert payload["status"] == "error"
    # freeze over unknown dataset
    root = workspace["root"]
    _run(["--root", root, "init"], capsys)
    bad_request = workspace["tmp"] / "bad.json"
    bad_request.write_text(
        json.dumps({"selections": [["ds-does-not-exist", "*"]]}), encoding="utf-8"
    )
    code, payload = _run(["--root", root, "freeze", "--request", str(bad_request)], capsys)
    assert code == 1
    assert "UnknownDatasetError" in payload["message"]
