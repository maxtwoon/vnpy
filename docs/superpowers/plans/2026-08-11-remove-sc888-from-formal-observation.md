# Remove SC888 From Formal Observation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove `SC888` from the formal SimNow observation enabled symbol set and align diagnostics defaults/tests with the new three-symbol observation contract map.

**Architecture:** Keep the change surgical by making `simnow_contract_map.json` the single source of truth for the enabled formal-observation set, then update tests and any diagnostics defaults that intentionally mirror that enabled set. Do not rewrite historical reports or unrelated `SC888` research scripts.

**Tech Stack:** Python, pytest, PowerShell wrapper config JSON

## Global Constraints

- Default workflow stays read-only; no order-sending behavior changes.
- Touch only files directly tied to formal observation symbol selection and its tests.
- Use TDD: failing tests first, then the minimal config/code changes to pass.
- Preserve existing diagnostics/history artifacts; do not rewrite generated historical reports.

---

### Task 1: Lock New Formal Observation Contract Map In Tests

**Files:**
- Modify: `D:\repo\vnpy\examples\czsc_strategy\tests\unit\test_run_next_work_wrapper.py`
- Modify: `D:\repo\vnpy\examples\czsc_strategy\tests\unit\test_simnow_run_summary.py`

**Interfaces:**
- Consumes: `examples/czsc_strategy/diagnostics/simnow_contract_map.json`
- Produces: failing expectations for the new enabled set `["A888", "RB888", "ZN888"]`

- [ ] **Step 1: Write the failing tests**
- [ ] **Step 2: Run the targeted tests to verify they fail**
- [ ] **Step 3: Confirm the failures are due to old SC888-enabled expectations**

### Task 2: Remove SC888 From Formal Observation Source Of Truth

**Files:**
- Modify: `D:\repo\vnpy\examples\czsc_strategy\diagnostics\simnow_contract_map.json`

**Interfaces:**
- Consumes: current `_meta` version/note and `SC888.enabled`
- Produces: updated formal-observation metadata and enabled symbol set without `SC888`

- [ ] **Step 1: Disable `SC888` in the contract map and update `_meta`**
- [ ] **Step 2: Keep other symbols unchanged**

### Task 3: Re-run Targeted Tests And Repair Any Observation-Default Expectations

**Files:**
- Modify if needed: `D:\repo\vnpy\examples\czsc_strategy\tests\unit\test_run_next_work_wrapper.py`
- Modify if needed: `D:\repo\vnpy\examples\czsc_strategy\tests\unit\test_simnow_run_summary.py`

**Interfaces:**
- Consumes: updated contract map
- Produces: passing tests for provenance/enabled-symbol behavior

- [ ] **Step 1: Run the targeted tests**
- [ ] **Step 2: Apply the smallest additional expectation updates if new failures appear**
- [ ] **Step 3: Re-run until green**

### Task 4: Verify No Broader Formal Observation Regressions

**Files:**
- Verify only: `D:\repo\vnpy\examples\czsc_strategy\tests\unit\test_run_next_work_wrapper.py`
- Verify only: `D:\repo\vnpy\examples\czsc_strategy\tests\unit\test_simnow_run_summary.py`
- Verify only: `D:\repo\vnpy\examples\czsc_strategy\diagnostics\simnow_contract_map.json`

**Interfaces:**
- Consumes: updated config and tests
- Produces: evidence that the observation wrapper and run-summary expectations remain coherent

- [ ] **Step 1: Run the final targeted verification commands**
- [ ] **Step 2: Inspect the updated contract map payload**
- [ ] **Step 3: Report the exact new enabled set and residual scope limits**
