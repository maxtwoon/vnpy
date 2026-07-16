# SimNow Formal Sessions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the hard-coded AP888 day-session gate with a config-driven per-symbol formal-session policy.

**Architecture:** The wrapper reads `formal_sessions` from the SimNow contract map, classifies the current local time as day or night, and rejects formal runs only when an enabled symbol disallows the current session. Tests drive the change from the wrapper boundary.

**Tech Stack:** PowerShell, JSON config, pytest

## Global Constraints

- Keep the workflow read-only.
- Touch only the wrapper, contract map, and wrapper unit tests.
- Preserve smoke behavior via `-SkipKlineUpdate`.
- Default missing `formal_sessions` to `["day", "night"]`.

---

### Task 1: Lock the new wrapper behavior in tests

**Files:**
- Modify: `examples/czsc_strategy/tests/unit/test_run_next_work_wrapper.py`
- Test: `examples/czsc_strategy/tests/unit/test_run_next_work_wrapper.py`

**Interfaces:**
- Consumes: `Assert-FormalObservationWindow -LiveCapture <bool> -SkipKlineUpdate <bool> -Now <datetimeoffset> -ContractMap <object>`
- Produces: failing tests that define config-driven formal-session behavior

- [ ] Add a failing test for rejecting a formal night run when an enabled symbol has `formal_sessions = @('day')`.
- [ ] Run `python -m pytest .\examples\czsc_strategy\tests\unit\test_run_next_work_wrapper.py -q` and verify the new test fails for the expected reason.

### Task 2: Implement config-driven formal-session validation

**Files:**
- Modify: `examples/czsc_strategy/diagnostics/run_next_work.ps1`
- Modify: `examples/czsc_strategy/diagnostics/simnow_contract_map.json`
- Test: `examples/czsc_strategy/tests/unit/test_run_next_work_wrapper.py`

**Interfaces:**
- Consumes: contract-map rows with `enabled: bool` and optional `formal_sessions: list[str]`
- Produces: wrapper rejection only when enabled symbols disallow the current session

- [ ] Update the contract map to declare `formal_sessions` for each configured symbol.
- [ ] Implement the minimal PowerShell logic to collect enabled symbols, derive the current session, and reject only on explicit mismatches.
- [ ] Re-run `python -m pytest .\examples\czsc_strategy\tests\unit\test_run_next_work_wrapper.py -q` and verify all wrapper tests pass.
