"""Bootstrap tests: real subprocess entry-command runs.

Kept free of any in-process vnpy import: every bootstrap guarantee (cwd
isolation before vnpy.trader.utility, singleton rejection, no SQLite
fallback, one fresh process per snapshot) is exercised through actual
subprocesses running the shipped entry commands.
"""

from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from research_store import Store

from test_native_support import daily_rows, freeze_all, import_dataset

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
TOOLS = ROOT / "tools"


def write_config(tmp_path: Path, store: Store, snapshot_id: str, name: str = "cfg.json") -> Path:
    config = {
        "store_root": str(store.root),
        "snapshot_id": snapshot_id,
        "runtime_dir": str(tmp_path / "runtime"),
        "repo_path": str(REPO),
        "integration_path": str(ROOT),
        "backtesters": ["cta", "portfolio"],
        "range": {"start": "2024-01-01", "end": "2024-01-31"},
    }
    path = tmp_path / name
    path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    return path


def run_tool(tool: str, config: Path, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(TOOLS / tool), "--config", str(config)],
        capture_output=True,
        text=True,
        cwd=cwd,
        timeout=300,
    )


def parse_receipt(proc: subprocess.CompletedProcess, runtime_dir: Path) -> dict:
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        receipts = sorted(runtime_dir.glob("native_bootstrap_receipt-*.json"))
        assert receipts, f"no receipt written; stdout={proc.stdout!r} stderr={proc.stderr!r}"
        return json.loads(receipts[-1].read_text(encoding="utf-8"))


@pytest.fixture()
def boot_env(store: Store, tmp_path: Path):
    dataset_id = import_dataset(
        store, tmp_path, daily_rows("000001"), asset_name="daily.csv"
    )
    snapshot_id = freeze_all(store, [dataset_id])
    return store, snapshot_id


def test_config_validation(tmp_path: Path) -> None:
    from vnpy_researchstore.bootstrap import load_config
    from research_store import StoreError

    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"store_root": "x", "bogus": 1}), encoding="utf-8")
    with pytest.raises(StoreError, match="unknown keys"):
        load_config(bad)

    incomplete = tmp_path / "incomplete.json"
    incomplete.write_text(json.dumps({"store_root": "x"}), encoding="utf-8")
    with pytest.raises(StoreError, match="missing required keys"):
        load_config(incomplete)


def test_bootstrap_receipt_and_no_sqlite_fallback(
    boot_env, tmp_path: Path
) -> None:
    store, snapshot_id = boot_env
    config = write_config(tmp_path, store, snapshot_id)
    proc = run_tool("native_bootstrap.py", config, tmp_path)
    assert proc.returncode == 0, proc.stderr

    receipt = parse_receipt(proc, tmp_path / "runtime")
    assert receipt["snapshot_id"] == snapshot_id
    assert receipt["store_root"] == str(store.root)
    assert receipt["range"] == {"start": "2024-01-01", "end": "2024-01-31"}
    # actual module origin recorded, under the configured repo path
    vnpy_file = Path(receipt["vnpy"]["module_file"])
    assert Path(receipt["vnpy"]["repo_path"]) in vnpy_file.parents
    # the bound database is the researchstore plugin, never a SQLite fallback
    assert receipt["database"]["module"] == "vnpy_researchstore.database"
    assert receipt["database"]["class"] == "Database"
    assert receipt["database"]["settings_name"] == "researchstore"
    # backtesters imported only after the binding
    assert "vnpy_ctastrategy" in receipt["backtesters"]["cta"]
    assert "vnpy_portfoliostrategy" in receipt["backtesters"]["portfolio"]
    # isolated cwd + runtime, no default runtime mutation
    runtime_dir = (tmp_path / "runtime").resolve()
    assert Path(receipt["cwd"]) == runtime_dir
    assert (runtime_dir / ".vntrader").is_dir()
    assert Path(receipt["receipt_path"]).is_file()


def test_overview_command(boot_env, tmp_path: Path) -> None:
    store, snapshot_id = boot_env
    config = write_config(tmp_path, store, snapshot_id)
    proc = run_tool("native_overview.py", config, tmp_path)
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["snapshot_id"] == snapshot_id
    symbols = [row["symbol"] for row in payload["overview"]]
    assert symbols == ["000001"]
    assert payload["overview"][0]["count"] == 5
    assert payload["overview"][0]["exchange"] == "SZSE"
    assert payload["overview"][0]["interval"] == "d"


def test_singleton_rejection(boot_env, tmp_path: Path) -> None:
    """A process that already initialized vnpy's database state is refused."""
    store, snapshot_id = boot_env
    config = write_config(tmp_path, store, snapshot_id)
    script = tmp_path / "preinit.py"
    script.write_text(
        textwrap.dedent(
            f"""
            import os, sys
            from pathlib import Path
            sys.path.insert(0, {str(REPO)!r})
            sys.path.insert(0, {str(ROOT)!r})
            runtime = Path(sys.argv[1])
            (runtime / ".vntrader").mkdir(parents=True, exist_ok=True)
            os.chdir(runtime)
            import vnpy.trader.database as database_module
            database_module.database = object()  # pre-initialized singleton
            from vnpy_researchstore.bootstrap import bootstrap_session, load_config
            config, identity = load_config(sys.argv[2])
            bootstrap_session(config, identity)
            """
        ),
        encoding="utf-8",
    )
    proc = subprocess.run(
        [sys.executable, str(script), str(tmp_path / "runtime"), str(config)],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        timeout=300,
    )
    assert proc.returncode != 0
    assert "already imported" in proc.stderr or "singleton" in proc.stderr


def test_two_separate_snapshot_processes(store: Store, tmp_path: Path) -> None:
    """Two snapshots, two fresh bootstrap processes, each bound to its own."""
    first_ds = import_dataset(
        store, tmp_path, daily_rows("000001"), asset_name="first.csv"
    )
    second_ds = import_dataset(
        store,
        tmp_path,
        daily_rows("000002"),
        asset_name="second.csv",
        source_id="synthetic-second",
    )
    first_snapshot = freeze_all(store, [first_ds])
    second_snapshot = freeze_all(store, [second_ds])
    assert first_snapshot != second_snapshot

    receipts = []
    for i, snapshot_id in enumerate((first_snapshot, second_snapshot)):
        run_dir = tmp_path / f"run{i}"
        run_dir.mkdir()
        config = write_config(run_dir, store, snapshot_id)
        proc = run_tool("native_bootstrap.py", config, run_dir)
        assert proc.returncode == 0, proc.stderr
        receipts.append(parse_receipt(proc, run_dir / "runtime"))

    assert receipts[0]["snapshot_id"] == first_snapshot
    assert receipts[1]["snapshot_id"] == second_snapshot
    assert receipts[0]["config_identity"] != receipts[1]["config_identity"]


def test_missing_snapshot_refused(store: Store, tmp_path: Path) -> None:
    config = write_config(tmp_path, store, "snap-does-not-exist")
    proc = run_tool("native_bootstrap.py", config, tmp_path)
    assert proc.returncode != 0
    assert "snap-does-not-exist" in proc.stderr
