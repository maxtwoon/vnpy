## Verification result — Claude inventory04C audit

**Input integrity:** all 4 stable hashes in `.coordination/claude-inventory04c-input-hashes.json` match current on-disk sha256 exactly (inventory.py, safeio.py, test_import_inventory.py, kimi-delivery04b-handoff.md) — no drift, no source/product edits made during this review.

**Tests:** `.venv/Scripts/python.exe -m pytest tests/test_import_inventory.py -v` → 9/9 passed, confirming the crash fix (list/non-dict `archives` elements preserved as `failed_records`/`unrecognized_records`, path-escape refusal) is real and correctly retained.

### FINAL_VERDICT: **FAIL** (for the "full-source inventory correction" claim)

The TypeError-crash fix itself is correct and verified. But the delivery's headline claim — PIT/futures packages have **zero on-disk archives, 389/326 "truthfully" missing** — is false, caused by an unfixed defect in the same function.

---

### Finding 1 (HIGH) — false "missing" from flat-root path resolution ignoring manifest `dataset` field
- **Path:** `research_store/importers/inventory.py:267` — `archive_path = package_path / name` (never uses `archive.get("dataset")`)
- **Trigger:** any RQ package whose manifest entries carry a `dataset` key and store archives in a per-dataset subdirectory (both PIT and china-futures-research packages; the 7 "clean" packages store archives flat at package root, so they're unaffected — that's why only these two show 100% missing).
- **Evidence:**
  - Manifest entry: `{"dataset":"basis_1d","file":"rqdatac_basis_1d_2010.tar.zst", ...}`; real file at `.../rqdatac_china_futures_research_full_history_20260804/basis_1d/rqdatac_basis_1d_2010.tar.zst`, not at package root.
  - Direct filesystem check: futures package **326/326** listed archives exist on disk under `<dataset>/<file>`, `0` truly absent — includes `contract_1m_none/rqdatac_contract_1m_none_2025.tar.zst` (662,207,309 bytes) and `dominant_1m_none/rqdatac_dominant_1m_none_2025.tar.zst` (124,306,799 bytes), matching the byte counts cited in the task exactly.
  - PIT package: **352/389** exist nested under `<dataset>/`; only **37** are genuinely absent (all `dataset=shares`, years 1990–2026 — confirmed no `shares/` directory exists anywhere under the package at all, so that subset is real, truthful "missing").
  - Reproduced with the actual project code (`scan_rq_package(...)`): currently emits `326/326` and `389/389` missing, matching the developer's reported numbers — so the miscount is real and current, not a stale report.
  - Evidence JSON saved: `.coordination/review-inventory04c/nested-path-verification.json`.
- **Minimum fix:** when `archive.get("dataset")` is present, try `package_path / dataset / name` (and only fall back to the flat `package_path / name`) before recording `missing_archives`; apply the same resolved path to the escape-refusal check.
- **Retained working behavior:** the 7 flat-layout packages, the crash-fix's failed/unrecognized-record handling, and the path-escape refusal logic are all correct as-is — do not change them.

### Finding 2 (MEDIUM) — `evidence.json` `generated_at` is a fabricated/mislabeled timestamp, not measured
- **Path:** `D:/quant-data/reports/delivery04b/delivery04b-evidence.json:2`
- **Evidence:**
  - File's own claimed value: `"generated_at": "2026-09-17T01:20:00+00:00"`.
  - File's actual filesystem mtime: `2026-09-17 01:04:27+08:00` (system TZ confirmed `+0800`) = `2026-09-16T17:04:27Z`.
  - The sibling `delivery04b-inventory.json`'s `generated_at` **is** code-measured (`datetime.now(timezone.utc).isoformat()` inside `scan_source_roots`) and equals `2026-09-16T17:03:19+00:00`, which matches that file's own mtime (`2026-09-17 01:03:19+08:00`) to the second — proving the measurement mechanism is trustworthy when actually used.
  - `evidence.json`'s claimed `01:20:00+00:00`, taken literally as UTC, is **~8h16m after** the file was actually written — impossible. This is consistent with someone hand-typing the local wall-clock reading ("01:20" Beijing) but tagging it `+00:00` instead of `+08:00`.
- **Minimum fix:** derive `evidence.json`'s `generated_at` programmatically from the actual run (reuse the inventory's own `generated_at` or `datetime.now(timezone.utc)`), not hand-typed.

### Commands/hashes used
```
sha256sum research_store/importers/inventory.py research_store/importers/safeio.py \
  tests/test_import_inventory.py .coordination/kimi-delivery04b-handoff.md
.venv/Scripts/python.exe -m pytest tests/test_import_inventory.py -v
.venv/Scripts/python.exe -c "from research_store.importers.inventory import scan_rq_package; ..."
stat -c '%y %n' delivery04b-inventory.json delivery04b-evidence.json
```
No product, git, or memory writes made; only temp evidence under `.coordination/review-inventory04c/`. Note: the 37 truly-missing "shares" PIT archives are a genuine data gap, not a code defect — do not count them toward the false-missing finding.