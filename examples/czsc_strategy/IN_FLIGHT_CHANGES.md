# In-Flight Changes Manifest

<!-- RESEARCH-ONLY / NOT PROMOTION EVIDENCE -->

This file tracks local in-flight work that is intentionally not yet treated as
promoted evidence. It exists because the SimNow observation workflow currently
has a large dirty worktree surface under `diagnostics/` and `tests/unit/`; this
state must be explicit until the changes are either reviewed and committed or
archived with `commit or stash` discipline.

## Scope

- `diagnostics/`: SimNow read-only observation automation, risk-halt review and
  decision records, daily brief/run summary generation, replay readiness, kline
  staging, and promotion/ledger summaries.
- `tests/unit/`: regression coverage for the SimNow automation workflow and the
  local strategy governance fixes.
- `chan_strategy/` and `README.md`: research/reporting disclosure changes for
  review findings; they are not promotion evidence.

## Current Promotion Blockers

- Manual `risk-halt decision` remains required before any further formal live
  capture is allowed.
- The forward-observation gate still requires `20 valid` SimNow observation
  days after the configured observation start date.
- Historical backtest windows remain contaminated research evidence and must not
  be described as proof of live effectiveness.

## Handling Rules

- Do not run SimNow `-LiveCapture` from this manifest; use
  `diagnostics/NEXT_WORK.md` and `diagnostics/ACCEPTANCE.md`.
- Do not include private broker settings, credentials, personal trading
  identifiers, or generated local SimNow artifacts in this manifest.
- Before broad promotion or handoff, review this dirty worktree surface and
  either commit the coherent patch set or stash/archive unrelated local work.
