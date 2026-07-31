# 移动止损分品种候选研究

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


- overrides：RB888 / SC888 使用 `150 / 0.15`，其他品种保持默认。
- 口径：逐品种独立回测，组合行使用五品种简单平均收益/回撤与交易数求和。

## full (2022-01-01 ~ 2026-04-24)

| 品种 | 参数 | baseline收益 | override收益 | 收益差 | baseline回撤 | override回撤 | 回撤差 | baseline交易 | override交易 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| AP888 | {"default": true} | 6.48% | 6.48% | 0.00% | 3.58% | 3.58% | 0.00% | 67 | 67 |
| RB888 | {"trailing_start_bp": 150, "trailing_drawback_pct": 0.15} | -8.02% | -1.72% | 6.30% | 8.75% | 3.18% | -5.57% | 43 | 51 |
| SC888 | {"trailing_start_bp": 150, "trailing_drawback_pct": 0.15} | -10.87% | -11.11% | -0.24% | 15.80% | 13.14% | -2.66% | 123 | 138 |
| A888 | {"default": true} | -0.20% | -0.20% | 0.00% | 5.90% | 5.90% | 0.00% | 47 | 47 |
| ZN888 | {"default": true} | 1.62% | 1.62% | 0.00% | 6.73% | 6.73% | 0.00% | 78 | 78 |
| 组合均值 | - | -2.20% | -0.98% | 1.21% | 8.15% | 6.51% | -1.65% | 358 | 381 |

## out_sample (2025-01-01 ~ 2026-04-24)

| 品种 | 参数 | baseline收益 | override收益 | 收益差 | baseline回撤 | override回撤 | 回撤差 | baseline交易 | override交易 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| AP888 | {"default": true} | 5.37% | 5.37% | 0.00% | 1.77% | 1.77% | 0.00% | 15 | 15 |
| RB888 | {"trailing_start_bp": 150, "trailing_drawback_pct": 0.15} | -1.54% | 1.03% | 2.57% | 3.17% | 1.35% | -1.82% | 13 | 18 |
| SC888 | {"trailing_start_bp": 150, "trailing_drawback_pct": 0.15} | -11.24% | -9.30% | 1.94% | 11.56% | 10.62% | -0.94% | 32 | 33 |
| A888 | {"default": true} | 3.67% | 3.67% | 0.00% | 3.83% | 3.83% | 0.00% | 16 | 16 |
| ZN888 | {"default": true} | 1.16% | 1.16% | 0.00% | 2.98% | 2.98% | 0.00% | 16 | 16 |
| 组合均值 | - | -0.52% | 0.39% | 0.90% | 4.66% | 4.11% | -0.55% | 92 | 98 |
