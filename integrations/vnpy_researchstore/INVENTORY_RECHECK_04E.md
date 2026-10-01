## Independent recheck — Claude inventory04E

**Input integrity:** all 8 hashes (4 stable: inventory.py, safeio.py, test_import_inventory.py, kimi-inventory-fix04d-handoff.md; 4 external: delivery04d-inventory.json, delivery04d-evidence.json, delivery04b-inventory.json, delivery04b-evidence.json) match `.coordination/claude-inventory04e-input-hashes.json` exactly — no drift.

**F1 (nested/flat path resolution) — CLOSED.** Read `_resolve_archive_path` in `inventory.py:218-322`: builds `<package>/<dataset>/<file>` first, falls back to flat `<package>/<file>`; validates the dataset segment for `..`/absolute escape before building the candidate and validates every resolved candidate stays under the resolved package root; never follows the historical absolute manifest `path`; surfaces same-vs-different-content ambiguity as a caveat rather than guessing. I independently re-ran `scan_rq_package(...)` myself (not just read the report) against the real on-disk packages:
- futures `rqdatac_china_futures_research_full_history_20260804`: **326 listed / 0 missing**
- PIT `rqdatac_a_share_pit_events_full_history_20260804`: **389 listed / 37 missing**, all `dataset=shares` — confirmed no `shares` directory exists anywhere under the package (`rglob` empty)
- other 7 packages: **0 missing**, unaffected

`pytest tests/test_import_inventory.py -v` → **15/15 passed**, including the 6 new F1 regressions (nested resolution, flat preservation, truthful nested missing, ambiguity conflict, dataset-traversal refusal, historical-path-ignored). `ruff check` and `mypy` both clean.

**F2 (fabricated timestamp) — CLOSED.** `delivery04d-evidence.json`'s `generated_at` (`2026-09-16T17:17:17.907206+00:00`) matches its own file mtime (`2026-09-17 01:17:17.9077 +0800`) to the second — a real measured value, not hand-typed (contrast with the old `delivery04b-evidence.json`'s ~8h16m-future value, left untouched as history per hash match).

No new findings introduced. No product/Git/memory/raw/provider/network/account writes made — only read-only checks and one temp evidence file at `.coordination/review-inventory04e/verification.json`.

**F1: CLOSED**
**F2: CLOSED**
**FINAL_VERDICT: PASS** (for the inventory-correction fix; not a full-WP10/first-usable-snapshot claim)