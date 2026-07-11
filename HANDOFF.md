---
task: A42 sync-guardian Hardening
version: 4.4.0
stage: dev
owner: kimi-code
updated: 2026-07-12
deliverables:
  - HANDOFF.md
  - docs/design/a42-sync-guardian-hardening.md
  - tools/sync_guardian/handoff.py
  - tools/sync_guardian/sync_check.py
  - tools/handoff.py
  - tools/sync_check.py
  - .synccheck.yml
  - examples/czsc_strategy/.synccheck.yml
  - examples/czsc_strategy/HANDOFF.md
  - examples/czsc_strategy/diagnostics/archive/HANDOFF-A32-archived-2026-07-11.md
  - .github/workflows/pythonapp.yml
  - AGENTS.md
  - tests/test_sync_guardian.py
blockers: []
last_transition_kind: next
last_transition_actor: claude-code
last_transition_from_stage: design
last_transition_to_stage: dev
last_transition_from_owner: claude-code
last_transition_to_owner: kimi-code
---

## Background

Tooling/process hardening, not part of the P1-P8 backtest-return-quality roadmap
(`docs/design/a38-phase-contracts-p2-p8.md`) — same parallel diagnostics-integrity line of work
as A41, started after A41 (SimNow authenticity fix) reached `done`. Promoted 2026-07-12 from a
DRAFT design produced during the same independent read-only 3-way audit that produced A40's §7a
addendum and A41; re-verified at promotion time that none of A42's five target findings drifted
during A40/A41 (both scoped to `chan_strategy/` and `diagnostics/simnow_*.py` respectively, never
`tools/`, `.synccheck.yml`, or `.github/workflows/`).

Five gaps in the sync-guardian workflow itself, verified 2026-07-11 and re-verified 2026-07-12:

1. `tools/handoff.py:9` / `tools/sync_check.py:9` hardcode
   `SCRIPT_DIR = Path(r"D:\repo\ashare\skills\sync-guardian\scripts")` — fails on any
   machine/CI runner without that exact external path.
2. `no_auto_advance` is real, existing functionality in the external `handoff.py`, but neither
   `.synccheck.yml` (root or `examples/czsc_strategy`) sets it — every stage, including `review`,
   is eligible for the automated `run` loop's silent auto-transition-on-agent-silence behavior.
3. `sync_check.py`'s deliverables check only verifies files **exist on disk**, not that they were
   actually touched during the current stage — a stage can complete without ever registering its
   real output as a tracked deliverable.
4. `examples/czsc_strategy/HANDOFF.md` is stale and misleading: `task: A32`, `stage: design`,
   `owner: claude-cowork`, `updated: 2026-07-03`, frozen since before A34 while all real work has
   flowed through the root `HANDOFF.md` since.
5. `.github/workflows/pythonapp.yml` runs lint/typecheck/build only — no pytest step, no
   `sync_check` step — so a version/handoff-state drift or broken acceptance gate is only ever
   caught locally.

Single source of truth: `docs/design/a42-sync-guardian-hardening.md`.

## Goal

Vendor `tools/handoff.py`/`tools/sync_check.py`'s external dependency into
`tools/sync_guardian/` for reproducibility; add `handoff.no_auto_advance: [review]` to both
`.synccheck.yml` files; add a deliverables-freshness enforcement check to the vendored
`sync_check.py` (fails loudly, not a warning, when a `dev`→`review` transition's deliverables
weren't freshly git-tracked — including `git add -f` for git-ignored paths); archive the stale
`examples/czsc_strategy/HANDOFF.md` and replace it with a truthful current-state file; add
`sync_check` (root + child) and the `czsc_strategy` unit-test suite as new CI steps in
`.github/workflows/pythonapp.yml`; update `AGENTS.md`'s CI section accordingly. No
strategy/backtest/SimNow code touched — scope is strictly `tools/`, `.synccheck.yml` files,
`.github/workflows/pythonapp.yml`, `AGENTS.md`, `examples/czsc_strategy/HANDOFF.md`/archive.

## Acceptance Criteria

- [ ] `tools/sync_guardian/handoff.py` and `tools/sync_guardian/sync_check.py` exist,
      byte-content-equivalent (modulo the added provenance comment) to the source at
      `D:\repo\ashare\skills\sync-guardian\scripts\`; `tools/handoff.py`/`tools/sync_check.py`'s
      `SCRIPT_DIR` no longer references any path outside the repo.
- [ ] `python tools/handoff.py status` and `python tools/sync_check.py` both succeed when run
      from a fresh clone of the repo with `D:\repo\ashare` renamed/inaccessible (or simulated via
      a temporarily-unset/invalid `D:\repo\ashare` path in a test harness) — direct reproducibility
      proof for Finding #5 in the design's numbering (external-path removal).
- [ ] `.synccheck.yml` (root) and `examples/czsc_strategy/.synccheck.yml` both set
      `handoff.no_auto_advance: [review]`.
- [ ] A test/fixture exercises the vendored `handoff.py run` loop with a stub agent command that
      exits 0 without transitioning stage while at `stage: review`; the loop halts with a
      non-zero exit and the stage remains `review` (does not silently auto-advance to `done`).
- [ ] `sync_check`'s new deliverables-tracking check fails (non-zero exit, named deliverable in
      the error) for a fixture HANDOFF.md at `stage: review` whose listed deliverables were not
      touched by any commit after its `design`→`dev` transition; passes for a fixture where at
      least one was.
- [ ] The same check fails for a fixture deliverable path under a git-ignored directory that
      exists on disk but was never `git add -f`'d into any tracked commit; passes once it is.
- [ ] `examples/czsc_strategy/HANDOFF.md`'s `stage`/`task`/`updated` fields are truthful as of
      the change date; the old content is preserved at
      `examples/czsc_strategy/diagnostics/archive/HANDOFF-A32-archived-2026-07-11.md`
      (git-tracked, added with `git add -f` since the archive dir sits under the git-ignored
      `diagnostics/`).
- [ ] `python tools/sync_check.py --root examples/czsc_strategy` still passes after the change.
- [ ] `.github/workflows/pythonapp.yml` runs `python tools/sync_check.py`,
      `python tools/sync_check.py --root examples/czsc_strategy`, and
      `python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"` as CI steps; a
      deliberately-broken `HANDOFF.md` (e.g. malformed front matter) in a throwaway test branch
      is confirmed to fail the CI job (gate has teeth in CI, not just locally).
- [ ] `AGENTS.md`'s CI section no longer states "no automated pytest step."
- [ ] No SimNow/backtest/strategy code touched (diff scoped to `tools/`, `.synccheck.yml` files,
      `.github/workflows/pythonapp.yml`, `AGENTS.md`, `examples/czsc_strategy/HANDOFF.md`/
      archive).
- [ ] `python tools/sync_check.py` (root, using the newly-vendored implementation) passes on this
      task's own final state.

## Notes for the Next Agent

(dev = kimi-code must read this before writing code)

1. **Entry point:** `docs/design/a42-sync-guardian-hardening.md`. Full dev prompt in design §8;
   review checklist in §9.
2. **This is pure tooling/process work** — `tools/`, `.synccheck.yml` (both), `.github/workflows/
   pythonapp.yml`, `AGENTS.md`, `examples/czsc_strategy/HANDOFF.md`. Do not touch
   `chan_strategy/` or `diagnostics/simnow_*.py` — none of the five findings are there.
3. **Vendoring scope is exactly two files** (§3a): `handoff.py` + `sync_check.py` from
   `D:\repo\ashare\skills\sync-guardian\scripts\`, preserving their mutual import relationship.
   Do NOT vendor `dashboard.py`/`init_project.py` — confirmed via import-graph check that neither
   is required.
4. **`no_auto_advance: [review]` needs no new logic** — it's a config key the vendored
   `handoff.py`'s existing `run` loop already consumes (confirmed at its lines ~544-552). Just
   add the key to both `.synccheck.yml` files after vendoring.
5. **§3d (stale sub-project HANDOFF.md) is a judgment call** — pick (a) mark
   `examples/czsc_strategy/HANDOFF.md` as done/superseded pointing to root, or (b) keep it active
   with a distinct honest purpose. The acceptance criterion only requires truthful fields and a
   passing `--root examples/czsc_strategy` gate, not a specific choice. Record the decision in a
   decision-log entry either way.
6. **Deliverables-freshness check (§3c) must fail loudly** — non-zero exit with the specific
   deliverable named, not a warning. This is the single highest-value check in this task: it's
   what would have caught A40/A41's repeated "report/module not git-tracked" defects automatically
   instead of requiring manual `git ls-files` due diligence each time.
7. **CI-gate-has-teeth evidence is required**, not just "the steps exist" — a deliberately-broken
   fixture/branch shown to fail the new CI job.
8. **Guardrails (reject-on-violation):** no `chan_strategy/`/SimNow code touched; no threshold
   tuning; `handoff.py`/`sync_check.py`'s public CLI surface (`python tools/handoff.py ...`)
   unchanged for all existing callers.
9. **Known environment accommodation:** if pytest/preflight hit the documented codex-sandbox
   Windows-symlink limitation during review, add a fresh Manual-verification block to this task's
   HANDOFF.md (doesn't persist automatically across tasks).
10. Finish with the acceptance commands, then
    `python tools/handoff.py next --actor kimi-code --summary "A42 sync-guardian hardening implemented"`.
    Transactional gate — fix and retry if it blocks; no `--no-gate`.

## Decision Log

- 2026-07-12 - A42 promoted from DRAFT to an active HANDOFF task after A41 reached `done`,
  matching the user's chosen sequencing ("先完成 A40 再依次 A41→A42"). Re-verified all cited
  file:line targets are unchanged since the draft was written — A40/A41's changes never touched
  `tools/`, `.synccheck.yml`, or `.github/workflows/`.
- 2026-07-11 (design, original) - Scoped vendoring to exactly the two files
  (`handoff.py`/`sync_check.py`) required for the existing CLI surface to keep working;
  `dashboard.py`/`init_project.py` explicitly excluded (not imported by either).
- 2026-07-11 (design, original) - §3d (stale sub-project HANDOFF.md) deliberately left as an
  explicit human judgment call rather than resolved unilaterally by the design, since it depends
  on whether the sub-project gate is meant to track something distinct from the root gate going
  forward.

## 交接历史

| 日期 | 从 → 到 | 阶段变化 | 摘要 |
|------|---------|----------|------|
| 2026-07-12 | codex → claude-code | done → design | A42 promoted from draft to active task after A41 reached done |
| 2026-07-12 | claude-code → kimi-code | design → dev | A42 promoted from draft to active task; re-verified no drift from A40/A41 |
