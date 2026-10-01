# Corrected source04I review (04IB) — bounded factual correction only

No new archive scans/streams; reused the two already-extracted parquet members (`contract_unit_0000.parquet`, `dominant_unit_0000.parquet`) and already-read `universe.csv`/sidecar json from `.coordination/review-futures04i/`. Correction analysis also saved there as `correction04ib_notes.md`.

## PROVEN (hashes, unchanged from 04I, not recomputed)
- `contract_1m_none_2025.tar.zst` sha256 `ec4c2aa7ffe401a255e70ef719d60ddead84f55c75bf6ac8514ccaed8c4da862` (662,207,309 bytes); `dominant_1m_none_2025.tar.zst` sha256 `f9954338f75257d3d2aa3e364a469a9657615fb051e4a5a45941a10ff1be380d` (124,306,799 bytes); sidecar sha256 `e08fb5bff8d39b1ec0c695b8dc928823d3f1ec0073e9c13d79d5c3a1dd6ed6a8` (859 bytes) — all match FUTURES_INPUT_CANDIDATES.md.
- Extracted member hashes: contract `unit_0000.parquet` sha256 `98e2dd44c7364acedd3ba6239fcf9f73b5ab33a99829a02dbf6d803c19e0d9cb`; dominant `unit_0000.parquet` sha256 `b93006d70c889c5bc82945b61a777a8bbbe27dcd4a1f949e48433793dc0e189a`.
- Repair sidecar's `bar_label` field literally reads "minute bar timestamp is the bar start label returned by RQData" — an explicit textual START claim, with `status: sidecar_only` and no accompanying row/calendar data.

## PROVEN (exact join, unchanged)
- Exact key (contract.order_book_id = dominant.dominant_id, datetime = datetime), A2505, window [2025-01-02, 2025-01-07): 1035 contract rows, 1035 dominant rows, 1035 matched, 0 unmatched, 0 duplicate keys either side, 0 value conflicts.
- Friday-night mapping: 2025-01-03 21:01:00 → trading_date 2025-01-06; 2025-01-02 21:01:00 → 2025-01-03; pattern holds through every night-session row in the window, including the boundary row 2025-01-06 21:01:00 → 2025-01-07.

## EMPIRICAL (locally checkable, but not by itself proof of label direction)
- The first bar timestamp of every session block in the window (21:01:00 / 09:01:00 / 10:31:00 / 13:31:00) matches `universe.csv`'s own `trading_hours` field for A2505 **exactly** — there is no offset between the minute-bar grid and the trading_hours string. The night session's last bar (23:00:00) also matches trading_hours' declared close exactly.
- `amount / (volume * 10)` approximates `close` for sampled rows (e.g. 3935.09 implied vs 3935.0 close) — a units/multiplier plausibility check.

## CORRECTED — demoted from RESOLVED to UNKNOWN
**(1) Label convention: UNKNOWN, not RESOLVED.** The 04I report described 21:00/09:00/10:30/13:30 as "independently declared" real opens and treated the :01 values as a +1-minute shift proving an END label. That 21:00/09:00/10:30/13:30 figure was never read from a local file — it came from outside general knowledge about Chinese futures exchange hours, applied to interpret local data. No RQData-independent local source (exchange calendar, contract spec, etc.) exists in this archive that records gate-open times separately from RQData-authored fields; `universe.csv`/`universe.json` are the only local hours source and could themselves already be reporting bar-grid-derived times rather than calendar times. The minute grid and `trading_hours` are internally consistent with each other, but internal self-consistency between two RQData-sourced fields does not establish which labeling convention produced it. **Corrected disposition: for this exact archive/member/window/contract, the label convention (START vs END) is UNKNOWN — a plausible, unproven hypothesis (END) coexists with the sidecar's unproven textual claim (START), and neither is established by local evidence.** This ambiguity is preserved, not resolved.

**(2) Turnover check does not bear on label direction.** `amount/(volume*10) ≈ close` holds regardless of whether a bar's timestamp names its start or end — it reflects only that the multiplier/units are plausible, not which endpoint the timestamp is. Retained solely as multiplier support, removed as label evidence.

**(3) Multiplier=10 for the window: not established historically, just not contradicted.** `universe.csv` is a single archive-dated snapshot (2026-08-03), long after the Jan-2025 window. The window falling inside `listed_date`/`de_listed_date` is necessary but not sufficient to prove the multiplier was 10 specifically during 2025-01-02..01-06 — no local multiplier-history/versioning file was found. Current snapshot value = 10; historical validity for the exact window = UNKNOWN, with no contrary local evidence either.

## Unaffected from 04I
The 1035-row exact join, its zero unmatched/duplicate/conflict counts, all recorded hashes, and the sidecar's unsupported START claim stand as previously reported and are not reopened by this correction.

## Next executable real validation scope (unchanged in kind, now explicitly targeting the demoted item)
1. Locate or rule out any local, RQData-independent source of real exchange session-open times (contract specifications, exchange trading-calendar files) before attempting to resolve END vs START again; absent that, the label question stays a source-side question requiring RQData verification (network/provider access, out of scope here).
2. No package-wide or cross-contract extrapolation is warranted from this bounded correction.

This is a factual correction only; no new import, freeze, product-code change, or archive rehash was performed.
