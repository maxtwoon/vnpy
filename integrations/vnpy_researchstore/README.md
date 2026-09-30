# vnpy_researchstore

Immutable research data store and VeighNa recorder for personal quant
research: a pure storage core (`research_store`, no vnpy dependency), a
read-only native bridge (`vnpy_researchstore`) that binds VeighNa consumers
to one frozen snapshot, and a small CLI. One local plugin; no backend, no
service. Status: **v0.1.0.dev1, accepted for the agreed personal offline
research scope**. Independent final audit: PASS; see
`.coordination/claude-delivery04n-final/REVIEW.md` and
`.coordination/completion-audit-20260930.json`. See VERIFICATION.md for
measured scopes and remaining data limitations; live gateway recording
remains LIVE_NOT_RUN.

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
# plugin-runtime command (historical 2026-09-17 evidence, plugin .venv):
.venv\Scripts\python.exe tools\delivery_etf_loop.py --config D:\quant-data\configs\delivery_etf_loop.json
```

The CURRENT 16/16 PASS claim (2026-09-30, 27.9 s) was produced on the
REGISTERED vnpy-alpha runtime, not the plugin .venv. To reproduce on that
route you need: the registered vnpy-alpha interpreter per
`D:/repo/quant/runtime-policy.json` (`C:/Python314/python.exe
D:/repo/quant/scripts/runtime.py run vnpy-alpha -- <args>`), the hash-pinned
local dependency overlays recorded in
`.coordination/etf-current-runtime-20260930` and
`.coordination/runtime-alpha-20260930/copied-packages.json` +
`copied-cta.json` plus the verified isolated portfolio plugin
(`D:/repo/quant/.runtime/verification/warehouse-union-portfolio-20260928/plugin`),
and process-local `PYTHONUTF8=1` / `PYTHONIOENCODING=utf-8` for child
processes. The exact instance config and recorded run live at
`.coordination/etf-current-runtime-20260930/utf8-run/` (config.json,
result.json, exit 0). Runtimes are recorded separately and never equated.

Bind: store `store-398306491d834f99`, snapshot `snap-030369f20bd18303`,
datasets `ds-d939147fd6b633fd348fa62ed1fef74c` (1d) /
`ds-b9bbad83ec09f4b9dcef6ea9a81c4b51` (1m), window 2016-01-18..21
Asia/Shanghai. Machine evidence:
`.coordination/etf-current-runtime-20260930/utf8-run/result.json`.

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
`replay`, and idempotent `seal` into a canonical revision. A durable
SYNTHETIC engineering session exists on the real store
(`sess-d7c9ad113b2e42f5`, CLOSED and sealed, 5 ticks + 2 bars, snapshot
`snap-7914084cde1ff139` — explicitly not real market history):

```powershell
.venv\Scripts\python.exe -m research_store --root D:/quant-data replay --session-id sess-d7c9ad113b2e42f5
.venv\Scripts\python.exe -m research_store --root D:/quant-data report --output D:\quant-data\reports\store-report.html
```

The public store report reads recording sessions read-only from the durable
journals (journal authority): journal-only sessions are visible with their
committed watermark and successor lineage, catalog-only rows are retained
with their missing journal marked as an error, unreadable/partial journals
are visible as errors, and live in-memory admission counters (accepted/
backlog/rejected/errors) are rendered as explicit **UNKNOWN** when null
(they stay `null` in the machine JSON — never inferred zero). Long cells
wrap, so the tables stay inside the viewport.

Known recording behavior: old key/value-formatted sessions remain replayable
but cannot seal; repeated `recover-session` creates DISTINCT successors —
run `inspect` first and use `--no-successor` for report-only repeats. No
authorized live gateway capture has been run; `live_gateway_recording` stays
`LIVE_NOT_RUN`.

## Configs: templates vs real instances

| File | Kind | Status |
|---|---|---|
| `configs/smoke_import.json`, `configs/smoke_snapshot.json`, `configs/recorder_replay.json`, `configs/backtest_profile.json` | repository templates | generic `REPLACE_ME` placeholders, never runnable as-is |
| `D:/quant-data/configs/smoke_import.json` | real instance | verified import loop (2016 two-ETF scope) |
| `D:/quant-data/configs/smoke_snapshot.json` | real instance | verified freeze selections of `snap-030369f20bd18303` |
| `D:/quant-data/configs/backtest_profile.json` | real instance | verified offline bootstrap binding (receipt `native_bootstrap_receipt-20260917T020446Z.json`) |
| `D:/quant-data/configs/delivery_etf_loop.json` | real instance | verified 16-check consumer loop binding |
| `D:/quant-data/configs/recorder_replay.json` | real instance | durable SYNTHETIC session `sess-d7c9ad113b2e42f5` (replay/report reference; explicitly not market history) |

Read-only validation of all instance configs:
`.venv\Scripts\python.exe tools\delivery_finalize.py check-configs` — checks
paths, store identity, snapshot manifests, dataset publication and recording
journal presence; missing future work is reported as `pending_items`, never
invented.

## Phase report

`.venv\Scripts\python.exe tools\delivery_finalize.py report` regenerates
`reports/delivery04n/verification-matrix.json` +
`reports/delivery04n/delivery04n-report.html` (standalone HTML, no backend).
Facts are extracted from bound evidence files at run time; missing evidence
degrades the entry to `EVIDENCE_MISSING` instead of passing.

## Honest limits

* Expected market coverage is UNKNOWN everywhere: no calendar/listing
  evidence exists in scope; observed min/max dates never imply completeness.
* SS representative scope is the evidenced rb2605 windows only (1/5/15m
  datasets separate; semantic-v2 supersedes numeric-turnover v1, which stays
  immutable history); calendar, units and broader eligibility unknown. Both
  public Alpha entrypoints on the postfix snapshot refuse at the earlier
  unmapped-exchange identity check — no VWAP-specific exception is reached.
* RQ futures: final real case PASS 14/14 (zero canonical publication); the
  time-label direction remains UNKNOWN by design pending scoped time
  evidence.
* LIVE_NOT_RUN is a standing label, not a placeholder to be filled by
  connecting an account.

## Rollback

Rollback is environmental, not data-related: uninstall the plugin
(`pip uninstall vnpy_researchstore`) or stop using it; remove the console
entries; keep using the original VeighNa launcher and database
(`SETTINGS["database.name"]` unchanged). Snapshots and published revisions
are immutable and remain on disk; no default `.vntrader` or global settings
are modified by any command in this README.
