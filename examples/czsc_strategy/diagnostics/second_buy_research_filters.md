# 二买追高过滤与分品种启用研究

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


- max_entry_vs_anchor：3.00%
- enable_2buy_symbols：AP888 / A888 / ZN888
- 口径：不改正式策略；按已发生二买交易做研究性剔除，并估算剔除后的最终收益。

## full (2022-01-01 ~ 2026-04-24)

| 场景 | 保留二买 | 保留二买收益 | 保留胜率 | 排除二买 | 排除二买收益 |
|---|---:|---:|---:|---:|---:|
| baseline | 53 | -31.30% | 45.28% | 0 | 0.00% |
| entry_filter | 38 | 0.67% | 50.00% | 15 | -31.97% |
| symbol_filter | 23 | 29.72% | 65.22% | 30 | -61.02% |
| combined | 21 | 24.76% | 61.90% | 32 | -56.05% |

### 按品种 adjusted_return_pct

| 场景 | 品种 | baseline收益 | adjusted收益 | 差值 | 保留二买 | 排除二买 |
|---|---|---:|---:|---:|---:|---:|
| baseline | AP888 | 6.48% | 6.48% | 0.00% | 4 | 0 |
| baseline | RB888 | -8.02% | -8.02% | 0.00% | 6 | 0 |
| baseline | SC888 | -10.87% | -10.87% | 0.00% | 24 | 0 |
| baseline | A888 | -0.20% | -0.20% | 0.00% | 7 | 0 |
| baseline | ZN888 | 1.62% | 1.62% | 0.00% | 12 | 0 |
| entry_filter | AP888 | 6.48% | 6.02% | -0.46% | 3 | 1 |
| entry_filter | RB888 | -8.02% | -7.35% | 0.67% | 5 | 1 |
| entry_filter | SC888 | -10.87% | -4.15% | 6.72% | 12 | 12 |
| entry_filter | A888 | -0.20% | -0.73% | -0.53% | 6 | 1 |
| entry_filter | ZN888 | 1.62% | 1.62% | 0.00% | 12 | 0 |
| symbol_filter | AP888 | 6.48% | 6.48% | 0.00% | 4 | 0 |
| symbol_filter | RB888 | -8.02% | -3.89% | 4.13% | 0 | 6 |
| symbol_filter | SC888 | -10.87% | -2.80% | 8.07% | 0 | 24 |
| symbol_filter | A888 | -0.20% | -0.20% | 0.00% | 7 | 0 |
| symbol_filter | ZN888 | 1.62% | 1.62% | 0.00% | 12 | 0 |
| combined | AP888 | 6.48% | 6.02% | -0.46% | 3 | 1 |
| combined | RB888 | -8.02% | -3.89% | 4.13% | 0 | 6 |
| combined | SC888 | -10.87% | -2.80% | 8.07% | 0 | 24 |
| combined | A888 | -0.20% | -0.73% | -0.53% | 6 | 1 |
| combined | ZN888 | 1.62% | 1.62% | 0.00% | 12 | 0 |

## out_sample (2025-01-01 ~ 2026-04-24)

| 场景 | 保留二买 | 保留二买收益 | 保留胜率 | 排除二买 | 排除二买收益 |
|---|---:|---:|---:|---:|---:|
| baseline | 17 | -4.00% | 52.94% | 0 | 0.00% |
| entry_filter | 14 | 15.58% | 64.29% | 3 | -19.58% |
| symbol_filter | 9 | 21.45% | 77.78% | 8 | -25.45% |
| combined | 9 | 21.45% | 77.78% | 8 | -25.45% |

### 按品种 adjusted_return_pct

| 场景 | 品种 | baseline收益 | adjusted收益 | 差值 | 保留二买 | 排除二买 |
|---|---|---:|---:|---:|---:|---:|
| baseline | AP888 | 5.37% | 5.37% | 0.00% | 3 | 0 |
| baseline | RB888 | -1.54% | -1.54% | 0.00% | 1 | 0 |
| baseline | SC888 | -11.24% | -11.24% | 0.00% | 7 | 0 |
| baseline | A888 | 3.67% | 3.67% | 0.00% | 4 | 0 |
| baseline | ZN888 | 1.16% | 1.16% | 0.00% | 2 | 0 |
| entry_filter | AP888 | 5.37% | 5.37% | 0.00% | 3 | 0 |
| entry_filter | RB888 | -1.54% | -1.54% | 0.00% | 1 | 0 |
| entry_filter | SC888 | -11.24% | -7.33% | 3.92% | 4 | 3 |
| entry_filter | A888 | 3.67% | 3.67% | 0.00% | 4 | 0 |
| entry_filter | ZN888 | 1.16% | 1.16% | 0.00% | 2 | 0 |
| symbol_filter | AP888 | 5.37% | 5.37% | 0.00% | 3 | 0 |
| symbol_filter | RB888 | -1.54% | -0.90% | 0.64% | 0 | 1 |
| symbol_filter | SC888 | -11.24% | -6.80% | 4.45% | 0 | 7 |
| symbol_filter | A888 | 3.67% | 3.67% | 0.00% | 4 | 0 |
| symbol_filter | ZN888 | 1.16% | 1.16% | 0.00% | 2 | 0 |
| combined | AP888 | 5.37% | 5.37% | 0.00% | 3 | 0 |
| combined | RB888 | -1.54% | -0.90% | 0.64% | 0 | 1 |
| combined | SC888 | -11.24% | -6.80% | 4.45% | 0 | 7 |
| combined | A888 | 3.67% | 3.67% | 0.00% | 4 | 0 |
| combined | ZN888 | 1.16% | 1.16% | 0.00% | 2 | 0 |
