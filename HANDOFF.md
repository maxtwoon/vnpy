---
task: A104 - Legacy A-share script hygiene (hardcoded token, stale sync gate, non-compliance disclosure)
version: 4.4.0
stage: dev
owner: kimi-code
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
last_transition_actor: claude-code
last_transition_from_stage: design
last_transition_to_stage: dev
last_transition_from_owner: claude-code
last_transition_to_owner: kimi-code
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

(dev = kimi-code must read this before starting)

1. **Four independent, low-risk, disclosure/hygiene-only fixes in one task** — none touch
   `chan_strategy/` or any production risk-control/signal/backtest logic.
2. **`debug_pos.py` fix is fail-closed**: do not add a default/fallback token value of any kind (empty
   string, placeholder, etc.) — an unset `TUSHARE_TOKEN` env var must raise, not silently proceed with no
   auth.
3. **The `sync_check.py` wrapper's relative path must resolve correctly from wherever it's invoked** — root's
   own `tools/sync_check.py` computes `ROOT = Path(__file__).resolve().parents[1]` (i.e. it locates the repo
   root via its own file location, not via cwd). Mirror that pattern so the subproject wrapper also locates
   `tools/sync_guardian/` via `__file__`-relative resolution, two levels further up
   (`examples/czsc_strategy/tools/sync_check.py` → repo root is `parents[2]`) — don't assume cwd.
4. **Warning banner wording must be identical (or near-identical, adapted only for filename) across all six
   files** — write it once, apply the same block to each, don't let wording drift file-to-file.
5. **Do not touch the concurrent SimNow-workstream files** — before committing, run `git status --short`
   and confirm only this task's files are staged (see Acceptance Criteria).
6. **Include a literal `## Manual Verification` heading** — required every time; do not omit it.
7. Finish with the acceptance commands, then
   `python tools/handoff.py next --actor kimi-code --summary "A104 legacy A-share script hygiene completed"`.
   Transactional gate — fix and retry if it blocks; no `--no-gate`. If the command itself crashes/times out
   for environment reasons, do not manually hand-edit HANDOFF.md's stage/owner fields to bypass it — leave
   the working tree with your changes uncommitted and note the failure in the Decision Log; claude-code will
   verify and commit properly.

## Decision Log

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

## 交接历史

| 日期 | 从 → 到 | 阶段变化 | 摘要 |
|------|---------|----------|------|
| 2026-07-22 | codex → claude-code | done → design | A104 (legacy A-share script hygiene: hardcoded token, stale sync gate, non-compliance disclosure) scoped from user's fresh whole-project audit; user chose examples-first sequencing |
| 2026-07-22 | claude-code → kimi-code | design → dev | A104 scoped: token->env var, sync_check.py thin wrapper, legacy A-share warning banners incl. run_stock_backtest.py survivorship-bias disclosure |
