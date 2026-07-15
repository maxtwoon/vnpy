---
task: A67 - Limit/Halt Unexecutable-Fill Backtest Mode
version: 4.4.0
stage: done
owner: codex
updated: 2026-07-15
deliverables:
  - HANDOFF.md
  - docs/design/a65-third-party-audit-remediation-roadmap.md
blockers: []
last_transition_kind: next
last_transition_actor: codex
last_transition_from_stage: review
last_transition_to_stage: done
last_transition_from_owner: codex
last_transition_to_owner: codex
---

## Background

Third task of the 2026-07-14 third-party-audit remediation roadmap
(`docs/design/a65-third-party-audit-remediation-roadmap.md` §"A67"), promoted immediately after
A66 reached `done` (codex accepted on the first review round). **This is the highest-risk task in
the A65-A69 roadmap** — it is the only one introducing genuinely new backtest behavior, unlike
A65/A66's fixes/docs.

**Re-verified 2026-07-15 by claude-code (due-diligence read of the full fill-decision path before
writing this HANDOFF):**

`limit_halt_model="aware"` (`config.py:130`) only tags fills — `Position.pairs` entries get
`is_entry_at_limit`/`is_exit_at_limit` booleans (`positions.py:923-924, 1026-1027`), but these
NEVER gate whether `_open_long`/`_open_short`/`_close_long`/`_close_short` actually execute. The
directional flags (`entry_at_limit`/`exit_at_limit`, resolved per-side by `_resolve_limit_flag`,
`positions.py:667` for exits, `positions.py:953/1067` for entries) are already computed and passed
into `Position.update` (`positions.py:638-731`) — they are simply stored for later tagging, never
checked before a fill happens.

**Fill decision points confirmed by direct read of `Position.update` (`positions.py:671-731`):**
- **Entries:** `Operate.LO`/`Operate.SO` at lines 671/675 — a single, easy-to-gate check point.
- **Exits — SEVEN separate call sites**, not one: signal-close (line 673/677), `exit_model="legacy"`
  branch's trailing-stop/fixed-stop/timeout (lines 691-708), and `exit_model="structural_atr"`
  branch's fixed-stop/timeout/ATR-trailing (lines 712-731), plus `_scale_out`'s partial take-profit
  (line 723-726, not gated by this task — partial TP is a profit-side voluntary action, not a
  forced exit; see Boundaries).
- **`_get_operate` re-evaluates every bar from the current `signals_dict`'s classification state**
  (`positions.py:733-760`, `event.is_match(signals_dict)`) — it is NOT a one-shot edge-triggered
  event. This matters: if an entry is skipped on bar N because of a limit touch, and the Chan-
  structure classification (e.g. "一买确认") is still the SAME on bar N+1 (plausible, since
  structure changes don't necessarily happen every bar), `_get_operate` will naturally re-request
  the same open on bar N+1 — a "reject this bar's fill" semantic does NOT necessarily mean
  "permanently lose this trade," though it is an approximation, not a guaranteed retry (the
  classification COULD also change between bars for unrelated reasons).

Full contract: `docs/design/a65-third-party-audit-remediation-roadmap.md` §"A67 — Limit/Halt
Unexecutable-Fill Backtest Mode" (the authoritative design — this HANDOFF summarizes it).

## Goal

Add a new `limit_halt_model="enforce"` value (alongside existing `"off"`/`"aware"`, which MUST
remain byte-identical). Under `"enforce"`, when a fill's directional limit flag indicates an
unexecutable price (using the SAME `_resolve_limit_flag`/`_bar_at_limit` directional logic already
built by A57/A59/A61 — do not re-derive this from scratch), the fill is either rejected (skipped
entirely for that bar — position state unchanged, tagged as `fill_rejected_at_limit`) or deferred
(retried at the next fillable bar). **This task's OWN design step must decide reject vs. defer and
record the decision, with rationale, in the Decision Log BEFORE writing any code** — mirroring the
A56 "decide, then implement" pattern.

**claude-code's own due-diligence lean (evidence for dev to weigh, NOT a pre-made decision):**
reject is simpler, has no cross-bar state-machine complexity, and — per the `_get_operate`
re-evaluation behavior confirmed above — often approximates a natural retry on the next bar without
needing an explicit pending-order mechanism. Defer would more precisely model "the order sits in
the market until it can fill," but introduces meaningfully more complexity (a pending-fill object
that must survive across bars, interact correctly with stop-loss/timeout/signal-close priority, and
be unit-tested for multi-bar-persistence edge cases). If, after weighing this, dev's own design step
still prefers defer, that's an acceptable choice — but it must be justified in the Decision Log, not
defaulted to without comparison.

## Acceptance Criteria

- [x] `limit_halt_model="off"` and `"aware"` remain byte-identical to current behavior (existing
      equivalence/tagging tests untouched, snapshot-verified).
- [x] A recorded design decision (reject vs. defer) with rationale in the Decision Log, BEFORE any
      code is written.
- [x] `limit_halt_model="enforce"` gates BOTH entries (`Operate.LO`/`SO`) and exits — covering all
      seven exit call sites enumerated above (signal-close, legacy trailing/fixed-stop/timeout,
      structural_atr fixed-stop/timeout/ATR-trailing). A shared helper function is strongly
      preferred over duplicating the same gating check at all seven call sites.
- [x] Unit-tested: a fixture bar at the limit band produces a rejected/deferred fill (position state
      correctly unchanged for reject, or correctly retried for defer) — for BOTH an entry and an
      exit case, with NO lookahead (a fixture proving the decision uses only current-and-prior-bar
      information, never a future bar).
- [x] A comparison report (RESEARCH-ONLY banner, reusing `declassify_historical_reports.
      build_banner()`) quantifies how much `"enforce"` changes reported trade counts/PnL relative to
      `"aware"` on the post-2026-04-24 window — reported as honest measurement, not a superiority
      claim.
- [x] No threshold tuning; no pre-2026-04-24 data used for any parameter choice; no SimNow
      order/cancel/send path changed; no `GOAL PASSED`.
- [x] `python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"` passes.
- [x] `python tools/sync_check.py` and `python tools/sync_check.py --root examples/czsc_strategy`
      pass.
- [x] `run_next_work.ps1 -Preflight` (from `examples/czsc_strategy/`) passes.

## Notes for the Next Agent

(review = codex rejected 2026-07-15)

Root sync gate is failing and must be fixed before this handoff can advance:

- `python tools/sync_check.py` fails with:
  `project_version_freshness[examples/czsc_strategy]: commit 4aff7e39 could not read chan_strategy/config.py`
- Reproduction evidence: `git show 4aff7e39:chan_strategy/config.py` fails, while
  `git show 4aff7e39:examples/czsc_strategy/chan_strategy/config.py` succeeds.
- The child gate still passes: `python tools/sync_check.py --root examples/czsc_strategy`.
- Targeted A67 tests pass: `python -m pytest examples/czsc_strategy/tests/unit/test_limit_halt_enforce.py -q -m "not realdb"` => `12 passed`.
- Full unit/preflight reruns in codex still hit the documented sandbox `tmp_path` / `WinError 5`
  limitation, so use the existing Manual Verification counts for those two acceptance items.

Likely fix direction: root `project_version_freshness` path handling needs to read the
project-rooted config from the repo-root path when using `git show`, or the root config needs an
equivalent path convention that keeps `changed` detection and `git show` consistent. After fixing,
rerun `python tools/sync_check.py` plus the child sync gate and targeted A67 test.

(dev = kimi-code must read this before writing code)

1. **Entry point:** `docs/design/a65-third-party-audit-remediation-roadmap.md` §"A67". Third task
   of the A65-A69 roadmap — read the design doc's Background AND re-read A59's `_bar_at_limit`
   directional-touch work in full before starting (`chan_strategy/limit_config.py`).
2. **Scope:** `chan_strategy/positions.py` (`Position.update`'s fill-decision path — all points
   enumerated in Background), `chan_strategy/backtest_engine.py` (if the entry/exit call sites need
   the directional flag threaded differently for `"enforce"` — check whether the existing
   `entry_at_limit`/`exit_at_limit` parameters already carry enough information, or whether the
   exit-side call sites need per-branch flag values that aren't currently computed per-branch), and
   `chan_strategy/config.py` (document the new value). Do not touch `"off"`/`"aware"`'s existing
   code paths at all beyond adding the new conditional branch.
3. **The seven exit call sites are NOT all equally important to gate.** If time/complexity
   pressure forces a scoping choice, prioritize per the audit's own concern: stop-loss/timeout exits
   being blocked by a limit/halt bar is the scenario with real risk-modeling value (a position that
   CANNOT be stopped out during a limit-down day is exactly what the audit flagged as unmodeled
   risk). Signal-close and ATR-trailing are lower priority if a scoping cut is truly necessary — but
   try to cover all seven; do not silently skip any without noting it in the Decision Log.
4. **`_scale_out` (partial take-profit) is explicitly OUT of scope for gating** — it's a voluntary
   profit-taking action, not a forced exit; the audit's concern is about being UNABLE to exit when
   needed, not about optional profit-taking being delayed. Do not gate it unless your own design
   step finds a compelling reason to.
5. **No lookahead, ever** — whatever mechanism is chosen (reject or defer) must only use
   information available at or before the bar being evaluated. If defer is chosen, the deferred
   fill must execute at the NEXT bar's actual price once fillable, never retroactively adjusting the
   original bar.
6. **The comparison report** should reuse `diagnostics/exit_model_report.py`-style structure/
   conventions if applicable (per-trade give-back, cross-model comparison) rather than inventing a
   new report format from scratch — check that file for precedent first.
7. **Guardrails (reject-on-violation):** no threshold tuning via backtest/capture-data selection; no
   pre-2026-04-24 data for any parameter choice; no SimNow order/cancel/send paths touched; no
   `GOAL PASSED`; `"off"`/`"aware"`'s existing equivalence/tagging snapshots must stay byte-identical.
8. **Include a Manual-verification block with natively-run counts, and run `ruff check`
   proactively before finishing.**
9. **If, after scoping this task in earnest, it proves too large for one dev round, say so
   explicitly and propose an A67a/A67b split** (mirroring the P8a/P8b and A69 precedent) rather than
   forcing an oversized or corner-cut implementation into one handoff.
10. Finish with the acceptance commands, then
    `python tools/handoff.py next --actor kimi-code --summary "A67 limit/halt enforce mode implemented"`.
    Transactional gate — fix and retry if it blocks; no `--no-gate`.

## Manual Verification

Natively-run counts (Windows, Python 3.14, repo `D:\repo\vnpy`):

```text
$ python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"
625 passed, 4 deselected in 28.97s

$ python -m pytest examples/czsc_strategy/tests/unit/test_limit_halt_enforce.py -q -m "not realdb"
12 passed in 0.11s

$ python tools/sync_check.py
[SYNC-CHECK] PASS: 版本与文档一致。

$ python tools/sync_check.py --root examples/czsc_strategy
[SYNC-CHECK] PASS: 版本与文档一致。

$ powershell -ExecutionPolicy Bypass -File diagnostics/run_next_work.ps1 -Preflight
==> Preflight complete; live SimNow capture was not requested
189 passed in 16.08s

$ ruff check examples/czsc_strategy/tests/unit/test_limit_halt_enforce.py examples/czsc_strategy/diagnostics/limit_halt_enforce_report.py examples/czsc_strategy/chan_strategy/backtest_engine.py examples/czsc_strategy/chan_strategy/config.py
All checks passed!

$ ruff check examples/czsc_strategy/chan_strategy/positions.py
29 pre-existing typing-annotation lints (no new issues introduced by this change).
```

Comparison report generated:
- `examples/czsc_strategy/diagnostics/limit_halt_enforce_report_2026-07-15.md`
- `examples/czsc_strategy/diagnostics/limit_halt_enforce_report_2026-07-15.json`

On the post-2026-04-24 window the report shows zero rejected fills because no tested symbol
actually hit its daily limit band during the window — this is honest measurement, not a claim of
no effect.

## Round 2 fix (claude-code, 2026-07-15, after codex's round-1 rejection)

codex's round-1 review correctly rejected on a root `sync_check.py` gate failure — but the root
cause was NOT in A67's own strategy-logic code. Investigation found TWO real, independent bugs in
`tools/sync_guardian/sync_check.py`'s A60-introduced `project_version_freshness` gate, both first
triggered by A67 simply being the first post-A60 commit that actually modified `config.py`
(A60 itself never touched `config.py`, so this code path had never actually run against real data):

1. **Windows GBK decode crash, silently swallowed.** `_file_at_commit`'s `subprocess.check_output`
   calls used `text=True` with no explicit encoding, so on Windows they decoded git's UTF-8 output
   using the system locale (GBK/cp936) — any Python file with non-ASCII content (e.g.
   `config.py`'s Chinese comments) raised `UnicodeDecodeError`, caught by a broad `except Exception`
   and silently turned into a false "could not read" gate failure. Fixed by pinning
   `encoding="utf-8", errors="replace"` on all the A60-introduced subprocess calls
   (`_find_gate_since_commit`, `_commits_after`, `_files_changed_in_commit`, `_file_at_commit`,
   `_first_parent`).
2. **`ast.literal_eval` cannot parse arithmetic expressions.** `_config_surface_fingerprint` used
   `ast.literal_eval(node.value)` to parse `STRATEGY_CONFIG`/`BACKTEST_CONFIG`'s dict literal, but
   `config.py` has genuinely always contained non-literal numeric expressions for readability
   (e.g. `"interval_1buy": 3600 * 24`, "one day in seconds") — `literal_eval` rejects any
   expression node, not just unsafe ones. Fixed with a new `_safe_eval_node` helper: a
   literal-eval superset that additionally tolerates numeric `BinOp`/`UnaryOp` (Add/Sub/Mult/Div on
   constants only) while still rejecting anything with potential side effects (calls, names,
   comprehensions).

Both bugs are pre-existing defects in A60's own code, unrelated to A67's strategy logic — A67 was
simply the first commit to exercise this code path against `config.py`'s real content. Added two
regression tests to `tests/test_sync_guardian.py`
(`test_project_version_freshness_handles_non_ascii_config_content`,
`test_project_version_freshness_handles_arithmetic_expressions_in_config`) reproducing both bugs
against a minimal fixture repo, both passing after the fix. Re-verified: `tests/
test_sync_guardian.py` (14 passed), full czsc_strategy unit suite (625 passed, unchanged), A67's
own targeted tests (12 passed), both root and child `sync_check.py` gates now PASS, `ruff check` on
the modified file (clean), and preflight (189 passed).

## Decision Log

- 2026-07-15 - A67 promoted from `docs/design/a65-third-party-audit-remediation-roadmap.md`'s
  draft to an active HANDOFF task, started immediately after A66 reached `done` (codex accepted on
  the first review round). This is the highest-risk task in the A65-A69 roadmap.
- 2026-07-15 - claude-code's due-diligence read confirmed: `limit_halt_model="aware"` genuinely
  never gates any fill (tagging-only, as the config comment states); there are SEVEN distinct exit
  call sites in `Position.update` (not one), spread across the `"legacy"` and `"structural_atr"`
  exit-model branches; `_get_operate` re-evaluates the Chan-structure classification every bar
  (not a one-shot edge-triggered event), meaning a rejected entry fill is NOT necessarily a
  permanently lost trade — this evidence leans toward recommending "reject" over "defer" for
  simplicity, but the final choice and its justification are dev's own design decision to record.
- 2026-07-15 - dev (kimi-code) design decision: implement `limit_halt_model="enforce"` as a
  **reject-this-bar** model, not a cross-bar deferral queue. Rationale: (1) reject keeps `Position`
  fully stateless across bars — no pending-fill object, no priority-interaction risk with stop-loss/
  timeout/signal-close, and no multi-bar persistence edge cases; (2) the audit's primary concern is
  quantifying the impact of unexecutable fills, and a reject model provides a clean, conservative
  lower bound; (3) `_get_operate` already re-evaluates classification every bar, so a skipped entry
  naturally retries on the next bar if the signal persists, approximating much of deferral's value
  without the complexity; (4) exit gating is straightforward: any exit triggered on a limit/halt bar
  is simply skipped for that bar, and because the same stop/timeout/signal condition is re-evaluated
  each bar, the next fillable bar will catch it. Partial take-profit (`_scale_out`) remains out of
  scope per the task boundary. Rejected fills are recorded with `fill_rejected_at_limit=True` on the
  `Position.pairs` entry that eventually closes, preserving an audit trail without changing trade
  counts/prices for non-rejected fills. Deferral was rejected for this round because introducing a
  persistent order object across bars would require new state, new priority rules (stop-loss vs
  pending entry), and substantially broader unit-test coverage; it is explicitly noted as a possible
  follow-up, not this task.

## 交接历史

| 日期 | 从 → 到 | 阶段变化 | 摘要 |
|------|---------|----------|------|
| 2026-07-15 | codex → claude-code | done → dev | A67 (limit/halt enforce mode) promoted from third-party audit remediation roadmap; handoff design->dev |
| 2026-07-15 | kimi-code → codex | dev → review | A67 limit/halt enforce mode implemented |
| 2026-07-15 | codex → kimi-code | review → dev | 打回: root sync_check fails on project_version_freshness config path |
| 2026-07-15 | kimi-code → codex | dev → review | A67 round 2: fixed sync_check.py encoding/arithmetic bugs blocking the gate |
| 2026-07-15 | codex → codex | review → done | A67 review accepted |
