---
task: A104 - Legacy A-share script hygiene (hardcoded token, stale sync gate, non-compliance disclosure)
version: 4.4.0
stage: done
owner: codex
updated: 2026-07-22
deliverables:
  - HANDOFF.md
  - examples/czsc_strategy/debug_pos.py
  - examples/czsc_strategy/tools/sync_check.py
  - examples/czsc_strategy/run_stock_backtest.py
  - examples/czsc_strategy/run_akshare_backtest.py
  - examples/czsc_strategy/run_baostock_backtest.py
  - examples/czsc_strategy/czsc_adapter.py
  - examples/czsc_strategy/czsc_multi_timeframe_strategy.py
  - examples/czsc_strategy/VERSION
  - examples/czsc_strategy/CHANGELOG.md
blockers: []
last_transition_kind: next
last_transition_actor: codex
last_transition_from_stage: review
last_transition_to_stage: done
last_transition_from_owner: codex
last_transition_to_owner: codex
---

## Background

A user-run, read-only, 4-subagent whole-project audit (2026-07-22, broader scope than this series' usual
single-finding re-audits — covered core `vnpy/`, `vnpy.alpha`, and `examples/czsc_strategy`) surfaced 14
findings. The user explicitly chose to sequence **examples/czsc_strategy-scoped findings first**, deferring
core `vnpy/` engine and `vnpy.alpha` findings to a separate future round, and confirmed this task should
follow the same design(claude-code) → dev(kimi-code) → review(codex) pipeline this series already uses.

This task bundles the four examples-scoped findings from that audit that are genuinely independent,
mechanical, and low-risk (no production risk-control logic touched):

1. **Hardcoded Tushare token committed to git history** — `debug_pos.py:9` calls
   `ts.set_token('da1f00839c22e497ddd81a46973751bc84315ba33d96472fd10547ca')` with the literal token in
   source. Confirmed via `git log -p --all -- examples/czsc_strategy/debug_pos.py` that this string is
   present in at least one historical commit (`adac8808`), not just the current working tree — i.e. this
   token must be treated as already compromised if this repo has ever been pushed to a remote. **The user
   has been told separately, outside this task's scope, to revoke/rotate the token on the Tushare account
   side** — that action is external to this repo and not part of this task's acceptance criteria. This
   task's job is only to stop the token from being hardcoded in source going forward (read from an env var
   instead), matching this repo's existing pattern (`.env`/`dotenv_boot` is not used in this subproject, but
   `os.environ` reads are standard elsewhere — see Plan below for the specific approach chosen).
2. **`examples/czsc_strategy/tools/sync_check.py` is a stale, duplicated standalone copy that bypasses
   newer gates** — confirmed via diff: the root repo's own `tools/sync_check.py` is now a thin 15-line
   wrapper that `runpy.run_path()`s the shared engine at `tools/sync_guardian/sync_check.py` (910 lines,
   includes `deliverables_policy`/`require_new_evidence_on_dev_to_review` and other gates added after this
   series' A54/A60-era hardening). The local copy under `examples/czsc_strategy/tools/sync_check.py` is a
   314-line standalone duplicate — an old fork that never received those later gate additions. `AGENTS.md:6`
   directs contributors to run this local (stale) copy. Note: `examples/czsc_strategy/.synccheck.yml`
   states this subproject intentionally keeps its own **governance config** independent of upstream vnpy
   (`"上游 vnpy 仓库不纳入治理范围"`) — that isolation is about the *config* (what versions/docs must
   match), not the *engine code*. Root's own `tools/sync_check.py` already proves the "thin wrapper
   delegating to the shared engine, but still operating on the local `.synccheck.yml`/`--root`" pattern is
   safe and preserves that config independence — this task applies the exact same pattern locally.
3. **Legacy A-share scripts remain runnable with no A-share compliance modeling, and no warning says so at
   the point of execution** — `README.md:17` already discloses, at the README level, that the actively
   maintained implementation is `chan_strategy/` (futures CTA) and that the old A-share prototype
   (`czsc_adapter.py` / `czsc_multi_timeframe_strategy.py` / `run_baostock_backtest.py`) is "no longer wired
   into the current backtest/test paths". However, that disclosure does not extend to `run_stock_backtest.py`
   or `run_akshare_backtest.py` (both still A-share-oriented, both absent from that README sentence), and
   none of the five legacy scripts carry an in-file warning — so a user who runs one directly (they are all
   plain executable scripts, `git status`/`git log` show all five are still tracked and unmodified for a long
   time, not archived) gets output with no visible caveat that T+1, 涨跌停/停牌 halts, sell-side stamp duty,
   and the no-short constraint are not modeled, and fills are immediate/unconstrained.
4. **`run_stock_backtest.py:47` selects its stock pool using data as of the backtest's *end* date** — this
   is a concrete look-ahead/survivorship-bias mechanism (a stock must have existed/qualified through the
   end of the window to be selected into a backtest that starts earlier), not just a general disclosure gap.

## Plan (what this task does)

All four items are **disclosure and hygiene fixes** — no risk-control, signal, or backtest-logic behavior
changes, and nothing in `chan_strategy/` (the actively-maintained, actually-tested implementation) is
touched.

1. **Token → env var** (`debug_pos.py`): replace the hardcoded literal with
   `ts.set_token(os.environ["TUSHARE_TOKEN"])`, raising a clear `RuntimeError` with a descriptive message
   if the env var is unset (fail-closed — do not silently fall back to any default/empty token). Add one
   line to the file's module docstring noting the env var requirement.
2. **`tools/sync_check.py` → thin wrapper**: replace the 314-line standalone copy with a thin wrapper that
   mirrors root's own `tools/sync_check.py` (`runpy.run_path()` against
   `../../tools/sync_guardian/sync_check.py`, i.e. the root repo's shared engine, two directories up from
   `examples/czsc_strategy/tools/`), so this subproject's gate automatically inherits current gates
   (`deliverables_policy`, etc.) instead of running a permanently-frozen fork. The subproject's own
   `.synccheck.yml`/`--root examples/czsc_strategy` config is untouched — only the *engine* is
   de-duplicated, not the *governance rules*. Verify after the swap that
   `python tools/sync_check.py` (run from `examples/czsc_strategy/`) still passes against the local config.
3. **Warning banner on legacy A-share scripts**: add an explicit, prominent comment block at the top of all
   five legacy scripts (`debug_pos.py`, `run_stock_backtest.py`, `run_akshare_backtest.py`,
   `run_baostock_backtest.py`, `czsc_adapter.py`, `czsc_multi_timeframe_strategy.py` — six files; the
   Background section above undercounted by one, `debug_pos.py` is both item 1 and item 3) stating plainly:
   this is a legacy/unmaintained A-share prototype, not the actively-tested strategy (`chan_strategy/` is);
   it does not model T+1, 涨跌停/停牌 halts, sell-side stamp duty, or the no-short constraint; fills are
   immediate/unconstrained; its output must not be used as evidence of strategy validity. Match the tone
   and placement of this repo's existing `RESEARCH-ONLY / NOT PROMOTION EVIDENCE` banner convention
   (`diagnostics_banner_check` in `.synccheck.yml`) without touching that machinery itself (these six files
   are outside the `diagnostics/` dir the automated banner gate scans, so this is a manually-added,
   consistently-worded comment block, not a new automated gate).
4. **`run_stock_backtest.py:47` bias disclosure**: fold into the same warning banner added in item 3 for
   this specific file — explicitly name the end-date stock-pool-selection survivorship/look-ahead mechanism
   as a known bias, rather than rewriting the pool-selection logic itself. Rationale: this script is being
   marked legacy/unmaintained in the same commit (item 3); investing in fixing point-in-time universe
   selection for a script the repo already doesn't wire into its actively-tested path is effort better spent
   once/if this script is ever promoted back to maintained status. Disclosure now, not a silent rewrite that
   could itself introduce new untested behavior into an unmaintained path.

## Out of scope (deliberately not done in this task)

- Everything the user deferred to "core vnpy/ first later": event-thread exception isolation
  (`vnpy/event/engine.py`), order-freeze auto-update (`vnpy/trader/engine.py`), all `vnpy.alpha` findings
  (fillable-bar backtesting bug, full-sample fit leakage, negative-window lookahead in the expression
  engine), and CI-workflow changes (`.github/workflows/pythonapp.yml` is repo-root scope, not
  `examples/czsc_strategy`).
- Actually fixing `run_stock_backtest.py`'s point-in-time universe selection (disclosed, not fixed — see
  Plan item 4 rationale).
- Any change to `chan_strategy/` itself, or to any file under `diagnostics/` (that directory is a separate,
  currently-active SimNow workstream with its own uncommitted changes — **do not touch**
  `diagnostics/WORK_LOG.md`, `diagnostics/simnow_20d_promotion_decision.md`,
  `diagnostics/simnow_replay_readiness.py`, or `tests/unit/test_simnow_replay_readiness.py`, all of which
  are currently modified in the working tree by that unrelated workstream).
- Root `vnpy/__init__.py::__version__` / root `HANDOFF.md`'s own `version:` field — this task only bumps the
  subproject's `examples/czsc_strategy/VERSION`/`CHANGELOG.md`, matching how prior A-series tasks scoped to
  `examples/czsc_strategy` have always version-bumped their own subproject VERSION file.  <!-- synccheck:ignore -->

## Acceptance Criteria

- [ ] `debug_pos.py` no longer contains the literal token string anywhere; reads `TUSHARE_TOKEN` from
      `os.environ`, raises a clear `RuntimeError` (not `KeyError`) with an actionable message if unset.
- [ ] `examples/czsc_strategy/tools/sync_check.py` is a thin wrapper (mirrors root's own file's structure
      and line count order-of-magnitude) delegating to `tools/sync_guardian/sync_check.py` two directories
      up; `python tools/sync_check.py` run from `examples/czsc_strategy/` still exits 0 against the local
      `.synccheck.yml`.
- [ ] All six legacy A-share scripts listed in Plan item 3 carry the warning banner at the top of the file,
      with consistent wording across all six (not six independently-worded ad-hoc comments).
- [ ] `run_stock_backtest.py`'s banner additionally names the specific end-date stock-pool-selection bias
      from Plan item 4.
- [ ] No behavior change to any of the six scripts' actual logic — this is comment/import-source-only for
      `debug_pos.py`'s token line, wrapper-only for `sync_check.py`, and comment-only for the other four.
- [ ] `python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"` — count should be UNCHANGED
      unless a new smoke test for `sync_check.py`'s wrapper behavior is added (dev's call; if added, note
      the new count explicitly, don't just report a bare "N passed" without saying it changed).
- [ ] `-m realdb` equivalence gate still passes unchanged (none of this task's files are
      `backtest_engine.py`/`positions.py`/`signals.py`, but verify per `AGENTS.md` rule rather than assume).
- [ ] `python tools/sync_check.py` (root) and `python tools/sync_check.py --root examples/czsc_strategy`
      (subproject, now via the new thin wrapper) both pass.
- [ ] `run_next_work.ps1 -Preflight` (from `examples/czsc_strategy/diagnostics/`) passes.
- [ ] `ruff check` clean on touched files (before/after comparison, per this series' established practice —
      this repo's ruff baseline is dirty by design, so compare touched-file counts, not whole-repo counts).
- [ ] `examples/czsc_strategy/VERSION`/`CHANGELOG.md` bumped in the same commit; CHANGELOG entry names all
      four findings plainly.
- [ ] Include a literal `## Manual Verification` heading with natively-run command output.
- [ ] Scope check before handoff: `git status --short` shows only this task's files staged — the four
      concurrent SimNow-workstream files named in "Out of scope" above must remain untouched/unstaged.
- [ ] Remember the `synccheck:ignore` marker for any version-like string in this task's own HANDOFF notes.

## Notes for the Next Agent

(review = codex must read this before starting; dev stage completed by kimi-code 2026-07-22)

1. **All four plan items are implemented**; verify each Acceptance Criterion above against the diff.
   Two deliberate deviations from the literal design text, both recorded in the Decision Log:
   (a) the design's note said repo root from `examples/czsc_strategy/tools/sync_check.py` is
   `parents[2]` — that is off by one (tools → czsc_strategy → examples → root); the wrapper correctly
   uses `parents[3]`, verified by actually running it from the subproject dir (exit 0).
   (b) the design scoped the token fix to `debug_pos.py` only, but grep showed the SAME literal token
   also hardcoded in `run_stock_backtest.py:44` (`TUSHARE_TOKEN = "..."`), which the design missed —
   leaving it would have defeated finding 1's stated job ("stop the token from being hardcoded in
   source going forward"). Fixed with the identical fail-closed `os.environ` + `RuntimeError` pattern.
   This is a code change beyond "comment-only" for that file; it changes no backtest/signal logic.
2. **Test count UNCHANGED at 780 passed (not realdb)**, same before/after — note the baseline is 780,
   not the 779 recorded in A103's changelog: the +1 comes from the concurrent SimNow workstream's
   uncommitted `tests/unit/test_simnow_replay_readiness.py`, not from this task. No new smoke test
   for the wrapper was added (dev's call per the acceptance criterion) — the wrapper is verified by
   the acceptance command that runs it directly (Manual Verification item 5).
3. **Banners verified byte-identical** across all six files (only the filename in line 4 differs;
   `run_stock_backtest.py` additionally carries the survivorship/look-ahead disclosure block per
   Plan item 4). Verification snippet and result in Manual Verification item 8.
4. **Scope check done**: `git status --short` before staging showed only this task's files modified
   plus the four pre-existing SimNow-workstream modifications (`diagnostics/WORK_LOG.md`,
   `diagnostics/simnow_20d_promotion_decision.md`, `diagnostics/simnow_replay_readiness.py`,
   `tests/unit/test_simnow_replay_readiness.py`) — those four were NOT staged and remain untouched.
5. **Version bump**: subproject only, 0.2.41 → 0.2.42 <!-- synccheck:ignore -->
   (`VERSION` + `CHANGELOG.md` entry naming all four findings). Root
   `vnpy/__init__.py` / this file's `version:` field untouched, per Out of scope.
6. Commit split follows this series' convention: one dev-work commit ("A104: ..."), then after
   `handoff.py next` a separate "A104: promote dev->review" commit for the transition metadata.

## Manual Verification

All commands run natively on this machine 2026-07-22 by kimi-code (not transcribed from elsewhere).

1. `python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"` (repo root)
   - Baseline BEFORE changes: `780 passed, 4 deselected in 48.54s`
   - AFTER changes: `780 passed, 4 deselected in 50.40s` — count UNCHANGED (no tests added/removed).
2. `python -m pytest examples/czsc_strategy/tests/unit -q -m realdb` (repo root, per AGENTS.md rule —
   verified rather than assumed even though no `backtest_engine.py`/`positions.py`/`signals.py` touched):
   `4 passed, 780 deselected in 79.42s (0:01:19)` — equivalence gate unchanged, passes.
3. `python tools/sync_check.py` (repo root): `[SYNC-CHECK] PASS: 版本与文档一致。` ROOT_EXIT=0
   (version truth 4.4.0; pre-existing WARN about missing `docs/archive/` unchanged).
4. `python tools/sync_check.py --root examples/czsc_strategy` (repo root): PASS, SUB_EXIT=0,
   version truth = 0.2.42 <!-- synccheck:ignore --> from `VERSION::`.
5. `python tools/sync_check.py` run FROM `examples/czsc_strategy/` (the new thin wrapper):
   PASS, EXIT=0 against local `.synccheck.yml` — wrapper resolves the shared engine at
   repo-root `tools/sync_guardian/sync_check.py` via `__file__`-relative `parents[3]`, cwd-independent.
6. `powershell -NoProfile -ExecutionPolicy Bypass -File .\run_next_work.ps1 -Preflight`
   (from `examples/czsc_strategy/diagnostics/`): `206 passed in 31.58s`, exit 0,
   "Preflight complete; live SimNow capture was not requested".
7. ruff touched-file before/after counts (repo ruff baseline is dirty by design; comparing
   touched-file counts per this series' practice):
   `debug_pos.py` 4→4, `run_stock_backtest.py` 22→22, `run_akshare_backtest.py` 15→15,
   `run_baostock_backtest.py` 28→28, `czsc_adapter.py` 7→7, `czsc_multi_timeframe_strategy.py` 10→10,
   `tools/sync_check.py` 20→0 (net improvement; no new errors introduced).
8. Banner consistency check (python, byte-level, normalizing only the filename line and the extra
   bias block): all six files `IDENTICAL`.
9. Token grep across the six scripts: zero hits for the literal `da1f00839c22e497...` string
   (it remains only in this HANDOFF.md's Background section, quoting the finding — already committed
   in git history at design time; rotation is external per the design).

## Review Findings (codex)

- 2026-07-22 (codex, review) - Rejecting: the touched-file ruff acceptance item is not reproducible.
  Running `ruff check examples/czsc_strategy/debug_pos.py examples/czsc_strategy/run_stock_backtest.py
  examples/czsc_strategy/run_akshare_backtest.py examples/czsc_strategy/run_baostock_backtest.py
  examples/czsc_strategy/czsc_adapter.py examples/czsc_strategy/czsc_multi_timeframe_strategy.py
  examples/czsc_strategy/tools/sync_check.py` exits 1 with 86 findings. This includes findings in
  files that the Manual Verification block records as clean or improved-to-zero, e.g.
  `czsc_multi_timeframe_strategy.py` still reports unused imports, blank-line whitespace, and an
  unnecessary f-string. Please either make the touched-file ruff gate pass as written, or update the
  handoff evidence with a reproducible before/after command and exact interpretation if the intended
  criterion is only "no new ruff findings."
- 2026-07-22 (codex, review) - Rejecting: the `-m realdb` equivalence gate could not be accepted from
  this review run. `python -m pytest examples/czsc_strategy/tests/unit -q -m realdb` exits 1 with
  two failures in `test_natural_agg_matches_cached_golden[AP888/RB888]`, both
  `sqlite3.OperationalError: unable to open database file` against
  `D:/BaiduNetdiskDownload/.../kline_data.db`. This looks environment/sandbox-related, but it is not
  one of the two documented substitute-evidence exceptions in `.synccheck.yml` (which only covers the
  unit-test and preflight commands when they fail with the `tmp_path`/WinError 5 signature). Please add
  documented manual evidence for this gate or make the gate reproducible in the review sandbox.
- 2026-07-22 (codex, review) - Informational: the not-realdb unit suite and preflight reruns both hit
  the documented `tmp_path`/WinError 5 sandbox signature, so those two items can use the Manual
  Verification counts already recorded in this file. Root sync check, subproject sync check, and the
  subproject wrapper run all exit 0; token grep over the six scripts has zero hits for the literal token.

## Decision Log

- 2026-07-22 (kimi-code, dev) - Implemented all four plan items. Two deviations from the literal design
  text, both small and recorded here per workflow rules: (a) design note 3's `parents[2]` was off by one —
  repo root from `examples/czsc_strategy/tools/sync_check.py` is `parents[3]`; the wrapper uses
  `parents[3]` and was verified by running it from the subproject dir (PASS, exit 0). (b) The design
  scoped the token fix to `debug_pos.py` only, but the SAME literal token was also hardcoded at
  `run_stock_backtest.py:44` (`TUSHARE_TOKEN = "..."`) — the design audit missed this second occurrence.
  Fixed with the identical fail-closed pattern (`os.environ.get("TUSHARE_TOKEN")` + descriptive
  `RuntimeError`, no default/fallback), since leaving it would defeat finding 1's stated goal. No
  backtest/signal logic changed anywhere; the other four legacy files are banner-comment-only as designed.
- 2026-07-22 (kimi-code, dev) - Test-count note: not-realdb baseline is 780 passed (both before and after
  this task), not the 779 recorded in A103's changelog — the +1 is the concurrent SimNow workstream's
  uncommitted `test_simnow_replay_readiness.py`, unrelated to this task. No new test added for the wrapper
  (acceptance criterion left it to dev's call): the wrapper is exercised directly by acceptance command 5.
- 2026-07-22 (claude-code, design) - User ran a fresh, broader (4-subagent, whole-project) read-only audit
  covering core `vnpy/`, `vnpy.alpha`, and `examples/czsc_strategy` — 14 findings total. User explicitly
  chose "examples/czsc_strategy first" over the audit's own suggested cross-cutting batch order, and
  confirmed the same design/dev/review pipeline this series already uses. This task scopes exactly the four
  examples-scoped findings that are independent, mechanical, and disclosure/hygiene-only; the remaining
  examples-adjacent-but-not-strictly-in-scope items (CI workflow, which is repo-root) and all core
  `vnpy`/`vnpy.alpha` findings are deferred to future tasks per the user's explicit sequencing choice.
- 2026-07-22 (claude-code, design) - Confirmed via `git log -p --all -- examples/czsc_strategy/debug_pos.py`
  that the hardcoded token is present in at least commit `adac8808`, i.e. already in git history, not just
  the working tree. Told the user directly (outside this task) that the token must be treated as
  already-compromised and rotated on the Tushare side; that rotation is external to this repo and not an
  acceptance criterion here. Deliberately did NOT attempt git-history rewriting (`filter-repo`/BFG) as part
  of this task — that's a disruptive, force-push-requiring operation the user has not asked for yet.
- 2026-07-22 (claude-code, design) - Confirmed via `diff` that root's `tools/sync_check.py` (15 lines) is
  already a thin wrapper around `tools/sync_guardian/sync_check.py` (910 lines), and that the local
  `examples/czsc_strategy/tools/sync_check.py` (314 lines) is a standalone duplicate lacking
  `deliverables_policy`/`require_new_evidence_on_dev_to_review` (confirmed via grep — zero matches in the
  local copy, present in the shared engine). Chose "thin wrapper delegating to shared engine, config stays
  local" over "delete the local copy entirely" because `AGENTS.md`/`.synccheck.yml` both actively reference
  running `tools/sync_check.py` from this directory as the subproject's own gate entry point — deleting it
  would break that documented entry point, not just remove duplication.
- 2026-07-22 (claude-code, design) - Read `README.md:15-19`: it already discloses `chan_strategy/` as the
  only actively-tested implementation and names three of the five legacy files as "no longer wired into
  current backtest/test paths" — but `run_stock_backtest.py` and `run_akshare_backtest.py` aren't named
  there, and none of the five (six, counting `debug_pos.py`) carry an in-file warning a user would actually
  see if they ran the script directly rather than reading the README first. Chose in-file banners (visible
  at the point of use) as the fix, additive to the existing README disclosure, not a replacement for it.
- 2026-07-22 (claude-code, design) - Chose disclosure over a logic rewrite for `run_stock_backtest.py`'s
  end-date stock-pool-selection bias (Plan item 4) — this script is being marked legacy/unmaintained in the
  same commit; fixing point-in-time universe selection properly is real, non-trivial work better deferred
  to if/when this script is ever promoted back to maintained status, per this project's established
  "disclose known limitations rather than rush an unvalidated fix" practice (documented precedent in the
  SimNow/ashare-adjacent workstreams' own Decision Logs).
- 2026-07-22 (claude-code, acting as kimi-code per this project's established substitution practice for
  evidence-only re-review, since the review's two blocking findings turned out to be a wording ambiguity
  and a codex-sandbox-specific limitation, not a code defect — no dev work was actually needed) -
  Independently re-verified both of codex's blocking findings:
  1. **Ruff "86 findings" — confirmed NOT a regression.** Created a worktree at the pre-A104 commit
     (`5ccd01ee`) and ran the identical `ruff check` command against the same seven files there: baseline
     is **106 errors**, vs **86 after A104** — a net improvement of 20 (all from replacing the stale
     314-line `sync_check.py` with the 15-line wrapper), zero new findings in any of the other six files.
     This matches kimi-code's own per-file before/after table already recorded in Manual Verification item
     7 above. The acceptance criterion's wording ("ruff check clean on touched files") was ambiguous — my
     own design brief's parenthetical clarified "before/after comparison ... not whole-repo counts" but the
     bare phrase "clean" reads as "zero findings" out of context, which is how codex's review interpreted
     it. This is a design-wording ambiguity, not a dev defect; no code or comment changes were needed to
     resolve it, only this clarification.
  2. **realdb gate `sqlite3.OperationalError` — confirmed codex-sandbox-specific, not reproducible outside
     it.** Re-ran `python -m pytest examples/czsc_strategy/tests/unit -q -m realdb` natively (same
     environment kimi-code used): **4 passed, 780 deselected**, zero failures — matches kimi-code's
     original Manual Verification exactly. Codex's review environment failed on
     `test_natural_agg_matches_cached_golden[AP888/RB888]` trying to open
     `D:/BaiduNetdiskDownload/.../kline_data.db`, a real, host-machine-specific cached-data path outside the
     `--add-dir` scopes granted to that review command (`.vntrader`, Temp) — same family of issue as this
     project's documented `tmp_path`/WinError 5 codex-sandbox filesystem-access limitation, just a
     different specific path/signature not yet covered by the existing narrow carve-out wording in
     `.synccheck.yml`. Not caused by any A104 change — none of A104's files touch backtest data loading,
     `kline_data.db`, or that test's fixtures.
  Recommend `.synccheck.yml`'s review-command carve-out wording be broadened in a future task to cover
  "any local-data-path `OperationalError`/`PermissionError` outside the granted `--add-dir` scopes" rather
  than only the specific `tmp_path`/WinError 5 signature — out of scope to edit here mid-review.

## 交接历史

| 日期 | 从 → 到 | 阶段变化 | 摘要 |
|------|---------|----------|------|
| 2026-07-22 | codex → claude-code | done → design | A104 (legacy A-share script hygiene: hardcoded token, stale sync gate, non-compliance disclosure) scoped from user's fresh whole-project audit; user chose examples-first sequencing |
| 2026-07-22 | claude-code → kimi-code | design → dev | A104 scoped: token->env var, sync_check.py thin wrapper, legacy A-share warning banners incl. run_stock_backtest.py survivorship-bias disclosure |
| 2026-07-22 | kimi-code → codex | dev → review | A104 legacy A-share script hygiene completed |
| 2026-07-22 | codex → kimi-code | review → dev | 打回: A104 review blocked: touched-file ruff gate nonzero and realdb gate not independently reproducible |
| 2026-07-22 | kimi-code → codex | dev → review | Both review-blocking findings independently re-verified as non-defects: ruff 106->86 (net improvement, matches recorded before/after table, wording ambiguity not a regression); realdb gate 4 passed natively, codex-sandbox-specific OperationalError on an out-of-scope local data path, same family as documented tmp_path/WinError5 limitation |
| 2026-07-22 | codex → codex | review → done | A104 review passed on second pass: sync gates pass freshly; token/wrapper/banner/version scope verified; unit/preflight sandbox failures match documented tmp_path WinError 5 limitation and manual native counts are recorded; realdb and ruff prior blocks resolved by documented second-pass evidence. |
