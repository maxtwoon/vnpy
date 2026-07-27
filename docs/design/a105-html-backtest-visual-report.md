# A105 - Reusable HTML Visual Backtest Report

## Background

The user wants a reusable HTML report template that every `chan_strategy` backtest run can produce,
visualizing on the K-line chart: 笔 (bi), 中枢 (zhongshu), long/short entry and exit points, plus a
trade/order list table and other supporting elements (equity curve, summary stats).

Clarified with the user before writing this design (three scope questions, all answered):

1. **线段 (XD / duan) is out of scope for this task.** Neither this project's `chan_strategy/` nor the
   pinned `czsc==0.9.51` library computes a line-segment/duan structure anywhere today — only 笔 (`CZSC.bi_list`)
   and 中枢 built from 笔 (`chan_strategy/zhongshu.py::build_zhongshu_from_bis`). Building a correct
   bi→duan construction algorithm is independent Chan-theory analysis work, not "build a report template"
   work, and the user explicitly chose not to do it here. The report's data payload reserves an optional
   `xd` key (rendered if present, matching `czsc.utils.echarts_plot.kline_pro`'s existing `xd` parameter)
   so this can be wired in later without changing the report/chart code.
2. **Multi-symbol: one HTML file with tab switching** (pyecharts `Tab()`), not one file per symbol. This
   matches how `PortfolioEngine` already runs N `BacktestEngine`s per formal run (currently 4 research
   symbols per `examples/czsc_strategy/diagnostics/simnow_contract_map.json`).
3. **Integration: built into `BacktestEngine`/`PortfolioEngine` itself**, generated automatically at the
   end of every backtest run (behind an opt-in config toggle, default off — see Boundaries), not a
   standalone script the user has to remember to invoke separately.

## Existing building blocks (why this design reuses them instead of writing a chart engine from scratch)

- `czsc.utils.echarts_plot.kline_pro(kline, fx, bi, xd, bs, ...)` (installed, `pyecharts==2.1.0` already
  present in the environment) already renders an interactive HTML/JS K-line chart with candlesticks,
  volume, MACD, moving averages, 分型 (fx), 笔 (bi), an optional 线段 (xd) overlay, and buy/sell markers
  (`bs`, using `czsc.enum.Operate.{LO,LE,SO,SE}` for long-open/long-exit/short-open/short-exit) — see
  `CZSC.to_echarts()` in the installed package for the reference usage pattern this design follows for the
  kline/fx/bi payload shape.
- It has **no 中枢 (zhongshu) parameter** — this design adds a custom overlay (echarts `markArea` boxes on
  the K-line series, one box per zhongshu using `zd`/`zg`/start-end dt) rather than modifying the
  third-party library.
- `BacktestEngine.run()` already keeps `self.trade_bars` (the resampled trading-frequency bars) but the
  local `czsc_trade = CZSC(...)` object it streams bars into is **not** currently retained after `run()`
  returns — this design adds `self.czsc_trade = czsc_trade` as the only change inside `run()` itself, so
  `czsc_trade.bi_list` is available afterward for charting.
- `PositionManager._close_long`/`_close_short` (`chan_strategy/positions.py`) already build a `pair: dict`
  per closed trade (`open_dt`, `close_dt`, `open_price`, `close_price`, `pnl_pct`, `pnl_currency`, `volume`,
  `reason`, `reason_code`, ...) consumed via `strategy.get_combined_trades()`. It has **no `direction`
  field** today (long vs short is implicit in which method built it). This design adds
  `pair["direction"] = "long"` / `"short"` at the two build sites — additive, no existing field removed or
  renamed, so nothing that reads `pair` today breaks.

## Approach

### New module: `chan_strategy/html_report.py`

Pure functions, no engine-class coupling beyond reading public/added attributes, so they are independently
unit-testable against small synthetic fixtures (no real market data or SimNow connection required):

- `build_symbol_chart_payload(engine: BacktestEngine) -> dict` — maps one finished `BacktestEngine` to the
  `kline_pro`-shaped payload:
  - `kline`: from `engine.trade_bars` (`dt`, `open`, `close`, `high`, `low`, `vol`).
  - `bi`: from `engine.czsc_trade.bi_list`, in the exact dict shape `kline_pro`'s docstring specifies
    (`dt`/`fx_mark`/`start_dt`/`end_dt`/`fx_high`/`fx_low`/`bi`), following `CZSC.to_echarts()`'s own
    construction as the reference.
  - `zs`: from `chan_strategy.zhongshu.build_zhongshu_from_bis(engine.czsc_trade.bi_list, mode="segment")`
    (non-overlapping segmentation — the "displayed history" mode already documented in `zhongshu.py`, as
    opposed to `mode="recent"` which is for live signal evaluation) mapped to
    `{"start_dt": ..., "end_dt": ..., "zd": ..., "zg": ...}` for the markArea overlay.
  - `xd`: `[]` (reserved, see Background item 1).
  - `bs`: from `engine.strategy.get_combined_trades()`, two rows per pair (open + close), mapped to
    `Operate.LO`/`Operate.SO` at `open_dt`/`open_price` and `Operate.LE`/`Operate.SE` at
    `close_dt`/`close_price`, using the new `pair["direction"]` field to pick long vs short.
  - `trades_table`: the raw pair list plus `strategy` name, for the order-list table (see below) — not
    passed to `kline_pro`.
  - `summary`: the subset of `engine.generate_report()`'s already-computed fields needed for a per-symbol
    stat card (`total_trades`, `win_rate`, `total_return_pct`, `max_drawdown_pct`, `sharpe_ratio`,
    `symbol`, `period`) — **no new metric computation**, only reads existing report fields.
- `_zhongshu_markarea(zs: list[dict]) -> opts.MarkAreaOpts` — builds the echarts markArea boxes overlaid on
  the `kline_pro` K-line series via `.overlap()`, styled distinctly from bi/xd (different color/opacity) so
  centers are visually separable from strokes.
- `_trades_table_html(trades_table: list[dict]) -> str` — renders the 成交订单清单 as a plain HTML
  `<table>` (columns: `strategy`, `direction`, `open_dt`, `open_price`, `close_dt`, `close_price`, `volume`,
  `pnl_pct`, `pnl_currency`, `bars_held`, `reason`). Plain HTML/CSS, not a JS widget — keeps the report
  self-contained and avoids a second charting-library dependency for what is fundamentally a data table.
- `render_backtest_html_report(symbol_payloads: dict[str, dict], out_path: Path, title: str) -> Path` —
  builds one `pyecharts.charts.Tab()`, one tab per symbol (`tab.add(grid_chart, symbol)`), and after
  `tab.render(out_path)` post-processes the written HTML to inject the summary card + trade table markup
  under each tab's chart div (pyecharts' `Tab` doesn't natively support non-chart HTML per tab, so this
  design appends the summary/table as plain HTML blocks positioned by tab index via a small inline
  `<script>` that shows/hides them in sync with pyecharts' own tab-click handler — see "given the framework
  doesn't support it" note in Notes for the Next Agent). Returns the written path.

### Engine integration points

- `chan_strategy/config.py`: add `"html_report_enabled": False` and `"html_report_dir"` (default:
  `str(Path(__file__).resolve().parents[1] / "diagnostics")`, i.e. alongside existing diagnostics
  artifacts) to `STRATEGY_CONFIG`. Default **off** — this is the key backward-compatibility guarantee: no
  existing caller/test that runs a backtest without opting in gets new file I/O or a new report-dict key.
- `BacktestEngine.generate_report()`: after building `report` as today, if
  `STRATEGY_CONFIG["html_report_enabled"]` is true, call `render_backtest_html_report({report["symbol"]:
  build_symbol_chart_payload(self)}, ...)` and set `report["html_report_path"]` to the written path.
- `PortfolioEngine.run()`: after `symbol_results` is built (all per-symbol `BacktestEngine`s have finished
  `run()`), if the toggle is on, collect one payload per successful symbol and call
  `render_backtest_html_report(...)` once for the whole portfolio (this is the "N tabs, one file" path);
  store the path on the top-level portfolio report dict, not per-symbol.
- Both integration points are additive at the end of an existing method — no change to control flow, sizing,
  signals, or risk logic.

## Data / interface summary

```text
build_symbol_chart_payload(engine) -> {
    "kline": [{"dt", "open", "close", "high", "low", "vol"}, ...],
    "bi":    [{"dt", "fx_mark", "start_dt", "end_dt", "fx_high", "fx_low", "bi"}, ...],
    "xd":    [],  # reserved, not computed this task
    "zs":    [{"start_dt", "end_dt", "zd", "zg"}, ...],
    "bs":    [{"dt", "price", "op", "op_desc"}, ...],   # op in czsc.enum.Operate
    "trades_table": [pair-dict with "direction" added, ...],
    "summary": {"symbol", "period", "total_trades", "win_rate", "total_return_pct",
                "max_drawdown_pct", "sharpe_ratio"},
}

render_backtest_html_report(symbol_payloads: dict[str, payload], out_path: Path, title: str) -> Path
```

## Boundaries (explicitly not done in this task)

- No 线段/duan construction algorithm (Background item 1) — `xd` stays an empty, documented hook.
- No change to any trading/signal/risk-control logic anywhere in `chan_strategy/` — the two source changes
  (`self.czsc_trade` retention, `pair["direction"]`) are additive/read-only from the strategy's perspective.
- No pixel-level / visual-rendering regression tests (not feasible in this test suite) — tests instead
  assert on the **data payload** (shapes, counts, required keys, `Operate` values) and that the written HTML
  is non-empty and contains the expected tab titles / summary numbers as substrings.
- Does not touch the SimNow observation workflow (`diagnostics/run_next_work.ps1` and friends) — that is a
  separate live-capture/replay system, not `BacktestEngine`/`PortfolioEngine`. Verify with the existing
  SimNow preflight command only to confirm this task did not accidentally break it (it shouldn't, since no
  `diagnostics/` file is touched), not as a feature integration point.
- Does not add CSV/Excel export of the trade list — only the embedded HTML table.
- Does not change the default backtest behavior for any existing caller/test — `html_report_enabled`
  defaults to `False`.

## Acceptance Criteria

- [ ] New module `examples/czsc_strategy/chan_strategy/html_report.py` implements
      `build_symbol_chart_payload`, `render_backtest_html_report`, and the private helpers described above.
- [ ] `BacktestEngine.run()` retains `self.czsc_trade` after completion (the trade-frequency `CZSC` object,
      not the daily/4H ones).
- [ ] `positions.py`'s `_close_long` and `_close_short` pair dicts each gain a `"direction"` field
      (`"long"`/`"short"`); no existing pair field removed, renamed, or changed in meaning.
- [ ] `STRATEGY_CONFIG` gains `html_report_enabled` (default `False`) and `html_report_dir` (default under
      `examples/czsc_strategy/diagnostics/`).
- [ ] `BacktestEngine.generate_report()` writes a single-symbol HTML report and sets
      `report["html_report_path"]` only when `html_report_enabled` is `True`; report dict is byte-for-byte
      unchanged (no new keys) when the toggle is `False`.
- [ ] `PortfolioEngine.run()` writes one multi-tab HTML (one tab per successful symbol) only when the toggle
      is `True`; no change to its report dict when the toggle is `False`.
- [ ] Each symbol's chart shows, at minimum: candlesticks, volume, MACD (from `kline_pro` defaults), 笔
      (bi), 中枢 (zhongshu markArea boxes, visually distinct from bi), and long/short entry+exit markers
      (`Operate.LO/LE/SO/SE`).
- [ ] Each symbol's tab includes a 成交订单清单 HTML table with at least the columns listed in "Data /
      interface summary" above, and a summary stat card sourced only from existing `generate_report()`
      fields (no new metric computation).
- [ ] `xd` payload key exists and is empty; a one-line comment in `html_report.py` points at this design
      doc's Background section for why.
- [ ] `pyecharts` is declared in `examples/czsc_strategy/requirements.txt` (it is already installed in this
      environment, but the subproject's own dependency manifest must name it — same standard this repo
      already applies to `czsc==0.9.51` in that file).
- [ ] New unit tests (paths TBD by dev, under `examples/czsc_strategy/tests/unit/`) cover: payload shape for
      a small synthetic `BacktestEngine`-like fixture (bi/zs/bs counts and required keys, `Operate` values
      correct for long vs short), and a smoke test that `render_backtest_html_report` writes a non-empty
      `.html` file containing each symbol name and both the trade-table and summary numbers as substrings.
      No test may require network access, a real SimNow connection, or the real historical SQLite DB.
- [ ] `python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"` — report the exact before/after
      count (this task adds tests, so the count must increase by exactly the number of new tests added; note
      this explicitly, don't just report a bare final number).
- [ ] `python -m pytest examples/czsc_strategy/tests/unit -q -m realdb` — unaffected, still passes (per
      `AGENTS.md` rule: verify, don't assume, even though no `backtest_engine.py`/`positions.py`/`signals.py`
      *signal or sizing* logic changed — `positions.py` is touched for the additive `direction` field).
- [ ] `powershell -ExecutionPolicy Bypass -File examples/czsc_strategy/diagnostics/run_next_work.ps1
      -Preflight` still passes unchanged (confirms no accidental breakage of the unrelated SimNow workflow).
- [ ] `python tools/sync_check.py` (root) and `python tools/sync_check.py --root examples/czsc_strategy`
      both pass.
- [ ] `ruff check` on touched files: report before/after counts per this series' established practice (repo
      ruff baseline is dirty by design; compare touched-file counts, not whole-repo counts).
- [ ] `examples/czsc_strategy/VERSION` / `CHANGELOG.md` bumped in the same commit (current version `0.2.44`);
      changelog entry names the new HTML report feature and the two additive schema changes
      (`self.czsc_trade`, `pair["direction"]`).
- [ ] Manual Verification section includes: an actual small backtest run with `html_report_enabled=True`,
      the resulting `.html` file path, and a plain-text description of what renders in each tab (tabs
      present, chart elements visible, table populated) — dev must actually generate one sample file, not
      only rely on unit-test assertions.
- [ ] Scope check before handoff: `git status --short` shows only this task's files staged.

## Notes for the Next Agent (dev = kimi-code)

1. **Why a post-render HTML patch for the summary/table instead of a "proper" pyecharts component**:
   pyecharts' `Tab()` container is designed for chart-to-chart tab switching; it has no first-class way to
   attach arbitrary non-chart HTML (a table, a stat card) to a specific tab that shows/hides together with
   that tab's chart. Two options were considered: (a) render the `Tab()` HTML via `.render_embed()`/`.render()`
   then string-inject a `<div data-tab-index="N">...</div>` block per symbol plus a small vanilla-JS
   listener that mirrors pyecharts' own tab click handler (chosen — keeps the file self-contained, no new JS
   dependency); (b) build a fully custom HTML/JS template that manually re-implements tabs and only uses
   pyecharts for the chart canvases (rejected — throws away `Tab()`'s built-in switching logic and styling
   for no real benefit). Pin down pyecharts 2.1.0's actual generated tab-click DOM/JS hook before writing the
   injection code — inspect one `Tab().render()` output file directly rather than guessing the markup.
2. **`zhongshu.build_zhongshu_from_bis(..., mode="segment")` vs `mode="recent"`**: use `"segment"`
   (non-overlapping, from-the-beginning) for the report's *displayed* centers — it is deterministic and
   matches "show me the centers that actually existed," whereas `"recent"` is deliberately overlapping and
   tuned for live signal evaluation, not a clean visual history. Do not reuse whatever mode a given
   `sell_signals.py`/`signals.py` call site happens to use for live decisions — this is an independent,
   display-only zhongshu build, same input (`bi_list`), display-appropriate mode.
3. **`bi` payload dict shape must match `kline_pro`'s docstring exactly** (`dt`, `fx_mark`, `start_dt`,
   `end_dt`, `fx_high`, `fx_low`, `bi`) — `CZSC.to_echarts()` in the installed `czsc` package
   (`C:\Python314\Lib\site-packages\czsc\analyze.py` around line 314-340, and
   `czsc\utils\echarts_plot.py` around line 63-110) is the authoritative reference for exact field names and
   the fx/bi construction pattern; read both before writing `build_symbol_chart_payload`, don't reverse the
   shape from the docstring alone.
4. **`get_combined_trades()` returns pairs sorted by `open_dt` across all sub-strategies** already (see
   `positions.py::get_combined_trades`) — the `bs` list for `kline_pro` doesn't need to be independently
   sorted, but note two `bs` rows (open + close) come from one pair, so build the `bs` list explicitly (not
   by re-flattening `trades_table`, to avoid drift if `trades_table`'s shape changes later for the table).
5. **Backward compatibility is load-bearing**: this repo's `AGENTS.md`/`.synccheck.yml` gate on unit-test
   *counts* elsewhere, and other diagnostics scripts call `generate_report()` and inspect its dict keys
   directly (e.g. `backtest_matrix_report.py`). Adding `report["html_report_path"]" only when the toggle is
   on, and never touching any existing key, is not optional polish — it's required to avoid silently
   breaking those consumers` return-dict assumptions.
6. **Where to actually run the Manual Verification backtest**: reuse an existing small/fast test fixture or
   README-documented quick-backtest command already used elsewhere in this series' Manual Verification
   sections (e.g. `run_next_work.ps1`'s own preflight compiles `chan_strategy`, but does not run a real
   backtest) — check `README.md`'s "Quick Start"/backtest invocation section for the fastest legitimate
   real-data command rather than inventing a new one.

## Decision Log

- 2026-07-27 (claude-code, design) - Confirmed with the user via three clarifying questions before writing
  this design (would otherwise have guessed wrong on scope): (1) 线段/XD is not implemented this task —
  neither `chan_strategy/` nor the pinned `czsc==0.9.51` library computes it anywhere, so "draw 线段" had no
  data source; the user chose to leave it as a reserved, empty payload key rather than adding a new
  Chan-theory construction algorithm to what was framed as "a report template" task. (2) Multi-symbol reports
  render as one HTML with tab switching (`pyecharts.charts.Tab()`), not one file per symbol, matching how
  `PortfolioEngine` already runs N symbols per formal run. (3) The report is generated automatically by
  `BacktestEngine`/`PortfolioEngine` at the end of every run (behind an opt-in, default-off config toggle),
  not a standalone diagnostics script the user has to remember to invoke.
- 2026-07-27 (claude-code, design) - Chose to reuse `czsc.utils.echarts_plot.kline_pro` (already installed,
  already implements K-line + fx + bi + xd-hook + buy/sell markers + MACD/MA as an interactive HTML chart)
  over writing a from-scratch charting layer, and to add only a custom 中枢 markArea overlay on top of it via
  `.overlap()`, since `kline_pro` has no zhongshu parameter. Rejected building the whole chart in raw
  pyecharts primitives — `kline_pro`/`CZSC.to_echarts()` already encode a working, tested bi/fx rendering
  convention this project should stay consistent with rather than reinvent.
- 2026-07-27 (claude-code, design) - Chose a plain HTML `<table>` for the 成交订单清单 over a second
  charting-library table widget (e.g. pyecharts' own `Table` component) — a plain table keeps the report
  self-contained/portable and is trivially assertable in unit tests via substring checks, at the cost of
  losing pyecharts-native sort/filter interactivity, which was not a stated requirement.
- 2026-07-27 (claude-code, design) - Made `html_report_enabled` default `False` specifically so this task
  cannot change behavior or output for any existing caller/test by default — the user asked for a reusable
  template usable "every time," not for every existing backtest invocation to suddenly start writing HTML
  files it didn't ask for. Opt-in is the safer default; the acceptance criteria treat unintended report-dict
  drift on the default path as a hard failure, not a nice-to-have.

## 交接历史

| 日期 | 从 → 到 | 阶段变化 | 摘要 |
|------|---------|----------|------|
| 2026-07-27 | 人 → claude-code | → design | A105 启动：可复用的 HTML 可视化回测报告模板（笔/中枢/买卖点/成交清单），用户澄清线段不做、多标签一份 HTML、集成进引擎自动生成 |
