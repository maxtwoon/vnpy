# SimNow Formal Window Auto-Duration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace fixed-duration formal SimNow captures with three approved formal windows that automatically run from the window start time to the window close time.

**Architecture:** Keep the behavior inside `run_next_work.ps1` so the automation entrypoint remains the single source of truth. Add one wrapper helper that classifies the current time into the approved formal windows and returns an auto-computed duration; then use that helper before capture starts so invalid windows fail early and valid windows no longer depend on a hard-coded `1800` seconds.

**Tech Stack:** PowerShell wrapper logic, pytest wrapper structure tests, existing SimNow diagnostics scripts.

## Global Constraints

- Default workflow is read-only.
- Do not send orders unless the user gives explicit written authorization in the current turn.
- Keep changes minimal and focused on the formal-window scheduling behavior.
- Formal windows are fixed at `09:05`, `13:35`, and `21:05`.
- Formal runs must automatically compute duration to the corresponding window close time.
- Non-window times must reject formal runs instead of silently falling back.
- Same-day later windows are allowed to overwrite earlier same-day results.

---

### Task 1: Lock the approved window behavior in tests

**Files:**
- Modify: `examples/czsc_strategy/tests/unit/test_run_next_work_wrapper.py`
- Test: `examples/czsc_strategy/tests/unit/test_run_next_work_wrapper.py`

**Interfaces:**
- Consumes: wrapper helper functions extracted from `examples/czsc_strategy/diagnostics/run_next_work.ps1`
- Produces: regression coverage for approved windows, rejected times, and auto-duration math

- [ ] **Step 1: Write failing tests**

Add tests covering:

```python
def test_formal_capture_plan_day_open_window_uses_1130_close():
    ...

def test_formal_capture_plan_afternoon_window_uses_1500_close():
    ...

def test_formal_capture_plan_night_window_uses_2300_close():
    ...

def test_formal_capture_plan_rejects_non_window_time():
    ...

def test_formal_capture_plan_rejects_when_remaining_time_is_shorter_than_min_bars():
    ...
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest .\examples\czsc_strategy\tests\unit\test_run_next_work_wrapper.py -q`

Expected: new formal-window tests fail because the helper does not exist yet and the wrapper still depends on the caller-provided duration.

- [ ] **Step 3: Keep tests focused on wrapper-visible behavior**

Use only extracted PowerShell helper functions plus stdout assertions. Do not add integration tests that require a live SimNow session.

- [ ] **Step 4: Re-run the focused test file after each edit**

Run: `python -m pytest .\examples\czsc_strategy\tests\unit\test_run_next_work_wrapper.py -q`

Expected: failures narrow to the not-yet-implemented wrapper behavior only.

### Task 2: Implement the formal window planner in the wrapper

**Files:**
- Modify: `examples/czsc_strategy/diagnostics/run_next_work.ps1`
- Test: `examples/czsc_strategy/tests/unit/test_run_next_work_wrapper.py`

**Interfaces:**
- Consumes: `LiveCapture`, `SkipKlineUpdate`, `MinKlineBarsPerSymbol`, current local time
- Produces: one helper that returns approved window metadata and an auto-computed duration used by the live capture step

- [ ] **Step 1: Add a helper that maps current local time to one approved formal window**

Implement a PowerShell helper returning:

```text
session_name
window_start
window_end
duration_seconds
```

using these windows:

```text
09:05 -> 11:30
13:35 -> 15:00
21:05 -> 23:00
```

- [ ] **Step 2: Reject formal runs outside those windows**

If the current time is not inside one of the three approved windows and this is not a smoke run, throw an actionable error explaining that formal runs are limited to the approved windows.

- [ ] **Step 3: Reject formal runs when the remaining window time cannot satisfy the bar threshold**

Use the computed remaining seconds and require:

```text
remaining_seconds >= MinKlineBarsPerSymbol * 60
```

for formal runs. Keep `-SkipKlineUpdate` exempt so smoke remains explicit.

- [ ] **Step 4: Override the live capture duration with the computed window duration**

Before invoking `simnow_daily_capture.py`, replace the caller-supplied duration with the window-derived duration for formal runs. Keep the existing explicit duration behavior for smoke runs.

- [ ] **Step 5: Update wrapper output with the chosen formal window**

Log the selected formal window and computed duration so operators can see why the wrapper chose the final capture length.

### Task 3: Verify end-to-end wrapper behavior

**Files:**
- Modify: `examples/czsc_strategy/diagnostics/run_next_work.ps1`
- Modify: `examples/czsc_strategy/tests/unit/test_run_next_work_wrapper.py`
- Test: `examples/czsc_strategy/tests/unit/test_run_next_work_wrapper.py`

**Interfaces:**
- Consumes: updated helper + existing wrapper steps
- Produces: verified wrapper behavior plus fresh automation memory

- [ ] **Step 1: Run the focused wrapper test file**

Run: `python -m pytest .\examples\czsc_strategy\tests\unit\test_run_next_work_wrapper.py -q`

Expected: PASS

- [ ] **Step 2: Run full preflight**

Run: `powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight`

Expected: PASS, including the wrapper tests and all existing SimNow diagnostics unit tests.

- [ ] **Step 3: Update automation memory**

Append a concise summary of the new window planner behavior and verification results to `$CODEX_HOME/automations/simnow/memory.md`.

