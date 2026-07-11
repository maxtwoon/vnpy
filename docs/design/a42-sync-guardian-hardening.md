# A42 Design: sync-guardian Hardening

> **Status: ACTIVE — promoted to a HANDOFF task 2026-07-12**, after A41 (SimNow authenticity fix)
> reached `done`. Originally produced 2026-07-11 by a read-only planning pass over an independent
> 3-way audit, alongside the A40 acceptance-criteria addendum
> (`docs/design/a40-real-position-sizing.md` §7a) and A41
> (`docs/design/a41-simnow-authenticity-fix.md`). Re-verified at promotion time: `tools/handoff.py:9`
> and `tools/sync_check.py:9` still hardcode the external `SCRIPT_DIR`; neither `.synccheck.yml`
> sets `no_auto_advance`; `examples/czsc_strategy/HANDOFF.md` is still frozen at A32/design/
> 2026-07-03 — no drift since the draft was written. §3d (stale sub-project HANDOFF.md cleanup)
> still contains an explicit judgment call flagged for the human reviewing this plan, not resolved
> by this promotion.

**Task:** Hardens the sync-guardian tooling itself: vendors the external
`tools/handoff.py`/`tools/sync_check.py` dependency (Finding #5) into the repo for
reproducibility, adds `no_auto_advance: [review]` (confirmed real, existing functionality in the
external `handoff.py`), adds deliverables-must-be-tracked enforcement, cleans up the stale
`examples/czsc_strategy/HANDOFF.md`, and adds a CI step running `sync_check` + pytest/preflight.

**Scope:** `tools/`, `.synccheck.yml`, `.github/workflows/pythonapp.yml`,
`examples/czsc_strategy/HANDOFF.md`/`.synccheck.yml`. No changes to strategy/backtest/diagnostics
code.

---

## 1. Background

Five gaps in the sync-guardian workflow itself, verified 2026-07-11:

1. `tools/handoff.py:9` and `tools/sync_check.py:9` hardcode
   `SCRIPT_DIR = Path(r"D:\repo\ashare\skills\sync-guardian\scripts")` — on any machine/CI runner
   without that exact path, both commands fail immediately. The vendoring scope is small:
   `handoff.py` (28,567 bytes) + `sync_check.py` (19,532 bytes) at
   `D:\repo\ashare\skills\sync-guardian\scripts\`, stdlib-only dependencies, `handoff.py` imports
   helper functions from `sync_check.py` (`handoff.py:46`).
2. `no_auto_advance` is real, existing functionality in the external `handoff.py` (confirmed at
   its lines ~18, ~544-552) — a YAML list under `.synccheck.yml`'s `handoff:` block. Today
   neither the root `.synccheck.yml` nor `examples/czsc_strategy/.synccheck.yml` sets it, so
   every stage (including `review`, the highest-stakes one) is eligible for the harness's silent
   auto-transition-on-agent-silence behavior when the pipeline's automated `run` loop is used.
3. `sync_check.py`'s `_check_handoff_file` (external, lines ~297-329) only verifies
   `deliverables` **exist as files on disk** — it does not verify they were modified/updated as
   part of the current stage's work, nor does it require any newly-produced evidence artifact
   (e.g. a new diagnostics report) to be added to the `deliverables:` list at all. A task can
   complete a stage without ever registering its actual output as a tracked deliverable, and
   `sync_check` won't flag it.
4. `examples/czsc_strategy/HANDOFF.md` is a live-gated (`examples/czsc_strategy/.synccheck.yml`
   still points at it) but content-stale file: `task: A32 审核问题数据接入 + A31 复核瑕疵修复`,
   `stage: design`, `owner: claude-cowork`, `updated: 2026-07-03` — frozen since before A34,
   while all real work since then has flowed through the **root** `HANDOFF.md`. The
   `--root examples/czsc_strategy` sync_check invocation (used as an acceptance command by
   A38/A39/A40) validates this stale file's structure, not anything about the actual current
   task.
5. `.github/workflows/pythonapp.yml` (per `AGENTS.md`'s own documentation) runs
   lint/typecheck/build only — "There is **no automated pytest step** in CI at the moment" and
   no `sync_check` step either, so a version/handoff-state drift or a broken acceptance gate
   would only ever be caught locally, not in CI.

## 2. Config

Add to root `.synccheck.yml`'s `handoff:` block (and mirror in
`examples/czsc_strategy/.synccheck.yml`):

```yaml
handoff:
  file: HANDOFF.md
  stages: [design, dev, review, done]
  owners:
    design: claude-code
    dev: kimi-code
    review: codex
  no_auto_advance: [review]   # review must explicitly next/reject; the pipeline's automated
                               # `run` loop must not silently treat "codex exited 0, forgot to
                               # transition" as an implicit accept for the highest-stakes gate.
  commands: ...                # unchanged
```

New top-level key in `.synccheck.yml` for deliverables enforcement:

```yaml
deliverables_policy:
  require_new_evidence_on_dev_to_review: true
  # When the stage transition is dev -> review, sync_check additionally requires
  # that at least one deliverable listed in HANDOFF.md's front matter has a git
  # mtime/diff newer than the transition's `updated` timestamp of the PRECEDING
  # design->dev transition (i.e. dev actually touched/added something tracked,
  # not just re-listed pre-existing files). Diagnostics evidence living under a
  # git-ignored directory (examples/czsc_strategy/diagnostics/) must appear in
  # `git show --stat` for the dev-stage commits (i.e. was `git add -f`'d), not
  # merely exist on disk untracked.
```

## 3. Semantics

### 3a. Vendoring fix (Finding #5)

Copy `handoff.py` and `sync_check.py` from `D:\repo\ashare\skills\sync-guardian\scripts\` into a
new repo-tracked directory `tools/sync_guardian/` (e.g. `tools/sync_guardian/handoff.py`,
`tools/sync_guardian/sync_check.py`), preserving the existing `handoff.py` → `sync_check.py`
import relationship (`from sync_check import ...`, unchanged since both files sit in the same
directory). Update the two existing wrapper entry points, `tools/handoff.py` and
`tools/sync_check.py`, to point `SCRIPT_DIR` at
`Path(__file__).resolve().parent / "sync_guardian"` instead of the external absolute path — this
preserves the existing `python tools/handoff.py ...` / `python tools/sync_check.py ...` CLI
surface (no caller, including every HANDOFF.md acceptance-command block written to date, needs
to change) while making the actual implementation self-contained.

`dashboard.py` and `init_project.py` are explicitly **not** vendored in this task (see
Boundaries §6) — they are not required for `tools/handoff.py`/`tools/sync_check.py` to run, and
vendoring them would expand scope without closing the reproducibility gap this task targets.

A one-time provenance note should be added as a comment at the top of both vendored files
recording the source path and date copied, so future maintainers know they were forked from
`D:\repo\ashare\skills\sync-guardian\scripts` on 2026-07-11 and are not expected to auto-sync
with that external location going forward — divergence is expected and acceptable; this repo's
copy is now authoritative for `vnpy`.

### 3b. `no_auto_advance: [review]`

As specified in §2 — purely a config addition to `.synccheck.yml`'s existing `handoff:` block,
consumed by the (now-vendored) `handoff.py`'s existing `run` command logic, which already
implements this exact check (confirmed, external `handoff.py` lines ~544-552) — no new code is
needed for this item beyond the config key itself and the vendoring in 3a. Apply to **both**
`.synccheck.yml` (root) and `examples/czsc_strategy/.synccheck.yml`, since both are live-gated
handoff configs.

### 3c. Deliverables-must-be-tracked enforcement

Add a new check function to the vendored `sync_check.py`,
`_check_deliverables_are_tracked_and_fresh`, invoked from `_check_handoff_file` when
`deliverables_policy.require_new_evidence_on_dev_to_review` is set:

- For a `stage == "review"` handoff file, verify (via
  `git log --follow -1 --format=%H -- <deliverable>` for each listed deliverable) that at least
  one deliverable was touched by a commit **after** the file's own
  `last_transition_from_stage: design` → `dev` transition commit (found via the
  `交接历史`/decision-log table or `last_transition_kind`/`last_transition_actor` front-matter
  fields already present in current `HANDOFF.md`s).
- If any deliverable path is inside a git-ignored directory (checked via
  `git check-ignore <path>`), require that the specific file appears in
  `git show --stat <most-recent-dev-stage-commit>` (i.e. was force-added) rather than merely
  existing on disk — this directly operationalizes the house-style rule already in effect:
  *"`examples/czsc_strategy/diagnostics/` is git-ignored, so any evidence artifact there must be
  `git add -f`'d to be reviewable."*
- Failure mode: `sync_check` errors (not just warns) with a message naming which deliverable(s)
  were never freshly tracked, so `dev`→`review` handoff cannot proceed via the gated
  `python tools/handoff.py next` command until fixed.

### 3d. Stale sub-project `HANDOFF.md` cleanup

`examples/czsc_strategy/HANDOFF.md` (A32, frozen at `design` since 2026-07-03) is archived, not
deleted (deletion could break any historical reference/tooling assuming the file's existence):
move it to `examples/czsc_strategy/diagnostics/archive/HANDOFF-A32-archived-2026-07-11.md` (the
archive directory `examples/czsc_strategy/.synccheck.yml` already designates:
`archive_dir: diagnostics/archive/`), and replace `examples/czsc_strategy/HANDOFF.md` with a
fresh file whose front matter honestly reflects present reality — either (a) `stage: done`,
`task: "A32 (superseded — see root HANDOFF.md for current work)"` with a one-line pointer, if the
sub-project handoff lineage is being formally retired in favor of root-only tracking going
forward, or (b) if the sub-project `--root examples/czsc_strategy` gate is still meant to track
something *meaningful* distinct from the root gate, a decision-log entry explaining what that
distinct thing is (today it appears to duplicate the root gate's purpose with no active content —
the design/dev/review commands in `examples/czsc_strategy/.synccheck.yml` are unset, meaning this
gate has no automated pipeline of its own; it may be safe to fully retire).

**This is a judgment call for the human reviewing this plan** — the concrete acceptance
criterion (§7) only requires that the file's `stage`/`task`/`updated` fields be truthful and that
`--root examples/czsc_strategy` continues to pass sync_check after the change, not a specific
choice of (a) vs (b).

### 3e. CI step running `sync_check` + pytest/preflight

Add a new job (or new steps in the existing job) to `.github/workflows/pythonapp.yml`, after the
existing `ruff check .` / `mypy vnpy` / `uv build` steps:

```yaml
      - name: sync_check (root)
        run: python tools/sync_check.py
      - name: sync_check (czsc_strategy)
        run: python tools/sync_check.py --root examples/czsc_strategy
      - name: pytest (czsc_strategy unit, not realdb)
        run: python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"
```

Given `AGENTS.md`'s own statement that CI currently has no pytest step and runs on
`windows-latest`, this addition runs on the same Windows runner already provisioned, avoiding new
cross-platform concerns. The `-m "not realdb"` marker exclusion is required since CI has no
access to the local historical SQLite DB (`SQLITE_DB_PATH`), matching how the task already
excludes `realdb` tests in every HANDOFF.md acceptance-command block observed to date.

## 4. No-lookahead / no-silent-pass discipline

Not directly applicable (this task is tooling/process, not backtest logic) — but the analogous
discipline applies: `sync_check`'s new deliverables-tracking check (§3c) must **fail loudly**
(non-zero exit, explicit error message) rather than warn-and-continue when a deliverable can't be
verified as freshly tracked, consistent with how `sync_check` already treats missing
deliverables as hard errors, not warnings.

## 5. Expected file changes

- `tools/sync_guardian/handoff.py`, `tools/sync_guardian/sync_check.py` — new, vendored copies
  (§3a).
- `tools/handoff.py`, `tools/sync_check.py` — `SCRIPT_DIR` updated to the repo-relative vendored
  path; `runpy.run_path` call otherwise unchanged.
- `.synccheck.yml` (root) — `handoff.no_auto_advance: [review]` (§3b); new `deliverables_policy`
  block (§3c).
- `examples/czsc_strategy/.synccheck.yml` — same two additions, mirrored.
- `examples/czsc_strategy/HANDOFF.md` — rewritten per §3d.
- `examples/czsc_strategy/diagnostics/archive/HANDOFF-A32-archived-2026-07-11.md` — new, archived
  copy of the old A32 file.
- `.github/workflows/pythonapp.yml` — new CI steps per §3e.
- `AGENTS.md` — one-line update to the CI section removing the now-stale "There is no automated
  pytest step in CI" statement.

## 6. Boundaries (what A42 does NOT do)

- **Does not vendor `dashboard.py` or `init_project.py`.** Only the two files actually required
  for `tools/handoff.py`/`tools/sync_check.py` to run (confirmed via import-graph check: neither
  `handoff.py` nor `sync_check.py` imports either file) are vendored. If the dashboard reporting
  tool is later needed, that's a separate, explicitly-scoped follow-up.
- **Does not change the sync-guardian *engine's* stage-transition/gate logic itself** beyond
  adding the `no_auto_advance` config consumption (which the vendored code already implements)
  and the new `_check_deliverables_are_tracked_and_fresh` check — no rewrite of `_transition`,
  `_die`, or the front-matter parser.
- **Does not retroactively re-validate past handoff transitions** (A31-A40) against the new
  deliverables-tracking rule — it applies going forward only, from the point this task lands.
- **Does not change any `owners`/`stages` values** for the root or sub-project handoff configs —
  only adds `no_auto_advance` and `deliverables_policy` as new keys.
- **Does not decide the final fate of `examples/czsc_strategy/.synccheck.yml`/its independent
  gate** beyond making its tracked `HANDOFF.md` truthful — whether the sub-project gate should be
  fully retired in favor of root-only tracking is flagged as a human decision point (§3d), not
  resolved unilaterally by this task.
- **Does not add pytest to CI for the *core* `vnpy`/`tests/` suite** beyond the
  `examples/czsc_strategy` unit suite already run locally per house convention — expanding CI to
  core-framework tests is a separate, unscoped decision.
- **No SimNow/backtest/strategy code touched** — this is pure tooling/process hardening.

## 7. Acceptance Criteria (decidable)

- [ ] `tools/sync_guardian/handoff.py` and `tools/sync_guardian/sync_check.py` exist,
      byte-content-equivalent (modulo the added provenance comment) to the source at
      `D:\repo\ashare\skills\sync-guardian\scripts\`; `tools/handoff.py`/`tools/sync_check.py`'s
      `SCRIPT_DIR` no longer references any path outside the repo.
- [ ] `python tools/handoff.py status` and `python tools/sync_check.py` both succeed when run
      from a fresh clone of the repo with `D:\repo\ashare` renamed/inaccessible (or simulated via
      a temporarily-unset/invalid `D:\repo\ashare` path in a test harness) — this is the direct
      reproducibility proof for Finding #5.
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
      the change date (no longer silently claims `stage: design` for a task last touched
      2026-07-03 while unrelated work has moved on); the old content is preserved at
      `examples/czsc_strategy/diagnostics/archive/HANDOFF-A32-archived-2026-07-11.md`
      (git-tracked, added with `git add -f` since the archive dir sits under the git-ignored
      `diagnostics/`).
- [ ] `python tools/sync_check.py --root examples/czsc_strategy` still passes after the §3d
      change.
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

## 8. Dev Handoff Prompt (dev = kimi-code)

```text
Read HANDOFF.md and docs/design/a42-sync-guardian-hardening.md. Implement A42 exactly as specified
-- tooling/process hardening only, no strategy/backtest/SimNow code changes.

1. Vendor D:\repo\ashare\skills\sync-guardian\scripts\handoff.py and sync_check.py into
   tools/sync_guardian/ (new dir), preserving their mutual import relationship. Update
   tools/handoff.py and tools/sync_check.py's SCRIPT_DIR to point at the repo-relative vendored
   path instead of the external absolute path. Do NOT vendor dashboard.py or init_project.py
   (not required by the two wrapper entry points).
2. Add handoff.no_auto_advance: [review] to both .synccheck.yml (root) and
   examples/czsc_strategy/.synccheck.yml.
3. Add a deliverables-freshness check to the vendored sync_check.py per design S3c: at dev->review
   transition, at least one HANDOFF.md deliverable must be freshly git-tracked (touched after the
   design->dev transition commit; if under a git-ignored dir, must appear in git show --stat for a
   dev-stage commit, i.e. was git add -f'd). Fail loudly (non-zero exit), not a warning.
4. Archive examples/czsc_strategy/HANDOFF.md (stale A32 content, frozen since 2026-07-03) to
   examples/czsc_strategy/diagnostics/archive/HANDOFF-A32-archived-2026-07-11.md (git add -f it,
   the dir is git-ignored). Replace examples/czsc_strategy/HANDOFF.md with a truthful current-state
   file per design S3d -- pick between "mark done/superseded, point to root HANDOFF.md" or
   "keep active with an honest current task" based on whether this sub-project gate still serves a
   purpose distinct from the root gate; record the decision in a decision-log entry.
5. Add sync_check (root + --root examples/czsc_strategy) and
   pytest examples/czsc_strategy/tests/unit -q -m "not realdb" as new steps in
   .github/workflows/pythonapp.yml, after the existing ruff/mypy/uv build steps.
6. Update AGENTS.md's CI section to remove the now-stale "no automated pytest step" statement.
7. Tests per design S7, including a fixture proving no_auto_advance actually halts the pipeline
   loop instead of silently auto-transitioning, and fixtures proving the deliverables-freshness
   check fails/passes as specified.

No strategy/backtest/SimNow code touched. No pre-2026-04-24 data for any selection (not applicable
here but keep the discipline). No GOAL PASSED.

Run:
- python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"
- python tools/sync_check.py ; python tools/sync_check.py --root examples/czsc_strategy
- python tools/handoff.py next --actor kimi-code --summary "A42 sync-guardian hardening implemented"
```

## 9. Review Checklist (review = codex)

Reject if: `tools/handoff.py`/`tools/sync_check.py` still reference any path outside the repo
(grep for `D:\repo\ashare` in the diff — must be zero hits outside a provenance comment); the
vendored `handoff.py run` loop does not actually halt (rather than silently transition) at
`review` when the agent doesn't self-transition; the deliverables-freshness check can be
satisfied by a deliverable that merely exists on disk without being freshly git-tracked (or, for
git-ignored paths, without being `git add -f`'d into a dev-stage commit);
`examples/czsc_strategy/HANDOFF.md`'s new content is itself inaccurate/stale; the new CI steps
are not actually present in `.github/workflows/pythonapp.yml` or don't fail on a
deliberately-broken fixture; any strategy/backtest/SimNow file touched; `sync_check` (root or
child) fails.

Accept if all §7 boxes are checked and the CI-gate-has-teeth evidence (a fixture/branch that
deliberately breaks a gate and is shown to fail CI) is present.
