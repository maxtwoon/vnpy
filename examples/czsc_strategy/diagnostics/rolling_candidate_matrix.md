# Rolling Candidate Matrix

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


- generated_at: `2026-06-19T03:30:22.013602+00:00`
- windows: half-year windows plus 2026YTD.
- expanded: combined plus AP888/A888 exemption from the 3% second-buy chase filter.

| window | scenario | return | drawdown | trades | win_rate | return_delta | drawdown_delta | trade_delta | errors |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 2022H1 | baseline | 0.02% | 1.73% | 50 | 45.33% | 0.00% | 0.00% | 0 | 0 |
| 2022H1 | combined | -0.28% | 1.64% | 46 | 44.76% | -0.30% | -0.10% | -4 | 0 |
| 2022H1 | expanded | -0.19% | 1.55% | 47 | 45.67% | -0.21% | -0.19% | -3 | 0 |
| 2022H2 | baseline | -0.04% | 1.67% | 55 | 49.92% | 0.00% | 0.00% | 0 | 0 |
| 2022H2 | combined | 0.46% | 1.00% | 51 | 56.66% | 0.51% | -0.67% | -4 | 0 |
| 2022H2 | expanded | 0.57% | 1.04% | 52 | 58.66% | 0.61% | -0.62% | -3 | 0 |
| 2023H1 | baseline | -1.48% | 2.00% | 39 | 25.33% | 0.00% | 0.00% | 0 | 0 |
| 2023H1 | combined | -1.28% | 1.59% | 37 | 28.33% | 0.20% | -0.41% | -2 | 0 |
| 2023H1 | expanded | -1.28% | 1.59% | 37 | 28.33% | 0.20% | -0.41% | -2 | 0 |
| 2023H2 | baseline | 0.37% | 1.11% | 28 | 61.90% | 0.00% | 0.00% | 0 | 0 |
| 2023H2 | combined | 0.37% | 0.84% | 30 | 70.57% | -0.00% | -0.27% | 2 | 0 |
| 2023H2 | expanded | 0.37% | 0.84% | 30 | 70.57% | -0.00% | -0.27% | 2 | 0 |
| 2024H1 | baseline | 0.52% | 1.29% | 34 | 43.39% | 0.00% | 0.00% | 0 | 0 |
| 2024H1 | combined | 0.46% | 1.09% | 35 | 45.77% | -0.07% | -0.20% | 1 | 0 |
| 2024H1 | expanded | 0.46% | 1.09% | 35 | 45.77% | -0.07% | -0.20% | 1 | 0 |
| 2024H2 | baseline | -0.25% | 1.90% | 41 | 35.00% | 0.00% | 0.00% | 0 | 0 |
| 2024H2 | combined | 0.34% | 1.29% | 40 | 44.77% | 0.59% | -0.60% | -1 | 0 |
| 2024H2 | expanded | 0.34% | 1.29% | 40 | 44.77% | 0.59% | -0.60% | -1 | 0 |
| 2025H1 | baseline | -0.36% | 1.54% | 28 | 32.52% | 0.00% | 0.00% | 0 | 0 |
| 2025H1 | combined | 0.07% | 1.12% | 28 | 45.00% | 0.43% | -0.42% | 0 | 0 |
| 2025H1 | expanded | 0.07% | 1.12% | 28 | 45.00% | 0.43% | -0.42% | 0 | 0 |
| 2025H2 | baseline | 1.44% | 1.31% | 38 | 63.33% | 0.00% | 0.00% | 0 | 0 |
| 2025H2 | combined | 1.45% | 1.17% | 38 | 62.78% | 0.01% | -0.14% | 0 | 0 |
| 2025H2 | expanded | 1.45% | 1.17% | 38 | 62.78% | 0.01% | -0.14% | 0 | 0 |
| 2026YTD | baseline | -0.64% | 1.46% | 17 | 34.67% | 0.00% | 0.00% | 0 | 0 |
| 2026YTD | combined | -0.40% | 1.19% | 17 | 38.67% | 0.23% | -0.27% | 0 | 0 |
| 2026YTD | expanded | -0.40% | 1.19% | 17 | 38.67% | 0.23% | -0.27% | 0 | 0 |

## Symbol Detail

### 2022H1 (2022-01-01 ~ 2022-06-30)

| scenario | symbol | return | drawdown | trades | win_rate |
|---|---|---:|---:|---:|---:|
| baseline | AP888 | -1.98% | 2.95% | 12 | 50.00% |
| baseline | RB888 | -0.64% | 0.80% | 4 | 25.00% |
| baseline | SC888 | 1.84% | 1.41% | 15 | 73.33% |
| baseline | A888 | -0.04% | 0.74% | 4 | 25.00% |
| baseline | ZN888 | 0.92% | 2.77% | 15 | 53.33% |
| combined | AP888 | -2.44% | 3.41% | 11 | 45.45% |
| combined | RB888 | -0.64% | 0.80% | 4 | 25.00% |
| combined | SC888 | 0.79% | 0.47% | 12 | 75.00% |
| combined | A888 | -0.04% | 0.74% | 4 | 25.00% |
| combined | ZN888 | 0.92% | 2.77% | 15 | 53.33% |
| expanded | AP888 | -1.98% | 2.95% | 12 | 50.00% |
| expanded | RB888 | -0.64% | 0.80% | 4 | 25.00% |
| expanded | SC888 | 0.79% | 0.47% | 12 | 75.00% |
| expanded | A888 | -0.04% | 0.74% | 4 | 25.00% |
| expanded | ZN888 | 0.92% | 2.77% | 15 | 53.33% |

### 2022H2 (2022-07-01 ~ 2022-12-31)

| scenario | symbol | return | drawdown | trades | win_rate |
|---|---|---:|---:|---:|---:|
| baseline | AP888 | -0.29% | 1.06% | 10 | 40.00% |
| baseline | RB888 | -0.64% | 1.77% | 5 | 40.00% |
| baseline | SC888 | -1.06% | 4.31% | 27 | 48.15% |
| baseline | A888 | 0.27% | 0.84% | 6 | 50.00% |
| baseline | ZN888 | 1.49% | 0.35% | 7 | 71.43% |
| combined | AP888 | -0.29% | 1.06% | 10 | 40.00% |
| combined | RB888 | -0.02% | 0.74% | 6 | 66.67% |
| combined | SC888 | 1.39% | 2.23% | 23 | 65.22% |
| combined | A888 | -0.26% | 0.62% | 5 | 40.00% |
| combined | ZN888 | 1.49% | 0.35% | 7 | 71.43% |
| expanded | AP888 | -0.29% | 1.06% | 10 | 40.00% |
| expanded | RB888 | -0.02% | 0.74% | 6 | 66.67% |
| expanded | SC888 | 1.39% | 2.23% | 23 | 65.22% |
| expanded | A888 | 0.27% | 0.84% | 6 | 50.00% |
| expanded | ZN888 | 1.49% | 0.35% | 7 | 71.43% |

### 2023H1 (2023-01-01 ~ 2023-06-30)

| scenario | symbol | return | drawdown | trades | win_rate |
|---|---|---:|---:|---:|---:|
| baseline | AP888 | -0.76% | 1.27% | 4 | 50.00% |
| baseline | RB888 | -1.71% | 2.42% | 6 | 16.67% |
| baseline | SC888 | -2.26% | 3.36% | 15 | 40.00% |
| baseline | A888 | -0.89% | 0.93% | 4 | 0.00% |
| baseline | ZN888 | -1.79% | 2.03% | 10 | 20.00% |
| combined | AP888 | -0.76% | 1.27% | 4 | 50.00% |
| combined | RB888 | -0.56% | 0.63% | 4 | 25.00% |
| combined | SC888 | -2.41% | 3.09% | 15 | 46.67% |
| combined | A888 | -0.89% | 0.93% | 4 | 0.00% |
| combined | ZN888 | -1.79% | 2.03% | 10 | 20.00% |
| expanded | AP888 | -0.76% | 1.27% | 4 | 50.00% |
| expanded | RB888 | -0.56% | 0.63% | 4 | 25.00% |
| expanded | SC888 | -2.41% | 3.09% | 15 | 46.67% |
| expanded | A888 | -0.89% | 0.93% | 4 | 0.00% |
| expanded | ZN888 | -1.79% | 2.03% | 10 | 20.00% |

### 2023H2 (2023-07-01 ~ 2023-12-31)

| scenario | symbol | return | drawdown | trades | win_rate |
|---|---|---:|---:|---:|---:|
| baseline | AP888 | 1.26% | 0.93% | 2 | 100.00% |
| baseline | RB888 | 0.01% | 0.45% | 4 | 50.00% |
| baseline | SC888 | 0.81% | 1.92% | 9 | 66.67% |
| baseline | A888 | -0.03% | 0.87% | 6 | 50.00% |
| baseline | ZN888 | -0.18% | 1.36% | 7 | 42.86% |
| combined | AP888 | 1.26% | 0.93% | 2 | 100.00% |
| combined | RB888 | 0.45% | 0.31% | 5 | 80.00% |
| combined | SC888 | 0.36% | 0.74% | 10 | 80.00% |
| combined | A888 | -0.03% | 0.87% | 6 | 50.00% |
| combined | ZN888 | -0.18% | 1.36% | 7 | 42.86% |
| expanded | AP888 | 1.26% | 0.93% | 2 | 100.00% |
| expanded | RB888 | 0.45% | 0.31% | 5 | 80.00% |
| expanded | SC888 | 0.36% | 0.74% | 10 | 80.00% |
| expanded | A888 | -0.03% | 0.87% | 6 | 50.00% |
| expanded | ZN888 | -0.18% | 1.36% | 7 | 42.86% |

### 2024H1 (2024-01-01 ~ 2024-06-30)

| scenario | symbol | return | drawdown | trades | win_rate |
|---|---|---:|---:|---:|---:|
| baseline | AP888 | -0.81% | 1.47% | 9 | 44.44% |
| baseline | RB888 | -1.23% | 1.45% | 6 | 16.67% |
| baseline | SC888 | 1.30% | 0.72% | 5 | 60.00% |
| baseline | A888 | -1.04% | 1.35% | 6 | 33.33% |
| baseline | ZN888 | 4.40% | 1.46% | 8 | 62.50% |
| combined | AP888 | -0.81% | 1.47% | 9 | 44.44% |
| combined | RB888 | -0.60% | 0.76% | 7 | 28.57% |
| combined | SC888 | 0.33% | 0.41% | 5 | 60.00% |
| combined | A888 | -1.04% | 1.35% | 6 | 33.33% |
| combined | ZN888 | 4.40% | 1.46% | 8 | 62.50% |
| expanded | AP888 | -0.81% | 1.47% | 9 | 44.44% |
| expanded | RB888 | -0.60% | 0.76% | 7 | 28.57% |
| expanded | SC888 | 0.33% | 0.41% | 5 | 60.00% |
| expanded | A888 | -1.04% | 1.35% | 6 | 33.33% |
| expanded | ZN888 | 4.40% | 1.46% | 8 | 62.50% |

### 2024H2 (2024-07-01 ~ 2024-12-31)

| scenario | symbol | return | drawdown | trades | win_rate |
|---|---|---:|---:|---:|---:|
| baseline | AP888 | 2.47% | 2.96% | 10 | 60.00% |
| baseline | RB888 | -1.21% | 2.27% | 4 | 25.00% |
| baseline | SC888 | -2.18% | 2.80% | 15 | 40.00% |
| baseline | A888 | 0.02% | 0.26% | 4 | 25.00% |
| baseline | ZN888 | -0.32% | 1.19% | 8 | 25.00% |
| combined | AP888 | 2.47% | 2.96% | 10 | 60.00% |
| combined | RB888 | 0.25% | 0.62% | 5 | 60.00% |
| combined | SC888 | -0.71% | 1.44% | 13 | 53.85% |
| combined | A888 | 0.02% | 0.26% | 4 | 25.00% |
| combined | ZN888 | -0.32% | 1.19% | 8 | 25.00% |
| expanded | AP888 | 2.47% | 2.96% | 10 | 60.00% |
| expanded | RB888 | 0.25% | 0.62% | 5 | 60.00% |
| expanded | SC888 | -0.71% | 1.44% | 13 | 53.85% |
| expanded | A888 | 0.02% | 0.26% | 4 | 25.00% |
| expanded | ZN888 | -0.32% | 1.19% | 8 | 25.00% |

### 2025H1 (2025-01-01 ~ 2025-06-30)

| scenario | symbol | return | drawdown | trades | win_rate |
|---|---|---:|---:|---:|---:|
| baseline | AP888 | -0.19% | 1.77% | 6 | 33.33% |
| baseline | RB888 | -0.62% | 1.54% | 5 | 40.00% |
| baseline | SC888 | -0.55% | 1.70% | 7 | 14.29% |
| baseline | A888 | 1.25% | 0.85% | 4 | 75.00% |
| baseline | ZN888 | -1.70% | 1.85% | 6 | 0.00% |
| combined | AP888 | -0.19% | 1.77% | 6 | 33.33% |
| combined | RB888 | 0.19% | 0.40% | 6 | 66.67% |
| combined | SC888 | 0.79% | 0.72% | 6 | 50.00% |
| combined | A888 | 1.25% | 0.85% | 4 | 75.00% |
| combined | ZN888 | -1.70% | 1.85% | 6 | 0.00% |
| expanded | AP888 | -0.19% | 1.77% | 6 | 33.33% |
| expanded | RB888 | 0.19% | 0.40% | 6 | 66.67% |
| expanded | SC888 | 0.79% | 0.72% | 6 | 50.00% |
| expanded | A888 | 1.25% | 0.85% | 4 | 75.00% |
| expanded | ZN888 | -1.70% | 1.85% | 6 | 0.00% |

### 2025H2 (2025-07-01 ~ 2025-12-31)

| scenario | symbol | return | drawdown | trades | win_rate |
|---|---|---:|---:|---:|---:|
| baseline | AP888 | 3.51% | 0.94% | 6 | 100.00% |
| baseline | RB888 | 0.31% | 1.03% | 6 | 50.00% |
| baseline | SC888 | -0.84% | 1.86% | 12 | 41.67% |
| baseline | A888 | 2.04% | 0.88% | 6 | 50.00% |
| baseline | ZN888 | 2.19% | 1.82% | 8 | 75.00% |
| combined | AP888 | 3.51% | 0.94% | 6 | 100.00% |
| combined | RB888 | 0.37% | 0.98% | 9 | 55.56% |
| combined | SC888 | -0.86% | 1.22% | 9 | 33.33% |
| combined | A888 | 2.04% | 0.88% | 6 | 50.00% |
| combined | ZN888 | 2.19% | 1.82% | 8 | 75.00% |
| expanded | AP888 | 3.51% | 0.94% | 6 | 100.00% |
| expanded | RB888 | 0.37% | 0.98% | 9 | 55.56% |
| expanded | SC888 | -0.86% | 1.22% | 9 | 33.33% |
| expanded | A888 | 2.04% | 0.88% | 6 | 50.00% |
| expanded | ZN888 | 2.19% | 1.82% | 8 | 75.00% |

### 2026YTD (2026-01-01 ~ 2026-04-24)

| scenario | symbol | return | drawdown | trades | win_rate |
|---|---|---:|---:|---:|---:|
| baseline | AP888 | -3.99% | 4.53% | 6 | 16.67% |
| baseline | RB888 | 0.36% | 0.46% | 2 | 50.00% |
| baseline | SC888 | -0.99% | 1.62% | 5 | 40.00% |
| baseline | A888 | 1.52% | 0.55% | 3 | 66.67% |
| baseline | ZN888 | -0.08% | 0.14% | 1 | 0.00% |
| combined | AP888 | -3.99% | 4.53% | 6 | 16.67% |
| combined | RB888 | 0.26% | 0.46% | 2 | 50.00% |
| combined | SC888 | 0.27% | 0.28% | 5 | 60.00% |
| combined | A888 | 1.52% | 0.55% | 3 | 66.67% |
| combined | ZN888 | -0.08% | 0.14% | 1 | 0.00% |
| expanded | AP888 | -3.99% | 4.53% | 6 | 16.67% |
| expanded | RB888 | 0.26% | 0.46% | 2 | 50.00% |
| expanded | SC888 | 0.27% | 0.28% | 5 | 60.00% |
| expanded | A888 | 1.52% | 0.55% | 3 | 66.67% |
| expanded | ZN888 | -0.08% | 0.14% | 1 | 0.00% |
