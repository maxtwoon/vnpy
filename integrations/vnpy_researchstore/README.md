# vnpy_researchstore

Immutable research data store and VeighNa recorder for personal quant
research: a pure storage core (`research_store`, no vnpy dependency), a
read-only native bridge (`vnpy_researchstore`) that binds VeighNa consumers
to one frozen snapshot, and a small CLI. One local plugin; no backend, no
service. Status: **v0.1.0.dev1, development complete pending independent
audit** — see VERIFICATION.md for exactly what is measured, pending, or
unknown.

## Install

```powershell
# from the integration directory, using the existing package .venv
D:\repo\vnpy\integrations\vnpy_researchstore\.venv\Scripts\python.exe -m pip install -e .
# console entries: qstore (store CLI), vnpy-recorder (recording launcher)
```

The research core never imports vnpy. The native bridge binds the
**repository** vnpy (`D:/repo/vnpy`) and an isolated runtime cwd BEFORE any
`vnpy.trader.utility` import — never site-packages, never the default
`.vntrader`.

## Store lifecycle (CLI)

`python -m research_store --root <store_root> <command>` (JSON on stdout,
progress on stderr; identical to the `qstore` entry point):

| Command | Purpose |
|---|---|
| `init` | initialize a store (empty dir or existing store) |
| `inspect` | catalog/assets/issues summary (`--dataset-id`, `--source-label`) |
| `import --config <json>` | run an import config (narrow with `--frequency/--years/--instruments/--tables/--months`; `--capture-db` for SSQuant captures; `--smoke`/`--overlay` are special scopes) |
| `freeze --request <json>` | freeze published partitions into an immutable snapshot |
| `verify [--snapshot-id <id>]` | integrity check (counts are store-global work units, not per-snapshot object counts) |
| `coverage` / `quality` | observed coverage / observational quality report |
| `resolve-conflict` | resolve a same-key conflict (existing/candidate/quarantine + reason) |
| `export --snapshot-id <id> --target <dir> [--format parquet\|sqlite\|alpha]` | export a snapshot |
| `report --output <html>` | standalone HTML store report (public report API) |
| `recover`, `recover-session`, `replay`, `seal` | recording journal recovery/replay/sealing (offline engineering) |

## Verified one-step real-ETF loop

The full consumer loop (core reader, native `Database` with bare
`510130`/`510300` + `Exchange.SSE`, both `ResearchAlphaLab` read methods,
offline CTA/Portfolio bootstrap in a fresh child process, snapshot verify,
import-idempotency cross-check — 16 checks, exit code 0/2):

```powershell
cd D:\repo\vnpy\integrations\vnpy_researchstore
.venv\Scripts\python.exe tools\delivery_etf_loop.py --config D:\quant-data\configs\delivery_etf_loop.json
```

Bind: store `store-398306491d834f99`, snapshot `snap-030369f20bd18303`,
datasets `ds-d939147fd6b633fd348fa62ed1fef74c` (1d) /
`ds-b9bbad83ec09f4b9dcef6ea9a81c4b51` (1m), window 2016-01-18..21
Asia/Shanghai. Machine evidence: `.coordination/delivery04f-dev/opencode-loop.rerun.stdout.json`.

## Offline CTA/Portfolio bootstrap

```powershell
.venv\Scripts\python.exe tools\native_bootstrap.py --config D:\quant-data\configs\backtest_profile.json
```

Fresh process required (the bootstrap refuses an already-imported vnpy or an
already-initialized database singleton; no SQLite fallback). Imports the
backtester modules and loads bars only — no gateway, account, strategy, or
network.

## Import / freeze (the verified 2016 ETF example)

```powershell
.venv\Scripts\python.exe -m research_store --root D:/quant-data import --config D:/quant-data/configs/smoke_import.json --frequency 1d --years 2016 --instruments 510130.XSHG 510300.XSHG
.venv\Scripts\python.exe -m research_store --root D:/quant-data import --config D:/quant-data/configs/smoke_import.json --frequency 1m --years 2016 --instruments 510130.XSHG 510300.XSHG
# repeat each command: same idempotency_key, 0 duplicate rows proves idempotency
.venv\Scripts\python.exe -m research_store --root D:/quant-data freeze --request D:/quant-data/configs/smoke_snapshot.json
.venv\Scripts\python.exe -m research_store --root D:/quant-data verify --snapshot-id <printed snapshot id>
```

Imports hash each archive via its sidecar before reading and load the
133-key repair index BEFORE base archives; disputed repaired keys are
excluded from default backtests with visible gaps. Freeze creates a NEW
immutable snapshot; never reinitialize or overwrite an existing store.
Larger ranges are expanded by repeating the import command with more
`--years` — there is no requirement (or helper) that ingests whole archives
in one shot.

## Recording (offline engineering; live = LIVE_NOT_RUN)

The recorder launcher (`vnpy-recorder`) and the journal CLI support offline
admission, clean stop vs UNCLEAN_END, `recover-session`, committed-only
`replay`, and idempotent `seal` into a canonical revision. Recording loops
are covered by the scoped test suites; **no durable recorded session exists
on the real store yet** (`D:/quant-data/journals` is empty), so no instance
replay/seal config is shipped — fill `configs/recorder_replay.json` (repo
template) from an ACTUAL session. No authorized live gateway capture has
been run; `live_gateway_recording` stays `LIVE_NOT_RUN`.

## Configs: templates vs real instances

| File | Kind | Status |
|---|---|---|
| `configs/smoke_import.json`, `configs/smoke_snapshot.json`, `configs/recorder_replay.json`, `configs/backtest_profile.json` | repository templates | generic `REPLACE_ME` placeholders, never runnable as-is |
| `D:/quant-data/configs/smoke_import.json` | real instance | verified import loop (2016 two-ETF scope) |
| `D:/quant-data/configs/smoke_snapshot.json` | real instance | verified freeze selections of `snap-030369f20bd18303` |
| `D:/quant-data/configs/backtest_profile.json` | real instance | verified offline bootstrap binding (receipt `native_bootstrap_receipt-20260917T020446Z.json`) |
| `D:/quant-data/configs/delivery_etf_loop.json` | real instance | verified 16-check consumer loop binding |
| recorder replay/seal instance | — | intentionally absent: no real session ID exists yet |

Read-only validation of all instance configs:
`.venv\Scripts\python.exe tools\delivery_finalize.py check-configs` — checks
paths, store identity, snapshot manifests, dataset publication; missing
future work is reported as `pending_items`, never invented.

## Phase report

`.venv\Scripts\python.exe tools\delivery_finalize.py report` regenerates
`reports/delivery04n/verification-matrix.json` +
`reports/delivery04n/delivery04n-report.html` (standalone HTML, no backend).
Facts are extracted from bound evidence files at run time; missing evidence
degrades the entry to `EVIDENCE_MISSING` instead of passing.

## Honest limits

* Expected market coverage is UNKNOWN everywhere: no calendar/listing
  evidence exists in scope; observed min/max dates never imply completeness.
* SS (1/5/15m/SimNow8/MA), RQ futures END-label direction, recording
  calendar/NULL semantics, and the recorder B1 launcher fix are owned by
  in-flight tasks (04H/04L/04M/02IA/03D) — see VERIFICATION.md.
* LIVE_NOT_RUN is a standing label, not a placeholder to be filled by
  connecting an account.

## Rollback

Rollback is environmental, not data-related: uninstall the plugin
(`pip uninstall vnpy_researchstore`) or stop using it; remove the console
entries; keep using the original VeighNa launcher and database
(`SETTINGS["database.name"]` unchanged). Snapshots and published revisions
are immutable and remain on disk; no default `.vntrader` or global settings
are modified by any command in this README.
