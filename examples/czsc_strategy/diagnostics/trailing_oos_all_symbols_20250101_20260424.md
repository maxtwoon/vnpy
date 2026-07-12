# 五品种移动止损样本外验证

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


- 区间：2025-01-01 ~ 2026-04-24
- baseline：默认 `300 / 0.25`
- tuned：`150 / 0.15`

| 品种 | baseline收益 | tuned收益 | 收益差 | baseline回撤 | tuned回撤 | 回撤差 | baseline交易 | tuned交易 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| AP888 | 5.37% | 2.79% | -2.58% | 1.77% | 1.11% | -0.66% | 15 | 18 |
| RB888 | -1.54% | 1.03% | 2.57% | 3.17% | 1.35% | -1.82% | 13 | 18 |
| SC888 | -11.24% | -9.30% | 1.94% | 11.56% | 10.62% | -0.94% | 32 | 33 |
| A888 | 3.67% | 2.97% | -0.70% | 3.83% | 1.04% | -2.79% | 16 | 20 |
| ZN888 | 1.16% | 0.09% | -1.07% | 2.98% | 2.64% | -0.34% | 16 | 18 |

## 结论

- 收益改善品种数：2 / 5
- 回撤不恶化品种数：5 / 5
- 若收益改善少于 3 个品种或回撤普遍恶化，不建议设为全局默认。
