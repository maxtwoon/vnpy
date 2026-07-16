# SimNow Formal Sessions Design

## Goal

Replace the hard-coded `AP888` day-session gate in the SimNow wrapper with a config-driven per-symbol formal-session policy.

## Current Problem

`examples/czsc_strategy/diagnostics/run_next_work.ps1` currently rejects every formal night-session run whenever `AP888.enabled=true`. This is stricter than the actual requirement: only symbols that are explicitly marked as day-only should block a formal night-session observation.

## Design

- Add a `formal_sessions` field to each enabled symbol in `examples/czsc_strategy/diagnostics/simnow_contract_map.json`.
- Supported values are `"day"` and `"night"`.
- `run_next_work.ps1` will inspect every `enabled=true` symbol and determine whether the current local time falls into the day session or night session.
- A formal run is allowed only when every enabled symbol allows the current session.
- If one or more enabled symbols disallow the current session, the wrapper rejects the formal run and lists the blocking symbols in the error message.
- Smoke runs (`-SkipKlineUpdate`) remain exempt from this session gate.

## Session Rules

- Day session: `08:45:00` to `15:30:00` local time, inclusive.
- Night session: any other local time.
- Missing `formal_sessions` falls back to `["day", "night"]` so only explicit restrictions block a run.

## Scope

- Modify only:
  - `examples/czsc_strategy/diagnostics/run_next_work.ps1`
  - `examples/czsc_strategy/diagnostics/simnow_contract_map.json`
  - `examples/czsc_strategy/tests/unit/test_run_next_work_wrapper.py`

## Verification

- Unit tests prove:
  - formal night runs are rejected when any enabled symbol is day-only;
  - formal night runs are allowed when enabled symbols explicitly allow night;
  - smoke runs still bypass the formal-session gate.
