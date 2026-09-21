# STORE-20260916 — execution contract v0.1

## Authority and scope

User approved the detailed unified storage plan on 2026-09-16 and assigned actual CLI roles: Codex plans/co-ordinates; Kimi and OpenCode develop; Claude Code independently audits/tests. FIRST have Claude Code audit this plan, incorporate blocking corrections, THEN start development. Do not substitute internal agents for these developers/reviewer.

Personal Windows research, one local machine/multiple research projects. Complete P0–P3: inventory both source roots, canonical market data, immutable snapshots, CTA/Portfolio/Alpha consumers, durable recording/recovery/sealing. P4 PIT financial/option/convertible research adapters are catalog-only in v0.1. Do not narrow the implementation to smoke-only wrappers or claim unknown data semantics are qualified.

Allowed edits: this integration and additive storage/CLI/test/docs changes to ../vnpy_datasource. Raw roots and D:/repo/dataSource are read-only. Do not edit vnpy core, installed site-packages, existing .vntrader settings, archived Chan workspace, ETF research or unrelated dirty files. Root HANDOFF belongs to another task; do not replace or advance it. No git add-all, commit/push, account connection, order or funds action. No source credentials in files/output.

Source roots:
- D:/BaiduNetdiskDownload/新数据库/ssquant数据库_20260425
- D:/BaiduNetdiskDownload/全息日线

Store root: D:/quant-data. Source archives stay in place. Capture a consistent SQLite backup for mutable source input. No recursive source edits, whole-tree extraction or whole-year minute-data materialization.

## Current verified environment/facts

Studio interpreter D:/veighna_studio/python.exe is Python 3.13. Existing pyarrow 25.0.1, polars 1.44.2, pandas 2.2.3, pytest 9.1.1; DuckDB and mypy not installed there. Develop in this package's .venv created from Studio with --system-site-packages; additions only in this venv. Do not upgrade existing Studio distributions. Record dependency versions. Existing integrations/vnpy_datasource is untracked; preserve and baseline it before editing.

SSQuant: 123 files/19.67GB including 9.44GB backup. Main DB 10.22GB, 1,395 bar tables (465 series x 1/5/15m), 88 products; 88x888, 88x777, 289 contracts. Indexed first/last span 2019-01-02 to 2026-09-01 but not uniform coverage. 68,022,890 is LOG-reported rows, not verified full COUNT. Has four staging tables (18,151 rows) and simnow_bar_meta (18,159 rows). Eight confirmed main-table SimNow keys on 2026-07-01: A888 11:29/15:04; RB888/SC888/ZN888 each 11:30/15:16. Do NOT classify every meta/main time overlap as contamination; staging and vendor continuous prices often reference different real contracts. Source schema has 27 standard columns plus four drifting tables. openint can be negative, cumulative_openint is candidate total OI. MA amount untrusted (903/1000 sample VWAP checks outside OHLC). real_symbol and source case must survive. 888/777 selection/roll/adjustment rules unverified.

Holographic: 3,608 files/53.91GB; daily 18 gzip CSV, 14,525,233 rows, 5,475 codes, 2009-01-05–2026-06-17, factor ALL 1.0 => adjustment UNKNOWN, not proven raw. 33 columns, extensive missing moneyflow/ST/industry; those columns not proven PIT. RQ groups: index 26.25GB, high-value 7.94GB, futures 7.65GB, ETF 3.67GB, convertible 2.64GB, options 2.08GB, other 1.20GB, actions .89GB, A-share PIT .62GB. Primary packages are tar.zst with CSV/Parquet members and manifests/SHA sidecars.

RQ ETF README explicitly adjustment:none; minute label END (09:31 => 09:30–09:31). Futures Parquet carries trading_date and dominant_id; member context may supply underlying identity. Universe contains exchange/listing/expiry/multipliers. Do not map .INDX blindly to SSE/SZSE. Zhengzhou three-digit contracts require unique universe/date match, not guessed decade.

IMPORTANT: ETF 133 deterministic repairs already occur INSIDE rebuilt 2016/2017/2018 base archives (QUALITY_REPAIR_20260905.json), not only later overlay. Load correction index before importing base. 118 rows' volume/amount differ from upstream_refetch audit. Keep old/new/upstream candidates; disputed keys excluded from default backtest with visible coverage gaps. Counts are tied to input hashes, not rules to truncate future datasets. Example 160105.XSHE 2017-09-19 13:01: repaired 0/0 versus refetch 15000/15840.

Other limits: convertible 4,911-row refetch overlay/audit missing locally; index 2014 actual SHA matches sidecar but differs root manifest (version conflict, not proven corruption); recommended shares 37 annual path missing but older actions archive contains copies; latest ETF sample is Sept9–11 vs base through July31, August gap unresolved. PIT sample preserves same quarter info_date 2025-04-19 and 2026-04-25; never upsert by only security/quarter. Dividend value 3.62 with round_lot10 is not per-share3.62. Preserve knowledge-time uncertainty.

## Mandatory amendments from actual Claude Code plan audit

Audit session30c8e062-f2aa-42a3-9eb0-9b7ba03dc88a returned ACCEPT_WITH_REQUIRED_CHANGES, exit0. PLAN_AUDIT.md is the complete original reviewer output; PLAN_AUDIT_DISPOSITION.md records decisions. The following clarifications are binding and override ambiguous wording elsewhere:

1. B1: RecordingMainEngine.close MUST enqueue RecorderStopBarrier BEFORE ANY call to super().close or event_engine.stop. Unregister callbacks ONLY inside the barrier handler on the still-running event-dispatch thread (not immediately when UI requests stop), fixing accepted cutoff after prior queued events. Wait for writer committed==accepted and CLOSED. Only then call super().close. Timeout10sec=>STOP_FAILED, do not call parent close or claim success. Closing from the dispatch thread itself must not deadlock; reject or marshal request to controlling thread.
2. B2: BOTH ResearchAlphaLab.load_bar_data AND load_bar_df inherit native inclusive-end semantics. Convert exactly to core half-open queries or apply precise <=end filtering. An actual final bar timestamp equal to end MUST survive, including after extended_days calculation. Database bridge has the same obligation. Do not add a whole bar/day indiscriminately.
3. B3: recording has separate typed API recover_session(root,session_id)->SessionRecoveryReport and seal(SealRequest)->SealReceipt; request includes session_id,committed seq range,transform version,source/calendar semantic spec. CLI verbs recover-session and seal distinct from import recover/freeze. Replay optional CLI consumes committed events without live source connection. Actual recording CLI/UI entry must also exist; no claims based only on library stubs.
4. N2: Native Database overview omits5m/15m and other unrepresentable intervals, reports omitted capabilities in diagnostics, and never relabels them as1m. Core overview retains actual intervals. ResearchAlphaLab v0.1 supports native1m/1d, not1h (Database may support1h).
5. N3: freeze captures ALL selected datasets/partition heads, versioned quality decisions and references in ONE short SQLite read transaction. Snapshot manifest written afterward from that immutable capture; no independent per-dataset current-head reads.
6. Import origin: bootstrap explicitly selects D:/repo/vnpy core on sys.path and records vnpy.__file__; set isolated cwd BEFORE importing vnpy.trader.utility or modules that transitively initialize it. Explicit plugin import and singleton checks happen after that. Same4.4.0 version does not prove same source.
7. Time-contract follow-up: minute observations with evidenced normalized bounds may have trading_date=NULL and explicit uncertainty; daily imports require non-null trading_date and use it for identity/dedup. No natural-date inference. Native consumers refuse ambiguous required time semantics; successful publication is not data qualification. See TIME_CONTRACT_REVIEW.md and TIME_CONTRACT_DISPOSITION.md.
8. SSQuant label evidence is scoped to captured source/table/range and versioned in the transform/receipt. Validate the selected scope using available source1m/5m evidence; neither global START guessing nor permanent blanket rejection of all SSQuant satisfies the plan. Unknown ranges preserve source labels/payload as queryable/inspectable candidates; only evidenced bounds become normalized canonical bars.

## Layout and boundaries

One installable distribution vnpy_researchstore, two packages:
- research_store: pure storage/models/schemas/catalog/objects/importers/quality/coverage/revisions/snapshots/reader/journal/aggregation/CLI, NEVER imports vnpy or provider SDK.
- vnpy_researchstore: Database, AlphaLab, bootstrap and recorder/UI bridges. Optional vnpy dependency; lazy imports.
- tests/, configs/, tools/, README.md, TASKS.md, VERIFICATION.md, CHANGELOG.md.

Data layout D:/quant-data: store.json, catalog.sqlite, objects/, manifests/revisions/, manifests/snapshots/, captures/, staging/, journals/, configs/, reports/, exports/, runtime/. Init only empty directory or correctly identified existing store. Parquet Zstandard immutable content-hash filenames; logical partitions in manifests. Never glob current directories when reading a snapshot.

## Core contracts

Semantic specification: source_id, asset_class, record_kind, interval (1m/5m/15m/1h/1d), adjustment (none/qfq/hfq/unknown), adjustment_version, series_kind/rule_version, timezone, source_time_label, volume_unit, turnover_unit, origin_method, schema_version. dataset_id hashes canonical semantic JSON. Contents advance revision, not arbitrary new semantic IDs by import date. Sources/adjustments/native-vs-derived data never silently merge.

Bars carry dataset identity, instrument OR series identity, original symbol, exchange, bar_start/bar_end UTC int64 ns, trading_date, original timestamp/label, float64 OHLCV/turnover/OI with real NULL, provenance locator/batch/transform, completeness and field quality, continuous-to-real-contract mapping. Keep source OI/amount and nonstandard columns in extensions. Nonfinite input becomes explicit missing/invalid, not valid infinity. Daily key is trading_date, not UTC midnight assumption. Historical ingested_at is not available_at. Trading day independent of natural date. Keep unknown units/times/corporate adjustment explicit.

Catalog SQLite: WAL, foreign_keys=ON, synchronous=FULL, busy_timeout=5000, user_version=1. Tables assets (origins,size,hash,format,discovery), datasets (semantic/schema), batches (idempotency,input,adapter/config,state,counts/errors), revisions (dataset,partition,parent,manifest/hash,rows,batch), partition_heads (dataset+partition=>revision), snapshots (manifest/hash), quality_issues (scope/code/evidence/resolution), recording_sessions (source/spec/journal/status/sealed outputs). Detailed security/calendar/coverage/conflict rows are versioned Parquet/sidecars, not millions of per-bar SQLite catalog rows. Fast discovery may have unverified hash; formal import hashes the actual input.

Partitions: daily dataset/year; equity/ETF minute dataset/exchange/year-month/stable instrument bucket (16); futures minute dataset/product/year-month; tick source/trading_date/exchange. Sorted instrument/time/sequence; target128–256MB. Each revision represents COMPLETE active file set for its partition; avoids query-time arbitrary dedup.

Publishing: record base heads; stream into staging; validate/readback/schema/count/key/order/hash; flush and atomic same-volume publish immutable data/sidecars/manifest; BEGIN IMMEDIATE short transaction; compare heads to base; insert revision/update heads/publish batch atomically. On head change rebuild, never overwrite another writer. No conversion while holding catalog transaction. State running -> prepared -> published, failed on error. recover prepared validates files and base; published returns prior receipt; orphan files reported, not automatically deleted; missing/tampered published object fails, never fallback.

Idempotency hashes asset contents + member/table/range + dataset + adapter/config/mapping versions. Same key/same values dedup ignoring audit timestamps, preserve source counts. Same key/different values => conflict sidecar existing/candidate/evidence; no last-wins. Unaffected new rows may publish, but default freeze on unresolved conflict range fails. Explicit resolve existing/candidate/quarantine creates NEW revision, never changes old snapshots. Deterministic repairs not market observations. Quarantine creates visible gaps, no zero/forward fill.

freeze captures chosen heads consistently then writes immutable snapshot manifest with exact revisions/files/hashes, calendars/mappings/conversion versions, field requirements, quality/coverage and explicit allowed gaps. New heads/issues never alter old snapshot interpretation. Default unresolved_conflicts=error; known gaps require explicit allow_known_gaps and recorded reasons. Dataset ambiguity is error, not latest-source selection.

Public API: inspect_asset -> AssetInspection; import_asset(ImportRequest)->ImportReceipt; recover(root,batch_id?)->RecoveryReport; coverage/quality(selection); resolve_conflict; freeze(SnapshotRequest)->SnapshotRef; open_snapshot(id)->SnapshotReader. reader.bars/ticks(dataset_id,instruments,start,end,required_fields) yields Arrow RecordBatches, [start,end). Distinguish unavailable field, no data, coverage gap, integrity error. DuckDB per-process,4 threads,8GB limit, spill to store staging. No shared writable DuckDB.

CLI qstore and python -m research_store: init,inspect,import,recover,coverage,quality,resolve-conflict,freeze,verify,export,report. JSON stdout, progress stderr, nonzero errors and explicit partial/unknown statuses. Input configuration paths preserved in receipt. Do not claim publication=complete usable coverage.

## Importers

General readers: sqlite/gzipCSV/tar.zstCSV/tar.zstParquet. Never execute downloaded scripts or pickle. Validate member paths, reject traversal/symlinks; no extractall. CSV chunks100k, one compressed member at a time; Parquet spool member to controlled staging then rowgroups. Record input/accepted/duplicate/quarantine/parse-failure counts. A failed member cannot be swallowed by successful neighbors.

SSQuant backup API from mode=ro into captures, quick_check+SHA, read only captured DB thereafter. table x month units. Infer each actual schema. Real contracts before continuous datasets; source 1/5/15 distinct from own aggregation. Source starts supported by sample 1m-to5m windows but must validate selected scope. No global turnover multiplier heuristic. Preserve raw amount when normalized turnover unavailable. Calendar/unique code mapping prerequisite for qualified trading-day uses. Apply precise8-key/source classification above; staging independent simulated source. continuous rule unknown => candidate research data, not executable synthetic contract.

RQ metadata + corrections before bars. ETF510130/510300 initial1d/1m,159915 overlap with existing verified source receipts for units. END minus1m; no midday filler. Base repair133 index applies to all versions. latest is a new asset with explicit merge/conflict checks. Read contractual none price semantics with evidence. Futures import contract_1m_none then dominant_map then dominant1d/1m. Keep trading_date,dominant_id,member identity; verified contracts can backtest, unknown continuous rule cannot masquerade as real contract fills.

JQ all33 columns preserved, OHLCV+extensions; adjustment unknown despite factor1; no flow NULL->0, preserve suspended/placeholder states. Observation queries allowed; unknown adjustment blocks default return backtest qualification. Existing datasource raw stock histories provide stock backtest path while JQ semantics unresolved.

PIT/option/convertible/etc catalog only first release, but list package members/schema/sample capability and known missing/refetch/version issues. Expected coverage only when calendar,sessions,list/delist,suspensions support it; otherwise expected unknown. observed/accepted/quarantined/expected plus reasoned interval sets. min/max is not completeness.

## DataSource and consumers

Add target=store to existing download/storage dispatch. CRITICAL: directly consume Client records/metadata/attempts/request/registry_sha256; do NOT use _normalized_rows()/to_bars() since those turn NULL into zero. Preserve existing sqlite/alpha behavior and late-import store dependency. Non-ok result cannot create success batch. No consumer modification of registry/credentials/runtime.

Database(BaseDatabase) read-only single-snapshot. Native MINUTE/HOUR/DAILY only; 5/15m never MINUTE. save/delete raise ReadOnlySnapshotError; native load_tick_data raises UnsupportedCapability in v0.1 (core tick query supported). Overview snapshot-only. Required OHLCV must validate. Missing auxiliary defaults error; explicit OHLCV-only allow_missing_auxiliary returns NaN+extra/receipt, not fake0. Stock OI not_applicable may map0 explicitly; missing futures OI not equivalent. Preserve provenance in extra. Bridge native inclusive end precisely to internal half-open, not arbitrary extra bar/day.

Bootstrap new process: config+snapshot validate; explicitly import plugin (no swallowed ModuleNotFoundError); ensure vnpy database singleton is uninitialized; set process-only nonsecret settings; get_database and assert plugin type+snapshot ID; THEN load CTA/Portfolio. No hot snapshot switch/LRU reuse, no current vt_setting edit. Isolated runtime directory set before vnpy utility imports. Record snapshot/adapter/config in run receipt. Existing SQLite never used as fallback.

ResearchAlphaLab(lab_path,store_root,snapshot_id), overrides load_bar_data/load_bar_df and prohibits market-data saves. Preserve extended_days, column/normalization/suspension semantics; handle empty inputs/windows; bind output dir to snapshot. OHLC initial-close normalize; retain original distinct VWAP preprocessing (do not silently refactor factors). Default features reject missing/untrusted turnover. Equity vwap turnover/volume; futures only verified single-side volume and effective multiplier => turnover/(volume*multiplier). volume0=>NULL, unknown units/multiplier=>error.

## Recording

Independent local ResearchRecorderApp/Engine+minimal statusUI; not old1–60sec UI semantics. No automatic gateway/account connection or strategy loading. Explicit real-instrument list. Different sources for sim/production; no LOCAL synthetic sequence. TickData does not automatically mean trade-by-trade; quote snapshots labelled accordingly.

Journal one session/SQLite and OS-owned lock. PID/heartbeat are diagnostics, never authority to steal lock. Events PK(session_id,seq), kind,instrument,event_ts_ns(nullable),received_ts_ns,source_event_id,payload/hash. session_meta spec/state/watermarks. Copy event into bounded queue100k. Single writer thread and SQLite connection;250ms or1000 events whichever first, FULL sync. Events+committed watermark same transaction. Same seq/hash replay idempotent; same seq/different hash integrity error, never REPLACE. Full queue/write error=>ERROR, stop admission, visible rejected count/backlog/watermarks; no silent drop or unbounded event-thread block.

Shutdown: existing MainEngine.close stops EventEngine first. Local RecordingMainEngine override issues RecorderStopBarrier while event thread active. Barrier fixes last accepted seq/cutoff and unregisters recorder callbacks. Writer drains/commits through cutoff; CLOSED only committed==accepted. Only then parent close.10sec timeout=>STOP_FAILED visibly, retry; do not falsely mark closed. Guarantee local accepted events, not upstream or postcutoff arrivals.

Recovery: unclosed session UNCLEAN_END, replay only committed sequence; new session links predecessor. Sealing idempotency session+watermark range+transform. Aggregate committed events sorted by eventtime/sequence. End-session/tradingday publishes final files; provisional running bars excluded from backtest snapshots. Cumulative volume/amount reset/unknown first baseline, gaps/late/out-of-session/partial lastbar remain visible. No negative-delta clamp pretending completeness; sampled-quote aggregates not full market OHLCV. Late correction new revision only. Journals retained14days AFTER verified sealing/publish; canonical objects/snapshot files no auto-delete.

## Work packages and gates

WP00 baseline/env/package/tasks; WP01 contracts/catalog; WP02 immutable publish/revisions/conflicts/snapshot/recovery; WP03 inventory/readers; WP04 RQ ETF real-data loop; WP05 datasource store target; WP06 SS/JQ/RQ futures+coverage; WP07 database/Alpha/bootstrap; WP08 recorder/journal/UI; WP09 aggregation/sealing; WP10 delivery/verification. Dependencies00->01->02;01->03->04;02+04->05/06/07;01+02->08->09;all->10. Freeze interfaces before parallel work. No actor edits another actor's owned paths without coordinator handoff.

Kimi owns pure core/catalog/publish/snapshot/journal/aggregation. OpenCode owns importers/quality/coverage and vnpy bridges plus datasource additions, after interface contract. Split tests accordingly. Codex writes plan/task assignments/status only, not product implementation. Claude independently audits before dev and reviews/tests after bounded milestones; findings return to assigned developers.

Required tests: repeat import; concurrent same-partition CAS; interrupt file-write/rename/commit recovery; snapshot immutability; tamper/missing file errors; NULL roundtrip; endlabel/night/holiday/no filling; frequency distinction;8 SimNow quarantine and stage coexistence;133 base repairs/118 candidate differences; JQ factor unknown; ambiguous Zhengzhou mapping; bad archive/member/path/hash versions; direct datasource preservation+legacy regressions; native bridge no fallback and identical common fields; Alpha preprocessing/multiplier/zero/empty; tick same-time/replay; queue overflow/disk failure; shutdown barrier; killed-process recovery; replay deterministic; cumulative resets/gaps/late/partial bars.

Fixtures minimal reconstructable data, not bulk purchased data in git. Real validation: raw ETF1d/1m, raw stock datasource, real futures contract, night and continuous mapping samples, MA bad amount, correction conflict. Record package/member/hash/range, input and output counts, actual query reads through both consumers. Real gateway absent=>LIVE_NOT_RUN, not substitute synthetic test PASS.

Verify: focused pytest new package and entire existing datasource tests; ruff both integrations; scoped mypy new packages; root tools/sync_check.py (do not weaken unrelated gates). Record initial baseline and distinguish unrelated failures. Build package and test pure-core import without vnpy side effects. Representative import/query/record replay timings and peakmemory; persistent backlog or memory excess requires fix, no invented throughput promise.

Ship configs smoke_import.json,smoke_snapshot.json,recorder_replay.json,backtest_profile.json with actual runnable paths/IDs from verified execution (not placeholders). README install/import/freeze/backtest/record/stop/recover;TASKS progress;VERIFICATION real facts/failures/not-run;CHANGELOG; machine-readable asset/coverage/conflict reports; simple HTML coverage/source/quality/watermark/disk report. First usable snapshot id. Journal deletion narrowly scoped and path-checked; raw/canonical kept. Rollback just original launcher/environment, no default config changed.

Completion distinguishes software functionality, ready datasets/ranges, candidate/quarantine/unknown data, real recording status. Finish all v0.1 work packages; do not redefine completion as only prototype or partial CLI facade.
