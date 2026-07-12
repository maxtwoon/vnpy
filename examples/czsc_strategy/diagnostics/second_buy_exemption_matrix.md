# Second-Buy Exemption Matrix

<!-- RESEARCH-ONLY / NOT PROMOTION EVIDENCE -->

> ⚠️ **RESEARCH ONLY — NOT PROMOTION EVIDENCE**
>
> This report was produced using the historical out-of-sample window `2022-01-01~2026-04-24`, which was repeatedly used for parameter selection. High-precision weights such as `0.847` and any bare `GOAL PASSED` rows are gate-fitting signatures, not evidence of a robust trading discovery. This artifact is retained as negative / contaminated evidence only.
>
> - `is_promotion_evidence`: False
> - `research_only`: True
> - `used_data_windows`: `["2022-01-01~2026-04-24"]`
> - `decision_data_windows`: ['2026-04-24~present', 'SimNow observation']
> - `note`: Future validation must use post-2026-04-24 incremental data and SimNow observation before any promotion claim can be considered.


- generated_at: `2026-06-19T00:59:47.418431+00:00`
- baseline here means current `combined` candidate.
- exemption means disabling only `max_2buy_entry_vs_anchor_pct` for that symbol; trailing overrides stay unchanged.

## full (2022-01-01 ~ 2026-04-24)

| scenario | return | drawdown | trades | win_rate | return_delta | drawdown_delta | trade_delta |
|---|---:|---:|---:|---:|---:|---:|---:|
| combined | 0.08% | 5.53% | 345 | 49.18% | 0.00% | 0.00% | 0 |
| exempt_AP888 | 0.17% | 5.44% | 346 | 49.31% | 0.09% | -0.09% | 1 |
| exempt_A888 | 0.19% | 5.44% | 346 | 49.45% | 0.11% | -0.09% | 1 |
| exempt_AP888_A888 | 0.28% | 5.35% | 347 | 49.58% | 0.20% | -0.18% | 2 |

| scenario | symbol | return | drawdown | trades | win_rate |
|---|---|---:|---:|---:|---:|
| combined | AP888 | 6.02% | 4.04% | 66 | 56.06% |
| combined | RB888 | -0.45% | 2.11% | 45 | 51.11% |
| combined | SC888 | -6.06% | 8.42% | 110 | 58.18% |
| combined | A888 | -0.73% | 6.35% | 46 | 36.96% |
| combined | ZN888 | 1.62% | 6.73% | 78 | 43.59% |
| exempt_AP888 | AP888 | 6.48% | 3.58% | 67 | 56.72% |
| exempt_AP888 | RB888 | -0.45% | 2.11% | 45 | 51.11% |
| exempt_AP888 | SC888 | -6.06% | 8.42% | 110 | 58.18% |
| exempt_AP888 | A888 | -0.73% | 6.35% | 46 | 36.96% |
| exempt_AP888 | ZN888 | 1.62% | 6.73% | 78 | 43.59% |
| exempt_A888 | AP888 | 6.02% | 4.04% | 66 | 56.06% |
| exempt_A888 | RB888 | -0.45% | 2.11% | 45 | 51.11% |
| exempt_A888 | SC888 | -6.06% | 8.42% | 110 | 58.18% |
| exempt_A888 | A888 | -0.20% | 5.90% | 47 | 38.30% |
| exempt_A888 | ZN888 | 1.62% | 6.73% | 78 | 43.59% |
| exempt_AP888_A888 | AP888 | 6.48% | 3.58% | 67 | 56.72% |
| exempt_AP888_A888 | RB888 | -0.45% | 2.11% | 45 | 51.11% |
| exempt_AP888_A888 | SC888 | -6.06% | 8.42% | 110 | 58.18% |
| exempt_AP888_A888 | A888 | -0.20% | 5.90% | 47 | 38.30% |
| exempt_AP888_A888 | ZN888 | 1.62% | 6.73% | 78 | 43.59% |

## out_sample (2025-01-01 ~ 2026-04-24)

| scenario | return | drawdown | trades | win_rate | return_delta | drawdown_delta | trade_delta |
|---|---:|---:|---:|---:|---:|---:|---:|
| combined | 1.16% | 3.27% | 89 | 56.48% | 0.00% | 0.00% | 0 |
| exempt_AP888 | 1.16% | 3.27% | 89 | 56.48% | 0.00% | 0.00% | 0 |
| exempt_A888 | 1.16% | 3.27% | 89 | 56.48% | 0.00% | 0.00% | 0 |
| exempt_AP888_A888 | 1.16% | 3.27% | 89 | 56.48% | 0.00% | 0.00% | 0 |

| scenario | symbol | return | drawdown | trades | win_rate |
|---|---|---:|---:|---:|---:|
| combined | AP888 | 5.37% | 1.77% | 15 | 73.33% |
| combined | RB888 | 0.78% | 1.27% | 17 | 58.82% |
| combined | SC888 | -5.17% | 6.52% | 25 | 44.00% |
| combined | A888 | 3.67% | 3.83% | 16 | 56.25% |
| combined | ZN888 | 1.16% | 2.98% | 16 | 50.00% |
| exempt_AP888 | AP888 | 5.37% | 1.77% | 15 | 73.33% |
| exempt_AP888 | RB888 | 0.78% | 1.27% | 17 | 58.82% |
| exempt_AP888 | SC888 | -5.17% | 6.52% | 25 | 44.00% |
| exempt_AP888 | A888 | 3.67% | 3.83% | 16 | 56.25% |
| exempt_AP888 | ZN888 | 1.16% | 2.98% | 16 | 50.00% |
| exempt_A888 | AP888 | 5.37% | 1.77% | 15 | 73.33% |
| exempt_A888 | RB888 | 0.78% | 1.27% | 17 | 58.82% |
| exempt_A888 | SC888 | -5.17% | 6.52% | 25 | 44.00% |
| exempt_A888 | A888 | 3.67% | 3.83% | 16 | 56.25% |
| exempt_A888 | ZN888 | 1.16% | 2.98% | 16 | 50.00% |
| exempt_AP888_A888 | AP888 | 5.37% | 1.77% | 15 | 73.33% |
| exempt_AP888_A888 | RB888 | 0.78% | 1.27% | 17 | 58.82% |
| exempt_AP888_A888 | SC888 | -5.17% | 6.52% | 25 | 44.00% |
| exempt_AP888_A888 | A888 | 3.67% | 3.83% | 16 | 56.25% |
| exempt_AP888_A888 | ZN888 | 1.16% | 2.98% | 16 | 50.00% |
