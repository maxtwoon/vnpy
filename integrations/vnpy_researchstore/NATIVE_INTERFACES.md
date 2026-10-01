# Native interfaces — vnpy_researchstore v0.1 (Kimi native02B scope)

Stable insertion boundary for the CLI/report/export workers. Everything here
is implemented and covered by `tests/test_native_*.py`; anything not listed
here does not exist yet. The core store contract lives in `INTERFACES.md`;
this file only covers the native (`vnpy`-facing) adapters.

## Package

`vnpy_researchstore` — lazy package init: `import vnpy_researchstore` has NO
vnpy/core side effects (PEP 562 `__getattr__`), so bootstrap can order cwd and
`sys.path` before any `vnpy.trader` import.

Modules: `database.py` (native `BaseDatabase` plugin), `alpha.py`
(`ResearchAlphaLab`), `bootstrap.py` (guarded process setup + run receipt),
`native_common.py` (shared interval/exchange/semantics/loading helpers — the
single place where inclusive-end conversion and dataset resolution live).

## Database plugin (`vnpy_researchstore.database.Database`)

Activated by `SETTINGS["database.name"] = "researchstore"`; the class name
`Database` is required by `vnpy.trader.database.get_database`. Constructor
takes no arguments and reads process-local SETTINGS:

| key | required | meaning |
|---|---|---|
| `researchstore.root` | yes | research store root |
| `researchstore.snapshot_id` | yes | bound immutable snapshot |
| `researchstore.allow_missing_auxiliary` | no (default `false`) | explicit OHLCV-only mode: missing/untrusted auxiliary values come back as NaN with `extra`/receipt notes instead of raising |
| `researchstore.exchange_map` | no | JSON file extending the source exchange-label map |

Behavior:

* Read-only snapshot view: `save_bar_data`/`save_tick_data`/`delete_*` raise
  `research_store.ReadOnlyError`; `load_tick_data` raises
  `UnsupportedCapabilityError` (v0.1); there is no SQLite fallback.
* `load_bar_data(symbol, exchange, interval, start, end)` — native inclusive
  end: a bar whose timestamp equals `end` is returned (exact half-open
  conversion + precise `<= end` filtering, never a padded bar/day). Supports
  `Interval.MINUTE`/`HOUR`/`DAILY`; anything else raises
  `UnsupportedCapabilityError`. Default loads are QUALIFIED: a query
  intersecting a default-qualified exclusion captured in the snapshot
  manifest (all deterministic repaired keys — the full repaired-key set,
  including repairs equal to their upstream candidates, not merely the
  disputed subsets) raises `CoverageGapError` unless the snapshot explicitly
  allowed the gap; allowed exclusions stay missing from the returned bars
  (the allowance permits the missing interval, never the rejected row; no
  filler, no silent drops).
* Symbol resolution: identity match on stored `instrument_id`/`series_id`
  against datasets of the requested interval inside the bound snapshot. The
  bridge resolves between the stored identity and the native request using the
  actual exchange labels and the explicit exchange map — importers preserve
  the vendor/source identity on disk, which may be the bare native symbol
  (`000001`) or a vendor-suffixed id (`510130.XSHG`); both are legitimate
  stored forms and neither is ever rewritten. For a native request
  `(symbol, exchange)` the candidate stored identities are the bare symbol
  plus `symbol.<label>` for every source label the exchange map already maps
  to the requested exchange (e.g. `510130` + `510130.XSHG` for
  `Exchange.SSE`). Arbitrary dotted symbols are never guessed and the exchange
  is never inferred from leading digits: a candidate is only formed from labels
  the explicit map already knows, and resolution additionally requires the
  row's own exchange label to map to the requested exchange. When BOTH the
  bare and a vendor-suffixed identity carry rows for one native symbol in one
  dataset, that is an explicit `StoreError` (ambiguous stored identities) —
  the bridge never silently merges two stored identities into one native
  symbol. The discovery/validation scan is OBSERVATIONAL (it must not depend on
  the caller's requested window — a clean range stays resolvable even when
  another range of the same symbol carries default-qualified exclusions); the
  actual `load_bar_data` read is QUALIFIED for the effective requested range
  and raises `CoverageGapError` on intersecting unallowed exclusions, and it
  uses the resolved stored identity for the read so vendor-suffixed rows are
  found. Zero matches -> `[]`; multiple matching datasets -> `StoreError`
  (ambiguity is an error, never a latest-source preference); an
  otherwise-matching row with an unmapped exchange label -> `StoreError`
  (extend the map, never guess). Exchange labels are validated over the WHOLE
  streamed row range of the requested symbol (every emitted batch/partition,
  not just the first): once a dataset is selected, every row of the symbol in
  it must carry a label mapping to the requested exchange — a later
  unmapped/NULL label, or one mapping to a different native exchange, refuses
  the whole load (`StoreError`) instead of silently relabelling, dropping, or
  splitting rows. Empty leading batches are not treated as absence of data,
  and only distinct labels are retained (streamed validation, no row
  materialization). The same per-row check re-runs during loading, so a bar is
   never stamped with an exchange its own row does not map to. Returned bars
   are stamped with the NATIVE `symbol`/`exchange`; the immutable stored
   identity actually read is preserved in `bar.extra["source_identity"]`.
   A stored identity whose dotted suffix is NOT a label the exchange map
   declares (e.g. `510131.XZZZ`) is never formed as a candidate: a native
   request for its prefix finds no candidate rows and returns `[]` — an
   ordinary empty result, not an error, and never a guessed/stripped match.
   Such present-but-unmappable rows are reported by the overview diagnostic
   (below), so ordinary absence stays distinguishable from data that exists
   under an undeclared source identity.
* Semantic refusals (`StoreError`) before any bar is produced: unknown
  timezone, unknown source time-label semantics, unknown volume unit, unknown
  turnover unit (default mode).
* Auxiliaries: default mode requires usable OHLCV + turnover (+ open interest
  for futures/option); NULLs raise `MissingFieldDataError`, importer-flagged
  untrusted turnover raises as well. Equity/ETF/index open interest is
  not-applicable and surfaced as an explicit `0.0` with metadata — a missing
  futures OI is never that case. Explicit OHLCV-only mode returns NaN for
  missing/untrusted auxiliaries plus per-bar `extra["auxiliary"]` notes and a
  `Database.last_receipt` (`LoadReceipt` with row counts per degradation).
* Every returned `BarData.extra` carries `snapshot_id`, `dataset_id`,
  `source_id`, `adjustment`, `source_symbol`, `source_identity` (the exact
  stored `instrument_id`/`series_id` read — bare native id or vendor-suffixed
  id), `source_exchange_label`, `trading_date`, `source_label`,
  `completeness`, `field_quality`, `contract_id`, and `provenance`
  (asset/batch/transform).
* `get_bar_overview()` is computed from the bound snapshot only; store
  datasets at intervals vnpy cannot represent (5m/15m) are omitted and
  reported in `Database.diagnostics`, never relabelled as 1m. The overview
  presents the DEFAULT QUALIFIED view: rows excluded by the snapshot's
  default-qualified policy are omitted from counts, with per-dataset omitted
  counts reported in `Database.diagnostics` — consistent with what
  `load_bar_data` returns/refuses by default. DAILY entries
  derive their date identity, start/end and count from each row's
  `trading_date` (midnight, the same convention `load_bar_data` uses) — never
   from the tz-converted `bar_start`, so night-session bars whose bar_start
   crosses midnight still match the boundaries native reads return.
   MINUTE/HOUR entries keep real `bar_start` semantics.
   Symbols are presented under their NATIVE form: a stored vendor-suffixed
   identity whose suffix maps to the row's own exchange is shown as the bare
   native symbol (`510130.XSHG` -> `510130`); any other identity is kept
   verbatim — visible, never silently stripped or relabelled. Rows whose
   exchange label the map does not declare are omitted from the overview
   counts and reported per dataset in `Database.diagnostics` (with the
   verbatim unmapped labels and row counts) — present-but-unmappable data is
   distinguishable from ordinary absence, and the stored identities stay
   verbatim in the immutable snapshot.
   `get_tick_overview()` returns `[]`. Call `Database.close()` when done.
  A snapshot that predates the default-qualified policy capture (legacy
  manifest format) is refused by default loads and by the overview with an
  explicit error — its rows are never silently presented as qualified.
* Native datetimes: naive in `database.timezone` (vnpy convention). Minute/hour
  bars are keyed by `bar_start`; daily bars by `trading_date` midnight.

## ResearchAlphaLab (`vnpy_researchstore.alpha.ResearchAlphaLab`)

```python
ResearchAlphaLab(lab_path, store_root, snapshot_id, *,
                 multipliers=None, allow_missing_auxiliary=False,
                 exchange_map_path=None)
```

* Read-only market data: `save_bar_data` raises `ReadOnlyError`. The
  effective lab directory is `<lab_path>/<snapshot_id>`; `<lab_path>` records
  a `.researchstore_snapshot` binding and refuses reuse with a different
  snapshot id.
* Native 1m/1d only (`Interval.MINUTE`/`DAILY`); 1h and others raise
  `UnsupportedCapabilityError`.
* `load_bar_data(vt_symbol, interval, start, end)` — same inclusive-end and
  resolution contract as the Database (including the whole-stream exchange
  uniformity refusal above, via the same shared helper) and the same DEFAULT
  QUALIFIED policy: intersecting default-qualified exclusions raise
  `CoverageGapError` unless the snapshot explicitly allowed the gap, and
  allowed exclusions stay missing from the returned bars; additionally refuses
  unknown trading dates (minute candidates with NULL `trading_date` stay
  observation-only), unknown price adjustment, and untrusted turnover
  (default mode). A normal native vt_symbol (`510130.SSE`) therefore also
  resolves datasets that store the vendor-suffixed identity
  (`510130.XSHG`); returned bars carry the native `symbol`/`exchange` and
  `extra["source_identity"]` preserves the stored identity. An undeclared
  stored suffix (e.g. only `510131.XZZZ` rows) finds no candidates: both
  load methods return empty (`[]` / `None`), never a guessed match.
* `load_bar_df(vt_symbols, interval, start, end, extended_days)` — preserves
  the native windowing (`start - extended_days`, `end + extended_days // 10`),
  output columns (`datetime, open, high, low, close, volume, turnover,
  open_interest, vwap, vt_symbol`), OHLC first-close normalization and
  suspended-row zero->NaN masking. The `vt_symbol` column always carries the
  caller's NATIVE vt_symbol — never the stored vendor-suffixed identity.
  VWAP: equity-like `turnover/volume`;
  futures `turnover/(volume*multiplier)` requiring a verified effective
  multiplier in `multipliers[vt_symbol]` AND a verified single-side lot
  volume unit — otherwise an explicit `StoreError` refusal. `volume == 0` ->
  NaN VWAP. Empty request (`[]`) or an all-empty window -> `None` (stable).

## Bootstrap (`vnpy_researchstore.bootstrap`)

```python
config, identity = load_config(path)          # parse + validate, sha256 identity
session = bootstrap_session(config, identity) # NativeSession(receipt, database, backtesters)
```

Order enforced: validate config -> refuse if `vnpy.trader.utility` already
imported or the database singleton is initialized -> repo path + integration
path onto `sys.path`, `chdir` into isolated `runtime_dir` (creates
`runtime_dir/.vntrader`) -> import `vnpy` and assert `vnpy.__file__` is under
`repo_path` -> set process-local SETTINGS -> explicit
`import vnpy_researchstore.database` (no swallowed ModuleNotFoundError) ->
`get_database()` + assert plugin class and snapshot id -> only then import the
CTA/Portfolio backtester modules -> write
`<runtime_dir>/native_bootstrap_receipt-<ts>.json`.

One fresh process per snapshot; no hot-switching, no settings-file edits, no
SQLite fallback.

Config keys (`configs/native_backtest.json` template): `store_root`,
`snapshot_id`, `runtime_dir`, `repo_path`, `integration_path` (default: this
package's parent), `allow_missing_auxiliary`, `exchange_map`,
`database_timezone`, `backtesters` (`["cta"]`, `["portfolio"]`, or both),
`range` (receipt metadata). Unknown keys are rejected; keys starting with `_`
are comments.

## Entry commands

```bash
python tools/native_bootstrap.py --config configs/native_backtest.json
python tools/native_overview.py  --config configs/native_backtest.json
```

Both print JSON on stdout and exit nonzero on any refusal. `native_overview`
emits `{"config_identity", "snapshot_id", "overview": [...], "diagnostics":
[...]}` for CLI/report integration.
