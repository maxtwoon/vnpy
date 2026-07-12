---
task: A51 - Limit-Up/Down/Halt Fill-Constraint Tagging (Gated)
version: 4.4.0
stage: done
owner: codex
updated: 2026-07-13
deliverables:
  - HANDOFF.md
  - docs/design/a49-audit-remediation-roadmap.md
blockers: []
last_transition_kind: next
last_transition_actor: codex
last_transition_from_stage: review
last_transition_to_stage: done
last_transition_from_owner: codex
last_transition_to_owner: codex
---

## Background

Third task of the 2026-07-12 audit remediation roadmap
(`docs/design/a49-audit-remediation-roadmap.md` §"A51"), started after A50 (limit-up/down/halt
exposure diagnostic) reached `done`. Per the design's own diagnostic-first discipline, this task's
exact scope was left unfinalized in the original draft, to be determined using A50's real
evidence rather than assumption. **That evidence is now in:**
`diagnostics/limit_halt_exposure_report_2026-07-13.md` measured only **2 total trades** across all
5 default symbols on the post-2026-04-24 window (AP888: 2 trades, 0 at limit; RB888/A888:
`交易周期数据不足` — insufficient bars to even run a baseline replay; SC888/ZN888: 0 trades in the
window). This sample is far too thin to justify actual fill-blocking enforcement, or to calibrate
any enforcement threshold responsibly — doing so now would effectively be tuning risk-control
behavior on 2 data points, which the roadmap's own guardrails already forbid in spirit
("no threshold tuning via backtest/capture-data selection").

**Scope decision (this promotion, informed by A50's evidence):** ship the **lowest-risk option**
from the original design's two alternatives — statistics-only tagging (per-fill limit-band flag
in the report/trade record), NOT fill-blocking/repricing enforcement. This is not a permanent
decision to never enforce; it is the evidence-appropriate choice given how little data currently
exists to validate a blocking rule against. A future task may revisit enforcement once the
post-2026-04-24 window has accumulated enough trade volume for the diagnostic to actually measure
something.

Full contract: `docs/design/a49-audit-remediation-roadmap.md` §"A51 — Limit-Up/Down/Halt
Fill-Constraint Enforcement (Gated)" (originally titled "enforcement" — this task narrows that to
"tagging" per the evidence above; the design doc's own placeholder Semantics section explicitly
anticipated this could be the outcome: "at minimum, tag every fill... if A50's measured exposure
is material... additionally suppress/reprice fills"). A50's exposure is not material (0 of 2
measured trades were at-limit), so only the tagging half applies this round.

## Goal

Add `limit_halt_model` config gate (`"off"` default, current behavior, byte-identical |
`"aware"`). Under `"aware"`, every `pairs` entry (from `Position`, surfaced by
`get_combined_trades()`) gains an `is_entry_at_limit: bool` / `is_exit_at_limit: bool` field pair,
computed the same way A50's diagnostic already computes it (reuse that logic — do not
reimplement), using the same cited exchange limit percentages A50 already sourced. This is a
**tagging-only** change: it must not alter which trades open/close, must not alter any fill price,
and must not alter `Position.pairs`' existing numeric fields (`pnl_pct`, `open_price`,
`close_price`, etc.) in any way — only adds the two new boolean fields.

## Acceptance Criteria

- [x] `limit_halt_model="off"` (default) → equity curve and every `Position.pairs` entry
      byte-identical to current (full-`BacktestEngine` equivalence test with a git-tracked golden
      snapshot, per the A44-A50 house pattern — do not ship with only a signal-filter unit check).
- [x] `limit_halt_model="aware"` → every `pairs` entry gains `is_entry_at_limit`/
      `is_exit_at_limit` boolean fields; all other existing `pairs` fields are numerically
      identical to what `"off"` would have produced for the same trade (unit-tested: run the same
      fixture under both modes, assert every field except the two new ones matches exactly).
- [x] The limit-band computation reuses A50's existing cited percentages
      (`diagnostics/limit_halt_exposure_report.py`'s `SYMBOL_LIMIT_CONFIG` or an equivalent shared
      module — do not duplicate/re-cite the percentages a second time; import or extract a shared
      source of truth).
- [x] A fixture with a known at-limit entry bar and a known not-at-limit entry bar both correctly
      tag `is_entry_at_limit` (unit-tested, both directions).
- [x] No fill is blocked, repriced, or delayed under `"aware"` — verify via a test asserting
      trade count and every trade's `open_dt`/`close_dt`/`open_price`/`close_price` are identical
      between `"off"` and `"aware"` on the same fixture (only the two new tag fields differ).
- [x] `diagnostics/limit_halt_exposure_report.py` (from A50) is updated to note, in its Methodology
      section, that `limit_halt_model="aware"` now exists as a per-trade tagging option (a
      one-line pointer, not a rewrite) — regenerate the report to confirm it still runs cleanly.
- [x] No threshold tuning; no pre-2026-04-24 data used for any parameter choice; no SimNow
      order/cancel/send path changed; no `GOAL PASSED`; does not touch position sizing (P3/A40)
      or exit-model logic (P8a/A47) beyond adding the two read-only tag fields to the pairs
      dict.
- [x] `python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"` passes.
- [x] `python tools/sync_check.py` and `python tools/sync_check.py --root examples/czsc_strategy`
      pass.
- [x] `run_next_work.ps1 -Preflight` (from `examples/czsc_strategy/`) passes — this script
      genuinely exists at `diagnostics/run_next_work.ps1`; verify the path carefully before
      claiming otherwise (A44's dev round falsely claimed it was absent).

## Manual verification (symlink-privilege sandbox limitation)

Run natively (outside the codex sandbox) by claude-code 2026-07-13, in response to codex's
review-round finding that its own sandboxed run hit the documented `tmp_path`/
`PermissionError [WinError 5]` symlink-privilege limitation (see the NOTE above the review
command in `.synccheck.yml`):

- `python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"` -> **542 passed, 4
  deselected**, no WinError 5.
- `python -m pytest examples/czsc_strategy/tests/unit/test_limit_halt_aware.py
  examples/czsc_strategy/tests/unit/test_limit_halt_off_equivalence.py
  examples/czsc_strategy/tests/unit/test_limit_halt_exposure_report.py -q -m "not realdb"` ->
  **16 passed**, no WinError 5.
- `run_next_work.ps1 -Preflight` -> **155 passed** (SimNow workflow unit tests), preflight
  completed cleanly, no WinError 5.
- `python tools/sync_check.py` -> PASS (root). `python tools/sync_check.py --root
  examples/czsc_strategy` -> PASS (child).

Reviewer (codex, sandboxed) may trust these counts for the two sandbox-blocked acceptance items
instead of re-running them; everything else should still be verified normally. codex's own review
found no implementation defect: both sync_check gates passed and the A51-specific tests passed
under an alternate writable basetemp (6 passed) in its sandboxed run.

## Notes for the Next Agent

(dev = kimi-code must read this before writing code)

### Review Reject Notes - 2026-07-13

1. Missing required sandbox-exception evidence for the two gated acceptance commands. In this review
   environment, both `python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"` and
   `powershell -ExecutionPolicy Bypass -File .\diagnostics\run_next_work.ps1 -Preflight` fail with
   the documented Windows pytest temp/symlink `PermissionError [WinError 5]` signature while scanning
   `C:\Users\Admin\AppData\Local\Temp\pytest-of-Admin`. Per `.synccheck.yml`, review may rely on a
   "Manual verification (symlink-privilege sandbox limitation)" block in the current task file for
   these two items, but no such block is present in `HANDOFF.md` or nearby task-state files. Record
   the unsandboxed/manual pass-fail counts for the unit suite and preflight command, or otherwise
   provide verifiable evidence for those two acceptance items, then hand off to review again.

Evidence already checked in this review: root `python tools/sync_check.py` passed; child
`python tools/sync_check.py --root examples/czsc_strategy` passed; A51-specific tests
`test_limit_halt_aware.py` and `test_limit_halt_off_equivalence.py` passed when pytest was pointed at
a writable alternate basetemp (`6 passed`); the committed diff is tagging-only and reuses the shared
`chan_strategy.limit_config.SYMBOL_LIMIT_CONFIG`.

1. **Entry point:** `docs/design/a49-audit-remediation-roadmap.md` §"A51" for the original
   two-option design shape; this HANDOFF's Background section explains why only the tagging
   option is in scope this round (A50's evidence was too thin to justify enforcement).
2. **Scope:** `chan_strategy/positions.py` (add the two tag fields to `pairs` entries at close
   time — in `_close_long`/`_close_short`/`_scale_out`, wherever a `pairs` dict is appended),
   `chan_strategy/config.py` (`limit_halt_model` key). Reuse A50's `SYMBOL_LIMIT_CONFIG` (or
   extract it into a small shared module both A50's diagnostic and this task's tagging logic can
   import — dev's choice on exact factoring, but do not copy-paste the cited percentages a second
   time).
3. **Tagging only — no fill-path changes.** Do not touch `_stop_triggered`/`_stop_fill`/the open
   dispatch in `ChanTimingStrategy.update`/`BacktestEngine`'s `execution_price=bar.open` fill
   timing. The only new code is: (a) a helper that checks whether a given fill price/bar is
   at-or-beyond a symbol's limit band (reusing A50's band-computation math), and (b) two new keys
   written into each `pairs` dict when `limit_halt_model="aware"`.
4. **`"off"` must remain the exact default** — this is a new opt-in tag, not a behavior change;
   the full-`BacktestEngine` equivalence test is mandatory from the first dev round (learn from
   A44's review reject — do not ship without it).
5. **Guardrails (reject-on-violation):** no threshold tuning via backtest/capture-data selection;
   no pre-2026-04-24 data for any parameter choice; no SimNow order/cancel/send paths touched; no
   `GOAL PASSED`; any fill-blocking/repricing logic is OUT OF SCOPE this round — if you find
   yourself writing code that changes whether/when/at-what-price a trade executes, stop, that
   belongs to a future task once more evidence exists.
6. **Before claiming any script "doesn't exist," verify the path carefully** —
   `run_next_work.ps1` lives at `examples/czsc_strategy/diagnostics/run_next_work.ps1`.
7. Finish with the acceptance commands, then
   `python tools/handoff.py next --actor kimi-code --summary "A51 limit-halt fill tagging implemented"`.
   Transactional gate — fix and retry if it blocks; no `--no-gate`.

## Decision Log

- 2026-07-13 - A51 promoted from `docs/design/a49-audit-remediation-roadmap.md`'s draft to an
  active HANDOFF task, started immediately after A50 reached `done`. Scope narrowed from the
  original design's two-option placeholder ("tag-only" vs. "tag + block/reprice") to tag-only
  ONLY, because A50's real evidence (2 total trades measured, 0 at-limit) is too thin to
  responsibly scope or calibrate any blocking/repricing rule — doing so now would be tuning risk
  logic on 2 data points, contrary to the roadmap's own no-tuning-on-thin-evidence discipline.
  Blocking/repricing enforcement is deferred to a future task once the post-2026-04-24 window
  accumulates enough trades for A50's diagnostic to measure something material.
- 2026-07-13 - Confirmed the tagging logic must reuse A50's already-cited `SYMBOL_LIMIT_CONFIG`
  percentages rather than re-deriving or re-citing them, per single-source-of-truth discipline.

## 交接历史

| 日期 | 从 → 到 | 阶段变化 | 摘要 |
|------|---------|----------|------|
| 2026-07-13 | codex → claude-code | done → design | A51 promoted from the audit remediation roadmap draft after A50 reached done; scope narrowed to tagging-only per A50's thin evidence |
| 2026-07-13 | claude-code → kimi-code | design → dev | A51 (limit/halt fill tagging) started |
| 2026-07-13 | kimi-code → codex | dev → review | A51 limit-halt fill tagging implemented |
| 2026-07-13 | codex → kimi-code | review → dev | 打回: Missing manual verification evidence for sandbox-blocked unit/preflight gates |
| 2026-07-13 | kimi-code → codex | dev → review | A51 limit-halt fill tagging implemented |
| 2026-07-13 | codex → codex | review → done | A51 review accepted: tagging-only implementation verified; sync gates passed; sandbox-blocked unit/preflight gates covered by recorded manual verification |
