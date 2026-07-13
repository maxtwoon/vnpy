---
task: A60 - Project-Level VERSION/CHANGELOG Gate + Banner-Exemption Config Cleanup
version: 4.4.0
stage: done
owner: codex
updated: 2026-07-14
deliverables:
  - HANDOFF.md
  - docs/design/a55-post-remediation-audit-roadmap.md
blockers: []
last_transition_kind: next
last_transition_actor: codex
last_transition_from_stage: review
last_transition_to_stage: done
last_transition_from_owner: codex
last_transition_to_owner: codex
---

## Background

Sixth and final task of the 2026-07-13 post-remediation re-audit roadmap
(`docs/design/a55-post-remediation-audit-roadmap.md` §"A60"), promoted immediately after A59
reached `done` (codex accepted the round-2 fix directly). Completing this task finishes the entire
A55-A60 roadmap.

`docs/review/ai_trading_review_2026-07-13.md` Findings 🟢#8/#9 (re-verified 2026-07-14 by
claude-code against current code):

1. **VERSION/CHANGELOG drift already relapsed.** `examples/czsc_strategy/CHANGELOG.md` currently has entries for `0.1.0` (A31/sync-guardian init), `0.2.0` (A51), and `0.2.1` (A56) — confirmed by reading the file directly. synccheck:ignore
   **A52 (continuous-contract data-integrity), A53 (config/signal
   single-source-of-truth cleanup), and A54 (report-disclaimer hygiene + sync_check gate) have NO
   CHANGELOG entry and never bumped VERSION**, despite each being an externally-visible,
   already-`done` change (confirmed via `git log --grep` — all three fully shipped and reviewed).
   Root cause: the root `.synccheck.yml` only guards `vnpy/__init__.py`'s version string; the
   project-level `examples/czsc_strategy/VERSION` has no gate requiring it to move when the
   project's own config surface changes.
2. **Banner-exemption list is half-declared, half-hardcoded.**
   `tools/sync_guardian/sync_check.py:626`'s `_check_diagnostics_banner` function contains a
   hardcoded `if path.name.startswith("audit_issue_diagnostics_"): continue` — confirmed present at
   that exact line — bypassing the config-driven `skip` list entirely for this one prefix pattern.
   Separately, `diagnostics_banner_check`'s scan uses a non-recursive `d.glob("*.md")`
   (`sync_check.py:623`), so `diagnostics/archive/` (which DOES exist — confirmed via `ls`, contains
   `HANDOFF-A32-archived-2026-07-11.md`, confirmed missing the RESEARCH-ONLY banner) is silently
   never scanned. Both the root and child `.synccheck.yml` already declare `archive_dir:
   diagnostics/archive/` for a *different* purpose (informational-only WARN if the dir is missing)
   — its files being outside the banner scan is currently an accident of the non-recursive glob,
   not a deliberate, documented decision either way.

Full contract: `docs/design/a55-post-remediation-audit-roadmap.md` §"A60 — Project-Level
VERSION/CHANGELOG Gate + Banner-Exemption Config Cleanup" (the authoritative design — this HANDOFF
summarizes it).

## Goal

1. **Add a new `sync_check.py` check (or extend the version-consistency check)** requiring
   `examples/czsc_strategy/VERSION`/`CHANGELOG.md` to be touched whenever a commit modifies
   `chan_strategy/config.py`'s top-level `STRATEGY_CONFIG`/`BACKTEST_CONFIG` keys — mirroring the
   spirit of `_check_deliverables_are_tracked_and_fresh` (`sync_check.py:323`, the A42 pattern: git
   log/diff based, not a static snapshot check). Read that function in full before designing the
   new heuristic; do not invent an unrelated mechanism. Exact trigger detail (e.g. compare the
   commit's diff of `config.py` against whether `VERSION`/`CHANGELOG.md` appear in the same
   commit's changed-files list) is this task's own design refinement — finalize and document your
   chosen heuristic in the Decision Log before implementing.
2. **Backfill CHANGELOG entries for A52/A53/A54.** Since none of the three ever bumped VERSION at
   the time, do not retroactively invent a fake intermediate version number for each — add the
   three missing entries as a historical backfill note (e.g. under a dated addendum or clearly
   marked as "retroactively documented by A60; VERSION was not bumped at the time these shipped").
   The point is closing the documentation gap honestly, not rewriting history to look like it was
   done right the first time.
3. **Move the `audit_issue_diagnostics_*` exemption into `.synccheck.yml`'s `skip` config** as a
   glob/prefix pattern (confirm whether `_check_diagnostics_banner`'s `skip_names` set supports
   patterns — currently it's an exact-match `set[str]`, so you'll need to extend the matching logic
   minimally to support at least prefix or glob patterns, not just exact filenames). Remove the
   hardcoded `startswith` check from the checker once the config-driven version works.
4. **Resolve the `diagnostics/archive/` scanning ambiguity — pick one, document it:** either extend
   the banner-check glob to recurse into `archive/` and backfill the banner into
   `HANDOFF-A32-archived-2026-07-11.md`, or explicitly declare `archive/` as an exempt directory in
   `.synccheck.yml` with a clear reason (e.g. "archived historical HANDOFF snapshots, not live
   diagnostic reports, exempt by design"). Do not leave it as an unstated glob accident either way.

## Acceptance Criteria

- [x] A new `sync_check.py` check fails (non-zero exit, clear message) for a fixture commit that
      changes `chan_strategy/config.py`'s top-level keys without touching `VERSION`/`CHANGELOG.md`;
      passes when both are touched together (unit-tested with real teeth — a fixture test that
      actually exercises failure, mirroring A42's/A54's own fixture-test pattern in
      `tests/test_sync_guardian.py`).
- [x] `examples/czsc_strategy/VERSION`/`CHANGELOG.md` backfilled with entries for A52 (rollover
      tagging), A53 (5 config keys + equity_mode resolution), A54 (sizing_caveat + banner gate) —
      honestly marked as a retroactive backfill, not a fabricated original bump.
- [x] `audit_issue_diagnostics_*` exemption is declared in `.synccheck.yml`'s `skip` config (as a
      pattern, not a hardcoded string in the checker), verified by a test that changes the config
      pattern and confirms the checker honors the new value from config, not from hardcoded logic.
- [x] `diagnostics/archive/` is explicitly declared exempt in config with a documented reason — not
      silently unscanned via glob accident.
- [x] No threshold tuning; no pre-2026-04-24 data; no SimNow order/cancel/send paths touched; no
      `GOAL PASSED`; does not fork a second copy of `sync_check.py`'s logic.
- [x] `python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"` passes (and the
      existing `tests/test_sync_guardian.py` suite was extended rather than duplicated).
- [x] `python tools/sync_check.py` and `python tools/sync_check.py --root examples/czsc_strategy`
      pass.
- [x] `run_next_work.ps1 -Preflight` (from `examples/czsc_strategy/`) passes.

## Manual verification

All acceptance commands run natively in the dev environment on 2026-07-14:

- `python -m pytest tests/test_sync_guardian.py -q` → 12 passed
- `python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"` → 586 passed, 4 deselected
- `python tools/sync_check.py` → PASS
- `python tools/sync_check.py --root examples/czsc_strategy` → PASS
- `ruff check tools/sync_guardian/sync_check.py tests/test_sync_guardian.py` → All checks passed
- `powershell -ExecutionPolicy Bypass -File diagnostics/run_next_work.ps1 -Preflight` (from `examples/czsc_strategy/`) → Preflight complete

## Notes for the Next Agent

(codex review rejection - 2026-07-14)

1. `tools/sync_guardian/sync_check.py:644` still scans diagnostics with `d.glob("*.md")`, so
   nested files under `diagnostics/archive/` are never visited. That means the new
   `exempt_dirs` config is documented, but it is not what actually exempts archive files; they
   remain silently skipped by the same non-recursive glob accident A60 was meant to resolve.
   Fix by making the banner scan recursive (for example `rglob("*.md")`) and applying
   `_is_path_exempt` to every candidate, so `exempt_dirs` is the active reason archived files are
   skipped.
2. Strengthen `tests/test_sync_guardian.py:437` so it proves the archive exemption is active:
   the same unbannered archived markdown file should fail when `exempt_dirs` is absent or changed,
   and pass when `diagnostics/archive` is configured. The current test would pass even if
   `exempt_dirs` handling were removed, because the file is never scanned.

(dev = kimi-code must read this before writing code)

1. **Entry point:** `docs/design/a55-post-remediation-audit-roadmap.md` §"A60". Sixth and FINAL
   task of the A55-A60 roadmap — completing this closes out the entire post-remediation re-audit
   wave.
2. **Scope:** `tools/sync_guardian/sync_check.py` (new/extended version-freshness check; banner
   glob/archive resolution; config-driven `audit_issue_diagnostics_*` pattern), `.synccheck.yml`
   (root) and `examples/czsc_strategy/.synccheck.yml` (new check config; skip pattern),
   `examples/czsc_strategy/VERSION`/`CHANGELOG.md` (backfill), and a sync-guardian test file (find
   the existing one first — likely `tests/test_sync_guardian.py` at repo root — do not create a
   duplicate). Do not touch any `chan_strategy/*.py` trading logic — this is a pure tooling/process
   task, "No-lookahead & correctness" is explicitly "not applicable" per the design doc.
3. **Read `_check_deliverables_are_tracked_and_fresh` (`sync_check.py:323-`) in full before
   designing the new check** — it's the established git-log/diff-based pattern for "did X get
   touched relative to Y" checks in this codebase; your new check should follow the same spirit
   (real git history inspection, not a naive current-file-state snapshot).
4. **`_check_diagnostics_banner`'s exact hardcoded line is `sync_check.py:626`**
   (`if path.name.startswith("audit_issue_diagnostics_"): continue`) — confirmed present at this
   line as of 2026-07-14; verify it hasn't drifted before editing.
5. **`diagnostics/archive/` already exists** with one file
   (`HANDOFF-A32-archived-2026-07-11.md`, confirmed missing the banner) — your choice of "recurse
   and backfill" vs. "explicitly exempt" should be informed by what that file actually is (an
   archived historical HANDOFF snapshot, not a live research/diagnostic report — this leans toward
   "explicitly exempt," but use your own judgment and document the reasoning either way).
6. **CHANGELOG backfill wording matters** — do not silently rewrite the `0.2.0`/`0.2.1` sections to pretend A52-A54 happened at those version numbers. synccheck:ignore
   Add clearly-dated, clearly-marked backfill
   entries (e.g. their own subsection noting "retroactively documented 2026-07-14 by A60; no VERSION
   bump occurred when these originally shipped in 2026-07-13").
7. **Guardrails (reject-on-violation):** no threshold tuning; no pre-2026-04-24 data; no SimNow
   paths; no `GOAL PASSED`; no forked/duplicated `sync_check.py` logic; the new version-freshness
   check must have real teeth (a fixture proving it actually fails under the right condition), not
   just a docstring claiming it works.
8. **Include a Manual-verification block with natively-run counts, and run `ruff check`
   proactively before finishing.**
9. Finish with the acceptance commands, then
   `python tools/handoff.py next --actor kimi-code --summary "A60 project-level VERSION/CHANGELOG gate + banner-exemption cleanup implemented"`.
   Transactional gate — fix and retry if it blocks; no `--no-gate`. **This is the last task in the
   roadmap** — after this reaches `done`, the entire A55-A60 wave is complete.

## Decision Log

- 2026-07-14 - A60 promoted from `docs/design/a55-post-remediation-audit-roadmap.md`'s draft to an
  active HANDOFF task, started immediately after A59 reached `done` (codex accepted the round-2 fix
  directly). This is the final task of the A55-A60 roadmap.
- 2026-07-14 - claude-code re-verified both findings against current code: confirmed
  `CHANGELOG.md` has no A52/A53/A54 entries (reads directly from 0.1.0 to 0.2.0 to 0.2.1). synccheck:ignore
  Confirmed the hardcoded `audit_issue_diagnostics_*` check at `sync_check.py:626`, and confirmed
  `diagnostics/archive/` exists with one banner-less file that the current non-recursive glob never
  reaches. All citations verified by direct file reads, not assumed from the design doc's earlier
  description.
- 2026-07-14 - Heuristic for `project_version_freshness` (A60): git-log/diff-based, same spirit as
  A42's deliverables-freshness check. The gate locates the commit that introduced the
  `project_version_freshness` block into `.synccheck.yml` (dynamic `gate_since`) and only inspects
  commits strictly after it. For each such commit, if `config.py` changed, the file is parsed at the
  commit and at its parent; the JSON-normalised fingerprints of `STRATEGY_CONFIG` /
  `BACKTEST_CONFIG` are compared. Any key addition/removal or value change triggers a requirement
  that `VERSION` or `CHANGELOG.md` also appears in the same commit's changed-files list. This avoids
  retroactively punishing A52-A54 and keeps the check deterministic.
- 2026-07-14 - `diagnostics/archive/` resolved as explicitly exempt: the directory contains archived
  historical HANDOFF snapshots, not live research/diagnostic reports, so it is declared in
  `exempt_dirs` with a documented reason rather than backfilling a RESEARCH-ONLY banner onto a
  non-report file.
- 2026-07-14 - VERSION bumped to 0.2.2 for A60; A52/A53/A54 entries added as a retroactive backfill  # synccheck:ignore
  subsection under 0.2.2, clearly stating that no VERSION bump occurred when they originally shipped.  # synccheck:ignore
- 2026-07-14 - `sync_check.py` typing/style modernised in passing to satisfy `ruff check` on the
  changed file (no functional change).
- 2026-07-14 - codex review rejection round-2 fixes (kimi-code):
  - Changed `_check_diagnostics_banner` diagnostics scan from `d.glob("*.md")` to
    `d.rglob("*.md")` so nested files (including `diagnostics/archive/`) are actually visited,
    and `_is_path_exempt` is applied to each candidate. This makes `exempt_dirs` the active
    reason archived files are skipped, not an accidental non-recursive glob.
  - Strengthened `tests/test_sync_guardian.py::test_diagnostics_banner_archive_exempt_honors_config`
    to prove the exemption is active: the same unbannered archived file passes when
    `exempt_dirs` contains `diagnostics/archive`, and fails when the exemption is removed.

## 交接历史

| 日期 | 从 → 到 | 阶段变化 | 摘要 |
|------|---------|----------|------|
| 2026-07-14 | codex → claude-code | done → dev | A60 (project-level VERSION/CHANGELOG gate + banner-exemption cleanup) promoted from post-remediation audit roadmap; handoff design->dev |
| 2026-07-14 | kimi-code → codex | dev → review | A60 project-level VERSION/CHANGELOG gate + banner-exemption cleanup implemented |
| 2026-07-14 | codex → kimi-code | review → dev | 打回: Archive banner exemption is not actually exercised because diagnostics scan remains non-recursive |
| 2026-07-14 | kimi-code → codex | dev → review | A60 project-level VERSION/CHANGELOG gate + banner-exemption cleanup implemented |
| 2026-07-14 | codex → codex | review → done | A60 review passed: project version freshness gate and diagnostics banner exemptions verified |
